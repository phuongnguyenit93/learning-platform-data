# Watching Changes, Caching, and Reconnecting with Curator

When using ZooKeeper as a service registry, each service instance is typically represented by a znode under the `/services` tree. Consumers need to know when instances are added, changed, or deleted so they can update their list of active endpoints. ZooKeeper provides watches to signal changes; Apache Curator adds recipes that make registering watchers, maintaining local caches, and handling reconnections easier.

In practice, consumers should not query ZooKeeper for every business request. A local cache such as Curator `ServiceCache` or `CuratorCache` holds the latest instance list and updates when changes occur. However, a cache is only a local view that can become stale during connection loss. Applications must still handle connection states, session expiration, ephemeral registrations, and data reconciliation after reconnecting.

## 1. Service registry structure in ZooKeeper

A simple model organizes services by name and each instance as its own znode:

```text
/services
  /inventory-service
    /instance-a
    /instance-b
  /payment-service
    /instance-c
```

Each instance znode stores a payload describing connection address and metadata, for example:

```json
{
  "name": "inventory-service",
  "id": "instance-a",
  "address": "10.20.1.15",
  "port": 8081,
  "metadata": {
    "zone": "ap-southeast-1a",
    "version": "2.4.1"
  }
}
```

In the standard model, an instance registers using an ephemeral znode. This znode is tied to the registering process's ZooKeeper session; when the session expires, ZooKeeper automatically deletes the ephemeral node. That cleans up instances whose clients lost their session, while also meaning the application must re-register once a new session is established.

ZooKeeper does not actively probe a service's HTTP health endpoint. An ephemeral node reflects the registering client's session state, not a guarantee that the application still processes requests cleanly. If business health checks are needed, add a separate check mechanism or integrate with a health-monitoring platform.

## 2. How ZooKeeper watches work

A watch is a mechanism for a client to receive notifications when a znode or its list of children changes. For example, a consumer can watch the children of `/services/inventory-service` to know which instances are currently registered.

Basic ZooKeeper watches have several important characteristics:

- Traditional watches are one-shot: after receiving an event, the client must register a new watch to keep listening.
- A watch event is a signal that data changed, not a complete event record that can be replayed.
- Multiple changes occurring between two reads may be observed as a single latest state; watches are not an event log guaranteeing delivery of every intermediate change.
- When a connection or session is interrupted, watchers must be re-established according to connection and session state.
- Upon receiving an event, the safe pattern is to re-read the current state rather than inferring the entire registry from a single event alone.

For example, if an instance is created and deleted rapidly before the consumer re-reads children, the consumer may only see the final list without observing both operations individually. Watches are therefore suited to maintaining a current view of the registry; if you need an audit trail of every change, use a separate event log or messaging system.

## 3. Curator helps manage watches and caches

Apache Curator provides higher-level abstractions over raw ZooKeeper APIs:

| Component | Purpose | When to use |
| --- | --- | --- |
| `CuratorFramework` | Manages connections, retries, and ZooKeeper operations | Almost all applications using Curator |
| `ServiceDiscovery` | Registers and queries service instances per Curator's recipe | Applications needing a ZooKeeper-based service registry |
| `ServiceCache` | Caches a service's instance list and notifies on changes | Consumers frequently looking up the same service |
| `CuratorCache` | Caches a znode or general znode tree, receiving create/change/delete events | Tracking metadata or custom-designed registry structures |
| `ConnectionStateListener` | Receives connection states `SUSPENDED`, `RECONNECTED`, `LOST`, etc. | Recovering caches and registrations when network/session changes |

For standard recipe-based service discovery, prefer `ServiceDiscovery` and `ServiceCache` because they understand Curator's service instance structure. Use `CuratorCache` when watching custom znode trees or when you need direct control over data mapping.

In modern Curator versions, `CuratorCache` is the preferred general cache API replacing older recipes such as `NodeCache`, `PathChildrenCache`, or `TreeCache`. Projects on older Curator versions may still use those APIs; check your exact version and documentation before upgrading.

## 4. Creating CuratorFramework and connecting to ZooKeeper

CuratorFramework manages the session with the ZooKeeper ensemble, retries operations according to the configured policy, and emits connection states to listeners.

```java
import org.apache.curator.RetryPolicy;
import org.apache.curator.framework.CuratorFramework;
import org.apache.curator.framework.CuratorFrameworkFactory;
import org.apache.curator.retry.ExponentialBackoffRetry;

public final class ZooKeeperClientFactory {

    private ZooKeeperClientFactory() {}

    public static CuratorFramework create(String connectString) {
        RetryPolicy retryPolicy = new ExponentialBackoffRetry(1_000, 5);

        CuratorFramework client = CuratorFrameworkFactory.builder()
                .connectString(connectString)
                .sessionTimeoutMs(60_000)
                .connectionTimeoutMs(15_000)
                .retryPolicy(retryPolicy)
                .build();

        client.start();
        return client;
    }
}
```

Initialize the client with the ensemble server list, such as `zk-1:2181,zk-2:2181,zk-3:2181`. `start()` initiates connection asynchronously; it does not mean the client is already connected. If the application needs to wait for initial connectivity, it can call:

```java
boolean connected = client.blockUntilConnected(15, TimeUnit.SECONDS);
if (!connected) {
    throw new IllegalStateException("Cannot connect to ZooKeeper ensemble");
}
```

Do not create a new CuratorFramework per request. Typically, a single client is managed for the application lifecycle and closed on shutdown.

## 5. Watching a service with ServiceCache

`ServiceCache` is a fitting choice when an application uses Curator Service Discovery. It keeps a service's instance list in memory and notifies when the cache updates.

Example initializing ServiceDiscovery and ServiceCache:

```java
import org.apache.curator.framework.CuratorFramework;
import org.apache.curator.x.discovery.ServiceCache;
import org.apache.curator.x.discovery.ServiceDiscovery;
import org.apache.curator.x.discovery.ServiceDiscoveryBuilder;
import org.apache.curator.x.discovery.ServiceInstance;
import org.apache.curator.x.discovery.details.JsonInstanceSerializer;

public class InventoryRegistry {

    private static final String BASE_PATH = "/services";

    private final CuratorFramework client;
    private final ServiceDiscovery<InstancePayload> discovery;
    private final ServiceCache<InstancePayload> inventoryCache;

    public InventoryRegistry(CuratorFramework client) throws Exception {
        this.client = client;

        JsonInstanceSerializer<InstancePayload> serializer =
                new JsonInstanceSerializer<>(InstancePayload.class);

        this.discovery = ServiceDiscoveryBuilder
                .builder(InstancePayload.class)
                .client(client)
                .basePath(BASE_PATH)
                .serializer(serializer)
                .build();

        discovery.start();

        this.inventoryCache = discovery.serviceCacheBuilder()
                .name("inventory-service")
                .build();

        inventoryCache.start();
    }

    public List<ServiceInstance<InstancePayload>> getInstances() {
        return inventoryCache.getInstances();
    }

    public void close() throws IOException {
        inventoryCache.close();
        discovery.close();
    }
}
```

`InstancePayload` is an application-defined payload class whose structure must be compatible with the chosen serializer. This example focuses on cache lifecycle; in real applications, manage `CuratorFramework`, `ServiceDiscovery`, and `ServiceCache` as Spring beans or lifecycle components so they close in the proper order.

Registering an instance with `ServiceDiscovery`:

```java
ServiceInstance<InstancePayload> instance = ServiceInstance
        .<InstancePayload>builder()
        .name("inventory-service")
        .id("inventory-10-20-1-15-8081")
        .address("10.20.1.15")
        .port(8081)
        .payload(new InstancePayload("2.4.1", "ap-southeast-1a"))
        .build();

discovery.registerService(instance);
```

With Curator Service Discovery's default dynamic registration type, instances are typically stored as ephemeral znodes. If your application designs custom persistent nodes or another registration type, make clear who is responsible for cleaning up stale records.

## 6. Receiving notifications when ServiceCache changes

Consumers can register a `ServiceCacheListener` to react when the instance list updates or connection state changes:

```java
import org.apache.curator.framework.CuratorFramework;
import org.apache.curator.framework.state.ConnectionState;
import org.apache.curator.x.discovery.ServiceCacheListener;

inventoryCache.addListener(new ServiceCacheListener() {

    @Override
    public void cacheChanged() {
        List<ServiceInstance<InstancePayload>> instances =
                inventoryCache.getInstances();

        // Rebuild an immutable local snapshot for request handling.
        updateRoutingSnapshot(instances);
    }

    @Override
    public void stateChanged(
            CuratorFramework client,
            ConnectionState newState) {
        handleConnectionState(newState);
    }
});
```

Listeners should do concise work: read the current snapshot, update an immutable data structure, or signal another component. Avoid long network calls, blocking operations, or heavy business logic inside callbacks because they can stall the event-processing thread.

After `inventoryCache.start()`, the application can read `getInstances()` to fetch the current snapshot. If you need to know the cache has completed initialization before accepting traffic, build a readiness barrier using the mechanism of your Curator version and mark the consumer ready only after the appropriate initialization signal. Do not treat calling `start()` alone as proof that the cache is populated.

## 7. Using CuratorCache for custom znode trees

If the registry uses a custom schema, `CuratorCache` lets you watch znode creates, changes, and deletes under a path. Example watching `/services/inventory-service`:

```java
import org.apache.curator.framework.CuratorFramework;
import org.apache.curator.framework.recipes.cache.CuratorCache;
import org.apache.curator.framework.recipes.cache.CuratorCacheListener;

CuratorCache cache = CuratorCache.builder(
        curatorFramework,
        "/services/inventory-service"
).build();

CuratorCacheListener listener = CuratorCacheListener.builder()
        .forCreates(node -> onInstanceCreated(node))
        .forChanges((oldNode, newNode) -> onInstanceChanged(oldNode, newNode))
        .forDeletes(node -> onInstanceDeleted(node))
        .forInitialized(() -> markCacheInitialized())
        .build();

cache.listenable().addListener(listener);
cache.start();
```

Once the cache initializes, you can read the snapshot of nodes Curator holds:

```java
cache.stream().forEach(this::loadInitialNode);
```

`forInitialized` is useful for separating the initial cache population phase from subsequent updates. Exact API names and overloads may vary across Curator versions; use the API matching your project's dependency. If you need a consistent snapshot at the application layer, synchronize snapshot building with update callbacks so stale initial data never overwrites newer changes.

`CuratorCache` is a general-purpose znode cache. It does not natively understand service names, addresses, ports, metadata, or instance selection policies. The application must deserialize payloads, validate data, and map them to an instance model.

## 8. Why is a local cache useful?

Without a cache, every request might have to query ZooKeeper for the service instance list. That increases latency, puts load on the ensemble, and ties business requests directly to ZooKeeper's responsiveness.

A cache helps:

- Read the instance list from local memory with low latency.
- Reuse snapshots across many requests.
- Update the list via watches/events instead of continuous polling.
- Reduce ZooKeeper reads on the request hot path.
- Retain recent data across brief interruptions, if application policy permits.

However, caching introduces stale-data risk. When a consumer disconnects, it may keep dead instances or miss newly registered ones. Therefore, the cache should carry freshness/connection state alongside it; never store just an endpoint list while ignoring the health of the underlying source.

A routing snapshot can include update timestamp, connection state, and instance list:

```java
public record RegistrySnapshot<T>(
        Instant updatedAt,
        boolean connected,
        List<ServiceInstance<T>> instances
) {}
```

When a callback receives a change, build a new immutable snapshot and swap the current snapshot with an atomic operation. Request threads only read the snapshot without mutating collections updated by listeners.

## 9. Curator connection states

Curator provides `ConnectionStateListener` so applications can observe ZooKeeper connection status. Common states include:

| State | Meaning | Suggested action |
| --- | --- | --- |
| `CONNECTED` | Initial connection established | Begin using the cache once initialization completes |
| `SUSPENDED` | Connection temporarily interrupted; session not yet confirmed lost | Mark data potentially stale; limit decisions relying on the newest registry state |
| `RECONNECTED` | Connection restored with a still-valid session | Verify cache/watches continue working and refresh snapshot if needed |
| `LOST` | Session expired | Treat ephemeral registrations tied to the old session as lost; re-register after obtaining a new session |
| `READ_ONLY` | Client connected in read-only mode if allowed by the ensemble | Do not perform write/register operations; read only when policy allows |

Listener example:

```java
curatorFramework.getConnectionStateListenable().addListener(
        (client, state) -> {
            switch (state) {
                case CONNECTED -> onConnected();
                case SUSPENDED -> markRegistryStale();
                case RECONNECTED -> reconcileAfterReconnect();
                case LOST -> handleExpiredSession();
                case READ_ONLY -> markReadOnly();
            }
        }
);
```

These states reflect Curator's connection/session, not the health of individual service instances. Never use `CONNECTED` to conclude every provider is healthy or `SUSPENDED` to conclude every instance has died.

## 10. Distinguishing SUSPENDED, RECONNECTED, and LOST

This is the most important part of handling reconnection:

### SUSPENDED: temporary connection loss

The client cannot currently communicate with ZooKeeper. The session may still be valid, but the application cannot be sure of the latest registry changes. The cache still holds prior data, so mark the snapshot as stale or degraded.

During this phase:

- Do not wipe out all instances just because the ZooKeeper connection dropped.
- Do not treat the old cache as guaranteed accurate.
- You may continue serving under a stale-read policy if business requirements accept it.
- Bound how long stale caches may be used and raise alerts if disconnection persists.

### RECONNECTED: connection restored

Curator has reconnected. If the session remained valid, the client's ephemeral nodes may still exist. Curator recipes can restore watching; the application should wait for the cache to update and reconcile its snapshot before marking the registry fresh.

Do not assume every event that happened during the disconnection was delivered sequentially. Traditional watches are not an event log. Re-read current state or use a cache recipe that manages resynchronization.

### LOST: session expired

`LOST` means the ZooKeeper session has expired. Ephemeral znodes tied to the old session were deleted by ZooKeeper. Curator can establish a new session upon reconnecting, but the application's ephemeral registrations must be recreated under the new session.

The application must:

1. Mark the old registration as no longer valid.
2. Wait for Curator to obtain a new session/connection.
3. Re-register the service instance using `ServiceDiscovery.registerService()` or the corresponding registration mechanism.
4. Verify the instance znode appears in the registry.
5. Wait for consumer caches to initialize/update before marking data fresh.

Curator recipes can manage part of internal watchers and lifecycle automatically, but do not assume every znode created manually by the application is restored automatically. Clearly define which component is responsible for re-registering ephemeral services.

## 11. Retry policy does not replace session recovery

Curator's `RetryPolicy` handles retrying operations on transient failures. For example, `ExponentialBackoffRetry` increases wait intervals between retries. Retries help with timeouts or brief drops, but cannot make an expired session valid again.

Distinguish clearly:

- **Operation retry:** retrying a read/write command after a transient error.
- **Reconnect:** re-establishing a connection to the ZooKeeper ensemble.
- **Session recovery:** handling when the old session expires and the client gets a new session.
- **Registration recovery:** recreating ephemeral znodes deleted due to session expiration.
- **Cache reconciliation:** resynchronizing the snapshot from current ZooKeeper state.

These steps are related but not identical. Configuring a retry policy alone is not enough to ensure a service instance reappears after `LOST`.

## 12. Registration recovery pattern after LOST

A component managing service registration can react to `LOST` and `RECONNECTED`. The code below outlines the lifecycle; adapt it to how your application creates `ServiceDiscovery` and your Curator version:

```java
public class RegistrationLifecycle implements ConnectionStateListener {

    private final ServiceDiscovery<InstancePayload> discovery;
    private final ServiceInstance<InstancePayload> localInstance;
    private final AtomicBoolean registered = new AtomicBoolean(false);

    public RegistrationLifecycle(
            ServiceDiscovery<InstancePayload> discovery,
            ServiceInstance<InstancePayload> localInstance) {
        this.discovery = discovery;
        this.localInstance = localInstance;
    }

    @Override
    public void stateChanged(CuratorFramework client, ConnectionState state) {
        if (state == ConnectionState.SUSPENDED) {
            markRegistrationUncertain();
            return;
        }

        if (state == ConnectionState.LOST) {
            registered.set(false);
            markRegistrationLost();
            return;
        }

        if (state == ConnectionState.RECONNECTED && !registered.get()) {
            registerAgain();
        }
    }

    private void registerAgain() {
        try {
            discovery.registerService(localInstance);
            registered.set(true);
            markRegistrationRestored();
        } catch (Exception e) {
            registered.set(false);
            scheduleRegistrationRetry(e);
        }
    }
}
```

This example illustrates the concept, not a complete retry implementation. In a real system, avoid duplicate registration when Curator recipes already self-recover registrations, handle races across callbacks, apply bounded retries with backoff, and verify the registration exists before updating status to succeeded. An idempotent registration manager can centralize this responsibility.

Do not run long blocking operations directly inside `ConnectionStateListener`. Offload recovery work to a managed executor to avoid blocking Curator's event thread.

## 13. Using the cache to choose an instance and call a service

Consumers read a snapshot from `ServiceCache` and then apply an instance selection policy. Simple example picking an instance from the list:

```java
public Optional<ServiceInstance<InstancePayload>> chooseInstance(
        List<ServiceInstance<InstancePayload>> instances) {

    if (instances == null || instances.isEmpty()) {
        return Optional.empty();
    }

    int index = ThreadLocalRandom.current().nextInt(instances.size());
    return Optional.of(instances.get(index));
}
```

This example only illustrates the selection step. In production, filter out invalid instances, check metadata/zone if required by policy, apply timeouts, and handle connection failures. If a request fails because an instance was just removed, the consumer can refresh the snapshot and try another instance when the operation is safe to retry.

Do not hold onto a selected `ServiceInstance` for too long and reuse it across many requests as an immutable address. Read the latest snapshot according to cache policy and handle errors when an instance no longer exists.

## 14. Avoiding race conditions when updating the cache

A consumer can receive multiple callbacks close together. If a callback mutates an `ArrayList` in place while request threads are reading it, the application may hit concurrency exceptions or observe a partially updated state.

A simple approach is to build an immutable snapshot and swap the reference using `AtomicReference`:

```java
public class InstanceSnapshotStore<T> {

    private final AtomicReference<List<ServiceInstance<T>>> current =
            new AtomicReference<>(List.of());

    public void replace(List<ServiceInstance<T>> instances) {
        current.set(List.copyOf(instances));
    }

    public List<ServiceInstance<T>> get() {
        return current.get();
    }
}
```

Cache callbacks obtain the updated list, validate data, and call `replace()`. Request threads only read the immutable list. If you also need to store `connected`, `updatedAt`, or `initialized`, group them all into one snapshot object and replace the entire object in one atomic operation so fields stay consistent with one another.

## 15. Handling stale caches and policies during ZooKeeper outages

No single policy fits every system. Decide explicitly whether consumers may continue using a stale cache or must stop calling services when ZooKeeper disconnects.

| Scenario | Common handling approach |
| --- | --- |
| Brief disconnection, recent cache | May continue using the old snapshot within an allowed time limit |
| Prolonged disconnection | Mark degraded, emit alerts, and restrict stale reads |
| `LOST` session on provider | Re-register ephemeral node and verify the new registration |
| `LOST` session on consumer | Wait for cache/watch resynchronization; do not treat old initialized state as proof of freshness |
| Cache not finished initializing | Do not mark registry-dependent flows ready yet |
| Empty instance list | Return an appropriate error, follow architectural fallback, or wait for registry; never fabricate fake endpoints |
| Instance recently deleted before cache receives event | Request timeouts/failures should trigger bounded refresh/retry |

If business logic requires routing strictly to currently healthy instances, a stale cache may not suffice. Use health checks, timeouts, circuit breakers, or an additional verification source. ZooKeeper session health does not equal application health.

## 16. Configuring timeouts, sessions, and retries

Three parameters typically need tuning:

- `sessionTimeoutMs`: duration ZooKeeper allows a session to go without contact before marking it expired. Too low causes frequent session loss on flaky networks; too high leaves ephemeral nodes around longer after a client actually dies.
- `connectionTimeoutMs`: time to wait when establishing an initial connection or a connection operation per Curator API.
- `RetryPolicy`: retry count and intervals when operations fail.

Configuration example:

```java
RetryPolicy retryPolicy = new ExponentialBackoffRetry(
        1_000,  // base sleep time
        5,      // max retries
        10_000  // max sleep time
);

CuratorFramework client = CuratorFrameworkFactory.builder()
        .connectString("zk-1:2181,zk-2:2181,zk-3:2181")
        .sessionTimeoutMs(60_000)
        .connectionTimeoutMs(15_000)
        .retryPolicy(retryPolicy)
        .build();
```

`ExponentialBackoffRetry` overloads depend on the Curator version; if your version lacks the three-argument overload, use the supported constructor. Choose timings based on network latency, failover time, and failure-detection requirements rather than copying example values blindly.

## 17. Testing watches, caches, and reconnection

A thorough test suite should simulate both normal registry changes and connection/session failures:

1. Start the ZooKeeper ensemble and CuratorFramework.
2. Start `ServiceDiscovery` and `ServiceCache`; wait for cache initialization.
3. Register instance A; confirm the listener receives the change and the snapshot contains A.
4. Register instance B; confirm the cache contains A and B.
5. Unregister A; confirm the cache drops A after updating.
6. Briefly cut network connectivity to the ensemble; confirm `SUSPENDED` state and the snapshot being marked stale.
7. Restore network before session timeout; confirm `RECONNECTED`, cache resumes watching, and snapshot reconciles.
8. Trigger session expiration; confirm `LOST`, ephemeral registration disappears, and provider re-registers with a new session.
9. Confirm the consumer sees the instance again after registration and cache converge.
10. Stop the application cleanly; confirm cache, discovery, and CuratorFramework close in proper order.

Do not check only whether callbacks fired. Verify cache contents after each phase, registration counts in ZooKeeper, session state, and actual reachability of endpoints. Reconnect tests need generous timeouts so they do not depend on thread scheduling or exact network recovery timing.

## 18. Common errors and diagnostics

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| No events received when znodes change | Watch not registered, cache not `start()`ed, or wrong path | Check base path, listener registration, and Curator logs |
| Only one change notification received | Using one-shot watch directly without re-registering | Use a Curator recipe or re-read and set a new watch |
| Cache empty right after `start()` | Cache still initializing asynchronously or registry has no instances | Wait for initialization signal and inspect znodes directly |
| Cache still holds deleted instance | Disconnected, event not yet delivered, or snapshot not refreshed | Check ConnectionState, watches, and reconcile current children |
| Instance disappears after reconnect | Session became `LOST` and ephemeral node was deleted | Check listener state and re-register instance |
| Instance does not reappear after `LOST` | Missing registration recovery or retries not succeeding | Check registration manager and znodes after new session becomes active |
| Callbacks slow down the application | Listener performs blocking work or network calls | Move processing to an executor and keep callbacks short |
| Requests hit stale addresses | Consumer holds instance URI too long or unbounded stale cache | Use timestamped snapshots, refreshes, and bounded retries |
| Duplicate instances appear | Non-unique instance ID or non-idempotent registration | Check path/ID and re-registration flow |
| ZooKeeper reports repeated session expirations | Session timeout too low, unstable network, or overloaded ensemble | Check latency, timeouts, GC pauses, and quorum health |

## 19. Closing resources according to lifecycle

CuratorFramework, ServiceDiscovery, ServiceCache, and CuratorCache all have lifecycles. Applications must close caches/listeners first, then ServiceDiscovery, and finally CuratorFramework if the application owns that client.

In Spring Boot, manage these via beans and `@PreDestroy` or `SmartLifecycle`. Avoid creating caches per request and forgetting to close them, as that leaks watchers, listeners, and memory resources.

If multiple service caches share one `ServiceDiscovery`, clearly define which component owns and closes `ServiceDiscovery`. Never let two beans close the same resource without an ownership convention.

## 20. Implementation checklist

- [ ] Choose `ServiceCache` for recipe-based service discovery or `CuratorCache` for custom znode trees.
- [ ] Understand that traditional ZooKeeper watches are one-shot and not an event log.
- [ ] Wait for cache initialization before marking consumer readiness.
- [ ] Read instances from local snapshots instead of querying ZooKeeper per request.
- [ ] Update snapshots immutably to prevent races between listeners and request threads.
- [ ] Monitor `SUSPENDED`, `RECONNECTED`, `LOST`, and `READ_ONLY`.
- [ ] Mark caches stale on disconnection and enforce stale-read limits.
- [ ] Re-register ephemeral services after session expiration when recipes do not handle it automatically.
- [ ] Use a retry policy for transient errors alongside dedicated session/registration recovery logic.
- [ ] Test instance create/change/delete, brief reconnects, and `LOST` sessions.
- [ ] Close caches, discovery, and CuratorFramework in the right order.

Curator reduces the complexity of watching changes and maintaining caches from ZooKeeper. `ServiceCache` fits a single service's instance list; `CuratorCache` fits custom znode trees. Both give consumers fast local snapshots, yet applications must still recognize stale data, distinguish reconnections from session expiration, and restore ephemeral registrations after `LOST`. Those practices keep service discovery dependable when the network or ZooKeeper ensemble experiences disruptions.
