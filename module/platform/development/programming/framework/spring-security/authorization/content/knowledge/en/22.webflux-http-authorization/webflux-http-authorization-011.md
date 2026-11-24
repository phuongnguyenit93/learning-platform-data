# CORS, CSRF, and Request Scope in Reactive Applications

## 1. Goal and WebFlux context

Spring WebFlux applications often serve web frontends (SPAs), JSON APIs, upload/download endpoints, data streams, and service-to-service clients. When the frontend runs on `https://app.example.test` and the API on `https://api.example.test`, browsers enforce the **Same-Origin Policy** and CORS; if the browser automatically sends cookie/session credentials, state-changing requests also face **CSRF**. In WebFlux, request data flows through `ServerWebExchange` and **Reactor Context**, unlike Servlet's thread-local approach.

These three topics are related yet solve **three distinct problems**:

| Mechanism | Primary question | Target |
|---|---|---|
| **CORS** (Cross-Origin Resource Sharing) | Which origins are allowed by the browser to read API responses in JavaScript? | Browsers, response headers, and preflight |
| **CSRF** (Cross-Site Request Forgery) | Is the browser sending an unintended state-changing request merely because it attaches credentials automatically? | Requests with ambient credentials such as cookies/sessions, or Basic in relevant scenarios |
| **Request context/scope** | Where are identity, tenant, correlation ID, and **this request's** data held/propagated in the reactive pipeline? | `ServerWebExchange`, Reactor Context, `Authentication`, `WebSession` |

CORS is **not** authentication or object authorization. A CSRF token is **not** a role/authority to view data. Request context **does not verify** a tenant/subject simply because they appeared in a header.

This guide focuses on **Spring Security WebFlux**: `ServerHttpSecurity`, `SecurityWebFilterChain`, `CorsWebFilter`, `CsrfWebFilter`, `WebSession`, and `ReactiveSecurityContextHolder`. Do not mistakenly copy `HttpSecurity`, `SecurityFilterChain`, or Servlet `CorsFilter` from MVC tutorials.

## 2. Illustrative request flow

~~~text
Browser (origin app.example.test)
    |
    | OPTIONS preflight (when needed)
    v
WebFlux CORS processing / CorsWebFilter
    |   - check Origin
    |   - check requested method and headers
    |   - return CORS preflight response or reject
    |
    | Actual GET/POST/PUT/DELETE
    v
Spring Security WebFilterChain
    |   - CSRF token check when request is protected
    |   - authentication and request authorization
    v
Handler / reactive service
    |   - verified actor + tenant + resource policy
    |   - Reactor Context / ServerWebExchange attributes
    v
Reactive repository / side effect
    |
    v
Response + CORS response headers
    |
Browser decides whether JavaScript may read the response
~~~

This is a **conceptual diagram**, not a guarantee of absolute `WebFilter` ordering in every project. What matters is that **CORS preflight runs before authentication**, because preflights normally carry neither cookies nor bearer tokens. CSRF is checked on configured actual unsafe requests, while the service still enforces object-level authorization before reading or writing data.

An actual request can be **accepted by CORS** while simultaneously **rejected by CSRF or authorization**. That is normal, not a sign that CORS "hasn't allowed it yet."

## 3. Origin is scheme + host + port

Two URLs share an origin when scheme, host, and port match:

~~~text
https://app.example.test            <- origin A
https://app.example.test/dashboard  <- origin A
https://api.example.test            <- origin B, different host
http://app.example.test             <- origin C, different scheme
https://app.example.test:8443       <- origin D, different port
~~~

The browser sends:

~~~http
Origin: https://app.example.test
~~~

The server may reply:

~~~http
Access-Control-Allow-Origin: https://app.example.test
~~~

When the request uses browser credentials and the server permits it, the response also needs:

~~~http
Access-Control-Allow-Credentials: true
~~~

**Origin is neither a tenant nor an identity.** An `Origin` header can be crafted or spoofed by non-browser HTTP clients. Never build authorization like "Origin is the admin app so the user automatically has `ROLE_ADMIN`." Browsers enforce CORS; `curl` or backend services can call APIs without browser JavaScript restrictions.

Also distinguish **same-origin** from **same-site**: two subdomains can be different origins yet the same site under browser and `SameSite` cookie rules. `SameSite` is a cookie defense-in-depth attribute and **does not replace** CORS, CSRF, or resource authorization checks.

## 4. CORS does not stop all requests from reaching the server

The Same-Origin Policy primarily restricts **cross-origin response reading by scripts** and certain interactions. A malicious site can still make a browser send cross-site requests under normal HTTP rules, such as submitting an HTML form. Therefore:

- Never think "I configured CORS to deny `evil.com`, so CSRF is impossible."
- Never rely on `Origin` as the sole way to authenticate a subject.
- Never enable CORS unconditionally for all origins just because an API uses Bearer tokens.
- Never use CORS response headers in place of `hasAuthority`, `@PreAuthorize`, or `tenant + resource ID` scoping.

For example, suppose a user is logged into `api.example.test` via a session cookie. A malicious site can submit a hidden HTML form POST to the API; even if the browser blocks its script from reading the response, the request may **already have executed**. CSRF protection must reject forged requests lacking a valid token **before data is modified**.

Conversely, a valid request with a Bearer token whose `Origin` is not on the allowlist can complete on the server while the browser stops the frontend from reading the response. CORS acts inside browser enforcement, not as a new authentication mechanism.

## 5. What is preflight, and when does it happen?

A browser can send an `OPTIONS` request before a cross-origin actual request requiring preflight, such as a JSON POST carrying a custom CSRF header:

~~~http
OPTIONS /api/documents/42 HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

This is a **preflight**, not the real POST. It asks the server: "If a script from this origin sends a POST with these headers, will CORS permit it?" The server responds accordingly:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET,POST,PUT,DELETE
Access-Control-Allow-Headers: Content-Type,X-CSRF-TOKEN
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 1800
Vary: Origin
~~~

The exact status code can vary by implementation; **do not assume** every successful preflight returns 200 (some servers return 204). The browser checks the CORS headers and sends the actual request only if they match.

**Preflights typically carry no cookie/session authentication**, and are not POST mutations. Hence, if `SecurityWebFilterChain` demands login before CORS runs, preflights fail with 401/403 and the actual request never gets a chance. Spring Security docs emphasize that CORS must be processed **before security**. See [Spring Security Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html).

### Browsers do not preflight every request

Certain GETs and form POSTs meeting the "simple request" criteria are sent directly without preflight. No preflight **does not mean CORS skips the response**, and certainly does not mean CSRF can be skipped.

CORS preflight caching (`Access-Control-Max-Age`) reduces OPTIONS traffic, yet it is not an authentication or CSRF token lifetime. The browser caches CORS consent, not ownership of Document #42.

## 6. Common CORS headers

| Header | Direction | Meaning |
|---|---|---|
| `Origin` | Browser → server | Origin of the script issuing the request |
| `Access-Control-Request-Method` | Preflight → server | Intended HTTP method |
| `Access-Control-Request-Headers` | Preflight → server | Headers the script wants to send |
| `Access-Control-Allow-Origin` | Server → browser | Origin permitted by CORS to read the response |
| `Access-Control-Allow-Methods` | Preflight response | Accepted methods |
| `Access-Control-Allow-Headers` | Preflight response | Accepted custom request headers |
| `Access-Control-Allow-Credentials` | Response | Allows browser to expose credentialed responses when true and other conditions hold |
| `Access-Control-Expose-Headers` | Response | Non-default response headers JavaScript is allowed to read |
| `Access-Control-Max-Age` | Preflight response | Duration the browser caches preflight results, capped by the browser |
| `Vary: Origin` | Response/cache | Helps caches vary CORS responses by `Origin` when needed |

**Do not confuse `Allow-Headers` with `Expose-Headers`:** the former controls which request headers may be sent; the latter controls which response headers JavaScript may read.

When using a CDN or reverse-proxy cache, verify CORS response headers, `Vary`, credentialed responses, and cache keys. A config that returns `Access-Control-Allow-Origin` by **blindly echoing any `Origin`** exposes data to other websites whenever the browser sends cookies.

## 7. Configuring WebFlux with `CorsWebFilter`

In Spring WebFlux, you can configure `CorsWebFilter` with `CorsConfiguration` and `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`. Example assuming a known frontend origin:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsWebFilter;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
public class ReactiveCorsConfiguration {

    @Bean
    CorsWebFilter corsWebFilter() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(
                List.of("https://app.example.test"));
        cors.setAllowedMethods(
                List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
        cors.setAllowedHeaders(
                List.of("Content-Type", "X-CSRF-TOKEN",
                        "X-XSRF-TOKEN", "Authorization"));
        cors.setExposedHeaders(List.of("X-Request-ID"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return new CorsWebFilter(source);
    }
}
~~~

This is a **WebFlux integration configuration class**, requiring Spring WebFlux, Spring Security, and application dependencies. Both origins are illustrative names, not real addresses.

Explanation of choices:
- `setAllowedOrigins` allowlists the specific origin instead of allowing every site.
- `setAllowedMethods` lists methods the frontend actually uses; that does not mean business authorization allows all of them.
- `setAllowedHeaders` covers headers the frontend needs for JSON and CSRF.
- `setAllowCredentials(true)` applies when the browser needs cross-origin cookies/sessions **and** you intentionally trust that origin.
- `setExposedHeaders` exposes only an observability response header; **never expose `Authorization`, `Set-Cookie`, or tokens**.
- `registerCorsConfiguration("/api/**",...)` scopes the policy to API paths rather than opening all endpoints.
- `CorsWebFilter` handles CORS requests and preflights in WebFlux.

**Do not register multiple conflicting CORS mechanisms** (`CorsWebFilter`, global WebFlux mappings, `@CrossOrigin`, gateway) without checking the final headers. If a gateway also injects headers, duplicate/invalid `Access-Control-Allow-Origin` values can break browsers. Pick a single owner for CORS policy and integration-test through the real ingress stack.

## 8. CORS and WebFlux `SecurityWebFilterChain` are two separate layers

A filter chain for cookie/session API requests:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveSecurityConfiguration {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/documents/**")
                    .hasAuthority("documents:read")
                .pathMatchers(HttpMethod.POST, "/api/documents/**")
                    .hasAuthority("documents:write")
                .anyExchange().denyAll()
            )
            // Do not disable CSRF: enabled by default.
            .build();
    }
}
~~~

This is a **Spring Security WebFlux snippet**, not a complete app: it lacks an authentication provider, endpoints, and login configuration. It demonstrates functional authority checks on GET/POST and does not check owner/tenant on Document #42.

When the frontend sends a cookie/session POST:
1. The CORS filter validates origin, method, and headers per policy.
2. Security checks the CSRF token if the POST is protected.
3. Security authenticates the actor and checks authority `documents:write`.
4. The service checks tenant, object ID, owner/grant, and data state.
5. Only if all pass does the mutation execute.

If POST returns 403, determine whether **CSRF, authentication/authority, or business policy** caused it. Never disable CSRF or switch to `permitAll` the moment you see 403.

### CORS with multiple chains or a gateway

An application may have multiple `SecurityWebFilterChain`s, especially when separating Bearer APIs, admin sessions, actuator, and public paths. CORS must apply properly **to every route browsers use**, not just the first chain. Test every combination:
- Allowed and disallowed origins.
- Preflights with and without authentication.
- Cookie/session versus bearer.
- HTTP methods and custom headers.
- Gateway-rewritten routes.
- Intentional `denyAll` or `authenticated` fallback rules.

## 9. Credentialed CORS: never pair `allowCredentials` with `"*"` origin

For cross-origin browser requests using cookies:

~~~text
Access-Control-Allow-Credentials: true
Access-Control-Allow-Origin: https://app.example.test
~~~

The origin must be specified explicitly; never configure:

~~~java
cors.setAllowedOrigins(List.of("*"));
cors.setAllowCredentials(true);
~~~

This is an **invalid pattern** under Spring CORS and browser credential rules. Spring Framework forbids the special wildcard `"*"` in `allowedOrigins` when credentials are enabled. `allowedOriginPatterns` exists for dynamic matching, yet it must still be tightly bounded and never serve as a wildcard for untrusted origins.

Credentialed CORS lets allowlisted websites **read personalized responses** from the API when the browser sends cookies. Therefore:
- Allowlist only controlled frontend origins.
- Guard against DNS/subdomain takeovers, preview-deployment domains, and stale origins.
- Never echo arbitrary `Origin` headers with `allowCredentials`.
- Never map `Origin` into user/tenant authorization.
- Set `Secure`, `HttpOnly`, `SameSite`, domain, and path appropriately on cookies.
- Use TLS for real frontends and APIs; avoid mixed content.
- If public CORS only serves public data, `allowCredentials` may not be needed at all.

Do not assume CORS enables cookies merely because the server returns `allowCredentials`: browsers also enforce `SameSite`, third-party cookie rules, and fetch `credentials` mode.

## 10. Combining with `@CrossOrigin` and `WebFluxConfigurer`

Spring WebFlux can also declare CORS on handler mappings:
- `@CrossOrigin` on controllers or methods.
- `WebFluxConfigurer.addCorsMappings(...)` for global path mappings.
- `CorsWebFilter` across the entire web filter pipeline.

All three address CORS, yet **execute at different positions**. Spring Framework WebFlux docs describe combining global and local configs (combining certain fields while local overrides others).

Mapping example:

~~~java
@Configuration
public class WebFluxCorsMappings implements WebFluxConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/public/**")
            .allowedOrigins("https://docs.example.test")
            .allowedMethods("GET");
    }
}
~~~

This is an integration snippet requiring imports and WebFlux runtime. In Spring Security apps, never rely solely on annotation/controller mappings for preflight without **verifying CORS runs before security filters**. `CorsWebFilter` is the clear choice for routes whose preflights must pass through security.

Avoid declaring two conflicting policies on the same path and relying on accidental precedence. Maintain one source of truth and test actual responses through gateway, security, and handler mappings.

## 11. What is CSRF: a valid cookie does not prove user intent

A classic attack:

~~~text
1. Alice logs into https://api.example.test
2. Browser stores a valid session cookie
3. Alice visits https://evil.example
4. Evil page auto-submits a POST form to the API
5. Browser may automatically attach the matching cookie
6. If the API only checks session/role:
   the server treats the request as Alice's and performs the change
~~~

**CSRF** exploits credentials attached automatically by the browser (*ambient authority*). To prevent it, the server requires an anti-forgery token that an attacker's site **cannot read or forge** merely by triggering a cross-site request.

A CSRF token is a primary defense. The browser must submit the token in a **header or form field** that is not generated automatically in forged requests. The server compares it against the expected managed token. The token does not replace authentication and does not grant resource access if role, owner, or tenant checks fail.

Protection also requires:
- Never performing state mutations via GET/HEAD/OPTIONS.
- Setting cookie `SameSite`/`Secure`/`HttpOnly` per context.
- Using `Origin`/`Referer` checks carefully where designed, without carelessly replacing tokens.
- Defending against XSS, because malicious scripts on a trusted origin can read tokens or act as the user.
- Enforcing per-action and per-resource authentication/authorization regardless.

**Having CORS does not mean having CSRF protection.** CSRF is a separate security layer.

## 12. Safe HTTP methods must truly be read-only

Spring Security applies CSRF by default to methods deemed unsafe; methods such as `GET`, `HEAD`, `OPTIONS`, and `TRACE` are considered safe by the default matcher. This relies on the assumption that **safe methods do not mutate state**.

If an API uses:
~~~http
GET /api/accounts/42/delete
~~~
to delete an account, that is a dangerous design: browsers, crawlers, prefetches, or crafted links can trigger the side effect while bypassing the default CSRF guard.

Instead:
~~~http
DELETE /api/accounts/42
X-CSRF-TOKEN: <token-if-cookie-auth>
~~~

and the service must enforce DELETE permission on that exact account.

A JSON POST can still need CSRF if the browser attaches cookies/sessions automatically; sending `Content-Type: application/json` does not waive CSRF. Content-type affects CORS/preflights, **not the threat model** of ambient credentials.

### Common misconception

"Any POST that passed preflight must be safe" is false. Preflight only checks CORS origin/method/headers; it does not verify the actual request carries a valid CSRF token. Even from an allowed origin, XSS or frontend bugs can submit dangerous requests.

## 13. Default CSRF in Spring Security WebFlux

In Spring Security WebFlux, CSRF protection is **enabled by default**. Main components:

| Component | Role |
|---|---|
| `CsrfWebFilter` | Checks whether a request requires CSRF, loads and compares expected vs presented tokens |
| `ServerCsrfTokenRepository` | Contract for generating/saving/loading CSRF tokens in WebFlux |
| `WebSessionServerCsrfTokenRepository` | Default repository storing the expected token in `WebSession` |
| `CookieServerCsrfTokenRepository` | Stores the token in a cookie, often for JS frontends |
| `ServerCsrfTokenRequestHandler` | Exposes the token in exchange attributes and resolves presented values |
| `XorServerCsrfTokenRequestAttributeHandler` | Default handler since Spring Security 6.0, mitigating BREACH via masking |
| `ServerCsrfTokenRequestAttributeHandler` | Alternative handler when considering compatibility/masking trade-offs |

CSRF tokens are managed reactively. `CsrfWebFilter` exposes a `Mono<CsrfToken>` inside `ServerWebExchange` attributes under key `CsrfToken.class.getName()` per documentation.

**Three distinct locations:**
- `WebSession`: where the **expected token** may persist across requests.
- `ServerWebExchange attribute`: how the **current** request accesses the token publisher.
- `Reactor Context`: how reactive execution carries per-subscription context; not a default token repository.

Never store expected tokens in a singleton field shared across users. Never serialize entire `WebSession` or token values into logs.

## 14. Token masking and BREACH in newer versions

Spring Security WebFlux documentation notes:
- Spring Security 5.8 used `ServerCsrfTokenRequestAttributeHandler` by default.
- Since Spring Security 6.0, the default is `XorServerCsrfTokenRequestAttributeHandler` to help mitigate BREACH.

BREACH involves leaking secrets via compressed response size correlation when tokens appear in response bodies. XOR-based masking ensures the **exposed** value varies across requests even while the underlying expected token stays managed by the repository.

Therefore, distinguish:
1. **Expected token** in `WebSession`/cookie repository.
2. **Exposed/masked token** rendered into forms/templates.
3. **Presented token** in a header or form field when a user submits a POST.
4. **Request handler** decoding/resolving the presented token per configured mechanism.

If an SPA reads the **raw `XSRF-TOKEN` cookie** and sends it verbatim in a header, verify how your Spring Security version's `XorServerCsrfTokenRequestAttributeHandler` handles it. A setup where JS reads a cookie and sends a raw header may need an **appropriate custom request handler** that accepts raw cookie tokens in headers while keeping response masking intact. Never downgrade to an unmasked handler just to silence errors without evaluating BREACH protection.

Only use tokens matching your project's CSRF request handler contract. Test real browser flows across login, logout, and JSON requests.

## 15. HTML form pages: placing the CSRF token in a form field

For server-rendered pages:
~~~html
<form method="post" action="/api/profile">
  <input type="hidden" name="_csrf" value="csrf-token-from-server">
  <button type="submit">Save</button>
</form>
~~~

This is **illustrative HTML**; the actual value must be injected by the framework/template from the current request token, never hardcoded in source. With Thymeleaf integrated with Spring Security, the hidden form field can be added automatically when configured properly.

In WebFlux, the token can be read from `ServerWebExchange`:

~~~java
import reactor.core.publisher.Mono;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.server.ServerWebExchange;

public Mono<CsrfToken> csrfToken(ServerWebExchange exchange) {
    Mono<CsrfToken> token =
            exchange.getAttribute(CsrfToken.class.getName());
    return token != null ? token : Mono.empty();
}
~~~

This is an **integration snippet inside a WebFlux component/controller**, requiring Spring Security CSRF enabled; never treat `Mono.empty()` as a valid token. On an endpoint meant to expose the token, handle missing token publishers cleanly per design instead of returning a random string or disabling CSRF.

Never put CSRF tokens in URL query strings, where they leak via browser history, `Referer` headers, proxy logs, and analytics. Prefer hidden form fields or headers. When HTML responses embed tokens, control caching and XSS carefully.

## 16. AJAX/JSON: CSRF tokens typically go in headers

Frontend sends an actual POST:

~~~http
POST /api/documents/42 HTTP/1.1
Origin: https://app.example.test
Content-Type: application/json
Cookie: SESSION=...
X-CSRF-TOKEN: <token-from-trusted-ui>

{"title":"Updated title"}
~~~

The server must:
1. Process CORS per origin/method/headers.
2. Validate the authentication cookie/session.
3. Match the presented CSRF token against the expected token.
4. Check `DOCUMENT_WRITE` authority and object authorization on Document #42.
5. Execute the transaction only if all checks pass.

Missing CSRF token ⇒ session/cookie POSTs can fail with **403** before any business service runs. Valid CSRF token yet caller lacks WRITE permission ⇒ still **403/404** per policy. CORS accepting an origin never turns a bad token into a valid one.

For SPAs:
- Use `X-CSRF-TOKEN` or `X-XSRF-TOKEN` depending on your repository/request handler.
- Obtain the token via a trusted channel on the allowed site/origin.
- A JS-readable cookie is a trade-off requiring strong CSP/XSS defenses and cookie scoping.
- On login/logout, session/tokens can rotate; the client must refresh its token.
- `fetch` calls need matching `credentials` mode when the API relies on cookies and CORS `allowCredentials`.
- If Axios/Angular reads cookies automatically, verify exact raw vs masked token behavior for your Spring Security version.
- Never log cookies, CSRF headers, or JSON bodies holding sensitive data.

## 17. `CookieServerCsrfTokenRepository`: reading from `XSRF-TOKEN`

When an SPA needs the token via a cookie, Spring Security provides `CookieServerCsrfTokenRepository`:

~~~java
import org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository;

@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .csrf(csrf -> csrf.csrfTokenRepository(
                CookieServerCsrfTokenRepository.withHttpOnlyFalse()))
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/**").authenticated()
            .anyExchange().denyAll()
        )
        .build();
}
~~~

**Integration snippet**, not a complete production configuration. `withHttpOnlyFalse()` lets JavaScript read the token cookie; Spring Security docs advise **against** this option when JavaScript does not need direct cookie access. Use `new CookieServerCsrfTokenRepository()` to keep `HttpOnly`.

Default conventions:
- Cookie: `XSRF-TOKEN`.
- Header: `X-XSRF-TOKEN`.
- Form parameter: `_csrf` where supported.

**Important compatibility point:** this snippet only configures **saving the token in a cookie**; it does not prove an SPA sending a raw header will be accepted by Spring Security 6+'s default XOR handler. For cookie-to-header flows, configure an appropriate `ServerCsrfTokenRequestHandler` and integration-test the entire flow; you may need a handler that reads raw header tokens while masking tokens in HTML. Do not copy Servlet's `SpaCsrfTokenRequestHandler` into a Reactive project without adapting types.

Never enable `withHttpOnlyFalse()` as a blanket "fix all CSRF errors" trick. It alters JS cookie visibility and has security consequences; evaluate your XSS threat model first.

## 18. `WebSession` is not Reactor Context or a request attribute

Three concepts frequently mixed up:

| Object | Typical scope | What to store | Warning |
|---|---|---|---|
| `ServerWebExchange` | One HTTP exchange/request-response | Request metadata, attributes for filters/handlers | Never reuse instances across requests |
| `exchange.getAttributes()` | Attributes bound to current exchange | Correlation ID, verified request analysis results | Client-supplied headers do not automatically become trusted |
| `Reactor Context` | One subscriber/reactive chain | Security context, tracing/correlation, data flow scope | Not a `ThreadLocal`; depends on subscription/context propagation |
| `WebSession` | Multi-request session state | Session-ID-bound state, default expected CSRF token | Do not store stale unbounded domain objects/roles |
| `SecurityContext` | Active `Authentication` | Principal/authorities produced by auth pipeline | Does not prove resource-level permission by itself |
| Singleton Spring bean | Whole app instance | Immutable dependencies, stateless services | Never put mutable `currentUser`/`currentTenant` fields |

**Request scope ≠ `WebSession` scope.** One request finishing does not end the `WebSession`, and one user/session can fire concurrent requests. Never write fields like:

~~~java
private String currentTenant;
private Authentication currentUser;
~~~

on a singleton `@Service` or `@Component` to track the "current request." Concurrent requests will overwrite one another's state. Pass verified context via method parameters, exchange attributes, or Reactor Context as appropriate.

Do not assume a Servlet `RequestContextHolder`/`HttpServletRequest` `ThreadLocal` exists in WebFlux; reactive execution can hop threads and use multiple subscriptions. Nor should `@RequestScope`/scoped proxies be assumed identical to Servlet request binding without verifying support and lifecycle in your WebFlux setup. Prefer explicit reactive mechanisms and test propagation.

## 19. `ReactiveSecurityContextHolder` and Reactor Context

Spring Security WebFlux uses Reactor Context to propagate security context along the reactive chain instead of relying solely on a single `ThreadLocal` from start to finish.

Example reading the principal:

~~~java
import reactor.core.publisher.Mono;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

public Mono<String> currentSubject() {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
}
~~~

This is a **Reactor/Spring Security integration snippet**, not a standalone runnable class. If the publisher lacks a security context, it may emit `Mono.empty()`. For operations requiring authentication, **never turn empty into a default user**.

Custom services should receive `Mono<Authentication>` or the principal from verified methods whenever possible rather than reading raw headers. For role checks, WebFlux HTTP managers and reactive method security use the authenticated context; domain services still check tenant/object access.

### Reactor Context is not a global variable

~~~java
Mono<String> operation = Mono.deferContextual(ctx -> {
    String requestId = ctx.getOrDefault(
            "trusted.requestId", "not-set");
    return Mono.just(requestId);
});

Mono<String> withContext = operation.contextWrite(
        ctx -> ctx.put("trusted.requestId", "req-123"));
~~~

This is a **reactive Java snippet** usable inside a configured Reactor program. `contextWrite` creates a context scoped by subscription/upstream semantics, not a global variable shared across requests.

A context entry is only **data**: placing `tenantId=north` into Reactor Context does not prove the actor belongs to `north`. The authentication/tenant resolver must verify membership before placing it into trusted context.

## 20. `WebFilter` attaching a per-exchange correlation ID

Example of a single-responsibility filter: generating a request ID and propagating it in exchange attributes + Reactor Context for async processing.

~~~java
import java.util.UUID;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(-100)
public class RequestCorrelationWebFilter implements WebFilter {

    public static final String REQUEST_ID_KEY = "trusted.requestId";

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {
        String requestId = UUID.randomUUID().toString();

        exchange.getAttributes().put(REQUEST_ID_KEY, requestId);
        exchange.getResponse().getHeaders().set("X-Request-ID", requestId);

        return chain.filter(exchange)
            .contextWrite(ctx -> ctx.put(REQUEST_ID_KEY, requestId));
    }
}
~~~

This is an **integration Spring WebFlux class**, without application config or tests. `@Order(-100)` only illustrates precedence; verify actual ordering against your project's security/CORS filters rather than assuming a magic number guarantees every filter relationship.

Benefits:
- No mutable singleton fields holding IDs.
- Server-generated request ID, never trusting arbitrary client `X-Request-ID` headers.
- Reactive handlers/services can read it from exchange attributes or `Mono.deferContextual`.
- Enables auditing and tracing without logging credentials.

**Note:** adding a correlation ID to a response header does not automatically let cross-origin JS frontends read it. If needed, list it in `Access-Control-Expose-Headers`. The header must contain no secrets or permissions.

Never place expected CSRF tokens, raw JWTs, or sensitive data into context or response headers just for debugging. Nor is a correlation ID a capability granting access to view logs; lookup endpoints require their own authorization.

## 21. Per-request tenant must come from an authenticated scope

Consider a request:

~~~http
GET /api/tenants/north/documents/42
X-Tenant-ID: north
Authorization: Bearer <access-token>
Origin: https://app.example.test
~~~

Three distinct values:
- `Origin`: browser CORS context, **does not verify roles**.
- `X-Tenant-ID` or path tenant: **target tenant chosen by the client**.
- `Authorization`: token that the resource server must validate; only validated identity/claims may be trusted.

A safe resolver:
1. Extract the authenticated issuer+subject or internal principal.
2. Read the target tenant from path/header with proper format/allowlist validation.
3. Look up the actor's active membership/entitlement in the target tenant.
4. Bind role/authority checks **within that specific tenant**.
5. When fetching Document #42, query `id AND tenant AND owner/allowedScope`.
6. When writing, use scoped mutations or proper transaction/lock/version policies.

Never do `currentTenant = request.getHeaders().getFirst("X-Tenant-ID")` and treat it as a trusted tenant for RLS queries without verification.

**An allowed CORS origin does not grant membership:** a legitimate frontend can still have a logged-in user who does not belong to `north`. Nor does a valid CSRF token grant membership; it only defends against forged requests within its threat model.

## 22. Avoiding context leaks across subscriptions, caches, and async boundaries

A reactive service easily breaks if it caches a whole `Mono<Authentication>`, `Mono<Document>`, or `SecurityContext` on a singleton shared across requests.

Anti-pattern:

~~~java
@Service
public class UnsafeContextCache {
    private Mono<String> cachedUser;

    public Mono<String> userName() {
        if (cachedUser == null) {
            cachedUser = ReactiveSecurityContextHolder.getContext()
                .map(ctx -> ctx.getAuthentication().getName())
                .cache();
        }
        return cachedUser;
    }
}
~~~

This is a **broken pattern**: caching a publisher of one subscription's security context and reusing it for another caller. Even with reactive context isolation, **`.cache()` on a shared publisher** can turn one actor's data into another's if scoped improperly.

Fixes:
- Resolve subject/tenant **per request/subscription**.
- Pass `VerifiedActor`/`VerifiedTenantScope` via method parameters or isolated per-request context.
- Never apply global `.cache()` to user/tenant/action-dependent results.
- If caching authorization data, key by issuer+subject+tenant+action+resource+revision with appropriate TTL and revocation.
- Never call `subscribe()` manually inside authorization services; let the framework manage subscriptions and context.
- When switching Reactor Schedulers or threads, test context propagation rather than relying on `ThreadLocal`.
- For non-reactive callbacks, pass verified context explicitly via controlled messages/commands rather than stale thread-locals.

## 23. CSRF with JWT Bearer tokens differs from cookie sessions

You may consider disabling CSRF for a **truly stateless** API when:
- Clients send Bearer tokens explicitly in the `Authorization` header.
- Browsers **do not automatically** attach those credentials on cross-site requests like cookies or browser-managed Basic auth.
- No session/cookie auth fallback exists on the same protected routes.
- No CSRF-sensitive cookie-based authentication/refresh/logout endpoints with side effects exist.
- No other ambient credentials (client certificates, proxy auth/cookie flows) are present in the threat model.
- CORS and object authorization remain properly enforced.

Separate example for a **verified stateless Bearer-only resource API**:

~~~java
import static org.springframework.security.config.Customizer.withDefaults;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class BearerOnlyApiSecurity {

    @Bean
    SecurityWebFilterChain bearerApi(ServerHttpSecurity http) {
        return http
            .csrf(csrf -> csrf.disable())
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("SCOPE_reports.read")
                .pathMatchers(HttpMethod.POST, "/api/reports/**")
                    .hasAuthority("SCOPE_reports.write")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

**Illustrative configuration, not a recommendation to disable CSRF by default.** Apply this only after verifying all conditions above, confirming your Spring Security/Boot versions, configuring issuer/JWK/audience, and testing thoroughly. If the same app also uses form login, cookie sessions, SPA refresh cookies, or Basic auth, do not copy `csrf.disable()` blindly across every filter chain.

Additionally, JWTs can be stored in cookies; once a token is auto-sent by the browser in a cookie, **it becomes an ambient credential again** and CSRF risk returns. How the token is transmitted matters more than calling it a "JWT."

## 24. How do `SameSite`, `HttpOnly`, and `Secure` cookies help?

A session cookie can be configured with suitable attributes:

~~~http
Set-Cookie: SESSION=opaque-session-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Notes:
- `Secure` restricts the cookie to secure connections.
- `HttpOnly` prevents JavaScript from reading the cookie via `document.cookie`; it does not stop the browser from sending the cookie.
- `SameSite=Lax/Strict/None` governs certain cross-site cookie transmissions; `SameSite=None` requires `Secure` in modern browsers.
- `Domain`/`Path` limit cookie scope; avoid widening to uncontrolled subdomains.
- Session tokens need strong entropy, rotation, and fixation/hijacking defenses.

Cookie `SameSite` is **defense in depth**, not a replacement for CSRF tokens across all browsers and workflows. If the frontend and API live on two subdomains of the same site yet different origins, `SameSite` may not block requests from a compromised subdomain. Likewise, XSS on a trusted origin can submit valid CSRF tokens.

Never rely on `HttpOnly` thinking it makes CSRF impossible: `HttpOnly` blocks **JS reading cookies**, not browsers sending them on requests.

## 25. CSRF during login, logout, and file uploads

**Login CSRF:** A forged login request can trap a victim's browser in an attacker-controlled session. Spring Security docs recommend protecting login requests with CSRF.

**Logout CSRF:** Prevent GET links from triggering unexpected logouts. By default, Spring Security WebFlux performs logout via POST requiring a valid token when CSRF is enabled.

**Multipart upload:** If the CSRF token sits inside a multipart body, the system may have to parse or buffer the upload before validating the token. For JS frontends, sending the CSRF token in a header is easier to validate early and reduces premature body processing risk. Still protect the entire upload pipeline with size limits, content validation, malware scanning where needed, and resource authorization.

**GET file download:** Downloads are usually safe reads; they do not need CSRF merely because they use GET, yet they still require authentication/object permissions and short-lived presigned URLs. If a GET download also triggers a significant side effect, separate the design and reassess safety.

**Streaming/SSE/WebSocket:** Long-lived connections have distinct handshakes/upgrades and browser auth contexts; do not assume WebSocket/SSE streams share identical protections with JSON POSTs. Check security requirements for handshakes, origins, authentication, and per-message authorization, especially with cookies. HTTP CORS does not replace WebSocket origin checks or message-level authorization.

## 26. Why can a POST return 403 even when CORS allows it?

Diagnostic table:

| Symptom | Likely cause | How to check |
|---|---|---|
| OPTIONS returns 401/403 | Security blocked preflight or wrong CORS rule | Check `CorsWebFilter`/order and allowed origin/method/headers |
| Browser reports "blocked by CORS policy" | Missing or conflicting CORS response headers | Inspect OPTIONS + actual headers; do not assume backend authz failed |
| OPTIONS succeeds, POST returns 403 | Missing/invalid CSRF token or insufficient permission | Inspect CSRF logs, authentication, authority, object policy |
| Same-origin POST succeeds, cross-origin fails CORS | Origin missing from allowlist or bad credentials config | Compare scheme+host+port, `allowedOrigins`, and fetch `credentials` |
| GET succeeds, POST returns 403 | CSRF enabled without token, or POST requires WRITE permission | Test with a valid token and matching role |
| User from another tenant can read data | Missing tenant/object authorization | Inspect scoped repository/service; **never tweak CORS to fix this** |
| `curl` succeeds while browser cannot read response | CORS constrains browsers only | Inspect preflight and response headers |
| Valid token yet returns 401 | JWT validation/audience/issuer/session mismatch | Check authentication converter and authn failures |
| SPA POST with raw `XSRF-TOKEN` cookie gets 403 | Request handler masking / CSRF version mismatch | Test expected token and handler; never disable CSRF recklessly |

A common mistake is calling both CORS errors and CSRF 403s "cross-origin blocked." Separate **preflight** from **actual request** in the Network tab and integration tests.

## 27. `WebTestClient`: testing CSRF in WebFlux

Spring Security Test supports `WebTestClient`. Example:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CsrfWebFluxTests {

    @Autowired
    WebTestClient client;

    @Test
    void postWithoutCsrfIsRejected() {
        client.mutateWith(mockUser().authorities(
                new org.springframework.security.core.authority
                    .SimpleGrantedAuthority("documents:write")))
            .post().uri("/api/documents")
            .bodyValue("{\"title\":\"Sample\"}")
            .header("Content-Type", "application/json")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void postWithCsrfPassesSecurityGate() {
        client.mutateWith(mockUser().authorities(
                new org.springframework.security.core.authority
                    .SimpleGrantedAuthority("documents:write")))
            .mutateWith(csrf())
            .post().uri("/api/documents")
            .bodyValue("{\"title\":\"Sample\"}")
            .header("Content-Type", "application/json")
            .exchange()
            .expectStatus().is2xxSuccessful();
    }
}
~~~

**This is an integration test snippet**, requiring Spring Boot WebFlux/Security Test/JUnit and a real `POST /api/documents` controller returning 2xx for a valid payload after authorization. If the controller returns 201 or 204, `is2xxSuccessful()` still passes; if app validation or resource policies deny it, adjust fixtures accordingly.

Testing notes:
- Security test context must be attached to `WebTestClient`; manual binding may require `springSecurity()`.
- `mutateWith(csrf())` is a **CSRF test helper** to verify security behavior, not a substitute for browser cookie/`SameSite`/real token negotiation tests.
- Mock principals skip parts of the authentication provider; keep at least one test exercising real login/JWT conversion.
- If a filter chain uses `csrf.disable()` for a Bearer-only API, the test above will no longer verify CSRF; test according to your chain's design.
- Do not assert status alone: denied requests must create zero documents, events, or side effects.
- On GET/HEAD requests, tokens are not required by the default matcher, yet authentication/authorities remain required if the route demands them.

## 28. Testing CORS preflight properly

An integration test should send a **simulated preflight** with `Origin`, requested method, and requested headers:

~~~http
OPTIONS /api/documents/42
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Expected:
- Response allows the exact allowlisted origin.
- Allowed methods include POST; allowed headers include the requested headers.
- Preflight requires no cookies/session or CSRF token.
- Origins outside the allowlist do not receive CORS headers permitting them.
- Requesting DELETE on an endpoint allowing only GET/POST is not approved by CORS.
- Arbitrary non-allowlisted headers are rejected in preflight.
- Credentialed responses never use wildcard `Access-Control-Allow-Origin: *`.
- Actual POST still requires authn/authz/CSRF per policy even when preflight PASSES.

A `curl` command to inspect headers:

~~~bash
curl -i -X OPTIONS 'https://api.example.test/api/documents/42' \
  -H 'Origin: https://app.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-csrf-token'
~~~

**Never treat `curl` as proof that browsers enforce CORS**: `curl` does not enforce the Same-Origin Policy. It only lets you inspect server headers; verify further in browsers or `WebTestClient` and through your gateway proxy.

If CORS is configured at an ingress/CDN rather than in the app, test the real deployment path too. A passing localhost preflight does not guarantee the ingress won't strip response headers in production.

## 29. Standalone Java 17: distinguishing preflight, CSRF, and tenant authorization

This is a **pure Java 17 demo without Spring**. It does not authenticate identities, implement browser CORS protocol, or generate cryptographically secure tokens; its purpose is to prove the independent questions:
1. Are the preflight origin, method, and headers approved?
2. Is the actual request authenticated?
3. For cookie-based unsafe methods, was the CSRF token presented properly?
4. Is the actor verified as belonging to the tenant owning the resource?

Create `ReactiveRequestSecurityDemo.java`:

~~~java
import java.util.Objects;
import java.util.Set;

public class ReactiveRequestSecurityDemo {
    private static final String TRUSTED_ORIGIN =
            "https://app.example.test";

    record Request(
            String method,
            String actorTenant,
            String resourceTenant,
            boolean authenticated,
            boolean ambientCredentials,
            String expectedCsrf,
            String providedCsrf) { }

    static boolean preflightAllowed(
            String origin,
            String requestedMethod,
            Set<String> requestedHeaders) {

        Set<String> allowedMethods =
                Set.of("GET", "POST", "PUT", "DELETE");
        Set<String> allowedHeaders =
                Set.of("content-type", "x-csrf-token", "authorization");

        return TRUSTED_ORIGIN.equals(origin)
                && allowedMethods.contains(requestedMethod)
                && requestedHeaders != null
                && allowedHeaders.containsAll(requestedHeaders);
    }

    static boolean unsafe(String method) {
        return Set.of("POST", "PUT", "PATCH", "DELETE")
                .contains(method);
    }

    static String handle(Request request) {
        if (request == null || !request.authenticated()) {
            return "UNAUTHENTICATED";
        }

        if (request.ambientCredentials()
                && unsafe(request.method())
                && (request.expectedCsrf() == null
                    || request.expectedCsrf().isBlank()
                    || !Objects.equals(
                        request.expectedCsrf(),
                        request.providedCsrf()))) {
            return "CSRF_BLOCKED";
        }

        if (request.actorTenant() == null
                || request.resourceTenant() == null
                || !request.actorTenant().equals(
                    request.resourceTenant())) {
            return "AUTHZ_BLOCKED";
        }

        return "ALLOW";
    }

    public static void main(String[] args) {
        Set<String> headers =
                Set.of("content-type", "x-csrf-token");

        System.out.println("preflight-valid="
                + preflightAllowed(
                    TRUSTED_ORIGIN, "POST", headers));
        System.out.println("preflight-evil-origin="
                + preflightAllowed(
                    "https://evil.example", "POST", headers));
        System.out.println("preflight-unknown-header="
                + preflightAllowed(
                    TRUSTED_ORIGIN, "POST",
                    Set.of("x-internal-secret")));

        Request cookiePost = new Request(
                "POST", "north", "north",
                true, true, "csrf-123", null);

        System.out.println("cookie-post-without-token="
                + handle(cookiePost));
        System.out.println("cookie-post-valid="
                + handle(new Request(
                    "POST", "north", "north",
                    true, true, "csrf-123", "csrf-123")));
        System.out.println("cookie-post-cross-tenant="
                + handle(new Request(
                    "POST", "north", "south",
                    true, true, "csrf-123", "csrf-123")));
        System.out.println("cookie-get="
                + handle(new Request(
                    "GET", "north", "north",
                    true, true, "csrf-123", null)));
        System.out.println("bearer-post="
                + handle(new Request(
                    "POST", "north", "north",
                    true, false, null, null)));
        System.out.println("anonymous-post="
                + handle(new Request(
                    "POST", "north", "north",
                    false, true, "csrf-123", null)));
    }
}
~~~

Run commands:

~~~bash
javac ReactiveRequestSecurityDemo.java
java ReactiveRequestSecurityDemo
~~~

Exact stdout:

~~~text
preflight-valid=true
preflight-evil-origin=false
preflight-unknown-header=false
cookie-post-without-token=CSRF_BLOCKED
cookie-post-valid=ALLOW
cookie-post-cross-tenant=AUTHZ_BLOCKED
cookie-get=ALLOW
bearer-post=ALLOW
anonymous-post=UNAUTHENTICATED
~~~

Explanation:
- Valid preflights are approved **without saying the user is allowed to POST a document**.
- Malicious origins or headers outside the allowlist fail preflight.
- Cookie POST without a token hits `CSRF_BLOCKED`.
- Cookie POST with a token yet an actor in a different tenant hits `AUTHZ_BLOCKED`.
- Cookie GET requires no CSRF in the safe-method model **yet still requires authentication/authorization**.
- Bearer POST in the example uses no ambient credentials, so it omits CSRF tokens under the stateless-only model; this is **not** advice to skip CSRF for every JWT.
- Anonymous POST is rejected.

**Demo scope limit:** this only simulates condition checks. Real CORS is enforced via browser/server headers; real CSRF tokens require framework-managed entropy, repositories, masking/request handlers, and constant-time comparison; real authorization requires trusted authentication and data sources. Production systems also handle redirects, cookies, preflights, timeouts, method overrides, and full CSRF/XSS threat models.

## 30. Test matrix for Reactive applications

| Scenario | CORS | CSRF | Authn/Authz | Expected result |
|---|---|---|---|---|
| Browser preflight, allowed origin + POST headers | PASS | N/A | No cookie needed | OPTIONS handled successfully |
| Disallowed preflight Origin | REJECT | N/A | Irrelevant | Browser blocks reading/sending actual request |
| GET from allowed origin, authenticated | PASS | Safe method | READ scope needed | Reads if valid object |
| Cookie POST, Origin allowed, missing token | PASS | FAIL | May have session | Mutation blocked |
| Cookie POST, valid token, missing role | PASS | PASS | FAIL | Mutation blocked |
| Cookie POST, valid token, valid role, wrong tenant | PASS | PASS | Object scope FAIL | Resource not written |
| Cookie POST, valid token, valid role/object | PASS | PASS | PASS | Operation proceeds subject to business validation |
| POST with Bearer-only auth from allowed origin | PASS | Per stateless design | Token/authority required | Allowed only if resource policy permits |
| HTTP Basic / browser ambient credential without CSRF | CORS doesn't fix | CSRF risk | Authn may PASS | Never disable CSRF recklessly |
| GET endpoint accidentally mutates state | May PASS | Skipped by safe matcher | Authn may PASS | Design bug that must be fixed |
| `SameSite=None` cookie in cross-site SPA | Per allowlist | Still needs CSRF if ambient | Session/authorization | Test entire browser flow |
| JWT stored in cookie | Per allowlist | CSRF risk exists | JWT validation | Never drop CSRF just because token is a JWT |
| Expired `WebSession` | May PASS | Expected token changed/gone | Authn may fail | Do not execute; refresh/login per flow |
| Masked CSRF token vs raw header mismatch | PASS | FAIL | Authn may PASS | 403; fix compatible request handler |
| CORS PASSES yet protected route returns 403 | PASS | May PASS | FAIL | This is authorization, not a "CORS error" |
| Origin allowed, no authenticated user | PASS | Per method | FAIL | 401/challenge or redirect |
| API gateway strips CORS response headers | Browser FAIL | App may process | Depends | Fix gateway; do not enable `permitAll` |
| Shared singleton request context | Unrelated | Unrelated | Leaks actor/tenant | Catch via concurrency tests |
| Reactor context lost across tasks | Unrelated | Unrelated | Missing auth | Fail closed; never fall back to default user |

**Test at three levels:** config/logic unit tests, `WebTestClient` integration tests with Spring Security, and real browser E2E tests (cookies, `SameSite`, credentials mode, preflight, gateway). One level alone cannot prove all mechanisms.

## 31. Common mistakes and fixes

**1. Adding `permitAll()` to all APIs when CORS fails.** This opens authorization broadly. **Fix:** configure CORS preflights in the right position while keeping security rules intact.

**2. Disabling CSRF because a CORS allowlist exists.** CORS does not stop all cross-site form submissions. **Fix:** keep CSRF whenever browsers auto-send sessions, cookies, or Basic credentials.

**3. Disabling CSRF merely because an API uses JWTs.** If JWTs sit in cookies or a session fallback exists, CSRF risk remains. **Fix:** analyze how credentials are transmitted.

**4. Using `Access-Control-Allow-Origin: *` with credentials.** Violates browser/Spring rules. **Fix:** allowlist explicit origins.

**5. Echoing arbitrary `Origin` headers with `allowCredentials`.** Malicious sites can read personalized responses when browsers send cookies. **Fix:** review origin trust and DNS/subdomain hygiene.

**6. Forgetting to handle OPTIONS preflight before authentication.** Browsers never send the actual request. **Fix:** configure `CorsWebFilter` properly and verify order.

**7. Adding `OPTIONS permitAll` without CORS headers.** Browsers still block the call. **Fix:** configure real preflight CORS handling.

**8. Allowing only GET and POST while the frontend uses PUT/PATCH or custom `X-CSRF-TOKEN`.** Preflight fails. **Fix:** allow the exact methods and headers required.

**9. Treating `X-Tenant-ID` as a verified tenant.** Clients can tamper with headers. **Fix:** verify membership/roles and object tenants server-side.

**10. Storing mutable `currentUser` fields on singleton beans.** Concurrent requests corrupt context. **Fix:** use exchange attributes, Reactor Context, and method parameters.

**11. Relying on Servlet `ThreadLocal` in WebFlux.** Reactive flows hop threads and subscriptions. **Fix:** use `ReactiveSecurityContextHolder` and Reactor Context.

**12. Caching a shared authentication publisher.** One request's identity is replayed to another. **Fix:** isolate context per subscription with exact cache keys/scopes.

**13. Sending the raw `XSRF-TOKEN` cookie while the default handler expects a masked token.** Mysterious CSRF 403s. **Fix:** verify handler contracts and test SPA flows without disabling protection.

**14. Enabling `CookieServerCsrfTokenRepository.withHttpOnlyFalse()` unconditionally.** Exposes token cookies to JS unnecessarily. **Fix:** enable only when the frontend needs it and XSS controls are in place.

**15. Putting CSRF tokens in URLs or logs.** Tokens leak via `Referer` and browser history. **Fix:** use headers or form fields and never log them.

**16. Using GET to mutate data.** Safe methods skip default CSRF checks. **Fix:** use POST/PUT/PATCH/DELETE.

**17. Treating a valid CSRF token as permission to modify an object.** Tokens are neither roles nor ACLs. **Fix:** enforce method and object authorization.

**18. Testing with `curl` and concluding browser CORS PASSES.** `curl` does not enforce browser SOP. **Fix:** use `WebTestClient` and browser E2E tests.

**19. Asserting only HTTP status without checking the database.** Denied requests can still trigger worker/event side effects. **Fix:** assert state and outboxes remain unchanged.

**20. Turning on full request/header debug logs to diagnose CSRF.** Easily logs cookies, tokens, and PII. **Fix:** log structured reasons/correlations with redaction and short retention.

## 32. Operations and review checklist

- [ ] Confirm the app runs on Spring WebFlux Reactive stack without copying Servlet APIs.
- [ ] Configure CORS before authentication for preflights from one clear source of truth.
- [ ] Ensure `Origin`, `Allow-Methods`, `Allow-Headers`, credentials, and `maxAge` are tightly scoped.
- [ ] Never use wildcard Origins when `allowCredentials` is true.
- [ ] Confirm gateways/CDNs/proxies neither duplicate nor strip CORS headers.
- [ ] Never use CORS in place of authentication or authorization.
- [ ] Keep CSRF enabled on cookie/session/Basic/ambient-auth browser endpoints.
- [ ] Never disable CSRF without confirming strictly Bearer-only, stateless, non-ambient credentials.
- [ ] Ensure safe HTTP methods perform no mutations.
- [ ] Generate/store/read CSRF tokens through a valid `ServerCsrfTokenRepository`.
- [ ] Understand your Spring version's default `WebSession` repository and XOR masking handler.
- [ ] Test the real SPA cookie/header CSRF contract, including across login and logout.
- [ ] Design cookie `Secure`/`HttpOnly`/`SameSite`/`Domain`/`Path` for actual browser flows.
- [ ] Never log or put CSRF tokens, session cookies, or bearer tokens in URLs or traces.
- [ ] Keep `ServerWebExchange` attributes, Reactor Context, `WebSession`, and singleton state distinct.
- [ ] Propagate authentication/context per reactive subscription rather than arbitrary request `ThreadLocal`s.
- [ ] Never cache `currentUser`/tenant in mutable singletons or publishers shared across actors.
- [ ] Verify requested tenants against authenticated memberships rather than trusting `Origin` or headers.
- [ ] Scope object-level reads/writes by ID + tenant + owner/ACL/action.
- [ ] Ensure custom reactive policies never call `block()` on the event loop or turn timeouts into ALLOW.
- [ ] Cover GET/POST, CSRF yes/no, allowed/denied origins, roles, and tenants in `WebTestClient`.
- [ ] Run browser E2E tests for preflight, credentials mode, `SameSite`, cross-site, and same-site flows.
- [ ] Verify denied requests produce zero illegal mutations, outbox entries, files, or events.
- [ ] Pin and verify Spring Security docs and versions before rollout.

**Conclusion:** In WebFlux, **CORS** governs whether browsers let an origin read responses; **CSRF** prevents forged requests when browsers attach credentials automatically; and **request context** keeps each reactive execution's data isolated across users and requests. None of the three **replaces** authentication, roles/authorities, or object-level authorization. Handle preflights before security, keep CSRF for flows with ambient credentials, carry verified identity/tenant data in Reactor Context or `ServerWebExchange`, and test the entire chain from browser to database transaction.

## References

- [Spring Security — Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html): preflight before security, `CorsWebFilter` integration.
- [Spring Framework — WebFlux CORS](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): `CorsConfiguration`, `@CrossOrigin`, `WebFluxConfigurer`, `CorsWebFilter`, credentials, and wildcards.
- [Spring Security — WebFlux CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): `WebSessionServerCsrfTokenRepository`, `CookieServerCsrfTokenRepository`, XOR token handler, form/AJAX/JSON.
- [Spring Security — CSRF Considerations](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html): safe methods, login/logout, and multipart uploads.
- [Spring Security — WebFlux HTTP Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `SecurityWebFilterChain`, `authorizeExchange`, and matchers.
- [Spring Security — Reactive Authentication](https://docs.spring.io/spring-security/reference/reactive/authentication/index.html): reactive authentication context.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): method-level authorization and Reactor Context.
- [Spring Security — Reactive Test Support](https://docs.spring.io/spring-security/reference/reactive/test/index.html): `WebTestClient`, `csrf()`, and `mockUser()`.
- [Spring Framework — WebFlux Architecture](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html): `ServerWebExchange`, handlers, and reactive request processing.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Request_Forgery_Prevention_Cheat_Sheet.html): token patterns, `SameSite`, Origin validation, and threat models.
