#!/usr/bin/env bash
# install_lamp.sh
# Apache2 + MySQL(MariaDB) + PHP 설치 및 csi_fall_db 생성
# 실행 방법: sudo bash install_lamp.sh

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

[[ $EUID -eq 0 ]] || error "루트 권한이 필요합니다. sudo bash $0 으로 실행하세요."

DB_NAME="csi_fall_db"
DB_USER="csi_user"
DB_PASS="1111"
DB_PASS_FILE="/root/.csi_db_credentials"

info "=== LAMP 스택 설치 시작 ==="

### ── 1. Apache2 설치 ────────────────────────────────────────────────────────
info "[1/5] Apache2 설치"
apt-get update -qq
apt-get install -y apache2

systemctl enable apache2
systemctl start apache2
info "Apache2 실행 중: http://localhost"

### ── 2. MariaDB 설치 ────────────────────────────────────────────────────────
info "[2/5] MariaDB 설치"
apt-get install -y mariadb-server mariadb-client

systemctl enable mariadb
systemctl start mariadb

### ── 3. PHP 설치 ────────────────────────────────────────────────────────────
info "[3/5] PHP 설치"
apt-get install -y php libapache2-mod-php php-mysql php-json php-mbstring

PHP_VER="$(php -r 'echo PHP_MAJOR_VERSION.".".PHP_MINOR_VERSION;')"
info "PHP ${PHP_VER} 설치됨"

# Apache php 모듈 활성화
a2enmod php"${PHP_VER}" 2>/dev/null || true
systemctl restart apache2

### ── 4. MySQL DB / 유저 생성 ────────────────────────────────────────────────
info "[4/5] DB 및 유저 생성 (${DB_NAME})"

mysql -u root << SQL
CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'localhost';
FLUSH PRIVILEGES;
SQL

# 자격증명 파일에 저장
cat > "$DB_PASS_FILE" << CRED
DB_NAME=${DB_NAME}
DB_USER=${DB_USER}
DB_PASS=${DB_PASS}
DB_HOST=localhost
CRED
chmod 600 "$DB_PASS_FILE"
info "DB 자격증명 저장: ${DB_PASS_FILE}"

### ── 5. Apache 리버스 프록시 모듈 활성화 ────────────────────────────────────
info "[5/5] Apache 리버스 프록시 모듈 활성화"
a2enmod proxy proxy_http proxy_wstunnel rewrite headers
systemctl restart apache2

### ── Apache 기본 동작 확인 ──────────────────────────────────────────────────
HTTP_CODE="$(curl -s -o /dev/null -w '%{http_code}' http://localhost/ || echo '000')"
if [[ "$HTTP_CODE" == "200" ]]; then
    info "Apache 정상 동작 확인 (HTTP ${HTTP_CODE})"
else
    warn "Apache 응답 코드: ${HTTP_CODE} — 수동으로 확인하세요."
fi

### ── 완료 ───────────────────────────────────────────────────────────────────
echo ""
info "=== LAMP 스택 설치 완료 ==="
echo ""
echo "  Apache:  http://localhost"
echo "  DB 이름: ${DB_NAME}"
echo "  DB 유저: ${DB_USER}"
echo "  자격증명: ${DB_PASS_FILE}"
echo ""
echo "  다음 단계: sudo mysql ${DB_NAME} < db/schema.sql"
