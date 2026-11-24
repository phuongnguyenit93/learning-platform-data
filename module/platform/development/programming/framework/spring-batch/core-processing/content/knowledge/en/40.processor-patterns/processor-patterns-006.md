# Classifier processor

In Spring Batch, an `ItemProcessor<I, O>` typically receives an input item, validates or transforms it, and returns an output item. When the same step must process multiple input types according to different rules, a single processor can become overly complex with many `if/else` branches. The **classifier processor** pattern solves this problem by selecting a delegate processor for each item.

Spring Batch provides `ClassifierCompositeItemProcessor<I, O>`. This component is itself an `ItemProcessor<I, O>`, but internally it uses a `Classifier` to decide which delegate will process the current item. The step only sees one composite processor; the specific processing rules are split into smaller processors.

For example, a job receives both domestic and international orders. Domestic orders require calculating tax according to local regulations; international orders require currency conversion and import fee calculation. The classifier inspects each input's details, selects the corresponding processor, and returns results of the same output type for the writer to process next.

## What is a classifier processor?

A classifier processor organizes the pipeline into two steps:

1. Classify the input item to select a delegate.
2. Call `process(item)` on the selected delegate and return its result.

Processing flow:

```text
                  ItemReader
                      |
                      v
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
       Domestic result     International result
             |                 |
             +--------+--------+
                      |
                      v
                  ItemWriter
```

Only the selected delegate processes that item. The classifier does not transform data itself, does not invoke all processors, and does not write output. It simply returns the component to be invoked.

`ClassifierCompositeItemProcessor` resides in the `org.springframework.batch.item.support` package. It combines two abstractions:

- Spring Batch's `ItemProcessor<I, O>`: processes one item and returns an output.
- Spring's `Classifier<C, T>`: receives an object and selects another object based on the input's content.

For a classifier processor, `C` is typically the input type and `T` is an `ItemProcessor` capable of processing that input.

## When should you use a classifier processor?

This pattern is useful when a single input stream contains multiple groups of items with different processing rules, yet results can still be unified under a single output contract.

Common cases:

- Domestic and international orders have different fee calculations.
- Card payments and bank transfers require different validations.
- Individual and corporate profiles need distinct normalization rules.
- Transactions across different product types have different calculation formulas.
- Messages from multiple event types need conversion into a common result model.
- Legacy data and new data require different converters.

It is not necessary to use a classifier for every condition. If there are only one or two short transformations, a simple processor with a conditional branch may be easier to read. A classifier shines when branches have distinct responsibilities, can be tested independently, or can be reused.

## The Classifier interface

`Classifier<C, T>` has one primary method:

```java
public interface Classifier<C, T> {
    T classify(C classifiable);
}
```

`classify` receives an item and returns a delegate. Example:

```java
Classifier<OrderInput, ItemProcessor<?, ? extends Order>> classifier = input -> {
    if (input.international()) {
        return internationalProcessor;
    }
    return domesticProcessor;
};
```

A classifier can be implemented as a lambda, method reference, or dedicated class. For simple routing logic, an inline lambda makes the conditions easy to spot. For logic with many rules, data checks, or multiple dependencies, a dedicated class is usually easier to test and maintain.

A classifier should be deterministic: the same input and configuration must select the same delegate. Avoid calling APIs, writing to a database, or performing side effects inside `classify`, because the framework may reprocess the item during retries or rollbacks.

## Full example: selecting a processor by order type

Suppose the input has these properties:

```java
public record OrderInput(
        String orderId,
        String countryCode,
        BigDecimal amount) {

    public boolean international() {
        return countryCode != null
                && !"VN".equalsIgnoreCase(countryCode);
    }
}
```

The output is a unified model:

```java
public record ProcessedOrder(
        String orderId,
        BigDecimal payableAmount,
        String currency,
        BigDecimal fee,
        String processingRoute) {
}
```

Two delegate processors both accept `OrderInput` and return `ProcessedOrder`:

```java
@Bean
ItemProcessor<OrderInput, ProcessedOrder> domesticOrderProcessor() {
    return input -> new ProcessedOrder(
            input.orderId(),
            input.amount(),
            "VND",
            calculateDomesticTax(input.amount()),
            "DOMESTIC");
}

@Bean
ItemProcessor<OrderInput, ProcessedOrder> internationalOrderProcessor() {
    return input -> new ProcessedOrder(
            input.orderId(),
            convertToSettlementCurrency(input.amount(), input.countryCode()),
            "USD",
            calculateImportFee(input),
            "INTERNATIONAL");
}
```

The methods `calculateDomesticTax`, `convertToSettlementCurrency`, and `calculateImportFee` contain application-implemented business logic. Both delegates share the same input/output types, so they are interchangeable where the classifier picks a processor.

Create the classifier:

```java
@Bean
Classifier<OrderInput, ItemProcessor<?, ? extends ProcessedOrder>>
orderProcessorClassifier(
        ItemProcessor<OrderInput, ProcessedOrder> domesticOrderProcessor,
        ItemProcessor<OrderInput, ProcessedOrder> internationalOrderProcessor) {

    return input -> input.international()
            ? internationalOrderProcessor
            : domesticOrderProcessor;
}
```

Then configure the composite processor:

```java
@Bean
ClassifierCompositeItemProcessor<OrderInput, ProcessedOrder> orderProcessor(
        Classifier<OrderInput, ItemProcessor<?, ? extends ProcessedOrder>>
                orderProcessorClassifier) {

    ClassifierCompositeItemProcessor<OrderInput, ProcessedOrder> processor =
            new ClassifierCompositeItemProcessor<>();
    processor.setClassifier(orderProcessorClassifier);
    return processor;
}
```

`ClassifierCompositeItemProcessor` executes the delegate returned by the classifier. Setter-based configuration as shown above is straightforward; if your project's Spring Batch version provides a corresponding builder, you can use the builder to configure the same contract.

## Attaching the classifier processor to a step

From the step's perspective, the composite processor is just a regular `ItemProcessor`:

```java
@Bean
Step processOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ClassifierCompositeItemProcessor<OrderInput, ProcessedOrder> orderProcessor,
        ItemWriter<ProcessedOrder> orderWriter) {

    return new StepBuilder("processOrdersStep", jobRepository)
            .<OrderInput, ProcessedOrder>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

The step does not need to know how many delegates exist or what the classification rules are. Routing happens inside the classifier processor, while the writer receives outputs of type `ProcessedOrder`.

If no output is needed for certain items, a delegate can return `null` per `ItemProcessor` semantics; that item will be filtered and not forwarded to the writer. Distinguish this behavior from the classifier returning `null`, which means no delegate was selected and typically causes an error when the composite tries to invoke the processor.

## Classification conditions and rule ordering

A classifier can be based on one attribute or multiple attributes. For example, transactions can be classified by country, sales channel, and value:

```java
return input -> {
    if (input.countryCode() == null) {
        return invalidInputProcessor;
    }
    if (!"VN".equalsIgnoreCase(input.countryCode())) {
        return internationalProcessor;
    }
    if (input.amount().compareTo(HIGH_VALUE_LIMIT) >= 0) {
        return highValueProcessor;
    }
    return domesticProcessor;
};
```

Condition order expresses business priority. In this example, high-value international orders still take the international branch because the international condition is checked first. Changing the order can route an item to a different processor.

With multiple conditions, extract classification logic into a named function or a route enum:

```java
enum OrderRoute {
    DOMESTIC,
    INTERNATIONAL,
    HIGH_VALUE,
    INVALID
}

private OrderRoute classifyOrder(OrderInput input) {
    if (input.countryCode() == null || input.amount() == null) {
        return OrderRoute.INVALID;
    }
    if (!"VN".equalsIgnoreCase(input.countryCode())) {
        return OrderRoute.INTERNATIONAL;
    }
    if (input.amount().compareTo(HIGH_VALUE_LIMIT) >= 0) {
        return OrderRoute.HIGH_VALUE;
    }
    return OrderRoute.DOMESTIC;
}
```

Then map `OrderRoute` to delegates. This lets you test rules independently of Spring Batch and avoids a long, hard-to-read lambda.

### Handling the default route

Every valid input must have a defined branch. You can use:

- A default processor for common types.
- A dedicated processor for unclassified data.
- A reject processor to produce a structured error result.
- An explicit exception if the input violates the contract and cannot proceed.

Do not return `null` from a classifier to represent a default or filter. If no delegate matches, return a default processor or throw a specific business exception.

Example with `switch`:

```java
return input -> switch (input.channel()) {
    case "WEB" -> webProcessor;
    case "STORE" -> storeProcessor;
    case "PARTNER" -> partnerProcessor;
    default -> unsupportedChannelProcessor;
};
```

If `channel` can be null, check before switching. Do not let `NullPointerException` act as an implicit routing mechanism.

## Classifier returning null vs. processor returning null

These two cases have different semantics:

| Where does null appear? | Meaning | Expected behavior |
| --- | --- | --- |
| `classifier.classify(item)` | No delegate selected | Configuration/routing error; no processor to call |
| `delegate.process(item)` | Processor decides to filter item | Item is not forwarded to the writer |

Example of a filtering processor:

```java
ItemProcessor<OrderInput, ProcessedOrder> skipCancelledProcessor = input -> {
    if (input.cancelled()) {
        return null;
    }
    return mapActiveOrder(input);
};
```

This is a valid filter if business rules dictate producing no output for cancelled orders. Spring Batch increments the filter count accordingly. If you need to track excluded items, record metrics or use an appropriate audit mechanism; do not make the classifier return null to filter.

## Delegate generic types

Selected delegates must be compatible with the composite processor's input and output types.

With `ClassifierCompositeItemProcessor<I, O>`:

- The classifier accepts an `I` or a compatible supertype.
- The delegate must be able to accept `I`.
- The delegate's result must be assignable to `O`.

If all delegates accept `OrderInput` and return `ProcessedOrder`, generics are straightforward. If delegates return different subtypes, define a common interface or sealed hierarchy.

Example:

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

Processors can return `CardPaymentResult` or `BankTransferResult`, while the composite declares output type `PaymentResult`. The downstream writer receives the common type and can handle subtypes as needed.

Avoid raw types or unchecked casts in the classifier. Generic errors can be hidden at compile time and only surface when a specific branch runs. If two branches have unrelated outputs, standardize onto a single output DTO or split into separate steps.

## Splitting processors into small components

Each delegate should handle one clear responsibility. Example:

```text
OrderInput
   |
   +--> DOMESTIC ------> DomesticTaxProcessor
   |
   +--> INTERNATIONAL -> InternationalFeeProcessor
   |
   +--> WHOLESALE -----> WholesaleDiscountProcessor
```

Delegates can be declared as separate beans, injected with required services, and unit tested independently. The classifier should not contain tax formulas, currency conversion rules, or detailed validation logic; it only selects a processor based on item attributes.

This makes it easy to change one branch's rules with minimal impact on other branches. A processor can also be reused across multiple jobs if input/output contracts match and the component holds no execution-specific state.

## Combining classifier with CompositeItemProcessor

`ClassifierCompositeItemProcessor` selects one processor. `CompositeItemProcessor` runs multiple processors sequentially. Both components can be combined when each route needs its own pipeline.

Comparison:

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

For example, both domestic and international orders need data normalization, while subsequent calculation steps differ. Two pipelines can be created:

```java
ItemProcessor<OrderInput, ProcessedOrder> domesticPipeline =
        new CompositeItemProcessorBuilder<OrderInput, ProcessedOrder>()
                .delegates(
                        domesticNormalizer,
                        domesticValidator,
                        domesticTaxProcessor)
                .build();

ItemProcessor<OrderInput, ProcessedOrder> internationalPipeline =
        new CompositeItemProcessorBuilder<OrderInput, ProcessedOrder>()
                .delegates(
                        internationalNormalizer,
                        internationalValidator,
                        internationalFeeProcessor)
                .build();
```

The classifier returns one of the two pipelines. Each pipeline sequentially executes its internal delegate processors. This approach is helpful when each item type has multiple distinct steps while sharing the same output contract.

If all branches share common normalization and validation, place those shared steps before or after the classifier instead of duplicating them in every pipeline. Structure the pipeline so shared rules have a single source of definition.

## Distinguishing from a processor with many if/else branches

A single processor can be written as:

```java
public ProcessedOrder process(OrderInput input) {
    if (input.international()) {
        return processInternational(input);
    }
    return processDomestic(input);
}
```

This works well when logic is short, branches are few, and reuse is unnecessary. Classifier composite is a better fit when:

- Each branch has substantial logic or its own dependencies.
- Branches need independent testing.
- Delegates can be reused.
- The number of input types is expected to grow.
- Each branch needs its own configuration or its own pipeline.

Do not create dozens of one-line processors just to replace a simple `if/else`. The goal is separation of responsibilities, not inflating class counts unnecessarily.

## Validation before and after classification

A classifier often relies on input fields. If a required field is missing or malformed, decide where validation sits.

One approach is to validate common invariants before the classifier runs:

```text
Reader
  |
  v
Common validation processor
  |
  v
Classifier processor
  |
  +--> Domestic processor
  +--> International processor
```

For instance, `orderId` and `amount` must exist for all order types; validate them prior to routing. Then each delegate validates branch-specific rules such as currency, country code, or tax identifier.

If the classifier must classify invalid inputs as well, provide an `invalidInputProcessor` to build a reject result. The key is never letting a null field cause an unintentional error inside the classifier.

Validation should distinguish:

- Structural errors: unable to parse input, usually handled in the reader.
- Common errors: missing fields required across all item types.
- Route-specific errors: fields valid for one branch but invalid for another.
- Infrastructure errors: external dependencies temporarily unavailable, potentially retryable.

## Exceptions, retry, and skip

If a delegate throws an exception, the exception propagates through `ClassifierCompositeItemProcessor` up to the step. The step can apply retry, skip, or fail according to its fault-tolerance policy.

Example retrying transient service errors and skipping business data errors:

```java
return new StepBuilder("processOrdersStep", jobRepository)
        .<OrderInput, ProcessedOrder>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(classifierProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientPricingException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .build();
```

`TransientPricingException` and `InvalidOrderException` are illustrative application exceptions. Retry only recoverable errors; permanent data errors should typically be rejected/skipped by policy. Do not catch exceptions inside a delegate and return dummy output to keep the step going if the item was not actually processed properly.

The classifier should avoid side effects. If the classifier calls an external service and that service fails, retries can invoke the classifier multiple times. It is better to include routing data in the input or perform enrichment in a processor with a clear retry policy.

### Retries may invoke the delegate again

Processors should generally be deterministic and free of non-idempotent side effects. If a processor sends emails, creates transactions, or calls state-mutating APIs, retries can repeat those actions multiple times.

Place side effects in the writer or an integration step with idempotency keys/outbox. Processors should focus on transforming data and producing results.

## Filtering items per branch

A delegate can return `null` to filter an item. This can differ by route:

- Domestic processor filters cancelled orders.
- International processor filters orders missing customs documents.
- Wholesale processor always returns a result after applying discounts.

The step's filter count reflects items for which the processor returned `null`. If you need to distinguish filter reasons, record per-route metrics or produce audit/reject output before returning null. Do not turn an unclassified error into a silent filter.

If the business needs to process excluded items, return an output with status `REJECTED` instead of null so the writer records it to a reject table/file. Choose based on auditability requirements and downstream contracts.

## XML configuration

You can declare the classifier and composite processor as beans and reference the composite inside a chunk step in XML.

Classifier bean:

```xml
<bean id="orderProcessorClassifier"
      class="com.example.batch.OrderProcessorClassifier">
    <property name="domesticProcessor" ref="domesticOrderProcessor"/>
    <property name="internationalProcessor" ref="internationalOrderProcessor"/>
</bean>
```

Composite processor:

```xml
<bean id="classifierProcessor"
      class="org.springframework.batch.item.support.ClassifierCompositeItemProcessor">
    <property name="classifier" ref="orderProcessorClassifier"/>
</bean>
```

Step registration:

```xml
<batch:step id="processOrdersStep">
    <batch:tasklet>
        <batch:chunk reader="orderReader"
                     processor="classifierProcessor"
                     writer="orderWriter"
                     commit-interval="100"/>
    </batch:tasklet>
</batch:step>
```

`OrderProcessorClassifier` is an application class implementing `Classifier<OrderInput, ItemProcessor<?, ? extends ProcessedOrder>>` and exposing setters for the delegates. Class names and namespace parsers must match your Spring Batch version. With Java configuration, lambdas are usually shorter; XML is useful when a project manages wiring centrally in configuration files.

## Delegate scope and lifecycle

Classifier composite does not automatically make delegates step-scoped. If a delegate needs `JobParameters`, `StepExecution`, or per-run state, declare the bean with `@StepScope` or an appropriate scope.

Example:

```java
@Bean
@StepScope
ItemProcessor<OrderInput, ProcessedOrder> internationalProcessor(
        @Value("#{jobParameters['exchangeRate']}") BigDecimal exchangeRate) {

    return input -> convertInternationalOrder(input, exchangeRate);
}
```

The composite processor can hold proxies of scoped beans and invoke the delegate while the step runs. Do not instantiate delegates with `new` if they require dependency injection, scoped proxies, or Spring bean lifecycle management.

### Stateful delegates

Processors should usually be stateless. If a delegate holds mutable state, such as counters or caches changing per item, examine:

- Do multiple step executions share the same singleton bean?
- Is a multi-threaded step or partitioning enabled?
- Must state be restored on restart?
- Does the state belong to the item or the execution?

Do not use singleton fields to store `currentOrder` or the current route. If state must survive restarts, store it in `ExecutionContext` via an `ItemStream` component or an appropriate persistence store; do not rely on processor memory.

## Thread safety and parallel processing

A classifier processor can be called from multiple threads if the step is configured as multi-threaded or executions share beans. A stateless classifier lambda reading immutable fields is usually easier to keep safe than a classifier mutating shared variables.

Guidelines:

- Do not store the current item in a classifier field.
- Do not update shared mutable counters without synchronization.
- Singleton delegates must be thread-safe or stateless.
- Delegates with dedicated resources/state should use an execution/partition-specific scope or instance.
- Do not share a non-thread-safe mutable formatter/parser across multiple workers.
- If metrics are needed, use Micrometer counters or an appropriate thread-safe mechanism.

Partitioning is often easier to reason about when each worker gets its own processor/delegate instances and input partition. While the classifier selects delegates, it does not create parallelism itself; concurrency is determined by the step/partition configuration.

## Performance and routing cost

A classifier typically incurs negligible cost compared to I/O or processor logic. However, a complex classifier calling multiple services or running per-item queries defeats the benefit of simple routing.

To maintain performance:

- Use fields already present on the item for classification when possible.
- Avoid database queries inside `classify` for every item.
- If enrichment is needed, consider a dedicated processor with caching or batch lookups.
- Keep routing rules short and deterministic.
- Measure per-delegate durations to spot a slow branch.
- Avoid instantiating new processor objects on every `classify` call.

Delegates are typically injected as reusable beans. If each item needs different configuration, pass that data in the input/context instead of creating thousands of processor instances.

## Testing the classifier independently

The classifier should be tested separately to verify all input types route to the correct delegate.

```java
@Test
void selectsInternationalProcessorForForeignOrder() {
    Classifier<OrderInput, ItemProcessor<?, ? extends ProcessedOrder>> classifier =
            input -> input.international()
                    ? internationalProcessor
                    : domesticProcessor;

    ItemProcessor<?, ? extends ProcessedOrder> selected =
            classifier.classify(new OrderInput(
                    "O-100", "US", new BigDecimal("100.00")));

    assertSame(internationalProcessor, selected);
}
```

Include tests for each branch and boundary values:

- Uppercase/lowercase country codes.
- Null or unsupported country codes.
- Amounts exactly on classification thresholds.
- Channels outside the allowlist.
- Missing required fields.

If using a route enum, test the `classifyOrder` function directly to verify rule priority ordering.

## Testing ClassifierCompositeItemProcessor

Beyond the classifier, verify that the composite actually invokes the selected delegate and returns the delegate's result.

```java
@Test
void compositeInvokesOnlySelectedProcessor() throws Exception {
    OrderInput input = new OrderInput(
            "O-200", "US", new BigDecimal("250.00"));

    when(internationalProcessor.process(input)).thenReturn(expectedOrder);

    ClassifierCompositeItemProcessor<OrderInput, ProcessedOrder> composite =
            new ClassifierCompositeItemProcessor<>();
    composite.setClassifier(candidate -> candidate.international()
            ? internationalProcessor
            : domesticProcessor);

    ProcessedOrder result = composite.process(input);

    assertEquals(expectedOrder, result);
    verify(internationalProcessor).process(input);
    verifyNoInteractions(domesticProcessor);
}
```

This test proves an international input invokes only the international processor. Add tests for domestic input, delegates returning null, and delegates throwing exceptions.

### Testing filters

Have the selected delegate return `null`; verify the composite returns `null` and the step does not pass that item to the writer. Check filter count when running step integration tests.

### Testing exceptions

Have the delegate throw an exception; verify the composite propagates the error to the caller. Then test retry/skip policies at the step level, since composite unit tests do not prove fault-tolerance configuration works.

## Integration testing with step/job

Unit tests only verify routing. Integration tests should run a real step with inputs spanning multiple routes:

1. Create fixtures including domestic, international, high-value, and invalid items.
2. Launch the job with distinct identifying `JobParameters`.
3. Verify `JobExecution` and `StepExecution` have expected statuses.
4. Inspect outputs for each branch.
5. Verify filtered items do not reach the writer.
6. Verify rejected items are stored according to policy.
7. Check read/process/filter/write counts.

Example assertions:

```java
assertEquals(2, jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM domestic_orders", Integer.class));

assertEquals(1, jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM international_orders", Integer.class));
```

Counts depend on the fixture. Check specific business keys to confirm each item entered the right route, rather than checking total row counts alone.

### Testing restarts

If delegate processors are stateless, saving processor state is usually unnecessary. However, queries/readers, inputs, and `JobParameters` used for routing must remain stable across restarts. If a delegate holds dedicated state, test the state lifecycle and keep state out of singleton fields.

Run the step through several chunks, force a step failure, then restart with the same identifying parameters. Verify items are processed by the right branch with no duplicate or missing outputs.

## Common pitfalls

### Classifier returns the wrong processor

Incorrect conditions or rule ordering can route items to the wrong branch. Test every route and boundary value.

### Classifier returns null

The composite has no delegate to call. Define a default processor or throw a meaningful exception.

### Confusing classifier null with processor null

Classifier null is a delegate selection error; processor null filters the item. Handle the two cases separately.

### Incompatible generic types

A delegate does not accept the right input or its output cannot be assigned to the common type. Use a common output interface/DTO and avoid raw types.

### Putting all business logic into the classifier

The classifier turns into a giant processor in disguise. Keep only selection rules in the classifier and move processing logic into delegates.

### Using a classifier for an overly simple condition

Adding extra beans does not make code clearer when each branch is a single assignment. Use a simple processor when appropriate.

### Confusing classifier composite with CompositeItemProcessor

A classifier picks one delegate; a composite processor sequentially runs multiple delegates. Choose the right semantics.

### Delegates with non-idempotent side effects

Retries can re-invoke the processor and duplicate side effects. Keep processors pure or use idempotency/outbox for side effects.

### Singleton delegates holding mutable state

Multiple executions/threads can overwrite each other's state. Use stateless processors or dedicated scopes.

### Classifier calling a service/database per item

Routing becomes a bottleneck and risks repeated side effects on retry. Put classification data in the item or an enrichment stage.

### Failing to test the default branch

New inputs or null fields can fall into the wrong branch. Define a default/error route and test it.

### Testing only the classifier without testing composite/step

The classifier may return the right delegate while step wiring is broken. Run integration tests to verify final output.

## Design principles

When implementing a classifier processor, determine:

1. Which input types require different processing rules?
2. Which fields do classification rules depend on, and are they stable?
3. Is priority ordering among conditions clear?
4. Does every branch have a valid delegate and a default/error route?
5. Do delegates share the input type and a compatible output contract?
6. Is a common DTO/interface needed for output subtypes?
7. Do any branches return `null` to filter, and is that distinguished from classifier null?
8. Should shared logic sit before/after the classifier or repeat in each pipeline?
9. Are delegates managed by Spring with appropriate scope and thread safety?
10. Do processors have side effects that retries could duplicate?
11. Have integration tests verified routing, filtering, exceptions, and outputs?

`ClassifierCompositeItemProcessor` fits well when each item needs exactly one processor from multiple choices. Keep the classifier focused on route decisions, place business logic in delegates, use a common output type, and clearly define default branches. Use `CompositeItemProcessor` inside branches when multiple sequential steps are needed. Keep delegates stateless or isolate state per step execution, avoid non-idempotent side effects, and test both the classifier and the actual step.

## Key takeaways

A classifier processor uses a `Classifier` to choose an `ItemProcessor` delegate for each input. `ClassifierCompositeItemProcessor<I, O>` is wired into a step like a regular processor; it invokes the selected processor and returns the result. The classifier only routes, while delegates perform transformation/validation. Delegates must accept the common input type and return compatible outputs; a shared interface/DTO can be used when branches return subtypes. A delegate returning `null` filters the item, whereas a classifier returning `null` fails to select a processor and typically causes an error. Define default/error routes, keep rules deterministic/stateless, place side effects where they are idempotent, and pick appropriate scopes for delegates. A classifier selects one branch, whereas `CompositeItemProcessor` chains multiple processors sequentially; both patterns can be combined to build dedicated pipelines per item type. Test rules, invoked delegates, filtering, exceptions, and step/job outputs to confirm routing is accurate.
