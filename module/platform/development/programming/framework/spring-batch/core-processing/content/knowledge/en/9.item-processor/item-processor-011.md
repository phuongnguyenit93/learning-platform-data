# Testing a processor with valid and invalid items

In Spring Batch, `ItemProcessor` receives an item from `ItemReader`, validates or transforms the data, and returns an item for `ItemWriter`. When building a processor, you need to clearly define how to handle three cases: a valid item, an item that needs to be dropped from the flow, and an item that is invalid to the point of reporting an error.

Testing a processor should verify both the returned result and the behavior when data is wrong. Unit tests make it quick to check the processing logic for each item; Step or Job tests confirm that Spring Batch applies transactions, filtering, skipping, and execution status correctly.

## 1. Defining the processor's behavior

`ItemProcessor<I, O>` takes an object of type `I` and returns an object of type `O`. The processor can keep the same data type or convert to a different type.

There are three important outcomes:

| Situation | Processor behavior | Meaning in Spring Batch |
|---|---|---|
| Valid item | Returns the validated or transformed object | The item is passed to the Writer. |
| Item to be filtered | Returns `null` | The item is filtered and is not passed to the Writer. |
| Invalid item | Throws an exception | The Step may fail, retry, or skip depending on the fault-tolerance configuration. |

You should not use `null` and exceptions interchangeably at random. Filter is generally for records that are structurally valid but do not belong to the dataset to be processed, for example a cancelled order. An exception is appropriate when the data is wrong or cannot be processed, for example a missing required customer ID or a negative amount.

## 2. Example processor to test

Suppose the application imports orders. A valid order must have a customer ID and an amount greater than 0. An order with status `CANCELLED` is removed from the flow; data that violates a required rule causes the processor to throw `InvalidOrderException`.

```java
import java.math.BigDecimal;
import org.springframework.batch.item.ItemProcessor;

public class OrderProcessor
        implements ItemProcessor<Order, ProcessedOrder> {

    @Override
    public ProcessedOrder process(Order order) {
        if ("CANCELLED".equals(order.status())) {
            return null;
        }

        if (order.customerId() == null || order.customerId().isBlank()) {
            throw new InvalidOrderException("Customer ID is required");
        }

        if (order.amount() == null
                || order.amount().compareTo(BigDecimal.ZERO) <= 0) {
            throw new InvalidOrderException("Amount must be greater than zero");
        }

        return new ProcessedOrder(
                order.id(),
                order.customerId(),
                order.amount());
    }
}
```

In this example, `Order` and `ProcessedOrder` are the application's domain data types; they can be defined as Java records or regular classes. `InvalidOrderException` is a dedicated business exception, usually extending `RuntimeException`:

```java
public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}
```

The processor does not modify the input object; instead it creates a new `ProcessedOrder` after the data passes the checks. Writing it this way makes the result easy to test and reduces side effects when Spring Batch retries or reprocesses an item.

## 3. Unit tests for valid items

Unit tests can call `process()` directly without initializing a Spring context, JobRepository, or JobLauncher. The goal is to confirm that a valid item is converted correctly.

An example using JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class OrderProcessorTest {

    private final OrderProcessor processor = new OrderProcessor();

    @Test
    void convertsValidOrder() throws Exception {
        Order input = new Order(
                "ORD-100",
                "CUS-10",
                new BigDecimal("125.50"),
                "NEW");

        ProcessedOrder result = processor.process(input);

        assertNotNull(result);
        assertEquals("ORD-100", result.id());
        assertEquals("CUS-10", result.customerId());
        assertEquals(new BigDecimal("125.50"), result.amount());
    }
}
```

This test checks the important output properties instead of only asserting that the result is not `null`. If the processor has calculation or data-normalization rules, you should check both the transformed values and the preserved fields.

## 4. Unit tests for invalid items

For items that violate business rules, tests need to confirm the exact exception type and error details. For example, a missing customer ID:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class OrderProcessorInvalidItemTest {

    private final OrderProcessor processor = new OrderProcessor();

    @Test
    void rejectsOrderWithoutCustomerId() {
        Order input = new Order(
                "ORD-101",
                " ",
                new BigDecimal("50.00"),
                "NEW");

        InvalidOrderException exception = assertThrows(
                InvalidOrderException.class,
                () -> processor.process(input));

        assertEquals("Customer ID is required", exception.getMessage());
    }

    @Test
    void rejectsZeroOrNegativeAmount() {
        Order input = new Order(
                "ORD-102",
                "CUS-10",
                BigDecimal.ZERO,
                "NEW");

        assertThrows(
                InvalidOrderException.class,
                () -> processor.process(input));
    }
}
```

You should test boundary cases such as `null`, empty strings, whitespace-only strings, zero, negative numbers, and unusually large values if they matter to the business. Each test should focus on a single condition so that when it fails you can identify which rule is broken.

## 5. Testing filtered items

If the processor returns `null`, Spring Batch treats that item as filtered. The item is not sent to the Writer, though this is not a skip caused by an exception.

```java
import static org.junit.jupiter.api.Assertions.assertNull;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class OrderProcessorFilterTest {

    private final OrderProcessor processor = new OrderProcessor();

    @Test
    void filtersCancelledOrder() throws Exception {
        Order cancelled = new Order(
                "ORD-103",
                "CUS-10",
                new BigDecimal("75.00"),
                "CANCELLED");

        assertNull(processor.process(cancelled));
    }
}
```

Distinguishing filtering from skipping is very important when reading operational metrics:

- `filterCount` increases when the processor returns `null`.
- `processSkipCount` increases when the processor throws an exception and that exception is configured to be skippable.

If an invalid record must be written to an error table or sent to a data-repair workflow, you should not just return `null` because doing so drops the record from the flow without automatically saving it anywhere. You can use a listener, the skip mechanism, or a separate processing branch depending on business requirements.

## 6. Using parameterized tests for many data cases

When many input values must obey the same rule, JUnit 5 supports `@ParameterizedTest`. This reduces test duplication while still expressing boundary cases clearly.

Example of testing several invalid amount values:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class OrderProcessorAmountTest {

    private final OrderProcessor processor = new OrderProcessor();

    @ParameterizedTest
    @ValueSource(strings = {"0", "-0.01", "-100"})
    void rejectsNonPositiveAmounts(String amount) {
        Order input = new Order(
                "ORD-104",
                "CUS-10",
                new BigDecimal(amount),
                "NEW");

        assertThrows(
                InvalidOrderException.class,
                () -> processor.process(input));
    }
}
```

You can use `@CsvSource` or `@MethodSource` when a test needs multiple data fields at once, such as customer ID, amount, status, and expected outcome. Name tests to reflect the rule being checked so that test reports are easy to read.

## 7. Mocking dependencies when the processor calls an external service

A real processor may depend on a service to look up customers, convert currencies, or check limits. Unit tests should isolate the processor with Mockito to actively control the dependency's results.

For example:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.when;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class CustomerEnrichmentProcessorTest {

    @Mock
    private CustomerService customerService;

    @InjectMocks
    private CustomerEnrichmentProcessor processor;

    @Test
    void enrichesOrderForKnownCustomer() throws Exception {
        Order input = new Order(
                "ORD-105", "CUS-10", new BigDecimal("80.00"), "NEW");
        when(customerService.findName("CUS-10"))
                .thenReturn("Lan Nguyen");

        EnrichedOrder result = processor.process(input);

        assertEquals("Lan Nguyen", result.customerName());
    }
}
```

Mocks let you check how the processor reacts when the service returns data, does not find the customer, or throws an exception. Do not mock the very logic you are trying to test; mock only the external dependency boundary so the test focuses on the processor's behavior.

## 8. Step integration testing with Spring Batch Test

Unit tests verify the processor's logic, but they do not prove that the Step applies skip, filter, transactions, and data writing properly. When you need to check coordination across components, you can use the `spring-batch-test` module.

With Spring Boot, `@SpringBatchTest` provides utilities such as `JobLauncherTestUtils`. `launchStep` lets you run a specific Step with test JobParameters.

The example below assumes the application has a Job configured for tests, a Step named `processOrdersStep`, a reader reading a fixture containing one invalid order, and the Step allows skipping `InvalidOrderException`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
@SpringBatchTest
class ProcessOrdersStepTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void skipsInvalidOrderAndCompletesStep() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("testRun", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchStep(
                "processOrdersStep", parameters);

        StepExecution stepExecution = execution.getStepExecutions()
                .iterator()
                .next();

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertEquals(1, stepExecution.getProcessSkipCount());
    }
}
```

For the test to run, you need the `spring-batch-test` dependency, a test context configuration containing the Job/Step, and a deterministic input fixture. If the application has multiple Jobs, configure `JobLauncherTestUtils` to point to the exact Job under test. A unique `testRun` parameter prevents test runs from accidentally reusing an already completed JobInstance.

In a Step that does not allow skipping, you can verify that the JobExecution or StepExecution ends with `FAILED` when the processor throws an exception. In a Step that allows skipping, confirm that `processSkipCount`, `filterCount`, `writeCount`, and the data the writer receives match the policy.

## 9. Testing the difference between filter and skip

A useful integration test prepares an input set containing three kinds of items:

1. One valid item that is written out.
2. One item that is filtered because it falls outside the processing scope.
3. One invalid item for which the processor throws an exception and the Step is configured to skip that exception type.

Assuming each kind appears once, the expected results can be represented as follows:

| Metric | Expected value | Explanation |
|---|---:|---|
| `readCount` | 3 | The reader read three items. |
| `filterCount` | 1 | One item was dropped by the processor returning `null`. |
| `processSkipCount` | 1 | One item caused an exception and was skipped. |
| `writeCount` | 1 | Only the valid item was passed to the Writer. |

Actual counters depend on the Step configuration, retry, transaction, and when the error occurs. When testing, you should also verify the content the Writer wrote instead of relying only on total counts. If using a test database, you can query the target table after the Step completes to confirm the correct record is present and no filtered/skipped record is there.

## 10. Testing when the processor uses StepScope or JobParameters

A processor can be declared `@StepScope` to receive JobParameters or values in the `ExecutionContext`. When calling the processor directly in a unit test, the scoped values are not initialized without a Step context.

Example of a processor that gets a business date from JobParameters:

```java
import java.time.LocalDate;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
@StepScope
public class BusinessDateProcessor
        implements ItemProcessor<Order, DatedOrder> {

    private final LocalDate businessDate;

    public BusinessDateProcessor(
            @Value("#{jobParameters['businessDate']}") String businessDate) {
        this.businessDate = LocalDate.parse(businessDate);
    }

    @Override
    public DatedOrder process(Order order) {
        return new DatedOrder(order.id(), businessDate);
    }
}
```

For a processor that depends on StepScope, you can use `StepScopeTestUtils` and a mock `StepExecution` to open the scope in tests:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;
import org.springframework.batch.test.StepScopeTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
@SpringBatchTest
class BusinessDateProcessorTest {

    @Autowired
    private BusinessDateProcessor processor;

    @Test
    void readsBusinessDateFromJobParameters() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2026-11-15")
                .toJobParameters();
        StepExecution stepExecution =
                MetaDataInstanceFactory.createStepExecution(parameters);

        DatedOrder result = StepScopeTestUtils.doInStepScope(
                stepExecution,
                () -> processor.process(new Order("ORD-106", "CUS-10",
                        new BigDecimal("40.00"), "NEW")));

        assertEquals(LocalDate.of(2026, 11, 15), result.businessDate());
    }
}
```

In this example, `DatedOrder` is the output type with a `businessDate` field; `Order` is the domain input used in the earlier sections. The test context needs to register the `BusinessDateProcessor` bean and enable Spring Batch test support. If the processor does not depend on scope, a direct unit test is simpler and does not need a Spring context.

## 11. Additional cases to test

Beyond basic valid and invalid items, a processor usually needs to be tested with these situations:

- **Boundary values:** amount equal to 0, negative values, dates at the start/end of a period, strings at maximum length.
- **Missing data:** required fields that are `null`, empty, or whitespace-only.
- **Malformed data:** invalid dates, unparseable numbers, unsupported status codes.
- **Duplicate data:** two items with the same business key and how the processor handles each item.
- **Failing dependencies:** a service timing out, returning `null`, or throwing an exception.
- **Repeatability:** whether processing the same input multiple times produces consistent results, especially when the Step has retry.
- **No unintended mutation of input:** if the processor creates a new output, confirm the input object remains unchanged when that is a design requirement.

## 12. Common testing mistakes

| Issue | Cause | Remedy |
|---|---|---|
| Only asserting the result is not `null` | Misses wrong data fields or wrong transformations. | Check the important fields of the output. |
| Using `assertNull` for every bad item | Confuses items to filter with items that must report an error. | Define the rules clearly: filter returns `null`, business error throws an exception. |
| Unit test needs to boot the whole Spring context | The processor depends too heavily on the container or scope. | Extract pure logic for direct testing; use Spring context only for integration tests. |
| Testing the Step without checking written data | The Step may be COMPLETED while the output is wrong. | Check writer output or query the target data. |
| Not checking skip/filter counts | Unclear by which mechanism items were dropped. | Assert `filterCount`, `processSkipCount`, and `writeCount`. |
| Tests depending on an old JobInstance | Tests reuse identifying JobParameters and are rejected on launch. | Use unique test parameters or clean metadata according to the test configuration. |
| Mocking the entire processor | The test does not execute the logic under test. | Mock only external dependencies, keeping the real processor in unit tests. |

## Conclusion

Testing an `ItemProcessor` needs to clearly verify three behaviors: valid items are transformed correctly, items to be discarded return `null`, and items violating rules must throw an appropriate exception. JUnit unit tests quickly check individual rules and boundary values; Mockito isolates external dependencies. Step or Job testing with Spring Batch Test verifies how the framework handles filtering, skipping, transactions, and written data. When you properly distinguish filtering from skipping and verify both output and metadata, the tests will closely reflect batch behavior in a real environment.
