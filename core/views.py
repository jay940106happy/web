from django.shortcuts import render


def home(request):
    # 先用假資料，之後再換成資料庫查詢
    stocks = [
        {"code": "2330", "name": "台積電", "price": 835.5, "change": +5.0},
        {"code": "2317", "name": "鴻海",   "price": 150.0, "change": -1.5},
        {"code": "2603", "name": "長榮",   "price": 180.0, "change": +2.3},
    ]

    context = {
        "stocks": stocks,
    }
    return render(request, "core/index.html", context)