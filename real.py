import requests
import time

def jquery_list(jquery, data_mode='[') -> dict:
    reverse_mode = {'[': ']', '{': '}', '(': ')'}
    tail_str = jquery[-5:][::-1]
    return eval(jquery[jquery.index(data_mode): -tail_str.index(reverse_mode[data_mode])])
for i in range(3960):
    concept_url = "http://94.push2.eastmoney.com/api/qt/clist/get?cb=jQuery112404219515748621301_1656315378776&pn=1&" \
                  "pz=500&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&wbp2u=|0|0|0|web&fid=f3&" \
                  "fs=m:90+t:3+f:!50&fields=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f24," \
                  "f25,f26,f22,f33,f11,f62,f128,f136,f115,f152,f124,f107,f104,f105,f140,f141,f207,f208,f209,f222&_=" \
                  f"{int(time.time() * 1000)}"


    headers = { 'User-Agent':'Mozilla/5.0 (Windows NT 6.1; ) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.129 Safari/537.36'        }

    response = requests.request("GET", concept_url, headers=headers)
    print(response.text)
    concept_index_list = []
    concept_name, up_down, representative = [], [], []


    for i in jquery_list(jquery=response.text, data_mode='{')['data']['diff']:
        if i['f14'] in ('昨日连板_含一字', '昨日连板', '昨日涨停_含一字', '昨日涨停', '昨日跌停', '昨日触板', '创业板综', 'B股', '上证180_', 'AH股'):
            continue
        concept_index_list.append((i['f12'], i['f14']))
        concept_name.append(i['f14'])
        up_down.append(i['f3'])
        representative.append(i['f62'])
    concept_data = {'概念名称': concept_name, '概念涨跌幅': up_down, '领涨个股': representative}
    print(concept_data)
print("3960没问题")
# save_data(data=concept_data, file_name='概念数据', header=True)
