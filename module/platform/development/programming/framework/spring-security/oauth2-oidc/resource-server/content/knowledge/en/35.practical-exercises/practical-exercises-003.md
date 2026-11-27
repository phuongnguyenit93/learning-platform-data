# Mapping Scopes and Roles and Protecting Read/Write Operations by HTTP Method

A **Spring Security OAuth 2.0 Resource Server** needs to convert permissions present in an access token into authorities that Spring Security understands, then use those authorities to decide which requests are allowed to read, create, modify, or delete resources. This practical exercise builds a consistent policy: scopes represent API access permissions by action, roles represent broader groups of responsibility, and the HTTP method specifies the operation being requested.

Example order management API:

| HTTP method | Endpoint | Required permission |
|---|---|---|
| GET | /api/orders or /api/orders/{id} | SCOPE_orders.read |
| POST | /api/orders | SCOPE_orders.write |
| PUT | /api/orders/{id} | SCOPE_orders.write |
| PATCH | /api/orders/{id} | SCOPE_orders.write |
| DELETE | /api/orders/{id} | ROLE_ORDER_ADMIN |

An access token might contain:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "roles": ["ORDER_OPERATOR"],
  "exp": 1893459600
}
~~~

Spring Security maps `scope` to `SCOPE_...` by default. The `roles` claim is a custom claim defined by the issuer's contract, so the application needs a converter to map it to `ROLE_...`. Once authorities are populated, request authorization can inspect a combination of HTTP method and path.

> **Design principle:** scopes should grant specific API/action permissions; roles should describe broader responsibilities. Grant only the exact authorities required, and place HTTP-method-specific rules before general path rules.

## 1. Understanding Scopes, Roles, and Authorities

### 1.1. Scope

An OAuth scope is a permission string requested by a client and granted by the Authorization Server per policy. For the orders API, the issuer might emit:

~~~text
orders.read
orders.write
~~~

The exact meaning is agreed upon by the API and the issuer. An easy-to-follow convention is:

- `orders.read` allows reading orders.
- `orders.write` allows creating or updating orders.
- `orders.cancel` if business rules require a separate cancellation permission.

Scopes should have a clear boundary; avoid overly broad scopes like `admin` if the API can separate specific actions.

### 1.2. Role

A role describes a responsibility or user group:

~~~text
ORDER_OPERATOR
ORDER_ADMIN
SUPPORT_AGENT
~~~

A role is usually broader than a single scope. For example, `ORDER_ADMIN` might be allowed to delete orders; `ORDER_OPERATOR` might be allowed to create and update them. Do not implicitly infer all permissions from a role name. Explicitly define which roles map to which authorities, and at which layer.

### 1.3. Authority

Spring Security checks `GrantedAuthority`. Authority strings are the values the application uses in expressions:

~~~text
SCOPE_orders.read
SCOPE_orders.write
ROLE_ORDER_ADMIN
ROLE_ORDER_OPERATOR
~~~

Prefixes are an important convention:

- `hasAuthority("SCOPE_orders.read")` matches the exact authority string.
- `hasRole("ORDER_ADMIN")` checks for the `ROLE_ORDER_ADMIN` authority by default.
- `hasAuthority("ROLE_ORDER_ADMIN")` also checks that exact string.

`hasRole("ROLE_ORDER_ADMIN")` is usually a convention mistake because Spring automatically prepends `ROLE_`; pass the unprefixed role name to `hasRole`, or use `hasAuthority` with the full string.

### 1.4. Scopes Are Not Automatically Roles

Do not mix the two permission types into one namespace:

~~~text
orders.read       -> SCOPE_orders.read
ORDER_ADMIN       -> ROLE_ORDER_ADMIN
~~~

This keeps policies readable and prevents a scope from accidentally satisfying a role check or vice versa.

## 2. Agreeing on Claims Between Authorization Server and Resource Server

Before writing a converter, agree on the access token schema:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "roles": ["ORDER_OPERATOR"],
  "exp": 1893459600
}
~~~

Decisions to clarify:

| Claim | Contract to agree on |
|---|---|
| scope | Space-delimited scope string or an array |
| scp | Whether it is used instead of `scope` |
| roles | Array of roles or string; whether roles include a prefix or not |
| aud | Resource Server identifier |
| iss | Exact issuer trusted by the Resource Server |
| sub | User or service subject; uniqueness within the issuer's scope |

By default, Spring Security can read scopes from the common `scope` or `scp` claim and add the `SCOPE_` prefix. If the issuer uses a different claim such as `permissions`, configure a converter explicitly. Do not guess the schema from a single environment's token.

Do not take roles from query parameters, request bodies, or client-supplied headers. Roles/scopes must come from a token whose signature/issuer/audience/timestamps and other trust conditions have already been verified by the Resource Server. The converter only runs in the authentication pipeline; it does not replace token verification.

## 3. Configuring Default Scope Mapping

Spring Security provides `JwtGrantedAuthoritiesConverter`. This converter reads the configured `scope`/`scp` claim, splits the values, and produces authorities with the default `SCOPE_` prefix.

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

Converter<Jwt, Collection<GrantedAuthority>> scopeConverter =
    new JwtGrantedAuthoritiesConverter();
~~~

With the token:

~~~json
{
  "scope": "orders.read orders.write"
}
~~~

Produced authorities:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

### 3.1. Customizing the Scope Claim

If the issuer emits permissions in the `permissions` claim:

~~~json
{
  "permissions": "orders.read orders.write"
}
~~~

you can configure:

~~~java
JwtGrantedAuthoritiesConverter scopeConverter =
    new JwtGrantedAuthoritiesConverter();

scopeConverter.setAuthoritiesClaimName("permissions");
scopeConverter.setAuthorityPrefix("SCOPE_");
scopeConverter.setAuthoritiesClaimDelimiter(" ");
~~~

`setAuthoritiesClaimDelimiter` is available in Spring Security versions that support this API. If your project's version lacks that method, use a custom converter to split the claim format. For JSON array claims, check your current version's behavior or write a custom converter accepting `Collection`; do not apply a string delimiter to array data.

### 3.2. Using an Array `scp` Claim

An issuer might emit:

~~~json
{
  "scp": ["orders.read", "orders.write"]
}
~~~

If the default converter in your version does not handle the specific claim format per contract, write a dedicated converter:

~~~java
Collection<GrantedAuthority> convertScopes(Jwt jwt) {
    Object claim = jwt.getClaims().get("scp");
    if (claim instanceof Collection<?> scopes) {
        return scopes.stream()
            .filter(String.class::isInstance)
            .map(String.class::cast)
            .filter(scope -> !scope.isBlank())
            .map(scope -> new SimpleGrantedAuthority("SCOPE_" + scope))
            .toList();
    }
    return List.of();
}
~~~

The converter must handle data types strictly according to the issuer schema. Do not convert arbitrary objects or nested JSON into authorities.

## 4. Creating a Role-Mapping Converter

Suppose the issuer emits:

~~~json
{
  "roles": ["ORDER_OPERATOR", "SUPPORT_AGENT"]
}
~~~

We want to produce:

~~~text
ROLE_ORDER_OPERATOR
ROLE_SUPPORT_AGENT
~~~

Converter:

~~~java
import java.util.Collection;
import java.util.List;

import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

final class JwtRolesConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    private static final String CLAIM_NAME = "roles";
    private static final String PREFIX = "ROLE_";

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        Object claim = jwt.getClaims().get(CLAIM_NAME);
        if (!(claim instanceof Collection<?> roles)) {
            return List.of();
        }

        return roles.stream()
            .filter(String.class::isInstance)
            .map(String.class::cast)
            .map(String::trim)
            .filter(role -> !role.isEmpty())
            .map(JwtRolesConverter::normalizeRole)
            .distinct()
            .map(SimpleGrantedAuthority::new)
            .toList();
    }

    private static String normalizeRole(String role) {
        return role.startsWith(PREFIX) ? role : PREFIX + role;
    }
}
~~~

The example above accepts roles with or without the prefix and avoids double-prefixing. In production systems, it is best if the issuer emits roles in one consistent format. If the contract specifies that roles never contain `ROLE_`, you can reject values that already carry the prefix rather than silently normalizing them.

### 4.1. Do Not Trust Wrongly Typed Claims

If `roles` is an object or a string not matching the schema, the converter returns an empty list. You can choose a stricter policy: a validator rejects the token when the role claim has the wrong type. This is useful when the issuer contract requires the claim to be an array.

Do not cast directly without checking the type:

~~~java
List<String> roles = (List<String>) jwt.getClaim("roles");
~~~

A token may contain a different data type, causing a `ClassCastException` and failing authentication in a hard-to-diagnose way. Check types and handle out-of-contract data explicitly.

### 4.2. Limiting the Number of Roles

If the role claim can grow large, set an upper bound before creating authorities:

~~~java
private static final int MAX_ROLES = 50;

if (roles.size() > MAX_ROLES) {
    throw new IllegalArgumentException("Too many role values");
}
~~~

In a complete design, enforce the claim budget in a token validator so the error is represented as an invalid token before an `Authentication` is granted. Never create thousands of `SimpleGrantedAuthority` objects from an unbounded claim.

## 5. Combining Scope and Role Authorities

A JWT can contain both scopes and roles. We need a converter that combines both sources:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

final class JwtAuthoritiesConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    private final Converter<Jwt, Collection<GrantedAuthority>> scopes =
        new JwtGrantedAuthoritiesConverter();

    private final Converter<Jwt, Collection<GrantedAuthority>> roles =
        new JwtRolesConverter();

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        Set<GrantedAuthority> result = new LinkedHashSet<>();
        Collection<GrantedAuthority> scopeAuthorities =
            this.scopes.convert(jwt);
        Collection<GrantedAuthority> roleAuthorities =
            this.roles.convert(jwt);

        if (scopeAuthorities != null) {
            result.addAll(scopeAuthorities);
        }
        if (roleAuthorities != null) {
            result.addAll(roleAuthorities);
        }
        return new ArrayList<>(result);
    }
}
~~~

Use `LinkedHashSet` to deduplicate while preserving deterministic ordering. If a token contains duplicate scopes/roles after mapping, only one corresponding authority is needed.

### 5.1. Wiring the Converter into `JwtAuthenticationConverter`

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;

JwtAuthenticationConverter authenticationConverter =
    new JwtAuthenticationConverter();

authenticationConverter.setJwtGrantedAuthoritiesConverter(
    new JwtAuthoritiesConverter());
~~~

Once the decoder verifies the token successfully, Spring Security uses this converter to build a `JwtAuthenticationToken` with the mapped authorities.

### 5.2. Registering the Converter in the Resource Server DSL

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt
        .jwtAuthenticationConverter(authenticationConverter)));
~~~

This converter only specifies how verified claims become authorities. It does not verify signatures, issuer, audience, or expiry; validators and the decoder must still be configured separately.

## 6. Protecting Operations by HTTP Method

Suppose the API policy is:

| Method | Path | Authority |
|---|---|---|
| GET | /api/orders/** | SCOPE_orders.read |
| POST | /api/orders | SCOPE_orders.write |
| PUT | /api/orders/** | SCOPE_orders.write |
| PATCH | /api/orders/** | SCOPE_orders.write |
| DELETE | /api/orders/** | ROLE_ORDER_ADMIN |

Matcher ordering is critical. Method-specific rules must precede general path rules.

### 6.1. Complete Servlet `SecurityFilterChain`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersSecurityConfiguration {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(
            new JwtAuthoritiesConverter());
        return converter;
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            JwtAuthenticationConverter jwtAuthenticationConverter)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()

                .requestMatchers(
                    HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")

                .requestMatchers(
                    HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")

                .requestMatchers(
                    HttpMethod.PUT, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")

                .requestMatchers(
                    HttpMethod.PATCH, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")

                .requestMatchers(
                    HttpMethod.DELETE, "/api/orders/**")
                    .hasAuthority("ROLE_ORDER_ADMIN")

                // Unlisted HTTP methods on this resource are denied.
                .requestMatchers("/api/orders/**").denyAll()

                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt
                    .jwtAuthenticationConverter(
                        jwtAuthenticationConverter)))
            .build();
    }
}
~~~

The final rule for `/api/orders/**` denies unlisted methods, such as `TRACE` or a newly added method without a policy yet. If replaced with `authenticated()`, any principal could pass through that path despite lacking the intended read/write permissions.

The example above uses `denyAll()` for remaining paths to illustrate an API exposing only declared routes. Applications with health, docs, or other routes need dedicated matchers per policy.

### 6.2. Why Distinguish `GET` and `PUT`?

A token with only `SCOPE_orders.read` must be able to read orders but not modify them. A token with only `SCOPE_orders.write` should not automatically be allowed to read if the policy requires a separate read permission.

Do not assume `write` implies `read` unless the issuer and API contract specify so. Separating scopes ensures clients receive only the minimum permissions needed.

### 6.3. Collection `POST` vs. Item `PUT`/`PATCH`

Typically:

- `POST` creates a resource in a collection.
- `PUT` replaces the state of a resource at a specific URI.
- `PATCH` partially updates a resource.
- `DELETE` deletes a resource.

A policy can share the `orders.write` scope for `POST`/`PUT`/`PATCH` and use a separate admin role for `DELETE`. If business rules require distinct permissions, split scopes explicitly into `orders.create`, `orders.update`, and `orders.delete`.

### 6.4. Specific Matchers Must Precede General Matchers

Common mistake:

~~~java
.requestMatchers("/api/orders/**").authenticated()
.requestMatchers(HttpMethod.DELETE, "/api/orders/**")
    .hasAuthority("ROLE_ORDER_ADMIN")
~~~

The general rule matches the request first, so the subsequent `DELETE` rule is never evaluated. Place specific method/path matchers first, followed by fallback deny or general rules.

## 7. Using `hasAuthority` and `hasRole` Correctly

The following expressions:

~~~java
.hasAuthority("SCOPE_orders.read")
.hasAuthority("ROLE_ORDER_ADMIN")
.hasRole("ORDER_ADMIN")
~~~

mean:

| Expression | Required authority |
|---|---|
| hasAuthority("SCOPE_orders.read") | SCOPE_orders.read |
| hasAuthority("ROLE_ORDER_ADMIN") | ROLE_ORDER_ADMIN |
| hasRole("ORDER_ADMIN") | ROLE_ORDER_ADMIN |
| hasRole("ROLE_ORDER_ADMIN") | Usually double-prefixes; avoid |

Scopes typically use `hasAuthority` because the scope name is an exact value. Roles can use `hasRole` if following the `ROLE_` prefix. Using `hasAuthority` for both types is also valid and often makes the mapping more explicit.

Do not change the role prefix in one place and forget to update the other. If the converter creates `ROLE_ORDER_ADMIN`, `hasRole("ORDER_ADMIN")` or `hasAuthority("ROLE_ORDER_ADMIN")` will match; `hasAuthority("ORDER_ADMIN")` will not.

## 8. Combining HTTP Authorization with Method Security

HTTP matchers protect requests at the application boundary. Method security protects service operations even when a method is invoked from another path, such as a message listener, scheduled job, or another controller.

### 8.1. Enabling Method Security

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

### 8.2. Protecting the Order Service

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class OrderService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    Order getOrder(String orderId) {
        // Load order and return it.
        return repository.findById(orderId)
            .orElseThrow(OrderNotFoundException::new);
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.write')")
    Order updateOrder(String orderId, UpdateOrderCommand command) {
        // Validate ownership/business rules and update.
        return repository.update(orderId, command);
    }

    @PreAuthorize("hasAuthority('ROLE_ORDER_ADMIN')")
    void deleteOrder(String orderId) {
        repository.delete(orderId);
    }
}
~~~

The repository/command types in the example are illustrative application components. Method security checks authorities; it does not replace ownership checks or order business invariants.

### 8.3. Checking Resource Ownership

The `orders.write` scope only states that the principal has API-level permission to update orders. It does not mean the user can edit every order. You can add domain authorization:

~~~java
@PreAuthorize("""
    hasAuthority('SCOPE_orders.write')
    and @orderAccess.canEdit(authentication, #orderId)
    """)
Order updateOrder(String orderId, UpdateOrderCommand command) {
    return repository.update(orderId, command);
}
~~~

`orderAccess.canEdit` can check tenant, owner, or workflow state. This is the resource-level data control layer; do not replace it with a broad role when business rules require ownership.

If using parameter names in SpEL, configure the compiler to retain parameter names (such as `-parameters`) or use parameter-binding annotations supported by your Spring Security version. Verify method proxying and parameter discovery in tests.

### 8.4. Method Security Must Go Through a Spring Proxy

Method security relies on proxies/interceptors. If a protected method is called from another method within the same object (self-invocation), the call can bypass the proxy and the annotation will not be applied as expected. Test by calling the Spring-managed bean from outside and design clear service boundaries.

## 9. Sample Controller and Service

A controller can delegate business logic to the service:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrdersController {

    private final OrderService orderService;

    OrdersController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping
    List<Order> list() {
        return orderService.listOrders();
    }

    @GetMapping("/{id}")
    Order get(@PathVariable String id) {
        return orderService.getOrder(id);
    }

    @PostMapping
    Order create(@RequestBody CreateOrderCommand command) {
        return orderService.createOrder(command);
    }

    @PutMapping("/{id}")
    Order replace(
            @PathVariable String id,
            @RequestBody UpdateOrderCommand command) {
        return orderService.updateOrder(id, command);
    }

    @PatchMapping("/{id}")
    Order patch(
            @PathVariable String id,
            @RequestBody UpdateOrderCommand command) {
        return orderService.updateOrder(id, command);
    }

    @DeleteMapping("/{id}")
    void delete(@PathVariable String id) {
        orderService.deleteOrder(id);
    }
}
~~~

In practice, return types may be DTOs, `ResponseEntity`, `Page`, or `Mono` depending on the stack. This example focuses on method-based permissions. Never return internal entities directly if they contain data not intended for the client.

## 10. End-to-End Processing Flow

~~~mermaid
flowchart TD
    A[HTTP request + Bearer access token] --> B[Bearer token resolver]
    B --> C[JwtDecoder verifies signature and validators]
    C --> D[JwtAuthenticationConverter]
    D --> E[JwtGrantedAuthoritiesConverter maps scopes]
    D --> F[JwtRolesConverter maps roles]
    E --> G[JwtAuthenticationToken]
    F --> G
    G --> H{HTTP method + path rule}
    H -->|GET + orders.read| I[Read controller/service]
    H -->|POST/PUT/PATCH + orders.write| J[Write controller/service]
    H -->|DELETE + ORDER_ADMIN| K[Delete controller/service]
    H -->|No matching authority| L[403 Forbidden]
    I --> M[Domain/ownership checks]
    J --> M
    K --> M
~~~

If the token is missing or fails verification, the request is rejected at authentication before creating a principal. If the token is verified but lacks the required authority, authorization returns `403`. If the authority is present but the caller does not own the resource, domain authorization can still deny access.

## 11. Testing Mapping and Authorization

Separate two questions:

1. Are claims mapped to the right authorities?
2. Does the HTTP method/path require the right authority?

Then add a signed Bearer token integration test to prove the decoder, converter, and filter chain are wired together.

### 11.1. Converter Unit Test

~~~java
@Test
void mapsScopesAndRolesToAuthorities() {
    Jwt jwt = Jwt.withTokenValue("test-token")
        .header("alg", "RS256")
        .claim("scope", "orders.read orders.write")
        .claim("roles", List.of("ORDER_ADMIN", "SUPPORT_AGENT"))
        .build();

    Collection<GrantedAuthority> authorities =
        new JwtAuthoritiesConverter().convert(jwt);

    assertThat(authorities)
        .extracting(GrantedAuthority::getAuthority)
        .containsExactlyInAnyOrder(
            "SCOPE_orders.read",
            "SCOPE_orders.write",
            "ROLE_ORDER_ADMIN",
            "ROLE_SUPPORT_AGENT");
}
~~~

This test verifies the converter directly. The JWT fixture has no signature and does not prove the production decoder verifies tokens.

### 11.2. MockMvc Test: `GET` Requires Read Scope

With Spring Security Test, you can use the `jwt()` request post-processor to test authorization:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;

mockMvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

### 11.3. MockMvc Test: Missing Read Scope

~~~java
mockMvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.write"))))
    .andExpect(status().isForbidden());
~~~

The principal is authenticated but only has the write scope; the `GET` policy requires the read scope, so it returns `403`.

### 11.4. MockMvc Test: `PUT` Requires Write Scope

~~~java
mockMvc.perform(put("/api/orders/123")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.write")))
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"status":"CONFIRMED"}
            """))
    .andExpect(status().isOk());
~~~

### 11.5. `GET` Scope Cannot Modify

~~~java
mockMvc.perform(put("/api/orders/123")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")))
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"status":"CONFIRMED"}
            """))
    .andExpect(status().isForbidden());
~~~

### 11.6. `DELETE` Requires Admin Role

~~~java
mockMvc.perform(delete("/api/orders/123")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("ROLE_ORDER_ADMIN"))))
    .andExpect(status().isNoContent());
~~~

A user with `SCOPE_orders.write` but without `ROLE_ORDER_ADMIN` must still be denied `DELETE` if the policy is defined that way.

### 11.7. Missing Token vs. Insufficient Permission Are Distinct Cases

~~~java
@Test
void missingTokenIsUnauthorized() throws Exception {
    mockMvc.perform(get("/api/orders"))
        .andExpect(status().isUnauthorized());
}

@Test
void authenticatedTokenWithoutReadScopeIsForbidden() throws Exception {
    mockMvc.perform(get("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.write"))))
        .andExpect(status().isForbidden());
}
~~~

The `jwt()` test post-processor creates an authentication for the request; that test is suitable for checking authorization. It does not pass a compact JWT through the decoder and does not test production converter mapping.

## 12. Integration Test with Signed Bearer JWTs

To test the full path, create a genuinely signed test access token, send it via the `Authorization` header, and let the Resource Server perform:

1. Bearer token extraction.
2. Signature verification.
3. Issuer/audience/time/type validators.
4. Scope and role mapping via the production converter.
5. HTTP-method-based matchers.

An example test token factory can use `NimbusJwtEncoder` with an RSA test key:

~~~java
String issueToken(
        JwtEncoder encoder,
        String scope,
        List<String> roles) {

    Instant now = Instant.now();
    JwtClaimsSet claims = JwtClaimsSet.builder()
        .issuer("https://identity.example.test")
        .subject("alice")
        .audience(List.of("orders-api"))
        .issuedAt(now.minusSeconds(10))
        .expiresAt(now.plusSeconds(300))
        .claim("scope", scope)
        .claim("roles", roles)
        .build();

    JwsHeader headers = JwsHeader
        .with(SignatureAlgorithm.RS256)
        .keyId("test-key")
        .build();

    return encoder.encode(
        JwtEncoderParameters.from(headers, claims))
        .getTokenValue();
}
~~~

Then send the token:

~~~java
String token = issueToken(
    testJwtEncoder,
    "orders.read",
    List.of("ORDER_OPERATOR"));

mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
    .andExpect(status().isOk());

mockMvc.perform(put("/api/orders/123")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"status\":\"CONFIRMED\"}"))
    .andExpect(status().isForbidden());
~~~

The test above verifies the production converter if the test context's decoder/authentication provider actually uses the same configured `JwtAuthenticationConverter`. Ensure the decoder trusts the public key corresponding to the test encoder and that issuer/audience validators accept the claims. Do not mock the decoder or use the `jwt()` post-processor in this integration test.

## 13. WebFlux Resource Server

With WebFlux, the scope/role and HTTP method policy is the same as Servlet, but the converter returns reactive authorities.

### 13.1. Reactive Role/Scope Converter

`JwtGrantedAuthoritiesConverter` can still be used to build the collection; wrap the collection in a `Flux` for `ReactiveJwtAuthenticationConverter`:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverter;
import reactor.core.publisher.Flux;

Converter<Jwt, Flux<GrantedAuthority>> authoritiesConverter = jwt -> {
    Collection<GrantedAuthority> scopes =
        new JwtGrantedAuthoritiesConverter().convert(jwt);
    Collection<GrantedAuthority> roles =
        new JwtRolesConverter().convert(jwt);

    return Flux.concat(
        Flux.fromIterable(scopes == null ? List.of() : scopes),
        Flux.fromIterable(roles));
};

ReactiveJwtAuthenticationConverter authenticationConverter =
    new ReactiveJwtAuthenticationConverter();
authenticationConverter.setJwtGrantedAuthoritiesConverter(
    authoritiesConverter);
~~~

In production code, instantiate the scope converter and role converter once as beans rather than creating new ones per request. You can reuse the combined logic from `JwtAuthoritiesConverter` and then wrap with `Flux.fromIterable`.

### 13.2. Reactive `SecurityWebFilterChain`

~~~java
@Bean
SecurityWebFilterChain reactiveApiSecurity(
        ServerHttpSecurity http,
        ReactiveJwtAuthenticationConverter authenticationConverter) {

    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/public/**").permitAll()

            .pathMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")

            .pathMatchers(HttpMethod.POST, "/api/orders")
                .hasAuthority("SCOPE_orders.write")

            .pathMatchers(HttpMethod.PUT, "/api/orders/**")
                .hasAuthority("SCOPE_orders.write")

            .pathMatchers(HttpMethod.PATCH, "/api/orders/**")
                .hasAuthority("SCOPE_orders.write")

            .pathMatchers(HttpMethod.DELETE, "/api/orders/**")
                .hasAuthority("ROLE_ORDER_ADMIN")

            .pathMatchers("/api/orders/**").denyAll()
            .anyExchange().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt
                .jwtAuthenticationConverter(authenticationConverter)))
        .build();
}
~~~

DSL names and reactive converter APIs must match your project's Spring Security version. The policy remains unchanged: method-specific rules come before the fallback path deny.

### 13.3. Reactive Method Security

For services returning `Mono`/`Flux`, enable:

~~~java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfiguration {
}
~~~

Example:

~~~java
@Service
class ReactiveOrderService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    Mono<Order> getOrder(String id) {
        return repository.findById(id);
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.write')")
    Mono<Order> updateOrder(String id, UpdateOrderCommand command) {
        return repository.update(id, command);
    }
}
~~~

Do not call `block()` to extract the principal or service result in a reactive path. Spring Security maintains the security context in the Reactor context; keep the pipeline reactive from filter to controller/service.

## 14. `OPTIONS`, CORS, and Method Authorization

Browsers may send a CORS preflight `OPTIONS` request before `GET`/`PUT`/`PATCH`/`DELETE` requests. If the API is called from a browser:

- Configure a CORS policy for allowed origins, methods, and headers.
- Allow preflight handling before requiring a Bearer token if the CORS policy requires it.
- Allow only the HTTP methods actually supported.
- Do not use a broad `permitAll` across all methods just to make preflight work.

Preflight `OPTIONS` is not a resource read/write operation. Configure CORS integration per your Spring Security version and test preflight separately. If the API does not serve cross-origin browsers, do not add arbitrary CORS rules.

## 15. Scope/Role Permissions Do Not Replace Data Controls

An authority like `SCOPE_orders.read` only decides whether the principal can call the API-level read operation. The application must still check:

- Does the user belong to the order's tenant?
- Does the order belong to an organization the principal is allowed to access?
- Does the current status permit modification?
- Is the user the owner/assignee?
- Are the updatable data fields restricted?

For example, the `write` scope does not permit changing `ownerId` or `tenantId` arbitrarily. Use DTOs that permit updating valid fields alongside domain authorization in the service. Do not treat an admin role as a reason to bypass all business invariants or auditing.

## 16. Complete Permission Matrix

With the example policy:

| Authorities in token | GET | POST | PUT/PATCH | DELETE |
|---|---:|---:|---:|---:|
| SCOPE_orders.read | Allowed | 403 | 403 | 403 |
| SCOPE_orders.write | 403 | Allowed | Allowed | 403 |
| ROLE_ORDER_OPERATOR | 403 | 403* | 403* | 403 |
| ROLE_ORDER_ADMIN | 403** | 403** | 403** | Allowed |
| SCOPE_orders.read + SCOPE_orders.write | Allowed | Allowed | Allowed | 403 |
| SCOPE_orders.read + ROLE_ORDER_ADMIN | Allowed | 403 | 403 | Allowed |
| No token | 401 | 401 | 401 | 401 |

*`ROLE_ORDER_OPERATOR` is only allowed to create/modify if the policy adds a rule mapping that role to those permissions or the matcher accepts that role. This table illustrates the current policy, which uses scopes alone for read/write.

**If admins need to read and edit all orders, add the corresponding authorities to the policy/matchers; the example above grants the admin role only to `DELETE`.

A matrix helps reviewers see which permissions are granted. Whenever you change mappings or add methods, update tests for all relevant columns.

## 17. Common Pitfalls

| Mistake | Consequence | Fix |
|---|---|---|
| Using `hasRole("ROLE_ADMIN")` | The `ROLE_` prefix may be added twice | Use `hasRole("ADMIN")` or full authority |
| Using `hasAuthority("orders.read")` | Does not match default `SCOPE_orders.read` | Use the proper prefix |
| Mapping only `scope`, ignoring role claim | Role-based rules always fail | Add a role converter |
| Role converter lacks claim type checks | `ClassCastException` or wrong mapping | Check `Collection`/`String` per schema |
| Duplicate role prefix | `ROLE_ROLE_ADMIN` | Normalize once and align with issuer contract |
| Mapping every claim to an authority | Unintended permissions | Map only allowed claims |
| General path rule placed before method rule | Specific rule never runs | Place specific method/path matchers first |
| Fallback `authenticated()` for all methods on orders | Unpolicied methods remain accessible | Use path fallback `denyAll()` |
| Allowing write scope to automatically grant read | Violates least privilege | Separate read and write if business rules require |
| Checking only HTTP matchers | Service can be called via another path | Add method security/domain authorization |
| Calling service via self-invocation | Method security proxy may be bypassed | Invoke through a Spring bean proxy |
| Using `jwt()` test to conclude converter works | Test post-processor bypasses production decoder/converter | Unit test converter and run Bearer integration tests |
| Not checking tenant/owner | User with scope can modify others' data | Enforce resource-level domain authorization |
| Allowing `OPTIONS` with broad `permitAll` | Exposes unnecessary methods | Configure CORS/preflight properly |

## 18. Implementation Sequence

1. **Finalize the token contract:** claim names, data types, scope format, role format, issuer, and audience.
2. **Configure decoder/validators:** verify signature, issuer, audience, timestamps, and token profile.
3. **Map scopes:** use `JwtGrantedAuthoritiesConverter` or a custom converter per claim.
4. **Map roles:** convert role claims to authorities with a consistent prefix.
5. **Combine authorities:** use a single `JwtAuthenticationConverter` for both scopes and roles.
6. **Write HTTP policy:** declare each method/path and required authority.
7. **Deny undefined methods:** add a path fallback `denyAll()` for sensitive resources.
8. **Protect services:** use method security and enforce ownership/tenant checks.
9. **Write tests:** converter, GET/read, POST/PUT/PATCH/write, DELETE/admin, 401, and 403.
10. **Integration test:** send signed JWTs via the Bearer header to test decoder → converter → authorization.

## 19. Conclusion

~~~text
JWT CLAIMS
  scope: orders.read orders.write
  roles: ORDER_OPERATOR
       |
       v
AUTHORITY MAPPING
  scope -> SCOPE_orders.read
          SCOPE_orders.write
  roles -> ROLE_ORDER_OPERATOR
       |
       v
HTTP METHOD POLICY
  GET            -> SCOPE_orders.read
  POST/PUT/PATCH -> SCOPE_orders.write
  DELETE         -> ROLE_ORDER_ADMIN
       |
       v
DOMAIN AUTHORIZATION
  tenant / owner / workflow / field-level rules
       |
       v
CONTROLLER + SERVICE
~~~

Scopes and roles are only useful when the Resource Server maps them to authorities according to a clear contract. Use `JwtGrantedAuthoritiesConverter` for standard scopes, a dedicated converter for role claims, and combine both sources in `JwtAuthenticationConverter`. Then protect each HTTP method/path with specific authorities, place detailed matchers before the fallback deny rule, and add method/domain security at the service layer.

Tests must distinguish authentication from authorization: missing or invalid tokens typically return `401`; authenticated tokens lacking the required scope/role return `403`. Mock JWTs are useful for quick policy checks, while signed Bearer token integration tests prove the production decoder and converter participate together in the request.

## References

- [Spring Security Reference — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder, authentication converter, and authorities.
- [Spring Security API — JwtGrantedAuthoritiesConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html): mapping scope claims to `GrantedAuthority`.
- [Spring Security API — JwtAuthenticationConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html): creating `JwtAuthenticationToken` and configuring the authorities converter.
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): request matchers, authorities, and method-based authorization.
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `PreAuthorize`, `EnableMethodSecurity`, and method interception.
- [Spring Security Reference — Testing MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): JWT request post-processor for authorization tests.
- [Spring Security Reference — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): `ReactiveJwtAuthenticationConverter` and WebFlux JWT support.
- [Spring Security Reference — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): reactive method authorization.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): `scope` parameter and authorization grants.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access-token profile.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer access-token request semantics.
