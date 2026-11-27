# 14.11. Difference Between Login State and Token State

## 1. The Problem: User Is Still Logged In, Yet Orders API Returns 401

Suppose the **Employee Portal** application uses **Spring Boot**, **Spring Security OAuth 2.0 Client**, and **OpenID Connect (OIDC)**. Employees sign in with their company account, view the profile page, and open the orders screen. After some time, the Portal page still shows the user's name, yet requests to the **Orders API** are rejected:

~~~text
Browser -> Employee Portal: GET /dashboard       -> 200 OK
Browser -> Employee Portal: GET /bff/orders       -> 502/401 depending on Portal handling
Portal  -> Orders API:       Authorization: Bearer ...
Orders API -> Portal:        401 invalid_token
~~~

Conversely, a user can **log out of Portal** while a recently issued access token is still unexpired at the Authorization Server or Resource Server.

This is not a contradiction in OAuth 2.0. **Application login state** and **OAuth2 Authorized Client token state** are **two separate lifecycles**:

- **Login** answers: *Which principal does the application identify the current request as?*
- **Token** answers: *Which credentials does the application hold to call protected resources, are those credentials still usable, and how must they be re-acquired?*

Understanding both states prevents mistakes such as logging users out as soon as an access token expires, treating a refresh token as a login session, or keeping a login session alive indefinitely simply because the system can refresh an access token.

> Context: Java 17+, Spring Boot 3 / Spring Security 6, **Servlet/Spring MVC** application signing in via OIDC Authorization Code Flow. URLs, tokens, and timestamps are illustrative. Architectural principles also apply to WebFlux, though Reactive repository/manager types have different APIs.

## 2. Distinguishing Five Objects Often Loosely Called "Token"

| Object | Where Is It Held? | What Is It Used For? | Does It Mean "Logged In"? |
|---|---|---|---|
| **HTTP session / session cookie** | Session identifier cookie in browser; session data server-side | Maintains Portal session state across HTTP requests | The cookie alone is **not enough**; server must hold a valid SecurityContext/Authentication |
| **Authentication and SecurityContext** | SecurityContextRepository, typically tied to HTTP session in web apps | Identifies principal and authorities for requests to Portal | **Yes**, within the application's authentication policy |
| **ID Token (OIDC)** | Received and verified by the OIDC client; may reside in OidcUser | Proves the authentication event issued by the OP for the right client | **Not Portal's session**, never used in place of an access token |
| **Access token (OAuth 2.0)** | Inside OAuth2AuthorizedClient or appropriate token store | Authorizes calls to a Resource Server | **No**; a valid token does not mean an active logged-in HTTP session exists |
| **Refresh token** | Stored securely with the authorized client when issued | Asks the Authorization Server to issue a new access token per policy | **No**; holding a refresh token does not prove the current browser is authenticated |

In Spring Security OAuth2 Client, an `OAuth2AuthorizedClient` typically holds:

~~~text
OAuth2AuthorizedClient
├── ClientRegistration         (registrationId, grant, provider, ...)
├── principalName              (principal name bound to authorized client)
├── OAuth2AccessToken
│   ├── tokenValue             (sensitive credential)
│   ├── issuedAt
│   ├── expiresAt
│   └── scopes
└── OAuth2RefreshToken         (may be null)
    ├── tokenValue             (sensitive credential)
    └── issuedAt
~~~

It is **not** a SecurityContext; nor does it carry a "login=true" flag capable of replacing web request authentication. When using OIDC, the ID Token is normally represented via `OidcUser` or related OIDC components, not as a primary property of `OAuth2AuthorizedClient`.

## 3. The Two Independent States Model

### 3.1. Portal Login State

When an HTTP request hits Portal, Spring Security typically:

1. Reads the corresponding session/authentication mechanism.
2. Restores or constructs `SecurityContext`.
3. Resolves `Authentication`: principal, authorities, and authenticated status.
4. Enforces authorization policies to decide which routes/resources the request may access.

For OAuth2 Login on Servlet, post-login Authentication is typically `OAuth2AuthenticationToken`, whose principal may be `OidcUser`.

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
~~~

This state depends on **Portal's session and application security policy**. It can end due to logout, session timeout, administrative session revocation, SecurityContext changes, or re-authentication policies.

### 3.2. Authorized Client Token State

An OAuth2 Authorized Client is identified by **client registration** and **associated principal**, and stored in the configured repository/service:

~~~text
ClientRegistration(company)
      +
PrincipalName(employee-0042)
      |
      v
OAuth2AuthorizedClient
      ├── access token
      └── refresh token (if any)
~~~

Token status depends on lifetime, refresh capability, Authorization Server policies, and Resource Server acceptance. **A token being "unexpired" per `expiresAt` does not guarantee the Resource Server will accept it**: the token could be revoked, rejected for audience/scope, or invalidated by server policy.

### 3.3. Patterns to Avoid

~~~java
// Incorrect: having a token does not mean the browser request is logged in.
boolean loggedIn = authorizedClient != null;

// Incorrect: user being logged in does not guarantee token is unexpired and usable.
boolean tokenValid = authentication.isAuthenticated();
~~~

These two checks answer the **wrong questions**. Determine authentication state, authorized-client state, and **target API authorization** separately.

## 4. Three Layers of Control in an API Call Request

~~~mermaid
flowchart TD
    A["Browser requests /bff/orders"] --> B{"Does Portal have valid Authentication?"}
    B -->|No| C["Redirect login or 401 depending on endpoint type"]
    B -->|Yes| D{"Is principal allowed to call this feature?"}
    D -->|No| E["403 at Portal"]
    D -->|Yes| F["Find/authorize OAuth2AuthorizedClient"]
    F --> G{"Eligible access token present?"}
    G -->|Missing / expired| H["Refresh/re-authorize if grant & policy allow"]
    H --> I{"Token acquisition succeeded?"}
    I -->|No| J["Handle token failure or require re-authorization"]
    I -->|Yes| K["Call Orders API with Bearer token"]
    G -->|Yes| K
    K --> L{"Does Orders API allow?"}
    L -->|No| M["401/403 from Resource Server"]
    L -->|Yes| N["Return business result"]
~~~

Three distinct decisions:

1. **Portal authentication**: which principal does this browser/request belong to?
2. **OAuth2 client authorization**: can Portal obtain an eligible token to call the API?
3. **Resource Server authorization**: does the Orders API accept this token for the specific resource?

Answering "Yes" at step 1 **does not automatically** guarantee steps 2 and 3 succeed. Similarly, a token still valid at step 2 does not mean the user is currently logged into Portal.

## 5. Timeline: Session and Access Token Expire at Different Times

Suppose an illustrative environment:

~~~text
09:00  User logs into Portal successfully.
       - Portal creates SecurityContext/session.
       - Authorized Client gets access token AT-1.
       - AT-1 expires_at = 09:05.
       - Refresh token RT-1 is issued.

09:03  User views dashboard.
       - Session still valid.
       - AT-1 not yet expired.

09:07  User calls /bff/orders.
       - Session still valid.
       - AT-1 has expired.
       - AuthorizedClientManager can refresh AT-1 to AT-2.
       - Browser does not necessarily need to sign in again.

09:20  User logs out of Portal.
       - SecurityContext/session is terminated per app mechanism.
       - AT-2 or RT-1 are not implicitly revoked at the IdP.

09:21  Browser sends a new request to Portal.
       - No valid login session remains.
       - AT-2 still being unexpired somewhere does not count as Portal login permission.
~~~

These timestamps are examples only. **Session timeouts may be idle-based**, whereas access tokens normally carry their own issued/expiry timestamps. Some systems enforce absolute sessions, token rotation, and different revocation policies; do not assume one fixed duration always applies.

## 6. State Matrix: Login and Tokens Can Diverge

| Portal Session | OAuth2 Authorized Client / Token | Meaning and Behavior |
|---|---|---|
| **Logged in** | Access token unexpired per metadata | Can call API, yet must still account for scopes/permissions and Resource Server response |
| **Logged in** | Access token expired, valid refresh token present | Authorized-client manager can refresh; re-login not necessarily required |
| **Logged in** | Access token expired, no refresh token | May need to prompt re-authorization; do not automatically conclude session ended |
| **Logged in** | No authorized client found for target registration | May need a new authorization grant or prompt user to grant access |
| **Logged in** | Token rejected by Resource Server | Could be revoked/invalid token, missing scope, wrong audience, or sync error; handle by root cause |
| **Not logged in** | Stale token still remains in store | **Never** treat the current browser as authenticated; require valid authentication |
| **Not logged in** | No token remains | Normal state after logout/expiry |
| **Service-to-service, no user login** | Has access token from client_credentials | Calls API under service identity; creates no user session |

**The same "token unusable" symptom can have many causes.** Expired access token, insufficient scope, and revocation are three different events. Do not collapse them into a single boolean without error details, timestamps, or handling order.

## 7. Where Does Spring Security Store Authentication and Authorized Clients?

### 7.1. SecurityContext and HTTP Session

With typical Servlet web login configuration:

~~~text
Browser
  Cookie: JSESSIONID=...
      |
      v
HttpSession / SecurityContextRepository
      |
      v
SecurityContext
      |
      v
Authentication
  principal = OidcUser
  authorities = ...
  authenticated = true
~~~

The session cookie is only a **pointer to locate the session**, while Authentication is controlled server-side via SecurityContext. A leaked cookie risks session hijacking, so use HTTPS, HttpOnly, SameSite, and protect the session store appropriately.

### 7.2. AuthorizedClientRepository and AuthorizedClientService

Common API types on Servlet:

~~~java
org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository
org.springframework.security.oauth2.client.OAuth2AuthorizedClientService
~~~

**OAuth2AuthorizedClientRepository** supports saving/loading authorized clients in the HTTP request/response and Authentication context. **OAuth2AuthorizedClientService** supports saving/loading authorized clients by client registration ID and principal name at the service tier.

Common implementations:

~~~java
HttpSessionOAuth2AuthorizedClientRepository
AuthenticatedPrincipalOAuth2AuthorizedClientRepository
InMemoryOAuth2AuthorizedClientService
JdbcOAuth2AuthorizedClientService
~~~

Spring Boot/Spring Security configuration and version determine the actual repository/service types used. **Never assume every application stores access tokens inside the HTTP session itself**, or that every authorized client record automatically vanishes when the session expires.

| Component | Purpose | Events Affecting It |
|---|---|---|
| `SecurityContextRepository` | Stores/retrieves Authentication | Login, logout, session timeout |
| `AuthorizationRequestRepository` | Stores pending authorization request to match state at callback | Authorization start/callback, session |
| `OAuth2AuthorizedClientRepository` | Stores/retrieves authorized client bound to request/principal | Authorization, refresh, token removal |
| `OAuth2AuthorizedClientService` | Stores/retrieves authorized client by registration and principal name | Authorization, refresh, cleanup |

**AuthorizationRequestRepository** is not **OAuth2AuthorizedClientRepository**: the first holds **pre-callback requests**, while the second holds **tokens after issuance**.

### 7.3. Does Logout Clear Both Stores?

You cannot give a blanket "yes" for every deployment. Portal logout typically invalidates the session and clears SecurityContext per config. However, **tokens at the Authorization Server may still be valid**, and authorized client records in a persistent service may have an independent lifecycle.

To ensure tokens are revoked or purged from local stores, **design proper logout/token cleanup**, rather than merely calling `invalidateHttpSession(true)` and assuming all credentials at the IdP disappeared.

## 8. OAuth2AuthorizedClient and ClientRegistration Differ

A `ClientRegistration` describes a **client registered** with the IdP:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: employee-portal
            authorization-grant-type: authorization_code
            scope: [openid, profile, orders.read]
~~~

Yet no user is authorized merely because YAML defines a registration.

`OAuth2AuthorizedClient` is the **outcome of a successful authorization** for a client/principal, containing the access token and refresh token (if issued).

~~~text
ClientRegistration
  company (application config)
        |
        | successful authorization for principal employee-0042
        v
OAuth2AuthorizedClient
  registrationId = company
  principalName  = employee-0042
  accessToken    = ...
  refreshToken   = ... (if any)
~~~

If the application supports multiple registrations, a principal may have an authorized client for `company` without having one for `partner` or `reports-api`. **Logging in via `company`** does not automatically issue tokens for all other client registrations.

## 9. Does an Expired ID Token Automatically Log Portal Out?

In OIDC, the **ID Token** attests to an authentication event, carrying claims such as `iss`, `sub`, `aud`, `exp`, and others.

When Spring Security completes login, the ID Token is verified per OIDC rules. Afterward, the application may maintain the **SecurityContext across a session**.

Therefore:

- **ID Token** expiration is normally checked when the token is accepted during authentication.
- Portal's **HTTP session** lifetime is governed by the application's session policy.
- **Access token** lifetime for calling APIs is a third, separate lifecycle.

**Do not assume an ID Token expiring at 10:00 will automatically destroy an active Portal session's SecurityContext at exactly 10:00.** If the system requires re-authentication after a set interval or before sensitive actions, implement an explicit **session/reauthentication policy**.

Conversely, never interpret "session still active" as "an old ID Token or access token should still be accepted everywhere". Each token/mechanism has its own purpose and lifetime.

### 9.1. Do Not Use the ID Token as a Bearer Token for Orders API

Avoid:

~~~java
// Wrong purpose: never use an ID Token as an access token calling a Resource Server.
String bearer = oidcUser.getIdToken().getTokenValue();
~~~

The right approach is using an **access token** issued for the API/Resource Server, with matching issuer/audience/scope and per API policy. An ID Token carries the **OAuth Client's audience**, and does not inherently authorize calling the Orders API.

## 10. An Unexpired Access Token Is Not Guaranteed to Be Accepted

An `OAuth2AccessToken` provides:

~~~java
OAuth2AccessToken token = authorizedClient.getAccessToken();
Instant expiresAt = token.getExpiresAt();
Set<String> scopes = token.getScopes();
~~~

`expiresAt` is the expiration timestamp known to the client when the token was issued. Using it to decide **when to attempt a refresh** makes sense, factoring in clock skew. However, you cannot check expiry alone and declare the token "definitely valid".

A token can still be rejected due to:

- **Revocation** or Authorization Server/Resource Server policy.
- **Audience** mismatch with the target API.
- **Insufficient scopes**.
- Invalid JWT signature, JWKS rotation, or wrong issuer data.
- Token restricted to specific resources/HTTP methods.
- Account/tenant/resource authorization changes at the Resource Server.
- Clock skew and unsynchronized system clocks.

At the same time, a JWT having an `exp` claim does not mean every Resource Server performs instant revocation; revocation support depends on token format and architecture.

**HTTP 401 and 403 have distinct meanings in most APIs**:

- **401** usually relates to missing/invalid/expired tokens or failed authentication at the Resource Server.
- **403** usually relates to a recognized token lacking sufficient permissions.

Actual responses depend on API configuration; inspect `WWW-Authenticate`, sanitized security logs, and Resource Server policies instead of guessing from a single status code.

## 11. A Refresh Token Is Not "Permanent Login"

If the Authorization Server issues a refresh token, the OAuth2 Client can request a new access token via the **refresh_token grant**:

~~~mermaid
sequenceDiagram
    participant Browser as Browser
    participant Portal as Employee Portal
    participant Manager as OAuth2AuthorizedClientManager
    participant IdP as Authorization Server
    participant API as Orders API

    Browser->>Portal: GET /bff/orders with valid session
    Portal->>Manager: authorize(company, principal)
    Manager->>Manager: Read OAuth2AuthorizedClient
    Manager->>Manager: Access token nearly/already expired
    Manager->>IdP: POST /token grant_type=refresh_token
    IdP-->>Manager: New access token (+ new refresh token if rotated)
    Manager->>Manager: Update authorized client
    Manager-->>Portal: Refreshed authorized client
    Portal->>API: Authorization: Bearer new token
    API-->>Portal: Order data
    Portal-->>Browser: Return result
~~~

This illustrates the flow when **a refresh token exists, the grant is supported, the token manager/provider is configured, and the request satisfies policy**. Not every token or provider issues refresh tokens.

### 11.1. When Does Refresh Actually Happen?

Specific conditions must hold:

1. A component such as `OAuth2AuthorizedClientManager` **is invoked** when the application needs an authorized client.
2. The authorized-client provider supports `refresh_token`.
3. The authorized client holds a usable refresh token.
4. The token requires refreshing per the provider's expiry/clock-skew logic.
5. The Authorization Server accepts the credentials/grant and returns a valid response.

**Having a refresh token in the database does not make the token refresh itself as time passes.** In most applications, refreshing is triggered when authorizing/calling an API or by a purpose-built task. If you only read `OAuth2AuthorizedClient` directly from the repository, do not expect the repository to call the token endpoint itself.

### 11.2. Refresh Can Fail Even While the Session Is Alive

For example, the IdP returns:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{"error":"invalid_grant"}
~~~

Causes include an expired or revoked refresh token, one already spent under rotation, revoked permission, or mismatched grant conditions.

At that point, Portal may still have a valid session Authentication, yet **no usable access token to call the Orders API**. The application must handle this per policy: trigger re-authorization, redirect through a fresh OIDC login if needed, return an appropriate error status, or ask the user to take action.

**Do not solve every token error by keeping login sessions alive forever.** Conversely, **do not force full user logout** every time an API has a transient error or a secondary registration's token expires.

### 11.3. Refresh Token Rotation

Some Authorization Servers **rotate refresh tokens**: when RT-1 is used, the server returns AT-2 and RT-2, while RT-1 may become unusable.

~~~text
T1: Authorized Client = AT-1 + RT-1
T2: Refresh RT-1       -> AT-2 + RT-2
T3: Save new Authorized Client
T4: Next refresh       -> use RT-2, never RT-1
~~~

If the application runs multiple replicas and two requests concurrently attempt to refresh using RT-1, races and `invalid_grant` errors can occur. Choose refresh coordination, consistent storage, and provider-compliant retries; **never unconditionally retry a token request with an already-rotated refresh token**.

## 12. Portal Logout Does Not Automatically Revoke Tokens

At least three layers of "logout" must be distinguished:

| Action | Primary Effect | What Not to Assume Automatically |
|---|---|---|
| **Portal local logout** | Clears/invalidates HTTP session and SecurityContext per config | Access/refresh tokens at Authorization Server were definitely revoked |
| **OIDC RP-Initiated Logout at IdP** | Redirects/coordinates ending the SSO session at OP if supported | All access tokens at every API are invalidated instantaneously |
| **Token revocation/cleanup** | Requests token revocation at appropriate endpoint and/or deletes local store records | Portal's browser session is automatically cleared without separate handling |

Example:

~~~text
10:00  User logs in -> Session S1 + AccessToken AT1
10:02  User logs out of Portal -> S1 invalidated
10:03  AT1 may still be unexpired at the Resource Server
10:04  Browser requests without Session S1 are not treated as logged in
~~~

If the application must revoke refresh tokens on logout, check whether the Authorization Server provides a **revocation endpoint** and token revocation policy. If single logout across clients is needed, that is a separate OIDC logout/session management problem, not merely clearing Portal's cookie.

**Portal logout must cut off the current browser session's access**, even if a token in a backend store has not yet expired. Conversely, revoking a token might not automatically clear SecurityContext; application policy must decide when to force user re-authentication.

## 13. Valid Cases Where Tokens Exist Without a Login Session

### 13.1. Client Credentials Flow

A backend task using `client_credentials` can acquire an access token to call an API under the service identity:

~~~text
Scheduled job
  -> OAuth2AuthorizedClientManager
  -> ClientRegistration(reports-service)
  -> access token from client_credentials
  -> Reports API
~~~

There is no browser, no user HTTP session, and no OIDC user principal. **A service access token does not prove a user is logged in.**

### 13.2. Authorized Client Stored in a Persistent Service

If a deployment uses an `OAuth2AuthorizedClientService` storing tokens by principal name, authorized client records may outlive HTTP sessions depending on configuration and cleanup policy. However, an unauthenticated browser **cannot ask Portal to arbitrarily load tokens for a browser-supplied principal name and act as that user**.

For user-delegated grants, applications must tie token retrieval to a trusted Authentication/authorization context. Never use `?principalName=admin` to select tokens.

### 13.3. Tokens in Another System

An access token issued to a mobile app, another service, or an earlier login does not mean Portal has a valid session. Tokens have their own audiences, clients, and lifecycles. Never treat a token's existence in another system as grounds to "restore" a Portal session without proper authentication.

## 14. Servlet: Configuring Spring Security OAuth2 Login

### 14.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

### 14.2. Client Registration

~~~yaml
# src/main/resources/application.yml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}

server:
  servlet:
    session:
      timeout: 30m
      cookie:
        http-only: true
        same-site: lax
~~~

In production, configure HTTPS and the `Secure` cookie flag properly, e.g., `server.servlet.session.cookie.secure=true`. `OIDC_CLIENT_SECRET` must come from a secure secret source—never written to Git, JavaScript, or shared docs.

`session.timeout: 30m` does not set the access token lifetime to 30 minutes. Access token lifetimes are determined by the Authorization Server and token response.

### 14.3. SecurityFilterChain

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain portalSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Here:

- `oauth2Login()` handles login and Authentication.
- `oauth2Client()` provides OAuth Client integrations to manage authorized client usage when the app needs to call APIs.
- No line of config claims "access tokens live as long as the session".

If Portal's API needs to handle unauthenticated requests with **401 JSON** instead of an HTML redirect to the IdP, configure route-appropriate security entry points/exception handling. That is a difference in **how requests are responded to**, not a change in token lifecycle nature.

## 15. Inspecting Login State and Token State Separately

A helpful diagnostic tool checks **two separate sources**: the request's Authentication and the authorized client in the repository. Example internal service inspecting metadata only, **without calling refresh**:

~~~java
package com.example.portal.diagnostics;

import java.time.Instant;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.stereotype.Component;

@Component
public class AuthStateInspector {

    private final OAuth2AuthorizedClientRepository authorizedClients;

    public AuthStateInspector(
        OAuth2AuthorizedClientRepository authorizedClients
    ) {
        this.authorizedClients = authorizedClients;
    }

    public AuthSnapshot inspect(
        Authentication authentication,
        HttpServletRequest request
    ) {
        boolean loggedIn = authentication != null
            && authentication.isAuthenticated()
            && !(authentication instanceof AnonymousAuthenticationToken);

        if (!loggedIn) {
            return new AuthSnapshot(false, false, null, false);
        }

        OAuth2AuthorizedClient client =
            authorizedClients.loadAuthorizedClient(
                "company", authentication, request
            );

        if (client == null || client.getAccessToken() == null) {
            return new AuthSnapshot(true, false, null, false);
        }

        Instant expiresAt = client.getAccessToken().getExpiresAt();
        boolean pastRecordedExpiry =
            expiresAt != null && !Instant.now().isBefore(expiresAt);

        return new AuthSnapshot(
            true, true, expiresAt, pastRecordedExpiry
        );
    }

    public record AuthSnapshot(
        boolean loggedIn,
        boolean authorizedClientStored,
        Instant tokenExpiresAt,
        boolean tokenPastRecordedExpiry
    ) {}
}
~~~

This code illustrates state inspection:

- **loggedIn** is based on the request's Authentication.
- **authorizedClientStored** indicates whether the store currently has a record for `company` and the principal.
- **tokenPastRecordedExpiry** compares against `expiresAt` at check time.

**Do not interpret `authorizedClientStored=true` as "the token is guaranteed accepted by the API".** And **do not interpret `tokenPastRecordedExpiry=true` as "must log out immediately"**.

This service **does not call `OAuth2AuthorizedClientManager.authorize(...)`** and therefore **does not proactively refresh tokens**. To acquire a refreshed token, go through the appropriate authorized client manager/provider.

> Diagnostic code should only be used in testing or controlled admin channels. Never expose endpoints returning principal/session/token metadata publicly, and never return `tokenValue` or refresh tokens to the browser for status checks.

## 16. Calling APIs Using a Managed Authorized Client

A Portal endpoint may need to call the Orders API on the user's behalf. With Spring Security OAuth2 Client on Servlet, `@RegisteredOAuth2AuthorizedClient` is one way to receive a context-resolved authorized client:

~~~java
package com.example.portal.web;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class OrdersController {

    private final RestClient ordersApi =
        RestClient.create("https://orders.example.test");

    @GetMapping("/bff/orders")
    public String orders(
        @RegisteredOAuth2AuthorizedClient("company")
        OAuth2AuthorizedClient authorizedClient
    ) {
        String accessToken =
            authorizedClient.getAccessToken().getTokenValue();

        return ordersApi.get()
            .uri("/api/orders")
            .headers(headers -> headers.setBearerAuth(accessToken))
            .retrieve()
            .body(String.class);
    }
}
~~~

This is a **server-to-server bearer token** example, without returning tokens to JavaScript. In production, the Orders API URL should come from environment properties; the HTTP client needs timeouts/TLS/error handling, and responses should not include unnecessary sensitive data.

When invoked via a **properly configured authorized client manager/argument resolver**, Spring Security can execute the **re-authorize/refresh** step along the provider chain when tokens expire. **Never assume simply reading an `OAuth2AuthorizedClient` from a repository refreshes it.**

### 16.1. What Should You Do If Orders API Returns 401?

Avoid:

~~~java
// Wrong approach: an API 401 immediately treats the entire Portal session as expired.
session.invalidate();
~~~

A classified handling approach:

1. Verify **the browser request is still authenticated at Portal**.
2. Verify the token sent to Orders API belongs to the right client registration, audience, and scopes.
3. Check whether the token passed its known expiry; if so and refreshable, use the appropriate token manager.
4. If the Resource Server returns `invalid_token`, apply OAuth2 client failure handling/re-authorization or prompt the user to re-consent where possible.
5. If the error is `insufficient_scope` or HTTP 403 due to permission policies, **refreshing with the same scopes usually will not solve it**; request appropriate permissions or deny the action.
6. If Orders API is returning 5xx/timeouts, do not turn an infrastructure outage into "logging out the user".

Avoid infinite retries and avoid **repeatedly sending the old token** once the Resource Server has declared it invalid. When using OAuth2 client filters for `WebClient` or `RestClient`, configure a version-appropriate authorized-client failure handler to purge invalid token data and attempt controlled re-acquisition.

## 17. Configuring OAuth2AuthorizedClientManager for Refresh Tokens

For Servlet web requests, `DefaultOAuth2AuthorizedClientManager` coordinates:

- `ClientRegistrationRepository`: provider/client config.
- `OAuth2AuthorizedClientRepository`: saves/loads authorized clients per request/principal.
- `OAuth2AuthorizedClientProvider`: executes `authorization_code`, `refresh_token`, etc., when enabled.

Example creating a manager with authorization code and refresh providers:

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class AuthorizedClientManagerConfig {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientRepository authorizedClientRepository
    ) {
        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        DefaultOAuth2AuthorizedClientManager manager =
            new DefaultOAuth2AuthorizedClientManager(
                registrations, authorizedClientRepository
            );
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

This example illustrates **registering a provider chain** rather than requiring every project to define a custom bean: Spring Boot and Spring Security may already supply suitable integrations. If creating a custom bean, verify OAuth2 Client callers **use that exact manager** and that other needed grants (such as `client_credentials`) are not accidentally omitted.

**The refresh token provider does not change `SessionCreationPolicy` or HTTP session timeout.** It only manages the **token** lifecycle.

### 17.1. Manager for Background Tasks Differs from Web Requests

A scheduled job or message consumer without an `HttpServletRequest` should normally use `AuthorizedClientServiceOAuth2AuthorizedClientManager` paired with `OAuth2AuthorizedClientService`, with the appropriate grant providers.

Never try to grab `SecurityContextHolder.getContext().getAuthentication()` from a web user inside a scheduled job and assume it is a valid identity across runs. If the task needs a service identity, use client credentials; if it must call on a user's behalf, enforce proper consent, storage, revocation, and auditing policies.

## 18. Ending a Session Does Not Mean Ending IdP Authorization

OIDC login involves at least **three kinds of sessions/states**:

~~~text
1) OP / IdP SSO Session
   Cookie at login.example.test

2) Portal Web Session
   Cookie at portal.example.test
   SecurityContext / OidcUser

3) OAuth2 Authorized Client
   Access token / Refresh token at Portal
   Whether token remains usable is decided by AS/Resource Server
~~~

Events:

| Event | OP SSO Session | Portal Session | Authorized Client/Token |
|---|---|---|---|
| User logs into Portal | May be created/reused | Created/activated | Usually has token after callback |
| User logs out of Portal | May still remain | Terminated per config | May still exist in store or AS |
| User logs out at OP | Terminated per OP policy | Not implicitly cleared if Portal receives no logout notification | Not implicitly revoked |
| Access token expires | Does not necessarily change | Does not necessarily change | Needs refresh/re-authorize to call API |
| Refresh token revoked | Does not necessarily change | May still exist | Cannot mint new tokens |
| Portal session timeout | SSO may remain | Terminated | Token may persist depending on storage |

If the browser returns to Portal after the local session expired while the IdP SSO session remains active, a fresh OIDC authorization flow can complete quickly so the user feels they "didn't need a password". **This is re-login via SSO**, not proof the old Portal session survived.

### 18.1. Single Logout and Back-Channel Logout

Some OPs support notifying RPs/Clients of logout per OIDC. When using those mechanisms, Portal must configure handlers and session linking properly per spec; **never assume default OIDC login config already handles full single logout or token revocation**.

Even when the application receives a logout event, decide which application sessions must be invalidated and whether corresponding authorized clients must be deleted/revoked.

## 19. Authorization State Can Change Even While Both Session and Token Remain Unexpired

This aspect is easy to overlook when looking only at authentication and tokens:

~~~text
09:00 User logs in, receives role ORDER_MANAGER
09:05 Administrator revokes role ORDER_MANAGER
09:10 HTTP session still exists
09:10 Access token has not expired yet
09:10 User requests deleting an order
~~~

The application must define **authorization refresh/check mechanisms**:

- If Portal roles/authorities are stored in `Authentication` at login time, privileges can go **stale** without a refresh/reauthentication policy.
- If the Resource Server checks permissions dynamically, the API may reject the call even with an unexpired token.
- If roles are embedded inside a JWT access token, an API relying solely on static JWT claims may continue accepting old roles until expiry, unless revocation/supplemental checks exist.
- If the app stores tenant membership/ownership in a database, enforce permissions at service/resource boundaries rather than trusting an `email` claim or principal name alone.

Therefore, **active session + unexpired token** still does not guarantee an operation is permitted. This is an **authorization** concern, distinct from both states analyzed here.

## 20. Multiple Authorized Clients in the Same Session

Employee Portal might use:

~~~text
registration company       -> OIDC login and Orders API
registration reports-api   -> access token to call Reports API
registration partner       -> authorization with partner IdP
~~~

A principal signed in via `company` does not necessarily hold tokens for `reports-api` or `partner`. Furthermore, tokens from two registrations can:

- Expire at different times.
- Have different refresh tokens or none at all.
- Carry different scopes and audiences.
- Be revoked independently.
- Use different client authentication methods.

Therefore, manage token state **per authorized client/registration**, never using a single global `userHasValidToken` flag.

Example:

| Registration | Login State | Token State |
|---|---|---|
| company | User is authenticated at Portal | Access token unexpired |
| reports-api | User is still logged in via company | Token not yet issued or expired |
| partner | User is still logged in via company | No consent from partner yet |

If calling the Reports API fails due to `reports-api`'s token, there is no need to immediately destroy the `company` session. Handle the authorization/token flow specifically for `reports-api`.

## 21. Principal Name and Authorized Client Storage

Some implementations store authorized clients based on:

~~~text
(clientRegistrationId, principalName)
~~~

Example:

~~~text
("company", "employee-0042")
~~~

If the application changes `user-name-attribute` from `sub` to `email`, or the user changes their email, the principal name can change and existing authorized clients will no longer be found under the new key.

Consequences may include:

- Portal signs the user in successfully yet cannot find old tokens.
- The client must re-authorize even though email only changed for profile reasons.
- Audits and authorized-client records accumulate multiple principal names for one person.

With OIDC, maintain a stable identity using **issuer + subject** for business data and assess the impact on authorized-client storage whenever changing principal naming. Never use email as an automatic bridge into token records belonging to another account.

## 22. Cookies, SameSite, and Reverse Proxies Affect Login; Not Token Expiry

Portal running behind a reverse proxy:

~~~text
Browser --HTTPS--> Proxy --internal HTTP--> Spring Boot
    |                                  |
    | Cookie JSESSIONID                | SecurityContext / AuthorizedClient
    +-- callback from IdP ------------>|
~~~

If the browser does not send the session cookie on the callback due to `SameSite`, `Secure`, `Path`, or mismatched host, the application may **fail to find the initial authorization request**, causing login to fail before any authorized client exists.

That differs from post-login **token expiry**. Never alter cookie policies to fix an expired access token; conversely, never extend access token lifetimes to mask lost callback sessions.

Production configuration example:

~~~yaml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      timeout: 30m
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

Only trust forwarded headers from a trusted proxy that strips/sanitizes host/scheme/prefix; never use arbitrary browser-supplied headers to determine redirect URIs. **`SameSite=Lax`** typically works for top-level GET callbacks; cross-site POST callbacks like `form_post` require separate evaluation of `SameSite`, `Secure`, and CSRF cookies.

### 22.1. Multi-Instance Sessions and Authorized-Client Stores

If the application runs multiple nodes:

~~~text
Login starts on node A -> authorization request/session A
Callback hits node B   -> must be able to access the same session data
Post-login token on B  -> must find the matching authorized client
~~~

Distinguish clearly:

- **Session store** to restore SecurityContext and authorization requests.
- **Authorized client storage** to find tokens by principal/registration.

You can use session persistence/affinity or shared stores depending on architecture. A shared token store does not automatically fix lost callback sessions; a shared session does not automatically prevent refresh token rotation race conditions.

## 23. How the Application Should Explain Errors to Users

Good UX messaging depends on **failure type**, rather than lumping every error into "Your login session has expired".

| Scenario | Appropriate Message/Semantics |
|---|---|
| Missing Authentication/session | Prompt Portal login |
| User authenticated yet secondary registration unauthorized | Prompt granting access/connecting the required service |
| Access token expired and refresh succeeded | Proceed normally without bothering the user |
| Refresh token unusable | Prompt re-authorization or re-authentication per policy |
| API returns 403 due to missing permissions | Report insufficient permissions; do not phrase as lost session |
| API temporarily times out / 5xx | Report service temporarily unavailable; bounded retry possible |
| Portal account disabled | Block access per policy, even if IdP login/refresh still works |
| Local logout succeeded | Stop treating browser as authenticated; cleanup/revocation per design |

**API vs. browser navigation note:** a JSON endpoint for an SPA/BFF should normally return a handleable HTTP status rather than unconditionally emitting an HTML redirect to the IdP. For front-channel navigation, redirecting to the IdP is appropriate. This distinction belongs to Portal's exception handling/entry point design.

## 24. Safe Observability and Logging

When investigating "still logged in yet API fails", collect **non-secret metadata**:

- Does the request have a valid Authentication?
- Which client registration ID is being used?
- Does an authorized client record exist?
- What is the access token's `expiresAt`, and has it passed?
- Is a refresh token present? **Log only a boolean**, never the token value.
- Was the token manager/provider invoked and did refresh succeed?
- Did the API return 401, 403, 429, 5xx, or timeout?
- Is the OAuth2 error `invalid_grant`, `invalid_client`, or `insufficient_scope`?

**Never log:**

~~~text
Authorization: Bearer <real-access-token>
refresh_token=<real-refresh-token>
client_secret=<real-client-secret>
session_cookie=<real-JSESSIONID>
id_token=<real-ID-token>
authorization_code=<real-code>
~~~

Even a JWT access token with a readable payload is a sensitive credential. To correlate logs, use trace IDs/request IDs and controlled event codes, keeping tokens and full personal data out of logging/APM systems.

## 25. Common Misconceptions

**"User is logged in, so the access token is still usable."** False. Sessions and tokens have separate expiries and policies.

**"If the access token expires, the user must log out immediately."** Not necessarily. Tokens can be refreshed/re-authorized while the session remains alive.

**"Having a refresh token means the user is always logged in."** False. A refresh token is a credential to re-issue access tokens, not an HTTP session, and does not verify browser requests.

**"If the ID Token expires, the session vanishes automatically."** Not implicitly. A session/reauthentication policy is needed.

**"Local logout automatically revokes all tokens at the IdP."** Not implicitly. Corresponding cleanup/revocation/logout must be configured.

**"No authorized client found means no Authentication."** False. An authorized client may not exist yet or may have been deleted for a registration.

**"`OAuth2AuthorizedClientRepository.loadAuthorizedClient` automatically refreshes tokens."** Do not assume that. The repository mainly saves/loads; token lifecycles are coordinated by managers/providers when invoked.

**"API returning 403 means the token expired."** Not necessarily. Usually it indicates insufficient permissions or a resource policy denial.

**"One access token works for every API."** False. Scope/audience/resource policies determine which APIs a token applies to.

**"If it's a JWT, the token can never be revoked."** False. Revocation capability/methods depend on the server, lifetimes, and token validation architecture.

**"A client credentials token is an employee login."** False. That grant is for a service identity, not a user OIDC session.

## 26. Scenario Exercises

### Exercise 1: Access Token Expired While Session Remains Active

~~~text
Portal session timeout = 30 minutes idle
Access token lifetime = 5 minutes
Refresh token = issued

09:00 login
09:10 user opens /bff/orders
~~~

**Question:** Must the user be redirected back to the IdP?

**Approach:** Not necessarily. While the session stays active and the refresh token remains valid, the authorized-client manager can obtain a new access token without forcing the user to log in again. If refresh fails, handle re-authorization per policy.

### Exercise 2: Logged Out Yet Token Still Unexpired

~~~text
10:00 Portal logout
10:01 Old access token accepted by Resource Server when called directly
~~~

**Question:** Did Portal logout fail?

**Approach:** Not necessarily. Local logout terminates the Portal session; an already-issued access token has its own lifecycle and may remain valid. If product requirements mandate revoking tokens on logout, implement revocation/cleanup and verify Resource Server policies.

### Exercise 3: Valid Session Yet Registration reports-api Has No Token

Portal uses `company` for login and `reports-api` for tokens calling the Reports API.

**Question:** Does missing a `reports-api` token mean the principal is unauthenticated?

**Approach:** No. The user can be authenticated via `company` without having authorized `reports-api` yet. Handle authorization specifically for that registration.

### Exercise 4: Token Unexpired Yet API Returns 403

Portal holds an access token with `orders.read`; the user requests deleting an order requiring `orders.write`.

**Question:** Will sending the refresh token definitely fix it?

**Approach:** No. Refreshing with the same scopes typically will not grant `orders.write`. Proper scope/consent authorization is required; if the user lacks permission, return an appropriate 403.

### Exercise 5: ID Token Expired

The OIDC login ID Token has `exp` at 09:05; the Portal session lasts until 09:30 per policy.

**Question:** Should that ID Token be used as a bearer token to call the Orders API at 09:10?

**Approach:** No. An ID Token is not an access token for the Orders API. Portal maintaining its session per its own policy also does not change the ID Token's `exp` semantics.

### Exercise 6: Two Replicas Refresh Simultaneously

Two requests hitting two nodes both use refresh token `RT-1`; the provider enforces refresh token rotation.

**Question:** What is the risk?

**Approach:** One request may consume RT-1 first and receive RT-2; the other uses invalidated RT-1 and gets `invalid_grant`. Implement concurrency/store coordination per AS policy, never retrying RT-1 indefinitely.

## 27. Checklist When Designing Authorized Clients

| Question | What to Decide |
|---|---|
| How does Portal authenticate requests? | SecurityContext/session, OIDC login, or configured auth mechanism |
| Where is the token sent? | Which Resource Server, audience, scopes, and matching principal |
| Where is the token stored? | Which `OAuth2AuthorizedClientRepository`/`Service`, retention, and access controls |
| When is the access token refreshed? | Which manager/provider is invoked and which grants are enabled |
| What if there is no refresh token? | Re-authorization mechanism or prompting user consent again |
| How are refresh failures handled? | Distinguish `invalid_grant`, `invalid_client`, timeouts, and required user actions |
| What does local logout handle? | Session/SecurityContext, local authorized client cleanup, revocation if needed |
| Does IdP SSO logout affect Portal? | Configure OIDC logout notifications/reauth policy |
| Access token unexpired yet API rejects? | Scopes, audience, revocation, and resource permissions |
| Multiple client registrations? | Separate tokens/refreshes; never use one global `tokenValid` flag |
| Multiple replicas? | Session store, authorized-client store, refresh token rotation/concurrency |
| Email/principal name changes? | Authorized client storage key, external identity mapping, and migrations |
| Do logs leak tokens/secrets? | Log only required metadata; sanitize credentials and personal data |
| Browser keeps session yet roles change? | Authorization policy/role refresh/session revalidation |

## 28. Conclusion

**Login state** and **token state** must be designed as **two independent yet related lifecycles**:

- **Authentication / SecurityContext / HTTP session** tells Portal which principal owns the current request and which application permissions apply.
- **OAuth2AuthorizedClient / access token / refresh token** tells the client whether it holds credentials to call a Resource Server and which grant/policy governs refreshing/re-authorizing them.
- **OIDC ID Token** is user authentication data at the login step—not a session cookie and not an access token for the Orders API.
- **Resource Server** validates tokens and enforces resource permissions itself; an unexpired token does not automatically grant permission.

Therefore, **a user can stay logged in when an access token expires**, and **a token can remain valid after a Portal session ends**. Never use a single `loggedIn` boolean to represent all token state, nor use `tokenPresent` to determine authentication state. Combine **session management**, **authorized-client management**, **refresh/revocation policy**, and **resource authorization** according to each layer's proper responsibility. That is the foundation for building stable, secure, and diagnosable OAuth2/OIDC Clients in Spring Security applications.
