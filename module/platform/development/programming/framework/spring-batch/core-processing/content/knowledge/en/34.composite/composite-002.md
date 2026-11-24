# Chaining Processors in Order

In Spring Batch, an item sometimes needs to go through multiple transformation steps before being written. For example, raw data may need to be normalized, enriched with reference information, validated against business rules, and then mapped into a DTO for the target system. All of this logic can be implemented in one `ItemProcessor`, but when the steps have distinct responsibilities, `CompositeItemProcessor` helps compose multiple processors into an ordered chain.

`CompositeItemProcessor<I, O>` invokes the delegates one after another. The output of the previous processor becomes the input of the next processor. The chain finishes when the last delegate produces output `O`, or earlier if a delegate returns `null` to filter the item. This is sequential processing per item; it does not fan out one item to multiple branches and does not run delegates in parallel.

## 1. When Do You Need to Chain Processors?

An order processing pipeline might consist of the following steps:

1. Normalize codes, whitespace, and input formatting.
2. Look up customer info or reference data.
3. Compute derived values.
4. Validate business conditions.
5. Convert into an object suitable for the writer.

Putting everything in one large processor makes the class take on too many responsibilities and makes individual steps hard to test. Splitting into small processors gives each step a clear input, output, and purpose.

Example diagram:

```text
RawOrder
   |
   v
NormalizeProcessor
   |
   v
NormalizedOrder
   |
   v
EnrichProcessor
   |
   v
EnrichedOrder
   |
   v
ExportMappingProcessor
   |
   v
OrderExport
```

Processor chaining is useful when:

- Transformation steps have a clear dependency order.
- The output of one step is the input of the next step.
- You want to reuse a processor across multiple Jobs/Steps.
- You want to unit test each step without running the entire Job.
- You want to separate normalization, enrichment, validation, and mapping logic.

If there is only a single simple transformation, one `ItemProcessor` is enough. Do not create a composite just to wrap a single processor.

## 2. How Does CompositeItemProcessor Work?

`CompositeItemProcessor<I, O>` is an implementation of `ItemProcessor<I, O>`. It holds a list of delegate processors and executes them in list order.

For an item `x`, the conceptual behavior is:

```text
result = x

for each delegate in configured order:
    if result is null:
        stop and return null
    result = delegate.process(result)

return result
```

Importantly, each delegate receives the latest result, not the original item again. If the first delegate turns `RawOrder` into `NormalizedOrder`, the second delegate must accept `NormalizedOrder`.

The composite does not guess how to convert types. Delegates must have mutually compatible data type contracts.

## 3. Example of Three Chained Processors

Suppose a Job reads raw order data and needs to produce an export object:

```java
public record RawOrder(
        String orderId,
        String customerCode,
        String amountText) {
}

public record NormalizedOrder(
        String orderId,
        String customerCode,
        BigDecimal amount) {
}

public record EnrichedOrder(
        String orderId,
        Customer customer,
        BigDecimal amount,
        BigDecimal taxRate) {
}

public record OrderExport(
        String orderId,
        String customerName,
        BigDecimal amount,
        BigDecimal tax) {
}
```

Each processor performs only one step:

```java
ItemProcessor<RawOrder, NormalizedOrder> normalizeProcessor = raw -> {
    String orderId = raw.orderId().trim();
    String customerCode = raw.customerCode().trim().toUpperCase(Locale.ROOT);
    BigDecimal amount = new BigDecimal(raw.amountText().trim());

    return new NormalizedOrder(orderId, customerCode, amount);
};

ItemProcessor<NormalizedOrder, EnrichedOrder> enrichProcessor = order -> {
    Customer customer = customerService.findByCode(order.customerCode());
    BigDecimal taxRate = taxService.rateFor(customer.region());

    return new EnrichedOrder(
            order.orderId(), customer, order.amount(), taxRate);
};

ItemProcessor<EnrichedOrder, OrderExport> exportMappingProcessor = order -> {
    BigDecimal tax = order.amount().multiply(order.taxRate());

    return new OrderExport(
            order.orderId(),
            order.customer().name(),
            order.amount(),
            tax);
};
```

The result of `normalizeProcessor` is passed to `enrichProcessor`; the enrichment result is then passed to `exportMappingProcessor`.

## 4. Configuring CompositeItemProcessorBuilder

Spring Batch provides `CompositeItemProcessorBuilder` to configure the chain:

```java
@Bean
ItemProcessor<RawOrder, OrderExport> orderCompositeProcessor(
        ItemProcessor<RawOrder, NormalizedOrder> normalizeProcessor,
        ItemProcessor<NormalizedOrder, EnrichedOrder> enrichProcessor,
        ItemProcessor<EnrichedOrder, OrderExport> exportMappingProcessor) {

    return new CompositeItemProcessorBuilder<RawOrder, OrderExport>()
            .delegates(List.of(
                    normalizeProcessor,
                    enrichProcessor,
                    exportMappingProcessor))
            .build();
}
```

`delegates(...)` takes the list of processors in the required execution order. `List.of(...)` creates a list with a deterministic order, keeping configuration readable and avoiding accidental order changes during initialization.

If the application configures the builder directly instead of via bean methods, the same principle applies: declare the composite's input type, final output type, and properly ordered delegate list.

## 5. Placing the Composite in a Step

A composite is an `ItemProcessor`, so it is attached to a Step like any ordinary processor:

```java
@Bean
Step exportOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<RawOrder> orderReader,
        ItemProcessor<RawOrder, OrderExport> orderCompositeProcessor,
        ItemWriter<OrderExport> orderWriter) {

    return new StepBuilder("exportOrdersStep", jobRepository)
            .<RawOrder, OrderExport>chunk(200, transactionManager)
            .reader(orderReader)
            .processor(orderCompositeProcessor)
            .writer(orderWriter)
            .build();
}
```

The Step only needs to know the input type `RawOrder` and output type `OrderExport`. Intermediate types are handled inside the delegate chain.

There is no need to create a separate Step for each transformation if the steps are just transformations on the same item and do not need separate commits or checkpoints. Use multiple Steps when there are independent business boundaries, transactions, restarts, or resources that need separate management.

## 6. Delegate Order Determines the Outcome

The order in the list is the execution order. You cannot swap them arbitrarily if one processor depends on the output of a preceding processor.

For example:

```text
RawOrder
   |
   v
Normalize amount text
   |
   v
Parse BigDecimal
   |
   v
Calculate tax
```

If tax is calculated before parsing the amount, the processor does not have a `BigDecimal` value to perform the math. If enrichment needs a normalized customer code, normalization must run before enrichment.

Name delegates by action and express the order in configuration. Avoid deriving order from a structure that does not guarantee iteration order, such as a map without a clear ordering rule.

### Avoid Implicit Ordering via Dependency Injection

If you inject a collection of processors from the Spring context, the order may depend on how Spring sorts beans or on `@Order` annotations. For critical business pipelines, configuring the list explicitly helps readers immediately see the processing chain right where the composite is created.

If the project intentionally uses `@Order`, define ordering by convention, test the delegate list, and prevent a new bean from accidentally altering the pipeline.

## 7. Data Types Between Processors Must Match

Each delegate has type `ItemProcessor<I, O>`. Output `O` of the previous step must be compatible with input `I` of the next step.

| Delegate | Input | Output |
|---|---|---|
| `normalizeProcessor` | `RawOrder` | `NormalizedOrder` |
| `enrichProcessor` | `NormalizedOrder` | `EnrichedOrder` |
| `exportMappingProcessor` | `EnrichedOrder` | `OrderExport` |
| Composite | `RawOrder` | `OrderExport` |

Declaring explicit generics helps the compiler catch many type errors before the Job runs. However, the composite's delegate list uses wildcard generics, so the compiler cannot always prove every intermediate input/output pair in the list. Declare processor variables with concrete types and test the entire chain.

Do not cast raw types or use non-generic `ItemProcessor`s to bypass compile errors. That pushes type errors to runtime, which are usually harder to investigate after a Job has processed part of the data.

## 8. Delegate Returning null: Stopping the Chain and Filtering Items

Per the `ItemProcessor` contract, returning `null` means the item is not forwarded to the writer. With `CompositeItemProcessor`, if a delegate returns `null`, the composite stops the chain for that item and returns `null`; subsequent delegates are not called for this item.

For example:

```java
ItemProcessor<NormalizedOrder, EnrichedOrder> filterInvalidOrder = order -> {
    if (order.amount().signum() <= 0) {
        return null;
    }
    return enrich(order);
};
```

If this delegate returns `null`, `exportMappingProcessor` does not run. The item is filtered out of the pipeline and is not sent to the writer.

This differs from throwing an exception:

- `return null`: filters the item per the processor's decision.
- `throw exception`: signals an error; the Step applies rollback, retry, skip, or fail per configuration.

Do not return `null` to mask system errors such as database timeouts or unavailable services. `null` should represent an intentional business decision.

## 9. Validating Data at Each Stage

A well-structured chain places each rule at the appropriate stage:

- Normalize: standardize input formatting and values.
- Parse: convert strings to domain types, raising an error if parsing fails.
- Enrich: fetch reference data or supplement information.
- Validate: verify business invariants.
- Map: construct the output DTO.

You do not necessarily need a separate processor for every tiny step. If two operations always go together, share the same responsibility, and do not need separate reuse, they can be combined. The goal is to separate meaningful steps, not to create too many fragmented classes.

Example validator:

```java
ItemProcessor<EnrichedOrder, EnrichedOrder> validateOrder = order -> {
    if (order.customer() == null) {
        throw new InvalidOrderException("Customer is required");
    }
    if (order.amount().signum() <= 0) {
        throw new InvalidOrderException("Amount must be positive");
    }
    return order;
};
```

A validator can return the same object if valid. It does not have to allocate a new object, though avoid mutating shared objects if that causes unintended side effects.

## 10. Exception Handling in the Chain

If a delegate throws an exception, `CompositeItemProcessor` does not continue calling subsequent delegates for that item; the exception propagates outward. Spring Batch handles exceptions at the Step level according to the retry/skip/rollback policy.

For example:

```text
RawOrder
   |
   v
NormalizeProcessor       succeeded
   |
   v
EnrichProcessor          throws ServiceUnavailableException
   |
   X
ExportMappingProcessor   not called
```

Principles:

- Do not catch exceptions inside a delegate and return a dummy object to keep the chain going.
- Preserve the cause chain when wrapping exceptions.
- Distinguish fixed data errors from transient errors.
- Set a retry policy for recoverable exceptions.
- Only skip exceptions when business rules permit dropping the item.
- Do not use `null` in place of an exception that requires investigation.

If a delegate calls an external service, configure timeouts and retries at the right layer. A processor may be re-invoked for the same item on chunk retry; external calls must be safe to repeat or read-only.

## 11. Retry and Skip Apply to the Whole Chain

For a Step using `CompositeItemProcessor`, Spring Batch sees one processor at the Step level. If an inner delegate throws an exception, the Step receives that exception and applies the configured policy.

For example:

```java
return new StepBuilder("exportOrdersStep", jobRepository)
        .<RawOrder, OrderExport>chunk(200, transactionManager)
        .reader(orderReader)
        .processor(orderCompositeProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(ServiceUnavailableException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .build();
```

In the example, transient service errors can be retried; data errors are allowed to be skipped within a limit. Whether errors occur in `normalizeProcessor`, `enrichProcessor`, or `exportMappingProcessor`, the exception type remains the basis for the policy decision.

If different policies are needed per step, use distinct exception types or configure a classifying `RetryPolicy`/`SkipPolicy`. Avoid relying on delegate position or exception messages to classify errors if clear exception classes can be used instead.

## 12. Processor Chain Is Not Fan-Out

`CompositeItemProcessor` is a sequential chain: the output of the prior delegate enters the next delegate. It does not send the same original item to multiple independent processors.

| Pattern | Behavior |
|---|---|
| `CompositeItemProcessor` | Sequential: A → B → C. |
| Routing/classifier processor | Selects one suitable processor based on a condition. |
| Custom fan-out | One input produces multiple independent outputs/branches per custom design. |
| `CompositeItemWriter` | Sends the same item/chunk to multiple writers. |

For example, if an order needs both a tax report calculation and a notification message generated, you should not chain two independent processors sequentially if both need the same input and produce two different results. Create one processor that returns a combined object, use appropriate routing, or design fan-out at another processing layer.

Do not confuse `CompositeItemProcessor` with `CompositeItemWriter`: one transforms an item through a chain, while the other coordinates multiple writers.

## 13. Comparison with ClassifierCompositeItemProcessor

If you need to choose one processor based on item type or a condition, `ClassifierCompositeItemProcessor` fits better than a fixed chain. For example, `CARD` transactions go through a card processor, and `BANK` transactions go through a bank processor.

```text
Transaction
    |
    v
Classifier
    |
    +---- CARD ----> CardProcessor
    |
    +---- BANK ----> BankTransferProcessor
```

Meanwhile, a chain always runs the same sequence of delegates:

```text
Transaction
    |
    v
Normalize
    |
    v
Enrich
    |
    v
Validate
```

The two patterns can be combined if needed: one step in the chain is a classifier that picks a specialized processor, after which the result continues through common steps. Only combine them when the flow truly requires it, as multiple routing layers can make execution harder to trace.

## 14. Registering Delegates as Separate Beans

In a Spring application, each delegate can be a separate bean for easy reuse and testing:

```java
@Bean
ItemProcessor<RawOrder, NormalizedOrder> normalizeProcessor() {
    return raw -> new NormalizedOrder(
            raw.orderId().trim(),
            raw.customerCode().trim().toUpperCase(Locale.ROOT),
            new BigDecimal(raw.amountText().trim()));
}

@Bean
ItemProcessor<NormalizedOrder, EnrichedOrder> enrichProcessor(
        CustomerService customerService,
        TaxService taxService) {
    return order -> {
        Customer customer = customerService.findByCode(order.customerCode());
        BigDecimal rate = taxService.rateFor(customer.region());
        return new EnrichedOrder(
                order.orderId(), customer, order.amount(), rate);
    };
}

@Bean
ItemProcessor<EnrichedOrder, OrderExport> exportMappingProcessor() {
    return order -> new OrderExport(
            order.orderId(),
            order.customer().name(),
            order.amount(),
            order.amount().multiply(order.taxRate()));
}
```

The composite bean receives the Spring-managed delegates:

```java
@Bean
ItemProcessor<RawOrder, OrderExport> orderCompositeProcessor(
        ItemProcessor<RawOrder, NormalizedOrder> normalizeProcessor,
        ItemProcessor<NormalizedOrder, EnrichedOrder> enrichProcessor,
        ItemProcessor<EnrichedOrder, OrderExport> exportMappingProcessor) {

    return new CompositeItemProcessorBuilder<RawOrder, OrderExport>()
            .delegates(List.of(
                    normalizeProcessor,
                    enrichProcessor,
                    exportMappingProcessor))
            .build();
}
```

If there are multiple beans with the same generic type or interface, use `@Qualifier` so injection is unambiguous. Name beans to reflect their responsibility and keep the list order explicit.

## 15. StepScope and JobParameters in Delegates

A delegate may need JobParameters, such as a tenant ID, business date, or run mode. In that case, the delegate can be declared `@StepScope`:

```java
@Bean
@StepScope
ItemProcessor<NormalizedOrder, EnrichedOrder> enrichProcessor(
        CustomerService customerService,
        TaxService taxService,
        @Value("#{jobParameters['tenant.id']}") Long tenantId) {

    return order -> {
        Customer customer = customerService.findByTenantAndCode(
                tenantId, order.customerCode());
        BigDecimal rate = taxService.rateFor(customer.region());
        return new EnrichedOrder(
                order.orderId(), customer, order.amount(), rate);
    };
}
```

`@StepScope` resolves values for the current StepExecution. If a delegate does not depend on execution context and holds no mutable state, a singleton is usually simpler.

Do not store per-item state in fields of a singleton processor. With a multi-threaded Step or concurrent Jobs, mutable fields can be overwritten across executions.

## 16. Statelessness and Thread Safety

Processors should generally be as close to pure functions as possible: accept an object, return a new object, and do not mutate shared state. This makes the chain safe under retries and easy to run concurrently.

If a Step runs with multiple threads or partition workers, check every delegate:

- Does the delegate use any shared mutable fields?
- Are injected services thread-safe?
- Are caches synchronized and bounded in size?
- Are `currentItem`, counters, or buffers held in fields?
- Are external API calls using appropriate rate limits or connection pools?

The composite does not serialize calls automatically. If multiple threads call the same composite bean, delegates can be invoked concurrently. Use stateless processors or scope them per StepExecution; do not assume the chain creates a fresh instance per item.

## 17. Side Effects in the Chain

Processors can be re-invoked during retries or chunk rollback handling. Therefore, delegates should avoid non-idempotent side effects such as sending emails, charging payments, or publishing messages.

Safer options:

- Only read reference data during enrichment.
- Build command/event objects instead of sending immediately.
- Write intent to an outbox inside the chunk transaction.
- Use a stable idempotency key if an API with side effects must be called.
- Move side effects to a writer or a separate Step with clear transaction and recovery strategies.

If a delegate calls a read API and times out, a retry may repeat the request; timeouts and retry limits are still needed. If an API mutates state, a timeout outcome can be ambiguous and requires idempotency or a status lookup.

## 18. Logging and Monitoring Individual Delegates

At the Step level, `ItemProcessListener` observes a single call to the configured processor. If that processor is `CompositeItemProcessor`, the listener wraps the entire chain; it does not emit separate callbacks for each internal delegate.

If per-step timing is needed, you can:

- Wrap each delegate with a timing decorator.
- Record metrics inside each processor.
- Use separate tracing spans for individual enrichment/validation operations.
- Use logs containing the step name and business correlation ID.

Do not log full sensitive payloads at every step. Metric tags should have low cardinality, such as `processor=normalize` or `processor=enrich`, avoiding order IDs as tags.

## 19. Testing Each Processor Independently

Because each delegate has a focused responsibility, unit test every processor:

- Normalize: whitespace, casing, number formats.
- Enrich: existing reference data, missing data, and service errors.
- Validate: valid cases and invariant violations.
- Mapping: output fields, data types, and derived values.

Example normalization test:

```java
@Test
void normalizesOrderFields() throws Exception {
    ItemProcessor<RawOrder, NormalizedOrder> processor = raw ->
            new NormalizedOrder(
                    raw.orderId().trim(),
                    raw.customerCode().trim().toUpperCase(Locale.ROOT),
                    new BigDecimal(raw.amountText().trim()));

    NormalizedOrder result = processor.process(
            new RawOrder(" O-1001 ", " c001 ", " 250.00 "));

    assertThat(result.orderId()).isEqualTo("O-1001");
    assertThat(result.customerCode()).isEqualTo("C001");
    assertThat(result.amount()).isEqualByComparingTo("250.00");
}
```

Unit testing each delegate helps isolate which step contains a bug rather than only seeing that the entire composite returned the wrong result.

## 20. Testing Execution Order

Mockito `InOrder` can be used to verify delegates are invoked in the exact order:

```java
@Test
void delegatesAreInvokedInConfiguredOrder() throws Exception {
    @SuppressWarnings("unchecked")
    ItemProcessor<RawOrder, NormalizedOrder> normalize = mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<NormalizedOrder, EnrichedOrder> enrich = mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<EnrichedOrder, OrderExport> map = mock(ItemProcessor.class);

    RawOrder raw = new RawOrder("O-1", "C-1", "10.00");
    NormalizedOrder normalized = new NormalizedOrder(
            "O-1", "C-1", new BigDecimal("10.00"));
    EnrichedOrder enriched = new EnrichedOrder(
            "O-1", new Customer("C-1", "Lan", "VN"),
            new BigDecimal("10.00"), new BigDecimal("0.1"));
    OrderExport expected = new OrderExport(
            "O-1", "Lan", new BigDecimal("10.00"), new BigDecimal("1.00"));

    when(normalize.process(raw)).thenReturn(normalized);
    when(enrich.process(normalized)).thenReturn(enriched);
    when(map.process(enriched)).thenReturn(expected);

    ItemProcessor<RawOrder, OrderExport> composite =
            new CompositeItemProcessorBuilder<RawOrder, OrderExport>()
                    .delegates(List.of(normalize, enrich, map))
                    .build();

    assertThat(composite.process(raw)).isEqualTo(expected);

    InOrder order = inOrder(normalize, enrich, map);
    order.verify(normalize).process(raw);
    order.verify(enrich).process(normalized);
    order.verify(map).process(enriched);
}
```

The models and constructors in the example are illustrative test fixtures. Tests should verify that the next delegate receives the exact output of the previous delegate, not just that all three mocks were called.

## 21. Testing Filtering and Exception Propagation

An important test is verifying that `null` stops the chain:

```java
@Test
void nullFromDelegateStopsRemainingProcessors() throws Exception {
    ItemProcessor<RawOrder, NormalizedOrder> normalize = raw -> null;
    ItemProcessor<NormalizedOrder, OrderExport> map = mock(ItemProcessor.class);

    ItemProcessor<RawOrder, OrderExport> composite =
            new CompositeItemProcessorBuilder<RawOrder, OrderExport>()
                    .delegates(List.of(normalize, map))
                    .build();

    assertThat(composite.process(
            new RawOrder("O-1", "C-1", "10.00"))).isNull();

    verifyNoInteractions(map);
}
```

And verifying exceptions are not swallowed by the composite:

```java
@Test
void exceptionStopsChainAndPropagates() throws Exception {
    RuntimeException failure = new IllegalStateException("enrichment failed");
    ItemProcessor<RawOrder, NormalizedOrder> normalize = raw -> {
        throw failure;
    };
    ItemProcessor<NormalizedOrder, OrderExport> map = mock(ItemProcessor.class);

    ItemProcessor<RawOrder, OrderExport> composite =
            new CompositeItemProcessorBuilder<RawOrder, OrderExport>()
                    .delegates(List.of(normalize, map))
                    .build();

    assertThatThrownBy(() -> composite.process(
            new RawOrder("O-1", "C-1", "10.00")))
            .isSameAs(failure);

    verifyNoInteractions(map);
}
```

These tests verify the basic semantics of the chain: a subsequent delegate only runs when the preceding delegate returns a non-null object and does not throw an exception.

## 22. Integration Testing with a Step

Unit tests of the composite do not verify transactions, filter counts, retries, skips, or writer integration. You can use `@SpringBatchTest` and `JobLauncherTestUtils` to run a real Step/Job in tests:

- Verify valid items pass through the entire chain and are written.
- Verify filtered items do not reach the writer and filter count is accurate.
- Verify exceptions in each delegate trigger Step retry/skip/fail per policy.
- Verify mapping order produces the correct output.
- Verify JobParameters are injected properly into `@StepScope` delegates.
- Verify the chain works on restart without repeating side effects.

If a delegate calls a database or external service, use deterministic fixtures and appropriate test doubles. Do not let tests depend on production data or an unstable network service.

## 23. Common Mistakes

### Reversing Delegate Order

Later processors receive unnormalized or unenriched data. Declare the list in business order and test invocation order.

### Input/Output Type Mismatch

The previous processor's output is incompatible with the next processor's input. Declare concrete generics for each delegate and avoid raw types or arbitrary casts.

### Thinking Delegates Run in Parallel

`CompositeItemProcessor` invokes delegates sequentially per item. If parallel execution is needed, that is a different concurrency design at the Step/partition or processing infrastructure level.

### Thinking the Composite Fans Out One Item

The output of the previous delegate is passed into the next delegate. Use a classifier or a custom fan-out design if multiple independent branches are needed.

### Delegate Returning null While Expecting Later Steps to Run

`null` is a filter signal and stops the chain for that item. If a valid empty result needs representation, use an object/Optional or explicit result type instead of null.

### Catching Exceptions and Returning a Default Object

Real errors are hidden and bad data continues to the writer. Propagate the exception or convert it into an explicit business result with clear status.

### Cramming All Logic into One Delegate

A composite adds no value if one delegate still does all the work. Split by responsibility and keep each step understandable and independently testable.

### Splitting into Too Many Tiny Processors

A long chain of fragmented steps adds overhead and hurts readability. Only split when there is a clear responsibility, rule, or reuse potential.

### Storing Mutable State in a Singleton

Multiple items/threads may share the processor and mix up state. Prefer stateless delegates or an appropriate scope.

### Putting Non-Idempotent Side Effects in a Processor

Retries can re-invoke delegates. Use idempotency, an outbox, or move side effects to a phase with clear recovery.

### Relying on ItemProcessListener to Measure Each Delegate

The Step's listener wraps the composite as a single processor. Use decorators or metrics inside delegates if per-step observability is needed.

## 24. Process for Building a Processor Chain

When designing an item transformation pipeline, you can follow this sequence:

1. Identify the input type from the reader and the output type required by the writer.
2. Split the logic into steps with clear responsibilities: normalize, enrich, validate, map.
3. Define the input/output generics of each delegate.
4. Order delegates according to data dependencies.
5. Create `CompositeItemProcessorBuilder<I, O>` with an explicit delegate list.
6. Decide clearly which conditions return `null` to filter and which must throw exceptions.
7. Register delegates and the composite as beans; use `@StepScope` when JobParameters or Step-scoped state is needed.
8. Wire the composite into the Step like a standard `ItemProcessor`.
9. Define retry/skip policies for exceptions from any delegate.
10. Keep delegates stateless/thread-safe and avoid non-idempotent side effects.
11. Unit test each processor, chain order, null short-circuiting, and exception propagation.
12. Integration test filter counts, writer output, transactions, retry/skip, and restart.

| Need | Suitable Mechanism |
|---|---|
| Multiple sequential transformation steps | `CompositeItemProcessor<I, O>` |
| Choosing one processor by type/condition | Classifier/routing processor |
| Sending the same item to multiple writers | `CompositeItemWriter` |
| One delegate excluding an item from output | Returning `null` intentionally |
| One delegate detecting an error to handle | Throwing an exception matching retry/skip/fail policy |
| Observing each step in the chain | Decorator, metrics, or tracing inside delegates |

## Conclusion

`CompositeItemProcessor<I, O>` lets you compose multiple `ItemProcessor`s into an ordered chain: the output of the preceding delegate becomes the input of the next. Use `CompositeItemProcessorBuilder` with an explicit delegate list, declare compatible intermediate types, and order them by data dependencies. When a delegate returns `null`, the item is filtered and remaining delegates do not run; when a delegate throws an exception, the error propagates to the Step to retry, skip, or fail per policy. A chain is sequential processing per item, not fan-out or parallel processing. Keep delegates small, stateless, and retry-safe, then test each step individually along with the full chain inside the Step.
