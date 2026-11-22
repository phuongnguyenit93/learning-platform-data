# In-Memory Caches and Post-Restore Refresh Strategies

An in-memory cache helps Java applications reduce latency by keeping frequently accessed data inside the process. When an application uses CRaC (Coordinated Restore at Checkpoint), the heap state saved in the checkpoint can carry along cache objects created earlier. After restore, those objects may still exist, yet the data inside does not automatically become fresh or remain accurate with respect to the source system.

While the process is checkpointed, data in databases, external services, configuration, access permissions, and business deadlines continues changing. A cache entry may have exceeded its TTL, a record may have been updated, a permission may have been revoked, or an endpoint may have changed. Therefore, a post-restore cache strategy must answer two separate questions: which data can be kept and which data must be checked, refreshed, or evicted before serving requests.

## 1. What Is an In-Memory Cache?

A cache is a temporary storage area for computed results or data so subsequent accesses do not have to repeat the full expensive operation. In Java, a cache can be a Map, a caching library, a specialized data structure, or a framework caching layer.

Simple example:

~~~java
Map<String, Product> productCache = new ConcurrentHashMap<>();

public Product findProduct(String id) {
    return productCache.computeIfAbsent(
        id,
        productRepository::findById
    );
}
~~~

The first time a product is accessed, the application reads from the repository and puts the result into the cache. Subsequent times, the application can return data from memory.

Caches are commonly used for:

- Infrequently changing application configuration.
- Product information, catalogs, or reference data.
- Database query results.
- Metadata and schemas.
- CPU-intensive computation results.
- Time-limited tokens or authentication information.
- DNS or service discovery metadata.
- Content fetched from external APIs.

Caches improve speed yet create an extra copy of data. This copy can diverge from the original data without clear update and invalidation policies.

### 1.1. Cache is not the primary data source

An ordinary cache is merely a copy serving fast access. The database, service, or source data store is what defines the authoritative state.

If the cache is lost, the application can usually reload data from the source. If the cache contains stale data, the application needs to know when using that data is permitted and when it must refresh.

Do not use an in-heap cache as the sole store for business state if the data must survive restarts, failovers, or deployments. For critical state, use a database, message broker, or an appropriate durable storage system.

### 1.2. Common types of caches

| Cache type | Examples | Characteristics |
|---|---|---|
| Reference data cache | Catalogs, country codes | Changes infrequently; can be kept longer if versioned |
| Query cache | Database read results | Can become stale when source data changes |
| Computation cache | Reports, aggregated results | Can be recomputed when needed |
| Configuration cache | Feature flags, endpoints | Can change independently of the process |
| Authentication cache | Access tokens, key metadata | Has expiration and security requirements |
| Discovery cache | DNS, service registry | Depends on network state and endpoints |
| Session cache | Sessions, user context | May depend on time and server state |

Each type has a different lifetime and consistency requirement. Therefore, you should not apply a single refresh policy across all caches in an application.

## 2. What Happens to Caches During Checkpoint and Restore?

CRaC saves process state so an application can be restored from a checkpoint. Objects on the heap, including Maps, cache entries, timestamps, and metadata, can be part of the saved state.

That means after restore, the application may see data loaded before checkpoint again. However, while the process is checkpointed:

- The database may have been updated.
- A record may have been deleted.
- Access permissions may have been revoked.
- Feature flags may have changed.
- Tokens may have expired.
- Cache entries may have exceeded their TTL.
- External services may have changed endpoints or versions.
- Distributed caches may have received invalidations from elsewhere while the process was inactive.

~~~mermaid
flowchart TD
    A["Running application"] --> B["Load data into cache"]
    B --> C["Create checkpoint"]
    C --> D["Heap and cache are saved"]
    D --> E["Time elapses"]
    E --> F["Source data changes"]
    F --> G["Restore process"]
    G --> H["Old cache appears in heap"]
    H --> I{"Is entry still valid?"}
    I -->|Yes| J["Can continue using"]
    I -->|No| K["Invalidate or refresh"]
    K --> L["Check data source"]
    L --> M["Serve requests"]
    J --> M
~~~

Checkpoint restores the process's memory state. It does not freeze databases, cache servers, DNS, authentication systems, or other services during the checkpoint period.

### 2.1. An existing object does not mean fresh data

Suppose a cache contains product price information at 09:00. The application creates a checkpoint at 09:05 and restores at 10:00. During that time, product prices may have changed.

After restore, the Map may still contain Product objects with old prices. Java does not automatically know that database records were updated. If the application immediately returns that object for a request, users may see outdated prices.

Similarly, a cache holding access permissions may still retain Permission objects after restore even if permissions were revoked. For security-sensitive or critical business data, re-verifying against the source is necessary.

### 2.2. Cache entries can carry references that are no longer valid

Caches do not hold only immutable data. They may retain:

- Entities managed by a persistence context.
- JDBC connections or HTTP responses.
- Objects containing sessions or transactions.
- Tokens and credentials.
- Native resources or handles.
- Objects dependent on a clock or service registry.
- Mutable collections shared across multiple threads.

Do not cache short-lived resources like transactions or connections merely because they are Java objects. Caches should prioritize data reusable independently of runtime resources.

### 2.3. Heap caches and out-of-process caches differ

A local cache in the heap can be saved with the checkpoint. An out-of-process cache, such as Redis or a cache service, continues existing independently and may be updated while the application is checkpointed.

After restore, the two caches may be out of sync:

- Local cache holds pre-checkpoint values.
- Distributed cache holds newer values.
- An invalidation event was sent while the application's consumer was inactive.
- The source data version has incremented.

Therefore, the application must determine which source is authoritative and how to resynchronize the local cache on restore.

## 3. Why Can Caches Become Stale After Restore?

### 3.1. TTL has expired

TTL (Time To Live) is the duration an entry is allowed to remain in the cache. If an entry was created before checkpoint, its TTL may have expired while the process was stopped.

Example:

- Entry created at 08:00 with a 15-minute TTL.
- Checkpoint at 08:05.
- Restore at 08:30.
- The entry has been expired since 08:15.

If the cache only evicts entries upon request access, expired entries may still remain in the heap. The application must check expiry on read or perform cleanup/refresh after restore.

### 3.2. Source data has changed

A record may have been updated or deleted in the database. If the local cache did not receive an invalidation during the checkpoint interval, the old value persists.

This is common with cache-aside: the application reads from the database on a cache miss and keeps the result in the local cache. When another instance updates the database, the current instance's local cache needs invalidation or TTL expiration.

### 3.3. Missed invalidation events

Some systems use a message broker or pub/sub to broadcast cache invalidations. If the process is not running while checkpointed, the consumer may miss events, lose its subscription, or need to re-read offsets after restore.

After restore, do not assume the local cache received all events. You may need to:

- Check the current version of the data.
- Re-read the offset or cursor of the event stream.
- Clear the entire cache group dependent on the stream.
- Resynchronize from a versioned snapshot.
- Recreate subscriptions before accepting traffic.

### 3.4. Expired credentials or tokens

Authentication caches carry unique risks. A token valid before checkpoint may expire before restore. If the application keeps using the old token, requests to external services may be rejected.

Do not rely solely on remaining lifetime calculated before checkpoint. After restore, check expiration against the current clock and refresh tokens per the authentication system's policy.

### 3.5. Feature flag and configuration changes

A configuration cache may become outdated when feature flags, endpoints, business limits, or security policies change.

For configuration affecting access control, payments, transaction limits, or routing, keeping old values can cause incorrect behavior. Categorize configuration by risk level and refresh values needing updates before the application accepts requests.

### 3.6. Clocks and deadlines no longer match

A cache entry may contain creation timestamps, expiration times, or deadlines. After restore, the application must evaluate those timestamps using the current clock.

Do not assume every deadline stored as elapsed time or a monotonic value remains meaningful across every checkpoint/restore mechanism. For deadlines that must persist across the process lifecycle, usually store absolute UTC timestamps or data-source-managed expirations, then recompute remaining time after restore.

## 4. TTL Policies and Cache Expiration

TTL limits how long data can be used without re-checking the source. An appropriate TTL depends on the rate of change and the impact if data is stale.

| Data | Recommended policy | Reason |
|---|---|---|
| Rarely changing catalog | Long TTL, versioned refresh | Changes infrequently |
| Product pricing | Short TTL or event-based invalidation | Prices may change frequently |
| Feature flags | Fast refresh, version check | Changes affect behavior |
| Permissions | Very short TTL or source verification | Permission revocation must take effect promptly |
| Tokens | Based on actual token expiry | Expired tokens must not be used |
| DNS/service discovery | Per TTL and resolver policy | Endpoints can change |
| Computed results | TTL based on recomputation cost and freshness | Can be recomputed when stale |

TTL only bounds the maximum staleness window assuming the cache checks expiry properly. TTL alone does not guarantee data is immediately fresh the moment the source changes.

### 4.1. Checking expiry on read

A cache entry can store its expiration timestamp:

~~~java
import java.time.Instant;

public record CacheEntry<V>(
        V value,
        Instant expiresAt
) {
    public boolean isExpired(Instant now) {
        return !now.isBefore(expiresAt);
    }
}
~~~

On read:

~~~java
public Product getProduct(String id) {
    CacheEntry<Product> entry = cache.get(id);
    Instant now = Instant.now();

    if (entry == null || entry.isExpired(now)) {
        return refreshProduct(id);
    }

    return entry.value();
}
~~~

In the example, expiration is represented by Instant to compare against current wall-clock time. If the system clock changes, expiry evaluation can also change; the system must use a reliable time source and an appropriate policy.

For applications needing exact deadline handling, you can combine source timestamps, versions, or server-issued expirations rather than relying solely on the local clock.

### 4.2. Do not use checkpoint time to reset TTLs

A common mistake is resetting a full TTL for every old entry after restore. For example, an entry that already existed 20 minutes before checkpoint is granted another 30 minutes after restore as if it had just been created.

That extends the lifetime of stale data. If an entry has an absolute expiration time, keep expiresAt unchanged and check against the current time. If a caching library stores remaining duration, check how the library handles time across restore.

### 4.3. Jitter to avoid synchronized refreshes

If multiple instances load the cache at the same time, entries may expire around the same time. After a deployment or mass restore, all instances could query the database simultaneously.

Jitter can be added to TTL to spread out refresh times:

~~~java
Duration baseTtl = Duration.ofMinutes(10);
long jitterSeconds = ThreadLocalRandom.current().nextLong(0, 61);

Duration effectiveTtl = baseTtl.plusSeconds(jitterSeconds);
~~~

Jitter must be used consistently with freshness requirements. For tokens or access permissions, do not add extra time beyond the credential's actual expiry.

## 5. Cache Refresh Strategies After Restore

Clearing the entire cache is not always necessary. There are multiple strategies, ranging from keeping data unchanged to refreshing everything.

### 5.1. Keeping versioned caches or immutable data

Some data that changes rarely or is identified by version can be retained.

Examples:

- Country code tables tagged with a version.
- Metadata of an immutable schema.
- Computation results keyed by input hash.
- Static resources with checksums.
- Configuration released together with a specific application version.

If the cache version matches the source version after restore, the data can continue being used. If the versions differ, the application must refresh.

This reduces warm-up cost, though it requires meaningful and reliably updated versions.

### 5.2. Lazy refresh

Lazy refresh does not reload the entire cache immediately after restore. Entries are refreshed only when a request accesses them and finds that the entry is expired or its version is no longer valid.

Advantages:

- Faster restore.
- Avoids placing heavy load on the database immediately at startup.
- Refreshes only data that is actually used.

Disadvantages:

- The first request for each key may be slow.
- Some requests may encounter refresh failures.
- If multiple requests read the same stale key simultaneously, it can trigger multiple concurrent queries.

A single-flight mechanism or per-key synchronization is required so only one thread refreshes an entry at a time.

### 5.3. Eager refresh or warm-up

Eager refresh preloads a critical set of data after restore, before the application accepts traffic.

Examples:

- Essential configuration.
- Catalogs used on every request.
- Public keys or authentication metadata.
- Routing or endpoint caches.
- Small reference data.

The advantage is that the first request does not have to wait for data loading. The disadvantage is longer restore time and potential load spikes on the data source.

Do not warm up an entire large cache if most keys go unused. Identify the minimal dataset necessary for the application to be ready.

### 5.4. Invalidating the entire cache

If it is impossible to determine which entries remain valid, the application can clear the local cache after restore and reload on demand.

This strategy is simple yet can increase database load, raise latency, and cause cache stampedes. Use it only when the cache can be rebuilt at acceptable cost and the data source can handle all instances simultaneously.

### 5.5. Version- or generation-based refresh

Another approach tags the cache with the generation or version of the source data. After restore, the application reads the current version. If the cached generation does not match, entries belonging to the older generation are not used.

Example:

~~~java
public record VersionedValue<V>(
        long generation,
        V value
) {}

public V get(String key, long currentGeneration) {
    VersionedValue<V> entry = cache.get(key);

    if (entry == null || entry.generation() != currentGeneration) {
        return loadAndCache(key, currentGeneration);
    }

    return entry.value();
}
~~~

The generation can be retrieved from a database, configuration service, or metadata store. Ensure reading the generation and the data has appropriate consistency; if a stale version is read, the application could still accept a stale entry.

### 5.6. Stale-while-revalidate

Some data allows returning an older value for a short window while refreshing in the background.

The mechanism typically consists of:

1. Entry within soft TTL: return data immediately.
2. Entry past soft TTL but within hard TTL: return stale data and trigger a background refresh.
3. Entry past hard TTL: do not return stale data; wait for refresh or report an error.

This reduces latency, yet is appropriate only when business rules tolerate temporarily stale data. Do not use it for permissions, tokens, account balances, or data where staleness can cause serious consequences.

## 6. Choosing Which Data to Keep, Refresh, or Evict

Classify caches by freshness requirements and risk level.

| Group | Examples | After restore |
|---|---|---|
| Immutable or versioned | Per-release metadata | Keep if version matches |
| Infrequently changing, low risk | Catalogs | Keep within TTL or refresh in background |
| Frequently changing business data | Prices, inventory | Check version or refresh |
| Sensitive data | Permissions, sessions | Refresh or re-verify |
| Expiring credentials | Access tokens | Check expiry and renew |
| Environment-dependent | DNS, endpoints, routes | Re-resolve when needed |
| Expensive computation cache | Reports, aggregates | Keep if input version still matches |
| Runtime references | Connections, transactions | Do not treat as data caches; manage via lifecycle resources |

A practical strategy can combine:

- Keeping immutable or versioned data.
- Keeping low-risk caches within their valid TTL.
- Invalidating time-dependent data.
- Refreshing security data and essential configuration.
- Lazy loading infrequently used data.
- Warming up a set of critical keys before opening readiness.

## 7. Integrating Caches with a CRaC Resource

CRaC provides the Resource interface with two main callbacks:

- beforeCheckpoint(): prepares resources before saving state.
- afterRestore(): restores or refreshes resources after the process is recovered.

For caches, beforeCheckpoint() can be used to stop background refreshes, stop invalidation listeners, or bring the cache into a consistent state. afterRestore() can check versions, invalidate stale entries, restart listeners, and warm up essential data.

Not every cache needs to be cleared in beforeCheckpoint(). If data has an explicit version and remains valid, retaining the cache can save restore time. Decisions should be based on the semantics of each data category.

### 7.1. Example Resource managing a cache

The example below uses application-defined abstractions: ProductCache, VersionProvider, and CacheWarmer. They are not CRaC APIs.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CacheCheckpointResource implements Resource {

    private final ProductCache cache;
    private final VersionProvider versionProvider;
    private final CacheWarmer warmer;

    public CacheCheckpointResource(
            ProductCache cache,
            VersionProvider versionProvider,
            CacheWarmer warmer) {

        this.cache = cache;
        this.versionProvider = versionProvider;
        this.warmer = warmer;

        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        // Stop background refresh and listener before saving the process.
        cache.pauseBackgroundRefresh();
        cache.stopInvalidationListener();
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {

        // Compare cache version with the current data source.
        long currentVersion = versionProvider.currentVersion();

        if (cache.version() != currentVersion) {
            cache.invalidateAll();
        } else {
            cache.invalidateExpiredEntries();
        }

        // Restart cache synchronization components.
        cache.startInvalidationListener();

        // Load necessary data before the application receives traffic.
        warmer.warmEssentialEntries();
        cache.resumeBackgroundRefresh();
    }
}
~~~

The example illustrates one organizational pattern, not an implementation usable verbatim with every caching library. Clearly determine:

- How listeners can be stopped and re-registered.
- How cache versions are stored and updated.
- Whether warm-up has a timeout.
- How the application handles an unreachable version service.
- Whether readiness opens only after essential caches are ready or if fallback is allowed.

If the caching library or framework already provides CRaC integration, follow the library's guidance and avoid registering another resource that handles the same cache redundantly.

### 7.2. Restoration order for caches and dependencies

Caches may depend on a database, Redis, configuration service, or service discovery. Therefore, the restore order must reflect dependencies:

1. Initialize configuration and network connections.
2. Connect to data sources or the distributed cache.
3. Read the current version/generation.
4. Invalidate or refresh the local cache.
5. Start listeners and background refresh.
6. Warm up essential keys.
7. Transition readiness to READY.

If warm-up runs before the database connection is ready, the callback can fail. If listeners start after traffic opens, the application may miss new invalidations.

## 8. Avoiding Cache Stampedes After Restore

A cache stampede occurs when multiple requests simultaneously detect an expired key and query the data source at once to refresh it.

After restore, this phenomenon can occur across many keys or multiple instances simultaneously, especially when the entire cache is invalidated.

### 8.1. Single-flight refresh

Single-flight ensures only one refresh happens per stale key. Other requests await the refresh result or use a stale value if policy permits.

Conceptual pattern:

~~~java
ConcurrentHashMap<String, CompletableFuture<Product>> refreshes =
        new ConcurrentHashMap<>();

public CompletableFuture<Product> refreshOnce(String key) {
    return refreshes.computeIfAbsent(key, id ->
        CompletableFuture.supplyAsync(() -> {
            try {
                return repository.loadProduct(id);
            } finally {
                refreshes.remove(id);
            }
        }, refreshExecutor)
    );
}
~~~

The snippet illustrates the single-flight idea; a production implementation must handle tasks completing very quickly, exceptions, executor rejections, and removing the future by identity to avoid accidentally removing a newer refresh.

### 8.2. Jitter and batched refreshes

Do not refresh every key at the exact same time if the cache is large. You can:

- Spread out expiration times using jitter.
- Warm up in small batches.
- Limit the number of concurrent refresh requests.
- Prioritize frequently accessed keys.
- Set timeouts and load limits on the database.
- Use a rate limiter for background refreshes.

### 8.3. Conditionally keeping stale values

If business logic allows it, you can keep a stale value during refresh. However, set a hard limit and classify data carefully. Do not return stale values when permissions were revoked, tokens expired, or the data directly impacts financial decisions.

### 8.4. Circuit breakers and fallbacks

If the data source is unavailable, continuous refreshes can make the system worse. A circuit breaker can temporarily halt source calls when errors exceed a threshold. The application must define fallbacks:

- Return stale values if business rules allow.
- Return a temporary error.
- Use a safe default value.
- Keep readiness NOT_READY if an essential dependency cannot operate.

Do not apply fallbacks silently for sensitive or critical data.

## 9. Cache Invalidation and Multi-Instance Synchronization

In a multi-instance system, each process has its own local cache. When one instance updates data, other instances must know so they can evict or refresh the entry.

Common mechanisms:

### 9.1. TTL polling

Each entry expires according to its TTL. This approach is simple and needs no event bus, yet has a maximum freshness lag bounded by the TTL.

### 9.2. Event-based invalidation

The service emits events when data changes. Instances receive events and invalidate the corresponding keys.

After restore, listeners may need to re-register and resync offsets/cursors. If unsure whether all events were received, invalidate the cache by namespace or compare against the current version.

### 9.3. Version-based validation

Each data group has a version. The cache entry stores the version it read. On access, the application compares it with the current version.

This reduces reliance on receiving every event, yet requires a version source with suitable reliability and read cost.

### 9.4. Distributed cache

Redis or an external cache server can store shared data. The local cache acts solely as an L1 cache, while the distributed cache acts as an L2 cache.

After restore:

- The L1 cache may be stale.
- The L2 cache may have been updated.
- The local cache must check versions or invalidation.
- Connections to the L2 cache must be verified before warm-up.

Do not assume the local cache and distributed cache automatically stay in sync simply because they hold the same keys.

## 10. Caches Containing Configuration and Security Data

Some caches directly affect application security or behavior.

### 10.1. Permissions and authorization

If access permissions are revoked while the process is checkpointed, an old local cache may continue permitting requests. For sensitive permissions, refresh or verify against the source per system requirements.

Do not use stale-while-revalidate for critical access permissions if policy requires revocations to take effect quickly.

### 10.2. Tokens and credentials

A checkpoint may contain tokens, keys, or credentials in the heap. Protect the checkpoint as an artifact containing sensitive data.

After restore:

- Check token expiration.
- Refresh tokens when necessary.
- Re-read secrets if the platform can change secrets.
- Avoid logging tokens or credentials.
- Do not keep credentials in caches longer than policy permits.

### 10.3. Feature flags and runtime configuration

Feature flags can control routing, limits, or business behavior. After restore, refresh flags that must reflect current state before accepting traffic.

Configuration can be divided into:

- Release-immutable configuration.
- Versioned runtime configuration.
- Sensitive configuration requiring immediate refresh.
- Configuration allowed to be stale briefly.

Each group has different TTL and fallback rules.

## 11. Designing Post-Restore Warm-Up

Warm-up is the process of preloading data to reduce cache misses when traffic begins arriving.

Do not load all data in a single fixed way. A good warm-up strategy identifies:

- Which keys are used frequently.
- Which data is essential for handling requests.
- Which data can be loaded lazily.
- Which sources have throughput limits.
- Whether data can be loaded in batches.
- The maximum timeout before opening readiness.

### 11.1. Prioritized warm-up

This can be divided into three tiers:

| Level | Data | Action |
|---|---|---|
| Critical | Essential configuration, permissions, endpoints | Refresh before accepting traffic |
| High | Catalogs and popular keys | Warm up in batches |
| Optional | Infrequently used data, reports | Lazy load on request |

### 11.2. Readiness and cache readiness

Readiness should reflect actual serving capability. If every request needs essential configuration or reference data, the application should not report READY before warm-up completes.

If a cache only improves performance and can fall back to the database, the application can accept traffic sooner. However, account for increased database load while the cache is still cold.

### 11.3. Time-bounded warm-up

Do not let the afterRestore callback wait indefinitely because a cache server or database is unresponsive.

Set timeouts for each data group. If a critical cache fails to load, keep readiness NOT_READY or report a restore error per policy. If an optional cache fails, the application can proceed with lazy loading.

## 12. Example Cache Strategy with Expiry and Refresh

The following example illustrates a product data cache with expiration timestamps. The cache is invalidated when the source version changes.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ConcurrentHashMap;

public final class ProductCache {

    private final ConcurrentHashMap<String, Entry> entries =
            new ConcurrentHashMap<>();

    private final Duration ttl;
    private final ProductRepository repository;

    public ProductCache(
            Duration ttl,
            ProductRepository repository) {
        this.ttl = ttl;
        this.repository = repository;
    }

    public Product get(String id) {
        Instant now = Instant.now();
        Entry entry = entries.get(id);

        if (entry != null
                && now.isBefore(entry.expiresAt())) {
            return entry.product();
        }

        Product fresh = repository.findById(id);
        entries.put(
            id,
            new Entry(fresh, Instant.now().plus(ttl))
        );

        return fresh;
    }

    public void invalidate(String id) {
        entries.remove(id);
    }

    public void invalidateAll() {
        entries.clear();
    }

    public void invalidateExpiredEntries() {
        Instant now = Instant.now();

        entries.entrySet().removeIf(
            item -> !now.isBefore(item.getValue().expiresAt())
        );
    }

    private record Entry(Product product, Instant expiresAt) {}
}
~~~

This is a minimal example. In production, consider:

- Synchronization when multiple threads refresh the same key.
- Repository error handling.
- Cache size limits.
- Eviction policies.
- Jitter for TTL.
- Data versioning.
- Metrics for cache hits, misses, and refresh failures.
- Never returning stale data past hard expiry.

### 12.1. Refreshing the cache after restore

A resource can invalidate expired entries and warm up critical data:

~~~java
public final class ProductCacheResource implements Resource {

    private final ProductCache cache;
    private final ProductCacheWarmer warmer;

    public ProductCacheResource(
            ProductCache cache,
            ProductCacheWarmer warmer) {
        this.cache = cache;
        this.warmer = warmer;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) {
        warmer.pause();
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        cache.invalidateExpiredEntries();
        warmer.refreshCriticalData();
        warmer.resume();
    }
}
~~~

The example assumes the classes already have their respective dependencies and methods. In a real application, handle errors when refreshing critical data, timeouts, and readiness state. If the cache cannot determine exact expiry, you may need to invalidate by version or clear a specific namespace.

## 13. Common Errors When Restoring Caches

| Mistake | Consequence | Mitigation |
|---|---|---|
| Keeping all entries without checking TTL | Serves expired data | Check expiry after restore and on read |
| Resetting TTL on old cache entries | Extends staleness window | Keep absolute expiry or version |
| Refreshing the entire cache at once | Overloads database | Batching, jitter, concurrency limits |
| Opening traffic before critical warm-up | Requests fail or use unsafe fallbacks | Readiness gate |
| Missing invalidation events | Local cache retains old data | Resync offsets or compare versions |
| Caching tokens without checking expiry | Requests rejected or stale credentials used | Refresh tokens by expiry |
| Caching connections or transactions | References to invalid resources | Manage via dedicated CRaC Resources |
| Using stale fallback for permissions | Revoked permissions still accepted | Refresh or check source |
| Unbounded warm-up | Restore hangs | Timeouts and error policies |
| Unbounded cache growth | Heap grows and restore slows down | Maximum size and eviction |

## 14. Observing Caches in Operations

After restore, monitor:

- Cache hit rate and miss rate.
- Number of retained entries.
- Number of invalidated entries.
- Number of TTL-expired entries.
- Warm-up duration.
- Refresh success/failure rates.
- Number of requests waiting on refresh.
- Count of cache stampedes or concurrent refreshes.
- Cache version compared to source version.
- Time from restore to READY.

Metrics help determine whether the cache genuinely speeds up post-restore execution or is placing heavy load on source systems.

Log key lifecycle stages:

- Cache restore preparation started.
- Cache invalidation completed.
- Cache version verified.
- Critical cache warm-up started/completed.
- Invalidation listener reconnected.
- Cache readiness changed.
- Cache refresh failed.

Do not log sensitive contents or tokens. For large caches, log counts and versions instead of dumping all keys/values.

## 15. Recommended Implementation Workflow

### Before checkpoint

1. Stop accepting new work if background cache refreshes are running.
2. Stop schedulers or listeners if separate lifecycle management is needed.
3. Wait for running refreshes to finish or transition them into a resumable state.
4. Determine which caches can be retained and which must be invalidated.
5. Close external resources used by the cache manager if they must be recreated.
6. Allow CRaC to proceed with checkpoint once state is ready.

### After restore

1. Initialize connections to the database, distributed cache, and configuration service.
2. Read the current version/generation.
3. Check TTL and expiry.
4. Invalidate caches that are stale or in an indeterminate state.
5. Restart invalidation listeners and background refresh.
6. Warm up critical keys in batches.
7. Transition readiness to READY once essential data is ready.

The order may vary depending on dependencies. For example, if a cache depends only on Redis, there is no need to wait for the database if Redis already provides reliably versioned data. Identify the authoritative source for each cache.

## 16. CRaC Cache Design Checklist

### Data and freshness

- [ ] Each cache group has a clear TTL or versioning policy.
- [ ] Sensitive business data has appropriate freshness requirements.
- [ ] Entries store absolute expiry or version information checkable after restore.
- [ ] Caches do not hold transactions, connections, or short-lived runtime resources.
- [ ] Credentials and tokens are checked for expiry.

### Restore and refresh

- [ ] Caches are classified into retain, refresh, or invalidate.
- [ ] Invalidation events are resynchronized after restore.
- [ ] DNS, endpoints, and environment-dependent configuration are refreshed when needed.
- [ ] Critical data warm-up has a timeout.
- [ ] Readiness reflects the state of essential caches.

### Performance and errors

- [ ] Refreshes are concurrency-limited.
- [ ] Jitter or batching is used to avoid stampedes.
- [ ] Single-flight or an equivalent mechanism is in place per key.
- [ ] Fallbacks are used only for data where business logic permits staleness.
- [ ] Caches have size bounds and eviction policies.
- [ ] Metrics exist for hits/misses, expiry, invalidation, and refreshes.

### Security and operations

- [ ] Checkpoints are protected because the heap may contain sensitive data.
- [ ] Secrets are not logged.
- [ ] Handling is defined for when the cache source is unavailable.
- [ ] Tested restore after TTL expiry, version changes, and missed invalidations.
- [ ] Tested multiple instances restoring simultaneously.

## 17. Frequently Asked Questions

### Are in-heap caches saved with the checkpoint?

Cache objects residing on the heap can be saved alongside process state. However, the restored data may be stale because data sources and external services continue changing while checkpointed.

### Should the entire cache be cleared in beforeCheckpoint()?

Not necessarily. Immutable or reliably versioned data can be retained. Caches depending on time, access permissions, or environment may need invalidation or refreshing. Decide per data group.

### Can you rely solely on TTL?

TTL limits how long an entry is used, yet does not guarantee fresh data immediately when the source changes. For data requiring high freshness, combine TTL with versioning or event-based invalidation.

### Should you use lazy refresh or eager warm-up?

Lazy refresh makes restore fast and loads only used keys. Eager warm-up suits essential data that must be ready before the first request. Many applications combine both: warming up critical groups and lazy-loading the rest.

### What if invalidation events are missed while checkpointed?

After restore, the consumer needs to resync offsets/cursors or compare against the source version. If you cannot verify that the cache received all events, invalidate the related data group or refresh from a versioned snapshot.

### Should tokens be kept in the cache across restore?

The object may be retained if design allows, yet you must not assume the token remains valid. After restore, check expiry and refresh per authentication policy. Checkpoints must also be protected since they can hold tokens and secrets in the heap.

### Should traffic open if warm-up fails?

It depends on which data failed. If it is an essential cache for access control or critical business logic, keep readiness NOT_READY or report an error per policy. If it is only a performance cache with a safe fallback, the application can accept traffic with appropriate limits.

### Do out-of-process caches need handling after restore?

Yes. Redis or a distributed cache may keep running independently, yet the application's connections, listeners, subscriptions, and local L1 cache may be stale. Reconnect, synchronize versions, and restore invalidation listeners.

## Conclusion

In-heap caches can be restored along with a CRaC process, yet an object's continued existence does not prove the data is fresh. TTLs may have expired, databases may have updated data, invalidation events may have been missed, tokens may have expired, and configuration may have changed while checkpointed.

A sound strategy classifies caches by freshness and risk level: keep immutable or versioned data, check expiry, invalidate stale data, refresh sensitive data, and warm up essential key groups. Combining versioning, TTLs, event resync, single-flight, jitter, timeouts, and readiness enables the application to recover caches in a controlled manner without causing load spikes or serving outdated data.