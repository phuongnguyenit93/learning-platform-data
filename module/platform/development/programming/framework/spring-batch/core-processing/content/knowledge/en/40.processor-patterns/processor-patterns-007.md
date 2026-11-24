# Caching processor

In Spring Batch, `ItemProcessor` typically performs validation, enrichment, mapping, or service calls to fetch supplemental data for each item. When many items need the same reference data, repeated database queries or service calls can slow down the Step and increase system load. A caching processor retains reusable results so subsequent executions do not repeat expensive work.

Caching must be designed around data semantics. Proper caching reduces latency and backend load; improper caching can return stale data, leak data across tenants, produce wrong results after restarts, or mask source errors. In particular, a cache does not replace Spring Batch transactions, checkpoints, or idempotency. An in-memory cached result can still persist after a chunk rolls back.

## 1. Why cache inside an ItemProcessor?

Suppose a Job imports 100,000 orders. Each order needs customer details to check status and credit limits:

~~~text
Order item
   |
   v
ItemProcessor
   |
   +--> Customer service / database
   |
   v
Enriched order
~~~

If 100,000 orders belong to only 5,000 customers, the processor may call the customer service repeatedly for the same customer ID. A cache stores previously loaded profiles:

~~~text
Order 1, customer C-001 ----+
Order 2, customer C-001 ----+----> Cache hit
Order 3, customer C-002 ---------> Cache miss -> Load profile -> Cache
Order 4, customer C-001 ---------> Cache hit
~~~

Common benefits:

- Reduces repeated database queries.
- Reduces requests to REST services or external systems.
- Reduces processor latency.
- Reduces load on source systems when a batch processes many items sharing keys.
- Maintains a snapshot of reference data over a defined period.

Caching is especially useful for read-heavy, infrequently changing data reusable across many items. It is less suitable for rapidly changing data or results dependent on per-invocation state.

## 2. Which data should be cached?

Not every result in a processor should be cached. Before adding a cache, verify data repeatability and change patterns.

| Data | Suitability | Reason |
|---|---|---|
| Country codes, categories, currencies | High | Rarely changes, shared across many items |
| Customer profiles | Depends on business rules | Often read repeatedly, but requires freshness |
| Product metadata | Depends on business rules | Prices and inventory can change quickly |
| Versioned tax rules | High if version-pinned | Same rule required across the entire batch |
| Pure validation results | Conditional | Cache only when input and context are complete and deterministic |
| Results of transaction-creating API calls | Unsuitable | Has side effects and must not be arbitrarily bypassed/repeated |
| Results dependent on current time | Usually unsuitable | Same input can yield different outputs at different times |
| Tenant-sensitive data | Strictly conditional | Keys and cache isolation must prevent data leaks |

A helpful rule is to cache only results that can be safely recomputed or re-read, using a key that fully captures every factor affecting the result.

Do not cache side effects such as transferring funds, creating invoices, sending emails, or issuing transaction commands simply because the method performing them lives in `ItemProcessor`. Those operations require idempotency keys, transactions/outboxes, or dedicated deduplication mechanisms.

## 3. Caching reference data rather than caching whole items

Usually, the safer and more controllable approach is to cache the reference data the processor needs, while still executing item-level processing logic for each item:

~~~java
@Component
public class OrderProcessor
        implements ItemProcessor<OrderInput, EnrichedOrder> {

    private final CustomerProfileService customerProfiles;

    public OrderProcessor(CustomerProfileService customerProfiles) {
        this.customerProfiles = customerProfiles;
    }

    @Override
    public EnrichedOrder process(OrderInput order) {
        CustomerProfile profile =
                customerProfiles.findByCustomerId(order.customerId());

        validateOrder(order, profile);
        return new EnrichedOrder(order, profile.customerTier());
    }
}
~~~

The processor still handles each order. The service is responsible for fetching profiles and may use caching. This separation keeps cache policies at the appropriate data layer while avoiding accidentally reusing the entire output of a different item.

If you cache the entire `EnrichedOrder`, the key must include all inputs and context affecting the output, such as order version, customer profile version, currency, locale, policy version, and business date. That is typically more complex than caching profiles by customer ID.

## 4. Using the Spring Cache abstraction

Spring provides a Cache abstraction so applications can use annotations or APIs without coupling directly to a specific cache provider. Providers can be Caffeine, JCache, Redis, or other configured implementations.

To use annotation-based caching, enable caching:

~~~java
@Configuration
@EnableCaching
public class CacheConfiguration {
}
~~~

Annotate the method that reads reference data:

~~~java
@Service
public class CustomerProfileService {

    private final CustomerRepository repository;

    public CustomerProfileService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Cacheable(
            cacheNames = "customerProfiles",
            key = "#customerId",
            unless = "#result == null")
    public CustomerProfile findByCustomerId(String customerId) {
        return repository.findByCustomerId(customerId)
                .orElse(null);
    }
}
~~~

When the method is called with a `customerId` already in the cache, Spring returns the cached value without executing the method body. On a miss, the method queries the repository and stores the result according to the cache configuration.

Commonly used attributes:

- `cacheNames`/`value`: cache name.
- `key`: expression determining the cache key.
- `keyGenerator`: custom key-generating component.
- `condition`: condition for applying caching.
- `unless`: condition to exclude the result from caching after method execution.
- `cacheManager`/`cacheResolver`: selects where the cache is managed.
- `sync`: instructs the cache provider to coordinate loading a key across concurrent calls, depending on provider support.

## 5. Spring Cache works via proxies

Annotations like `Cacheable` are typically enforced through Spring AOP proxies. Therefore, the method must be invoked through a Spring bean proxy for caching advice to execute.

A common mistake is self-invocation:

~~~java
@Service
public class CustomerProfileService {

    public CustomerProfile load(String id) {
        return findCached(id);
    }

    @Cacheable(cacheNames = "customerProfiles", key = "#id")
    public CustomerProfile findCached(String id) {
        return repository.findByCustomerId(id).orElse(null);
    }
}
~~~

If `load()` calls `findCached()` directly on the same instance, the internal call usually bypasses the proxy, so `@Cacheable` on `findCached()` may not apply. Invoke cacheable methods from another bean or extract the method into a separate service.

Do not instantiate services manually with `new` if you rely on proxies and Spring-managed dependencies. Inject beans via constructors.

## 6. Configuring a cache provider with Caffeine

Caffeine is a popular in-memory cache on the JVM. It supports size limits, expiration, and efficient eviction policies.

Example Spring Cache configuration:

~~~java
@Configuration
@EnableCaching
public class CacheConfiguration {

    @Bean
    CacheManager cacheManager() {
        CaffeineCacheManager manager =
                new CaffeineCacheManager("customerProfiles");

        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(100_000)
                .expireAfterWrite(Duration.ofMinutes(10)));

        return manager;
    }
}
~~~

This example requires the Caffeine dependency in the build. `maximumSize` caps the number of entries, and `expireAfterWrite` sets the time-to-live from the time of write. Actual values should be based on object size, unique key count, heap budget, and data change rate.

An in-memory cache belongs to a single JVM. When running multiple application instances or multiple worker processes, each process has its own cache. One process may see updated data while another holds stale values until entries expire or are invalidated.

## 7. TTL, eviction, and memory limits

Caches need lifecycle policies. Without an entry limit, a Job processing millions of unique business keys can retain too many objects on the heap and cause heavy garbage collection or `OutOfMemoryError`.

Common mechanisms:

- **TTL/expiration:** automatically expires after a duration.
- **Maximum size:** caps the number of entries.
- **Maximum weight:** caps by estimated entry weight.
- **Eviction policy:** removes entries when space is needed.
- **Explicit invalidation:** deletes entries when source data changes.
- **Versioned keys:** creates new keys when data versions change.

Long TTLs raise hit rates but may serve stale data longer. Short TTLs improve freshness but lower hit rates and increase source load. Choose based on data SLAs, not solely to minimize service calls.

Maximum size caps entry counts, not exact byte usage. One entry may hold an object much larger than another. If value sizes vary widely, estimate memory footprint or use a cache provider supporting maximum weight.

## 8. Choosing accurate cache keys

A cache key must fully represent every factor determining the result. If the key omits a context dimension, the cache can return one item's result for another item.

For example, tenant-dependent profiles:

~~~java
@Cacheable(
        cacheNames = "customerProfiles",
        key = "#tenantId + ':' + #customerId")
public CustomerProfile find(
        String tenantId,
        String customerId) {
    return repository.find(tenantId, customerId).orElse(null);
}
~~~

If only `customerId` is used in a multi-tenant system, two tenants can accidentally share an entry. This is both a data bug and a potential cross-tenant data leak.

Factors that may need to be included in the key:

- Tenant or security domain.
- Entity ID.
- Locale or currency.
- Policy/schema version.
- Business date or effective date.
- Request type or channel.
- Source data version.

Do not use mutable objects as keys if `equals`/`hashCode` can change after insertion into the cache. Prefer immutable records/key objects or normalized canonical strings.

## 9. Immutable key objects

When a key has multiple components, using a record makes the contract explicit:

~~~java
public record CustomerCacheKey(
        String tenantId,
        String customerId,
        String policyVersion) {
}
~~~

Creating a key:

~~~java
CustomerCacheKey key = new CustomerCacheKey(
        tenantId,
        customerId,
        policyVersion);
~~~

Keys must be normalized consistently. For example, if tenant IDs are case-insensitive, canonicalize at a single layer before creating the key. Do not arbitrarily trim or change casing if the contract allows distinct values.

Avoid logging or tagging metrics directly with keys containing sensitive values. You can log the cache name and hit/miss outcome without recording raw keys.

## 10. Caching ItemProcessor output with a decorator

In some cases, you want to wrap an existing `ItemProcessor` with a caching processor. You can create a decorator:

~~~java
public class CachingItemProcessor<I, O>
        implements ItemProcessor<I, O> {

    private final ItemProcessor<I, O> delegate;
    private final Cache cache;
    private final Function<I, Object> keyGenerator;

    public CachingItemProcessor(
            ItemProcessor<I, O> delegate,
            Cache cache,
            Function<I, Object> keyGenerator) {
        this.delegate = delegate;
        this.cache = cache;
        this.keyGenerator = keyGenerator;
    }

    @Override
    @SuppressWarnings("unchecked")
    public O process(I item) throws Exception {
        Object key = keyGenerator.apply(item);
        Cache.ValueWrapper cached = cache.get(key);

        if (cached != null) {
            return (O) cached.get();
        }

        O result = delegate.process(item);
        if (result != null) {
            cache.put(key, result);
        }
        return result;
    }
}
~~~

This decorator caches only non-null outputs. That avoids relying on whether the cache provider supports storing nulls, and does not retain filter decisions indefinitely. Concurrent cache misses across threads can still invoke the delegate multiple times because get-then-process-then-put is not atomic. If single-flight loading is required, use the provider's synchronous loading API or a suitable cache loader.

The decorator pattern is only safe when the delegate is a deterministic function of the key, has no side effects, and its output is reusable. If the delegate updates a database, sends messages, or depends on mutable state, caching the entire output can skip necessary work.

## 11. Caching null and negative caching

A lookup that finds no data can be cached to avoid repeated queries. This is often called negative caching.

For example, a non-existent customer ID appears repeatedly in a file. Querying the database every time wastes load on the same empty result.

Negative caching requires caution:

- Data that does not exist today may be created shortly after.
- Caching null for too long can hide newly created records.
- Some cache providers disallow storing null or require explicit configuration.
- Null can mean different things: not found, unauthorized, or source error.

With Spring Cache, `unless` can exclude null from the cache:

~~~java
@Cacheable(
        cacheNames = "customerProfiles",
        key = "#customerId",
        unless = "#result == null")
public CustomerProfile find(String customerId) {
    return repository.findByCustomerId(customerId).orElse(null);
}
~~~

If negative caching is desired, represent the result explicitly using `Optional` or a wrapper with `FOUND`/`NOT_FOUND` states, and assign a shorter TTL for `NOT_FOUND`. Never cache timeouts or connection errors as if the data definitely does not exist.

## 12. Cache hits, cache misses, and cache stampedes

Concurrent cache misses can cause multiple threads to call the backend simultaneously for the same key before the entry is populated. This phenomenon is commonly known as a cache stampede or thundering herd.

~~~text
Thread A ---- cache miss ----+
Thread B ---- cache miss ----+----> Multiple backend loads
Thread C ---- cache miss ----+
~~~

For expensive data, coordinate loading:

- Use a cache API with atomic loading/single-flight support.
- Use Caffeine's `Cache.get(key, mappingFunction)` when working with Caffeine directly.
- Use Spring Cache `sync=true` if the provider and `Cache` implementation support the appropriate semantics.
- Preload reference data before the Step if the dataset is small and known upfront.
- Use distributed locks only when needed, weighing cost and resilience.

Spring Cache example:

~~~java
@Cacheable(
        cacheNames = "customerProfiles",
        key = "#customerId",
        sync = true)
public CustomerProfile find(String customerId) {
    return repository.findByCustomerId(customerId).orElse(null);
}
~~~

`sync=true` requests synchronizing loads for the same key through the cache provider. This is not an identical distributed guarantee across all providers; check the limitations of your `Cache` implementation. Do not rely on it for business locking across multiple application instances unless the provider offers distributed coordination.

## 13. Local cache vs. distributed cache

There are two common deployment models:

| Criterion | Local cache | Distributed cache |
|---|---|---|
| Storage location | Single JVM heap | Shared cache system such as Redis or a distributed provider |
| Latency | Typically very low | Includes a network round-trip |
| Cross-instance sharing | Not shared automatically | Can be shared |
| Invalidation | Per JVM or via events | Can be more centralized, though requires design |
| Failure mode | Affects current process | Adds network/cache server dependency |
| Best suited for | Small, rarely changing reference data | Multiple instances needing a shared cache |

A local cache is simple and fast, though it can maintain duplicate copies across worker processes. A distributed cache reduces cache data duplication across processes, but introduces network latency, network failures, serialization, and operational overhead.

Do not switch to a distributed cache just because a Job runs multiple threads in one JVM. A Caffeine local cache can handle that well. A distributed cache is only needed when multiple processes must share entries or there are centralized invalidation/visibility requirements.

## 14. Cache scope and lifecycle in Spring Batch

Caches and processor beans can have different lifecycles:

- Singleton processor: one instance may be shared across multiple `JobExecution` runs or threads.
- `@StepScope` processor: dedicated target bean per `StepExecution`.
- Singleton `CacheManager`: usually shared across the application context.
- Local cache inside a processor: shares the processor bean's lifecycle.
- Distributed cache: lives outside the JVM and can survive restarts.

`@StepScope` does not automatically create a per-thread cache. If a processor holds a mutable cache field, multiple threads in the same `StepExecution` still access the same instance. If you want a separate cache per worker partition, create a cache per `StepExecution` or include the partition ID in the key; weigh memory usage and whether data can be shared across partitions.

If a cache lives in a singleton service, two `JobExecution` runs may share entries. This is only valid when cached data does not depend on per-Job state. If it depends on batch ID, policy version, or security context, include those factors in the key or isolate the cache.

## 15. Cache thread safety

In a multi-threaded Step, multiple threads can call the same processor or cache service. Use a cache provider with appropriate concurrency semantics.

Key points to watch:

- Do not use a mutable `HashMap` as a shared cache when multiple threads read/write.
- Caffeine and `ConcurrentMapCache` support concurrent access per their implementations.
- Cached values should be immutable or copied before returning.
- Cache loaders should not perform non-idempotent side effects.
- Concurrent invalidations and loads must have clear semantics.
- Do not mutate objects stored inside the cache.

A thread-safe cache does not make all data inside it thread-safe. If a cache stores a mutable `ArrayList` and multiple processors modify that list, race conditions still occur.

## 16. Never mutate cached values directly

Suppose the cache stores `CustomerProfile`:

~~~java
CustomerProfile profile = cache.get(customerId);
profile.setRiskLevel("HIGH");
~~~

If `profile` is a shared mutable object, one item's mutation can affect other items or alter results without invalidation. This is especially dangerous when cached values are reused across tenants or `JobExecution` runs.

Prefer immutable DTOs:

~~~java
public record CustomerProfile(
        String customerId,
        String tier,
        String riskLevel) {
}
~~~

If modifications are needed, create a new object:

~~~java
CustomerProfile enriched = new CustomerProfile(
        profile.customerId(),
        profile.tier(),
        calculateRisk(order, profile));
~~~

Never write per-item state into reference objects fetched from a cache. Caches should hold stable reference data; item outputs should be distinct objects.

## 17. Cache and chunk transactions

In-memory caches typically do not participate in database transactions. For example:

1. The processor reads data from a repository.
2. The result is placed in the cache.
3. The writer writes data, but the chunk rolls back.
4. The cache still holds the newly read value.

This is not necessarily a bug if the cache only contains committed reference data that can be safely re-read. However, if the cache stores results depending on uncommitted changes, the cache can retain values that no longer exist in the database after rollback.

Do not assume a cache `put` rolls back alongside the database transaction. Spring Cache does not provide database-like transaction semantics by default. Some providers/integrations offer specific transaction-aware behavior, which must be explicitly configured and verified.

For data that may change within the same chunk, avoid caching uncommitted results or use versions/snapshots to distinguish them. If post-commit invalidation is needed, use transaction synchronization or post-commit events/outboxes instead of evicting before the transaction finishes.

## 18. Cache and retry

Spring Batch may re-invoke the processor when retrying an item or chunk. Caching changes how many times the delegate is called:

- First attempt is a cache miss; the delegate runs and the result is cached.
- The writer later fails.
- The chunk rolls back and the processor is called again.
- On retry, it is a cache hit; the delegate does not run again.

This is correct if the delegate is a pure computation and the result remains valid. It is wrong if the delegate has side effects that must execute on every attempt or if output depends on rolled-back transaction state.

Therefore:

- Do not use caching to prevent duplicate side effects.
- Do not cache transient exceptions as final results.
- Do not cache results dependent on uncommitted state.
- Use idempotency keys for side effects.
- Version cache keys if data changes per transaction.

If a retry must re-invoke the delegate to confirm source state, do not cache the entire processor's output. Cache only slowly changing reference data and let the status verification step run again.

## 19. Cache and restart

Local JVM caches are lost when the process restarts. This is not a problem if the cache is purely a performance optimization: early items after restart may see more cache misses, after which the cache warms up again.

Do not store the entire cache in `ExecutionContext`. `ExecutionContext` is meant for checkpoints and recoverable state, not large cache stores. Storing thousands or millions of entries bloats metadata, increases serialization overhead, and degrades `JobRepository`.

If cached results must survive restarts, you can use:

- A distributed cache with TTL and versioning.
- A reference snapshot table tied to the batch ID.
- An immutable snapshot file.
- `JobParameters` containing policy/version to reload the exact data.

For batches requiring reproducible results, the most important practice is pinning data/rule versions. The cache is merely a speed layer over that snapshot.

## 20. Cache invalidation when source data changes

A cache can become stale when source data is updated. Choose an invalidation strategy:

### TTL

Entries expire automatically after a duration. Easy to implement, but accepts a staleness window.

### Explicit eviction

When a service updates a customer, it evicts the corresponding entry:

~~~java
@CacheEvict(
        cacheNames = "customerProfiles",
        key = "#customerId")
public void updateProfile(
        String customerId,
        CustomerProfileUpdate update) {
    repository.update(customerId, update);
}
~~~

If the database update succeeds but eviction fails, the cache can hold stale data. Consider transaction ordering, invalidation retries, or post-commit events.

### Versioned keys

Keys include a profile version or policy version. When the version increments, new requests use new keys and ignore old entries. Old entries can expire via TTL.

### Event-driven invalidation

A service emits an event after data changes; cache instances receive the event and evict entries. Delayed, lost, or duplicate events must be handled. With multiple JVMs, invalidation events must be broadcast to every instance holding a local cache.

No single strategy fits all data. For reference data needing intra-batch consistency, snapshot/version pinning is usually easier to control than immediate invalidation.

## 21. Caching policy versions per batch

Suppose a processor calculates taxes using tax rules. If rules change mid-Job, two items in the same batch could be computed under two different versions if the cache refreshes during execution.

You can pin the policy version in `JobParameters`:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("batchId", batchId, true)
        .addString("taxPolicyVersion", policyVersion, true)
        .toJobParameters();
~~~

Cache key:

~~~java
@Cacheable(
        cacheNames = "taxRules",
        key = "#policyVersion + ':' + #countryCode")
public TaxRule findRule(
        String policyVersion,
        String countryCode) {
    return repository.findRule(policyVersion, countryCode);
}
~~~

When restarting the same `JobInstance`, `policyVersion` stays the same. If a new policy is needed, launch a new `JobInstance` or follow an explicit reprocessing workflow. Never silently switch versions within an already-checkpointed execution.

## 22. Cache errors and fallback policies

A cache provider or backend can fail:

- Cache server unreachable.
- Serialization/deserialization failure.
- Entry expired or evicted.
- Cache loader timeout.
- Cache out of capacity or write rejected.

Decide whether the cache is a hard dependency or merely an optimization:

| Situation | Potentially appropriate policy |
|---|---|
| Cache miss | Load from source |
| Cache read error, source available | Fail-open: read source directly |
| Cache write error after successful load | Return source result if cache is only an optimization |
| Policy/security lookup indeterminate | Fail-closed if safety cannot be verified |
| Source timeout | Bounded retry or fail the Step |
| Data does not exist | Short-TTL negative cache if business rules allow |

Do not blindly treat every cache exception as a cache miss. If the cache is the only store holding required policies or data, ignoring errors can yield wrong results. Logs and metrics should distinguish cache failures from source failures.

## 23. Cache warming and preloading

If the Job knows the required reference dataset upfront, it can preload the cache before processing items:

~~~text
Step 1: Load reference data
          |
          v
      Cache warm-up
          |
          v
Step 2: Process business items
          |
          v
      Cache lookups
~~~

Preloading works well when:

- The reference dataset is bounded in size.
- Data must stay consistent within a batch.
- A versioned snapshot can be loaded.
- Preload time is lower than repeated query overhead.

Do not preload an entire massive table onto the heap if the Job only uses a small subset. You can preload by key set, by partition, or rely on on-demand caching.

If warm-up is a separate Step, save the policy/version or snapshot ID so later Steps use the same data. If the warm-up Step succeeds but the processing Step restarts, do not assume a local cache is still in memory; re-preloading or a persistent snapshot may be necessary.

## 24. Cache and multi-threaded Steps / partitioning

In a multi-threaded Step, multiple threads can call the same processor. The cache provider must support concurrent get/put/load operations. If the processor is a singleton, all threads may share a cache field or service cache.

In partitioning, each worker may run in a separate process or JVM:

- Local caches on each worker do not share entries.
- The same tenant/key may be loaded repeatedly across multiple partitions.
- A distributed cache can share entries, at the cost of network dependency.
- Policy versions must match if partitions require consistent results.

Do not assume a cache hit on partition A gives partition B a hit if they run on different JVMs. To reduce duplicate loads across workers, use a distributed cache or preload a shared snapshot.

Also avoid letting a single hot key cause all workers to contend on the same backend entry. A local near-cache paired with a distributed cache can be used if the provider supports it and consistency requirements allow.

## 25. Caching inside a processor chain

A pipeline may consist of multiple processors:

~~~text
Input
  |
  v
NormalizeProcessor
  |
  v
CachedReferenceLookupProcessor
  |
  v
ValidateProcessor
  |
  v
EnrichProcessor
  |
  v
Output
~~~

Place the cache near the step with repeated data lookups. You do not need to cache the entire pipeline. For example:

- Normalize: usually a fast transformation, no caching needed.
- Reference lookup: can be cached by reference key.
- Validation: cache only if pure and dependent solely on complete input/context.
- Enrichment: cache if data is reusable and freshness bounds are clear.

If using `CompositeItemProcessor`, delegates must have compatible input/output types. A cache wrapper must preserve the `ItemProcessor` contract: return an output or `null` to filter, and throw exceptions per defined semantics.

## 26. Cache and classifiers

A classifier can select a processor based on cached metadata or policies. However, do not use a cache to mask missing route configuration or allow routes to change non-deterministically.

If routing depends on tenant policies, the cache key must include tenant and policy version. When the classifier chooses a delegate, the decision must remain stable across retries/restarts for the same item.

If a cache lookup inside a classifier fails, distinguish transient errors from unknown routes. Do not return a null delegate just because of a cache miss; a cache miss is an opportunity to load from the source, whereas a no-match means no valid route exists once policy is resolved.

## 27. Observing cache effectiveness

Do not add a cache and simply assume performance improved. Measure:

- Hit count and miss count.
- Hit ratio.
- Load count and load failure count.
- Load latency.
- Eviction count.
- Cache size/estimated weight.
- Backend query/request count.
- Processor duration before and after caching.
- Staleness or invalidation rate if measurable.

A high hit ratio is not necessarily beneficial if cache loads are cheap or cached objects consume excessive heap. Conversely, a modest hit ratio can still help if every miss calls a slow service.

Use Micrometer or cache provider metrics for observability. Avoid placing business IDs or customer IDs in metric tags because high cardinality can overload metrics backends and expose sensitive data. Tagging by cache name, outcome, or operation type is generally safer.

## 28. Testing a caching processor

Unit tests should verify the delegate is called the expected number of times:

~~~java
@Test
void reusesCachedCustomerProfile() {
    CustomerRepository repository = mock(CustomerRepository.class);
    CustomerProfile profile =
            new CustomerProfile("C-001", "GOLD", "LOW");

    when(repository.findByCustomerId("C-001"))
            .thenReturn(Optional.of(profile));

    CustomerProfileService service =
            new CustomerProfileService(repository);

    CustomerProfile first = service.findByCustomerId("C-001");
    CustomerProfile second = service.findByCustomerId("C-001");

    assertSame(first, second);
    verify(repository, times(1)).findByCustomerId("C-001");
}
~~~

The snippet above only tests a plain service; if using `@Cacheable`, invoke it through a Spring proxy in a test context for the annotation to take effect. A unit test instantiating the object with `new` will not exercise Spring AOP caching.

Scenarios to test:

- Cache hits do not call the source again.
- Cache misses call the source and store the result.
- Different keys do not collide on entries.
- Different tenants do not share data.
- Null/negative results follow TTL and policy.
- Expired or evicted entries reload properly.
- Cache failures follow fail-open/fail-closed policies.
- Concurrent threads missing the same key do not create unexpected load.
- Mutable outputs are not altered across items.

## 29. Testing Spring Batch integration

An integration test should run a Step with multiple items having repeated reference keys and verify both outputs and load counts:

~~~text
Input:
  Order 1 -> customer C-001
  Order 2 -> customer C-001
  Order 3 -> customer C-002
  Order 4 -> customer C-001

Expected reference loads:
  C-001 -> 1 time during cache lifetime
  C-002 -> 1 time during cache lifetime
~~~

Verify:

- Each item's output remains accurate.
- Backend query count decreases as expected.
- Cache keys do not mix tenants/policies.
- Retries do not duplicate side effects.
- Rollbacks do not leave uncommitted data in the cache.
- Restarts work properly when the cache is cold.
- Partitions or multiple `JobExecution` runs do not share state across wrong boundaries.

If using a local cache, restart tests should recreate the application context or cache instance to prove the Job does not depend on warm cache state. If using a distributed cache, test invalidation, TTL, and connection failures with an appropriate test provider.

## 30. Common pitfalls

**Caching an entire processor with side effects:** cache hits bypass the delegate and can skip required business operations. Only cache reads or deterministic computations.

**Omitting tenant or policy version from cache keys:** can return data from another context. Include every factor affecting the result in the key.

**Unbounded caches:** batches with many unique keys can grow the heap continuously. Set maximum size/weight and TTL.

**Caching mutable outputs:** subsequent items may see objects mutated by earlier items. Use immutable values or copies.

**Using `@Cacheable` in self-invocation:** internal calls bypass the proxy so caching advice does not run as expected. Split beans or call through a proxy.

**Assuming cache puts roll back with the database:** caches normally do not participate in chunk transactions. Do not cache state dependent on uncommitted changes.

**Using a cache for deduplication:** cache evictions, restarts, or multiple instances can cause side effects to run again. Use idempotency keys and unique constraints.

**Caching nulls for too long:** newly created records continue to appear non-existent. Negative caches need short TTLs and clear semantics.

**Ignoring cache stampedes:** concurrent misses hit the backend with many requests. Use atomic loading/single-flight when needed.

**Treating a local cache as shared across partitions:** each JVM has its own cache. Evaluate cache scope and worker topology.

**Caching policies that change without versioning:** the same Job may apply inconsistent rules. Pin policy versions or batch snapshots.

**Putting business IDs in metric tags:** creates high cardinality and risks exposing data. Use low-cardinality tags.

**Not testing cold cache on restart:** the Job might only work when the cache is warm. Ensure caching is purely a performance optimization, not a required source of state.

## Conclusion

A caching processor reduces repeated queries and service calls when many items share data or reusable results. Prefer caching reference data inside a service called by the processor; only cache full outputs when processing is deterministic, keys are complete, and there are no side effects. Choose providers, TTLs, eviction, and invalidation according to freshness requirements, memory budgets, and worker topology. Ensure cache keys include tenant/context/version, values are immutable, caches are thread-safe, and cache failures have clear policies. Caches usually do not participate in chunk transactions and local caches are lost on restart, so never use them as replacements for checkpoints, idempotency, or business state. Measure hits/misses and backend load, and test cache hits, cold caches, concurrency, rollbacks, and restarts in Step integration tests to prove caching only accelerates execution without altering business outcomes.
