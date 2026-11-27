# ReactiveJwtAuthenticationConverter and Authority Mapping

In a **Spring Security OAuth 2.0/OIDC Resource Server** running on **Spring WebFlux**, JWT access token authentication involves two distinct tasks: **verifying the token** and **turning verified claims into an identity/permissions that Spring Security understands**. After `ReactiveJwtDecoder` confirms the signature, issuer, expiration, and required token conditions, **`ReactiveJwtAuthenticationConverter`** converts the `Jwt` object into an `Authentication` usable within the **Reactor Context**.

The confusing part is that **claims do not automatically equal `GrantedAuthority`**. A token with `"scope": "orders.read"` is normally converted into the `SCOPE_orders.read` authority; however, if the issuer uses `"permissions": ["orders.export"]` or places `roles` inside `realm_access.roles`, the application must configure the mapping intentionally. Misconfiguring the claim source or prefix causes endpoints to return **403** despite a valid JWT; configuring it too broadly can cause the Resource Server to grant permissions beyond what the token was actually issued for.

This lesson progresses from **`ReactiveJwtAuthenticationConverter`**, `JwtGrantedAuthoritiesConverter`, and **`ReactiveJwtGrantedAuthoritiesConverterAdapter`** to writing a genuinely reactive converter, wiring the converter into **`SecurityWebFilterChain`**, reading authorities from **`ReactiveSecurityContextHolder`**, and testing both authority mapping and WebFlux responses.

## 1. Position of the Converter in WebFlux JWT Architecture

Suppose the Orders API receives:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <jwt-access-token>
~~~

An illustrative JWT access token has claims:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "iat": 1763164800,
  "exp": 1893456000,
  "scope": "orders.read orders.export"
}
~~~

This is **only a payload example**, not a validly signed JWT. In an actual request, Spring Security must verify the token using trusted configuration before using claims.

~~~mermaid
flowchart TD
    A["HTTP Authorization: Bearer JWT"] --> B["SecurityWebFilterChain"]
    B --> C["Bearer token extraction / AuthenticationWebFilter"]
    C --> D["ReactiveAuthenticationManager"]
    D --> E["ReactiveJwtDecoder"]
    E --> F{"Valid signature, iss, aud, exp, nbf, profile?"}
    F -- "No" --> X["Authentication failure: usually 401"]
    F -- "Yes" --> G["Verified Jwt"]
    G --> H["ReactiveJwtAuthenticationConverter"]
    H --> I["Convert JWT claims → Flux<GrantedAuthority>"]
    I --> J["JwtAuthenticationToken"]
    J --> K["Reactive SecurityContext in Reactor Context"]
    K --> L["AuthorizationWebFilter / method security"]
    L --> M{"Authority / object policy satisfied?"}
    M -- "No" --> Y["Usually 403 or 404 per policy"]
    M -- "Yes" --> N["Reactive Controller / Service"]
~~~

The diagram presents **logical responsibilities**, without asserting exact names or positions of every WebFilter across all Spring Security versions.

| Component | Role |
| --- | --- |
| `SecurityWebFilterChain` | Defines how WebFlux requests are protected |
| `ServerHttpSecurity` | DSL for configuring reactive HTTP security |
| `ReactiveJwtDecoder` | Decodes/verifies JWTs and applies token validators |
| `ReactiveJwtAuthenticationConverter` | Creates reactive `Authentication` from a verified `Jwt` |
| `JwtGrantedAuthoritiesConverter` | Synchronously converts scope/permission claims into `Collection<GrantedAuthority>` |
| `ReactiveJwtGrantedAuthoritiesConverterAdapter` | Adapts a synchronous authorities converter to `Flux<GrantedAuthority>` |
| `JwtAuthenticationToken` | Common JWT Resource Server `Authentication`, carrying the JWT and authorities |
| `ReactiveSecurityContextHolder` | Reads the subscriber's `SecurityContext` from the Reactor Context |
| `AuthorizationWebFilter` and method security | Checks functional rules; business policies handle tenant/owner |

**A converter is not a decoder.** Changing `ReactiveJwtAuthenticationConverter` does not turn an unverified token into a trusted one. The API still requires a trusted decoder, API audience checks, and mandatory claim/profile validation.

## 2. Data Types: Why Does "Reactive" in the Name Matter?

In Spring Security Servlet, `JwtAuthenticationConverter` is normally a **synchronous** converter:

~~~java
Converter<Jwt, AbstractAuthenticationToken>
~~~

In WebFlux, `ReactiveJwtAuthenticationConverter` under the standard API implements:

~~~java
Converter<Jwt, Mono<AbstractAuthenticationToken>>
~~~

It allows the authentication chain to emit a `Mono` and integrate with the Reactor pipeline. The authority-mapping component expected by the reactive converter has the form:

~~~java
Converter<Jwt, Flux<GrantedAuthority>>
~~~

Do not confuse the three type layers:

~~~text
Decoder-verified JWT: Jwt
             |
             v
Authorities converter:
     Jwt -> Flux<GrantedAuthority>
             |
             v
ReactiveJwtAuthenticationConverter:
     Jwt -> Mono<AbstractAuthenticationToken>
             |
             v
JwtAuthenticationToken:
     principal, token, authorities collection
~~~

In standard Spring Security releases, the converter can collect the authorities `Flux` into a list before constructing `JwtAuthenticationToken`. If the authorities `Flux` errors, JWT authentication will not complete successfully along that chain.

### Comparing Servlet and WebFlux

| Aspect | Servlet | WebFlux |
| --- | --- | --- |
| HTTP security | `HttpSecurity` + `SecurityFilterChain` | `ServerHttpSecurity` + `SecurityWebFilterChain` |
| JWT decoder | `JwtDecoder` | `ReactiveJwtDecoder` |
| Common JWT authentication converter | `JwtAuthenticationConverter` | `ReactiveJwtAuthenticationConverter` |
| Default/custom authorities converter | `JwtGrantedAuthoritiesConverter` | Can reuse the same converter via a reactive adapter |
| Security context | Typically ThreadLocal-backed | Reactor Context per subscriber |
| JWT authentication object | `JwtAuthenticationToken` | Also typically `JwtAuthenticationToken` |
| HTTP testing | `MockMvc` | `WebTestClient` |

The class names are similar but **not interchangeable**. Passing a synchronous `JwtAuthenticationConverter` directly into a DSL expecting `Mono<AbstractAuthenticationToken>` causes type errors; you must use the corresponding adapter or write a reactive converter.

## 3. Default Convention: `scope`/`scp` → `SCOPE_`

In a standard Spring Security JWT Resource Server setup, OAuth 2.0 permissions are read from a familiar scope claim such as **`scope`** or **`scp`**.

Example:

~~~json
{
  "scope": "orders.read orders.write"
}
~~~

The typical result is:

~~~text
JwtGrantedAuthoritiesConverter
  "orders.read"  -> SimpleGrantedAuthority("SCOPE_orders.read")
  "orders.write" -> SimpleGrantedAuthority("SCOPE_orders.write")
~~~

Or the issuer emits:

~~~json
{
  "scp": ["orders.read", "orders.export"]
}
~~~

Result:

~~~text
SCOPE_orders.read
SCOPE_orders.export
~~~

Therefore, the rule:

~~~java
.pathMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

matches the `orders.read` scope, whereas `hasAuthority("orders.read")` **does not match automatically** when the converter prepends the `SCOPE_` prefix.

A few notes:

- `scope` is typically a **space-delimited string of scopes** per OAuth 2.0.
- `scp` can be a string array per the issuer's contract.
- Missing a recognized claim normally yields an **empty set of authorities**, rather than granting default permissions.
- If both `scope` and `scp` are present, **do not assume they are merged by default**; the converter selects a well-known claim according to its version behavior.
- Custom claims such as `permissions`, `groups`, or `roles` **do not automatically** become authorities merely by appearing in the token.
- `SCOPE_` is an **authority naming convention**, not a JSON claim or proof that the caller owns an order.

### Scopes Differ from User Roles

Scopes normally express OAuth 2.0 permissions **granted to a token/client in a resource-access context**. Roles such as `ORDER_MANAGER` may belong to the subject's business permission model. These two concepts do not necessarily have the same scope.

For example, an employee has role `ORDER_MANAGER` while the client requested and was granted only `orders.read`; the API must not infer that the client is allowed `orders.delete`. Sensitive operations may require **both scope and role**, plus tenant/owner checks.

## 4. Using `JwtGrantedAuthoritiesConverter` Through a Reactive Adapter

When the issuer emits permission claims as a simple **string** or **string array**, the least-code approach is to configure the synchronous `JwtGrantedAuthoritiesConverter` and wrap it with **`ReactiveJwtGrantedAuthoritiesConverterAdapter`**.

Suppose the issuer provides:

~~~json
{
  "sub": "user-42",
  "aud": ["orders-api"],
  "permissions": ["orders.read", "orders.export"]
}
~~~

We want to convert `permissions` into:

~~~text
PERMISSION_orders.read
PERMISSION_orders.export
~~~

Code:

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtGrantedAuthoritiesConverterAdapter;

JwtGrantedAuthoritiesConverter permissionExtractor =
    new JwtGrantedAuthoritiesConverter();
permissionExtractor.setAuthoritiesClaimName("permissions");
permissionExtractor.setAuthorityPrefix("PERMISSION_");

ReactiveJwtAuthenticationConverter authenticationConverter =
    new ReactiveJwtAuthenticationConverter();
authenticationConverter.setJwtGrantedAuthoritiesConverter(
    new ReactiveJwtGrantedAuthoritiesConverterAdapter(permissionExtractor)
);
~~~

Here:

1. `setAuthoritiesClaimName("permissions")` selects the **claim source**.
2. `setAuthorityPrefix("PERMISSION_")` sets the **authority name prefix**.
3. `ReactiveJwtGrantedAuthoritiesConverterAdapter` turns the `Collection<GrantedAuthority>` output into `Flux<GrantedAuthority>` per the WebFlux contract.
4. `ReactiveJwtAuthenticationConverter` consumes the `Flux` and constructs the `Authentication` for the JWT.

**Switching the source to `permissions` can drop authorities coming from `scope`/`scp`** if you rely on only one reconfigured extractor. To keep both, **combine converters** or write an explicit custom converter.

### Adding a Delimiter for Custom String Claims

An issuer might emit:

~~~json
{
  "permissions": "orders.read,orders.export"
}
~~~

In Spring Security versions providing `setAuthoritiesClaimDelimiter(String)`, such as Spring Security 6.1+, you can do:

~~~java
JwtGrantedAuthoritiesConverter converter =
    new JwtGrantedAuthoritiesConverter();
converter.setAuthoritiesClaimName("permissions");
converter.setAuthorityPrefix("PERMISSION_");
converter.setAuthoritiesClaimDelimiter(",");
~~~

The delimiter is normally a **regex**, so escape it properly in Java and match issuer semantics. Never treat a comma as the OAuth 2.0 `scope` standard default. For string arrays, the converter does not need to split a string with a delimiter.

**Version note:** if `setAuthoritiesClaimDelimiter(...)` does not exist in your current library version, write a custom converter or perform a controlled upgrade; never copy code and ignore compile errors.

## 5. Wiring `ReactiveJwtAuthenticationConverter` into `ServerHttpSecurity`

A converter instance takes effect only when **attached to the WebFlux JWT Resource Server configuration handling requests**.

Typical Maven dependencies:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

Example WebFlux configuration with permissions:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtGrantedAuthoritiesConverterAdapter;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class ReactiveOrdersSecurity {

    @Bean
    ReactiveJwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter permissions =
            new JwtGrantedAuthoritiesConverter();
        permissions.setAuthoritiesClaimName("permissions");
        permissions.setAuthorityPrefix("PERMISSION_");

        ReactiveJwtAuthenticationConverter converter =
            new ReactiveJwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(
            new ReactiveJwtGrantedAuthoritiesConverterAdapter(permissions));
        return converter;
    }

    @Bean
    SecurityWebFilterChain apiSecurity(
            ServerHttpSecurity http,
            ReactiveJwtAuthenticationConverter jwtAuthenticationConverter) {
        return http
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("PERMISSION_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/reports/export")
                    .hasAuthority("PERMISSION_orders.export")
                .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
                jwt.jwtAuthenticationConverter(jwtAuthenticationConverter)))
            .build();
    }
}
~~~

Result:

~~~text
JWT.permissions = ["orders.read", "orders.export"]
          |
          v
ReactiveJwtGrantedAuthoritiesConverterAdapter
          |
          v
Flux<GrantedAuthority>:
  PERMISSION_orders.read
  PERMISSION_orders.export
          |
          v
JwtAuthenticationToken in Reactor Context
          |
          v
WebFlux authorizeExchange().hasAuthority(...)
~~~

**Important:** this setup **maps only `permissions`**. Rules checking `SCOPE_orders.read` may return 403 because the default scope converter is no longer active. If the application needs both permission types, see the combination section below.

CSRF is disabled in the example because it assumes a **stateless, Bearer-only API that does not rely on browser-auto-sent cookie credentials**. For applications using cookies/sessions, evaluate CSRF and adjust the configuration accordingly.

On token security, `issuer-uri` helps configure the issuer/JWKS per Spring Security capabilities; **audience, token type/profile, and mandatory business claims must still be validated per the API contract**. Customizing the converter does not replace those validators.

## 6. Combining `scope` and `permissions` Without Losing Existing Permissions

A JWT may contain both:

~~~json
{
  "scope": "orders.read",
  "permissions": ["orders.export", "reports.view"]
}
~~~

We want:

~~~text
SCOPE_orders.read
PERMISSION_orders.export
PERMISSION_reports.view
~~~

### 6.1. Combining via Synchronous Converter Then Reactive Adapter

In Spring Security versions providing `DelegatingJwtGrantedAuthoritiesConverter`, you can use:

~~~java
import org.springframework.security.oauth2.server.resource.authentication.DelegatingJwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtGrantedAuthoritiesConverterAdapter;

JwtGrantedAuthoritiesConverter scopes =
    new JwtGrantedAuthoritiesConverter(); // scope/scp, SCOPE_

JwtGrantedAuthoritiesConverter permissions =
    new JwtGrantedAuthoritiesConverter();
permissions.setAuthoritiesClaimName("permissions");
permissions.setAuthorityPrefix("PERMISSION_");

DelegatingJwtGrantedAuthoritiesConverter combined =
    new DelegatingJwtGrantedAuthoritiesConverter(scopes, permissions);

ReactiveJwtAuthenticationConverter authentication =
    new ReactiveJwtAuthenticationConverter();
authentication.setJwtGrantedAuthoritiesConverter(
    new ReactiveJwtGrantedAuthoritiesConverterAdapter(combined));
~~~

`DelegatingJwtGrantedAuthoritiesConverter` merges the authorities from child converters. This works well when all sources can be extracted **synchronously, quickly, and without I/O**.

If that class is unavailable in your dependency version, write your own `Converter<Jwt, Collection<GrantedAuthority>>` to merge results using a `LinkedHashSet`, then wrap it with the reactive adapter.

### 6.2. Combining Directly in `Flux`

Another option is creating a `Converter<Jwt, Flux<GrantedAuthority>>` with Reactor:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtGrantedAuthoritiesConverterAdapter;
import reactor.core.publisher.Flux;

public final class ScopesAndPermissionsConverter
        implements Converter<Jwt, Flux<GrantedAuthority>> {

    private final ReactiveJwtGrantedAuthoritiesConverterAdapter scopeAdapter;
    private final ReactiveJwtGrantedAuthoritiesConverterAdapter permissionAdapter;

    public ScopesAndPermissionsConverter() {
        JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

        JwtGrantedAuthoritiesConverter permissions =
            new JwtGrantedAuthoritiesConverter();
        permissions.setAuthoritiesClaimName("permissions");
        permissions.setAuthorityPrefix("PERMISSION_");

        this.scopeAdapter =
            new ReactiveJwtGrantedAuthoritiesConverterAdapter(scopes);
        this.permissionAdapter =
            new ReactiveJwtGrantedAuthoritiesConverterAdapter(permissions);
    }

    @Override
    public Flux<GrantedAuthority> convert(Jwt jwt) {
        return Flux.concat(
            scopeAdapter.convert(jwt),
            permissionAdapter.convert(jwt)
        ).distinct(GrantedAuthority::getAuthority);
    }
}
~~~

Wire it in:

~~~java
ReactiveJwtAuthenticationConverter authentication =
    new ReactiveJwtAuthenticationConverter();
authentication.setJwtGrantedAuthoritiesConverter(
    new ScopesAndPermissionsConverter());
~~~

`distinct(GrantedAuthority::getAuthority)` prevents duplicate authority names when sources contain overlapping values. Emission order in the `Flux` should not be used to make permission decisions; authorization only needs the right set of authority names.

**Combining sources is a policy decision.** If `permissions` holds general user permissions while `scope` holds token permissions granted to a specific client, merging them may broaden what the client can invoke on the API. Clarify whether a rule needs **any single authority** or **multiple conditions simultaneously**.

## 7. Mapping Roles Inside Nested Claims

Some issuers supply roles inside nested objects instead of a direct string claim. A common structure:

~~~json
{
  "sub": "user-42",
  "scope": "orders.read",
  "realm_access": {
    "roles": ["USER", "REPORT_VIEWER"]
  },
  "resource_access": {
    "orders-api": {
      "roles": ["ORDER_EDITOR"]
    },
    "billing-api": {
      "roles": ["BILLING_ADMIN"]
    }
  }
}
~~~

Do not assume:

~~~java
// NOT a JSONPath by default:
roles.setAuthoritiesClaimName("resource_access.orders-api.roles");
~~~

Standard `JwtGrantedAuthoritiesConverter` looks up **top-level claim names directly**. Dots do not automatically turn into nested JSON queries. For nested objects, write a schema-aware converter.

### Converter Reading Only Roles for `orders-api`

Example role mapping accepting only pre-defined roles:

~~~java
import java.util.Collection;
import java.util.Map;
import java.util.Set;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import reactor.core.publisher.Flux;

public final class OrdersResourceRolesConverter
        implements Converter<Jwt, Flux<GrantedAuthority>> {

    private static final String RESOURCE = "orders-api";
    private static final Set<String> ALLOWED_ROLES =
        Set.of("ORDER_READER", "ORDER_EDITOR", "ORDER_MANAGER");

    @Override
    public Flux<GrantedAuthority> convert(Jwt jwt) {
        return Flux.defer(() -> {
            Object rawResources = jwt.getClaim("resource_access");
            if (!(rawResources instanceof Map<?, ?> resources)) {
                return Flux.empty();
            }

            Object rawOrders = resources.get(RESOURCE);
            if (!(rawOrders instanceof Map<?, ?> orders)) {
                return Flux.empty();
            }

            Object rawRoles = orders.get("roles");
            if (!(rawRoles instanceof Collection<?> values)) {
                return Flux.empty();
            }

            return Flux.fromIterable(values)
                .filter(String.class::isInstance)
                .cast(String.class)
                .filter(ALLOWED_ROLES::contains)
                .map(role -> (GrantedAuthority)
                    new SimpleGrantedAuthority("ROLE_" + role));
        });
    }
}
~~~

Here:

- Reads roles only from **`resource_access["orders-api"]`**.
- Does not pull in `BILLING_ADMIN` from `billing-api`.
- Maps only roles in the **allowlist**.
- Returns `Flux.empty()` when matching data is absent, never granting default permissions.
- Uses the `ROLE_` namespace for application-defined role rules.

**Realm-level roles and resource-specific roles have different semantics**. The API must decide whether realm roles are accepted; the example above accepts only resource roles to avoid importing permissions from elsewhere.

When the profile mandates the permission structure, **claims of the wrong type may need to be rejected at token validation**, rather than silently skipped to return an empty `Flux`. Handling must align with the Authorization Server contract.

### Combining Roles with Scopes

~~~java
public final class OrdersAuthoritiesConverter
        implements Converter<Jwt, Flux<GrantedAuthority>> {

    private final ReactiveJwtGrantedAuthoritiesConverterAdapter scopes =
        new ReactiveJwtGrantedAuthoritiesConverterAdapter(
            new JwtGrantedAuthoritiesConverter());

    private final OrdersResourceRolesConverter roles =
        new OrdersResourceRolesConverter();

    @Override
    public Flux<GrantedAuthority> convert(Jwt jwt) {
        return Flux.concat(
            scopes.convert(jwt),
            roles.convert(jwt)
        ).distinct(GrantedAuthority::getAuthority);
    }
}
~~~

The skeleton above needs imports for `Converter`, `Jwt`, `Flux`, `GrantedAuthority`, and the classes shown in previous sections.

Once this converter is wired, you can require **both scope and role**:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.write') and hasRole('ORDER_EDITOR')")
public Mono<Void> updateOrder(String orderId, UpdateOrderRequest request) {
    // ...
}
~~~

In standard Spring Security setups, `hasRole('ORDER_EDITOR')` looks for the `ROLE_ORDER_EDITOR` authority. To check the full name directly, use `hasAuthority('ROLE_ORDER_EDITOR')`; do not assume `hasRole('ROLE_ORDER_EDITOR')` is right.

## 8. Distinguishing Synchronous Authorities from Truly Reactive I/O Processing

The class name **`ReactiveJwtAuthenticationConverter` does not automatically make all logic inside a converter non-blocking**.

When mapping scopes/roles purely from in-memory claims:

~~~text
Jwt -> read claims -> SimpleGrantedAuthority -> Flux
~~~

using synchronous `JwtGrantedAuthoritiesConverter` via `ReactiveJwtGrantedAuthoritiesConverterAdapter` is a great fit.

Conversely, if a mapper performs:

~~~java
// DO NOT DO THIS on the event-loop:
List<String> roles = blockingRoleRepository.findRoles(jwt.getSubject());
~~~

it still **blocks the thread** even inside a reactive converter. The adapter does not automatically move blocking I/O onto a safe scheduler.

### When You Genuinely Must Use a Reactive Permission Service

You can write a converter returning a `Flux` from an asynchronous service:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import reactor.core.publisher.Flux;

public final class ReactivePolicyAuthoritiesConverter
        implements Converter<Jwt, Flux<GrantedAuthority>> {

    private final ReactiveRoleService roleService;

    public ReactivePolicyAuthoritiesConverter(ReactiveRoleService roleService) {
        this.roleService = roleService;
    }

    @Override
    public Flux<GrantedAuthority> convert(Jwt jwt) {
        return Flux.defer(() -> roleService
            .findAllowedRoles(jwt.getIssuer().toString(), jwt.getSubject())
            .filter(role -> role.startsWith("ORDER_"))
            .map(role -> (GrantedAuthority)
                new SimpleGrantedAuthority("ROLE_" + role)));
    }
}
~~~

`ReactiveRoleService` is a **custom business interface**, assuming `findAllowedRoles(...)` returns a `Flux<String>` from a trusted reactive data source. The example illustrates publisher composition instead of calling `block()`. In production, validate against an **exact** role allowlist (plus tenant, audience, and policy), rather than just `startsWith("ORDER_")` if that could enable privilege escalation.

### Trade-offs of Fetching Permissions During Authentication

If the converter queries a DB or policy service to build authorities, evaluate:

- **Latency:** every authentication may add I/O or retries.
- **Availability:** if the role source fails, it must **fail closed**, never granting default permissions.
- **Revocation:** roles may change between token issuance and request authentication.
- **Scope/token semantics:** internal roles must never expand functionality beyond the scopes granted to the client.
- **Tenant:** roles often belong to a tenant or resource; caching solely by subject is insufficient if it ignores issuer/tenant.
- **Caching:** if caching authorities, choose TTL and invalidation based on permission sensitivity.
- **Resource authorization:** even verified roles do not replace per-record permissions.

In many systems, the converter should remain **fast and purely token-driven**; membership, owner, and sharing checks belong in the service and repository layers where full resource context exists. Avoid turning the converter into the home for all business policies.

### Do Not `subscribe()` or `block()` Inside the Converter

Avoid:

~~~java
// NO: spawns an independent subscription without properly awaiting results.
roleService.findAllowedRoles(...).subscribe(role -> addAuthority(role));

// NO: blocks the event-loop and spawns another subscription.
List<String> roles = roleService.findAllowedRoles(...).collectList().block();
~~~

Instead, **return `Flux<GrantedAuthority>`** and let WebFlux/Spring Security manage subscription within the authentication pipeline.

## 9. How Does `ReactiveJwtAuthenticationConverterAdapter` Differ?

Spring Security has a similarly named adapter:

**`ReactiveJwtAuthenticationConverterAdapter`**.

These two adapters serve **different purposes**:

| Class | Wrapped input | Reactive output type |
| --- | --- | --- |
| `ReactiveJwtGrantedAuthoritiesConverterAdapter` | `Converter<Jwt, Collection<GrantedAuthority>>` | `Converter<Jwt, Flux<GrantedAuthority>>` |
| `ReactiveJwtAuthenticationConverterAdapter` | `Converter<Jwt, AbstractAuthenticationToken>` | `Converter<Jwt, Mono<AbstractAuthenticationToken>>` |

### Using the Authentication Adapter When Migrating from Servlet

If a project already has a synchronous `JwtAuthenticationConverter` with pure claim-mapping policies, you can wrap the whole converter:

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverterAdapter;

JwtGrantedAuthoritiesConverter permissions =
    new JwtGrantedAuthoritiesConverter();
permissions.setAuthoritiesClaimName("permissions");
permissions.setAuthorityPrefix("PERMISSION_");

JwtAuthenticationConverter servletStyle =
    new JwtAuthenticationConverter();
servletStyle.setJwtGrantedAuthoritiesConverter(permissions);

ReactiveJwtAuthenticationConverterAdapter reactive =
    new ReactiveJwtAuthenticationConverterAdapter(servletStyle);
~~~

Then configure:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
    jwt.jwtAuthenticationConverter(reactive)))
~~~

This is a way to **reuse a synchronous converter**; it does not turn synchronous work into non-blocking execution. If the old converter performs blocking I/O, redesign it rather than merely wrapping it in an adapter.

### Which Approach Should You Choose?

- **Only changing claim/prefix/delimiter:** `JwtGrantedAuthoritiesConverter` + `ReactiveJwtGrantedAuthoritiesConverterAdapter`.
- **Already have a full Servlet-style `JwtAuthenticationConverter`:** `ReactiveJwtAuthenticationConverterAdapter` can be used.
- **Need to combine multiple pure-claim sources:** synchronous delegating converter + adapter, or a converter returning `Flux`.
- **Need permissions from a reactive service:** custom `Converter<Jwt, Flux<GrantedAuthority>>` with clean publisher composition and policy.

Check the **generic types** and API of your current Spring Security version; similar class names are a frequent source of compile errors or wiring the wrong converter type.

## 10. Principal Name and Identity Mapping

`ReactiveJwtAuthenticationConverter` does not only produce authorities; it also determines the principal name for `JwtAuthenticationToken`.

By common default, the principal name is derived from the JWT's **`sub`**. Example:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "a6be8cf9",
  "preferred_username": "alice",
  "scope": "orders.read"
}
~~~

If a project wants `Authentication.getName()` to display `preferred_username`, on versions supporting `setPrincipalClaimName(...)`:

~~~java
ReactiveJwtAuthenticationConverter converter =
    new ReactiveJwtAuthenticationConverter();
converter.setPrincipalClaimName("preferred_username");
~~~

This only changes how the `Authentication` name is populated. **It does not alter the JWT `sub`, grant extra authorities, or turn a username into an immutable ownership key.**

In a multi-issuer Resource Server, durable identity often requires the verified **`(iss, sub)`** pair mapped to an internal user ID. Emails and usernames can change, so never use `preferred_username` as proof of record ownership.

With **Client Credentials**, the token may represent a **machine client** rather than a human user; owner/tenant policies and `getName()` must follow the client identity contract rather than assuming every `sub` is a user ID.

## 11. Reading Authorities from Reactor `SecurityContext`

Once the converter successfully creates `JwtAuthenticationToken`, Spring Security WebFlux places the `Authentication` into the **SecurityContext inside the Reactor Context**, making it readable by downstream publishers.

In a reactive service:

~~~java
import java.util.List;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

public Mono<List<String>> currentAuthorities() {
    return ReactiveSecurityContextHolder.getContext()
        .flatMap(context ->
            Mono.justOrEmpty(context.getAuthentication()))
        .map(Authentication::getAuthorities)
        .map(authorities -> authorities.stream()
            .map(GrantedAuthority::getAuthority)
            .toList());
}
~~~

`ReactiveSecurityContextHolder.getContext()` returns **`Mono<SecurityContext>`**, not a synchronous `SecurityContext`. It resolves at **subscription time** within the request context.

Do not write:

~~~java
// Unsuitable in a WebFlux request flow:
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
~~~

because Servlet-style ThreadLocal `SecurityContextHolder` **is not the default identity source for Reactor subscribers**.

### Accessing the JWT in a Reactive Service

~~~java
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import reactor.core.publisher.Mono;

public Mono<Jwt> currentJwt() {
    return ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx ->
            Mono.justOrEmpty(ctx.getAuthentication()))
        .ofType(JwtAuthenticationToken.class)
        .map(JwtAuthenticationToken::getToken)
        .switchIfEmpty(Mono.error(
            new AuthenticationCredentialsNotFoundException(
                "JWT Authentication required")));
}
~~~

In a JWT Resource Server, `JwtAuthenticationToken.getToken()` returns the decoder-processed `Jwt`. For opaque tokens, the principal is typically `OAuth2AuthenticatedPrincipal` and the `Authentication` is typically `BearerTokenAuthentication`; **never blindly cast an opaque principal to `Jwt`**.

### Do Not `block()` or `subscribe()` to Fetch Identity

Avoid:

~~~java
// DO NOT: blocks on event-loop, independent subscription.
Jwt jwt = currentJwt().block();

// DO NOT: fire-and-forget, does not preserve lifecycle/context.
currentAuthorities().subscribe(System.out::println);
~~~

Compose publishers so the framework subscribes inside the HTTP request flow. `publishOn`/`subscribeOn` within the same Reactor subscription do not lose the Reactor Context on their own; the risk typically comes from **detaching subscriptions** or bridging to callbacks/executors that do not propagate context.

## 12. HTTP Authorization, Method Security, and Object-Level Permissions

Suppose the converter produces:

~~~text
SCOPE_orders.read
SCOPE_orders.write
ROLE_ORDER_EDITOR
PERMISSION_orders.export
~~~

In WebFlux, you can use `authorizeExchange`:

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .pathMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .pathMatchers("/api/reports/export")
        .hasAuthority("PERMISSION_orders.export")
    .anyExchange().authenticated())
~~~

**Matcher ordering matters.** Place the specific matcher for `/api/reports/export` before broader matchers if patterns overlap; never let a broad rule accidentally match a sensitive endpoint first.

With `@EnableReactiveMethodSecurity`, services returning `Mono`/`Flux` can be protected with `@PreAuthorize`:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OrderCommandService {

    private final ReactiveOrderRepository orders;
    private final CurrentActorService actors;

    public OrderCommandService(
            ReactiveOrderRepository orders,
            CurrentActorService actors) {
        this.orders = orders;
        this.actors = actors;
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.write') and hasRole('ORDER_EDITOR')")
    public Mono<Void> update(String tenantId, String orderId, UpdateOrderRequest input) {
        return actors.currentActor()
            .flatMap(actor -> orders.updateIfAllowed(
                tenantId, orderId, actor.userId(), input));
    }
}
~~~

The interfaces/DTOs in the example are **custom business domain code**, not Spring Security APIs. `updateIfAllowed(...)` must check that the actor has permission within the **right tenant and order**. Having `SCOPE_orders.write` or `ROLE_ORDER_EDITOR` alone is not enough to edit someone else's order.

A safe rule might look like:

~~~text
Valid access token
    AND has SCOPE_orders.write
    AND has ROLE_ORDER_EDITOR (if policy requires)
    AND actor is an active member of the tenant
    AND (actor is owner OR granted EDIT share)
    AND order is in an editable state
~~~

Reactive method security normally relies on proxies/interceptors; **self-invocation** from one method in the same bean to another annotated with `@PreAuthorize` may bypass the interceptor. Never place all protection in a single annotation while leaving other paths free to query the DB unscoped.

## 13. Custom Converters Do Not Increase the Trustworthiness of Claims

Several risks to distinguish:

**Reading claims from an unverified JWT.** Base64URL-decoding part of the payload on the frontend or in a controller does not verify signatures. Authorities must only be built from a `Jwt` accepted by `ReactiveJwtDecoder` per policy.

**Accepting an ID token as an access token.** An OIDC ID token may carry `groups` or `roles`, yet it is not an access token meant for a Resource Server. Validate `aud`, token type/profile, and token purpose per contract.

**Wrong or spoofed issuer.** With multiple issuers, never fetch arbitrary JWKS URLs from an unverified `iss` claim and trust any keys; use an allowlist and a resolver/decoder aligned with trust boundaries.

**Mapping roles from another resource.** If a JWT contains `resource_access.billing-api.roles`, the Orders API must not convert `BILLING_ADMIN` into an order-management role.

**Mapping every string into a permission.** An array from an issuer with wrong types or non-allowlisted names must never create arbitrary authorities. Enforce schemas, allowlists, and failure policies.

**Retaining revoked permissions.** If roles/memberships inside an older JWT remain valid until `exp`, the converter will read stale claims. Permissions requiring fast revocation may need live policy checks or appropriate token revocation/introspection.

**Leaking data in logs.** Never log raw JWTs, `Authorization` headers, private keys, or sensitive token attributes just to debug mapping. Log controlled metadata such as request ID, verified issuer, required authority name, and error reason at an appropriate level.

## 14. Unit Testing the Converter with `StepVerifier`

Because `ReactiveJwtAuthenticationConverter.convert(jwt)` returns `Mono<AbstractAuthenticationToken>`, you can test results in **Reactor Test** without an HTTP server.

Example mapping `permissions`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtGrantedAuthoritiesConverterAdapter;
import reactor.test.StepVerifier;

class ReactiveJwtAuthenticationConverterTest {

    @Test
    void mapsPermissionsToAuthorities() {
        Jwt jwt = Jwt.withTokenValue("unit-test-token")
            .header("alg", "RS256")
            .issuer("https://auth.example.com/realms/shop")
            .subject("user-42")
            .issuedAt(Instant.parse("2026-01-01T00:00:00Z"))
            .expiresAt(Instant.parse("2031-01-01T00:00:00Z"))
            .claim("scope", "payments.write")
            .claim("permissions", List.of("orders.read", "orders.export"))
            .build();

        JwtGrantedAuthoritiesConverter extractor =
            new JwtGrantedAuthoritiesConverter();
        extractor.setAuthoritiesClaimName("permissions");
        extractor.setAuthorityPrefix("PERMISSION_");

        ReactiveJwtAuthenticationConverter converter =
            new ReactiveJwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(
            new ReactiveJwtGrantedAuthoritiesConverterAdapter(extractor));

        StepVerifier.create(converter.convert(jwt))
            .assertNext(authentication -> {
                assertTrue(authentication instanceof JwtAuthenticationToken);
                assertEquals("user-42", authentication.getName());

                Set<String> names = authentication.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .collect(Collectors.toSet());

                assertTrue(names.contains("PERMISSION_orders.read"));
                assertTrue(names.contains("PERMISSION_orders.export"));
                assertFalse(names.contains("SCOPE_payments.write"));
            })
            .verifyComplete();
    }
}
~~~

**Because the extractor was pointed at `permissions`, the `payments.write` scope is not converted into an authority** in this test. The test also demonstrates that the common default principal name is based on `sub`.

`"unit-test-token"` is a dummy string; a hand-built `Jwt` here **does not prove a valid JWS signature**. This unit test checks only `Jwt` → `Authentication` conversion and authority names.

### Testing Missing Permission Claims

When the issuer omits the claim the converter expects:

~~~java
Jwt jwt = Jwt.withTokenValue("unit-test")
    .header("alg", "RS256")
    .subject("user-42")
    .claim("scope", "orders.read")
    .build();

JwtGrantedAuthoritiesConverter permissions =
    new JwtGrantedAuthoritiesConverter();
permissions.setAuthoritiesClaimName("permissions");
permissions.setAuthorityPrefix("PERMISSION_");

ReactiveJwtAuthenticationConverter converter =
    new ReactiveJwtAuthenticationConverter();
converter.setJwtGrantedAuthoritiesConverter(
    new ReactiveJwtGrantedAuthoritiesConverterAdapter(permissions));

StepVerifier.create(converter.convert(jwt))
    .assertNext(auth -> assertTrue(auth.getAuthorities().isEmpty()))
    .verifyComplete();
~~~

This behavior is helpful when the permission claim is optional. If the profile requires `permissions`, add a **token validator** to reject JWTs with missing/malformed schemas rather than creating an empty `Authentication` and waiting for authorization.

### Testing Nested Roles

Test `OrdersResourceRolesConverter` with a JWT containing `resource_access.orders-api.roles` and `resource_access.billing-api.roles`. Expect only `ROLE_ORDER_EDITOR` when it is allowlisted and properly namespaced; **never** `ROLE_BILLING_ADMIN`. Also test null claims, wrong types, and empty arrays matching the schema supported by the API.

## 15. `WebTestClient`: Testing Mapping in `SecurityWebFilterChain`

To verify the converter **is properly wired into the WebFlux Resource Server**, run an HTTP test through `SecurityWebFilterChain` rather than calling `convert(jwt)` directly.

Spring Boot/WebFlux can use `@SpringBootTest` + `@AutoConfigureWebTestClient`. Mock at the exact **`ReactiveJwtDecoder`** boundary while keeping the real WebFilter, converter, and authorization rules.

Example (assuming a `GET /api/reports/list` endpoint requiring `PERMISSION_orders.read`):

~~~java
import static org.mockito.Mockito.when;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

@SpringBootTest
@AutoConfigureWebTestClient
class WebFluxJwtAuthoritiesTest {

    @Autowired WebTestClient client;

    @MockitoBean
    ReactiveJwtDecoder jwtDecoder;

    @Test
    void tokenWithPermissionIsAllowedByRealChain() {
        when(jwtDecoder.decode("token-with-permission"))
            .thenReturn(Mono.just(jwt(
                "token-with-permission",
                List.of("orders.read"))));

        client.get().uri("/api/reports/list")
            .headers(headers -> headers.setBearerAuth("token-with-permission"))
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void validTokenWithoutPermissionIsForbidden() {
        when(jwtDecoder.decode("token-without-permission"))
            .thenReturn(Mono.just(jwt(
                "token-without-permission",
                List.of("reports.other"))));

        client.get().uri("/api/reports/list")
            .headers(headers -> headers.setBearerAuth("token-without-permission"))
            .exchange()
            .expectStatus().isForbidden();
    }

    private static Jwt jwt(String tokenValue, List<String> permissions) {
        return Jwt.withTokenValue(tokenValue)
            .header("alg", "RS256")
            .issuer("https://auth.example.com/realms/shop")
            .subject("user-42")
            .issuedAt(Instant.parse("2026-01-01T00:00:00Z"))
            .expiresAt(Instant.parse("2031-01-01T00:00:00Z"))
            .claim("aud", List.of("orders-api"))
            .claim("permissions", permissions)
            .build();
    }
}
~~~

**Prerequisites:** the WebFlux app must wire the right `ReactiveJwtAuthenticationConverter` into `SecurityWebFilterChain` and expose the matching endpoint. If the controller requires a DB or additional policy, provide test fixtures. `@MockitoBean` works in newer Spring Test lines (e.g., Spring Framework 6.2+); on older projects, use Spring Boot's `@MockBean` per your version.

This test verifies **Bearer header → WebFilter → mock decoder → reactive converter → authorities → URL authorization**. It **does not** verify real cryptographic signatures, timestamps, audience, or issuer validators because the decoder is mocked. Dedicated decoder/JWKS tests are required to verify those constraints.

### Why `mockJwt()` Alone Is Not Enough to Prove Converter Behavior

Spring Security Test provides `mockJwt()` for `WebTestClient`:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

webTestClient.mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("PERMISSION_orders.read")))
    .get().uri("/api/reports/list")
    .exchange()
    .expectStatus().isOk();
~~~

This is useful for testing **authorization rules** with a pre-built `Authentication`. However, it can **bypass both the real `ReactiveJwtDecoder` and the real `ReactiveJwtAuthenticationConverter`**. Therefore:

| Test type | Proves | Does not prove |
| --- | --- | --- |
| `StepVerifier` calling `convert(jwt)` | Authority/name mapping logic | That the converter is wired into the WebFilter chain |
| `WebTestClient.mutateWith(mockJwt())` | HTTP/method authorization with a test `Authentication` | Real claim mapping and decoder |
| `WebTestClient` Bearer header + mock `ReactiveJwtDecoder` | WebFilter, converter mapping, and authorization | Real signature/JWKS, issuer/audience/time validation |
| Real signed Bearer JWS + real `ReactiveJwtDecoder`/JWKS | Token verification and real WebFlux wiring | Business/DB permissions if fixtures are absent |
| Service/repository integration test | Tenant, owner, sharing, relationships | JWT signatures and web filters if HTTP is not invoked |

Different test layers **complement each other**; never replace all of them with a single passing `mockJwt()` test.

## 16. Common Pitfalls When Using Reactive JWT Converters

### "I wrote a converter bean, yet requests still return 403"

The bean may not have been wired via `jwt.jwtAuthenticationConverter(...)` on the **`SecurityWebFilterChain` handling that endpoint**, or it was accidentally wired to Servlet `HttpSecurity`. If the app has multiple WebFilter chains, verify matchers and ordering.

### "The JWT already has `roles`, why doesn't `hasRole('ADMIN')` work?"

The default converter reads `scope`/`scp`, not `roles`. If roles live in nested JSON, write a schema-aware converter. `hasRole('ADMIN')` normally looks for `ROLE_ADMIN`, not `ADMIN` or `SCOPE_admin`.

### "`setAuthoritiesClaimName('permissions')` made `SCOPE_orders.read` disappear"

Expected when reconfiguring a single extractor to point at a different claim. If you need both scopes and permissions, deliberately combine two extractors. Never blindly merge every permission-like claim regardless of source.

### "I used `ReactiveJwtAuthenticationConverterAdapter` with blocking I/O—is it non-blocking now?"

No. The adapter only converts return types to Reactor; synchronous DB reads or HTTP calls still block the event loop. Use a genuinely reactive service or offload blocking work off the event loop per architectural design.

### "I have `SCOPE_orders.read`, why do I still get 403 when reading order 123?"

The service may require ownership, tenant membership, sharing, or additional method security. **Authorities are functional permissions**, not permission on every specific record.

### "I called `ReactiveSecurityContextHolder.getContext().block()` and got no Authentication"

`getContext()` reads context per subscriber. `block()` creates a separate subscription and can run in the wrong context; blocking is also unsuitable for the WebFlux event loop. Compose publishers instead of blocking.

### "I used `preferred_username` as the owner ID"

Usernames can change or collide; use an issuer-verified identifier and internal mapping, typically based on `(iss, sub)`, then check business permissions.

### "The JWT has an `aud` for another API, yet the converter still created `SCOPE_orders.read`"

That is why audience/profile validators must be placed in the decoder or a trusted verification component **before conversion**. The converter does not make a wrong audience valid and must not be the sole defense against misused tokens.

### "Can I return all authorities and the raw token for debugging?"

Do not. Tokens are credentials, and claims/authorities may expose internal information. Use controlled logging and never store `Authorization` headers or intact JWS strings in metrics/logs.

## 17. Decision Framework for Production Systems

| Data format in JWT | Approach | What to verify |
| --- | --- | --- |
| `scope` string or `scp` array | Default `JwtGrantedAuthoritiesConverter` + reactive adapter | `SCOPE_` prefix, matching rules |
| `permissions` string array | `setAuthoritiesClaimName("permissions")` + custom prefix | Issuer schema and which permissions the API accepts |
| Comma-delimited `permissions` string | Version-supported delimiter or custom converter | Actual regex/delimiter used by issuer |
| Scope plus permissions | Delegating converter or `Flux` merge | Is merging the two permission sources allowed? |
| Top-level `roles` array | Converter with `ROLE_` per policy | How scopes and roles must combine |
| `realm_access.roles` | Custom converter reading nested map | Scope of realm roles vs. resource roles |
| `resource_access.orders-api.roles` | Custom converter selecting client/resource namespace | Never pull roles from another resource |
| Permissions as an array of objects | Custom converter understanding item schema | Never call `toString()` to grant permissions |
| Permissions from a reactive policy service | `Converter<Jwt, Flux<GrantedAuthority>>` | Timeouts, fail-closed, tenant, cache, non-blocking |
| Legacy Servlet converter to reuse | `ReactiveJwtAuthenticationConverterAdapter` | Legacy logic must be purely sync with no blocking I/O |

Before choosing a converter, answer these questions:

1. **Has the token been sufficiently verified?** Signature, issuer, audience, timestamps, token type/profile, and mandatory claims.
2. **Which claim source carries valid permissions for the Orders API?** `scope`, `scp`, `permissions`, or specific roles.
3. **What are the expected authority names?** `SCOPE_...`, `PERMISSION_...`, or `ROLE_...`; rules must match those names.
4. **Should multiple sources be merged or both required?** Avoid inadvertently elevating client privileges.
5. **Is permission data inside nested JSON?** Write a schema-aware parser rather than treating dots as JSONPath.
6. **Does the mapper perform I/O?** If so, use real publishers and evaluate latency/failures without blocking the event loop.
7. **Where are object-level permissions checked?** Tenant/owner/sharing belong in business policies, not just the converter.
8. **Do tests cover the real execution path?** Unit `StepVerifier` and `WebTestClient` with Bearer headers verify distinct layers.

**Key takeaway:** `ReactiveJwtAuthenticationConverter` is the **bridge between a verified JWT and Spring Security `Authentication` in WebFlux**. Default permissions normally map `scope`/`scp` to `SCOPE_...`; for custom claims, configure `JwtGrantedAuthoritiesConverter` with `ReactiveJwtGrantedAuthoritiesConverterAdapter`, or write a `Converter<Jwt, Flux<GrantedAuthority>>` following an explicit schema. **Correct mapping does not replace token verification and does not automatically grant access per tenant or business resource.**
