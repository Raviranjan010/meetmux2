# Dataset contract

SkyFlow runs immediately with a deterministic synthetic training set, so no dataset is required for the hackathon demo.

For a real deployment, use historical A-CDM / ADS-B records with: `scheduled`, `actual_taxi_minutes`, `weather`, `congestion`, `inbound_delay`, `peak_bank`, and `aircraft`. Aim for 5,000+ completed movements; exclude passenger PII. NOAA/METAR weather and OpenSky movement data are suitable enrichment sources, subject to their terms.
