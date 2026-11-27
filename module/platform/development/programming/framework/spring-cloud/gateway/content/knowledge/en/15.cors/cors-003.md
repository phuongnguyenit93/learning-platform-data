# Global CORS configuration for Gateway Server WebFlux in Spring Cloud Gateway

An SPA running at `https://app.example.test` often calls an API at `https://api.example.test`. Even though both belong to the same system, **the browser treats them as two different origins**. If the API Gateway does not return the appropriate Cross-Origin Resource Sharing (**CORS**) headers, the browser may block JavaScript from reading the response or prevent the actual request from being sent after a preflight check.

In **SPRING_CLOUD_GATEWAY**, you can configure a **global** CORS policy for Gateway Server WebFlux instead of repeating configuration on each route. This lesson belongs to the **CORS** chapter and explains how to use `spring.cloud.gateway.globalcors.cors-configurations`, handle preflights that do not match a route via `add-to-simple-url-handler-mapping`, choose safe origins/methods/headers, coordinate with Spring Security, and verify with real HTTP requests.

The Gateway still handles route predicates, the filter chain, path/header transformations, service discovery, and routing to microservices. CORS is a **browser policy**; it does not replace authentication, authorization, rate limiting, circuit breakers, retries, TLS, or request observability.

> **Version scope:** The YAML configurations below illustrate **Spring Cloud Gateway Server WebFlux** lines that use the `spring.cloud.gateway.globalcors` namespace, common in Gateway 4.x. Other release lines or the **Server MVC** variant may use different namespaces and integration mechanisms. Consult the official documentation for your exact Spring Boot, Spring Cloud, and Gateway versions.

## 1. Understanding same-origin and CORS properly

An **origin** is defined by the triple **scheme + hostname + port**. The path does not participate in determining the origin.

| Web page calling API | API being called | Same origin? |
|---|---|---|
| `https://app.example.test` | `https://app.example.test/api/orders` | Yes |
| `https://app.example.test` | `https://api.example.test/orders` | No — different hostname |
| `http://localhost:3000` | `http://localhost:8080/api/orders` | No — different port |
| `http://app.example.test` | `https://app.example.test/api/orders` | No — different scheme |
| `https://app.example.test` | `https://app.example.test:8443/api/orders` | No — different port |

The **Same-Origin Policy** restricts JavaScript in the browser from accessing certain cross-origin responses unless the server permits it via CORS. The browser sends the `Origin` header to declare the origin of the requesting page.

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Accept: application/json
~~~

If the origin is allowed, the Gateway may respond:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin
Content-Type: application/json
~~~

With a valid origin and properly processed response, JavaScript at `https://app.example.test` can read the response subject to the remaining CORS rules. The `Vary` header and other exact values depend on framework/proxy handling; the example is illustrative.

**CORS does not block arbitrary clients.** cURL, CLIs, server-to-server applications, or malicious clients can send HTTP requests without obeying browser CORS policies. Therefore **do not use CORS as an API authorization allowlist**, and do not substitute it for OAuth2/JWT, session security, IP policies, or sensitive-data controls.

## 2. How do regular requests and preflight differ?

The browser can either send a cross-origin request directly and then check the response headers, or perform a **preflight** using HTTP `OPTIONS` before sending the actual request. Whether preflight occurs is determined by Fetch/CORS rules—method, request headers, and content type—not simply because a request is cross-origin.

For example, an SPA wants to send JSON via `POST` with an `Authorization` header:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

A valid preflight response may look like:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: Authorization,Content-Type,X-Request-Id
Access-Control-Max-Age: 1800
~~~

The status code may be `200` or another success code depending on the stack; **do not treat the number in the illustration as a mandatory requirement**. Once preflight passes, the browser sends the actual POST according to its own rules.

~~~mermaid
sequenceDiagram
    participant B as Browser at app.example.test
    participant G as Gateway api.example.test
    participant S as Downstream orders
    B->>G: OPTIONS /api/orders + Origin + Access-Control-Request-Method
    G-->>B: Preflight CORS headers (if allowed)
    Note over B: Browser checks origin, method, and request headers
    B->>G: POST /api/orders + Origin + Authorization + JSON
    G->>S: Route + GatewayFilter + downstream request
    S-->>G: Response
    G-->>B: Actual response + CORS headers
    Note over B: Browser checks CORS on actual response before JS reads it
~~~

**Keep the two round-trips separate:** preflight is an independent HTTP `OPTIONS` request, not the POST body. In many configurations, the Gateway handles preflight at the CORS handler layer without forwarding it to the backend, while the actual POST flows through the route and filter chain as normal.

Even a simple request like a cross-origin GET still needs `Access-Control-Allow-Origin` on the **actual response** for JavaScript to read the data. Making preflight succeed alone is **not enough**.

## 3. Minimal global CORS configuration with explicit boundaries

Assume only the following two frontends are permitted to call the Gateway:

- `https://app.example.test` — user application.
- `https://admin.example.test` — administration application.

An illustrative configuration for Server WebFlux:

~~~yaml
spring:
  cloud:
    gateway:
      globalcors:
        cors-configurations:
          '[/**]':
            allowedOrigins:
              - https://app.example.test
              - https://admin.example.test
            allowedMethods:
              - GET
              - POST
              - PUT
              - DELETE
              - OPTIONS
            allowedHeaders:
              - Authorization
              - Content-Type
              - X-Request-Id
            exposedHeaders:
              - X-Request-Id
            allowCredentials: true
            maxAge: 1800
~~~

**Reading the key parts:**

1. `globalcors` is a CORS configuration group applied at the Gateway handler mapping level, not a `filters` item inside an individual `RouteDefinition`.
2. `cors-configurations` maps a **path pattern** to a `CorsConfiguration` policy. The key `'[/**]'` applies to matching paths on the Gateway. The square brackets support Spring Boot's map-key binding mechanism; keep the syntax prescribed by your version's documentation.
3. `allowedOrigins` is a **list of exact origins**, containing scheme and hostname (plus port if non-default). Do not include paths like `/login` or `/api` in an origin.
4. `allowedMethods` are the methods the frontend may use under CORS; this list **does not create routes** and **does not grant business API access**.
5. `allowedHeaders` are the request headers that preflight may propose sending.
6. `exposedHeaders` are the **response headers** that JavaScript may read beyond CORS-safelisted response headers.
7. `allowCredentials: true` allows CORS responses to indicate support for credentialed requests per browser rules; use only with explicit origins and an appropriate authentication policy.
8. `maxAge` specifies the preflight result cache duration in **seconds**, subject to browser control and limits.

Values like `app.example.test` and `admin.example.test` are illustrative; replace them with domains controlled by your organization. Do not assume that listing a domain in an allowlist guarantees the domain itself is secure or that all of its users are authorized to access the API.

### Why does the `'[/**]'` key have square brackets?

In typical Gateway configurations:

~~~yaml
globalcors:
  cors-configurations:
    '[/**]':
      allowedOrigins:
        - https://app.example.test
~~~

This map key corresponds to the pattern `/**`. The `[...]` syntax helps Spring Boot preserve special characters in the key when binding to a configuration map. **Do not mistake `[/**]` for an actual HTTP path** that browsers should request.

You can use a narrower pattern when your version and requirements allow—for instance, only a specific group of API URLs; however, a "global" policy should generally be verified against error responses, unmatched routes, and preflight requests before deciding its scope.

## 4. `add-to-simple-url-handler-mapping`: preflight not matching a route

A classic scenario:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders
          uri: http://localhost:9090
          predicates:
            - Path=/api/orders/**
            - Method=POST
~~~

The browser sends `OPTIONS /api/orders/42` to ask whether POST is allowed. Because this route specifies `Method=POST`, **`OPTIONS` does not match the predicate**, so the request may not be processed through the standard route handler mapping.

In supported Gateway Server WebFlux releases, you can add:

~~~yaml
spring:
  cloud:
    gateway:
      globalcors:
        add-to-simple-url-handler-mapping: true
        cors-configurations:
          '[/**]':
            allowedOrigins:
              - https://app.example.test
            allowedMethods:
              - POST
              - OPTIONS
            allowedHeaders:
              - Content-Type
              - Authorization
~~~

`add-to-simple-url-handler-mapping: true` attaches the global CORS configuration to the **simple URL handler mapping** so matching CORS requests are handled **even when a request does not match any Gateway route predicate**. This is especially useful for `OPTIONS` preflights when routes only accept `GET`, `POST`, or other specific methods.

~~~mermaid
flowchart TD
    O["OPTIONS /api/orders/42 + Origin + preflight headers"] --> M{"Does Gateway route Method=POST match?"}
    M -->|No| H{"Is global CORS added to simple URL handler mapping?"}
    H -->|No| N["May fall through to another handler / 404 / CORS error"]
    H -->|Yes| C{"Are origin, requested method, and headers allowed?"}
    C -->|Yes| A["Return CORS preflight response"]
    C -->|No| D["Do not grant CORS / may reject"]
    A --> B["Browser decides to send actual POST"]
    B --> P["POST matches route and goes downstream"]
~~~

**This property does not turn `OPTIONS` into `POST`**, does not create routes for nonexistent APIs, and does not relax Spring Security permissions. A preflight can be answered at the global CORS layer even if the target backend URL is unavailable; the actual request must still match a route, pass authentication, and connect downstream successfully.

### Responses that bypass routes

A route-specific `GatewayFilter` may not execute if a request fails to match a route or is rejected early by the security layer. Global CORS and simple handler mapping extend coverage to the relevant preflight paths, **not as a guarantee that every 401/403/404/5xx response in the application automatically carries the same CORS headers**. Test each response type and verify filter/handler mapping order in your running version.

## 5. Understanding each CORS property and misconfiguration risks

| Property | Purpose | Common mistake |
|---|---|---|
| `allowedOrigins` | Allow exact origins | Forgetting scheme/port; including paths in origins; granting overly broad access |
| `allowedOriginPatterns` | Allow origins matching supported patterns | Overly broad patterns allowing untrusted subdomains |
| `allowedMethods` | Declare methods permitted under CORS | Confusing with routing predicates or authorization |
| `allowedHeaders` | Headers clients may request to send in preflight | Omitting `Authorization` or `Content-Type` when frontend uses JSON/JWT |
| `exposedHeaders` | Response headers JS can read | Confusing with allowed request headers |
| `allowCredentials` | Policy for sending credentials over CORS | Combining credentials with incompatible wildcard origins |
| `maxAge` | Preflight cache duration | Confusing seconds with milliseconds; expecting every browser to cache identically |
| `add-to-simple-url-handler-mapping` | Enable global CORS on simple URL mapping | Forgetting to enable when `OPTIONS` misses route predicates |

### `allowedHeaders` and `exposedHeaders` are not the same

Suppose the frontend sends:

~~~http
Authorization: Bearer token-example
Content-Type: application/json
~~~

Preflight asks whether the browser may send these two **request headers**. They belong in `allowedHeaders`. Conversely, if the backend returns:

~~~http
X-Request-Id: request-42
~~~

and JavaScript needs to read `response.headers.get("X-Request-Id")`, the name `X-Request-Id` must appear in `exposedHeaders` (unless the header is safelisted).

**Do not use `exposedHeaders` to allow sending `Authorization`.** They govern opposite directions of traffic.

### Origin policy differs from path policy

`cors-configurations.'[/**]'` applies based on the **path seen by the Gateway**, not origin wildcards. `allowedOrigins` checks the **`Origin`** such as `https://app.example.test`. To allow only one API, design an appropriate path pattern while reviewing all configured routes.

## 6. `allowCredentials`, wildcards, and trust boundaries

For APIs using cookies/sessions or browser requests with credentials, `allowCredentials: true` requires strict evaluation of the CORS configuration.

**Do not use configurations like this:**

~~~yaml
globalcors:
  cors-configurations:
    '[/**]':
      allowedOrigins:
        - '*'
      allowCredentials: true
~~~

In Spring Framework, **wildcard `*` in `allowedOrigins` is incompatible with `allowCredentials=true`**; configuration validation may fail. Moreover, from a security perspective, permitting credentials for every origin is a dangerous policy.

The clearest approach is an explicit origin allowlist:

~~~yaml
globalcors:
  cors-configurations:
    '[/**]':
      allowedOrigins:
        - https://app.example.test
      allowCredentials: true
~~~

### If you genuinely need origin patterns

Some Spring versions support `allowedOriginPatterns` to match origins by pattern, for example:

~~~yaml
globalcors:
  cors-configurations:
    '[/**]':
      allowedOriginPatterns:
        - https://*.apps.example.test
      allowCredentials: true
~~~

This can respond to CORS with the **specific matched origin** rather than returning literal `*`. However, wildcard subdomains significantly expand the trust boundary: if any matching subdomain is compromised, users' browsers can make cross-origin requests to your API under the allowed pattern.

Only use patterns when you **control all matched subdomains**, have clear provisioning/revocation policies, and have verified the exact behavior of your Spring Framework version. For APIs holding sensitive data, an explicit domain allowlist is usually easier to govern.

### CORS does not replace CSRF protection

When authentication relies on **cookies**, allowing credentialed cross-origin access and preventing **Cross-Site Request Forgery (CSRF)** are two separate concerns. Under certain conditions, a browser can still dispatch a request even if JavaScript cannot read the response due to CORS. Evaluate `SameSite`, `Secure`, CSRF tokens, authorization, and session policies accordingly.

Never disable CSRF mechanically just to "fix a CORS error." For stateless APIs using Bearer tokens, CSRF setup may differ from cookie-based APIs, but the decision must come from a threat model—not merely from a preflight failure.

## 7. CORS and Spring Security WebFlux

In a Gateway integrated with Spring Security, a common failure is **preflight receiving 401/403**. The browser sends `OPTIONS` to check cross-origin permission, yet preflight requests normally **do not carry the same authentication credentials as the actual request**. If a security filter treats it like a business GET/POST requiring a JWT before CORS is resolved, the browser stops immediately.

A logical order to achieve:

~~~mermaid
flowchart TD
    REQ["Browser preflight OPTIONS"] --> SEC["WebFlux / Spring Security filter chain"]
    SEC --> CO["CORS checked by the appropriate component"]
    CO --> OK{"Origin, method, headers accepted?"}
    OK -->|No| REJ["CORS not granted"]
    OK -->|Yes| PREF["Complete preflight per policy"]
    PREF --> REAL["Browser sends actual request"]
    REAL --> AUTH["Authenticate and authorize actual request"]
    AUTH --> RT["Route predicates + GatewayFilters"]
    RT --> DOWN["Downstream microservice"]
~~~

This diagram shows only the **logical requirement**; exact runtime ordering depends on how `SecurityWebFilterChain`, handler mappings, and CORS processing are wired.

**Approach:**

1. Confirm the Gateway binds `globalcors` properly and the policy matches your origin/method/headers.
2. Verify whether security blocks `OPTIONS` before the CORS handler runs.
3. Integrate CORS with **Spring Security reactive** according to the documentation for your version; if you allow preflight through authorization, keep full authentication/authorization enforced on **actual requests**.
4. Do not open all of `/**` with `permitAll` just so preflight succeeds.
5. Test requests with and without credentials, expired tokens, unauthorized resources, and error responses.

Avoid having **two separate CORS policies** handle the same request (for example, one in `SecurityWebFilterChain`, one in Gateway, and one in the backend) without clear precedence. Discrepancies can create conflicting CORS responses, duplicate headers, or error branches missing required headers.

## 8. How does global CORS differ from route metadata CORS and response header filters?

Spring Cloud Gateway can apply CORS globally or, on supported release lines, configure **per-route CORS** via metadata/configuration. Which choice fits best depends on whether multiple frontends require different policies.

| Approach | Scope | Suitable scenario |
|---|---|---|
| **`globalcors`** | Policy by path pattern in Gateway handler mapping | Most APIs share the same origin allowlist |
| **Route-specific CORS metadata** | Policy attached to one route per version support | A subset of APIs needs different origins/methods |
| **`SetResponseHeader` / `AddResponseHeader`** | Modifies headers after route selection | Normal response headers; does not replace CORS preflight handling |
| **`DedupeResponseHeader`** | Reduces duplicate headers per configured strategy | Gateway and downstream both emit CORS headers |
| **`CorsWebFilter` / security integration** | WebFlux layer covering conditions per configuration | Need CORS handled at web/security layer outside route scope |

**Avoid hand-rolling CORS with just `SetResponseHeader=Access-Control-Allow-Origin,*`.** CORS must evaluate origin, preflight, requested method/headers, credentials, error requests, and actual responses. Setting a static header does not perform these checks.

### When both Gateway and downstream emit CORS headers

Suppose the downstream returns `Access-Control-Allow-Origin` while the Gateway's global CORS also emits that header. When the browser receives **multiple Allow-Origin headers** or an invalid merged value, the browser may reject the response even though both layers "allowed" it.

The preferred solution is to **assign one CORS policy owner**:

- The Gateway decides CORS for public browser APIs, while downstream services omit CORS headers on traffic flowing through the Gateway; or
- The system enforces another clear policy split, verified on the final response.

In versions supporting `DedupeResponseHeader`, you can use it to reduce duplicate headers, for example:

~~~yaml
spring:
  cloud:
    gateway:
      default-filters:
        - DedupeResponseHeader=Access-Control-Allow-Credentials Access-Control-Allow-Origin
~~~

This filter **only removes duplicates**; it does not verify whether an origin is allowed. Do not use deduplication to paper over two conflicting CORS configurations. Also review actual ordering, since headers may sometimes be added outside the Gateway after leaving the filter chain.

## 9. CORS with route predicates, path rewriting, and service discovery

A realistic route:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders
          uri: lb://order-service
          predicates:
            - Path=/api/orders/**
            - Method=POST
          filters:
            - StripPrefix=1
            - SetRequestHeader=X-Edge-Service,orders
~~~

With global CORS policy:

- The browser sends preflight `OPTIONS /api/orders/42`, asking for `POST` and the `Authorization` header.
- Because the route has predicate `Method=POST`, preflight does not necessarily match the route. `add-to-simple-url-handler-mapping: true` handles this at the global CORS layer.
- The browser sends the actual POST; once accepted by security policy, the request matches the `orders` route, executes `StripPrefix` and `SetRequestHeader`, and selects an `order-service` instance via the load balancer.
- Downstream receives `POST /orders/42` given `StripPrefix=1` and no other path-modifying filter; it does not need the browser origin for business authorization if the Gateway/security contract already handles it.
- The actual response must carry valid CORS headers so the browser can read it.

**CORS does not guarantee that `lb://order-service` has healthy instances, that downstream URIs are secure, that TLS certificates are valid, or that rate limiting works.** If the backend returns 503, the CORS policy should still be checked so the frontend can read error responses where appropriate; if the API has no matching route, routing errors must be debugged independently.

### Which URL is evaluated against the CORS path pattern?

Distinguish the **incoming request path to the Gateway** from the downstream path after `StripPrefix` or `RewritePath`. `globalcors.cors-configurations` is applied at the layer handling the **incoming Gateway request**, so patterns must match the **public URL** seen by the handler mapping, not the post-filter path.

For example, if the frontend calls `/api/orders/42` and the CORS pattern only matches `/orders/**`, do not assume it matches because `StripPrefix` runs later. Test preflight against the public URL to confirm.

## 10. Designing CORS configuration per environment

A common operational mistake is carrying development settings like `allowedOrigins: ['*']` into production. Manage allowed origins as part of your deployment policy, reviewing them whenever frontend domains, ports, CDNs, or staging environments change.

Illustrative example for **development**, when the frontend runs at a specific address:

~~~yaml
spring:
  cloud:
    gateway:
      globalcors:
        add-to-simple-url-handler-mapping: true
        cors-configurations:
          '[/**]':
            allowedOrigins:
              - http://localhost:3000
            allowedMethods:
              - GET
              - POST
              - OPTIONS
            allowedHeaders:
              - Authorization
              - Content-Type
            maxAge: 600
~~~

For production, replace the origin with HTTPS domains controlled by your organization; enable `allowCredentials` only if business requirements genuinely need it and corresponding CSRF/session policies are in place. Frontends on port 5173/4200 or preview domains are **different origins**; never open a broad wildcard simply for testing convenience.

When using Spring Boot externalized configuration, profiles and environment overrides can alter CORS properties. Verify the **effective configuration on the running instance**. Do not assume one valid YAML file means every Gateway node loaded the same policy.

## 11. Practice: testing CORS with cURL and a browser

Assume the Gateway listens on `http://localhost:8080`, the test frontend has origin `http://localhost:3000`, and the test backend is on `http://localhost:9090`. Configure the development settings from Section 10 and an illustrative route:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: demo-orders
          uri: http://localhost:9090
          predicates:
            - Path=/api/orders/**
            - Method=POST
          filters:
            - StripPrefix=1
~~~

Assume the backend accepts `POST /orders/42`. This is a demo environment; do not assume the endpoint exists unless you run an actual mock/service.

### Step 1 — Allowed preflight

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/orders/42" \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type"
~~~

In PowerShell environments where `curl` is an alias, use `curl.exe` with shell-appropriate line continuation syntax. In Bash, trailing `\` continues lines as shown.

What to check:

- The response is a **successful preflight response** per your runtime policy.
- `Access-Control-Allow-Origin` permits `http://localhost:3000`.
- `Access-Control-Allow-Methods` and `Access-Control-Allow-Headers` accept POST and the requested headers.
- Other headers such as `Access-Control-Max-Age` or `Vary` match your configuration and framework behavior.
- No request needs to be forwarded to the backend solely to answer preflight.

### Step 2 — Disallowed origin

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/orders/42" \
  -H "Origin: http://localhost:9999" \
  -H "Access-Control-Request-Method: POST"
~~~

You should not see `Access-Control-Allow-Origin: http://localhost:9999`. The server may return `403` or another response depending on handler mapping/CORS processing; **evaluate the policy via headers and browser behavior**, not status code alone.

### Step 3 — Disallowed method or request header

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/orders/42" \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: DELETE"

curl -i -X OPTIONS "http://localhost:8080/api/orders/42" \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: x-unapproved-header"
~~~

Per the Section 10 configuration, `DELETE` and `X-Unapproved-Header` are not allowed. Verify the Gateway rejects the corresponding preflight. **Note:** a CORS policy denying `DELETE` does not replace authorization if a non-browser HTTP client sends `DELETE` directly.

### Step 4 — Actual request

~~~bash
curl -i -X POST "http://localhost:8080/api/orders/42" \
  -H "Origin: http://localhost:3000" \
  -H "Content-Type: application/json" \
  -d '{"quantity":2}'
~~~

If the test backend receives the POST and responds, the actual response must carry valid CORS headers. Also test backend 4xx/5xx states to check whether the frontend can read error bodies. Do not assume from a passing preflight that the actual request will return 2xx.

### Step 5 — Browser Fetch

From a page running at `http://localhost:3000`, run:

~~~javascript
const response = await fetch("http://localhost:8080/api/orders/42", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ quantity: 2 }),
});
console.log(response.status, await response.text());
~~~

Open Developer Tools and inspect the **Network** tab to compare the `OPTIONS` request (if sent by the browser), the actual POST request, the `Origin`, and the `Access-Control-*` response headers. If JavaScript reports a "CORS error," inspect both network requests: the failure may come from preflight, from missing CORS headers on the actual response, or from security/proxy handling before the route.

### Step 6 — Test credentials when required by policy

Only after configuring the origin allowlist, session/token model, and `allowCredentials` properly, test a request using the frontend's credentials mode. For example, with session cookies:

~~~javascript
const response = await fetch("https://api.example.test/api/profile", {
  credentials: "include",
});
console.log(response.status);
~~~

This snippet only shows the browser call. Running it in practice also requires a `/profile` endpoint, properly configured cookies (including `SameSite`/`Secure` where needed), HTTPS, and matching CSRF/session policies. Never use production cookies in a demo environment.

### Lab results summary

| Test | Condition | Expected sign |
|---|---|---|
| Preflight valid origin | `localhost:3000`, POST, allowed headers | CORS preflight accepted |
| Preflight unknown origin | `localhost:9999` | Origin is not granted |
| Preflight unknown method | DELETE outside `allowedMethods` | Method is not granted |
| Preflight unknown header | `X-Unapproved-Header` | Header is not granted |
| Actual POST | Valid origin, POST route exists | Route/filters/backend work; response carries valid CORS headers |
| Backend error | Route matches but backend returns 5xx | Browser can read error response if CORS policy allows |
| Security rejection | Missing/expired token | HTTP 401/403 per auth; verify CORS headers on this branch |
| Route mismatch | Public URL differs from route pattern | May return 404; distinguish from CORS policy errors |

**Limitation of cURL:** it does not enforce the Same-Origin Policy and does not block responses when CORS is misconfigured. cURL is useful for inspecting HTTP headers, while **a real browser verifies the web user experience**.

## 12. Systematic CORS troubleshooting

| Symptom | Causes to check | Resolution |
|---|---|---|
| OPTIONS returns 404 when route only accepts POST | `Method=POST` predicate does not match OPTIONS | Consider `add-to-simple-url-handler-mapping: true` and test preflight |
| OPTIONS returns 401/403 | Security runs before CORS or policy rejects the request | Check `SecurityWebFilterChain`, CORS order, origin/method/headers |
| GET returns 200 in cURL yet browser reports CORS | Actual response lacks matching CORS headers | Send `Origin` when testing and inspect browser Network tab |
| Frontend origin has a different port | Origin is scheme + host + port | Add the exact required origin; avoid production wildcards |
| Duplicate `Access-Control-Allow-Origin` headers | Both Gateway and backend/proxy emit CORS headers | Designate one owner and deduplicate cleanly |
| `allowCredentials=true` paired with `allowedOrigins=*` | Invalid/insecure configuration | Use explicit origin allowlist or controlled patterns |
| Reading response header `X-Request-Id` returns `null` | Header missing or not exposed | Inspect actual response and `exposedHeaders` |
| `Authorization` header blocked during preflight | Missing from `allowedHeaders` | Add required header after policy review |
| Browser still refuses to send cookies | Incompatible cookie `SameSite`/`Secure`, credentials policy, or HTTPS | Check session/cookie attributes, CSRF, and browser DevTools |
| Downstream 404/503 surfaces as generic CORS error | Error branch lacks CORS headers, route missed, or proxy overrides | Compare status, route ID, handler mapping, and final headers |
| Behavior differs across Gateway instances | Different profiles/configs/restarts/refreshes | Inspect effective config, logs, and rollout per instance |
| CORS works locally but fails behind CDN/ingress | Proxy caches without varying by `Origin` or overwrites headers | Check `Vary`, cache key, and responses at each hop |

### Five-question triage process

1. **Which `Origin`** actually appears in the browser request (scheme, host, port)?
2. **Did the browser send `OPTIONS` or a direct request**, and what are `Access-Control-Request-Method/Headers`?
3. **Which Gateway handler processed it**—did it match a route, or did security block it earlier?
4. **Does the final response** at the browser contain the right `Access-Control-Allow-Origin` and Allow-Methods/Headers/Credentials/Expose-Headers?
5. **Did a proxy, CDN, default filter, or downstream service** add, strip, or merge CORS headers afterward?

Use targeted logs and tracing: record the requested origin, route ID, preflight/actual status, and policy rejection reason; **never log raw access tokens or cookies** for debugging.

## 13. Safe deployment checklist

- [ ] I distinguish **origin** from domain/path and understand scheme/host/port all matter.
- [ ] I know `OPTIONS` preflight differs from the actual request and not every cross-origin request triggers preflight.
- [ ] I configured `spring.cloud.gateway.globalcors.cors-configurations` in the right Gateway Server WebFlux namespace.
- [ ] I understand the map key `'[/**]'` represents the evaluated public path pattern.
- [ ] I use explicit `allowedOrigins` in production and carefully evaluate `allowedOriginPatterns` if needed.
- [ ] I never combine `allowCredentials: true` with `allowedOrigins: ['*']`.
- [ ] I distinguish `allowedHeaders` (request) from `exposedHeaders` (response).
- [ ] I choose `maxAge` based on requirements and test policy changes in a real browser.
- [ ] I verify `add-to-simple-url-handler-mapping` when `OPTIONS` does not match a `Method` predicate.
- [ ] I integrate CORS with Spring Security WebFlux without relaxing authorization on business requests.
- [ ] I do not treat CORS as authentication, authorization, or CSRF protection.
- [ ] I establish a single CORS owner across Gateway, downstream services, ingress, and CDN.
- [ ] I test allowed/rejected origins, allowed/rejected methods/headers, preflight, and actual requests.
- [ ] I test 401/403/404/429/503 responses wherever they can occur in the architecture.
- [ ] I verify cookies, `credentials`, `SameSite`, `Secure`, and TLS if the API uses sessions.
- [ ] I still manage route predicates, rate limiting, retries/circuit breakers, TLS, and metrics/tracing as independent policies.
- [ ] I confirm all Gateway instances load the same policy in multi-node deployments.

## Official references

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — look up the **CORS Configuration** section for your exact **Gateway Server WebFlux** version, including `globalcors` and `add-to-simple-url-handler-mapping`.
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html) — how WebFlux handles CORS, `CorsConfiguration`, and policy fields.
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html) — integrating CORS with reactive security, especially preflight.
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS) — CORS requests/responses, preflight, credentials, and browser errors.
- [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) — YAML binding, profiles, and per-environment configuration.

**Takeaway:** Global CORS configuration in Gateway Server WebFlux must **explicitly specify origins, methods, request headers, credentials, and path scope**, while properly handling **`OPTIONS` preflights that miss routes** when needed. A policy is only verified when **the browser can read the actual response** and disallowed requests are rejected by rule; CORS never replaces authentication, authorization, or data protection in microservices.
