# Designing Reuse Detection and Token-Family Revocation When Extending

## 1. The Problem: An Old Refresh Token Unexpectedly Reappears

In a Spring Boot application building an OAuth 2.0/OpenID Connect (OIDC) Authorization Server with **Spring Security** and **Spring Authorization Server (SAS)**, refresh tokens allow clients to request new access tokens without requiring interactive user login every time an access token expires.

Suppose `orders-portal` holds refresh token `R1`. When needing to refresh the session, the client sends `R1` to `/oauth2/token`. The Authorization Server issues a new access token and, under a **refresh token rotation** policy, issues refresh token `R2` replacing `R1`.

Later, the token endpoint receives `R1` again. Two scenarios are possible:

- The legitimate client timed out, missed the first response, and **retried** with `R1`.
- An attacker copied `R1` and tried reusing it after it had already been consumed.

From the server's viewpoint, the two requests can look identical. If the server merely returns `invalid_grant` because `R1` is no longer valid, we have **rejected the invalid attempt** yet have not necessarily **detected and handled the possibility that the entire refresh token chain was compromised**. That is why some systems need a **refresh token family** and **reuse detection** model.

This lesson belongs to the **Refresh Token** chapter and explains:

1. How to distinguish refresh token rotation, reuse detection, and family-wide revocation.
2. What `TokenSettings.reuseRefreshTokens(false)` solves and what the application may need to add.
3. How to model parent–child relationships across refresh tokens, store history securely, and prevent race conditions.
4. When to revoke the entire family, when to only return `invalid_grant`, and the impact on already-issued access tokens.
5. How to extend Spring Authorization Server, test, and operate without breaking default grant checks.

> **Version note:** Class names and configuration examples illustrate the **Spring Authorization Server 1.x / Spring Security 6.x** line. APIs and integration points may change as Authorization Server is integrated into newer Spring Security generations. Verify Javadoc and runtime code for your exact version; never treat an illustrative token-family design as a built-in feature across all SAS versions.

## 2. From Ordinary Refresh Tokens to Token Families

### 2.1. Terms That Must Be Separated

| Term | Meaning | Example |
| --- | --- | --- |
| **Refresh token** | Credential used with `grant_type=refresh_token` to request new tokens | `R1` |
| **Refresh token rotation** | On each successful refresh, issue a replacement refresh token and disallow continued use of the old token | `R1 → R2 → R3` |
| **Token reuse / replay** | A consumed/disallowed refresh token reappears in a new request | Client resends `R1` after already receiving `R2` |
| **Refresh token family** | Group of refresh tokens sharing lineage from the same grant/authorization or session, including consumed old tokens | `F42 = {R1, R2, R3}` |
| **Reuse detection** | Recognizing that a **used** token was re-presented by retaining historical state long enough | Look up `R1`'s fingerprint, find `status=CONSUMED` |
| **Family revocation** | Invalidating all current refresh tokens and future tokens derivable from that family | Detect `R1` replay → block active `R3` as well |
| **Sender-constrained token** | Token bound to proof of possession of a client/device key or certificate per supported profile | DPoP or mTLS per matching standard, version, and policy |

**Enabling rotation does not automatically give you family reuse detection.** After rotation, an old token may simply no longer exist in the active authorization store. To recognize "this was once a valid token belonging to family F42," the server must retain a trace of the old token while prohibiting its reuse.

### 2.2. Lifecycle Illustration of a Family

```mermaid
flowchart LR
    R1["R1\nACTIVE"] -->|"valid refresh"| R2["R2\nACTIVE"]
    R2 -->|"valid refresh"| R3["R3\nACTIVE"]
    R1 -.->|"transitions to"| U1["R1\nCONSUMED"]
    R2 -.->|"transitions to"| U2["R2\nCONSUMED"]
    U1 -->|"R1 resubmitted"| D["REUSE_DETECTED"]
    D --> F["Family REVOKED"]
    F --> X["R3 can no longer refresh"]
```

The arrows describe logical relationships. When `R1` is exchanged for `R2`, `R1`'s status must transition from `ACTIVE` to `CONSUMED` atomically with issuing `R2`. `R1` must never revert to `ACTIVE`, even if connectivity drops between instances.

In the simplest model, **each family has only one active refresh token at a time**. This is a design choice that makes replay detection crisp, not the only mandatory specification for every protocol or product.

### 2.3. Token Family Does Not Mean Entire Account

A user may sign in to `orders-portal` on both laptop and phone. If each initial session/authorization creates a separate family:

```text
Alice + orders-portal + laptop session -> family F-LAPTOP
Alice + orders-portal + mobile session -> family F-MOBILE
Bob   + orders-portal + laptop session -> family F-BOB
```

A replay in `F-LAPTOP` should **at minimum** block refresh tokens belonging to that family per policy; it does not automatically require deleting all of Alice's tokens across every device or Bob's tokens. Depending on risk level, an organization may add an account-wide revocation action, keeping it distinct from family-wide operations to avoid overly broad invalidation.

## 3. Threat Model: Why Rotation Is Insufficient Without Remembering Old Tokens

### 3.1. Attacker Holds a Leaked Refresh Token

Suppose `R1` is stolen and both the legitimate client and an attacker can use it. One of them will exchange `R1` for `R2` first; the other resubmitting `R1` will be rejected.

```mermaid
sequenceDiagram
    autonumber
    participant C as Legitimate Client
    participant AS as Authorization Server
    participant DB as Family Store
    participant X as Attacker
    C->>AS: refresh_token=R1
    AS->>DB: Check R1 ACTIVE
    DB-->>AS: ACTIVE in family F42
    AS->>DB: Consume R1 and create R2
    AS-->>C: New access token + R2
    X->>AS: refresh_token=R1 again
    AS->>DB: Look up R1 fingerprint
    DB-->>AS: R1 CONSUMED, family F42
    AS->>DB: Mark F42 REVOKED
    AS-->>X: invalid_grant
    C->>AS: refresh_token=R2
    AS->>DB: Check F42
    DB-->>AS: REVOKED
    AS-->>C: invalid_grant; require re-login
```

This is **application behavior that must be explicitly designed** when choosing family-wide revocation, not a guarantee that default SAS executes all steps above. Detecting reuse reveals that the same refresh token appeared multiple times; **it cannot reliably tell which party is the legitimate client**. High-security systems therefore revoke the family and force the user to initiate a new authorization.

### 3.2. Limits of Detection Mechanisms

Reuse detection has limitations that should be documented openly:

- If a token is stolen yet **never reused**, there is no reuse event to detect.
- If an attacker exchanges the token first and the legitimate client never refreshes again, no replay may appear during the observation window.
- If an attacker obtains the latest token as well and continually controls the client, family rotation does not replace device protection, XSS/CSRF defenses, or sender-constraining.
- Without keeping a fingerprint/state of consumed tokens, a request with an old token may look like "nonexistent token," making it impossible to identify the family to revoke.
- If a browser/app retries after a timeout, family revocation can trigger even without an attacker. This is a **security–availability trade-off**, not a bug to fix by arbitrarily re-accepting `R1`.

### 3.3. Ways Refresh Tokens Leak

Refresh tokens should never appear in URLs, query strings, analytics, reverse-proxy logs, exception stack traces, debug dumps, or untrusted frontend areas. For backend confidential clients, keep tokens in a server-side credential store with encryption, access control, and proper key management. For public clients, evaluate modern profiles, rotation, sender-constraining, and platform-recommended storage.

**Never embed a `client_secret` in an SPA/mobile app to "protect" refresh tokens.** Public clients cannot keep such a secret confidential; rely on protocol bindings and appropriate storage models.

## 4. What Does Spring Authorization Server Support Out of the Box?

### 4.1. Basic Refresh Grant

At the token endpoint, the client sends:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=R1&scope=orders.read
```

This is an illustrative request; `BASE64_CLIENT_CREDENTIALS` and `R1` are placeholders, **not real credentials**. Confidential clients must authenticate with their registered method. Whether `scope` can be sent in a refresh request, which scopes are permitted, and how refresh tokens are issued depend on the grant, client, and configuration.

A typical refresh flow in SAS involves:

| Component | Role |
| --- | --- |
| `OAuth2TokenEndpointFilter` | Receives token requests |
| `OAuth2RefreshTokenAuthenticationConverter` | Parses `grant_type=refresh_token` and creates the grant authentication request |
| `OAuth2RefreshTokenAuthenticationToken` | `Authentication` object representing the refresh grant request |
| `OAuth2ClientAuthenticationFilter` | Authenticates the client per registered mechanism, when applicable |
| `OAuth2RefreshTokenAuthenticationProvider` | Validates refresh token, client, scopes, and grant conditions; issues new tokens |
| `OAuth2AuthorizationService` | Looks up and saves authorization/token state |
| `OAuth2TokenGenerator` | Generates tokens per configuration |
| `TokenSettings` | Policy for lifetimes, reuse/rotation, and other token settings |

### 4.2. Configuring Rotation with `reuseRefreshTokens(false)`

Example for a confidential web client (SAS 1.x):

```java
RegisteredClient ordersWeb = RegisteredClient.withId(stableInternalId)
        .clientId("orders-web")
        .clientSecret(passwordEncoder.encode(secretFromSecretManager))
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri("https://orders.example.com/login/oauth2/code/orders")
        .scope("orders.read")
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .build())
        .tokenSettings(TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(10))
                .refreshTokenTimeToLive(Duration.ofDays(14))
                .reuseRefreshTokens(false)
                .build())
        .build();
```

In this example, `stableInternalId` is a durably persisted client key; `secretFromSecretManager` is retrieved from a secret management system, not a hardcoded literal in source code. The snippet only constructs a `RegisteredClient`, not a complete Authorization Server configuration.

`reuseRefreshTokens(false)` requests **issuing a new refresh token upon successful refresh as implemented by SAS**. On SAS 1.x versions, authorization state can be updated to store the new refresh token in place of the old one. This prevents the old token from continuing to be used as the active token.

**Critical limitation:** the setting above **is not a token-family declaration API**, does not guarantee storing history of every consumed refresh token, does not provide a `family_id`, and must not be assumed to automatically **revoke an entire chain** upon detecting reuse. Verify the exact behavior of the `OAuth2RefreshTokenAuthenticationProvider` and `OAuth2AuthorizationService` you use.

### 4.3. `reuseRefreshTokens(true)` and Risks When Replay Detection Is Needed

Under a policy reusing the same refresh token, a client can use one token multiple times within valid bounds; thus "this token appeared a second time" is not anomalous evidence. To detect **reuse after consumption**, you need **rotation and verifiable consumed state**.

A new project should not keep reuse enabled indefinitely merely to avoid handling retries. Especially for public clients, OAuth 2.0 Security BCP mandates refresh token replay protection through appropriate **sender-constraining or rotation**; choose based on your threat model and version/framework support.

### 4.4. Public Clients Do Not Automatically Receive Refresh Tokens

Do not assume every Authorization Code + PKCE public client is issued a refresh token by SAS in all configurations. Some SAS 1.x setups restrict issuing refresh tokens to public clients. If a product needs long-lived sessions on SPAs/mobile apps, verify version capabilities, OAuth Security BCP principles, and BFF/backend token storage or sender-constraining options where appropriate.

Never alter client authentication or token generators to issue unpolicy-backed refresh tokens simply because "mobile needs long sessions."

## 5. When Do You Truly Need to Extend to Token Families?

Not every system needs a custom family registry. Before designing one, identify **testable requirements**:

| Requirement | Is standard rotation usually enough? | When is an extension needed? |
| --- | --- | --- |
| Old tokens cannot be used to request new tokens | Usually yes, with proper rotation and persistence | Test against your exact SAS version and repository |
| Distinguish a once-valid old token from a completely random token | Not necessarily | Requires storing fingerprints/historical records |
| Detect that already-consumed `R1` reappeared | Cannot be inferred from rotation settings alone | Requires a reuse registry and token status |
| Identify active descendant `R3` of `R1` | Not a guaranteed default model | Requires family ID and token lineage |
| Automatically block all future refreshes in the family | Not via `reuseRefreshTokens(false)` alone | Requires family revocation policy enforced at refresh endpoint |
| Prevent two concurrent requests from both exchanging the same token | Must verify depending on persistence | May require stronger locks/CAS/transactions |
| Immediately invalidate unexpired JWT access tokens | No | Resource Server needs state checks/denylist/introspection or suitable token TTL |
| Display security alert to the user | No | Requires audited/correlated reuse events |

If a system only needs old tokens rejected and access tokens live very briefly, standard rotation may satisfy the goal. If a system claims "detects stolen tokens and revokes the entire family," you must build **verifiable code paths and test evidence** for that claim.

## 6. Suggested Data Model for Families and Token History

One approach maintains two data groups:

1. **`refresh_token_family`**: family identity, client, principal, authorization/session, status, and revocation time.
2. **`refresh_token_lineage`**: fingerprint of each refresh token, parent/child relationship, consumed status, and timestamps.

```mermaid
erDiagram
    REFRESH_TOKEN_FAMILY ||--o{ REFRESH_TOKEN_LINEAGE : contains
    REFRESH_TOKEN_FAMILY {
        string family_id PK
        string registered_client_id
        string principal_name
        string authorization_id
        string status
        datetime created_at
        datetime expires_at
        datetime revoked_at
        bigint version
    }
    REFRESH_TOKEN_LINEAGE {
        string token_id PK
        string family_id FK
        string parent_token_id
        string token_fingerprint UK
        string status
        datetime issued_at
        datetime expires_at
        datetime consumed_at
    }
```

This is an **illustrative domain schema**, not a built-in schema generated by SAS. For multi-tenant systems, add tenant/issuer identifiers and data-partitioning constraints. `principal_name` may not represent an end user in some grants; family identification must match the refresh token's origin.

### 6.1. Suggested Fields and Constraints

| Field | Role | Security/operational rule |
| --- | --- | --- |
| `family_id` | Rotation chain ID | Generated once; unchanged across refreshes |
| `registered_client_id` | Internal `RegisteredClient.id` key | Never substitute HTTP `client_id` string |
| `authorization_id` | Link to `OAuth2Authorization` | Derived from valid authorization; used to locate token issuance state |
| `principal_name` | Authorized subject, when present | Never trust caller-supplied principal |
| `status` family | `ACTIVE`, `REVOKED`, `EXPIRED` | `REVOKED` family must never issue further refreshes |
| `token_fingerprint` | Lookup key without storing plaintext | Use HMAC or secure hash on high-entropy random tokens with proper key management |
| `parent_token_id` | Lineage across token generations | Aids tracing; never rely on token name ordering |
| `status` token | `ACTIVE`, `CONSUMED`, `REVOKED` | Never transition `CONSUMED` back to `ACTIVE` |
| `consumed_at` | Timestamp when token was used | Supports replay detection, auditing, and TTL |
| `version` | Concurrent update control | Use CAS/optimistic locking or row locks per design |
| `expires_at` | Token/family deadline | Never allow refreshes past the family's absolute ceiling |

Include a **unique constraint** on fingerprint and, in a single-active-token-per-family model, a mechanism ensuring two active tokens cannot coexist validly. Row locks on the family plus transactions can serialize all rotations; a unique partial index for active status is an extra **database-dependent** safeguard, not portable SQL across every dialect.

### 6.2. Why Retain Traces of Used Tokens?

With rotation, `OAuth2Authorization` may retain only the **current refresh token**. After `R1` is replaced by `R2`, `authorizationService.findByToken("R1", REFRESH_TOKEN)` may return no authorization. The server then cannot tell whether an incoming string is:

- An old once-valid token from family F42;
- A token that never existed;
- A token from another issuer/environment;
- A random value sent by an attacker.

To implement **genuine** replay detection, retain a **tombstone / fingerprint** of old tokens at least for the defined detection window. Purging `R1`'s record immediately after issuing `R2` destroys the ability to link `R1` back to its family.

Retaining traces does not mean storing raw refresh tokens. Plaintext tokens must be treated as credentials. For high-entropy tokens, you can use an HMAC-SHA-256 fingerprint (with a separately protected HMAC key) or a controlled equivalent so lookups succeed without exposing raw tokens if the DB is read improperly. When rotating HMAC keys, design versioning/lookup across old fingerprints until the detection lifecycle ends.

### 6.3. When Should a Family Expire?

Do not let rotation create an infinite refresh chain if policy requires re-login after a fixed interval. Distinguish two limits:

- **Per-refresh-token deadline:** each token has `expires_at`, e.g., 7 days from issuance.
- **Absolute family deadline:** no descendant may outlive the family's end timestamp, e.g., 30 days from initial grant.

Exact durations are **design examples** balancing UX, security, and session governance. A family may also terminate early on user logout, consent revocation, client disablement, credential rotation, or reuse events.

## 7. Atomic Rotation and Reuse Detection Algorithm

### 7.1. Minimal State Machine

```mermaid
stateDiagram-v2
    [*] --> ACTIVE : Issue R1
    ACTIVE --> CONSUMED : Refresh succeeds and creates R2
    ACTIVE --> EXPIRED : Past deadline
    ACTIVE --> REVOKED : User/admin/client revoke
    CONSUMED --> REUSE_DETECTED : R1 reappears
    REUSE_DETECTED --> REVOKED : Revoke family
    EXPIRED --> [*]
    REVOKED --> [*]
```

Note that `REUSE_DETECTED` can be an **audit event**, not necessarily a separate token status column. When a `CONSUMED` token reappears, the system marks the family `REVOKED` inside a transaction. An expired, never-used token must be rejected; whether to treat that as replay and revoke the whole family is a risk-policy decision.

### 7.2. Safe Sequence with a Shared Database

Conceptual sequence for a single refresh:

1. **Authenticate the OAuth client first.** Verify the registered client authentication method and credentials where applicable. Never trust a self-asserted `client_id`.
2. **Look up the token fingerprint.** If never seen, return `invalid_grant` and never pick an arbitrary family to revoke.
3. **Verify the token belongs to the right client/issuer.** If the request violates bindings, reject per protocol; never let an unauthorized caller revoke someone else's family.
4. **Lock the family or enforce version control.** Every request mutating a family follows the same lock order to prevent two concurrent refreshes.
5. **Re-read token state under the lock.** If the token is already `CONSUMED`, mark the family `REVOKED`, record the reuse event, and finish with a rejection decision. If the family is already `REVOKED`, simply reject.
6. **Verify standard grant conditions.** Token unexpired, valid authorization, client permitted to use refresh grant, scopes within granted bounds, and valid session/user/tenant policies.
7. **Create the new refresh token `Rnext` and new access token.** Save family ID, parent token, and new fingerprint; mark the old token `CONSUMED`.
8. **Update `OAuth2Authorization` and family/lineage consistently** inside an appropriate transaction. Commit before returning the token response.
9. **Return the token response** only after state persists successfully; if the transaction rolls back, never publish issued tokens as valid.

Steps 5 and 8 are where the system requires **atomicity**; checking `usedAt == null` in memory and writing in a separate step lets two concurrent requests both win.

### 7.3. Pseudocode for an Integrated Service

The following sample is **intentionally Java pseudocode** illustrating the business contract; `FamilyRepository`, `LineageRepository`, `RefreshIssuer`, and the DTOs **are not built-in SAS APIs**:

```java
@Transactional
RefreshDecision rotateAndPersist(
        AuthenticatedClient client,
        String presentedRefreshToken,
        Set<String> requestedScopes) {

    String fingerprint = tokenFingerprinter.hmac(presentedRefreshToken);
    TokenRecord initial = lineage.findByFingerprint(fingerprint);
    if (initial == null || !initial.belongsTo(client)) {
        return RefreshDecision.invalidGrant();
    }

    // All rotate/revoke paths lock the family in the same order.
    Family family = families.lockById(initial.familyId());
    TokenRecord current = lineage.findById(initial.id()); // Re-read under lock.

    if (family.isRevokedOrExpired()) {
        return RefreshDecision.invalidGrant();
    }

    if (current.isConsumed()) {
        families.markRevoked(family.id(), "REFRESH_REUSE");
        lineage.revokeActiveTokensInFamily(family.id());
        audit.recordReuse(family.id(), client.id());  // Never log raw tokens.
        return RefreshDecision.reuseDetected();
    }

    if (!current.isActive() || current.isExpired()) {
        return RefreshDecision.invalidGrant();
    }

    // This placeholder MUST preserve all default grant checks.
    grantChecks.verify(client, family, current, requestedScopes);

    IssuedTokens issued = refreshIssuer.issueReplacement(family, current);

    lineage.markConsumed(current.id());
    lineage.insertActiveChild(
            family.id(),
            current.id(),
            tokenFingerprinter.hmac(issued.refreshToken()),
            issued.refreshExpiresAt());
    authorizations.saveConsistentWithFamily(issued.authorization());

    return RefreshDecision.granted(issued);
}

RefreshDecision decision = rotationService.rotateAndPersist(
        authenticatedClient, rawRefreshToken, requestedScopes);

// Convert decision into an OAuth error OUTSIDE the transaction.
if (decision.isRejected()) {
    throw new OAuth2AuthenticationException(
            new OAuth2Error(OAuth2ErrorCodes.INVALID_GRANT));
}
return decision.tokensForResponse();
```

**Very important subtlety:** in many `@Transactional` configurations, calling `markRevoked(...)` and immediately **throwing an unchecked exception** rolls back the transaction and **undoes the family revocation**. The pseudocode therefore returns `ReuseDetected` outside the transaction to **commit revocation first**, and only then does the HTTP adapter throw `OAuth2AuthenticationException` and return `invalid_grant`. Alternatively, use dedicated transaction boundaries with explicit commit semantics; write integration tests for the reuse branch proving `REVOKED` actually persists.

This pseudocode omits full cryptography, token generation, locking, indexing, and SAS wiring, so never copy it into production without completing those parts. Specifically, `authorizations.saveConsistentWithFamily` is an abstraction **your application must design** so SAS state and the family registry stay consistent.

### 7.4. Two Concurrent Requests Using the Same R1

```text
Request A: authenticate client -> find F42 -> lock F42
Request B: authenticate client -> find F42 -> wait on F42 lock
Request A: sees R1 ACTIVE -> issue R2 -> R1 CONSUMED -> commit
Request B: re-read R1 -> sees CONSUMED -> mark F42 REVOKED -> commit
Request B: return invalid_grant
```

Under a conservative policy, request B triggers a **reuse event** and revokes request A's R2; even when A and B came from the same client due to a retry, the server may be unable to tell them apart. If product requirements demand softer retry handling, use a **strictly authenticated sender/transaction idempotency mechanism**, not merely "accept R1 for 30 extra seconds," since that window lets attackers reuse old tokens.

Without locks/CAS, if two requests both read `R1 ACTIVE`, both can issue different tokens. That is a severe bug that sequential tests will miss.

## 8. Integrating into Spring Authorization Server Without Dropping Default Checks

### 8.1. Why Not Just Add a Simple Validator?

In SAS 1.x, the refresh grant is handled by `OAuth2RefreshTokenAuthenticationProvider` against state in `OAuth2AuthorizationService`. A validator invoked after the framework fails to locate the old refresh token may **lack the data** to know which family it belonged to.

An extension solution typically needs:

- A **lineage store** holding fingerprints of consumed refresh tokens and family IDs.
- A **refresh grant handler** able to query lineage and authorization state with atomic control before issuing tokens.
- **Transaction coordination** between the family registry and `OAuth2AuthorizationService`.
- **Token issuance** using `OAuth2TokenGenerator` and SAS policies consistently.
- **Revocation handling** ensuring all active refresh tokens in the family are rejected thereafter.

If a custom provider replaces the standard provider yet only checks "is token in registry" before issuing tokens, it can bypass client binding, `RegisteredClient`, scopes, expiry, authorization state, or other policies. That creates higher risk than replay itself.

### 8.2. Choosing Extension Points and Provider Ordering

In SAS 1.x configuration style, the token endpoint provides:

```java
.tokenEndpoint(tokenEndpoint -> tokenEndpoint
    .authenticationProviders(providers -> {
        // Inspect the existing provider list for your exact version.
        // For the refresh_token grant, replace/wrap the matching provider
        // per reviewed design; NEVER leave two providers with a success path
        // that bypasses family policy.
    }))
```

This snippet **locates the extension point**, not a complete runnable configuration. Depending on integration style, you may need a transactional wrapper or a controlled replacement of `OAuth2RefreshTokenAuthenticationProvider` backed by a dedicated service. Simply **appending** a provider at the end of the list may never execute if the default provider handles the request first; conversely, putting a new provider at the front that returns tokens without running standard checks opens a bypass.

One easily verified architecture places the family registry **within the same persistence/transaction boundary** as the authorization store while maintaining grant logic equivalent to the standard provider. If using two databases or remote services, design fail-closed behavior, retry/idempotency, outbox/compensation, or other consistency mechanisms; never claim `@Transactional` alone guarantees cross-system atomicity.

### 8.3. Relationship with OAuth2Authorization and OAuth2AuthorizationService

Each family must map cleanly to an authorization or chain of authorizations per policy. Use internal `RegisteredClient.id` to link data; `client_id` is the request protocol identifier.

When a family is revoked, deleting only the active fingerprint from the registry is **not enough** if SAS can still find the refresh token via `OAuth2AuthorizationService` and another provider accepts it. Conversely, deleting the authorization from SAS without keeping old token tombstones loses reuse signals. **Both state sources must stay aligned**, and every refresh path must check family status.

### 8.4. Do Not Automatically Assume the New Refresh Token Is "Safe"

When `R1` reuse is detected, you do not know whether the attacker or the legitimate client currently holds `R2`. Ignoring the event because "R2 is the newer token" may let the party that hijacked the session keep refreshing. Family revocation is a conservative way to block both sides, forcing the user to re-login/re-authorize per policy.

## 9. Which Tokens Does Family Revocation Affect?

### 9.1. Distinguishing Refresh Rights from Active Access Tokens

| Subject | When family transitions to `REVOKED` | Additional steps needed for immediate effect |
| --- | --- | --- |
| **Active refresh token** | Must be rejected at the token endpoint when used again | All providers/instances check family status; no bypass paths |
| **Consumed refresh token** | Continues being rejected; may record replay | Retain fingerprint/tombstone across detection window |
| **Authorization code** | Not inherently part of the refresh token family | If policy disconnects the entire authorization, revoke via matching authorization relationship |
| **Self-contained JWT access token** | May remain accepted by APIs until `exp` | Short TTL, token denylist/version, introspection, or API-side state checks per SLA |
| **Opaque/reference access token** | Can be invalidated when authorization/token state updates | Resource Server uses introspection and consistent caching |
| **OIDC ID token** | Neither a refresh token nor an API access token | Handle sessions, OIDC logout, and ID token validation per its own role |
| **OP/RP login session** | Does not end automatically just by revoking a family | Separate logout/session revocation if required |
| **Other families for same user/client** | Should not be affected by default | Act further only under an explicit account/device-wide policy |

**Revoking an entire family does not immediately invalidate all signed access tokens.** If APIs only verify JWT signature, issuer, audience, and expiry, they do not automatically know `family.status=REVOKED`. Coordinate with Resource Servers whenever the product promises immediate access termination.

### 9.2. Revoking via the Token Revocation Endpoint

RFC 7009 defines the Token Revocation Endpoint, typically `/oauth2/revoke`, to revoke tokens under client authentication rules. It does not prescribe a universal **token family** schema across implementations.

If an application exposes `revokeFamily(familyId)`, implement it on an appropriately authorized admin backend:

1. Verify the actor is authorized to revoke the family by client/user/tenant.
2. Mark the family `REVOKED` with reason and timestamp.
3. Block refreshes for any active descendants.
4. Apply invalidation policies to the active `OAuth2Authorization`/tokens and propagate events to APIs when needed.
5. Write audit records and report the effective revocation scope accurately.

Never let arbitrary clients pass someone else's `familyId` to invalidate sessions at will. Even revoking a client's own family must verify client binding.

### 9.3. When Should You Revoke the Whole Family?

A common policy:

- **Evidence that a `CONSUMED` token was re-presented** after verifying matching client/issuer/binding → revoke family, log risk event, require new authorization.
- **Client or user proactively disconnects** → revoke the corresponding family per requested scope.
- **Compromised account or device detected** → consider revoking multiple families for that user/client and requiring re-authentication.
- **Completely unrecognized token** → return `invalid_grant`, rate-limit/observe, without guessing a family to revoke.
- **Expired yet unconsumed token** → reject; deciding whether to revoke the family or merely clean state depends on your threat model.

Avoid using `client_id` alone to wipe all families: a single client serves many users. Bind reliably to `registeredClientId`, principal, issuer/tenant, and the verified family itself.

## 10. Timeouts, Retries, and Grace Periods: The Hardest Problem

### 10.1. Why Can a Legitimate Client Cause a Reuse Event?

```text
T0   Client sends R1.
T1   Server commits R1 -> R2 and returns result.
T2   Network drops response; client never sees R2.
T3   Client retries with R1.
T4   Server sees R1 CONSUMED and revokes family.
```

The system cannot prove from R1 alone whether this is an attack. A conservative security-first option forces the user to sign in again. This behavior must be **documented and tested**, not treated as a bug to patch by letting R1 be exchanged repeatedly for several seconds.

### 10.2. Design Options and Trade-offs

| Option | Advantage | Risk / condition |
| --- | --- | --- |
| **Revoke immediately on reuse** | Easy to reason about; shrinks risk of attacker holding descendant | Legitimate retries may force user re-login |
| **Allow retry via securely bound idempotency key** | Reduces failures from dropped responses | Must prove identical sender/transaction; never return R2 to an unproven caller |
| **Grace period accepting old token** | May reduce retry errors | Creates an attacker reuse window; unsuitable without sender binding and clear threat model |
| **Sender-constraining (DPoP/mTLS)** | Reduces stolen-token value without the key | Requires full stack version support, proof/replay checks, and client key protection |
| **BFF/server-side token handling** | Keeps tokens out of JavaScript and centralizes refreshes | Increases operational responsibility for sessions/cookies/backend and CSRF |

If choosing a grace period, document its conditions, duration, request-distinguishing evidence, and revocation trigger when proofs diverge. **Never** simply say "old tokens stay valid for 30 seconds" and still claim reliable reuse detection.

### 10.3. Controlling Duplicate Requests on the Client

Alongside server controls, clients should use **single-flight refresh**: when multiple API requests see an expiring access token, only one refresh executes while others await its result. Across multiple tabs/processes, synchronize carefully per application architecture. However, single-flight only reduces benign errors; it **does not replace** single-use enforcement at the Authorization Server.

## 11. Common Security Risks and Implementation Mistakes

### 11.1. Enabling Rotation Alone and Calling It Reuse Detection

If SAS no longer retains old tokens, `R1` may return `invalid_grant`, yet the system cannot identify family F42. You must store fingerprints and historical mappings long enough if the goal is family-level detection/revocation.

### 11.2. Throwing an Exception on Replay Detection and Rolling Back the Revocation

Inside a transaction, `throw new OAuth2AuthenticationException(...)` right after setting `family.status=REVOKED` can roll back the change. Separate committing the revocation decision from returning the error response, and verify against a real DB.

### 11.3. Treating `findByToken` on the Default Repository as Full History

`OAuth2AuthorizationService.findByToken` looks up tokens per repository state; it makes no promise to retain every refresh token ever issued. Finding old tokens requires dedicated indexes/tombstones.

### 11.4. Writing a Custom Provider While Dropping Client and Scope Checks

A provider that only checks fingerprint before issuing tokens can be abused to refresh across different clients, higher scopes, or revoked authorizations. Preserve every SAS refresh grant check or a verified equivalent; prefer supported extension points over replacing the core.

### 11.5. Family Data and OAuth2Authorization Desynchronizing Across Two Stores

If lineage writes succeed while `OAuth2AuthorizationService.save` fails, the client may lose its refresh token; conversely, an active token might exist unrecognized by the family registry. Use a shared transaction when feasible, or outbox/compensation with fail-closed behavior proven by fault-injection tests.

### 11.6. Purging Tombstones Too Early

Deleting `R1`'s trace before descendants expire prevents linking `R1` replays to the family. Set minimum retention matching the detection window and family lifetime, bounded by data minimization and privacy policies.

### 11.7. Revoking All User Sessions Because One Family Replayed

This can cause broad disruption or denial of service. Default scope should be the affected family; escalate to client/account-wide revocation only under an explicit risk policy.

### 11.8. Logging Raw Refresh Tokens or Storing Them Plaintext in History Databases

Tokens leaked via logs/backups can be abused while unexpired. Use fingerprints for lookup, encrypt/protect tokens per SAS model, and restrict logs/telemetry/backups. Audits should record only family ID, client ID, reason code, timestamp, and correlation ID.

## 12. State-Machine and Race-Condition Testing

### 12.1. Baseline Test Matrix

| Scenario | Expected outcome |
| --- | --- |
| `R1` active, matching client, unexpired | Issues new access token and `R2`; `R1` becomes `CONSUMED` |
| Resubmit `R1` after successful refresh | `invalid_grant`; records reuse event and revokes F42 per policy |
| Use `R2` after F42 is revoked | `invalid_grant`; no new tokens issued |
| Submit token that never existed | `invalid_grant`; never arbitrarily revokes another family |
| Client B submits Client A's refresh token | Rejected by client binding; never lets Client B revoke A's family |
| Wrong client credentials | `invalid_client` at client authentication; never enters token issuance |
| Expired refresh token | Rejected; no new tokens created |
| Family past absolute lifetime | Rejected even if newest descendant has a longer individual deadline |
| Refresh requests ungranted/disallowed scope | `invalid_scope` or appropriate error; no privilege escalation |
| `reuseRefreshTokens(false)` effective | Returned token differs from prior token per policy |
| One user with two families | Replay in family A does not revoke family B by default |
| Two users on same client | Revoking Alice's family does not affect Bob's family |
| Logout/disconnect with revocation policy | Corresponding family blocked and audited properly |
| Unexpired JWT access token after family revocation | APIs follow promised revocation mechanism; never assume automatic invalidation |
| Opaque access token after revocation | Introspection/cache reflects status per SLA |
| Replay recorded yet HTTP returns error | DB retains `REVOKED` family after commit |

### 12.2. Concurrency and Retries

| Test | What to prove |
| --- | --- |
| Two concurrent requests sending same `R1` | Never two successful rotations; final state consistent |
| Request B waits on Request A's lock | After A commits, B sees fresh state instead of stale snapshot |
| Dropped response after rotation commit | Client retry handled per documented policy; no uncontrolled second token |
| Server crash before commit | No successful token returned without DB persistence |
| Server crash after commit, before response | Retries do not break single-use; recovery follows policy |
| Two nodes sharing DB | No split branches with two active descendants |
| Failure writing `OAuth2Authorization` after writing lineage | Whole transaction rolls back or compensation restores safe state |
| Reuse event triggers revoke inside transaction | `REVOKED` remains persisted even though token endpoint returns `invalid_grant` |
| Race between refresh and user disconnect | No new refresh token issued once revocation policy takes effect |
| Cache or family store connection loss | Fail-closed; never issue refresh tokens when state cannot be verified |

When using JDBC, test on a production-like database/dialect with real transaction isolation and locking. Simple in-memory tests or mocked repositories miss race conditions. Also verify `OAuth2AuthorizationService` when issuing access tokens and saving new refresh tokens.

### 12.3. Data-Safety Testing

- Search logs/APM/audits after tests to ensure zero raw refresh tokens, secrets, or full token responses appear.
- Confirm fingerprints cannot recover original tokens by design and HMAC keys are managed separately.
- Test that User A cannot revoke User B's family by substituting a family ID.
- Test that a disabled client, disabled grant, or revoked scope cannot refresh even with a valid fingerprint.
- Test that tombstone cleanup preserves detection throughout the committed window.
- Test rotation/replay in multi-issuer or multi-tenant environments without cross-family confusion.

## 13. Observability and Incident Response Workflow

### 13.1. Sample Audit Event

```json
{
  "event": "refresh_token_reuse_detected",
  "family_ref": "family-f42",
  "registered_client_id": "internal-client-ref",
  "client_id": "orders-web",
  "reason": "CONSUMED_TOKEN_PRESENTED",
  "action": "FAMILY_REVOKED",
  "correlation_id": "req-8ac4",
  "event_time": "2026-11-16T10:00:00Z"
}
```

This is an application-defined audit schema, not a standard event emitted automatically by SAS in all setups. Never send raw refresh tokens or exploitable fingerprints to public log systems; access to reference fields must be restricted with appropriate retention.

### 13.2. Useful Monitoring Metrics

- `invalid_grant` rate on the refresh grant by client and application version.
- Count of `CONSUMED` tokens re-presented and count of revoked families.
- Rate of reuse appearing immediately after initial refresh, suggesting network retry/single-flight bugs.
- Lock/transaction wait times, CAS conflict counts, and DB errors.
- Refresh requests rejected due to family status, token expiry, or client binding.
- Volume of old refresh tokens retained as tombstones and cleanup rate per retention.
- Rate of users forced to re-login after reuse and number of confirmed compromise incidents.

A buggy client retry rollout can spike reuse events. Do not automatically blame every event on an attacker or lock entire accounts; investigate correlation, client version, timestamps, and token-leak evidence.

### 13.3. Runbook When Reuse Is Detected

1. **Verify the event:** was the token genuinely `CONSUMED`, which family/client did it belong to, and were there concurrent legitimate requests or timeouts?
2. **Verify revocation state:** is the family `REVOKED` and are active refresh descendants blocked on every node?
3. **Assess unexpired access tokens:** do Resource Servers use offline JWTs or introspection; are denylists/state updates needed per SLA?
4. **Assess blast radius:** one family, one device, one client, one tenant, or multiple sessions of the same user?
5. **Notify and recover:** per policy, require re-login, rotate client credentials, or contact support; never attach tokens in notifications.
6. **Investigate root cause:** exfiltration via client/logs/proxies, malware, post-timeout retries, or concurrency bugs.
7. **Re-test:** reproduce sequential/concurrent replay and prove patched code never creates two active tokens or rolls back revocation.

If immediate revocation is demanded while APIs only verify JWTs offline without state checks, state the technical limitation clearly rather than claiming all access tokens were cut off immediately.

## 14. Design Case Study Exercise

An Authorization Server serves two clients:

```text
Client: orders-web
  Grant: authorization_code + refresh_token
  reuseRefreshTokens: false
  Access token TTL: 10 minutes
  Refresh token TTL: 7 days

Family F-A (Alice on laptop)
  R1: CONSUMED
  R2: CONSUMED
  R3: ACTIVE

Family F-B (Alice on phone)
  R4: ACTIVE
```

The system receives two requests:

- **Request X:** `R1` is resubmitted with valid client authentication.
- **Request Y:** `R3` is used to refresh nearly simultaneously.

Suppose the orders API uses offline JWTs and the current access token still has 8 minutes remaining.

Answer:

1. Why might calling `OAuth2AuthorizationService.findByToken(R1, REFRESH_TOKEN)` alone be insufficient to determine that `R1` belongs to family F-A?
2. After seeing `R1` is `CONSUMED`, where must the family be locked and how must Request Y be handled so no uncontrolled new descendant is issued?
3. Should Alice's F-B be revoked immediately? What policy is needed if you want to revoke both families?
4. Are unexpired JWT access tokens automatically rejected by the API when F-A is revoked?
5. If Request X was actually a post-timeout retry by the legitimate client, how can you distinguish it from an attacker? What is the trade-off of immediate revocation?
6. Why might throwing `OAuth2AuthenticationException` inside the transaction right after updating F-A negate the revocation?
7. Design at least six tests: old token, different client, two parallel refreshes, retry after timeout, offline JWT after revocation, and crash/restart between commit and response.

**Answer guidance:** a registry holding fingerprints/token lineage is required to locate F-A; use locking/CAS and transactions so after reuse F-A is revoked and Y cannot succeed past the effective revocation point. F-B is a separate family, revoked only under an explicit account-protection policy. Offline JWTs remain valid until `exp` without a denylist/state check. Retries and theft can look identical, so use strict idempotency/sender-binding mechanisms to reduce false positives; ensure revocation commits before raising the OAuth error.

## 15. Production Implementation Checklist

1. **Clear scope:** distinguish rotation, single-use, reuse detection, family revocation, and access token revocation SLAs.
2. **Client:** client auth, grants, scopes, redirects/consent, and token policies remain governed by SAS; never replace standard providers with under-validated logic.
3. **Rotation:** enable `reuseRefreshTokens(false)` when appropriate and verify behavior on your exact version/persistence.
4. **Lineage:** each family has a stable ID, old tokens have fingerprints/tombstones and parent relationships; never store raw tokens in logs/history indexes.
5. **Atomicity:** at most one active descendant; use transactions + lock/CAS, test multi-node, and ensure revocation commits before returning `invalid_grant`.
6. **Policy:** decide when to revoke a family, when to block user/client, and how to handle unknown/expired tokens and legitimate retries.
7. **Access tokens:** account for JWT vs. opaque, introspection caches, and effective post-revocation lifetimes.
8. **Data store:** configure retention, indexes, backups, HMAC key management, transactions, and historical token cleanup.
9. **Client application:** single-flight refresh, credential protection, no blind retries with old refresh tokens, safe re-authorization path.
10. **Testing:** sequential/concurrent replay, double-submits, failovers, crashes, dropped responses, DB errors, and races with logout/disconnect.
11. **Operations:** minimal auditing, reuse alerts, runbooks for both compromise and false positives, zero token leaks.

## 16. References

- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, `OAuth2Authorization`, `OAuth2AuthorizationService`, `TokenSettings`.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): token endpoint, refresh grant, and provider extension points.
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): `AuthenticationManager`, `AuthenticationProvider`, and separation of concerns.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Refresh Token Grant, client authentication, and scope constraints.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): refresh token protection, replay detection, rotation, and sender-constraining.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): token revocation behavior.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): token state and Resource Servers.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained tokens under the DPoP profile.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): certificate binding and client authentication; verify actual stack support.

**Takeaway:** `reuseRefreshTokens(false)` is an important step to rotate refresh tokens, yet **detecting reused old tokens and revoking the entire token family is a distinct state, transaction, and policy problem**. Getting it right requires recording traces of consumed tokens, linking families/clients/principals accurately, performing atomic updates on rotation or revocation, handling retries cautiously, and verifying impact at Resource Servers. No single configuration flag substitutes for this design, testing, and operational discipline.
