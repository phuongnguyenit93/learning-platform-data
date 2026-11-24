# Thread Safety of Custom Components

In Spring Batch, a custom component may be invoked concurrently by multiple threads or multiple `Job` executions. If the component keeps mutable state in fields, concurrent calls can overwrite each other's data, drop items, produce wrong results, or cause hard-to-reproduce bugs. Therefore, when enabling multi-threaded `Step`s, partitioning, parallel flows, or concurrent `JobExecution`s, identify clearly which components are shared and which hold isolated state.

Thread safety is not merely adding the `synchronized` keyword. You must understand Spring bean lifecycles, `StepExecution` scope, how Spring Batch invokes readers/processors/writers, thread-bound transactions, checkpoints, and shared resources. Good designs keep components stateless, use immutable data, partition work, or isolate state per `StepExecution`. Synchronize only when you genuinely must share an inseparable resource.

## 1. What Is Thread Safety?

A component is thread-safe when multiple threads can invoke it concurrently without breaking invariants or producing inconsistent results. A component may maintain internal state, provided every read and update of that state is properly controlled.

For example, the following component is unsafe under concurrent calls:

~~~java
public class SequenceProcessor
        implements ItemProcessor<OrderInput, Order> {

    private long sequence;

    @Override
    public Order process(OrderInput input) {
        sequence++;
        return new Order(sequence, input.orderId());
    }
}
~~~

Two threads can read the same `sequence` value, increment it, and emit duplicate sequence numbers. Using `long` instead of `Long` does not solve the race condition.

A better approach is keeping business counters out of the processor. If unique sequences must be assigned, use a database-managed sequence/identity or a concurrency-safe ID service. If a counter is solely for metrics, use `AtomicLong` or a thread-safe metrics facility, never using that counter as a checkpoint or business data.

## 2. Concurrency Models in Spring Batch

Thread safety becomes critical when a `Job` processes multiple units of work concurrently. Common models:

| Model | Execution style | Primary risk |
|---|---|---|
| Multi-threaded `Step` | Chunks or step work run across multiple threads via a `TaskExecutor` | `Step` components receive concurrent calls |
| Partitioning | A manager `Step` splits data across worker `StepExecution`s | Workers share singleton beans or overwrite state/resources |
| Parallel flows | Multiple `Step` branches execute concurrently | Shared services, listeners, and resources across branches |
| Concurrent `JobExecution` | Same `Job` definition runs for multiple `JobInstance`s | Singleton beans used simultaneously by multiple runs |
| Async processing | Processor or work dispatched to an executor | Results may complete out of order and context may not propagate to all threads |

Never assume all components in every model run on the same thread. Call distribution depends on the `Step` type, executor setup, and Spring Batch version. Identify exactly which components the framework calls concurrently in your chosen model and design accordingly.

## 3. Spring Beans Are Singletons by Default

In Spring, beans without an explicit scope default to singleton scope: a single instance serves the application context. That means two distinct `JobExecution`s can share the same reader, processor, writer, tasklet, or listener instance if declared as a singleton.

Example:

~~~java
@Component
public class CustomerProcessor
        implements ItemProcessor<CustomerInput, Customer> {

    private String currentBatchId;

    public void setCurrentBatchId(String currentBatchId) {
        this.currentBatchId = currentBatchId;
    }

    @Override
    public Customer process(CustomerInput input) {
        return new Customer(currentBatchId, input.customerId());
    }
}
~~~

This design is unsafe if two `JobExecution`s update `currentBatchId` concurrently. One thread may write Job B's batch ID while another thread processes items for Job A.

Do not store per-run changing data in singleton fields. Pass batch IDs via item or method parameters, or use appropriately scoped beans when late binding is needed.

## 4. Prefer Stateless Components

A stateless component holds no mutable state between invocations. It uses only the current input and stably configured dependencies. This is usually the easiest approach to scale and test.

~~~java
@Component
public class NormalizeOrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    private final CurrencyPolicy currencyPolicy;

    public NormalizeOrderProcessor(CurrencyPolicy currencyPolicy) {
        this.currencyPolicy = currencyPolicy;
    }

    @Override
    public Order process(OrderInput input) {
        BigDecimal normalizedAmount =
                currencyPolicy.normalize(input.amount(), input.currency());

        return new Order(
                input.orderId(),
                input.customerId(),
                normalizedAmount);
    }
}
~~~

This design is safe if `CurrencyPolicy` also has no shared mutable state or manages concurrent state properly itself. Marking dependencies `final` prevents reassigning references after construction, but does not automatically make the referenced object thread-safe.

Helpful guidelines:

- Keep configuration immutable once the bean is constructed.
- Use local variables for per-invocation data.
- Never store the current item in a field.
- Never store batch IDs or partition IDs in singleton fields.
- Avoid shared mutable collections without synchronization.
- Store durable business state in the database or appropriately scoped `ExecutionContext`.

## 5. @StepScope Does Not Automatically Make Components Thread-Safe

`@StepScope` creates a target bean per `StepExecution`. It is useful for injecting that execution's `JobParameters` or `StepExecutionContext` and isolating beans across separate `StepExecution`s.

However, a single `StepExecution` can be executed by multiple threads in a multi-threaded `Step`. Those threads can invoke the same `@StepScope` target bean concurrently. Thus, `@StepScope` does not protect mutable bean fields from concurrent access.

Distinction:

| Scope | Instance scope | What scope solves | What scope does not solve |
|---|---|---|---|
| Singleton | One per application context | Sharing dependencies and configuration | Does not protect mutable state |
| `@JobScope` | One per `JobExecution` | Isolates beans across `JobExecution`s | Does not synchronize access across `Step`s/threads |
| `@StepScope` | One per `StepExecution` | Isolates beans across `StepExecution`s | Does not protect multiple threads within the same `StepExecution` |

For example, a `@StepScope` reader receiving a partition range usually fits partitioning well because each worker has its own `StepExecution`. Yet if one worker `Step` runs multiple chunk threads simultaneously, that worker's reader is still shared across threads.

Choose scope by data lifetime, then evaluate thread safety based on how the component is actually called.

## 6. Separating State by Job, Step, Partition, and Item

Before writing a custom component, determine which scope each piece of state belongs to:

| Scope | Example | Appropriate storage |
|---|---|---|
| Application-wide | Configuration, shared clients | Immutable beans or thread-safe dependencies |
| Single `JobExecution` | Batch ID, source version | `JobParameters` or `JobExecutionContext` |
| Single `StepExecution` | Checkpoint, `Step` range | `StepExecutionContext` / `ItemStream` |
| Single partition | `minId`, `maxId`, file segment | Worker's `StepExecutionContext` |
| Single item | Validation result, transformed value | Item or local variable, never shared fields |
| Long-lived business state | Processing status, business sequence | Database or business system |

Never use a singleton field to hold multi-item or multi-partition state. Never use `JobExecutionContext` as a concurrent counter updated by multiple workers without synchronization and explicit merge rules.

## 7. Readers and Thread Safety

Readers normally hold state: current position, cursor, file handle, page number, or checkpoint. Many readers are designed for sequential single-threaded reading. If multiple threads invoke `read()` concurrently, problems can occur:

- Two threads read the same item.
- An item is skipped due to non-atomic position updates.
- Item ordering changes.
- Checkpoints fail to reflect committed items.
- Cursors or file handles suffer unsupported concurrent access.

Do not share a stateful reader across threads unless the implementation explicitly guarantees thread safety.

### Using Partitioning to Isolate Readers

When data can split into independent ranges, partitioning is usually cleaner. Each worker `StepExecution` gets its own reader and data range.

~~~text
Manager Step
    |
    +--> Partition 0: IDs 1..1000 --> Reader 0 --> Writer 0
    |
    +--> Partition 1: IDs 1001..2000 --> Reader 1 --> Writer 1
    |
    +--> Partition 2: IDs 2001..3000 --> Reader 2 --> Writer 2
~~~

Readers can receive `minId`/`maxId` via `StepExecutionContext`:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<Customer> partitionReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return createReaderForRange(dataSource, minId, maxId);
}
~~~

Each worker gets a target reader scoped to its `StepExecution`. Ensure ranges do not overlap, cover all data accurately, and use stable paging order. With keyset paging, sort keys should be unique or paired with deterministic tie-breakers.

### SynchronizedItemStreamReader

Spring Batch provides `SynchronizedItemStreamReader` to synchronize `read()` calls on a delegate `ItemStreamReader`. It can help when sharing a non-thread-safe reader in certain setups.

Synchronizing `read()` serializes item retrieval, which can limit concurrency gains on the reader side. Moreover, sequentially read items can still be processed and written on different chunks/threads finishing out of order. If checkpoints update while chunks finish out of order, evaluate restart behavior and item reprocessing carefully.

`SynchronizedItemStreamReader` does not turn the whole pipeline into an ordered chain, nor does it automatically make every delegate method thread-safe. Check the API docs for your Spring Batch version and test restarts before choosing this wrapper.

## 8. Processors and Thread Safety

Stateless processors parallelize easily because each call handles an independent item. Risks emerge when a processor:

- Writes the current item into a field.
- Uses a shared mutable `HashMap` or `ArrayList`.
- Increments an unsynchronized counter.
- Uses non-thread-safe formatters or parsers.
- Calls services holding mutable state.
- Uses `ThreadLocal` without proper cleanup.
- Relies on item arrival order to compute results.

Unsafe example:

~~~java
public class PriceProcessor implements ItemProcessor<Input, Output> {

    private final Map<String, BigDecimal> rates = new HashMap<>();
    private Input current;

    @Override
    public Output process(Input item) {
        current = item;
        BigDecimal rate = rates.get(item.currency());
        return convert(current, rate);
    }
}
~~~

The `current` field can be overwritten by another thread. `HashMap` is unsafe under concurrent modifications. If `rates` is loaded once and never mutates, build an immutable map at construction time:

~~~java
public class PriceProcessor implements ItemProcessor<Input, Output> {

    private final Map<String, BigDecimal> rates;

    public PriceProcessor(Map<String, BigDecimal> configuredRates) {
        this.rates = Map.copyOf(configuredRates);
    }

    @Override
    public Output process(Input item) {
        BigDecimal rate = rates.get(item.currency());
        if (rate == null) {
            throw new UnsupportedCurrencyException(item.currency());
        }
        return convert(item, rate);
    }
}
~~~

`Map.copyOf` returns an unmodifiable copy. Values inside should also be immutable objects; an unmodifiable collection holding mutable values still needs protection.

## 9. Writers and Thread Safety

A writer can receive concurrent chunks in a multi-threaded `Step` or be shared across workers if declared as a shared bean. Determine whether the writer supports concurrent calls.

### JDBC Writers

Built-in writers such as `JdbcBatchItemWriter` are typically configured once and used across a `Step`. `NamedParameterJdbcTemplate`/`JdbcTemplate` are designed for shared use once configured. Still, custom parameter providers, callbacks, or dependencies invoked by the writer must also be thread-safe.

Never store an active `Connection` or `PreparedStatement` in a writer field. Use `JdbcTemplate`/`NamedParameterJdbcTemplate` so the framework obtains connections bound to the active transaction.

### File Writers

Two threads writing to the same file can interleave bytes, reorder lines, or corrupt records. When parallel output is required, prefer one separate file per partition and merge them in a subsequent `Step` once all workers finish.

Use `synchronized` writes only if serialized writing is acceptable and you have verified ordering, flushing, checkpointing, and restart behavior. Locking around an entire writer often eliminates most benefits of parallelism.

### Custom Writers with Buffers

If a writer keeps a `StringBuilder`, list, or buffer in a field, concurrent calls can mix data. Use per-invocation local buffers or synchronize critical sections carefully. Also consider buffer flushing/clearing on transaction rollbacks: data pushed outside a transaction is not automatically undone.

## 10. Example Custom JDBC Writer

A custom writer can use `JdbcTemplate` without keeping per-item mutable state:

~~~java
public class AuditItemWriter implements ItemWriter<AuditRecord> {

    private final JdbcTemplate jdbcTemplate;

    public AuditItemWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends AuditRecord> chunk) {
        jdbcTemplate.batchUpdate(
                """
                INSERT INTO batch_audit(record_id, event_type, created_at)
                VALUES (?, ?, ?)
                """,
                chunk.getItems(),
                chunk.size(),
                (statement, item) -> {
                    statement.setString(1, item.recordId());
                    statement.setString(2, item.eventType());
                    statement.setTimestamp(3, Timestamp.from(item.createdAt()));
                });
    }
}
~~~

The writer holds no items or statements in fields. `JdbcTemplate` manages JDBC callbacks and retrieves connections from the current transaction context. Crucially, `JdbcTemplate`'s `DataSource` must participate in the transaction manager used by the `Step`.

If the writer also records metrics, use a concurrency-safe metrics library. Do not increment a shared `long` field and treat it as the committed record count: the writer may be retried or chunks may roll back. Business counts should be reconciled from the database or `StepExecution` metadata.

## 11. Tasklets and Listeners

Tasklets and listeners can also be singleton beans. If the same instance executes across multiple `StepExecution`s, per-run mutable fields create race conditions.

For `Tasklet`s:

- Avoid storing `execute()` invocation state in singleton fields.
- Use local variables or `ExecutionContext` for required checkpoints.
- Use `@StepScope` if the tasklet depends on parameters or state specific to a `StepExecution`.
- If multiple threads run within the same `StepExecution`, protect shared state anyway.

For listeners:

- Do not assume callbacks always fire in a global sequential order under concurrency.
- Do not use a shared `ArrayList`/`HashMap` to collect concurrent callbacks.
- Do not rely on listeners to perform non-idempotent side effects.
- If results must be aggregated, use thread-safe collectors or persist events durably and aggregate later.

Listeners fire at various lifecycle points. Distinguish item, chunk, `Step`, and `Job` callbacks so events from different threads do not get conflated.

## 12. ExecutionContext Is Not an Arbitrary Concurrent Store

`ExecutionContext` is meant for recoverable state. It should not be treated like a general-purpose `ConcurrentHashMap` across threads.

In partitioning, each worker has its own `StepExecutionContext`, ideal for storing that worker's checkpoints or ranges. In a multi-threaded `Step`, multiple chunk threads operate within one `StepExecution`; updating context keys from multiple threads requires explicit design.

Principles:

- Each component owns a dedicated namespaced set of keys.
- Do not let multiple threads write to the same key without merge rules.
- Do not update contexts from custom threads outside the Spring Batch lifecycle without controlling transaction/persistence semantics.
- Store only small data needed for restarts.
- Never store the active item in context as a shared variable.

To aggregate metrics across partitions, have each worker write its own result and let the manager `Step` read and combine them once workers complete. This avoids contention on a shared key.

## 13. ItemStream Lifecycle and Thread Safety

Readers/writers implementing `ItemStream` have three callbacks: `open()`, `update()`, and `close()`. This is a stream lifecycle per `StepExecution`, not per-item callbacks.

Avoid:

- Opening/closing the same resource on every read or write when the component is meant to hold the resource across the `Step`.
- Letting multiple threads update one checkpoint key unsynchronized.
- Closing a reader or writer from one thread while another thread is still using it.
- Assuming `close()` on one thread waits for application-spawned background work to finish.

In partitioning, give each worker its own stream/resource. When sharing a component across threads, establish explicit synchronization contracts across read/write and checkpoints. Synchronizing `read()` alone does not resolve `update()`/`close()` coordination.

## 14. Transactions Are Thread-Bound

In Spring's standard transaction model, transactions bind to the current thread. A chunk transaction does not automatically propagate to new threads spawned by the application.

This implies:

- Do not use `new Thread` or `parallelStream()` inside a processor/writer to run database work expecting it to join the chunk transaction.
- Do not keep a JDBC `Connection` in a field to share across threads.
- Use `JdbcTemplate` or repositories to retrieve connections bound to the active transaction.
- If async work is required, design dedicated transaction boundaries and error handling for async tasks.
- Commit chunks only after all work belonging to the chunk completes under the configured model.

If a worker thread opens its own transaction, that transaction can commit even when the main chunk transaction rolls back. This causes data divergence without coordination.

Across multiple resources or databases, local transactions do not automatically ensure cross-resource atomicity. Consider suitable transaction managers, distributed transactions, or outbox/compensation patterns.

## 15. Shared Resources and External Clients

Dependencies like HTTP clients, cache clients, or connection pools may be designed for sharing, yet you must check each implementation's thread-safety contract.

Examples:

- `JdbcTemplate` and `NamedParameterJdbcTemplate` are designed for shared use once configured.
- Some HTTP clients are immutable/thread-safe, whereas certain request builders or response objects are single-request only.
- `EntityManager` must not be held in a field and used concurrently outside managed transactions/contexts.
- File streams, cursors, and mutable parsers are usually unsafe for concurrent access.
- A cache may be thread-safe for single operations while still non-atomic across read-modify-write sequences.

Never assume an object is thread-safe simply because Spring injects it. Spring handles lifecycle and dependency injection; thread safety belongs to the object's contract and how your code uses it.

## 16. Atomics and Concurrent Collections

When data genuinely must be shared across threads, use appropriate concurrency primitives:

| Need | Suitable option |
|---|---|
| Technical counters | `AtomicLong` or `LongAdder` |
| Concurrently updated map cache | `ConcurrentHashMap` |
| Append-only event list | `ConcurrentLinkedQueue` |
| Compound state needing atomic updates | `synchronized`, `Lock`, or atomic reference/update functions |
| Per-partition results | Per-partition collections merged afterward |

`ConcurrentHashMap` protects individual map operations, yet multi-step sequences can still race. Checking `containsKey` followed by `put` is not atomic; use `computeIfAbsent` or appropriate atomic methods.

`AtomicLong` protects increments, but does not tie into database transactions. If a processor increments a counter and the chunk rolls back, the counter keeps the incremented value. Therefore, use in-memory counters only for telemetry or non-transactional purposes.

## 17. Synchronized and Lock Limitations

The `synchronized` keyword ensures only one thread at a time executes a guarded block on the same monitor. It works well for protecting small invariants:

~~~java
public class InMemoryAuditCollector {

    private final List<AuditRecord> records = new ArrayList<>();

    public synchronized void add(AuditRecord record) {
        records.add(record);
    }

    public synchronized List<AuditRecord> snapshot() {
        return List.copyOf(records);
    }
}
~~~

This synchronizes access to the list. However, all threads must share the same collector instance; instantiating multiple collectors leaves state unprotected. `snapshot()` also copies the list inside the lock, so large lists can increase contention.

Do not place `synchronized` around an entire `process()` or `write()` method if it performs slow network/database calls unnecessarily. Overly broad locks serialize threads and defeat concurrency.

When using `Lock`, always release it inside `finally`. With `synchronized`, the monitor releases automatically on block exit, even on exceptions.

## 18. Processing Order and Parallel Results

Parallel processing generally does not guarantee completion order matches read order. For instance, item 1 may take 2 seconds while item 2 takes 100 ms; item 2 can finish before item 1.

If business logic requires ordering:

- Partition by key so dependent items stay in the same partition.
- Preserve ordering within each partition if needed.
- Use sequence/version checks so writers detect stale updates.
- Use bounded reordering if global order must be restored.
- Avoid parallelism for strictly sequential stages if invariants cannot be preserved.

Do not rely on a sequence field in a processor to infer item ordering under concurrency. Invocation order of `process()`, completion order, and commit order can all differ.

## 19. Partitioning Usually Isolates State Better

When workloads split into independent regions, partitioning gives each worker:

- Its own `StepExecution`.
- Its own `StepExecutionContext`.
- Dedicated scoped reader and writer.
- Isolated resources or files.
- Disjoint data-lock ranges.

Example partitioning by region:

~~~java
@Bean
@StepScope
ItemReader<Customer> customerReader(
        @Value("#{stepExecutionContext['regionCode']}") String regionCode,
        CustomerRepository repository) {

    return new RegionCustomerReader(repository, regionCode);
}
~~~

The partitioner assigns a different `regionCode` to each worker. Each worker's reader reads only its assigned region.

Partitioning does not eliminate every race condition. If two partitions update the same customer ID or the same summary table, the database can still experience lock contention or lost updates. Design partition keys to minimize output overlap.

## 20. Be Careful with ThreadLocal

`ThreadLocal` stores per-thread values and can help for short-lived technical context. However, thread pools reuse threads across many items and `JobExecution`s. Failing to remove values leaks prior task data into subsequent tasks.

Never use `ThreadLocal` to replace `JobParameters` or `ExecutionContext`. Those belong to an execution, not a thread identity, because one execution can span many threads and one thread serves many executions over time.

If `ThreadLocal` is unavoidable:

- Set values within a well-defined scope.
- Clear via `remove()` in `finally`.
- Never store large objects or sensitive data.
- Never assume child threads inherit values automatically.
- Test against reused executor thread pools.

## 21. Retries and Idempotency in Concurrent Environments

Retries can cause the same item or chunk to run multiple times. When multiple threads retry concurrently, check-then-write sequences can race:

~~~text
Thread A: check that order does not exist yet
Thread B: check that order does not exist yet
Thread A: insert order
Thread B: insert order
~~~

Java-level checks do not replace database unique constraints. Use unique keys, upserts, optimistic locking, or idempotency keys to enforce invariants in the data store.

Non-transactional actions such as sending emails or calling transactional APIs need stable idempotency keys. Timeouts can trigger retries even when the remote system processed the request and only the response was lost.

## 22. Example Race Condition Test

Sequential unit tests miss many concurrency bugs. Use `CountDownLatch`, `CyclicBarrier`, or executors to drive controlled concurrent calls.

Example testing the collector:

~~~java
@Test
void recordsAllEventsFromConcurrentCallers() throws Exception {
    int workers = 8;
    int eventsPerWorker = 1_000;

    InMemoryAuditCollector collector = new InMemoryAuditCollector();
    ExecutorService executor = Executors.newFixedThreadPool(workers);
    CountDownLatch start = new CountDownLatch(1);

    try {
        List<Future<?>> tasks = new ArrayList<>();
        for (int worker = 0; worker < workers; worker++) {
            int workerId = worker;
            tasks.add(executor.submit(() -> {
                start.await();
                for (int i = 0; i < eventsPerWorker; i++) {
                    collector.add(new AuditRecord(workerId, i));
                }
                return null;
            }));
        }

        start.countDown();
        for (Future<?> task : tasks) {
            task.get();
        }

        assertEquals(workers * eventsPerWorker, collector.snapshot().size());
    } finally {
        executor.shutdownNow();
    }
}
~~~

This test generates repeatable concurrent load and verifies no events are lost. For Spring Batch components, add `Step` integration tests running multiple chunks/partitions and asserting final data invariants.

Do not rely solely on execution timing or `Thread.sleep()` to provoke races. Use latches/barriers to synchronize start times and force threads through the critical code paths simultaneously.

## 23. Testing Transactions and Restarts Under Concurrency

Verify thread safety alongside transaction behavior:

- Does a chunk rollback skew in-memory counters?
- Can two partitions insert duplicate business keys?
- Does a restart re-read uncommitted items without creating duplicates?
- Can checkpoints advance past committed data?
- Do listeners record duplicate audit entries on retry?
- Can a resource be closed while another worker is still using it?

For databases, run integration tests against the target database engine whenever logic depends on locking or isolation. H2 may not reproduce deadlock or concurrency behaviors seen in PostgreSQL, MySQL, Oracle, or SQL Server.

Restart tests should preserve `JobRepository` and the business database between the initial run and the restart. Inject a deliberate failure after several chunks commit, restart with the same identifying `JobParameters`, and reconcile the final set of business keys for missing or duplicate records.

## 24. Logging and Metrics in Parallel Processing

When multiple threads execute the same `Step`, logs interleave. Log tracing identifiers:

- `JobExecution` ID.
- `StepExecution` ID.
- Partition name or worker ID.
- Item business key.
- Thread name when analyzing concurrency.
- Retry attempt or error category.

Never use thread names as business identifiers because thread pools reuse threads and names vary across runs.

Metrics like processed counts, failures, and latencies need thread-safe collectors. Distinguish in-memory metrics from `StepExecution` counters and truly committed records. When chunks roll back or retry, one processor call does not mean an item was committed.

## 25. Common Mistakes

**Assuming Spring automatically synchronizes singleton beans:** singleton scope controls only instance count, not mutable field safety.

**Assuming @StepScope means thread-safe:** multiple threads in the same `StepExecution` can share one target bean.

**Sharing a stateful reader across threads:** read positions, cursors, and checkpoints can race. Use per-partition readers or tested synchronization.

**Using shared mutable HashMap/ArrayList instances:** concurrent updates drop entries or corrupt internal structure. Use immutable state, concurrent collections, or locks.

**Incrementing a counter in a processor and treating it as committed count:** retries and rollbacks cause in-memory counters to diverge from persisted data.

**Holding Connections or Statements in fields:** connections bind to transactions/threads and must not be shared across workers.

**Using overly broad synchronized blocks:** serializes threads and eliminates concurrency gains.

**Spawning manual threads inside processors/writers:** Spring Batch transactions and contexts do not propagate to newly created threads.

**Using ThreadLocal without calling remove():** thread pools retain state from earlier items or `Job`s.

**Assuming processing order is preserved:** parallel outcomes can finish and commit out of read order.

**Updating a shared ExecutionContext key from multiple workers:** checkpoints or metadata can be overwritten. Use isolated contexts and merge afterward.

**Not testing restarts with a synchronized reader:** synchronizing `read()` does not automatically align checkpoints with commit order.

## Conclusion

Thread safety of custom Spring Batch components depends on the state held by each component, its bean scope, and the active concurrency model. Favor stateless readers/processors/writers, immutable dependencies, and isolated resources per `StepExecution` or partition. Remember that `@StepScope` isolates beans only across `StepExecution`s; multiple threads within one `StepExecution` can still invoke the same target. For stateful readers, file writers, listeners, `ExecutionContext`, and mutable caches, define state ownership and synchronize at the right granularity. Transactions bind to the current thread, so never spawn manual threads expecting the chunk transaction to propagate. Test concurrency with latches/barriers, verify final data invariants, rollbacks, and restarts, and choose partitioning whenever datasets divide cleanly to reduce shared state and preserve correctness when scaling in parallel.
