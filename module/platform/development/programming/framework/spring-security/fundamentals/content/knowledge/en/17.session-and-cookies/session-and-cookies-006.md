# `Secure`, `HttpOnly`, and `SameSite` Cookies in Spring Security

**Topic:** Spring Security – fundamentals → **Sessions and cookies**. This lesson targets Java 17+ and Spring Boot 3.x/Spring Security 6.x, and the same reasoning applies to newer versions after verifying the API documentation. The goal is to understand browser cookies, the exact meaning of these three security attributes, session cookie configuration for Spring MVC and WebFlux, and their limits in preventing session hijacking, XSS, and CSRF.

## 1. How Do Cookies Participate in a Login Session?

In a **server-side session** login application, the server typically creates a random session, stores authentication state on the server (or a distributed session store), and sends a **session identifier** to the browser via the `Set-Cookie` response header. The browser stores the cookie and sends it back via the `Cookie` request header on requests matching the domain, path, scheme, SameSite, and other browser policies.

```http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=opaque-random-id; Path=/; Secure; HttpOnly; SameSite=Lax
Content-Type: text/html
```

On a subsequent request to a valid URL:

```http
GET /account HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=opaque-random-id
```

**Distinguish the two headers:** `Set-Cookie` is the server **setting** the cookie; `Cookie` is the browser **sending back the name and value**, **without sending back the attributes** `Secure`, `HttpOnly`, or `SameSite`. The server must verify the session ID against its store and the user's permissions: merely seeing a cookie does not mean the caller is authenticated.

Three main attributes to read in `Set-Cookie`:

| Attribute | Controls | Primary protection | What it does **not** do |
|---|---|---|---|
| `Secure` | Browser only sends the cookie in HTTPS requests (localhost dev exceptions vary by browser) | Reduces cookie leakage over unencrypted HTTP connections | Does not block JavaScript from reading the cookie; does not enable HTTPS/TLS by itself |
| `HttpOnly` | Prevents page JavaScript APIs like `document.cookie` from reading/writing that cookie | Reduces the risk of XSS directly stealing the session ID | Does not stop JavaScript from issuing requests using the victim's session; does not prevent XSS |
| `SameSite` | Site condition of the request when the browser sends the cookie | Reduces certain CSRF and cross-site request attack paths | Does not replace CSRF tokens, Origin validation, and authorization |

**A generally sensible configuration for login sessions in an HTTPS web application:** `Secure; HttpOnly; SameSite=Lax`, adjusting to `SameSite=Strict` or `None` when business needs and the threat model genuinely require it. This is a reference baseline; **there is no single SameSite value suited to every product**.

## 2. `Secure`: Only Send Cookies Over a Secure Connection

Set `Secure` so browsers do not send session cookies over plain HTTP. This is especially critical for applications with login sessions: if a session cookie travels over an unencrypted connection, an eavesdropper or on-path attacker can capture the ID and hijack the session.

```http
Set-Cookie: JSESSIONID=abc123; Path=/; Secure; HttpOnly; SameSite=Lax
```

Under normal conditions:

- Visiting `https://app.example.com/account`: the cookie satisfies the HTTPS scheme condition and can be sent if domain/path/SameSite also match.
- Visiting `http://app.example.com/account`: the browser **does not send cookies marked `Secure`**.
- Modern browsers generally disallow plain HTTP origins from setting `Secure` cookies; **localhost** has browser-specific exceptions/differences, so do not extrapolate from local environments to production.
- `Secure` **does not encrypt the cookie contents by itself**. It relies on the request's TLS; the cookie still needs an unpredictable value, bounded lifetime, and server-side protection. Without `HttpOnly`, same-origin JavaScript can still read the cookie value.

### 2.1. HTTPS and reverse proxies

An application may run internally over HTTP behind Nginx, a load balancer, or a Kubernetes ingress while users access **HTTPS** externally. Do not disable `Secure` just because the hop from the proxy to the app is HTTP. Configure `Secure=true` on the session cookie so the browser only sends it over public HTTPS; configure TLS termination and proxy headers properly, trusting only managed proxies. With Spring Boot, you may need appropriate `Forwarded`/`X-Forwarded-*` handling if the framework must infer the scheme, redirect URLs, or client IP.

**Real HTTPS, HSTS, and `Secure` cookies are complementary layers**: HTTPS protects the channel; `Secure` restricts where the browser sends cookies; HSTS instructs the browser to prefer HTTPS for a host that received the policy. `Secure` does not issue TLS certificates, does not redirect HTTP, and does not prevent all forms of session fixation.

## 3. `HttpOnly`: Reducing the Risk of JavaScript Reading the Session ID

With `HttpOnly`, normal JavaScript on the page cannot access the cookie via `document.cookie` or related cookie-scripting APIs. The session ID is therefore harder to steal directly through an injected script on the page.

Example session cookie:

```http
Set-Cookie: JSESSIONID=abc123; Path=/; Secure; HttpOnly; SameSite=Lax
```

If the page runs:

```javascript
console.log(document.cookie);
```

The returned string may contain other cookies lacking `HttpOnly`, yet **will not include the `JSESSIONID` cookie marked `HttpOnly`**. **Never print real cookies to logs or the browser console in a production application.**

### 3.1. Understanding the limits accurately

- `HttpOnly` **does not prevent the cookie from being sent**. The browser still attaches it automatically to matching requests, including JavaScript-initiated requests via `fetch`/`XMLHttpRequest` if credentials, SameSite, CORS, and other conditions allow it.
- If the page has XSS, malicious code can still **perform actions on the user's behalf** using the logged-in browser, read data the script is allowed to read, or manipulate the DOM. `HttpOnly` only restricts one channel for reading the cookie **value**; it does not eliminate XSS.
- Never set `HttpOnly=false` on the **session ID** just so the frontend can display "logged in" status. Use an endpoint such as `GET /api/me` returning non-sensitive profile data within permitted bounds.
- An `HttpOnly` cookie does not need to contain a JSON profile, password, or easily exposed access token; a session ID should be an opaque, random value tied to a server-managed session.

### 3.2. Intentional exception: a cookie holding a CSRF token

Some SPAs read a CSRF token from an `XSRF-TOKEN` cookie and send the token value in an `X-XSRF-TOKEN` header. When **JavaScript genuinely needs to read the CSRF token cookie**, that cookie may **omit `HttpOnly`** by design. **Do not confuse the CSRF token cookie with the login session cookie**: the session cookie should still have `HttpOnly=true`.

Spring Security Servlet provides `CookieCsrfTokenRepository.withHttpOnlyFalse()` for cases where JavaScript reads the token. This is a **conditional** configuration, not a blanket recommendation for every app; SPAs on Spring Security 6 also need to handle deferred tokens/BREACH protection and CSRF token re-issuance per official documentation.

```java
// Snippet inside Servlet application's HttpSecurity configuration.
// Use only when the SPA needs JavaScript to read the XSRF-TOKEN cookie.
http.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
);
```

This snippet is **not a standalone Java program**; it requires importing `org.springframework.security.web.csrf.CookieCsrfTokenRepository` and the corresponding Spring Security types. It configures the **CSRF cookie**, and does **not** mean the `JSESSIONID` session cookie loses `HttpOnly`.

## 4. `SameSite`: "Same Site" Differs from "Same Origin"

`SameSite` decides whether the browser sends a cookie when a request originates in a **cross-site context**. To understand it correctly, distinguish:

- **Origin** consists of `scheme + hostname + port`. For example, `https://app.example.com:443` and `https://api.example.com:443` are **different origins**.
- **Site** in modern cookie definitions is typically based on `scheme + registrable domain` (schemeful same-site). For example, `https://app.example.com` and `https://api.example.com` are usually **same-site** because they share the HTTPS scheme and the registrable domain `example.com`.
- `https://app.example.com` and `https://payments.example.net` are **cross-site**.
- `http://app.example.com` and `https://app.example.com` have **different schemes**, so they are treated as distinct under schemeful same-site rules.

**Consequence:** SameSite is not a mechanism for blocking **cross-origin** requests in general. Subdomains on the same site can send cookies in a same-site context, even though they remain cross-origin and are subject to **CORS** if JavaScript wants to read the response. Do not treat `SameSite=Strict` as a CSRF wall against untrusted subdomains on the same site.

## 5. The Three Values: `Strict`, `Lax`, and `None`

| Value | When the browser sends the cookie | Suitable cases | Trade-off |
|---|---|---|---|
| `SameSite=Strict` | Only in same-site contexts | Sensitive functional sessions rarely navigated to from external sites | Opening a page via an external link may omit the session on the initial navigation |
| `SameSite=Lax` | Same-site, plus certain cross-site **top-level navigations** using safe HTTP methods like GET | Many standard web applications | Cross-site top-level GET still carries the cookie; standard cross-site POST does not |
| `SameSite=None` | Allows sending in both same-site and cross-site contexts when other cookie/browser conditions are met | Embedded iframes, cross-site integrations genuinely needing credentials | **Must be paired with Secure**; increases CSRF surface, may be blocked by browser third-party cookie restrictions |

Examples:

```http
Set-Cookie: session_strict=opaque; Path=/; Secure; HttpOnly; SameSite=Strict
Set-Cookie: session_lax=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
Set-Cookie: session_cross=opaque; Path=/; Secure; HttpOnly; SameSite=None
```

These are **three independent illustrative cookies**, not a requirement for a real app to issue three session cookies simultaneously.

### 5.1. Common behavior matrix

Suppose the user is logged in at `https://app.example.com` and the cookie's host/path match the target. The table below describes **SameSite conditions in modern browsers**, assuming no other cookie policy blocks it.

| Request scenario to app.example.com | Strict | Lax (explicitly declared) | None + Secure |
|---|---|---|---|
| Internal click inside the app (same-site) | Sent | Sent | Sent |
| `fetch` from a matching same-site page | Sent* | Sent* | Sent* |
| User clicks link from `other.net` → top-level `GET` to app | Not sent | Sent | Sent |
| Form on `other.net` → top-level `POST` to app | Not sent | Not sent | May be sent |
| Loading `<img>` or `iframe` of app from `other.net` | Not sent | Not sent | May be sent |
| `fetch` from `other.net` to app | Not sent | Not sent | May be sent* |

Asterisk `*`: **SameSite is only one condition**. For JavaScript `fetch`, you must also consider `credentials` (especially cross-origin), CORS, cookie scope, third-party cookie blocking, and browser policies. With `None`, "may be sent" reflects that browsers can still reject third-party cookies, especially in iframe/tracking contexts.

### 5.2. `Lax` and top-level navigation

`Lax` typically **sends the cookie when a user directly navigates via GET from an external site**. That helps UX: a user clicking a link from an email or partner site to their account page keeps their session. `Strict` can cause that initial request to lack the session; once the page opens and the user navigates within the site, the cookie is sent again if same-site conditions hold.

Precisely because `Lax` still allows cross-site top-level GETs, **never design GET endpoints with state-changing side effects** such as `GET /transfer?amount=...` or `GET /delete?id=...`. Safe methods must truly have no significant business side effects; use POST/PUT/PATCH/DELETE and CSRF protection for state-changing actions when cookies are the authentication mechanism.

### 5.3. Default SameSite when undeclared

Many modern browsers apply `Lax`-like behavior when a cookie lacks a SameSite attribute. **However, do not rely on browser defaults**:

- Policies vary by browser, mode, version, or usage context.
- Some browsers implement default `Lax` with a **short-lived exception for cross-site POST shortly after cookie creation**, often called `Lax-allowing-unsafe`. That exception is **not equivalent to a cookie explicitly declaring `SameSite=Lax`**.
- Therefore, set `SameSite=Lax` or `Strict` explicitly according to a tested policy.

### 5.4. `None` means no SameSite restriction, not "no cookie"

`SameSite=None` **does not mean disabling cookies or removing transport protection**. It allows browsers to send cookies in cross-site contexts when eligible and **must be paired with `Secure`**:

```http
Set-Cookie: embedded_session=opaque; Path=/; Secure; HttpOnly; SameSite=None
```

Missing Secure:

```http
Set-Cookie: embedded_session=opaque; Path=/; HttpOnly; SameSite=None
```

Many modern browsers **reject** the second cookie form. Even a valid `None; Secure` cookie may **not be sent** due to third-party cookie blocking, privacy/tracking protection, or partitioning. When iframe/cross-site SSO flows are needed, test with real browsers, CORS, redirects, and session behavior; do not rely solely on the flag.

## 6. `SameSite`, CSRF, CORS, and XSS Are Different Problems

### 6.1. Why does SameSite help reduce CSRF?

In a CSRF attack, a user logged into `bank.example` visits a malicious site that triggers a request to the bank. If the browser automatically sends the session cookie with that request, the backend may mistake the request for an action authorized by the account owner.

`SameSite=Lax` or `Strict` eliminates many cases where cookies auto-attach to **cross-site unsafe requests**. However:

1. `Lax` still permits cross-site top-level GET; GET must never perform sensitive actions.
2. Requests originating from a **same-site** subdomain may not be blocked by SameSite, even if that subdomain is compromised.
3. Browsers are not the only way APIs are called; non-browser API clients can attach `Cookie` headers manually.
4. Redirects, state-changing endpoints, differing browser policies, and login lifecycles must also be considered.
5. `SameSite=None` required for integrations makes cookies more likely to appear on cross-site requests; stronger CSRF defenses are needed.

**Conclusion:** For applications using cookies/sessions for authentication, continue applying Spring Security's **CSRF protection** or an equivalent mechanism reviewed against your threat model—do not disable CSRF merely because `SameSite=Lax` was added. You may also need trusted Origin/Referer checks, CSRF token validation, and rejection of invalid requests.

### 6.2. Why doesn't CORS replace CSRF?

**CORS** governs whether JavaScript on another origin is permitted to **read the response** (and for certain requests, pass preflight). It is not a rule forbidding all ways a browser can **send** requests, such as form submissions. A response blocked from JavaScript reading can still have caused the server to execute the action if the backend processed the request without a CSRF guard.

Consider a frontend `https://app.example.com` and an API `https://api.example.com`:

- They are **same-site** if both use HTTPS and the same registrable domain, yet **cross-origin**.
- A host-only cookie issued by `api.example.com` can still be sent **to `api.example.com`**; it does not necessarily need `Domain=.example.com`.
- When JavaScript makes cross-origin calls with `fetch`, it typically needs `credentials: "include"` and the API must return specific CORS headers matching the calling origin; `Access-Control-Allow-Origin: *` is incompatible with credentialed CORS responses.
- Valid CORS **does not automatically allow** a request to bypass Spring Security authorization or CSRF.

```javascript
// Running at https://app.example.com, calling a different-origin API
fetch("https://api.example.com/api/me", {
  method: "GET",
  credentials: "include"
}).then(response => {
  if (!response.ok) throw new Error("HTTP " + response.status);
  return response.json();
});
```

This snippet only demonstrates configuring credentials from the frontend; whether a cookie is actually attached depends on SameSite, domain/path, Secure, browser policies, and whether the cookie already exists. Never log session IDs to the console.

### 6.3. Why doesn't HttpOnly fix XSS?

An XSS payload may not be able to read an `HttpOnly` `JSESSIONID`, yet it can still **call APIs using the active session**, modify the DOM, or read frontend data the user is authorized to view. You still need input/output handling, output encoding, an appropriate CSP, safe libraries, and dependency updates. `HttpOnly` is only one layer reducing direct theft of the session cookie.

## 7. `Domain`, `Path`, and Cookie Lifetime Matter Too

The three main flags do not operate in isolation. Other attributes govern the **scope** and **lifetime** of a cookie:

| Attribute | Meaning | Security note |
|---|---|---|
| Omitting `Domain` | Host-only cookie: bound to the host that issued it | Preferred when sharing across subdomains is unnecessary |
| `Domain=example.com` | Allows sending the cookie to the domain and eligible subdomains within scope | Expands subdomain attack surface, risks cookie tossing/fixation |
| `Path=/app` | Only sent when the request path matches | **Not a security authorization boundary** between apps on the same host |
| `Max-Age=1800` | Valid for seconds from when it is set | Not synonymous with server-side session lifetime |
| `Expires=...` | Expiration at an absolute timestamp | If both `Max-Age` and `Expires` are present, `Max-Age` takes precedence |
| Neither `Expires` nor `Max-Age` | Browser session cookie | Browsers may restore sessions on restart; do not treat closing a tab as guaranteed logout |

For session identifiers, use unpredictable random values, sensible lifetimes, and session ID rotation/migration after login or privilege elevation, combined with server-side logout/invalidation. Spring Security provides session fixation protection in appropriate flows; **cookie flags alone do not replace this mechanism**.

### 7.1. Prefer host-only cookies

`Set-Cookie` without `Domain` creates a host-only cookie. If the API lives at `api.example.com` and the frontend at `app.example.com`, the session cookie **can** remain host-only on the API: the browser automatically sends it to the API on matching requests. Setting `Domain=example.com` so every subdomain receives the cookie **is not always necessary**, and can introduce risks from less-protected subdomains.

### 7.2. Cookie prefixes

Browsers support special prefixes that enforce additional constraints when creating cookies:

- `__Secure-<name>`: must be set over HTTPS and carry `Secure`.
- `__Host-<name>`: must carry `Secure`, `Path=/`, and **must not specify `Domain`**; useful for mitigating cookie injection from subdomains.
- `__Http-<name>` and `__Host-Http-<name>`: add an `HttpOnly` requirement where supported by browsers; check compatibility and do not rely on prefixes alone.

Example host-only session cookie:

```http
Set-Cookie: __Host-session=opaque-random-id; Path=/; Secure; HttpOnly; SameSite=Lax
```

Example **invalid** for the `__Host-` prefix because `Domain` is set:

```http
Set-Cookie: __Host-session=opaque; Domain=example.com; Path=/; Secure; HttpOnly; SameSite=Lax
```

If you rename the session cookie to `__Host-session`, the server or session infrastructure must **read the new name**. Prefixes are conventions enforced by supporting browsers and must be verified for compatibility; they do not replace server-side validation.

## 8. Spring Boot Servlet / Spring MVC Configuration

In a **Spring Boot 3.5** application with the corresponding auto-configured servlet container, session cookies can be configured in `application.yml`:

```yaml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        secure: true
        http-only: true
        same-site: lax
        path: /
```

Equivalent in `application.properties`:

```properties
server.servlet.session.timeout=30m
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.cookie.path=/
```

**Explanation:**

1. `secure=true` requires the session cookie to carry `Secure`; production must serve HTTPS to the browser. In local environments running plain `http://127.0.0.1`, `Secure` cookies can behave differently across browsers; test with production-like HTTPS.
2. `http-only=true` requires the session cookie to carry `HttpOnly`, reducing the risk of JavaScript stealing the session ID.
3. `same-site=lax` sets `SameSite=Lax` on the cookie. If `strict` or `none` is needed, switch to that value **only after reviewing navigation flows and CSRF**; `none` must be paired with `secure=true`.
4. `timeout=30m` is the configured server-side Servlet session timeout; it **does not automatically guarantee** a `Max-Age=1800` attribute on the cookie.
5. `path=/` scopes the cookie to the root path of the host; consider actual application context paths if the host serves multiple apps.

The properties above apply to the **Servlet session cookie** and do not automatically govern other cookies such as custom tokens, `remember-me`, OAuth2 redirect state, or CSRF cookies depending on the repository/mechanism used. Every cookie emitted by other components must still be audited independently.

**Note:** applications using Spring Session or a custom container/proxy may have additional configuration via `CookieSerializer`, filters, or header rewrites. Inspect the **actual** `Set-Cookie` on responses after deployment rather than inferring everything from YAML.

### 8.1. Spring Security bean and session configuration

`SecurityFilterChain` handles authentication, authorization, CSRF, session fixation, logout, security headers, and related steps. Enabling cookie flags **does not require** disabling CSRF or changing authorization rules. Example basic `WebSecurityConfig.java` configuration class for a Spring MVC application with form login:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form.permitAll());

        return http.build();
    }
}
```

This configuration class uses Spring Security 6.x and Java 17+, meant for a Spring Boot MVC application with `spring-boot-starter-web` and `spring-boot-starter-security`. The `Secure`/`HttpOnly`/`SameSite` values belong to the session cookie properties above, not inside `formLogin()`. By default in a configuration like this, CSRF **is not disabled**. Handle user/password storage and login pages appropriately for a real application.

Do not assume `formLogin` automatically creates a cookie on every request: the session cookie is emitted when the framework creates/uses a session according to the session strategy. To verify, exercise the actual login/session flow in tests.

### 8.2. Distinguishing the main session cookie from API-issued custom cookies

If your code sends `Set-Cookie` directly for a custom cookie, `server.servlet.session.cookie.*` properties **do not guarantee** it carries those flags. Use a standard builder such as Spring's `ResponseCookie` and issue it only under controlled logic.

The example below creates **an illustrative non-authentication cookie**. It is a Java 17+ controller for a Spring Boot web app, not a standalone `.java` file runnable with `javac` without Spring dependencies.

```java
import java.time.Duration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SampleCookieController {

    @GetMapping("/public/example-cookie")
    public ResponseEntity<String> issueExampleCookie() {
        ResponseCookie cookie = ResponseCookie
            .from("__Host-example", "sample-value")
            .secure(true)
            .httpOnly(true)
            .sameSite("Lax")
            .path("/")
            .maxAge(Duration.ofMinutes(5))
            .build();

        return ResponseEntity.ok()
            .header(HttpHeaders.SET_COOKIE, cookie.toString())
            .body("Cookie example");
    }
}
```

Because the cookie named `__Host-example` has `Secure`, `Path=/`, and **no `Domain`**, it satisfies `__Host-` prefix rules in supporting browsers. The string `sample-value` is for learning only and **must never be used as a real session ID/token**. Standard session cookies should be managed by Spring/the container/session store, not hand-rolled from a predictable or hardcoded value.

## 9. Spring Boot WebFlux Configuration

In Spring Boot 3.5, session cookies in the **reactive WebFlux** model use a separate property group `server.reactive.session.cookie.*`:

```yaml
server:
  reactive:
    session:
      timeout: 30m
      cookie:
        secure: true
        http-only: true
        same-site: lax
        path: /
```

Keep them distinct:

| Model | Cookie configuration namespace |
|---|---|
| Servlet / Spring MVC | `server.servlet.session.cookie.*` |
| Reactive / Spring WebFlux | `server.reactive.session.cookie.*` |

Do not configure both namespaces and assume both apply. Determine whether the application actually runs Servlet or Reactive. Spring Boot may choose Servlet if both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, so verify the actual runtime/application type.

In WebFlux, the HTTP security layer is configured via `ServerHttpSecurity`/`SecurityWebFilterChain` instead of `HttpSecurity`/`SecurityFilterChain`. Cookie flags and SameSite policies are browser concerns, while retrieving the session/reactive security context must remain inside the Reactor flow. Minimal example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveWebSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated()
            )
            .httpBasic(org.springframework.security.config.Customizer.withDefaults())
            .build();
    }
}
```

**Note on the example:** `httpBasic` does not inherently describe a cookie-based login session: Basic can authenticate on each request via the `Authorization` header. If the application genuinely needs session-based login, choose an appropriate authentication/session mechanism rather than assuming `SecurityWebFilterChain` implies session cookies. The YAML above configures **when a WebSession cookie is created**; it does not force every request to create a session.

## 10. Special Cases: Cross-Site Login, Iframes, and SPAs

### 10.1. Frontend on a different origin yet still same-site

Example:

- Frontend: `https://app.example.com`.
- Backend: `https://api.example.com`.

The two hosts are **cross-origin**, yet typically **same-site** (both HTTPS, same registrable domain). In this case, you can use `SameSite=Lax` for the API's host-only cookie, combined with `fetch(..., { credentials: "include" })` and CORS configured for the specific frontend. **Do not automatically pick `SameSite=None` simply because the two origins differ**.

### 10.2. Genuinely cross-site frontend

Example:

- Frontend: `https://portal.partner.net`.
- Backend: `https://auth.example.com`.

This is **cross-site**. If a cookie genuinely must participate in cross-site requests, `SameSite=None; Secure` may be needed, yet you still must account for browser third-party cookie blocking, consent, CORS, CSRF, and authentication architecture. When third-party cookies are blocked, changing the flag to `None` does not guarantee the login flow will work. Consider integrations based on top-level redirects/OIDC flows, same-site frontend/backend hosting, or another security-reviewed architecture.

### 10.3. OAuth2/OIDC login redirects do not mean every cookie must be None

An authorization code flow redirects through an external identity provider. Upon redirecting back to the callback, the request can be a **top-level GET**, and a `SameSite=Lax` cookie can be sent. However, variants using POST response modes, iframes, silent login, or different domains have different requirements. Inspect how session/state/nonce are stored, the callback method, and supported browsers; do not relax all session cookies to `SameSite=None` purely on the assumption that "SSO requires cross-site."

## 11. Verifying `Set-Cookie` on Real Responses

Do not merely read `application.yml` and assume the configuration is right. Inspect browsers and responses over **HTTPS** in a production-like environment:

1. Open DevTools → **Network** → the response creating the session (login or session-initializing request); inspect the `Set-Cookie` response header, not confusing it with the `Cookie` request header.
2. Open DevTools → **Application/Storage → Cookies**; verify `Secure`, `HttpOnly`, `SameSite`, Domain, Path, and Expires.
3. Reload the page after login; confirm the session cookie is sent to the right host/path and **not** sent to unintended hosts/paths.
4. Test from an actual external site for top-level GET, POST, and iframe/fetch; remember cookies can be blocked by CORS/credentials or third-party policies rather than SameSite alone.
5. Check cookies after deploying behind a reverse proxy/load balancer; avoid the pitfall where local works yet production emits cookies missing `Secure` due to wrong scheme forwarding.
6. Verify logout, session invalidation, session fixation defense, CSRF token lifecycle, and server session expiration.

Command to inspect response headers (example only; the URL must belong to your test environment):

```bash
curl -i https://app.example.com/public/example-cookie
```

In the test response from the sample controller, the `Set-Cookie` header should contain attributes similar to:

```http
Set-Cookie: __Host-example=sample-value; Path=/; Max-Age=300; Secure; HttpOnly; SameSite=Lax
```

**Attribute order may vary**; tests should assert the presence of each flag rather than exact full-line string equality unless an API specifically requires it. `curl` **does not fully simulate** browser decisions around SameSite, CORS, or third-party cookies. Never put real session IDs into logs or publicly shared captures.

### 11.1. MockMvc test snippet for a controller-created cookie

With `spring-boot-starter-test` or equivalent, `MockMvc`, and a configured Spring test context:

```java
MvcResult result = mockMvc
    .perform(get("/public/example-cookie"))
    .andExpect(status().isOk())
    .andReturn();

List<String> cookieHeaders = result.getResponse()
    .getHeaders(HttpHeaders.SET_COOKIE);

assertThat(cookieHeaders).anySatisfy(value -> {
    assertThat(value).contains("__Host-example=");
    assertThat(value).contains("Secure");
    assertThat(value).contains("HttpOnly");
    assertThat(value).contains("SameSite=Lax");
    assertThat(value).contains("Path=/");
});
```

This is a test **snippet**, not a standalone test class. It requires importing `MvcResult`, `HttpHeaders`, `List`, `MockMvcRequestBuilders.get`, `MockMvcResultMatchers.status`, and AssertJ's `Assertions.assertThat`; it requires injecting `MockMvc` and creating a Spring test context. The snippet verifies the **sample endpoint's** cookie, and **does not by itself prove** that Spring Boot emits the `JSESSIONID` session cookie properly: you must trigger a real session in a corresponding integration test.

### 11.2. Risk-based test cases

| Test case | Expected result |
|---|---|
| Session created over HTTPS | Session cookie carries expected `Secure`, `HttpOnly`, `SameSite` |
| Request to same host/path over HTTP | Browser does not send the `Secure` cookie (aside from localhost differences) |
| Run `document.cookie` | Cannot read the `HttpOnly` cookie |
| JavaScript calls API while logged in | `HttpOnly` cookie can still be sent per cookie policy; API still enforces authorization |
| Cross-site top-level GET | `Lax` may send, `Strict` does not send |
| Cross-site POST from external site | Explicitly declared `Lax` does not send session; `None` may send if browser allows |
| Iframe from another site | Standard `Lax`/`Strict` does not send; `None + Secure` may send |
| `SameSite=None` missing `Secure` | Modern browsers typically reject the cookie |
| Cookie with `__Host-` prefix yet has `Domain` | Supporting browsers reject it |
| CSRF POST without token | Must be rejected when CSRF guard applies, regardless of `Lax` cookie presence |
| Logout | Server session invalidated; browser cookie expired/deleted matching exact name/path/domain |
| Untrusted subdomain | SameSite does not automatically block same-site requests; authz/CSRF still checked |
| Expired session | Server rejects old session ID even if browser still holds the cookie |
| App behind HTTPS proxy | `Set-Cookie` retains `Secure` and intended domain/path |

**Distinguish browser behavior from header serialization:** a unit test seeing `SameSite=Lax` in a header only verifies the server **emitted the right flag**; to know whether browsers **send or withhold** it in each real scenario, run browser integration tests.

## 12. Standalone Java 17 Example: A Simple SameSite Mental Model

To reinforce the matrix, you can write a plain Java **learning model** without Spring. It **does not fully simulate a browser**: it omits default-Lax grace periods, CORS/credentials, third-party blocking, iframe policies, Domain/Path/Secure, and redirect chains. Use it to remember basic rules, **not in place of browser tests or server-side security decisions**.

File `SameSitePolicyDemo.java`:

```java
public class SameSitePolicyDemo {

    enum Mode { STRICT, LAX, NONE }

    record Scenario(boolean sameSite,
                    boolean topLevelNavigation,
                    boolean safeMethod) {}

    static boolean allowedBySameSite(Mode mode, Scenario request) {
        if (request.sameSite()) {
            return true;
        }
        return switch (mode) {
            case STRICT -> false;
            case LAX ->
                request.topLevelNavigation() && request.safeMethod();
            case NONE -> true;
        };
    }

    public static void main(String[] args) {
        Scenario externalLinkGet = new Scenario(false, true, true);
        Scenario externalFormPost = new Scenario(false, true, false);

        System.out.println("Strict link GET: "
            + allowedBySameSite(Mode.STRICT, externalLinkGet));
        System.out.println("Lax link GET: "
            + allowedBySameSite(Mode.LAX, externalLinkGet));
        System.out.println("Lax form POST: "
            + allowedBySameSite(Mode.LAX, externalFormPost));
        System.out.println("None form POST: "
            + allowedBySameSite(Mode.NONE, externalFormPost));
    }
}
```

Compile and run with **JDK 17+**:

```bash
javac SameSitePolicyDemo.java
java SameSitePolicyDemo
```

Exact stdout according to the model above:

```text
Strict link GET: false
Lax link GET: true
Lax form POST: false
None form POST: true
```

These booleans describe only an **idealized SameSite gate**. For instance, `None form POST: true` **does not assert** a browser will actually send the cookie: it still requires `Secure`, HTTPS, matching cookie scope, no third-party cookie blocking by the browser, and satisfying other policies. Also distinguish `safeMethod` (GET/HEAD/OPTIONS/TRACE per HTTP semantics) from "a request incapable of side effects": the application itself must **ensure** safe methods do not mutate state.

## 13. Common Mistakes and How to Fix Them

1. **Omitting `Secure` because the app runs HTTP behind a proxy:** set `Secure` cookies for external HTTPS; fix trust chains/forwarded headers and TLS/proxy config.
2. **Thinking `Secure` blocks XSS or encrypts values in RAM:** incorrect. Use `HttpOnly`, XSS defenses, session hardening, and authorization.
3. **Disabling `HttpOnly` on the session cookie because the SPA needs to know the user:** keep `HttpOnly`, use an `/api/me` endpoint; only consider a readable CSRF token cookie when truly needed.
4. **Using `SameSite=None` without `Secure`:** browsers typically reject the cookie; add `Secure` and HTTPS or redesign the integration.
5. **Treating `Lax` as complete CSRF protection:** cross-site top-level GET still sends cookies; same-site subdomains can bypass this layer; always protect unsafe methods with appropriate CSRF controls.
6. **Treating cross-origin as always cross-site:** two HTTPS subdomains of the same registrable domain can be same-site yet cross-origin; distinguish CORS from SameSite.
7. **Thinking CORS blocks all cross-site POSTs:** form POSTs can reach the server even if frontend JavaScript cannot read the response. The backend must enforce CSRF checks.
8. **Relying on browser default `Lax`:** omitting the explicit attribute can yield varying behavior, including the brief POST exception after cookie creation.
9. **Setting `Domain` too broadly:** `Domain=example.com` causes many subdomains to share cookie scope; prefer host-only and `__Host-` prefixes where suitable.
10. **Confusing `Path` with a security boundary:** `Path` is a cookie-sending condition, not authorization between apps/tenants.
11. **Setting infinite `Max-Age` for sensitive sessions:** widens the window of exposure if a valid ID is stolen; enforce bounded lifetimes and server-side rotation/invalidation.
12. **Storing passwords, PII, or sensitive bearer tokens in readable form inside cookies:** prefer an opaque session ID and minimize client-side data.
13. **Disabling CSRF so form/login "stops returning 403" without investigating:** distinguish wrong tokens, unissued CSRF tokens, expired sessions, browser-blocked cookies, and missing permissions.
14. **Assuming every `Set-Cookie` is a session:** remember-me, CSRF, tracking/preferences, and custom cookies have different policies; inspect each type.
15. **Testing with curl and inferring browser SameSite support:** curl only reads headers and does not represent browsers/iframes/credentials/third-party policies.
16. **Using local HTTP and concluding `Secure` cookies are "broken":** test over HTTPS or configure a proper test environment; localhost has browser-dependent exceptions.

## 14. Pre-Production Deployment Checklist

- [ ] All login pages and requests carrying session cookies are served over HTTPS with standard TLS configuration.
- [ ] Issued session cookies have `Secure=true` and `HttpOnly=true`, verified on real responses behind the proxy.
- [ ] `SameSite` is set explicitly: choose `Lax`/`Strict` per UX; `None` only when genuinely cross-site and paired with `Secure`.
- [ ] Identify **site vs. origin** for frontend/API/identity provider; test login redirects and iframe/cross-site flows if any.
- [ ] Keep CSRF protection or an equivalent mechanism suited to cookie authentication; GET has no state-changing side effects.
- [ ] Prefer host-only session cookies; Domain, Path, and `__Host-` prefix are deliberately verified.
- [ ] Session IDs are unpredictable, rotated after login/privilege elevation, invalidated on logout, and bounded by reasonable lifetimes.
- [ ] No passwords, sensitive personal data, or unnecessary secrets are stored in cookies.
- [ ] Audit session cookies, CSRF token cookies, and custom cookies **separately**.
- [ ] Test in real browsers over HTTPS, including cross-site GET/POST, subdomains, iframes, credentials, and third-party cookie restrictions.
- [ ] Verify configuration matches the web stack: `server.servlet.session.cookie.*` for MVC, `server.reactive.session.cookie.*` for WebFlux.
- [ ] Mitigate XSS and protect endpoints and data on the server; **never treat a cookie flag as proof of authorization**.

## 15. Official References

- [MDN — Set-Cookie: Secure, HttpOnly, SameSite, Prefixes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie).
- [MDN — Secure cookie configuration](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Cookies).
- [MDN — Using HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies).
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html).
- [Spring Boot 3.5 — Servlet Web Applications / SameSite Cookies](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html).
- [Spring Security — CSRF Protection (Servlet)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html).

**Remember:** `Secure` governs **the HTTPS channel**, `HttpOnly` governs **whether JavaScript can read the cookie**, and `SameSite` governs **when the browser sends the cookie in same-site/cross-site contexts**. The three attributes complement each other yet **do not replace** TLS, XSS prevention, CSRF tokens, session management, server-side authorization, or real browser testing.