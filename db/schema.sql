-- WiFi-CSI 낙상 감지 시스템 DB 스키마
-- DB: csi_fall_db
-- 실행: mysql -u root -p < db/schema.sql

CREATE DATABASE IF NOT EXISTS csi_fall_db
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE csi_fall_db;

-- ── 수집 세션 ────────────────────────────────────────────────────────────────
-- 한 번의 수집 단위 (label, 거리, 방향 등 메타 정보)
CREATE TABLE IF NOT EXISTS sessions (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    label        VARCHAR(50)  NOT NULL,          -- fall_forward, walk, static, ...
    collected_at DATETIME     NOT NULL DEFAULT NOW(),
    distance_m   FLOAT,                          -- 측정 거리 (m)
    direction    VARCHAR(20),                    -- front / side / back
    note         VARCHAR(255)                    -- 자유 메모
) ENGINE=InnoDB;

-- ── CSI 샘플 ─────────────────────────────────────────────────────────────────
-- 서브캐리어 진폭 시계열 (BLOB으로 numpy array 직렬화 저장)
CREATE TABLE IF NOT EXISTS csi_samples (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    session_id     INT     NOT NULL,
    timestamp      DOUBLE  NOT NULL,             -- UNIX 타임스탬프 (초, 소수점 포함)
    subcarrier_data MEDIUMBLOB NOT NULL,          -- numpy float32 array → tobytes()
    n_subcarriers  SMALLINT NOT NULL DEFAULT 256, -- 서브캐리어 수
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    INDEX idx_csi_session (session_id),
    INDEX idx_csi_ts      (timestamp)
) ENGINE=InnoDB;

-- ── 마이크 샘플 ──────────────────────────────────────────────────────────────
-- 오디오 진폭 시계열 (충격음 감지용)
CREATE TABLE IF NOT EXISTS mic_samples (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT    NOT NULL,
    timestamp  DOUBLE NOT NULL,                  -- UNIX 타임스탬프 (초, 소수점 포함)
    amplitude  FLOAT  NOT NULL,                  -- RMS 진폭 (0.0 ~ 1.0)
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    INDEX idx_mic_session (session_id),
    INDEX idx_mic_ts      (timestamp)
) ENGINE=InnoDB;

-- ── 낙상 이벤트 (실시간 감지 결과) ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fall_events (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    detected_at     DATETIME NOT NULL DEFAULT NOW(),
    csi_confidence  FLOAT    NOT NULL,            -- CSI 모델 낙상 확률 (0.0~1.0)
    impact_detected TINYINT  NOT NULL DEFAULT 0,  -- 충격음 감지 여부
    confirmed       TINYINT  NOT NULL DEFAULT 0,  -- 교차검증 낙상 확정 여부
    model_version   VARCHAR(50),                  -- 사용된 모델 버전
    INDEX idx_event_time (detected_at)
) ENGINE=InnoDB;

-- ── DB 유저 생성 (필요 시 주석 해제 후 실행) ─────────────────────────────────
-- CREATE USER IF NOT EXISTS 'csi_user'@'localhost' IDENTIFIED BY 'changeme';
-- GRANT ALL PRIVILEGES ON csi_fall_db.* TO 'csi_user'@'localhost';
-- FLUSH PRIVILEGES;
