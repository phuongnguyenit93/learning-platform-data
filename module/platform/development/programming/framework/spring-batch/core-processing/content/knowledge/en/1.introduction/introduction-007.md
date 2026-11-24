# Transactions, Checkpoints, and Progress State

In Spring Batch, transactions, checkpoints, and progress state work together so that a Step can process data in portions, recover after errors, and allow a run to be monitored. These three concepts are related but solve three separate problems:

- **Transaction** determines which parts of the work are committed or rolled back together.
- **Checkpoint** stores the position and state needed to continue from the most recent committed point.
- **Execution status and counters** record what state a run is in and how much data has been processed.

Understanding the boundaries of each part helps you design batch jobs that can restart, avoid writing duplicate data, and explain exactly what happened when a job failed.

## 1. Chunk-Oriented Processing Lifecycle

A Step usually uses chunk-oriented processing to read, process, and write data in groups. For example, with a commit interval of 100, Spring Batch gathers up to 100 items into a chunk and then hands that group to the ItemWriter.

General flow:

1. Begin a transaction for the chunk.
2. Call the ItemReader to read items.
3. Call the ItemProcessor for each item if the Step has a processor.
4. The ItemProcessor can return a transformed item or return null to filter that item out.
5. Call the ItemWriter once with the remaining items in the chunk.
6. Update the Step's state and checkpoint.
7. Commit the transaction. If an error that triggers rollback occurs, the transaction is rolled back according to the configuration.

Example with a commit interval of 3:

~~~text
Chunk 1: read A, B, C -> process -> write -> commit
Chunk 2: read D, E, F -> process -> write -> commit
Chunk 3: read G, H, I -> process -> write -> commit
...
~~~

Each chunk is a transaction unit. If writing chunk 2 fails and the error causes the transaction to roll back, the changes belonging to that transaction are undone. Chunks that were committed earlier are kept.

The commit interval is the number of items the framework gathers into a chunk, and it is not necessarily equal to the number of rows ultimately written. If the processor filters an item by returning null, that item is not passed to the writer, but it has still been read and processed.

### Configuring the Chunk and the Transaction Manager

The example below uses an API in the Spring Batch 5 style:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

The parameter 100 is the commit interval. The transaction manager controls the transaction for each chunk. In a real application, the transaction manager must match the resource the writer uses, such as the transaction manager for the target database.

API names and signatures may differ in Spring Batch 4 or earlier versions; the example above follows the StepBuilder configuration style common in Spring Batch 5.

## 2. How Do Transactions Protect Data?

A transaction provides a commit/rollback boundary for the resources managed by the transaction manager.

Suppose a chunk updates three orders:

~~~text
BEGIN
  UPDATE order A
  UPDATE order B
  UPDATE order C
COMMIT
~~~

If the statement that updates order C fails and the error causes the transaction to roll back, the updates to A and B in the same transaction are also undone. The database does not keep a state in which only part of the chunk was updated.

This is useful when the writer performs multiple database operations. The writer can write each item in the chunk, but those operations still belong to the same transaction if they use the same transaction manager and the same transactional resource.

### Choosing the Commit Interval

The commit interval directly affects performance and recovery cost.

| Small commit interval | Large commit interval |
|---|---|
| Shorter transactions | Longer-lasting transactions |
| Fewer items to reprocess after a rollback | May have to reprocess more items |
| Frequent commits, increasing commit overhead | Fewer commits |
| Usually holds less data in memory | May need more memory |
| Locks are usually held for a shorter time | Locks may be held longer |

There is no single number that suits every job. Consider the data size, the processing time per item, the database's load capacity, the degree of lock contention, and the recovery requirements. You can start with a moderate chunk, measure the run time and resource usage, and then adjust.

### What Transactions Do Not Protect on Their Own

A database transaction does not automatically undo effects outside the database, for example:

- Sending email or calling another system's API.
- Writing a file to the filesystem.
- Pushing a message into a broker that does not participate in the same transaction.
- Calling a payment service or a shipping service.

If the writer calls an external API and then the database transaction rolls back, the external API may still have performed the action. When the job reruns, that action may be repeated.

For such effects, you need to design an additional appropriate mechanism, for example:

- **Idempotency key** so the system can recognize that a request has already been processed.
- **Transactional outbox** to record the intent to send a message in the same database transaction, after which a separate process publishes the message.
- A result-recording table or a business key to detect operations that have completed.
- A compensation mechanism when an external action cannot be rolled back.

Do not assume that rolling back a chunk will undo everything that the code in the writer has done.

## 3. Checkpoints and ExecutionContext

A checkpoint is the state saved at a commit point, sufficient for a reader or writer to continue the work when the Step is restarted.

Spring Batch stores state data in the **ExecutionContext**, a key/value structure attached to an execution. There are two main scopes:

- **Step ExecutionContext** is attached to the StepExecution. This is where the read position or the state needed to restart a Step is usually stored.
- **Job ExecutionContext** is attached to the JobExecution. This is an appropriate place to share a small amount of state between Steps within the same job execution.

For a chunk-oriented Step, the Step's state is usually updated and saved at the commit boundary. The Job ExecutionContext is usually updated when a Step completes or when the application actively updates it. The details of when it is saved depend on the Step lifecycle and the repository configuration.

The **JobRepository** stores Spring Batch's metadata, including executions, step executions, and execution contexts. A checkpoint is not a copy of all business data; it should contain only the information needed to determine how to continue processing.

### The Role of ItemStream

Components that need to save and restore state can implement **ItemStream**. The basic lifecycle consists of:

- **open(ExecutionContext)**: restores state when the Step starts or restarts.
- **update(ExecutionContext)**: writes the current state into the ExecutionContext at the point where the framework is about to save the checkpoint.
- **close()**: releases resources when the Step ends.

Many of the readers and writers that ship with Spring Batch already implement this mechanism. When using those components, set a stable component name and enable state saving if you need restart. For example, a FlatFileItemReader can be configured as follows:

~~~java
@Bean
@StepScope
FlatFileItemReader<Customer> customerReader(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        LineMapper<Customer> customerLineMapper) {

    return new FlatFileItemReaderBuilder<Customer>()
            .name("customerReader")
            .resource(new FileSystemResource(inputFile))
            .lineMapper(customerLineMapper)
            .saveState(true)
            .build();
}
~~~

**@StepScope** lets the reader be created when the Step runs, at which time the job parameter inputFile has a value. **saveState(true)** lets the reader save the information needed to restore the read position. Keep the reader name stable across reruns so that Spring Batch correctly recognizes the component's state.

If you set **saveState(false)**, the component does not save its own checkpoint. That may be appropriate for a reader that does not need restart or a design in which the read position is managed elsewhere, but the Step cannot rely on that reader's internal state to continue accurately.

### Example of a Reader That Manages Its Own Checkpoint

A custom reader can store the index of the next item to read. The simple example below illustrates the ItemStreamReader contract; the list in the example is only meant to clarify the mechanism:

~~~java
public class IndexedItemReader<T> implements ItemStreamReader<T> {

    private static final String NEXT_INDEX = "indexedReader.nextIndex";

    private final List<T> items;
    private int nextIndex;

    public IndexedItemReader(List<T> items) {
        this.items = items;
    }

    @Override
    public void open(ExecutionContext context) {
        nextIndex = context.containsKey(NEXT_INDEX)
                ? context.getInt(NEXT_INDEX)
                : 0;
    }

    @Override
    public T read() {
        if (nextIndex >= items.size()) {
            return null;
        }

        return items.get(nextIndex++);
    }

    @Override
    public void update(ExecutionContext context) {
        context.putInt(NEXT_INDEX, nextIndex);
    }

    @Override
    public void close() {
        // Release resources if the reader uses external resources.
    }
}
~~~

Suppose the first chunk reads and commits 100 items. When update is called, the reader saves **nextIndex = 100**. If the next chunk fails and the Step is restarted, open reads the value 100 back from the ExecutionContext and starts from the 101st item.

This is an example illustrating a checkpoint on restart. A production reader needs to handle additional real-world requirements such as a data source that can change, rollback within the same run, concurrent access, and resource release. Incrementing an in-memory index variable does not automatically return the reader to its earlier position when a chunk rolls back and is then retried immediately within the same execution.

### Choosing What to Store in the ExecutionContext

Store only the values needed to recover or to pass state between Steps, for example:

- The sequence number of the next record.
- The last ID processed in a data stream with a stable ordering.
- The name or version of the input file.
- A timestamp or paging key that has been confirmed.

Use keys prefixed with the component name, such as **customerReader.nextIndex**, to avoid key collisions among multiple readers or writers. The stored value must be compatible with the ExecutionContext serialization mechanism that is configured. Do not put the whole item list, large objects, or sensitive business data into a checkpoint.

If a reader or writer is wrapped inside another component, make sure the inner component is registered as a stream when needed. Otherwise, its open, update, and close callbacks may not be called as expected.

## 4. Restarting a Job and the Role of JobParameters

Spring Batch distinguishes JobInstance from JobExecution:

- **JobInstance** represents a logical run of a job, determined by the job name and the identifying JobParameters.
- **JobExecution** represents one specific execution of a JobInstance.
- A JobInstance can have multiple JobExecutions if a previous run failed or was stopped and was restarted.

Example:

~~~text
JobInstance: importOrders + businessDate=2026-11-15
  JobExecution 101: FAILED
  JobExecution 108: STARTED
  JobExecution 108: COMPLETED
~~~

If you rerun the same job name with the same identifying parameters, Spring Batch recognizes it as the same JobInstance. When a JobInstance has a failed or stopped execution, the job can be restarted and use the saved checkpoint.

If you change an identifying parameter, for example businessDate, Spring Batch creates a new JobInstance. The new run starts from a new state, not by restarting the checkpoint of the old JobInstance.

This leads to several principles:

- Use JobParameters to clearly determine the data set or business period the job processes.
- When restarting, keep the identifying parameters of the run you need to continue unchanged.
- Create a new parameter only when the intent is to run a new JobInstance.
- Ensure that the input data and the read order remain compatible with the saved checkpoint.

An input file that has been replaced but still uses the same parameter can cause the checkpoint to point to a position that is no longer correct. You can additionally store the file name, size, checksum, or the data source version to detect a situation where the input has changed.

By default, a Step that has completed within a JobInstance is usually skipped when the job is restarted. If the business requires rerunning a completed Step, you can consider configuring **allowStartIfComplete(true)** for that Step. You need to assess the impact of duplicated data before enabling this option.

## 5. Progress State and Executions

Spring Batch stores state at multiple levels. You need to know which object you are observing so that you do not confuse the state of one run with the state of the job in general.

| Object | Meaning |
|---|---|
| JobInstance | The logical identity of a job by job name and identifying parameters |
| JobExecution | One specific run of a JobInstance |
| StepExecution | One specific execution of a Step within a JobExecution |
| ExecutionContext | State data used to restart or exchange information |
| ExitStatus | A result code used to describe the result and to steer the flow |

### BatchStatus

**BatchStatus** describes the execution state of a JobExecution or StepExecution. Commonly seen statuses include:

| BatchStatus | General meaning |
|---|---|
| STARTING | The execution is being initialized |
| STARTED | The execution is running |
| STOPPING | A stop request is being processed |
| STOPPED | The execution has stopped on request |
| FAILED | The execution ended because of an error |
| COMPLETED | The execution has completed |
| ABANDONED | The execution is marked as not to be restarted |
| UNKNOWN | A reliable state cannot be determined |

**STOPPED** and **FAILED** have different meanings. A job that was stopped in a controlled way can be restarted depending on its state and configuration; a failed job usually needs its cause of error addressed before restart. **ABANDONED** indicates an execution that will not be continued through the normal restart mechanism.

### ExitStatus

**ExitStatus** describes the result as an exit code. It is commonly used in the job flow to decide the next Step. For example, a Step can complete in terms of execution but return its own business code so that the flow moves to a different processing branch.

Therefore, you should not equate BatchStatus with ExitStatus. BatchStatus tells you whether the execution completed, failed, or was stopped; ExitStatus describes the result that the flow or the monitoring system uses.

### Progress Counters in StepExecution

**StepExecution** contains several counters that help you observe progress:

| Field | Explanation |
|---|---|
| readCount | Number of items read successfully |
| writeCount | Number of items written |
| filterCount | Number of items filtered by the processor returning null |
| readSkipCount | Number of read errors handled by the skip policy |
| processSkipCount | Number of processing errors that were skipped |
| writeSkipCount | Number of write errors that were skipped |
| commitCount | Number of commits recorded |
| rollbackCount | Number of rollbacks recorded |
| startTime, endTime | Start and end times of the execution |
| status, exitStatus | The Step's status and result code |

The counters help answer the question of how many items the job has read, filtered, written, or skipped. They do not replace a checkpoint. Do not infer the position to continue reading from readCount alone, because filtering, skipping, rollback, and the way the reader pages can make the number of items read not equivalent to the position in the data source.

For example, readCount can be 1,000 while writeCount is 970 and filterCount is 30. This can be completely normal if the processor deliberately filters 30 items.

### Observing Progress with Metadata

You can observe state through the execution objects in code or through the **JobExplorer** when you need to query executions that have been stored in the repository. For example, from a StepExecution:

~~~java
void logStepProgress(StepExecution stepExecution) {
    log.info(
            "step={}, status={}, read={}, written={}, filtered={}, commits={}, rollbacks={}",
            stepExecution.getStepName(),
            stepExecution.getStatus(),
            stepExecution.getReadCount(),
            stepExecution.getWriteCount(),
            stepExecution.getFilterCount(),
            stepExecution.getCommitCount(),
            stepExecution.getRollbackCount()
    );
}
~~~

For a monitoring system, you should display at least the job name, the JobExecution ID, the Step name, the BatchStatus, the start time, the end time, and the important counters. The JobExecution ID helps distinguish restarts belonging to the same JobInstance.

The metadata in the JobRepository is the source for tracking Spring Batch executions. Do not update the metadata tables directly to “fix” progress. Let the framework manage state through the JobRepository and the corresponding APIs.

## 6. What Happens When a Chunk Fails?

Suppose a Step reads 1,000 orders, with a commit interval of 100:

~~~text
Chunk 1: items 1-100       -> commit
Chunk 2: items 101-200    -> commit
Chunk 3: items 201-300    -> commit
Chunk 4: items 301-400    -> writer hits an error -> rollback
~~~

After chunk 4 rolls back:

- The database changes belonging to chunk 4 are rolled back if they participate in the same transaction.
- The three chunks that were committed earlier are kept.
- The most recent durable checkpoint is still after chunk 3, if the repository and the business data are committed in sync.
- The Job or Step may end with the status FAILED, depending on the error type and configuration.
- When restarting the same JobInstance, a restartable reader can continue from the checkpoint after item 300.

The counters in the execution reflect what actually happened in the run and may include information about rollback, skip, or retry. When analyzing an incident, look at the execution status, the counters, and the checkpoint together rather than looking at a single number.

### Skip and Retry Affect Progress

Spring Batch can be configured to retry a transient operation or skip a faulty item according to a defined policy.

- **Retry** tries the operation again when the error is considered likely to be transient, such as a recoverable service access error.
- **Skip** allows the job to continue after an accepted type of error, while incrementing the corresponding skip counter.
- **Rollback** undoes the changes in the current transaction when the error requires a rollback.

Retry and skip need to be designed based on the nature of the error. Do not skip important data errors just to get the job to the COMPLETED status, because the final result may be missing data without anyone noticing. With a writer that is not idempotent or has effects outside the transaction, a retry can also create duplicate operations.

## 7. Keeping Checkpoints Consistent with Business Data

A checkpoint is only useful when it correctly describes the portion of data that has been durably processed.

If the business data and Spring Batch's metadata share the same transaction manager and the same appropriate transactional resource, writing the business data and updating the checkpoint can be committed together. In that case, after a restart, the checkpoint corresponds to the data that was committed.

If the business data and the JobRepository use different databases or transaction managers, you should not assume that the two places always commit or roll back atomically. A situation can occur in which the business data has been committed but the checkpoint has not been saved, or the checkpoint has been saved but the business data has not been committed. You need to understand clearly how the application's transactions are configured and choose an appropriate synchronization mechanism.

For sources or destinations that do not support a shared transaction, design for safe repeated runs:

- Use a unique business key or an upsert where appropriate.
- Store processing markers in a place where they can be checked again.
- Make the writer idempotent if possible.
- Check whether the input data changed between two runs.
- Use an outbox or a compensation mechanism for cross-system effects.

A correct checkpoint cannot by itself fix a writer that creates duplicate data when rerun.

## 8. Situations to Watch for in Operations

**A reader that does not save state.** If a reader turns off saveState or does not implement ItemStream when it should, Spring Batch does not have enough internal information to restore the read position. You need to add a checkpoint mechanism or accept rerunning from the beginning with an idempotent design.

**A changing data source.** A checkpoint by line number or position may no longer be correct if the file is replaced, records are inserted, or the data order changes. Use a stable data source or additionally store a source version identifier.

**A Step with multiple streams.** Each stream needs its own key and must be registered correctly so that the lifecycle callbacks are called. A duplicate key in the ExecutionContext can cause one component's state to overwrite another's.

**Parallel execution or partitioning.** Each partition usually has its own StepExecution and ExecutionContext. A reader shared among multiple threads must be safe for concurrent access; a shared checkpoint without synchronization can cause omissions or duplicate processing. Prefer per-partition state and clear data division.

**A Step completes but the job fails at a later Step.** When restarting the same JobInstance, the completed Step is usually skipped. If a Step needs to be rerun, configure it deliberately and make sure the Step's operations are safe to repeat.

**Using new JobParameters when you want to restart.** Changing an identifying parameter creates a new JobInstance. The new job does not continue the old instance's checkpoint, even if the job name is the same.

## 9. How to Read a Run to Find the Cause of a Failure

When a batch job does not complete, you can check in turn:

1. Identify the JobInstance and the JobExecution ID to be sure you are looking at the right run.
2. Read the BatchStatus, the ExitStatus, the start/end times, and the error information.
3. Identify the StepExecution that failed; look at the read, write, filter, skip, commit, and rollback counts.
4. Identify the most recent checkpoint saved in the Step ExecutionContext.
5. Check whether the reader supports restart and whether the data source is still the right version.
6. Check whether the writer creates effects outside the transaction or could write duplicates on restart.
7. After addressing the cause, restart the same JobInstance if the goal is to continue from the saved checkpoint.

When operating, you need to clearly distinguish three questions: the transaction tells you which portion of data has been committed; the checkpoint tells you where the Step can continue from; the execution status and counters tell you how the run went. Combining all three is what allows you to accurately assess the progress and the safety of a restart.

