# How Does a Resource Server Differ in Responsibility from an OAuth2 Client and an Authorization Server?

In an OAuth 2.0 system, the **Resource Server**, **OAuth2 Client**, and **Authorization Server** are three *roles* with distinct responsibilities. Clearly distinguishing these three roles answers critical design questions: who logs users in, who issues access tokens, who carries tokens to call APIs, and who decides whether an API request may access data.

In Spring Security, configuring `oauth2ResourceServer()`, `oauth2Login()/oauth2Client()`, and an Authorization Server addresses different parts of this flow. A single application can assume multiple roles, yet that does not merge their responsibilities into one.

## 1. Overview of the three roles

Suppose a retail system has:

- **Shop Web**: the application users use to view their orders.
- **Identity Server**: where users authenticate and the application requests access.
- **Orders API**: the service holding order data and exposing `GET /api/orders/42`.

In this scenario:

| OAuth 2.0 role | Example component | Core responsibility |
| --- | --- | --- |
| **OAuth2 Client** | Shop Web | Requests access, obtains/manages access tokens via an appropriate grant, and **sends tokens** when calling APIs. |
| **Authorization Server (AS)** | Identity Server | Authenticates principals when required by the flow; handles authorization and **issues tokens** to clients. |
| **Resource Server (RS)** | Orders API | **Protects resources/APIs**: accepts access tokens, verifies validity, and checks permissions before returning data. |

**Resource Owner** (typically the user who owns the data) is another role in the OAuth model. Users interact with the Client and the Authorization Server, though the user themselves is not one of the three server/client roles being compared.

A typical Authorization Code with PKCE flow:

~~~mermaid
sequenceDiagram
    actor U as User
    participant C as OAuth2 Client (Shop Web)
    participant A as Authorization Server
    participant R as Resource Server (Orders API)

    U->>C: Open application / request to view orders
    C-->>U: Redirect to Authorization Server
    U->>A: Log in, approve consent when required
    A-->>C: Return authorization code via redirect
    C->>A: Exchange code for token (with PKCE)
    A-->>C: Access token (+ ID token if using OIDC)
    C->>R: GET /api/orders/42 + Bearer access_token
    R->>R: Verify token, scope, and order permissions
    R-->>C: Data or 401/403 error
    C-->>U: Display result
~~~

The diagram above depicts a user-involved scenario. With the `client_credentials` flow between services, a Client can obtain a token directly from the Authorization Server without a user login step; the Resource Server still performs its responsibility of validating tokens and protecting the API.

## 2. Resource Server: accepting tokens to protect resources

**A Resource Server is the API/service that owns protected resources**, such as orders, customer profiles, or internal documents. A request to a Resource Server typically contains:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer eyJ...
~~~

Conceptually, the Resource Server must:

1. **Extract the access token** from the request, most commonly from the `Authorization: Bearer ...` header.
2. **Validate the token** according to the system's chosen format/mechanism: signature, issuer, expiration, and audience for JWTs; or query the Authorization Server via introspection for opaque tokens.
3. **Convert authentication info into a principal/authorities**—for example, the `orders.read` scope becomes the `SCOPE_orders.read` authority under Spring Security's default JWT configuration.
4. **Check permissions at the API and specific data level**: is the caller allowed to read orders, and does that order belong to an authorized tenant/user?
5. **Return the resource or deny access**. Typically, a missing or invalid token results in HTTP 401; a valid token lacking sufficient permissions results in HTTP 403.

The Resource Server **is not responsible for issuing access tokens** or directing users to login screens. It can learn the caller's identity from verified claims, which is different from running login flows itself, collecting passwords, or issuing login sessions for a user-facing application.

### What must the Resource Server trust?

When using JWTs, the Resource Server must trust **configured keys/issuers**, not simply trust the JSON contents inside the token. Anyone can decode a JWT's payload; being able to read claims does not prove the token was issued by the right Authorization Server.

Common checks:

| Check | Meaning |
| --- | --- |
| Signature and algorithm | The JWT was validly signed by a trusted key, rejecting algorithms outside policy. |
| `iss` (issuer) | The token came from an allowed Authorization Server. |
| `exp`, `nbf` | The token has not expired and is already active; may account for reasonable clock skew. |
| `aud` (audience) | The token was issued for this API, avoiding misuse of tokens meant for other APIs. |
| Scope/authority | The token permits the category of action required by the endpoint, e.g. `orders.read`. |
| Business permissions | The caller may only access orders or tenants they are permitted to reach, even with a valid scope. |

Verifying the JWT is a necessary condition for trusting its claims, yet **a valid JWT does not automatically grant access to every resource**. Checking scopes and object permissions is the authorization part belonging to the Resource Server.

### JWT vs. opaque tokens: same responsibility, different verification

| JWT access token | Opaque access token |
| --- | --- |
| May contain readable claims; Resource Server verifies the signature using trusted public keys/JWK. | A reference string; Resource Server typically calls an **introspection endpoint** to retrieve token status/attributes. |
| Can be verified locally after fetching/updating the appropriate keys. | Depends on reachability of the introspection endpoint (or caching if applied by the system). |
| Early revocation is not automatically reflected solely by checking signature and `exp`. | Introspection can return an inactive status per Authorization Server policy. |
| Still requires checking issuer, expiration, audience, and permissions per design. | Still requires checking active status, client/subject/scope, and intended usage per design. |

**Whether a token is JWT or opaque does not determine the service's role**: if a service accepts access tokens to protect an API, it is acting as a Resource Server.

## 3. OAuth2 Client: requesting and using access rights

**An OAuth2 Client is an application that requests authorization to call a protected resource.** For example, Shop Web wants to read orders on a user's behalf; it uses a grant supported by the Authorization Server to obtain an access token, then sends that token to the Orders API.

Depending on application type and flow, an OAuth2 Client may:

- Redirect users to the Authorization Server for authentication and authorization, handle callbacks and authorization codes, and use PKCE when appropriate.
- Exchange an authorization code or use `client_credentials` to obtain an access token.
- Store token material securely, attach access tokens to requests sent to Resource Servers, and obtain new/refreshed tokens when allowed.
- Attach access tokens to outbound HTTP calls, such as when the Shop Web backend calls the Orders API using `WebClient`.
- If using **OpenID Connect (OIDC)** for login, receive and validate the **ID token** per OIDC rules, then establish the application's login state.

Crucially, the Client **does not decide whether a token is valid for the Orders API**. The Client can send requests with a token, yet the Resource Server must verify it itself. The Authorization Server is what issues tokens; Clients do not mint trustworthy access tokens themselves.

### OAuth2 Client and OIDC login are not the same concept

**OAuth 2.0** primarily solves *resource access authorization*; **OpenID Connect** adds an *identity authentication* layer on top of OAuth 2.0. Consequently:

- An **access token** is meant for calling a Resource Server; its target audience and permissions are defined by the API's design.
- An **ID token** is meant for the **OIDC Client** to know the outcome of user authentication; its audience is typically `client_id`.
- An API must not accept an ID token in place of an access token just because the ID token is also a JWT containing `sub` or a username.
- An OAuth2 Client can operate without OIDC, such as a service calling another service using `client_credentials`.

In Spring Security, `oauth2Login()` focuses on interactive login via OAuth 2.0/OIDC and typically establishes a principal/session for a web application. `oauth2Client()` provides support for managing authorized clients/tokens for outbound calls to other services. They are related, yet serve different needs from `oauth2ResourceServer()`.

## 4. Authorization Server: issuing tokens based on authentication and policy

**The Authorization Server** is where Clients request access permissions and where tokens are issued. Depending on grant type and policy, an Authorization Server may:

- Identify the Client, validate `client_id`, client authentication method, and redirect URIs against configuration.
- Authenticate users when required; handle login and consent prompts where appropriate.
- Receive/validate authorization requests, authorization codes, PKCE, and supported grants.
- Evaluate granted scopes and **issue access tokens**; optionally issue refresh tokens; and if supporting OIDC, issue **ID tokens**.
- Publish metadata, public keys (JWKS), and support introspection/revocation depending on implementation capabilities.
- Manage token lifecycles and policies concerning Clients, users, scopes, and audiences.

The Authorization Server generally **does not own the business rule** for "may order 42 be displayed?". It can grant the `orders.read` scope, yet the Orders API still has to check access rights for the specific order.

Nor is the Authorization Server synonymous with "logging in". In `client_credentials`, it can issue an access token after authenticating the **Client**, with no end user logging in at all.

**Spring Authorization Server** or a dedicated Identity Provider can fulfill this role. Simply adding Resource Server configuration to a Spring Boot application **does not turn it into an Authorization Server** and does not create a `/oauth2/token` endpoint to mint tokens.

## 5. Comparison table: who is responsible for what?

| Task | OAuth2 Client | Authorization Server | Resource Server |
| --- | --- | --- | --- |
| Initiates authorization/token request flow | **Yes** | Receives, processes | No |
| Authenticates user during login flow | Redirects/receives outcome | **Yes**, directly or via integrated authentication | Not primary function |
| Issues and signs access tokens | No | **Yes** | No |
| Sends access token when calling API | **Yes** | Not primary role | **Receives** token |
| Validates access token before serving API | Does not decide for API | Provides keys or introspection by design | **Yes** |
| Enforces endpoint scopes | May request scopes | Grants permitted scopes | **Yes** |
| Checks permissions on individual business records | Does not decide for API | Usually no | **Yes** |
| Manages tokens when calling other APIs | **Yes** | Issues/refreshes per policy | Usually no |
| Returns data from business endpoints | Typically displays or consumes data | Usually no | **Yes** |
| Handles ID token in OIDC | Receives, verifies for login | **Issues** | Never uses as access token |

"Yes" and "No" in the table indicate **role responsibilities**, not mandatory boundaries on deployment process count. A system can co-locate multiple roles within one application, or a single application can act as a Resource Server for inbound API calls and an OAuth2 Client for outbound API calls.

## 6. Example Resource Server implementation with Spring Security

Suppose the Orders API uses **JWT access tokens** issued by an existing Authorization Server. With Spring Boot, add the Resource Server dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Configure the issuer of the token authority:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/shop
~~~

When using `issuer-uri`, Spring Security can use the issuer's metadata to discover the appropriate public keys and validate JWTs with default checks, including signature, timestamps, and issuer. Validating the **expected audience for this API** should be explicitly configured according to your system's security requirements; never assume every token from the same issuer is intended for the Orders API.

Example requiring corresponding scopes for read/write operations:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

This snippet illustrates an **API that accepts only Bearer tokens**, so the example disables CSRF and uses stateless sessions. If the same application also serves a website with cookie-based login, evaluate CSRF, sessions, and a separate `SecurityFilterChain` scope for that flow; never blindly copy API settings across an entire website.

For JWTs with a standard `scope` or `scp` claim, Spring Security by default maps scopes to authorities prefixed with `SCOPE_`. For instance, the `orders.read` scope maps to `SCOPE_orders.read`. If the Authorization Server uses different claims or conventions, configure authority mapping accordingly.

Test invocation:

~~~bash
curl -i https://orders.example.test/api/orders/42 \
  -H "Authorization: Bearer $ACCESS_TOKEN"
~~~

With this API, typical outcomes are:

| Request | Typical outcome |
| --- | --- |
| Missing token, or expired/invalid-signature token | **401 Unauthorized**; Resource Server cannot authenticate the caller. |
| Valid token, but missing `orders.read` scope | **403 Forbidden**; caller has not been granted permission to call the endpoint. |
| Valid token with `orders.read`, but order 42 belongs to someone else | **403 Forbidden** or **404 Not Found** depending on resource non-disclosure policy. |
| Valid token, sufficient scope, and sufficient business permissions | **200 OK** with data if the order exists. |

Scope checks in the filter chain are only the **first layer of verification**. For example, `hasAuthority("SCOPE_orders.read")` does not check ownership of `orderId = 42` on its own; there must be additional business logic, protected methods, or object-level authorization policies.

### If the access token is an opaque token

The application remains a Resource Server but switches to introspection, for example:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: https://identity.example.test/oauth2/introspect
          client-id: orders-api
          client-secret: "${INTROSPECTION_CLIENT_SECRET}"
~~~

And configure `oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(Customizer.withDefaults()))`. The introspection endpoint and authentication method must match your actual Authorization Server. These are token verification credentials for the API, **not credentials for the Orders API to issue tokens itself**.

## 7. Client-side and Authorization Server-side examples

On the Shop Web side, dependencies and configuration serve a different purpose:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

~~~java
@Bean
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/", "/assets/**").permitAll()
            .anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults())
        .oauth2Client(Customizer.withDefaults())
        .build();
}
~~~

This is an **illustration of the web application's security part**; to run in practice, you must configure `ClientRegistration` (issuer, `client-id`, grant/redirect URI, secret if confidential) and a mechanism using the authorized client to attach access tokens to requests sent to the Orders API. `oauth2Login()` does not automatically grant access to the Orders API; that API still needs its own Resource Server configuration.

On the Authorization Server side, the Identity Server must configure client registrations, grants and scopes, signing keys/token formats, and required endpoints. It can be implemented with **Spring Authorization Server** or another Identity Provider. Regardless of product, the fundamental integration contract is:

- The Client knows **client registration, authorization/token endpoints, issuer**, and how to request tokens.
- The Resource Server knows **issuer/public keys or introspection**, audience rules, and how to interpret scopes/claims.
- The Authorization Server knows **which Clients may request which permissions** and how to issue tokens trusted by the other parties.

## 8. One application can be both a Client and a Resource Server

Consider **Backend A**:

1. Receives `GET /api/profile` with an access token from a mobile app. For this inbound request, Backend A acts as a **Resource Server**.
2. Backend A needs to query the **Reporting API** and uses `client_credentials` to obtain an access token intended for the Reporting API. For this outbound request, Backend A acts as an **OAuth2 Client**.
3. The Identity Server issues the token to Backend A's Client and publishes verification info for the Reporting API. It acts as the **Authorization Server**.

This is valid. However, the inbound request's token **is not automatically permitted to be forwarded** to the Reporting API: you must consider audience, scope, how principals are represented, and delegation/token exchange mechanisms if business logic requires acting on the user's behalf. Each API validates tokens intended specifically for itself.

Similarly, a single deployment might both host token-issuance endpoints and protect its own management API. In that case, that component fulfills **two distinct roles**; never assume every endpoint on an Authorization Server is automatically a Resource Server.

## 9. Common misconceptions

**"The Resource Server handles OAuth2 login."** With Bearer tokens, a Resource Server normally only validates the received token and sets up `Authentication` for API requests. Redirecting users to log in and completing OIDC login belong to the Client and Authorization Server.

**"The Resource Server issues its own JWTs, so no Authorization Server is needed."** An API can certainly implement its own authentication and token issuance mechanism, yet once it issues tokens, it takes on the additional responsibility of *token issuance*. In OAuth 2.0 architecture, that is no longer purely the Resource Server role.

**"Having a JWT with a valid signature means reading data is allowed."** A validly signed JWT must still match the issuer, timestamps, audience, and required constraints. After authentication, the Resource Server must check authorities/scopes and business permissions on the data.

**"ID tokens and access tokens are both JWTs, so they can be used interchangeably."** An ID token proves authentication results to an OIDC Client; an access token is the credential for calling a Resource Server. The two tokens have different audiences and purposes.

**"Only human users use OAuth2."** With `client_credentials`, a service can also be a Client. The Resource Server validates the access token representing the Client and grants only the permitted access.

**"If the Resource Server sees the scope, it is definitely safe to return every record."** Scopes typically express operation-level permissions at the API level. Per-user/tenant/owner permissions, record states, or organizational policies still need separate checks.

**"Logging out or revoking a token on the Authorization Server invalidates all JWTs immediately."** With locally verified JWTs, a Resource Server may continue accepting unexpired tokens unless additional revocation mechanisms are in place. Choose token lifetimes, introspection, or revocation strategies that fit business requirements.

## 10. How to identify roles when designing a system

When you encounter a component in a diagram, ask:

1. **Does it request and send access tokens to call another API?** → It is acting as an **OAuth2 Client**.
2. **Does it authenticate/authorize and issue access tokens to Clients?** → It is acting as an **Authorization Server**.
3. **Does it receive access tokens to decide whether to return data or execute business logic?** → It is acting as a **Resource Server**.

With Spring Security, the practical mapping is:

| Role to build | Common Spring mechanism | Configuration questions to answer |
| --- | --- | --- |
| Resource Server | `spring-boot-starter-oauth2-resource-server`; `oauth2ResourceServer().jwt()` or `opaqueToken()` | Which issuer/keys to trust, which audience tokens must target, and how to check authorities and data permissions? |
| OAuth2 Client | `spring-boot-starter-oauth2-client`; `oauth2Login()` and/or `oauth2Client()` | Where is the Client registered, which grant is used, and how are tokens obtained/stored and attached to requests? |
| Authorization Server | Spring Authorization Server or Identity Provider | Which Clients may use which grants/scopes, how authentication works, and how tokens are issued/signed and published? |

**The decisive distinction:** The Authorization Server **grants** permissions in token form; the OAuth2 Client **requests and carries** tokens for use; the Resource Server **verifies and enforces** those permissions when protecting actual resources. Separating these three questions from the start helps design clean trust boundaries, configure Spring Security for the right purpose, and avoid confusing OIDC login with OAuth 2.0 API protection.
