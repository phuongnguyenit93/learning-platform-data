# Caches, Login Sessions, and Messages That Persist Across Deployments

When upgrading the JDK, framework, or Java application version, we typically check whether the source code compiles and whether the service starts up. However, a running system also holds **state created by the previous version**: values in cache, user login sessions, events awaiting consumption in message brokers, retry tasks, dead-letter records, and data emitted by another service. This data does not automatically vanish when replacing containers, changing JDKs, or rolling out a new version to production.

For example, an old service running Java 8 wrote a Java-serialized object into Redis. The new service running Java 21 uses the same cache key, yet a class changed packages, added a field, or changed `serialVersionUID`. Deployment may succeed, but cache-read requests throw `InvalidClassException` or `ClassNotFoundException`. Another scenario: an old consumer is still running during a rolling deployment while the new producer starts emitting events with an enum or data type unknown to the old consumer. All tests running solely against new data on the new version may pass, while production fails minutes or days later.

This lesson guides you through identifying state types that cross deployment boundaries, evaluating read/write compatibility between old and new versions, building an **expand–migrate–contract** strategy, and testing across the true lifecycles of caches, sessions, and messages.

## 1. What Is State That "Outlives an Application Version"?

A Java process may terminate, yet the data it created continues to reside elsewhere:

- **Distributed cache:** Redis, Memcached, Hazelcast, Infinispan, or the application's cache store.
- **Persistent local cache:** cache files, disk stores, or embedded data stores on volumes preserved across deployments.
- **HTTP session:** sessions in a database/Redis, session replication in an application server, or tokens containing claims issued by a previous server.
- **Message broker:** Kafka topics, RabbitMQ queues, JMS providers, event streaming systems, and retry/dead-letter records.
- **Scheduled/durable jobs:** payloads stored in a job scheduler or database for later processing.
- **Outbox/inbox:** events and deduplication records persisted for transactional forwarding and duplicate handling.
- **Object storage/file:** snapshots or exported payloads for future batch jobs/consumers to read.

These are forms of **data contracts across time**. The writer at time T may not be the same version as the reader at time T+1.

A typical deployment:

~~~text
                  Before deploy                    After deploy
              +---------------------+        +---------------------+
              | App v1 / old JDK    |        | App v2 / new JDK    |
              | Cache writer v1     |        | Cache reader v2     |
              | Session writer v1   |        | Session reader v2   |
              | Event producer v1   |        | Event consumer v2   |
              +----------+----------+        +----------+----------+
                         |                              |
                         +--------------+---------------+
                                        |
                        +-------------------------------+
                        | Redis / DB / broker / storage |
                        | Unexpired or unconsumed data  |
                        | still remains intact          |
                        +-------------------------------+
~~~

During a rolling deployment, **v1 and v2 may also run simultaneously**. Therefore, you must account for v1 reading data just written by v2, not only v2 reading old data.

## 2. Five Compatibility Dimensions to Evaluate

Data compatibility across deployments is more than "JSON still parses". There are at least five dimensions:

1. **Format compatibility:** is the payload represented in JSON, Java Serialization, Avro, Protobuf, CBOR, or another binary format? Does the reader recognize the format?
2. **Schema compatibility:** do field names, types, required/optional flags, defaults, enums, and nested structures still align?
3. **Semantic compatibility:** did the meaning of the same field change? For example, `expiresAt` previously in seconds and later in milliseconds.
4. **Security compatibility:** was the data encrypted/signed, were keys rotated, did algorithms change, were policies added, or did trust boundaries shift?
5. **Operational compatibility:** how long does the data persist, is it written concurrently by two versions, can it be rolled back, and are there enough metrics to detect failures?

Each dimension can produce failures differently:

| Change | Potential failure | Verification measure |
|---|---|---|
| Switching serializer from JDK binary to JSON | Reader misreads magic bytes/format | Test real v1 payloads with reader v2 |
| Renaming package/class | Java deserializer cannot find the class | Use old binary fixtures; avoid Java object serialization for long-lived contracts |
| Adding required field without default | Old payloads lack mandatory data | Test v1 schema → v2 reader |
| Adding enum value | Old consumer cannot handle the new value | Check fallback/unknown enum handling |
| Changing timestamp unit | No parse error, but wrong time values | Behavioral contract tests and boundary cases |
| Changing encryption/signing keys | Old sessions or payloads fail decryption/verification | Test rotation and controlled rollback |
| Changing TTL | Sessions expire early or old data lingers abnormally | Test expiration and monitoring |
| Deploying producer/consumer concurrently | v1 receives events only v2 understands | v1↔v2 matrix and rollout plan |

**Succeeding at reading does not mean correct behavior.** A value that parses all fields cleanly yet has the wrong currency unit or timezone can be more dangerous than an obvious error.

## 3. Cross-Version Read and Write Matrix

Using notation:

- `W1`: old version writes.
- `R1`: old version reads.
- `W2`: new version writes.
- `R2`: new version reads.

Four key combinations:

| Payload | Reader | Goal |
|---|---|---|
| W1 | R1 | Old baseline works |
| W1 | R2 | **Backward-read:** new version can read old data |
| W2 | R2 | New version works on its own |
| W2 | R1 | **Forward-read:** old version can read new data, needed for rolling deploys or rollback |

In a system that upgrades all at once with no rollback, W2→R1 might not occur. However, if multiple pods run concurrently, a load balancer still routes requests to the old version, or old consumers can still receive new messages, then W2→R1 is a real-world scenario.

Check **each independent producer/consumer**, not just per service. A payload written by cache-writer v2 might be read by batch-job v1; a session cookie issued by frontend v2 might be processed by backend v1.

## 4. Inventorying State Storage Locations

Before modifying serializers or schemas, build an inventory:

| Component | Storage | Writer | Reader | Format | Lifetime | Needed on rollback? |
|---|---|---|---|---|---|---|
| Product price | Redis | Catalog v1/v2 | Catalog API | JSON schema v1 | 30 minutes | Yes |
| User profile | Redis | Account v1/v2 | Account API | Old JDK binary | 6 hours | Yes |
| HTTP session | Redis/DB | Web nodes | Web nodes | Framework serializer | 12 hours | Yes |
| Refresh token | DB/identity service | Auth service | Auth service | Token/hash metadata | Several days | Yes |
| Order events | Kafka topic | Order producer | Billing/Shipping | Avro v1 | 7 days | Yes |
| Retry job | Durable queue | Batch worker | Batch worker | JSON job v2 | Until completed | Yes |
| Dead-letter event | DLQ | Broker/consumer | Replay tool | Multiple schemas | Possibly months | Must evaluate separately |

More important than the store name is:

- Which versions are **permitted to read/write concurrently**?
- Does the data belong to a business source-of-truth or is it merely a reproducible copy?
- Is TTL/retention actually enforced, or do some entries never expire?
- Are there writers outside the main application, such as cronjobs, admin scripts, ETL, or partner services?
- Does the data contain PII, session tokens, secret keys, or sensitive information?
- Can the data be deleted safely, or does deleting it cause logouts, lost jobs, or broken idempotency?

Do not lump "cache" and "queue" under the same policy. Caches can be cleared and rebuilt in certain cases; unprocessed business messages may represent obligations that must be completed and cannot be deleted.

## 5. Caches When Changing JDK and Application Versions

Cache is often treated purely as a performance optimization, yet its compatibility impact can be huge. A cache miss can spike database load; a cache hit with an incompatible old payload can cause 500 errors; a cache hit containing semantically wrong data can lead to incorrect business decisions.

### 5.1. Classifying Caches by Risk

- **Local in-memory cache:** lost when the process stops, but can coexist in v1/v2 nodes simultaneously and cause behavioral differences.
- **Distributed cache:** persists independently of processes and can be read by multiple versions.
- **Persistent cache:** disk files/snapshots persisting across restarts/deployments; requires checking format/version and recoverability.
- **Shared cross-service cache:** producer and consumer are different services; changes are no longer an internal refactor.
- **Derived cache:** can be regenerated from the database/source-of-truth.
- **Authority-like cache:** holds token/session/rate-limit/idempotency state; clearing the cache can break controls or alter security.

For pure derived caches, changing key namespaces or invalidating keys are viable options. For sessions or idempotency state, never assume clearing the cache is safe.

### 5.2. Cache Keys Are Also Part of the Schema

A cache entry has a contract consisting of **key + value + TTL + semantics**:

~~~text
catalog:price:v1:sku-104
catalog:price:v2:sku-104
~~~

Two similar keys with different payloads:

~~~json
{
  "schemaVersion": 1,
  "amount": 125000,
  "currency": "VND"
}
~~~

~~~json
{
  "schemaVersion": 2,
  "money": {
    "decimal": "125000",
    "currency": "VND"
  },
  "calculatedAt": "2026-11-12T08:00:00Z"
}
~~~

If you change the value structure while keeping the key `catalog:price:sku-104`, the old reader and new reader can misread each other's format. One way to reduce risk is to **version the cache key** so the two formats do not contend for the same slot.

However, changing the key causes both cache copies to coexist and can increase load on the source-of-truth when v2 reads for the first time. Account for cache warm-up, TTL, memory quota, and request rate limiting.

### 5.3. Cache Migration Strategies

**Strategy A — New reader supports both schemas.** Keep the existing key; R2 can read both v1 and v2. Appropriate when differences are small, old data remains useful, and writer v2 does not break R1 during parallel operation.

**Strategy B — New namespace/version.** V2 writes `prefix:v2:...`, while v1 uses `prefix:v1:...`. The two versions stay isolated; v2 may fall back to reading v1 and converting if source data and policy allow.

**Strategy C — Controlled invalidation.** Gradually delete keys in a defined scope and let them be regenerated. Only suitable when the data is a derived cache, has an authoritative source, and can tolerate cache misses.

**Strategy D — Background migration.** Read v1 entries, validate them, convert to schema v2, and write the new key. Avoid semantic changes, handle write races, and record progress.

**Strategy E — Discard old data on read.** If the reader detects an unsupported v1 schema, treat the entry as a cache miss and refetch. Do this only for entries allowed to be regenerated; never apply to sessions or messages requiring processing.

### 5.4. Choosing by Data Type

| State | Can be deleted to regenerate? | Typically suitable option |
|---|---|---|
| Temporary HTTP response cache | Usually yes, but account for load | Key versioning, invalidation, TTL |
| Lookup table derived from DB | Yes, if the DB can handle the load | Schema-aware read or rebuild |
| Prices in checkout flow | Must consider consistency and price-lock timing | Explicit contract, no silent fallback |
| Session stored in Redis | Should not be cleared en masse | Compatible reader + session migration |
| Distributed lock | Dangerous to delete | Preserve key/TTL semantics, test concurrency |
| Idempotency key | Deleting can cause duplicates | Preserve duration and replay semantics |
| Event in queue | Not a cache | Versioned message + consumer compatibility |

## 6. Java Serialization and Binary Cache Risks

Some older applications store Java objects directly using `ObjectOutputStream`, a framework's Java serialization serializer, or session replication systems. This tightly couples the data to the **binary class name, serialVersionUID, field structure, and reader classpath**.

Example old class:

~~~java
package com.acme.session;

import java.io.Serializable;

public final class CartSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;

    private String cartId;
    private int quantity;
}
~~~

If the new version moves the package to `com.acme.checkout.CartSnapshot`, the old serialized payload still references the old class name. Even if the new fields are identical, the deserializer may fail to find the class and throw `ClassNotFoundException`.

If the class keeps the same name but `serialVersionUID` changes incompatibly, you may receive:

~~~text
java.io.InvalidClassException
~~~

If you change field types, inheritance hierarchy, or serialization structure incompatibly, other errors or unexpected results can occur. Do not treat a fixed `serialVersionUID` as a "guarantee that all changes are compatible". It is only one part of the version-checking mechanism during Java deserialization.

### 6.1. Field Changes Are Not Just Adding or Removing Fields

With default Java object serialization, some cases of adding new fields can be handled by the old/new deserializer under compatibility rules. However:

- New fields may receive default values `null`, `0`, or `false` when reading an old stream.
- New business invariants may no longer hold.
- Renamed/repackaged classes do not automatically map to the new name.
- Externalizable or custom `readObject`/`writeObject` methods have their own logic and contracts.
- `transient` fields are not serialized by default.
- Proxies, ORM enhancement, and class loaders can further complicate compatibility.

For example, adding `currency` to `CartSnapshot`: the v1 payload has no `currency`; reader v2 must decide whether a default is valid or whether to fetch it from the source-of-truth. Blindly assigning `"USD"` when the old data was actually VND is a semantic bug even without an exception.

### 6.2. Do Not Deserialize Java Objects from Untrusted Data

Java native deserialization carries security risks when processing streams controlled by untrusted parties. Cache/message data may come from trusted systems, yet you still need to evaluate tampering risk, store write permissions, and type allowlists.

For cases where reading old binary data is mandatory:

- Restrict data sources and write permissions.
- Apply serialization filtering via supported JDK APIs and configuration, such as `ObjectInputFilter`, with an appropriate allowlist/limits.
- Avoid loading unnecessary classes.
- Do not automatically accept all types just to make the migration pass.
- Plan a migration to an explicit-schema format such as JSON, Avro, or Protobuf if it is a long-term storage contract.

If the goal is "reading data that persists across deployments", formats independent of implementation classes are usually much easier to govern than Java serialized objects.

## 7. Designing Cache Payloads with schemaVersion

One way to reduce coupling is to use **data transfer objects and managed formats**. Example JSON payload:

~~~json
{
  "schemaVersion": 2,
  "cacheKey": "customer:981",
  "cachedAt": "2026-11-12T08:20:00Z",
  "expiresAt": "2026-11-12T08:50:00Z",
  "value": {
    "customerId": "981",
    "status": "ACTIVE"
  }
}
~~~

The reader needs to know:

- Is a missing `schemaVersion` treated as v1, or as an invalid payload?
- Which versions are supported?
- Can fields be absent?
- How are unknown fields/enums handled?
- Does the timestamp use UTC ISO-8601 or which epoch unit?
- Does storage TTL match `expiresAt` in the payload?

Illustrative handling code (pseudocode, not tied to a specific JSON library):

~~~java
CacheValue readCache(byte[] bytes) {
    JsonObject json = jsonCodec.decode(bytes);
    int version = json.getInt("schemaVersion", 1);

    switch (version) {
        case 1:
            return migrateV1ToCurrent(json);
        case 2:
            return parseCurrent(json);
        default:
            throw new UnsupportedSchemaVersionException(version);
    }
}
~~~

In a derived cache, `UnsupportedSchemaVersionException` may be turned into a cache miss and fetch from source-of-truth. In sessions or mandatory business data, never silently swallow the error and construct empty state.

### 7.1. Read Old, Write New

A common pattern during the transition period is:

~~~text
                 Reader v2
                    |
          +---------+---------+
          |                   |
       Payload v1          Payload v2
          |                   |
      Parse v1            Parse v2
          |                   |
      Normalize --------------+
                    |
             Internal model v2
                    |
              Writer v2
~~~

Reader v2 continues supporting v1 for a measured/defined window. Writer v2 can begin writing the new format **only after** every consumer that can still receive this data has been upgraded or has a compatibility bridge.

### 7.2. Do Not Turn Schema Errors into a Cache Stampede

If many requests simultaneously hit thousands of unreadable old cache entries and query the DB all at once, the system can overload. You need to:

- Coalesce/single-flight requests for the same key.
- Limit concurrency and request rate to the source-of-truth.
- Use TTL jitter to prevent mass simultaneous key expiration.
- Warm up hot caches before rollout.
- Measure cache hits/misses, deserialization errors, and latency.
- Have a mechanism to stop writing the new schema via a feature flag when rollback is needed.

## 8. TTL, Expiration, and the Meaning of "Old Data Is Gone"

You cannot conclude "an hour after deployment all old cache entries have vanished" without knowing the actual TTL.

State may persist longer than expected when:

- Keys lack a TTL due to a bug or were written with a command that sets no expiration.
- TTL is extended on access (sliding expiration).
- A v1 job or node continues writing the old format.
- Backup/restore brings old data back.
- Local client caches hold copies longer than the distributed cache.
- Dead-letter queues or retry jobs contain payloads with no clear maximum retention.

With Redis, operations to inspect keys and TTLs should target specific permitted keys:

~~~text
TTL catalog:price:v1:sku-104
PTTL catalog:price:v1:sku-104
TYPE catalog:price:v1:sku-104
~~~

Scanning or mass-deleting production keys solely to find old data is discouraged. Operations like `KEYS *` on a large Redis instance can cause operational impact; deletion requires scope, backups, and an approved plan.

The milestone for "dropping schema v1 support" must be based on **actual maximum lifetime + remaining time of old writers + replay/restore policy**, not solely on default TTL values in source code.

## 9. HTTP Login Sessions Persisting Across Rolling Deployments

In a web application, a user can log in before a deployment and continue sending requests after the new service comes up. If session state is stored on the server or in a shared store, that session may be **created by v1 yet read by v2**.

Common session forms:

- **In-memory `HttpSession` on a single node:** may be lost when the node stops, or replicated depending on the application server.
- **Distributed session** in Redis/DB: accessed by multiple nodes and survives restarts.
- **Sticky session:** the load balancer prefers the same node, though failover/rolling deployments still change the handling node.
- **Opaque session token:** the cookie holds only a session identifier, while state lives on the server.
- **Signed/encrypted cookie or JWT:** part or all of the claims reside on the client side and continue to be sent after the deployed version changes.
- **Refresh token/SSO session:** long-lived and dependent on the identity provider/authorization server.

Do not equate **HTTP sessions**, **access tokens**, **refresh tokens**, and **business workflow state**. They have different lifecycles, access permissions, and migration requirements.

### 9.1. Sessions Containing Legacy Java Objects

Example old code:

~~~java
HttpSession session = request.getSession();
session.setAttribute("currentUser", userEntity);
~~~

If `userEntity` is a Hibernate entity or a Java object tied to an implementation class, the serialized session may be coupled to the class name, `serialVersionUID`, lazy proxies, and framework version. When v2 deploys, the session store still contains v1 objects.

Errors can arise when:

- The session is deserialized on a new node.
- The framework changes its default serializer.
- The class is renamed or properties are no longer compatible.
- The application server's class loader cannot find the old class.
- The session contains non-serializable objects when replication is enabled.
- The session contains sensitive data that should not be stored or requires revalidation.

### 9.2. Store Stable Session DTOs Instead of Domain Objects

A more migration-friendly design keeps session attributes small, based on primitives/strings and schema-backed formats:

~~~java
public final class SessionProfile implements java.io.Serializable {
    private static final long serialVersionUID = 1L;

    private String userId;
    private String localeTag;
    private int schemaVersion;

    public SessionProfile(String userId, String localeTag) {
        this.userId = userId;
        this.localeTag = localeTag;
        this.schemaVersion = 1;
    }

    // Getters and validation per application contract.
}
~~~

The example above still uses Java serialization to illustrate a DTO, not as a blanket recommendation to use serialization for distributed sessions. With Redis or database-backed sessions, JSON/custom schema formats usually make data boundaries clearer when supported by the system.

Avoid storing raw passwords, private keys, long-lived credentials, or entire entity graphs in the session. Prefer IDs and minimal data; fetch fresh business data from the source-of-truth when needed.

### 9.3. Session Expiry, Cookies, and Security

Beyond serializers, a migration may alter:

- Session timeouts and sliding expiration.
- Cookie name, domain, path, `SameSite`, `Secure`, `HttpOnly`.
- Cookie signing/encryption keys and key rotation schedules.
- Session ID regeneration after login or privilege changes.
- Multi-node logout/invalidation mechanisms.
- CSRF tokens stored in the session.
- Principal/authority claims when upgrading security frameworks.
- Session fixation protection and session recovery after restarts.

A v2 unable to read v1 sessions can trigger mass logouts. This is sometimes an acceptable decision, but **it must be an explicit product/security decision**, not an accidental consequence of migration.

If both v1/v2 are running, changing the cookie name or secret can bounce users back and forth between two authentication states. Design a bounded dual-key/dual-format read period, or roll out by user cohort if feasible.

## 10. Tokens Issued Before Deployment

JWTs and self-contained tokens are not deserialized like Java objects in Redis, yet they are still **messages that persist across deployments**. An access token issued at 09:00 may be validated by API v2 at 09:15.

Check:

- `iss`, `aud`, `sub`, `exp`, `nbf`, and clock skew.
- Allowed algorithms and key IDs such as `kid`.
- Whether key rotation has sufficient overlap to verify old tokens until they expire.
- Whether new claims cause old consumers to misinterpret roles/permissions.
- Whether old consumers ignore new claims or require an explicit schema version.
- Refresh tokens/SSO sessions may outlive access tokens.
- Whether revocation/logout policies remain consistent.

Do not weaken signature checks, skip `aud`, or accept weak algorithms merely to "keep users logged in" during a JDK upgrade. If sessions must expire due to a security contract change, prepare a UX plan, estimate affected users, and communicate clearly.

## 11. Message Queues and Unprocessed Messages

Unlike a cache, a message in a broker usually represents an event or command that must be processed. It may have been emitted by producer v1 yet read only by consumer v2 because a backlog spanned the deployment.

Example:

~~~text
Producer v1 -- order.created(v1) --> Topic/Queue --> Consumer v2
Producer v2 -- order.created(v2) --> Topic/Queue --> Consumer v1
                            |
                      Retry / DLQ
                            |
                   Replay after several days
~~~

The dataset to consider includes:

- Unconsumed messages.
- In-flight messages when a process is replaced.
- Already-acked messages that still have outbox/dedup state.
- Delayed retry messages.
- Dead-letter messages awaiting investigation and replay.
- Events retained in Kafka logs for new consumers reading from older offsets.
- Snapshots/checkpoints of stream processors or materialized views.
- Batch jobs scheduled prior to deployment.

A message schema compatible only with the new version does not guarantee system safety if **old consumers** or un-upgraded replay tools still exist.

## 12. Versioning Message Envelopes and Payloads

A message contract should separate routing metadata from the business payload:

~~~json
{
  "messageId": "8d30cc13-a53c-4d9a-9c14-f2a61b20bda1",
  "eventType": "order.created",
  "schemaVersion": 2,
  "occurredAt": "2026-11-12T08:10:00Z",
  "producer": "order-service",
  "payload": {
    "orderId": "O-18025",
    "total": {
      "amount": "125000.00",
      "currency": "VND"
    },
    "items": [
      {"sku": "P-104", "quantity": 2}
    ]
  }
}
~~~

Commonly useful fields:

| Field | Purpose |
|---|---|
| `messageId` | Identifies the message for dedup/idempotency |
| `eventType` | Specifies the event type instead of guessing from fields |
| `schemaVersion` | Selects the parser/adapter for the payload |
| `occurredAt` | Timestamp when the event occurred per defined standard |
| `producer` | Traces the emitting source, not a sole trust mechanism |
| `correlationId` | Tracks workflows/requests across multiple services |
| `payload` | Business data conforming to a specific schema |
| `trace metadata` | Correlates logging/tracing where appropriate |

Not every system needs all fields in this exact shape; Kafka headers, a schema registry, or messaging frameworks may store metadata separately. However, there must be **an explicit version and identity contract**, rather than guessing versions from whether a field is present.

### 12.1. Distinguishing Event Version from Application Version

`schemaVersion=2` does not mean the message is valid only on "app version 2" or "Java 21". A single schema version can be supported by multiple producer/consumer versions. Version is a property of the **data contract**, not synonymous with the JDK runtime.

When upgrading the JDK without changing the message schema, you still must check serializer libraries and classpath/providers. When changing the schema while keeping the JDK, the same compatibility testing applies.

### 12.2. Changes That Are Typically Compatible vs. Breaking

| Schema change | Risk | Mitigation |
|---|---|---|
| Adding optional field with default | Usually easy to support | Old consumer ignores unknown fields per contract |
| Adding required field without default | New reader fails to read old payloads | Make field optional, provide default, or use v1 adapter |
| Changing type `number` to `string` | Parsers/consumers break | Migrate by version with a transition period |
| Renaming field | Old consumer cannot find it | Support read aliases during transition |
| Changing semantics with same type | Easily causes silent business bugs | Version the schema, run contract tests, and migrate |
| Adding enum value | Old consumer may crash or default wrongly | Unknown-value strategy |
| Removing field | Old consumer needing the field fails | Deprecate first, measure usage, remove only after old consumers are gone |
| Changing timestamp unit | Parses successfully, but wrong time | Explicit unit contract, boundary tests |
| Changing Kafka key/ordering | Can alter partitioning/ordering | Evaluate per-entity processing flows |

Do not mechanically conclude that "adding a JSON field is always backward compatible". That holds only if actual readers and schemas permit unknown fields and the new field does not break semantics.

## 13. JSON, Avro, Protobuf, and Java Binary Messages

### 13.1. JSON

JSON can be read/written across many languages, but does not automatically guarantee schema compatibility. Jackson/Gson settings such as fail-on-unknown-properties, null handling, polymorphic type metadata, date/time serialization, or case sensitivity may change across framework versions.

A message containing:

~~~json
{"status":"PENDING"}
~~~

does not automatically guarantee a new parser will know how to handle:

~~~json
{"status":"AWAITING_REVIEW"}
~~~

If the code uses:

~~~java
Status.valueOf(statusFromMessage)
~~~

then the new enum value will throw `IllegalArgumentException` when an older reader has not declared it. You can use a parser with an explicit unknown branch, route unsupported messages into a safe handling flow, or prevent the producer from emitting the new enum until consumers are upgraded.

### 13.2. Avro

Avro supports schema evolution via structured rules such as reader/writer schemas, field defaults, unions, and compatibility modes. However, compatibility depends on the schema registry/configuration and actual encoding, not merely on using Avro.

If the topic uses a schema registry, verify:

- Subject naming strategy.
- Configured compatibility mode, such as backward/forward/full where appropriate.
- Supported reader/writer schema versions.
- Remaining running consumers and events that may be replayed.
- Whether schema migration tools or state-store formats depend on versions.

### 13.3. Protocol Buffers

Protobuf can maintain strong compatibility when following field number and wire type rules. However, changing field numbers, reusing deleted field numbers, or changing semantics without control can break the contract.

Key principles:

- Do not reuse published field numbers.
- Use `reserved` for removed field numbers/names when appropriate for the schema.
- Check unknown enum values and default semantics.
- Check `protoc` version, generated classes, and the runtime library.
- Ensure old consumers can ignore new fields per contract.
- Check changes affecting the binary/source API of generated Java code.

### 13.4. Java Native Serialization for Messages

If a message payload is a `Serializable` object or a framework binary serializer tied to FQCNs, failures can occur when upgrading the JDK, changing class hierarchies, or changing dependency versions. This is similar to caches/sessions but often more dangerous because message data cannot simply be skipped.

For long-lived contracts or those with multiple producers/consumers, prefer schemas and encodings managed independently of implementation classes. If old binary formats must be kept, build a bounded compatibility reader with a separate migration plan, and avoid having the new producer emit payloads that old consumers cannot understand.

## 14. Rollout Order: Upgrade Readers Before Writers

For message schemas or shared state schemas, a helpful principle is **readers support the new format before writers emit it**.

~~~text
T0:  Producer v1 -> schema v1 -> Consumer v1

T1:  Producer v1 -> schema v1 -> Consumer v2
     (Consumer v2 can read both v1 and v2)

T2:  Producer v2 -> schema v2 -> Consumer v2
     (Enable schema v2 only when no incompatible consumer v1 remains)

T3:  Wait for retention/retry/replay windows needing schema v1 support to expire

T4:  Remove parser v1 once no old data sources remain
~~~

This is the **expand–migrate–contract** pattern:

1. **Expand:** expand readers and schemas to support both old and new versions.
2. **Migrate:** move writers, lingering data, and consumers to the new format.
3. **Contract:** stop writing v1, wait for v1 data to finish its lifecycle, and only then remove compatibility code.

With **rollback**, the ordering can be trickier. If producer v2 has already emitted schema v2 that consumer v1 does not understand, rolling back only the consumer to v1 can cause errors. Choose one of these options: keep consumer v2 able to read schema v2, use message contract v1 during the rollback window, or ensure a bridge/adapter.

## 15. Dual-Read, Dual-Write, and Migration Variants

### 15.1. Dual-Read

The new reader attempts to read the new schema; if it encounters a clearly identified v1 payload, it uses an adapter to convert it into the current domain model.

~~~text
Reader v2
  -> detect schemaVersion
  -> parse v1 / parse v2
  -> normalize to internal model
  -> validate business invariants
  -> execute operation
~~~

Distinguish between a **valid v1 payload** and a **corrupted payload**. Do not treat every parse failure as v1 and fall back unconditionally, as that can mask corrupted or tampered data.

### 15.2. Dual-Write

In some cache or state-store migrations, the new version writes both v1 and v2 formats. This prevents old readers from being left behind, but carries risks:

- The two records are not updated atomically.
- Writing v1 succeeds while v2 fails, or vice versa.
- It becomes unclear which copy is authoritative.
- TTLs drift out of sync.
- Write volume and storage costs increase.
- Sensitive data is duplicated, creating additional security risk.

Use dual-write only with an explicit consistency and retry policy. For business events, emitting two parallel messages for the same action can cause consumers to execute twice. When migrating event formats, use an adapter or explicitly designed version routing with idempotency/dedup.

### 15.3. Shadow-Read and Canary

One risk-reduction technique is having the new version read v1 data in **shadow mode** without using the result for business decisions yet. Compare parse results, schema validation, and latency against the old reader. Do not log payloads containing PII or tokens for comparison.

A canary rollout lets a small slice of traffic/sessions be processed by v2 before scaling out. However, with shared caches or queues, a canary writer can emit v2 data to all consumers, including v1. Therefore, **an application canary does not automatically isolate the data contract**: use versioned namespaces, separate topics/queues, or feature flags on writers.

## 16. Retry, Redelivery, Idempotency, and Late Messages

Brokers and consumers typically operate with at-least-once delivery. A message may be redelivered after a timeout, crash, or retry. Bumping the application version does not eliminate the possibility of redelivery.

Design consumers so that processing the same event repeatedly does not produce unintended side effects.

Example message:

~~~json
{
  "messageId": "41e64ab9-3313-4311-8d2d-99162808b9bd",
  "schemaVersion": 1,
  "eventType": "payment.authorized",
  "payload": {
    "paymentId": "PM-309",
    "orderId": "O-18025"
  }
}
~~~

The consumer can record `messageId` in an inbox/dedup table and execute business logic within an appropriate transaction. When deploying v2, **do not wipe dedup state** merely because the service version changed; otherwise, a retried v1 message could be processed a second time.

### 16.1. "Exactly Once" Must Be Scoped

A streaming platform may provide an exactly-once mechanism for certain internal operations without automatically guaranteeing that side effects in databases, payment gateways, or external APIs happen only once. Consider idempotency keys, transaction boundaries, and replay semantics.

### 16.2. Ordering and Message Keys

A new message may change how the partition key or grouping is computed. Even if the schema is readable, the processing order of events for the same entity can change. For instance, `order.created` and `order.cancelled` may arrive at different consumers or be reordered if the partitioning strategy changes.

During migration, keep business keys stable if the ordering contract relies on them, or redesign them in a separate rollout with concurrency testing.

### 16.3. Dead-Letter Queues Are Historical Data Stores

DLQs sometimes retain payloads for weeks or months. During replay, current tools must be able to read old schemas or have a migration job.

Do not delete parser v1 merely because the main topic has no v1 messages left. Inventory DLQs, retries, backups, reprocessing jobs, and event archives as well. For poison messages, separate schema errors from business errors to avoid infinite retry loops.

## 17. Transactional Outbox and Pending Events

A common pattern is writing a business change and an outbox event within the same database transaction, after which a relay publishes the event to the broker.

~~~text
Business transaction
  -> update order table
  -> insert outbox row (schema v1)
  -> commit
           |
           v
     Outbox relay v2
           |
           v
       Event broker
           |
           v
      Consumer v2
~~~

If the relay upgrades to v2, it may encounter unpublished v1 outbox rows. In that case, the relay must know how to read and emit the proper contract for older rows. If the relay automatically re-serializes all rows into schema v2, verify that old consumers/partners can accept them.

Outbox attributes to monitor:

- Payload schema version.
- Message ID/idempotency key.
- Publishing status, retry count, next attempt time.
- Ordering by aggregate/business key if needed.
- Transaction boundaries and no-loss/no-duplication event guarantees.
- Retention period of outbox rows and replay capability.

Also check inbox/dedup tables across migration; deleting or changing the key format can cause old messages to be processed repeatedly.

## 18. Caches, Sessions, and Messages Have Different Time Windows

An operational mistake is picking the same "wait 24 hours then delete the compatibility layer" cutoff for every kind of state.

| Data type | Factors governing lifetime | How to verify old data is gone |
|---|---|---|
| Derived cache | TTL, refresh, old writers, restore | Observe versioned keys, TTL, traffic, write sources |
| Session | Idle timeout, max lifetime, refresh, user activity | Session counts by schema version, logout/reissue policy |
| Access token | `exp`, key overlap, clock skew | Verification metrics by `kid`/token version |
| Refresh token | Rotation/revocation policy | Token metadata inventory and maximum lifetime |
| Broker event | Retention, consumer lag, replay | Offsets, schema distribution, backlog, DLQ |
| Delayed/retry message | Maximum delay, retry backoff, manual replay | Retry queue/DLQ metrics and policy |
| Outbox | Relay lag, retries, and manual recovery | Pending rows by schema version |
| Backup/snapshot | Retention and restore policy | Test restore with the current reader |

The milestone for removing reader v1 must be decided based on **which data sources can genuinely reappear**, not simply when the v2 deployment finished.

## 19. Testing with Realistic Yet Safe Data Fixtures

To prove compatibility, you need a set of **golden fixtures** representing previously emitted data. Each fixture should record:

- Producer version/JDK/vendor or build ID if available.
- Serializer and schema version.
- Payload with PII/secrets safely stripped or anonymized.
- Post-parse expectations: domain values, defaults, validation results.
- Behavior on unknown fields/enums, missing fields, or corrupted data.
- Appropriate timestamps/TTLs/expirations.
- Cases involving possible rollback or replay.

Example fixture structure for a test:

~~~text
fixtures/
  cache/
    price-v1.json
    price-v2.json
    cart-java8.ser
  sessions/
    anonymous-v1.json
    authenticated-v1.json
    expired-session-v1.json
  messages/
    order-created-v1.json
    order-created-v2.json
    order-cancelled-legacy.json
    unknown-enum-v2.json
~~~

This is an example of organizing test artifacts, not a directive to commit raw session tokens or binaries containing private data into the repository. If a fixture is a Java serialized binary, generate synthetic test data in an isolated environment and never deserialize content obtained from untrusted sources.

### 19.1. Minimum Test Matrix

| Test | Input | Reader/runtime | Expectation |
|---|---|---|---|
| Cache v1 read by v2 | Old cache fixture | App v2/new JDK | Reads accurately or controlled cache miss |
| Cache v2 read by v1 | New cache fixture | App v1/old JDK | Passes if required by rolling/rollback |
| Old session on new node | Session created by v1 | App v2 | Still authenticates, expiry accurate |
| Session after key rotation | Old token/key | Auth v2 | Verifies within overlap window |
| Old event awaiting consumption | Event v1 | Consumer v2 | Processes properly, no duplicate side effects |
| New event hits old consumer | Event v2 | Consumer v1 | Allowed only if contract is compatible |
| Replay from DLQ | Message v1 | New replay tool | Reads/routes/acks properly |
| Pending outbox | Row v1 | Relay v2 | Emits one logical message per policy |
| Corrupted/unknown schema | Malformed payload | Reader v2 | Fails safely in a controlled manner, no silent corruption |
| Mixed deployment | W1/W2 and R1/R2 | Mixed cluster | No dropped sessions, no wrong-format writes |

Tests must distinguish **expected pass** from **expected safe failure**. For example, an unknown schema may need to be rejected or routed to the DLQ, rather than always parsed.

### 19.2. System-Level Testing

A valuable integration test:

1. Start v1 with real Redis/broker/test database.
2. Have v1 write cache entries, create sessions, emit v1 events, and leave some messages unconsumed.
3. Stop part of v1 or introduce v2 while data still remains.
4. Have v2 read those old keys/sessions/messages.
5. Keep v1 and v2 running concurrently if the real rollout has a mixed-version phase.
6. Have v2 write new data and verify v1 can read it where required.
7. Stop v1 while backlog/retries/DLQ still exist, and run v2 replay.
8. Test rollback according to the published artifact and schema contract.
9. Compare business outcomes and message counts before and after.
10. Save logs/metrics with sensitive data masked.

Running only unit tests with freshly created objects from v2 code misses most "state persisting across deployments" issues.

## 20. Diagnosing Common Errors

| Symptom | Cause to investigate | Useful evidence |
|---|---|---|
| `InvalidClassException` when reading cache/session | Java serialization class evolution or mismatched UID | Binary fixture, class name, `serialVersionUID` |
| `ClassNotFoundException` during deserialization | Class changed package, missing dependency, different loader | Name in stream, classpath, defining loader |
| JSON mapping exception | Field/type/enum change, different mapper config | Payload schema version and mapper settings |
| Sudden spike in cache misses | Key namespace changed, TTL/invalidation, decode failure | Hit/miss metrics by schema, source load |
| Users logged out after deploy | Session serializer, cookie/key rotation, or store config | Session read failures, cookie attrs, key IDs |
| Errors occur only when v1 and v2 pods run together | Two-way compatibility missing | W1/R2, W2/R1 tests |
| Kafka consumer lag increases | Parser/schema error or slow processing | Error rate, partition offsets, retries |
| DLQ grows after release | Unknown event version/field or business validation | DLQ reason/category and schema distribution |
| Event processed twice | Retries, dedup state wiped, or key changed | Message IDs, inbox records, side-effect logs |
| Outbox emits wrong format | Relay v2 reads v1 rows with v2 logic | Outbox schema metadata and payload |
| Wrong monetary amount/timestamp without exception | Semantic contract changed units/defaults | Golden fixture semantic assertions |
| Rollback fails | v1 cannot read v2 data | Forward-read compatibility results |

Classify errors by **source state and contract**. Do not "fix" every error by flushing Redis, ignoring unknown fields, or increasing retries indefinitely. Those workarounds can hide business data loss or trigger load spikes.

## 21. Post-Deploy Production Observability

Useful metrics:

**Cache**
- Hits, misses, deserialization errors, stale reads by cache schema version.
- Key counts per namespace, TTL distribution (within safe collection capabilities).
- Redis memory, evictions, latency, source-of-truth fallback load.
- Ratio of v1 writers still appearing during the mixed deployment window.

**Sessions and authentication**
- Sessions created/read by schema version.
- Session deserialization failures.
- Login rate, unexpected logouts, 401/403 rates by deployment version.
- Session expiry, refresh, and key rotation usage.
- Sticky node selection/replication/failover incidents.

**Messages**
- Consumer lag, backlog, and processing latency by topic/partition.
- Schema-version distribution of consumed messages.
- Retry/negative-ack/DLQ counts by cause category.
- Dedup hit rate, duplicate business operations, and outbox pending counts.
- Replay attempts, poison messages, and maximum processing time.

**Security and data**
- Count of old tokens/signatures still verified during the overlap window.
- Decrypt/verify errors, policy violations, and trust key changes.
- Do not put payloads containing PII, tokens, or secrets into logs merely to increase observability.

A dashboard tracking only HTTP 5xx is insufficient: a failing background consumer may produce no HTTP responses at all while backlog and DLQ climb steadily.

## 22. Deciding Between "Preserve Compatibility or Clear Old Data"

There is no single answer. Weigh data value, regenerability, security, allowable downtime, and user commitments.

### Can Invalidate/Rebuild When

- Data is purely cached, not the source of truth.
- Source-of-truth is complete and can withstand regeneration load.
- The stale-data window and performance degradation are acceptable.
- Deletion does not lose sessions, locks, idempotency records, or jobs.
- There is a controlled execution plan scoped by key prefix/partition.

### Need a Compatible Reader When

- User sessions must remain valid across deployments.
- Old messages must be processed.
- There is a backlog, retries, DLQ, or snapshot restore.
- Rolling deployment includes both v1 and v2.
- Rollback procedures require the old version to continue reading new data.
- Data is business or audit records rather than derived cache.

### Can Proactively Cut Sessions / Change Contract When

- There is a clear security reason or policy change.
- Users/partners are notified and have a re-login/reconnection path.
- Existing messages/jobs are migrated or handled separately.
- Downtime/maintenance windows are approved.
- Evidence confirms no unfulfilled business obligations are lost.

Unmanaged changes causing mass logouts can trigger operational incidents; however, keeping all sessions alive by weakening security checks is also not a valid goal.

## 23. A Safe Rollout Roadmap

### Phase 1 — Baseline and Inventory

- Identify v1 JDK/framework/serializer.
- List cache key prefixes, session stores, brokers, topics, DLQs, retry jobs, and outboxes.
- Document schemas, TTLs, retention, writers, readers, secret/key dependencies, and owners.
- Save safe golden fixtures for v1, including rare payloads.
- Measure current errors and latency for a comparison baseline.

### Phase 2 — Expand Read Capability

- Deploy reader v2 capable of understanding both v1 and required v2 formats.
- Add version detection and semantic validation.
- Keep writers emitting schema v1 while old consumers remain.
- Add per-schema telemetry and safe-fail handling for corrupted payloads.
- Test cache stampede protection, session expiration, and message retries.

### Phase 3 — Mixed Deployment

- Introduce a subset of v2 instances into the system.
- Ensure reader v1 only receives data it is proven able to read.
- If v2 must write schema v2, isolate using key namespaces, topics/versions, or feature flags so new data is not unintentionally delivered to v1.
- Test user session node switching, concurrent requests, and broker consumer-group rebalancing.
- Monitor background errors and DLQs, not just health checks.

### Phase 4 — Transition Writers and State

- Enable producer/writer v2 only once relevant consumers are ready.
- Migrate cache keys, session DTOs, or payloads via adapters/background migration when needed.
- Ensure outbox/retry/DLQ handle historical data.
- Record the timestamp when v1 writes stop and monitor remaining v1 schema volume.
- Prepare rollback procedures suited to v2 data already emitted.

### Phase 5 — Wait Out Data Lifecycles and Clean Up Old Contracts

- Wait out TTL/session max lifetime/message retention/retry/replay/backup policies.
- Verify no v1 writers remain active.
- Check whether DLQ/outbox/snapshots can still reintroduce v1 data.
- Remove reader v1 only with evidence that historical sources are exhausted or migrated.
- Remove feature flags and compatibility adapters in a separate release change with regression tests.

### Phase 6 — Evaluate Real Rollback

A rollback is not merely swapping the image from v2 back to v1. Once writer v2 has written:

- Caches may hold new keys/schemas.
- Sessions may contain new formats or security claims.
- Queues may contain new event schemas.
- Databases/outboxes may contain v2 rows.
- Tokens may be signed with a new key.

Therefore, determine **what the rolled-back v1 version can read** and whether a compatibility release must be kept instead of reverting to the original build. Do not mark "rollback ready" merely because the old container still starts.

## 24. Comprehensive Example: Upgrading JDK and Framework with Redis + Sessions + Kafka

Suppose an e-commerce platform runs a Java 11 application, Redis cache/sessions, and Kafka. The team wants to move to Java 21 and upgrade the framework; during this:

- Redis stores `ProductView` using Java serialization.
- Sessions contain a framework-serialized principal object.
- Kafka retains `order.created` JSON schema v1 in the topic for 7 days.
- Some failed events sit in the DLQ and may be replayed a month later.
- The system uses rolling deployments, with v1 and v2 running concurrently for a period.

### Risky Approach

1. Rename the `ProductView` package and change the principal structure.
2. Switch the Redis serializer to JSON with the same cache keys/session prefix.
3. Have the producer emit `order.created` schema v2 as soon as the first pod starts.
4. Flush all of Redis when errors happen.
5. Roll back to v1 when DLQ grows.

Consequences may include v1/v2 being unable to read each other's sessions, mass logouts, cache misses overloading the DB, consumer v1 failing to understand v2 events, and rollback still failing to handle already-emitted messages.

### Controlled Approach

**Step 1:** Separate derived caches from Redis sessions and idempotency keys; do not flush the whole database/prefix.

**Step 2:** Create golden fixtures from the v1 format for caches/sessions/events using synthetic test data containing no secrets.

**Step 3:** For derived caches, use namespace `product:v2` with the new JSON serializer, allowing bounded cache misses/rebuilds. Prevent v1 from misreading v2 keys.

**Step 4:** Keep the session serializer compatible or build a v1→v2 session adapter during the transition window. If impossible, design a migration with an explicit session cutoff rather than random failures.

**Step 5:** Kafka consumer v2 accepts both schema v1 and v2. While consumer v1 remains, the producer continues sending schema v1 or only adds new fields under a v1-compatible policy.

**Step 6:** Once no v1 consumers remain in groups reading the event, enable producer v2 to emit schema v2. Monitor schema distribution, lag, and DLQ.

**Step 7:** Keep parser v1 long enough for Kafka retention, DLQ, delayed retries, and replay policy; do not remove based solely on cache TTL.

**Step 8:** Test rollback. If v1 cannot read already-emitted schema v2, rollback requires a compatible release or an approved way to block/quarantine new payloads—not simply redeploying v1.

Reported results:

| Item | Required evidence |
|---|---|
| Cache v1/v2 | Read fixtures, hit/miss, source load, TTL, key namespace |
| Session | Old session on new node, new session on old node if needed, auth/expiry |
| Kafka | W1/R2 and W2/R1 across rollout stages, lag, DLQ, replay |
| Outbox/retry | Pending old schemas still processed, idempotency preserved |
| JDK/framework | Correct serializer/provider settings and classloading |
| Rollback | Artifacts, feature flags, data contracts, and real tests |

## 25. Common Misconceptions

**"Caches are cleared on deploy, so no migration is needed."** False for distributed/persistent caches and caches shared across multiple services.

**"Adding `serialVersionUID` is enough to make Java Serialization compatible."** False. Class/package names, field structures, custom serialization, and semantic invariants still matter.

**"The new producer and new consumer just need to understand each other."** Insufficient when old consumers, retries, DLQs, or old event replays remain.

**"JSON can ignore unknown fields, so any schema change is fine."** False. Required fields, enums, data types, and field meanings can break the contract.

**"Flushing Redis fixes session errors."** It can cause mass logouts and lose idempotency/locks if the same store holds other state types.

**"Once the broker acks, an event will never reappear."** Do not assume this in every system; account for redelivery, retries, replay, and side effects.

**"Rolling deployment is safe because every pod is healthy."** Insufficient. Readers/writers of different versions can still interact through the same storage or queue even when HTTP health checks are all green.

**"Wait for cache TTL to expire then delete the old parser for all data."** Insufficient for sliding session expiry, message retention, DLQs, outboxes, and backup restores.

**"Rollback is just rerunning the v1 image."** False if the data format was written one-way by writer v2 and cannot be read backward.

**"Parse errors can be ignored so the service keeps running."** For derived caches, a controlled fallback may work; for payment events, session security state, or business jobs, ignoring them can cause data loss and severe inconsistencies.

## 26. Checklist Before Upgrading JDK or Changing Data Contracts

- [ ] Listed every type of state that persists across restarts/deployments.
- [ ] Distinguished derived caches, sessions, idempotency state, locks, and durable messages.
- [ ] Identified producers/writers and readers/consumers for every payload.
- [ ] Recorded serializers, schema versions, key namespaces, TTLs, and retention.
- [ ] Verified the new JDK/framework can read v1 data fixtures.
- [ ] Verified v1 can read v2 data if required by rolling deploy/rollback.
- [ ] Checked Java Serialization class names, UIDs, custom serializers, and classloaders.
- [ ] Defined unknown fields/enums, null/default handling, and semantic compatibility.
- [ ] Accounted for TTL, sliding session expiry, token max lifetime, broker retention, retries, and DLQs.
- [ ] Checked session cookies, security key rotation, expiry, and user experience.
- [ ] Ensured consumers are ready before producers emit a new schema.
- [ ] Verified idempotency, dedup, and message ordering during retries/replays.
- [ ] Checked outbox/inbox and pending jobs.
- [ ] Avoided deleting keys or business messages with a blanket invalidation command.
- [ ] Ran integration tests with existing v1 data present when starting v2.
- [ ] Ran mixed-version and rollback tests reflecting real architecture.
- [ ] Put metrics in place for parse errors, cache misses, session failures, lag, and DLQs.
- [ ] Planned a retention period keeping reader v1 long enough for historical data lifecycles.
- [ ] Identified owners and required evidence before removing compatibility code.
- [ ] Protected PII, tokens, and passwords, and avoided deserializing from untrusted sources.

## 27. Conclusion

In Java Advance Compatibility Migration, **caches, login sessions, and messages are contracts that remain in force after the code version that created them has been replaced**. A deployment can succeed at the infrastructure level yet fail at the data level if the new version cannot read old payloads, the old version cannot understand new payloads, or historical data is processed wrongly due to changed field semantics.

The reliable method is to build an inventory by storage location and lifecycle, create v1 fixtures, test the W1/R1–W1/R2–W2/R2–W2/R1 matrix, use schema versions, and deploy **readers before writers**. For regenerable caches, switch namespaces or invalidate in a controlled way; for sessions and durable messages, preserve access and fulfill business obligations properly. Remove the old reader only after verifying TTL, session lifetime, broker retention, retries, DLQs, outboxes, and restore policies.

Compatibility across deployments is not merely the ability to load a file or parse a JSON document. It is a commitment that **data created yesterday still has meaning and is processed properly tomorrow**, even after the JDK, framework, class loaders, and application have changed.
