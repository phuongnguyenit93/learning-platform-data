# Redis clients, distributed caches, and connection re-establishment

Redis is commonly used as a distributed cache, temporary data store, message broker, or state store serving multiple Java instances. Applications access Redis through clients such as Lettuce, Jedis, or Redisson. A client may manage sockets, connection pools, event loops, topology, authentication, Pub/Sub subscriptions, and background tasks.

When an application uses CRaC (Coordinated Restore at Checkpoint), client and cache objects in the heap can be restored alongside the process. However, network connections and state on the Redis server continue to change independently during the checkpoint period. Redis may restart, fail over, switch primary, update topology, or evict idle connections. A subscription may be dropped, and invalidation events may be missed.

Therefore, the application must proactively manage the Redis client lifecycle: stop work using the client before the checkpoint, release or re-prepare connections according to the library's guidelines, and then create new connections, authenticate, discover topology, and restore subscriptions after restore. Only open traffic once Redis and essential features are ready.

## 1. Redis clients and distributed caches

Redis is a data store running independently from the Java process. The application communicates with Redis over the RESP network protocol. Java clients hide most protocol details and provide APIs to read, write, manage keys, execute transactions, use Pub/Sub, Streams, and other data structures.

An application can use Redis in several ways:

- **Cache-aside:** the application reads the cache first; on a miss, it reads the data source and writes the result into Redis.
- **Distributed cache:** multiple instances share a common set of keys and TTLs.
- **Session store:** stores user sessions or state.
- **Rate limiter:** counts requests and enforces rate limits.
- **Distributed lock:** coordinates access permissions across multiple instances.
- **Pub/Sub:** sends events to active subscribers.
- **Redis Streams:** stores messages with IDs, consumer groups, and pending state.
- **Client-side caching:** holds an L1 copy in application memory and receives invalidations from Redis.

These usage patterns have different recovery requirements. A GET command can be resent relatively simply; a write command, lock operation, transaction, or message processing needs result determination before retrying.

### 1.1. Components managed by a Redis client

Depending on the library, a Redis client may own or reference:

| Component | Role | Risk around checkpoint |
|---|---|---|
| Client object | Configures and creates connections | May already be closed or hold old configuration |
| TCP connection | Transmits commands and responses | Peer or network path may have expired |
| Connection pool | Manages multiple connections | Connections in the pool may be stale; borrowed connections need to be returned |
| Event loop / Netty resources | Handles asynchronous I/O | Threads and channels require an appropriate lifecycle |
| Cluster topology | Knows node and slot mapping | Primary or nodes may have changed |
| Pub/Sub connection | Receives events continuously | Subscriptions may be lost on disconnect |
| Stream consumer | Reads messages by consumer group | Messages may remain pending or need reclaiming |
| Client-side cache | Keeps a copy in the heap | May miss invalidations while the client is disconnected |

Not every library uses the same model. Some clients manage connections automatically and can reconnect on network interruptions while the JVM is running. Some clients use a pool to dispense short-lived connections. Some clients use an event loop and shared connections. Identify clearly which library, version, and component owns each resource.

### 1.2. Distributed cache is not the same as local cache

Redis is typically an L2 cache shared across multiple instances. A local cache in the heap is the L1 cache of each individual process.

~~~text
Instance A: L1 cache ─┐
                     ├── Redis (L2) ─── Database / source of truth
Instance B: L1 cache ─┘
~~~

After restore, instance A's local cache may contain stale data, while Redis has already been updated by instance B. The connection to Redis may become operational again, but that alone does not automatically synchronize the local cache.

The application needs a TTL, version, invalidation, or refresh policy to ensure L1 data remains consistent with the authoritative data.

## 2. What changes during a checkpoint?

Suppose an application takes a checkpoint at 09:00 and restores at 09:30. During those 30 minutes, Redis and the network infrastructure continue running:

- The Redis server may restart or be upgraded.
- Redis Sentinel may elect a new primary.
- Redis Cluster may change slot ownership.
- Load balancers, firewalls, or NATs may drop idle connections.
- ACL users or passwords may be changed.
- TLS certificates may be replaced or expire.
- Pub/Sub subscribers may lose connections and miss messages.
- Redis Streams consumer groups may have new messages or old pending messages.
- Cache keys may expire by TTL or be evicted.
- Local caches may miss invalidation events.

The Redis client object may still exist in the heap after restore. However, that object does not prove that the socket is still usable, the server is still on the same node, the subscription still exists, or local data is fresh.

~~~mermaid
sequenceDiagram
    participant A as Java application
    participant C as Redis client
    participant R as Redis server
    A->>C: GET / SET / SUBSCRIBE
    C->>R: TCP connection
    Note over A: Create checkpoint
    Note over C: Process is checkpointed
    Note over R: Redis continues running
    R->>R: Restart / failover / topology change
    Note over A: Restore process
    A->>C: Reuse restored client state
    C-->>A: Reconnect, error or stale state
    A->>R: Re-authenticate and discover topology
    R-->>A: Current server state
~~~

Some clients can automatically reconnect after ordinary network errors. However, TCP-layer reconnection does not automatically recover all application state. You must distinguish between the transport connection, Redis protocol state, subscriptions, consumer progress, and cache consistency.

## 3. Does automatic reconnect solve the entire problem?

Many Redis clients support automatic reconnect. When a socket disconnects while the application is running, the client can try to open a new connection and resume processing commands according to the library's policy.

This is useful, but it is not a guarantee that all operations will continue correctly after a CRaC restore.

Automatic reconnect typically cannot determine on its own:

- Whether a write command sent before the checkpoint was executed by Redis.
- Whether a Pub/Sub message sent while the subscriber was offline needs to be reprocessed.
- Whether a subscription needs to be recreated with the current handler and application state.
- Whether the local cache missed invalidations.
- Whether a Redis lock still belongs to the client or its lease has expired.
- Whether an in-progress transaction or pipeline can continue.
- Whether the cluster topology changed and all routes have been updated.
- Whether current credentials or certificates are still valid.

If the client has an official CRaC integration, consult the guide for that exact version. The integration may already register resources and handle the event loop, connections, or pool. Avoid closing the same resource a second time if the library already manages it.

If the client does not clearly support checkpoint/restore, a controllable strategy is typically to stop activity, close the client or connections via the library's proper API before the checkpoint, and then create a new client after restore.

### 3.1. Distinguishing reconnect and recreate

| Action | Meaning | When appropriate |
|---|---|---|
| Reconnect | Existing client tries to re-establish the transport connection | Library supports reconnect and internal state remains valid |
| Recreate connection | Close old connection, create new connection | Old socket or protocol state is untrustworthy |
| Recreate client | Create a new client object and resource manager | Client was shut down or event loop/pool must be reinitialized |
| Refresh topology | Update current nodes, slots, or primary | Redis Cluster/Sentinel changed |
| Resubscribe | Re-register channels/patterns | Pub/Sub or invalidation listener disconnected |
| Reconcile data | Reconcile local cache with authoritative data | Invalidations may have been missed while offline |

Do not call a generic reconnect method if the library does not provide one or if the client has already been completely shut down. A closed client may not be reusable; in that case, a new instance must be created.

## 4. Connection pool management

A connection pool holds multiple connections for reuse and reduces the cost of opening TCP/TLS connections. Applications using Jedis commonly use a pool model that lends one Jedis connection per operation or scope. Lettuce typically supports asynchronous connections and can use a single thread-safe connection for multiple commands in library-supported cases. Redisson manages connections and internal resources according to its configuration.

### 4.1. Borrowed connections

Before a checkpoint, the pool may have connections currently borrowed by a thread to execute commands. If the pool is closed while a connection is still in use, requests may fail mid-flight.

You must:

1. Stop accepting new requests that use Redis.
2. Stop workers and scheduled tasks that are sending commands.
3. Wait for running Redis operations to complete.
4. Ensure borrowed connections have been returned to the pool.
5. Close the pool/client according to the library's lifecycle.

Do not close the pool before borrowers finish. With a connection pool, monitoring active connections, idle connections, and waiting borrowers helps determine when it is safe to close.

### 4.2. Do not hold borrowed connections across a checkpoint

A connection borrowed from a pool should have a well-defined usage scope. Do not store a connection in a singleton field or hold it in a long-waiting task if the library expects connections to be returned after each operation.

With Jedis, a single Jedis instance should generally not be shared concurrently across multiple threads; use the pool as instructed by the library and return connections to the pool in a finally block or try-with-resources.

Illustrative example:

~~~java
try (Jedis jedis = jedisPool.getResource()) {
    return jedis.get("product:42");
}
~~~

In this model, calling close on the borrowed Jedis typically returns the resource to the pool according to the library's contract. Confirm the behavior of the version in use; closing the entire pool is a separate lifecycle operation.

### 4.3. Creating a new pool after restore

If the pool was shut down before the checkpoint, do not attempt to reuse that pool. Create a new pool from current configuration:

- Hostname or seed nodes.
- Port.
- TLS and trust configuration.
- ACL username/password or credential provider.
- Connection timeout and command timeout.
- Pool size and wait limits.
- Cluster/Sentinel discovery.
- Retry and health-check policies.

Do not persist static credentials inside a checkpoint if the platform can rotate secrets. After restore, re-read secrets from a managed source and initialize the client using the current configuration.

## 5. Redis Standalone, Sentinel, and Cluster

The reconnection strategy depends on the Redis topology.

### 5.1. Standalone

With Redis standalone, the client typically connects to a single hostname and port. After restore, the client needs to:

- Resolve the hostname via current DNS.
- Open a new TCP connection if the old connection is closed or stale.
- Re-authenticate.
- Verify the server responds.
- Confirm required commands are permitted.

If Redis is behind a proxy or managed endpoint, the endpoint may remain the same while the backend has changed. The client needs appropriate reconnect and health-check mechanisms.

### 5.2. Redis Sentinel

Sentinel monitors Redis and can coordinate failover to elect a new primary. A client holding an old primary address may continue sending writes to a node that is no longer primary.

After restore, the client needs to obtain the current primary information from Sentinel or the library's discovery mechanism. Do not hard-code a node address known before the checkpoint if the system uses failover.

Operations to verify:

- Connecting to the Sentinel endpoint.
- Discovering the current primary by master name.
- Creating a connection to the new primary.
- Handling replicas if the application reads from replicas.
- Updating the pool and retrying commands that can be safely resent.

### 5.3. Redis Cluster

Redis Cluster partitions the keyspace into hash slots and distributes slots across nodes. Clients typically need a topology map to route commands to the node owning the slot.

During a checkpoint, the cluster may reshard or fail over. An old client may hold an outdated topology map. Redis may return redirects such as MOVED or ASK; the client must handle them per protocol and update topology.

After restore:

- Connect to seed nodes or the cluster endpoint.
- Refresh topology.
- Update the slot map.
- Recreate or refresh connection pools for required nodes.
- Handle redirects and nodes that are no longer available.

The topology refresh API and redirect handling depend on the client. Use the library's cluster-aware features rather than building custom routing unless there is a special requirement.

## 6. Authentication, TLS, and secret rotation

Redis connections may use ACL username/password, TLS certificates, or a platform-managed authentication mechanism.

During a checkpoint:

- Passwords may be rotated.
- ACL users may be disabled or have their permissions changed.
- Client certificates may expire.
- The trust store may change.
- Secret providers may return new values.

After restore, the client must authenticate with the current configuration. If it still uses old credentials cached in the heap, reconnection may fail.

Several principles:

- Read secrets from the provider when creating the client or refreshing credentials.
- Do not write passwords, tokens, or certificate private keys to logs.
- Configure connect timeouts and auth timeouts.
- Distinguish authentication errors from network errors.
- Do not retry indefinitely with invalid credentials.
- If the client does not support changing credentials on an existing connection, create a new connection or client as instructed.

TLS also requires a new handshake when establishing a transport connection. The fact that a client object remains in the heap does not prove that old certificates or TLS sessions remain valid.

## 7. Pub/Sub and subscriptions after restore

Redis Pub/Sub delivers messages to subscribers that are active at the time the message is published. Pub/Sub is not a durable queue: messages published while a subscriber is offline are not automatically replayed when the subscriber reconnects.

This is a critical point when using CRaC.

### 7.1. What happens when a subscriber is checkpointed?

Suppose an instance subscribes to the channel `cache:invalidate`. When the instance is checkpointed:

- The TCP connection may be closed or dropped.
- The subscription may be removed by the server.
- Messages published while offline are not queued for the subscriber.
- The local cache may retain stale entries.
- After restore, the client reconnects but does not automatically know which messages were missed.

Therefore, resubscribing is not sufficient to guarantee cache consistency. The application must reconcile or invalidate the cache after reconnecting.

### 7.2. Pub/Sub recovery sequence

1. Stop processing new messages before the checkpoint.
2. Wait for running handlers to complete.
3. Close the Pub/Sub connection or use the client's CRaC integration.
4. After restore, create a new connection/subscriber.
5. Resubscribe to the required channels and patterns.
6. Compare versions or invalidate the local cache to account for missed messages.
7. Open traffic only when the cache state satisfies policy.

### 7.3. When durable messaging is needed, consider Redis Streams

If the application needs to read messages after offline periods, Redis Streams with consumer groups is better suited than Pub/Sub in many cases. Streams store messages by ID and track pending entries.

After restore, the consumer needs to:

- Reconnect and join the consumer group.
- Read new messages at the appropriate offset.
- Check pending entries of the old consumer.
- Reclaim messages that have been idle long enough according to policy.
- ACK only after business processing succeeds.
- Use idempotency to tolerate redelivered messages.

Do not ACK a message before business side effects have been durably recorded. If the process is checkpointed after ACKing but before the business commit, the message may be lost from the consumer's perspective.

## 8. Client-side caching and invalidation tracking

Some clients or integrations support client-side caching: the application keeps a copy of keys in local memory and Redis sends invalidations when keys change.

This mechanism can reduce round trips, but it depends on a tracking connection and receiving every invalidation.

If the process is checkpointed or the tracking connection is interrupted:

- Redis may not send invalidations while the client is offline.
- The local cache still holds pre-checkpoint values.
- After reconnecting, the client may need to re-register tracking.
- Missed invalidations are not necessarily replayed.

Therefore, unless you can prove the client library has a complete resync mechanism, clear or invalidate the L1 cache after restore before reusing it. Alternatively, compare generation/version from a trusted source.

A simple strategy is incrementing a generation counter when the local cache is re-established:

~~~java
public final class LocalCacheState {
    private final AtomicLong generation = new AtomicLong();

    public long currentGeneration() {
        return generation.get();
    }

    public void invalidateAllAfterReconnect() {
        generation.incrementAndGet();
    }
}
~~~

Entries can carry the generation at load time. When reading, the application only uses an entry if the entry's generation matches the current generation. This is an example of versioning in the application; it must be coordinated with the actual cache structure to delete or skip stale entries.

## 9. Redis locks, transactions, and commands with uncertain outcomes

Not all Redis operations can be retried in the same way.

### 9.1. Distributed locks

A lock typically has a lease or TTL. If the application is checkpointed longer than the lease, the lock may expire and another instance may acquire it. After restore, the old process might assume it still owns the lock.

Do not continue a critical section based solely on a lock object still existing in the heap. Ownership must be verified using an appropriate token/fencing mechanism. For critical operations, a fencing token allows the target system to reject an old writer once a new owner exists.

Before a checkpoint, finish critical sections and release locks if possible. If a lock cannot be released because the connection is already lost, wait for the lease to expire and do not continue work based on old ownership.

### 9.2. MULTI/EXEC and transactions

An open Redis transaction or a pipeline with commands that have not received responses may have uncertain outcomes when the connection is lost. Do not retain old transaction state across a restore and assume it can continue.

Before a checkpoint, complete or discard transactions according to the client's API. If it is unknown whether EXEC was executed by Redis, inspect data state using an operation ID or idempotent design.

### 9.3. Retrying write commands

If the client sends SET, INCR, or a Lua script and the connection resets before receiving the response, the server may already have executed the command. Retrying can cause a second side effect, especially with INCR, LPUSH, or non-idempotent update operations.

Example:

1. Client sends INCR `counter`.
2. Redis executes and increments the counter.
3. The response is lost before the client receives it.
4. Client reconnects and resends INCR.
5. The counter increments twice.

For repeatable operations, use a request ID, idempotency key, Lua script with ID check, or a data model that allows deduplication.

## 10. Retry and backoff strategies

After restore, Redis may not be ready immediately. It could be failing over, restarting, or updating topology. Retries need bounds and must avoid causing a massive simultaneous reconnection wave.

### 10.1. Exponential backoff and jitter

An illustrative retry schedule:

| Attempt | Wait interval |
|---|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1.6 s |
| 5 | 3.2 s |

Set a maximum wait interval and add random jitter. If multiple instances restore simultaneously, jitter helps prevent all clients from reconnecting at the exact same moment.

### 10.2. Classifying errors

| Error | Handling |
|---|---|
| Connection refused or timeout | Retry with backoff |
| Connection reset | Create new connection; evaluate prior command outcome |
| MOVED or ASK | Use a cluster-aware client to update routing |
| Authentication failure | Refresh credentials or report configuration error |
| TLS handshake failure | Check certificates, trust store, and expiration |
| NOAUTH / NOPERM | Check ACL and command permissions |
| OOM or Redis resource limit | Do not retry aggressively; address capacity |
| Wrong type or data error | Fix logic or data; retrying will not resolve the root cause |

Do not retry configuration, ACL, or data errors indefinitely. A circuit breaker and recovery time limit help protect Redis from a loop of failing requests.

### 10.3. Fallback when Redis is not ready

Fallbacks may include:

- Returning data from the database.
- Using still-valid local cache entries.
- Returning a temporary error.
- Keeping readiness at NOT_READY.
- Pausing jobs that require Redis.

Not every application should fall back to the database. If Redis is used to offload the database, having all instances fall back together after restore can cause a database stampede. For permission, session, or distributed lock data, an improper fallback can cause security or consistency failures.

## 11. Integrating a Redis client with CRaC Resource

One way to organize this is to use a resource that owns the Redis runtime. The resource is responsible for stopping activity, closing the old runtime, and creating a new runtime after restore.

The example below uses application-defined abstractions to avoid coupling the lifecycle to a specific library's API:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class RedisCheckpointResource implements Resource {

    private final RedisRuntimeFactory runtimeFactory;
    private final RedisWorkCoordinator workCoordinator;
    private final CacheReconciler cacheReconciler;

    private volatile RedisRuntime runtime;

    public RedisCheckpointResource(
            RedisRuntimeFactory runtimeFactory,
            RedisWorkCoordinator workCoordinator,
            CacheReconciler cacheReconciler) throws Exception {

        this.runtimeFactory = runtimeFactory;
        this.workCoordinator = workCoordinator;
        this.cacheReconciler = cacheReconciler;

        this.runtime = runtimeFactory.createAndConnect();
        this.runtime.verifyReady();

        Core.getGlobalContext().register(this);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        // Stop accepting new work that uses Redis.
        workCoordinator.stopAccepting();

        // Complete running commands and process messages according to policy.
        workCoordinator.drainInFlight();

        // Stop Pub/Sub listeners and consumers before closing transport.
        workCoordinator.stopListenersAndConsumers();

        RedisRuntime oldRuntime = runtime;
        runtime = null;

        if (oldRuntime != null) {
            oldRuntime.close();
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {

        RedisRuntime newRuntime = runtimeFactory.createAndConnect();

        try {
            newRuntime.verifyReady();

            // Reconcile local cache because invalidations may have been missed.
            cacheReconciler.reconcile(newRuntime);

            // Restore subscriptions/consumers after the connection is ready.
            newRuntime.restoreSubscriptionsAndConsumers();

            runtime = newRuntime;
            workCoordinator.attach(newRuntime);
            workCoordinator.resumeAccepting();

        } catch (Exception e) {
            newRuntime.close();
            workCoordinator.markUnavailable();
            throw e;
        }
    }
}
~~~

The types RedisRuntimeFactory, RedisWorkCoordinator, CacheReconciler, and RedisRuntime are application-defined abstractions, not classes from Lettuce, Jedis, or CRaC.

The example illustrates the order of responsibilities:

1. Stop accepting new work.
2. Drain running commands and handlers.
3. Stop listeners and consumers.
4. Close the old client runtime.
5. After restore, create a new runtime and verify the connection.
6. Reconcile the local cache.
7. Restore subscriptions/consumers.
8. Re-open admission.

In production, steps require specific timeouts and error handling. If reconnection fails, the application must not open traffic that uses Redis. Appropriate readiness or degraded states are required.

### 11.1. Note on errors in beforeCheckpoint()

If a preparation step fails after admission has stopped or listeners have closed, the application must have a recovery path. CRaC Resource provides callbacks before checkpoint and after restore; do not assume an afterCheckpoint callback will automatically reopen components if checkpoint creation is aborted.

If the application initiates the checkpoint itself, the calling coordinator can catch the error and perform a rollback: recreate the Redis runtime, resubscribe, reconcile the cache, and then reopen admission. If recovery is impossible, keep the instance in an unavailable state.

### 11.2. Avoiding closing a resource twice

If the library already has CRaC integration, it may register resources itself for connections or event loops. Do not create another resource that closes the same connections and pools without clear ownership.

Choose a single owner for each component:

- Client runtime owns the event loop.
- Pool owns pooled connections.
- Subscription manager owns listeners.
- Cache manager owns the local cache.
- Lifecycle coordinator orchestrates the overall order.

## 12. Examples with Lettuce and Jedis

Two popular libraries have different usage models. API details can change across versions, so cross-reference documentation for the exact version.

### 12.1. Lettuce

Lettuce uses Netty and supports synchronous, asynchronous, and reactive APIs. Some Lettuce connections can be shared across multiple threads according to the library's contract. ClientResources manages underlying resources such as event loops.

When integrating CRaC, consider:

- Whether stateful connections are currently in use by any request.
- Who owns ClientResources and the event loop.
- Whether individual connections can be closed or the client must be shut down.
- Whether reconnect is enabled and how it is configured.
- How cluster topology refresh operates.
- Whether Pub/Sub connections need to be recreated and resubscribed.
- Whether client-side caching must be invalidated after the tracking connection is lost.

If you shut down RedisClient or ClientResources, do not assume you can call connect again on the same shut-down object. A factory creating a new client and resource manager after restore may be required.

### 12.2. Jedis

Jedis is typically used in a connection pool model. A Jedis instance is borrowed from the pool for an operation or a short scope and should not be shared concurrently across multiple threads.

Considerations:

- No connection is currently borrowed when closing the pool.
- Borrowers always return connections to the pool.
- The pool is recreated after shutdown if the implementation does not support reopening.
- Sentinel or Cluster configuration is used to discover current topology.
- Pub/Sub listeners are stopped and recreated.
- Stale connections are evicted according to pool policy.

Example of scoped connection borrowing:

~~~java
try (Jedis jedis = jedisPool.getResource()) {
    jedis.set("warmup:status", "ready");
}
~~~

The code snippet illustrates borrowing and returning a resource. Do not use a single Jedis instance as a field shared by multiple threads. Closing JedisPool is a pool-level lifecycle operation and must be coordinated separately.

### 12.3. Redisson and other clients

Redisson provides higher-level abstractions for maps, locks, topics, semaphores, and many distributed structures. Objects like RMap or RLock typically depend on RedissonClient and underlying connections.

After restore, determine:

- Whether RedissonClient has a corresponding CRaC integration.
- Whether Netty/event loops are recovered properly.
- Whether lock leases are still valid.
- Whether topic listeners need to be re-registered.
- Whether local cached maps need to be invalidated.
- How a shut-down client can be replaced with a new client.

Do not assume an API object such as RMap can keep functioning simply because its reference remains in the heap.

## 13. Recovering Pub/Sub, Streams, and cache listeners

Continuous operations require separate procedures.

| Feature | Before checkpoint | After restore |
|---|---|---|
| Pub/Sub | Stop handler, unsubscribe/close connection | Resubscribe; reconcile missed events |
| Keyspace notifications | Stop subscriber | Resubscribe; do not treat notifications as a durable log |
| Redis Streams | Stop reading, process and ACK per policy | Join consumer group, inspect pending and reclaim |
| Client-side invalidation | Stop tracking listener | Recreate tracking; invalidate or resync L1 |
| Scheduled refresh | Pause scheduler and drain tasks | Recalculate schedule, create new scheduler if needed |

### 13.1. Pub/Sub does not store messages for offline subscribers

If the application must guarantee processing of every event during the checkpoint period, Pub/Sub may not meet the requirement. Consider Streams or a durable message broker. If Pub/Sub is still used for invalidation, combine it with versioning or invalidate the entire key group on reconnect.

### 13.2. Streams and pending entries

Redis Streams consumer groups track messages that have been delivered but not yet ACKed. After restore, messages may still sit in the pending entries of the old consumer.

A procedure is needed to:

- Check the pending count.
- Identify which consumer holds the messages.
- Reclaim messages that have been idle long enough.
- Reprocess them using an idempotent handler.
- ACK after business work completes durably.

Do not simply create a new consumer and read new messages while ignoring old pending entries.

## 14. Cache consistency after reconnecting

A ready Redis connection does not mean the local cache is synchronized. The application must choose one of the following approaches:

### 14.1. Invalidate all of L1

Simple and safe when the cache is small, data can be reloaded, and there is no reliable version. After restore, clear the local cache and reload on demand.

### 14.2. Invalidate by namespace

If only one group of data receives missed invalidation events, clear the corresponding namespace. This reduces cache misses compared to clearing everything.

### 14.3. Version or generation

Store the data version in Redis or the database. After restore, read the current generation and compare it with the cached generation. If different, ignore stale entries.

### 14.4. TTL and lazy refresh

Retain entries still within TTL if freshness policy permits. Expired entries are refreshed upon request. Single-flight is needed to avoid multiple requests refreshing the same key simultaneously.

### 14.5. Do not use stale cache for sensitive decisions

Permissions, tokens, sessions, balances, or lock states require strict policies. If data validity cannot be determined, check the source or reject the operation instead of using a stale value.

## 15. Observability and testing

Record the following states:

- Redis checkpoint preparation started.
- Redis work drained.
- Pool borrowers returned.
- Client runtime closed.
- Redis reconnect started/completed.
- Authentication and TLS succeeded.
- Cluster/Sentinel topology refreshed.
- Pub/Sub resubscribed.
- Streams pending entries reconciled.
- Local cache invalidated or version verified.
- Redis readiness changed.

Useful metrics:

| Metric | Purpose |
|---|---|
| Connection active/idle | Monitor pool and active connections |
| Reconnect attempts | Track transport recovery |
| Reconnect duration | Measure time to re-establish connections |
| Command timeout/error rate | Detect failed commands |
| Pool borrow wait | Detect connection starvation in pool |
| Topology refresh count | Track Sentinel/Cluster changes |
| Pub/Sub reconnect count | Detect disconnected subscribers |
| Stream pending count | Track un-ACKed messages |
| Cache invalidation count | Measure L1 data cleared |
| Time to Redis ready | Measure time until Redis is ready |
| Restore-to-application-ready | Measure time from restore to serving traffic |

Scenarios to test:

1. Restore immediately after checkpoint when Redis has not changed.
2. Restore after a period longer than the idle timeout.
3. Redis restarts during the checkpoint period.
4. Sentinel fails over to a new primary.
5. Cluster topology changes or slots are migrated.
6. ACL password or TLS certificate is rotated.
7. Pub/Sub messages are published while the subscriber is offline.
8. Client-side invalidation is interrupted.
9. Stream consumer has pending entries.
10. A write command was executed but the response was lost.
11. Reconnect fails temporarily and then succeeds.
12. Multiple instances restore simultaneously and reconnect together.
13. Redis remains unavailable beyond the timeout.
14. Local cache holds an old version after Redis has been updated.

The objective is to prove the application reconnects to the correct endpoint, authenticates properly, restores subscriptions, does not drop pending work, and does not serve stale local cache data outside policy.

## 16. Recommended implementation procedure

### Before checkpoint

1. Switch readiness to NOT_READY if requests require Redis.
2. Stop accepting new requests and jobs that use Redis.
3. Pause cache refresh schedulers.
4. Stop Pub/Sub handlers and Streams consumers.
5. Drain running commands and return borrowed connections to the pool.
6. Finish transactions or handle uncertain command states.
7. Close the Redis client/pool/resource according to the library's guidelines or CRaC integration.
8. Allow CRaC to proceed with creating the checkpoint.

### After restore

1. Read current configuration and secrets.
2. Create a new client, event loop, and connection pool if needed.
3. Connect and authenticate with Redis.
4. Refresh Sentinel/Cluster topology.
5. Verify the ability to execute essential commands.
6. Restore Pub/Sub subscriptions and Streams consumers.
7. Reconcile or invalidate the local cache.
8. Restart schedulers and background refreshes.
9. Switch readiness to READY.

If Redis is an optional dependency for some endpoints, capability-based readiness or degraded mode can be used. However, requests that require Redis must have a clear and safe fallback.

## 17. Common errors

| Error | Consequence | Handling |
|---|---|---|
| Reusing an old socket without checking | Command timeout or reset | Reconnect/recreate per client lifecycle |
| Closing the pool while borrowers are active | Requests fail mid-flight | Stop admission and drain borrowers |
| Reusing a shut-down client | Unable to create new connections | Create a new client runtime |
| Relying solely on auto reconnect | Lost subscriptions or stale cache | Resubscribe and reconcile state |
| Not refreshing Cluster topology | Sending commands to old nodes | Use cluster-aware topology refresh |
| Using credentials stored in the heap too long | Authentication failure | Read new secrets and re-authenticate |
| Ignoring Pub/Sub messages while offline | Local cache is not invalidated | Version check or invalidate L1 |
| Not handling Streams pending entries | Messages hang or are under-processed | Reclaim and process idempotently |
| Blindly retrying INCR or writes | Duplicated side effects | Idempotency key or result verification |
| Using an old lock after restore | Critical section runs after losing lease | Check ownership/fencing token |
| Opening traffic before Redis is ready | Bulk request failures | Readiness gate and timeout |
| All instances reconnecting at once | Redis overload | Backoff, jitter, and concurrency limits |

## 18. Redis client checklist for CRaC

### Ownership and connections

- [ ] Identify who owns the Redis client, pool, event loop, and listeners.
- [ ] No connections remain borrowed when closing the pool.
- [ ] Shut-down clients are recreated instead of attempting reuse.
- [ ] CRaC integration of the exact library version has been verified.
- [ ] Timeouts are set for connect, command, and pool borrow.

### Reconnect and topology

- [ ] Hostnames are resolved using current configuration.
- [ ] Sentinel primary or Cluster topology is refreshed.
- [ ] ACL and TLS are re-authenticated.
- [ ] Retries have bounds, backoff, and jitter.
- [ ] Configuration/authentication errors are classified separately.

### Subscriptions and data

- [ ] Pub/Sub listeners are re-registered.
- [ ] Missed cache invalidations are reconciled.
- [ ] Streams pending entries are checked and reclaimed according to policy.
- [ ] Local caches are invalidated or version-checked.
- [ ] Redis locks are not assumed to be still owned just because the object remains in the heap.
- [ ] Write commands have idempotency mechanisms where required.

### Readiness and operations

- [ ] Do not accept traffic before essential Redis dependencies are ready.
- [ ] Metrics exist for reconnect, pool, command errors, and readiness.
- [ ] A fallback policy exists that does not cause a database stampede.
- [ ] Failover, restart, credential rotation, and long-duration restore have been tested.
- [ ] Multiple instances reconnecting simultaneously have been tested.

## 19. Frequently asked questions

### Does a Redis client object remaining in the heap after restore mean the connection is still active?

No. The object's continued existence reflects only in-process state. The TCP socket, Redis server, proxy, network path, and protocol state may have changed. Connections must be verified or recreated according to the client lifecycle.

### Is automatic reconnect in Lettuce or other clients sufficient?

Do not assume so by default. Automatic reconnect may handle transport interruptions, but subscriptions, topology, pending commands, client-side cache invalidation, and business logic must be recovered under separate policies. Check the exact library version and CRaC support.

### Should RedisClient be shut down in beforeCheckpoint()?

If the application owns the client and the library requires creating a new instance after shutdown, this can be an appropriate strategy. Beforehand, drain all commands and listeners using the client. If the library has CRaC integration, follow the lifecycle defined by that integration to avoid double-closing.

### Does Pub/Sub resend missed messages upon reconnection?

No. Redis Pub/Sub does not store messages for offline subscribers. If events must be processed after reconnection, use Streams or a durable event source; for invalidation, compare versions or clear the local cache.

### Does Redis Streams require handling after restore?

Yes. Consumers must rejoin the group, check pending entries, and reclaim idle messages according to policy. ACK only after business work completes durably, and handlers should be idempotent.

### Should the local cache be retained after Redis reconnects?

Only if entries can be proven still valid via TTL, versioning, or a reliable invalidation mechanism. If the tracking connection was lost and events could have been missed, invalidate or reconcile L1 before reusing it.

### What should the application do if Redis is not ready after restore?

Keep readiness in a not-ready state for features that depend on Redis, retry with limits, and log errors. Only use fallbacks if data and business rules permit; avoid shifting all load onto the database.

### Can all Redis commands be retried after Connection reset?

No. A command may have already been executed by Redis while the response was lost. Retrying INCR, LPUSH, or a non-idempotent operation can cause duplicate side effects. An idempotency key, operation ID, or state check is needed before resending.

### Is a distributed lock still valid after restore?

Do not assume so. The lease may have expired and another instance may have acquired the lock. Verify ownership or use a fencing token before continuing a critical section.

## Conclusion

A Redis client is a collection of resources including connections, pools, event loops, topology, subscriptions, and cache state. After a CRaC restore, these objects may still exist in the heap while the Redis server, network path, credentials, subscriptions, or data have changed.

A safe workflow is to stop Redis work and drain connections before the checkpoint, then create or reconnect the client according to the library's contract, re-authenticate, refresh topology, resubscribe, and reconcile the local cache. Pub/Sub messages can be missed; Streams require handling pending entries; write commands need idempotency; distributed locks require lease verification. Open readiness only when Redis and essential capabilities are ready.
