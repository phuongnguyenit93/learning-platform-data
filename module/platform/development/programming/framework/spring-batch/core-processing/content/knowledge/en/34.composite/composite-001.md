# CompositeItemProcessor

In Spring Batch, `CompositeItemProcessor<I, O>` allows combining multiple small `ItemProcessor`s into a single processor. For each input item, the composite invokes the delegates in the declared order; the output of the previous delegate becomes the input of the next delegate. The final result is passed to the `ItemWriter`.

This pattern fits when a pipeline has multiple independent processing steps, such as normalizing data, validating, transforming into a domain object, and enriching with reference data. Each delegate has a clear responsibility and can be tested and reused independently. The composite coordinates the execution order without merging all logic into one large class.

`CompositeItemProcessor` executes the delegates sequentially for each item. It does not run processors in parallel, does not create separate transactions, and does not replace the step's fault-tolerant policy. If a delegate returns `null`, the item is filtered and the remaining delegates are not called for that item. If a delegate throws an exception, the exception is propagated so the step applies its retry, skip, or fail policy.

## 1. What is CompositeItemProcessor?

`CompositeItemProcessor<I, O>` is an implementation of `ItemProcessor<I, O>`. It holds a list of processor delegates and runs them in order.

For example, an order processing pipeline:

1. Normalize strings and status codes.
2. Validate input data.
3. Convert `OrderInput` to `Order`.
4. Enrich with customer segment.
5. Return `EnrichedOrder` to the writer.

Diagram:

~~~mermaid
flowchart LR
    A[OrderInput] --> B[NormalizeProcessor]
    B --> C[ValidateProcessor]
    C --> D[MapToOrderProcessor]
    D --> E[EnrichOrderProcessor]
    E --> F[EnrichedOrder]
    F --> G[ItemWriter]
~~~

Without a composite, a single class might have to perform all five responsibilities. With a composite, each delegate can focus on one step and have its own input/output contract.

## 2. Principles for Chaining Delegates

The most important condition is that the output type of one delegate must be compatible with the input type of the next delegate.

For example:

| Order | Processor | Input | Output |
|---|---|---|---|
| 1 | `NormalizeOrderProcessor` | `OrderInput` | `OrderInput` |
| 2 | `MapOrderProcessor` | `OrderInput` | `Order` |
| 3 | `EnrichOrderProcessor` | `Order` | `EnrichedOrder` |

The chain has the overall contract `ItemProcessor<OrderInput, EnrichedOrder>`.

The composite does not automatically convert data types. If the first delegate returns `Customer` while the next delegate expects `Order`, the application must redesign the chain or add an appropriate mapping step. Java generics help verify types at many declaration points, but due to type erasure and the generic delegate list, some mismatches may only surface at runtime.

Keep each delegate's type concrete in bean declarations and avoid raw types or unnecessary casts. Delegate names should clearly reflect their input/output or responsibility so readers can easily follow the data flow.

## 3. Writing Small Processor Delegates

Each delegate should do one clearly expressible job. For example, a normalization processor:

~~~java
public class NormalizeOrderProcessor
        implements ItemProcessor<OrderInput, OrderInput> {

    @Override
    public OrderInput process(OrderInput input) {
        return new OrderInput(
                input.orderId() == null
                        ? null : input.orderId().trim(),
                input.customerId() == null
                        ? null : input.customerId().trim(),
                input.amount(),
                input.status() == null
                        ? null : input.status().trim().toUpperCase(Locale.ROOT));
    }
}
~~~

This delegate only normalizes representation. It does not access the database and does not decide whether an order is allowed to be written.

A validation processor:

~~~java
public class ValidateOrderProcessor
        implements ItemProcessor<OrderInput, OrderInput> {

    @Override
    public OrderInput process(OrderInput input) {
        if (input.orderId() == null || input.orderId().isBlank()) {
            throw new InvalidOrderException("orderId is required");
        }
        if (input.customerId() == null || input.customerId().isBlank()) {
            throw new InvalidOrderException("customerId is required");
        }
        if (input.amount() == null || input.amount().signum() < 0) {
            throw new InvalidOrderException("amount must be non-negative");
        }
        return input;
    }
}
~~~

The validation delegate returns the item if valid. When data is invalid, it throws a meaningful exception so the step handles it according to policy. This preserves error details and enables skip/reject configuration if business rules allow it.

A processor for mapping to a domain object:

~~~java
public class MapOrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        return new Order(
                input.orderId(),
                input.customerId(),
                input.amount(),
                OrderStatus.valueOf(input.status()));
    }
}
~~~

An enrichment processor can add reference data:

~~~java
public class EnrichOrderProcessor
        implements ItemProcessor<Order, EnrichedOrder> {

    private final CustomerService customerService;

    public EnrichOrderProcessor(CustomerService customerService) {
        this.customerService = customerService;
    }

    @Override
    public EnrichedOrder process(Order order) {
        Customer customer =
                customerService.getRequired(order.customerId());

        return new EnrichedOrder(
                order,
                customer.segment(),
                customer.region());
    }
}
~~~

The examples above use illustrative records/constructors. Real models can be JavaBeans, records, or domain types suited to the application.

## 4. Configuring CompositeItemProcessor

Each delegate can be declared as a Spring bean and then wired together in a composite bean:

~~~java
@Bean
ItemProcessor<OrderInput, OrderInput> normalizeOrderProcessor() {
    return new NormalizeOrderProcessor();
}

@Bean
ItemProcessor<OrderInput, OrderInput> validateOrderProcessor() {
    return new ValidateOrderProcessor();
}

@Bean
ItemProcessor<OrderInput, Order> mapOrderProcessor() {
    return new MapOrderProcessor();
}

@Bean
ItemProcessor<Order, EnrichedOrder> enrichOrderProcessor(
        CustomerService customerService) {
    return new EnrichOrderProcessor(customerService);
}

@Bean
ItemProcessor<OrderInput, EnrichedOrder> orderProcessor(
        ItemProcessor<OrderInput, OrderInput> normalizeOrderProcessor,
        ItemProcessor<OrderInput, OrderInput> validateOrderProcessor,
        ItemProcessor<OrderInput, Order> mapOrderProcessor,
        ItemProcessor<Order, EnrichedOrder> enrichOrderProcessor)
        throws Exception {

    CompositeItemProcessor<OrderInput, EnrichedOrder> composite =
            new CompositeItemProcessor<>();

    composite.setDelegates(List.of(
            normalizeOrderProcessor,
            validateOrderProcessor,
            mapOrderProcessor,
            enrichOrderProcessor));

    composite.afterPropertiesSet();
    return composite;
}
~~~

`setDelegates` accepts the list of processors in the exact execution order. `afterPropertiesSet()` lets the composite validate required configuration during bean initialization. In the example, the delegates are declared as separate beans so they can inject dependencies, swap implementations, and be unit tested independently.

If multiple beans implement the same generic type, use qualifiers or explicit bean names to prevent Spring from injecting the wrong candidate. You can declare an explicit name:

~~~java
@Bean("normalizeOrderProcessor")
ItemProcessor<OrderInput, OrderInput> normalizeOrderProcessor() {
    return new NormalizeOrderProcessor();
}
~~~

and inject with `@Qualifier("normalizeOrderProcessor")` when disambiguation is needed.

## 5. Wiring the Composite into a Chunk Step

From the step's perspective, a composite is just a regular `ItemProcessor<I, O>`. The reader supplies the chain's input type, and the writer receives the final output type:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, EnrichedOrder> orderProcessor,
        ItemWriter<EnrichedOrder> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, EnrichedOrder>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
~~~

The step does not need to know how many delegates are inside the composite. It only works with the overall `OrderInput` to `EnrichedOrder` contract.

When changing the internals of the chain while keeping the overall input/output unchanged, the reader and writer configurations can stay intact. This is a key benefit of composition.

## 6. How Delegate Order Affects Results

The composite executes delegates in list order. Changing the order can alter results or break type compatibility in the chain.

For example:

- Normalizing before validation lets `" ORD-1 "` be validated as `"ORD-1"`.
- Validation before normalization may reject data with whitespace if rules require clean strings.
- Mapping to the domain object must happen before enrichment if enrichment expects the domain object.
- Enrichment before validation may issue unnecessary queries for items certain to be rejected.

Arrange the chain by data dependencies and processing cost. Cheap checks can be placed early to reject invalid data before calling services or databases. However, do not change the order purely for performance if doing so alters business semantics.

A reference order diagram:

~~~text
Input
  -> normalize representation
  -> validate required fields
  -> map to domain
  -> enrich reference data
  -> output
~~~

## 7. Filtering by Returning null

Per the `ItemProcessor` contract, returning `null` means the item is filtered. In `CompositeItemProcessor`, if a delegate returns `null`, the composite stops the chain for that item and returns `null` to the step. Subsequent delegates are not invoked.

Example of filtering cancelled orders:

~~~java
public class ExcludeCancelledOrderProcessor
        implements ItemProcessor<Order, Order> {

    @Override
    public Order process(Order order) {
        if (order.status() == OrderStatus.CANCELLED) {
            return null;
        }
        return order;
    }
}
~~~

If the filter delegate is placed before enrichment, CANCELLED orders do not trigger extra queries for customer info. If placed after enrichment, the service has already been called before the item is excluded.

Filtering is not skipping:

| Situation | Outcome |
|---|---|
| Delegate returns an object | Item continues to the next delegate |
| Delegate returns `null` | Item is filtered; chain stops |
| Delegate throws an exception | Chain stops on error; step applies retry/skip/fail policy |

Do not return `null` to hide service errors, conversion failures, or corrupted required data. Those cases need an exception and an explicit handling policy.

## 8. Exception Propagation Through the Composite

If a delegate throws an exception, the composite does not turn it into null or decide to skip on its own. The exception propagates out of the `process` call; the fault-tolerant step decides whether to retry, skip, or fail.

For example:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, EnrichedOrder>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TemporaryCustomerServiceException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(20)
        .listener(skipListener)
        .build();
~~~

In the example, validation exceptions are classified as skippable; temporary service errors can be retried within a limit. Make sure the actual exception thrown by the delegate matches the configured type. If a delegate wraps an exception, preserve the cause and configure the policy for the exception type seen by the framework.

Do not catch all exceptions in each delegate and return a default object. That hides errors and can send bad data to the writer.

## 9. Retry and Re-running the Entire Chain

When a fault-tolerant step retries an item, it must be designed so re-invoking the processor does not cause unintended side effects. In a chain, an exception in the fourth delegate can cause earlier delegates to run again on the next attempt.

For example:

1. Normalize delegate succeeds.
2. Validation delegate succeeds.
3. Mapping delegate succeeds.
4. Enrichment delegate calls a service and times out.
5. Step retries the item; composite runs again from the first delegate.

Therefore, delegates before the failure may be invoked multiple times. This is usually safe if they only normalize, validate, or create new objects. It can be dangerous if they write to a database, send messages, or perform non-idempotent operations.

Principles:

- Keep processor delegates pure or performing only safe read operations.
- If a service with side effects must be called, use an idempotency key or move the side effect to the writer/outbox.
- Do not track "item already processed" only in an in-memory field of the delegate.
- Distinguish transient retryable errors from data errors that should not be retried.
- Set retry limits and backoff appropriate to the dependency.

The composite does not create checkpoints between delegates. Checkpoints and transactions belong to the step/chunk lifecycle, not individual links in the chain.

## 10. Choosing Validation and Filter Placement

The placement of validation/filtering affects both cost and data meaning:

| Step | Goal | Usually Reasonable Placement |
|---|---|---|
| Required field checks | Detect unprocessable input | Early, after minimal normalization |
| Enum/code checks | Block unsupported values | Before mapping or right during mapping |
| Simple condition filtering | Exclude items needing no further processing | Before expensive enrichment |
| Reference state checks | Verify data from another system | After lookup keys are available |
| Output normalization | Format data as needed by the writer | Near the end of the chain if output formatting |

There is no single right order for every job. For example, if normalization modifies data used for lookup, it must occur before enrichment. If filtering relies on data only available after enrichment, the filter must be placed after that step.

Document clearly what data each delegate receives, what it returns, and what conditions cause an item to be filtered or throw an exception. This helps maintainers understand why an item did not reach the writer.

## 11. Combining with ValidatingItemProcessor

`ValidatingItemProcessor<T>` is a built-in delegate for running a `Validator<T>`. It can be placed in the chain when the input/output type at that position remains `T`.

For example:

~~~java
@Bean
ItemProcessor<OrderInput, OrderInput> validationProcessor(
        Validator<OrderInput> orderValidator) {

    ValidatingItemProcessor<OrderInput> processor =
            new ValidatingItemProcessor<>(orderValidator);
    return processor;
}
~~~

The composite can combine normalize, validate, and map:

~~~java
composite.setDelegates(List.of(
        normalizeOrderProcessor,
        validationProcessor,
        mapOrderProcessor));
~~~

By default, a validation failure is represented by an exception. If `filter` is configured on `ValidatingItemProcessor`, a validation failure can cause the item to be excluded. Choose behavior based on business rules: invalid data that needs rejection/auditing should usually throw an exception so a listener records the reason; items that normally do not require processing under standard conditions can be filtered.

## 12. Using CompositeItemProcessor with Intermediate Data Types

Delegates do not need to share the same input/output type. A strength of the composite is linking intermediate types:

~~~java
ItemProcessor<RawOrderRow, NormalizedOrderRow>
ItemProcessor<NormalizedOrderRow, ValidatedOrder>
ItemProcessor<ValidatedOrder, EnrichedOrder>
ItemProcessor<EnrichedOrder, OrderEntity>
~~~

Overall contract:

~~~java
ItemProcessor<RawOrderRow, OrderEntity>
~~~

Each intermediate type should clearly express the data state. For example, `NormalizedOrderRow` means strings have been normalized; `ValidatedOrder` means basic conditions have been checked. This naming reduces passing around a generic DTO with many nullable fields where it is unclear which fields are ready.

There is no need to create an intermediate class for every single-line transformation. Only create a new type when it clarifies boundaries or data invariants. For small transformations that do not change the contract, you can keep the same input/output type.

## 13. CompositeItemProcessor is Not a Branching Router

The composite executes all delegates in order for every item, unless a delegate returns null or throws an exception. It does not pick a single delegate based on item type.

If you need to choose a processor by record type, use a classifier such as `ClassifierCompositeItemProcessor` or write a processor that dispatches by data type. For example:

~~~text
ImportRecord
  -> CustomerRecord: CustomerProcessor
  -> OrderRecord: OrderProcessor
  -> PaymentRecord: PaymentProcessor
~~~

After type-specific processing, another composite can be used inside each branch if that branch also has multiple sequential steps.

Do not use a composite just to simulate if/else with delegates returning null. That makes the flow hard to follow and can cause many delegates to run unnecessarily.

## 14. CompositeItemProcessor Does Not Run in Parallel

The name "composite" only refers to composing processors; it does not mean delegates execute concurrently. For a single item, the call order is sequential:

~~~text
delegate 1 -> delegate 2 -> delegate 3 -> output
~~~

If the second delegate needs the result of the first, sequential execution is mandatory. If the goal is higher throughput, concurrency is configured at the step/partition/flow level via TaskExecutor or partitioning, not by changing the delegate list.

When a step runs on multiple threads, multiple items can pass through the same composite concurrently. Therefore, the composite and shared delegates must be safe for concurrent invocation. Do not store mutable current items or per-invocation state in singleton fields.

## 15. Thread Safety of the Composite and Delegates

The composite mainly holds a list of delegates and calls them in order. However, that does not automatically make the delegates thread-safe. If the same composite bean is called by multiple workers, each delegate may also be called concurrently.

Prefer:

- Stateless delegates using local variables inside `process`.
- Dependencies that read data safely and use per-thread connections/transactions.
- Immutable configuration after bean initialization.
- Avoiding `currentItem`, `currentBatchId`, or shared mutable buffers in fields.
- If partition-specific state is needed, passing it via StepExecutionContext and creating an appropriate target with StepScope.

StepScope is tied to StepExecution, which does not mean a new instance per chunk thread in a multi-threaded step. If a target processor of the same step is invoked concurrently, it must still be thread-safe. With partitioning, each worker has its own StepExecution, so StepScope is generally better suited for worker-owned state.

## 16. Side Effects and Idempotency

A delegate can be invoked again during chunk rollback, retry, or restart. Therefore, avoid irreversible side effects inside `process`.

Unsafe example:

~~~java
public Order process(OrderInput input) {
    paymentGateway.charge(input.paymentToken(), input.amount());
    return mapToOrder(input);
}
~~~

If this delegate succeeds but a subsequent delegate throws an exception, the step may retry the entire item. The charge command could be sent again.

Safer design:

1. Delegates validate, normalize, and build commands.
2. The writer writes data or outbox records inside the transaction.
3. A dispatcher sends external effects after commit.
4. The external API receives a stable idempotency key to prevent duplicates.
5. A reconciliation process handles cases where external call outcomes are ambiguous.

A delegate calling a read-only service is usually lower risk, but still needs timeouts, retry limits, and handling for changing data states.

## 17. Performance of a Processor Chain

Each item passes through each delegate until the chain ends. If there are N items and K delegates, the number of calls can reach N × K when all items pass through the entire chain.

To keep the chain efficient:

- Place cheap checks and steps likely to exclude items early before expensive steps.
- Avoid creating overly large intermediate objects unnecessarily.
- Do not query the database separately in every delegate if queries can be merged or bulk-looked up.
- Cache reference data only when semantics and lifetime are clear.
- Avoid logging payloads at INFO level for every delegate/item.
- Measure time per delegate to identify bottlenecks.
- Limit concurrency according to database and external API capacity.

Do not merge all steps into a single processor just to reduce method calls if doing so sacrifices responsibility boundaries and testability. Java method call overhead is usually tiny compared to I/O; measure before optimizing.

## 18. Logging and Observability per Delegate

`ItemProcessListener` can be used at the step level to observe all invocations of the configured processor. If you need per-delegate timing, wrap delegates with a decorator or record metrics inside delegates.

Example timing decorator:

~~~java
public class TimedProcessor<I, O> implements ItemProcessor<I, O> {

    private final String name;
    private final ItemProcessor<I, O> delegate;
    private final Timer timer;

    public TimedProcessor(
            String name,
            ItemProcessor<I, O> delegate,
            MeterRegistry registry) {
        this.name = name;
        this.delegate = delegate;
        this.timer = registry.timer("batch.processor.duration", "delegate", name);
    }

    @Override
    public O process(I item) throws Exception {
        return timer.recordCallable(() -> delegate.process(item));
    }
}
~~~

Adapt the example to your project's metrics API and exception contract. Do not put the entire item into metric tags because cardinality can grow unbounded. Tags should be the delegate or step name, not per-record IDs.

When logging errors, preserve the source ID or correlation ID, the delegate name if available, and the exception cause. Avoid logging sensitive data or credentials.

## 19. Testing Each Delegate

Each delegate can be unit tested independently. This helps pinpoint whether a bug belongs to normalization, validation, mapping, or enrichment without running the entire job.

Example normalization test:

~~~java
@Test
void trimsIdentifiersAndNormalizesStatus() throws Exception {
    NormalizeOrderProcessor processor =
            new NormalizeOrderProcessor();

    OrderInput input = new OrderInput(
            " ORD-10 ",
            " CUS-20 ",
            new BigDecimal("12.50"),
            " active ");

    OrderInput result = processor.process(input);

    assertEquals("ORD-10", result.orderId());
    assertEquals("CUS-20", result.customerId());
    assertEquals("ACTIVE", result.status());
}
~~~

Unit tests for each delegate should focus on that delegate's contract: valid inputs, boundary cases, nulls, exceptions, and outputs. Enrichment delegates should mock dependencies to verify handling of missing customers or service timeouts.

## 20. Testing the Entire CompositeItemProcessor

Besides testing each delegate, test the order and behavior of the composite:

1. Delegates are invoked in the exact order.
2. Output of the previous delegate is passed to the next delegate.
3. Final output has the exact type and values expected by the writer.
4. A delegate returning null stops the chain; subsequent delegates are not called.
5. A delegate throwing an exception stops the chain and the exception propagates.
6. Empty configuration or missing required delegates is detected at initialization per the version's contract.
7. Chains with different intermediate types work properly.
8. Multiple calls with the same input produce deterministic results.
9. Concurrent calls do not mix state.
10. Retrying the chain does not produce duplicate side effects.

Mockito can be used to verify order:

~~~java
InOrder order = inOrder(normalizeProcessor, mapProcessor, enrichProcessor);

composite.process(input);

order.verify(normalizeProcessor).process(input);
order.verify(mapProcessor).process(normalizedInput);
order.verify(enrichProcessor).process(mappedOrder);
~~~

The example assumes delegates are mocks and the composite has been configured with them. When testing output, verify the returned value as well rather than only asserting that methods were called.

## 21. Integration Testing in a Chunk Step

Unit testing the composite does not prove the step wired the reader, processor, and writer correctly. Integration tests should run the step with small datasets and an observable writer.

Examples of assertions to include:

- Job/step completes with valid input.
- Writer receives the exact final output type of the chain.
- Filtered items do not appear in the writer.
- Invalid items are handled per the configured skip/fail policy.
- Skip listener records the exact source ID and cause.
- Retries do not produce duplicate outputs or side effects.
- Filter count, process skip count, and write count match the test dataset.

If the processor calls a database or API, use integration tests covering the relevant transaction/retry boundaries. Do not only mock all dependencies and conclude that side effects are safe.

## 22. Common Pitfalls

**Reversing delegate order.** Output may not yet be normalized or may lack data needed for the next step. Declare the chain by dependency and test the order.

**Output type mismatch with the next input.** The composite does not convert types automatically. Use clear intermediate types and concrete generics.

**Assuming the composite runs in parallel.** Delegates for an item run sequentially. Concurrency is configured at the step/partition/flow level.

**Delegate returning null too early.** The item is filtered and later steps do not run. Only filter when that is an intentional business decision.

**Catching exceptions and returning null.** Errors turn into silent filters. Throw an appropriate exception so the step applies its policy.

**Triggering side effects inside a delegate.** Retries can re-run earlier delegates. Use idempotency or an outbox for external effects.

**A delegate holding mutable state in a singleton.** Multiple items/threads can overwrite state. Keep delegates stateless or protect state properly.

**Enrichment causing N+1 queries.** Each item may trigger multiple database calls. Measure and consider joins, caching, or bulk lookups.

**Failing to check null at the start of the chain.** An invalid null input can cause confusing errors in the first delegate. Define the reader's contract and validate data at the right boundary.

**Chain too long and hard to read.** Splitting classes does not mean creating dozens of tiny fragmented steps. Keep each delegate with clear responsibility and standalone value.

## 23. Workflow for Designing a CompositeItemProcessor

When building a composite, follow these steps in order:

1. Identify the item type returned by the reader and the type needed by the writer.
2. Split the pipeline into steps with clear responsibilities.
3. Define each delegate's input/output types and ensure adjacent links are compatible.
4. Decide which steps transform, validate, enrich, or filter.
5. Place cheap validation and filtering early if that preserves business semantics.
6. Declare each delegate as a bean and wire them in the proper order.
7. Attach the composite to the step like a normal ItemProcessor.
8. Configure retry/skip based on the actual exception types from delegates.
9. Verify thread safety and idempotency across the whole chain.
10. Write unit tests per delegate, chain tests, and step integration tests.
11. Monitor latency, filter count, process skip count, and output reconciliation.

## Conclusion

`CompositeItemProcessor<I, O>` combines multiple `ItemProcessor`s into a sequential pipeline per item. The output of one delegate is passed as the input to the next; data types between links must be compatible. The composite returns the final result to the writer, stops the chain when a delegate returns `null`, and propagates exceptions so the step applies its retry, skip, or fail policy.

Split logic into delegates with clear responsibilities such as normalize, validate, map, and enrich; declare concrete generics; wire them in the right order; and keep delegates stateless and safe to re-run. The composite does not create transactions, does not run delegates in parallel, and does not automatically make side effects idempotent. Test each delegate, the chain order, filter/exception propagation, and the whole step to ensure the pipeline processes data accurately before writing.
