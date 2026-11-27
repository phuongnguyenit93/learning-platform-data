# Key TTLs and metadata

In a Spring Integration flow using Redis, not all data shares the same lifecycle. A deduplication marker usually only needs to survive for a bounded window, whereas a synchronization checkpoint may need to survive across many restarts. Choosing the right TTL (time to live) and metadata storage strategy helps flows tolerate retries, restarts, and duplicate deliveries without losing essential state.

This lesson frames TTLs and metadata in the context of Redis adapters: messages enter a flow via an inbound adapter, route across a `MessageChannel`, and handlers read or update Redis state. The same principles apply whenever a flow coordinates Redis with files, SFTP, HTTP, JMS, AMQP, Kafka, or databases: keep message contracts stable and define explicitly which state must persist and for how long.

## 1. Distinguishing TTLs and metadata

A **TTL** is the lifespan during which a Redis key remains valid. Upon expiration, Redis removes the key from the keyspace. TTLs suit temporary data such as:

- Markers identifying accepted events to block duplicate deliveries within a time window.
- Transient processing states or job leases.
- Cached lookup results, short-lived tokens, or session information.

**Metadata** describes the progress or context of an integration flow and is normally smaller than payloads. Examples: last processed offset, last record ID, HTTP resource ETag, imported filename, or latest synchronization watermark. Metadata usually must survive application restarts so the flow resumes from the right position.

Both concepts can live in Redis yet serve different purposes. Never put a short TTL on a checkpoint merely because it is stored in Redis. Conversely, never keep deduplication markers forever when business rules only require a bounded deduplication window.

| Data | Typical lifecycle | Question to answer |
| --- | --- | --- |
| Idempotency key | Has TTL | For how long must a re-arriving event still be treated as duplicate? |
| Processing lease | Short TTL, renewable | How long may a worker hold processing ownership at most? |
| Checkpoint / offset | Usually no TTL | On restart, where must the flow resume? |
| ETag or cache metadata | Has TTL or replaced on source change | How often must the source be revalidated? |

## 2. TTL operates at the Redis key level

Redis tracks expirations per key. You can attach a TTL right when creating a key:

```redis
SET si:orders:dedup:event-8421 1 NX EX 86400
TTL si:orders:dedup:event-8421
```

`NX` creates the key only if it does not yet exist; `EX 86400` sets an 86,400-second expiration. This combination suits claiming an idempotency key over a 24-hour window. `TTL` returns remaining seconds; `-2` means the key does not exist, while `-1` means the key exists with no expiration.

Key points to remember:

- Re-running `SET` on a key without specifying a TTL normally clears the prior TTL. If an existing expiration must be preserved, use an intentional update command and check support in your Redis/client version.
- TTLs belong to the whole key. If multiple metadata entries share one Redis hash, setting a TTL expires the entire hash rather than individual fields.
- TTL is a data expiration mechanism, not a precision scheduler. Never rely on exact key expiration timing to trigger deadline-critical business actions.
- Redis may evict expired keys lazily on access or via background sweeps. Applications should not depend on millisecond-exact deletion times.

Size TTLs to the business window. For idempotency keys, TTL must cover the full window of possible resends, retries, and manual replays. Too short lets old events re-execute; too long wastes Redis memory on obsolete keys. When long-term deduplication is required, store durable idempotency constraints in a database rather than relying solely on TTL-bound keys.

## 3. Storing metadata with Spring Integration

Spring Integration defines the `MetadataStore` abstraction for reading, writing, and removing metadata key/value pairs. `RedisMetadataStore` is a Redis-backed implementation suited when multiple application runs or instances need shared progress state.

Example bean declaration:

```java
@Bean
MetadataStore integrationMetadataStore(RedisConnectionFactory connectionFactory) {
    return new RedisMetadataStore(connectionFactory);
}
```

A single-source sync flow can persist the last processed record ID:

```java
String checkpointKey = "erp:orders:last-id";

String lastId = metadataStore.get(checkpointKey);
// Read source after lastId, process a batch cleanly, then advance the checkpoint.
String nextId = batch.lastSuccessfullyProcessedId();

if (lastId == null) {
    metadataStore.putIfAbsent(checkpointKey, nextId);
} else if (!metadataStore.replace(checkpointKey, lastId, nextId)) {
    throw new IllegalStateException("Checkpoint was updated by another flow");
}
```

`putIfAbsent` helps initialize state; `replace` supports conditional updates against the prior value. If multiple consumers update one checkpoint concurrently, handle failed updates by re-reading and reconciling state. Even when a single consumer owns the source, document the single-writer assumption explicitly in the design.

`MetadataStore` defines a metadata persistence contract and passes no TTL arguments in `get`, `put`, or `replace`. Therefore, do not assume every metadata entry gets an independent TTL merely through this abstraction. When per-entry TTLs are needed, use separate Redis keys via `StringRedisTemplate`/`RedisTemplate`, or implement a `MetadataStore` with explicit expiration rules. Avoid mutating internal `RedisMetadataStore` keys directly; its storage layout is an implementation detail.

## 4. Creating keys with TTL from a handler

For temporary data, `StringRedisTemplate` lets you set value and TTL in one atomic operation. The example below creates a 48-hour deduplication marker:

```java
@Component
class OrderIdempotencyKeys {

    private final StringRedisTemplate redis;

    OrderIdempotencyKeys(StringRedisTemplate redis) {
        this.redis = redis;
    }

    boolean claim(String eventId) {
        String key = "si:orders:dedup:" + eventId;
        Boolean created = redis.opsForValue().setIfAbsent(
                key,
                "1",
                Duration.ofHours(48));
        return Boolean.TRUE.equals(created);
    }
}
```

`setIfAbsent` with a duration performs atomic conditional key creation in Redis. Only one consumer among contenders racing on the same `eventId` receives `true`; the others treat the event as already claimed. This snippet assumes `eventId` is a stable business ID supplied by the source. Never use `MessageHeaders.ID` as an idempotency key, because Spring Message IDs change when messages are recreated.

An inbound flow can receive messages from a Redis queue and forward them to a processing channel:

```java
@Bean
IntegrationFlow ordersFromRedis(RedisConnectionFactory connectionFactory) {
    return IntegrationFlow
            .from(new RedisQueueInboundChannelAdapter(connectionFactory, "orders:in"))
            .channel("orders.input")
            .get();
}
```

This flow illustrates the receive boundary. Handlers downstream of the channel extract `eventId`, check the idempotency key, and update metadata once processing succeeds. The adapter's serializer/deserializer configuration must match the producer's payload contract; never assume payloads arrive as Java objects unless both sides share that format.

**Note on marker ordering:** setting the deduplication marker before invoking business logic causes retries to skip incomplete work if the handler fails. Setting it only after business logic leaves a race or crash window between the two steps where concurrent consumers can duplicate work. A TTL-bound Redis key alone does not guarantee exactly-once external side effects. For critical database updates, use unique constraints on event IDs, transactions/outboxes, or business-layer idempotency. When using keys as leases, include an ownership token and verify the token on renewals and releases so an expired worker cannot delete a newer worker's lease.

## 5. Designing namespaces and lifecycle policies

Name keys by application, environment, flow, and purpose so they are easy to search, monitor, and clean up:

```text
si:{environment}:{flow}:{purpose}:{business-id}

si:prod:orders:dedup:event-8421
si:prod:erp:checkpoint:last-order-id
si:prod:catalog:etag:products
```

Key segments should be stable and standardized. Never put passwords, tokens, personal data, or full payloads inside key names. If a business ID might contain separator characters, sanitize or encode it before constructing keys.

Before picking a TTL, answer:

1. How long can the source resend a message, including retries and manual replays?
2. Can a worker take longer than the TTL to finish? If so, how are leases renewed?
3. Must metadata survive deployments, restarts, or consumer failovers?
4. When Redis is unreachable, should the flow stop and retry, route messages to an error channel, or proceed knowing duplicate risk exists?
5. Who owns cleaning up stale state and enforcing Redis memory limits?

Update checkpoints only after the corresponding batch succeeds. Updating checkpoints before side effects risks skipping unprocessed data if a failure occurs in between. Updating afterward requires batch re-runs to be safe or business-layer idempotency.

## 6. Common pitfalls and mitigations

| Scenario | Consequence | Mitigation |
| --- | --- | --- |
| TTL shorter than retry/replay window | Old events re-execute after key expires | Size TTL to real retry policies and replay horizons |
| Checkpoint given a short TTL | Flow restarts and re-reads old offsets or loses progress | Keep checkpoints durable; add TTL only with explicit recovery |
| Overwriting key via `SET` without TTL | Old TTL cleared; key lives longer than intended | Pass TTL atomically on write or verify TTL after updates |
| Multiple flows updating one checkpoint | One flow overwrites another's progress | Use conditional `replace`, partition checkpoints, or enforce single writer |
| Redis unreachable | Cannot check idempotency or persist progress | Pick fail-fast/retry or risk-assessed fail-open; route errors properly |
| Marker written before side effect, then handler fails | Retries falsely treat message as completed | Use controlled claim/complete state or durable target idempotency |

Never equate a successful Redis response with completed business work. Log `eventId`, flow name, processing status, and relevant checkpoints while omitting sensitive values. Useful metrics include keys created, duplicates detected, retry counts, Redis errors, and processing latency. During investigations, run `TTL`/`PTTL` on specific keys to check remaining lifetimes.

## 7. Verifying behavior before going live

For any flow using idempotency keys and checkpoints, test at least these cases:

- Send the same `eventId` twice within the TTL and confirm the second takes the duplicate branch.
- Resend after the TTL expires and confirm behavior matches your reprocessing policy.
- Restart the application and confirm checkpoints persist and processing resumes from the committed position.
- Run two concurrent consumers with the same `eventId` and confirm claiming grants ownership to only one.
- Make Redis temporarily unreachable and confirm retries/error flows follow the chosen policy.
- Force a handler failure after claiming the key to confirm recovery does not silently drop business work.

TTLs and metadata are integral parts of an adapter's operational contract. When you define explicitly which keys are ephemeral, which hold durable progress, who owns updates, and how Redis outages behave, Spring Integration flows become far easier to recover and observe.
