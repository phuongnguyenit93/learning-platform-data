# 17.8. `invalid_grant`, Revoked Tokens, and Re-Login Prompts

In **Spring Security OAuth 2.0/OIDC Client**, a `refresh_token` lets an application request new access tokens at the Token Endpoint without sending the user through the login screen every time an access token expires. Yet a refresh token is not permanent access. It can expire, be revoked, be replaced by a newer token after rotation, no longer belong to a valid Client, or be rejected by the Authorization Server for policy reasons.

A typical scenario:

```text
The user connected the application to an OIDC provider.
The application saved an OAuth2AuthorizedClient holding an access token and refresh token.
The access token expired.
Spring Security calls the Token Endpoint with grant_type=refresh_token.
The Authorization Server returns HTTP 400, error=invalid_grant.
```

**How should the application respond?** Never retry the refresh request infinitely; never fall back to another user's token, delete all account data, or treat every API 401 as an `invalid_grant`. Depending on the context, remove the invalid authorized client, mark the connection state as **needing re-authorization**, and initiate a new **Authorization Code/OIDC Login** involving the user when appropriate.

This lesson analyzes the standard meaning of `invalid_grant`, distinguishes revocation/expiration/rotation, explains how Spring Security handles refresh failures, contrasts Resource Server errors, and shows how to design safe reauthorization UX and operational strategies in both Servlet apps and background tasks.

## 1. Where Does the Refresh Token Appear in OAuth 2.0/OIDC Login?

With the Authorization Code Flow, the browser is redirected to the OpenID Provider (OP), then returns to the Client with an authorization code. Spring exchanges the code at the Token Endpoint, receiving an access token and optionally a refresh token.

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant C as Spring Security OAuth2 Client
    participant AS as Authorization Server
    participant API as Resource Server

    U->>B: Initiate login/connection
    B->>C: GET /oauth2/authorization/company
    C-->>B: 302 to Authorization Endpoint
    B->>AS: Login and grant consent if needed
    AS-->>B: Redirect to callback?code=...&state=...
    B->>C: GET /login/oauth2/code/company
    C->>AS: POST /token grant_type=authorization_code
    AS-->>C: access_token + id_token + refresh_token?
    C->>C: Verify OIDC and save authorized client
    C->>API: Authorization: Bearer access_token
    API-->>C: 200 OK
    Note over C: After some time, access token nears/reaches expiry
    C->>AS: POST /token grant_type=refresh_token
    alt Refresh succeeds
        AS-->>C: new access_token (+ new refresh_token?)
        C->>C: Update authorized client
        C->>API: Call API with new access token
    else Refresh invalid
        AS-->>C: HTTP 400 error=invalid_grant
        C->>C: Stop using failing refresh token, update state
        C-->>B: Prompt user to reconnect/re-login when appropriate
    end
```

Terms to keep distinct:

| Term | Meaning | Conclusion you must NOT jump to |
|---|---|---|
| **Access token** | Credential for calling APIs / Resource Servers | An unexpired `expiresAt` does not guarantee it has not been revoked |
| **Refresh token** | Credential for requesting new access tokens at the Token Endpoint | Holding a refresh token does not guarantee it is still valid |
| **ID Token** | JWT proving identity authentication in OIDC | Never use it in place of an access token for APIs |
| **HTTP session** | Login state in the Spring MVC application | An active session does not guarantee access/refresh tokens still work |
| **`OAuth2AuthorizedClient`** | Registration + principal + issued access/refresh tokens | Having a DB record does not guarantee the Token Endpoint will accept a refresh |
| **Reauthorization** | User walking through a new authorization flow when needed | Does not necessarily require re-entering a password if the IdP still has a valid session |

An application can still treat the user as **logged into the website** while an external API connection requires **reauthorization**. These are two separate states that should be modeled independently.

## 2. Understanding `invalid_grant` Under OAuth 2.0

According to **RFC 6749, Section 5.2**, `invalid_grant` is a Token Endpoint error code indicating that the provided authorization grant or refresh token is invalid, expired, revoked, does not match the redirection URI when applicable, or was issued to another Client.

Example response:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{
  "error": "invalid_grant",
  "error_description": "Refresh token is invalid or expired"
}
```

`error_description` is merely an optional human-readable string returned by the provider. Some providers return detailed messages, while others return only `invalid_grant`. Never rely on parsing its phrasing to make security decisions.

### 2.1. `invalid_grant` does not exclusively mean "token was revoked"

Common causes when using `grant_type=refresh_token`:

1. The refresh token reached its **absolute expiration**.
2. The refresh token hit an **idle timeout** after going unused for too long.
3. The user **revoked consent** or disconnected the app at the IdP.
4. An administrator or provider **revoked the token or linked session**.
5. The refresh token was **rotated** and the old token is no longer accepted.
6. A concurrent refresh request consumed the old token first, causing the second request to be rejected.
7. The refresh token was issued to **another Client** or a different environment.
8. The token was saved/updated improperly, truncated, or loaded from a stale cache/backup.
9. The Client's registration/policy changed, rendering the refresh token incompatible with the current Client.
10. The provider enforced specific time, session, or security policy limits.

**You cannot pinpoint the exact cause from `invalid_grant` alone.** Distinguishing revocation, rotation, and expiration requires checking context, Authorization Server audit logs (when available), token lifecycle, and previous refreshes.

### 2.2. The same error code also appears when exchanging an authorization code

`invalid_grant` **is not exclusive to refresh tokens**. The Token Endpoint can also return it during `grant_type=authorization_code` if:

- The code expired.
- The code was already consumed.
- The redirect URI does not match the original request.
- The PKCE `code_verifier` is invalid.
- The code was revoked or does not belong to the current Client.

Therefore, the first debugging question must be: **was the Token Endpoint request using `authorization_code` or `refresh_token`?**

| Active grant | `invalid_grant` usually relates to | Reaction |
|---|---|---|
| `authorization_code` | Invalid code / PKCE / Redirect URI / callback | Diagnose the login flow; restart flow if appropriate, do not touch refresh tokens |
| `refresh_token` | Expired/revoked/rotated/wrong-Client refresh token | Clear broken refresh state; prompt for reauthorization when needed |
| Extension grant | Provider-specific grant payload | Follow that grant's specification and contract |

Never wire a single "log everyone out" handler to every `invalid_grant` regardless of grant and origin.

## 3. Distinguishing Three Error Groups: Token Endpoint, Resource Server, and OIDC Login

A common time-waster is lumping every HTTP 401/403 and `invalid_grant` together as "broken refresh token".

### 3.1. Refresh error at the Token Endpoint

Example:

```http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic EXAMPLE_CLIENT_AUTH

grant_type=refresh_token&refresh_token=EXAMPLE_REFRESH_TOKEN
```

Response:

```json
{
  "error": "invalid_grant"
}
```

This means the Token Endpoint **rejected the refresh credential**. Calling it again with the exact same refresh token usually will not fix the problem and may trigger reuse-detection policies.

### 3.2. HTTP 401 at the Resource Server when using an access token

Example:

```http
GET /api/events HTTP/1.1
Host: api.example.test
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
```

Response:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

This means **the API rejected the access token**. Causes include expiration, revocation, wrong signature/issuer/audience, or token misconfiguration. The Client may need to obtain a new token or fix its registration; **you cannot yet assume the refresh token was revoked**.

### 3.3. HTTP 403 due to insufficient permissions

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

The token may be authentic yet lack the required scope or permission. Refreshing with **the same old scopes** usually does not grant additional permissions. You may need to request supplemental permissions/consent or update Authorization Server entitlements.

### 3.4. Comparison table

| Source | Error form | Primary meaning | Resolution |
|---|---|---|---|
| Token Endpoint | `400 invalid_grant` on refresh | Refresh credential no longer accepted | Stop retrying old token; clean up authorized client and reauthorize when needed |
| Token Endpoint | `401/400 invalid_client` | Client authentication failed | Check Client ID/secret/authentication method; do not force every user to re-login |
| Token Endpoint | `400 invalid_scope` | Requested scope invalid | Fix scopes, consent, or configuration |
| Resource Server | `401 invalid_token` | Access token rejected by API | Inspect expiry, revocation, audience; refresh token if appropriate |
| Resource Server | `403 insufficient_scope` | Insufficient API permissions | Request proper permissions or deny the operation |
| OAuth2 Login callback | `invalid_grant` on code exchange | Code/PKCE/Redirect URI/Client mismatch | Inspect authorization code flow |
| Spring MVC | HTTP 401/302 from the app | Missing app session or login entry point | Distinguish unauthenticated app session from provider token failure |

**Principle:** classify errors by endpoint, grant, and call layer before deciding to delete tokens or force users to sign in again.

## 4. When Does an Expired Access Token Trigger a Refresh?

In Spring Security, `OAuth2AuthorizedClient` holds `OAuth2AccessToken` and optionally `OAuth2RefreshToken`. When an `OAuth2AuthorizedClientManager` is configured with `refreshToken()`, the provider can refresh the access token when it is expired or close to expiration per policy.

```text
OAuth2AuthorizedClient
  ├── ClientRegistration
  ├── principalName
  ├── OAuth2AccessToken
  │    ├── tokenValue
  │    ├── issuedAt
  │    ├── expiresAt
  │    └── scopes
  └── OAuth2RefreshToken? (nullable)
```

Scenarios:

| Token state | What can the provider do? |
|---|---|
| Access token still valid | Return the existing authorized client |
| Access token nearing expiry, valid refresh token | Execute refresh grant and save new access token |
| Access token expired, no refresh token | Cannot refresh via this grant; another flow is needed |
| Refresh token revoked | Token Endpoint returns `invalid_grant` or corresponding provider error |
| `ClientRegistration` uses `client_credentials` | Normally requests new access token via client credentials; no refresh token needed |
| No saved authorized client | Background manager cannot interactively obtain user consent or authorization code |

**Having `refreshToken()` in the provider builder does not make the Authorization Server issue refresh tokens.** The provider decides which tokens to issue based on Client registration, grant, consent, scopes, and policy.

### 4.1. `expires_in` belongs to the access token, not a guarantee for the refresh token

Token response:

```json
{
  "access_token": "ACCESS_1",
  "token_type": "Bearer",
  "expires_in": 1800,
  "refresh_token": "REFRESH_1",
  "scope": "openid profile calendar.read"
}
```

`expires_in=1800` describes the access token's lifetime. It **does not mean the refresh token also lives for 1,800 seconds**. A refresh token may have its own lifetime, idle timeout, or revocation policy, often not advertised directly in a standard OAuth2 response.

### 4.2. An unexpired access token can still be revoked

A Resource Server may rely on introspection, revocation lists, or custom policies. Thus an access token with `getExpiresAt()` in the future is not guaranteed to be accepted by the API.

Conversely, an expired access token does not automatically mean the refresh token is also expired. The Client should use the refresh mechanism and handle errors at the Token Endpoint.

## 5. Why Are Refresh Tokens Revoked?

### 5.1. Revocation by the user

Users can open the "Connected apps" page at their IdP and revoke access for an application. The Authorization Server may revoke the refresh token or the entire authorization grant per policy.

Result: the application still holds an `OAuth2AuthorizedClient` record in its database, yet the Token Endpoint **no longer accepts** the stored refresh token.

### 5.2. Revocation by an administrator or security policy

An organization can revoke sessions/tokens when:

- A user leaves the organization or their account is disabled.
- There are signs of token compromise.
- Security settings change, credentials are reset, or incident response runs.
- The Client application is no longer permitted to access the resource.
- Policy requires users to re-grant consent.

Do not assume a specific action at the IdP revokes **every kind** of token across **every provider**. Exact behavior depends on issuer architecture, refresh token families, sessions, and APIs.

### 5.3. Refresh token timeout or expiration

Many providers enforce:

- **Absolute lifetime:** after a fixed deadline, the token can no longer be used.
- **Idle lifetime:** the token becomes invalid if unused for a set duration.
- **Session-bound lifetime:** the token depends on the age or state of the OP session per policy.
- **Policy-driven lifetime:** varies by Client, user, grant type, or risk level.

Even a healthy application will eventually have to ask the user to reconnect when one of these limits is reached.

### 5.4. Rotation invalidates the old token

Refresh token rotation issues a **new refresh token** when an old one is used; the Authorization Server may invalidate the old token and, if it sees the old token used again, treat that as a sign of theft.

```text
T0: Client holds RT-1
T1: Client sends RT-1 with grant_type=refresh_token
T2: AS returns AT-2 and RT-2
T3: Client saves RT-2, stops using RT-1
T4: Client sends RT-1 again -> invalid_grant / reuse detected
```

Under RFC 6749, if the Server issues a new refresh token, the Client **must discard the old token and replace it with the new one**. Never store the new token only in a local variable while leaving the old token in the database.

## 6. Refresh Token Rotation and Race Conditions

This is a common source of `invalid_grant` in systems with concurrent requests, multiple workers, or multiple instances.

### 6.1. Two requests using the same refresh token

```mermaid
sequenceDiagram
    autonumber
    participant A as Request/Pod A
    participant B as Request/Pod B
    participant DB as Authorized Client Store
    participant AS as Authorization Server

    A->>DB: Read authorized client with RT-1
    B->>DB: Read authorized client with RT-1
    A->>AS: POST refresh_token=RT-1
    AS-->>A: AT-2 and RT-2
    A->>DB: Save AT-2, RT-2
    B->>AS: POST refresh_token=RT-1
    AS-->>B: 400 invalid_grant
    Note over B,AS: RT-1 already used or invalidated
```

The situation is even worse if the provider treats **reuse** as token theft and revokes the entire **token family**, including the newly issued RT-2. Request A appears to succeed, yet the next refresh still fails.

### 6.2. Not only a scheduler problem

Races can happen when:

- Two HTTP requests concurrently call an API with an expiring access token.
- Two pods share one `OAuth2AuthorizedClientService`.
- A web request and a background job simultaneously refresh a user's token.
- A worker retries a refresh after a timeout even though the previous request already completed at the AS.
- The database is overwritten by a late cache/transaction write holding an old refresh token.
- Multiple devices improperly share a single refresh token against the Client model.

### 6.3. Ways to reduce the risk

Depending on your system, you can apply:

1. **Single-flight refresh** keyed by `(clientRegistrationId, principalName)` within a process.
2. **Distributed lock** or coordination when multiple instances share a refresh token.
3. **Optimistic locking / compare-and-swap** in the store to prevent stale data from overwriting fresh data.
4. **Updating access token and refresh token in one transaction** when persistence supports it.
5. **Reloading the authorized client from storage** before concluding a connection is invalid after a potentially race-induced error.
6. **Idempotent job design** so retrying business work does not create duplicate side effects.
7. **Bounded rate limiting/backoff** for transient errors; never retry `invalid_grant` infinitely.

`JdbcOAuth2AuthorizedClientService` enables shared token persistence, yet **it does not by itself guarantee** only one instance sends a refresh request. When strict rotation is enabled on the provider, add synchronization.

### 6.4. Be careful retrying after timeouts

Suppose the Client sends refresh RT-1, the Authorization Server succeeds and issues RT-2, yet the response is lost to a timeout. The Client still knows only RT-1.

If the Client immediately retries RT-1:

- The provider may reject it because RT-1 was already consumed.
- The provider may revoke the token family under reuse-detection policy.

Therefore, retrying a refresh token must be carefully evaluated against provider behavior. Never treat a refresh grant like an idempotent HTTP GET. If the new token state cannot be recovered safely, you may have to ask the user to re-authorize.

## 7. Where Is `invalid_grant` Detected in Spring Security?

Spring Security OAuth2 Client includes these components:

| Component | Role |
|---|---|
| `OAuth2AuthorizedClientManager` | Coordinates issuing/reissuing authorized clients |
| `OAuth2AuthorizedClientProvider` | Executes grants, including `refresh_token` |
| `OAuth2AuthorizedClientService` | Saves/loads/removes authorized clients outside Servlet requests |
| `OAuth2AuthorizedClientRepository` | Saves/loads/removes authorized clients in Servlet request contexts |
| `DefaultOAuth2AuthorizedClientManager` | Manager for web/Servlet requests |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | Manager for service tier, schedulers, and workers |
| `OAuth2AuthorizationFailureHandler` | Handles authorization failures per policy |
| `OAuth2AuthorizationSuccessHandler` | Handles successes, usually persisting the authorized client |
| `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` | Removes authorized clients for configured error codes |

When a token refresh is rejected, Spring can throw `OAuth2AuthorizationException` with an `OAuth2Error` containing the error code:

```java
try {
    OAuth2AuthorizedClient client = manager.authorize(request);
    // Use authorized client if present; check null when appropriate.
} catch (OAuth2AuthorizationException ex) {
    String errorCode = ex.getError().getErrorCode();

    if ("invalid_grant".equals(errorCode)) {
        // Refresh grant is no longer valid or was rejected.
    }
}
```

This snippet is conceptual; `manager` and `request` must be initialized via appropriate configuration. Avoid logging raw exceptions if stack traces or attached request logging might contain sensitive credentials.

### 7.1. Default behavior of `DefaultOAuth2AuthorizedClientManager`

Per Spring Security Javadoc, when authorization fails with `invalid_grant`, the Servlet request manager **by default removes the stored authorized client** from `OAuth2AuthorizedClientRepository`.

This is sensible: do not keep feeding a known-rejected refresh token into future calls.

This behavior changes if the application configures `setAuthorizationFailureHandler(...)`. In that case, **ensure** the custom handler does not accidentally omit necessary cleanup.

### 7.2. Default behavior of `AuthorizedClientServiceOAuth2AuthorizedClientManager`

For the service-tier manager used by scheduled jobs or workers, by default when `invalid_grant` occurs, the previous authorized client is **removed from `OAuth2AuthorizedClientService`**.

When a user-delegated job depends on that connection, deleting the authorized client is only the technical step; the application also needs to **mark the business connection as needing reauthorization** and guide the user through an interactive flow when they return.

### 7.3. Do not automatically wipe the entire session on refresh failure

When a refresh token is rejected, at least two distinct states exist:

```text
Spring Security login session:
  User is logged into your website.

External API connection:
  User authorized access to a provider's API.
  That connection may enter RECONNECT_REQUIRED.
```

If the app is a portal with a backend session, a Calendar API refresh token failure should not necessarily log the user out of the entire website. The right goal is usually revoking usage of **the Calendar connection** and prompting the user to re-authorize that connection.

Conversely, if product policy mandates the app session is only valid while the OIDC provider's tokens work, you can enforce reauthentication. That is an explicit security/product decision, not a universal default for every OAuth2 Client.

## 8. Configuring Managers with the Refresh Token Provider

### 8.1. Configuration for Servlet HTTP requests

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class WebOAuth2ClientConfiguration {

    @Bean("webAuthorizedClientManager")
    OAuth2AuthorizedClientManager webAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        DefaultOAuth2AuthorizedClientManager manager =
            new DefaultOAuth2AuthorizedClientManager(
                registrations,
                authorizedClients
            );

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

Here:

- `.authorizationCode()` supports browser flows in the appropriate context.
- `.refreshToken()` gives the manager the ability to renew access tokens when a refresh token already exists.
- The repository persists authorized clients in the web context per application design.
- By default, the manager handles `invalid_grant` by removing the failing authorized client from the repository unless overridden by a custom handler.

**Do not** assume every OIDC Login is guaranteed to have a refresh token just because the provider builder includes `refreshToken()`.

### 8.2. Configuration for tasks outside HTTP requests

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class BackgroundOAuth2ClientConfiguration {

    @Bean("offlineAuthorizedClientManager")
    OAuth2AuthorizedClientManager offlineAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .refreshToken()
                .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations,
                authorizedClients
            );

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

This example uses `refreshToken()` because the background task assumes **a user's authorized client already exists**, obtained through an interactive flow and saved under the right service/principal. Without an authorized client or refresh token, the background manager cannot display a consent screen to obtain a new authorization code.

A service-to-service job using `client_credentials` can also include `.clientCredentials()`, though that is a **different flow**, not a fix for an expired user refresh token.

### 8.3. Notes on shared storage

If web login uses an `OAuth2AuthorizedClientRepository` while a background worker queries a separate `OAuth2AuthorizedClientService`, the worker may fail to see the user's issued authorized client.

For jobs to continue using user permissions, design consistently:

- `registrationId` must match.
- `principalName` must identify the authorizing user.
- The authorized client must live in storage accessible to the background manager.
- The refresh token must actually have been issued by the provider and remain valid.
- The user must have granted offline/long-lived permissions per provider policy.
- The app must verify user/tenant ownership before letting a worker read a token.

**Never manually copy refresh tokens into an unprotected business table** just so background tasks can see credentials.

## 9. Detecting Refresh Errors in Business Services

A service should classify token errors and return a **stable business state** rather than leaking raw OAuth2 errors to the UI.

Suppose an app manages Calendar API connections. A verified record stores:

```text
internal_account_id = account-42
client_registration_id = calendar
authorized_client_principal_name = user-oidc-782
connection_status = CONNECTED
```

A background worker can retrieve the user's authorized client:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.stereotype.Service;

@Service
public class CalendarAuthorizationService {

    private final OAuth2AuthorizedClientManager manager;
    private final ConnectionStatusService statusService;

    public CalendarAuthorizationService(
            @Qualifier("offlineAuthorizedClientManager")
            OAuth2AuthorizedClientManager manager,
            ConnectionStatusService statusService) {

        this.manager = manager;
        this.statusService = statusService;
    }

    public OAuth2AuthorizedClient requireAuthorizedClient(
            TrustedCalendarConnection connection) {

        OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
            .withClientRegistrationId(connection.registrationId())
            .principal(connection.authorizedClientPrincipalName())
            .build();

        try {
            OAuth2AuthorizedClient client = manager.authorize(request);

            if (client == null) {
                statusService.requireReconnect(connection.id());
                throw new ReconnectRequiredException();
            }

            // Provider may not support refreshing and return the existing token.
            // Only use the access token if it is still valid for the task/API.
            if (client.getAccessToken().getExpiresAt() != null
                    && !java.time.Instant.now()
                        .isBefore(client.getAccessToken().getExpiresAt())) {

                statusService.requireReconnect(connection.id());
                throw new ReconnectRequiredException();
            }

            return client;
        } catch (OAuth2AuthorizationException ex) {
            String code = ex.getError().getErrorCode();

            if ("invalid_grant".equals(code)) {
                // The manager's default failure handler has usually
                // already removed the invalid authorized client from the service.
                statusService.requireReconnect(connection.id());
                throw new ReconnectRequiredException();
            }

            // Do not turn every network/config error into a reconnect prompt.
            throw ex;
        }
    }

    public interface ConnectionStatusService {
        void requireReconnect(String trustedConnectionId);
    }

    public record TrustedCalendarConnection(
            String id,
            String registrationId,
            String authorizedClientPrincipalName) {}

    public static final class ReconnectRequiredException
            extends RuntimeException {}
}
```

This is an **application structure template**, not a drop-in runnable module: the `TrustedCalendarConnection` repository, security checks, status persistence, and HTTP client must be implemented separately.

Points to remember:

1. `connection` must come from a record whose user/account **ownership is verified**, never from an arbitrary queue parameter.
2. Never print exceptions alongside token requests/responses.
3. `invalid_grant` thrown by the manager is classified as the connection needing reauthorization.
4. Transient `5xx`/timeout errors do not necessarily require immediate user reconnection.
5. With refresh token rotation, a race-prevention strategy is needed; the snippet above does not implement a distributed lock by itself.
6. When no authorized client exists, the manager cannot generate user consent; the app must initiate an interactive flow later.

### 9.1. Why still check whether the access token is expired?

With the `refreshToken()` provider, if no usable refresh token exists, the manager cannot reauthorize; depending on context, it may return the existing expired authorized client. If the caller sees a non-null client and immediately calls the API with the expired token, the result can be a 401.

To illustrate the failure state, the snippet above checks `expiresAt` when necessary. In production, let the provider/HTTP integration handle clock skew and token lifecycle for your version; avoid building a parallel refresh mechanism based solely on `Instant.now()`.

### 9.2. Never expose tokens in API responses

The API response to the frontend only needs:

```json
{
  "connection": "calendar",
  "status": "RECONNECT_REQUIRED",
  "action": "REAUTHORIZE"
}
```

Never return:

```json
{
  "refresh_token": "EXAMPLE_SECRET",
  "access_token": "EXAMPLE_SECRET",
  "oauth2_error_description": "RAW_PROVIDER_RESPONSE"
}
```

Provider error details can contain sensitive data or internal structures not meant for end users. Expose only a business code sufficient for the UI to present the next step.

## 10. Cleaning Up Invalid Authorized Clients While Preserving Business Metadata

On refresh `invalid_grant`, distinguish:

- **Authorized client credential state:** holds access token, refresh token, and metadata; must often be deleted to avoid reuse.
- **Business connection state:** records which provider the user connected, connection date, intended permissions, and whether reauthorization is needed; can be kept to guide the UI.
- **Internal account:** internal user data; must never be deleted merely because a refresh token failed.

State lifecycle example:

```text
CONNECTED
  -> access token nears expiry -> REFRESHING
  -> refresh succeeds          -> CONNECTED
  -> invalid_grant             -> RECONNECT_REQUIRED
  -> user reauthorizes         -> CONNECTED
  -> user disconnects          -> DISCONNECTED
```

```mermaid
stateDiagram-v2
    [*] --> CONNECTED: User completes OAuth2/OIDC consent
    CONNECTED --> REFRESHING: Access token needs refresh
    REFRESHING --> CONNECTED: New token valid
    REFRESHING --> RECONNECT_REQUIRED: invalid_grant
    CONNECTED --> RECONNECT_REQUIRED: Provider revoked / policy requires new consent
    RECONNECT_REQUIRED --> AUTHORIZING: User starts interactive flow
    AUTHORIZING --> CONNECTED: Valid callback, new tokens saved
    AUTHORIZING --> RECONNECT_REQUIRED: User cancels / callback fails
    CONNECTED --> DISCONNECTED: User actively disconnects
    RECONNECT_REQUIRED --> DISCONNECTED: User actively disconnects
```

### 10.1. What to watch out for when deleting an authorized client

`OAuth2AuthorizedClientService` supports deletion by `registrationId` and `principalName`:

```java
authorizedClientService.removeAuthorizedClient(
    "calendar",
    trustedUserPrincipalName
);
```

**Delete only the specific failing authorized client.** Never invoke a blanket "clear all OAuth2 clients" function if only one Calendar connection was revoked.

If the manager uses its default failure handler, `invalid_grant` already triggers cleanup via the management pipeline. Avoid adding a redundant manual remove step, especially under concurrency where another worker may have just saved a fresh refresh token. In concurrent systems, deletions should be coordinated and version-checked.

### 10.2. Never change the principal name to "dodge" `invalid_grant`

A wrong workaround:

```java
// WRONG: generating a new principal to bypass the rejected refresh token record.
.principal("user-782-" + java.util.UUID.randomUUID())
```

Changing the principal merely makes the manager look up a different key in storage. It **does not re-grant user permissions** and can create orphaned records or mix up tokens across Clients.

### 10.3. Never switch to Client Credentials when a user's refresh is rejected

If a user granted `calendar.read` via authorization code and refreshing is rejected, do not fall back to a `client_credentials` token to keep reading personal calendars. Application permissions and user permissions have distinct trust boundaries. If an API supports service-level access, that must be a separate architectural and authorization decision.

## 11. Prompting for Re-Login vs. Reauthorization?

The phrase "log in again" in OAuth2 UX can refer to at least three distinct actions:

| Action | Goal | When appropriate |
|---|---|---|
| **Re-login to the app** | Re-establish portal `SecurityContext`/session | User's app session expired or policy requires it |
| **Reauthorize external connection** | Reissue access/refresh tokens for the Client at the provider | Connection's refresh token was revoked/expired |
| **Reauthenticate at the IdP** | Require the user to authenticate again at the provider | Sensitive action or provider policy demands a fresh session |

These three **are not equivalent**.

For example, if the user is on the Spring app's dashboard with an active local session while their Microsoft Calendar connection reports `RECONNECT_REQUIRED`, the right UX is usually showing a **"Reconnect Microsoft account"** button rather than logging them out of the whole portal.

### 11.1. The provider's OIDC session may still be active

When the user is sent back to the Authorization Endpoint, the IdP may still have an active SSO session and issue a new authorization code **without showing a password prompt**. It is still a valid fresh reauthorization flow with `state`/PKCE and a callback.

If product policy requires the user to **genuinely reauthenticate**, you can use OIDC parameters like `prompt=login` or `max_age` where supported by the provider, and validate `auth_time` when needed. Never assume every IdP honors optional hints identically.

### 11.2. `offline_access` does not guarantee a permanent refresh token

Some OIDC Providers use the `offline_access` scope and consent rules to issue refresh tokens. However:

- Not every provider accepts `offline_access`.
- Specific Client settings or `prompt`/consent options may be required.
- Providers may enforce idle timeouts or absolute lifetimes.
- Users or administrators can revoke tokens at any time.
- Rotation and reuse detection still apply.
- Refresh tokens must not remain permanently valid after a user leaves an organization.

Therefore, the system **must always support a `RECONNECT_REQUIRED` recovery path**, even when `offline_access` was granted.

## 12. Designing Safe Reauthorization UX

A connection settings page might show:

```text
Calendar connection needs to be confirmed again.

Previous access expired or was revoked.
Data already synced in the app is preserved per policy.
[ Reconnect ]
```

The "Reconnect" button initiates **a new authorization flow from the backend**, never reusing the broken refresh token.

Example default Spring Security initiation link:

```html
<a href="/oauth2/authorization/calendar">
    Reconnect Calendar
</a>
```

The path `/oauth2/authorization/calendar` illustrates registration ID `calendar`. In products supporting multiple providers, the UI should only present server-approved registration IDs rather than building URLs from arbitrary user-supplied issuers.

### 12.1. Full flow of the "Reconnect" button

1. The user is authenticated in the app and authorized to manage that connection.
2. The backend checks that the record is `RECONNECT_REQUIRED` or eligible for reauthorization per policy.
3. For an existing external account connection, the backend creates a short-lived **pending-reauthorization context** bound to the account, connection, and session.
4. Spring initiates a new authorization request, generating `state` and PKCE/nonce as applicable.
5. The browser visits the Authorization Endpoint; the user authenticates/consents as required.
6. The provider returns a code to the callback; Spring validates the code, state, and ID Token (if OIDC).
7. The backend verifies that the newly authenticated external identity matches **the exact account connection** the user is reauthorizing.
8. The new authorized client is saved and the new refresh token is stored properly.
9. The pending context expires; the connection returns to `CONNECTED`.
10. Background tasks may resume per policy and updated permissions.

**Never replace `state` with an `accountId` or sensitive return URL**, and never bind a different external identity to the old connection just because the email matches. For OIDC, verify the `(iss, sub)` pair; for non-OIDC OAuth2, use the stable provider-published ID per contract.

### 12.2. Handling a user signing into the IdP with a different account

A dangerous bug: a user clicks reconnect for `connection_id=42` owned by Alice, yet selects Bob at the IdP. If the backend blindly writes Bob's tokens onto Alice's record, data leaks and identities get mixed.

Before replacing the authorized client, check:

- Is changing the external account linked to this connection permitted?
- If not, does the new subject/provider user ID match the previous identity?
- If account switching is allowed, is the user clearly informed and prompted to confirm?
- Do the new tokens match the right tenant, scope, audience, and `ClientRegistration`?
- Does the pending-reauthorization context belong to the currently logged-in internal account?

**Never use email as the sole proof** that two external identities belong to the same person.

### 12.3. Avoiding open redirects

Never blindly accept:

```text
/login?returnTo=https://evil.example.test
```

and redirect the user to that URL after OAuth2 completes. Use Spring's saved request mechanism or an allowlist of internal routes. If the app must redirect to an external frontend URL, allow only URLs from trusted server configuration.

## 13. Preventing Infinite Login Loops

A common failure mode:

```text
GET /dashboard
  -> Client calls API, refresh token returns invalid_grant
  -> redirects to /oauth2/authorization/company
  -> login/callback succeeds
  -> redirects to /dashboard
  -> Client again reads broken/unsaved authorized client
  -> redirects to /oauth2/authorization/company
  -> ...
```

### 13.1. Causes

- The old refresh token was not removed, or cache was not updated.
- After the callback, the new authorized client was not saved to the right repository/service.
- The principal name used when saving differs from the principal name used when reading.
- The user did not consent to offline access/scopes, so no refresh token was issued.
- Connection policy keeps marking `RECONNECT_REQUIRED` despite a successful callback.
- The callback issued tokens for a different registration or tenant.
- The app auto-redirects into the authorization flow **on every API request** with no circuit breaker.
- An error handler mistakes HTTP 403 for "needs re-login".

### 13.2. How to prevent it

1. Maintain a dedicated reauthorization state with a TTL and attempt limit.
2. When refresh fails, **return a business status** rather than auto-redirecting on every background/API request.
3. Initiate interactive flows only when the user clicks a button or under controlled rules.
4. After the callback, verify the new authorized client exists under the exact registration/principal with sufficient permissions.
5. If required scopes were not granted, display a clear error rather than looping back to login.
6. If the provider/user denies consent, do not continuously retry.
7. Use correlation IDs and flow states for debugging without logging raw `state` or tokens.

For SPAs calling JSON APIs, normally return an HTTP status and a code such as `RECONNECT_REQUIRED` so the frontend displays a button. Never turn every failed `fetch` into a redirect to the IdP login page returning HTML inside an XHR response.

## 14. Spring HTTP Clients: 401/403 Errors from the Resource Server

A subtle point: the manager handles errors **when requesting tokens**, whereas an API can still return errors **after the token is sent**.

### 14.1. Using `RestClient` and `OAuth2ClientHttpRequestInterceptor`

In supported Spring Security versions, `OAuth2ClientHttpRequestInterceptor` integrates `OAuth2AuthorizedClientManager` and can forward 401/403 errors from the Resource Server to an `OAuth2AuthorizationFailureHandler`.

You can configure a failure handler backed by `OAuth2AuthorizedClientService`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.web.client.RestClient;

@Bean
RestClient apiRestClient(
        OAuth2AuthorizedClientManager authorizedClientManager,
        OAuth2AuthorizedClientService authorizedClientService) {

    var interceptor =
        new OAuth2ClientHttpRequestInterceptor(authorizedClientManager);

    interceptor.setAuthorizationFailureHandler(
        OAuth2ClientHttpRequestInterceptor.authorizationFailureHandler(
            authorizedClientService
        )
    );

    return RestClient.builder()
        .requestInterceptor(interceptor)
        .build();
}
```

This is **an example of API failure handling**, not a complete configuration resolving registration/principal for every request. For background jobs, configure resolvers or request attributes appropriate to your version and service manager; never let the interceptor depend on an arbitrary web request's principal.

### 14.2. Does the handler delete on every 401/403?

Do not assume every HTTP 401/403 deletes the entire authorized client. `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` inspects the forwarded OAuth2 error code; exact behavior depends on the integration and version.

For example, a Resource Server returning `invalid_token` can stop the client from reusing the stale access token. With `insufficient_scope`, the problem is permissions; wiping out the refresh token can break a valid user connection without solving the missing scope.

With user-delegated refresh tokens, be especially careful with auto-removal after API 401s: **deleting the entire authorized client can discard a still-valid refresh token**. Choose your exact strategy based on error type, version, consent, and your product's reauthorization workflow.

### 14.3. `WebClient` also has failure-handler support

When using `ServletOAuth2AuthorizedClientExchangeFilterFunction`, Spring Security can forward 401/403 errors to an authorization failure handler. However, constructors taking a manager vs. a repository can have **different default failure-handling behavior** across versions.

Do not assume every `WebClient` automatically deletes authorized clients upon receiving a 401. Check your actual configuration and wire `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` explicitly if needed.

### 14.4. What if you set the Bearer header manually?

If code retrieves the token from the manager and calls the API directly:

```java
restClient.get()
    .uri("/api/events")
    .headers(h -> h.setBearerAuth(accessToken))
    .retrieve()
    .body(String.class);
```

then API errors do not flow through `OAuth2AuthorizedClientManager` the way refresh token errors do. You must handle responses/exceptions in the HTTP client layer and decide whether to invalidate the token, retry once, or halt the connection depending on the cause.

**Never retry infinitely** on 401/403; never forward tokens to URLs outside an allowlist, including when an HTTP client follows redirects automatically.

## 15. Retry and Backoff Rules by Error Type

Not every error is safe to retry.

| Error type | Auto-retry? | Reason |
|---|---|---|
| `invalid_grant` on refresh | **No** uncontrolled retries with same token | Token may be revoked/rotated; reuse detection risk |
| `invalid_client` | Not until config is fixed | Client credentials wrong/rejected |
| `invalid_scope` | Not before fixing requested permissions | Policy/consent error |
| HTTP 429 from Token Endpoint | Allowed, obeying `Retry-After` and caps | Rate limit; avoid overloading |
| Transient HTTP 5xx | Allowed with backoff and cap | Server error; with refresh rotation, note the prior request may have succeeded |
| Network timeout on refresh | **Use extreme caution** | Uncertain whether the old token was already consumed |
| API 401 `invalid_token` | May reacquire/retry boundedly per policy | Not necessarily a refresh error; diagnose |
| API 403 `insufficient_scope` | Do not retry with same scopes | Insufficient permissions |
| Browser authorization cancelled by user | Never loop infinitely | Respect the user's decision |

### 15.1. Exponential backoff cannot fix a revoked token

Backoff helps with network/load blips, yet if a refresh token was revoked, waiting 1, 2, 4, and 8 minutes and resending **the same refresh token** will never make it valid again.

Transition the system to `RECONNECT_REQUIRED`, pause related scheduled syncs, and notify the user when they can act, rather than firing thousands of doomed refresh requests.

### 15.2. Business operation idempotency differs from token retries

Suppose an invoicing job calls an API after getting a fresh token. If the API times out, retrying the API call could create duplicate invoices. That is a business-level idempotency problem requiring idempotency keys or transaction guards. Never assume solving token refresh makes every downstream retry safe.

## 16. Intentional Token Revocation per RFC 7009

Beyond external revocations, applications sometimes actively disconnect or revoke tokens when the user chooses "Disconnect".

**RFC 7009 — Token Revocation** defines an endpoint where the Client submits a token to request revocation. Simplified form request example:

```http
POST /oauth2/revoke HTTP/1.1
Host: login.example.test
Authorization: Basic EXAMPLE_CLIENT_AUTH
Content-Type: application/x-www-form-urlencoded

token=EXAMPLE_REFRESH_TOKEN&token_type_hint=refresh_token
```

Providers may require specific Client authentication and endpoint syntax conforming to the standard.

### 16.1. A revocation response does not prove the token was previously valid

Per RFC 7009, the endpoint may return HTTP 200 even if the token was already invalid; this prevents leaking token state via responses.

When a user disconnects, you should:

1. Verify the user is authorized to manage the connection.
2. If the provider supports revocation, request revocation of the appropriate credentials.
3. Delete the authorized client and app-side session/token state per policy.
4. Mark the business connection `DISCONNECTED`.
5. Record an audit event without tokens.
6. Coordinate jobs/queues so in-flight work stops using that connection.

**Logging out of an HTTP session and revoking a refresh token are not the same operation.** OIDC RP-Initiated Logout is also a separate mechanism governing the session at the OP.

### 16.2. Revoking a refresh token affects access tokens differently across providers

Some providers revoke the entire grant/token family, while others handle access tokens separately. Never assume every issued access token immediately stops working when a refresh token is revoked; that depends on token format, Resource Server validation, and provider policy.

If immediate access cut-off is required, enforce it on the Authorization Server / Resource Server side (revocation/introspection/session control) rather than merely deleting a record in the Spring Client.

## 17. Managing State Across Multiple Instances

A production deployment typically has multiple pods:

```text
Pod A: HTTP callback / user session
Pod B: Scheduled Sync Job
Pod C: Queue Consumer
Shared Database: authorized clients + connection state
Authorization Server: refresh token rotation
```

Situations to handle:

- Pod A just saved a new refresh token, while Pod B still holds a stale cache.
- Pod B's refresh fails due to rotation, yet Pod C had already succeeded earlier.
- On Pod A the user disconnects, while Pod B is still processing an older message.
- Two workers both flip business state to `RECONNECT_REQUIRED`, clobbering another worker's successful state.
- A backup/restore resurrects an already-used refresh token and triggers reuse detection.

### 17.1. Durable token storage and atomic updates

`InMemoryOAuth2AuthorizedClientService` neither shares tokens across instances nor survives restarts. `JdbcOAuth2AuthorizedClientService` provides durable storage, yet **does not automatically solve every race**.

With strict refresh token rotation, you can design:

```text
Lock key: registrationId + principalName
    -> re-read latest authorized client
    -> if token still needs refresh, call AS once
    -> save new access + refresh tokens safely
    -> release lock
```

Without locking, use versioned optimistic locking to prevent stale writes. Choose the model based on provider behavior and task frequency. Never use a single global lock across all users if it introduces unnecessary contention.

### 17.2. On `invalid_grant` from a race, should you immediately mark reconnect?

In a concurrent system, one worker may receive `invalid_grant` because another worker already legitimately consumed the old token. However, the provider may also have revoked the entire token family on reuse; you cannot safely assume the newer token is definitely still good.

One strategy:

1. Record a refresh-conflict event without logging tokens.
2. Check the latest version and authorized client state from the trusted store.
3. If another worker updated the token, evaluate provider policy and whether the token family may still be valid.
4. Never let late cleanup delete the newer token record.
5. When uncertain, transition to needing reauthorization and notify rather than retrying endlessly.
6. Prevent recurrence with proper coordination.

**Key point:** Spring manager's default cleanup is useful, yet does not replace cluster-wide concurrency design. If overriding the handler to add version-aware cleanup, respect the library contract and do not accidentally bypass required checks.

### 17.3. Multi-tenant and per-user isolation

An `OAuth2AuthorizedClientService` normally keys tokens by `(clientRegistrationId, principalName)`. Therefore:

- Never share one principal name across multiple distinct users.
- Never allow a message from tenant A to specify a principal belonging to tenant B.
- Bind principals to verified internal accounts/connections.
- Tokens issued for Resource Server A must not be reused for Resource Server B.
- When disconnecting a connection, delete only tokens matching that exact registration and principal.
- If a provider supports multiple tenants/issuers, enforce issuer/`ClientRegistration` consistency.

## 18. When Should You Require the User to Re-Login Completely?

Do not assume every `invalid_grant` forces a full application logout. Some policies may require:

### 18.1. Apps directly tied to the OP session

If product rules dictate users may only access the portal while their OP session remains valid, token revocation can trigger policy-driven reauthentication. Still, distinguish OP session expiration from refresh token rejection—no OAuth2 rule says both always happen together.

### 18.2. External API connections that are auxiliary features

If a user is logged into a portal and a Calendar API connection expires, good UX usually:

- Keeps the portal session active.
- Pauses Calendar sync features.
- Displays `RECONNECT_REQUIRED`.
- Opens the reconnect flow when the user chooses.
- Preserves internal data outside the connection scope.

### 18.3. Severe security incidents

When there is evidence of token theft or refresh token reuse causing family revocation, an organization may choose to:

- Disable the connection immediately.
- Revoke related credentials.
- Require strong-factor reauthentication on the account.
- Alert the user per policy.
- Audit logs for anomalous access patterns.

That is an incident-response plan driven by reliable signals—not an automatic reaction to every HTTP 400.

## 19. Designing Business State for OAuth2 Connections

A reference schema:

```sql
CREATE TABLE oauth_connection (
    id UUID PRIMARY KEY,
    internal_account_id UUID NOT NULL,
    registration_id VARCHAR(128) NOT NULL,
    principal_name VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL,
    last_success_at TIMESTAMP WITH TIME ZONE,
    reconnect_required_at TIMESTAMP WITH TIME ZONE,
    failure_code VARCHAR(80),
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT ck_oauth_connection_status
      CHECK (status IN (
        'CONNECTED',
        'RECONNECT_REQUIRED',
        'DISCONNECTED'
      ))
);
```

Meaning:

- `internal_account_id` links to the verified internal business account owner.
- `registration_id` and `principal_name` point to the authorized client in the token store.
- `status` tells the UI and jobs whether the connection may continue running.
- `failure_code` holds only a sanitized error code, never raw HTTP responses.
- `version` supports optimistic concurrency if implemented by the application.
- Real tokens live in `OAuth2AuthorizedClientService` or a dedicated secure store, never in plaintext columns of a business table.

A connection can still appear with metadata even after its tokens are removed upon entering `RECONNECT_REQUIRED`. That is a valid state.

### 19.1. Minimal auditing

Useful audit events:

```text
CONNECTION_AUTHORIZED
TOKEN_REFRESH_SUCCEEDED
TOKEN_REFRESH_FAILED_INVALID_GRANT
CONNECTION_RECONNECT_REQUIRED
CONNECTION_REAUTHORIZED
CONNECTION_DISCONNECTED
```

Never store access tokens, refresh tokens, authorization codes, or raw ID Tokens in audit logs. For user/tenant identifiers, enforce appropriate access controls.

## 20. Step-by-Step Diagnostic Workflow for `invalid_grant`

When an error appears, investigate **in order**:

1. **Locate the failure:** Token Endpoint or downstream API?
2. **Check `grant_type`:** `refresh_token` or `authorization_code`?
3. **Record the OAuth2 error code:** `invalid_grant`, `invalid_client`, `invalid_scope`... without logging tokens.
4. **Verify registration ID and environment:** Is there a staging/prod/tenant or Client ID mix-up?
5. **Check when the last refresh succeeded:** Is refresh token rotation active?
6. **Check concurrency:** Are multiple pods/requests refreshing the same authorized client?
7. **Inspect storage:** Were new tokens saved, or is a stale cache serving old ones?
8. **Inspect provider audit logs if permitted:** Revocation, user consent, session timeout, or policy change?
9. **Separate transient errors from invalid credentials:** Do not retry `invalid_grant` with the same token; handle timeouts/5xx with dedicated policies.
10. **Check Spring's default cleanup:** Is the manager using a service or repository, and did a custom failure handler override it?
11. **Assess account state:** Is the portal session still valid? Does the external connection need reauthorization?
12. **Prepare safe reconnect UX:** right provider, right account, right permissions, and protected account linking.
13. **Verify after reconnecting:** Does the new authorized client hold valid tokens, sufficient scopes, and do jobs resume cleanly?

### 20.1. Safe logging example

```text
event=oauth_refresh_failed
registrationId=calendar
principalCategory=user
grantType=refresh_token
errorCode=invalid_grant
connectionStatus=RECONNECT_REQUIRED
correlationId=8f6e... (random internal ID)
```

Never log:

```text
refresh_token
access_token
id_token
Authorization: Basic/Bearer
OAuth2 authorization code
raw token response or unfiltered error_description
session cookie
```

The error code and correlation ID are usually enough for telemetry investigation without exposing credentials.

### 20.2. Is `DEBUG`-level logging safe enough?

Even with `org.springframework.security=DEBUG`, HTTP clients, proxies, or APM tooling can capture token requests/responses if logging is too broad. Audit the entire pipeline; never upload HAR files, traces, or exception dumps containing real tokens to unsuitable support systems.

## 21. Common Error Reference Table

| Symptom | Possible cause | Resolution |
|---|---|---|
| Refresh Token Endpoint returns `invalid_grant` | Token expired/revoked/rotated/wrong Client | Stop reuse, clean up state, prompt reauthorization when needed |
| First refresh succeeds, next fails immediately | New token wasn't saved, or worker used old RT | Inspect rotation and persistence |
| Errors occur only across multiple pods | Concurrent refresh / reuse detection | Single-flight, locking, optimistic locking |
| Old token still used after refresh | Stale cache or failed update | Reload storage, coordinate updates |
| HTTP API returns 401 while access token unexpired | Revocation/audience/issuer/API policy | Check Resource Server; do not jump to "refresh invalid" |
| API returns 403 `insufficient_scope` | Token lacks permissions | Handle consent/scopes; do not refresh endlessly |
| `invalid_client` at Token Endpoint | Wrong secret or auth method | Fix Client configuration |
| `invalid_grant` at login callback | Authorization code/PKCE/Redirect URI error | Debug OAuth2 Login; do not conflate with refresh failure |
| User stays logged into portal while Calendar needs reconnect | HTTP session and external token lifecycles differ | Keep session per policy, reconnect the specific connection |
| Still fails after reconnect | Saved under wrong principal/registration or missing scope | Check storage, user identity, granted scopes |
| Login redirect loop | State not updated, auto-redirecting on every API call | Cap retries, use explicit UI reconnect |
| No refresh token | AS did not grant offline access, policy/consent | Check registration and grant setup |
| After local revocation, API still accepts old token | Deleting client store does not block Resource Server | Enforce AS revocation/resource validation |
| Background worker cannot auto-reconnect | Flow requires user agent/consent | Mark `RECONNECT_REQUIRED` and notify user |
| Custom failure handler fails to delete broken token | Overrode manager's default cleanup | Preserve required behavior or configure appropriate handler |
| API failure handler deletes still-valid refresh token | Overly broad auto-remove policy | Classify 401/403; preserve token lifecycle per requirements |
| Changed `principalName` to bypass error | Broken authorized client mapping | Use stable principal bound to user/tenant |
| Swapped user token for Client Credentials | Mixed trust boundaries | Separate service permissions from user consent |

## 22. Practice Scenarios

### Exercise 1: Distinguishing errors

The Client calls the Token Endpoint:

```http
POST /token
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=EXAMPLE_RT
```

The server returns:

```json
{"error":"invalid_grant"}
```

**Question:** Can you conclude the refresh token was revoked by an admin?

**Suggested answer:** No. It could be expired, revoked, rotated, or belong to another Client. The immediate priority is not retrying the old token infinitely, handling the broken authorized client, and investigating the root cause as needed.

### Exercise 2: Do not confuse 401 with `invalid_grant`

The Resource Server returns:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

**Suggested answer:** This is an API-level access token error. The token may be expired, revoked, have the wrong audience, or hit another issue. Never conclude the refresh token is broken without an actual failed token refresh attempt.

### Exercise 3: Two pods refreshing together

Pod A uses RT-1 successfully and receives RT-2. Pod B just sent RT-1 and received `invalid_grant`.

**Suggested answer:** A rotation race condition occurred. Coordinate refreshes and persist the latest token; check whether reuse-detection policy also revoked RT-2. Never keep retrying RT-1.

### Exercise 4: Session active while connection fails

The user navigates the portal normally, yet the Google Calendar connection needs reconnecting.

**Suggested answer:** Show `RECONNECT_REQUIRED` for Calendar. Do not force a full portal logout unless policy explicitly requires it.

### Exercise 5: No refresh token in response

Token response:

```json
{
  "access_token": "EXAMPLE_AT",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "openid profile"
}
```

**Suggested answer:** You cannot use a refresh grant from this response. Check whether the provider issues refresh tokens for that flow/consent; when the access token expires, a fresh authorization flow may be required.

### Exercise 6: Deleting tokens after errors

`DefaultOAuth2AuthorizedClientManager` was given a custom failure handler that only logs; afterward, a refresh job keeps resending the stale token endlessly.

**Suggested answer:** The custom handler likely replaced the default `invalid_grant` cleanup behavior. Configure the handler to remove the failing authorized client from the right repository and bound retries. Never log raw tokens.

### Exercise 7: Reconnecting with a different account

A user starts reconnecting Alice's external account, yet chooses Bob at the IdP.

**Suggested answer:** Never silently overwrite the old external identity with Bob. Compare the callback's identity against the connection being reauthorized; if switching accounts is desired, require explicit confirmation and a dedicated flow.

### Exercise 8: 403 on insufficient scope

The Calendar API requires `calendar.write` while the token only has `calendar.read`, and the API returns 403.

**Suggested answer:** Refreshing for another token with the same read scope will not solve it. Determine whether the user wants/can grant write access, update scopes/consent per provider, and follow least-privilege policy.

### Exercise 9: Retrying after a timeout

A refresh request with RT-1 times out, so the Client does not know whether the AS issued RT-2.

**Suggested answer:** Never assume retrying RT-1 is always safe. With rotation, the AS may already have consumed RT-1. Follow a provider-appropriate retry/coordination strategy; if the new state is lost, reauthorization may be necessary.

### Exercise 10: Local token deletion vs. revocation

The application deletes `OAuth2AuthorizedClient` from the database when the user selects Disconnect.

**Suggested answer:** That stops the application from reusing the stored token, yet **does not automatically guarantee the Authorization Server or Resource Server revoked the credentials**. When provider-side revocation is required, use the supported revocation endpoint and manage the full lifecycle.

## 23. Most Important Principles

- **`invalid_grant` at the Token Endpoint is a general error code**, not sole proof of revocation.
- **Refresh tokens can expire, be revoked, or be replaced by rotation**; never treat them as permanent credentials.
- **Never infinitely retry a rejected refresh token**, especially when the provider enforces reuse detection.
- **Separate Token Endpoint `invalid_grant` from Resource Server 401/403**; they have different origins and remedies.
- **Spring Security managers include default `invalid_grant` cleanup**, so preserve necessary state-removal logic if replacing the failure handler.
- **Delete only the failing authorized client**; never wipe the entire HTTP session, internal account, or unrelated connections without explicit policy.
- **An HTTP session can remain valid** even when an external API connection needs reauthorization.
- **Reauthorization requires a new authorization flow**, usually interactive; background workers cannot create consent on their own.
- **Verify identity at the callback during reconnect** to prevent accidental external account swaps or account-linking vulnerabilities.
- **Rotation race conditions are a security risk**, not just a performance bug; persist new tokens and synchronize workers.
- **Revocation at the Authorization Server differs from local token deletion**; review RFC 7009 and provider policies.
- **Avoid logging tokens, codes, cookies, and sensitive error payloads.** Prefer error codes and connection statuses.
- **Never substitute client credentials for a user-delegated token** to work around errors or bypass consent.
- **Provide `RECONNECT_REQUIRED` UX and state** so users can proactively restore connections when needed.

## 24. References

1. [RFC 6749 — OAuth 2.0, Section 5.2](https://www.rfc-editor.org/rfc/rfc6749#section-5.2): token error responses and `invalid_grant`.
2. [RFC 6749 — Section 6: Refreshing an Access Token](https://www.rfc-editor.org/rfc/rfc6749#section-6): refresh grant, validation, and replacing refresh tokens.
3. [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `invalid_token`, `insufficient_scope`, and Resource Server HTTP statuses.
4. [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): active token revocation and revocation endpoint responses.
5. [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): refresh token security, rotation/replay detection, and Client protection.
6. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): authorization code, token endpoint, `offline_access`, and OIDC requirements.
7. [Spring Security Reference — Servlet OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): managing OAuth2 Clients and grants.
8. [Spring Security Reference — Authorized Clients](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html): `RestClient`/`WebClient` integration and failure handling.
9. [Spring Security API — `DefaultOAuth2AuthorizedClientManager`](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizedClientManager.html): default removal of authorized clients on `invalid_grant`.
10. [Spring Security API — `AuthorizedClientServiceOAuth2AuthorizedClientManager`](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html): service manager and failure handling outside Servlet requests.
11. [Spring Security API — `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler`](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/RemoveAuthorizedClientOAuth2AuthorizationFailureHandler.html): authorized client removal policy by OAuth2 error.
12. [Spring Security API — `OAuth2ClientHttpRequestInterceptor`](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/client/OAuth2ClientHttpRequestInterceptor.html): forwarding API 401/403 errors to the authorization failure handler when configured.

## 25. Summary

**`invalid_grant` in a Refresh Token Grant signals that the Authorization Server rejects the current refresh credential.** It can stem from expiration, revocation, rotation, a mismatched Client, or provider policy; thus the error code alone cannot identify a single cause.

In **Spring Security OAuth2/OIDC Client**, the resilient approach is using `OAuth2AuthorizedClientManager` with the right grant providers, preserving cleanup on refresh failures, preventing refresh token reuse/races, and separating connection state from website login state. When user permissions can no longer be refreshed, transition the connection to **`RECONNECT_REQUIRED`** and let the user run a fresh **Authorization Code/OIDC flow** verifying the exact Client, identity, and consent. These practices prevent refresh loops, reduce token replay risk, and keep the user experience consistent even when provider permissions are revoked.
