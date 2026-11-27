# Caching Clients, Authorizations, and Cache Invalidation Mechanisms

## 1. Context and Objectives

In an **OAuth 2.0/OpenID Connect Authorization Server** built with **Spring Security**, **Spring Authorization Server**, and **Spring Boot**, protocol endpoints repeatedly read the same data: client configurations, issued authorizations, and user consents. As request volume grows, querying the database on every client authentication, introspection, token refresh, or authorization request can introduce significant latency and I/O load.

Caching reduces reads against the persistence store, but Authorization Server data differs from ordinary catalog or reference-data caches. A small state change can alter access permissions:

- A client is disabled or its secret is rotated.
- A client's redirect URIs, grant types, authentication methods, or scopes are updated.
- An access token or refresh token is revoked.
- Refresh token rotation invalidates the old token and issues a new one.
- A user withdraws consent granted to a client.

If a cache serves stale entries after the database updates, the Authorization Server might keep accepting an old client secret, report a revoked token as active during introspection, or ignore that a user just withdrew consent. Therefore, caching must be designed alongside synchronization and invalidation mechanisms.

Running example: an Authorization Server at `https://auth.example.com` runs three instances behind a load balancer. Instance A handles a refresh token request; instance B handles introspection; instance C handles an authorization request. All three share one database, while each keeps a local Caffeine cache. When instance A revokes a token, caches on B and C must also reflect the change according to a consistent policy.

After this lesson, you will be able to:

1. Distinguish the data managed by `RegisteredClientRepository`, `OAuth2AuthorizationService`, and `OAuth2AuthorizationConsentService`.
2. Decide which data is appropriate to cache, which cache keys to use, and what conditions should govern TTLs.
3. Build cache decorators for Spring Authorization Server's core services.
4. Invalidate caches whenever a client, authorization, or consent is saved, updated, or removed.
5. Handle token rotation, token revocation, and client secret changes.
6. Synchronize caches across multiple Authorization Server instances.
7. Use transaction after-commit callbacks, transactional outbox, and versioning to minimize cache inconsistency.
8. Distinguish eventual consistency from immediate revocation requirements.
9. Test stale caches, race conditions, duplicate events, and node disconnects.
10. Monitor cache hit ratios, evictions, invalidation lag, and impact on protocol endpoints.

**Version Scope:** This material references Spring Authorization Server 1.5.8, Spring Security 6.x, and Spring Framework 6.x. Spring Authorization Server supplies in-memory and JDBC repositories/services; this lesson shows how to wrap them with application-managed caching. No cache decorator is enabled by default for these three core services.

## 2. Three Data Groups to Cache

### 2.1. RegisteredClient

`RegisteredClientRepository` manages registered clients. Core APIs:

~~~java
RegisteredClient findById(String id);
RegisteredClient findByClientId(String clientId);
void save(RegisteredClient registeredClient);
~~~

A `RegisteredClient` holds the client ID, encoded client secret, authentication methods, grant types, redirect URIs, post-logout redirect URIs, scopes, client settings, and token settings.

This data is relatively stable compared to authorizations. A client may be read thousands of times while its metadata changes only a few times per day. Consequently, caching clients usually delivers strong gains.

Flows that read `RegisteredClient`:

- Client authentication at the Token Endpoint.
- Authorization Code Flow and other grants.
- Token introspection/revocation when identifying the client.
- OIDC Dynamic Client Registration and Client Configuration.
- Consent handling and client-related metadata discovery.

The cache must support both lookup keys: internal ID and client ID. Caching only by client ID leaves `findById` hitting the database; caching only by internal ID leaves client authentication lookups missing the cache.

### 2.2. OAuth2Authorization

`OAuth2AuthorizationService` manages granted authorizations. Core APIs:

~~~java
void save(OAuth2Authorization authorization);
void remove(OAuth2Authorization authorization);
OAuth2Authorization findById(String id);
OAuth2Authorization findByToken(
    String token,
    OAuth2TokenType tokenType
);
~~~

An `OAuth2Authorization` can hold multiple tokens depending on the grant type:

- Authorization Code Flow: authorization code, access token, and possibly a refresh token.
- OIDC Authorization Code Flow: authorization code, ID Token, access token, and possibly a refresh token.
- Client Credentials: access token.
- Device Authorization Flow: device code, user code, and related state.

Authorizations also hold the principal, internal client ID, grant type, scopes, attributes, and metadata. Token status changes when a token expires or is invalidated. `OAuth2Authorization.Token` provides `isExpired()`, `isInvalidated()`, and `isActive()`.

This is the most sensitive group for caching. If a cache holds a pre-revocation authorization, introspection may report the token as still active. If a cache serves an outdated snapshot after refresh rotation, the old token may still resolve or the new token may not be recognized.

### 2.3. OAuth2AuthorizationConsent

`OAuth2AuthorizationConsentService` manages consent keyed by `RegisteredClient` ID and principal name:

~~~java
OAuth2AuthorizationConsent findById(
    String registeredClientId,
    String principalName
);

void save(OAuth2AuthorizationConsent authorizationConsent);
void remove(OAuth2AuthorizationConsent authorizationConsent);
~~~

Consent holds the authorities granted by the resource owner to the client. An authority can represent a scope, claim, permission, or role.

The cache key must include both `registeredClientId` and `principalName`. Keying solely by client ID risks returning one user's consent for another user.

### 2.4. Comparing the Three Cache Groups

| Group | Lookup Keys | Change Frequency | Risk When Stale |
| --- | --- | --- | --- |
| RegisteredClient | ID and client ID | Low to medium | Accepts old secret, disabled client remains usable, stale redirect/grant metadata stays in effect. |
| OAuth2Authorization | Authorization ID, token value, and token type | High | Revoked tokens may still appear active; token rotation is not reflected. |
| OAuth2AuthorizationConsent | RegisteredClient ID + principal name | Medium | Withdrawn permissions may still be treated as consented. |

Do not apply the same TTL, cache keys, or invalidation policy across all three groups.

## 3. Where Does Caching Sit in the Architecture?

### 3.1. Cache Decorators Around Core Services

Spring Authorization Server accesses core services through interfaces. You can place a decorator between the protocol endpoints and the persistence implementation:

~~~mermaid
flowchart TD
    A["Authorization / Token / Introspection Endpoints"] --> B["RegisteredClientRepository"]
    A --> C["OAuth2AuthorizationService"]
    A --> D["OAuth2AuthorizationConsentService"]
    B --> E["Cache Decorator"]
    C --> F["Cache Decorator"]
    D --> G["Cache Decorator"]
    E --> H["JDBC / JPA Repository"]
    F --> I["JDBC / JPA Authorization Store"]
    G --> J["JDBC / JPA Consent Store"]
    H --> K[("Database")]
    I --> K
    J --> K
~~~

Decorators preserve interface contracts and delegate read/write operations to the underlying implementation. This keeps protocol endpoints unaware of whether caching uses Caffeine, Redis, or another distributed cache.

### 3.2. Do Not Confuse InMemory Services with Caches

Spring Authorization Server provides `InMemoryRegisteredClientRepository`, `InMemoryOAuth2AuthorizationService`, and `InMemoryOAuth2AuthorizationConsentService`. These implementations store data directly in memory and suit development/testing per framework docs.

They are not caches sitting in front of JDBC persistence. If one instance uses an `InMemory` service and another uses JDBC, the two instances do not share state. Across restarts or scale-outs, in-memory data does not synchronize automatically.

In production, caching is typically an extra layer in front of a persistent repository/service. The database or durable store remains the primary source of truth.

### 3.3. Local Cache vs. Distributed Cache

| Cache Type | Example | Advantages | Limitations |
| --- | --- | --- | --- |
| Local in-process | Caffeine | Low latency, no network hop, reduces database load. | Each instance holds its own cache; invalidation must reach every node. |
| Distributed cache | Redis | Instances share one cache namespace. | Adds a network hop, depends on cache cluster, still requires coordinating races with DB transactions. |
| Hybrid | Caffeine + Redis | Fast local reads, Redis shares state. | Higher complexity; must manage two cache tiers and invalidate both. |

With a local cache, invalidation events must reach every node. With a distributed cache, deleting one key affects every node reading that key, yet cached data can still go stale if database writes and cache updates are not properly coordinated.

## 4. Designing Cache Keys

### 4.1. Separate Namespaces per Data Type

Never share a single key space across different domain objects. For example:

~~~text
client:{tenant}:{issuer}:id:{registeredClientId}
client:{tenant}:{issuer}:client-id:{clientId}

authorization:{tenant}:{issuer}:id:{authorizationId}
authorization:{tenant}:{issuer}:token:{tokenType}:{tokenDigest}
authorization:{tenant}:{issuer}:token:ANY:{tokenDigest}

consent:{tenant}:{issuer}:{registeredClientId}:{principalName}
~~~

If a system serves multiple tenants or multiple issuers, tenant/issuer must appear in the cache namespace. Otherwise, two Authorization Servers sharing client IDs or authorization IDs could read each other's entries.

### 4.2. Never Use Raw Bearer Tokens as Cache Keys

Token values are credentials. Using raw tokens directly as keys exposes them in Redis key listings, monitoring, cache diagnostic dumps, cache client logs, and snapshots/backups.

Use HMAC-SHA-256 with an application-managed secret key:

~~~java
String tokenCacheKey(
        SecretKey lookupKey,
        String tokenType,
        String token) throws GeneralSecurityException {

    Mac mac = Mac.getInstance("HmacSHA256");
    mac.init(lookupKey);
    mac.update(tokenType.getBytes(StandardCharsets.UTF_8));
    mac.update((byte) 0);
    byte[] digest = mac.doFinal(
        token.getBytes(StandardCharsets.UTF_8));

    return HexFormat.of().formatHex(digest);
}
~~~

The `tokenType` component provides domain separation: the same string in two different token types yields two distinct cache keys. For `tokenType=null` lookups, use a dedicated `ANY` namespace. Never store the HMAC key in the cache database, event payloads, or source code; manage it via a secret manager/KMS.

### 4.3. Consent Keys Must Include Both Client and Principal

Caching consent by composite key can use a structured key object in a local cache or canonical encoding in a distributed cache. Example:

~~~java
record ConsentCacheKey(
    String registeredClientId,
    String principalName
) {}
~~~

If string keys are required, encode each component with safe delimiters or use a digest; never concatenate two strings with `:` if identifiers can contain `:` unescaped. The principal name must use the exact canonical form used by the persistence service; do not lowercase or normalize automatically if the system is case-sensitive.

### 4.4. Keys Must Be Deterministic Across Instances

When using distributed caches or cross-instance invalidation events, every node must compute the exact same cache key from the same inputs. Never use:

- Object identity hashes.
- Random UUIDs for cache lookups.
- Class-version-dependent Java serialization as keys.
- Hash codes that are not deterministic across processes.

Use canonical string/byte encodings and version the namespace when key formats change.

## 5. Caching RegisteredClient

### 5.1. Bidirectional Lookup Caching

`RegisteredClientRepository` has two read methods:

- `findById(id)`.
- `findByClientId(clientId)`.

You can maintain two cache aliases pointing to the same immutable `RegisteredClient` snapshot:

~~~java
RegisteredClient findById(String id) {
    return byId.get(id, () -> {
        RegisteredClient client = delegate.findById(id);
        if (client != null) {
            byClientId.put(client.getClientId(), client);
        }
        return client;
    });
}

RegisteredClient findByClientId(String clientId) {
    return byClientId.get(clientId, () -> {
        RegisteredClient client =
            delegate.findByClientId(clientId);
        if (client != null) {
            byId.put(client.getId(), client);
        }
        return client;
    });
}
~~~

This pseudocode illustrates a cache decorator; `byId` and `byClientId` are application-configured cache abstractions, and `delegate` is the underlying `RegisteredClientRepository`.

### 5.2. Invalidate Both Aliases on Save

When updating a client:

1. Read the old record to capture the previous client ID if metadata allows renaming it.
2. Write the new record via the delegate.
3. After the transaction commits, evict the key by internal ID.
4. Evict both the old client ID alias and the new client ID alias.
5. Publish an invalidation event so other instances clear the same namespace.

Evicting only `byId` leaves `byClientId` serving stale data. If `clientId` changed and only the new ID is evicted, the old alias lingers.

### 5.3. Which Changes Require Invalidation?

Any change affecting protocol behavior must refresh the cache:

- Client secret or secret expiration.
- Client authentication methods and authentication algorithms.
- Authorization grant types.
- Redirect URIs and post-logout redirect URIs.
- Permitted scopes.
- PKCE/consent requirements in `ClientSettings`.
- Access token/refresh token settings.
- Enabled/disabled status if the application models it.

In particular, when rotating a client secret, instances must not keep accepting the old secret longer than the consistency policy allows.

### 5.4. Caching Secrets and Sensitive Data

`RegisteredClient` can contain an encoded client secret. The `RegisteredClientRepository` Javadoc states that sensitive information such as the client secret must be encoded outside the repository implementation.

Caching does not replace `PasswordEncoder`. Never store plaintext secrets, never log full `RegisteredClient` objects, never put secrets into metric labels, and restrict access to cache snapshots. When rotating secrets, evict the old entry after commit.

## 6. Caching OAuth2Authorization

### 6.1. Caching by Authorization ID

`findById(id)` can be cached by authorization ID. The cached value is an `OAuth2Authorization` snapshot:

~~~java
OAuth2Authorization findById(String id) {
    return authorizationById.get(
        id,
        () -> delegate.findById(id));
}
~~~

Never mutate cached objects directly. When updating token metadata or invalidated state, create a new object via the framework's builder/copy mechanism and call `save`. If custom attributes inside contain mutable objects, ensure snapshots cannot be mutated outside the persistence flow.

### 6.2. Caching by Token Value and Token Type

`findByToken(token, tokenType)` can be cached by token digest:

~~~text
authorization:token:access_token:{digest}
authorization:token:refresh_token:{digest}
authorization:token:code:{digest}
authorization:token:id_token:{digest}
authorization:token:user_code:{digest}
authorization:token:device_code:{digest}
authorization:token:ANY:{digest}
~~~

The cache can store either the full authorization snapshot or the authorization ID. If storing the ID, the next read needs a cache hit by ID to avoid hitting the database. If storing the snapshot directly, every alias must be evicted whenever the authorization changes.

The `tokenType=null` case requires searching across all token types supported by the implementation. Never cache an `ANY` result as equivalent to an access token. When an authorization changes, evict both typed keys and `ANY` keys for all associated token values.

### 6.3. Enumerating Token Aliases to Evict

An authorization can contain multiple tokens. On updates, the cache decorator must know both old and new tokens. You can create a persistence-layer helper to extract:

- Authorization code.
- Access token.
- Refresh token.
- OIDC ID Token.
- User code.
- Device code.
- `state` if the implementation allows state lookups via `findByToken`.

`OAuth2Authorization` provides accessors such as `getAccessToken()`, `getRefreshToken()`, and `getToken(Class)`. The helper must cover all token types stored/queried by the service, not just access tokens.

Token-based cache lookups can follow the same loader pattern:

~~~java
OAuth2Authorization findByToken(
        String token, OAuth2TokenType tokenType) {

    String key = tokenKeyFactory.create(token, tokenType);
    return byToken.get(
        key,
        () -> delegate.findByToken(token, tokenType));
}
~~~

`tokenKeyFactory` must use an HMAC digest and create a separate `ANY` namespace when `tokenType` is `null`. This example never puts raw tokens in keys. Ensure cache entries are evicted when the authorization changes, even when token values stay the same while invalidated metadata changes.

### 6.4. Invalidation on Save

When `save(authorization)` updates an existing authorization ID, any of these may happen:

- A token value stays the same while its invalidated flag changes.
- An old refresh token is invalidated and a new one is added.
- An authorization code is marked consumed.
- Claims/metadata are updated.
- Device/user codes change state.

Therefore, evicting only by authorization ID is insufficient if `findByToken` maintains separate alias caches. Evict all token keys from both the old snapshot and the new snapshot.

A safe write workflow:

1. Read the old authorization inside the same transaction or fetch token keys from a reliable reverse index.
2. Write the new authorization to the durable store.
3. Build an invalidation event containing the authorization ID, version, and fingerprints of old/new token aliases.
4. Write the event to the outbox in the same transaction.
5. After commit, evict the local cache.
6. Remaining nodes process the event and evict their caches accordingly.

Pseudocode for the write path:

~~~java
@Transactional
public void save(OAuth2Authorization next) {
    OAuth2Authorization previous =
        delegate.findById(next.getId());

    delegate.save(next);

    long version = versionRepository.nextVersion(next.getId());
    Set<String> oldKeys = tokenKeyFactory.keysFor(previous);
    Set<String> newKeys = tokenKeyFactory.keysFor(next);

    outbox.append(AuthorizationChanged.of(
        next.getId(), version, oldKeys, newKeys));

    afterCommit(() -> {
        authorizationById.evict(next.getId());
        oldKeys.forEach(byToken::evict);
        newKeys.forEach(byToken::evict);
    });
}
~~~

`delegate`, `versionRepository`, `tokenKeyFactory`, and `outbox` are application-supplied components. They must participate in the same transaction manager/database transaction; if the outbox writes to a separate database without distributed transactions, an equivalent reliability mechanism is needed. `keysFor` produces only fingerprints/HMAC cache keys and never places raw tokens into events. This snippet illustrates the idea; preserve semantics for every token type and state supported by your implementation.

### 6.5. Invalidation on Remove

`remove(authorization)` must evict:

- The cache entry by authorization ID.
- Cache entries for every token value and token type on the authorization.
- `ANY` alias cache entries for those tokens.
- Any reverse index storing the authorization's alias list.

Deleting only the database row while leaving token aliases in the cache allows `findByToken` to keep returning a deleted authorization.

### 6.6. Do Not Cache Active Status Independently for Too Long

`OAuth2Authorization.Token.isActive()` is computed from expiration and invalidated state. When caching the full authorization snapshot, expiration can still be evaluated at read time, yet invalidated state only changes when the snapshot is refreshed/evicted.

Never cache an `active=true` boolean with a TTL longer than the token lifetime or invalidation SLA. For introspection, once a token is revoked, results must reflect the new state per system policy.

## 7. Caching OAuth2AuthorizationConsent

### 7.1. Caching by Composite Key

Cache consent by:

~~~text
consent:{registeredClientId}:{principalName}
~~~

Keys must be safely encoded as covered in the cache key design section. The principal name must match the exact canonical form used by the persistence service; never lowercase or normalize automatically if the system is case-sensitive.

### 7.2. Invalidate on Save/Remove

Once `save(consent)` or `remove(consent)` completes:

- Evict the key for `(registeredClientId, principalName)`.
- Broadcast an event to other instances.
- If aggregate per-user or per-client views are cached, evict those dependent views too.

Consent determines which authorities a user approved. If a user withdraws consent, a stale cache could cause the next authorization request to skip the consent screen or continue granting withdrawn permissions.

### 7.3. Consent Caching Does Not Replace Authorization Revocation

Withdrawing consent and revoking issued authorizations/tokens are separate workflows. Removing consent prevents future authorization flows from relying on the old consent decision. Previously issued access tokens/refresh tokens may remain valid depending on policy.

If business requirements dictate that "withdrawing consent must invalidate all issued tokens," the workflow must:

1. Remove/update consent.
2. Locate related authorizations by client and principal.
3. Invalidate tokens per policy.
4. Emit invalidation events for authorization caches.
5. Report completion only after achieving the committed consistency guarantee.

Never assume `OAuth2AuthorizationConsentService.remove()` automatically deletes all related authorizations.

## 8. Cache-Aside, TTL, and Negative Caching

### 8.1. Cache-Aside

Cache-aside is a straightforward pattern:

1. Read cache.
2. On hit, return result.
3. On miss, read durable store.
4. Populate cache with result.
5. On writes, update durable store and invalidate cache.

~~~mermaid
flowchart TD
    A["Protocol endpoint needs data"] --> B["Read cache"]
    B --> C{"Cache hit?"}
    C -->|Yes| D["Return snapshot"]
    C -->|No| E["Read database"]
    E --> F["Put snapshot into cache"]
    F --> D
    G["save / remove"] --> H["Write durable store"]
    H --> I["Commit transaction"]
    I --> J["Evict local cache"]
    I --> K["Outbox event"]
    K --> L["Broadcast invalidation to nodes"]
~~~

Cache-aside is easy to implement, but races between cache fills and invalidations must be handled—especially when multiple nodes read and write concurrently.

### 8.2. TTL by Data Category

No single TTL fits every deployment. Choose TTLs based on update frequency and tolerable staleness:

| Data | Starting Reference TTL | Factors to Consider |
| --- | --- | --- |
| RegisteredClient | Tens of seconds to a few minutes | Client secret rotation, disabling, redirect/grant updates, and invalidation SLA. |
| Authorization by ID | A few seconds to shorter than token lifetime | Refresh/revocation frequency and introspection consistency. |
| Token lookup alias | Short, never exceeding token expiry | Revocation, rotation, cache size, and hit ratio. |
| Consent | Tens of seconds to a few minutes | SLA when users withdraw consent or admins alter permissions. |
| Negative lookup | Do not cache, or very short TTL | A client/token may have just been created right after a miss. |

These figures are only starting points for benchmarking. Production TTLs must derive from real workloads and security requirements rather than copying defaults from examples.

### 8.3. Bounding TTL by Token Expiry

For token lookup aliases, cache duration must never exceed the token's expiration time. If a token expires at `exp`, its cache entry must expire no later than `exp`.

However, expiry-based TTL does not handle revocation. A token can be invalidated before `exp`, so explicit invalidation or authoritative checks remain mandatory.

### 8.4. Negative Caching

Negative caching stores "not found" results. It can reduce database lookups when attackers flood random tokens, yet carries risks:

- A newly registered client continues returning not found from cache.
- A newly issued token hits a stale cache miss.
- Cache keys for unknown tokens grow unboundedly, causing memory pressure.
- Attackers can fill the cache with random tokens.

If negative caching is used:

- Keep TTLs very short.
- Enforce strict size bounds and eviction.
- Never store raw tokens.
- Invalidate negative keys when the corresponding client/token is created.
- Rate-limit not-found requests.

For Authorization Servers, it is usually best to avoid long negative caches for token and client lookups.

### 8.5. Preventing Cache Stampedes

When a key expires, many concurrent requests can miss simultaneously and query the database. Consider:

- Atomic get-with-loader/single-flight per cache key.
- TTL jitter to avoid synchronized expirations.
- Loader concurrency limits.
- Timeouts and bulkheads for database lookups.
- Never holding a global lock while querying the database.

Never allow a cache loader to call back into the same decorator in a way that causes recursion or deadlocks.

## 9. Cache Invalidation Mechanisms

### 9.1. Events to Emit

| Event | Cache Entries to Evict |
| --- | --- |
| `RegisteredClient` created | New client ID and internal ID. |
| `RegisteredClient` updated | Both old and new aliases; any client-dependent views. |
| Client secret rotated | Client aliases on every node; stop accepting the old secret. |
| Client disabled/deleted | Client aliases; related authorizations/consents per policy. |
| Authorization created | ID and new token aliases; clear matching negative caches if any. |
| Authorization updated | ID, old and new token aliases, both typed and `ANY`. |
| Authorization revoked | ID and all token aliases; introspection must observe invalidated state. |
| Authorization deleted | ID, all token aliases, and reverse index. |
| Refresh token rotated | Old and new refresh token aliases; related authorization aliases. |
| Consent granted/updated | Composite key of client + principal. |
| Consent withdrawn | Composite key and dependent aggregate views. |

### 9.2. Evict or Update Cache?

There are two options:

- **Evict:** remove the cache entry; the next read reloads from the database. Simple, with low risk of writing a stale snapshot.
- **Update:** replace the cache entry with the new snapshot after persistence commits. Reduces cache misses, yet requires exact object/version accuracy.

For authorizations and token status, eviction is usually safer because updates can easily miss a token alias or write a snapshot before transaction commit.

### 9.3. Eviction Must Happen After Commit

If eviction runs before the transaction commits, another request can:

1. Observe a cache miss.
2. Read the old version from the database because the write transaction has not committed yet.
3. Put that old version back into the cache.
4. Watch the original transaction commit without a second eviction.

The result is a stale cache despite a successful write transaction.

Therefore, local cache eviction must run after commit. When no transaction is active, evict immediately after delegate save/remove succeeds.

### 9.4. TransactionSynchronization afterCommit

A helper can register a callback:

~~~java
void afterCommit(Runnable invalidation) {
    if (!TransactionSynchronizationManager
            .isActualTransactionActive()) {
        invalidation.run();
        return;
    }

    if (!TransactionSynchronizationManager
            .isSynchronizationActive()) {
        throw new IllegalStateException(
            "Transaction synchronization is required");
    }

    TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                invalidation.run();
            }
        });
}
~~~

This example targets the local process. The callback evicts the cache only when the transaction commits successfully. On rollback, the callback does not execute.

If invalidation fails after commit, the database cannot roll back. Thus, an after-commit callback does not replace durable retries for cross-node invalidation.

## 10. Synchronizing Caches Across Multiple Authorization Server Instances

### 10.1. The Local Cache Problem

Suppose instances A and B both cache authorization `auth-100`. Instance A revokes the access token and commits to the database. If only A's cache is evicted, instance B can keep returning the stale snapshot and treating the token as active.

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Instance A
    participant DB as Database
    participant B as Instance B
    A->>DB: UPDATE authorization: token invalidated
    DB-->>A: Commit succeeded
    A->>A: Evict local cache
    B->>B: Cache still holds stale snapshot
    B->>B: Introspection reads stale authorization
    Note over A,B: Cross-instance invalidation event required
~~~

### 10.2. Plain Pub/Sub Can Drop Events

Redis Pub/Sub or non-durable broadcast messaging can lose messages when a consumer is offline or reconnecting. If an instance misses a revocation event, stale data persists until TTL expiration.

Pub/Sub can reduce latency, but should not be the sole invalidation mechanism for security-critical data.

### 10.3. Transactional Outbox

A transactional outbox stores invalidation events in the same database transaction as the data change:

1. Update the authorization/client/consent.
2. Insert a row into the outbox table in the same transaction.
3. Commit both together.
4. A publisher reads unsent outbox rows and emits events to the message broker.
5. Consumers on each instance evict their caches.
6. Mark events processed or advance consumer offsets.

Example event payload:

~~~json
{
  "eventId": "evt-92f1",
  "entityType": "authorization",
  "entityId": "auth-100",
  "version": 42,
  "tenant": "tenant-a",
  "evictKeys": [
    "authorization:tenant-a:id:auth-100",
    "authorization:tenant-a:token:access_token:<hmac-digest>"
  ]
}
~~~

Payloads contain only cache keys/fingerprints—never raw access tokens, refresh tokens, client secrets, or sensitive claims.

### 10.4. Events Must Be Idempotent and Versioned

Brokers can deliver duplicate or out-of-order events. Consumers should:

- Use `eventId` to recognize already-processed events.
- Carry a monotonically increasing version per entity.
- Ignore events older than the already-applied version.
- Treat eviction as idempotent; receiving the same event twice is safe.
- Retry when the cache is unavailable.

If version 43 arrives before version 42, the consumer must not let event 42 overwrite newer state/version. For eviction-only events, older events are generally safe to evict, yet versioning still prevents stale cache refills.

### 10.5. Preventing Races While a Cache Loader Is Running

Another race happens when node B is loading an old snapshot from the database while node A commits an update and sends an invalidation event to B:

1. B misses the cache and begins reading the old version.
2. A commits the new version and emits an event.
3. B receives the event and evicts its cache.
4. B finishes its stale query and writes the old snapshot into the cache after eviction.

One solution is generation/version fencing:

~~~java
long generationBefore = generations.current(key);
OAuth2Authorization loaded = delegate.findById(id);

if (generationBefore == generations.current(key)) {
    cache.put(key, loaded);
}
return loaded;
~~~

When a consumer receives an invalidation event, it increments the generation for that key/entity. If a loader started before the event and finishes afterward, the generation changed, so the loader must not populate the cache with the stale snapshot.

This is pseudocode. The generation store must be shared or updated consistently across the cache node scope; with distributed caches, you can use database/cache versions or compare-and-set.

### 10.6. Restarts and Broker Disconnections

When an instance restarts:

- Start with an empty local cache or a fresh generation namespace.
- Restore consumer offsets/replay events if the broker supports it.
- Do not load snapshots from disk without a way to verify versions.
- Monitor how long the consumer lags.

When a running node loses broker connectivity, clear its cache or catch up on events from the last offset before serving sensitive requests. If cache freshness cannot be verified, bypass the cache for operations needing current state.

## 11. Consistency and Immediate Revocation Requirements

### 11.1. Eventual Consistency

Outbox + broker + local cache typically yield eventual consistency. After a database commit, nodes receive invalidations after some delay.

This is acceptable when the system explicitly defines:

- Maximum staleness window.
- Backstop TTLs.
- Retry policies and alerts for event lag.
- Which endpoints tolerate the staleness window.

Never label a system strongly consistent if invalidation is delivered asynchronously.

### 11.2. Stronger Consistency for Introspection and Revocation

If policy requires a revoked token to appear inactive to introspection the moment revocation returns success, you can:

- Bypass the authorization cache on introspection/revocation paths.
- Use a shared authoritative store for active/invalidated token state.
- Perform synchronous invalidation and await acknowledgment from involved nodes/caches before returning success.
- Use version/fencing checks on sensitive read paths.

Each option trades off latency, availability, and consistency. If the system cannot complete synchronous invalidation, never claim revocation is immediately cluster-wide.

### 11.3. Self-Contained JWTs Are Not Revoked by Authorization Server Caches

Resource Servers can verify self-contained JWTs using signatures and claims without calling the Authorization Server. Evicting caches at the Authorization Server does not automatically invalidate already-issued JWTs at Resource Servers.

To revoke a JWT before `exp`, you need another mechanism such as:

- Token introspection instead of local-only verification.
- A denylist/`jti` revocation lookup.
- Short token TTLs matching the maximum acceptable exposure window.
- Session/version checks at the Resource Server.

Never confuse internal Authorization Server cache invalidation with ecosystem-wide token revocation.

## 12. Spring Cache and Integration Patterns

### 12.1. Spring Cache Is an Abstraction, Not a Consistency Protocol

Spring Framework provides `@Cacheable`, `@CachePut`, `@CacheEvict`, and `CacheManager`. They standardize cache operations, yet do not solve:

- Evicting multiple aliases for one entity.
- Broadcasting invalidation events to other nodes.
- Writing an outbox inside the database transaction.
- Preventing races between cache loaders and invalidation.
- Guaranteeing immediate revocation visibility.

Consequently, for Authorization Server core services, explicit decorators are usually easier to control than scattering a few annotations.

### 12.2. RegisteredClientRepository Decorator Example

~~~java
public final class CachingRegisteredClientRepository
        implements RegisteredClientRepository {

    private final RegisteredClientRepository delegate;
    private final Cache byId;
    private final Cache byClientId;

    public CachingRegisteredClientRepository(
            RegisteredClientRepository delegate,
            Cache byId,
            Cache byClientId) {
        this.delegate = delegate;
        this.byId = byId;
        this.byClientId = byClientId;
    }

    @Override
    public RegisteredClient findById(String id) {
        return byId.get(id, () -> {
            RegisteredClient client = delegate.findById(id);
            if (client != null) {
                byClientId.put(client.getClientId(), client);
            }
            return client;
        });
    }

    @Override
    public RegisteredClient findByClientId(String clientId) {
        return byClientId.get(clientId, () -> {
            RegisteredClient client =
                delegate.findByClientId(clientId);
            if (client != null) {
                byId.put(client.getId(), client);
            }
            return client;
        });
    }

    @Override
    public void save(RegisteredClient registeredClient) {
        RegisteredClient previous =
            delegate.findById(registeredClient.getId());

        delegate.save(registeredClient);

        afterCommit(() -> {
            byId.evict(registeredClient.getId());
            byClientId.evict(registeredClient.getClientId());
            if (previous != null) {
                byClientId.evict(previous.getClientId());
            }
        });
    }
}
~~~

This example illustrates a decorator structure using Spring's `Cache`. In production, add a shared transaction boundary covering reading the old record, saving, and appending the outbox event; version/generation fencing; cross-instance invalidation events; policy for client deletion via separate extension operations; and handling for cache misses/loader exceptions.

The snippet reads the old record to evict the old alias. If `clientId` is immutable by application policy, this can be simplified; if renaming is allowed, read the old record within the same consistency boundary as the update.

### 12.3. Configuring the Cache Decorator

You can configure a local Caffeine cache via Spring Cache:

~~~java
@Bean
CacheManager cacheManager() {
    CaffeineCacheManager manager = new CaffeineCacheManager(
        "registeredClientById",
        "registeredClientByClientId",
        "authorizationById",
        "authorizationByToken",
        "authorizationConsent");

    manager.setCaffeine(Caffeine.newBuilder()
        .maximumSize(100_000)
        .expireAfterWrite(Duration.ofMinutes(2))
        .recordStats());

    return manager;
}
~~~

The TTL in this example is purely illustrative. In practice, configure separate TTLs per cache region; authorizations/tokens normally need shorter lifetimes than `RegisteredClient`. Never use a single global TTL when domains differ in sensitivity and update frequency.

### 12.4. Registering Decorators with AuthorizationServerConfigurer

Core services can be wired via `OAuth2AuthorizationServerConfigurer`:

~~~java
http.with(authorizationServerConfigurer, authorizationServer -> authorizationServer
    .registeredClientRepository(cachingRegisteredClientRepository)
    .authorizationService(cachingAuthorizationService)
    .authorizationConsentService(cachingConsentService)
);
~~~

Ensure every protocol endpoint and custom provider uses these same decorators. Never wire a cached bean for one endpoint while another endpoint reads the raw delegate directly, as that introduces two read paths with differing consistency.

### 12.5. Be Careful with @CacheEvict

By default, `@CacheEvict` evicts after method invocation succeeds. That does not guarantee eviction runs after an outer database transaction commits; transaction/cache advisor ordering can interfere.

To tie caching to commits, use a transaction-aware cache strategy or register invalidations in `TransactionSynchronization.afterCommit()`. For cross-node invalidation, write to an outbox inside the same transaction; after-commit callbacks are only a local optimization.

Additionally, Spring caching annotations rely on proxies. Self-invocation within the same object can bypass the interceptor. Verify call paths before relying on annotations to ensure caching actually applies.

## 13. Common Mistakes

### Mistake 1: Caching RegisteredClient Only by Client ID

**Symptom:** Client authentication speeds up, yet internal-ID lookups still query the database.

**Cause:** Only one alias is cached.

**Fix:** Cache both `findById` and `findByClientId`, and evict both aliases together.

### Mistake 2: Evicting the Cache Before Database Commit

**Symptom:** Another request reloads the stale record and writes it back into the cache.

**Cause:** Invalidation runs before commit.

**Fix:** Evict after commit and use version/generation fencing to prevent cache-fill races.

### Mistake 3: Evicting Only on the Node Performing Revocation

**Symptom:** Other nodes continue returning active on introspection for a revoked token.

**Cause:** Local caches are not synchronized.

**Fix:** Use a transactional outbox/durable events and monitor invalidation lag.

### Mistake 4: Evicting Only by Authorization ID

**Symptom:** `findById` misses, yet `findByToken` keeps returning the stale authorization.

**Cause:** Token alias cache entries remain.

**Fix:** Evict all typed token keys, `ANY` keys, and reverse indexes.

### Mistake 5: Failing to Handle Refresh Token Rotation

**Symptom:** Old refresh tokens remain resolvable in cache or new tokens go unrecognized.

**Cause:** Only the new token or only the authorization ID is evicted.

**Fix:** Collect token aliases from both old and new snapshots; evict all of them after commit.

### Mistake 6: Caching Consent Only by Principal

**Symptom:** Client A's consent is returned for Client B.

**Cause:** Cache key omits `RegisteredClient` ID.

**Fix:** Use the composite key `(registeredClientId, principalName)`.

### Mistake 7: Using Long TTLs Instead of Invalidation

**Symptom:** Old client secrets or revoked tokens remain accepted for the duration of the TTL.

**Cause:** Missing event-driven invalidation.

**Fix:** TTL is a backstop; write-driven invalidation is still required.

### Mistake 8: Using Raw Tokens as Cache Keys

**Symptom:** Bearer tokens show up in cache diagnostics or key listings.

**Cause:** Using credentials directly as keys.

**Fix:** Use HMAC digests, never log keys, and keep the HMAC secret outside the database.

### Mistake 9: Silent Pub/Sub Event Loss

**Symptom:** A node serves stale cache entries until TTL expires.

**Cause:** Relying on non-durable broadcast messaging.

**Fix:** Use an outbox, durable broker/offsets, retries, and clear caches when a node cannot replay events.

### Mistake 10: Confusing Cache Invalidation with JWT Revocation

**Symptom:** Issued JWTs remain accepted by Resource Servers after Authorization Server caches are cleared.

**Cause:** Resource Servers verify JWTs locally without querying the Authorization Server.

**Fix:** Use introspection, denylist/version checks, or appropriately short token TTLs.

### Mistake 11: Cache Miss Overwritten by a Stale Loader

**Symptom:** Invalidation arrived, yet the stale snapshot reappears.

**Cause:** Loader started before commit and finished after invalidation.

**Fix:** Use generation/version fencing and skip `put` if the generation changed.

### Mistake 12: Caching Mutable Objects

**Symptom:** One flow mutates attributes, causing other requests to observe unexpected state.

**Cause:** Sharing mutable objects across requests.

**Fix:** Cache immutable snapshots, never mutate cached objects directly, and build fresh objects on updates.

## 14. Testing Caching and Invalidation

### 14.1. Unit Tests for Cache Decorators

Verify:

- `findById` calls the delegate once across cache hits.
- `findByClientId` calls the delegate once across cache hits.
- Caching a `RegisteredClient` by ID also populates the client-ID alias.
- `save` evicts both old and new aliases.
- Consent caches match the exact client/principal pair.
- Authorization token aliases distinguish token types.
- `null` token type uses its own cache key.
- Token misses are not cached for excessively long durations.

### 14.2. Transaction Integration Tests

| Scenario | Expected Result |
| --- | --- |
| Save client inside committed transaction | Cache evicts after commit. |
| Save client then roll back | Old cache stays valid; no committed invalidation event emitted. |
| Save authorization then roll back | Old token aliases are not wrongly evicted; no committed event emitted. |
| Revoke token and commit | Authorization/token alias caches are evicted. |
| Revoke token then roll back | Cache does not reflect uncommitted changes. |
| Save consent | Composite key evicted after commit. |
| Remove consent | Composite key evicted after commit. |
| Refresh token rotation | Both old and new tokens are handled properly. |

### 14.3. Multi-Node Integration Tests

Start at least two instances, A and B:

1. A and B both load a `RegisteredClient`/authorization into their caches.
2. A updates the client or revokes a token and commits.
3. Verify B receives the invalidation event.
4. Verify B reloads the updated version from the database.
5. Inject duplicate events and out-of-order events.
6. Disconnect B from the broker, mutate an authorization on A, then reconnect B.
7. Verify B replays events or clears its cache before serving requests.
8. Simulate B's loader reading stale state while A commits; verify the generation fence blocks stale caching.

### 14.4. Testing Immediate Revocation Requirements

If the system guarantees immediate revocation visibility:

- Send introspection requests concurrently with revocation.
- Identify the linearization point where revocation is considered complete.
- Ensure introspection requests after that point never receive `active=true`.
- When cache/broker is unavailable, verify endpoints fail closed or bypass cache per policy.
- Never test only on a single local node.

## 15. Observability and Operations

### 15.1. Cache Metrics

Monitor:

- Hit ratio and miss ratio per cache region.
- Load latency and loader errors.
- Eviction count and expiration count.
- Cache size/estimated size.
- Cache loader concurrency and stampedes.
- Unpublished outbox event count.
- Consumer lag and invalidation delay.
- Event retry/dead-letter counts.
- Count of generation/version mismatches blocking cache puts.

Never attach raw client secrets, tokens, principal names, or sensitive authorization IDs as metric labels. Use bounded-cardinality dimensions such as cache region, operation, and tenant class/opaque tags.

### 15.2. Setting SLOs for Invalidation

A multi-node deployment should define:

- Maximum time from DB commit until the last node evicts its cache.
- Percentage of invalidation events processed on time.
- Maximum tolerable broker consumer lag.
- Behavior when a node goes offline or the broker is unavailable.
- Which endpoints allow eventual consistency.
- Which endpoints must read authoritative state.

TTL serves only as a backstop if events are lost or a node misses notifications.

### 15.3. Runbook for Invalidation Failures

When invalidation lag breaches SLO:

1. Identify affected entity types and cache regions.
2. Check outbox backlog, broker lag, and consumer errors.
3. Identify which nodes have not received events.
4. Bypass or clear caches on out-of-sync nodes if policy requires.
5. Replay events from a safe offset.
6. Verify the latest tokens/clients/consents directly against the durable store.
7. Restore the cache read path only after nodes catch up.

Do not reflexively flush the entire cache cluster if only one region is affected; doing so can trigger a database thundering herd.

## 16. Production Checklist

| Item | Condition to Verify |
| --- | --- |
| Core services | Dedicated decorators for `RegisteredClient`, authorization, and consent? |
| Source of truth | Database/durable store remains the primary source of truth? |
| Client aliases | Cached by both internal ID and client ID? |
| Authorization aliases | Cached by ID, token type, and token digest? |
| Consent keys | Include both `RegisteredClient` ID and principal name? |
| Token privacy | Never use raw bearer tokens as cache keys or in event payloads? |
| TTL | Separate TTLs per domain, token expiry, and consistency SLA? |
| Negative cache | Short TTL, size bounds, and invalidation when new records are created? |
| Write invalidation | `save`/`remove` evict both old and new aliases accurately? |
| Transactions | Local cache eviction runs after commit? |
| Outbox | Invalidation events are written in the same transaction as durable updates? |
| Multi-node | Every instance receives events or replays on reconnect? |
| Event ordering | Events are idempotent and carry versions/generations? |
| Cache-fill race | Stale loaders cannot overwrite newer snapshots? |
| Revocation | Introspection reflects revocations within committed SLOs? |
| Consent withdrawal | Policy for handling already-issued authorizations/tokens is clearly defined? |
| JWT | Server-side caches are distinguished from self-contained JWT validation at Resource Servers? |
| Secrets | Client secrets are encoded, never logged, and evicted upon rotation? |
| Observability | Metrics cover hit ratio, invalidation lag, outbox backlog, and event retries? |
| Recovery | Runbooks cover bypassing/clearing/replaying caches on desynchronized nodes? |

## 17. Practical Exercise

An Authorization Server runs three instances A, B, and C. All three share one PostgreSQL database while keeping local Caffeine caches. The system holds 200,000 `RegisteredClient`s, 15 million authorizations, and 4 million consents. Introspection p95 must stay under 30 ms. A token can be revoked at any moment; business requirements state that introspection after a revocation returns success must no longer return `active=true`.

1. Design cache namespaces and keys for the three core services.
2. Choose cached data, TTLs, and negative caching policies for each service.
3. Write a `RegisteredClientRepository` decorator supporting lookups by ID and client ID.
4. Design authorization token aliases for access tokens, refresh tokens, authorization codes, ID Tokens, and `tokenType=null`.
5. Design invalidation for refresh token rotation, revocation, and authorization removal.
6. Design composite keys for consent and the invalidation flow when a user withdraws consent.
7. Use transaction after-commit callbacks for local eviction and an outbox to broadcast events to other nodes.
8. Resolve the race when instance B is loading an old snapshot while instance A commits a revocation.
9. Define handling if B loses broker connectivity for 30 seconds.
10. Decide which endpoints can use eventually consistent caches and which must bypass caches to meet the revocation SLA.
11. Write a two-node integration test proving a revoked token is no longer active after the committed commit point.
12. Measure p50/p95/p99 latency, DB QPS, cache hit ratio, and invalidation lag before and after enabling caching.

**Acceptance Criteria:** Caching reduces database load without changing core service semantics; clients/authorizations/consents evict exact keys after commit; events contain no raw credentials; reconnecting nodes never serve stale snapshots; revocation SLA is verified across multiple instances.

## 18. Reference Documents

- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClientRepository`, `OAuth2AuthorizationService`, `OAuth2AuthorizationConsentService`, token lifecycle, and core models.
- [Spring Authorization Server 1.5.8 — RegisteredClientRepository Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/client/RegisteredClientRepository.html): `findById`, `findByClientId`, `save`, and client secret handling.
- [Spring Authorization Server 1.5.8 — OAuth2AuthorizationService Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2AuthorizationService.html): authorization management contract.
- [Spring Authorization Server 1.5.8 — OAuth2Authorization Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2Authorization.html): token accessors, attributes, and authorization identity.
- [Spring Authorization Server 1.5.8 — OAuth2AuthorizationConsentService Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2AuthorizationConsentService.html): composite lookup, save, and remove consent.
- [Spring Authorization Server 1.5.8 — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): configuring core services via `OAuth2AuthorizationServerConfigurer`.
- [Spring Authorization Server 1.5.8 — How-to: Implement core services with JPA](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-jpa.html): implementing custom persistence services.
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `@Cacheable`, `@CachePut`, `@CacheEvict`, and the cache abstraction.
- [Spring Framework 6.2 — TransactionSynchronization Javadoc](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html): `afterCommit` callback.
