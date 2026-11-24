# Retry state and item identity in Spring Batch

In chunk-oriented processing, an item can be reprocessed when reading, processing, or writing encounters a transient error. To bound the number of attempts and avoid confusion across executions, the retry mechanism must know which item is being retried and the current retry state of that item. This is why **retry state** and **item identity** are closely related in Spring Batch.

Item identity is the stable identifier of a business data unit throughout processing. It enables the framework to associate a retry context with the right item even when, after rollback, the reader creates a fresh Java object for the same record. If the identity is unstable or duplicated, retry counts can be miscalculated, states of two items can collide, or an item can be retried as though it had never failed.

## 1. What is retry state?

Retry state is the information that the retry mechanism retains across attempts of a failed operation. It can include the attempt count so far, the latest exception, the retry policy's state, and internal metadata needed to decide whether to continue retrying or stop.

For example, a processor calls an external lookup service. The service may temporarily time out. The job is allowed to retry a few times before concluding the item cannot be processed:

```text
Item ORDER-42
    |
    v
First process -> timeout
    |
    v
Retry state: one failure recorded
    |
    v
Next process -> timeout
    |
    v
Retry state: continue within limit
    |
    v
Next process -> success
```

Retry state lets the framework recognize that those invocations belong to the same retry sequence for item ORDER-42. Without recognizing the same item, each re-appearance of the object could be treated as a new item and the retry counter would fail to reflect actual progress.

Retry state is technical coordination state for a processing sequence. It is not a business outcome, does not replace reader checkpoints, and does not automatically make external operations idempotent.

## 2. What is item identity?

Item identity is the key that identifies a logical item in the data source. This key typically comes from a business identifier such as an order ID, customer ID, transaction ID, or a combination of fields uniquely identifying a record in a batch.

For example, two distinct Java objects can still represent the same order:

```java
Order firstRead = new Order("ORDER-42", new BigDecimal("125.00"));
Order readAgain = new Order("ORDER-42", new BigDecimal("125.00"));

System.out.println(firstRead == readAgain); // false
```

The two objects do not share Java reference identity (==), yet they share business item identity because both represent ORDER-42.

In Spring Batch, item identity must be stable enough for the retry mechanism to correlate attempts of the same item. Especially after rollback, a reader may re-read a record and instantiate a new object. If retry state is keyed by object identity or by a value that changes across reads, the framework may fail to locate the previous retry context.

## 3. Why does retry need to identify items?

A chunk step processes multiple items within the same transaction. When one item throws an error, the transaction may roll back and the framework has to re-execute part of the work. With stateful retry, retry state must be preserved across rollback boundaries so the next appearance of the same item continues the exact retry sequence.

Example:

```text
Chunk: [A, B, C]
    |
    v
Processor processes A -> success
Processor processes B -> transient error
    |
    v
Chunk rollback
    |
    v
Framework reprocesses items under retry mechanism
    |
    v
Reader may supply B again as a new object
    |
    v
Retry state must be linked to the same item B
```

Without a stable identifier, re-reading can produce a different key. The retry policy then fails to see the prior failure count and may permit more attempts than intended. Conversely, if two distinct items produce the same key, they may share retry state and stop one item prematurely.

Item identity must therefore be both **stable across re-reads** and **unique across distinct logical items within retry scope**.

## 4. How does retry state differ from ExecutionContext?

These two kinds of state serve different purposes:

| Aspect | Retry state | ExecutionContext |
| --- | --- | --- |
| Purpose | Tracks the retry sequence of a failing operation/item. | Persists checkpoints and recovery state of the job/step. |
| Scope | Bound to the retried item/operation. | Bound to StepExecution or JobExecution. |
| Contents | Retry count, exception, and policy state. | Reader position, last key, file name, progress parameters, or small metadata. |
| Lifecycle | Follows the retry context and retry mechanism's cache lifecycle. | Persisted through JobRepository per execution lifecycle. |
| Process restart | Do not assume retry counts survive a JVM restart. | Used to restore execution on restart per Spring Batch rules. |

For example, a reader can save lastProcessedId=200 in the step ExecutionContext. This is a durable checkpoint so the reader resumes after a job restart. Meanwhile, retry state for ORDER-201 tracks how many times processing that item failed in the current retry sequence.

Do not manually store retry counts in ExecutionContext just to track retry attempts. If business rules require durable attempt counts across multiple job executions, design a dedicated business status table with explicit transactions, keys, and update policies.

## 5. Stateful retry vs. stateless retry

Retry can be structured in two broad ways:

- **Stateless retry:** the operation is retried immediately within the same call scope, without attaching long-lived retry state to the item to recover across transaction boundaries.
- **Stateful retry:** attempt state is retained when the operation exits on failure and is retried in a subsequent transaction/processing pass. The framework must re-identify the same item to look up the right retry context.

In batch processing, rolling back a transaction can be part of the recovery strategy. When an item fails, the chunk transaction rolls back; the subsequent pass must continue according to the retry policy and retry state of that exact item. This is where item identity becomes especially critical.

Not every exception requires retrying across a rollback. A transient error can be handled by retrying directly inside the operation if the operation is safe and the transaction does not need to unwind. Conversely, if rollback is required to release locks or restore resources, stateful retry may fit better.

Choose the retry style based on error type, transaction boundaries, and safe re-execution capability. Do not use retry as an infinite loop to mask prolonged infrastructure outages.

## 6. Basic retry configuration

For transient errors, retry can be configured on a fault-tolerant chunk step:

```java
@Bean
Step enrichOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, EnrichedOrder> processor,
        ItemWriter<EnrichedOrder> writer) {

    return new StepBuilder("enrichOrdersStep", jobRepository)
        .<Order, EnrichedOrder>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
}
```

In this example, TransientDataAccessException is chosen because this category can reflect temporary data access issues. retryLimit(3) bounds retries per Spring Batch/Spring Retry configuration. Actual invocation counts should be verified with tests for the version in use, because you must distinguish the initial call from permitted retry attempts.

Only retry exceptions that stand a chance of succeeding on retry. Invalid data errors should normally be validated, skipped, or failed per business rules. Authentication failures, schema mismatches, or programming bugs are rarely resolved by repeating the same call.

## 7. KeyGenerator for determining item identity

When the retry mechanism needs to store context per item, Spring Batch can use KeyGenerator to derive a key for the item. A key generator can be configured on FaultTolerantStepBuilder.

Common API contract in Spring Batch 5:

```java
public interface KeyGenerator {
    Object getKey(Object item);
}
```

If an item has stable equals() and hashCode() based on its business identifier, the default item-based key may suffice. However, for DTOs without clear equality semantics, mutable items, or readers instantiating new objects on each read, provide a dedicated key generator based on the business key.

Example:

```java
@Bean
KeyGenerator orderRetryKeyGenerator() {
    return item -> {
        Order order = (Order) item;
        return order.getId();
    };
}
```

Registering it on the step:

```java
return new StepBuilder("enrichOrdersStep", jobRepository)
    .<Order, EnrichedOrder>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .keyGenerator(orderRetryKeyGenerator)
    .build();
```

The key generator must return a stable key for the same logical item. If the item is not Order, use the proper input type of the processor/reader; the cast above fits only when the step actually processes Order.

## 8. Choosing a stable business key

A good business key should satisfy these conditions:

1. **Stable:** re-reading the same item must yield the same key.
2. **Unique:** two different items within the same processing scope never share a key.
3. **Immutable:** fields forming the key do not change between attempts.
4. **Compact and easy to compare:** avoid putting large payloads into the key.
5. **Clearly scoped:** the key must distinguish batches/tenants/versions if standalone IDs could collide.

For instance, orderId may suffice if globally unique. If order IDs are only unique per tenant, the key should include the tenant:

```java
@Bean
KeyGenerator orderRetryKeyGenerator() {
    return item -> {
        Order order = (Order) item;
        return order.getTenantId() + ":" + order.getId();
    };
}
```

If the same order can appear across multiple imports with different payloads, you may need to include a batch ID or version:

```java
@Bean
KeyGenerator importRetryKeyGenerator() {
    return item -> {
        ImportedOrder order = (ImportedOrder) item;
        return order.getImportBatchId()
            + ":" + order.getTenantId()
            + ":" + order.getOrderId()
            + ":" + order.getSourceVersion();
    };
}
```

This is a key identifying the logical occurrence of an item in a batch. Which components to pick depends on business rules; do not include a version if it can change across re-reads of the same item.

## 9. Why not use object identity or arbitrary hash codes?

Object identity (==) only tells whether two variables point to the same instance. After rollback, a reader may construct a fresh instance from a database row or file line, so references differ even when logical data matches.

hashCode() is not automatically a business key either. Some Java classes do not override equals()/hashCode(), falling back to object identity. Classes that do override them may include mutable fields; if a field changes after the key is stored, cache lookups may fail to find the previous entry.

Unstable example:

```java
public class Order {
    private String id;
    private BigDecimal total;
    private int retryMarker;

    // equals/hashCode are generated from all fields,
    // including retryMarker which mutates during processing.
}
```

If retryMarker mutates, hash/equality can change while the item serves as the key of a retry context. Avoid using fields that change during processing as identity components.

A safe approach is using an immutable key:

```java
public record OrderRetryKey(String tenantId, String orderId) {}
```

The key generator can return a fresh OrderRetryKey on each read; records with identical component values maintain stable equality.

## 10. Key collision and misattributed retry state

If two different items produce the same key, their retry contexts can be shared or overwritten. This causes subtle bugs:

```text
Item A -> key = "ORDER-42" -> retry count = 2
Item B -> key = "ORDER-42" -> finds A's retry state
```

Item B might be treated as having already retried several times even though it never failed, or item A might lose its own state. Therefore, keys must be unique across items that can be retried concurrently or live in the same retry context cache.

Common collision-prone situations:

- IDs unique only within a tenant while the key uses only the ID.
- Multiple input files reusing the same line numbers.
- A record re-imported in different batches while the key omits batch ID.
- A key generator using only item type or a shared status field.
- Using truncated strings or collision-prone hashes without preserving original identifying fields.

When using composite keys, pick components that uniquely identify one business occurrence. Do not include a fresh random timestamp generated on every read in the key, as it turns the same item into multiple distinct keys.

## 11. Reader instantiating fresh objects after rollback

A database reader can map each row into a new DTO. When a chunk rolls back and the reader re-reads the same row, the new object may not match the previous object via equals(). An ID-based key generator helps the framework recognize the two objects as the same logical item.

Example:

```java
public class OrderRowMapper implements RowMapper<Order> {

    @Override
    public Order mapRow(ResultSet rs, int rowNum) throws SQLException {
        return new Order(
            rs.getString("tenant_id"),
            rs.getString("order_id"),
            rs.getBigDecimal("total")
        );
    }
}
```

Each mapper invocation can instantiate a new Order. The retry key should derive from tenant_id and order_id, not from the object's heap address.

For file readers, identity may combine file identity and line number, or a parsed business ID. For paginated APIs, identity may combine source ID and record ID. For queues, use a stable message/event ID produced by the publisher.

If a business ID cannot be extracted because an error happens directly inside read, read-skip callbacks only have the exception and source metadata supplied by the reader. In that case, rely on source identifiers such as file path + line number or message ID if available, and do not assume a processor KeyGenerator resolves read errors before an item is created.

## 12. Item identity and reader buffering

In a chunk step, Spring Batch can buffer read items so that when a transaction rolls back, items can be reprocessed without re-reading the source. This is an important part of coordinating retry and rollback.

With transactional queue sources, a different mechanism may be used because the broker can redeliver messages on transaction rollback. Setting readerIsTransactionalQueue() indicates the reader pulls from a transactional queue so the framework avoids standard buffering for that source.

Whether an item comes from a buffer or is recreated by the reader, retry state must stay bound to the right logical item. Do not rely on a single Java instance if the reader or source can recreate objects. Using a stable key is the clearest way to express business identity.

## 13. Retry state and RetryContextCache

In stateful retry, retry information must be preserved between attempts. Spring Retry provides RetryContext and RetryContextCache; Spring Batch uses the corresponding retry mechanics in fault-tolerant processing.

Conceptually:

```text
Item
  |
  v
KeyGenerator -> item key
  |
  v
RetryContextCache[key]
  |
  +-- retry count
  +-- last exception
  +-- retry policy state
  |
  v
Retry decision
```

The cache allows locating the retry context by key when the same item reappears. The key generator thus bridges the item object and retry state.

Do not treat the retry context cache as durable storage for complete processing history. The cache normally serves the runtime retry lifecycle of the step. If the JVM stops or the application restarts, do not assume prior retry counts remain intact. Spring Batch's durable metadata and checkpoints in ExecutionContext serve separate roles.

If the system needs to audit attempt counts across process restarts, persist them in a dedicated business/technical audit table under a stable operation key. Do not inspect or mutate internal retry cache entries to replace official state storage.

## 14. When does retry state end?

Once an item succeeds or the retry sequence ends per policy, the item's retry context is no longer needed for subsequent attempts in that sequence. The retry mechanism manages context/cache lifecycles according to its implementation.

Applications should not manually remove retry cache entries or reset retry counts by switching keys mid-sequence. Doing so causes the framework to lose track of the retry sequence and exceed configured limits.

If an item fails past the retry limit and is then skipped, listeners can record the final failure. If the exception is not skipped, the step may fail. If the job restarts, the reader resumes from the committed checkpoint and uncommitted items may be reprocessed in the new execution; prior runtime retry state is not a durable historical guarantee.

## 15. Distinguishing retry identity from idempotency key

Both keys may derive from the same business ID, yet serve different purposes:

| Key | Where it is used | Purpose |
| --- | --- | --- |
| Retry identity key | Spring Batch retry mechanism | Identifies an item to look up the right retry state. |
| Idempotency key | Writer, external API, or consumer | Prevents a business action from applying twice when a request is resent. |

A retry identity key does not automatically make side effects idempotent. For example, a key generator helps Spring Batch recognize ORDER-42 is being retried, but if the processor calls a payment API twice with different request IDs, the customer can still be charged twice.

When calling external APIs, use an idempotency key stable across a business operation and pass it across all retries. For database writers, use unique constraints, upserts, or state checks by business key. For messaging, consumers should record processed event IDs so redeliveries do not repeat side effects.

## 16. ProcessorNonTransactional and retry state

In a fault-tolerant step, the processor can be re-invoked when a chunk rolls back. If the processor performs pure but expensive transformations, an application can consider processorNonTransactional() to cache processor outputs and avoid recomputation during reprocessing as supported by step mechanics.

Example:

```java
return new StepBuilder("enrichOrdersStep", jobRepository)
    .<Order, EnrichedOrder>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .processorNonTransactional()
    .build();
```

This option relates to whether the processor needs to be re-invoked after rollback; it replaces neither KeyGenerator nor the retry policy. The processor must suit result caching: it must not depend on time-varying data without a snapshot, and must not perform side effects that are unsafe to repeat.

Do not use processorNonTransactional() merely to hide a processor with side effects. If the processor sends emails or calls mutating APIs, output caching does not cover every restart, process crash, or external transaction case.

## 17. Coordinating retry and skip with item identity

Retry and skip can be configured together:

```java
return new StepBuilder("importOrdersStep", jobRepository)
    .<Order, OrderEntity>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .skip(InvalidOrderException.class)
    .skipLimit(20)
    .keyGenerator(orderRetryKeyGenerator)
    .build();
```

Here:

- TransientDataAccessException is retried up to the retry limit.
- InvalidOrderException can be skipped within the skip limit.
- KeyGenerator determines item identity so retry state is attached to the right order.
- Exceptions outside the retry or skip policy cause the step to fail as configured.

Item identity does not alter which exceptions are retried or skipped. It only ensures retry state is tracked for the right item. Skip limit also differs from retry limit: one caps skipped items, while the other governs retry attempts.

## 18. Retry state in partitioning and multi-threaded steps

When a step runs concurrently, multiple items can maintain retry state simultaneously. The key generator should be stateless and thread-safe. Do not store the current item or retry count in a shared mutable field:

```java
// Avoid: this field can be overwritten by multiple workers.
private String currentOrderId;
```

Compute the key directly from the item:

```java
@Bean
KeyGenerator orderKeyGenerator() {
    return item -> {
        Order order = (Order) item;
        return new OrderRetryKey(order.getTenantId(), order.getId());
    };
}
```

In partitioning, each worker step has its own StepExecution and retry sequences. However, the same business item should never be assigned concurrently to two partitions. If partition ranges overlap, two workers can process the same item together and produce duplicate side effects even though each worker's retry key is stable.

With remote partitioning, retry state typically belongs to the runtime of the worker handling the partition. Do not assume the retry cache is shared across machines. Redelivery/restart on another worker must rely on checkpoints, message identity, and write idempotency.

## 19. Common mistakes when choosing item identity

**Using object reference as identity:** the reader may create a new object after rollback. Use a stable business key to recognize the same record.

**Using default hash code:** classes not overriding equals()/hashCode() fall back to object identity. Check equality semantics or provide a KeyGenerator.

**Using mutable fields in keys:** mutating a field after storing the retry context can cause later lookups to miss the old key. Use immutable fields only.

**Non-unique keys:** two orders in different tenants sharing an ID can collide. Use a composite key including tenant and business ID.

**Generating a new UUID on every read:** the same item gets a different key after rollback, splitting retry state across sequences. Derive keys from stable business identifiers.

**Using the retry key as an idempotency key without considering operation:** an order with multiple legitimate payments could be wrongly deduplicated. Add a payment attempt or operation ID when needed.

**Confusing retry cache with ExecutionContext:** runtime retry counts are not durable checkpoints. Use ExecutionContext for read positions and restart data.

**Assuming retry state survives JVM restart:** do not treat the retry cache as durable history. If needed, store business attempt counts in a dedicated data store.

**Holding state in a singleton KeyGenerator:** multiple workers can invoke it concurrently. Compute keys purely from input without shared state.

**Using retry for unrecoverable errors:** a stable key will not make credential, schema, or bug errors go away. Classify exceptions and bound retries.

## 20. Testing KeyGenerator

Verify that keys are stable for the same logical item and distinct for different items:

```java
class OrderRetryKeyGeneratorTest {

    private final KeyGenerator keyGenerator = item -> {
        Order order = (Order) item;
        return new OrderRetryKey(order.getTenantId(), order.getId());
    };

    @Test
    void generatesSameKeyForFreshInstancesOfSameOrder() {
        Order first = new Order("TENANT-A", "ORDER-42");
        Order second = new Order("TENANT-A", "ORDER-42");

        assertThat(keyGenerator.getKey(first))
            .isEqualTo(keyGenerator.getKey(second));
    }

    @Test
    void distinguishesOrdersFromDifferentTenants() {
        Order first = new Order("TENANT-A", "ORDER-42");
        Order second = new Order("TENANT-B", "ORDER-42");

        assertThat(keyGenerator.getKey(first))
            .isNotEqualTo(keyGenerator.getKey(second));
    }
}
```

OrderRetryKey is an immutable record:

```java
public record OrderRetryKey(String tenantId, String orderId) {}
```

These two tests verify identity logic independently of Spring Batch. Add tests for batch ID/version if they form part of the key.

## 21. Testing retry state across rollback

An integration test should simulate the reader returning a new object for the same business record after rollback. The processor or writer can throw a transient exception several times and then succeed.

What to confirm:

1. Distinct object instances with the same business key produce the same retry key.
2. The retry policy recognizes attempts belonging to the same item.
3. Retry counts do not reset just because the reader created a new object.
4. Once limits are exceeded, the step fails or follows the skip policy as configured.
5. An item with a different business key does not accidentally share the prior item's retry state.
6. After a job restart, the reader resumes from durable checkpoints; do not assume the old retry cache persists.

You can use a test reader that counts reads and instantiates a new Order(...) on every read to verify the key generator. Use a test processor throwing errors per business ID and counting invocations, ensuring the fixture accurately models the step's transaction rollback and reader behavior.

Do not unit-test KeyGenerator alone and conclude job retries work properly. Integration tests confirm the framework actually uses that key in a fault-tolerant step and links retry state accurately across reprocessing.

## 22. Choosing item identity across different data sources

| Source | Typical identity | Considerations |
| --- | --- | --- |
| Database table | Primary key or tenant + primary key | Use stable keys; avoid fields that can mutate during execution. |
| CSV/file | File/batch ID + business ID or line number | Line numbers are unique only within one file; add file identity. |
| Message queue | Message ID/event ID | Producer must assign stable IDs so redeliveries preserve identity. |
| Paginated API | Source ID + record ID/version | Page tokens are not necessarily per-record identity. |
| Multi-tenant | Tenant ID + record ID | Avoid collisions when IDs are unique only per tenant. |
| Multi-version data | Business ID + version or operation ID | Include version only if it identifies a distinct logical occurrence. |

If the reader cannot construct an item due to a parse error, there is no object to pass to a processor retry key. For read skips, record error provenance via exception metadata such as file name, line number, or message identifier if provided by the reader.

## 23. Designing retry state and item identity for production

First, classify retryable errors and determine the required transaction behavior. Choose retry limits and backoff matching external recovery times; avoid retrying data or configuration errors that cannot resolve on their own.

Next, choose a stable business key for items. If items already carry immutable equality/hash codes aligned with business identity, that identity may work. If the reader instantiates new objects, DTOs are mutable, or the business key is composite, configure KeyGenerator to return an immutable, unique key. Check for collisions across tenants, batches, files, or operations when IDs have narrower scopes.

Distinguish runtime retry state from checkpoints in ExecutionContext. The reader saves read positions and restart state in execution context; the retry mechanism tracks per-item retry sequences at runtime. If retry history must persist across process restarts, store it in a separate business/technical audit store.

Finally, guarantee writer or external API operations are idempotent independently of retry identity. Test items re-read as fresh objects, key collisions, retry exhaustion, rollbacks, and restarts. When item identity is stable and retry state binds to the right item, Spring Batch can manage retry attempts accurately without mixing state across records.
