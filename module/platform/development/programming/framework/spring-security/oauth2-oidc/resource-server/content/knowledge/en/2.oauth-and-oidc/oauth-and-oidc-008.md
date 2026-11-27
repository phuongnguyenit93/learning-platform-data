# Resource Server Does Not Issue New Tokens or Refresh Client Tokens

In an **OAuth 2.0 and OpenID Connect (OIDC)** architecture, the **Resource Server** is the service exposing resources protected by access tokens. It validates the access token attached to a request, checks access permissions, and returns the API response. When a token is expired or invalid, the Resource Server must reject the request; it **does not mint new access tokens, exchange refresh tokens, or issue replacement tokens for the client**.

This is a critical boundary when building APIs with **Spring Security OAuth 2.0 Resource Server**. Validating an incoming request's token is fundamentally different from obtaining tokens for outgoing requests or renewing access on a user's behalf.

## 1. Who is responsible for the token lifecycle?

Consider a system where a web application calls an Orders API:

| Role | Example | Primary responsibility |
| --- | --- | --- |
| **Resource Owner** | User who owns the orders | The authority over resource access rights in the system's model |
| **Client** | Web app, mobile app, backend/BFF | Requests access tokens, sends them to APIs, and requests new tokens when needed |
| **Authorization Server** | Keycloak, OAuth 2.0/OIDC provider, Spring Authorization Server | Processes authorization requests and issues access tokens; handles refresh grants when supported |
| **Resource Server** | Orders API using Spring Security Resource Server | Receives bearer access tokens, validates them, and enforces API access control |

A system can implement multiple roles within a single application; the table above describes **logical roles**, not necessarily four physical servers. The fact that an API can access the Authorization Server's metadata or JWKS does not turn it into a token-issuing system.

~~~text
                   Request token / refresh
    +----------+ --------------------------> +----------------------+
    |  Client  | <-------------------------- | Authorization Server |
    +----------+        Access token         +----------------------+
         |
         | HTTP Authorization: Bearer <access-token>
         v
    +-----------------+
    | Resource Server |
    | - Validate token|
    | - Check perms   |
    +-----------------+
         |
         +------> 200 OK / 401 Unauthorized / 403 Forbidden
~~~

**Foundational rule:** The Resource Server **consumes/validates access tokens**; the Authorization Server **issues tokens**; the Client **manages obtaining and using tokens**.

## 2. How does a Resource Server process a request?

A client sends a request to the API:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <access-token>
Accept: application/json
~~~

In a Spring Security Resource Server application, processing typically proceeds as follows:

1. **Extract the bearer token** from the `Authorization` HTTP header.
2. **Validate the token.** For JWTs, the API checks signature, issuer, lifetime, and other configured claims; it must check audience to ensure the token targets this API. For opaque tokens, the API can use token introspection provided by the issuer.
3. **Establish the authentication context** for the request, such as `JwtAuthenticationToken` and authorities mapped from valid scopes/claims.
4. **Check permissions**: endpoint permissions, HTTP method, and business-level permissions on the record, tenant, or owner.
5. **Return data or reject the request** depending on the outcome.

The Resource Server **does not** need the client's refresh token to perform those five steps. Nor does it extend the `exp` claim itself, sign a new JWT, call the token endpoint on the client's behalf, or convert an expired bearer token into a valid one.

### Validating a JWT is not refreshing a token

A JWT typically contains information such as:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
~~~

This is an illustrative payload, **not a complete token**. `exp` is the expiration timestamp; `iss` is the issuer; `aud` indicates the intended audience. The Resource Server may only accept the JWT when all required validations succeed. Being able to Base64-decode the payload does not prove the signature is valid.

If a token has expired, fetching fresh public keys from JWKS by the API **does not renew that JWT**. JWKS exists for signature verification, not access token issuance. Nor may the API edit `exp` itself and treat the token as issued by the Authorization Server.

### Introspection is also not refreshing

With an opaque token, the Resource Server can ask the introspection endpoint whether the token is currently `active`, along with necessary attributes. The answer only concerns **the status of the token being checked**. If the token is no longer active, the API rejects the request; introspection never mints a new token.

## 3. Expired access token: the proper handling sequence

Suppose the client already has access token A, but it expires before calling the Orders API:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant RS as Resource Server
    participant AS as Authorization Server

    C->>RS: GET /api/orders + access token A (expired)
    RS->>RS: Validate token, detect expiration
    RS-->>C: 401 Unauthorized (invalid_token)
    Note over RS: Does not issue or refresh tokens
    C->>AS: Request new token using a supported grant
    alt Token issuance permitted
        AS-->>C: Access token B
        C->>RS: Call API with Bearer token B
        RS->>RS: Validate B and check permissions
        RS-->>C: Data or appropriate error
    else Cannot issue token
        AS-->>C: Token endpoint error response
        Note over C: Handle session end / re-authorize
    end
~~~

Notes:

- **The Resource Server only rejects the current request**; it does not by default terminate the user's entire account or login session.
- **The Client proactively** requests a new token if an authorized mechanism is available.
- **The Authorization Server** decides whether to issue a new token based on the grant, policy, login state, lifetime, and client permissions.
- Token B, if issued, must **be validated again by the Resource Server**. A new token does not automatically grant the client access to every endpoint or every record.

With JWTs, the API normally validates signatures and claims locally. With opaque tokens, the API may consult introspection. This difference only changes **how** the access token is validated, not **who must refresh** it.

## 4. Meaning of HTTP 401 and 403

APIs using bearer tokens typically signal authentication/authorization errors via HTTP status codes and, where appropriate, `WWW-Authenticate`:

| Scenario | Typical response | How the client should interpret it |
| --- | --- | --- |
| No bearer token sent to an endpoint requiring authentication | **401 Unauthorized** | Request lacks authentication credentials |
| Access token expired, invalid signature, or rejected | **401 Unauthorized**, possibly with `invalid_token` | Current token is invalid; determine whether a new token can be obtained |
| Valid access token lacking required scope/permission | **403 Forbidden**, possibly with `insufficient_scope` | Token lacks permission; refreshing will not necessarily solve it |
| Subject has read scope but is not allowed to read a specific order | Usually **403**, or another code per business design | Object-level permission check failed; do not assume an expired token error |

Example response when a token is invalid:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Content-Length: 0
~~~

Example response when a scope is missing:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
Content-Length: 0
~~~

These responses are **illustrative**; entry points, access denied handlers, and application configuration affect actual headers/bodies. Also avoid exposing excessive sensitive details about why authentication failed.

**Do not design clients to refresh infinitely on every 401.** A 401 has many causes besides token expiration. Nor should clients automatically refresh on 403: if an account lacks `orders.write` or does not own the order, a fresh token with the same permissions will not change the outcome.

## 5. How does a client obtain a new access token?

### 5.1. Refresh token grant

If the Authorization Server issued a refresh token and permits its use, the client sends the refresh token to the **Authorization Server's token endpoint**:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<refresh-token>
~~~

This is an illustrative request; token endpoint path, client authentication, parameters, and credential transmission depend on the provider and client type.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant AS as Authorization Server
    participant API as Resource Server
    C->>AS: Token endpoint, grant_type=refresh_token
    AS->>AS: Validate refresh token, client, and policy
    alt Valid refresh
        AS-->>C: New access token (+ new refresh token if rotated)
        C->>API: Request with new access token
        API-->>C: Result per token and permissions
    else Invalid refresh
        AS-->>C: Error, e.g., invalid_grant
        Note over C: Re-authorize / re-login or report error
    end
~~~

A refresh token may have expired, been revoked, or never been issued. Some Authorization Servers use **refresh token rotation**: issuing a new refresh token and invalidating the previous one on each refresh. Under concurrent requests, the client must synchronize refreshing and store the new token to avoid reusing an old refresh token.

**Never send a refresh token to the Orders API.** It is a high-value credential intended only for the token endpoint. Having business APIs receive or store refresh tokens widens the secret exposure surface and blurs responsibilities.

### 5.2. Re-running the authorization flow

For user-login applications, if no valid refresh token is available, the client can start a new **Authorization Code flow**, typically with **PKCE**. The Authorization Server decides whether the user must log in or consent again.

Example: an SPA calling the Orders API receives 401 because its access token expired. The application manages token state client-side and initiates a new authorization flow when needed. The Orders API does not redirect the browser to the OIDC provider to fetch tokens on behalf of the SPA.

### 5.3. Client Credentials for machine-to-machine communication

A backend service can use the **Client Credentials** grant to request an access token on its own behalf. When the token expires, the service typically **requests a new access token using Client Credentials** rather than using a refresh token:

~~~mermaid
sequenceDiagram
    participant C as Reporting Service (Client)
    participant AS as Authorization Server
    participant RS as Inventory API (Resource Server)
    C->>AS: client_credentials
    AS-->>C: Access token A
    C->>RS: API request + Bearer A
    RS-->>C: Response
    Note over C: Token A expires
    C->>AS: Next client_credentials request
    AS-->>C: Access token B
    C->>RS: API request + Bearer B
    RS-->>C: Response
~~~

This flow requires no end user during each token issuance. The Resource Server still only receives and validates bearer access tokens.

## 6. Spring Security Resource Server configuration: what it includes and excludes

With Spring Boot and Spring Security for the Servlet stack, dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

A Resource Server configuration validating JWTs:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

`issuer-uri` specifies the trusted issuer for discovering metadata/verification keys and validating tokens. This configuration **does not create a token endpoint**, does not issue refresh tokens, and does not add OAuth2 Client functionality.

Example `SecurityFilterChain` protecting the API:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersApiSecurity {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
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

What this configuration means:

- `oauth2ResourceServer(...jwt(...))` enables Bearer JWT processing **on incoming API requests**.
- The Resource Server can validate tokens with a `JwtDecoder` and establish an `Authentication` to enforce authorization rules.
- In standard configurations, scope `orders.read` maps to authority `SCOPE_orders.read`; issuers using custom claims require custom mapping.
- `SessionCreationPolicy.STATELESS` fits APIs that do not rely on HTTP sessions for authentication.
- Disabling CSRF in the example is **only for pure Bearer-token APIs that do not use automatically attached auth cookies**. For applications with session cookies, evaluate and retain appropriate CSRF protection.
- `hasAuthority(...)` only protects endpoint/method-level access. The API must still verify that the user is permitted to access **that specific order record** and its corresponding tenant.

When a JWT expires, Spring Security rejects the token in the authentication layer. Nothing by default calls the issuer's token endpoint to obtain a new access token and continue into the controller as if the original request were valid.

### Inside the Resource Server filter pipeline

~~~text
HTTP Request / Authorization: Bearer <jwt>
                  |
                  v
    BearerTokenAuthenticationFilter
                  |
                  v
       JwtAuthenticationProvider
                  |
                  v
              JwtDecoder
                  |
         Validate token / JWT
                  |
                  v
         Valid Authentication
                  |
                  v
        Authorization rules
                  |
                  v
         Controller / Service
~~~

If validation fails, processing stops with the appropriate authentication error. If the token is valid but lacks permissions, processing is denied at the authorization step. **No step in the diagram above is a refresh token grant.**

With JWTs, the Resource Server should enforce all conditions required by its contract with the Authorization Server, especially **audience** when the API must only accept tokens intended for itself. A valid signature and matching issuer do not automatically prove a token was issued for every API.

### If the Authorization Server issues opaque tokens

The Resource Server can use introspection configured as:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: YOUR_INTROSPECTION_CLIENT_ID
          client-secret: YOUR_INTROSPECTION_CLIENT_SECRET
~~~

These are **placeholder values**. In production, use your issuer's real endpoint and retrieve credentials from a secrets manager. The API must configure `opaqueToken` mode instead of `jwt` to use introspection. Querying token status at the introspection endpoint still **does not** create a new token.

## 7. An application can be both a Resource Server and an OAuth2 Client

Consider an API Gateway/BFF or Service A that handles incoming requests while also calling Service B:

~~~text
Browser / another application
            |
            | Bearer token X
            v
        Service A
      /           \
     /             \
Resource Server   OAuth2 Client
validates token X requests or manages token Y
                       |
                       | Bearer token Y
                       v
                 Service B (Resource Server)
~~~

- **Token X** is for requests incoming to A. A's Resource Server side validates X and access rights to A.
- **Token Y** is for requests where A calls B. A's OAuth2 Client side can request and manage Y according to its configured grant.
- **Obtaining a new token Y** is behavior of the OAuth2 Client, **not** the Resource Server renewing token X.
- If **token relay** is used, A may forward token X only in cases genuinely permitted by token design and policy; never blindly forward a token scoped only to A's audience onto B. Token relay is not refreshing.

In Spring Security, components such as `OAuth2AuthorizedClientManager` and `OAuth2AuthorizedClientProvider` belong to **OAuth2 Client** support and can obtain/refresh tokens for outgoing API calls when configured, with an appropriate grant permitted by the Authorization Server. Meanwhile, `oauth2ResourceServer()` handles bearer tokens on incoming requests.

| Spring Security capability | Primary role |
| --- | --- |
| **OAuth2 Resource Server** | Validates access tokens, protects API endpoints |
| **OAuth2 Client / OAuth2 Login** | Participates in OAuth 2.0/OIDC flows, requests and manages client tokens, handles application login |
| **Spring Authorization Server** | Exposes authorization/token endpoints, issues tokens |

Merely adding the OAuth2 Client dependency does not guarantee tokens are automatically refreshed in every scenario. Actual behavior depends on authorized-client storage, client registration, provider/grant, a valid refresh token, and how the calling component is configured.

## 8. Does OIDC change token refresh responsibilities?

**No.** OIDC adds **end-user authentication** on top of OAuth 2.0, but it does not change how the Resource Server uses access tokens to protect APIs.

| Token | Purpose | Consumer |
| --- | --- | --- |
| **Access token** | Controls access to resources | Client sends to Resource Server |
| **ID token** | Contains details about the user authentication event for the OIDC client | OIDC client validates for login |
| **Refresh token** | Requests a new access token if issued and permitted | Client sends to Authorization Server |

**Never use an ID token in place of an access token when calling APIs. Never send a refresh token to a Resource Server.**

For example, a user logs in via OIDC at the Authorization Server. The application receives authentication details for its login session and an access token to call the Orders API. When the access token expires, the application performs the new-token acquisition flow or re-authenticates/re-authorizes if needed. The Orders API continues its role of receiving and validating access tokens without deciding how the application's OIDC session should be refreshed.

## 9. Common points of confusion

### "The API already configured `issuer-uri`, why doesn't it auto-refresh?"

`issuer-uri` helps the API identify the trusted issuer and fetch the metadata needed to **validate tokens**. It does not supply the client's refresh token, does not turn the API into an OAuth2 Client, and does not initiate `grant_type=refresh_token` requests.

### "The JWT expired—can the API update `exp` and re-sign it to keep using it?"

Never. Tokens are issued under the Authorization Server's keys and policies. Having a Resource Server re-mint tokens outside the designed mechanism breaks trust boundaries. To reduce how often users log in again, design access token and refresh token lifetimes properly between the client and Authorization Server.

### "The API calls the introspection endpoint—does that refresh the token?"

No. **Introspection** asks whether the current token is still accepted. **Refresh** is when the client requests a new token from the token endpoint under a specific grant and authorization policy.

### "If the response is 403, should we just refresh the token and retry?"

No. `403 Forbidden` typically reflects missing permissions, such as lacking `orders.write` or attempting to view someone else's order. A new access token with the same permissions will still be rejected.

### "Why can an old JWT still be accepted by the API after logout or revocation?"

With **offline**-verified JWTs, the Resource Server may not query the Authorization Server for revocation status on every request. An issued JWT can remain accepted until expiration if the API only checks signature, timestamps, and claims without an additional revocation mechanism. Near-immediate revocation requires dedicated strategies such as introspection, synchronized deny-lists, or short access token lifetimes. This is a **token validation and revocation** concern, not client token refreshing.

### "The client has a refresh token—does the API need to receive or store it?"

Normally no. The client protects the refresh token and exchanges it with the Authorization Server. The Resource Server needs data to **validate access tokens and authorize requests**, not hold the client's refresh secret.

### "Can one backend be both an Authorization Server and a Resource Server?"

Yes, if both roles are intentionally designed and implemented. However, when a backend issues tokens, that is **deliberate Authorization Server functionality**; enabling Spring Security Resource Server does not create token-issuing capability.

## 10. Handling expired tokens in production systems

**At the Resource Server:**

1. Validate token type, issuer, signature/status, lifetime, audience, and required authorization rules.
2. Return **401** when the request lacks valid authentication credentials; return **403** when properly authenticated but lacking permissions.
3. Never accept refresh tokens on business API endpoints, never re-sign JWTs, and never issue new tokens in place of the Authorization Server.
4. Log enough for diagnostics, but **never log raw access tokens, refresh tokens, or client secrets**.
5. Enforce per-resource permissions rather than relying solely on coarse scopes.

**At the Client:**

1. Track access token expiration when reliable metadata is available; request a new token proactively before expiration if appropriate.
2. If issued a refresh token, send it to the token endpoint per the Authorization Server's flow and policy. Otherwise, re-run the appropriate grant, such as Authorization Code + PKCE or Client Credentials.
3. When retrying a request after a 401, retry in a controlled manner with the new token; avoid infinite retry loops.
4. Synchronize concurrent refresh requests, especially when the Authorization Server enables refresh token rotation.
5. If refreshing fails, clear invalid token state and trigger re-login/re-authorization or return an appropriate error to the caller.

**At the Authorization Server:** manage token issuance, allowed grants, client authentication, token lifetimes, rotation, revocation, and re-authorization policies.

## 11. Summary by request type

| Request | Client | Authorization Server | Resource Server |
| --- | --- | --- | --- |
| OIDC login | Initiates/completes flow | Authenticates and issues tokens per policy | Not involved until an API request occurs |
| Renewing access token with refresh token | Sends refresh grant | Validates and issues new token if valid | Not involved |
| Service requesting token via Client Credentials | Sends matching grant | Authenticates client and issues access token | Not involved |
| Calling API with valid access token | Sends Bearer token | May not be involved per JWT request | Validates token and checks permissions |
| Calling API with expired access token | Receives error; decides to obtain new token | Only involved if client sends issuance/refresh request | Rejects request, typically with 401 |
| Calling API lacking scope or object permission | Handles insufficient-permission state | Only grants different permissions if allowed by flow/policy | Rejects operation, typically with 403 |

**Remember:** A Spring Security Resource Server rejecting an expired access token is **protecting the API as designed**. Obtaining a new access token belongs to the **Client and Authorization Server**; deciding whether the new token is allowed to access specific resources still belongs to the **Resource Server and business rules**.
