import misc
import json
import data_handler as dh
import pandas as pd
import numpy as np
import strategy as strat
import datetime
import backtest
import sys

def aberration_sim( mdf, config):
    start_equity = config['capital']
    marginrate = config['marginrate']
    offset = config['offset']
    pos_class = config['pos_class']
    pos_args  = config['pos_args']
    bbands = config['bbands']
    tick_base = config['tick_base']
    close_daily = config['close_daily']
    win = bbands[0]
    k = bbands[1]
    tcost = config['trans_cost']
    unit = config['unit']
    freq = config['freq']
    xdf = dh.conv_ohlc_freq(mdf, freq)
    boll_ma = dh.MA(xdf, win).shift(1)
    boll_std = dh.STDDEV(xdf, win).shift(1)
    upbnd = np.ceil((boll_ma + boll_std * k)/tick_base) * tick_base
    lowbnd = np.floor((boll_ma - boll_std * k)/tick_base) * tick_base
    boll_ma = np.floor(boll_ma/tick_base + 0.5) * tick_base
    xdata = pd.concat([boll_ma, boll_std, upbnd, lowbnd], axis=1, keys=['ma', 'stdev', 'upbnd', 'lowbnd']).fillna(0)
    mdf = mdf.join(xdata, how = 'left').fillna(method='ffill')
    mdf['nxtopen'] = mdf['open'].shift(-1)
    ll = mdf.shape[0]
    mdf['pos'] = pd.Series([0]*ll, index = mdf.index)
    mdf['cost'] = pd.Series([0]*ll, index = mdf.index)
    curr_pos = []
    closed_trades = []
    start_d = mdf.date[0]
    end_d = mdf.date[-1]
    tradeid = 0
    for idx, dd in enumerate(mdf.index):
        mslice = mdf.ix[dd]
        min_id = mslice.min_id
        d = mslice.date
        if len(curr_pos) > 1:
            print "wrong position numbers", len(curr_pos)
            continue
        elif len(curr_pos) == 0:
            pos = 0
            start_pos = 0
        else:
            pos = curr_pos[0].pos
            start_pos = pos
        mdf.ix[dd, 'pos'] = pos
        if mslice.ma == 0:
            continue
        if min_id >=config['exit_min']:
            if (pos!=0) and ((d == end_d) or close_daily):
                curr_pos[0].close(mslice.close - misc.sign(pos) * offset , dd)
                tradeid += 1
                curr_pos[0].exit_tradeid = tradeid
                closed_trades.append(curr_pos[0])
                curr_pos = []
                mdf.ix[dd, 'cost'] -=  abs(pos) * (offset + mslice.close*tcost)
                pos = 0
        else:
            if ((mslice.high >= mslice.ma) and (pos<0)) or ((mslice.low <= mslice.ma) and (pos>0)):
                if pos < 0: 
                    exec_price = max(mslice.open, mslice.ma)
                else:
                    exec_price = min(mslice.open, mslice.ma)
                curr_pos[0].close(exec_price - misc.sign(pos) * offset, dd)
                tradeid += 1
                curr_pos[0].exit_tradeid = tradeid
                closed_trades.append(curr_pos[0])
                curr_pos = []
                mdf.ix[dd, 'cost'] -= abs(pos) * (offset + exec_price*tcost)
                pos = 0
            if ((mslice.high > mslice.upbnd) and (pos<=0)) or ((mslice.low < mslice.lowbnd) and (pos>=0)):
                if (pos == 0):
                    target_pos = (mslice.high > mslice.upbnd) * unit - (mslice.low < mslice.lowbnd) * unit
                    if target_pos == 0:
                        print "the min bar hit both up and low bounds, need to think about how to handle it", start_pos, mslice
                        if mslice.close > mslice.ma:
                            target_pos = (mslice.high > mslice.upbnd) * unit
                            target = max(mslice.open, mslice.upbnd)
                        else:
                            trade_pos = - (mslice.low < mslice.lowbnd) * unit
                            target =  min(mslice.open, mslice.lowbnd)
                    else:
                        target = (mslice.high > mslice.upbnd) * max(mslice.open, mslice.upbnd) + ( mslice.low < mslice.lowbnd) * min(mslice.open, mslice.lowbnd)
                    new_pos = pos_class([mslice.contract], [1], target_pos, target, mslice.ma, **pos_args)
                    tradeid += 1
                    new_pos.entry_tradeid = tradeid
                    new_pos.open(target + misc.sign(target_pos)*offset, dd)
                    curr_pos.append(new_pos)
                    pos = target_pos
                    mdf.ix[dd, 'cost'] -=  abs(target_pos) * (offset + target*tcost)
                else:
                    print "something wrong with position=%s, close =%s, MA=%s, upBnd=%s, lowBnd=%s" % ( pos, mslice.close, mslice.ma, mslice.upbnd, mslice.lowbnd)
        mdf.ix[dd, 'pos'] = pos
    (res_pnl, ts) = backtest.get_pnl_stats( mdf, start_equity, marginrate, 'm')
    res_trade = backtest.get_trade_stats( closed_trades )
    res = dict( res_pnl.items() + res_trade.items())
    return (res, closed_trades, ts)

def gen_config_file(filename):
    sim_config = {}
    sim_config['sim_func']  = 'bktest_aberration.aberration_sim'
    sim_config['scen_keys'] = ['freq', 'bbands']
    sim_config['sim_name']   = 'Abberation_'
    sim_config['products']   = ['y', 'p', 'l', 'pp', 'cs', 'a', 'rb', 'SR', 'TA', 'MA', 'i', 'j', 'jd', 'jm', 'ag', 'cu', 'm', 'RM', 'ru']
    sim_config['start_date'] = '20150102'
    sim_config['end_date']   = '20160429'
    sim_config['need_daily'] = True
    sim_config['freq']  =  [ '15min', '30min', '60min']
    sim_config['bbands'] = [(20, 1), (40, 1)]
    sim_config['chan'] = [10, 20]
    sim_config['pos_class'] = 'strat.TradePos'
    sim_config['offset']    = 1
    chan_func = { 'high': {'func': 'dh.PCT_CHANNEL', 'args':{'pct': 90, 'field': 'high'}},
                  'low':  {'func': 'dh.PCT_CHANNEL', 'args':{'pct': 10, 'field': 'low'}}}
    config = {'capital': 10000,
              'use_chan': False,
              'trans_cost': 0.0,
              'close_daily': False,
              'unit': 1,
              'stoploss': 0.0,
              'pos_args': {},
              'exit_min': 2055,
              'chan_func': chan_func,
              }
    sim_config['config'] = config
    with open(filename, 'w') as outfile:
        json.dump(sim_config, outfile)
    return sim_config

if __name__=="__main__":
    args = sys.argv[1:]
    if len(args) < 1:
        print "need to input a file name for config file"
    else:
        gen_config_file(args[0])
    pass