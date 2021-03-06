from genericpath import exists
import time, json, os, hmac
from requests import Request, Response, Session
from ciso8601 import parse_datetime

class FtxClient:

    _ENDPOINT = 'https://ftx.com/api/'

    def __init__(self):
        #check settings file
        settings_file = f"{os.environ['HOME']}/.config/ftxclient/settings.json"
        if exists(settings_file):
            keys_file = open(settings_file, 'r')
            keys_file_content = keys_file.read()
            keys = json.loads(keys_file_content)
            self._api_key = keys['api_key']
            self._api_sec = keys['api_sec_key']
        else:
            # creating ~/.config/ftxclient/settings.json
            print(">>> settings file not found. creating...")
            settings_template = '{\n"api_key" : "put_your_api-key_there",\n"api_sec_key":"put_your_api-sec-key_there"\n}'
            os.makedirs(os.path.dirname(settings_file), exist_ok=True)
            new_settings_file = open(settings_file, 'w')
            new_settings_file.write(str(settings_template))
            new_settings_file.close()
            print(f">>> settings file created. fill your keys in {settings_file} >>> exiting")
            exit()
        self._session = Session()


    def _sign_request(self, request: Request):
        ts = int(time.time() * 1000)
        preparedRequest = request.prepare()
        signature_payload = f'{ts}{preparedRequest.method}{preparedRequest.path_url}'.encode()
        signature = hmac.new(self._api_sec.encode(), signature_payload, 'sha256').hexdigest()
        preparedRequest.headers['FTX-KEY'] = self._api_key
        preparedRequest.headers['FTX-SIGN'] = signature
        preparedRequest.headers['FTX-TS'] = str(ts)
        return preparedRequest


    def _send_request(self, method: str, path: str, **kwargs):
        request = Request(method, self._ENDPOINT + path, **kwargs)
        preparedRequest = self._sign_request(request)
        response = self._session.send(preparedRequest)
        return (self._prepare_response(response))


    def _get(self, path: str, params=None):
        return self._send_request('GET', path, params=params)


    def _post(self, request):
        return self._send_request('POST', request)


    def _prepare_response(self, response: Response):
        try:
            data = response.json()
        except ValueError:
            response.raise_for_status()
            raise
        else:
            if not data['success']:
                raise Exception(data['error'])
            return data['result']


    def get_all_futures(self):
        return self._get('futures')


    def get_balances(self):
        return self._get('wallet/balances')


    def get_account_info(self):
        return self._get('account')
    

    def get_future(self, future_name: str = None):
        return self._get(f'futures/{future_name}')


    def get_markets(self):
        return self._get('markets')


    def get_orderbook(self, market: str, depth: int = None):
        return self._get(f'markets/{market}/orderbook', {'depth': depth})


    def get_trades(self, market: str, start_time: float = None, end_time: float = None):
        return self._get(f'markets/{market}/trades', {'start_time': start_time, 'end_time': end_time})


    def get_open_orders(self, market: str = None):
        return self._get(f'orders', {'market': market})


    def get_order_history(
        self, market: str = None, side: str = None, order_type: str = None,
        start_time: float = None, end_time: float = None):
        return self._get(f'orders/history', {
            'market': market,
            'side': side,
            'orderType': order_type,
            'start_time': start_time,
            'end_time': end_time
        })


    def get_conditional_order_history(
        self, market: str = None, side: str = None, type: str = None,
        order_type: str = None, start_time: float = None, end_time: float = None):
        return self._get(f'conditional_orders/history', {
            'market': market,
            'side': side,
            'type': type,
            'orderType': order_type,
            'start_time': start_time,
            'end_time': end_time
        })


    def modify_order(
        self, existing_order_id: str = None,
        existing_client_order_id: str = None, price: float = None,
        size: float = None, client_order_id: str = None):
        assert (existing_order_id is None) ^ (existing_client_order_id is None), \
            'Must supply exactly one ID for the order to modify'
        assert (price is None) or (size is None), 'Must modify price or size of order'
        path = f'orders/{existing_order_id}/modify' if existing_order_id is not None else \
            f'orders/by_client_id/{existing_client_order_id}/modify'
        return self._post(path, {
            **({'size': size} if size is not None else {}),
            **({'price': price} if price is not None else {}),
            ** ({'clientId': client_order_id} if client_order_id is not None else {}),
        })


    def get_conditional_orders(self, market: str = None):
        return self._get(f'conditional_orders', {'market': market})


    def place_order(self, market: str, side: str, price: float, size: float, type: str = 'limit',
                    reduce_only: bool = False, ioc: bool = False, post_only: bool = False,
                    client_id: str = None, reject_after_ts: float = None):
        return self._post('orders', {
            'market': market,
            'side': side,
            'price': price,
            'size': size,
            'type': type,
            'reduceOnly': reduce_only,
            'ioc': ioc,
            'postOnly': post_only,
            'clientId': client_id,
            'rejectAfterTs': reject_after_ts
        })


    def place_conditional_order(
        self, market: str, side: str, size: float, type: str = 'stop',
        limit_price: float = None, reduce_only: bool = False, cancel: bool = True,
        trigger_price: float = None, trail_value: float = None):
        """
        To send a Stop Market order, set type='stop' and supply a trigger_price
        To send a Stop Limit order, also supply a limit_price
        To send a Take Profit Market order, set type='trailing_stop' and supply a trigger_price
        To send a Trailing Stop order, set type='trailing_stop' and supply a trail_value
        """
        assert type in ('stop', 'take_profit', 'trailing_stop')
        assert type not in ('stop', 'take_profit') or trigger_price is not None, \
            'Need trigger prices for stop losses and take profits'
        assert type not in ('trailing_stop',) or (trigger_price is None and trail_value is not None), \
            'Trailing stops need a trail value and cannot take a trigger price'

        return self._post('conditional_orders', {
            'market': market,
            'side': side,
            'triggerPrice': trigger_price,
            'size': size,
            'reduceOnly': reduce_only,
            'type': 'stop',
            'cancelLimitOnTrigger': cancel,
            'orderPrice': limit_price
        })


    def cancel_order(self, order_id: str):
        return self._delete(f'orders/{order_id}')


    def cancel_orders(
        self, market_name: str = None,
        conditional_orders: bool = False, limit_orders: bool = False
    ):
        return self._delete(f'orders', {
            'market': market_name,
            'conditionalOrdersOnly': conditional_orders,
            'limitOrdersOnly': limit_orders
        })


    def get_fills(self, market: str = None, start_time: float = None,
        end_time: float = None, min_id: int = None, order_id: int = None):
        return self._get('fills', {
            'market': market,
            'start_time': start_time,
            'end_time': end_time,
            'minId': min_id,
            'orderId': order_id
        })


    def get_total_usd_balance(self):
        total_usd = 0
        balances = self._get('wallet/balances')
        for balance in balances:
            total_usd += balance['usdValue']
        return total_usd

    def get_all_balances(self):
        return self._get('wallet/all_balances')

    def get_total_account_usd_balance(self):
        total_usd = 0
        all_balances = self._get('wallet/all_balances')
        for wallet in all_balances:
            for balance in all_balances[wallet]:
                total_usd += balance['usdValue']
        return total_usd

    def get_positions(self, show_avg_price: bool = False):
        return self._get('positions', {'showAvgPrice': show_avg_price})

    def get_position(self, name: str, show_avg_price: bool = False):
        return next(filter(lambda x: x['future'] == name, self.get_positions(show_avg_price)), None)

    def get_all_trades(self, market: str, start_time: float = None, end_time: float = None):
        ids = set()
        limit = 100
        results = []
        while True:
            response = self._get(f'markets/{market}/trades', {
                'end_time': end_time,
                'start_time': start_time,
            })
            deduped_trades = [r for r in response if r['id'] not in ids]
            results.extend(deduped_trades)
            ids |= {r['id'] for r in deduped_trades}
            print(f'Adding {len(response)} trades with end time {end_time}')
            if len(response) == 0:
                break
            end_time = min(parse_datetime(t['time']) for t in response).timestamp()
            if len(response) < limit:
                break
        return results

    def get_historical_prices(
        self, market: str, resolution: int = 300, start_time: float = None,
        end_time: float = None
    ):
        return self._get(f'markets/{market}/candles', {
            'resolution': resolution,
            'start_time': start_time,
            'end_time': end_time
        })

    def get_last_historical_prices(self, market: str, resolution: int = 300):
        return self._get(f'markets/{market}/candles/last', {'resolution': resolution})

    def get_borrow_rates(self):
        return self._get('spot_margin/borrow_rates')

    def get_borrow_history(self, start_time: float = None, end_time: float = None):
        return self._get('spot_margin/borrow_history', {'start_time': start_time, 'end_time': end_time})

    def get_lending_history(self, start_time: float = None, end_time: float = None):
        return self._get('spot_margin/lending_history', {
            'start_time': start_time,
            'end_time': end_time
        })

    def get_expired_futures(self):
        return self._get('expired_futures')

    def get_coins(self):
        return self._get('wallet/coins')

    def get_future_stats(self, future_name: str):
        return self._get(f'futures/{future_name}/stats')

    def get_single_market(self, market: str = None):
        return self._get(f'markets/{market}')

    def get_market_info(self, market: str = None):
        return self._get('spot_margin/market_info', {'market': market})

    def get_trigger_order_triggers(self, conditional_order_id: str = None):
        return self._get(f'conditional_orders/{conditional_order_id}/triggers')

    def get_trigger_order_history(self, market: str = None):
        return self._get('conditional_orders/history', {'market': market})

    def get_staking_balances(self):
        return self._get('staking/balances')

    def get_stakes(self):
        return self._get('staking/stakes')

    def get_staking_rewards(self, start_time: float = None, end_time: float = None):
        return self._get('staking/staking_rewards', {
            'start_time': start_time,
            'end_time': end_time
        })

    def place_staking_request(self, coin: str = 'SRM', size: float = None):
        return self._post('srm_stakes/stakes',)

    def get_funding_rates(self, future: str = None, start_time: float = None, end_time: float = None):
        return self._get('funding_rates', {
            'future': future,
            'start_time': start_time,
            'end_time': end_time
        })

    def get_all_funding_rates(self):
        return self._get('funding_rates')

    def get_funding_payments(self, start_time: float = None, end_time: float = None):
        return self._get('funding_payments', {
            'start_time': start_time,
            'end_time': end_time
        })

    def create_subaccount(self, nickname: str):
        return self._post('subaccounts', {'nickname': nickname})

    def get_subaccount_balances(self, nickname: str):
        return self._get(f'subaccounts/{nickname}/balances')

    def get_deposit_address(self, ticker: str):
        return self._get(f'wallet/deposit_address/{ticker}')

    def get_deposit_history(self):
        return self._get('wallet/deposits')

    def get_withdrawal_fee(self, coin: str, size: int, address: str, method: str = None, tag: str = None):
        return self._get('wallet/withdrawal_fee', {
            'coin': coin,
            'size': size,
            'address': address,
            'method': method,
            'tag': tag
        })

    def get_withdrawals(self, start_time: float = None, end_time: float = None):
        return self._get('wallet/withdrawals', {'start_time': start_time, 'end_time': end_time})

    def get_saved_addresses(self, coin: str = None):
        return self._get('wallet/saved_addresses', {'coin': coin})

    def submit_fiat_withdrawal(self, coin: str, size: int, saved_address_id: int, code: int = None):
        return self._post('wallet/fiat_withdrawals', {
        'coin': coin,
        'size': size,
        'savedAddressId': saved_address_id,
        'code': code
    })

    def get_latency_stats(self, days: int = 1, subaccount_nickname: str = None):
        return self._get('stats/latency_stats', {'days': days, 'subaccount_nickname': subaccount_nickname})