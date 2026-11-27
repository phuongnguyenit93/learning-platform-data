# 401/403 and TokenRelay Failing to Send the Expected Access Token

## 1. Context: Request Reaches the Gateway, Yet the Backend Still Rejects It

A client calls an API through **Spring Cloud Gateway (SCG)** and receives HTTP **401 Unauthorized** or **403 Forbidden**. The development team inspects the token on the client side and sees it looks valid, the route matched, yet the Catalog/Orders backend still reports a missing access token, wrong audience, or insufficient scope. In some cases the 401/403 response is generated right at the Gateway; in others it is **returned by the upstream backend and proxied back to the client by the Gateway**.

This class of bugs is easy to misdiagnose because the same status code can arise at multiple boundaries:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Spring Cloud Gateway
    participant IDP as OAuth2 Authorization Server
    participant B as Catalog / Orders
    C->>G: HTTP request + optional Bearer token
    Note over G: Spring Security authenticates / authorizes
    G->>IDP: Obtain / refresh access token (when OAuth2 Client needs one)
    IDP-->>G: Access token
    G->>B: Proxied request + Authorization: Bearer ...
    B-->>G: 200, 401 or 403
    G-->>C: Final response
~~~

A request can fail at **inbound authentication**, **Gateway authorization**, **OAuth2 client token acquisition**, **TokenRelay**, **outbound HTTP transport**, or **backend authorization**. Therefore, looking at 401/403 in a browser or Postman alone is not enough to conclude where the token was lost.

The lesson **"401/403 and TokenRelay Failing to Send the Expected Access Token"** belongs to the **Troubleshooting** chapter of the **SPRING_CLOUD_GATEWAY** module. Its goal is to pinpoint which token must travel across each hop, where the Gateway obtains the token, which audience/scope the backend expects, and which layer produced the response.

### After This Lesson, You Will Be Able To

1. Distinguish **401** from **403**, and determine whether the status came from the Gateway or upstream.
2. Distinguish three Spring Security roles: **OAuth2 Client**, **OAuth2 Login**, and **OAuth2 Resource Server**.
3. Explain why `TokenRelay` is not an arbitrary copier of any `Authorization` header.
4. Configure `TokenRelay` **without a clientRegistrationId** to relay the authorized client bound to an OAuth2-logged-in user.
5. Configure `TokenRelay=catalog-client` so the Gateway obtains a service access token from the appropriate registration, such as **client_credentials**.
6. Understand why an inbound JWT verified by Resource Server is not automatically an `OAuth2AuthorizedClient` that TokenRelay can look up.
7. Inspect OAuth2 registrations, authorized client repositories/services, principals, sessions, token expiry, issuer, audience, and scopes.
8. Detect which filter/header stripped, overwrote, or failed to forward the token.
9. Test using a backend stub, count requests, and verify upstream receives `Authorization` without writing real tokens to logs.
10. Build a runbook for 401/403 incidents that avoids forwarding tokens across wrong trust boundaries and restores service safely.

> **Primary scope:** Examples use **Spring Cloud Gateway Server WebFlux** and reactive Spring Security. Gateway Server Web MVC runs on Servlet/Spring MVC and has different HTTP client/filter configurations; never copy `SecurityWebFilterChain`, `WebFilter`, or reactive APIs into an MVC application. Cross-check property names and dependencies against your actual Spring Boot/Spring Cloud BOM.

## 2. Distinguish 401 and 403 Before Checking TokenRelay

By HTTP semantics, the two statuses describe different situations:

| Status | Typical Meaning | Question to Answer |
| --- | --- | --- |
| **401 Unauthorized** | Request lacks valid credentials or credentials were rejected; server often sends a `WWW-Authenticate` challenge | Does a token exist, with valid signature/issuer/audience and unexpired lifetime? |
| **403 Forbidden** | Server understood the request but refuses to fulfill it per permissions/policy | Principal is authenticated, yet is a scope/role/tenant/resource permission missing? |

The name "Unauthorized" for 401 is often misleading; think of it simply as **no accepted identity yet for the request**. 403 usually means **identity was established, but permissions are insufficient**, though real applications may assign statuses per their own policies.

### 2.1. A Request Can Receive 401 from Two Places

**401 at the Gateway:**

- Client omits the Bearer token while the route requires authentication.
- Token is expired, or has an invalid signature, wrong issuer, wrong audience, or is untrusted by the decoder.
- OAuth2 login session does not exist or the authorized client/token is no longer valid.
- Gateway lacks a valid token to call the token endpoint per registration.

**401 at the upstream:**

- Gateway sends the request without an `Authorization` header.
- Header contains a token with the wrong audience or issuer for Catalog.
- Token is expired, has a bad signature, or the backend does not trust the issuer/JWKS.
- Gateway mistakenly relayed an ID token, refresh token, or a token meant for a different API backend.

### 2.2. A Request Can Receive 403 from Multiple Policies

- Spring Security at the Gateway authenticated successfully, yet authorities are insufficient.
- CSRF protection rejects a state-changing request missing a CSRF token.
- Backend receives a valid token lacking a scope such as `catalog.read`.
- Backend enforces tenant/ownership checks and denies access to the resource.
- A WAF/API gateway/authorization proxy in front of SCG returns 403.

**Never disable CSRF, open `permitAll()`, or grant `ROLE_ADMIN` just to make a 403 disappear** before identifying which policy produced the response.

### 2.3. Status Code Alone Does Not Reveal Response Origin

An HTTP 401 from upstream can be passed straight back to the client by SCG. Hence the client seeing 401 **does not prove Spring Security Gateway blocked the request**. Compare:

- Gateway inbound request count and authentication/authorization outcomes.
- Gateway route ID and outbound attempt count.
- Backend request count and redacted backend authorization logs.
- Upstream HTTP status/exception and final client status.
- Trace/correlation IDs propagated across hops.

If backend request count is 0, the failure likely occurred before calling the backend. If the backend received the request and returned 401/403, inspect **the token actually arriving at the backend and the backend's policy**.

## 3. Four OAuth2 Roles Frequently Confused

Spring Security supports multiple OAuth2 roles. `TokenRelay` depends on **which role the Gateway is playing**.

| Role | Spring Security Component | Responsibility | Key Token / Object |
| --- | --- | --- | --- |
| **OAuth2 Client** | OAuth2 Client support | Gateway calls a token endpoint or uses an authorized client to access a resource server | `ClientRegistration`, `OAuth2AuthorizedClient`, access token |
| **OAuth2 Login** | `oauth2Login()` | User logs in via Authorization Code flow | `OAuth2AuthenticationToken` and authorized client bound to user |
| **OAuth2 Resource Server** | `oauth2ResourceServer()` | Gateway validates Bearer tokens sent by clients | `JwtAuthenticationToken` or opaque-token authentication |
| **Authorization Server / IdP** | External token-issuing system | Authenticates clients/users and issues access/refresh tokens | Token endpoint, issuer, JWKS, scopes, audience policy |

### 3.1. OAuth2 Client Differs from Resource Server

When Gateway is configured as a **Resource Server**, it can read `Authorization: Bearer <token>`, validate the JWT, and place an `Authentication` in the security context. That proves **the inbound token was accepted by the Gateway** under the configured validator.

However, this **does not automatically create an `OAuth2AuthorizedClient`** stored by `ClientRegistration` for OAuth2 Client/TokenRelay to retrieve. The two mechanisms serve distinct purposes:

- Resource Server validates incoming tokens.
- OAuth2 Client manages registrations, authorization grants, authorized clients, and tokens used when calling downstream.

Consequently, the symptom "Gateway accepted a valid JWT, yet TokenRelay could not find an access token" happens if you only configure Resource Server and expect `TokenRelay` to blindly copy the Bearer header upstream.

### 3.2. ID Token Is Not an Access Token

In OpenID Connect:

- **ID token** describes the authentication event and user identity for the client/OIDC relying party.
- **Access token** is issued to call resource servers/APIs with specific audiences/scopes.
- **Refresh token** is used to obtain a new access token, not as credentials sent to API backends.

`TokenRelay` forwards the appropriate **OAuth2 access token** from the authorized client. Never forward an ID token or refresh token to Catalog/Orders as a workaround for 401.

### 3.3. Access Tokens Must Target the Right Resource Server

A JWT with a valid signature can still be rejected by Orders if:

- `iss` is not in Orders' trust configuration.
- `aud` does not include the audience required by Orders.
- `exp` has passed or `nbf` is in the future (check clock skew).
- `scope`/`scp` lacks required permissions.
- `azp`, client identity, or tenant claims fail policy.
- The token is an ID token or intended for a different API.

**A token valid at the Gateway is not automatically valid at every backend.** Each resource server must verify issuer, audience, signature, expiration, and authorization per its own contract.

## 4. What Does TokenRelay Actually Do?

`TokenRelay` is a **Gateway filter factory** in Spring Cloud Gateway that uses OAuth2 Client support to retrieve the access token of an `OAuth2AuthorizedClient` and attach it to the upstream request as:

~~~http
Authorization: Bearer <access-token>
~~~

It has two primary modes of usage:

| Route Configuration | Selected Token | Typical Scenario |
| --- | --- | --- |
| `TokenRelay` | Authorized client bound to the user currently authenticated via OAuth2 login | Delegation for a logged-in user |
| `TokenRelay=catalog-client` | Authorized client for `ClientRegistration` with ID `catalog-client` | Gateway obtains a service token, commonly using `client_credentials` |

**Do not assume `TokenRelay` always relays whatever Bearer token happens to sit in the request header.** In particular, an inbound `JwtAuthenticationToken` from Resource Server is not implicitly equivalent to an `OAuth2AuthenticationToken` with a persisted authorized client.

### 4.1. TokenRelay Without a Registration ID

When using:

~~~yaml
filters:
  - TokenRelay
~~~

Gateway uses the **OAuth2-logged-in user** and the authorized client matching that user's registration to relay the access token. Typical flow:

1. User is redirected to the IdP via the OAuth2 Authorization Code flow.
2. After the callback, Spring Security creates user authentication and an authorized client holding the access token.
3. User calls a route needing downstream access.
4. TokenRelay fetches the access token from the authorized client bound to the current authentication.
5. Gateway sends the request to the backend with the Bearer access token.

If the application only verifies inbound Bearer JWTs via Resource Server without an OAuth2 login/authorized-client state, the filter cannot magically infer a token to relay.

### 4.2. TokenRelay With a Registration ID

When using:

~~~yaml
filters:
  - TokenRelay=catalog-client
~~~

Gateway specifies the exact **ClientRegistration ID** to use. The OAuth2 Client manager uses that registration and appropriate principal/context to authorize or retrieve an authorized client, then supplies the access token on the outbound request.

With a `client_credentials` registration, Gateway obtains a token representing the **service/client application**. The backend normally sees the service identity rather than the end user. This fits when the backend only needs to identify which gateway service is calling.

### 4.3. Three Token Propagation Models

~~~mermaid
flowchart TD
    A["Inbound request"] --> B{"Which identity model does Gateway receive?"}
    B -->|"OAuth2 login user"| C["OAuth2AuthenticationToken"]
    C --> D["TokenRelay without registration ID"]
    D --> U["Upstream with user access token"]
    B -->|"Gateway calls with service identity"| E["ClientRegistration: client_credentials"]
    E --> F["TokenRelay=registrationId"]
    F --> V["Upstream with service access token"]
    B -->|"Inbound Bearer JWT / Resource Server"| G["JwtAuthenticationToken"]
    G --> H["TokenRelay is not a raw header copy"]
    H --> I["Controlled pass-through or token exchange design"]
    I --> W["Upstream with token for right audience"]
~~~

| Model | Who Does the Backend See? | When Is It Appropriate? |
| --- | --- | --- |
| User token relay | User/client identity per access token | Backend needs per-user permissions and IdP issues tokens with right audience |
| Service token relay | Gateway service/client | Backend only needs to authenticate the calling service; service privileges are scoped |
| Token exchange / on-behalf-of | User delegation via a new token scoped for downstream | User context must be preserved while inbound token lacks right audience/scope |

**Never replace a user token with a service token while assuming the backend still knows which user called.** If business logic requires per-user tenancy, ownership, and auditing, design delegation/token exchange or an authenticated, integrity-protected context with a clear trust boundary.

## 5. Required Dependencies for Gateway WebFlux

`TokenRelay` requires OAuth2 Client support on the classpath. For a **Spring Cloud Gateway Server WebFlux** app using Maven, typical dependencies are:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>

    <!-- Add only if Gateway validates inbound Bearer JWTs. -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
</dependencies>
~~~

Gateway starter names differ across Spring Cloud Gateway generations. Older lines use `spring-cloud-starter-gateway` instead of the newer Server WebFlux starter. **Never mix multiple Gateway server variants or Web MVC/WebFlux starters arbitrarily**; choose the right stack and supported BOM.

With Gradle, coordinates are analogous:

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-gateway-server-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

The Resource Server starter is **optional depending on your inbound security model**; if Gateway only uses OAuth2 Login or service client credentials for routes, dependency needs differ. Do not add Resource Server merely because you are configuring TokenRelay.

### 5.1. Inspect the Dependency Tree

In a real project, verify:

- OAuth2 Client classes resolve from the Spring Security version managed by the Boot BOM.
- The Gateway Server WebFlux `TokenRelay` filter factory is present at runtime.
- No conflicts exist between Spring Boot and the Spring Cloud release train.
- If using Web MVC, dependencies and TokenRelay support for your **Gateway Server MVC release** must be verified separately.

A route YAML referencing `TokenRelay` without the OAuth2 Client dependency loaded can cause the filter factory to be unavailable at startup or fail at runtime. Do not work around this by manually copying the Authorization header before confirming proper dependencies/runtime.

## 6. Configuring TokenRelay with OAuth2 Login: Relaying the User's Token

The first model fits when users **log in via OAuth2/OIDC at the Gateway** and the backend needs the access token bound to that user.

### 6.1. OAuth2 Client Registration for Authorization Code

Example YAML:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate-login:
            provider: corporate-idp
            client-id: ${GATEWAY_OAUTH_CLIENT_ID}
            client-secret: ${GATEWAY_OAUTH_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - catalog.read
        provider:
          corporate-idp:
            issuer-uri: https://idp.example.test/issuer
~~~

Client ID, client secret, issuer, and redirect URI values are **test-environment placeholders**. Client secrets must be supplied via an approved secret manager/secret injection mechanism; never commit them to Git or write them to logs.

### 6.2. Spring Security WebFlux for Login and OAuth2 Client

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class OAuthLoginSecurityConfiguration {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/oauth2/**", "/login/**")
                            .permitAll()
                        .pathMatchers("/api/catalog/**")
                            .authenticated()
                        .anyExchange().denyAll())
                .oauth2Login(Customizer.withDefaults())
                .oauth2Client(Customizer.withDefaults())
                .build();
    }
}
~~~

This is a **browser/session-based login** model. Do not disable CSRF mechanically; session cookies are sent automatically by browsers and require proper CSRF protection. Configure exact redirect URIs, trusted forwarded headers if behind a reverse proxy, Secure/HttpOnly/SameSite cookies, and session lifetimes per policy.

### 6.3. Route Using TokenRelay Without a Registration ID

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-user-token
              uri: https://catalog.internal.example:8443
              predicates:
                - Path=/api/catalog/**
                - Method=GET
              filters:
                - StripPrefix=2
                - TokenRelay
~~~

In this example, the user logged in via OAuth2 and the authorized client for registration `corporate-login` is stored for that user. `TokenRelay` retrieves the **current authorized client's access token** to call Catalog.

**Route configuration alone is not enough.** If the user has not logged in, the session expired, the authorized client is missing, the token expired without refreshing, or the registration is wrong, Gateway has no token to relay. Exact behavior depends on exception handling/security entry point/filter path; inspect redacted logs and test on your exact version.

### 6.4. User Token Relay Requires Session/Authorized-Client Persistence

Across multiple Gateway replicas:

- A user may log in on Pod A while a subsequent request is routed by the load balancer to Pod B.
- If session/authorized-client state resides only in Pod A's memory, Pod B cannot find the authentication or token.
- Sticky sessions can mitigate symptoms in some setups, yet do not replace proper HA/session design.
- Use a shared session store such as Spring Session if login sessions must span replicas; verify which repository/service stores authorized clients and how it persists/replicates.
- Upon logout, revocation, or session expiration, old tokens must no longer be used per policy.

Never log session IDs or authorized-client access tokens while investigating these bugs.

## 7. Configuring TokenRelay with client_credentials: Service Token

The second model fits when Gateway calls Catalog **under the Gateway service's own identity**. Inbound clients can be authenticated via JWT, API key, or another mechanism; the downstream access token is acquired from an OAuth2 Client registration.

### 7.1. ClientRegistration for Catalog

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          catalog-client:
            provider: internal-idp
            client-id: ${CATALOG_CLIENT_ID}
            client-secret: ${CATALOG_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - catalog.read
        provider:
          internal-idp:
            token-uri: https://idp.example.test/oauth2/token
~~~

The exact registration ID is **`catalog-client`**. It must match the argument in route filter `TokenRelay=catalog-client`. Even a one-character mismatch causes Gateway to miss the registration. Scope `catalog.read` is only an example; the authorization server and Catalog must agree on scope/claim names and authority mappings.

### 7.2. Route Acquiring a Service Access Token

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-service-token
              uri: https://catalog.internal.example:8443
              predicates:
                - Path=/api/catalog/**
                - Method=GET
              filters:
                - StripPrefix=2
                - TokenRelay=catalog-client
~~~

When a request matches the route, the filter uses registration `catalog-client` to obtain an authorized client/access token and sends the Bearer token to Catalog. **This token represents the Gateway service**, not the end user.

### 7.3. Gateway Must Still Authenticate Inbound Users on Private APIs

If clients send JWTs and Gateway needs to validate them:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ResourceServerAndClientSecurityConfiguration {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/api/catalog/**")
                            .hasAuthority("SCOPE_catalog.proxy")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(resourceServer ->
                        resourceServer.jwt(Customizer.withDefaults()))
                .oauth2Client(Customizer.withDefaults())
                // Example for stateless Bearer-only APIs.
                // If using cookie/session authentication, evaluate CSRF separately.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .build();
    }
}
~~~

In this model there are **two tokens and two authorization decisions**:

1. Inbound token: client → Gateway, verifying issuer/audience/scope `catalog.proxy`.
2. Service token: Gateway → Catalog, acquired via `catalog-client`, scope `catalog.read`.

Gateway does not relay the raw inbound JWT merely because it validated it. The backend sees the service identity; if user identity is needed, add token exchange/on-behalf-of or another delegation design supported by your IdP and backend.

### 7.4. Client Credentials Have a Different Lifecycle from Authorization Code

- Client credentials require no user browser login.
- The authorized client/token typically binds to a principal representing the client/service in the OAuth2 client manager.
- Access tokens can be cached/reused and renewed on expiry per manager/provider support.
- Each Gateway replica may maintain its own token cache; scaling out replicas can spike token endpoint calls on cold starts.
- Client secrets, token endpoint availability, clock skew, and token expiry can all cause failures.
- Never fetch a new token **on every request** via a hand-rolled HTTP call when the OAuth2 Client manager already manages the authorized client lifecycle.

## 8. Inbound Bearer JWT and TokenRelay: The Most Common Confusion

A Resource Server configuration can validate JWTs:

~~~java
http.oauth2ResourceServer(resourceServer ->
        resourceServer.jwt(Customizer.withDefaults()));
~~~

Then a request arrives with:

~~~http
GET /api/catalog/items/42 HTTP/1.1
Authorization: Bearer <client-access-token>
~~~

Gateway creates an authentication in the security context (typically `JwtAuthenticationToken`). Yet **that is not automatically an OAuth2 Login authorized client**.

### 8.1. Why Doesn't TokenRelay Automatically Send the Inbound Token?

`TokenRelay` is an OAuth2 Client filter; it looks up an authorized client by the **registration/principal context** used by the OAuth2 Client manager. A Resource Server merely validates the inbound bearer token and does not create a corresponding `ClientRegistration`/`OAuth2AuthorizedClient`.

Therefore:

| Gateway Inbound Setup | `TokenRelay` Without Registration ID |
| --- | --- |
| OAuth2 Login + stored user authorized client | Can relay the user's access token |
| Resource Server only + `JwtAuthenticationToken` | **Does NOT default to raw inbound token passthrough** |
| Resource Server + OAuth2 Client `client_credentials` registration | Use explicit registration with `TokenRelay=...` to send a service token |
| Integrated Token Exchange / OBO | Relays the downstream token issued via that flow, per integration |

### 8.2. Which Model Should You Choose If the Backend Needs the User's Inbound Token?

Three options to evaluate:

1. **IdP issues an access token whose audience includes downstream** and the architecture uses controlled Bearer pass-through. Ensure the token genuinely carries the right audience/scope, Gateway never opens arbitrary forwarding to untrusted backends, and the backend validates it independently.
2. **OAuth2 Token Exchange / On-Behalf-Of (OBO)**: Gateway exchanges the inbound token for a new token carrying the backend's audience/scope, if supported by the IdP.
3. **OAuth2 Login + authorized client**: when users log in at Gateway and the registration's access token is persisted, use TokenRelay without a registration ID.

**Never write a custom filter copying every `Authorization` header to every upstream URI** just to make 401 disappear. That risks leaking tokens to unauthorized services, bypassing audience boundaries, or enabling SSRF/token exfiltration.

### 8.3. Never Swap a User Token for Client Credentials and Forget Ownership

A service token usually tells the backend "the Gateway service is permitted to call Catalog". It **does not prove** user A is allowed to read tenant B's item. When Gateway replaces a user token with a service token, the backend needs a trustworthy user context mechanism (token exchange, signed delegation context, or protected authorization call) and must still enforce ownership. Never treat an arbitrary `X-User-Id` header as proof.

## 9. Diagnosing ClientRegistration and OAuth2AuthorizedClient

When `TokenRelay` fails to send an access token, inspect **registration → manager → authorized client → principal → filter → outbound request** in order. Do not start by changing the backend's JWT decoder if Gateway never sent a token to the backend.

### 9.1. Registration ID Must Match Exactly

Cross-check three places:

| Location | Example |
| --- | --- |
| YAML registration | `spring.security.oauth2.client.registration.catalog-client` |
| Route filter | `TokenRelay=catalog-client` |
| Token request/log metadata | registration ID `catalog-client` |

Common mistakes:

- Naming the registration `catalog-service` while the route specifies `catalog-client`.
- Defining `client-id` without a valid `provider`/issuer or token URI.
- Setting grant type `authorization_code` on a machine-to-machine route with no user login.
- Setting grant type `client_credentials` while client secret, authentication method, or scopes mismatch the IdP.
- Configuring only `spring.security.oauth2.resourceserver.jwt.issuer-uri` without any OAuth2 Client registration.
- Production profile failing to load the same OAuth2 Client config as the local profile.

### 9.2. Verify Whether the Authorized Client Was Created/Stored

`OAuth2AuthorizedClient` holds `ClientRegistration`, principal name, and access token. With OAuth2 Login, it binds to the authorized user; with client credentials, it binds to the principal/client context used by the manager.

Verify:

1. Did the OAuth2 login callback complete successfully?
2. Does the exact `registrationId` exist in `ReactiveClientRegistrationRepository`?
3. Is an authorized client stored in the active `ServerOAuth2AuthorizedClientRepository` or `ReactiveOAuth2AuthorizedClientService`?
4. Does the current principal match the exact name/type and context under which the authorized client was saved?
5. Is the token still valid, or can the manager refresh/re-authorize it?
6. Can the current Pod read session/authorized-client state created on another Pod?
7. Was a custom manager/repository declared that inadvertently replaced the default configuration?

Never dump the entire authorized client object because it contains access/refresh tokens. Log only registration ID, grant type, pseudonymized principal identifier, token expiry timestamp (if policy allows), and outcome.

### 9.3. Token Endpoint and Grant Type

For `client_credentials`, check:

- Can Gateway reach the token endpoint over DNS/TCP/TLS?
- Does the client authentication method expected by the IdP match `client_secret_basic`, `client_secret_post`, `private_key_jwt`, or another method?
- Is the client authorized for the requested scopes?
- Does the token response include valid `access_token`, `token_type`, and `expires_in`?
- Is clock skew between Gateway and IdP causing tokens to be treated as invalid/expired?
- Are token endpoint rate limits or availability preventing the manager from acquiring new tokens?

Never pass client secrets directly in URLs/query strings or debug logs. If the token endpoint returns `invalid_client`, the bug is OAuth2 client authentication; if it returns `invalid_scope`/`unauthorized_client`, check grants/scopes/client policies first.

### 9.4. Client Credentials and Principal Context

In some apps, a custom `ReactiveOAuth2AuthorizedClientManager` is configured to authorize clients for the current principal. If custom code builds a manager without `clientCredentials()` provider support, `TokenRelay=catalog-client` cannot obtain a token even when the registration exists.

When customizing the manager, verify:

- Does the provider chain include the required grant types (`clientCredentials`, `authorizationCode`, `refreshToken`)?
- Does the authorized client repository/service fit the flow in use?
- Does the manager receive a stable principal/context?
- Does it persist authorized clients and handle expiry/refresh properly?
- Are two beans of the same manager type colliding or overriding auto-configuration?

**Never build a custom token cache in a static field** to bypass manager errors. It can retain expired tokens, mix client identities across tenants, fail under concurrency, and break rotation/revocation.

## 10. Filter Chain: Token Acquired Yet Lost Outbound

Even when OAuth2 Client successfully obtains a token, another Gateway filter can strip or overwrite the header before the HTTP request leaves.

### 10.1. Check Hop by Hop

~~~mermaid
flowchart TD
    A["Inbound Authorization (optional)"] --> B["Spring Security authentication"]
    B --> C["Route predicate selects route"]
    C --> D["TokenRelay obtains authorized client"]
    D --> E["GatewayFilter chain mutates outbound request"]
    E --> F["HTTP client sends request"]
    F --> G["Backend receives Authorization"]
~~~

| Point | Question |
| --- | --- |
| Inbound request | Did the client send credentials if the route requires them? |
| Spring Security | Is the principal authenticated and of the expected type? |
| Route | Did the request match the route containing TokenRelay? |
| OAuth2 Client | Was the registration/authorized client found and authorized? |
| Gateway filters | Did another filter remove or replace `Authorization`? |
| HTTP client | Did a custom client/request transformer strip the header? |
| Edge/service mesh | Did a proxy behind SCG strip `Authorization`? |
| Backend | Did the request hit the right service/port and did middleware read the right header? |

### 10.2. Filters Prone to Conflicts

| Configuration | Risk |
| --- | --- |
| `RemoveRequestHeader=Authorization` | Can strip the Bearer header after TokenRelay added it, depending on actual filter order |
| `SetRequestHeader=Authorization,...` | Can overwrite the token supplied by TokenRelay with another value |
| `AddRequestHeader=Authorization,...` | Can create multiple Authorization values or an invalid header |
| Custom `GlobalFilter` stripping headers | May apply across many routes, not only the intended ones |
| Edge proxy/service mesh stripping auth header | Token disappears after Gateway already sent it properly |
| Backend adapter reading wrong header/forwarded auth | Token reaches the Pod yet misses the middleware expecting it |

**Do not put `RemoveRequestHeader=Authorization` on the same route as `TokenRelay` if the goal is to keep the outbound access token.** If you want to drop an inbound token and send a service token, design the relay/overwrite order explicitly, verify filter ordering for your exact version, and prove it with an HTTP stub. Never assume execution order solely from YAML line order.

### 10.3. SetRequestHeader and AddRequestHeader Are Not Equivalent

- `SetRequestHeader` replaces the header value with the specified value.
- `AddRequestHeader` appends a header value; it is not the right tool for replacing a Bearer token.
- `RemoveRequestHeader` removes the header from the outbound request.

For access tokens, **let TokenRelay own setting Authorization**. Never hardcode static tokens in YAML, never assemble `Bearer <configured-token>` in route configs, and never fabricate fake tokens to probe production.

### 10.4. Do Not Log Authorization to Prove Token Relay

You can prove the header arrived at the backend without logging tokens:

- Have the backend stub log only `authorizationPresent=true/false`.
- Log the scheme as `Bearer` while redacting the credential.
- If correlating tokens in a lab is necessary, use fake tokens and controlled one-way hash fingerprints; never log raw tokens.
- Log `routeId`, `registrationId`, `upstreamService`, response status, and correlation ID.
- Turn off wiretap/header logging after finishing the experiment.

## 11. Separate Inbound Errors from Upstream Errors Using Request Counters

To avoid confusing Gateway's 401/403 with Catalog's 401/403, place counters on **both sides**.

| Observation | Likely Conclusion | Next Step |
| --- | --- | --- |
| Gateway inbound count rises, backend count = 0, status 401 | Authentication/token validation failed at Gateway or request missed route | Check Security entry point and sanitized auth failures |
| Gateway inbound count rises, backend count = 0, status 403 | Gateway authorization/CSRF/policy blocked | Check authorities, matchers, CSRF |
| Backend count rises, `Authorization` absent | TokenRelay did not run/acquire token or header was stripped | Check route, manager, filter chain, and edge |
| Backend count rises, Bearer present, backend returns 401 | Wrong/expired token, wrong issuer/audience, or backend untrusted | Verify claims/policy using safe test tooling |
| Backend count rises, Bearer present, backend returns 403 | Token accepted, yet scope/role/tenant/ownership missing | Check authorization policy at backend |
| Backend count = 0, Gateway status 503 | Token endpoint/route/filter/transport failed prior to upstream | Separate OAuth2 client exceptions from Catalog connectivity |
| Token endpoint count climbs continuously | Authorized client not cached/reused or principal/manager keeps changing | Check repository, principal key, and expiry |
| Some replicas send token, others do not | Session/token cache/config drift | Check per-Pod registration, session store, profile |

**Backend count = 0 does not always mean Security blocked it**: the route may have missed, DNS/connection failed before HTTP reached the backend, or TokenRelay failed. Combine Gateway route outcomes with exception types.

### 11.1. Upstream Returns 401 While Gateway Logs Show No Auth Failure

This strongly indicates Gateway passed inbound security, yet the backend rejected the credentials. Check:

1. Did the backend receive the request?
2. Was the Authorization header present (log boolean/scheme only)?
3. Was the token a user token or a service token?
4. Do `iss`, `aud`, `exp`, `nbf`, and scopes/claims satisfy the backend?
5. Is the backend fetching JWKS from the right issuer and refreshing new keys?
6. Is clock skew between IdP/Gateway/backend reasonable?

### 11.2. Gateway Returns 403 Before Upstream

If backend counter is 0, check:

- Does `.hasAuthority("SCOPE_catalog.read")` match how Resource Server maps scopes to authorities?
- Does the token carry `scope` or `scp` claims, and does the converter map the `SCOPE_` prefix?
- Does the security matcher cover the exact path after ingress rewrites?
- Is CSRF blocking POST/PUT/PATCH/DELETE due to cookie/session authentication?
- Is another authorization rule present in `SecurityWebFilterChain` or method security?

Never fix this by switching all routes to `permitAll()`. Write tests for each role/scope and verify the backend receives zero rejected requests.

## 12. Issuer, Audience, Scopes, and Claim Mapping

TokenRelay only forwards the authorized client's access token; **it does not automatically transform a token into what the backend expects**. Define the contract between the IdP and each resource server.

### 12.1. Claims to Cross-Check

| Claim / Attribute | Question | Potential Error |
| --- | --- | --- |
| `iss` | Does issuer match URL/trust configuration? | Backend rejects token |
| `aud` | Is token intended for Catalog API or Gateway? | Gateway accepts, Catalog returns 401 |
| `exp` | Is token unexpired? | Token expired |
| `nbf` | Has token reached its valid-from time? | Token not yet valid |
| `scope` / `scp` | Does it carry required permissions? | 403 insufficient scope |
| `sub` | Is subject a user or service principal? | Wrong ownership/audit |
| `client_id` / `azp` | Which client was issued the token? | Disallowed by client policy |
| tenant/roles | Do claims match tenant/role mapping? | 403 per business authorization |
| `kid` | Is signing key still in JWKS? | Signature verification failure on key rotation |

### 12.2. Audience Mismatch Example

Suppose inbound token:

~~~json
{
  "iss": "https://idp.example.test/issuer",
  "aud": ["gateway-api"],
  "scope": "catalog.proxy",
  "sub": "user-42",
  "exp": 1893456000
}
~~~

Gateway accepts the token because of audience `gateway-api` and scope `catalog.proxy`. Catalog, however, requires audience `catalog-api` and scope `catalog.read`. **Relaying this exact token to Catalog does not change its audience to `catalog-api`**; the backend rightly rejects it.

Valid solutions:

- IdP issues tokens with appropriate multiple audiences if policy permits and backends accept it.
- Use OAuth2 Token Exchange / OBO to exchange the token for one carrying Catalog's audience/resource and scope.
- Use service credentials if the backend only needs to authenticate the Gateway service while user authorization uses a separate mechanism.

Never modify the `aud` claim inside a JWT by decoding and re-encoding at the Gateway. The signature will break; the Gateway is not an authorization server.

### 12.3. Scopes and Authorities Are Not Role Names

Spring Security Resource Server typically maps scopes to authorities prefixed with `SCOPE_` (e.g., `catalog.read` becomes `SCOPE_catalog.read`), whereas roles may use `ROLE_`. Other backends may read `scp`, `roles`, or custom claims. Inspect the **JWT converter and authorization mapping** at each resource server rather than just glancing at scopes inside the token.

### 12.4. Opaque Tokens

If the IdP issues opaque access tokens, Resource Server can validate them via an introspection endpoint. TokenRelay can still relay an authorized client's access token, yet the backend must support the same token format/introspection or trust policy. Never assume every Bearer token is a JWT decodable offline.

### 12.5. Clock Skew and Key Rotation

Valid tokens can be rejected if clocks on Gateway, backend, and IdP drift too far. JWKS rotation can create a window before backends fetch the new signing key. Verify NTP/clock sync, token `kid`, JWKS caching/refresh, and redacted signature errors; never set huge clock skew or disable signature verification.

## 13. Intentional Token Relay Configurations: Complete Examples

### 13.1. Model A: User OAuth2 Login

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          corporate-login:
            provider: corporate-idp
            client-id: ${GATEWAY_OAUTH_CLIENT_ID}
            client-secret: ${GATEWAY_OAUTH_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - catalog.read
        provider:
          corporate-idp:
            issuer-uri: https://idp.example.test/issuer

  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-user-token
              uri: https://catalog.internal.example:8443
              predicates:
                - Path=/api/catalog/**
              filters:
                - StripPrefix=2
                - TokenRelay
~~~

**Contract:** user logs in at Gateway, authorized client is bound to the user, downstream receives the user's access token. Session/authorized-client persistence across replicas is required and the backend must accept that token's audience/scopes.

### 13.2. Model B: Inbound JWT + Outbound Service Token

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
      client:
        registration:
          catalog-client:
            provider: internal-idp
            client-id: ${CATALOG_CLIENT_ID}
            client-secret: ${CATALOG_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - catalog.read
        provider:
          internal-idp:
            token-uri: https://idp.example.test/oauth2/token

  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-service-token
              uri: https://catalog.internal.example:8443
              predicates:
                - Path=/api/catalog/**
                - Method=GET
              filters:
                - StripPrefix=2
                - TokenRelay=catalog-client
~~~

Security configuration must require the appropriate inbound scope and enable OAuth2 Client support. These are **two distinct credentials**: the user's inbound JWT and the outbound service access token. Catalog authorizes the service identity; if per-user permissions are needed, add a properly designed delegation context/token exchange.

### 13.3. Never Mix Both Models Without Defining Precedence

If a route can encounter a user session, an inbound JWT, and `TokenRelay=catalog-client`, decide explicitly whether the backend requires:

- a user access token;
- a service access token;
- user-delegated token exchange; or
- no token.

Never let an accidental session cookie decide which token goes to the backend. Every route needs an **explicit, testable, security-reviewed token policy**.

## 14. Spring Cloud Gateway Web MVC: Differences to Remember

Gateway Server Web MVC is built on Servlet/Spring MVC and has a different filter/request lifecycle from WebFlux:

| Gateway Server WebFlux | Gateway Server Web MVC |
| --- | --- |
| Reactive `SecurityWebFilterChain` | Servlet `SecurityFilterChain` |
| `ServerWebExchange`, `WebFilter`, `Mono` | `HttpServletRequest`, Servlet Filter, MVC/WebMvc.fn |
| Reactive OAuth2 Client repository/manager APIs | Corresponding Servlet OAuth2 Client APIs/repository/manager |
| Reactor Netty HTTP client in typical setups | MVC stack HTTP client/request factory |
| Reactive GatewayFilter/GlobalFilter chain | MVC before/handler/after filters per Gateway Server MVC release |

Never use `ServerOAuth2AuthorizedClientRepository` or `ReactiveOAuth2AuthorizedClientManager` in Servlet code just because the TokenRelay name looks the same. Check **TokenRelay support, starters, registration properties, and filter APIs for your exact Gateway Server MVC version**. If a feature/route filter is unsupported in your MVC release, do not assume adding WebFlux YAML enables it.

## 15. When Do You Need a Custom ReactiveOAuth2AuthorizedClientManager?

In some versions/setups, auto-configuration provides an appropriate manager. When an application **declares its own manager**, verify the provider chain supports every grant type required by its routes. A manager configured only with `authorizationCode()` will not authorize a `client_credentials` registration.

### 15.1. Example Manager for Client Credentials

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;

@Configuration
public class OAuth2ClientManagerConfiguration {

    @Bean
    ReactiveOAuth2AuthorizedClientManager authorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository authorizedClients) {

        ReactiveOAuth2AuthorizedClientProvider provider =
                ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                        .clientCredentials()
                        .build();

        DefaultReactiveOAuth2AuthorizedClientManager manager =
                new DefaultReactiveOAuth2AuthorizedClientManager(
                        registrations, authorizedClients);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

This example is for **a manager needing only client credentials** in a reactive web application. It is not mandatory for every SCG release; before adding the bean, check existing manager auto-configuration and corresponding API docs. If the same application also needs authorization code/refresh tokens, the provider chain must include those grants, and the repository/session must match each flow.

### 15.2. Do Not Override the Manager and Forget Other Grant Providers

A common configuration bug:

1. Initially the manager supports authorization code and refresh tokens for user login.
2. A developer adds a new manager bean containing only `clientCredentials()`.
3. No-arg `TokenRelay` for users stops acquiring/refreshing authorized clients as before.
4. Some routes work while user-specific routes begin failing.

Whenever adding a custom manager, write tests for **every registration type** in use and verify the provider chain, principal context, and authorized-client repository/service. Never rely on one service-token route passing to assume all user-token routes still work.

### 15.3. Repository and Service Have Different Roles

- `ServerOAuth2AuthorizedClientRepository` stores/reads authorized clients in the context of a reactive web request (typically bound to session/user).
- `ReactiveOAuth2AuthorizedClientService` provides persistence/service abstraction for authorized clients by registration/principal.
- `DefaultReactiveOAuth2AuthorizedClientManager` uses the repository tied to the web exchange.
- `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` fits application/service contexts using the authorized-client service, depending on integration.

Choose manager/repository type based on **user session vs. machine client**, not class name alone. A service-to-service token cache keyed by an unstable principal can hammer the token endpoint; a user-session repository unshared across replicas causes intermittent failures.

## 16. Filter Order and Session Persistence

### 16.1. Security WebFilterChain and GatewayFilter Chain Are Two Pipelines

Spring Security WebFlux protects inbound requests at the WebFilter layer. After a request clears security and a Gateway route is selected, the Gateway filter chain executes route/global filters, including TokenRelay.

~~~mermaid
flowchart TD
    A["HTTP inbound request"] --> B["WebFlux WebFilter chain"]
    B --> C{"Authenticated / authorized?"}
    C -->|No| D["401 / 403 response"]
    C -->|Yes| E["Route predicate matching"]
    E --> F["Route GatewayFilter chain"]
    F --> G["TokenRelay / path / header filters"]
    G --> H["Outbound HTTP client"]
    H --> I["Backend authorization"]
~~~

A request blocked by Spring Security **never reaches the TokenRelay route filter**. Thus having no outbound Authorization header in that scenario is expected behavior, not a TokenRelay bug.

### 16.2. Filter Order and Header Mutation

Gateway merges default filters, route filters, and global filters using the framework's ordering mechanism. Never assume execution order strictly matches YAML line order once filters are wrapped/sorted.

To diagnose:

1. Identify the actual matched route ID.
2. Inspect bound route filters after configuration binding.
3. Search for custom GlobalFilters/route filters mutating Authorization.
4. In tests, inspect headers at the **backend stub**, not only on the exchange prior to TokenRelay.
5. Temporarily remove suspected filters in a test profile to compare; never strip production policies "for a quick test".

### 16.3. SaveSession and OAuth2 Login

When OAuth2 Login stores authentication/authorized clients in WebSession, know when and where the session persists. Some flows/apps use the Gateway `SaveSession` filter to force saving WebSession before forwarding requests, yet **not every TokenRelay route requires adding SaveSession**. Use it only when your session lifecycle/deployment model requires it and integration tests verify it.

When running multiple Gateway replicas:

- Use a shared session store when browser login state must be accessible from any Pod.
- Check cookie domain/path/Secure/SameSite and forwarded schemes behind TLS-terminating proxies.
- Ensure session/authorized-client persistence does not lose authorized clients when requests switch Pods.
- Ensure rolling deployments do not wipe sessions/authorized clients outside policy.

### 16.4. Do Not Randomly Mix Browser Logins and Machine APIs

Browsers use session cookies and OAuth2 Login; machine clients usually send Bearer tokens validated by Resource Server. Supporting both is possible, yet requires **separate security matchers and CSRF policies**. Never enable login sessions for all APIs assuming TokenRelay will automatically relay Bearer tokens for machine clients.

## 17. Testing TokenRelay with an HTTP Backend Stub

Unit tests for route predicates do not prove tokens reach upstream. An integration test should include a **token endpoint test double**, a **real Gateway HTTP listener**, and a **backend stub**.

### 17.1. Test Diagram

~~~mermaid
flowchart LR
    T["JUnit / HTTP client"] --> G["Gateway RANDOM_PORT"]
    G -->|client_credentials| IDP["Token endpoint stub"]
    IDP -->|fake access token| G
    G -->|Authorization: Bearer fake-token| B["Catalog HTTP stub"]
    B --> J["Request journal: tokenPresent, route, count"]
~~~

In tests, use synthetic access tokens such as `test-service-access-token`, never real user or production tokens. The token endpoint stub returns a standard OAuth2 response, for example:

~~~json
{
  "access_token": "test-service-access-token",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "catalog.read"
}
~~~

The backend stub records only:

~~~text
requestCount=1
authorizationPresent=true
authorizationScheme=Bearer
resolvedPrincipal=service-catalog-client (test metadata)
~~~

Never print access token values to the console or test reports. If exact assertion is needed, compare against the synthetic token **in memory** without printing its value on assertion failure.

### 17.2. What Integration Tests Must Verify

1. Gateway starts up and the route containing `TokenRelay=catalog-client` loads.
2. OAuth2 Client registration has the right ID and grant type.
3. Token endpoint stub is called when a new authorized client is needed.
4. Backend stub receives exactly one request per inbound request in non-retry tests.
5. The `Authorization` header uses the Bearer scheme and carries the synthetic token from the token endpoint.
6. Backend stub receives the right path/query after `StripPrefix`.
7. Client receives response status/body per contract.
8. Subsequent calls while the token is unexpired reuse the authorized client; test token endpoint call counts per your version's manager/cache policy.
9. When the token endpoint returns `invalid_client` or times out, Gateway does not call Catalog with fake/empty credentials.
10. When the backend returns 401/403, the response is observed as an upstream response, not mistaken for an inbound authentication failure.

### 17.3. Negative Tests

| Test | Setup | Assertion |
| --- | --- | --- |
| Missing registration | Route references `catalog-clinet` (typo) | Clear startup/filter/authorization failure; backend HITS=0 |
| Missing OAuth2 Client dependency | Test context lacks OAuth2 Client support | App/filter fails to start or route unusable; error not masked |
| Token endpoint `invalid_client` | Wrong test client ID/secret | Backend HITS=0; redacted token acquisition error logged |
| Token endpoint `invalid_scope` | Disallowed scope | Backend HITS=0 |
| Token endpoint timeout | Stub fails to reply within deadline | Request fails finitely without hanging indefinitely |
| Expired authorized client | Token expiry elapsed | Manager refreshes/re-authorizes per grant, or fails cleanly |
| Inbound JWT missing scope | Resource Server + `client_credentials` | Gateway 403, backend HITS=0 |
| Upstream missing Authorization | Add test filter intentionally stripping header | Test catches `authorizationPresent=false` |
| Upstream returns 401 | Stub returns 401 after receiving request | Backend HITS=1, status provenance is upstream |
| Upstream returns 403 | Stub returns 403 | Backend HITS=1, scopes not artificially elevated |

### 17.4. Testing User-Token Relay Differs from Service-Token Relay

With OAuth2 Login:

- Stand up a test authorization server or use Spring Security test support to create the authentication/authorized client.
- Verify the authorized client binds to the right principal.
- Send a request with the test session and assert the backend receives the synthetic user access token.
- Test session expiration/missing authorized client and multi-replica persistence.

With Resource Server + `client_credentials`:

- Send a valid test inbound JWT to Gateway.
- Gateway verifies inbound scope.
- TokenRelay obtains a **synthetic service token** from the token endpoint stub.
- Backend receives the service token; test explicitly asserts it is not the inbound JWT.

Never use a test checking only status 200 to conclude these two flows are equivalent.

## 18. Troubleshooting Runbook for 401/403 and TokenRelay

Following this order isolates bugs rapidly without dumping tokens.

### Step 1 — Identify Which Layer Generated the Status

Record:

- Timestamp, route ID, correlation/trace ID.
- Method/path with sensitive queries removed.
- Status received by client and `WWW-Authenticate` value if present.
- Whether Gateway matched a route, and outbound attempt count.
- Whether the backend received the request, and which status the backend returned.

If 401/403 occurs prior to routing, TokenRelay never ran. If the backend received the request and returned 401/403, focus on outbound credentials and backend authorization.

### Step 2 — Identify Which OAuth2 Flow Gateway Uses

Ask clearly:

1. Does the inbound request use an OAuth2 Login session or a Bearer JWT Resource Server?
2. Does downstream expect a user token, a service token, or token exchange?
3. Does the route use `TokenRelay` or `TokenRelay=<registrationId>`?
4. Does the registration specify the right grant type?

This is the most critical step. If the answer is **Resource Server accepts JWT, backend needs that exact token**, do not expect no-arg TokenRelay to copy the raw inbound header automatically.

### Step 3 — Verify Dependencies and Configuration

- Is the OAuth2 Client starter on the runtime classpath?
- Is the TokenRelay route filter factory recognized?
- Is `spring.security.oauth2.client.registration.<id>` loaded under the active profile?
- Does the route's registration ID match verbatim?
- Are token endpoint URI/issuer/client authentication method/grant/scopes accurate?
- Is a custom `ReactiveOAuth2AuthorizedClientManager` missing a grant provider?
- Does the route namespace match your Gateway Server WebFlux version?

### Step 4 — Verify Principal and Authorized Client

- For OAuth2 Login: is the user logged in and is the session still alive?
- Is the authorized client stored under the matching principal/registration?
- For client credentials: does the manager authorize this grant and use a stable principal context?
- Across replicas: does the current Pod have access to the required session/authorized-client state?
- Is the token expired, revoked, or unable to refresh?

### Step 5 — Verify Outbound Headers at the Backend Stub

Never verify by dumping raw tokens. The backend stub only needs to report:

~~~text
authorizationPresent=true
authorizationScheme=Bearer
tokenAudienceExpected=true (test token only)
routeId=catalog-service-token
~~~

If `authorizationPresent=false`, check whether TokenRelay ran and whether a filter/edge stripped the header. If the header is present yet the backend returns 401, inspect issuer/audience/expiry/JWKS. If the backend returns 403, inspect scopes/roles/tenant/ownership.

### Step 6 — Remediate Based on Root Cause

| Root Cause | Appropriate Remediation |
| --- | --- |
| Wrong registration ID | Fix route registration reference, test route startup |
| Missing OAuth2 Client dependency | Add proper starter/BOM, check filter factory |
| Missing client credentials grant/provider | Configure proper manager/provider, test token endpoint |
| Token endpoint unavailable | Check DNS/TLS/network/IdP health; retry token acquisition within deadline |
| Lost authorized client/session | Restore shared session/persistence and verify across replicas |
| Header stripped after TokenRelay | Fix filter ownership/order and add backend stub regression test |
| Audience/scope mismatch | Issue token with right resource/scope or use token exchange/service identity |
| Stale backend JWKS | Restore JWKS refresh/key rotation per policy |
| Backend lacks user ownership context | Implement delegation/token exchange; never inject fake user headers |

**Never remediate by disabling JWT validation, setting all routes to `permitAll()`, skipping audience checks, or logging real tokens.** Those shortcuts turn an availability incident into an authentication vulnerability.

## 19. Symptom → Cause → Priority Check Table

| Symptom | Possible Cause | Priority Check |
| --- | --- | --- |
| Client receives 401, backend HITS=0 | Gateway authentication failed | Resource Server decoder, session, `WWW-Authenticate` |
| Client receives 403, backend HITS=0 | Gateway authorization/CSRF | Authority matchers, scope mapping, CSRF |
| Gateway 200 on health, 401 on Catalog route | Health requires no auth; private route differs | Security rules and inbound token |
| Gateway accepts valid JWT, yet backend lacks Authorization | Resource Server creates no OAuth2AuthorizedClient; wrong TokenRelay flow | Principal type, registration, and relay mode |
| No-arg `TokenRelay` relays nothing | No OAuth2 Login authorized client/session | `OAuth2AuthenticationToken`, authorized client repository |
| `TokenRelay=catalog-client` relays nothing | Wrong registration ID or manager fails to authorize | ClientRegistration, provider chain, token endpoint |
| Error "client registration not found" | Route uses wrong ID or profile omits registration | Compare route filter against runtime config |
| Error no authorized client | Principal/registration association missing | Repository/service, principal name, session |
| Token endpoint returns `invalid_client` | Wrong client ID/secret/auth method | IdP client config and secret injection |
| Token endpoint returns `invalid_scope` | Scope ungranted/invalid | Registration scopes and IdP grant policy |
| Token endpoint timeout | DNS/TLS/IdP/network/connection timeout | Token endpoint transport metrics |
| Backend receives request without Authorization | TokenRelay did not run or header stripped | Route match, filter order, edge/service mesh |
| Backend receives two Authorization values | `AddRequestHeader` or custom filter appends | Outbound header journal; enforce single owner |
| Backend returns 401 with Bearer present | Expired/wrong issuer/audience/signature/JWKS | Redacted claims, backend decoder, clocks |
| Backend returns 403 with Bearer present | Missing scope/role/tenant/resource permission | Authorization mapping/backend ownership |
| Token valid at Gateway, rejected at Catalog | Audience scoped only to Gateway | `aud`, token exchange/OBO, or service token |
| Service token works, yet user ownership wrong | Backend sees only Gateway service principal | Delegation context/token exchange |
| Login works on one Pod, fails 401 on another | Session/authorized client stored locally only | Shared session store, cookies, replica routing |
| Errors start after token expiry | Refresh/client credentials re-authorization not running | Manager providers, expiry, token endpoint |
| Errors after IdP key rotation | Backend JWKS cache/refresh lagging | `kid`, JWKS refresh, signature errors |
| One route gets token, another does not | TokenRelay omitted on second route or different security flow | Route ID/filter list |
| 401 starts after adding RemoveRequestHeader | Filter strips outbound Authorization | Filter chain ordering and backend stub |
| Fails only through ingress, direct test passes | Proxy strips headers, wrong forwarded scheme/session cookie | Edge config, trusted proxy, cookie attributes |
| Browser fails while curl passes | CORS preflight/credentials/SameSite | OPTIONS, CORS allow headers, cookie policy |
| Gateway returns 503 when TokenRelay fetches token | Token endpoint/client manager exception mapped to error | Token endpoint outcome and Gateway exception |
| Backend has 0 HITS while Gateway logs route match | OAuth2 authorize/token acquisition or outbound connect failed | Manager exception, DNS/TCP/TLS, outbound metrics |
| Backend HITS spike multiple times per request | Multi-layer retries or client retries | Attempts per inbound request, idempotency |
| Logs hide Authorization so team assumes token lost | Logging policy properly redacts header | Backend boolean/scheme metric; do not enable raw header logs |

## 20. Safe Verification and Observation Commands

### 20.1. Call Route with Inbound Bearer Token

~~~bash
# Run in a test environment; ACCESS_TOKEN must be provided via a secret-safe mechanism.
curl --silent --show-error -D - -o /dev/null \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  'https://gateway.lab.example.test/api/catalog/items/42'
~~~

This command prints only response headers/status without the body; nevertheless, shell expansion and process environments must still follow policy. Never paste production tokens into chat, source code, CI output, or shell history. Use test tokens with dedicated test audiences/scopes.

### 20.2. Test Missing Token and Insufficient Scope

~~~bash
# Anonymous request: expect 401 if route requires authentication.
curl --silent --show-error -D - -o /dev/null \
  'https://gateway.lab.example.test/api/catalog/private'

# Test token with valid signature but missing scope: expect 403 per policy.
curl --silent --show-error -D - -o /dev/null \
  -H "Authorization: Bearer ${READ_ONLY_TOKEN}" \
  'https://gateway.lab.example.test/api/orders'
~~~

Expected statuses depend on actual security rules; these are **verification commands**, not observed execution outputs. If a route allows anonymous access or the backend emits its own status, outcomes differ; check backend counters/traces to confirm the layer.

### 20.3. Verify TokenRelay Service Token with a Stub

In a network-isolated lab with a backend stub, send a GET through Gateway and inspect the journal:

~~~text
routeId=catalog-service-token
inboundAuthenticated=true
oauth2RegistrationId=catalog-client
outboundAuthorizationPresent=true
outboundAuthorizationScheme=Bearer
backendRequestCount=1
~~~

The values above are **hypothetical metadata**, not live output. Never print raw `outboundAuthorization` to the terminal. If the backend lacks a token, inspect the TokenRelay manager/filter chain; if the token is present yet returns 401, inspect claims/resource-server policy.

### 20.4. Logs and Actuator

- Use correlation IDs and route IDs to join Gateway and upstream logs.
- Raise OAuth2 Client/Spring Security log levels only in **test environments or short approved windows**, after verifying redaction.
- Never enable Netty wiretap/header dumps in production to read tokens.
- Expose only necessary health/metrics/route diagnostics; protect Gateway Actuator with authentication and network isolation.
- Actuator's route listing endpoint can leak URIs/backend topology/filter configs; never expose it publicly.
- Metric labels should only use bounded values like route ID, registration ID, upstream service, and outcome; never user IDs, raw URLs/queries, or JWTs.

### 20.5. Do Not Mistake Token Endpoint Failures for Backend Failures

OAuth2 Client may call the IdP **before** calling Catalog. When the token endpoint times out or returns `invalid_client`, Catalog HITS can be 0. Do not raise Catalog timeouts or edit the backend JWT decoder in this case. Track separately:

- Token endpoint request count/status/duration.
- OAuth2 client authorization success/failure.
- Gateway outbound Catalog attempts.
- Catalog inbound count/status.

These are four separate streams of evidence.

## 21. End-to-End Sample Incident Walkthrough

### Scenario

A private Catalog API starts returning 401 after operations updates Gateway to:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog
              uri: https://catalog.internal.example:8443
              predicates:
                - Path=/api/catalog/**
              filters:
                - StripPrefix=2
                - TokenRelay
~~~

Client sends a valid Bearer JWT. Spring Security Gateway validates the JWT successfully and selects route ID `catalog`, yet Catalog logs:

~~~text
401 invalid_token: missing bearer credentials
~~~

### Initial Observations

| Layer | Illustrative Evidence |
| --- | --- |
| Client → Gateway | Bearer JWT present, Gateway returns status 401 |
| Spring Security inbound | JWT signature/issuer/audience gateway-api valid |
| Gateway route | Route `catalog` matches |
| Gateway outbound | HTTP attempt occurred |
| Catalog | HITS=1, no Authorization header |

Because backend HITS=1 and inbound Security succeeded, the failure is **not Gateway rejecting the JWT**. The token was simply not forwarded.

### Root Cause Analysis

The route uses `TokenRelay` without a registration ID. The team assumed this filter copies the raw inbound Bearer JWT. Instead, Gateway is configured as a **Resource Server** with no OAuth2 Login/authorized client for the user. TokenRelay has no authorized client to relay.

### Choose the Solution Based on Backend Requirements

**Case A — Catalog Only Needs to Authenticate the Gateway Service:**

1. Add OAuth2 Client registration `catalog-client` with grant `client_credentials`.
2. Configure `TokenRelay=catalog-client`.
3. Keep inbound Resource Server scope `catalog.proxy`.
4. Grant the service client scope `catalog.read`.
5. Catalog authenticates the service identity and enforces user/tenant policies via a dedicated delegation mechanism if required by business logic.

**Case B — Catalog Must Know the End User:**

1. Check whether the inbound token already includes Catalog's audience/scope.
2. If not, the IdP must support Token Exchange/OBO or another delegation flow.
3. Gateway obtains a downstream token carrying Catalog's audience/scope.
4. Catalog verifies the downstream token and enforces resource ownership.

Never pick client credentials and then blindly inject `X-User-Id` from the request to substitute for user authorization.

### Expected Outcome After Fix (in Lab)

~~~text
Gateway inbound authenticated=true
Gateway routeId=catalog
oauth2RegistrationId=catalog-client
tokenAcquisition=success
Catalog authorizationPresent=true
Catalog authorizationScheme=Bearer
Catalog response=200
~~~

The lines above are **illustrative target outcomes**, not logs from a running app. In production, log redacted metadata without printing tokens.

## 22. Test Matrix Before Fixing Bugs or Deploying TokenRelay

| ID | Scenario | Required Evidence |
| --- | --- | --- |
| A01 | Anonymous call to auth-protected route | 401/deny per contract, backend HITS=0 |
| A02 | JWT with invalid signature | Gateway rejects, backend HITS=0 |
| A03 | JWT with wrong issuer | Gateway rejects, backend HITS=0 |
| A04 | JWT with wrong Gateway audience | Gateway rejects, backend HITS=0 |
| A05 | Expired JWT | Gateway rejects or refreshes per designed flow |
| A06 | JWT with valid issuer/audience but missing scope | 403 at Gateway, backend HITS=0 |
| A07 | OAuth2 Login user with authorized client | No-arg TokenRelay sends user access token |
| A08 | Unauthenticated user | Redirect/login challenge or error per policy; no empty token sent |
| A09 | Expired session | Stale authorized client not reused outside policy |
| A10 | Missing authorized client | Clear filter/manager failure; backend HITS=0 |
| A11 | Wrong ClientRegistration ID | Token acquisition fails; backend HITS=0 |
| A12 | Client credentials token endpoint succeeds | Backend receives service Bearer token |
| A13 | Token endpoint invalid_client | Backend HITS=0 |
| A14 | Token endpoint invalid_scope | Backend HITS=0 |
| A15 | Token endpoint timeout | Request terminates within deadline |
| A16 | Client secret rotation | Token acquisition recovers with new secret |
| A17 | Expired access token | Manager re-authorizes/refreshes per grant |
| A18 | Custom manager missing provider | Test catches non-working flow |
| A19 | Route filter RemoveRequestHeader strips Authorization | Backend journal detects missing header |
| A20 | Custom GlobalFilter strips Authorization | Regression test catches lost header |
| A21 | Edge/service mesh strips Authorization | E2E catches difference before/after proxy |
| A22 | Backend returns 401 due to wrong audience | Gateway outbound token present; backend policy rejects |
| A23 | Backend returns 403 due to missing scope | Valid token, authorization rejects |
| A24 | Backend enforces tenant/ownership | Non-owner user receives 403 |
| A25 | User token relay across two Gateway replicas | Session/authorized client exists on both Pods |
| A26 | Client credentials across multiple replicas | Token manager/cache works without hammering IdP |
| A27 | Token key rotation/JWKS refresh | Signature verification remains enabled |
| A28 | Retries on backend 401/403 | No infinite retries or identity switching |
| A29 | 401 response from backend | Client status/provenance distinguished from Gateway 401 |
| A30 | Logs/traces/metrics | No leaked tokens, secrets, cookies, or PII |

### How to Organize Tests

- **Unit/security tests:** authentication, authorization, scope mapping, and CSRF.
- **OAuth2 client tests:** registrations, grant providers, token endpoint responses/errors, authorized-client persistence.
- **Gateway HTTP integration tests:** route filters, TokenRelay, paths/headers, and backend stubs.
- **E2E through edge/mesh:** header forwarding, TLS/mTLS, cookies, sessions, and status provenance.
- **Multi-replica tests:** shared sessions, token caching, rolling restarts, and configuration drift.

Do not treat WebTestClient with mocked authentication as proof that the token endpoint or outbound HTTP actually executed. Use **HTTP test doubles with request journals** when proving TokenRelay delivers credentials to backends.

## 23. Hands-On Lab: Investigating TokenRelay Not Sending Tokens

**Scenario:** Gateway Server WebFlux receives an inbound JWT with scope `catalog.proxy`. Catalog requires an access token with audience `catalog-api` and scope `catalog.read`. The route uses `TokenRelay` without a registration ID; the backend returns 401 due to a missing Bearer header.

### Part A — Set Up the Test Environment

1. Create a Gateway Server WebFlux app with a compatible Spring Boot/Spring Cloud BOM.
2. Add the OAuth2 Client starter; add the Resource Server starter if validating inbound JWTs.
3. Stand up a token endpoint stub returning a fake access token with scope `catalog.read`.
4. Stand up a Catalog HTTP stub recording `authorizationPresent`, `authorizationScheme`, request count, and method/path/query; never store raw tokens.
5. Run Gateway on a random port and inject token/backend stub URIs via test properties.
6. Use only fake tokens and test keys; never call production IdPs or backends.

### Part B — Reproduce the Failure

1. Configure Gateway solely as a Resource Server accepting inbound JWTs.
2. Leave the route using `TokenRelay` without a registration ID.
3. Send a valid test JWT for audience `gateway-api`.
4. Confirm Gateway security accepts it and the route matches.
5. Inspect the Catalog stub: the request arrived, yet the Authorization header is missing per reproduction setup.
6. Record the final status and backend counter; do not log the token.

### Part C — Apply the Service Token Model

1. Add registration `catalog-client` with `client_credentials`, a fake client secret, and scope `catalog.read`.
2. Update the route to `TokenRelay=catalog-client`.
3. Ensure `SecurityWebFilterChain` still requires inbound scope `catalog.proxy`.
4. Send the same test inbound JWT.
5. Verify the token endpoint stub was called and the Catalog stub received the fake Bearer token.
6. Verify the token is reused per lifecycle/expiry policy without calling the token endpoint endlessly.
7. Make the token endpoint return `invalid_client`; Catalog HITS must be 0.

### Part D — Try the User Delegation Model

1. Maintain a separate test route using OAuth2 Login Authorization Code.
2. Create a test user and authorized client holding a fake access token intended for Catalog.
3. Use TokenRelay without a registration ID.
4. Verify the backend receives the token bound to the test user, not a service token.
5. Clear/expire the session and check behavior when the authorized client is gone.
6. Run across two Gateway replicas with an appropriate session store and verify Pod B reads state created on Pod A.

### Part E — Find a Filter Stripping the Header

1. Add test route filter `RemoveRequestHeader=Authorization` in a sandbox.
2. Send a request and observe the backend stub reporting `authorizationPresent=false`.
3. Test custom `SetRequestHeader` or `AddRequestHeader` and observe behavior/duplicate values.
4. Remove the conflicting filter so only TokenRelay manages outbound Authorization.
5. Re-run the test and prove the backend receives the proper Bearer scheme.
6. Never enable raw header logging or wiretap containing credentials.

### Part F — Classify Statuses

1. Anonymous inbound → verify 401/entry point and backend HITS=0.
2. Authenticated but missing inbound scope → verify 403 and backend HITS=0.
3. Valid inbound, token endpoint failure → verify token acquisition failure, backend HITS=0.
4. Valid inbound, outbound token wrong audience → backend receives token and returns 401.
5. Outbound token right audience but missing scope → backend returns 403.
6. Valid outbound token, yet user does not own resource → backend returns 403 per ownership policy.

### Acceptance Rubric

| Item | Evidence |
| --- | --- |
| OAuth2 roles | Explains how Resource Server differs from OAuth2 Client/Login |
| Token source | Identifies user token, service token, or token exchange |
| Registration | Accurate ID, provider, grant, client auth method, and scopes |
| Authorized client | Accurate principal/repository/session |
| Filter chain | No filter unintentionally strips/overwrites Authorization |
| Backend | Bearer header present, right issuer/audience/scope, no raw token logged |
| Status | Separates Gateway 401/403 from upstream |
| Security | No auth bypasses, no spoofed headers treated as identity |
| Multi-replica | Stable session/token lifecycle |
| Recovery | Runbook and negative tests in place |

**Passing criteria:** Learners demonstrate **TokenRelay fetches tokens from the right source, sends the right token to the right backend, and distinguishes inbound auth errors from upstream token/authorization errors**.

## 24. Anti-Patterns to Avoid

| Anti-Pattern | Why It Is Wrong / Risky | Replace With |
| --- | --- | --- |
| Seeing 401 and immediately editing JWT decoder | 401 may come from backend or token endpoint | Identify response provenance via counters/traces |
| Seeing 403 and adding `ROLE_ADMIN` | Masks scope/tenant/ownership bugs | Inspect policy causing 403 and test specific authority |
| Enabling only Resource Server with no-arg TokenRelay | Inbound JWT is not automatically an OAuth2AuthorizedClient | Pick service token, user OAuth2 client, or token exchange |
| Assuming TokenRelay copies any inbound Authorization | TokenRelay fetches via OAuth2 Client manager/authorized client | Identify token source and registration |
| Using ID token as a Bearer access token | Wrong purpose/audience | Use access token issued for the resource server |
| Forwarding refresh tokens to backends | Leaks credentials capable of minting new tokens | Send only the appropriate access token |
| Using `client_credentials` assuming backend knows the user | Backend only sees the service principal | Token exchange/delegation + ownership checks |
| Using `AddRequestHeader=Authorization` | Can produce duplicate Authorization headers | Let TokenRelay manage a single Bearer header |
| Putting `RemoveRequestHeader=Authorization` after TokenRelay | Strips outbound token | Check filter ordering and remove conflicting filter |
| Hardcoding Bearer tokens in YAML | Leaks secrets, expires, prevents rotation | OAuth2 Client registration/secret manager |
| Writing a custom static token cache | Concurrency, expiry, principal mix-up, rotation bugs | Authorized client manager/repository/service |
| Disabling audience verification on backends | Tokens for other APIs could be accepted | Issue right audience or use token exchange |
| Granting wildcard scopes to fix 403 | Violates least privilege | Grant minimal scopes per route/resource |
| Disabling CSRF for browser sessions | Opens CSRF vulnerabilities | Distinguish cookie/session vs. Bearer-only APIs |
| `permitAll()` on all routes | Removes authentication/authorization controls | Matchers per route/method/scope |
| Copying raw Authorization to every upstream | Token exfiltration and confused deputy | Upstream allowlists, audience policies, token exchange |
| Logging raw tokens to debug | Leaks access/refresh credentials | Backend boolean/scheme, redacted metadata |
| Trusting client-supplied X-User-Id | Spoofed principal/tenant | Identity from verified token or signed delegation |
| Assuming backend HITS=0 proves Security blocked | Could be route miss, token endpoint failure, DNS/TCP failure | Route outcome + OAuth2 manager + transport metrics |
| Assuming status 401 proves TokenRelay didn't run | Backend may return 401 even when token arrived | Check Authorization presence and backend validation |
| Using mocked JWT tests to claim valid signature/issuer | Mock auth skips the real decoder | Signed test JWTs over HTTP integration tests |
| Testing only one Gateway Pod | Misses session/config drift | Multi-replica tests and per-Pod metrics |
| Enabling wiretap/header dumps in production | Can log tokens/cookies/PII | Safe instrumentation, test stubs, temporary approved logs |

## 25. Pre-Merge Checklist for OAuth2/TokenRelay Changes

~~~text
[ ] Identified Gateway Server WebFlux vs. Web MVC.
[ ] Compatible Spring Boot/Spring Cloud BOM and OAuth2 Client starter.
[ ] Identified inbound flow: OAuth2 Login vs. Resource Server.
[ ] Identified downstream identity: user token, service token, or token exchange.
[ ] No-arg TokenRelay used only when a user's authorized client exists.
[ ] TokenRelay=registrationId matches exact ClientRegistration ID.
[ ] Registration specifies accurate provider, token URI/issuer, grant type, and scopes.
[ ] Custom OAuth2AuthorizedClientManager supports required grants.
[ ] Authorized-client repository/service and principal context are correct.
[ ] Session/authorized-client persistence works across replicas if needed.
[ ] Access token carries right issuer, audience, expiry, and scopes for backend.
[ ] ID tokens/refresh tokens are never sent to resource servers.
[ ] Backend still validates tokens and enforces tenant/resource ownership.
[ ] No filter unintentionally strips/overwrites/appends Authorization.
[ ] Backend stub proves Authorization present and Bearer scheme.
[ ] No raw tokens, secrets, cookies, session IDs, or PII logged.
[ ] Tests cover inbound and upstream 401/403 and token endpoint errors.
[ ] Tests cover token expiry, refresh/re-authorization, and secret rotation.
[ ] Tests cover filter ordering, edge header stripping, and multi-replica behavior.
[ ] Actuator/route diagnostics are secured.
[ ] Retries are bounded and never repeat non-idempotent side-effecting operations.
[ ] Runbook defines status provenance and recovery paths.
~~~

## 26. Summary

- **401 and 403 do not share the same cause.** 401 usually relates to missing/unaccepted credentials; 403 usually means an authenticated principal lacks sufficient permissions. Gateway, edge proxies, and upstream backends can all emit these statuses, so always establish **response provenance**.
- **OAuth2 Client, OAuth2 Login, and OAuth2 Resource Server are distinct roles.** Resource Server validates inbound Bearer tokens; OAuth2 Client manages registrations/authorized clients/tokens for outbound calls; OAuth2 Login creates sessions and authorized clients bound to users.
- **TokenRelay is an OAuth2 Client Gateway filter**, not a raw Authorization header copier. The no-arg form uses the authorized client bound to an OAuth2-logged-in user; `TokenRelay=registrationId` uses the specified registration, commonly suited to client credentials.
- **A valid inbound JWT does not create an OAuth2AuthorizedClient.** If Gateway acts solely as a Resource Server, no-arg TokenRelay does not relay the inbound token by default. Choose user OAuth2 login, service tokens, token exchange/OBO, or explicitly designed and protected pass-through.
- **Service tokens differ from user tokens.** `client_credentials` represents the Gateway service; the backend does not automatically know the end user/tenant. If user-level authorization is needed, add delegation/token exchange or a verified context, and still enforce ownership in the backend.
- **The right token must match the right resource server.** Issuer, audience, expiration, not-before, signing key, and scopes/roles must satisfy Catalog/Orders policies. A token accepted by Gateway is not guaranteed to be accepted by backends.
- **The authorized client lifecycle matters.** Registration ID, principal, manager provider chain, repository/service, token expiry/refresh, session persistence, and replica behavior can all prevent TokenRelay from obtaining a token.
- **The filter chain can drop tokens.** `RemoveRequestHeader`, `SetRequestHeader`, `AddRequestHeader`, GlobalFilters, edge proxies, or service meshes can strip/overwrite Authorization. Prove header delivery to the backend with safe stubs without logging raw tokens.
- **Testing must cover both sides.** Security tests verify inbound 401/403; OAuth2 client tests verify token acquisition; HTTP integration tests verify outbound Bearer headers and backend responses. Never assert status 200 alone.
- **Safe recovery preserves trust boundaries.** Never disable signature/audience validation, open `permitAll()`, forward refresh tokens, hardcode access tokens, or trust client-supplied identity headers as principals.

A well-behaved **SPRING_CLOUD_GATEWAY** deployment with TokenRelay must answer four questions: **who was authenticated inbound, where does Gateway obtain the access token, which backend is permitted to receive that token, and what permissions does the backend grant upon receiving it?** When all four answers are clear and backed by tests, 401/403 bugs are isolated at the right layer without weakening security.

### Official References for Version Cross-Checking

- **Spring Cloud Gateway Reference — TokenRelay GatewayFilter:** https://docs.spring.io/spring-cloud-gateway/reference/
- **Spring Security OAuth2 Client:** https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html
- **Spring Security Reactive OAuth2 Resource Server:** https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html
- **Spring Security OAuth2 Login:** https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html
- **HTTP Semantics, RFC 9110** (401/403, WWW-Authenticate): https://www.rfc-editor.org/rfc/rfc9110
- **OAuth 2.0 Bearer Token Usage, RFC 6750:** https://www.rfc-editor.org/rfc/rfc6750
- **OAuth 2.0 Token Exchange, RFC 8693:** https://www.rfc-editor.org/rfc/rfc8693

Cross-check your running **Spring Boot, Spring Cloud Gateway, Spring Security, and IdP versions** before copying properties/APIs. YAML/Java snippets in this lesson are WebFlux learning and testing examples; this lesson does not replace integration testing on real systems or STEP 6 technical Content QA.
