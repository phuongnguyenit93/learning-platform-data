# Distinguishing Context from Job Parameters

In Spring Batch, **JobParameters** and **ExecutionContext** both carry data during a Job run, but they solve two different problems:

- **JobParameters** are input data passed when launching a Job. They describe the requested run, and identifying parameters can identify the JobInstance.
- **ExecutionContext** is a storage area for state that can change during execution. Spring Batch and the application use it to store checkpoints, progress, and data needed for restoration on restart.

A concise way to remember: JobParameters answer **"With what inputs was the Job requested to run?"**; ExecutionContext answers **"How far has the Job processed, and what state must be kept to continue?"**

If the two mechanisms are misused, a Job may create the wrong JobInstance, restart with incorrect data, or lose intermediate state between Steps.

## 1. What Are JobParameters?

JobParameters are a set of parameters passed to a Job when the application calls JobLauncher. Values typically describe the unit of work to process or how to perform that work.

For example, a file-import Job might receive:

- Input file path.
- Business date.
- Customer code or reconciliation period code.
- FULL or DELTA mode.
- Request ID from the calling system.

Creating JobParameters with JobParametersBuilder:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/customers.csv", true)
        .addString("businessDate", "2026-11-15", true)
        .addString("mode", "FULL", false)
        .toJobParameters();
~~~

The final boolean parameter specifies whether the value is an **identifying parameter**:

- true: participates in identifying the JobInstance.
- false: does not participate in identifying the JobInstance.

In the example:

- inputFile and businessDate are identifying parameters.
- mode is a non-identifying parameter.

JobParameters are created before the Job runs and are treated as input data of the execution. JobParameters itself is an immutable object; if you need to record progress that changes while running, use ExecutionContext.

### JobParameters Passed to JobLauncher

~~~java
JobExecution execution = jobLauncher.run(
        customerImportJob,
        parameters
);
~~~

JobLauncher takes the Job along with JobParameters and asks JobRepository to determine the corresponding JobInstance. If launch conditions are valid, Spring Batch creates a JobExecution for the run.

JobParameters are tied to the execution and stored in the metadata repository. They can be read within components of the Job, but they are not the place to store checkpoints after each chunk.

## 2. Identifying Parameters Determine the JobInstance

A JobInstance is identified by:

1. Job name.
2. Set of identifying JobParameters.

For example, the customerImportJob runs with:

~~~text
inputFile = /data/customers-01.csv
businessDate = 2026-11-15
mode = FULL
~~~

If inputFile and businessDate are marked identifying, the Job name together with those two values identifies a JobInstance.

~~~text
Job definition: customerImportJob
       |
       +-- JobInstance A
       |     inputFile=/data/customers-01.csv
       |     businessDate=2026-11-15
       |
       +-- JobInstance B
             inputFile=/data/customers-02.csv
             businessDate=2026-11-15
~~~

Two different input files produce two different JobInstances because inputFile is an identifying parameter.

If only mode changes from FULL to DELTA and mode is non-identifying, the JobInstance keeps the same identity. The mode value is still part of the execution's JobParameters, but it does not create a new JobInstance.

### Why Does JobInstance Identity Matter?

Spring Batch uses JobInstance to manage history and restarts:

- If a JobInstance is currently running, a duplicate launch request may be rejected.
- If a JobInstance has already completed, running again with the same identifying parameters is usually rejected because that instance is already finished.
- If a JobInstance failed or stopped and is restartable, the next run uses the same identifying parameters to continue the old instance.
- If an identifying parameter changes, the request belongs to a new JobInstance and does not use the old instance's checkpoints.

Therefore, choose identifying parameters according to the business unit of work to process. If each file is a separate unit of work, file code or file path can be an identifying parameter. If each reconciliation day is a separate unit of work, businessDate can participate in identity.

Do not use a randomly incremented parameter as identifying merely to bypass duplicate-run errors if the real goal is to restart the old Job. Doing so creates a new JobInstance and does not restore the state of the unfinished instance.

## 3. When Are Non-Identifying Parameters Used?

A non-identifying parameter is stored alongside the execution but does not affect JobInstance identity.

Example:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFile", "/data/customers.csv", true)
        .addString("notificationMode", "EMAIL", false)
        .toJobParameters();
~~~

In the example, notificationMode does not alter the JobInstance. This parameter can control how notifications are sent or how logging is formatted if doing so does not alter the meaning of the processed business data.

Be careful when choosing non-identifying parameters. If a value alters the dataset, calculation rules, or business outcome, omitting it from identity can cause two distinct requests to be treated as the same JobInstance.

For example, if mode=FULL and mode=DELTA produce two different business outcomes for the same file and processing date, consider whether mode should be an identifying parameter. The decision depends on how the application defines a logical processing unit.

Also keep meaningful parameters consistent on restart. Even if a parameter is non-identifying, changing it between a failed run and a restart can still change the outcome. JobInstance identity and business consistency are two separate concerns to evaluate.

## 4. What Is ExecutionContext?

ExecutionContext is a key-value data storage area bound to an execution. Unlike JobParameters, ExecutionContext can be updated while the Job or Step is running.

Example:

~~~java
ExecutionContext context = stepExecution.getExecutionContext();

context.putLong("lastCustomerId", 98765L);
context.putInt("processedCount", 500);
context.putString("outputFile", "/data/result-part-01.csv");
~~~

These values can represent:

- The position the reader has processed up to.
- The last ID read.
- The number of completed records.
- The name of a temporary file being created.
- An intermediate status code.
- Information that needs to be passed from one Step to another.

ExecutionContext is not a local variable existing only within a single method. Spring Batch persists its state to JobRepository during the execution lifecycle to support restart and resuming work.

Values put into ExecutionContext must be compatible with the serialization mechanism configured for JobRepository. Prefer simple, small, and stable data types such as Strings, numbers, booleans, dates/times, or IDs. Avoid storing large object graphs, connections, streams, services, or non-serializable objects.

## 5. Two ExecutionContext Scopes

Spring Batch has ExecutionContext at two levels:

| Scope | Belongs to | Purpose |
|---|---|---|
| Job ExecutionContext | JobExecution | Stores state shared between Steps within one Job run |
| Step ExecutionContext | StepExecution | Stores private state of one Step, typically used for checkpoints |

### Job ExecutionContext

Job ExecutionContext is bound to a JobExecution. It is suitable for data that a subsequent Step needs to use.

Examples:

- The first Step determines the normalized file name.
- The next Step needs to know that file name.
- A summary Step records the ID of the generated report.
- Later Steps need to know the processing period code or intermediate results.

### Step ExecutionContext

Step ExecutionContext is bound to a StepExecution. It is suitable for state meaningful only within that Step's scope.

Examples:

- Which line of the file the reader is on.
- The last ID read.
- The current page of a paging reader.
- The number of items processed in the Step.
- Internal state needing restoration when the Step restarts.

Do not store all data in Job ExecutionContext. If data only serves a reader's checkpoint, keep it in Step ExecutionContext to avoid bloating the Job context and making it hard to understand.

## 6. Lifecycle and State Persistence Capability

When a Job starts, Spring Batch creates a JobExecution. Each executed Step creates a corresponding StepExecution. Each object has its own ExecutionContext.

~~~text
JobParameters
     |
     v
JobLauncher
     |
     v
JobRepository
     |
     v
JobInstance
     |
     v
JobExecution
  + Job ExecutionContext
     |
     +--> StepExecution A
     |       + Step ExecutionContext A
     |
     +--> StepExecution B
             + Step ExecutionContext B
~~~

With a chunk Step, Step ExecutionContext state is typically updated at checkpoint boundaries when a chunk completes. When the chunk commits, required state can be persisted alongside Step metadata per transaction configuration.

When a Job restarts:

1. Spring Batch locates the JobInstance by Job name and identifying JobParameters.
2. The repository retrieves metadata from previous executions.
3. Completed Steps are typically skipped, unless configured to allow re-running.
4. Incomplete or failed Steps are restarted according to saved state.
5. Readers or writers supporting ItemStream reopen with the previous ExecutionContext.
6. The Step resumes from the checkpoint that the processing component can restore.

If the metadata repository only stores in memory and the process has terminated, state may be lost. To restart across fresh application startups, a durable JobRepository is needed, typically a database-backed repository.

## 7. Direct Comparison: JobParameters vs. ExecutionContext

| Criterion | JobParameters | ExecutionContext |
|---|---|---|
| Purpose | Run inputs | Runtime state during execution |
| When created | Before the Job launches | Created and updated during execution |
| Changes while Job runs? | No; the parameter object is immutable | Yes; a mutable state storage area |
| Identifies JobInstance? | Identifying parameters do | No |
| Scope | Bound to JobExecution | JobExecution or StepExecution |
| Used for checkpoints? | Not a checkpoint mechanism | Yes |
| Shared between Steps? | Steps can read the same input parameters | Job context can hold shared data |
| Restart | Uses identifying parameters to find JobInstance | Restores saved progress and state |
| Examples | inputFile, businessDate, tenantId | lastReadId, currentLine, generatedFile |

A practical rule:

- Data known before running that describes the processing request: JobParameters.
- Data generated or changing while running: ExecutionContext.
- Reader/writer state for restart: Step ExecutionContext.
- Intermediate data needed by a later Step: Job ExecutionContext.

## 8. Example: JobParameters for Input, ExecutionContext for Progress

Suppose a Job imports customer files. JobParameters hold the file path and business date. The reader stores the last read ID in Step ExecutionContext.

### Launching the Job with JobParameters

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/customers.csv", true)
        .addString("businessDate", "2026-11-15", true)
        .toJobParameters();

JobExecution execution =
        jobLauncher.run(customerImportJob, parameters);
~~~

### Reader Receiving JobParameters

StepScope can be used to inject parameters when the Step starts:

~~~java
@Bean
@StepScope
public FlatFileItemReader<RawCustomer> customerReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {

    return new FlatFileItemReaderBuilder<RawCustomer>()
            .name("customerReader")
            .resource(inputFile)
            .delimited()
            .names("id", "name", "email")
            .targetType(RawCustomer.class)
            .saveState(true)
            .build();
}
~~~

Here inputFile is fixed input data for the run. The reader can use it to open the exact file. saveState(true) allows the reader to save its own state into ExecutionContext to support restart.

### Saving Progress in Step ExecutionContext

A component can update processing state:

~~~java
public class ProgressListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        ExecutionContext context =
                stepExecution.getExecutionContext();

        context.putLong(
                "lastReadCount",
                stepExecution.getReadCount());

        return stepExecution.getExitStatus();
    }
}
~~~

The example above illustrates writing a value to Step ExecutionContext. In a real application, the listener must be registered with the Step and update state at an appropriate point. For reader checkpoints, let the reader implement ItemStream and save its read position itself via open/update rather than using a listener to guess position.

## 9. Moving Data from Step Context to Job Context

One Step may produce data that the next Step needs to use. That data can be stored in Job ExecutionContext.

For example, a Step creates a report and wants to pass reportId to a notification Step:

~~~java
public class CreateReportTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        StepExecution stepExecution = chunkContext
                .getStepContext()
                .getStepExecution();

        stepExecution.getExecutionContext()
                .putLong("reportId", 12345L);

        return RepeatStatus.FINISHED;
    }
}
~~~

The code above stores reportId in Step ExecutionContext. To make it available to the next Step as shared Job-level data, **ExecutionContextPromotionListener** can be used.

~~~java
@Bean
public ExecutionContextPromotionListener reportContextPromotionListener() {
    ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();

    listener.setKeys(new String[] {"reportId"});
    return listener;
}
~~~

Register the listener with the report creation Step:

~~~java
@Bean
public Step createReportStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ExecutionContextPromotionListener reportContextPromotionListener) {

    return new StepBuilder("createReportStep", jobRepository)
            .tasklet(new CreateReportTasklet(), transactionManager)
            .listener(reportContextPromotionListener)
            .build();
}
~~~

After the Step completes per the configured listener condition, the reportId key is promoted from Step ExecutionContext to Job ExecutionContext. The subsequent Step can read that value.

If promotion should happen only when the Step completes successfully, configure appropriate ExitStatuses for the listener instead of promoting every outcome by default. For data needed by later Steps, clearly define success conditions and how to handle cases where the prior Step fails.

## 10. Reading Job ExecutionContext and Step ExecutionContext Using Scope

In Spring Batch, scopes allow injecting runtime data into beans.

### Reading JobParameters

~~~java
@Bean
@StepScope
public ItemReader<RawCustomer> reader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {
    // Create reader according to the input file.
}
~~~

### Reading Job ExecutionContext

~~~java
@Bean
@StepScope
public ItemProcessor<RawCustomer, Customer> processor(
        @Value("#{jobExecutionContext['importMode']}") String importMode) {
    // Use shared Job data.
}
~~~

### Reading Step ExecutionContext

~~~java
@Bean
@StepScope
public ItemWriter<Customer> writer(
        @Value("#{stepExecutionContext['outputPath']}") String outputPath) {
    // Use private state of the current Step.
}
~~~

These expressions are usually used with @StepScope because the data exists only when the Step actually runs. Do not create a singleton bean at application context startup and try to read JobParameters that do not yet exist.

If a key has not been saved in the context yet, the expression may receive null or fail to resolve to the required data type. Ensure the prior Step wrote/promoted the key and the data type matches.

## 11. Using ExecutionContext for Reader Checkpoints

A restartable reader typically implements ItemStream. Three main methods:

- open(ExecutionContext): restores saved state or initializes new state.
- update(ExecutionContext): saves current progress at checkpoints.
- close(): releases resources.

Example of a custom reader saving the last read ID:

~~~java
public class CustomerReader implements ItemStreamReader<Customer> {

    private final CustomerRepository repository;
    private long lastId;

    public CustomerReader(CustomerRepository repository) {
        this.repository = repository;
    }

    @Override
    public void open(ExecutionContext context) {
        lastId = context.getLong("lastId", 0L);
    }

    @Override
    public Customer read() {
        Customer customer = repository.findNextAfter(lastId);

        if (customer != null) {
            lastId = customer.getId();
        }

        return customer;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong("lastId", lastId);
    }

    @Override
    public void close() {
        // Close resources if the reader opens resources itself.
    }
}
~~~

In the example:

- lastId is state that changes with read progress.
- open() restores lastId from ExecutionContext.
- read() retrieves the next record.
- update() saves the current position at checkpoints.

When the Job restarts, a new reader is opened with the saved context and can resume from the corresponding ID.

In a real application, the findNextAfter query must have a stable order, unique key, and repeatable pagination conditions. If the data source changes between the initial run and restart, saving only the last ID may not be enough to guarantee the exact same dataset.

## 12. Do Not Use JobParameters to Store Progress

A design mistake is trying to turn JobParameters into a mutable state store:

~~~java
// There is no API to update JobParameters like this.
parameters.addLong("lastProcessedId", lastId);
~~~

JobParameters is not a mutable map for a Step to update after every chunk. If you want to save the last processed ID, use Step ExecutionContext.

Conversely, do not put inputFile or businessDate into ExecutionContext merely because key-value pairs can be written there. Those values are already inputs of the run and may participate in identifying the JobInstance; keep them in JobParameters.

Using the right mechanism keeps metadata clear:

- JobParameters represents the execution request.
- ExecutionContext represents execution state.
- JobInstance represents a logical processing unit.
- JobExecution represents a specific execution attempt.

## 13. Restart: How Do the Two Mechanisms Work Together?

When restarting a JobInstance, Spring Batch needs both JobParameters and ExecutionContext.

Example:

~~~text
Job: customerImportJob
JobParameters:
  inputFile=customers.csv (identifying)
  businessDate=2026-11-15 (identifying)

JobInstance A
  |
  +-- JobExecution 1: FAILED
  |      |
  |      +-- Step importCustomersStep
  |             Step ExecutionContext:
  |               lastId=200
  |
  +-- JobExecution 2: RESTART
         |
         +-- Reuse JobInstance A
         |
         +-- Reader opens with checkpoint lastId=200
                |
                v
           Continue after ID 200
~~~

JobParameters identifies which JobInstance needs to be restarted. ExecutionContext stores Step progress so readers/writers can restore.

If inputFile is changed to a different file and inputFile is an identifying parameter, the new request creates a different JobInstance. The old JobInstance's context is not used for the new run.

If only a non-identifying parameter changes, the JobInstance identity may remain the same. However, if that value alters how data is processed, restart may produce inconsistent results. Therefore, do not look solely at the identifying flag; evaluate the business meaning of each parameter.

## 14. Job Context Does Not Replace Step Context

It is possible to store everything in Job ExecutionContext, but doing so usually makes state hard to manage.

For example, a reader stores currentLine in the Job context. If the Job has two Steps that both read files, the currentLine key may collide or be overwritten by the other Step.

A clearer division:

| Data | Appropriate storage location |
|---|---|
| Input file path | JobParameters |
| Business date | JobParameters |
| Processing mode specified at launch | JobParameters |
| Step A's file read position | Step A ExecutionContext |
| Step B's reader current page | Step B ExecutionContext |
| Report ID needed by the email-sending Step | Job ExecutionContext |
| Intermediate result shared across multiple Steps | Job ExecutionContext |
| Counter serving a Step's private checkpoint | Step ExecutionContext |

Job context fits state shared between Steps within the same JobExecution. Step context fits the private progress of a single StepExecution.

## 15. ExecutionContext Is Not a Place for Large Business Data

ExecutionContext is persisted alongside execution metadata. Therefore, putting large object graphs into the context can bloat metadata, increase serialization/deserialization costs, and impact restart time.

For example, do not store the entire customer list:

~~~java
context.put("allCustomers", customers);
~~~

Instead, store an ID or reference location:

~~~java
context.putLong("stagingBatchId", stagingBatchId);
context.putString("outputFile", outputFilePath);
~~~

When the data is needed, the next Step reloads it from the database or file using that ID.

Also avoid storing objects that cannot be serialized or are tied to resource lifecycles, such as:

- Connection or DataSource.
- BufferedReader or BufferedWriter.
- HTTP clients/sessions not designed to be serialized.
- Spring beans or proxies.
- Threads, executors, or locks.
- Large entity graphs with circular relationships.

ExecutionContext should hold small, restorable state that is meaningful on restart.

## 16. Naming Keys and Avoiding Collisions

ExecutionContext is a key-value map. When multiple components store state, name keys with clear namespaces or reader/step names.

Example:

~~~java
context.putLong("customerReader.lastId", lastId);
context.putString("reportStep.outputPath", outputPath);
context.putInt("validationStep.invalidCount", invalidCount);
~~~

Avoid generic keys like current, status, or count if multiple components might write to the same context.

With Step ExecutionContext, keys should still have clear names for easy diagnosis in metadata. With Job ExecutionContext, take special care to avoid collisions between Steps since it is a shared state area.

Do not arbitrarily rename keys across application versions if old JobInstances might be restarted with new code. If context structure changes, consider backward compatibility or a migration/default-value mechanism.

## 17. JobParameters and ExecutionContext in Tests

When testing a Job, verify both inputs and execution state.

Example running a Job with JobParameters:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/tmp/customers.csv", true)
        .addString("businessDate", "2026-11-15", true)
        .toJobParameters();

JobExecution execution =
        jobLauncherTestUtils.launchJob(parameters);

assertEquals(BatchStatus.COMPLETED, execution.getStatus());

assertEquals(
        "/tmp/customers.csv",
        execution.getJobParameters().getString("inputFile"));
~~~

Step ExecutionContext can be inspected:

~~~java
StepExecution stepExecution = execution.getStepExecutions()
        .stream()
        .filter(step -> "importCustomersStep".equals(step.getStepName()))
        .findFirst()
        .orElseThrow();

ExecutionContext context = stepExecution.getExecutionContext();

assertEquals(
        200L,
        context.getLong("lastCustomerId"));
~~~

Specific assertions depend on the reader and the keys the application saves. With built-in readers, internal keys may differ; test via APIs or restart behavior instead of coupling tests to unstable implementation details.

### Testing identifying parameters

A dedicated test should verify:

- Same Job name and same identifying parameters produce the same JobInstance.
- Changing an identifying parameter creates a different JobInstance.
- Changing a non-identifying parameter does not change JobInstance identity.
- A completed JobInstance cannot be re-run as a new instance with the same identifying parameters.
- Restarting a failed JobInstance reuses the exact identifying parameters and restores checkpoints.

## 18. Common Mistakes

### Using ExecutionContext instead of JobParameters

File paths and business dates known before running should be passed via JobParameters. If stored only in the context, JobInstance identity does not reflect the true unit of work.

### Using JobParameters to store checkpoints

JobParameters is not a mutable data area. Reader position, last ID, or processed chunk count belong in ExecutionContext.

### Putting all state into Job context

Private reader/Step state belongs in Step ExecutionContext. If Job context is used for everything, Steps may overwrite each other's keys and independent restarts become difficult.

### Thinking non-identifying parameters do not matter

They do not determine JobInstance identity, yet they can still change how data is processed. Keep these values consistent on restart if they affect outcomes.

### Storing large objects in ExecutionContext

The context is persisted in the metadata repository. Large object graphs increase save, read, and restart costs. Store IDs or reference locations.

### Thinking Job context automatically receives every value from Step context

Step context and Job context are two separate scopes. To share keys from Step to Job, use promotion or update Job ExecutionContext intentionally.

### Thinking restart only needs ExecutionContext

Spring Batch must identify the exact JobInstance using JobParameters first, and only then restores the corresponding ExecutionContext.

## 19. How to Choose the Right Storage Location

When designing a Job, classify each value:

1. Is the value available before the Job starts and describes the processing request? Use JobParameters.
2. Does the value participate in identifying an independent business unit? Mark it identifying.
3. Does the value only control how to run without creating a new processing unit? Consider non-identifying.
4. Does the value arise during processing and need to resume after restart? Use ExecutionContext.
5. Does the state serve only a single Step? Use Step ExecutionContext.
6. Is it an intermediate result needed by a later Step? Use Job ExecutionContext or promotion.
7. Is it large data or primary business data? Store in a database/file; context holds only a reference ID.
8. Does the value need to remain stable on restart? Check both identifying and non-identifying JobParameters along with the data source.

Clearly distinguishing the two mechanisms gives Jobs accurate identity and reliable recovery capability. JobParameters describes the execution request and identifies the JobInstance through identifying parameters. ExecutionContext stores state changing during execution at the Job or Step level. When used in the right scope, Spring Batch can both know which job it is processing and restore how far that job has progressed.
