#!/usr/bin/env bash
cd "$(dirname "$0")"

while true; do
  clear
  echo "High-Risk Paper Trader"
  echo
  echo "1) Start"
  echo "2) Stop"
  echo "3) Status"
  echo "4) Restart"
  echo "5) Open Dashboard"
  echo "6) Logs"
  echo "7) Exit"
  echo
  read -r -p "Choose: " choice

  case "$choice" in
    1) ./scripts/tradectl.sh start ;;
    2) ./scripts/tradectl.sh stop ;;
    3) ./scripts/tradectl.sh status ;;
    4) ./scripts/tradectl.sh restart ;;
    5) ./scripts/tradectl.sh open ;;
    6) ./scripts/tradectl.sh logs ;;
    7) exit 0 ;;
    *) echo "Unknown choice." ;;
  esac

  echo
  read -r -p "Press Enter to continue..."
done

