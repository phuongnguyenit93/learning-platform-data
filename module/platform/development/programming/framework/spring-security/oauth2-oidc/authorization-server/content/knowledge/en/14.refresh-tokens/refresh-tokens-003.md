# Exchanging a Refresh Token to Issue a New Access Token

> **Chapter:** Refresh Token  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Scope:** Designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in a Spring Boot application.  
> **Version context:** Java examples target Spring Boot 3.x, Spring Security 6.x, and Spring Authorization Server 1.x (Servlet stack). For Spring Security 7.x with integrated Authorization Server, verify APIs and starters against your exact deployment version.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain how the **refresh token grant** works at the token endpoint, why it differs from the Authorization Code Grant, and why it does not require redirecting the browser to the login page every time.
2. Identify mandatory checks when receiving a refresh token: **client**, **grant type**, **status**, **expiration**, **scope**, and issuance policy.
3. Describe how Spring Authorization Server uses `RegisteredClientRepository`, `OAuth2AuthorizationService`, `OAuth2RefreshTokenAuthenticationProvider`, and `OAuth2TokenGenerator` when issuing a new access token.
4. Configure `TokenSettings.accessTokenTimeToLive(...)`, `refreshTokenTimeToLive(...)`, and `reuseRefreshTokens(...)` according to requirements.
5. Distinguish **refresh token reuse** from **refresh token rotation**, understanding the limits of replay detection, token revocation, and session termination.
6. Write tests for valid refresh tokens, wrong client, expired, invalidated, exceeded scope, reuse after rotation, and concurrent requests.
7. Design secure refresh token storage in BFFs, backends, mobile apps, and multi-instance systems.

**Key point:** A refresh token is not an "unlimited pass" that can be exchanged for an access token at any time. It is a **credential with its own permissions and lifecycle**, issued to a specific client within a specific authorization; the AS must re-verify constraints before each new token issuance.

## 2. Distinguishing Access Tokens and Refresh Tokens

| Attribute | Access token | Refresh token |
| --- | --- | --- |
| Purpose | Allows the Client to access a Resource Server (RS) | Allows the Client to request a new access token at the Authorization Server (AS) |
| Sent to | Protected APIs, typically via `Authorization: Bearer ...` | AS token endpoint, typically in `grant_type=refresh_token` |
| Receiving party | RS validates the token and access permissions | AS authenticates/validates the token exchange request |
| Lifetime | Usually relatively short | Usually longer than access tokens, governed by AS policy |
| Format | Can be self-contained JWT or opaque/reference | Typically an unpredictable opaque string in SAS 1.x; do not assume structure |
| Scope | Represents granted API access permissions | Bound to the authorization/permitted scopes, not a right to expand arbitrarily |
| Revocation | Depends on how the RS validates JWT/opaque tokens and policy | AS can mark the token invalid; effective enforcement also depends on implementation |
| If compromised | Attacker can call APIs within the token's scope | Attacker can request new access tokens unless blocked by additional constraints |

In OAuth 2.0, refresh tokens are **never sent to a Resource Server** to access data. The RS must not accept a refresh token as an access token, even if both strings look similar. Conversely, an access token is not a valid credential for calling the `refresh_token` grant.

A refresh token may be issued in a token response when the grant allows it and AS policy decides so. **Not every Client or every grant receives a refresh token.** Specifically, RFC 6749 recommends **against** issuing a refresh token for the Client Credentials Grant; in Spring Authorization Server, registering `AuthorizationGrantType.REFRESH_TOKEN` does not automatically turn every token response into one with a refresh token.

### 2.1. Why Do We Need Refresh Tokens If Access Tokens Already Have Lifetimes?

Suppose a booking application uses an access token valid for only 5 minutes. A user operates inside the application for longer than 5 minutes. Without a refresh token, the client would have to restart a new authorization flow or use another authentication mechanism, potentially causing unnecessary redirects.

If the AS has issued a valid refresh token, the client can obtain a new access token **without requiring the user to re-enter their password every time the access token expires**. This improves user experience, while increasing the value of the refresh token to attackers: a credential capable of sustaining access must be stored strictly.

### 2.2. A Refresh Token Is Not the Same as an AS Login Session

Three states must be separated clearly:

- **Resource Owner login session:** may exist in an HTTP session at the AS to handle browser login and consent.
- **Authorization and refresh token:** persisted by the AS via `OAuth2AuthorizationService` to process grants across separate HTTP requests.
- **Access token at the RS:** validated by the RS via JWT signature or introspection/metadata; does not automatically share a `SecurityContext` with the AS.

A user logging out of a web page **does not by default** revoke all active refresh tokens and still-valid JWTs. If system requirements call for "logout from all devices," you must add token revocation policies, session invalidation, and appropriate token checking at the RS.

## 3. End-to-End Refresh Token Grant Flow

Suppose:

- **Resource Owner:** Lan.
- **OAuth2 Client:** backend/BFF `booking-web`, a registered confidential client.
- **AS:** `https://auth.example.test`.
- **RS:** `https://api.example.test`.
- The client previously completed Authorization Code + PKCE and received an access token and a refresh token per policy.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Resource Owner
    participant C as booking-web (Client)
    participant AS as Authorization Server
    participant DB as Authorization Store
    participant RS as Resource Server

    U->>C: Sign in and perform initial actions
    Note over C,AS: Authorization Code + PKCE completed
    AS-->>C: access_token A1 + refresh_token R1
    C->>RS: API request using A1
    RS-->>C: Valid response
    Note over C: A1 nearing/past expiration; R1 still valid
    C->>AS: POST /oauth2/token<br/>grant_type=refresh_token, R1, client authentication
    AS->>AS: Authenticate client + verify grant type
    AS->>DB: Look up R1 and associated authorization
    DB-->>AS: RegisteredClient binding, scopes, token status
    AS->>AS: Verify active/expiry/scopes + rotation policy
    alt R1 is valid
        AS->>DB: Save access token A2<br/>and new refresh token if rotated
        AS-->>C: access_token A2 + refresh_token per policy
        C->>RS: API request using A2
        RS-->>C: Valid response
    else R1 is invalid
        AS-->>C: OAuth2 error, no token issued
    end
~~~

In the `POST /oauth2/token` request, the principal typically represents the **authenticated/identified OAuth2 Client**, not a `UsernamePasswordAuthenticationToken` from the earlier browser login session. The authorization's Resource Owner is determined from the stored grant record, not by retrieving a ThreadLocal from the old login request.

### 3.1. Two Token Issuances Are Related but Not Identical

Initially, the client receives a refresh token according to the initial grant and AS issuance policy. Subsequently, on a successful refresh:

- A **new access token** is issued, typically with new `issued_at` and `expires_at` timestamps.
- `refresh_token` in the response may be the **old string** (reuse) or a **new string** (rotation), depending on `TokenSettings` and the provider.
- Scopes remain the same or are **narrowed** upon a valid request; the client cannot use refresh to grant itself unapproved scopes.
- Issuing an ID token during an OIDC refresh must follow OIDC policy and implementation; **do not assume it happens automatically just because a new access token is issued**.

## 4. Standard HTTP Request and HTTP Response

### 4.1. Confidential Client Sends a Refresh Request

Illustrative HTTP example:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <encoded-client-id-and-secret>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=refresh_token&refresh_token=REFRESH_TOKEN_VALUE&scope=booking.read
~~~

In OAuth 2.0:

- `grant_type` **must** be `refresh_token`.
- `refresh_token` is the value previously issued by the AS.
- `scope` is an **optional** parameter. If present, requested scopes must not exceed the originally granted authorization scope. When `scope` is omitted, per RFC 6749, the scope must be treated as the original scope per server/profile rules.
- A confidential client must authenticate using its **registered method**, such as `client_secret_basic`. Never send client secrets in URLs.
- Use TLS; never include real refresh tokens or secrets in logs, documentation examples, screenshots, or analytics tools.

`Authorization: Basic <encoded-client-id-and-secret>` is only a placeholder; applications should use an OAuth2 Client library instead of assembling authentication headers by hand. Basic encoding must comply with relevant OAuth2 and HTTP rules.

### 4.2. Successful Token Response

Example:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "NEW_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 300,
  "refresh_token": "NEW_OR_REUSED_REFRESH_TOKEN",
  "scope": "booking.read"
}
~~~

This response illustrates typical fields:

| Field | Role | Notes |
| --- | --- | --- |
| `access_token` | New token for RS | Can be JWT or opaque per `TokenSettings.accessTokenFormat` |
| `token_type` | Token type, usually `Bearer` | RS uses the matching scheme and verification method |
| `expires_in` | Seconds remaining before the access token expires at response time | Client should compute expiration time with an appropriate skew margin |
| `refresh_token` | Refresh token after exchange | Reused or new value per policy; update storage only when the response is valid |
| `scope` | Scopes of the new access token, if returned | Never expanded beyond granted permissions |

Do not rely on `refresh_token` always being present in every AS response if a protocol/profile permits omitting it or the server changes policy; with Spring Authorization Server 1.x, reuse/rotation behavior is controlled by `TokenSettings` and the provider. Clients must handle responses according to the specific deployment contract.

### 4.3. Invalid Refresh Request or Inactive Token

Typically the AS returns an OAuth2 error such as:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{
  "error": "invalid_grant"
}
~~~

`invalid_grant` typically corresponds to a wrong, expired, invalidated refresh token, or one violating grant/client bindings. If **client authentication** is invalid, the AS may return `invalid_client` with an appropriate HTTP status/challenge; if requested scopes exceed granted permissions, it may return `invalid_scope`.

Do not rely on error descriptions to infer which user owns a refresh token or whether it exists; the AS should avoid leaking sensitive data in `error_description` and logs.

## 5. Verification Steps in the Authorization Server

In Spring Authorization Server 1.x, refresh token processing lives at the **Token Endpoint**, not the Authorization Endpoint:

1. `OAuth2ClientAuthenticationFilter` and its associated providers identify/authenticate the client against its registration.
2. `OAuth2TokenEndpointFilter` uses the appropriate converter to turn the request into an `OAuth2RefreshTokenAuthenticationToken`.
3. `OAuth2RefreshTokenAuthenticationProvider` processes the request using components like `RegisteredClientRepository`, `OAuth2AuthorizationService`, and `OAuth2TokenGenerator`.
4. The provider validates client/grant/refresh token and scopes, generates a new access token, and handles the refresh token per policy.
5. The AS saves the updated authorization state and builds the appropriate OAuth2 token response.

These steps represent the logical model of the SAS 1.x branch; exact ordering or customization APIs may differ between versions.

### 5.1. Table of Required Conditions

| Condition | What the AS must prove | When unmet |
| --- | --- | --- |
| Client identified/authenticated | Method matches `RegisteredClient`; confidential client proves valid credentials | `invalid_client` or client authentication error |
| Client allowed to refresh | Registration includes `AuthorizationGrantType.REFRESH_TOKEN` | Reject grant |
| Refresh token exists | `OAuth2AuthorizationService` holds the matching authorization/token | `invalid_grant` |
| Correct token type | It is a refresh token accepted by the AS, not an access token or ID token | `invalid_grant` or appropriate request error |
| Token bound to client | The authorization's `registeredClientId` matches the requesting client | `invalid_grant` |
| Token is active | Not expired, not invalidated, and not already consumed by rotation | `invalid_grant` |
| Valid scopes | Requested scopes do not exceed the authorization's `authorizedScopes` | `invalid_scope` |
| Token policy | Permitted to issue new token; apply TTL, format, rotation, claims policy | Reject or issue per policy |
| State persisted | Updated state is saved consistently for audit/revocation | Do not return success if correctness cannot be guaranteed |

A critical check is **binding the refresh token to the Client**. Knowing the refresh token string is not enough for Client B to exchange a token issued to Client A. This binding applies to both Confidential and Public Clients; for public clients, protection must rely on policy/token rotation, sender-constrained tokens, or appropriate factors because `client_id` is not a secret.

### 5.2. No Need for Resource Owner Re-Login on Every Refresh

The refresh token grant is not a username/password re-entry flow. The AS relies on the previously created authorization to determine the principal and granted scopes. Depending on policy, the AS can:

- Allow refresh while the refresh token remains valid and unrevoked.
- Reject if the account/consent/client has been disabled or had permissions revoked, **provided the implementation checks that state**.
- Require the user to complete a new authorization/login when the refresh token is expired or no longer valid.

**Do not assume** that marking an account `disabled` in a user table immediately rejects all existing refresh tokens. If this requirement matters, design state checking/revocation logic at the AS and test it explicitly.

## 6. Configuring RegisteredClient to Allow Refresh Tokens

Example baseline: a backend BFF using Authorization Code + PKCE, confidential client, needing to maintain user experience across multiple access token expirations.

~~~java
import java.time.Duration;

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

public final class ClientFactory {

    private ClientFactory() {}

    public static RegisteredClient bookingBff(
            String secretFromSecureConfig,
            PasswordEncoder passwordEncoder) {

        return RegisteredClient
            .withId("booking-bff-internal-id")
            .clientId("booking-bff")
            .clientSecret(passwordEncoder.encode(secretFromSecureConfig))
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
            .authorizationGrantType(
                AuthorizationGrantType.REFRESH_TOKEN)
            .redirectUri(
                "https://app.example.test/login/oauth2/code/booking-bff")
            .scope(OidcScopes.OPENID)
            .scope("booking.read")
            .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(true)
                .build())
            .tokenSettings(TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(5))
                .refreshTokenTimeToLive(Duration.ofDays(7))
                .reuseRefreshTokens(false)
                .build())
            .build();
    }
}
~~~

Explanation:

- `authorizationGrantType(AUTHORIZATION_CODE)` enables creating the initial grant via browser and PKCE.
- `authorizationGrantType(REFRESH_TOKEN)` allows the client to use the refresh token grant once it holds an AS-issued refresh token.
- `CLIENT_SECRET_BASIC` requires the client to authenticate at the token endpoint. The secret must come from a secret manager/secure config and be hashed with an appropriate `PasswordEncoder`.
- `requireProofKey(true)` requires PKCE in the initial grant. **A PKCE verifier is not a normal parameter of the refresh token grant**, because the refresh token already has its own binding.
- `accessTokenTimeToLive(...)` and `refreshTokenTimeToLive(...)` govern each token type's TTL independently, not a shared lifetime.
- `reuseRefreshTokens(false)` expresses intent for **rotation**: on successful refresh, issue a new refresh token instead of continuing to reuse the old one.
- Selecting rotation **does not automatically provide a full token-family replay-detection system**; add dedicated policies if theft-response behavior is required.

**This is only an illustrative `RegisteredClient` factory.** A complete AS requires saving registrations via `RegisteredClientRepository` and configuring the authorization store, signing keys, issuer, user authentication, consent, filter chains, and endpoints for your exact version. A registration ID must be stable when persisted durably; never regenerate random IDs on every boot and break links to existing authorizations.

### 6.1. Choosing TTLs with Justification

| Setting | Example | Meaning |
| --- | --- | --- |
| Access token TTL | 5 minutes | Limits how long a stolen access token remains usable |
| Refresh token TTL | 7 days | Allows the client to request new access tokens within the granted window |
| Rotation | `false` for `reuseRefreshTokens` | Successful refresh issues a new refresh token per policy |
| Absolute session lifetime | e.g., max 30 days | **Not automatically configured by the settings above alone**; must be designed as a separate policy |

These durations are **illustrative examples, not mandatory standards**. A banking system may need very different TTLs and re-authentication rules than a news reader app. Evaluate client type, token compromise risk, UX, session policies, and compliance requirements.

## 7. Reuse and Rotation: Two Policies with Distinct Trade-offs

### 7.1. Refresh Token Reuse

When configured as:

~~~java
TokenSettings.builder()
    .reuseRefreshTokens(true)
    .build();
~~~

The AS can continue accepting **the same refresh token** across multiple access token exchanges until the token expires, is revoked, or is invalidated by policy.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server

    Note over C,AS: C has R1 and A1
    C->>AS: R1 requests new access token
    AS-->>C: A2 + R1 (reuse)
    C->>AS: R1 requests access token again
    AS-->>C: A3 + R1 (reuse)
~~~

Advantage: simpler credential management for the client, lower risk of desynchronization when responses drop over the network. Disadvantage: if R1 is stolen, an attacker can continue using it until the AS invalidates the token or it expires, absent additional protective constraints.

### 7.2. Refresh Token Rotation

When configured as:

~~~java
TokenSettings.builder()
    .reuseRefreshTokens(false)
    .build();
~~~

The AS is instructed to **issue a new refresh token after a successful exchange**, typically also invalidating the previous token for further refreshes.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server

    Note over C,AS: C holds R1
    C->>AS: Use R1
    AS->>AS: Validate R1 and replace with R2
    AS-->>C: A2 + R2
    C->>C: Save R2 replacing R1
    C->>AS: Use R2
    AS->>AS: Validate R2 and replace with R3
    AS-->>C: A3 + R3
    C->>C: Save R3 replacing R2
    Note over C,AS: Reusing R1/R2 must be rejected once invalidated
~~~

Rotation limits reuse of a leaked token and creates an opportunity to detect replay. However, **rotation alone is not a complete token-theft detection mechanism**:

- You need to track the refresh-token family chain to recognize that reuse of an old token signals an attacker.
- You need a policy to revoke the entire family or force re-authentication upon detecting replay.
- You need to handle race conditions between two concurrent refresh requests.
- You need a strategy when a response carrying R2 is lost after the AS has already invalidated R1.
- You need to decide whether to cap total session lifetime or let rotation extend indefinitely.

Spring Authorization Server provides `reuseRefreshTokens(false)` for issuance policy. **Do not assume it always implements family-wide revocation, replay alerts, or absolute session timeouts.** Such requirements must be implemented and tested specifically on your version.

### 7.3. Exchanging a Refresh Token Does Not Mean Infinite Extension

When reusing R1, R1's original expiration time generally does not shift merely because the AS issued a new access token. When rotating R1 → R2, the new token may receive a fresh TTL per configuration, potentially extending login continuity indefinitely if no independent cap exists.

If the organization requires "no refreshes past 30 days from initial login," you must persist and enforce an **absolute authorization/session lifetime** in a dedicated policy. Setting `refreshTokenTimeToLive(Duration.ofDays(7))` alone does not configure an absolute lifetime ceiling for the whole family.

## 8. Verifying Scopes During Refresh

A client cannot request broader permissions than the scopes approved in the initial authorization.

Example granted authorization:

~~~text
authorizedScopes = ["openid", "booking.read", "profile"]
~~~

Requests:

| Refresh request | Valid scope outcome |
| --- | --- |
| No `scope` | Retain granted scope per AS/profile policy |
| `scope=booking.read` | May succeed: narrowed scope |
| `scope=booking.read profile` | May succeed: subset of granted scope |
| `scope=booking.write` | Cannot expand: AS rejects |
| `scope=admin` | Cannot expand: AS rejects |
| `scope=booking.read admin` | Rejected due to scope outside the authorization |

In the Spring Authorization Server 1.x branch, `OAuth2RefreshTokenAuthenticationProvider` handles scope requests and validates against the authorization's granted scopes. Never write a custom provider that skips this check and arbitrarily grants scopes from `RegisteredClient.getScopes()`.

**Distinction:** `RegisteredClient.getScopes()` are the scopes *the client may request*; `OAuth2Authorization.getAuthorizedScopes()` are the scopes *actually granted* to a specific authorization. At the refresh endpoint, using client registration alone to grant additional scopes would bypass Resource Owner consent.

### 8.1. User Permissions Changing While a Refresh Token Is Still Valid

Suppose Lan was granted `booking.read`, but later had order-viewing permissions revoked. The AS does not automatically re-read the user permissions database on every refresh request in all configurations. If business rules require changes to take effect immediately, you must:

- Proactively revoke the affected authorizations/refresh tokens.
- Check permission/tenant status at new-token issuance time if policy lives at the AS.
- Or always enforce object-level authorization at the RS rather than trusting stale JWT claims.
- Test access tokens issued **before** the permission change and tokens issued **after** the change event.

Do not assume refresh token rotation automatically synchronizes all business permissions.

## 9. Persisting OAuth2Authorization and Refresh Token State

### 9.1. Repositories/Services Supporting Processing

| Component | Responsibility | Avoid confusing with |
| --- | --- | --- |
| `RegisteredClientRepository` | Stores Client registrations, grant types, token settings | Does not store active refresh tokens |
| `OAuth2AuthorizationService` | Persists authorizations, access/refresh tokens, and metadata | Does not replace the login request's `SecurityContext` |
| `OAuth2AuthorizationConsentService` | Persists consent decisions when needed | Does not replace active checks on refresh tokens |
| `OAuth2TokenGenerator` | Generates tokens matching grant and settings | Does not authenticate the Client |
| `OAuth2RefreshTokenAuthenticationProvider` | Coordinates the refresh token grant | Does not handle Resource Owner form login |

Spring Authorization Server 1.x provides an in-memory implementation for learning and JDBC for authorization storage per documentation. For multi-instance production, you need a shared data store/design with sufficient consistency to process refresh tokens safely.

### 9.2. Inspecting Tokens via AuthorizationService

Lookup concept (illustrative for admin code or tests):

~~~java
OAuth2Authorization authorization =
    authorizationService.findByToken(
        refreshTokenValue,
        OAuth2TokenType.REFRESH_TOKEN
    );

if (authorization == null) {
    // Does not exist or authorization cannot be found.
    // Never issue an access token.
}

OAuth2Authorization.Token<OAuth2RefreshToken> storedRefreshToken =
    authorization.getRefreshToken();

if (storedRefreshToken == null || !storedRefreshToken.isActive()) {
    // Token is expired, invalidated, or inactive per metadata.
    // Do not issue a new token.
}
~~~

Variables `authorizationService` and `refreshTokenValue` must be supplied by the application/test, importing `OAuth2Authorization`, `OAuth2TokenType`, and `OAuth2RefreshToken`. The snippet above **does not replace `OAuth2RefreshTokenAuthenticationProvider`**. It merely illustrates the lookup and status APIs; the provider is responsible for verifying client binding, scopes, and executing token issuance.

Never expose this code in a public controller that accepts raw refresh tokens and returns metadata to arbitrary callers. Only look up inside trusted security boundaries and never log refresh token strings.

### 9.3. Atomicity When Exchanging Tokens

With rotation, two concurrent requests may both try to use R1:

~~~mermaid
flowchart LR
    C["Two concurrent requests with R1"]
    A["AS instance A"]
    B["AS instance B"]
    DB[("Authorization Store")]
    T{"Are validation + replacing R1<br/>guaranteed consistent?"}
    OK["Only one request refreshes"]
    BAD["Risk of both succeeding<br/>or client saving wrong new token"]

    C --> A
    C --> B
    A --> DB
    B --> DB
    DB --> T
    T -->|"Yes"| OK
    T -->|"No"| BAD
~~~

In a multi-instance system, simply having a repository with a `save(...)` method **does not prove** that read/check/update is atomic under concurrent load. Verify transactions, optimistic/pessimistic locking, or serialization/compare-and-set depending on the store type. Test concurrency against the actual deployment storage infrastructure, not solely with `InMemoryOAuth2AuthorizationService`.

## 10. How Must Clients Store and Replace Refresh Tokens?

### 10.1. Backend or BFF

If the client runs on a server and can safeguard credentials, store refresh tokens in a server-side authorized-client store or protected secret store. The browser holds only a BFF session cookie with appropriate CSRF/XSS/cookie policies.

~~~mermaid
flowchart TD
    B["Browser<br/>session cookie"]
    BFF["BFF / Backend OAuth2 Client<br/>authorized client manager"]
    DB[("Protected token store")]
    AS["Authorization Server<br/>/oauth2/token"]
    API["Resource Server"]

    B -->|"Request with cookie"| BFF
    BFF <--> DB
    BFF -->|"Use access token"| API
    BFF -->|"Refresh token when needed"| AS
    AS -->|"New access token + RT per policy"| BFF
    BFF -->|"Persist replacement token per policy"| DB
~~~

Benefit: keeps refresh tokens out of browser JavaScript and `localStorage`. You must still defend against session hijacking, XSS calling APIs under the user's session, CSRF, log leaks, and unauthorized access to the backend token store.

### 10.2. Spring Security OAuth2 Client Can Refresh Automatically

On the **OAuth2 Client** side (the application calling the AS), an `OAuth2AuthorizedClientManager` can use providers supporting Authorization Code and Refresh Token:

~~~java
@Bean
OAuth2AuthorizedClientManager authorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientRepository authorizedClients) {

    OAuth2AuthorizedClientProvider provider =
        OAuth2AuthorizedClientProviderBuilder.builder()
            .authorizationCode()
            .refreshToken()
            .build();

    DefaultOAuth2AuthorizedClientManager manager =
        new DefaultOAuth2AuthorizedClientManager(
            registrations, authorizedClients
        );

    manager.setAuthorizedClientProvider(provider);
    return manager;
}
~~~

This snippet is a **configuration fragment for a Servlet OAuth2 Client application**, not a bean to put inside the Authorization Server just to issue tokens. It requires imports from `spring-security-oauth2-client` along with configured `ClientRegistrationRepository` and `OAuth2AuthorizedClientRepository`.

Callers must supply the proper principal/authorized-client context to the manager; the client library manages refresh requests and persists responses in the corresponding authorized-client mechanism. Do not reinvent a refresh endpoint that passes raw tokens to the browser if Spring OAuth2 Client already covers your use case.

### 10.3. Mobile Apps or Public Clients

A public client cannot prove identity using a client secret embedded in the app. Any strategy for issuing refresh tokens to public clients must evaluate **token protection capability, rotation or sender-constraining**, AS policy, and current security profiles.

Specifically in Spring Authorization Server 1.x, registering `ClientAuthenticationMethod.NONE` and the `REFRESH_TOKEN` grant **does not guarantee the default AS will issue refresh tokens to a public client**. Verify your version's capabilities and policies; if public clients require refresh tokens, explicitly design and test the protective mechanisms rather than assuming tokens will be issued.

If the system decides to issue refresh tokens to mobile apps, the app should use platform secure storage (Keychain/Keystore equivalents), protect state/PKCE, and limit leaks via logs/backups. Do not treat secure storage as absolute protection if the device itself is compromised.

### 10.4. Never Store Refresh Tokens in Easily Readable Locations

Avoid:

- Placing refresh tokens in URL queries, deep links, redirect URIs, browser history, or analytics.
- Storing them in SPA `localStorage` without a threat assessment and matching mitigations.
- Writing refresh tokens into consoles/logs/tracing, crash reports, emails, or webhooks.
- Storing plaintext refresh tokens in a database without access controls, appropriate encryption-at-rest, backup policies, and auditing.
- Sharing the same refresh token across multiple clients/devices without device separation and permission lifecycle strategies.

## 11. Refresh Token Rotation, Replay, and Network Failures

### 11.1. When Refresh Succeeds on AS but the Client Misses the Response

Example:

1. Client sends R1 to AS.
2. AS validates R1, invalidates R1, and issues R2.
3. AS saves R2 and returns a response with the new access token + R2.
4. Network drops; the client never receives the response.
5. Client only has R1 left, which is no longer valid.

The client must not retry R1 indefinitely, as the AS may treat it as replay. Some systems implement a **grace period** or custom idempotency policy, though this widens the token reuse window and requires tight design. Do not assume Spring Authorization Server includes every custom recovery mechanism by default.

In many applications, when refresh fails without safe recovery, the choice is to initiate a fresh authorization/login flow. Client behavior must handle error states cleanly without saving empty tokens or logging raw credentials for debugging.

### 11.2. When Two API Requests Simultaneously Notice an Expired Access Token

A BFF may trigger two refresh requests using the same R1:

~~~text
API request A -> sees A1 expired -> refreshes with R1
API request B -> sees A1 expired -> refreshes with R1

AS (rotation):
  A may receive R2 and succeed
  B reusing R1 may be rejected

If B handles failure incorrectly:
  - deletes authorized client already holding R2
  - overwrites with old R1
  - unnecessarily forces user to log in again
~~~

You must **synchronize refreshes to run once per authorized client** under concurrent requests, managing token updates via versioning/compare-and-set or a store-appropriate mechanism. Across multiple BFF instances, a local in-JVM mutex is insufficient.

### 11.3. Reuse Detection and Family Revocation

Advanced model:

~~~mermaid
flowchart TD
    A["Client uses valid R1"]
    B["AS issues R2, invalidates R1"]
    C{"Does R1 reappear?"}
    D["Flag replay indicator"]
    E["Revoke refresh-token family<br/>or require re-authentication"]
    F["Continue while token is valid"]

    A --> B --> C
    C -->|"Yes"| D --> E
    C -->|"No"| F
~~~

This is a **security policy that must be designed**, not a claim that `reuseRefreshTokens(false)` automatically builds a family tree or revokes the whole family upon detecting reuse. If implementing replay detection:

- Distinguish network/concurrency retries from theft indicators.
- Do not reveal to an attacker that a specific user's token family exists.
- Have clear auditing/alerting and incident policies.
- Check how existing access tokens can be invalidated: self-validated JWTs at an RS may stay valid until `exp`.

## 12. Revoking Refresh Tokens, Logout, and Permission Changes

### 12.1. Token Revocation Endpoint

RFC 7009 defines token revocation. When supported by the AS, a client can request revoking a refresh token:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.test
Authorization: Basic <encoded-client-credentials>
Content-Type: application/x-www-form-urlencoded

token=REFRESH_TOKEN_VALUE&token_type_hint=refresh_token
~~~

Use the actual endpoint URI published in AS metadata/settings. `token_type_hint` only helps the AS identify the token type; the AS must verify the caller and revocation policy. An HTTP success response from the revocation endpoint **is not a promise that all already-issued JWT access tokens will immediately be rejected by RSs**.

### 12.2. Logout May Require Multiple Actions

| Action | Primary effect | Limitation |
| --- | --- | --- |
| Clear BFF session cookie | Browser loses BFF session | Server-side refresh token may still exist unless deleted/revoked |
| Delete authorized client in BFF | Client stops using stored credentials | AS may not know the token was deleted |
| Revoke refresh token at AS | Can no longer exchange that refresh token for new access tokens per policy | Old access tokens may still be valid |
| Revoke authorization/token family | Invalidates related tokens/grants per implementation | Must check whether RSs enforce revocation immediately |
| Log out AS session | Ends browser login session at AS | Does not automatically mean all issued grants are revoked |
| OIDC RP-Initiated Logout | Coordinates logout at OIDC Provider if supported | Does not automatically replace OAuth2 Token Revocation |

When a user loses permissions, deletes their account, or device compromise is suspected, clearly specify **what must terminate**: browser sessions, refresh tokens, access tokens, user grants, or all of them.

### 12.3. Revocation and RS Using JWT/Opaque Tokens

- An RS verifying JWTs locally generally does not know the AS just revoked a refresh token or authorization. Already-issued JWT access tokens can still be accepted until expiration unless the RS checks extra state like a denylist, token version, or business state.
- An RS using opaque introspection can receive `active: false` after revocation, though response caching may introduce latency.
- Shortening access token TTL limits how long a leaked token remains usable, at the cost of higher refresh traffic, and does not replace an incident response strategy.

## 13. Testing the Refresh Token Grant

### 13.1. Mandatory Test Matrix

| Case | Setup | Expected outcome |
| --- | --- | --- |
| Valid refresh | R1 active, matching client, grant enabled, valid scope | Issues new access token |
| R1 expired | Test clock past `expiresAt` | `invalid_grant`, no access token issued |
| R1 revoked/invalidated | Authorization store records token inactive | Rejected |
| R1 nonexistent | Arbitrary token absent from store | Rejected |
| Access token used as refresh token | Wrong token type value | Rejected |
| Wrong client secret | Confidential client auth fails | `invalid_client` or error per auth method |
| Client B exchanges Client A's R1 | Wrong client binding | Rejected |
| Client lacks refresh grant | Registration missing `REFRESH_TOKEN` | Rejected |
| Scope equal to granted scope | No extra permissions requested | Succeeds if other conditions hold |
| Subset scope requested | `scope=booking.read` when multiple scopes were granted | Can succeed with narrowed scope |
| Scope outside authorized scopes | Unapproved `scope=admin` | `invalid_scope`, no token issued |
| Reuse mode | `reuseRefreshTokens(true)` | R1 continues being returned/used per policy while active |
| Rotation mode | `reuseRefreshTokens(false)` | New token R2; R1 no longer allowed to refresh |
| Reuse R1 after rotation | R1 already replaced | Rejected; verify replay policy if implemented |
| Two concurrent refresh requests | Same R1, multiple instances | Must not break single-use or desynchronize tokens |
| AS restart/failover | Token issued before restart | Matches persistence policy and state |
| User permissions removed | R1 still unexpired but permissions changed | Enforces required revocation/validation policy |
| Refresh token leaked into logs | Simulated logs/tracing | Ensure proper redaction and auditing |

### 13.2. HTTP-Level Testing

Integration test with a registered confidential client:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <valid-client-basic-credential>
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=VALID_R1&scope=booking.read
~~~

Before this request, the test must **actually obtain R1** issued by the AS from a valid grant; never invent a dummy string and expect refresh to succeed. After the response:

1. Assert HTTP 200 and `token_type=Bearer`.
2. Assert a new `access_token` is present with matching lifetime and scopes.
3. If rotating, assert the returned refresh token differs from R1 and R1 is rejected in a subsequent request.
4. If reusing, assert R1 remains usable per policy and does not exceed TTL.
5. Call the RS using the new access token to verify issuer/audience/scope and data permissions.

### 13.3. Spring Security Test: What Is Sufficient and What Is Not?

`@WithMockUser` and `jwt()` in `spring-security-test` are useful for testing authorization rules. However, they **do not prove a real refresh token passed through the provider**, client authentication, and authorization store.

To test the refresh grant:

- Use MockMvc or an HTTP test client against a real AS context.
- Initialize verifiable registered clients, authorization service, and token generator/keys.
- Obtain a refresh token from a valid authorization flow or properly constructed authorization/token metadata fixture.
- Send requests to `/oauth2/token` through the security filters.
- Inspect responses and the updated authorization state.
- Add concurrency tests if production runs multiple workers/instances.

### 13.4. Tests Should Not Depend on Internal Error Ordering

If a request has both a wrong client secret and an expired refresh token, the AS may stop at client authentication. To prove expired refresh tokens are blocked, use **valid client credentials**. To prove client binding, use two clients both registered with the right grant where the token belongs to only one client.

The goal is to prove **every security condition is enforced**, not just observing an arbitrary HTTP 400.

## 14. Observability and Troubleshooting

| Symptom | Possibility | Investigation steps |
| --- | --- | --- |
| Token endpoint returns `invalid_grant` | Wrong, expired, revoked, rotated refresh token, or client mismatch | Check state in `OAuth2AuthorizationService` and client binding; never log raw R1 |
| Token endpoint returns `invalid_client` | Wrong secret/certificate/client auth method | Check `RegisteredClient` and client authentication |
| Returns `invalid_scope` | Client requests scopes exceeding `authorizedScopes` | Compare requested scopes with actual authorization, not just registration |
| Client never received an initial refresh token | Grant/client type/policy forbids issuance | Check initial grant, client authentication method, and SAS version issuance logic |
| Token exchange succeeds yet RS returns 401 | Wrong issuer/audience/signature or RS uses wrong decoder | Inspect new token and RS configuration |
| Two refresh requests cause random logouts | Rotation race; authorized-client store overwritten | Synchronize refreshes, check versioning/compare-and-set |
| Refresh tokens stop working after restart | Authorizations stored in-memory only or unshared data | Check persistence, migrations, failover |
| Old JWT still accesses API after revoking R1 | RS verifies JWT locally without revocation check | Adjust TTL/denylist/introspection per policy |
| Rotation extends logins indefinitely | Missing absolute session lifetime | Add time-ceiling policy and re-authentication |
| AS/DB slows down as refresh volume rises | Too-short TTL, retry storms, slow token queries | Benchmark, cap retries, tune indexes/store, rate limit |
| Refresh token appears in logs | Logging bodies/headers or error dumps | Redact, rotate/revoke exposed credentials, check retention |

### 14.1. Sequence for Diagnosing a Refresh Failure

1. Does the token endpoint match the right issuer/URL? Is HTTPS used?
2. Does the request include `grant_type=refresh_token`, a real token, and the proper client authentication method?
3. Which `RegisteredClient` was identified, and is that client allowed to refresh?
4. Does the authorization store hold a record for the refresh token, and is the token active?
5. Does the authorization's `registeredClientId` match the requesting client?
6. Are requested scopes within `authorizedScopes`?
7. Was there prior rotation, concurrent requests, retries, or a dropped response?
8. Are there custom policies on account status, consent, tenant, or absolute session lifetime?
9. If the AS returned tokens successfully yet the API fails, independently check issuer/audience/scope at the RS.

Log request ID/correlation ID, error type, sanitized client ID, provider status, processing duration, and a **keyed one-way hash or dedicated audit ID for the token** if correlation is truly needed; never log raw refresh tokens, access tokens, client secrets, or full request bodies.

## 15. Real-World Design Scenarios

### 15.1. Booking BFF with Browser User Login

Requirement: users work on the web long-term without logging in every 5 minutes; the system has a server-side BFF.

**Suitable design:**

- Authorization Code + PKCE to obtain the initial grant.
- Confidential backend client authenticating at the token endpoint.
- Relatively short access token TTL with refresh tokens stored server-side.
- Rotation or reuse depending on security/UX requirements and concurrency-handling capability.
- Logout/revocation, absolute lifetime, session policies, and RS authorization checks.
- Never hand refresh tokens directly to the browser.

### 15.2. Machine Service with Client Credentials

Requirement: a data-sync job calls APIs hourly with no Resource Owner.

**Direction:** The Client Credentials Grant lets the client request new access tokens directly by authenticating as the client at the token endpoint. A refresh token is typically **unnecessary**, and RFC 6749 recommends against issuing one for this grant. When the access token expires, the client repeats the client credentials grant per policy; do not try to fabricate fake refresh tokens.

### 15.3. Mobile App Requiring Long-Lived Usage

Requirement: no backend holds a client secret; users want infrequent re-logins.

**Direction:** evaluate whether your AS and Spring version provide a secure refresh token issuance mechanism for public clients; if so, you need rotation or appropriate sender-constrained tokens, secure storage, handling for lost tokens/races, and compromise response behavior. Registering `NONE` with `REFRESH_TOKEN` is only one piece and does not guarantee all production logic is provided out of the box.

### 15.4. Admin Portal with Immediate Access Revocation Policy

Requirement: when an employee's permissions are revoked, they must not obtain further access tokens.

**Direction:** beyond protecting refresh tokens, the AS needs grant/token revocation logic or appropriate account status/consent checks. The RS must enforce policies preventing use of previously issued access tokens for sensitive operations; do not rely solely on rotation or browser logout.

## 16. Mistakes to Avoid

| Mistake | Consequence | Right approach |
| --- | --- | --- |
| Sending refresh tokens to a Resource Server | Sensitive credential spreads unnecessarily | Send only to AS token/revocation endpoints |
| Allowing Client B to exchange Client A's refresh token | Breaks client binding and authorization | Check `registeredClientId` and client authentication |
| Allowing new scopes just because they are in `RegisteredClient.getScopes()` | Bypasses initial grant consent/permissions | Use `authorizedScopes` as the upper bound |
| Using an invalidated refresh token to issue access tokens | Replay, unauthorized persistent access | Check `isActive()` and store state |
| Assuming `reuseRefreshTokens(false)` provides family revocation | Incomplete theft detection/remediation | Design explicit replay handling |
| Rotating while the Client fails to persist R2 | Subsequent refreshes fail | Update authorized-client store safely and atomically |
| Two requests refreshing without synchronization | Races, lost new credentials | Single-flight refresh and appropriate optimistic locking |
| Storing authorizations only in memory across multiple AS instances | Lost refresh state on restart/failover | Shared persistence, HA testing |
| Assuming revoking R1 immediately invalidates JWT A1 at RS | Locally verified JWT stays valid until expiry | Design TTL and revocation at RS |
| Putting refresh tokens into localStorage/logs/queries | Credential theft risk | Backend/BFF/secure storage and proper redaction |
| Skipping confidential client auth at refresh endpoint | Caller does not prove valid client identity | Use registered method, adhere to RFC 6749 |
| Issuing perpetual refresh tokens | Unbounded prolonged access | TTL, absolute lifetime, and re-authentication |
| Issuing refresh tokens for Client Credentials just to avoid login calls | Incorrect grant semantics | Use client credentials to request new access tokens |
| Writing a custom refresh handler skipping revocation/scope checks | Issues tokens with wrong permissions | Prefer default `OAuth2RefreshTokenAuthenticationProvider` |

## 17. Implementation Checklist

- [ ] `RegisteredClient` has `REFRESH_TOKEN` grant and client auth method configured properly.
- [ ] Clear understanding of whether the initial grant issues refresh tokens for that client type.
- [ ] Distinguish access token, refresh token, authorization code, and ID token.
- [ ] Token endpoint authenticates clients and matches refresh tokens against client binding.
- [ ] Refresh token is active, unexpired, and not invalidated.
- [ ] Requested scopes do not exceed `OAuth2Authorization.authorizedScopes`.
- [ ] Access/refresh token TTLs chosen per policy, with absolute session lifetime if required.
- [ ] `reuseRefreshTokens` chosen intentionally; if rotating, token updates and races are handled.
- [ ] Policies exist for revocation, logout, user permission changes, and compromise/replay.
- [ ] Authorization store supports multiple instances and is concurrency-tested.
- [ ] Client stores refresh tokens securely, never logging or sending them to RS.
- [ ] Tests cover refresh success, expired, wrong client, wrong scope, reuse, rotation, and replay.
- [ ] Verified RS accepts new access tokens with correct issuer, audience, and scopes.
- [ ] Monitoring covers `invalid_grant`, `invalid_client`, DB performance, and anomalous events.

## 18. Self-Check Questions

**Question 1.** Why doesn't a client with a valid refresh token need the Resource Owner to re-enter a password every time the access token expires?

**Answer:** The AS has persisted the authorization/grant and verifies the refresh token alongside client, scope, and expiration bindings when the client requests a new token. Initial user login and token refresh are two separate stages.

**Question 2.** Can Client A exchange a refresh token issued to Client B if it knows the token string and has similar scope permissions?

**Answer:** No. The AS must match the refresh token to its specific authorization/registered client and authenticate the caller via its registered method.

**Question 3.** Does configuring `reuseRefreshTokens(false)` automatically guarantee replay detection and revocation of the entire token family?

**Answer:** Not by default. It indicates a policy to issue a new refresh token, whereas family tracking, replay detection, incident response, and absolute lifetime must be evaluated and may require customization.

**Question 4.** The initial scope was `booking.read`. Can a refresh request ask for `booking.write` if that scope is listed in RegisteredClient?

**Answer:** No. The scopes granted in the original authorization are the limit; a client cannot escalate permissions solely through the refresh token grant.

**Question 5.** With Client Credentials, is a refresh token required for continuous system operation?

**Answer:** No. The client can use client credentials to request a new access token when needed; RFC 6749 recommends against issuing refresh tokens for this grant.

**Question 6.** Why does logging out of the browser not necessarily invalidate all already-issued access tokens?

**Answer:** Browser sessions, refresh tokens, and access tokens have independent lifecycles. Issued JWTs may still be verified locally by an RS until expiration without additional revocation mechanisms.

**Question 7.** What risks arise when two requests concurrently use R1 under rotation?

**Answer:** One request may receive R2 while the other is rejected because R1 was invalidated; if the client/store handles failures poorly, the new token may be overwritten or the session erroneously deleted. Concurrent refreshes must be coordinated.

## 19. References and Conclusion

Official documentation—always verify against the exact Spring version you run:

- [RFC 6749 — OAuth 2.0, Refreshing an Access Token (Section 6)](https://www.rfc-editor.org/rfc/rfc6749#section-6)
- [RFC 6749 — Refresh Token (Section 1.5)](https://www.rfc-editor.org/rfc/rfc6749#section-1.5)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Core Model and Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Security — OAuth2 Client Authorized Client Manager](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html)
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)

**Summary:** To exchange a refresh token for a new access token, the Authorization Server must authenticate/identify the **right client**, look up the **active refresh token** in `OAuth2AuthorizationService`, respect the **grant type and authorized scopes**, issue an access token per `TokenSettings`, and handle the refresh token under a **reuse or rotation** policy. Refresh token security does not end at returning HTTP 200: you must manage storage, replay, revocation, token families, session lifetimes, and concurrency testing. Properly separating responsibilities among the AS, OAuth2 Client, and Resource Server is essential to maintaining secure sessions in OAuth 2.0/OIDC systems.
