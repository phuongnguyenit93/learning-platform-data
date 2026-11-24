# Processor retry and idempotency in Spring Batch

In a chunk-oriented Step, an item may be processed multiple times. This can happen when a processor throws a transient exception and Spring Batch retries, when a chunk rolls back, or when a Job restarts from a checkpoint. If the processor only transforms data in memory, re-execution typically causes no issues. However, if the processor calls APIs, updates a database, sends messages, or creates other side effects, re-execution can perform the same action multiple times.

Two concepts must be understood together: **retry** and **idempotency**:

- Retry is the mechanism of re-attempting an operation after an error considered recoverable.
- Idempotency is the property guaranteeing that executing the same operation multiple times does not change the business outcome after the first execution.

Retry helps overcome transient failures. Idempotency ensures safe handling when the same item is processed again. Retry without idempotency can duplicate side effects; idempotency without retry may be safe yet still fail when systems are temporarily unavailable.

In Spring Batch, a processor should preferably be a pure transformation: take input, validate, and return a new output without side effects. If business requirements force calling external systems, you must use a stable idempotency key, define transaction boundaries, and test rollback/retry/restart scenarios.

This lesson covers the processor lifecycle, why a processor gets called again, exception classification, configuring retry/backoff/skip, designing deterministic processors, database and API idempotency, inbox/outbox, relationships with chunk transactions, and testing.

## 1. Where does the processor sit in the chunk lifecycle?

A chunk-oriented Step reads items, invokes the processor if configured, collects outputs, and passes the chunk to the writer. A transaction typically wraps chunk processing according to the Step configuration.

~~~mermaid
flowchart TD
    A["Begin chunk transaction"] --> B["ItemReader reads item"]
    B --> C["ItemProcessor processes item"]
    C --> D{"Processor result?"}
    D -->|Item| E["Add output to chunk"]
    D -->|null| F["Filter item"]
    E --> G{"Chunk full or EOF?"}
    F --> G
    G -->|No| B
    G -->|Yes| H["ItemWriter writes chunk"]
    H --> I["Commit transaction"]
~~~

The processor has a simple interface:

~~~java
public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}
~~~

Where:

- `I` is the input item type from the reader.
- `O` is the output item type for the writer.
- Return an object `O` to continue the pipeline.
- Return `null` to filter the item, meaning the item is not passed to the writer.
- Throw an exception to report a processing error.

The processor does not control commits. Transactions and retry/skip policies belong to the Step. However, because the processor runs inside the Step's item-processing flow, its design must be compatible with rollbacks and re-invocation.

## 2. Why can a processor be called multiple times?

A processor must never assume each item is processed only once. Common situations include:

1. The processor throws a transient exception and the Step retries the item.
2. The writer fails, causing the chunk to roll back; depending on configuration and reader, items in the chunk may be reprocessed.
3. A chunk retry causes the framework to re-execute necessary processing.
4. The Step fails and the Job restarts from a checkpoint; uncommitted items may be read/processed again.
5. An operator reruns a `JobInstance` or launches a new `JobInstance` over the same business source.
6. The upstream source replays the same business event or feeds the same message into the batch multiple times.

In a fault-tolerant Step, Spring Batch may buffer read items for reuse on rollback, though whether and when the processor is called again depends on reader type, transactions, and configuration. The safe design rule is never relying on the assumption that a processor runs only once.

For example, a processor calls an API to create a shipment. The API succeeds, but the response times out. Spring Batch sees the exception and retries. If the second call lacks an idempotency key, the shipping system might create two shipments for the same order.

A safe processor must handle receiving the same item again without producing unintended duplicate business effects.

## 3. Retry and idempotency solve two different problems

| Concept | Question answered | Goal |
|---|---|---|
| Retry | When an operation fails transiently, should we try again? | Increase completion likelihood |
| Idempotency | If an operation is called again, is the outcome duplicated? | Protect correctness |
| Deduplication | Is this the same event already processed? | Detect duplicate deliveries |
| Restart | From which checkpoint should the Job resume? | Resume batch after failure |

Retry is a policy governing when and how many times to re-execute. Idempotency is a property of an operation or workflow. Deduplication typically relies on a stable key to recognize an already-applied event. Restart uses Spring Batch metadata to restore progress.

These mechanisms complement rather than replace one another. `ExecutionContext` does not automatically ensure external side effects happen once. Likewise, an idempotency key does not tell a reader where to resume reading.

## 4. A processor should be a pure transformation

A pure processor uses only its input and defined configuration to produce output. It does not call external systems, write to a database, or mutate shared state.

Example:

~~~java
public record RawOrder(
    String orderId,
    String customerId,
    BigDecimal amount,
    String currency
) {
}

public record NormalizedOrder(
    String orderId,
    String customerId,
    BigDecimal amount,
    String currency,
    boolean highValue
) {
}
~~~

Processor:

~~~java
public final class NormalizeOrderProcessor
        implements ItemProcessor<RawOrder, NormalizedOrder> {

    private final BigDecimal highValueLimit;

    public NormalizeOrderProcessor(BigDecimal highValueLimit) {
        this.highValueLimit = highValueLimit;
    }

    @Override
    public NormalizedOrder process(RawOrder item) {
        if (item.amount() == null || item.amount().signum() < 0) {
            throw new InvalidOrderException(
                "Invalid order amount: " + item.orderId()
            );
        }

        String orderId = item.orderId().trim();
        String customerId = item.customerId().trim();
        String currency = item.currency().trim().toUpperCase(Locale.ROOT);

        boolean highValue =
            item.amount().compareTo(highValueLimit) >= 0;

        return new NormalizedOrder(
            orderId,
            customerId,
            item.amount(),
            currency,
            highValue
        );
    }
}
~~~

The same `RawOrder` and the same `highValueLimit` produce the exact same `NormalizedOrder`. The processor does not mutate the input item, write data, or depend on state from previous calls.

This is the easiest kind of processor to retry: if Spring Batch invokes it again, the transformation yields the identical result.

### Do not mutate the input item unnecessarily

The following example can cause problems:

~~~java
public Order process(Order item) {
    item.setStatus("NORMALIZED");
    item.setAmount(item.getAmount().setScale(2));
    return item;
}
~~~

If the same object is retained in a buffer or reused in another attempt, the processor may observe data already mutated from a prior attempt. That makes results depend on call history.

Prefer immutable objects like Java records or construct a new output object. If a mutable model is mandatory, make a copy before mutating.

## 5. Deterministic processing

A deterministic processor returns the same output given the same input and business configuration. Factors that make a processor non-deterministic include:

- Reading current time via `Clock.systemUTC()` on every call.
- Generating a new UUID for the same item.
- Using random numbers.
- Reading mutable configuration that changes between retries.
- Calling an API that returns different states across calls.
- Relying on a counter or order of previously processed items.
- Using mutable database data without a snapshot.

Non-deterministic example:

~~~java
public EnrichedOrder process(RawOrder order) {
    return new EnrichedOrder(
        order.orderId(),
        Instant.now(),
        UUID.randomUUID().toString()
    );
}
~~~

If the processor is invoked again, the timestamp and ID will change. That can produce different outputs for the same item.

This can be fixed by snapshotting values before running the Step:

~~~java
public record BatchContext(
    Instant processingTime,
    String runId
) {
}
~~~

Pass `processingTime` and `runId` via `JobParameters` or `JobExecutionContext`, then inject them via `@StepScope`. The same `JobInstance` uses the same snapshot by design.

If an event ID is needed, generate it at the business-event creation boundary and store it stably alongside the input data, rather than regenerating it on every processor invocation.

## 6. Classifying exceptions before configuring retry

Not every error should be retried. Retries only help when system state is likely to change so the next attempt can succeed.

| Error category | Example | Handling direction |
|---|---|---|
| Transient errors | Timeout, connection reset, HTTP 503 | Bounded retry |
| Rate limits | HTTP 429 | Retry per `Retry-After` or backoff |
| Invalid data | Missing ID, negative amount | Usually do not retry; reject/skip |
| Configuration errors | Wrong URL, missing credentials | Fail early |
| Mapping/schema errors | Unparseable field | Usually do not retry |
| Concurrency conflicts | Optimistic lock/deadlock | Can retry with bounds |
| Business rejections | Ineligible for processing | Do not retry if state has not changed |

Exceptions should be meaningful so policies classify them properly:

~~~java
public class TransientPricingException extends RuntimeException {
    public TransientPricingException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}
~~~

Do not catch every exception and throw a single generic `RuntimeException`. If all errors are treated as retryable, an item with invalid data will be retried repeatedly with zero chance of succeeding.

## 7. Configuring processor retry in a Step

Retries are configured at the fault-tolerant Step level. Example:

~~~java
@Bean
Step enrichOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<RawOrder> reader,
        ItemProcessor<RawOrder, EnrichedOrder> processor,
        ItemWriter<EnrichedOrder> writer) {

    return new StepBuilder("enrichOrdersStep", jobRepository)
        .<RawOrder, EnrichedOrder>chunk(50, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientPricingException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(100)
        .build();
}
~~~

Meaning:

- `faultTolerant()` enables retry/skip configuration for the Step.
- `retry(...)` declares retryable exceptions.
- `retryLimit(...)` caps retry attempts per the semantics of your Spring Batch version.
- `skip(...)` permits bypassing specified data exceptions.
- `skipLimit(...)` caps total skips.

Step-level retry policies can apply to read, process, or write phases depending on the exception and configuration. Never assume every thrown exception came from the processor. When distinguishing errors by stage is needed, use explicit exception types, listeners, and Step tests.

### Retry limit and initial attempt

Builder APIs and how `retryLimit` counts attempts can vary across Spring Batch/Spring Retry versions. Check your project's dependency versions and verify actual attempt counts with tests. Do not infer total attempts solely from the `retryLimit` property name.

### Excluding exceptions from retry

If only a specific subset of errors should be retried, configure `retry(...)` for that group and `noRetry(...)` for non-retryable errors per your version's API. A validation exception should never be retried simply because it is a `RuntimeException`.

## 8. Backoff between retry attempts

Immediate back-to-back retries without delay can overload an already struggling service. Backoff introduces a wait interval between attempts.

Exponential backoff example:

~~~java
ExponentialBackOffPolicy backOffPolicy =
    new ExponentialBackOffPolicy();

backOffPolicy.setInitialInterval(500L);
backOffPolicy.setMultiplier(2.0);
backOffPolicy.setMaxInterval(8000L);
~~~

Attach the policy to the fault-tolerant Step per your version's API:

~~~java
return new StepBuilder("enrichOrdersStep", jobRepository)
    .<RawOrder, EnrichedOrder>chunk(50, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TransientPricingException.class)
    .retryLimit(3)
    .backOffPolicy(backOffPolicy)
    .build();
~~~

With the illustrative configuration, wait intervals grow across retries up to the maximum cap. Real values should be chosen based on service timeouts, latency, throughput, and retry budgets.

### Jitter and retry storms

If thousands of items fail at once and all retry after exactly 1, 2, and 4 seconds, they can create synchronized traffic spikes on the service. Jitter adds controlled randomness to wait intervals to spread out retries.

Not every default `BackOffPolicy` includes jitter. If a service enforces rate limits, a custom policy or honoring HTTP `Retry-After` responses may be required.

## 9. Retry budgets and timeouts

Retries must not continue indefinitely. Define a maximum total time budget per item and for the whole Step.

Example:

- Timeout per call: 2 seconds.
- Maximum 3 retries.
- Backoff: 0.5, 1, and 2 seconds.
- Total expected item duration must fit within the Job's SLA.

Account for connection time, server processing time, backoff, and transactions. If the Step holds a transaction open while waiting on an API, database connections or locks may be held longer than necessary.

Some designs extract API enrichment into a separate step or use bulk APIs to reduce call counts. Retry is a recovery mechanism, not a substitute for proper throughput and timeout design.

## 10. Processor retries can repeat side effects

Example processor:

~~~java
public EnrichedOrder process(RawOrder order) {
    shippingClient.createShipment(order);
    return map(order);
}
~~~

Suppose the shipment creation API succeeds, but the response times out. The processor throws an exception; Spring Batch retries. The API receives a second request and creates a duplicate shipment.

Even if the first call returns a successful response, the writer may fail later and roll back the chunk. If the processor runs again during chunk retry, the API may be called again.

A better approach separates transformation from side effects:

~~~java
public ShipmentCommand process(RawOrder order) {
    return new ShipmentCommand(
        order.orderId(),
        order.customerId(),
        order.shippingAddress(),
        order.shipmentEventId()
    );
}
~~~

The processor only builds the command. The writer or an application service executes the side effect using a stable idempotency key.

If the API supports an `Idempotency-Key` header, send the exact same key on every retry of the same business operation.

## 11. Idempotency keys must be stable

An idempotency key represents a single business operation. It must be created once and stay identical across:

- Spring Batch internal retries.
- Chunk rollbacks and reprocessing.
- Job restarts.
- Broker redeliveries if items come from messages.
- Producer retries or replays.
- HTTP retries after timeouts.

Command example:

~~~java
public record ShipmentCommand(
    String orderId,
    String customerId,
    Address address,
    String idempotencyKey
) {
}
~~~

The key can be a producer-generated shipment event ID, or a composite key per business contract such as `orderId + shipmentVersion`. Never generate a fresh UUID inside each `process()` call.

### Distinguishing idempotency keys from attempt IDs

- Idempotency keys stay constant for the same business operation.
- Attempt IDs can change on each attempt to trace individual calls.
- Correlation IDs link logs/traces across services.
- Message delivery tags can change on each broker delivery.

Never use an attempt ID or delivery tag as an idempotency key because they do not identify the same business operation.

## 12. Idempotency at external APIs

If the writer calls an API that supports idempotency:

~~~java
public ShipmentResult createShipment(ShipmentCommand command) {
    return shippingClient.createShipment(
        command,
        command.idempotencyKey()
    );
}
~~~

The external API must clearly define:

- Scope of key uniqueness.
- Key retention duration.
- Behavior when the same key is resent with the same payload.
- Behavior when the same key is resent with a different payload.
- Response returned for an already-processed request.
- Handling of concurrent requests carrying the same key.

If the server receives the same key with an equivalent payload, it should return the stored result instead of creating a new shipment.

If the same key arrives with a different payload, it should normally return a conflict or explicit error. Never silently accept it, as that can mask producer bugs.

### A timeout does not prove a request failed

When a client times out, the server may have already executed the side effect while the response failed to reach the client. Never generate a new key just because the previous call timed out. Retry with the same key or reconcile using the business operation ID.

If an API does not support idempotency and offers no way to query outcomes by business key, exactly-once side effects cannot be guaranteed by processor logic alone.

## 13. Idempotency in the database

If business updates and idempotency records live in the same database, protect them with a unique constraint and transaction.

Example table:

~~~sql
CREATE TABLE processed_operation (
    operation_key VARCHAR(200) PRIMARY KEY,
    operation_type VARCHAR(100) NOT NULL,
    payload_hash VARCHAR(128) NOT NULL,
    processed_at TIMESTAMP NOT NULL
);
~~~

Service executing the operation:

~~~java
@Transactional
public ProcessingResult applyOnce(ShipmentCommand command) {
    boolean inserted = operationRepository.insertIfAbsent(
        command.idempotencyKey(),
        "CREATE_SHIPMENT",
        hash(command)
    );

    if (!inserted) {
        return ProcessingResult.ALREADY_APPLIED;
    }

    shipmentRepository.createShipment(command);

    return ProcessingResult.APPLIED;
}
~~~

The critical point is inserting the operation key and applying the business update in the same transaction. If the business update fails, the operation record must roll back too. If the transaction commits, subsequent retries hit the unique key and do not repeat the side effect.

The insert-if-absent statement depends on the database. PostgreSQL example:

~~~sql
INSERT INTO processed_operation (
    operation_key,
    operation_type,
    payload_hash,
    processed_at
)
VALUES (?, ?, ?, CURRENT_TIMESTAMP)
ON CONFLICT (operation_key) DO NOTHING;
~~~

Do not rely solely on a SELECT-then-INSERT pattern. Two concurrent workers can both see the key as absent. A database unique constraint is the final safeguard.

### Same key with a different payload

Store a payload hash or critical business fields to distinguish valid duplicates from erroneous key reuse. If the key exists with a different payload hash, raise an error or quarantine per policy. Never treat every conflict as a harmless duplicate.

## 14. Should the processor check the idempotency store?

You could write a processor that checks whether the key exists and returns `null` if the item was already processed. However, this approach is usually insufficient on its own:

~~~java
public ShipmentCommand process(RawOrder order) {
    if (operationRepository.exists(order.eventId())) {
        return null;
    }

    return createCommand(order);
}
~~~

Issues:

- SELECT and write are not atomic.
- Two workers can simultaneously see the key as absent.
- State can change between processor and writer.
- The processor may be invoked again.
- Returning `null` increments `filterCount`, potentially confusing duplicates with business filtering.
- If the check creates a marker or side effect, transaction boundaries become harder to control.

The processor can read info or flag expected duplicates as an optimization, yet the writer/service must still enforce protection via unique constraints or API idempotency keys.

If reporting needs to distinguish duplicates, outputs can carry an explicit route/result such as `NEW`, `ALREADY_APPLIED`, or `REJECTED`, rather than silently filtering without an audit trail.

## 15. Idempotency in the writer and chunk transactions

With a database writer, business updates usually run inside the chunk transaction if using the proper `DataSource` and transaction manager. If the chunk rolls back, updates in that transaction roll back. When the Step retries, operations can rerun against uncommitted state.

This makes database writers safer when:

- All updates participate in the same transaction.
- No independent propagation commits side effects outside the chunk.
- Unique constraints protect business keys.
- SQL updates include appropriate conditions.
- Triggers or stored procedures also avoid out-of-transaction side effects.

Writer example:

~~~java
public class ShipmentWriter implements ItemWriter<ShipmentCommand> {

    private final ShipmentService shipmentService;

    public ShipmentWriter(ShipmentService shipmentService) {
        this.shipmentService = shipmentService;
    }

    @Override
    public void write(Chunk<? extends ShipmentCommand> chunk) {
        for (ShipmentCommand command : chunk.getItems()) {
            shipmentService.applyOnce(command);
        }
    }
}
~~~

The service shares the Step's transaction manager and `DataSource`. Never open a `REQUIRES_NEW` transaction for the operation key while the business update stays in the outer transaction; doing so can commit the marker before the business update commits.

### Transaction propagation must be understood clearly

- `REQUIRED` normally joins the current transaction if one exists.
- `REQUIRES_NEW` suspends the current transaction and starts an independent transaction.
- `NOT_SUPPORTED` can suspend the current transaction and run non-transactionally.

If an inbox marker commits in `REQUIRES_NEW` while the writer's business update rolls back, subsequent retries may treat the item as a duplicate even though the business update never completed. Choose propagation intentionally and test with a real database.

## 16. Processor side effects with a different transaction manager

A processor might call a repository using the Step's transaction manager. If the database operation joins the chunk transaction, rollback can undo it. However, placing side effects in the processor still makes code harder to reason about and unsafe if:

- The dependency uses a different `DataSource` or transaction manager.
- The method uses `REQUIRES_NEW`.
- The processor calls an API or broker outside the transaction.
- An async task runs after `process()` returns.
- Side effects commit before the writer finishes.
- Retry policies re-invoke the processor outside the expected transaction.

Prefer pure processors and place side effects in writers/services designed for transactions. If a side-effecting processor is unavoidable, document transaction ownership explicitly and test crash windows.

## 17. Outbox pattern for message publishing side effects

A common use case is a processor/writer updating a database and needing to publish an event. Calling a broker right after the database update creates a failure window:

- DB commits but publish fails: downstream misses the event.
- Publish succeeds but DB rolls back: downstream receives an event without corresponding state.
- Publish succeeds but response times out: retry may publish duplicates.

The Outbox Pattern stores the publishing intent in the same transaction as the business update.

~~~sql
CREATE TABLE outbox_event (
    event_id VARCHAR(200) PRIMARY KEY,
    aggregate_id VARCHAR(200) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL
);
~~~

Within the same transaction:

1. Record the operation/idempotency key.
2. Update business data.
3. Insert the outbox event.
4. Commit.

A separate publisher reads the outbox and dispatches messages. If the publisher crashes after publishing but before marking published, the event may be resent. Downstream consumers still require idempotency.

Outbox makes business updates and publishing intent atomic in the database; it does not turn broker delivery into exactly-once.

## 18. Distinguishing retryable vs. non-retryable in a business processor

Example processor calling a pricing service:

~~~java
public EnrichedOrder process(RawOrder order) {
    try {
        PriceQuote quote = pricingClient.quote(order.productId());
        return new EnrichedOrder(order, quote);
    } catch (SocketTimeoutException ex) {
        throw new TransientPricingException(
            "Pricing service timeout",
            ex
        );
    } catch (InvalidProductException ex) {
        throw new InvalidOrderException(
            "Invalid product: " + order.productId()
        );
    }
}
~~~

Timeouts can be retried. A non-existent product is a data error or business rejection, normally not retried if data has not changed.

If the pricing service returns HTTP 429, respect `Retry-After` if the client and retry policy support it. HTTP 5xx may be transient; HTTP 4xx are usually request/validation errors, with exceptions such as 408 or 429. Classify according to the API contract rather than status code ranges alone.

Do not blindly retry all `IOException` instances. Some errors are configuration bugs or unrecoverable payload errors.

## 19. Skipping after retries are exhausted

An exception can be configured as both retryable and skippable. Once retries are exhausted, the Step can apply its skip policy if that exception is skippable.

Example:

~~~java
return new StepBuilder("enrichOrdersStep", jobRepository)
    .<RawOrder, EnrichedOrder>chunk(50, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TransientPricingException.class)
    .retryLimit(3)
    .skip(InvalidOrderException.class)
    .skipLimit(100)
    .build();
~~~

In this example, transient pricing errors are retried. `InvalidOrderException` errors can be skipped. If a transient error should be skipped once retries are exhausted, add it to the skip policy and explicitly verify the business consequences. Never skip infrastructure failures merely to force the Job to finish `COMPLETED`.

### SkipListener and reject output

If skipped items must be saved for investigation, use a `SkipListener` or reject writer. Listeners should not perform non-idempotent side effects because callbacks can be affected by transactions/rollbacks and Step lifecycle.

A durable reject store can use a unique key combining `JobInstance` + item business key to prevent duplicate reject records.

## 20. Returning null from a processor vs. retry and skip

`ItemProcessor` returning `null` means filtering the item. This is not an exception, not a retry, and not necessarily a skip.

Example:

~~~java
public NormalizedOrder process(RawOrder order) {
    if (order.isTestRecord()) {
        return null;
    }

    return normalize(order);
}
~~~

When an item is filtered:

- The item is not passed to the writer.
- `filterCount` increments per Step semantics.
- There is no exception to retry.
- `processSkipCount` does not increment simply from returning `null`.

If the processor returns `null` because it detected an already-processed event, decide whether you want that counted as a filter or a duplicate. For business auditing, return an explicit outcome or record a dedicated metric inside the idempotency component.

## 21. Stateful processors and concurrency

A processor with mutable fields can introduce bugs during retries or parallel execution:

~~~java
public class UnsafeProcessor
        implements ItemProcessor<Order, Order> {

    private int processedCount;

    @Override
    public Order process(Order order) {
        processedCount++;
        order.setSequence(processedCount);
        return order;
    }
}
~~~

Results depend on ordering and invocation count. If an item is retried, its sequence number changes. If the Step runs multi-threaded, the counter races.

Do not use a processor to generate business sequences via in-memory counters. Use source IDs, database sequences, or an allocator with explicit transactions and semantics.

If a processor needs a cache, ensure the cache is purely an optimization and never alters outcomes. Shared mutable caches must be thread-safe and must never become the source of truth for business state.

### @StepScope does not automatically make a processor thread-safe

`@StepScope` creates a target bean bound to `StepExecution`, yet a multi-threaded Step can still call the same target from multiple threads. If a processor holds mutable state, synchronize it or redesign it to be stateless.

Partitioning normally creates a separate `StepExecution` per partition, making it better suited when per-worker state is required.

## 22. Snapshotting configuration and time-dependent data

Processors may use thresholds, exchange rates, policies, or business dates. If these values change between retries or restarts, the same item can be processed differently.

Example high-value threshold:

~~~java
@Bean
@StepScope
ItemProcessor<RawOrder, EnrichedOrder> orderProcessor(
        @Value("#{jobParameters['highValueLimit']}") BigDecimal limit,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new OrderProcessor(limit, LocalDate.parse(businessDate));
}
~~~

If a `JobInstance` must keep the same rules, parameters must remain stable across restarts. Use identifying `JobParameters` when values form part of run identity; otherwise, store an explicit metadata snapshot and ensure restarts restore identical values.

Never read thresholds from a mutable config server on each `process` call if changes could yield inconsistent results across attempts.

## 23. Retries and asynchronous side effects

A processor might submit work to an executor or call an async service and return before completion. That removes the asynchronous work from the chunk's transaction boundary.

Dangerous example:

~~~java
public OrderCommand process(Order order) {
    executor.submit(() -> externalClient.publish(order));
    return toCommand(order);
}
~~~

If the Step rolls back after the async task starts, the side effect can still happen. Retries submit additional tasks. Job shutdown does not necessarily wait for or properly cancel submitted tasks.

If asynchronous processing is required, use a model with explicit acknowledgments and durable queues, or write an outbox inside the transaction and let a separate publisher handle dispatch. Never fire-and-forget side effects from a processor.

## 24. Processor retries vs. writer retries

A Step can retry exceptions originating in multiple stages. Know where side effects live:

| Stage | Example error | Risk on retry |
|---|---|---|
| Reader | Timeout fetching input | Duplicate reads or missed items if cursor/ack is broken |
| Processor | Enrichment API timeout | API may have already executed side effects |
| Writer | DB deadlock or API timeout | Partial writes may have occurred |
| Commit | Connection lost during commit | Client may not know whether transaction committed |

Processors should generally be side-effect-free. Writers are the usual place for writing output and can rely on chunk transactions when resources share the transaction manager. External writers still require idempotency.

Never assume retrying an exception always means the prior operation did not happen. A timeout often simply means the client did not receive the response in time.

## 25. Retry policies do not replace circuit breakers

Retries fit short-lived errors. If an external service is down for an extended period, retrying every item slows down the Job and adds pressure to the failing system.

A circuit breaker can temporarily halt calls after consecutive failures, giving the dependency time to recover. When open, the processor can throw a meaningful exception so the Step stops or waits for retry via a separate workflow.

Principles:

- Finite retry budgets.
- Per-request timeouts.
- Backoff and jitter.
- Circuit breakers when dependencies can suffer prolonged outages.
- Rate limiters to stay within quotas.
- Metrics for attempts, latencies, and failures.
- Never retry validation or configuration errors.

Retries, circuit breakers, and rate limiters solve different problems; they can work together, though nested retry layers must be avoided so attempt counts do not multiply unexpectedly.

## 26. Testing pure processors

Because pure processors have no Spring Batch context dependencies, unit tests are straightforward:

~~~java
@Test
void normalizesOrderDeterministically() throws Exception {
    NormalizeOrderProcessor processor =
        new NormalizeOrderProcessor(new BigDecimal("1000.00"));

    RawOrder input = new RawOrder(
        " O-1001 ",
        " C-10 ",
        new BigDecimal("1200.00"),
        "usd"
    );

    NormalizedOrder first = processor.process(input);
    NormalizedOrder second = processor.process(input);

    assertEquals(first, second);
    assertEquals("O-1001", first.orderId());
    assertEquals("C-10", first.customerId());
    assertEquals("USD", first.currency());
    assertTrue(first.highValue());
}
~~~

The test calls the processor twice with the same input and verifies equivalent results. This is a simple way to verify deterministic behavior.

If the processor returns objects without overridden `equals`, assert individual fields. Records provide value equality out of the box.

### Verifying input immutability

For mutable inputs, snapshot state before calling `process` and assert it remained unchanged. Better yet, use immutable inputs so mutation permutations need not be tested.

## 27. Testing retries with mock dependencies

If the processor calls a dependency that can time out, tests should simulate failure followed by success:

~~~java
@Test
void processorCanRecoverFromTransientDependencyFailure()
        throws Exception {

    when(pricingClient.quote("SKU-1"))
        .thenThrow(new TransientPricingException("timeout", null))
        .thenReturn(new PriceQuote(new BigDecimal("25.00")));

    PricingProcessor processor =
        new PricingProcessor(pricingClient);

    assertThrows(
        TransientPricingException.class,
        () -> processor.process(orderWithSku("SKU-1"))
    );

    EnrichedOrder result =
        processor.process(orderWithSku("SKU-1"));

    assertEquals(new BigDecimal("25.00"), result.price());
    verify(pricingClient, times(2)).quote("SKU-1");
}
~~~

This test only proves the processor can raise an error and succeed on a later call. It does not test Spring Batch's retry policy. To test Step retries, run a real Step with a fake processor/dependency and verify attempt counts.

## 28. Testing side-effect idempotency

For services using idempotency keys:

~~~java
@Test
void appliesSameOperationOnlyOnce() {
    ShipmentCommand command = new ShipmentCommand(
        "O-1001",
        "C-10",
        address(),
        "shipment-event-9001"
    );

    when(operationRepository.insertIfAbsent(
        "shipment-event-9001",
        "CREATE_SHIPMENT",
        expectedHash(command)
    )).thenReturn(true, false);

    shipmentService.applyOnce(command);
    shipmentService.applyOnce(command);

    verify(shipmentRepository, times(1))
        .createShipment(command);
}
~~~

This test verifies the same key creates the side effect only once in service logic. With a real database, write integration tests to verify unique constraints and transaction rollbacks.

### Testing same key with a different payload

Construct two commands with the same key but different amount/address values. The service must detect invalid key reuse or return a conflict per contract. Never silently ignore differing payloads.

## 29. Testing Step retries with spring-batch-test

Use `JobLauncherTestUtils` to run a Step and verify fault-tolerant behavior.

Example test setup where the processor fails only on the first attempt:

~~~java
AtomicInteger attempts = new AtomicInteger();

ItemProcessor<RawOrder, EnrichedOrder> processor = item -> {
    if (attempts.incrementAndGet() == 1) {
        throw new TransientPricingException(
            "Temporary failure",
            null
        );
    }

    return enrich(item);
};
~~~

Run the Step with a one-item reader and a fake writer or test database. After launch:

- Verify the Step is `COMPLETED` when retry succeeds.
- Verify the processor was re-invoked according to policy.
- Verify the writer received the item exactly once.
- Verify no duplicate business records exist.
- Verify retry metrics/listeners if tracked by the application.

To test the retry limit, configure the processor to always throw. Verify the Step fails after the actual attempt count for your version/configuration. Do not merely assert the exception in a unit test; inspect `StepExecution` and `JobExecution`.

## 30. Testing chunk rollback and processor re-invocation

An important test makes the writer fail after the processor already handled items. In a fault-tolerant Step, depending on configuration, items may be reprocessed during rollback/retry.

Simulation:

1. Reader returns two items.
2. Processor creates outputs and counts invocations.
3. Writer throws a transient exception on the first write.
4. Retry policy permits retrying.
5. Writer succeeds on the next attempt.
6. Verify final output has no duplicates.
7. Verify the processor created no out-of-transaction side effects, or side effects were protected by idempotency keys.

Do not claim the processor is always re-invoked under every rollback configuration. Tests must reflect the actual reader/transaction and fault-tolerance behavior of your application.

## 31. Testing restart after failure

Job restart tests must use the same `JobInstance` and identifying `JobParameters`. Trigger a failure after at least one chunk has committed.

Verify:

- Committed chunks are not re-written beyond idempotency policy.
- Uncommitted items proceed.
- The processor may be re-invoked for items in the failed chunk.
- External non-database side effects are not duplicated.
- Idempotency keys remain unchanged.
- `JobRepository` stores checkpoints accurately.
- Output writers restore proper state.

If the processor depends on time or configuration, restart tests must confirm snapshots stay identical across executions.

## 32. Retry listeners and observability

When monitoring retries is needed, use listeners appropriate for your Spring Batch/Spring Retry version. Listeners help observe:

- Exception type.
- Item business key.
- Attempt count.
- Wait duration.
- Final outcome.
- `JobExecution` and `StepExecution` IDs.

Do not log full payloads if they contain sensitive data. Use correlation IDs or business keys.

Metrics may include:

- `processor.process.count`
- `processor.retry.count`
- `processor.failure.count`
- `processor.skip.count`
- `processor.duration`
- `processor.idempotency.hit.count`
- `external.api.timeout.count`
- `external.api.idempotency.conflict.count`

Rising retry rates can signal a degrading dependency. Rising idempotency hits can indicate normal redelivery or duplicate producer submissions; correlate with broker delivery metrics.

## 33. Common implementation pitfalls

### Assuming the processor is called only once

Retries, rollbacks, and restarts can reprocess the same item. Design processors to be safe across multiple calls.

### Sending messages or calling side-effecting APIs in the processor

Retries can resend messages or repeat actions. Separate transformation from side effects, or use stable idempotency keys.

### Generating a new UUID in every process() call

The same operation gets different keys and cannot be deduplicated. Generate keys at the business event source and preserve them.

### Retrying every exception

Data and configuration errors do not fix themselves. Retry only transient errors or recoverable conflicts.

### Unbounded retries

Can tie up chunks/Jobs for too long and cause retry storms. Use limits, timeouts, backoff, and retry budgets.

### Using SELECT alone to check prior processing

Race conditions still allow duplicates. Use unique constraints and atomic inserts/updates.

### Committing idempotency markers separately

The marker can commit while the business update rolls back. Put both in the same transaction when sharing a database.

### Unintentional REQUIRES_NEW usage

Markers can commit independently of the chunk. Audit transaction propagation.

### Treating HTTP timeouts as failed requests

The server may have already performed the operation. Retry with the same key or reconcile.

### Using counters or mutable fields in processors

Retries and concurrency make outputs depend on call history. Processors should be stateless.

### Reading current time or random values in processors

The same item can yield different outputs after retry. Snapshot values per `JobInstance` or include them in inputs.

### Confusing filtering with skipping

Returning `null` is filtering, not an exception/skip. Track `filterCount` and `skipCount` separately.

### Assuming database and broker share a transaction

Without transaction coordination, database commits and broker acks still have a failure window. Use inbox/outbox and idempotency.

### Testing the processor in isolation only

Unit tests do not prove Step retries, rollbacks, and restarts work properly. Add Step integration tests.

## 34. Processor retry and idempotency design workflow

When implementing a retry-capable processor, follow this sequence:

1. **Identify side effects:** does the processor only transform data, or call databases/APIs/brokers?
2. **Prefer pure transformations:** produce new, deterministic outputs without mutating inputs.
3. **Classify errors:** transient, validation, business rejection, configuration, or concurrency conflict.
4. **Choose retry policies:** retry only recoverable errors.
5. **Set retry budgets:** limits, timeouts, backoff, jitter, and total duration.
6. **Design idempotency keys:** stable across retries, rollbacks, restarts, and redeliveries.
7. **Place side effects properly:** writer/service with clear transactions; external APIs need idempotency keys.
8. **Protect the database:** unique constraints, insert-if-absent, and business updates in the same transaction.
9. **Use outbox:** when events must be published after business updates.
10. **Keep config deterministic:** snapshot business dates, thresholds, policy versions, and run IDs.
11. **Test:** repeated inputs, transient dependency failures, retry limits, chunk rollbacks, and restarts.
12. **Monitor:** retry rates, failures, skips, idempotency hits, and external API timeouts.

## 35. Key takeaways

- `ItemProcessor` may be invoked multiple times for the same item due to retries, rollbacks, or restarts.
- Retry is the re-execution mechanism; idempotency is the ability to handle re-execution without duplicating business effects.
- Processors should be pure, deterministic transformations without side effects.
- Prefer immutable inputs/outputs and never mutate input objects.
- Never generate new UUIDs, timestamps, or random values for the same operation inside `process()`.
- Classify exceptions into transient, validation, business rejection, and configuration errors.
- Retry with limits, timeouts, backoff, and jitter; never retry all errors.
- Step retry policies can affect read/process/write depending on exceptions and configuration.
- Database side effects must join appropriate transactions; watch propagation like `REQUIRES_NEW`.
- External APIs require stable idempotency keys; timeouts do not prove requests were not processed.
- Unique constraints and atomic inserts protect databases against concurrent duplicates.
- Inbox stores received events; outbox stores publishing intent alongside business updates.
- `ExecutionContext` checkpoints do not replace idempotency stores.
- Returning `null` from a processor is filtering, not retry or skip.
- Test pure processors, Step retries, chunk rollbacks, and Job restarts.
- Monitor attempts, retries, skips, idempotency hits, and dependency errors.

Retry helps Spring Batch recover from transient errors, while idempotency protects data when an item is reprocessed. When processors stay pure transformations, side effects live inside transactions or idempotent APIs, and retry policies carry explicit bounds, batch pipelines can recover without producing duplicate business outcomes.

