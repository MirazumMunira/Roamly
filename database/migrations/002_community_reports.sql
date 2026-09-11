ALTER TABLE reality_reports ADD COLUMN IF NOT EXISTS verification_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE reality_reports ADD COLUMN IF NOT EXISTS base_confidence NUMERIC(3,2);
UPDATE reality_reports SET base_confidence = confidence WHERE base_confidence IS NULL;
ALTER TABLE reality_reports ALTER COLUMN base_confidence SET DEFAULT 0.50;
ALTER TABLE reality_reports ALTER COLUMN base_confidence SET NOT NULL;
ALTER TABLE reality_reports DROP CONSTRAINT IF EXISTS reality_reports_category_check;
ALTER TABLE reality_reports ADD CONSTRAINT reality_reports_category_check CHECK (category IN ('accessibility', 'entrance', 'elevator', 'facility', 'road_closure', 'flooding', 'sidewalk', 'construction', 'temporary_closure', 'parking', 'public_facility', 'traffic_light', 'crowding', 'local_problem'));
CREATE TABLE IF NOT EXISTS reality_report_verifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(), report_id UUID NOT NULL REFERENCES reality_reports(id) ON DELETE CASCADE,
  verifier_id UUID, verdict VARCHAR(16) NOT NULL CHECK (verdict IN ('confirm', 'dispute')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE (report_id, verifier_id)
);
