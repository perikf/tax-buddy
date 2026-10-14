"""Synthetic IBKR statement builders shared by the test modules."""

HDR = ("Trades,Header,DataDiscriminator,Asset Category,Currency,Symbol,Date/Time,"
       "Quantity,T. Price,C. Price,Proceeds,Comm/Fee,Basis,Realized P/L,"
       "Realized P/L %,MTM P/L,Code")
OPEN_HDR = "Open Positions,Header,DataDiscriminator,Asset Category,Currency,Symbol,Quantity,Mult"
FII_HDR = "Financial Instrument Information,Header,Asset Category,Symbol,Description,Conid,Security ID,Type"


def row(sym="AAPL", dt="2024-05-01, 10:00:00", qty="10", price="100", comm="-1",
        cat="Stocks", ccy="USD", disc="Order"):
    return (f'Trades,Data,{disc},{cat},{ccy},{sym},"{dt}",{qty},{price},99,'
            f"-1000,{comm},1000,0,0,0,O")


def open_row(sym="AAPL", qty="25", disc="Summary"):
    return f"Open Positions,Data,{disc},Stocks,USD,{sym},{qty},1"


def fii_row(sym="AAPL", description="APPLE INC", conid="265598", isin="US0378331005"):
    return f"Financial Instrument Information,Data,Stocks,{sym},{description},{conid},{isin},COMMON"


def csv_bytes(*lines, bom=True, period="", generated=""):
    head = "Statement,Header,Field Name,Field Value\nStatement,Data,BrokerName,IBKR\n"
    if period:
        head += f'Statement,Data,Period,"{period}"\n'
    if generated:
        head += f'Statement,Data,WhenGenerated,"{generated}"\n'
    return (("﻿" if bom else "") + head + "\n".join(lines) + "\n").encode()


FULL_STATEMENT = csv_bytes(
    HDR,
    row(qty="100", price="100", dt="2024-05-01, 10:00:00"),
    row(qty="-40", price="120", dt="2024-07-01, 10:00:00"),
    OPEN_HDR, open_row(qty="60"),
    FII_HDR, fii_row(),
    period="January 1, 2024 - December 31, 2024", generated="2025-01-10, 08:00:00",
)
