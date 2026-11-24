# One Job with Multiple Interdependent Steps

A Spring Batch Job can consist of multiple Steps that perform different parts of the same workflow. The Steps can run one after another, branch according to results, or run in parallel when they are independent. When a later Step needs results produced by an earlier Step, the Job flow must clearly express the dependency order and how data is passed between them.

For example, an order import workflow can consist of:

1. Read the input file and validate its structure.
2. Normalize the data that has been validated.
3. Write the orders to the database.
4. Generate the result report.

Step 2 needs the data produced by Step 1; Step 3 needs the normalized data; Step 4 needs the results of the data write. This is a chain of dependencies. Spring Batch lets you model this chain in the Job flow, manage the execution of each Step, and store metadata so that you can monitor it or restart when an error occurs.

## 1. Job Flow and Dependency Relationships Between Steps

A Job defines a workflow made up of Steps and how to move from one Step to another. Dependency relationships are expressed in the flow. The order in which beans are declared or the order of the configuration methods does not by itself create dependency relationships.

For a linear workflow:

~~~text
Job: importOrders
    |
    v
validateInput
    |
    v
normalizeOrders
    |
    v
writeOrders
    |
    v
createReport
~~~

Each Step starts only after the preceding Step ends according to the flow's transition conditions. In the simple case, the Steps continue when the previous Step completes successfully.

You need to distinguish two kinds of relationships:

- **Sequence dependency:** Step B runs only after Step A completes under a defined condition.
- **Data dependency:** Step B needs a result, file, ID, or state produced by Step A.

A flow can define the correct order and still not be enough if the later Step does not know how to obtain the earlier Step's output data. Therefore, designing multiple Steps needs to address both the control flow and the data flow.

## 2. Declaring Steps That Run Sequentially

For a linear workflow, you can use start() and next() to declare the execution order. The following example uses the common Java API of Spring Batch 5:

~~~java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step normalizeOrdersStep,
        Step writeOrdersStep,
        Step createReportStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(validateInputStep)
            .next(normalizeOrdersStep)
            .next(writeOrdersStep)
            .next(createReportStep)
            .build();
}
~~~

start(validateInputStep) specifies the first Step. Each call to next() adds the next Step to the flow. The JobRepository stores the metadata about the JobExecution and StepExecution while the Job runs.

The Steps are configured separately. They can be Tasklet Steps or chunk-oriented Steps depending on the kind of work. For example, checking a file can use a Tasklet; normalizing and writing many records usually suits chunk processing.

~~~java
@Bean
Step validateInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet validateInputTasklet) {

    return new StepBuilder("validateInputStep", jobRepository)
            .tasklet(validateInputTasklet, transactionManager)
            .build();
}
~~~

A chunk-oriented Step can be declared as follows:

~~~java
@Bean
Step writeOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("writeOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

The commit interval of the chunk Step is 100 items. The transaction boundary of each chunk is inside the Step. The fact that the Job orchestrates multiple Steps does not create a single transaction spanning the entire Job.

In an ordinary sequential flow, if the previous Step fails, the following Steps do not run on their own as if the previous Step had succeeded. The Job ends with a failed status unless the flow declares a different transition for that result.

## 3. Passing Data Between Steps

Steps in the same JobExecution may need to exchange information. Spring Batch provides two ExecutionContexts with different scopes:

- **Step ExecutionContext** belongs to one StepExecution. It usually stores the Step's own state, for example the reader position that needs to be recovered on restart.
- **Job ExecutionContext** belongs to the JobExecution. It is suitable for sharing small values between Steps within the same Job run.

If the first Step produces the path of a validated file, the later Step can read that path from the Job ExecutionContext.

### A Step Writes Shared Information

An example of a Tasklet that stores the output file path in the Job ExecutionContext:

~~~java
@Bean
Tasklet validateInputTasklet() {
    return (contribution, chunkContext) -> {
        JobExecution jobExecution =
                contribution.getStepExecution().getJobExecution();

        // Assume the file has been validated and prepared successfully.
        String validatedFile = "/data/batch/validated-orders.csv";

        jobExecution.getExecutionContext()
                .putString("validatedOrdersFile", validatedFile);

        return RepeatStatus.FINISHED;
    };
}
~~~

The value validatedOrdersFile is placed in the Job ExecutionContext so that a later Step can access it. The Job ExecutionContext is saved through the JobRepository during the Step execution lifecycle; shared data should be published when the Step that produces it has completed successfully.

### The Later Step Reads the Information

A reader bean can use @StepScope to receive the value from the Job ExecutionContext when the Step starts:

~~~java
@Bean
@StepScope
FlatFileItemReader<Order> validatedOrdersReader(
        @Value("#{jobExecutionContext['validatedOrdersFile']}")
        String inputFile,
        LineMapper<Order> orderLineMapper) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("validatedOrdersReader")
            .resource(new FileSystemResource(inputFile))
            .lineMapper(orderLineMapper)
            .saveState(true)
            .build();
}
~~~

@StepScope defers creating the reader until the Step runs, at which point the value in the execution context can be resolved. The reader is given a stable name and saveState(true) is enabled so that Spring Batch stores the state needed for restart.

In a real application, the Step that creates the file must ensure the file exists and is complete before the reading Step starts. If the file may be replaced between restarts, you should also store information that identifies the version of the source, such as a checksum or a data batch ID.

### When to Use the Step ExecutionContext and the Job ExecutionContext?

| Need | Appropriate place to store |
|---|---|
| The next read position of a reader | Step ExecutionContext |
| Internal state of a Step that needs to be recovered | Step ExecutionContext |
| A file path created by an earlier Step for a later Step to use | Job ExecutionContext |
| A batch ID or small result that must be shared between Steps | Job ExecutionContext |
| Large business datasets | Database, file, or dedicated storage |

Do not put a list of thousands or millions of items into the ExecutionContext. The context is designed to store metadata and recovery state, not to replace a business data store.

If a Step needs to publish a key from the Step ExecutionContext to the Job ExecutionContext, you can use ExecutionContextPromotionListener. This is useful when the component that produces the data wants to store its state at the Step scope first, and then promote only some selected keys to the Job scope when the Step completes.

An example of configuring the listener:

~~~java
@Bean
ExecutionContextPromotionListener promoteOutputPath() {
    ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();

    listener.setKeys(new String[] { "validatedOrdersFile" });
    return listener;
}
~~~

Registering the listener on the Step that produces the value to be shared:

~~~java
return new StepBuilder("validateInputStep", jobRepository)
        .tasklet(validateInputTasklet, transactionManager)
        .listener(promoteOutputPath())
        .build();
~~~

The Tasklet can put the key into the Step ExecutionContext:

~~~java
contribution.getStepExecution()
        .getExecutionContext()
        .putString("validatedOrdersFile", validatedFile);
~~~

The listener performs the promotion according to its status configuration. You need to ensure the key is written with the correct name and that the Step ends in a status that allows promotion.

## 4. Distinguishing JobParameters from Data Created Within the Job

JobParameters and ExecutionContext can both supply values to multiple Steps, but they serve different purposes.

**JobParameters** are the input of a JobInstance. They usually describe the data period, the source file, the tenant, or the run mode. The identifying parameters determine the identity of the JobInstance.

**Job ExecutionContext** stores data that arises during the run and is shared by the Steps in the same JobExecution. For example, the first Step produces the name of a temporary file or the batch ID that was processed.

For example:

~~~text
JobParameters:
  businessDate = 2026-11-15
  inputFile = /data/in/orders.csv

Step validateInput:
  reads inputFile
  validates the data
  creates validatedFile

Job ExecutionContext:
  validatedFile = /data/out/validated-orders.csv

Step writeOrders:
  reads validatedFile
  writes data to the database
~~~

Do not change JobParameters to pass runtime results from one Step to another. Use the ExecutionContext for runtime state and use an appropriate business data store for large data or data that needs to be queried independently.

## 5. Navigating the Flow by Step Results

Not every workflow has a linear path. In some cases a Step validates data and needs to choose a processing branch depending on the result.

Spring Batch supports declaring transitions based on a Step's ExitStatus. For example, if the validation Step succeeds, continue importing the data; if it fails, run a Step that records the error:

~~~java
@Bean
Job importWithValidationJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step writeOrdersStep,
        Step recordValidationFailureStep) {

    return new JobBuilder("importWithValidationJob", jobRepository)
            .start(validateInputStep)
                .on("COMPLETED").to(writeOrdersStep)
            .from(validateInputStep)
                .on("FAILED").to(recordValidationFailureStep)
            .from(writeOrdersStep)
                .on("*").end()
            .from(recordValidationFailureStep)
                .on("*").fail()
            .end()
            .build();
}
~~~

In the example:

- on("COMPLETED") matches the completed result of the validation Step.
- on("FAILED") matches the failed result and moves to the Step that records the error.
- on("*") is a pattern that matches the remaining result codes of the corresponding Step.
- end() ends the Job flow with a completed result per the declared transition.
- fail() ends the flow with a failed result.

This example shows that the Step that records the error can still be performed to store diagnostic information, while the final result of the Job is still a failure. In a real flow, you need to declare transitions appropriate to the ExitStatus values that the Step can return.

### BatchStatus and ExitStatus in Navigation

BatchStatus describes the execution lifecycle status, such as COMPLETED, FAILED, or STOPPED. ExitStatus is the result code used to describe the result of a Step and to navigate the flow.

A Step can end with the BatchStatus COMPLETED but return a business ExitStatus such as NO_DATA. In that case, the flow can use on("NO_DATA") to select the corresponding branch.

For example, a file-checking Step can return the code NO_DATA if the file is valid but has no records:

~~~java
contribution.setExitStatus(new ExitStatus("NO_DATA"));
return RepeatStatus.FINISHED;
~~~

The corresponding transition can be declared:

~~~java
return new JobBuilder("importOptionalDataJob", jobRepository)
        .start(checkDataStep)
            .on("NO_DATA").to(createEmptyReportStep)
        .from(checkDataStep)
            .on("COMPLETED").to(importDataStep)
        .from(createEmptyReportStep)
            .on("*").end()
        .from(importDataStep)
            .on("*").end()
        .end()
        .build();
~~~

You need to design the order and patterns of the transitions so that all possible results are handled explicitly. Do not use a single generic COMPLETED code for every business situation if those situations need to follow different branches.

## 6. Using JobExecutionDecider for Business Decisions

When the branching condition is more complex than a simple ExitStatus code, you can use JobExecutionDecider. The decider receives the JobExecution and the most recent StepExecution, and then returns a FlowExecutionStatus for the flow to choose a branch.

For example, a job can choose between a full import process or an import of only the changes based on the JobParameter mode:

~~~java
public class ImportModeDecider implements JobExecutionDecider {

    @Override
    public FlowExecutionStatus decide(
            JobExecution jobExecution,
            StepExecution stepExecution) {

        String mode = jobExecution.getJobParameters().getString("mode");

        if ("FULL".equalsIgnoreCase(mode)) {
            return new FlowExecutionStatus("FULL");
        }

        return new FlowExecutionStatus("DELTA");
    }
}
~~~

The flow uses the statuses returned by the Decider:

~~~java
return new JobBuilder("modeBasedImportJob", jobRepository)
        .start(prepareInputStep)
        .next(importModeDecider)
            .on("FULL").to(fullImportStep)
        .from(importModeDecider)
            .on("DELTA").to(deltaImportStep)
        .from(fullImportStep)
            .on("*").end()
        .from(deltaImportStep)
            .on("*").end()
        .end()
        .build();
~~~

The Decider only decides the next branch. It does not replace the Step's data processing work. Keeping the decision logic centralized in the Decider makes the flow easier to read when the business condition needs to check multiple parameters or metadata.

If the decision depends only on the direct result of a single Step, an ExitStatus transition is usually simpler. If the decision is based on multiple runtime values or needs to share a single branch-selection logic, a Decider is more suitable.

## 7. Dependent Steps and Independent Steps

When designing the flow, you need to determine which Steps really depend on the results of other Steps.

For example:

~~~text
                  +--> generateCustomerReport --+
prepareData ------|                              |----> publishReports
                  +--> generateOrderReport -----+
~~~

The two report-generating Steps can run independently after prepareData completes. The publishReports Step starts only when both report-generating branches have ended.

If two Steps need the same file or the same output record, they have a data dependency. Do not put them into two parallel branches if one branch can change data that the other branch is reading.

For independent work, Spring Batch supports split to run multiple Flows in parallel using a TaskExecutor. General diagram:

~~~text
                    +--> customerFlow --+
prepareData --> split                   +--> publishReports
                    +--> orderFlow -----+
~~~

Each child flow can contain one or more Steps. The Step after the convergence point runs only when the flows in the split have completed according to the flow's rules.

When running in parallel, you need to consider:

- Whether the two branches access or update the same data.
- Whether you need locks, data partitioning, or a concurrency-safe writer design.
- Whether the shared beans have mutable state.
- Whether multiple branches write to the same key in the Job ExecutionContext.
- Whether the database resources, thread pool, and external services can handle the load.

Run in parallel only when the branches are truly independent or a clear synchronization mechanism is in place. If Step B needs Step A's output, keep the dependency relationship in the flow.

## 8. Transactions and Errors Between Steps

Each Step has its own lifecycle and transaction. With a chunk-oriented Step, each chunk usually has one transaction. Steps are not implicitly inside one large transaction.

Suppose a Job has three Steps:

~~~text
Step A: validate and prepare  -> COMPLETED
Step B: write to database    -> FAILED
Step C: create report        -> NOT STARTED
~~~

If Step A has committed data or created a file, then when Step B fails, the changes Step A already committed are not automatically rolled back. Step C does not run in this flow unless an error-handling transition leads the flow there.

This has several consequences:

- A later Step runs only when the transition condition from the previous Step is satisfied.
- Data created by the previous Step may still exist even though the later Step failed.
- On restart, a completed Step is usually skipped and Spring Batch continues from the Step that needs to run again.
- If a Step produces effects outside the transaction, you need to account for the possibility that those effects happened before the Job failed.

For effects that cannot be rolled back, such as sending an email, calling an API, or publishing a message, use an idempotency key, an outbox, or an appropriate compensation mechanism. A Step that is re-run should not create duplicate records or send duplicate notifications unintentionally.

## 9. Restarting a Job with Multiple Steps

Spring Batch stores the JobInstance, JobExecution, and StepExecution in the JobRepository. When a Job fails, an operator can restart the same JobInstance if the state and configuration allow it.

For example:

~~~text
JobInstance: importOrders, businessDate=2026-11-15

JobExecution 101:
  validateInputStep   -> COMPLETED
  normalizeOrdersStep -> COMPLETED
  writeOrdersStep     -> FAILED
  createReportStep    -> NOT STARTED

JobExecution 108 (restart):
  validateInputStep   -> skipped (already completed)
  normalizeOrdersStep -> skipped (already completed)
  writeOrdersStep     -> run again
  createReportStep    -> runs after writeOrdersStep completes
~~~

This is the common default behavior when restarting a JobInstance: completed Steps are skipped. A failed Step is executed again, using a checkpoint if the components support restart.

If you need to re-run a completed Step every time the Job restarts, you can configure allowStartIfComplete(true) for that Step. Enable it only when the Step's operation is safe to repeat or there is a mechanism to clean up the old data.

When restarting, keep the identifying JobParameters unchanged to continue the same JobInstance. If you change an identifying parameter, Spring Batch creates a new JobInstance and does not use the previous instance's checkpoint.

### Restart and Data Between Steps

If Step A creates a file for Step B, make sure that file still exists and is still the correct version when the Job is restarted. If the temporary file is deleted after the first run, Step B may be unable to continue even though its checkpoint is still valid.

Some design approaches:

- Store intermediate output in a durable location, identified by JobInstance or business key.
- Store file-identifying metadata in the Job ExecutionContext.
- Regenerate the output safely if the Step that creates the data is re-run.
- Use a database staging table if you need to query, verify, and recover the intermediate data.
- Clean up temporary data under a clear lifecycle policy, after the Job no longer needs to be restarted.

A reader's checkpoint only restores the read position; it does not guarantee that the source file still exists or has not changed.

## 10. Rules for Designing a Job with Multiple Interdependent Steps

When dividing a workflow into multiple Steps, you should define the work boundaries by clear responsibilities. Each Step should have inputs, outputs, and a completion condition that are easy to understand.

Some useful principles:

1. **One Step, one main responsibility.** Separate work such as validating input, transforming, writing data, and generating reports when they have different lifecycles or recovery approaches.
2. **Declare dependencies in the Job flow.** Use next(), transitions, or a Decider to express precisely the conditions under which a later Step runs.
3. **Pass metadata via the ExecutionContext.** Use the Job ExecutionContext for small values that need to be shared between Steps; use the Step ExecutionContext for a Step's own checkpoint.
4. **Store business data in the appropriate place.** Large data should live in a database or durable file, not be stuffed into the ExecutionContext.
5. **Design Steps to be restartable.** Readers, writers, and intermediate outputs must support resuming or safe repeated execution.
6. **Do not run in parallel while dependencies remain unresolved.** Split only independent branches or branches that have a synchronization mechanism.
7. **Keep Step names stable.** Metadata and execution history are tied to the Step name; renaming arbitrarily can affect how state is recognized across deployment versions.
8. **Observe each Step.** Track BatchStatus, ExitStatus, run time, and the counters to know exactly which Step completed or failed.

A Job with multiple Steps is not necessarily better than one large Step. Divide into Steps when there is a clear benefit in responsibility, recovery, observability, or business navigation. If operations must always form one small unit of processing and do not need their own lifecycle, you can keep them in the same Step.

## 11. Monitoring and Testing a Multi-Step Flow

When testing a multi-Step Job, you need to confirm both the execution order and the data passed between Steps.

For a sequential Job, you can observe the list of StepExecutions belonging to the JobExecution and check:

- Which Steps started and ended.
- The actual order of the Steps.
- The BatchStatus and ExitStatus of each Step.
- The read, write, filter, skip, commit, and rollback counters if it is a chunk Step.
- The important keys in the Job ExecutionContext.
- The intermediate output that the next Step uses.

When writing integration tests, you can use JobLauncherTestUtils from Spring Batch's test support to run the Job with specific JobParameters. Some important scenarios:

| Scenario | What to confirm |
|---|---|
| All Steps succeed | The Steps run in the correct order and the Job completes |
| The first Step fails | The dependent Steps after it do not run via the success branch |
| A middle Step fails | The later Steps do not run; the state and checkpoint are saved |
| Restart after an error | Completed Steps are handled per the configuration; the failed Step can continue |
| Different conditional branches | The flow takes the correct branch by ExitStatus or Decider |
| Missing shared data | The consuming Step reports a clear error instead of using a wrong default value |
| Parallel run | No unexpected data overwrites or resource contention |

A test that only checks the Job has the COMPLETED status is not enough if the workflow has multiple branches. You should also check the StepExecutions that were created, the execution order, and the output data of the important Steps.

When reading a multi-Step Job, trace three relationships: the flow decides which Step runs next; the ExecutionContext or a shared data store carries output between Steps; the JobRepository stores state for monitoring and restart. Designing all three clearly makes a batch workflow easy to operate and to recover when a phase encounters an error.

