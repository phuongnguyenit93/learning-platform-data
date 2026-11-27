# Impact of cache, share, and Multiple Subscriptions on Queries

## 1. A reactive publisher does not equal a single query execution

In Spring Data R2DBC, repository methods typically return `Mono<T>` or `Flux<T>`. These types describe a data stream that executes when subscribed to. Calling a repository method creates a publisher; each time the source publisher is subscribed to, it can trigger a fresh SQL execution.

Example:

~~~java
Mono<Customer> customerQuery = customerRepository.findById(42L);
~~~

That line builds a publisher describing a query to find the customer with ID 42. If this publisher is subscribed to twice, the repository usually executes the query twice:

~~~java
StepVerifier.create(customerQuery)
        .expectNextCount(1)
        .verifyComplete();

StepVerifier.create(customerQuery)
        .expectNextCount(1)
        .verifyComplete();
~~~

Two independent subscriptions may fetch data at different times, borrow two separate connections, and observe two different database states.

This is normal behavior for the cold publishers returned by Spring Data R2DBC. A cold publisher starts work anew for each subscriber. This gives each consumption its own execution, but it also means a publisher used across multiple pipeline branches can inadvertently generate multiple SQL statements.

Three mechanisms commonly discussed to control this are:

- **Multiple subscriptions:** each subscriber can re-trigger the data source.
- **cache():** shares a single source subscription and stores signals/results to replay to later subscribers.
- **share():** shares a single source subscription among concurrent participating subscribers, following Reactor's multicast semantics.

Understanding their differences helps prevent duplicate queries, stale data, excessive memory consumption, and transaction bugs when using R2DBC.

## 2. Cold publishers and the R2DBC query lifecycle

A repository query is normally a cold publisher. When subscribed to, the publisher begins interacting with the database:

~~~text
Repository method called
          |
          v
    Mono / Flux created
          |
          v
       subscribe()
          |
          v
 Acquire connection from ConnectionFactory
          |
          v
 Send SQL via R2DBC driver
          |
          v
 Receive and map results
          |
          v
 Complete / Error / Cancel
          |
          v
 Return connection to pool
~~~

With `Mono<Customer>`, one subscription can emit at most one `Customer` or complete empty. With `Flux<Customer>`, one subscription can emit multiple rows.

When a subscriber consumes a `Flux` from the database, the connection may be held while the stream is still reading results. The connection is normally released when the publisher completes, emits an error, or is cancelled per driver/framework lifecycle.

If the same `Flux` is subscribed to multiple times, each subscription can re-execute the SQL and use its own connection. With a bounded pool, accidentally creating multiple concurrent subscriptions can raise the number of borrowed connections and cause pool contention.

Do not assume a repository publisher automatically stores results just because it was assigned to a variable. Storing a variable only holds a reference to the publisher; it does not turn a cold source into a cache.

## 3. Multiple subscriptions can execute a query multiple times

### 3.1. Subscribing twice

~~~java
Mono<Customer> query = customerRepository.findById(42L);

query.subscribe(customer -> log.info("First: {}", customer));
query.subscribe(customer -> log.info("Second: {}", customer));
~~~

Two `subscribe()` calls create two subscriptions. With a cold repository publisher, each subscription can run a separate `SELECT` statement.

Beyond querying the database twice, this code creates two independent execution paths. Errors go to two separate subscribers instead of returning to a caller as a single publisher. In WebFlux services, avoid calling `subscribe` yourself to handle results; return the publisher or chain steps using Reactor operators.

### 3.2. Reusing the same publisher across two branches

A subtler mistake is using the same publisher across multiple branches:

~~~java
Mono<Customer> customer = customerRepository.findById(customerId);

return Mono.zip(
        customer.map(Customer::name),
        customer.map(Customer::email)
);
~~~

`Mono.zip` subscribes to each component source. Both branches here reference the same cold publisher, so the query can execute twice.

If the goal is to fetch one `Customer` and derive both name and email from the same result, read once and transform the object:

~~~java
return customerRepository.findById(customerId)
        .map(found -> new CustomerContact(
                found.name(),
                found.email()
        ));
~~~

If downstream branches genuinely need to consume the same result independently, you can create a cached publisher within an appropriate scope:

~~~java
Mono<Customer> sharedCustomer =
        customerRepository.findById(customerId).cache();

return Mono.zip(
        sharedCustomer.map(Customer::name),
        sharedCustomer.map(Customer::email)
);
~~~

This way, the branches subscribe to the cached publisher; the repository source is subscribed to once and the signal is replayed. Still, only use `cache` when reusing the exact same result is valid for business logic and the publisher's lifetime is controlled.

### 3.3. Operations that commonly create new subscriptions

Situations that can trigger additional subscriptions include:

- Calling `subscribe()` multiple times.
- Calling `block()` multiple times on the same publisher.
- Returning the same publisher to multiple independent callers.
- Using a cold publisher in multi-branch operators like `zip`.
- Using `retry` or `repeat`, causing upstream to be re-subscribed.
- Frameworks or adapters consuming the publisher across multiple lifecycles.
- Tests passing the same publisher into multiple `StepVerifier` runs.

Read the pipeline carefully to determine which subscriptions actually reach the database source. Not every operator creates an extra subscription; standard operators usually pass through the same subscription. However, operators combining multiple publishers or resubscription mechanisms can trigger the source multiple times.

## 4. cache() turns a source into a replaying publisher

Reactor provides the `cache()` operator for `Mono` and `Flux`. After the first subscription, `cache` retains signals from the source and replays them to later subscribers according to the selected cache policy.

With `Mono`:

~~~java
Mono<Customer> cachedCustomer =
        customerRepository.findById(42L).cache();
~~~

When the first subscriber subscribes, the repository source executes. The result or terminal signal is cached. Subsequent subscribers receive the stored signal without re-running the source query for the lifetime of that cache.

~~~text
                    Subscriber A
                         |
                         v
                +----------------+
                |  Mono.cache()  |
                +----------------+
                         |
                  subscribe source
                         |
                         v
                Repository SELECT
                         |
                         v
                  Customer / Empty
                         |
                 Store cached signal
                         |
             +-----------+-----------+
             |                       |
             v                       v
       Subscriber B            Subscriber C
     receives cached         receives cached
         signal                  signal
~~~

An important distinction: `cache` stores **reactive signals**, not merely successful values. For `Mono`, the cached signal can be:

- An `onNext` value followed by complete.
- Empty completion, meaning no result was found.
- An error signal.

Thus, errors or empty results can also be replayed to later subscribers. Never assume `cache` retains only successful values.

### 4.1. cache() does not automatically know when data changes

~~~java
Mono<Customer> customer = customerRepository.findById(id).cache();
~~~

Once the source emits `Customer`, later subscribers receive the same cached object/result. If another operation updates the record, the cached publisher does not automatically re-query for fresh data.

`cache` does not synchronize with the database, does not watch `UPDATE`/`DELETE` statements, and does not auto-invalidate when a repository saves another entity. If fresh data is required, create a new publisher or implement an explicit invalidation/TTL strategy.

### 4.2. Caching is tied to the publisher instance

`cache()` is not a distributed cache or an automatic application-wide cache. It is bound to the specific publisher instance created and held by reference.

Example:

~~~java
public Mono<Customer> findCustomer(Long id) {
    return customerRepository.findById(id).cache();
}
~~~

Each call to this method creates a new cached publisher. If two requests call the method separately, they usually get two different cache instances and run two separate queries.

Conversely, storing a cached publisher in a singleton field keeps that cache alive for the bean's lifetime and can serve stale data for a long time. Do not keep an unbounded cached field for data varying by ID, tenant, or user without proper keying, eviction, and invalidation.

## 5. Caching with TTL and bounded history

Indefinite caching can fit an immutable result within a very short scope, but it is usually unsuitable for mutable database data.

Reactor supports caching with a TTL:

~~~java
Mono<Customer> cachedCustomer =
        customerRepository.findById(id)
                .cache(Duration.ofSeconds(30));
~~~

After the TTL expires, the cached signal can expire and the next subscription re-triggers the source per operator semantics. TTL bounds maximum staleness over time, though it does not guarantee updates appear immediately after database changes.

With `Flux`, you can cache a bounded history:

~~~java
Flux<CustomerSummary> cachedSummaries =
        customerRepository.findAll()
                .map(CustomerSummary::from)
                .cache(100);
~~~

Bounded cache history limits how many elements are retained for replay. Check the exact semantics of your Reactor version and assess whether replaying a long stream is actually needed.

### 5.1. Caching an entire Flux can retain a lot of data

~~~java
Flux<Customer> allCustomers =
        customerRepository.findAll().cache();
~~~

If the table has millions of rows, unbounded caching can keep the entire result set on the heap. This puts heavy pressure on memory, increases GC pauses, and can trigger `OutOfMemoryError`.

Do not cache an entire large query just to avoid running SQL a second time. Consider pagination, bounded history, caching small DTOs, TTLs, or a dedicated cache with key-based eviction and capacity limits.

### 5.2. TTL is not a business invalidation mechanism

Suppose a cache has a 30-second TTL. A request updates `Customer` right after the cache is populated. Subsequent subscribers within those 30 seconds can still receive stale data.

If immediate invalidation after writes is required, explicitly design cache deletion/replacement upon updates, or use a cache abstraction with suitable keys and eviction. Setting a TTL simply declares a policy tolerating stale data for that window.

## 6. cache() affects errors and empty results too

For `Mono`, `cache` retains terminal signals. Example:

~~~java
Mono<Customer> cached =
        customerRepository.findById(id).cache();
~~~

If the ID does not exist, the source completes empty. `cache` stores the empty signal, so later subscribers also receive empty instead of re-running the `SELECT`.

If the first query hits a connection failure, the error signal may be cached. Later subscribers receive the same cached error rather than necessarily attempting a new database call.

This can be undesirable for transient errors. If you want to retry the source first and cache only the final outcome, order the operators accordingly:

~~~java
Mono<Customer> result =
        customerRepository.findById(id)
                .retryWhen(retryPolicy)
                .cache(Duration.ofSeconds(20));
~~~

The source is retried per policy; the final terminal outcome after retries is cached.

Conversely:

~~~java
Mono<Customer> result =
        customerRepository.findById(id)
                .cache()
                .retryWhen(retryPolicy);
~~~

If the cache already stored an error, downstream retry may merely resubscribe to the cache and get the same error back instead of executing a fresh repository query. Thus, placing `cache()` relative to `retryWhen()` changes behavior.

Never cache errors indefinitely if the goal is automatic recovery when the database comes back online. Choose retries, TTLs, and invalidation according to error type and data semantics.

## 7. share() shares one source subscription across subscribers

`share()` is a multicast operator. With `Flux`, it allows multiple subscribers to receive elements emitted from a single source subscription while they are concurrently subscribed.

Example:

~~~java
Flux<Customer> sharedCustomers =
        customerRepository.findAll().share();

Flux<String> names =
        sharedCustomers.map(Customer::name);

Flux<String> emails =
        sharedCustomers.map(Customer::email);

return Flux.merge(names, emails);
~~~

When two branches subscribe close together to the same shared `Flux`, they can share one source subscription instead of each branch running its own query.

This is useful when multiple consumers need to observe the same live stream. However, `share` does not share the same semantics as `cache`.

### 7.1. share does not replay history like cache

With a shared `Flux`, a subscriber joining after some elements were already emitted will not receive earlier elements. Subscribers receive elements emitted while they are subscribed, along with terminal signals per source/operator semantics.

Suppose a source emits A, B, C sequentially:

~~~text
Time       -------------------------------------->

Source      A -------- B -------- C -------- complete

Subscriber 1  subscribe ------------------------>
Receives     A -------- B -------- C

Subscriber 2             subscribe ------------>
Receives                B -------- C

Subscriber 3                         subscribe ->
Receives                            C
~~~

This is a live multicast model. If subscribers need the complete results from the beginning, `share` is not suitable; you need replay/cache or a fresh query.

With finite database publishers, late subscribers can miss already emitted rows. Do not use `share` as a way to cache query results.

### 7.2. share is not a persistent cache

`share()` creates no cache keys, has no business TTL, performs no per-entity eviction, and does not survive process restarts. It does not replace Redis, Caffeine, or a managed application cache.

Nor is it a cluster-wide deduplication mechanism. Two application instances with separate `share` publishers still run two independent queries.

### 7.3. Subscriber cancellation affects the source

With multicast/refCount semantics, the source connects when the first subscriber joins. When subscribers leave, the source connection may be cancelled according to the operator's rules. As long as one subscriber remains, the source generally continues serving it.

With R2DBC `Flux` queries, cancelling upstream can end result-set reading and release the connection early. Exact behavior depends on the Reactor version and driver. Test carefully with long streams or cancellable subscribers.

Do not use `share` to hide a subscriber failing to consume data. A slow or non-cancelling subscriber can extend the source's lifetime and hold the connection longer than expected.

## 8. Comparing cache(), share(), and cold publishers

| Characteristic | Cold repository publisher | cache() | share() |
|---|---|---|---|
| Source subscription | Each subscription can re-run the query | Typically once per cache instance | Shares source subscription across connected subscribers |
| Replays past data | No | Yes, per cache history/TTL | Does not replay Flux history |
| Late subscriber | Starts a new query | Receives cached signal/results | Receives only items emitted after joining |
| Fresh DB data | New query can observe new data | Can be stale until expiry/invalidation | New subscriber after reset can trigger a new subscription per operator semantics |
| Memory | Does not hold full results just because publisher was created | Can hold signals and many elements | Does not retain replay history like cache |
| Primary purpose | Independent execution per consumption | Reuse and replay results | Multicast a live emitting stream |
| Primary risk | Duplicate queries, higher connection usage | Stale data, memory retention, caching errors/empty | Subscribers missing data, complex lifecycle/cancellation |

Choose the operator based on the business question:

- Does each request need fresh data? Use a cold publisher and let each request run its query.
- Do multiple branches in the same task need the same read result? Caching within a short publisher scope can work.
- Do multiple concurrent subscribers need to observe the same active stream? Consider `share`.
- Do you need caching by ID, tenant, TTL, invalidation, and bounded memory? Use a proper cache abstraction rather than an unmanaged publisher cache.

## 9. Multiple subscriptions and reactive transactions

This is especially important with Spring Data R2DBC. Reactive transactions are bound to the subscription and Reactor Context. A transactional method returns a publisher; when subscribed through the proxy, the transaction manager opens a transaction for that subscription.

If a cold publisher is subscribed to twice, the two executions can run in two separate transactions if each is wrapped by its corresponding transaction boundary.

Example:

~~~java
@Transactional
public Mono<Customer> findCustomer(Long id) {
    return customerRepository.findById(id);
}
~~~

If a caller invokes this method through the Spring proxy twice and subscribes to both publishers, each call can have its own transaction lifecycle depending on propagation configuration and the transaction manager.

### 9.1. Do not cache transaction-bound data and reuse it across transactions

Suppose a publisher is cached and reused across multiple requests:

~~~java
Mono<Account> cachedAccount =
        transactionalService.loadAccount(accountId).cache();
~~~

The first subscription may run the query in the first transaction/context. A later subscriber can receive the cached result without running a query in its own fresh transaction. The result may no longer reflect current state and is no longer read under the later subscriber's isolation or security context.

For data depending on tenant, user, permissions, or transaction snapshots, this poses a serious risk. Never share a global cached publisher across callers with different contexts.

If application-level caching is required, define keys incorporating every dimension affecting the result (such as tenant and ID), enforce authorization before reading the cache, set explicit TTL/invalidation, and avoid storing connections/transactions in the cache.

### 9.2. Cache inside a @Transactional method must be understood properly

Example:

~~~java
@Transactional
public Mono<Customer> loadAndCache(Long id) {
    return customerRepository.findById(id).cache();
}
~~~

The transaction interceptor wraps the publisher returned by the method. The first subscription activates both the transaction and the cached source. Once the result is cached, subsequent subscribers may receive the stored data without executing a new query. Do not assume every subsequent subscriber performs a fresh database read merely because the method has `@Transactional`.

When data must be read fresh within each caller's transaction, do not attach `cache` to that publisher. Create a fresh query publisher per subscription or place caching at a different layer with clear semantics and scope.

## 10. Connection pool and the cost of duplicate queries

Every subscription to a cold publisher can trigger a connection acquisition and SQL execution. When multiple subscribers trigger queries simultaneously, the connection pool can come under pressure.

Example of a request creating multiple independent branches:

~~~java
Mono<Customer> customer = customerRepository.findById(id);

Mono<String> name = customer.map(Customer::name);
Mono<String> status = customer.map(Customer::status);
Mono<String> email = customer.map(Customer::email);

return Mono.zip(name, status, email);
~~~

The three branches can cause the same query to be subscribed to three times. Under high traffic, this pattern generates duplicate identical queries and increases database load.

The simple approach is to transform once:

~~~java
return customerRepository.findById(id)
        .map(found -> new CustomerView(
                found.name(),
                found.status(),
                found.email()
        ));
~~~

If there is a reason to keep separate branches, cache the result within the scope of that task:

~~~java
Mono<Customer> customer = customerRepository.findById(id).cache();

Mono<String> name = customer.map(Customer::name);
Mono<String> status = customer.map(Customer::status);
Mono<String> email = customer.map(Customer::email);

return Mono.zip(name, status, email);
~~~

This cached publisher should only be created for a single specific request/task and never stored in a singleton field without key management and invalidation policies.

For streaming `Flux`, a single subscription can hold a connection for the entire read duration. `share` can allow multiple subscribers to consume a single stream, whereas `cache` may need to read and store many elements. Both affect backpressure, memory, and connection hold times.

## 11. Retry and repeat can also re-run SQL

Reactor provides resubscribing operators such as `retry`, `retryWhen`, and `repeat`.

Example:

~~~java
Mono<Customer> customer =
        customerRepository.findById(id)
                .retryWhen(retryPolicy);
~~~

When an error matching the policy occurs, `retry` re-subscribes to the source. With a cold repository, the `SELECT` statement can be re-executed.

`repeat` can re-subscribe after the publisher completes:

~~~java
Flux<Customer> polling =
        customerRepository.findByStatus("PENDING")
                .repeat(3);
~~~

This can execute multiple queries. Distinguish `retry` after an error from `repeat` after completion: `retry` is for trying again on failure; `repeat` is for running again after completion.

### 11.1. Order of retry and cache changes outcomes

Retry before cache:

~~~java
Mono<Customer> cached =
        customerRepository.findById(id)
                .retryWhen(retryPolicy)
                .cache(Duration.ofSeconds(10));
~~~

The source can be retried per policy; the final signal after retries is cached.

Cache before retry:

~~~java
Mono<Customer> result =
        customerRepository.findById(id)
                .cache()
                .retryWhen(retryPolicy);
~~~

If the cache already holds an error, retry may merely receive the same error from the cache instead of running a new database query. Placing `cache` before `retry` can defeat the purpose of retrying.

When retrying a write command, evaluate whether the previous attempt might have committed while its response was lost. Retrying an additive update can apply the change twice. Use idempotency keys, unique constraints, or idempotent SQL statements when commit status is uncertain.

## 12. Multiple subscriptions on write operations

Multiple subscriptions do not only cause duplicate `SELECT`s. With `INSERT`, `UPDATE`, or `DELETE`, a new subscription can re-execute the side effect.

Example:

~~~java
Mono<Customer> create =
        customerRepository.save(new Customer(
                null,
                "An Nguyen",
                "an@example.test"
        ));

create.subscribe();
create.subscribe();
~~~

Two subscriptions can produce two inserts. If the ID is database-generated and there is no unique business key, the database may store two distinct rows. If a unique constraint exists, the second subscription can fail.

With additive updates:

~~~java
Mono<Long> increment =
        databaseClient.sql("""
                UPDATE inventory
                SET quantity = quantity + 1
                WHERE sku = :sku
                """)
            .bind("sku", sku)
            .fetch()
            .rowsUpdated();
~~~

Subscribing twice increments `quantity` twice. The same publisher does not imply a single execution.

### 12.1. Do not use cache() as an idempotency mechanism for writes

A cached `Mono` may prevent the same publisher instance from running the source multiple times:

~~~java
Mono<Customer> cachedWrite =
        customerRepository.save(customer).cache();
~~~

However, this is not a reliable idempotency mechanism for an API:

- The cache exists only in memory for that publisher's lifetime.
- Other instances or processes do not share the cache.
- Process restarts wipe the cache.
- The cache may retain errors or stale outcomes.
- A new request creates a new publisher and runs the write again.
- Caching does not protect side effects outside the publisher.

When business logic must prevent duplicate requests, use an idempotency key persisted in the database with appropriate unique constraints and transactions. Do not rely on caching a publisher to ensure exactly-once writes.

### 12.2. Retrying writes requires idempotent semantics

If the database committed but the connection dropped before the application received the result, the caller may not know whether the operation succeeded. A retry may re-execute the SQL.

For operations setting absolute values, repetition may produce the same final state. For increments, inserts, or event emission, use idempotency keys, event IDs, unique constraints, or outbox/deduplication to prevent duplicate effects.

## 13. Using cache at the right layer

There are different types of caches, each with a different scope.

### 13.1. Local cache for a single pipeline

Use `Mono.cache()` when multiple branches within one task need the same result and re-reading the database is unnecessary:

~~~java
public Mono<CustomerView> buildView(Long id) {
    Mono<Customer> customerOnce =
            customerRepository.findById(id).cache();

    return Mono.zip(
            customerOnce.map(Customer::name),
            customerOnce.map(Customer::status)
    ).map(tuple -> new CustomerView(tuple.getT1(), tuple.getT2()));
}
~~~

Even better, read once and map to a DTO if transformations can run within a single callback. Caching is useful when multiple independent subscribers must receive the result of one publisher.

### 13.2. Keyed application cache

If you want to cache results across multiple requests, use an abstraction managing keys, TTL, eviction, capacity, and concurrency. Keys must reflect every factor affecting the result:

~~~text
customer-summary:{tenantId}:{customerId}
~~~

Do not use only `customerId` if data depends on tenant or access rights. Decide whether the cache stores empty/error results or only successful outcomes; cache frameworks usually expose these semantics more cleanly than a raw publisher cache.

### 13.3. HTTP or service-layer caching

An immutable response DTO may suit application-level or HTTP caching. Still, caching responses must never bypass authorization. If content varies by user, tenant, locale, or permissions, those dimensions must be part of the cache key or the response must not be shared.

### 13.4. When not to cache

Do not cache a publisher when:

- Results must reflect the latest database state on every request.
- Results depend on a transaction snapshot or security context.
- The publisher emits a huge `Flux` without memory bounds.
- The publisher represents a write that must execute on every invocation.
- Transient errors should not be retained.
- TTL/invalidation is undefined.
- The publisher is held in a singleton containing caller-specific data.

## 14. How to observe actual query counts

When you suspect a publisher runs multiple times, measure actual executions rather than guessing from lines of code.

You can enable driver-appropriate SQL logging or observe statements via a test database. One illustrative way in unit tests is counting source subscriptions:

~~~java
AtomicInteger subscriptions = new AtomicInteger();

Mono<String> source = Mono.defer(() -> {
    subscriptions.incrementAndGet();
    return Mono.just("value");
});
~~~

Two subscriptions:

~~~java
StepVerifier.create(source).expectNext("value").verifyComplete();
StepVerifier.create(source).expectNext("value").verifyComplete();

assertThat(subscriptions.get()).isEqualTo(2);
~~~

With cache:

~~~java
AtomicInteger cachedSubscriptions = new AtomicInteger();

Mono<String> cachedSource = Mono.defer(() -> {
    cachedSubscriptions.incrementAndGet();
    return Mono.just("value");
}).cache();

StepVerifier.create(cachedSource).expectNext("value").verifyComplete();
StepVerifier.create(cachedSource).expectNext("value").verifyComplete();

assertThat(cachedSubscriptions.get()).isEqualTo(1);
~~~

This example verifies Reactor subscription semantics, not R2DBC SQL execution. To verify actual queries, use integration tests with a compatible database, SQL logging, or statement observation tools.

Also measure:

- Statements per request.
- Connection pool acquisitions.
- Connection acquire wait time.
- Execution duration and rows returned.
- Number of subscribers and when they join/cancel.
- Heap usage when caching a `Flux`.
- Retry rates and retried statement counts.

Do not enable logging of sensitive bind parameters in production without protection mechanisms.

## 15. Testing cache and share

### 15.1. Testing that cold sources re-run

~~~java
@Test
void coldPublisherExecutesForEachSubscription() {
    AtomicInteger executions = new AtomicInteger();

    Mono<Integer> source = Mono.defer(() ->
            Mono.just(executions.incrementAndGet())
    );

    StepVerifier.create(source)
            .expectNext(1)
            .verifyComplete();

    StepVerifier.create(source)
            .expectNext(2)
            .verifyComplete();
}
~~~

The test verifies that each subscription creates a new execution.

### 15.2. Testing that cache subscribes to the source only once

~~~java
@Test
void cacheReplaysTheSourceSignal() {
    AtomicInteger executions = new AtomicInteger();

    Mono<Integer> cached = Mono.defer(() ->
            Mono.just(executions.incrementAndGet())
    ).cache();

    StepVerifier.create(cached)
            .expectNext(1)
            .verifyComplete();

    StepVerifier.create(cached)
            .expectNext(1)
            .verifyComplete();

    assertThat(executions.get()).isEqualTo(1);
}
~~~

This test also shows that the second subscriber receives the stale/stored value instead of generating a new one.

### 15.3. Testing share with concurrent subscribers

With a shared `Flux`, attach two subscribers while the source is emitting. You can use a time-controlled test source or a sink to verify both subscribers receive the same elements emitted after both have subscribed.

Do not write tests relying on arbitrary sleeps. Use `StepVerifier`, `TestPublisher`, or `Sinks` to coordinate subscribe and emit timing deterministically.

### 15.4. Testing late subscribers

With `share`, verify that a subscriber joining after some elements were emitted does not receive history as `cache` does. This is a critical distinction to capture in tests.

With `cache`, verify that a late subscriber receives cached values per the configured history/TTL.

### 15.5. Testing errors and empty signals

Also test:

- `Mono` emitting one value.
- `Mono` completing empty.
- `Mono` emitting an error.
- `Flux` completing normally.
- `Flux` emitting an error mid-stream.
- TTL expiration.
- Subscriber cancelling before the source completes.

These cases confirm whether `cache`/`share` retain, replay, or cancel the source according to desired semantics.

### 15.6. Testing against a real database

Use Testcontainers or a matching test database to verify:

- Whether two repository subscriptions produce two `SELECT`s.
- Whether `cache` prevents the source query from re-running within the same publisher instance.
- Whether `share` actually multicasts a single result stream for concurrent subscribers.
- Whether cancellation releases connections as expected.
- That transaction context is not improperly shared across subscribers.
- Whether retries re-issue SQL and writes are safe to retry.

Repository mocks only assert method calls; they do not prove statement execution counts, connection lifecycles, or driver transaction behavior.

## 16. Common mistakes

| Symptom | Possible cause | How to fix |
|---|---|---|
| Same `SELECT` appears multiple times | Cold publisher subscribed in multiple branches | Read once and map; or cache within an appropriate scope |
| Using `Mono.zip` runs query twice | Same cold source passed to multiple branches | Create one cached publisher or restructure the pipeline |
| Stale data returned | Cache holds results after the database changed | TTL, invalidation, or fresh query |
| Later subscriber misses rows | Used `share` on `Flux` expecting replay | Use `cache`/replay or a fresh query |
| Heap grows sharply | Unbounded `Flux` cache retaining all results | Bound history, paginate data, or use a cache with eviction |
| Database error repeats despite retry | Error was cached before retry | Put retry before cache or avoid caching errors |
| Additive update doubled | Write publisher subscribed/retried multiple times | Idempotency keys, event deduplication, or idempotent writes |
| Connection pool exhausted | Many concurrent subscriptions/streams | Eliminate extra subscriptions, limit concurrency and stream lifetimes |
| Cache used across wrong tenant/user | Shared publisher/cache lacks context in key | Partition cache by identity/tenant and verify authorization |
| Different transactions receive same cached result | Publisher cached across transaction boundaries | Do not cache transaction-scoped data; cache at the right layer |
| `share` subscriber misses initial data | Subscriber joined after `Flux` began emitting | Use replay/cache if history is needed |
| New requests do not run new queries | Reusing a long-lived cached publisher | Create publishers per request or manage cache keys/TTLs explicitly |

## 17. Decision process for whether to cache or share

Before adding an operator, answer:

1. Is the repository source a cold publisher or already shared at another layer?
2. How many times is the publisher subscribed to within a single request?
3. Do branches truly need the exact same result, or independent fresh data?
4. Do subscribers join concurrently or at staggered times?
5. Do late subscribers need previously emitted elements?
6. How long can results tolerate staleness?
7. Does caching retain empty/error signals?
8. Could the `Flux` be very large and cause high memory retention?
9. Does the publisher depend on tenant, user, permissions, or transaction context?
10. Could any write, retry, or side effect be repeated?
11. Are TTL, invalidation, and cache keys defined?
12. Have SQL counts, connections, and memory been measured under realistic workloads?

Typical suitable choices:

- **No cache:** each request needs fresh data or the publisher represents an operation that must execute individually.
- **Short-lived `Mono.cache()`:** multiple branches within one task need the same single value.
- **`Flux.cache(history/TTL)`:** need to replay an emitted stream with controlled size/lifetime.
- **`share()`:** multiple concurrent subscribers need the same live emitting stream without history replay.
- **Keyed cache abstraction:** need to reuse data across requests with TTL, eviction, and business invalidation.

## 18. Conclusion

Spring Data R2DBC repository publishers are normally cold: each independent subscription can re-execute SQL and acquire a new connection. Therefore, reusing the same `Mono` or `Flux` across multiple branches, subscribing multiple times, blocking multiple times, or retrying/repeating can generate extra queries. For writes, repeated execution can create duplicate data or apply side effects multiple times.

`cache()` shares the source subscription and replays stored signals/results to subsequent subscribers. It can retain values, empty signals, and errors; indefinite caching or caching an entire `Flux` can cause stale data and heavy memory use. TTLs bound retention duration but do not replace business invalidation.

`share()` suits multicasting to subscribers concurrently participating in a live stream. With `Flux`, late subscribers do not receive previously emitted history as with `cache`. It is neither a keyed cache nor a durable deduplication mechanism.

Control subscription counts before reaching for operators, keep publisher caches in an appropriate scope, never share transaction- or security-context-dependent data across callers, and do not rely on `cache` to make writes idempotent. For retries or redeliverable messages, use unique constraints, idempotency keys, and appropriate transactions. Verify SQL counts, connection lifecycles, memory, and transaction behavior using integration tests on a real database/driver.
