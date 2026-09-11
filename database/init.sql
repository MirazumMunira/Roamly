CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email VARCHAR(255) UNIQUE NOT NULL,
  display_name VARCHAR(120),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS places (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_place_id VARCHAR(255) UNIQUE NOT NULL,
  name VARCHAR(255) NOT NULL,
  address TEXT,
  latitude DOUBLE PRECISION NOT NULL,
  longitude DOUBLE PRECISION NOT NULL,
  rating NUMERIC(2,1),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_preferences (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  preferred_categories JSONB NOT NULL DEFAULT '[]'::jsonb,
  preferred_transport_mode VARCHAR(32) NOT NULL DEFAULT 'DRIVE',
  situation_defaults JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reality_reports (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  place_id VARCHAR(255),
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  category VARCHAR(40) NOT NULL CHECK (category IN ('accessibility', 'entrance', 'elevator', 'facility', 'road_closure', 'flooding', 'sidewalk', 'construction', 'temporary_closure', 'parking', 'public_facility', 'traffic_light', 'crowding', 'local_problem')),
  content TEXT NOT NULL,
  source_kind VARCHAR(24) NOT NULL DEFAULT 'user_report' CHECK (source_kind IN ('user_report', 'official', 'partner')),
  reported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ NOT NULL,
  confidence NUMERIC(3,2) NOT NULL DEFAULT 0.50 CHECK (confidence >= 0 AND confidence <= 1),
  base_confidence NUMERIC(3,2) NOT NULL DEFAULT 0.50 CHECK (base_confidence >= 0 AND base_confidence <= 1),
  verification_count INTEGER NOT NULL DEFAULT 0,
  status VARCHAR(16) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'resolved', 'rejected')),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  embedding VECTOR(1536) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reality_report_verifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  report_id UUID NOT NULL REFERENCES reality_reports(id) ON DELETE CASCADE,
  verifier_id UUID,
  verdict VARCHAR(16) NOT NULL CHECK (verdict IN ('confirm', 'dispute')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (report_id, verifier_id)
);

CREATE TABLE IF NOT EXISTS place_features (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  place_id VARCHAR(255) NOT NULL,
  feature_type VARCHAR(48) NOT NULL CHECK (feature_type IN ('department', 'emergency_entrance', 'entrance', 'elevator', 'gate', 'internal_navigation', 'bus_route', 'accessible_stop', 'lighting', 'activity_level', 'hazard', 'accessible_parking', 'parking_restriction', 'parking_availability', 'rest_seating', 'quiet_area', 'wifi', 'charging', 'changing_room', 'washroom', 'accessible_entrance')),
  details TEXT NOT NULL,
  source_kind VARCHAR(24) NOT NULL DEFAULT 'partner' CHECK (source_kind IN ('official', 'partner', 'community')),
  confidence NUMERIC(3,2) NOT NULL DEFAULT .50 CHECK (confidence >= 0 AND confidence <= 1),
  observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS place_features_active_idx ON place_features (place_id, feature_type, observed_at DESC);

CREATE INDEX IF NOT EXISTS reality_reports_place_active_idx ON reality_reports (place_id, reported_at DESC) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS reality_reports_embedding_idx ON reality_reports USING hnsw (embedding vector_cosine_ops);
