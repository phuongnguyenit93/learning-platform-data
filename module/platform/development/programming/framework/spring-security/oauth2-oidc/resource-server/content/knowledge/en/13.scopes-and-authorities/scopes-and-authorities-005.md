# JwtGrantedAuthoritiesConverter and Customizing Claim Sources

In **Spring Security OAuth 2.0 Resource Server**, once a JWT access token has been decoded and verified, the application needs to convert permission data inside the JWT into **`GrantedAuthority`** objects to enforce rules such as `hasAuthority("SCOPE_orders.read")`, `hasRole("ADMIN")`, or `@PreAuthorize(...)`. The default component that usually performs this task is **`JwtGrantedAuthoritiesConverter`**.

An Authorization Server can issue access tokens with a string-typed `scope`, an array-typed `scp`, organization-defined `permissions`, or roles nested inside a JSON object. Those formats do not naturally turn into the same set of authorities. The Resource Server must understand **which claim source is trusted**, **what data type the claim has**, **how authority names should be formatted**, and **whether the converter is actually wired into the active authentication chain**.

This lesson focuses on how `JwtGrantedAuthoritiesConverter` works, options for changing the claim source/prefix/delimiter depending on the Spring Security version, combining multiple permission sources, and handling nested claims in JWTs for a Servlet Resource Server API.

## 1. From access token to `GrantedAuthority` in Spring Security

Suppose the Orders API receives a request:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <access-token>
~~~

The client sends an **access token** issued by the Authorization Server. The Resource Server must authenticate the token first, and only then enforce permissions.

~~~mermaid
flowchart TD
    A["Client sends Bearer JWT"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["JwtAuthenticationProvider"]
    C --> D["JwtDecoder / NimbusJwtDecoder"]
    D --> E{"Signature, issuer, exp, aud, profile valid?"}
    E -- "No" --> F["Authentication rejected: typically 401"]
    E -- "Yes" --> G["JwtAuthenticationConverter"]
    G --> H["JwtGrantedAuthoritiesConverter / custom Converter"]
    H --> I["GrantedAuthority collection"]
    I --> J["JwtAuthenticationToken"]
    J --> K["SecurityContext"]
    K --> L{"Authorization: sufficient permissions?"}
    L -- "No" --> M["Permission denied: typically 403"]
    L -- "Yes" --> N["Controller / Service"]
~~~

Different layers have distinct responsibilities:

| Component | Responsibility |
| --- | --- |
| `JwtDecoder` | Verifies the token, signature, and token conditions configured by the application |
| `Jwt` | Represents the token processed by the decoder, including headers and claims |
| `JwtGrantedAuthoritiesConverter` | Converts one or a group of permission claims into a `Collection<GrantedAuthority>` |
| `JwtAuthenticationConverter` | Uses the authorities converter and principal name to build an `AbstractAuthenticationToken`, typically `JwtAuthenticationToken` |
| `SecurityContext` | Holds the request's `Authentication` after successful authentication |
| `AuthorizationFilter` / method security | Matches authorities against access conditions |

**A claim is not an authority until it has been mapped.** For example, a JWT containing `"roles":["ADMIN"]` does not mean Spring Security creates `ROLE_ADMIN` by default. A `hasRole("ADMIN")` rule can return 403 even with a valid JWT if no converter maps it properly.

More importantly: **the converter does not replace JWT verification**. It only uses data already accepted by the decoder. Valid signature, correct issuer, correct audience, and token validators must all remain enforced when customizing authorities.

## 2. Default: `scope` or `scp` to `SCOPE_`-prefixed authorities

Under the common default configuration in Spring Security Resource Server, `JwtGrantedAuthoritiesConverter` looks for a permission-range claim among well-known names, typically **`scope`** or **`scp`**.

Example access token carrying:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "scope": "orders.read orders.write"
}
~~~

Spring Security typically converts:

~~~text
JWT claim:
scope = "orders.read orders.write"

JwtGrantedAuthoritiesConverter:
"orders.read"  -> SimpleGrantedAuthority("SCOPE_orders.read")
"orders.write" -> SimpleGrantedAuthority("SCOPE_orders.write")
~~~

With `scp` as a JSON array:

~~~json
{
  "scp": ["orders.read", "orders.export"]
}
~~~

The corresponding result can be:

~~~text
SCOPE_orders.read
SCOPE_orders.export
~~~

Points to remember:

- The default prefix is typically **`SCOPE_`**, so check with `hasAuthority("SCOPE_orders.read")` rather than `hasAuthority("orders.read")`.
- The `scope` string usually contains **space-separated** scopes per the OAuth 2.0 model.
- If the claim uses an array, each valid element typically corresponds to one scope name.
- If the JWT has none of the permission claims recognized by the converter, the result is typically an **empty authorities collection**.
- If a token has both `scope` and `scp`, do not assume the converter automatically **merges both claims**. Which claim name is selected depends on the converter's lookup order and detection logic. If business logic requires merging, configure it explicitly.

A payload with `"permissions": ["orders.read"]` or `"roles": ["ADMIN"]` will **not be mapped automatically** by a converter reading only the default `scope`/`scp`.

### Scope and authority are not identical concepts

**Scope** is data carrying permission semantics granted by the Authorization Server in an OAuth 2.0 context. **GrantedAuthority** is the object Spring Security uses to match authorization policies inside the application.

The Resource Server can turn scopes into authorities, but it can also create authorities from roles, permissions, or other verified claims. `SCOPE_` itself is just a **naming convention**. It does not prove the user owns a specific record or automatically grant access to every tenant.

## 3. Options on `JwtGrantedAuthoritiesConverter`

Commonly used methods:

| API | Purpose | Example |
| --- | --- | --- |
| `setAuthoritiesClaimName(String)` | Specifies the claim carrying permissions instead of looking up `scope`/`scp` by default | `"permissions"` |
| `setAuthorityPrefix(String)` | Changes the prefix for generated authorities | `"PERMISSION_"`, `"ROLE_"`, or `""` |
| `setAuthoritiesClaimDelimiter(String)` | Changes the regular expression used to split string claims | `","` or `"\\s+"` |

**Version note:** `setAuthoritiesClaimDelimiter(...)` was added in newer Spring Security lines (e.g., Spring Security 6.1). Do not copy this call into an older version that lacks the API. If your dependency does not support it, upgrade appropriately or use a custom `Converter<Jwt, Collection<GrantedAuthority>>` to split strings per the issuer's convention.

### 3.1. Switching the source to the `permissions` claim

Suppose the issuer issues:

~~~json
{
  "sub": "user-42",
  "aud": ["orders-api"],
  "permissions": ["orders.read", "orders.export"]
}
~~~

We want to produce authorities `PERMISSION_orders.read` and `PERMISSION_orders.export`.

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

JwtGrantedAuthoritiesConverter permissions =
    new JwtGrantedAuthoritiesConverter();

permissions.setAuthoritiesClaimName("permissions");
permissions.setAuthorityPrefix("PERMISSION_");
~~~

When used to convert a JWT, this converter reads **`permissions`**, and no longer reads `scope` by default as before. An API can check:

~~~java
.requestMatchers("/api/reports/**")
    .hasAuthority("PERMISSION_orders.export")
~~~

This is a decision about **the contract between the issuer and the API**. Do not switch to another claim name just because its name looks close to "permissions"; understand under which policy the Authorization Server actually grants those values.

### 3.2. Changing the prefix for a claim holding roles

If the issuer provides:

~~~json
{
  "roles": ["ADMIN", "SUPPORT"]
}
~~~

you can configure:

~~~java
JwtGrantedAuthoritiesConverter roles =
    new JwtGrantedAuthoritiesConverter();
roles.setAuthoritiesClaimName("roles");
roles.setAuthorityPrefix("ROLE_");
~~~

Expected result:

~~~text
ROLE_ADMIN
ROLE_SUPPORT
~~~

These authorities are compatible with the expression:

~~~java
hasRole("ADMIN")
~~~

because `hasRole("ADMIN")` in standard Spring Security configuration checks for authorities prefixed with `ROLE_`. **Do not write `hasRole("ROLE_ADMIN")` out of habit**: in many expression/DSL APIs, `hasRole` adds the prefix automatically and may reject arguments that already include the prefix. To check the full name, use `hasAuthority("ROLE_ADMIN")`.

**Changing the prefix does not turn a role into a scope.** `ROLE_ADMIN` and `SCOPE_admin` are only equivalent if the application policy deliberately defines them as equivalent, which generally should not be done implicitly.

### 3.3. Changing the delimiter for string claims

For example, an issuer uses the claim:

~~~json
{
  "permissions": "orders.read,orders.write,orders.export"
}
~~~

If your Spring Security version provides `setAuthoritiesClaimDelimiter(...)`, you can do:

~~~java
JwtGrantedAuthoritiesConverter permissions =
    new JwtGrantedAuthoritiesConverter();
permissions.setAuthoritiesClaimName("permissions");
permissions.setAuthorityPrefix("PERMISSION_");
permissions.setAuthoritiesClaimDelimiter(",");
~~~

The string is then split on commas. In many versions, the delimiter is a **regular expression (regex)**, so watch out for special characters. For strings separated by one or more whitespace characters:

~~~java
permissions.setAuthoritiesClaimDelimiter("\\s+");
~~~

For an **array** `["orders.read","orders.write"]`, the converter typically reads elements as a collection and does not need string splitting by delimiter. If the issuer emits a claim as an array of objects such as `[{"name":"orders.read"}]`, a simple `JwtGrantedAuthoritiesConverter` is not the right choice; use a custom converter with type checking.

In particular, distinguish delimiters for custom permission strings from the standard scope format in OAuth 2.0: do not treat commas as the standard delimiter for `scope` unless the Authorization Server issues tokens under that convention.

## 4. Wiring the converter into `JwtAuthenticationConverter`

Creating a `JwtGrantedAuthoritiesConverter` is **not enough**: you must plug it into `JwtAuthenticationConverter`, and then wire the resulting converter into the Resource Server configuration handling requests.

Example of a Spring Boot Servlet API accepting `permissions`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter authorities =
            new JwtGrantedAuthoritiesConverter();
        authorities.setAuthoritiesClaimName("permissions");
        authorities.setAuthorityPrefix("PERMISSION_");

        JwtAuthenticationConverter authenticationConverter =
            new JwtAuthenticationConverter();
        authenticationConverter.setJwtGrantedAuthoritiesConverter(authorities);
        return authenticationConverter;
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            JwtAuthenticationConverter jwtAuthenticationConverter
    ) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/api/reports/**")
                    .hasAuthority("PERMISSION_orders.export")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
                jwt.jwtAuthenticationConverter(jwtAuthenticationConverter)))
            .build();
    }
}
~~~

Notes:

1. `jwtAuthenticationConverter(...)` is where you **attach** the converter to the JWT Resource Server DSL.
2. `setJwtGrantedAuthoritiesConverter(...)` replaces the default authority source for that `JwtAuthenticationConverter`; if it only reads `permissions`, then `scope`/`scp` may no longer be converted into authorities.
3. `hasAuthority(...)` must use the **exact post-mapping name**. If the prefix is `PERMISSION_` while the rule still requires `SCOPE_`, requests can be rejected with 403.
4. Disabling CSRF in this example fits APIs using only **Bearer tokens**, not relying on cookies automatically sent by browsers for authentication. For applications with sessions/cookies, design CSRF protection accordingly.
5. The converter only handles **permissions mapped from the JWT**. The API must still check whether the user is allowed to operate on the specific resource.

Configuration usually includes the JWT issuer:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

`issuer-uri` configures the trusted issuer via Spring Security's supported mechanism. When using a custom decoder, you still must check signature, issuer, audience, expiration, and required claims/profiles. **Customizing authorities does not replace the audience validator**.

## 5. Customizing the principal name is a separate concern

`JwtAuthenticationConverter` typically sets the principal name from the JWT's `sub`. Switching the authority source to `permissions` **does not simultaneously** change the principal name.

For example, the issuer provides:

~~~json
{
  "sub": "e18d76f1",
  "preferred_username": "alice",
  "permissions": ["orders.read"]
}
~~~

If the display/login name needs to be `preferred_username`:

~~~java
JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
converter.setJwtGrantedAuthoritiesConverter(permissions);
converter.setPrincipalClaimName("preferred_username");
~~~

Then `Authentication.getName()` can be based on `preferred_username`. However, changing `getName()` **does not change the immutable identity of the principal**. For record ownership logic, use a stable identifier guaranteed by the issuer and bound to the issuer/tenant; display usernames can change or collide.

In a multi-issuer system, using `sub` alone while ignoring `iss` also risks identifier collisions. System-level identity should be defined within the appropriate trust boundary rather than treating every `sub` worldwide as unique.

## 6. Combining two sources: keeping scope and adding permissions

A common requirement is:

- Keep `scope`/`scp` for rules like `SCOPE_orders.read`.
- Also read `permissions` for `PERMISSION_orders.export`.

If you only call `setAuthoritiesClaimName("permissions")`, the new converter typically **replaces** the default permission source. To keep both, you can use **`DelegatingJwtGrantedAuthoritiesConverter`** in versions that provide this API.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.authentication.DelegatingJwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    // Read scope/scp using the default convention.
    JwtGrantedAuthoritiesConverter scopes =
        new JwtGrantedAuthoritiesConverter();

    // Read the issuer's custom permissions claim.
    JwtGrantedAuthoritiesConverter permissions =
        new JwtGrantedAuthoritiesConverter();
    permissions.setAuthoritiesClaimName("permissions");
    permissions.setAuthorityPrefix("PERMISSION_");

    DelegatingJwtGrantedAuthoritiesConverter allAuthorities =
        new DelegatingJwtGrantedAuthoritiesConverter(
            scopes,
            permissions
        );

    JwtAuthenticationConverter authentication =
        new JwtAuthenticationConverter();
    authentication.setJwtGrantedAuthoritiesConverter(allAuthorities);
    return authentication;
}
~~~

Suppose the JWT has:

~~~json
{
  "scope": "orders.read",
  "permissions": ["orders.export"]
}
~~~

Result:

~~~text
SCOPE_orders.read
PERMISSION_orders.export
~~~

`DelegatingJwtGrantedAuthoritiesConverter` invokes each component converter and aggregates authorities; in supported versions, this reduces duplicate authorities and preserves a useful order for reading/debugging. However, **never rely on authority ordering to make authorization decisions**. Permission depends on whether an authority name is present in the collection.

If your project does not yet have `DelegatingJwtGrantedAuthoritiesConverter`, you can write a custom `Converter<Jwt, Collection<GrantedAuthority>>` that merges results from both converters using a `LinkedHashSet`; handle null/empty results according to each converter's contract.

### Preserving granted permission relationships

Simply having two claims does not mean they should always be unioned. For example, `scope` represents OAuth 2.0 permissions granted to a **specific client**, whereas `roles` may describe internal user roles. If the API automatically takes **all user roles** and gives the client every corresponding permission, it may inadvertently bypass the scope boundaries intended by the Authorization Server.

An API may require both conditions:

~~~text
Access token has SCOPE_orders.write
                 AND
Principal has ROLE_ORDER_EDITOR
                 AND
Allowed to edit this specific order/tenant
~~~

When designing, explicitly decide whether an authority **expands** permissions granted to the client or acts as an **additional** condition that must be satisfied. Do not merge blindly so that a powerful role overrides access token restrictions.

## 7. When permissions live inside nested JSON objects

Some issuers (for example, Keycloak-style configurations) may emit claims such as:

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
    "payments-api": {
      "roles": ["PAYMENT_VIEWER"]
    }
  }
}
~~~

Here `realm_access` and `resource_access` are **JSON objects**, not scope strings. `JwtGrantedAuthoritiesConverter.setAuthoritiesClaimName("realm_access.roles")` **does not automatically mean** nested path traversal. With the standard converter, claim names are looked up at the **top-level claim map**; dots do not denote JSONPath.

To read nested claims, use a dedicated `Converter<Jwt, Collection<GrantedAuthority>>`. The following example:

- Preserves default authorities from `scope`/`scp`.
- Reads realm-level roles at `realm_access.roles`.
- Reads only roles intended for **`orders-api`** at `resource_access["orders-api"].roles`.
- Restricts generated authorities to names accepted by the API policy.

~~~java
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

public final class OrdersAuthoritiesConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    private static final String ORDERS_RESOURCE = "orders-api";

    private static final Set<String> SUPPORTED_ROLES =
        Set.of("USER", "REPORT_VIEWER", "ORDER_EDITOR");

    private final JwtGrantedAuthoritiesConverter scopes =
        new JwtGrantedAuthoritiesConverter();

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        Set<GrantedAuthority> result = new LinkedHashSet<>();

        Collection<GrantedAuthority> scopeAuthorities = scopes.convert(jwt);
        if (scopeAuthorities != null) {
            result.addAll(scopeAuthorities);
        }

        Object realmAccess = jwt.getClaim("realm_access");
        if (realmAccess instanceof Map<?, ?> realm) {
            addRoles(result, realm.get("roles"));
        }

        Object resourceAccess = jwt.getClaim("resource_access");
        if (resourceAccess instanceof Map<?, ?> resources) {
            Object orders = resources.get(ORDERS_RESOURCE);
            if (orders instanceof Map<?, ?> ordersClaims) {
                addRoles(result, ordersClaims.get("roles"));
            }
        }
        return result;
    }

    private static void addRoles(
            Set<GrantedAuthority> authorities,
            Object rawRoles) {

        if (!(rawRoles instanceof Collection<?> roles)) {
            return;
        }
        for (Object value : roles) {
            if (value instanceof String role
                    && SUPPORTED_ROLES.contains(role)) {
                authorities.add(
                    new SimpleGrantedAuthority("ROLE_" + role));
            }
        }
    }
}
~~~

This converter can be wired via:

~~~java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(
        new OrdersAuthoritiesConverter());
    return converter;
}
~~~

The example above **intentionally excludes** `PAYMENT_VIEWER` from `payments-api` from the Orders API's authorities. In addition, `SUPPORTED_ROLES` illustrates a way to limit roles understood by the API. Actual names must follow the designed permissions and what the issuer emits.

**Security note:** Realm-level roles may apply more broadly than a single resource; mapping `ROLE_ORDER_EDITOR` from such a broad source is a decision that warrants careful review. When scoping to a client/resource is required, only map roles from the proper namespace and add rules requiring appropriate scopes. Never treat the presence of a role in a JWT as proof that the principal may act on every account or tenant.

## 8. Converting structured claims that are not string arrays

A JWT may carry a shape like:

~~~json
{
  "permissions": [
    {"resource": "orders", "action": "read"},
    {"resource": "orders", "action": "export"}
  ]
}
~~~

This is an **array of JSON objects**. A simple `JwtGrantedAuthoritiesConverter` setup will not fit because the elements are not string permission names. If the contract genuinely uses such a structure, a custom converter must check types and **build authorities according to intentional rules**:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

public static Collection<GrantedAuthority> mapStructuredPermissions(Jwt jwt) {
    Object raw = jwt.getClaim("permissions");
    List<GrantedAuthority> result = new ArrayList<>();

    if (!(raw instanceof Collection<?> entries)) {
        return result;
    }

    for (Object entry : entries) {
        if (!(entry instanceof Map<?, ?> permission)) {
            continue;
        }

        Object resource = permission.get("resource");
        Object action = permission.get("action");

        if ("orders".equals(resource) && "read".equals(action)) {
            result.add(new SimpleGrantedAuthority("PERMISSION_orders.read"));
        } else if ("orders".equals(resource)
                && "export".equals(action)) {
            result.add(new SimpleGrantedAuthority("PERMISSION_orders.export"));
        }
    }
    return result;
}
~~~

The example only accepts **known permission pairs** and skips structures that do not match the contract. In a real system, explicitly define how malformed data is handled: some policies need to **reject the entire token** rather than silently ignoring invalid permissions. This decision belongs to the Resource Server's security design, not an automatic feature of the default converter.

### Do not call `toString()` on arbitrary elements

If code converts an object to a string and adds a prefix, it might generate an authority like:

~~~text
PERMISSION_{resource=orders, action=read}
~~~

This is not a defined business permission and can cause hard-to-diagnose authorization bugs. A claim must be interpreted **according to the schema** agreed upon by the issuer and API, not by arbitrarily calling `String.valueOf(...)`.

## 9. `hasAuthority`, `hasRole`, and method security after mapping

Suppose the converter produces:

~~~text
SCOPE_orders.read
SCOPE_orders.write
ROLE_ORDER_EDITOR
PERMISSION_orders.export
~~~

Endpoints can be protected with:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .requestMatchers(HttpMethod.GET, "/api/reports/export")
        .hasAuthority("PERMISSION_orders.export")
    .anyRequest().authenticated())
~~~

Pay attention to **request matcher order**: if a broad GET rule `/api/orders/**` precedes a more specific GET rule with stricter requirements within the same path space, the specific rule may never be evaluated. Order matchers by appropriate specificity.

To combine a scope and a role in the same condition, you can use method security:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.write') and hasRole('ORDER_EDITOR')")
    public void updateOrder(String orderId) {
        // Beyond the rule above, the service must check tenant and access to orderId.
    }
}
~~~

To use `@PreAuthorize`, the application must enable method security per the corresponding version, for example:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

`hasRole('ORDER_EDITOR')` typically looks for the `ROLE_ORDER_EDITOR` authority. If your converter creates `APP_ROLE_ORDER_EDITOR`, the expression must be adjusted to use the exact authority name.

**Important:** even after checking `SCOPE_orders.write` and `ROLE_ORDER_EDITOR`, the service must still verify that the principal has permission to **edit the specific orderId belonging to the right tenant**. This is object-level authorization and cannot be inferred solely from global authorities.

## 10. The difference between claim conversion and token validation

A Resource Server can encounter different failure modes:

| Case | Layer involved | Typical behavior |
| --- | --- | --- |
| Expired JWT or invalid signature | Decoder/validators | Authentication fails, typically **401** |
| JWT issued for a different audience | Audience validation | Must be rejected at the authentication layer per API policy |
| Valid JWT missing the `scope`/`permissions` required by the rule | Authority mapping + authorization | Converter produces few/no authorities; rule typically returns **403** |
| JWT has string `permissions` while converter expects another format | Claim mapping | Expected authority is missing; may fail mapping depending on implementation |
| JWT has `roles` while converter only reads `scope` | Authority mapping | `hasRole(...)` typically returns **403** |
| JWT has matching authority but user does not own the record | Business authorization | Typically **403** or a designed business response |

**Never resolve a 403 caused by mapping by disabling signature checks or removing the audience validator.** Instead, inspect what `Authentication.getAuthorities()` contains after token validation and compare it against the names required by rules.

From a security standpoint:

- **Issuer:** accept only tokens issued by a configured trusted source.
- **Audience:** accept only access tokens intended for this API.
- **Expiration, token type:** `exp`, `nbf`, mandatory claims, and appropriate profile.
- **Authorities:** convert claims strictly per contract without arbitrarily expanding permissions.
- **Business policy:** restrict operations to the right record, tenant, and context.

The JWT authority mapping layer must run **after** the token has been verified per the decoder contract. Base64URL-decoding the payload and building authorities from unverified JSON is **unsafe**.

## 11. When the claim comes from an OIDC ID token or a different issuer's token

An OIDC ID token can carry `roles`, `groups`, or custom claims. However, **an ID token is for the OIDC client to authenticate the user**; it is **not** automatically a valid access token for a Resource Server.

For example, the same issuer issues:

- **ID token** with `aud` set to the login client `orders-web`.
- **Access token** with `aud` set to `orders-api` and scope `orders.read`.

The Resource Server must validate access tokens for the right audience and profile. Never accept an ID token and map `groups` into API authorities merely because the ID token has a valid signature.

A multi-issuer system can also have two claims named `roles` with completely different meanings. Issuer A defines `ADMIN` as order administration; Issuer B uses `ADMIN` for UI administration in another application. You cannot merge them into a single system-wide `ROLE_ADMIN` without policies distinguishing issuer, audience, and tenant.

When multiple issuers are needed, mechanisms like `AuthenticationManagerResolver<HttpServletRequest>` or multiple `SecurityFilterChain` instances can be designed around an allowlist and token contracts. Each branch should have its own decoder, validators, and converter if permission schemas differ. Never trust any unverified `iss` or JWKS URL self-declared by a token.

## 12. Common pitfalls when customizing authority sources

### Pitfall 1: Creating a converter without wiring it into the Resource Server

~~~java
// Creating a bean or object without linking it to jwtAuthenticationConverter
// of the SecurityFilterChain handling the endpoint.
JwtGrantedAuthoritiesConverter converter =
    new JwtGrantedAuthoritiesConverter();
converter.setAuthoritiesClaimName("permissions");
~~~

Make sure `JwtAuthenticationConverter` uses that converter and the Resource Server DSL calls `jwtAuthenticationConverter(...)` on the right filter chain. If the application has multiple chains, a converter on chain A does not automatically apply to chain B.

### Pitfall 2: Switching the source claim and losing scopes

When switching from the default `scope` to `permissions`, scope authorities may vanish. If both are needed, use `DelegatingJwtGrantedAuthoritiesConverter` or an explicit custom converter.

### Pitfall 3: Changing the prefix without updating rules

The converter produces `PERMISSION_orders.read`, yet the rule still checks `SCOPE_orders.read`. Valid tokens still receive 403 because Spring Security compares authority names **literally**, without inferring any equivalence between prefixes.

### Pitfall 4: Treating a nested claim as a dot path

`setAuthoritiesClaimName("realm_access.roles")` is not JSONPath. When `realm_access` is an object containing `roles`, you need a converter that reads map and collection structures.

### Pitfall 5: Ignoring the actual JSON type

An issuer might emit:

~~~json
{
  "scope": "orders.read orders.write",
  "scp": ["orders.read"],
  "roles": ["USER"],
  "permissions": [{"name": "orders.export"}]
}
~~~

A single simple coercion rule cannot fit all of them. Define the schema and mapping per claim, and handle mismatched types per policy.

### Pitfall 6: Turning every role into a client permission

A user-level `roles` claim may span multiple applications. If a client was only granted `orders.read`, turning an `ADMIN` role into permission to delete orders can exceed the intended scope. Design rules combining scopes and business permissions, distinguishing realm-level roles from resource-specific roles.

### Pitfall 7: Confusing `ROLE_` and `SCOPE_`

`hasRole("ADMIN")` typically pairs with `ROLE_ADMIN`. `hasAuthority("SCOPE_admin")` pairs with the exact authority `SCOPE_admin`. These are two separate permission namespaces and do not substitute for one another.

### Pitfall 8: Debugging by logging the JWT

A Bearer access token is a credential that can be used to call the API. Never log full tokens, authorization headers, or sensitive claim data. When diagnosing, log request IDs, verified issuers, error categories, and expected authority names at an appropriate level.

## 13. Testing the converter at the right layer

A converter can be tested directly without an HTTP server. Example testing `permissions`:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Collection;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

class JwtGrantedAuthoritiesConverterTest {

    @Test
    void mapsPermissionsFromChosenClaim() {
        Jwt jwt = Jwt.withTokenValue("unit-test-only")
            .header("alg", "RS256")
            .subject("user-42")
            .claim("permissions", List.of("orders.read", "orders.export"))
            .claim("scope", "payments.write")
            .build();

        JwtGrantedAuthoritiesConverter converter =
            new JwtGrantedAuthoritiesConverter();
        converter.setAuthoritiesClaimName("permissions");
        converter.setAuthorityPrefix("PERMISSION_");

        Collection<GrantedAuthority> granted = converter.convert(jwt);
        List<String> names = granted.stream()
            .map(GrantedAuthority::getAuthority)
            .toList();

        assertTrue(names.contains("PERMISSION_orders.read"));
        assertTrue(names.contains("PERMISSION_orders.export"));
        assertFalse(names.contains("SCOPE_payments.write"));
    }
}
~~~

This test shows **changing the claim source takes effect**: `scope` is not mapped once the converter is instructed to read only `permissions`. The `Jwt` built with `withTokenValue(...)` is a unit test object, **not a JWT with a verified signature**.

An integration test should further verify:

1. A real token signed with a test key trusted by `JwtDecoder`.
2. The token matches the issuer, audience, expiration, and profile accepted by the API.
3. `SecurityFilterChain` uses the intended `JwtAuthenticationConverter`.
4. Requests with sufficient authorities reach the endpoint, and requests lacking permissions are rejected properly.
5. Malformed data or claims disallowed by the issuer do not become unintended authorities.

Helpers such as `jwt()` in **Spring Security Test MockMvc** are helpful for testing authorization with a mocked `Authentication`, but they typically **bypass the real JwtDecoder and the claim-conversion step in the Resource Server chain**. Therefore, mocking `jwt()` with direct authorities does not prove `JwtGrantedAuthoritiesConverter` is wired properly in production.

## 14. Choosing a permission mapping strategy per model

| Token model | Typically suitable mapping | What to ensure |
| --- | --- | --- |
| String `scope` or array `scp` | Default converter | `SCOPE_...` rules match the scopes issued by the issuer |
| String-array `permissions` | `setAuthoritiesClaimName("permissions")`, dedicated prefix | Clear permission schema; rules use the right prefix |
| Direct string-array `roles` | Converter with `ROLE_` if policy allows | Do not bypass scopes and client/resource boundaries |
| Independent `scope` and `permissions` | `DelegatingJwtGrantedAuthoritiesConverter` | Decide properly between merging or requiring multiple conditions |
| Nested `realm_access.roles` | Custom converter reading objects | Do not assume dot-separated claim names act as JSONPath |
| Nested `resource_access[client].roles` | Custom converter selecting a specific resource namespace | Do not pull in roles from other applications |
| Object-array `permissions` | Custom converter validating schema and allowlist | Never blindly call `toString()` on arbitrary structures |
| Multiple issuers with different permission claims | Separate mappings per trusted issuer/chain | Never merge permissions across different trust domains |

When designing API protection cleanly, answer three questions: **which claim is actually the source of granted permissions**, **which Spring Security authority names must be created**, and **how do API rules check those authorities alongside resource-level permissions**.

## 15. Core takeaways to remember

- **`JwtGrantedAuthoritiesConverter`** converts JWT scopes/permission claims into `GrantedAuthority` instances for Spring Security.
- Common default: `scope` or `scp` → **`SCOPE_...`**. It does not automatically extract arbitrary `roles`/`permissions` claims.
- `setAuthoritiesClaimName(...)` changes the **source claim**, `setAuthorityPrefix(...)` changes the **authority name**, and `setAuthoritiesClaimDelimiter(...)` changes **how string claims are split** in supported versions.
- To use it in a Servlet Resource Server, wire it into **`JwtAuthenticationConverter`**, and wire that converter into the **JWT Resource Server DSL** of the `SecurityFilterChain` actually handling requests.
- To combine multiple sources, use **`DelegatingJwtGrantedAuthoritiesConverter`** if available or write a custom `Converter<Jwt, Collection<GrantedAuthority>>`.
- **Nested claims** require explicit code to read objects/lists; dots in a claim name are not automatically JSONPath.
- `SCOPE_`, `PERMISSION_`, and `ROLE_` are separate naming conventions; `hasAuthority(...)` and `hasRole(...)` must match them precisely.
- The converter **does not replace** signature verification, issuer, audience, expiration, token profile, or record-level access policies.
- When a token is valid yet permissions are mapped incorrectly, the typical symptom is **403**, whereas an invalid JWT at the authentication layer typically yields **401**.

Well-designed authority mapping helps the Resource Server understand the permissions granted by the Authorization Server, while **never expanding** access scope on its own. A sustainable approach is to define the claim schema between issuer and API, map intentionally, check the necessary permissions at endpoints, and continue enforcing authorization on each business resource.
