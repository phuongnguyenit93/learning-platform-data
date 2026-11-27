# Scope Requests During Refresh and the No-Privilege-Escalation Principle

## 1. The Problem to Solve

In a **Spring Security OAuth2/OIDC Authorization Server**, once an application has been granted authorization by a user, it may receive a **refresh token** to request new access tokens without sending the browser back through the Authorization Endpoint every time an access token expires. The critical security question is:

> When using a refresh token, can a client send an additional scope that was never approved to obtain an access token with broader permissions?

**No.** Per **RFC 6749 §6**, the `scope` parameter in a refresh token request is **optional**. If provided, the requested scope **must not include any scope outside the set originally granted to that authorization**. If omitted, the request is treated as requesting the originally granted scope.

In the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, our goal is to learn how to **design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in Spring Boot**. This lesson belongs to the **Refresh Token** chapter and focuses on handling the `scope` parameter during refresh, the source of truth determining the maximum permission set, common mistakes, and tests required before production operation.

After completing this lesson, you should be able to:

1. Distinguish **client-registered scopes**, **user-consented scopes**, **actual authorization scopes**, **refresh-requested scopes**, and **scopes on the new access token**.
2. Know how refresh requests **without `scope`**, with **narrowed scopes**, or with **excessive scopes** are handled.
3. Understand why **privileges cannot be escalated via a refresh token**, even if client metadata or user roles change later.
4. Identify the roles of **`RegisteredClientRepository`**, **`OAuth2AuthorizationService`**, **`OAuth2RefreshTokenAuthenticationProvider`**, and **`OAuth2TokenGenerator`** in Spring Authorization Server.
5. Design tests for refresh token rotation, permission revocation policies, OIDC, JWT/opaque tokens, and multi-instance deployments.

**Example scope:** APIs and configurations are presented using **Spring Authorization Server 1.5.x / Spring Security 6.x / Spring Boot 3.x**. When using Spring Security 7.x or newer versions, verify the Javadoc, dependencies, and behavior of that exact version. We do not assume every client type, particularly public SPAs, always receives a refresh token by default.

## 2. Five Scope Sets to Distinguish

Consider client `orders-bff`, user `alice`, and an order management API.

| Symbol | Scope set | Who decides? | Example |
| --- | --- | --- | --- |
| **R** | Scopes **registered** for the client | Client administration / `RegisteredClient.scopes` | `{orders.read, orders.write, orders.export}` |
| **G** | Scopes **actually granted** to an authorization | Authorization request, user consent, and AS policy | `{orders.read, orders.write}` |
| **Q** | Scopes the client **requests on refresh** | The `scope` parameter in the current request, if any | `{orders.read}` |
| **I** | Scopes **actually issued** on the new access token | Authentication provider + token policy | `{orders.read}` |
| **P** | Scope **still permitted by current policy**, if re-evaluated | Account lifecycle, client lifecycle, tenant/entitlement, and resource policies | May shrink because user lost export permission |

Core conditions:

```text
Refresh request WITHOUT scope:
    Q defaults to G           (per RFC 6749 §6)

Refresh request WITH scope:
    Q ⊆ G                     (must not expand beyond original grant)

New access token:
    I ⊆ Q                     (if Q is sent and server applies strict policy)
    or I ⊆ G                  (if Q is omitted)

If implementing dynamic downscoping policy P:
    I ⊆ G ∩ P                 (additional policy designed by the application)

Never set G := R to retroactively elevate an old grant.
```

This is a **reasoning model**. In concrete implementations, an Authorization Server may use a normalized scope set and reject rather than automatically narrowing by `P`. The essential normative principle is **never granting additional permissions outside the original grant via a refresh token**.

### 2.1. Why Isn't `RegisteredClient.scopes` Enough?

A client may register many scopes, yet the user only approves a subset. For example:

```text
Client registration R = {orders.read, orders.write, orders.export}
Authorization grant G = {orders.read, orders.write}

Refresh with scope=orders.export
    -> INVALID, even though orders.export is in RegisteredClient.scopes

Refresh with scope=orders.read
    -> VALID under the subset rule, provided all other conditions hold
```

Checking only `requestedScopes ⊆ registeredClient.getScopes()` is **insufficient**: it allows a client to expand scope to a permission that was **registered but never granted in the current authorization**.

### 2.2. Why Isn't Previously Stored Consent Enough Either?

`OAuth2AuthorizationConsentService` may hold permissions a user previously approved for a client, yet a specific refresh token must remain bound to **the authorization from which it originated**. Consent from another time, newly approved scopes in another session, or new scopes added to the registration **do not automatically convert an old refresh token into permission to issue broader access tokens**.

**The decisive anchor** for the refresh token grant is the authorization associated with that refresh token and its originally granted scope set. Consent, registration, and policies can serve as additional evaluation inputs; they do not replace the anti-escalation requirement.

## 3. What Does RFC 6749 §6 Say About `scope`?

For a valid refresh token, the Token Endpoint receives a request of the form:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_CLIENT_ID_AND_SECRET
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=REFRESH_TOKEN_VALUE
```

Protocol rules:

1. `grant_type=refresh_token`: **required**.
2. `refresh_token`: **required**; value must have been issued to the matching client and remain valid.
3. `scope`: **optional**; if present, must be a subset of the scopes belonging to the original authorization.
4. A confidential client or client requiring authentication must perform **client authentication** using its registered method.
5. The AS must verify the token, client binding, expiration/revocation state, and grant policies before issuing a new access token.

RFC 6749 also notes a crucial detail: **if the AS returns a new refresh token upon refresh, the new refresh token must have the same scope as the refresh token sent in the request**. Narrowing the new access token **does not implicitly shrink the scope of the rotated refresh token**.

### 3.1. Three Cases to Remember

Suppose the original authorization was granted:

```text
G = {orders.read, orders.write}
```

| Request to Token Endpoint | Outcome under scope rules | Explanation |
| --- | --- | --- |
| No `scope` | May issue access token with scopes from **G** | Omitting the parameter means re-requesting the granted scope, not empty |
| `scope=orders.read` | May issue access token with only `orders.read` | Valid subset of G |
| `scope=orders.write` | May issue access token with only `orders.write` | Still within G |
| `scope=orders.read orders.write` | May issue access token with both permissions | Equal to G |
| `scope=orders.export` | **Rejected** | Permission not in G |
| `scope=orders.read orders.export` | **Rejected** | Contains a scope exceeding G; do not partially accept without explicit policy |
| `scope=admin` | **Rejected** | Cannot use refresh to escalate to admin |
| `scope=` (parameter present but empty) | Treated as malformed/invalid request per validator | **Do not treat as parameter omission by default** |

**Important distinction:** "Not sending the `scope` parameter" differs from "sending `scope` with an empty value." When writing HTTP clients, use standard form-encoding APIs and test malformed/duplicate parameters instead of ad-hoc string concatenation.

### 3.2. Scope Is a Space-Delimited String

Per RFC 6749 §3.3, `scope` format consists of space-separated **scope-tokens**. With HTTP form encoding:

```text
scope=orders.read%20orders.write
```

or let the HTTP client URL-encode automatically. **Scope names are case-sensitive** in typical OAuth handling, so `orders.read` is a different permission from `orders.Read`. Do not interpret commas as scope delimiters:

```text
scope=orders.read,orders.write
```

The string above is not equivalent to two separate scopes unless the system intentionally defined a scope token containing a comma (discouraged due to confusion). Never accept unfamiliar scope names just because they start with a familiar prefix.

## 4. Refresh Flow Diagram Under Granted Scope

```mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client / BFF
    participant T as Token Endpoint
    participant R as RegisteredClientRepository
    participant A as OAuth2AuthorizationService
    participant G as OAuth2TokenGenerator
    C->>T: POST grant_type=refresh_token, refresh_token, scope?
    T->>R: Authenticate/look up client, verify grant
    T->>A: findByToken(refresh_token, REFRESH_TOKEN)
    A-->>T: Authorization, refresh token state, authorizedScopes=G
    T->>T: Check matching client, active, expiresAt/revoked
    alt scope sent but not a subset of G
        T-->>C: OAuth error: invalid_scope
    else scope valid or omitted
        T->>T: Select new access token scope from G / Q
        T->>G: generate access token with resolved authorizedScopes
        G-->>T: Token and corresponding claims
        T->>A: save updated authorization/token state
        T-->>C: New access token (+ refresh token if rotated)
    end
```

The diagram shows that the **authentication provider** is the orchestrator. It calls the repository/service/generator to ensure valid grant and scope. Neither does the client write scopes into the access token itself, nor does `OAuth2TokenGenerator` arbitrarily add permissions based on client name.

### 4.1. Example A — Refresh Without Sending Scope

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_CLIENT_ID_AND_SECRET
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=RT_FOR_ORDERS_GRANT
```

If the token belongs to the original authorization with `{orders.read, orders.write}` and all other conditions are valid, the AS can issue an access token with that granted scope set. **Omitting `scope` does not mean "fewer permissions."**

### 4.2. Example B — Refresh Requesting Read-Only Scope

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_CLIENT_ID_AND_SECRET
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=RT_FOR_ORDERS_GRANT&scope=orders.read
```

Illustrative response example:

```json
{
  "access_token": "NEW_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders.read"
}
```

Tokens in examples are **placeholders**; a real AS may include other valid fields, such as a new `refresh_token` under rotation and profile-supported metadata. For JWT access tokens, verify the actual scope claim inside the token and Resource Server validation, not solely the JSON response field.

**Consequence:** the new access token works for calling APIs requiring only `orders.read`, not endpoints needing `orders.write`.

### 4.3. Example C — Client Attempting to Escalate Permissions

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_CLIENT_ID_AND_SECRET
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=RT_FOR_ORDERS_GRANT&scope=orders.read%20orders.export
```

Token Endpoint OAuth error response:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "error": "invalid_scope"
}
```

This example is the **expected outcome when the client authenticated and the refresh token is still valid**, yet the request exceeds the granted permissions. If client authentication is wrong or the refresh token is invalid, the AS may return a **different** OAuth error such as `invalid_client`/`invalid_grant` per check ordering. Never rely on the HTTP status of a different failure to conclude the scope validator ran.

## 5. Where Does Spring Authorization Server Store Scope Information?

### 5.1. RegisteredClient Is the Registration Limit, Not the Active Authorization

`RegisteredClient` has `scopes` and `authorizationGrantTypes`. These attributes indicate the **configured capabilities/boundaries** for the client. For example:

```java
RegisteredClient ordersBff = RegisteredClient.withId("orders-bff-internal-id")
        .clientId("orders-bff")
        .clientSecret(encodedClientSecret)
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri("https://orders.example.com/login/oauth2/code/orders-bff")
        .scope(OidcScopes.OPENID)
        .scope("orders.read")
        .scope("orders.write")
        .scope("orders.export")
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(true)
                .build())
        .tokenSettings(TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(10))
                .refreshTokenTimeToLive(Duration.ofHours(8))
                .reuseRefreshTokens(false)
                .build())
        .build();
```

This snippet is a **model configuration excerpt**; you must import the corresponding Spring/Java classes and supply `encodedClientSecret` encoded/hashed with an appropriate `PasswordEncoder`. A valid registration must also be persisted in `RegisteredClientRepository`. Never put plaintext secrets in source code.

Even when the registration contains `orders.export`, that **does not** prove `alice`'s authorization was ever granted that permission.

### 5.2. OAuth2Authorization Stores the Scopes of the Active Grant

`OAuth2Authorization` represents a specific authorization and contains:

- `registeredClientId`: links to the internal ID of `RegisteredClient`.
- `principalName`: the user or subject matching the grant.
- `authorizationGrantType`: the initial grant type.
- `authorizedScopes`: **the scope set actually granted** to that authorization.
- `OAuth2Authorization.Token<OAuth2RefreshToken>`: the refresh token and corresponding metadata/status.
- Other access tokens/ID tokens when present.

Example reading data from the service (illustrating relationships; not an HTTP authentication method):

```java
import java.util.Set;
import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;

public class RefreshGrantInspection {
    private final OAuth2AuthorizationService authorizationService;

    public RefreshGrantInspection(OAuth2AuthorizationService authorizationService) {
        this.authorizationService = authorizationService;
    }

    public Set<String> findGrantScopes(String refreshTokenValue) {
        OAuth2Authorization authorization = authorizationService.findByToken(
                refreshTokenValue, OAuth2TokenType.REFRESH_TOKEN);
        if (authorization == null || authorization.getRefreshToken() == null ||
                !authorization.getRefreshToken().isActive()) {
            throw new IllegalStateException("Refresh token is not active");
        }
        return authorization.getAuthorizedScopes();
    }
}
```

**Warning:** The code above is only to explain the storage model. It **does not check client binding, grant, caller identity, token endpoint policy, or caller authorization**; never expose a custom endpoint built on this method. In a real application, Spring Authorization Server's `AuthenticationProvider` implementations must enforce all protocol conditions.

### 5.3. Consent Is a Separate Layer, Not a Source to Expand Refresh Permissions

`OAuth2AuthorizationConsentService` can store permissions a user approved for a client. However:

- The user may approve an additional scope in a **new authorization flow**.
- Registration may have scopes added administratively.
- An **existing** authorization still retains the `authorizedScopes` from its own issuance.

Never sum scopes seen in consent/registration to add permissions to an old refresh token. To request new scopes, initiate a new authorization flow with required authentication/consent and conditions.

## 6. Verification Flow in OAuth2RefreshTokenAuthenticationProvider

In Spring Authorization Server, the components participating at the Token Endpoint include:

| Component | Role |
| --- | --- |
| `OAuth2TokenEndpointFilter` | Receives HTTP POST to the Token Endpoint. |
| `OAuth2RefreshTokenAuthenticationConverter` | Converts the `grant_type=refresh_token` request into an authentication token containing the refresh token and requested scopes. |
| `OAuth2RefreshTokenAuthenticationProvider` | Executes refresh grant validation and orchestrates token issuance. |
| `RegisteredClientRepository` | Resolves the client and grant/credential policies. |
| `OAuth2AuthorizationService` | Looks up the authorization by refresh token, checks state, and saves results. |
| `OAuth2TokenGenerator<?>` | Generates tokens per provider-established context; not a place to elevate privileges. |

In a valid flow, the provider must examine **the authenticated client**, **which client the refresh token is bound to**, **whether the token is active**, **whether the grant is allowed**, and **whether requested scopes lie within the original authorization**. It then selects scopes for the new access token and invokes the generator.

```mermaid
flowchart TD
    A["POST /oauth2/token<br/>grant_type=refresh_token"] --> B{"Valid client authentication and<br/>refresh grant?"}
    B -->|"No"| E["Appropriate OAuth error<br/>invalid_client / unauthorized_client"]
    B -->|"Yes"| C{"Refresh token found,<br/>matches client, and active?"}
    C -->|"No"| F["invalid_grant"]
    C -->|"Yes"| D{"Scope parameter present?"}
    D -->|"No"| G["Use authorization's<br/>authorizedScopes G"]
    D -->|"Yes"| H{"Requested scopes Q ⊆ G?"}
    H -->|"No"| I["invalid_scope"]
    H -->|"Yes"| J["Use valid subset Q"]
    G --> K["Token generator + additional policies"]
    J --> K
    K --> L["Save new token/authorization<br/>and return token response"]
```

This is a **conceptual decision flow**, not a source-code trace or mandatory exception ordering across every version. Error codes/responses may vary when requests are malformed or client authentication fails before the scope check.

### 6.1. Why Never Customize a Provider to "Relax" Scopes?

Spring Authorization Server enforces grant constraints in the provider. If a project customizes the Token Endpoint, never accidentally replace the validator with:

```java
// WRONG: comparing requested scopes only against registration.
if (registeredClient.getScopes().containsAll(requestedScopes)) {
    // Does not mean the refresh token was granted these scopes!
    issueTokenWith(requestedScopes);
}
```

This is **counter-example pseudocode**, not standard API usage. Putting registered-but-ungranted scopes into a new access token is **privilege escalation**. Any valid extension must preserve the `Q ⊆ G` invariant, then apply stricter current policies if needed.

## 7. Java Example Modeling the No-Escalation Principle

The following code is a **pure Java policy** for learning, unit testing, and designing application validation. It does not replace `OAuth2RefreshTokenAuthenticationProvider`'s internal validator.

```java
import java.util.Objects;
import java.util.Set;

public final class RefreshScopePolicy {
    private RefreshScopePolicy() {}

    /**
     * @param granted      scopes stored on the original authorization (G)
     * @param requested    scopes parsed from the request (Q), if scopePresent=true
     * @param scopePresent whether scope actually appeared in the HTTP form
     */
    public static Set<String> chooseScopes(
            Set<String> granted,
            Set<String> requested,
            boolean scopePresent) {

        Objects.requireNonNull(granted, "granted scopes");

        if (!scopePresent) {
            return Set.copyOf(granted); // RFC 6749 §6: defaults to G
        }
        if (requested == null || requested.isEmpty()) {
            throw new IllegalArgumentException("invalid_scope");
        }
        if (!granted.containsAll(requested)) {
            throw new IllegalArgumentException("invalid_scope");
        }

        return Set.copyOf(requested); // valid narrowed request
    }
}
```

In a real Authorization Server:

- HTTP parsing must use framework components to guard against duplicate/malformed parameters and validate scope token syntax.
- Application exceptions must map properly to an **OAuth2 error response** (typically `invalid_scope`), without exposing internal grant sets or stack traces.
- The provider must also verify matching client, refresh token expiry/invalidation, current consent/policies if applicable, and other security constraints.
- If a dynamic downscoping policy exists, **do not** replace `granted` with client-registered scopes or current user roles to allow expansion. Apply an extra restriction layer atop the original grant.

### 7.1. Unit Test for the Subset Invariant

```java
import java.util.Set;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class RefreshScopePolicyTest {
    private static final Set<String> GRANTED =
            Set.of("orders.read", "orders.write");

    @Test
    void omittedScopeMeansOriginallyGrantedScopes() {
        assertThat(RefreshScopePolicy.chooseScopes(GRANTED, null, false))
                .containsExactlyInAnyOrder("orders.read", "orders.write");
    }

    @Test
    void requestedSubsetIsAllowed() {
        assertThat(RefreshScopePolicy.chooseScopes(
                GRANTED, Set.of("orders.read"), true))
                .containsExactly("orders.read");
    }

    @Test
    void requestedScopeOutsideGrantIsRejected() {
        assertThatThrownBy(() -> RefreshScopePolicy.chooseScopes(
                GRANTED, Set.of("orders.read", "orders.export"), true))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("invalid_scope");
    }

    @Test
    void explicitEmptyScopeIsNotOmission() {
        assertThatThrownBy(() -> RefreshScopePolicy.chooseScopes(
                GRANTED, Set.of(), true))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
```

This is a **policy unit test example**. It verifies subset comparison, **not** that Spring's real Token Endpoint blocks privilege escalation; you must add HTTP integration tests with real refresh tokens.

## 8. When Client or User Scopes Change After Refresh Token Issuance

This area frequently produces security bugs in long-running systems.

### 8.1. Client Receives Additional Scopes in Registration

Day 1:

```text
RegisteredClient.scopes = {orders.read, orders.write}
Authorization G          = {orders.read}
```

Day 2, an administrator updates registration:

```text
RegisteredClient.scopes = {orders.read, orders.write, orders.export}
Old Authorization G      = {orders.read}   // does not change automatically
```

A client attempting to send `scope=orders.export` with Day 1's refresh token must be **rejected**. Changing registration modifies permissions **that may be granted in the future**, not a retroactive approval for previously issued refresh tokens.

To receive the new permission, the client must initiate an appropriate authorization flow with the new scope, with the AS checking policy and user consent as needed before issuing a new authorization/tokens.

### 8.2. Client Loses a Scope or User Loses Permissions

Suppose `orders.write` was previously in G, yet now the user lost order-editing rights or an admin removed that scope from registration:

- **RFC §6 minimum rule:** a refresh request must not request scopes outside **G**, yet this **does not automatically guarantee the framework re-checks every entitlement/registration change** during refresh.
- **Business need:** if `orders.write` must be revoked immediately, design authorization/refresh token updates or revocation, check entitlements at the Token Endpoint and **Resource Server**, or apply another sufficiently strong policy.
- **Old JWT access tokens:** if APIs verify JWTs offline, permission changes at the AS do not automatically invalidate unexpired JWTs.
- **Re-authorization:** the client needs a new authorization flow when requesting scopes outside G; if the user is no longer permitted, the new flow must block it too.

Never claim "removing a scope from client registration" suffices to make **all old access/refresh tokens** lose permissions immediately. That is a broader **revocation/permission-change workflow**.

### 8.3. Does Narrowing Scope on One Refresh Change the Grant Forever?

**Not by default.** Suppose original G is `{orders.read, orders.write}`:

```mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client
    participant AS as Authorization Server
    C->>AS: Refresh #1, scope=orders.read
    AS-->>C: Access Token #1: {orders.read}
    Note over AS: Original grant G may still be {read, write}
    C->>AS: Refresh #2, scope omitted
    AS-->>C: Access Token #2: {orders.read, orders.write} (if original grant/policy still permits)
```

This is a **valid scenario under RFC 6749 §6 semantics**, because the first refresh only requested a **narrower access token**, not a permanent modification of the grant/consent. If the AS rotates the refresh token, the RFC specifies that the replacement refresh token's scope **matches the previous refresh token**; do not equate it with the narrowed access token's scope.

If the product requires **permanent downscoping**, modify or revoke the authorization/consent/tokens per policy and create an appropriate new grant, rather than relying on the client sending `scope=orders.read` once.

## 9. Refresh Token Rotation, Client Binding, and Scope

### 9.1. Three Independent Protection Axes

| Axis | Question | Mechanism |
| --- | --- | --- |
| **Permissions** | Do the new access token's scopes exceed the original grant? | `Q ⊆ G`, authorization policy, Resource Server authorization |
| **Subject/client** | Is the refresh token used by the exact client that received it? | Client authentication/sender constraint, client binding |
| **Lifecycle** | Is the refresh token still active, expired, or reused? | `OAuth2AuthorizationService`, TTL, rotation, revocation, replay handling |

Scope checks **do not** replace client authentication. A stolen refresh token can still be abused within its granted scope if unprotected. Conversely, valid client credentials do not allow requesting extra scopes outside G.

### 9.2. Configuring Lifetimes and Rotation

In Spring Authorization Server, `TokenSettings` can configure:

```java
TokenSettings tokenSettings = TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(10))
        .refreshTokenTimeToLive(Duration.ofDays(7))
        .reuseRefreshTokens(false)
        .build();
```

This is only a policy snippet for `RegisteredClient`. When `reuseRefreshTokens(false)`, the AS can issue a new refresh token on a valid refresh; the application must update its stored credential **safely**. Rotation does not turn a narrowed access token scope into a permanently removed grant permission.

**Important:** rotating a single token and **detecting token-family replay with whole-family revocation** are not the same guarantee. When deploying public clients or requiring abuse detection, verify actual version/framework features and build additional policies/tests per RFC 9700.

### 9.3. Storing Client Credentials and Refresh Tokens Securely

- Transmit refresh tokens only over **HTTPS**, in the Token Endpoint's form body, never in URLs.
- Protect secrets/tokens on a backend/BFF or appropriate secure storage; never write raw values into logs/tracing/metric labels.
- Use sender-constraining or rotation where appropriate, especially for public clients per RFC 9700.
- Design idempotency/retries carefully: two concurrent refresh requests can race on rotation, causing `invalid_grant` or reuse of an already-replaced token.
- Never embed refresh tokens in access token JWT claims or application data responses.

**Note on public SPAs:** some Spring Authorization Server versions, such as the public client flow in the 1.5.x PKCE guide, do not issue refresh tokens by default to clients using `ClientAuthenticationMethod.NONE`. Never assume configuring `authorizationGrantType(REFRESH_TOKEN)` guarantees an SPA receives a refresh token; verify real behavior and consider a BFF when appropriate.

## 10. OIDC: `openid` Scope, ID Tokens, and Refresh Grant

In OpenID Connect, `openid` is the scope that triggers an OIDC authentication request. Scopes like `profile` or `email` typically request additional claims per provider policy. On refresh:

1. A refresh token originating from an OIDC authorization **remains bound by the original grant**; the client cannot use it to "add" ungranted `email` or `admin`.
2. If the Token Endpoint supports issuing an ID token during refresh, its contents must satisfy **OIDC Core §12**, issuer/audience/signature, timestamps, and related conditions. **Never assume** every refresh response contains an ID token.
3. Changes to user consent/claims do not turn a refresh request into a new interactive user authorization request.
4. Scopes appearing on an access token and claims inside an ID token/UserInfo are related but **not identical**; `scope=profile` does not guarantee a specific claim field appears identically across every provider.

For example, a client originally granted only `openid profile` must have a refresh request with `scope=openid email` **rejected**, unless `email` truly belonged to the original authorization's scope. To gain new permissions, run an appropriate authorization flow/consent.

## 11. Difference Between Token Response and Resource Server Permissions

Never check only HTTP 200 from the Token Endpoint. Ensure actually granted scopes are reflected consistently across:

- The `scope` field in the token response when provided per protocol.
- JWT access token claims (such as the `scope` claim in the relevant profile), or introspection metadata for opaque tokens.
- `OAuth2Authorization.Token<OAuth2AccessToken>` and the AS token-issuance context.
- Authorization rules at the Resource Server: `POST /orders/{id}` must require `orders.write` and reject tokens having only `orders.read`.

An access token **with valid scopes** must still undergo issuer, audience, expiry, signature/token-state checks, and related constraints. Scopes do not replace record ownership or tenant isolation.

### 11.1. Caution When Customizing JWT Claims

If a project uses `OAuth2TokenCustomizer<JwtEncodingContext>`, never write:

```java
// WRONG: adding permissions just because the account has ROLE_ADMIN.
context.getClaims().claim("scope", "orders.read orders.write admin");
```

This snippet is a counter-example, not how to build tokens. Every claim representing **scopes/permissions** must come from valid authorization decisions, never copying all current user roles into an access token during a refresh flow.

Specifically, adding a custom claim under a different name from `scope` can still create privilege escalation if the Resource Server treats that claim as an access permission. Test both **how the Token Generator produces claims** and **how the Resource Server interprets claims**.

### 11.2. What If the Token Endpoint Issues Narrow Scopes Yet the API Still Permits Writes?

Check:

1. Does the actual JWT/introspection unexpectedly contain `orders.write`?
2. Does Spring Security Resource Server map scopes to `SCOPE_orders.write`, or is it overly broadly mapping roles?
3. Does the API enforce scope checks on the sensitive endpoint?
4. Is there stale authorization caching at an API gateway/Resource Server?
5. Was an older access token (issued with broader scopes) sent instead of the newly narrowed token?

The AS returning `scope=orders.read` in JSON while the Resource Server still permits writes is an **end-to-end authorization issue**, not solely a bug in refresh token grant code.

## 12. HTTP Testing with Spring Boot

### 12.1. Recommended Test Dataset

Prepare:

- A confidential client `orders-bff` registered with `authorization_code` and `refresh_token` for scopes `openid`, `orders.read`, `orders.write`, `orders.export`.
- A test user who granted **only** `openid`, `orders.read`, and `orders.write`, excluding `orders.export`.
- An authorization stored via `OAuth2AuthorizationService`, holding an active refresh token bound to the exact `registeredClientId`.
- A test Resource Server with a read endpoint requiring `orders.read` and a write endpoint requiring `orders.write`.
- Fixtures created through a real authorization flow (preferred) or via controlled integration test service setup.

Assume:

```text
R = {openid, orders.read, orders.write, orders.export}
G = {openid, orders.read, orders.write}
```

### 12.2. Scope Test Matrix

| ID | Refresh request | Expected outcome |
| --- | --- | --- |
| S01 | No `scope` sent | May issue access token per G, if refresh token and client are valid |
| S02 | `scope=orders.read` | New token has read permission only, never automatically includes `orders.write` |
| S03 | `scope=orders.write` | Scope is within G; request allowed regarding scope |
| S04 | `scope=openid orders.read` | Valid subset when other OIDC/grant conditions are met |
| S05 | `scope=openid orders.read orders.write` | Equal to G; valid regarding scope |
| S06 | `scope=orders.export` | Rejected `invalid_scope` even though this scope is in R |
| S07 | `scope=orders.read orders.export` | Rejected; never issues a token broader than G |
| S08 | `scope=admin` | Rejected `invalid_scope` |
| S09 | `scope=orders.Read` | Rejected if absent from G; scopes are case-sensitive |
| S10 | `scope=` present but empty | Rejected as malformed/invalid request per validator, not treated as omission |
| S11 | Duplicate/improperly encoded `scope` parameter | Reject ambiguous/malformed request; never pick one value arbitrarily |
| S12 | Update R to add `orders.admin`, then refresh old token asking for it | Still rejected; old G does not change |
| S13 | Refresh #1 `scope=orders.read`, Refresh #2 omits scope | Do not **assume** #1 permanently stripped `orders.write` from G |
| S14 | Expired/invalidated refresh token | `invalid_grant` or corresponding OAuth error; no token issued |
| S15 | Refresh token belonging to another client | Rejected per binding/client authentication; no token issued |
| S16 | Client lacks `refresh_token` grant permission | Rejected per client/grant policy |
| S17 | User or client disabled per custom policy | Stop issuing tokens if business rule requires halting issuance |
| S18 | JWT issued with read scope calls write API | Resource Server returns insufficient-permission error per policy; blocks write |

Cases labeled "valid regarding scope" **do not automatically guarantee token issuance succeeds**: the refresh token must remain unexpired, unrevoked, bound to the right client, and satisfy all other policies.

### 12.3. Curl Test Requests

Run only in **test environments**, using fixture credentials and avoiding printing tokens into shared terminal logs:

```bash
# Request an access token narrower than the original grant.
curl --request POST 'https://auth.test.example/oauth2/token' \
  --user 'orders-bff:TEST_CLIENT_SECRET' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=refresh_token' \
  --data-urlencode 'refresh_token=TEST_REFRESH_TOKEN' \
  --data-urlencode 'scope=orders.read'
```

To test privilege escalation attempts, replace with:

```bash
curl --request POST 'https://auth.test.example/oauth2/token' \
  --user 'orders-bff:TEST_CLIENT_SECRET' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=refresh_token' \
  --data-urlencode 'refresh_token=TEST_REFRESH_TOKEN' \
  --data-urlencode 'scope=orders.read orders.export'
```

All values are placeholders. With real secrets/tokens, avoid placing them in shell history, command-line arguments visible to other processes, or CI logs. Prefer test clients using secure secret injection and redaction tooling.

**Reading results:** if the second call fails with `invalid_grant` because the refresh token rotated/expired during the first call, the test **has not proven** the `invalid_scope` rule. Use independent fixtures or mint a fresh refresh token before each case to isolate causes.

### 12.4. Testing JWT/Opaque Tokens and State Models

After each successful refresh:

1. Inspect the **actual** scope set of the new access token (JWT claims or introspection), not just the HTTP response.
2. Verify the narrowed access token cannot call endpoints requiring broader scopes.
3. Verify the new refresh token (if rotated) replaces the old token properly; do not assume the refresh token's scope was permanently narrowed.
4. Verify `OAuth2AuthorizationService` persists token state consistently across restarts/multiple instances.
5. Send error requests and verify no new token is issued.

## 13. Multi-Instance Operations, Permission Changes, and Revocation

### 13.1. Multiple Nodes Handling Refreshes Concurrently

```mermaid
flowchart LR
    C["OAuth2 Client / BFF"] --> LB["Load Balancer"]
    LB --> A["AS node A"]
    LB --> B["AS node B"]
    A --> DB[("Shared OAuth2AuthorizationService<br/>G + refresh token state")]
    B --> DB
    A --> CLIENT[("RegisteredClientRepository<br/>client / grants / token policy")]
    B --> CLIENT
```

If AS A stores authorizations in its own memory while AS B receives the refresh request, B may fail to find the refresh token. For production, consider `JdbcOAuth2AuthorizationService` or equivalent durable shared storage and resolve concurrency/transactions during refresh rotation. **Never fix distributed state bugs by removing scope validation.**

### 13.2. Emergency Permission Revocation

Suppose `alice` loses `orders.write` due to changing departments. A safe procedure typically requires:

1. Recording the entitlement/consent change per product policy.
2. Blocking issuance of new access tokens containing `orders.write`, including refresh requests that **omit scope** (which would otherwise default to old G).
3. Revoking or invalidating related refresh tokens/authorizations as needed; do not expect changing registration alone to suffice.
4. Handling already-issued access tokens at Resource Servers: short TTL, opaque introspection, denylists, or an appropriate state-checking policy.
5. Verifying impact across all nodes, caches, clients, and APIs; write audit records without raw tokens.

**Distinction:** RFC §6 guarantees **no privilege escalation** via refresh. That rule **does not automatically guarantee immediate privilege reduction when a user's entitlements change**. Requirements to terminate existing access must be designed as a separate operational mechanism.

### 13.3. Incident Monitoring Without Leaking Information

Monitor rates of `invalid_scope`, `invalid_grant`, client auth failures, refresh rotation failures, and revocation calls. Separate error causes:

- `invalid_scope`: invalid scope request or exceeding the original grant.
- `invalid_grant`: expired/invalid/revoked refresh token or wrong grant/client binding.
- `invalid_client`: client authentication failure when applicable.
- `unauthorized_client`: client not permitted to use the grant per policy.
- `invalid_request`: missing, duplicate, or malformed parameters.

Specific error codes depend on the Token Endpoint's validation context; **never disclose a user's granted scope set** just to explain why a request was invalid. Log correlation IDs, sanitized client IDs, error types, request outcomes, and redacted operational details—never log refresh tokens, access tokens, client secrets, or full JWT payloads.

## 14. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "Omitting `scope` means requesting no permissions." | For the refresh grant, omitting scope means re-requesting the **originally granted** scope. |
| "If the client registers `admin`, an old refresh token can request `admin`." | No; Q must belong to the original authorization G. |
| "Expanding consent later means old refresh tokens gain elevated permissions." | Not automatically; the old grant retains its own granted scope. |
| "`scope=orders.read` on the first refresh makes the refresh token read-only forever." | Not by default; narrowing the current access token differs from revoking grant/refresh token permissions. |
| "Rotating a refresh token changes its scope to match the new access token." | RFC 6749 §6 requires the new refresh token to retain the **same scope** as the prior refresh token. |
| "Having a valid client secret allows requesting any scope in registration." | No; client auth does not bypass G's boundaries. |
| "Checking only `registeredClient.getScopes()` is sufficient." | No; you must check the granted authorization and additional policies. |
| "Fewer scopes means previously issued JWTs also shrink in scope." | No; already-signed JWTs do not mutate. |
| "Removing `orders.write` from registration makes every API block old tokens immediately." | No; you need revocation strategies and Resource Server checks. |
| "Seeing `invalid_grant` means the `invalid_scope` test passed." | False; you need an active refresh token, matching client, and isolated fixtures. |
| "`OAuth2AuthorizationConsentService` is where the Token Endpoint pulls new scopes." | Consent does not automatically grant broader scopes than the original grant on refresh. |
| "A JWT customizer can add any permissions freely." | Resource Servers may trust those claims; bind them strictly to actual grant policy. |

## 15. Production Checklist

**Permission boundaries**

- [ ] Refresh requests **without scope** resolve to the original grant, never treated as empty permissions.
- [ ] Refresh requests **with scope** must be a subset of the authorized scopes of the exact authorization holding the refresh token.
- [ ] Never escalate permissions by substituting `RegisteredClient.scopes` or newer consent for the original grant.
- [ ] Verify new token responses and JWT/introspection tokens contain no scopes exceeding granted permissions.
- [ ] Resource Servers genuinely enforce scopes on sensitive APIs.

**Security and lifecycle**

- [ ] Refresh tokens are bound to the exact client, active, and the `refresh_token` grant is permitted.
- [ ] Confidential clients authenticate via registered methods; public clients follow the deployment version's refresh token protection policy.
- [ ] Token TTLs, rotation/replay handling, concurrent refreshes, and logout/revocation are tested.
- [ ] User/client lifecycle changes connect to token issuance and revocation policies.
- [ ] Raw refresh/access tokens and secrets are never written to logs/tracing/analytics.

**Testing and operations**

- [ ] Tests cover omitted, subset, equal, superset, unknown, empty, duplicate, and case-sensitive scopes.
- [ ] Tests verify newly registered scopes after an old grant was created cannot be obtained via the old refresh token.
- [ ] Tests confirm narrowing scope on one refresh is **not mistakenly assumed** to narrow the grant forever.
- [ ] Tests cover multi-node, restarts, token rotation, and durable authorization state.
- [ ] Metrics exist for `invalid_scope`/`invalid_grant`, secure auditing, and emergency permission revocation at APIs.

## 16. References

- [RFC 6749 §6 — Refreshing an Access Token](https://www.rfc-editor.org/rfc/rfc6749#section-6): optional `scope`, must fall within original grant, client binding, new refresh token keeps same scope.
- [RFC 6749 §3.3 — Access Token Scope](https://www.rfc-editor.org/rfc/rfc6749#section-3.3): scope syntax and semantics.
- [RFC 6749 §5.1–5.2 — Token Response and Error Response](https://www.rfc-editor.org/rfc/rfc6749#section-5.1): `scope` field in token responses and OAuth errors.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): refresh token protection, rotation/sender-constraining, least-privilege scopes, and modern security recommendations.
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, `OAuth2AuthorizationService`, and `authorizedScopes`.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): Token Endpoint, authentication converter/provider, and security configuration.
- [Spring Authorization Server — How to Implement Core Services with JPA](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-jpa.html): client/authorization persistence model and data references.
- [Spring Authorization Server — SPA Authentication with PKCE](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-pkce.html): characteristics of public clients and refresh token limits in the corresponding version guide.
- [OpenID Connect Core 1.0 §12 — Using Refresh Tokens](https://openid.net/specs/openid-connect-core-1_0.html#RefreshTokens): refresh rules in an OIDC context.

**Conclusion:** A refresh token lets a client request **a new access token within previously granted permissions**, not an opportunity to claim new permissions. Omitting `scope` means using the original grant's scope; sending `scope` allows requesting only a **subset** of that grant. In Spring Authorization Server, rely on `OAuth2Authorization.authorizedScopes` and the refresh grant provider, verify issued tokens end-to-end, and design additional revocation mechanisms when user/client permissions are withdrawn. That is the core boundary between **renewing credentials** and **granting new privileges**.
