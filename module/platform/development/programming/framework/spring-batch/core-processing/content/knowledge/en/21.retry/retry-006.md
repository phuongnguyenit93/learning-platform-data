# Retry in read, process, and write

In Spring Batch, retry allows a chunk Step to re-attempt an operation when the reader, processor, or writer encounters a recoverable error. For example, a database query may temporarily hit a deadlock, a reference service may time out while processing an item, or the writer may experience a brief connection error. If the error is classified as retryable, the framework can re-execute the operation according to configured limits and backoff policies.

Retry is especially useful for transient errors. It cannot fix permanently invalid input data, programming bugs, or misconfiguration. Those errors must be skipped per business rules or cause the Step to fail. To use retry safely, you must understand which component is re-invoked, which transactions roll back, and which side effects might repeat.

## 1. Where does retry fit in chunk processing?

A chunk Step runs a cycle of reading, processing, and writing multiple items. Exceptions can occur in each phase:

```text
ItemReader
    |
    +-- Transient error --> Retry read
    |
    v
ItemProcessor
    |
    +-- Transient error --> Retry process
    |
    v
ItemWriter
    |
    +-- Transient error --> Retry write
    |
    v
Commit chunk
```

Retry is a fault-tolerance mechanism at the operation/item level within a chunk Step. It does not mean Spring Batch restarts the entire Job. If retry succeeds, the Step continues processing the chunk along the normal path. If retries are exhausted, the exception can be handed off to the skip policy if skippable; otherwise, the Step can fail.

| Phase | Example transient error | Operation that may be retried |
|---|---|---|
| Read | Timeout fetching data from a database or API | `ItemReader.read()` |
| Process | Timeout calling a reference data lookup service | `ItemProcessor.process(item)` |
| Write | Deadlock or database connection error when writing | `ItemWriter.write(chunk)` or write subset re-handled by the framework |

Each phase has distinct characteristics. Read retry requires a reader that can safely resume; process retry may invoke the processor again with the same item; write retry may invoke the writer again with the chunk or relevant item subset. Therefore, never assume a single retry always corresponds to one identical item across all three phases.

## 2. Basic retry configuration for a Step

In Spring Batch 5, retry is configured on a fault-tolerant chunk Step using `.retry(...)` and `.retryLimit(...)`:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(200, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .build();
}
```

In this example, `TransientDataAccessException` is the error group permitted to retry. `retryLimit` bounds the number of retries per the builder's policy. When choosing values, verify the semantics of your Spring Batch/Spring Retry version and factor backoff time into the Job's SLA.

Not every exception is retried. Exceptions outside the retry configuration follow the corresponding error policy, typically failing the Step unless skipped or handled by another policy.

### Excluding exceptions from retry

You can configure exceptions not to retry using `.noRetry(...)`:

```java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retryLimit(3)
.noRetry(InvalidOrderException.class)
```

In this example, transient data access errors may be retried, whereas order data errors are not retried. If an item lacks an order ID, waiting longer will not make the data valid; that error should be skipped or fail the Step per business rules.

### Using a custom RetryPolicy

When different exception types need different retry limits, you can supply a custom `RetryPolicy` instead of relying only on a single shared `.retryLimit(...)`. Spring Retry includes policies such as `SimpleRetryPolicy`, `NeverRetryPolicy`, `TimeoutRetryPolicy`, and `ExceptionClassifierRetryPolicy`.

A custom policy should have a safe default: unknown exceptions must not be retried automatically. When using `.retryPolicy(...)`, let that policy govern retry behavior and avoid mixing multiple `.retry(...)`/`.retryLimit(...)` rules without understanding how the builder applies configuration.

## 3. Retry in ItemReader

`ItemReader.read()` retrieves the next item from the data source. Read retry is appropriate when reading fails due to transient errors such as connection timeouts or query deadlocks.

Example of a reader querying a data service:

```java
public class RemoteOrderReader implements ItemReader<OrderInput> {

    private final OrderSourceClient client;
    private Iterator<OrderInput> currentPage;

    public RemoteOrderReader(OrderSourceClient client) {
        this.client = client;
    }

    @Override
    public OrderInput read() {
        if (currentPage == null || !currentPage.hasNext()) {
            List<OrderInput> nextPage = client.fetchNextPage();
            if (nextPage.isEmpty()) {
                return null;
            }
            currentPage = nextPage.iterator();
        }

        return currentPage.next();
    }
}
```

If `fetchNextPage()` throws a timeout exception configured for retry, Spring Batch can re-invoke the read operation. The reader must ensure a failed call does not lose position or skip a page of data.

### Points to watch when retrying reads

- If the read request was processed by the server but the response timed out, re-invoking might fetch a different page if the API uses an unstable cursor.
- If the reader increments offset or cursor before confirming data receipt, an exception can cause the reader to skip data.
- Readers may hold state in memory; clarify whether state is updated before or after a successful read.
- For non-transactional sources, a database rollback does not automatically rewind the read source to its prior position.
- For readers supporting `ItemStream`, checkpoints should be persisted via `ExecutionContext` to restart from the last committed position.

### Read retry and buffering

In chunk processing, Spring Batch generally buffers read items to support rollback and chunk reprocessing. This prevents the framework from necessarily re-reading the entire source whenever a writer transaction rolls back. However, errors occurring directly inside `read()` before an item is produced behave differently: the reader must support re-invoking the read operation without losing data.

For transactional queue sources, `readerIsTransactionalQueue()` can be configured when the reader consumes from a queue where transaction rollback redelivers messages to the source. Enable this only when the source and reader genuinely have transactional queue semantics; do not use this option for ordinary files or APIs.

## 4. Retry in ItemProcessor

`ItemProcessor.process(item)` receives a read item and returns an output item. Process retry fits when the processor depends on a service or resource that may be temporarily unavailable.

For example, a processor needs to look up tax rates from an external service:

```java
public class TaxProcessor implements ItemProcessor<OrderInput, Order> {

    private final TaxRateClient taxRateClient;

    public TaxProcessor(TaxRateClient taxRateClient) {
        this.taxRateClient = taxRateClient;
    }

    @Override
    public Order process(OrderInput input) {
        BigDecimal rate = taxRateClient.getRate(input.region());
        BigDecimal tax = input.amount().multiply(rate);

        return new Order(
                input.orderId(),
                input.amount(),
                tax);
    }
}
```

If `getRate()` throws a transient timeout exception configured for retry, the processor can be called again with the item under processing. Once the service recovers, the processor can return the result and the item moves on to the writer.

### Process retry and safe repetition

The processor can be called multiple times for the same item during retry or rollback. Thus, keep the processor as free of side effects as possible:

- Avoid sending emails inside `process`.
- Avoid writing business data directly to another system outside the Step's transaction.
- Avoid incrementing external business counters on every processor invocation.
- Do not generate a new random business ID on every retry if the ID must remain stable.
- If calling an API with side effects, use an idempotency key or move the work to an outbox/separate Step.

If the processor only validates, computes, and builds output objects, repeated invocation is usually safer. If the processor has side effects, clearly define how to detect whether a request was already executed.

### Distinguishing data errors from transient errors

An item with a negative amount is a permanent data error; retrying will not make the amount valid. Conversely, a timed-out exchange-rate lookup may succeed on the next try. Use distinct exception types to separate the two cases:

```java
if (input.amount().signum() <= 0) {
    throw new InvalidOrderException("Amount must be positive");
}

BigDecimal rate = taxRateClient.getRate(input.region());
```

`InvalidOrderException` can be configured to skip or fail; timeout exceptions from the client can be retried.

## 5. Retry in ItemWriter

`ItemWriter` receives the chunk's output items and writes them to the target system. Write retry fits when write failures are recoverable, such as deadlocks, lock timeouts, or transient database connection errors.

Example batch writer:

```java
@Bean
JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO orders (order_id, amount, tax)
                    VALUES (:orderId, :amount, :tax)
                    """)
            .beanMapped()
            .build();
}
```

If the database hits a deadlock during writes and the exception is configured for retry, Spring Batch can roll back the chunk transaction and retry the write operation under fault-tolerance mechanics.

### The writer receives a chunk, not a single item

In Spring Batch 5, `ItemWriter` receives a `Chunk` of output items. Therefore, a write failure may relate to any item in the chunk or to the target resource itself.

```java
public class AuditWriter implements ItemWriter<Order> {

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            // Write the orders in the chunk.
        }
    }
}
```

During write retry or write skip, the framework may roll back and re-invoke the writer. In some write-skip scenarios, Spring Batch may scan the chunk by attempting smaller groups or individual items to isolate the failing item. Consequently, never assume the writer is invoked only once per chunk.

### Write retry and transactions

If the writer writes through the Step's datasource and transaction manager, uncommitted changes can roll back when the writer throws an exception. On retry, the writer can re-execute the operation in a new transaction or along the framework-managed retry path.

This does not automatically protect resources outside the transaction:

- An HTTP request may have been processed by the server even though the client timed out.
- Sent emails cannot be recalled by a database rollback.
- Files written or renamed do not automatically revert to their prior state.
- Published messages may remain even after a JDBC rollback.

If the writer performs non-transactional side effects, use idempotency keys, outbox/inbox patterns, or reconciliation procedures to prevent duplicate effects.

## 6. Configuring retry with backoff

If retries happen immediately, the application may send consecutive requests into an already overloaded system. Backoff introduces a wait interval between attempts so resources have time to recover.

Example using exponential backoff:

```java
@Bean
BackOffPolicy retryBackOffPolicy() {
    ExponentialBackOffPolicy policy = new ExponentialBackOffPolicy();
    policy.setInitialInterval(500L);
    policy.setMultiplier(2.0);
    policy.setMaxInterval(5_000L);
    return policy;
}

@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter,
        BackOffPolicy retryBackOffPolicy) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(200, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(4)
            .backOffPolicy(retryBackOffPolicy)
            .build();
}
```

In this example, the wait interval starts at 500 ms, grows by a factor of 2, and is capped at 5 seconds. Values should be chosen based on service timeouts, Job SLA, and potential overload levels.

Backoff does not replace timeouts. If a request hangs for 10 minutes, backoff only starts after the request terminates in failure. Configure connect/read/query timeouts on the HTTP client, JDBC driver, or corresponding service.

## 7. RetryLimit and execution counts

`retryLimit` limits retries for configured exceptions. When choosing a limit, distinguish:

- The initial invocation.
- Retry attempts after prior failures.
- Total backoff wait duration.
- Time spent by the reader/processor/writer itself on each call.

Exact limit semantics must be understood according to the Spring Batch/Spring Retry API in use. Some policies express `maxAttempts` including the initial call, whereas the Spring Batch builder may describe retry limit as the number of retries. Do not calculate total time or request counts from a single number without verifying how the builder constructs the policy.

For example, if an operation takes 2 seconds per call and has multiple backoff waits, total duration can far exceed 2 seconds. Compute the worst-case time per item/chunk and ensure the Job timeout/SLA accommodates it.

## 8. Combining retry and skip

Retry and skip can be configured together:

- Retry errors capable of self-recovery.
- If retrying fails, skip the item if that exception is also skippable and the skip limit has not been reached.
- If the exception is not skipped or exceeds the skip limit, the Step fails.

Example:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(200, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skip(FlatFileParseException.class)
        .skipLimit(50)
        .build();
```

In this example, transient data access errors are retried. Order data errors and CSV line-parsing errors are skipped within limits. Since database errors are not in the skip policy, retry exhaustion causes the Step to fail.

Do not configure the same exception as both retryable and skippable without clarifying the intended final outcome. In some scenarios, you want to retry a transient error first and skip only after exhausting retries; in others, that error should fail the Step. Test with real exceptions and the policy of your specific version.

## 9. Retry and skip are not the same as filter

Filtering is a business decision in the processor: returning `null` excludes a valid item from the writer. Retrying re-attempts an operation that threw an exception. Skipping bypasses an item due to an exception permitted to be ignored.

| Mechanism | Trigger | Purpose | Counter/observability |
|---|---|---|---|
| Retry | Exception matching retry policy | Re-attempt recoverable errors | RetryContext/RetryListener and logs/metrics. |
| Skip | Exception matching skip policy within limit | Bypass allowed faulty items | Read/process/write skip counts and SkipListener. |
| Filter | Processor returns `null` | Exclude valid items outside output scope | `filterCount`. |

Do not retry an item just because it does not need to be written; use filtering. Do not skip transient errors if recovery is possible and the data must be processed; consider retry. Do not use retry to handle permanent data errors.

## 10. Retry, rollback, and chunk transactions

A chunk usually executes inside a transaction. When an exception occurs, the current transaction may roll back according to rollback rules and Step configuration. Then the framework applies retry or skip per policy.

Key points to understand:

- Previously committed chunks remain intact.
- The current chunk may roll back before the operation is retried.
- The processor may be re-invoked for the same item.
- The writer may be re-invoked with the chunk or relevant item group.
- The reader may be re-invoked if the failure happens during read; previously read items are typically buffered to support rollback.
- Side effects outside the transaction do not automatically roll back.

Do not treat retry as rolling back the entire Job. Retry only handles operations/chunks under fault-tolerance mechanics. If the Step fails after exhausting retries, the Job can be restarted using committed metadata and checkpoints.

### noRollback is not retry

Configuring `.noRollback(SomeException.class)` only alters rollback behavior for the specified exception. It does not automatically retry and does not automatically skip the item.

Use `noRollback` only when the transaction can safely remain consistent after the exception. If the writer already wrote partial data and the exception indicates the transaction is no longer safe, suppressing rollback can leave inconsistent state behind.

## 11. Stateful retry, reader buffering, and checkpoints

Retrying an operation within a chunk and restarting after a process stops are two distinct mechanisms:

- **Retry within the current execution:** the framework re-attempts the operation after an exception per the retry policy.
- **Job/Step restart:** Spring Batch creates a new JobExecution for the same JobInstance and restores checkpoints saved in ExecutionContext if supported by the reader/writer.

`RetryContext` holds transient state for a retry operation. `ExecutionContext` stores durable checkpoints for the Job/Step. Do not use retry count as a checkpoint, and do not use ExecutionContext to replace a retry policy.

Readers/writers implementing `ItemStream` can use `open`, `update`, and `close` to restore/save state. For paginated readers, store a cursor or the last committed key; for file readers, use a stable read position. If the source changes ordering between runs and restarts, offset-based checkpoints can lead to duplicate or missed items.

## 12. RetryListener for observing attempts

Spring Retry's `RetryListener` can record the lifecycle of a retry operation through the `open`, `onError`, and `close` callbacks.

Example listener logging exceptions and retry counts:

```java
public class BatchRetryListener implements RetryListener {

    private static final Logger log =
            LoggerFactory.getLogger(BatchRetryListener.class);

    @Override
    public <T, E extends Throwable> boolean open(
            RetryContext context,
            RetryCallback<T, E> callback) {
        return true;
    }

    @Override
    public <T, E extends Throwable> void onError(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {
        log.warn("Retry count={}, exceptionType={}",
                context.getRetryCount(),
                throwable.getClass().getSimpleName());
    }

    @Override
    public <T, E extends Throwable> void close(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {
        if (throwable != null) {
            log.error("Retry operation ended with failure", throwable);
        }
    }
}
```

Register the listener on a fault-tolerant Step builder using `.listener(retryListener)` per the API of your Spring Batch/Spring Retry version. Listeners observe retries; they do not decide whether an exception is retried.

For concurrent Jobs, a singleton listener must be thread-safe. Do not store per-item retry counts in shared mutable fields; use `RetryContext` and thread-safe metrics. Do not write sensitive payloads to logs.

## 13. Choosing retryable exceptions

An exception suitable for retry typically exhibits these traits:

- Likely to recover on its own after some time.
- The operation can be re-executed without corrupting data.
- Clear timeouts and backoff are in place.
- Bounded retries prevent infinite loops.
- Observable and investigable if retries fail.

Examples commonly considered:

- Database deadlock.
- Lock acquisition timeout.
- Brief connection glitches.
- HTTP 429 or 5xx per service policy.
- Timeouts on idempotent lookup services.

Examples usually not retried by default:

- Data missing required fields.
- Unparseable dates or monetary amounts.
- Missing required input file.
- Configuration errors or permanent access-denied errors.
- Unexpected programming bugs such as `NullPointerException`.

Classification should be based on actual root causes. For instance, HTTP 429 typically needs backoff and honoring `Retry-After`; HTTP 400 due to an invalid payload normally should not be retried. An HTTP 500 might be transient, yet it can also reflect a server-side business failure.

## 14. Idempotency when retrying read, process, and write

Retry can invoke operations again. Idempotency is especially critical when operations produce side effects.

### Reader

The reader must re-read the exact item after an error. With paginated APIs, use stable cursors or request IDs; avoid advancing page/offset before receiving and confirming data successfully.

### Processor

The processor should favor pure computation. If calling an API with side effects, use an idempotency key bound to the business key and operation so repeated requests do not create new outcomes.

### Writer

The writer may be re-invoked. For databases, use unique business keys, upserts, or appropriate status checks. For messages/APIs, use outbox/inbox patterns or idempotency keys. Do not rely on JDBC transactions to roll back an external system request.

Example API accepting an idempotency key:

```java
paymentClient.charge(
        order.orderId(),
        order.amount(),
        "charge-order-" + order.orderId());
```

This is an illustrative example; the target system must actually support idempotency keys and persist results under that key. Merely sending a header/key that the API ignores provides no deduplication guarantee.

## 15. Retry and concurrency

When partitioning or multi-threaded Steps run concurrently, multiple items may retry at the same time. Consider:

- Total retry requests can spike sharply when a service degrades.
- Backoff helps spread load, but does not replace circuit breakers or rate limiters.
- Readers/processors/writers must be thread-safe according to how the Step uses them.
- RetryListeners and metrics must support concurrent access.
- Connection pools must suffice for worker counts without exceeding database capacity.
- Avoid holding locks or transactions open during backoff if the configuration/retry path keeps transactions active.

In some configurations, the chunk transaction rolls back and retry runs in a new transaction; in other execution paths, transaction details depend on the retry policy and transaction attributes. Measure transaction duration and test deadlocks/timeouts in a production-like environment.

## 16. Testing retry for each phase

Unit-testing readers, processors, and writers individually helps confirm exception behavior. Step-level integration tests should verify Spring Batch actually applies retry policies, transactions, and skips properly.

### Read retry

- Reader throws a transient exception on the first call and returns the item on the next.
- Reader does not skip a cursor/page after a failed read.
- When retries are exhausted, the Step ends in the status dictated by policy.
- Restart resumes from committed checkpoints.

### Process retry

- Processor throws a transient exception and then succeeds on a subsequent call.
- Processor receives the exact same item again.
- Permanent data errors are not unintentionally retried.
- Side effects are not duplicated.

### Write retry

- Writer throws a deadlock/timeout and then succeeds on a subsequent call.
- Transaction rolls back partially written data before retrying.
- Writer does not create duplicates when re-invoked.
- When retries are exhausted, skips or fails per policy.

### Verifying backoff and listeners

- Backoff is applied between attempts as configured.
- RetryListener receives callbacks following the proper lifecycle.
- Retry counts and exceptions are recorded accurately.
- Listeners are thread-safe when multiple workers are active.

## 17. Common mistakes

### Retrying permanent data errors

An item missing an ID or having invalid format will fail again on the next attempt. Use skip or fail per business rules instead of retry.

### Retrying all exceptions

Retrying `Exception.class` can repeat programming bugs, configuration errors, or unrecoverable failures. Select only exception types identified as transient.

### Omitting retry limits

Unbounded retries can keep a Job from finishing and hold resources too long. Always set limits and monitor retry exhaustion.

### Immediate continuous retries

No backoff can overload the target system further. Use fixed or exponential backoff tailored to service characteristics.

### Assuming the writer is invoked only once

Write retries or write skips can cause the writer to be re-invoked. Writers need suitable transactions or idempotency.

### Processors causing side effects

The processor can re-run for the same item. Avoid sending emails, publishing messages, or writing to external systems without deduplication.

### Confusing retry with Job restart

Retry handles exceptions within the current execution. Restart creates a new JobExecution and restores saved checkpoints. The two mechanisms have different lifecycles and metadata.

### Overlapping retry and skip configurations without testing

Once retries are exhausted, an exception may be skipped if included in the skip policy; otherwise, the Step fails. Clarify desired behavior and test boundary conditions.

### Thinking backoff is a timeout

Backoff only waits between attempts. It does not cancel a hung I/O call. Configure separate timeouts for JDBC, HTTP clients, and data sources.

## 18. Process for implementing retry in read, process, and write

When building a fault-tolerant chunk Step, you can follow this sequence:

1. List errors that may occur in the reader, processor, and writer.
2. Classify permanent data errors, transient errors, and fatal errors.
3. Choose specific exception types for `.retry(...)`.
4. Set a retry limit based on SLA and service recovery characteristics.
5. Configure backoff if immediate retries could generate heavy load.
6. Confirm the reader does not lose items on read retry and supports checkpoints on restart.
7. Keep the processor low on side effects and safe under repeated calls.
8. Ensure the writer participates in transactions or has idempotency for non-transactional side effects.
9. Decide whether retry exhaustion skips or fails; configure a separate skip policy if business rules permit.
10. Add a RetryListener/metrics for observability without replacing policy with a listener.
11. Test errors in all three phases, rollbacks, backoff, restarts, and concurrency.

| Phase | Safe retry design |
|---|---|
| Read | Reader can be re-invoked without missing items; stable cursor/checkpoint. |
| Process | Processor focuses on computation; external calls have idempotency and timeouts. |
| Write | Writer tolerates re-invocation; database uses transactions/unique keys, external output uses outbox or idempotency keys. |

## Conclusion

Spring Batch can retry errors in `ItemReader`, `ItemProcessor`, and `ItemWriter` within a fault-tolerant chunk Step. Read retry requires a reader that does not lose position on a failed read; process retry may re-invoke the processor with the same item; write retry may re-invoke the writer with the chunk or relevant item group and requires proper transactions/idempotency. Use `.retry(...)`, `.retryLimit(...)`, `.noRetry(...)`, and `BackOffPolicy` to handle transient errors; use skip for items permitted to be bypassed and fail the Step when continuing is unsafe. Distinguish in-execution retry from Job restart, test each phase, and design any repeatable side effects to be idempotent.
