# MetaDataInstanceFactory in Spring Batch Testing

## 1. Problem to Solve

In a batch job, many components do not merely process input data—they also rely on **run metadata**. For example:

- A `StepExecutionListener` checks `readCount` and `writeCount` to decide the step's exit status.
- An `ItemReader` or `ItemWriter` reads run parameters (`JobParameters`) to pick a file, processing date, or operational mode.
- A `@StepScope` component accesses `stepExecutionContext` or `jobParameters` via Spring Expression Language (SpEL).
- Recovery logic reads checkpoints from `ExecutionContext`.

When testing these components in isolation, we normally **do not need to run the entire job**. However, `StepExecution` must be linked to `JobExecution`, and `JobExecution` attaches to `JobInstance` and `JobParameters`. Manually constructing the entire object graph in every test produces verbose setup that obscures the actual behavior under test.

`org.springframework.batch.test.MetaDataInstanceFactory` is a utility class in the `spring-batch-test` module providing **static methods** to build structurally valid metadata for tests:

```text
JobInstance (job name, instance identity)
    └── JobExecution (execution attempt, JobParameters, job ExecutionContext)
            └── StepExecution (step name, counters, step ExecutionContext)
```

Minimal example:

```java
StepExecution stepExecution = MetaDataInstanceFactory.createStepExecution();
stepExecution.setReadCount(0);

// Pass stepExecution into the listener or a function under test.
```

The factory pre-creates the required parent objects. The test only needs to set fields relevant to the scenario under examination.

> **Scope:** `MetaDataInstanceFactory` creates metadata objects **in memory**; it does not run jobs/steps, does not write to `BATCH_*` tables, does not invoke `ItemReader`/`ItemWriter`, does not start transactions, and does not prove that a batch configuration executes successfully. That is the role of integration tests.

## 2. Preparing Dependencies and Distinguishing Versions

With Gradle, declare the test library on the same Spring Batch version line managed by the project:

```groovy
dependencies {
    testImplementation 'org.springframework.batch:spring-batch-test'
    testImplementation 'org.junit.jupiter:junit-jupiter'
}
```

In Spring Boot projects, BOM/dependency management normally controls versions; if not using a BOM, specify compatible versions explicitly. The examples in the following sections use **Spring Batch 5.2.x + JUnit 5**, with key imports:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.test.MetaDataInstanceFactory;
```

**Note for Spring Batch 6.x:** `MetaDataInstanceFactory` still resides in `org.springframework.batch.test`, but several related types moved packages—for example, `JobExecution` belongs to `org.springframework.batch.core.job`, `StepExecution` to `org.springframework.batch.core.step`, `JobParameters`/`JobParametersBuilder` to `org.springframework.batch.core.job.parameters`, and `ExecutionContext` to `org.springframework.batch.infrastructure.item`. When copying examples, use imports matching your actual version.

## 3. Metadata Objects to Understand Before Using the Factory

| Object | Represents | Data Often Needed in Unit Tests |
|---|---|---|
| `JobInstance` | A *logical* run of a job, identified in the system by job name plus identifying parameters | Job name, instance ID |
| `JobExecution` | An execution/run attempt of a job instance; one instance can have multiple executions on reruns | Execution ID, `JobParameters`, status, job-level `ExecutionContext` |
| `StepExecution` | One execution of a step within a `JobExecution` | Step name, ID, `readCount`, `writeCount`, skip/commit count, `ExitStatus`, step-level `ExecutionContext` |
| `JobParameters` | Input values describing a run, such as file name or business date | `inputFile`, `businessDate`, `run.id` |
| `ExecutionContext` | Key-value store holding execution state/checkpoints; scoped at job or step level | Last read position, business flags, values for restart |

Clearly distinguish these two cases:

```java
StepExecution step = MetaDataInstanceFactory.createStepExecution();

// Step context, typically used to store the step's own checkpoint.
step.getExecutionContext().putString("cursor", "record-101");

// Job context, sharing state at the job execution scope.
step.getJobExecution().getExecutionContext()
    .putString("reportPath", "/tmp/report.csv");
```

`JobParameters` is not `ExecutionContext`: input parameters describe the run, whereas context holds state that may be updated during processing. Do not use them interchangeably in tests.

## 4. List of `MetaDataInstanceFactory` Methods

### 4.1. Creating `JobInstance`

| Method | Meaning |
|---|---|
| `createJobInstance()` | Creates an instance with default name and ID. |
| `createJobInstance(String jobName, Long instanceId)` | Creates an instance with a test-specified name and ID. |

### 4.2. Creating `JobExecution`

| Method | Meaning |
|---|---|
| `createJobExecution()` | Creates an execution with default metadata and an associated `JobInstance`. |
| `createJobExecution(Long executionId)` | Specifies the job execution ID; remaining fields use defaults. |
| `createJobExecution(String jobName, Long instanceId, Long executionId)` | Specifies job name, instance ID, and execution ID; job parameters are empty. |
| `createJobExecution(String jobName, Long instanceId, Long executionId, JobParameters jobParameters)` | Adds custom input parameters. |
| `createJobExecutionWithStepExecutions(Long executionId, Collection<String> stepNames)` | Creates a `JobExecution` and attaches `StepExecution` objects with the given names. |

### 4.3. Creating `StepExecution`

| Method | Meaning |
|---|---|
| `createStepExecution()` | Creates a step execution with a default parent metadata graph. |
| `createStepExecution(String stepName, Long executionId)` | Specifies the step name and **the step execution ID**. |
| `createStepExecution(JobExecution jobExecution, String stepName, Long executionId)` | Attaches the step to a pre-constructed job execution. |
| `createStepExecution(JobParameters jobParameters)` | Creates a step and parent objects using the supplied job parameters. |
| `createStepExecution(ExecutionContext executionContext)` | Creates a step with the supplied **step-level** execution context. |
| `createStepExecution(JobParameters jobParameters, ExecutionContext executionContext)` | Creates a step combining both job parameters and step-level context. |

Overloads accepting `Long` use synthetic IDs for testing. They do **not** allocate IDs from `JobRepository`.

### 4.4. Built-in Default Values

Per Spring Batch 5.2.x and 6.x APIs:

| Constant | Value |
|---|---|
| `DEFAULT_JOB_NAME` | `"job"` |
| `DEFAULT_JOB_INSTANCE_ID` | `12L` |
| `DEFAULT_JOB_EXECUTION_ID` | `123L` |
| `DEFAULT_STEP_NAME` | `"step"` |
| `DEFAULT_STEP_EXECUTION_ID` | `1234L` |

You can reference these constants directly when checking default characteristics. However, when business logic depends on job/step names or IDs, pass explicit values so tests are readable and do not accidentally rely on defaults.

## 5. Example 1 — Unit Test for `StepExecutionListener`

Suppose the business requirement is: a step is considered successful only if it read at least one record. The listener inspects `StepExecution` after the step finishes and returns `ExitStatus.FAILED` if there was no data.

```java
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class RejectEmptyInputListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getReadCount() == 0) {
            return ExitStatus.FAILED;
        }
        return ExitStatus.COMPLETED;
    }
}
```

Complete unit test with JUnit Jupiter:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;

class RejectEmptyInputListenerTest {

    private final RejectEmptyInputListener listener =
            new RejectEmptyInputListener();

    @Test
    void failsWhenNoItemsWereRead() {
        StepExecution step = MetaDataInstanceFactory
                .createStepExecution("importOrders", 1001L);
        step.setReadCount(0);

        ExitStatus result = listener.afterStep(step);

        assertEquals(ExitStatus.FAILED, result);
    }

    @Test
    void succeedsWhenAtLeastOneItemWasRead() {
        StepExecution step = MetaDataInstanceFactory
                .createStepExecution("importOrders", 1002L);
        step.setReadCount(15);

        ExitStatus result = listener.afterStep(step);

        assertEquals(ExitStatus.COMPLETED, result);
    }
}
```

Key observations:

1. `createStepExecution(...)` handles the metadata dependency; the test does not need `JobLauncher`, `JobRepository`, or a database.
2. `setReadCount(...)` sets up the input state under test without actually reading 15 records.
3. The name `importOrders` and IDs `1001L`, `1002L` only help describe the scenario; they do not cause a step to execute.
4. Calling `afterStep(...)` is a **direct invocation of the listener method**. The framework does not automatically trigger listener lifecycle callbacks simply because a `StepExecution` was created.

In practice, you can do the same with `getWriteCount()`, `getSkipCount()`, `getCommitCount()`, `getExitStatus()`, or status flags read by application code.

## 6. Example 2 — Testing `JobParameters` and `ExecutionContext`

A processor might use an input file name from `JobParameters` and the latest processing position from `ExecutionContext`. The factory supports building both in a single call:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.test.MetaDataInstanceFactory;

class MetaDataInstanceFactoryParametersTest {

    @Test
    void suppliesJobParametersAndStepCheckpoint() {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "orders-2026-11.csv")
                .addLong("run.id", 42L)
                .toJobParameters();

        ExecutionContext checkpoint = new ExecutionContext();
        checkpoint.putString("lastProcessedKey", "ORD-0150");

        StepExecution step = MetaDataInstanceFactory
                .createStepExecution(parameters, checkpoint);

        assertEquals("orders-2026-11.csv",
                step.getJobParameters().getString("inputFile"));
        assertEquals(42L,
                step.getJobParameters().getLong("run.id"));
        assertEquals("ORD-0150",
                step.getExecutionContext().getString("lastProcessedKey"));
    }
}
```

**Why pass context through the factory?** The created `StepExecution` comes pre-populated with the checkpoint data expected by the component under test. You can also call `createStepExecution(parameters)` and then set `step.getExecutionContext().putString(...)` if that makes the test intent clearer.

When you need **job-level** `ExecutionContext`, assign it on the right parent object:

```java
StepExecution step = MetaDataInstanceFactory.createStepExecution();

step.getJobExecution().getExecutionContext()
    .putString("archiveName", "orders-archive.zip");

// Read the job context properly:
String archive = step.getJobExecution()
    .getExecutionContext().getString("archiveName");
```

If production code accesses `jobExecutionContext['archiveName']`, placing the value in `step.getExecutionContext()` will not set up the right scenario, even if the key name is identical.

## 7. Example 3 — Attaching `StepExecution` to a Specific Job

When a test needs to assert both job identity and step details, you can create `JobExecution` first and then create a step from it:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;

class ExecutionRelationshipTest {

    @Test
    void stepBelongsToSpecifiedJobExecution() {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2026-11-16")
                .toJobParameters();

        JobExecution job = MetaDataInstanceFactory.createJobExecution(
                "dailySettlement", 88L, 890L, parameters);

        StepExecution step = MetaDataInstanceFactory.createStepExecution(
                job, "calculateTotals", 891L);

        assertSame(job, step.getJobExecution());
        assertEquals("dailySettlement", job.getJobInstance().getJobName());
        assertEquals("calculateTotals", step.getStepName());
        assertEquals("2026-11-16",
                step.getJobParameters().getString("businessDate"));
    }
}
```

Here, the three IDs represent three distinct things: `88L` is the **JobInstance ID**, `890L` is the **JobExecution ID**, and `891L` is the **StepExecution ID**. Avoid generic variable names like `id`, because confusing IDs easily makes tests hard to read.

To obtain a job execution containing metadata for multiple steps from the start, use `createJobExecutionWithStepExecutions`:

```java
JobExecution job = MetaDataInstanceFactory.createJobExecutionWithStepExecutions(
        900L, java.util.List.of("extract", "transform", "load"));

java.util.Set<String> names = job.getStepExecutions().stream()
        .map(StepExecution::getStepName)
        .collect(java.util.stream.Collectors.toSet());

assertEquals(java.util.Set.of("extract", "transform", "load"), names);
```

The factory creates `StepExecution` instances linked to the `JobExecution`, each with its own ID. **Do not infer execution order** from element order in the metadata collection: these steps have not run, and the method does not simulate job flow, transitions, or restarts.

## 8. Combining with Testing `@StepScope` Components

### 8.1. Why Must Scope Be Activated?

A `@StepScope` bean is typically lazily initialized and reads values from an active step, such as:

```java
@Bean
@StepScope
public OrderFileReader orderFileReader(
        @Value("#{jobParameters['inputFile']}") String fileName,
        @Value("#{stepExecutionContext['lastProcessedKey']}") String cursor) {
    return new OrderFileReader(fileName, cursor);
}
```

This is an **illustrative configuration example**: `OrderFileReader` is an application-defined class. When Spring creates this bean, it requires an active `StepContext`. Calling `MetaDataInstanceFactory.createStepExecution()` alone does not activate `@StepScope`.

### 8.2. Using `StepScopeTestUtils`

In a Spring test where `orderFileReader` is configured at step scope, you can open a temporary scope around the invocation:

```java
JobParameters params = new JobParametersBuilder()
        .addString("inputFile", "orders.csv")
        .toJobParameters();

ExecutionContext ctx = new ExecutionContext();
ctx.putString("lastProcessedKey", "ORD-0250");

StepExecution step = MetaDataInstanceFactory.createStepExecution(params, ctx);

// orderFileReader is a Spring proxy injected from the ApplicationContext.
String path = StepScopeTestUtils.doInStepScope(step,
        () -> orderFileReader.getInputFileName());

assertEquals("orders.csv", path);
```

To use this snippet, the test needs an `ApplicationContext` with `StepScope` registered, `orderFileReader` as an appropriate proxy bean, and `getInputFileName()` as a method on the application class. `StepScopeTestUtils.doInStepScope(...)` binds `StepExecution` to the thread for the duration of the callback and restores scope state afterward; it **does not run the step**.

### 8.3. Using `StepScopeTestExecutionListener`

For tests running under Spring Test, `StepScopeTestExecutionListener` can automatically look up a method in the test class returning `StepExecution` and use that object as the context for the test method. Since Spring Batch 4.1, `@SpringBatchTest` automatically includes listeners supporting step scope and job scope in the test configuration.

Core example of a test that already has a context and a step-scoped bean:

```java
@SpringBatchTest
@SpringJUnitConfig(OrdersBatchTestConfiguration.class)
class OrderReaderScopeTest {

    @Autowired
    private OrderFileReader orderFileReader;

    // The listener identifies the factory method by its StepExecution return type.
    public StepExecution getStepExecution() {
        JobParameters params = new JobParametersBuilder()
                .addString("inputFile", "input/orders.csv")
                .toJobParameters();
        StepExecution step = MetaDataInstanceFactory.createStepExecution(params);
        step.getExecutionContext().putString("lastProcessedKey", "ORD-0099");
        return step;
    }

    @Test
    void readerReceivesTheCurrentInputFile() {
        assertEquals("input/orders.csv",
                orderFileReader.getInputFileName());
    }
}
```

`OrdersBatchTestConfiguration` and `OrderFileReader` in the example above are application configuration/classes. The key mechanism to remember is: **the listener provides the scope**, while **the factory supplies the input metadata** for that scope. If you omit declaring a `getStepExecution()` method, the listener can use a default step execution; however, the test will lack specialized parameters or context unless you set them explicitly.

## 9. Choosing the Right Testing Tool

| Goal | Suitable Tool | Executes Batch? |
|---|---|---|
| Create metadata for unit tests of listeners or business functions | `MetaDataInstanceFactory` | No |
| Invoke `@StepScope` bean inside a simulated step scope | `MetaDataInstanceFactory` + `StepScopeTestUtils` or `StepScopeTestExecutionListener` | No |
| Run a single step with Spring Batch infrastructure | `JobLauncherTestUtils.launchStep(...)` (Spring Batch 5.x) | Yes |
| Run an entire job and verify data and final status | `JobLauncherTestUtils.launchJob(...)` with test context (Spring Batch 5.x) | Yes |
| Verify metadata persisted in repository and restart behavior | Integration test with `JobRepository`, data source, and real/test config | Yes |

In Spring Batch 6.x, test launch utilities changed, including introducing `JobOperatorTestUtils`; refer to the testing documentation for your exact version. `MetaDataInstanceFactory` retains its role of creating in-memory metadata.

## 10. Common Pitfalls

### Pitfall 1: Assuming the Factory Executed the Step

```java
StepExecution step = MetaDataInstanceFactory.createStepExecution();
assertEquals(10, step.getReadCount()); // Incorrect expectation: no reader has run yet.
```

To test logic when 10 items have been read, **explicitly set** `step.setReadCount(10)`. To verify that a reader actually read 10 items, execute the reader logic or run the step in an appropriate test.

### Pitfall 2: Putting Keys in Job Context Instead of Step Context

```java
step.getExecutionContext().putString("cursor", "C-10");
```

The line above is appropriate only when the tested code reads `stepExecutionContext['cursor']`. If the code reads `jobExecutionContext['cursor']`, set `step.getJobExecution().getExecutionContext()`.

### Pitfall 3: Treating Default IDs as Persistent IDs

IDs `12L`, `123L`, and `1234L` are fixture creation conveniences. Do not use them to infer record existence in `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, or `BATCH_STEP_EXECUTION`. In repository-backed tests, valid IDs must be managed by the repository itself.

### Pitfall 4: Accessing `@StepScope` Beans Without an Active Scope

`MetaDataInstanceFactory` does not register or activate Spring scopes. In tests with `@StepScope` proxy beans, use the listener integrated with Spring Test or `StepScopeTestUtils.doInStepScope(...)`, and ensure the scope is registered in `ApplicationContext`.

### Pitfall 5: Using Mock Metadata to Prove Real Restart

Populating `ExecutionContext` with a checkpoint only tests whether the handler **reads and reacts** to that checkpoint. It does not test persisting/restoring checkpoints across two runs, how Spring Batch determines restartability, or how the repository handles the same job instance. Those behaviors require integration tests.

### Pitfall 6: Mixing Spring Batch 5.x and 6.x Imports

If your IDE reports missing `StepExecution`, `JobExecution`, or `ExecutionContext`, check library versions before changing test logic. Several type packages shifted in 6.x while factory method names remained very similar. Also ensure `spring-batch-test` and the Spring Batch runtime use compatible versions.

## 11. Applying to a Project

When writing tests for a Spring Batch component, you can follow this sequence:

1. **Identify the actual inputs:** does the listener need read count, the processor need a job parameter, the `@StepScope` bean need execution context, or the logic need a step name?
2. **Pick the shortest overload:** `createStepExecution()` for simple tests; overloads accepting `JobParameters`/`ExecutionContext` when those values are needed; overload accepting `JobExecution` when parent–child relationships matter.
3. **Set the right scope:** use getters on step, job execution, or job parameters matching the exact API read by production code.
4. **Invoke the component under test:** listener/business function directly for unit tests; open step scope when testing `@StepScope` beans.
5. **Assert meaningful outcomes:** returned status, read checkpoints, execution path, counters, exceptions, or business values.
6. **Add integration tests** when the goal includes metadata persistence, transactions, restarts, or real flow execution.

### Practice Exercise

Write a listener named `SkipThresholdListener`: if `stepExecution.getSkipCount()` is greater than 5, `afterStep(...)` returns `ExitStatus.FAILED`; otherwise it returns `ExitStatus.COMPLETED`.

- Use `MetaDataInstanceFactory.createStepExecution("validateOrders", 100L)` to build data for the `skipCount = 0` branch.
- Build the boundary case `skipCount = 5` and the threshold-exceeded case `skipCount = 6`.
- Set `setReadSkipCount(...)`, `setProcessSkipCount(...)`, or `setWriteSkipCount(...)` matching how the listener reads skip counts; if the listener reads the total, ensure the fixture reflects that total.
- Try extending it: add a `JobParameters` entry named `maxSkips`, read the value from `stepExecution.getJobParameters()`, and test two different threshold configurations.

This exercise illustrates the exact value of the factory: **placing metadata into a desired test state without having to run a job to produce that state**.

## 12. Official References

- [Spring Batch 5.2.6 — `MetaDataInstanceFactory` Javadoc](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/test/MetaDataInstanceFactory.html): all overloads and default constants.
- [Spring Batch 6.0.5 — `MetaDataInstanceFactory` Javadoc](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/test/MetaDataInstanceFactory.html): 6.x API.
- [Spring Batch 5.2 — Unit Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html): using the factory in tests, step scope testing, and comparisons with running real jobs/steps.
- [Spring Batch 5.2 — `StepScopeTestUtils` Javadoc](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/test/StepScopeTestUtils.html): opening temporary scope for a callback.

