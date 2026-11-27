# Customizing Principals, Authority Converters, and Authorization Behavior During Upgrades

## 1. Why Can Resource Server Upgrades Alter Access Permissions?

When upgrading Spring Security, a Resource Server may still start up and verify JWT signatures while application behavior silently shifts. Controllers might receive a different principal type than before, `Authentication` might have a different name, authority prefixes might change, or authorization rules might no longer match the authorities produced from tokens.

These shifts typically surface at three tightly coupled points:

- **Principal mapping:** determines the identity the application sees through `Authentication`, such as subject, username, or a custom domain principal.
- **Authority conversion:** translates scopes, roles, groups, and custom claims into `GrantedAuthority` instances.
- **Authorization behavior:** uses those authorities in request matchers, method security, role hierarchies, and resource ownership policies.

For instance, the default Resource Server turns scope `orders.read` into authority `SCOPE_orders.read`. If legacy code checks `hasRole("orders.read")`, the request is denied because `hasRole` looks for `ROLE_orders.read`. The token is valid; the break is in the contract between the converter and the authorization rule.

Similarly, if legacy code casts `Authentication.getPrincipal()` to `UserDetails` while the new version produces `JwtAuthenticationToken`, errors may surface only when a controller or service accesses the principal.

During an upgrade, treat principals and authorities as an application contract. That contract covers principal name, principal object type, authority set, prefixes, claim reading, authorization rule ordering, and 401/403 behavior.

### Learning Objectives

After this lesson, you will be able to:

1. Understand principals, `Authentication`, and `GrantedAuthority` in a Resource Server.
2. Understand the default behavior of `JwtAuthenticationConverter` and `JwtGrantedAuthoritiesConverter`.
3. Customize the principal name from the appropriate claim.
4. Combine scopes and roles inside one authority converter.
5. Build a custom domain principal when the application genuinely needs one.
6. Adapt synchronous converters to reactive converters for WebFlux.
7. Distinguish scope authorities from role authorities.
8. Preserve request authorization and method security behavior during upgrades.
9. Test changes with unit tests and `MockMvc`/`WebTestClient`.
10. Plan a rollback-safe migration without inadvertently widening permissions.

---

## 2. Concepts to Align Before Modifying Converters

### 2.1. What Does `Authentication` Contain?

After the Resource Server validates an access token, Spring Security creates an `Authentication` object. For a JWT Resource Server, the common class is `JwtAuthenticationToken`.

An authenticated `Authentication` typically provides:

| Property | Meaning |
|---|---|
| `getPrincipal()` | The object representing the principal |
| `getName()` | The principal identifier string used by Spring Security |
| `getAuthorities()` | `GrantedAuthority` instances eligible for authorization checks |
| `getCredentials()` | Credential information attached to `Authentication` |
| `isAuthenticated()` | Authentication status |

Do not assume `getPrincipal()` and `getName()` return the same data type. With `JwtAuthenticationToken`, the principal is the `Jwt` object; `getName()` is the identifier string selected from the principal claim.

Example:

~~~java
Authentication authentication = ...;

String name = authentication.getName();

Object principal = authentication.getPrincipal();

Collection<? extends GrantedAuthority> authorities =
    authentication.getAuthorities();
~~~

If legacy code uses `getPrincipal()` to obtain a username or casts it to `UserDetails`, verify the contract. For JWT Resource Servers, the common pattern is injecting `Jwt` via `@AuthenticationPrincipal` or reading `Authentication.getName()`.

### 2.2. A Principal Is Not Synonymous with a User Profile

The principal represents identity within the security context. It does not need to carry the entire user profile.

JWT example:

~~~json
{
  "iss": "https://id.example.com/realms/shop",
  "sub": "user-417",
  "preferred_username": "phuong",
  "email": "user@example.test",
  "tenant_id": "tenant-a",
  "scope": "orders.read"
}
~~~

Claims carry different meanings:

- `sub` is usually the stable identifier within an issuer's scope.
- `preferred_username` may change over time.
- `email` may be updated or reassigned to another user.
- `tenant_id` is meaningful only if the Authorization Server issues this claim under a trusted contract.
- `scope` represents permissions granted to the token.

For auditing, ownership, and cache keys, prefer stable identifiers. In multi-issuer systems, `subject` may be unique only per issuer; internal identity keys should factor in both issuer and subject when two namespaces must stay distinct.

### 2.3. `GrantedAuthority` Is a Standardized Permission String

`GrantedAuthority` represents a permission the authorization layer can evaluate:

~~~java
new SimpleGrantedAuthority("SCOPE_orders.read");
new SimpleGrantedAuthority("ROLE_ORDER_ADMIN");
~~~

An authority does not acquire meaning automatically simply because a JWT claim happens to look like a role name. The converter decides which claims are mapped and which prefixes are added.

Standardize on a clear convention:

- Scopes: `SCOPE_orders.read`, `SCOPE_orders.write`.
- Roles: `ROLE_ORDER_READER`, `ROLE_ORDER_ADMIN`.
- Custom permissions: `PERM_orders:approve` if the organization adopts that convention.

Do not mix `ROLE_` and `SCOPE_` for the same category of permission. Consistent conventions make authorization rules readable and testable.

---

## 3. Default Behavior of JWT Converters

### 3.1. `JwtAuthenticationConverter`

In a Servlet Resource Server, `JwtAuthenticationConverter` converts a verified `Jwt` into an `AbstractAuthenticationToken`. By default it produces `JwtAuthenticationToken`.

Two primary aspects are customizable:

- Principal name claim via `setPrincipalClaimName(...)`.
- Authority converter via `setJwtGrantedAuthoritiesConverter(...)`.

Minimal configuration example:

~~~java
JwtAuthenticationConverter converter =
    new JwtAuthenticationConverter();

converter.setPrincipalClaimName("sub");

converter.setJwtGrantedAuthoritiesConverter(
    new JwtGrantedAuthoritiesConverter()
);
~~~

`sub` is the default principal claim in common setups. Changing it to `preferred_username` makes `Authentication.getName()` reflect that claim when present. The object type returned by `getPrincipal()` remains `Jwt`.

### 3.2. `JwtGrantedAuthoritiesConverter`

`JwtGrantedAuthoritiesConverter` is the default authority converter for JWTs. It reads `scope` or `scp` per supported conventions and produces authorities with the default `SCOPE_` prefix.

Example:

~~~json
{
  "sub": "user-417",
  "scope": "orders.read orders.write"
}
~~~

Generated authorities:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Some Authorization Servers use the `scp` claim instead of `scope` or represent scopes as a JSON array. Confirm your system's actual token schema and test the exact data types. Never assume all issuers emit the same claim format.

### 3.3. Prefixes Are Part of the Contract

Suppose the converter produces `SCOPE_orders.read`. The following rules are not equivalent:

~~~java
.hasAuthority("SCOPE_orders.read")
.hasRole("orders.read")
.hasAuthority("ROLE_orders.read")
~~~

`hasAuthority` compares exact authority strings.

`hasRole("ORDER_ADMIN")` is a shorthand role check using the default `ROLE_` prefix, looking for `ROLE_ORDER_ADMIN`. Do not pass the prefix in the argument when the framework prepends it automatically.

Example:

~~~java
.requestMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.read")

.requestMatchers("/api/admin/**")
    .hasRole("ORDER_ADMIN")
~~~

When upgrading, compare the actual produced authority against the string checked by the rule. Do not look only at the raw JWT claim.

### 3.4. Changing the Claim Name Does Not Merge Multiple Claims

`JwtGrantedAuthoritiesConverter` can be configured to read a custom claim:

~~~java
JwtGrantedAuthoritiesConverter converter =
    new JwtGrantedAuthoritiesConverter();

converter.setAuthoritiesClaimName("permissions");
converter.setAuthorityPrefix("PERM_");
~~~

This instructs the converter to read the `permissions` claim and create authorities prefixed with `PERM_`. It does not automatically combine default scopes with roles or permissions.

If both scopes and roles are needed, write a combined converter explicitly. Simply changing `authoritiesClaimName` to `roles` will drop `scope` from `Authentication`.

### 3.5. The Default Converter Does Not Turn Every Claim into Roles

A token containing claims:

~~~json
{
  "roles": ["ORDER_ADMIN"],
  "groups": ["finance"],
  "permissions": ["orders:approve"]
}
~~~

does not automatically turn every value above into a `GrantedAuthority`. The application must define explicit mappings.

Watch out for this when migrating from a system that had a custom converter to default Resource Server configuration. Dropping the custom converter during migration can make authorities vanish even though the token still carries the claims.

---

## 4. Customizing the Principal Name

### 4.1. Choosing the Right Identifier Claim

You can select `preferred_username` as the `Authentication` name:

~~~java
JwtAuthenticationConverter converter =
    new JwtAuthenticationConverter();

converter.setPrincipalClaimName("preferred_username");
~~~

When the token includes `preferred_username`, `authentication.getName()` returns that claim's value. However, usernames can change and can be recycled. For persistent identity, auditing, or ownership, `sub` is usually safer.

A common approach:

- Use `sub` as the stable identifier.
- Use `preferred_username` for display.
- Use `email` for contact purposes when issued and verified per policy.
- Use `tenant_id` as verified context while still checking tenant/resource access per business rules.

### 4.2. Configuring the Principal Claim in a Bean

~~~java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();

    converter.setPrincipalClaimName("sub");

    return converter;
}
~~~

Wire it into the Servlet Resource Server:

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        JwtAuthenticationConverter converter) throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt
                .jwtAuthenticationConverter(converter)
            )
        )
        .build();
}
~~~

The converter runs only after the decoder verifies the access token. Never use a converter as a substitute for signature, issuer, audience, or timestamp validation.

### 4.3. Using the Principal in Controllers

In a JWT Resource Server, you can inject `Jwt`:

~~~java
@RestController
@RequestMapping("/api/profile")
public class ProfileController {

    @GetMapping
    Map<String, String> profile(@AuthenticationPrincipal Jwt jwt) {
        return Map.of(
            "subject", jwt.getSubject(),
            "username", jwt.getClaimAsString("preferred_username")
        );
    }
}
~~~

Or use `Authentication`:

~~~java
@GetMapping("/identity")
String identity(Authentication authentication) {
    return authentication.getName();
}
~~~

The second approach couples less tightly to a specific principal type when the app only needs the identifier string. When detailed claims are needed, inject `Jwt` explicitly so readers see the endpoint depends on JWTs.

### 4.4. Avoid Using Email as the Principal Primary Key Unnecessarily

Email addresses can change, may not be unique across issuers, or may be reassigned after account deletion. Using email as `getName()` can break auditing, caching, and ownership whenever an email changes.

If a display name is needed, read that claim separately. There is no need to swap the primary identity key just to display a friendlier string.

### 4.5. Multiple Issuers and Subject Collisions

Two issuers can both issue `sub=user-417` for two different individuals. If an application federates multiple issuers, using `sub` alone risks collisions.

An internal principal identity can be the pair:

~~~text
issuer = https://login.alpha.example
subject = user-417
~~~

Normalize that pair into an account key per application convention. Avoid naive string concatenation if the delimiter might appear in the data; use a record/value object or unambiguous encoding in the domain layer.

---

## 5. Combining Scopes and Roles in an Authority Converter

### 5.1. Sample Token Contract

Suppose the Authorization Server issues an access token:

~~~json
{
  "iss": "https://id.example.com/realms/shop",
  "sub": "user-417",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "roles": ["ORDER_READER", "ORDER_ADMIN"]
}
~~~

The application wants to produce:

~~~text
SCOPE_orders.read
SCOPE_orders.write
ROLE_ORDER_READER
ROLE_ORDER_ADMIN
~~~

Scopes and roles may arrive in separate claims. The converter must map each according to its convention.

### 5.2. Writing a Combined Converter

~~~java
public final class OrdersAuthoritiesConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    private static final Set<String> ALLOWED_ROLES = Set.of(
        "ORDER_READER",
        "ORDER_ADMIN"
    );

    private final JwtGrantedAuthoritiesConverter scopes =
        new JwtGrantedAuthoritiesConverter();

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        Set<GrantedAuthority> authorities = new LinkedHashSet<>();

        Collection<GrantedAuthority> scopeAuthorities =
            this.scopes.convert(jwt);

        if (scopeAuthorities != null) {
            authorities.addAll(scopeAuthorities);
        }

        Object rawRoles = jwt.getClaims().get("roles");

        if (rawRoles instanceof Collection<?> roles) {
            for (Object rawRole : roles) {
                if (rawRole instanceof String role
                        && ALLOWED_ROLES.contains(role)) {
                    authorities.add(
                        new SimpleGrantedAuthority("ROLE_" + role)
                    );
                }
            }
        }

        return authorities;
    }
}
~~~

This example accepts `roles` only as a JSON array and maps only the two declared roles. If the issuer sends roles as a string or in a different claim, write the parser per the real token contract. Never blindly turn arbitrary strings into roles by prepending `ROLE_`.

Use `LinkedHashSet` to deduplicate authorities and preserve deterministic ordering for logs/tests. Authorities must never be granted from uncontrolled claims.

### 5.3. Attaching the Converter to `JwtAuthenticationConverter`

~~~java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();

    converter.setPrincipalClaimName("sub");
    converter.setJwtGrantedAuthoritiesConverter(
        new OrdersAuthoritiesConverter()
    );

    return converter;
}
~~~

With this converter active, `Authentication` carries both scope authorities and role authorities. Rules can evaluate them independently:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .requestMatchers("/api/admin/**")
        .hasRole("ORDER_ADMIN")
    .anyRequest().denyAll()
)
~~~

Never grant a role just because a scope name resembles a role. Scopes and roles have distinct semantics and are normally governed at different layers.

### 5.4. When Roles Live Inside Nested Claims

Some issuers emit:

~~~json
{
  "realm_access": {
    "roles": ["ORDER_ADMIN"]
  },
  "resource_access": {
    "orders-api": {
      "roles": ["ORDER_READER"]
    }
  }
}
~~~

The converter must read the exact structure and namespace. Never collect roles from every client/resource in the token and grant them to the current API.

For example, roles inside `resource_access.orders-api` are scoped to the Orders API rather than roles belonging to `billing-api`. Constrain mappings to the specific resource identifier.

### 5.5. Controlling Roles Outside the Allowlist

A token signed by a trusted issuer does not imply every string in its `roles` claim should become an application authority. Claims can carry roles from other systems, deprecated roles, or issuer misconfigurations.

A role allowlist helps catch contract drift and prevents unsupported role names from entering the authorization layer. When adding a new role, update the mapping and tests together with the Authorization Server change.

---

## 6. Custom Domain Principals When the Application Needs a Dedicated Type

### 6.1. When to Keep `JwtAuthenticationToken`?

If controllers and services need only:

- `Authentication.getName()`.
- `Jwt` claims.
- `GrantedAuthority`.

then `JwtAuthenticationToken` is usually sufficient. Inject `Jwt` using `@AuthenticationPrincipal`. Creating a custom `Authentication` for every app adds boilerplate and introduces an extra contract to maintain across upgrades.

### 6.2. When Is a Domain Principal Needed?

Some applications have legacy APIs/services coupled to `AccountPrincipal` or `UserDetails`. In such cases, a custom `Authentication` can have `getPrincipal()` return the domain object.

Domain principal example:

~~~java
public record AccountPrincipal(
    String subject,
    String username,
    String tenantId
) {}
~~~

Custom `Authentication` token:

~~~java
public final class AccountPrincipalAuthenticationToken
        extends AbstractAuthenticationToken {

    private final AccountPrincipal principal;
    private Jwt credentials;

    public AccountPrincipalAuthenticationToken(
            AccountPrincipal principal,
            Jwt credentials,
            Collection<? extends GrantedAuthority> authorities) {

        super(authorities);
        this.principal = principal;
        this.credentials = credentials;
        super.setAuthenticated(true);
    }

    @Override
    public Object getPrincipal() {
        return this.principal;
    }

    @Override
    public Object getCredentials() {
        return this.credentials;
    }

    @Override
    public String getName() {
        return this.principal.subject();
    }

    @Override
    public void eraseCredentials() {
        super.eraseCredentials();
        this.credentials = null;
    }
}
~~~

In this example, the JWT is held as credentials so the framework can clear it via `eraseCredentials()`. The domain principal stores only the fields the application needs. Avoid copying raw access tokens or sensitive claims into the principal object.

### 6.3. Converter Producing a Custom `Authentication`

~~~java
public final class AccountJwtAuthenticationConverter
        implements Converter<Jwt, AbstractAuthenticationToken> {

    private final Converter<Jwt, Collection<GrantedAuthority>>
        authoritiesConverter;

    public AccountJwtAuthenticationConverter(
            Converter<Jwt, Collection<GrantedAuthority>>
                authoritiesConverter) {
        this.authoritiesConverter = authoritiesConverter;
    }

    @Override
    public AbstractAuthenticationToken convert(Jwt jwt) {
        String subject = jwt.getSubject();

        if (subject == null || subject.isBlank()) {
            throw new IllegalArgumentException(
                "JWT subject is required"
            );
        }

        String username =
            jwt.getClaimAsString("preferred_username");

        String tenantId =
            jwt.getClaimAsString("tenant_id");

        AccountPrincipal principal = new AccountPrincipal(
            subject,
            username,
            tenantId
        );

        Collection<GrantedAuthority> authorities =
            this.authoritiesConverter.convert(jwt);

        return new AccountPrincipalAuthenticationToken(
            principal,
            jwt,
            authorities == null ? List.of() : authorities
        );
    }
}
~~~

In production systems, required claims should be validated by a validator prior to conversion. The converter should not be the sole place catching invalid issuers, audiences, or claim profiles. Throwing an exception here merely illustrates the contract; replace it with a dedicated validator so errors are categorized accurately.

### 6.4. Consequences for Controllers and Method Security

After switching to a custom `Authentication`, code using:

~~~java
@AuthenticationPrincipal Jwt jwt
~~~

will no longer work because the principal is now `AccountPrincipal`. Controllers must update to the new contract:

~~~java
@GetMapping("/profile")
AccountPrincipal profile(
        @AuthenticationPrincipal AccountPrincipal principal) {
    return principal;
}
~~~

Or continue using `Authentication.getName()` if only the subject is needed.

Never change the principal type silently. Audit every usage of `@AuthenticationPrincipal`, `Authentication.getPrincipal()`, casts to `UserDetails`, audit names, and cache keys before deploying.

---

## 7. Servlet Resource Server Configuration

### 7.1. Configuring the Converter in `SecurityFilterChain`

Complete configuration with scopes and roles:

~~~java
@Configuration
@EnableWebSecurity
public class ApiSecurityConfig {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();

        converter.setPrincipalClaimName("sub");
        converter.setJwtGrantedAuthoritiesConverter(
            new OrdersAuthoritiesConverter()
        );

        return converter;
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            JwtAuthenticationConverter converter)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers("/api/admin/**")
                    .hasRole("ORDER_ADMIN")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt
                    .jwtAuthenticationConverter(converter)
                )
            )
            .build();
    }
}
~~~

Request matcher order matters: specific rules must precede general rules, with `anyRequest()` last. When upgrading, preserve rule ordering and verify matchers still cover the intended paths/context paths.

### 7.2. Lambda DSL and Configuration Upgrades

Modern Spring Security configurations use the lambda DSL:

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/orders/**")
            .hasAuthority("SCOPE_orders.read")
        .anyRequest().authenticated()
    )
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(jwt -> jwt
            .jwtAuthenticationConverter(converter)
        )
    );
~~~

Legacy code may use the chained configurer style:

~~~java
http
    .authorizeRequests()
        .antMatchers("/api/orders/**")
            .hasAuthority("SCOPE_orders.read")
        .and()
    .oauth2ResourceServer()
        .jwt()
            .jwtAuthenticationConverter(converter);
~~~

When migrating to the new API, do not simply rename methods. Confirm matcher semantics, rule order, default behaviors, and that the converter is actually wired into the decoder chain.

---

## 8. WebFlux Resource Server Configuration

### 8.1. Reactive Converters Have a Different Type from Servlet Converters

The Servlet converter contract is:

~~~java
Converter<Jwt, AbstractAuthenticationToken>
~~~

The reactive converter must emit `Authentication` via `Mono`:

~~~java
Converter<Jwt, Mono<AbstractAuthenticationToken>>
~~~

Spring Security provides `ReactiveJwtAuthenticationConverterAdapter` to wrap a synchronous converter:

~~~java
Converter<Jwt, AbstractAuthenticationToken> delegate =
    jwtAuthenticationConverter();

Converter<Jwt, Mono<AbstractAuthenticationToken>> reactiveConverter =
    new ReactiveJwtAuthenticationConverterAdapter(delegate);
~~~

The adapter merely wraps the synchronous result in a `Mono`. It does not turn blocking database or HTTP calls inside the delegate into non-blocking operations.

### 8.2. Configuring the Converter for WebFlux

~~~java
@Bean
Converter<Jwt, Mono<AbstractAuthenticationToken>>
reactiveJwtAuthenticationConverter(
        JwtAuthenticationConverter delegate) {

    return new ReactiveJwtAuthenticationConverterAdapter(delegate);
}

@Bean
SecurityWebFilterChain apiSecurity(
        ServerHttpSecurity http,
        Converter<Jwt, Mono<AbstractAuthenticationToken>> converter) {

    return http
        .authorizeExchange(exchange -> exchange
            .pathMatchers("/api/public/**").permitAll()
            .pathMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .pathMatchers("/api/admin/**")
                .hasRole("ORDER_ADMIN")
            .anyExchange().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt
                .jwtAuthenticationConverter(converter)
            )
        )
        .build();
}
~~~

This is a WebFlux configuration. Do not pass a synchronous `JwtAuthenticationConverter` directly where a reactive converter is expected.

### 8.3. Truly Asynchronous Converters

If you need to look up additional authorities from a reactive service, write a converter returning `Mono` directly:

~~~java
public final class DirectoryJwtAuthenticationConverter
        implements Converter<Jwt, Mono<AbstractAuthenticationToken>> {

    private final RoleDirectory roleDirectory;

    public DirectoryJwtAuthenticationConverter(
            RoleDirectory roleDirectory) {
        this.roleDirectory = roleDirectory;
    }

    @Override
    public Mono<AbstractAuthenticationToken> convert(Jwt jwt) {
        return this.roleDirectory
            .findAuthorities(jwt.getSubject())
            .map(authorities ->
                new JwtAuthenticationToken(jwt, authorities)
            );
    }
}
~~~

Dependency interface:

~~~java
public interface RoleDirectory {
    Mono<Collection<GrantedAuthority>> findAuthorities(String subject);
}
~~~

Never call `block()` inside the converter. If the directory fails, do not issue an `Authentication` with default permissions. Decide explicitly whether an empty result means the user has no authorities or indicates a contract error; typically the service should emit an empty collection rather than `Mono.empty()` when a valid user simply has zero authorities.

### 8.4. `SecurityContext` in WebFlux

Servlet typically relies on `SecurityContextHolder` bound to thread context. WebFlux uses a reactive security context propagated through the Reactor Context.

In reactive code, do not rely on:

~~~java
SecurityContextHolder.getContext()
~~~

to obtain the principal inside callbacks. Use `ReactiveSecurityContextHolder` or obtain `Authentication` from reactive method security/APIs.

Do not convert the pipeline to blocking code expecting `SecurityContextHolder` to behave identically. Migrating a Servlet application to WebFlux is an architectural change, not just swapping converter types.

---

## 9. Opaque Tokens and Principal/Authority Mapping

### 9.1. Opaque Tokens Do Not Use `JwtAuthenticationConverter`

For opaque tokens, the Resource Server introspects the token and receives an `OAuth2AuthenticatedPrincipal`. `JwtAuthenticationConverter` applies only to JWTs.

Spring Security provides `OpaqueTokenIntrospector` on Servlet and `ReactiveOpaqueTokenIntrospector` on WebFlux. To customize the principal or authorities for opaque tokens, customize the introspector or matching converter per your version's API.

### 9.2. Mapping Scopes from Introspection Responses

An introspection response might contain:

~~~json
{
  "active": true,
  "sub": "user-417",
  "scope": "orders.read orders.write"
}
~~~

Resource Server typically maps scopes to authorities prefixed with `SCOPE_`. When customizing the introspector, preserve these semantics or transition to a new convention deliberately.

### 9.3. Wrapping the Introspector to Add Authorities

Conceptual pattern:

~~~java
public final class CustomOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    public CustomOpaqueTokenIntrospector(
            OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
            this.delegate.introspect(token);

        Collection<GrantedAuthority> authorities =
            new LinkedHashSet<>(principal.getAuthorities());

        Object rawRoles = principal.getAttribute("roles");

        if (rawRoles instanceof Collection<?> roles) {
            for (Object rawRole : roles) {
                if (rawRole instanceof String role
                        && Set.of("ORDER_READER", "ORDER_ADMIN")
                            .contains(role)) {
                    authorities.add(
                        new SimpleGrantedAuthority("ROLE_" + role)
                    );
                }
            }
        }

        return new DefaultOAuth2AuthenticatedPrincipal(
            principal.getName(),
            principal.getAttributes(),
            authorities
        );
    }
}
~~~

This illustrates a Servlet introspector. In WebFlux, use `ReactiveOpaqueTokenIntrospector` and return a `Mono` principal. Never run a synchronous implementation on the reactive event loop if it performs blocking I/O.

### 9.4. Keeping Token Format Independent from Authorization Contracts

Whether an API accepts JWTs or opaque tokens, strive to keep one unified authority convention:

~~~text
SCOPE_orders.read
SCOPE_orders.write
ROLE_ORDER_ADMIN
~~~

If the same endpoint accepts both token formats, tests must confirm they yield equivalent authorities under the policy. Otherwise, users could receive different permissions merely because the AS minted tokens in a different format.

---

## 10. Upgrading Authorization Behavior

### 10.1. `hasAuthority` and `hasRole`

Two matchers often confused:

| API | Checks |
|---|---|
| `hasAuthority("SCOPE_orders.read")` | Exact authority `SCOPE_orders.read` |
| `hasRole("ORDER_ADMIN")` | Role authority `ROLE_ORDER_ADMIN` using the default prefix |
| `hasAnyAuthority(...)` | Any of the exact authorities |
| `hasAnyRole(...)` | Any of the roles after applying the prefix |
| `access(...)` | Authorization decision via the supplied expression/manager |

If the old converter emitted `ROLE_ADMIN` while the new converter emits `SCOPE_admin`, existing rules will behave differently.

Never solve this by relaxing the rule to `authenticated()` when the endpoint originally required specific permissions. Fix the converter or the rule per the agreed contract.

### 10.2. Custom Role Prefixes

Spring Security defaults to `ROLE_` for role-based helpers. You can configure `GrantedAuthorityDefaults` if the application requires another prefix:

~~~java
@Bean
GrantedAuthorityDefaults grantedAuthorityDefaults() {
    return new GrantedAuthorityDefaults("APPROLE_");
}
~~~

If you change the prefix, inspect every usage of `hasRole`/`hasAnyRole` and method security. Likewise, the converter must emit authorities matching the new prefix when role helpers are used.

Changing the prefix can revoke permissions broadly. Treat it as a security-impacting behavior migration.

### 10.3. Request Matchers and Rule Ordering

Example:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**")
        .hasRole("ORDER_ADMIN")
    .requestMatchers("/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().denyAll()
)
~~~

Specific rules must precede general rules. When upgrading, check:

- Whether path patterns match as before.
- Whether context path/servlet path changed.
- Whether HTTP methods are properly constrained.
- Which matcher applies first.
- Whether new endpoints accidentally fall into `authenticated()` instead of `denyAll()`.

Never assume old and new matchers share identical semantics simply because the pattern string looks the same. Verify against your stack and version.

### 10.4. Method Security

Modern method security configuration uses `@EnableMethodSecurity`:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Annotations such as `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` can protect service methods. When upgrading from older setups, verify:

- Which annotations are enabled.
- Whether proxies wrap the target beans and methods.
- Whether self-invocation bypasses the proxy.
- Whether expressions use the expected authority prefixes.
- Whether custom `PermissionEvaluator`/`AuthorizationManager` beans remain wired.
- Whether sensitive methods have corresponding allow/deny tests.

In WebFlux, enable reactive method security with `@EnableReactiveMethodSecurity` and keep the security context inside the reactive execution model.

### 10.5. Scopes and Object-Level Authorization

The `orders.read` scope may permit invoking the order-reading operation, but it does not mean the caller may read every order.

An authorization flow may comprise:

1. Request matchers checking scopes.
2. Method security checking roles or business permissions.
3. Services checking tenant membership.
4. Repositories filtering records by owner/tenant.
5. Auditing recording actions against the principal identity.

Never replace object-level authorization with a coarse authority. The converter only derives authorities from the token; services must still enforce permissions on specific resources.

---

## 11. Common Changes When Upgrading Spring Security

### 11.1. Moving from Chained DSL to Lambda DSL

Older code may use `authorizeRequests`/`antMatchers` and chained configurers. Modern code uses `authorizeHttpRequests`/`requestMatchers` and the lambda DSL.

When migrating, preserve each rule's intent:

| Legacy Configuration | Modern Configuration |
|---|---|
| `authorizeRequests()` | `authorizeHttpRequests(...)` |
| `antMatchers(...)` | `requestMatchers(...)` |
| chained `jwtAuthenticationConverter(...)` | `jwt(jwt -> jwt.jwtAuthenticationConverter(...))` |
| `@EnableGlobalMethodSecurity` | `@EnableMethodSecurity` |
| Servlet `SecurityFilterChain` | Still `SecurityFilterChain` |
| Reactive `SecurityWebFilterChain` | Still `SecurityWebFilterChain` |

This is a high-level mapping. Exact APIs and deprecations/removals depend on the Spring Security version. Check the migration guide and Javadoc for your exact major version.

### 11.2. Converter No Longer Wired in the Right Place

A common mistake is creating a custom `JwtAuthenticationConverter` bean without passing it to the Resource Server configurer. A bean existing in the context does not mean the framework wires it in automatically in every setup.

Verify the DSL:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt
        .jwtAuthenticationConverter(jwtAuthenticationConverter)
    )
)
~~~

After upgrading, test the actual `Authentication` produced by HTTP requests. Do not unit-test the bean alone and assume the security chain uses it.

### 11.3. Scope Claims or Role Claims Changing Schema

An Authorization Server might change from:

~~~json
{
  "scope": "orders.read"
}
~~~

to:

~~~json
{
  "scp": ["orders.read"]
}
~~~

Or move roles into a nested claim. The converter must reflect the new token contract. Avoid performing a framework migration and a token schema migration simultaneously without comparative tests, as isolating failures becomes difficult.

### 11.4. Principal Name Changing

If older code used usernames while the new converter uses `sub`, audit records, cache keys, tenant lookups, and service logs may shift identity. Identify every consumer of `Authentication.getName()` before switching claims.

If a change is required, support a transition period via a dedicated field or domain adapter. Never switch identity keys mid-release without evaluating historical data.

### 11.5. Mixing Servlet and WebFlux APIs

Several classes have similar names yet different contracts:

| Servlet | WebFlux |
|---|---|
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `JwtDecoder` | `ReactiveJwtDecoder` |
| `Converter<Jwt, AbstractAuthenticationToken>` | `Converter<Jwt, Mono<AbstractAuthenticationToken>>` |
| `JwtAuthenticationConverter` | `ReactiveJwtAuthenticationConverterAdapter` or custom reactive converter |
| `SecurityContextHolder` | `ReactiveSecurityContextHolder` |
| `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |

Never run blocking converters on the reactive event loop. Never wire reactive converters into Servlet DSL. When migrating stacks, redesign the integration boundary rather than just changing imports.

---

## 12. Testing Converters and Principal Contracts

### 12.1. Creating a `Jwt` Fixture

~~~java
static Jwt testJwt() {
    Instant now = Instant.now();

    return Jwt.withTokenValue("test-token")
        .header("alg", "RS256")
        .issuer("https://id.example.test")
        .subject("user-417")
        .audience(List.of("orders-api"))
        .issuedAt(now.minusSeconds(10))
        .expiresAt(now.plusSeconds(300))
        .claim("preferred_username", "phuong")
        .claim("tenant_id", "tenant-a")
        .claim("scope", "orders.read orders.write")
        .claim("roles", List.of("ORDER_READER", "ORDER_ADMIN"))
        .build();
}
~~~

This fixture is suitable for testing converters. It does not exercise signature validation; decoder tests need compact JWTs signed with test keys.

### 12.2. Testing Principal Name and Authorities

~~~java
@Test
void mapsPrincipalAndAuthorities() {
    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();

    converter.setPrincipalClaimName("preferred_username");
    converter.setJwtGrantedAuthoritiesConverter(
        new OrdersAuthoritiesConverter()
    );

    AbstractAuthenticationToken authentication =
        converter.convert(testJwt());

    assertEquals("phuong", authentication.getName());

    Set<String> authorities = authentication.getAuthorities().stream()
        .map(GrantedAuthority::getAuthority)
        .collect(Collectors.toSet());

    assertTrue(authorities.contains("SCOPE_orders.read"));
    assertTrue(authorities.contains("SCOPE_orders.write"));
    assertTrue(authorities.contains("ROLE_ORDER_READER"));
    assertTrue(authorities.contains("ROLE_ORDER_ADMIN"));
}
~~~

Checking authorities with a `Set` keeps tests order-independent. If ordering matters in your application, assert it explicitly; most authorization checks only require membership.

### 12.3. Testing Roles Outside the Allowlist

~~~java
@Test
void ignoresUnknownRole() {
    Jwt jwt = Jwt.withTokenValue("test-token")
        .header("alg", "RS256")
        .subject("user-417")
        .claim("roles", List.of("ORDER_ADMIN", "SUPERUSER"))
        .build();

    Collection<GrantedAuthority> authorities =
        new OrdersAuthoritiesConverter().convert(jwt);

    Set<String> names = authorities.stream()
        .map(GrantedAuthority::getAuthority)
        .collect(Collectors.toSet());

    assertTrue(names.contains("ROLE_ORDER_ADMIN"));
    assertFalse(names.contains("ROLE_SUPERUSER"));
}
~~~

This test protects the mapping contract when the issuer adds unexpected roles. Depending on policy, you can ignore unknown roles and emit a warning metric, or reject the token if the schema requires strict adherence.

### 12.4. Testing Missing Principal Claims

If the application requires `preferred_username`, test tokens missing that claim. Fallback behavior should be explicit:

- Fall back to `sub`.
- Reject `Authentication` if the required claim is absent.
- Use a custom principal allowing `null` for the display field while keeping `subject`.

Never leave behavior reliant on an implicit fallback without tests.

### 12.5. Testing Custom Principal Types

When using a custom `Authentication`, assert:

~~~java
assertInstanceOf(
    AccountPrincipal.class,
    authentication.getPrincipal()
);

AccountPrincipal principal =
    (AccountPrincipal) authentication.getPrincipal();

assertEquals("user-417", principal.subject());
assertEquals("tenant-a", principal.tenantId());
~~~

Also test `eraseCredentials()` if the custom token retains the JWT in credentials. Never keep access tokens in objects longer-lived than necessary.

---

## 13. Testing Authorization Behavior After Upgrading

### 13.1. Distinguishing 401 and 403

| Scenario | Expected Result |
|---|---|
| Missing token | 401 |
| Invalid signature/issuer/audience | 401 |
| Expired token | 401 |
| Authentication succeeds but missing scope | 403 |
| Has scope but missing admin role | 403 |
| Has scope/role but wrong tenant | 403 or 404 per policy |
| Sufficient permissions and valid resource | 2xx |

If a converter drops authorities, requests usually shift from 2xx to 403. If a decoder is no longer configured properly, tokens may fail with 401. These are two distinct migration bugs and must be tested separately.

### 13.2. `MockMvc` for Servlet Authorization

Spring Security Test supports the JWT request post-processor:

~~~java
mockMvc.perform(get("/api/orders")
        .with(jwt()
            .jwt(jwt -> jwt
                .subject("user-417")
                .claim("scope", "orders.read")
            )
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )
        ))
    .andExpect(status().isOk());
~~~

The `jwt()` helper creates a test `Authentication` to verify authorization rules. It does not invoke the JWT signature decoder. If your goal is testing the converter, invoke the real converter or configure a suitable test; if your goal is signature/issuer/audience validation, send a real signed compact JWT.

### 13.3. `WebTestClient` for WebFlux Authorization

~~~java
webTestClient
    .mutateWith(mockJwt()
        .jwt(jwt -> jwt
            .subject("user-417")
            .claim("scope", "orders.read")
        )
        .authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )
    )
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

Just like `MockMvc`, `mockJwt` helps test route authorization. To verify the real converter, let the Resource Server process a token through the security chain and inspect the produced `Authentication`.

### 13.4. Testing Reactive Converters with `StepVerifier`

When using the adapter:

~~~java
Converter<Jwt, Mono<AbstractAuthenticationToken>> converter =
    new ReactiveJwtAuthenticationConverterAdapter(
        jwtAuthenticationConverter
    );

StepVerifier.create(converter.convert(testJwt()))
    .assertNext(authentication -> {
        assertEquals("user-417", authentication.getName());
        assertTrue(authentication.getAuthorities().stream()
            .anyMatch(authority ->
                authority.getAuthority().equals("SCOPE_orders.read")));
    })
    .verifyComplete();
~~~

For converters performing async role lookups, test success, empty results, timeouts, and upstream failures. Never convert directory errors into an `Authentication` with default permissions.

### 13.5. Migration Contract Tests

Before upgrading, capture the current contract:

~~~text
Principal name:
  user-417

Principal type:
  UserDetails or Jwt

Authorities:
  SCOPE_orders.read
  ROLE_ORDER_ADMIN

GET /api/orders:
  200 when SCOPE_orders.read is present
  403 when scope is missing

POST /api/orders:
  200 when SCOPE_orders.write is present
  403 when only orders.read is present

GET /api/admin:
  200 when ROLE_ORDER_ADMIN is present
  403 when only SCOPE_orders.read is present
~~~

After upgrading, run the same suite against the new configuration. If any difference is intentional, update the contract and migration notes. Otherwise, fix the converter or rule before rolling out.

---

## 14. Safe Upgrade Workflow

### Step 1: Map Principal Consumers

Find every place using:

- `Authentication.getName()`.
- `Authentication.getPrincipal()`.
- `@AuthenticationPrincipal`.
- Casts to `Jwt`, `UserDetails`, or custom principals.
- Principals in auditing, cache keys, tenant lookups, and database ownership.
- `ReactiveSecurityContextHolder` or `SecurityContextHolder`.

Document current types and semantics.

### Step 2: Document the Authority Contract

List source claims and resulting authorities:

| Source Claim | Data Type | Authority |
|---|---|---|
| `scope` | String or list per AS contract | `SCOPE_*` |
| `roles` | JSON array | `ROLE_*` |
| `permissions` | JSON array | `PERM_*` |
| `groups` | issuer-specific | Map only when policy requires |

Specify prefixes, role allowlists, handling of missing claims, and unknown roles.

### Step 3: Preserve Token Validation

Separate converter migration from trust-policy migration whenever possible. Keep issuer, audience, signature algorithm, expiry, and key source validations intact. Never weaken the decoder to make authorization tests pass.

### Step 4: Create an Explicit Converter

Extract principal name and authority mapping into a unit-testable bean. Do not rely on default mappings if your token schema includes custom claims.

### Step 5: Update Authorization DSL

Migrate matchers to the new API version while preserving order and semantics. Check `hasRole`/`hasAuthority`, prefixes, method security, and role hierarchies.

### Step 6: Choose the Right Servlet or WebFlux Adapter

Servlet uses synchronous converters. WebFlux uses reactive converters or an adapter for purely synchronous converters. Never call blocking services inside a reactive converter.

### Step 7: Run Contract and Integration Tests

Verify principal name/type, authority sets, 401/403 responses, request matchers, method security, and object-level authorization.

### Step 8: Roll Out with Observability

Deploy via canary or small instance groups where infrastructure supports it. Monitor 401/403 rates, authority mapping failures, principal type errors, method security denials, and principal cast exceptions.

### Step 9: Contract-Based Rollback

Keep the previous converter and configuration ready to restore. If the token schema also changes, ensure both application versions are compatible during the overlap window or coordinate token issuance accordingly.

---

## 15. Common Upgrade Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Changing the principal claim without finding consumers | Auditing/caching/ownership change identity | Search for every `getName()` call |
| Casting `getPrincipal()` to `UserDetails` | `ClassCastException` | Use `Jwt` or custom `Authentication` explicitly |
| Reading only `roles` and dropping `scope` | APIs lose scope permissions | Combine converters intentionally |
| Using `hasRole` for `SCOPE_` authorities | Requests fail with 403 | Use `hasAuthority` with exact string |
| Using `hasAuthority("ADMIN")` with `ROLE_ADMIN` | Rule fails to match | Use `hasRole` or exact `ROLE_` authority |
| Changing scope prefix | Permissions lost or mis-granted | Test authority contracts |
| Mapping every role string into an authority | Out-of-policy roles leak in | Allowlist roles and namespaces |
| Keeping raw tokens long-term in custom principals | Increases credential exposure risk | Keep minimal data and erase credentials |
| Creating a converter bean without wiring it in DSL | Bean sits unused | Check `SecurityFilterChain` wiring |
| Using a Servlet converter in WebFlux | Wrong generic contract or blocking I/O | Use reactive adapter/converter |
| Using `SecurityContextHolder` in reactive callbacks | Missing context or wrong thread | Use `ReactiveSecurityContextHolder` |
| Dropping method security when changing annotations | Services lose protection layer | Verify `@EnableMethodSecurity` |
| Updating matchers without keeping order | Broad rule shadows narrow rule | Place specific matchers first |
| Using `mockJwt` to test signatures | Tests bypass the decoder | Use signed JWT integration tests |
| Testing only 200 responses | Misses 403/401 paths | Test allow, deny, and error cases |
| Using email as principal key | Identity shifts when email changes | Use stable `subject` |
| Trusting role claims from another issuer schema | Permissions mismatched to resource | Check issuer/resource namespaces |
| Failing open when authority lookup fails | Issues `Authentication` without basis | Propagate error or fail closed per policy |

---

## 16. Self-Check Questions

**Question 1.** Are `JwtAuthenticationToken.getPrincipal()` and `getName()` the same?

**Answer:** No. `getPrincipal()` normally returns the `Jwt` object; `getName()` returns the identifier string selected from the principal claim, defaulting usually to `sub`.

**Question 2.** What is `JwtAuthenticationConverter` used for?

**Answer:** Converting a verified `Jwt` into an `Authentication`, while determining the principal name and authority collection.

**Question 3.** Which claims does `JwtGrantedAuthoritiesConverter` read by default?

**Answer:** It supports Spring Security's `scope`/`scp` conventions and produces authorities with the default `SCOPE_` prefix.

**Question 4.** Why does `hasRole("ORDER_ADMIN")` not match `SCOPE_orders.read`?

**Answer:** `hasRole` uses the default `ROLE_` prefix. Scope authorities use the `SCOPE_` prefix and are a distinct kind of permission.

**Question 5.** Does `setAuthoritiesClaimName("roles")` automatically combine scopes?

**Answer:** No. It configures the single claim that converter reads. To keep both scopes and roles, write a combined converter.

**Question 6.** Does changing the principal claim to `preferred_username` change the type of `getPrincipal()`?

**Answer:** No. `JwtAuthenticationToken` still holds `Jwt` as its principal; the string returned by `getName()` comes from the configured claim.

**Question 7.** When is a custom `Authentication` needed?

**Answer:** When the application genuinely needs `getPrincipal()` to return a dedicated domain principal/`UserDetails`. When only names and claims are needed, `JwtAuthenticationToken` is usually sufficient.

**Question 8.** What does `ReactiveJwtAuthenticationConverterAdapter` do?

**Answer:** It wraps a synchronous converter into one returning `Mono`. It does not turn blocking I/O in the delegate into non-blocking operations.

**Question 9.** Do opaque tokens use `JwtAuthenticationConverter`?

**Answer:** No. Opaque tokens use an introspector to produce `OAuth2AuthenticatedPrincipal`; customize via the introspector or matching converter.

**Question 10.** Why test both 401 and 403?

**Answer:** 401 indicates authentication failure; 403 indicates authentication succeeded without sufficient permissions. Each points to a different part of the migration.

**Question 11.** Does `MockMvc` `jwt()` verify token signatures?

**Answer:** No. It builds a test `Authentication` for authorization checks. Real signed JWTs are needed to test the decoder.

**Question 12.** Should every role inside a JWT be mapped to a `GrantedAuthority`?

**Answer:** Not if the issuer emits multiple namespaces or roles outside this API. Map roles per resource and enforce an explicit allowlist.

**Question 13.** When moving from Servlet to WebFlux, can you rely on `SecurityContextHolder`?

**Answer:** Do not rely on `ThreadLocal` in reactive flows. Use `ReactiveSecurityContextHolder` and propagate context through the Reactor pipeline.

**Question 14.** Why does `requestMatchers` ordering matter?

**Answer:** The authorization DSL applies rules in match order. A broad rule placed first can shadow specific rules behind it.

**Question 15.** Is changing an authority prefix a minor refactor?

**Answer:** No. It can flip authorization outcomes for every request. It requires contract tests, observable rollout, and a rollback plan.

---

## 17. References

- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT authentication, `JwtAuthenticationConverter`, and authority mapping.
- [Spring Security API — JwtAuthenticationConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html): principal claim and authority converter.
- [Spring Security API — JwtGrantedAuthoritiesConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html): scope claim and authority prefix.
- [Spring Security — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): reactive JWT converters and WebFlux Resource Server.
- [Spring Security API — ReactiveJwtAuthenticationConverterAdapter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/ReactiveJwtAuthenticationConverterAdapter.html): adapter for synchronous converters in reactive stacks.
- [Spring Security — Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html): request authorization and `AuthorizationManager`.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity` and method authorization.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): reactive method security and Reactor context.
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): `MockMvc` security test support.
- [Spring Security — WebFlux Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html): `WebTestClient` and reactive security test support.

APIs can vary across major/minor versions. Check the migration guide and Javadoc for the exact version you are upgrading to, especially for DSLs, converter generics, and method security.

---

## 18. Key Takeaways

When upgrading a Spring Security Resource Server, principal mapping, authority conversion, and authorization rules must be treated as a single unified contract.

- **Principal:** the default JWT principal is `Jwt`; `getName()` typically uses `sub`. Changing the claim name does not automatically change the principal type.
- **Authorities:** `JwtGrantedAuthoritiesConverter` defaults to mapping `scope`/`scp` to `SCOPE_*`. Roles require explicit mapping and the `ROLE_` prefix per convention.
- **Custom mapping:** combine scopes and roles explicitly; restrict allowed namespaces/roles; never turn arbitrary claims into permissions.
- **Custom principal:** build a custom domain `Authentication` only when the application genuinely requires a different principal type, while managing credentials and all consumers.
- **Servlet/WebFlux:** Servlet uses synchronous converters; WebFlux needs converters returning `Mono` or `ReactiveJwtAuthenticationConverterAdapter`.
- **Authorization:** verify `hasRole`/`hasAuthority`, matcher order, method security, tenant checks, and object-level permissions.
- **Migration:** preserve token validation, record the old contract, test principal/authorities and 401/403 responses, roll out with observability, and keep a rollback plan ready.

An upgrade is complete when the application builds the right principal, emits the right authorities, and preserves exact authorization decisions for every valid and invalid request.
