# Converting Token Data into Authentication and GrantedAuthority

In a **Spring Security OAuth 2.0 Resource Server** running on **Servlet** (typically combined with Spring MVC), an HTTP request carrying a Bearer access token becomes a request from an **authenticated** user or client only after Spring Security validates the token and constructs a valid `Authentication` object. The permissions that the application uses to decide whether to allow API calls are represented by `GrantedAuthority` objects inside `Authentication`.

The core focus of this lesson is understanding **which layers token data passes through and how it turns into a principal and authorities**, as well as how to customize mapping rules for `scope`, `scp`, or custom permission claims while preserving the boundary between **authentication** and **authorization**.

Examples in this lesson use Java, Spring Boot, and Spring Security's familiar lambda DSL syntax. All issuers, audiences, tokens, and IDs are simulated data; real APIs must use agreed token contracts, trusted issuer lists, and permission policies.

## 1. Four Concepts to Distinguish

| Concept | What does it represent? | Example |
|---|---|---|
| **Bearer access token** | Credential presented by the client to the API over HTTP; untrusted before verification | `Authorization: Bearer eyJ...` or opaque token |
| **Principal** | Subject identified from a valid credential; may be a user or service client | JWT `sub = user-123` |
| **Authentication** | Spring Security object describing principal, credential, authentication status, authorities, and related details | `JwtAuthenticationToken`, `BearerTokenAuthentication` |
| **GrantedAuthority** | A string-based permission placed in `Authentication` for authorization components to inspect | `SCOPE_orders.read`, `ROLE_ADMIN` |

### Authentication vs. Authorization

**Authentication** asks: *Is the token valid and which principal does it represent?* **Authorization** asks: *Is the authenticated principal allowed to perform this specific action on this resource?*

~~~text
HTTP request:
    Authorization: Bearer <access_token>
                |
                v
     Validate access token
       (authentication)
                |
                v
    Authentication object
      - principal
      - authorities
      - authenticated = true
                |
                v
        Evaluate policy
        (authorization)
                |
                v
        Controller/Service
~~~

**`GrantedAuthority` does not prove identity or token signature on its own.** It is permission data derived **after** the source data has been trusted. A `roles` claim read from JSON cannot become a valid permission unless the token has passed all required checks.

## 2. Where Conversion Happens in the Servlet Security Filter Chain

Suppose the client sends:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
~~~

When the application has a `SecurityFilterChain` configured with `oauth2ResourceServer(...)`, the common processing path is:

~~~mermaid
flowchart TD
    A["Servlet HTTP request"] --> B["DelegatingFilterProxy"]
    B --> C["FilterChainProxy → select SecurityFilterChain"]
    C --> D["BearerTokenAuthenticationFilter"]
    D --> E["BearerTokenAuthenticationToken (unauthenticated)"]
    E --> F["AuthenticationManager / ProviderManager"]
    F --> G{"Resource Server mechanism"}
    G -->|"JWT"| H["JwtAuthenticationProvider → JwtDecoder"]
    G -->|"Opaque token"| I["OpaqueTokenAuthenticationProvider → OpaqueTokenIntrospector"]
    H --> J["JwtAuthenticationConverter"]
    I --> K["OAuth2AuthenticatedPrincipal + authorities"]
    J --> L["JwtAuthenticationToken"]
    K --> M["BearerTokenAuthentication"]
    L --> N["SecurityContextHolder"]
    M --> N
    N --> O["AuthorizationFilter / Access Rules"]
    O --> P["DispatcherServlet → Controller"]
~~~

Specific steps:

1. The Servlet container passes the request into Spring Security's filter chain. `FilterChainProxy` selects the appropriate `SecurityFilterChain` by matcher; the Resource Server's authentication filter lives in that chain.
2. `BearerTokenAuthenticationFilter` uses `BearerTokenResolver` to locate the Bearer token, by default primarily from the `Authorization` header. If found, it creates a `BearerTokenAuthenticationToken`.
3. `BearerTokenAuthenticationToken` is an `Authentication` in an **unauthenticated state**; the token string acts as the input credential, with no trusted authorities yet.
4. `AuthenticationManager` routes the input object to a matching provider, such as `JwtAuthenticationProvider` or `OpaqueTokenAuthenticationProvider`.
5. The provider verifies the JWT or introspects the opaque token. Only when the token is valid does it construct an authenticated `Authentication` with principal and authorities.
6. `BearerTokenAuthenticationFilter` places the authentication result into `SecurityContext` via `SecurityContextHolder` and continues the filter chain.
7. The authorization layer applies `authorizeHttpRequests` rules or method security. The request reaches the controller/service only when applicable rules are satisfied.

**Not every request must have an `Authentication`**: public endpoints can be accessed without a Bearer token; many applications also include `AnonymousAuthenticationFilter`, which creates an anonymous authentication for unauthenticated requests. That differs from a successful access token authentication result.

## 3. Relevant Interfaces and Classes

### 3.1. What Is `Authentication`?

`org.springframework.security.core.Authentication` extends `Principal` and defines key methods:

| API | Practical meaning |
|---|---|
| `getPrincipal()` | Identified principal identity/context |
| `getCredentials()` | Credential associated with authentication; must never be logged or returned in API responses |
| `getAuthorities()` | Collection of `GrantedAuthority` instances for authorization |
| `getDetails()` | Request or context details if present; may be `null` |
| `getName()` | Principal name per implementation/claim mapping |
| `isAuthenticated()` | Indicator that the result was accepted by an authentication mechanism |

Do not rely on `isAuthenticated()` alone to bypass API policies. Spring Security builds a trusted authentication object after validation steps, yet **authorization still needs to check authorities and business data**.

At different stages, the `Authentication` interface is backed by different implementations:

~~~text
Before authentication:
    BearerTokenAuthenticationToken
        authenticated = false
        credentials   = raw token

After JWT authentication:
    JwtAuthenticationToken
        principal     = Jwt
        authorities   = from JwtAuthenticationConverter

After opaque authentication:
    BearerTokenAuthentication
        principal     = OAuth2AuthenticatedPrincipal
        authorities   = from OpaqueTokenIntrospector result
~~~

### 3.2. What Is Inside `GrantedAuthority`?

`GrantedAuthority` is a small interface with one main method:

~~~java
public interface GrantedAuthority extends java.io.Serializable {
    String getAuthority();
}
~~~

`SimpleGrantedAuthority` is the most common implementation:

~~~java
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

GrantedAuthority read = new SimpleGrantedAuthority("SCOPE_orders.read");
GrantedAuthority admin = new SimpleGrantedAuthority("ROLE_ADMIN");
~~~

**Permission values are strings.** With `hasAuthority("SCOPE_orders.read")`, Spring Security compares by authority name. If code creates `orders.read` while the rule requires `SCOPE_orders.read`, permissions do not match. If code creates `ROLE_ADMIN` while the rule requires `SCOPE_ADMIN`, they do not match either.

Authorities can come from standard scopes, issuer-provided roles, organizational policies, or protected supplemental logic. Spring Security does not automatically guess that arbitrary custom claims are permissions.

### 3.3. Types of Principals

| Token processed as | Common principal | How to read data |
|---|---|---|
| JWT Resource Server | `Jwt` | `jwt.getSubject()`, `jwt.getClaimAsString("...")` |
| Opaque token with introspection | `OAuth2AuthenticatedPrincipal` | `principal.getName()`, `principal.getAttribute("...")` |
| Custom authentication | Depends on implementation | Per application-designed interface/class |

Do not assume the principal is always `UserDetails` as in username/password login. Bearer token authentication **does not necessarily call `UserDetailsService`** or query a database user table to construct the principal.

## 4. Converting a JWT into `JwtAuthenticationToken`

With signed JWT access tokens and a Resource Server configured with `jwt()`, the key components are:

~~~mermaid
flowchart LR
    A["BearerTokenAuthenticationToken"] --> B["JwtAuthenticationProvider"]
    B --> C["JwtDecoder"]
    C --> D["Valid Jwt"]
    D --> E["JwtAuthenticationConverter"]
    E --> F["JwtGrantedAuthoritiesConverter"]
    F --> G["GrantedAuthority: SCOPE_*"]
    E --> H["JwtAuthenticationToken"]
    G --> H
~~~

### 4.1. Decoder Validates the Token Before the Converter Runs

`JwtDecoder` verifies the signature/algorithm against trusted configuration and runs required validators, such as `exp`, `nbf`, and `iss` when an issuer is configured. APIs typically also need to configure an **audience `aud`** validator when required to ensure the token was issued for the right Resource Server.

Only after decoding and validation succeed does `JwtAuthenticationProvider` pass the `Jwt` object to the converter. If the signature is invalid or the token is expired, the converter **must never be used** to patch claims or add authorities to let the request proceed.

An illustrative JWT payload:

~~~json
{
  "iss": "https://login.example.test/realms/company",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read orders.create",
  "iat": 1924988400,
  "exp": 1924992000
}
~~~

This is only a payload snippet for explaining the data; it is not a signed JWT. The API must never merely Base64URL-decode a payload and trust these claims. Illustrative timestamp values do not imply the token is currently valid at the time of reading.

### 4.2. Default Converter Uses Scopes

`JwtAuthenticationConverter` typically uses `JwtGrantedAuthoritiesConverter` to convert `scope` or `scp` claims into authorities. The `scope` claim is commonly a **space-delimited string**; `scp` may also be an **array of scope names** depending on the Authorization Server and token profile.

Example:

~~~json
{
  "sub": "user-123",
  "scope": "orders.read orders.create profile"
}
~~~

Converts to:

~~~text
Validated Jwt token
    |
    v
JwtGrantedAuthoritiesConverter
    |
    +--> SCOPE_orders.read
    +--> SCOPE_orders.create
    +--> SCOPE_profile
    |
    v
JwtAuthenticationConverter
    |
    v
JwtAuthenticationToken
  - name          = user-123 (default from sub)
  - principal     = validated Jwt object
  - authorities   = the GrantedAuthorities above
  - authenticated = true
~~~

With an array claim:

~~~json
{
  "sub": "user-123",
  "scp": ["orders.read", "orders.create"]
}
~~~

Default result is similar: `SCOPE_orders.read` and `SCOPE_orders.create`.

If no valid `scope`/`scp` claim is present, default scope-derived authorities can be empty. **Do not assign broader default permissions** to compensate for missing claims; the API must handle this per policy.

### 4.3. Example Reading `Authentication` in Java

In a Spring MVC controller:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class AuthenticationInfoController {

    @GetMapping("/api/whoami")
    Map<String, Object> whoAmI(Authentication authentication) {
        List<String> authorities = authentication.getAuthorities()
            .stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "name", authentication.getName(),
            "authenticated", authentication.isAuthenticated(),
            "authorities", authorities
        );
    }
}
~~~

This is an **illustrative learning endpoint**; if used in production, restrict access and avoid over-exposing information. Never include `authentication.getCredentials()` or raw tokens in responses.

In controllers dedicated to JWT handling, you can inject the principal:

~~~java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class JwtPrincipalController {

    @GetMapping("/api/me")
    Map<String, String> me(@AuthenticationPrincipal Jwt jwt) {
        return Map.of("subject", jwt.getSubject());
    }
}
~~~

`@AuthenticationPrincipal Jwt` is only appropriate when JWT authentication yields a `Jwt` principal. If the API uses opaque tokens, the principal is usually `OAuth2AuthenticatedPrincipal`; injecting `Jwt` in that case may yield null.

## 5. Building a `SecurityFilterChain` with Mapped Permissions

A Spring MVC Resource Server application with JWT typically needs:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Example issuer configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/company
~~~

Bean protecting Orders API GET requests:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class OrdersSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(withDefaults()))
            .build();
    }
}
~~~

Logical sequence:

1. The JWT must be verified successfully; invalid tokens are rejected.
2. The default converter maps `scope=orders.read` to `SCOPE_orders.read`.
3. `hasAuthority("SCOPE_orders.read")` allows GET requests to proceed when the authority matches.
4. The service must still verify ownership of the specific order, tenant, and other business rules.

`anyRequest().authenticated()` only requires authentication for unmatched requests and does not restrict sensitive actions by scope on its own. In a real API, define explicit rules for each operation or use a `denyAll` default policy where appropriate.

Another distinction: `issuer-uri` configures the issuer source and default JWT validation, yet **does not automatically prove the token has the API's audience** in all cases. When the contract requires `aud=orders-api`, configure an explicit audience validator or the corresponding framework configuration mechanism.

## 6. Customizing JWT: Changing the Scope Claim Name and Authority Prefix

Not every Authorization Server uses the same claim names. An issuer may use:

~~~json
{
  "sub": "user-123",
  "permissions": ["orders:read", "orders:create"]
}
~~~

If the contract guarantees `permissions` is a **trusted array of permissions**, you can use `JwtGrantedAuthoritiesConverter`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter grants =
        new JwtGrantedAuthoritiesConverter();

    grants.setAuthoritiesClaimName("permissions");
    grants.setAuthorityPrefix("PERMISSION_");

    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(grants);
    return converter;
}
~~~

This converter produces:

~~~text
permissions = ["orders:read", "orders:create"]

GrantedAuthority:
    PERMISSION_orders:read
    PERMISSION_orders:create
~~~

Corresponding rule:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("PERMISSION_orders:read")
~~~

**Merely defining a converter bean may not be enough for the Resource Server to use it.** Register the converter in the security chain's JWT DSL:

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        JwtAuthenticationConverter jwtAuthenticationConverter) throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("PERMISSION_orders:read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
            jwt.jwtAuthenticationConverter(jwtAuthenticationConverter)))
        .build();
}
~~~

This snippet is an **alternative configuration** to the `SecurityFilterChain` bean in Section 5. In a real application, keep only one chain definition matching those requests, or configure multiple chains with explicit matchers and ordering; do not copy all examples into multiple beans that all match every path.

### 6.1. Keeping the `SCOPE_` Prefix When Changing the Claim Name

If the issuer uses `permissions` while the actual semantics are still **scopes**, you can change only the claim name and keep the default `SCOPE_` prefix:

~~~java
JwtGrantedAuthoritiesConverter grants =
    new JwtGrantedAuthoritiesConverter();
grants.setAuthoritiesClaimName("permissions");
// Do not call setAuthorityPrefix: continues using the default SCOPE_ prefix.
~~~

Keep **authority names consistent between the converter and rules**. Avoid changing the prefix and forgetting to update `@PreAuthorize` expressions and `authorizeHttpRequests` rules.

### 6.2. Changing the Principal Name Claim

`JwtAuthenticationConverter` can also change the claim used for `Authentication.getName()`:

~~~java
JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
converter.setPrincipalClaimName("preferred_username");
~~~

For example, `preferred_username` can help display a friendly name, though it is not always immutable or globally unique. For data ownership checks, prefer a stable identifier such as the combination of issuer and `sub` per contract. **Changing `getName()` does not give the JWT any extra authorities**, nor does it turn the JWT principal into a `UserDetails`.

## 7. When Claims Contain Roles: `ROLE_*` vs. `SCOPE_*`

In Spring Security, commonly used rules are:

| Syntax | Typical required authority | Meaning |
|---|---|---|
| `hasAuthority("SCOPE_orders.read")` | `SCOPE_orders.read` | Checks scope directly |
| `hasAuthority("ROLE_ADMIN")` | `ROLE_ADMIN` | Checks exact role authority |
| `hasRole("ADMIN")` | `ROLE_ADMIN` (with default role prefix) | Shorthand syntax for roles |
| `hasAuthority("PERMISSION_orders:read")` | `PERMISSION_orders:read` | Custom permission per contract |

JWT containing:

~~~json
{
  "sub": "user-123",
  "scope": "orders.read",
  "roles": ["ADMIN", "AUDITOR"]
}
~~~

**Spring Security JWT Resource Server does not automatically map every `roles` claim to `ROLE_*`.** The default path prioritizes `scope`/`scp`. To combine scopes and roles, configure a converter matching the issuer contract.

### 7.1. Combining Scopes and Roles in a Converter

Suppose the issuer guarantees the `roles` claim is a **string array of role names** formatted like `ADMIN`, `AUDITOR`. The code below keeps default scopes and adds roles:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

public final class OrdersJwtConverterFactory {

    public static JwtAuthenticationConverter create() {
        JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

        Converter<Jwt, Collection<GrantedAuthority>> authorities = jwt -> {
            List<GrantedAuthority> result = new ArrayList<>();

            Collection<GrantedAuthority> scopeAuthorities =
                scopes.convert(jwt);
            if (scopeAuthorities != null) {
                result.addAll(scopeAuthorities);
            }

            List<String> roles = jwt.getClaimAsStringList("roles");
            if (roles != null) {
                for (String role : roles) {
                    if (role != null && role.matches("[A-Z][A-Z0-9_]*")) {
                        result.add(new SimpleGrantedAuthority("ROLE_" + role));
                    }
                }
            }
            return result;
        };

        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(authorities);
        return converter;
    }
}
~~~

Output for the sample JWT:

~~~text
SCOPE_orders.read
ROLE_ADMIN
ROLE_AUDITOR
~~~

This code is an example for a **flat `roles` claim** and does not automatically handle nested structures like `realm_access.roles` or `resource_access.{client}.roles` used by some providers. If your issuer returns role claims in another shape, confirm the exact contract and write the corresponding extractor.

Pattern-filtering strings in the example avoids unexpected authorities from malformed data; **it does not replace token validation**. Only add roles when the issuer is trusted, audience matches, the token is valid, and the claim source is recognized by the system. Avoid arbitrarily mapping client-populated claims into administrative roles.

### 7.2. Alternative Mapping When the Issuer Uses Namespaced Roles

A system might issue `roles = ["orders-admin"]` instead of `ADMIN`. In that case, the application should map explicitly:

~~~text
Issuer role "orders-admin" → GrantedAuthority "ROLE_ORDERS_ADMIN"
Issuer role "orders-viewer" → GrantedAuthority "ROLE_ORDERS_VIEWER"
~~~

Avoid a blanket rule replacing `-` with `_` for all roles if there is any risk of name collisions or privilege escalation. An explicit mapping table is easier to review for sensitive privileges.

## 8. Converting Opaque Tokens into `BearerTokenAuthentication`

Not every access token can be decoded locally as a JWT. With **opaque tokens**, the Resource Server usually calls the Authorization Server's **OAuth 2.0 Token Introspection** (RFC 7662). The client still sends:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer opa_example_random_string
~~~

Spring Security does not look at whether a token contains dots to infer permissions. When `opaqueToken()` is configured, `OpaqueTokenAuthenticationProvider` uses `OpaqueTokenIntrospector` to verify the token per the introspection contract.

### 8.1. Conversion Chain for Opaque Tokens

~~~mermaid
flowchart TD
    A["Authorization: Bearer opaque-token"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["BearerTokenAuthenticationToken"]
    C --> D["OpaqueTokenAuthenticationProvider"]
    D --> E["OpaqueTokenIntrospector"]
    E --> F["AS Introspection Endpoint"]
    F --> G{"active + valid policy?"}
    G -->|No| H["Authentication rejected"]
    G -->|Yes| I["OAuth2AuthenticatedPrincipal"]
    I --> J["Authorities from scope/metadata"]
    J --> K["BearerTokenAuthentication"]
    K --> L["SecurityContextHolder"]
    L --> M["Authorization rules"]
~~~

Example response from a trusted introspection endpoint:

~~~json
{
  "active": true,
  "sub": "user-123",
  "client_id": "shop-client",
  "scope": "orders.read profile",
  "aud": ["orders-api"],
  "exp": 1924992000
}
~~~

Attributes other than `active` can vary by Authorization Server. The API must never treat every `active=true` introspection response as sufficient for authorization; if the contract requires **audience, tenant, client identity, or token type**, ensure those conditions are checked by a trusted mechanism.

| Introspection data | Typical behavior in Spring Security |
|---|---|
| `active = false` | Introspector rejects token; no valid authenticated principal created |
| `active = true` | Can create `OAuth2AuthenticatedPrincipal` with attributes and authorities |
| `scope = "orders.read profile"` | Typically mapped to `SCOPE_orders.read`, `SCOPE_profile` |
| `sub = "user-123"` | Can be used as principal name, depending on introspector and token profile |
| `client_id = "shop-client"` | Attribute available for custom policies |
| `aud = ["orders-api"]` | Resource binding must be verified per contract; do not assume every introspector checks it automatically |

Spring Security builds an authentication result of type **`BearerTokenAuthentication`**, containing an `OAuth2AuthenticatedPrincipal`. The authorities used by the provider come from the principal returned by the introspector. Unlike JWT, no `JwtAuthenticationConverter` participates by default in the opaque token pipeline.

### 8.2. Basic Spring Boot Configuration

The dependency remains `spring-boot-starter-oauth2-resource-server`; configuration for opaque tokens:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: ${OAUTH_INTROSPECTION_URI}
          client-id: ${OAUTH_INTROSPECTION_CLIENT_ID}
          client-secret: ${OAUTH_INTROSPECTION_CLIENT_SECRET}
~~~

These values must come from secure configuration or a secret manager. `client-id` and `client-secret` are the **Resource Server's credentials at the introspection endpoint**, distinct from the credential sent by the end user/client in the Bearer header.

To enable the opaque token branch in the Servlet security chain:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(withDefaults()))
        .build();
}
~~~

This is an **alternative security chain** to the JWT example in the previous section. Compiling this method requires the imports introduced in Section 5. In a real application, select the authentication mechanism matching the Authorization Server's token type and contract; do not arbitrarily enable multiple configurations and rely on token string appearance.

### 8.3. Reading an Opaque Token Principal

~~~java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OpaquePrincipalController {

    @GetMapping("/api/me")
    Map<String, String> me(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        return Map.of("name", principal.getName());
    }
}
~~~

Do not assume `principal.getName()` is always an end user. With `client_credentials`, the principal may represent an application or service. If the API needs to distinguish service tokens from delegated user tokens, that is **part of the access token contract**, not just a naming choice.

### 8.4. When Custom Authorities Are Needed for Opaque Tokens

Suppose introspection returns an additional claim verified by the Identity team:

~~~json
{
  "active": true,
  "sub": "user-123",
  "scope": "orders.read",
  "roles": ["SUPERVISOR"]
}
~~~

To turn `roles` into `ROLE_SUPERVISOR`, you can create an introspector decorator. Core of the decorator:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class RoleMappingOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    public RoleMappingOpaqueTokenIntrospector(
            OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        // Delegate validates the token with the introspection endpoint first.
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        List<GrantedAuthority> authorities =
            new ArrayList<>(principal.getAuthorities());
        Object roles = principal.getAttribute("roles");

        if (roles instanceof Collection<?> roleValues) {
            for (Object role : roleValues) {
                if (role instanceof String roleName
                        && roleName.matches("[A-Z][A-Z0-9_]*")) {
                    authorities.add(
                        new SimpleGrantedAuthority("ROLE_" + roleName)
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

The decorator preserves existing authorities, so scopes like `SCOPE_orders.read` are not lost. It only adds roles when the claim has a contract-allowed format. **This code does not create the delegate bean itself**: you must supply it with an `OpaqueTokenIntrospector` configured with the trusted endpoint and client credentials, then register the result in your security configuration. If you define an `OpaqueTokenIntrospector` bean yourself, check how it interacts with auto-configuration; Spring Boot may stop auto-configuring the default introspector once an application bean exists.

For introspection from an issuer serving multiple resources, the decorator can also check `aud`, `tenant`, or principal type **before returning an accepted result**. Never just append authorities and ignore other mandatory constraints.

## 9. When Is `Authentication` Placed into `SecurityContextHolder`?

In Servlet Spring Security, `SecurityContextHolder` is the standard access point to the current execution's `SecurityContext`. The default strategy is typically `ThreadLocal`-based.

After the provider authenticates successfully, the filter creates/updates the security context with the authenticated `Authentication`, and the processing chain continues to authorization and the controller:

~~~text
BearerTokenAuthenticationFilter
    |
    | AuthenticationManager.authenticate(...)
    v
JwtAuthenticationToken / BearerTokenAuthentication
    |
    v
SecurityContext
    |
    v
SecurityContextHolder
    |
    v
AuthorizationFilter -> DispatcherServlet / Controller
~~~

Typical Servlet code to read the context:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

if (authentication != null) {
    String principalName = authentication.getName();
}
~~~

**Only read the context after the filter chain has performed authentication** if your logic depends on the current identity. `Authentication` may be `null` or anonymous on public endpoints. Avoid casting every principal to `Jwt` or `UserDetails` without checking the implementation.

### 9.1. ThreadLocal, Request Lifecycle, and Asynchrony

In Servlet apps, the security context is normally bound to the request-handling thread and managed and cleared by the framework across the lifecycle. If business code spawns threads, uses `CompletableFuture`, `@Async`, or custom executors, do not assume the context automatically propagates to other threads. Spring Security provides `DelegatingSecurityContext...` utilities when context propagation across async tasks is truly needed.

Never copy a raw access token into a global or static variable to "preserve login state." That is not a valid way to store a security context and can leak credentials across requests.

A **stateless** Bearer token API does not need to store `Authentication` in an HTTP session for reuse on subsequent requests: each request can send an access token and be re-authenticated per policy. However, always inspect how sessions, context repositories, and other authentication mechanisms are actually configured in the app; do not assume merely enabling `oauth2ResourceServer()` guarantees every component is completely session-free.

### 9.2. Why Not Build an Authenticated Token from Request Parameters?

The pattern below is **unsafe** when role/name data comes directly from the client without verification:

~~~java
// ANTI-PATTERN — never use to authenticate requests:
// String role = request.getParameter("role");
// Authentication fake = new UsernamePasswordAuthenticationToken(
//     request.getParameter("user"),
//     null,
//     List.of(new SimpleGrantedAuthority("ROLE_" + role))
// );
// SecurityContextHolder.getContext().setAuthentication(fake);
~~~

An attacker can simply send `role=ADMIN`. The proper path is letting **`AuthenticationProvider`** use verified data from the token/issuer to construct trusted authorities. If the application must map permissions from a database, that lookup and attachment must happen inside a trusted component with clear identity, tenant, and authorization constraints.

## 10. How Does Authorization Use `GrantedAuthority`?

Once the token has been converted into `Authentication`, Spring Security rules check the collection returned by `authentication.getAuthorities()`.

### 10.1. Checking at the HTTP Layer

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders")
        .hasAuthority("SCOPE_orders.create")
    .requestMatchers("/api/admin/**")
        .hasRole("ADMIN")
    .anyRequest().authenticated()
);
~~~

In this context:

- GET requires `SCOPE_orders.read`.
- POST creating an order requires `SCOPE_orders.create`.
- `hasRole("ADMIN")` typically requires `ROLE_ADMIN` per the default role prefix.
- Remaining requests only require successful authentication; real systems must define additional business permissions.

This is an illustrative DSL configuration snippet inside `HttpSecurity`, not a standalone Java class. If the API uses cookies for browser authentication, handle CSRF for state-changing HTTP methods; do not disable CSRF by default just while studying rules.

### 10.2. Checking at the Method Level

Spring Security can protect service methods with `@PreAuthorize` when `@EnableMethodSecurity` is enabled:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderView readOrder(String orderId) {
        // The service must still check owner/tenant before returning data.
        return loadOrderForCurrentPrincipal(orderId);
    }
}
~~~

`OrderView` and `loadOrderForCurrentPrincipal` are business types to be defined by the application; the snippet illustrates where to place the rule. `@PreAuthorize` must execute through Spring's method security proxy on a Spring-managed bean. An internal self-invocation bypassing the proxy may not trigger method security as expected.

### 10.3. Scopes Do Not Replace Record-Level Access Control

Suppose an authenticated token has:

~~~text
principal = user-123
authorities = [SCOPE_orders.read]
~~~

These requests share the exact same authority:

~~~text
GET /api/orders/42   (ownerId = user-123)
GET /api/orders/99   (ownerId = user-999)
~~~

Authority `SCOPE_orders.read` permits **the order-reading action type**, yet only the first request may satisfy the ownership policy. The service must verify owner/tenant/data policies after the HTTP layer confirms the scope. Otherwise, **Broken Object Level Authorization (BOLA)** can occur even with a valid token and scope.

A business implementation might look like:

~~~java
public OrderView findOrderForUser(String orderId, String subject) {
    Order order = repository.findById(orderId)
        .orElseThrow(OrderNotFoundException::new);

    if (!order.getOwnerSubject().equals(subject)) {
        throw new AccessDeniedException("Order access denied");
    }
    return toView(order);
}
~~~

Classes `Order`, `OrderView`, `OrderNotFoundException`, `repository`, and `toView` are assumed to belong to the application. The purpose is illustrating the order **authentication → scope → ownership**. For multi-tenant systems, scope `subject` within the appropriate issuer/tenant namespace; never use an unverified raw username as a global key.

## 11. Distinguishing Token Conversion Errors from Insufficient-Permission Errors

| Scenario | Stage | Typical response |
|---|---|---|
| No Bearer token on endpoint requiring authentication | No valid authentication yet | `401 Unauthorized` |
| Malformed HTTP Bearer token structure | Token resolution / authentication | Usually rejected; RFC 6750 includes `invalid_request` cases |
| JWT with bad signature, issuer, or expired | `JwtDecoder` / validator | `401 Unauthorized` |
| Inactive opaque token | `OpaqueTokenIntrospector` | `401 Unauthorized` |
| Valid token lacking required scope claim | Authority mapping then authorization | `403 Forbidden` |
| Valid token with scope but lacking required role | Authorization | `403 Forbidden` |
| Valid token, sufficient scope, but wrong resource owner | Business authorization | `403 Forbidden`; may be masked as `404` per policy |
| Valid token, full permissions, policy satisfied | Controller/service | Business-determined status |
| Introspection endpoint network failure or bad client secret | Auth infrastructure / upstream | Fail closed; HTTP status to client depends on error handling |

A Resource Server using Bearer authentication may return:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

When the token is authenticated but lacks scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.read"
~~~

These are illustrative **RFC 6750** responses; exact error codes and headers may vary by request, filter, exception handler, and Spring Security configuration. Never put raw tokens or secret key details into `error_description`.

### 11.1. Very Common Authority Prefix Mistake

Example token claim:

~~~json
{ "scope": "orders.read" }
~~~

Spring Security default mapping:

~~~text
SCOPE_orders.read
~~~

Yet the application writes:

~~~java
.hasAuthority("orders.read")
~~~

Requests will receive `403` even though the token authenticated validly. The fix is matching **rule values** and **converter output** per contract, for example:

~~~java
.hasAuthority("SCOPE_orders.read")
~~~

Never "fix" this error by disabling JWT signature checks, dropping issuer validation, or adding `permitAll()`.

### 11.2. `roles` Claim Present, Yet `hasRole("ADMIN")` Still Returns 403

Without configuring a converter, Spring Security JWT Resource Server does not read a `roles` claim automatically. After authentication, `Authentication.getAuthorities()` may contain only `SCOPE_*`. To use `hasRole("ADMIN")`, the converter must emit `ROLE_ADMIN` from a trusted, configured role source.

### 11.3. Valid JWT Signature, Yet Intended for a Different API

Claim:

~~~json
{ "aud": ["billing-api"], "scope": "orders.read" }
~~~

If the Orders API requires audience `orders-api`, this token must be rejected **at the authentication/validation step** even though the scope looks right. Map authorities only after verifying the right source and right resource. Never let a converter "patch" the audience to accept the token.

### 11.4. Converter Errors Differ from Missing-Scope Errors

A custom converter may throw an exception due to a `roles` claim having the wrong data type, unexpected null, or parsing bugs. An unhandled Java exception can cause a server error instead of an intentional 403. Converter design should:

- Specify expected claim types and how missing claims are handled.
- Never fabricate permissions when claims are missing or invalid.
- Never mix unverified request data into permissions.
- Enforce rules to reject tokens if the contract requires mandatory claims that are absent.
- Separate **lacking permission** (authorization) from **contract-invalid token** (authentication/validation).

If a mandatory claim determines whether the token is acceptable at all, a **validator at the decoder/introspection step** is usually more appropriate than letting the converter silently turn the token into an authentication with missing permissions. A converter's primary job is mapping verified data.

## 12. Role of `AuthenticationManager` and Providers

`AuthenticationManager` accepts an input `Authentication` and returns an authenticated `Authentication` or throws an appropriate error. The common Servlet security implementation is `ProviderManager`, which manages `AuthenticationProvider`s.

~~~text
AuthenticationManager.authenticate(
    new BearerTokenAuthenticationToken(rawToken)
)
          |
          v
ProviderManager
          |
          +-- JWT Resource Server:
          |      JwtAuthenticationProvider
          |        → JwtDecoder
          |        → JwtAuthenticationConverter
          |        → JwtAuthenticationToken
          |
          +-- Opaque Resource Server:
                 OpaqueTokenAuthenticationProvider
                   → OpaqueTokenIntrospector
                   → BearerTokenAuthentication
~~~

The key difference lies in **how the token is verified and how the principal is mapped**. Controllers/services can depend on the common `Authentication` and `GrantedAuthority` interfaces to avoid tight coupling to JWT/opaque tokens; only when specific claims are needed must concrete principal types be handled.

A `ProviderManager` can hold multiple providers for different authentication mechanisms, though ordering and token support must be configured explicitly. Never route JWT tokens to an opaque introspector or vice versa without an intentional token-resolution/multi-token design.

## 13. Side-by-Side Comparison of JWT and Opaque Token Flows

| Characteristic | JWT access token | Opaque access token |
|---|---|---|
| Bearer request header | `Authorization: Bearer ...` | `Authorization: Bearer ...` |
| Servlet filter | `BearerTokenAuthenticationFilter` | `BearerTokenAuthenticationFilter` |
| Provider input | `BearerTokenAuthenticationToken` | `BearerTokenAuthenticationToken` |
| `AuthenticationProvider` | `JwtAuthenticationProvider` | `OpaqueTokenAuthenticationProvider` |
| Token verification | `JwtDecoder` + validators (signature, claims, issuer, audience per config) | `OpaqueTokenIntrospector` + introspection contract |
| Authenticated principal | Typically `Jwt` | Typically `OAuth2AuthenticatedPrincipal` |
| Where authorities are converted | `JwtAuthenticationConverter`, `JwtGrantedAuthoritiesConverter` | Authorities returned by `OpaqueTokenIntrospector` / principal |
| Resulting `Authentication` | `JwtAuthenticationToken` | `BearerTokenAuthentication` |
| Stored in security context | `SecurityContextHolder` | `SecurityContextHolder` |
| Authorization rules | `hasAuthority("SCOPE_...")`, role/custom policies | Matching authority rules |
| Customization | JWT claim converters and validators | Decorator/custom introspector, metadata validation |

**The same `scope` name does not guarantee the same semantics across multiple issuers.** If an API trusts multiple Authorization Servers, ensure each issuer has a compatible permission contract or apply separate mappings and checks.

## 14. Verifying Mapping with Sample Data

### 14.1. Token and Authority Mapping Reference

| Verified data | Common default converter | Resulting authorities |
|---|---|---|
| JWT `scope: "orders.read profile"` | `JwtGrantedAuthoritiesConverter` | `SCOPE_orders.read`, `SCOPE_profile` |
| JWT `scp: ["orders.read"]` | `JwtGrantedAuthoritiesConverter` | `SCOPE_orders.read` |
| JWT without `scope`/`scp` | No standard scope to map | No `SCOPE_*` authorities generated from scopes |
| JWT `roles: ["ADMIN"]`, no role converter | Custom role unhandled | Does not auto-generate `ROLE_ADMIN` |
| JWT `permissions: ["orders:read"]` with custom converter | `JwtGrantedAuthoritiesConverter` with custom claim and prefix | `PERMISSION_orders:read` |
| Opaque introspection `scope: "orders.read"` | Matching introspector returns scope permissions | `SCOPE_orders.read` |
| Opaque introspection with `roles` and trusted decorator | Additional role mapping | `ROLE_SUPERVISOR` per example |

### 14.2. Reading an `Authentication` Result Exercise

Suppose authentication yields:

~~~text
Authentication implementation: JwtAuthenticationToken
getName(): user-123
isAuthenticated(): true
authorities:
    SCOPE_orders.read
    SCOPE_profile
~~~

Evaluating rules:

| Rule | Result |
|---|---|
| `authenticated()` | Passes |
| `hasAuthority("SCOPE_orders.read")` | Passes |
| `hasAuthority("SCOPE_orders.write")` | Fails |
| `hasRole("ADMIN")` | Fails due to missing `ROLE_ADMIN` |
| `hasAnyAuthority("SCOPE_profile", "SCOPE_orders.write")` | Passes because `SCOPE_profile` is present |

These outcomes only illustrate authority and authentication evaluation. If a rule combines ownership, tenant, client type, or business state conditions, the request can still be denied even when a scope rule passes.

### 14.3. Unit-Testing a Converter on a Sample `Jwt` Object

You can verify the mapping path in plain Java by building a `Jwt` **for testing the converter**, without signing a JWT:

~~~java
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

Jwt jwt = Jwt.withTokenValue("example-only")
    .header("alg", "RS256")
    .claim("sub", "user-123")
    .claim("scope", "orders.read profile")
    .build();

JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
JwtAuthenticationToken authentication =
    (JwtAuthenticationToken) converter.convert(jwt);

// Example output:
// authentication.getName()                 -> "user-123"
// authentication.getAuthorities()          -> SCOPE_orders.read, SCOPE_profile
// authentication.isAuthenticated()         -> true
~~~

This snippet demonstrates the concept **input claims → `JwtAuthenticationConverter` → authorities**, yet **does not verify any real signature**, does not invoke `JwtDecoder`, and does not replace Resource Server integration tests. Never construct a `Jwt` object from a request body to authenticate real HTTP requests.

## 15. Misconceptions to Avoid

### "Having a `role` claim in the JWT means having a Spring Security role"

Incorrect. A verified JWT only supplies trusted claim data per contract. A converter is needed to turn that claim into matching `GrantedAuthority` instances. With a default Resource Server, authorities typically originate from `scope` or `scp`.

### "`getPrincipal()` is always a `String` username"

No. With `JwtAuthenticationToken`, the principal is typically `Jwt`; with opaque-token `BearerTokenAuthentication`, it is `OAuth2AuthenticatedPrincipal`. Retrieve the name via `getName()` or use the appropriate principal type API.

### "Changing `getName()` means changing permissions"

No. `JwtAuthenticationConverter.setPrincipalClaimName(...)` adjusts the authentication's representative name, while authority mapping belongs to `JwtGrantedAuthoritiesConverter` or a corresponding converter. Those are two separate decisions.

### "`hasRole("ADMIN")` automatically checks `scope=ADMIN`"

No. By default, `hasRole("ADMIN")` checks `ROLE_ADMIN`; a scope maps to `SCOPE_ADMIN` if a scope named `ADMIN` exists. Explicit mapping is required to bridge data between the two namespaces.

### "Being able to read the JWT payload means it is authenticated"

No. Base64URL payloads can be forged. `JwtDecoder` and validators must verify signature, issuer, validity timestamps, and constraints such as audience before the converter reads any claims.

### "Introspection `active=true` means the token works for every API"

No. Suitability for a **specific Resource Server**, scopes, and tenants must still be verified by the introspection contract and API policy.

### "Having `SCOPE_orders.read` allows reading every order"

No. An authority only indicates permission for an operation at a coarse level. Services must check record permissions, subject, tenant, and other rules to prevent data exposure.

### "`SecurityContextHolder` keeps `Authentication` forever across all threads"

No. In Servlet apps, the context is bound by default to the current execution/thread and the security framework lifecycle. Manually spawned threads and async execution require explicit context propagation when truly needed.

### "Defining a converter bean automatically affects every security chain"

Do not assume that. Verify which chain uses which converter and attach converters explicitly in the DSL when customizing. With multiple chains, clearly configure which chain accepts which token type and which permission rules apply.

## 16. Self-Check Questions

**Question 1.** Which class extracts Bearer tokens from Servlet requests in a typical Spring Security Resource Server setup?

`BearerTokenAuthenticationFilter` using `BearerTokenResolver`. The initial result is represented as an unauthenticated `BearerTokenAuthenticationToken`.

**Question 2.** When using JWTs, which class converts verified claims into authorities?

`JwtAuthenticationConverter`, typically delegating to `JwtGrantedAuthoritiesConverter`. In the default configuration, `scope`/`scp` data maps to `SimpleGrantedAuthority` with the `SCOPE_` prefix.

**Question 3.** When using opaque tokens, is `JwtAuthenticationConverter` needed?

Usually **no**. `OpaqueTokenIntrospector` returns the principal and authorities; `OpaqueTokenAuthenticationProvider` builds `BearerTokenAuthentication`.

**Question 4.** A token has `scope="orders.read"` while a rule uses `hasAuthority("orders.read")`. Why can this return 403?

Because the default authority name is `SCOPE_orders.read`. Either the rule must match the exact authority string or the converter must be intentionally configured differently.

**Question 5.** Why is `hasAuthority("SCOPE_orders.read")` alone insufficient to return any order?

Because scopes do not verify ownership of individual orders. The business layer must verify subject/tenant and record-level permissions.

**Question 6.** When are principals/roles considered trustworthy?

Only after the authentication mechanism verifies the token against a trusted issuer, keys/algorithms, or introspection endpoint, along with validity timestamps and required constraints. The converter is not a substitute for token validation.

## 17. Remembering the Conversion Flow

For **JWT**:

~~~text
HTTP Authorization: Bearer
  → BearerTokenAuthenticationFilter
  → BearerTokenAuthenticationToken (unauthenticated)
  → AuthenticationManager
  → JwtAuthenticationProvider
  → JwtDecoder + validators
  → JwtAuthenticationConverter
  → JwtGrantedAuthoritiesConverter
  → JwtAuthenticationToken (principal Jwt, authorities)
  → SecurityContextHolder
  → HTTP authorization / method security
~~~

For **opaque tokens**:

~~~text
HTTP Authorization: Bearer
  → BearerTokenAuthenticationFilter
  → BearerTokenAuthenticationToken (unauthenticated)
  → AuthenticationManager
  → OpaqueTokenAuthenticationProvider
  → OpaqueTokenIntrospector
  → OAuth2AuthenticatedPrincipal + authorities
  → BearerTokenAuthentication
  → SecurityContextHolder
  → HTTP authorization / method security
~~~

**`Authentication` is the authentication result**, while **`GrantedAuthority` is how Spring Security represents permissions for authorization**. The JWT and opaque branches differ in how credentials are verified and how principals/authorities are extracted, yet both ultimately place a valid `Authentication` into the Servlet security context to enforce API access rules.

## References

- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Servlet Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security — Servlet Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
