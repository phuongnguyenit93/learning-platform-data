# A Step Is a Unit of Processing in a Job

In Spring Batch, a **Job** describes a batch processing workflow, while a **Step** divides that workflow into phases with clear responsibilities. A Job usually consists of several Steps that run in sequence or branch depending on the outcome. Each Step performs one part of the work and has its own lifecycle, status, statistics, and transaction mechanism.

For example, a customer data import workflow can be divided into the following Steps:

1. Validate the input file and the batch parameters.
2. Read, normalize, and write customers to the database.
3. Reconcile the record counts.
4. Save the result report or send a completion notification.

Dividing a Job into Steps makes it easier to monitor progress, handle errors, restart from the appropriate phase, and test each part.

## 1. Job and Step in the Spring Batch Architecture

A Job is the top-level unit of work. A Job defines which Steps to run and the rules for moving from one Step to another. A Step is a specific execution phase inside a Job.

~~~mermaid
flowchart TD
    A["Job: importCustomersJob"] --> B["Step 1: validateInput"]
    B --> C["Step 2: importCustomers"]
    C --> D["Step 3: reconcile"]
    D --> E["Step 4: publishReport"]
~~~

In this example:

- The Job represents the entire customer import workflow.
- Each Step is responsible for an independent phase.
- The result of one Step can determine the next Step.
- Spring Batch records the execution result of each Step for monitoring and restart.

You should not put every operation into a single Step if the operations have different lifecycles, error handling, or restart requirements. Conversely, there is no need to create a new Step for every small line of code. A Step should represent a meaningful phase of the business or operational process.

### Distinguishing the Concepts

| Concept | Role |
|---|---|
| Job | Defines a batch workflow made up of one or more Steps and the control flow |
| JobInstance | A logical run identified by the Job and its identifying JobParameters |
| JobExecution | A specific execution of a JobInstance |
| Step | Defines a processing phase in a Job |
| StepExecution | A record of one execution of a Step within a JobExecution |
| JobRepository | Stores the metadata of the Job, Steps, status, and ExecutionContext |
| JobLauncher | Launches a Job with its JobParameters |

You need to distinguish **Step** from **StepExecution**. A Step is a configuration that can be referenced in a Job. A StepExecution is a runtime record created when the Step actually starts running. When a JobInstance is restarted, Spring Batch creates a new JobExecution and creates new StepExecutions for the Steps that are executed in that run.

## 2. What Is a Step Responsible For?

A Step establishes a clear boundary for a processing phase. Depending on the type of Step, the framework and the application configuration manage the following responsibilities:

- **Executing the work:** invoking Tasklet logic or orchestrating the read, process, and write flow by chunk.
- **Transactions:** defining the transaction scope for each Tasklet execution or each chunk.
- **Status tracking:** recording whether the Step is running, completed, failed, or stopped.
- **Statistics:** storing the number of items read, written, filtered, and skipped, and the number of commits and rollbacks.
- **State persistence:** keeping checkpoints in the ExecutionContext so that processing can continue when the Job is restarted.
- **Extended lifecycle:** invoking listeners before and after the Step or around each chunk.
- **Flow control:** providing an ExitStatus so that the Job can decide the next step.

A Step is not necessarily a single transaction that spans from start to finish. A chunk-oriented Step can consist of thousands of small transactions, each corresponding to one chunk. This allows a Job to process large volumes of data without holding all the work in one long transaction.

## 3. Ways to Implement a Step

Spring Batch supports several kinds of Steps. The two most common approaches are Tasklet and chunk-oriented processing.

### Tasklet Step

A Tasklet is suitable for an operation with a relatively well-defined scope, for example:

- Deleting temporary files or preparing a working directory.
- Checking conditions before importing data.
- Calling a stored procedure.
- Copying or renaming files.
- Updating a group of statuses in the database.
- Generating a report or marking a batch as completed.

A Tasklet has a simple contract:

~~~java
public interface Tasklet {
    RepeatStatus execute(
        StepContribution contribution,
        ChunkContext chunkContext
    ) throws Exception;
}
~~~

Each time `execute` is called, the Tasklet returns one of the following results:

- `RepeatStatus.FINISHED`: the Tasklet's work is complete.
- `RepeatStatus.CONTINUABLE`: the framework may call the Tasklet again.

Spring Batch executes each Tasklet call within the transaction scope used by the Step. If the Tasklet returns `CONTINUABLE`, the framework repeats the call using the repeat mechanism; if it returns `FINISHED`, the Step ends normally.

An example of a Tasklet that checks for and creates the output directory:

~~~java
@Bean
Tasklet prepareOutputDirectory() {
    return (contribution, chunkContext) -> {
        Path output = Path.of("work", "output");

        Files.createDirectories(output);

        return RepeatStatus.FINISHED;
    };
}
~~~

Declaring a Step that uses the Tasklet:

~~~java
@Bean
Step prepareOutputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet prepareOutputDirectory) {

    return new StepBuilder("prepareOutputStep", jobRepository)
        .tasklet(prepareOutputDirectory, transactionManager)
        .build();
}
~~~

The Tasklet returns `FINISHED` after creating the directory. If creating the directory fails and an exception is thrown, the Step fails according to the error handling policy in effect.

### Chunk-oriented Step

Chunk-oriented processing is suitable for work that processes many items. The Step reads items one at a time, can process each item, gathers the results into a chunk, and then writes them as a group.

~~~mermaid
flowchart LR
    A["ItemReader"] --> B["ItemProcessor"]
    B --> C["Chunk"]
    C --> D["ItemWriter"]
    D --> E["Commit"]
~~~

Configuring a chunk-oriented Step usually involves declaring the commit interval:

~~~java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> reader,
        ItemProcessor<CustomerInput, Customer> processor,
        ItemWriter<Customer> writer) {

    return new StepBuilder("importCustomersStep", jobRepository)
        .<CustomerInput, Customer>chunk(200, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
~~~

With a commit interval of `200`, the framework reads and processes up to 200 input items for a chunk before writing the results and completing that chunk's transaction. The last chunk may contain fewer items if the source is exhausted. If the processor filters an item by returning `null`, the number of items the writer receives can be smaller than the number of items the reader has read.

Tasklet and chunk-oriented are two ways of configuring how a Step performs its work. A chunk-oriented Step is also implemented internally by the framework through the Tasklet mechanism, but users configure it with `chunk(...)` along with a reader, processor, and writer. When designing a Job, choose the approach that fits the nature of the processing phase.

### Comparing Tasklet and Chunk-oriented

| Criterion | Tasklet | Chunk-oriented |
|---|---|---|
| Unit of work | One operation or one iteration of the Tasklet | A group of items |
| Main configuration | `tasklet(...)` | `chunk(...)` |
| Commonly used components | Tasklet | ItemReader, ItemProcessor, ItemWriter |
| Transaction | Each Tasklet call | Each chunk |
| Suitable cases | Preparation, cleanup, calling procedures, control operations | Importing, transforming, and exporting datasets |
| Data tracking | Updates the contribution itself if needed | The framework counts the items in the chunk |

## 4. Declaring a Step and Attaching It to a Job

In Spring Batch 5, you can create a Step with `StepBuilder` and pass the `JobRepository` into the constructor. The transaction manager is declared explicitly when configuring a Tasklet or chunk.

An example of a Job that runs three Steps in order:

~~~java
@Bean
Job customerImportJob(
        JobRepository jobRepository,
        Step prepareOutputStep,
        Step importCustomersStep,
        Step reconcileStep) {

    return new JobBuilder("customerImportJob", jobRepository)
        .start(prepareOutputStep)
        .next(importCustomersStep)
        .next(reconcileStep)
        .build();
}
~~~

The Job performs the following:

1. `prepareOutputStep` prepares the output environment.
2. `importCustomersStep` imports and writes the customer data.
3. `reconcileStep` reconciles the results.

`start(...)` specifies the first Step. `next(...)` appends the next Step. When a Step completes in the normal flow, the Job moves on to the next Step.

Step beans are usually declared separately so that they can be reused across multiple Jobs if the semantics and configuration are the same. However, think carefully before sharing a Step among multiple Jobs, because the Step name, restart state, parameters, and input resources may differ.

## 5. The Step Execution Lifecycle

When a Job reaches a Step, Spring Batch creates and manages the corresponding StepExecution. The general lifecycle is as follows:

~~~mermaid
sequenceDiagram
    participant J as Job
    participant R as JobRepository
    participant S as Step
    participant L as StepListener
    participant W as Work

    J->>R: Create StepExecution
    J->>S: Execute Step
    S->>L: beforeStep
    S->>W: Run the Tasklet or the chunks
    W-->>S: Results and statistics
    S->>L: afterStep
    S->>R: Save status and results
    S-->>J: ExitStatus
    J->>J: Choose the next branch
~~~

This can be described as the following phases:

1. The Job flow chooses the Step to run.
2. Spring Batch creates a StepExecution associated with the current JobExecution.
3. The Step moves to the started state and calls the before-Step listener if one is configured.
4. The Step runs the Tasklet or processes the chunks.
5. The framework updates the statistics, status, and ExecutionContext.
6. When the Step ends, the after-Step listener is called.
7. The result is stored in the JobRepository.
8. The Job uses the ExitStatus to determine the next path.

If a Step throws an unhandled exception, the Step usually ends in a failed state. The Job then evaluates the result according to the configured flow and transitions.

## 6. StepExecution and Statistics

`StepExecution` represents a specific run of a Step. This object is associated with a JobExecution and stores information such as:

- The Step name and the start and end times.
- BatchStatus and ExitStatus.
- The number of items read and written.
- The number of items filtered or skipped.
- The number of commits and rollbacks.
- The Step's ExecutionContext.

Some common counters:

| Property | Meaning |
|---|---|
| `readCount` | Number of items read |
| `writeCount` | Number of items written successfully |
| `filterCount` | Number of items filtered in the processor |
| `readSkipCount` | Number of read errors that were skipped |
| `processSkipCount` | Number of processing errors that were skipped |
| `writeSkipCount` | Number of write errors that were skipped |
| `commitCount` | Number of commits |
| `rollbackCount` | Number of rollbacks |
| `status` | The BatchStatus of the StepExecution |
| `exitStatus` | The exit result of the Step |

The counters help determine how much data the Step has processed and in which phase errors occurred. For example, if `readCount` is high but `writeCount` is low, many items may have been filtered or part of the processing may have been skipped. You need to look at `filterCount` and the skip counts to understand the cause.

You can access the StepExecution from listeners or from components that receive a `StepContribution`. With a Tasklet, the `StepContribution` lets you update the contribution information for the current execution. In a chunk-oriented Step, the framework manages many of the standard statistics itself.

## 7. Distinguishing BatchStatus from ExitStatus

Spring Batch stores both the execution status and the exit result of a Step. The two values are related but serve different purposes.

**BatchStatus** represents the lifecycle state of the StepExecution. Some common statuses:

| BatchStatus | Meaning |
|---|---|
| `STARTING` | Preparing to start |
| `STARTED` | Executing |
| `STOPPING` | In the process of stopping |
| `STOPPED` | Stopped on request or by the stop mechanism |
| `COMPLETED` | Execution completed |
| `FAILED` | Execution failed |
| `ABANDONED` | The execution was marked as not to be continued |
| `UNKNOWN` | A reliable status could not be determined |

**ExitStatus** describes the result that the Step returns to the Job flow. Common values include `COMPLETED`, `FAILED`, `STOPPED`, and `NOOP`. An application can also create custom ExitStatus values such as `NO_DATA` or `VALIDATION_WARNING` to control the next branch.

An important difference is that **the Job flow uses ExitStatus to match transitions**. BatchStatus mainly reflects the execution state. You should not assume the two values are always the same or always have the same meaning.

For example, a Step may complete technically but find that there is no data to import. A listener can return a custom ExitStatus `NO_DATA`; the Job then moves to the branch that handles empty data.

## 8. Controlling the Job Flow with Step Results

A Job can run sequentially or branch based on ExitStatus. Sequential configuration uses `next(...)`. When branching is needed, you can use transitions with `on(...)` and `to(...)`.

For example, after the input validation Step:

~~~java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step importStep,
        Step rejectInputStep) {

    return new JobBuilder("importJob", jobRepository)
        .start(validateInputStep)
            .on("FAILED").to(rejectInputStep)
        .from(validateInputStep)
            .on("*").to(importStep)
        .end()
        .build();
}
~~~

Meaning:

- If `validateInputStep` has an ExitStatus matching `FAILED`, the Job moves to `rejectInputStep`.
- If the result matches the pattern `*`, the Job moves to `importStep`.
- `end()` ends the flow definition before the Job is built.

The `*` pattern is a wildcard that matches the other ExitStatus values. When declaring multiple transitions, you need to order them and design the patterns so that the specific branch is handled as intended.

Moving to an error-handling Step does not automatically decide whether the final Job must be COMPLETED or FAILED. The final result depends on the flow and the terminating transition that is configured. If you need the Job to report failure even though it ran a logging or error-collecting Step, design the final outcome of the flow explicitly.

### JobExecutionDecider

When the branching condition depends on data or complex business logic, you can use `JobExecutionDecider`. The decider returns a `FlowExecutionStatus` so that the Job can choose a branch.

Examples of suitable decisions:

- Whether the batch has data or not.
- Whether an additional reconciliation step needs to run.
- Whether the data is a new import or an update.
- Whether a business condition allows the flow to proceed or requires a switch to an exception-handling flow.

A decider is suitable for flow-control decisions. The heavy data processing should still be placed in a dedicated Step, so that the flow does not become a place that holds data reading and writing logic.

## 9. StepExecutionListener and Other Listeners

Listeners let you run logic at specific points in the Step lifecycle without mixing that logic into the reader, processor, or writer.

`StepExecutionListener` provides two main extension points:

- `beforeStep(StepExecution)` is called before the Step executes.
- `afterStep(StepExecution)` is called after the Step ends; the method can return an ExitStatus to supplement or change the exit result.

An example of a listener that flags a Step with no data:

~~~java
@Bean
StepExecutionListener emptyResultListener() {
    return new StepExecutionListener() {
        @Override
        public void beforeStep(StepExecution stepExecution) {
            // You can record the start time or other starting information.
        }

        @Override
        public ExitStatus afterStep(StepExecution stepExecution) {
            if (stepExecution.getReadCount() == 0) {
                return new ExitStatus("NO_DATA");
            }
            return null;
        }
    };
}
~~~

Attaching the listener to the Step:

~~~java
return new StepBuilder("importStep", jobRepository)
    .<InputRecord, OutputRecord>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .listener(emptyResultListener())
    .build();
~~~

In the example, if the reader reads no items, the listener returns the ExitStatus `NO_DATA`. If there is no custom result, the listener returns `null` to keep the existing result unchanged.

Besides StepExecutionListener, Spring Batch also has listeners at the chunk, read, process, and write scopes. For example, `ChunkListener` can run before or after a chunk; `ItemReadListener` can react when a read succeeds or encounters an error. Choose the listener according to the scope of the event you need to observe.

Listeners should be used for logging, metrics, audit recording, or adjusting the execution result. Avoid placing the main business logic in listeners, because that makes it hard to determine the processing flow and the transaction boundaries.

## 10. ExecutionContext and Data Between Steps

A Step often needs to store state for restart or to share a small amount of information between phases. Spring Batch provides `ExecutionContext` at two scopes:

- **StepExecutionContext:** associated with a StepExecution, usually storing the Step's own checkpoints and state.
- **JobExecutionContext:** associated with a JobExecution, used to share information between Steps within the same Job run.

For example, a file validation Step can store the number of valid lines or the batch code in the JobExecutionContext for the next import Step to use. A reader can store its read position in the StepExecutionContext so it can be restored on restart.

~~~java
// Illustrative example in a component running inside a Step.
stepExecution.getExecutionContext()
    .putLong("lastProcessedId", lastProcessedId);

jobExecution.getExecutionContext()
    .putString("batchReference", batchReference);
~~~

You need to choose the right storage scope:

| Type of data | Appropriate scope |
|---|---|
| File read position or reader checkpoint | StepExecutionContext |
| Internal state used only within one Step | StepExecutionContext |
| Batch code shared by multiple Steps | JobExecutionContext |
| Result information that must be passed between Steps | JobExecutionContext |

The ExecutionContext is a state storage area that can be persisted through the JobRepository. Store only small data that is meaningful for resuming or coordinating work. Do not use it as a store for large datasets; business data should live in files, a database, or an appropriate storage system.

The StepExecutionContext is usually updated at the Step's checkpoints. The JobExecutionContext is saved so that subsequent Steps can use it, usually at the boundary where a Step completes. For custom components, you need to implement state saving and restoring in line with the lifecycle.

## 11. Restart and Step Re-run Behavior

An important benefit of Steps is that Spring Batch can track which phases have completed and which need to continue.

Suppose a Job consists of three Steps:

~~~mermaid
flowchart TD
    A["Step 1: Prepare"] --> B["Step 2: Import"]
    B --> C["Step 3: Reconcile"]
    B -. "Error midway" .-> D["Job stops"]
    D -. "Restart the same JobInstance" .-> B
~~~

If Step 1 has completed, Step 2 fails, and the Job is restarted with the same JobInstance, Spring Batch usually skips the completed Step 1 and continues from the Step that can be restarted. With a chunk-oriented Step that has checkpoints, the framework can restore the state and continue from the uncommitted portion.

Some rules to understand:

- A Step that is COMPLETED is usually skipped when the JobInstance is restarted.
- A failed or stopped Step can be executed again if the Job and the Step allow restart.
- Each time a Step actually runs, a new StepExecution is created.
- Checkpoint data is used to restore the state of components that support restart.
- If the identifying JobParameters are changed, the application may create a new JobInstance instead of continuing the old one.

### allowStartIfComplete

By default, a completed Step does not run again when the same JobInstance is restarted. You can allow a Step to run again with `allowStartIfComplete(true)`:

~~~java
@Bean
Step refreshReferenceDataStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet refreshReferenceDataTasklet) {

    return new StepBuilder("refreshReferenceDataStep", jobRepository)
        .tasklet(refreshReferenceDataTasklet, transactionManager)
        .allowStartIfComplete(true)
        .build();
}
~~~

This option is useful when a Step needs to run again each time the JobInstance is restarted, for example to refresh an intermediate data area before continuing. Enable it only when the work can be safely re-run or when a mechanism to control side effects is already in place.

### startLimit

`startLimit(...)` limits the number of times a Step is allowed to start executing:

~~~java
return new StepBuilder("importStep", jobRepository)
    .<InputRecord, OutputRecord>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .startLimit(3)
    .build();
~~~

The example above limits the number of times the Step is started, per the configuration, to 3. When the limit is exceeded, Spring Batch does not launch that Step again within the JobInstance. This limit is useful for preventing a Step from failing continuously and being restarted indefinitely.

### Safe Restart and Idempotency

Spring Batch stores metadata and checkpoints, but it does not automatically make every external operation idempotent. If a Step sends requests to an API, sends emails, or writes files without a control mechanism, the operation may be repeated when the Job restarts.

Some ways to reduce the risk:

- Use a business key or batch code to identify operations that have already been processed.
- Design write operations to be idempotent if the business allows it.
- Write the processing state and the data in the same transaction when both belong to the same database.
- Use an outbox or an acknowledgment mechanism from the target system for external effects.
- Make sure the Tasklet can be called again without producing incorrect data or duplicate side effects.

Restart is safe only when the stored state and the Step's effects are designed to be consistent with each other.

## 12. Step Scope and Job Parameters

A Step may need to receive parameters when the Job is launched, such as a file path, a batch code, or a processing date. These values are not necessarily available when the Step bean is declared. `@StepScope` lets you create a bean scoped to the StepExecution and use late binding to obtain runtime parameters.

Example:

~~~java
@Bean
@StepScope
Tasklet validateInputFile(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return (contribution, chunkContext) -> {
        Path path = Path.of(inputFile);
        if (!Files.isRegularFile(path)) {
            throw new FileNotFoundException("Input file not found: " + inputFile);
        }
        return RepeatStatus.FINISHED;
    };
}
~~~

When the Step starts, Spring Batch creates the scoped bean and injects the `inputFile` value from the JobParameters. The Tasklet uses that path to check the input file, so the same configuration can run with many different files without hard-coding the path.

You can obtain data from the contexts through similar expressions:

- `#{jobParameters['batchDate']}`: a Job parameter.
- `#{jobExecutionContext['batchReference']}`: data shared at the JobExecution scope.
- `#{stepExecutionContext['partitionFile']}`: data at the StepExecution scope.

Use Step scope only when a bean needs runtime data or state tied to a StepExecution. Stateless beans that do not depend on runtime parameters usually do not need this scope.

## 13. Stopping a Step and Handling Errors

A Step can end in several ways:

- Completing normally.
- Failing because of an exception or an error condition.
- Being stopped at the request of the application or an operational mechanism.
- Being skipped according to flow or restart rules.

In practice, you need to distinguish business errors, data errors, and infrastructure errors. For example, a malformed file can be handled by a validation Step that reports the error clearly; a temporary database connection error may need a retry; a programming logic error usually needs to make the Job fail so it can be investigated.

With a chunk-oriented Step, you can configure skip and retry for the appropriate exception types. With a Tasklet, you need to handle the error proactively or throw the exception so that the framework records the status. You should not catch every exception and then return `FINISHED`, because the Job could then report completion even though the work did not succeed.

When a controlled stop is needed, the application can request that the Job or Step stop. The Step goes to the stopped state at a point the framework can handle safely. With chunk processing, this is usually tied to chunk and transaction boundaries, so that data that has already been committed is preserved.

## 14. Organizing Steps for Easy Operations

A large Job should be divided into Steps that have clear goals, inputs, and outputs. When naming a Step, use a name that expresses the business purpose or phase, for example:

- `validateInputStep`
- `loadReferenceDataStep`
- `importCustomerStep`
- `reconcileResultStep`
- `publishReportStep`

Step names are stored in the metadata, so they need to be kept stable across deployment versions if you want restart and operational history queries to be consistent.

A Step should have one main responsibility. If a Step loads files, validates business rules, sends notifications, and updates multiple systems all at once, it becomes hard to tell which phase an error belongs to and how to restart safely. You can split it into separate Steps when each phase has different transaction, retry, audit, or operational rules.

However, splitting too finely also makes a Job complicated: more metadata, more Step transitions, and more points where state must be managed. Split along boundaries that are meaningful to the business or operations.

### Running Steps in Parallel and Partitioning

For large data volumes, Spring Batch offers several ways to scale execution:

- Run independent flows in parallel when they do not depend on each other's results.
- Partitioning divides the data into multiple parts and runs a worker Step for each part.
- Some chunk configurations can use a TaskExecutor for concurrent processing, depending on the model and version.

These approaches increase the thread-safety requirements for the reader, processor, writer, and shared resources. You need to ensure that each partition has its own data range, does not overwrite another partition's checkpoint, and does not create conflicts when writing to the target. Add parallelism only after you have identified the performance bottleneck and can verify the correctness of the data.

## 15. Monitoring and Testing a Step

A Step should be tested as an independent unit before testing the whole Job. Important aspects include:

- **Success path:** the Step performs the right work and ends with the expected status.
- **Error path:** exceptions are propagated or handled according to the policy.
- **Statistics:** the read, write, filter, skip, commit, and rollback counts reflect the results correctly.
- **Transaction:** an error midway does not leave partial data in resources participating in the transaction.
- **Restart:** the Step can restore its checkpoint and does not produce unexpected duplicate effects.
- **Flow:** the ExitStatus leads the Job to the correct next Step.
- **Listener:** listeners are called at the right time and do not change the result unintentionally.
- **Runtime parameters:** Step scope receives the correct JobParameters and ExecutionContext.

When testing a Job, you should also test the case where one Step completes but the next Step fails. On restart, check whether the completed Step is skipped correctly, whether the failed Step restores its state correctly, and whether the Job ends with a status consistent with the flow.

You can use Spring Batch's testing utilities such as `JobLauncherTestUtils` and `JobRepositoryTestUtils` in integration tests. Tests should use a JobRepository and transaction configuration similar to the application environment so that the results reflect the real metadata and restart behavior.

## 16. Comprehensive Example: A Customer Import Job

A customer import Job can be organized into three Steps:

~~~mermaid
flowchart TD
    A["validateInputStep"] --> B["importCustomersStep"]
    B --> C["reconcileStep"]
    A -. "FAILED" .-> D["rejectInputStep"]
~~~

- `validateInputStep` is a Tasklet Step that checks the file and the parameters.
- `importCustomersStep` is a chunk-oriented Step that reads, normalizes, and writes the data.
- `reconcileStep` is a Tasklet Step that compares the number of records received with the number written.
- `rejectInputStep` is the branch that handles the case where the input is invalid.

Basic sequential configuration:

~~~java
@Bean
Job customerImportJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step importCustomersStep,
        Step reconcileStep) {

    return new JobBuilder("customerImportJob", jobRepository)
        .start(validateInputStep)
        .next(importCustomersStep)
        .next(reconcileStep)
        .build();
}
~~~

If you need a branch for invalid input, replace the sequential flow with ExitStatus-based transitions as in the example in the flow control section. In that case, the listener or the Tasklet of the validation Step can return a custom ExitStatus to distinguish empty data, valid data, and invalid data.

When the Job runs, the JobRepository stores the JobExecution and the StepExecutions. If the import Step fails after some chunks have been committed, you can restart the JobInstance to continue from the checkpoint. The completed input validation Step is usually skipped, while the import Step restores its state if the reader and writer support restart.

## 17. Key Points to Remember When Designing a Step

- A Job describes the whole workflow; a Step represents each meaningful processing phase.
- A Step is a definition, while a StepExecution is the record of one Step run.
- A Tasklet is suitable for a single operation or control work; chunk-oriented is suitable for datasets made up of many items.
- A Step has its own transaction boundary and state; a chunk-oriented Step usually commits per chunk.
- BatchStatus reflects the execution state, while ExitStatus is used to control the Job flow.
- The ExecutionContext stores checkpoints and the information needed between phases.
- Listeners provide extension points in the Step lifecycle.
- Safe restart requires that readers, writers, and side effects be able to recover or to be handled appropriately when repeated.
- Step names should be stable and a Step's responsibility should be clear enough to make it easy to monitor, test, and operate.

By dividing a Job into Steps along the correct work boundaries, a Spring Batch application can control progress better, locate errors faster, and restart from the appropriate phase without having to redo the entire workflow.

