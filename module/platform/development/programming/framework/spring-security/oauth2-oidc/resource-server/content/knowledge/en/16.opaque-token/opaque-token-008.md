# `OAuth2AuthenticatedPrincipal`, `attributes`, `name`, and `authorities`

In a **Spring Security OAuth 2.0 Resource Server**, **opaque** access tokens are typically not decoded locally by the API like JWTs. Instead, the Resource Server sends the token to the Authorization Server's **token introspection endpoint** to determine whether the token is active and retrieve the necessary metadata. After that verification step, Spring Security represents the identity and access permissions via an object implementing **`OAuth2AuthenticatedPrincipal`**.

This object has three key facets:

- **`attributes`:** token or principal data/metadata returned by introspection and accepted by the introspector.
- **`name`:** the identifier exposed by Spring Security via `getName()`, which is not necessarily the same as a display username, email, or `client_id`.
- **`authorities`:** the `GrantedAuthority` collection used by authorization rules such as `hasAuthority("SCOPE_orders.read")`.

A common mistake is seeing `"scope": "orders.read"` in an introspection response and assuming every service will automatically receive `SCOPE_orders.read`, or seeing `sub` and assuming the caller can read every record. You need to understand **who builds the principal**, **how attributes turn into authorities**, **where `getName` comes from**, and **which business permissions still must be checked separately**.

This lesson focuses on **Opaque Token Resource Server** in Spring Security Servlet, while comparing principal types with JWT Resource Server to prevent invalid casts.

## 1. Where `OAuth2AuthenticatedPrincipal` sits in the opaque token flow

A client calls the Orders API with an access token:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer 6b09f46f-opaque-token-example
~~~

The string `6b09f46f-opaque-token-example` is purely illustrative data, not a usable token. The Resource Server **does not** infer user permissions from the shape of this string.

Typical processing flow:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client
    participant F as BearerTokenAuthenticationFilter
    participant P as OpaqueTokenAuthenticationProvider
    participant I as OpaqueTokenIntrospector
    participant AS as Authorization Server
    participant A as AuthorizationFilter
    participant API as Controller

    C->>F: GET /api/orders + Authorization: Bearer token
    F->>P: BearerTokenAuthenticationToken via AuthenticationManager
    P->>I: introspect(token)
    I->>AS: HTTP POST introspection (TLS + client authentication)
    AS-->>I: active=true + scope/sub/client_id/exp/...
    I-->>P: OAuth2AuthenticatedPrincipal
    P-->>F: BearerTokenAuthentication
    F->>F: Store Authentication in SecurityContext
    F->>A: Continue processing request
    alt Authorized
        A->>API: Forward request
        API-->>C: Permitted data
    else Unauthorized
        A-->>C: 403 Forbidden
    end
~~~

If the Authorization Server returns `active: false` or the introspector cannot validate the token per policy, **no trusted principal is created** to let the request proceed. Authentication failure typically produces **401 Unauthorized**. When the token is authenticated yet lacks endpoint permissions, it typically produces **403 Forbidden**.

| Component | Role |
| --- | --- |
| `BearerTokenAuthenticationFilter` | Extracts Bearer token and builds authentication request |
| `BearerTokenAuthenticationToken` | Carries raw incoming token string; not yet an authenticated principal |
| `AuthenticationManager` | Routes the request to the matching provider |
| `OpaqueTokenAuthenticationProvider` | Invokes introspector and builds successful authentication or reports error |
| `OpaqueTokenIntrospector` | Verifies token with issuer and returns trusted metadata/principal per contract |
| `OAuth2AuthenticatedPrincipal` | Interface for attributes, name, and authorities of the introspection-accepted subject |
| `DefaultOAuth2AuthenticatedPrincipal` | A common implementation of that interface |
| `BearerTokenAuthentication` | Resulting `Authentication` object stored in `SecurityContext` |
| `AuthorizationFilter` and method security | Checks authorities and access policies |

**Do not confuse `OAuth2AuthenticatedPrincipal` with the Authorization Server or OAuth2 Client.** It is a **Resource Server-side** object representing the principal after introspection; it **does not issue, refresh, or revoke tokens**.

## 2. Introspection response: the input data for the principal

Under the OAuth 2.0 Token Introspection model (RFC 7662), the Resource Server sends the token to an issuer-approved endpoint. Example outbound request:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic <resource-server-credentials>
Content-Type: application/x-www-form-urlencoded

token=<access-token>
~~~

The credentials used to call introspection **differ** from the access token sent by the client to the API. The actual endpoint, authentication method, and required parameters depend on the Authorization Server.

An active response might look like:

~~~json
{
  "active": true,
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "client_id": "orders-web",
  "username": "alice",
  "scope": "orders.read orders.export",
  "token_type": "Bearer",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "iat": 1893452400,
  "tenant_id": "t-7",
  "permissions": ["orders:view", "reports:export"]
}
~~~

If the token is inactive:

~~~json
{
  "active": false
}
~~~

Never assume **every introspection response contains all the fields in the example**. Under RFC 7662, `active` is the core status field; much of the remaining metadata **may be optional** or withheld depending on caller permissions. Some issuers include custom claims such as `tenant_id` or `permissions`.

### Three data levels to keep separate

1. **HTTP JSON introspection response:** raw data from the Authorization Server via the configured endpoint.
2. **`OAuth2AuthenticatedPrincipal.getAttributes()`:** the attribute map processed by the introspector and handed to Spring Security. Java types may have been normalized.
3. **`OAuth2AuthenticatedPrincipal.getAuthorities()`:** authorities produced by the introspector or a custom converter from accepted info; **not all JSON attributes**.

When introspection returns `active: false`, the Resource Server must reject the token. Never "borrow" `scope`/`sub` from an unaccepted response.

**Protect the introspection channel:** call only trusted issuer endpoints over TLS, manage credentials as secrets, enforce timeouts, and fail closed on errors. Never send tokens to a URL self-declared by the client in a payload or header.

## 3. What does the `OAuth2AuthenticatedPrincipal` interface contain?

The interface belongs to the Spring Security OAuth 2.0 Core module:

~~~java
import java.util.Collection;
import java.util.Map;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

// Key conceptual methods:
Map<String, Object> attributes = principal.getAttributes();
Object subject = principal.getAttribute("sub");
String name = principal.getName();
Collection<? extends GrantedAuthority> authorities =
    principal.getAuthorities();
~~~

`getAttribute(String)` is a convenient accessor for a single attribute in the map. It does not validate claim contents itself, does not guarantee the attribute exists, and does not automatically coerce JSON data into a specific domain DTO.

| API | Data type | Meaning |
| --- | --- | --- |
| `getAttributes()` | `Map<String, Object>` | Metadata supplied by the introspector |
| `getAttribute("sub")` | Generic value, nullable | Fetches an attribute by name |
| `getName()` | `String` | Principal name chosen by the implementation |
| `getAuthorities()` | `Collection<? extends GrantedAuthority>` | Permissions used by Spring Security for authorization |

**`getName()` is not a copy of all attributes**, and **`getAuthorities()` is not the claims map**. They are three distinct views of one principal.

### Example using `DefaultOAuth2AuthenticatedPrincipal`

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

Map<String, Object> attributes = Map.of(
    "sub", "user-42",
    "client_id", "orders-web",
    "scope", "orders.read"
);

OAuth2AuthenticatedPrincipal principal =
    new DefaultOAuth2AuthenticatedPrincipal(
        "user-42",
        attributes,
        List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
    );

System.out.println(principal.getName());          // user-42
System.out.println(principal.getAttribute("sub")); // user-42
System.out.println(principal.getAuthorities());    // [SCOPE_orders.read]
~~~

This example **manually constructing a principal** only illustrates the data type. Never build such a principal directly from request JSON unverified by the issuer and treat the request as authenticated.

In standard Spring Security releases, `DefaultOAuth2AuthenticatedPrincipal` provides constructors accepting **name**, **attributes**, and **authorities**, as well as constructors taking attributes/authorities and picking the name from common attributes like `sub`. Do not assume every custom introspector chooses the name identically; check the implementation you use.

## 4. `attributes`: reading the right schema and Java types

Attributes often contain fields of varying types:

| Introspection attribute | Possible JSON form | Possible Java type after introspector |
| --- | --- | --- |
| `sub` | `"user-42"` | `String` |
| `client_id` | `"orders-web"` | `String` |
| `scope` | `"orders.read orders.export"` | `String` or an adapter-normalized type |
| `aud` | `["orders-api"]` or string | `Collection<?>` or `String`, depending on implementation |
| `exp`, `iat`, `nbf` | NumericDate (JSON number, seconds) | `Instant` or numeric type, depending on introspector/converter |
| `permissions` | Custom string array | `Collection<?>` |
| `tenant_id` | Contract-defined string | `String` |
| Custom object | JSON object | Usually `Map<?, ?>` or an adapter-created DTO |

**A JSON number does not always mean a Java `Long`.** For JWT timestamps or introspection metadata, an adapter may convert NumericDate into `Instant`. Never write `(Long) principal.getAttribute("exp")` or `(List<String>) principal.getAttribute("aud")` without confirming your implementation's actual schema.

Type-safe attribute reading example:

~~~java
import java.time.Instant;
import java.util.Collection;
import java.util.Map;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

void inspect(OAuth2AuthenticatedPrincipal principal) {
    Map<String, Object> attrs = principal.getAttributes();

    Object rawSubject = attrs.get("sub");
    String subject = rawSubject instanceof String s ? s : null;

    Object rawClient = attrs.get("client_id");
    String clientId = rawClient instanceof String s ? s : null;

    Object rawExpiry = attrs.get("exp");
    Instant expiresAt = rawExpiry instanceof Instant i ? i : null;

    Object rawPermissions = attrs.get("permissions");
    if (rawPermissions instanceof Collection<?> permissions) {
        for (Object permission : permissions) {
            if (permission instanceof String p) {
                // Process p per issuer/API contract.
            }
        }
    }
}
~~~

This example code does **not** replace the introspector's expiration checks; it merely reads already-accepted values. If a library returns seconds instead of `Instant`, use a converter with **explicit units**. Never guess seconds vs. milliseconds by counting digits.

### Attributes are not always a user profile

`client_id` describes the OAuth 2.0 client; `scope` describes token permissions; `exp` relates to expiration; `sub` is the subject if present. These values serve distinct purposes.

Do not return the entire `principal.getAttributes()` map in an API response just for debugging: it may include PII, tenant data, or internal metadata not meant for disclosure. Pick the needed fields and project them into an API-contract DTO.

## 5. `name`: `getName` is not necessarily a username

In Spring Security, `Authentication.getName()` is typically a convenient identifier for the principal. With opaque tokens:

~~~text
BearerTokenAuthentication
          |
          +-- principal: OAuth2AuthenticatedPrincipal
          |      |
          |      +-- getName()
          |      +-- getAttributes()
          |      +-- getAuthorities()
          |
          +-- getName() delegates to the corresponding principal
~~~

A `DefaultOAuth2AuthenticatedPrincipal` created from an introspection response may use `sub` as its name. However:

- `sub` may be **absent** in introspection responses for certain token types.
- `username` is merely a display/login name that can change or lack uniqueness.
- `client_id` identifies the client, not automatically an end-user subject.
- A custom introspector may pick another name per contract.
- Across multiple issuers, the same `sub` can refer to two completely different entities.

Deliberate name-selection example:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;

var principal = new DefaultOAuth2AuthenticatedPrincipal(
    "internal-user-841",
    Map.of(
        "iss", "https://auth.example.com/realms/shop",
        "sub", "external-user-42",
        "username", "alice"
    ),
    List.of()
);

String name = principal.getName();          // internal-user-841
String subject = principal.getAttribute("sub"); // external-user-42
~~~

In this example, `getName()` and `sub` differ intentionally. They do not contradict each other: the name is chosen by the principal adapter, whereas `sub` is the original claim.

### Stable identification principle

When checking ownership, tenants, or audits, rely on **issuer-verified identity** mapped to an internal ID. For tokens carrying `iss` and `sub`, the `(iss, sub)` pair can serve as input to identity mapping, provided that issuer is truly the introspection-trusted source. Never treat the raw `getName()` string as standalone proof sufficient to access any tenant's data.

For Client Credentials tokens, when the issuer supplies only `client_id` without a user `sub`, enforce a dedicated **machine-principal policy**: which client may call which API, which resource scope, and which tenant. Never turn a client ID into the "owner" of human user records.

## 6. `authorities`: from introspection `scope` to `SCOPE_...`

In standard opaque-token Resource Server configurations, Spring Security's built-in introspector maps scopes into `GrantedAuthority` instances prefixed with **`SCOPE_`**.

Introspection response:

~~~json
{
  "active": true,
  "sub": "user-42",
  "scope": "orders.read orders.export"
}
~~~

Authorities typically become:

~~~text
SCOPE_orders.read
SCOPE_orders.export
~~~

Thus, HTTP authorization can use:

~~~java
.requestMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

Note:

1. In OAuth 2.0, `scope` is usually a **space-delimited string of scopes**, not a JSON array by default.
2. The `SCOPE_` prefix is Spring Security's authority naming convention. Requiring `SCOPE_orders.read` differs from `orders.read`.
3. If a custom introspector builds a principal without creating authorities, Spring Security will not automatically re-parse `scope` in every setup. Mapping belongs in your chosen adapter/converter.
4. Custom `permissions`/`roles` claims are **not automatically mapped** to `ROLE_ADMIN` or `PERMISSION_orders.export`.
5. Having `SCOPE_orders.read` does not mean permission to view **every individual order**; check ownership, tenant, or sharing in the service layer.

### Authorities are exact names, not decorative labels

These authorities are all distinct:

~~~text
SCOPE_orders.read
PERMISSION_orders.read
ROLE_ORDER_READER
orders.read
~~~

`hasAuthority("SCOPE_orders.read")` matches only that exact authority string. In standard configurations, `hasRole("ADMIN")` checks `ROLE_ADMIN`; `hasRole` does not match arbitrary scopes containing the word `admin`.

When designing mappings, clearly separate which namespace holds **OAuth scopes**, which holds **internal roles**, and which holds **Resource Server permissions**. Never grant administrative authorities casually just because a claim happens to look similar.

## 7. Distinguishing principals in JWT vs. opaque tokens

Two Resource Server configurations can accept the same `Authorization: Bearer ...` HTTP header yet produce different principals:

| Property | JWT Resource Server | Opaque Token Resource Server |
| --- | --- | --- |
| Verification component | `JwtDecoder` | `OpaqueTokenIntrospector` |
| Typical Authentication result | `JwtAuthenticationToken` | `BearerTokenAuthentication` |
| Typical principal | `Jwt` | `OAuth2AuthenticatedPrincipal` |
| Accessing data | `jwt.getClaims()`, `getSubject()`, `getExpiresAt()` | `principal.getAttributes()`, `getAttribute("sub")` |
| Principal name | Usually `sub` or custom converter | Per `OAuth2AuthenticatedPrincipal.getName()` |
| Authorities | Usually via `JwtGrantedAuthoritiesConverter` | From introspector/custom mapping |
| Call issuer on every request? | Usually no once matching keys are cached | Usually makes an introspection request unless cached |

**Never cast `(Jwt) authentication.getPrincipal()` in an opaque Resource Server.** A controller written specifically for JWTs will fail or receive the wrong principal type after switching to opaque tokens.

Example with Spring Security Servlet:

~~~java
import java.util.Collection;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;

void inspectAuthentication(Authentication authentication) {
    if (authentication instanceof BearerTokenAuthentication bearer) {
        Object principal = bearer.getPrincipal();
        String name = bearer.getName();
        Collection<? extends GrantedAuthority> authorities =
            bearer.getAuthorities();

        // bearer.getTokenAttributes() provides attributes.
        // bearer.getToken() holds the access token: never log tokenValue.
    }
}
~~~

When an application supports multiple token types, the domain layer can normalize identity into an abstraction such as `AuthenticatedActor(userId, tenantId, clientId, scopes)` **after authentication succeeds**, avoiding tight coupling of controllers/services to JWT vs. opaque types.

## 8. Configuring a Spring Boot Servlet Resource Server for opaque tokens

Common Maven dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

In `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: REPLACE_WITH_SECURE_RUNTIME_SECRET
~~~

This is an illustrative configuration. In practice, load the secret from a secret manager, environment variable, or controlled secret mechanism—**never commit real client secrets to source control**. Both the endpoint and credentials must belong to a trusted configured Authorization Server.

Example Java configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersResourceServerSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
~~~

In this configuration, built-in introspection builds the principal and authorities per your library version. Before trusting a token, the API must ensure **the right issuer/introspection endpoint, right audience/resource, validity timestamps, and token purpose** per contract. `active: true` alone does not guarantee a token was meant for the Orders API.

`csrf(...disable())` fits **stateless Bearer-token APIs** that do not accept browser-submitted cookies as credentials. If the application uses sessions/cookies, evaluate CSRF protection separately.

**`permitAll()` does not automatically turn off the Bearer filter.** If a client sends an invalid Bearer token to `/health`, the filter can still try to authenticate it and reject the request before reaching the `permitAll` rule. That is a behavior of token processing in the security chain, not a property of the principal.

## 9. Reading the principal in Controllers and Services

With an opaque-token Resource Server, you can inject `OAuth2AuthenticatedPrincipal` via `@AuthenticationPrincipal`:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {

    @GetMapping("/api/me")
    Map<String, String> me(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

        Map<String, String> result = new LinkedHashMap<>();
        result.put("name", principal.getName());

        Object rawSubject = principal.getAttribute("sub");
        if (rawSubject instanceof String subject) {
            result.put("subject", subject);
        }

        Object rawClient = principal.getAttribute("client_id");
        if (rawClient instanceof String clientId) {
            result.put("clientId", clientId);
        }

        return result;
    }
}
~~~

This example returns only a few illustrative fields, **not** the entire attributes map. If an API requires a value to be non-null, validate it explicitly and define clear error semantics rather than assuming introspection always supplies `sub` or `client_id`.

An option less coupled to a specific principal type:

~~~java
import java.util.List;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class AuthoritiesController {

    @GetMapping("/api/my-authorities")
    List<String> authorities(Authentication authentication) {
        return authentication.getAuthorities().stream()
            .map(a -> a.getAuthority())
            .toList();
    }
}
~~~

This endpoint only illustrates reading authorities. In production, consider carefully whether exposing the full list of authorities to clients is appropriate, especially internal permissions or sensitive authorization structures.

### Authorization must still check every record

Suppose a valid token carries `SCOPE_orders.read`, the caller belongs to tenant `t-7`, and order 123 belongs to tenant `t-8`. `hasAuthority("SCOPE_orders.read")` does not block cross-tenant access by itself. The service still must enforce:

~~~text
Introspected and verified Principal
          |
          v
Map issuer/subject or client identity
          |
          v
Check functional permission via authorities
          |
          v
Check tenant membership, owner/share/relationship
          |
          v
Query data scoped to the right tenant
~~~

Never rely on `principal.getName()` or a request-supplied `tenant_id` as the sole proof to read a resource.

## 10. Customizing authorities with `OpaqueTokenIntrospector`

Suppose the Authorization Server returns:

~~~json
{
  "active": true,
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "permissions": ["orders:export", "orders:approve"]
}
~~~

You want to keep `SCOPE_orders.read` and add `PERMISSION_orders.export` per the API contract. You can **decorate** a configured introspector that verifies the token, and construct a new principal carrying the added authorities.

Example:

~~~java
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OAuth2IntrospectionException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class OrdersOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    public OrdersOpaqueTokenIntrospector(OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        // Must succeed against trusted introspection source before mapping.
        OAuth2AuthenticatedPrincipal verified = delegate.introspect(token);

        Map<String, Object> attrs =
            new LinkedHashMap<>(verified.getAttributes());

        if (!isExpectedAudience(attrs.get("aud"))) {
            throw new OAuth2IntrospectionException(
                "Token is not intended for Orders API");
        }

        Set<GrantedAuthority> authorities = new LinkedHashSet<>();
        authorities.addAll(verified.getAuthorities());

        Object raw = attrs.get("permissions");
        if (raw instanceof Collection<?> permissions) {
            for (Object permission : permissions) {
                if ("orders:export".equals(permission)) {
                    authorities.add(new SimpleGrantedAuthority(
                        "PERMISSION_orders.export"));
                }
                if ("orders:approve".equals(permission)) {
                    authorities.add(new SimpleGrantedAuthority(
                        "PERMISSION_orders.approve"));
                }
            }
        }

        return new DefaultOAuth2AuthenticatedPrincipal(
            verified.getName(), attrs, authorities);
    }

    private boolean isExpectedAudience(Object aud) {
        if (aud instanceof String name) {
            return "orders-api".equals(name);
        }
        if (aud instanceof Collection<?> audiences) {
            return audiences.contains("orders-api");
        }
        return false;
    }
}
~~~

**This code illustrates one policy**: the API requires introspection to include `aud` targeting `orders-api`. If the issuer omits `aud`, the code **fails closed**. Real systems must design the introspection contract and enforce audience/issuer/client authorization according to what the issuer provides, rather than accepting any `active: true` response.

Also, `verified.getAuthorities()` in the example must come from an introspector **that has already verified the token**. Adding permissions is allowed only from trusted claims and an **allowlist of permissions understood by the API**. Never take arbitrary user-controllable strings to construct `ROLE_ADMIN`.

### Wiring a custom introspector into the Resource Server

An illustrative configuration for versions that still provide `NimbusOpaqueTokenIntrospector`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Bean
OpaqueTokenIntrospector ordersIntrospector() {
    OpaqueTokenIntrospector base = new NimbusOpaqueTokenIntrospector(
        "https://auth.example.com/oauth2/introspect",
        "orders-resource-server",
        "INJECT_SECURE_SECRET_AT_RUNTIME"
    );
    return new OrdersOpaqueTokenIntrospector(base);
}
~~~

Newer Spring Security releases offer different introspector APIs/builders (such as the Spring-named implementations), and some older classes have been or will be deprecated. **Pick the API actually available in your project's dependency version.** This snippet only shows the **delegate → policy-aware decorator** structure; real secrets must be injected from a secret store/runtime, never hardcoded like the example.

In `SecurityFilterChain`, you can attach the introspector via the DSL:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(opaque ->
    opaque.introspector(ordersIntrospector)
))
~~~

Here `ordersIntrospector` is an object/bean properly constructed and passed to the chain (not a variable that appears out of thin air). If the application already auto-wires an `OpaqueTokenIntrospector` bean, avoid defining duplicate configurations without knowing which bean is actually used.

### Why preserve attributes while constructing a new principal?

In the example, the code copies the attribute map and constructs a new `DefaultOAuth2AuthenticatedPrincipal`:

~~~text
verified principal from delegate
  getName()        -> preserved, unless policy changes the name
  getAttributes()  -> copied into a map for the new principal
  getAuthorities() -> preserved + allowlisted permissions added
~~~

This is much cleaner than attempting to mutate the collections returned by `getAuthorities()` or `getAttributes()` in place. Never assume implementation collections are mutable, nor let post-authentication components quietly alter authorities.

### When should a token be rejected instead of ignoring a claim?

If the profile states `permissions` must be a string array, yet introspection returns:

~~~json
{
  "active": true,
  "permissions": {"admin": true}
}
~~~

a strict policy can **reject the token** for violating the schema rather than silently ignoring `permissions`. This behavior must be defined by the API: missing optional permissions may yield empty authorities, while a mistyped mandatory claim may constitute an authentication error. Never call `toString()` on an arbitrary object to mint an authority.

## 11. Customizing `name`: username, subject, and client identity

Suppose introspection returns:

~~~json
{
  "active": true,
  "sub": "subject-42",
  "username": "alice",
  "client_id": "orders-web"
}
~~~

If the application wants `getName()` to return `alice` for display:

~~~java
OAuth2AuthenticatedPrincipal verified = delegate.introspect(token);

Object username = verified.getAttribute("username");
String displayName = username instanceof String s
    ? s
    : verified.getName();

OAuth2AuthenticatedPrincipal renamed =
    new DefaultOAuth2AuthenticatedPrincipal(
        displayName,
        verified.getAttributes(),
        verified.getAuthorities()
    );
~~~

This is a **display-name adjustment**, not a permission grant or change of the token's subject. Never use a display username as an ownership key or primary identity in multi-tenant systems.

In many systems, it is better to **keep `getName()` as a stable identifier** and put `username`/`preferred_username` into UI DTOs. If you must change `name` for legacy compatibility, ensure all code reading `getName()` understands its updated meaning.

### When `sub` is absent

For some machine-to-machine access tokens, introspection may return `client_id` without a user subject. Clarify:

- This is a **client** principal, not an inferred human user.
- Which Client IDs are trusted, under which issuer.
- Which resources that client may access, in which tenant.
- Whether audiences/scopes and client authorization match the contract.

Never default `getName() == client_id` unless the introspector sets it intentionally, and never grant a client a user's privileges just because two strings happen to match.

## 12. Unit testing `getName`, `attributes`, and `authorities`

You can test the principal with JUnit 5 without an Authorization Server:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

class PrincipalUnitTest {

    @Test
    void exposesAttributesNameAndAuthoritiesSeparately() {
        OAuth2AuthenticatedPrincipal principal =
            new DefaultOAuth2AuthenticatedPrincipal(
                "local-user-7",
                Map.of(
                    "sub", "external-sub-42",
                    "client_id", "orders-web",
                    "scope", "orders.read"
                ),
                List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
            );

        assertEquals("local-user-7", principal.getName());
        assertEquals("external-sub-42", principal.getAttribute("sub"));
        assertEquals("orders-web", principal.getAttribute("client_id"));
        assertTrue(principal.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .anyMatch("SCOPE_orders.read"::equals));
    }
}
~~~

This test only verifies **the contract of the manually constructed object**. It does not prove the introspection endpoint works or that `active: false` is rejected.

### Testing a custom introspector with a fake delegate

You can build a fake delegate returning a principal only for a test token string, then call the decorator:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

OpaqueTokenIntrospector fake = token -> {
    if (!"test-active-token".equals(token)) {
        throw new IllegalArgumentException("Unexpected test token");
    }
    return new DefaultOAuth2AuthenticatedPrincipal(
        "user-42",
        Map.of(
            "sub", "user-42",
            "aud", List.of("orders-api"),
            "permissions", List.of("orders:export")
        ),
        List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
    );
};

OpaqueTokenIntrospector decorated =
    new OrdersOpaqueTokenIntrospector(fake);

var principal = decorated.introspect("test-active-token");
// principal.getAuthorities() contains SCOPE_orders.read and
// PERMISSION_orders.export per the example converter.
~~~

This snippet only tests the **decorator's mapping**. A fake delegate does not represent network/TLS checks or real tokens. For integration testing, use an introspection test server/HTTP stub and a real security chain, verifying active responses, audience, timeouts, and errors.

## 13. HTTP integration tests and Spring Security Test `opaqueToken()`

Spring Security Test provides request post-processors for various authentication styles. With MockMvc, the `opaqueToken()` helper lets you attach a simulated principal to a request to test authorization:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Assuming MockMvc and an endpoint requiring SCOPE_orders.read.
mockMvc.perform(get("/api/orders")
        .with(opaqueToken()
            .authorities(new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

Tests like this verify **authorization given an existing `Authentication`**, yet **typically do not call a real introspection endpoint** and do not prove your production `OpaqueTokenIntrospector` maps authorities properly.

To test the entire Bearer flow:

1. Use a real security chain with `oauth2ResourceServer(...opaqueToken(...))`.
2. Send HTTP requests with the `Authorization: Bearer ...` header.
3. Replace the introspection network call with a stub server or mock `OpaqueTokenIntrospector` at the Spring context level.
4. Return a principal with matching attributes/authorities, or throw the matching error to simulate an inactive token.
5. Assert 401 for invalid tokens, 403 when permissions are lacking, and the expected response when authorized.
6. In fuller integration tests, confirm the client calls the introspection endpoint with properly configured TLS, authentication, and timeouts.

### Scenario matrix

| Scenario | Expected outcome |
| --- | --- |
| No token sent to an API requiring authentication | Usually 401 |
| Token present in request yet introspection returns `active: false` | No trusted principal created, usually 401 |
| Active token with `scope: orders.read`, mapped properly | Has authority `SCOPE_orders.read` |
| Active token missing endpoint's required scope | Authentication may succeed, authorization usually 403 |
| Active token yet `aud` targets another API | Rejected by Resource Server's audience policy |
| Introspection disconnects/times out | Fail closed, no access granted; HTTP code depends on error handling |
| Response lacks `sub` | Name/identity handled per contract; do not assume a known user |
| Introspection has mistyped `permissions` | Handled per schema policy; never mint arbitrary authorities |
| User has `SCOPE_orders.read` but does not own the order | Denied by object-level authorization |

## 14. Common mistakes and right understanding

### 14.1. Casting the principal to `Jwt`

~~~java
// Wrong if the endpoint's Authentication is BearerTokenAuthentication.
Jwt jwt = (Jwt) authentication.getPrincipal();
~~~

With opaque tokens, the principal is typically `OAuth2AuthenticatedPrincipal`, not `Jwt`. If an application must handle both token types, normalize the actor with a controlled adapter instead of casting in every controller.

### 14.2. Assuming `getName` is always `sub`

`getName()` is chosen by the principal implementation. It may be derived from `sub`, yet a custom introspector can use another name. If an immutable ID is required, check your identity contract and use verified issuer/subject or internal user IDs.

### 14.3. Confusing `attributes` with `GrantedAuthority`

Having `"scope": "orders.read"` in the map **is not automatically equivalent** to having `SCOPE_orders.read` in `getAuthorities()` if a custom introspector does not map scopes. Spring Security matches authorities present in `Authentication`; not every expression parses attributes automatically.

### 14.4. Turning `roles` straight into `ROLE_ADMIN`

If introspection returns a `roles` claim under a custom schema, do not blindly prefix every value with `ROLE_` without checking which issuer/resource that role belongs to. You could accidentally escalate privileges from a role meant for another system. Require an allowlist and audience/tenant-scoped semantics.

### 14.5. Treating `active=true` as complete authorization

`active: true` means the token is active per the introspection response. It **does not guarantee** the token belongs to the Orders API, holds the necessary scopes, or that the user owns the order. Audience, client, business permissions, and tenant boundaries must be designed separately per contract.

### 14.6. Mixing scopes with another client's permissions

In OAuth 2.0, an access token is issued for a specific set of permissions and target audience. If an issuer provides multiple role/permission sources, never merge them in a way that lets a read-only scoped client gain write or admin privileges beyond what was granted.

### 14.7. Logging `getToken().getTokenValue()`

`BearerTokenAuthentication.getToken()` contains the access token. **Never write `tokenValue` into logs, send it to metric labels, or return it via an API.** When debugging, rely on request IDs, verified issuer, introspection status, error categories, and loggable identity metadata.

### 14.8. Assuming introspection is always fast and available

With opaque tokens, the Resource Server usually makes a network call during authentication, so Authorization Server latency and availability are part of the design. Policy-controlled introspection caching can be considered, traded off against fast token revocation; never accept unverified requests just because the endpoint failed.

## 15. Relationship to OAuth 2.0 Client and OIDC

**`OpaqueTokenIntrospector`** is a **Resource Server** tool for checking access tokens. It differs from:

- **OAuth 2.0 Client:** an application requesting access tokens from the Authorization Server via an appropriate grant and optionally using refresh tokens.
- **OIDC Client:** verifies the **ID token** to establish user sign-in state for the client.
- **Resource Server:** receives **access tokens** sent to the API and authorizes resource access.

An **ID token** does not automatically become a valid API access token merely because it is a JWT containing `sub` or `email`. In an opaque-token flow, introspection data is valid only when the token matches the intended purpose/audience and API policy.

Specifically, `OAuth2AuthenticatedPrincipal` is **not the same** as an `OidcUser` in OAuth2 Login. Both belong to Spring Security's principal hierarchy, yet serve different contexts. In a Servlet opaque-token Resource Server, the standard authentication object is `BearerTokenAuthentication`.

## 16. Data model summary

~~~text
HTTP Authorization: Bearer <opaque-token>
                  |
                  v
       BearerTokenAuthenticationFilter
                  |
                  v
       OpaqueTokenAuthenticationProvider
                  |
                  v
            OpaqueTokenIntrospector
                  |
                  +----> Authorization Server introspection
                  |      active, sub, scope, client_id, aud, ...
                  v
       OAuth2AuthenticatedPrincipal
                  |
                  +-- attributes: Map<String, Object>
                  +-- name: String (implementation-defined)
                  +-- authorities: Collection<GrantedAuthority>
                  |
                  v
          BearerTokenAuthentication
                  |
                  v
              SecurityContext
                  |
                  v
       Endpoint / method authorization
                  |
                  v
      Tenant / ownership / business policy
~~~

| Question | API or concept to use |
| --- | --- |
| Which metadata did introspection provide? | `principal.getAttributes()` |
| Fetch subject specifically, if present? | `principal.getAttribute("sub")`, checking type and null |
| What does Spring Security call this principal? | `principal.getName()` |
| Which scopes/roles/permissions are used for authorization? | `principal.getAuthorities()` or `authentication.getAuthorities()` |
| What authentication type does an opaque Resource Server store? | Usually `BearerTokenAuthentication` |
| Who constructs the principal? | `OpaqueTokenIntrospector` after token verification |
| Need extra authorities from a custom claim? | Custom introspector/converter with explicit allowlist and schema |
| Who verifies the access token is still active? | Introspection endpoint with trusted introspector logic |
| Who issues/refreshes tokens? | Authorization Server via the client's OAuth 2.0 flow |
| Who checks resource owner and tenant? | Resource Server's business policy |

**Key takeaway:** In an opaque-token Resource Server, `OAuth2AuthenticatedPrincipal` is **the bridge between the introspection result and Spring Security's authorization engine**. `attributes` holds metadata, `name` identifies the principal per the implementation, and `authorities` is what Spring Security actually matches when checking permissions. To protect APIs properly, **verify tokens at a trusted source**, **map claims deliberately**, **never confuse identity with permission**, and continue enforcing permissions on every business resource.
