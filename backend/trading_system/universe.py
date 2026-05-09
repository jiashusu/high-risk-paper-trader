from .models import Asset, AssetClass


DEFAULT_UNIVERSE: list[Asset] = [
    Asset(symbol="BTC-USD", display_name="Bitcoin", asset_class=AssetClass.CRYPTO, liquidity_score=1.0),
    Asset(symbol="ETH-USD", display_name="Ethereum", asset_class=AssetClass.CRYPTO, liquidity_score=0.98),
    Asset(symbol="SOL-USD", display_name="Solana", asset_class=AssetClass.CRYPTO, liquidity_score=0.92),
    Asset(symbol="NVDA", display_name="NVIDIA", asset_class=AssetClass.EQUITY, liquidity_score=0.96),
    Asset(symbol="TSLA", display_name="Tesla", asset_class=AssetClass.EQUITY, liquidity_score=0.92),
    Asset(symbol="QQQ", display_name="Nasdaq 100 ETF", asset_class=AssetClass.ETF, liquidity_score=0.97),
    Asset(symbol="TQQQ", display_name="3x Nasdaq ETF", asset_class=AssetClass.ETF, liquidity_score=0.9),
    Asset(symbol="SPY", display_name="S&P 500 ETF", asset_class=AssetClass.ETF, liquidity_score=1.0),
]

