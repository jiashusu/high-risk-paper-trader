#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_PORT="${API_PORT:-8010}"
WEB_PORT="${WEB_PORT:-3000}"
API_URL="http://127.0.0.1:${API_PORT}"
WEB_URL="http://localhost:${WEB_PORT}"
PID_DIR="${PROJECT_DIR}/.pids"
LOG_DIR="${PROJECT_DIR}/logs"
API_PID_FILE="${PID_DIR}/api.pid"
WEB_PID_FILE="${PID_DIR}/web.pid"

mkdir -p "${PID_DIR}" "${LOG_DIR}"

cd "${PROJECT_DIR}"

print_header() {
  printf "\nHigh-Risk Paper Trader\n"
  printf "Project: %s\n\n" "${PROJECT_DIR}"
}

pid_alive() {
  local pid="${1:-}"
  [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null
}

read_pid() {
  local file="$1"
  [[ -f "${file}" ]] && tr -d '[:space:]' < "${file}" || true
}

port_pid() {
  local port="$1"
  lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null | head -1 || true
}

ensure_dependencies() {
  if [[ ! -x ".venv/bin/python" ]]; then
    echo "Creating Python virtual environment..."
    python3 -m venv .venv
  fi

  if ! .venv/bin/python -c "import fastapi, uvicorn, pydantic_settings" >/dev/null 2>&1; then
    echo "Installing Python dependencies..."
    .venv/bin/python -m pip install -e ".[test]"
  fi

  if [[ ! -d "node_modules" ]]; then
    echo "Installing Node dependencies..."
    npm install
  fi
}

start_api() {
  local existing
  existing="$(port_pid "${API_PORT}")"
  if [[ -n "${existing}" ]]; then
    echo "API port ${API_PORT} is already in use by PID ${existing}."
    echo "If this is this project, status will show it. If not, choose another API_PORT."
    echo "${existing}" > "${API_PID_FILE}"
    return
  fi

  echo "Starting API on ${API_URL}..."
  nohup .venv/bin/python -m uvicorn backend.trading_system.main:app \
    --host 0.0.0.0 \
    --port "${API_PORT}" \
    > "${LOG_DIR}/api.log" 2>&1 &
  echo "$!" > "${API_PID_FILE}"
  sleep 1
  port_pid "${API_PORT}" > "${API_PID_FILE}"
}

start_web() {
  local existing
  existing="$(port_pid "${WEB_PORT}")"
  if [[ -n "${existing}" ]]; then
    echo "Web port ${WEB_PORT} is already in use by PID ${existing}."
    echo "${existing}" > "${WEB_PID_FILE}"
    return
  fi

  echo "Building dashboard for stable local start..."
  NEXT_PUBLIC_API_BASE_URL="${API_URL}" npm run build > "${LOG_DIR}/build.log" 2>&1

  echo "Starting dashboard on ${WEB_URL}..."
  NEXT_PUBLIC_API_BASE_URL="${API_URL}" nohup npm run start -- --hostname 0.0.0.0 --port "${WEB_PORT}" \
    > "${LOG_DIR}/web.log" 2>&1 &
  echo "$!" > "${WEB_PID_FILE}"
  sleep 1
  port_pid "${WEB_PORT}" > "${WEB_PID_FILE}"
}

start_all() {
  print_header
  ensure_dependencies
  start_api
  start_web
  sleep 2
  status_all
  echo
  echo "Open dashboard: ${WEB_URL}"
}

stop_one() {
  local name="$1"
  local pid_file="$2"
  local port="$3"
  local pid
  pid="$(read_pid "${pid_file}")"

  if pid_alive "${pid}"; then
    echo "Stopping ${name} PID ${pid}..."
    kill "${pid}" 2>/dev/null || true
  fi

  local port_owner
  port_owner="$(port_pid "${port}")"
  if [[ -n "${port_owner}" ]] && [[ "${port_owner}" == "${pid}" ]]; then
    sleep 1
    if pid_alive "${port_owner}"; then
      echo "Force stopping ${name} PID ${port_owner}..."
      kill -9 "${port_owner}" 2>/dev/null || true
    fi
  elif [[ -n "${port_owner}" && -n "${pid}" ]]; then
    echo "Stopping ${name} listener PID ${port_owner}..."
    kill "${port_owner}" 2>/dev/null || true
  fi

  rm -f "${pid_file}"
}

stop_all() {
  print_header
  stop_one "dashboard" "${WEB_PID_FILE}" "${WEB_PORT}"
  stop_one "API" "${API_PID_FILE}" "${API_PORT}"
  echo "Stopped this project's known services."
}

status_port() {
  local label="$1"
  local port="$2"
  local url="$3"
  local pid_file="$4"
  local expected_pid actual_pid
  expected_pid="$(read_pid "${pid_file}")"
  actual_pid="$(port_pid "${port}")"

  if [[ -n "${actual_pid}" ]]; then
    local command
    command="$(ps -p "${actual_pid}" -o command= 2>/dev/null || true)"
    if [[ -n "${expected_pid}" && "${actual_pid}" == "${expected_pid}" ]]; then
      printf "RUNNING  %-10s %s  PID %s\n" "${label}" "${url}" "${actual_pid}"
    else
      printf "BUSY     %-10s %s  PID %s\n" "${label}" "${url}" "${actual_pid}"
    fi
    printf "         %s\n" "${command}"
  else
    printf "STOPPED  %-10s %s\n" "${label}" "${url}"
  fi
}

status_all() {
  print_header
  status_port "API" "${API_PORT}" "${API_URL}" "${API_PID_FILE}"
  status_port "Dashboard" "${WEB_PORT}" "${WEB_URL}" "${WEB_PID_FILE}"
  echo
  echo "Common local development ports:"
  local common_ports
  common_ports="$(lsof -nP \
    -iTCP:3000 -iTCP:3001 -iTCP:5000 -iTCP:7000 -iTCP:8000 -iTCP:8010 -iTCP:8080 \
    -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "${common_ports}" ]]; then
    echo "${common_ports}"
  else
    echo "No common development ports are listening."
  fi
  echo
  echo "For every listening port on this Mac, run:"
  echo "  lsof -nP -iTCP -sTCP:LISTEN"
}

open_dashboard() {
  open "${WEB_URL}"
}

tail_logs() {
  print_header
  echo "API log: ${LOG_DIR}/api.log"
  echo "Build log: ${LOG_DIR}/build.log"
  echo "Web log: ${LOG_DIR}/web.log"
  echo
  tail -n 80 -f "${LOG_DIR}/api.log" "${LOG_DIR}/build.log" "${LOG_DIR}/web.log"
}

usage() {
  cat <<EOF
Usage: ./scripts/tradectl.sh <command>

Commands:
  start    Start API and dashboard in the background
  stop     Stop this project's API and dashboard
  restart  Stop, then start
  status   Show this project status and all listening localhost ports
  open     Open dashboard in the browser
  logs     Follow API and web logs

Ports:
  Dashboard: ${WEB_URL}
  API:       ${API_URL}

Override ports:
  WEB_PORT=3001 API_PORT=8011 ./scripts/tradectl.sh start
EOF
}

case "${1:-status}" in
  start) start_all ;;
  stop) stop_all ;;
  restart) stop_all; start_all ;;
  status) status_all ;;
  open) open_dashboard ;;
  logs) tail_logs ;;
  *) usage; exit 1 ;;
esac
