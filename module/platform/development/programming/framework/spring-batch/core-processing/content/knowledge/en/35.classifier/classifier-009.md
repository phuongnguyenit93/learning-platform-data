# Classifier and Deterministic Routing

In Spring Batch, a Classifier is an abstraction used to select a result based on an input object. In batch processing, that result is typically an ItemWriter, ItemProcessor, or another processing strategy. For example, each Order can be sent to a writer based on order type, each event can be processed by subtype, or each record can be routed by tenant.

Deterministic routing means the same item, under the same rule set and same configuration version, always goes to the same route. This stability is especially important when chunks are retried or Jobs are restarted. If a routing decision changes between runs, a record could be written to multiple places, missed, or no longer match checkpoints and audit metadata.

A classifier should focus on making a pure, explicit, and testable decision. Side effects such as writing to a database, writing files, sending messages, or calling HTTP belong to the selected component. For reliable routing, define the route key, default rules, invalid-value handling, configuration versioning, and how to preserve the same decision across retries/restarts.

## 1. What Is a Classifier?

A Classifier is a strategy that takes a value of type C and returns a result of type T. In Spring, this abstraction is represented by an interface with a single classify method:

~~~java
public interface Classifier<C, T> {
    T classify(C classifiable);
}
~~~

The two generic types mean:

- C is the input type the classifier inspects.
- T is the result type selected from that input.

Example of a classifier taking an Order and returning a route name:

~~~java
Classifier<Order, String> orderRoute =
        order -> order.isPriority()
                ? "PRIORITY"
                : "STANDARD";
~~~

A classifier can return a writer, processor, handler, enum, strategy, or configuration object. It does not have to return a String. Choosing the result type depends on the component using the classifier.

In Spring Batch, a familiar use case is ClassifierCompositeItemWriter: the classifier takes each item and returns the appropriate ItemWriter. Some Spring Batch versions also provide a classifier-based composite processor to select an ItemProcessor. Verify the classes and APIs present in your project's dependency version before using them.

## 2. Routing and Item Processing Are Two Separate Responsibilities

Routing answers where an item will be processed or by which strategy. The selected component performs the actual work.

~~~text
Input item
    |
    v
Normalize / derive route key
    |
    v
Classifier
    |
    +--> Route A --> Writer A
    |
    +--> Route B --> Writer B
    |
    +--> Route C --> Writer C
~~~

Examples:
- A PRIORITY-channel Order is written to the priority file.
- A STANDARD-channel Order is written to the standard table.
- A PaymentReceived event is processed by the payment processor.
- A record belonging to a specific tenant is written to the corresponding partition.

If a classifier both decides the route and writes data, routing logic becomes hard to test and can cause side effects even when a chunk rolls back. Keeping the classifier focused on decisions makes observing, updating rules, and testing easier.

## 3. What Does Deterministic Routing Mean?

A routing function is deterministic when the same input and same rule set always return the same result.

Example:

~~~java
OrderRoute classify(Order order) {
    return order.getAmount().compareTo(new BigDecimal("10000")) >= 0
            ? OrderRoute.HIGH_VALUE
            : OrderRoute.STANDARD;
}
~~~

If the item's amount does not change and the threshold stays fixed, the route is always identical.

Conversely, the following rules can be non-deterministic:
- Selecting a writer randomly.
- Using the current timestamp to decide the route.
- Calling an external service whose response changes between two calls.
- Relying on an incrementing counter in a singleton classifier.
- Relying on configuration that can be updated while the Job is running.
- Relying on item order if that order is not guaranteed across restarts.

Deterministic routing does not mean every Job must always use the same route forever. A new JobInstance can use a new rule set. The requirement is that within one logical unit of work, decisions must remain consistent with the chosen contract.

## 4. Why Is Determinism Important in Spring Batch?

Spring Batch supports item/chunk-level retries and restarts after failed executions. An item can be reprocessed after a rollback or after reopening a JobInstance.

Suppose on the first pass item 100 is routed to writer A, writer A writes a side effect, and then another writer fails. On retry, the classifier picks writer B because external configuration changed. The outcome could be:
- Item 100 exists in both A and B.
- Item 100 exists only in A while metadata claims route B.
- Audit records log a different route than where data was actually stored.
- Restart cannot resume the output matching the old checkpoint.

Therefore, the classifier must produce stable results across retries and restarts. If routing depends on mutable rules, version them or pin the rules per JobInstance.

## 5. Choosing a Stable Route Key

A good route key should be based on stable business data with clear meaning.

Examples:
- Order channel.
- Transaction type.
- Tenant ID.
- Normalized country code.
- Event type.
- Product category.
- Business date or batch ID.
- A predetermined partition key.

Avoid using unstable attributes such as:
- Timestamp when the classifier is called.
- A random UUID generated on every classify call.
- Item sequence number within a thread if order is not fixed.
- Hash code of a mutable object.
- External state that can change between retries.

Example enum-based route:

~~~java
public enum OrderRoute {
    PRIORITY,
    STANDARD,
    INTERNATIONAL,
    REJECTED
}
~~~

An enum constrains the route set and clarifies the contract. When a route key is built from multiple fields, normalize them in a separate step before the classifier uses it.

## 6. Normalizing Data Before Classification

Input data can differ in casing, whitespace, country codes, or enum representations. If the classifier uses raw values directly, the same business meaning can be split across multiple routes.

Example normalizing a country code:

~~~java
String normalizeCountry(String value) {
    if (value == null || value.isBlank()) {
        return "UNKNOWN";
    }

    return value.trim().toUpperCase(Locale.ROOT);
}
~~~

Use Locale.ROOT for normalizing technical codes so results do not depend on the host machine's locale. For data with special business rules, apply proper canonicalization rather than only trim/uppercase.

Normalization can be done in an ItemProcessor or a dedicated mapper:

~~~java
public record RoutedOrder(
        Order order,
        OrderRoute route) {
}

@Bean
ItemProcessor<Order, RoutedOrder> prepareRoute() {
    return order -> {
        String channel = normalizeChannel(order.getChannel());
        OrderRoute route = switch (channel) {
            case "P" -> OrderRoute.PRIORITY;
            case "I" -> OrderRoute.INTERNATIONAL;
            case "S" -> OrderRoute.STANDARD;
            default -> OrderRoute.REJECTED;
        };

        return new RoutedOrder(order, route);
    };
}
~~~

Once the route is determined and stored in RoutedOrder, the writer can use that result instead of repeating normalization logic. If the processor can re-run on retry, the data and rules used to compute the route must still be stable.

## 7. Writing a Pure, Side-Effect-Free Classifier

A classifier should behave like a decision function:
- Accept an item or route key.
- Read the necessary fields.
- Apply defined rules.
- Return a route or strategy.
- Never write data, call APIs, or mutate the item.

Example:

~~~java
public class OrderClassifier
        implements Classifier<Order, OrderRoute> {

    @Override
    public OrderRoute classify(Order order) {
        if (order == null) {
            throw new IllegalArgumentException("Order must not be null");
        }

        if (order.isRejected()) {
            return OrderRoute.REJECTED;
        }

        if (order.isInternational()) {
            return OrderRoute.INTERNATIONAL;
        }

        if (order.isPriority()) {
            return OrderRoute.PRIORITY;
        }

        return OrderRoute.STANDARD;
    }
}
~~~

The logic above has a clear priority order. If an Order is both rejected and international, the rejected branch wins. This precedence rule is part of the contract and must be tested.

Do not let the classifier increment a counter to alternate between writers A/B if routes must be stable per item. If you need even load distribution, use a deterministic distribution algorithm based on a stable key or a load-balancing mechanism designed specifically for that purpose.

## 8. A Classifier Must Handle All Cases Completely

A classifier should have a defined outcome for every valid input. When an undefined route occurs, an explicit policy is required.

Common options:
- Return a default route.
- Return a reject/quarantine route.
- Throw an exception to fail the Step.
- Record classification errors in a dedicated control stream.

Example:

~~~java
OrderRoute classify(Order order) {
    if (order.getChannel() == null) {
        return OrderRoute.REJECTED;
    }

    return switch (order.getChannel()) {
        case PRIORITY -> OrderRoute.PRIORITY;
        case STANDARD -> OrderRoute.STANDARD;
        case INTERNATIONAL -> OrderRoute.INTERNATIONAL;
    };
}
~~~

If the route key is a String, avoid ad-hoc null or string comparisons scattered in multiple places. Normalizing and parsing into an enum upfront makes branches clearer.

Do not return null unless the classifier's consumer specifies what null means. A null result can trigger failures deeper inside the composite writer and be harder to diagnose.

## 9. Handling Unsupported Routes

When a new route value appears, the system needs predictable behavior. For example, upstream sends channel "EXPRESS" while the application currently supports only PRIORITY and STANDARD.

Two common design options exist.

**Explicit rejection:**

~~~java
OrderRoute classify(String channel) {
    return switch (channel) {
        case "P" -> OrderRoute.PRIORITY;
        case "S" -> OrderRoute.STANDARD;
        default -> throw new UnsupportedOperationException(
                "Unsupported channel: " + channel);
    };
}
~~~

This fits when a new route represents a configuration error or contract change requiring the Job to stop.

**Routing to quarantine:**

~~~java
OrderRoute classify(String channel) {
    return switch (channel) {
        case "P" -> OrderRoute.PRIORITY;
        case "S" -> OrderRoute.STANDARD;
        default -> OrderRoute.REJECTED;
    };
}
~~~

This fits when business rules allow continuing to process other records and storing unrecognized records for investigation. Log rejection reasons and quarantine counts so the Job does not mask data quality issues.

Do not use a default route silently if that route could send data to the wrong system. A default must be an intentional business decision.

## 10. Routing with ClassifierCompositeItemWriter

An application can use ClassifierCompositeItemWriter to select a writer per item. The classifier receives the item and returns the matching delegate writer.

Example:

~~~java
@Bean
ClassifierCompositeItemWriter<Order> orderWriterRouter(
        @Qualifier("priorityWriter") ItemWriter<Order> priorityWriter,
        @Qualifier("standardWriter") ItemWriter<Order> standardWriter) {

    ClassifierCompositeItemWriter<Order> composite =
            new ClassifierCompositeItemWriter<>();

    composite.setClassifier(order ->
            order.isPriority()
                    ? priorityWriter
                    : standardWriter);

    return composite;
}
~~~

Step declaration:

~~~java
@Bean
Step routeOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ClassifierCompositeItemWriter<Order> orderWriterRouter) {

    return new StepBuilder("routeOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .writer(orderWriterRouter)
            .build();
}
~~~

The composite is responsible for invoking the selected writer. The delegate performs the write. If a delegate is an ItemStream, ensure the delegate's lifecycle is registered with the Step using the corresponding stream mechanism; do not assume every wrapper automatically forwards open, update, and close.

## 11. Distinguishing Routing from Broadcasting

ClassifierCompositeItemWriter selects one delegate per item. CompositeItemWriter typically sends the same chunk to multiple delegates in configured order.

| Requirement | Appropriate mechanism |
|---|---|
| Route A items go to writer A, route B items go to writer B | ClassifierCompositeItemWriter |
| Every item writes to both database and audit file | CompositeItemWriter |
| Route A items write to database and audit, route B only to database | ClassifierCompositeItemWriter selecting a CompositeItemWriter or adapter for route A |
| Different processing by subtype before writing | Classifier combined with processor or writer |
| Split data into workers with independent lifecycles and checkpoints | Partitioning |

Do not use a broadcast composite for single-destination selection, or data may be written to every delegate. Conversely, do not use a classifier when every system must receive the same record.

## 12. Classifying by Multiple Conditions and Precedence

A classifier often has multiple conditions. Check order affects results if an item satisfies multiple conditions.

Example:
1. Records marked invalid always go to the reject route.
2. International records go to the international route.
3. Priority records go to the priority route.
4. Remaining records go to the standard route.

~~~java
OrderRoute classify(Order order) {
    if (!order.isValid()) {
        return OrderRoute.REJECTED;
    }
    if (order.isInternational()) {
        return OrderRoute.INTERNATIONAL;
    }
    if (order.isPriority()) {
        return OrderRoute.PRIORITY;
    }
    return OrderRoute.STANDARD;
}
~~~

Write precedence as explicit rules and test overlapping cases. Do not let if/else order become an accidental detail nobody notices.

If rules grow increasingly complex, extract them into a policy object or versioned rule table. A small classifier calling a policy is easier to read than a lambda containing dozens of conditions.

## 13. Deterministic Routing When Using Hashing

One way to distribute items across a fixed number of routes is hashing a stable key. For example, assigning a customer to one of four buckets:

~~~java
int bucketFor(String customerId, int bucketCount) {
    return Math.floorMod(
            customerId.hashCode(),
            bucketCount);
}
~~~

Conditions for stable results:
- customerId must be stable.
- Strings must be normalized before hashing.
- bucketCount must stay constant within the scope of a JobInstance.
- The hash algorithm must remain unchanged across runs requiring restart.
- Never use hashCode of mutable objects or objects without a stable contract.

Using a different bucketCount changes the route for most keys. Therefore, do not change partition counts when restarting the same JobInstance if outputs or checkpoints depend on the prior routes.

For long-term distribution across node additions/removals, consistent hashing or a persistent mapping table can be considered. Do not roll a complex algorithm if a simple partition assignment table meets requirements.

## 14. Do Not Use Counters or Randomness for Restartable Routing

A counter-based classifier might look like load balancing:

~~~java
AtomicInteger counter = new AtomicInteger();

ItemWriter<Order> classify(Order order) {
    return counter.getAndIncrement() % 2 == 0
            ? writerA
            : writerB;
}
~~~

However, results depend on the order and number of times the classifier is called. When a chunk retries or a Job restarts, the counter can start from a different value; an item can go to a different writer.

Random routing has the same problem. If even distribution is needed while staying deterministic, use a stable key:

~~~java
ItemWriter<Order> classify(Order order) {
    int bucket = Math.floorMod(
            order.getCustomerId().hashCode(), 2);

    return bucket == 0 ? writerA : writerB;
}
~~~

This guarantees the same customer key enters the same bucket when the algorithm and bucket count stay unchanged. Still, hash-based distribution does not guarantee exact load balance. If dynamic load balancing is required, you must explicitly accept non-determinism or persist assignment decisions in a durable registry.

## 15. Versioning Routing Rules

Routing rules can change over time: amount thresholds, country lists, tenant mappings, or partition counts. If a Job restarts with new rules, the same item can switch to another route.

One way to control this is binding the rule version to the JobInstance.

JobParameters example:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("routingRuleVersion", "v3", true)
        .toJobParameters();
~~~

When the JobInstance is created, the version is persisted with identifying parameters. The classifier or policy loader uses that exact version.

Another approach is storing the version in the Job ExecutionContext after Job initialization. On restart, the application checks the existing version and reuses the same rule set.

Do not automatically read "latest configuration" every time the classifier is invoked. If configuration changes between chunks, the same Job could process records under two different rule sets.

## 16. Keeping Configuration Constant on Restart

Restarting the same JobInstance means resuming the same logical unit of work. Factors affecting routing must remain unchanged:

- Route keys and normalization logic.
- Rule precedence.
- Mapping from route to delegate.
- Bucket/partition counts if hashing is used.
- Configuration version.
- Supported tenant or channel lists.
- Semantics of default/reject routes.
- Output schemas and names for each route.

If keeping old configuration is impossible, you need a controlled migration plan. For example, create a new JobInstance to reprocess the entire dataset with the new rules, or store finalized route decisions in a staging table so restarts read them back.

Do not silently change routing rules while an old JobInstance can still be restarted.

## 17. Persisting Resolved Routes When Rules Cannot Be Recomputed

Some route decisions depend on external data or manually approved business decisions. In those cases, keeping only the rule version may not be enough.

You can store routes in a staging table:

~~~text
batch_input
  item_id
  payload
  resolved_route
  routing_rule_version
  job_instance_id
~~~

Processing flow:
1. Prepare input and compute routes.
2. Store the resolved route alongside the item key.
3. The Job processes items from staging.
4. Retries/restarts read back resolved_route.
5. Audits can look up the route and rule version used.

This makes route decisions durable and independent of external services at restart time. Ensure staging data creation and JobInstance are linked consistently so mappings from another batch are never reused accidentally.

## 18. Do Not Let a Classifier Call External Services per Item

If a classifier calls HTTP or a database to look up a route for every item, the Job can suffer:
- High latency.
- Service outages failing the Step.
- Results changing across retries.
- Rate limiting.
- Hard-to-test logic.
- Duplicate requests for the same key.

If mappings are small and stable, load them once when the Job starts and use an immutable map in the Step. If mappings are large, read from a staging table or a versioned cache. If an external service is the authoritative decision source, freeze its result in durable metadata before writers perform side effects.

Do not perform remote lookups from the classifier when the same result can be prepared upfront by a dedicated Step or processor.

## 19. Nulls, Invalid Data, and Fallback Routes

The classifier must explicitly handle:
- Null items.
- Null route keys.
- Empty or whitespace-only route codes.
- Unsupported route codes.
- Missing mappings.
- Unconfigured target delegates.
- Missing or incompatible rule versions.

You can use separate REJECTED or UNKNOWN outcomes:

~~~java
public enum Route {
    ACCEPTED,
    PRIORITY,
    STANDARD,
    REJECTED,
    UNKNOWN
}
~~~

UNKNOWN and REJECTED do not necessarily mean the same thing. REJECTED can be a known business outcome; UNKNOWN can indicate unrecognized configuration or data. Separating the two statuses helps operations investigate the exact cause.

If an unknown route is a critical error, fail the Step rather than silently falling back to a default writer. If business rules allow quarantine, record both the original route key and reason in the reject output.

## 20. Transactions and Route Side Effects

A classifier only picks a delegate; it does not create a distributed transaction. Delegates are invoked during the chunk's write phase, yet rollback capability depends on resources and the transaction manager.

For example:
- Two JDBC delegates using the same transaction manager and transaction-bound DataSource can roll back together.
- One delegate writing a file and one delegate writing to a database do not share an atomic transaction by default.
- A delegate sending HTTP requests or messages may have already produced side effects even if a later delegate fails.
- Two separate databases require dedicated transaction mechanisms if atomicity is required.

If a route has external side effects, consider:
- Idempotency keys per item/business key.
- An outbox table written inside the database transaction.
- Staging outputs and publishing after commit.
- Bounded retries and reconciliation.
- Persisting sent state to avoid duplicate sends.

Do not assume a chunk rollback deletes files or revokes already-succeeded requests.

## 21. Deterministic Routing and Retry

During retries, an item may be invoked multiple times. The classifier must return the same route for that item.

Example routing based on an item field:

~~~java
OrderRoute classify(Order order) {
    return order.getRiskLevel() == RiskLevel.HIGH
            ? OrderRoute.REVIEW
            : OrderRoute.AUTO_PROCESS;
}
~~~

This is deterministic if riskLevel is stable data within the run. If riskLevel is re-queried from a time-varying service, results can differ.

If a processor builds RoutedOrder once and then the writer retries, check whether the framework re-invokes the processor under each fault-tolerance scenario. Do not assume already-routed objects are always preserved across every retry path. A safer approach is basing routes on immutable input or persisting route decisions in durable data when business rules require it.

Delegate writers should also be idempotent if side effects can execute before an exception occurs.

## 22. Deterministic Routing and Restart

When a Job restarts, the classifier may be recreated with the ApplicationContext or in a new process. Therefore, do not rely on in-memory fields to store unique decisions.

Recreate the exact same route from:
- Identifying JobParameters.
- Stable source data.
- Pinned rule version.
- Mappings saved in the Job ExecutionContext or staging.
- Unchanged algorithm and bucket counts.

If output paths or writer state depend on the route, writer names and resource paths must also remain stable. For instance, each route writes a file named by JobInstance ID and route name, rather than generating a new UUID on every launch.

If rules changed and the old version cannot be restored, decide explicitly: continue with persisted routes, start a new JobInstance, or run a migration procedure. Do not pick new rules and continue on top of old checkpoints.

## 23. Routing and Partitioning Are Not the Same

Routing selects a handler/delegate for an item within the same Step. Partitioning creates separate StepExecutions, each worker having its own ExecutionContext and lifecycle.

| Criterion | Classifier routing | Partitioning |
|---|---|---|
| Classification unit | Per item | Data range or partition |
| StepExecution | Typically the same StepExecution | Each worker has its own StepExecution |
| Resource lifecycle | Delegates within the same Step | Workers have independent lifecycles |
| Checkpoint | Delegate state within the Step | State per worker StepExecution |
| Concurrency | Does not spawn parallel workers itself | Can run parallel workers |
| Best fit | Pick writer/processor per item | Split dataset for independent processing |

If you need one writer per item type, a classifier fits. If each tenant needs its own transactions, restarts, concurrency, and resources, partitioning may fit better.

Do not create thousands of writers inside a classifier just to mimic partitioning. Consider route counts, file descriptor limits, connection pools, and lifecycle management.

## 24. Deterministic Routing with Consistent Mapping

With many routes or shards, carefully consider how keys map to targets. A simple modulo:

~~~java
int shard = Math.floorMod(customerId.hashCode(), shardCount);
~~~

is easy to use, yet when shardCount changes, most keys shift shards.

If the system needs to add/remove nodes while minimizing key movement, consistent hashing can reduce the number of remapped keys. Still, results depend on:
- Hash algorithm and seed.
- Node/route list.
- Virtual node configuration.
- Canonical key format.
- Ring/mapping version.

Store the mapping version in JobParameters or metadata so restarts use the exact same ring. If routing supports long-term database sharding, use a proven library/registry rather than writing a naive hash ring from scratch.

## 25. Logging and Auditing Route Decisions

When an item is routed, record enough metadata for investigation:
- Job name.
- JobInstance ID and JobExecution ID.
- Step name.
- Item business key.
- Selected route.
- Routing rule version.
- Delegate name or output resource.
- Rejection reason if any.

Do not log full payloads if they contain personal info, credentials, or sensitive data. Use permitted business keys or reference IDs.

You can count items per route using StepExecution metrics or custom listeners/adapters. Metrics help spot:
- A route suddenly receiving zero items.
- A route receiving an abnormal spike in items.
- Increasing rejection rates.
- Skewed tenant distribution.
- Delegates with high latency or high error rates.

Do not use high-cardinality item IDs as metric tags. Keep route names and rule versions at controlled cardinality.

## 26. Testing the Classifier

A classifier should be tested as an isolated unit. Tests must cover boundary values and overlapping conditions.

Example:

~~~java
@Test
void routesHighValueOrdersToReview() {
    OrderClassifier classifier = new OrderClassifier();

    Order order = orderWithRiskLevel(RiskLevel.HIGH);

    assertEquals(
            OrderRoute.REVIEW,
            classifier.classify(order));
}
~~~

Key tests:
- Every valid route key selects the right route.
- Null and blank are handled per contract.
- Unsupported routes are rejected or failed properly.
- Precedence among conditions is accurate.
- The same item yields the same result repeatedly.
- Changing the order of classifier calls does not change results.
- Different rule versions only alter routes per defined mappings.

A property test can invoke the classifier multiple times with the same item and verify the result stays constant. This does not prove all inputs are deterministic, yet helps uncover accidental counters/random state.

## 27. Testing Retry and Restart

Classifier unit tests are not enough to prove consistent routing in a real Job. Integration tests with a JobRepository and delegate writers are needed.

Scenarios:

| Scenario | What to verify |
|---|---|
| Multiple routes in one chunk | Each item reaches the right delegate |
| Chunk retry | The same item still picks the same route |
| Writer fails after side effect | Retry does not create unintended duplicate data |
| Restart same JobInstance | Rule version and routes remain unchanged |
| New version deployed | Old Job uses compatible rules or fails cleanly |
| Missing route mapping | Job rejects or fails explicitly |
| Non-existent rule version | Does not silently fall back to latest |
| Hash partition | Same key goes to same bucket when version is unchanged |
| Bucket count changed | Job detects mapping version mismatch |
| Multi-threaded Step | Classifier and delegates are thread-safe |
| Partitioned Step | Workers use partition-appropriate mappings and resources |
| Audit | Route and rule version are recorded accurately |

A typical integration test:
1. Launch Job with fixed identifying parameters and routingRuleVersion.
2. Process several chunks and intentionally fail a writer.
3. Record routes of processed items and the JobInstance ID.
4. Restart the same JobInstance.
5. Verify the classifier uses the same rule version and subsequent items reach the right delegates.
6. Check each route's output for missing or duplicate items.
7. Launch a new JobInstance with a new rule version and verify route changes occur only per contract.

## 28. Common Pitfalls

**Classifier uses randomness or counters.** Retries/restarts can send the same item to a different route.

**Relying on the current timestamp.** The same item may be classified differently when reprocessed.

**Reading latest config on every classify call.** Rules can change mid-run between chunks of the same JobInstance.

**Unnormalized route keys.** Different representations of the same business code can go to different routes.

**No default or reject policy.** New values can fail deep inside a writer or be dropped.

**Classifier has side effects.** Retries can repeat side effects and make decisions hard to test.

**Using hashCode of mutable objects.** Routes can change after fields participating in hashing mutate.

**Changing bucket count on restart.** Keys can shift shards and fail to match prior checkpoints/outputs.

**Unversioned mappings.** New deployments can alter routes for restarting Jobs.

**Using classifier routing instead of partitioning.** Routes do not automatically gain independent StepExecutions and lifecycles.

**Assuming composite writer is a distributed transaction.** External side effects may not roll back with the database.

**Skipping restart tests.** Unit tests pass routes, yet real Jobs may duplicate writes or invoke the wrong delegate.

## 29. Workflow for Designing Deterministic Routing

When implementing a classifier in Spring Batch, follow this sequence:

1. Identify item types and valid routes.
2. Choose route keys based on stable business data.
3. Normalize keys before classification.
4. Write a pure, side-effect-free classifier with explicit precedence.
5. Define null, unknown, reject, and default behaviors.
6. If rules change over time, version rules and pin the version per JobInstance.
7. If routes depend on external services, prepare or persist route decisions durably.
8. Choose ClassifierCompositeItemWriter when each item needs one delegate; use CompositeItemWriter when broadcasting.
9. Register proper lifecycles for ItemStream delegates.
10. Keep output paths, writer names, mappings, and bucket counts stable across restarts.
11. Verify thread safety and consider partitioning if independent workers/resources are needed.
12. Design idempotency or outbox for out-of-transaction side effects.
13. Audit routes and rule versions with appropriate business keys.
14. Test unit behavior, retries, restarts, rule migrations, and actual outputs.

A Classifier provides a replaceable and independently testable decision point. Deterministic routing ensures the same item goes to the same destination under a pinned rule set, even when chunks retry or Jobs restart. When route keys are stable, rules are versioned, fallbacks are explicit, and delegates have proper lifecycles/transactions, batch systems can route data while preserving consistency and traceability.

