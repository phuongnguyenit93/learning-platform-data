# Testing a processor chain

In Spring Batch, a processor chain consists of multiple `ItemProcessor` instances linked in sequence: the output of an earlier processor becomes the input of the next one. `CompositeItemProcessor` provides a way to assemble those delegates into a single processor for a Step to use. When testing a chain, you must verify that each delegate receives the right data, processing order is accurate, the final output matches the contract, and stopping branches such as `null` or exceptions behave as expected.

A test that only invokes the final processor or merely runs the Job to `COMPLETED` status is not enough to prove the chain is configured properly. A chain can produce a coincidentally right output even when a delegate was never invoked, order was inverted, a mapping step was bypassed, or errors were mishandled. Split testing into three layers: unit tests for each delegate, unit tests for `CompositeItemProcessor` to verify composition, and Step integration tests to verify wiring, filtering, retry/skip, and actual outputs.

## 1. What is a processor chain?

An `ItemProcessor<I, O>` receives an item and returns a processed item. A chain combines multiple processors with different intermediate types:

```text
OrderInput
    |
    v
NormalizeOrderProcessor
    |  OrderInput -> NormalizedOrder
    v
ValidateOrderProcessor
    |  NormalizedOrder -> ValidatedOrder
    v
EnrichOrderProcessor
    |  ValidatedOrder -> EnrichedOrder
    v
MapExportProcessor
    |  EnrichedOrder -> OrderExport
    v
OrderExport
```

Each delegate has one clear responsibility. The normalize processor standardizes inputs; the validate processor checks business rules; the enrich processor supplements data; the final processor converts to the model expected by the writer.

`CompositeItemProcessor<I, O>` implements `ItemProcessor<I, O>` and sequentially invokes the configured delegates. The Step only needs to declare the composite as its processor. Thus, chaining logic is tested separately from reading/writing logic.

## 2. Distinguishing delegate tests from composite tests

The two test types answer two different questions:

| Test type | Core question | Example assertions |
|---|---|---|
| Delegate unit test | Does an individual processor handle inputs correctly? | Normalizes order codes, rejects negative amounts, maps fields accurately. |
| Composite unit test | Are processors called in the right order and passing outputs properly? | Delegate B receives the exact output of A; final result is output of C. |
| Step integration test | Does Spring Batch wire and coordinate the chain accurately inside chunks? | Writer receives right items, filter/skip/retry counters match. |

Testing only delegates leaves the chain exposed to misordered wiring or a missing step. Testing only the composite with mocks leaves business logic inside delegates untested. Testing only the Job end-to-end makes it hard to pinpoint whether a bug lies in mapping, chaining, or the reader/writer.

## 3. Building an example domain for the chain

Suppose a Step exports order data. Intermediate types explicitly define each step's inputs/outputs:

```java
public record OrderInput(
        String orderId,
        String customerCode,
        String amountText) {
}

public record NormalizedOrder(
        String orderId,
        String customerCode,
        BigDecimal amount) {
}

public record ValidatedOrder(
        String orderId,
        String customerCode,
        BigDecimal amount) {
}

public record EnrichedOrder(
        String orderId,
        String customerName,
        BigDecimal amount) {
}

public record OrderExport(
        String orderId,
        String customerName,
        BigDecimal amount) {
}
```

Each record represents a data shape at a specific chain boundary. Using distinct intermediate types allows the compiler to catch mismatches when one delegate's output is incompatible with the next delegate's input.

## 4. Delegates in the example

The first processor normalizes data:

```java
public class NormalizeOrderProcessor
        implements ItemProcessor<OrderInput, NormalizedOrder> {

    @Override
    public NormalizedOrder process(OrderInput input) {
        return new NormalizedOrder(
                input.orderId().trim(),
                input.customerCode().trim().toUpperCase(Locale.ROOT),
                new BigDecimal(input.amountText().trim()));
    }
}
```

The next processor checks business rules:

```java
public class ValidateOrderProcessor
        implements ItemProcessor<NormalizedOrder, ValidatedOrder> {

    @Override
    public ValidatedOrder process(NormalizedOrder order) {
        if (order.amount().signum() <= 0) {
            throw new InvalidOrderException(order.orderId());
        }

        return new ValidatedOrder(
                order.orderId(),
                order.customerCode(),
                order.amount());
    }
}
```

The enrichment processor looks up the customer name:

```java
public class EnrichOrderProcessor
        implements ItemProcessor<ValidatedOrder, EnrichedOrder> {

    private final CustomerService customerService;

    public EnrichOrderProcessor(CustomerService customerService) {
        this.customerService = customerService;
    }

    @Override
    public EnrichedOrder process(ValidatedOrder order) {
        String name = customerService.findName(order.customerCode());
        return new EnrichedOrder(order.orderId(), name, order.amount());
    }
}
```

The final processor maps to output:

```java
public class MapOrderExportProcessor
        implements ItemProcessor<EnrichedOrder, OrderExport> {

    @Override
    public OrderExport process(EnrichedOrder order) {
        return new OrderExport(
                order.orderId(),
                order.customerName(),
                order.amount());
    }
}
```

These classes are kept short to illustrate contracts. In real applications, each delegate may inject its own validators, repositories, or API clients; delegate unit tests should mock those collaborators.

## 5. Configuring CompositeItemProcessor

You can wire delegates using the builder:

```java
@Bean
ItemProcessor<OrderInput, OrderExport> orderProcessor(
        NormalizeOrderProcessor normalize,
        ValidateOrderProcessor validate,
        EnrichOrderProcessor enrich,
        MapOrderExportProcessor map) throws Exception {

    return new CompositeItemProcessorBuilder<OrderInput, OrderExport>()
            .delegates(List.of(normalize, validate, enrich, map))
            .build();
}
```

The `delegates` list defines the exact execution order. The builder validates certain configuration requirements and builds the composite. In this example, the output type of `normalize` matches the input type of `validate`, continuing through subsequent steps.

Declaring delegates inline inside Step configuration can make configuration tests harder to read. A dedicated composite bean allows unit tests to obtain the exact production chain while the Step simply injects one `ItemProcessor<OrderInput, OrderExport>`.

## 6. Unit testing each delegate

Delegates should be tested independently of the composite. Example normalize test:

```java
class NormalizeOrderProcessorTest {

    private final NormalizeOrderProcessor processor =
            new NormalizeOrderProcessor();

    @Test
    void trimsFieldsAndNormalizesCustomerCode() throws Exception {
        OrderInput input = new OrderInput(
                " O-100 ", " cust-7 ", " 125.50 ");

        NormalizedOrder result = processor.process(input);

        assertThat(result).isEqualTo(new NormalizedOrder(
                "O-100",
                "CUST-7",
                new BigDecimal("125.50")));
    }
}
```

This test verifies normalize behavior without creating a Step or `JobRepository`. For processors with dependencies, mock collaborators and verify the inputs sent to dependencies along with returned outputs.

Example enrichment test:

```java
@Test
void enrichesOrderWithCustomerName() throws Exception {
    CustomerService customerService = mock(CustomerService.class);
    EnrichOrderProcessor processor =
            new EnrichOrderProcessor(customerService);

    ValidatedOrder input = new ValidatedOrder(
            "O-100", "CUST-7", new BigDecimal("125.50"));
    when(customerService.findName("CUST-7")).thenReturn("Lan Nguyen");

    EnrichedOrder result = processor.process(input);

    assertThat(result).isEqualTo(new EnrichedOrder(
            "O-100", "Lan Nguyen", new BigDecimal("125.50")));
    verify(customerService).findName("CUST-7");
    verifyNoMoreInteractions(customerService);
}
```

Delegate tests should cover valid inputs, boundary inputs, invalid data, and dependency errors when those fall under the processor's responsibility.

## 7. Testing the composite with mock delegates

To test composition, mock each `ItemProcessor` and stub outputs for each step:

```java
@Test
void passesOutputOfEachDelegateToTheNextDelegate() throws Exception {
    @SuppressWarnings("unchecked")
    ItemProcessor<OrderInput, NormalizedOrder> normalize =
            mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<NormalizedOrder, ValidatedOrder> validate =
            mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<ValidatedOrder, EnrichedOrder> enrich =
            mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<EnrichedOrder, OrderExport> map =
            mock(ItemProcessor.class);

    OrderInput input = new OrderInput(" O-100 ", " cust-7 ", "125.50");
    NormalizedOrder normalized = new NormalizedOrder(
            "O-100", "CUST-7", new BigDecimal("125.50"));
    ValidatedOrder validated = new ValidatedOrder(
            "O-100", "CUST-7", new BigDecimal("125.50"));
    EnrichedOrder enriched = new EnrichedOrder(
            "O-100", "Lan Nguyen", new BigDecimal("125.50"));
    OrderExport expected = new OrderExport(
            "O-100", "Lan Nguyen", new BigDecimal("125.50"));

    when(normalize.process(input)).thenReturn(normalized);
    when(validate.process(normalized)).thenReturn(validated);
    when(enrich.process(validated)).thenReturn(enriched);
    when(map.process(enriched)).thenReturn(expected);

    CompositeItemProcessor<OrderInput, OrderExport> composite =
            new CompositeItemProcessorBuilder<OrderInput, OrderExport>()
                    .delegates(List.of(normalize, validate, enrich, map))
                    .build();

    assertThat(composite.process(input)).isEqualTo(expected);

    InOrder order = inOrder(normalize, validate, enrich, map);
    order.verify(normalize).process(input);
    order.verify(validate).process(normalized);
    order.verify(enrich).process(validated);
    order.verify(map).process(enriched);
    verifyNoMoreInteractions(normalize, validate, enrich, map);
}
```

The test verifies that the composite forwards each delegate's output object to the next delegate and invokes delegates in order. `InOrder` makes invocation order explicit; asserting the final result verifies the chain output is returned to the caller.

If the project uses a Java version without `record` support, replace records with immutable classes/POJOs; the test semantics remain identical.

## 8. Verifying delegates are not skipped or called redundantly

A wiring bug can cause the chain to invoke only three out of four delegates or accidentally include a delegate twice. `InOrder` combined with `verifyNoMoreInteractions` catches those cases.

If a delegate is optional by configuration, tests must explicitly show which chain variant is under test. Never write a generic assertion checking only the final output without verifying critical steps ran.

When a delegate has side effects, verify the delegate's collaborators are called the exact expected number of times. For example, `EnrichOrderProcessor` calls `CustomerService` once per item. If processing one item calls the service twice, tests can catch regressions that amplify query/API traffic.

## 9. Testing chain order with transforming values

In addition to mocks, real processors with simple transformations can prove order matters:

```java
@Test
void executesProcessorsInConfiguredOrder() throws Exception {
    ItemProcessor<String, String> trim = String::trim;
    ItemProcessor<String, String> uppercase = String::toUpperCase;
    ItemProcessor<String, String> addPrefix = value -> "ORDER-" + value;

    CompositeItemProcessor<String, String> composite =
            new CompositeItemProcessorBuilder<String, String>()
                    .delegates(List.of(trim, uppercase, addPrefix))
                    .build();

    assertThat(composite.process("  ab-10  "))
            .isEqualTo("ORDER-AB-10");
}
```

If `trim` and `uppercase` are swapped, this example's output could still look identical; therefore, pick transformations where order genuinely affects the output or use `InOrder` mocks. Never use an order-insensitive input and conclude the chain order is correct.

## 10. Input/output types between delegates

A chain can span different intermediate types. The compiler checks generics at compile time when types are declared explicitly:

```java
ItemProcessor<OrderInput, NormalizedOrder> normalize = ...;
ItemProcessor<NormalizedOrder, ValidatedOrder> validate = ...;
ItemProcessor<ValidatedOrder, OrderExport> map = ...;
```

A common configuration bug is the second delegate expecting `String` while the first returns `NormalizedOrder`, or the final delegate returning a type the writer does not accept. Avoid raw types and unnecessary casts in production configuration.

Compile-time type safety does not prove runtime mapping correctness. A processor can construct a type-valid object while assigning the wrong fields. Thus, delegate unit tests must still assert all meaningful fields.

## 11. Testing when a delegate returns null

Per the Spring Batch contract, a processor returning `null` means the item is filtered and not forwarded to the writer. In `CompositeItemProcessor`, when a delegate returns `null`, the chain stops there; remaining delegates are not called.

Test example:

```java
@Test
void nullFromDelegateStopsTheRemainingChain() throws Exception {
    @SuppressWarnings("unchecked")
    ItemProcessor<String, String> normalize = mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<String, String> filter = mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<String, String> map = mock(ItemProcessor.class);

    when(normalize.process("input")).thenReturn("normalized");
    when(filter.process("normalized")).thenReturn(null);

    CompositeItemProcessor<String, String> composite =
            new CompositeItemProcessorBuilder<String, String>()
                    .delegates(List.of(normalize, filter, map))
                    .build();

    assertThat(composite.process("input")).isNull();

    InOrder order = inOrder(normalize, filter);
    order.verify(normalize).process("input");
    order.verify(filter).process("normalized");
    verifyNoInteractions(map);
}
```

This test matters because a later delegate might create side effects or call external services. Once an item is filtered, that delegate must not run.

## 12. Distinguishing null filters from exceptions

`null` is a filter signal per the processor contract. Exceptions are processing errors handled by the Step's fault-tolerance policy.

| Delegate result | Chain behavior | Typical Step behavior |
|---|---|---|
| Returns object | Passes object to next delegate | Continues to writer. |
| Returns `null` | Stops chain for current item | Increments filter count; writer does not receive item. |
| Throws exception | Chain stops due to error | Rollback/retry/skip/fail per configuration. |

Do not use `null` to represent system errors like database unavailability or API timeouts. Doing so turns errors into silent filters and drops data from output without an explicit skip record.

## 13. Testing exceptions from a delegate

If a delegate mid-chain throws an exception, subsequent delegates must not run and the exception must propagate out:

```java
@Test
void exceptionStopsTheChainAndPropagates() throws Exception {
    @SuppressWarnings("unchecked")
    ItemProcessor<String, String> first = mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<String, String> second = mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<String, String> third = mock(ItemProcessor.class);

    RuntimeException failure = new IllegalStateException("validation failed");
    when(first.process("input")).thenReturn("normalized");
    when(second.process("normalized")).thenThrow(failure);

    CompositeItemProcessor<String, String> composite =
            new CompositeItemProcessorBuilder<String, String>()
                    .delegates(List.of(first, second, third))
                    .build();

    assertThatThrownBy(() -> composite.process("input"))
            .isSameAs(failure);

    verify(first).process("input");
    verify(second).process("normalized");
    verifyNoInteractions(third);
}
```

Tests should place exceptions at the start, middle, and end of the chain if those positions carry different semantics or side effects. Usually one representative test proves composite propagation alongside dedicated tests for each delegate's business exceptions, always ensuring later steps do not run after failure.

## 14. Testing empty chains and missing configuration

An empty chain or missing mandatory delegate is usually an application configuration error, not a normal business case. Explicitly decide whether a chain is allowed to have zero delegates.

For a chain requiring normalize, validate, and map, test that the configuration building the composite receives all delegates. You can verify the application context initializes cleanly and the composite bean exists.

Do not write convoluted tests solely to assert internal builder behavior on empty lists if the application does not support empty chains. Instead, ensure your application factory/configuration cannot accidentally build an empty list and fails fast with a clear message.

## 15. Testing production bean configuration

Unit tests constructing a composite manually verify semantics, yet may miss production beans wired in the wrong order or injected with the wrong delegate. A small Spring context test can pull the exact composite bean:

```java
@SpringJUnitConfig(BatchProcessorConfiguration.class)
class OrderProcessorConfigurationTest {

    @Autowired
    ItemProcessor<OrderInput, OrderExport> orderProcessor;

    @Test
    void configuredChainProducesExpectedExport() throws Exception {
        OrderInput input = new OrderInput(
                " O-100 ", " cust-7 ", "125.50");

        OrderExport result = orderProcessor.process(input);

        assertThat(result.orderId()).isEqualTo("O-100");
        assertThat(result.customerName()).isEqualTo("Lan Nguyen");
        assertThat(result.amount()).isEqualByComparingTo("125.50");
    }
}
```

The test must supply suitable fixtures/customer services, such as test beans or a test database. The goal is retrieving the production bean to confirm delegates are wired accurately, rather than building a separate composite inside the test.

If the chain depends on `@StepScope`, the bean may require an active StepScope context when invoked. In that case, use `StepScopeTestExecutionListener` or `StepScopeTestUtils` to provide a `StepExecution` context for the test, or verify the chain at the Step integration level.

## 16. Testing processors with @StepScope

A delegate may read `JobParameters` or `StepExecutionContext` via `@Value`. Unit tests invoking the bean outside StepScope may fail because the scope is inactive.

Example:

```java
@Bean
@StepScope
ItemProcessor<OrderInput, NormalizedOrder> normalizeProcessor(
        @Value("#{jobParameters['tenant.id']}") Long tenantId,
        TenantConfigurationService configurationService) {

    return input -> normalize(input, tenantId, configurationService);
}
```

When testing, create a `StepExecution` with `JobParameters` containing `tenant.id` and register test scope support. Never mock away the entire scope and skip parameter checks if logic depends on the tenant.

With Spring Batch Test, `StepScopeTestExecutionListener` can supply `StepExecution` to test methods per framework conventions. `StepScopeTestUtils.doInStepScope(...)` allows executing code inside a provided StepScope context. Pick the approach matching your project's Spring Batch version.

## 17. Integration testing through a Step

After unit tests, write an integration test proving the Step uses the composite properly. You can use `@SpringBatchTest`, `JobLauncherTestUtils`, and small fixture readers/writers.

Example test structure:

```java
@SpringBatchTest
@SpringJUnitConfig(OrderJobTestConfiguration.class)
class OrderExportStepTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void stepRunsConfiguredProcessorChain() throws Exception {
        JobExecution execution = jobLauncherTestUtils.launchStep(
                "exportOrdersStep",
                new JobParametersBuilder()
                        .addString("test.run", UUID.randomUUID().toString())
                        .toJobParameters());

        assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);

        StepExecution stepExecution = execution.getStepExecutions()
                .iterator().next();
        assertThat(stepExecution.getReadCount()).isEqualTo(2);
        assertThat(stepExecution.getWriteCount()).isEqualTo(2);
    }
}
```

This is an illustrative skeleton. The test configuration must define a Step named `exportOrdersStep`, a reader returning two items, and a writer observing output. When using `launchStep`, `JobLauncherTestUtils` must be configured with the appropriate Job/Step per version. To test the full Job flow, use `launchJob`.

Do not assert `BatchStatus.COMPLETED` alone. Verify the writer received the right records and final data reflects every step in the chain.

## 18. Inspecting writer outputs

A test writer can collect received items for assertions:

```java
class CollectingOrderWriter implements ItemWriter<OrderExport> {

    private final List<OrderExport> written = new ArrayList<>();

    @Override
    public void write(Chunk<? extends OrderExport> chunk) {
        written.addAll(chunk.getItems());
    }

    List<OrderExport> writtenItems() {
        return List.copyOf(written);
    }
}
```

In integration tests, inject the test writer or use a real repository/output file depending on goals. Assertions should compare business keys, normalized/enriched fields, and output ordering if ordering is part of the contract.

If the writer executes across multiple chunks, `write` will be called multiple times; never assume a single invocation for the whole Step. Tests must accumulate items across chunks or assert each chunk properly.

## 19. Testing filter counts

A delegate can return `null` to exclude items. Integration tests should verify excluded items do not reach the writer and `filterCount` matches:

```java
assertThat(stepExecution.getReadCount()).isEqualTo(3);
assertThat(stepExecution.getFilterCount()).isEqualTo(1);
assertThat(stepExecution.getWriteCount()).isEqualTo(2);
```

These numbers assume all three items are read, one item is filtered, and the remaining two items are written successfully without skips or retries altering counters.

Verify the writer did not receive the filtered item. Checking `filterCount` alone may miss unwanted writer output or side effects in an earlier delegate that ran before the filter point.

## 20. Testing retries when a delegate throws an exception

If an exception from a delegate is configured for retry, the Step may re-run processing for the item per fault-tolerance behavior. Tests should verify:

- The exception is of a retryable type.
- Retry limits are enforced accurately.
- Retries eventually succeed or ultimately fail per fixture.
- Delegates before the failure point may be re-invoked; never assume only the failing delegate re-runs.
- Side effects of earlier delegates are safe when reprocessed.

For example, the first processor calls an API and a later processor fails: retrying the chain can call the first API multiple times. If the API has side effects, use idempotency keys or move side effects to an appropriate step.

Do not count invocations only on the failing delegate. Check invocation counts on preceding delegates too and confirm the chain retains no corrupted mutable state across attempts.

## 21. Testing skip policies

If the Step skips an exception type raised from the chain, failing items are not written and the Step continues per policy. Use `SkipListener` to verify items and exceptions are recorded:

```java
@Bean
SkipListener<OrderInput, OrderExport> orderSkipListener(
        RejectedOrderRepository rejectedOrders) {

    return new SkipListener<>() {
        @Override
        public void onSkipInProcess(
                OrderInput item,
                Throwable failure) {
            rejectedOrders.record(item.orderId(), failure.getClass().getSimpleName());
        }
    };
}
```

In tests, verify `processSkipCount`, that rejected items are saved accurately, and that other valid items still reach the writer. Do not skip generic exceptions broadly; configure exception types by business rules and separate data errors from transient system errors.

## 22. Listeners observing a processor chain

`ItemProcessListener<I, O>` attaches to the processor used by the Step. When the Step uses `CompositeItemProcessor`, Step-level listeners observe the composite as a single processor; they do not automatically fire callbacks for each inner delegate.

If per-delegate timing or logging is needed, you can:

- Wrap each delegate in a timing decorator.
- Record metrics inside each processor.
- Use observable collaborators in unit tests.
- Attach branch/step names to structured logs.

Decorator example:

```java
public class TimingProcessor<I, O> implements ItemProcessor<I, O> {

    private final String name;
    private final ItemProcessor<I, O> delegate;
    private final Timer timer;

    public TimingProcessor(
            String name,
            ItemProcessor<I, O> delegate,
            MeterRegistry registry) {
        this.name = name;
        this.delegate = delegate;
        this.timer = Timer.builder("batch.processor.duration")
                .tag("processor", name)
                .register(registry);
    }

    @Override
    public O process(I item) throws Exception {
        return timer.recordCallable(() -> delegate.process(item));
    }
}
```

Decorators must preserve delegate semantics, including returning `null` and propagating exceptions. When wrapping delegates, ensure other stream/listener lifecycles (if the delegate implements `ItemStream`) are forwarded or registered separately.

## 23. Testing side effects and idempotency in a chain

An ideal processor simply transforms items and returns output. In practice, a delegate may call an API, write audits, or update a database. If the Step retries, the processor may re-run and repeat side effects.

Tests should verify:

- Retrying the same business item does not create unintended duplicate transactions/API calls.
- Idempotency keys stay identical across attempts.
- Audits do not record success prior to chunk commit if atomicity is required.
- Delegates do not hold per-item mutable state in singleton fields.
- When a delegate is re-invoked, outputs remain deterministic or errors are handled explicitly.

Example test verifying a service receives the idempotency key:

```java
verify(paymentGateway, times(1)).submit(
        eq("order-O-100"),
        any(PaymentRequest.class));
```

In integration tests with retries, assertions should check the number of operations actually committed/accepted, not merely how many times a processor method ran.

## 24. Testing null inputs and validation boundaries

If a reader can return `null`, define the reader/processor contract. In Spring Batch, `ItemReader.read()` returns `null` to signal end of data; `ItemProcessor` is not normally invoked with a null item as a valid record.

If a field inside an item is null, test separately how delegates handle that field. Never confuse `read() == null` (EOF) with `process(item) == null` (item filtered).

Example:

```java
@Test
void missingCustomerCodeIsRejected() {
    OrderInput input = new OrderInput("O-100", null, "125.50");

    assertThatThrownBy(() -> normalizeProcessor.process(input))
            .isInstanceOf(InvalidOrderException.class);
}
```

If business policy requires filtering instead of rejecting, the processor can return `null`; integration tests must verify filter counts and absence of output.

## 25. Testing data mutations between delegates

A processor chain executes sequentially on the same item reference/value. When delegates use mutable objects, an earlier step can mutate the object received by a later step. Sometimes this is intentional, yet it can create subtle coupling.

Prefer immutable DTOs/records as intermediate types. When mutable objects are used, tests must verify which fields change and which values downstream delegates observe.

For example, a bug can occur when a normalize processor mutates an input object shared in a cache or singleton field. Testing with two consecutive items helps detect one item's data leaking into the next item.

Never store `currentItem`, `currentCustomer`, or per-item accumulators in mutable fields of a singleton processor without explicit lifecycle/reset and concurrency contracts.

## 26. Testing concurrency in multi-threaded Steps

`CompositeItemProcessor` invokes delegates sequentially per item; the chain itself does not run one item's delegates in parallel. However, a multi-threaded Step can invoke the same composite/delegate instance from multiple threads depending on configuration.

Test concurrency when:

- The Step uses a task executor for chunk/item processing.
- Multiple Jobs/Steps share singleton beans.
- Delegates hold caches or mutable state.
- Collaborators are not thread-safe.
- Side effects or business ordering depend on items.

Tests should submit many distinct items concurrently and verify outputs never mix fields or correlation IDs. If a delegate is not thread-safe, use an appropriate scope, stateless design, thread-safe collaborators, or adjust concurrency.

Never assume that because a chain runs sequentially per item, the whole bean is accessed by only one thread at a time.

## 27. Testing chains with multiple filtering steps

If multiple delegates can return `null`, test different filter positions:

```text
Input -> Normalize -> Validate -> Enrich -> Map
              |          |         |
              |          |         +--> null: do not call Map
              |          +------------> null: do not call Enrich/Map
              +-----------------------> null: do not call Validate/Enrich/Map
```

You do not need to duplicate every test if composite semantics are uniform, yet each delegate with filtering logic needs its own unit tests. One representative composite test verifies short-circuiting; Step integration tests verify combined filter counts are accurate.

If the chain has side effects prior to a filter step, consider moving filtering/validation ahead of side effects to avoid calling APIs or writing audits for ultimately excluded items.

## 28. Testing mapping errors between intermediate types

A chain can compile while still mapping fields wrongly. For instance, an enrich processor receives the right customer code yet constructs `EnrichedOrder` with the previous item's `orderId` due to a mutable cache.

Unit tests should verify:

- Every output field comes from the right input field.
- `BigDecimal` is not converted through `double` causing precision loss.
- Dates/times preserve required timezones and formats.
- Null/blank semantics are explicit.
- Identifiers are not altered unintentionally.
- Mapping does not drop fields needed by the next delegate.

For complex mappings, use fixtures with distinct values in every field to expose swapped assignments. Avoid tests reusing the same value across multiple fields, as broken mappings might still pass.

## 29. Testing side-effect ordering and output ordering

Delegate ordering within a single item is fixed by the configuration list. Ordering across items depends on the reader, chunking, and Step concurrency.

If business rules require global item processing order, configure the Step/partitioning appropriately and test at the Step level. `CompositeItemProcessor` does not guarantee item 1 finishes the entire chain before item 2 starts under every concurrent setup.

If only output ordering by a sort key is needed, ensure the reader has a stable sort and the writer does not reorder. Assert outputs using lists of business keys, not just total item counts.

## 30. Testing chains with Spring Batch Test

Spring Batch Test provides utilities to run Jobs/Steps in integration tests. A typical setup includes:

- `@SpringBatchTest` to register test utilities/listeners.
- `@SpringJUnitConfig` or an equivalent Spring test context.
- `JobLauncherTestUtils` to launch Jobs or Steps.
- `JobRepositoryTestUtils` to clean metadata between tests when appropriate.
- StepScope test support if readers/processors/writers use `@StepScope`.

Example testing the full flow:

```java
@SpringBatchTest
@SpringJUnitConfig(OrderJobTestConfiguration.class)
class OrderJobProcessorChainTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    OrderExportRepository exportRepository;

    @Test
    void jobWritesExpectedResultsFromProcessorChain() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("test.run.id", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(exportRepository.findAllForTestRun(parameters))
                .containsExactly(
                        new OrderExport("O-100", "Lan Nguyen",
                                new BigDecimal("125.50")));
    }
}
```

Repository/helper names in the example are application test components. If the writer writes files, replace repository assertions with reading and parsing the staging file. `JobParameters` must guarantee a distinct `JobInstance` per test so metadata does not collide.

## 31. Testing restarts after partial chain processing

Restart tests are valuable when delegates hold state, have side effects, or the processor chain has retryable/skippable errors. Scenario:

1. Seed inputs containing multiple items with deterministic business IDs.
2. Launch the Job for the first time and force Step failure after several chunks commit.
3. Verify committed items produced accurate outputs.
4. Restart the same `JobInstance` with identical identifying parameters.
5. Verify the reader resumes from the right checkpoint.
6. Verify the chain processes remaining items in the right delegate order.
7. Verify there are no duplicate or missing outputs.
8. Verify delegate side effects before/after failure obey idempotency policies.

If the processor chain is stateless and side-effect-free, restart tests can focus on Step wiring/outputs. If delegates maintain caches/state or call external systems, test both lifecycle and recovery.

## 32. Recommended test matrix

A practical test suite can follow this matrix:

| Layer | Case | What to verify |
|---|---|---|
| Delegate unit | Valid input | Output and field mappings are accurate. |
| Delegate unit | Boundary/invalid input | Validation, exceptions, or filters match contract. |
| Delegate unit | Collaborator failure | Exceptions propagate or translate intentionally. |
| Composite unit | Successful chain | Correct order and exact objects passed between steps. |
| Composite unit | Delegate returns null | Chain stops, subsequent delegates do not run. |
| Composite unit | Delegate throws exception | Chain stops, exception propagates out. |
| Composite unit | Delegate invokes side effect | Collaborator call count and order are accurate. |
| Context test | Production bean | Right delegates and ordering are wired. |
| Step integration | Successful chunk | Writer receives accurate output. |
| Step integration | Filtering | `filterCount`, `writeCount`, and outputs are accurate. |
| Step integration | Retry/skip | Counters, listeners, and Step statuses are accurate. |
| Restart integration | Mid-Job failure | No missing/duplicate outputs and side effects are safe. |
| Concurrency test | Many concurrent items | No state leaks across items. |

Not every project needs every row. Choose tests based on actual risk and delegate responsibilities, while always maintaining at least one test per critical delegate and one verifying composition.

## 33. Common mistakes when testing a processor chain

### Testing only the final result

Outputs can turn out right by coincidence even if a delegate was skipped or the chain was misordered. Verify invocations and values passed between every step.

### Testing only a mocked composite

Composition may work while delegate business logic is broken. Write dedicated unit tests for each delegate.

### Failing to verify downstream delegates do not run on filter

Downstream side effects could still fire. Use `verifyNoInteractions` or verify zero invocations.

### Treating null as an exception

Null is a filter per the processor contract. Exceptions are processing errors routed through fault-tolerance policies.

### Testing retries only by counting calls to the failing processor

Delegates before the failure point can re-run too. Test side effects and idempotency across the entire chain.

### Using raw generic types

The compiler loses the ability to catch type mismatches between delegates. Declare explicit input/output types.

### Building a different chain in tests than in production

Tests pass while real beans may inject in the wrong order. Add tests loading the production composite bean from the Spring context.

### Ignoring StepScope

Testing `@StepScope` beans outside scope context can fail to reflect `JobParameters`/`ExecutionContext`. Provide a `StepExecution` test context.

### Asserting only BatchStatus

A `COMPLETED` Job does not prove outputs are right. Assert writer outputs, counters, and business keys.

### Holding mutable state in a singleton processor

Earlier items can corrupt later items or other threads. Prefer stateless processors and immutable intermediate data.

### Skipping concurrency tests with multi-threaded Steps

The chain runs delegates sequentially per item, yet the same instance can be called concurrently for many items. Verify thread safety of all delegates/collaborators.

## 34. Processor chain testing workflow

When building or modifying a chain, follow this sequence:

1. List delegates, input types, output types, and expected order.
2. Unit test each delegate with valid, boundary, and error inputs.
3. Use mocks to test that the composite passes each step's output to the next step.
4. Use `InOrder` to verify invocations happen in order.
5. Test delegates returning `null` and verify the chain short-circuits.
6. Test exceptions and verify subsequent delegates do not run.
7. Test side effects, retries, and idempotency if delegates call external systems.
8. Load the production composite bean to verify wiring and `StepScope`.
9. Integration test the Step/Job with an observable writer.
10. Verify filter/skip/retry counters and listeners.
11. Test restarts if the Job must recover after failure.
12. Test concurrency if multiple items can be processed simultaneously.

| Question | Evidence |
|---|---|
| Is each delegate's business logic right? | Dedicated unit tests per delegate. |
| Is the chain order right? | `InOrder` and concrete intermediate outputs. |
| Are outputs passed accurately? | Verify the next delegate receives the exact object. |
| Does filtering stop the chain? | Subsequent delegates are not called; Step filter count increments. |
| Do exceptions stop the chain? | Exceptions propagate; subsequent delegates do not run. |
| Is production wiring accurate? | Tests loading the composite bean from the Spring context. |
| Does the Step write accurate results? | Integration tests verifying outputs and counters. |
| Are retries safe? | Tests for side effects, reload/idempotency, and retry exhaustion. |

## Conclusion

Testing a processor chain requires verifying both individual delegate behavior and how `CompositeItemProcessor` combines them. Test delegates independently, use mocks and `InOrder` to prove right ordering and data handoffs between steps, and verify `null` halts the chain while exceptions propagate. Testing production beans and running Step integration tests catches wiring mistakes, `StepScope` issues, and errors in filter/skip/retry counters and outputs. If delegates have side effects or the Step runs multi-threaded, also verify idempotency, state isolation, and thread safety. A chain is trustworthy only when each step is sound, composition is right, and the Step uses the chain per its business contract.
