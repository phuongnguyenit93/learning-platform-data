# Creating Deterministic `JobParameters` in Spring Batch Tests

In Spring Batch, `JobParameters` represent the set of parameters passed into each batch job run: business date, data source, tenant code, processing mode, or a business identifier. During testing, these parameters must be prepared **intentionally and reproducibly**. A test that uses `System.currentTimeMillis()`, `UUID.randomUUID()`, or `LocalDate.now()` on every run can accidentally create a new `JobInstance`, making failures hard to reproduce and invalidating restart tests.

The goals of creating deterministic `JobParameters` are:

- The same test input produces the same parameter set across runs and across different machines.
- Each scenario has clear data so a reader looking at the test knows what the job will process.
- Tests that verify the *same* `JobInstance` keep the identifying parameters unchanged.
- Tests that require *different* `JobInstance`s intentionally pick different values rather than relying on chance.
- Test failures reflect batch behavior rather than side effects from time, environment, or leftover metadata in `JobRepository`.

## 1. What do `JobParameters` affect?

In Spring Batch, the logical identity of a processing run can be understood by the formula:

```text
JobInstance = Job name + identifying JobParameters

JobInstance "importOrders", businessDate=2025-01-15, source=orders-v1
  |
  +-- JobExecution #1: FAILED
  |
  +-- JobExecution #2: COMPLETED   (re-run/restart same JobInstance)

JobInstance "importOrders", businessDate=2025-01-16, source=orders-v1
  |
  +-- JobExecution #3: COMPLETED   (different JobInstance)
```

A `JobExecution` is a **single execution attempt**; one `JobInstance` can have multiple `JobExecution`s, for example failing on the first run and succeeding on a restart. If a `JobInstance` has already completed, attempting to run it again through a standard `JobRepository` will be rejected (for example, with `JobInstanceAlreadyCompleteException`).

A `JobParameter` consists of a name, value, type, and an **`identifying`** flag:

| Property | Example | Impact |
| --- | --- | --- |
| Name (*key*) | `businessDate` | Used to look up the parameter by key |
| Value | `2025-01-15` | Data used by the job during processing |
| Type | `String`, `Long`, `LocalDate`, ... | Determines the read/write API and type conversion |
| `identifying=true` | `businessDate=2025-01-15` | Contributes to determining the `JobInstance` |
| `identifying=false` | `traceLabel=smoke-test` | Can be read by the job without changing the `JobInstance` identity |

By default, `JobParametersBuilder` methods such as `addString`, `addLong`, `addDouble`, etc., create an **identifying parameter**. To make a parameter non-identifying, pass `false` to the corresponding overload.

> **Deterministic does not mean using the exact same parameter set for every test.** In unit tests, you can use a fixed parameter set for every run. In integration tests with a stateful `JobRepository`, each independent scenario usually needs its own identity, or the repository needs to be isolated/cleaned between runs. For restart tests, by contrast, you must preserve the identity of the same `JobInstance`.

## 2. Creating a fixed parameter set with `JobParametersBuilder`

The example below uses Spring Batch 5.x, JUnit Jupiter, and explicit fixture data. Values are hardcoded to avoid variation based on the system clock or test machine.

```java
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

final class BatchTestParameters {

    private BatchTestParameters() {
    }

    static JobParameters standard() {
        return forScenario("standard-import");
    }

    static JobParameters forScenario(String scenario) {
        return new JobParametersBuilder()
                .addString("businessDate", "2025-01-15", true)
                .addString("inputName", "orders-small-v1.csv", true)
                .addString("testScenario", scenario, true)
                .addString("traceLabel", "batch-test", false)
                .toJobParameters();
    }
}
```

Rationale behind these choices:

- `businessDate`: a *fixed* business date so results do not depend on the day the test runs.
- `inputName`: a *fixed* fixture name indicating which dataset is processed. If changing the fixture changes the meaning of the run, it should be an identifying parameter.
- `testScenario`: a clear scenario name (`standard-import`, `empty-input`, `invalid-row`) to distinguish `JobInstance`s when these scenarios share a repository.
- `traceLabel`: a label for observability; changing the label should not create a new `JobInstance`, so `identifying=false` is set.

`JobParametersBuilder` is a mutable builder used to add/modify parameters during construction, whereas `JobParameters` is immutable once created. A factory method should instantiate a **new builder on every call**. Do not hold a `static` builder and mutate it across different tests, as that can leak data between tests or cause failures under parallel execution.

This pure parameter creation requires no database, `JobLauncher`, or Spring application context.

## 3. Directly testing determinism and the identifying flag

A test class can verify that two calls for the same scenario always yield the same data, and that different scenarios produce different identifying parameters:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobParameters;

import static org.junit.jupiter.api.Assertions.*;

class BatchTestParametersTest {

    @Test
    void sameScenarioHasSameParameters() {
        JobParameters first = BatchTestParameters.forScenario("standard-import");
        JobParameters second = BatchTestParameters.forScenario("standard-import");

        assertEquals(first, second);
        assertEquals("2025-01-15", first.getString("businessDate"));
        assertEquals("orders-small-v1.csv", first.getString("inputName"));
        assertEquals("standard-import", first.getString("testScenario"));
    }

    @Test
    void scenarioKeyIntentionallyChangesIdentity() {
        JobParameters valid = BatchTestParameters.forScenario("valid-input");
        JobParameters empty = BatchTestParameters.forScenario("empty-input");

        assertNotEquals(
                valid.getIdentifyingParameters(),
                empty.getIdentifyingParameters());
    }

    @Test
    void tracingLabelDoesNotContributeToJobIdentity() {
        JobParameters params = BatchTestParameters.standard();

        assertFalse(params.getParameter("traceLabel").isIdentifying());
        assertTrue(params.getParameter("businessDate").isIdentifying());
        assertFalse(params.getIdentifyingParameters().containsKey("traceLabel"));
    }
}
```

`getIdentifyingParameters()` is available in Spring Batch 5.1+; on earlier versions, check `isIdentifying()` on individual `JobParameter`s or iterate over the map from `getParameters()`. Do not compare the entire `JobParameters` object to conclude whether two parameter sets share the same **job identity**, because the full set also contains `identifying=false` entries.

## 4. Distinguishing deterministic parameters from parameters that create a new identity

Consider the following three parameter sets for the same job named `importOrders`:

| Parameter set | `businessDate` (identifying) | `testScenario` (identifying) | `traceLabel` (non-identifying) | Logical identity |
| --- | --- | --- | --- | --- |
| A | `2025-01-15` | `standard-import` | `run-a` | Instance A |
| B | `2025-01-15` | `standard-import` | `run-b` | **Same instance as A** |
| C | `2025-01-15` | `empty-input` | `run-a` | Different instance from A |

If you want to **test restart**, prepare A and reuse the exact same set of identifying parameters after a failed run. If you want to test **two completely independent scenarios** in the same repository, use A and C. If you only need to attach debug metadata without changing the instance, vary `traceLabel` as in A and B.

However, `testScenario` is a test-convenience parameter and does not necessarily belong to the production business contract of the job. Do not add a new identifying parameter just to bypass `JobInstanceAlreadyCompleteException` in a test that is supposed to verify idempotency or restart behavior. When production fidelity matters, keep the business parameters intact and isolate the test `JobRepository` instead of altering the identity definition.

## 5. Using parameter sets in job/step-scoped bean tests

`@JobScope` or `@StepScope` beans commonly read parameters using Spring Expression Language:

```java
@Bean
@StepScope
FlatFileItemReader<OrderRow> orderReader(
        @Value("#{jobParameters['inputName']}") String inputName) {
    // Select resource by inputName and configure the reader.
    // Specific FlatFileItemReader configuration depends on the fixture file structure.
    return createReaderFor(inputName);
}
```

In tests, values must be placed on the **`JobExecution` bound to the scope**. For minimal infrastructure tests, `spring-batch-test` provides `MetaDataInstanceFactory` to create metadata without running an entire job:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.test.MetaDataInstanceFactory;

import static org.junit.jupiter.api.Assertions.assertEquals;

class JobExecutionParameterFixtureTest {

    @Test
    void jobExecutionCarriesTheFixedFixture() {
        JobParameters params = BatchTestParameters.forScenario("read-orders");

        JobExecution execution = MetaDataInstanceFactory.createJobExecution(
                "importOrders", 11L, 21L, params);

        assertEquals("2025-01-15",
                execution.getJobParameters().getString("businessDate"));
        assertEquals("orders-small-v1.csv",
                execution.getJobParameters().getString("inputName"));
    }
}
```

For tests that actually invoke a scoped bean, you can use `JobScopeTestUtils.doInJobScope(jobExecution, ...)` or create a `StepExecution` and use `StepScopeTestUtils.doInStepScope(stepExecution, ...)`. Both approaches inject the **same fixed parameter set** into `#{jobParameters[...]}` expressions; there is no need to replace them with random data.

Example of creating step metadata for `@StepScope`:

```java
JobParameters params = BatchTestParameters.forScenario("reader-fixture");
StepExecution stepExecution = MetaDataInstanceFactory.createStepExecution(params);

String path = StepScopeTestUtils.doInStepScope(
        stepExecution,
        () -> stepExecution.getJobParameters().getString("inputName"));

assertEquals("orders-small-v1.csv", path);
```

The snippet above requires importing `org.springframework.batch.core.StepExecution` and `org.springframework.batch.test.StepScopeTestUtils` along with the corresponding JUnit static imports. With a real bean, replace the expression returning `path` with a call to the `@StepScope` bean injected from the Spring test context. The invocation on the scoped proxy must happen inside the lambda.

## 6. Using deterministic parameters in job integration tests

When running an actual job via `JobLauncherTestUtils`, pass `JobParameters` explicitly to control the inputs. The following example demonstrates JUnit Jupiter with Spring Batch 5.x in a project with a valid job and repository configuration:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBatchTest
@SpringBootTest
class ImportOrdersJobIT {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void importsFixedInput() throws Exception {
        JobParameters parameters = BatchTestParameters.forScenario("importsFixedInput");

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
    }
}
```

This example assumes the application context has a single suitable job for `JobLauncherTestUtils` to pick up. If multiple `Job`s exist, configure the target job explicitly in the test, for example via `jobLauncherTestUtils.setJob(importOrdersJob)` in `@BeforeEach`. `BatchTestParameters` from section 2 must reside in the same test module to be accessible.

**Note on the repository:** If `importsFixedInput` has already completed in a `JobRepository` persisted from a previous run, executing it again with the same job name and identifying parameters will not start a new run. That is normal Spring Batch behavior, not a flaw in how the parameters were created.

Approaches depending on your goal:

1. **Integration tests independent across CI runs:** use a dedicated test repository, an isolated test database, or clean batch metadata in a controlled manner between scenarios. Fixing parameters and isolating state is the most reproducible approach.
2. **Multiple scenarios on the same repository:** create an identifying `testScenario` with a stable, distinct name per scenario. This separates tests within *one* suite run, though it does not by itself solve re-running the whole suite against an old repository.
3. **Restart testing:** reuse the identifying parameters of the failed instance and preserve repository state; do not increment `run.id`, add timestamps, or generate a new UUID.
4. **Testing business logic only without a repository:** use a `JobParameters` fixture with test-created metadata, and test the appropriate bean or step instead of launching the full job.

The no-argument `launchJob()` overloads on `JobLauncherTestUtils` can auto-generate random parameters to guarantee uniqueness. They are handy in some smoke tests, but whenever a test must reproduce exact inputs or verify job identity, call `launchJob(jobParameters)` with explicit parameters.

## 7. Restart testing requires the **same** identifying parameters

Suppose a job processing data for `2025-01-15` fails midway. When fixing the bug or testing restartability, we want the next run to resume the same work for that date rather than creating a new job instance. Therefore, the parameters that identify the instance must stay intact:

```java
JobParameters original = new JobParametersBuilder()
        .addString("businessDate", "2025-01-15", true)
        .addString("inputName", "orders-small-v1.csv", true)
        .toJobParameters();

// The first run fails and JobRepository persists the FAILED status.
// After the failure condition is resolved, re-run the exact same instance:
JobParameters retry = new JobParametersBuilder(original)
        .toJobParameters();

assertEquals(original.getIdentifyingParameters(),
             retry.getIdentifyingParameters());
```

This is the **data preparation** part of a restart test, not a complete restart test on its own. A full restart test requires a restartable job, a repository holding the failed run, resolution of the failure condition, and assertions on the subsequent execution. If the first run already `COMPLETED`, calling it again with the same parameters will be rejected under instance completion rules; that is not a post-failure restart scenario.

Do not use `RunIdIncrementer` or `.addLong("run.id", System.nanoTime())` just to make a restart test pass: changing an identifying parameter creates a different instance and can mask bugs related to checkpoints/`ExecutionContext`.

## 8. Time, file paths, and dynamic data

Sources of non-determinism often appear in overlooked places:

| Data | Prone to flakiness | Replace with |
| --- | --- | --- |
| Business date | `LocalDate.now()` | `LocalDate.of(2025, 1, 15)` or a fixed date in the fixture |
| Timestamp | `Instant.now()` | `Instant.parse("2025-01-15T00:00:00Z")` or injected `Clock.fixed(...)` |
| Identifier | `UUID.randomUUID()` | Stable, meaningful `caseId` or `testScenario` |
| Run ID | `System.currentTimeMillis()` | Fixed constant/scenario if the test does not need a new instance |
| File path | Absolute path on a developer's machine | Fixture from `src/test/resources`, relative resource name, or `@TempDir` as needed |
| Locale/time zone | Relying on system default formatting | Explicit ISO strings, explicitly specified `ZoneId`/`Locale` |

For code with real-time dependencies, injecting a `Clock` into the parameter builder lets the test control the clock:

```java
import java.time.Clock;
import java.time.LocalDate;

static JobParameters forDay(Clock clock) {
    LocalDate day = LocalDate.now(clock);

    return new JobParametersBuilder()
            .addString("businessDate", day.toString(), true)
            .toJobParameters();
}

// In the test:
Clock fixedClock = Clock.fixed(
        java.time.Instant.parse("2025-01-15T08:30:00Z"),
        java.time.ZoneOffset.UTC);
JobParameters params = forDay(fixedClock);
assertEquals("2025-01-15", params.getString("businessDate"));
```

`Clock.fixed(...)` preserves the "get current date" logic in production code while making test data reproducible. If the test is unrelated to the clock, using a plain date constant in the fixture is simpler.

When using `@TempDir`, the filesystem path can differ on each run. This is normal for file-reading tests, but if you turn the temporary path into an identifying parameter, each run can accidentally become a different `JobInstance`. Consider passing a **logical fixture name** as the parameter and letting the reader resolve the resource, or verify that changing the path genuinely carries business-identity semantics.

## 9. Designing a parameter factory for the entire test suite

A small, pure factory keeps keys, data types, and identifying flags consistent across tests. You can define constants to prevent typos:

```java
final class JobParamKeys {
    static final String BUSINESS_DATE = "businessDate";
    static final String INPUT_NAME = "inputName";
    static final String TEST_SCENARIO = "testScenario";

    private JobParamKeys() {}
}

static JobParameters forTestCase(String scenario, String file) {
    return new JobParametersBuilder()
            .addString(JobParamKeys.BUSINESS_DATE, "2025-01-15", true)
            .addString(JobParamKeys.INPUT_NAME, file, true)
            .addString(JobParamKeys.TEST_SCENARIO, scenario, true)
            .toJobParameters();
}
```

When multiple tests share a factory:

- Call the factory in each test to obtain an independently constructed `JobParameters` instance; do not place a shared `JobParametersBuilder` in a mutable field.
- Name scenarios after specific behaviors, such as `acceptsTwoOrders`, `rejectsMalformedPrice`, `restartsAfterReadFailure`.
- Do not add unrelated parameters to every test; the smaller and more meaningful a fixture is, the easier failures are to diagnose.
- Preserve the exact data type expected by batch code. `addLong("pageSize", 100L)` differs from `addString("pageSize", "100")` if downstream code reads `getLong("pageSize")`.
- When adding a new key, choose `identifying` based on the **business identity of the job**. Do not default every varying key to identifying, nor mark everything non-identifying.

One distinction to keep clear: `JobParameters` are the job's input values; `ExecutionContext` is where Spring Batch/the application stores state produced during processing. Do not use `JobParameters` to simulate a checkpoint already written to `ExecutionContext` in a restart test.

## 10. Common pitfalls

| Symptom | Common cause | Approach |
| --- | --- | --- |
| Test passes locally but flakes on CI | Date, time zone, or test execution order affects parameters | Use fixed values or an injected `Clock`, isolate the repository |
| Re-running throws `JobInstanceAlreadyCompleteException` | Same job name + same identifying parameters already `COMPLETED` | Isolate/prepare the repository for integration tests; only use a different identity when a distinct instance is truly needed |
| Restart test actually runs from the beginning | Adding timestamp/UUID/run ID changes the identity | Keep the identifying parameters of the `FAILED` run unchanged |
| Adding a debug label causes the job to be treated as a new instance | `addString(key, value)` defaults to identifying | Use the `addString(key, value, false)` overload |
| Reader does not receive the date or path | Wrong key, wrong type, or the test's `JobExecution` lacks the expected parameters | Centralize creation through a factory and pass it to the actual execution being used |
| Two tests interfere with each other | Shared mutable builder or repository with stale state | Create a new builder and isolate integration test metadata |
| Test produces unexpected results when the input file changes | Fixed fixture name but file contents were modified | Version fixture data, verify the test loads the intended resource, and update expectations explicitly |

## 11. Version notes and references

The examples use the **Spring Batch 5.x** package:

```java
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
```

In **Spring Batch 6.x**, classes related to job parameters are located in the `org.springframework.batch.core.job.parameters` package. In addition, some test launcher APIs shifted toward `JobOperatorTestUtils`; when using 6.x, check the APIs for your project version. The principles around identifying parameters, deterministic fixtures, and restarts remain unchanged.

Official documentation:

- [Spring Batch Reference — Domain: JobInstance, JobExecution, JobParameters](https://docs.spring.io/spring-batch/reference/domain.html)
- [Spring Batch 5.2 API — JobParametersBuilder](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/JobParametersBuilder.html)
- [Spring Batch 5.2 API — JobParameters](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/JobParameters.html)
- [Spring Batch 5.2 API — MetaDataInstanceFactory](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/test/MetaDataInstanceFactory.html)
- [Spring Batch 5.2 API — JobLauncherTestUtils](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/test/JobLauncherTestUtils.html)
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html)

A good `JobParameters` set for tests must be **readable, reproducible, and accurately represent job identity**. Fix your input data; deliberately choose `identifying` keys; use a simple factory for scenarios; and decide how to isolate `JobRepository` based on whether you are testing independent runs or restarts. As a result, the same test can be executed repeatedly while still proving the exact Spring Batch behavior intended.
