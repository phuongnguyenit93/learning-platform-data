# 17.7. Handling Refresh Tokens Omitted from the Response

## Lesson Objectives

In **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client**, an application can retain a **refresh token** to obtain a new access token when the current access token expires or is about to expire. One scenario that causes many systems to accidentally lose the ability to renew tokens is: **the token endpoint returns a successful refresh response without a `refresh_token` field**.

This is **not automatically an error**. Under OAuth 2.0, the Authorization Server (AS) **may** issue a new refresh token when handling a refresh token grant; it is not required to issue a new one in every response. When the client already holds refresh token R1, a successful refresh response returning only access token A2 normally means the client **keeps the existing R1**. If the response also returns a new refresh token R2, the client must **replace R1 with R2**.

Contrast this clearly with an **initial token response that contains no refresh token**. When R1 was never received in the first place, the client cannot renew its access token via the refresh token grant and has no existing token to retain.

After this lesson, you will be able to:

- Distinguish an initial token response from a refresh token grant response.
- Read responses with or without `refresh_token` and understand their token-lifecycle consequences.
- Explain **keeping the old refresh token when no new one is returned** and **replacing the old token when the AS issues a new one**.
- Understand how `OAuth2AccessTokenResponse`, `OAuth2AuthorizedClient`, `RefreshTokenOAuth2AuthorizedClientProvider`, and the manager coordinate.
- Spot custom-code bugs that accidentally overwrite a stored refresh token with `null`.
- Handle `invalid_grant`, token rotation, malformed responses, and concurrent refresh requests.
- Protect tokens in repositories, sessions, multi-instance deployments, and during logout.
- Distinguish access token refreshing from OIDC reauthentication, ID tokens, and Resource Server authorization.

## 1. Context: Refresh Response Missing a New Token

Suppose **Employee Portal** uses Spring Boot with OIDC Authorization Code Login against an enterprise OpenID Provider (OP). After login, the Portal needs an access token to call the **Orders API**.

The token response after Authorization Code exchange might be:

~~~json
{
  "access_token": "ACCESS_A1",
  "token_type": "Bearer",
  "expires_in": 600,
  "refresh_token": "REFRESH_R1",
  "id_token": "ID_TOKEN_1",
  "scope": "openid profile orders.read"
}
~~~

The token strings are placeholders, not real tokens. Spring Security validates the OIDC result, establishes the principal, and stores an `OAuth2AuthorizedClient` containing access token A1 and refresh token R1.

Later, A1 expires. The client calls the token endpoint using R1:

~~~http
POST /oauth2/token HTTP/1.1
Host: id.example.com
Authorization: Basic <CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=REFRESH_R1
~~~

This request illustrates confidential client authentication using HTTP Basic; real clients must use the method registered with the AS.

The AS returns:

~~~json
{
  "access_token": "ACCESS_A2",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "openid profile orders.read"
}
~~~

**There is no `refresh_token`.** Such a token response can be completely valid: the AS issued a new access token without issuing a replacement refresh token.

Expected state:

~~~text
Before refresh:
  accessToken  = A1
  refreshToken = R1

Response:
  accessToken  = A2
  refreshToken = field absent

Authorized client after update:
  accessToken  = A2
  refreshToken = R1
~~~

If custom code naively takes `response.getRefreshToken()` and writes it straight into the authorized client, the application can accidentally store `refreshToken = null`, leaving the next refresh with no credential.

## 2. Key Question: Did a Refresh Token Exist Before the Response?

| Case | Prior refresh token | Current response | State after processing |
|---|---|---|---|
| Initial Authorization Code token issuance | None yet | A1, no refresh token | A1, no refresh token |
| Initial Authorization Code token issuance | None yet | A1 + R1 | A1 + R1 |
| Refresh token grant, no rotation this turn | Already has R1 | A2, no new refresh token | A2 + R1 |
| Refresh token grant with rotation | Already has R1 | A2 + R2 | A2 + R2; discard R1 |
| Refresh grant fails | May still have R1 | OAuth error such as `invalid_grant` | Handle error; do not treat as successful refresh |

The difference is not whether the JSON happens to contain a `refresh_token` field in isolation. What matters more is the **grant context** and the **authorized client state prior to executing the grant**.

### 2.1. Never issued a refresh token initially

Initial token response:

~~~json
{
  "access_token": "ACCESS_A1",
  "token_type": "Bearer",
  "expires_in": 600,
  "id_token": "ID_TOKEN_1"
}
~~~

The client can sign the user in and call APIs with A1, yet it has no R1. When A1 expires, the `refresh_token` provider has no refresh token to use. The application may need to initiate a new Authorization Code flow or use another grant permitted by the AS.

**Never fabricate a refresh token from an ID token, access token, or old authorization code.**

### 2.2. Already have R1, refresh response does not issue R2

If the AS processes the refresh token grant successfully and returns access token A2 without issuing a new refresh token, in the standard model the client retains R1 for future use.

This **is not a guarantee that R1 will remain valid forever**. The AS can still limit its lifetime, revoke it, enforce usage-count limits, or change token issuance rules for the client.

### 2.3. Already have R1, refresh response issues R2

If the response contains R2:

~~~json
{
  "access_token": "ACCESS_A2",
  "token_type": "Bearer",
  "expires_in": 600,
  "refresh_token": "REFRESH_R2"
}
~~~

The client must save A2/R2 and **discard R1**. Keeping R1 as a backup token can violate rotation policy or trigger reuse detection if sent again.

## 3. What Does OAuth 2.0 Specify?

### 3.1. A new refresh token is not required in every refresh response

Under OAuth 2.0, the AS **may issue a new refresh token** when a client executes the refresh token grant. When a new token is issued, the client must replace the old one with the new one.

Therefore:

- **No new token in a successful response:** do not assume the AS wants you to delete the old token.
- **New token in a successful response:** stop using the old token as a valid credential.
- **AS returns an OAuth error:** do not construct a new authorized client from an error response.

This logic is critical when building custom providers or integrating token stores.

### 3.2. Refresh tokens differ from authorization codes

An authorization code is a short-lived, **single-use** value exchanged for tokens. Do not assume every refresh token must also be single-use.

An AS may implement:

- Refresh tokens reusable multiple times until expiration or revocation.
- Refresh token rotation, issuing a new token on every successful refresh.
- Token family policies and reuse detection for already-rotated tokens.
- Binding refresh tokens to clients and other security constraints.

The client must conform to the contract of the AS in use.

### 3.3. Do not equate an absent token with an invalid token value

Three distinct cases:

~~~json
{
  "access_token": "ACCESS_A2",
  "token_type": "Bearer",
  "expires_in": 600
}
~~~

~~~json
{
  "access_token": "ACCESS_A2",
  "token_type": "Bearer",
  "expires_in": 600,
  "refresh_token": null
}
~~~

~~~json
{
  "access_token": "ACCESS_A2",
  "token_type": "Bearer",
  "expires_in": 600,
  "refresh_token": ""
}
~~~

An **absent** `refresh_token` is different from returning JSON `null` or an empty string. The latter two are not valid refresh tokens. They may indicate a provider returning malformed schema or a non-standard convention that the client should not silently accept.

Never treat an empty string as a new token. Let the token response client validate the response against the actual contract.

### 3.4. A successful response still requires a valid access token

A response like:

~~~json
{
  "token_type": "Bearer",
  "expires_in": 600
}
~~~

does not become a valid refresh response merely because its HTTP status is 200. A successful token response requires mandatory OAuth fields, including an access token and token type.

**Omitting a new refresh token can be valid; omitting the access token in a successful token response is a completely different problem.**

## 4. Timeline When the AS Does Not Rotate Every Turn

Suppose the AS allows R1 to be used multiple times:

~~~text
T0  Authorization Code succeeds:
    issues A1 + R1
    client saves A1/R1

T1  A1 expires:
    sends refresh_token=R1
    AS returns A2, no R2
    client saves A2/R1

T2  A2 expires:
    sends refresh_token=R1
    AS returns A3, no R3
    client saves A3/R1

T3  R1 expires or is revoked:
    AS returns invalid_grant
    client handles fresh authorization if needed
~~~

This is a valid model when the AS permits reusing refresh tokens within their validity window. Even so, the AS may reject at any time per policy; the client must not treat R1 as a permanent credential.

## 5. Timeline When the AS Uses Refresh Token Rotation

Rotation model:

~~~text
T0  Initial:
    A1 / R1

T1  Use R1:
    AS issues A2 / R2
    client replaces R1 with R2

T2  Use R2:
    AS issues A3 / R3
    client replaces R2 with R3

T3  Reuse R1:
    AS rejects per reuse policy
~~~

Points to remember:

- When a new refresh token is returned, **persist the new token**.
- Never keep the old refresh token as a default fallback.
- Prevent other requests from overwriting the new token pair with stale data.
- Some AS implementations revoke the token family if a rotated token is reused.

**The rule of keeping R1 applies only when a successful response provides no replacement token—never when the response already issued R2.**

## 6. How Does Spring Security Represent Refresh Results?

### 6.1. `OAuth2AccessTokenResponse`

Spring Security represents token endpoint responses using:

~~~java
org.springframework.security.oauth2.core.endpoint.OAuth2AccessTokenResponse
~~~

This object holds `OAuth2AccessToken`, `OAuth2RefreshToken` if present, scopes, and related metadata.

For a refresh response without `refresh_token`, calling:

~~~java
OAuth2RefreshToken returnedRefreshToken =
        tokenResponse.getRefreshToken();
~~~

can return `null`.

**Here `null` means the current response had no new refresh token**; it does not prove R1 in the existing authorized client was revoked by the AS.

### 6.2. `OAuth2AuthorizedClient`

The stored authorized client holds:

~~~java
OAuth2AccessToken currentAccessToken =
        authorizedClient.getAccessToken();

OAuth2RefreshToken storedRefreshToken =
        authorizedClient.getRefreshToken();
~~~

When building the updated post-refresh state, inspect **both the token response** and **the existing authorized client**.

### 6.3. `RefreshTokenOAuth2AuthorizedClientProvider`

Spring Security's refresh token provider:

~~~java
org.springframework.security.oauth2.client.RefreshTokenOAuth2AuthorizedClientProvider
~~~

In a standard refresh flow, the provider follows the rule:

~~~text
updatedAccessToken = response.accessToken

updatedRefreshToken =
    response.refreshToken != null
        ? response.refreshToken
        : existingAuthorizedClient.refreshToken
~~~

When the response includes R2, R2 is chosen. When the response omits a new token, R1 from the existing authorized client is retained. **This is a key behavior that prevents losing refresh tokens when using the standard provider.**

### 6.4. `OAuth2AuthorizedClientManager`

The manager coordinates:

~~~text
OAuth2AuthorizedClientManager
├── ClientRegistrationRepository
├── OAuth2AuthorizedClientRepository / Service
├── OAuth2AuthorizedClientProvider
│   └── RefreshTokenOAuth2AuthorizedClientProvider
└── Authorization success / failure handlers
~~~

After a successful refresh, the manager saves the updated authorized client via its success handler. Ensure the write location and read location are consistent; if two different repositories/services are used, subsequent requests may see stale data.

## 7. Java Illustration: Avoiding Overwriting R1 with `null`

### 7.1. Merging the response into the stored authorized client

Illustrative update logic:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;
import org.springframework.security.oauth2.core.endpoint.OAuth2AccessTokenResponse;

public final class RefreshResultMerger {

    private RefreshResultMerger() {}

    public static OAuth2AuthorizedClient merge(
            OAuth2AuthorizedClient existing,
            OAuth2AccessTokenResponse response) {

        OAuth2RefreshToken newRefreshToken =
                response.getRefreshToken();

        OAuth2RefreshToken effectiveRefreshToken =
                newRefreshToken != null
                        ? newRefreshToken
                        : existing.getRefreshToken();

        return new OAuth2AuthorizedClient(
                existing.getClientRegistration(),
                existing.getPrincipalName(),
                response.getAccessToken(),
                effectiveRefreshToken);
    }
}
~~~

This is **explanatory code**, not a suggestion that every project should implement its own refresh provider. In applications using Spring Security's standard manager/provider, retaining the old refresh token is already handled by the provider.

### 7.2. Outcomes for the three cases

| Prior authorized client | Response | Merge result |
|---|---|---|
| A1/R1 | A2, no R2 | A2/R1 |
| A1/R1 | A2/R2 | A2/R2 |
| A1, null refresh token | A2, no refresh token | A2, null refresh token |

This method never fabricates a refresh token if the AS never issued one.

### 7.3. Incorrect merge that loses the token

~~~java
// Logic bug: response missing refresh_token wipes out R1.
OAuth2AuthorizedClient updated = new OAuth2AuthorizedClient(
        existing.getClientRegistration(),
        existing.getPrincipalName(),
        response.getAccessToken(),
        response.getRefreshToken());
~~~

If the response has no refresh token, the final value becomes `null`. The application loses the ability to refresh next time.

**Do not "fix" this by mutating the AS's JSON response to inject R1.** Keep a clean distinction between what the AS actually returned and the state the client maintains in `OAuth2AuthorizedClient`.

## 8. Configuring Spring Boot OIDC Client

### 8.1. Dependency

Maven example:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

### 8.2. Registration

`application.yml` example:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-oidc
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
          company-oidc:
            issuer-uri: https://id.example.com/realms/company
~~~

- `corporate` is Spring Security's registration ID.
- `openid` indicates the client uses OpenID Connect.
- `orders.read` is an illustrative API scope that must be allowed by both the AS and API.
- `issuer-uri` identifies the trusted OP.
- Client secrets are provided via environment variables or a secret manager.

**Configuring OIDC Login alone does not guarantee a refresh token will always be issued.** That depends on the AS, client type, scopes, consent, and policies.

### 8.3. Is `offline_access` required?

In OIDC, the `offline_access` scope relates to requesting access when the End-User is not present. Some providers use this scope or separate client settings to decide whether to issue refresh tokens.

Never claim that:

- Having `openid` always yields a refresh token.
- Adding `offline_access` guarantees a refresh token.
- Every OP shares the same consent requirements for refresh tokens.
- Long-lived tokens require no security risk evaluation.

When **the initial token response lacks R1**, check the provider's documentation/contract, client registration, and authorization policy; never invent a token.

### 8.4. Servlet filter chain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .oauth2Client(Customizer.withDefaults())
                .build();
    }
}
~~~

`oauth2Login()` handles the browser redirect/callback flow; `oauth2Client()` enables authorized client usage when calling APIs per configuration.

## 9. Enabling the Refresh Provider in `OAuth2AuthorizedClientManager`

Example Servlet manager:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class AuthorizedClientManagerConfig {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository repository) {

        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .authorizationCode()
                        .refreshToken()
                        .build();

        DefaultOAuth2AuthorizedClientManager manager =
                new DefaultOAuth2AuthorizedClientManager(
                        registrations,
                        repository);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

With this setup:

1. The manager locates the authorized client for the registration/principal.
2. If the token is still usable, the manager returns the stored client.
3. If refresh is needed and a refresh token exists, the provider executes the refresh token grant.
4. If the AS returns A2 without R2, the provider retains the existing R1.
5. The updated authorized client is persisted by the manager's success handler.

Do not assume every `authorize()` call hits the token endpoint.

### 9.1. Flow when refresh response omits R2

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Controller / HTTP Client
    participant Manager as OAuth2AuthorizedClientManager
    participant Repo as Authorized Client Repository
    participant Provider as Refresh Token Provider
    participant AS as Authorization Server
    App->>Manager: authorize(corporate, Alice)
    Manager->>Repo: load authorized client
    Repo-->>Manager: A1 / R1
    Manager->>Provider: reauthorize when needed
    Provider->>AS: refresh_token=R1
    AS-->>Provider: access_token=A2, no R2 issued
    Note over Provider: Retain R1 from old authorized client
    Provider-->>Manager: A2 / R1
    Manager->>Repo: save A2 / R1
    Manager-->>App: updated authorized client
~~~

No mutation of the raw AS response is needed. State merging happens cleanly inside the client/provider.

## 10. Reading Token Status Without Exposing Credentials

In a Servlet controller, you can receive the authorized client:

~~~java
import java.time.Instant;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AuthorizedClientStatusController {

    @GetMapping("/client-status")
    TokenStatus status(
            @RegisteredOAuth2AuthorizedClient("corporate")
            OAuth2AuthorizedClient client) {

        if (client == null) {
            return new TokenStatus(false, false, null);
        }

        return new TokenStatus(
                client.getAccessToken() != null,
                client.getRefreshToken() != null,
                client.getAccessToken() != null
                        ? client.getAccessToken().getExpiresAt()
                        : null);
    }

    record TokenStatus(
            boolean hasAccessToken,
            boolean hasRefreshToken,
            Instant accessTokenExpiry) {}
}
~~~

This example never returns raw tokens. In production, a status endpoint also requires authentication/authorization policies and should return only genuinely needed fields.

### 10.1. Returning the refresh token to the frontend is misuse

Never return:

~~~json
{
  "refresh_token": "REFRESH_R1"
}
~~~

just to let the frontend know "a token exists". Use a boolean flag like `hasRefreshToken` if the UI really needs to show connection status. Refresh tokens must remain in secure storage appropriate to your architecture.

### 10.2. ID tokens are not access tokens

`OidcUser.getIdToken()` authenticates the End-User to the RP. When calling the Orders API, use the API-scoped access token from the authorized client.

Never fall back to the ID token for calling APIs when no refresh token is returned.

## 11. Repository/Service Must Persist Updated State

Related abstractions:

| Abstraction | Responsibility |
|---|---|
| `OAuth2AuthorizedClientRepository` | Saves/loads/removes authorized clients per Servlet request/response |
| `OAuth2AuthorizedClientService` | Saves/loads/removes by registration ID + principal |
| `HttpSessionOAuth2AuthorizedClientRepository` | `HttpSession`-based implementation |
| `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` | Can delegate authenticated principals to a service while using a session repository for anonymous users |
| `OAuth2AuthorizedClientManager` | Coordinates providers and success/failure handling |

After a successful refresh, data must be written to **the exact store that subsequent requests read from**.

Example:

~~~text
Refresh on Portal A:
  load A1/R1
  AS returns A2, no R2
  save A2/R1

Next request on Portal B:
  must see A2/R1 if using a shared store
~~~

If B uses an isolated store, it may still see A1/R1 or no authorized client at all. That is a storage issue, not necessarily the AS "failing to return a refresh token".

### 11.1. `saveAuthorizedClient` with a service

A valid authorized client can be persisted via:

~~~java
OAuth2AuthorizedClient updated = ...;  // Result from manager/provider
Authentication principal = ...;        // Authenticated principal

authorizedClientService.saveAuthorizedClient(updated, principal);
~~~

This snippet illustrates the interface only. If the manager's success handler already saves the authorized client, do not redundantly save it again in every controller.

### 11.2. Tokens must belong to the exact principal

If Alice and Bob both use registration `corporate`, Alice's token must never be reused in Bob's requests.

If custom persistence keys only by a global `registrationId` without principal/session isolation, tokens can get mixed across users.

With multiple OIDC issuers or tenants, the identity key should rest on a trusted internal identity bound to `(iss, sub)` rather than email or bare `sub` without the issuer.

## 12. Cases Where Custom Code Easily Loses R1

### 12.1. Overwriting the object from the new response

Wrong pattern:

~~~text
existing authorized client = A1/R1
token response             = A2/no R2

custom object mapper:
  access_token  <- response.access_token
  refresh_token <- response.refresh_token (null)
~~~

Result: `A2/null`. Next time, R1 is gone.

Solution: state-merging logic must preserve R1 when the response **does not issue a new token**.

### 12.2. JSON mappers defaulting missing fields to `null`

If an application manually serializes `OAuth2AuthorizedClient` to JSON/DB and overwrites the entire row from the response, a field absent in the response may be turned into `null` by the mapper and wipe out the stored refresh token.

Distinguish **absent** from **explicit replacement** in update methods, and allow only trusted components to modify token records.

### 12.3. Saving only the new access token

A custom success handler might write only access token A2 to the DB without retaining refresh token R1. That likewise destroys refresh capability.

Save/update the full valid authorized client from the provider/manager rather than building a stripped-down record without the refresh token when the app still needs future refreshes.

### 12.4. Reading and writing to two different stores

The manager writes A2/R1 through `OAuth2AuthorizedClientService`, while a controller reads from a separate `HttpSessionOAuth2AuthorizedClientRepository`. Tokens can "disappear" or drift out of sync.

Establish which repository/service is the single source of truth for token issuance and API calls.

## 13. `invalid_grant` Errors After Retaining R1

Suppose the AS previously returned A2 without issuing R2, so the client kept R1. On the next refresh:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "invalid_grant"
}
~~~

Possible reasons:

- R1 expired.
- R1 was revoked by the user or AS.
- Client registration or permissions changed.
- Another request already used R1 and the AS enforces rotation.
- The AS enforces a single-use or token-family policy different from what was expected.
- R1 does not match the client sending the request.
- Unintended reuse occurred and the AS triggered reuse detection.

Never look at `invalid_grant` alone and conclude "the client was wrong to keep R1". Check provider policies and redacted operational telemetry.

### 13.1. Error handling

1. Never retry endlessly with the same old refresh token.
2. Recognize this as a token-endpoint error, distinct from API 401/403 errors.
3. Use the failure handler/manager to delete or mark the old authorized client invalid per policy.
4. When needed and a user is present, initiate a fresh Authorization Code flow.
5. For userless services, use an appropriate grant/service identity.
6. Never use an ID token or old authorization code as a refresh token.

**Deleting the local authorized client does not automatically revoke the token at the AS.**

### 13.2. AS rotates without returning a new token?

If a provider's contract states R1 is invalidated immediately on every refresh, yet a successful response fails to include R2, the client cannot guess a replacement token.

Investigate the AS behavior and potential integration bugs. If R1 cannot be reused, the client may need fresh authorization. **Never fabricate dummy tokens or retry R1 infinitely.**

## 14. Concurrent Requests and Refresh Token Rotation

### 14.1. Typical race

~~~text
Request A loads A1/R1
Request B loads A1/R1

A: refreshes R1 -> A2/R2
B: refreshes R1 -> invalid_grant (or reuse policy)
~~~

If request B overwrites state with stale data on top of A2/R2, the application loses the new refresh token.

Consider:

- Locking/single-flight keyed by registration and principal.
- Conditional updates or appropriate transactions.
- Shared token storage across instances.
- Preserving the A2/R2 pair when the AS rotates.
- Never writing R1 from an old snapshot after R2 already exists.
- Bounded retries and context-appropriate error handling.

Do not assume a session repository or manager automatically provides atomic refreshes across multiple threads or multiple nodes.

### 14.2. When the AS allows reusing R1

If the AS does not rotate and two requests refresh R1 simultaneously:

~~~text
A: R1 -> A2, no R2
B: R1 -> A3, no R3
~~~

Both requests may succeed under AS policy. Even then, writing A2/A3 still has concurrency hazards; prevent stale overwrites or principal mix-ups.

### 14.3. Lost responses

If the AS already issued A2/R2 and invalidated R1, yet a network drop loses the response, the client may still hold only R1. Retrying R1 may be rejected by the AS.

The client cannot recover R2 by guessing. Plan for retry policies, AS grace periods if supported, or a fresh authorization flow. This is an inherent failure mode of rotation to account for.

## 15. Refresh Responses and API Errors Are Separate Concerns

| Response | Source | Meaning |
|---|---|---|
| Token endpoint returns A2, no R2 | Authorization Server | Refresh succeeded, no replacement refresh token issued |
| Token endpoint returns `invalid_grant` | Authorization Server | Refresh failed |
| Orders API returns 401 | Resource Server | Access token rejected or request unauthenticated |
| Orders API returns 403 | Resource Server | Insufficient access permissions |
| Orders API returns order JSON | Resource Server | Unrelated to refresh token issuance |

If an API returns 401, distinguish expired access tokens from wrong audience, revocation, wrong issuer, or token profile mismatches. Even a freshly refreshed access token can be rejected by an API if its audience or scopes do not match.

**Do not treat every 401/403 as a signal to refresh R1**, and do not treat an API JSON response lacking `refresh_token` as an error.

## 16. Is a New ID Token Needed in a Refresh Response?

In OIDC:

- The ID token authenticates the End-User to the Relying Party.
- The access token accesses the Resource Server.
- The refresh token requests new tokens at the token endpoint per AS permissions and policy.

A refresh response may omit a new ID token depending on flow and provider. That is **different** from omitting a new refresh token.

~~~text
No new id_token
    !=
No new refresh_token
    !=
Access token refresh failed
~~~

A successful refresh token grant also **does not prove the user just re-authenticated**. If the app requires fresh MFA or authentication freshness, send an OIDC Authentication Request and verify `auth_time`, `acr`, or other policy-required claims.

## 17. Securing Refresh Tokens in Storage

A refresh token is a credential capable of obtaining new access tokens. Therefore it must be protected:

- HTTPS when communicating with the AS.
- Client authentication/PKCE matching the flow and client type.
- Access control on the authorized client store.
- Encrypted transport and encrypted storage at rest where appropriate.
- TTL, cleanup, and backup/replication policies.
- Never write raw tokens to logs or tracing.
- Never return refresh tokens to the frontend.
- Never share tokens across principals or tenants.
- Purge tokens on logout or provider disconnect per policy.

### 17.1. `HttpSession` and refresh tokens

If authorized clients are stored in `HttpSession`, the session store holds refresh tokens. The session cookie normally carries only a session ID rather than raw tokens, yet stealing that cookie still lets an attacker exercise the session's permissions.

Enforce `HttpOnly`, `Secure`, `SameSite`, HTTPS, CSRF protection, session fixation defense, and secure session stores.

### 17.2. Logout and revocation

Logging out of the Portal clears the local session, yet does not by default revoke the refresh token at the AS. If tokens live in an `OAuth2AuthorizedClientService` outside the session, logout does not automatically purge that record unless explicitly configured.

`removeAuthorizedClient` deletes local state; token revocation at the AS is a separate operation.

### 17.3. Never use a refresh token as an API token

Refresh tokens are only for the token endpoint under the appropriate grant. They must **never** be sent to the Orders API in an `Authorization: Bearer` header. A Resource Server expects an access token with the right audience and scopes.

## 18. Safe Observability: Knowing Whether the AS Returned R2 Without Logging Tokens

Helpful telemetry fields:

~~~text
registrationId: corporate
principalReference: internal-user-id
authorizedClientFound: true
refreshAttempted: true
refreshSucceeded: true
newRefreshTokenReturned: false
storedRefreshTokenPresent: true
accessTokenExpiry: timestamp
errorType: none
~~~

Never log:

~~~text
raw access token
raw refresh token
id_token
authorization code
code_verifier
client secret
JSESSIONID / session cookie
serialized OAuth2AuthorizedClient
~~~

To correlate duplicate requests, use a dedicated correlation ID, never raw tokens.

### 18.1. Workflow for debugging "first refresh works, second one fails"

1. Check whether the initial token response contained refresh token R1.
2. Verify whether the first refresh actually called the token endpoint.
3. If the response returned only A2, confirm R1 remains on the saved authorized client.
4. If the response returned R2, confirm the store replaced R1 with R2.
5. If R1/R2 was present yet the next refresh failed, check expiry, revocation, rotation, or races.
6. If requests across multiple instances see different states, inspect the backing store.
7. If using a custom provider/mapper/success handler, check where tokens are updated.
8. Avoid infinitely retrying real refresh tokens in production; the AS may trigger reuse detection.

## 19. Common Errors

| Symptom | Possible cause | Resolution approach |
|---|---|---|
| Refresh succeeds, then R1 is lost | Wrote `null` from response onto authorized client | Retain old R1 when no R2 is returned |
| AS returns R2, yet next call still uses R1 | Failed to save new token on rotation | Save R2 and discard R1 |
| Initial response lacks refresh token | AS did not issue R1 | Check client policy, scopes, and consent |
| `invalid_grant` after retaining R1 | R1 expired, revoked, or rotation/race occurred | Check policy and initiate fresh authorization |
| HTTP 200 without access token | Invalid response | Fail in parser / token response client |
| `refresh_token` is empty string or `null` | Invalid payload or provider quirk | Do not treat as a valid new token |
| New token visible in only one request | Misconfigured store or success handler | Unify repository/service |
| Multiple nodes lose R2 | Stale state overwrite or unshared token store | Synchronize updates |
| API returns 401 after refresh | Wrong audience/issuer/expiry on access token | Check Resource Server policy |
| API returns 403 after refresh | Missing business permissions/scopes | Do not expect refresh to expand permissions |
| Token still valid after logout | Local cleanup differs from AS revocation | Consider revoking at the AS |
| ID token used as refresh token | Token type mix-up | Use the refresh token issued by the AS |

## 20. Scenario Exercises

### Scenario A — Never had R1

**Input:** Authorization Code response contains A1 and an ID token, with no refresh token.

**Outcome:** The client has no refresh token to retain. When A1 expires, a new Authorization Code flow or another AS-supported grant is needed.

### Scenario B — Have R1, response omits R2

**Input:** Stored authorized client has A1/R1; AS returns A2 with no refresh token.

**Outcome:** Normally save A2/R1. Never overwrite R1 with `null`.

### Scenario C — Have R1, response includes R2

**Input:** A1/R1; AS returns A2/R2.

**Outcome:** Save A2/R2 and discard R1; reusing R1 can trigger reuse detection.

### Scenario D — AS rejects R1 on the next call

**Input:** A2/R1 was saved, next call gets `invalid_grant`.

**Outcome:** Do not conclude the client was wrong merely for keeping R1. Check AS expiry, revocation, races, rotation, and provider contract; handle the error rather than retrying infinitely.

### Scenario E — Two concurrent requests

**Input:** Both requests use R1; one receives R2 while the other errors.

**Outcome:** Enforce concurrency control and write ordering so stale R1 never overwrites R2.

### Scenario F — AS returns success without A2

**Input:** HTTP 200 containing only `expires_in`.

**Outcome:** This is not a complete successful token response for updating the authorized client. The parser/client must raise an error.

## 21. Self-Check Questions

**Q1.** Is a successful refresh response without a new `refresh_token` always an error?

**Answer:** No. The AS may issue a new access token without issuing a replacement refresh token.

**Q2.** The client has A1/R1, and the refresh response contains only A2. What should be saved?

**Answer:** Normally A2/R1; keep the old token when no replacement is issued, per the AS contract.

**Q3.** If the response has A2/R2, may we keep R1 as a backup?

**Answer:** No. Replace R1 with R2 whenever the AS issues a new refresh token.

**Q4.** The initial token response had no refresh token. Is there an R1 to keep?

**Answer:** No. The client was never issued a refresh token.

**Q5.** Does `OAuth2AccessTokenResponse.getRefreshToken() == null` prove R1 was revoked?

**Answer:** No. It only indicates the current response did not include a new refresh token.

**Q6.** How does Spring Security's refresh provider normally behave when the response omits R2?

**Answer:** It retains the refresh token from the existing authorized client when building the updated authorized client.

**Q7.** If the AS returns R2 yet the client saves R1, what can happen?

**Answer:** The next refresh may hit `invalid_grant` or trigger reuse detection.

**Q8.** Does keeping R1 guarantee R1 stays valid forever?

**Answer:** No. The AS controls expiration, revocation, and other policies.

**Q9.** If an API returns 403 after a refresh, does that mean the refresh token was lost?

**Answer:** No. 403 normally relates to authorization, scopes, or ownership.

**Q10.** Can an ID token substitute for a refresh token?

**Answer:** No. The two token types have distinct purposes and usage rules.

**Q11.** Why can concurrent requests lose R2?

**Answer:** Another request may write back a stale A1/R1 snapshot after one request already saved A2/R2.

**Q12.** Does deleting the local authorized client revoke the token at the AS?

**Answer:** No. Local cleanup and token revocation at the AS are separate operations.

## Key Takeaways

- **A successful refresh response without `refresh_token` is not an error by default.** The AS is not required to issue a new refresh token every turn.
- **An initial token response without a refresh token** means there is no credential for the refresh token grant yet.
- **When R1 exists and the refresh response returns A2 without R2:** normally keep **A2/R1**.
- **When the response returns A2/R2:** save **A2/R2** and discard R1 per rotation.
- **Spring Security's `RefreshTokenOAuth2AuthorizedClientProvider`** preserves the existing refresh token when no new one is returned; prefer the standard manager/provider over ad-hoc response merging.
- **Keeping R1 does not guarantee R1 remains valid forever.** The AS can enforce expiry, revocation, and reuse detection; handle `invalid_grant` cleanly.
- **Store tokens under the exact principal/registration and update consistently**, especially with rotation, concurrent requests, or multiple nodes.
- **Refresh tokens are sensitive credentials**: never log them, never send them to frontends or resource APIs, never substitute ID tokens, and never confuse local cleanup with AS revocation.
