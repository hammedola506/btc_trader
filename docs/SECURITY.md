# Security Policy & Roadmap

## Implemented Security Controls (BUG-04)

- **HTTP Basic Authentication**: Enforced across all dashboard and control API endpoints (`/`, `/api/status`, `/api/stats`, `/api/journal`, `/api/start`, `/api/stop`, `/api/style`, `/api/auto-trade`, `/api/backtest/*`).
- **Fail-Fast Startup Validation**: The application refuses to start if `DASHBOARD_AUTH_ENABLED` is `True` but credentials (`DASHBOARD_USERNAME` or `DASHBOARD_PASSWORD`) are missing or empty.
- **Constant-Time Comparison**: Credential verification uses `hmac.compare_digest` to prevent timing attacks.
- **Cache Prevention**: Authenticated responses return `Cache-Control: no-store, no-cache, must-revalidate, max-age=0` and `Pragma: no-cache` headers.
- **Health Check Exemption**: `/api/health` is unauthenticated for load-balancer health monitoring.

---

## Future Security Architecture Roadmap

1. **Session-based Authentication (JWT / Cookie)**:
   Migrate from HTTP Basic Auth to signed, encrypted HttpOnly session cookies or short-lived JWT tokens to prevent basic auth credentials from persisting in browser headers.

2. **TLS / HTTPS Termination**:
   Enforce HTTPS via reverse proxy (Nginx, Traefik, or GCP Cloud Run / Load Balancer) so all credentials and API traffic are encrypted in transit.

3. **CSRF Protection**:
   Integrate CSRF token validation (`Flask-WTF` / `SameSite=Strict` cookies) for all POST control endpoints (`/api/start`, `/api/stop`, `/api/auto-trade`, `/api/style`).

4. **API Rate Limiting**:
   Implement `Flask-Limiter` to enforce IP-based rate limits on login attempts and control endpoints to prevent brute-force attacks.

5. **Multi-Factor Authentication (2FA / TOTP)**:
   Add TOTP (Time-based One-Time Password) verification prior to enabling live auto-trading or modifying critical risk settings.
