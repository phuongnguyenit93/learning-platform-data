# From Which Checkpoint Can a Step Restart?

In Spring Batch, a Step can resume from the **most recent checkpoint that was saved successfully**. For a Step that processes by chunk, the checkpoint usually corresponds to the chunk's commit boundary. If a chunk encounters an error before committing, that chunk's transaction is rolled back, and the data in the chunk may be read and processed again when the Job restarts.

A checkpoint is not a position that Spring Batch guesses from a line number or run time. It is state that the reader, the writer, or the application's logic saves into the **ExecutionContext**, which the **JobRepository** then maintains so that the next execution can recover it.

## 1. What Is a Checkpoint?

A checkpoint is a saved state milestone that lets a Step continue its work after being interrupted. It describes the portion of progress that the framework and the processing components can recover.

Suppose a Step reads a CSV file and writes customers to the database in chunks of 100 records:

~~~text
Chunk 1: lines 1   - 100   -> written successfully -> COMMIT
Chunk 2: lines 101 - 200   -> written successfully -> COMMIT
Chunk 3: lines 201 - 300   -> processing           -> error, ROLLBACK
~~~

If the application encounters an error in chunk 3, the most recent checkpoint is still the one after chunk 2. On restart, the Step continues from the state saved after chunk 2. The records belonging to chunk 3 may be read and processed again.

~~~text
Data source
     |
     v
[1 - 100]   COMMIT  <--- checkpoint 1
     |
     v
[101 - 200] COMMIT  <--- checkpoint 2
     |
     v
[201 - 300] ERROR
             |
             +---- ROLLBACK
                      |
                      v
                  RESTART
                      |
                      v
                Continue from checkpoint 2
~~~

Therefore, the usual answer to the question “From which checkpoint does a Step restart?” is: **from the last checkpoint that was saved and committed successfully**, not from the last item that the program started reading.

The specific way of recovery depends on the type of Step, whether the reader/writer supports saving state, and whether the application saves custom checkpoints.

## 2. Where Does the ExecutionContext Store Checkpoints?

Spring Batch uses **ExecutionContext** to store state data as key-value pairs. There are two commonly encountered scopes:

| Scope | Owning object | Purpose |
|---|---|---|
| Job ExecutionContext | JobExecution | Stores data that needs to be shared between Steps in the same Job run |
| Step ExecutionContext | StepExecution | Stores the Step's own state, commonly used for read/write positions and checkpoints |

A reader's checkpoint usually lives in the Step ExecutionContext because the read progress belongs to the Step being executed.

With a JobRepository that uses a database, Spring Batch stores the ExecutionContexts in the metadata repository, usually in:

- **BATCH_JOB_EXECUTION_CONTEXT**: the ExecutionContext of the JobExecution.
- **BATCH_STEP_EXECUTION_CONTEXT**: the ExecutionContext of the StepExecution.

For example, a Step ExecutionContext can contain data such as:

~~~text
{
    "customerReader.current.count": 200,
    "customerReader.read.count": 200,
    "lastProcessedCustomerId": 98765
}
~~~

The actual keys depend on the reader, the writer, or the logic implemented by the application. Do not rely on the internal key names of a specific reader; treat the ExecutionContext as the state-saving contract of that component.

### What Is the Role of the JobRepository?

An ExecutionContext that exists only in the memory of a Java object is not enough to restart after the application process ends. The state must be saved through the JobRepository.

In an environment that needs to restart after the application is shut down or the server reboots, use a JobRepository that can store metadata durably, usually a database-based repository. A repository that stores only in memory will lose its data when the process ends and cannot provide a checkpoint for a new run afterward.

## 3. A Chunk Step Restarts from the Commit Boundary

With chunk-oriented processing, Spring Batch reads and processes data in groups. Each chunk is processed in a transaction; when a chunk succeeds, the transaction is committed and the corresponding checkpoint is updated.

An example of a Step with a chunk size of 100:

~~~java
@Bean
public Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<RawCustomer> customerReader,
        ItemProcessor<RawCustomer, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<RawCustomer, Customer>chunk(100, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}
~~~

Suppose the reader reads a file with 1,000 lines:

| Chunk | Data | Result | Most recent checkpoint |
|---|---:|---|---:|
| 1 | 1–100 | Commit succeeded | After line 100 |
| 2 | 101–200 | Commit succeeded | After line 200 |
| 3 | 201–300 | Writer encountered an error, rollback | Still after line 200 |
| 4 onward | Not yet processed | Not yet run | Still after line 200 |

On restart, the reader is restored from the state after chunk 2. Chunk 3 is performed again.

**Chunk size affects how often checkpoints are created** in the ordinary chunk model:

- Small chunk: checkpoints and commits are more frequent, and the amount of work to redo on an error is usually smaller; in exchange, transaction and commit costs may increase.
- Large chunk: fewer commits, which can improve performance in some cases; in exchange, transactions last longer and more items may have to be reprocessed when a chunk fails.

Chunk size is not a number that guarantees exactly that many records will be written. The processor can filter items by returning null, the skip policy can skip failing items, and the last chunk can be smaller than configured.

### Why Is an Uncommitted Chunk Processed Again?

Suppose chunk 3 has read 100 items, the processor has converted them, and the writer has started writing. If the writer throws an exception before the transaction commits, the changes inside the transaction are rolled back.

The previous chunk's checkpoint is still the most recent committed state. On restart, the reader restores this state and re-reads the data needed for chunk 3.

This also means the processor can be called again for the items belonging to the uncommitted chunk. Design the processor and any auxiliary operations so that being called again does not cause unintended side effects.

## 4. ItemStream and How a Reader Stores Its Read Position

Spring Batch uses the **ItemStream** contract so that stateful components can open, save, and restore state.

Three important methods:

| Method | When it is called | Responsibility |
|---|---|---|
| **open(ExecutionContext)** | When the Step opens the stream | Read the old state or initialize a new state |
| **update(ExecutionContext)** | At the time a checkpoint is updated | Write the current progress into the ExecutionContext |
| **close()** | When the Step closes the stream | Release resources |

A reader that supports restart needs to be able to restore the read position in open() and also update its state in update().

### Example with FlatFileItemReader

Built-in readers such as FlatFileItemReader support saving read state. You can configure a reader as follows:

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

Points to note:

- **name("customerReader")** sets a stable name for the reader so that its state is recognized in the ExecutionContext.
- **saveState(true)** allows the reader to save the state needed for restart.
- **@StepScope** lets the reader receive JobParameters at the time the Step runs.
- **inputFile** must point to the correct data source of the JobInstance being restarted.

With a reader that supports ItemStream, Spring Batch can call the stream lifecycle methods and save the checkpoint together with the Step's metadata.

Some readers have a saveState option. If you set **saveState(false)**, the reader does not save its restart state. In that case, the framework cannot restore the read position from a checkpoint provided by the reader; how restart is handled depends on the design of the reader and the data source, and there is often a risk of re-reading from the beginning.

### A Custom Reader Needs to Save State

If you implement a reader yourself, provide a mechanism to save and restore the position. The simple example below uses the last customer ID that was read:

~~~java
public class CustomerReader implements ItemStreamReader<Customer> {

    private long lastProcessedId;
    private CustomerRepository repository;

    public CustomerReader(CustomerRepository repository) {
        this.repository = repository;
    }

    @Override
    public void open(ExecutionContext executionContext) {
        lastProcessedId = executionContext.getLong("lastProcessedId", 0L);
    }

    @Override
    public Customer read() {
        Customer customer = repository.findNextAfter(lastProcessedId);

        if (customer != null) {
            lastProcessedId = customer.getId();
        }

        return customer;
    }

    @Override
    public void update(ExecutionContext executionContext) {
        executionContext.putLong("lastProcessedId", lastProcessedId);
    }

    @Override
    public void close() {
        // Release resources if the reader has opened any.
    }
}
~~~

The mechanism above illustrates three things:

1. open() retrieves the last saved ID.
2. read() fetches the next record and updates the current position in the reader object.
3. update() writes that position into the ExecutionContext at the checkpoint.

In a real application, the findNextAfter query must have a stable ordering and clear paging conditions. If the source data changes while the Job is interrupted, saving only the last ID may not be enough to ensure consistent results.

If a reader is wrapped inside another reader, make sure the delegate's state is also managed. You may need to register the delegate stream with the Step using the stream(...) mechanism, or implement a wrapper that fully forwards the ItemStream calls. If the framework does not know that a component needs to save state, that component's checkpoint may not be updated.

## 5. Where Does a Tasklet Step Restart From?

A Tasklet Step does not automatically have checkpoints by item position like a chunk reader. A Tasklet is invoked through the execute method, and the application decides what state needs to be saved if the work can be resumed midway.

For a Tasklet that performs a short task with no intermediate state, when the Step fails and is restarted, the task is usually run again from the beginning.

If a Tasklet performs long work over multiple iterations, it can save its progress into the Step ExecutionContext. For example, a Tasklet that processes a set of IDs group by group:

~~~java
@Bean
public Step rebuildIndexStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        IndexService indexService) {

    return new StepBuilder("rebuildIndexStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                ExecutionContext context = chunkContext
                        .getStepContext()
                        .getStepExecution()
                        .getExecutionContext();

                long lastId = context.getLong("lastId", 0L);

                long nextId = indexService.rebuildNextBatch(lastId, 500);

                if (nextId == lastId) {
                    return RepeatStatus.FINISHED;
                }

                context.putLong("lastId", nextId);
                return RepeatStatus.CONTINUABLE;
            }, transactionManager)
            .build();
}
~~~

In the example:

- lastId is the Tasklet's saved progress.
- Each call processes a group of up to 500 records.
- If there is more data, the Tasklet updates lastId and returns CONTINUABLE.
- When the data is exhausted, the Tasklet returns FINISHED.

TaskletStep executes each Tasklet call in a transaction. When the ExecutionContext state is saved successfully together with the transaction, a restart can recover the most recently committed checkpoint.

If the Tasklet calls an external API or writes a file and those operations are not in the same transaction, saving lastId does not automatically undo the external effects when the transaction rolls back. You need to design batch operations that can be safely re-run.

## 6. Conditions for Spring Batch to Recover the Correct Checkpoint

Having a checkpoint in the ExecutionContext is not enough. Restart also depends on the identity of the JobInstance, the JobRepository, and how the processing components save state.

### Reuse the Identifying JobParameters

A JobInstance is identified by the Job name and the identifying JobParameters.

When you want to restart a JobInstance that has failed or been stopped, run it again with the same set of identifying parameters. Spring Batch relies on the old metadata to create a new JobExecution belonging to that JobInstance and to recover the progress of the Steps.

~~~text
customerImportJob
       |
       +-- JobInstance(inputFile=customers.csv)
                |
                +-- JobExecution 1: FAILED
                |       |
                |       +-- importCustomersStep
                |               checkpoint: after chunk 2
                |
                +-- JobExecution 2: RESTARTED
                        |
                        +-- importCustomersStep
                                continues after chunk 2
~~~

If you change an identifying parameter, for example changing inputFile, Spring Batch creates a new JobInstance. The new JobInstance does not continue from the old JobInstance's checkpoint.

Non-identifying parameters do not change the identity of the JobInstance. However, make sure the values that affect processing remain appropriate on restart; do not change the processing mode midway if doing so changes the meaning of the old checkpoint.

### The JobRepository Must Retain the Metadata

When the application is stopped completely, the checkpoint must still exist in the repository. If the metadata lives only in the memory of a process that has ended, a new run cannot find the old checkpoint again.

In a production environment, a database-backed JobRepository is typically used, and the metadata tables are kept intact across deployments or application restarts.

### Readers and Writers Must Support the Required State

Stateful readers/writers need to implement ItemStream or be registered as streams with the Step. If a component does not save progress, the framework cannot infer a safe position to continue from by itself.

Pay particular attention to:

- A custom reader that does not save its position.
- A reader wrapped in a wrapper that does not forward ItemStream.
- A reader that sets saveState(false).
- A data source that changes between two runs.
- A reader name or reader configuration that changes so that the old state no longer matches.

In these cases, the Step may re-read the data from the beginning, fail to restore the correct position, or restore a position that no longer fits the current data source.

## 7. When a Job Restarts, Which Steps Are Run Again?

A Job's restartability and a Step's checkpoint are related but are not the same concept.

When restarting a JobInstance:

- A Step that has completed is usually skipped.
- A Step that failed or has not completed can be run again from the saved checkpoint.
- A new Step that has never run starts from the beginning.
- A Step configured with **allowStartIfComplete(true)** can be executed again even though it completed before.

For example:

~~~text
Job run 1
  |
  +--> validateInputStep       COMPLETED
  |
  +--> importCustomersStep     FAILED
         checkpoint: chunk 8
  |
  +--> createReportStep        NOT STARTED

Job restart
  |
  +--> validateInputStep       SKIPPED
  |
  +--> importCustomersStep     RESTART from checkpoint chunk 8
  |
  +--> createReportStep        START from the beginning
~~~

### allowStartIfComplete Is Not a Checkpoint

You can configure:

~~~java
@Bean
public Step refreshReferenceDataStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    return new StepBuilder("refreshReferenceDataStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                // Refresh the reference data.
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .allowStartIfComplete(true)
            .build();
}
~~~

**allowStartIfComplete(true)** allows a completed Step to be executed again when the JobInstance is restarted. This configuration controls whether the Step is allowed to run again; it does not create a new checkpoint by itself and does not replace the state-saving mechanism of the reader or Tasklet.

Define clearly what it means for the Step to run again, especially for tasks that create reports, send notifications, or call external systems. If the Step is not safe to execute multiple times, you need a de-duplication mechanism.

### startLimit Does Not Determine the Checkpoint

startLimit limits the number of times a Step is allowed to start. It does not decide the next read position.

~~~java
new StepBuilder("importCustomersStep", jobRepository)
        .<RawCustomer, Customer>chunk(100, transactionManager)
        .reader(customerReader)
        .processor(customerProcessor)
        .writer(customerWriter)
        .startLimit(3)
        .build();
~~~

If the Step has exceeded the start limit, the next restart may be rejected. Increasing startLimit does not replace saving checkpoints correctly.

Similarly, preventRestart() is a Job-level configuration that disallows restarting the Job. It does not change how a reader stores its read position.

## 8. Checkpoints and Transactions: What Gets Redone?

A checkpoint is usually tied to the chunk's transaction boundary. This produces several situations:

| Situation | Common behavior on restart |
|---|---|
| Chunk already committed | Continue after that chunk's checkpoint |
| Chunk was being processed but rolled back | Re-read and re-process the data belonging to the uncommitted chunk |
| Step failed before the first checkpoint | Start over from the initial state |
| Reader does not save state | Cannot restore the position provided by the reader; may re-read from the beginning |
| Step already completed | Usually skipped when the Job is restarted |
| New Step not yet run | Starts from the beginning |

### Effects Outside the Transaction

A Step's transaction usually protects the operations within the corresponding transaction manager, such as writing data to the same database. However, an HTTP call, sending an email, or writing an external file is not automatically rolled back along with the database transaction.

For example:

1. The writer calls an API to create an invoice.
2. The API creates the invoice successfully.
3. The chunk's database transaction encounters an error before the commit.
4. Spring Batch rolls back the chunk.
5. The Job restarts and calls the API again for the same invoice.

If the API does not support idempotency, the system may create a duplicate invoice. Therefore, use a unique transaction code, an idempotency key, an outbox table, or a state-checking mechanism appropriate to the business.

**A checkpoint guarantees the ability to recover metadata progress; it does not by itself guarantee that every external effect happens only once.**

### How Do Skip and Retry Affect This?

In chunk processing, a retry can cause an item to be processed again within the same run. The skip policy can allow skipping a failing item so that the chunk continues.

When the final chunk commits, the checkpoint reflects the completed progress of that chunk, including both the items processed successfully and the items skipped per the configuration. When you restart after this checkpoint, the items already recorded as skipped are not automatically put back into processing as if they had never encountered an error.

Track readCount, writeCount, filterCount, the skip counts, and the error logs to understand exactly which data was processed, filtered, or skipped.

## 9. A Changing Data Source Can Make a Checkpoint Meaningless

A reader's checkpoint is meaningful only when the data source at the time of the restart is compatible with the data source at the time the checkpoint was created.

For example, a reader saves its position after line 10,000 of the file customers.csv. After the Job fails, someone replaces the file with another version that has lines added or removed. The reader continues from the saved position, but the content at that position may no longer be the expected record.

Some practical measures:

- Use an immutable input file for each JobInstance.
- Put a file ID, data version, or business date into the identifying JobParameters.
- Store a checksum or source metadata if the business requires verifying that the source has not changed.
- For database paging, use a stable sort key and reproducible query conditions.
- Avoid offset-based paging over a continuously changing dataset without a snapshot or consistent conditions.

If the source data can change, define clearly which snapshot a JobInstance is processing. Saving only the line number or last ID may not be enough.

## 10. Checkpoints in a Partitioned Step

With partitioning, a Step is divided into multiple partitions to be processed in parallel or in a distributed way. Each partition has its own StepExecution and ExecutionContext.

~~~text
masterStep
   |
   +--> partition 0
   |       its own checkpoint
   |
   +--> partition 1
   |       its own checkpoint
   |
   +--> partition 2
           its own checkpoint
~~~

When a partition fails, a restart can recover that partition from its own checkpoint, while the partitions that have completed are handled according to their saved state.

This requires:

- Each partition has a stable data range that does not overlap unintentionally.
- Each partition's reader can save the state it needs.
- The metadata of each StepExecution is stored durably.
- Shared resources are managed safely when multiple partitions run concurrently.

The master Step's checkpoint does not replace the checkpoint of each worker Step. When debugging a partitioned Job, look at the ExecutionContext and the state of each corresponding StepExecution.

## 11. Example of a Failed Run and a Restart

Suppose a Job imports a file with 450 records, with a chunk size of 100.

First run:

~~~text
Chunk 1: 1   - 100  -> COMMITTED
Chunk 2: 101 - 200  -> COMMITTED
Chunk 3: 201 - 300  -> COMMITTED
Chunk 4: 301 - 400  -> FAILED, ROLLBACK
Chunk 5: 401 - 450  -> not yet run
~~~

At the time of the error, the most recent checkpoint is after chunk 3. When restarting with the same JobInstance and a reader that supports state recovery:

~~~text
Chunk 1: already committed -> no need to reprocess
Chunk 2: already committed -> no need to reprocess
Chunk 3: already committed -> no need to reprocess
Chunk 4: re-read and re-process from the state after chunk 3
Chunk 5: continues after chunk 4 completes
~~~

If chunk 4 commits successfully in the restart, the new checkpoint moves to after record 400. The Job then processes the last 50 records.

If the reader does not save state, the result can differ: the reader may start over from the beginning. In that case, the writer and the target data must have a mechanism to avoid duplicate writes or must be designed to be safely reprocessed.

## 12. Monitoring Checkpoints When Investigating Errors

When a Step does not restart from the position you expect, examine the previous run's metadata and the stream configuration.

| Information | What to understand |
|---|---|
| JobInstance | Is the restart using the correct identifying JobParameters? |
| JobExecution | What status did the previous run end in? |
| StepExecution | Did the Step fail or complete? |
| ExecutionContext | What is the last checkpoint state that was saved? |
| readCount | How many items were read in that execution? |
| writeCount | How many items were written? |
| commitCount | How many chunk transactions were committed? |
| Reader configuration | Does the reader support ItemStream and save state? |
| JobRepository | Is the metadata stored durably? |

You can view the metadata in repository tables such as BATCH_JOB_EXECUTION, BATCH_STEP_EXECUTION, and BATCH_STEP_EXECUTION_CONTEXT. When reading the data, you need to cross-reference the correct JobExecution and StepExecution belonging to the JobInstance being restarted.

Do not rely only on readCount to infer the exact read position. A reader can read ahead, filter items, or perform its own paging logic. The reader's ExecutionContext is what holds the recovery state that the component provides.

## 13. Principles for Designing a Restartable Step

When building a Step, decide from the start what data needs to be saved in order to continue the work.

- For chunk processing, choose an appropriate chunk size and use readers/writers that support ItemStream when state recovery is needed.
- For a custom reader, implement open, update, and close, and save a reproducible position.
- For a long Tasklet, save business progress in the Step ExecutionContext at safe transaction boundaries.
- Keep the identifying JobParameters stable when restarting an old JobInstance.
- Use a durable JobRepository if you need to restart after the process or server stops.
- Keep the data source stable throughout the lifecycle of the JobInstance.
- Design effects outside the transaction to be idempotent or to have a de-duplication mechanism.
- Check each partition separately if you use partitioning.
- Distinguish a completed Step from a failed Step; a completed Step is usually skipped when the Job is restarted.

The core point is that a checkpoint reflects **the most recent state that the Step saved safely**. For a chunk Step, that is usually the last committed chunk. For a Tasklet or a custom reader, the application must save enough state to be able to continue the work correctly. When the checkpoint, the JobParameters, the JobRepository, and the data source are managed consistently, Spring Batch can restart a Job without having to reprocess all the data that has already completed.
