# Lost Cookie, Wrong SameSite, or Public URL Mismatch Behind Proxy — Spring Security Diagnostics

## 1. Scenario and Goal

A Spring Boot/Spring Security application runs fine on localhost, yet after deploying behind Nginx, ingress, or a load balancer it hits one of these symptoms:

- Users log in successfully and are immediately redirected back to the login page.
- The browser gets multiple `302` redirects between `/login`, home, and the Identity Provider (IdP).
- OAuth2/OIDC login reports `redirect_uri_mismatch`, `invalid_state_parameter`, or missing authorization request.
- A session cookie is sent in the response, yet the next request omits the `Cookie` header.
- The cookie still sits in Browser Storage, yet is not sent on a cross-site `POST` callback.
- The app emits `Location: http://app:8080/login/oauth2/code/...` or `/login/...` while the user visits `https://login.example.test/auth/...`.
- In a multi-pod environment, login works intermittently even though the browser sends the cookie properly.

The goal of this lesson is **not to guess and disable security**. We need to find the exact break point in the chain:

```text
Did browser receive Set-Cookie?
   |
   +-- NO  -> login failed / session not created /
   |          response altered by proxy / attributes rejected by browser
   |
   +-- YES -> Did browser store the cookie?
                |
                +-- NO  -> Secure/HTTPS, Domain, Path,
                |          __Host- prefix, SameSite=None without Secure,
                |          third-party policy, quota...
                |
                +-- YES -> Did next request send Cookie?
                             |
                             +-- NO  -> host/path/scheme/SameSite,
                             |          CORS credentials, cross-site POST,
                             |          iframe/third-party restrictions
                             |
                             +-- YES -> Does backend recognize the session?
                                          |
                                          +-- NO  -> expired/invalidated,
                                          |          session ID rotated after login,
                                          |          wrong cookie name,
                                          |          different pod/session store,
                                          |          SecurityContext not saved
                                          |
                                          +-- YES -> Check authorization/CSRF/
                                                   OAuth state/redirect URI
```

With proxies and OAuth2, there is also an **independent** question: does the backend know the external public URL and generate the right callback/redirect? A valid cookie **cannot fix** a `redirect_uri` built from an internal host/scheme/prefix.

The main context is **Spring Boot 3.x / Spring Security 6.x Servlet, Spring MVC, Java 17+**. Examples use the synthetic domain `example.test`, not real accounts or services. For WebFlux or Spring Boot 4/Spring Security 7, cross-check version-specific properties and APIs.

## 2. Distinguishing Three Easily Confused Problem Categories

| Category | Concrete Sign | Usually Involves |
| --- | --- | --- |
| **Cookie not stored** | Response has `Set-Cookie`, yet Application > Cookies does not | `Secure` over HTTP, `SameSite=None` missing `Secure`, invalid `Domain`, wrong `__Host-` prefix, browser policy |
| **Cookie not sent** | Browser holds cookie, yet request lacks matching `Cookie` | Domain/host, Path, HTTPS, SameSite, cross-site `POST`/iframe, `fetch(credentials)` |
| **Cookie sent, no session** | Request has `Cookie`, yet server sees anonymous/no `SecurityContext` | Expired session, logout/rotation, missing shared store, Spring Security session policy or custom save |
| **Wrong public URL** | `Location`/`redirect_uri` uses `http`, internal host, port `8080`, or drops `/auth` | Trusted forwarded headers and reverse proxy path rewriting |
| **CSRF or OAuth state failure** | `403` CSRF, OAuth callback reports missing state | Cookie not sent, lost state session, cross-site POST, or wrong request flow |
| **Redirected right after login** | Browser loops `302 /login` despite valid credentials | Unpersisted session, unsent cookie, callback path mismatch, or wrong protection rule |

**Correct investigation order:** observe **response containing `Set-Cookie` → browser storage decision → request `Cookie` → backend session lookup → `redirect_uri`/state/CSRF**. Do not start by setting `SameSite=None` or disabling CSRF across the entire app.

## 3. Understanding Each Boundary and What Information to Record

A deployment with TLS termination and a public prefix:

```text
Browser
  https://login.example.test/auth/login
    |
    | TLS, Host: login.example.test
    v
Nginx / Ingress / Load Balancer
    |  public prefix /auth may be stripped per config
    |  X-Forwarded-Proto: https
    |  X-Forwarded-Host: login.example.test
    |  X-Forwarded-Port: 443
    |  X-Forwarded-Prefix: /auth
    v
Spring Boot app
  http://app:8080/login
    |
    +-- Spring Security: Authentication + session context
    +-- Servlet container: Set-Cookie/HttpSession
    +-- OAuth2 client: builds redirect_uri/callback
    v
Response via proxy back to browser
  Set-Cookie: __Host-SESSION=...; Path=/; Secure; HttpOnly; SameSite=Lax
  Location: https://login.example.test/auth/...
```

In this example, the **public base URL** is `https://login.example.test/auth`, whereas the backend sees `http://app:8080` if proxy info is not handled. Using `server.servlet.context-path=/auth` **while** the proxy strips the prefix and sends `X-Forwarded-Prefix=/auth` can accidentally double `/auth/auth` or break mappings. Always diagram the actual path and rewrites.

### Five Values to Verify

1. **Browser public URL** in the address bar: scheme, host, port, and path.
2. **Actual backend URL** called by the proxy: scheme, host, port, and path after rewrite.
3. **Forwarded headers overwritten by the trusted proxy**: `Forwarded` or `X-Forwarded-Proto`/`Host`/`Port`/`Prefix`.
4. **Headers actually received by the browser**: `Set-Cookie`, `Location`, HSTS/CORS, and HTTP status.
5. **URI used by Spring OAuth2 client**: `redirect_uri` sent to the Authorization Server and callback registered at the IdP.

Never print raw session IDs, authorization codes, `state`, CSRF tokens, passwords, cookies, or access tokens into logs to "diagnose". When comparing sessions, use boolean indicators, correlation IDs, and redacted metadata.

## 4. Did the Browser Actually Receive `Set-Cookie`?

With browser Developer Tools:

1. Open **Network**, enable Preserve log.
2. Log in from an incognito/test profile; locate the **response** that begins/completes authentication (possibly multiple `302`s).
3. Inspect `Response Headers → Set-Cookie` on **each response**, not just the final response.
4. Check the request's **Cookies** tab and any **Blocked/Excluded Reasons** warnings if provided by the browser.
5. Open **Application/Storage → Cookies** for the right host.
6. Follow the **next request** and its Request Cookies tab to confirm whether the cookie was actually sent.

### Why Is `Set-Cookie` Missing on the Final Response?

A successful login typically consists of:

```text
POST /login
   <- 302, Set-Cookie: SESSION=...  (ID may rotate after login)
GET /home
   <- 200, Set-Cookie not required
```

If you inspect only `GET /home`, you might wrongly assume "the server did not create a cookie". **Preserve log** lets you see `Set-Cookie` on the intermediate response in the redirect chain.

`Set-Cookie` is a **forbidden response header** for the JavaScript Fetch API, so `response.headers.get("set-cookie")` on the frontend normally returns null even when the Network tab shows the cookie. That is a browser header-protection rule, not proof the server omitted the cookie.

### If the Response Has No `Set-Cookie`

- Did login actually succeed? Check HTTP status, `Location`, and authentication failure handlers.
- Was a session created? `SessionCreationPolicy.STATELESS`, `NullSecurityContextRepository`, or custom filters can prevent server sessions.
- With Spring Security 6.x, a **custom authentication flow** setting `SecurityContextHolder` directly may need to call `SecurityContextRepository.saveContext(...)`; writing only to ThreadLocal does not guarantee the next request is authenticated.
- Did a proxy/CDN strip/modify `Set-Cookie` or cache an authenticated response?
- Did the browser receive the response from the right endpoint, or redirect to another host where the cookie appeared?
- A session ID changing after login is normal under **session fixation protection**. Compare the new cookie after login, not the old anonymous ID.

**Do not propose disabling session fixation protection.** Rotation exists to stop attackers who knew the ID before the victim logged in.

## 5. Why Is `Set-Cookie` Present, Yet the Browser Still Does Not Store It?

A sample cookie **not shared with subdomains**:

```http
Set-Cookie: __Host-SESSION=redacted; Path=/; Secure; HttpOnly; SameSite=Lax
```

`redacted` is a placeholder string hiding the secret, not a real usable session value.

### Key Attributes and Failures

| Attribute | Rule | Diagnostic Failure |
| --- | --- | --- |
| `Secure` | Cookie sent only over HTTPS (browsers make an exception for localhost) | Issuing secure cookies from a public HTTP origin or visiting an HTTP URL |
| `HttpOnly` | JavaScript cannot access cookie via `document.cookie` | Developers think the cookie disappeared when JS cannot read it |
| `SameSite=Lax` | Sent same-site; plus certain top-level cross-site safe navigations like GET | OIDC callback using cross-site POST omits cookie |
| `SameSite=Strict` | Sent only in same-site context | Clicking a top-level link from email/external site omits cookie |
| `SameSite=None` | Allowed under SameSite for both same-site and cross-site | Must include `Secure`; still subject to third-party cookie policies |
| `Domain` | If omitted: host-only cookie | Setting `Domain=internal.local` when browser visits `login.example.test` gets rejected |
| `Path` | Browser sends only for matching paths | Cookie has `Path=/api` while callback is at `/auth` |
| `Max-Age` / `Expires` | Browser may delete cookie on expiry or `Max-Age=0` | Cookie cleared by logout/redirect response or clock/policy |
| `__Host-` prefix | `Secure`, HTTPS origin, `Path=/`, **no Domain** | Having `Domain` or `Path=/auth` causes browser rejection |

**The browser decides** whether to accept a cookie. A `Set-Cookie` header looking reasonable in `curl` is not enough to prove the browser stored it; check DevTools and browser policies.

### Host-Only and `Domain`

- A cookie issued from `login.example.test` **without `Domain`** belongs exclusively to that host.
- `Domain=example.test` makes the cookie eligible to be sent to subdomains, widening the attack surface; avoid using it just to "fix login" unless genuinely needed.
- `Domain=app:8080` is invalid: the `Domain` attribute **never includes a port**. Browsers use the external hostname, never an internal backend hostname.
- Two cookies with the same name but different `Path`/`Domain` can coexist; the server receives a `Cookie` header without `Path`/`Domain` attributes, easily reading the wrong ID. Inspect cookie storage and clean up stale duplicates cleanly.
- A cookie issued by `login.example.test` does not automatically carry to `api.another.test`; across different domains, design proper cross-origin authentication rather than expanding `Domain` across registrable domains.

### The `__Host-` Prefix

With `__Host-SESSION`, prefix-aware browsers reject:

```http
# WRONG: has Domain
Set-Cookie: __Host-SESSION=redacted; Path=/; Domain=example.test; Secure

# WRONG: Path other than "/"
Set-Cookie: __Host-SESSION=redacted; Path=/auth; Secure

# VALID PER PREFIX RULES:
Set-Cookie: __Host-SESSION=redacted; Path=/; Secure; HttpOnly; SameSite=Lax
```

A cookie prefix constrains only **how the browser accepts the cookie**, not whether the user is authenticated or the server session is valid. If an app runs under public prefix `/auth`, `Path=/` is still valid for the prefix, though it sends the cookie across the whole host; evaluate host scope and avoid mixing unrelated apps on the same hostname carelessly.

## 6. Distinguishing `SameSite`, Same-Origin, Cross-Origin, and Cross-Site

**Origin** is typically `scheme + host + port`. **Site** in `SameSite` uses *schemeful site* (scheme plus registrable domain), so two different origins can still be same-site.

| Scenario | Cross-Origin? | Cross-Site? | Consequence |
| --- | --- | --- | --- |
| `https://app.example.test` → `https://api.example.test` | Yes | Usually **no**, if sharing registrable domain | Needs CORS for JS `fetch`; `SameSite=Lax` can send cookie |
| `https://app.example.test` → `https://other.test` | Yes | Yes | `SameSite=Lax` blocks many requests |
| `http://app.example.test` → `https://app.example.test` | Yes | Schemeful site can differ | `Secure` and `SameSite` must consider scheme too |
| `https://login.example.test` → `https://login.example.test` | No | No | Cookie Path/TTL/session state can still fail |

**CORS does not replace `SameSite`**, and **`SameSite` does not replace CSRF protection**. A compromised subdomain can still be same-site despite being cross-origin. With cookie-authenticated APIs, keep CSRF tokens/Origin checks per threat model.

### `SameSite=Lax` With OIDC Redirects

- Top-level `GET` navigations from the IdP back to the app are normally allowed by `SameSite=Lax` cookies.
- Cross-site `POST`, such as OIDC `response_mode=form_post`, **does not** send cookies with **explicit `SameSite=Lax`** under standard rules.
- If `SameSite` is **omitted**, some browsers apply Lax-by-default with a brief POST grace window for new cookies. Never rely on this browser quirk when designing authentication.
- With `SameSite=Strict`, callbacks/navigations from an IdP can drop cookies even on top-level GETs.
- `SameSite=None; Secure` permits cookies under SameSite rules yet **does not guarantee** delivery: browsers may restrict third-party cookies, tracking protection, or iframes.

**Never apply `SameSite=None` unconditionally to every cookie.** When a flow truly needs cross-site POST/iframe, scope the cookie specifically and keep CSRF, OAuth `state`, OIDC `nonce`, PKCE where appropriate, and security headers. For many systems, switching to a top-level GET callback or designing proper OAuth state storage is worth considering.

## 7. Cookie Is Stored, Yet Absent From Requests

Inspect the **specific request**, not just the Storage tab. Example `Secure` cookie for `login.example.test`:

```text
Browser Storage:
  __Host-SESSION
    Host = login.example.test
    Path = /
    Secure = true
    SameSite = Lax

Request A: https://login.example.test/auth/home
  Cookie is sent if valid and not blocked by another policy.

Request B: http://login.example.test/auth/home
  Secure cookie is not sent over plain HTTP.

Request C: https://other.example.test/auth/home
  Host-only cookie for login.example.test is not sent.

Request D: cross-site POST callback to login.example.test
  Explicit SameSite=Lax normally blocks sending the cookie.
```

### Non-SameSite Causes

- Cookie `Path` is `/portal` while the request hits `/auth`.
- A logout response sent `Set-Cookie` with `Max-Age=0`, deleting the cookie immediately.
- Two apps share the same cookie name and host, each overwriting the other's ID.
- Browser is in privacy/third-party restriction mode or an extension blocks cookies.
- Cross-origin `fetch()`/Axios did not enable credentials; CORS response omits `Allow-Credentials`.
- Browser switches hosts constantly, e.g., `www.example.test` vs `example.test`.
- A redirect goes from HTTPS to HTTP, dropping `Secure` cookies on the next hop.
- A new cookie after session fixation rotation replaced the old ID; the client retained or resent the old value.
- Session cookie hit `Max-Age`/`Expires` or was evicted by browser policy.
- Server uses a different cookie name than the client sends (e.g. `JSESSIONID` vs `SESSION`, Spring Session, or custom setup).

**Do not check `document.cookie` to verify a session cookie exists** when `HttpOnly` is set: JavaScript not seeing it is intended behavior.

## 8. SPA, `fetch` Credentials, CORS, and Cookies

For a frontend `https://app.example.test` calling API `https://api.example.test`, the request is **cross-origin** even if same-site. The browser Fetch API defaults to credentials mode `same-origin`; thus you must explicitly opt in for cross-origin cookies.

Example **on a frontend genuinely permitted to call the API**:

```javascript
const response = await fetch(
  "https://api.example.test/account",
  {
    method: "GET",
    credentials: "include"
  }
);
```

On the backend/API and gateway, verify:

- `Access-Control-Allow-Origin` matches the **specific allowed origin** when using credentials, never wildcard `*`.
- `Access-Control-Allow-Credentials: true` on valid credentialed CORS responses.
- `OPTIONS` preflights are not wrongly blocked by authentication; keep a proper CORS allowlist.
- Cookies have host/path/secure/samesite matching the **target request**, not just the origin hosting the JavaScript.
- For true cross-site requests, `SameSite=None; Secure` may be needed, though browser third-party restrictions can still block it.
- For cookie-authenticated POST/PUT/DELETE, **CSRF protection is still required**. CORS policy does not replace anti-CSRF.

**If frontend and backend are same-origin**, do not loosen CORS or `SameSite` to cure an unrelated bug. Read the Network request to see whether the HTTP request actually carries the cookie.

## 9. Public URL Mismatch Behind Proxy: A Separate Bug From Cookies

Spring Boot runs at `http://app:8080`, while users visit `https://login.example.test/auth`. OAuth2 login may build an authorization request:

```text
Wrong (backend-internal):
  redirect_uri=http://app:8080/login/oauth2/code/demo

Right (public):
  redirect_uri=https://login.example.test/auth/login/oauth2/code/demo
```

IdPs normally require `redirect_uri` to match the **exact registered value** for scheme/host/port/path; any mismatch fails before the callback reaches the app. A different hostname, wrong port, or missing public prefix suffices to fail.

Check two separate values:

1. The `redirect_uri` **actually sent** in the authorization request to the IdP; visible percent-encoded in Network (keep `state`/nonce secret when sharing logs).
2. The redirect URI **registered** at the IdP (application/client registration).

If the two differ, fix forwarded headers/context-prefix/registration config. **Never** use wildcard redirect URIs or disable redirect URI validation at the IdP just to make login "work again".

### Meaning of `baseUrl` in `oauth2Login`

Spring Security OAuth2 Client supports template variables such as:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            client-id: "registered-demo-client"
            client-secret: "read-from-secret-manager-in-real-deployments"
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          demo:
            issuer-uri: "https://idp.example.test/realms/demo"
```

**This is an illustrative config excerpt**, not a runnable OIDC app: client registration, secret, issuer metadata, user store/certificates must come from a real secrets manager. Never commit plaintext client secrets in production repositories, even if guides use placeholder strings.

`{baseUrl}` depends on the external request info Spring observes after proxy processing. Without forwarded headers, it can become HTTP/backend hostname instead of HTTPS/public domain. `{registrationId}` must match both the callback route and client registration.

It must also match Spring Security's callback handler `/login/oauth2/code/{registrationId}`, or if customizing the redirect endpoint, configure the same path in `oauth2Login().redirectionEndpoint(...)`. Do not change one side and forget the other.

## 10. Spring Boot 3.5: Configuring Forwarded Headers and Cookies

Configuration for a **Servlet app behind a trusted reverse proxy**:

```yaml
server:
  # Spring Framework ForwardedHeaderFilter / forwarded info:
  forward-headers-strategy: framework

  # With Tomcat and SSL termination at proxy, avoid context-root
  # redirect occurring before X-Forwarded-Proto is evaluated:
  tomcat:
    redirect-context-root: false

  servlet:
    session:
      tracking-modes: cookie
      timeout: 20m
      cookie:
        name: "__Host-SESSION"
        path: /
        secure: true
        http-only: true
        same-site: lax
```

**Effects and preconditions:**

- `server.forward-headers-strategy=framework` lets the framework process `Forwarded`/`X-Forwarded-*`, including public scheme, host, port, and prefix in the appropriate context.
- `native` uses container features, which may suffice for `X-Forwarded-Proto`/`X-Forwarded-For` yet does not necessarily handle all public prefix styles. Choose per your actual proxy/container, and **never stack multiple overlapping forwarded-header layers simultaneously** without verifying.
- `server.tomcat.redirect-context-root=false` is recommended by Spring Boot when Tomcat sits behind an SSL-terminating proxy so context-root redirects do not fire before trusting `X-Forwarded-Proto`.
- `secure=true` issues `Secure` cookies even when **proxy → backend** is HTTP; the real client URL must still be HTTPS.
- `http-only=true` protects the session cookie from direct JavaScript reads.
- `name="__Host-SESSION"` and `path=/` **are valid only when `Domain` is unset** and browser requests arrive over HTTPS; if the container/proxy adds `Domain` or alters `Path`, the browser rejects the prefix.
- `same-site=lax` is **suited to standard top-level GET flows**, not necessarily `form_post` callbacks/iframes; change only after verifying the actual flow.
- `tracking-modes=cookie` avoids `;jsessionid=...` in URLs. Test actual container/link generation.

**Number-one trust rule:** if the edge proxy **does not strip inbound client-supplied forwarded headers and overwrite them with trusted values**, enabling `server.forward-headers-strategy=framework` allows host-header/redirect poisoning. Never leave the backend port exposed directly to attackers while the app trusts forwarded headers by default.

### When Public Prefix and Servlet Context Differ

Two models to distinguish:

**A. Proxy strips `/auth`**:

```text
Public:  https://login.example.test/auth/login
Proxy:   /auth/login  ->  http://app:8080/login
Header:  X-Forwarded-Prefix: /auth
App:     server.servlet.context-path default /
```

**B. Backend mounts at `/auth` itself**:

```text
Public:  https://login.example.test/auth/login
Proxy:   /auth/login  ->  http://app:8080/auth/login
App:     server.servlet.context-path: /auth
Header:  X-Forwarded-Prefix not needed to add /auth again
```

Both approaches work, yet **do not mix** configs to produce double prefixes or broken mappings. With multiple proxy hops, document every path rewrite and accompanying headers.

## 11. Nginx TLS Termination: Controlled Path-Stripping Example

Suppose Nginx is the **sole** edge proxy receiving public requests and the backend runs at `http://app:8080` with context path `/`. An illustrative config excerpt:

```nginx
server {
    listen 443 ssl;
    server_name login.example.test;

    # ssl_certificate, ssl_certificate_key, TLS policy, and HSTS
    # must be configured for your real system.

    location /auth/ {
        # Trailing / in proxy_pass rewrites the /auth/ prefix
        # to / at the backend with this location prefix style.
        proxy_pass http://app:8080/;

        # Do not let clients dictate scheme/host/port/prefix:
        proxy_set_header Host login.example.test;
        proxy_set_header X-Forwarded-Host login.example.test;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-Prefix /auth;

        # Clear inbound Forwarded header to prevent conflicts/spoofing:
        proxy_set_header Forwarded "";

        # With a single edge, do not inherit client-supplied IP chains.
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
```

**This is an Nginx snippet, not a complete deployment file.** Certificates/ciphers, HTTP → HTTPS redirects, HSTS, `location = /auth` (trailing-slash normalization), health routes, timeouts, other headers, and multi-proxy topologies must be configured/tested separately. Do not copy `proxy_pass` path stripping verbatim if the real backend already mounts `/auth`.

Points to check on deployment:

- Browser `https://login.example.test/auth/login` maps to `/login` at the backend.
- After processing `X-Forwarded-Prefix`, the app generates public URLs with **exactly one `/auth`**.
- Every external `Location` uses HTTPS/public host, never leaking `http://app:8080`.
- Cookies returned to the browser have matching `Domain`/`Path`. `__Host-SESSION` requires `Path=/` and no `Domain`.
- Edge ignores `Forwarded` or `X-Forwarded-*` sent by Internet clients; if intermediate trusted proxies exist, define clearly where sanitization occurs.
- Backend port is not public, and proxy-to-backend network traffic is protected per threat model.

### Why Adding Only `X-Forwarded-Proto` May Not Suffice

`X-Forwarded-Proto=https` fixes only the scheme. The app can still see:

```text
host = app:8080          (wrong host)
port = 8080             (wrong port)
contextPath = ""        (missing /auth)
```

Handle **public host, port, and prefix together** per architecture. You can use `Forwarded: proto=https;host=login.example.test` or `X-Forwarded-*` supplied by a trusted proxy; do not send conflicting header sets simultaneously.

**Never enable wildcard Host/redirect logic** or construct absolute URLs from unverified `Host` or `X-Forwarded-Host`. Use public-origin allowlists and proxy sanitization.

## 12. OAuth2/OIDC: When Cookies Are Lost, `state` and `nonce` Can Be Lost Too

In a typical OAuth2 Authorization Code flow:

```text
Browser -> /auth/oauth2/authorization/demo
    |
    +-- Spring creates OAuth2AuthorizationRequest
    |   and saves correlation state to repository (usually HttpSession)
    |
    v
302 -> https://idp.example.test/authorize?...&state=...
    |
    v
User authenticates with IdP
    |
    v
Callback -> https://login.example.test/auth/login/oauth2/code/demo
               |
               +-- Did browser send the SAME session cookie?
               +-- Did application find the authorization request?
               +-- Does request state match?
               +-- Does Redirect URI match IdP registration?
               +-- Does OIDC validation (issuer/signature/nonce...) pass?
```

If the session cookie does not arrive at the callback, the backend cannot find the original `OAuth2AuthorizationRequest`. From a user's perspective, this is easily misdiagnosed as "wrong client secret" or "broken IdP".

### Error Types to Distinguish

| Error | When It Appears | What to Check |
| --- | --- | --- |
| `redirect_uri_mismatch` | IdP rejects authorize request before callback | Sent `redirect_uri` vs client registration, proxy scheme/host/prefix |
| `authorization_request_not_found` or missing correlation/state | Callback hits app, yet request state is gone | Cookie, session store, SameSite, session rotation, callback host/path, state repository |
| `invalid_state_parameter` | Callback `state` mismatches or is missing | Initiation/callback sharing session, CSRF/state tampering, expired session |
| Callback `404`/`403` | Wrong route/proxy/security matcher or CSRF/method mismatch | Path rewrite, callback route, `SecurityFilterChain`, CSRF policy |
| Login loop after callback | Authentication succeeded yet session failed to persist | Post-login `Set-Cookie`, Request `Cookie`, `SecurityContextRepository`, multiple pods |

Depending on version, handler, and IdP, error codes/names may vary. Do not conclude from one exception string alone; inspect Network traces and safe server metrics.

### Why `form_post` Differs From `GET`

`response_mode=form_post` makes the IdP **POST** the callback cross-site. If the app stores the authorization request in `HttpSession` while the browser omits the `SameSite=Lax` session cookie, Spring cannot recover the state and the callback fails. Fixes must satisfy cookie policy, CSRF/callback handling, and OIDC correlation; never disable state validation or turn every cookie cross-site unconditionally.

## 13. Cookie Is Sent, Yet Spring Sees Anonymous

This is the **server-side** branch, no longer "SameSite dropped the cookie". Check:

1. Does the session cookie name read by the backend match what the browser sends?
2. Does the Servlet container find an `HttpSession` for that ID?
3. Did the session expire via idle timeout/absolute limit or logout?
4. After authentication, was context saved in the right `SecurityContextRepository`?
5. Session fixation protection rotated the ID: is the client sending the **new** ID or the old one?
6. Request 1 hit pod A, request 2 hit pod B: is Spring Session/shared store or sticky routing configured right?
7. Do all pods share the same cookie name/path and compatible session serializer/schema?
8. If using `SessionCreationPolicy.STATELESS` or a bearer resource server, should `HttpSession` even be expected?
9. Did the `SecurityFilterChain` matcher change between login and protected API, sending request 2 to a stateless chain ignoring sessions?
10. Does a custom filter write authentication into `SecurityContextHolder` without persisting context?

### Spring Security 6: Explicit Save in Custom Flows

Spring Security 6's `SecurityContextHolderFilter` defaults to **reading** context from the repository and does not automatically save manual modifications made by the app. If a custom controller calls `AuthenticationManager.authenticate` and only runs:

```java
SecurityContextHolder.getContext().setAuthentication(authentication);
```

then the next request may remain anonymous. In custom flows, create/set the context and call repository save when appropriate:

```java
// Spring Security 6.x Servlet fragment, inside a verified auth flow:
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
```

`securityContextRepository` must be the instance configured consistently with `SecurityFilterChain`; `request`/`response` are valid-lifecycle Servlet objects. This is **not** a complete login controller — you still need credential verification, session strategy, CSRF, and failure handling. Standard Spring Security form login handles this in the framework; avoid adding duplicate saves unnecessarily.

### Multi-Instance

```text
Request 1: Pod A -> creates session S123 in Pod A RAM
Request 2: Pod B -> receives Cookie S123, yet Pod B RAM lacks S123
=> Pod B treats as anonymous; User sees intermittent login loss
```

Fix with Spring Session (Redis/JDBC) or a proper shared-session architecture; sticky sessions are only a limited routing tactic and do not replace revocation/failover when scaling. **Do not try to fix by widening the cookie `Domain` to pods**: pods are backend servers, not browser hostnames.

## 14. 15-Minute Browser/Proxy/Backend Investigation Checklist

### Step 1 — Capture a Minimal Flow

- Use a test account and a dedicated browser profile.
- Enable **Preserve log** in Network.
- Perform one login: record method, URL, and HTTP status/`Location` across every redirect.
- Note **presence/absence** of `Set-Cookie` and Request `Cookie`; never copy secret cookie values.
- Pinpoint the first request that loses authenticated state or leaves the public origin.

### Step 2 — Check Browser Cookie Acceptance

- Inspect DevTools Cookies/Application and blocked reasons.
- Verify `Secure` with HTTPS, `HttpOnly`, `SameSite`, `Domain`, `Path`, `Expires`/`Max-Age`, `__Host-` rules.
- Are there duplicate cookies with the same name on two paths/domains? Did any response clear the cookie with `Max-Age=0`?
- If inside a third-party context/iframe, check browser privacy restrictions.

### Step 3 — Check Request Cookies

- Right host? E.g., `login.example.test` vs `app.example.test`.
- Right HTTPS scheme? Any accidental redirect to HTTP?
- Does the cookie `Path` cover the request path?
- Did `SameSite` or `fetch` credentials/CORS block a cross-site POST/iframe/fetch?
- Did the session ID rotate after login while the frontend kept the old ID?

### Step 4 — Check Public URL and Forwarded Headers

- Do `Location` and OAuth `redirect_uri` contain internal `app:8080`, HTTP, or a missing prefix?
- Compare `Forwarded` or `X-Forwarded-Proto/Host/Port/Prefix` **written by the trusted proxy**; never read spoofed raw headers as proof.
- Check `server.forward-headers-strategy` and Tomcat context-root redirects.
- Determine how many times the reverse proxy strips/mounts prefixes.

### Step 5 — Check Session and Callback

- If the browser **sent the cookie**, does the backend find a valid session?
- Do state repository, CSRF, session persistence, expiry/logout/session store/shared Redis line up?
- Does the IdP client registration have the exact matching public redirect URI?
- Across multiple pods, are sessions consistent and routed through the right security chain?

**Minimal sufficient evidence:** one scrubbed request–response trace with status + `Location`, scrubbed cookie attributes, browser blocked reason, and public/internal path mapping. No need to share secrets with teammates or support.

## 15. Using `curl` Properly, and Its Limits

On a machine with proper TLS trust, inspect response headers:

```bash
curl -sS -D - -o /dev/null https://login.example.test/auth/login
```

To trace redirects **without leaking secrets**, inspect public GET URLs in a test environment; avoid printing tokens/OAuth authorization codes/`state` to logs or chat. If sending a login POST, never put passwords in command history or share raw traces.

**Never use `curl -k` as a TLS fix**: it disables certificate verification and hides real bugs. Likewise, `curl` has a cookie jar yet **is not a browser**, so it does not fully simulate `SameSite`, third-party cookie blocking, cookie-prefix enforcement, or user-gesture restrictions.

In Windows PowerShell 5.1, use `curl.exe` instead of the `curl` alias for standard curl syntax.

### Pitfall of Testing Directly Against the Backend

Calling `http://app:8080/login` over the internal network differs from the public browser flow. It lacks TLS, public `Host`/prefix, and browser cookie policies. A "backend returns 200" result **does not prove** public OAuth/cookies work. To debug, compare edge and backend traffic with scrubbed metadata without bypassing network trust boundaries.

## 16. Plain Java 17: Simulating Why Cookies Are Rejected or Not Sent

Standalone runnable example on **JDK 17+**. It is **not** a full RFC 6265 implementation and does not replace browser DevTools. It models the most error-prone rules: `__Host-`, `Secure`, host/path, explicit `SameSite=Lax`, and public callback URLs.

Create **`CookieProxyDiagnosisDemo.java`**:

```java
import java.util.*;

public class CookieProxyDiagnosisDemo {
    enum SameSite { STRICT, LAX, NONE }

    record Cookie(String name, String originHost, String path,
                  boolean secure, boolean httpOnly, boolean hasDomain,
                  SameSite sameSite) {}

    record Request(String scheme, String host, String path,
                   boolean crossSite, boolean topLevelNavigation,
                   String method) {}

    static boolean canStore(Cookie c, boolean httpsOrigin) {
        if (c.secure() && !httpsOrigin) return false;
        if (c.sameSite() == SameSite.NONE && !c.secure()) return false;
        if (c.name().startsWith("__Host-")) {
            if (!httpsOrigin || !c.secure()
                    || !"/".equals(c.path()) || c.hasDomain()) {
                return false;
            }
        }
        return true;
    }

    static boolean pathMatches(String cookiePath, String requestPath) {
        if (cookiePath.equals(requestPath)) return true;
        if (!requestPath.startsWith(cookiePath)) return false;
        return cookiePath.endsWith("/")
                || requestPath.charAt(cookiePath.length()) == '/';
    }

    static boolean sends(Cookie c, Request r) {
        if (c.secure() && !"https".equals(r.scheme())) return false;
        if (!c.originHost().equalsIgnoreCase(r.host())) return false;
        if (!pathMatches(c.path(), r.path())) return false;

        if (!r.crossSite()) return true;
        if (c.sameSite() == SameSite.STRICT) return false;
        if (c.sameSite() == SameSite.LAX) {
            return r.topLevelNavigation()
                    && ("GET".equals(r.method())
                        || "HEAD".equals(r.method()));
        }
        return true; // NONE, assuming browser privacy policy allows
    }

    static String publicCallback(String proto, String host, String prefix,
                                 String callbackPath) {
        if (!"https".equals(proto)
                || !"login.example.test".equals(host)) {
            throw new SecurityException("Untrusted public origin");
        }
        String safePrefix = prefix.endsWith("/")
                ? prefix.substring(0, prefix.length() - 1) : prefix;
        return proto + "://" + host + safePrefix + callbackPath;
    }

    public static void main(String[] args) {
        Cookie session = new Cookie(
                "__Host-SESSION", "login.example.test",
                "/", true, true, false, SameSite.LAX);

        System.out.println("validHostCookie="
                + canStore(session, true));

        System.out.println("sameSiteHttps=" + sends(session,
                new Request("https", "login.example.test", "/auth/home",
                        false, false, "GET")));

        System.out.println("httpBlocked=" + !sends(session,
                new Request("http", "login.example.test", "/auth/home",
                        false, false, "GET")));

        System.out.println("crossSitePostBlocked=" + !sends(session,
                new Request("https", "login.example.test",
                        "/auth/login/oauth2/code/demo",
                        true, true, "POST")));

        System.out.println("crossSiteTopGetAllowed=" + sends(session,
                new Request("https", "login.example.test",
                        "/auth/login/oauth2/code/demo",
                        true, true, "GET")));

        System.out.println("wrongHostBlocked=" + !sends(session,
                new Request("https", "other.example.test", "/auth/home",
                        false, false, "GET")));

        Cookie pathCookie = new Cookie(
                "SESSION", "login.example.test",
                "/auth", true, true, false, SameSite.LAX);

        System.out.println("wrongPathBlocked=" + !sends(pathCookie,
                new Request("https", "login.example.test", "/portal/home",
                        false, false, "GET")));

        Cookie badPrefix = new Cookie(
                "__Host-SESSION", "login.example.test",
                "/", true, true, true, SameSite.LAX);

        System.out.println("hostPrefixRejectsDomain="
                + !canStore(badPrefix, true));

        Cookie badNone = new Cookie(
                "SESSION", "login.example.test",
                "/", false, true, false, SameSite.NONE);

        System.out.println("noneNeedsSecure="
                + !canStore(badNone, true));

        String external = publicCallback(
                "https", "login.example.test",
                "/auth", "/login/oauth2/code/demo");
        String internal =
                "http://app:8080/login/oauth2/code/demo";

        System.out.println("publicCallback=" + external);
        System.out.println("internalDoesNotMatch="
                + !external.equals(internal));
    }
}
```

Compile and run:

```bash
javac CookieProxyDiagnosisDemo.java
java CookieProxyDiagnosisDemo
```

**Deterministic stdout:**

```text
validHostCookie=true
sameSiteHttps=true
httpBlocked=true
crossSitePostBlocked=true
crossSiteTopGetAllowed=true
wrongHostBlocked=true
wrongPathBlocked=true
hostPrefixRejectsDomain=true
noneNeedsSecure=true
publicCallback=https://login.example.test/auth/login/oauth2/code/demo
internalDoesNotMatch=true
```

### Meaning and Simulation Limits

- `validHostCookie=true` because `__Host-` has `Secure`, `Path=/`, no `Domain`, and was set over HTTPS.
- `httpBlocked=true` because `Secure` cookies are not sent over plain HTTP.
- `crossSitePostBlocked=true` models only **explicit `SameSite=Lax`** on cross-site POST; it does not simulate some browsers' Lax-by-default grace window or complex redirect chains.
- `crossSiteTopGetAllowed=true` illustrates that top-level cross-site GETs can carry Lax cookies.
- `wrongHostBlocked` and `wrongPathBlocked` remind you that host-only/`Path` checks occur **in the browser before sending**.
- `hostPrefixRejectsDomain=true` shows `__Host-` rejects `Domain`.
- `noneNeedsSecure=true` shows `SameSite=None` without `Secure` is rejected.
- `publicCallback` is the URL to register at the IdP when the proxy strips the prefix. It does not actually parse forwarded headers.
- The code intentionally **does not** simulate the public suffix list, schemeful site calculation, `Expires`/`Max-Age`, full cookie `Domain` matching, `Set-Cookie` parsing, third-party blockers, CORS, `HttpOnly`, cookie jars, or OAuth2 protocol flows. `crossSite` is a test-supplied input, not auto-classified.
- The program's output **does not prove** your Spring Boot or Nginx config is right; browser/HTTP integration tests are needed.

## 17. Testing With Spring Boot and Browsers: Check Each Layer, Never Mistake MockMvc for a Browser

### Unit Tests for URL Generation

If the app builds absolute URLs itself, test against a **public origin allowlist** and exact public prefix. With Spring Boot and forwarded headers, use integration tests hitting a real proxy or a test environment with `ForwardedHeaderFilter`. Merely passing a fake `X-Forwarded-Host` header in a unit test calling code directly does not prove production resists header spoofing.

An architectural test spec:

```text
Given public URL:
    https://login.example.test/auth/login
And backend URL:
    http://app:8080/login
And trusted proxy headers:
    X-Forwarded-Proto: https
    X-Forwarded-Host: login.example.test
    X-Forwarded-Prefix: /auth

When OAuth authorization request is issued:
    redirect_uri must be
    https://login.example.test/auth/login/oauth2/code/demo
And response Location must contain no internal host/port.
```

### Browser Tests for Cookies

MockMvc does not enforce browser `SameSite`/third-party privacy rules; use Playwright/Selenium or a real browser to verify:

- Is `Set-Cookie` accepted by the browser?
- Do cookie `Secure`/`Domain`/`Path` match the public URL?
- Is `SameSite=Lax` sent on top-level GET callbacks?
- Is `SameSite=Lax` omitted on cross-site POST callbacks?
- Does the browser reject `SameSite=None` lacking `Secure`?
- Does cross-origin `fetch` send credentials and receive a valid CORS allowlist response?
- Are SSO cookies and app session cookies scoped separately?
- Do host/prefix behind the proxy produce the right redirect URI?

### Integration Tests for Server Sessions

In Spring Security Servlet, `MockMvc` and `spring-security-test` can verify request state with `MockHttpSession`, yet you should not assert browser cookie-jar rules from MockMvc alone:

```java
// Test fragment inside a @SpringBootTest + @AutoConfigureMockMvc class
// with MockMvc injected and login form/users configured.
MvcResult result = mvc.perform(formLogin()
        .user("alice").password("test-password"))
        .andExpect(authenticated())
        .andReturn();

MockHttpSession session =
        (MockHttpSession) result.getRequest().getSession(false);

assertNotNull(session);

mvc.perform(get("/private")
        .session(session))
        .andExpect(authenticated());
```

Project imports: `org.springframework.test.web.servlet.MvcResult`, `org.springframework.mock.web.MockHttpSession`, `org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin`, `org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated`, `org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get`, and JUnit `assertNotNull`. This is a **test fragment**, not a standalone app; `/private` and the test user must exist in the fixture.

**Caution:** a MockMvc session test does not prove a `SameSite` cookie is sent by the browser on an IdP callback; run an E2E public-URL test. Conversely, testing browser login alone does not catch an inconsistent backend session store across pods.

## 18. "Quick Fixes" That Usually Degrade Security

**1. Setting all cookies to `SameSite=None`.** Increases CSRF risk and can still face third-party cookie blocking. Change only per flow, preserve CSRF/state/nonce, and verify in a browser.

**2. Disabling `csrf()` completely.** Login/session cookies still carry CSRF risk, especially for form POSTs and cross-origin requests. Fix the CSRF repository, token transport, or protocol callback matcher instead of disabling broadly.

**3. Dropping `Secure` so cookies work over HTTP behind a proxy.** Confuses **proxy→backend** with **browser→public edge**. Public browsers must use HTTPS; configure `Secure` properly even over trusted backend HTTP.

**4. Removing `HttpOnly` so the frontend can see `SESSION`.** `HttpOnly` blocks JS cookie reads by design. The frontend checks login state via a server API; it needs no raw session secret.

**5. Enabling `server.forward-headers-strategy=framework` without sanitizing Internet headers.** Attackers can trick the app into issuing redirects/absolute URLs to spoofed hosts; edge stripping/rewriting and closing direct backend ports are required.

**6. Changing IdP `redirect_uri` to a wildcard.** Breaks redirect/callback boundaries. Register exact public URLs and fix proxy/request schemes.

**7. Setting `Domain=example.test` so all apps share a session.** Expands scope and risk of session fixation/subdomain compromise; prefer host-only cookies.

**8. Keeping `__Host-SESSION` while setting `Path=/auth`.** Browsers reject the prefix. Use `Path=/` with no `Domain`, or intentionally change cookie naming/policy.

**9. Configuring both `context-path=/auth` and `forwarded-prefix=/auth` after proxy stripping.** Easily produces `/auth/auth` or 404. Pick one path model and test it.

**10. Disabling session fixation protection to keep `JSESSIONID` constant.** May mask symptoms briefly while opening a fixation vulnerability. Track the new cookie after login.

**11. Using `SessionCreationPolicy.STATELESS` with form login expecting auto-saved sessions.** Decide stateful vs stateless architecture; fix the security chain/context persistence.

**12. Raising session timeout to infinite.** Does not cure browser-rejected cookies or wrong public URLs while increasing session-theft risk.

**13. Trusting client-sent `Host`/`X-Forwarded-Host`.** Enables host-header poisoning; use allowlists and trusted proxy rewrites.

**14. Treating `curl -k` success as valid TLS.** `-k` skips certificate validation. Browsers and IdPs will still reject bad certs.

**15. Testing only a single pod.** In-memory sessions work on one pod yet fail once a load balancer routes requests to another pod.

**16. Enabling CORS wildcard with credentials.** Browsers reject it and it signals overly broad trust. Use an exact origin allowlist.

**17. Logging cookies, authorization codes, or `state`.** Creates session hijacking or OAuth replay risks. Redact from edge through app/observability.

**18. Setting cookies on the internal backend hostname.** Browsers cannot reach backend hostnames; issue cookies on the valid public host response.

**19. Assuming an `HttpOnly` cookie is missing because `document.cookie` is empty.** Check Network/Application tabs, not JS.

**20. Blaming the IdP for every OAuth `state` failure.** State is often lost because the session cookie missed the callback or the state repository lived on another pod.

## 19. Diagnostic Test Matrix

| Case | Input / Context | Expected Outcome |
| --- | --- | --- |
| `Secure` cookie over HTTPS | Public HTTPS URL | Browser accepts and sends within scope |
| `Secure` cookie over public HTTP | HTTP URL | `Secure` cookie is not sent |
| `__Host-` cookie with `Domain` | Invalid prefix `Set-Cookie` | Browser rejects |
| `__Host-` cookie `Path=/auth` | Wrong path for prefix | Browser rejects |
| `SameSite=None` missing `Secure` | Invalid response header | Browser rejects |
| Explicit `SameSite=Lax`, cross-site top-level GET | IdP GET callback | Sends session if rest of scope is valid |
| Explicit `SameSite=Lax`, cross-site POST | IdP `form_post` | Normally omits session |
| `SameSite=Strict`, navigation from external site | Top-level navigation | Not sent in cross-site context |
| Host-only cookie wrong host | `login.example.test` → `other.example.test` | Not sent |
| Cookie `Path=/auth` yet request `/portal` | Path mismatch | Not sent |
| Expired cookie / `Max-Age=0` | Logout/expiry response | Browser deletes or stops sending |
| Cross-origin `fetch` missing credentials | SPA → different-origin API | Does not attach cookies under default fetch |
| CORS credentials and wildcard origin | Invalid response policy | Browser rejects credentialed CORS response |
| Proxy sends only `X-Forwarded-Proto` | Internal host/prefix still wrong | Redirect URI still wrong; add trusted mapping |
| Proxy strips `/auth`, app receives prefix | OAuth authorization redirect | Public URI has `/auth` once |
| Proxy does not strip, app `context=/auth` | OAuth callback | No double prefix |
| Attacker injects `X-Forwarded-Host` | Internet request | Edge strips/rewrites; URL is not poisoned |
| IdP registered URL differs from computed URL | OAuth login | Exact mismatch detected |
| Cookie sent yet session expired | Protected request | Anonymous/redirect per policy |
| Custom login omits context save | Request right after login | Detected/fixed with explicit save |
| 2 pods keeping only in-memory sessions | Alternating requests across pods | Inconsistency detected; use shared store |
| Spring Session Redis | 2+ pods and logout | Session exists/revoked consistently |
| `Set-Cookie` header only on 302 | Preserve log | `Set-Cookie` found on intermediate response |
| Logout rotates/deletes session | GET request after logout | Old cookie does not authenticate |
| Browser third-party restriction | OIDC in iframe | May be blocked even with `None`; use proper flow |
| CSRF POST with session cookie | Missing/bad CSRF token | Rejected per policy without disabling CSRF |
| Logs/metrics/traces | Security QA | No leaked cookies, codes, tokens, or passwords |

## 20. Final Checklist for On-Call Operators

1. Did you identify the **first request** that lost authenticated state rather than looking at a generic "login loop"?
2. Does Network Preserve log capture every `302`, `Set-Cookie`, and `Location`?
3. Did the browser store the cookie? If not, what is the DevTools blocked reason?
4. Does the stored cookie have the right `Domain`/host, `Path`, `Secure`, `SameSite`, `__Host-` prefix, and `Expires`?
5. Does the browser actually send the cookie on the key request, or is it merely sitting in Storage?
6. Is the flow a cross-site GET, cross-site POST, iframe, or cross-origin `fetch`?
7. Do you distinguish **origin** vs **site**, and avoid using CORS in place of CSRF?
8. Does `SameSite=None` (if needed) include `Secure` and still comply with browser privacy policies?
9. Is the app configured for forwarded headers **behind a trusted/sanitized edge**?
10. Do external scheme/host/port/prefix match the actual `redirect_uri` used?
11. Is the proxy stripping the path or is the backend setting context-path? Are there duplicate/missing prefixes?
12. Does the cookie sent to the backend resolve the session across **every pod**?
13. Does Spring Security 6 custom login persist `SecurityContext` in the right repository?
14. Did the session ID rotate after login for fixation protection, and is the browser using the new ID?
15. Are OAuth `state`/authorization requests stored and read back in the same session?
16. Does the IdP client registration use an exact public redirect URI, not a wildcard?
17. Was the user login flow tested in a real browser + real proxy, not only MockMvc/`curl`?
18. Have all debug logs/headers been scrubbed of session IDs, codes, passwords, and tokens?
19. Have cookie/forwarded-header changes undergone security review against CSRF/host poisoning?
20. Have logout, session expiry, multiple tabs, mobile browsers, and multi-instance routing been tested?

### Official References

- Spring Boot 3.5 — Running Behind a Front-end Proxy Server: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Boot 3.5 — Servlet SameSite cookies: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5 — Common Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
- Spring Framework 6.2 — ForwardedHeaderFilter and security: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html
- Spring Security 6.5 — Session Management, SecurityContext persistence: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security 6.5 — Session Management FAQ: https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/faq.html
- Spring Security 6.5 — OAuth2 Login: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/core.html
- MDN — Set-Cookie, Secure/SameSite/__Host- rules: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie
- MDN — Using HTTP Cookies: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP — Cross-Site Request Forgery Prevention: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html

**Conclusion:** when login "loses the session", prove **cookie issued, browser stored, browser sent, and server recognized session** in order. In parallel, verify the **public scheme/host/port/prefix** supplied by the proxy for OAuth2 callbacks and redirects. Fix only the exact pipeline segment backed by evidence; never disable `Secure`, `HttpOnly`, CSRF, or OAuth state validation, or open trust headers to mask symptoms.
