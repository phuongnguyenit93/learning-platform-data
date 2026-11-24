# Relationship Between CORS, SameSite Cookies, CSRF, and HTTPS in Spring Security Servlet

> **Scope:** Spring Security 6.x on the Servlet stack (Spring MVC/Spring Boot 3.x; Java 17+). This lesson distinguishes four mechanisms that appear together in web applications using session cookies: **CORS**, **SameSite**, **CSRF**, and **HTTPS**. They solve different security questions and must be applied together depending on architecture.

## 1. Objectives and the Big Picture

After this lesson, you will be able to explain why a frontend `https://app.example.com` calling an API `https://api.example.com` needs CORS configuration yet can still use `SameSite=Lax` cookies; why CORS does not replace CSRF protection; and why HTTPS does not by itself prevent browsers from sending forged requests.

| Mechanism | Question it answers | Where enforced | Limits to remember |
| --- | --- | --- | --- |
| **CORS** (Cross-Origin Resource Sharing) | Can JavaScript from origin A read the response from origin B? For requests needing preflight, does the server allow that method/header? | Server declares policy via HTTP headers; **browser** checks and enforces | CORS does not block all state-changing requests; does not authenticate users. |
| **SameSite Cookie** | Should the browser attach the cookie in this same-site/cross-site context? | Browser selects cookies to send | SameSite does not verify POST intent, and does not protect against **same-site** attacker subdomains. |
| **CSRF protection** | Does a request using automatically attached credentials carry hard-to-forge proof from outside? | Server, e.g., `CsrfFilter` in Spring Security | CSRF tokens do not replace authentication/authorization or prevent XSS. |
| **HTTPS/TLS** | Is the transport channel encrypted, integrity-protected, and TLS-endpoint authenticated? | Client, TLS server/proxy | HTTPS does not prove a request came from intentional user action. |

Do not conclude "enabling one layer means the other three aren't needed." For example, a POST carrying a session cookie over HTTPS is still a CSRF target if a browser is tricked by another page into sending the request and the server only checks the cookie.

## 2. How Does Origin Differ from Site?

### 2.1 Origin: scheme, host, and port

Two URLs are considered **same-origin** when they share the same **scheme** (`https`/`http`), **host**, and **port** (after normalizing the respective default port).

- `https://app.example.com/home` → `https://app.example.com/api`: **same-origin**, even though the path differs.
- `https://app.example.com` → `https://api.example.com`: **cross-origin**, because the host differs.
- `https://app.example.com` → `https://app.example.com:8443`: **cross-origin**, because the port differs.
- `https://app.example.com` → `http://app.example.com`: **cross-origin**, because the scheme differs.

CORS is bound to **origin**. Same-origin browsers can call APIs within that origin without needing the server to return CORS headers.

### 2.2 Site: scheme and registrable domain

Under the **schemeful same-site** model of modern browsers, a "site" is determined by **scheme + registrable domain** (typically eTLD+1 per the Public Suffix List), ignoring port and usually ignoring subdomains. Do not compute this naively by taking the last two hostname labels, since a public suffix can have multiple levels.

- `https://app.example.com` and `https://api.example.com`: **cross-origin yet same-site**.
- `https://app.example.com` and `https://api.other-example.net`: **cross-origin, cross-site**.
- `https://app.example.com` and `http://api.example.com`: **cross-site** under schemeful same-site.
- Two HTTPS URLs on the same host with different ports: **cross-origin, same-site**.

| Frontend → API scenario | CORS? | SameSite? | CSRF when using cookies? |
| --- | --- | --- | --- |
| `https://app.example.com` → `https://app.example.com/api` | No CORS needed for same-origin fetch. | Cookie is eligible for same-site. | Still needed for POST/PUT/PATCH/DELETE. |
| `https://app.example.com` → `https://api.example.com` | Needed if JS reads cross-origin responses. | Same site; `Lax` may still be sent. | Still needed, because cookies attach automatically. |
| `https://app.example.com` → `https://api.other-example.net` | Needed. | Cross-site; `Lax/Strict` normally do not send cookies in fetch. | If API uses cross-site cookies, still need CSRF and third-party cookie policy evaluation. |
| `https://app.example.com` → `http://api.example.com` | Cross-origin, though mixed content is also an issue. | Schemeful cross-site. | HTTPS/Secure/mixed-content must be resolved first. |

**Same site does not mean shared cookies.** Cookies also have `Domain` or host-only attributes, `Path`, `Secure`, `HttpOnly`, and expiration. For example, an API at `api.example.com` can issue a host-only session cookie for the API; that cookie is sent to the API when conditions are met, even when the frontend is on another subdomain. Cookies of `app.example.com` are not automatically sent to `api.example.com`.

## 3. Processing Sequence of a Request with Cookies

Suppose a user logs into an API using a session cookie; frontend JavaScript on another origin calls the API.

~~~text
JavaScript at https://app.example.com
    |
    +-- Browser determines cross-origin and same-site/cross-site
    |     +-- Identifies matching cookies: Domain/Path/Secure/SameSite
    |     +-- Evaluates fetch credentials mode
    |
    +-- If preflight is required, sends OPTIONS to API
    |     +-- CORS on server checks Origin, method, headers
    |     +-- OPTIONS normally carries no session cookie
    |
    +-- Actual request (GET/POST/...)
          |
          +-- CORS integration on server
          +-- CsrfFilter: validates token for unsafe methods
          +-- Authentication + Authorization
          +-- Controller (if permitted)
          |
          +-- Response includes CORS headers when origin is allowed
                   |
                   +-- Browser decides whether JS may read response
~~~

Not every request has a preflight, and the browser may block even before the actual request step (for example mixed content). Yet once a request reaches the controller and mutates data, **blocking JS from reading the response via CORS does not roll back that mutation**. That is why CORS must never be used as the sole CSRF defense.

## 4. What Does CORS Control?

### 4.1 Origin and Key HTTP Headers

A cross-origin client may send `Origin: https://app.example.com`. An API may allow returning:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

For requests needing preflight, the browser sends `OPTIONS` before sending the actual request:

~~~http
OPTIONS /api/preferences HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

If accepted, the preflight response may include:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE, OPTIONS
Access-Control-Allow-Headers: content-type,x-csrf-token
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Illustrative example; status and header order/casing may differ depending on Spring Framework/proxy. `Content-Type: application/json` and custom header `X-CSRF-TOKEN` commonly trigger preflight in cross-origin fetch.

### 4.2 Credentialed Requests Have Specific Conditions

To have JS send cookies to a **cross-origin** API, the client normally must set `credentials: "include"`; `fetch` defaults to `"same-origin"`, so it does not send cookies to a cross-origin API even when same-site. For credentialed responses, the server must return a **specific** origin, and must not use `Access-Control-Allow-Origin: *` with `Access-Control-Allow-Credentials: true`.

CORS allows JavaScript to consume the response yet **cannot force cookies to be sent** if `Secure`, `SameSite`, `Domain`, `Path`, or the browser already filtered the cookie out. Conversely, never grant `Access-Control-Allow-Credentials: true` to all Origins by arbitrarily reflecting the Origin value received from the client.

Spring Security needs CORS to handle preflight before authentication filters that might reject `OPTIONS`: preflight normally **carries no session cookie**. When a `CorsConfigurationSource` bean is present, `http.cors(...)` is the right integration in the Servlet filter chain.

### 4.3 Why Isn't Blocking Response Reading Enough to Stop CSRF?

An attacker page can construct a plain HTML form:

~~~html
<form action="https://api.example.com/account/email" method="post">
  <input type="hidden" name="email" value="attacker@example.net">
  <button type="submit">Submit</button>
</form>
~~~

This kind of form POST **needs no CORS preflight**. The browser can send the request and, depending on SameSite/cookie context, attach credentials. The attacker may **not be able to read** the response, yet if the server only checks the cookie without checking CSRF/Origin, the state change may have already occurred. This is a conceptual example; the endpoint is illustrative only, not an existing system.

CORS sometimes blocks requests containing custom headers or JSON thanks to preflight, yet forms can use content types that browsers allow sending directly. Therefore do not use CORS to replace `CsrfFilter`.

## 5. SameSite Cookies: Lax, Strict, None

| Value | Typical behavior | Limitations |
| --- | --- | --- |
| `SameSite=Strict` | Sends cookies only in same-site contexts. | Navigating into the app from an external website may omit the cookie on initial navigation; sibling subdomains may still be same-site. |
| `SameSite=Lax` | Sends in same-site contexts and certain top-level **cross-site navigations with safe methods**, mainly GET. | Cross-site top-level GET can still carry cookies; never design GET endpoints to mutate state. |
| `SameSite=None; Secure` | Allows cookies in cross-site contexts when the browser and cookie policy permit. | `Secure` is mandatory in modern browsers; third-party cookie blocking can still prevent cookies from being sent. |

**Common confusion:** frontend `https://app.example.com` and API `https://api.example.com` are **same-site**; the API host's session cookie with `SameSite=Lax` is still eligible to be sent when the frontend fetches the API, provided host/path, HTTPS, and `credentials: "include"` match. **You do not need `SameSite=None` merely because the two hosts are different subdomains.**

Conversely, frontend `https://app.example.com` calling `https://api.other-example.net` is cross-site; `SameSite=Lax/Strict` normally blocks cookies in cross-site fetch. If you must rely on cross-site cookies, `SameSite=None; Secure` is required and third-party cookie restrictions must be verified. Do not blindly change SameSite to "fix CORS".

### Risks from Sibling Subdomains

If `https://evil.example.com` is controlled by an attacker, it and `https://api.example.com` are **cross-origin yet same-site**. SameSite=Lax/Strict **does not by itself prevent** requests from that subdomain from carrying cookies to the API. CORS can stop JS from reading the response, yet does not eliminate all requests with side effects. CSRF tokens, appropriate Origin/Fetch Metadata checks, and authorization each still have their own role.

Keep session cookies **host-only** when sharing across subdomains is unnecessary. Setting an overly broad `Domain=.example.com` causes many subdomains to receive the cookie, expanding the attack surface; host-only reduces this risk, though it also does not replace CSRF.

## 6. CSRF: Proof for State-Changing Requests

Browsers automatically attach valid session cookies for a URL; that is an "ambient credential". Attackers try to make the browser send POSTs with the victim's real cookie. A CSRF token is an unpredictable value that the legitimate application additionally sends via a hidden form field or header; the server compares it against the token tied to the valid session/repository.

In Spring Security Servlet, `CsrfFilter` protects unsafe methods by default: typically POST/PUT/PATCH/DELETE. GET/HEAD/OPTIONS/TRACE methods are not required to have a token under the default matcher because they are assumed safe. **Never use GET to transfer money, change settings, delete resources, or cause side effects.**

- **CORS does not replace CSRF**: blocking response reading alone does not stop all form POSTs.
- **SameSite does not replace CSRF**: especially dangerous with compromised same-site subdomains and GET endpoints with side effects.
- **HTTPS does not replace CSRF**: a forged request can still travel over a perfectly encrypted HTTPS channel.
- **CSRF does not replace authorization**: even with a valid token, a user without permission to modify a resource must still be rejected.
- **CSRF does not replace XSS defense**: malicious scripts on the same origin can read the token and send valid requests.
- **JSON does not automatically protect against CSRF**: the credential mechanism and server validation determine risk, not the label "REST API".

If an API uses only `Authorization: Bearer ...` explicitly attached by JS and accepts zero browser-auto-sent credentials, the CSRF model differs from session cookies. However, if session cookies, browser-cached HTTP Basic, refresh cookies, or any auto-sent credential flow remain, CSRF must still be evaluated per endpoint. Do not automatically disable CSRF for the entire application just because it is an SPA.

### Tokens with SPAs and Spring Security 6

Spring Security 6 uses **deferred CSRF tokens** and defaults to **XOR masking** for the exposed token value to mitigate BREACH risks. An SPA can call `GET /api/csrf` to fetch a properly formatted token, then send the `csrf.headerName` header with value `csrf.token` on POST. When the frontend explicitly reads the token, the supplier is materialized; requests not needing a token need not force loading/creating one.

If switching to `CookieCsrfTokenRepository` so JavaScript can read a raw `XSRF-TOKEN` cookie, ensure the server has a request handler compatible with how the client sends the token. A raw cookie token does not always match the default XOR representation on the request attribute.

## 7. HTTPS, Secure Cookies, HSTS, and Proxies

HTTPS encrypts and protects data integrity in transit; the client verifies the server's identity via TLS certificates. It helps protect session cookies and CSRF tokens from eavesdropping/tampering on the wire, yet **does not block forged requests** automatically sent by the browser to an HTTPS API.

Key points in session-based systems:

1. Enable HTTPS consistently for frontend, API, and login/refresh/logout endpoints; avoid mixed content (an HTTPS page calling an HTTP API may be blocked by the browser).
2. Mark session cookies `Secure` so they are sent only over connections considered secure; use `HttpOnly` so JS cannot directly read the session cookie. `HttpOnly` does not stop the browser from sending cookies automatically.
3. Use **HSTS** on HTTPS endpoints/edge where appropriate so browsers prefer HTTPS after caching the policy; evaluate `includeSubDomains` carefully.
4. With TLS termination at a reverse proxy, trust only forwarded headers set by a trusted proxy; secure the proxy → application hop per your threat model. Never unconditionally trust `X-Forwarded-Proto` sent by external clients.
5. If the application uses a separate CSRF cookie, configure that cookie's attributes separately. **Session cookie** attributes do not guarantee another cookie shares the same `SameSite/Secure/HttpOnly`.

Switching scheme from HTTPS to HTTP can also alter schemeful same-site evaluation and trigger `Secure` cookie blocking; never "fix" this by disabling Secure or relaxing SameSite.

## 8. Spring Security Servlet Configuration for Same-Site, Cross-Origin SPA and API

Suppose:

- Frontend: `https://app.example.com`.
- API: `https://api.example.com`.
- Authentication: API session cookie.
- Frontend is permitted to call `/api/**` using fetch with cookies; write requests still require a CSRF token.

### 8.1 SecurityFilterChain and CORS Policy

Here is a `WebSecurityConfig.java` class in a Spring Boot project with `spring-boot-starter-web` and `spring-boot-starter-security` dependencies. This Java snippet requires the Spring runtime/dependencies and is **not** a standalone Java SE program runnable directly with `javac`.

~~~java
package com.example.demo;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .cors(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(
                List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
        cors.setAllowedHeaders(List.of("Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Meaning:

- `.cors(Customizer.withDefaults())` integrates CORS into Spring Security so preflight is processed before authentication requires a session. `CorsConfigurationSource` restricts origins/methods/headers to a whitelist.
- `setAllowedOrigins` takes the **full origin**, e.g., with `https://` and no path. Do not use wildcards or reflect arbitrary Origins when `allowCredentials=true`.
- `setAllowedHeaders` must match custom headers sent by the client. The example uses the default token header `X-CSRF-TOKEN`; if the system uses another name, update it intentionally.
- `csrf(Customizer.withDefaults())` preserves CSRF protection. Do not call `csrf.disable()` just because the SPA communicates over JSON.
- `formLogin(...)` illustrates an application with session authentication. A real system's login flow must be configured to fit the SPA, including redirects, responses, session lifecycle, and re-fetching the CSRF token after authentication changes.
- Policy is bound to `/api/**`; endpoints outside this scope are not automatically granted CORS merely for being on the same host. Open only paths the frontend genuinely needs to access.

### 8.2 Session Cookies Over HTTPS

Example `application.properties` for an HTTPS deployment environment:

~~~properties
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
~~~

These apply to the Servlet session cookie managed by Spring Boot. `SameSite=Lax` can be an appropriate choice for `app.example.com` and `api.example.com` on **same-site HTTPS**; you do not need to switch to `None` just to call an API on another subdomain. Inspect the actual `Set-Cookie` response, Domain/Path, and reverse proxy.

### 8.3 Issuing the CSRF Token When the Frontend Needs It

File `CsrfEndpoint.java` in the Spring MVC application:

~~~java
package com.example.demo;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class CsrfEndpoint {

    @GetMapping("/csrf")
    public CsrfToken csrf(CsrfToken csrfToken) {
        return csrfToken;
    }
}
~~~

The GET endpoint reads the token on demand, triggering deferred loading. Spring Security 6 provides a representation matching the active handler, and the JSON typically includes `headerName`, `parameterName`, and `token`. Since tokens are bound to a session, do not share-cache them across users; configuring `Cache-Control: no-store` is appropriate for the token response. After login/logout or session changes, a fresh token must be fetched.

### 8.4 JavaScript Calling the API with Cookies and CSRF Token

The following JavaScript runs at frontend `https://app.example.com`. It assumes the API has a business endpoint POST `/api/preferences` and session authentication is already validly established. This is an **integration snippet** and will not run standalone without the backend/login.

~~~javascript
const tokenResponse = await fetch(
  "https://api.example.com/api/csrf",
  { credentials: "include", cache: "no-store" }
);
if (!tokenResponse.ok) {
  throw new Error("Cannot obtain CSRF token");
}
const csrf = await tokenResponse.json();

const updateResponse = await fetch(
  "https://api.example.com/api/preferences",
  {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify({ theme: "dark" })
  }
);
if (!updateResponse.ok) {
  throw new Error("Update failed");
}
~~~

Flow: GET token is allowed by CORS → API cookie is stored/sent per browser policy → JSON POST with custom CSRF header typically triggers preflight → actual POST includes cookie and CSRF header → `CsrfFilter` checks before business logic → authentication/authorization steps and controller execute if valid.

The browser needs `credentials: "include"` for cross-origin APIs **even when same-site**. The token header is not a session credential; do not log tokens or place them in URLs. If the server returns a redirect to a cross-origin login page or an error response missing CORS headers, the browser may display a CORS error: inspect redirects and authentication rather than just editing the CORS whitelist.

## 9. Verifying Mechanisms with Realistic Scenarios

### 9.1 Checking Preflight (Server-Side Check Only)

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/preferences" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

A valid configuration is expected to show concrete origin `https://app.example.com`, method `POST`, matching headers, and `Access-Control-Allow-Credentials: true`. Change Origin to `https://untrusted.example.net` to confirm the server does not grant CORS permission arbitrarily. Depending on config, an invalid origin may yield 403 or lack allow headers.

**curl does not enforce SameSite, CORS, or mixed-content policies like a browser.** Use browser DevTools with a real frontend to confirm whether the request sends cookies, whether preflight succeeds, whether POST reaches the server, and whether JS can read the response.

### 9.2 Cases to Test in the Browser / Integration Tests

| Case | What to observe |
| --- | --- |
| Same-origin frontend calls POST with session | No CORS needed; CSRF still blocks POST missing token. |
| Frontend `app.example.com` calls `api.example.com` | CORS returns exact origin; `credentials: include`; valid API cookie can be sent with SameSite=Lax; valid POST includes token. |
| Omit `credentials: "include"` in cross-origin fetch | Session cookie is not sent as expected even if CORS allows; usually treated as unauthenticated. |
| Send POST missing/wrong token with valid cookie | `CsrfFilter` blocks, typically returning HTTP 403; no state mutation occurs. |
| POST with valid token yet user lacks permission | Still must be rejected by authorization; CSRF passing grants no extra permissions. |
| Cross-site form POST from untrusted origin | Does not depend on CORS to stop sending; SameSite may drop cookies, while CSRF must defend if credentials reach the server. |
| Attacker-controlled same-site subdomain | SameSite alone cannot distinguish subdomains; CORS blocks reading when origin is disallowed, CSRF/authorization protect actions. |
| HTTPS page calling HTTP API | Browser may block mixed content, Secure cookies not sent; fix HTTPS, do not disable Secure. |
| Session changes after login/logout | Old token may become invalid; frontend must reload token. |

Observe in DevTools: `Origin`, request URL/method, `Access-Control-Request-*`, `Access-Control-Allow-*`, `Cookie`/`Set-Cookie` (and reasons a cookie was blocked), status, redirects, `Content-Type`, and CSRF header. Distinguish preflight errors from auth/CSRF 401/403 errors.

### 9.3 Distinguishing the Four Layers During Incidents

- **Preflight rejected:** check Origin/method/headers allowlist and whether CORS runs before auth; never open `*` with credentials.
- **Response blocked by CORS even though server returned 200/401/403:** verify the response/error/redirect chain includes proper CORS headers; the server itself may have already processed the request.
- **Cookie not sent:** check fetch credentials, Domain/Path, Secure, SameSite, third-party cookie restrictions, and HTTPS scheme. SameSite is site-based, not origin-based.
- **POST has cookie yet gets 403:** check CSRF token, raw/masked format, refreshed session/token after login, then check authorization. Never disable CSRF to bypass the error.
- **Mixed content / TLS / proxy:** fix transport and trusted proxy configuration; never disable HTTPS/Secure/HSTS just to make requests work temporarily.

## 10. Misconceptions to Avoid

**"CORS = CSRF defense."** False: CORS restricts response reading or certain preflight flows; simple form POSTs need no preflight. A CSRF token verifies that the request actually has authority to perform the session-bound action.

**"SameSite=Lax is enough for all CSRF."** False: same-site attackers (for example a sibling subdomain) can trigger requests carrying cookies; and top-level cross-site GETs can still carry Lax cookies. GET endpoints must be safe per HTTP semantics.

**"Enabling HTTPS eliminates CSRF."** False: forged requests can still be sent over HTTPS. HTTPS protects confidentiality in transit, not user intent.

**"Different origin means different site."** False: `app.example.com` and `api.example.com` both on HTTPS are cross-origin yet same-site; do not rush to SameSite=None.

**"SameSite=None makes CORS succeed."** False: cookie policy and CORS are independent. `None; Secure` can still be blocked by browsers as third-party cookies, and does not grant CORS permission.

**"Using JSON/SPA means CSRF can be disabled."** False if the API still uses automatically sent cookie credentials. You must base it on the actual credential model.

**"A CORS error always means the whitelist is wrong."** Incomplete: redirect/login errors, preflight blocked by auth, dropped cookies, HTTPS/proxy issues, or error responses lacking CORS headers can all make the browser report a CORS error.

**"CORS protects the API from curl/Postman."** False: non-browser tools do not enforce CORS or SameSite like browsers. APIs must always verify authentication and access permissions themselves.

## 11. Choosing an Approach by Architecture

- **Same-origin server-rendered web:** HTTPS + Secure/HttpOnly session cookies + appropriate SameSite + Spring Security CSRF. No need to open broad CORS when the frontend is not cross-origin.
- **Cross-origin yet same-site SPA:** restrict CORS to trusted origins, frontend uses `credentials: "include"`, API cookies use proper host/path and appropriate SameSite (usually Lax), CSRF tokens for unsafe methods, and HTTPS for both hosts.
- **Cross-site SPA:** CORS is still needed for JS to read the API; cross-site cookies face SameSite=None; Secure requirements and third-party cookie policies. Evaluate moving to same-site/same-origin via a proxy/backend-for-frontend if the architecture depends on session cookies.
- **API using only client-attached Bearer tokens:** CORS remains the cross-origin read policy; HTTPS still protects tokens. Evaluate CSRF needs based on whether any browser-auto-sent credentials remain; authorization is mandatory.

**Key Takeaways:** **CORS controls cross-origin JavaScript access; SameSite controls cookie sending by site; CSRF validates state-changing requests when automatic credentials exist; HTTPS protects transport.** Secure design requires evaluating origin, site, cookie scope, HTTP methods, CSRF tokens, authentication/authorization, and TLS together.