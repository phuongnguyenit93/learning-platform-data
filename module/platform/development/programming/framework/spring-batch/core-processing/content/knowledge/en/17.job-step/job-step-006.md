# Restarting a Child Job

In Spring Batch, a Job can invoke another Job as a Step through `JobStep`. The Job invoked inside is typically viewed as the **child job**, while the Job containing `JobStep` is the **parent job**. This structure helps split a large workflow into Jobs with separate responsibilities that can be tracked and operated independently.

When a child job fails, it can be restarted under its own `JobInstance` and `JobParameters`. The parent job also has its own execution state and history. Therefore, you must distinguish between restarting the child job directly and restarting the parent job containing `JobStep`. The two operations are related but not synonymous: restarting the parent can cause `JobStep` to launch the child again, whereas restarting the child directly does not automatically transition the parent Step to completed.

## 1. JobStep and the Parent-Child Relationship

`JobStep` is a type of Step responsible for launching another Job using `JobLauncher`. The Parent Job treats running the child job as a step in its flow.

For example, an order processing workflow can be split into:

- `dailyOrderJob`: parent job orchestrating the entire workflow.
- `validateOrderJob`: child job validating input data.
- `processOrderJob`: child job processing orders.
- `publishSummaryStep`: Step of the parent generating the summary report.

The flow can be illustrated as follows:

```text
Parent Job: dailyOrderJob
       |
       v
JobStep: validateOrderJobStep
       |
       +----> Child Job: validateOrderJob
       |             |
       |             +--> Child JobExecution
       |             +--> Child StepExecutions
       |
       v
JobStep: processOrderJobStep
       |
       +----> Child Job: processOrderJob
       |             |
       |             +--> Child JobExecution
       |             +--> Child StepExecutions
       |
       v
Parent Step: publishSummaryStep
       |
       v
Parent Job ends
```

Parent and child have separate execution objects:

| Object | Scope |
|---|---|
| Parent `JobInstance` | One logical unit of work of the parent job. |
| Parent `JobExecution` | One specific run of the parent job. |
| Parent `StepExecution` for `JobStep` | One execution where the parent performs the step of calling the child job. |
| Child `JobInstance` | One logical unit of work of the child job, identified by the child job name and identifying parameters. |
| Child `JobExecution` | One execution attempt of the child job. |
| Child `StepExecution` | Step executions inside the child job. |

A child job is not merely a Java method invoked inside the parent. It has its own `JobInstance`, `JobExecution`, `StepExecution`s, and metadata in `JobRepository`.

## 2. Why Distinguish Parent Restart from Child Restart?

Suppose the parent job runs a `JobStep` to invoke `customerImportJob`. The child job begins processing data but fails in its second Step:

```text
Parent JobExecution #100
  |
  +--> Parent StepExecution: customerImportJobStep = FAILED
          |
          +--> Child JobInstance: customerImportJob / businessDate=2026-11-15
                  |
                  +--> Child JobExecution #201 = FAILED
                          validateStep = COMPLETED
                          importStep   = FAILED
```

When restarting the parent with the same identifying parameters, the parent creates a new `JobExecution` for the same Parent `JobInstance`. `JobStep` is executed again and invokes the child job with the extracted parameters. If the previous child `JobInstance` is in a restartable state such as `FAILED` or `STOPPED`, Spring Batch can create a new Child `JobExecution` for the same Child `JobInstance`.

```text
Parent JobInstance: dailyOrderJob / businessDate=2026-11-15
  |
  +--> Parent JobExecution #100 = FAILED
  |       customerImportJobStep = FAILED
  |
  +--> Parent JobExecution #105 = COMPLETED
          customerImportJobStep = COMPLETED
             |
             +--> Child JobInstance: customerImportJob / businessDate=2026-11-15
                     |
                     +--> Child JobExecution #201 = FAILED
                     +--> Child JobExecution #208 = COMPLETED
```

Restarting the parent is usually the natural approach when you want to resume the entire orchestration workflow from the failed `JobStep`. If you only restart the child directly, the parent `JobExecution` and Parent `StepExecution` retain their old statuses. The parent does not automatically know the child was handled manually until a synchronization mechanism runs or the parent is re-run appropriately.

## 3. Which JobParameters Identify the Child Job?

When `JobStep` invokes a child job, it needs to construct `JobParameters` for the child. `JobParametersExtractor` is responsible for extracting parameters from the parent's `StepExecution`.

The child's identifying parameters determine the Child `JobInstance`. Thus, parameter selection directly affects restarts:

- Same child job name and same identifying parameters: same Child `JobInstance`.
- Different identifying parameters: new Child `JobInstance`.
- Changing non-identifying parameters: still the same Child `JobInstance`.

For example, if the child job processes data by date and source file:

```text
Child Job: customerImportJob
  businessDate=2026-11-15  (identifying)
  inputFile=customers.csv  (identifying)
  parentExecutionId=100    (non-identifying)
```

`businessDate` and `inputFile` define the child's unit of work. `parentExecutionId` only traces which parent requested the child run. When the parent restarts, the parent gets a new `JobExecution` ID; if `parentExecutionId` were an identifying parameter of the child, every parent restart would create a new Child `JobInstance` and potentially reprocess data from the start. Therefore, tracing info should normally be a non-identifying parameter.

## 4. Extracting JobParameters for the Child with JobParametersExtractor

Spring Batch provides the `JobParametersExtractor` interface and the `DefaultJobParametersExtractor` implementation. You can use the default extractor when keys to transfer from `ExecutionContext` are already fixed. For specific business rules, implement a custom extractor to precisely control identifying and non-identifying parameters.

Custom extractor example:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.step.job.JobParametersExtractor;

public class CustomerImportParametersExtractor
        implements JobParametersExtractor {

    @Override
    public JobParameters getJobParameters(Job job, StepExecution stepExecution) {
        JobParameters parentParameters =
                stepExecution.getJobExecution().getJobParameters();

        String businessDate = parentParameters.getString("businessDate");
        String inputFile = stepExecution.getExecutionContext()
                .getString("inputFile");

        if (businessDate == null || inputFile == null) {
            throw new IllegalStateException(
                    "businessDate and inputFile are required for child job");
        }

        return new JobParametersBuilder()
                .addString("businessDate", businessDate, true)
                .addString("inputFile", inputFile, true)
                .addLong("parentExecutionId",
                        stepExecution.getJobExecution().getId(), false)
                .toJobParameters();
    }
}
```

The extractor above takes the business date from the parent's `JobParameters` and the file path from Step `ExecutionContext`. Both values are marked identifying for the child. The parent run ID is added for traceability without participating in the Child `JobInstance` identity.

If the `inputFile` value is produced in an earlier Step, that Step must store the key in `ExecutionContext` before `JobStep` runs. You can use `StepExecution` directly or `ExecutionContextPromotionListener` if the data needs to be promoted to Job `ExecutionContext`.

## 5. Declaring JobStep in Java

In Spring Batch 5 and later, you can configure `JobStep` from `StepBuilder`, specifying the child Job, `JobLauncher`, extractor, and transaction manager:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.step.job.JobParametersExtractor;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class ParentJobConfig {

    @Bean
    public Step customerImportJobStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            JobLauncher jobLauncher,
            Job customerImportJob,
            JobParametersExtractor customerImportParametersExtractor) {

        return new StepBuilder("customerImportJobStep", jobRepository)
                .job(customerImportJob)
                .launcher(jobLauncher)
                .parametersExtractor(customerImportParametersExtractor)
                .transactionManager(transactionManager)
                .build();
    }

    @Bean
    public Job dailyOrderJob(
            JobRepository jobRepository,
            Step customerImportJobStep,
            Step publishSummaryStep) {

        return new JobBuilder("dailyOrderJob", jobRepository)
                .start(customerImportJobStep)
                .next(publishSummaryStep)
                .build();
    }
}
```

`customerImportJob` is a child job declared in its own configuration. `customerImportJobStep` is the parent's Step responsible for launching the child. `JobParametersExtractor` builds the parameter set for the child from the parent `StepExecution` state.

In a real application, ensure the child `Job` is registered in the same application context or provided via an appropriate configuration mechanism. Parent and child typically share `JobRepository` so metadata of both Jobs is managed and queried uniformly.

## 6. What Happens When the Child Job is FAILED?

When the child job fails, `JobStep` receives the failure outcome from the child and the parent Step normally ends as `FAILED`. The parent Job accordingly ends as `FAILED` if the flow has no dedicated transition to handle failure results.

```text
Parent Job
   |
   v
JobStep: runChildJob
   |
   v
Child JobExecution
   |
   +--> validateStep = COMPLETED
   +--> importStep   = FAILED
   |
   v
Child JobExecution = FAILED
   |
   v
Parent JobStep = FAILED
   |
   v
Parent JobExecution = FAILED
```

If the child `JobInstance` is restartable, re-running the parent `JobInstance` with the same identifying parameters causes `JobStep` to be retried. When the extractor regenerates the exact identifying `JobParameters` for the child, `JobLauncher` recognizes the old Child `JobInstance` and can create a new Child `JobExecution` to restart.

An essential requirement is that the extractor must return a stable set of identifying parameters. If every parent restart adds a new UUID or timestamp to the child's identifying parameters, Spring Batch will create a new Child `JobInstance` instead of restarting the failed instance.

## 7. What Happens When the Child Job is Already COMPLETED?

An already-completed Child `JobInstance` cannot be launched again as a new piece of work with the same identifying parameters. If `JobStep` executes again and invokes the child using the exact identifying parameters of a `COMPLETED` instance, Spring Batch normally throws `JobInstanceAlreadyCompleteException`.

You may encounter this scenario:

```text
Child JobInstance: customerImportJob / businessDate=2026-11-15
  |
  +--> Child JobExecution #201 = COMPLETED

Parent restart
  |
  +--> JobStep re-runs
          |
          +--> launches child with same identifying parameters
                    |
                    +--> JobInstanceAlreadyCompleteException
```

This situation commonly occurs when the parent `JobStep` needs to re-run while the child already completed on the previous run—for example, the parent stopped or errored at the boundary after the child committed its result but before the parent Step was recorded as completed. It can also happen if configuration permits the parent `JobStep` to re-run after it has already completed.

Do not solve this by automatically adding a new identifying parameter for the child. That could cause the child to re-run all data and create duplicate side effects. First, determine whether the child already completed the work properly and how the parent Step status was stored.

Appropriate ways to handle this:

1. Design the child job to be idempotent, with business keys so a new run does not create duplicate data.
2. Use status or an audit record so the parent recognizes the child already completed the exact unit of work and proceeds according to explicit rules.
3. If a new processing run is genuinely needed, create a new Child `JobInstance` using a semantically meaningful identifying parameter, such as `reprocessVersion` or `correctionBatchId`.
4. Enable `allowStartIfComplete(true)` for `JobStep` only when re-launching the child has been designed and controlled safely.

## 8. Restarting the Child Directly

You may need to restart the child job independently to fix a data error or recover a single run without re-running the entire parent. In that case, use the exact Child `JobInstance` and identifying `JobParameters` of the previous run.

General procedure:

1. Look up the failed Child `JobExecution` using `JobExplorer` or `JobRepository`.
2. Identify the Child `JobInstance` and identifying `JobParameters`.
3. Fix the root cause of the failure, such as input file, data, or dependent configuration.
4. Restart the child via the appropriate orchestration API, such as `JobOperator.restart(executionId)` or launching the child with the same `Job` and same identifying parameters.
5. Monitor the new Child `JobExecution` until it reaches a final state.
6. Synchronize the outcome with the parent according to the application's operational procedure.

Illustrative example of restarting via `JobOperator`:

```java
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.stereotype.Service;

@Service
public class ChildJobRestartService {

    private final JobOperator jobOperator;

    public ChildJobRestartService(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public Long restartChild(Long failedExecutionId) throws Exception {
        return jobOperator.restart(failedExecutionId);
    }
}
```

`failedExecutionId` must be the ID of the Child `JobExecution` to restart, not the Parent `JobExecution` ID. Restarting the child directly does not automatically mark the Parent `StepExecution` as `COMPLETED`. If the parent remains in a failed state, an orchestration step is needed to confirm the child completed and allow the parent to proceed without launching the child redundantly.

## 9. Restarting the Parent So JobStep Re-invokes the Child

When you want the entire parent flow to continue as designed, you normally restart the parent `JobInstance`. Spring Batch creates a new Parent `JobExecution`; already-completed Steps are normally skipped per restart policy, while the failed `JobStep` is executed again.

```text
Parent JobInstance: dailyOrderJob / businessDate=2026-11-15
  |
  +--> Parent JobExecution #100 = FAILED
  |       validateStep = COMPLETED
  |       customerImportJobStep = FAILED
  |
  +--> Parent JobExecution #105
          validateStep = skipped (already completed)
          customerImportJobStep = re-run
             |
             +--> Child JobInstance with same identifying parameters
                      New Child JobExecution
```

If the child previously failed, the new invocation can restart the child. If the child already completed, the invocation may be rejected as explained in the previous section. Therefore, restarting the parent requires inspecting the Child `JobExecution` history as well, not just the parent status.

Parent and child may have different restart policies. The parent may allow restart while the child is configured with `preventRestart()`, or vice versa. Check the policies of both Jobs and their related Steps.

## 10. Notes on JobParameters and RunIdIncrementer

A common mistake is using `RunIdIncrementer` on the child job and assuming every parent restart will resume the right child instance. An incrementer creates a new identifying parameter for the next run; therefore it can create a new Child `JobInstance`.

For example, if the child receives:

```text
businessDate=2026-11-15
run.id=1
```

and on restart the extractor or launcher produces:

```text
businessDate=2026-11-15
run.id=2
```

then this is a new Child `JobInstance`, not a restart of the old Child `JobInstance`. This can be useful when business logic intentionally creates a new processing run, but it is unsuitable when the goal is to resume a failed run.

Define clearly:

- Which parameters identify the child's unit of work?
- Which parameters are only for tracing/logging?
- Must a parent restart preserve the child identifying parameters?
- When reprocessing already-completed data, which version code or correction code represents that request?

A good convention is to use stable business keys as identifying parameters, while parent execution ID and requester info are non-identifying parameters.

## 11. Transactions and JobRepository in JobStep

`JobStep` has its own transaction for executing the parent Step, while the child job executes the transactions of the Steps inside it. Do not open a single transaction wrapping the parent and the entire child job.

Example:

```text
Parent JobStep transaction
       |
       +--> launches child Job
                |
                +--> Child Step 1 chunk transactions
                +--> Child Step 2 chunk transactions
                +--> Child Tasklet transactions
```

The child's data transactions are managed by the transaction manager configured for the child Steps. Even if parent and child share a database, transaction boundaries should still be kept at the scope of each Step/chunk. The child job may have already committed data before the parent `JobStep` finishes.

This explains why you can encounter cases where the child is already `COMPLETED` while parent `JobStep` has not yet recorded completion. A transaction rollback on the parent does not automatically undo every already-committed transaction inside the child. Restart design must rely on metadata at both levels and ensure business operations are idempotent.

## 12. Monitoring Parent and Child Executions

When investigating failures, query the right level:

| What to Look For | Information to Inspect |
|---|---|
| Parent `JobInstance` | Parent Job name and identifying parent `JobParameters`. |
| Parent `JobExecution` | Parent run, final status, and error. |
| Parent `StepExecution` | Which `JobStep` failed, `ExitStatus`, and execution timestamps. |
| Child `JobInstance` | Child Job name and identifying child `JobParameters`. |
| Child `JobExecution` | Which child run failed/completed, and how many restarts occurred. |
| Child `StepExecution` | Step inside the child that caused the error, read/write counts, and checkpoint. |

`JobExplorer` can be used to look up `JobInstance`s and `JobExecution`s by Job name, parameters, or ID. When `JobStep` stores the child execution ID or result in `ExecutionContext`/audit, tracing the parent-child relationship becomes easier. Do not rely on parent and child IDs being similar; these are two independent executions.

A helpful operational practice is to log the following when `JobStep` invokes a child:

- Parent `JobExecution` ID.
- Parent `StepExecution` ID and `JobStep` name.
- Child Job name.
- Child `JobParameters`, especially identifying parameters.
- Child `JobExecution` ID returned from `JobLauncher` if available.
- Child `BatchStatus` and `ExitStatus`.

Do not log secrets or tokens in `JobParameters` logs. Log only the values needed for traceability.

## 13. Testing Parent and Child Restarts

Unit tests for `JobParametersExtractor` should verify that the child parameter set is created accurately and keeps identifying parameters unchanged when the parent restarts.

Example:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.mockito.Mockito.mock;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;

class CustomerImportParametersExtractorTest {

    @Test
    void keepsChildIdentityStableAcrossParentExecutions() {
        JobParameters parentParameters = new JobParametersBuilder()
                .addString("businessDate", "2026-11-15", true)
                .toJobParameters();
        JobExecution parentExecution = new JobExecution(
                new JobInstance(1L, "dailyOrderJob"),
                100L,
                parentParameters);
        StepExecution parentStepExecution =
                new StepExecution("customerImportJobStep", parentExecution);
        parentStepExecution.getExecutionContext()
                .putString("inputFile", "customers.csv");

        Job childJob = mock(Job.class); // Extractor does not need to read Job metadata.
        JobParameters childParameters =
                new CustomerImportParametersExtractor()
                        .getJobParameters(childJob, parentStepExecution);

        assertEquals("2026-11-15", childParameters.getString("businessDate"));
        assertEquals("customers.csv", childParameters.getString("inputFile"));
        assertFalse(childParameters.getParameters()
                .get("parentExecutionId").isIdentifying());
    }
}
```

The test above illustrates how to check the identifying flag. In real tests, you can create two Parent `JobExecution`s with different IDs but the same identifying `JobParameters`, invoke the extractor for each `StepExecution`, and assert that the child's identifying parameters are equal while `parentExecutionId` differs and remains non-identifying.

Integration tests should run parent `JobStep` together with the child `Job` against a test `JobRepository`:

1. Run the parent the first time, configuring the child to fail in a Step.
2. Verify both parent `JobExecution` and child `JobExecution` fail according to the flow.
3. Fix the error condition and restart the parent with the same identifying parent `JobParameters`.
4. Verify the child has a new `JobExecution` while keeping the same Child `JobInstance`.
5. Verify the child completes and the parent proceeds to the Step after `JobStep`.
6. Also create a case where the child is already `COMPLETED` yet parent `JobStep` must re-run to verify how the application handles `JobInstanceAlreadyCompleteException`.

Tests should use fixed data and verify business data after restart, not just check `COMPLETED` status. If the child writes data to a database, verify there are no duplicate records or incorrect updates when the Step re-runs.

## 14. Common Mistakes

| Mistake | Cause | How to Fix |
|---|---|---|
| Restarting parent creates a new child `JobInstance` | Extractor adds a new identifying parameter on each parent run. | Keep child identifying parameters stable across restarts. |
| Child is already `COMPLETED` but `JobStep` re-launch is rejected | The same child `JobInstance` cannot be launched again after completion. | Inspect child execution and parent status; handle completed child per explicit policy. |
| Restarting child directly leaves parent `FAILED` | Child and parent have separate execution metadata. | Synchronize status and coordinate parent continuation as designed. |
| Using `parentExecutionId` as an identifying parameter of the child | Parent restart gets a new execution ID and thus creates a new child instance. | Make `parentExecutionId` non-identifying for traceability. |
| Using `RunIdIncrementer` for every child invocation | Each call can create a new Child `JobInstance` and reprocess data. | Use an incrementer only when a new processing unit is intentionally needed. |
| Assuming parent rollback rolls back the child | Child Steps have separate transactions and may already have committed. | Check child status and design idempotent operations. |
| Looking only at Parent `JobExecution` when investigating | Cannot tell how far the child ran or whether it completed. | Query both Parent `StepExecution` and Child `JobExecution`/`StepExecution`. |
| Not checking child restart policy | The child may be configured to disallow restarts. | Check `preventRestart`, execution status, and restartability of each Step. |

## Conclusion

`JobStep` lets a parent Job invoke a child Job as a Step, yet parent and child have separate `JobInstance`, `JobExecution`, and `StepExecution`s. When the child fails, restarting the parent with the same identifying parameters normally causes `JobStep` to call the child again; if the child also uses the same identifying parameters, Spring Batch can restart the right Child `JobInstance`. If the child is already `COMPLETED`, launching the same instance again is rejected, so check the history and policy for handling a completed child. Use `JobParametersExtractor` to build stable child parameters, keep the parent execution ID non-identifying when used only for tracing, and design idempotent business operations so parent-child restarts are safe.
