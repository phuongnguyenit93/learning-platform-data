# TaskletStep and Chunk-oriented Step

In Spring Batch, a Step is an independent phase of a Job. A Step can perform a compact business operation, such as calling a stored procedure or moving a file, or process a large number of records group by group. Two commonly used ways of organizing a Step are **TaskletStep** and **chunk-oriented processing**.

The key point when learning these two concepts is to distinguish the API used to declare a Step from the underlying execution mechanism. TaskletStep is a kind of Step that implements invoking a Tasklet in a loop with transaction management. Chunk-oriented processing is a model that processes data chunk by chunk; in Spring Batch, this model is also implemented inside a TaskletStep by a specialized Tasklet.

## 1. Where Does a Step Fit in a Job?

A Job describes the batch workflow at the overall level. A Job is usually assembled from multiple Steps, each Step responsible for one part of the work:

~~~text
Job: importOrders
    |
    +-- Step 1: validateInput
    |
    +-- Step 2: importOrders
    |
    +-- Step 3: generateReport
    |
    +-- Step 4: archiveInput
~~~

A Step has its own lifecycle, execution status, and metadata. Spring Batch records Step executions through StepExecution, including the number of reads, processes, and writes, the number of skipped records, the status, and the ExecutionContext.

When designing a Step, the first question should be the nature of the work:

- Is the work a single operation or a piece of logic that can be done in one call? A Tasklet is usually suitable.
- Does the work need to read many items, process each item, and write the results in groups? Chunk-oriented processing is usually suitable.

Both choices use Spring Batch's Step management mechanism, but they differ in how the logic is organized, the transaction boundaries, and the ability to handle errors at the item level.

## 2. What Are Tasklet and TaskletStep?

A **Tasklet** is a small processing contract in Spring Batch. A Tasklet does its work in the method:

~~~java
RepeatStatus execute(
        StepContribution contribution,
        ChunkContext chunkContext) throws Exception;
~~~

A Tasklet receives a StepContribution to update the contribution information for the StepExecution, and a ChunkContext to access the context of the call. The method returns a RepeatStatus to indicate whether the Tasklet loop needs to continue or has finished:

- **RepeatStatus.FINISHED**: the Tasklet has completed its work; the Step can end if there are no other errors.
- **RepeatStatus.CONTINUABLE**: Spring Batch calls the Tasklet again on the next iteration.

**TaskletStep** is the implementation of Step that executes a Tasklet. It manages the loop that calls the Tasklet, the transactions, updating the StepExecution, and saving the execution state. Each call to Tasklet.execute is performed within a transaction managed by the Step.

For a Tasklet that performs only one operation, the flow usually looks like this:

~~~text
TaskletStep starts
       |
       v
Open transaction
       |
       v
Call Tasklet.execute(...)
       |
       v
Tasklet returns FINISHED?
   | Yes            | No
   v                v
Commit transaction  Commit transaction
   |                |
   v                v
End Step            Repeat and call the Tasklet again
~~~

If the Tasklet returns CONTINUABLE, the Step continues the loop. Each subsequent call is again performed in that iteration's transaction. If the Tasklet throws an exception, the current transaction is rolled back according to the transaction manager configuration and the Step may end in a failed state.

### Example of a Tasklet That Performs One Operation

Suppose the system needs to mark a batch of data as reconciled. The work is a single business operation, so it can be implemented with a Tasklet:

~~~java
@Bean
public Step markReconciliationStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ReconciliationService reconciliationService) {

    Tasklet tasklet = (contribution, chunkContext) -> {
        reconciliationService.markCurrentBatchAsReconciled();
        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("markReconciliationStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
~~~

In the example, the Tasklet calls the service and returns FINISHED after the operation completes. StepBuilder creates the Step with a stable name, the JobRepository manages the metadata, and the transaction manager controls the transaction for the Tasklet execution.

The code uses the Spring Batch 5 or later API, in which the JobRepository and PlatformTransactionManager are passed directly when creating the StepBuilder and declaring the Tasklet.

### When a Tasklet Needs Multiple Iterations

A Tasklet is not required to be called exactly once. If the work needs to repeat, the Tasklet can return CONTINUABLE while there is still work and FINISHED once it has finished processing:

~~~java
@Bean
public Step processPendingPagesStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        PendingPageService pageService) {

    Tasklet tasklet = (contribution, chunkContext) -> {
        boolean processed = pageService.processNextPage();

        return processed
                ? RepeatStatus.CONTINUABLE
                : RepeatStatus.FINISHED;
    };

    return new StepBuilder("processPendingPagesStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
~~~

Each call processes one page and ends that iteration's transaction. While pages remain, the loop continues. When there is no more data, the Tasklet returns FINISHED.

For work that loops over multiple iterations, you need to define clearly how the processing position is stored. If progress must be recovered after a restart, the Tasklet needs to store a checkpoint in the ExecutionContext or in an appropriate durable state store. Do not rely only on in-memory instance variables, because the bean may be recreated or the process may stop at any time.

## 3. What Is Chunk-oriented Processing?

Chunk-oriented processing organizes data processing in groups of items. Each chunk is read, processed, and written in one transaction unit. The standard model has three components:

- **ItemReader** reads items one at a time from the data source.
- **ItemProcessor** transforms, validates, or discards items; this component may be left unconfigured if no intermediate processing is needed.
- **ItemWriter** writes a group of processed items to the destination.

For example, a Job that imports orders from a CSV file into a database. Instead of loading the entire file into memory and writing it all at once, Spring Batch reads and writes in groups of limited size.

~~~text
Data source
     |
     v
 ItemReader
     |
     v
 ItemProcessor (optional)
     |
     v
 Chunk's set of items
     |
     v
 ItemWriter
     |
     v
 Data destination

Each chunk completes in one transaction
     |
     v
 Commit and move on to the next chunk
~~~

The **commit interval** is the number of items used to determine the normal chunk size. For example, if the chunk size is configured as 100, the Step reads and processes a group of up to about 100 items before calling the writer and committing that group. The last chunk may have fewer than 100 items when the data source is exhausted.

Chunk-oriented processing is suitable when you need to process large datasets, limit memory usage, control transactions by group, and take advantage of Spring Batch's reader, processor, and writer mechanisms.

### Example of Declaring a Chunk-oriented Step

The following example processes Orders in chunks of 100 items:

~~~java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
~~~

The two generic types in the chunk declaration represent the input item type and the item type after processing:

- The first type is the type read by the ItemReader, here Order.
- The second type is the type returned by the ItemProcessor and accepted by the ItemWriter, here also Order.

If the processor converts OrderInput into OrderEntity, you can declare two different types:

~~~java
return new StepBuilder("convertOrdersStep", jobRepository)
        .<OrderInput, OrderEntity>chunk(100, transactionManager)
        .reader(orderInputReader)
        .processor(orderConverter)
        .writer(orderEntityWriter)
        .build();
~~~

In this configuration, the reader reads OrderInput, the processor converts it to OrderEntity, and the writer writes the OrderEntity items.

## 4. Chunk Size Determines the Transaction Boundary

With a chunk-oriented Step, Spring Batch gathers items into a chunk. When the chunk reaches the configured size or the data source ends, the framework calls the ItemWriter to write the group of items and completes the chunk's transaction.

For example, with a chunk size of 3:

~~~text
Read item 1 -> process item 1
Read item 2 -> process item 2
Read item 3 -> process item 3
Call writer with [1, 2, 3]
Commit the transaction of chunk 1

Read item 4 -> process item 4
Read item 5 -> process item 5
Read item 6 -> process item 6
Call writer with [4, 5, 6]
Commit the transaction of chunk 2
~~~

If the writer or an operation participating in the transaction fails before the commit, the current chunk's transaction may be rolled back. Chunks that were committed earlier remain recorded. On restart, Spring Batch relies on the metadata and on the state of components that support state saving to continue, within the capability of the reader and the Step configuration.

Chunk size creates a trade-off:

| Chunk size | Common impact |
| --- | --- |
| Small | Short transactions, and the amount of data to redo on rollback is usually small; in exchange there are more commits and higher overhead |
| Large | Fewer commits and possibly higher throughput; in exchange transactions last longer, use more memory, and have a larger rollback scope |

There is no single optimal chunk size for every system. You need to consider item processing time, the database's transaction limits, memory capacity, load tolerance, and recovery requirements.

## 5. Why Is Chunk-oriented Still Executed by a TaskletStep?

This is a relationship that is easy to confuse when reading the Spring Batch API.

TaskletStep is an execution controller for a Step. It receives a Tasklet and calls the Tasklet within a transaction. When you declare a Step with the chunk API, Spring Batch builds a specialized Tasklet, ChunkOrientedTasklet, to perform the read, process, and write loop for each chunk. ChunkOrientedTasklet runs inside the TaskletStep.

The relationship can be represented as follows:

~~~text
Declare Step with tasklet(...)
          |
          v
      TaskletStep
          |
          v
      Custom Tasklet

Declare Step with chunk(...)
          |
          v
      TaskletStep
          |
          v
  ChunkOrientedTasklet
          |
          +--> ItemReader
          +--> ItemProcessor
          +--> ItemWriter
          |
          v
     Chunks and transactions
~~~

Therefore, in normal usage, TaskletStep and chunk-oriented Step are not two independent kinds of Step at the implementation layer. The difference lies in the declared processing model and the specific Tasklet that the Step executes:

- With the tasklet API, the application provides its own Tasklet.
- With the chunk API, the application configures the reader, processor, writer, and commit interval; Spring Batch creates the corresponding chunk logic.

Understanding this relationship helps you read stack traces, metadata, and Step configuration more accurately. A chunk-oriented Step still has a StepExecution, transactions, and the lifecycle of a TaskletStep.

## 6. Comparing Tasklet and Chunk-oriented Processing

| Criterion | Custom Tasklet | Chunk-oriented |
| --- | --- | --- |
| Goal | Perform an operation or a business loop controlled by the application | Process a set of items through a reader, processor, and writer |
| Unit of processing | Each call to Tasklet.execute | A chunk made up of many items |
| Transaction boundary | Each call to Tasklet.execute | Each chunk |
| Continuation control | The Tasklet returns FINISHED or CONTINUABLE | The framework manages the read loop and ends when the reader runs out of data |
| Item processing | The application organizes the logic itself | Has a reader/processor/writer structure |
| Commit interval | No chunk size configuration in the tasklet API | Has chunk size configuration |
| Per-item skip/retry | Usually has to be designed yourself or handled at an appropriate level | Has fault-tolerant mechanisms at the chunk/item level |
| Progress tracking | The application needs to proactively save checkpoints if needed | Many readers/writers support ItemStream and ExecutionContext |
| Examples | Calling a stored procedure, cleaning up data, sending an orchestration command | Importing a file, synchronizing records, bulk data conversion |

The difference in transactions needs to be understood correctly. A Tasklet can be called multiple times and each call is in its own transaction. A chunk-oriented Step also uses transactions, but one transaction spans the processing of a chunk, including reading, processing, and writing according to the Step's configuration.

## 7. Error Handling, Retry, and Skip

### With a Tasklet

A Tasklet is suitable for an operation with clear business logic and a relatively compact error scope. When an exception escapes the Tasklet, the current transaction is usually rolled back and the Step fails, unless the application or configuration handles the error in another way.

If a Tasklet performs multiple operations in one call, note that the transaction automatically rolls back only the resources participating in the same transaction manager. Calling an HTTP API, writing a file, or sending a message to an external system is not automatically undone when the database transaction rolls back.

Therefore, a Tasklet that performs external side effects needs to be designed to be idempotent or to have reconciliation, retry, and compensation mechanisms. If the Tasklet is called again after a restart, the same operation should not produce unintended duplicate results.

### With a Chunk-oriented Step

Chunk-oriented processing provides fault-tolerant mechanisms to configure retry and skip for appropriate errors. For example:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(20)
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
~~~

In the example, up to 20 InvalidOrderException errors are allowed to be skipped per the configuration; TransientDataAccessException errors are retried up to 3 times under the retry policy. If the limit is exceeded or the error is not allowed to be skipped/retried, the Step may fail.

Skip and retry have different meanings:

- **Skip** allows skipping an item or an error in the configured group in order to continue processing the remaining items. Depending on when the error occurs, Spring Batch applies the skip policy in the read, process, or write phase.
- **Retry** tries a failed operation again, and is usually useful for transient errors such as an interrupted database connection.

Do not configure skip for every exception. Skipping invalid-data errors can be a business requirement, but skipping infrastructure errors or programming errors can hide incidents and make the results wrong.

## 8. Restart and Saving Processing State

Spring Batch stores the metadata of JobExecution and StepExecution in the JobRepository. The ExecutionContext associated with the StepExecution can store the information needed to continue the work after the process has been stopped.

### Restart in a Chunk-oriented Step

Many of Spring Batch's reader and writer components implement ItemStream. The ItemStream lifecycle allows a component to open resources, update state, and save state into the ExecutionContext. For example, a file reader can store its read position so that on restart it knows where to continue.

Restart depends on the specific reader/writer and their configuration. Not every custom reader automatically saves progress. If you implement a reader yourself, consider implementing ItemStream, saving state in open/update, and restoring it on the next open.

Some components have a saveState option. If state saving is turned off, that component may not restore the read position as expected. Check the configuration before relying on restart.

### Restart in a Tasklet

A custom Tasklet does not automatically have fine-grained checkpoints like a reader that supports ItemStream. If the Tasklet splits the work into multiple iterations or processes multiple groups of data, the application needs to proactively record the completed position in the ExecutionContext or in a durable state store.

An example of the idea of saving a checkpoint:

~~~java
Tasklet tasklet = (contribution, chunkContext) -> {
    ExecutionContext executionContext =
            contribution.getStepExecution().getExecutionContext();

    int nextPage = executionContext.getInt("nextPage", 0);

    boolean hasMore = pageService.processPage(nextPage);

    if (hasMore) {
        executionContext.putInt("nextPage", nextPage + 1);
        return RepeatStatus.CONTINUABLE;
    }

    return RepeatStatus.FINISHED;
};
~~~

This illustrates how to read and update the processing position. In a real application, you need to define clearly the meaning of the service's return value, when the checkpoint is saved, the atomicity between the business data update and the checkpoint, and how to handle a page being executed again.

A checkpoint is reliable only when it is consistent with the committed data. If the data update succeeds but the checkpoint has not been saved, a restart may process the same data again. If the checkpoint is saved before the business data is committed, a restart may miss data. The transaction design and idempotency must account for both situations.

## 9. Which Model to Choose for Each Type of Work?

### Use a Tasklet for a Compact Business Operation

A Tasklet is usually the right choice when the work can be expressed clearly as one operation or one loop controlled by the application, for example:

- Calling a stored procedure to create aggregate data.
- Deleting temporary data by a condition.
- Moving or renaming the input file.
- Writing a control record or updating the batch status.
- Calling a service that orchestrates another process.

For these operations, the reader/processor/writer model may not bring a significant benefit. A short Tasklet with a clear transaction and error handling is usually easier to understand.

### Use Chunk-oriented for Processing Many Items

Chunk-oriented is suitable when:

- The data source has many records that need to be read sequentially.
- Each record needs to be validated or converted.
- The results are written in groups to optimize database access.
- You need to track the number of items read, written, filtered, and skipped.
- You need retry or skip at the item level under a specific policy.
- You want to take advantage of ItemStream and ExecutionContext to support restart.

Typical examples are importing millions of lines from a file, synchronizing data between two systems, or converting records in bulk.

### Both Can Be Combined in One Job

A Job can use multiple Steps with different models. For example:

~~~text
Job: dailyImport
    |
    +-- TaskletStep: prepareInput
    |       Check the file, create the working directory
    |
    +-- Chunk-oriented Step: importRecords
    |       Read, convert, and write groups of records
    |
    +-- TaskletStep: publishResult
    |       Record completion status, emit a signal
    |
    +-- TaskletStep: archiveInput
            Archive the processed file
~~~

Dividing Steps by responsibility makes it easier to monitor the state of each phase and to design restart. You need to ensure the Steps can be safely re-run under the Job's restart policy.

## 10. Declaring a Step in Spring Batch 5 and Later

Spring Batch 5 encourages declaring a Step with StepBuilder and passing the JobRepository directly. The transaction manager is also specified explicitly when configuring a Tasklet or a chunk:

~~~java
@Configuration
public class OrderJobConfiguration {

    @Bean
    public Step prepareStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            PreparationService preparationService) {

        Tasklet tasklet = (contribution, chunkContext) -> {
            preparationService.prepare();
            return RepeatStatus.FINISHED;
        };

        return new StepBuilder("prepareStep", jobRepository)
                .tasklet(tasklet, transactionManager)
                .build();
    }

    @Bean
    public Step importStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<OrderInput> reader,
            ItemProcessor<OrderInput, Order> processor,
            ItemWriter<Order> writer) {

        return new StepBuilder("importStep", jobRepository)
                .<OrderInput, Order>chunk(100, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .build();
    }
}
~~~

The two Steps above illustrate two ways of declaring:

- prepareStep uses a custom Tasklet and completes after one call.
- importStep uses chunk-oriented processing with a commit interval of 100.

In older versions of Spring Batch, an application may encounter StepBuilderFactory or JobBuilderFactory. The configuration approach depends on the framework version; when upgrading, you need to move to the API of the version in use and declare the appropriate transaction manager.

## 11. Common Design Mistakes

### Using a Tasklet to Process an Entire Large File in Memory Yourself

If a Tasklet reads the whole file into a list before writing, memory can grow with the file size and the entire operation can sit in one long transaction. For large data, chunk-oriented usually controls memory and transactions better.

### Choosing a Chunk Size That Is Too Large

A large chunk can lengthen the transaction, hold resources for a long time, and cause a single rollback to have to reprocess many items. Measure actual time and resources to choose an appropriate size.

### Assuming a Tasklet Always Runs Only Once

A TaskletStep can call a Tasklet multiple times if the Tasklet returns CONTINUABLE. The Tasklet logic must define a clear stop condition to avoid an infinite loop.

### Using RepeatStatus as the Job's Status

RepeatStatus only controls the loop that calls the Tasklet. It does not replace BatchStatus or ExitStatus. A Tasklet returning FINISHED means the Tasklet loop ended normally; the Step's final status also depends on the execution result and on other listeners or configuration.

### Thinking a Database Rollback Will Undo Every Side Effect

The transaction manager only manages the resources participating in the corresponding transaction. An HTTP request or a file write operation may already have completed even if the database transaction is rolled back. Use idempotency keys, an outbox, controlled retry, or a compensation process when you need to coordinate multiple systems.

### Not Saving a Checkpoint for a Multi-iteration Tasklet

If a Tasklet processes multiple pages or groups, not saving progress means a restart may begin again from the start. Define a durable checkpoint and ensure the checkpoint is consistent with the committed data.

### Ignoring the Restart Capability of the Reader and Writer

Chunk-oriented does not mean every reader/writer can automatically be restarted. You need to use components that support ItemStream or implement a state saving and restoring mechanism yourself.

## 12. How to Make Decisions When Designing a Step

Before writing code, describe the work's inputs, outputs, and recovery approach:

1. Does the work have to process a large set of items or only perform a single business operation?
2. Is there a need to read, convert, and write each item?
3. Do you want to commit after each operation or after a group of items?
4. When an item fails, can you skip or retry just that item?
5. When the process stops midway, which checkpoint do you need to recover from?
6. Are there side effects outside the database transaction, and how do you avoid performing them twice?

If the work is a clear single operation, a Tasklet is usually suitable. If the work is a flow that processes many items, chunk-oriented is usually suitable. When a Job has several different phases, you can combine multiple Steps and choose the appropriate model for each phase.

## Conclusion

TaskletStep provides the mechanism for executing a Tasklet with a loop, transactions, and Step metadata. A custom Tasklet is suitable for a compact business operation or a loop controlled by the application. Chunk-oriented processing handles data in groups through ItemReader, ItemProcessor, and ItemWriter, with each chunk being one transaction unit. In Spring Batch, a chunk-oriented Step is also executed inside a TaskletStep through ChunkOrientedTasklet. Understanding this relationship helps you choose the right model, design the commit interval, and build an appropriate restart capability.
