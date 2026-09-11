# ROAMLY

Roamly is a starter foundation for an AI-powered city companion. This first version provides map-based place discovery, browser location, basic place details, and directions. It intentionally does not include AI reasoning, RAG, weather, reports, accessibility intelligence, or notifications.

## Project structure

```text
roamly/
├── frontend/                 # React + Vite + Tailwind client
├── backend/
│   ├── app/
│   │   ├── api/              # HTTP routes
│   │   ├── services/         # OpenStreetMap/Nominatim/OSRM integration
│   │   ├── db/               # SQLAlchemy models/session
│   │   └── core/             # Settings
│   └── requirements.txt
├── database/init.sql         # PostgreSQL schema
└── .env.example
```

## Windows 11 + VS Code setup

This project is compatible with Windows 11. Use **Node.js 20+**, **Python 3.10+**, and **PostgreSQL 15+**. In VS Code, open the `roamly` folder, then open two integrated PowerShell terminals.

1. Copy `backend/.env.example` to `backend/.env` and set database/AI values as needed. No map API key or browser map key is required.
2. Use PostgreSQL with the **pgvector** extension. The simplest Windows setup is Docker Desktop:

```powershell
docker compose up -d
```

This starts `pgvector/pgvector` and applies `database/init.sql` on its first run. Alternatively, install the pgvector extension for your local PostgreSQL instance, create a `roamly` database, then run this from the project root:

```powershell
psql -U postgres -d roamly -f .\database\init.sql
```

If `psql` is not recognized, add PostgreSQL's `bin` folder to your Windows `PATH`, or run it from the **SQL Shell (psql)** installed with PostgreSQL.
3. Start the API:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

If PowerShell prevents activation, run this once for the current terminal and activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

4. In another terminal, start the client:

```powershell
cd frontend
npm install
npm run dev
```

If your PowerShell execution policy blocks `npm.ps1`, use `npm.cmd install` and `npm.cmd run dev` instead.

Open the address shown by Vite (normally `http://localhost:5173`).

In VS Code, select the Python interpreter at `backend\.venv\Scripts\python.exe`. The provided debug profiles also let you launch the API or frontend from the Run and Debug panel.

## OpenStreetMap map stack

Roamly does not use Google Maps, Google Cloud, a Google API key, billing, or payment verification. The React map uses Leaflet with OpenStreetMap tiles. FastAPI uses Nominatim for text lookup, Overpass for nearby OpenStreetMap POIs, and OSRM for basic route geometry, distance, and ETA.

No map key is required. The default public endpoints are configured in `backend/.env` (`NOMINATIM_URL`, `OVERPASS_URL`, and `OSRM_URL`); set a meaningful `OSM_USER_AGENT` before using public instances beyond development. The frontend calls `/api` through Vite's proxy and does not directly call provider APIs.

## AI place chat

The chat box accepts natural language such as `Find somewhere to eat near me`, `I need a pharmacy and a grocery store`, or `Find somewhere open right now`. The backend sends the message to the configured provider only to extract a structured intent, then queries OpenStreetMap data for every displayed result. Ratings and opening status are unavailable unless supplied by OSM; Roamly never invents them.

Set one provider in `backend/.env`:

```env
# Works without an AI key, with basic phrase matching
AI_PROVIDER=heuristic

# Or use Gemini
AI_PROVIDER=gemini
AI_FALLBACK_PROVIDER=openrouter
GEMINI_API_KEY=your_server_only_key
GEMINI_MODEL=gemini-2.5-flash

# Or use OpenRouter
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=your_server_only_key
OPENROUTER_MODEL=openai/gpt-4o
```

Gemini and OpenRouter keys are server-only. Roamly deliberately does not let a model create factual place answers: names, addresses, ratings, locations, and opening status come only from OpenStreetMap results.

## Reality Layer and RAG

The Reality Layer stores short-lived, confidence-scored reports for places and local conditions: accessibility, entrances and elevators, facilities, closures, flooding, sidewalks, parking, and public-facility conditions. Each report has a reporting timestamp, expiry timestamp, source type, confidence, and an embedding.

`POST /api/reality/reports` creates a report and embeds its content. `POST /api/reality/places/{place_id}/answer` embeds a question, retrieves the nearest active reports through pgvector, and combines that evidence with OpenStreetMap status when available. The response always separates provider data from report evidence and marks a map-open versus recent-closure conflict.

For retrieval, configure Gemini embeddings in `backend/.env`:

```env
EMBEDDING_PROVIDER=gemini
GEMINI_API_KEY=your_server_only_key
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIMENSIONS=1536
```

The configured dimensions must remain `1536` for the included `VECTOR(1536)` schema. Gemini embeddings are stored and retrieved through PostgreSQL/pgvector; the embedding adapter remains provider-based for a future switch.

Reality reports use Gemini `RETRIEVAL_DOCUMENT` embeddings when stored; Reality questions use `RETRIEVAL_QUERY` embeddings before pgvector similarity search. Gemini embedding models support configurable output dimensions, including the 1536-dimensional schema Roamly uses. [Gemini embeddings documentation](https://ai.google.dev/gemini-api/docs/embeddings)

## Weather intelligence

Roamly retrieves current conditions and the next few hours of forecast through the Open-Meteo weather API. The dashboard displays temperature, condition, precipitation, and the near-term rain probability. No weather API key is exposed to the client.

`GET /api/weather?lat={latitude}&lng={longitude}` returns the normalized weather context. Each `POST /api/chat` request retrieves that same context before intent extraction. Rain-related requests can therefore favour indoor nearby categories, while questions such as `Is now a good time to walk?` receive weather-based guidance rather than a place search. This feature does not score, alter, or optimize routes.

## User context and situation awareness

Roamly separates **temporary trip context** from durable **saved preferences**. Temporary context is held in the browser session, appears as dashboard chips, and is passed with each `POST /api/chat` request. Statements such as `I'm with my grandmother`, `I use a wheelchair`, `I don't want stairs`, `I'm in a hurry`, or `I need somewhere to rest` are also parsed into structured signals.

Currently supported temporary signals are: `senior_companion`, `stroller`, `wheelchair`, `avoid_stairs`, `low_walking`, `in_a_hurry`, `night_travel`, and `needs_rest`. Low-walking and hurry context reduces the nearby search radius; night travel applies the current open-now filter; rest can suggest nearby cafes. Accessibility/entrance/stair information is never assumed from this context—use Reality Layer reports to verify those conditions. No route scoring is performed.

Saved preferences remain separate under `user_preferences.situation_defaults`, with `GET` and `PUT /api/users/{user_id}/preferences` endpoints. They are ready for authenticated accounts but are not automatically mixed into this anonymous session flow.

## Personalized smart routing

`POST /api/routes/smart` requests OSRM route candidates, then ranks them using a deterministic backend score—not an LLM. The score applies documented weights for duration, distance, temporary context (such as limited walking or urgency), and active Reality Layer hazards in a conservative endpoint corridor. The response returns the recommended candidate, alternatives, scoring reasons, and the condition reports considered.

The map renders the chosen candidate and the place panel lets the user select another option. OSRM may provide alternatives depending on profile and coverage; when it supplies only one candidate, Roamly presents that route transparently. Stairs and exact route accessibility are not inferred from route geometry; the explanation explicitly labels them as unverified unless supported by Reality Layer evidence.

## Community reports, verification, and alerts

Users can submit an observed temporary condition from a selected place: flooding, blocked sidewalks/entrances, construction, elevator or traffic-light faults, closed public facilities or businesses, parking pressure, and crowding. Reports include the selected place location, observed time, category, initial confidence, expiry, and source type. This implementation deliberately contains no Computer Vision or image analysis.

Other users can confirm or dispute retrieved reports with `POST /api/reality/reports/{report_id}/verify`. The report's displayed confidence is updated from verification evidence and the verification count is shown beside it. Run `database/migrations/002_community_reports.sql` once for an existing database; fresh Docker databases receive the full schema from `database/init.sql`.

While a destination is selected, the client polls `POST /api/alerts/check` once a minute for active Reality Layer reports in a conservative route/destination area and displays an alert banner. Alerts explicitly state that they are time-limited evidence, not a guarantee that a route is unsafe or safe. For a production mobile experience, replace browser polling with authenticated push subscriptions; this foundation keeps notification decisions server-side and tied to an active destination/route context.

## Final demo: more than a map

The dashboard's **Run the final demo** button runs this scenario: “I’m new here. It’s raining, I’m with my grandmother, we need food and a washroom, she can’t walk much, and I don't want stairs.” It activates the relevant temporary context, uses live weather and OpenStreetMap data to find candidates, then lets the presenter select a destination to show the deterministic route recommendation, active Reality Layer evidence, and what is verified or unverified at that place.

Place intelligence is stored as evidence in `place_features`, with source, confidence, observation time, and optional expiry. It covers hospital departments/emergency access; entrances, elevators, gates, and internal navigation; bus-route/accessibility data; lighting and activity evidence for night travel; accessible parking and restrictions; plus seating, quiet areas, Wi-Fi, charging, changing rooms, and washrooms. Use `POST /api/place-features` to ingest official, partner, or community evidence and `POST /api/places/{place_id}/intelligence` to retrieve it for a destination.

Missing place intelligence is shown as **not verified**, never treated as a negative fact. No Computer Vision, Vision AI, or image analysis is used anywhere in Roamly.
