# Transactions When Updating Batch Metadata

In Spring Batch, `JobRepository` stores metadata describing the state of jobs, job instances, job executions, step executions, and execution contexts. This data is updated continuously as the job starts, as steps run, after each chunk, and when the job finishes. Because metadata determines the ability to monitor and restart, the update operations must be performed in transactions with clear boundaries.

A transaction ensures that a group of metadata changes is recorded consistently. If a chunk fails during processing and the transaction rolls back, the corresponding checkpoint also needs to be rolled back so that the next run does not skip data that has not been committed. In the common JDBC configuration, `JobRepository` uses a `PlatformTransactionManager` to manage transactions when reading and writing the `BATCH_*` metadata tables.

## Why Does Updating Metadata Need a Transaction?

Spring Batch metadata is not just a status log. The framework relies on metadata to decide which jobs are running, which steps have completed, and where to continue on restart. If state is partially written or a checkpoint does not match business data, a restart may skip or repeat data processing.

For example, a step reads 100 orders, processes them, and writes them to the database. After the writer completes, Spring Batch updates the item counts and the `ExecutionContext` to record the next read position. If the order data has been committed but the checkpoint has not been saved, a restart may re-read the chunk just processed. Conversely, if the checkpoint is saved before the business data commits, a restart may skip orders that were not actually written.

A transaction helps coordinate related operations in a single commit unit. When metadata and business data take part in one transaction on the same database resource, they can commit or roll back together. This is the foundation for Spring Batch to maintain reliable checkpoints.

## How Does JobRepository Manage Transactions?

`JobRepository` is the abstraction that manages metadata. With a JDBC repository, operations are performed on the Spring Batch schema through the configured `DataSource` and `PlatformTransactionManager`.

Common groups of operations:

| Operation | Related Metadata | Purpose |
| --- | --- | --- |
| Create a `JobExecution` | `BATCH_JOB_EXECUTION` and related tables | Record a new run of a `JobInstance` |
| Update a `JobExecution` | Status, start/end time, exit code | Track the run's lifecycle |
| Create/update a `StepExecution` | `BATCH_STEP_EXECUTION` | Track the step's status and figures |
| Update the execution context | `BATCH_JOB_EXECUTION_CONTEXT`, `BATCH_STEP_EXECUTION_CONTEXT` | Store checkpoints and recovery state |
| Store job parameters | `BATCH_JOB_EXECUTION_PARAMS` | Record the parameters used in the run |

The metadata write operations are performed by the repository in transactions according to the configuration. The application usually calls Spring Batch APIs such as `JobLauncher`, `JobRepository`, or step components; the framework is responsible for calling the repository at the right time. You should not directly update the `BATCH_*` tables yourself to change execution state.

With the JDBC `JobRepository`, the methods that create an instance or execution need protection against concurrent launch requests. Spring Batch usually uses a stricter isolation level for the group of `create*` operations (the common default is `SERIALIZABLE`) to prevent two processes from creating metadata for the same logical job. The remaining repository operations are also performed in transactions, with an isolation level per the transaction manager/database configuration. You can customize the isolation for the create operation, but only do so after clearly understanding the contention and the schema's unique constraints.

## Transaction Boundaries in the Job Lifecycle

A job has multiple metadata-update phases. They are not necessarily in a single transaction that lasts from launch to completion.

```text
JobLauncher
    |
    | transaction creating JobExecution
    v
JobExecution = STARTING / STARTED
    |
    v
Create and start StepExecution
    |
    v
Chunk transaction 1
    |-- read / process / write
    |-- update ExecutionContext and StepExecution
    +-- COMMIT or ROLLBACK
    |
    v
Chunk transaction 2
    |-- read / process / write
    |-- update checkpoint and step figures
    +-- COMMIT or ROLLBACK
    |
    v
Update StepExecution status
    |
    v
Update JobExecution status
    |
    v
COMPLETED / FAILED / STOPPED
```

The diagram shows the phases at a conceptual level. Spring Batch can open separate transactions for the execution-creation operation, the start/end status updates, and the chunks. A job usually has many short transactions throughout its run, which lets data be committed per processing unit instead of holding one enormous transaction.

### When Creating a JobExecution

When `JobLauncher` receives a request to run a job, Spring Batch looks up or creates a `JobInstance` based on the job name and identifying parameters, and then creates a `JobExecution`. The repository writes the initial metadata in a transaction. If creating the execution is unsuccessful, the job cannot continue as a valid run.

The isolation level on the create operation plays an important role when multiple requests launch the same job with the same identifying parameters. It helps prevent two concurrent threads from creating two conflicting instances or executions for the same identity.

### When a Step Starts and Ends

Spring Batch creates or updates a `StepExecution` to store the step's status, start/end time, and the number of items read/written, skipped, committed, and rolled back. When the step moves to an end state, the metadata is updated through the repository in the corresponding transaction.

### In Each Chunk

With a chunk-oriented step, each chunk is usually one transaction unit. The framework reads and processes a group of items, calls the writer, updates the status and execution context, and then commits the transaction per the configuration. If an error causes the transaction to roll back, the changes inside that transaction are rolled back.

### When the Job Ends

After the steps finish, Spring Batch updates the final status of the `JobExecution`, such as `COMPLETED`, `FAILED`, or `STOPPED`, along with the time and exit information. These updates are managed by the repository in its own transaction.

## Chunk Transactions and Checkpoints

With chunk processing, `commit-interval` determines the number of items gathered into a chunk before committing. For example `chunk(100, transactionManager)` means each chunk processes at most 100 items under the transaction manager provided to the step.

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

In the example, `transactionManager` manages the chunk's transaction. `JobRepository` is passed into `StepBuilder` so the step stores metadata. For business data and checkpoint metadata to commit consistently, the step's transaction manager and the repository's transaction manager need to be configured to suit the same database resource when both kinds of data live in one database.

During the chunk commit, Spring Batch updates the `StepExecution` and `ExecutionContext` according to the step's lifecycle. A reader that supports state can save its current position so a restart knows where to continue. The checkpoint must correspond to the committed data. If the transaction rolls back, the checkpoint saved in the same transaction also rolls back; the next run can re-read that chunk.

`commit-interval` is a decision that affects both performance and rollback scope:

| Chunk Size | Common Impact |
| --- | --- |
| Small | Short transactions, fewer items rolled back, but the number of commits and metadata updates increases |
| Large | Fewer commits, possibly higher throughput, but longer transactions and a rollback may have to reprocess more items |

There is no single optimal value for every job. Consider per-item processing time, database load, locks, memory footprint, restart requirements, and metadata update frequency.

## Shared or Separate Transaction Managers?

An application can have a transaction manager for business data and a transaction manager for batch metadata. The right configuration depends on whether the two kinds of data live in the same database or in independent resources.

### Metadata and Business Data Share a Database

This is the simplest case for coordinating transactions. If `JobRepository` and the writer use the same `DataSource` and the same `PlatformTransactionManager`, repository operations called within an active transaction can join the same transaction under a suitable propagation (usually `REQUIRED`).

```text
Chunk transaction
       |
       +---- Writer writes the ORDER table
       |
       +---- JobRepository updates BATCH_STEP_EXECUTION
       |
       +---- JobRepository stores STEP_EXECUTION_CONTEXT
       |
       +---- COMMIT / ROLLBACK in the same transaction
```

If the writer or the repository hits an error before commit, the transaction can roll back both the business data and the checkpoint metadata enlisted in the same transaction. This helps reduce the risk of the checkpoint getting ahead of the data.

The important condition is that the operations actually use the same transaction resource and transaction manager. Merely having the same database URL or the same database server is not enough to guarantee that two separate connections take part in one transaction.

### Metadata and Business Data Use Different Databases

Some systems separate the batch metadata database from the business database for authorization, load isolation, or operational requirements. In that case, the repository and the writer may use two `DataSource`s and two different transaction managers.

Two local transaction managers do not coordinate by themselves to commit or roll back atomically. For example, the writer commits orders to the business database, and then the transaction writing the checkpoint to the metadata database fails. On restart, Spring Batch may re-read items that were already written to the business database. The reverse can also happen if the checkpoint commits while the business data has not been saved.

```text
Business transaction              Metadata transaction
        |                                  |
        v                                  v
  Write ORDER rows                  Write checkpoint
        |                                  |
     COMMIT                              error
        |                                  |
        +---------- restart ---------------+
                   |
                   v
          Items may be re-read
```

When resources are separated, you need to design for recoverability:

- Make the writer idempotent: writing the same business key multiple times still gives the correct result.
- Use a unique constraint or an upsert with clear business rules to avoid duplicate records.
- You can record processing state in the business system to reconcile when metadata and data diverge.
- Define the behavior when one side commits while the other rolls back or loses its connection.
- If the requirements truly need atomic commit across multiple resources, evaluate a distributed transaction/XA solution and its operational cost.

In many systems, idempotency and reconcilability are the practical way to handle errors between two databases. You should not assume that configuring two transaction managers will automatically create a distributed transaction.

## Propagation and Nested Transactions

Propagation determines whether a transactional operation joins an existing transaction or creates its own. In batch processing, this choice directly affects the consistency of business data and checkpoints.

`REQUIRED` is usually the suitable propagation when a writer or repository operation needs to join the active chunk transaction. If a transaction already exists, the operation joins it; if not, it creates a new one.

`REQUIRES_NEW` temporarily suspends the current transaction and opens a separate one. If the writer uses `REQUIRES_NEW` to commit business data while the chunk transaction can still roll back, the separately committed data may exist even though the chunk checkpoint rolls back. On restart, the item may be processed again. This approach is only suitable when the application has designed for idempotency and truly needs an independent transaction.

`NESTED` relies on the savepoint capability of the transaction manager and the database. Not every transaction manager or resource supports it the same way. Do not choose a propagation just to dodge a transaction error; you need to determine clearly which state must commit together and which can be independent.

A service called from an `ItemWriter` usually joins the chunk transaction if the service's transaction configuration allows it. Check the `@Transactional` annotation, the propagation, the datasource, and the injected transaction manager; a method that appears to be inside the chunk may open its own transaction if it is configured differently.

## Configuring JobRepository and Transaction Attributes

With Spring Boot, the application usually declares a `DataSource` and lets auto-configuration set up the JDBC `JobRepository` along with the batch components. The repository needs a suitable transaction manager to write metadata. The step also needs a transaction manager for the chunk.

In a self-managed configuration, you need to determine clearly:

1. Which `DataSource` holds the `BATCH_*` schema.
2. Which `PlatformTransactionManager` manages the `JobRepository` operations.
3. Which `PlatformTransactionManager` manages the step/chunk transaction.
4. Whether the two transaction managers manage the same resource.
5. Which isolation level and timeout suit the database and the actual load.

In Spring Batch versions that support explicit JDBC repository configuration, the repository is created with a datasource, a transaction manager, and transaction attributes for the create/update operations. The specific configuration API differs between Spring Batch and Spring Boot versions, so use the configuration approach that matches your project's version. Do not mix old configuration examples with the new builder API without checking compatibility.

Some properties to consider:

| Property | Operational Meaning |
| --- | --- |
| Isolation level for the create operation | Reduces race conditions when multiple requests create an instance/execution |
| Transaction propagation | Determines whether a repository operation joins the existing transaction or opens a new one |
| Transaction timeout | Limits the transaction's wait time; it must be compatible with chunk time and database load |
| Table prefix | Lets the repository use metadata table names with a different prefix if the schema is configured accordingly |

Do not lower the isolation level of the create operation just to reduce locks without checking the contention errors that may appear. If multiple nodes launch a job, you need to keep the mechanism that protects instance identity and check the schema's unique constraints.

## Error Handling and Rollback

When an exception occurs in a chunk, the result depends on the exception type, the retry/skip configuration, and the transaction boundary. If the error causes the chunk to roll back, the database operations that took part in that transaction will be rolled back. Spring Batch can retry the item or chunk per the fault-tolerance configuration, or end the step in a failed state.

Common cases:

| Situation | Usual Transaction Result | What to Check |
| --- | --- | --- |
| The writer throws an exception before commit | The chunk transaction rolls back | Does the writer write to a system outside the transaction? |
| A database error when updating metadata within a chunk | The chunk transaction may roll back | Do metadata and business data share the same transaction resource? |
| The application stops after a chunk commit | The committed chunk's data and checkpoint remain | Does the reader restore its state correctly? |
| The application stops before commit | The uncommitted transaction is rolled back when the connection is released | Does the writer have side effects outside the database? |
| Two databases use two transaction managers | One side may commit while the other fails | Is there idempotency and a reconciliation process? |

Not every side effect is rolled back by the database. Sending email, calling HTTP, publishing a message, or writing a file may have already happened before the chunk transaction rolls back. For these side effects, you should use the outbox pattern, communication with an idempotency key, or a confirmation/reconciliation mechanism to avoid duplicate sends or processing on retry.

## Isolation, Locks, and Concurrent Runs

Metadata transactions are also affected by concurrency. When multiple schedulers, nodes, or operators launch a job, the repository must protect the creation of `JobInstance` and `JobExecution`. A higher isolation level helps prevent some race conditions, but it can increase lock contention depending on the database.

Operational principles:

- Use a shared durable `JobRepository` for the nodes that take part in one batch system.
- Use stable identifying parameters so nodes recognize the same logical job.
- Keep the schema and Spring Batch version compatible across all nodes.
- Set the transaction timeout to suit chunk processing time and the database's limits.
- Monitor deadlocks, lock waits, the connection pool, and commit time.
- Do not arbitrarily reduce isolation or remove constraints to handle contention errors.

If transactions frequently time out or deadlock, check the writer's queries, the order of record updates, the chunk size, indexes, and lock-holding time. Simply increasing the timeout may only make the error appear later.

## Example Scenario: Metadata and Business Data in the Same Transaction

Suppose `importOrdersStep` reads data from a file and writes orders to the `ORDERS` table. Both the `ORDERS` table and the `BATCH_*` tables live in the same PostgreSQL database, and the writer and `JobRepository` use the same transaction manager.

A chunk of 100 orders is processed as follows:

1. The reader takes 100 items and the processor transforms them.
2. The writer writes the 100 orders.
3. Spring Batch updates the `StepExecution` figures and the checkpoint in the `ExecutionContext`.
4. The transaction commits.

If step 3 hits an error before commit, the writer and the metadata checkpoint take part in the same transaction, so the changes in the chunk roll back. On restart, the reader can re-read those 100 items. If the commit succeeds and then the application stops, the order data and the checkpoint have been saved in the same transaction; the reader can continue from the next chunk.

This design still needs to ensure the reader saves state correctly and the writer creates no side effects outside the transaction. But it provides a clear commit boundary between business data and metadata.

## Example Scenario: Metadata and Business Data in Two Databases

Suppose `BATCH_*` lives in the database `batch_meta`, while orders live in the database `orders_db`. The step uses the transaction manager of `orders_db` to write data; the repository uses the transaction manager of `batch_meta` to store checkpoints.

If the writer commits to `orders_db` successfully but updating the context in `batch_meta` fails, the next run may reprocess those orders. When the writer has a unique business key and handles upsert properly, reprocessing can be safe. If the writer always inserts a new row without controlling duplicates, the data will be duplicated.

Therefore, separating databases needs to come with an idempotency strategy, processing-state checks, and a recovery procedure. If the business requirements do not accept any period of inconsistency between the two databases, you need to evaluate a distributed transaction or redesign the data flow so it can be recovered.

## Diagnosing Metadata Transaction Errors

When a job hits an error related to transactions or metadata, start from the execution state and the log at the exact time the error occurred.

### Deadlock or Lock Timeout on BATCH_* Tables

Check whether multiple jobs are creating instances/executions or updating metadata concurrently. Look at the isolation level, the queries holding locks, the database indexes, and the number of workers. Do not directly modify the state in the tables to release locks.

### JobExecution Created but the Step Did Not Start

The execution-creation transaction may have committed but the next step failed when creating or updating the `StepExecution`, or the application was stopped between the two phases. Check `BATCH_JOB_EXECUTION`, the execution state, and the log at the time of moving to the step.

### Step Rolled Back but the Data Still Exists

Determine whether the writer uses a different transaction manager, the `REQUIRES_NEW` propagation, a different connection, or a system outside the database. Check which datasource the actual transaction was opened on and which side effects committed independently.

### Restart Re-reads Data That Was Already Written

Check the checkpoint in the `ExecutionContext`, the reader state, the commit timing, and whether metadata/business data share the same transaction. If you use two databases, check the possibility that one side committed while the other failed; then evaluate the writer's idempotency.

### Metadata Not Updated Due to a Connection Error

Check the connection pool, timeouts, schema write permissions, the database status, and the transaction manager configured for the repository. When the metadata database is unavailable, the job may be unable to create an execution or update state safely.

Do not fix this by manually updating `STATUS`, `VERSION`, or the execution context in the `BATCH_*` tables. Direct edits can break the relationships among instance, execution, step, and checkpoint. Restore the database or use Spring Batch's operational API after determining a valid state.

## Principles for Designing Transactions for Batch Metadata

When building a production job, clearly answer the following questions:

1. Do metadata and business data live in the same database or different databases?
2. Which transaction manager is used for `JobRepository` and which is used for the step?
3. If it is the same database, do the repository operations actually take part in the chunk transaction?
4. If it is a different database, how does the application handle one side committing while the other rolls back?
5. Which checkpoint does the `ExecutionContext` store, and does that checkpoint match the committed data?
6. Is the writer idempotent when a chunk is retried or restarted?
7. Are the isolation, timeout, and chunk size suitable for the load and concurrency?
8. Are there enough logs, metrics, and a reconciliation process to investigate a divergent state?

For a system that uses one relational database for both batch metadata and business data, sharing the `DataSource` and transaction manager is usually the simplest way to synchronize a chunk's commit with its checkpoint. For a system with separate databases, you need to design clear recoverability; if you do not use a distributed transaction, idempotency and reconciliation are the important mechanisms for handling divergent commits.

## Key Takeaways

`JobRepository` updates batch metadata through the configured transaction manager. The phases of creating an execution, updating step/job status, and committing each chunk have their own transaction boundaries. In chunk processing, business data and the checkpoint should commit or roll back together when they share the same transaction resource. If metadata and business data are in two databases or use two independent transaction managers, there is no default atomic commit guarantee; the writer needs to be idempotent and the system needs an appropriate recovery and reconciliation mechanism. Isolation, propagation, timeout, and chunk size all affect the consistency and performance of a batch job.
