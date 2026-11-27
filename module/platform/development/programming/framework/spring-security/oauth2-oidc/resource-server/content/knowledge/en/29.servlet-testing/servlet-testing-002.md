# jwt() and Creating Jwt, Claims, and Authorities for Authorization Testing

When testing a **Spring Security OAuth 2.0 Resource Server on Servlet**, we often need to verify whether a request is allowed or denied based on the access token's scope, role, tenant, or claims. Generating a real signed JWT for every authorization test would make tests verbose, dependent on keys/JWKS, and harder to keep focused on authorization rules.

Spring Security Test provides **`jwt()`**, a MockMvc request postprocessor that creates an authentication based on a **`Jwt`** object so the request is processed as if JWT authentication has already occurred. You can customize the JOSE header, claims, subject, and authorities to test authorization rules.

Key distinction: **`jwt()` tests authorization with mock JWT authentication**. It does not send a raw Bearer token through the full authentication process, does not call `JwtDecoder` to verify signatures, and does not prove that issuer/audience/expiration validators are active. When you need to test those steps, you must write separate tests using a real Authorization header with a controlled decoder or tokens signed with test keys.

> **Illustrative context:** An Orders API using Spring Boot 3.x / Spring Security 6.x receives JWT access tokens via Bearer authentication. GET endpoints require `SCOPE_orders.read`, and POST endpoints require `SCOPE_orders.write`. Examples are Servlet/MockMvc tests.

## 1. Why use jwt() in authorization testing?

An authorization test should focus on the question: given an Authentication with a specific subject and authorities, is the request allowed?

```java
mvc.perform(get("/api/orders")
        .with(jwt()))
    .andExpect(status().isOk());
```

The `jwt()` request postprocessor creates a JWT-based authentication so Spring Security can evaluate authorization. Tests do not need to spin up a real Authorization Server, call a JWKS endpoint, or sign JWTs with production private keys.

Common scenarios:

- A user with `SCOPE_orders.read` can read orders.
- A user with only `SCOPE_orders.read` cannot create orders.
- A user with role `ROLE_SUPPORT` can access support endpoints.
- A JWT has a `tenant_id` claim to test tenant boundaries.
- The JWT subject is used to check ownership.
- Method security such as `@PreAuthorize` is evaluated based on authorities.

### 1.1. jwt() creates authentication for test requests

For Servlet MockMvc, import:

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
```

Use the postprocessor:

```java
mvc.perform(get("/api/orders")
        .with(jwt()))
    .andExpect(status().isOk());
```

`jwt()` installs a JWT-backed authentication into the test request. Some default values may be supplied by the test helper; meaningful tests should explicitly declare the claims and authorities required by the authorization rules.

### 1.2. jwt() does not create a signed compact JWT

`jwt()` does not need to generate a string like:

```text
eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3Qta2V5In0...
```

It creates a `Jwt` object in the test and a corresponding `JwtAuthenticationToken`. Consequently, there is no cryptographic signature verification step like when the Resource Server processes:

```http
Authorization: Bearer eyJ...
```

This is why `jwt()` is convenient for authorization tests and also why it must not be used as proof that the JWT decoder works properly.

## 2. Dependencies and MockMvc configuration

### 2.1. Adding Spring Security Test

Gradle Groovy DSL example:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

`spring-security-test` provides request postprocessors, annotations, and test helpers for Spring Security. Use the version train managed by Spring Boot; avoid mixing an incompatible test module version with the Spring Security runtime.

### 2.2. The application needs Resource Server configuration

A typical Servlet configuration:

```java
@Configuration
@EnableWebSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

In this example, `http.oauth2ResourceServer(oauth2 -> oauth2.jwt(...))` configures the real JWT authentication path when requests carry a Bearer token. Meanwhile, `jwt()` in tests installs JWT authentication to check authorization rules.

| API | Where used | Role |
|---|---|---|
| `oauth2ResourceServer(...).jwt(...)` | Security configuration | Enables JWT Resource Server authentication |
| `SecurityMockMvcRequestPostProcessors.jwt()` | MockMvc test | Creates mock JWT-backed authentication |
| `Jwt.withTokenValue(...)` | Test/helper code | Builds a Jwt object from headers and claims |
| `JwtDecoder.decode(...)` | Authentication pipeline | Decodes and verifies tokens via decoder/validators |

### 2.3. Enabling MockMvc security filters

With Spring Boot:

```java
@SpringBootTest
@AutoConfigureMockMvc
class OrderAuthorizationTests {

    @Autowired
    MockMvc mvc;
}
```

`@AutoConfigureMockMvc` normally configures MockMvc with the application's filter chain from the context. If building MockMvc manually with `MockMvcBuilders.standaloneSetup(...)`, you need to apply the appropriate Spring Security config, typically via `springSecurity()` and the right filter chain/repository.

The standalone approach requires explicitly supplying the security configuration and filter chain; do not assume calling `springSecurity()` alone automatically creates the entire Resource Server configuration of the application.

## 3. Creating a Jwt with jwt().jwt(...)

The common approach is to use `jwt()` and configure the builder via a lambda:

```java
mvc.perform(get("/api/orders")
        .with(jwt().jwt(jwt -> jwt
            .subject("alice")
            .claim("scope", "orders.read")
            .claim("tenant_id", "tenant-a")
        )))
    .andExpect(status().isOk());
```

The lambda receives a `Jwt.Builder`. You can customize:

- `subject(...)` for the subject.
- `claim(name, value)` for any claim.
- `header(name, value)` for the JOSE header of the Jwt object.
- `issuedAt(...)` and `expiresAt(...)` for timestamps.
- `claim("iss", ...)` and `claim("aud", ...)` to create issuer/audience claims in the test object.

If you need to test decoder/issuer/audience validation, `jwt()` does not perform that validation; a separate decoder test is needed.

### 3.1. Creating meaningful claims for the API

A test JWT access token might have:

```json
{
  "iss": "https://login.example.com",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-a",
  "iat": 2000000000,
  "exp": 2000000600
}
```

Corresponding creation:

```java
mvc.perform(get("/api/orders")
        .with(jwt().jwt(jwt -> jwt
            .claim("iss", "https://login.example.com")
            .subject("alice")
            .claim("aud", List.of("orders-api"))
            .claim("scope", "orders.read")
            .claim("tenant_id", "tenant-a")
            .issuedAt(Instant.parse("2033-05-18T03:33:20Z"))
            .expiresAt(Instant.parse("2033-05-18T03:43:20Z"))
        )))
    .andExpect(status().isOk());
```

Timestamps only illustrate how to construct the object; in real tests, choose intentional fixed times or use a `Clock` to avoid tests depending on the current wall clock. These values are not checked by `JwtDecoder` when using the `jwt()` request postprocessor.

### 3.2. Creating a Jwt beforehand and passing it to jwt()

When the same token model is needed across multiple tests, you can create a helper:

```java
private Jwt ordersReadJwt() {
    Instant now = Instant.parse("2030-01-01T10:00:00Z");

    return Jwt.withTokenValue("test-access-token")
        .header("alg", "none")
        .claim("iss", "https://login.example.com")
        .claim("sub", "alice")
        .claim("aud", List.of("orders-api"))
        .claim("scope", "orders.read")
        .claim("tenant_id", "tenant-a")
        .issuedAt(now.minusSeconds(30))
        .expiresAt(now.plusSeconds(300))
        .build();
}
```

Usage:

```java
mvc.perform(get("/api/orders")
        .with(jwt().jwt(ordersReadJwt())))
    .andExpect(status().isOk());
```

The `alg=none` header in the test object is not a valid JWT signature and is not used for cryptographic validation testing. It is a Jwt object constructed directly for the test postprocessor.

### 3.3. Creating multiple Jwts per persona/permission

```java
private Jwt jwtFor(
        String subject,
        String scope,
        String tenantId) {

    Instant now = Instant.parse("2030-01-01T10:00:00Z");

    return Jwt.withTokenValue("token-for-" + subject)
        .header("alg", "none")
        .claim("iss", "https://login.example.com")
        .claim("sub", subject)
        .claim("aud", List.of("orders-api"))
        .claim("scope", scope)
        .claim("tenant_id", tenantId)
        .issuedAt(now.minusSeconds(30))
        .expiresAt(now.plusSeconds(300))
        .build();
}
```

Using the helper:

```java
mvc.perform(get("/api/orders")
        .with(jwt().jwt(jwtFor("alice", "orders.read", "tenant-a"))))
    .andExpect(status().isOk());

mvc.perform(post("/api/orders")
        .with(jwt().jwt(jwtFor("alice", "orders.read", "tenant-a"))))
    .andExpect(status().isForbidden());
```

Both requests have the same identity/scope, but only GET is allowed by the rule. Create a separate object per test or use immutable builders; avoid mutable singleton test fixtures.
## 4. Claims and authorities: where do they differ?

**Claims** are data inside the access token. **Authorities** are the permissions Spring Security uses to make authorization decisions. Some claims are mapped by a converter into authorities, but not every claim automatically becomes a permission.

Example:

```json
{
  "sub": "alice",
  "scope": "orders.read orders.write",
  "roles": ["SUPPORT"],
  "tenant_id": "tenant-a"
}
```

Interpretation:

- `sub` identifies the subject.
- `scope` represents OAuth scopes.
- `roles` is a custom claim defined by the issuer/application contract.
- `tenant_id` is tenant data checked by application/domain policy.

Spring Security's default JWT authority converter normally reads the scope claim (`scope` or `scp`) and produces authorities prefixed with `SCOPE_`. For example, `orders.read` becomes `SCOPE_orders.read`.

The `roles` claim does not automatically become `ROLE_SUPPORT` unless the application configures a corresponding converter.

### 4.1. Scope claim

Token example:

```json
{
  "scope": "orders.read orders.write"
}
```

With the default `JwtGrantedAuthoritiesConverter`, scope values are mapped to:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Therefore, the authorization rule `hasAuthority("SCOPE_orders.read")` requires the exact prefix and exact scope name.

### 4.2. scp claim

Some issuers use the `scp` claim, often as a collection:

```json
{
  "scp": ["orders.read", "orders.write"]
}
```

Spring Security supports common scope conventions by default; if the issuer uses a different schema, configure `JwtGrantedAuthoritiesConverter` and test the mapping explicitly.

Do not assume every issuer uses the same claim name or format.

### 4.3. Role claim

A token may contain:

```json
{
  "roles": ["SUPPORT", "AUDITOR"]
}
```

This is an application claim. To map it to `ROLE_SUPPORT` and `ROLE_AUDITOR`, configure a custom converter. Do not confuse `hasRole("SUPPORT")` with `hasAuthority("SUPPORT")`: `hasRole` adds the `ROLE_` prefix by default.

### 4.4. Tenant claims are not authorities by default

Example:

```json
{
  "tenant_id": "tenant-a"
}
```

This claim does not automatically create an authority. It is typically used to check tenant context or domain authorization. Do not turn every tenant ID into a role if doing so bloats permissions or makes them hard to manage.

## 5. Creating authorities directly with jwt().authorities(...)

When a test only needs to check authorization against a specific set of permissions, you can specify authorities directly:

```java
mvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )))
    .andExpect(status().isOk());
```

Multiple authorities:

```java
mvc.perform(get("/api/admin/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"),
            new SimpleGrantedAuthority("ROLE_AUDITOR")
        )))
    .andExpect(status().isOk());
```

When specifying `authorities(...)`, the test supplies authorities directly to the authentication instead of relying on the default converter to derive them from claims. This is a good way to isolate authorization rules, though it does not test claim-to-authority mapping.

### 5.1. Use claims when testing token data

Tenant test example:

```java
mvc.perform(get("/api/tenants/tenant-a/orders")
        .with(jwt().jwt(jwt -> jwt
            .subject("alice")
            .claim("scope", "orders.read")
            .claim("tenant_id", "tenant-a")
        )))
    .andExpect(status().isOk());
```

The needed claims are kept on the Jwt principal for the controller, argument resolver, or domain service to read.

### 5.2. Use authorities when testing a permission rule

```java
mvc.perform(post("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.write")
        )))
    .andExpect(status().isCreated());
```

This test focuses on whether the endpoint requires the right authority. It does not prove the issuer actually grants that scope or that the converter maps the scope claim accurately.

### 5.3. Do not put authorities into a claim and expect Spring to understand automatically

Token example:

```json
{
  "authorities": ["ROLE_ADMIN"]
}
```

The default converter does not necessarily read a claim named `authorities`. If the application uses this claim, a custom converter must be configured. If a test uses `jwt().authorities(...)`, the authorities are attached directly and can make the test pass even when production claim mapping is broken.

## 6. JwtAuthenticationToken and principal

`jwt()` creates a JWT-based authentication. In a controller, you can receive:

```java
@GetMapping("/api/orders")
public List<Order> orders(
        @AuthenticationPrincipal Jwt jwt) {
    String subject = jwt.getSubject();
    String tenantId = jwt.getClaimAsString("tenant_id");

    return orderService.findOrders(subject, tenantId);
}
```

Or receive Authentication:

```java
@GetMapping("/api/current-user")
public Map<String, Object> currentUser(Authentication authentication) {
    JwtAuthenticationToken jwtAuthentication =
        (JwtAuthenticationToken) authentication;

    Jwt jwt = jwtAuthentication.getToken();

    return Map.of(
        "subject", jwt.getSubject(),
        "authorities", jwtAuthentication.getAuthorities()
    );
}
```

In the test:

```java
mvc.perform(get("/api/current-user")
        .with(jwt().jwt(jwt -> jwt
            .subject("alice")
            .claim("tenant_id", "tenant-a")
            .claim("scope", "orders.read")
        )))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.subject").value("alice"));
```

The default principal name of `JwtAuthenticationToken` is normally taken from the `sub` claim. If the application configures a different principal claim, test the corresponding converter/configuration.

### 6.1. Checking claims in the controller

If the controller uses `@AuthenticationPrincipal Jwt`, tests can confirm claims are read correctly. However, do not let controllers make sensitive authorization decisions solely on unverified claims; in tests the `jwt()` object is built directly, whereas in production it must go through the decoder.

### 6.2. Only check authorities in the response when that is the contract

Do not expose all JWT claims/authorities in an API response just for testing. If a user-info endpoint is an intentional API contract, return only allowed fields. Otherwise, testing authorization via status codes/side effects is enough.

## 7. Testing hasAuthority and hasAnyAuthority

Security configuration:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .requestMatchers("/api/reports/**")
        .hasAnyAuthority(
            "SCOPE_reports.read",
            "ROLE_AUDITOR"
        )
    .anyRequest().authenticated()
)
```

Tests:

```java
@Test
void readerCanReadOrders() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isOk());
}

@Test
void readerCannotCreateOrders() throws Exception {
    mvc.perform(post("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isForbidden());
}

@Test
void auditorCanReadReports() throws Exception {
    mvc.perform(get("/api/reports")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("ROLE_AUDITOR")
            )))
        .andExpect(status().isOk());
}
```

### 7.1. hasRole and the ROLE_ prefix

`hasRole("ADMIN")` is normally equivalent to checking the authority `ROLE_ADMIN`. Example:

```java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

Test:

```java
mvc.perform(get("/api/admin/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("ROLE_ADMIN")
        )))
    .andExpect(status().isOk());
```

Do not pass `new SimpleGrantedAuthority("ADMIN")` and expect `hasRole("ADMIN")` to accept it automatically. If using `hasAuthority("ROLE_ADMIN")`, pass that exact authority string.

### 7.2. Testing missing authorities

A valid JWT authentication without the matching authority usually results in 403 on an endpoint requiring permission. This differs from an unauthenticated request, which usually receives 401 when the endpoint requires authentication.

```java
mvc.perform(get("/api/orders")
        .with(jwt().authorities(List.of())))
    .andExpect(status().isForbidden());
```

If the API configures a custom entry point/access denied handler, the response body may differ; status codes and security semantics must still match the contract.

## 8. Testing claims and domain authorization

Not every decision should be represented as an authority. Tenant, resource owner, account state, and business relationships often require domain checks.

Example of a controller/service reading the tenant claim:

```java
@GetMapping("/api/tenants/{tenantId}/orders")
public List<Order> tenantOrders(
        @PathVariable String tenantId,
        @AuthenticationPrincipal Jwt jwt) {

    String tokenTenant = jwt.getClaimAsString("tenant_id");

    if (!tenantId.equals(tokenTenant)) {
        throw new AccessDeniedException("Tenant mismatch");
    }

    return orderService.findByTenant(tenantId);
}
```

Test matching tenant:

```java
mvc.perform(get("/api/tenants/tenant-a/orders")
        .with(jwt().jwt(jwt -> jwt
            .subject("alice")
            .claim("scope", "orders.read")
            .claim("tenant_id", "tenant-a")
        )))
    .andExpect(status().isOk());
```

Test mismatched tenant:

```java
mvc.perform(get("/api/tenants/tenant-b/orders")
        .with(jwt().jwt(jwt -> jwt
            .subject("alice")
            .claim("scope", "orders.read")
            .claim("tenant_id", "tenant-a")
        )))
    .andExpect(status().isForbidden());
```

This is a domain policy test using claims from Jwt authentication. If the tenant policy lives in the service layer or method security, place tests at that boundary and verify the controller performs no side effects on tenant mismatch.

### 8.1. Ownership based on sub

Example of a user-owned resource:

```java
@PreAuthorize("@orderAuthorization.canRead(#orderId, authentication)")
public Order findOrder(String orderId) {
    return orderRepository.findById(orderId)
        .orElseThrow();
}
```

In the test, change the subject:

```java
mvc.perform(get("/api/orders/order-42")
        .with(jwt().jwt(jwt -> jwt
            .subject("alice")
            .claim("scope", "orders.read")
        )))
    .andExpect(status().isOk());
```

Then use a different subject to confirm the policy rejects it. Do not test only scope if actual access also depends on the owner.

### 8.2. Missing or wrongly typed claims

If the application requires `tenant_id`, test tokens missing the claim as well as claims with wrong types/null. Do not assume the claim is always present just because the test helper lets you construct arbitrary Jwts.

Example:

```java
mvc.perform(get("/api/tenants/tenant-a/orders")
        .with(jwt().jwt(jwt -> jwt
            .subject("alice")
            .claim("scope", "orders.read")
        )))
    .andExpect(status().isForbidden());
```

Domain policies should fail closed when required tenant data is missing or invalid.

## 9. Using jwt() with @PreAuthorize and method security

If the application uses method security:

```java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

Service:

```java
@Service
public class OrderQueryService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public List<Order> findOrders() {
        return List.of();
    }

    @PreAuthorize("hasRole('SUPPORT')")
    public Order supportView(String orderId) {
        return new Order(orderId);
    }
}
```

MockMvc test with `jwt()`:

```java
@Test
void methodSecurityAllowsReader() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isOk());
}

@Test
void methodSecurityRejectsMissingAuthority() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(List.of())))
        .andExpect(status().isForbidden());
}
```

### 9.1. MockMvc must call through a Spring-managed proxy

Method security relies on Spring AOP proxies. If a test instantiates the service manually with `new OrderQueryService()`, annotations may not be enforced. Use the Spring context and inject the managed bean.

### 9.2. Testing methods directly when needed

You can test service methods with Spring Security Test annotations or appropriate context setup, but testing a method directly does not prove the filter chain authenticated the request. Split tests by boundary:

- Unit tests for domain authorization logic.
- Method-security integration tests through the Spring proxy.
- MockMvc tests for routes/filter chains.
## 10. How do jwt() and @WithMockUser differ?

Spring Security Test has `@WithMockUser` to create mock authentication with username/roles. However, when the application expects a JWT, `jwt()` is usually a better fit because the principal is a Jwt and has claims.

| Aspect | `@WithMockUser` | `jwt()` |
|---|---|---|
| Principal | UserDetails-like principal | Jwt |
| Authentication | Username/password style mock authentication | JwtAuthenticationToken |
| Claims | No JWT claims | Can build claims |
| Subject | Username | `sub` claim |
| Authorities | Roles/authorities configured via annotation | Can be mapped from scope claim or set directly |
| Useful for | General user authorization | JWT Resource Server, claims, scope, Jwt principal |
| Verifies JWT signature | No | No |
| Runs JwtDecoder | No | No |

`@WithMockUser` example:

```java
@Test
@WithMockUser(username = "alice", roles = "SUPPORT")
void supportEndpointAllowsSupportUser() throws Exception {
    mvc.perform(get("/api/support"))
        .andExpect(status().isOk());
}
```

`jwt()` example:

```java
@Test
void supportEndpointAllowsJwtSupportAuthority() throws Exception {
    mvc.perform(get("/api/support")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("ROLE_SUPPORT")
            )))
        .andExpect(status().isOk());
}
```

The two tests are not completely equivalent if the controller injects `Jwt` or the application reads claims. Use `jwt()` for tests requiring a JWT principal.

## 11. Testing scope-to-authority mapping

When authorities are not specified directly, `jwt()` uses the test helper's JWT authentication converter to map the scope claim.

Example:

```java
mvc.perform(get("/api/orders")
        .with(jwt().jwt(jwt -> jwt
            .claim("scope", "orders.read orders.write")
        )))
    .andExpect(status().isOk());
```

The default converter normally produces:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Thus `hasAuthority("SCOPE_orders.read")` will match the corresponding scope claim.

### 11.1. Why test both mapping and authorization?

A test using `jwt().authorities(...)` can prove authorization rules work, but skips the converter. A test using `jwt().jwt(...)` with a scope claim can check the default mapping path used by the request postprocessor.

However, neither proves the production converter is wired properly into `oauth2ResourceServer().jwt()` when real token headers are used. To test real wiring, send an Authorization header and let the filter chain build the authentication.

### 11.2. List-formatted scope claims

If the issuer sends `scp` as an array, write a matching test:

```java
mvc.perform(get("/api/orders")
        .with(jwt().jwt(jwt -> jwt
            .claim("scp", List.of("orders.read", "orders.write"))
        )))
    .andExpect(status().isOk());
```

Ensure the claim format matches the converter in use. Do not assume lists, space-delimited strings, and nested objects are handled identically.

## 12. Custom JwtGrantedAuthoritiesConverter for a roles claim

Suppose the Authorization Server issues:

```json
{
  "sub": "alice",
  "scope": "orders.read",
  "roles": ["SUPPORT", "AUDITOR"]
}
```

The application wants to map roles to `ROLE_...`:

```java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter scopes =
        new JwtGrantedAuthoritiesConverter();

    JwtGrantedAuthoritiesConverter roles =
        new JwtGrantedAuthoritiesConverter();

    roles.setAuthoritiesClaimName("roles");
    roles.setAuthorityPrefix("ROLE_");

    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();

    converter.setJwtGrantedAuthoritiesConverter(jwt -> {
        Collection<GrantedAuthority> authorities =
            new ArrayList<>(scopes.convert(jwt));

        authorities.addAll(roles.convert(jwt));
        return authorities;
    });

    return converter;
}
```

In the Resource Server configuration:

```java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt
        .jwtAuthenticationConverter(jwtAuthenticationConverter())
    )
)
```

This is an example converter for a roles claim shaped as a collection of strings. In real projects, you may need a custom converter to validate claim types, reject invalid values, handle nested roles, or avoid duplicate mappings.

### 12.1. Unit testing the converter directly

```java
@Test
void mapsScopesAndRoles() {
    Jwt jwt = Jwt.withTokenValue("test-token")
        .header("alg", "none")
        .claim("sub", "alice")
        .claim("scope", "orders.read")
        .claim("roles", List.of("SUPPORT", "AUDITOR"))
        .build();

    JwtAuthenticationConverter converter =
        jwtAuthenticationConverter();

    AbstractAuthenticationToken authentication =
        converter.convert(jwt);

    assertThat(authentication.getAuthorities())
        .extracting(GrantedAuthority::getAuthority)
        .contains(
            "SCOPE_orders.read",
            "ROLE_SUPPORT",
            "ROLE_AUDITOR"
        );
}
```

This test verifies the converter logic. It does not prove the converter is attached to the Resource Server filter chain. Add an integration test with a real Bearer header to verify wiring.

### 12.2. jwt().authorities(...) bypasses claim mapping

If you write:

```java
.with(jwt().authorities(
    new SimpleGrantedAuthority("ROLE_SUPPORT")
))
```

the test has provided the authority directly. It does not verify that the `roles` claim is mapped by the converter. When the goal is to test mapping, use Jwt claims and the real converter or unit test the converter.

### 12.3. Custom principal claim

If the application configures a principal claim name other than `sub`, tests must check `Authentication.getName()` and the principal according to the converter. Do not just change the claim in Jwt and assume Spring picks that claim automatically.

## 13. Creating a Jwt with intentional headers and claims

`Jwt` stores both JOSE headers and claims. Example:

```java
Jwt jwt = Jwt.withTokenValue("test-token")
    .header("alg", "RS256")
    .header("kid", "test-signing-key")
    .claim("iss", "https://login.example.com")
    .claim("sub", "alice")
    .claim("aud", List.of("orders-api"))
    .claim("scope", "orders.read")
    .claim("tenant_id", "tenant-a")
    .claim("client_id", "orders-frontend")
    .claim("azp", "orders-frontend")
    .claim("token_use", "access")
    .issuedAt(Instant.parse("2030-01-01T10:00:00Z"))
    .expiresAt(Instant.parse("2030-01-01T10:10:00Z"))
    .build();
```

Notes:

- `alg` and `kid` here are just data inside the test Jwt object.
- Setting `alg=RS256` does not sign the token.
- `iss`, `aud`, and `exp` in the test object are not checked by the decoder if the request uses the `jwt()` postprocessor.
- Custom claims only have meaning to code/converters that read them.
- Do not use production private keys or tokens in test fixtures.

### 13.1. Numeric and boolean claims

If the application reads typed claims, create them with the right types:

```java
.claim("account_verified", true)
.claim("risk_score", 12)
.claim("permissions_version", 3L)
```

Do not use the string `"true"` if the code expects a Boolean, or `"12"` if the code expects a Number. Tests should reflect real JSON claim types.

### 13.2. Nested object claims

Example:

```java
.claim("tenant", Map.of(
    "id", "tenant-a",
    "region", "ap-southeast-1"
))
```

When reading nested claims, check for null/type and do not assume every issuer token provides the full object.

### 13.3. Do not put sensitive data in fixtures

Use mock subjects and tenants. Do not copy real access tokens, real emails, client secrets, or production data into test source code, test reports, or snapshots.

## 14. Testing 401, 403, and permitAll

Distinguish between:

- **401 Unauthorized:** request lacks valid Authentication for an endpoint requiring login.
- **403 Forbidden:** request is authenticated, but lacks the authority or is denied by authorization/domain policy.
- **permitAll:** endpoint allows anonymous access; no JWT required.

### 14.1. Anonymous requests receive 401

```java
@Test
void anonymousCannotReadOrders() throws Exception {
    mvc.perform(get("/api/orders"))
        .andExpect(status().isUnauthorized());
}
```

The result depends on the protected endpoint and configured entry point. For a Bearer Resource Server, also check `WWW-Authenticate` if that is part of the API contract.

### 14.2. Authenticated but missing scope receives 403

```java
@Test
void authenticatedWithoutReadScopeIsForbidden() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(List.of())))
        .andExpect(status().isForbidden());
}
```

### 14.3. Authenticated with scope is allowed

```java
@Test
void readerCanReadOrders() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isOk());
}
```

### 14.4. Public endpoints do not need jwt()

```java
@Test
void publicEndpointAllowsAnonymous() throws Exception {
    mvc.perform(get("/api/public/catalog"))
        .andExpect(status().isOk());
}
```

Do not attach `jwt()` to every test out of habit. An anonymous test is useful to prove public/protected endpoints and the authentication entry point behave properly.

## 15. Testing real Authorization headers: when is JwtDecoder needed?

If the goal is to verify that `BearerTokenAuthenticationFilter`, `BearerTokenResolver`, `JwtDecoder`, and the production converter work together, send the header:

```http
Authorization: Bearer test-token
```

In the test, replace the decoder with a controlled mock:

```java
@SpringBootTest
@AutoConfigureMockMvc
class BearerAuthenticationPipelineTests {

    @Autowired
    MockMvc mvc;

    @MockBean
    JwtDecoder jwtDecoder;

    @Test
    void authenticatesBearerHeaderUsingConfiguredDecoder()
            throws Exception {

        Jwt jwt = Jwt.withTokenValue("test-token")
            .header("alg", "none")
            .claim("sub", "alice")
            .claim("scope", "orders.read")
            .build();

        given(jwtDecoder.decode("test-token")).willReturn(jwt);

        mvc.perform(get("/api/orders")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    "Bearer test-token"
                ))
            .andExpect(status().isOk());

        then(jwtDecoder).should().decode("test-token");
    }
}
```

This is an integration test for the Bearer authentication path with a mock decoder. Because `JwtDecoder` is mocked, the test does not verify cryptographic signatures or real validators; it verifies the request goes through the pipeline and the decoder is called.

`@MockBean` is used in many Spring Boot 3.x versions; in newer Spring Framework/Boot versions, you can use the corresponding mock bean annotation such as `@MockitoBean`. Choose the annotation supported by your project version.

### 15.1. Verifying the production converter is called

If you configure a custom `JwtAuthenticationConverter`, test with a real Authorization header and have the decoder return a Jwt with scope/roles claims. Then verify the endpoint is allowed/denied according to the authorities produced by the converter.

If a test uses `jwt().authorities(...)`, it bypasses the converter and does not verify this wiring.

### 15.2. Testing real issuer/audience/expiry validators

Use `NimbusJwtDecoder` with a test public key/JWK set or a test Authorization Server/JWKS fixture. Sign tokens with a test private key and send a real Authorization header.

Test separately:

- Valid and invalid signatures.
- Valid and invalid issuers.
- Valid and invalid audiences.
- Expired `exp`.
- Future `nbf`.
- Allowed algorithms.
- Custom claim validators.
- Token profile or token type if required by the application.

Do not use `jwt()` to conclude the validators above work, because the postprocessor creates authentication directly.

## 16. Testing claim mapping and authorization by layer

A test suite can be organized into:

| Layer | Test | Data |
|---|---|---|
| Jwt builder/helper | Build properly typed claims | `sub`, `scope`, `tenant_id` |
| Authorities converter | Scope/roles → authorities | `scope`, `roles` |
| Security filter chain | URL rules | `SCOPE_orders.read` |
| Method security | `@PreAuthorize` | Authorities |
| Domain policy | Tenant/owner | `tenant_id`, `sub` |
| JWT authentication pipeline | Header → decoder → converter | Bearer header |
| JWT validation | Signature/issuer/audience/time | Signed test JWT |

### 16.1. Do not combine everything into one giant test

A single test that boots the app, mocks the AS, mocks the database, builds a JWT, calls an endpoint, and asserts everything can be hard to diagnose when it fails. Split tests by responsibility so you know whether the bug is in the token fixture, converter, authentication, URL authorization, method authorization, or domain policy.

### 16.2. Still include some integration tests

Unit testing a converter alone does not prove the Resource Server configuration uses that converter. Unit testing service authorization alone does not prove the filter chain protects the endpoint. Therefore, you still need a few MockMvc integration tests with real security filters.

## 17. Helper methods for readable tests

A helper can encapsulate scopes and claims:

```java
private RequestPostProcessor jwtReader(String subject) {
    return jwt().jwt(jwt -> jwt
        .subject(subject)
        .claim("scope", "orders.read")
        .claim("tenant_id", "tenant-a")
    );
}

private RequestPostProcessor jwtWriter(String subject) {
    return jwt().jwt(jwt -> jwt
        .subject(subject)
        .claim("scope", "orders.write")
        .claim("tenant_id", "tenant-a")
    );
}
```

Usage:

```java
mvc.perform(get("/api/orders").with(jwtReader("alice")))
    .andExpect(status().isOk());

mvc.perform(post("/api/orders").with(jwtReader("alice")))
    .andExpect(status().isForbidden());

mvc.perform(post("/api/orders").with(jwtWriter("alice")))
    .andExpect(status().isCreated());
```

### 17.1. Helper for direct authorities

```java
private RequestPostProcessor authenticatedWith(
        String... authorities) {

    List<GrantedAuthority> grantedAuthorities =
        Arrays.stream(authorities)
            .map(SimpleGrantedAuthority::new)
            .toList();

    return jwt().authorities(grantedAuthorities);
}
```

If an API version only exposes the corresponding varargs or collection overload, adjust the helper according to your project version's Javadoc. Avoid helpers that obscure the difference between claims and authorities.

### 17.2. Avoid overly generic helpers

Do not create helpers with dozens of nullable parameters. Such helpers make tests hard to read and can easily produce invalid combinations. Create small builders per persona/use case: reader, writer, support agent, cross-tenant actor.

## 18. Testing with @AuthenticationPrincipal Jwt

Controller:

```java
@GetMapping("/api/current-tenant")
public String currentTenant(
        @AuthenticationPrincipal Jwt jwt) {
    return jwt.getClaimAsString("tenant_id");
}
```

Test:

```java
mvc.perform(get("/api/current-tenant")
        .with(jwt().jwt(jwt -> jwt
            .subject("alice")
            .claim("tenant_id", "tenant-a")
        )))
    .andExpect(status().isOk())
    .andExpect(content().string("tenant-a"));
```

If the controller uses a custom argument resolver or principal claim mapping, test accordingly. Do not use `@WithMockUser` for this test because the principal is not a Jwt.

## 19. Testing failures when claims are missing or invalid

A JWT may be authenticated yet missing a claim expected by the application. Test these cases:

- Missing `sub` if required by the domain.
- Missing `tenant_id`.
- `tenant_id` is an object instead of a string.
- `roles` is a string instead of a collection.
- `scope` is a list while the converter expects a string, or vice versa.
- `aud` missing downstream resource.
- Claim contains a tenant that does not exist or does not belong to the actor.

Example of wrongly typed tenant claim:

```java
mvc.perform(get("/api/current-tenant")
        .with(jwt().jwt(jwt -> jwt
            .subject("alice")
            .claim("tenant_id", List.of("tenant-a", "tenant-b"))
        )))
    .andExpect(status().isForbidden());
```

Controllers/services should handle unexpected data types safely. Do not cast blindly or return 500 because of a malformed claim.

## 20. Testing authority prefixes and scope names

| Converter produces | Rule checks | Result |
|---|---|---|
| `SCOPE_orders.read` | `hasAuthority("SCOPE_orders.read")` | Match |
| `SCOPE_orders.read` | `hasAuthority("orders.read")` | No match |
| `ROLE_SUPPORT` | `hasRole("SUPPORT")` | Match |
| `ROLE_SUPPORT` | `hasAuthority("SUPPORT")` | No match |
| `ROLE_SUPPORT` | `hasAuthority("ROLE_SUPPORT")` | Match |

Tests should assert exact prefixes. Do not change the prefix in a test helper to make tests pass while the production converter is still wrong.

## 21. Testing multiple security chains or multiple endpoint types

An application may have chains for API Bearer, web sessions, and public endpoints. `jwt()` tests should send requests to real URLs so the chain matcher is selected properly.

Example:

```java
@Test
void apiRouteUsesBearerAuthorizationRules() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isOk());
}

@Test
void webRouteUsesItsOwnAuthenticationMechanism() throws Exception {
    mvc.perform(get("/web/profile"))
        .andExpect(status().is3xxRedirection());
}
```

The second test is only appropriate if the web chain actually configures a login redirect. The point is to verify each route is handled by the right chain, rather than attaching JWT test authentication to every URL.

## 22. Important limitations of jwt()

### 22.1. Does not verify signatures

The Jwt object is constructed directly without cryptographic verification. Use signed tokens and a real decoder test when needed.

### 22.2. Does not run JwtDecoder

The request postprocessor installs JWT authentication into the test request. It does not check whether `JwtDecoder` is properly configured or whether the JWKS endpoint works.

### 22.3. Does not prove the Bearer header parser works

To test `Authorization: Bearer`, send a real header. `jwt()` does not test `DefaultBearerTokenResolver` or a custom `BearerTokenResolver`.

### 22.4. Does not test issuer/audience/time validators

Claims in a test Jwt are not validated automatically. Validators must be tested separately through the decoder pipeline.

### 22.5. Does not automatically test production converter mapping

If you specify `jwt().authorities(...)`, authorities are supplied directly. If you use `jwt().jwt(...)`, the postprocessor uses the test helper's converter; it is not necessarily the converter configured in the Resource Server.

### 22.6. Does not test token revocation/introspection

For opaque tokens, test `OpaqueTokenIntrospector` and the `active` response; `jwt()` creates JWT authentication so it does not test introspection.

### 22.7. Does not test DPoP/mTLS proof-of-possession

`jwt()` does not create DPoP proofs, compare `cnf.jkt`, or check certificate binding. Those parts require dedicated integration tests.

## 23. Example of a complete MockMvc test class

```java
package com.example.orders;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersAuthorizationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void readerCanReadOrders() throws Exception {
        mvc.perform(get("/api/orders")
                .with(jwt().jwt(jwt -> jwt
                    .subject("alice")
                    .claim("scope", "orders.read")
                    .claim("tenant_id", "tenant-a")
                )))
            .andExpect(status().isOk());
    }

    @Test
    void readerCannotWriteOrders() throws Exception {
        mvc.perform(post("/api/orders")
                .with(jwt().jwt(jwt -> jwt
                    .subject("alice")
                    .claim("scope", "orders.read")
                    .claim("tenant_id", "tenant-a")
                )))
            .andExpect(status().isForbidden());
    }

    @Test
    void writerCanWriteOrders() throws Exception {
        mvc.perform(post("/api/orders")
                .with(jwt().jwt(jwt -> jwt
                    .subject("alice")
                    .claim("scope", "orders.write")
                    .claim("tenant_id", "tenant-a")
                )))
            .andExpect(status().isCreated());
    }

    @Test
    void explicitAuthorityCanBeUsedForFocusedAuthorizationTest()
            throws Exception {
        mvc.perform(get("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read")
                )))
            .andExpect(status().isOk());
    }

    @Test
    void anonymousRequestIsUnauthorized() throws Exception {
        mvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }
}
```

This class illustrates how to write tests. To run in a project, you need the corresponding endpoints, security configuration, decoder bean, and dependencies. The anonymous test depends on the endpoint requiring authentication; the writer test depends on the controller/service returning 201 on success.

## 24. Common mistakes

1. **Using `jwt()` and concluding JWT signatures were tested.** The postprocessor creates authentication directly.
2. **Using `jwt().authorities(...)` to test scope mapping.** Authorities are explicitly specified; the claim converter may be bypassed.
3. **Putting a `roles` claim into Jwt and assuming the default converter maps it automatically.** A custom converter is required if the issuer uses a custom schema.
4. **Confusing `hasRole("ADMIN")` with `hasAuthority("ADMIN")`.** The default role prefix is `ROLE_`.
5. **Not setting the scope claim explicitly.** Relying on defaults makes tests hard to understand and implementation/version-dependent.
6. **Using `@WithMockUser` when the controller expects a Jwt principal.** The principal is not a Jwt.
7. **Testing the converter alone without testing wiring.** The converter might be correct yet not attached to the Resource Server.
8. **Having no anonymous tests.** Endpoints could accidentally be left open.
9. **Not distinguishing 401 and 403.** Missing authentication differs from being authenticated without permissions.
10. **Using the tenant claim as an authority.** Tenant context usually requires domain authorization.
11. **Creating a Jwt with wrong issuer/audience and expecting `jwt()` to return 401.** The request postprocessor does not run validators.
12. **Sending a Bearer header without configuring a mock decoder.** The pipeline will not succeed in authenticating the token.
13. **Using production tokens/claims in tests.** Creates credential/PII exposure risks.
14. **Using helpers that generate too many arbitrary combinations.** Tests become hard to read and may not reflect the token contract.

## 25. Workflow for choosing a testing approach

| Goal | Appropriate test approach |
|---|---|
| Which scopes does an endpoint allow? | `jwt().authorities(...)` or `jwt().jwt(...)` |
| Are `sub`/`tenant_id` claims read properly? | `jwt().jwt(...)` with specific claims |
| Does the scope claim map to `SCOPE_...`? | `jwt().jwt(...)` with scope claim; add converter unit test |
| Does a custom roles claim map properly? | Unit test custom converter and integration with Bearer header |
| Does the controller receive `@AuthenticationPrincipal Jwt`? | `jwt().jwt(...)` |
| `@PreAuthorize` by authority? | MockMvc `jwt()` through Spring proxy/filter chain |
| Does anonymous get 401? | MockMvc request without postprocessor |
| Does missing authority get 403? | `jwt()` with empty/mismatching authorities |
| Is the Bearer header parsed? | Real Authorization header |
| Is JwtDecoder called? | Real Authorization header and mock/spy decoder |
| Are signature/issuer/audience/expiry validated? | Signed test JWT and real decoder/validators |
| Opaque introspection? | Mock/test introspector, do not use `jwt()` |
| DPoP proof/key binding? | DPoP-specific integration tests |

## 26. Checklist for JWT authorization tests

- [ ] Use `jwt()` when the goal is JWT-backed authentication in MockMvc.
- [ ] Explicitly declare `sub` and required claims.
- [ ] Distinguish claims from authorities.
- [ ] Use the `SCOPE_` prefix properly for OAuth scopes.
- [ ] Use the `ROLE_` prefix properly for roles.
- [ ] Use `jwt().authorities(...)` only when setting permissions directly.
- [ ] Test scope mapping separately if it is an important contract.
- [ ] Test tenant/owner claims at the domain boundary.
- [ ] Include an anonymous 401 test.
- [ ] Include an authenticated-but-missing-permissions 403 test.
- [ ] Include success tests for each required authority.
- [ ] Test method security through a Spring-managed proxy.
- [ ] Use a real Bearer header when testing filter/decoder/converter wiring.
- [ ] Use signed test tokens and a real decoder when testing cryptographic validation.
- [ ] Do not use `jwt()` to conclude issuer/audience/expiry/JWKS/revocation work.
- [ ] Do not use production access tokens or sensitive data in fixtures.

## 27. References

- [Spring Security — Testing OAuth 2.0](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): MockMvc support, `jwt()`, and OAuth2 test request postprocessors.
- [Spring Security — MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): integrating the Spring Security filter chain with MockMvc.
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT authentication, decoder, and authority mapping.
- [Spring Security API — Jwt](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/Jwt.html): creating and accessing Jwt headers/claims.
- [Spring Security API — JwtGrantedAuthoritiesConverter](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html): scope/authority conversion.
- [Spring Security API — JwtAuthenticationConverter](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html): converting Jwt to JwtAuthenticationToken.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize` and method authorization.
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html): testing method security with Spring Security Test.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access token claims and validation profile.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer token presentation and error semantics.

**Conclusion:** `jwt()` is a MockMvc tool for creating JWT-backed Authentication and focusing on authorization testing. Use `jwt().jwt(...)` when you need control over subject/claims and want the test helper to map scopes; use `jwt().authorities(...)` when you want to test a specific set of permissions directly. Claims like `sub`, `scope`, `roles`, and `tenant_id` serve different roles; authority mapping must match the production converter. When you need to verify Bearer headers, JwtDecoder, signatures, issuer, audience, or expiration, send real headers and test the decoder/validators separately. Clearly separating authorization tests from authentication tests ensures test results reflect the exact security layer the application needs to protect.

