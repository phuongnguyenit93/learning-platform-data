# Paths Outside the Security Chain and How to Verify Coverage

In a **Spring Security OAuth 2.0/OIDC Resource Server**, an API is typically protected by one or more **SecurityFilterChain**s. Each chain has authentication filters and authorization rules such as **hasAuthority("SCOPE_orders.read")**, **authenticated()**, **permitAll()**, or **denyAll()**.

A dangerous mistake is assuming that declaring **anyRequest().authenticated()** inside one chain automatically protects every URL in the application. In reality, **FilterChainProxy runs only the security filters of the first SecurityFilterChain that matches the request**. If no chain matches, the filters and authorization rules of those chains **are not applied** to the request.

An endpoint might still be blocked by an API Gateway, firewall, or another security layer. However, if you rely on Spring Security to protect the Resource Server, treat **requests outside any security chain** as a gap that must be closed—especially when a controller/servlet actually serves that request.

This lesson explains how Spring Security selects chains, distinguishes **securityMatcher** from **requestMatchers**, designs fallbacks, verifies coverage using real endpoints, and highlights easily overlooked details such as HTTP methods, servlet paths, reverse proxies, Actuator, and dispatcher types.

## 1. Three Very Different States of a Path

| State | Is a SecurityFilterChain selected? | Are authorization rules executed? | Meaning |
|---|---|---|---|
| **Permitted via `permitAll()` in a chain** | Yes | Yes; policy allows requests without authentication | **Intentionally** public endpoint |
| **Protected via `authenticated()`/`hasAuthority` in a chain** | Yes | Yes; policy checks token and permissions per config | Security-controlled endpoint |
| **Matches no chain** | No | No; no Spring Security chain processes the request | Can become a **blind spot** if the endpoint remains reachable |

Another case is **web.ignoring()**: Spring Security is instructed to bypass requests matching certain matchers. This is not **permitAll()** and should not be used casually on business APIs.

### 1.1. Example of a Missed Path

An application has a controller:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class InternalReportController {
    @GetMapping("/internal/reports")
    String reports() {
        return "internal data";
    }
}
~~~

Yet only one SecurityFilterChain exists:

~~~java
@Bean
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        );
    return http.build();
}
~~~

**/internal/reports falls outside the `/api/**` scope.** If no other chain matches, **anyRequest().authenticated()** in **apiChain** does not protect that endpoint. A request without a Bearer token can reach the controller unless another protection mechanism exists.

**Principle:** **anyRequest** covers only requests already selected into **that specific chain**. It is not a blanket command across every servlet or HTTP port in the system.

## 2. How FilterChainProxy Selects a SecurityFilterChain

In a **Servlet** application, Spring Security typically registers its filter via **DelegatingFilterProxy**, delegating to the **springSecurityFilterChain** bean. That bean is typically a **FilterChainProxy** holding an ordered list of **SecurityFilterChain**s.

Each SecurityFilterChain has:

1. A **RequestMatcher** determining which requests belong to the chain.
2. A list of security filters executed for matched requests.
3. A position in the list relative to other chains.

**The first chain whose matcher matches is selected.** Spring Security does not run every matching chain and combine all policies.

~~~mermaid
flowchart TD
    R[HTTP request] --> P[DelegatingFilterProxy / FilterChainProxy]
    P --> C1{Chain 1 matches?}
    C1 -->|Yes| F1[Run chain 1 filters]
    C1 -->|No| C2{Chain 2 matches?}
    C2 -->|Yes| F2[Run chain 2 filters]
    C2 -->|No| C3{Fallback chain matches?}
    C3 -->|Yes| F3[Run fallback filters]
    C3 -->|No| U[No matching security chain]
    F1 --> A[Corresponding authentication and authorization]
    F2 --> A
    F3 --> A
    U --> H[Request continues through remaining layers]
~~~

### 2.1. First Match Wins

Suppose these chains are registered:

~~~text
@Order(1): securityMatcher("/api/admin/**")
@Order(2): securityMatcher("/api/**")
@Order(3): default matcher for all remaining requests
~~~

Selection order:

| Request | Selected chain |
|---|---|
| **GET /api/admin/reports** | Chain 1 |
| **GET /api/orders/42** | Chain 2 |
| **GET /health/live** | Chain 3 |
| **GET /internal/reports** | Chain 3 |

**/api/admin/reports** could also match **/api/**, yet the second chain is never executed because the first chain already matched.

If the first admin chain uses only **authenticated()**, while the second API chain has **hasAuthority("SCOPE_admin.read")**, the second chain's rule **is not automatically added** to admin requests. All required policies must live in the first selected chain.

### 2.2. Do Not Rely on Boot Creating a Fallback Automatically

Spring Boot provides security auto-configuration when an application defines no security of its own. Once the application declares its own **SecurityFilterChain**, Boot's default chain configuration typically steps back.

Therefore, if you declare only one chain restricted to **/api/**, **never assume** Spring Boot will automatically add a chain protecting endpoints outside **/api/**. Another library might register an extra chain, which must be verified at runtime rather than guessed from a single Java file.

## 3. Where Does securityMatcher Differ from requestMatchers?

There are two matcher levels that frequently get confused.

### 3.1. securityMatcher: Scope of the Entire Chain

~~~java
http.securityMatcher("/api/**");
~~~

This line decides **whether the current chain is selected** for a request. If the URL does not match, Spring Security continues checking other chains. Rules inside the current chain **are not evaluated**.

### 3.2. requestMatchers in authorizeHttpRequests: Selecting Rules Inside a Chain

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest()
        .authenticated()
);
~~~

These rules are evaluated **after the request has entered the chain**.

Combining both levels:

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
    );
~~~

Outcome:

- **/api/admin/reports**: enters the chain and requires **ROLE_ADMIN**.
- **/api/orders/42**: enters the chain and requires authentication.
- **/internal/reports**: **does not enter this chain**, so it is unaffected by its **anyRequest**.

~~~mermaid
flowchart TD
    R[Request] --> S{Does the chain's securityMatcher match?}
    S -->|No| N[Try next SecurityFilterChain]
    S -->|Yes| M[Evaluate authorizeHttpRequests]
    M --> C[Specific requestMatchers]
    M --> A[anyRequest inside chain]
    C --> Q[Check corresponding policy]
    A --> Q
~~~

**`securityMatcher` selects the chain; `requestMatchers` selects rules inside the chain.**

## 4. A Safer Configuration with a Fallback Chain

Suppose the Orders API application requires:

- **/api/** requests go through the JWT Resource Server.
- **GET /api/public/** is intentionally public.
- **GET /api/orders/** requires the **orders.read** scope.
- Other APIs must at least be authenticated.
- **GET /health/live** is a public health endpoint.
- All remaining paths are denied by default.

**Spring Security Servlet** example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest()
                    .authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        http
            // No securityMatcher restriction: uses the default matcher.
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/health/live")
                    .permitAll()
                .anyRequest()
                    .denyAll()
            );

        return http.build();
    }
}
~~~

Meaning:

1. **@Order(1)** ensures the API chain is evaluated first.
2. Requests under **/api/** use the Bearer JWT mechanism configured by that chain.
3. **/api/public/** allows tokenless access while still belonging to the API chain.
4. **@Order(2)** is an unrestricted-matcher fallback covering requests not claimed by the prior chain.
5. The fallback allows only **GET /health/live**; other routes hit **denyAll()**.
6. Adding a new **/internal/export** without declaring a policy will not silently become public if requests genuinely pass through `FilterChainProxy`.

**This is an illustrative configuration** and does not cover every path and HTTP method of every application. You may need CORS, Actuator, error pages, static assets, DELETE/PUT rules, client-appropriate CSRF, and other business endpoints. Every exception must be intentional and tested.

### 4.1. When Does a Fallback Use `authenticated` Instead of `denyAll`?

If the architecture requires endpoints outside **/api/** to also accept Bearer tokens and operate, use a covering chain with proper authentication/authorization. **denyAll** is a strong fail-closed option when no routes outside the group are permitted.

Do not blindly set **anyRequest().authenticated()** and assume all actions are safe: **authenticated** only requires authentication, not **orders.write** or export permissions. Sensitive endpoints require explicit policies and resource-level permissions.

### 4.2. Never Place a Catch-All Chain First

Dangerous example:

~~~text
@Order(1): matcher /**            -> permitAll()
@Order(2): matcher /api/**        -> OAuth2 JWT Resource Server
~~~

The first chain matches all requests, so the API chain behind it may never be chosen. Requests can pass through without the JWT authentication the developer expected.

Conversely, a **denyAll** catch-all placed first can block every API even with a properly configured JWT chain behind it.

**Specialized chains go first; broad-matcher fallbacks go last.**

## 5. `permitAll` Does Not Mean Skipping Spring Security

An endpoint with the rule:

~~~java
.requestMatchers(HttpMethod.GET, "/api/public/ping").permitAll()
~~~

can still pass through the Spring Security filters of the selected chain. The **permitAll** policy only states that the authorization step does not require an authenticated principal for matching requests.

| Aspect | **permitAll()** | **Matches no chain** |
|---|---|---|
| FilterChainProxy selects a chain | Yes | No |
| Authorization rule present | Yes | No |
| Chain's security filters can process request | Yes | No |
| Chain security headers/policies can apply | Yes | Not guaranteed |
| Endpoint is intentionally public | Yes | Cannot be inferred |
| Usually suitable for public paths | Yes | No |

**An important detail:** if a **permitAll** endpoint sits inside a JWT chain and the client sends an **invalid Bearer token**, the authentication filter may process that token and return an error before `permitAll` allows it. Thus, a public endpoint returning 200 without a token yet 401 with a bad token **does not mean** `securityMatcher` is broken.

### 5.1. `web.ignoring` Is a Different Mechanism

Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;

@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring().requestMatchers("/assets/**");
}
~~~

**web.ignoring()** configures Spring Security to bypass matching requests at the web security level. For static assets, projects have historically used this approach, yet for most public endpoints you should prefer **`permitAll` inside a `SecurityFilterChain`** to avoid losing other security filters and policies.

A configuration like:

~~~java
web.ignoring().requestMatchers("/api/**");
~~~

can accidentally strip Spring Security protection from the entire API. Never use ignoring to "fix 401/403 errors" on business endpoints.

## 6. Why Does a Chain Miss URLs Even Though `anyRequest` Is Declared?

Consider:

~~~java
http
    .securityMatcher("/api/private/**")
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated()
    );
~~~

Different requests:

| URL | Belongs to this chain? | Is `anyRequest` in this chain evaluated? |
|---|---|---|
| **/api/private/orders** | Yes if matcher matches | Yes |
| **/api/public/ping** | No | No |
| **/internal/reports** | No | No |
| **/health/live** | No | No |
| **/actuator/health** | Depends on actual path/port; outside above pattern | Not by this chain |

This is not a Spring Security bug. It is the exact effect of setting **securityMatcher**. The design flaw is **having no other chain** protecting the remaining paths or being unaware those paths exist.

When a team adds a new controller, Spring Boot automatically registers endpoints from the controller's routes while the previously narrowed chain remains unchanged. A fallback therefore reduces the risk of new routes becoming public by default.

## 7. Coverage Has Two Layers: Chain and Rule

Knowing a request **has a SecurityFilterChain** is still not enough. You must also know **which authorization rule applies inside that chain**.

Example:

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/orders/**")
            .hasAuthority("SCOPE_orders.read")
        .anyRequest()
            .authenticated()
    );
~~~

If the controller exposes:

~~~text
GET    /api/orders/42    -> read order
PUT    /api/orders/42    -> edit order
DELETE /api/orders/42    -> delete order
~~~

then:

- **GET** requires **SCOPE_orders.read**.
- **PUT** and **DELETE** fall into **anyRequest().authenticated()** if no other rule exists.
- A valid token **without write/delete scopes** can pass the authentication requirement of the default rule.

All three methods belong to the API chain, yet **authorization-policy coverage is still incomplete**.

| Check layer | Question |
|---|---|
| **Filter-chain coverage** | Does the request enter an appropriate Spring Security chain? |
| **Authorization-rule coverage** | Within that chain, does the rule for that exact path/method require sufficient privileges? |
| **Domain/resource authorization** | May the principal act on this specific record, tenant, or data state? |

Sound security requires all three.

## 8. Context Path, Servlet Path, and URL Matching Mechanics

A public URL is not necessarily the exact string **RequestMatcher** sees inside the application.

Factors that commonly affect matching:

| Factor | Example | Risk of misunderstanding |
|---|---|---|
| **Context path** | /shop | External URL has a prefix differing from the servlet path matched |
| **Servlet path** | /api | App has multiple servlet mappings or a dedicated DispatcherServlet |
| **Request URI/path info** | /orders/42 | Matchers evaluate part of the path per specific rules |
| **Reverse proxy rewrite** | /v1/orders → /api/orders | Backend `securityMatcher` sees the backend route, not necessarily the public route |
| **Trailing slash** | /api, /api/ | May behave differently across matchers/versions |
| **Path encoding** | Encoded slashes, multiple slashes | Containers, firewalls, and matchers may normalize differently |
| **HTTP method** | GET, POST, OPTIONS | Method-specific rules do not apply to every method |

Spring Security offers different **RequestMatcher** types and integrations with Spring MVC/`PathPattern`. Exact behavior depends on the Spring Security version, servlet configuration, and how matchers are constructed.

### 8.1. Do Not Test Only `/api/orders/42` and Forget `/api` and `/api/`

If configuring **securityMatcher("/api/**")**, verify against the real app:

~~~text
GET /api
GET /api/
GET /api/orders
GET /api/orders/42
POST /api/orders
OPTIONS /api/orders
~~~

Never assume **/api/** definitely matches or does not match **/api** across all `RequestMatcher` types and versions. Verify with requests in your real context.

### 8.2. Multiple Servlets May Need Different Matchers

Spring Boot MVC normally has one DispatcherServlet, yet an application can register other servlets or configure non-default servlet mappings. Then a request matcher written assuming a **/** servlet path may fail to match as expected.

When multiple servlets exist:

- Identify the actual `contextPath`, `servletPath`, and `pathInfo`.
- Choose the matching mechanism supported by your Spring Security version.
- Test routes on each servlet/registration, not just a MockMvc request lacking servlet paths.
- Never assume the main DispatcherServlet's chain covers every servlet deployed in the container.

## 9. Filter Registration Is Also a Boundary

Even a **SecurityFilterChain** with a catch-all matcher cannot protect a request if **the Servlet filter proxy is not registered or executed for that request**.

In standard Spring Boot Servlet apps, Spring Security is registered automatically. However, manual deployments, multiple web contexts, or customized filter registrations must verify:

- Does the **springSecurityFilterChain** bean exist and get registered?
- Are the Servlet filter registration's URL patterns appropriate?
- Which dispatcher types does the filter handle?
- Are there other servlets or contexts where requests bypass the filter proxy?
- Does a profile or conditional bean accidentally disable a SecurityFilterChain?
- Does any test configuration accidentally turn off filters?

**Never fix a filter registration bug merely by adding `requestMatchers` to a chain that is never invoked.**

### 9.1. DispatcherType: REQUEST, FORWARD, ERROR, ASYNC

Servlets use dispatcher types such as:

- **REQUEST** for normal incoming requests.
- **FORWARD** when the container forwards internally.
- **ERROR** for error dispatches.
- **ASYNC** for asynchronous processing.
- **INCLUDE** for include operations.

Filter registration and authorization can apply differently by dispatcher type. Spring Boot offers a property to configure dispatcher types on the security filter depending on version, such as **spring.security.filter.dispatcher-types**.

Verify:

1. Are **REQUEST** dispatches protected as expected?
2. Does an internal **FORWARD** to a sensitive endpoint alter filter/authorization handling?
3. Does an **ERROR** dispatch to **/error** get blocked by a fallback and alter the original response?
4. Does **ASYNC** processing create a new dispatch needing matching security context and filters?

Not every FORWARD/ERROR is a vulnerability. Many applications intentionally permit certain dispatches to render errors properly, while controlling route boundaries so overly broad rules do not expose business controllers.

### 9.2. `/error` Can Be Blocked by `denyAll`

Suppose an initial request triggers a 500 error and the container dispatches to **/error**. If a `denyAll` fallback blocks the error dispatch, clients may see 403 or another response that complicates troubleshooting.

Solutions include configuring dispatcher-specific rules or an appropriate error route, depending on version and architecture. However, **never bypass security for all paths just to display error pages**. Test error dispatches explicitly and avoid leaking sensitive data.

## 10. Reverse Proxies and External Paths

Suppose a request travels:

~~~text
Client:
  https://api.example.com/v1/orders/42

Gateway:
  /v1/orders/42  ->  orders-service:8080/api/orders/42

Spring MVC backend:
  GET /api/orders/42
~~~

If the backend configures **securityMatcher("/api/**")**, verify what path the matcher actually sees after proxy rewrites, context paths, and servlet mappings. You cannot rely solely on the URL shown in the browser.

Scenarios worth checking:

- Proxy rewrites the path before forwarding to the Servlet container.
- Another ingress route does not rewrite the same way as the primary route.
- The backend is reachable directly on an internal port.
- Client-supplied `X-Forwarded-Prefix` or `Host` headers are improperly trusted.
- The application uses a different context path in staging versus production.
- An alias route for the same controller is added after the chain was configured.

Analysis chain:

~~~text
Public URL
    -> Ingress/Gateway route
    -> Rewrite/forwarded headers
    -> Container context path
    -> Servlet path + pathInfo
    -> First matching SecurityFilterChain
    -> Authorization rule
    -> Controller
~~~

Therefore, security testing should include **requests through the real public URL** in a deployment test environment, alongside backend MockMvc tests.

## 11. Do Not Forget Actuator and the Management Port

Spring Boot applications may use Actuator, exposing endpoints such as:

~~~text
/actuator/health
/actuator/info
/actuator/metrics
/actuator/env
/actuator/heapdump
~~~

Which endpoints are active or exposed depends on Actuator configuration. Several endpoints contain sensitive details and require strict protection.

Two common models exist:

**Actuator on the same port/context as the application:** management paths must be covered by security configuration in that context. Never assume **securityMatcher("/api/**")** protects **/actuator/**.

**Actuator on a separate management port/context:** a separate web server/context and policy may apply. You cannot use the application port's fallback chain as proof that the management port is protected.

Check:

- Is the management port separated?
- Which Actuator endpoints are exposed?
- Are health/liveness endpoints intentionally public?
- Are metrics, env, heapdump, or logfile properly restricted by network and permissions?
- Is there a dedicated management ingress?
- What do no-token, invalid-token, and under-privileged user scenarios return on **the actual port**?

## 12. OPTIONS and CORS Preflight

A browser may send:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

A **200/204** response to OPTIONS may be correct for CORS preflight. Yet it **does not prove `POST /api/orders` is protected or permitted**.

CORS checks cross-origin access from browsers; it does not replace JWT signature verification, Bearer authentication, or authorization.

Test separately:

- **OPTIONS /api/orders** with proper preflight headers.
- **POST /api/orders** without a token.
- **POST /api/orders** with a JWT having a bad signature or wrong audience.
- **POST /api/orders** with a valid token lacking write permission.
- **POST /api/orders** with a valid write-scoped token meeting domain policy.

Do not omit OPTIONS from your HTTP map, yet never use an OPTIONS outcome as the sole test for an endpoint.

## 13. Route and Method Coverage Checklist Matrix

To audit a real application, build a matrix:

| Endpoint | Port/context | Expected chain | Expected rule | Without token |
|---|---|---|---|---|
| **GET /api/public/ping** | API port | API chain | permitAll | Allowed |
| **GET /api/orders/42** | API port | API chain | SCOPE_orders.read | Usually 401 |
| **POST /api/orders** | API port | API chain | SCOPE_orders.write | Usually 401 |
| **GET /api/admin/reports** | API port | API/admin chain | Admin role/scope | Usually 401 |
| **GET /internal/coverage-probe** | API port | Fallback | denyAll | Denied |
| **GET /health/live** | API port | Fallback | permitAll | Allowed |
| **GET /actuator/health** | Actual management port | Management policy | Per design | Per design |
| **GET /actuator/env** | Actual management port | Management policy | Block unintended access | Per design |

This is a **requirements table**, not test results. With the configuration in section 4, **POST /api/orders** falls into **anyRequest().authenticated()**, so it **does not yet satisfy the SCOPE_orders.write requirement** in the table. An explicit rule must be added.

Comparing **desired policy** against **written rules** uncovers bugs not only at the chain level, but also on specific methods and paths.

### 13.1. A Missing Handler Can Also Return 404

Calling **GET /secret/not-found** when the application has no matching controller returns 404 simply because no route exists. It **does not prove Spring Security blocked access**.

To verify coverage, use:

- Routes with real handlers that exhibit clear behavior when unblocked; or
- A test-only probe controller created inside the test context.

That way, when a request is denied, you know the denial came from security policy rather than simply a missing handler.

## 14. MockMvc Must Run with Spring Security Filters

A common testing mistake is running MockMvc without including the security filter chain in the request pipeline.

### 14.1. `standaloneSetup` Is Not Equivalent to Production

Example:

~~~java
MockMvc mockMvc = MockMvcBuilders
    .standaloneSetup(new OrderController(...))
    .build();
~~~

This suits unit-testing controllers yet **does not run the real `springSecurityFilterChain`**.

Similarly:

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

disables adding Servlet filters to MockMvc. Using this kind of test to determine whether a URL is protected by `JwtDecoder` can lead to completely wrong conclusions.

### 14.2. Testing Private Endpoints in a Production-Like Context

An appropriate pattern in Spring Boot Servlet:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ApiSecurityCoverageTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void ordersEndpointRequiresToken() throws Exception {
        mockMvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

This example assumes JUnit and Spring Boot Test/MockMvc imports. Run it against **the real `SecurityFilterChain` and controller mappings**. With a default JWT Resource Server, a private endpoint without a Bearer token typically returns **401**.

If a route has no handler and returns 404, 404 cannot serve as security proof. Tests should verify the handler exists and filters are wired into the context.

### 14.3. Creating a Test-Only Probe Outside Specialized Chains

To prove the fallback genuinely blocks paths outside **/api/**, you can add a **test-only** controller:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CoverageProbeController {

    @GetMapping("/internal/coverage-probe")
    ResponseEntity<Void> probe() {
        return ResponseEntity.noContent().build();
    }
}
~~~

Without security, this handler would return **204 No Content**. With a **denyAll** fallback, the request should be blocked before reaching the handler:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@Import(CoverageProbeController.class)
class CoverageProbeTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void pathOutsideApiChainIsDenied() throws Exception {
        mockMvc.perform(get("/internal/coverage-probe"))
            .andExpect(status().isForbidden());
    }
}
~~~

This is an abbreviated test example; exact imports, bean registration, and status codes depend on app configuration. If the fallback uses a different authentication entry point, it may return another **4xx** status. The key is that **the handler exists** and unpermitted requests never reach it.

Never accidentally deploy a test-only probe as a production endpoint.

### 14.4. When Building MockMvc Manually from `WebApplicationContext`

Spring Security Test provides the **`springSecurity()`** configurer for MockMvc:

~~~java
MockMvc mockMvc = MockMvcBuilders
    .webAppContextSetup(context)
    .apply(springSecurity())
    .build();
~~~

Remember to use the Spring Security Test imports and verify filters are actually registered. **`@WebMvcTest`** is a useful slice test, yet it may load a different bean set from the full application context; it should not be the sole proof of production coverage.

## 15. Inspecting the Runtime Selected Chain

### 15.1. Enabling `FilterChainProxy` Logs in Test Environments

You can temporarily enable logging:

~~~yaml
logging:
  level:
    org.springframework.security.web.FilterChainProxy: TRACE
~~~

Depending on the Spring Security version, logs show request details and which filter chain handled the request. Do not rely on logs alone: combine them with request tests and a review of the `SecurityFilterChain` list.

**Never log raw Bearer tokens, Authorization headers, cookies, secrets, or sensitive payloads.** Use verbose logging only in appropriate environments and only for as long as needed.

### 15.2. Inspecting the List of `SecurityFilterChain`s

In Servlet Spring Security, **FilterChainProxy** manages the chains and provides APIs to inspect them in an appropriate context. A configuration test can check:

- Number of chains.
- Each chain's matcher and order.
- Which chains include `BearerTokenAuthenticationFilter`.
- Whether a broad fallback matcher exists at the end.
- Which paths are intentionally ignored.
- Which chain matches **first** for each request.

**Do not check only "at least one chain matches"** if the first chain is an overly broad **permitAll**. Example:

~~~text
Chain 1 (first):  /**             -> permitAll
Chain 2:          /api/admin/**   -> hasRole("ADMIN")
~~~

**/api/admin/reports** gets swallowed by Chain 1 first, rendering Chain 2 useless for protecting that request.

### 15.3. Real Requests Matter More Than String Pattern Comparisons

A manually constructed `MockHttpServletRequest` missing proper `contextPath`/`servletPath` can produce different matcher results from real traffic. Thus, chain introspection is an analysis aid, whereas **integration requests against the real application** are the primary evidence of coverage.

## 16. Testing Through Real HTTP, Gateways, and Management Ports

MockMvc does not traverse the full gateway, reverse proxy, TLS, ingress, and real container configuration. In multi-tier systems, test all of:

1. **Public URLs** used by real clients.
2. **Direct backend URLs/ports** if reachable in the architecture.
3. **The management port** if separated.
4. Paths with differing prefixes/rewrites.
5. Necessary **GET, POST, PUT, DELETE, OPTIONS** HTTP methods.
6. Missing tokens, forged signatures, wrong issuers/audiences, expired tokens.
7. Valid tokens lacking required scopes or tenant permissions.
8. FORWARD/ERROR/ASYNC dispatches in flows that use them.

Example private endpoint check:

~~~bash
curl -i https://api.example.com/api/orders/42
~~~

With a typical JWT Resource Server, a private endpoint without a token returns **401 Unauthorized** and may include **WWW-Authenticate: Bearer**.

Checking an endpoint outside **/api/**:

~~~bash
curl -i https://api.example.com/internal/coverage-probe
~~~

If the test handler exists and the `denyAll` fallback is active, the request must be denied. **Do not infer security from a 404 on an unmapped URL.**

When testing with privileged tokens, use test-environment tokens with short lifetimes, trusted test issuers/JWKS, and proper secret handling. Never put production tokens in logs or tickets.

## 17. Three Types of Missing Protection Often Confused as One

| Error category | Example | Fix |
|---|---|---|
| **No matching SecurityFilterChain** | Only `securityMatcher("/api/**")` exists while `/internal/export` controller exists | Add/adjust chains or fallback |
| **Chain exists, but rule is too broad** | PUT/DELETE requires only `authenticated()` instead of write/delete scope | Fix `requestMatchers` and domain authorization |
| **Rule exists, but Authentication is untrusted** | Custom filter extracts roles from unverified JWT JSON | Use trusted `JwtDecoder`/introspection; fix trust boundary |
| **Chain bean exists, but request bypasses FilterChainProxy** | Different filter registration/dispatcher/context, or test disabled filters | Fix filter wiring, deployment/test setup |

Distinguishing the right category prevents slapping on extra matchers without fixing the root cause.

### 17.1. Anti-Patterns to Flag During Review

- Narrow **securityMatcher** with no fallback.
- **anyRequest().permitAll()** appearing in an early chain with a broad matcher.
- **web.ignoring("/api/**")** or bypassing entire business endpoint groups.
- **authenticated()** rules on methods that need specific scopes/roles.
- A high-priority SecurityFilterChain shadowing a specialized chain behind it.
- MockMvc using **standaloneSetup** or **addFilters=false** in security tests.
- Tests asserting 404 on a non-existent route as proof of security.
- Reverse proxy rewriting URLs outside the backend matcher's scope.
- Management endpoints on a separate port with no security review.
- Custom servlet/filter registrations missing needed dispatchers/paths.
- Enabling a production profile that drops a SecurityFilterChain or unintentionally opens `permitAll`.

## 18. Practical Workflow for Auditing Coverage

### Step 1 — Inventory Real Routes

Collect all HTTP endpoints from controller mappings, API specs, actuator mappings if applicable, servlet registrations, gateway routes, and management ports. Record **HTTP method, public path, backend path, port, and context**.

Do not collect only endpoints starting with **/api/**.

### Step 2 — List Chains and Order

Example:

~~~text
@Order(1): /api/admin/**     -> admin JWT policy
@Order(2): /api/**           -> general JWT API policy
@Order(3): any request       -> fallback deny/public exceptions
~~~

Identify which chain has broad matchers, which requires Bearer tokens, and which serves as fallback.

### Step 3 — Trace Each Route to Its First Matching Chain

For each request:

~~~text
HTTP method + actual servlet path
  -> First matching SecurityFilterChain
  -> Selected authorizeHttpRequests rule
  -> Required authentication/scope/role
  -> Domain resource policy
~~~

If no chain matches, determine whether that is intentional or a vulnerability. If a chain matches yet the rule grants too much, fix it as well.

### Step 4 — Design Fail-Closed

If deployment process requires new endpoints to undergo security review first, a **denyAll** fallback or equivalent fail-closed policy is appropriate. Define explicit public exceptions rather than using global `permitAll` for convenience.

### Step 5 — Test No-Token Scenarios

For private endpoints **with real handlers**, requests without tokens must be rejected by authentication per policy—usually **401** for a Bearer Resource Server. For a `denyAll` fallback, test real endpoints outside the API chain to avoid the 404 trap.

### Step 6 — Test Valid and Invalid Tokens

Test bad signatures, wrong issuers/audiences, expired tokens; valid tokens missing scopes; tokens with scopes belonging to the wrong tenant; and valid authorized tokens. Authentication, request authorization, and domain policy layers must be tested independently.

### Step 7 — Test Deployment Paths

Verify proxy rewrites, Servlet contexts, management ports, HTTP methods/path variants, and relevant dispatcher types. Catch discrepancies between local MockMvc and real traffic before production.

### Step 8 — Tie Coverage Review to Adding Endpoints

Whenever adding a controller or a dependency that registers endpoints:

- Record routes in the coverage matrix.
- Identify the selected chain and policy.
- Add negative tests.
- Review changes to **@Order**, **securityMatcher**, **web.ignoring**, and fallbacks.
- Deploy only once sensitive endpoints have explicit protection.

## 19. Self-Check Exercises

**Question 1.** A chain has **securityMatcher("/api/**")** and **anyRequest().authenticated()**. Does that `anyRequest` rule protect a **/admin/export** controller?

**No.** `/admin/export` falls outside the chain's scope; another chain or fallback is required.

**Question 2.** Does a chain using **permitAll("/api/public/**")** mean requests skip security filters?

**No.** `permitAll` is an authorization decision inside the chain; security filters may still process the request.

**Question 3.** If two chains both match **/api/admin/reports**, do their rules combine?

**No.** The first matching chain in priority order is selected.

**Question 4.** Does **GET /secret/unknown** returning 404 prove `/secret/**` is protected?

**No.** It may simply mean no handler exists. Test real routes or a test-only probe.

**Question 5.** If a `denyAll` fallback exists on the application port, is a separate Actuator management port definitely protected?

**Cannot be concluded.** Inspect the actual management port's context and policy.

**Question 6.** If a SecurityFilterChain matches the request, is the endpoint already secure?

**Not necessarily.** Rules inside the chain might be too broad, omit needed scopes, or skip tenant/ownership checks.

**Question 7.** Why can MockMvc give misleading conclusions?

Because MockMvc can be built without Spring Security filters attached, or load only a test slice that differs from production.

## Conclusion

Spring Security coverage must be evaluated at **two levels**: whether a request falls into an appropriate **SecurityFilterChain**, and whether rules inside that chain require **the right permissions** for that path and method. **FilterChainProxy picks the first matching chain**, and **anyRequest** inside a chain scoped by **securityMatcher** never automatically extends across the whole application.

To prevent missed endpoints, order chains clearly, include a **fallback with an explicit policy**, prefer **`permitAll` inside a chain** over bypassing security, and test requests against **real handlers** with security filters enabled.

When assessing real coverage, do not overlook **HTTP methods, path/context/servlet mappings, proxy rewrites, dispatcher types, Actuator/management ports, and deployment profiles**. A 404 response, a filterless MockMvc test, or a single `anyRequest` line in code is never sufficient proof that an API is secure.

### References

- [Spring Security — Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html#_multiple_httpsecurity_instances)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Servlet Security Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security API — FilterChainProxy](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/FilterChainProxy.html)
- [Spring Security API — SecurityFilterChain](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/SecurityFilterChain.html)
- [Spring Security — Testing Spring MVC](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [Spring Boot — Security](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
- [Spring Boot — Actuator Endpoint Security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.security)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
