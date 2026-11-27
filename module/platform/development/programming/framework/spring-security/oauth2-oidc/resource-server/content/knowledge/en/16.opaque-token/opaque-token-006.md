# `OpaqueTokenAuthenticationProvider` and `BearerTokenAuthentication`

In a **Spring Security OAuth 2.0/OIDC Resource Server**, an API receiving a Bearer access token does not necessarily have to process it as a JWT. With an **opaque token**, the Resource Server typically verifies the token by contacting the **Authorization Server** via **OAuth 2.0 Token Introspection** (RFC 7662) rather than reading claims and verifying JWS signatures itself.

Two central classes in the **Servlet Resource Server** flow are:

- **`OpaqueTokenAuthenticationProvider`**: an **`AuthenticationProvider`** that uses an **`OpaqueTokenIntrospector`** to validate the access token and build the resulting `Authentication`.
- **`BearerTokenAuthentication`**: the **successful `Authentication`** type created by default by the provider after introspection accepts the token; it holds the **`OAuth2AuthenticatedPrincipal`**, the access token, and the **`GrantedAuthority`** collection.

There is also a similarly named **`BearerTokenAuthenticationToken`**. That is instead the **inbound authentication request**, created from the Bearer token string sent by the client. It does not yet prove the token is valid.

This distinction is critical: **passing a token into `AuthenticationManager` does not mean it is authenticated; only successful introspection producing a proper `Authentication` establishes an identity usable for authorization**. This lesson walks from the HTTP filter to the provider, introspection endpoint, object model, Spring Boot configuration, custom policies, testing, and safe operations.

## 1. What is an opaque token?

A Bearer access token is a credential the client sends to the API, typically via the header:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer mV6tR2nQp9xL8fA4
~~~

The token string above is purely a **hypothetical example**, not a real credential. **Bearer** means whoever holds the token can use it within its granted scope, so the token must be kept secret and sent over HTTPS.

An **opaque token** is a token that the Resource Server must not assume has a structure it can decode and verify itself. It may be a random string referencing state stored at the Authorization Server, or a structured value where the Resource Server is still designed to use introspection.

The Resource Server must ask a trusted source:

- Is the token **`active`**?
- Which subject (**`sub`**) does the token belong to?
- Which client (**`client_id`**) was the token issued to?
- Which **scopes** does the token carry?
- Is the token intended for this API's resource/audience?
- What expiration, issuer, tenant, or domain-specific policy metadata applies?

### 1.1. JWT Resource Server vs. opaque Resource Server

| Aspect | JWT/JWS | Opaque token/introspection |
|---|---|---|
| Common verification mechanism | **`JwtDecoder`**, signatures and validators | **`OpaqueTokenIntrospector`**, querying the Authorization Server |
| `AuthenticationProvider` | **`JwtAuthenticationProvider`** | **`OpaqueTokenAuthenticationProvider`** |
| Successful `Authentication` | **`JwtAuthenticationToken`** | **`BearerTokenAuthentication`** by default |
| Default principal | **`Jwt`** | **`OAuth2AuthenticatedPrincipal`** |
| Source of claims/attributes | Verified JWT | Trusted introspection response |
| Scope authorities | Usually **`SCOPE_*`** | Usually **`SCOPE_*`** |
| Revocation detection | Requires extra policy when verifying offline | AS can return **`active=false`** |
| Network dependency | Can use cached public keys | Usually calls introspection endpoint unless valid cached result exists |

The name **`opaqueToken()`** in Spring Security refers to the **introspection authentication strategy**. A token that looks like a JWT can still take this path if the application is configured to introspect rather than verify JWTs locally.

## 2. Distinguishing three similarly named classes

| Object | Role | Is the token authenticated yet? |
|---|---|---|
| **`BearerTokenAuthenticationToken`** | Authentication request created from the token string sent by the client | **Not yet** |
| **`OpaqueTokenAuthenticationProvider`** | Component that checks the token via `OpaqueTokenIntrospector` | Performs authentication |
| **`BearerTokenAuthentication`** | Default `Authentication` result after successful introspection | **Authenticated** per result and configured policy |

### 2.1. `BearerTokenAuthenticationToken` is the request object

When a Servlet request carrying a Bearer token is processed, **`BearerTokenAuthenticationFilter`** extracts the token and creates an authentication request object:

~~~java
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;

BearerTokenAuthenticationToken request =
    new BearerTokenAuthenticationToken("example-opaque-token");
~~~

On this class, **`getToken()`** returns the input raw **`String`** token. Calling the constructor does not send an introspection request and confers zero trust upon the token.

Never create an authority like **`ROLE_ADMIN`** from an unauthenticated string just because this class implements the `Authentication` interface.

### 2.2. `OpaqueTokenAuthenticationProvider` is the processor

**`OpaqueTokenAuthenticationProvider`** implements **`AuthenticationProvider`**. It receives the token request, delegates to **`OpaqueTokenIntrospector`** to verify the token, and builds the `Authentication` via **`OpaqueTokenAuthenticationConverter`**.

A simplified flow:

~~~text
BearerTokenAuthenticationToken(rawToken)
    -> OpaqueTokenAuthenticationProvider
    -> OpaqueTokenIntrospector.introspect(rawToken)
    -> OAuth2AuthenticatedPrincipal (only if token is valid)
    -> OpaqueTokenAuthenticationConverter
    -> default BearerTokenAuthentication
~~~

If introspection does not accept the token, the provider **never returns a successful `Authentication`** for that token.

### 2.3. `BearerTokenAuthentication` is the result

**`BearerTokenAuthentication`** is the result normally stored in `SecurityContext` after the token is authenticated. It holds:

- **`OAuth2AuthenticatedPrincipal`** as the default principal.
- **`OAuth2AccessToken`** as the authenticated token/credential.
- **`GrantedAuthority`** derived from trusted metadata/mappers.
- **Token attributes** from the introspection response.

The **`BearerTokenAuthentication`** class name does not guarantee that custom fields like **`aud`**, **`tenant_id`**, or **`permissions`** have been thoroughly checked for business rules. Those policies still must be designed explicitly.

## 3. Servlet processing flow from request to `SecurityContext`

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant F as BearerTokenAuthenticationFilter
    participant M as AuthenticationManager / ProviderManager
    participant P as OpaqueTokenAuthenticationProvider
    participant I as OpaqueTokenIntrospector
    participant AS as Authorization Server
    participant S as SecurityContext and Authorization

    C->>F: GET /api/orders/42 + Bearer token
    F->>F: Create BearerTokenAuthenticationToken
    F->>M: authenticate(request)
    M->>P: authenticate(BearerTokenAuthenticationToken)
    P->>I: introspect(raw token)
    I->>AS: POST /introspect over HTTPS with client authentication
    AS-->>I: active=true and token metadata
    I-->>P: OAuth2AuthenticatedPrincipal
    P-->>M: BearerTokenAuthentication
    M-->>F: Authentication succeeded
    F->>S: Store Authentication in SecurityContext
    S->>S: Check scopes, roles, and record-level permissions
    S-->>C: Response per authorization policy
~~~

The diagram illustrates the logical steps in Spring Security **Servlet**. Internal filter details, exception handling, and extra framework authorities can vary by version.

1. **`BearerTokenAuthenticationFilter`** extracts the token from the request per Bearer rules.
2. The filter creates **`BearerTokenAuthenticationToken`** and passes it to **`AuthenticationManager`**.
3. **`ProviderManager`** selects the matching provider; for an opaque-token Resource Server, that is **`OpaqueTokenAuthenticationProvider`**.
4. The provider calls **`OpaqueTokenIntrospector`**.
5. The introspector typically calls the Authorization Server over HTTPS.
6. If the token is valid, the introspector returns **`OAuth2AuthenticatedPrincipal`**.
7. The provider converts the result into **`BearerTokenAuthentication`** by default.
8. The filter stores the `Authentication` in **`SecurityContext`** for the request lifecycle.
9. HTTP/method/domain authorization evaluates authorities and permissions on the specific resource.

### 3.1. Why just having a token in the header is not enough

The **`Authorization: Bearer`** header may contain:

- A genuine, valid token with the right audience.
- A non-existent or revoked token.
- An expired token.
- A token intended for a different API.
- A random string fabricated by an attacker.
- A genuine JWT that is not allowed to be used with this Resource Server.

The filter receiving the token does not know which case applies. **The provider + introspector** are responsible for establishing the authentication result. Never skip this step or treat client-supplied claims as trustworthy.

## 4. API of `OpaqueTokenAuthenticationProvider`

The class resides in package:

~~~text
org.springframework.security.oauth2.server.resource.authentication
~~~

Core APIs:

| API | Function |
|---|---|
| **`OpaqueTokenAuthenticationProvider(OpaqueTokenIntrospector)`** | Creates the provider with an introspector |
| **`supports(Class<?> authentication)`** | Indicates whether the provider can handle an Authentication request type |
| **`authenticate(Authentication authentication)`** | Performs introspection, checks token, and creates Authentication |
| **`setAuthenticationConverter(OpaqueTokenAuthenticationConverter)`** | Customizes how Authentication is built after introspection |

### 4.1. `supports` does not mean the token is active

Example:

~~~java
OpaqueTokenAuthenticationProvider provider =
    new OpaqueTokenAuthenticationProvider(introspector);

boolean supported =
    provider.supports(BearerTokenAuthenticationToken.class);
~~~

**`supported`** only says the provider can process that request class, not that every token is permitted. Zero introspection is proven by calling `supports()`.

### 4.2. `authenticate` triggers verification

A contract description:

~~~text
authenticate(Authentication request):
    rawToken = extract from BearerTokenAuthenticationToken
    principal = introspector.introspect(rawToken)
    result = converter.convert(rawToken, principal)
    return result
~~~

This is **pseudocode**, not Spring Security source code. If the introspector fails, the provider reports an error via the authentication exception path and never returns a valid principal.

### 4.3. When is `setAuthenticationConverter` used?

**`OpaqueTokenAuthenticationConverter`** is an extension point for converting the token plus introspection-verified principal into an **`Authentication`** object. Contract:

~~~java
Authentication convert(
    String introspectedToken,
    OAuth2AuthenticatedPrincipal authenticatedPrincipal
);
~~~

An application can use a custom converter when it needs a custom `Authentication` type or specialized identity-mapping logic. However:

- The converter must use only the **introspection-authenticated principal**.
- It does not replace introspection.
- It must never upgrade every active token to `ROLE_ADMIN`.
- If returning a different `Authentication` type, controllers must not assume they can cast to **`BearerTokenAuthentication`**.

On supporting Spring Security versions, the provider allows:

~~~java
provider.setAuthenticationConverter(customAuthenticationConverter);
~~~

Here **`customAuthenticationConverter`** is an application object implementing the contract; the snippet merely shows the API extension point. With Spring Boot, it is usually cleaner to declare the appropriate converter/introspector in configuration rather than manually registering the provider.

## 5. `OpaqueTokenIntrospector` is the trust boundary

The interface resides in package:

~~~text
org.springframework.security.oauth2.server.resource.introspection
~~~

Abbreviated form:

~~~java
public interface OpaqueTokenIntrospector {
    OAuth2AuthenticatedPrincipal introspect(String token);
}
~~~

Meaning:

- Accepts an unverified **raw token**.
- Uses a trusted mechanism to verify it, typically calling the RFC 7662 introspection endpoint.
- Returns **`OAuth2AuthenticatedPrincipal`** when accepted.
- Throws an error if the token is invalid or cannot be introspected per contract.

Another implementation may validate tokens against a trusted internal data store/token registry, provided it upholds the same verification rules.

### 5.1. Common implementations

| Implementation | When to use? |
|---|---|
| **`SpringOpaqueTokenIntrospector`** | Default HTTP introspection client in many Spring Security setups |
| **`RestClientOpaqueTokenIntrospector`** | Uses `RestClient`; suitable when customizing HTTP client, timeouts, headers |
| **Custom `OpaqueTokenIntrospector`** | Add audience validation, domain permission mapping, caching, or custom token sources |
| **`OpaqueTokenAuthenticationConverter`** | Build a custom `Authentication` result from the introspected principal |

An example builder for supporting Spring Security releases:

~~~java
OpaqueTokenIntrospector trusted =
    SpringOpaqueTokenIntrospector
        .withIntrospectionUri("https://login.example.com/oauth2/introspect")
        .clientId("orders-resource-server")
        .clientSecret("example-secret-only")
        .build();
~~~

This is a placeholder; **never place real client secrets in source code**. This builder exists in corresponding Spring Security versions such as 6.5+; on older versions, use the constructors/APIs supported by that version.

## 6. RFC 7662: introspection request and response

The Authorization Server typically exposes a dedicated introspection endpoint, e.g.:

~~~text
https://login.example.com/oauth2/introspect
~~~

This is a trust endpoint **preconfigured by the Resource Server**, never taken from a value supplied by the token or client.

### 6.1. Illustrative HTTP request

~~~http
POST /oauth2/introspect HTTP/1.1
Host: login.example.com
Authorization: Basic <encoded-introspection-client-credentials>
Content-Type: application/x-www-form-urlencoded

token=<opaque-access-token>&token_type_hint=access_token
~~~

**`token`** is the primary parameter; **`token_type_hint`** is an optional hint under RFC 7662. Client authentication protects permission to invoke introspection. Always use HTTPS, verify certificates/hostnames, and protect the Resource Server's credentials.

### 6.2. Active token

Illustrative JSON response:

~~~json
{
  "active": true,
  "sub": "user-123",
  "scope": "orders.read orders.write",
  "client_id": "web-client",
  "token_type": "Bearer",
  "aud": ["orders-api"],
  "iss": "https://login.example.com/realms/shop",
  "exp": 1893456000,
  "tenant_id": "tenant-a"
}
~~~

Fields beyond **`active`** depend on the contract with the Authorization Server. Not every introspection endpoint is required to return **`aud`**, **`iss`**, **`sub`**, **`tenant_id`**, or full JWT-like data.

**`active=true`** indicates the Authorization Server considers the token active under its policy; the Resource Server must still enforce conditions on audience, scope, token type, tenant, or business rules if required by API policy.

### 6.3. Inactive token

~~~json
{
  "active": false
}
~~~

An inactive token must be rejected. A minimal inactive response does not explain why the token is invalid; it might be non-existent, expired, or revoked.

Do not fall back to assigning principals from stale metadata or trust a token just because the client sent **`sub`** along with the request.

### 6.4. Introspection does not automatically mean audience validation

One application might only need `active` + `scope` per its Authorization Server contract; another must check **`aud = orders-api`**. If the protected target requires strict audience enforcement, verify that the result contains complete data or rely on a trusted resource-binding mechanism at the AS.

If the introspection endpoint does not return **`aud`** while policy mandates audience checks, resolve the contract with the issuer. Never silently drop the check just to let tokens through.

## 7. What is the structure of `BearerTokenAuthentication`?

**`BearerTokenAuthentication`** is an `Authentication` implementation extending **`AbstractOAuth2TokenAuthenticationToken<OAuth2AccessToken>`**.

| Member | Value/meaning |
|---|---|
| **`getPrincipal()`** | By default, an **`OAuth2AuthenticatedPrincipal`** |
| **`getName()`** | Principal name, usually tied to **`sub`** if present |
| **`getAuthorities()`** | Set of **`GrantedAuthority`** |
| **`getTokenAttributes()`** | Map of token metadata from introspection |
| **`getToken()`** | A verified **`OAuth2AccessToken`**, not a raw `String` |
| **`getCredentials()`** | Credential attached to the `Authentication`; must be protected |
| **`isAuthenticated()`** | Indicates whether the `Authentication` was accepted |

A resulting instance can be visualized as:

~~~text
BearerTokenAuthentication
  authenticated: true
  principal: OAuth2AuthenticatedPrincipal
  name: user-123
  authorities:
    - SCOPE_orders.read
    - SCOPE_orders.write
  tokenAttributes:
    sub: user-123
    aud: [orders-api]
    scope: orders.read orders.write
    tenant_id: tenant-a
  token: OAuth2AccessToken
~~~

In modern Spring Security releases, the authorities set may also include framework authorities such as **`FACTOR_BEARER`**. This depends on version/configuration and **never replaces business scopes/roles**.

### 7.1. `getToken()` on the two different `Authentication` classes

Two easily confused signatures:

~~~text
BearerTokenAuthenticationToken.getToken()
    -> String raw token

BearerTokenAuthentication.getToken()
    -> OAuth2AccessToken
~~~

**`OAuth2AccessToken`** can hold the token value. Never write this object out to an HTTP response, never log credentials, and never store it in tracing/metric labels.

### 7.2. `getTokenAttributes()`

Introspection data is stored in a `Map`:

~~~java
import java.util.Map;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;

Map<String, Object> attributes = authentication.getTokenAttributes();
Object subject = attributes.get("sub");
Object tenant = attributes.get("tenant_id");
~~~

Value types can vary depending on how the introspector converts the response: `String`, `Collection`, `Instant`, or other types. Do not cast blindly unless the claim has a stable contract.

### 7.3. Principal and `getName()`

~~~java
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

OAuth2AuthenticatedPrincipal principal =
    (OAuth2AuthenticatedPrincipal) authentication.getPrincipal();

String subject = principal.getAttribute("sub");
String principalName = authentication.getName();
~~~

When **`sub`** is present, `name` usually reflects the subject. If `sub` is absent, how `name` is determined depends on the implementation. In multi-issuer systems, a safe user identifier is typically **`issuer + sub`**, not `sub` or email alone.

## 8. Accessing `Authentication` in a controller after introspection

In Spring MVC, a controller can accept `BearerTokenAuthentication` or the authenticated principal.

### 8.1. Injecting `BearerTokenAuthentication`

~~~java
import java.util.Map;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {

    @GetMapping("/api/me")
    Map<String, String> me(BearerTokenAuthentication authentication) {
        return Map.of("subject", authentication.getName());
    }
}
~~~

This example assumes `name` is non-null and the endpoint receives only requests authenticated under the opaque strategy. A real application may need to validate required claims and use a DTO.

### 8.2. `@AuthenticationPrincipal`

~~~java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class IdentityController {

    @GetMapping("/api/identity")
    Map<String, String> identity(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        String sub = principal.getAttribute("sub");
        return Map.of("subject", sub);
    }
}
~~~

This example likewise assumes the introspection response includes **`sub`**. If the issuer does not always emit `sub`, define appropriate null-handling/validation.

If using a **custom `OpaqueTokenAuthenticationConverter`** that returns another `Authentication` type, controllers should not hard-depend on `BearerTokenAuthentication`. When abstraction is needed, inject **`Authentication`** or a principal per the actual contract.

### 8.3. Never return all token attributes

An introspection response may contain `client_id`, `tenant_id`, permissions, token values, or sensitive metadata. Never blindly return **`authentication.getTokenAttributes()`** intact to clients just because authentication succeeded. Filter fields, check permissions, and avoid leaking internal data.

## 9. Configuring a Spring Boot opaque Resource Server

A common configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: replace-through-secret-manager
~~~

The `client-id`/`client-secret` values are illustrative; in real applications load them via environment variables or a secret manager. Never commit real secrets.

- **`opaquetoken`** is the Spring Boot property group.
- **`introspection-uri`** is the Authorization Server's trusted endpoint.
- **`client-id`/`client-secret`** are the Resource Server's credentials for calling introspection.
- You do not need JWT **`issuer-uri`/`jwk-set-uri`** to introspect under this strategy.
- If the API needs audience/issuer validation on introspection results, configure the appropriate policy; do not assume JWT validators are reused automatically.

### 9.1. `SecurityFilterChain`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OpaqueApiSecurityConfiguration {

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
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

In this chain, requests are authenticated via introspection before authority-dependent rules run. **`permitAll`** is an authorization decision for public endpoints, not a blanket bypass of every filter.

When defining a custom `SecurityFilterChain`, check **`securityMatcher`** scope, chain ordering, and any routes not matched by any chain. **`anyRequest`** inside a narrowed chain does not cover every endpoint in the application.

### 9.2. Dependencies

| Spring Boot | Typical Resource Server starter |
|---|---|
| **3.x** | **`spring-boot-starter-oauth2-resource-server`** |
| **4.x** | **`spring-boot-starter-security-oauth2-resource-server`** |

Opaque introspection requires the Resource Server module and its related dependencies. **`spring-security-oauth2-jose`** is not mandatory solely for opaque token introspection, unlike JWT signature verification. Use Spring Boot dependency management to avoid mismatched major Spring Security versions.

## 10. Mapping scopes to `GrantedAuthority`

An introspection response commonly includes:

~~~json
{
  "active": true,
  "scope": "orders.read orders.write",
  "sub": "user-123"
}
~~~

In the default configuration, Spring Security turns scopes into authorities prefixed with **`SCOPE_`**:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Thus you can protect an endpoint with:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

**Scope** is not the same as **role**:

- **`hasAuthority("SCOPE_orders.read")`** checks the scope authority.
- **`hasRole("ADMIN")`** checks **`ROLE_ADMIN`** by default.
- A **`roles: ["ADMIN"]`** claim in introspection metadata does not automatically create `ROLE_ADMIN`.
- OIDC scopes such as **`openid`**, **`profile`**, and **`email`** are not business permissions by themselves.

Beyond scopes, the Resource Server still needs to check **tenant**, ownership, and domain conditions for specific orders.

### 10.1. Authorities in newer Spring Security releases

Some recent Spring Security releases add framework authorities related to authentication factors, such as **`FACTOR_BEARER`**, on successful introspection. When checking permissions, do not assert that `Authentication` has *only* `SCOPE_orders.read`; other system-level authorities may be present.

**`FACTOR_BEARER` is not a business read/write permission**, nor does it turn an active token into permission across all APIs.

## 11. Customizing the introspector to check audience

An application may require the introspection result to include audience **`orders-api`**. When the issuer supplies that claim, you can **wrap the trusted introspector** to add validation:

~~~java
import java.util.Collection;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringOpaqueTokenIntrospector;

@Configuration
class IntrospectionConfiguration {

    @Bean
    OpaqueTokenIntrospector introspector() {
        OpaqueTokenIntrospector trusted = SpringOpaqueTokenIntrospector
            .withIntrospectionUri(
                "https://login.example.com/oauth2/introspect")
            .clientId("orders-resource-server")
            .clientSecret("replace-through-secret-manager")
            .build();

        return token -> {
            OAuth2AuthenticatedPrincipal principal =
                trusted.introspect(token);

            Object aud = principal.getAttribute("aud");
            boolean allowed = "orders-api".equals(aud)
                || (aud instanceof Collection<?> values
                    && values.contains("orders-api"));

            if (!allowed) {
                throw new BadOpaqueTokenException(
                    "Introspected token not intended for orders-api");
            }
            return principal;
        };
    }
}
~~~

This example uses placeholder client credentials; **never hardcode real secrets**. In practice, inject credentials via Spring configuration/secret manager.

Key points:

1. **`trusted.introspect(token)`** must run first.
2. **`aud`** is validated on the principal already accepted by introspection.
3. If `aud` is mandatory yet missing, the example rejects it per fail-closed policy.
4. If the AS does not return `aud`, design another trusted resource-binding mechanism rather than relaxing the condition.
5. A custom **`@Bean OpaqueTokenIntrospector`** typically replaces Boot's auto-configuration; do not assume properties automatically apply all policies to the custom bean.

You can pick **`RestClientOpaqueTokenIntrospector`** instead of `SpringOpaqueTokenIntrospector` when you need HTTP client/timeout control matching your version's API.

## 12. Customizing permissions while preserving default scopes

If the Authorization Server returns:

~~~json
{
  "active": true,
  "sub": "user-123",
  "scope": "orders.read",
  "permissions": ["orders.approve"]
}
~~~

The application may need **`PERM_orders.approve`** in addition to **`SCOPE_orders.read`**. An introspector decorator adds this policy without dropping base verification:

~~~java
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

class PermissionsIntrospector implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    PermissionsIntrospector(OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal = delegate.introspect(token);
        Set<GrantedAuthority> granted =
            new LinkedHashSet<>(principal.getAuthorities());

        Object raw = principal.getAttribute("permissions");
        if (raw instanceof Collection<?> values) {
            for (Object value : values) {
                // Illustrates allowlisting a business permission.
                if ("orders.approve".equals(value)) {
                    granted.add(new SimpleGrantedAuthority(
                        "PERM_orders.approve"));
                }
            }
        }

        return new DefaultOAuth2AuthenticatedPrincipal(
            principal.getName(), principal.getAttributes(), granted);
    }
}
~~~

**Never** wrap this decorator around a fake delegate that returns a principal for every token. In production, the delegate must perform trusted introspection.

Nor should you map arbitrary permissions from JSON directly into `ROLE_ADMIN`. Require a clear contract: which issuer grants permissions, which resource/tenant they apply to, and whether roles are time-bounded.

## 13. When do you need a custom `OpaqueTokenAuthenticationConverter`?

**`OpaqueTokenAuthenticationConverter`** runs after introspection and converts **raw token + `OAuth2AuthenticatedPrincipal`** into an `Authentication`.

It fits when you need to:

- Produce a custom `Authentication` or domain principal type.
- Normalize principal metadata to an application contract.
- Enrich authorities from another trusted source.
- Extend the authentication outcome using Spring Security's supported hook.

If you only need extra authorities derived from introspection attributes, an **`OpaqueTokenIntrospector`** decorator is usually simpler.

A custom converter **must never**:

- Return an authenticated principal for an un-introspected raw token.
- Grant `ROLE_ADMIN` to every active token.
- Take permission data from unverified request bodies/headers.
- Leak raw tokens into logs/responses.
- Bypass the API's token type/issuer/audience contract.

The default converter normally returns **`BearerTokenAuthentication`**. A custom converter may return a different `Authentication`; in that case, write controllers against the interface or matching principal type.

## 14. Unit testing `OpaqueTokenAuthenticationProvider`

You can test the provider without calling a real Authorization Server by using a **test-double** introspector:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.OpaqueTokenAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

class OpaqueTokenProviderTest {

    @Test
    void successfulIntrospectionProducesAuthenticatedPrincipal() {
        OpaqueTokenIntrospector introspector = token -> {
            if (!"test-active-token".equals(token)) {
                throw new BadOpaqueTokenException("Token inactive");
            }
            return new DefaultOAuth2AuthenticatedPrincipal(
                "user-123",
                Map.of("sub", "user-123",
                       "scope", List.of("orders.read")),
                List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
            );
        };

        OpaqueTokenAuthenticationProvider provider =
            new OpaqueTokenAuthenticationProvider(introspector);

        Authentication result = provider.authenticate(
            new BearerTokenAuthenticationToken("test-active-token")
        );

        assertInstanceOf(BearerTokenAuthentication.class, result);
        assertTrue(result.isAuthenticated());
        assertEquals("user-123", result.getName());
        assertTrue(result.getAuthorities().stream().anyMatch(
            a -> "SCOPE_orders.read".equals(a.getAuthority())));
    }
}
~~~

What this test proves:

- The provider accepts **`BearerTokenAuthenticationToken`**.
- The provider invokes the introspector.
- On successful introspection, the default result is **`BearerTokenAuthentication`**.
- Authorities can include the expected scope.

It **does not prove TLS, client credentials, or a live production endpoint**. Use test doubles strictly in tests—never as production introspectors.

### 14.1. Inactive tokens must be rejected

Test with a test-double introspector throwing **`BadOpaqueTokenException`**:

~~~java
OpaqueTokenIntrospector introspector = token -> {
    throw new BadOpaqueTokenException("Token inactive");
};
~~~

When the provider processes a `BearerTokenAuthenticationToken`, it must not produce a successful `Authentication`. In real tests, verify the exception type/HTTP response matching your version and exception-handling setup.

### 14.2. Add real HTTP introspection tests with a stub server

Use a test-environment HTTP stub server for the introspection endpoint to verify:

- POST method and request parameters are correct.
- Introspection client authentication is sent properly.
- `active=true` maps to principal/authorities.
- `active=false` is rejected.
- `401`/`403` from the introspection endpoint does not create a principal.
- Timeouts, `5xx`, and TLS errors do not make the Resource Server fail open.
- Responses missing `aud`, `scope`, or mandatory claims are handled per policy.

## 15. `MockMvc` and `opaqueToken()` do not test the provider by themselves

Spring Security Test includes the **`opaqueToken()` request post-processor** to test authorization without calling an introspection endpoint.

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

// Inside a test class with MockMvc and an appropriate endpoint configured.
@Test
void readScopeAllowsOrderEndpoint() throws Exception {
    mockMvc.perform(get("/api/orders/42")
            .with(opaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isOk());
}
~~~

This test is good for checking **`SecurityFilterChain` and authorities**, yet usually **bypasses `OpaqueTokenAuthenticationProvider` and real HTTP introspection** because it injects a simulated `Authentication`.

A `200` outcome also depends on the controller and test data. If the handler returns `404` or hits another domain policy, provide matching fixtures.

### 15.1. Suggested test matrix

| Case | Authentication | Authorization | Typical outcome |
|---|---|---|---|
| No token, private endpoint | None | Insufficient | 401 |
| `active=false` token | Failed | No access granted | 401 |
| `active=true`, `orders.read` scope | Succeeded | Read permission satisfied | Controller invoked |
| `active=true`, missing `orders.read` | Succeeded | Missing scope | 403 |
| `active=true`, `aud` for another API | Rejected by custom audience policy | Does not reach business handler | 401 per flow |
| `active=true`, valid scope, wrong tenant | Succeeded | Rejected by domain policy | 403 or 404 |
| Introspection times out | Cannot verify reliably | No access granted | Error per exception handling; never fail-open |
| Introspection wrong `client-secret` | Rejected upstream | No access granted | Must fix credentials/config |
| Revoked token | AS returns `active=false` | Rejected | 401 |

These HTTP codes are typical, not a guarantee across every Spring Security setup. Infrastructure errors may yield 5xx or be mapped differently.

## 16. Introspection and operational security

### 16.1. The introspection URL must come from trusted configuration

Never let the request or token decide the introspection endpoint. Allowing the token to pick a URL opens **SSRF**, sending raw tokens/credentials to attacker-controlled hosts or probing internal addresses.

The trusted source must come from issuer/Authorization Server configuration, or an explicitly governed multi-tenant allowlist/routing table.

### 16.2. Protecting tokens and client credentials

- Use HTTPS and verify certificate chains/hostnames.
- Store `client-secret` in a secret manager or secure configuration; rotate as needed.
- Never log `Authorization: Bearer`, `Authorization: Basic`, raw tokens, or sensitive introspection responses.
- Never put tokens in URL query strings or tracing labels.
- Configure timeouts, connection pooling, outbound traffic limits, and response size limits.
- Separate DNS/TLS/upstream outages from inactive tokens.
- Never enable trust-all certificates to temporarily paper over environment issues.

### 16.3. Fail closed when the AS fails

A request with a token that cannot be introspected **must not be treated as authenticated just because the token looks well-formed**. When the Authorization Server is unavailable, the Resource Server can return an error, perform bounded retries, or use a policy-approved valid cache, yet must never fabricate a successful principal.

## 17. Performance, caching, and revocation

Because introspection typically requires a network call, it introduces trade-offs:

| Factor | Consequence |
|---|---|
| **Latency** | Adds round-trip time before running controller logic |
| **Throughput** | Introspection volume scales with API request volume |
| **Availability** | Resource Server depends on AS/introspection service availability |
| **Revocation** | AS can return `active=false` promptly after revocation |
| **Caching** | Cuts latency yet can extend how long a revoked token remains accepted |

If caching **`active=true`** results, establish clear policies for TTL, token expiration, and acceptable revocation lag. Never cache indefinitely and never use expired cached active results.

Operational practices:

1. Track latency, error rates, timeouts, and introspection call counts.
2. Tune HTTP client pooling and sensible timeouts.
3. Bound cache TTL by remaining `exp` and revocation requirements.
4. Apply rate limiting to mitigate floods of random tokens.
5. Never treat upstream timeouts as `active=true`.
6. Test token revocation with cases flipping `active` between requests.

Do not assume Spring Security ships a default cache fitting every policy; verify against your actual introspector and configuration.

## 18. JWTs can also go through `opaqueToken()`

An application can receive **JWT-formatted** access tokens yet choose to verify them via **introspection** instead of `JwtDecoder`—for example, to query the AS per request for revocation status.

In that case:

~~~text
Bearer JWT (dot-separated string)
  -> BearerTokenAuthenticationFilter
  -> OpaqueTokenAuthenticationProvider
  -> OpaqueTokenIntrospector
  -> default BearerTokenAuthentication
~~~

What determines the `Authentication` type is not merely the raw token's appearance, but the **configured authentication mechanism**.

If the introspection response returns only `active` without claims the API needs, never parse the unverified JWT yourself and grant permissions from those claims. Either establish an explicit supplementary trust/validation strategy or require the AS to return the needed metadata.

## 19. Servlet vs. Reactive WebFlux

This lesson focuses on Spring Security **Servlet/MVC**:

~~~text
SecurityFilterChain
BearerTokenAuthenticationFilter
AuthenticationManager / ProviderManager
OpaqueTokenAuthenticationProvider
OpaqueTokenIntrospector
BearerTokenAuthentication
~~~

For **WebFlux**, Spring Security uses the corresponding reactive types:

- **`SecurityWebFilterChain`**.
- **`ReactiveOpaqueTokenIntrospector`**.
- **`OpaqueTokenReactiveAuthenticationManager`** and related reactive components.

Never copy **`HttpSecurity`** configuration verbatim or run blocking HTTP introspection on the Reactor event loop without addressing the execution model. For WebFlux, use the official reactive APIs for your version.

## 20. Common mistakes

### 20.1. Treating `BearerTokenAuthenticationToken` as already authenticated

It is only the authentication request object. Never use that raw token to grant permissions without introspection.

### 20.2. Building `BearerTokenAuthentication` directly from request JSON

If a controller reads client-supplied data and builds a principal/authorities, it bypasses the authentication boundary. Rely only on trusted introspector output.

### 20.3. Custom introspector always returning a principal

~~~java
// WRONG: illustrates an authentication-bypass implementation.
OpaqueTokenIntrospector unsafe = token ->
    new DefaultOAuth2AuthenticatedPrincipal(
        "admin",
        Map.of("sub", "admin"),
        List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
    );
~~~

This accepts every token string without calling the AS at all. A restricted test double may be used in unit tests, **never in production**.

### 20.4. Turning `active=true` into system-wide privileges

An active token does not mean sufficient scope, right audience, right tenant, or access to every record.

### 20.5. Assuming `roles` in the response automatically become `ROLE_*`

Spring Security by default maps scopes primarily to **`SCOPE_*`**. If the API uses custom roles/permissions, map them intentionally and enforce domain policy.

### 20.6. Dropping scope authorities during custom mapping

Constructing a new principal containing only `ROLE_ADMIN` can strip the `SCOPE_*` authorities required by endpoints. When adding authorities, preserve trusted and policy-permitted authorities.

### 20.7. Assuming opaque tokens have no expiration

The AS may compute `active` from expiration, revocation, and other policies. Never treat opaque tokens as permanent. **`exp`** metadata may or may not be present; when caching, always enforce lifetime limits.

### 20.8. Ignoring token errors to boost availability

When introspection suffers network/TLS errors, never allow access automatically; this is an authentication infrastructure failure that must fail closed.

### 20.9. Logging raw tokens

A Bearer token is a replayable credential. Never log `getToken().getTokenValue()`, credentials, or full `Authentication` objects. Log only request IDs and policy-safe metadata.

### 20.10. Confusing 401 with 403

Inactive tokens typically yield **401**. Active tokens lacking `SCOPE_orders.read` typically yield **403**. The two cases require distinct handling—never "fix" a 403 with `permitAll`.

## 21. End-to-end flow: Orders API

Suppose the contract is:

~~~text
Trusted AS:        https://login.example.com
Introspection URI: https://login.example.com/oauth2/introspect
Required audience: orders-api
Read scope:        orders.read
Domain policy:     matching tenant and ownership
~~~

Client sends:

~~~http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer <opaque-access-token>
~~~

**Step A — Receive token.** `BearerTokenAuthenticationFilter` extracts the raw token and builds `BearerTokenAuthenticationToken`. There is no trusted principal yet.

**Step B — Select provider.** `ProviderManager` delegates the request to `OpaqueTokenAuthenticationProvider`.

**Step C — Introspect.** The provider calls the introspector, which sends the token to the trusted Authorization Server. If `active=false` or the request cannot be verified, no successful `Authentication` is created.

**Step D — Check token policy.** If the response carries an audience and policy mandates **`orders-api`**, the API validates the audience—and likewise issuer/client/token type if contracted.

**Step E — Build `Authentication`.** The provider uses the default converter to build `BearerTokenAuthentication` with principal/authorities such as `SCOPE_orders.read`.

**Step F — Check HTTP authorization.** `SecurityFilterChain` requires **`SCOPE_orders.read`**. Missing that authority blocks the request.

**Step G — Check domain authorization.** The service checks that order 42 belongs to an authorized tenant/owner. A valid scope does not replace record-level permissions.

**Step H — Return response.** Only after all these checks pass does the API process data and respond.

This is the chain: **raw Bearer token → introspection by trusted source → successful `Authentication` → authority/domain authorization**.

## 22. Self-check questions

**1. Is `BearerTokenAuthenticationToken` the same as `BearerTokenAuthentication`?**

No. The first is the **unauthenticated request**, while the second is the **default successful result** of an opaque Resource Server.

**2. Is `OpaqueTokenAuthenticationProvider` the HTTP introspection client?**

It is the **`AuthenticationProvider`**, using **`OpaqueTokenIntrospector`**. The introspector implementation is typically the component sending HTTP requests to the AS.

**3. What does `OpaqueTokenIntrospector` return on success?**

**`OAuth2AuthenticatedPrincipal`** with matching token attributes and authorities. If the token is invalid, it must throw an error rather than returning a successful principal.

**4. Does `BearerTokenAuthentication.getToken()` return a raw `String` like `BearerTokenAuthenticationToken.getToken()`?**

No. The successful result returns an **`OAuth2AccessToken`**; the request token returns the raw token `String`. Both must be protected.

**5. Does `active=true` allow calling every endpoint?**

No. The API still checks audience, scopes, roles/permissions, and resource-level access.

**6. Why might an active opaque token receive a 403 from the API?**

Because it may lack the **`SCOPE_orders.read`** authority or be denied by domain authorization.

**7. What happens if a JWT is sent to `opaqueToken()`?**

It can be introspected as a token string; the result is still normally `BearerTokenAuthentication`. Spring does not switch to `JwtDecoder` simply because the raw token contains dots.

**8. Should `active=true` be cached?**

Only under an explicit revocation/expiration policy with bounded TTLs. Caching too long can allow revoked tokens to remain accepted.

**9. When the AS is unavailable, can introspection be skipped?**

No. Without valid proof per policy, an authenticated principal must never be created.

**10. Does a custom authentication converter always return `BearerTokenAuthentication`?**

No. A converter may return another `Authentication` type, so code relying on a specific subtype must be checked carefully.

## Conclusion

In a Spring Security Servlet Resource Server, **`BearerTokenAuthenticationToken`** is the authentication request carrying the token string, **`OpaqueTokenAuthenticationProvider`** verifies the token via **`OpaqueTokenIntrospector`**, and **`BearerTokenAuthentication`** is the default successful `Authentication` result.

**`OpaqueTokenIntrospector`** establishes the trust boundary, typically using the Authorization Server's RFC 7662 introspection endpoint. Once accepted, Spring Security can map scopes to **`SCOPE_*`** and use **`OAuth2AuthenticatedPrincipal`** to expose attributes in `SecurityContext`. Afterward, the API must still enforce audience, scopes, tenants, and business permissions.

Never construct an `Authentication` from a raw token directly, never treat `active=true` as system-wide authority, never expose access tokens or credentials, and never fail open when introspection errors occur.

### References

- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security API — `OpaqueTokenAuthenticationProvider`](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/OpaqueTokenAuthenticationProvider.html)
- [Spring Security API — `BearerTokenAuthentication`](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/BearerTokenAuthentication.html)
- [Spring Security API — `BearerTokenAuthenticationToken`](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/BearerTokenAuthenticationToken.html)
- [Spring Security API — `OpaqueTokenIntrospector`](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html)
- [Spring Security API — `OpaqueTokenAuthenticationConverter`](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenAuthenticationConverter.html)
- [Spring Security API — `SpringOpaqueTokenIntrospector`](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringOpaqueTokenIntrospector.html)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
