#!/usr/bin/env bash
# install_python_env.sh
# Python 가상환경 생성 및 의존성 설치
# 실행 방법: bash install_python_env.sh  (루트 불필요)

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENV_DIR="${PROJECT_ROOT}/venv"
REQUIREMENTS="${PROJECT_ROOT}/requirements.txt"

info "=== Python 가상환경 설치 시작 ==="
info "프로젝트 루트: ${PROJECT_ROOT}"

### ── 1. Python 버전 확인 ────────────────────────────────────────────────────
PY_VER="$(python3 --version 2>&1)"
info "Python 버전: ${PY_VER}"
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" \
    || error "Python 3.10 이상이 필요합니다."

### ── 2. 시스템 의존성 (pip 빌드에 필요) ─────────────────────────────────────
info "[1/4] 시스템 빌드 의존성 확인"
if [[ $EUID -eq 0 ]]; then
    apt-get install -y --no-install-recommends \
        python3-venv python3-pip python3-dev \
        libportaudio2 libportaudiocpp0 portaudio19-dev \
        libsndfile1 ffmpeg \
        libasound2-dev \
        gcc g++
else
    warn "루트가 아니므로 시스템 패키지 설치를 건너뜁니다."
    warn "portaudio/libsndfile 가 없으면 sounddevice/librosa 설치 실패할 수 있습니다."
    warn "필요 시: sudo apt-get install -y libportaudio2 portaudio19-dev libsndfile1 ffmpeg"
fi

### ── 3. 가상환경 생성 ───────────────────────────────────────────────────────
info "[2/4] 가상환경 생성: ${VENV_DIR}"
if [[ -d "$VENV_DIR" ]]; then
    warn "기존 venv 존재 — 재사용합니다."
else
    python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1090
source "${VENV_DIR}/bin/activate"
pip install --upgrade pip setuptools wheel --quiet

### ── 4. 의존성 설치 ─────────────────────────────────────────────────────────
info "[3/4] requirements.txt 설치"
[[ -f "$REQUIREMENTS" ]] || error "requirements.txt 없음: ${REQUIREMENTS}"

# PyTorch: RPi 4 (aarch64) — CPU 전용 버전 설치
ARCH="$(uname -m)"
if [[ "$ARCH" == "aarch64" ]]; then
    info "  aarch64 감지 — PyTorch CPU 버전 설치"
    pip install torch --index-url https://download.pytorch.org/whl/cpu --quiet
    # torch를 이미 설치했으므로 requirements.txt의 torch는 건너뜀
    grep -v '^torch' "$REQUIREMENTS" | pip install -r /dev/stdin --quiet
else
    pip install -r "$REQUIREMENTS" --quiet
fi

### ── 5. import 검증 ─────────────────────────────────────────────────────────
info "[4/4] import 검증"
FAILED=()
for pkg in fastapi uvicorn torch numpy scipy pandas sounddevice librosa apscheduler mysql.connector; do
    if python3 -c "import ${pkg//.//}; print('  OK: ${pkg}')" 2>/dev/null; then
        :
    else
        # 패키지명이 모듈명과 다른 경우 대응
        MOD="${pkg}"
        case "$pkg" in
            mysql.connector) MOD="mysql.connector" ;;
        esac
        python3 -c "import ${MOD}" 2>/dev/null \
            && echo "  OK: ${pkg}" \
            || { warn "  FAIL: ${pkg}"; FAILED+=("$pkg"); }
    fi
done

if [[ ${#FAILED[@]} -gt 0 ]]; then
    warn "설치 실패 패키지: ${FAILED[*]}"
    warn "수동으로 확인하세요: source venv/bin/activate && pip install <패키지>"
else
    info "모든 패키지 import 성공"
fi

### ── activate 스크립트 안내 ─────────────────────────────────────────────────
echo ""
info "=== Python 환경 설정 완료 ==="
echo ""
echo "  가상환경 활성화: source ${VENV_DIR}/bin/activate"
echo "  RPi.GPIO는 RPi 하드웨어에서만 정상 동작합니다."
