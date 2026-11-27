# hasAuthority, hasRole, and the ROLE_ Prefix

In **Spring Security OAuth 2.0/OIDC Resource Server**, after a Bearer access token is verified, Spring Security creates an **Authentication** containing a collection of **GrantedAuthority** objects. The **hasAuthority(...)** and **hasRole(...)** methods use that collection to decide whether a request may enter an endpoint or method.

These two checks are easily confused because both deal with permissions yet follow different conventions:

- **hasAuthority("SCOPE_orders.read")**: requires the exact authority **SCOPE_orders.read**.
- **hasAuthority("ROLE_ADMIN")**: requires the exact authority **ROLE_ADMIN**.
- **hasRole("ADMIN")**: by default, requires the authority **ROLE_ADMIN**, because Spring Security applies the **ROLE_** prefix to roles.
- **hasRole("ROLE_ADMIN")**: should not be used in the HTTP request authorization DSL; some APIs throw an error because the argument already carries the prefix.

In a JWT Resource Server, the OAuth2 scope **orders.read** is typically mapped to **SCOPE_orders.read**, **not** **ROLE_orders.read**. Similarly, if a JWT carries a **roles** claim containing **ADMIN**, Spring Security **does not automatically convert that claim into ROLE_ADMIN** without an appropriate converter.

This lesson explains what an authority is, how scopes differ from roles, how to write rules, how to configure converters, per-tenant permissions, and common 403 errors.

## 1. Authentication, GrantedAuthority, scope, and role

### 1.1. Where does Authentication come from?

In an OAuth2 JWT Resource Server, the typical flow is:

~~~mermaid
flowchart LR
    A[Authorization: Bearer JWT] --> B[BearerTokenAuthenticationFilter]
    B --> C[JwtAuthenticationProvider]
    C --> D[JwtDecoder verifies token]
    D -->|Invalid| E[401 Unauthorized]
    D -->|Valid| F[JwtAuthenticationConverter]
    F --> G[JwtAuthenticationToken with GrantedAuthority]
    G --> H[hasAuthority / hasRole]
    H -->|Insufficient permission| I[403 Forbidden]
    H -->|Sufficient permission| J[Controller / Service]
~~~

Key roles:

- **JwtDecoder** verifies the JWT signature with trusted keys, issuer, expiration, and configured validators, which must include checking the API's audience.
- **JwtAuthenticationConverter** converts an accepted token into an Authentication and authorities.
- **Authentication** represents the authenticated principal. In a JWT Resource Server, the common implementation is **JwtAuthenticationToken**.
- **GrantedAuthority** represents a permission that Spring Security can match against rules.
- **hasAuthority/hasRole** only check authorities on Authentication; they do not verify the JWT signature themselves.

A valid token containing:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "exp": 1893456000
}
~~~

can create an Authentication with:

~~~text
principal: Jwt(...)
name: user-123
authorities:
  - SCOPE_orders.read
  - SCOPE_orders.write
~~~

**Important:** claims should only become authorities **after the token has passed issuer verification and validators**. If code parses JSON from an unverified Bearer token on its own and builds an Authentication, hasRole/hasAuthority rules can be fooled.

### 1.2. GrantedAuthority is the unit of permission matching

Spring Security provides the **GrantedAuthority** interface and the common implementation **SimpleGrantedAuthority**:

~~~java
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

GrantedAuthority readOrders =
    new SimpleGrantedAuthority("SCOPE_orders.read");

GrantedAuthority admin =
    new SimpleGrantedAuthority("ROLE_ADMIN");

GrantedAuthority approve =
    new SimpleGrantedAuthority("PERM_orders.approve");
~~~

By themselves, those three strings have no cryptographic properties or automatic privileges. They have meaning because **the application's authorization code chooses to check them**.

Spring Security supports prefix conventions to reduce confusion:

| Authority | Meaning by convention |
|---|---|
| **SCOPE_orders.read** | Token has OAuth2 scope **orders.read** |
| **SCOPE_orders.write** | Token has OAuth2 scope **orders.write** |
| **ROLE_ADMIN** | Principal holds the **ADMIN** role under the application model |
| **ROLE_SUPPORT** | Principal holds the **SUPPORT** role |
| **PERM_orders.approve** | A fine-grained permission designed by the application |
| **ADMIN** | An authority literally named **ADMIN**, not implicitly equivalent to ROLE_ADMIN |

Not every application uses all of these prefixes. **ROLE_** and **SCOPE_** are common Spring Security conventions; **PERM_** is just an example of a custom naming convention.

### 1.3. How do roles and OAuth2 scopes differ?

A **scope** in OAuth2 is the access range granted to an access token, such as **orders.read**, **orders.write**, or **reports.export**. It is tied to authorization granted to a specific token, client, and resource.

A **role** is typically a permission group for a principal within an application or organization, such as **ADMIN**, **AUDITOR**, or **SUPPORT**. Roles may be issued by the Authorization Server in a JWT or computed by the application from a database/internal rules, but they must come from a trusted identity and permission source.

For example, the same principal might hold the ADMIN role while the access token only has the **orders.read** scope. You must not conclude that the token implicitly has **orders.write** or data-export permission if API policy requires the corresponding scope.

Similarly, a token with **openid**, **profile**, or **email** scopes does not automatically acquire business permissions just because Spring Security produces **SCOPE_openid**, **SCOPE_profile**, and **SCOPE_email** authorities.

## 2. hasAuthority performs exact string matching

The **hasAuthority** method requires Authentication to contain an authority with the exact specified name.

For example:

~~~java
.requestMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

For the rule to pass, the GrantedAuthority collection must contain **SCOPE_orders.read**.

If Authentication only has:

~~~text
ROLE_ADMIN
SCOPE_email
~~~

then **hasAuthority("SCOPE_orders.read")** fails. Spring Security does not treat **ROLE_ADMIN** or **SCOPE_email** as equivalent to **SCOPE_orders.read**.

Other examples:

~~~java
.hasAuthority("ROLE_ADMIN")
.hasAuthority("PERM_orders.approve")
.hasAuthority("SCOPE_reports.export")
~~~

All three match the respective authority string without adding or stripping prefixes. **hasAuthority("ADMIN")** is different from **hasAuthority("ROLE_ADMIN")**.

### 2.1. Exact matching prevents unintended privilege grants

When using explicit authorities, policies are easy to read:

~~~text
Access token scope:       orders.read
Spring GrantedAuthority:  SCOPE_orders.read
Endpoint rule:            hasAuthority("SCOPE_orders.read")
~~~

Conversely, if the rule uses the name **ROLE_orders.read** while the converter produces **SCOPE_orders.read**, the request is typically rejected with 403.

Although exact matching is the main principle, a system may still configure a custom authorization manager or role hierarchy; in that case, you must understand how the rules and custom policies operate rather than relying solely on the method name.

## 3. hasRole and the ROLE_ prefix

In Spring Security, **a role is typically represented as a GrantedAuthority prefixed with ROLE_**.

With the default prefix:

~~~java
.requestMatchers("/api/admin/**")
    .hasRole("ADMIN")
~~~

is equivalent in required authority to:

~~~java
.requestMatchers("/api/admin/**")
    .hasAuthority("ROLE_ADMIN")
~~~

If Authentication contains **ROLE_ADMIN**, the rule can pass. If it only contains **ADMIN** or **SCOPE_ADMIN**, the default rule fails.

### 3.1. Do not apply the ROLE_ prefix twice

Do not write:

~~~java
// Do not use this style for default hasRole in the HTTP DSL:
.requestMatchers("/api/admin/**")
    .hasRole("ROLE_ADMIN")
~~~

Request authorization APIs such as **AuthorityAuthorizationManager.hasRole** expect the argument to be a role name without **ROLE_**; some implementations throw **IllegalArgumentException** when the argument already has the prefix.

Two clear choices:

~~~java
// To express a role by convention:
.hasRole("ADMIN")

// To express the exact GrantedAuthority name:
.hasAuthority("ROLE_ADMIN")
~~~

In **@PreAuthorize** for method security, the standard style is also **hasRole('ADMIN')** rather than embedding the prefix.

### 3.2. hasRole does not inspect a roles claim in the JWT

Suppose a JWT is validly signed by the issuer:

~~~json
{
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "roles": ["ADMIN"]
}
~~~

If the application only uses the default scope converter, Authentication may only contain:

~~~text
SCOPE_orders.read
~~~

Result:

- **hasAuthority("SCOPE_orders.read")**: passes.
- **hasRole("ADMIN")**: fails.
- **hasAuthority("ROLE_ADMIN")**: fails.

Spring Security does not treat a JSON field named **roles** as a mandatory OAuth2/OIDC rule; seeing ADMIN in a claim does not automatically create ROLE_ADMIN. To use roles, the Resource Server must **map the claim to GrantedAuthority** according to a trusted contract.

## 4. Comparison table: hasAuthority vs. hasRole

| Rule | Required GrantedAuthority under default config | Use case |
|---|---|---|
| **hasAuthority("SCOPE_orders.read")** | **SCOPE_orders.read** | Protect an endpoint using an OAuth2 scope |
| **hasAuthority("SCOPE_reports.export")** | **SCOPE_reports.export** | Only tokens granted the export scope may call it |
| **hasAuthority("ROLE_ADMIN")** | **ROLE_ADMIN** | Explicitly check a role authority |
| **hasRole("ADMIN")** | **ROLE_ADMIN** | Check a role by convention |
| **hasRole("SUPPORT")** | **ROLE_SUPPORT** | Check the support role |
| **hasAuthority("ADMIN")** | **ADMIN** | Only when the application creates a literal ADMIN authority |
| **hasRole("orders.read")** | **ROLE_orders.read** | Usually a bug if trying to check scope orders.read |

Given these verified Authentications:

| Authentication | Authorities |
|---|---|
| **A** | SCOPE_orders.read |
| **B** | ROLE_ADMIN |
| **C** | SCOPE_orders.read, ROLE_ADMIN |
| **D** | ADMIN |
| **E** | SCOPE_openid, SCOPE_profile, SCOPE_email |

We get the result matrix:

| Rule | A | B | C | D | E |
|---|:---:|:---:|:---:|:---:|:---:|
| **hasAuthority("SCOPE_orders.read")** | ✓ | ✗ | ✓ | ✗ | ✗ |
| **hasRole("ADMIN")** | ✗ | ✓ | ✓ | ✗ | ✗ |
| **hasAuthority("ROLE_ADMIN")** | ✗ | ✓ | ✓ | ✗ | ✗ |
| **hasAuthority("ADMIN")** | ✗ | ✗ | ✗ | ✓ | ✗ |
| **hasAuthority("SCOPE_email")** | ✗ | ✗ | ✗ | ✗ | ✓ |

This matrix only describes **how authorities are matched**. Whether an authority is present must be grounded in a verified token; passing a rule does not prove business logic should grant access. For example, **SCOPE_email** is not permission to export customer data.

## 5. How are scopes from a JWT mapped to SCOPE_*?

**JwtGrantedAuthoritiesConverter** is the Spring Security class commonly used to turn JWT scopes into authorities. By default, it recognizes common scope claim names such as **scope** or **scp**.

Example 1 — space-separated string scope:

~~~json
{
  "scope": "orders.read orders.write"
}
~~~

Example 2 — array scp:

~~~json
{
  "scp": ["orders.read", "orders.write"]
}
~~~

With the appropriate default configuration, the corresponding scopes are mapped to:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Key points:

- **SCOPE_** is the converter's default prefix for scopes.
- The **scope/scp** claim is read per the converter's claim-selection logic; if a token contains both, do not assume the framework automatically merges all values without configuration.
- The default converter **does not** scan the entire JWT to guess roles, permissions, or tenant rights.
- **SCOPE_orders.read** can be checked with **hasAuthority("SCOPE_orders.read")**.
- Do not use **hasRole("orders.read")** to check an OAuth scope because it checks permissions in the **ROLE_** group.

### 5.1. OIDC scopes do not automatically become business permissions

A token may contain:

~~~json
{
  "scope": "openid profile email"
}
~~~

Spring Security may produce:

~~~text
SCOPE_openid
SCOPE_profile
SCOPE_email
~~~

These scopes relate to OpenID Connect and identity data. Never infer that **SCOPE_email** equals permission to view all customers' email addresses, or that **SCOPE_profile** equals permission to edit other users' profiles.

OAuth scopes and business logic must have a clear contract between the Authorization Server and Resource Server. If the Orders API needs read permission for orders, define a dedicated scope/permission such as **orders.read** instead of reusing identity scopes.

### 5.2. What if the claim has a different name?

Suppose the Authorization Server sends:

~~~json
{
  "permissions": ["orders.read", "orders.approve"]
}
~~~

This is **not** a default scope claim name. The application can configure the converter:

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

JwtGrantedAuthoritiesConverter permissionsConverter =
    new JwtGrantedAuthoritiesConverter();

permissionsConverter.setAuthoritiesClaimName("permissions");
permissionsConverter.setAuthorityPrefix("PERM_");
~~~

When the converter processes the matching claim, the authorities become:

~~~text
PERM_orders.read
PERM_orders.approve
~~~

Then use:

~~~java
.hasAuthority("PERM_orders.approve")
~~~

Switching the converter to the **permissions** claim may cause the default **scope** mapping not to be retained. If you need both scopes and permissions simultaneously, you must **combine converters** or intentionally add authorities from multiple sources.

## 6. Configuring SecurityFilterChain for Orders API

Suppose the policy is:

| Endpoint | Condition |
|---|---|
| **GET /api/public/** | Public |
| **GET /api/orders/** | OAuth2 scope orders.read |
| **POST /api/orders/** | OAuth2 scope orders.write |
| **PUT /api/orders/** | OAuth2 scope orders.write |
| **/api/admin/** | Application role ADMIN |
| Remaining endpoints | At least authenticated; real apps need explicit policies |

**Spring Security Servlet** configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(HttpMethod.PUT, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers("/api/admin/**")
                    .hasRole("ADMIN")
                .anyRequest()
                    .authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Points to note:

1. **JwtDecoder** must verify signature, issuer, audience, expiration, and the appropriate token profile before rules evaluate authorities.
2. Matchers are ordered; place specific rules before broad ones and review all endpoints/HTTP methods.
3. **anyRequest().authenticated()** only requires authentication, with no specific scope requirement; for sensitive APIs, build a tight enough policy so no endpoint is left exposed.
4. The **ADMIN** role only takes effect if a converter or permission mechanism creates **ROLE_ADMIN**.
5. Checking endpoints by scope/role is only **coarse-grained authorization**; record/tenant permissions must be enforced in the service or domain layer.

### 6.1. Valid JWT token yet the rule still returns 403

Suppose a valid token has:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "roles": ["ADMIN"],
  "exp": 1893456000
}
~~~

If the decoder and default converter only produce **SCOPE_orders.read**, a request to **/api/admin/reports** lacks **ROLE_ADMIN**, so **hasRole("ADMIN")** rejects it, typically returning **403 Forbidden**.

This is not necessarily a JWT signature error. Check **Authentication.authorities** (logging only necessary metadata and never raw tokens) and claim mapping. Never fix the error by removing JWT validation or changing the endpoint to **permitAll()**.

## 7. Intentionally mapping a roles claim to ROLE_*

If a trusted Authorization Server emits a **roles** claim and the API is contracted to use it as a role source, configure **JwtAuthenticationConverter**.

Example token:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "aud": ["orders-api"],
  "sub": "user-123",
  "scope": "orders.read reports.read",
  "roles": ["ADMIN", "SUPPORT"]
}
~~~

Target authorities:

~~~text
SCOPE_orders.read
SCOPE_reports.read
ROLE_ADMIN
ROLE_SUPPORT
~~~

### 7.1. Converter that preserves scopes and adds roles

~~~java
import java.util.Collection;
import java.util.LinkedHashSet;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Configuration
public class JwtAuthoritiesConfiguration {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopeConverter =
            new JwtGrantedAuthoritiesConverter();

        Converter<Jwt, Collection<GrantedAuthority>> combined = jwt -> {
            Collection<GrantedAuthority> authorities =
                new LinkedHashSet<>();

            Collection<GrantedAuthority> scopes =
                scopeConverter.convert(jwt);
            if (scopes != null) {
                authorities.addAll(scopes);
            }

            Object rawRoles = jwt.getClaim("roles");
            if (rawRoles instanceof Collection<?> roles) {
                for (Object value : roles) {
                    if (value instanceof String role
                            && role.matches("[A-Z][A-Z0-9_]*")) {
                        authorities.add(
                            new SimpleGrantedAuthority("ROLE_" + role)
                        );
                    }
                }
            }

            return authorities;
        };

        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(combined);
        return converter;
    }
}
~~~

Explanation:

- Default **JwtGrantedAuthoritiesConverter** handles scope/scp into **SCOPE_***.
- **rawRoles** is read from the **roles** claim, assuming the issuer is trusted by the API and the token passed **JwtDecoder**.
- **LinkedHashSet** prevents duplicate authorities when combining multiple sources.
- Role strings are format-checked before creating **ROLE_***. This is only a basic check; production should also enforce a **role allowlist** and appropriate tenant/resource rules.
- If the token has no roles, scope mapping still works.
- If roles is not an array of strings, the example grants no roles from malformed data.

**Crucially:** the converter is not where issuer trust is established. It only processes a **Jwt already verified by the decoder** in the standard authentication flow. Never invoke the converter directly on a Jwt built from client-supplied JSON and treat it as logged in.

### 7.2. Avoiding double ROLE_ prefixes

The converter above expects:

~~~json
{
  "roles": ["ADMIN", "SUPPORT"]
}
~~~

and produces:

~~~text
ROLE_ADMIN
ROLE_SUPPORT
~~~

If the issuer sends:

~~~json
{
  "roles": ["ROLE_ADMIN"]
}
~~~

and the converter prepends **ROLE_**, it can produce **ROLE_ROLE_ADMIN**. That is not the authority **hasRole("ADMIN")** expects.

The application should standardize on one contract:

- The claim holds the role name **ADMIN** and the application adds the prefix; or
- The claim holds the literal authority **ROLE_ADMIN**, and the application checks/normalizes without doubling.

Never mix both formats without validation/normalization rules and tests.

### 7.3. Wiring the converter into the Resource Server

In `SecurityFilterChain`:

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
            .anyRequest()
                .authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt
                .jwtAuthenticationConverter(jwtAuthenticationConverter)
            )
        );

    return http.build();
}
~~~

This snippet is an illustrative bean method using the same imports for **HttpSecurity**, **SecurityFilterChain**, **HttpMethod**, and **@Bean** as the previous example.

After the decoder accepts the JWT, Spring Security invokes the converter; only then can **hasRole("ADMIN")** pass if Authentication carries **ROLE_ADMIN**.

### 7.4. Roles may live in nested claims

Some identity providers represent roles in nested structures:

~~~json
{
  "realm_access": {
    "roles": ["ADMIN"]
  },
  "resource_access": {
    "orders-api": {
      "roles": ["ORDER_APPROVER"]
    }
  }
}
~~~

These fields are an example of a provider-specific role model, **not a mandatory OAuth2/OIDC role format**. The Resource Server must know precisely:

- Is the role realm-wide, app-wide, or scoped to a single resource?
- Which audience/client is the role intended for?
- Is the role tenant-scoped?
- Which issuer is authorized to grant that type of role?
- Should ROLE_ mapping be used system-wide, or is a fine-grained permission like PERM_orders.approve needed?

Never map every role from every client into a system-wide role simply because the claim is named **roles**.

## 8. @PreAuthorize and method security

Beyond HTTP authorization, Spring Security provides **method security** with the **@PreAuthorize** annotation.

Enable method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

An illustrative service:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderDetails readOrder(long orderId) {
        // Domain policy must still check tenant and ownership.
        throw new UnsupportedOperationException("Implement in application");
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void runAdminOperation() {
        // Requires ROLE_ADMIN by default.
    }

    @PreAuthorize("hasAuthority('ROLE_SUPPORT')")
    public void runSupportOperation() {
        // Checks exact ROLE_SUPPORT.
    }
}
~~~

**OrderDetails** is a hypothetical business type to illustrate the annotation. Methods must be implemented in the real application.

From the example:

- **hasAuthority('SCOPE_orders.read')** checks the exact authority.
- **hasRole('ADMIN')** uses the role prefix and checks **ROLE_ADMIN**.
- **hasAuthority('ROLE_SUPPORT')** checks the exact name **ROLE_SUPPORT**.

### 8.1. Combining scope with record-level policy

Example when a request must have a scope and may only read orders of the right tenant:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.read') " +
    "and @orderPolicy.canRead(authentication, #orderId)"
)
public OrderDetails readOrder(long orderId) {
    return orderService.load(orderId);
}
~~~

Here **orderPolicy** is a custom application bean that checks tenant, ownership relations, state, and real data conditions. The expression assumes the **orderId** parameter is accessible by name to Spring Security via appropriate compiler/parameter-metadata configuration.

Even if a principal has **ROLE_ADMIN**, the privilege may only be valid within one tenant. **hasRole('ADMIN')** does not automatically check whether the resource belongs to the permitted tenant scope.

### 8.2. @PreAuthorize also requires a trusted Authentication

Method security uses the Authentication in SecurityContext. It **does not verify the JWT signature itself** and does not fetch the issuer's JWKS.

If a custom filter builds an Authentication from unverified roles and stores it in SecurityContext, **hasRole('ADMIN')** can be bypassed. The proper design remains:

~~~text
JwtDecoder verifies access token
 -> JwtAuthenticationConverter builds GrantedAuthority
 -> SecurityContext holds Authentication
 -> @PreAuthorize matches permissions
 -> domain policy verifies resource
~~~

In applications using Spring proxy-based method security, also understand the limitations of self-invocation within the same instance and the possibility of annotations being bypassed when calls skip the proxy. Design and test real method authorization accordingly.

## 9. hasAnyAuthority, hasAnyRole, and combined expressions

When an endpoint permits any of several permissions, you can use:

~~~java
.hasAnyAuthority("SCOPE_reports.read", "PERM_reports.read")
~~~

or:

~~~java
.hasAnyRole("ADMIN", "AUDITOR")
~~~

By default, **hasAnyRole("ADMIN", "AUDITOR")** checks **ROLE_ADMIN** or **ROLE_AUDITOR**.

In method security:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_reports.export') or hasRole('ADMIN')"
)
public byte[] exportReport() {
    return new byte[0];
}
~~~

The **or** expression lets either condition pass. However, this **should only be used when business policy allows the ADMIN role to substitute for the export scope**. In a Resource Server, there are operations where the access token still strictly requires a specific scope even if the principal holds an admin role; do not expand token privileges beyond the grant contract without reason.

If **both** scope and role are required:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.approve') and hasRole('MANAGER')"
)
public void approveOrder(long orderId) {
    // Also check tenant/ownership and order state.
}
~~~

Using **and** or **or** must come from authorization requirements, not convenience for making 403s go away.

## 10. ROLE_ can be customized, but should not be changed arbitrarily

Across many Spring Security components, the default role prefix is **ROLE_**. Extension points such as **GrantedAuthorityDefaults** exist to customize the default role prefix in supported contexts.

However, be cautious:

- Do not assume changing the prefix affects every request authorization API, method security, custom expression, or integration uniformly across all Spring Security versions.
- Some request authorization factory methods like **hasRole** have fixed prefix rules per their own implementation.
- Changing the prefix can cause existing rules, annotations, and test helpers to behave differently.
- If the goal is to check a specific custom authority exactly, **hasAuthority("...")** is clearer.

For a JWT Resource Server, an easy-to-follow design is to keep:

~~~text
SCOPE_  -> OAuth2 scopes
ROLE_   -> application roles
PERM_   -> fine-grained permissions defined by application convention
~~~

and configure converters/authorization rules consistently. Only change the prefix when there is a clear architectural requirement tested against the exact Spring Security version in use.

### 10.1. Does ROLE_ADMIN automatically include every scope?

No.

If Authentication has:

~~~text
ROLE_ADMIN
~~~

then:

- **hasRole("ADMIN")**: passes.
- **hasAuthority("ROLE_ADMIN")**: passes.
- **hasAuthority("SCOPE_orders.read")**: does not pass automatically.

If the application wants the ADMIN role to be permitted to perform specific functions, build an explicit policy or role hierarchy. Automatically assuming ADMIN has every OAuth scope can violate access token constraints and the principle of least privilege.

## 11. Common pitfalls when combining roles and scopes

### 11.1. Using hasRole to check a scope

The JWT is mapped to **SCOPE_orders.read**, but the rule:

~~~java
.hasRole("orders.read")
~~~

checks **ROLE_orders.read**, so it typically returns 403. For OAuth scopes:

~~~java
.hasAuthority("SCOPE_orders.read")
~~~

### 11.2. Using hasAuthority("ADMIN") when ROLE_ADMIN is present

Authentication contains **ROLE_ADMIN**, but the rule requires **ADMIN**. The two strings do not match. Fix it to **hasRole("ADMIN")** or **hasAuthority("ROLE_ADMIN")** if the policy actually checks the ADMIN role.

### 11.3. Token has roles but the converter only reads scopes

A JWT claim **roles: ["ADMIN"]** does not automatically turn into **ROLE_ADMIN**. You need an explicit converter or another trusted authority source used by the application.

### 11.4. Converter produces ROLE_ROLE_ADMIN

The claim already contains **ROLE_ADMIN**, yet the converter prepends **ROLE_**. Standardize the role name format and normalization.

### 11.5. Custom converter drops SCOPE_*

If you replace the default converter with one that only reads roles, conventionally mapped scopes may disappear. Use a composite converter when both scopes and roles are needed.

### 11.6. Role issued for tenant A accesses tenant B

A token carrying **ROLE_ADMIN** for one tenant may be mistaken for a system-wide admin. Constrain tenant/resource in the domain policy; a single authority string does not always describe the full scope.

### 11.7. OIDC scopes used as data permissions

Having **SCOPE_email** or **SCOPE_profile** does not grant permission to export data or edit another user's profile. Define separate scopes/permissions for business operations.

### 11.8. Rule placed after a broad matcher

In the `authorizeHttpRequests` DSL, request matcher order matters. If a broad matcher appears before a specific protection rule, requests may not receive the intended policy. Place specific rules first and check all HTTP methods.

### 11.9. Checking roles while skipping JWT source verification

If a custom authentication flow reads JWT JSON directly, an attacker can write roles ADMIN and pass hasRole. **JwtDecoder** must verify the token before mapping.

### 11.10. Confusing 401 and 403

- **401** usually relates to a missing or invalid Bearer token: signature, issuer, audience, expiration.
- **403** usually means the token was authenticated, but lacks the authority or was blocked by domain authorization.
- Some applications return **404** to hide resources the caller has no access to.

Never resolve 403 by removing verification or changing sensitive endpoints to permitAll.

## 12. Testing rules purposefully

### 12.1. MockMvc with simulated JWT Authentication

Spring Security Test provides the **jwt() request post-processor** to simulate Authentication for a Servlet request.

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

// Inside a test class configured with MockMvc and appropriate controller/fixture.
@Test
void adminCanAccessRoleEndpoint() throws Exception {
    mockMvc.perform(get("/api/admin/reports")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("ROLE_ADMIN")
            )))
        .andExpect(status().isOk());
}

@Test
void oauthScopeOnlyDoesNotGrantAdminRole() throws Exception {
    mockMvc.perform(get("/api/admin/reports")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isForbidden());
}
~~~

The assertions above are examples: **200** depends on the application's controller and fixture; a real API may return a different success status or resource error after passing authorization.

More importantly: **jwt() in this style of test typically bypasses the real JwtDecoder**. It tests authorization given an Authentication, and does not prove forged JWTs are rejected in production.

### 12.2. @WithMockUser: roles and authorities

~~~java
@WithMockUser(roles = "ADMIN")
~~~

typically creates **ROLE_ADMIN**.

~~~java
@WithMockUser(authorities = "SCOPE_orders.read")
~~~

creates the exact **SCOPE_orders.read**.

This is a tool for testing method/request authorization, not for verifying JWT signature, issuer, or audience.

### 12.3. Testing converter and decoder separately

You should have two layers of tests:

**Converter tests:** Construct a test Jwt with **scope = orders.read** and **roles = ["ADMIN"]**, call the converter, and verify the authorities:

~~~text
SCOPE_orders.read
ROLE_ADMIN
~~~

Also test invalid role formats, duplicated prefixes, and missing scope/roles cases.

**Decoder/integration tests:** Configure a test issuer/JWKS and send tokens signed with a test private key. Tokens with forged signatures, wrong audiences, expired timestamps, or untrusted issuers must be rejected **before the converter creates authorities**.

Mocking principal/authorities alone is not enough to prove that a self-signed JWT with roles ADMIN will be blocked.

### 12.4. Suggested test matrix

| Scenario | Order-read API requiring scope | Admin API requiring role |
|---|---|---|
| No token | 401 | 401 |
| Forged signature token with full scope/role claims | 401 | 401 |
| Verified JWT with only SCOPE_orders.read | Passes scope rule | 403 |
| Verified JWT with only ROLE_ADMIN | Fails scope rule if required | Passes role rule |
| Verified JWT with SCOPE_orders.read and ROLE_ADMIN | Passes scope rule | Passes role rule |
| Validly signed JWT whose aud is not for this API | 401 | 401 |
| JWT with sufficient authorities but wrong tenant | Rejected by domain policy | Depends on tenant policy |

This table illustrates typical responses; exact status codes may depend on exception handling and resource-hiding policies.

## 13. Real-world scenarios to distinguish

### 13.1. Project uses only OAuth2 scopes, no roles

If the API only checks scopes such as **orders.read**, **orders.write**, and **reports.export**, **ROLE_*** may not be needed at all.

For example:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
~~~

This is often the cleanest model for service-to-service APIs, where the access token represents delegated authorization. Do not add a role converter just because Spring Security has a hasRole method.

### 13.2. Project has roles, but not on every endpoint

You can use:

~~~java
.requestMatchers("/api/admin/**")
    .hasRole("ADMIN")
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

Roles and scopes are used side-by-side by purpose. Ensure the JWT role claim is validly issued and endpoints requiring a role do not accidentally skip scope checks if policy requires both.

### 13.3. Order-approval permission should not default to the ADMIN role

Example rule:

~~~text
Action: approve order
Requires:
  - Access token has orders.approve permission
  - Principal is the assigned approver
  - Order is in WAITING_APPROVAL status
  - Tenant matches the granted scope
~~~

You can use **hasAuthority("SCOPE_orders.approve")** or **hasAuthority("PERM_orders.approve")** for the technical permission, then check domain conditions. A generic ADMIN role is not enough to express these conditions.

### 13.4. JWT access token vs. ID Token

An OIDC **ID Token** can also carry user claims, but it is intended for the OIDC client to confirm login. A Resource Server must accept an **access token** with the right audience and token type/profile; never accept an ID Token merely because it contains roles or is signed by the same JWKS.

### 13.5. Opaque tokens also produce authorities

If a Resource Server uses **opaque token introspection**, Authentication can obtain scopes/authorities from a trusted introspection response per the implementation. **hasAuthority** and **hasRole** still check GrantedAuthority, while the token verification source is introspection rather than JwtDecoder.

## 14. Authority design workflow for a Resource Server

A practical sequence:

1. **Define trust:** which issuers may issue JWTs, which audience belongs to the API, and which algorithms and JWKS sources are used for verification.
2. **Identify scopes/roles/permissions:** which permissions belong to the access token, which are application roles, and which belong to a tenant or record.
3. **Standardize claim names:** **scope/scp**, **roles**, **permissions**, or provider-specific structures.
4. **Establish naming conventions:** e.g., **SCOPE_*** for scopes, **ROLE_*** for roles, **PERM_*** for permissions.
5. **Configure converters:** only map claims issued by a trusted issuer; preserve required authorities when combining multiple sources.
6. **Write HTTP/method rules:** use **hasAuthority** for specific strings, **hasRole** for the role convention.
7. **Add domain policy:** tenant, owner, state, assignment, and allowed data.
8. **Test across layers:** decoder, converter, request authorization, and per-resource permissions.
9. **Monitor operations:** log authentication/authorization errors appropriately without logging raw Bearer tokens or sensitive claims.

Example convention:

~~~text
JWT scope          orders.read         -> SCOPE_orders.read
JWT role           ADMIN               -> ROLE_ADMIN
JWT permission     orders.approve      -> PERM_orders.approve

GET /api/orders    hasAuthority("SCOPE_orders.read")
POST /api/approve  hasAuthority("PERM_orders.approve")
GET /api/admin     hasRole("ADMIN")
~~~

A system may choose a different model, but it must remain consistent from issuer to converter to authorization rules.

## 15. Quick Q&A

**Why does hasAuthority("ROLE_ADMIN") work while hasAuthority("ADMIN") does not?**

Because Authentication contains **ROLE_ADMIN**, not **ADMIN**. hasAuthority checks exact strings.

**Is hasRole("ADMIN") the same as hasAuthority("ROLE_ADMIN")?**

With the default role prefix, they check the same **ROLE_ADMIN** authority. They differ in expression: hasRole uses the convention, while hasAuthority specifies the literal authority.

**Should I write hasRole("ROLE_ADMIN")?**

No. In the default request DSL, use **hasRole("ADMIN")**; if you want to state the prefix explicitly, use **hasAuthority("ROLE_ADMIN")**.

**Why does hasRole("orders.read") return 403 when the JWT has scope orders.read?**

Because the JWT scope defaults to **SCOPE_orders.read**, whereas hasRole defaults to looking for **ROLE_orders.read**. Use **hasAuthority("SCOPE_orders.read")**.

**Why does hasRole("ADMIN") still return 403 when the JWT has roles ["ADMIN"]?**

Spring Security does not automatically map arbitrary roles claims into ROLE_ADMIN. You need an appropriate converter and a trusted issuer/claim policy.

**Does having ROLE_ADMIN automatically grant every SCOPE_*?**

No. ROLE_ADMIN and SCOPE_orders.read are differently named authorities unless the application intentionally adds extra authorization logic.

**Does having SCOPE_email allow exporting customer emails?**

No. **email** is an OIDC identity-related scope, not a default business permission to export customer data.

**Can ROLE_ be changed?**

Some Spring Security components support a custom default role prefix, but do not assume every API honors the same configuration. If using a custom prefix, test both HTTP and method security on your exact version. For literal authorities, **hasAuthority** is usually easier to control.

**Should roles be mapped to SCOPE_?**

Only when there is an explicit security contract. In many applications, keeping scopes and roles separate prevents confusing permissions granted to an access token with user roles.

## Conclusion

In Spring Security, **GrantedAuthority** is the data checked by authorization rules. **hasAuthority("X")** matches the exact string **X**, whereas **hasRole("ADMIN")** checks **ROLE_ADMIN** by default. A JWT Resource Server typically maps the OAuth scope **orders.read** to **SCOPE_orders.read**, so the right rule is **hasAuthority("SCOPE_orders.read")**, not **hasRole("orders.read")**.

If an access token carries a **roles** claim, the application must **actively map** trusted role data into **ROLE_*** before hasRole works. Neither hasAuthority nor hasRole **replaces** JWT signature verification, issuer/audience validation, or per-tenant/record permission checks.

The proper processing chain is **verify token → map trusted claims to authorities → check hasAuthority/hasRole → enforce business policy on the resource**.

### References

- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security API — JwtGrantedAuthoritiesConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html)
- [Spring Security API — JwtAuthenticationConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html)
- [Spring Security API — AuthorityAuthorizationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorityAuthorizationManager.html)
- [Spring Security API — GrantedAuthorityDefaults](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/core/GrantedAuthorityDefaults.html)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
