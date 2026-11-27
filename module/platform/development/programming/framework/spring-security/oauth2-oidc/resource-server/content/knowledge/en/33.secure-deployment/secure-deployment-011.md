# Reviewing Public Endpoints and Verifying No Security Chain Gaps

## 1. Objective: Know How Every Entry Point into the Application Is Protected

A Spring Security application can expose more endpoints than the controllers a development team usually looks at. Beyond business APIs, there are health checks, actuators, static resources, error handlers, OAuth callbacks, custom servlets, WebSockets, GraphQL, or routes registered via functional routers. A new endpoint can also be added without anyone updating security matchers.

Risk arises when a path slips outside `SecurityFilterChain`, an overly broad matcher accidentally opens an entire API group, or a specialized chain lacks a fallback chain covering the remainder.

The review aims to answer four questions:

1. Which URLs and HTTP methods does the application actually expose?
2. Which endpoints allow anonymous access, which require authentication, and which require specific authorities?
3. Which `SecurityFilterChain` handles each request?
4. Do tests prove both public and protected endpoints, including method and path variations?

**Default principle:** every request must pass through an intentional security chain. Public endpoints are declared explicitly in an allowlist; everything else requires authentication or is denied.

## 2. Distinguishing `securityMatcher` and `requestMatchers`

These two matchers serve different roles.

| Matcher | Placement | Question |
| --- | --- | --- |
| `securityMatcher(...)` | Selecting a `SecurityFilterChain` | Does this request belong to this chain? |
| `requestMatchers(...)` | Inside `authorizeHttpRequests` | Within the selected chain, is this request permitted, authenticated, or authority-checked? |

Example:

```java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers(HttpMethod.GET, "/api/catalog/public/**")
            .permitAll()
        .requestMatchers("/api/admin/**")
            .hasAuthority("SCOPE_admin")
        .anyRequest()
            .authenticated())
    .oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults()));
```

In this example:

- `securityMatcher("/api/**")` selects this chain for all requests under `/api/**`.
- `requestMatchers(HttpMethod.GET, "/api/catalog/public/**")` opens only GET requests under the public catalog path.
- `/api/admin/**` requires the `SCOPE_admin` authority.
- Remaining requests in the `/api/**` chain must be authenticated.

If `securityMatcher` is omitted, the default chain can apply to all requests. When multiple chains exist, chain selection depends on each chain's order and matcher.

### 2.1. A Request Enters Only the First Matching Chain

When multiple `SecurityFilterChain` beans exist, Spring Security evaluates them in `@Order` sequence. The first chain whose `securityMatcher` matches handles the request; subsequent chains no longer apply to that request.

```text
Incoming request
      │
      ▼
SecurityFilterChain @Order(1)
      │ match?
      ├── yes ──> use this chain, stop chain selection
      │
      └── no
           ▼
SecurityFilterChain @Order(2)
      │ match?
      ├── yes ──> use this chain, stop chain selection
      │
      └── no
           ▼
SecurityFilterChain @Order(3)
      │
      └── ...
```

This is why a specialized chain does not automatically protect the rest of the application. If no chain matches, the request may bypass the Spring Security filter chain altogether.

### 2.2. `anyRequest()` Covers Only Requests Inside the Selected Chain

Example:

```java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(authorize -> authorize
        .anyRequest().authenticated());
```

`anyRequest().authenticated()` here applies only to requests under `/api/**`. It does not protect `/admin/**`, `/internal/**`, `/actuator/**`, or other endpoints outside the matcher.

Always read `anyRequest()` together with `securityMatcher`, never separating the two during reviews.

## 3. Building an Endpoint Inventory Before Writing an Allowlist

You cannot prove every endpoint is protected without knowing every endpoint that exists. Build the inventory by URL **and HTTP method**, not just controller name.

A useful inventory includes:

| Field | Content |
| --- | --- |
| HTTP method | GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS, or ALL |
| Route | Route template, e.g., `/api/orders/{orderId}` |
| Handler | Controller/method or functional route |
| Category | Public, authenticated, role/scope-protected, internal, management |
| Chain | Expected security chain handling it |
| Public justification | Business justification and endpoint owner |
| Test | Test name proving the policy |
| Exposure | Internet, internal network, management port, or gateway-only |

Example:

| Method | Route | Classification | Policy |
| --- | --- | --- | --- |
| GET | `/api/catalog/public/**` | Public | `permitAll` |
| GET | `/api/orders/**` | Authenticated | `SCOPE_orders:read` |
| POST | `/api/orders/**` | Authenticated | `SCOPE_orders:write` |
| DELETE | `/api/admin/users/**` | Restricted | `SCOPE_admin` |
| GET | `/actuator/health` | Operational public/internal | Expose only summary health per deployment |
| GET | `/actuator/env` | Sensitive management | Never public |
| POST | `/oauth2/token` | Protocol endpoint | Exists only if the app genuinely acts as an Authorization Server |

Do not copy the sample table verbatim into production. API owners must confirm routes, methods, exposure, and business justifications.

### 3.1. Endpoint Sources to Audit

At a minimum, check these sources:

1. **Spring MVC controllers:** `@RequestMapping`, `@GetMapping`, `@PostMapping`, and inherited mappings.
2. **Functional routes:** `RouterFunction`, `RouterFunctions.route`, and bean-registered routes.
3. **Actuator:** endpoints exposed via `management.endpoints.web.exposure.include`, management port, and base path.
4. **Servlet/filter mappings:** custom servlets, extra dispatcher servlets, file uploads, or library-registered endpoints.
5. **Error handling:** `/error`, error controllers, exception handlers, and dispatcher types.
6. **Static resources:** favicon, assets, documentation UI, file downloads.
7. **Protocol callbacks:** OAuth/OIDC login callbacks, logout callbacks, webhooks, and event-receiver endpoints.
8. **Realtime endpoints:** WebSocket handshakes, SockJS, SSE, and GraphQL HTTP/WebSocket.
9. **Infrastructure routing:** ingress, API gateway, reverse proxies, path rewrites, and management ports.
10. **Custom contexts:** application context path, servlet path, and management context path.

A controller inventory cannot see every servlet, actuator endpoint, gateway route, or WebSocket handshake. Combine application code inspection with deployment configuration.

### 3.2. Checking Routes by HTTP Method

One path can have different policies by method:

```text
GET    /api/orders/{id}  -> SCOPE_orders:read
PATCH  /api/orders/{id}  -> SCOPE_orders:write
DELETE /api/orders/{id}  -> SCOPE_orders:delete
```

If an inventory lists only paths, reviewers may miss a data-writing method. Every supported method must have an explicit policy.

Do not assume `HEAD` or `OPTIONS` is always protected identically to `GET`. Check actual framework, CORS, and route behavior.

## 4. Maintaining an Intentional Public Endpoint Allowlist

An endpoint is public when users do not need authentication to access it. Public does not mean the endpoint lacks validation, rate limiting, business authorization, or abuse controls.

Examples of endpoints that may be public:

- Public catalogs or reference lists.
- Landing pages or instructional content.
- Summary health endpoints for load balancers if permitted by operational policy.
- Protocol-designated public callbacks with their own verification mechanism.
- Static assets containing no private data.

Examples of endpoints that normally should not be public:

- User, order, or account data.
- Admin/management endpoints.
- Actuator `env`, `configprops`, `heapdump`, `mappings`, `beans`, `loggers` without a dedicated protection layer.
- Metrics containing internal details or tenant data.
- Data export/download endpoints.
- Endpoints that mutate state, create transactions, or perform sensitive actions.

For every public endpoint, document:

1. Who consumes the endpoint?
2. What data can be returned?
3. Are rate limiting, abuse protection, or caching policies needed?
4. Does the endpoint accept input affecting data or processing cost?
5. Who owns the decision to make it public?
6. Which test detects accidental method or route changes?

Never keep an endpoint public merely because it has existed for a long time or because an existing test expects to call it.

## 5. How `permitAll` and `web.ignoring` Differ

These two mechanisms are not equivalent.

### 5.1. `permitAll`: Still Traverses Spring Security

Example:

```java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/public/**").permitAll()
        .anyRequest().authenticated());
```

Requests to `/public/**` do not need an authenticated principal to pass the authorization rule. However, the request still traverses the security filter chain. Relevant filters can still handle:

- Security headers.
- CORS integration.
- Security context lifecycle.
- CSRF protection if enabled.
- Request firewall.
- Other filters configured in the chain.

If the Resource Server filter is also in the chain, an attached Bearer token may still be parsed and authenticated before the `permitAll` authorization rule is evaluated.

### 5.2. `web.ignoring`: Bypasses the Security Filter Chain

Example:

```java
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring()
            .requestMatchers("/assets/**", "/favicon.ico");
}
```

Requests matching `web.ignoring` do not pass through the Spring Security filter chain. They skip filters provided by the chain, including Spring Security's security headers, security context, CSRF, and authorization rules.

Consider this mechanism only for resources that genuinely need zero processing from the security chain. For most HTTP endpoints, `permitAll` is clearer and easier to control.

### 5.3. Comparison Table

| Behavior | `permitAll` | `web.ignoring` |
| --- | --- | --- |
| Request traverses Spring Security chain | Yes | No |
| Security headers added by chain | Can apply | Not from bypassed chain |
| `SecurityContext`/filter chain | Yes | No |
| CORS/CSRF/security filters | Per chain config | Not from bypassed chain |
| Authorization rule | Allows anonymous | Chain rules do not run |
| Use for public APIs | Usually appropriate | Avoid |
| Use for static resources | Can be used | Narrow, intentional cases |

Modern Spring Security supports `permitAll` without forcing the application to read the session for authentication if the request does not need it. Therefore, do not choose `web.ignoring` merely to save a session lookup.

## 6. Configuring a Default Chain Following Deny-by-Default

For a simple Resource Server, a single chain covering the entire application is usually easiest to review:

```java
@Bean
SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers(
                            HttpMethod.GET,
                            "/api/catalog/public/**")
                        .permitAll()
                    .requestMatchers(
                            HttpMethod.GET,
                            "/actuator/health")
                        .permitAll()
                    .requestMatchers(
                            HttpMethod.GET,
                            "/api/orders/**")
                        .hasAuthority("SCOPE_orders:read")
                    .requestMatchers(
                            HttpMethod.POST,
                            "/api/orders/**")
                        .hasAuthority("SCOPE_orders:write")
                    .requestMatchers("/api/admin/**")
                        .hasAuthority("SCOPE_admin")
                    .anyRequest()
                        .authenticated())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
            .build();
}
```

Specific rules are placed ahead of general rules. `anyRequest().authenticated()` sits last so any unclassified route still requires authentication.

### 6.1. Public Does Not Mean Removing the Authentication Filter

Because the Resource Server filter remains active, public requests without a Bearer token can be accessed. Yet if a client sends a malformed or expired Bearer token, authentication can fail before `permitAll` is evaluated and the response will be 401.

This behavior must be decided intentionally:

- If a public endpoint accepts anonymous requests and valid tokens are optional, design intentional optional-authentication handling.
- If a public endpoint uses authentication when a valid token is present to personalize content, it is usually better to reject invalid tokens rather than silently ignoring errors.
- If a public endpoint needs no identity, you can place that route group in a chain without a Resource Server filter; then `Bearer` headers are not authenticated in that chain.

Do not write tests solely with tokenless requests and conclude all calls to a public endpoint behave identically.

### 6.2. `permitAll` Does Not Bypass Method Security

HTTP-layer authorization and method security are two separate layers.

For example, an endpoint has `permitAll`, yet the controller calls a service with:

```java
@PreAuthorize("hasAuthority('SCOPE_internal:read')")
public PublicData readData() {
    // ...
}
```

Anonymous requests can still be rejected by method security. When reviewing public endpoints, check all of:

- Request matchers in `SecurityFilterChain`.
- `@PreAuthorize`, `@PostAuthorize`, `@Secured`, and method interceptors.
- Authorization in the service/domain layer.
- Object ownership, tenant, and business checks.

Never remove method-level security just to make a public endpoint pass tests.

## 7. Multiple `SecurityFilterChain`s: Always Have a Fallback

An application may separate chains for APIs, actuator, or public areas. Each chain needs an explicit matcher and defined order.

Three-group example:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers(
                            HttpMethod.GET,
                            "/api/catalog/public/**")
                        .permitAll()
                    .requestMatchers("/api/admin/**")
                        .hasAuthority("SCOPE_admin")
                    .anyRequest()
                        .authenticated())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
            .build();
}

@Bean
@Order(2)
SecurityFilterChain publicPagesChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/public/**", "/health")
            .authorizeHttpRequests(authorize -> authorize
                    .anyRequest().permitAll())
            .build();
}

@Bean
@Order(3)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(authorize -> authorize
                    .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
            .build();
}
```

This illustrates a Resource Server application. The first chain handles `/api/**`; the second handles two public-page groups; the final chain has no `securityMatcher`, so it covers everything else.

### 7.1. Items to Check When Reviewing Multiple Chains

- Chains have explicit `@Order` and are not unexpectedly shadowed by an earlier broader chain.
- `securityMatcher` definitions across chains do not overlap unintentionally.
- Public chains do not accidentally cover `/api/admin/**` or `/actuator/**`.
- A fallback chain is not missing.
- Every chain needing OAuth2 Resource Server configures `oauth2ResourceServer`.
- CORS, CSRF, session policies, and security headers match each chain.
- There are no empty chains or overly broad matchers created just to open a single endpoint.

### 7.2. A Public Chain May Not Authenticate `Bearer` Headers

In the example above, `publicPagesChain` does not install `oauth2ResourceServer`. Requests to `/public/**` are therefore treated as anonymous by that chain; `Bearer` headers are not verified by a Resource Server filter in that chain.

If the application requires invalid tokens to be rejected even on public routes, place the endpoint in a chain with a Resource Server filter and use `permitAll` at the authorization layer. Document the contract clearly and test the exact desired behavior.

### 7.3. Avoid Placing a Catch-All Chain Matcher Too Early

A chain with `securityMatcher("/**")` and `@Order(1)` matches nearly every request, preventing subsequent chains from being selected. If that chain has different rules, endpoints can receive the wrong policy.

Use a catch-all chain only as the final fallback or when the application genuinely has only one chain.

## 8. Controlling Actuator and Management Endpoints

Actuator is a frequently overlooked source of endpoints because it does not live in business controllers.

Example exposure configuration:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
```

`exposure.include` controls which endpoints are exposed over the web; it does not decide whether an endpoint is public or protected.

A common policy:

| Actuator Endpoint | Suggested Policy |
| --- | --- |
| `/actuator/health` | Public or internal-only, returning summary info. |
| `/actuator/health/liveness` | Open only as needed by orchestrator. |
| `/actuator/health/readiness` | Open only as needed by load balancer/orchestrator. |
| `/actuator/info` | Public only if contents are approved. |
| `/actuator/metrics` | Protected/internal-only. |
| `/actuator/prometheus` | Internal network or dedicated scrape identity. |
| `/actuator/env` | Never public. |
| `/actuator/configprops` | Never public. |
| `/actuator/heapdump` | Never public. |
| `/actuator/beans`, `/actuator/mappings` | Protected; can expose internal structure. |
| `/actuator/loggers` | Protected; can alter log levels. |

### 8.1. Use `EndpointRequest` for Actuator

Spring Security provides Actuator-endpoint matchers to avoid relying solely on URL strings:

```java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;

@Bean
@Order(1)
SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
    return http
            .securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers(
                            EndpointRequest.to("health", "info"))
                        .permitAll()
                    .anyRequest()
                        .hasAuthority("SCOPE_ops"))
            .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
            .build();
}
```

This example assumes management endpoints share the same Resource Server authentication. If Actuator runs on a separate management port or uses a different network identity, configure chains and deployment boundaries to match that architecture.

### 8.2. Health Details Should Not Be Public

Health responses can expose database names, hostnames, dependency URLs, queue states, or infrastructure details. Expose only the minimum status needed publicly. Configure `management.endpoint.health.show-details` and health contributors per operational requirements.

### 8.3. A Management Port Is an Additional Boundary

A separate management port limits network exposure yet does not replace authorization. You still need firewalls/network policies allowing only appropriate scrapers/orchestrators, authentication/authorization for sensitive endpoints, verification that ingress never routes the management port to the Internet, and production configuration testing.

## 9. CORS Preflight, `OPTIONS`, and Public Endpoints

Browsers may send a CORS preflight before the actual request:

```http
OPTIONS /api/orders HTTP/1.1
Origin: https://shop.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
```

Preflights are not business requests and typically carry no Bearer token. Configure CORS to handle preflights before the appropriate authorization step:

```java
http
    .cors(Customizer.withDefaults())
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/api/catalog/public/**").permitAll()
        .anyRequest().authenticated());
```

Do not open all `OPTIONS` across every path just to make browser preflights work. CORS must restrict origins, methods, and headers per the API contract.

### 9.1. CORS Is Not Authorization

CORS is a browser policy controlling whether JavaScript on another origin can read responses. It does not prevent `curl`, mobile apps, or server-to-server clients from calling the API.

Returning `Access-Control-Allow-Origin` does not mean an endpoint is protected. Conversely, `permitAll` does not configure CORS by itself.

### 9.2. Test Both Preflight and Actual Requests

For browser-facing endpoints, test:

1. `OPTIONS` preflight from an allowed origin.
2. `OPTIONS` preflight from a disallowed origin.
3. Actual `POST`/`PUT`/`PATCH`/`DELETE` with a valid Bearer token.
4. Actual request with no token.
5. Actual request with a token missing required scopes.

Never test only `OPTIONS` and conclude that data-modifying methods are protected.

## 10. CSRF and State-Changing Public Endpoints

`permitAll` only grants authorization at the HTTP layer. It does not disable CSRF protection.

For APIs accepting only Bearer tokens in the `Authorization` header and using no cookie authentication, many stateless Resource Server applications can disable CSRF for the API per their defined threat model.

However, if browsers automatically send cookies/sessions for authentication, state-changing public or authenticated endpoints must still consider CSRF.

Example:

```java
http
    .csrf(csrf -> csrf
        .ignoringRequestMatchers("/api/**"))
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/public/**").permitAll()
        .anyRequest().authenticated());
```

This is only an example when `/api/**` genuinely uses bearer headers and does not rely on cookies for authentication. Do not copy this configuration into a browser/session application without evaluating CSRF.

A public endpoint using `POST` to subscribe to a newsletter can still suffer from abuse, spam, or CSRF depending on authentication and impact. Public does not mean rate limiting, validation, or abuse controls are unnecessary.

## 11. Path Matching: Variations Easily Missed

A matcher is only safe when its semantics match the route the servlet actually receives.

Cases to audit:

- Trailing slashes: `/api/public` vs. `/api/public/`.
- Path variables: `/api/orders/{id}`.
- Wildcards: `/api/**` vs. `/api/*`.
- HTTP methods: `GET` vs. `POST`/`DELETE`.
- Context path and servlet path.
- Reverse proxy rewrites or prefixes like `/gateway/app`.
- URL encoding, encoded slashes, and separator characters.
- Duplicate slashes, matrix parameters, and path normalization.
- Servlet mappings other than the default `DispatcherServlet`.

Do not assume `/api/public/**` has identical semantics across `AntPathMatcher`, MVC matchers, and `PathPattern`. Spring Framework/Spring Security versions and matcher configuration affect matching behavior.

### 11.1. Test Paths as the Application Actually Receives Them

If ingress rewrites `/shop/api/orders` to `/api/orders`, `MockMvc` tests only see the post-rewrite path. Add deployment/integration tests at the gateway to confirm external paths cannot bypass policy.

If the application sets `server.servlet.context-path` or a custom servlet path, configure matchers accordingly and test paths including the real context path.

### 11.2. Do Not Use Substring Matching

Avoid custom logic like:

```java
if (request.getRequestURI().contains("/public/")) {
    // Bypass authentication
}
```

Substrings can match unintended paths. Use explicit request matchers and test lookalike paths:

```text
/api/public/catalog
/api/public-admin/catalog
/api/admin/public/catalog
/api/publicity/catalog
```

Only paths designed to be public may allow anonymous access.

## 12. Error Dispatches and `/error`

Spring Boot may forward failed requests to `/error`. That is a different dispatch from the original request.

When reviewing, distinguish:

- Direct requests to `/error`.
- Error dispatches initiated by the servlet container.
- Authorization rules applied by dispatcher type.
- Error responses potentially disclosing exceptions, routes, or internal details.

If permitting error dispatches so the framework can render standard error responses, restrict by dispatcher type and verify actual behavior. Do not open all requests to `/error` merely because the application has an error page.

Example matcher by dispatcher type:

```java
import jakarta.servlet.DispatcherType;

http.authorizeHttpRequests(authorize -> authorize
        .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
        .requestMatchers("/public/**").permitAll()
        .anyRequest().authenticated());
```

This rule only illustrates restricting by dispatcher type. Test direct requests to `/error` and error dispatches separately; do not assume both share the same policy.

## 13. Automatically Enumerating Spring MVC Mappings

You can use `RequestMappingHandlerMapping` in tests to catch new controller routes not yet added to the security inventory.

Example skeleton for Spring Framework 6:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

import java.util.Set;
import java.util.stream.Collectors;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class EndpointInventoryTest {

    @Autowired
    RequestMappingHandlerMapping handlerMapping;

    private static final Set<String> APPROVED_ROUTES = Set.of(
            "GET /api/catalog/public/**",
            "GET /api/orders/{id}",
            "POST /api/orders",
            "DELETE /api/admin/users/{id}");

    @Test
    void everyControllerMappingIsClassified() {
        Set<String> discovered = handlerMapping.getHandlerMethods()
                .keySet()
                .stream()
                .flatMap(info -> {
                    Set<String> patterns = info.getPatternValues();
                    Set<RequestMethod> methods =
                            info.getMethodsCondition().getMethods();

                    if (methods.isEmpty()) {
                        return patterns.stream()
                                .map(path -> "ALL " + path);
                    }

                    return patterns.stream()
                            .flatMap(path -> methods.stream()
                                    .map(method ->
                                            method.name() + " " + path));
                })
                .collect(Collectors.toSet());

        assertThat(discovered)
                .as("Every MVC route must have an explicit security classification")
                .containsAll(APPROVED_ROUTES);

        assertThat(APPROVED_ROUTES)
                .as("New MVC routes must be reviewed and added to the inventory")
                .containsAll(discovered);
    }
}
```

This skeleton must be adapted to your application's actual routes. Mappings without a single method can be represented as `ALL`; if `params`, `headers`, `consumes`, or `produces` distinguish handlers, include those conditions in the inventory when they affect security policy.

### 13.1. Inventory Tests Do Not Replace Security Tests

The test above only detects new or unclassified MVC mappings. It does not prove matchers in the security chain are right, public endpoints are truly anonymously accessible, protected endpoints actually return 401/403 when required, Actuator/servlet/functional routes are listed, or gateways/ingresses expose no extra routes.

Combine inventory tests with `MockMvc` and deployment tests.

### 13.2. Extending the Inventory Beyond MVC

Add separate route sources for Actuator endpoint discovery, `RouterFunction`/functional endpoints, servlet registrations and filter mappings, WebSocket handshakes, management ports, and gateway/ingress route definitions.

If the application has multiple modules, aggregate all modules' inventories into one reviewable manifest.

## 14. Testing Public Endpoints with MockMvc

A public endpoint must be accessible without authentication:

```java
@Test
void publicCatalogCanBeReadWithoutAuthentication() throws Exception {
    mockMvc.perform(get("/api/catalog/public/items"))
            .andExpect(status().isOk());
}
```

Do not use `with(user(...))` or `with(jwt())` in this test; the goal is to prove anonymous access.

### 14.1. Testing Against a Route List

Parameterized test example:

```java
static Stream<Arguments> publicRequests() {
    return Stream.of(
            arguments(get("/api/catalog/public/items")),
            arguments(get("/health")),
            arguments(get("/public/documentation"))
    );
}

@ParameterizedTest
@MethodSource("publicRequests")
void approvedPublicRoutesAllowAnonymous(
        MockHttpServletRequestBuilder request) throws Exception {

    mockMvc.perform(request)
            .andExpect(status().is2xxSuccessful());
}
```

The routes in the example must exist and return 2xx per actual contract. If a health endpoint can return 503 when a dependency fails, assert security behavior specifically rather than requiring status 200.

### 14.2. Testing Non-Public Methods

If only `GET` is public, `POST` to the same path must require authentication or be rejected:

```java
@Test
void publicCatalogGetDoesNotMakePostPublic() throws Exception {
    mockMvc.perform(post("/api/catalog/public/items")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"name\":\"unexpected\"}"))
            .andExpect(status().isUnauthorized());
}
```

The result can be 401 if the path is handled by the Resource Server chain and unauthenticated; if the method is unmapped or rejected by method rules, the result may be 404/405 depending on processing order. Pick a real `POST` route in the application to test the policy rather than relying on a non-existent path.

## 15. Testing Protected Endpoints

For a Resource Server using Bearer tokens, test three states:

1. No token → 401.
2. Valid token lacking authority → 403.
3. Valid token with authority → request permitted.

Example:

```java
@Test
void ordersRequireAuthentication() throws Exception {
    mockMvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
}

@Test
void authenticatedUserWithoutReadScopeGetsForbidden() throws Exception {
    mockMvc.perform(get("/api/orders")
                    .with(jwt().authorities(
                            new SimpleGrantedAuthority(
                                    "SCOPE_profile:read"))))
            .andExpect(status().isForbidden());
}

@Test
void userWithReadScopeCanReadOrders() throws Exception {
    mockMvc.perform(get("/api/orders")
                    .with(jwt().authorities(
                            new SimpleGrantedAuthority(
                                    "SCOPE_orders:read"))))
            .andExpect(status().isOk());
}
```

`jwt()` is appropriate here to test authorization rules with a pre-built principal. It does not prove Bearer token signature/JWKS/issuer verification; those parts require dedicated signed-token integration tests.

## 16. Testing Tokens on Public Endpoints

If a public endpoint resides in a chain with a Resource Server filter, explicitly decide how caller-sent tokens are handled:

| Request | Common Behavior |
| --- | --- |
| No `Authorization` header | `permitAll` allows anonymous access. |
| Valid Bearer token | `Authentication` may be established; authorization still permits. |
| Expired / invalid-signature Bearer token | Authentication filter may return 401 before authorization. |
| `Authorization` header not using Bearer scheme | Resource Server may ignore depending on resolver; verify contract. |

Test the chosen behavior:

```java
@Test
void publicRouteRejectsInvalidBearerWhenResourceServerFilterIsPresent()
        throws Exception {

    mockMvc.perform(get("/api/catalog/public/items")
                    .header(
                            HttpHeaders.AUTHORIZATION,
                            "Bearer definitely-not-a-jwt"))
            .andExpect(status().isUnauthorized());
}
```

This test holds only if the public route is in a chain with a Bearer Resource Server filter. If the route belongs to a chain without a Resource Server filter, `Bearer` headers will not be verified and the request remains public. Document this behavior clearly in the endpoint contract.

Never silently ignore invalid tokens to treat requests as anonymous unless the application has a reviewed optional-authentication design.

## 17. Testing That Unlisted Endpoints Remain Protected

This is an essential test for detecting chain gaps.

If using a fallback chain with `anyRequest().authenticated()`, an undeclared path entering the application must still require authentication before reaching a handler:

```java
@Test
void unclassifiedPathStillHitsFallbackSecurityChain() throws Exception {
    mockMvc.perform(get("/__security_probe__/not-a-real-route"))
            .andExpect(status().isUnauthorized());
}
```

With a valid token, the request may pass authentication and return 404 because no handler exists. That proves the fallback chain applied before MVC route resolution.

This test must run in a test application context having the same fallback chain as production. If the application has multiple servlet/context paths, create probes for each boundary.

### 17.1. Do Not Use 404 as Proof an Endpoint Is Protected

A non-existent request may return 404 from MVC without proving the security policy of real routes. Conversely, when security filters run before MVC, non-existent requests may return 401 if unauthenticated.

Test real endpoints and test the fallback separately. Never use a single 404 result to conclude there are no gaps.

## 18. Testing Paths Similar to Public Paths

If `/api/public/**` is open, test lookalike paths:

```text
GET /api/public/items
GET /api/public-admin/users
GET /api/admin/public/users
GET /api/publicity/items
POST /api/public/items
DELETE /api/public/items/123
```

Only approved requests may be anonymous. Other paths must hit the protected fallback or not exist.

You can write parameterized tests with a list of negative cases:

```java
static Stream<Arguments> protectedLookalikeRequests() {
    return Stream.of(
            arguments(get("/api/public-admin/users")),
            arguments(get("/api/admin/public/users")),
            arguments(get("/api/publicity/items")),
            arguments(post("/api/public/items")),
            arguments(delete("/api/public/items/123"))
    );
}

@ParameterizedTest
@MethodSource("protectedLookalikeRequests")
void lookalikePathsDoNotInheritPublicAccess(
        MockHttpServletRequestBuilder request) throws Exception {

    mockMvc.perform(request)
            .andExpect(status().isUnauthorized());
}
```

Adjust negative cases to match real routes so every request is meaningful. If a method does not exist, verify the chain using requests to real handlers or inspect `FilterChainProxy` rather than inferring policy from 404/405.

## 19. Testing Security Headers on Public Endpoints

A `permitAll` endpoint should still receive security headers configured in the chain, such as:

- `X-Content-Type-Options`.
- Appropriate `Cache-Control`.
- `X-Frame-Options` or CSP depending on application type.
- HSTS when running HTTPS and configured appropriately.

Example:

```java
@Test
void publicEndpointStillReceivesSecurityHeaders() throws Exception {
    mockMvc.perform(get("/api/catalog/public/items"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    "X-Content-Type-Options", "nosniff"));
}
```

Exact headers depend on Spring Security configuration and response type. With `web.ignoring`, headers added by the Spring Security chain are absent; this is another reason to prefer `permitAll` for HTTP endpoints.

## 20. `FilterChainProxy` and Determining Which Chain Is Selected

In tests or debugging, you can inspect `FilterChainProxy` to see which chain is selected for a request. This is a helper for verifying matchers/ordering; avoid coupling tests tightly to the internal order of every filter unless needed.

A conceptual check:

```java
@Autowired
FilterChainProxy springSecurityFilterChain;

MockHttpServletRequest request =
        new MockHttpServletRequest("GET", "/api/orders");

List<Filter> filters =
        springSecurityFilterChain.getFilters(request);

assertThat(filters).isNotEmpty();
```

`getFilters` APIs and request construction must match your Spring Security/Servlet version. Explicitly check for the Bearer filter in the chain if required by a test, yet prefer end-to-end integration tests via `MockMvc` to verify behavior.

### 20.1. Debug Logging Is Not a Production Solution

Spring Security debug mode helps observe filter chains during development. Do not turn on broad debug logging in production just to trace matchers because requests/headers or internal details can appear in logs.

When debugging:

- Use test/dev environments.
- Use fake data.
- Limit how long it stays enabled.
- Never capture `Authorization` headers or tokens.
- Turn off debug once the issue is identified.

## 21. OAuth/OIDC Endpoints and Callbacks

A pure Resource Server usually does not expose all OAuth endpoints itself. If the same application also includes OAuth2 Client login, Authorization Server, or OIDC Provider capabilities, classify protocol endpoints separately.

| Endpoint | Meaning | How to Review |
| --- | --- | --- |
| `/oauth2/authorization/{registrationId}` | Initiates OAuth2 login | Public entry point per login flow. |
| `/login/oauth2/code/{registrationId}` | Redirect callback from Authorization Server | Must handle state/correlation and protocol validation; do not treat as a regular business API. |
| `/logout` | Ends session/login | Check HTTP method, CSRF, and logout contract. |
| `/oauth2/token` | Authorization Server Token Endpoint | Present only if app is an AS; client auth and grant policies mandatory per profile. |
| `/.well-known/openid-configuration` | Provider metadata | Public only if app acts as an OIDC Provider and contents are meant to be public. |
| `/oauth2/jwks` | Public signing keys | Can be public when app is an issuer; must contain no private keys. |

Never `permitAll` an entire `/oauth2/**` prefix just because one callback or metadata endpoint needs to be public. Each protocol endpoint has its own contract.

## 22. Static Resources and API Documentation

Static assets such as CSS, JavaScript, images, and favicons usually do not require authentication. `permitAll` can be used:

```java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers(
                "/assets/**",
                "/favicon.ico",
                "/webjars/**")
            .permitAll()
        .anyRequest().authenticated());
```

However, verify:

- Static directories contain no backups, sensitive source maps, configs, or export files.
- File uploads/downloads are not mistaken for public static assets.
- Whether API documentation UI and OpenAPI JSON are permitted to be public per policy.
- Swagger UI does not expose internal schemas or admin endpoints.
- Cache headers do not leak personal data across users.

`/static/**` can hold both public and private content if the application serves files itself. Never open the entire prefix just because a few images need to be public.

## 23. Exposure Sources Outside Spring Security

An application with an accurate security chain can still be exposed unexpectedly by deployment:

- Ingress routes pointing straight to an internal service/port.
- Gateways skipping authentication for the wrong path prefix.
- Reverse proxies rewriting paths before matchers evaluate.
- Management ports exposed to the Internet.
- Kubernetes `Service`/`NodePort`/`LoadBalancer` exposing extra ports.
- Public static hosting buckets.
- WebSocket endpoints with separate handshake policies.
- Servlets/filters mounted on a different context path.

Reviews must combine:

1. Routes in code.
2. `SecurityFilterChain` and matchers.
3. Actuator/application properties.
4. Gateway/ingress/proxy configuration.
5. Network exposure and port mappings.
6. Integration tests through the actual URLs/ports clients hit.

Never treat a route's absence from `RequestMappingHandlerMapping` as proof it is unreachable from the Internet.

## 24. Public Endpoint Review Process

A practical process can follow these steps:

1. **Collect:** export inventory from MVC mappings, Actuator, functional routes, servlet registrations, and the gateway.
2. **Normalize:** record each route with HTTP method, context path, and exposure.
3. **Classify:** public, authenticated, authority-protected, internal-only, or protocol-specific.
4. **Approve:** every public route has an owner and justification.
5. **Map:** identify the chain and matcher handling each route.
6. **Check fallback:** confirm unclassified requests remain protected.
7. **Check methods/paths:** negative cases for other methods, lookalike paths, trailing slashes, and context paths.
8. **Check additional layers:** method security, CSRF, CORS, object authorization, rate limiting.
9. **Check deployment:** gateway, ingress, management ports, and external routing.
10. **Automate:** run inventory tests, anonymous tests, protected tests, and negative matcher tests in CI.

When a new endpoint is added, pull requests should update both the inventory and security tests at the same time.

## 25. Security Test Matrix

| Case | Request | Credential | Expectation |
| --- | --- | --- | --- |
| PUB-01 | `GET` approved public endpoint | None | 2xx per contract |
| PUB-02 | `GET` public endpoint in chain with Bearer filter | Valid token | Allowed |
| PUB-03 | `GET` public endpoint in chain with Bearer filter | Invalid token | 401 per policy |
| PROT-01 | `GET` protected endpoint | None | 401 |
| PROT-02 | `GET` protected endpoint | Valid token, missing scope | 403 |
| PROT-03 | `GET` protected endpoint | Token with right scope | 2xx |
| PROT-04 | `POST` write endpoint | Read-only token | 403 |
| PROT-05 | `DELETE` restricted endpoint | Token missing admin | 403 |
| MATCH-01 | Path resembling public prefix | None | Not public |
| MATCH-02 | Different method on public path | None | Not public outside contract |
| CHAIN-01 | Request matching specialized chain | Per chain policy | Handled by right chain |
| CHAIN-02 | Request outside specialized chains | None | Protected by fallback |
| ACT-01 | `GET` summary health | None | Per health policy |
| ACT-02 | `GET` `actuator/env` | None | 401/403 or not exposed |
| CORS-01 | `OPTIONS` preflight valid origin | None | Appropriate CORS response |
| CORS-02 | `OPTIONS` preflight unknown origin | None | No CORS permission granted |
| CSRF-01 | Public state-changing endpoint with cookie context | No CSRF token | Rejected if CSRF policy requires |
| ERR-01 | Error dispatch | Per dispatcher policy | Safe error response |
| HDR-01 | `GET` public endpoint | None | Security headers per config |
| GAP-01 | Request to unclassified path | None | Fallback requires authentication |

Exact statuses must follow the application's contract. For example, a non-existent endpoint may return 404/405 instead of 401 depending on processing order; use real endpoints to prove authorization.

## 26. Common Mistakes

1. **Reviewing only controllers:** misses Actuator, servlets, functional routes, WebSockets, and gateways.
2. **Listing only paths without methods:** a public `GET` can cause teams to accidentally open `POST`/`DELETE`.
3. **Confusing `securityMatcher` with `requestMatchers`:** one selects the chain, the other selects authorization rules inside the chain.
4. **Assuming `anyRequest().authenticated()` protects the entire app:** it applies only inside the selected chain.
5. **Missing a fallback chain:** requests outside specialized matchers may bypass Spring Security.
6. **Placing a catch-all chain too early:** a broad chain can capture requests meant for specialized chains.
7. **Using `web.ignoring` for public APIs:** skips security filters and headers.
8. **Permitting an entire broad prefix:** one public route can accidentally expose admin/private endpoints sharing the prefix.
9. **Permitting all `OPTIONS`:** bypasses CORS policy and can make matchers too broad.
10. **Treating CORS as authorization:** CORS does not protect APIs from non-browser clients.
11. **Assuming `permitAll` bypasses method security:** `@PreAuthorize` and domain policies can still deny access.
12. **Assuming health endpoints are harmless:** health details can expose infrastructure.
13. **Disabling CSRF for every endpoint:** unsafe if browsers use cookie/session authentication.
14. **Testing only anonymous requests:** misses behavior when callers send invalid tokens to public routes.
15. **Asserting only 4xx status:** fails to distinguish authentication failure from authorization denial.
16. **Enabling Spring Security debug in production:** can leak request/security details.
17. **Not testing reverse proxy rewrites:** external paths may differ from paths seen by matchers.
18. **Treating an inventory test as a complete security test:** inventories only detect routes, not policy enforcement.

## 27. Review Completion Checklist

- [ ] Complete inventory of routes and HTTP methods exists.
- [ ] MVC, functional routes, Actuator, servlets, error, protocol, and realtime endpoints reviewed.
- [ ] Ingress, gateway, reverse proxies, management ports, and context paths reviewed.
- [ ] Every endpoint has a classification and owner.
- [ ] Every public endpoint has an approved justification and data exposure review.
- [ ] Public allowlist restricts specific methods and paths.
- [ ] Specific rules precede general rules.
- [ ] Chain selection is clear for every request.
- [ ] Every specialized chain has explicit matcher/order.
- [ ] A fallback chain protects everything else.
- [ ] No misordered catch-all matcher exists.
- [ ] `permitAll` is used for most public HTTP endpoints.
- [ ] `web.ignoring` is used only in narrow, justified cases.
- [ ] Behavior for invalid Bearer tokens on public routes is verified.
- [ ] Method security and object/tenant authorization are verified.
- [ ] CORS preflights are configured per origin/method/header allowlist.
- [ ] CSRF is evaluated based on how credentials are actually transmitted.
- [ ] Actuator endpoints are exposed and protected separately.
- [ ] Tests cover anonymous, missing token, insufficient scope, and authorized token cases.
- [ ] Negative tests cover lookalike paths and other HTTP methods.
- [ ] Tests prove the fallback chain protects unclassified paths.
- [ ] Inventory tests detect unreviewed new routes.
- [ ] Security headers and error handling are verified on public routes.

## 28. Self-Check Questions

**1. What is `securityMatcher` used for?** Selecting which `SecurityFilterChain` handles a request.

**2. What is `requestMatchers` used for?** Selecting authorization rules inside the chosen chain.

**3. Does `anyRequest().authenticated()` protect paths outside `securityMatcher`?** No.

**4. What happens when no `SecurityFilterChain` matches?** The request may not traverse the Spring Security filter chain.

**5. When multiple chains exist, which chain is chosen?** The first chain in order whose matcher matches the request.

**6. Why is a fallback chain needed?** To protect requests that do not belong to any specialized chain.

**7. Does `permitAll` bypass security filters?** No; it only permits authorization at that rule.

**8. Does `web.ignoring` differ from `permitAll`?** Yes; ignored requests bypass the Spring Security filter chain.

**9. Can a public endpoint return 401 when an invalid token is sent?** Yes, if a Resource Server Bearer filter is in the chain and authentication fails before authorization.

**10. Does `permitAll` bypass `@PreAuthorize`?** No.

**11. Does CORS replace authentication/authorization?** No.

**12. Should all `OPTIONS` requests be permitted?** No; configure CORS preflights per an explicit policy.

**13. Does Actuator's `exposure.include` make endpoints public?** No; it only exposes endpoints over the web, and security must still be configured.

**14. Why must inventories track HTTP methods?** The same path might have a public `GET` while `POST`/`DELETE` require permissions.

**15. Can `RequestMappingHandlerMapping` alone inventory every endpoint?** No; there are also Actuator, servlet, functional, WebSocket, and gateway routes.

**16. Why can testing a non-existent path be insufficient?** A 404/405 does not prove the policy of real endpoints.

**17. When should `web.ignoring` be used?** Only for resources genuinely needing no security chain processing, with an impact assessment.

**18. Why test external paths through the gateway?** Rewrites and ingress rules can make real paths differ from application matchers.

**19. Should security debug be enabled in production?** No; enable it only briefly in controlled environments with fake data.

**20. What is the best evidence that no security gaps remain?** A complete inventory, an explicit fallback chain, classified policies, and integration tests proving both public and protected behavior.

## 29. References

- **Spring Security Reference — Java Configuration / Multiple `HttpSecurity` instances:** configuring multiple `SecurityFilterChain`s, ordering, and matchers. https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- **Spring Security Reference — Authorize HTTP Requests:** `requestMatchers`, `permitAll`, `authenticated`, and authorization rules. https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- **Spring Security Reference — Web Security:** `WebSecurityCustomizer` and ignoring requests. https://docs.spring.io/spring-security/reference/servlet/architecture.html
- **Spring Boot Reference — Actuator Endpoints:** exposing and configuring management endpoints. https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- **Spring Boot Reference — Actuator Security:** securing management endpoints. https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- **Spring Security Reference — CORS:** CORS processing in the security chain. https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- **Spring Security Reference — CSRF:** CSRF protection and configuration per application architecture. https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- **Spring Security Reference — Testing MockMvc:** testing request authorization and security behavior. https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- **OWASP Authorization Cheat Sheet:** deny by default and checking permissions on every request. https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- **OWASP Attack Surface Analysis Cheat Sheet:** inventorying and reviewing attack surfaces. https://cheatsheetseries.owasp.org/cheatsheets/Attack_Surface_Analysis_Cheat_Sheet.html

## 30. Conclusion

Reviewing public endpoints means inventorying the entire access surface and proving every request passes through an intentional policy. Build an inventory by path and HTTP method, classify routes as public/authenticated/restricted, identify handling chains, and maintain a fallback chain protecting all remaining requests.

In Spring Security, `securityMatcher` selects the filter chain; `requestMatchers` selects authorization rules inside the chain. `permitAll` grants anonymous access while still traversing security filters; `web.ignoring` bypasses the entire chain and fits only narrow cases. Multiple chains must have explicit ordering so catch-all chains never shadow specialized ones and requests never fall outside all chains.

Finally, combine inventory tests with `MockMvc` tests for public routes, protected routes, other methods, invalid tokens, missing scopes, lookalike paths, Actuator, and fallback behavior. Also inspect gateways, ingress, context paths, CORS, CSRF, and method security. Only when new routes are detected, policies classified, and tests verify behavior at the actual boundaries can a team be confident no endpoints were accidentally left uncovered.
