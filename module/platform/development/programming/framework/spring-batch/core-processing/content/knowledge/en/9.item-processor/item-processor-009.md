# Idempotent processor

In Spring Batch, `ItemProcessor<I, O>` receives an input item, applies processing rules, and returns an output item. A good processor should be able to process the same item again without producing a wrong result or unintended side effects. That is the practical meaning of designing an **idempotent processor**.

In batch processing, an item can be processed again because of a retry, rollback, restart, or because the application resends the same request. If a processor depends on the number of times it is called, the current time, or changes to external state on every run, the results can differ. Designing a processor that is safe to repeat makes the job easier to recover and more predictable.

## 1. What is idempotent?

In software processing, an operation is called idempotent when performing it once or many times under the same conditions leads to the same final result. For a processor, what matters is that the same item and the same reference data must produce the same processing result, and that calling it again creates no additional side effects.

An example of normalizing an order code:

```java
String normalize(String value) {
    return value.trim().toUpperCase(Locale.ROOT);
}
```

Calling the function with `"  ab-123 "` always returns `"AB-123"`. Applying it again to the result `"AB-123"` still leaves the result unchanged:

```text
normalize("  ab-123 ")  -> "AB-123"
normalize("AB-123")    -> "AB-123"
```

This is an idempotent transformation in the mathematical sense: applying it again does not change the already-normalized result.

In an `ItemProcessor`, two related properties are usually needed:

- **Deterministic:** the same input and the same reference data give the same output.
- **No side effects during processing:** calling it again does not write additional data, send additional notifications, or change external state.

These two properties let the processor be called again safely. A pure function processor usually achieves this goal easily: it only computes the output from the input and does not change external state.

## 2. Why can the processor be called again?

You should not assume an item passes through the processor exactly once over the entire job lifecycle. Depending on the fault-tolerance configuration and execution path, the same item can be processed again.

Some common situations:

- **Retry:** the processor or an operation in the chunk hits a transient error and the framework tries again according to the retry policy.
- **Rollback:** an uncommitted chunk is rolled back; processing may have to be redone for the related items.
- **Restart:** the step is run again after the previous execution failed. The reader can restore a checkpoint, while items that were not committed can appear again.
- **An external re-run request:** an operator or a system re-invokes a unit of work after not receiving a confirmation result.
- **Parallel processing:** multiple workers or partitions process different data ranges; if the ranges overlap or a request is sent repeatedly, the same record can be processed multiple times.

For example, a chunk has 100 items. The processor has converted the items, but the writer fails before the chunk commits. When the framework applies a retry or the step is restarted, some or all of the items can be processed again depending on the policy and the saved state.

```text
Read item
   |
   v
ItemProcessor
   |
   v
ItemWriter
   |
   +---- error before commit
             |
             v
          rollback
             |
             v
       retry / restart
             |
             v
       reprocess the item
```

The fact that a processor can be called again is a characteristic to account for in the design. Do not rely on an in-memory counter or assume a call order to decide business results.

## 3. A pure, easily repeatable processor

A simple processor usually takes an input DTO, validates it, and creates a new output object. For example:

```java
public record OrderInput(
        String orderId,
        String customerCode,
        BigDecimal amount) {
}

public record Order(
        String orderId,
        String customerCode,
        BigDecimal amount) {
}

@Bean
ItemProcessor<OrderInput, Order> normalizeOrderProcessor() {
    return input -> {
        if (input.amount() == null || input.amount().signum() <= 0) {
            throw new InvalidOrderException(
                    "Invalid amount for order " + input.orderId());
        }

        return new Order(
                input.orderId().trim(),
                input.customerCode().trim().toUpperCase(Locale.ROOT),
                input.amount().setScale(2, RoundingMode.HALF_UP));
    };
}
```

With the same `OrderInput`, the processor produces the same `Order`, as long as the normalization rules do not change. The processor does not write to the database, does not send messages, and does not update a global counter.

A few principles help keep a processor easy to repeat:

- Create a new output object instead of directly modifying the input object if the object can be reused or shared.
- Use stable transformations such as trim, code normalization, format checking, and computation from the input fields.
- Pass the necessary data into the item or JobParameters instead of reading values that change over time during processing.
- Avoid producing results based on the sequence number of processor calls.
- Do not write business data or emit notifications in the processor unless there is a dedicated deduplication mechanism.

## 4. Avoid depending on the current time and random data

A processor can become non-deterministic if it reads the system clock or generates random values on every call.

An unstable example:

```java
public record OrderWithMetadata(
        String orderId,
        String customerCode,
        BigDecimal amount,
        LocalDateTime processedAt,
        String requestId) {
}

@Bean
ItemProcessor<OrderInput, OrderWithMetadata> processor() {
    return input -> new OrderWithMetadata(
            input.orderId(),
            input.customerCode(),
            input.amount(),
            LocalDateTime.now(),
            UUID.randomUUID().toString());
}
```

When the same item is processed again, `processedAt` and the UUID will differ. If these values affect business results or are recorded, a retry can produce a different result from the first attempt.

If you need a business date, pass that date through JobParameters:

```java
public record BusinessDatedOrder(
        String orderId,
        String customerCode,
        BigDecimal amount,
        LocalDate businessDate) {
}

@Bean
@StepScope
ItemProcessor<OrderInput, BusinessDatedOrder> processor(
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    LocalDate processingDate = LocalDate.parse(businessDate);

    return input -> new BusinessDatedOrder(
            input.orderId(),
            input.customerCode().trim().toUpperCase(Locale.ROOT),
            input.amount(),
            processingDate);
}
```

With the same JobInstance, `businessDate` stays the same, so reprocessing an item uses the same business date. If you need a receipt timestamp or a correlation ID, you can create it at the request/job level and store it in a parameter or appropriate metadata, instead of generating a new value each time `process` is called.

A UUID is not always wrong. If the UUID represents a new business unit, create and store it at the request-intake boundary, and then reuse it on retry. Avoid creating a new UUID inside the processor on each call if it is used as a deduplication key.

## 5. Separate computation from side effects

A processor should focus on converting the item. Operations that change external state, such as writing to a database, sending email, publishing a message, or calling an API to create a transaction, should usually be placed in the writer or a separate step with a suitable recovery mechanism.

For example, a processor should not send an email every time it processes an order:

```java
// Not recommended: each process call may send an additional email.
@Bean
ItemProcessor<OrderInput, Order> processor(NotificationService notifications) {
    return input -> {
        notifications.sendOrderReceived(input.orderId());
        return mapToOrder(input);
    };
}
```

If the chunk rolls back or the processor is called again, the email can be sent multiple times. A database transaction cannot recall an email that has already been sent.

A better design is for the processor to only create output data, while sending notifications is handled in a separate step after the data has been recorded. The notification step needs an idempotency key or an outbox table to determine whether a notification has already been emitted.

```text
ItemReader
    |
    v
ItemProcessor (only transforms data)
    |
    v
ItemWriter (writes data / outbox)
    |
    v
Database commit
    |
    v
Notification step / Outbox publisher
    |
    v
Send notification with a deduplication key
```

If the processor needs to look up data from another service to enrich the item, the read operation is usually acceptable, but you need to consider the stability of the returned data. If the reference data changes between the first processing and the retry, the same item can produce different outputs. This can be solved with a snapshot, a reference-data version, or storing the necessary values together with the batch.

## 6. Reading external data in the processor

Not every service call in a processor is a side effect. For example, looking up a customer tier or an exchange rate can be a read operation. However, the idempotency of the result also depends on whether that service returns stable data.

Suppose the processor fetches the current exchange rate from an API. If the first call returns 25,000 and the retry returns 25,100, the same input transaction can produce a different converted amount. The problem is not that the API is read-only, but that the reference data changes over time.

Some ways to handle it:

- Lock the exchange rate or reference-data version at the start of the batch.
- Store a snapshot of the necessary data in a database or an immutable resource.
- Pass a version/snapshot code through JobParameters so that every execution of the same JobInstance uses the same data.
- Cache lookup results at an appropriate scope if the data is guaranteed to be immutable during the batch.
- If changing reference data is a business requirement, record the version used clearly so the result can be explained.

Do not cache arbitrarily in a singleton processor if the cache makes the result depend on the processing history of a thread or application instance. Clearly define the cache's scope and lifecycle.

## 7. Distinguishing idempotent, deterministic, and exactly-once

These three concepts are related but not synonymous:

| Concept | Meaning | Question to answer |
|---|---|---|
| Idempotent | Repeating the operation does not change the final result any further. | Does calling it again create additional side effects or change the result? |
| Deterministic | The same input and the same reference state produce the same output. | Does the same data always give the same result? |
| Exactly-once | A business effect is applied exactly once within the scope the system guarantees. | Does the system guarantee no loss and no repeated application? |

A pure, deterministic processor usually makes reprocessing safe. But that does not by itself guarantee the whole job is exactly-once. The writer can still write duplicates, an external API can still receive repeated requests, or the metadata may be out of sync with external side effects.

Conversely, a write operation with an idempotency key at the receiving system can help multiple sends of the same request produce only one business result. This is a mechanism at the side-effect boundary, not a property you get automatically just because the processor returns the same output.

## 8. Idempotency key for external side effects

When a process needs to send a request to another system, you can use a stable idempotency key so the receiving system recognizes repeated requests. The key should be created from a stable business identifier, such as a batch ID and an order ID.

For example:

```java
String idempotencyKey = batchId + ":" + input.orderId();
```

If the request sent for the same order in the same batch is retried, the key stays the same. The receiving system can store the processed key and return the old result when it receives a duplicate request.

You should not create the key with `UUID.randomUUID()` on each processor or writer call, because each retry will create a new key and the receiving system cannot recognize that it is the same logical request.

If the external API supports idempotency keys, you need to understand the API's key-retention policy: retention time, key scope, the response when a duplicate is sent, and how it handles the same key with a different payload. If the API does not support it, the application may need a send-status table, an outbox, or a separate reconciliation step.

## 9. The writer must also be designed to tolerate repeated writes

An idempotent processor is not enough if the writer is not idempotent. For example, the processor creates the same `Order` each time, but the writer always performs an `INSERT` of a new row. If the chunk is reprocessed, the database may contain two records for the same order.

Some ways to make the writer safer:

- Use a unique business key such as `order_id` and handle duplicates deliberately.
- Use an upsert or merge statement depending on the database's capabilities.
- Record the processing state by batch ID and item ID.
- Use an outbox with a unique key for events that need to be emitted.
- Clearly distinguish a new insert from an update to an existing record.

For example, the target table can have a unique constraint on `(batch_id, order_id)`. The writer uses an appropriate statement to update or skip records that have already been recorded. The specific implementation depends on the database and business rules.

You should not just catch a duplicate-key error and blindly ignore it. A duplicate record may have a different payload; you need to determine whether it is the same result being resent or a data conflict that needs handling.

## 10. Retry and the processor

In a chunk-oriented step, you can configure retry for transient exceptions. For example, a processor that calls a read service may encounter a timeout. Spring Batch can retry according to the step's retry policy.

```java
return new StepBuilder("processOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

The retry policy needs to be limited to recoverable error types. Do not retry indefinitely or retry data errors that cannot fix themselves. For service calls, there should be a clear timeout, backoff, and a limit on total wait time.

On retry, the processor can be called again depending on the execution path and the fault-tolerance configuration. Therefore, design the processor so it does not depend on the number of calls. If you use `processorNonTransactional` or options related to caching processor results, you need to understand the semantics for the Spring Batch version in use; do not use them to replace the idempotency design for side effects.

## 11. Filter and skip do not replace idempotency

A processor can return `null` to filter an item. It can also throw an exception so the step applies the skip policy if the exception is allowed.

```java
@Bean
ItemProcessor<OrderInput, Order> processor() {
    return input -> {
        if (input.orderId() == null || input.orderId().isBlank()) {
            throw new InvalidOrderException("Missing order ID");
        }

        if (input.amount().signum() == 0) {
            return null; // filter according to a business rule
        }

        return mapToOrder(input);
    };
}
```

Filter decides whether an item is passed to the writer. Skip decides which kinds of exceptions can be ignored. Idempotency addresses whether reprocessing creates repeated results or side effects. These are three different issues.

If the processor writes error logs or stores a rejected record in a separate system, that recording operation also needs to be considered on retry. Avoid creating multiple identical error records for the same item if that makes reconciliation difficult.

## 12. Avoid modifying the input object and using mutable state

A processor is usually designed as a transformation from input to output. If the processor modifies the input object directly, calling it again may receive an object that has already been changed in some processing arrangements or tests, leading to unpredictable results.

An example of what not to modify directly:

```java
@Bean
ItemProcessor<OrderInputMutable, OrderInputMutable> processor() {
    return input -> {
        input.setCustomerCode(input.getCustomerCode().trim());
        input.setAmount(input.getAmount().setScale(2, RoundingMode.HALF_UP));
        return input;
    };
}
```

If possible, use immutable objects or create a new output object:

```java
@Bean
ItemProcessor<OrderInput, NormalizedOrder> processor() {
    return input -> new NormalizedOrder(
            input.orderId().trim(),
            input.customerCode().trim().toUpperCase(Locale.ROOT),
            input.amount().setScale(2, RoundingMode.HALF_UP));
}
```

Immutable objects are easier to reason about, easier to test, and prevent the processor from changing data shared by other components.

## 13. Stateful processors and parallel processing

A processor can hold state such as a counter, a cache, or a set of codes already seen. However, mutable state means the result can depend on item order, thread, or the history of the previous execution.

For example, a processor increments a global counter and assigns a sequence number to each item. If an item is processed again, the new sequence number may differ. If the step runs with multiple threads, multiple threads can update the counter concurrently and create a race condition.

When you need state, consider:

- Is the state business data that must be stored durably, or just a temporary cache?
- Can it be recomputed from the input instead of maintaining a mutable counter?
- Does the state need to be stored in the `ExecutionContext` for restart?
- Does each partition or step execution have its own state?
- Is the processor called concurrently by multiple threads?
- Does the result depend on item order?

If processing in parallel, the processor should be thread-safe or created with an appropriate scope so each execution/partition has its own instance. Do not rely on a singleton processor with mutable state unless synchronization and recovery have been designed explicitly.

## 14. Testing the repeatability of a processor

A processor can usually be unit tested without starting all of Spring Batch. A useful test approach is to call the processor multiple times with the same input and confirm the outputs are equivalent.

For example:

```java
@Test
void processingSameInputProducesSameOutput() throws Exception {
    ItemProcessor<OrderInput, Order> processor = normalizeOrderProcessor();

    OrderInput input = new OrderInput(
            " O-001 ", " customer-a ", new BigDecimal("125.5"));

    Order first = processor.process(input);
    Order second = processor.process(input);

    assertThat(second).isEqualTo(first);
}
```

For a processor with side effects or service dependencies, you need to additionally check:

- Does the same input produce the same number of write or request-sending calls? Ideally the processor performs none of these operations.
- When the service returns the same data snapshot, is the output the same?
- When the service times out and then retries, can the processor continue without creating unintended changes?
- Are the time parameters and the reference-data version fixed within the same JobInstance?
- Does the processor modify the input object or shared state?

At the integration-test level, you can simulate the writer failing before the commit and then re-run the step to confirm the business result is not doubled. Unit tests verify the transformation; integration tests verify the interaction among the reader, processor, writer, transaction, and metadata.

## 15. Example: a processor that calls a lookup service but keeps its output stable

Suppose an order needs to be enriched with a customer segment. The processor can call a read-only service to get the customer segment. To keep the output stable, the service needs to return data according to a version/snapshot determined for the batch.

```java
public record CustomerSnapshot(
        String customerId,
        String segment,
        String version) {
}

public record EnrichedOrder(
        String orderId,
        String customerCode,
        BigDecimal amount,
        String customerSegment) {
}

@Bean
@StepScope
ItemProcessor<OrderInput, EnrichedOrder> enrichOrderProcessor(
        CustomerLookupService customerLookupService,
        @Value("#{jobParameters['customerSnapshotVersion']}") String snapshotVersion) {

    return input -> {
        CustomerSnapshot customer = customerLookupService.find(
                input.customerCode(), snapshotVersion);

        return new EnrichedOrder(
                input.orderId(),
                input.customerCode(),
                input.amount(),
                customer.segment());
    };
}
```

In this example, the processor does not update the customer profile. It only looks up the snapshot at a fixed version and then creates the output. When the same item is processed again within the same JobInstance, the same snapshot version is used.

If the lookup service returns continuously changing data and does not support snapshots, the processor can produce different results on a retry. In that case you need to store the reference data, lock the version, or change the design so the batch result is reproducible.

## 16. Checklist for designing an idempotent processor

When implementing an `ItemProcessor`, consider the following questions:

1. Does the same input always produce the same output when the parameters and reference data do not change?
2. Does the processor read the system clock, generate a UUID, or generate a random number on each call?
3. Does the processor write to a database, send email, publish a message, or call an API that changes state?
4. If there is an external lookup, is the returned data stable throughout the JobInstance?
5. Does the processor directly modify the input object or shared state?
6. If the item is reprocessed after a rollback/restart, is the result still valid?
7. If the processor runs in parallel, are the dependencies and state thread-safe?
8. Can the writer write the same output again without creating duplicate business data?
9. Do external side effects have an idempotency key or a reconciliation mechanism?
10. Is there a test proving that calling it again with the same input gives the expected result?

Not every processor needs a complex mechanism. For pure normalization or transformation, keeping the input clear and creating a new output is usually enough. Processors that call external services or depend on changing data need to design snapshots, versions, and error handling more carefully.

## 17. Points to remember

- A processor can be called again due to retry, rollback, restart, or a repeated run request; do not rely on the assumption that each item is processed exactly once.
- The same input and the same reference data should produce the same output.
- Prefer a pure processor: compute and transform data, creating no side effects.
- Avoid depending on `now()`, a UUID, or a random number newly generated on each call if they affect the result.
- Use JobParameters or a fixed snapshot for business dates and reference data that must be stable.
- If you need to call an external system, use a stable idempotency key or move the side effect to the writer/a separate step with a deduplication mechanism.
- An idempotent processor does not by itself guarantee an idempotent writer or an exactly-once job as a whole.
- Avoid modifying the input object and avoid shared mutable state in parallel processing.
- Distinguish filtering with `null`, skipping due to exceptions, and idempotency; they address different problems.
- Test by calling again with the same input and checking both the output and the side effects.

Designing an idempotent processor lets Spring Batch retry or restart in a more predictable way. Keep the item processing stable, manage reference data with versions, and place side effects at boundaries where repetition can be controlled. Then, when the framework reprocesses an item, there is less risk of incorrectly changing the business result.
