# Rabalata Shuttle — mobile-friendly web app starter

**Credit:** c Otsile graphics 2026

This is a deployable Flask web application foundation, designed to be operated from a phone browser and deployed through GitHub + Render. It includes email OTP verification, customer/driver accounts, driver vehicle registration with car photo and selfie uploads, ride requests, price offers/counter-offers, driver availability/location endpoint, and a map UI.

## Important: what is and is not live
- Email verification sends real email only after you configure a real SMTP sender in Render.
- Driver documents are collected, but **admin review/approval is still manual**. Do not accept drivers until you verify licence, professional driving permit (where required), insurance, vehicle documents, and identity.
- The map uses OpenStreetMap tiles with Leaflet. Browser GPS works only with permission over HTTPS. Driver location is refreshed while the driver dashboard is open; this is not a native background tracking app.
- Card payment and automated bank payouts are **not activated**. A real provider account, API keys, verified webhooks, KYC, settlement rules and payout API are required. This project deliberately does not fake card payments or claim funds have reached a driver's balance.
- The vehicle photo upload is **not an automatic number-plate scanner**. Driver enters plate, brand/model and colour and uploads images. OCR/plate validation needs a separate service and human review; a photo alone cannot verify ownership.
- This initial version has no production admin portal, SMS/phone OTP, native app background GPS, or fully automated payout flow. Complete those before accepting public rides or money.

## Run locally
1. Install Python 3.11+.
2. `python -m venv .venv`
3. Activate it, then `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and set environment variables (export them in your shell; this app does not load `.env` automatically).
5. `python app.py`
6. Open `http://127.0.0.1:5000`

## Deploy from a phone with GitHub and Render
1. Extract this ZIP on your phone or computer.
2. Create a GitHub repository named `rabalata-shuttle`; upload the files and folders from this ZIP.
3. In Render, choose **New + → Blueprint**, connect GitHub, and select this repository. Render reads `render.yaml`.
4. In Render environment settings, set `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USERNAME`, `MAIL_PASSWORD`, and `MAIL_DEFAULT_SENDER` to a real SMTP email service. Use an email provider's app password/API SMTP credentials, not your everyday email password.
5. Wait for deployment, open the `https://...onrender.com` address, and test registration + email verification.
6. Configure a custom domain and production monitoring before launch.

## Security and launch checklist
- Set a unique secret key and configure HTTPS.
- Configure a persistent PostgreSQL database and private object storage for driver images; `/tmp` uploads can disappear on restarts.
- Add rate limiting, CSRF protection, audit logs, account recovery, consent/privacy notices, data retention and deletion.
- Restrict uploaded file sizes/types and malware scan uploads.
- Implement admin approval and review for all drivers and vehicles.
- Integrate a South Africa-supported payment gateway with signed webhook verification and its official payout product; never trust a browser callback for payment confirmation.
- Store bank details only through the provider's secure onboarding/tokenization, not in this app.
- Get legal, tax, consumer-protection, POPIA and transport compliance advice before public launch.

## Routes
- `/` home
- `/register`, `/verify`, `/login`, `/logout`
- `/book` request a ride
- `/driver/register` vehicle + selfie registration
- `/driver/dashboard` driver requests and offers
- `/ride/<id>` ride details and offers
- `/health` deployment health check
