# Testing a tasklet with step contribution

In Spring Batch, `Tasklet` is a way to model a step that performs a specific task, such as cleaning up temporary files, calling a stored procedure, generating a report, or processing a group of data in a way controlled by the application. When called, the tasklet receives `StepContribution` and `ChunkContext`, then returns `RepeatStatus` to tell the framework whether the step has finished or needs to keep repeating.

Testing a tasklet needs to verify both the business behavior and the execution information that the tasklet contributes to the step. `StepContribution` is where the tasklet can record read/write counts, filtered or skipped counts, and a custom `ExitStatus`. During an actual run, `TaskletStep` applies the contribution to `StepExecution` and persists metadata per transaction. When calling the tasklet directly in a unit test, applying the contribution does not happen automatically; tests must distinguish between these two layers of objects.

## 1. Tasklet receives StepContribution and ChunkContext

The `Tasklet` interface has the `execute` method:

```java
public interface Tasklet {
    RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception;
}
```

The two parameters have different roles:

- **`StepContribution`** represents the changes that this tasklet execution contributes to `StepExecution`, such as the number of records written or a custom `ExitStatus`.
- **`ChunkContext`** provides the context of the current chunk/tasklet, including `StepContext`, `StepExecution`, job parameters, and attributes stored in the chunk context.

The tasklet returns one of the `RepeatStatus` values:

| Value | Meaning |
|---|---|
| `RepeatStatus.FINISHED` | This tasklet execution is complete; the step can finish if there are no other orchestration conditions |
| `RepeatStatus.CONTINUABLE` | The tasklet needs to be called again; usually used when each call processes one part of the work |

A simple tasklet normally returns `FINISHED`. A tasklet processing in batches can return `CONTINUABLE` until no data remains.

## 2. What is StepContribution?

`StepContribution` is a set of changes arising within one execution unit of a step. It is attached to a `StepExecution` and records the new contribution, instead of directly mutating the step's accumulated counters inside each business statement.

Information that can be recorded includes:

- Number of items read (`readCount`).
- Number of items written (`writeCount`).
- Number of items filtered (`filterCount`).
- Number of items skipped at the read, process, or write phase.
- Number of rollbacks or commits recorded per the API and execution flow.
- `ExitStatus` of the execution portion.

In a data-processing tasklet, you can increment counters when you know the exact number of records processed. For example, if a task successfully writes 12 records, the tasklet can call `contribution.incrementWriteCount(12)`.

Do not artificially increment counters just to make metrics look complete. A tasklet cleaning up a directory or calling a stored procedure does not necessarily have a `readCount` or `writeCount` in the item sense. If the task does not process items, item counters can remain 0 even though the tasklet completed its work.

## 3. How does StepContribution differ from StepExecution?

The two objects are directly related but do not replace each other:

| Object | Role | Scope |
|---|---|---|
| `StepContribution` | Records changes from one call/processing unit | Current contribution |
| `StepExecution` | Stores state and accumulated metrics of a step run | Entire step execution |

When running a tasklet inside `TaskletStep`, the framework creates a contribution, passes it to `execute`, and then applies the changes to `StepExecution` within the step execution lifecycle. Metadata updates are coordinated with the tasklet step's transaction.

In a unit test calling `tasklet.execute(...)` directly, the framework is not in between to apply the contribution. Therefore, after calling the tasklet, you can inspect `contribution.getWriteCount()` directly. If you want to verify the accumulated state as when the framework applies the contribution, the test can explicitly call `stepExecution.apply(contribution)`.

This is an important point when writing tests: if you only inspect `stepExecution.getWriteCount()` after calling the tasklet directly, the result may still be 0 because the contribution has not been applied yet.

## 4. Example of a tasklet recording counts

Suppose a tasklet generates summary records from prepared data. The service returns the number of records actually written successfully.

```java
public class GenerateSummaryTasklet implements Tasklet {

    private final SummaryService summaryService;

    public GenerateSummaryTasklet(SummaryService summaryService) {
        this.summaryService = summaryService;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception {

        int written = summaryService.generate();
        contribution.incrementWriteCount(written);

        if (written == 0) {
            contribution.setExitStatus(new ExitStatus("NO_DATA"));
        }

        return RepeatStatus.FINISHED;
    }
}
```

In the example:

- `SummaryService` performs the business logic and returns the number of records written.
- `incrementWriteCount(written)` records the actual output record count.
- When there is no data, the tasklet sets exit code `NO_DATA` so the flow or reporting can distinguish it from the case with data.
- `FINISHED` indicates the tasklet does not need to be called again.

`ExitStatus` is the result code of a step/job, while `BatchStatus` is the execution lifecycle status. A step can finish executing normally yet carry a custom exit code so the flow transitions to another branch.

## 5. Direct unit testing of a Tasklet

A unit test can call `execute` directly without launching an entire Spring Batch job. To do so, create a `StepExecution`, a `StepContribution` attached to that execution, and a `ChunkContext` containing a `StepContext`.

```java
StepExecution stepExecution = MetaDataInstanceFactory.createStepExecution();
StepContribution contribution = new StepContribution(stepExecution);
ChunkContext chunkContext = new ChunkContext(new StepContext(stepExecution));
```

`MetaDataInstanceFactory` belongs to the `spring-batch-test` module and creates convenient test metadata. This setup gives the tasklet a valid context without starting a real repository.

Example with JUnit 5 and Mockito:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.StepContribution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.batch.core.scope.context.StepContext;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.test.MetaDataInstanceFactory;

class GenerateSummaryTaskletTest {

    @Test
    void recordsWrittenCountAndFinishes() throws Exception {
        SummaryService summaryService = org.mockito.Mockito.mock(SummaryService.class);
        when(summaryService.generate()).thenReturn(3);

        GenerateSummaryTasklet tasklet =
                new GenerateSummaryTasklet(summaryService);

        StepExecution stepExecution = MetaDataInstanceFactory.createStepExecution();
        StepContribution contribution = new StepContribution(stepExecution);
        ChunkContext chunkContext = new ChunkContext(new StepContext(stepExecution));

        RepeatStatus result = tasklet.execute(contribution, chunkContext);

        assertEquals(RepeatStatus.FINISHED, result);
        assertEquals(3, contribution.getWriteCount());
        assertEquals("COMPLETED", contribution.getExitStatus().getExitCode());
        verify(summaryService).generate();
    }
}
```

The test verifies three things: the tasklet finishes, the contribution records three records, and the service is called exactly once. A contribution's default `ExitStatus` is usually `COMPLETED`; when the tasklet sets a custom code, you can check that code instead of the default.

Mockito imports can be shortened with a static `mock(...)` import in the project. The key is that the test does not need to initialize the entire application context if the goal is only to test the `execute` logic.

## 6. Checking StepExecution after applying the contribution

When you want to verify how the contribution is added to the accumulated counters, you can simulate the framework step of applying the contribution:

```java
StepExecution stepExecution = MetaDataInstanceFactory.createStepExecution();
StepContribution contribution = new StepContribution(stepExecution);
ChunkContext chunkContext = new ChunkContext(new StepContext(stepExecution));

tasklet.execute(contribution, chunkContext);

stepExecution.apply(contribution);

assertEquals(3, stepExecution.getWriteCount());
assertEquals("COMPLETED", stepExecution.getExitStatus().getExitCode());
```

`StepExecution.apply(contribution)` adds the counters and applies exit status information from the contribution into the execution. In a direct test, this simulates the integration part handled by the framework. When running a real step via `JobLauncher`, the application does not call `apply` itself inside the tasklet; `TaskletStep` manages this lifecycle.

Do not call `apply` twice for the same contribution in a test, because that would add the numbers twice and not reflect normal execution.

## 7. Testing the no-data branch and custom ExitStatus

If a tasklet has different business branches, test each branch. For example, when there is no data, return `FINISHED` and set exit code `NO_DATA`.

```java
@Test
void returnsNoDataExitStatusWhenNothingWasWritten() throws Exception {
    SummaryService summaryService = mock(SummaryService.class);
    when(summaryService.generate()).thenReturn(0);

    GenerateSummaryTasklet tasklet = new GenerateSummaryTasklet(summaryService);
    StepExecution stepExecution = MetaDataInstanceFactory.createStepExecution();
    StepContribution contribution = new StepContribution(stepExecution);
    ChunkContext chunkContext = new ChunkContext(new StepContext(stepExecution));

    RepeatStatus result = tasklet.execute(contribution, chunkContext);

    assertEquals(RepeatStatus.FINISHED, result);
    assertEquals(0, contribution.getWriteCount());
    assertEquals("NO_DATA", contribution.getExitStatus().getExitCode());
}
```

If the step uses the exit code to route the flow, an integration test should check both the step exit status and that the correct next step runs. Checking only `RepeatStatus.FINISHED` is not enough to prove the flow handles the business outcome correctly.

## 8. Testing errors and exceptions

A tasklet can throw an exception when a service fails. A unit test should verify that the exception propagates out and does not record a false success count.

```java
@Test
void propagatesServiceFailure() throws Exception {
    SummaryService summaryService = mock(SummaryService.class);
    when(summaryService.generate()).thenThrow(new IOException("Output unavailable"));

    GenerateSummaryTasklet tasklet = new GenerateSummaryTasklet(summaryService);
    StepExecution stepExecution = MetaDataInstanceFactory.createStepExecution();
    StepContribution contribution = new StepContribution(stepExecution);
    ChunkContext chunkContext = new ChunkContext(new StepContext(stepExecution));

    assertThrows(IOException.class,
            () -> tasklet.execute(contribution, chunkContext));

    assertEquals(0, contribution.getWriteCount());
    verify(summaryService).generate();
}
```

This test verifies that the tasklet does not swallow the exception and does not increment `writeCount` when the service did not report a successful write. If the service could write partially before throwing an error, this unit test does not prove the data was rolled back; an integration test with a real transaction manager and resource is needed.

Do not catch every exception inside the tasklet and return `FINISHED`. If the tasklet hides errors, the framework may mark the step successful even though the business work was not completed.

## 9. Testing RepeatStatus.CONTINUABLE

A tasklet can process data in batches. Each call processes one portion and returns `CONTINUABLE`; when no data remains, it returns `FINISHED`.

Example logic:

```java
public class ProcessPagesTasklet implements Tasklet {

    private final PageService pageService;

    public ProcessPagesTasklet(PageService pageService) {
        this.pageService = pageService;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        int written = pageService.processNextPage();
        contribution.incrementWriteCount(written);

        return pageService.hasMorePages()
                ? RepeatStatus.CONTINUABLE
                : RepeatStatus.FINISHED;
    }
}
```

For a repeating tasklet, test that:

- Calls with data return `CONTINUABLE` while work remains.
- The final call returns `FINISHED`.
- Each call processes only a well-defined portion of work.
- Contribution counts are recorded for the right processed portion.
- If a call fails, the transaction and state allow resuming without duplicate or missed processing.

In `TaskletStep`, the framework manages calls and transactions in a loop. In a direct unit test, you can invoke the tasklet multiple times with corresponding contributions to test each pass's logic; to verify actual repeat and transaction behavior, run an integration test with the configured step.

A repeating tasklet needs a clear termination condition. If `hasMorePages()` always returns true due to a state bug, the step can run indefinitely. You can add an iteration limit, timeout, or appropriate operational stop condition.

## 10. Testing a tasklet that uses StepScope or JobParameters

A tasklet can be declared with `@StepScope` to receive job parameters or the step execution context at runtime. In that case, a unit test calling the constructor directly may not exercise Spring's late binding mechanism.

Spring Batch Test provides `StepScopeTestUtils` to run a block of code within step scope with a mock `StepExecution`:

```java
StepExecution stepExecution = MetaDataInstanceFactory.createStepExecution(
        new JobParametersBuilder()
                .addString("outputFile", "target/test-output.csv", true)
                .toJobParameters());

StepScopeTestUtils.doInStepScope(stepExecution, () -> {
    // Obtain the @StepScope bean and test the logic within the step context.
    assertNotNull(tasklet);
    return null;
});
```

In the example, `tasklet` represents the step-scoped bean injected from the test context. `StepScopeTestUtils` activates the scope during the callback, allowing expressions referencing `jobParameters` or `stepExecutionContext` to resolve.

If you need to verify that Spring creates the bean and injects parameters properly, use a test context with a real batch configuration. If you only test business logic, passing values into the constructor or mocking collaborators makes tests simpler.

## 11. Integration testing with JobLauncherTestUtils

A unit test calling `execute` directly does not test the full behavior of `TaskletStep`, transaction manager, `JobRepository`, metadata persistence, or flow transitions. For those requirements, run the step through `JobLauncherTestUtils`.

`@SpringBatchTest` helps register Spring Batch test utilities such as `JobLauncherTestUtils`, `JobRepositoryTestUtils`, and listeners for step/job scope. General example with JUnit 5:

```java
@SpringBatchTest
@SpringJUnitConfig(BatchTestConfiguration.class)
class ArchiveStepIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobRepositoryTestUtils jobRepositoryTestUtils;

    @AfterEach
    void cleanMetadata() {
        jobRepositoryTestUtils.removeJobExecutions();
    }

    @Test
    void launchesArchiveStepAndRecordsContribution() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2026-11-15", true)
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchStep(
                "archiveStep", parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        StepExecution stepExecution = execution.getStepExecutions()
                .stream()
                .filter(step -> "archiveStep".equals(step.getStepName()))
                .findFirst()
                .orElseThrow();

        assertEquals(3, stepExecution.getWriteCount());
    }
}
```

This is an illustrative skeleton; `BatchTestConfiguration` must provide the job, step, repository, datasource, transaction manager, and required collaborators. `launchStep` runs the chosen step through the Spring Batch infrastructure, so the test can check status and contributions after the framework completes.

If tests run repeatedly, manage metadata and identifying parameters to avoid `JobInstanceAlreadyCompleteException`. You can clean execution metadata with `JobRepositoryTestUtils` in the test environment or use distinct identifying parameters per test run. Do not use this metadata cleanup on a production repository.

## 12. Testing rollback with a real database in tests

A unit test mocking a service to throw an exception only proves the tasklet reacts to errors. It does not prove the transaction rolled back data. To verify rollback, you need an integration test using a test database and the step's actual transaction manager.

Example scenario:

1. The tasklet uses `JdbcTemplate` to insert a row into a test table.
2. After the insert, the tasklet intentionally throws an exception.
3. `TaskletStep` catches the exception and the transaction rolls back.
4. The test queries the database after the job finishes and confirms the inserted row does not exist.

Illustrative tasklet:

```java
public class InsertThenFailTasklet implements Tasklet {

    private final JdbcTemplate jdbcTemplate;

    public InsertThenFailTasklet(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        jdbcTemplate.update(
                "insert into batch_test_record(id, name) values (?, ?)",
                1L, "temporary");

        contribution.incrementWriteCount(1);
        throw new IllegalStateException("Force rollback for test");
    }
}
```

In the integration test, launch the step and verify `BatchStatus.FAILED` and that querying `select count(*) from batch_test_record where id = 1` returns 0. The test must ensure `JdbcTemplate` uses the same `DataSource` and transaction manager that the step uses. If the tasklet opens its own connection or writes through a system outside the transaction, the rollback assertion may fail.

Another note: incrementing `writeCount` in the contribution before the exception occurs does not mean the data committed. When the transaction fails, that execution's contribution is not applied like a successful chunk. Verify both final metadata and actual data, rather than inferring from local variables before the exception.

## 13. Testing ExitStatus and flow transitions

A tasklet can set a custom `ExitStatus` so the job moves to another step based on business outcomes.

For example, `archiveStep` can return `NO_DATA` when there are no files to archive. The job can configure a flow:

```java
return new JobBuilder("archiveJob", jobRepository)
        .start(archiveStep)
            .on("NO_DATA").to(noDataNotificationStep)
        .from(archiveStep)
            .on("COMPLETED").to(reportStep)
        .from(archiveStep)
            .on("FAILED").fail()
        .end()
        .build();
```

A specific flow may need default transitions or other statuses depending on configuration. The point is that the step's exit code can decide the next branch.

When testing, verify that:

- The tasklet sets the right exit code for each case.
- The step finishes with the appropriate `BatchStatus`.
- The flow selects the right next step.
- The job has the final `BatchStatus` and `ExitStatus` matching the expected result.

Do not confuse `RepeatStatus.FINISHED` with `ExitStatus.COMPLETED`. `RepeatStatus` controls repeating the tasklet call; `ExitStatus` represents the step outcome used by the flow and operations systems.

## 14. Testing errors when a tasklet is called multiple times

If a tasklet returns `CONTINUABLE`, it can run multiple times within the same step execution. An error can occur on the second or third call after earlier calls have completed their transactions.

For example, a tasklet processing page by page:

| Call | Business outcome | RepeatStatus | Transaction |
|---|---|---|---|
| 1 | Write page 1 | `CONTINUABLE` | Commit if successful |
| 2 | Write page 2 | `CONTINUABLE` | Commit if successful |
| 3 | Error writing page 3 | Exception | Roll back call 3 transaction |
| Restart | Continue per saved state | Depends on outcome | Earlier committed calls are preserved |

Tests need to verify where the tasklet's state is stored. If a tasklet keeps `currentPage` in a field of a singleton bean, the state may not be restored properly after restart or could be shared across different executions. You can use `ExecutionContext`, an appropriate reader/stream, or a durably stored business checkpoint key.

A repeating tasklet should process each unit of work idempotently. If a call rolls back and runs again, the same page must not create duplicate records or corrupt totals.

## 15. What not to do in tasklet tests

- **Checking only that a mock was called:** that does not prove the contribution, exit status, or transaction is correct.
- **Calling the tasklet directly and expecting StepExecution to change automatically:** unit tests must inspect the contribution or call `apply` if simulating integration.
- **Mocking the transaction manager when trying to test database rollback:** a mock does not prove the database undid the write operation.
- **Incrementing writeCount for every task:** only record counts when they clearly correspond to items actually written.
- **Catching exceptions inside the tasklet and returning FINISHED:** can cause the step to report success while the work failed.
- **Wrapping the test with `@Transactional` without understanding job transactions:** the test transaction and the transaction opened by `TaskletStep` can differ; query results may not reflect the job's commit/rollback.
- **Reusing identifying parameters of a completed execution:** tests may hit an instance-already-complete error; manage metadata or test parameters appropriately.
- **Checking only `RepeatStatus`:** also check `BatchStatus`, `ExitStatus`, contribution, and target data when those are part of the requirements.

## 16. Splitting unit tests and integration tests

Not every tasklet test needs to boot the entire Spring Batch context. You can choose the test level according to the question you need to answer:

| Goal | Suitable testing approach |
|---|---|
| Tasklet calls the service properly and returns `FINISHED` | Unit test calling `execute` directly with mocks |
| Tasklet increments contribution by the right amount | Unit test checking `StepContribution` |
| Tasklet sets a custom exit code | Unit test checking `contribution.getExitStatus()` |
| Tasklet returns `CONTINUABLE` then finishes | Unit test individual calls; integration test if verifying the step loop |
| `@StepScope` receives the right job parameter | Test with Spring context and `StepScopeTestUtils` or `@SpringBatchTest` |
| `TaskletStep` persists StepExecution and metadata | Integration test via `JobLauncherTestUtils` |
| Database rolls back when tasklet throws an exception | Integration test with a real database and transaction manager |
| Flow chooses the right branch by ExitStatus | Integration test launching the job and inspecting step executions |

This split keeps unit tests fast and focused on tasklet logic, while integration tests focus on framework wiring, transactions, repositories, and flows that unit tests cannot fully simulate.

## 17. Principles to remember

- `Tasklet.execute` receives `StepContribution` and `ChunkContext`, and returns `RepeatStatus`.
- `FINISHED` ends tasklet repetition; `CONTINUABLE` asks the framework to call again.
- `StepContribution` records the changes of one execution pass; `StepExecution` holds the step's accumulated metrics.
- When calling a tasklet directly in a unit test, check the contribution; the framework does not automatically apply the contribution to `StepExecution` in that direct call.
- You can call `StepExecution.apply(contribution)` in a test to simulate applying the contribution, but never call it twice for the same contribution.
- Only increment read/write/filter/skip counts when the numbers accurately reflect the work the tasklet performed.
- Use `MetaDataInstanceFactory` to create test metadata and appropriate `ChunkContext`/`StepContext`.
- Use unit tests to check outcomes, contributions, exit status, and exceptions; use integration tests to check transactions, rollbacks, repositories, and flows.
- For `@StepScope` tasklets, test late binding with Spring Batch Test utilities or an appropriate context test.
- For repeating tasklets, test `CONTINUABLE`, termination conditions, state, and safe re-runnability.

Testing a tasklet with step contribution helps confirm not only that the business task runs properly, but also the metrics and outcomes the tasklet reports to Spring Batch. Combining direct unit tests with integration tests via `TaskletStep` helps distinguish tasklet logic bugs from transaction, metadata, or flow orchestration errors.
