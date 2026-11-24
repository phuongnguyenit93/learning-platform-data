# Writing a Custom ItemProcessor

In Spring Batch, `ItemProcessor` is the component that receives an item from `ItemReader`, performs item-level processing, and returns an output item for `ItemWriter`. When you need to apply business rules, normalize data, convert types, enrich information, or filter items out of the flow, you can write a custom implementation of `ItemProcessor<I, O>`.

The processor is the natural boundary between input data and data to be written. The reader focuses on fetching data; the processor focuses on transforming or deciding whether an item moves forward; the writer focuses on persisting results. Keeping this boundary clear makes each part easier to test, reuse, and evolve independently.

A good processor usually processes one item using logic that can be understood and tested on its own. It should not hold shared mutable state across calls, manage chunk transactions itself, or produce side effects that cannot be safely repeated. In chunk processing, the same item may be reprocessed when a transaction rolls back or a job restarts, so determinism and idempotency must be considered from the initial design.

## 1. What Is ItemProcessor?

Spring Batch defines the generic interface:

~~~java
public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}
~~~

The two generic types describe the data contract:

- `I` is the item type the reader supplies to the processor.
- `O` is the item type the processor returns for the writer to receive.

A processor can keep the same data type—for example, `OrderInput` into normalized `OrderInput`—or convert to a different type, such as `OrderInput` into `OrderEntity` or `InvoiceRow`.

Example processor converting an input order into a database write command:

~~~java
public class OrderProcessor
        implements ItemProcessor<OrderInput, OrderToSave> {

    @Override
    public OrderToSave process(OrderInput input) {
        return new OrderToSave(
                input.orderId().trim(),
                input.customerId().trim(),
                input.amount().setScale(2, RoundingMode.HALF_UP));
    }
}
~~~

The processor is invoked for each item supplied by the reader. It does not receive the whole chunk in the basic interface; each call handles one item. Spring Batch manages collecting output items into a chunk and passing them to the writer.

## 2. Position of the Processor in a Chunk Step

A chunk-oriented step typically has a reader, processor, and writer:

~~~mermaid
flowchart LR
    A[ItemReader] --> B[ItemProcessor]
    B --> C[ItemWriter]
    C --> D[Commit chunk]
~~~

For example, with a chunk size of 100:

1. The reader reads input items.
2. The processor is called individually for each item.
3. Valid items are converted into outputs; filtered items do not proceed.
4. The writer receives the list of output items for the chunk.
5. Spring Batch commits the transaction according to step configuration.

If the processor throws an exception, the chunk follows the configured fault-tolerant policy or the step fails. If the processor returns `null`, that item is treated as filtered and is not sent to the writer.

The processor does not directly decide when to commit. It should focus on item processing and let the step/transaction manager manage transaction boundaries.

## 3. Configuring a Custom ItemProcessor

You can define a processor as a Spring bean and inject it into the step:

~~~java
@Bean
ItemProcessor<OrderInput, Order> orderProcessor(
        CustomerRepository customerRepository) {

    return new OrderProcessor(customerRepository);
}

@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
~~~

The chunk's generic declaration must match the pipeline's input and output types:

- The reader returns `OrderInput`.
- The processor accepts `OrderInput` and returns `Order`.
- The writer accepts `Order`.

If the types mismatch, errors generally appear at compile time when full generics are declared. Avoid raw types or unnecessary casts because they defeat Java's type checking.

In Spring Batch 5 configuration, `StepBuilder` takes `JobRepository` and chunk size with `PlatformTransactionManager`. In older versions, the builder API may differ; use the API corresponding to your project's version.

## 4. Distinguishing Transform, Filter, and Skip

A processor has three common outcome types:

| Behavior | How it is expressed | Meaning |
|---|---|---|
| Transform | Return a different or normalized object | Item proceeds to the writer |
| Filter | Return `null` | Item is intentionally excluded, not sent to writer |
| Processing error | Throw an exception | Step applies retry/skip/fail policy or fails |

Filtering and skipping are not the same. Filtering is a normal business decision—for example, exporting only orders with status `ACTIVE`. Skipping is how a step handles an item that threw an exception permitted by policy—for example, a malformed input line or a record with invalid data.

Example filter:

~~~java
public class ActiveOrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        if (!"ACTIVE".equalsIgnoreCase(input.status())) {
            return null;
        }
        return mapToOrder(input);
    }
}
~~~

Filtered items do not increment the skip count. Spring Batch tracks filtered item counts separately in `StepExecution`. Do not use `null` to hide parse errors, database failures, or unexpected exceptions; those errors must be represented as exceptions so policy can handle them.

## 5. Transforming Data in the Processor

A common task of a processor is converting data from an input DTO to the model needed by the writer. For example, a source file stores dates as strings and amounts may have many decimal places; the processor normalizes them into domain types.

~~~java
public class InvoiceProcessor
        implements ItemProcessor<InvoiceInput, Invoice> {

    private static final DateTimeFormatter DATE_FORMAT =
            DateTimeFormatter.ofPattern("uuuu-MM-dd");

    @Override
    public Invoice process(InvoiceInput input) {
        LocalDate invoiceDate =
                LocalDate.parse(input.invoiceDate(), DATE_FORMAT);

        BigDecimal amount = input.amount()
                .setScale(2, RoundingMode.HALF_UP);

        return new Invoice(
                input.invoiceNumber().trim(),
                invoiceDate,
                amount,
                input.currency().toUpperCase(Locale.ROOT));
    }
}
~~~

Use `BigDecimal` for monetary amounts and formatters with explicit patterns for dates. Do not rely on the batch host machine's default locale or timezone. If conversion fails, throw a contextual exception rather than returning an object with incorrect default values.

Mapping and representation normalization generally fit well in a processor. Complex rules depending on system state or business policies should be extracted into a dedicated service so the processor stays readable.

## 6. Validation in ItemProcessor

The processor is often where business conditions are checked before writing data:

- Order ID must not be blank.
- Amount must be greater than or equal to 0.
- Invoice date must not fall outside the allowed range.
- Customer ID must exist.
- Order status must belong to the supported set of values.

Example:

~~~java
public class ValidateOrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        if (input.orderId() == null || input.orderId().isBlank()) {
            throw new InvalidOrderException("orderId is required");
        }

        if (input.amount() == null
                || input.amount().signum() < 0) {
            throw new InvalidOrderException(
                    "amount must be zero or greater");
        }

        return new Order(
                input.orderId().trim(),
                input.customerId(),
                input.amount());
    }
}
~~~

Validation needs to distinguish data errors from system errors. An order missing `orderId` is an item data error; a database timeout while checking the customer is a potentially transient infrastructure error. Do not use the same exception for both if their retry/skip policies differ.

For validation with many rules, you can use Bean Validation or a dedicated `Validator`. The processor remains responsible for deciding whether validation failure is thrown, converted into a reject record, or filtered according to business rules.

## 7. Using ValidatingItemProcessor

Spring Batch provides `ValidatingItemProcessor` to apply a `Validator` to each item. It is useful when validation can be expressed as a separate `Validator` object.

Example:

~~~java
@Bean
Validator<OrderInput> orderInputValidator() {
    return input -> {
        if (input.orderId() == null || input.orderId().isBlank()) {
            throw new ValidationException("orderId is required");
        }
        if (input.amount() == null || input.amount().signum() < 0) {
            throw new ValidationException("amount must be non-negative");
        }
    };
}

@Bean
ItemProcessor<OrderInput, OrderInput> validatedOrderProcessor(
        Validator<OrderInput> orderInputValidator) {

    ValidatingItemProcessor<OrderInput> processor =
            new ValidatingItemProcessor<>(orderInputValidator);
    return processor;
}
~~~

By default, a validation failure is thrown as an exception. If the processor is configured in filter mode, a validation failure can cause the item to be excluded by returning `null`. Only enable filtering when the business specifies that invalid items are intentionally discarded; if you need to track rejects and reasons, usually throw an exception and handle it via a skip listener or reject store.

`ValidatingItemProcessor` does not replace all mapping or enrichment logic. It can be placed in a chain alongside a transformation processor.

## 8. Enrichment with a Service or Repository

A processor can supplement required information from a service or repository. For example, input contains only `customerId`, while the writer also needs the customer's segment:

~~~java
public class EnrichOrderProcessor
        implements ItemProcessor<OrderInput, EnrichedOrder> {

    private final CustomerService customerService;

    public EnrichOrderProcessor(CustomerService customerService) {
        this.customerService = customerService;
    }

    @Override
    public EnrichedOrder process(OrderInput input) {
        Customer customer =
                customerService.getRequired(input.customerId());

        return new EnrichedOrder(
                input.orderId(),
                customer.id(),
                customer.segment(),
                input.amount());
    }
}
~~~

This is synchronous per-item enrichment. Across millions of items, a separate query per item can create an N+1 query problem and slow down the job. Consider:

- Including needed data via a join in the reader query if appropriate.
- Caching immutable or infrequently changing reference data.
- Using grouped bulk lookups if the processor architecture permits.
- Partitioning data to control load.
- Measuring service call duration and actual query counts before optimizing.

Do not cache mutable data indefinitely if results must reflect the latest state. Caches need appropriate lifetime policies, memory bounds, and invalidation.

## 9. Splitting a Processor into Small Components

When a processor has multiple responsibilities, split the steps into small classes or services:

~~~java
public class OrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    private final OrderValidator validator;
    private final OrderNormalizer normalizer;
    private final CustomerEnricher enricher;

    public OrderProcessor(
            OrderValidator validator,
            OrderNormalizer normalizer,
            CustomerEnricher enricher) {
        this.validator = validator;
        this.normalizer = normalizer;
        this.enricher = enricher;
    }

    @Override
    public Order process(OrderInput input) {
        validator.validate(input);
        OrderInput normalized = normalizer.normalize(input);
        return enricher.enrich(normalized);
    }
}
~~~

Each component can be tested independently. The processor orchestrates the processing order and passes results between components. If a step can filter items, decide explicitly whether later steps run and represent that decision via `null` per contract.

Avoid creating a monolithic processor that parses, calls multiple APIs, sends messages, writes to the database, updates metrics, and handles routing. Those responsibilities make the processor hard to test and make retry behavior difficult to reason about.

## 10. Chaining Multiple Processors with CompositeItemProcessor

When you want to run multiple processors sequentially, Spring Batch provides `CompositeItemProcessor`. The output of the preceding delegate becomes the input of the next delegate.

Example:

~~~java
@Bean
ItemProcessor<OrderInput, EnrichedOrder> orderProcessorChain(
        ItemProcessor<OrderInput, OrderInput> normalizeProcessor,
        ItemProcessor<OrderInput, Order> mapProcessor,
        ItemProcessor<Order, EnrichedOrder> enrichProcessor) throws Exception {

    CompositeItemProcessor<OrderInput, EnrichedOrder> composite =
            new CompositeItemProcessor<>();

    composite.setDelegates(List.of(
            normalizeProcessor,
            mapProcessor,
            enrichProcessor));
    composite.afterPropertiesSet();
    return composite;
}
~~~

In this chain:

1. `normalizeProcessor` takes `OrderInput` and returns `OrderInput`.
2. `mapProcessor` takes `OrderInput` and returns `Order`.
3. `enrichProcessor` takes `Order` and returns `EnrichedOrder`.

Each delegate's output type must be compatible with the next delegate's input type. If any delegate returns `null`, the chain stops for that item and the item is filtered; downstream delegates do not receive `null`.

`CompositeItemProcessor` fits well when steps have a clear sequence and you want to reuse individual processors. Do not over-split into delegates just to create more classes; the chain should represent meaningful processing stages.

## 11. Selecting a Processor by Item Type

If input contains multiple record types and each type needs different logic, you can use `ClassifierCompositeItemProcessor` to select the appropriate processor based on the item.

Conceptual example:

~~~java
@Bean
ItemProcessor<ImportRecord, ImportResult> classifiedProcessor(
        ItemProcessor<CustomerRecord, ImportResult> customerProcessor,
        ItemProcessor<OrderRecord, ImportResult> orderProcessor) {

    ClassifierCompositeItemProcessor<ImportRecord, ImportResult> composite =
            new ClassifierCompositeItemProcessor<>();

    composite.setClassifier(record -> {
        if (record instanceof CustomerRecord) {
            return item -> customerProcessor.process((CustomerRecord) item);
        }
        if (record instanceof OrderRecord) {
            return item -> orderProcessor.process((OrderRecord) item);
        }
        throw new IllegalArgumentException(
                "Unsupported record type: " + record.getClass().getName());
    });
    return composite;
}
~~~

This example illustrates branching by record type; in a real application, use a dedicated strongly typed classifier and control any unchecked casts. Another option is designing a common interface with implementations that handle the same input type.

Do not return a `null` processor from the classifier unless there is an explicit handling rule. Unsupported record types should raise a contextual error or route to a dedicated reject branch.

## 12. Should the Processor Return the Same Object or a New Object?

A processor can return the exact input object if no modification is needed:

~~~java
public class PassThroughOrderProcessor
        implements ItemProcessor<Order, Order> {

    @Override
    public Order process(Order item) {
        return item;
    }
}
~~~

However, if normalization or additional data is required, it is usually better to create a new output object, especially when the input is an immutable record or shared across multiple places. Mutating the input object can cause side effects if the reader, a cache, a test fixture, or another processing branch still holds a reference to it.

If the object is mutable and the processor modifies it directly, define clear object ownership and ensure no other consumer accesses it concurrently. Immutable DTO/domain objects usually make pipelines more predictable.

## 13. Processor Exceptions and Fault-Tolerant Steps

The `process` method can throw `Exception`. Spring Batch delegates that error to the step's error-handling mechanism. Depending on configuration, an exception can:

- Cause the step/job to fail.
- Be retried if classified as retryable and within the retry limit.
- Be skipped if declared skippable and the skip limit has not been exceeded.

Example configuration:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
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

In this example, temporary service errors are retried up to the configured limit; item-specific data errors can be skipped. This is only a sample policy: you must determine which exceptions are genuinely transient and safe to retry, and which exceptions are permitted to be skipped by business rules.

Do not catch all `Exception`s inside `process` and return `null`. That turns system errors into silent filtering, loses data, and causes job metadata to misreport errors. Let exceptions propagate or wrap them into specific domain exceptions while preserving the cause.

## 14. Distinguishing Data Errors from Infrastructure Errors

A processor may call databases, REST APIs, or other services. Categorize errors by recoverability:

| Scenario | Typically appropriate handling |
|---|---|
| Missing required field | Validation exception; fail or skip per policy |
| Unsupported status code | Data error; usually reject or fail |
| Temporary API timeout | Can retry with limit and backoff |
| API returns "customer does not exist" | Business/data error; do not retry indefinitely |
| Database deadlock | Transaction rollback then retry if appropriately configured |
| Programming bug like unexpected `NullPointerException` | Usually fail and investigate, do not blanket-skip |

Do not classify every `RuntimeException` as skippable or retryable. An overly broad rule can mask programming mistakes or misconfigurations.

If you need to persist reject records, use a listener or dedicated mechanism to store source ID, input reference, exception type, and reason. Ensure reject persistence has transaction semantics aligned with the step and does not create duplicate records during retries.

## 15. Side Effects and Idempotency

A processor can be called again if a chunk rolls back or an operation is retried. Therefore, processors should favor pure logic or safely repeatable side effects.

Example of what not to do inside a processor:

~~~java
public Order process(OrderInput input) {
    paymentGateway.charge(input.paymentToken(), input.amount());
    return map(input);
}
~~~

If the chunk transaction rolls back after a successful charge, reprocessing may charge a second time. A database transaction cannot automatically undo a payment request already accepted by an external system.

Better options:

- Have the processor only validate and build the command to execute.
- Have the writer persist the command/outbox record in the same database transaction.
- Have a separate dispatcher send messages or call APIs from the outbox.
- Use stable idempotency keys tied to the business operation.
- Record processing state to prevent duplicate submissions and support reconciliation.

If a processor must call a service to read data, ensure the call has no side effects or has safe retry semantics. Set timeouts, limit retries, and monitor latency.

## 16. Processors in Multi-Threaded Steps

In a multi-threaded step, the same processor bean may be invoked concurrently by multiple worker threads. Therefore, processors should generally be stateless:

~~~java
@Component
public class AmountNormalizer
        implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        BigDecimal amount =
                input.amount().setScale(2, RoundingMode.HALF_UP);
        return new Order(input.orderId(), amount);
    }
}
~~~

Do not store the current item, per-call mutable batch IDs, or mutable counters in singleton fields without synchronization. Local variables inside `process` belong to that invocation and are safer than shared state.

If the processor depends on configuration from `JobParameters` or partition context, you can use `StepScope` for late binding per `StepExecution`. However, `StepScope` does not mean a new instance is created per chunk thread in a multi-threaded step. If multiple threads call the target processor, it must still be thread-safe.

In partitioning, each worker has its own `StepExecution`; a step-scoped processor can receive the corresponding partition's context. This is usually cleaner if each worker needs isolated state.

## 17. Do Not Use the Processor to Manage Chunks

`ItemProcessor` receives one item at a time, not the entire chunk list. Do not collect items in a field waiting for a full batch to process together, because:

- State can mix across chunks or threads.
- Rollbacks/restarts can leave the in-memory list out of sync with checkpoints.
- Memory grows with the number of items.
- The state's lifecycle does not align with chunk transactions.

If you need batch-level processing, consider a reader query that fetches in batches, a writer that supports bulk operations, or a separate aggregation step. If you need chunk boundary awareness, use appropriate listeners or writers rather than storing ad-hoc state inside the processor.

## 18. Processor Performance

The processor is normally invoked once per item, so small per-call overhead becomes significant when processing millions of records.

Optimization approaches:

- Avoid repeatedly creating expensive formatters or parsers when immutable/thread-safe instances can be reused.
- Avoid querying a database/API repeatedly for the same reference data.
- Use batch lookups or joins in the reader where appropriate.
- Avoid logging full payloads at `INFO` level for every item.
- Keep the output object graph lean enough for the writer.
- Measure processing time separately from reading and writing to identify bottlenecks.
- Bound concurrency according to external dependency capacity.

Caching can improve throughput, but it requires memory bounds and expiration policies. When reference data changes during a job run, caching choices can affect business consistency.

Do not optimize by removing mandatory validations or replacing exceptions with incorrect default values. Measure first, optimize hot spots, and preserve data semantics.

## 19. Observing the Processor with Listeners and Metadata

Spring Batch provides `ItemProcessListener` to observe the item-processing lifecycle:

~~~java
public class OrderProcessListener
        implements ItemProcessListener<OrderInput, Order> {

    @Override
    public void beforeProcess(OrderInput item) {
        // Correlation ID can be logged if needed.
    }

    @Override
    public void afterProcess(OrderInput item, Order result) {
        // result may be null if the item was filtered.
    }

    @Override
    public void onProcessError(OrderInput item, Exception e) {
        // Log error details in a controlled manner.
    }
}
~~~

Listeners are useful for logging, metrics, and auditing. Avoid logging sensitive payloads or entire items. If a listener writes reject/audit data to a database, understand transaction and retry semantics so you do not insert duplicate records.

`StepExecution` provides counters such as `readCount`, `writeCount`, `filterCount`, `processSkipCount`, and `skipCount`. You can use them to observe:

- How many items were read.
- How many items were filtered because the processor returned `null`.
- How many items were written.
- How many processing errors were skipped.

These counters aid operations, though they do not replace output data reconciliation. If `filterCount` spikes unexpectedly, inspect filter rules and input distribution.

## 20. Unit Testing ItemProcessor

A processor should have independent unit tests because it typically holds important transformation and validation rules.

Example:

~~~java
class OrderProcessorTest {

    private final OrderProcessor processor = new OrderProcessor();

    @Test
    void normalizesOrderFields() throws Exception {
        OrderInput input = new OrderInput(
                " ORD-1001 ",
                " CUS-01 ",
                new BigDecimal("12.345"));

        Order result = processor.process(input);

        assertEquals("ORD-1001", result.orderId());
        assertEquals("CUS-01", result.customerId());
        assertEquals(new BigDecimal("12.35"), result.amount());
    }

    @Test
    void rejectsNegativeAmount() {
        OrderInput input = new OrderInput(
                "ORD-1002",
                "CUS-02",
                new BigDecimal("-1.00"));

        assertThrows(
                InvalidOrderException.class,
                () -> processor.process(input));
    }
}
~~~

Recommended test cases:

1. Valid input produces expected output.
2. Strings with whitespace are normalized according to rules.
3. Null values or missing required fields are handled explicitly.
4. Amounts, dates, and enums convert accurately.
5. Filter conditions return `null` when required by business logic.
6. Validation failures throw the expected exception type.
7. Dependency errors preserve causes or map to meaningful exceptions.
8. Enrichment uses service data properly and handles not-found cases.
9. The processor does not unexpectedly mutate input.
10. Repeated calls with the same input produce deterministic results if designed to be deterministic.

You do not need to mock the entire Spring Batch framework in processor unit tests. Test `process` directly with the required inputs and dependencies; use separate integration tests for step configuration and fault-tolerant behavior.

## 21. Integration Testing the Processor in a Step

Unit tests do not prove the processor is wired properly into the step or that filter/skip counters behave as expected. Integration tests should run the step with a simple test reader, processor, and writer.

Example verifying filtering:

~~~java
JobExecution execution =
        jobLauncherTestUtils.launchStep(
                "filterOrdersStep",
                jobParameters);

StepExecution stepExecution = execution.getStepExecutions()
        .stream()
        .filter(step -> step.getStepName().equals("filterOrdersStep"))
        .findFirst()
        .orElseThrow();

assertEquals(3, stepExecution.getFilterCount());
assertEquals(7, stepExecution.getWriteCount());
~~~

The example assumes the reader returns 10 items, the processor filters 3 items, and the remaining 7 items are written by the writer. Use an isolated test `JobRepository` or clean metadata appropriately so each run has deterministic `JobParameters`.

For skip/retry, check processor invocation counts, skip counts, final outputs, reject stores, and job status. For side effects, test rollback/retry to verify no duplicates are created.

## 22. Common Pitfalls

**Using null to represent errors.** `null` is the filter signal per contract. Throw exceptions for errors that need retry, skip, or fail handling.

**Confusing filtering with skipping.** Filtering intentionally excludes an item; skipping discards an item that threw a policy-allowed exception.

**Using raw types or mismatched generics.** The processor's output type must match the type the writer accepts.

**Putting too many responsibilities in one processor.** Split validation, normalization, and enrichment into meaningful components.

**Calling APIs with side effects in process.** Rollback/retry can re-invoke the processor and create duplicate actions. Use an outbox or idempotency.

**Catching all exceptions and returning a default item.** Errors are hidden and bad data gets written. Categorize exceptions explicitly.

**Using the same exception for validation and timeouts.** Retry/skip policies become imprecise. Separate exceptions by error nature.

**Holding mutable state in a singleton processor.** Multi-threaded steps can corrupt state across threads. Keep processors stateless or synchronize state intentionally.

**Assuming StepScope creates an instance per thread.** `StepScope` binds to `StepExecution`. Components must still be thread-safe if multiple threads call the target.

**Making N+1 queries during enrichment.** One query per item can severely slow down the job. Consider joins, controlled caching, or bulk lookups.

**Not checking filter and reject counts.** A job may complete while dropping too many items. Set thresholds and reconcile against business expectations.

## 23. Processor Construction Workflow

When building a custom `ItemProcessor`, you can follow this sequence:

1. Identify the input type from the reader and the output type required by the writer.
2. Determine whether the processor performs transformation, validation, enrichment, or filtering.
3. Explicitly define the conditions for returning `null` and which exceptions are thrown.
4. Extract business rules into independently testable services/validators.
5. Keep logic deterministic and avoid non-idempotent side effects.
6. Wire the processor into the step with generic types matching the reader and writer.
7. Choose retry/skip policies based on exception types and business requirements.
8. Verify thread safety if the step uses `TaskExecutor`, partitioning, or parallel flows.
9. Write unit tests for item logic and integration tests for filtering/skipping/retrying.
10. Monitor `filterCount`, `processSkipCount`, latency, and reconciliation results in production.

## Conclusion

`ItemProcessor<I, O>` receives an item from the reader and returns an output item for the writer. When writing a custom processor, clearly define input/output types and separate transformation, validation, enrichment, and filtering by responsibility. Return `null` only when intentionally filtering an item; throw exceptions when the step needs to apply retry, skip, or fail policies.

Keep processors stateless and deterministic, especially when a step runs with multiple threads or items may be reprocessed after rollback. Avoid non-idempotent side effects in `process`; use writers, outboxes, or idempotency mechanisms for actions that must commit. Combine unit tests with step integration tests to verify mapping, filter counts, exception policies, and actual outputs. A small processor with a clear contract keeps the chunk pipeline easy to control and recover.
