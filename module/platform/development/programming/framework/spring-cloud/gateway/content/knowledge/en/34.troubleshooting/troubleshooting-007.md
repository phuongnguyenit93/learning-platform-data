# Preflight Failures or Duplicate CORS Headers

## 1. When the Browser Reports a CORS Error, Where Should the Gateway Be Checked?

**SPRING_CLOUD_GATEWAY** sits between the frontend and microservices: receiving requests, selecting routes via predicates, executing the filter chain, transforming paths/headers, authenticating, rate limiting, applying circuit breakers/retries, terminating/initiating TLS, and proxying to backends. When the frontend runs on a different origin from the Gateway, the browser enforces **Cross-Origin Resource Sharing (CORS)**. A misconfiguration can leave an API working in `curl` or Postman while JavaScript in the browser cannot read the response.

Two common operational symptoms are:

- **Preflight failure:** the browser sends `OPTIONS` prior to the actual request, yet receives 401/403/404/405 or a response missing CORS headers.
- **Duplicate CORS response headers:** the response contains two or more `Access-Control-Allow-Origin` or `Access-Control-Allow-Credentials` headers, or inconsistent values across Gateway, backend, Spring Security, and reverse proxy.

```mermaid
sequenceDiagram
    participant B as Browser
    participant G as Spring Cloud Gateway
    participant S as Spring Security
    participant U as Upstream service
    B->>G: OPTIONS /api/orders<br/>Origin + Access-Control-Request-Method
    G->>S: WebFlux Security chain
    alt Security blocks before CORS
        S-->>B: 401/403, missing CORS headers
    else CORS handled properly
        S->>G: Allow preflight through
        G-->>B: 200/204 + Access-Control-Allow-*
        B->>G: POST /api/orders + Origin
        G->>U: Proxy request
        U-->>G: 201 + CORS headers (may be duplicated)
        G-->>B: 201 + response headers
    end
```

**Key point:** CORS is a mechanism the **browser** uses to decide whether JavaScript is permitted to read a cross-origin response. CORS does not replace authentication, authorization, CSRF protection, or rate limiting. A request can still reach the backend and trigger side effects even when the browser subsequently reports a CORS error because it blocked reading the response.

### Lesson Objectives

After this lesson, you will be able to:

1. Distinguish an `OPTIONS` preflight request from an actual `GET/POST/PUT/DELETE` request.
2. Read the three core preflight headers: `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`.
3. Fix routes with `Method=GET,POST` that prevent `OPTIONS` from matching using global CORS and `add-to-simple-url-handler-mapping`.
4. Determine whether Spring Security is rejecting preflights before Gateway's CORS handler executes.
5. Configure origin/method/header/credentials allowlists soundly.
6. Find the source generating duplicate CORS response headers and designate a single responsible layer.
7. Use `DedupeResponseHeader` within its proper scope to strip identical duplicates, rather than using it to mask conflicting CORS policies.
8. Use `curl`, browser DevTools, Gateway logs, backend logs, and `WebTestClient` to isolate the failing layer.
9. Write tests covering accepted/rejected preflights, actual responses, and duplicate-header scenarios.
10. Design safe CORS with cookies/credentials, multiple Gateway replicas, ingress, and backends that also configure CORS.

> **Version scope:** Examples target **Spring Cloud Gateway Server WebFlux 4.3.x**, **Spring Cloud 2025.0.x**, **Spring Boot 3.5.x**, **Spring Framework 6.2.x**, and Java 17+. This lesson uses the configuration namespace for Gateway Server WebFlux. Gateway Server Web MVC uses the Servlet stack and a different Security integration; do not copy reactive configurations verbatim into MVC. Verify configuration metadata for your exact patch version before rollout.

## 2. How Do CORS and Preflight Work?

### 2.1. An Origin Is Defined by Scheme, Host, and Port

An origin has three parts:

```text
origin = scheme + host + port
```

Examples:

| URL | Origin |
| --- | --- |
| `https://app.example.com` | `https://app.example.com` |
| `http://app.example.com` | `http://app.example.com` |
| `https://app.example.com:8443` | `https://app.example.com:8443` |
| `https://admin.example.com` | `https://admin.example.com` |

These four values are not the same origin. Switching HTTP to HTTPS, changing subdomain, or changing port creates a different origin. An origin **has no path**; configuring `https://app.example.com/dashboard` is invalid origin syntax because it includes a path.

Some development environments use `http://localhost:5173`, while the production frontend runs on `https://app.example.com`. Declare every needed origin accurately; never assume `localhost`, production domains, and preview domains share an origin.

### 2.2. When Does the Browser Send a Preflight?

Browsers generally send a preflight when a cross-origin request is not a **CORS-safelisted request**. Examples:

- Using methods `PUT`, `PATCH`, `DELETE`.
- Using `Content-Type: application/json` (not among the safelisted MIME types).
- Sending `Authorization`, `X-Request-Id`, or other custom headers.
- Any request with headers/content-types not permitted without preflight.

Not every cross-origin request triggers a preflight. **Simple requests** can send the actual request directly, yet the actual response still needs valid CORS headers for JavaScript to read its content.

A preflight is a separate HTTP request:

```http
OPTIONS /api/orders/42 HTTP/1.1
Host: gateway.example.com
Origin: https://app.example.com
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: authorization,content-type,x-request-id
```

It carries three pieces of information to inspect:

| Header | Meaning |
| --- | --- |
| `Origin` | Origin of the page running JavaScript. |
| `Access-Control-Request-Method` | Method the browser wants to send in the **actual request** (e.g., `PATCH`). |
| `Access-Control-Request-Headers` | Request headers the actual request wants to include. |

The Gateway/CORS handler must respond allowing the appropriate origin, method, and headers. Example:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,POST,PATCH
Access-Control-Allow-Headers: Authorization,Content-Type,X-Request-Id
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
Vary: Origin
```

A successful status can be 200 or 204 depending on the handler; what must be verified is **valid CORS headers** and proper handling. The browser sends the actual request only after the preflight is accepted.

### 2.3. Preflight Is Not a Business Request

Preflight requests usually **do not carry the cookies or bearer token of the actual request**. Never require a preflight to authenticate like `PATCH /api/orders/42` and return 401 merely because no session cookie is attached. Instead:

- The CORS layer validates `Origin`, requested method, and requested headers.
- The Security policy permits preflights to be processed.
- The actual request still enforces full JWT/session authentication and authorization checks.
- The backend must never treat a passing preflight as proof that a user is logged in.

Permitting `OPTIONS` through CORS/security **does not grant access to the real API**. It only allows the browser to check upfront whether the intended request may be sent.

### 2.4. CORS Is Not a Firewall

A `curl` request is not subject to browser CORS enforcement. If a server omits `Access-Control-Allow-Origin`, `curl` can still send the request and read the response. Therefore:

- Succeeding in `curl` does not prove CORS is configured correctly.
- A browser CORS error does not prove the backend failed to process the request.
- Never use CORS in place of authentication, authorization, or CSRF protection.
- Never set `Access-Control-Allow-Origin: *` as a cure-all; origin policies must fit your data sensitivity and credential requirements.

## 3. Root Cause #1: `OPTIONS` Fails to Match the Route Predicate

### 3.1. Route Only Accepts GET/POST While Preflight Uses OPTIONS

A common route:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders_api
              uri: http://127.0.0.1:9001
              predicates:
                - Path=/api/orders/**
                - Method=GET,POST,PATCH
              filters:
                - StripPrefix=1
```

Actual request `PATCH /api/orders/42` matches the route. However, the browser preflight sends:

```http
OPTIONS /api/orders/42
Origin: https://app.example.com
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: authorization,content-type
```

`Method=GET,POST,PATCH` **does not match OPTIONS**. If Gateway only applies CORS when a request matches a route, the preflight falls through to a route miss/404 and the browser reports a CORS error. That is why an API works in Postman yet breaks when called from a frontend.

**Do not mechanically add OPTIONS to every business route's predicate.** CORS preflight is not an actual business operation; Gateway provides global CORS for the URL handler to process requests that do not match a route predicate.

### 3.2. Use Global CORS and `add-to-simple-url-handler-mapping`

In Gateway Server WebFlux 4.3, configuration metadata provides:

- `spring.cloud.gateway.server.webflux.globalcors.cors-configurations`
- `spring.cloud.gateway.server.webflux.globalcors.add-to-simple-url-handler-mapping`

Example global CORS configuration for an API:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          globalcors:
            add-to-simple-url-handler-mapping: true
            cors-configurations:
              '[/**]':
                allowedOrigins:
                  - https://app.example.com
                  - https://admin.example.com
                allowedMethods:
                  - GET
                  - POST
                  - PATCH
                  - DELETE
                allowedHeaders:
                  - Authorization
                  - Content-Type
                  - X-Request-Id
                exposedHeaders:
                  - X-Request-Id
                allowCredentials: true
                maxAge: 3600
```

`add-to-simple-url-handler-mapping: true` helps when a CORS preflight **is not handled by a route predicate**, such as when a route matches only `GET` while preflight uses `OPTIONS`. Gateway registers global CORS configurations on the simple URL handler mapping to handle CORS requests unclaimed by any route predicate.

**Distinguish two cases:**

- If a route only specifies `Path=/api/**` without method filtering, `OPTIONS` can match the route; check route/global CORS per your active setup.
- If a route specifies `Method=GET,POST` or another predicate excluding preflight, enabling simple URL handler mapping is a clean way to handle unmatched preflights.

### 3.3. Mind Configuration Prefix Differences Between Starters

Gateway 4.3 CORS docs illustrate global CORS using the compatibility prefix `spring.cloud.gateway.globalcors`; 4.3.5 configuration properties also list dedicated WebFlux properties under `spring.cloud.gateway.server.webflux.globalcors`. This lesson uses the **Gateway Server WebFlux starter** and the `server.webflux` prefix in examples.

Do not declare both prefixes simultaneously just to "see which one works". Verify:

1. Whether the project uses `spring-cloud-starter-gateway-server-webflux` or the older Gateway starter.
2. Configuration metadata/IDE completion for your exact Gateway patch version.
3. Active bound configuration (if Actuator configprops is available, expose it only on a secured management interface).
4. That an actual HTTP preflight returns the expected CORS headers.

If using the legacy starter and release-train docs specify `spring.cloud.gateway.globalcors`, use that legacy prefix consistently. **Never guess a prefix from an Internet snippet while ignoring the running dependency.**

### 3.4. Route-Level CORS Metadata

CORS can be declared directly on a route via metadata:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders_api
              uri: http://127.0.0.1:9001
              predicates:
                - Path=/api/orders/**
                - Method=GET,POST,PATCH
              metadata:
                cors:
                  allowedOrigins:
                    - https://app.example.com
                  allowedMethods:
                    - GET
                    - POST
                    - PATCH
                  allowedHeaders:
                    - Authorization
                    - Content-Type
                    - X-Request-Id
                  allowCredentials: true
                  maxAge: 3600
```

Route metadata fits when individual routes need distinct policies. However, if preflight misses the route due to `Method`, **do not assume route metadata will magically resolve a route miss**. In that case global CORS + `add-to-simple-url-handler-mapping` is usually appropriate. Test both preflight and actual requests against real routes.

## 4. Root Cause #2: Spring Security Rejects Preflight Before CORS

### 4.1. Why Does the Browser Get 401/403 Even When the Real API Uses JWT?

Spring Security WebFlux runs inside the **WebFilter chain**, before requests reach Gateway's handler mapping. Meanwhile, Gateway's global CORS applies at the handler-mapping layer. If Security requires every request to be authenticated, an `OPTIONS` preflight lacking the actual request's cookie/token can be blocked **before Gateway's CORS handler ever sees it**.

Failure flow:

```text
Browser OPTIONS
    |
    v
Spring Security WebFilter
    |
    +--> anyExchange().authenticated()
             |
             +--> no session cookie / bearer token
                       |
                       +--> 401/403
                                |
                                +--> Gateway global CORS never ran
```

This is a common culprit when:

- Gateway defines global CORS, yet the frontend still reports CORS errors.
- `OPTIONS` returns 401/403, while calling GET in Postman with a token succeeds.
- The backend shows no corresponding request because preflight was blocked prior to routing.
- Trying to add `OPTIONS` to the `Method` predicate fails to fix Security's 401.

### 4.2. Integrate CORS into the Spring Security Reactive Chain

When an application uses Spring Security, let CORS execute **before authentication/authorization** via Security's reactive CORS integration. The example below uses a single CORS configuration source for Security:

```java
package com.example.gateway;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
public class SecurityConfiguration {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        cors.setAllowedOrigins(List.of(
                "https://app.example.com",
                "https://admin.example.com"));

        // Actual request methods the browser asks permission to send.
        cors.setAllowedMethods(List.of(
                "GET", "POST", "PATCH", "DELETE"));

        cors.setAllowedHeaders(List.of(
                "Authorization",
                "Content-Type",
                "X-Request-Id"));

        cors.setExposedHeaders(List.of("X-Request-Id"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
                .cors(Customizer.withDefaults())
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(
                                HttpMethod.OPTIONS, "/api/**")
                        .permitAll()
                        .anyExchange()
                        .authenticated())
                .build();
    }
}
```

**Important import:** `UrlBasedCorsConfigurationSource` in this example is the reactive class:

```java
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;
```

Do not accidentally import the Servlet class `org.springframework.web.cors.UrlBasedCorsConfigurationSource` into Gateway Server WebFlux.

Explanation:

- `.cors(Customizer.withDefaults())` enables Spring Security's CORS integration using the declared reactive `CorsConfigurationSource`.
- `OPTIONS /api/**` is permitted past authorization rules. The CORS processor still checks origin/method/headers; `permitAll` does not allow all origins.
- Actual requests still require authentication via `.anyExchange().authenticated()`.
- `allowedMethods` lists the methods the browser intends to send; for example, preflight `OPTIONS` carries `Access-Control-Request-Method: PATCH`, so the policy must allow `PATCH`.
- `allowCredentials(true)` only enables browser credential usage per CORS; it **does not authenticate** users.

### 4.3. Designate One CORS Owner

An application can have several CORS mechanisms:

- Spring Security reactive CORS integration.
- Spring Cloud Gateway global CORS.
- A custom `CorsWebFilter` bean.
- CORS at ingress/reverse proxy.
- CORS on the backend or controller `@CrossOrigin`.

If multiple layers each emit `Access-Control-Allow-Origin`, headers get duplicated. Designate **one authoritative layer** for your public API:

| Architecture | Approach |
| --- | --- |
| Gateway without Spring Security | Use Gateway global CORS, enabling simple URL handler mapping when needed. |
| Gateway with Spring Security | Prefer Security CORS integration so preflight runs prior to authorization. |
| Ingress already owns CORS | Ensure Gateway/backend do not emit the same headers; test responses through ingress. |
| Backend manages its own CORS | Gateway should not layer another conflicting policy without clear reason; check for duplicate/conflicting headers. |
| Per-route CORS policies needed | Design policies intentionally; test how global and route-level metadata combine. |

**Do not enable** Security CORS, a standalone `CorsWebFilter`, and Gateway global CORS simultaneously with three different origin lists hoping the browser picks the right one. If layered deliberately, keep configs consistent and verify the final response over real HTTP.

### 4.4. `OPTIONS permitAll` Does Not Replace CORS Validation

Configuring:

```java
.pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()
```

lets every OPTIONS request pass authorization, yet **does not generate CORS headers itself**. Without a CORS processor or with a disallowed origin, the browser still rejects the call. Nor should you open every method/endpoint indiscriminately: permit preflights only on API paths that require them.

Never change to `.anyExchange().permitAll()` just to silence browser errors. Verify preflight and actual request responses separately.

## 5. Root Cause #3: Origin, Method, Header, or Credentials Mismatch

### 5.1. Origin Must Match Exactly

These configurations are commonly wrong:

| Configuration | Mistake |
| --- | --- |
| `allowedOrigins: https://app.example.com/` | Origins never have a trailing slash. |
| `allowedOrigins: http://app.example.com` | Frontend actually uses HTTPS. |
| `allowedOrigins: https://app.example.com:3000` | Port differs from the origin the browser sends. |
| `allowedOrigins: https://*.example.com` | `allowedOrigins` is not an arbitrary wildcard pattern. |
| `allowedOrigins: "*"` with `allowCredentials: true` | Wildcard origin is disallowed with credentialed CORS. |
| Allowing only `https://app.example.com` | Preview frontend running on `https://preview.example.com` was omitted. |

If patterns are genuinely needed, Spring Framework provides `allowedOriginPatterns`; when matched, the response reflects the specific matched origin rather than returning a literal wildcard. Prefer a **finite list of exact origins** whenever possible, especially with credentials enabled.

### 5.2. Actual Request Method Must Be Permitted

For example, the browser sends:

```http
Access-Control-Request-Method: PATCH
```

If the CORS policy only lists `GET,POST`, preflight fails even if the Gateway route includes `Method=PATCH`. There are two separate method checks:

1. **Gateway route predicate:** does the route accept the actual HTTP method?
2. **CORS allowedMethods:** is the browser allowed to send that actual method cross-origin?

Both must align. Allowing `PATCH` in CORS does not create a PATCH route; conversely, matching a PATCH route does not automatically permit cross-origin callers.

### 5.3. Requested Headers Must Be Allowlisted

A request carrying:

```http
Access-Control-Request-Headers: authorization,content-type,x-request-id
```

requires the CORS policy to permit those headers. HTTP header names are case-insensitive, yet during debugging match **exact names**:

| Header Browser Requests | Configuration to Check |
| --- | --- |
| `authorization` | `allowedHeaders: Authorization` |
| `content-type` | `allowedHeaders: Content-Type` |
| `x-request-id` | `allowedHeaders: X-Request-Id` |
| `x-tenant-id` | Allow only if required by API contract and identity source is verified. |

Do not add `allowedHeaders: "*"` just to clear an error without evaluating risk. Headers like `X-Internal-User`, `X-Admin`, or `X-Forwarded-For` may carry security meaning in backends; letting browsers send them does not make them trustworthy.

### 5.4. Credentials and Wildcard Origin

If the frontend uses cookies or credentialed fetch:

```javascript
fetch("https://gateway.example.com/api/profile", {
  method: "GET",
  credentials: "include"
});
```

the server must reply with:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
```

**Never** return:

```http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

With `allowCredentials: true`, use exact `allowedOrigins` or carefully scoped patterns. Beyond CORS, cookies also depend on `SameSite`, `Secure`, domain/path, and browser third-party cookie rules. Valid CORS alone does not guarantee browsers send cookies when cookie attributes mismatch.

### 5.5. `Access-Control-Expose-Headers` vs. `Access-Control-Allow-Headers`

Two frequently confused settings:

- `allowedHeaders`: which headers the browser **may send** in the request.
- `exposedHeaders`: which headers JavaScript **may read** from the response beyond safelisted response headers.

For instance, if the frontend needs to read `X-Request-Id` from responses, configure:

```yaml
exposedHeaders:
  - X-Request-Id
```

Adding `X-Request-Id` to `allowedHeaders` is no substitute for `exposedHeaders` when JavaScript cannot read a response header.

### 5.6. Preflight Caching Can Retain Stale Policies

`Access-Control-Max-Age` tells the browser how long to cache preflight results. After changing origin/method/header policies, browsers may continue using cached preflight responses until expiry or cache eviction.

When debugging:

- Use an incognito/private window or clear browser cache to rule out stale results.
- Inspect the response's `Access-Control-Max-Age`.
- Do not set an overly long max-age if policies change frequently.
- Do not conclude new config failed to apply based on a single cached browser session.

### 5.7. `Vary: Origin` and Reverse Proxy Caches

When a server returns `Access-Control-Allow-Origin` based on the request origin, responses vary by origin. Shared caches/CDNs must know the response depends on `Origin`. Check for:

```http
Vary: Origin
```

If a cache stores a response for `https://app.example.com` and serves it to `https://admin.example.com` without keying on origin, CORS breaks or data leaks if cache policy is also misconfigured. Never strip `Vary` while troubleshooting; inspect CDN/ingress cache keys and cache-control headers.

## 6. Root Cause #4: CORS Response Headers Added Multiple Times

### 6.1. Why Do Duplicate Headers Appear?

A common situation is **multiple layers believing they own CORS**:

```text
Browser
  |
  v
CDN / Ingress       -> adds Access-Control-Allow-Origin
  |
  v
Spring Cloud Gateway -> adds Access-Control-Allow-Origin
  |
  v
Backend service     -> @CrossOrigin adds Access-Control-Allow-Origin
  |
  v
Response returns through all layers
```

Example final response:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Credentials: true
```

Or worse, layers return two different origins:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Origin: https://admin.example.com
```

Browsers normally reject responses when `Access-Control-Allow-Origin` has multiple values or a value that is not a single valid origin (or `*` under valid conditions). **Never join two origins with a comma** instead of choosing one valid origin.

### 6.2. Identify Which Layer Adds the Header

Check step by step:

1. **Direct backend:** call the backend with `curl` including `Origin` and check if it already returns CORS headers.
2. **Gateway:** send the same request through Gateway and compare responses.
3. **Ingress/CDN:** call via the public domain and compare against the internal Gateway service.
4. **Spring Security:** check whether a `CorsConfigurationSource`/CORS integration adds headers.
5. **Controller:** search for `@CrossOrigin`, `CorsWebFilter`, `WebFluxConfigurer`, or manual code setting response headers.
6. **Gateway filters:** inspect `AddResponseHeader`, `SetResponseHeader`, `DedupeResponseHeader`, and global/default filters.
7. **Proxy middleware:** inspect ingress annotations/configs such as `add_header`, response header policies, or CDN rules.

Use `curl -i` or `curl -D - -o /dev/null` to inspect all raw response headers. A response viewed in a browser console may already be merged/formatted differently by the browser than what arrived over the wire; inspect wire responses at each layer.

### 6.3. `DedupeResponseHeader` in Gateway

Spring Cloud Gateway Server WebFlux includes the `DedupeResponseHeader` GatewayFilter Factory to strip duplicate response header values when **Gateway CORS logic and a downstream service both emit the same header**.

Example:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders_api
              uri: http://127.0.0.1:9001
              predicates:
                - Path=/api/orders/**
              filters:
                - DedupeResponseHeader=Access-Control-Allow-Credentials Access-Control-Allow-Origin
```

You can specify the strategy explicitly:

```yaml
filters:
  - name: DedupeResponseHeader
    args:
      name: Access-Control-Allow-Credentials Access-Control-Allow-Origin
      strategy: RETAIN_UNIQUE
```

Supported strategies:

| Strategy | Meaning |
| --- | --- |
| `RETAIN_FIRST` | Keep the first value (default). |
| `RETAIN_LAST` | Keep the last value. |
| `RETAIN_UNIQUE` | Keep unique values, stripping duplicates. |

**Only use dedupe as a safeguard when duplicate values are genuinely identical and policies are aligned.** If Gateway returns `https://app.example.com` while the backend returns `https://admin.example.com`, picking `RETAIN_FIRST` or `RETAIN_LAST` masks a policy conflict rather than fixing the root cause. Designate one owner and remove redundant CORS config.

### 6.4. Limitations of Route-Level Dedupe

`DedupeResponseHeader` is a **route-attached GatewayFilter**. Consequently:

- It applies to responses passing through routes that configure the filter.
- It cannot fix headers added by a CDN/ingress **after Gateway returns the response**.
- If a preflight is handled at simple URL handler mapping without hitting a Gateway route, do not expect route-level dedupe to affect that preflight response.
- It does not fix wrong origin configs, validate origins, or replace a CORS policy.

If duplicate headers appear on preflights, fix the CORS source ahead of routing (Security CORS/Gateway handler) and stop the other layer from emitting headers. If duplicates appear on actual responses traversing a route, dedupe can be applied once the cause is verified and values match.

### 6.5. Not All Repeated Response Headers Behave the Same

Headers like `Vary` can legitimately contain multiple tokens with list semantics. `Access-Control-Allow-Origin`, by contrast, must be **a single specific origin or valid wildcard**, never a list of origins. While debugging, do not apply `DedupeResponseHeader` to every header indiscriminately or concatenate values arbitrarily. Target only the duplicated CORS headers in accordance with their contract.

## 7. HTTP-Driven Diagnostic Workflow Instead of Guessing from Console Errors

### 7.1. Step 1 — Confirm What the Browser Actually Sent

Open Developer Tools → **Network**, enable Preserve log, reproduce the action, and locate the `OPTIONS` request right before the API call. Record:

- Request URL, method, and status.
- Request headers `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`.
- Response headers `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, `Access-Control-Allow-Credentials`, `Access-Control-Max-Age`, `Vary`.
- How many response header lines appear for `Access-Control-Allow-Origin` and `Access-Control-Allow-Credentials`.
- Whether the browser sent the actual request after the preflight.

Do not jump to conclusions from a generic console message like `CORS policy: No 'Access-Control-Allow-Origin' header`. Pinpoint which request lacked the header: OPTIONS, actual response, or a redirect/error response.

### 7.2. Step 2 — Reproduce the Preflight with curl

Suppose the browser wants to send PATCH with Authorization and Content-Type:

```bash
curl -i -X OPTIONS \
  "https://gateway.example.com/api/orders/42" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: PATCH" \
  -H "Access-Control-Request-Headers: authorization,content-type,x-request-id"
```

Expected response looks like:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,POST,PATCH,DELETE
Access-Control-Allow-Headers: Authorization,Content-Type,X-Request-Id
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
Vary: Origin
```

The status may vary by handler, yet if the response is 401/403/404/405 or lacks required CORS headers, keep tracing which layer generated it. With credentialed CORS policies, `Access-Control-Allow-Origin` must reflect a specific origin, never `*`.

### 7.3. Step 3 — Test a Disallowed Origin

```bash
curl -i -X OPTIONS \
  "https://gateway.example.com/api/orders/42" \
  -H "Origin: https://untrusted.example.net" \
  -H "Access-Control-Request-Method: PATCH" \
  -H "Access-Control-Request-Headers: authorization,content-type"
```

Disallowed origins must be rejected per policy, typically with 403 or a response lacking CORS allow headers. **Never** return `Access-Control-Allow-Origin: https://untrusted.example.net` merely because the client sent that Origin. Servers must never echo back arbitrary origins without allowlist validation.

### 7.4. Step 4 — Compare the Actual Request

```bash
curl -i -X PATCH \
  "https://gateway.example.com/api/orders/42" \
  -H "Origin: https://app.example.com" \
  -H "Authorization: Bearer REDACTED_FOR_EXAMPLE" \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: cors-debug-001" \
  --data '{"status":"confirmed"}'
```

The command above illustrates an HTTP actual request; use synthetic tokens in documentation and valid tokens only in authorized environments. **curl does not enforce browser CORS policies**. It can return 200/401/500 even when browsers block JavaScript from reading the response. The goal is to observe whether Gateway/backend processed the request and which response headers were sent.

### 7.5. Step 5 — Call the Backend Directly to Isolate the Layer

In a lab or authorized internal network, call the same backend endpoint with the same `Origin`:

```bash
curl -i \
  "http://127.0.0.1:9001/orders/42" \
  -H "Origin: https://app.example.com"
```

Compare:

| Direct Backend | Via Gateway | Likely Cause |
| --- | --- | --- |
| No CORS headers | One valid set | Gateway is the CORS owner. |
| One set | Two identical sets | Gateway/ingress is adding headers again. |
| One origin | Different origin or two origins | Gateway/ingress/security configs conflict. |
| 200 | 404/405 for OPTIONS | Route predicate/handler mapping needs inspection. |
| 200 | 401/403 for OPTIONS | Security WebFilter chain or auth proxy blocks upfront. |
| 200 | Browser reports CORS despite curl via Gateway showing headers | Check real browser origin, redirects, cache, CDN, and final wire response. |

Never expose the backend directly to the Internet just for debugging. Perform comparisons over a controlled network path.

### 7.6. Step 6 — Check for Redirects or Error Responses

CORS may pass on preflight while the actual request hits a redirect:

- HTTP → HTTPS redirect.
- Gateway route returns 302/307 to a login endpoint.
- Backend redirects to a different domain.
- Authentication gateway returns an error response lacking CORS headers.
- Upstream timeout/502/503 generated by Gateway.

Browsers enforce CORS across responses and redirect chains too. Inspect **every hop** and the final host, not just the initial request URL. Avoid redirecting API calls to different origins unnecessarily; design auth flows and CORS cleanly.

### 7.7. Step 7 — Verify the Running Configuration

If YAML was edited yet behavior did not change:

1. Confirm the app reads the intended `application.yml`/profile.
2. Confirm the prefix matches the starter/version (Server WebFlux vs. legacy Gateway starter).
3. Check configuration overrides from environment variables, Config Server, Helm values, or command-line args.
4. Confirm route/CORS config loaded on **every Gateway replica**.
5. Confirm ingress/CDN targets the right service and is not serving stale cached responses.
6. Restart/refresh per deployment mechanism if config does not hot-reload.
7. Re-send the preflight with exact real origin/method/headers.

Do not expose `/actuator/env` publicly for quick checks. If using Actuator `configprops`, expose it only on a secured management network and never leak secrets.

## 8. Lab: One Gateway CORS Owner with a Route Matching Only GET/POST/PATCH

### 8.1. Topology

The lab illustrates this setup:

- Gateway Server WebFlux listens on `:8080`.
- Demo backend listens on `:9001`.
- Route `/api/orders/**` matches only `GET,POST,PATCH`.
- `OPTIONS` preflight does not match the route due to the Method predicate.
- Gateway global CORS allows `https://app.example.com`.
- `add-to-simple-url-handler-mapping: true` handles preflight.
- Demo backend **does not add CORS headers itself**, keeping a single CORS owner.

```text
Browser / curl
    |
    | OPTIONS /api/orders/42
    | Origin + Access-Control-Request-Method: PATCH
    v
Gateway :8080
    |
    +--> global CORS simple URL mapping
    |      |
    |      +--> returns preflight response
    |           (does not proxy OPTIONS to backend)
    |
    +--> PATCH /api/orders/42
             |
             v
         Route Method=PATCH
             |
             v
         Backend :9001
```

This is a loopback lab; authentication and TLS are omitted. Never expose demo ports to the Internet or use real data.

### 8.2. Route and CORS Configuration

In a Spring Boot Gateway Server WebFlux 4.3 project, the relevant part of `application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webflux:
          globalcors:
            add-to-simple-url-handler-mapping: true
            cors-configurations:
              '[/**]':
                allowedOrigins:
                  - https://app.example.com
                allowedMethods:
                  - GET
                  - POST
                  - PATCH
                allowedHeaders:
                  - Authorization
                  - Content-Type
                  - X-Request-Id
                exposedHeaders:
                  - X-Request-Id
                allowCredentials: true
                maxAge: 600

          routes:
            - id: orders_api
              uri: http://127.0.0.1:9001
              predicates:
                - Path=/api/orders/**
                - Method=GET,POST,PATCH
              filters:
                - StripPrefix=1
```

In the example, the global CORS policy applies to `[/**]`; in production, narrow it to `[/api/**]` or an appropriate pattern. Specify exact required origins, methods, and headers. `maxAge: 600` equals 10 minutes so lab changes are easy to observe; it is not a mandatory value.

**If your project uses Spring Security**, do not copy this lab verbatim assuming global handler mapping always runs before Security. Apply the Security CORS integration from Section 4 and maintain a single consistent CORS owner.

### 8.3. Demo Backend Without CORS

Create a minimal HTTP server in a separate directory:

```java
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

public class OrdersBackend {

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 9001), 0);

        server.createContext("/", exchange -> {
            String response = "method="
                    + exchange.getRequestMethod()
                    + "\npath="
                    + exchange.getRequestURI().getRawPath()
                    + "\n";

            byte[] body = response.getBytes(StandardCharsets.UTF_8);

            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");

            // Backend intentionally omits Access-Control-Allow-*.
            exchange.sendResponseHeaders(200, body.length);

            try (var output = exchange.getResponseBody()) {
                output.write(body);
            }
        });

        server.start();
        System.out.println(
                "OrdersBackend listening at 127.0.0.1:9001");
    }
}
```

Start the backend with JDK:

```bash
java OrdersBackend.java
```

Start Gateway in another terminal:

```bash
mvn spring-boot:run
```

These commands are instructions for learners to run in a separate lab project, not steps to run against the lesson repository.

### 8.4. Send Preflight to Gateway

```bash
curl -i -X OPTIONS \
  "http://127.0.0.1:8080/api/orders/42" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: PATCH" \
  -H "Access-Control-Request-Headers: authorization,content-type,x-request-id"
```

Verify the output:

- Contains `Access-Control-Allow-Origin: https://app.example.com`.
- `Access-Control-Allow-Methods` allows `PATCH`.
- `Access-Control-Allow-Headers` includes Authorization, Content-Type, and X-Request-Id.
- `Access-Control-Allow-Credentials: true` if credentialed CORS is configured.
- Backend **does not need to receive OPTIONS** if Gateway handled the preflight at simple URL handler mapping.

If the response is 404, check global CORS binding/prefix and `add-to-simple-url-handler-mapping`. If 401/403, check Security/ingress first. If the response succeeds yet lacks CORS headers, check origin/path mapping and active configuration.

### 8.5. Send Actual PATCH

```bash
curl -i -X PATCH \
  "http://127.0.0.1:8080/api/orders/42" \
  -H "Origin: https://app.example.com" \
  -H "Authorization: Bearer demo-token" \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: lab-001" \
  --data '{"status":"confirmed"}'
```

The lab backend does not validate tokens or process business JSON; the token header merely illustrates a CORS request carrying Authorization. In production, actual requests still require the security chain and backend authorization. Observe that the response contains a single valid set of CORS headers.

### 8.6. Test a Disallowed Origin

```bash
curl -i -X OPTIONS \
  "http://127.0.0.1:8080/api/orders/42" \
  -H "Origin: https://untrusted.example.net" \
  -H "Access-Control-Request-Method: PATCH" \
  -H "Access-Control-Request-Headers: authorization"
```

An origin outside the allowlist must not receive a matching `Access-Control-Allow-Origin`. Never change the configuration to a wildcard just to make curl return the header.

## 9. Integration Tests with WebTestClient

### 9.1. Testing Valid Preflight

In a project with the Gateway app, CORS config, and test route/backend:

```java
package com.example.gateway;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class GatewayCorsIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void allowedPreflightReceivesCorsHeaders() {
        client.options()
                .uri("/api/orders/42")
                .headers(headers -> {
                    headers.setOrigin("https://app.example.com");
                    headers.setAccessControlRequestMethod(
                            HttpMethod.PATCH);
                    headers.setAccessControlRequestHeaders(List.of(
                            "Authorization",
                            "Content-Type",
                            "X-Request-Id"));
                })
                .exchange()
                .expectStatus().is2xxSuccessful()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        "https://app.example.com")
                .expectHeader().value(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
                        value -> assertThat(value).contains("PATCH"));
    }

    @Test
    void disallowedOriginDoesNotReceiveAllowOrigin() {
        client.options()
                .uri("/api/orders/42")
                .headers(headers -> {
                    headers.setOrigin(
                            "https://untrusted.example.net");
                    headers.setAccessControlRequestMethod(
                            HttpMethod.PATCH);
                })
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().doesNotExist(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }
}
```

The first test verifies preflight succeeds **even when the route matches only GET/POST/PATCH**. The second verifies a disallowed origin receives no allow-origin header. If the application uses Security CORS integration, use the exact real configuration source and provide an appropriate security test setup; never disable security just to make CORS tests pass.

### 9.2. Testing Against Duplicate Headers

After configuring a single CORS owner (or route response dedupe where appropriate), assert on the actual response:

```java
client.patch()
        .uri("/api/orders/42")
        .header(HttpHeaders.ORIGIN, "https://app.example.com")
        .header(HttpHeaders.CONTENT_TYPE, "application/json")
        .bodyValue("{\"status\":\"confirmed\"}")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.com");
```

`valueEquals` ensures the final header value contains the single expected origin in the response observed by WebTestClient. If the test fails, call the backend directly and then through Gateway to find which layer added the duplicate. **Never edit the test to accept two origins** just to turn CI green. This snippet assumes the lab has authentication disabled; if Spring Security is enabled, supply valid test authentication for the actual PATCH rather than relaxing security rules.

### 9.3. Concerns That Tests Should Separate

| Test | Question Answered |
| --- | --- |
| CORS configuration unit test | Does the allowlist specify the right origin/method/header/credentials? |
| Gateway preflight integration test | Is `OPTIONS` handled when the route predicate does not match the method? |
| Security integration test | Does CORS run before auth while actual requests still require authentication? |
| Backend contract test | Does the backend add CORS headers itself? |
| End-to-end through ingress/CDN | Does the final response have duplicate headers or proxy alterations? |
| Browser test | Does the browser actually accept preflight and allow JS to read the response? |

A `WebTestClient` test on a local Gateway cannot catch headers added downstream/upstream later by CDN/ingress. When a bug happens only on the public domain, test the **entire public request path**.

## 10. Quick Symptom-Based Troubleshooting Table

| Observed Symptom | Likely Cause | First Check |
| --- | --- | --- |
| OPTIONS returns 404 | `OPTIONS` fails `Method` predicate; no simple URL CORS mapping. | Check route `Method`, global CORS, and `add-to-simple-url-handler-mapping`. |
| OPTIONS returns 405 | Handler/proxy does not allow method or controller mapping rejects. | Compare Gateway vs. ingress responses; verify CORS handler ran. |
| OPTIONS returns 401 | Security enforces authentication prior to CORS. | Enable Security CORS integration; inspect `CorsConfigurationSource`. |
| OPTIONS returns 403 | Origin/method/header not allowlisted or Security policy rejects. | Inspect `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`. |
| OPTIONS 2xx yet missing ACAO | No CORS config matches path/origin; wrong prefix or profile. | Inspect active config and `Access-Control-Allow-Origin`. |
| OPTIONS 2xx with ACAO yet browser blocks | Wrong method/header/credentials or duplicate headers. | Inspect all `Access-Control-Allow-*` and response header lines. |
| Browser says `No Access-Control-Allow-Origin` on GET | Actual response/error/redirect lacks ACAO. | Inspect the actual response, not just preflight. |
| Backend processed POST/PATCH yet browser reports CORS | Actual request went through; response lacked/had wrong CORS header. | Inspect side effects/backend logs and response path. |
| ACAO appears twice with same value | Gateway and backend/ingress both emit it. | Call backend directly, then via Gateway to spot the first duplicating layer. |
| ACAO has two different origins | Two conflicting CORS policies. | Designate one CORS owner; fix source policy rather than only deduping. |
| ACAC appears multiple times | Security/Gateway/backend all add credentials header. | Compare credentials settings across layers. |
| Browser omits cookie despite passing preflight | Cookie `SameSite`/`Secure`/domain or browser third-party cookie policy. | Check cookie attributes and fetch credentials mode. |
| JavaScript cannot read `X-Request-Id` | Header not exposed. | Add `exposedHeaders: X-Request-Id`. |
| Browser still uses old policy after deploy | Preflight result cached in browser. | Check `Access-Control-Max-Age`; test in private window. |
| Fails only on public domain, internal service works | Ingress/CDN adds/strips headers, caches, or redirects. | Compare headers at Gateway service vs. public edge. |
| Error appeared after adding `@CrossOrigin` | Backend became a second CORS owner. | Remove one config source or apply intentional dedupe. |
| CORS fails on only one route | Route metadata, Path predicate, filter order, or specific method. | Inspect route definition and check route overlap. |
| OPTIONS reaches backend instead of Gateway answering | Global CORS handler inactive or preflight proxied by route. | Check `add-to-simple-url-handler-mapping` and CORS ownership. |
| Actual response missing `Vary` | Proxy/CDN rewrites headers or cache policy. | Inspect responses hop by hop and cache config. |

### 10.1. Decision Tree

```mermaid
flowchart TD
    A["Browser reports CORS"] --> B{"Is there an OPTIONS preflight?"}
    B -->|"Yes"| C{"OPTIONS status?"}
    B -->|"No"| H["Inspect actual response"]
    C -->|"404/405"| D["Route Method / simple URL mapping"]
    C -->|"401"| E["Spring Security CORS before auth"]
    C -->|"403"| F["Origin / requested method / headers"]
    C -->|"2xx"| G["Check allow-* headers and duplicates"]
    H --> I{"Does ACAO have exactly one origin?"}
    I -->|"Missing"| J["Actual error/redirect/backend CORS"]
    I -->|"Duplicate or mismatched"| K["Gateway + backend + ingress all emitting"]
    I -->|"Present"| L["Credentials / exposed headers / browser cache"]
```

## 11. Common Bad Fixes to Avoid

| Temporary Fix | Why You Should Avoid It |
| --- | --- |
| Setting `allowedOrigins: "*"` for all APIs | Opens cross-origin access to every website; invalid with credentialed CORS. |
| Setting `allowCredentials: true` because browser reports missing cookie | CORS alone does not cause cookies to be sent; SameSite/Secure and auth policy also apply. |
| Adding `OPTIONS` to every route `Method` | May not fix Security 401 and complicates route predicates. |
| Permitting all `OPTIONS /**` and all other requests | Expands authorization beyond preflight needs. |
| `.anyExchange().permitAll()` | Disables real endpoint protection just to silence a browser error. |
| Disabling Spring Security CORS without another CORS handler | Preflights may fail before authentication. |
| Adding an extra `CorsWebFilter` because headers are missing | Can produce duplicate response headers alongside Gateway/Security. |
| Using `DedupeResponseHeader` to pick between two different origins | Masks policy conflicts; fails to define which origin is truly allowed. |
| Adding CORS headers via `AddResponseHeader` on every route | Skips Origin, method, and header validation; can reflect/share wrong policy. |
| Checking only preflight, ignoring actual responses | Actual responses or error/redirect responses can still lack CORS headers. |
| Testing only with Postman/curl | Neither tool enforces browser CORS policies. |
| Assuming browser CORS error means backend never ran | The actual request may have succeeded and created side effects. |
| Stripping `Vary: Origin` to shrink headers | Can make caches serve CORS responses to the wrong origin. |
| Logging Authorization/cookies to debug | Creates credential leak risks; log only redacted request ID, route, status, and reason. |

## 12. Observability: Capturing the Right Signals Without Leaking Data

### 12.1. Useful Log Fields

During investigation, structured logs can include:

```text
routeId=orders_api
method=OPTIONS
path=/api/orders/42
originClass=allowed
corsDecision=PRE_FLIGHT_ACCEPTED
status=200
requestId=cors-debug-001
```

For rejected requests:

```text
routeId=orders_api
method=OPTIONS
path=/api/orders/42
originClass=not-allowed
corsDecision=REJECT
status=403
requestId=cors-debug-002
```

Log Origin only by allowlist/class or controlled values; avoid logging all headers. **Never log Authorization, Cookies, session IDs, or request bodies** just to diagnose CORS.

### 12.2. Metrics Split by Decision and Route

Useful metrics to track:

- Preflight count by route ID and allow/reject outcome.
- 401/403/404/405 counts on OPTIONS.
- Responses with missing or duplicate CORS headers detected in test/edge checks.
- Actual requests and 4xx/5xx by route.
- Preflight/actual request latency.
- Route/config version per Gateway replica.
- Cache/CDN hit ratio when policies vary by Origin.

Never use raw Origin, user ID, or request ID as unbounded-cardinality metric tags. Use route ID, status class, decision, and origin class from a finite set. For duplicate-header errors, metrics/alerts should indicate the **observing layer** (Gateway, ingress, or backend) rather than lumping everything into an unattributed count.

### 12.3. Comparing Across Network Hops

An operational workflow can capture redacted snapshots:

| Hop | Request/Response to Compare |
| --- | --- |
| Direct backend | Which CORS headers does the backend emit itself? |
| Gateway service | Which headers did Gateway add/remove? |
| Ingress/internal load balancer | Does it rewrite/append headers? |
| Public CDN/WAF | Does it add CORS policies, cache responses, or redirect? |
| Browser | What are the cached preflight result and final actual response? |

Compare only relevant headers; never dump full responses that may hold cookies/tokens. If an error exists only at the public edge, editing Gateway config may have no effect because the header is added after Gateway.

## 13. Regression Test Matrix

| ID | Scenario | Expected Outcome | Verification Layer |
| --- | --- | --- | --- |
| C01 | OPTIONS, allowed origin, PATCH method | 2xx preflight and single-origin ACAO. | Gateway integration. |
| C02 | OPTIONS, origin outside allowlist | Rejected, no ACAO returned for that origin. | Gateway/Security integration. |
| C03 | OPTIONS, disallowed requested method | Rejected. | CORS processor. |
| C04 | OPTIONS, requested header outside allowlist | Rejected. | CORS processor. |
| C05 | Route with `Method=GET,POST,PATCH`, OPTIONS | Simple URL CORS handler processes preflight. | Gateway integration. |
| C06 | Security enabled, OPTIONS without cookie/token | CORS processed before auth; no 401 merely for missing session. | Spring Security integration. |
| C07 | Actual PATCH without token | Authentication still rejects. | Security integration. |
| C08 | Actual PATCH with valid token | Route and backend process per permissions. | HTTP integration. |
| C09 | Credentials enabled with specific origin | ACAO is the specific origin, ACAC is true. | HTTP integration/browser. |
| C10 | Credentials enabled with wildcard allowedOrigins | Config rejected or disallowed per Spring CORS policy. | Config validation. |
| C11 | Backend and Gateway both add the same ACAO | Final response retains one valid value after owner selection/dedupe. | Gateway integration. |
| C12 | Backend and Gateway return two different origins | Test catches conflict; dedupe is not treated as a policy fix. | Gateway integration. |
| C13 | Preflight misses route and hits simple mapping | Route-level dedupe is not assumed to run; CORS owner handles header. | Gateway integration. |
| C14 | `X-Request-Id` in response | JS can read it when listed in exposedHeaders. | Browser E2E. |
| C15 | Preflight cache still active after deploy | Test private window/cleared cache to verify new policy. | Browser E2E. |
| C16 | Response via CDN/ingress | No duplicate ACAO/ACAC added after Gateway. | Edge integration. |
| C17 | Redirect/error response | CORS headers and redirect target match policy. | End-to-end. |
| C18 | Multiple Gateway replicas | Consistent CORS policy across every replica. | Deployment/staging. |

**Do not mark C01–C18 as PASS just because a configuration unit test passed.** Browser CORS enforcement, Security filter ordering, and headers added by CDN/ingress must be verified at the appropriate layers.

## 14. Pre-Release Checklist

### Preflight and Route Matching

- [ ] Inspected the real `OPTIONS` request in Browser DevTools.
- [ ] `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers` recorded accurately.
- [ ] Route `Method` predicates checked; understood why OPTIONS does not match.
- [ ] Global CORS configured under the right prefix for starter/version.
- [ ] `add-to-simple-url-handler-mapping: true` enabled when preflight misses routes and needs the simple URL handler.
- [ ] Route-level CORS metadata is not expected to handle route misses.

### Security and CORS Policy

- [ ] With Spring Security, CORS executes before authentication.
- [ ] OPTIONS permitted only within API paths requiring preflight.
- [ ] Actual requests still enforce authentication/authorization per contract.
- [ ] Exact allowed origins configured; wildcard never paired with credentials.
- [ ] Allowed methods match actual methods the browser sends.
- [ ] Allowed headers match required request headers.
- [ ] Exposed headers include only response headers the frontend needs to read.
- [ ] Cookie `SameSite`/`Secure` and credentials mode verified.
- [ ] CORS is not used in place of CSRF/authentication/authorization.

### Duplicate Response Headers

- [ ] A single primary CORS owner designated for the public API.
- [ ] Direct backend, Gateway, ingress, and public CDN compared.
- [ ] No multiple or conflicting `Access-Control-Allow-Origin` or `Access-Control-Allow-Credentials` headers.
- [ ] `DedupeResponseHeader` used only for identical duplicates within route response scope.
- [ ] Preflights tested separately since they may bypass route GatewayFilters.
- [ ] `Vary: Origin` and CDN cache keys preserved properly.

### Testing and Operations

- [ ] `curl` tests cover valid preflights and disallowed origins.
- [ ] `WebTestClient` integration tests cover OPTIONS and actual requests.
- [ ] Tests verify actual unauthorized requests are still blocked.
- [ ] Browser E2E tests run through ingress/public domain.
- [ ] Logs contain no tokens, cookies, session IDs, or bodies.
- [ ] Metrics separate CORS decisions, statuses, and route IDs.
- [ ] Active configuration is consistent across every Gateway replica.
- [ ] Rollback and cache invalidation plans exist for CORS policy changes.

## 15. Self-Check Questions

**1. What is a preflight request?**

It is an `OPTIONS` request sent by the browser before certain cross-origin requests to ask whether the server permits the origin, method, and headers of the actual request.

**2. Why can a `Method=GET,POST` route cause preflight 404s?**

Because preflight uses `OPTIONS`, which does not match the predicate. Global CORS with `add-to-simple-url-handler-mapping: true` can handle requests that do not match a route predicate.

**3. Why can Spring Security return 401 before Gateway CORS runs?**

The Security WebFilter chain executes ahead of handler mapping. Preflights normally lack the actual request's cookie/session, so CORS integration must run prior to authentication.

**4. Does `OPTIONS permitAll` automatically generate CORS headers?**

No. It only prevents the authorization layer from blocking OPTIONS; a valid CORS processor is still needed to validate origin/method/headers and emit response headers.

**5. If the actual request uses PATCH, what does CORS allowedMethods need?**

It must allow **PATCH**, because `Access-Control-Request-Method` describes the actual method the browser wants to send. OPTIONS is the preflight transport method, not a substitute for the actual method.

**6. Why can't `allowedOrigins: "*"` be used with `allowCredentials: true`?**

Credentialed CORS requires specific origins or appropriate origin patterns; wildcard origins are disallowed in `allowedOrigins` alongside credentials.

**7. How do `allowedHeaders` and `exposedHeaders` differ?**

`allowedHeaders` controls which headers the browser may send; `exposedHeaders` allows JavaScript to read headers from the response.

**8. Why can a response with two `Access-Control-Allow-Origin` headers be rejected by the browser?**

This header must represent a single valid origin (or wildcard under allowed conditions), not multiple origins. Two layers emitting the header can render the response invalid.

**9. When should `DedupeResponseHeader` be used?**

When Gateway and downstream emit **the exact same value** and duplicates must be stripped on responses passing through a route. It does not fix conflicting CORS policies or headers added by a CDN after Gateway.

**10. Why doesn't a successful curl prove browser CORS works?**

curl does not enforce browser CORS policies. Browsers validate preflight and response headers before letting JavaScript read the response.

**11. If the browser reports a CORS error after a POST, could the backend have processed the POST?**

Yes. The actual request may have reached the backend and produced side effects; only the response failing CORS prevented JavaScript from reading it.

**12. Does CORS replace authentication or CSRF protection?**

No. CORS is a browser access policy; servers must still authenticate, authorize, and apply proper CSRF protection.

## Conclusion

**Preflight failures or duplicate CORS headers** usually stem from misalignment across route predicates, Spring Security, Gateway CORS, backends, and ingress/CDNs. When a route accepts only `GET/POST/PATCH`, `OPTIONS` preflights can fail to match; Gateway Server WebFlux 4.3 supports `globalcors.add-to-simple-url-handler-mapping` to handle CORS for requests unclaimed by route predicates. When Spring Security runs upfront, integrate reactive CORS before authentication so preflights are not rejected simply for lacking a session or token.

When responses carry multiple `Access-Control-Allow-Origin` or `Access-Control-Allow-Credentials` headers, find **which layer is adding the header** and designate a single CORS owner. `DedupeResponseHeader` helps strip identical duplicates on responses traversing a route, yet is no substitute for fixing conflicting policies and does not handle preflights outside the route chain. Combine Browser DevTools, `curl`, `WebTestClient`, backend comparisons, and edge tests to verify both **preflight and actual requests**. Keep CORS policies finite, never use CORS in place of authentication/authorization, and ensure final headers are valid along the entire path from browser to microservices.

### Official References

- [Spring Cloud Gateway Server WebFlux 4.3 — CORS Configuration](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/cors-configuration.html)
- [Spring Cloud Gateway Server WebFlux 4.3 — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/4.3/configprops.html)
- [Spring Cloud Gateway Server WebFlux 4.3 — DedupeResponseHeader Filter Factory](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/gatewayfilter-factories/deduperesponseheader-factory.html)
- [Spring Framework 6.2 — WebFlux CORS](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-cors.html)
- [Spring Framework 6.2 — CorsConfiguration Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/cors/CorsConfiguration.html)
- [Spring Framework 6.2 — DefaultCorsProcessor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/cors/reactive/DefaultCorsProcessor.html)
- [Spring Security 6.5 — CORS Integration for Reactive Applications](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html)
- [Spring Security 6.5 — Reactive Web Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [MDN — CORS Guide](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS)
- [MDN — Preflight Request](https://developer.mozilla.org/en-US/docs/Glossary/Preflight_request)




