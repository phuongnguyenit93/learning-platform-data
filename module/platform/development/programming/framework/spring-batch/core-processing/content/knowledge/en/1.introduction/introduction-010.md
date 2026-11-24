# Components You Will Encounter in a Spring Batch Application

Spring Batch is Spring's framework for batch processing tasks. A batch application usually has to read a large volume of data, validate or transform it, write the results to another system, and be able to continue running after hitting an error. Spring Batch provides components to organize the work, orchestrate each processing step, manage transactions, and store execution state.

When reading a Spring Batch application, you will commonly encounter the following groups of components:

- **Job and Step** describe the work to be done and the steps that make up that work.
- **JobLauncher and JobRepository** launch the work and store execution information.
- **ItemReader, ItemProcessor, and ItemWriter** take care of reading, processing, and writing each group of data.
- **PlatformTransactionManager and ExecutionContext** support transactions and state saving so the job can be restarted.
- **Listeners, scopes, and management tools** let you add behavior at appropriate points and operate jobs more conveniently.

## 1. The Big Picture

A basic processing flow can be pictured as follows:

```text
User / Scheduler / API
             |
             v
        JobLauncher
             |
             v
            Job
             |
       +-----+------+
       |            |
       v            v
     Step 1       Step 2       ...
       |
       v
  ItemReader
       |
       v
 ItemProcessor (optional)
       |
       v
  ItemWriter

JobLauncher, Job, and Step work with the JobRepository
to store metadata and execution state.
The Step uses the TransactionManager to manage transactions.
```

For example, an order import job can consist of three steps: read and validate the input file, write the orders to the database, and then generate a result report. Each step can use a different processing approach. The data import step usually uses the chunk model with a reader, processor, and writer; the report-generation step can use a simple tasklet.

## 2. Job: A Complete Batch Task

A `Job` is the highest-level unit of work in Spring Batch. A Job describes a named batch process, consisting of one or more steps, and can have control branches depending on execution results.

Examples of jobs:

- `importCustomerJob`: imports customer data from a file.
- `dailySettlementJob`: reconciles transactions at the end of the day.
- `archiveOrderJob`: moves old orders to an archive area.

A Job is usually declared as a Spring bean. A Job does not directly read each line of data; it orchestrates the steps that carry out the specific work.

### JobInstance and JobExecution

These two concepts are easy to confuse:

| Component | Meaning |
|---|---|
| `Job` | The definition of the work, for example `dailySettlementJob`. |
| `JobInstance` | A logical run of a job, determined by the job name and the identifying job parameters. |
| `JobExecution` | One specific execution of a JobInstance. A JobInstance can have multiple JobExecutions if the previous run failed and was restarted. |

Suppose `dailySettlementJob` runs with the business-date parameter `2026-11-15`. The combination of the job name and that date identifying parameter determines a JobInstance. If the first run fails, rerunning with the same identifying parameters creates a new JobExecution belonging to the same JobInstance. If it runs with a different business date, Spring Batch determines a different JobInstance.

Therefore, `JobInstance` answers the question “which data set or business period is this work for?”, while `JobExecution` answers the question “how did this specific execution go?”.

## 3. JobParameters: Input Data at Launch

`JobParameters` is the set of parameters passed in when launching a job. They are commonly used to specify the input file, the processing date, a customer code, or a data range.

Example:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "data/orders.csv", true)
        .addString("businessDate", "2026-11-15", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
```

A parameter with the `identifying` flag set to `true` participates in determining the JobInstance. The `requestedBy` parameter in the example above has the value `false`, so it does not change the JobInstance identity. The choice of identifying parameters should be based on business meaning: two runs with the same identifying parameters are considered the same logical processing run and can be involved in the restart mechanism.

You should not add a randomly changing identifying parameter to every run if the goal is to restart the specific JobInstance that failed. Conversely, if you want to deliberately create a new JobInstance, you need to pass in an appropriate new set of identifying parameters.

## 4. Step and StepExecution

A `Step` is an independent phase within a Job. A job can consist of one step or multiple steps that are chained, branched, or run according to a configured flow.

Example of an order import process:

1. `readOrdersStep`: reads and validates the input data.
2. `writeOrdersStep`: writes the valid data to the database.
3. `createSummaryStep`: generates statistics after the data import.

A `StepExecution` stores information about one execution of a step, such as the status, the start and end times, and the number of items read, written, skipped, or committed. When a JobExecution runs through multiple steps, each step that is executed has corresponding StepExecution information.

A Step is usually built in one of two main styles:

- **Chunk-oriented step**: reads and processes data in groups of items.
- **Tasklet step**: performs a task in one or more tasklet calls.

## 5. Chunk Processing: Read, Process, and Write in Groups

Chunk processing is the most common model when processing data in bulk. In this model, Spring Batch reads item by item, optionally transforms the items, gathers the items into a chunk, and then writes that chunk.

The three main components are:

### ItemReader

`ItemReader<T>` reads data and returns items of type `T` one at a time. Each time Spring Batch calls `read()`, the reader returns one item. When the data is exhausted, the reader returns `null` to signal the end.

Some commonly seen readers:

- `FlatFileItemReader`: reads data from a text file such as a CSV or a character-delimited file.
- `JdbcCursorItemReader`: reads JDBC query results in cursor style.
- `JdbcPagingItemReader`: reads data page by page, suitable for some large-data queries.
- `RepositoryItemReader`: reads data through a Spring Data repository.

The reader is responsible for fetching data and converting the source data into items that the subsequent steps can use. Checking business rules is usually placed in the processor for a clear separation of responsibilities.

### ItemProcessor

`ItemProcessor<I, O>` receives an item of type `I`, processes it, and returns an item of type `O`. The input and output types can be the same or different.

A processor is commonly used to:

- Normalize data, for example removing whitespace or normalizing codes.
- Check business conditions and add necessary information.
- Convert an input record into an object that fits the target system.

A processor can return `null` to filter an item out of the chunk being written. This is filter behavior; it differs from throwing an exception to report a processing error. If you do not need to transform or filter data, the processor can be omitted.

### ItemWriter

`ItemWriter<T>` receives a group of processed items and writes them to the destination, such as a database, a file, or another service.

Some commonly seen writers:

- `JdbcBatchItemWriter`: writes data using JDBC batch.
- `FlatFileItemWriter`: writes data to a file.
- `RepositoryItemWriter`: writes through a Spring Data repository.

In Spring Batch 5, the `write` method receives a `Chunk` of items. When reading code from older versions, you may encounter a different method signature, because the writer API has changed across versions.

### Chunk Size and the Transaction Boundary

Suppose the chunk size is configured as `100`. Spring Batch reads up to 100 items, runs the processor on those items if there is one, calls the writer to write the group of data, and then commits the transaction. After that, the framework continues with the next chunk.

```text
Read items 1 ... 100
        |
        v
Process the items (if there is a processor)
        |
        v
Write a chunk of up to 100 items
        |
        v
Commit the transaction
        |
        v
Read the next chunk
```

The last chunk may have fewer items than the configured size. When the reader returns `null`, the step ends after completing the writing and commit of the remaining chunk.

Chunk size affects the number of commits, the amount of data within one transaction, and memory usage. A chunk that is too small can increase commit overhead; a chunk that is too large can make transactions long and require more resources. The appropriate value depends on the reader/writer speed, the item size, the database, and the recovery requirements.

## 6. Tasklet: Performing a Single Task

A `Tasklet` suits work that does not need to read and write item by item in chunks, for example:

- Deleting temporary files.
- Creating a directory or preparing input data.
- Running an update statement or a stored procedure.
- Performing a simple aggregation operation.

A tasklet implements the `execute` method. The method returns `RepeatStatus.FINISHED` when done or `RepeatStatus.CONTINUABLE` when it needs to be called again. In a `TaskletStep`, Spring Batch manages the transaction for each tasklet call according to the step's configuration.

Example of declaring a step that uses a tasklet:

```java
@Bean
Step cleanupStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    return new StepBuilder("cleanupStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                // Perform the cleanup work here.
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

Choose a chunk when the work processes a set of items in a read-process-write cycle. Choose a tasklet when the work is a single operation or a piece of processing that the application controls itself.

## 7. JobRepository: Where Spring Batch Stores Metadata

`JobRepository` is a very important infrastructure component. It stores metadata about the JobInstance, JobExecution, StepExecution, JobParameters, and ExecutionContext. Thanks to this metadata, Spring Batch can track state, report results, and support restart.

In a real application, the JobRepository is usually configured to store data in a database through Spring Batch's metadata tables. These tables are different from the business tables that the application uses to store orders, customers, or transactions.

For example, an application can have:

- A business database containing the `orders` table.
- Spring Batch's metadata tables containing job, step, execution, and checkpoint state information.

The two groups of data can live in the same database or in different databases, depending on configuration. You need to make sure the metadata schema has been initialized correctly for the Spring Batch version in use and that the datasource/transaction manager are configured consistently.

`JobRepository` is not where all the input data or the processed business data is stored. It stores the execution management information and state the framework needs.

## 8. JobLauncher: Launching a Job

`JobLauncher` receives a Job together with `JobParameters` and asks Spring Batch to execute that job. The caller can be an application, a REST endpoint, a scheduler, or another orchestration component.

Example:

```java
JobExecution execution = jobLauncher.run(importJob, parameters);
```

The JobLauncher works with the JobRepository to create or find the JobInstance, record the JobExecution, and begin the execution process. Whether execution is synchronous or asynchronous depends on the configuration of the launcher and the executor used.

When launching, the application may encounter cases such as a job of the same JobInstance already running, a JobInstance that has already completed, or invalid parameters. Therefore, the place that calls the JobLauncher needs to handle the appropriate exceptions and record the launch result.

## 9. JobExplorer, JobOperator, and JobRegistry

These are components that support job lookup and management when the application has richer operational needs.

| Component | Role |
|---|---|
| `JobExplorer` | Looks up stored metadata, for example finding a JobInstance, JobExecution, or StepExecution and viewing the execution state. |
| `JobOperator` | Provides higher-level job operational actions, such as launching, restarting, or requesting a stop of an execution, via the APIs supported by the version. |
| `JobRegistry` | Registers and looks up Jobs by name; useful when jobs are registered or selected dynamically. |

Not every application needs to call all three of these components directly. For a small application, JobLauncher and JobRepository may be enough for the basic run flow. When you need a monitoring screen, an administrative endpoint, or a dynamic orchestration mechanism, JobExplorer, JobOperator, and JobRegistry become more useful.

## 10. PlatformTransactionManager: Managing Transactions

In chunk processing, Spring Batch needs to determine when to begin, commit, or roll back a transaction. `PlatformTransactionManager` is Spring's abstraction used to manage those transactions.

A step usually receives a transaction manager that matches the resource the step uses. For example, if the writer writes to a relational database through JDBC, the transaction manager must manage that datasource correctly.

When a chunk fails before commit, the chunk's transaction can be rolled back. This helps avoid a half-written state in resources managed by the transaction. However, if the processor or writer calls an external system that does not participate in the same transaction, the external operation may not be automatically undone. When integrating multiple systems, you need to design appropriate error handling, retry, and idempotency.

## 11. ExecutionContext: Storing State to Continue Processing

`ExecutionContext` is a key-value store attached to a JobExecution or StepExecution. Spring Batch uses it to store the state needed between executions, especially the checkpoint information of readers that support restart.

For example, a reader can store the position it has read in a file. If the step fails after some chunks have been committed, a restart can use the saved state to continue from the appropriate position instead of reading from the beginning.

There are two commonly seen scopes:

- **Job ExecutionContext**: state at the whole-job scope, which later steps can use.
- **Step ExecutionContext**: the state of one particular step, commonly used for the checkpoint of a reader or writer in that step.

The ExecutionContext is stored together with the execution metadata in the JobRepository. You should store only small values that are necessary to continue the work; do not put an entire large data set in here. The values need to be supported by Spring Batch's serializer.

## 12. Listeners: Hooks at Points in the Lifecycle

Listeners let the application run additional logic when an event occurs in a job or step. They are useful for logging, timing, audit recording, or sending status information.

Some commonly seen listeners:

| Listener | When it is used |
|---|---|
| `JobExecutionListener` | Before and after a JobExecution runs. |
| `StepExecutionListener` | Before and after a StepExecution runs. |
| `ChunkListener` | Before and after a chunk, or when a chunk encounters an error, via the corresponding callbacks. |
| `ItemReadListener` | Before/after reading an item or when reading encounters an error. |
| `ItemProcessListener` | Before/after processing an item or when processing encounters an error. |
| `ItemWriteListener` | Before/after writing a chunk or when writing encounters an error. |

For example, a `JobExecutionListener` can record the start time in `beforeJob` and record the result in `afterJob`. A listener should focus on supporting behavior. The main business rules and control flow should be placed in the appropriate job, step, tasklet, or processor.

## 13. @StepScope and @JobScope

Some beans need to be created with data that is only available when the job starts, such as a file path in the JobParameters or a value stored in the ExecutionContext. `@StepScope` and `@JobScope` help defer bean initialization so that values can be accessed according to the execution scope.

- `@StepScope` creates the bean within the scope of one step execution. This is a common choice for a reader, processor, or writer that needs step parameters.
- `@JobScope` creates the bean within the scope of one job execution. It suits objects that need to be shared within the job scope and need to access job parameters or the job execution context.

For example, a reader can receive the file name from a job parameter using a late-binding expression:

```java
@Bean
@StepScope
FlatFileItemReader<String> inputReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {
    // Configure the reader to use inputFile here.
    return new FlatFileItemReaderBuilder<String>()
            .name("inputReader")
            .resource(new FileSystemResource(inputFile))
            .lineMapper((line, lineNumber) -> line)
            .build();
}
```

Because bean scope is tied to the execution lifecycle, you need to declare these beans in a way that Spring Batch can manage the scope. You should not read JobParameters while creating an ordinary singleton bean if that value only exists when the job is launched.

## 14. Example Assembling a Job, Step, and Chunk Components

The example below illustrates configuration using the Spring Batch 5 API or later. The `reader` and `writer` are assumed to be beans declared elsewhere; the example focuses on how to assemble the components into a job.

```java
@Configuration
public class ImportJobConfiguration {

    @Bean
    Job importJob(JobRepository jobRepository, Step importStep) {
        return new JobBuilder("importJob", jobRepository)
                .start(importStep)
                .build();
    }

    @Bean
    Step importStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<String> reader,
            ItemProcessor<String, String> processor,
            ItemWriter<String> writer) {

        return new StepBuilder("importStep", jobRepository)
                .<String, String>chunk(100, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .build();
    }

    @Bean
    ItemProcessor<String, String> normalizeProcessor() {
        return String::trim;
    }
}
```

In the example:

1. `importJob` defines a job named `importJob` that starts with `importStep`.
2. `importStep` is a chunk-oriented step with a chunk size of 100.
3. `reader` supplies the input strings one at a time.
4. `normalizeProcessor` removes leading and trailing whitespace from the string.
5. `writer` receives the processed strings in each chunk and writes them to the destination.
6. The `JobRepository` stores metadata; the `PlatformTransactionManager` manages the transaction for the chunk.

When launching, the caller creates the JobParameters and then passes the job and the parameters to the JobLauncher:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "data/input.txt", true)
        .addString("businessDate", "2026-11-15", true)
        .toJobParameters();

JobExecution execution = jobLauncher.run(importJob, parameters);
```

This configuration snippet assumes that the `JobRepository`, `PlatformTransactionManager`, `JobLauncher`, and the reader/writer beans have been configured in the application context. The specific infrastructure configuration depends on whether the application uses Spring Boot or configures Spring Batch directly, as well as the framework version.

## 15. What Happens When a Job Fails and Is Restarted?

Restartability is an important reason to use Spring Batch. When a job fails, the metadata in the JobRepository tells you which JobInstance, JobExecution, and steps have run, and what the current state is. The ExecutionContext can contain checkpoints saved at commit boundaries.

When restarting with the same identifying JobParameters, Spring Batch can create a new JobExecution for the existing JobInstance and continue according to the job/step restart rules. A step that has completed can be skipped in the restart if the configuration and state allow; a step that failed can be rerun. The ability to continue accurately also depends on the reader/writer, the checkpoint, the transaction, and the application's design.

Some principles to remember:

- Choose identifying JobParameters that accurately reflect one business unit of work.
- Use readers/writers that can save and restore state when you need restart.
- Design write operations to be idempotent when part of the work may have to be redone.
- Do not assume that every call to an API or an external system is rolled back along with the database transaction.
- Distinguish restarting a failed JobInstance from creating a new JobInstance with different identifying parameters.

## 16. Distinguishing Easily Confused Components

| Pair of concepts | How to distinguish |
|---|---|
| `Job` and `JobInstance` | A Job is a definition; a JobInstance is one logical processing run determined by the identifying parameters. |
| `JobInstance` and `JobExecution` | A JobInstance can have multiple JobExecutions across runs or restarts. |
| `Step` and `StepExecution` | A Step is the definition of a phase; a StepExecution is one execution of that phase. |
| `ItemProcessor` and `ItemWriter` | The processor transforms or filters each item; the writer writes the processed items in chunks. |
| Chunk and Tasklet | A chunk organizes read-process-write in groups; a tasklet performs a task defined by the application. |
| `JobRepository` and `ExecutionContext` | The JobRepository stores execution metadata; the ExecutionContext is a key-value state store belonging to an execution and saved through the repository. |
| `JobLauncher` and `JobOperator` | The JobLauncher launches a job; the JobOperator provides additional job management actions at the operational level. |

When reading a Spring Batch application, start from the `Job` bean to see which steps the process consists of. Then open each `Step` to determine whether the step uses a chunk or a tasklet, where the reader gets its data, which rules the processor applies, and where the writer writes. Finally, look at the JobParameters, the JobRepository, the transaction manager, and the listeners to understand how the job is launched, monitored, and recovered when errors occur.
