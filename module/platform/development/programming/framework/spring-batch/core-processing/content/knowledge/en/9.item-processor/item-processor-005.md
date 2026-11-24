# Chaining multiple processors

In Spring Batch, an `ItemProcessor` receives an input item, performs a transformation or validation, and returns an output item. When a processing step needs several consecutive operations, you can combine multiple processors into a chain. Each processor handles one small task, and the output of the previous processor becomes the input of the next.

For example, when importing orders, a chain of processors can normalize the data, add customer information, check business rules, and create an object ready to be written to the database. This organization separates the logic into components with clear responsibilities that can be tested individually.

Spring Batch provides `CompositeItemProcessor` and `CompositeItemProcessorBuilder` to implement this chain. The delegates are called in their declared order for each item. The chain runs inside the same step and the same chunk process; it does not create an extra step, transaction, or checkpoint for each processor.

## 1. Why chain multiple processors?

A single large processor quickly accumulates many responsibilities: string normalization, reference data lookup, calculation, condition checking, and mapping to the write model. When all the logic lives in one method, reading, testing, and changing rules becomes difficult.

You can split the operations as follows:

1. **Normalize:** clean and normalize the input data.
2. **Enrich:** add information from another system or repository.
3. **Validate:** check business conditions.
4. **Transform:** create the final data type the writer needs.

An example with orders:

```mermaid
flowchart LR
    A[OrderInput] --> B[Normalize]
    B --> C[Enrich customer]
    C --> D[Validate]
    D --> E[ApprovedOrder]
    E --> F[ItemWriter]
```

Each delegate focuses on one transformation step. If a normalization rule changes, you only need to change the corresponding processor. If you need to test a processor individually, you can write a unit test for that delegate without launching the entire job.

A chain is appropriate when the operations form a continuous item-processing pipeline with clear input/output relationships. If the stages have their own transaction boundaries, checkpoints, control conditions, or restart behavior, consider splitting them into multiple steps instead of merely chaining processors.

## 2. How CompositeItemProcessor works

`CompositeItemProcessor<I, O>` is an `ItemProcessor` that wraps several other processors. When it receives an item, it calls each delegate in order:

1. The first delegate receives the original item.
2. The output of the first delegate is passed to the second delegate.
3. The output continues through the subsequent delegates.
4. The output of the last delegate becomes the result of the composite processor.

Suppose there are three processors:

```java
ItemProcessor<OrderInput, NormalizedOrder> normalize;
ItemProcessor<NormalizedOrder, EnrichedOrder> enrich;
ItemProcessor<EnrichedOrder, ApprovedOrder> validate;
```

The data type flow will be:

```text
OrderInput
    -> NormalizedOrder
    -> EnrichedOrder
    -> ApprovedOrder
```

The generic types express the contract between steps. The output of one delegate must be compatible with the input of the next delegate. When you declare concrete types, the compiler helps catch many chaining type errors at compile time.

An important point is that the chain runs per item. With 3 delegates and 100 items in a chunk, Spring Batch runs the processing chain for each item in delegate order, and then the writer receives the remaining results of the chunk. It does not run the first delegate for all 100 items before running the second delegate for the entire chunk.

## 3. Creating a chain with CompositeItemProcessorBuilder

In Spring Batch 5+, you can use `CompositeItemProcessorBuilder` to declare the list of delegates. The example below uses three processors whose input/output types chain together:

```java
@Bean
ItemProcessor<OrderInput, ApprovedOrder> orderProcessor(
        ItemProcessor<OrderInput, NormalizedOrder> normalizeOrder,
        ItemProcessor<NormalizedOrder, EnrichedOrder> enrichOrder,
        ItemProcessor<EnrichedOrder, ApprovedOrder> validateOrder) {

    return new CompositeItemProcessorBuilder<OrderInput, ApprovedOrder>()
            .delegates(List.of(
                    normalizeOrder,
                    enrichOrder,
                    validateOrder))
            .build();
}
```

The delegates are called in exactly the order in `List.of(...)`. Do not rely on the order in which beans are retrieved from the application context or the alphabetical order of bean names; declare the processing order explicitly.

`CompositeItemProcessorBuilder` validates the configuration when building the composite. The generic input type `OrderInput` and output type `ApprovedOrder` describe the outer contract of the whole chain; each delegate still needs input/output compatible with the delegate next to it.

If you are using an older version of Spring Batch or want to configure it directly, you can create a `CompositeItemProcessor` and call `setDelegates(...)`. For new applications, the builder makes the configuration clearer and validates it when the bean is initialized.

## 4. Example delegates in an order pipeline

To see the role of each processor clearly, suppose the input data has the fields `orderId`, `customerId`, and `amount`.

The illustrative data types:

```java
public record OrderInput(
        String orderId,
        String customerId,
        BigDecimal amount) {}

public record NormalizedOrder(
        String orderId,
        String customerId,
        BigDecimal amount) {}

public record EnrichedOrder(
        NormalizedOrder order,
        String customerTier) {}

public record ApprovedOrder(
        String orderId,
        String customerId,
        BigDecimal amount,
        String customerTier) {}
```

### 4.1. Data normalization processor

The first processor cleans strings and normalizes the customer code:

```java
@Bean
ItemProcessor<OrderInput, NormalizedOrder> normalizeOrder() {
    return input -> new NormalizedOrder(
            input.orderId().trim(),
            input.customerId().trim().toUpperCase(Locale.ROOT),
            input.amount());
}
```

This processor only transforms existing data. It does not need to know the customer information or how the writer stores orders.

### 4.2. Data enrichment processor

The second processor looks up the customer tier to enrich the data:

```java
@Bean
ItemProcessor<NormalizedOrder, EnrichedOrder> enrichOrder(
        CustomerService customerService) {

    return order -> {
        Customer customer =
                customerService.findRequired(order.customerId());

        return new EnrichedOrder(order, customer.tier());
    };
}
```

This processor depends on `CustomerService`, but it does not need to know how the input file is read or which table the result is written to. If the customer service has a transient error, the step's retry policy can decide whether to try again.

### 4.3. Processor that validates and creates the final result

The last processor checks business rules and then converts to the type the writer needs:

```java
@Bean
ItemProcessor<EnrichedOrder, ApprovedOrder> validateOrder() {
    return enriched -> {
        if (enriched.order().amount().signum() <= 0) {
            throw new InvalidOrderException("Order amount must be positive");
        }

        return new ApprovedOrder(
                enriched.order().orderId(),
                enriched.order().customerId(),
                enriched.order().amount(),
                enriched.customerTier());
    };
}
```

Here, invalid data makes the processor throw `InvalidOrderException`. The step can be configured to skip this kind of error if the business allows it, or to fail the job if the data needs to be handled manually. You should not turn every validation error into `null`, because `null` means filtering the item, not reporting an error.

### 4.4. Combining the processors

Once you have the three delegate beans, combine them into a single processor:

```java
@Bean
ItemProcessor<OrderInput, ApprovedOrder> orderProcessor(
        ItemProcessor<OrderInput, NormalizedOrder> normalizeOrder,
        ItemProcessor<NormalizedOrder, EnrichedOrder> enrichOrder,
        ItemProcessor<EnrichedOrder, ApprovedOrder> validateOrder) {

    return new CompositeItemProcessorBuilder<OrderInput, ApprovedOrder>()
            .delegates(List.of(
                    normalizeOrder,
                    enrichOrder,
                    validateOrder))
            .build();
}
```

The end result is an `ItemProcessor<OrderInput, ApprovedOrder>`. The step does not need to know how many delegates are inside; it only needs to know the composite's input and output types.

## 5. Putting the chain into a chunk-oriented step

The composite processor is configured for the step just like an ordinary processor:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, ApprovedOrder> orderProcessor,
        ItemWriter<ApprovedOrder> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, ApprovedOrder>chunk(100, transactionManager)
            .reader(reader)
            .processor(orderProcessor)
            .writer(writer)
            .build();
}
```

The reader supplies `OrderInput`; the composite processes it through the delegates and returns `ApprovedOrder`; the writer receives the remaining `ApprovedOrder`s in the chunk. The transaction is still managed by the step. The composite does not create a separate transaction for each delegate.

If a delegate throws an exception, the exception propagates out of the composite and the step applies the configured error policy. If a delegate returns `null`, the composite stops the chain for that item and the item is filtered; the delegates after it are not called for this item.

## 6. The meaning of a null result in a processor chain

Under the `ItemProcessor` contract, returning `null` means the item is filtered and not forwarded to the writer. `CompositeItemProcessor` preserves this meaning: when a delegate returns `null`, the composite does not call the subsequent delegates for that item.

For example:

```java
ItemProcessor<NormalizedOrder, EnrichedOrder> filterTestOrders = order -> {
    if (order.orderId().startsWith("TEST-")) {
        return null;
    }
    return enrich(order);
};
```

If this delegate sits in the middle of the chain, an order with a `TEST-` ID will not be passed on to the later validation or mapping steps and will not reach the writer.

Use `null` only when the intent is to drop the item from the processing flow. If invalid data needs to be recorded, investigated, or reprocessed, throw an appropriate exception, create a result type that represents the rejected state, or record the error information using a clear business mechanism.

Distinguish three cases:

| Delegate result | Meaning in the chain |
|---|---|
| Returns an object | The object becomes the input of the next delegate |
| Returns `null` | Filters the item; stops the chain for that item; the writer does not receive the item |
| Throws an exception | The chain stops due to an error; the step applies retry, skip, or fail according to the configuration |

## 7. Delegate order affects the result

The order of the processors is part of the business rules. For example, normalizing the customer code needs to happen before the customer lookup if the repository requires the code in uppercase. Validating the amount can be done before calling an external service to avoid an unnecessary lookup for an item that will certainly be rejected.

An example of two different orders:

```text
Normalize -> Enrich -> Validate
```

and

```text
Enrich -> Normalize -> Validate
```

These two chains can produce different results if `Enrich` depends on the format of the customer code. Therefore, arrange them according to data dependencies and business goals, not just by processor name.

Some organizing suggestions:

- Normalize formats and strip whitespace before lookups.
- Check structure or required fields before expensive operations.
- Enrich data after a valid reference key is available.
- Check business rules after all necessary data is available.
- Map to the type the writer needs at the end of the chain.

Not every pipeline needs exactly the order above. Clearly determine the input/output and dependencies of each delegate in the specific business domain.

## 8. Processor chains and error handling

`CompositeItemProcessor` does not define retry or skip on its own. It only orchestrates the delegates. When a delegate throws an exception, the step receives that exception and applies the fault-tolerance policy if one is configured.

For example:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, ApprovedOrder> orderProcessor,
        ItemWriter<ApprovedOrder> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, ApprovedOrder>chunk(100, transactionManager)
            .reader(reader)
            .processor(orderProcessor)
            .writer(writer)
            .faultTolerant()
            .skip(InvalidOrderException.class)
            .skipLimit(50)
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .build();
}
```

In this example, validation errors are allowed to be skipped within a limit of 50 items; transient data access errors can be retried up to the configured limit. You need to verify the exceptions actually thrown from the delegates and consider backoff for transient errors.

Some principles:

- Skip only exceptions that represent data that can be rejected under business rules.
- Retry only errors that are likely to go away on their own, such as deadlocks or transient connection errors.
- Do not retry validation errors that cannot fix themselves indefinitely.
- If a delegate calls an API or writes side effects, you must account for the delegate possibly being called again on chunk rollback or retry.
- Do not configure skip for every `Exception` without clearly understanding the consequences; it can hide programming errors and infrastructure errors.

## 9. Keep processors simple, with few side effects

A processor should generally focus on transforming, enriching, and validating data. If possible, design the processor to be stateless and deterministic: the same input with the same reference data produces the same output.

Avoid performing side effects that are hard to repeat in a processor, such as debiting money, sending email, or publishing messages directly. A processor can be called again on retry or when a chunk rolls back. If you need to integrate with an external system, consider saving the intent to send into an outbox within the business transaction, and then publishing the message using a dedicated component.

If a processor needs to look up a database or service, consider the cost of the call for each item. For example, 100 items can generate 100 additional queries. You can use a bounded cache, a bulk lookup with an appropriate design, or move the reference data into a separate preparation step. You need to ensure the cache does not break consistency or hold stale data beyond what is intended.

A processor should not depend on `HttpServletRequest`, a request-scoped bean, or the request's thread-local. A job can run in the background long after the HTTP request ends. Pass the necessary parameters through `JobParameters`, an appropriate context, or a business data store.

## 10. Thread safety and delegate scope

In a sequential step, the delegates are usually called sequentially on the step's processing thread. However, if the step uses multi-threading or a parallel-processing configuration, the same processor bean can be called concurrently by multiple threads depending on the step's structure.

Therefore:

- Prefer stateless processors that do not hold per-item data in mutable fields.
- If you need a cache, use a thread-safe structure with a capacity limit.
- Do not store an item's temporary variables in a field of a singleton processor.
- If a delegate has state tied to the step, consider `@StepScope` and an appropriate lifecycle.
- If a delegate implements `ItemStream` itself, ensure Spring Batch knows about and manages that stream's lifecycle.

A note when using a composite: `CompositeItemProcessor` itself mainly orchestrates the list of delegates; you should not assume it automatically forwards every custom lifecycle of the delegates. If a delegate needs Spring Batch to call `open()`, `update()`, or `close()`, you need to register that stream with the step using `.stream(delegate)` or use a wrapper that fully forwards `ItemStream`. Avoid duplicate registration that causes callbacks to be called multiple times.

## 11. When to use multiple processors and when to split into multiple steps

A chain of multiple processors and a multi-step job address two different needs.

| Criterion | Chain of multiple processors | Multiple steps |
|---|---|---|
| Purpose | Separate the transformations/checks on a single item | Separate the stages of a batch process |
| Data flow | Output of the previous delegate to the input of the next delegate | The next step starts when the flow allows |
| Transaction | Still part of the chunk step's transaction | Each step/chunk has its own transaction boundary |
| Checkpoint | Checkpoint is managed by the step; there is no separate checkpoint for each delegate | Each step has its own metadata and state |
| Restart | Restart the step from the reader/step checkpoint | Can resume at an incomplete step according to the flow and restart configuration |
| Transition condition | Logic in the processor or filter/exception | Transition, decider, or the job's flow |

Use a chain when the operations are just consecutive transformations on the same item and need the same step lifecycle. Split into steps when a stage needs its own commit, its own checkpoint, transition conditions, resources, or an independent recovery process.

For example, normalizing an address, looking up the customer tier, and checking the limit for an order can be a chain. But downloading a file, importing data, reconciling totals, and sending results to another system are usually business stages suited to multiple steps.

## 12. Testing a chain of multiple processors

You should test each delegate as well as the composite:

1. **Delegate unit tests:** confirm that normalization, enrichment, and validation work independently.
2. **Order check:** confirm that the output of the previous delegate is passed correctly to the next delegate.
3. **Type check:** ensure the generic input/output of the delegates are compatible.
4. **Filter check:** when a delegate returns `null`, the following delegates are not called and the writer does not receive that item.
5. **Exception check:** the exception propagates out of the composite and the step applies skip/retry according to the configuration.
6. **Boundary data check:** empty strings, nonexistent codes, an amount of 0/negative, large data, or missing fields.
7. **Performance check:** measure the number of service/database calls per chunk and the cost of each delegate.
8. **Parallel check:** if the step runs multi-threaded, confirm the delegates have no race conditions or incorrectly shared state.
9. **Restart check:** confirm the processor can be called again without creating duplicate side effects.

An example composite unit test can use small processors with deterministic output and then check the final result. For integration tests, use `JobLauncherTestUtils` or an appropriate job-launching mechanism to confirm that the whole reader → composite processor → writer works correctly in the step's transaction.

## 13. Common mistakes

**Reversing the delegate order.** An enrichment processor may look up using an unnormalized code. Declare the order explicitly according to data dependencies.

**Chaining the wrong input/output types.** Using raw types or unsafe casts can hide chaining errors. Declare concrete generics for each delegate.

**Returning `null` when validation fails.** `null` means filtering the item and does not record the rejection reason. Use an exception or a business result model if you need traceability.

**Stuffing too many responsibilities into one delegate.** A large delegate defeats the benefit of splitting the pipeline. Each processor should have one clear responsibility.

**Thinking each processor is a step.** The composite runs inside one step and uses the same transaction/checkpoint boundary. To get a separate execution boundary, create a separate step.

**Performing non-idempotent side effects.** A retry or rollback can cause a delegate to be called again. Use an appropriate transaction, unique key, outbox, or idempotency key.

**Using a mutable singleton in a multi-threaded step.** A shared field can cause one item's data to overwrite another's. Prefer stateless or manage scope/thread safety properly.

**Forgetting to register a delegate that implements ItemStream.** The composite can obscure the delegate's lifecycle. Register the stream separately or forward the callbacks fully.

## Conclusion

Chaining multiple processors splits an item-processing pipeline into small stages with clear input/output types that can be tested independently. `CompositeItemProcessorBuilder` lets you combine delegates in order; the output of each delegate becomes the input of the next. If a delegate returns `null`, the item is filtered and the chain stops for that item; if it throws an exception, the step applies the retry, skip, or fail policy.

Keep processors focused on transformation, enrichment, and validation; limit side effects; ensure the order and data types of the delegates; and pay attention to thread safety and lifecycle when using a multi-threaded step or delegates that implement `ItemStream`. Use a chain for consecutive transformations on an item, and use multiple steps when you need transaction boundaries, checkpoints, flow control, or independent recovery.
