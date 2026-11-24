# Testing Individual Steps in Spring Batch

In a multi-step batch job, you sometimes need to verify that a single step processes data accurately without running the entire job. **Testing individual steps** lets you prepare inputs solely for the step under test, run that step inside Spring Batch's infrastructure, and inspect its execution status, output data, and side effects. This is an important technique under the **Testing batch** topic in Spring Batch Core Processing.

For example, an order-import job has three steps:

```text
importOrdersJob
    ├── downloadFileStep
    ├── validateOrdersStep       ← step under test
    └── persistOrdersStep
```

When testing `validateOrdersStep`, we do not want every test run to download a file from an external server or write real data to production storage. Instead, we provide the required data and context to `validateOrdersStep`, run only this step, and verify the outcome. **Testing a single step does not mean ignoring the step's dependencies**: if the step requires a database, transactions, `JobParameters`, or `ExecutionContext`, the test must still supply those dependencies in a controlled way.

## 1. Distinguishing Testing Levels

| Testing Level | Target Executed | When to Use | What to Assert |
| --- | --- | --- | --- |
| Unit test | Plain `ItemProcessor`, `Tasklet`, validator, or service | Quickly testing business rules and edge cases | Return values, exceptions, interactions with dependencies |
| Scoped component test | A `@StepScope` or `@JobScope` bean | Verifying late binding from parameters/context | Injected values, behavior inside the scope |
| **Individual step integration test** | An actual `Step` with `JobRepository` and transactions | Testing reader → processor → writer, status, skip/retry, data persistence | `StepExecution`, committed data, errors, and item counts |
| Full job integration test | Entire `Job` flow | Verifying step order, flow, transitions, context sharing across steps | `JobExecution`, end-to-end output, whole-workflow behavior |

If you only want to test an order-code normalization rule, calling `ItemProcessor.process()` directly is sufficient. If you want to be sure the step reads 10 records, filters 2 records, writes 8 records, and commits properly, you need to run the `Step` itself using Spring Batch's testing tools. Both testing styles complement each other.

## 2. Step Testing Tools

The `spring-batch-test` library provides the core components:

- `@SpringBatchTest`: integrates Spring Batch testing tools into the Spring TestContext; also registers listeners supporting step/job scopes.
- `JobLauncherTestUtils` in **Spring Batch 5.x**: the `launchStep(...)` method runs a step by name using a wrapper job containing only that step.
- `JobOperatorTestUtils` in **Spring Batch 6.x**: the `startStep(...)` method serves the corresponding role. In 6.x, `JobLauncherTestUtils` is deprecated.
- `JobRepositoryTestUtils`: helps prepare or clean up job execution metadata in the repository for testing.
- `MetaDataInstanceFactory`, `StepScopeTestUtils`, and `StepScopeTestExecutionListener`: create mock `StepExecution` objects and activate step scope when testing components in isolation.

Two essential points to understand:

1. `launchStep()`/`startStep()` **runs a step through Spring Batch's execution mechanism**, rather than merely calling a Java method directly. Thus, the step still has execution status, transactions, and metadata in `JobRepository`.
2. They typically use a **single-step wrapper job** for the test run. Preceding or succeeding steps in the real job do not run automatically. Do not use step-test results to conclude that the entire job's flow logic is correct.

### 2.1. Declaring Dependencies

The following examples use **Spring Boot 3.x + Spring Batch 5.x + JUnit Jupiter**. In Gradle, the project needs the corresponding dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

`spring-boot-starter-test` provides JUnit 5 and AssertJ; `spring-batch-test` provides batch test utilities; H2 acts as a test database storing the `BATCH_*` metadata tables. For projects already using a suitable test database, H2 is not mandatory. Let Spring Boot manage consistent dependency versions through its BOM.

## 3. Complete Example: Running an Isolated `TaskletStep`

Suppose `importOrdersJob` has two steps:

1. `prepareInputStep`: prepares the input.
2. `validateBusinessDateStep`: reads the `businessDate` parameter, verifies it is non-blank, and saves the valid date into `StepExecutionContext`.

The test must ensure `validateBusinessDateStep` succeeds when the date is valid, fails when the date is blank, and **does not invoke** `prepareInputStep`.

Place the class below in `src/test/java/.../ValidateBusinessDateStepTest.java` (adjusting `package` to your project). The example configures tests independently from the application's other jobs.

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBatchTest
@SpringBootTest(
    classes = ValidateBusinessDateStepTest.TestBatchApp.class,
    properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always"
    }
)
class ValidateBusinessDateStepTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void runsOnlyTargetStepWithValidParameter() throws Exception {
        // Arrange: parameters identifying the run, independent of the previous step.
        JobParameters parameters = new JobParametersBuilder()
            .addString("businessDate", "2026-11-16")
            .addLong("testCaseId", 1L)
            .toJobParameters();

        // Act: run only the named step.
        JobExecution jobExecution = jobLauncherTestUtils.launchStep(
            "validateBusinessDateStep", parameters
        );

        // Assert: status + business outcome + isolation.
        assertThat(jobExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(jobExecution.getStepExecutions()).hasSize(1);

        StepExecution stepExecution = onlyStep(jobExecution);
        assertThat(stepExecution.getStepName())
            .isEqualTo("validateBusinessDateStep");
        assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(stepExecution.getExitStatus()).isEqualTo(ExitStatus.COMPLETED);
        assertThat(stepExecution.getExecutionContext()
            .getString("validatedBusinessDate"))
            .isEqualTo("2026-11-16");
        assertThat(jobExecution.getExecutionContext()
            .containsKey("preparationDone"))
            .isFalse();
    }

    @Test
    void failsWhenBusinessDateIsBlank() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
            .addString("businessDate", " ")
            .addLong("testCaseId", 2L)
            .toJobParameters();

        JobExecution jobExecution = jobLauncherTestUtils.launchStep(
            "validateBusinessDateStep", parameters
        );

        StepExecution stepExecution = onlyStep(jobExecution);
        assertThat(jobExecution.getStatus()).isEqualTo(BatchStatus.FAILED);
        assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.FAILED);
        assertThat(stepExecution.getFailureExceptions()).isNotEmpty();
        assertThat(stepExecution.getExecutionContext()
            .containsKey("validatedBusinessDate"))
            .isFalse();
    }

    private static StepExecution onlyStep(JobExecution execution) {
        return execution.getStepExecutions().iterator().next();
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestBatchApp {

        @Bean
        Job importOrdersJob(
                JobRepository repository,
                @Qualifier("prepareInputStep") Step prepareInputStep,
                @Qualifier("validateBusinessDateStep") Step validateStep) {
            return new JobBuilder("importOrdersJob", repository)
                .start(prepareInputStep)
                .next(validateStep)
                .build();
        }

        @Bean
        Step prepareInputStep(JobRepository repository,
                              PlatformTransactionManager txManager) {
            return new StepBuilder("prepareInputStep", repository)
                .tasklet((contribution, chunkContext) -> {
                    contribution.getStepExecution().getJobExecution()
                        .getExecutionContext().putString("preparationDone", "yes");
                    return RepeatStatus.FINISHED;
                }, txManager)
                .build();
        }

        @Bean
        Step validateBusinessDateStep(JobRepository repository,
                                      PlatformTransactionManager txManager,
                                      Tasklet validateBusinessDateTasklet) {
            return new StepBuilder("validateBusinessDateStep", repository)
                .tasklet(validateBusinessDateTasklet, txManager)
                .build();
        }

        @Bean
        Tasklet validateBusinessDateTasklet() {
            return (contribution, chunkContext) -> {
                StepExecution stepExecution = contribution.getStepExecution();
                String date = stepExecution.getJobParameters()
                    .getString("businessDate");

                if (date == null || date.isBlank()) {
                    throw new IllegalArgumentException("businessDate is required");
                }

                stepExecution.getExecutionContext()
                    .putString("validatedBusinessDate", date);
                return RepeatStatus.FINISHED;
            };
        }
    }
}
```

**Explanation of key parts:**

- `@SpringBatchTest` provides `JobLauncherTestUtils`. `@SpringBootTest` initializes Spring Batch beans and infrastructure; `spring.batch.job.enabled=false` prevents Boot from auto-launching jobs when the context is created.
- `spring.batch.jdbc.initialize-schema=always` initializes `BATCH_*` metadata in the test database. For shared databases or separately managed schemas, configure initialization appropriately instead of re-initializing arbitrarily.
- `JobBuilder` and `StepBuilder` take `JobRepository` directly, compatible with Spring Batch 5 configuration style. No `JobBuilderFactory`/`StepBuilderFactory` from older articles is needed.
- Even though `importOrdersJob` declares `prepareInputStep` first, calling `launchStep("validateBusinessDateStep", ...)` creates only one `StepExecution` corresponding to the step under test.
- The `businessDate` parameter passes through `JobParameters`; the business result is written into the **step execution context**. These are two different kinds of data: parameters represent immutable inputs of the job execution, while context holds state that can be updated during execution.
- The failure case asserts both the `FAILED` status and the exception list. An exception thrown inside a tasklet is normally captured by Spring Batch inside `StepExecution`; tests should not assume `launchStep()` will rethrow that exception directly.

The example deliberately gives the two tests different `testCaseId` values so the two runs create separate `JobInstance` records. If you rerun the same job name with the same *identifying JobParameters* on a `JobRepository` that retains metadata, you may encounter `JobInstanceAlreadyCompleteException` instead of re-testing business logic.

## 4. Equivalent in Spring Batch 6.x

Spring Batch 6 switches to `JobOperatorTestUtils`. In the corresponding test, replace the field and invocation from the Spring Batch 5 example with:

```java
import org.springframework.batch.core.repository.ExecutionContext;
import org.springframework.batch.test.JobOperatorTestUtils;

@Autowired
private JobOperatorTestUtils jobOperatorTestUtils;

// Inside the test:
JobExecution result = jobOperatorTestUtils.startStep(
    "validateBusinessDateStep",
    parameters,
    new ExecutionContext()
);
```

In this example, the third `ExecutionContext` argument is the **initial job execution context** for the wrapper job. It is not the `StepExecutionContext`. Spring Batch 6 also reorganizes several core type packages, so you must use imports matching your actual dependency version. For example, `JobExecution` resides in `org.springframework.batch.core.job`, `StepExecution` in `org.springframework.batch.core.step`, and `JobParameters` in `org.springframework.batch.core.job.parameters` in 6.x. Do not mix 5.x imports with 6.x dependencies.

The new method does not change the testing semantics: prepare parameters and context, launch one step, and then inspect `JobExecution`/`StepExecution` to verify. For Spring Batch 6, avoid writing new code based on the deprecated `JobLauncherTestUtils`.

## 5. Testing a Step That Uses `JobParameters` and `ExecutionContext`

A step often depends on data produced by an earlier step:

```text
prepareFileStep
    └── jobExecutionContext["inputPath"] = "/tmp/orders.csv"
              ↓
parseFileStep
    └── reader uses inputPath
```

When running `parseFileStep` alone, `prepareFileStep` does not execute, so the test must supply `inputPath` up front. With Spring Batch 5:

```java
JobParameters params = new JobParametersBuilder()
    .addLong("testCaseId", 100L)
    .toJobParameters();

ExecutionContext initialJobContext = new ExecutionContext();
initialJobContext.putString("inputPath", "src/test/resources/orders.csv");

JobExecution result = jobLauncherTestUtils.launchStep(
    "parseFileStep", params, initialJobContext
);
```

In Spring Batch 6, change the last call to `jobOperatorTestUtils.startStep("parseFileStep", params, initialJobContext)`.

Distinguish three data scopes:

| Data | Lifecycle and Scope | How Passed in Tests |
| --- | --- | --- |
| `JobParameters` | Input parameters for a job run; identifying parameters contribute to `JobInstance` identity | `launchStep(name, params, ...)` or `startStep(name, params, ...)` |
| `JobExecutionContext` | State shared across steps within one job execution | Third `ExecutionContext` parameter when running an individual step |
| `StepExecutionContext` | State private to a single step execution | Created/updated by the step; inspected via `stepExecution.getExecutionContext()`; initialized separately when testing scoped components |

If `parseFileStep` uses `@Value("#{jobExecutionContext['inputPath']}")` in a `@StepScope` bean, the value comes from the job context supplied to the run. If the step needs data stored in the step context from a **restart**, the test must prepare the corresponding metadata/context via a fixture or `JobRepository` rather than confusing job context with step context.

## 6. Testing `@StepScope` Beans Individually

An `ItemReader`, `ItemProcessor`, `ItemWriter`, or service annotated with `@StepScope` is properly instantiated only when a `StepContext` is active. Calling the bean from a plain Java unit test or Spring test without activating the scope can fail because no current step execution exists.

Example component receiving a dynamic value:

```java
@Component
@StepScope
public class InputFileNameProvider {
    private final String fileName;

    public InputFileNameProvider(
            @Value("#{stepExecutionContext['fileName']}") String fileName) {
        this.fileName = fileName;
    }

    public String getFileName() {
        return fileName;
    }
}
```

If the test already has a Spring context containing the `InputFileNameProvider` bean, you can use `StepScopeTestUtils` to simulate a single execution:

```java
@Autowired
InputFileNameProvider inputFileNameProvider;

@Test
void resolvesFileNameFromStepContext() throws Exception {
    StepExecution stepExecution = MetaDataInstanceFactory.createStepExecution();
    stepExecution.getExecutionContext().putString("fileName", "orders.csv");

    String actual = StepScopeTestUtils.doInStepScope(
        stepExecution,
        inputFileNameProvider::getFileName
    );

    assertThat(actual).isEqualTo("orders.csv");
}
```

Related imports in Spring Batch 5 are `org.springframework.batch.test.MetaDataInstanceFactory`, `org.springframework.batch.test.StepScopeTestUtils`, and `org.springframework.batch.core.StepExecution`. `@SpringBatchTest` also enables `StepScopeTestExecutionListener`; when using this listener, the test can provide a `getStepExecution()` method to customize the step context. For a short, explicit operation, `doInStepScope(...)` precisely bounds when the scope is active.

Note that this is **testing a step-scoped component**, not an integration test of the entire `Step`. It catches late-binding configuration errors before running reader/processor/writer together.

## 7. Testing a `chunk-oriented Step`

For a chunk-oriented step, for example:

```text
ItemReader<String>
    → ItemProcessor<String, Order>
    → ItemWriter<Order>
    → commit by chunk size
```

The test should prepare a small input set that still covers distinct cases. For example, mock data of six lines: four valid lines, one line to be filtered, and one line skipped due to a business error configured for `skip`.

After running the step, verify both categories of results:

**`StepExecution` metadata:**

```java
StepExecution stepExecution = jobExecution.getStepExecutions()
    .stream()
    .filter(s -> s.getStepName().equals("importOrdersStep"))
    .findFirst()
    .orElseThrow();

assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(stepExecution.getReadCount()).isEqualTo(6);
assertThat(stepExecution.getFilterCount()).isEqualTo(1);
assertThat(stepExecution.getProcessSkipCount()).isEqualTo(1);
assertThat(stepExecution.getWriteCount()).isEqualTo(4);
```

These numbers **only hold for the described fixture and corresponding processing configuration**: the reader must successfully read six lines; the processor returns `null` for the filtered line; the business error in the processor must fall under the `skip` policy; the writer writes the remaining four items. If an error occurs in the reader or writer, inspect `readSkipCount` or `writeSkipCount` instead of `processSkipCount`.

**Actual side effects:**

```java
List<OrderEntity> rows = orderRepository.findAll();
assertThat(rows).hasSize(4);
assertThat(rows).extracting(OrderEntity::getOrderCode)
    .containsExactlyInAnyOrder("A001", "A002", "A003", "A004");
```

The second snippet illustrates a test using an application repository; `OrderEntity` and `orderRepository` must be replaced with the project's real model and repository. Do not rely solely on `BatchStatus.COMPLETED`: a step can report completion while writing wrong records, wrong order, or duplicate data.

When a step uses `faultTolerant()`, split tests by scenario:

- **Filter:** processor returns `null` to drop an item; inspect `filterCount`, without confusing it with exception-based skipping.
- **Skip:** reader/processor/writer throws an exception covered by the `skip` policy; verify the step continues and the right skip counters increment.
- **Retry:** mocked dependency fails transiently and then succeeds; verify invocation count and final outcome. Do not assume `rollbackCount` must equal a fixed constant if transaction or reader configuration alters rollback behavior.
- **Skip/retry limit exceeded:** step transitions to `FAILED`; check the exception, number of committed items, and uncommitted data from the failed transaction.

In particular, with chunk transactions, a rollback can trigger item reprocessing. Therefore, verify whether the writer or external calls are safe under retries; tests should assert the final data state rather than only how many times a method was invoked.

## 8. Preparing Fixtures and Keeping Tests Independent

A step test typically follows the **Arrange → Act → Assert → Cleanup** sequence:

1. **Arrange:** create a few test records/fixture files, set up `JobParameters`, job context, and initial database state.
2. **Act:** run the exact step name, using `launchStep` in 5.x or `startStep` in 6.x.
3. **Assert:** verify `BatchStatus`, `ExitStatus`, counters, exceptions, `ExecutionContext`, and output data.
4. **Cleanup:** delete test data, close resources, and clean metadata if the test shares a repository with other runs.

Principles that keep tests repeatable and stable:

- **Use small data with predictable outputs.** Files under `src/test/resources`, an isolated test database, or Testcontainers suit real SQL operations. Do not depend on external APIs if the goal is testing step logic.
- **Give each run a clear identity.** Do not repeat identifying `JobParameters` against a repository that already recorded a completed job unless intentionally testing restart. Add a `testCaseId` or clean metadata in the test database.
- **Do not share mutable state across tests.** Stateful reader cursors, buffered writers, static lists, or mocked singletons can make tests order-dependent. Reset input data and dependencies per case.
- **Clean metadata intentionally.** `JobRepositoryTestUtils.removeJobExecutions()` is appropriate only when the repository is test-scoped and safe to wipe; never run it against real application data.
- **Avoid wrapping step tests with `@Transactional`.** Spring Batch manages transactions per step/chunk itself; a test-method transaction can alter data visibility or cause end-of-test rollback to give a false impression of committed data.
- **Test resource lifecycle.** With `ItemStreamReader`/`ItemStreamWriter` when tested directly, call `open(ExecutionContext)`, `update(...)` when needed, and `close()` at the right time. When running a full `Step`, the framework handles this lifecycle.

## 9. Common Errors and Root-Cause Diagnosis

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Step not found by name | Bean/`Step` name differs from passed name, or step is not in the selected job | Check step name in `StepBuilder`, job configuration, and ensure the utility points to the right job |
| `JobLauncherTestUtils`/`JobOperatorTestUtils` not injected | Missing `spring-batch-test`, missing `@SpringBatchTest`, or wrong API version | Add the dependency, annotation, and utility class matching Spring Batch 5/6 |
| `JobInstanceAlreadyCompleteException` | Rerunning same job name and identifying parameters on a repository with existing metadata | Use different parameters or clean the test repository before the run |
| Missing `BATCH_JOB_INSTANCE`, `BATCH_STEP_EXECUTION` tables | Metadata schema not initialized | Initialize schema for the test database; check datasource and batch JDBC settings |
| `ScopeNotActiveException` accessing `@StepScope` bean | No active step context | Run the component inside `StepScopeTestUtils` or use the appropriate test listener |
| Step reports `COMPLETED` but data is wrong | Only status checked, output not verified | Assert database/file/message data and counters on `StepExecution` |
| Isolated step test lacks values created by previous step | Running a step standalone does not run upstream steps | Prepare required fixtures and `JobExecutionContext`/metadata before running |
| Tests flaky when run in parallel | Sharing metadata, output files, or mutable beans | Isolate database/schema/resources per test and avoid shared state |

## 10. When Should You Add Full-Job Tests?

Testing individual steps answers: *"Given prepared data, parameters, and context, does this step execute properly?"* It does not prove that:

- A preceding step actually writes the right value into context for the next step to read.
- Job conditional branches (`COMPLETED`, `FAILED`, `STOPPED`, custom exit codes) transition to the right next step.
- The entire job behaves properly when restarting after some steps have already completed.
- Listeners or logic attached only at the job level behave properly across the full flow.

Therefore, combine unit tests for tricky logic, isolated step integration tests for data cases, and a few full-job integration tests for critical flows. This combination provides fast feedback when a single step changes while still verifying cross-step dependencies.

## References

- [Spring Batch 5.x Reference — Testing Individual Steps](https://docs.spring.io/spring-batch/docs/5.2.x/reference/testing.html): `@SpringBatchTest`, `JobLauncherTestUtils.launchStep`, and step scope testing.
- [Spring Batch 6.x Reference — Unit Testing](https://docs.spring.io/spring-batch/reference/testing.html): `JobOperatorTestUtils`, `@SpringBatchTest`, and current test utilities.
- [Spring Batch 6.x API — JobOperatorTestUtils](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/test/JobOperatorTestUtils.html): `startStep` signature and supplying `JobParameters`/`ExecutionContext`.
