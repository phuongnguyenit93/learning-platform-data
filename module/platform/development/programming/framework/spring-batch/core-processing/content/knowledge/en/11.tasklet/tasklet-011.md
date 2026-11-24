# Do not put an oversized item pipeline into a tasklet

In Spring Batch, `Tasklet` suits a task with a clear scope, such as calling a stored procedure, creating a control file, cleaning up temporary data, or performing an orchestration operation. You should not turn a Tasklet into a place that manually reads, processes, and writes hundreds of thousands or millions of items inside one large loop.

When work is primarily an item pipeline — reading each record, validating or transforming it, and then writing the result — the chunk-oriented processing model is usually more suitable. This model provides `ItemReader`, `ItemProcessor`, `ItemWriter`, per-chunk transactions, counters, and retry, skip, and checkpoint mechanisms out of the box. If you build the entire pipeline yourself inside a single call to `Tasklet.execute()`, the application must take responsibility for many concerns that Spring Batch already supports.

## 1. Why should a Tasklet not take on an oversized item pipeline?

A Tasklet can perform multiple operations in `execute()`. Technically, there is no limit preventing you from writing a loop that reads a file, calls a service, transforms data, and writes to the database inside the same method. However, when the work has large volume, this approach easily creates a processing unit that is too big and hard to operate.

Example to avoid:

```java
@Component
public class ImportAllCustomersTasklet implements Tasklet {

    private final CustomerService customerService;
    private final CustomerRepository customerRepository;

    public ImportAllCustomersTasklet(
            CustomerService customerService,
            CustomerRepository customerRepository) {
        this.customerService = customerService;
        this.customerRepository = customerRepository;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        List<CustomerInput> allCustomers = customerService.loadAllCustomers();
        List<Customer> converted = new ArrayList<>();

        for (CustomerInput input : allCustomers) {
            converted.add(convert(input));
        }

        customerRepository.saveAll(converted);
        return RepeatStatus.FINISHED;
    }
}
```

This Tasklet loads all data into memory, converts everything, and writes it at once. With a few hundred records, this approach may be acceptable if the data limit is clear. With millions of records, it can cause heap pressure, garbage collection overhead, long transactions, and difficulty continuing after a failure.

Another issue is that a hand-written loop is not automatically managed by Spring Batch like a chunk pipeline. If an item fails midway, the Tasklet must decide for itself which items were processed, which are retried, which are skipped, and how to recover after a restart.

## 2. Risks of processing too many items in a Tasklet

### Memory usage grows with the entire dataset

If a Tasklet calls `loadAll()` or reads an entire file into a `List`, the required memory grows with the number and size of items. One million objects can consume far more heap than the raw data size because the JVM also has to store headers, references, collections, and intermediate objects.

When heap is overused, the garbage collector has to work harder; the application can slow down, throw `OutOfMemoryError`, or be terminated by the operating system/container. This situation also affects other Jobs and online APIs if they run in the same JVM.

Chunk-oriented processing usually holds only the group of items currently being processed at once. With a chunk size of 500, the application does not need to keep all one million items in a list just to write data.

### A transaction can last too long

In `TaskletStep`, each call to `Tasklet.execute()` is managed inside the Step's transaction. If a single call runs a loop for tens of minutes before returning, the transaction can hold database connections and locks for a long time.

Consequences can include:

- Transaction timeout before the Tasklet completes.
- Database locks held for a long time, forcing other transactions to wait.
- Rapid growth of transaction logs or undo data.
- Connection pool occupied for a long period.
- On rollback, all changes in the huge transaction may be undone, even though most of the work was already done.

With chunk processing, each chunk has its own transaction per the Step configuration. Already committed chunks are preserved if a later chunk fails. This limits the rollback scope and lets the Job resume from the saved checkpoint when the reader supports restart.

### Hard to determine progress and failure location

If a Tasklet has only a single `execute()` call, Step metadata mainly reflects the status of that execution. If the Tasklet manually processes 500,000 items and fails at item 450,000, Spring Batch does not automatically know that position unless the Tasklet code saves progress itself.

Operators may only see Step `FAILED` without per-item read/write counters, without knowing how many items completed, and without knowing where to resume from. To get this information, the Tasklet has to write logs, update counters, and save checkpoints itself.

Chunk processing provides counters such as `readCount`, `writeCount`, `filterCount`, skip counts, and reader execution context information. That information helps track progress in finer detail.

### Retry and skip must be implemented manually

In a hand-written loop pipeline, if item 300 encounters an error, the Tasklet must define for itself:

- Should that item be retried, and at most how many times?
- Should an invalid item be skipped or must the entire Step stop?
- If retry succeeds, which item should processing continue from?
- If an error happens after an external system already received a request, how do we avoid resending side effects?

A chunk-oriented Step has fault tolerance configuration to retry or skip selected exceptions, along with limits and appropriate listeners. This does not eliminate the need to design for idempotency, but it provides a standard mechanism to manage errors per item/chunk.

### Hard to restart after the application stops

Suppose a Tasklet reads a 1 GB file, processes up to 90%, and then the server restarts. If the Tasklet does not save checkpoints, restarting may have to read and reprocess from the beginning. If it already wrote part of the data to the target system, re-running may produce duplicate data.

Chunk-oriented processing combining `ItemStream` and `ExecutionContext` can save the read position at commit boundaries. On restart, a reader supporting state persistence can resume from the checkpoint. Committed chunks are kept; the uncommitted portion is reprocessed according to configuration and reader state.

## 3. Comparing a large Tasklet with chunk-oriented processing

| Aspect | Tasklet handling the entire pipeline itself | Chunk-oriented processing |
|---|---|---|
| Processing unit | The entire loop or hand-written logic inside `execute()` | A group of items by chunk size |
| Memory | Easily grows with the whole dataset if everything is loaded | Usually bounded to the active group of items and reader buffers |
| Transaction | Can span the entire Tasklet invocation | Transactions are normally committed per chunk |
| Per-item retry/skip | Must write the logic yourself | Built-in Step fault tolerance mechanism |
| Progress tracking | Must update logs, counters, and status yourself | Has StepExecution counters and chunk metadata |
| Restart | Must save and restore progress yourself | Reader/ItemStream can use ExecutionContext as a checkpoint |
| Suitable for | Single task, clearly bounded work, or set-based operations | Pipeline reading, processing, and writing large volumes of items |

A Tasklet is not always less efficient. A set-based SQL statement can update millions of rows faster than reading each item through Java. The problem is using a Tasklet to implement a large item pipeline manually without a valid reason.

## 4. Moving a large pipeline to chunk-oriented processing

Suppose you need to import 500,000 customers from a CSV file into the database. Each line needs to be validated, normalized, and written to the database.

Instead of loading the entire file into a `List` inside a Tasklet, split the pipeline into three components:

```text
CSV file
   |
   v
ItemReader<CustomerInput>
   |
   v
ItemProcessor<CustomerInput, Customer>
   |
   v
ItemWriter<Customer>
   |
   v
Database

Each chunk is written and committed per configuration.
```

### Reader reads line by line

```java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("customerId", "fullName", "email")
            .targetType(CustomerInput.class)
            .build();
}
```

The reader takes each line and returns a `CustomerInput`. At end of file, the reader returns `null` to signal EOF. A reader supporting `ItemStream` can save its read position to support restart.

### Processor processes one item

```java
@Bean
ItemProcessor<CustomerInput, Customer> customerProcessor() {
    return input -> {
        if (input.customerId() == null || input.customerId().isBlank()) {
            throw new InvalidCustomerException("customerId is required");
        }

        return new Customer(
                input.customerId().trim(),
                input.fullName().trim(),
                input.email().trim().toLowerCase());
    };
}
```

The processor only handles the current item, does not hold the entire list, and does not need to know how many items are in a chunk.

### Writer writes one chunk

```java
@Bean
JdbcBatchItemWriter<Customer> customerWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Customer>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO customers(customer_id, full_name, email)
                    VALUES (:customerId, :fullName, :email)
                    """)
            .beanMapped()
            .build();
}
```

The writer receives the list of processed items in the chunk and can use batch operations to write efficiently to the database.

### Configuring the Step with a commit interval

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> customerReader,
        ItemProcessor<CustomerInput, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<CustomerInput, Customer>chunk(500, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}
```

With a chunk size of 500, Spring Batch reads and processes up to 500 items, calls the writer for that group, and then commits the transaction. If the file has 500,000 lines and no items are filtered or cause errors changing the flow, there are about 1,000 chunks to process. The last chunk may be smaller if the item count does not divide evenly.

## 5. Adding retry and skip to the item pipeline

A chunk-oriented Step can be configured to handle errors by exception type. For example, customer data errors are allowed to skip up to a limit, while transient database errors can be retried:

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> customerReader,
        ItemProcessor<CustomerInput, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<CustomerInput, Customer>chunk(500, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .faultTolerant()
            .skip(InvalidCustomerException.class)
            .skipLimit(100)
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .build();
}
```

This is an illustrative error policy example. Skip only when business rules allow excluding that record from the result; retry only errors likely to resolve themselves. Save skipped items and their reasons so data can be fixed or compensated. For writers with side effects outside the database, add idempotency so retries do not create duplicate actions.

## 6. When a Tasklet is still the right choice

Having a large number of records does not automatically force using chunk. If the database can perform the work with an efficient set-based statement, a Tasklet calling a service or stored procedure can be a good choice.

For example, deleting expired staging records with a single SQL statement:

```java
@Component
public class DeleteExpiredStagingTasklet implements Tasklet {

    private final JdbcTemplate jdbcTemplate;

    public DeleteExpiredStagingTasklet(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        int deleted = jdbcTemplate.update("""
                DELETE FROM staging_records
                WHERE expires_at < CURRENT_TIMESTAMP
                """);

        contribution.incrementWriteCount(deleted);
        return RepeatStatus.FINISHED;
    }
}
```

This Tasklet does not read each record into Java. The database executes the set-based operation and returns the number of deleted rows. This approach can be more efficient than a Java pipeline if the operation is simple, can be executed atomically, and has a reasonable transaction duration.

However, a statement deleting millions of rows can still create a large transaction, hold locks, and generate significant transaction logs. If the database does not handle a one-shot operation well, you can split it into bounded deletions, such as deleting one group of IDs per pass, and return `CONTINUABLE` so TaskletStep repeats. This approach needs a clear stop condition, idempotency, and a suitable progress tracking mechanism.

A Tasklet also suits:

- Calling a stored procedure with controlled boundaries and execution duration.
- Creating a manifest file or control file.
- Checking preconditions before starting a pipeline.
- Changing the status of a data batch with a set-based operation.
- Calling an orchestration service to trigger other work.

## 7. If a Tasklet needs to be split into multiple passes

A Tasklet can return `RepeatStatus.CONTINUABLE` to ask Spring Batch to call `execute()` again. This is useful for a task that can be split into small passes, such as deleting data by groups of IDs. Each call can process a bounded group and end that pass's transaction.

General example:

```java
@Component
public class PurgeOldRecordsTasklet implements Tasklet {

    private final PurgeService purgeService;

    public PurgeOldRecordsTasklet(PurgeService purgeService) {
        this.purgeService = purgeService;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        int deleted = purgeService.deleteNextPage(500);
        contribution.incrementWriteCount(deleted);

        return deleted == 0
                ? RepeatStatus.FINISHED
                : RepeatStatus.CONTINUABLE;
    }
}
```

This is a per-pass bounded repeating task, not a general replacement for chunk processing. If the work truly needs a reader, processor, and writer per item, per-item skip/retry, and reader checkpoints, use a chunk-oriented Step so the framework manages those parts.

When a Tasklet repeats over multiple passes, ensure:

- Each call makes visible progress.
- There is a reliable stop condition to avoid infinite loops.
- Already-committed operations can be recognized on restart.
- No duplicate side effects are created when a pass is retried or re-executed.
- Sufficient logs and metadata exist so operators know how far processing has progressed.

## 8. Factors to consider when splitting out a pipeline

When moving a large Tasklet to chunk-oriented processing, clearly define the boundary of responsibilities for each component:

| Component | Responsibility |
|---|---|
| `ItemReader` | Reads the next item and returns `null` at end of input; supports checkpoints if restart is needed |
| `ItemProcessor` | Validates, transforms, or filters one item; avoids holding shared mutable state |
| `ItemWriter` | Writes the chunk's group of items; ensures safe writing on retry |
| `Step` | Configures chunk size, transaction manager, retry, skip, and listeners |
| `JobRepository` | Stores Job/Step metadata and execution status |

Some design questions:

1. Can the data source be read sequentially or by pages?
2. Can a stable ordering and data scope be defined for each JobInstance?
3. Can an item be processed independently, or must it rely on the previous item?
4. Can the writer write in batches, and which resources does the transaction cover?
5. If a chunk fails, which items might be re-read or rewritten?
6. Do faulty records need to be skipped, logged to an error list, and compensated?
7. Can the reader save checkpoints and restore position after restart?
8. Are there side effects in external systems requiring idempotency?

Not every pipeline can be moved directly to chunk processing. If business rules require sequential processing with accumulated state, you may need to group data by business key or use multiple Steps. If an operation depends on the entire dataset, it can be split into an aggregation Step after the item-processing Steps complete.

## 9. Impact on performance and operability

Chunk size is a parameter that needs measuring and tuning. A chunk that is too small can increase commits and round trips; a chunk that is too large can increase memory and transaction duration. Do not pick a value purely by intuition.

When comparing a large Tasklet with chunk processing, measure:

- Total Job duration and throughput (items/second).
- Heap usage, garbage collection, and CPU.
- Transaction duration, lock waits, and connection pool usage.
- Counts of items read, written, filtered, and skipped.
- Counts of commits, rollbacks, and retries.
- Recovery time after simulating a failure midway.
- Load generated on the database and dependent services.

A set-based Tasklet can be faster than chunk because the database processes data close to storage. A chunk Step can be more reliable for pipelines that need per-item processing. The right choice depends on the nature of the work and operational limits, not solely on the number of data rows.

## 10. Common mistakes

**Loading all data into a List:** memory grows with data volume and can exhaust JVM heap. Use a sequential or paging reader if many items must be processed.

**Reading, processing, and writing millions of items inside one `execute()`:** the transaction can stretch out, progress is hard to observe, and a mid-run failure forces custom recovery code. Split into chunks if this is an item pipeline.

**Writing rudimentary retry/skip yourself:** can silently miss important errors or duplicate side effects. Use a fault-tolerant Step when appropriate and define error policies per business rules.

**No checkpoints:** restart may have to redo the entire job. Use a reader supporting `ItemStream` or save controlled progress.

**Choosing a chunk size that is too large:** reduces commit frequency but can increase memory, transaction hold time, and rollback scope.

**Using chunk for a simple set-based SQL statement:** reading each item through Java can consume more resources than letting the database perform one set operation.

**Assuming database rollback undoes external services:** REST APIs, email, or filesystems usually do not participate in database transactions. Idempotency and reconciliation are needed.

## Conclusion

You should not use a Tasklet to manually load, process, and write a pipeline with a large volume of items inside one `execute()` call. Doing so easily consumes memory, holds transactions too long, lacks per-item counters, and forces the application to build retry, skip, checkpoint, and restart mechanisms itself. For multi-item read-process-write pipelines, chunk-oriented processing provides better-suited transaction boundaries, reader/processor/writer abstractions, fault tolerance, and progress metadata. A Tasklet remains a good choice for single tasks, set-based operations, or clearly scoped orchestration work; what matters is choosing the model based on the nature of the work and designing for recoverability from the start.
