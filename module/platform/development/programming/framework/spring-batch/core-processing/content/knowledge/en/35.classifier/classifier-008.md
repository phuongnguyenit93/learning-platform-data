# Stateful Classifiers

In Spring Batch, a Classifier is typically used to select a matching delegate for each item. For example, a BUY transaction is routed to a buy processor, and a SELL transaction is routed to a sell processor. The simplest implementation is a classifier that only reads input data and returns the corresponding delegate.

However, in some systems, a classifier also holds state: caching routing info, counting classifications, storing per-execution configuration, or applying policies based on the state of a run. In those cases, you must determine the scope of the state, who updates it, whether it is shared across threads, and whether it must be restored on restart.

A stateful classifier is not inherently wrong. Risk arises when state changes classification results depending on call order while Spring Batch may retry items, roll back chunks, execute in parallel, or restart a Step. The design must ensure the same item is routed consistently per business rules, or persist routing decisions durably enough to recover.

## 1. Classifier in Spring Batch

A Classifier is an abstraction that takes an input object and returns a classification result. In Spring, the interface has the general form:

~~~java
public interface Classifier<C, T> {
    T classify(C classifiable);
}
~~~

In Spring Batch, ClassifierCompositeItemProcessor uses a Classifier to pick an ItemProcessor for the current item:

~~~text
ItemReader
    |
    v
Input item
    |
    v
ClassifierCompositeItemProcessor
    |
    v
Classifier.classify(item)
    |
    +---- Route A ----> Processor A
    |
    +---- Route B ----> Processor B
    |
    +---- Route C ----> Processor C
    |
    v
Output item
    |
    v
ItemWriter
~~~

A stateless classifier typically relies only on item properties and immutable configuration:

~~~java
public class PaymentClassifier
        implements Classifier<Payment, ItemProcessor<?, ? extends PaymentResult>> {

    private final ItemProcessor<Payment, PaymentResult> cardProcessor;
    private final ItemProcessor<Payment, PaymentResult> transferProcessor;

    public PaymentClassifier(
            ItemProcessor<Payment, PaymentResult> cardProcessor,
            ItemProcessor<Payment, PaymentResult> transferProcessor) {
        this.cardProcessor = cardProcessor;
        this.transferProcessor = transferProcessor;
    }

    @Override
    public ItemProcessor<?, ? extends PaymentResult> classify(Payment payment) {
        return switch (payment.type()) {
            case CARD -> cardProcessor;
            case TRANSFER -> transferProcessor;
        };
    }
}
~~~

This classifier does not need to remember previous items. For the same Payment with the same type, it always picks the same delegate. This is usually easier to understand, easier to test, and safer during retry/restart.

## 2. What Can State in a Classifier Be?

The word state can refer to several different kinds of data. Distinguish them before deciding how to store and synchronize them:

| State type | Example | Purpose |
|---|---|---|
| Configuration state | Map from transaction type to processor | Decide route from configuration |
| Cache state | Cache routes or policies looked up from an external service | Reduce repeated lookup costs |
| Execution state | Items processed in a StepExecution, partition mode | Reflect progress of a run |
| Metrics state | Number of times the classifier selected each branch | Observe load and routing behavior |
| Business state | Deciding which stage a record has already transitioned through | Represent business state |
| Invocation-order state | Counter incremented on each classify call to pick the next branch | Route based on call order |

Configuration state should generally be immutable after the bean is created. Cache and metrics can change at runtime yet require thread safety. Execution state must be tied to the right JobExecution, StepExecution, or partition. Business state should be managed by a durable business system. Invocation-order state requires the greatest caution because retries, rollbacks, and concurrency can alter call order.

Do not lump all these data types into a single mutable field. Each state needs its own owner, lifecycle, and recovery rules.

## 3. Why Might You Need a Stateful Classifier?

A stateful classifier can be useful in certain scenarios:

- Caching policy lookup results so a configuration service is not called per item.
- Holding a route registry loaded when the Step begins.
- Collecting how many times the classifier picks each delegate for metrics.
- Using StepExecution- or partition-specific information to select handling.
- Holding a stable configuration snapshot for the duration of a run.

For example, the system can load transaction-type mappings and a policy version from the database before the Step runs. The classifier uses that snapshot to route consistently throughout the Step. This state is helpful because items do not need to re-query configuration on every classification.

Conversely, if a classifier increments a counter and alternates between processors A, B, A, B, an item's route depends on how many classifications ran before it. That kind of state is usually unsuitable for business logic requiring accurate restarts and retries.

## 4. Stateful Does Not Mean Arbitrarily Mutable

A component can hold state yet remain safe if the state is immutable after initialization. For example, a route Map built from configuration and frozen:

~~~java
public class PaymentClassifier
        implements Classifier<Payment, ItemProcessor<?, ? extends PaymentResult>> {

    private final Map<PaymentType, ItemProcessor<Payment, PaymentResult>> routes;

    public PaymentClassifier(
            Map<PaymentType, ItemProcessor<Payment, PaymentResult>> routes) {
        this.routes = Map.copyOf(routes);
    }

    @Override
    public ItemProcessor<?, ? extends PaymentResult> classify(Payment payment) {
        ItemProcessor<Payment, PaymentResult> processor =
                routes.get(payment.type());

        if (processor == null) {
            throw new IllegalArgumentException(
                    "Unsupported payment type: " + payment.type());
        }
        return processor;
    }
}
~~~

The classifier holds a Map in a field, yet never modifies the Map after the constructor finishes. If the delegates are also thread-safe, multiple threads can read this configuration concurrently.

Map.copyOf protects the map structure from modification through the returned reference. It does not automatically make the processor objects inside immutable or thread-safe. Evaluate each delegate separately.

## 5. Example of Cache State in a Classifier

Suppose routing depends on a policy looked up by tenant. If every item calls PolicyService, the Job could issue many redundant queries. A cache can store looked-up policies:

~~~java
public class TenantClassifier
        implements Classifier<Payment, ItemProcessor<?, ? extends PaymentResult>> {

    private final PolicyService policyService;
    private final Map<PaymentType, ItemProcessor<Payment, PaymentResult>> routes;
    private final ConcurrentMap<String, PaymentType> tenantPolicyCache =
            new ConcurrentHashMap<>();

    public TenantClassifier(
            PolicyService policyService,
            Map<PaymentType, ItemProcessor<Payment, PaymentResult>> routes) {
        this.policyService = policyService;
        this.routes = Map.copyOf(routes);
    }

    @Override
    public ItemProcessor<?, ? extends PaymentResult> classify(Payment payment) {
        PaymentType selectedType = tenantPolicyCache.computeIfAbsent(
                payment.tenantId(),
                policyService::findPaymentType);

        ItemProcessor<Payment, PaymentResult> processor = routes.get(selectedType);
        if (processor == null) {
            throw new IllegalStateException(
                    "No processor configured for " + selectedType);
        }
        return processor;
    }
}
~~~

This example illustrates a per-tenant cache. Before using it in production, decide:

- Can the policy change while the Job is running?
- Should the cache live for one StepExecution, one JobExecution, or the whole application?
- Does the cache need expiration or version-based refresh?
- If a lookup fails transiently, can it be retried?
- If multiple threads look up the same tenant simultaneously, is a single load acceptable or is another mechanism needed?

ConcurrentHashMap supports concurrent access on the map. computeIfAbsent computes and inserts a value by key in a coordinated manner within the map. However, the mapping function should not have hard-to-repeat side effects and must not recursively call back into the same map. Also note exceptions: if the lookup throws an error, no value is cached and subsequent calls can try again.

Caching is only appropriate when policies are allowed to be reused over a defined period. If policies change between Jobs, pin the policy version in JobParameters or ExecutionContext so all items of the same execution use the same snapshot.

## 6. Metrics State: Counting Classifications

A classifier can keep technical counters to track how many times each branch is chosen:

~~~java
public class CountingPaymentClassifier
        implements Classifier<Payment, ItemProcessor<?, ? extends PaymentResult>> {

    private final PaymentClassifier delegate;
    private final ConcurrentMap<PaymentType, LongAdder> counts =
            new ConcurrentHashMap<>();

    public CountingPaymentClassifier(PaymentClassifier delegate) {
        this.delegate = delegate;
    }

    @Override
    public ItemProcessor<?, ? extends PaymentResult> classify(Payment payment) {
        counts.computeIfAbsent(payment.type(), key -> new LongAdder()).increment();
        return delegate.classify(payment);
    }

    public long countFor(PaymentType type) {
        LongAdder count = counts.get(type);
        return count == null ? 0L : count.sum();
    }
}
~~~

LongAdder fits counters with frequent concurrent updates. It reduces contention compared to a single AtomicLong under some multi-threaded workloads. The value of sum() is the number of recorded classify calls, not necessarily the number of committed items.

An item can be classified multiple times on retry or when the framework isolates a failing item. A chunk can roll back after the classifier has incremented the counter. Therefore, do not use this counter as the count of successfully written business records. To count committed items, obtain counts from the database, StepExecution counters, or an audit mechanism tied to transaction commits.

## 7. What Risks Does Invocation-Order State Carry?

The following example uses a counter to alternate routes:

~~~java
public class RoundRobinClassifier
        implements Classifier<Payment, ItemProcessor<?, ? extends PaymentResult>> {

    private final AtomicInteger next = new AtomicInteger();
    private final List<ItemProcessor<Payment, PaymentResult>> processors;

    public RoundRobinClassifier(
            List<ItemProcessor<Payment, PaymentResult>> processors) {
        this.processors = List.copyOf(processors);
    }

    @Override
    public ItemProcessor<?, ? extends PaymentResult> classify(Payment payment) {
        int index = Math.floorMod(next.getAndIncrement(), processors.size());
        return processors.get(index);
    }
}
~~~

AtomicInteger protects the counter increment when multiple threads call concurrently. However, it only solves the race condition on the counter; it does not guarantee stable routing per item.

Suppose on the first pass:

~~~text
classify item A -> Processor 0
classify item B -> Processor 1
classify item C -> Processor 0
~~~

If item B is retried, the next call might get Processor 1 or Processor 0 depending on other items that called classify in between. When running in parallel, the order in which counter values are obtained also depends on thread scheduling. After a restart, the counter may be reinitialized from the start.

If delegates A and B have different business rules, the exact same item could be processed in two different ways. That is a data risk, not just a metrics inaccuracy.

Round-robin should only be used if the goal is load distribution with no business significance, delegates have equivalent behavior, and the system accepts distribution order changing on retry/restart. If stable distribution is required, use a deterministic routing key instead of an invocation counter.

## 8. Using a Stable Routing Key Instead of a Counter

If the goal is sharding items across multiple processors or workers stably, you can compute the route from an immutable key on the item:

~~~java
public class StableShardClassifier
        implements Classifier<Payment, ItemProcessor<?, ? extends PaymentResult>> {

    private final List<ItemProcessor<Payment, PaymentResult>> processors;

    public StableShardClassifier(
            List<ItemProcessor<Payment, PaymentResult>> processors) {
        if (processors.isEmpty()) {
            throw new IllegalArgumentException("At least one processor is required");
        }
        this.processors = List.copyOf(processors);
    }

    @Override
    public ItemProcessor<?, ? extends PaymentResult> classify(Payment payment) {
        int index = Math.floorMod(
                payment.paymentId().hashCode(),
                processors.size());
        return processors.get(index);
    }
}
~~~

With the same paymentId and same processor list, the route is always identical. Retries do not automatically move an item to another branch.

If the processor list changes size or order, hash modulo can produce different routes. When routes must stay stable across deployment versions, version the algorithm, keep shard counts fixed, or use consistent hashing with configuration pinned per JobExecution.

For business logic, usually route by type, tenant, region, or an explicit business key rather than arbitrary distribution by counter.

## 9. State per JobExecution and StepExecution

A classifier may need data that varies per run, such as:

- Policy version chosen when launching the Job.
- Region assigned to a worker partition.
- Step-specific processing threshold.
- Route mapping determined from input parameters.

Do not store these values in fields of a singleton shared across multiple JobExecutions. Use JobParameters, JobExecutionContext, or StepExecutionContext with the appropriate scope.

| State source | Scope | When appropriate |
|---|---|---|
| JobParameters | JobExecution input | Files, business date, policy version |
| JobExecutionContext | One JobExecution, shareable across Steps | Metadata produced during the Job |
| StepExecutionContext | One StepExecution | Step/partition-specific checkpoints or config |
| @JobScope bean | One JobExecution | Dependencies needing Job-scoped state |
| @StepScope bean | One StepExecution | Dependencies needing Step-scoped state |
| Immutable singleton | Application context | Shared unchanging configuration |

Scope controls bean lifecycle; ExecutionContext persists data needed for recovery. The two concepts are related yet do not replace each other.

## 10. Using @StepScope for a Classifier

If a classifier needs Step-specific configuration, you can declare the bean with @StepScope:

~~~java
@Bean
@StepScope
PaymentClassifier paymentClassifier(
        @Value("#{stepExecutionContext['routeMode']}") String routeMode,
        CardPaymentProcessor cardProcessor,
        TransferPaymentProcessor transferProcessor) {

    return new PaymentClassifier(routeMode, cardProcessor, transferProcessor);
}
~~~

This example assumes PaymentClassifier is designed to accept routeMode via constructor and only use that value within the StepExecution scope. The classifier can choose how to route based on routeMode.

@StepScope gives each StepExecution its own target bean. It does not automatically make the target thread-safe if multiple threads within the same StepExecution invoke the classifier concurrently. If the classifier has mutable fields updated inside classify(), synchronize them or redesign so state is not dangerously shared.

If a value is needed across the entire Job, @JobScope may fit better. Still, a JobScope bean can be accessed concurrently by Steps running in parallel within the same JobExecution; scope is not a synchronization lock.

## 11. Persisting Restartable State with ExecutionContext

The Classifier interface only has the classify() method. It does not itself provide open/update/close callbacks, and Spring Batch does not automatically persist classifier fields into the JobRepository.

If classifier state must be restored on restart, integrate lifecycle or persist state through a Step-managed component. One way is having the classifier implement ItemStream and registering that stream with the Step:

~~~java
public class StatefulClassifier
        implements Classifier<Payment, ItemProcessor<?, ? extends PaymentResult>>,
                   ItemStream {

    private static final String ROUTE_COUNT_KEY =
            "paymentClassifier.routeCount";

    private final ItemProcessor<Payment, PaymentResult> primary;
    private final ItemProcessor<Payment, PaymentResult> secondary;
    private long routeCount;

    public StatefulClassifier(
            ItemProcessor<Payment, PaymentResult> primary,
            ItemProcessor<Payment, PaymentResult> secondary) {
        this.primary = primary;
        this.secondary = secondary;
    }

    @Override
    public void open(ExecutionContext executionContext) {
        routeCount = executionContext.getLong(ROUTE_COUNT_KEY, 0L);
    }

    @Override
    public ItemProcessor<?, ? extends PaymentResult> classify(Payment payment) {
        boolean usePrimary = (routeCount++ % 2L) == 0L;
        return usePrimary ? primary : secondary;
    }

    @Override
    public void update(ExecutionContext executionContext) {
        executionContext.putLong(ROUTE_COUNT_KEY, routeCount);
    }

    @Override
    public void close() {
        // No resources to release in this example.
    }
}
~~~

Register the composite as the processor and the classifier as a Step stream:

~~~java
@Bean
Step paymentStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Payment> reader,
        ClassifierCompositeItemProcessor<Payment, PaymentResult> processor,
        StatefulClassifier classifier,
        ItemWriter<PaymentResult> writer) {

    return new StepBuilder("paymentStep", jobRepository)
            .<Payment, PaymentResult>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .stream(classifier)
            .build();
}
~~~

Registering the stream lets the Step call the ItemStream lifecycle to open, update, and close state. Simply implementing ItemStream without registering the component with the Step is not enough to ensure callbacks are invoked.

The example above illustrates saving/restoring state, yet an alternating counter still has issues under retry and concurrency. update() writes state at Step checkpoints; it does not turn each classify call into a route decision committed atomically with the item. If a chunk rolls back or an item is retried, routeCount may have already advanced in memory. In a multi-threaded Step, multiple threads can also update the counter concurrently.

Therefore, do not use this alternating pattern for business decisions requiring determinism. For critical state, persist route decisions by business key in the database or determine routes from immutable data.

## 12. Understanding Update and Rollback Order Properly

ExecutionContext and chunk transactions are managed by Spring Batch according to the Step lifecycle. ItemStream.update() is called at stream state-update points, typically during chunk processing before the transaction completes.

Do not treat incrementing a field in the classifier as a committed change. A chunk can:

1. Invoke the classifier for several items.
2. Increment in-memory state.
3. Invoke the writer.
4. Encounter an error and roll back the transaction.
5. Retry the item or chunk.

In-memory state does not automatically roll back with the database transaction. If the classifier incremented a counter, after rollback the counter may stay advanced. This causes the retry's route to differ from the original route.

To make state reflect committed data, use an appropriate transaction-aware mechanism or store state by business key inside the same transaction as the output. AtomicLong or synchronized alone cannot create consistency with a database transaction.

## 13. Thread Safety of a Stateful Classifier

A singleton classifier can be used concurrently by multiple Steps or JobExecutions. A @StepScope classifier can be called by multiple threads within the same StepExecution. Therefore, identify who accesses every field.

Examples of risks:

- A mutable HashMap updated by multiple threads.
- Non-atomic increments on a long counter.
- A currentItem field overwritten between two calls.
- A cache refreshed while another thread is reading.
- The classifier closing resources while another thread is classifying.

If state is purely a cache, use concurrent structures or immutable snapshots. If state is per-StepExecution data, prefer a Step-scoped instance and avoid sharing with other workers. If state is business state, use a database or system with concurrency control.

AtomicInteger and AtomicLong only protect single updates. They do not make multiple fields update as a transaction, do not handle rollbacks, and do not guarantee stable per-item routes.

## 14. Cache Invalidation and Policy Snapshots

A cache in a classifier can become a source of bugs if routing data changes while a Job is running.

For example, tenant A initially routes to Processor X. While the Job runs, policy is updated to route to Processor Y. If the cache lacks versioning rules, some items may go to X and others to Y depending on when the cache refreshes.

Strategies:

- **Per-execution snapshot:** load all mappings when the Step starts and use them immutably until the Step finishes.
- **Versioned policy:** JobParameters stores policyVersion; every lookup uses that exact version.
- **TTL cache:** accept that policy can change after an interval; only use when business rules allow.
- **Explicit invalidation:** update the cache on policy-change events while defining how in-flight items are handled.
- **Per-partition cache:** each worker has its own snapshot if partitions require independent policies.

For batches requiring reproducible results, snapshot/versioned policies are usually easier to control than TTL caches. On restart, reload the exact policy version used originally rather than defaulting to the latest policy.

## 15. State in Partitioning

Partitioning is often a suitable way to isolate state per worker. The Manager Step creates separate ExecutionContexts per partition; each worker has its own StepExecution and can have its own @StepScope classifier.

Example partitioner providing route mode:

~~~java
ExecutionContext context = new ExecutionContext();
context.putString("routeMode", "REGION_A");
partitions.put("regionA", context);
~~~

Worker classifier receiving the mode:

~~~java
@Bean
@StepScope
RegionClassifier regionClassifier(
        @Value("#{stepExecutionContext['routeMode']}") String routeMode,
        RegionAProcessor regionAProcessor,
        RegionBProcessor regionBProcessor) {

    return new RegionClassifier(routeMode, regionAProcessor, regionBProcessor);
}
~~~

Each worker has its own context, so partition A's routeMode does not overwrite partition B. This is per-partition configuration state, not a global counter distributing items.

If a worker Step runs multithreaded, the worker's classifier can still be invoked concurrently. Keep the classifier stateless after construction completes or protect necessary mutable state.

## 16. Distinguishing Classifier State from Processor State

A classifier only decides which delegate receives an item. The processor executes business logic. Do not let the classifier accumulate logic that belongs in the processor.

| Responsibility | Appropriate component |
|---|---|
| Choose delegate by type | Classifier |
| Validate amount | ItemProcessor |
| Calculate fees | ItemProcessor or domain service |
| Call policy to determine route | Classifier or routing service |
| Save checkpoints | ItemStream/ExecutionContext |
| Persist long-lived business state | Repository/domain service |
| Write output | ItemWriter |
| Count committed items | StepExecution metadata or database |

If the classifier must mutate items, write to the database, or call APIs with side effects just to choose a branch, you may need to extract an enrichment step or routing service. The classifier should return the processing choice; the delegate is responsible for executing the branch rules.

## 17. Error Handling in a Classifier

A classifier can encounter:

- Items missing a route key.
- Unsupported route keys.
- Cache lookup failures.
- Policy service timeouts.
- Configured mappings missing a delegate.
- Errors when reading or restoring state.

Distinguish data errors from infrastructure errors:

| Error | Potentially appropriate handling |
|---|---|
| Unsupported type | Fail fast or fallback with audit |
| Required route field missing | Validation failure; skip only if business rules allow |
| Transient policy service timeout | Bounded retry if lookup is safe |
| Missing delegate in configuration | Configuration error, usually fail the Step |
| Cache contains invalid policy version | Stop and report error, avoid arbitrary branch selection |
| State checkpoint unreadable | Do not proceed with an unknown route |

Do not return null from a classifier if the composite requires a delegate. A null delegate can cause errors when the composite invokes the processor. To filter items, the selected delegate can return null per the ItemProcessor contract; that is a different decision from the classifier failing to find a route.

## 18. Skip and Retry with a Stateful Classifier

A classifier is invoked during the process stage when used inside ClassifierCompositeItemProcessor. Exceptions from the classifier or delegates can be affected by the Step's skip/retry policies.

Retries can cause the classifier to be called again for the same item. Therefore:

- classify should be deterministic and not depend on an invocation counter if the route has business meaning.
- Cache lookups should be safe to re-execute.
- Do not write non-idempotent side effects in classify.
- If routes must be pinned, store routes by business key or compute from immutable data.
- Exceptions distinguishing transient vs permanent errors should be distinct.

Configuration example:

~~~java
return new StepBuilder("paymentStep", jobRepository)
        .<Payment, PaymentResult>chunk(100, transactionManager)
        .reader(reader)
        .processor(classifierComposite)
        .writer(writer)
        .faultTolerant()
        .retry(TemporaryPolicyLookupException.class)
        .retryLimit(3)
        .skip(UnsupportedPaymentTypeException.class)
        .skipLimit(20)
        .build();
~~~

Only skip unsupported payment types if the business contract permits that record type. If the classifier fails to find a delegate due to a bad deployment config, do not turn a configuration error into per-item skips.

## 19. Testing a Stateful Classifier

Unit tests must verify both routing results and how state changes:

- Routes are selected properly for valid items.
- State initializes properly.
- Cache hits do not unnecessarily call the service again.
- Cache misses load and store results accurately.
- Unknown routes have explicit behavior.
- Concurrent classify calls do not corrupt cache structures or counters.
- State is not shared across two StepExecutions when isolation is required.

Example testing cache:

~~~java
@Test
void loadsTenantPolicyOnlyOnce() {
    PolicyService policyService = mock(PolicyService.class);
    when(policyService.findPaymentType("TENANT-1"))
            .thenReturn(PaymentType.CARD);

    TenantClassifier classifier =
            new TenantClassifier(policyService, configuredRoutes());

    classifier.classify(paymentFor("TENANT-1", "P-1"));
    classifier.classify(paymentFor("TENANT-1", "P-2"));

    verify(policyService, times(1)).findPaymentType("TENANT-1");
}
~~~

This test verifies caching within a single classifier instance. Add tests for policy version changes, lookup failures, and multiple threads accessing the same tenant simultaneously.

## 20. Concurrency Testing

Sequential tests are insufficient to uncover race conditions. Use ExecutorService with CountDownLatch or CyclicBarrier so multiple threads start classifying nearly simultaneously.

For caches, verify:

- No entries are lost.
- No wrong delegates are returned.
- Policy service call counts match the chosen cache semantics.
- No exceptions from concurrent collection modification.

For counters, verify total invocation counts after all Futures complete. However, counter totals only prove arithmetic accuracy, not stable per-item routing.

For business routing, verify that classifying the same item multiple times always returns the same delegate, even while other items are classified concurrently.

## 21. Testing Restart and Checkpoints

If a classifier implements ItemStream or uses ExecutionContext, test across two JobExecutions with a persistent JobRepository:

1. Launch the Job with fixed identifying parameters.
2. Allow some chunks to commit, then induce a controlled failure.
3. Inspect the persisted checkpoint.
4. Restart with the same JobInstance and same input.
5. Verify the classifier state reopens properly.
6. Verify the same business items still route consistently.
7. Reconcile output data to detect missing items or duplicates.

Tests should cover chunk rollback after the classifier has already been called. If in-memory state advances while the transaction rolls back, verify whether a retry can route differently. For business routes, differing results usually signal that the design needs changing.

Do not merely assert Job COMPLETED. Compare sets of business keys and results per route against expected outcomes.

## 22. Logging and Metrics

When a classifier holds a cache or state, logs should help answer:

- Which key routed the item?
- Which delegate was selected?
- Which policy version was used?
- Did the result come from cache or a lookup?
- Did the classifier encounter an unknown route?
- How many times was the item retried?

Avoid logging raw payloads or sensitive data unnecessarily. You can log business keys, route keys, policy versions, JobExecution ID, and StepExecution ID.

Metrics should distinguish:

- Number of classify calls.
- Number of cache hits/misses.
- Number of failed policy lookups.
- Number of items processed by processors.
- Number of items committed by writers.

These numbers are not synonymous. An invocation can be retried; an output can roll back. Use StepExecution counters or committed data to report business results.

## 23. When Should You Avoid State in a Classifier?

Prefer a stateless classifier when:

- Routes can be derived directly from the item.
- Retries/restarts must give the same item the same result.
- The Step runs in parallel or uses partitioning.
- State only serves counting and separate metrics can be used.
- Policies can be placed in immutable configuration.
- Stable routing keys can be used instead of counters.

If state is required, keep it minimal and clarify:

1. Does state belong to the application, JobExecution, StepExecution, or partition?
2. Who owns and updates the state?
3. Do multiple threads read/write it?
4. Must state be restored on restart?
5. Does chunk rollback need to undo state?
6. Must retrying the same item pick the same route?
7. How are policy changes across executions handled?

If you cannot answer these questions, the state may be placed at the wrong layer.

## 24. Common Pitfalls

**Using invocation counters to decide business routes:** retries and concurrency can send the same item to a different delegate. Use stable keys or persist decisions by business key.

**Assuming AtomicInteger solves everything:** atomics only protect counter updates; they do not handle rollbacks, restarts, or cross-field consistency.

**Holding execution state in singletons:** multiple JobExecutions can overwrite each other's data. Use JobParameters, ExecutionContext, or properly scoped beans.

**Assuming @StepScope is automatically thread-safe:** multiple threads inside the same StepExecution can still invoke the same target bean.

**Not persisting restartable state:** in-memory fields are lost when the process stops. Use ItemStream/ExecutionContext or durable storage.

**Implementing ItemStream yet forgetting to register:** the Step will not invoke lifecycles if the stream is not registered or discovered through components.

**Treating update() as a per-classify commit:** update is a stream state-saving callback in the Step lifecycle, not something that makes every routing decision its own transaction.

**Caching policies without versions:** a single Job can use multiple policies if the cache refreshes mid-run. Pin versions or snapshot per execution.

**Using non-thread-safe mutable caches:** multiple threads can corrupt state or read inconsistent values. Use immutable snapshots or concurrent structures.

**Using metrics counters as committed item counts:** retries and rollbacks cause classify counts to differ from successfully written items.

**Returning null when no delegate is found:** the composite can fail when invoking the processor. Fail fast or return an intentional fallback.

**Skipping restart tests:** a classifier that works on the first run can route differently after restarting because state was reset or policies changed.

## Conclusion

A stateful classifier can hold configuration, caches, metrics, or execution-scoped state to support routing. Distinguish immutable state from mutable state, technical state from business state, and application-level state from Job/Step/partition-level state. Classifiers relying on call order or counters to switch delegates are prone to bugs under retry, rollback, concurrency, and restart; AtomicInteger only protects concurrent increments rather than guaranteeing an item always takes the same route. Prefer deterministic routing from items or stable routing keys. If caching is needed, use thread-safe structures and pin policy versions; if state must be recovered, integrate ItemStream/ExecutionContext and register the lifecycle with the Step. Test caching, concurrency, rollback, and restart to ensure state does not alter business results unintentionally.
