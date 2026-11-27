# Rule Matching Order and Default Rules for Remaining Requests

In a **Spring Security OAuth 2.0/OIDC Resource Server** using Servlet, HTTP authorization configuration is typically declared with `HttpSecurity.authorizeHttpRequests(...)`. An API may have public endpoints, endpoints requiring only login, endpoints requiring specific scopes, and administrative endpoints. For these policies to work correctly, you must not only write `hasAuthority(...)` or `authenticated()` accurately, but also understand **which rule is evaluated first** and **how requests matching none of the specific rules are handled**.

Core rule:

> Within the rule list of `authorizeHttpRequests`, Spring Security evaluates `RequestMatcher`s in **the order declared**; **the first matching rule** determines the authorization policy for that request. Later rules are never used to "rescue" a denial decision made by an earlier rule.

Therefore, you typically place **specific rules first**, **broad rules later**, and a **default rule for remaining requests** at the end. For sensitive APIs, a safe strategy is `anyRequest().denyAll()` so that new endpoints do not automatically inherit an overly broad policy; in systems with different requirements, `anyRequest().authenticated()` can also be appropriate, provided its limits are clearly understood.

This lesson focuses on **HTTP Authorization** in the context of a Resource Server receiving Bearer JWT or opaque tokens. The examples use Spring Boot, Spring Security Servlet, and Java, with comparisons to WebFlux where useful. URIs, scopes, API names, and issuers are all illustrative.

## 1. Distinguishing Token Validation from HTTP Authorization Decisions

The client sends:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
~~~

In the Resource Server, Spring Security validates the access token and builds an authenticated `Authentication`. With a JWT, `JwtDecoder` verifies signature, issuer, timestamps, and audience per configuration, and `JwtAuthenticationConverter` typically maps the `scope` or `scp` claim into `GrantedAuthority` instances such as `SCOPE_orders.read`. With an opaque token, `OpaqueTokenIntrospector` validates via a trusted introspection endpoint and builds the principal/authorities.

Only after authentication succeeds does authorization evaluate **which request is being called** and **whether the matching rule is satisfied**.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Spring Security FilterChainProxy"]
    B --> C["Bearer token authentication (if present)"]
    C --> D["AuthorizationFilter"]
    D --> E["RequestMatcherDelegatingAuthorizationManager"]
    E --> F{"First matching rule"}
    F --> G["permitAll"]
    F --> H["authenticated"]
    F --> I["hasAuthority / hasRole"]
    F --> J["denyAll"]
    G --> K["Continue to application"]
    H --> L{"Condition satisfied?"}
    I --> L
    J --> M["Denied"]
    L -->|Yes| K
    L -->|No| M
~~~

OAuth 2.0/OIDC examples often mention **token scopes**, yet `authorizeHttpRequests` does not inherently know which scope each URL needs. The application itself must write the endpoint → rule mapping. For instance:

~~~text
GET  /api/orders/**  → SCOPE_orders.read
POST /api/orders     → SCOPE_orders.create
GET  /api/admin/**   → ROLE_ADMIN
GET  /health/public  → permitAll
Remaining requests   → denyAll or authenticated by design
~~~

**Successful authentication does not mean permission to call every endpoint.** A token with a valid signature and unexpired lifetime can still receive `403 Forbidden` if it lacks a scope. Conversely, `permitAll()` does not turn an invalid JWT into a valid one: if a client sends an invalid Bearer token to a public URL in a chain with Bearer authentication, the authentication filter may reject the request before `permitAll` is evaluated.

## 2. What Does "Matching Order" Really Mean?

`authorizeHttpRequests` builds an ordered set of mappings:

~~~text
RequestMatcher 1  → AuthorizationManager 1
RequestMatcher 2  → AuthorizationManager 2
RequestMatcher 3  → AuthorizationManager 3
...
RequestMatcher N  → AuthorizationManager N
~~~

When a request arrives:

1. Spring Security inspects the HTTP request details (method, path, and other attributes depending on the matcher).
2. It checks the first matcher.
3. If the matcher does not match, it moves on to the next matcher.
4. If the matcher matches, it uses **the associated authorization manager** to decide whether to allow or deny.
5. It does not continue checking subsequent matchers simply because the matched authorization manager returned a denial.

Example:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
)
~~~

A request `GET /api/admin/users` matches `/api/**` **before** `/api/admin/**`. Thus it is governed by `authenticated()`, **not** `hasRole("ADMIN")`. A regular user only needs to be authenticated to pass that HTTP rule, even though the developer intended to protect admin URLs with a role.

Rewriting the order:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
)
~~~

Now `/api/admin/users` hits the admin matcher first, so it requires `ROLE_ADMIN` per the default role prefix.

### 2.1. There Is No "Automatic Priority for Longer Patterns"

Do not assume Spring Security automatically prioritizes `/api/admin/**` over `/api/**` simply because it is more specific or longer. In the declarative `authorizeHttpRequests` model, **declaration order** is part of the policy.

| First matching matcher | Subsequent matcher | Actual outcome |
|---|---|---|
| `/api/** → authenticated` | `/api/admin/** → hasRole("ADMIN")` | The admin HTTP rule may never apply to admin URLs |
| `/api/admin/** → hasRole("ADMIN")` | `/api/** → authenticated` | Admin requires `ROLE_ADMIN`; other API URLs require authenticated |
| `/** → permitAll` | `/api/** → authenticated` | Requests may be permitted overly broadly |
| `/api/orders/** → hasAuthority("SCOPE_orders.read")` | `POST /api/orders → hasAuthority("SCOPE_orders.create")` | If POST is covered by the first matcher, it receives the wrong read rule |

The last row highlights another factor: a matcher **not restricted by HTTP method** usually applies to multiple methods. Getting the URL path right is not enough for a sound policy.

### 2.2. Matching Once Does Not Mean Allowing Once

If a request matches:

~~~java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
~~~

but the principal lacks `ROLE_ADMIN`, Spring Security **denies** it. It does not fall through to the later rule `.requestMatchers("/api/**").authenticated()` to try again. This property prevents "falling back to a more lenient rule," which is why ordering must be determined before implementation.

### 2.3. `RequestMatcher` Semantics Matter More Than String Shape

`requestMatchers(...)` has multiple overloads, and matchers can examine method, URL path, dispatcher type, or other conditions. Path-string semantics depend on the matcher type chosen/configured by Spring Security and the framework version, such as matchers integrated with Spring MVC versus specialized matchers.

Do not treat `requestMatchers("/api/**")` as running an arbitrary regex algorithm. For complex requirements, pick the right matcher implementation explicitly and verify paths with slashes, URI encoding, servlet paths, or proxy prefixes against your deployment architecture. Even so, **within the same rule list**, first-match-wins remains the design invariant to preserve.

## 3. Basic Example: Resource Server with Multiple Permission Levels

Suppose an order management API has:

| Endpoint | Desired access level |
|---|---|
| `GET /public/catalog` | Public |
| `GET /api/orders/**` | Bearer token with `orders.read` |
| `POST /api/orders` | Bearer token with `orders.create` |
| `PUT /api/orders/{id}` | Bearer token with `orders.update` |
| `DELETE /api/orders/{id}` | Bearer token with `orders.delete` |
| `/api/admin/**` | Admin role mapped reliably by the issuer/application |
| `/api/profile` | Authenticated principal |
| All other paths | Denied by the default `denyAll` policy |

### 3.1. Dependencies

Spring Boot example using Servlet/Spring MVC and JWT:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

### 3.2. Configuring the Trusted Issuer

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/company
~~~

The Issuer URI must come from the contract with the Authorization Server. The Resource Server should also verify the audience dedicated to the Orders API, such as `orders-api`, using the appropriate framework version property/validator. **Trusting the issuer alone does not guarantee the token was issued for this API.**

### 3.3. SecurityFilterChain with Explicit Rule Ordering

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class OrdersApiSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/catalog")
                    .permitAll()
                .requestMatchers("/api/admin/**")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .requestMatchers(HttpMethod.PUT, "/api/orders/*")
                    .hasAuthority("SCOPE_orders.update")
                .requestMatchers(HttpMethod.DELETE, "/api/orders/*")
                    .hasAuthority("SCOPE_orders.delete")
                .requestMatchers("/api/profile")
                    .authenticated()
                .anyRequest()
                    .denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

Here admin matchers come first, followed by API endpoints separated by **method**, then profile, and `anyRequest().denyAll()` at the end. If the application adds another endpoint, it is not accepted automatically until its authorization policy is declared.

**This is an example of security rules, not a complete runnable project**: controllers, services, audience validators, record ownership, and client-specific CSRF/session/CORS policies must be designed separately.

#### Caution When Using `/api/orders/*`

A single-asterisk pattern typically describes one path segment, whereas `/**` typically covers multiple segments. Exact matching details depend on the `RequestMatcher` type. If business logic allows editing only `/api/orders/{id}`, clarify the URL shape, methods, whether routes can have nested segments, and verify with HTTP tests. Do not use a broader `/**` just to "make it match" when the actual target is a single-segment ID.

### 3.4. Which Authorities Do Token Scopes Become?

A JWT issued by a trusted issuer with an illustrative payload:

~~~json
{
  "iss": "https://login.example.test/realms/company",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read orders.create",
  "exp": 1924992000
}
~~~

After validation, the common default converter maps:

~~~text
scope = orders.read orders.create
    ↓
GrantedAuthority("SCOPE_orders.read")
GrantedAuthority("SCOPE_orders.create")
~~~

Hence `GET /api/orders/42` passes the read rule, and `POST /api/orders` passes the create rule if all other conditions hold. This token **lacks** `SCOPE_orders.delete`, so the corresponding DELETE request is rejected at authorization.

The `scope` claim from a JWT is trustworthy **only after** the decoder verifies the signature and issuer/time/audience/profile conditions per the contract. With opaque tokens, authorities are constructed from trusted introspection results instead of a JWT decoder.

### 3.5. HTTP Rules Do Not Replace Per-Order Permissions

A principal holding `SCOPE_orders.read` is still not necessarily allowed to view **every** order. HTTP rules check the operation type; the service must also verify that the order belongs to the right user/tenant or is shared per policy.

~~~text
HTTP authorization:
    Has SCOPE_orders.read?
             ↓
Service authorization:
    Does the order belong to the permitted subject/tenant?
             ↓
Return business data
~~~

Never use `anyRequest().authenticated()` in place of record-level checks. The default rule is an HTTP-level "front door," not the entire application authorization model.

## 4. Default Rules for Remaining Requests

After specific matchers, an application typically declares `anyRequest()` as a final rule applying to unmatched requests within **the current security chain**. Choosing this rule expresses the API's **default security posture**.

| Final rule | Condition for remaining requests to proceed | Usage characteristics |
|---|---|---|
| `anyRequest().denyAll()` | No remaining requests are allowed by this rule | **Default deny / endpoint allowlist**; good for APIs requiring tight surface control |
| `anyRequest().authenticated()` | Validly authenticated principal | Blocks anonymous, but enforces no specific scope; assess carefully for sensitive endpoints |
| `anyRequest().permitAll()` | Permitted at the HTTP authorization layer | Suitable for chains dedicated strictly to public resources; very risky as a default for protected APIs |
| `anyRequest().hasAuthority("SCOPE_api.access")` | Principal holds one mandatory authority | Use when **all** remaining endpoints genuinely share the exact same permission |
| `anyRequest().hasRole("USER")` | Principal holds the role per default prefix | Suitable when policy requires that role for all remaining URLs; does not replace object-level checks |

### 4.1. `denyAll`: Prioritizing Zero Unexpected Access

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public/catalog").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders")
        .hasAuthority("SCOPE_orders.create")
    .anyRequest().denyAll()
)
~~~

Suppose next month a developer adds `GET /api/reports/export` without updating the security rules. If the endpoint goes through this chain, it hits **`denyAll`**, instead of accidentally becoming callable by any client with an arbitrary access token. This is a practical benefit of a **fail-closed** policy.

Key point to grasp: `denyAll()` only rejects requests **that reach the final rule within the selected chain**. It does not cover requests routed to another `SecurityFilterChain` or **matching no chain at all**. Multi-chain behavior is covered separately below.

### 4.2. `authenticated`: Requires Authentication, Yet Access May Still Be Too Broad

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public/catalog").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
)
~~~

With `anyRequest().authenticated()`, URLs such as `/api/profile`, `/api/preferences`, or a new endpoint `/api/payments/refund` all require only authentication unless a specific rule precedes them. For sensitive data and state-changing operations, this can constitute **missing authorization**, because many valid tokens are not meant to perform those actions.

`authenticated()` is useful when the API or current zone has a uniform policy that "every authenticated principal is allowed," such as a personal info page always scoped to **the caller themselves** by the service. Even then, data-scoping design and reviews for new endpoints are essential.

### 4.3. `permitAll`: Does Not Mean All Other Filters Are Bypassed

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated()
)
~~~

`permitAll()` **requires no authority to enter the endpoint**, yet the request still passes through the selected security filter chain. Mechanisms such as CORS, security headers, the firewall, Bearer token authentication, or custom filters may still process the request.

For example, `GET /public/catalog` without a Bearer token may be permitted. However, a request to that same URL carrying `Authorization: Bearer invalid-token` may be **rejected by the Resource Server at authentication before `permitAll` is evaluated**. Never assume "since it is a public endpoint, bad tokens will surely be ignored."

If a group of public paths must completely bypass Bearer authentication, you can design a **dedicated security chain** or select appropriate filters. That must be explicitly designed and tested, not assumed from `permitAll()`.

### 4.4. Why Must `anyRequest` Be Last?

`anyRequest()` represents a catch-all matcher for remaining requests. Once used, there is no logical place for rules below it. In modern Spring Security builders, declaring additional matchers after `anyRequest()` can be rejected at configuration time because `anyRequest` already defines the catch-all.

**Do not write**:

~~~java
// ANTI-PATTERN — never put anyRequest first and add rules afterward.
.authorizeHttpRequests(auth -> auth
    .anyRequest().authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
)
~~~

Instead of hoping later matchers still apply, write all specific rules **first** and put `anyRequest` at the very end.

### 4.5. Is Declaring `anyRequest` Mandatory?

Avoid relying on "implicit default" behavior when no catch-all rule is present, because outcomes can be hard to reason about across combinations of framework versions, security chains, and DSLs. **Explicitly declare** the fallback policy using `anyRequest().denyAll()` or `anyRequest().authenticated()` per contract.

What matters is not a specific version number, but that **anyone reading the configuration immediately sees what happens to endpoints without a dedicated rule**. A security policy should never depend on developers memorizing an implicit default.

## 5. Rule Ordering by HTTP Method

A single path can support multiple HTTP methods, and each method carries different consequences:

~~~text
GET    /api/orders/42  → read
PUT    /api/orders/42  → update
DELETE /api/orders/42  → delete
~~~

If you write:

~~~java
.requestMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.DELETE, "/api/orders/**")
    .hasAuthority("SCOPE_orders.delete")
~~~

then a DELETE request can match the first `/api/orders/**` rule and **require only read permission**. Never place an "all methods" matcher for the same resource ahead of method-specific rules.

### 5.1. Place Sensitive Methods First

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.DELETE, "/api/orders/*")
        .hasAuthority("SCOPE_orders.delete")
    .requestMatchers(HttpMethod.PUT, "/api/orders/*")
        .hasAuthority("SCOPE_orders.update")
    .requestMatchers(HttpMethod.POST, "/api/orders")
        .hasAuthority("SCOPE_orders.create")
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().denyAll()
)
~~~

When every relevant rule specifies an explicit HTTP method, accidentally creating an "all methods" rule becomes much less likely. If the application also adds `PATCH`, add a dedicated rule or let the default catch-all deny it.

### 5.2. Safe Default for Unknown Methods

Suppose a controller adds `PATCH /api/orders/42` without adding a policy yet. With a `denyAll` catch-all, the request is blocked. With an `authenticated` catch-all, any authenticated principal can pass HTTP authorization and rely on the controller/service to check permissions on its own.

For write/delete endpoints, default deny reduces the risk of "a new path passing auth without the right scope." Still, the service must check owner/tenant, and HTTP method security does not replace CSRF defenses for applications using cookie-based authentication.

### 5.3. HTTP `HEAD` and `OPTIONS`

Method behavior depends on controller mappings, the servlet stack, and matchers. `HEAD` may be handled closely to `GET` in some MVC configurations, yet **never assume a GET rule always covers HEAD the way you expect**. If metadata/resources have security requirements, define an explicit HEAD policy accordingly.

`OPTIONS` may be:

- **CORS preflight** from a browser, typically carrying no Bearer token.
- An ordinary OPTIONS request to an endpoint, not necessarily a preflight.

These two cases are not identical. Never blindly permit all `OPTIONS /**` without considering purpose and CORS configuration. The CORS section below covers standard handling.

## 6. An Authorization Model by Scope and Sensitivity

Rather than just appending `denyAll` at the end and assuming every URL is safe, classify HTTP zones.

| Zone | Example | Rule to consider starting with |
|---|---|---|
| Public | `/public/catalog` | `permitAll`, permitting only needed methods/paths |
| Read API | `GET /api/orders/**` | `SCOPE_orders.read` |
| Write API | `POST /api/orders` | `SCOPE_orders.create` |
| Modify API | `PUT/PATCH /api/orders/{id}` | `SCOPE_orders.update` |
| Delete API | `DELETE /api/orders/{id}` | `SCOPE_orders.delete` |
| Admin | `/api/admin/**` | Admin role or dedicated permission mapped from a trusted source |
| Authenticated user info | `/api/profile` | `authenticated` + return only the caller's identity |
| Internal management | `/actuator/**` or internal endpoints | Dedicated chain/conditions, restricted network, permissions, and visibility |
| Unknown/new endpoints | Unclassified | `denyAll` per default-deny choice |

This classification speeds up code reviews: **which group does the new endpoint belong to, and which rule does it need?** Never "temporarily open" it with `permitAll` or `authenticated` and forget to tighten it later.

### 6.1. Do Not Equate `hasRole` with OAuth 2.0 Scopes

In Spring Security, `hasRole("ADMIN")` normally requires authority `ROLE_ADMIN` under the default role prefix. The default JWT Resource Server maps `scope="orders.read"` to `SCOPE_orders.read`. These are two different namespaces:

~~~text
scope = orders.admin      → SCOPE_orders.admin
role  = ADMIN             → ROLE_ADMIN (if a trusted custom mapping exists)
~~~

If the issuer supplies a `roles` claim without a configured converter in the app, `hasRole("ADMIN")` may always deny because `ROLE_ADMIN` is never created. Never "fix" this by removing `hasRole` or switching admin endpoints to `authenticated`; clarify the trusted authority source and mapping instead.

### 6.2. Shared Rules Using `hasAnyAuthority`

When aligned with the contract, an endpoint can accept any one of several scopes:

~~~java
.requestMatchers(HttpMethod.GET, "/api/reports/**")
    .hasAnyAuthority("SCOPE_reports.read", "SCOPE_reports.admin")
~~~

This expresses **OR across authorities** for one matcher. Do not overuse it when policy requires multiple conditions **simultaneously**, such as having the right scope **and** belonging to an allowed tenant. For complex policies, consider a custom `AuthorizationManager` or method/domain authorization.

### 6.3. Keep Service-Level Authorization

Example:

~~~text
GET /api/orders/42
JWT principal sub = user-123
authorities = [SCOPE_orders.read]

Order 42:
  owner = user-456
~~~

The HTTP rule may pass, yet **that does not mean the request may return the order's contents**. If the service fails to verify owner/tenant, the API risks Broken Object Level Authorization. A catch-all rule cannot fix record-level data authorization bugs.

## 7. How Do `permitAll`, `anonymous`, and `authenticated` Differ?

Common Spring Security rules:

| Rule | Intent |
|---|---|
| `permitAll()` | Permits the request at the authorization layer regardless of whether the principal is authenticated |
| `denyAll()` | Denies the request |
| `authenticated()` | Requires an authenticated principal, not merely anonymous |
| `anonymous()` | Intended for requests treated as anonymous |
| `fullyAuthenticated()` | Requires full authentication per the trust resolver; meaningful with remember-me |
| `hasAuthority("...")` | Requires the exact declared authority |
| `hasRole("...")` | Checks a role using the role prefix convention |

In Bearer JWT APIs without remember-me, `fullyAuthenticated` may behave similarly to `authenticated` for many requests, yet the two rules should not be treated as identical across all Spring Security architectures.

A browser login page might use `anonymous()` by design, whereas a pure Bearer Resource Server API rarely needs it. When login sessions and Bearer tokens coexist in the same application, define distinct request matchers, authentication mechanisms, and policies.

### 7.1. Public Does Not Mean Ignoring Invalid Tokens

~~~text
GET /public/catalog

No Authorization header:
    → permitAll can allow

Authorization: Bearer invalid-token:
    → BearerTokenAuthenticationFilter can reject
       before AuthorizationFilter applies permitAll
~~~

Do not write clients that blindly send an empty/expired Bearer token to every public endpoint expecting the server to ignore it. On the server side, if you want public endpoints completely decoupled from Bearer authentication, design an appropriate filter chain.

### 7.2. 401 and 403 Errors When Rules Fail

| Scenario | Typical result |
|---|---|
| Request to an `authenticated()` endpoint without a token | 401 |
| Request with a Bearer JWT with bad signature/expired | 401 |
| Valid JWT missing `SCOPE_orders.read` | 403 |
| Valid JWT missing `ROLE_ADMIN` | 403 |
| Request hitting `denyAll` from an authenticated principal | Usually 403 |
| Request hitting `denyAll` from anonymous | May trigger the 401 entry point depending on handler setup |
| Request hitting `permitAll` without a token | Usually permitted to proceed |
| Request hitting `permitAll` carrying an invalid Bearer token | May return 401 at the authentication filter |

These are **common** statuses, not immutable guarantees: `AuthenticationEntryPoint`, `AccessDeniedHandler`, security chains, and exception handling can produce different response details.

## 8. Two Distinct Ordering Layers: Selecting `SecurityFilterChain` vs. Selecting a Rule

In a Servlet application with multiple `SecurityFilterChain`s, **there is not just a single matcher list**. Distinguish two layers:

1. **Chain selection layer**: `FilterChainProxy` inspects `SecurityFilterChain`s in order and picks **the first chain matching the request**.
2. **HTTP authorization layer**: inside the chosen chain, `AuthorizationFilter` uses the `authorizeHttpRequests` matchers and again picks **the first rule matching the request**.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["FilterChainProxy"]
    B --> C{"Which SecurityFilterChain matches first?"}
    C -->|"Chain @Order(1)"| D["Chain A: /api/**"]
    C -->|"Chain @Order(2)"| E["Chain B: remaining paths"]
    C -->|"No chain matches"| X["Not protected by any Spring Security chain"]
    D --> F["authorizeHttpRequests in A"]
    E --> G["authorizeHttpRequests in B"]
    F --> H["Rule A1 → A2 → ... → anyRequest"]
    G --> I["Rule B1 → B2 → ... → anyRequest"]
    H --> J["Authorization decision"]
    I --> J
~~~

**An `anyRequest().denyAll()` in Chain A does not apply to requests never selected by Chain A.** This is especially important if the API has one chain for `/api/**`, another for form login or public endpoints, and management endpoints.

### 8.1. `securityMatcher` Defines Chain Scope

Example:

~~~java
http.securityMatcher("/api/**");
~~~

Meaning: the `SecurityFilterChain` configured via this `http` can protect only requests matching `/api/**`. If a request is `GET /docs/index.html`, this chain is not selected simply because `anyRequest()` appears inside it.

### 8.2. `requestMatchers` Inside `authorizeHttpRequests` Defines Rules

Example:

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/orders/**")
            .hasAuthority("SCOPE_orders.read")
        .anyRequest().denyAll()
    );
~~~

Here:

- `securityMatcher("/api/**")` is **the applicability scope of the chain**.
- `requestMatchers(GET, "/api/orders/**")` is **the scope of one rule** inside the chain.
- `anyRequest().denyAll()` handles remaining requests **within the API chain**.
- `/docs/index.html` does not belong to this chain; it must be protected by another chain or governed by an intentional policy.

### 8.3. `@Order` Defines Chain Selection Order

Two-chain pattern: an API chain first and a fallback chain second.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class MultiChainSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/catalog")
                    .permitAll()
                .anyRequest().denyAll()
            )
            .build();
    }
}
~~~

This is an **alternative configuration**; do not paste it into the same application alongside the global `SecurityFilterChain` bean from earlier. Chain 1 uses Bearer JWT authentication and protects `/api/**`. Chain 2 declares no `securityMatcher`, so it acts as a **fallback** for requests not matching the earlier chain. Chain 2's explicit policy allows the public catalog and denies other URLs.

**If `/api/profile` also needs to work**, declare its rule and endpoint inside the API chain before `anyRequest().denyAll()`. If there is an `/actuator/health` endpoint or documentation pages, design and declare policies in the appropriate chain. The example intentionally avoids opening all of actuator and docs automatically.

### 8.4. Chain Ordering Is Also "First Match Wins"

Wrong:

~~~java
@Order(1)
SecurityFilterChain broadChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .build();
}
~~~

If this chain has no `securityMatcher` restriction and precedes an API chain configured with a lower-priority order, it can **capture all requests first**, preventing the later API chain from ever being chosen.

There is no "try the second chain if the first chain denies." Just like intra-chain rules, **the first matching chain is the one used**. Only if the first chain does not match is the next chain considered.

### 8.5. What If No Chain Matches?

This is a greater risk than picking an overly broad rule. Suppose there is only one chain:

~~~java
@Bean
SecurityFilterChain onlyApiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
        .build();
}
~~~

A request `GET /internal/reports` does not match `/api/**`. If **no other `SecurityFilterChain` exists**, it may pass through the application without being protected by this chain's Spring Security filters. Whether the path resolves depends on controllers/servlets, yet **you must never treat `denyAll` inside the API chain as global protection**.

The practical solution is defining a **fallback chain** matching remaining requests with `denyAll` or an explicit policy. Furthermore, endpoints on a different management port/servlet context may have their own protection mechanism; evaluate the actual deployment scope.

## 9. Public Path Rules and API Chains: Avoiding Overexposure

When a project mixes public resources with a bearer API, there are two common ways to organize it.

### 9.1. One Chain, One Rule List

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public/catalog").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
)
~~~

Pros: short and easy to read for small applications. Cons: `/api/**.authenticated()` is a **broad** policy, so scope-requiring endpoints must be placed **before** it, and new endpoints must not be opened unintentionally.

### 9.2. Multiple Chains by Zone

~~~text
@Order(1) /public/**   → public chain with appropriate security headers/CORS
@Order(2) /api/**      → OAuth 2.0 Resource Server chain
@Order(3) fallback     → denyAll
~~~

Pros: separates authentication mechanisms, CORS, and policies more cleanly. Cons: requires controlling **chain ordering**, matcher scope, full coverage, and filter configuration.

Example of a public-only chain:

~~~java
@Bean
@Order(1)
SecurityFilterChain publicChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/public/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/public/catalog")
                .permitAll()
            .anyRequest().denyAll()
        )
        .build();
}
~~~

This chain does not enable `oauth2ResourceServer()`, so for its public routes, Bearer authentication is not triggered merely because a client sends a Bearer header. Even so, the chain's other security filters can still run. When using multiple chains, also build the API chain and fallback rather than copying `publicChain` by itself.

### 9.3. Do Not Casually Use `web.ignoring()` Instead of `permitAll()`

Some legacy apps configure security ignoring for static resources. When using `WebSecurityCustomizer.ignoring()`, requests may **bypass the Spring Security filter chain altogether**, unlike `permitAll()`, which keeps the chain's filters active.

For public endpoints needing protective headers, CORS, security context, or auditing at the Spring Security layer, designing an appropriate chain and using `permitAll()` is usually preferable to skipping all filters. Only use ignoring when you clearly understand the consequences and control routes precisely; never ignore `/api/**` as a quick fix for a 401 error.

## 10. CORS Preflight, OPTIONS, and Processing Order

Browsers calling a cross-origin API typically send a **CORS preflight** before sending a request carrying an `Authorization` header:

~~~http
OPTIONS /api/orders/42 HTTP/1.1
Origin: https://shop.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Preflight **is not the same as the actual GET request** and typically lacks a Bearer token. If a security filter requires a JWT for the preflight before CORS is handled, the browser may report a CORS error even though the user holds a valid token.

### 10.1. Prioritize Configuring CORS at the Right Boundary

In Spring Security:

~~~java
import static org.springframework.security.config.Customizer.withDefaults;

http.cors(withDefaults());
~~~

Appropriate CORS configuration must be provided via Spring MVC or a `CorsConfigurationSource` bean that Spring Security can consume. Example:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://shop.example.test"));
    config.setAllowedMethods(
        List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
    config.setAllowedHeaders(List.of("Authorization", "Content-Type"));

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
~~~

This is an illustrative CORS configuration for an API serving a browser client from a known origin. When using cookies/cross-origin credentials, `allowCredentials` and `allowedOrigins` policies differ and must never carelessly combine wildcard origins. CORS **is not** a Bearer token validation mechanism; JWTs still must be verified by the Resource Server on actual requests.

### 10.2. Should `OPTIONS /** → permitAll` Be Used?

Some examples open all OPTIONS:

~~~java
.requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
~~~

This is an HTTP authorization policy and **does not fully configure CORS by itself**. It can allow non-preflight OPTIONS requests and still fail to emit the `Access-Control-Allow-*` headers browsers expect.

Prefer `http.cors(...)` and configuring allowed origins/methods/headers, ensuring preflight is handled before authentication when needed. If your organization still uses an OPTIONS rule for architectural compatibility, scope and test it as its own rule; never use it to disable auth for real methods.

### 10.3. CORS Does Not Alter Rule Ordering Principles

After preflight succeeds, the actual request such as `GET /api/orders/42` still must pass JWT authentication and the matcher requiring `SCOPE_orders.read`. Never treat "Origin allowed" as permission to call the API: a request from a valid origin with a bad token or missing scope must still be rejected.

## 11. Dispatcher Types: REQUEST, FORWARD, ERROR

Servlets have multiple dispatch types beyond the initial request, such as `FORWARD` and `ERROR`. In some applications, Spring Security also runs authorization on subsequent dispatches; behavior depends on dispatcher-type configuration and security filter registration.

For instance, an application wanting to allow internal dispatches to an error page:

~~~java
import jakarta.servlet.DispatcherType;

http.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().denyAll()
);
~~~

Meaning: an `ERROR` rule placed before URL matchers can permit error dispatches to reach error handling, while the original HTTP request still undergoes authentication/authorization. This **does not mean every app should open ERROR/FORWARD unconditionally**.

### 11.1. Why Be Careful with `FORWARD`?

If a public endpoint can forward to a sensitive controller/path, an overly broad `dispatcherTypeMatchers(FORWARD).permitAll()` rule can bypass controls at the subsequent dispatch step. Evaluate who can trigger forwards, target paths, and service authorization.

Add dispatcher-type rules only when there is a clear need and you understand the impact. Place them before other matchers if intended to take precedence, but never turn them into a "shortcut" bypassing business authorization.

### 11.2. Error URLs and Status Codes

If `/error` or an error-display endpoint needs to handle anonymous requests, configure the corresponding route/execution rule. Never expose stack traces, JWT claims, Authorization headers, or internal exceptions in the body just because the error path was allowed.

## 12. URL Matching Patterns and Easily Missed Cases

An HTTP rule is only safe when the matcher recognizes the exact path the application actually processes. In systems with gateways, servlet paths, API versioning, or encoded URLs, configure matchers according to your framework setup.

### 12.1. Trailing Slashes and Nested Paths

These paths should not always be assumed equivalent:

~~~text
/api/orders
/api/orders/
/api/orders/42
/api/orders/42/items
~~~

Depending on the matcher and MVC configuration, trailing slashes may be handled differently. Do not assume `/api/orders/*` covers all nested endpoints or `/api/orders/**` covers only a single ID.

If write/delete endpoints are allowed at `/api/orders/{id}`, ensure the rule's scope matches. Using a `denyAll` catch-all reduces fallout when a new path appears outside designed rules.

### 12.2. Context Path, Servlet Path, and Reverse Proxy

Suppose the client calls:

~~~text
https://gateway.example.test/shop/api/orders/42
~~~

The gateway might strip the `/shop` prefix before forwarding the request to the application, or the application might set `server.servlet.context-path`. Matchers in Spring Security apply to the request entering the servlet container per the chosen matcher's semantics. Therefore **do not copy the gateway's public path verbatim into matchers without verifying the path the app actually sees**.

With multiple servlet mappings or complex servlet paths, use framework-supported matcher APIs and configure base paths/servlet paths explicitly; do not just append `/**` to dodge 404/403 errors.

### 12.3. Encoded Paths and the HTTP Firewall

Forms such as encoded slashes, dots, semicolon/matrix parameters, or path traversal must be handled consistently across gateway, servlet container, and Spring Security. Spring Security versions provide an HTTP firewall mechanism, yet you should never loosen the firewall carelessly just to make a matcher "match." Normalization mismatches between proxy and app can create paths that bypass policies if left unchecked.

### 12.4. HTTP Methods Must Be Evaluated Alongside Paths

A method-unrestricted `/api/orders/**` matcher can apply to GET, POST, PUT, PATCH, DELETE, and OPTIONS. If the app needs a **read-only** branch, write method-specific rules or policies denying the remaining methods.

### 12.5. API Versioning

~~~text
/api/v1/orders/**
/api/v2/orders/**
~~~

A rule for `/api/v1/**` does not automatically apply to `/api/v2/**` if the matcher does not match. With default deny, a new v2 API will be blocked until its policy is added. This is desirable behavior when an organization reviews security policy for each API version.

## 13. Verifying Rule Ordering with Scenario Tables

Suppose an API has this policy:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public/catalog").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders")
        .hasAuthority("SCOPE_orders.create")
    .requestMatchers("/api/profile").authenticated()
    .anyRequest().denyAll()
)
~~~

### 13.1. Rule Selection Matrix

| Request | First matching matcher | Applied policy |
|---|---|---|
| `GET /public/catalog` | GET `/public/catalog` | `permitAll` |
| `POST /public/catalog` | `anyRequest` | `denyAll` |
| `GET /api/admin/users` | `/api/admin/**` | `hasRole("ADMIN")` |
| `POST /api/admin/users` | `/api/admin/**` | `hasRole("ADMIN")` |
| `GET /api/orders/42` | GET `/api/orders/**` | `hasAuthority("SCOPE_orders.read")` |
| `POST /api/orders` | POST `/api/orders` | `hasAuthority("SCOPE_orders.create")` |
| `DELETE /api/orders/42` | `anyRequest` | `denyAll` (no dedicated DELETE rule in this sample) |
| `GET /api/profile` | `/api/profile` | `authenticated` |
| `GET /api/reports/export` | `anyRequest` | `denyAll` |
| `GET /unknown` | `anyRequest` | `denyAll` |

When a request matches no specific rule, `anyRequest` guarantees an explicit policy within the chain. **This is only the matcher table**, not yet the HTTP status table: requests reaching `hasRole("ADMIN")` still require the principal to hold the role and may face additional business policies.

### 13.2. Token and Authorization Matrix

Assume the JWT has passed signature, issuer, audience, and expiry validation:

| Request | Authenticated authorities | Outcome at HTTP authorization |
|---|---|---|
| `GET /public/catalog` | No token | Permitted by public rule |
| `GET /api/orders/42` | `SCOPE_orders.read` | Permitted at HTTP layer |
| `GET /api/orders/42` | `SCOPE_orders.create` | Denied due to missing read permission |
| `POST /api/orders` | `SCOPE_orders.create` | Permitted at HTTP layer |
| `POST /api/orders` | `SCOPE_orders.read` | Denied due to missing create permission |
| `GET /api/admin/users` | `ROLE_ADMIN` | Permitted at HTTP layer |
| `GET /api/admin/users` | `SCOPE_orders.read` | Denied due to missing `ROLE_ADMIN` |
| `GET /api/profile` | Authenticated, empty authorities | Permitted at HTTP layer per `authenticated` |
| `GET /api/reports/export` | `ROLE_ADMIN` and all other scopes | Denied by `denyAll` catch-all |

The last row is worth noting: **`denyAll` still denies admins**. It expresses the decision to block any unclassified request, not merely "block anonymous."

## 14. Writing HTTP Tests to Catch Ordering Mistakes

With Spring Security Test, you can use `MockMvc` and the `jwt()` request post processor to verify **HTTP authorization rules** without needing a real token from an IdP.

~~~gradle
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Assuming the project already has controllers for the tested URLs and the security chain from section 13, here is an example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void readRequiresReadScope() throws Exception {
        mvc.perform(
                get("/api/orders/42")
                    .with(jwt().authorities(
                        new SimpleGrantedAuthority("SCOPE_orders.read")
                    ))
            )
            .andExpect(status().isOk());
    }

    @Test
    void readScopeDoesNotGrantAdminRoute() throws Exception {
        mvc.perform(
                get("/api/admin/users")
                    .with(jwt().authorities(
                        new SimpleGrantedAuthority("SCOPE_orders.read")
                    ))
            )
            .andExpect(status().isForbidden());
    }

    @Test
    void newEndpointIsDeniedEvenWithAuthenticatedJwt() throws Exception {
        mvc.perform(
                get("/api/reports/export")
                    .with(jwt().authorities(
                        new SimpleGrantedAuthority("ROLE_ADMIN")
                    ))
            )
            .andExpect(status().isForbidden());
    }
}
~~~

**Notes on the test example**:

- This is a template for testing **HTTP authorization** and assumes the controllers/services for successful paths work, e.g., `GET /api/orders/42` returns HTTP 200 when permitted. If the controller does not exist yet, the success response might be 404 instead of 200.
- `jwt()` from `spring-security-test` simulates an authenticated principal with the selected authorities. It **does not verify JWT signatures, JWK Sets, issuers, audiences, or expiry** like a real Bearer token request.
- Separate integration tests must send **real signed test JWTs** via `Authorization: Bearer` with a trusted decoder/JWK configuration to verify the authentication layer.
- When using opaque tokens, use the corresponding helpers/mocks to verify HTTP rules, while testing introspection integration separately.

### 14.1. Specifically Testing Broad-Rule-First Bugs

Suppose someone accidentally writes:

~~~java
.requestMatchers("/api/**").authenticated()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
~~~

The `readScopeDoesNotGrantAdminRoute` test will catch the issue if an HTTP request to admin carrying a JWT with `SCOPE_orders.read` but no `ROLE_ADMIN` passes HTTP authorization. The fix is **moving the admin matcher first** or redesigning the rules, not relaxing the test to accept weaker behavior.

### 14.2. Testing Methods, Not Just Paths

A passing GET test does not prove DELETE on the same URL is blocked properly:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;

@Test
void deleteIsDeniedWithoutDeletePolicy() throws Exception {
    mvc.perform(
            delete("/api/orders/42")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read")
                ))
        )
        .andExpect(status().isForbidden());
}
~~~

The illustrative test assumes **a Bearer-token Resource Server configuration where a separate CSRF layer does not return 403 prior to HTTP authorization**. For apps using cookies/sessions and CSRF, state-changing test requests may require a valid CSRF token to distinguish CSRF errors from authority errors. Even though both yield 403, the test intent differs; do not mistake a CSRF 403 for proof that DELETE permissions are configured properly.

### 14.3. Testing Paths Outside Chain Scope

With multiple `SecurityFilterChain`s, test not only `/api/**` but also:

~~~text
/public/catalog
/docs/index.html
/actuator/health
/internal/reports
/api/v2/orders/42
~~~

The goal is verifying **which chain is selected** and **which rule inside that chain applies**. A passing `/api/orders` test does not prove `/internal/reports` is protected by Spring Security.

### 14.4. Essential Test Cases

| Scenario | Objective |
|---|---|
| Anonymous calls public URL | `permitAll` has the right scope |
| Anonymous calls protected endpoint | Authentication is required |
| Authenticated yet missing authority | `hasAuthority` genuinely denies |
| JWT has the right authority | Matching rule lets it proceed |
| Non-admin calls admin URL | Admin matcher precedes broad matchers |
| GET with read scope, DELETE with read scope | Method rules are not swallowed by a generic rule |
| New URL without a specific rule | `denyAll` catch-all works |
| URL outside API chain's `securityMatcher` | Fallback chain protects the request |
| CORS preflight from an allowed origin | CORS succeeds without weakening real GET/POST security |
| Encoded/trailing-slash paths | No unexpected paths bypass matchers |
| ERROR/FORWARD dispatches if used | Dispatcher policy creates no bypass path |

## 15. What Extra Decisions Are Needed When Using `anyRequest().authenticated()`?

`anyRequest().authenticated()` is not wrong in every system. It fits when you **intentionally give all unclassified endpoints in that chain a shared "authentication required" policy**. Yet it requires supporting conditions.

### 15.1. APIs Reading Only the Caller's Own Data

For example, `GET /api/me` or `GET /api/preferences` returns data only for the current principal. `authenticated()` can suffice at the HTTP layer **if**:

1. The service never accepts an arbitrary user ID and returns someone else's data.
2. Subject/issuer/tenant are used consistently.
3. Responses contain no sensitive data outside the contract.
4. Mutation endpoints have dedicated rules.
5. Every new endpoint undergoes business authorization review.

Thus, `authenticated()` is a necessary condition at the HTTP layer, while data permissions must be enforced by service design.

### 15.2. Multi-Scope APIs

In the Orders API, an `orders.read` token and an `orders.create` token have different capabilities. If an `authenticated` catch-all applies to unclassified write endpoints, a client holding only `orders.read` can pass the write endpoint's HTTP rule. Policies should therefore separate sensitive methods/routes explicitly or pick `denyAll` for unknown endpoints.

### 15.3. Multi-Tenant APIs

`authenticated()` only confirms the request carries a valid principal per the authentication mechanism. It **does not inherently know which tenant may access which resources**. A token may belong to tenant A while the request references tenant B's data. Enforce tenant binding during token validation if required by the contract, and in domain authorization when accessing records.

### 15.4. APIs Accepting Tokens from Multiple Issuers

When an API trusts multiple issuers, the same authority string like `SCOPE_reports.read` can carry different meanings across issuers. Manage the trusted issuer allowlist, audiences, token profiles, and per-issuer authority mappings; do not let `authenticated()` open every endpoint simply because one issuer can mint access tokens for the system.

## 16. Common Mistakes When Configuring Ordering

### 16.1. Placing a Broad Matcher Before an Admin Matcher

~~~java
// ANTI-PATTERN:
.requestMatchers("/api/**").authenticated()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
~~~

Admin URLs are matched first by the broad matcher, leaving the later role rule unused. Fix: place the admin matcher first.

### 16.2. Placing GET/POST/DELETE Under a Method-Unrestricted Matcher

~~~java
// ANTI-PATTERN:
.requestMatchers("/api/orders/**").hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.DELETE, "/api/orders/**")
    .hasAuthority("SCOPE_orders.delete")
~~~

DELETE can match the read rule. Fix: separate methods clearly, put narrow rules first, and keep a deny fallback.

### 16.3. Setting `permitAll` on `/**`

~~~java
// ANTI-PATTERN:
.requestMatchers("/**").permitAll()
.requestMatchers("/api/**").authenticated()
~~~

The overly broad matcher sends API requests into the public policy, skipping the protection rules below.

### 16.4. Putting `anyRequest` First and Declaring Rules Afterward

~~~java
// ANTI-PATTERN:
.anyRequest().authenticated()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
~~~

This is not a "default first, exceptions later" structure. Builders may reject the configuration; conceptually, the catch-all already captures every request.

### 16.5. Having `denyAll` in the API Chain While Forgetting a Fallback Chain

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .anyRequest().denyAll());
~~~

This rule does not apply to `/internal/**` if requests do not enter the API chain. Define a policy for requests outside the chain's scope.

### 16.6. Overly Broad Public Matchers

~~~java
// ANTI-PATTERN if only health should be public:
.requestMatchers("/actuator/**").permitAll()
~~~

The pattern can open far more management endpoints than intended, including ones that should never be public. Use exact URL/endpoint matchers, configure management exposure, and enforce network controls per policy.

### 16.7. Using `hasRole("ADMIN")` When the JWT Only Has `SCOPE_admin`

`hasRole("ADMIN")` usually requires `ROLE_ADMIN`; JWT scopes map to `SCOPE_admin` by default. If you want roles, configure a converter mapping from a trusted source, or choose a specific scope authority per the contract.

### 16.8. Using Only `authenticated` While Forgetting Object-Level Authorization

A valid token does not grant permission to view arbitrary orders. HTTP authorization must be paired with owner, tenant, and domain policy checks.

### 16.9. Opening All OPTIONS to Fix CORS Errors

`OPTIONS /** → permitAll` neither generates CORS headers nor replaces allowed origin/method/header configuration. Handle CORS preflight at the proper layer while keeping auth on real requests.

### 16.10. Disabling CSRF Regardless of Application Type

Bearer tokens are typically sent deliberately via the Authorization header; however, applications also using cookies/sessions carry distinct CSRF risks. Do not disable CSRF just to make testing POST/DELETE easier or merely because an OAuth Resource Server configuration is present.

### 16.11. Changing Servlet Context Path or Gateway Prefix While Forgetting Matchers

Routes exposed by a gateway do not always equal paths at the servlet. Verify the actual request path seen by matchers; do not broaden `/**` just to stop endpoints from returning 403.

### 16.12. Relying on 401/403 Alone to Conclude Matchers Are Correct

A 403 can result from CSRF, domain authorization, missing scopes, or `denyAll`. A 401 can result from an invalid Bearer token before rules are even reached. To understand execution flow, isolate authentication, matching, and authorization using dedicated tests rather than inferring the entire policy from a single status code.

## 17. Comparison with Spring WebFlux

In WebFlux, applications use `ServerHttpSecurity` and `SecurityWebFilterChain` instead of `HttpSecurity` and `SecurityFilterChain`. The authorization API is typically `authorizeExchange(...)`, using `pathMatchers(...)` and `anyExchange()`. **The ordering concept remains identical: matchers are evaluated in declaration order and the first matching rule applies.**

### 17.1. Reactive Resource Server Example

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ReactiveOrdersSecurity {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/public/catalog")
                    .permitAll()
                .pathMatchers("/api/admin/**")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

Requests with matching scopes still must pass JWT verification via `ReactiveJwtDecoder`. For opaque tokens, use the corresponding reactive introspection configuration. Never use a Servlet `SecurityFilterChain` bean in place of `SecurityWebFilterChain` in WebFlux.

### 17.2. Conceptual API Comparison

| Intent | Servlet | WebFlux |
|---|---|---|
| Configure security chain | `HttpSecurity` | `ServerHttpSecurity` |
| Builder result | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Authorize requests | `authorizeHttpRequests` | `authorizeExchange` |
| Match path/method | `requestMatchers(...)` | `pathMatchers(...)` |
| Catch-all rule | `anyRequest()` | `anyExchange()` |
| Allow anonymous and authenticated | `permitAll()` | `permitAll()` |
| Require authentication | `authenticated()` | `authenticated()` |
| Require authority | `hasAuthority("SCOPE_...")` | `hasAuthority("SCOPE_...")` |
| Deny remaining requests | `anyRequest().denyAll()` | `anyExchange().denyAll()` |

WebFlux can also have **multiple `SecurityWebFilterChain`s**, with ordering and matchers for chain selection. Place sensitive API chains before broad chains and include an explicit fallback. Do not let an overly broad chain matcher capture every request ahead of a narrow chain.

### 17.3. Reactive CORS and Preflight

In WebFlux, CORS must also be handled before Bearer authentication causes preflight failures. `cors(...)` and WebFlux CORS source APIs differ from Servlet; do not copy a Servlet `UrlBasedCorsConfigurationSource` bean expecting all details to match.

The rule stays the same: an allowed browser origin **does not imply authorization**; actual GET/POST requests still must pass JWT/opaque authentication and scope checks.

## 18. Designing Default Policies Across Three Application Patterns

No single catch-all fits every product. Choose based on access intent rather than habit.

### 18.1. Sensitive Business Resource Server

Characteristics:

- HTTP operations require specific scopes/permissions.
- New endpoints require security review.
- Multi-tenancy, personal data, or state-changing operations exist.

Recommended pattern:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public/catalog").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders")
        .hasAuthority("SCOPE_orders.create")
    .requestMatchers(HttpMethod.DELETE, "/api/orders/*")
        .hasAuthority("SCOPE_orders.delete")
    .anyRequest().denyAll()
)
~~~

**Benefits:** new endpoints/methods are denied by default. **Limits:** rules must be updated when valid endpoints are added, and data permissions must still be checked in services. Complex APIs may need multiple chains or custom `AuthorizationManager`s.

### 18.2. Authenticated-Users-Only Zone

Characteristics:

- Every endpoint in the designed scope exposes data **only for the current principal**.
- No operations require special scopes, or they are already guarded at the method/domain layer.
- The engineering team takes responsibility for reviewing new endpoints in this scope.

You can choose:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated()
)
~~~

**Risk:** a new sensitive endpoint will be accessible to any authenticated principal unless given its own rule. State clearly that this is intentional, and do not equate it with default deny.

### 18.3. Public Endpoints/Resources in a Separate Chain

Characteristics:

- Only specific URLs and methods are allowed without a token.
- Bearer authentication should be decoupled from the public zone.
- Certain security headers/CORS and observability are still desired by design.

You can use:

~~~text
Public SecurityFilterChain:
    securityMatcher("/public/**")
    GET /public/catalog → permitAll
    anyRequest           → denyAll

Bearer API SecurityFilterChain:
    securityMatcher("/api/**")
    GET /api/orders/**   → SCOPE_orders.read
    ...
    anyRequest           → denyAll

Fallback SecurityFilterChain:
    anyRequest           → denyAll
~~~

Chain ordering must ensure **public matchers and API matchers do not accidentally intersect in unpredictable ways**. The fallback chain protects unclassified paths, while the public chain allows only a known set of URLs.

### 18.4. Why Is There No "Silver Bullet" Catch-All for Everything?

A single final rule cannot simultaneously express admin roles, read/write scopes, public resources, and order ownership. `anyRequest` is a **default policy**, not an automatic permission inference engine. You must combine:

~~~text
Trusted token validation
     +
HTTP method/path authorization
     +
Method-level authorization if needed
     +
Object/tenant ownership policy
     +
Fallback for unclassified routes
~~~

## 19. A Scenario of Configuration Evolving Over Time

On day one, the API has only two endpoints:

~~~text
GET /api/orders/{id}   → read
POST /api/orders       → create
~~~

Policy:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders")
        .hasAuthority("SCOPE_orders.create")
    .anyRequest().denyAll()
)
~~~

Later, the team adds:

~~~text
DELETE /api/orders/{id}
~~~

### 19.1. If the Catch-All Is `denyAll`

The undeclared DELETE rule causes requests to be denied at HTTP authorization. The developer must add:

~~~java
.requestMatchers(HttpMethod.DELETE, "/api/orders/*")
    .hasAuthority("SCOPE_orders.delete")
~~~

**before** `anyRequest().denyAll()` and ensure the controller/service enforces ownership/tenant checks. This is an intentional, reviewable change.

### 19.2. If the Catch-All Is `authenticated`

The new DELETE can pass HTTP authorization with any valid JWT, including tokens holding only a read scope, **unless another rule blocks it**. Nothing in `authenticated()` automatically infers that DELETE requires `orders.delete`.

Therefore, when building multi-permission APIs, default deny prevents accidentally loosening policies when adding controllers without security matchers.

### 19.3. If a Broad Read Matcher Is Added in the Wrong Place

Suppose during refactoring, a developer changes to:

~~~java
.requestMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.DELETE, "/api/orders/*")
    .hasAuthority("SCOPE_orders.delete")
.anyRequest().denyAll()
~~~

The DELETE rule may be shadowed by the first matcher and require only the read scope. **A `denyAll` catch-all does not fix a broad matcher that matched before it.** You must inspect specific matcher ordering as well, not just check for a trailing `anyRequest().denyAll()`.

## 20. Checklist When Reviewing `authorizeHttpRequests`

When reading a Spring Security Resource Server configuration, ask these questions:

| Question | Why does it matter? |
|---|---|
| Which security chain receives the request first? | Prevents a broad chain from swallowing the API chain |
| Is there a fallback chain protecting out-of-scope requests? | Prevents URLs from going unprotected when no chain matches |
| Are admin/write matchers placed before broad matchers? | Prevents strong policies from being shadowed by weak matchers |
| Do rules account for HTTP methods? | Prevents GET read permissions from applying to POST/DELETE |
| Is `anyRequest` explicitly declared at the end? | Provides a clear, readable default policy |
| Is the default `denyAll`, `authenticated`, or `permitAll`? | Each choice has distinct consequences for new endpoints |
| Does the public matcher allow too many URLs/methods? | Prevents exposing management/internal endpoints |
| Are JWT/opaque scopes mapped to the right authorities? | Prevents unexpected 403s or unintended permissions |
| Does the API validate issuer, audience, and token validity? | Authorization is meaningful only after trustworthy authentication |
| Is CORS preflight handled properly? | Avoids browser errors and overly broad OPTIONS rules |
| Do any routes depend on ERROR/FORWARD dispatches? | Prevents dispatcher policies from causing bypasses or broken error pages |
| Are owner/tenant permissions checked in the service? | Prevents cross-user data leakage |
| Do HTTP tests cover both allowed and denied requests? | Catches matcher ordering and default policy bugs |
| Are new/unlisted URLs tested? | Confirms the fallback actually takes effect |
| Are gateway, context path, and servlet path consistent? | Prevents matchers from diverging from paths handled by the app |

**Never treat `permitAll()`, `authenticated()`, `hasAuthority(...)`, and `denyAll()` as an unordered set.** Ordering is part of access-control design; a single misplaced broad matcher can alter the policy of many endpoints.

## 21. Self-Check Exercises

### Exercise 1: Which Matcher Is Used?

Given:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
)
~~~

**Question:** Which rule applies to `GET /api/admin/users`?

**Answer:** `/api/** → authenticated()`. This matcher appears first and already matches. The later `hasRole("ADMIN")` rule is never evaluated. Swap the order of the two matchers.

### Exercise 2: Valid Token Without the Scope

Given:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.anyRequest().denyAll()
~~~

**Question:** A JWT has valid issuer/audience and is unexpired, yet carries only `SCOPE_profile`, calling `GET /api/orders/42`?

**Answer:** The token authenticates successfully, but HTTP authorization denies it for lacking `SCOPE_orders.read`. Typically the response is 403, without falling through to `anyRequest`.

### Exercise 3: A New Endpoint

Given:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.anyRequest().denyAll()
~~~

**Question:** A developer adds `DELETE /api/orders/42` and forgets to add a security rule; what is the expected result?

**Answer:** DELETE does not match the GET matcher and falls into the chain's `anyRequest().denyAll()`, so it is denied. Add an explicit DELETE rule only after defining the `orders.delete` permission and business policy.

### Exercise 4: Multiple Chains

Given:

~~~text
Chain A @Order(1):
  securityMatcher("/api/**")
  anyRequest().denyAll()

No Chain B exists.
~~~

**Question:** Does Chain A block `GET /internal/reports`?

**Answer:** No. It does not match `securityMatcher("/api/**")`, so it does not enter Chain A. Define a fallback chain or other security coverage for requests outside `/api/**`.

### Exercise 5: Public Endpoint Receiving an Invalid Bearer Token

Given:

~~~java
.requestMatchers("/public/**").permitAll()
.anyRequest().authenticated()
~~~

with `oauth2ResourceServer(...jwt(...))` enabled on the same chain.

**Question:** If a client sends an invalid JWT to `/public/catalog`, does `permitAll()` guarantee a 200 response?

**Answer:** No. The Bearer authentication filter can detect the invalid token and return an authentication error before the `permitAll` authorization rule runs. If you need a public chain without Bearer verification, design a separate chain with a clear scope.

### Exercise 6: Is POST Swallowed by the GET Rule?

Given:

~~~java
.requestMatchers("/api/orders/**").hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.POST, "/api/orders").hasAuthority("SCOPE_orders.create")
.anyRequest().denyAll()
~~~

**Question:** Is POST guaranteed to require `SCOPE_orders.create`?

**Answer:** Not guaranteed. If the first broad matcher matches the POST path under the active matcher semantics, the request receives `SCOPE_orders.read` instead of the create rule. To avoid bugs, never place a method-unrestricted matcher ahead of write rules sharing the same path scope.

### Exercise 7: What Constitutes a Complete Default-Deny Policy?

**Answer:** Not merely putting `anyRequest().denyAll()` in one chain. You must ensure every sensitive request is picked up by a suitable protective chain, specific rules are properly ordered, and unclassified requests reach the deny catch-all inside the chain/fallback. The service layer must still check data permissions.

## 22. Key Takeaways

Servlet HTTP authorization can be pictured as two "first match wins" passes:

~~~text
HTTP REQUEST
   |
   v
FilterChainProxy
   |
   +-- Select first matching SecurityFilterChain
   |      (securityMatcher, @Order)
   |
   v
Authentication in the selected chain
   |
   v
authorizeHttpRequests
   |
   +-- Select first matching RequestMatcher
   |      (method, path, dispatcher type...)
   |
   +-- Apply that matcher's AuthorizationManager
   |      permitAll / authenticated /
   |      hasAuthority / hasRole / denyAll
   |
   v
Controller/service if permitted
   |
   v
Check owner/tenant/business permissions as needed
~~~

**Three practical principles to retain:**

1. **Specific first, broad later:** admin, write/delete, method-specific, and sensitive paths must precede broad matchers.
2. **Intentional final catch-all:** `anyRequest().denyAll()` fits a deny-by-default posture; `authenticated()` fits only when you truly want every authenticated principal to access remaining URLs; `permitAll()` should never be an accidental fallback on a protected API.
3. **Full chain coverage:** `anyRequest` takes effect only inside the selected chain. With multiple `SecurityFilterChain`s, use proper `@Order`, `securityMatcher`, and a fallback chain so no paths sit outside protection.

Enforcing proper **rule matching order** and **default rules for remaining requests** ensures a Resource Server not only validates access tokens accurately, but also prevents valid tokens from being used beyond their intended endpoints, methods, and permissions.

## References

- [Spring Security — Authorize HTTP Requests (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Java Configuration / Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive Authorization / Authorize Exchanges](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Security — Spring Security Test](https://docs.spring.io/spring-security/reference/servlet/test/index.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [OWASP — API Security Top 10](https://owasp.org/API-Security/editions/2023/en/0x11-t10/)
