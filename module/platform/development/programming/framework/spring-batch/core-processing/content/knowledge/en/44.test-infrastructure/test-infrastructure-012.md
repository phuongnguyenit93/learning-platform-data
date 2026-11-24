# Distinguishing Unit Tests and Batch Integration Tests in Spring Batch

In a Spring Batch application, the same processing logic can be tested at multiple levels. For instance, an order-import step has an `ItemReader` fetching data, an `ItemProcessor` normalizing it, and an `ItemWriter` persisting it to a database. You can call `ItemProcessor.process()` directly to verify normalization rules, or launch a real `Step` to verify that reader, processor, writer, transactions, and Spring Batch infrastructure work together properly.

Those two kinds of tests address **two different categories of risk**:

- A **unit test** verifies a single unit of logic while external dependencies are isolated or replaced by test doubles. It typically does not start a Spring context, `JobRepository`, database, or Batch runtime.
- A **batch integration test** verifies the real collaboration of components inside a step or job, including Spring Batch execution infrastructure when within scope. It typically creates a Spring context, `JobRepository`, transaction manager, and resources such as test databases or files.

The deciding factor is **not** whether the test filename ends in `*UnitTest` or `*IntegrationTest`, nor merely whether `@SpringBootTest` is present. Look at the *system boundary actually executed*: does it run batch mechanics, perform real I/O through the infrastructure, and verify state and side effects, or does it invoke pure Java logic directly?

This is foundational knowledge for the **Test infrastructure** chapter in **Spring Batch Core Processing**: picking the right test level catches bugs accurately, keeps suites fast, and minimizes brittle tests.

## 1. An Example to Illustrate Both Levels

Suppose a job imports a list of order codes:

```text
importOrdersJob
  |
  +-- importOrdersStep (chunk-oriented)
        |
        +-- ItemReader<String>       reads: " a001 ", "  ", " b002 "
        |
        +-- ItemProcessor<String,String>
        |      trim + uppercase
        |      blank line -> null (filter)
        |
        +-- ItemWriter<String>       writes normalized codes to database
```

**The unit test question:** Given `" a001 "`, does the processor return `"A001"`? Given a blank line, does it return `null` to filter it?

**The integration test question:** When running `importOrdersStep`, does the framework read three items, filter one, write two, mark the step `COMPLETED`, and actually persist `A001` and `B002` in the database?

If the processor is correct while the writer points to the wrong table name, unit tests still pass. If the writer works while a normalization rule fails on a subtle edge case, an integration test with overly simple fixtures might miss it. Thus, both levels of testing are essential.

## 2. Comparing Unit Tests and Batch Integration Tests

| Criterion | Unit Test | Batch Integration Test |
| --- | --- | --- |
| Primary goal | Verify logic of a single class/method and contract at its boundary | Verify components working together in a step, job, and execution infrastructure |
| Typical targets | `ItemProcessor`, validators, mappers, formatters, extracted tasklet services | `Step`, `Job`, real readers/writers, listeners, transactions, `JobRepository` |
| Spring context startup | Usually unnecessary | Usually required, via Spring Test or Spring Boot Test |
| Data | Java objects, collections, mocks/stubs | File fixtures, test databases, `JobParameters`, `ExecutionContext` |
| Dependencies | Mocks/fakes/stubs or simple controlled dependencies | Real components within integration scope; mock only systems outside test scope |
| Execution | Direct method call | Launch `Step`/`Job` via Batch test tools or version-appropriate `JobOperator`/launcher |
| Assertions | Return values, exceptions, collaborator interactions | `JobExecution`, `StepExecution`, exit status, read/write/skip counts, committed data |
| Transactions and restart | Not verified by calling methods alone | Verifiable in Batch and repository test infrastructure |
| Speed | Typically fast and easy to isolate | Usually slower due to context startup and I/O |
| Configuration fidelity | Does not verify wiring, scopes, or real schemas | Catches wiring, SQL, transaction, scope, and flow errors in executed paths |
| When failing | Usually points directly to broken logic | Requires investigating configuration, dependencies, metadata, or data |

An integration test **does not have to** launch an entire job. Running one step through Spring Batch with a real `JobRepository` is already a step-level integration test. Conversely, a test annotated with `@SpringBootTest` that mocks every dependency and invokes a single method still mostly tests component logic; an annotation alone does not define test depth.

## 3. Unit Tests: Testing `ItemProcessor` Without Running Spring Batch

In Spring Batch, `ItemProcessor<I, O>` is a natural place for unit-testable logic. Example processor that normalizes order codes and filters blank lines:

```java
package com.example.batch;

import java.util.Locale;
import org.springframework.batch.item.ItemProcessor;

public final class NormalizeOrderCodeProcessor
        implements ItemProcessor<String, String> {

    @Override
    public String process(String item) {
        if (item == null || item.isBlank()) {
            // Spring Batch treats null from a processor as a filtered item.
            return null;
        }

        String code = item.strip().toUpperCase(Locale.ROOT);
        if (code.length() > 20) {
            throw new IllegalArgumentException("Order code is too long");
        }
        return code;
    }
}
```

Unit test with JUnit Jupiter and AssertJ:

```java
package com.example.batch;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class NormalizeOrderCodeProcessorTest {

    private NormalizeOrderCodeProcessor processor;

    @BeforeEach
    void setUp() {
        processor = new NormalizeOrderCodeProcessor();
    }

    @Test
    void normalizesLeadingWhitespaceAndCase() throws Exception {
        assertThat(processor.process(" a001 ")).isEqualTo("A001");
        assertThat(processor.process("b002")).isEqualTo("B002");
    }

    @Test
    void filtersBlankOrNullInput() throws Exception {
        assertThat(processor.process("   ")).isNull();
        assertThat(processor.process(null)).isNull();
    }

    @Test
    void rejectsCodeLongerThanLimit() {
        assertThatThrownBy(() -> processor.process("X".repeat(21)))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessage("Order code is too long");
    }
}
```

The test above **does not use** `@SpringBootTest`, `@SpringBatchTest`, a database, or `JobParameters`. It directly proves per-call outputs and edge-case behavior of `process()`. However, this unit test cannot prove that a real step invokes the processor, filters the expected count, writes to the database, or commits cleanly.

### 3.1. When to Use Mocks/Stubs?

If a processor calls `PricingService`, `ReferenceDataClient`, or `OrderRepository`, unit tests can replace them with Mockito mocks or fakes to control outputs and faults:

```java
// Illustrative pattern when a production processor depends on PricingService.
PricingService pricing = mock(PricingService.class);
when(pricing.getRate("VIP")).thenReturn(new BigDecimal("0.90"));

OrderPriceProcessor processor = new OrderPriceProcessor(pricing);
OrderPrice actual = processor.process(new Order("A001", "VIP"));

assertThat(actual.total()).isEqualByComparingTo("90.00");
verify(pricing).getRate("VIP");
```

`PricingService`, `OrderPriceProcessor`, `Order`, and `OrderPrice` are illustrative application types, not Spring Batch APIs. The pattern clarifies the boundary: the test verifies how the processor handles the service's return value, **not** the real service or database. Likewise, never mock the `ItemProcessor` under test itself, as its logic would never run.

### 3.2. Tasklets and Writers Can Also Be Unit Tested

Not every `Tasklet` requires launching a `Step`. If a tasklet delegates to a business service, extract the logic from the framework API and unit test that service directly. Similarly, CSV line formatting or entity mapping logic can be tested without opening files or databases. Still, verifying `ItemStream` lifecycle, chunk transactions, and skip/retry mechanics requires integration tests.

## 4. Batch Integration Tests: Launching a Step and Verifying Real Outcomes

An integration test for `importOrdersStep` requires these pieces:

```text
JUnit 5 / Spring Test
          |
    Spring ApplicationContext
          |
    JobLauncherTestUtils (Spring Batch 5)
          |
        Step / Job
          |
  Reader -> Processor -> Writer
          |
  PlatformTransactionManager
          |
     H2 Database (test)
          |
  JobRepository + BATCH_* metadata tables
```

Here H2 stands in for the real database in the test environment. In applications relying on PostgreSQL/Oracle-specific SQL or specialized locking and transaction features, Testcontainers with the application's actual database engine provides higher fidelity than H2.

### 4.1. Example Dependencies

The following example uses **Spring Boot 3.x, Spring Batch 5.x, JUnit Jupiter**, and Gradle. Let the Spring Boot BOM align library versions:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

`spring-batch-test` includes `@SpringBatchTest`, `JobLauncherTestUtils`, `JobRepositoryTestUtils`, and job/step scope utilities. `@SpringBatchTest` sets up batch test infrastructure; by itself it does not replace declaring the Spring context via `@SpringBootTest` or equivalent test configuration.

### 4.2. Complete Integration Test for a `chunk-oriented Step`

Using `NormalizeOrderCodeProcessor` from earlier, create the following test class at `src/test/java/com/example/batch/NormalizeOrdersStepIntegrationTest.java`:

```java
package com.example.batch;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.support.ListItemReader;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBatchTest
@SpringBootTest(
    classes = NormalizeOrdersStepIntegrationTest.TestBatchApplication.class,
    properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always"
    }
)
class NormalizeOrdersStepIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeEach
    void createAndClearBusinessTable() {
        jdbcTemplate.execute("""
            CREATE TABLE IF NOT EXISTS processed_codes (
                code VARCHAR(20) NOT NULL
            )
            """);
        jdbcTemplate.update("DELETE FROM processed_codes");
    }

    @Test
    void runsReaderProcessorWriterAndCommitsResults() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
            // Uniquely identify each run to avoid colliding with a completed JobInstance.
            .addString("testRunId", UUID.randomUUID().toString())
            .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchStep(
            "normalizeCodesStep", parameters
        );

        assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(execution.getStepExecutions()).hasSize(1);

        StepExecution stepExecution =
            execution.getStepExecutions().iterator().next();

        assertThat(stepExecution.getStepName()).isEqualTo("normalizeCodesStep");
        assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(stepExecution.getReadCount()).isEqualTo(3);
        assertThat(stepExecution.getFilterCount()).isEqualTo(1);
        assertThat(stepExecution.getWriteCount()).isEqualTo(2);

        List<String> committedCodes = jdbcTemplate.queryForList(
            "SELECT code FROM processed_codes ORDER BY code",
            String.class
        );
        assertThat(committedCodes).containsExactly("A001", "B002");
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestBatchApplication {

        @Bean
        Job normalizeCodesJob(
                JobRepository jobRepository,
                @Qualifier("normalizeCodesStep") Step normalizeCodesStep) {
            return new JobBuilder("normalizeCodesJob", jobRepository)
                .start(normalizeCodesStep)
                .build();
        }

        @Bean
        @StepScope
        ItemReader<String> codesReader() {
            // Create a fresh reader per StepExecution to avoid reusing a spent cursor.
            return new ListItemReader<>(List.of(" a001 ", "   ", " b002 "));
        }

        @Bean
        Step normalizeCodesStep(
                JobRepository jobRepository,
                PlatformTransactionManager transactionManager,
                @Qualifier("codesReader") ItemReader<String> reader,
                JdbcTemplate jdbcTemplate) {

            return new StepBuilder("normalizeCodesStep", jobRepository)
                .<String, String>chunk(2, transactionManager)
                .reader(reader)
                .processor(new NormalizeOrderCodeProcessor())
                .writer(chunk -> {
                    for (String code : chunk) {
                        jdbcTemplate.update(
                            "INSERT INTO processed_codes(code) VALUES (?)", code
                        );
                    }
                })
                .build();
        }
    }
}
```

**Key differences from the unit test in Section 3:**

1. Spring Test starts an `ApplicationContext` with configured `Job`, `Step`, reader, and dependencies. `spring.batch.job.enabled=false` stops Spring Boot from auto-running jobs at context startup; the test explicitly launches the step.
2. `@SpringBatchTest` supplies `JobLauncherTestUtils`. `launchStep("normalizeCodesStep", ...)` asks Batch to execute the step with `JobRepository`, transactions, and metadata. Because this tests a single step, other steps in a real job do not run automatically.
3. `@StepScope` ensures a fresh `ListItemReader` is created per step execution. This matters especially for stateful/cursor readers, where reusing one instance across runs leaves later tests with no remaining items.
4. `processed_codes` is a real business table in the test H2 database. Checking `BatchStatus.COMPLETED` alone is insufficient; assertions also verify `readCount`, `filterCount`, `writeCount`, and persisted rows.
5. `INSERT` statements execute inside chunk transactions. To verify rollback, add a controlled failure scenario and inspect which rows committed or rolled back after the step terminates.
6. `testRunId` is an identifying `JobParameter` preventing collisions with an already completed `JobInstance`. In real suites, also isolate business tables or databases across parallel tests.

In real projects, test configurations typically **import production step configuration** and swap only out-of-scope dependencies (such as input files or external APIs). The example above defines a minimal configuration inline for clarity, yet copying entire step definitions into tests risks testing a different configuration from production. For genuine integration coverage, inject the real production `Step` whenever possible.

### 4.3. Adjusting for Spring Batch 6

Spring Batch 6.x introduces `JobOperatorTestUtils` and `startStep(...)`, replacing 5.x's `JobLauncherTestUtils.launchStep(...)` (the older API is deprecated). Several core types also moved packages in 6.x. Pick one consistent version matching your project's Spring Boot/dependency stack and update imports and test utilities accordingly; never mix Spring Batch 5 code onto a Spring Batch 6 classpath.

Conceptually, the testing workflow stays the same: prepare fixtures and parameters, launch the real step via the test utility, retrieve `JobExecution` and `StepExecution`, and assert metadata and output.

## 5. Choosing Integration Test Scope: Single Step or Full Job?

Batch integration tests have at least two common scopes:

```text
Unit test:              processor.process(" a001 ")
                             |
                             v
                            "A001"

Step integration test:  [importOrdersStep]
                       Reader -> Processor -> Writer
                             |
                             v
                       StepExecution + output

Job integration test:   [step A] -> [step B] -> [step C]
                             |
                             v
                       JobExecution + final output
```

**Running a single step** works well for testing reads/writes, transactions, skips, retries, or step listeners. In Spring Batch 5, `JobLauncherTestUtils.launchStep(name, params)` creates a wrapper job to run the chosen step. This scope does not prove that the overall job flow is wired correctly.

**Running the full job** works well for testing step ordering, transition conditions, data passed via `JobExecutionContext`, restarts, and end-to-end job effects. In Spring Batch 5, `JobLauncherTestUtils.launchJob(params)` is the standard entry point when the test context holds the target job. A suite often needs both: multiple step tests for broad data coverage and targeted job tests for critical flows.

| What You Need to Prove | Scope to Choose |
| --- | --- |
| Code normalization rules and null-input handling | Processor unit test |
| Real reader opens files and parses records | Reader or step integration test with file fixtures |
| Chunk writes to database and transaction commits | Step integration test |
| Retry/skip policy applies properly | Step integration test with controlled injected faults |
| `@StepScope` receives right `JobParameters` | Component scope test or step integration test |
| Step B receives context written by Step A | Job integration test or multi-step integration test |
| Job branching based on `ExitStatus` | Job integration test |
| Restart skips already committed data | Integration test with `JobRepository` and persisted state across restart |

## 6. Differences in Dependencies and Test Doubles

### In Unit Tests

Use simple dependencies, fakes, stubs, or mocks to control inputs and verify interactions. For instance, if a processor calls `ExchangeRateService`, tests can return a fixed rate without hitting the network or database. You do not need to spin up a full job to know whether arithmetic inside the processor is right.

The limitation is that mocks behave strictly as the test author scripts them. If a mocked `OrderRepository.save()` always succeeds, unit tests will never catch broken SQL, rolled-back transactions, or database `UNIQUE` constraint violations.

### In Batch Integration Tests

Use real components within the boundary under test:

- When testing `JdbcBatchItemWriter`, use a test database and verify persisted rows rather than mocking `JdbcTemplate` and counting calls.
- When testing `FlatFileItemWriter`, write to `@TempDir` and read back contents, encoding, and line ordering.
- When testing restart, use a `JobRepository` whose metadata survives across the relevant runs.
- When integrating with external systems outside the test boundary (payment APIs, email, message brokers), use a stub server or matching test container. Keep that boundary explicit.

Not every integration test has to connect to every external system live. For example, you can test the entire reader–processor–writer pipeline and batch transactions against H2 while mocking an external pricing API. The test then proves the integration **inside the test boundary**, not that the live external API works.

## 7. What Infrastructure Does a Batch Integration Test Need?

### 7.1. `ApplicationContext` and Bean Configuration

The Spring context wires job, step, reader, writer, processor, listener, and infrastructure beans. Annotations such as `@StepScope` and `@JobScope` enable late binding from `JobParameters` or `ExecutionContext`.

Ordinary unit tests need no scopes. However, if you want to test a single `@StepScope` component without running an entire step, Spring Batch Test offers `StepScopeTestUtils` and `MetaDataInstanceFactory` to establish a `StepExecution` for the test.

### 7.2. `JobRepository` and Metadata

`JobRepository` stores `JobInstance`, `JobExecution`, `StepExecution`, execution contexts, and statuses. Batch integration tests rely on the repository to evaluate start, completion, failure, and restart behavior. The `BATCH_*` tables must exist in the test database before launching a step or job. With Spring Boot 3.x and an embedded database, `spring.batch.jdbc.initialize-schema=always` handles this in test configuration.

Persisted metadata introduces an important rule: launching the same job name and **identifying `JobParameters`** against a repository that already recorded a `COMPLETED` run may raise `JobInstanceAlreadyCompleteException`. That is expected Spring Batch behavior, not a business logic bug. Tests must supply distinct parameters or clean metadata explicitly in a dedicated test database.

### 7.3. `PlatformTransactionManager`

Chunk-oriented steps manage commits and rollbacks via the transaction manager. Processor unit tests cannot simulate this. Integration tests can force a writer failure on a specific item to verify how many records committed beforehand, step status, and retry/skip policy effects.

Note: placing `@Transactional` directly on a test method does not equate to testing step transactions. Test-managed transactions and Spring Batch-managed transactions can interact in confusing ways, especially on the same thread. For tests proving data **actually committed**, query the database after the step finishes and clean up separately.

### 7.4. Fixtures and External Environment

Keep input sets small with clear expected outputs. For files, place source fixtures in `src/test/resources` and write outputs to `@TempDir`. For databases, use isolated schemas/databases and reset business data between cases. When H2 does not faithfully match production SQL or dialect features, use Testcontainers with PostgreSQL, MySQL, or the target database.

## 8. How to Verify Results in Each Test Type

### Unit Tests: Assert Logic

Example for `NormalizeOrderCodeProcessor`:

```java
assertThat(processor.process(" a001 ")).isEqualTo("A001");
assertThat(processor.process("   ")).isNull();
assertThatThrownBy(() -> processor.process("X".repeat(21)))
    .isInstanceOf(IllegalArgumentException.class);
```

Assertions focus on return values, exceptions, and the class contract. When dependencies are mocked, `verify(...)` can help, but avoid coupling tests tightly to internal calls that do not affect externally promised behavior.

### Batch Integration Tests: Assert Metadata **and** Output

```java
assertThat(jobExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(stepExecution.getReadCount()).isEqualTo(3);
assertThat(stepExecution.getFilterCount()).isEqualTo(1);
assertThat(stepExecution.getWriteCount()).isEqualTo(2);

assertThat(jdbcTemplate.queryForList(
    "SELECT code FROM processed_codes ORDER BY code", String.class
)).containsExactly("A001", "B002");
```

This snippet references `jobExecution`/`stepExecution` from the run and the fixture table from Section 4. `BatchStatus.COMPLETED` does not guarantee right data: a step can complete while writing to the wrong column, dropping rows, or producing wrong file encodings. Verifying actual outputs is therefore non-negotiable.

In failure cases, assert `FAILED`, `getFailureExceptions()`, `readSkipCount`, `processSkipCount`, `writeSkipCount`, committed partial data, and `ExecutionContext` entries. Every counter assertion must correspond to concrete fixtures and batch policy rather than arbitrary guesses.

## 9. Failure, Skip, Retry, and Restart: Where Should Each Be Tested?

### Exception-Throwing Rules: Unit Tests

Suppose a processor must reject codes longer than 20 characters. A direct unit test like Section 3 shows the exception is thrown at the exact boundary. Unit tests are ideal for covering wide input matrices because they run fast.

### Skip/Retry Policies: Integration Tests

Spring Batch can be configured to skip specific exceptions or retry transient failures. Processor unit tests cannot prove that the step recognizes the exception in `skip(...)`, retries properly, rolls back the chunk, and updates counters accurately.

For example, when a processor throws `ValidationException` for one item and the step defines a `skipLimit`, an integration test must supply input containing a bad record, run the step, assert `processSkipCount`, and confirm valid records still get written. For writer retries, use a dependency that fails a set number of times before succeeding, and assert the final output contains no duplicates.

### Restart: Integration Tests with Persistent Metadata and State

Restart only makes sense when two runs target the exact same `JobInstance` with prior state and execution context preserved. To test it, let the first run fail at a designed point, inspect data/metadata after failure, and relaunch using your version's restart mechanism. After the second run, verify work resumed cleanly without duplicating previously committed data.

If a test wipes all metadata or changes identifying parameters between the two runs, it tests **a brand-new job instance**, not a restart of the prior run.

## 10. Common Mistakes When Classifying Tests

| Mistake | Why It Is Wrong | Better Approach |
| --- | --- | --- |
| Adding `@SpringBootTest`, calling `processor.process()`, and calling it a full integration test | Batch infrastructure is never executed | Keep a pure unit test for logic; launch a real step/job for integration |
| Mocking `ItemReader`, `ItemProcessor`, and `ItemWriter` and asserting step `COMPLETED` | Wiring runs, yet real read/write logic is untested | Keep real implementations for the components under test; mock only external boundaries |
| Asserting only `BatchStatus.COMPLETED` | Does not verify output records or files | Assert counters, outputs, and final persisted state |
| Using the production database in integration tests | Risks corrupting data and depends on external state | Use a dedicated test database/schema with controlled cleanup |
| Reusing a stateful `ListItemReader` across runs | Cursor may already sit at the end from an earlier test | Instantiate a fresh reader per step execution, e.g., `@StepScope` |
| Reusing identifying parameters of a completed run | Batch rejects rerunning a completed job instance | Generate unique test identities or clean test metadata |
| Deleting output/metadata after phase 1 of a restart test | Destroys the state needed to verify restart | Keep state intact across phases; clean up after final assertions |
| Relying on H2 to prove production-specific SQL | H2 can differ in dialect, locking, or isolation | Use Testcontainers with the target database for critical behaviors |
| Running every test with `@SpringBootTest` | Slow suites and harder root-cause isolation | Use unit tests for logic, integration tests at meaningful boundaries |
| Assuming 5.x and 6.x test APIs are identical | Classes and packages changed across major versions | Check your Spring Batch version and pick the matching test utilities |

## 11. Organizing the Test Suite and Practical Strategy

A project can organize tests by purpose (package names are illustrative):

```text
src/test/java/com/example/batch/
    unit/
        NormalizeOrderCodeProcessorTest.java
        OrderValidatorTest.java
        ReportLineFormatterTest.java

    integration/
        NormalizeOrdersStepIntegrationTest.java
        ExportReportStepIntegrationTest.java
        ImportOrdersJobIntegrationTest.java

src/test/resources/
    fixtures/
        orders-valid.csv
        orders-with-errors.csv
```

Use unit tests for broad coverage of valid inputs, boundary inputs, business rejections, and calculations. For every critical step, add integration tests covering the happy path, actual output, and key failure paths. For every job with non-trivial flow, add a handful of full-job integration tests verifying transitions, inter-step context, and restart.

A quick decision guide before writing a test:

1. **Checking whether a business rule is right?** Call the method directly with Java objects and assert; start with a unit test.
2. **Checking whether reader/processor/writer collaborate properly?** Run a real step with fixtures and `JobRepository`; write a step integration test.
3. **Checking whether steps chain and branch properly?** Run the full job and assert status, flow, and outputs; write a job integration test.
4. **Checking whether database- or external-system-dependent behavior matches deployment?** Write an integration test against compatible services, preferring containers or isolated test environments.

In CI, run unit tests frequently because they are fast; run batch integration tests at stages suited to your project and environment availability. Crucially, keep fixtures, outputs, and metadata isolated so tests fail only when behavior breaks—never because an earlier test left stale state behind.

## 12. Conclusion on Testing Boundaries

A unit test proves **one component fulfills its contract**. A batch integration test proves **components and Spring Batch infrastructure collaborate properly during a real step or job execution**. Combining both delivers fast feedback on logic while catching configuration, transaction, job metadata, resource-scope, and side-effect bugs that unit tests cannot reach.

## References

- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): Spring Batch job/step testing utilities, scopes, and component testing techniques.
- [Spring Batch 5.2 — Testing](https://docs.spring.io/spring-batch/docs/5.2.x/reference/testing.html): using `JobLauncherTestUtils` in Spring Batch 5.x.
- [Spring Framework Reference — Testing](https://docs.spring.io/spring-framework/reference/testing.html): Spring TestContext, JUnit Jupiter, and integration test environments.
- [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): Spring Boot Test mechanics and context management in tests.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): writing and organizing unit and integration tests with JUnit Jupiter.
