# Handling Concurrent Refresh Requests and Ensuring Consistency

> **Chapter: Refresh Token.** This lesson belongs to the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module: learning how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application. The focus is on **race conditions when multiple requests use the same refresh token**, designing **safe refresh token rotation**, atomicity during state updates, and coordination between the **OAuth2 Client** and **Authorization Server** in multi-instance environments.

## 1. Why Are Refresh Tokens a Concurrency Hotspot?

Short-lived access tokens limit the damage if exposed. When they expire, an OAuth2 Client can send a refresh token to `/oauth2/token` to obtain a new access token without forcing the user to sign in again immediately. However, a browser or backend service typically has **multiple API requests running concurrently**. If all five requests notice the access token is about to expire, all five may try to refresh **using the same refresh token**.

Example scenario:

- **Authorization Server (AS/OP):** `https://login.example.vn`, using Spring Authorization Server.
- **Confidential web client / Backend for Frontend (BFF):** `portal-web` at `https://portal.example.vn`, using Spring Security OAuth2 Client.
- **Resource Server:** `https://api.example.vn`; the Client uses access tokens to call APIs.
- **Initial grant:** Authorization Code + PKCE, client permitted to use `refresh_token`.
- **Current state:** access token `A0` is nearing expiration; current refresh token is `R0`.
- **Two concurrent requests:** `GET /orders` and `GET /profile` need fresh tokens at the same time.

If **rotation** is enabled, a successful refresh using `R0` issues `R1` and forbids continued use of `R0`. The second request using `R0` may be rejected with `invalid_grant`. Never "fix" this error by letting both requests arbitrarily use the old token, as that can break **replay detection**.

### 1.1. Failure Modes to Distinguish

| Symptom | Actual problem | Observable result |
|---|---|---|
| Two threads in **one JVM** use the same `R0` | Client does not coalesce multiple refreshes into one (single-flight) | One succeeds, the other gets `invalid_grant` |
| Two **Client pods** share a session/token store yet refresh independently | A `synchronized` lock only protects one JVM | Cross-instance race, overwriting new tokens with old ones |
| Two **Authorization Server pods** both read `R0` before either saves `R1` | Non-atomic state transition | Risk of both accepting the old token or last-write-wins |
| AS issues `R1` yet response is lost | Client still holds `R0` even though server moved to `R1` | Retries can look like replay; user forced to re-login |
| Client saves `R1` yet another request overwrites with stale snapshot `R0` | Lost update in Client's token store | Subsequent requests use an invalidated refresh token |
| Attacker uses a stolen refresh token | **Genuine replay** | Must be detected per rotation/sender-constraining policy |
| Access token expires with no refresh token | Not a race condition | Client needs a new authorization grant or suitable mechanism |

**Right goal:** at most one effective refresh state transition per refresh token version; every Client instance observes the latest state; failures are handled **without leaking tokens or granting off-policy access**.

## 2. Distinguishing Refresh Token Reuse and Refresh Token Rotation

Spring Authorization Server provides `TokenSettings.Builder.reuseRefreshTokens(boolean)`.

| Policy | On successful refresh | When two requests use `R0` concurrently | Trade-off |
|---|---|---|---|
| `reuseRefreshTokens(true)` | Refresh token `R0` is **reused** in the token response per policy | Multiple requests may be accepted while token remains valid and other conditions hold | Simpler Client coordination yet **does not provide replay detection via rotation** |
| `reuseRefreshTokens(false)` | AS issues a new refresh token `R1`; old token must not continue being used after valid state transition | Second request must be handled as old/invalid token; replay detection and handling depend on implementation | Supports rotation model; requires atomicity, consistent state persistence, and replay strategy |
| **Sender-constrained refresh token** | Client must prove possession of the key/certificate bound to the token | Two client instances can only use it if holding the valid bound credential; still needs version/storage control | Reduces stolen-token usability; requires compatible DPoP/mTLS infrastructure |

**Key standard point:** RFC 9700 §4.14 requires Authorization Servers **MUST** use **refresh token rotation or sender-constraining** to detect replay for **public clients** when issuing refresh tokens. For confidential clients, tokens must be bound to the exact client; additional policies depend on the threat model. Never issue refresh tokens to every client without evaluating risks, scope, and actual need.

**Key Spring point:** In Spring Authorization Server 1.5.x, `TokenSettings.isReuseRefreshTokens()` defaults to **`true`**. Calling `reuseRefreshTokens(false)` sets a policy to issue new refresh tokens upon refresh, yet **is not enough to infer** that the current deployment already has atomic compare-and-swap, a token-family ledger, or whole-family revocation on replay. These properties must be verified against your version, repository, and actual execution flow.

### 2.1. Refresh Token Request/Response Example

Client sends the **refresh token** over HTTPS to the token endpoint:

```http
POST /oauth2/token HTTP/1.1
Host: login.example.vn
Authorization: Basic REDACTED_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=R0_REDACTED&scope=orders.read
```

Sample successful response (illustrative, **not real tokens**):

```json
{
  "access_token": "A1_REDACTED",
  "token_type": "Bearer",
  "expires_in": 300,
  "refresh_token": "R1_REDACTED",
  "scope": "orders.read"
}
```

When rotation is enabled, the Client must save **`A1` and `R1` together as a new state version** before letting other flows start refreshing. In reuse mode, the server may return the same refresh token; the Client must still handle responses accurately. Do not assume every response from every Authorization Server includes `refresh_token`: Client updates must obey the response and OAuth2 Client contract in use, **never writing `null`** and accidentally wiping a still-valid credential.

`scope` sent on refresh must never expand beyond the granted authorization's scope. Refreshing is not a way to request new permissions or redo consent. Access tokens/ID Tokens issued afterward still undergo Resource Server/Relying Party validation; a refresh token is not an API-calling credential.

## 3. Timeline of a Race Condition

### 3.1. Two Client Requests Using One Old Token

```mermaid
sequenceDiagram
    autonumber
    participant R1 as Request 1
    participant R2 as Request 2
    participant Store as Client token store
    participant AS as Authorization Server

    R1->>Store: Read expired A0 + R0
    R2->>Store: Read expired A0 + R0
    R1->>AS: POST refresh_token=R0
    R2->>AS: POST refresh_token=R0
    AS-->>R1: Success: A1, R1 (rotated)
    AS-->>R2: invalid_grant since R0 already used
    R1->>Store: Write A1, R1
    Note over Store: Risk: R2's failure handler<br/>deletes or overwrites newly saved state
    R2->>Store: Run error handling on A0,R0 snapshot
```

If the failure on Request 2 triggers a handler that deletes an `OAuth2AuthorizedClient` from storage by shared key, it can delete **the very state Request 1 just saved**. Therefore, **never blindly delete by key on failure**; if customizing failure handlers, verify the current record/version in storage still matches the record the failing request used.

### 3.2. Two AS Pods Accepting the Same Refresh Token

```mermaid
sequenceDiagram
    autonumber
    participant C1 as Client request A
    participant C2 as Client request B
    participant AS1 as AS pod 1
    participant AS2 as AS pod 2
    participant DB as Authorization store

    C1->>AS1: refresh R0
    C2->>AS2: refresh R0
    AS1->>DB: Load authorization with current=R0
    AS2->>DB: Load authorization with current=R0
    AS1->>AS1: Create A1,R1 from R0 snapshot
    AS2->>AS2: Create A2,R2 from R0 snapshot
    AS1->>DB: Write R1
    AS2->>DB: Write R2 if no concurrency guard
    Note over DB: Last-write-wins or inconsistent state
```

In a **correct** rotation model, one transaction must win and **at most one successor state** is committed from `R0`. If two transactions both issue tokens and return success, consistency has been violated. If one transaction gets an old-token-reused error, the replay policy must define **safe handling** rather than trying to guess which request was an attacker.

## 4. Configuring Spring Authorization Server: Enabling Rotation in the Right Place

A confidential `RegisteredClient` using Authorization Code and Refresh Token (Spring Authorization Server 1.x):

```java
import java.time.Duration;

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

static RegisteredClient portalClient(String encodedClientSecret) {
    return RegisteredClient.withId("registration-portal-web")
            .clientId("portal-web")
            .clientName("Portal Web")
            .clientSecret(encodedClientSecret)
            .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                    AuthorizationGrantType.AUTHORIZATION_CODE)
            .authorizationGrantType(
                    AuthorizationGrantType.REFRESH_TOKEN)
            .redirectUri(
                    "https://portal.example.vn/login/oauth2/code/portal")
            .scope("orders.read")
            .clientSettings(ClientSettings.builder()
                    .requireProofKey(true)
                    .requireAuthorizationConsent(true)
                    .build())
            .tokenSettings(TokenSettings.builder()
                    .accessTokenTimeToLive(Duration.ofMinutes(5))
                    .refreshTokenTimeToLive(Duration.ofHours(8))
                    .reuseRefreshTokens(false) // Request rotation on refresh
                    .build())
            .build();
}
```

**Example scope:** Place the method inside a class and persist the result with `RegisteredClientRepository`. `encodedClientSecret` must be a string hashed with Spring Security's `PasswordEncoder`; the plaintext secret stays in the Client's secret manager. A complete Authorization Server also needs `SecurityFilterChain`, `AuthorizationServerSettings`, `OAuth2AuthorizationService`, user authentication, consent, and JWK signing (if issuing JWTs).

Explanation:

- `authorizationGrantType(REFRESH_TOKEN)` allows the client to use the Refresh Token grant; it does **not** mean every request is issued a refresh token.
- `reuseRefreshTokens(false)` configures issuing a new token in the refresh response when issuance conditions hold; this policy **does not replace** an atomic store or token-family replay detection.
- `refreshTokenTimeToLive(...)` is a per-policy TTL, **distinct** from idle timeouts, absolute family lifetimes, or whole-family revocation. If those bounds are needed, design them explicitly.
- The 5-minute / 8-hour TTL values are illustrative only and depend on client type, resource sensitivity, and session requirements.
- `requireProofKey(true)` applies to the original Authorization Code; PKCE does not replace refresh token checks at the token endpoint.

### 4.1. Components Actually Involved in Refresh

| Spring component | Responsibility |
|---|---|
| `RegisteredClientRepository` | Resolves client, allowed grant types, authentication methods, and `TokenSettings` |
| `OAuth2RefreshTokenAuthenticationProvider` | Processes the Refresh Token grant in the AS per library mechanics |
| `OAuth2AuthorizationService` | Retrieves/saves authorizations along with access/refresh token state |
| `JdbcOAuth2AuthorizationService` or custom storage | Persistence; **do not assume atomic rotation** without verifying the update contract |
| `OAuth2TokenGenerator` / `OAuth2RefreshTokenGenerator` | Generates tokens per authorization/token settings policy |
| `OAuth2AuthorizedClientRepository` or `OAuth2AuthorizedClientService` | **Client side**: persists authorized client/access/refresh tokens after exchange |
| `OAuth2AuthorizedClientManager` and `RefreshTokenOAuth2AuthorizedClientProvider` | **Client side**: performs re-authorization/refresh when eligible |

**Do not confuse:** `OAuth2AuthorizationService` is the **AS-side** store, whereas `OAuth2AuthorizedClientService` is the **OAuth2 Client-side** store. They live in different applications/trust boundaries, so concurrency must be designed on **both sides**.

Spring Security enables `OAuth2AuthorizedClientManager` to automatically renew access tokens when a refresh token exists and renewal is needed, yet **do not treat every `authorize(...)` call as a distributed single-flight lock**. Multiple callers can still read the same stale snapshot before new results are saved.

## 5. Client Side: Coalescing Multiple Requests into One Refresh (Single-Flight)

**Single-flight** means multiple requests needing a fresh token for the **same authorized-client/session** wait on **one refresh operation** rather than concurrently spending the old refresh token. The lock key must be scoped accurately:

```text
lock key = tenant/issuer + client registration ID + principal/session identity
```

Never use one global lock for all users/clients: it turns User A's refresh into User B's bottleneck. Equally, never lock per request ID: two requests in the same session get two different locks, failing to prevent races.

### 5.1. Double-Check Pattern Within One JVM

The Java code below is an **illustrative algorithm**, independent of specific Spring Security APIs. `TokenStore`, `TokenEndpoint`, and `TokenPair` are application-defined interfaces/records showing read/write boundaries; implement them with real OAuth2 Client APIs and storage.

```java
import java.time.Duration;
import java.time.Instant;

record TokenPair(
        String accessToken,
        Instant accessTokenExpiresAt,
        String refreshToken,
        long version) {}

interface TokenStore {
    TokenPair load(String key);

    // Replace state only if record still matches the version just read.
    boolean replaceIfVersion(String key, long oldVersion, TokenPair next);
}

interface TokenEndpoint {
    // Send POST /oauth2/token over TLS; never log credentials.
    TokenPair refresh(String oldRefreshToken, long expectedNextVersion);
}

final class SingleFlightTokenService {
    private final Object monitor = new Object();
    private final String key;
    private final TokenStore store;
    private final TokenEndpoint endpoint;

    SingleFlightTokenService(
            String key, TokenStore store, TokenEndpoint endpoint) {
        this.key = key;
        this.store = store;
        this.endpoint = endpoint;
    }

    TokenPair getUsableToken() {
        TokenPair snapshot = store.load(key);
        if (usable(snapshot)) {
            return snapshot; // Fast path: no lock needed
        }

        synchronized (monitor) {
            TokenPair latest = store.load(key); // Double-check under lock
            if (usable(latest)) {
                return latest;
            }
            if (latest == null || latest.refreshToken() == null) {
                throw new IllegalStateException("Reauthorization required");
            }

            TokenPair rotated = endpoint.refresh(
                    latest.refreshToken(), latest.version() + 1);

            if (!store.replaceIfVersion(key, latest.version(), rotated)) {
                // Concurrent update occurred: read new record, never reuse old R.
                TokenPair afterConflict = store.load(key);
                if (usable(afterConflict)) {
                    return afterConflict;
                }
                throw new IllegalStateException(
                        "Token state changed during refresh");
            }
            return rotated;
        }
    }

    private boolean usable(TokenPair pair) {
        return pair != null
                && pair.accessTokenExpiresAt() != null
                && pair.accessTokenExpiresAt().isAfter(
                        Instant.now().plus(Duration.ofSeconds(30)));
    }
}
```

**Be sure to read the example's limitations:**

1. One `SingleFlightTokenService` instance has one `monitor`, so it only serializes threads **sharing that exact instance**. Across multiple beans, pods, or JVMs, `synchronized` **does not** protect across instances.
2. `replaceIfVersion` provides **optimistic concurrency** at Client storage, yet cannot undo **two pods having already sent the same `R0` to the AS**. Preventing duplicate refreshes before hitting the token endpoint requires cross-instance coordination.
3. If the HTTP call succeeded yet saving to storage failed, the token already rotated at the AS. **Never automatically call the token endpoint again with the old refresh token** inside catch/finally. Reconcile/recover from a trusted state source or initiate a new authorization.
4. Spring Security's real `OAuth2AuthorizedClientManager` API has its own token/authorized-client model; this example only explains double-check + CAS and is **not a built-in framework class**.
5. `refreshToken` should live only in a backend/secret-aware store; never write this string into exceptions, logs, or metric labels.

### 5.2. Spring Security OAuth2 Client and Persisting the New Token

On the Spring Security Client side, `OAuth2AuthorizedClient` holds `OAuth2AccessToken` and optionally `OAuth2RefreshToken`. `OAuth2AuthorizedClientManager.authorize(...)` coordinates `OAuth2AuthorizedClientProvider` (including the refresh grant) with the persistence repository/service.

Normally, the manager saves the new authorized client after a successful refresh and **can remove the old authorized client upon receiving `invalid_grant`** via its default failure handler. Under a race, a second request receiving `invalid_grant` might operate on a stale snapshot. If customizing failure handlers, apply **compare-and-delete by version** or verify the active token in storage before deleting; never blindly delete a record already updated by another thread.

Spring Security example (illustrating only the manager bean; **does not add a single-flight lock automatically**):

```java
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
                    registrations, authorizedClients);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
```

This snippet belongs to a **servlet web Client application**. When running in a background service without an `HttpServletRequest`, consider `AuthorizedClientServiceOAuth2AuthorizedClientManager` with a corresponding `OAuth2AuthorizedClientService`. Choose keys by `registrationId` and `principalName` consistently across requests; never share a fixed principal across different users.

**Note:** Never override success/failure handlers arbitrarily and forget to persist the authorized client. Any change must be tested to verify the new `refresh_token` actually persists and subsequent requests use the updated version.

## 6. Multiple Client Pods: Distributed Locks, Fencing, and Atomic Updates

Suppose two pods of `portal-web` serve the same user simultaneously; both share `OAuth2AuthorizedClientService` in a DB. Each pod has its own `synchronized` lock, so both can still spend `R0`. A stronger strategy combines **cross-instance single-flight** and **optimistic concurrency**.

### 6.1. Cross-Instance Coordination Workflow

```mermaid
flowchart TD
    Start["API request needs access token"] --> Load["Read authorized client from shared store"]
    Load --> Valid{"Is access token<br/>still usable?"}
    Valid -->|Yes| Return["Use current token"]
    Valid -->|No| Lock["Acquire distributed lock/lease<br/>for key issuer+client+principal"]
    Lock --> Reload["Reload record + version under lock"]
    Reload --> Valid2{"Did another pod<br/>already refresh?"}
    Valid2 -->|Yes| Unlock["Release lock, use new record"]
    Valid2 -->|No| HTTP["POST refresh with current refresh token"]
    HTTP --> Persist["CAS save token response + version<br/>before releasing lock"]
    Persist --> OK{"Commit succeeded?"}
    OK -->|Yes| Unlock
    OK -->|No| Recover["Do not retry old R<br/>Re-read/reconcile/fail closed"]
    Recover --> Unlock
    Unlock --> Return
```

Essential steps:

1. **Load token**: if the access token remains valid after an appropriate **clock skew** margin, do not refresh.
2. **Acquire distributed lock by authorized-client key**, with timeout, lease, and owner tracking.
3. **Re-read under the lock**, because another pod may have finished refreshing right before the lock was granted.
4. If still needed, send **one** refresh request. Save the entire new access/refresh token pair **atomically** with a new version; prevent half-written failures.
5. Release the lock only after commit. Waiting callers read the new state and never reuse `R0`.
6. If the lock expires during a slow refresh, use **fencing tokens/versions** and storage CAS so a stale lock holder cannot overwrite newer results.

### 6.2. Why Isn't a Simple Redis `SET NX PX` Enough?

A Redis distributed lock can fit some architectures, yet **lease expiry** creates hazards: Pod A holds the lock while the token endpoint is slow; the lease expires; Pod B acquires a new lock and also refreshes. If A continues writing after B updated, a lost update occurs. Therefore:

- Locks must include an owner token, sensible TTL, and ownership-checked release—never blindly `DEL` a lock now owned by another pod.
- You need a **monotonically increasing fencing token** or storage version/CAS to block stale lock holders from writing data.
- Never assume distributed locks shield every token endpoint call during network faults, timeouts, or long GC pauses. The Authorization Server **must still reject duplicate consumption**.
- Consider DB row locks if the Client token store lives in the same RDBMS; however, avoid holding DB transactions/row locks across slow external HTTP calls—design safe leases/serialization and load-test thoroughly.

A practical alternative is funneling refreshes through **a token broker** or service owning single-writer token state, though that central component still requires high availability, fencing, and durable persistence.

## 7. Authorization Server Side: Checking and Replacing Refresh Tokens **Atomically**

Clients try to avoid duplicate sends, yet **the AS cannot trust Clients to always be right**: attackers, flaky networks, retries, or buggy Client libraries can still send the same `R0` multiple times. The Authorization Server must guarantee:

- A refresh token is never consumed more times than policy allows.
- With rotation, **one old version has at most one valid successor**.
- Never let two AS pods both report success with two different successors for the same `R0`.
- Authorization/token data and history required for replay detection are committed consistently before returning responses.
- If genuine replay is detected, execute the appropriate token-family/sender-binding revocation policy.

### 7.1. Designing Token Family/Lineage (Recommended Model)

A **token family** is the chain of refresh tokens derived from the same authorization grant, e.g.:

```text
Authorization grant G42
  refresh family F42:
     R0 --rotate--> R1 --rotate--> R2
     R0: consumed
     R1: consumed
     R2: current
```

A **custom** storage model might use:

| Field | Meaning |
|---|---|
| `family_id` | Unpredictable family identifier / internal key |
| `authorization_id` | Reference to owning grant/authorization |
| `registered_client_id` and `principal_id` | Client/user binding |
| `current_token_digest` | Secure digest of the currently valid token |
| `generation` and `version` | Rotation generation and CAS version |
| `status`, `revoked_at` | Active/revoked/expired and timestamp |
| `absolute_expires_at`, `idle_expires_at` | Family bounds if required by policy |
| `last_rotated_at`, `last_used_at` | Minimal audit trail, anomaly detection |

Add a **token history/ledger** storing `digest/token identifier` of consumed tokens alongside `family_id`, generation, and consumed timestamp (retained long enough for the replay detection window). Once `R0` is replaced, you still need to know which family `R0` belonged to in order to handle reuse. Keeping only the **current refresh token** and wiping every trace of `R0` cannot justify claiming RFC 9700-style replay detection.

Never put raw refresh tokens in logs, metrics, or SQL audit tables. Because refresh tokens must have high entropy and be unpredictable, you can store a **keyed digest/HMAC** for lookup and comparison per architecture; protect the digest key and restrict read access. Never use hashing of a weak token to "compensate" for low-entropy token generation.

### 7.2. Atomic Compare-and-Swap (CAS)

Illustrative SQL for a custom store (not Spring Authorization Server's built-in schema):

```sql
-- PSEUDOSQL: execute inside a transaction with appropriate isolation.
-- :old_digest must already be identified and bound to the right family/client.
UPDATE refresh_family
SET current_token_digest = :new_digest,
    generation = generation + 1,
    version = version + 1,
    last_rotated_at = CURRENT_TIMESTAMP
WHERE family_id = :family_id
  AND current_token_digest = :old_digest
  AND version = :expected_version
  AND revoked_at IS NULL
  AND absolute_expires_at > CURRENT_TIMESTAMP;
```

Suppose two transactions both attempt to transition `R0` → successor. Only **one** transaction may update under `current_token_digest=hash(R0)` and `version=v`. If update count is `0`, the losing transaction **must not return a successful response** with any refresh token it generated. Check whether the token expired, was revoked, belongs to another client, or was already consumed; if reuse is detected, execute the replay policy.

In a real implementation:

1. Look up the record by token hash/identifier and client binding; **never trust a request-asserted `client_id` before authentication**.
2. Open a transaction; lock or CAS the family record and record the old token in the ledger (or inspect an existing ledger entry).
3. Generate new tokens with a cryptographic random generator and construct the successor authorization/state.
4. Atomically commit **family/version + ledger + token metadata/authorization** within the same verifiable transaction; unique constraints prevent two successors for the same generation.
5. **After commit**, return the token response. If the transaction rolls back, never return new tokens.
6. When the loser detects conflict, never "retry CAS" using the same old token to try winning. Evaluate replay per policy and return a safe error.

**Very important limitation:** the SQL above illustrates the CAS concept only. If refresh tokens/authorizations also live in `OAuth2AuthorizationService` in a separate DB or transaction, updating the family table **alone** is not atomic enough; design consistent adapters and transaction boundaries. Never apply this SQL directly to the built-in `oauth2_authorization` schema and assume concurrency is safe.

### 7.3. Do Not Assume `JdbcOAuth2AuthorizationService` Already Implements Token-Family CAS

`JdbcOAuth2AuthorizationService` persists `OAuth2Authorization` durably via JDBC, yet **saving data to a DB** does not prove that **read → validate → rotate → save** is serialized under contention or retains full refresh token lineage. Before production:

- Verify behavior, schema, and concurrency contracts against the exact **running library version**.
- Test two concurrent requests hitting **two AS pods** with the same old refresh token.
- Inspect the DB post-test: exactly one successor accepted, versions never rolled back, ledger sufficient to recognize old tokens if promising replay detection.
- If missing, implement suitable mechanisms via custom service/provider/transactional layers or upgrade when upstream provides verified guarantees; **never just slap `@Transactional` onto a controller wrapping the token endpoint** and assume atomicity.

### 7.4. Transaction Isolation and Locking

| Technique | Solves | Does not solve automatically |
|---|---|---|
| `SELECT ... FOR UPDATE` on family row | Serializes transactions modifying the same DB row | Client sending duplicate requests; overly long transactions; ledger/replay policy |
| Optimistic locking via `version` | Blocks lost updates when all writers check version | Dropped HTTP responses; tokens emitted outside transactions; conflict handling |
| Unique constraint `(family_id, consumed_generation)` | Prevents writing two successors for the same generation | Client auth binding, scope limits, and UX |
| DB transaction | All-or-nothing across tables **within the same transaction** | Distributed transactions with KMS, external services, caches, network token responses |
| Distributed lock before request | Reduces cross-pod work/races | Lease expiry, fencing, and actors bypassing the lock |
| Serializable isolation | Prevents certain anomalies | Replay/rotation design, retry failures, or dropped responses; serialization failures still require handling |

## 8. Replay Detection: Benign Concurrency and Attacks Look Alike

RFC 9700 §4.14 describes rotation as follows: when a replaced refresh token reappears, the server knows there is a sign of **replay** yet **cannot determine** from the token alone whether the request came from a legitimate user or an attacker. Thus a strict detection model may **revoke the still-valid refresh token of the entire family**, forcing the client to obtain a new authorization grant.

### 8.1. Three Distinct Scenarios

| Scenario | Server state | Safe approach |
|---|---|---|
| Two legitimate requests from the same client use `R0` | One request rotates to `R1`; the next uses already-consumed `R0` | Client single-flight to **prevent** races; AS handles old token per replay policy |
| Attacker holds `R0`, user already moved to `R1` | Attacker reuses `R0` | Detect consumed token, revoke family, alert/re-authorize |
| Response `R1` dropped, client retries `R0` | AS committed `R1`; client does not know successor | **Do not retry blindly**; need designed recovery/re-authorization rather than waiving replay |

**Safety cannot be decided reliably from a 50 ms gap or identical IP.** A "grace window" letting old tokens work after rotation can mask genuine replay. If choosing a false-positive reduction mechanism, establish a clear threat model, strict instance/sender binding, tight limits, and evaluate whether it still satisfies RFC 9700's **replay detection** requirement. Never present grace periods as a default security feature.

### 8.2. Rotation and Sender-Constrained Tokens

For a public client, if rotation is not used, RFC 9700 requires an appropriate sender-constrained mechanism such as DPoP/mTLS. Sender-constrained tokens reduce the utility of a stolen token alone, yet:

- Binding must be verified on **every refresh request**.
- Lost/compromised private keys still need dedicated handling policies.
- Client instances holding different keys may be unable to share tokens bound to the original instance's key.
- Concurrent requests can still cause lost updates if the Client token store is inconsistent; sender-constraining **is not distributed single-flight**.

## 9. Dropped Responses, Timeouts, Retries, and Recovery

### 9.1. Why HTTP Timeout Does Not Mean the Request Went Unprocessed

Suppose Client sends `R0`, AS commits `R1`, yet the response drops in transit. Client only observes a **timeout**; it does not know whether the server committed. Resending `R0` is unsafe under strict rotation because:

- If the AS committed, `R0` is already consumed and retrying can trigger family alerts/revocation.
- If the AS did not commit, `R0` might still be valid, yet the Client cannot tell the two cases apart from a timeout.
- If the client creates a second refresh request after a dropped response, risk of **two successors** on a non-atomic AS increases.

**Client policy should separate error classes:**

| Error class | Meaning | Safe action |
|---|---|---|
| `invalid_grant` from AS | Wrong/expired/consumed/revoked/invalid refresh token | Re-read shared token store; if a newer version exists use it, otherwise require fresh authorization |
| `invalid_client` | Invalid client authentication | Halt automatic refreshes, fix configuration/credentials, and alert operations |
| HTTP 429 / 503 **before request was definitely processed/committed** | Server overloaded/temporarily unavailable | May retry with backoff per policy **only if state is confirmed unchanged** |
| Timeout/connection reset **after sending request** | Outcome is **unknown** | Never retry the same `R0` blindly; check shared state or follow recovery/reauth workflow |
| Client token store CAS write fails | Another pod may have updated; AS may have rotated | Re-read version; never overwrite with stale state or resend old refresh token |
| AS returns malformed token response | Missing required fields, TLS/issuer mismatch, decode error | Fail closed, never write partial state; evaluate recovery if AS rotated |

"Retry only when certain the request was unprocessed" is hard to guarantee over HTTP in practice; clients should generally **fail closed and re-authorize** rather than inventing retries that trigger replay. If the product needs seamless UX when responses drop, design an **explicitly authenticated idempotency/recovery protocol** between client and AS, binding client, token generation, request identity, TTL, and response consistency; this is **not** a built-in feature of the OAuth2 Refresh Token grant.

### 9.2. Tokens Must Be Saved as Versioned Pairs

Client state is not just a refresh token string, but a versioned record:

```text
AuthorizedClientState {
  key: (issuer, registrationId, principalId, tenantId),
  accessToken: A1,
  accessTokenExpiresAt: ...,
  refreshToken: R1,
  refreshTokenExpiresAt: ...,
  version: 18,
  updatedAt: ...
}
```

When transitioning `R0` → `R1`, commit **new access token, new refresh token, expiry, and version** in one consistent storage operation. With Redis, use an atomic Lua/transaction with CAS or versioned structure; with RDBMS, update with `WHERE version = :old_version`. Never update fields one by one across separate commands and let concurrent readers observe half-updated state.

Clients should **re-read** the record upon conflict rather than reverting to the old token. An in-flight API request already holding an unexpired access token A0 may proceed per policy; new requests needing A1 must use the latest state. Expired tokens or revoked families ⇒ require appropriate login/authorization.

## 10. Access Rights, Token Scopes, and Logout During Concurrent Refresh

Concurrency does not relax any OAuth2 security invariant:

1. AS must authenticate confidential clients and ensure refresh tokens belong to the exact client, grant, and subject. Public clients must follow RFC 9700 refresh protections.
2. Scopes on new access tokens **never exceed** granted permissions and valid request/consent bounds. Never let attackers escalate scopes via refresh.
3. Revoked tokens, deleted authorizations, or changed user/consent/policies must be enforced per policy. A refresh running concurrently with logout/revocation needs a clear **commit order** and behavior: never issue new tokens once revocation takes effect.
4. If the AS issues JWT access tokens, revoking a refresh token **does not automatically revoke unexpired issued JWTs**. Resource Servers may need short TTLs, introspection/status checks, or revocation lists depending on requirements.
5. In OIDC, the refresh grant **does not mean the user newly logged in**. Do not treat a new access token's `iat` as a new `auth_time`; if an ID Token is issued on refresh, check OIDC rules and corresponding claims.
6. Never mix token states of two users, two tenants, or two client registrations just because they share a browser, pod, or Redis key.

### 10.1. Refresh Concurrent with Revocation/Logout

```mermaid
sequenceDiagram
    autonumber
    participant User as User
    participant Client as Client BFF
    participant AS as Authorization Server
    participant DB as Shared token/authorization store

    Client->>AS: Refresh R0
    User->>AS: Revoke session/authorization grant
    par Two transactions contending on state
        AS->>DB: Validate and transition R0 -> R1 (transaction)
    and
        AS->>DB: Mark grant/family revoked (transaction)
    end
    DB-->>AS: Commit order resolved
    Note over AS,DB: Must not let refresh from stale snapshot<br/>revive family after revocation
    AS-->>Client: New tokens if refresh legitimately won, or error if revoked
```

If revocation commits **before** the refresh updates state, the refresh must be rejected. If refresh commits **before** revocation, the subsequent revocation must invalidate the family/successor appropriately. Never allow an update using a stale snapshot to clear `revoked_at` or flip a family back to `active` after revocation. Revocation and refresh flows must share the same atomic state/transaction mechanism.

## 11. Testing Race Conditions in a Controlled Way

You cannot test concurrency reliably by calling refresh twice sequentially and concluding the system is safe. You must **synchronize start times**, let two requests read the same snapshot, measure outcomes, and inspect the real DB after commit. Use dummy tokens/credentials in staging or integration tests; never print verbatim refresh tokens in logs/test reports.

### 11.1. Test Matrix

| Test case | Setup | Expectation |
|---|---|---|
| Single refresh | Valid `R0`, expired access token | Issues `A1` and, if rotation enabled, `R1`; version increments properly |
| Two requests in same JVM | 10 callers for same expired authorized client | Client single-flight makes **one** token endpoint call (within that service instance) |
| Two Client pods | Pods A/B sharing expired record | Only one refresh sent per distributed coordination strategy; other pod uses persisted result |
| Two AS pods receiving same `R0` | Bypass Client single-flight, send concurrently | **Never** two successful successors; DB holds only one valid final state and loser handled per policy |
| Lost update at Client store | Attempt writing stale-version record after R1 committed | CAS rejects; never reverts to R0 |
| Old token replay | Use `R0` after R1 committed | Rejected; if family policy exists, revoke successor and record security event |
| Timeout after commit | AS commits R1 yet response blocked | Client does not blindly retry R0; clean reauthorize/recovery path |
| Crash before commit | Stop AS before transaction commits | No success returned; DB has no half-written state |
| Crash after commit before response | AS commits then loses connection | Client recognizes unknown outcome and handles safely |
| Lease expiry | Pod A refreshes slowly; Pod B acquires lock | Fencing/CAS blocks stale Pod A overwrite; AS rejects duplicate |
| Refresh parallel with revoke | One refresh transaction, one revoke transaction | Never "resurrects" revoked family post-commit; consistent ordering |
| Expired refresh token | Token past TTL/idle/absolute lifetime | `invalid_grant`/appropriate error; no token issued |
| Excessive scope | Refresh request adds ungranted scope | Rejected/no permissions granted beyond authorization |
| Wrong client | Token R0 belongs to Client A yet B tries refreshing | Rejected without disclosing Family A details |
| Wrong tenant/principal | Same client registration, different principal | Never accidentally share token state/locks |
| Load test | Hundreds of users/sessions refreshing concurrently | No system-wide lockups; latency, DB contention, and error rates within SLO |
| Multi-node persistence | AS Pod A issues R1; AS Pod B validates R1 | R1 accepted per policy; consistent state |
| Reuse mode | `reuseRefreshTokens(true)`, two valid requests | Verify server behavior and capacity limits; **do not** claim rotation-based replay detection |
| Public client | Client with refresh token and public policy | Verify rotation or sender-constraining per RFC 9700 |
| Client failure handler | Request A saved R1; Request B gets `invalid_grant` on R0 | Handler B does not blindly delete new record R1 |

### 11.2. Using a Barrier to Create Real Contention

JUnit 5/Java example illustrating concurrent orchestration **around an existing refresh-calling helper in a test**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

@Test
void onlyOneRefreshMayCommitForSameOldToken() throws Exception {
    int callers = 2;
    CountDownLatch ready = new CountDownLatch(callers);
    CountDownLatch start = new CountDownLatch(1);

    ExecutorService pool = Executors.newFixedThreadPool(callers);
    try {
        List<Future<RefreshResult>> futures = new ArrayList<>();
        for (int i = 0; i < callers; i++) {
            futures.add(pool.submit(() -> {
                ready.countDown();
                if (!start.await(5, TimeUnit.SECONDS)) {
                    throw new AssertionError("Barrier timeout");
                }
                return callTokenEndpointWithSameR0();
            }));
        }
        assertTrue(ready.await(5, TimeUnit.SECONDS));
        start.countDown();

        List<RefreshResult> results = new ArrayList<>();
        for (Future<RefreshResult> future : futures) {
            results.add(future.get(15, TimeUnit.SECONDS));
        }

        assertEquals(1, results.stream()
                .filter(RefreshResult::success).count());
        // Verify real DB: at most one successor committed, valid history.
        assertPersistedFamilyHasAtMostOneSuccessorForR0();
    } finally {
        pool.shutdownNow();
    }
}
```

**This is a test skeleton**; `callTokenEndpointWithSameR0()`, `assertPersistedFamilyHasAtMostOneSuccessorForR0()`, and `RefreshResult` must be defined by the project. Asserting `success==1` fits systems designed to accept one valid refresh; if **immediate family revocation on reuse detection** is active, the successor may be revoked afterward and the test must also check `revoked` state.

A caller-side barrier only makes requests arrive close together. To prove AS atomicity, use a test hook/barrier where **both requests have read the same version** before CAS, or drive DB transactions via a test harness; avoid shipping test hooks to production. Repeat tests across **two real instances** and against production-equivalent database/driver/isolation levels.

### 11.3. Which Invariants to Assert?

- **No double-success:** at most one `R0 → Rnext` transition commits successfully.
- **No lost update:** Client store cannot revert to R0 after writing R1; AS DB never has two current tokens for the same family.
- **No replay bypass:** consumed R0 can never issue new off-policy tokens.
- **No token leakage:** tests/logs/traces contain zero raw tokens, client secrets, or Authorization headers.
- **No accidental deletion:** a failed refresh on a stale snapshot never deletes the Client's newer state.
- **Revocation wins:** a committed revocation can never be "resurrected" by a refresh.
- **Multi-tenant isolation:** distinct clients/users never block each other unreasonably or share tokens.
- **Observability:** metrics exist for conflicts/replays/failures without turning token values into labels.

## 12. Operations, Monitoring, and Troubleshooting

### 12.1. Useful Metrics and Logs

| Metric/event group | Purpose |
|---|---|
| `refresh_attempt_total{outcome}` | Success/`invalid_grant`/`invalid_client`/timeout ratios |
| `refresh_rotation_conflict_total` | Detects contention while swapping tokens; spikes may mean client lacks single-flight |
| `refresh_family_replay_detected_total` | Monitors consumed old tokens resubmitted per policy |
| `refresh_family_revoked_total{reason}` | Assesses security impact and forced re-login UX |
| `client_singleflight_wait_seconds` | Time requests wait on a refresh, distinguishing intra-JVM vs. cross-pod |
| `token_store_cas_conflict_total` | Uncovers potential lost updates at Client storage |
| `refresh_token_endpoint_latency` | Detects latency causing lease expirations/timeouts |
| `reauthorization_required_total{reason}` | Measures how often users are forced to re-login |

Use **low-cardinality** labels like outcome, environment, and client type; never use raw `refresh_token`, `access_token`, user ID, session ID, or email as labels. For audits needing targeted investigation, use **correlation IDs/hashed identifiers** with restricted access and bounded retention. Avoid logging token endpoint request/response bodies.

### 12.2. Runbook When `invalid_grant` Spikes

1. Check whether the incident began alongside enabling `reuseRefreshTokens(false)`, scaling Client pods, changing storage, or upgrading Spring Security.
2. Use metrics to separate: **duplicate Client refreshes**, **expired/revoked tokens**, **clock skew**, or **DB conflicts** at the Authorization Server.
3. Confirm the Client persisted the new `refresh_token`, used the right user/client/tenant key, and failure handlers did not delete another request's fresh record.
4. Inspect locks/leases/fencing across Client pods; never conclude the cluster is safe because one pod looks healthy.
5. Inspect persistence/transaction isolation and the audit ledger at the AS. Look for duplicate successors, missing consumed states, or overwritten revocations.
6. If **token theft** is suspected, follow security incident response, revoke families/authorizations per policy, and force fresh grants; never "hotfix" by relaxing acceptance of old refresh tokens.
7. Load-test and race-test in staging, verifying improvement post-fix. Never turn on raw-token debug logging in production.

### 12.3. Common Pitfalls

| Symptom | Possible cause | Remediation |
|---|---|---|
| Users forced to re-login when opening multiple tabs | Multiple refreshes with same R0; loser triggers revoke/failure handler | Per-session single-flight, re-read token before refresh, CAS failure handler |
| Alternating new and old tokens after refreshes | Client pod overwrote with stale authorized client snapshot | Versioned storage and atomic compare-and-swap |
| AS returns two new refresh tokens from one R0 | Read/modify/save not serialized in AS store | Atomic consumption/transaction + constraints; multi-pod tests |
| Redis lock still exhibits races | Lease expired, missing fencing, wrong-owner release | Fencing tokens, CAS storage, control lease and latency |
| `invalid_grant` rises after network timeouts | Client retries R0 while AS already committed R1 | Never retry blindly; re-read/recover or re-authorize |
| `invalid_grant` deletes still-valid record | Default/custom failure handler deletes key without version check | Compare-and-delete or version-aware custom handling |
| Two users share a token | Overly broad storage key (`client_id` only) | Include principal/tenant/issuer/registration ID |
| AS data consistent on one pod, fails when scaled | In-memory store or stale local cache | Shared DB + transactions, cache invalidation, concurrency tests |
| Refresh still works after logout | Refresh/revoke race or revocation skips family | Shared revocation state and CAS transactions |
| Tokens leaked in APM/logs | Logging HTTP bodies/headers or response JSON | Strip raw token logs, secret scanning, rotate exposed secrets |
| Enabling reuse to "make errors go away" | Masks Client races and loses rotation replay detection | Fix concurrency; evaluate public client protection per RFC 9700 |
| Continuous premature refreshes | Excessive skew or broken expiry parsing; many callers hit manager concurrently | Choose sensible skew and single-flight; measure token endpoint load |

## 13. Production Implementation Checklist

- [ ] Decided **whether each client type should receive refresh tokens**; never use the Refresh Token grant for `client_credentials` inappropriately.
- [ ] Distinguished reuse vs. rotation; for **public clients**, satisfy RFC 9700 with rotation or sender-constraining if issuing refresh tokens.
- [ ] `RegisteredClient` has `AuthorizationGrantType.REFRESH_TOKEN` and appropriate `TokenSettings` (TTLs, `reuseRefreshTokens(false)` if rotation is desired).
- [ ] Client implements **single-flight by authorized-client key**, double-checks state, and uses versioned atomic storage.
- [ ] Across multiple Client pods, cross-instance coordination or a properly designed token broker is in place; `synchronized` is not treated as a distributed lock.
- [ ] Locks/leases have owners, timeouts, and fencing/CAS; stale holders cannot overwrite successors.
- [ ] AS enforces **atomic consumption**/commit of refresh tokens, never permitting two successors for one generation.
- [ ] If claiming **replay detection via rotation**, lineage/consumed token state and family-revocation policies on reuse are implemented.
- [ ] Client never automatically retries old refresh tokens on response timeouts or unknown AS states.
- [ ] Token responses persist as atomic pairs (access/refresh + expiry + version) with no partial writes.
- [ ] Failure handlers never delete records already refreshed successfully by another caller.
- [ ] Refresh grant remains bounded by client binding, scopes, subject, consent, and revocation; new tokens never escalate permissions.
- [ ] Storage/authorization services are shared across AS pods with suitable isolation/transactions/constraints.
- [ ] Concurrency tests cover single-JVM, multi-Client-pod, multi-AS-pod, dropped responses, stale writes, logout/revoke, and replay.
- [ ] Metrics, alerts, audits, and runbooks exist without logging raw tokens/credentials; private keys/client secrets are protected via secret managers.
- [ ] Concurrency guarantees are verified on the **exact deployed Spring Security/Spring Authorization Server and DB driver versions**, not just by API names.

**Self-check questions**

1. Why does `reuseRefreshTokens(false)` not automatically guarantee only one concurrent request can replace `R0` with a new token?
2. Which case does `synchronized` in an OAuth2 Client solve, and why does it fail across two pods?
3. One request receives `invalid_grant` after another request already saved R1. Why can deleting the authorized client by key without checking version cause session loss?
4. When the AS committed R1 yet the HTTP response dropped, why is retrying R0 not always safe?
5. How does a token family/consumed ledger improve replay detection compared to storing only the active refresh token?
6. How does AS-side CAS differ from Client-storage CAS? Why are both needed?
7. Why does a TTL-based Redis lock still need fencing/versioning in storage?
8. Does revoking consent/refresh tokens automatically invalidate all unexpired JWT access tokens at Resource Servers?
9. For public clients issued refresh tokens, which categories of replay protection does RFC 9700 require?
10. How would you use a barrier and DB inspection to prove two AS pods cannot concurrently issue two valid successors?

## References

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Refresh Token grant, client binding, and token endpoint.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): §2.2.2 and §4.14 on refresh token protection, rotation, sender-constraining, and replay detection.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): token revocation.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constraining in DPoP-supporting deployments.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): certificate binding per supporting infrastructure.
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, `OAuth2Authorization`, `OAuth2AuthorizationService`, and token settings.
- [Spring Authorization Server — TokenSettings API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/TokenSettings.html): default `reuseRefreshTokens`, refresh TTL.
- [Spring Authorization Server — TokenSettings.Builder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/TokenSettings.Builder.html): `reuseRefreshTokens(boolean)`.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): token endpoint, providers, and extension points.
- [Spring Security — OAuth2 Client Core Interfaces and Classes](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html): `OAuth2AuthorizedClientManager` and persistence handlers.
- [Spring Security — OAuth2 Client Authorization Grant Support](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html): Refresh Token provider and client behavior.
- [Spring Security — AuthorizedClientServiceOAuth2AuthorizedClientManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html): post-success saving and removal on `invalid_grant`.
