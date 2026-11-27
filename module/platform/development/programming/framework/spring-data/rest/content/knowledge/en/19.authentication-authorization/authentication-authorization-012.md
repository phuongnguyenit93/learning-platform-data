# CSRF, Session Cookies, and Strategies for Token-Based APIs in Spring Data REST

## Objective

After this lesson, you will be able to explain why a REST API can still be vulnerable to CSRF; recognize when session cookies cause browsers to attach credentials automatically; configure CSRF tokens for session-based Spring Data REST applications; distinguish that model from Bearer-token-only APIs; and organize Spring Security filter chains suited to each authentication style.

## 1. What is CSRF and why do REST APIs still need to care?

Cross-Site Request Forgery (CSRF) is an attack that tricks an authenticated user's browser into sending an unintended request to an application the user trusts. Attackers typically lure the user into opening another web page. That page can issue a form submission or request to the target application.

The key factor is that the browser can automatically attach credentials bound to the target origin, such as session cookies. If the server only checks that the cookie is valid without verifying the request originated intentionally from the application, data-mutating actions can execute under the user's identity.

For example, a user is logged into an order management application at `https://shop.example.com`. The browser holds a session cookie. A malicious page can attempt to submit a form to the endpoint that changes the shipping address. If the browser automatically sends the session cookie and the server does not require a CSRF token, the request can authenticate as the real user.

CSRF does not depend on whether an API returns HTML or JSON. Spring Data REST still accepts write operations such as POST, PUT, PATCH, and DELETE. If the browser automatically sends cookies or other credentials, those endpoints still require an appropriate CSRF defense policy.

## 2. When is CSRF a risk?

Consider how credentials are sent to the server:

| Authentication mechanism | Does the browser automatically send credentials on cross-site requests? | CSRF |
| --- | --- | --- |
| Session cookie | May automatically send cookies matching domain, path, and SameSite | Requires CSRF protection |
| JWT or token stored in a cookie | Cookies are still sent automatically by the browser | Still requires CSRF protection |
| HTTP Basic Authentication cached/sent automatically by the browser | May automatically attach credentials | Evaluate and protect against CSRF |
| Bearer token explicitly placed by the client in the `Authorization` header | Another site cannot read the app's token and attach it to requests | Generally no CSRF needed for that mechanism |
| Native client explicitly setting a Bearer token in a header | No automatic browser cookie mechanism | Generally no CSRF needed for that mechanism |

CSRF primarily exploits **ambient credentials**: credentials automatically attached by the browser on requests. Cookies are the most common example.

Labels like "REST API", "JWT", or "stateless" do not determine on their own whether an API needs CSRF protection. Look at how credentials actually arrive at the server. A JWT stored in a cookie still shares the ambient credential properties of a session cookie.

## 3. Spring Security protects requests with CSRF tokens

Spring Security provides `CsrfFilter` and `CsrfTokenRepository` to generate, store, and validate CSRF tokens. By default, CSRF protection is enabled for state-changing requests, typically including POST, PUT, PATCH, and DELETE. Safe methods like GET, HEAD, and OPTIONS should never be used to mutate data.

In a session-based application, the token is typically stored server-side associated with the HTTP session. When rendering HTML, the application embeds the token in a hidden field or meta tag. The client must send the token back on write requests; the session cookie alone is insufficient.

Server-rendered form example:

```html
<form method="post" action="/orders">
    <input type="hidden" name="_csrf" value="...">
    <!-- Data fields -->
    <button type="submit">Create order</button>
</form>
```

For JavaScript requests, the token is typically sent in a header. Spring Security's default header name is `X-CSRF-TOKEN` when using the default session repository; with `CookieCsrfTokenRepository`, the default header name is `X-XSRF-TOKEN`.

If the token is missing or does not match what the server expects, Spring Security rejects the request before the controller/repository executes the operation. The response is typically `403 Forbidden`.

## 4. Session cookies and Spring Data REST applications

A Spring Data REST application may use session login via form login or another session-based authentication mechanism. The browser stores the session cookie and sends it automatically when calling same-site APIs per cookie rules.

Spring Security configuration can keep default CSRF protection enabled:

```java
@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        // CSRF is enabled by default; do not disable for session-based apps.
        return http.build();
    }
}
```

With a session-based API, GET requests read resources; POST/PUT/PATCH/DELETE requests require a CSRF token. Example creating an Order via the collection resource:

```http
POST /api/orders HTTP/1.1
Cookie: JSESSIONID=...
Content-Type: application/json
Accept: application/hal+json
X-CSRF-TOKEN: <token obtained from application>

{
  "description": "Laptop order"
}
```

The actual session cookie name may be `JSESSIONID` or a container-configured name. The token must be retrieved from the authenticated application and sent back on the request; never invent a random token string on the client.

## 5. Using CookieCsrfTokenRepository for SPAs

An SPA running in a browser often needs to read the CSRF token and attach it to headers on state-changing requests. Spring Security provides `CookieCsrfTokenRepository` to store the token in a cookie.

Basic configuration:

```java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {

    http
        .csrf(csrf -> csrf
            .csrfTokenRepository(
                CookieCsrfTokenRepository.withHttpOnlyFalse()));

    return http.build();
}
```

By default, this repository uses:

- Cookie name `XSRF-TOKEN`.
- Header name `X-XSRF-TOKEN`.
- Request parameter name `_csrf`.

`withHttpOnlyFalse()` allows JavaScript to read the CSRF cookie so it can place the value in a header. This is the CSRF token cookie, not the session cookie. The session cookie should remain `HttpOnly` so JavaScript cannot read the authentication credential.

Same-origin JavaScript example:

```javascript
function readCookie(name) {
    const prefix = name + "=";
    const item = document.cookie
        .split("; ")
        .find(value => value.startsWith(prefix));

    return item ? decodeURIComponent(item.slice(prefix.length)) : null;
}

async function createOrder(order) {
    const csrfToken = readCookie("XSRF-TOKEN");

    return fetch("/api/orders", {
        method: "POST",
        credentials: "same-origin",
        headers: {
            "Content-Type": "application/json",
            "Accept": "application/hal+json",
            "X-XSRF-TOKEN": csrfToken
        },
        body: JSON.stringify(order)
    });
}
```

This example illustrates reading the cookie and sending the header. The application must ensure the token cookie has been generated prior to calling the function and that tokens are refreshed after authentication events that change the session.

### Spring Security 6 and SPA token handling

Spring Security 6 uses deferred CSRF tokens and BREACH protection with XOR encoding in request attributes. An SPA reads the cookie token and sends the raw token in a header, so a request handler matching how tokens are issued and resolved must be configured.

Adding `CookieCsrfTokenRepository` alone may not suffice for all SPA flows in Spring Security 6. Follow the `SpaCsrfTokenRequestHandler` pattern from your exact Spring Security version's documentation, ensuring the handler:

- Uses the XOR handler for tokens exposed in request attributes/HTML responses.
- Accepts the raw token from the SPA header compatibly with the cookie repository.
- Forces token creation when needed so the cookie is sent to the browser.
- Refreshes tokens after authentication success and logout if the application requires a new token for the next session.

Do not copy a handler from another Spring Security version without checking the API and behavior of your project's version. Deferred token and BREACH handling details vary between versions.

## 6. Secure cookie settings

Session cookies are authentication credentials, so they typically need these attributes:

- `HttpOnly`: prevents JavaScript from reading the session cookie.
- `Secure`: sends the cookie only over HTTPS.
- `SameSite=Lax` or `Strict` where compatible with navigation and login flows.
- `Path` and `Domain` narrow enough that the cookie is only sent to the application that needs it.

The CSRF token cookie may need to be readable by JavaScript, hence `HttpOnly=false` in the double-submit cookie pattern. Keep that readability restricted strictly to the token cookie; never make the session cookie JavaScript-readable.

`SameSite` is an extra defense layer. `Lax` generally allows cookies on certain safe top-level navigations; `Strict` restricts cross-site sending further but may impact login flows coming from external sites. `None` allows cookies in cross-site contexts and requires `Secure`. If the application genuinely needs cross-site cookies, keep CSRF token protection enabled and configure CORS/credentials properly.

Never rely on `SameSite` as the sole reason to disable CSRF. Cookie behavior depends on browsers, site topology, subdomains, and real integration flows.

## 7. Bearer token APIs: when can CSRF be disabled?

An API that only accepts Bearer tokens in the `Authorization` header may not need CSRF protection for that API, because browsers do not automatically attach this token to cross-site requests. Legitimate clients must explicitly obtain and send the token:

```http
GET /api/orders HTTP/1.1
Authorization: Bearer eyJ...
Accept: application/hal+json
```

A malicious form on another website cannot read a token held by an application on another origin to insert it into the `Authorization` header. Under this model, CSRF is not the primary threat for Bearer authentication.

You can configure a dedicated filter chain for a stateless API using only Bearer tokens:

```java
@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain bearerApi(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserApp(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        // Browser chain keeps default CSRF protection.
        return http.build();
    }
}
```

This is a pattern for splitting filter chains. Adjust matchers, authorization, and resource server configuration for your application. The API chain may only disable CSRF when the API genuinely authenticates solely via the Bearer header and does not rely on session cookies, JWT cookies, HTTP Basic, or other automatically sent credentials.

`SessionCreationPolicy.STATELESS` by itself does not render CSRF protection unnecessary. An application may store no HTTP session yet still authenticate via cookies; those cookies are still sent automatically by the browser. Decide whether to enable/disable CSRF based on the credential mechanism, not solely on the label "stateless".

## 8. JWTs in cookies vs. Bearer tokens in headers

Two applications both using JWTs can still have different CSRF exposure:

**JWT in the Authorization header**

The client explicitly sets `Authorization: Bearer ...`. Browsers do not automatically attach the token to requests created by other websites. CSRF generally does not apply to this authentication mechanism.

**JWT in a cookie**

The server sets a JWT in a cookie and the browser automatically sends that cookie to matching domains. A cross-site request can carry that cookie per browser cookie policy. CSRF remains a risk and requires appropriate token protection.

Storing tokens in `localStorage` or `sessionStorage` reduces CSRF exposure because browsers do not send those values automatically like cookies, but makes tokens readable by JavaScript if XSS occurs. No token storage pattern eliminates all risks. Choose based on your threat model; for browser applications, a Backend-for-Frontend (BFF) holding access tokens on the server and using session cookies with CSRF protection is also a common choice.

## 9. How does CSRF differ from CORS and SameSite?

These three mechanisms address related issues but do not replace one another:

| Mechanism | Primary question | Role |
| --- | --- | --- |
| CSRF protection | Was the data-mutating request initiated by a trusted client? | Validates a CSRF token or equivalent request verification mechanism |
| CORS | Does the browser allow JavaScript from another origin to read the response? | Controls cross-origin browser access |
| SameSite cookies | Is the cookie sent in a cross-site context? | Reduces browser cookie transmission in certain cross-site requests |

CORS is not a complete CSRF defense. A cross-origin HTML form can submit certain simple requests without JavaScript needing to read the response. CORS can block scripts from reading responses, yet does not necessarily prevent the request from reaching the server.

SameSite reduces some cross-site requests carrying cookies, but CSRF tokens should still be used for session-based applications per Spring Security guidance. You can add `Origin` or `Referer` checks as defense in depth, yet should not replace token protection solely with those header checks.

## 10. CORS and CSRF for cross-origin SPAs

If the SPA and Spring Data REST run on different origins, such as `https://app.example.com` and `https://api.example.com`, configure CORS explicitly.

For cookie/session requests, the client must send credentials and the server must allow the specific origin along with credentials. Never use a wildcard origin when credentials are enabled. Also allow the CSRF header sent by the client, such as `X-XSRF-TOKEN`.

Illustrative CORS configuration example:

```java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://app.example.com"));
    config.setAllowedMethods(
        List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
    config.setAllowedHeaders(
        List.of("Content-Type", "Accept", "X-XSRF-TOKEN"));
    config.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", config);
    return source;
}
```

Enable CORS in Spring Security:

```java
http.cors(Customizer.withDefaults());
```

Client sending cookies:

```javascript
fetch("https://api.example.com/api/orders", {
    method: "POST",
    credentials: "include",
    headers: {
        "Content-Type": "application/json",
        "X-XSRF-TOKEN": csrfToken
    },
    body: JSON.stringify(order)
});
```

For JavaScript to read a CSRF cookie from the API origin, cookie domain/path and frontend deployment topology must be designed appropriately. A host-only cookie on the API origin cannot be read directly by JavaScript on a different origin. You can provide a token bootstrap endpoint or deploy a same-origin BFF/reverse proxy to simplify token sharing.

CORS must handle OPTIONS preflight requests before the actual operation runs. The CSRF token is still required on the actual write request. Align CORS configurations across Spring Security and Spring Data REST so one layer does not permit what another layer blocks.

## 11. CSRF with Spring Data REST endpoints

Spring Data REST automatically generates repository endpoints. If these endpoints are accessed using session cookies, keep CSRF protection for write operations:

| Operation | Example | CSRF token |
| --- | --- | --- |
| Read collection | `GET /api/orders` | Not required |
| Read item | `GET /api/orders/42` | Not required |
| Create resource | `POST /api/orders` | Required when using cookies/sessions |
| Replace resource | `PUT /api/orders/42` | Required when using cookies/sessions |
| Partial update | `PATCH /api/orders/42` | Required when using cookies/sessions |
| Delete resource | `DELETE /api/orders/42` | Required when using cookies/sessions |

Never turn GET into a data-mutating operation. If GET has side effects, the application breaks HTTP semantics and makes caching, crawlers, prefetching, and CSRF protection unpredictable.

If the API uses a Spring Data REST base path, matchers must reflect the actual URLs. When splitting filter chains, verify custom controllers and repository endpoints both land in chains with the right authentication/CSRF policies.

## 12. Special endpoints to watch

**Login and logout:** CSRF can also apply to login/logout actions. Do not arbitrarily exempt login/logout endpoints from protection. When login or logout rotates tokens/sessions, the SPA must fetch the new token before the next write request.

**CSRF token retrieval endpoint:** An SPA may need an initial GET request for the server to generate a token and set the cookie/representation. This endpoint must not perform business mutations. Ensure the token is initialized prior to POST/PUT/PATCH/DELETE requests.

**File uploads:** Multipart requests are also state-changing requests and require a CSRF token. Spring Security supports appropriate mechanisms for sending tokens on multipart requests; consider filter ordering and file size limits.

**WebSockets or other protocols:** Do not assume the HTTP CSRF filter protects every handshake or message. Check the protocol's own authentication and origin validation mechanisms.

## 13. Diagnosing 403 errors caused by CSRF

If a write request returns `403 Forbidden`, check:

1. Is the application using session cookies or automatically sent credentials?
2. Has a CSRF token been issued to the browser?
3. Does the token cookie exist with the right domain/path without having been cleared?
4. Is the client sending the right header name: `X-CSRF-TOKEN` or `X-XSRF-TOKEN` depending on the repository?
5. Does the header token match the token stored in the session/cookie?
6. Did the token change after login/logout or session rotation?
7. With Spring Security 6 SPAs, does the request handler handle raw cookie tokens and XOR tokens properly?
8. Is the request routed through the expected SecurityFilterChain?
9. Do CORS/preflight settings allow the required custom headers and credentials?

Enable Spring Security logging in development to see whether the CSRF filter rejected the request due to a missing or mismatched token. Never log CSRF tokens, session IDs, or access tokens in production logs. A 403 response can also originate from authorization; check logs to separate CSRF failures from missing permissions.

## 14. Strategy selection checklist

**Browser applications using session cookies**

- Keep Spring Security's default CSRF protection enabled.
- Use `HttpOnly`, `Secure`, and appropriate `SameSite` attributes on session cookies.
- For server-rendered forms, render the token in a hidden field.
- For SPAs, use a CSRF cookie or bootstrap endpoint and send the token in a header.
- Refresh the token after login/logout when required by your version's flow.
- Never disable CSRF simply because endpoints return JSON or are called a REST API.

**APIs using only Bearer tokens**

- Accept tokens solely in the `Authorization` header.
- Do not allow session cookies/JWT cookies/HTTP Basic as fallback credentials in the same filter chain.
- Use a stateless session policy if appropriate.
- You may disable CSRF in the dedicated filter chain for this API.
- Protect tokens from XSS and check authorization on every request.
- Maintain an explicit CORS allowlist if browser clients call the API cross-origin.

**Applications combining browser sessions and API tokens**

- Separate SecurityFilterChain instances with explicit request matchers and ordering.
- Keep CSRF protection enabled on the browser chain.
- The Bearer-only API chain may disable CSRF when meeting the no-ambient-credentials condition.
- Prevent URL overlap that could route requests into the wrong chain.
- Test POST/PATCH/DELETE with both session cookies and Bearer tokens.

## Summary

- CSRF exploits credentials automatically sent by browsers; REST/JSON does not automatically exempt an API from CSRF.
- Session cookies and JWTs in cookies need CSRF protection for state-changing requests.
- Spring Security enables CSRF by default; keep protection enabled for session-based Spring Data REST.
- SPAs can use `CookieCsrfTokenRepository` with the `XSRF-TOKEN` cookie and `X-XSRF-TOKEN` header; session cookies should remain HttpOnly.
- Spring Security 6 uses deferred/XOR token handling; SPAs need a compatible request handler and token refresh flow.
- APIs accepting only Bearer tokens explicitly placed in `Authorization` generally do not need CSRF; it can be disabled in a dedicated stateless filter chain.
- `STATELESS` alone does not prove CSRF is unnecessary; a JWT in a cookie is still an ambient credential.
- CORS and SameSite are distinct mechanisms; they complement but do not replace CSRF tokens.
- Keep CSRF for POST/PUT/PATCH/DELETE under cookie/session authentication and diagnose 403s across tokens, cookies, handlers, filter chains, and CORS.

## References

- [Spring Security — Cross Site Request Forgery (CSRF)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — CSRF protection for JavaScript applications](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html#csrf-integration-javascript)
- [Spring Security — CookieCsrfTokenRepository API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/csrf/CookieCsrfTokenRepository.html)
- [Spring Security — Multiple HttpSecurity instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html#_multiple_httpsecurity_instances)
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html)
- [OWASP Cheat Sheet — Cross-Site Request Forgery Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
