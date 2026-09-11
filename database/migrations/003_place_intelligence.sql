CREATE TABLE IF NOT EXISTS place_features (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(), place_id VARCHAR(255) NOT NULL,
  feature_type VARCHAR(48) NOT NULL CHECK (feature_type IN ('department', 'emergency_entrance', 'entrance', 'elevator', 'gate', 'internal_navigation', 'bus_route', 'accessible_stop', 'lighting', 'activity_level', 'hazard', 'accessible_parking', 'parking_restriction', 'parking_availability', 'rest_seating', 'quiet_area', 'wifi', 'charging', 'changing_room', 'washroom', 'accessible_entrance')),
  details TEXT NOT NULL, source_kind VARCHAR(24) NOT NULL DEFAULT 'partner' CHECK (source_kind IN ('official', 'partner', 'community')),
  confidence NUMERIC(3,2) NOT NULL DEFAULT .50 CHECK (confidence >= 0 AND confidence <= 1), observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), expires_at TIMESTAMPTZ, metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS place_features_active_idx ON place_features (place_id, feature_type, observed_at DESC);
