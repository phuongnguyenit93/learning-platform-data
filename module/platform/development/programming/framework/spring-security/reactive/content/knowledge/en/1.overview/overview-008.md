# Prerequisites and Learning Sequence: From HTTP Requests to Business Security in Spring Security Reactive

> **Scope:** This lesson builds a knowledge map and practical sequence for **Spring WebFlux + Spring Security Reactive** applications. The goal is to understand how an HTTP request is identified, authenticated, and authorized, followed by checking permissions on **business actions and data**. The examples use Java and JWT Bearer tokens for APIs; they represent one concrete learning track, not the only login mechanism in Spring Security.

## 1. Destination of the Learning Path

After this lesson, learners should be able to answer four questions in order:

1. **What request is arriving?** HTTP method, path, headers, cookies/body, HTTPS protocol, and which data is untrusted.
2. **Who is calling?** Can the application verify the caller's identity/credentials? How does that mechanism produce an Authentication object?
3. **Which features can that caller invoke?** What operations do path rules and method/service rules permit based on roles, authorities, or scopes?
4. **Is that caller allowed to act on this specific object?** For example, even with permission to view orders, they may only view their own orders or those of their assigned tenant.

**Authentication** answers "who is calling?". **Authorization** answers "what can be done with which resource?". **Business security** also evaluates state, owner, tenant, membership relationships, and domain-specific conditions. Having a valid JWT or the USER role is not enough to access every record.

A satisfactory learning outcome must be demonstrated through observable behavior: requests missing identity are blocked; requests with identity but insufficient permissions are denied; requests with sufficient functional permissions but wrong owner/tenant cannot retrieve data; only fully valid requests succeed.

## 2. Required Prerequisites

### 2.1. Java, Spring, and the HTTP protocol

- **Java 17+**: classes/interfaces/records, generics, exceptions, lambdas, dependency injection, and running JUnit tests.
- **Spring Boot**: components, beans, configuration, Controller/Service/Repository, environment-based configuration, and dependencies.
- **HTTP**: GET/POST/PUT/PATCH/DELETE methods, URL/path/query, headers (especially Authorization), cookies, body, status codes, HTTPS/TLS. Do not equate HTTP state with login sessions: HTTP itself is stateless, though applications can use sessions/cookies.
- **Common status codes**: 200/201 on success; 400 on malformed requests; **401** when authentication is required or credentials are invalid; **403** when authenticated but not permitted; **404** when non-existent or when the API intentionally avoids disclosing resource existence. Actual handling also depends on entry points, exception handlers, and product policy.

**Prerequisite check:** use an HTTP client to send GET /api/orders/42, identify the method, path, and Authorization header, and clearly distinguish whether the server knows "who is calling" from whether it allows viewing order 42.

### 2.2. Reactive WebFlux and Project Reactor

- **Mono<T>** represents an asynchronous stream with at most one value; **Flux<T>** can emit multiple values. Most work in a reactive chain happens upon subscription, not merely because a Mono/Flux was constructed.
- **map** transforms values synchronously; **flatMap** composes an asynchronous operation returning a Publisher; **filter** drops values failing a predicate; **switchIfEmpty** handles empty results; **onErrorResume** handles errors per policy.
- **Never block the event loop** with block(), Thread.sleep(), synchronous JDBC, or synchronous HTTP calls on the event loop. If an irreplaceable blocking library exists, enforce a separate execution boundary and a clear migration plan.
- **Reactor Context** attaches data to a subscription and propagates through the reactive chain; unlike ThreadLocal, execution can switch threads. In Spring Security Reactive, SecurityContext is accessed via ReactiveSecurityContextHolder inside the pipeline.
- **WebFlux** uses WebFilter, ServerWebExchange, and SecurityWebFilterChain; do not copy Servlet/MVC OncePerRequestFilter, HttpSecurity, or SecurityFilterChain directly into Reactive configuration.

**Prerequisite check:** explain why reading a user from ThreadLocal inside a reactive processing step can be wrong and why calling block() in a WebFlux controller is risky.

### 2.3. Foundational security concepts

- **Principal**: authenticated identity; **credentials**: data used to prove identity; **authorities**: permissions attached to Authentication. Roles are typically represented as authorities with the ROLE_ prefix; scopes in a JWT Resource Server are typically mapped to SCOPE_… by default.
- **Session/cookie and Bearer token** are two different ways of carrying authentication state. For Bearer JWTs, the server must verify signature, expiration, issuer, and required constraints like audience; never treat merely decoding the payload as authentication.
- **OAuth 2.0** primarily addresses access delegation; **OpenID Connect** adds a user identification layer. An API acting as a Resource Server usually receives and validates access tokens, rather than issuing tokens itself merely because Resource Server is declared.
- **Least privilege, deny by default, defense in depth**: open only necessary permissions; both the HTTP entry point and the business layer must protect their own domains of responsibility.
- **CSRF** and **CORS** are distinct: CORS governs cross-origin access enforced by browsers; CSRF involves browsers automatically sending credentials (typically cookies). Never disable CSRF solely because "the API uses JSON" if the app still relies on cookie-based authentication.

## 3. Map of a Secured Request

Consider GET /api/orders/42 on an API using Bearer tokens:

~~~mermaid
flowchart TD
    A["Client sends HTTP request"] --> B["WebFlux + SecurityWebFilterChain"]
    B --> C{"Are credentials valid?"}
    C -->|"No"| D["401 / authentication entry point"]
    C -->|"Yes"| E{"Route access permitted?"}
    E -->|"No"| F["403 / access denied"]
    E -->|"Yes"| G["Controller / Handler"]
    G --> H{"Service / action permitted?"}
    H -->|"No"| F
    H -->|"Yes"| I{"Allowed to access order 42 in this tenant?"}
    I -->|"No"| J["403 or 404 per policy"]
    I -->|"Yes"| K["Reactive Repository"]
    K --> L["Return permitted data"]
~~~

The diagram illustrates **a typical path for an endpoint requiring login**. Public routes may skip identity requirements; data or system errors are not necessarily authorization errors. JWTs are validated at the security boundary and converted into Authentication; controllers do not manually verify signature strings in every method.

| Layer | Question to answer | Example |
| --- | --- | --- |
| HTTP/transport | Did the request arrive over HTTPS and conform to the API contract? | Method, path, headers, body, TLS |
| Authentication | Is the token/session valid and who does it belong to? | JWT validated, principal is subject |
| Request authorization | Which authority does this endpoint require? | GET /api/orders/** requires SCOPE_orders:read |
| Method/action authorization | Can the caller execute this business operation? | Order-reading service accepts only orders:read |
| Object/tenant authorization | Does the caller have permission on the specific order? | Matching ownerId or tenantId |
| Data/output boundary | Does the result contain only permitted data? | Tenant-filtered query; DTO avoids exposing sensitive fields |

**Layered principle:** Permission to call a path does not automatically grant permission on every record. A client-supplied ID cannot be trusted as "belonging to the caller."

## 4. Recommended Learning Sequence and Gate Criteria per Stage

Follow the order below so each stage yields a verifiable outcome before expanding:

| Stage | What to learn and why | Minimum practice | Sign of understanding |
| --- | --- | --- | --- |
| **0 — HTTP** | Request/response, HTTPS, cookies, headers, 401/403/404 | Send the same URL with/without Authorization | Accurately classify each case |
| **1 — Reactive** | Mono/Flux, subscription, errors, Reactor Context | Write a data-fetching pipeline without block() | Explain when work executes and where errors go |
| **2 — WebFlux routing** | Controller/functional routes, WebFilter, ServerWebExchange | Create GET /health and GET /api/orders/{id} | Distinguish routing from security |
| **3 — Security chain** | SecurityWebFilterChain, ServerHttpSecurity, matcher order | Open /health, deny the rest by default | Unknown routes do not accidentally become public |
| **4 — Authentication** | Authentication, SecurityContext, Resource Server, JWT | Configure a real issuer in a test environment | Missing/invalid/expired tokens are rejected |
| **5 — Route permissions** | authenticated, permitAll, hasAuthority, denyAll | Require SCOPE_orders:read for GET orders | Valid token lacking scope is blocked |
| **6 — Method permissions** | @EnableReactiveMethodSecurity, @PreAuthorize | Block the order-reading service when scope is missing | Calling service via Spring bean still enforces policy |
| **7 — Object permissions** | owner, tenant, order status, filtered queries | Prevent Alice from reading Bob's order | Same scope but different owner leaks no data |
| **8 — Testing & operations** | WebTestClient, mockJwt, error codes, safe log/audit | Test identity × permission × data matrix | Evidence exists for both allow and deny branches |

**How to learn effectively:** after each stage, proceed only once you can write one positive example and one negative example. If a 401/403/404 result cannot be explained, return to the corresponding stage rather than randomly tweaking matchers or removing checks.

## 5. Illustrative Configuration: The HTTP Gatekeeper

The Java snippet below sits inside a Spring Boot application using WebFlux, Spring Security, and OAuth2 Resource Server/JWT support. It is **a configuration class within a project**, not a standalone runnable Java program. A real issuer/decoder and business beans must be provided for the full application to run.

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .pathMatchers("/api/**").authenticated()
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

**Explanation in processing order:**

1. **@EnableWebFluxSecurity** activates the security model for WebFlux; **SecurityWebFilterChain** describes the HTTP policy.
2. **/health** is opened explicitly. **GET /api/orders/** allows only principals with the matching authority; remaining APIs require authentication; other paths are denied by default.
3. **oauth2ResourceServer(...jwt(...))** enables Bearer JWT processing with a configured decoder/validator. When using Spring Boot, an example configuration structure is:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/realms/demo
~~~

The address above only **illustrates syntax**; replace it with a real issuer and ensure the discovery document/signing keys exist. Depending on the API contract, also configure **audience** validation, permission claim mapping, and invalid-token handling; by default, validating a JWT does not mean the token was issued for this specific API.

4. **@EnableReactiveMethodSecurity** prepares permission control on Spring-managed reactive methods. URL policies do not automatically protect business logic invoked from another entry point.
5. **csrf(...disable)** is only appropriate for a truly stateless API example receiving client-attached Bearer tokens and not relying on cookies for authentication. For cookie/session-based browser logins, evaluate CSRF and maintain appropriate protection. CORS requires its own policy specifying allowed origins/methods/headers.

**Matcher order matters:** specific rules must precede broad rules. When multiple SecurityWebFilterChains exist, inspect both securityMatcher and chain ordering; avoid letting a broad chain accidentally capture all requests ahead of a specialized chain.

## 6. Going Deeper from Functional Permissions to Business Permissions

Suppose the system has two users, Alice and Bob. Both hold the SCOPE_orders:read authority, yet order 42 belongs to Bob. With only a route rule requiring the scope on GET /api/orders/**, Alice could try GET /api/orders/42 and exploit an **IDOR/BOLA** vulnerability (ID-based object access without object-level authorization).

The business layer must check **the exact object being read or modified**. The Java example below describes the Order/OrderRepository contract and Service logic. It is a snippet to integrate into an application with an OrderRepository implementation; not a standalone Spring Boot application.

~~~java
package example.orders;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

record Order(String id, String ownerId, String description) {}

interface OrderRepository {
    Mono<Order> findById(String id);
}

@Service
public class OrderService {
    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize("hasAuthority('SCOPE_orders:read')")
    public Mono<Order> findVisibleOrder(String orderId) {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .flatMap(currentUserId ->
                orders.findById(orderId)
                    .filter(order -> order.ownerId().equals(currentUserId))
                    .switchIfEmpty(Mono.error(
                        new ResponseStatusException(HttpStatus.NOT_FOUND)
                    ))
            );
    }
}
~~~

- **@PreAuthorize** checks the scope at the service entry; **filter** checks each record's owner. Either a missing record or a mismatched owner yields 404 under a policy that avoids disclosing order existence. An application may choose 403 for unauthorized access if its existence-disclosure policy permits; be consistent and test it.
- In the example, **Authentication.getName() is assumed to be an internal ID matching ownerId**. With real JWTs, getName() usually comes from the subject claim and may **differ** from internal IDs. Map from the authenticated identity to a business ID using a trusted rule, never arbitrarily comparing username/email with tenantId.
- **Service-level checks still must protect other callers**, not only HTTP. Method security uses Spring AOP: internal calls within the same object (self-invocation) can bypass the protective proxy. If business logic runs from a message consumer or batch job, explicitly define the task's identity and policy.
- With multi-tenant data, comparing ownerId alone is insufficient. Pass the verified tenant into queries (e.g., findByIdAndTenantId), verify tenant membership/roles, and enforce checks at update time. State transitions, money transfers, or sensitive actions may require checking conditions **after loading data and at write time** to prevent race conditions.
- **Never grant permissions based on ownerId or role in a client-sent JSON body.** Those attributes must be verified from the validated token and server-side data.

## 7. Outcome Matrix to Observe

Consider GET /api/orders/42 when the route requires SCOPE_orders:read:

| Case | Which check decides? | Expected result |
| --- | --- | --- |
| Missing Bearer token | HTTP authentication | **401** |
| Token with bad signature / expired / invalid issuer | JWT validation | **401** |
| Valid token lacking SCOPE_orders:read | Request authorization or @PreAuthorize | **403** |
| Valid token with scope, order owned by someone else | Business/object authorization | **404** per example policy |
| Valid token with scope, matching order owner | All layers | **200** and only permitted data |
| Valid token from another tenant even with matching record ID | Tenant/data authorization | **403/404** per policy, no data leaked |
| Path outside exposed API | Default route policy | Denied by configuration; not public by default |

**Note on 401 and 403:** 401 signals authentication is required, while 403 signals the identity is known but lacks sufficient permissions; exact response headers and bodies depend on Spring Security / exception-handling configuration. Do not assume all authentication errors always produce the exact same JSON format. For policies hiding resources with 404, tests must assert that owner/tenant/object names are not leaked in response bodies or logs returned to clients.

## 8. Testing Layer by Layer, Not Just the Happy Path

### 8.1. Testing workflow

1. **Web layer:** use WebTestClient for requests missing a token, with an unauthorized token, and with an authorized token; spring-security-test provides mockJwt() to supply a principal in tests, not to verify real JWT signatures.
2. **Service layer:** test @PreAuthorize via a **proxied Spring bean** along with matching/mismatched owner cases. A unit test calling a manually instantiated object with new does not automatically exercise AOP proxies.
3. **Repository/data layer:** ensure queries accurately filter by owner/tenant; for updates, verify affected rows and state-transition conditions.
4. **Real authentication integration:** test decoder/issuer/audience/expiry and claim mapping with realistic test tokens. mockJwt() does not replace this test layer.
5. **Negative tests:** test another user's ID, another tenant, missing scope, wrong scope, disabled or revoked users, wrong HTTP methods, and undeclared paths; verify both outcomes and returned payloads.

Example WebTestClient test structure when the client is configured with Spring Security test support:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

// Illustrative snippet inside a @Test method;
// client is a configured WebTestClient, and record 42 must be properly seeded.
client
    .mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders:read")))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

The example above **only tests the success branch** when the test environment seeds order 42 for the principal created by mockJwt(); you must explicitly set the subject and corresponding owner data. Add similar tests for missing scope and mismatched owner; never infer that a single 200 request proves the system is secure.

### 8.2. Tracing and troubleshooting

When encountering unexpected results, trace sequentially: **request → selected chain → authentication → mapped authorities → route matcher → method security → owner/tenant query → exception handler**. You can enable appropriate logging in test environments, yet never print access tokens, passwords, session IDs, sensitive data, or full claims to logs. Audit logs should record the action, appropriate resource identifier, normalized principal, allow/deny decision, and correlation ID per data-protection policy.

## 9. Common Pitfalls When Moving from HTTP to Business Logic

1. **"If a JWT can be decoded, the user is logged in."** Base64 decoding does not verify signature, expiration, issuer, or audience. Use a proper decoder/validator and protect transport.
2. **"Having ROLE_ADMIN or read scope grants access to all data."** Roles/scopes usually grant functional capabilities; owner/tenant/business status still must be checked separately unless an approved global policy says otherwise.
3. **"Blocking routes is enough."** Business logic can be invoked from other entry points; route security does not replace method and data authorization.
4. **"Reactive apps use SecurityContextHolder like MVC."** Reactive authentication flows through Reactor Context; ThreadLocal and thread switches can lose or corrupt context.
5. **"Adding block() to grab the current user is faster."** block() breaks the non-blocking model on the event loop and can cause stalls or deadlocks; keep the Mono/Flux flow and compose with flatMap.
6. **"@PreAuthorize always runs on every call."** Spring method security requires a valid bean/proxy; self-invocation and manually new-ed objects can bypass interception.
7. **"CORS replaces CSRF" or "stateless means always disable CSRF".** The two mechanisms serve different purposes; CSRF decisions depend on how browsers carry credentials.
8. **"The request body has the right tenantId, so it can be trusted."** Resolve tenant from trusted sources, verify membership, and constrain queries/writes by tenant on the server.
9. **"Returning 404 prevents leaks."** If a query reads unauthorized data before deciding, caches, logs, side effects, or error messages can still leak information; check permissions before emitting data or triggering side effects.
10. **"A mockJwt() test proves production JWT configuration is valid."** mockJwt tests authorization logic; decoder, signature, and issuer require separate integration tests.

## 10. Cumulative Practice Exercise and Definition of Done

**Context:** build an API to read and cancel orders for two users, Alice and Bob, in different tenants. Predefined functional rules: reading orders requires SCOPE_orders:read; canceling orders requires SCOPE_orders:cancel; only the order owner or a tenant manager role may cancel, and only while the order remains in a cancelable status.

**Sequence of steps:**

1. Build a public /health endpoint and an /api/orders/{id} endpoint in WebFlux; verify requests/responses without security.
2. Add a SecurityWebFilterChain with deny-by-default; require authentication for the API; explain 401 on tokenless requests.
3. Configure a JWT Resource Server with a real test issuer; write tests for valid/invalid tokens and verify SCOPE_orders:read mapping.
4. Enforce GET permissions by route, then add read policy to the service with @PreAuthorize; explain why both layers are needed.
5. Constrain queries by trusted owner/tenant, build a scenario where Alice tries Bob's order ID; expect 404 or 403 per chosen policy.
6. Add order cancellation: check scope, owner/manager relationship, tenant, and status before updating; design the write operation so the status condition remains valid when saving.
7. Write a positive/negative test matrix across all boundaries. Prove users cannot read/cancel others' orders and no sensitive data leaks in responses.

**Definition of Done for this module:** learners can redraw the request path, distinguish 401/403/404, show where Authentication is created and where it is read from Reactor Context, explain the difference among route/method/object permissions, and provide tests for at least four cases: missing token, missing scope, wrong owner/tenant, and full valid permissions. They must be able to answer: **If Alice knows Bob's exact order ID, which layer stops Alice from accessing it and which test proves it?**

## 11. Quick Self-Check

- If GET /health is allowed while GET /api/orders/42 without a token gets 401, which rule is responsible for each outcome?
- Why can a valid Bearer token still receive 403 at a route? When might an owner check return 404?
- If the same service is called by both an HTTP controller and a message consumer, is relying solely on pathMatchers enough?
- Why does a JWT subject not automatically equal an internal user ID? Where should identity mapping be resolved?
- Why must tenant checks be enforced in data queries and updates, even when @PreAuthorize has already passed?
- What can mockJwt() test, and what can it **not** test?
- When moving from Servlet MVC to WebFlux, which security APIs and concepts must transition from ThreadLocal and Servlet filters to Reactive Context and WebFilters?

If you cannot explain one of the questions yet, return to the corresponding stage in Section 4 and add a small test before continuing.

## 12. Official References

- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): SecurityWebFilterChain, ServerHttpSecurity, and multiple chains.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): @EnableReactiveMethodSecurity, @PreAuthorize, and Reactor Context.
- [Spring Security — Reactive OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): JWT validation and issuer/JWK configuration.
- [Spring Security — Testing OAuth2 in WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): mockJwt() and testing permissions.
- [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/): Mono/Flux, operators, and Context.

**Connecting message across the lesson:** security does not stop at turning a Bearer token into an Authentication. The complete journey runs from **HTTP → authentication → functional endpoint permission → business operation permission → specific data permission → response containing only permitted data**.