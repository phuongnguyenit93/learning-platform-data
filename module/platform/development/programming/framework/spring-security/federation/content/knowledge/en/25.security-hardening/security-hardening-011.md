# Preventing Leakage of Assertions, Tickets, and Tokens via URLs, Logs, or Browser Caches

In a **Spring Security federation** system, authentication data can appear in many forms: **SAML Assertion/SAMLResponse**, **CAS Service Ticket/Proxy Ticket**, **OAuth 2.0 Authorization Code**, **OIDC ID Token**, **OAuth Access Token/Refresh Token**, **session cookies**, and login-session identifiers. Their purposes differ, yet they share a common risk: **if placed into URLs, access logs, traces, response caches, browser storage, memory dumps, or third-party services, they can become a source of identity disclosure and session hijacking**.

The goal of this lesson is not “hide everything from the browser at all costs”: some protocols **require the browser to carry a short-lived artifact**. The right goal is to **minimize credential presence across easily copied surfaces, bind artifacts to the exact client/service/session, detect exposure, and remediate leaks**. Even a single-use CAS ticket must stay out of logs; an exposed OAuth authorization code gains additional protection from **PKCE**, yet PKCE must never be used as an excuse to log raw codes.

This lesson belongs to the **Security Hardening** group, explaining OIDC/OAuth2, SAML2, and CAS mechanisms and how sensitive data travels through URLs/history/Referer/logs/browser caches/Java memory. It includes Spring Security Servlet guidance, response header choices, log allowlists, a **self-compiling/runnable Java 17 demo**, a test matrix, an incident runbook, and official references.

> **One-sentence principle:** never put reusable tokens in URIs; never log raw callbacks/credentials; never cache authentication content or sensitive pages; use HTTPS, protocol bindings, short TTLs, and least privilege to limit damage if an artifact ever leaks.

## 1. Distinguishing What Needs Protection

| Data | What is it used for? | Where can it appear? | Primary risk |
| --- | --- | --- | --- |
| **OAuth Authorization Code** | Exchanged for tokens at the token endpoint | `code` query param on redirect URI; or `form_post` if supported | Someone else tries exchanging the code before the client; state/redirect flow leakage |
| **OIDC ID Token** | Proves authentication outcome to the OIDC client | Token endpoint/back-channel in Authorization Code; other flows may use front-channel | PII/claims and identity context leaked; confusing ID Token with access token |
| **OAuth Access Token** | Calling protected resources/APIs | `Authorization: Bearer`, token storage, proxy/APM | **Bearer token theft/replay**, API access within scopes |
| **Refresh Token** | Requesting new access tokens | Token endpoint/client secure storage | Long-lived exposure, extending access beyond short-lived access tokens |
| **SAMLResponse/Assertion** | Delivering authentication result from IdP to SP | HTML form `SAMLResponse`/HTTP POST to ACS; other bindings | Claims/signature exposure, replay if SP checks are incomplete |
| **SAML Artifact** | Reference to a message redeemed over back-channel | Front-channel browser depending on binding | Artifact captured and redeemed if lacking binding/one-time enforcement |
| **CAS Service Ticket (ST)** | Proving CAS login for a service URL | `ticket=ST-...` parameter in callback URL | Ticket stolen before SP validation, replay/leakage from access logs |
| **CAS Proxy Ticket/PGT** | Accessing services or calling services on a user's behalf per CAS policy | CAS back-channel and delegation-enabled apps | Out-of-scope delegation or downstream session hijacking |
| **Session cookie** | Maintaining browser session at IdP/SP | Cookie header, cookie jar, HAR, proxy logs | Session hijacking, fixation, or reuse of old sessions |
| **`state`/`nonce`/`RelayState`** | Binding requests/responses and navigation per protocol | Front-channel and state stores | Exposure or forgery of correlation, CSRF/login injection, open redirects |

**The terms “token”, “ticket”, and “assertion” are not interchangeable.** An ID Token proves authentication to an **OIDC client**; an Access Token is a credential for calling APIs; an OAuth authorization code is a short-lived credential solely for exchanging tokens; a CAS ST is bound to a service; a SAML Assertion carries authentication/attribute data for a designated SP. Protection mechanisms and lifetimes differ, yet **none of them should be written raw to logs by default**.

### Examples that must be treated as sensitive data

~~~text
OAuth callback:
  /login/oauth2/code/corp?code=CODE-EXAMPLE&state=OPAQUE-STATE

CAS callback:
  /login/cas?ticket=ST-EXAMPLE&service=https%3A%2F%2Fportal.example

OAuth API (should not use):
  /api/reports?access_token=TOKEN-EXAMPLE

OAuth API (usual bearer method):
  Authorization: Bearer TOKEN-EXAMPLE

SAML POST form field:
  SAMLResponse=<base64 XML with claims and signature>
  RelayState=<opaque correlated application state>

Session:
  Cookie: JSESSIONID=SESSION-EXAMPLE
~~~

These are **dummy values for analysis**, not usable credentials. **Never copy real callback URLs, Authorization headers, or Cookie headers into support tickets, public chats, DevTools screenshots, or unapproved AI tools.**

## 2. Through Which Paths Does Authentication Data Leak?

~~~mermaid
flowchart TD
    A[Browser / IdP / Callback] --> B[URL query / fragment / form body]
    B --> C[Reverse proxy, WAF, CDN, access logs]
    B --> D[Browser history, Referrer, bookmarks]
    B --> E[Third-party JS, images, analytics]
    A --> F[HTTP response, cookies, local browser storage]
    F --> G[Browser cache, Service Worker, backups]
    A --> H[Spring filters, exceptions, APM traces]
    H --> I[Structured logs, heap dumps, crash reports]
    C --> J[Untrusted reader / attacker]
    D --> J
    E --> J
    G --> J
    I --> J
~~~

Watch three **independent** data-holding systems:

1. **Network/server systems**: reverse proxies, ingress, WAF, API gateways, CDNs, web server access logs, APM/tracing, debug loggers, centralized logging.
2. **Browser/device**: address bar, history, Referer, clipboard, HAR exports/downloads, bfcache/HTTP cache, Web Storage, JavaScript memory, browser extensions.
3. **Application/backend**: request/response bodies, exception context, thread-local/MDC, heap dumps, trace spans, HTTP client interceptors, token stores, session persistence, and backups.

Deleting an entry from Spring logs **does not delete copies at ingress**, and `Cache-Control: no-store` **does not erase logs already written**. Defense-in-depth must cover every surface the data actually traverses.

## 3. URL Query, Browser History, and Referer

A URI like:

~~~http
GET /login/oauth2/code/corp?code=AUTH-CODE&state=OPAQUE HTTP/1.1
Host: portal.example
~~~

can end up in browser history, reverse proxy request logs, APM tags, browser sync, screenshots/address bars, or transmitted in **`Referer`** when the callback page loads resources/links. RFC 9700 (**OAuth 2.0 Security Best Current Practice**, 2025) explicitly documents both **credential leakage via Referer** and **browser history**.

**Do not misunderstand:** an authorization code in the query of an OIDC Authorization Code flow **is protocol-valid** and intentional. The goal is to minimize the code's value if exposed (one-time authorization code, short TTL, client binding/PKCE), shorten exposure time, and never write full URIs to logs.

Risks to distinguish:

- **Query strings** are sent to servers and many reverse proxies; default access logs may record the full request target.
- **URL fragments** (after `#`) are normally **not sent by HTTP user-agents to servers**, yet still reside in browser address bars/history, can be read by same-origin JavaScript, and can leak via extensions/XSS or browser-specific quirks. Never treat fragments as a secret vault.
- **Referer** can carry the source URI per browser Referrer Policy, especially same-origin; if a callback holding code/state loads a third-party tracking script, check that leakage vector.
- **`Location` redirects** can carry query params from a callback to the next URL if the app appends or forwards all request parameters.
- **Open redirects** on IdP/client can forward codes/tokens to an attacker's origin; allow only exact registered redirect URIs.
- **Secondary query parameters** like `next`, `returnUrl`, `RelayState` can be abused by attackers to force external redirects without an allowlist.

### Referrer Policy does not replace protocol validation

Appropriate response headers for authentication pages:

~~~http
Referrer-Policy: no-referrer
Cache-Control: no-store
Pragma: no-cache
Expires: 0
~~~

`no-referrer` restricts sending `Referer` on requests originating from the document. It **does not erase URLs from browser history, access logs, or third-party scripts already running on the page**. Avoid third-party subresources on callback/auto-post pages by design, even with headers set.

**Order matters:** if a callback page already loaded analytics before cleaning the URL, fixing it later with JavaScript may be too late. Configure the server-side callback to process the code and redirect to a **credential-free** application URL before rendering dashboards.

## 4. OAuth 2.0/OIDC: Protecting the Authorization Code Flow

A standard safe configuration for a web app:

~~~text
1. Browser -> Spring route protected
2. Spring -> IdP /authorize (response_type=code, state, nonce, PKCE)
3. IdP -> Spring callback ?code=...&state=...
4. Spring validates state + authorization request association
5. Spring exchanges code via HTTPS back-channel with the IdP
6. Token endpoint returns tokens to registered client
7. Spring validates OIDC ID Token (iss/aud/exp/nonce/signature)
8. Spring establishes local authenticated session
9. Browser -> clean application URL without code/state
~~~

**Code leakage controls:**

- **Authorization Code + PKCE (S256)**, even for confidential clients if supported by the stack; **never use implicit grant** to emit access tokens directly over the front-channel barring very specific justified cases evaluated under RFC 9700.
- **Exact redirect URI matching** against registered redirect URIs; never accept arbitrary callback URLs from requests.
- **Short-lived, single-use** codes, bound to client and redirect URI per OAuth server requirements.
- High-entropy random `state`, bound to request/session for CSRF defense; `nonce` for OIDC flows when required, binding ID Token to login request.
- Never place access tokens, refresh tokens, ID Tokens, PKCE `code_verifier`, or client secrets inside `state`, `nonce`, or return URLs.
- With multiple IdPs, prevent mix-up via issuer/client association and `iss` in authorization responses where available; never guess the issuer from user-selected queries.
- Never render a page with links/analytics/iframes/third-party resources while the callback still holds credentials in the address bar.
- Consider **`response_mode=form_post`** for authorization responses if IdP/client support it and response-mode/session cookies are properly configured; never blindly assume every OAuth implementation supports it.
- After token exchange/validation completes, redirect to a clean page. Never forward the raw callback query to another app or reverse proxy.

**Key distinction:** PKCE protects code exchange without `code_verifier`, **does not stop codes from being written to access logs**, and does not protect if an attacker already stole both session/PKCE verifier or has XSS on the client. Pair PKCE with URL/log controls.

### Why avoid OAuth implicit flow?

Flows delivering `access_token` via browser URL fragments raise token leak/replay risk. RFC 9700 recommends the Authorization Code flow or mechanisms that do not return access tokens in authorization responses. Browsers can save fragments in history; same-origin JavaScript can read them; extensions/XSS can steal them.

Never “fix” this by moving access tokens from the fragment to the query string. That **puts bearer credentials directly into server access logs**.

## 5. Bearer Access Tokens: Strictly Avoid Query Strings

Example **to avoid**:

~~~http
GET /api/reports?access_token=ACCESS-TOKEN HTTP/1.1
Host: api.example
~~~

RFC 6750 already noted the logging risk of URI query parameters; RFC 9700 updates the requirement more strictly: **clients MUST NOT pass access tokens in URI query parameters per RFC 6750 `2.3`**. Bearer tokens should be sent in the HTTP `Authorization` header over HTTPS:

~~~http
GET /api/reports HTTP/1.1
Host: api.example
Authorization: Bearer ACCESS-TOKEN
~~~

**Yet headers are not automatically safe:** WAFs/full request dumps, application interceptors, APM auto-instrumentation, proxy debug logs, or HAR files can still capture `Authorization`. Scrub or disable capturing sensitive headers at every collection point. Never let `Cookie`/`Set-Cookie` appear in raw logs.

Token scopes, audience, expiration, and sender-constraining limit damage upon theft:
- Validate token `iss`, `aud`, signature, `exp`, and proper scopes at the resource server.
- Prefer least privilege and short-lived access tokens.
- Use mTLS sender-constrained tokens or DPoP when supported by the stack and suited to the threat model.
- Use **refresh token rotation** or client/device binding for public clients; enforce reuse detection per IdP implementation.
- Never send an ID Token to an API as an Access Token: it has a **different audience and purpose**.

**A leaked bearer token can remain valid until expiration or revocation**, even when the API enables HTTPS and `no-store`. Maintain incident response procedures and sensible lifetimes.

## 6. SAML 2.0: POST Binding Is Not Secret Storage

In **SAML HTTP POST binding**, the IdP typically renders an HTML form with hidden fields:

~~~html
<form method="post" action="https://sp.example/saml2/acs">
  <input type="hidden" name="SAMLResponse" value="BASE64-XML-EXAMPLE">
  <input type="hidden" name="RelayState" value="OPAQUE-STATE">
  <button type="submit">Continue</button>
</form>
~~~

The browser submits the form via HTTP POST to the **Assertion Consumer Service (ACS)**. `SAMLResponse` can contain Assertions, subject identifiers, attributes, timestamps, and XML signatures. **Hidden inputs are not encrypted or secret from the browser**: DevTools, browser extensions, scripts on the IdP form page, endpoint network captures, and WAF/request-body logging can still observe them.

The OASIS SAML Technical Overview describes the auto-submit POST flow with `SAMLResponse` and `RelayState` form fields. The risk is not standard POST usage itself, but **body logging, form caching, third-party scripts, incomplete Assertion checks, and retaining sensitive content longer than needed**.

Requirements:

1. Use HTTPS and verify certificate chains/hosts on both IdP and SP.
2. Never write `SAMLResponse`, decoded Assertion XML, signed XML fragments, sensitive NameIDs, or full attributes to application logs.
3. IdP HTML auto-submit pages should set `Cache-Control: no-store`, avoid third-party scripts/analytics, and use submission-compatible CSP.
4. SP validates **issuer, signature, Destination, Recipient, InResponseTo, AudienceRestriction, Conditions/SubjectConfirmationData timestamps**, expected binding, and replay cache per profile.
5. Consume only truly needed attributes; enforce data minimization starting at the IdP.
6. After the SP processes `SAMLResponse`, redirect to a clean URL/dashboard; never echo response bodies or params into HTML/error pages.
7. Handle `RelayState` carefully: usually opaque correlation state; never create an open redirect via `Location: {RelayState}`.
8. SAML Artifact binding can shrink front-channel assertions by sending an artifact and retrieving the message over back-channel; **the artifact itself is still a valuable reference credential** needing one-time redemption, audience/binding/TLS, and no indiscriminate logging.

**A signed SAML Assertion can still hold confidential PII.** A signature guarantees integrity/origin when verified properly; **it does not mean the Assertion is encrypted**. To hide contents from browsers/intermediaries, use **SAML XML Encryption**/encrypted assertions per profile with proper SP keys; encryption does not replace signature/audience/replay checks.

## 7. CAS: Tickets in URLs Are a Protocol Reality Requiring Management

In classic CAS web SSO, after the user logs in, CAS redirects the browser to the **service URL** with a `ticket` parameter:

~~~http
HTTP/1.1 302 Found
Location: https://portal.example/login/cas?ticket=ST-FAKE-EXAMPLE
~~~

Spring Security's `CasAuthenticationFilter` per Javadoc defaults to processing URL `/login/cas`, reads the opaque service ticket from the `ticket` request parameter, and uses `CasAuthenticationProvider` and a CAS ticket validator to verify with the CAS server. The ticket must be **bound to the service URL** and treated as a single-use protocol artifact; never persist it as a long-lived password.

Risks:

- Browser history/URL holds `ST-...` during the redirect.
- Ingress/web server access logs record `/login/cas?ticket=ST-...` verbatim.
- APM loggers or error handlers log `request.getQueryString()`.
- Browser Referer sent from the ticket-holding page to another origin.
- Post-login redirects accidentally copying the ticket into `returnUrl` or HTML links.
- Ticket validation failures logging the raw ticket in exceptions/logs.
- CAS Proxy Tickets/Proxy-Granting Tickets carrying downstream privileges beyond STs, needing delegation-policy protection.

Mitigations:

1. **Never log query strings** of CAS callbacks at gateways, access logs, Spring, or tracing.
2. Configure `ServiceProperties.getService()`/callback URL to match the exact service for which the ticket was issued; reject tickets meant for other services.
3. Validate tickets over back-channel HTTPS, checking CAS server trust and TLS; one-time validation, preventing replay.
4. Once validated, redirect the browser to a **clean application URL** without `ticket`. Across Spring/CAS versions, test the real flow rather than assuming the filter strips browser history automatically in all setups.
5. Set cache/no-referrer headers on callback and error pages; never embed tokens in HTML or diagnostics.
6. Never copy tickets into session attributes/logs/URLs as “login proof”. Retain only needed identity/session state.
7. For CAS PGT/PT, add checks for delegated service, callback, receiver key, and scope; never log tokens to network dashboards.

**Important:** the CAS ticket query param is part of the protocol; you cannot simply “reject all query params” on `/login/cas` and keep classic CAS working. Protect that specific endpoint, process the ticket once, and redirect to a clean URL.

## 8. Comparison Table of Leakage Surfaces by Protocol

| Mechanism | Expected front-channel | Data to keep out of logs | Specific post-checks |
| --- | --- | --- | --- |
| OIDC Authorization Code | `code` and `state` on redirect callback (or form_post if supported) | Code/state, raw redirect URI, authorization/token responses | PKCE, exact redirect URI, state, nonce, iss/aud/signature |
| OAuth bearer API | No bearer token in URI | Authorization, cookies, access/refresh tokens, bodies | Audience, scopes, expiry, sender constraint |
| SAML2 POST | `SAMLResponse` in form body, `RelayState` | Decoded XML, base64 response, NameID, attributes | Issuer, signature, audience, recipient, timestamp, replay |
| SAML Artifact | Artifact on front-channel per binding | Artifact, SOAP exchange details | One-time artifact resolution, mutual trust/TLS |
| CAS ST | `ticket` in query | Ticket, raw request target, validation responses | Service binding, one-time validation, clean redirect |
| CAS PT/PGT | Typically back-channel/delegation contexts | Proxy/PGT tokens, sensitive callback payloads | Delegation restrictions and valid targets |
| IdP/SP session | Cookie on HTTPS requests | Cookie, Set-Cookie, server session identifiers | HttpOnly/Secure/SameSite, rotation, logout/revocation |

Do not rely on a single regex log scrubber as your sole defense everywhere. **SAMLResponse lives in POST bodies**, bearer tokens in `Authorization`, CAS STs in queries, and session IDs in `Cookie`; each source requires its own **collection-prevention policy**.

## 9. HTTP Caches, CDN/Proxy Caches, and Browser Back

Current Spring Security defaults add response headers to prevent caching sensitive content:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
~~~

Understand the differences:

- **`no-store`** instructs caches not to store the request or response; it is the strongest directive for auth callbacks, token-bearing error responses, and private pages.
- **`no-cache`** does not mean “do not store”: HTTP caches may store it and must revalidate before reuse. Thus `no-cache` alone does not replace `no-store`.
- **`private`** restricts caching to private caches, **without preventing browsers from storing it**. Never use `private` alone for highly sensitive content.
- **`max-age=0, must-revalidate`** helps enforce freshness, while `no-store` remains the primary control.
- **`Pragma: no-cache`** and `Expires: 0` support legacy compatibility; they do not replace modern `Cache-Control`.
- **`Vary: Authorization`/`Vary: Cookie`** may be needed in approved caching scenarios, yet **must not be treated as a substitute for `no-store`** on auth responses.

**Spring Security may not overwrite `Cache-Control` if the app sets response headers itself**; servlet controllers, CDNs, other frameworks, and reverse proxies can modify headers. Never assume safety merely because the security dependency is present. Inspect headers on the **actual response after all proxies**.

### Browser Back/Forward Cache (bfcache)

`no-store` curbs HTTP caching, yet you should not claim every browser version drops history snapshots/bfcache or JavaScript memory under all conditions. Browser behavior varies; sensitive pages need **properly designed per-request/restore session authorization**, not just a header assuming Back always shows a blank screen.

### Caching at CDN/ingress

Token callbacks and private pages must never become publicly cached objects. Avoid:
- CDN caching `/login/oauth2/code/*`, `/login/cas`, `/login/saml2/sso/*`.
- Reverse proxy caching 302 authentication redirects carrying credentials.
- Shared caches keyed by URL without considering session/user.
- Cache keys containing query secrets leaking into CDN analytics/control planes.
- Edge debug logs holding raw response bodies from SAML auto-post pages.

**Configure both origin and edge**: `no-store` responses, skip-store auth routes, redacted logs, and empirical testing across browsers and multiple users.

## 10. Referrer-Policy, HSTS, CSP, and Cookies

A baseline set of protections for auth pages and sensitive endpoints:

~~~http
Referrer-Policy: no-referrer
Cache-Control: no-store
Pragma: no-cache
Expires: 0
X-Content-Type-Options: nosniff
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'none'
~~~

**Do not copy the CSP above to every app untested**: if a SAML IdP requires an inline auto-submit script, an appropriate CSP `script-src`/nonce/hash is mandatory—never allow `unsafe-inline` casually. HSTS applies only over HTTPS, and `includeSubDomains` must account for all real subdomains. HSTS does not erase previously logged data.

### Session cookies

Cookies holding session identifiers should set:
- **`Secure`**: sent only over HTTPS.
- **`HttpOnly`**: JavaScript cannot read the value via `document.cookie` (does not stop XSS from calling APIs with auto-sent cookies).
- **`SameSite`** matching the real SSO flow: `Lax` usually fits top-level GET callbacks, whereas **SAML cross-site POST ACS** may need `SameSite=None; Secure` or alternative state/cookie handling; `Strict` is not a universal default for all SSO.
- Minimal Domain/Path, avoiding leaking cookies across unrelated subdomains; consider the **`__Host-`** prefix when Secure, `Path=/`, and no Domain apply.
- Proper session fixation protection, session rotation, timeouts, and logout/invalidation.

**HttpOnly does not equal CSRF defense and does not stop requests from automatically attaching cookies.** Analyze CSRF, same-site/cross-site callbacks, logout, and cookie sessions concretely. Never place session IDs in URLs (URL rewriting like `;jsessionid=...`) when secure cookies work; in Spring/Servlet containers, disable URL-based session tracking if unneeded.

## 11. localStorage, sessionStorage, IndexedDB, and Service Workers

Browser storage APIs differ:

| Storage | Readable by browser JS? | Risk |
| --- | --- | --- |
| `localStorage` | Yes, same origin | XSS steals tokens; persists after tab closes |
| `sessionStorage` | Yes, same tab/context | XSS can still steal it; not a secret vault |
| `IndexedDB` | Yes, per origin permissions | Persistent data; accessible to Service Workers/scripts per policy |
| **HttpOnly** Cookie | JS cannot read cookie value | CSRF/same-site; XSS can still make authenticated requests |
| JS in-memory variable | Same-execution-context scripts can access per architecture | XSS or extensions can tamper; lost on reload |
| Server-side token store/BFF | Browser holds only session cookie | Reduces browser token exposure, though backend store/session still need protection |

OWASP HTML5/Session Management guidance recommends **never storing authentication tokens, refresh tokens, or session IDs in Web Storage** because same-origin XSS can read them. `sessionStorage` is not a “safe version” of `localStorage`.

For **Spring MVC web applications** using Authorization Code flow, prefer server-side session/token management where architecturally appropriate. For SPAs/browser-based clients, evaluate **Backend-for-Frontend (BFF)**, PKCE, CSP, Trusted Types, dependency security, and token lifecycles; never send long-lived refresh tokens to JS runtimes just because a library supports it.

### Service Worker/Cache API

Service Workers can intercept requests and Cache API can store responses if the app explicitly codes it. HTTP `Cache-Control: no-store` **does not replace reviewing Service Worker Cache API logic**; never cache login callbacks or APIs carrying PII/tokens. On logout, implement appropriate client-side cleanup, while recognizing you **cannot guarantee purging every copy in screenshots, browser history, analytics, or cloud backups**.

### Browser extensions and HAR exports

HAR files often record full request URLs, headers, cookies, and sometimes POST bodies. If a developer exports a HAR of a login callback, it may hold a CAS ticket, SAMLResponse, OAuth code/state, or Authorization header. **Never upload raw HARs to public issue trackers.** Export only in controlled environments, apply verified redaction, and enforce tight access controls and short retention.

## 12. Logs and APM: Beyond Spring's application.log

Layers prone to accidentally logging credentials:

| Layer | Where secrets appear | Required change |
| --- | --- | --- |
| Nginx/Apache/ingress | `$request`, `$request_uri` including query | Use path-only, log route/method/status; strip queries on auth routes |
| Load balancer/CDN | Request URI, headers, cache keys, debug dumps | Route exclusions, field redaction, short retention |
| WAF | Request/response body capture, anomaly samples | Never log raw `SAMLResponse`, Authorization, Cookie |
| Spring MVC | `getRequestURL()` + `getQueryString()`, parameter dumps | Log canonical route/endpoint ID and outcome |
| Spring Security | DEBUG/TRACE, exception details | Enable only briefly; never log credentials/tokens |
| HTTP clients | Token requests/responses from RestClient/WebClient | Mask Authorization, client_secret, refresh_token, tokens |
| APM/tracing | HTTP `url.full`, span attributes, baggage, custom tags | Omit query/headers/body; scrub before export |
| Centralized logging/SIEM | Raw logs from multiple tiers | Ingestion rules, encryption, access control, retention |
| Error reporters | Exception local variables, request bodies, breadcrumbs | Disable sensitive captures, audit PII scrubbing |
| Heap/thread dumps | Access/refresh tokens, Assertion XML, cookies | Restrict dump access; avoid attaching to tickets |

**Warning:** regex redaction running **after** full tokens were already shipped to an exporter can be too late. Prefer **not collecting sensitive fields at the source** (data minimization) and using an **allowlist** of fields permitted to be logged.

### Safer field list for auditing

~~~text
time=2026-11-07T03:00:00Z
event=AUTH_CALLBACK
protocol=OIDC
endpoint=oidc_callback
method=GET
result=SUCCESS
duration_ms=47
correlation_id=nonsecret-random-id
provider_key=corp_idp
principal_link_id=approved-internal-id (if genuinely needed and permitted)
~~~

Do not log:

~~~text
?code=...&state=...
?ticket=...
SAMLResponse=...
Authorization: Bearer ...
Cookie: JSESSIONID=...
Set-Cookie: ...
refresh_token=...
client_secret=...
full ID Token/JWT, NameID/Assertion XML, password
~~~

**`correlation_id`** must be a dedicated random identifier for audit/tracing—never reuse a bearer credential or write `state`/tickets into it. When investigations need to distinguish tokens, use a **non-authenticating reference ID** with bounded retention and access controls, rather than raw tokens or unkeyed hashes of low-entropy tokens.

## 13. Allowlist-Based Logging Rules Instead of Regex Catch-Alls

**Anti-pattern:**

~~~java
// DO NOT do this in a Spring filter/controller:
log.info("auth callback uri={}", request.getRequestURI()
        + "?" + request.getQueryString());
log.debug("SAMLResponse={}", request.getParameter("SAMLResponse"));
log.info("Authorization={}", request.getHeader("Authorization"));
log.error("authentication failed, request={}", request);
~~~

Some APIs/`toString()` methods include sensitive data. Log messages carrying codes/tickets can be copied into APM exception events even if the app does not persist them separately.

**Safer principle:**

~~~text
input: HTTP request with untrusted URL/headers/body
derive:
  route identifier from a FIXED set of known callback routes
  method from fixed allowlist
  high-level result code
  duration
  independent correlation ID
discard for logging:
  full request-target, query, fragments, POST parameters
  Authorization/Cookie/Set-Cookie, token responses
  SAML XML/NameID, exception parameter dumps
output:
  structured audit event with only approved fields
~~~

Never log **full raw paths** if paths can carry bearer tokens, user IDs/PII, or traversal payloads; use a **route template/registered endpoint key**. Never pass `request.getParameterMap()` to structured logging, because it contains OAuth code/state, CAS tickets, and SAMLResponses.

### Loggers/frameworks to inspect

- Embedded Tomcat `AccessLogValve`, Jetty/Undertow access logs.
- Spring Boot actuator HTTP exchanges/observability tags.
- Spring Security DEBUG/TRACE, OAuth2 client/Resource Server/SAML logs.
- Spring MVC request/response logging filters and custom Servlet filters.
- WebClient/RestTemplate wire logging, Reactor Netty HTTP wiretap.
- Nginx `$request` vs `$uri`: `$request` normally contains the full request-target/query; `$uri` is normally path-only yet can still be user input requiring classification. **Do not assume swapping variables suffices** if another agent logs full URLs.
- WAF/mod_security request-body logging; SAML POST payloads can appear in bodies.
- OpenTelemetry `url.full`, `http.request.header.authorization`, baggage, exception attributes, and collectors.
- Error trackers (Sentry, Rollbar, crash dumps), CI test artifacts, load-testing captures.

**Protect the logging pipeline**: principle of least privilege, encryption at rest/transit, retention, segregated audit access, logging health alerts, and secret scanning on synthetic test flows. Never ship raw logs containing credentials to external vendors without data handling agreements and scrubbing.

## 14. Spring Security Servlet: Response Headers for Auth Endpoints

Current Spring Security versions provide default security response headers, including **`Cache-Control/Pragma/Expires`** disabling caching. You can also explicitly declare **`Referrer-Policy`** for your application:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter;

@Configuration
public class FederationSecurityHeaders {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated())
            .headers(headers -> headers
                .cacheControl(Customizer.withDefaults())
                .referrerPolicy(ref -> ref.policy(
                    ReferrerPolicyHeaderWriter
                      .ReferrerPolicy.NO_REFERRER)))
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

This is a **Spring Security Servlet configuration fragment**, requiring Spring Security OAuth2 Client/Boot dependencies and a valid ClientRegistration. It is **not** runnable directly with `javac`. API names/lambdas may differ in your Spring Security release—check docs and dependency trees; when using **SAML or CAS**, add the matching authentication chain/provider rather than copying `oauth2Login` as the whole federation config.

**Important filter chain note:** login callbacks are handled by filters before app controllers render views. Therefore headers must apply across **all response paths**, including success, failure, redirects, static auto-submit, error, exception, and any requests outside the Spring Security chain. If MVC/proxies override `Cache-Control`, test actual responses rather than assuming defaults hold.

### Response headers do not prevent logging

No `http.headers(...)` option erases raw `code`/`ticket` values from access logs already written before the request reached Spring. Configure logging separately at ingress/proxy/APM and application layers.

### What should the callback response do?

After authentication is verified:
1. Create/update the application security context per Spring mechanisms, session fixation protection, and cookie flags.
2. Issue **303 See Other** or an appropriate redirect to a **clean application URL** without code, ticket, SAMLResponse, or state.
3. Never render templates embedding the original callback URI in links, forms, scripts, history, or `<base>`.
4. Never include third-party resources on callback/error pages, restricting Referrer.
5. Never expose raw exception causes/bodies on error pages.

**Caution:** never write a pre-authentication redirect filter to strip `ticket`/`code` before Spring validates; redirecting too early discards callback data and breaks login. Rely on authentication success handlers/filters and protocol implementations.

## 15. Identifying OAuth2 Login and SAML/CAS Endpoints Accurately

Spring Security endpoints vary by version/configuration:

~~~text
OIDC/OAuth login start:
  /oauth2/authorization/{registrationId}

OIDC/OAuth callback (Spring Security Servlet default):
  /login/oauth2/code/{registrationId}

SAML2 SP ACS (common):
  /login/saml2/sso/{registrationId}

CAS filter processing URL (Spring CAS Javadoc default):
  /login/cas
~~~

Never guard solely with a regex like “anything containing `/login`” while missing custom callbacks, reverse proxy rewrites, aliases, or queries. The **actual endpoint list** must come from your app and IdP/SP metadata/callback configuration.

Data leakage examples:
- Nginx access log recording request line on `/login/cas?ticket=...`.
- Spring debug filter printing `request.getQueryString()` at `/login/oauth2/code/corp`.
- WAF logging POST `SAMLResponse` on blocked request events.
- Application error page echoing `RelayState` or query `redirect_uri`.
- OAuth client library logging HTTP token responses carrying `refresh_token`.
- Frontend analytics sending full `location.href` while URL still holds `code`/`state`.
- API GET request attaching `access_token` to the URL.

Inspect **exact routes and data types**, not just Spring's access log format.

## 16. Standalone Java 17: Logging with a Route Allowlist Instead of Raw URLs

Example goal: simulate an OAuth/CAS/SAML callback and emit an audit event **containing no queries/tokens**. Code uses **`java.net.URI`** and an allowlist of fixed routes; it never reads request bodies, Authorization headers, or cookies into logs. It connects to no IdP, **performs no authentication**, and is **not a production sanitizer**: the goal is understanding the **log-only-permitted-data** method.

Create file **`AuthUrlSafeAuditDemo.java`**:

~~~java
import java.net.URI;

public final class AuthUrlSafeAuditDemo {

    enum Outcome { OK, REJECTED }

    static String route(URI uri) {
        return switch (uri.getPath()) {
            case "/login/cas" -> "CAS";
            case "/login/oauth2/code/corp" -> "OIDC";
            case "/login/saml2/sso/corp" -> "SAML";
            default -> "OTHER";
        };
    }

    static String safeMethod(String method) {
        return switch (method) {
            case "GET" -> "GET";
            case "POST" -> "POST";
            default -> "OTHER";
        };
    }

    static String event(String method, URI uri, Outcome result) {
        return "event=auth_callback route=" + route(uri)
                + " method=" + safeMethod(method)
                + " status=" + result;
    }

    public static void main(String[] args) {
        URI cas = URI.create(
            "https://portal.example/login/cas"
            + "?ticket=ST-EXAMPLE-SECRET&service=portal");

        URI oidc = URI.create(
            "https://portal.example/login/oauth2/code/corp"
            + "?code=AUTH-CODE-EXAMPLE&state=OPAQUE");

        URI saml = URI.create(
            "https://portal.example/login/saml2/sso/corp");

        String casLog = event("GET", cas, Outcome.OK);
        String oidcLog = event("GET", oidc, Outcome.OK);
        String samlLog = event("POST", saml, Outcome.REJECTED);

        System.out.println(casLog);
        System.out.println(oidcLog);
        System.out.println(samlLog);

        String allLogs = casLog + "\n" + oidcLog + "\n" + samlLog;
        boolean excludesSecrets =
                !allLogs.contains("ST-EXAMPLE-SECRET")
                && !allLogs.contains("AUTH-CODE-EXAMPLE")
                && !allLogs.contains("OPAQUE");

        System.out.println("No sample credentials in logs: "
                + excludesSecrets);

        System.out.println("CAS callback has query: "
                + (cas.getRawQuery() != null));

        System.out.println("SAML body not logged: "
                + !samlLog.contains("SAMLResponse"));
    }
}
~~~

Compile and run with **JDK 17+**:

~~~bash
javac AuthUrlSafeAuditDemo.java
java AuthUrlSafeAuditDemo
~~~

**Exact stdout:**

~~~text
event=auth_callback route=CAS method=GET status=OK
event=auth_callback route=OIDC method=GET status=OK
event=auth_callback route=SAML method=POST status=REJECTED
No sample credentials in logs: true
CAS callback has query: true
SAML body not logged: true
~~~

Explanation:

- `URI.create` holds **dummy values** simulating browser URLs with a CAS ticket and OAuth code; the program never prints `uri.toString()`.
- `route` returns only **fixed endpoint labels**, putting no raw paths or query strings into logs. Any path outside the allowlist is tagged `OTHER`.
- `safeMethod` allows only GET/POST, never printing unusual attacker-supplied HTTP method strings.
- `Outcome` is a bounded status enum; never log exceptions containing tokens.
- `No sample credentials in logs: true` confirms output from the **demo function** excludes the dummy tokens placed in the two URIs. It does not prove a real server isn't logging at the proxy/APM.
- `CAS callback has query: true` shows valid callbacks still carry URL queries, so tests **cannot simply block all queries**.
- `SAML body not logged: true` only illustrates omitting the body from this function; **it does not prove a real server's WAF/Tomcat/APM isn't storing SAMLResponse**.

**Never use this example to skip framework `Authorization`/`SAMLResponse` checks**: keep full protocol validation intact. Call audit functions only **after defining secret-free audit fields**.

## 17. Integrating Safe Audit Logging in Spring Security

A real app should emit audit events in authentication success/failure handlers or a dedicated service, with **few fields and fixed keys**:

~~~java
// Pseudocode fragment: requires logger bean and app-specific event model.
String protocol = "OIDC";   // from configured registrationId
String endpoint = "oidc_callback"; // static route ID
String outcome = "SUCCESS"; // high-level enum

auditLogger.info("protocol={} endpoint={} outcome={}",
        protocol, endpoint, outcome);

// Do not do:
// logger.info("callback={}", request.getRequestURL());
// logger.info("query={}", request.getQueryString());
// logger.info("parameters={}", request.getParameterMap());
// logger.info("idToken={}", oidcUser.getIdToken().getTokenValue());
~~~

In multi-IdP systems, log only **known internal registration IDs**, never dumping full issuer access tokens, `userinfo` JSON, or SAML XML. If auditing user identity is required, store an **internal user ID** post-validation per log data access policy—raw OIDC `sub`/NameID/email are unneeded without justification.

### Exceptions and auth errors

- Log `errorCode=INVALID_SIGNATURE`, `errorCode=EXPIRED_TOKEN`, `errorCode=CAS_TICKET_REPLAY` as internal enums.
- Never log `AuthenticationException.getMessage()` verbatim if the provider might embed tokens/requests in the message.
- Show only generic login errors to the browser, using an independent correlation ID for support.
- Never log entire `Saml2AuthenticationToken`, `OAuth2AuthenticationToken`, `BearerTokenAuthentication`, or credential-bearing properties via `toString()` without knowing their exact semantics.

**SIEM redaction is the last line of defense, not a substitute for refusing to collect secrets.** For performance traces, emit only high-level outcome/provider ID/duration without full `url.full` on auth callbacks.

## 18. “Clean” URLs and Browser History: When to Apply?

Proper diagram for callbacks carrying codes/tickets:

~~~text
Browser:
  /login/oauth2/code/corp?code=...&state=...
      -> Spring validates callback
      -> exchange code once
      -> creates authenticated session
      -> redirects 303/302 to /reports (no query tokens)

Final browser URL:
  https://portal.example/reports
~~~

Clean redirecting ensures **codes/tickets do not remain in the application page URL**. However, browser history or logs may still retain the initial callback URL. Therefore **never rely on redirecting alone**; combine short TTL/one-time semantics, PKCE, Referrer-Policy, log exclusions, and cache controls.

### Can JavaScript history.replaceState be used?

In SPAs, `history.replaceState({}, "", "/app")` can strip queries/fragments from the **current URL** after the callback was validly parsed and processed, yet:
- JavaScript having executed means the credential existed in the runtime.
- It does not erase raw URLs from proxy logs, older history/sync records, browser extensions, or analytics fired prior to cleanup.
- `replaceState` does not verify token signatures/issuers.
- Avoid breaking `state`/`nonce` validation or callback handling.

With Spring MVC server-side OIDC/CAS, prefer handling the callback **server-side** and redirecting cleanly before rendering, avoiding passing raw credentials to JavaScript.

## 19. Preventing Leaks via HTML, Analytics, Redirects, and Error Pages

Small gaps easily overlooked:

1. **Analytics capturing full URL:** `window.location.href` on a callback page holds `code`/`state` and gets sent to an analytics vendor. Block scripts from running on callbacks; strip query parameters and inspect actually transmitted data.
2. **Error pages echoing raw URLs:** “Login failed on /login/cas?ticket=...” puts the ticket into HTML, screenshots, and caches.
3. **Redirects preserving queries:** `Location: /home?ticket=...` inadvertently preserves the credential.
4. **Open redirects:** IdP/SP accepts `returnUrl=https://attacker.example` and redirects post-callback with state/tokens in the query.
5. **Referer to third parties:** callback page loads external images/scripts/links while the browser still holds the code.
6. **Exception diagnostics:** SAML XML rendered on end-user error pages for “easier debugging”.
7. **PDF/CSV exports:** app embeds tokens/NameIDs in metadata/filenames/QR codes unnecessarily.
8. **Copy/paste in support tickets:** developers capture address bars or HARs containing full callback URLs.
9. **Browser autofill/extensions:** extensions may read URLs/forms under granted permissions.
10. **Link previews/chat apps:** user shares a callback link holding a CAS ticket or OAuth code; preview bots fetch it, leaking or consuming the one-time ticket.

**Principle:** callback endpoints should be **pure protocol handlers**, rendering no third-party UI; error pages display only generic error codes and a path back to login.

## 20. Java Memory, Thread Dumps, Heap Dumps, and Secret Lifecycle

In Spring/Java backends, tokens can live in:
- `OAuth2AuthorizedClient`, `OAuth2AccessToken`, and refresh token stores.
- `OidcIdToken`/`OidcUser`, Spring SecurityContext/HTTP sessions.
- `Saml2Authentication`/credential objects containing Assertion XML or attributes.
- CAS ticket validation payloads.
- HTTP client request/response buffers, Netty ByteBufs, servlet request params.
- Thread locals/MDC, exception cause chains, temporary strings, heap dumps, and crash reports.

There is no practical way to guarantee a Java `String` holding a credential is immediately “zeroized”: immutable strings and GC can retain data until memory is reclaimed. Therefore:

- **Minimize copying credentials** into temporary strings/DTOs/logging/JSON.
- Do not retain raw Assertions/tickets/codes longer than needed for validation.
- Store tokens only in approved, encrypted, access-controlled credential stores with rotation/TTL.
- Never keep raw tokens in MDC, `ThreadLocal`, business events, or analytics payloads.
- Restrict read access to heap dumps, core dumps, thread dumps, crash artifacts, and backups/snapshots.
- Never enable `-XX:+HeapDumpOnOutOfMemoryError` to a world-readable volume or auto-upload to issue trackers without policy.
- Enforce retention, encryption, key rotation, and access audits on observability/artifacts.
- Use fake tokens when testing and never capture raw production traces.

**No security design should rely on “the token is in RAM so it is completely safe”.** XSS, RCE, memory dumps, or server compromise can extract tokens; scopes/TTLs/audience and secret management remain mandatory.

## 21. Misconfigurations and Diagnostics

| Symptom | Likely Leak Vector | Remediation |
| --- | --- | --- |
| Ingress access logs contain `?ticket=ST-...` | Logging request target/query | Switch to route/URI path-only; scrub all ingress |
| APM trace spans contain `code=...` | `url.full` or auto-tagging | Drop query/headers/body before export |
| SAML XML appears in WAF events | Request body sampling | Disable/redact SAMLResponse capture via narrow rule |
| Browser Back shows pre-logout page | HTTP cache/bfcache/session policy | no-store + session invalidation + browser restore tests |
| Tokens appear in localStorage | Frontend token persistence | BFF/HttpOnly cookies or reduced-JS-exposure architecture |
| User sends screenshot of URL with CAS ticket | Address bar/history | One-time handling + clean redirect + support policy |
| API uses `?access_token=...` | Bearer query URI | Switch to Authorization header over HTTPS |
| Audit records ID Token and full email | Flawed logging design | Route/outcome allowlist + PII minimization |
| App 302s to external redirect URL with state | Open redirect/returnUrl abuse | Validate relative paths/strict allowlist |
| “no-cache” yet browser retains sensitive data | Missing no-store or another cache layer | Add no-store, check CDN/Service Worker |
| Login callback loads third-party tracking script | Referrer/JS execution | Remove third-party resources on callbacks |
| XSS on SPA reads token | Web Storage/JS token access | CSP, XSS defense, BFF/token handling |
| Spring defaults present yet response cached | Controller/proxy overrides headers | Inspect final response at edge, fix override |
| TLS verification disabled for debugging | MITM can read credentials | Proper PKIX truststore/hostname |
| Signed SAML Assertion leaks attributes | Signature does not encrypt | Minimization, SAML Encryption if needed |
| CAS ticket validation works yet logs hold raw ticket | Separate logging pipeline | Audit allowlist + ingress scrubbing |
| Logout does not stop active tokens | Token vs session revocation differ | Token TTL, revocation, backend checks |

**Do not treat an HTTP 200 test as sufficient.** Tests must observe exact trace/log/caching/history boundaries while ensuring protocol login still succeeds and replays are rejected.

## 22. Anti-Leakage Test Matrix by Protocol

| Area | Scenario | Expected |
| --- | --- | --- |
| OAuth callback | `code`/`state` in callback URL | Protocol succeeds, absent from logs/APM |
| PKCE | Code stolen without verifier | Token endpoint rejects unauthorized exchange |
| Replayed code | Exchanging same code twice | Rejected (one-time) |
| OAuth implicit | Access token in fragment | Legacy flow disabled without justification |
| API | Bearer token in query | Client never sends it; resource policy rejects/disables |
| API | Valid Authorization header | API validates issuer/audience/scope/expiry |
| OIDC tokens | Raw ID/refresh tokens | Absent from logs, JS analytics, URLs, error pages |
| Multiple IdPs | Code from IdP A sent to callback B | Mix-up checks reject |
| Redirect target | External URL forced via query | No open redirect |
| CAS ST | `ticket` query on callback | Ticket validated one-time, absent from ingress/app logs |
| CAS replay | Reusing already-validated ST | CAS rejects |
| CAS service mismatch | ST issued for another service | SP/CAS rejects |
| CAS proxy ticket | PT/PGT in downstream contexts | Not logged, delegation scope restricted |
| SAML POST | SAMLResponse hidden form | Browser POST over TLS, full ACS verification |
| SAML XML log | WAF debug body capture | Raw Assertion/NameID absent from logs |
| SAML replay | Already-used Assertion ID | Replay cache/validity rejects |
| SAML wrong audience | Assertion for another SP | Reject |
| SAML Artifact | Redeeming artifact twice | Reject/resolve per profile |
| Cache auth pages | Response Cache-Control | no-store, Pragma/Expires per policy |
| Browser Back | Logout then Back | Session data neither shown nor accepted against policy |
| CDN cache | Users A and B on same URL | Never reuse private auth/sensitive responses |
| Referer | Callback loads external resources | Never sends URL carrying code/ticket/state |
| Analytics | `location.href` on callback | Query sanitized or no third parties present |
| Header logs | Authorization/Cookie/Set-Cookie | Redacted/omitted across entire pipeline |
| HAR export | Raw login trace | Never distributed outside approved systems |
| Browser storage | localStorage/sessionStorage/IndexedDB | Contains no long-lived credentials per policy |
| XSS | Malicious script can run | CSP + XSS defense, tokens not easily readable |
| Session cookie | Flags and SameSite fit callback | Secure/HttpOnly/SameSite, no session IDs in URL |
| Heap dump | App memory diagnostics | Restricted, encrypted, TTL, no public attachments |
| Failure handler | Auth exception with details | Error code/correlation ID only, no XML tokens |
| Log redaction regression | New fields, query aliases/encoded params | Allowlist still excludes credentials |
| Load balancer config drift | One node still logs full query | Automated config check detects |
| Token issuer/key rollover | IdP rotates keys | RP verifies cleanly without dropping signatures |
| Incident exercise | Synthetic token placed in logs | Alert/triage/revocation/purge execute properly |

### Using synthetic credentials in testing

Never use production bearer tokens to “see if logs keep secrets”. Create clearly labeled dummy strings like `TEST-CAS-ST-DO-NOT-USE`, send them through **authorized test infrastructure**, and inspect ingress/app/APM/SIEM logs via proper procedures. Afterwards ensure test data is not mistaken for real tokens or shipped to out-of-scope alert vendors.

With Spring MockMvc, you can verify:
- Cache headers on protected responses and callback failures.
- `Referrer-Policy` on responses before redirects and after login.
- No redirects to arbitrary external URLs.
- Authentication success/failure never echoes credentials.
- Structured audit events exclude callback parameters.

**MockMvc cannot test Nginx/WAF/Cloud CDN or browser history.** Dedicated end-to-end tests are needed to observe those layers.

## 23. Layered Practical Verification Procedure

1. **Map credential flows**: OIDC code/token endpoints, SAML POST/Artifact, CAS ST/PGT, cookies.
2. **Classify secrets** per field: bearer, one-time ticket, correlation state, PII.
3. **Audit callback endpoints** and proxy rewrites/IdP metadata; remove unnecessary paths.
4. **Audit URL/query logging** at ingress, LB, CDN, web servers, and app.
5. **Audit POST body logging** at WAFs, reverse proxies, and SAML error reporting.
6. **Audit HTTP client wire logs** on token/CAS validation back-channels.
7. **Verify response headers** on auth/PII routes behind all proxies: no-store/no-referrer.
8. **Audit frontend**: analytics, third-party scripts, history handling, Service Workers, browser storage.
9. **Verify Spring framework flows**: state, nonce, PKCE, signatures, audience, service binding, replay.
10. **Audit Java memory/artifacts**: dumps, exception payloads, session/token stores, MDC, APM spans.
11. **Test User A/B** to verify private cached data is never shared; test Back/logout.
12. **Test negative cases**: replay, wrong audience, token in query, open redirect, forged SAML/expired CAS ST.
13. **Drill the incident runbook** with synthetic tokens, log discovery, revocation, purge, and auditing.
14. **Assign ownership**: network/platform, IdP/IAM, app, security monitoring, and support processes.

Any major change to APM agents, reverse proxy log formats, CDN rules, Spring Security upgrades, or SSO protocol bindings should re-run a relevant subset of these checks.

## 24. When a Token/Assertion/Ticket Leaks: Incident Response

If a raw credential is found in logs, traces, support tickets, or browser storage, **do not merely delete the log line**. Execute:

1. **Scope assessment**: credential type (access vs refresh, CAS ST, SAML Assertion, session cookie), issuer, audience, TTL, privileges, and who had read access.
2. **Stop ongoing leakage**: disable raw query/body/header capture or pause the pipeline; preserve evidence per legal/audit rules.
3. **Revocation**: revoke tokens/refresh tokens if supported by the provider; invalidate affected sessions, rotate client/service secrets if needed. For one-time codes/tickets, verify whether they were used or expired and still check for replay/misissuance.
4. **Inspect access logs/API usage**: look for abuse by identity, audience, IP/device, and granted scopes without spreading the credential further during investigation.
5. **Hunt for copies**: ingress logs, SIEM, APM, WAF, debug artifacts, screenshots, browser sync, backups, support tools, third-party processors.
6. **Purge/redact** per retention/incident policy; never claim all copies on user devices were deleted unless provable.
7. **Assess personal and legal impact**: SAML/ID Tokens containing PII may require breach notification workflows; never assume “one-time token expired” means zero disclosure.
8. **Fix the design**: log allowlists, SSO callback isolation, cache controls, key/token rotation, and automated regression tests.
9. **Document lessons learned** and update contracts across IdP, app, proxy, and logging platform.

**Never re-post a real token to ask support.** When evidence is needed, use an independent correlation ID and minimized time-window details.

## 25. Frequently Asked Questions

**Q:** Is an OIDC Authorization Code in the query string a security bug?

**A:** Not by itself: redirect query delivery is standard flow. The risk is the code entering logs/history/Referer; mitigate with PKCE, state, short TTL, exact redirect URI, clean redirects, no-referrer, and log scrubbing.

**Q:** Is putting an access token in the URL fragment safe because the server never sees `#`?

**A:** No. Fragments normally aren't sent to the server, yet exist in browser/JS/history and can be stolen by XSS/extensions. RFC 9700 discourages implicit grant emitting access tokens on the front-channel.

**Q:** `SAMLResponse` is in a hidden form field—does that mean it is encrypted?

**A:** No. Base64 is encoding, not encryption. Signatures prevent tampering when verified properly; hiding attributes from browsers/intermediaries requires considering encrypted assertions per threat model.

**Q:** CAS tickets inherently put `ticket` in the URL—must CAS be turned off?

**A:** No. Implement proper one-time/service-bound CAS service-ticket validation, omit queries from logs, set no-store/no-referrer, and redirect to a clean URL. Never re-log the ticket or keep it in app links.

**Q:** Does `Cache-Control: no-store` erase browser history?

**A:** No. It governs HTTP caching semantics only—it is not a command to wipe history, screenshots, APM logs, or Service Worker storage.

**Q:** When using `Authorization: Bearer`, do we still need log scrubbing?

**A:** Yes. WAFs/proxies/APM can record headers. Never collect Authorization, Cookie, Set-Cookie, or token response bodies in logs.

**Q:** Can we hash tokens and log them for debugging?

**A:** Assess re-identification risk and artifact predictability. Prefer independent event IDs; if a stable marker is truly needed, use a secret-keyed HMAC with retention/access controls rather than ad-hoc raw SHA over low-entropy tokens.

**Q:** Is `SameSite=Strict` always best for SSO?

**A:** No. Cross-site SAML POST ACS may need `SameSite=None; Secure` or another session-state design, while OIDC GET callbacks often use `Lax`. Test against real CSRF and session rules; never weaken security blindly.

**Q:** Spring's logs are clean—what else needs checking?

**A:** Ingress, CDN, load balancers, WAF, HTTP client wire logs, APM, centralized log collectors, browser analytics, HARs, and crash/heap dumps.

## 26. Acceptance Checklist

- [ ] Clearly classify OAuth codes, ID/Access/Refresh Tokens, SAML Responses/Artifacts, CAS ST/PT/PGT, and session cookies.
- [ ] Never place access tokens/refresh tokens in URI queries or fragments for “easy sharing”.
- [ ] OIDC Authorization Code flow enforces PKCE, state/nonce, exact redirect, and one-time codes.
- [ ] Legacy implicit token-in-browser flow is not enabled without risk justification.
- [ ] Never log raw callback URIs/queries in Spring, ingress, CDN, or WAF/APM.
- [ ] Never log POST body `SAMLResponse`, decoded Assertions, or NameID/PII.
- [ ] CAS service tickets validate one-time and bind to service URLs.
- [ ] SAML signatures, audience, destination, recipient, timestamps, and replay are validated.
- [ ] Token issuers, signatures, audiences, scopes, and expirations are verified.
- [ ] Auth callback/error pages use no third-party analytics/scripts and never echo params.
- [ ] `Referrer-Policy: no-referrer` is applied on appropriate pages.
- [ ] `Cache-Control: no-store` and compatibility headers are applied to auth/private responses.
- [ ] Never cache auth callbacks/PII pages at shared CDNs/proxies.
- [ ] Cookie Secure/HttpOnly/SameSite align with GET/POST federation callbacks.
- [ ] Never use URL rewriting with JSESSIONID or session ID query params.
- [ ] Browser storage holds no long-lived tokens/session IDs per policy.
- [ ] Service Worker Cache API stores no token/PII auth data.
- [ ] Logs contain only route ID/method/result/correlation ID without user credentials.
- [ ] Never log `Authorization`, `Cookie`, `Set-Cookie`, or HTTP client token responses.
- [ ] Dumps/traces/HARs/crash reports have access/retention limits and redaction.
- [ ] Post-login, the browser redirects to a clean URL free of auth artifacts.
- [ ] User A/B, Back/logout, Referer, redirect, and cache regression tests PASS.
- [ ] Tests exist against open redirects, code replay, CAS ST replay, and SAML Assertion replay.
- [ ] Incident runbook for revoke/purge/notify/rotate with clear ownership is in place.
- [ ] Re-verify after Spring/IdP/ingress/observability upgrades.

## 27. Official References

1. [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): OAuth code/access token leakage via Referer/history, PKCE, exact redirect URI, implicit flow, and countermeasures.
2. [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer via Authorization and query parameter risks.
3. [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): code challenge/verifier preventing authorization code interception.
4. [Spring Security — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/features/exploits/headers.html): default Cache-Control/Pragma/Expires/HSTS and caching policy.
5. [Spring Security — Servlet Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): Spring header configuration/overrides.
6. [Spring Security — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): `/login/oauth2/code/*` redirect endpoint.
7. [Spring Security — CasAuthenticationFilter Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/cas/web/CasAuthenticationFilter.html): CAS `ticket` parameter, service URL, and default `/login/cas`.
8. [OASIS — SAML V2.0 Technical Overview](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html): HTTP POST binding, SAMLResponse hidden form, and ACS processing.
9. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): never log session IDs, access tokens, passwords, or sensitive data.
10. [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): browser Web Storage, session cookies, logout, and session risks.
11. [OWASP — HTML5 Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html): localStorage/sessionStorage and XSS.
12. [MDN — Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control): no-store/no-cache/private semantics.
13. [MDN — Referrer-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy): no-referrer and leak prevention.
14. [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): Secure/HttpOnly/SameSite cookie attributes.
15. [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): verifying bearer tokens, issuer, JWT claims, and authorities.

**Final takeaway:** authentication data must stay within the right **channel, lifetime, and recipient**; avoid turning callback URLs, logs, browser storage, or heap dumps into unintended credential stores. With **OIDC**, use Authorization Code + PKCE and protect callbacks; with **SAML**, protect POST bodies, XML/claims, and replay; with **CAS**, accept protocol tickets on the URL yet never store/log them and validate once. Across Spring and infrastructure, enforce **log allowlists, no-store, no-referrer, HTTPS, secure session cookies, clean redirects, limited token retention, and end-to-end negative tests**.