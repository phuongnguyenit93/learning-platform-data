# Classifier Selects a Processor or Writer

In Spring Batch, `Classifier` enables selecting a processing component based on item data. Instead of using a single processor or writer for every item, a step can classify each item and then route it to the appropriate processor or writer.

Two components commonly used for this routing pattern are:

- `ClassifierCompositeItemProcessor<I, O>`: selects an `ItemProcessor` for each input item and then returns the result of that processor.
- `ClassifierCompositeItemWriter<T>`: selects an `ItemWriter` for each output item and then forwards the item to the corresponding writer.

`Classifier` only decides **which delegate to select**. It does not transform data itself, does not write to the database, and does not manage transactions. The actual work is still performed by the selected `ItemProcessor` or `ItemWriter`.

For example, an order-processing job has two groups: domestic orders and international orders. The domestic processor calculates tax according to domestic rules; the international processor checks currency and customs fees. After processing, the writer can send the results to two different tables or two different files. The classifier reads an item's property and selects the right delegate for each case.

## What Is a Classifier?

`Classifier<C, T>` is an interface from Spring Core Classification, located in the `org.springframework.classify` package. Its contract is to accept an input object and return a selected object:

```java
public interface Classifier<C, T> {
    T classify(C classifiable);
}
```

In a Spring Batch context:

- `C` is the item type that the classifier uses to make decisions.
- `T` is the selected delegate type, such as `ItemProcessor` or `ItemWriter`.

Example of a classifier selecting a processor by order type:

```java
Classifier<OrderInput, ItemProcessor<?, ? extends Order>> classifier = input -> {
    if (input.international()) {
        return internationalOrderProcessor;
    }
    return domesticOrderProcessor;
};
```

A classifier can be written as a lambda, a method reference, or a dedicated class implementing `Classifier`. For simple logic, a lambda makes the routing condition visible right at the configuration site. For complex logic, a dedicated class is easier to test and reuse.

A classifier should return a valid delegate for every input that the step can receive. If it returns `null`, the composite has no processor/writer to invoke and will typically throw a runtime error. If a default branch is needed, return a default delegate explicitly.

## ClassifierCompositeItemProcessor

`ClassifierCompositeItemProcessor<I, O>` is a composite `ItemProcessor`. It uses a classifier to select a processor based on the input item, invokes that processor, and returns the result.

```text
                  Input item
                      |
                      v
                  Classifier
                      |
             +--------+--------+
             |                 |
             v                 v
      Domestic processor  International processor
             |                 |
             v                 v
       Domestic order     International order
             |                 |
             +--------+--------+
                      |
                      v
                 Output item
```

Only one processor is selected for each input item. The remaining processors are not invoked for that item.

### Example: Selecting a Processor by Input Property

Suppose the input model is:

```java
public record OrderInput(
        String orderId,
        String countryCode,
        BigDecimal amount) {

    public boolean international() {
        return !"VN".equalsIgnoreCase(countryCode);
    }
}
```

Two processors both accept `OrderInput` and return `Order`:

```java
@Bean
ItemProcessor<OrderInput, Order> domesticOrderProcessor() {
    return input -> new Order(
            input.orderId(),
            input.amount(),
            "VND",
            calculateDomesticTax(input.amount()));
}

@Bean
ItemProcessor<OrderInput, Order> internationalOrderProcessor() {
    return input -> new Order(
            input.orderId(),
            convertToSettlementCurrency(input.amount(), input.countryCode()),
            "USD",
            calculateImportFee(input));
}
```

The methods `calculateDomesticTax`, `convertToSettlementCurrency`, and `calculateImportFee` are business logic provided by the application. Both processors have the same input type and output type, so they can be selected by the same `ClassifierCompositeItemProcessor<OrderInput, Order>`.

Declaring the classifier and composite processor:

```java
@Bean
Classifier<OrderInput, ItemProcessor<?, ? extends Order>> orderProcessorClassifier(
        ItemProcessor<OrderInput, Order> domesticOrderProcessor,
        ItemProcessor<OrderInput, Order> internationalOrderProcessor) {

    return input -> input.international()
            ? internationalOrderProcessor
            : domesticOrderProcessor;
}

@Bean
ClassifierCompositeItemProcessor<OrderInput, Order> orderProcessor(
        Classifier<OrderInput, ItemProcessor<?, ? extends Order>> orderProcessorClassifier) {

    return new ClassifierCompositeItemProcessorBuilder<OrderInput, Order>()
            .classifier(orderProcessorClassifier)
            .build();
}
```

`ClassifierCompositeItemProcessorBuilder` helps configure the composite and validates the required dependencies when building. You can also instantiate `ClassifierCompositeItemProcessor` and call `setClassifier(...)` if you prefer JavaBean-style configuration.

### Attaching the Composite Processor to a Step

```java
@Bean
Step processOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ClassifierCompositeItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("processOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

To the step, the composite processor is just an ordinary `ItemProcessor`. The step does not need to know how many processor delegates exist or what condition the classifier uses.

## Data Types Across Processor Delegates

Selected processor delegates must be compatible with the composite's generic input/output types.

For a composite declared as `ClassifierCompositeItemProcessor<I, O>`:

- The classifier receives a value compatible with `I`.
- The selected processor must be able to accept `I`.
- The processor's result must be assignable to `O`.

Example where multiple processors return different subtypes:

```java
public sealed interface PaymentResult
        permits CardPaymentResult, BankTransferResult {
    String paymentId();
}

public record CardPaymentResult(
        String paymentId,
        String authorizationCode) implements PaymentResult {
}

public record BankTransferResult(
        String paymentId,
        String bankReference) implements PaymentResult {
}
```

The composite can declare its output as `PaymentResult`, while each delegate returns a specific subtype. The downstream writer can accept `PaymentResult` and classify further by subtype or business field.

Do not cast arbitrarily inside the classifier. If a delegate has incompatible input/output types, the error might only surface when a specific branch runs. Use explicit generic types and a shared output type that has business meaning.

### Processor Returning null

Just like a regular `ItemProcessor`, the selected delegate processor can return `null` to filter an item. When it does, the item is not passed to the step's writer.

Distinguish two cases:

- Classifier returns `null`: there is no delegate to execute, which is usually a configuration/routing error.
- Selected processor returns `null`: the item is filtered according to Spring Batch semantics.

If filtering is valid behavior, track `filterCount` and design appropriate metrics. Do not use a classifier returning `null` to represent filtering.

## Multi-Layer Processors and Composite Processors

`ClassifierCompositeItemProcessor` selects one processor from among its delegates. It differs from `CompositeItemProcessor`, which executes a chain of processors sequentially.

Example:

```text
CompositeItemProcessor:
Input -> Normalize -> Validate -> Enrich -> Output
```

```text
ClassifierCompositeItemProcessor:
                 Input
                   |
               Classifier
                /      \
          Processor A  Processor B
                \      /
                 Output
```

Both patterns can be combined. For example, a classifier selects a separate pipeline for each input type, while each pipeline is a `CompositeItemProcessor` consisting of normalize, validate, and enrich:

```java
ItemProcessor<OrderInput, Order> domesticPipeline =
        new CompositeItemProcessorBuilder<OrderInput, Order>()
                .delegates(domesticNormalizer, domesticValidator, domesticEnricher)
                .build();
```

The classifier returns `domesticPipeline` or `internationalPipeline`. This approach is useful when different input types have multi-step processing differences while still sharing a single output contract.

Do not build a long composite chain if the branches actually only need one differing processor. Choose a structure that accurately reflects the business logic so it is easy to understand and test.

## ClassifierCompositeItemWriter

`ClassifierCompositeItemWriter<T>` is a composite `ItemWriter`. It classifies each item in a chunk and routes the item to the selected writer.

```text
                 Chunk<Order>
                       |
                       v
                   Classifier
                       |
             +---------+---------+
             |                   |
             v                   v
       Domestic writer     International writer
             |                   |
             v                   v
       domestic_orders      foreign_orders
```

Unlike the composite processor, the composite writer performs routing for each output item in the chunk. Items can be grouped by delegate writer; each writer receives the portion of the chunk intended for it.

### Example: Selecting a Writer by Order Type

Suppose the output model is:

```java
public record Order(
        String orderId,
        BigDecimal amount,
        String currency,
        boolean international) {
}
```

Two writers can write to two different tables:

```java
@Bean
JdbcBatchItemWriter<Order> domesticOrderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("INSERT INTO domestic_orders(order_id, amount) VALUES (?, ?)")
            .itemPreparedStatementSetter((order, ps) -> {
                ps.setString(1, order.orderId());
                ps.setBigDecimal(2, order.amount());
            })
            .build();
}

@Bean
JdbcBatchItemWriter<Order> internationalOrderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("INSERT INTO international_orders(order_id, amount, currency) VALUES (?, ?, ?)")
            .itemPreparedStatementSetter((order, ps) -> {
                ps.setString(1, order.orderId());
                ps.setBigDecimal(2, order.amount());
                ps.setString(3, order.currency());
            })
            .build();
}
```

Classifier selecting the writer:

```java
@Bean
Classifier<Order, ItemWriter<? super Order>> orderWriterClassifier(
        ItemWriter<Order> domesticOrderWriter,
        ItemWriter<Order> internationalOrderWriter) {

    return order -> order.international()
            ? internationalOrderWriter
            : domesticOrderWriter;
}

@Bean
ClassifierCompositeItemWriter<Order> orderRoutingWriter(
        Classifier<Order, ItemWriter<? super Order>> orderWriterClassifier) {

    return new ClassifierCompositeItemWriterBuilder<Order>()
            .classifier(orderWriterClassifier)
            .build();
}
```

The composite writer can be attached to the step with `.writer(orderRoutingWriter)`, just like a regular writer.

### Attaching the Composite Writer to a Step

```java
@Bean
Step routeOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ClassifierCompositeItemWriter<Order> orderRoutingWriter) {

    return new StepBuilder("routeOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderRoutingWriter)
            .build();
}
```

The step only knows about one writer, `orderRoutingWriter`. The classifier and delegates are responsible for choosing the destination for each item.

## Writers Are Invoked in Groups

`ClassifierCompositeItemWriter` does not mean every item triggers a separate writer call. It classifies the items in the chunk, groups items by delegate writer, and then calls the corresponding writer with that group of items.

For example, if a chunk contains:

```text
[D-1, I-1, D-2, D-3, I-2]

Domestic writer receives:      [D-1, D-2, D-3]
International writer receives: [I-1, I-2]
```

This allows delegate writers to continue using batch writes effectively. Item order within a group generally follows the order they appeared in the chunk, but you should not rely on the invocation order across delegate groups if the implementation uses a map to group writers. If the business logic requires a global ordering across destinations, design an explicitly ordered sequential write mechanism or split into separate steps.

Can a delegate writer receive an empty chunk? Under standard routing, only delegates that have classified items are called. Do not rely on an empty callback to trigger side effects; use a listener or a separate step for work that must always run.

## Selecting a Delegate by Multiple Conditions

A classifier can use multiple properties to decide the branch. For example, orders can be classified by country, amount threshold, and sales channel:

```java
@Bean
Classifier<OrderInput, ItemProcessor<?, ? extends Order>> orderClassifier(
        ItemProcessor<OrderInput, Order> domesticProcessor,
        ItemProcessor<OrderInput, Order> highValueProcessor,
        ItemProcessor<OrderInput, Order> internationalProcessor) {

    return input -> {
        if (!"VN".equalsIgnoreCase(input.countryCode())) {
            return internationalProcessor;
        }
        if (input.amount().compareTo(new BigDecimal("100000000")) >= 0) {
            return highValueProcessor;
        }
        return domesticProcessor;
    };
}
```

Condition ordering is part of the business logic. A high-value international order will take the international branch because that condition is checked first. Changing the order can send an item down a different branch.

With multiple conditions, extract a clearly named classification function:

```java
private Route classifyOrder(OrderInput input) {
    if (input.countryCode() == null) {
        return Route.INVALID;
    }
    if (!"VN".equalsIgnoreCase(input.countryCode())) {
        return Route.INTERNATIONAL;
    }
    if (input.amount().compareTo(HIGH_VALUE_LIMIT) >= 0) {
        return Route.HIGH_VALUE;
    }
    return Route.DOMESTIC;
}
```

Then the classifier maps `Route` to a delegate. This makes it easy to unit test the decision logic independently of Spring Batch.

## Default Branches and Invalid Data

A classifier needs to define behavior for every case. You can choose one of the following approaches:

- A default delegate handles items that do not belong to any special branch.
- A reject processor/writer branch records invalid data.
- Throw a meaningful exception when an input cannot be classified.
- Perform required validation before the classifier to reject inputs missing information.

Example:

```java
return input -> switch (input.channel()) {
    case "WEB" -> webProcessor;
    case "STORE" -> storeProcessor;
    case "PARTNER" -> partnerProcessor;
    default -> throw new UnsupportedOperationException(
            "Unsupported channel: " + input.channel());
};
```

If `channel` can be null, handle it explicitly before the switch. Do not let a `NullPointerException` act as an implicit routing mechanism.

For invalid data that still needs to be recorded as rejected, you can choose a `rejectProcessor` that returns a subtype/result with a reject status or route to a reject writer. If a processor returns `null`, the item is filtered and does not reach the writer; that is not equivalent to writing a reject record.

## Should You Route in the Processor or the Writer?

Classification should be placed at the layer that matches the business decision:

| Question | Appropriate routing layer |
| --- | --- |
| Does each input type require different transformation/validation rules? | `ClassifierCompositeItemProcessor` |
| Are items already normalized but need to be written to different destinations? | `ClassifierCompositeItemWriter` |
| Are both different processing rules and different write destinations needed? | Both can be used, with a separate classifier at each layer |
| Does the entire job flow differ based on launch parameters? | A job flow/decider or separate steps may be more appropriate |
| Must a single item be written to all destinations? | `CompositeItemWriter`, not a classifier writer |

Do not route in the writer if the difference is actually calculation or validation rules. Conversely, do not duplicate processors just to pick a different target table if the output model already carries enough information and the transformation logic is the same.

## Comparison with CompositeItemProcessor and CompositeItemWriter

The composite names look similar, but their semantics differ:

| Component | Behavior |
| --- | --- |
| `CompositeItemProcessor` | Runs multiple processors in sequence; the output of the previous processor is the input to the next |
| `ClassifierCompositeItemProcessor` | Selects one processor per input item |
| `CompositeItemWriter` | Sends the same chunk to multiple configured delegate writers |
| `ClassifierCompositeItemWriter` | Classifies each item and sends the item to the selected writer |

Example:

```text
CompositeItemWriter:
  item A --> database writer
         --> audit file writer
```

```text
ClassifierCompositeItemWriter:
  item A --> domestic writer
  item B --> international writer
```

If an item must be written simultaneously to both a business table and an audit file, `CompositeItemWriter` is usually a better fit. If an item should only be written to one of several destinations depending on its properties, `ClassifierCompositeItemWriter` is a better fit.

## Registering Streams for Delegate Writers

Delegate writers can be stateful writers, such as a `FlatFileItemWriter` implementing `ItemStream` to save checkpoints. `ClassifierCompositeItemWriter` is used in `.writer(...)`, but you should not assume every internal `ItemStream` delegate automatically has its lifecycle managed by the step.

If a delegate is not automatically forwarded or registered by the composite, register the stream explicitly:

```java
return new StepBuilder("routeOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderRoutingWriter)
        .stream(domesticFileWriter)
        .stream(internationalFileWriter)
        .build();
```

On restart, each writer needs to receive the right `ExecutionContext` and restore its own resource/state. Give writers distinct and stable names so state keys do not collide. If a delegate writer is a JDBC writer that does not need separate state, do not add `.stream(...)` just because it is a delegate; only register components that actually implement `ItemStream` and require lifecycle management.

If a delegate both has its lifecycle forwarded by a wrapper and is registered directly, callbacks can be invoked twice. Establish a single stream-management path.

## Transactions with Writer Routing

A classifier writer is typically invoked inside the chunk step's transaction. If all delegates write to the same datasource and share the same transaction manager, database operations can participate in the same chunk transaction.

However, if delegates write to different resources, a single database transaction does not automatically produce an atomic commit across all of them:

| Delegate | Transaction behavior |
| --- | --- |
| Two JDBC writers using the same datasource/transaction | Can participate together in the chunk transaction |
| A JDBC writer using a different datasource | May have an independent transaction |
| File writer | File I/O does not automatically participate in a JDBC transaction |
| Message writer | Broker acknowledgement/transaction has its own semantics |
| HTTP/API writer | External side effects usually do not roll back with the chunk |

For example, the domestic writer succeeds in writing to the database and then the international writer throws an exception. If both use the same transactional resource, the chunk can roll back both sets of database changes. If one delegate has already sent a message or written a file outside the transaction, that side effect may remain even when the chunk rolls back.

With multiple output destinations, consider a transactional outbox, staging files, idempotency keys, or a publish/finalize step after the chunk/job finishes. Do not treat a classifier composite as a distributed transaction coordinator.

## Retry, Skip, and Idempotency

The classifier and delegates can be invoked multiple times during retry, rollback, or skip processing. Therefore:

- The classifier should be deterministic and side-effect-free.
- Processor delegates should avoid non-idempotent side effects.
- Writer delegates must handle replay safely by transaction/business key.
- Retry policies should only apply to recoverable exceptions.
- Skip policies must distinguish data errors from infrastructure errors.

For example, if the classifier calls an API to look up customer tier before choosing a processor, every retry may repeat that API call. You should include routing information in the item from the reader/enrichment step or use an appropriate cached/idempotent service, rather than producing side effects in `classify`.

For writers, a delegate may have already written part of the output outside a transaction before throwing an exception. When Spring Batch retries or reprocesses the chunk, the same item can reach the delegate again. Use unique constraints, upserts, event IDs, or idempotency keys to prevent duplicates.

## Thread Safety and Parallel Processing

`ClassifierCompositeItemWriter` should not be assumed thread-safe just because it is a Spring Batch component. If a step runs multithreaded or multiple executions share an instance, the classifier and delegate writers must be concurrency-safe.

Checklist:

- Does the classifier hold shared mutable state?
- Are the delegate writers thread-safe?
- Can multiple threads write to the same file or the same mutable buffer?
- Does `@StepScope` create separate instances at the right execution scope?
- Does each partition have its own writer/resource, or are they contending over a single output path?
- Do transactions share connections or resources inappropriately?

A stateless classifier based on immutable fields of an item is generally safer than a classifier that updates a counter or stores `currentRoute` in a field. For stateful delegate writers, use separate instances/resources per step or per partition if needed.

If global item ordering matters, parallel routing and grouping by writer can cause the order observed at different destinations to no longer match the input order. Design sequence numbers or an ordered merge step if downstream requires it.

## XML Configuration

With Java configuration, you can create composites using builders or beans and inject them into the step. In XML, you can also declare the classifier and composite processor/writer as beans and reference them in a chunk step. The XML structure and class names must be compatible with the Spring Batch version in use.

Example declaring a classifier bean and composite processor in JavaBean style:

```xml
<bean id="orderProcessorClassifier"
      class="com.example.batch.OrderProcessorClassifier">
    <property name="domesticProcessor" ref="domesticOrderProcessor"/>
    <property name="internationalProcessor" ref="internationalOrderProcessor"/>
</bean>

<bean id="orderProcessor"
      class="org.springframework.batch.item.support.ClassifierCompositeItemProcessor">
    <property name="classifier" ref="orderProcessorClassifier"/>
</bean>

<batch:step id="processOrdersStep">
    <batch:tasklet>
        <batch:chunk reader="orderReader"
                     processor="orderProcessor"
                     writer="orderWriter"
                     commit-interval="100"/>
    </batch:tasklet>
</batch:step>
```

`OrderProcessorClassifier` is an application class implementing `Classifier<OrderInput, ItemProcessor<?, ? extends Order>>` with setters for the two delegates. The composite processor receives the classifier via a property. For Spring Batch versions with different constructor/builder APIs, use configuration compatible with your dependency.

Similarly, you can declare `ClassifierCompositeItemWriter` and a classifier writer bean, then reference the composite with `writer="orderRoutingWriter"`. If a delegate writer implements `ItemStream`, declare streams using the `batch:streams` syntax supported by the XSD version or use Java configuration `.stream(...)`.

You do not need XML just to use a classifier; Java configuration is usually more convenient when the classifier is created from a lambda or method reference.

## Testing the Classifier Independently

A classifier should be tested in isolation to verify each item type routes to the right delegate.

```java
@Test
void routesInternationalOrderToInternationalProcessor() {
    ItemProcessor<OrderInput, Order> domestic = input -> domesticOrder;
    ItemProcessor<OrderInput, Order> international = input -> internationalOrder;

    Classifier<OrderInput, ItemProcessor<?, ? extends Order>> classifier =
            input -> input.international() ? international : domestic;

    assertSame(international, classifier.classify(
            new OrderInput("O-2", "US", new BigDecimal("100.00"))));
}
```

This test only checks the routing decision. You should add tests for domestic inputs, null/invalid values, and the default branch.

If the classifier uses multiple conditions, add tests for boundary values, such as amounts equal to the threshold, country codes with different casing, and unsupported channels.

## Testing ClassifierCompositeItemProcessor

You can mock delegate processors to verify that the composite invokes only one branch:

```java
@Test
void compositeProcessorInvokesSelectedDelegate() throws Exception {
    OrderInput input = new OrderInput(
            "O-2", "US", new BigDecimal("100.00"));

    when(internationalProcessor.process(input)).thenReturn(expectedOrder);

    Order result = compositeProcessor.process(input);

    assertEquals(expectedOrder, result);
    verify(internationalProcessor).process(input);
    verifyNoInteractions(domesticProcessor);
}
```

The test should verify that the expected output is returned and the unselected processor is never called. Add a case where a delegate returns `null` to verify filtering according to processor semantics.

## Testing ClassifierCompositeItemWriter

For writers, create mock delegates and a chunk containing items belonging to multiple routes:

```java
@Test
void routesItemsToTheirWriterGroups() throws Exception {
    Chunk<Order> chunk = new Chunk<>(List.of(
            domesticOrder1,
            internationalOrder1,
            domesticOrder2));

    routingWriter.write(chunk);

    verify(domesticWriter).write(argThat(items ->
            items.getItems().equals(
                    List.of(domesticOrder1, domesticOrder2))));

    verify(internationalWriter).write(argThat(items ->
            items.getItems().equals(List.of(internationalOrder1))));
}
```

This is an example of testing grouping; the matcher and `Chunk` constructor must match the Spring Batch/Mockito versions in your project. Do not assert the invocation order between delegates if the implementation does not guarantee group ordering. Assert the set of items each delegate receives.

## Integration Testing with JobLauncherTestUtils

Unit testing a classifier does not prove that the composite writer/processor is wired properly into the step. An integration test should run a small job with input containing multiple item types.

Test scenario:

1. Prepare input containing at least two item types.
2. Launch the job with test-specific identifying `JobParameters`.
3. Verify `JobExecution` and the step reach the expected status.
4. Verify the processor delegates are invoked for each input type.
5. Verify data is written to the right target tables/files.
6. Verify no items are lost or accidentally written to both branches.
7. Check counters and reject output for the invalid branch.

Example database assertion:

```java
assertEquals(2, jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM domestic_orders", Integer.class));

assertEquals(1, jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM international_orders", Integer.class));
```

These counts depend on the fixture. You should query by business key to confirm specific items landed at the right destination, rather than only checking total row counts.

## Testing Transactions and Rollback

Create a delegate writer that throws an exception after being invoked and verify that the chunk transaction rolls back for database writers sharing the same transaction resource. Then check:

- Current chunk data is gone if the transaction rolled back.
- Previously committed chunk data remains intact.
- The job/step has the expected status per the fault-tolerance policy.
- Restart or retry does not create duplicates.

If a delegate writes files or sends messages, the test should simulate out-of-transaction side effects and verify that idempotency/staging/outbox handles replay. Do not conclude all delegates rolled back solely because a database table has no rows.

## Testing ItemStream Delegates and Restart

If a delegate writer is a `FlatFileItemWriter` or a custom `ItemStreamWriter`, integration tests should verify that the stream is registered and state is restored:

1. Run the job so several chunks commit.
2. Cause the step to fail after one group of writers has already written.
3. Restart with the same identifying parameters and the same output resources.
4. Verify the delegate writer reopens from the appropriate checkpoint.
5. Check that the output has no missing items, no duplicates, and no data mixed across routes.

Keep writer names stable, use distinct `ExecutionContext` keys, and register `.stream(...)` if the delegate's lifecycle is not forwarded by the wrapper/composite.

## Common Pitfalls

### Classifier Returns the Wrong Delegate

Wrong routing conditions or incorrect if/else ordering can send items down another branch. Test every route and boundary value.

### Classifier Returns null

The composite has no delegate to invoke. Define a default or throw a meaningful exception when input is invalid.

### Confusing null from a Processor with null from a Classifier

A processor returning `null` means filtering the item; a classifier returning `null` is usually a routing error. Do not conflate the two semantics.

### Incompatible Generic Types

Delegates accept/return types incompatible with the composite. Use a meaningful common interface/supertype and avoid unchecked casts.

### Using CompositeItemProcessor When Only One Branch Should Run

Composite processor runs all delegates sequentially; classifier processor picks one delegate. Choose the right semantics.

### Using CompositeItemWriter When an Item Should Go to Only One Destination

Composite writer can send the same item to multiple delegates. Classifier writer is for exclusive per-item routing.

### Using a Classifier Writer While Expecting a Fixed Group Order

The writer may group items by delegate, and the group invocation order is not a business contract. Use separate steps/flows or an explicitly coordinated ordered writer if needed.

### Putting Side Effects Inside the Classifier

The classifier may be called again during retry or replay. Keep the classifier stateless and only decide the delegate.

### Forgetting to Register Delegate Writer Streams

A writer hidden inside a composite may not receive `open/update/close`. Register streams explicitly or forward the lifecycle.

### Non-Idempotent Delegate Writers

Rollback/retry can call the writer again. Use proper transactions, unique keys, upserts, outbox, or staging.

### Sharing Stateful Delegates Across Steps/Partitions

Multiple executions may contend over the same file/resource or mutable state. Isolate instances/resources and verify thread safety.

## Design Principles

When using a classifier to select a processor or writer, determine:

1. Is routing based on the input item or the output item?
2. Are classification conditions clear, deterministic, and side-effect-free?
3. Does every branch have a valid delegate and defined default/error behavior?
4. Do processor delegates have compatible input/output types?
5. Do writer delegates accept the right output type and receive only items belonging to their route?
6. Do you need to pick one branch or send the item to multiple writers?
7. Is there any invocation-order dependency between delegates?
8. Do delegates have appropriate transaction, idempotency, and thread-safety properties?
9. Do any writer delegates implement `ItemStream` requiring separate lifecycle registration?
10. Can retry/skip/restart invoke the classifier or delegates again?
11. Have unit and integration tests verified routing, output, rollback, and restart?

`ClassifierCompositeItemProcessor` fits when each input needs one processing path out of multiple processors. `ClassifierCompositeItemWriter` fits when each output item needs to go to a selected writer. Keep the classifier simple, deterministic, and stateless; use a common type for delegates; define a default route; and ensure writer delegates have proper transaction/idempotency/lifecycle handling. Test each branch with a realistic job to be certain no items are lost, duplicated, or misrouted.

## Summary

`Classifier<C, T>` takes an item and returns the selected delegate. `ClassifierCompositeItemProcessor<I, O>` selects one processor per input and returns its result; a processor returning `null` means filtering. `ClassifierCompositeItemWriter<T>` classifies each output item, groups items by writer, and passes each group to the appropriate delegate. Use a classifier processor for differences in transformation/validation, and a classifier writer for differences in write destination; use `CompositeItemProcessor` or `CompositeItemWriter` when you need to run multiple delegates sequentially or write to multiple destinations. Define a default/error route, keep the classifier stateless, ensure generic type compatibility, and do not rely on invocation order across writer groups. Verify transactions, retry, idempotency, thread safety, and delegate writer stream registration so routing remains accurate under rollback or restart.
