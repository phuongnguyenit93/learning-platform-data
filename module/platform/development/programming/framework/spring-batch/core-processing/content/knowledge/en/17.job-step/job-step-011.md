# Testing Parent and Child Jobs

In Spring Batch, one job can launch another job as a step in a flow using `JobStep`. The outer orchestrating job is typically called the **parent job**, while the inner launched job is the **child job**. This structure is useful when a large workflow needs to be split into child jobs with separate responsibilities, reusability, or independent operational lifecycles.

When testing a parent/child model, verify both levels: whether the child job processes accurately when run independently, and whether the parent job passes the right parameters, launches the child, receives the outcome status, and controls flow properly. Checking only that the parent job ends in `COMPLETED` is not enough; observe both the child's `JobExecution` and the `StepExecution` representing `JobStep` in the parent.

Spring Batch Test provides `@SpringBatchTest`, `JobLauncherTestUtils`, and `JobRepositoryTestUtils` to assist testing. `JobExplorer` helps query persisted metadata, including child job executions. Tests should use a repository and transaction manager matching the application configuration to properly verify orchestration and restart behavior.

## Parent Job, Child Job, and JobStep

`JobStep` is a step of the parent job whose role is to launch a child `Job` via `JobLauncher`. It uses `JobParametersExtractor` to construct a `JobParameters` set for the child from information in the parent execution and step execution.

Flow example:

```text
parentJob
    |
    v
validateInputStep
    |
    v
runChildJobStep --------------+
    |                          |
    | JobLauncher              v
    +--------------------> childJob
                              |
                              +--> childExtractStep
                              |
                              +--> childProcessStep
                              |
                              +--> childFinalizeStep
    |
    v
parentSummaryStep
    |
    v
parentJob completes
```

Execution objects at the two levels have distinct roles:

| Object | Belongs to Which Job? | Role |
| --- | --- | --- |
| Parent `JobExecution` | Parent job | Tracks a run of the entire outer workflow |
| Parent `StepExecution` of `JobStep` | Parent job | Tracks the step responsible for launching the child job |
| Child `JobExecution` | Child job | Tracks an actual run of the child job |
| Child `StepExecution` | Child job | Tracks each step inside the child job |

Parent and child normally share `JobRepository` so metadata of both jobs is managed in a single repository system. The child still has its own `JobInstance`, `JobExecution`, parameters, and step executions. Parent `JobStep` does not turn steps inside the child into steps of the parent.

## Configuring JobStep

In Spring Batch 5, `JobStepBuilder` is created from a `StepBuilder` and receives the child job, launcher, and parameter extractor.

```java
@Bean
Step runChildJobStep(
        JobRepository jobRepository,
        JobLauncher jobLauncher,
        @Qualifier("childJob") Job childJob,
        JobParametersExtractor childParametersExtractor) {

    return new JobStepBuilder(
            new StepBuilder("runChildJobStep", jobRepository))
            .job(childJob)
            .launcher(jobLauncher)
            .parametersExtractor(childParametersExtractor)
            .build();
}
```

`JobParametersExtractor` decides which parameters are passed to the child. This is an important contract to test, because changing an identifying parameter can cause the child job to create a different `JobInstance`, fail to restart the same instance, or accidentally collide with an already-completed child execution.

Example of a custom extractor passing business date along with a stable identifier of the parent instance:

```java
@Bean
JobParametersExtractor childParametersExtractor() {
    return (parentJobExecution, parentStepExecution) ->
            new JobParametersBuilder()
                    .addString(
                            "businessDate",
                            parentJobExecution.getJobParameters()
                                    .getString("businessDate"),
                            true)
                    .addString(
                            "parentJobName",
                            parentJobExecution.getJobInstance().getJobName(),
                            true)
                    .addLong(
                            "parentInstanceId",
                            parentJobExecution.getJobInstance().getInstanceId(),
                            true)
                    .toJobParameters();
}
```

In this example, `businessDate`, `parentJobName`, and `parentInstanceId` form a child instance identity tied to one parent logical instance. `parentInstanceId` remains stable when the parent is restarted because a restart creates a new execution for the same `JobInstance`. Depending on business rules, another stable business key can be used. Do not put a timestamp or a new parent execution ID into identifying parameters if the goal is to restart the same child instance.

The specific builder and extractor APIs must be compatible with the Spring Batch version your project uses. With other configurations, you can use `DefaultJobParametersExtractor`; what matters when testing is verifying the exact actual output of the extractor.

## Required Test Structure

Tests should be divided into groups so each test answers a clear question:

| Test Group | What to Verify |
| --- | --- |
| Independent child job | Child steps properly handle inputs, business data, statuses, and errors |
| Parameter extractor | Child receives exact parameter names, values, types, and identifying flags |
| Parent orchestration | Parent `JobStep` actually launches the child and waits for the outcome appropriately |
| Status propagation | Child outcome properly affects parent step status and flow |
| Restart | Child can restart with stable identifying parameters after a failure |
| Isolation/cleanup | Metadata from one test does not affect other tests |

Unit tests fit pure logic such as parameter extractors or mappers. Integration tests with a Spring context and `JobRepository` fit verifying `JobStep`, metadata, transactions, and restarts. Do not merely mock `JobLauncher` across the entire test suite because doing so fails to test actual child execution and how the repository persists state.

## Setting Up Tests with Spring Batch Test

`@SpringBatchTest` registers Spring Batch testing utilities, typically including `JobLauncherTestUtils` and `JobRepositoryTestUtils`, along with test-supporting scopes. It can be combined with `@SpringBootTest` to load application configuration.

Integration test skeleton example:

```java
@SpringBootTest
@SpringBatchTest
class ParentChildJobIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    @Qualifier("parentJob")
    private Job parentJob;

    @Autowired
    private JobExplorer jobExplorer;

    @BeforeEach
    void selectParentJob() {
        jobLauncherTestUtils.setJob(parentJob);
    }
}
```

`JobLauncherTestUtils` needs to know which job is being tested. When the application context has multiple `Job` beans, explicitly specify the parent job before calling `launchJob`. If testing the child independently with the same utility, you can set the child job for that test or use `JobLauncher` directly.

With multiple job beans, avoid relying on Spring autowiring a single `Job` bean automatically. Use `@Qualifier` to inject the exact job, step, and launcher under test.

### Test Database and Metadata

Integration tests should use a test database matching the Spring Batch schema. An embedded database can be used for simple tests if business SQL is compatible; for jobs relying on database-specific syntax, Testcontainers or a test database of the same RDBMS usually reflects production more accurately.

`JobRepositoryTestUtils` helps clean up batch metadata created by tests. Use controlled cleanup after tests complete, especially if tests share a database. Do not delete metadata of jobs currently under test or executions created by other environments.

## Testing the Child Job Independently

Before testing parent orchestration, test the child job like an ordinary job. The goal is to prove the child job can run accurately with the parameter set it requires, independent of any parent invoking it.

Example using `JobLauncher` directly:

```java
@SpringBootTest
@SpringBatchTest
class ChildJobIntegrationTest {

    @Autowired
    private JobLauncher jobLauncher;

    @Autowired
    @Qualifier("childJob")
    private Job childJob;

    @Test
    void childJobCompletesForValidParameters() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2026-11-15", true)
                .addString("parentJobName", "parentJob", true)
                .addLong("parentInstanceId", 1001L, true)
                .toJobParameters();

        JobExecution execution = jobLauncher.run(childJob, parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertEquals("childJob", execution.getJobInstance().getJobName());
        assertEquals(
                "2026-11-15",
                execution.getJobParameters().getString("businessDate"));
    }
}
```

The parent values in the example are illustrative test parameters. In a real parent-child test, the extractor builds them from the parent execution. Independent testing separates bugs inside the child job from parameter-passing or orchestration bugs in the parent.

Cases to test in the child job:

- Required parameters are present and have the right types.
- Invalid parameters cause the child to fail per expected validation.
- Business data is written accurately and not duplicated when re-run under business rules.
- Steps inside the child have expected statuses and exit statuses.
- The child job can restart after a step fails if design permits.
- The child job does not depend on objects or thread context existing only in the parent.

## Testing the Parameter Extractor

The extractor is where the child job's execution identity is determined. Independently test the mapping between parent execution, parent step execution, and child parameters.

Example checking extractor output:

```java
@Test
void extractsStableChildParameters() {
    JobParameters parentParameters = new JobParametersBuilder()
            .addString("businessDate", "2026-11-15", true)
            .addString("requestedBy", "test-user", false)
            .toJobParameters();

    JobInstance parentInstance = new JobInstance(42L, "parentJob");
    JobExecution parentExecution =
            new JobExecution(parentInstance, parentParameters);
    StepExecution parentStepExecution =
            new StepExecution("runChildJobStep", parentExecution);

    JobParametersExtractor extractor = childParametersExtractor();
    JobParameters childParameters =
            extractor.getJobParameters(parentExecution, parentStepExecution);

    assertEquals(
            "2026-11-15",
            childParameters.getString("businessDate"));
    assertEquals("parentJob", childParameters.getString("parentJobName"));
    assertEquals(42L, childParameters.getLong("parentInstanceId"));
}
```

This is a unit test illustrating the extractor defined above. `JobInstance`/`JobExecution` constructors may differ by the library version's API; if full test execution objects are needed, use a test factory or repository instead of constructing objects manually.

In addition to values, check the identifying flag:

```java
JobParameter<?> dateParameter =
        childParameters.getParameters().get("businessDate");

assertTrue(dateParameter.isIdentifying());
```

Checking the identifying flag is critical. If a parameter meant to preserve child instance identity is marked non-identifying or vice versa, launch/restart behavior may differ from expectations even though displayed values look identical.

## Testing the Parent Job Launching the Child Job

This is the core integration test. Launch the parent via `JobLauncherTestUtils`, then verify the parent completes and the child job has a corresponding execution in `JobRepository`.

```java
@Test
void parentLaunchesChildJobAndCompletes() throws Exception {
    JobParameters parentParameters = new JobParametersBuilder()
            .addString("businessDate", "2026-11-15", true)
            .addString("testRunId", UUID.randomUUID().toString(), true)
            .toJobParameters();

    JobExecution parentExecution =
            jobLauncherTestUtils.launchJob(parentParameters);

    assertEquals(BatchStatus.COMPLETED, parentExecution.getStatus());

    StepExecution jobStepExecution = parentExecution.getStepExecutions()
            .stream()
            .filter(step -> step.getStepName().equals("runChildJobStep"))
            .findFirst()
            .orElseThrow();

    assertEquals(BatchStatus.COMPLETED, jobStepExecution.getStatus());
}
```

This test verifies the parent step has completed status. To confirm the child actually ran, query `JobExplorer` and find the child execution by job name together with the identifying parameters created by the extractor.

```java
List<JobExecution> findChildExecutions(
        JobExplorer jobExplorer,
        String businessDate,
        String parentJobName,
        Long parentInstanceId) {

    return jobExplorer.findJobInstancesByName("childJob", 0, 100)
            .stream()
            .flatMap(instance -> jobExplorer.getJobExecutions(instance).stream())
            .filter(execution -> businessDate.equals(
                    execution.getJobParameters().getString("businessDate")))
            .filter(execution -> parentJobName.equals(
                    execution.getJobParameters().getString("parentJobName")))
            .filter(execution -> parentInstanceId.equals(
                    execution.getJobParameters().getLong("parentInstanceId")))
            .toList();
}
```

After the parent runs:

```java
List<JobExecution> childExecutions = findChildExecutions(
        jobExplorer,
        "2026-11-15",
        "parentJob",
        parentExecution.getJobInstance().getInstanceId());

assertEquals(1, childExecutions.size());
assertEquals(BatchStatus.COMPLETED, childExecutions.get(0).getStatus());
```

`findJobInstancesByName` returns instances by child job name; the test further filters executions by parameters to avoid mistaking an execution from another test. In a large suite, limit the query range, use a dedicated test database, or clean up metadata after each test.

## Verifying the Parent Receives Child Status

`JobStep` uses the child execution result to determine the parent step's status. Therefore, verify at least three layers:

1. The child's `JobExecution` has the right status and exit status.
2. The `StepExecution` corresponding to `JobStep` in the parent reflects the child's outcome.
3. The parent's flow proceeds to the next step, failure branch, or end state according to configuration.

Do not assert only `parentExecution.getStatus() == COMPLETED` if the job has custom transitions. A child can end with a custom exit code and the parent can route to another branch while still yielding a valid overall outcome as designed.

If the parent flow uses `on("FAILED").to(recoveryStep)` or a custom `ExitStatus`, tests must verify which steps executed and which steps were skipped. You can inspect the list of `StepExecution`s from the parent execution to verify.

## Testing Child Job Failure

An important scenario is when the child job fails in a step. The parent must receive the failed result from `JobStep` and apply the declared flow.

Example of configuring the parent to route when the child step fails:

```java
@Bean
Job parentJob(
        JobRepository jobRepository,
        Step runChildJobStep,
        Step recoveryStep,
        Step summaryStep) {

    return new JobBuilder("parentJob", jobRepository)
            .start(runChildJobStep)
                .on("FAILED").to(recoveryStep)
            .from(runChildJobStep)
                .on("*").to(summaryStep)
            .from(recoveryStep)
                .on("*").to(summaryStep)
            .end()
            .build();
}
```

The test should set up data causing the child to fail deterministically, such as an invalid parameter or a test double of a business service throwing an exception. Then verify:

- Child `JobExecution` is in `FAILED` status.
- Parent `StepExecution` of `runChildJobStep` has the corresponding failure result.
- Parent transitions to `recoveryStep` if transitions are configured as in the example.
- `summaryStep` runs or does not run per the actual flow.
- Business data committed before the failure is preserved if it was in earlier chunk transactions.

Do not assume all child data automatically rolls back when the child job fails. Previously committed chunks may still persist; tests must verify the actual state of business data.

## Testing Parameters Passed to the Child

Parent and child can have different parameter sets. The parent does not necessarily forward every parameter to the child; the extractor decides precisely which values are passed.

For example, the parent receives:

```text
businessDate = 2026-11-15       identifying
requestedBy  = test-user        non-identifying
testRunId    = 8c...            identifying (for test isolation only)
```

The child may only receive:

```text
businessDate    = 2026-11-15    identifying
parentJobName   = parentJob     identifying
parentInstanceId = 42           identifying
```

Tests should verify:

- Child's required parameters are present.
- Values are mapped accurately from parent or step context.
- Data types are preserved accurately.
- Identifying flags match business semantics.
- Disallowed parameters do not appear in the child.
- Default values or optional parameters are handled explicitly.

Do not check only whether the child ran. The child might run successfully with the wrong parameter set yet process the wrong data scope.

## Testing Child Job Restarts

Restart is a key aspect of parent/child orchestration. When the child job fails, the parent can be restarted so `JobStep` re-launches the child. For the child to resume the same logical instance, the extractor must produce the exact same identifying parameters as the previous run.

Example parameter strategy:

- `businessDate`: identifying and stable.
- `parentJobName`: identifying and stable.
- `parentInstanceId`: identifying, unchanged across restarts of the same parent `JobInstance`.
- `parentExecutionId`: if stored for tracing, should be non-identifying; never use a new execution ID as child identity when wanting to restart the same child instance.

A restart test can follow this sequence:

1. Run the parent with a fixed set of identifying parameters.
2. Let the child complete some steps and then fail on a later step.
3. Verify the first child execution is `FAILED` and metadata/checkpoints were saved.
4. Restart the parent with the same identifying parameters.
5. Verify the extractor generates the same identifying parameters for the child.
6. Verify the child is restarted per `JobRepository` rules, resumes from a valid checkpoint, and completes.
7. Reconcile business data to ensure already-committed chunks were not duplicated.

If on each restart the extractor adds a new identifying timestamp, the child will be treated as a new `JobInstance`. In that case, the child may re-run from the beginning instead of restarting the failed execution.

### Restarting When Child Already Completed but Parent Failed Later

Another scenario: the child is already `COMPLETED`, yet the parent fails in `parentSummaryStep`. When restarting the parent, the restart flow may skip the already-completed `JobStep` and resume from the failed step per parent metadata. If the parent is configured to re-run `JobStep`, a child already completed with the same identifying parameters may be rejected because the `JobInstance` is complete.

Tests must reflect the application's real restart flow. Do not add random parameters to dodge `JobInstanceAlreadyCompleteException`; determine whether the child needs to re-run or the parent simply needs to continue from the step after the child.

## Testing Child Job Independently vs. Through Parent Serve Different Purposes

The two test styles do not replace each other:

| Independent Child Test | Test Through Parent |
| --- | --- |
| Tests child step logic | Tests parent invokes the right child |
| Tests child validators and parameters | Tests extractor maps parameters accurately |
| Tests child business data | Tests parent/child metadata linked by parameters |
| Tests child restart | Tests parent restart triggers child properly |
| Easy to isolate bugs inside child | Catches wiring, flow, and launcher bugs |

A solid integration suite usually has both: small tests for child logic and end-to-end parent-child tests for orchestration.

## Inspecting Metadata with JobExplorer

`JobExplorer` is Spring Batch's metadata-reading API. In tests, it helps find child `JobInstance`s, retrieve `JobExecution` lists, and inspect `StepExecution`s without directly querying `BATCH_*` tables.

Example:

```java
JobInstance childInstance = jobExplorer.findJobInstancesByName(
        "childJob", 0, 10).stream()
        .filter(instance -> jobExplorer.getJobExecutions(instance).stream()
                .anyMatch(execution ->
                        "2026-11-15".equals(execution.getJobParameters()
                                .getString("businessDate"))))
        .findFirst()
        .orElseThrow();

List<JobExecution> executions =
        jobExplorer.getJobExecutions(childInstance);

assertFalse(executions.isEmpty());
```

In real tests, also filter by `parentJobName` and `parentInstanceId` or a stable correlation parameter so you do not pick up an execution from another run.

`JobRepository` can be used to read or update metadata in certain specialized tests, yet `JobExplorer` is more appropriate for observational queries. Do not modify `BATCH_*` tables directly via SQL to force statuses in standard tests.

## Using JobLauncherTestUtils Properly

`JobLauncherTestUtils` provides methods such as `launchJob(...)` and `launchStep(...)`. With parent-child:

- Use `launchJob(parentParameters)` to run the entire parent job.
- Use `launchStep(stepName, parameters)` when isolating a single step of the job attached to the test utility.
- Set the target job via `setJob(...)` if the application context has multiple jobs.
- Use `JobExplorer` to locate the child execution after parent `JobStep` completes.

Do not use `launchStep("runChildJobStep")` to replace testing the parent flow if the goal is verifying transitions across multiple steps. `launchStep` focuses on one step; it does not prove the entire parent flow executes properly.

If you want to run the child directly, use `JobLauncher.run(childJob, childParameters)` or configure a separate test utility for the child. Ensure the child job receives the exact parameters the production extractor would produce.

## Synchronous and Asynchronous Testing

With `JobStep`, a launcher is used to launch the child. In standard integration tests, use `SyncTaskExecutor` or a synchronous launcher so the `JobStep` call receives the child outcome after the child finishes executing. This makes assertions on child status and parent flow deterministic.

If an asynchronous launcher is configured, `JobLauncher.run` may return while the child is still running. In that case, parent `JobStep` may observe an incomplete status unless an appropriate waiting/coordination mechanism exists. Do not simply switch the launcher to async and assume `JobStep` automatically waits for the child to finish.

If the architecture requires running the child asynchronously, design an explicit orchestration mechanism—such as the parent recording the request, the next step polling status via `JobExplorer` with a timeout, or a dedicated orchestration system. Tests must check intermediate states, timeouts, child failures, and that the parent does not mark completion before business conditions are met.

For synchronous tests, still avoid using `Thread.sleep` to wait for jobs. Use a synchronous launcher or an await mechanism with an explicit timeout and observable completion condition.

## Test Isolation and Unique JobParameters

Spring Batch does not allow re-launching an already-completed `JobInstance` as a normal new execution. If multiple tests share the same job name and identifying parameters, a later test may hit `JobInstanceAlreadyCompleteException` or `JobExecutionAlreadyRunningException`.

Ways to isolate tests:

- Use a distinct identifying `testRunId` per test if the goal is creating an independent instance.
- Use different business dates or business keys when that reflects test data scope.
- Use a separate database per test suite or test container.
- Clean batch metadata after tests using `JobRepositoryTestUtils` when appropriate.
- Clean business data and corresponding staging data, not just metadata.

Do not add random parameters into restart tests. In restart tests, keep identifying parameters identical between the initial run and the restart run to properly test the same `JobInstance`.

Example of creating independent parameters for each test:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("testRunId", UUID.randomUUID().toString(), true)
        .toJobParameters();
```

In a restart test, build the parameter set once and reuse that exact set; do not generate a new UUID on the restart run.

## Cleanup with JobRepositoryTestUtils

`JobRepositoryTestUtils` helps clean job executions created during tests. It can be used in `@AfterEach` or `@AfterAll` depending on database scope and suite organization.

```java
@Autowired
private JobRepositoryTestUtils jobRepositoryTestUtils;

@AfterEach
void cleanBatchMetadata() {
    jobRepositoryTestUtils.removeJobExecutions();
}
```

Cleaning metadata does not automatically delete business records, files, object storage, or messages created by the child job. Clean those resources separately, using test identifiers so other tests' data is unaffected.

If tests run in parallel on the same repository, calling global `removeJobExecutions()` can delete metadata another test is actively using. When running in parallel, prefer separate databases/schemas or scoped cleanup covering only executions owned by the test.

## Testing Business Data of Parent and Child

Metadata tells whether a job ran and how it ended, yet does not prove business output is correct. Each test must verify data at the right boundary:

- The child job creates the right records, statuses, or files for the input.
- The parent step after the child receives the right result or reference published by the child.
- Child failure does not cause a parent summary to process unready data.
- Chunks committed before child failure are still reflected accurately.
- Restart neither duplicates nor drops business records.
- If the child emits messages, verify event IDs, payloads, and idempotent consumer/outbox handling.

Do not assert only `BatchStatus.COMPLETED`. A job can complete while a writer writes to the wrong table, receives the wrong business date, or processes the wrong record count. Assert both metadata and business outcomes.

## Testing Flow and ExitStatus

The parent can route based on `JobStep`'s exit code. The child can return `COMPLETED`, `FAILED`, or a custom `ExitStatus` depending on step and listener configuration.

Tests should cover:

| Child Outcome | What to Verify on Parent |
| --- | --- |
| `COMPLETED` | Parent proceeds to the normal next step |
| `FAILED` | Parent stops or goes to recovery flow per configuration |
| Custom exit code | Transition matches the declared pattern |
| Child rejected due to running/completed instance | Parent handles exception or state per operational contract |
| Invalid child parameters | Child does not process business data and parent receives appropriate error |

If using a custom exit code, check both `BatchStatus` and `ExitStatus`. The two values are related but not synonymous; flow transitions normally rely on the exit code.

## Testing When Child Already Ran Previously

A child job may be invoked by multiple parent instances or run independently before the parent calls it. When the child already has metadata, the result of a new launch depends on identifying parameters and existing execution status.

Cases to test:

- Child instance does not exist yet: child is created and runs for the first time.
- Child instance is currently running: duplicate launch request is handled properly.
- Child instance already completed: parent exhibits the designed behavior when calling again with the same parameters.
- Child instance failed: restart with the same identifying parameters is allowed if the job is restartable.
- Child instance is non-restartable: parent receives an error and flow handles it explicitly.

Do not automatically add an identifying timestamp merely to avoid already-completed instance errors. Doing so can create a new child instance and reprocess business data. If business rules require a new run, use a meaningful identifying parameter such as `reprocessVersion` or `runSequence` and verify data impact.

## Testing When Parent and Child Share JobRepository

In a typical configuration, parent and child share one `JobRepository`. This allows querying metadata of both jobs via `JobExplorer` and supports restarts based on execution history.

Integration tests must verify:

- Parent and child are registered in the same repository used by `JobStep`.
- Child execution appears in metadata after the parent runs.
- Child job name and parameters are accurate.
- Child step executions are stored separately.
- Parent step has status reflecting the child outcome.
- Restart reuses existing metadata rather than another test or in-memory repository.

If parent and child accidentally use different repositories, the parent may fail to observe child status as expected and restarts become hard to coordinate. Explicitly inject `JobRepository`/launchers in multi-datasource configurations.

## Testing with Multiple Job Beans and Multiple Test Classes

An application context can contain multiple parent jobs, child jobs, and jobs for other purposes. This easily creates ambiguity when injecting `JobLauncherTestUtils` or `Job`.

Principles:

- Use `@Qualifier` for each `Job` and `Step`.
- Call `jobLauncherTestUtils.setJob(parentJob)` before launching the parent.
- If multiple test classes share the same singleton test utility, avoid changing job selection concurrently.
- For tests running in parallel, use separate utilities or call `JobLauncher` directly with explicitly injected jobs.
- Keep test configuration consistent so no test depends on execution order.

Do not give parent and child the same name. Job names are used in metadata and when querying `JobExplorer`; distinct names make testing, operations, and logging easy to tell apart.

## Diagnosing Failing Tests

### Parent COMPLETED but Child Execution Not Found

Check whether the parent actually contains the `JobStep` under test, whether the step was invoked along the flow, whether the child job bean was injected properly, and whether `JobStep` uses the right `JobLauncher`/`JobRepository`. Check the child job name and how metadata is queried.

### Child Runs but Receives Wrong Parameters

Check `JobParametersExtractor`, key names, data types, and identifying flags. The child may be using a different default extractor than the test assumed.

### Second Test Hits JobInstanceAlreadyCompleteException

Two tests are using the same job name and identifying parameters, or metadata was not cleaned up. Use distinct test parameters for independent tests; keep parameters identical in restart tests.

### Restart Creates a New Child JobInstance

The extractor may be adding a new identifying timestamp, UUID, or parent execution ID each time. Switch to a stable business key or parent instance ID if the goal is restarting the same child instance.

### Parent Step Fails Even Though Child Finished Running

Check whether the launcher runs asynchronously, the status returned when `JobLauncher.run` finishes, exceptions from the child, and how `JobStep` propagates exit status. For standard synchronous orchestration, use a synchronous launcher so the parent receives the completed outcome.

### Test Metadata Leaks Between Tests

Check whether the database/schema is shared, whether tests run in parallel, and whether cleanup deletes the right scope. Create a separate test database or use a stable correlation parameter to filter executions.

### Child FAILED Yet Business Data Still Exists

This can be valid behavior if earlier chunks already committed. Inspect individual `StepExecution`s, checkpoints, and business records instead of assuming the entire child job is a single transaction.

## Minimum Test Matrix

A parent/child integration test suite can start with the following cases:

| Test Case | Expected Result |
| --- | --- |
| Child runs independently with valid parameters | Child `COMPLETED`, accurate output |
| Child receives missing required parameter | Child fails before writing business data |
| Extractor maps parameters from parent | Child receives exact values, types, and identifying flags |
| Parent calls child via `JobStep` | Child `JobExecution` exists, parent `JobStep` completes |
| Child fails | Parent receives status and follows the right recovery flow |
| Restart child after failure | Same identifying parameters, resumes from valid checkpoint |
| Parent restarts after child already completed | Child is not re-run unintentionally |
| Child instance running or already completed | Parent handles duplicate launch per rules |
| Multiple tests run in same suite | No metadata or business data leakage |
| Child has chunks committed before error | Committed data preserved and restart creates no duplicates |

Not every project needs all cases from the outset, yet parameter, status, restart, and test isolation scenarios are essential parts of the parent/child model.

## Test Design Principles

When writing tests for parent and child jobs, clarify:

1. Can the child run independently with a deterministic parameter set?
2. Does parent `JobStep` invoke the right child job?
3. What parameter set and identifying flags does `JobParametersExtractor` produce?
4. Do parent and child use the appropriate repository/launcher?
5. Does child `JobExecution` have the right status, exit status, and step executions?
6. How does the parent flow handle `COMPLETED`, `FAILED`, and custom exit codes?
7. Do restarts preserve child identifying parameters?
8. Are already-committed chunks preserved and is the writer idempotent?
9. Do tests use isolated parameters and clean up metadata/business data within the right scope?
10. Are business outcomes checked in addition to metadata statuses?

For most applications, a reliable approach is testing the child job independently to verify logic, and then running parent integration tests against a real repository to verify `JobStep`, parameter extraction, status propagation, and restarts. Use `JobExplorer` to observe child executions, keep identifying parameters stable for restarts, and isolate test data so runs do not affect each other.

## Key Takeaways

The parent job uses `JobStep` to launch the child job via `JobLauncher` and `JobParametersExtractor`. The child has its own `JobInstance`, `JobExecution`, and step executions; the parent has a `StepExecution` representing the child-launching step. Test the child independently, test the extractor, and then run parent integration tests to confirm the child execution is actually created, receives the right parameters, and returns the appropriate status to the parent flow. Use `JobExplorer` to query metadata, checking business data, failures, and restarts. Child identifying parameters must remain stable across restarts; independent tests need distinct parameters, whereas restart tests must reuse the exact same parameter set. For synchronous `JobStep`, use a synchronous launcher in tests so outcomes are deterministic and ensure the parent proceeds only upon the child's completed status.
