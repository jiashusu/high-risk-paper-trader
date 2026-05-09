"use client";

import { useEffect, useRef } from "react";
import { CandlestickData, createChart, IChartApi, Time } from "lightweight-charts";
import type { Candle, Trade } from "@/lib/api";

type Props = {
  candles: Candle[];
  trades: Trade[];
};

export function MarketChart({ candles, trades }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!containerRef.current || candles.length === 0) return;

    let chart: IChartApi | null = createChart(containerRef.current, {
      autoSize: true,
      layout: { background: { color: "#1b1f23" }, textColor: "#aab2ad" },
      grid: { vertLines: { color: "#293036" }, horzLines: { color: "#293036" } },
      rightPriceScale: { borderColor: "#343c42" },
      timeScale: { borderColor: "#343c42", timeVisible: true },
      crosshair: { mode: 1 },
    });

    const series = chart.addCandlestickSeries({
      upColor: "#48d597",
      downColor: "#ff6b66",
      borderUpColor: "#48d597",
      borderDownColor: "#ff6b66",
      wickUpColor: "#48d597",
      wickDownColor: "#ff6b66",
    });

    const candleData: CandlestickData[] = candles.map((item) => ({
      time: Math.floor(new Date(item.timestamp).getTime() / 1000) as Time,
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close,
    }));
    series.setData(candleData);
    series.setMarkers(
      trades.map((trade) => ({
        time: Math.floor(new Date(trade.timestamp).getTime() / 1000) as Time,
        position: trade.side === "buy" ? "belowBar" : "aboveBar",
        color: trade.side === "buy" ? "#48d597" : "#ff6b66",
        shape: trade.side === "buy" ? "arrowUp" : "arrowDown",
        text: `${trade.side.toUpperCase()} ${trade.symbol}`,
      })),
    );
    chart.timeScale().fitContent();

    return () => {
      chart?.remove();
      chart = null;
    };
  }, [candles, trades]);

  return <div ref={containerRef} className="chart-wrap" aria-label="Candlestick chart with paper trade markers" />;
}

