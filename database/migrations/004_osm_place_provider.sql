-- Run once for an existing database created before the OpenStreetMap migration.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'places' AND column_name = 'google_place_id') THEN
    ALTER TABLE places RENAME COLUMN google_place_id TO provider_place_id;
  END IF;
END $$;
