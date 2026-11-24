# JobLauncherTestUtils

## Role of JobLauncherTestUtils

In Spring Batch, a job is typically composed of multiple steps that can read data, process individual items, write results, evaluate conditions, and branch to different paths. When testing, calling a method in a reader, processor, or writer directly only verifies a small part of the processing. It does not prove that Spring Batch can launch the job, create executions, manage transactions, persist metadata, or transition states as expected.

JobLauncherTestUtils is a utility in the spring-batch-test module used to launch a job or a single step in tests. This tool connects to the JobLauncher, JobRepository, and job configured in the Spring ApplicationContext. As a result, tests can verify the behavior of a batch job through Spring Batch's real execution mechanism without manually writing code to invoke each component.

The two main operations are:

- **launchJob(...):** launches the entire job. Used when verifying the end-to-end flow, step ordering, transition conditions, and overall outcome.
- **launchStep(...):** launches a specific step in the test environment. Used when focusing on testing a single step's processing without running the entire job flow.

The returned result is a JobExecution. From this object, the test can inspect the job status, exit status, StepExecutions, read/write/skip counters, and any exceptions recorded during execution.

## Adding the Test Dependency

JobLauncherTestUtils resides in the spring-batch-test artifact, not in spring-batch-core. This dependency only needs to be on the test classpath.

With Maven:

~~~xml
<dependency>
    <groupId>org.springframework.batch</groupId>
    <artifactId>spring-batch-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

With Gradle:

~~~groovy
dependencies {
    testImplementation 'org.springframework.batch:spring-batch-test'
}
~~~

If the project uses Spring Boot dependency management or the Spring Batch BOM, let the BOM manage the version so that spring-batch-test is compatible with the version of spring-batch-core. If the project manages versions manually, declare all Spring Batch artifacts on the same version line.

## Registering the Utility in the Test Context

The standard approach is to combine @SpringBatchTest with @SpringBootTest:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBatchTest
@SpringBootTest
class ImportJobTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void importJobCompletes() throws Exception {
        // Test is implemented in the following sections.
    }
}
~~~

@SpringBootTest loads the application's ApplicationContext, including the job and step configurations, JobRepository, JobLauncher, datasource, and the beans required by the job. @SpringBatchTest adds utilities and test listeners for Spring Batch, including JobLauncherTestUtils, JobRepositoryTestUtils, StepScopeTestExecutionListener, and JobScopeTestExecutionListener.

If not using Spring Boot, Spring's test configuration such as @SpringJUnitConfig can be used, provided the context supplies the required Spring Batch beans and the test utility is registered.

A Spring Boot application may automatically run a job on startup via JobLauncherApplicationRunner. If this automatic execution causes the job to run as soon as the test context is created, disable auto-launching in the test configuration, for example:

~~~java
@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class ImportJobTest {
    // ...
}
~~~

This property applies to Spring Boot Batch configuration; for non-Boot applications, check how job launching is configured in the test context.

## Launching the Entire Job with launchJob

When you want to verify that the job works end to end, call launchJob(). This method launches the job bound to JobLauncherTestUtils and returns a JobExecution.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.beans.factory.annotation.Autowired;

class ImportJobTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void importJobCompletes() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "src/test/resources/orders.csv")
                .addString("testRunId", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution =
                jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertEquals(
                ExitStatus.COMPLETED.getExitCode(),
                execution.getExitStatus().getExitCode());
        assertTrue(execution.getAllFailureExceptions().isEmpty());
    }
}
~~~

In the example, inputFile represents the input parameter required by the job. Parameter names and types must match how the job reads JobParameters. testRunId creates a distinct identifying value for the test run, keeping the test independent so it does not accidentally reuse the same job instance.

If the job does not require mandatory parameters, you can call directly:

~~~java
JobExecution execution = jobLauncherTestUtils.launchJob();
~~~

The no-argument call uses a unique set of JobParameters generated by the utility. This is convenient for an isolated run. When you need to control input data, test restarts, or verify behavior with a specific parameter set, build JobParameters and pass them to launchJob(parameters).

### Reading JobExecution Results

JobExecution describes a single execution attempt of a job. A JobInstance can have multiple JobExecutions if the job is re-run through the restart mechanism. Some commonly checked details include:

| Property | Meaning When Testing |
|---|---|
| getStatus() | Execution status such as COMPLETED, FAILED, STOPPED, or STARTED. |
| getExitStatus() | Exit code and result description set by the job or a listener. |
| getStepExecutions() | The step executions belonging to the job run. |
| getAllFailureExceptions() | Exceptions recorded during execution. |
| getJobParameters() | The set of parameters used to launch the job. |
| getExecutionContext() | Job-level execution context. |

BatchStatus and ExitStatus serve different purposes. BatchStatus represents the lifecycle status of the execution. ExitStatus represents the exit code and can be customized to support flow transitions or business conventions. For a normally completed job, both are typically verified to be COMPLETED.

A job ending with FAILED usually still returns a JobExecution with a failed status; the error is reflected in the execution and the list of failure exceptions. Errors that occur before the job actually runs, such as invalid parameters or an already running job instance, may be thrown from the launch call. Tests should distinguish runtime business errors from setup or launch errors.

## Launching a Single Step with launchStep

When only a single step needs to be tested, use launchStep:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.beans.factory.annotation.Autowired;

class NormalizeStepTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void normalizeStepCompletes() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("testRunId", "normalize-step-test")
                .toJobParameters();

        JobExecution execution =
                jobLauncherTestUtils.launchStep("normalizeStep", parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        StepExecution stepExecution = execution.getStepExecutions()
                .stream()
                .filter(step -> "normalizeStep".equals(step.getStepName()))
                .findFirst()
                .orElseThrow();

        assertEquals(3, stepExecution.getReadCount());
        assertEquals(3, stepExecution.getWriteCount());
    }
}
~~~

The name normalizeStep must match the step name declared in the Spring Batch context. In the example, the test assumes the fixture file has three valid records and the step writes all three; actual counts should be adjusted to match the project's data and processing rules.

launchStep runs the specified step through Spring Batch's test mechanism, creating the execution required for the step to operate. It is useful when a step has a reader, processor, writer, listener, or @StepScope beans that need to be initialized in the proper batch context.

However, testing with launchStep does not prove that the entire job flow works correctly. Preceding or succeeding steps relative to the step under test, transition conditions, decider decisions, and whole-job restart configuration are not verified by this test alone. If the step depends on data written to the ExecutionContext by a previous step, provide an appropriate context according to the API of the version in use or test the entire job with launchJob.

## Choosing launchJob or launchStep

| Testing Need | Appropriate Launch Method | What to Verify |
|---|---|---|
| Verify end-to-end import flow | launchJob(...) | All required steps run in the right order and the job finishes in the right status. |
| Verify reader, processor, and writer of one step | launchStep(...) | Data read, processed, written, and step counters. |
| Verify step transition conditions or deciders | launchJob(...) | Execution branch chosen based on status or data. |
| Verify skip/retry handling in one step | launchStep(...) or launchJob(...) | Skip/retry counters, output data, and final status. |
| Verify restart after a failed run | launchJob(parameters) with same identifying parameters | New execution belongs to the same JobInstance and resumes according to the restart policy. |

Both types of tests can be combined: step tests to isolate data processing bugs, and job tests to verify step integration and control flow.

## JobParameters and JobInstance Uniqueness

Spring Batch identifies a JobInstance based on the job name and parameters marked as identifying. Each attempt to run a job instance creates a JobExecution. Therefore, two job invocations with the same job name and the same identifying parameters may be treated as two runs of the same instance.

JobParametersBuilder creates identifying parameters by default when calling standard parameter-adding methods. You can explicitly mark a parameter as non-identifying using the overload with a boolean flag:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "src/test/resources/orders.csv", true)
        .addString("traceId", "test-trace-01", false)
        .toJobParameters();
~~~

In the example, inputFile participates in identifying the job instance, while traceId is only supplemental information. Decide identifying status based on business data semantics. If changing the input file represents a different batch processing run, the file can be an identifying parameter. If only a trace code changes while the data being processed stays the same, the trace code usually should not alter the job instance identity.

Common scenarios:

- **Independent runs across tests:** add a distinct identifying parameter, such as a UUID, to avoid instance collisions in a shared repository.
- **Testing restart:** pass the exact same identifying parameters for the next run. Changing an identifying parameter causes Spring Batch to create a different JobInstance, and the test will no longer verify restart of the original instance.
- **Re-running a completed job:** the same identifying parameters typically result in JobInstanceAlreadyCompleteException if the job is not allowed to re-run under the current configuration.
- **Concurrent runs:** do not share identifying parameters across two independent runs if the goal of the test is to create two separate job instances.

Do not mechanically add a random parameter to every test. For restart tests or duplicate-run prevention tests, reusing the same parameter set is part of the scenario under test.

## Inspecting StepExecution and Counters

Each step executed within a job has its own StepExecution. You can retrieve the step execution from JobExecution for detailed inspection:

~~~java
StepExecution stepExecution = execution.getStepExecutions()
        .stream()
        .filter(step -> "importStep".equals(step.getStepName()))
        .findFirst()
        .orElseThrow();

assertEquals(BatchStatus.COMPLETED, stepExecution.getStatus());
assertEquals(10, stepExecution.getReadCount());
assertEquals(8, stepExecution.getWriteCount());
assertEquals(2, stepExecution.getFilterCount());
~~~

Common counters:

| Counter | Interpretation |
|---|---|
| readCount | Number of items successfully read. |
| writeCount | Number of items successfully written. |
| filterCount | Number of items filtered by the processor and not passed to the writer. |
| readSkipCount | Number of read errors skipped according to skip configuration. |
| processSkipCount | Number of processing errors skipped. |
| writeSkipCount | Number of write errors skipped. |
| commitCount | Number of chunk commits. |
| rollbackCount | Number of rollbacks recorded. |

Not every job needs to assert all counters. Choose the values that reflect the step's contract. For example, with a file containing 10 records where 2 records are filtered, you can assert readCount equals 10, filterCount equals 2, and writeCount equals 8. If the output data itself is the critical business result, read the file or query the database to confirm the actual contents rather than relying solely on counts.

## Testing Scoped Jobs and Steps

Spring Batch often uses @StepScope or @JobScope for beans that need access to job parameters, step executions, or execution contexts at runtime. These beans cannot always be properly initialized if tests call methods directly outside a batch context.

When running via JobLauncherTestUtils, Spring Batch creates the required execution context for the job or step. @SpringBatchTest also registers StepScopeTestExecutionListener and JobScopeTestExecutionListener, supporting tests that require scope contexts. This enables testing components that depend on @Value("#{jobParameters['inputFile']}") or data in the execution context.

Example of a reader receiving a file path from a job parameter:

~~~java
@Bean
@StepScope
FlatFileItemReader<Order> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {
    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("id", "amount")
            .targetType(Order.class)
            .build();
}
~~~

The job test needs to pass the corresponding inputFile parameter. If the parameter is missing or the key name does not match, the bean may fail to be created or the reader may fail to read the resource. When testing a single step, ensure the step runs within batch scope and provide the parameters/context the step requires.

## Managing Test Data and Metadata

JobRepository stores metadata about job instances, job executions, and step executions. As a result, one test's outcome can affect another test if they share a database and use the same identifying parameters.

Ways to keep tests independent:

1. Use a dedicated test database or an in-memory database when appropriate.
2. Use stable input fixtures and generate separate output paths for each run.
3. Use a distinct identifying parameter for independent runs.
4. Check and clean up batch metadata after tests if the test suite requires a clean repository.

@SpringBatchTest also provides JobRepositoryTestUtils. You can call removeJobExecutions() to delete job executions from the repository in a test environment:

~~~java
import org.junit.jupiter.api.AfterEach;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.beans.factory.annotation.Autowired;

class ImportJobTest {

    @Autowired
    private JobRepositoryTestUtils jobRepositoryTestUtils;

    @AfterEach
    void cleanBatchMetadata() {
        jobRepositoryTestUtils.removeJobExecutions();
    }
}
~~~

This method affects all executions in the repository used by the utility. Only use full metadata cleanup when the repository is isolated for tests or when the test suite clearly controls the data scope. Do not use it on a repository shared with batch data that needs to be preserved.

Additionally, do not assume that @Transactional on a test method will roll back all data written by a job. A chunk-oriented step has its own transactions and commits; the job may finish committing before the test method ends. Manage input/output data and metadata according to the job's actual transaction configuration.

## Synchronous and Asynchronous JobLauncher

With a synchronous JobLauncher, the launch call usually returns only after the job completes, so the test can check the final status immediately after launchJob. If the application configures an asynchronous launcher, the method may return while the job is still running. In that case, the JobExecution may be in STARTING or STARTED status.

In the asynchronous case, the test needs to wait for the execution to reach a terminal state using a bounded synchronization mechanism before asserting COMPLETED or FAILED. Avoid using Thread.sleep with a fixed duration because processing time varies by environment and can make tests flaky.

## Common Errors

### JobLauncherTestUtils Not Found

Verify that the spring-batch-test dependency is on the test classpath, that its version is compatible with Spring Batch core, and that the test context uses @SpringBatchTest or manually registers the utility bean.

### Unable to Determine Which Job to Run

JobLauncherTestUtils must be bound to the job being tested. If the ApplicationContext has multiple Job beans, job selection can become ambiguous. Configure the utility to explicitly point to the target job, such as calling setJob(...) with a bean injected via @Qualifier, or create a dedicated test configuration for that job. Do not assume the utility will automatically pick the right job in a multi-job context.

### Invalid JobParameters

Cross-check key names, data types, and required parameters demanded by the job or validator. In particular, check whether parameters read in @StepScope beans are actually passed when calling launchJob(parameters) or launchStep(...).

### JobInstanceAlreadyCompleteException

The repository already has a completed execution for the job with the same identifying parameters. If this is an independent test run, create a new identifying parameter. If testing restart or duplicate-run prevention, keep the parameters unchanged and assert the expected exception or status.

### Step Not Found or Cannot Run Independently

Check the exact step name and whether the step is registered in the context. If the step requires data produced by a preceding step, an isolated launchStep may not provide a sufficient execution context. In that case, construct an appropriate input context or use launchJob to test the whole flow.

### Test Receives STARTED Status Instead of COMPLETED

Check whether the JobLauncher is configured to run asynchronously. If so, wait for the execution to finish before verifying the final status.

## Complete Example: Testing Job and Step Execution

The example below combines launching the job, checking overall status, and verifying item counts processed in the step:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

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

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class OrdersJobIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void ordersJobReadsAndWritesExpectedItems() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "src/test/resources/orders.csv")
                .addString("testRunId", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution =
                jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertTrue(execution.getAllFailureExceptions().isEmpty());

        StepExecution importStep = execution.getStepExecutions()
                .stream()
                .filter(step -> "importStep".equals(step.getStepName()))
                .findFirst()
                .orElseThrow();

        assertEquals(BatchStatus.COMPLETED, importStep.getStatus());
        assertEquals(10, importStep.getReadCount());
        assertEquals(8, importStep.getWriteCount());
        assertEquals(2, importStep.getFilterCount());
    }
}
~~~

This is an illustrative example assuming a job with a step named importStep that receives inputFile, reads 10 items, filters 2 items, and writes 8 items. When applying it to a project, adjust job/step names, parameters, and expected counts according to the actual configuration and fixtures. Additional assertions on the output data should be included to verify that the contents were written accurately.

JobLauncherTestUtils is well suited for Spring Batch integration testing: it allows tests to launch jobs or steps using the configured batch infrastructure and inspect JobExecution/StepExecution afterward. Combining it with deterministic fixtures, purposefully designed JobParameters, and assertions on business outcomes helps catch bugs in both execution flow and output data.
