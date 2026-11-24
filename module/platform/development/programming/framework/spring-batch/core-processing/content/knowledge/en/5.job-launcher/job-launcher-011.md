# Testing JobLauncher with a Test Job in Spring Batch

`JobLauncher` is the component that receives a `Job` together with `JobParameters` and asks Spring Batch to execute that job. When testing, we need to confirm that the launcher cooperates correctly with the `JobRepository`, creates the execution, passes the parameters, runs the steps, and returns an appropriate status. A practical way to verify this flow is to create a small **test job**, used only in the test environment, and launch it using the very batch infrastructure that the application configures.

Spring Batch provides `spring-batch-test` and `JobLauncherTestUtils` to support this work. This utility calls the `JobLauncher` that has been configured in the test context, making the test close to how the application runs for real without having to write a scheduler or launch the entire application manually.

## 1. Distinguishing testing JobLauncher from testing step logic

A batch job can be tested at several levels:

| Test level | Goal | Commonly used approach |
| --- | --- | --- |
| Unit test for a processor or service | Verify business logic in isolation. | Call the method directly, no need to launch a job. |
| Testing a single step | Verify the reader, processor, writer, or tasklet within a step. | `JobLauncherTestUtils.launchStep(...)` or a separate step test configuration. |
| Testing a job | Verify the steps and flow are orchestrated correctly. | `JobLauncherTestUtils.launchJob(...)`. |
| Launcher integration testing | Verify that `JobLauncher`, `JobRepository`, the transaction manager, and the job work together in the Spring context. | Launch a test job through `JobLauncherTestUtils` or call `JobLauncher` directly. |

In this lesson, the focus is testing the job launch flow through the launcher. A test job should be small, easy to understand, and have an observable result. When the goal is to verify the flow or the launcher configuration, there is no need to bring all the production business processing into the test job.

## 2. Adding the Spring Batch test library

The testing utilities are in the `spring-batch-test` module. For a Gradle project using Spring Boot dependency management, you can declare:

```groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.batch:spring-batch-test")
    testRuntimeOnly("com.h2database:h2")
}
```

`spring-batch-test` should use a version compatible with the `spring-batch-core` in the application. If the project does not use Spring Boot dependency management, you need to declare the corresponding version instead of letting the Spring Batch modules drift out of version alignment.

H2 is one option for the metadata repository in tests because it can create a dedicated in-memory database. The project can use another test database if it needs to verify SQL behavior, locking, or transaction specifics of the production database.

## 3. JobLauncherTestUtils and @SpringBatchTest

`JobLauncherTestUtils` is a utility in `spring-batch-test`. It provides commonly used methods:

- `launchJob()` launches the job that has been attached to the utility with a set of parameters generated for the test run.
- `launchJob(JobParameters)` launches the job with parameters specified by the test.
- `launchStep(String stepName)` launches an individual step in a temporary test job.
- The overloads of `launchStep(...)` allow passing additional `JobParameters` and `ExecutionContext`.
- `setJob(Job job)` selects the job that the utility will launch. This is a clear way to specify the test job when the context has multiple `Job` beans.

The `@SpringBatchTest` annotation helps register utilities such as `JobLauncherTestUtils` and `JobRepositoryTestUtils`, and also configures the listeners needed for testing Spring Batch scopes such as job scope and step scope. It is combined with the Spring test context, for example `@SpringBootTest` or `@SpringJUnitConfig`.

`JobLauncherTestUtils` uses the `JobLauncher` and `JobRepository` in the application context. Therefore, the test can verify the application's actual configuration without creating a fake launcher itself. With a standalone test context, you need to provide the complete batch infrastructure, datasource, and an appropriate metadata schema.

## 4. Creating a small test job

The following example uses a Spring Boot test context and declares a job just for the test. The job has only one tasklet step. When launched, the step finishes normally so the test can check the `JobExecution` and `StepExecution`.

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@TestConfiguration
class LauncherTestJobConfiguration {

    @Bean
    Step launcherTestStep(JobRepository jobRepository,
                          PlatformTransactionManager transactionManager) {
        return new StepBuilder("launcherTestStep", jobRepository)
            .tasklet((contribution, chunkContext) -> RepeatStatus.FINISHED,
                     transactionManager)
            .build();
    }

    @Bean
    Job launcherTestJob(JobRepository jobRepository,
                        Step launcherTestStep) {
        return new JobBuilder("launcherTestJob", jobRepository)
            .start(launcherTestStep)
            .build();
    }
}
```

This is the declaration using the Spring Batch 5 builder API. With older versions, the way to create `JobBuilder` and `StepBuilder` may differ; use the API that corresponds to the version managed by your project.

The test job is named `launcherTestJob`, and the step is named `launcherTestStep`. Distinct names help avoid confusion with production jobs and make the assertions in the test clear. The tasklet returns `RepeatStatus.FINISHED`, so the step completes after one call.

In an application with multiple `PlatformTransactionManager`s, use `@Qualifier` to specify the transaction manager for the test step. The job and step must use the same batch infrastructure that the test wants to verify.

## 5. Testing a job launch with JobLauncherTestUtils

The test below loads the application context, registers the Spring Batch utilities, and imports the test job configuration. It explicitly selects the job to run with `setJob()` and then launches with a parameter set specific to this test run.

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

@SpringBootTest(properties = "spring.batch.job.enabled=false")
@SpringBatchTest
@Import(LauncherTestJobConfiguration.class)
class JobLauncherIntegrationTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    @Qualifier("launcherTestJob")
    Job launcherTestJob;

    @BeforeEach
    void selectJobUnderTest() {
        jobLauncherTestUtils.setJob(launcherTestJob);
    }

    @Test
    void launchesTestJobAndReturnsExecutionMetadata() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
            .addString("requestId", UUID.randomUUID().toString(), true)
            .addString("source", "launcher-test", false)
            .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(execution.getExitStatus()).isEqualTo(ExitStatus.COMPLETED);
        assertThat(execution.getJobInstance().getJobName())
            .isEqualTo("launcherTestJob");
        assertThat(execution.getStepExecutions()).hasSize(1);

        StepExecution stepExecution = execution.getStepExecutions()
            .iterator()
            .next();

        assertThat(stepExecution.getStepName()).isEqualTo("launcherTestStep");
        assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
    }
}
```

In the example:

1. `@SpringBootTest` loads the application configuration and the batch infrastructure.
2. `spring.batch.job.enabled=false` prevents Spring Boot from automatically launching jobs when creating the application context. The test deliberately decides when the job runs.
3. `@SpringBatchTest` registers the Spring Batch testing utilities.
4. `@Import` adds the test job to the context.
5. `setJob(launcherTestJob)` ensures the utility runs exactly the job under test, even when the application has multiple job beans.
6. `launchJob(parameters)` calls the launcher with the defined parameter set.
7. The test verifies the job status, exit status, job name, and step execution results.

`requestId` is an identifying parameter and is newly generated for each test run. This way, test runs do not accidentally reuse the same `JobInstance`. `source` is a non-identifying parameter to illustrate a parameter that describes the request source but does not take part in determining the instance identity.

If the project does not use Spring Boot, you can replace `@SpringBootTest` and `@Import` with `@SpringJUnitConfig` along with a test configuration that provides the `JobRepository`, `JobLauncher`, datasource, transaction manager, and the test job. The principle remains that the utility must receive the right `Job` and use the batch infrastructure of the test context.

## 6. Why do you need to disable automatic job launching in tests?

Spring Boot can automatically launch jobs when the application starts if batch job auto-launch is enabled. This is convenient when running the application, but in tests it can cause the job to run as soon as the context is created, before the test calls `JobLauncherTestUtils`.

As a result, the test can run into problems such as:

- The job runs twice: once from the automatic mechanism and once from the test.
- A production job is launched unintentionally in the test context.
- Test data is changed before the assertions begin.
- An already-completed job instance causes the next call with the same identifying parameters to be rejected.

With Spring Boot, the property `spring.batch.job.enabled=false` is commonly used to turn off the auto-launch mechanism in tests. If the project configures a launcher or scheduler in its own way, you need to disable the corresponding trigger in the test profile.

## 7. Choosing appropriate JobParameters for each test

`JobParameters` affect the `JobInstance` identity. If two runs use the same job name and the same identifying parameters, they belong to the same instance. When the instance has completed, Spring Batch usually refuses to run it again as a new job.

You can create separate parameters for each test run:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("requestId", UUID.randomUUID().toString(), true)
    .addString("businessDate", "2026-11-15", false)
    .toJobParameters();
```

In this example, `requestId` is identifying; `businessDate` is non-identifying. The marking in the test is only for illustration. In a real application, the identifying parameters must accurately reflect a business unit of work.

If you want to test restart behavior, you should not create a new identifying parameter on the second run. Reuse the same `JobParameters` for the same instance, make the first run end in a restartable state, and then check the next execution according to the job's rules. This is a separate scenario, requiring the test job configuration and data to be set up so that a controlled failure can be reproduced.

The parameterless `launchJob()` can use the unique parameter set generated by the utility for the test. When you need to verify logic based on specific parameters, you should pass `JobParameters` explicitly so the test shows exactly the condition being verified.

## 8. Testing JobLauncher directly

`JobLauncherTestUtils` is convenient when testing a job, but you can inject `JobLauncher` and call it directly if the goal is to confirm that the launcher receives the right job and parameters.

```java
@Autowired
JobLauncher jobLauncher;

@Autowired
@Qualifier("launcherTestJob")
Job launcherTestJob;

@Test
void launchesJobThroughConfiguredLauncher() throws Exception {
    JobParameters parameters = new JobParametersBuilder()
        .addString("requestId", UUID.randomUUID().toString(), true)
        .toJobParameters();

    JobExecution execution = jobLauncher.run(launcherTestJob, parameters);

    assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
    assertThat(execution.getJobInstance().getJobName())
        .isEqualTo("launcherTestJob");
}
```

The direct call shows the contract of `JobLauncher` clearly: it receives a `Job` object and `JobParameters` and returns a `JobExecution`. The test still needs a Spring context and an appropriate repository if you want to confirm real integration. If you only mock `JobLauncher`, the test only verifies how another component calls the launcher; it cannot check transactions or the metadata repository.

In a test suite, you should choose one primary way of launching for each goal. Use `JobLauncherTestUtils` when you need the Spring Batch utilities, and use `JobLauncher` directly when you need to verify the launcher API at a specific integration level.

## 9. Testing a single step with launchStep()

Sometimes the bug is in the reader, processor, writer, or tasklet rather than in the flow of the whole job. `JobLauncherTestUtils.launchStep("stepName")` helps run an individual step without having to execute all the preceding steps.

```java
@Test
void launchesOneStepForFocusedTest() throws Exception {
    JobExecution execution = jobLauncherTestUtils.launchStep("launcherTestStep");

    assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
    assertThat(execution.getStepExecutions()).hasSize(1);

    StepExecution stepExecution = execution.getStepExecutions()
        .iterator()
        .next();

    assertThat(stepExecution.getStepName()).isEqualTo("launcherTestStep");
    assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
}
```

The utility creates a temporary test job to run the specified step. Therefore, `launchStep()` is useful for verifying the behavior of a step within the batch infrastructure, but it does not verify the step order or transitions of the production job. To verify the flow, use `launchJob()` on the job under test itself.

If a step needs parameters or an execution context, use the appropriate overload of `launchStep(...)` to pass the input data. For a step with `@StepScope`, `@SpringBatchTest` helps configure listeners so the scope is activated in the test context.

## 10. Verifying the job execution result

A good launcher test should check many aspects of the `JobExecution`, instead of only confirming that the method does not throw an exception.

| Property | What to confirm |
| --- | --- |
| `getStatus()` | The job ends with the expected `BatchStatus`, such as `COMPLETED` or `FAILED`. |
| `getExitStatus()` | The exit code and description reflect the result the job was designed to produce. |
| `getJobInstance().getJobName()` | It is the job that was requested to launch. |
| `getJobParameters()` | The launcher used the right parameters. |
| `getStepExecutions()` | The expected steps were executed and have the appropriate status. |
| `getStartTime()` / `getEndTime()` | The execution has timestamps consistent with the final status. |

An example of checking parameters:

```java
assertThat(execution.getJobParameters().getString("source"))
    .isEqualTo("launcher-test");
```

For a job with multiple steps, you can check the set of step names that ran:

```java
assertThat(execution.getStepExecutions())
    .extracting(StepExecution::getStepName)
    .contains("validateStep", "importStep", "reportStep");
```

If the flow has branches, check the exact step of the chosen branch and confirm that the steps of the branch not chosen do not appear in the execution. That way the test confirms the orchestration behavior, not just that the job finished successfully.

## 11. Testing a failing job and the error result

A test job can be configured to fail deliberately in order to confirm that the launcher records the error status. For example, a test tasklet can throw an exception:

```java
@Bean
Step failingTestStep(JobRepository jobRepository,
                     PlatformTransactionManager transactionManager) {
    return new StepBuilder("failingTestStep", jobRepository)
        .tasklet((contribution, chunkContext) -> {
            throw new IllegalStateException("Expected test failure");
        }, transactionManager)
        .build();
}
```

When the launcher runs a job containing this step, the framework usually returns a `JobExecution` with the `FAILED` status after recording the error. The test can check:

```java
assertThat(execution.getStatus()).isEqualTo(BatchStatus.FAILED);
assertThat(execution.getAllFailureExceptions()).isNotEmpty();
```

Depending on whether the `JobLauncher` and `TaskExecutor` are configured synchronously or asynchronously, the time of return can differ. With an asynchronous launcher, the test needs to wait for the execution to complete using a time-bounded synchronization mechanism before checking the final status. Do not assume an execution already has a final status as soon as `run()` returns if the application uses an asynchronous executor.

If you check a custom exit status, assert the exact exit code that the listener or flow produces. `BatchStatus.FAILED` and `ExitStatus.FAILED` usually go together when there is an unhandled exception, but the two properties have separate roles and can be customized independently.

## 12. Cleaning up test data and isolating metadata

A test job still writes metadata into the `JobRepository`. If the test uses a shared database, the executions can affect later runs or other tests. You should use a dedicated database for tests, such as in-memory H2 or an independent test schema.

`JobRepositoryTestUtils` provides methods that help delete execution metadata in the test environment, for example `removeJobExecutions()`. You can use this utility to clean up data between tests when the repository is entirely owned by the test suite.

```java
@Autowired
JobRepositoryTestUtils jobRepositoryTestUtils;

@AfterEach
void cleanUpBatchMetadata() {
    jobRepositoryTestUtils.removeJobExecutions();
}
```

Use this cleanup approach only with an isolated test repository. Do not call `removeJobExecutions()` on a production database or a repository shared with other jobs. If tests run in parallel or share a database, deleting metadata can break executions that other tests are using.

Another option is to use unique identifying parameters for each test and clean up only the data belonging to that test using an appropriate mechanism. Remember that deleting metadata does not delete the business data created by the writer; test data in business tables also needs to be isolated or cleaned up separately.

## 13. Testing with multiple jobs in the same application context

A real application usually has multiple `Job` beans. In that case, you should not depend on Spring choosing a single job for `JobLauncherTestUtils` automatically. Inject the job to be tested using `@Qualifier` and call `setJob()` before launching:

```java
@Autowired
JobLauncherTestUtils jobLauncherTestUtils;

@Autowired
@Qualifier("dailyImportJob")
Job dailyImportJob;

@BeforeEach
void configureTargetJob() {
    jobLauncherTestUtils.setJob(dailyImportJob);
}
```

If tests share one utility instance and run in parallel in the same context, changing the target job through `setJob()` can create conflicts. You can split the test context by job, use a dedicated utility, or avoid running in parallel the tests that share the same mutable utility.

A dedicated test job is an appropriate choice when you only need to verify the launcher configuration or a small behavior. When the goal is to confirm that a production job is selected and runs correctly, use that production bean in the test with isolated data and database. Don't let a test job unintentionally replace the integration test of the real job.

## 14. Testing an asynchronous launcher

`JobLauncher` can be configured with a `TaskExecutor` to execute asynchronously. In that case, the launcher call can return the `JobExecution` before the job completes. The test should not assert the final status immediately if the execution is still `STARTING` or `STARTED`.

One approach is to wait, within a time limit, until the status moves to a terminal state, and then assert. An illustrative example:

```java
JobExecution execution = jobLauncher.run(job, parameters);

long deadline = System.nanoTime() + Duration.ofSeconds(10).toNanos();
while (execution.isRunning() && System.nanoTime() < deadline) {
    Thread.sleep(50);
}

assertThat(execution.isRunning()).isFalse();
assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
```

This is a simple illustration of waiting for an asynchronous execution. In a test suite that needs high stability, use a waiting mechanism with a timeout appropriate to the project, and avoid long sleeps or loops without limits. Also note that the in-memory `JobExecution` object may not reflect the latest update depending on how the launcher and repository update it; you can re-read the execution by ID through `JobExplorer` after the job completes.

If you are not testing asynchronous behavior, using a synchronous launcher in the test usually makes the result simpler and easier to reproduce. However, when production uses an asynchronous executor, there should be at least one integration test for that configuration.

## 15. Common errors when testing JobLauncher

**`JobLauncherTestUtils` not found:** check the `spring-batch-test` dependency and the `@SpringBatchTest` annotation. Make sure the test runs in a Spring context rather than instantiating a plain JUnit test class.

**The utility doesn't know which job to run:** the context has multiple `Job` beans or no job is selected. Inject the right bean with `@Qualifier` and call `setJob()` before launching.

**The job runs by itself when the context initializes:** turn off Spring Boot's auto-launch with `spring.batch.job.enabled=false` in the test configuration and check for custom schedulers.

**Duplicate instance or already-completed instance errors:** check the job name and identifying parameters. Create a separate identifying parameter for each test if the goal is a new run; reuse the parameters if you are testing restart.

**Metadata tables not found:** check the test datasource, the schema script, or the schema-initialization configuration appropriate to the Spring Batch version and the database.

**Order-dependent tests:** leftover metadata from a previous test or tests sharing parameters. Use an isolated test database, unique parameters, and an appropriate cleanup procedure.

**A step test passes but the job flow is wrong:** `launchStep()` only verifies the individual step. Use `launchJob()` to confirm the transitions and step order of the actual job.

**Asserting the status too early:** an asynchronous launcher can return before the job finishes. Wait for the execution with a timeout and re-read the status after completion.

## 16. How to organize a useful launcher test suite

A test suite can start with a small test job to confirm the launcher, repository, and transaction manager work. Then, add cases according to the behaviors that need protecting:

1. **Successful launch:** confirm the right job, parameters, step execution, and final status.
2. **Input parameters:** confirm identifying and non-identifying parameters are passed and handled correctly.
3. **Flow branches:** confirm the exit status or decider leads the job to the right step.
4. **Failure:** confirm the error is recorded and the execution status is appropriate.
5. **Restart:** confirm the same job instance can continue after a failure as designed.
6. **Multiple jobs:** confirm the test utility launches the right bean when the context has multiple jobs.
7. **Executor configuration:** if production uses an asynchronous launcher, confirm the test can reliably observe the final status.

Each test should use controllable business data and confirm the result in both the metadata and the target data store when that is within the scope of the test. You should not check only `BatchStatus.COMPLETED` if the job's goal also includes writing the correct number of records or selecting the correct business branch.

Testing the launcher with a test job helps confirm the path from the launch request to the `JobExecution` and `StepExecution` in Spring Batch. When you use `JobLauncherTestUtils`, select the job explicitly, create appropriate `JobParameters`, isolate the metadata repository, and assert both the status and the step results, the test can verify the batch configuration in a repeatable and easy-to-diagnose way.
