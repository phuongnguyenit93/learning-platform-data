# Composite processor

`CompositeItemProcessor<I, O>` combines multiple `ItemProcessor` instances into a sequential pipeline. Each delegate receives the output of the previous delegate and produces the input for the next one. This organization splits item processing into smaller steps such as validation, normalization, enrichment, and transformation to the output model.

A composite processor only orchestrates the processing chain for a single item. It does not run delegates in parallel by itself, does not write data, and does not create separate transactions. Spring Batch still invokes the composite from the chunk step; exceptions, filtering, retries, skips, and transactions are handled according to the step's policies.

## 1. How does CompositeItemProcessor work?

`CompositeItemProcessor` invokes delegates in the exact configured order. The output of the first delegate becomes the input of the second delegate, continuing through the final delegate.

```text
ItemReader<OrderInput>
        |
        v
CompositeItemProcessor
        |
        +--> validateProcessor
        |       OrderInput -> ValidatedOrder
        |
        +--> normalizeProcessor
        |       ValidatedOrder -> NormalizedOrder
        |
        +--> enrichProcessor
        |       NormalizedOrder -> EnrichedOrder
        |
        v
ItemWriter<EnrichedOrder>
```

Example pipeline separating three responsibilities:

- Validation checks input data and rejects invalid items.
- Normalization standardizes codes, strings, or date formats.
- Enrichment adds reference data or computed values.

The final delegate returns the data type expected by the writer. There is no automatic rollback to an earlier delegate's output.

## 2. Declaring intermediate data types

You should define clear data types between steps. This gives each processor a small contract and shows what processing the data has already undergone.

```java
public record OrderInput(
        String orderId,
        String customerCode,
        BigDecimal amount) {
}

public record ValidatedOrder(
        String orderId,
        String customerCode,
        BigDecimal amount) {
}

public record NormalizedOrder(
        String orderId,
        String customerCode,
        BigDecimal amount) {
}

public record EnrichedOrder(
        String orderId,
        Long customerId,
        BigDecimal amount,
        String riskCategory) {
}
```

The example uses Java records to keep data immutable. With regular classes, constructors, getters, and immutable value objects can be used similarly.

## 3. Writing individual delegate processors

Each delegate implements `ItemProcessor<I, O>`. The `process` method receives an item and returns the next item or `null` to filter the item.

Validation processor:

```java
public class OrderValidationProcessor
        implements ItemProcessor<OrderInput, ValidatedOrder> {

    @Override
    public ValidatedOrder process(OrderInput input) {
        if (input.orderId() == null || input.orderId().isBlank()) {
            throw new InvalidOrderException("orderId is required");
        }
        if (input.amount() == null || input.amount().signum() < 0) {
            throw new InvalidOrderException("amount must be non-negative");
        }

        return new ValidatedOrder(
            input.orderId().trim(),
            input.customerCode(),
            input.amount()
        );
    }
}
```

Normalization processor:

```java
public class OrderNormalizationProcessor
        implements ItemProcessor<ValidatedOrder, NormalizedOrder> {

    @Override
    public NormalizedOrder process(ValidatedOrder order) {
        return new NormalizedOrder(
            order.orderId().toUpperCase(Locale.ROOT),
            order.customerCode().trim().toUpperCase(Locale.ROOT),
            order.amount().setScale(2, RoundingMode.HALF_UP)
        );
    }
}
```

Enrichment processor:

```java
public class OrderEnrichmentProcessor
        implements ItemProcessor<NormalizedOrder, EnrichedOrder> {

    private final CustomerLookup customerLookup;

    public OrderEnrichmentProcessor(CustomerLookup customerLookup) {
        this.customerLookup = customerLookup;
    }

    @Override
    public EnrichedOrder process(NormalizedOrder order) {
        Customer customer = customerLookup.findByCode(order.customerCode());
        if (customer == null) {
            throw new UnknownCustomerException(order.customerCode());
        }

        return new EnrichedOrder(
            order.orderId(),
            customer.id(),
            order.amount(),
            customer.riskCategory()
        );
    }
}
```

Keep lookup, mapping, and validation in clearly named components. When a normalization rule needs to change, only the corresponding delegate needs to be modified or replaced.

## 4. Wiring delegates with CompositeItemProcessorBuilder

In Spring Batch 5, `CompositeItemProcessorBuilder` can be used to declare the delegate chain:

```java
@Bean
CompositeItemProcessor<OrderInput, EnrichedOrder> orderCompositeProcessor(
        OrderValidationProcessor validationProcessor,
        OrderNormalizationProcessor normalizationProcessor,
        OrderEnrichmentProcessor enrichmentProcessor) throws Exception {

    return new CompositeItemProcessorBuilder<OrderInput, EnrichedOrder>()
        .delegates(
            validationProcessor,
            normalizationProcessor,
            enrichmentProcessor
        )
        .build();
}
```

The order in `delegates(...)` is the execution order. In the example above, enrichment receives `NormalizedOrder`, not `OrderInput` or `ValidatedOrder`.

The builder validates basic configuration such as the delegate list. Because the generic type of the delegate list is typically represented using wildcards, the compiler cannot always catch every mismatch between intermediate types. Declare each processor's types explicitly and test the entire chain.

## 5. Using setDelegates without the builder

You can also configure `CompositeItemProcessor` directly:

```java
@Bean
CompositeItemProcessor<OrderInput, EnrichedOrder> orderCompositeProcessor(
        OrderValidationProcessor validationProcessor,
        OrderNormalizationProcessor normalizationProcessor,
        OrderEnrichmentProcessor enrichmentProcessor) throws Exception {

    CompositeItemProcessor<OrderInput, EnrichedOrder> composite =
        new CompositeItemProcessor<>();

    composite.setDelegates(List.of(
        validationProcessor,
        normalizationProcessor,
        enrichmentProcessor
    ));
    composite.afterPropertiesSet();

    return composite;
}
```

`afterPropertiesSet()` verifies that the required configuration has been set. When using the builder, this initialization is handled by the builder.

Do not modify the delegate list while the step is running. The pipeline configuration should remain immutable throughout an execution to avoid different items passing through different chains.

## 6. Connecting the composite processor to a chunk step

The composite processor is passed to the step like a regular `ItemProcessor`:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        CompositeItemProcessor<OrderInput, EnrichedOrder> orderCompositeProcessor,
        ItemWriter<EnrichedOrder> orderWriter) {

    return new StepBuilder("importOrders", jobRepository)
        .<OrderInput, EnrichedOrder>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderCompositeProcessor)
        .writer(orderWriter)
        .build();
}
```

Chunk size and transaction manager are still configured on the step. The composite does not open separate transactions per delegate; delegates execute within the item processing flow of the current chunk.

## 7. Delegate order affects results

Changing delegate order can alter both semantics and the data types being passed.

Valid example:

```text
OrderInput
   -> validate
   -> normalize
   -> enrich
   -> EnrichedOrder
```

Logically incorrect example:

```text
OrderInput
   -> enrich (needs normalized customerCode)
   -> normalize
```

In the incorrect example, the lookup may fail if the customer code contains whitespace or differs in letter case. Steps must be ordered according to data dependencies and business rules.

If an earlier step needs data produced by a later step, a linear pipeline cannot resolve that dependency by arbitrarily reordering steps. Redesign the input/output objects or create a dedicated orchestrating processor.

## 8. Null is the item-filtering signal

Per the `ItemProcessor` contract, returning `null` means the item is filtered and is not forwarded to the writer. In `CompositeItemProcessor`, if a delegate returns `null`, the chain stops for that item; remaining delegates are not called.

Example:

```java
public class IgnoreCancelledOrderProcessor
        implements ItemProcessor<NormalizedOrder, NormalizedOrder> {

    @Override
    public NormalizedOrder process(NormalizedOrder order) {
        if (order.isCancelled()) {
            return null;
        }
        return order;
    }
}
```

Pipeline:

```text
OrderInput
   -> validate
   -> normalize
   -> filterCancelled
         |
         +--> null: stops chain, writer does not receive item
         |
         +--> item: continues to enrich
```

Ensure `null` is only used for intentional filtering. If null represents missing input data or a mapping error, throw an appropriate exception so the step applies its fail/skip/retry policy.

## 9. Distinguishing filtering from exceptions

Filtering and exceptions have different operational meanings:

| Processor behavior | Meaning | Impact in step |
|---|---|---|
| Returns item | Continues pipeline and may reach writer | Increments process count; writer processes item |
| Returns `null` | Item is filtered | Increments filter count; writer does not receive item |
| Throws exception | Item processing failed | Step applies rollback, retry, or skip policy |

Do not return `null` to hide data errors. For example, a missing customer may be an error that needs rejection/auditing, not normal filtering.

## 10. Exceptions from delegates propagate to the step

If a delegate throws an exception, `CompositeItemProcessor` does not invoke subsequent delegates for that item. The exception propagates up to the chunk step for Spring Batch to handle according to its fault-tolerance configuration.

```text
validate -> normalize -> enrich
                         |
                         +--> exception
                               |
                               v
                       chunk fault handling
                         /           \
                      retry         skip/fail
```

Do not catch all exceptions inside a delegate and return `null`. Doing so turns errors into filters and allows the step to complete even though items were lost.

If more context is needed, wrap the exception with the item key and root cause, while avoiding putting sensitive payloads into messages/logs.

## 11. Retry and skip with a composite processor

Fault tolerance is configured on the step, not on individual delegates:

```java
return new StepBuilder("importOrders", jobRepository)
    .<OrderInput, EnrichedOrder>chunk(100, transactionManager)
    .reader(orderReader)
    .processor(orderCompositeProcessor)
    .writer(orderWriter)
    .faultTolerant()
    .retry(TransientCustomerLookupException.class)
    .retryLimit(3)
    .skip(InvalidOrderException.class)
    .skipLimit(50)
    .build();
```

This example retries transient lookup errors and skips classified input errors. Actual exceptions should be chosen based on the cause and semantics of the application.

On retry, the composite may re-run from the beginning for that item; therefore, delegates must avoid non-idempotent side effects. If a delegate sends messages, writes files, or calls APIs, use an outbox/idempotency or move the side effect to a post-commit phase.

Do not retry permanent validation errors such as a missing order ID. Do not skip broad infrastructure errors like database unavailability if continuing with other items makes no sense.

## 12. Each delegate should focus on a single responsibility

A pipeline is easy to maintain when each delegate has a clear purpose:

- Validation: verify required fields, ranges, and item invariants.
- Normalization: standardize formats, codes, and whitespace.
- Enrichment: supplement data from reference data.
- Classification: assign category or routing metadata to the item.
- Mapping: convert to the DTO/entity expected by the writer.

Avoid creating a delegate for every tiny line of code if it makes the pipeline hard to read. Conversely, one giant processor containing many independent steps makes logic hard to test and modify.

Choose boundaries based on nameability, reusability, independent testability, and separate changeability.

## 13. Processors should be stateless when possible

Processors are typically created as Spring singletons. Storing per-item mutable state in fields can cause items or threads to interfere with one another.

Prefer stateless processors:

```java
public class NormalizeCodeProcessor
        implements ItemProcessor<OrderInput, NormalizedOrder> {

    @Override
    public NormalizedOrder process(OrderInput input) {
        return new NormalizedOrder(
            input.orderId().trim().toUpperCase(Locale.ROOT),
            input.customerCode().trim().toUpperCase(Locale.ROOT),
            input.amount()
        );
    }
}
```

If caching is needed, use a thread-safe structure or a cache with a clear lifecycle/eviction policy. Do not use `currentItem`, `currentIndex` fields, or temporary variables shared across invocations.

## 14. Composite processor does not run in parallel

The composite invokes delegates sequentially within the same `process` call. Three delegates do not run concurrently simply because they are listed together.

If concurrency is required, that is a step-architecture decision such as a multi-threaded step or partitioning. In that case, you must verify thread safety for every delegate and every service they use.

Do not use a composite as a way to parallelize enrichment. If two independent tasks need to run in parallel, consider a specialized processor using a bounded executor with timeouts, while carefully controlling transaction context, errors, cancellation, and resources.

## 15. Enrichment and database performance

Enrichment delegates often query databases or services. If every item triggers a query, the pipeline can suffer from N+1 lookups and a sharp drop in throughput.

Ways to optimize:

- Cache small, stable reference data in a thread-safe cache.
- Bulk lookup per chunk if the architecture allows.
- Load reference data into a staging table or join in the reader query.
- Use appropriate indexes for lookup keys.
- Set timeouts and classify transient errors for remote lookups.

Do not cache rapidly changing data without an appropriate TTL/version. If enrichment results must be consistent within a job, define a snapshot or version of the reference data.

## 16. Using ValidatingItemProcessor in the chain

Spring Batch provides `ValidatingItemProcessor<T>` to integrate validators into the pipeline. You can use `setFilter(true)` if you want validation failures to become filters per the processor contract; by default, validation failures are normally thrown as exceptions.

Example:

```java
@Bean
ValidatingItemProcessor<OrderInput> orderValidationProcessor(
        Validator<OrderInput> validator) {

    ValidatingItemProcessor<OrderInput> processor =
        new ValidatingItemProcessor<>(validator);
    processor.setFilter(false);
    return processor;
}
```

Only enable filtering when a validation failure genuinely means the item is excluded by business rules. If you need to reject records and save the reason, use exception/skip listeners or a dedicated reject flow.

## 17. Composite processor vs. ClassifierCompositeItemProcessor

The two components serve different goals:

| Component | Behavior | When to use |
|---|---|---|
| `CompositeItemProcessor` | Calls all delegates in order, passing output to the next delegate | Multiple sequential processing steps for the same item |
| `ClassifierCompositeItemProcessor` | Selects one processor for the item based on a classifier | Different item types follow different processing branches |

Chain example:

```text
input -> validate -> normalize -> enrich -> output
```

Routing example:

```text
                 +--> priorityProcessor --+
input -> classify|                       +--> output
                 +--> standardProcessor -+
```

Do not use `CompositeItemProcessor` to simulate routing with conditional delegates that return the item unchanged. If only one branch needs to run, a classifier composite expresses the intent much more clearly.

## 18. Combining routing and chaining

You can use a classifier to select an appropriate composite pipeline based on item type. Each branch is its own delegate chain.

Conceptual example:

```text
OrderInput
   |
   v
Classifier
   |
   +--> Retail pipeline: validate -> normalize -> enrich retail
   |
   +--> Wholesale pipeline: validate -> normalize -> enrich wholesale
   |
   +--> Internal pipeline: validate -> map internal
```

Keep a common input/output type at branch boundaries so the writer can receive a unified contract. If branches return different types, add a final mapping step to convert to a shared output type.

## 19. Testing each delegate independently

Each processor should have unit tests for its own contract before testing the chain.

Normalization test example:

```java
@Test
void normalizesOrderCodes() {
    var processor = new OrderNormalizationProcessor();
    var input = new ValidatedOrder(
        " ord-1 ", " cust-a ", new BigDecimal("10"));

    NormalizedOrder result = processor.process(input);

    assertThat(result.orderId()).isEqualTo("ORD-1");
    assertThat(result.customerCode()).isEqualTo("CUST-A");
    assertThat(result.amount()).isEqualByComparingTo("10.00");
}
```

Isolated tests help pinpoint whether a bug lies in validation, normalization, or enrichment rather than only knowing the composite returned the wrong result.

## 20. Testing delegate order in the composite

Chain tests should verify the final output and delegate invocation order. Real processors or mocks with `InOrder` can be used.

```java
@Test
void invokesDelegatesInConfiguredOrder() throws Exception {
    ItemProcessor<OrderInput, ValidatedOrder> validate =
        input -> new ValidatedOrder(
            input.orderId(), input.customerCode(), input.amount());

    ItemProcessor<ValidatedOrder, NormalizedOrder> normalize =
        order -> new NormalizedOrder(
            order.orderId().toUpperCase(Locale.ROOT),
            order.customerCode(),
            order.amount());

    ItemProcessor<NormalizedOrder, EnrichedOrder> enrich =
        order -> new EnrichedOrder(
            order.orderId(), 42L, order.amount(), "LOW");

    CompositeItemProcessor<OrderInput, EnrichedOrder> composite =
        new CompositeItemProcessorBuilder<OrderInput, EnrichedOrder>()
            .delegates(validate, normalize, enrich)
            .build();

    EnrichedOrder result = composite.process(
        new OrderInput("ord-1", "C-1", new BigDecimal("5.00")));

    assertThat(result.orderId()).isEqualTo("ORD-1");
    assertThat(result.customerId()).isEqualTo(42L);
}
```

The test above uses lambdas to focus on passing outputs between steps. In thorough tests, individual delegates can be mocked to verify call order and received arguments.

## 21. Testing null short-circuiting

Verify that when a delegate returns `null`, subsequent delegates are not called and the composite returns `null`.

```java
@Test
void stopsChainWhenDelegateFiltersItem() throws Exception {
    AtomicBoolean laterDelegateCalled = new AtomicBoolean(false);

    ItemProcessor<OrderInput, ValidatedOrder> filter = input -> null;
    ItemProcessor<ValidatedOrder, EnrichedOrder> later = order -> {
        laterDelegateCalled.set(true);
        return new EnrichedOrder(
            order.orderId(), 1L, order.amount(), "LOW");
    };

    CompositeItemProcessor<OrderInput, EnrichedOrder> composite =
        new CompositeItemProcessorBuilder<OrderInput, EnrichedOrder>()
            .delegates(filter, later)
            .build();

    assertThat(composite.process(
        new OrderInput("O-1", "C-1", BigDecimal.ONE)))
        .isNull();
    assertThat(laterDelegateCalled).isFalse();
}
```

This test guarantees filtering does not accidentally invoke downstream enrichment or side effects.

## 22. Testing exception propagation

If a delegate throws an exception, the composite must propagate the error to the caller and not invoke later steps.

```java
@Test
void stopsChainWhenDelegateThrows() {
    ItemProcessor<OrderInput, ValidatedOrder> failing = input -> {
        throw new InvalidOrderException("invalid order");
    };

    ItemProcessor<ValidatedOrder, EnrichedOrder> later = order -> {
        throw new AssertionError("must not be called");
    };

    CompositeItemProcessor<OrderInput, EnrichedOrder> composite =
        new CompositeItemProcessorBuilder<OrderInput, EnrichedOrder>()
            .delegates(failing, later)
            .build();

    assertThatThrownBy(() -> composite.process(
        new OrderInput("O-1", "C-1", BigDecimal.ONE)))
        .isInstanceOf(InvalidOrderException.class);
}
```

In integration tests, verify this exception is properly classified by the step as fail, skip, or retry per configuration.

## 23. Testing the composite in a step

Composite unit tests do not verify filter counts, skip counts, or step transactions. Have integration tests with a real or controlled-fixture reader, composite processor, and writer.

Useful assertions:

- Number of items read.
- Number of items filtered because the processor returned `null`.
- Number of items written.
- Number of skipped items and exception causes.
- Final output data.
- Number of times the enrichment delegate was invoked during retries.
- Transaction rollback when the writer fails.

For instance, a filtered item should not appear in writer output, while valid items must traverse all delegates.

## 24. Delegates with side effects and retries

Ideally, processors only transform items. If a delegate sends emails, writes independently to a database, or calls an API, retries can trigger the side effect multiple times.

For example, enrichment calling a partner service might time out after the partner already processed the request. Spring Batch retries the item, and the same request may be sent again.

Safeguards:

- Use an idempotency key based on the item's business ID.
- Prefer reading data and computing in the processor, letting the writer perform transactional changes.
- Use an outbox to record events in the same database transaction and publish after commit.
- Classify timeouts/exceptions to decide whether retrying is safe.
- Keep retry counts and backoff bounded.

Do not assume a chunk transaction can roll back sent HTTP requests or published messages.

## 25. Composite processor and partitioning

When a step runs partitioned or multi-threaded, the same processor bean may be called from multiple threads depending on configuration. The composite does not automatically synchronize delegate state.

Ensure:

- Delegates are stateless or thread-safe.
- Shared caches are thread-safe and have clear update policies.
- Current items are not stored in mutable fields.
- Non-thread-safe `EntityManager`, JDBC Connection, or parsers are not shared.
- Lookup services have appropriate connection pools and timeouts.

If a delegate needs per-worker state, design appropriate scope and lifecycle; do not place partition state in a singleton processor.

## 26. Logging and pipeline observability

When a chain has multiple steps, logs should indicate the item key and the failing processing step. Avoid logging full payloads if they contain personal or sensitive data.

Separate metrics/counters can be used for:

- Number of items entering validation and number rejected.
- Number of items normalized.
- Successful/failed lookup counts.
- Average duration of each delegate.
- Retry/skip counts by exception category.

Do not add side effects inside processors solely for counting if it causes metrics to double-count on retries. Use metrics with clear semantics or lifecycle-appropriate listeners.

## 27. Common pitfalls

| Pitfall | Consequence | How to handle |
|---|---|---|
| Misconfigured delegate order | Downstream steps receive unnormalized data | Order by dependencies and test the chain |
| Intermediate type mismatch | Compile errors bypassed or runtime `ClassCastException` | Declare concrete generics for each delegate |
| Delegate returns `null` unintentionally | Item is filtered and never reaches writer | Only use null for intentional filtering |
| Catching exceptions and returning null | Data/infrastructure errors are masked as filters | Throw clearly classified exceptions |
| One processor doing too much | Hard to test and modify | Split by meaningful responsibilities |
| Delegate holds mutable state | Item output depends on order or thread | Use stateless/thread-safe processors |
| One query lookup per item | N+1 problem and low throughput | Bulk lookup, cache, or join |
| Non-idempotent side effects in processor | Retries produce duplicate actions | Outbox/idempotency or move side effects |
| Using a chain when only one branch is needed | Executes unrelated steps | Use a classifier composite |
| Thinking composite runs in parallel | Misunderstanding concurrency | Composite runs delegates sequentially |
| Testing only composite output | Fails to catch downstream delegates running after null/error | Test short-circuiting and exceptions |

## 28. Composite processor design checklist

When designing a pipeline, determine:

1. What are the processor's input type and final output type?
2. Which business steps can be separated into independent responsibilities?
3. What are the intermediate data types between each delegate?
4. What data dependencies dictate delegate order?
5. Which cases filter with `null`, and which must throw exceptions?
6. Which delegates perform I/O, lookups, or side effects?
7. Which delegates can be re-invoked on retry, and are side effects idempotent?
8. Can the processor be called concurrently in a partitioned/multi-threaded step?
9. Do all steps need to be chained, or should a classifier pick one branch?
10. Do unit tests check order, null, and exceptions, and do integration tests verify step counters/output?

## Conclusion

`CompositeItemProcessor<I, O>` chains multiple `ItemProcessor` instances into a sequential pipeline. Each delegate receives the previous step's output; a delegate returning `null` filters the item and stops the chain, while exceptions propagate to the step to apply retry/skip/rollback policies.

Declare intermediate data types explicitly, keep each delegate focused on a single responsibility, configure order intentionally, and use `CompositeItemProcessorBuilder` in Spring Batch 5. A composite does not execute in parallel and does not automatically make side effects idempotent. Test each delegate, the full chain, null short-circuiting, exception propagation, and step behavior to ensure the pipeline works correctly.
