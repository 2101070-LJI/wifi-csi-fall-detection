#!/usr/bin/env bash
# install_nexmon.sh
# Nexmon CSI 설치 스크립트 — BCM4345C0 (BCM43455C0), Raspberry Pi 4
# 실행 전: sudo apt install -y git (이더넷 연결 필수, WiFi 비활성화됨)
# 실행 방법: sudo bash install_nexmon.sh

set -euo pipefail

### ── 색상 출력 ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

### ── 루트 권한 확인 ────────────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || error "루트 권한이 필요합니다. sudo bash $0 으로 실행하세요."

### ── 변수 ───────────────────────────────────────────────────────────────────
NEXMON_DIR="/opt/nexmon"
CHIP="bcm43455c0"
FW_VER="7_45_189"
# nexmon_csi는 nexmon의 patches 디렉토리 하위에 위치해야 함
NEXMON_CSI_DIR="${NEXMON_DIR}/patches/${CHIP}/${FW_VER}/nexmon_csi"
KERNEL_VER="$(uname -r)"
INSTALL_LOG="/var/log/nexmon_install.log"

info "=== Nexmon CSI 설치 시작 (칩: ${CHIP}, 커널: ${KERNEL_VER}) ==="
exec > >(tee -a "$INSTALL_LOG") 2>&1

### ── 1. 의존성 설치 ─────────────────────────────────────────────────────────
info "[1/8] 의존성 패키지 설치"
apt-get update -qq
apt-get install -y --no-install-recommends \
    git gawk qpdf bison flex libfl-dev xxd make automake \
    libgmp3-dev libmpfr-dev libmpc-dev \
    libnl-3-dev libnl-genl-3-dev \
    tcpdump build-essential \
    bc libssl-dev python3 curl \
    libc6:armhf libstdc++6:armhf libgmp-dev:armhf \
    gcc-arm-linux-gnueabihf

# ── rpi-source 로 현재 커널 헤더 설치 ─────────────────────────────────────
info "[1/8] rpi-source로 커널 헤더 설치 (${KERNEL_VER})"
HEADER_PATH="/lib/modules/${KERNEL_VER}/build"
if [[ -d "$HEADER_PATH" ]]; then
    info "커널 헤더 이미 존재: ${HEADER_PATH}"
else
    curl -L https://raw.githubusercontent.com/RPi-Distro/rpi-source/master/rpi-source \
        -o /usr/local/bin/rpi-source
    chmod +x /usr/local/bin/rpi-source
    rpi-source --skip-gcc || error "rpi-source 실패 — 인터넷 연결 및 커널 버전을 확인하세요."
fi

HEADER_PATH="/lib/modules/${KERNEL_VER}/build"
if [[ ! -d "$HEADER_PATH" ]]; then
    error "커널 헤더 설치 실패: ${HEADER_PATH} 없음"
fi
info "커널 헤더 확인: ${HEADER_PATH}"

### ── 2. nexmon (base) 클론 ──────────────────────────────────────────────────
info "[2/8] nexmon 베이스 클론"
if [[ -d "$NEXMON_DIR/.git" ]]; then
    warn "이미 존재 — git pull"
    git -C "$NEXMON_DIR" pull --quiet
else
    git clone https://github.com/seemoo-lab/nexmon.git "$NEXMON_DIR" --depth 1
fi

### ── 3. nexmon_csi 클론 ─────────────────────────────────────────────────────
info "[3/8] nexmon_csi 클론 → ${NEXMON_CSI_DIR}"
mkdir -p "${NEXMON_DIR}/patches/${CHIP}/${FW_VER}"
if [[ -d "$NEXMON_CSI_DIR/.git" ]]; then
    warn "이미 존재 — git pull"
    git -C "$NEXMON_CSI_DIR" pull --quiet
else
    git clone https://github.com/seemoo-lab/nexmon_csi.git "$NEXMON_CSI_DIR" --depth 1
fi

### ── 4. nexmon 환경 변수 설정 ───────────────────────────────────────────────
info "[4/8] 환경 변수 설정"
export NEXMON_ROOT="$NEXMON_DIR"
# shellcheck disable=SC1090
source "$NEXMON_DIR/setup_env.sh"

### ── 5. nexmon ARM 크로스 컴파일러 빌드 + ucode/templateram 추출 ─────────────
info "[5/8] nexmon ARM 컴파일러 빌드 (시간이 걸릴 수 있습니다)"
make -C "$NEXMON_DIR/buildtools/gcc-arm-none-eabi-4_8-2014q1/build" -j"$(nproc)" \
    2>/dev/null || warn "ARM 컴파일러 빌드 실패 — 사전 빌드된 바이너리 사용 시도"

# 크로스 컴파일러 의존 라이브러리 libisl.so.10 빌드 (aarch64 host에서 필수)
# arm-none-eabi-gcc (armhf 바이너리)가 libisl.so.10을 요구함
ISL_LIB="/lib/arm-linux-gnueabihf/libisl.so.10"
if [[ ! -f "$ISL_LIB" ]]; then
    info "[5/8] libisl.so.10 빌드 (크로스 컴파일러 의존성)"
    ISL_SRC="$NEXMON_DIR/buildtools/isl-0.10"
    if [[ -d "$ISL_SRC" ]]; then
        # config.sub/guess가 구버전이라 aarch64 인식 못함 — 최신 버전으로 교체
        cp /usr/share/misc/config.sub "$ISL_SRC/config.sub"
        cp /usr/share/misc/config.guess "$ISL_SRC/config.guess"
        (cd "$ISL_SRC" \
            && ./configure --build=aarch64-linux-gnu --host=arm-linux-gnueabihf \
               CC=arm-linux-gnueabihf-gcc \
               CFLAGS="-I/usr/arm-linux-gnueabihf/include" \
               LDFLAGS="-L/usr/arm-linux-gnueabihf/lib" \
            && make -j"$(nproc)" \
            && make install \
            && ln -sf /usr/local/lib/libisl.so "$ISL_LIB" \
            && ldconfig \
            && info "libisl.so.10 설치 완료") \
            || warn "libisl.so.10 빌드 실패"
    else
        warn "isl-0.10 소스 없음: ${ISL_SRC}"
    fi

# libmpfr.so.4 빌드 (arm-none-eabi-gcc cc1 의존성)
MPFR_LIB="/lib/arm-linux-gnueabihf/libmpfr.so.4"
if [[ ! -f "$MPFR_LIB" ]]; then
    info "[5/8] libmpfr.so.4 빌드 (크로스 컴파일러 의존성)"
    MPFR_SRC="$NEXMON_DIR/buildtools/mpfr-3.1.4"
    if [[ -d "$MPFR_SRC" ]]; then
        cp /usr/share/misc/config.sub "$MPFR_SRC/config.sub"
        cp /usr/share/misc/config.guess "$MPFR_SRC/config.guess"
        make -C "$MPFR_SRC" distclean 2>/dev/null || true
        (cd "$MPFR_SRC" \
            && ./configure --build=aarch64-linux-gnu --host=arm-linux-gnueabihf \
               CC=arm-linux-gnueabihf-gcc \
               CFLAGS="-I/usr/arm-linux-gnueabihf/include" \
               LDFLAGS="-L/usr/arm-linux-gnueabihf/lib" \
               --with-gmp=/usr/arm-linux-gnueabihf \
            && make -C src -j"$(nproc)" \
            && make -C src install \
            && ln -sf /usr/local/lib/libmpfr.so "$MPFR_LIB" \
            && ldconfig \
            && info "libmpfr.so.4 설치 완료") \
            || warn "libmpfr.so.4 빌드 실패"
    else
        warn "mpfr-3.1.4 소스 없음: ${MPFR_SRC}"
    fi
else
    info "libmpfr.so.4 이미 존재: ${MPFR_LIB}"
fi

# b43-v3 Python 스크립트 Python 3 호환으로 변환 (Debian Trixie에는 python2 없음)
info "[5/8] b43-v3 Python 스크립트 Python 3 변환"
python3 - <<'PYEOF'
import re, os

for fname in [
    '/opt/nexmon/buildtools/b43-v3/debug/libb43.py',
    '/opt/nexmon/buildtools/b43-v3/debug/b43-beautifier',
]:
    if not os.path.exists(fname):
        continue
    with open(fname, 'r') as f:
        content = f.read()
    orig = content
    # except X, e: -> except X as e:
    content = re.sub(r'except\s+(\w+)\s*,\s*(\w+)\s*:', r'except \1 as \2:', content)
    # print "..." -> print("...")
    content = re.sub(r'^(\s*)print\s+(.*?)$', lambda m: m.group(1) + 'print(' + m.group(2).rstrip() + ')', content, flags=re.MULTILINE)
    # file(...) -> open(...)
    content = content.replace('file(', 'open(')
    # shebang
    content = content.replace('#!/usr/bin/env python\n', '#!/usr/bin/env python3\n')
    if content != orig:
        with open(fname, 'w') as f:
            f.write(content)
        print(f'  Python 3 변환 완료: {fname}')
    else:
        print(f'  이미 변환됨: {fname}')
PYEOF
else
    info "libisl.so.10 이미 존재: ${ISL_LIB}"
fi

# ucode, templateram, flashpatch 추출 (펌웨어 빌드에 필수)
# -k: 다른 칩 빌드 실패 무시하고 계속 진행
info "[5/8] nexmon ucode/templateram 추출"
make -C "$NEXMON_DIR" -k -j"$(nproc)" || warn "일부 칩 추출 실패 (무시) — 타겟 칩(${CHIP}) 추출 여부 확인"
[[ -f "${NEXMON_DIR}/firmwares/${CHIP}/${FW_VER}/definitions.mk" ]] \
    || error "${CHIP}/${FW_VER} 펌웨어 추출 실패 — definitions.mk 없음"
info "${CHIP}/${FW_VER} 펌웨어 추출 확인 완료"

### ── 6. nexmon_csi 펌웨어 패치 빌드 ─────────────────────────────────────────
info "[6/8] CSI 패치 펌웨어 빌드 (${CHIP}/${FW_VER})"
if [[ ! -d "$NEXMON_CSI_DIR" ]]; then
    error "nexmon_csi 디렉토리 없음: ${NEXMON_CSI_DIR}"
fi

# 커널 6.x: Makefile.rpi 사용 (cyfmac43455-sdio.bin 경로 + update-alternatives 처리)
# 커널 4.19/5.4/5.10: Makefile 사용
if [[ -f "${NEXMON_CSI_DIR}/Makefile.rpi" ]]; then
    # ucode asm 파일에 cond.inc include 추가 (b43-asm이 COND_RX_IFS2 등 매크로 인식 불가)
    COND_INC="${NEXMON_DIR}/buildtools/b43-v3/debug/include/cond.inc"
    CSI_ASM="${NEXMON_CSI_DIR}/src/csi.ucode.${CHIP}.${FW_VER}.asm"
    if [[ -f "$COND_INC" && -f "$CSI_ASM" ]] && ! grep -q "cond.inc" "$CSI_ASM"; then
        sed -i "s|%arch 15|#include \"${COND_INC}\"\n%arch 15|" "$CSI_ASM"
    fi
    # init 먼저 실행 — obj/gen/log 디렉토리 생성 및 nexmon.pre 생성
    make -C "$NEXMON_CSI_DIR" -f Makefile.rpi init
    # Makefile.rpi는 tmp 임시파일을 공유하므로 병렬 빌드 불가 (단일 스레드)
    make -C "$NEXMON_CSI_DIR" -f Makefile.rpi
else
    make -C "$NEXMON_CSI_DIR" init
    make -C "$NEXMON_CSI_DIR"
fi

### ── 7. 패치된 펌웨어 설치 ──────────────────────────────────────────────────
info "[7/8] 패치된 펌웨어 설치"
# Makefile.rpi의 install-firmware 타겟이 update-alternatives로 cyfmac43455-sdio.bin 처리
if [[ -f "${NEXMON_CSI_DIR}/Makefile.rpi" ]]; then
    make -C "$NEXMON_CSI_DIR" -f Makefile.rpi install-firmware
    info "패치된 펌웨어 설치 완료 (cyfmac43455-sdio.bin via update-alternatives)"
else
    # 구버전 커널 fallback: 직접 복사
    FW_DEST="/lib/firmware/brcm/brcmfmac43455-sdio.bin"
    PATCHED_FW="${NEXMON_CSI_DIR}/brcmfmac43455-sdio.bin"
    [[ -f "$FW_DEST" ]] && cp "$FW_DEST" "${FW_DEST}.bak.$(date +%Y%m%d%H%M%S)" && info "원본 펌웨어 백업 완료"
    [[ -f "$PATCHED_FW" ]] || error "패치된 펌웨어 파일을 찾을 수 없습니다: ${PATCHED_FW}"
    cp "$PATCHED_FW" "$FW_DEST"
    info "패치된 펌웨어 설치 완료 (brcmfmac43455-sdio.bin)"
fi

### ── 8. nexutil 빌드 및 설치 ────────────────────────────────────────────────
info "[8/8] nexutil 빌드 및 설치"
make -C "${NEXMON_DIR}/utilities/nexutil" -j"$(nproc)"
make -C "${NEXMON_DIR}/utilities/nexutil" install

### ── 모니터 모드 설정 스크립트 생성 ──────────────────────────────────────────
info "모니터 모드 설정 스크립트 생성: /usr/local/bin/csi_start.sh"
cat > /usr/local/bin/csi_start.sh << 'EOF'
#!/usr/bin/env bash
# CSI 수집 시작 (모니터 모드 전환)
set -euo pipefail

IFACE="${1:-wlan0}"
CHANNEL="${2:-6}"
BW="${3:-80}"

ip link set "$IFACE" down
iw dev "$IFACE" set type monitor
ip link set "$IFACE" up
iw dev "$IFACE" set channel "$CHANNEL" "${BW}MHz" 2>/dev/null \
    || iw dev "$IFACE" set channel "$CHANNEL"

# Nexmon CSI 활성화 (모든 서브캐리어)
nexutil -Iwlan0 -s500 -b -l34 \
    -v$(printf '%b' '\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00') \
    2>/dev/null || true

# makecsiparams가 있으면 활용
if command -v makecsiparams &>/dev/null; then
    PARAMS="$(makecsiparams -c "${CHANNEL}/${BW}" -C 1 -N 1)"
    nexutil -Iwlan0 -s500 -b -l"$(echo -n "$PARAMS" | wc -c)" -v"$PARAMS"
fi

echo "[CSI] wlan0 모니터 모드 활성화, 채널 ${CHANNEL}, BW ${BW}MHz"
echo "[CSI] tcpdump로 수신: sudo tcpdump -i wlan0 dst port 5500 -vv -w /tmp/csi.pcap"
EOF
chmod +x /usr/local/bin/csi_start.sh

cat > /usr/local/bin/csi_stop.sh << 'EOF'
#!/usr/bin/env bash
# CSI 수집 중지 (매니지드 모드 복구)
ip link set wlan0 down
iw dev wlan0 set type managed
ip link set wlan0 up
echo "[CSI] wlan0 managed 모드 복구"
EOF
chmod +x /usr/local/bin/csi_stop.sh

### ── 완료 ───────────────────────────────────────────────────────────────────
echo ""
info "=== Nexmon CSI 설치 완료 ==="
echo ""
echo "  재부팅 후 패치된 펌웨어가 로드됩니다."
echo ""
echo "  [검증 방법]"
echo "  1. sudo reboot"
echo "  2. sudo bash /usr/local/bin/csi_start.sh"
echo "  3. sudo tcpdump -i wlan0 dst port 5500 -vv"
echo ""
echo "  로그: ${INSTALL_LOG}"
