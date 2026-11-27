# `BearerTokenAuthenticationToken` Before Authentication in the Servlet Processing Chain

## 1. Context and Meaning of the "Unauthenticated" State

In a **Spring Security OAuth 2.0 Resource Server** running on the **Servlet stack** (such as a Spring MVC application), clients typically send an access token in an HTTP header:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6ImsxIn0.payload.signature
```

At the moment the HTTP request arrives, the value after `Bearer` is merely **a client-supplied string**. There is not yet any proof that this token was issued by a trusted Authorization Server, is unexpired, is intended for this API, or contains valid access permissions.

Spring Security represents that preliminary authentication request with the object:

```java
org.springframework.security.oauth2.server.resource.authentication
    .BearerTokenAuthenticationToken
```

This is an **unauthenticated `Authentication`**, typically created by `BearerTokenAuthenticationFilter` and passed to `AuthenticationManager`. It is the data-exchange carrier between the **HTTP filter** and the **authentication mechanism**, not a successful result or a trusted identity for authorization.

Keep these distinctions clear:

- **Bearer credential:** the access token string appearing in the request, before validation.
- **`BearerTokenAuthenticationToken`:** the `Authentication` object containing the token string just extracted from the HTTP request, with `isAuthenticated() == false` upon creation.
- **Authenticated `Authentication`:** the result produced by a provider after checking the token; typically `JwtAuthenticationToken` or `BearerTokenAuthentication`, depending on JWT vs. opaque token.
- **`SecurityContext`:** where Spring Security attaches the authentication result so downstream components can use it for authorization.

> **Principle:** "Having a token" only means the request presented a credential. "Authenticated" is the conclusion reached by a trusted authentication mechanism after verifying that credential.

## 2. Position of `BearerTokenAuthenticationToken` in the Servlet Processing Chain

In a Spring MVC application, requests travel through filter layers before reaching a controller:

```text
Client / HTTP request
        |
        v
Servlet container (Tomcat, Jetty, ...)
        |
        v
DelegatingFilterProxy ("springSecurityFilterChain")
        |
        v
FilterChainProxy
        |
        v
SecurityFilterChain matching the request path
        |
        +--> SecurityContextHolderFilter (manages context at start of request)
        |           |
        |           v
        +--> BearerTokenAuthenticationFilter
        |       |
        |       +-- BearerTokenResolver extracts token from request
        |       |
        |       +-- new BearerTokenAuthenticationToken(rawToken)
        |       |       isAuthenticated = false
        |       |
        |       +-- AuthenticationManager.authenticate(requestToken)
        |               |
        |               +-- JwtAuthenticationProvider / OpaqueTokenAuthenticationProvider
        |                       |
        |                       +-- validate token + map authorities
        |                       |
        |                       +-- authenticated Authentication
        |
        +--> SecurityContext holds the authenticated Authentication
        |
        +--> Downstream filters (e.g. AnonymousAuthenticationFilter,
        |    ExceptionTranslationFilter, AuthorizationFilter)
        |
        v
DispatcherServlet -> Controller -> Service -> Response
```

The diagram describes the **typical flow** of a Spring Security Servlet Resource Server. Actual filters and ordering may vary by version, number of `SecurityFilterChain`s, and additional filters. The invariant to understand is that **an unauthenticated request must pass through `AuthenticationManager`/provider before being used as a trusted identity**.

### Who Creates This Object?

In a standard Resource Server configuration, **`BearerTokenAuthenticationFilter`** itself executes:

```java
BearerTokenAuthenticationToken authenticationRequest =
        new BearerTokenAuthenticationToken(token);
```

The filter may also attach request `details`, then pass this object to `AuthenticationManager`. Controllers or business services never need to create and "log in" with this object manually.

### Why Create an Unauthenticated `Authentication`?

Spring Security unifies authentication behind the contract:

```java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
```

Both the input and output are `Authentication`, yet their **roles are completely different**:

1. **Input:** describes what credential the client presented, with no guarantee of validity.
2. **Authenticator:** selects the appropriate provider and verifies the credential.
3. **Successful output:** describes the principal, validated token, mapped authorities, and authenticated state.
4. **Failure:** throws `AuthenticationException`; no authenticated result is created for `SecurityContext`.

That is why the class name `BearerTokenAuthenticationToken` sounds like a "logged-in token," whereas in reality it is an **authentication request object**.

## 3. Structure of `BearerTokenAuthenticationToken`

`BearerTokenAuthenticationToken` is an `Authentication` implementation extending `AbstractAuthenticationToken`.

Characteristics upon initial creation:

| Member | Value or meaning before authentication |
|---|---|
| `getToken()` | Raw bearer token string extracted from the request |
| `getPrincipal()` | In this class, returns the **raw token string itself**, not `UserDetails` or a verified `Jwt` |
| `getCredentials()` | Also the **raw token string**; used as the credential for authentication |
| `getAuthorities()` | Initially no trusted authorities, typically an empty collection |
| `isAuthenticated()` | **`false`** when instantiated |
| `getDetails()` | May be populated by the filter with request details via `AuthenticationDetailsSource` |
| `getName()` | Must not be used as a trusted username at this stage; the principal is still the credential |

Example instantiating the object outside HTTP to inspect its API semantics:

```java
import org.springframework.security.oauth2.server.resource.authentication
        .BearerTokenAuthenticationToken;

String rawAccessToken = "opaque-or-jwt-token-value";
BearerTokenAuthenticationToken request =
        new BearerTokenAuthenticationToken(rawAccessToken);

// Not authenticated yet, no API access permissions.
boolean authenticated = request.isAuthenticated(); // false
String presentedToken = request.getToken();          // raw token
Object principal = request.getPrincipal();           // raw token
Object credentials = request.getCredentials();       // raw token
int authorityCount = request.getAuthorities().size();// 0
```

The example above explains the data type; **it is neither a guide for forging tokens nor a way to log users in from a controller**. In the real flow, Spring Security constructs this object after reading the Bearer credential.

### Do Not Misinterpret `principal`

In many login mechanisms, `principal` is a username, `UserDetails`, or a verified identity. With an input **`BearerTokenAuthenticationToken`**, however, `getPrincipal()` returns the raw token. If application code reads `authenticationRequest.getPrincipal()` and treats it as a user ID, it has confused a **credential** with an **identity**.

The confirmed identity appears **after** the provider succeeds, such as a verified `sub` JWT claim or the principal returned by introspection.

### Why Doesn't the Object Contain Scopes/Roles at Creation Time?

A JWT access token can be decoded to reveal `scope` or `roles`, but prior to verification, those are client-modifiable data. Hence `BearerTokenAuthenticationToken` does not decode JWTs or map permissions in its constructor. That belongs to **`JwtDecoder` / token introspection / provider** and the authority converter after the token has been verified.

Putting unverified authorities into an `Authentication` and using them for authorization violates the trust boundary.

## 4. From HTTP Header to Authentication Request

### 4.1. `BearerTokenResolver` Extracts the Bearer Token

`BearerTokenAuthenticationFilter` delegates reading the request to a `BearerTokenResolver`. The default Servlet implementation is `DefaultBearerTokenResolver`, which primarily reads the token from:

```http
Authorization: Bearer ACCESS_TOKEN
```

The resolver is responsible for recognizing the scheme and credential structure. By default, query parameters and form-body `access_token` parameters are not enabled as token transport channels. Settings changing how tokens are read belong to the application's specific security policy.

The return value when a structurally valid Bearer token is present is a **raw token `String`**. The resolver does not check the JWT signature, `exp`, audience, or scopes yet.

### 4.2. When No Bearer Token Is Present

Example:

```http
GET /api/orders HTTP/1.1
Host: api.example.com
```

When the resolver finds no Bearer credential, it normally returns `null`. `BearerTokenAuthenticationFilter` **does not create** a `BearerTokenAuthenticationToken` in this case and continues the filter chain.

Subsequently:

- An endpoint marked `permitAll()` can proceed without bearer authentication.
- An endpoint requiring `authenticated()` or a specific authority usually results in a 401 challenge when no other valid authentication mechanism is present.
- Another filter such as `AnonymousAuthenticationFilter` may supply an anonymous authentication representing an unauthenticated request; anonymous does not mean an access token was authenticated.

Missing a token is different from presenting an invalid token value.

### 4.3. When the Bearer Header Is Malformed

Example:

```http
Authorization: Bearer
```

Or:

```http
Authorization: Bearer abc def
```

The resolver may throw `OAuth2AuthenticationException` because the Bearer credential is structurally invalid. The filter handles the error through the Resource Server mechanism; **no valid `BearerTokenAuthenticationToken` is created to send to the provider**.

Thus two failure points must be distinguished:

- **Before `BearerTokenAuthenticationToken`:** the HTTP Bearer credential could not be extracted cleanly.
- **After `BearerTokenAuthenticationToken`:** the token string was extracted, but the JWT decoder/introspector determined the token is invalid.

Both cases may return 401, yet require diagnosing different components.

### 4.4. When Syntax Matches Bearer Format but the Token Is Fake

```http
Authorization: Bearer abc.def.ghi
```

The resolver can extract `abc.def.ghi` and construct a `BearerTokenAuthenticationToken` even though that string is not a valid JWT. **You cannot conclude authentication succeeded just because the object was created.** `JwtDecoder` will check the JWS format, signature, issuer, validity period, and configured validators.

### 4.5. When a Request Carries Multiple Credentials

If there are two `Authorization` headers or both header and query/form tokens, how the resolver and proxies see them depends on configuration and the HTTP layer. The safe rule is to define one unambiguous bearer credential source and reject ambiguous requests. Creating **one `BearerTokenAuthenticationToken` from the first token** does not prove the original request had only one token.

Enforce duplicate/multiple-source detection policies at the gateway or a request-processing layer that sees full inputs, rather than picking one token arbitrarily by order.

## 5. Passing to `AuthenticationManager`: Where Real Authentication Begins

After creating the authentication request, the filter delegates to `AuthenticationManager`. Simplified flow:

```java
// Pseudocode illustrating framework logical responsibilities.
String token = bearerTokenResolver.resolve(request);

if (token == null) {
    filterChain.doFilter(request, response);
    return;
}

BearerTokenAuthenticationToken authenticationRequest =
        new BearerTokenAuthenticationToken(token);

authenticationRequest.setDetails(
        authenticationDetailsSource.buildDetails(request));

Authentication authenticationResult =
        authenticationManager.authenticate(authenticationRequest);

// Only the authenticated result is stored in SecurityContext.
SecurityContext context = securityContextHolderStrategy.createEmptyContext();
context.setAuthentication(authenticationResult);
securityContextHolderStrategy.setContext(context);

filterChain.doFilter(request, response);
```

This is **explanatory pseudocode**, not a verbatim copy of the filter source code: the real implementation also handles `AuthenticationManagerResolver<HttpServletRequest>`, `SecurityContextRepository`, exceptions, and failure handlers. Do not paste this pseudocode into an application to replace the built-in filter.

### How Does `AuthenticationManager` Choose a Provider?

In Spring Security, an `AuthenticationManager` such as `ProviderManager` iterates to find an `AuthenticationProvider` that supports the authentication request type. In a typical Resource Server:

| Provider | Accepts request | Authentication method | Result on success |
|---|---|---|---|
| `JwtAuthenticationProvider` | `BearerTokenAuthenticationToken` | Uses `JwtDecoder` to verify signed JWT access tokens and run validators | `JwtAuthenticationToken` |
| `OpaqueTokenAuthenticationProvider` | `BearerTokenAuthenticationToken` | Uses `OpaqueTokenIntrospector` to query the AS for token and metadata | `BearerTokenAuthentication` |
| Custom provider | Depends on design and `supports(...)` | Must enforce all system validation requirements | Appropriate authenticated `Authentication` |

Both JWT and opaque tokens can start from **the exact same unauthenticated object type**. The input `Authentication` type does not say whether the inner token is JWT or opaque; the **configured provider/decoder** determines how it is checked.

Spring Security supports `AuthenticationManagerResolver<HttpServletRequest>` to choose a manager per request in multi-issuer/multi-tenant models, but selection must adhere to **pre-configured trusted sources**. Never pick an arbitrary issuer or JWKS solely from unverified claims.

## 6. Path When the API Accepts JWT Access Tokens

Suppose the Resource Server uses JWTs:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com/realms/demo
```

And configures a security chain:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
```

This is a Resource Server application configuration using the Spring Security DSL. It lets the framework wire the necessary filter and provider automatically. In practice, the Resource Server must also verify the **API's audience** per the token contract; configuring an issuer alone does not automatically satisfy every audience or access-token-type policy.

### 6.1. Step-by-Step from Raw Token to Authenticated JWT

1. Client sends `Authorization: Bearer <jwt>`.
2. `BearerTokenAuthenticationFilter` uses the resolver to extract the token string.
3. The filter creates `BearerTokenAuthenticationToken` with `isAuthenticated() == false` and no authorities.
4. `AuthenticationManager` routes the request to the matching `JwtAuthenticationProvider`.
5. The provider calls `JwtDecoder.decode(rawToken)`.
6. The decoder parses the JWS, verifies the signature with trusted keys and algorithms, and runs validators for issuer, timestamps, and configured constraints (such as audience, or `at+jwt` token profile).
7. `JwtAuthenticationConverter` converts the `Jwt` into a `JwtAuthenticationToken` with the corresponding principal and authorities.
8. The provider returns the authenticated result; the filter stores it in `SecurityContext`.
9. `AuthorizationFilter` and permission policies continue checking the endpoint and resources.

Sequence diagram:

```mermaid
sequenceDiagram
    participant Client
    participant Filter as BearerTokenAuthenticationFilter
    participant Resolver as BearerTokenResolver
    participant Manager as AuthenticationManager
    participant Provider as JwtAuthenticationProvider
    participant Decoder as JwtDecoder
    participant Context as SecurityContextHolder

    Client->>Filter: HTTP Authorization: Bearer JWT
    Filter->>Resolver: resolve(request)
    Resolver-->>Filter: raw JWT String
    Note over Filter: Create BearerTokenAuthenticationToken\nauthenticated=false, empty authorities
    Filter->>Manager: authenticate(authenticationRequest)
    Manager->>Provider: authenticate(authenticationRequest)
    Provider->>Decoder: decode(raw JWT)
    Decoder-->>Provider: Jwt with verified signature/claims
    Note over Provider: Convert Jwt into JwtAuthenticationToken
    Provider-->>Manager: authenticated Authentication
    Manager-->>Filter: authenticationResult
    Filter->>Context: Store result in SecurityContext
    Filter-->>Client: Continue filters and endpoint handling
```

If the decoder throws an error due to an invalid signature, expired token, or failed validator, the provider fails authentication. No trusted `JwtAuthenticationToken` is produced for authorization to accept the request.

### 6.2. Comparing the Object Before and After JWT Provider Processing

| Characteristic | Before: `BearerTokenAuthenticationToken` | After: `JwtAuthenticationToken` |
|---|---|---|
| Role | Authentication request | Authentication result |
| State | Unauthenticated | Authenticated when provider returns successfully |
| Principal | Raw bearer token string | `Jwt` verified by the decoder |
| Credentials | Raw bearer token string | Per implementation, verified token representation |
| Authorities | No verified permissions | Mapped from claims such as `scope`/`scp` via converter |
| Identity | Must not be inferred from raw token | Typically from `sub` claim or configured principal claim |
| Usable for authorization? | **No** | Yes, after checking scopes and business policies |

Example of a verified JWT:

```json
{
  "iss": "https://id.example.com/realms/demo",
  "sub": "user-123",
  "aud": "orders-api",
  "scope": "orders.read",
  "iat": 1909996400,
  "exp": 1910000000
}
```

The values above are **illustrative claims only**, not a signed access token. If `scope=orders.read`, default configuration maps it to authority `SCOPE_orders.read`. However, a scope does not automatically authorize the user to read **every** order; the business layer still checks permissions for order `42`.

### 6.3. Why Not Read `scope` Directly from `BearerTokenAuthenticationToken`?

`BearerTokenAuthenticationToken` has not verified the token. An attacker could edit the payload of a JWT, producing JSON that appears to have `scope=admin`, without a valid signature. If the application Base64URL-decodes claims and grants permissions *before* `JwtDecoder`, the signature becomes meaningless.

Only a `Jwt` that has passed through a trusted `JwtDecoder` and the API's validators is valid input for converters and authorization.

## 7. Path When the Access Token Is Opaque

A Resource Server can also accept opaque access tokens, meaning token strings whose internal structure the API cannot interpret directly. For example:

```http
Authorization: Bearer XoU6DkL3p9v2opaqueToken
```

The filter **still constructs**:

```java
BearerTokenAuthenticationToken requestToken =
        new BearerTokenAuthenticationToken("XoU6DkL3p9v2opaqueToken");
```

The difference appears at the provider:

1. `OpaqueTokenAuthenticationProvider` receives `BearerTokenAuthenticationToken`.
2. The provider calls `OpaqueTokenIntrospector` to check the token via introspection or a trusted Authorization Server mechanism.
3. The AS replies with whether the token is `active` along with relevant metadata.
4. On successful authentication, the provider builds `BearerTokenAuthentication` with principal/authorities from the verified data.
5. The authenticated result is placed into `SecurityContext` by the filter; the authorization layer checks subsequent permissions.

Configuration example:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.com/oauth2/introspect
          client-id: orders-api-introspection
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

This configuration demonstrates introspection capability, not a guarantee that `active=true` automatically validates the API's **audience/resource**. The Resource Server needs policies checking metadata against the issuer contract, including permissions, token type, and intended recipient.

### Before and After Opaque Authentication

| Characteristic | `BearerTokenAuthenticationToken` | `BearerTokenAuthentication` |
|---|---|---|
| Token | Unverified raw string | OAuth2 access token processed by provider |
| Principal | Credential string | `OAuth2AuthenticatedPrincipal` with introspection attributes |
| Authorities | Empty | Mapped from trusted scopes/metadata |
| Authenticated | `false` | `true` once provider completes |
| Placed in context? | Must not be | Yes, when authentication succeeds |

Common ground between JWT and opaque tokens: **the initial request object is never treated as an authenticated identity**.

## 8. When Is `SecurityContext` Updated?

Only after `AuthenticationManager.authenticate(...)` returns a successful `Authentication` does `BearerTokenAuthenticationFilter` have a basis to place it into `SecurityContext`. In modern Spring Security Servlet versions, the filter manages context creation and interacts with `SecurityContextRepository` according to configuration.

State transition diagram:

```text
Before Bearer filter:
    SecurityContext may be empty or hold context from another mechanism;
    no Bearer authentication result exists yet for this request.

BearerTokenResolver -> raw token:
    No authenticated result yet.

new BearerTokenAuthenticationToken(rawToken):
    isAuthenticated = false
    Must not be used as an authenticated principal in context.

AuthenticationManager.authenticate(...):
    Success -> authenticated Authentication
    Failure -> AuthenticationException

Bearer filter after success:
    SecurityContext.authentication = authenticated result
    Subsequent filters can check request permissions.
```

### `SecurityContextHolder` and Request Scope

`SecurityContextHolder` is the access point for the security context of the current execution thread. In Servlet applications, the framework manages, populates, and clears the context around the request lifecycle.

Do not assume `SecurityContextHolder` retains token state indefinitely after the response ends. In a stateless API, a bearer access token is normally authenticated **per request**, and the context is cleared according to the HTTP processing lifecycle rather than acting like a form-login session.

When using async servlets, thread pools, or the reactive stack, security context propagation follows separate rules. This lesson covers only the **Servlet Resource Server** path; do not apply Servlet filters directly to WebFlux Security.

### Why Not Place an Unauthenticated Object in the Context?

Anti-pattern to avoid:

```java
// DO NOT do this in a custom filter:
BearerTokenAuthenticationToken requestToken =
        new BearerTokenAuthenticationToken(rawToken);

// Do not place it in the context and let the request proceed as if logged in:
SecurityContextHolder.getContext().setAuthentication(requestToken);
```

Even when `isAuthenticated()` is currently `false`, placing a raw object into the context blurs the boundary between credential and identity. Worse, if custom code flips the authenticated flag itself or constructs an `Authentication` with authorities without provider verification, the authorization layer may mistakenly trust the result.

**Implementation principle:** only store results produced by a trusted authentication mechanism in the context; let `BearerTokenAuthenticationFilter` and `AuthenticationManager` manage this process.

## 9. What Does `isAuthenticated()` Actually Mean?

The `Authentication` interface declares:

```java
boolean isAuthenticated();
```

A `false` value on a newly created `BearerTokenAuthenticationToken` means Spring Security **has not yet accepted** that credential as proof of authentication. It does not mean "the token is expired"; expiration is only determined when the decoder/introspector checks it.

Statements to distinguish:

| Statement | True or false? | Explanation |
|---|---|---|
| "Having a `BearerTokenAuthenticationToken` means authentication succeeded." | **False** | The object is an authentication request |
| "This object holds the raw token in `getCredentials()`." | **True** | It is the credential to be verified |
| "`isAuthenticated=false` proves the token is fake." | **False** | Before verification, no conclusion can be drawn |
| "The provider may return a different `Authentication` than the input." | **True** | JWT/opaque providers typically return different result types |
| "Scopes read from a raw JWT can be used immediately for authorization." | **False** | Claims have not passed signature/issuer/audience checks |
| "An authenticated JWT result is always allowed to access every endpoint." | **False** | Endpoint and resource authorization are still required |

Some `Authentication` implementations provide a mechanism to mark `authenticated`, but **never call `setAuthenticated(true)` yourself to bypass `AuthenticationManager`**. That is not credential verification; flipping a boolean does not make a JWT signature valid or an opaque token active.

### `getName()` Differs Before and After

`Authentication.getName()` is often used as the principal name in audit logs or for displaying identity. At the `BearerTokenAuthenticationToken` stage, the principal is still the raw token, so **never call `getName()` to log a user ID or make access decisions**.

After JWT authentication, the default principal name typically comes from `sub`, or can be customized via a converter. With opaque tokens, the principal name depends on the attributes returned by the introspector and how they are mapped. Never treat `BearerTokenAuthenticationToken.getPrincipal()` as the current user.

## 10. Complete Example of a Successful Request

Suppose the system uses JWT access tokens for an order-reading API. Processing sequence:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer VALID_ACCESS_TOKEN
```

In this request:

1. The Servlet container hands the request to `springSecurityFilterChain`.
2. `FilterChainProxy` selects the matching `SecurityFilterChain`.
3. `BearerTokenAuthenticationFilter` receives the request and calls the resolver.
4. The resolver extracts the string `VALID_ACCESS_TOKEN`.
5. The filter constructs `BearerTokenAuthenticationToken` containing the raw string and no authorities.
6. `AuthenticationManager` passes it to `JwtAuthenticationProvider`.
7. `JwtDecoder` verifies the JWT signature, issuer, expiration, and application validators (such as audience `orders-api`, and profile `at+jwt` if using RFC 9068).
8. The provider converts the verified JWT into `JwtAuthenticationToken`; the converter can map `scope=orders.read` to `SCOPE_orders.read`.
9. The filter stores the authenticated result in the security context.
10. `AuthorizationFilter` checks `hasAuthority("SCOPE_orders.read")`.
11. The controller/service checks permission to view order `42`, e.g., verifying the order belongs to the principal's account or tenant.
12. Only if every condition passes does the endpoint return the data.

A valid outcome does not mean the Resource Server issued the token; the **Authorization Server issues tokens**, while the Resource Server only validates them and enforces access policies per the contract.

### Checkpoints to Observe in a Debugger

| Checkpoint | Commonly observed object type | Meaning |
|---|---|---|
| Right after `resolve` | `String` | Raw credential extracted from HTTP |
| Right after constructor | `BearerTokenAuthenticationToken` | Unauthenticated authentication request |
| Inside `JwtAuthenticationProvider` | `BearerTokenAuthenticationToken` | Provider is using the token string to invoke the decoder |
| After `JwtDecoder.decode(...)` | `Jwt` | JWT verified by the decoder against configured validators |
| After `JwtAuthenticationConverter` | `JwtAuthenticationToken` | Principal and authorities populated from verified token |
| In controller after filter chain succeeds | `Authentication` in `SecurityContext` | Used for authorization and principal details |

These objects can differ when using opaque tokens, custom converters, or multiple security chains.

## 11. Examples When Authentication Fails

### 11.1. Expired JWT

The request has a well-formed Bearer header, so the resolver still creates `BearerTokenAuthenticationToken`. When the provider calls the decoder, an expired `exp` causes authentication failure. The filter handles the authentication error, usually returning **401 Unauthorized** with a Bearer challenge. The context is not updated with an "almost valid" Authentication.

### 11.2. JWT with Wrong Issuer or Audience

Suppose an OIDC ID token signed by the same provider is meant for client `web-client`:

```json
{
  "iss": "https://id.example.com/realms/demo",
  "sub": "user-123",
  "aud": "web-client",
  "exp": 1910000000
}
```

A Bearer request can construct `BearerTokenAuthenticationToken` normally. Even a valid signature does not turn an ID token into an access token for `orders-api`. The decoder/validators must enforce the **token-purpose and audience contract** to reject tokens meant for another purpose. Without proper audience/profile validation, an API risks mistakenly accepting tokens issued by the same issuer.

### 11.3. Inactive Opaque Token

The resolver builds an authentication request from the token string, but introspection returns `active=false` or rejects per the issuer contract. The provider creates no authenticated result; the API rejects the credential.

### 11.4. Valid Token with Insufficient Scope

The provider authenticates the JWT successfully and returns a `JwtAuthenticationToken` with authorities. However, `POST /api/orders` requires `orders.write`, while the token only has `orders.read`. This is an **authorization failure**, typically returning **403 Forbidden**, unlike a `BearerTokenAuthenticationToken` rejected during authentication.

### 11.5. A Token Revoked Before Expiration

With self-contained JWTs validated by signature and expiration, a Resource Server typically does not automatically know a token was revoked without extra mechanisms (introspection, revocation lists, short TTLs, sender/session binding, etc.). `BearerTokenAuthenticationToken` cannot know this either. Supporting revocation is part of the **token contract and validation mechanism**, not the authentication request constructor.

## 12. Error Handling and HTTP Status Codes

In a Resource Server, errors generally divide as follows:

| Origin | Example | Typical HTTP result |
|---|---|---|
| Resolver finds no Bearer token | Missing `Authorization` | Public endpoints may run; protected endpoints typically return 401 |
| Resolver sees malformed Bearer credential | `Authorization: Bearer ` | Failure at extraction step, usually 401 per default handler |
| Provider/decoder rejects token | Bad signature, expired, wrong audience | Usually **401 Unauthorized** with `invalid_token` |
| Provider succeeds, authorization denies | Missing scope/object permission | Usually **403 Forbidden**, possibly with `insufficient_scope` |

Example response:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

A response like:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

indicates a situation where the token may be valid for authentication, yet the request lacks permission. Exact headers and `error_description` depend on `BearerTokenAuthenticationEntryPoint`, `BearerTokenAccessDeniedHandler`, exceptions, and endpoint policies.

Note: RFC 6750 distinguishes `invalid_request` (usually 400), `invalid_token` (401), and `insufficient_scope` (403); Spring Security has specific mapping rules, so do not assume every malformed bearer request always returns 400.

**Never include raw tokens in error responses.** Diagnostics should pinpoint the failing component (resolver, decoder, introspection, authorization) without exposing credentials.

## 13. Class Interfaces and Commonly Confused Classes

Class names in Spring Security can look similar:

| Class | Where used? | State and purpose |
|---|---|---|
| `BearerTokenAuthenticationToken` | Input to `AuthenticationManager` when a request carries a bearer token | Unauthenticated; holds raw token |
| `JwtAuthenticationToken` | Result of JWT Resource Server authentication | Authenticated; carries `Jwt` and authorities |
| `BearerTokenAuthentication` | Result of opaque token Resource Server authentication | Authenticated; carries principal and processed access token |
| `OAuth2AuthenticationToken` | Commonly seen in OAuth2 Login/OIDC Client | Authentication of a user logged in via OAuth2/OIDC client |
| `UsernamePasswordAuthenticationToken` | Username/password authentication | Can be unauthenticated or authenticated depending on constructor/factory |
| `AnonymousAuthenticationToken` | Anonymous mechanism in the filter chain | Represents a request with no user authentication in an anonymous context |
| `OAuth2AccessToken` | Access token data model in Spring Security | **Not** an alternative implementation for an authentication request |

Important distinctions:

- **`BearerTokenAuthenticationToken`** is not an OIDC ID token.
- **`BearerTokenAuthentication`** is a different class and typically represents a **successful opaque-token authentication result**.
- **`JwtAuthenticationToken`** is the Resource Server's JWT validation result; sharing the word "Jwt" does not mean it comes from `oauth2Login()`.
- **`OAuth2AuthenticationToken`** typically represents authentication from OAuth2 Login; do not use it to bypass Bearer access token validation for a REST API.

## 14. Example Inspecting the Object in an Application

In a controller, Spring Security can inject the `Authentication` object **after the request has passed through the filter chain**. For example:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PrincipalController {

    @GetMapping("/api/me")
    String me(Authentication authentication) {
        if (authentication instanceof JwtAuthenticationToken jwtAuth) {
            // This authentication has passed JWT Resource Server validation.
            return jwtAuth.getName();
        }
        return "Authenticated with another supported mechanism";
    }
}
```

The example assumes `/api/me` is configured as `authenticated()`. Cases with no authentication or apps supporting multiple mechanisms should be handled according to real requirements; do not treat this example as a complete authorization policy.

To observe the internal flow in a debugger, you can place breakpoints at:

- `BearerTokenAuthenticationFilter#doFilterInternal` when the resolver returns a token.
- Constructor or getters of `BearerTokenAuthenticationToken` to inspect the request state.
- `ProviderManager#authenticate` to observe the selected provider.
- `JwtAuthenticationProvider#authenticate` or `OpaqueTokenAuthenticationProvider#authenticate`.
- `NimbusJwtDecoder#decode` when the API uses JWT/JWS.
- Where the filter stores the authenticated result in `SecurityContextHolder`.
- `AuthorizationFilter` to inspect endpoint permission checks.

These are **architectural observation points**; exact class names and method locations can change across Spring Security versions. With real tokens, a debugger may display raw tokens in memory, so avoid sharing screenshots, dumps, or debug output containing credentials.

### Safe Logging

Safe to log:

- Request ID/tracing ID and endpoint (without bearer tokens in the URL).
- Processing stage: `resolution`, `jwt_validation`, `opaque_introspection`, `authorization`.
- Concise normalized outcomes such as `invalid_signature`, `expired`, `wrong_audience`, `insufficient_scope`.

Do NOT log:

- `getToken()`, `getCredentials()`, raw `Authorization` header.
- An entire `BearerTokenAuthenticationToken` via automatic object serialization/logging.
- Refresh tokens, ID tokens, opaque tokens, or sensitive JWT payloads.

A bearer token is a credential that can be replayed by whoever obtains it, so logging raw values creates risks beyond an ordinary programming bug.

## 15. Implementation Mistakes and How to Avoid Them

### Mistake 1: Trusting an Object Because It Implements `Authentication`

```java
// Do not use logic like this to grant access:
Authentication request = new BearerTokenAuthenticationToken(rawToken);
if (request != null) {
    // "Having an Authentication" does not mean authenticated!
}
```

`Authentication` is an **interface for both requests and results**. Only the object type and verified authenticated state determine whether it can be used for authorization, and permissions must still be checked at the appropriate layer.

### Mistake 2: Manually Setting `isAuthenticated=true`

```java
// Do not turn a raw credential into an identity by flipping a flag.
BearerTokenAuthenticationToken request =
        new BearerTokenAuthenticationToken(rawToken);
// request.setAuthenticated(true); // Never do this as an authentication mechanism.
```

A flag does not verify the signature, issuer, audience, scope, or introspection status. Always invoke `AuthenticationManager` and trust **the result returned by the provider**, never fabricating a result without validation.

### Mistake 3: Using the Raw Token as a User ID

```java
// Do not do this with an unauthenticated authentication request:
// String userId = request.getPrincipal().toString();
```

At this layer, `principal` is the raw token, not a verified user ID. Doing so could also write the token into a database or log as a username. Use the authenticated principal (such as `JwtAuthenticationToken`) with claims verified by the decoder.

### Mistake 4: Treating "Decoded JWT" as "Verified JWT"

Anyone can Base64URL-decode a JWT to read the JSON payload, yet that step does not prove the signature is valid. `BearerTokenAuthenticationToken` only holds the raw string. All `scope`, `roles`, and `tenant` permissions must come from a **verified** source through a trusted JWT decoder/introspector.

### Mistake 5: Skipping Audience Checks Because a Familiar Issuer Signed the Token

An OIDC Provider may sign an ID token for `web-client` and an access token for `orders-api` using the same key. If the API fails to validate the audience and token profile, it may mistakenly accept an ID token as a bearer access token. Token classification and validation must never rely on "the JWT looks valid."

### Mistake 6: Writing a Second Filter That Reimplements Bearer Handling

A custom servlet filter that extracts headers itself and pushes unauthenticated objects into the context can conflict with the standard filter, produce inconsistent error handling, and blur trust boundaries. Usually you should configure `oauth2ResourceServer().jwt()` or `opaqueToken()`, adding `JwtDecoder`, `BearerTokenResolver`, or converters at the proper extension points.

If you must customize an `AuthenticationProvider`, preserve all validation rules, error handling, and authorization rather than skipping checks inside the provider.

## 16. Questions to Read the Flow Correctly in a Debugger

When encountering `BearerTokenAuthenticationToken`, identify the request stage using these questions:

1. **Where was the object created?** If in `BearerTokenAuthenticationFilter`, the Bearer credential was just extracted from HTTP.
2. **Is `isAuthenticated()` `true` yet?** When newly constructed, it is `false`; do not infer whether the token is valid or invalid yet.
3. **What is `getPrincipal()`?** At this stage it is the raw token, not a user.
4. **Which provider is handling it?** `JwtAuthenticationProvider` for JWT, `OpaqueTokenAuthenticationProvider` for opaque tokens.
5. **Has the JWT decoder/introspector succeeded?** This is the boundary between untrusted data and an authenticated result.
6. **What class is the final `Authentication` object?** Typically `JwtAuthenticationToken` for JWT; typically `BearerTokenAuthentication` for opaque tokens.
7. **Has the result been placed into `SecurityContext`?** Only after success is it used for authorization.
8. **Where were audience, profile, and scopes checked?** A valid signature alone does not authorize the API request.
9. **If the endpoint is denied, did it fail at authentication or authorization?** 401 usually indicates a credential error; 403 usually indicates insufficient permissions after authentication.
10. **Is any sensitive information being logged?** A raw bearer token is a credential and must be protected.

## 17. Summary of the Authentication Request's Role

In brief:

```text
Authorization: Bearer <raw-token>
            |
            v
    BearerTokenResolver
            |
            v
BearerTokenAuthenticationToken
  principal      = raw token string
  credentials    = raw token string
  authorities    = []
  authenticated  = false
            |
            v
 AuthenticationManager
            |
            v
       Provider
       /      \
      /        \
 JwtDecoder   OpaqueTokenIntrospector
      \        /
       \      /
     Authenticated Authentication
       (JwtAuthenticationToken /
        BearerTokenAuthentication)
            |
            v
   SecurityContextHolder
            |
            v
 Authorization + business rules
```

**`BearerTokenAuthenticationToken` is an authentication request carrying a bearer credential**, not proof of identity or an access decision. The filter creates it, `AuthenticationManager`/provider validates the token, and only the **authenticated result** is stored in `SecurityContext` for downstream authorization rules to evaluate.

## 18. References

- **Spring Security Reference — OAuth 2.0 Resource Server (Servlet)**: filter components, JWT/opaque tokens, and authentication. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html
- **Spring Security Reference — JWT Resource Server**: JWT decoder, claim validation, and authorities from scopes. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- **Spring Security API — `BearerTokenAuthenticationToken`**: Authentication object for an unauthenticated bearer token. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/BearerTokenAuthenticationToken.html
- **Spring Security API — `BearerTokenAuthenticationFilter`**: extracts bearer credentials and invokes AuthenticationManager. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/authentication/BearerTokenAuthenticationFilter.html
- **Spring Security API — `JwtAuthenticationProvider`**: authenticates JWTs from bearer authentication requests. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationProvider.html
- **Spring Security API — `OpaqueTokenAuthenticationProvider`**: processes opaque access tokens via introspection. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/OpaqueTokenAuthenticationProvider.html
- **RFC 6750 — OAuth 2.0 Bearer Token Usage**: sending Bearer credentials and error handling. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 7519 — JSON Web Token**: JWT format and claims. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 7662 — OAuth 2.0 Token Introspection**: validating opaque token state. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens**: binding JWT access tokens to the intended resource and purpose. https://www.rfc-editor.org/rfc/rfc9068
