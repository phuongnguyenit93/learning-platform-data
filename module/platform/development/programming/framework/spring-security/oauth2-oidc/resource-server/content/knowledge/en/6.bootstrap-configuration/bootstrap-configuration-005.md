# Configuring Opaque Tokens with an Introspection Endpoint and Credentials

In a **Spring Security OAuth 2.0 Resource Server**, the API normally receives an access token from the client via the `Authorization: Bearer ...` header. If the access token is an **opaque token** (a string the API cannot decode and verify claims from on its own), the Resource Server needs a reliable way to know whether the token is still active, whom it was issued to, and what permissions it holds. The standard approach is to send the token to a **token introspection endpoint** provided by the Authorization Server, following **RFC 7662**.

To configure this successfully, clearly distinguish **two types of credentials** in a request involving introspection:

1. **The access token sent from the client to the Resource Server**: the business request credential, e.g. `Authorization: Bearer <ACCESS_TOKEN>`.
2. **The Resource Server's credentials when calling the introspection endpoint**: dedicated credentials allowing the Authorization Server to authorize the API to query token status—typically **introspection client ID + client secret**, sent via HTTP Basic over HTTPS.

These two credentials serve completely different purposes. **Never use a user's access token as the client secret**; nor should you send the Resource Server's client secret in API responses or to browsers. This lesson covers designing this contract and configuring it on both **Spring MVC/Servlet** and **Spring WebFlux/Reactive**, with HTTP, YAML, and Java examples, authorization, operational failures, and security considerations.

> Hostnames, tokens, client IDs, and URLs in this lesson are **illustrative examples**. In a real system, obtain endpoints and authentication policies from your trusted Authorization Server/Identity Provider (IdP).

## 1. What Are Opaque Access Tokens and Token Introspection?

OAuth 2.0 does not require access tokens to have a JWT structure. An Authorization Server can issue a string that only it understands, for example:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.test
Authorization: Bearer opa_9f47a2e1c9b84d67a03
Accept: application/json
~~~

The value `opa_9f47a2e1c9b84d67a03` is illustrative only and not valid. The client does not need to know how the token is represented: it simply puts the **access token string** after the `Bearer` scheme. Nor should the Resource Server **guess** what permissions a token has from the characters in the string.

**Introspection** is a backend-to-backend request from the Resource Server to an endpoint protected by the Authorization Server. The Resource Server sends the token to check and authenticates **itself** to the endpoint. The Authorization Server responds with whether the token is `active` and, when appropriate, metadata such as `scope`, `sub`, `client_id`, `exp`, or `aud`.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant RS as Resource Server (Orders API)
    participant AS as Authorization Server
    C->>RS: GET /api/orders/42 + Bearer opaque token
    RS->>AS: POST /oauth2/introspect<br/>token=... + introspection client auth
    AS->>AS: Validate token and RS lookup permission
    AS-->>RS: JSON: active, scope, sub, ...
    alt Token active and sufficient permissions
        RS->>RS: Create Authentication, check scopes and policies
        RS-->>C: 200 OK (or business response)
    else Token inactive/invalid
        RS-->>C: 401 Unauthorized
    else Token active but insufficient permissions
        RS-->>C: 403 Forbidden
    end
~~~

### 1.1. How Opaque Tokens Differ from JWTs in Resource Server Processing

| Criterion | Locally verified JWT access token | Opaque access token with introspection |
|---|---|---|
| Token format | Typically three Base64URL parts separated by dots | Does not need an API-readable structure |
| Typical verification method | Verify signature/JWK, issuer, timestamps, audience, claim validation | Call trusted introspection endpoint, receive `active` and metadata |
| Network call to Authorization Server per request | Typically no, once JWK/metadata are cached | Typically yes, unless an explicit cache is designed |
| Detecting revoked tokens | Requires a revocation strategy or short TTL | Can be detected near real-time via introspection, depending on cache and AS policy |
| Data used by Resource Server | JWT claims **after verification** | Introspection attributes **from trusted endpoint** |
| How client sends token | `Authorization: Bearer <token>` | `Authorization: Bearer <token>` |

Introspection can also be applied to JWT-formatted tokens if the system intentionally chooses that pattern. The `opaqueToken(...)` name in Spring Security denotes **introspection-based authentication**, not a rule forcing the token string into a specific non-JWT format.

## 2. Distinguishing Three Commonly Confused Endpoints

In an OAuth 2.0/OIDC system, the Authorization Server exposes multiple endpoints. They are not interchangeable:

| Endpoint | Who calls it | Purpose | Data sent |
|---|---|---|---|
| **Token endpoint** | OAuth 2.0 client | Obtain access/refresh tokens per grant | `grant_type`, code, client credentials, refresh token... |
| **Introspection endpoint** | Resource Server or AS-authorized client | Check an issued token and retrieve metadata per lookup permissions | `token`, optional `token_type_hint`; caller must be properly authenticated/authorized |
| **OIDC UserInfo endpoint** | OIDC client with suitable access token | Retrieve end-user claims per OIDC | Access token for UserInfo, typically via Bearer |
| **JWK Set endpoint** | JWT verifier | Fetch published public keys | Typically GET; not for querying opaque token `active` status |

Example introspection endpoint (not live):

~~~text
https://idp.example.test/oauth2/introspect
~~~

Do not blindly append `/introspect` to a login page or token endpoint URL unless the provider publishes that exact path. For Authorization Servers supporting metadata, you can find `introspection_endpoint` in **OAuth 2.0 Authorization Server Metadata**, though you must verify compatibility with your IdP and actual security setup. Having OIDC discovery does not guarantee every provider supports introspection for every token type.

## 3. What Does an Introspection HTTP Request Send?

Per RFC 7662, the Resource Server sends an HTTP `POST` to the introspection endpoint using `application/x-www-form-urlencoded`. The key parameter is `token`:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: idp.example.test
Authorization: Basic <BASE64_OF_CLIENT_ID_COLON_CLIENT_SECRET>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=opa_9f47a2e1c9b84d67a03&token_type_hint=access_token
~~~

Explanation of components:

- `POST /oauth2/introspect`: request **from Resource Server to Authorization Server**, not an end-user API call.
- `Authorization: Basic ...`: proves the **introspection client** identity when the provider uses HTTP Basic. The Base64 string encodes client ID and client secret as required by HTTP Basic; Base64 **is not encryption**, so the connection must use HTTPS.
- `Content-Type: application/x-www-form-urlencoded`: POST form encoding required by RFC 7662.
- `token`: **the access token being checked**; not the introspection client's secret.
- `token_type_hint=access_token`: optional hint for the Authorization Server; not mandatory and providers may ignore it.
- `Accept: application/json`: client expects a JSON response.

`token` may contain characters requiring percent-encoding; the HTTP client or Spring library handles proper form encoding. **Never append the token to a URL query string** when the endpoint expects a form body.

### 3.1. Example Response for an Active Token

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": true,
  "scope": "orders.read orders.create",
  "client_id": "shop-web-client",
  "sub": "user-123",
  "token_type": "Bearer",
  "exp": 1924992000,
  "iat": 1924988400,
  "aud": ["orders-api"],
  "iss": "https://idp.example.test"
}
~~~

`active: true` indicates the token is considered active by the Authorization Server under its policy. **Not every Authorization Server returns all the fields above.** Under RFC 7662, attributes beyond `active` are disclosed depending on token type and disclosure policy for the caller.

| Field | Meaning | How the API uses it |
|---|---|---|
| `active` | Whether the token is still recognized | Mandatory check during introspection |
| `scope` | Granted scopes, usually space-delimited | Mapped to authorities then checked against endpoints |
| `sub` | Subject represented by the token per AS profile | Used to identify principal and data permissions, if present |
| `client_id` | Client receiving the token per AS definition | Used if policy restricts which clients may call the API |
| `token_type` | Token type, typically Bearer | Checked against profile when contract requires |
| `exp` / `iat` / `nbf` | Expiration, issuance, not-before timestamps | Time bounds and caching policies when present |
| `aud` | Target resource/API for the token | Verify the token is meant for this API if returned |
| `iss` | Token issuer | Checked when profile/contract uses this field |

**Never assume `active=true` means "every API can accept this token."** If an AS issues tokens for multiple Resource Servers, the API must establish a resource/audience binding contract and proper caller permissions on introspection. When `aud` is omitted, resource suitability must be guaranteed by another rule agreed upon with the Authorization Server.

### 3.2. Inactive Token

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": false
}
~~~

An opaque token can be inactive because it expired, was revoked, does not exist, or the caller is not permitted to inspect it. Per RFC 7662, the server may withhold the specific reason. **An HTTP 200 from the introspection endpoint does not mean the access token is valid**; you must inspect `active`.

### 3.3. Introspection Client Rejected

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="introspection"
~~~

This occurs when the **Resource Server is not authorized to call introspection**—for example, wrong client secret, client ID, authentication method, or policy. It differs from introspection returning HTTP 200 with `{"active": false}` due to an invalid end-user token. Distinguishing the two cases helps troubleshoot the real root cause.

## 4. Two Credential Pairs and Where They Live

| Flow | Credential | Sent to | Managed by |
|---|---|---|---|
| Client → API | `Authorization: Bearer <ACCESS_TOKEN>` | Resource Server | OAuth client receiving token from AS |
| API → Introspection endpoint | `Authorization: Basic <BASE64(id:secret)>` in typical config | Authorization Server | Resource Server managing AS-issued ID/secret |

If using another introspection authentication method such as **mTLS**, **private_key_jwt**, or provider-specific Basic variants, configure the HTTP client/introspector accordingly. **The three default properties below do not automatically support every client authentication scheme.**

The introspection client must be authorized by the Authorization Server to **look up only the appropriate token/resource scope**. Never reuse a browser OAuth client's secret or an Authorization Server admin secret as the introspection secret. In multi-API architectures, each Resource Server may need its own introspection client for permission boundaries and auditing.

### Relationship Between `client-id` and `aud`

`client-id` in introspection configuration is the **Resource Server's identity when calling the introspection endpoint**. `aud` in the access token identifies the **API permitted to receive the token**. These two values can differ:

~~~text
Introspection client-id = orders-introspection-client
Token audience         = orders-api
Token client_id        = shop-web-client
~~~

These are three distinct identities with different purposes. Do not assume introspection `client-id` equals `aud` or the `client_id` inside the access token unless your AS contract specifically defines it that way.

## 5. Configuring a Spring Boot Resource Server for Introspection

Example for an Orders API using Spring Boot + Spring Security with **opaque token introspection**. First, add dependencies:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

In `application.yml`:

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

Example runtime environment variables supplying the values:

~~~text
OAUTH_INTROSPECTION_URI=https://idp.example.test/oauth2/introspect
OAUTH_INTROSPECTION_CLIENT_ID=orders-introspection-client
OAUTH_INTROSPECTION_CLIENT_SECRET=<secret-stored-securely>
~~~

These are **illustrative values**; never commit real secrets to Git, container images, issue trackers, or public docs. The `client-secret` property must come from a secret manager, protected environment variables, or your deployment platform's secure configuration mechanism.

### 5.1. Exact Meaning of Each Property

| Spring Boot property | What it is used for |
|---|---|
| `spring.security.oauth2.resourceserver.opaquetoken.introspection-uri` | HTTPS URL where the Resource Server sends tokens to verify |
| `spring.security.oauth2.resourceserver.opaquetoken.client-id` | Resource Server ID at the introspection endpoint |
| `spring.security.oauth2.resourceserver.opaquetoken.client-secret` | Secret authenticating the Resource Server to the introspection endpoint |

The property segment **`opaquetoken`** is written as one word in the configuration path. Do not confuse it with `oauth2.client.registration.*` — that group is for applications acting as an **OAuth 2.0 Client**, whereas here the application acts as a **Resource Server** introspecting tokens.

Spring Boot creates the appropriate introspection components when the dependency and properties are configured and no custom bean replaces them. On the Servlet stack this is `OpaqueTokenIntrospector`; on WebFlux it is `ReactiveOpaqueTokenIntrospector`.

### 5.2. Enabling Opaque Tokens in HTTP Security

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class OrdersApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(withDefaults()))
            .build();
    }
}
~~~

This example assumes a **pure Bearer-token API without browser login cookies/sessions**, hence illustrating `SessionCreationPolicy.STATELESS` and disabling CSRF. If the application includes cookie/session login or browser flows exposed to CSRF risk, design dedicated CSRF protection; never disable CSRF across the entire app blindly.

In this configuration:

- `oauth2ResourceServer(...opaqueToken(...))` enables access token authentication via introspection.
- Spring Security uses the endpoint and credentials from YAML to call the Authorization Server.
- `authorizeHttpRequests(...)` enforces authorization rules after authentication.
- `hasAuthority("SCOPE_orders.read")` checks the scope mapped from the introspection response.
- `anyRequest().authenticated()` requires a valid token for remaining requests; real applications should define explicit rules per endpoint and avoid exposing sensitive actions solely behind generic authentication.

### 5.3. Controller Reading the Authenticated Principal

~~~java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CurrentUserController {

    @GetMapping("/api/me")
    Map<String, String> me(@AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        return Map.of("principal", principal.getName());
    }
}
~~~

In an opaque-token Resource Server, Spring Security typically builds a `BearerTokenAuthentication` with an `OAuth2AuthenticatedPrincipal` and authorities derived from scopes. `principal.getName()` depends on the `sub` attribute or introspection response characteristics/configuration. If the token represents a service, the principal name may not be a human username. Do not use this example to infer data permissions purely from the principal name.

## 6. Execution Flow in Servlet

When a request arrives:

~~~mermaid
flowchart TD
    A["Client sends Authorization: Bearer token"] --> B["Spring Security FilterChainProxy"]
    B --> C["BearerTokenAuthenticationFilter"]
    C --> D["BearerTokenAuthenticationToken"]
    D --> E["AuthenticationManager / OpaqueTokenAuthenticationProvider"]
    E --> F["OpaqueTokenIntrospector"]
    F --> G["HTTPS POST introspection + client authentication"]
    G --> H{"active = true?"}
    H -->|No| I["Authentication failure → HTTP 401"]
    H -->|Yes| J["OAuth2AuthenticatedPrincipal + GrantedAuthority"]
    J --> K["BearerTokenAuthentication / SecurityContext"]
    K --> L{"Sufficient authority and policy?"}
    L -->|No| M["HTTP 403"]
    L -->|Yes| N["Controller / Service"]
~~~

The Resource Server **does not issue tokens** and does not send end-user passwords to introspection. It uses the token received in the request to query the Authorization Server, then places the authenticated principal into the request's security context.

### Responsibilities of Key Classes

| Spring Security component (Servlet) | Responsibility |
|---|---|
| `SecurityFilterChain` | Configures the protected request group |
| `BearerTokenAuthenticationFilter` | Extracts the Bearer token and triggers authentication |
| `BearerTokenAuthenticationToken` | Represents the unauthenticated credential |
| `AuthenticationManager` / `OpaqueTokenAuthenticationProvider` | Coordinates and executes opaque token authentication |
| `OpaqueTokenIntrospector` | Performs introspection and returns an authenticated principal |
| `OAuth2AuthenticatedPrincipal` | Represents the principal and retrieved attributes/authorities |
| `BearerTokenAuthentication` | Bearer token authentication result stored in context |
| `AuthorizationFilter` / URL rules | Evaluates authorities and access policies |

Spring Security handles the standard processing pipeline. The application should configure endpoints and permissions per the contract, and only introduce a custom introspector for specific needs such as audience, tenant, attribute mapping, or client authentication schemes not supported out of the box.

## 7. Configuring the Same Contract on Spring WebFlux

When running **Spring WebFlux**, the client header sent to the API and the introspection contract **stay the same**. However, the security pipeline uses `SecurityWebFilterChain`, `ServerHttpSecurity`, and `ReactiveOpaqueTokenIntrospector` instead of Servlet interfaces.

Dependencies for a reactive application:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

`application.yml` uses the exact same property group:

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

Corresponding Java configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ReactiveOrdersApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .csrf(csrf -> csrf.disable())
            .authorizeExchange(auth -> auth
                .pathMatchers("/actuator/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(withDefaults()))
            .build();
    }
}
~~~

`csrf.disable()` only illustrates the assumption of a pure Bearer API not relying on cookies/sessions. When browser cookie login exists, configure CSRF separately just like in Servlet.

Reactive flow diagram:

~~~mermaid
flowchart TD
    A["Bearer token request"] --> B["WebFilterChainProxy / SecurityWebFilterChain"]
    B --> C["AuthenticationWebFilter"]
    C --> D["ReactiveAuthenticationManager"]
    D --> E["OpaqueTokenReactiveAuthenticationManager"]
    E --> F["ReactiveOpaqueTokenIntrospector"]
    F --> G["HTTP introspection → Mono<OAuth2AuthenticatedPrincipal>"]
    G --> H["Reactive SecurityContext"]
    H --> I["authorizeExchange"]
    I --> J["WebFlux handler"]
~~~

HTTP calls to the introspection endpoint must fit the reactive model so they never block the event loop. If implementing a custom `ReactiveOpaqueTokenIntrospector`, never invoke a blocking HTTP client inside an operator like `Mono.just(blockingCall())`. Avoid `block()` in WebFlux request processing.

### 7.1. Comparing the Interfaces

| Responsibility | Servlet / Spring MVC | Reactive / WebFlux |
|---|---|---|
| HTTP security builder | `HttpSecurity` | `ServerHttpSecurity` |
| Security configuration | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Bearer filter | `BearerTokenAuthenticationFilter` | `AuthenticationWebFilter` |
| Opaque token manager | `OpaqueTokenAuthenticationProvider` | `OpaqueTokenReactiveAuthenticationManager` |
| Introspection integration | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |
| Security context | `SecurityContextHolder` | `ReactiveSecurityContextHolder` |
| Scope rule | `authorizeHttpRequests(...).hasAuthority(...)` | `authorizeExchange(...).hasAuthority(...)` |
| HTTP testing tool | `MockMvc` | `WebTestClient` |

A Spring MVC application may use `WebClient` as an HTTP client, but that does not turn `HttpSecurity` into `ServerHttpSecurity`. Security configuration types must match the **actual web runtime** of the application.

## 8. Scopes and Principal After Successful Introspection

When introspection returns:

~~~json
{
  "active": true,
  "scope": "orders.read orders.create",
  "sub": "user-123",
  "client_id": "shop-web-client"
}
~~~

Spring Security normally maps scopes into `GrantedAuthority` instances prefixed with `SCOPE_`:

~~~text
scope = "orders.read orders.create"
    ↓
GrantedAuthority: SCOPE_orders.read
GrantedAuthority: SCOPE_orders.create
~~~

In `SecurityFilterChain`, declaring:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

Results in:

- Token `active=true`, with `orders.read`: passes **authentication** and satisfies the GET **scope rule**.
- Token `active=true`, only `orders.create`: authenticated, yet lacks GET permission, typically returning **403 Forbidden**.
- Token `active=false`: does not produce a valid principal, typically returning **401 Unauthorized**.
- Token `active=true`, yet principal tries to read someone else's order: the service must **further enforce data ownership/tenant checks**, not rely on scopes alone.

### 8.1. Action Permissions vs. Resource Permissions

| Endpoint | Illustrative minimum scope | Domain-specific check |
|---|---|---|
| `GET /api/orders/{id}` | `orders.read` | Order owner / tenant / sharing rules |
| `POST /api/orders` | `orders.create` | Active customer, valid payload |
| `POST /api/orders/{id}/cancel` | `orders.cancel` | Order owner and cancellable state |
| `GET /api/admin/orders` | `orders.admin.read` | Admin role and tenant boundary |

Do not infer that an access token's `client_id` is the end-user account. Under `client_credentials`, a token may represent a service, while under authorization code it represents a user and client per the token profile. The introspection contract must define the meaning of `sub`, `client_id`, `aud`, and extended claims.

### 8.2. Introspection Does Not Automatically Enforce Audience/Issuer Binding

One Authorization Server can issue tokens for multiple APIs. Consider:

~~~text
Orders API audience  = orders-api
Billing API audience = billing-api
Trusted AS           = https://idp.example.test
~~~

A token issued for `billing-api` **must not** be accepted by Orders API just because introspection returns `active=true`. The API must enforce resource binding via one of:

1. The AS scopes introspection responses per Resource Server based on the introspection client identity and only returns `active=true` for tokens belonging to that resource; **or**
2. The AS returns trusted `aud`/metadata and the Resource Server applies a validator for its own audience; **or**
3. Another strictly enforced, mutually agreed mechanism proves the token is meant for the API.

Do not assume Spring Security automatically checks `aud` or `iss` in every introspection response the way a JWT decoder does. **The core trust chain of introspection is the configured endpoint, TLS, client authentication, and the returned data contract.**

## 9. When Do You Need a Custom `OpaqueTokenIntrospector`?

Using only the three endpoint/ID/secret properties suffices for basic introspection when the AS uses a supported auth method and the default contract meets needs. A **custom introspector** is appropriate when:

- The AS returns additional tenant, audience, or role claims that the Resource Server must enforce before accepting a token.
- The API needs custom mapping from scopes/roles to `GrantedAuthority`.
- The endpoint requires custom HTTP client settings, timeouts, proxies, mTLS certificates, `private_key_jwt`, or body authentication other than Basic.
- The system needs policy-driven caching, latency metrics, bounded retries, or failover.
- The Resource Server must restrict tokens to specific clients/issuers/resources per contract.

**Extension principle:** receive access token → call a trusted introspection implementation → verify `active`/metadata per policy → return principal only after all mandatory checks succeed. Never construct a successful principal when introspection fails or times out.

### 9.1. Example Audience-Checking Wrapper

The following example shows audience checking wrapping an **already safely configured delegate introspector**. It is a supplementary class to wire into your bean/DSL per your Spring Security version and application type. Do not use it as a replacement for authenticating against the introspection endpoint.

~~~java
import java.util.Collection;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class AudienceCheckingIntrospector implements OpaqueTokenIntrospector {
    private final OpaqueTokenIntrospector delegate;
    private final String expectedAudience;

    public AudienceCheckingIntrospector(
            OpaqueTokenIntrospector delegate,
            String expectedAudience) {
        this.delegate = delegate;
        this.expectedAudience = expectedAudience;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal = delegate.introspect(token);
        Object audience = principal.getAttribute("aud");

        boolean accepted =
            (audience instanceof String && expectedAudience.equals(audience))
            || (audience instanceof Collection<?>
                && ((Collection<?>) audience).contains(expectedAudience));

        if (!accepted) {
            throw new OAuth2AuthenticationException(
                new OAuth2Error(
                    "invalid_token",
                    "The token is not intended for this API",
                    null
                )
            );
        }
        return principal;
    }
}
~~~

This class **does not know the endpoint or credentials itself**: the delegate must be constructed from a real HTTP client/introspector with trusted URL and credentials. In Spring Boot, registering your own `OpaqueTokenIntrospector` bean may stop auto-configuration from creating the default bean; wire the delegate and wrapper explicitly to avoid self-referential beans.

Depending on the Authorization Server, `aud` may be a string, a collection, or absent. Under this example policy, a missing claim is rejected. If the AS does not return audience, enforce reliable resource binding on the server side or use another agreed mechanism rather than skipping validation without review.

In WebFlux, implement the equivalent using `ReactiveOpaqueTokenIntrospector` and reactive publishers. A Servlet implementation cannot be reused in WebFlux simply by changing imports.

### 9.2. Introspection Authentication Methods Other Than HTTP Basic

HTTP Basic with `client-id` and `client-secret` is the standard Spring Boot opaque-token Resource Server path. Some Authorization Servers instead require:

| Mechanism | Purpose | Additional implementation required |
|---|---|---|
| `client_secret_basic` | Sends ID/secret via HTTP Basic | Typically handled by default properties |
| `client_secret_post` | Sends credentials in the form body | Needs HTTP client/introspector supporting AS convention |
| `private_key_jwt` | Authenticates client via private-key-signed JWT assertion | Requires assertion signing, key management, claims, and profile-compliant endpoint |
| Mutual TLS (mTLS) | Resource Server authenticates with client certificate | Configure keystore/truststore, HTTP client TLS, and AS policy |
| Provider-specific mechanism | E.g., gateway token or custom auth header | Consult AS documentation and build matching integration |

Never replace `Authorization: Basic` with `Authorization: Bearer <END_USER_ACCESS_TOKEN>` unless the Authorization Server's proprietary protocol explicitly requires an appropriate administrative token issued for that exact purpose. The token being introspected and the credential authorizing **permission to introspect** are two separate entities.

### 9.3. Expiration and Rotation of Introspection Secrets

Client secrets used for introspection typically follow a lifecycle governed by the Authorization Server. If a secret is revoked or rotated while the API still uses the old secret, introspection calls can fail en masse. A rotation workflow should include:

1. Ability to issue a new secret in the secret manager with restricted read access.
2. Deployment/reload or rolling restart mechanism so the Resource Server picks up new credentials.
3. Overlap policy where both old and new secrets are valid simultaneously, if supported by the AS.
4. Health checks and monitoring for introspection authentication failures after rotation.
5. Controlled revocation of the old secret.

Never log old or new secret values in logs or error states. **Keep secrets isolated by environment**: production secrets must never be reused in development or staging.

## 10. Testing the Introspection Endpoint with an HTTP Client

Before wiring Spring Security, the integration team can test the introspection endpoint using a **test token**, a dedicated test-environment introspection account, and HTTPS. This helps separate **endpoint/credentials** issues from **Spring Security configuration** issues.

### 10.1. cURL Sending an Introspection Request

Bash/Zsh example when environment variables are securely populated:

~~~bash
curl --silent --show-error --fail-with-body \
  --request POST \
  --user "$OAUTH_INTROSPECTION_CLIENT_ID:$OAUTH_INTROSPECTION_CLIENT_SECRET" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "token=$ACCESS_TOKEN" \
  --data-urlencode "token_type_hint=access_token" \
  "https://idp.example.test/oauth2/introspect"
~~~

`--data-urlencode` encodes the token properly for a form body. `--user` instructs cURL to use HTTP Basic per the example contract. On systems with strict credential protection rules, keep in mind that command arguments and environment variables can be captured by process monitors, shells, or CI tools; follow your organization's secret management and safe testing practices. Never use real tokens in screenshots, tutorials, or shared logs.

**Results to distinguish:**

~~~text
HTTP 200 + {"active": true, ...}
    → introspection caller accepted; token active.

HTTP 200 + {"active": false}
    → introspection caller accepted; token inactive
      or caller not permitted to receive token details per AS policy.

HTTP 401/403 from the introspection endpoint itself
    → typically wrong/missing credentials or caller lacks lookup permission.

HTTP 404/405
    → typically wrong endpoint URL or HTTP method.

TLS/DNS/timeout/5xx
    → connectivity, configuration, availability, or AS/gateway error.
~~~

Do not look only at an HTTP 200 status from introspection and conclude the token is valid. The deciding field is `active`, combined with attributes matching the API policy.

### 10.2. cURL Calling the Resource Server

After configuring Spring Security, test calling the API with a token:

~~~bash
curl --silent --show-error --include \
  --header "Authorization: Bearer $ACCESS_TOKEN" \
  --header "Accept: application/json" \
  "https://orders-api.example.test/api/orders/42"
~~~

Important distinction: this request sends the **Bearer access token for Orders API**, not the introspection client ID/secret. Introspection client values stay strictly on the backend.

Do not test by disabling authentication or moving the token into a URL query parameter. An API returning 200 when the entire security chain is disabled proves nothing about whether introspection is configured correctly.

## 11. Error States Across the Two Different HTTP Hops

An opaque-token request passes through two HTTP exchanges: client ↔ API and API ↔ Authorization Server. Errors on the second hop therefore surface to the client through the first hop.

### 11.1. No Access Token Sent

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.test
Accept: application/json
~~~

The Resource Server protecting the endpoint typically responds:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

In this case there is normally **no need** to call the introspection endpoint because there is no credential to verify.

### 11.2. Inactive or Invalid Access Token

Introspection returns:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"active":false}
~~~

The Resource Server typically responds to the client:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Do not forward sensitive details from the Authorization Server directly to the client. `invalid_token` sufficiently communicates that the Bearer credential was rejected, unless the API specifies a richer error contract.

### 11.3. Active Access Token Missing Scope

Introspection may return `active=true` and `scope="orders.create"` while the client calls `GET /api/orders/42` requiring `orders.read`. Token authentication succeeds, yet authorization denies the request:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.read"
~~~

The header above is an example per RFC 6750. Exact default behavior and `WWW-Authenticate` content vary with Spring Security configuration and authorization handlers; the core rule remains **401 for missing/invalid credentials, 403 for insufficient permissions after authentication**.

### 11.4. Wrong Introspection Client Secret

The Authorization Server returns 401 to the introspection call itself. This is a **Resource Server configuration or permission error**, not proof that every end-user token is invalid. The application must **refuse the request** whenever it cannot introspect; the HTTP response to the caller may be 5xx or another status depending on exception handling. Avoid mapping every upstream error blindly to an end-user 401, which hides revoked or misconfigured secrets from operations.

### 11.5. Introspection Endpoint Timeout or Unavailability

If the token cannot be verified, ensure the request never proceeds as authenticated. Failing closed on **access control** does not require every upstream outage to return the exact same HTTP status code. Systems can design 503/500 responses and proper alerting; the goal is to **never accept unverified credentials**.

| Error layer | Symptom | Action |
|---|---|---|
| Client → API missing token | Request lacks Bearer header | Require client to send an access token |
| Client → API inactive token | Introspection HTTP 200, `active=false` | Reject token; client must obtain a valid token |
| Client → API missing scope | Introspection active, missing `SCOPE_*` | Reject at authorization |
| API → AS unauthorized | Introspection HTTP 401/403 | Fix introspection client registration/secret/policy |
| API → AS connectivity error | DNS, TLS, timeout, gateway 502, AS 5xx | Inspect infrastructure, timeouts, resilience |
| API accepts token meant for another resource | Introspection lacks resource binding | Add agreed audience/policy validation |

## 12. Latency, Timeouts, Caching, and Resilience

With standard introspection configuration, every API request needing Bearer authentication can trigger **an HTTP call to the Authorization Server**. Under high concurrency, introspection calls scale rapidly and impact:

- **API Latency**: adds network, TLS, and Authorization Server processing time.
- **Availability**: the API depends on introspection endpoint availability.
- **Capacity**: the Authorization Server must handle traffic from all Resource Servers.
- **Cost**: can increase network and IdP infrastructure costs.
- **Revocation freshness**: revoked tokens can be caught promptly if introspection is uncached and the AS updates state immediately.

### 12.1. Configuring Timeouts and Bounded Retries

A custom introspection HTTP client must set **connect timeouts**, **response/read timeouts**, and a bounded retry policy. Never allow requests to hang indefinitely when the AS is unresponsive. Unlimited retries across all errors during an IdP outage can trigger a **retry storm**, worsening the incident.

Note that `introspection-uri`, `client-id`, and `client-secret` only define **where to call and how to authenticate**. They do not cover timeouts, connection pools, proxies, retries, or circuit breakers. Those settings depend on your framework version and how the underlying HTTP client/introspector is configured.

### 12.2. Should You Cache Introspection Results?

Caching reduces latency and cost, yet delays detection of revoked tokens. Any cache design must explicitly decide:

| Aspect | Considerations |
|---|---|
| Cache key | Safely represent the token; avoid logging or exposing raw tokens |
| TTL | Never exceed remaining `exp`; balance revocation lag per policy |
| Inactive tokens | Whether to cache negative responses and for how long |
| Permission/tenant changes | Can metadata go stale when scopes or user status change? |
| Cached data | Tokens, principals, and metadata are sensitive; enforce read access and protection |
| Multi-issuer/resource | Never share results across differing policies or introspection sources |
| Cache outage | When cache or AS is unavailable, never assume tokens are active |

**Do not assume Spring Security caches introspection responses for an arbitrary duration by default.** If caching is added, document it explicitly in the operational contract; in particular, never cache `active=true` beyond token expiration or acceptable revocation lag.

### 12.3. Observability Without Leaking Tokens

Useful operational metrics:

- Introspection request volume over time broken down by active/inactive/error.
- Introspection endpoint p50/p95/p99 latency and timeout rate.
- Introspection client authentication failure rate (upstream 401/403).
- DNS/TLS/network errors separated from inactive-token rejections.
- API 401/403 counts categorized by cause **without containing credentials**.
- Secret rotation counts, endpoint changes, and policy updates.

To correlate logs, use valid request IDs/trace IDs and non-sensitive metadata. **Never log raw access tokens, refresh tokens, Basic headers, or client secrets.** Even token hashes need clear access policies and purpose to avoid inadvertently creating user-tracking identifiers.

## 13. Testing Introspection Configuration and Contract

A thorough Resource Server test suite should cover:

| Scenario | Introspection response / input | API expectation |
|---|---|---|
| Valid token, sufficient scope | `active=true`, `scope="orders.read"` | Proceeds into GET business logic |
| Nonexistent token | `active=false` | `401`, protected controller not invoked |
| Expired / revoked token | AS returns inactive per policy | `401` |
| Active token, missing scope | `active=true`, only `orders.create` | `403` when GET requires `orders.read` |
| Active token, wrong/missing audience | `aud` missing or `billing-api` | Rejected if policy requires audience |
| Active token, wrong tenant | Tenant claim/metadata mismatches resource | Rejected per business policy |
| Wrong introspection credentials | AS returns `401/403` | API request rejected; operational alert raised |
| Introspection endpoint unresponsive | Timeout/DNS/TLS | Fail closed on access control, raise alert |
| Malformed introspection JSON | Parse error | No valid principal created |
| AS returns `active=false` with HTTP 200 | HTTP transport succeeded, token inactive | Authentication still rejected |
| Request without Bearer token | No AS call needed | Protected API returns `401` |
| Public request without token | No introspection needed per policy | Allowed through `permitAll` endpoint if configured |

### 13.1. Testing Authorization Rules with Spring Security Test

For Spring MVC, `spring-security-test` provides the `opaqueToken()` request post processor to simulate an authenticated principal. Illustrative example:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Inside a test configured with MockMvc and GET /api/orders/42 mapping:
mockMvc.perform(get("/api/orders/42")
        .with(opaqueToken().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )))
    .andExpect(status().isOk());
~~~

To compile this snippet, import `org.springframework.security.core.authority.SimpleGrantedAuthority` and set up a matching test controller/context. Mock-token tests verify **URL/scope rules**, yet **do not prove the Resource Server called the right introspection endpoint or used the right credentials**: the post processor simulates authentication without invoking the real endpoint.

To test introspection integration, use a test HTTP stub/server for the AS endpoint, assert the `POST` request with the `token` form field and introspection client authentication, and simulate `active=true/false` JSON payloads and upstream errors. For WebFlux, use `WebTestClient` and its corresponding security test support; keep authorization logic tests distinct from real HTTP interaction tests.

### 13.2. Why You Should Not Test Only with Real Tokens

A handful of manual access tokens cannot prove that:

- Introspection credentials are read correctly across every environment.
- Policies handle `aud`, issuer, missing scopes, and tenant mismatches properly.
- Connections do not hang during IdP downtime.
- No credentials appear in logs or error responses.
- Caching, TTLs, and secret rotation behave per contract.

Include **negative test cases** and upstream failure tests alongside happy paths to avoid building an API that only works when the IdP behaves ideally.

## 14. Troubleshooting When Spring Boot Fails to Authenticate Opaque Tokens

| Symptom | Check first | Suggested fix |
|---|---|---|
| All requests return `401` | Did the client send `Authorization: Bearer`? | Inspect the actual HTTP request; do not substitute URL query params |
| API never calls introspection despite properties | Does the security chain enable `opaqueToken()` on the right runtime? | Verify Servlet vs. WebFlux, security bean, request matchers |
| Introspection returns `401` for every token | Are client ID/secret valid and active? | Check introspection permissions, auth method, and secret manager |
| Introspection endpoint returns `404` | Is `introspection-uri` the official path? | Cross-check provider metadata/documentation |
| Token is active yet API returns `403` | Is `scope` returned and mapped to `SCOPE_*`? | Inspect authorization rules and scope metadata |
| Token from another API also authenticates | Is audience/resource binding enforced? | Add Resource Server policy/validator |
| Same token succeeds intermittently | Network, AS cluster, revocation/caching, clock/TTL | Check distributed observability and consistent policies |
| WebFlux slow, event loop blocked | Does a custom introspector use a blocking HTTP client? | Switch to reactive I/O and set proper timeouts |
| API works locally, fails in production | Secret/URI/TLS trust/proxy differences across environments | Check deployment configuration and secure connectivity |
| Browser reports CORS before GET reaches API | Preflight OPTIONS blocked | Configure CORS properly before security; preflight carries no Bearer |
| All requests fail after rotating secret | API still uses the old secret | Synchronize secret rollout/restart/reload per design |

### 14.1. `401` from the API vs. `401` from the Introspection Endpoint

This is a common confusion:

~~~text
Client --(Bearer token)--> Orders API
   <-- 401 Unauthorized    |    missing / invalid token

Orders API --(client-id + secret, POST token)--> AS Introspection
   <-- 401 Unauthorized                          |    introspection caller unauthorized
~~~

In the second case, the end-user client cannot resolve the error by endlessly rotating access tokens if the Resource Server has lost introspection authorization. The fix belongs in **API / Authorization Server configuration**.

### 14.2. Browser CORS Preflight

Cross-origin JavaScript requests with an `Authorization` header typically trigger an **OPTIONS preflight** carrying no Bearer token. If Spring Security blocks the preflight before CORS runs, the browser reports a CORS error even when the introspection URL and token are completely valid. Configure allowed origins, methods, headers, and CORS integration ordering properly; never disable API authentication just to let preflight pass.

## 15. Essential Security Constraints

Introspection makes the Resource Server rely on the Authorization Server to validate credentials. Therefore:

1. **Always use HTTPS** for both the introspection endpoint and the Resource Server API.
2. **Trust only pre-configured/approved endpoints.** Never take introspection URLs from untrusted caller headers or tokens.
3. **Protect the client secret** via a secret manager or access-controlled environment variables; never store it in source code.
4. **Scope down introspection client privileges** so the AS only returns data necessary for the Resource Server.
5. **Validate scopes, audience/resource, and tenant** per contract after introspection; `active=true` alone is not enough for every request.
6. **Never log tokens or Basic Authorization headers.** Only log error codes, request IDs, and allowed metrics.
7. **Fail closed** when a token cannot be verified; an AS outage must never bypass authentication.
8. **Enforce timeouts, bounded retries, rate limits, and caching controls** to avoid exhausting API or IdP connections.
9. **Distinguish access tokens from ID tokens and refresh tokens.** The API must not accept other token types as Bearer access tokens.
10. **Manage contract changes** when updating introspection URIs, client authentication methods, secrets, scope naming, or resource-binding claims.

### Self-Check Questions

**Q1.** Through which header does the Resource Server receive an opaque access token from the client?

~~~http
Authorization: Bearer <ACCESS_TOKEN>
~~~

**Q2.** What does the Resource Server send to the introspection endpoint in a standard default configuration?

An HTTP `POST` form-urlencoded request containing the `token` parameter and the **introspection client's** credentials, typically HTTP Basic with `client-id` and `client-secret`.

**Q3.** Does HTTP 200 from the introspection endpoint mean the token is valid?

**No.** You must inspect `active`. An `{"active":false}` response still normally uses HTTP 200.

**Q4.** Why might an active token cause the API to return `403`?

The token authenticated successfully, yet the principal lacks the required scope/authority or fails a business policy.

**Q5.** Can you assign a user's access token directly to `spring.security.oauth2.resourceserver.opaquetoken.client-secret`?

**No.** That secret is the Resource Server's own credential for authenticating to the introspection endpoint. The access token is the business request's credential.

**Q6.** If introspection times out, can the request proceed to avoid disruption?

**No.** Without verifying the token, no valid authentication can be established. The system must reject the request and handle the infrastructure error appropriately.

## 16. Configuration Recap

Basic configuration consists of three settings:

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

And one directive enabling opaque tokens:

~~~java
// Servlet / HttpSecurity:
.oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(withDefaults()))

// WebFlux / ServerHttpSecurity:
.oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(withDefaults()))
~~~

**Both Java lines are DSL snippets placed inside their respective builders**, not standalone Java statements. Servlet and WebFlux use different security chain classes, while the introspection connection properties keep the same structure.

In a complete request lifecycle, Spring Security extracts the access token from `Authorization: Bearer ...`, sends it to a **trusted** introspection endpoint alongside the Resource Server's credentials, accepts only matching active results, and verifies scopes and policies before handing off to business logic. **Introspection endpoint/credentials**, **token active/metadata**, and **API authorization** are three parts that must be configured and operated together.

## References

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [Spring Security — Servlet OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security — Servlet Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security — Reactive Bearer Tokens](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/bearer-tokens.html)
- [Spring Security — Servlet CORS Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
