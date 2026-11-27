# JwtAuthenticationProvider and OpaqueTokenAuthenticationProvider

In a **Spring Security OAuth 2.0 Resource Server** for Servlet applications, two components—**`JwtAuthenticationProvider`** and **`OpaqueTokenAuthenticationProvider`**—are responsible for authenticating the request's **Bearer access token**. Both implement the `AuthenticationProvider` mechanism, yet use two different ways of validating tokens:

- **`JwtAuthenticationProvider`** uses a **`JwtDecoder`** to decode, verify, and convert a JWT access token into an authenticated `Authentication` object.
- **`OpaqueTokenAuthenticationProvider`** uses an **`OpaqueTokenIntrospector`** to validate a token via **token introspection** and then build an `Authentication` object from the returned attributes and authorities.

Understanding these two providers explains why the same `Authorization: Bearer ...` HTTP header can go through different validation mechanisms, why `401 Unauthorized` differs from `403 Forbidden`, and which extension points to customize when the Authorization Server issues specialized claims or scopes.

> **Scope:** This lesson focuses on the **Servlet** processing chain of Spring Security Resource Server: request → filter → authentication manager/provider → security context → authorization → controller. JWT and opaque token configurations are illustrated as **two separate options** for an API.

## 1. Role of Providers in Resource Server Architecture

Consider an Orders API application, a **Resource Server** that does not issue access tokens itself but accepts tokens issued to clients by an **Authorization Server**:

~~~text
Client                    Authorization Server                  Orders API
   |                               |                                |
   |--- Request access token ----->|                                |
   |<-- Access token --------------|                                |
   |                                                                |
   |--- GET /api/orders ------------------------------------------->|
   |    Authorization: Bearer <access-token>                        |
   |                                                                |
   |                            BearerTokenAuthenticationFilter    |
   |                                        |                       |
   |                               AuthenticationManager            |
   |                                        |                       |
   |                        Configured AuthenticationProvider       |
   |                          /                     \               |
   |          JwtAuthenticationProvider      OpaqueTokenAuthenticationProvider
   |                   |                         |                  |
   |               JwtDecoder             OpaqueTokenIntrospector   |
   |                   |                         |                  |
   |             Verify JWT             Introspect access token     |
   |                          \                     /               |
   |                           Valid Authentication?                |
   |                                      |                         |
   |                         Authorization (API permissions)        |
   |                                      |                         |
   |<--------------------- 200 / 401 / 403 -------------------------|
~~~

**The two branches are drawn side by side for comparison:** a typical request enters the provider branch chosen by the filter chain's `AuthenticationManager` configuration. Do not assume Spring Security tries JWT by default and automatically falls back to introspection if the JWT is invalid.

### What Is Each Component Responsible For?

| Component | Responsibility |
| --- | --- |
| `FilterChainProxy` and `SecurityFilterChain` | Select and order the security filters applied to a request |
| `BearerTokenAuthenticationFilter` | Extract the bearer token from the request and pass an authentication request to `AuthenticationManager` |
| `BearerTokenAuthenticationToken` | **Unauthenticated** `Authentication` object carrying the bearer token string from the request |
| `AuthenticationManager` / `ProviderManager` | Coordinate authentication with the appropriate `AuthenticationProvider` |
| `JwtAuthenticationProvider` | Validate JWTs via `JwtDecoder` and convert the JWT into an `Authentication` |
| `OpaqueTokenAuthenticationProvider` | Validate via `OpaqueTokenIntrospector` and build an `Authentication` from the introspection result |
| `SecurityContextHolder` / `SecurityContext` | Provide the accepted authentication information to downstream request processing |
| `AuthorizationFilter` and method security | Use `Authentication` alongside permission policies to permit or deny access |

These are two distinct stages:

1. **Authentication** asks: "Can this token be trusted to identify the subject and its associated permissions?"
2. **Authorization** asks: "Is the authenticated subject allowed to perform this action on the specific endpoint or resource?"

A JWT with a valid signature or an introspection response returning `active: true` **does not automatically grant permission** to read every record in the API.

## 2. The Servlet Processing Chain Before Reaching the Provider

When a request enters a Spring Security Servlet application:

1. The Servlet container invokes the filter chain containing Spring Security via `DelegatingFilterProxy` and `FilterChainProxy`.
2. Spring Security determines which `SecurityFilterChain` matches the request. An application can define multiple chains with `securityMatcher(...)` and `@Order` ordering.
3. Inside a chain configured as an OAuth 2.0 Resource Server, `BearerTokenAuthenticationFilter` uses a `BearerTokenResolver` (typically `DefaultBearerTokenResolver`) to extract the bearer token, primarily from the `Authorization` header.
4. If a token is present, the filter constructs a `BearerTokenAuthenticationToken` and invokes `AuthenticationManager.authenticate(...)`.
5. The manager delegates the request to a registered provider. The provider validates the token and either builds a valid `Authentication` or throws an authentication exception.
6. On success, the filter populates `SecurityContext` for the request and continues the filter chain. Authorization mechanisms then evaluate access permissions.
7. On authentication failure, the Resource Server typically returns a **401** Bearer response. When the token is valid but lacks permissions, the authorization layer typically returns **403**.

Sequence diagram:

~~~mermaid
sequenceDiagram
    autonumber
    participant Client
    participant F as BearerTokenAuthenticationFilter
    participant M as AuthenticationManager
    participant P as AuthenticationProvider
    participant A as AuthorizationFilter
    participant C as Controller

    Client->>F: GET /api/orders with Authorization: Bearer ...
    F->>F: BearerTokenResolver extracts token
    F->>M: authenticate(BearerTokenAuthenticationToken)
    M->>P: authenticate(...)
    alt Token valid
        P-->>M: Authenticated Authentication
        M-->>F: Authentication
        F->>F: Set Authentication in SecurityContext
        F->>A: Continue chain
        alt Sufficient permissions
            A->>C: Allow request through
            C-->>Client: 200 OK + data
        else Insufficient permissions
            A-->>Client: 403 Forbidden
        end
    else Token invalid
        P-->>M: AuthenticationException
        M-->>F: Authentication error
        F-->>Client: 401 Unauthorized
    end
~~~

**If the request carries no bearer token**, the filter lets the chain continue without creating a bearer-based `Authentication`. Afterward, if the endpoint requires authentication, endpoint protection still denies the request. This differs from a token **being present yet invalid** and rejected by the provider during authentication.

Additionally, errors parsing a bearer token from the header can occur directly inside `BearerTokenResolver`, before any provider is called.

### Why the Same `BearerTokenAuthenticationToken`?

`BearerTokenAuthenticationToken` wraps the **initial bearer token string**. It is neither a `JwtAuthenticationToken` nor an authenticated `BearerTokenAuthentication`.

A common point of confusion is that **both `JwtAuthenticationProvider` and `OpaqueTokenAuthenticationProvider` can support a `BearerTokenAuthenticationToken` input**. Therefore:

- Spring Security does not choose between the two providers via `supports(...)` based on whether a token looks like a JWT or opaque string.
- Choosing the validation type must be designed via Resource Server configuration, separate chains, or an appropriate `AuthenticationManagerResolver`.
- Do not turn "JWT or opaque?" into an arbitrary heuristic based on the number of dots in the string; token format does not replace issuer contracts and policies.

## 3. `JwtAuthenticationProvider`: Validating JWT Tokens

`JwtAuthenticationProvider` accepts a `BearerTokenAuthenticationToken` and uses `JwtDecoder` to convert the token string into a **verified** `Jwt` object.

A JWS compact-signed JWT string typically looks like:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Illustrative payload:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "scope": "orders.read orders.export"
}
~~~

The payload above is only an **example JSON claim set**; merely Base64URL-decoding and reading the payload does not make a token trustworthy.

### 3.1. Steps Inside the JWT Provider

~~~mermaid
flowchart TD
    A["BearerTokenAuthenticationToken"] --> B["JwtAuthenticationProvider"]
    B --> C["JwtDecoder.decode(token)"]
    C --> D{"JWT valid?"}
    D -- "No" --> E["AuthenticationException / Bearer 401"]
    D -- "Yes" --> F["Jwt: verified header + claims"]
    F --> G["JwtAuthenticationConverter"]
    G --> H["JwtAuthenticationToken"]
    H --> I["AuthenticationManager returns Authentication"]
    I --> J["SecurityContext, then API authorization checks"]
~~~

Key components:

**`JwtDecoder`** is responsible for decoding and verifying the token per configuration. With the widely used `NimbusJwtDecoder`, this includes verifying the JWS signature with the appropriate key along with token validators; the API must also configure validation for **issuer, timestamps, audience**, and any contract requirements with its issuer.

**`JwtAuthenticationConverter`** takes a valid `Jwt` and produces an `AbstractAuthenticationToken`. The default configuration produces a `JwtAuthenticationToken`, mapping `scope` or `scp` claims into `GrantedAuthority` instances prefixed with `SCOPE_`.

**`JwtAuthenticationToken`** typically contains:

- **Principal:** the `Jwt` object.
- **Authorities:** converted permissions, such as `SCOPE_orders.read`.
- **Name:** by default derived from `sub`, unless the converter is customized.
- **Token attributes:** accessible through the token authentication class API.

Controller example:

~~~java
import java.time.Instant;
import java.util.List;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class JwtProfileController {

    @GetMapping("/api/profile")
    String currentProfile(
            org.springframework.security.core.annotation.AuthenticationPrincipal
            Jwt jwt) {

        String subject = jwt.getSubject();
        Instant expiresAt = jwt.getExpiresAt();
        List<String> audiences = jwt.getAudience();
        return "Subject: " + subject;
    }
}
~~~

Using `@AuthenticationPrincipal Jwt` is **appropriate when the application uses a JWT Resource Server**. If the API switches to opaque tokens, the principal may no longer be a `Jwt`, requiring either updating the controller contract or using a shared abstraction.

### 3.2. Verifying Signature, Timestamps, and Issuer

The JWT provider does more than split a string on dots. In a typical flow:

1. The decoder parses a well-structured JOSE header and payload.
2. The decoder verifies the algorithm/signature using configured trusted keys. For issuers supporting JWKS, public keys can be fetched from the JWKS endpoint and refreshed when needed.
3. Validators check relevant conditions such as `exp`, `nbf`, and `iss`; application policy must explicitly specify `aud` and other required claims to verify.
4. Only after verification succeeds does `JwtAuthenticationConverter` convert accepted claims into identity and authorities.

`exp` and `nbf` typically use **NumericDate (Unix epoch seconds)** in JWT JSON. The Java layer converts them to `Instant` for timestamp validation. A configured clock-skew allowance is an acceptable clock drift margin, **not an extension of JWT lifetime**.

A valid signature is not enough if the token:

- Is expired.
- Was issued by a different issuer.
- Is intended for a different audience (e.g., Payments API instead of Orders API).
- Lacks a required scope/claim for the endpoint or is unauthorized for a specific object.

### 3.3. Converting Scopes and Principal Name

Example claims issued by an issuer:

~~~json
{
  "sub": "user-42",
  "preferred_username": "alice",
  "scope": "orders.read orders.write"
}
~~~

By default, Spring Security typically produces authorities like:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

If the issuer uses a `permissions` claim instead of `scope`, the application must define a corresponding converter. When you need to change the principal name to `preferred_username`, you can configure `JwtAuthenticationConverter`.

Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter grantedAuthorities =
        new JwtGrantedAuthoritiesConverter();
    grantedAuthorities.setAuthoritiesClaimName("permissions");
    grantedAuthorities.setAuthorityPrefix("PERMISSION_");

    JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(grantedAuthorities);
    converter.setPrincipalClaimName("preferred_username");
    return converter;
}
~~~

In this example, the `permissions` claim must have a data type compatible with the converter, such as a list of permission names:

~~~json
{
  "permissions": ["orders.read", "orders.export"]
}
~~~

Then the authorities become `PERMISSION_orders.read` and `PERMISSION_orders.export`. If you switch from `SCOPE_` to `PERMISSION_`, you must also update every `hasAuthority(...)` expression accordingly; do not assume the two prefixes are interchangeable.

To use this converter, pass it to `jwtAuthenticationConverter(...)` in the Resource Server DSL. A converter bean you declare **should not be assumed to apply automatically to every `SecurityFilterChain`** unless explicitly configured.

## 4. `OpaqueTokenAuthenticationProvider`: Validation via Introspection

An **opaque token** is an access token where the Resource Server does not rely on reading JWT claims and verifying signatures locally. The API typically sends the token to a **token introspection endpoint** exposed by the Authorization Server. Introspection can also be used for JWTs **if the issuer supports it** and the API is designed that way; the name "opaque token support" describes how the API **validates** the token, not a prohibition on the issuer issuing JWTs.

### 4.1. Steps Inside the Opaque Provider

~~~mermaid
flowchart TD
    A["BearerTokenAuthenticationToken"] --> B["OpaqueTokenAuthenticationProvider"]
    B --> C["OpaqueTokenIntrospector.introspect(token)"]
    C --> D["Authorization Server introspection endpoint"]
    D --> E{"Token active / accepted?"}
    E -- "No" --> F["Authentication error / Bearer 401"]
    E -- "Yes" --> G["OAuth2AuthenticatedPrincipal"]
    G --> H["GrantedAuthority from scope / attributes"]
    H --> I["BearerTokenAuthentication"]
    I --> J["AuthenticationManager returns Authentication"]
    J --> K["SecurityContext, then API authorization checks"]
~~~

In a typical introspection implementation:

1. `OpaqueTokenIntrospector` sends the access token string to the introspection endpoint along with the Resource Server's credentials, when required by the endpoint.
2. The Authorization Server checks the token state and relevant policies, then returns metadata.
3. If the token is valid, the introspector constructs an `OAuth2AuthenticatedPrincipal` with attributes and authorities interpreted per configuration.
4. The provider creates an authenticated `BearerTokenAuthentication` for the filter chain to use.

The request carrying the token to the API is different from the introspection request:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.com
Authorization: Bearer <access-token>
~~~

Illustrative introspection request from the Resource Server to the Authorization Server:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic <resource-server-credentials>
Content-Type: application/x-www-form-urlencoded

token=<access-token>
~~~

The credentials header and path in this example are **illustrative only**. The API uses its own credentials issued by the Authorization Server to call introspection. These credentials are not the end user's password or the `client_secret` of the client application making the API request.

An introspection response might look like:

~~~json
{
  "active": true,
  "sub": "user-42",
  "client_id": "orders-frontend",
  "scope": "orders.read orders.export",
  "exp": 1893456000,
  "aud": ["orders-api"],
  "iss": "https://auth.example.com/realms/shop"
}
~~~

When the token is no longer active, the endpoint typically returns:

~~~json
{
  "active": false
}
~~~

In practice, the response depends on the Authorization Server and the introspection client's permissions. `active: true` is a key requirement, yet the API must still ensure issuer, audience, scope, and permission policies match resource protection requirements. Especially when using a **custom introspector**, never treat any JSON response containing `sub` as sufficient for authentication.

### 4.2. `OAuth2AuthenticatedPrincipal` and `BearerTokenAuthentication`

Unlike the JWT branch, an opaque token's principal is typically `OAuth2AuthenticatedPrincipal`, and the resulting `Authentication` is typically `BearerTokenAuthentication`.

Example reading the principal:

~~~java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OpaqueProfileController {

    @GetMapping("/api/profile")
    String currentProfile(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        String subject = principal.getAttribute("sub");
        String clientId = principal.getAttribute("client_id");
        return "Subject: " + subject;
    }
}
~~~

The principal's attributes come from introspection and configured conversion steps. Do not assume every issuer returns `client_id`, `aud`, or custom claims; verify your Authorization Server's contract.

### 4.3. Introspection Does Not Refresh Tokens

When the API introspects a token, it asks **whether the presented token is still valid**. An `active: false` result does not cause the provider to fetch a new access token. Requesting or refreshing tokens is the responsibility of the **OAuth2 Client and Authorization Server**, not the Resource Server's two `AuthenticationProvider`s.

## 5. Direct Comparison of the Two Providers

| Criterion | `JwtAuthenticationProvider` | `OpaqueTokenAuthenticationProvider` |
| --- | --- | --- |
| Input from filter | `BearerTokenAuthenticationToken` | `BearerTokenAuthenticationToken` |
| Primary validation component | `JwtDecoder` | `OpaqueTokenIntrospector` |
| Source of truth | Signature/keys and claims inside the JWT, plus validators | Token state/attributes confirmed by the introspection endpoint |
| Typical `Authentication` result | `JwtAuthenticationToken` | `BearerTokenAuthentication` |
| Typical principal | `Jwt` | `OAuth2AuthenticatedPrincipal` |
| Authorities | Converted from JWT claims by converter | Extracted/converted from introspection attributes per configuration |
| Contact Authorization Server per request | Usually no, once trusted keys are available for local verification | Usually makes an HTTP introspection call per authentication unless caching is implemented |
| Token revocation | Difficult to take immediate effect with offline JWT validation alone | Can reflect revocation status via introspection, depending on issuer/caching |
| Network dependency during authentication | May be needed for metadata/JWKS or key rotation; not necessarily per request | Typically depends on the introspection endpoint on each authentication |
| Customization | `JwtDecoder`, token validators, `JwtAuthenticationConverter` | `OpaqueTokenIntrospector`, authority/principal conversion per version API |
| Issues or refreshes tokens? | **No** | **No** |

**Performance:** JWT allows the API to validate many requests locally once trusted keys are cached, reducing network calls. Introspection typically adds latency and depends on Authorization Server availability, though it lets the Resource Server observe issuer-managed token state. Caching introspection results can reduce load, but must be balanced against fast token revocation needs.

**Security:** Offline JWT validation requires strict checks on issuer, audience, signature, algorithm/key, and expiration. Introspection requires trusted TLS connections, protecting the Resource Server's client credentials, and verifying endpoints/responses accurately. Neither approach replaces business authorization such as "whether user A may view order 123."

## 6. Configuring Spring Security Servlet with the JWT Provider

For a Spring Boot application using the Servlet stack, add the Resource Server dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Declare a valid issuer in `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

Example `SecurityFilterChain` for JWT:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class JwtResourceServerSecurity {

    @Bean
    SecurityFilterChain jwtApiChain(HttpSecurity http) throws Exception {
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
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

In this configuration:

- `oauth2ResourceServer(...jwt(...))` wires JWT-based Bearer token handling and the JWT provider.
- `issuer-uri` enables supported standard issuer/JWKS discovery while validating the issuer according to Spring Security's configuration.
- The API must ensure the access token's **audience** matches the API; do not assume `issuer-uri` enforces all desired audience rules automatically.
- When the token scope is `orders.read`, common default mapping produces `SCOPE_orders.read` for `hasAuthority(...)`.
- Checking scopes in the filter chain **does not replace** object/tenant checks in services or controllers.

The `csrf(...disable())` snippet is only appropriate for **stateless APIs authenticating via Bearer tokens and not using browser-auto-sent cookies for authentication**. If the application uses cookies/sessions for login, design appropriate CSRF protection.

For example, `jwt(Customizer.withDefaults())` can be replaced with converter configuration:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
    jwt.jwtAuthenticationConverter(jwtAuthenticationConverter())
))
~~~

The snippet above is just **configuration wiring** inside the builder; it uses the `jwtAuthenticationConverter()` bean/helper defined earlier. If mapping to `PERMISSION_`, update `hasAuthority(...)` accordingly.

## 7. Configuring Spring Security Servlet with the Opaque Provider

If tokens are validated via introspection, replace the JWT configuration with opaque token configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: YOUR_RESOURCE_SERVER_INTROSPECTION_SECRET
~~~

The values above are illustrative only. In real systems, store introspection credentials in a secret manager or secure configuration mechanism, and use the URL published by your Authorization Server.

Example dedicated `SecurityFilterChain` for opaque tokens:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OpaqueResourceServerSecurity {

    @Bean
    SecurityFilterChain opaqueApiChain(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
~~~

**Note:** The JWT and opaque configuration classes in these two sections are **two mutually alternative examples for the same API**, not two files to copy simultaneously into one application as two default chains both matching all paths. If an application needs to accept both mechanisms, deliberately design chain/manager selection.

### 7.1. Customizing the Introspector

Depending on the Spring Security version and Authorization Server type, an API can define a custom `OpaqueTokenIntrospector` to:

- Call the introspection endpoint using the HTTP authentication mechanism required by the issuer.
- Transform attributes, such as scope names or tenant identifiers.
- Add or restrict `GrantedAuthority` instances according to defined policies.
- Reject tokens with the wrong audience or belonging to untrusted clients/issuers, when the response provides information to check.
- Control timeouts and connection errors when calling the issuer; consider caching if policy allows.

Crucially, a custom introspector must **preserve validation principles**: never construct a trusted `OAuth2AuthenticatedPrincipal` from data not verified by the issuer, and never ignore a deactivated token status.

### 7.2. Introspection Connection Errors vs. Invalid Token Errors

If introspection returns `active: false`, the token is rejected. If the introspection endpoint is unreachable, times out, or returns a server error, that is a **verification infrastructure failure**, not proof that the token is valid. The Resource Server must fail safely and never let the request through simply because the verification service errored.

The final HTTP status code for connection failures depends on components, versions, handlers, and application policy. Therefore, do not hardcode the assumption that **every introspection failure produces `401 invalid_token`**. Logs should contain useful diagnostics while strictly avoiding raw access tokens, client secrets, or sensitive responses.

## 8. Choosing the Right Provider for Your System

Several design criteria:

| Need | Commonly considered direction | Explanation |
| --- | --- | --- |
| High request volume requiring low per-request latency | JWT provider | Tokens can be verified locally once trusted keys are available |
| Token revocation status needs prompt enforcement | Introspection/opaque provider | Authorization Server can check current token state |
| Issuer emits opaque tokens and provides an introspection endpoint | Opaque provider | Cannot verify JWT signatures locally because tokens lack a compatible JWT structure |
| Issuer emits JWTs with standard signatures and JWKS | JWT provider | Resource Server verifies signatures and claims per contract |
| JWTs are used, but organization requires introspection on every request | Opaque/introspection approach, if supported by issuer | Verification mechanism depends on contract and policy choices |
| Resource Server must operate if issuer temporarily cannot serve introspection | JWT provider can help | Once trusted keys are cached, per-request issuer calls are usually unnecessary |

Do not choose a provider merely because of labels like "JWT is better" or "opaque is more secure." Base the decision on the token type the issuer actually issues, supported endpoints, acceptable latency, revocation requirements, and policy consistency across APIs.

### Accepting Multiple Token Types or Multiple Issuers

If a system has APIs/routes using different verification methods, you can use **multiple `SecurityFilterChain`s** with `securityMatcher(...)` and appropriate ordering to apply each configuration.

If routing by issuer or per tenant is needed, you can use **`AuthenticationManagerResolver<HttpServletRequest>`** with configured authentication managers; for example, a multi-tenant JWT model can use an **allowlist** of issuers. Never read an unverified `iss` from a token and trust arbitrary client-supplied issuers or JWKS URLs.

A subtle detail: both providers can `supports(BearerTokenAuthenticationToken.class)`. Registering both simultaneously in the same `ProviderManager` does not make provider ordering a reliable "automatically try the right token type" solution. Define an explicit routing policy or pick a single validation mode per chain.

## 9. Accessing Authentication in Controllers and Services

When using the JWT provider:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

void inspectJwt(Authentication authentication) {
    if (authentication instanceof JwtAuthenticationToken jwtAuth) {
        String subject = jwtAuth.getToken().getSubject();
        String name = jwtAuth.getName();
        var authorities = jwtAuth.getAuthorities();
    }
}
~~~

When using the opaque provider:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;

void inspectOpaque(Authentication authentication) {
    if (authentication instanceof BearerTokenAuthentication bearerAuth) {
        String subject = bearerAuth.getTokenAttributes().get("sub").toString();
        String name = bearerAuth.getName();
        var authorities = bearerAuth.getAuthorities();
    }
}
~~~

In applications supporting multiple authentication methods, business code should usually depend on **essential interfaces** such as `Authentication.getName()`, `getAuthorities()`, or a shared identity abstraction/service, rather than casting to provider-specific types in every controller.

Simple example using only the common interface:

~~~java
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CurrentUserController {

    @GetMapping("/api/me")
    Map<String, String> me(Authentication authentication) {
        return Map.of("principal", authentication.getName());
    }
}
~~~

Returning `authentication.getName()` to the client is only an example. A multi-tenant system must clearly define which issuer scope `sub` is unique within, avoiding using `sub` alone to access data across tenants or issuers.

## 10. Troubleshooting Scenarios in a Resource Server

### Scenario A: Expired JWT

Request:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer <expired-jwt>
~~~

`JwtDecoder` detects that the token no longer satisfies timestamp constraints; the provider does not produce an accepted `JwtAuthenticationToken`. The client typically receives **401** and the corresponding Bearer challenge. **`JwtAuthenticationProvider` does not refresh JWTs**; the client must request a new token from the Authorization Server when permitted.

### Scenario B: JWT Has Valid Signature but `aud` Targets Another API

If the Orders API only validates signature/issuer without enforcing an appropriate audience policy, it may accidentally accept a token issued for the Payments API. Verify that `aud` matches the Orders API during validation. A matching scope name does not substitute for audience checks.

### Scenario C: Revoked Opaque Token

The Resource Server introspects the token and the Authorization Server returns `active: false`. `OpaqueTokenAuthenticationProvider` will not construct a valid `Authentication` to reach the controller. This is an advantage of introspection when revocation status must be reflected and the issuer enforces the corresponding policy.

### Scenario D: Introspection Endpoint Slow or Unreachable

Callers experience errors or timeouts even with previously accepted bearer tokens. Check connectivity to the issuer, TLS, credentials, timeouts, and introspection load limits. Never "let requests pass" to avoid errors, as doing so removes authentication altogether.

### Scenario E: Valid Token, Yet API Returns 403

The provider authenticated the token, yet `AuthorizationFilter` or service-layer security denied the operation. For example, the token carries `SCOPE_orders.read` while the endpoint requires `SCOPE_orders.write`, or the subject is not allowed to access another user's order. Switching from the JWT provider to the opaque provider **does not automatically grant extra permissions**.

### Scenario F: Token Contains `roles`, Yet `hasRole("ADMIN")` Does Not Work

With the JWT provider, defaults may map only `scope` or `scp` into `SCOPE_...`; a custom `roles` claim does not automatically become `ROLE_ADMIN`. Configure an appropriate claim/authority mapping. Likewise, the introspection provider only populates authorities according to configured metadata and mappings.

### Scenario G: Client Sends an ID Token Instead of an Access Token

In OIDC, an **ID token** authenticates the user to an **OIDC Client**. A Resource Server must require an **access token intended for its API**. An ID token is also formatted as a JWT, which does not mean it is acceptable as an API access token. Checking audience, token type/purpose, and related policies prevents this confusion.

## 11. Security and Operational Boundaries

Both providers are **access token validation** components, not places to:

- Issue access tokens or refresh tokens to clients.
- Decide that a user may access every business record.
- Re-authenticate passwords/OTPs directly at the Orders API.
- Create OIDC login sessions for browsers.
- Automatically run a refresh grant when the API returns 401.

With JWTs, manage concerns such as signing keys/JWKS, key rotation, trusted issuers, audiences, allowed algorithms, lifetimes, and token revocation strategies. With introspection, manage trusted endpoints, TLS certificates, client credentials, latency, timeouts, endpoint availability, and failure handling.

For both, the API must authorize after authentication and enforce **object-level authorization**. For example, `orders.read` means the client may perform read operations within a certain scope—it **does not mean** a valid token may view everyone's orders.

When logging for diagnostics, you may log request IDs, authentication outcomes, verified issuers, or authenticated identities at an appropriate level. **Never log raw bearer tokens, refresh tokens, introspection client secrets**, or sensitive authentication payloads.

## 12. Summary of the Processing Flow

| Question | JWT Resource Server | Opaque Resource Server |
| --- | --- | --- |
| Which filter extracts the token from the HTTP request? | `BearerTokenAuthenticationFilter` | `BearerTokenAuthenticationFilter` |
| What wraps the initial token? | `BearerTokenAuthenticationToken` | `BearerTokenAuthenticationToken` |
| Which provider performs authentication? | `JwtAuthenticationProvider` | `OpaqueTokenAuthenticationProvider` |
| Which component performs verification? | `JwtDecoder` | `OpaqueTokenIntrospector` |
| What is the typical successful `Authentication`? | `JwtAuthenticationToken` | `BearerTokenAuthentication` |
| What checks endpoint permissions? | Spring Security's authorization mechanism | Spring Security's authorization mechanism |
| What issues or refreshes tokens? | Authorization Server on Client request | Authorization Server on Client request |

When reading Spring Security code, trace these two paths:

~~~text
JWT:
BearerTokenAuthenticationFilter
  -> AuthenticationManager
  -> JwtAuthenticationProvider
  -> JwtDecoder
  -> JwtAuthenticationConverter
  -> JwtAuthenticationToken
  -> SecurityContext
  -> Authorization

Opaque token / introspection:
BearerTokenAuthenticationFilter
  -> AuthenticationManager
  -> OpaqueTokenAuthenticationProvider
  -> OpaqueTokenIntrospector
  -> OAuth2AuthenticatedPrincipal
  -> BearerTokenAuthentication
  -> SecurityContext
  -> Authorization
~~~

**Key takeaway:** Both `JwtAuthenticationProvider` and `OpaqueTokenAuthenticationProvider` connect **Bearer token authentication** to Spring Security Servlet API protection, differing in **how tokens are verified and the resulting principal representation**. Successful token authentication is only the first step; deciding access to endpoints and individual resources remains the responsibility of the Resource Server's authorization layer.
