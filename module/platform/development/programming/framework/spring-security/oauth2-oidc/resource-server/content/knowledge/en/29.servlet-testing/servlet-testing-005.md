# Testing Scopes, Roles, HTTP Methods, and Resource Access

A **Spring Security OAuth 2.0 Resource Server** may verify an access token successfully yet still need to reject a request if the token lacks a scope, the user lacks a role, the HTTP method is disallowed, or the caller does not own the accessed resource.

When testing Servlet applications, separate four decision layers:

1. **Authentication:** does the request have a verified identity?
2. **Scope/authority:** does the access token carry the required OAuth2 permission?
3. **Role:** does the principal hold the required application role?
4. **Resource authorization:** does the principal have access to the exact record, tenant, or business object?

HTTP methods and URLs are also part of the policy: read permission via GET does not automatically permit POST, PUT, or DELETE on the same path.

This lesson presents how to configure authorization with **HttpSecurity**, how to distinguish **SCOPE_** and **ROLE_**, how to enforce method and resource-level access, and how to test them using **MockMvc**, **Spring Security Test**, **@WithMockUser**, **jwt()**, and **opaqueToken()**. A critical part is recognizing which tests verify authorization and which actually test JWT signatures or introspection.

## 1. Authentication and authorization are two distinct steps

In a Servlet Resource Server, a Bearer request typically flows through:

~~~mermaid
flowchart TD
    R[HTTP request + Authorization Bearer] --> F[BearerTokenAuthenticationFilter]
    F --> V[JwtDecoder or OpaqueTokenIntrospector]
    V -->|Invalid| U[401 Unauthorized]
    V -->|Valid| A[Authentication + GrantedAuthorities]
    A --> Z{Authorization policy}
    Z -->|Sufficient scope, role, resource permission| OK[Controller / service]
    Z -->|Missing permission| D[403 Forbidden or policy 404]
    OK --> M[Domain operation]
~~~

**Authentication** answers: "Who is calling and is the credential valid?"

**Authorization** answers: "Is this identity allowed to perform this specific action on this resource?"

Access token example:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
~~~

The Resource Server may verify signature, issuer, audience, and expiration successfully. However, the token only has **orders.read**, so it must not automatically allow creating or deleting orders.

An authenticated request does not mean every endpoint is allowed.

## 2. How are scopes mapped to authorities?

Spring Security uses **GrantedAuthority** as its general permission unit. With a JWT Resource Server, the default **JwtAuthenticationConverter** uses **JwtGrantedAuthoritiesConverter** to convert scopes into authorities.

Claim example:

~~~json
{
  "scope": "orders.read orders.write"
}
~~~

Corresponding default authorities:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Some access tokens use the **scp** claim instead of **scope**. Spring Security's default converter supports these common scope conventions; confirm the actual Authorization Server contract.

### 2.1. hasAuthority checks the exact value

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
)
~~~

**hasAuthority("SCOPE_orders.read")** requires that exact authority string.

If the token only has **SCOPE_orders.write**, the request fails the read rule unless another policy grants the corresponding permission.

### 2.2. Scopes are permissions granted to an access token

Scopes typically represent the bounds granted to a client/user when requesting an access token, for example:

~~~text
orders.read
orders.write
inventory.read
payments.refund
~~~

Scopes have meaning according to the contract between the Authorization Server, client, and Resource Server. Never infer from a scope's name alone that it means the exact same permission across every issuer or every API.

### 2.3. Do not confuse the scope claim with the authority string

If the token contains:

~~~json
{
  "scope": "orders.read"
}
~~~

the default authority is normally **SCOPE_orders.read**, not **orders.read** and not **ROLE_orders.read**.

If authorization is configured as:

~~~java
.hasAuthority("orders.read")
~~~

the request may be rejected even though the JWT contains scope `orders.read`, because the authority prefix does not match.

You can change the prefix via the converter, but it must be consistent across the application and explicitly tested.

## 3. How do roles differ from scopes?

Roles typically represent roles within an application or organization, for example:

~~~text
ADMIN
ORDER_MANAGER
AUDITOR
SUPPORT_AGENT
~~~

Spring Security uses the **ROLE_** prefix convention for role-based rules.

~~~java
.hasRole("ADMIN")
~~~

is equivalent to checking the authority:

~~~java
.hasAuthority("ROLE_ADMIN")
~~~

**hasRole("ADMIN") automatically prepends the ROLE_ prefix** under the default role prefix configuration. Do not pass `ROLE_ADMIN` into `hasRole`, as it can cause a duplicated prefix or configuration errors depending on the API.

### 3.1. Scopes and roles are not automatically equivalent

| Criterion | Scope | Role |
|---|---|---|
| Common meaning | Permission granted to an access token | Role of a user/client in the application |
| Examples | orders.read, orders.write | ADMIN, AUDITOR |
| Default authority from JWT scope | SCOPE_orders.read | Not automatically mapped from a roles claim |
| Common rule | hasAuthority("SCOPE_orders.read") | hasRole("ADMIN") |
| Data source | OAuth2 access token contract | May be a verified claim or UserDetails/policy service |

This is a useful distinction, not a mandatory rule for every system. An Authorization Server might emit role claims, but the Resource Server must explicitly decide which claims are trusted and how they map.

### 3.2. The roles claim is not mapped to ROLE_ automatically

JWT example:

~~~json
{
  "sub": "alice",
  "scope": "orders.read",
  "roles": ["ADMIN", "ORDER_MANAGER"]
}
~~~

The default converter does not automatically assume every claim named `roles` represents application roles. To use this claim, you must configure **JwtAuthenticationConverter** or a custom converter to map it.

Never grant `ROLE_ADMIN` simply because a request sends a header or self-declared `roles` JSON. Read claims only after the JWT has been verified by the decoder.

## 4. Configuring authorization by scope, role, and HTTP method

Suppose an Orders API has the policy:

- `GET /api/orders/**` requires scope `orders.read`.
- `POST /api/orders/**` requires scope `orders.write`.
- `DELETE /api/orders/**` requires role `ADMIN`.
- `/api/admin/**` requires role `ADMIN`.
- All other requests are denied.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(HttpMethod.PUT, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
                    .hasRole("ADMIN")
                .requestMatchers("/api/admin/**")
                    .hasRole("ADMIN")
                .anyRequest()
                    .denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

The example assumes the application has configured `JwtDecoder` and appropriate token validation.

### 4.1. Matcher order matters

Spring Security applies authorization rules in matcher declaration order. Specific rules should be declared before broad rules.

Wrong example:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers(HttpMethod.DELETE, "/api/orders/**").hasRole("ADMIN")
)
~~~

The `/api/**` rule matches first and only requires authenticated access; the subsequent DELETE rule is never used for that request.

Corrected:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.DELETE, "/api/orders/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
)
~~~

Even better, define specific scopes/roles for each API group and use **anyRequest().denyAll()** if the system needs to fail closed when new routes appear.

### 4.2. Same path, different methods

~~~text
GET    /api/orders/42  -> SCOPE_orders.read
POST   /api/orders     -> SCOPE_orders.write
PUT    /api/orders/42  -> SCOPE_orders.write
DELETE /api/orders/42  -> ROLE_ADMIN
~~~

Do not use a single broad `authenticated()` rule for all methods if business operations require different permissions.

### 4.3. HTTP method is not resource permission

The rule `GET + orders.read` only checks permission at the route/method level. It does not prove the user is allowed to view **order 42**.

If two users both have scope `orders.read`, both can pass the HTTP rule, yet only the owner or a member of the right tenant may view the specific record.

Therefore, resource/service-level authorization is also required.

## 5. Configuring a custom role claim for JWT

Suppose the Authorization Server emits:

~~~json
{
  "sub": "alice",
  "scope": "orders.read",
  "roles": ["ADMIN", "ORDER_MANAGER"]
}
~~~

We want:

- scope `orders.read` → `SCOPE_orders.read`
- role `ADMIN` → `ROLE_ADMIN`
- role `ORDER_MANAGER` → `ROLE_ORDER_MANAGER`

You can combine **JwtGrantedAuthoritiesConverter** with a roles converter:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Configuration
class JwtAuthorityConfiguration {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopeConverter =
            new JwtGrantedAuthoritiesConverter();

        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();

        converter.setJwtGrantedAuthoritiesConverter(jwt -> {
            Collection<GrantedAuthority> authorities =
                new ArrayList<>(scopeConverter.convert(jwt));

            List<String> roles = jwt.getClaimAsStringList("roles");
            if (roles != null) {
                for (String role : roles) {
                    authorities.add(
                        new SimpleGrantedAuthority("ROLE_" + role)
                    );
                }
            }

            return authorities;
        });

        return converter;
    }
}
~~~

Attach the converter to the Resource Server:

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        JwtAuthenticationConverter jwtAuthenticationConverter)
        throws Exception {

    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers("/api/admin/**")
                .hasRole("ADMIN")
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt
                .jwtAuthenticationConverter(jwtAuthenticationConverter)
            )
        );

    return http.build();
}
~~~

### 5.1. Restricting role-granting sources

Do not map every role claim from every issuer into internal privileges.

For example, a partner issuer's token containing:

~~~json
{
  "roles": ["ADMIN"]
}
~~~

should not automatically be allowed to become **ROLE_ADMIN** in the internal administration system.

If there are multiple issuers, role mapping should depend on the verified issuer/resource contract. You can use a separate converter per decoder/AuthenticationManager or namespace authorities accordingly.

### 5.2. Testing mapping independently

You can unit test the converter with a test-constructed Jwt:

~~~java
Jwt jwt = Jwt.withTokenValue("test-token")
    .header("alg", "none")
    .claim("sub", "alice")
    .claim("scope", "orders.read")
    .claim("roles", List.of("ADMIN"))
    .build();

JwtAuthenticationToken authentication =
    (JwtAuthenticationToken) jwtAuthenticationConverter.convert(jwt);

assertThat(authentication.getAuthorities())
    .extracting(GrantedAuthority::getAuthority)
    .contains("SCOPE_orders.read", "ROLE_ADMIN");
~~~

This is a mapping unit test. The Jwt created in the test does not have a valid signature and does not test JwtDecoder.

## 6. Resource access: owner, tenant, and specific record

An endpoint:

~~~http
GET /api/orders/42
~~~

may simultaneously require:

- Valid token.
- Scope `orders.read`.
- Token's tenant matches the order's tenant.
- Token's subject is the owner or has permission to manage the order.
- Order exists and is in a readable state.

This is **resource-level authorization**.

### 6.1. Why path matchers are not enough

The rule:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

does not know who owns order 42. It only knows the request matches the path/method and Authentication has the required authority.

Never treat hard-to-guess UUIDs as an authorization mechanism. Attackers can obtain IDs via logs, URLs, exports, or another source.

### 6.2. Using method security for resource policies

Enable method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Example of an authorization component checking subject, tenant, and ownership:

~~~java
import java.util.UUID;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;

@Component("orderAuthorization")
class OrderAuthorization {

    private final OrderRepository repository;

    OrderAuthorization(OrderRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(
            Authentication authentication,
            UUID orderId,
            String subject,
            String tenantId) {

        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)) {
            return false;
        }

        String tokenSubject = jwtAuth.getToken().getSubject();
        String tokenTenant =
            jwtAuth.getToken().getClaimAsString("tenant_id");

        if (tokenSubject == null || tokenTenant == null) {
            return false;
        }

        if (!tokenSubject.equals(subject) || !tokenTenant.equals(tenantId)) {
            return false;
        }

        return repository.existsByIdAndTenantIdAndOwnerSubject(
            orderId, tenantId, subject
        );
    }
}
~~~

In production code, remove unused imports and replace the repository with the appropriate API. The example only illustrates an owner/tenant policy for a JWT-based API.

Protect the service method:

~~~java
import java.util.UUID;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;
import org.springframework.stereotype.Service;

@Service
class OrderService {

    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize(
        "@orderAuthorization.canRead(authentication, #orderId, #subject, #tenantId)"
    )
    public Order getOrder(
            @P("orderId") UUID orderId,
            @P("subject") String subject,
            @P("tenantId") String tenantId) {

        return repository
            .findByIdAndTenantIdAndOwnerSubject(orderId, tenantId, subject)
            .orElseThrow(OrderNotFoundException::new);
    }
}
~~~

The controller reads subject and tenant from the verified JWT:

~~~java
import java.util.UUID;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/api/orders/{id}")
    Order getOrder(
            @PathVariable UUID id,
            @AuthenticationPrincipal Jwt jwt) {

        return orderService.getOrder(
            id,
            jwt.getSubject(),
            jwt.getClaimAsString("tenant_id")
        );
    }
}
~~~

Key points:

- Subject and tenant are taken from the verified JWT, not from client-supplied query parameters.
- The authorization component checks identity and the repository.
- The read query also restricts by tenant/owner, avoiding checking once and then loading unrestricted data in a later query.
- If the API supports opaque tokens or multiple principal types, design a shared identity abstraction instead of casting every Authentication to `JwtAuthenticationToken`.

### 6.3. Choosing between 403 and 404

When a user knows an ID but does not own the resource, the API may:

- Return **403 Forbidden** to explicitly state the principal lacks permission.
- Return **404 Not Found** to avoid revealing whether the resource exists.

This is a security/API contract decision. Keep it consistent across GET, PUT, DELETE, and related endpoints.

### 6.4. Do not use @PostAuthorize for every operation

**@PostAuthorize** checks permissions after the method has executed. It can be useful when inspecting the returned result, but the method has already read data or performed side effects before being denied.

For mutating operations, check permissions before execution. For list queries, prefer filtering directly at the repository/database by tenant/owner instead of loading everything and using `@PostFilter`.

## 7. Protecting service methods with @PreAuthorize

Method security is useful when the same service is called from multiple controllers or internal components.

Example:

~~~java
@Service
class PaymentService {

    @PreAuthorize("hasAuthority('SCOPE_payments.refund')")
    public void refund(UUID paymentId) {
        // Perform refund after checking other domain rules
    }

    @PreAuthorize("hasRole('FINANCE_ADMIN')")
    public void exportFinancialReport() {
        // Export financial report
    }
}
~~~

Conditions can be combined:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.write') and hasRole('ORDER_MANAGER')"
)
public void updateOrder(UUID orderId) {
    // ...
}
~~~

Both authorities are required to pass the rule.

### 7.1. Method security does not replace request authorization

Both can be used together:

- HTTP layer: method/path requires read or write scope.
- Service layer: user has access to the specific order/tenant.

The HTTP layer blocks unsuitable requests early. The service layer protects business operations even if the method is called from another entry point.

### 7.2. Method security relies on Spring AOP proxies

Method calls must pass through the Spring-managed proxy for method security to apply. **Self-invocation** from one method to another on the same instance can bypass the proxy.

Example:

~~~java
public void outer() {
    this.sensitiveOperation(); // May bypass proxy-based method interceptor
}

@PreAuthorize("hasRole('ADMIN')")
public void sensitiveOperation() {
    // ...
}
~~~

Do not rely on the annotation if the call path does not go through the proxy. Split the service bean or design appropriate boundaries.

## 8. MockMvc and Spring Security Test

Spring Security provides test support for Servlet via **spring-security-test**.

Gradle dependency:

~~~groovy
dependencies {
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

If using Spring Boot dependency management, do not specify a version different from the application's Spring Security version.

MockMvc allows sending simulated HTTP requests through MVC and the Spring Security filters attached to the test context.

### 8.1. Enabling Spring Security filters in MockMvc

With Spring Boot:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderApiSecurityTests {

    @Autowired
    MockMvc mvc;
}
~~~

With manual configuration:

~~~java
MockMvc mvc = MockMvcBuilders
    .webAppContextSetup(applicationContext)
    .apply(springSecurity())
    .build();
~~~

**Do not use @AutoConfigureMockMvc(addFilters = false)** in tests intended to verify SecurityFilterChain. When filters are disabled, requests can go straight to the controller and the test no longer proves HTTP-layer authorization.

If using `standaloneSetup`, you must explicitly attach Spring Security filters/configuration properly; otherwise security behavior may differ from the real application.

## 9. Testing JWT authorization with jwt()

Spring Security Test has the **jwt()** `RequestPostProcessor` to create a `JwtAuthenticationToken` for the request.

Example:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void readOrdersWithReadScopeIsAllowed() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isOk());
}
~~~

The request enters the `SecurityContext` with an Authentication holding the specified authority.

### 9.1. Testing missing scope

~~~java
@Test
void readOrdersWithoutReadScopeIsForbidden() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.write")
            )))
        .andExpect(status().isForbidden());
}
~~~

The mock JWT may be authenticated, yet it lacks the required authority, so authorization rejects with 403.

### 9.2. Configuring claims of the mock JWT

~~~java
mvc.perform(get("/api/orders")
        .with(jwt().jwt(jwt -> jwt
            .claim("sub", "alice")
            .claim("tenant_id", "tenant-a")
            .claim("scope", "orders.read")
        )))
    .andExpect(status().isOk());
~~~

The `jwt()` `RequestPostProcessor` creates a test JWT with customizable claims. `scope`/`scp` are converted into authorities according to the converter configured for the Resource Server, unless the test overrides authorities directly.

### 9.3. Distinguishing converter tests from authorization tests

When writing:

~~~java
.with(jwt().authorities(
    new SimpleGrantedAuthority("ROLE_ADMIN")
))
~~~

the test **directly supplies the authority to the mock Authentication**. It tests the `hasRole`/`hasAuthority` rule, but skips the `roles` claim mapping logic.

To test a custom `JwtAuthenticationConverter`, write a direct unit test to check the Authentication and authorities produced by the converter. The `jwt().authorities(...)` request post processor takes a separate `Converter<Jwt, Collection<GrantedAuthority>>`; it does not accept `JwtAuthenticationConverter` because the two converters have different return types.

### 9.4. jwt() does not verify real signatures

Per Spring Security documentation, `jwt()` creates a declarative Jwt to attach Authentication to the request. The default test JWT has header `alg=none` and does not need a valid signature.

This is very useful when the focus is authorization, but **it does not prove `JwtDecoder` checked the signature, issuer, audience, or expiration**.

## 10. Testing opaque tokens with opaqueToken()

For an opaque token Resource Server, Spring Security Test provides the **opaqueToken()** `RequestPostProcessor`.

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.opaqueToken;

@Test
void partnerReadScopeAllowsRequest() throws Exception {
    mvc.perform(get("/api/partners/orders")
            .with(opaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_partner.read")
            )))
        .andExpect(status().isOk());
}
~~~

You can configure attributes and authorities of `OAuth2AuthenticatedPrincipal` to simulate a user, tenant, or client.

Like `jwt()`, **opaqueToken() does not call a real introspection endpoint**. It creates a mock `BearerTokenAuthentication` in the `SecurityContext` to test authorization.

If the goal is to test the HTTP client, Basic client credentials, `active=false` responses, timeouts, or AS integration, you need tests with a stub/real introspection server.

## 11. Testing roles with @WithMockUser or user()

For role-based authorization, you can use:

~~~java
import org.springframework.security.test.context.support.WithMockUser;

@Test
@WithMockUser(username = "alice", roles = "ADMIN")
void adminCanDeleteOrder() throws Exception {
    mvc.perform(delete("/api/orders/42"))
        .andExpect(status().isNoContent());
}
~~~

**roles = "ADMIN"** creates authority **ROLE_ADMIN**.

Equivalent using the request post processor:

~~~java
mvc.perform(delete("/api/orders/42")
        .with(user("alice").roles("ADMIN")))
    .andExpect(status().isNoContent());
~~~

### 11.1. @WithMockUser is not JWT Authentication

`@WithMockUser` creates a username/password-style Authentication with a `User` principal. It is useful for:

- Role rules.
- Method security.
- Policies independent of JWT claims.
- Testing service logic by authorities.

It does not prove the Resource Server received and verified a Bearer JWT. For JWT-specific claims like `tenant_id`, `sub`, `client_id`, use `jwt()` or an appropriate Authentication.

### 11.2. hasRole and roles() both use prefixes

Example:

~~~java
@PreAuthorize("hasRole('ADMIN')")
~~~

test:

~~~java
@WithMockUser(roles = "ADMIN")
~~~

Both sides match **ROLE_ADMIN**.

If using:

~~~java
@PreAuthorize("hasAuthority('ADMIN')")
~~~

then `@WithMockUser(roles = "ADMIN")` does not create authority `ADMIN`; it creates `ROLE_ADMIN`. When the exact authority `ADMIN` is needed, use `authorities`:

~~~java
@WithMockUser(authorities = "ADMIN")
~~~

## 12. Testing HTTP methods and separate scopes

Suppose configuration is:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
.requestMatchers(HttpMethod.DELETE, "/api/orders/**")
    .hasRole("ADMIN")
~~~

You can test the matrix:

~~~java
@Test
void readScopeCanGetButCannotCreateOrder() throws Exception {
    mvc.perform(get("/api/orders/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isOk());

    mvc.perform(post("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            ))
            .with(csrf()))
        .andExpect(status().isForbidden());
}

@Test
void writeScopeCanCreateOrder() throws Exception {
    mvc.perform(post("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {"productId":"p-100","quantity":2}
                """)
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.write")
            ))
            .with(csrf()))
        .andExpect(status().isCreated());
}
~~~

The example assumes an order-creation API with CSRF protection enabled. If the API is Bearer-only stateless and CSRF is disabled per threat model, test requests do not need `csrf()`.

### 12.1. Why might POST tests need csrf()?

Spring Security CSRF protection normally applies to unsafe HTTP methods. A POST request can receive 403 due to a missing CSRF token **before scope authorization is evaluated**.

If a test aims to prove a token lacking `orders.write` is rejected, yet does not send a CSRF token in a CSRF-enabled application, the 403 result is not guaranteed to come from the scope rule.

Use:

~~~java
.with(csrf())
~~~

to pass the CSRF layer in scope authorization tests, or test CSRF separately.

Do not disable CSRF application-wide just to make tests pass. Only disable it for APIs that truly do not use browser-ambient credentials such as session cookies or JWT cookies.

### 12.2. 405 vs 403

- **403**: request was rejected by security/authorization or CSRF policy.
- **405 Method Not Allowed**: request reached MVC handler mapping, but the method is not supported by the endpoint.
- **401**: no valid Authentication yet.

If `anyRequest().denyAll()` catches an HTTP method without a declared rule, the request may receive 403 before MVC returns 405. When testing 405, supply sufficient Authentication/authority so the request passes the security layer and reaches handler mapping.

## 13. Testing resource-level authorization

Suppose user Alice belongs to tenant A, and user Bob belongs to tenant B.

| Caller | Order | Policy outcome |
|---|---|---|
| Alice / tenant A | Alice's order / tenant A | Allowed |
| Alice / tenant A | Bob's order / tenant A | Denied |
| Alice / tenant A | Tenant B order | Denied |
| Alice / tenant A | Non-existent ID | 404 |
| Admin with tenant-wide permission | Same-tenant order | Per admin policy |
| Tenant A admin | Tenant B order | Denied |

### 13.1. Testing JWT claims and resource ownership

Example:

~~~java
@Test
void ownerCanReadOwnOrder() throws Exception {
    mvc.perform(get("/api/orders/42")
            .with(jwt().jwt(jwt -> jwt
                .claim("sub", "alice")
                .claim("tenant_id", "tenant-a")
            ).authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isOk());
}

@Test
void anotherUserCannotReadOrder() throws Exception {
    mvc.perform(get("/api/orders/42")
            .with(jwt().jwt(jwt -> jwt
                .claim("sub", "bob")
                .claim("tenant_id", "tenant-a")
            ).authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isForbidden());
}
~~~

These two tests assume order 42 belongs to Alice in tenant A and the service method enforces resource authorization. The second test keeps the same scope as the first while changing the subject, proving **the scope does not automatically grant access to every order**.

### 13.2. Testing cross-tenant access

~~~java
@Test
void userCannotReadOrderFromAnotherTenant() throws Exception {
    mvc.perform(get("/api/orders/42")
            .with(jwt().jwt(jwt -> jwt
                .claim("sub", "alice")
                .claim("tenant_id", "tenant-b")
            ).authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isNotFound());
}
~~~

Status 404 in the example reflects an anti-enumeration policy: do not disclose whether the order exists in another tenant. If your API contract uses 403, test for that status.

### 13.3. Do not test only with a mocked controller/service

If you only mock the service:

~~~java
when(orderService.getOrder(...)).thenReturn(order);
~~~

the controller test might not pass through the method-security proxy or repository ownership query. When testing resource authorization, test the real service bean/proxy and repository policy.

You can use integration tests with a test database, or test service method security separately using a Spring context with `@EnableMethodSecurity` enabled.

## 14. Testing method security

Enable:

~~~java
@EnableMethodSecurity
~~~

Service example:

~~~java
@Service
class AdminReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public Report generate() {
        return new Report();
    }
}
~~~

Test:

~~~java
@SpringBootTest
class AdminReportServiceTests {

    @Autowired
    AdminReportService service;

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanGenerateReport() {
        assertThat(service.generate()).isNotNull();
    }

    @Test
    @WithMockUser(roles = "USER")
    void regularUserIsDenied() {
        assertThatThrownBy(() -> service.generate())
            .isInstanceOf(AccessDeniedException.class);
    }
}
~~~

This test invokes the service bean from the Spring context so the method-security proxy applies. If the test calls an object instantiated directly with `new`, the annotation may not be intercepted.

### 14.1. Scope method security

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.write')")
public void updateOrder(UUID orderId) {
    // ...
}
~~~

A test with Authentication holding `SCOPE_orders.read` must be denied; `SCOPE_orders.write` is required to pass.

### 14.2. @PostAuthorize rule

~~~java
@PostAuthorize("returnObject.owner == authentication.name")
public Document getDocument(UUID id) {
    return repository.findById(id).orElseThrow();
}
~~~

You can check permissions on the result, though the document has already been loaded before the policy runs. For sensitive data or side effects, prefer checking beforehand or scoping the database query directly.

## 15. Testing real JWT signatures, issuer, audience, and expiration

The **jwt()** test post processor skips cryptographic verification. If the goal is to test `JwtDecoder`, send a token signed with a test key through the real Bearer filter.

Key tests:

- JWT with valid signature, right issuer/audience, unexpired `exp` → authenticated.
- Tampered signature → 401.
- Untrusted issuer → 401.
- Wrong audience for the API → 401.
- Expired token → 401.
- `nbf` in the future beyond clock skew → 401.
- Disallowed algorithm → 401.
- Valid scope but missing resource permission → 403 or policy 404.

You can use a test RSA/EC key pair and `JwtEncoder`/`JwtDecoder` or a JWKS test server. Testing with a mock decoder is useful for filter/exception handling, but does not prove signature/JWKS behavior.

### 15.1. Separating tests by objective

| Objective | Appropriate test approach |
|---|---|
| Scope authorization | MockMvc + jwt() |
| Opaque authorities authorization | MockMvc + opaqueToken() |
| Role-based authorization | @WithMockUser or user() |
| Custom role converter | Unit test converter and integration test wired converter |
| HTTP method policy | MockMvc across HTTP methods |
| Resource ownership/tenant | Method security + repository integration |
| JWT signature/issuer/aud/exp | Signed JWT + real JwtDecoder |
| Opaque introspection | HTTP stub/test AS server |
| CSRF | Unsafe requests with/without csrf() |
| SecurityFilterChain coverage | MockMvc running full Spring Security filters |

## 16. Testing 401, 403, 404, and 405 for the right cause

| Status | Typical meaning | What to check |
|---|---|---|
| **401 Unauthorized** | No valid Authentication | Missing Bearer token, invalid signature, expired, inactive |
| **403 Forbidden** | Authenticated but insufficient permissions, or CSRF rejected | Scope, role, resource policy, CSRF |
| **404 Not Found** | Resource does not exist or intentionally hidden when unauthorized | Resource existence/tenant policy |
| **405 Method Not Allowed** | MVC has no handler for that method after security passes | Request mapping and HTTP method |

Do not assert only status codes. When a test fails, identify which layer rejected it:

1. Bearer token extraction.
2. Authentication provider/decoder/introspector.
3. CSRF filter.
4. Request authorization.
5. Method security.
6. Resource/domain authorization.
7. MVC handler mapping.

A 403 caused by missing CSRF does not prove scope checking works.

## 17. Verifying SecurityFilterChain is actually attached to MockMvc

With test configuration:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class SecurityIntegrationTests {
    @Autowired
    MockMvc mvc;
}
~~~

Spring Boot auto-configures MockMvc with filters by default.

If you use:

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

filters are bypassed. Do not use this setting for authorization tests.

With `@WebMvcTest`, ensure `SecurityFilterChain` and necessary security beans are imported/mocked properly. A slice test may not load the application's full Resource Server configuration.

Also check `SecurityFilterChain` ordering if the application has multiple chains: requests to `/api/orders/**` must enter the intended chain, not be picked up earlier by a broader chain.

## 18. Testing OpaqueTokenAuthentication and authority mapping

With an opaque Resource Server, the introspection response can carry attributes and scopes. Spring Security converts the information returned by the introspector into principal/authorities according to configuration.

Use test:

~~~java
mvc.perform(get("/api/partners/orders")
        .with(opaqueToken()
            .authorities(
                new SimpleGrantedAuthority("SCOPE_partner.read")
            )
        ))
    .andExpect(status().isOk());
~~~

This is an authorization test with a mock principal. To test mapping from a real introspection response, use a test `OpaqueTokenIntrospector` or stub HTTP introspection endpoint.

Scenarios:

- `active=false` → authentication fails.
- `active=true`, sufficient scope → authorization can succeed.
- `active=true`, missing scope → 403.
- introspection timeout/5xx → verification error, no successful Authentication created.
- mismatched issuer/audience/tenant attributes → rejected by custom validation/policy.

Do not use `opaqueToken()` to conclude the HTTP introspection endpoint or client credentials are working.

## 19. Testing role and scope together

An endpoint may require both a scope and a role:

~~~java
.requestMatchers(HttpMethod.POST, "/api/orders/**")
    .access((authentication, context) ->
        new AuthorizationDecision(
            authentication.get().getAuthorities().stream()
                .anyMatch(a -> a.getAuthority().equals("SCOPE_orders.write"))
            &&
            authentication.get().getAuthorities().stream()
                .anyMatch(a -> a.getAuthority().equals("ROLE_ORDER_MANAGER"))
        )
    )
~~~

The example above illustrates AND logic. In production code, write a dedicated custom `AuthorizationManager`/component if the policy is complex, making it easy to test and avoiding repeated stream logic.

A simpler rule can use:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.write') and hasRole('ORDER_MANAGER')"
)
~~~

### 19.1. AND matrix

| Scope | Role | Result |
|---|---|---|
| orders.write | ORDER_MANAGER | Allowed |
| orders.write | USER | Denied |
| orders.read | ORDER_MANAGER | Denied |
| orders.read | USER | Denied |

Test every combination, not only the success case.

## 20. Testing list resources and tenant filtering

For endpoint:

~~~http
GET /api/orders
~~~

if the user belongs to tenant A, the API should only return orders belonging to tenant A and records the user is allowed to view.

Do not:

1. Load all orders.
2. Return the list to the controller.
3. Filter by comparing subject in memory at the end.

That approach risks leaking data via logs, metrics, memory, pagination counts, or logic bugs.

Prefer repository queries conditioned on tenant/owner:

~~~java
Page<Order> findByTenantIdAndOwnerSubject(
    String tenantId,
    String subject,
    Pageable pageable
);
~~~

Tests:

- Tenant A user receives only tenant A data.
- Pagination counts reflect only permitted data.
- Sorting/filtering does not leak tenant B records.
- Users without management roles cannot toggle a query flag to view the entire tenant.
- The tenant ID in the query comes from the verified identity, not trusting client-sent parameters.

## 21. CSRF configuration and testing POST/PUT/DELETE

Servlet Spring Security normally enables CSRF protection in default web configurations. For stateless Bearer-only APIs, configuration may differ if tokens are explicitly sent in the `Authorization` header and no browser-ambient credentials are used.

If the application uses session cookies, JWT cookies, or Basic auth sent automatically by browsers, CSRF still needs evaluation.

In MockMvc, POST/PUT/PATCH/DELETE requests may require:

~~~java
.with(csrf())
~~~

Test CSRF separately:

~~~java
@Test
void postWithoutCsrfIsRejectedWhenCsrfIsEnabled() throws Exception {
    mvc.perform(post("/web/profile"))
        .andExpect(status().isForbidden());
}

@Test
void postWithCsrfPassesCsrfLayer() throws Exception {
    mvc.perform(post("/web/profile")
            .with(user("alice"))
            .with(csrf()))
        .andExpect(status().isOk());
}
~~~

The example assumes a web endpoint requiring authentication and CSRF. The second test needs an appropriate role/scope if authorization rules require additional permissions.

Do not remove CSRF just because a POST test returns 403. Identify the cause of the 403 first.

## 22. A sample test suite based on an authorization matrix

Policy example:

| Method | Path | Requirement |
|---|---|---|
| GET | /api/orders/** | SCOPE_orders.read |
| POST | /api/orders/** | SCOPE_orders.write |
| DELETE | /api/orders/** | ROLE_ADMIN |
| GET | /api/admin/** | ROLE_ADMIN |
| Any other request | Any path | denyAll |

Minimum test suite should include:

~~~java
@Test
void anonymousRequestGets401() throws Exception {
    mvc.perform(get("/api/orders"))
        .andExpect(status().isUnauthorized());
}

@Test
void readScopeCanReadOrders() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isOk());
}

@Test
void writeScopeCannotReadWhenReadScopeIsRequired() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.write")
            )))
        .andExpect(status().isForbidden());
}

@Test
void readScopeCannotDeleteOrder() throws Exception {
    mvc.perform(delete("/api/orders/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isForbidden());
}

@Test
void adminRoleCanDeleteOrder() throws Exception {
    mvc.perform(delete("/api/orders/42")
            .with(user("admin").roles("ADMIN"))
            .with(csrf()))
        .andExpect(status().isNoContent());
}
~~~

The tests above assume:

- MockMvc has Spring Security filters attached.
- GET/DELETE have corresponding handlers.
- The DELETE chain has CSRF disabled for Bearer-only APIs or the test adds `csrf()` if CSRF is enabled.
- Endpoints actually return the stated statuses.
- Services/repositories have no extra conditions altering the outcome.

When using `@WithMockUser`/`user()` for role tests, the test focuses on role authorization. Use `jwt()` to test the JWT authority path. Do not mix the goals of the two mock Authentication types.

## 23. Layered testing checklist

### Authentication

- No token → 401.
- Invalid Bearer token → 401.
- Expired JWT → 401.
- Wrong issuer/audience → 401.
- Inactive opaque token → 401.
- Introspection/decoder infrastructure failures must not fail-open.

### Scope

- Right scope → passes.
- Missing scope → 403.
- Write-only does not grant read if policy requires read.
- Scope claim maps with the right `SCOPE_` prefix.
- Scopes from other issuers are not mis-mapped.

### Role

- `ROLE_ADMIN` passes `hasRole("ADMIN")`.
- `ROLE_USER` is denied.
- `roles` claim is mapped only when converter is configured.
- Partner issuer roles are not mapped to internal admin.

### HTTP method

- GET/POST/PUT/DELETE have distinct rules.
- Right method but missing scope → 403.
- Wrong method does not accidentally match a broad rule.
- Distinguish security 403 from MVC 405.

### Resource

- Owner can access.
- Non-owner is denied.
- Cross-tenant is denied.
- Non-existent returns 404.
- List queries are filtered directly in the repository.
- Update/delete checks permission before side effects.

### Test harness

- MockMvc includes Spring Security filters.
- `addFilters=false` is not used.
- CSRF is handled explicitly.
- `jwt()`/`opaqueToken()` are used only for authorization-focused tests.
- Signed-token/AS integration tests exist for decoder/introspection.
- Method security is invoked through Spring proxies.

## 24. Common anti-patterns

**Only testing that controllers return 200.** Does not prove scope, role, method, or resource ownership was checked.

**Using @WithMockUser to test JWT signatures.** `@WithMockUser` creates a mock username/password Authentication.

**Using jwt() and claiming the decoder verified the signature.** `jwt()` injects a mock `JwtAuthenticationToken` without needing a valid JWT.

**Using opaqueToken() and claiming AS introspection works.** The post processor does not call the introspection endpoint.

**Confusing hasRole("ADMIN") with hasAuthority("ADMIN").** `hasRole` looks for `ROLE_ADMIN` by default.

**Confusing scope orders.read with authority orders.read.** The default converter normally adds `SCOPE_`.

**Mapping untrusted roles claims to ROLE_ADMIN.** Use only verified claims and proper issuer policies.

**Using a single authenticated rule for all HTTP methods.** Can allow write/delete with a read-only token.

**Using path matchers instead of resource ownership.** Read scope does not mean permission to read every order ID.

**Checking permissions only in controllers.** A service might be called from another entry point; domain/service boundaries are needed.

**Using @PostAuthorize for operations with side effects.** The method may have already performed work before being denied.

**Using @PostFilter for large lists instead of tenant-scoped queries.** Wastes resources and risks leaking data through metadata/pagination.

**Dropping CSRF to test POST.** Can hide security bugs in browser/session flows.

**Using addFilters=false.** Tests no longer verify security filters.

**Not testing cross-tenant access.** Hard-to-guess IDs do not replace authorization.

## 25. Workflow for building a test suite

**Step 1 — Write a policy table.** List methods, paths, scopes, roles, and resource constraints.

**Step 2 — Identify Authentication type.** JWT Resource Server, opaque token, Basic, session, or custom principal.

**Step 3 — Test authority mapping.** `scope`/`scp` and roles map to `GrantedAuthority` with the right prefix.

**Step 4 — Test request authorization.** Use MockMvc and `jwt()`/`opaqueToken()`/`user()` matching the policy type.

**Step 5 — Test the method matrix.** Same path, different methods, and different scopes.

**Step 6 — Test resource authorization.** Owner, non-owner, cross-tenant, missing resource, and admin boundary.

**Step 7 — Test method security.** Enable `@EnableMethodSecurity`, invoke service beans through proxies.

**Step 8 — Test CSRF separately.** Distinguish 403 from CSRF vs 403 from missing authority.

**Step 9 — Test cryptographic/authentication integration.** Signed JWT, JWKS/issuer/audience/expiration, or introspection stub.

**Step 10 — Test through the real SecurityFilterChain.** Ensure filters, matcher order, and fallback behave like the application.

**Step 11 — Check error contracts.** 401, 403, 404, and 405 from the right layer/policy.

**Step 12 — Keep negative tests.** Whenever adding a new scope, role, route, or HTTP method, add tests proving permissions are not unintentionally widened.

## 26. Self-check questions

**1. If a JWT has scope orders.read, what is the typical default authority?**

`SCOPE_orders.read`.

**2. Which authority does hasRole("ADMIN") check?**

`ROLE_ADMIN` under the default prefix.

**3. Is the roles claim in a JWT mapped to ROLE_ADMIN automatically?**

Not by default. A custom `JwtAuthenticationConverter` or appropriate mapping is required.

**4. Can a user with scope orders.read DELETE an order?**

No, if DELETE requires `ROLE_ADMIN` or a different scope.

**5. Does GET /api/orders/** with read scope mean the user can view every order?**

No. You must check owner, tenant, or specific resource permissions.

**6. Does jwt() verify the JWT signature?**

No. It creates a mock Authentication for authorization testing.

**7. Does opaqueToken() call the introspection endpoint?**

No. It creates a mock `BearerTokenAuthentication`.

**8. What authority does @WithMockUser(roles="ADMIN") create?**

`ROLE_ADMIN`.

**9. Why can a POST without csrf() return 403 even with the right scope?**

Because the CSRF filter can reject the request before authorization rules are evaluated.

**10. What is @EnableMethodSecurity used for?**

Enabling annotations such as `@PreAuthorize` and `@PostAuthorize` for Spring-managed method calls.

**11. Why might @PostAuthorize be unsuitable for DELETE?**

The method may have already executed side effects before the authorization result is denied.

**12. When is a signed JWT integration test needed?**

When you need to test signatures, keys/JWKS, issuer, audience, `exp`/`nbf`, and the real converter/decoder rather than only testing authorization with mock Authentication.

## Conclusion

Authorization testing for a Spring Security Resource Server needs to progress from **scopes**, **roles**, and **HTTP methods** to **specific resource permissions**. A valid access token only proves the credential was accepted; it does not automatically permit every operation or every record.

In Servlet tests:

- Use **jwt()** to test authorization with a mock `JwtAuthenticationToken`.
- Use **opaqueToken()** to test authorization with a mock `BearerTokenAuthentication`.
- Use **@WithMockUser/user()** for role and method-security policies independent of JWT claims.
- Use signed JWTs and a real decoder/JWKS when cryptographic validation must be proved.
- Use an introspection stub/server when opaque-token authentication must be proved.
- Test methods, tenants, owners, and repository queries; distinguish 401, 403, 404, 405, and CSRF failures.

**A good test suite must prove both allowed requests and closely similar requests that must be denied.** In particular, cross-scope, cross-role, cross-method, and cross-tenant tests help catch unintended privilege expansion as the API evolves.

### References

- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [Spring Security — Running a Test as a User in Spring MVC Test](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security API — JwtAuthenticationConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html)
- [Spring Security API — JwtGrantedAuthoritiesConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html)
- [Spring Security API — SecurityMockMvcRequestPostProcessors](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html)
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
