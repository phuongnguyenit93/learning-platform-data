# 17.10. Multi-Instance Refreshing and Coordinating Token Store Updates

## 1. Problem Statement: One Refresh Token Used by Multiple Instances

In Spring Security OAuth 2.0/OIDC Client, an application typically holds an <code>OAuth2AuthorizedClient</code> containing the ClientRegistration, principal name, access token, and refresh token (if issued by the Authorization Server). When the access token expires or is about to expire, <code>OAuth2AuthorizedClientManager</code> can use the refresh token to request a new access token.

In a **single-instance, low-concurrency** environment, this operation is easy to reason about. However, when running multiple replicas behind a load balancer or multiple workers sharing a database, nearly simultaneous requests can read **the exact same stale token record** and decide to refresh at once.

Example:

~~~text
Token store currently holds:
    registrationId = company
    principalName  = user-123
    access token   = A0 (about to expire)
    refresh token  = R0

Instance A reads R0
Instance B reads R0
Instance A sends R0 to the Token Endpoint
Instance B also sends R0 to the Token Endpoint
~~~

If the OpenID Provider / Authorization Server uses **refresh token rotation**, each successful refresh issues a new refresh token and invalidates the old one:

~~~text
R0  --refresh succeeds-->  A1 + R1
R0  --reused------------>  invalid_grant or reuse detected
~~~

The consequence is not merely an extra HTTP call. Depending on provider policy, reusing R0 can also trigger **reuse detection** and invalidate an entire token family, rendering even the newly issued R1 unusable.

Thus, the core problem in a multi-instance system is:

> How do we ensure refreshes for **the same authorized client** are coordinated, and that access token / refresh token data in the store is always updated consistently?

This topic sits at the intersection of **OAuth2 Client**, **concurrency control**, **persistent storage**, and **distributed systems**. No single <code>refreshToken()</code> call can solve all of this by itself.

## 2. Objectives and Terminology

After this lesson, you will be able to:

1. Explain the race condition when multiple instances refresh the same authorized client simultaneously.
2. Distinguish refresh token rotation, token reuse detection, and access token expiry.
3. Understand that authorized clients must be stored by <code>(registrationId, principalName)</code>, partitioned by issuer/tenant when needed.
4. Design key-scoped **single-flight refresh**, ensuring at most one effective refresh runs for a given authorized client at a time.
5. Choose the right mechanism among **distributed locks**, **optimistic concurrency/CAS**, **fencing**, or a single-writer model.
6. Ensure **the new access token and refresh token are saved as one consistent update**.
7. Handle <code>invalid_grant</code> errors and failure handlers without accidentally deleting a newer token saved by another instance.
8. Integrate cleanly with Spring Security managers/services without conflating storage, refresh providers, and business locks.

Key terms:

| Term | Meaning |
|---|---|
| **Authorized client** | Associates a ClientRegistration, principal name, and issued tokens |
| **Refresh token rotation** | A successful refresh issues a new refresh token and prevents the old token from being used as before |
| **Single-flight** | When multiple requests need the same result, only one performs the work and the rest use that result |
| **Lost update** | A newer record gets overwritten by a late write carrying stale data |
| **CAS (compare-and-swap)** | Write only if the current version/state still matches what was observed |
| **Fencing token** | A monotonically increasing generation/ownership number letting storage reject an older writer even if its lock lease expired |
| **Lease** | A time-bounded lock that must be renewed or checked before acting |
| **Token family** | A group of related refresh tokens under the provider's rotation/reuse-detection policy |

## 3. How Does Spring Security Manage Refresh Tokens?

Main components:

~~~mermaid
flowchart TD
    APP["Request or background job"] --> M["OAuth2AuthorizedClientManager"]
    M --> REG["ClientRegistrationRepository"]
    M --> STORE["OAuth2AuthorizedClientService or Repository"]
    M --> P["OAuth2AuthorizedClientProvider"]
    P --> RT["Refresh Token Provider"]
    RT --> OP["Authorization Server /token"]
    OP --> RT
    RT --> M
    M --> STORE
    STORE --> DB["Database / Session / Distributed Store"]
~~~

During a single invocation:

1. The manager selects the ClientRegistration.
2. The manager loads <code>OAuth2AuthorizedClient</code> by registration and principal.
3. The refresh token provider checks whether the access token is expired/nearing expiry and whether a refresh token exists.
4. If eligible, the provider sends a refresh token grant to the Token Endpoint.
5. The Authorization Server returns a new access token and optionally a new refresh token.
6. The manager saves the updated authorized client via its success handler and service/repository.

### 3.1. Abstractions to distinguish

| Component | Role | Creates a distributed lock? |
|---|---|---|
| <code>ClientRegistrationRepository</code> | Client config, issuer, grant, endpoints | No |
| <code>OAuth2AuthorizedClient</code> | Current token state for a principal | No |
| <code>OAuth2AuthorizedClientService</code> | Saves, loads, removes authorized clients by registration/principal | Does not guarantee single-flight refresh by default |
| <code>OAuth2AuthorizedClientRepository</code> | Stores authorized clients in Servlet context | Does not coordinate across nodes by default |
| <code>OAuth2AuthorizedClientProvider</code> | Executes refresh grant when applicable | Does not create distributed locks by default |
| <code>OAuth2AuthorizedClientManager</code> | Coordinates providers and persistence | Does not serialize refreshes cluster-wide by default |
| Application Lock/CAS adapter | Controls concurrency at the token-state boundary | Must be designed or supplied separately |

Key point: **switching from an in-memory service to a JDBC service does not automatically stop two nodes from refreshing together**. JDBC shares the token record, yet if both nodes read the same old version and both call the Token Endpoint, the race still happens.

### 3.2. Authorized client lookup key

With <code>OAuth2AuthorizedClientService</code>, lookups normally use:

~~~text
registrationId + principalName
~~~

Examples:

~~~text
(company, user-123)
(partner, user-123)
(company, user-456)
~~~

These are three distinct authorized clients; never lock the entire application just to refresh one user.

In multi-tenant/multi-issuer systems, `principalName` must be designed to avoid collisions. Subject <code>123</code> from issuer A is not automatically the same person as subject <code>123</code> from issuer B. If registration ID and principal name do not isolate tenants, fix the identity/storage design before adding locks.

## 4. Race Condition Timeline with Refresh Token Rotation

Suppose R0 can only succeed once and the OP returns R1 upon refresh.

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Instance A
    participant B as Instance B
    participant DB as Authorized Client Store
    participant OP as Token Endpoint
    A->>DB: load(company, user-123)
    DB-->>A: A0, R0, version=7
    B->>DB: load(company, user-123)
    DB-->>B: A0, R0, version=7
    A->>OP: refresh_token=R0
    OP-->>A: A1, R1
    B->>OP: refresh_token=R0
    OP-->>B: invalid_grant / reuse detection
    A->>DB: save A1,R1
    B->>DB: error handler may remove authorized client
    Note over DB: If deleted unconditionally, freshly saved A1,R1 may be lost
~~~

This race has at least three consequences:

**1. The second request fails.** B receives <code>invalid_grant</code> even though from the initial perspective both A and B saw a stored token.

**2. Fresh state gets deleted.** If B errors out and runs a failure handler that deletes the authorized client solely by registration/principal, it can delete the A1/R1 record A just saved.

**3. Token family is impacted.** If the OP treats reusing R0 as stolen-token evidence, it may invalidate related refresh tokens. Depending on OP policy, even R1 in the database may become unusable.

Not every provider shares the exact same policy. Some allow a short grace period, some issue a new refresh token every time, and some do not rotate. **Never assume a provider will tolerate two concurrent refresh requests** simply because no error showed up in testing.

### 4.1. Races do not happen only between two servers

Two threads on the same instance can also race when concurrently handling two HTTP requests for one principal. Sources of competing refreshes include:

- Two browser tabs calling the backend simultaneously.
- API gateway request retries.
- A web request and a background job sharing the same authorized client.
- Two replicas behind a load balancer.
- A scheduler running on multiple nodes.
- An instance timing out and retrying while the earlier refresh is still in flight.

Coordination must therefore cover **every code path capable of triggering a refresh**, not just one controller.

## 5. Second Race: Lost Updates and Stale Writes

Even if the OP does not invalidate the token family on reuse, storage can still be overwritten out of order.

Example:

~~~text
T0  Token store: access=A0, refresh=R0, version=7
T1  A reads version=7
T2  B reads version=7
T3  A refreshes successfully: A1,R1
T4  A saves A1,R1, version=8
T5  B saves an old snapshot or late result derived from R0
T6  Token store is overwritten with stale/invalid state
~~~

Under strict refresh rotation, B might not get a new token; however, **stale writes** also happen when:

- Multiple places call <code>saveAuthorizedClient()</code>.
- A node updates authorities/session state and accidentally re-saves an old authorized client.
- Two refreshes return different tokens because the provider allows a reuse/grace period.
- A lock's lease expires while an older writer still finishes its request and writes late.

A solution that only prevents concurrent calls to the Token Endpoint without protecting the write step can still suffer lost updates.

### 5.1. Preserve the access/refresh token pair atomically

After a successful refresh:

~~~text
Before: access=A0, refresh=R0
After:  access=A1, refresh=R1
~~~

Never save A1 while keeping R0 when the OP rotated. If the response omits a new refresh token, OAuth2 refresh logic retains the prior refresh token per the token response contract; if R1 is returned, replace with R1 accurately.

**The entire authorized client must be persisted as one consistent state**, never updating the access token and refresh token in two separate operations where other nodes can observe a half-old, half-new state.

## 6. Coordination Strategies

No single solution fits every architecture.

| Strategy | Idea | Advantages | Risks / limitations |
|---|---|---|---|
| **Single instance owns refresh** | All refreshes for a key route through one worker / single writer | Easy to reason about ordering | Needs queues/routing and failover |
| **Per-key distributed lock** | Only one node holds the lock during refresh | Prevents concurrent Token Endpoint calls if all nodes obey | Lease expiry, node pauses/crashes, stale writers |
| **Optimistic CAS / version** | Write only if version is unchanged | Prevents lost updates | CAS alone **does not stop two requests from sending R0 to the OP** |
| **Lock + CAS / fencing** | Serialize refresh then guard state writes | Better defense against both duplicate refreshes and stale writes | Higher complexity; requires proper lock timeouts and storage |
| **Database row lock** | Use transaction/row-level lock to serialize | Uses existing DB | Holding a transaction across HTTP calls risks bottlenecks/timeouts |
| **In-JVM single-flight cache** | Threads on one node share a future | Cuts internal duplicate refreshes | Does not coordinate across replicas |

**Practical recommendation:** for multi-instance systems with refresh token rotation, you typically need **per-key coordination before calling the Token Endpoint**, **re-reading the token after acquiring refresh ownership**, and **protecting storage updates with version/fencing** if locks can expire or other code paths write data.

### 6.1. Lock by key, never globally

Avoid a single global lock:

~~~text
lock = "oauth2-refresh-global"
~~~

User A's refresh would block unrelated user B.

Use a stable key based on:

~~~text
oauth2-refresh:{registrationId}:{principalKey}
~~~

In multi-tenant environments, include the verified tenant or issuer namespace. Never build lock keys from unvalidated user-controlled strings that could cause resource contention.

If keys are stored in Redis or observable systems, **hash the principal identifier** to avoid leaking PII in key names. Use one canonicalization scheme so every node computes the exact same key.

## 7. Single-Flight Algorithm with Double-Check

A safer workflow:

~~~text
function authorizeWithCoordinatedRefresh(registration, principal):
    key = stableKey(registration, principal)

    current = store.load(key)
    if current already has a usable access token per policy:
        return current

    acquire distributed lock for key, with timeout
    try:
        latest = store.load(key)  // re-read after acquiring lock

        if latest was already refreshed by another node and token is usable:
            return latest

        result = refresh using the latest refresh token in latest

        save result atomically with version/fencing
        return committed state
    finally:
        release lock only if still the owner
~~~

This is **pseudocode**, not Spring Security library code.

### 7.1. Why load twice?

Suppose A and B both see A0 nearing expiration. A acquires the lock first, refreshes, and saves A1/R1; B waits.

If B finishes waiting for the lock and **still uses the A0/R0 copy read before waiting**, B sends R0 to the OP anyway, reproducing the original race.

Therefore, after B acquires the lock, it must:

1. **Reload** the latest authorized client from storage.
2. Check whether the new access token is now usable.
3. If A1 is valid, **skip refreshing**.
4. If refresh is still needed, use the refresh token from **the latest record**.

### 7.2. When the lock cannot be acquired

Do not immediately bypass the lock and refresh with the old copy.

Options:

- Wait for a bounded time and re-read storage.
- Return a transient error / 503 on internal APIs if waiting fails and the token is expired.
- For some workloads, use the **still-valid old access token** to finish the request if policy and safety margins allow.
- For background jobs, defer processing under a bounded retry policy.

Never use the old refresh token as a "shortcut" while another node is actively refreshing.

### 7.3. When the lock holder crashes

If A crashes before calling the Token Endpoint, the lock lease expires and B can proceed. If A crashes **after the OP accepted R0 but before saving R1**, the store still holds R0 even though the OP may have invalidated R0.

This is a **gap that cannot be closed completely with locks or database transactions alone** because the Token Endpoint and storage are two independent systems that normally share no distributed transaction.

The system must have a recovery policy:

- If the provider supports a grace period or idempotency, follow that contract.
- If the refresh token becomes unusable, mark the client as needing reauthorization.
- For delegated user tokens, ask the user to log in / re-authorize when appropriate.
- Never fabricate tokens or assume outcomes without verification.

## 8. Distributed Locks: Leases, Ownership, and Fencing

### 8.1. Time-bounded locks

Example lock entry:

~~~text
key = oauth2-refresh:company:hash-user-123
owner = random-owner-id-for-this-attempt
lease = 15 seconds
~~~

The duration must cover normal token requests without being infinite. HTTP timeouts, GC pauses, network delays, and token endpoint outages make execution time unpredictable.

If the lease expires while node A is still working, node B can acquire the lock. When A returns and writes, there are **two overlapping owners over time**, and a lock alone no longer protects storage.

### 8.2. Release must verify the owner

Dangerous pattern:

~~~text
DEL oauth2-refresh:company:hash-user-123
~~~

If A's lease expired, B acquired a new lock, and then A runs an unconditional <code>DEL</code>, A deletes B's lock.

Release must be an atomic check-and-delete:

~~~text
if lock.owner == myOwnerId:
    delete lock
~~~

In Redis, use an atomic script/command designed to compare owner and delete in one step. Never run separate `GET` and `DEL` commands where lock ownership could change in between.

### 8.3. Fencing tokens

A fencing token is a **monotonically increasing sequence number** issued whenever a lock gets a new owner:

~~~text
A acquires lock: fencing=41
B acquires lock later: fencing=42
~~~

When A wakes up late and tries to write with `fencing=41`, storage rejects it because it has already seen newer owner `fencing=42`.

Pseudocode:

~~~text
saveIfFenceIsCurrent(key, newTokens, fencing):
    if fencing < persistedFence:
        reject stale writer
    else:
        update authorized client and persistedFence atomically
~~~

Fencing must be **enforced at the write destination**; generating a fencing number that storage ignores does nothing.

Fencing guards against **late overwrites**, yet cannot recall a refresh request that already reached the OP and consumed R0. Preventing reuse therefore still requires coordination **before calling the Token Endpoint**.

### 8.4. Avoid keeping a database transaction open indefinitely while calling `/token`

A tempting idea is <code>SELECT ... FOR UPDATE</code> and calling the HTTP Token Endpoint inside the same transaction:

~~~text
BEGIN TRANSACTION
SELECT token FOR UPDATE
POST /token  <- waiting on external network
UPDATE token
COMMIT
~~~

This serializes rows in the database, yet holds locks throughout the network call; when the OP slows down, it causes contention, exhausted connection pools, and deadlocks/timeouts.

If using DB locks, carefully tune timeouts, transaction isolation, lock leases, and recovery. For many systems, a distributed lock outside the transaction paired with a short CAS update is easier to operate.

## 9. Optimistic Concurrency and CAS on the Token Store

**CAS does not make the HTTP refresh atomic with the database**, yet it stops stale writers from overwriting newer tokens.

Suppose the table has a <code>version</code> column:

~~~text
registration_id | principal_name | access_token | refresh_token | version
company         | user-123       | A0           | R0            | 7
~~~

After a successful refresh, A updates A1/R1 from version 7:

~~~sql
UPDATE oauth2_authorized_client_state
SET access_token_ciphertext = :new_access_token,
    refresh_token_ciphertext = :new_refresh_token,
    access_token_expires_at = :new_expires_at,
    version = version + 1
WHERE registration_id = :registration_id
  AND principal_name = :principal_name
  AND version = :expected_version;
~~~

If the updated row count is **1**, A succeeded. If **0**, the data is no longer at the expected version: another writer modified or deleted the row, or the key does not exist.

Always **check the affected row count**. Never run an `UPDATE ... WHERE version` and ignore its return value.

### 9.1. What does CAS protect?

~~~text
A and B both read version=7

A CAS version 7 -> 8: succeeds
B CAS version 7 -> 8: fails because version is already 8
~~~

Thus B cannot overwrite A1/R1 with stale data.

### 9.2. What does CAS NOT protect?

CAS runs **after** the node called the Token Endpoint. If both A and B sent R0 before writing, the OP may still detect reuse.

Therefore:

> **CAS solves lost updates in storage; per-key coordination solves duplicate refreshes at the Token Endpoint.**

The two mechanisms complement each other when refresh token rotation carries risk.

### 9.3. Default JDBC schema does not include `version`

Spring Security's <code>JdbcOAuth2AuthorizedClientService</code> provides JDBC persistence for authorized clients, yet you must not assume its default schema and API in your version support optimistic versioning or fencing as shown above.

If CAS is required, the application may need to:

- Create a custom table/version column and customize the service/DAO SQL.
- Build a wrapper or custom <code>OAuth2AuthorizedClientService</code> with compare-and-set semantics.
- Handle serialization and encryption for token values.
- Protect both <code>save</code> and <code>remove</code> from stale operations.

Do not just add a <code>version</code> column to the database and expect the manager to use it automatically.

## 10. Designing a Versioned Token Store

A conceptual schema for authorized-client state:

~~~sql
CREATE TABLE oauth2_authorized_client_state (
    registration_id           VARCHAR(100) NOT NULL,
    principal_name            VARCHAR(255) NOT NULL,
    access_token_ciphertext   BYTEA NOT NULL,
    refresh_token_ciphertext  BYTEA,
    access_token_issued_at    TIMESTAMP WITH TIME ZONE,
    access_token_expires_at   TIMESTAMP WITH TIME ZONE,
    version                   BIGINT NOT NULL DEFAULT 0,
    fencing_sequence          BIGINT NOT NULL DEFAULT 0,
    updated_at                TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (registration_id, principal_name)
);
~~~

This is **illustrative PostgreSQL-style DDL**, not a copy-paste Spring Security schema. A real implementation also needs token type, scopes, ClientRegistration metadata/reference, refresh-token timestamps, serialization format, and other fields per <code>OAuth2AuthorizedClient</code>.

<code>access_token_ciphertext</code> and <code>refresh_token_ciphertext</code> emphasize that tokens are **credentials**, not ordinary data. Apply encryption-at-rest, key management, database permissions, TLS, backup protection, and retention policies.

### 10.1. Atomically update both tokens

Do not split:

~~~text
UPDATE access_token = A1
COMMIT
UPDATE refresh_token = R1
COMMIT
~~~

Between the two commits, node B can see access token A1 paired with rotated-out refresh token R0.

Replace with **one atomic transaction/update** covering the entire token state and version.

### 10.2. Deletes must also be conditional

When a refresh request fails with <code>invalid_grant</code>, running:

~~~sql
DELETE FROM oauth2_authorized_client_state
WHERE registration_id = :registration_id
  AND principal_name = :principal_name;
~~~

can delete a newer record just saved by another node.

With versioning:

~~~sql
DELETE FROM oauth2_authorized_client_state
WHERE registration_id = :registration_id
  AND principal_name = :principal_name
  AND version = :expected_version;
~~~

Delete only if the row in the DB **is still the version that failed**. If 0 rows were deleted, reload state, check whether another node already refreshed, and decide next steps rather than retrying an unconditional delete.

### 10.3. Refresh token rotation and token encryption

If encryption uses random nonces/IVs, two ciphertexts of the same refresh token will differ. Comparing ciphertexts to check "same R0" is therefore unreliable with non-deterministic encryption.

Prefer:

- Per-record version/CAS.
- Non-reversible HMAC/fingerprint with a dedicated key if comparing tokens without exposing raw values is necessary.
- Never logging raw tokens to compare them.

Hashes/fingerprints are still sensitive operational data and must have restricted storage/usage. A CAS version counter is usually simpler and clearer for preventing stale writes.

## 11. Integrating with Spring Security: Choosing Managers by Context

For Servlet web apps:

~~~java
DefaultOAuth2AuthorizedClientManager
~~~

normally pairs with <code>OAuth2AuthorizedClientRepository</code> and HTTP requests.

For services/background jobs:

~~~java
AuthorizedClientServiceOAuth2AuthorizedClientManager
~~~

pairs with <code>OAuth2AuthorizedClientService</code> and has no dependency on Servlet requests.

In both cases, coordination must wrap **every place that performs refreshes**. If an app has both a web manager and a service manager touching the same authorized client, locking only one inconsistently will not enforce single-flight.

### 11.1. Configuring the Refresh Token Provider

Example service manager that only refreshes already-existing authorized clients:

~~~java
package example.security;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class RefreshManagerConfig {

    @Bean("refreshAuthorizedClientManager")
    OAuth2AuthorizedClientManager refreshManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService service) {

        var provider = OAuth2AuthorizedClientProviderBuilder.builder()
            .refreshToken(configurer ->
                configurer.clockSkew(Duration.ofSeconds(45)))
            .build();

        var manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, service);
        manager.setAuthorizedClientProvider(provider);

        return manager;
    }
}
~~~

Points to note:

- This manager **does not initiate authorization code login** when no authorized client exists yet.
- <code>refreshToken()</code> runs only when a refresh token exists and refresh conditions hold.
- Service/repository beans must point to the same storage where the app saved the authorized client after login.
- <code>clockSkew</code> marks tokens as needing refresh early; when many requests arrive near that mark, concurrency rises.
- **This manager setup does not yet include a distributed lock.** Add a coordination layer if running multiple instances that must avoid parallel refreshes.

If the app never refreshes in background jobs, do not define a service manager merely because it has an OIDC login. Match extension points to real flows.

### 11.2. Do not wrap the manager superficially

One naive idea:

~~~text
lock.acquire(key)
manager.authorize(request)
lock.release(key)
~~~

If **every refresh** passes through the wrapper, the lock never expires prematurely, and the manager reloads storage inside the lock, this curbs races.

However, the manager normally **persists results inside the <code>authorize(...)</code> call** via its success handler. If the lease expires or another code path invokes the manager without the lock, an external wrapper cannot prevent stale writes without CAS.

Therefore, when safety against lease expiry or partial failures is required:

1. All code paths must use the same coordinator.
2. Storage or custom success/failure handlers must perform **conditional updates/deletes**.
3. Check ownership/fencing at commit time where possible.
4. Reload the latest token after waiting for the lock.

Never describe a Java `synchronized` method or a naive distributed lock as "having completely solved refresh token rotation in a cluster".

## 12. Java: Application-Layer Coordinator

The example below decouples key-based locking from Spring Security. <code>DistributedKeyMutex</code> is an **architectural interface**, not a built-in Spring Security class. Production apps must supply an implementation backed by Redis, DB, or an appropriate distributed lock service.

### 12.1. Key-based lock interface

~~~java
package example.security.refresh;

import java.time.Duration;
import java.util.function.Supplier;

public interface DistributedKeyMutex {

    /**
     * At most one owner per key at a time.
     * Throws an appropriate exception if lock cannot be acquired within waitTimeout.
     * Implementations must release by owner and guard the lease.
     */
    <T> T withLock(
        String key,
        Duration waitTimeout,
        Supplier<T> work);
}
~~~

### 12.2. Coordinator invoking the manager inside the lock

~~~java
package example.security.refresh;

import java.time.Duration;
import java.util.Objects;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;

@Service
public class CoordinatedRefreshService {

    private final OAuth2AuthorizedClientManager manager;
    private final DistributedKeyMutex mutex;

    public CoordinatedRefreshService(
        @Qualifier("refreshAuthorizedClientManager")
        OAuth2AuthorizedClientManager manager,
        DistributedKeyMutex mutex) {
        this.manager = manager;
        this.mutex = mutex;
    }

    public OAuth2AuthorizedClient authorize(
        String registrationId,
        String trustedPrincipalKey) {

        Objects.requireNonNull(registrationId);
        Objects.requireNonNull(trustedPrincipalKey);

        // Real lock keys should canonicalize and hash sensitive identifiers.
        String lockKey =
            "oauth2:refresh:" + registrationId + ":" + trustedPrincipalKey;

        return mutex.withLock(
            lockKey,
            Duration.ofSeconds(5),
            () -> {
                OAuth2AuthorizeRequest request =
                    OAuth2AuthorizeRequest
                        .withClientRegistrationId(registrationId)
                        .principal(trustedPrincipalKey)
                        .build();

                OAuth2AuthorizedClient client = manager.authorize(request);
                if (client == null) {
                    throw new IllegalStateException(
                        "No authorized client or refresh capability");
                }
                return client;
            });
    }
}
~~~

**Very important limitation of this example:** this illustrates **application-level coordination when all manager calls go through the same mutex**, not a full production implementation hardened against stale writes. <code>DistributedKeyMutex</code> has no implementation here; you must address lease/renewal, owner-checked release, acquisition timeouts, and storage fencing/CAS. If the manager writes to an <code>OAuth2AuthorizedClientService</code> that lacks conditional writes, a stale writer after lease expiry can still overwrite tokens.

When high guarantees are needed, combine custom versioned storage and/or a custom refresh workflow to **push version/fencing down to the write point**, rather than putting locks only on a controller while other paths bypass them.

### 12.3. Reloading after acquiring the lock

In the example above, the manager loads the authorized client inside <code>authorize()</code> after the coordinator acquires the lock. That is far better than a caller holding an <code>OAuth2AuthorizedClient</code> read before waiting and refreshing with that stale snapshot.

When writing a detailed custom refresh workflow, make the re-read rule explicit:

~~~text
withLock(key):
    latest = authorizedClientStore.load(key)
    if latest.accessToken is still usable:
        return latest
    if latest.refreshToken is absent:
        require reauthorization
    response = tokenClient.refresh(latest.refreshToken)
    compareAndSet(latest.version, response)
~~~

With the default <code>OAuth2AuthorizedClientManager</code>, align on when the provider treats a token as "about to expire" based on clock skew. Avoid using a different time threshold in the coordinator than in the provider, which could cause the coordinator to return a token the provider actually wanted to refresh.

## 13. Java: Versioned Storage Model to Prevent Stale Writes

To illustrate CAS independently of the default schema, define a specialized API:

~~~java
package example.security.refresh;

import java.util.Optional;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;

public interface VersionedAuthorizedClientStore {

    Optional<VersionedClient> load(
        String registrationId,
        String principalName);

    /**
     * Writes only when current version equals expectedVersion.
     * Returns false on concurrent modification.
     */
    boolean compareAndSave(
        String registrationId,
        String principalName,
        long expectedVersion,
        OAuth2AuthorizedClient newClient);

    /**
     * Deletes only the exact version that failed.
     */
    boolean compareAndRemove(
        String registrationId,
        String principalName,
        long expectedVersion);

    record VersionedClient(
        OAuth2AuthorizedClient client,
        long version) {
    }
}
~~~

This is an **application-defined interface**, not a built-in API on <code>OAuth2AuthorizedClientService</code>.

A JDBC implementation can run <code>UPDATE ... WHERE version = ?</code> and verify <code>rowsUpdated == 1</code>.

If <code>compareAndSave(...)</code> returns <code>false</code>:

1. Never overwrite tokens with the older result.
2. Reload the latest state.
3. Check whether the newer token is already valid for the request.
4. If not, classify the error and run recovery; never automatically reuse the old refresh token.

### 13.1. CAS when the row does not yet exist

There is no row to update with <code>WHERE version</code> if the authorized client has never been saved. In practice, handle creation via:

- <code>INSERT</code> with unique key <code>(registrationId, principalName)</code>.
- On duplicate key, reload and apply CAS.
- Avoid unconditional <code>UPSERT</code> that lets an older writer clobber a newer token.

"Initial creation" and "refreshing an existing record" are two distinct state transitions. Particularly during Authorization Code callbacks, a user can start two parallel logins; define a policy for which new authorized client may replace an older one.

### 13.2. CAS and encryption

The token store should encrypt sensitive fields; keeping `version` in metadata reveals no token values. At write time:

~~~text
read version=7
refresh using R0
encrypt A1/R1
CAS version 7 -> 8, atomic row update
~~~

Never log token values directly in SQL logs; use bind parameters and audit driver/ORM logging settings. Systems storing ciphertexts must still protect encryption keys and backups.

## 14. Spring Security Failure Handlers and Risk of Deleting Fresh Tokens

Some managers default to specific refresh error handling, such as removing the authorized client after an <code>invalid_grant</code>. Exact behavior depends on the manager, version, and configuration.

In multi-instance environments, examine:

~~~text
A: refresh R0 succeeds, saves A1/R1
B: refresh R0 fails invalid_grant
B: removeAuthorizedClient(company, user-123)
~~~

If B removes unconditionally by key, A1/R1 can be deleted.

### 14.1. Conditional removal

A safer policy:

~~~text
if invalid_grant error:
    re-read authorized client
    if current.version != version of the failing refresh request:
        do not delete the newer state
    else:
        compareAndRemove(expectedVersion)
        mark as needing reauthorization
~~~

Key point: **delete the failing state**, not every version under that key.

If the Authorization Server detected refresh token reuse and invalidated the token family, the newer A1/R1 may also be compromised/invalidated. You cannot conclude it is valid solely because the database has a newer version. Use OP behavior, subsequent token request responses, and recovery policies to decide whether the user must re-login.

### 14.2. Do not treat all errors as `invalid_grant`

Timeouts, DNS, TLS, HTTP 429, or HTTP 503 do not mean the same thing as <code>invalid_grant</code>. Deleting authorized clients on every transport error can force many users to log in again simply because the OP had a brief outage.

Classify errors:

| Error type | What can be inferred | Resolution |
|---|---|---|
| <code>invalid_grant</code> at Token Endpoint | Refresh token/grant rejected | Check races, rotation, revocation, reauthorization |
| <code>invalid_client</code> | Client authentication failed | Check secret/credentials/registration |
| HTTP 429 | Provider rate-limiting | Back off, reduce refresh frequency |
| HTTP 5xx | OP/gateway error | Bounded retries, circuit breaker |
| Timeout after sending refresh | Uncertain whether OP processed request | Never blindly reuse R0 |
| Storage CAS conflict | Concurrent update occurred | Reload state; do not overwrite |
| Lock timeout | Another node may be refreshing | Wait/reload or return transient error |

### 14.3. Uncertain refresh outcomes

Suppose A sends R0 and the OP rotates to R1, yet the response is lost on the network. Local storage still holds R0. If A or B immediately retries with R0, the OP may treat it as reuse.

There is no generic way for a Client to **reconstruct R1** if it never received R1.

Remediation depends on the provider:

- If the OP offers idempotency or grace-window semantics, follow that contract.
- If the OP does not, mark the authorized client as needing reauthorization when refreshing stops working.
- For user-facing OIDC Login, prompt the user through a fresh Authorization Code Flow when needed.
- You may continue using the still-valid old access token for requests not needing a refresh if policy permits, yet never treat the refresh as having succeeded.

## 15. On-Demand Refresh vs. Proactive Refresh

There are two ways to trigger refreshes.

### 15.1. On-demand

Right when an HTTP request prepares to call a Resource Server, the manager checks the access token and refreshes if it is nearing expiration.

Advantages:

- Does not request new tokens when users are inactive.
- Ties refreshes directly to real demand.

Risks:

- Many requests arriving near token expiry can create bursts.
- Users wait on the token endpoint response.
- During an OP outage, many user requests can fail at once.

### 15.2. Proactive refresh

A background task proactively scans authorized clients nearing expiration and refreshes before user requests arrive.

Advantages:

- Lowers latency for the first request after expiry.
- Allows rate control and scheduled distribution of work.

Risks:

- Refreshes tokens that may no longer be needed, adding OP load.
- Multiple replicas running the same scheduler without distributed coordination.
- Easily races with on-demand refreshes if both touch the same key.
- Extends refresh token active usage per policy, raising secret-governance and revocation requirements.

**Important:** if an application uses both proactive and on-demand refreshes, both must share **the same coordinator, lock key, and storage versioning**. Never lock only the scheduler while allowing web requests to refresh outside the lock.

### 15.3. Jitter reduces bursts without replacing locks

When thousands of authorized clients expire together, refreshing in unison can hit rate limits. Smooth load with **jitter** and batched scheduling:

~~~text
target refresh time = expiresAt - safetyMargin - randomJitter
~~~

However, jitter only lowers the probability of workloads colliding at the exact same instant; it **does not guarantee single-flight for a single authorized client**. Per-key coordination is still required when token reuse must be prevented.

## 16. Token Store, Sessions, and Multi-Instance

A Servlet OIDC Login application may have:

~~~text
HTTP Session / SecurityContext:
    user is authenticated

OAuth2AuthorizedClientService:
    issued tokens bound to principal/registration

AuthorizationRequestRepository:
    state/PKCE awaiting callback (short-lived)
~~~

These are three different kinds of data with distinct lifecycles.

Using Spring Session/Redis to share HTTP sessions **does not automatically mean** <code>OAuth2AuthorizedClientService</code> also uses Redis. If the service is still <code>InMemoryOAuth2AuthorizedClientService</code>, each instance has isolated token state.

Conversely, using a shared JDBC authorized-client service does not automatically share HTTP sessions or make OIDC callbacks work across every node.

### 16.1. When is a shared token store needed?

A shared store is typically needed when:

- Multiple instances serve requests for one principal and must see newly updated tokens.
- Tokens must survive restarts.
- Dedicated workers refresh tokens on behalf of web nodes.
- Centralized revocation/cleanup is desired.

If each node handles a disjoint set of principals independently without token roaming, other designs may fit. The key is **explicit ownership**; never let instances accidentally share a refresh token without coordination.

### 16.2. Multi-tenant isolation

In a multi-tenant system:

~~~text
tenant-a / registration=company / principal=user-123
tenant-b / registration=company / principal=user-123
~~~

If these two identities are not the same user, both storage keys and lock keys must separate them. The OIDC <code>(iss, sub)</code> pair or a unique internal principal key can form the foundation, depending on design.

Never rely on browser-supplied email addresses or unvalidated <code>tenant</code>/<code>principal</code> parameters to select a refresh token.

## 17. Security When Coordinating Refreshes

Placing tokens in a shared store raises data-protection requirements.

### 17.1. Protecting tokens and databases

- Persist access/refresh tokens only when genuinely needed.
- Encrypt sensitive data at rest and manage keys securely.
- Use TLS to the database, Redis, Authorization Server, and APIs.
- Restrict which service accounts can read/write the authorized-client table.
- Avoid granting broad SQL access over the entire token store to components needing only one workload.
- Protect backups, snapshots, and database logs from token exposure.
- Enforce token-deletion policies on logout, provider unlink, permission revocation, or end of lifecycle.

### 17.2. Never log credentials in race traces

Avoid logging:

- <code>accessToken.getTokenValue()</code>.
- <code>refreshToken.getTokenValue()</code>.
- Client secrets or HTTP <code>Authorization</code> headers.
- Authorization codes, PKCE verifiers, or real nonces/states.
- Raw token responses.
- SQL bind parameters containing ciphertexts or tokens.

Log safer diagnostics instead:

~~~text
registrationId=company
principalKeyHash=...
refreshLockAcquired=true
storageVersionBefore=7
storageVersionAfter=8
refreshOutcome=success
refreshDurationMs=430
~~~

Even principal hashes and registration IDs must follow organizational telemetry policies. Never attach raw Token Endpoint exception messages as metric labels.

### 17.3. Useful metrics

| Metric | Meaning |
|---|---|
| <code>oauth2_refresh_attempt_total</code> | Number of refreshes actually sent to the OP |
| <code>oauth2_refresh_success_total</code> | Number of successful refreshes |
| <code>oauth2_refresh_failure_total{kind}</code> | Normalized failure categories |
| <code>oauth2_refresh_lock_wait_ms</code> | Lock acquisition wait time |
| <code>oauth2_refresh_lock_timeout_total</code> | Number of lock acquisition failures |
| <code>oauth2_refresh_cas_conflict_total</code> | Number of storage update conflicts |
| <code>oauth2_refresh_stale_writer_rejected_total</code> | Writes rejected by version/fencing |
| <code>oauth2_refresh_reauthorization_required_total</code> | Count of flows needing re-authorization |

Never use token values or raw `principalName` as metric labels; doing so leaks data and explodes cardinality.

## 18. Choosing Solutions by System Scale

### 18.1. Small, single-node application

You can use <code>OAuth2AuthorizedClientManager</code> with an appropriate store. Even on one node, multiple threads run concurrently, so if the provider enforces strict rotation, still consider **in-JVM** per-key single-flight or a unified coordinator.

If you plan to scale out, introduce the coordinator abstraction early so a local mutex can later be swapped for a distributed lock without rewriting every controller.

### 18.2. Multiple nodes, moderate traffic

A generally sound strategy:

1. Use shared authorized-client storage.
2. Lock by <code>(registrationId, principalKey)</code>.
3. Re-read the record after acquiring the lock.
4. Refresh only if the token still needs refreshing.
5. Atomically update both access and refresh tokens.
6. Guard saves/removes with CAS/versioning in case locks expire.
7. Set bounded timeouts and collect metrics.

### 18.3. Large systems with multiple providers/tenants

You can evolve toward:

- A single-writer refresh service or queues partitioned by authorized-client key.
- A dedicated token vault/service with versioning and auditing.
- Per-provider rate limiters and token request budgets.
- Distributed locks with fencing tokens and lease renewal.
- Batched proactive refreshes prioritizing active authorized clients.
- Automated revocation/reauthorization policies based on error type and provider capability.

These options increase operational overhead—do not adopt all of them prematurely if your system does not need them. Aim for **consistency calibrated to the Authorization Server's rotation/reuse characteristics**.

## 19. Common Design Pitfalls

| Flawed design | Why it fails | Fix |
|---|---|---|
| Using <code>synchronized</code> thinking it locks the cluster | Locks only within one JVM | Distributed lock/coordinator or single writer |
| Using JDBC service and assuming races are solved | Shared DB does not stop two nodes from calling the OP together | Per-key lock + re-read |
| Using CAS without locking before HTTP refresh | Two nodes can still send R0 to the OP | Coordinate before the Token Endpoint |
| Acquiring lock then using pre-lock token snapshot | Snapshot may already be stale | Re-read token after acquiring lock |
| Releasing lock without checking owner | Old node can delete new node's lock | Owner-checked atomic release |
| Unbounded lock lease | A crash can hang the lock forever | Bounded lease/timeout/renewal + recovery |
| Trusting lock alone without CAS/fencing | Lease can expire before writing | Conditional storage updates |
| Saving access and refresh tokens in two commits | Inconsistent intermediate states visible | Atomic update of the entire token pair |
| Unconditionally deleting authorized client after <code>invalid_grant</code> | Can delete fresh token saved by another node | Version-conditional delete |
| Retrying R0 immediately after timeout | OP may have already consumed R0 | Classify uncertain outcomes |
| Forcing logout on every error | 5xx/timeouts do not prove token revocation | Classify errors and recovery paths |
| Single global lock | User A blocks User B | Lock per authorized-client key |
| Principal key changes per request | Breaks consistent state sharing | Stable trusted principal key |
| Logging refresh tokens for comparison | Exposes credentials | Safe versioning/fingerprinting |
| Locking only the proactive job while web requests refresh freely | Two code paths still contend | Shared coordinator for all writers |

## 20. Troubleshooting Production Incidents

When <code>invalid_grant</code> suddenly spikes after scaling from 1 to multiple replicas:

1. **Identify the grant:** did the error occur in a refresh token grant or an authorization code/other endpoint call?
2. **Identify provider policy:** does the OP enforce refresh token rotation, reuse detection, grace periods, or token family revocation?
3. **Check instance count and timing:** did two requests for the same principal/registration hit near token expiry?
4. **Compare storage versions:** did two nodes read the same version and refresh token state?
5. **Inspect locking:** is there a real shared lock, stable key, owner-checked release, and sensible lease?
6. **Check re-reads:** after acquiring the lock, did node B reload fresh state or use an old snapshot?
7. **Inspect writes/deletes:** did a success/failure handler unconditionally update/delete after the version changed?
8. **Check timeouts:** could a prior refresh request have been processed by the OP even though the Client missed the response?
9. **Check downstream:** are API 401s due to expired tokens, wrong audiences, or provider revocation?
10. **Check recovery:** does the app prompt for reauthorization cleanly, or loop infinitely with the failing refresh token?

Isolation flow:

~~~text
Multiple instances see access token nearing expiry?
    |
    v
Do all code paths use the same coordinator?
    |--- No ---> add shared single-flight
    |
    v
Do callers reload after acquiring the lock?
    |--- No ---> stop using stale refresh tokens
    |
    v
Do storage saves/removes use CAS/fencing?
    |--- No ---> prevent stale updates/deletes
    |
    v
What is the provider's rotation/reuse policy?
    |
    +--- Refresh succeeds ---> atomic save A1/R1
    |
    +--- invalid_grant ------> triage race vs. revocation
    |
    +--- timeout ------------> uncertain outcome state
    |
    v
Retry/re-login and emit metrics per policy
~~~

Never collect raw refresh tokens to investigate. Internal correlation IDs, versions, sanitized timestamps, provider registration IDs, and error categories suffice.

## 21. Practice Exercises and Scenarios

### Exercise 1 — Two nodes using the same refresh token

~~~text
A reads: version=5, refresh=R0
B reads: version=5, refresh=R0
A calls OP and receives A1/R1
B calls OP with R0 and receives invalid_grant
~~~

**Question:** Does simply switching storage from memory to a database fix the root cause?

**Answer:** No. A database lets both nodes see the same state, yet does not stop them from both sending R0. You need coordination before calling the OP, re-reading after acquiring the lock, and protecting writes with CAS/fencing.

### Exercise 2 — Reloading after lock

B waits 2 seconds for the lock. Meanwhile A saves version 6 with A1/R1. B acquires the lock, yet still holds the old version 5 object.

**Question:** Should B refresh R0 from the version 5 object?

**Answer:** No. B must reload the latest authorized client from shared storage. If A1 is usable, B uses A1 and skips refreshing.

### Exercise 3 — CAS conflict

A and B both try to update version 7. A updates to version 8; B executes:

~~~sql
UPDATE oauth2_authorized_client_state
SET version = 8
WHERE registration_id = 'company'
  AND principal_name = 'user-123'
  AND version = 7;
~~~

and gets 0 rows updated.

**Question:** May B drop the version condition to force the write?

**Answer:** No. A concurrent modification occurred. B must reload state; if a newer authorized client exists, use/evaluate it. Dropping the version condition reintroduces lost updates.

### Exercise 4 — Accidentally deleting a newer token

A saves version 8 with R1. B gets <code>invalid_grant</code> on R0 and calls <code>removeAuthorizedClient(registration, principal)</code> unconditionally.

**Question:** What is the risk and what should be done?

**Answer:** B can delete the new R1 record. Delete conditionally on the version that failed; if the current version differs, do not delete. Also check whether the OP revoked the entire token family upon detecting R0 reuse.

### Exercise 5 — Lock expiration

A acquires a 10-second lock; the Token Endpoint takes 12 seconds. B acquires the lock after 10 seconds and starts refreshing.

**Question:** Why is a simple distributed lock not enough?

**Answer:** Lease expiry lets two nodes process concurrently. You need proper timeouts/renewal, owner checks, storage fencing, and recovery design. Fencing cannot recall a request already sent to the OP, so lock leases and pre-HTTP coordination must be tuned carefully.

### Exercise 6 — CAS without locking

Two nodes both read version 12 and both call the OP with R0. Only one updates the database thanks to CAS.

**Question:** Is this safe with an OP that enables reuse detection?

**Answer:** Not yet. CAS prevents lost updates in the DB, yet the OP still sees R0 used twice. Single-flight before refreshing is what reduces reuse risk.

### Exercise 7 — Timeout after refresh

The Client sends R0, hits a read timeout, and receives no token response.

**Question:** Can you be certain R0 was not consumed?

**Answer:** No. The OP may have processed it and issued R1 while the response was lost. Never continuously retry R0; follow provider policy, bounded retries only when safe, and reauthorization when unrecoverable.

### Exercise 8 — Multi-tenant

Issuers A and B both have subject <code>123</code>. The system uses a single token store and lock key <code>oauth2-refresh:123</code>.

**Question:** What is the bug?

**Answer:** The two identities collide on locks and storage. Keys must be partitioned by registration and a trusted principal namespace, including issuer/tenant if needed. Never treat matching subjects across issuers as the same person.

### Exercise 9 — Proactive and on-demand

A scheduler refreshes tokens before expiry, while a web controller uses a separate manager and can refresh directly.

**Question:** Is placing a distributed lock only in the scheduler enough?

**Answer:** No. The controller can reuse R0 concurrently. Every path refreshing the same authorized client must share the same coordination mechanism and conditional writes.

### Exercise 10 — Designing a solution for a three-replica system

Design a system with:

1. Shared authorized-client store with <code>version</code> and atomic updates of the token pair.
2. Stable keys derived from <code>(registrationId, trustedPrincipalKey)</code>.
3. Distributed lock with lease, owner-checked release, and stale-writer protection.
4. Re-reading the authorized client after acquiring the lock.
5. Refreshing only if the token still needs refreshing.
6. CAS saves/removes handling version conflicts.
7. Classification of <code>invalid_grant</code>, timeouts, 429, 5xx, and reauthorization paths.
8. Metrics for lock wait, refresh success/failure, CAS conflicts, and token request rate.
9. Cleanup policies on logout or authorization revocation.
10. Protection of token values, secrets, SQL logging, and telemetry.

Explain what happens if a node crashes **before** the Token Endpoint, **after** OP refresh but **before** DB save, and **after** DB save but **before** releasing the lock.

## 22. Key Takeaways

- When multiple instances share an authorized client, **refresh token rotation can cause two nodes to reuse R0 and trigger <code>invalid_grant</code> or reuse detection**.
- <code>OAuth2AuthorizedClientManager</code> and the JDBC service **do not provide distributed single-flight refresh by default**. Shared storage is only one piece of the architecture.
- **Per-key distributed locks** help curb duplicate refreshes. **Re-reading after acquiring the lock** is mandatory to avoid using stale snapshots.
- **CAS/versioning** protects storage from lost updates; **fencing** rejects stale writers after lock ownership changes. CAS alone cannot prevent R0 from being sent twice to the OP.
- Access tokens and refresh tokens must be **updated atomically as a pair**, especially when the OP issues a new refresh token.
- A failure handler after <code>invalid_grant</code> must not **unconditionally delete** the authorized client for that key, because another instance may have just saved a newer version.
- Timeouts after sending a refresh token create an **uncertain outcome**: the OP may have consumed the token even if the Client never got the response. Never blindly retry R0.
- Every code path (web, API, scheduler, proactive refresh) sharing an authorized client must pass through **the same coordination policy**.
- Protect token storage, principal namespaces, TLS, secrets, and logs; monitor lock waits, refresh failures, and CAS conflicts to spot races in production.

### References

- **Spring Security Reference — OAuth2 Client:** <code>OAuth2AuthorizedClientManager</code>, authorized client persistence, and the refresh token provider.
- **Spring Security Java API:** <code>OAuth2AuthorizedClient</code>, <code>OAuth2AuthorizedClientService</code>, <code>OAuth2AuthorizedClientRepository</code>, and <code>OAuth2AuthorizedClientProviderBuilder</code>.
- **Spring Security Java API:** <code>DefaultOAuth2AuthorizedClientManager</code>, <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code>, and authorization success/failure handlers.
- **RFC 6749 — The OAuth 2.0 Authorization Framework**, Section 6: Refreshing an Access Token.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** refresh token protection, rotation, and replay detection.
- **RFC 7009 — OAuth 2.0 Token Revocation:** revoking tokens at the Authorization Server.
- **OpenID Connect Core 1.0:** Authorization Code Flow, ID Token, and relationship to OAuth2 token responses.
- **Documentation of your Authorization Server:** refresh token rotation, reuse policies, grace periods, and token revocation semantics; these behaviors vary by provider.
