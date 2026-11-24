# Transaction metadata and business data

In Spring Batch, each job run creates and updates two groups of data with different purposes: **batch metadata** and **business data**. Batch metadata describes the execution process, while business data is the domain data that the job reads, transforms, or writes to the target system.

These two groups of data are typically updated in the same processing flow. Therefore, the transaction design must answer the question: when a chunk or a tasklet fails, do the business data and the metadata checkpoint commit or roll back together? If they are not consistent, a restart may write duplicate data or skip work that was not completed.

Spring Batch provides `JobRepository` to manage metadata and uses the step's transaction manager to coordinate processing transactions. When metadata and business data share a transaction resource and an appropriate transaction manager, the related changes can commit or roll back together. When they reside in independent resources, there is no atomic commit by default; the application must design idempotency, an outbox, or a corresponding recovery mechanism.

## Distinguishing batch metadata from business data

### Batch metadata

Batch metadata records the identity and run history of a job. With a JDBC `JobRepository`, the data is typically stored in Spring Batch tables with the `BATCH_` prefix.

| Metadata group | Example content | Purpose |
| --- | --- | --- |
| `JobInstance` | Job name and identifying parameters | Identifies a logical job |
| `JobExecution` | Status, start/end times, exit code, errors | Tracks one execution |
| `StepExecution` | Step status, number of items read/written/skipped/filtered, commit and rollback count | Tracks the progress of a step |
| `JobParameters` | Business date, file name, data range, and the identifying flag | Determines the input and the identity of the run |
| `ExecutionContext` | Next read position, page number, last processed key | Stores checkpoints for restart |

Commonly encountered metadata tables include `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_JOB_EXECUTION_PARAMS`, `BATCH_STEP_EXECUTION`, `BATCH_JOB_EXECUTION_CONTEXT`, and `BATCH_STEP_EXECUTION_CONTEXT`. The column names, data types, and specific schema depend on the Spring Batch version and the database management system.

### Business data

Business data is the domain data that the job processes, for example:

- Orders, transactions, invoices, or customer information.
- Staging records loaded from a source file.
- Computation results, balances, reports, or aggregated data.
- Business processing state, audit records, or outbox events.

These tables are designed by the application/domain. Spring Batch does not decide the business schema itself and also does not use the `BATCH_*` tables as the place to store all input data or results.

For example, an order import job may use:

```text
Batch metadata database/schema          Business database/schema
-------------------------------         ------------------------
BATCH_JOB_INSTANCE                      orders
BATCH_JOB_EXECUTION                     order_items
BATCH_STEP_EXECUTION                    import_audit
BATCH_STEP_EXECUTION_CONTEXT            outbox_events
```

The two groups can reside in the same database or in two separate databases. Separating schemas helps with organization and permissions; but merely being on the same database server or having the same database name is not enough to guarantee that they participate in the same transaction.

## Why do transactions between the two groups of data matter?

Spring Batch uses metadata to determine how far a step has processed. If the checkpoint says a group of items has completed but the business data has not been saved, a restart may skip those items. If the business data has been saved but the checkpoint has not been updated, a restart may reprocess the items and create duplicate data.

For example, a chunk of 100 orders:

1. The reader reads 100 orders.
2. The processor normalizes and validates the data.
3. The writer writes the 100 orders into the `orders` table.
4. Spring Batch updates the `StepExecution` figures and the checkpoint in the `ExecutionContext`.
5. The transaction commits.

When the business rows and the checkpoint participate in one transaction, they can be committed or rolled back as a unit. If the two changes commit independently, there may be a window of time in which one side has been saved and the other has not.

```text
One chunk
   |
   +----> Write business rows
   |
   +----> Update StepExecution / ExecutionContext
   |
   v
Transaction commit
   |
   +----> Business data saved
   +----> Checkpoint saved
```

The goal is for the checkpoint to accurately reflect the business data that has been committed. The transaction boundary is the key mechanism for maintaining this relationship.

## When metadata and business data share a transaction

This is the easiest case to coordinate. For example, both the `orders` table and the `BATCH_*` tables are in the same PostgreSQL database, and the step and the `JobRepository` use the same `DataSource` and `PlatformTransactionManager`.

In a chunk-oriented step, the step's transaction manager opens the transaction for the chunk. The writer writes business data in that transaction. The repository operations that update the `StepExecution` and the execution context can participate in the same transaction if the `JobRepository` is configured to use the same resource and an appropriate propagation.

```text
                  One JDBC transaction
                           |
             +-------------+-------------+
             |             |             |
             v             v             v
       INSERT orders   UPDATE audit   UPDATE BATCH_*
             |             |             |
             +-------------+-------------+
                           |
                      COMMIT / ROLLBACK
```

If the writer throws an exception before the commit, the business data changes in the transaction are rolled back. The checkpoint updated in the same transaction is also rolled back. On restart, Spring Batch can re-read the uncommitted chunk.

If the transaction commits successfully, the business data and the related checkpoint are saved together. The job can continue from the next piece of data according to the reader's state.

### Configuring a step that shares the transaction manager

An example in Spring Batch 5 with a JDBC writer:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        @Qualifier("batchTransactionManager")
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

In the illustrative configuration, `batchTransactionManager` must manage the correct datasource that the writer and the repository use if the goal is a shared transaction. The bean name is only an example; the application can use a different name. If there are multiple transaction managers, use an explicit qualifier to avoid injecting the wrong bean.

There is no need to open a transaction manually in an ordinary writer. The writer should participate in the chunk transaction managed by the step. If the writer calls a service with `@Transactional`, the default `Propagation.REQUIRED` typically allows the service to join the current transaction when the transaction manager and resource are the same.

### A tasklet sharing the transaction

With `TaskletStep`, the usual transaction boundary is one transaction per call to `Tasklet.execute`. If the tasklet updates business data with a `JdbcTemplate` using the same datasource and transaction manager as the step, those SQL statements can commit or roll back together with the metadata the repository updates in the transaction.

If the tasklet returns `RepeatStatus.CONTINUABLE`, each subsequent call has its own transaction. Therefore, a unit of business work and its corresponding checkpoint should be updated within the same invocation/transaction.

## When metadata and business data use different transaction managers

An application may separate the metadata database from the business database for permissions, load isolation, backup, or independent operation. For example:

- `batch_meta_db` stores the `BATCH_*` tables.
- `orders_db` stores orders and related data.

When the repository and the writer use two different datasources or two different local transaction managers, the two transactions do not automatically commit or roll back atomically.

```text
Transaction of orders_db           Transaction of batch_meta_db
          |                                  |
          v                                  v
     Write orders                     Write checkpoint
          |                                  |
      COMMIT                              ROLLBACK
          |                                  |
          +------------ restart -------------+
                         |
                         v
                Item may be reprocessed
```

Two main risk scenarios:

| State after the error | Possible consequence |
| --- | --- |
| Business data committed, metadata checkpoint not committed | Restart may re-read the item and the writer writes a duplicate |
| Metadata checkpoint committed, business data not committed | Restart may skip the item even though the business result has not been saved |

The specific order of operations and transactions depends on the repository configuration, the transaction manager, and the resource. Do not assume the commit order between two local transaction managers creates atomicity.

### The same database server can still mean two transactions

For example, two datasources point to the same PostgreSQL server but use separate connection pools. If each datasource opens its own connection and is managed by its own transaction manager, the operations can belong to two independent transactions. Similarly, using two schemas on the same database but configuring two separate transaction managers does not automatically make them one transaction.

To have a shared transaction, ensure both groups of data participate in the same transaction resource and an appropriate transaction manager, or use a clearly configured distributed transaction mechanism.

## Strategies for maintaining consistency

Not every application needs the same implementation. The choice depends on the number of resources, the required level of consistency, and the business recoverability.

### Share the transaction resource

If the business data and the metadata can reside in the same database/resource, this is typically the simplest solution. Use the same `DataSource`, an appropriate transaction manager, and a clear repository/step configuration so that the business rows and the checkpoint are updated in the same transaction.

Advantages:

- Business data and the checkpoint can commit/roll back together.
- Restart is more predictable because the checkpoint is tied to committed data.
- No distributed transaction coordination is needed.

Limitations:

- Batch metadata and the business workload depend on one database.
- The metadata write load and the business data write load compete for resources.
- May not meet permission, isolation, or multi-system architecture requirements.

### Idempotent writer

When atomic commit across resources cannot be guaranteed, the writer should handle receiving the same item again safely. Some approaches:

- Create a unique constraint on the business key.
- Use an upsert with clear rules.
- Store a processing key to recognize items that have been applied.
- Use an idempotency key when calling an API or publishing a message.
- Check the current state before performing an operation that could be repeated.

A PostgreSQL upsert example:

```sql
INSERT INTO orders (order_id, customer_id, amount, status)
VALUES (:orderId, :customerId, :amount, :status)
ON CONFLICT (order_id)
DO UPDATE SET
    customer_id = EXCLUDED.customer_id,
    amount = EXCLUDED.amount,
    status = EXCLUDED.status;
```

An upsert helps avoid duplicates by `order_id`, but you need to determine whether updating again is valid. If the target record may have been updated more recently by another process, unconditionally overwriting it can lose data.

### Business processing ledger

For a job processing large volumes of data, you can store a business ledger recording each item or each group that has been applied. For example, a `batch_processed_item` table storing `job_business_key`, `item_key`, `processed_at`, and the result.

The ledger should be in the same transaction as the business changes it represents. When the writer receives an item again, it checks the ledger or uses a unique key to avoid applying the change twice. This approach is useful when the Spring Batch metadata is in a separate resource but the business system still needs to protect itself against replay.

Do not treat the business ledger as a replacement for the `JobRepository`. The ledger answers the question of whether a business item has been applied; the repository answers the question of what state the job/step execution is in and where to restart from.

### Transactional outbox for messages

If a batch job updates business data and needs to emit a message, do not rely on the assumption that a database transaction can roll back a message already received by the broker.

A common pattern is the transactional outbox:

```text
One business DB transaction
          |
          +---- Write business rows
          |
          +---- Write outbox event
          |
          +---- COMMIT
                    |
                    v
             Outbox publisher
                    |
                    v
              Message broker
                    |
                    v
             Idempotent consumer
```

The business row and the outbox event are written in the same transaction in the business database. A separate publisher reads unsent events and emits them to the broker. If the publisher sends successfully but has not yet marked the event as sent, it may send it again; therefore the event needs a stable ID and the consumer needs to be idempotent.

The outbox ensures the event is stored together with the business change; it does not create an atomic transaction between the database and the broker. It turns the problem of sending messages into a flow that can be retried and reconciled.

### Distributed transaction or XA

If a business requirement mandates that business data and metadata across multiple resources must commit atomically, you can evaluate a distributed transaction/XA with a transaction coordinator and XA-capable resources.

Distributed transactions have costs in configuration, performance, operations, recovery logs, and system dependencies. Not every database, driver, or broker supports the same level. Choose it only when the atomicity requirement is truly necessary and the operations team is able to manage the coordinator and in-doubt states.

In many batch systems, idempotency and reconcilability are simpler and more scalable than putting every resource into XA.

## JobRepository and the step's transaction

`JobRepository` manages metadata, but that does not mean every metadata update across the whole job lifecycle is in the same transaction as the business data.

Operations such as creating a `JobExecution`, marking the start/end of a step, updating a `StepExecution`, or saving an execution context occur at different points in the lifecycle. In chunk processing, the metadata updates related to the checkpoint can participate in the chunk transaction when the repository and the step are configured compatibly. State transitions at the start/end of a job or step may belong to separate transactions.

This means:

- A business chunk may have committed but the final status update step of the job hits an error.
- A `JobExecution` may be marked `FAILED` even though some earlier business chunks committed successfully.
- A `COMPLETED` metadata status does not by itself replace verifying business results if the job writes to multiple independent resources.
- On restart, Spring Batch relies on the repository state and the checkpoint; the writer still needs to be safe against items that have not been confirmed or are resent.

Therefore, distinguish the transaction of each chunk/tasklet invocation from the transaction that manages the lifecycle state transitions of the job and step.

## Example: a chunk writing to the database together with metadata

Suppose the job `importOrdersJob` imports a CSV file into the `orders` table. `businessDate` is an identifying parameter. `FlatFileItemReader` reads line by line, the processor normalizes the data, and `JdbcBatchItemWriter` inserts the orders.

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        JdbcBatchItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(200, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

Suppose the `JobRepository` and the writer use the same datasource/transaction manager. Each chunk of up to 200 items can write business rows and update the checkpoint in the same transaction. If the third chunk fails before the commit, that chunk's changes roll back; the two earlier chunks that have committed still exist. On restart with the same identifying parameters, the reader restores the checkpoint to continue from the unfinished chunk.

If `orders` is in a separate database and the writer uses a different transaction manager from the repository, the checkpoint and the business rows may become out of step when one transaction commits and the other fails. In that case, a unique business key or an upsert helps the writer tolerate replay.

## Example: a tasklet updating business data and metadata

A tasklet can perform a short business operation such as updating the status of an accounting period and writing a checkpoint.

```java
public class CloseAccountingPeriodTasklet implements Tasklet {

    private final JdbcTemplate jdbcTemplate;

    public CloseAccountingPeriodTasklet(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        String period = chunkContext.getStepContext()
                .getJobParameters().get("period").toString();

        jdbcTemplate.update(
                "UPDATE accounting_period SET status = 'CLOSED' WHERE period_code = ?",
                period);

        contribution.getStepExecution()
                .getExecutionContext()
                .putString("closedPeriod", period);

        return RepeatStatus.FINISHED;
    }
}
```

If the tasklet uses the same transaction resource and transaction manager as the repository, the business state change and the related execution context can be committed in the same transaction of the tasklet invocation. If the business database differs from the metadata database, you need an additional business mechanism to ensure that closing the period can be safely re-executed.

In production code, you should validate the required parameter, use an API that retrieves parameters with an appropriate type, and handle the case where the accounting period is already closed. An `UPDATE` operation should have a condition or business key so that calling it again does not produce incorrect effects.

## Handling restart and inconsistent state

When a job fails, before restarting you need to determine:

1. Did the last chunk or tasklet invocation commit its business data?
2. Has the corresponding checkpoint been saved in the `ExecutionContext`?
3. Do the metadata and business data share a transaction resource?
4. Can the writer be called again with the same item?
5. Is there a ledger, unique key, idempotency key, or outbox to detect operations that have been applied?

Do not just look at a `JobExecution` in the `FAILED` state and conclude that all business changes have rolled back. Earlier chunks may have committed. Conversely, do not see the checkpoint advance and assume all external side effects have completed.

A recovery process may include:

- Reading the execution and step metadata to determine the run, the checkpoint, and the error.
- Reconciling business records or the ledger by business key.
- Checking the message/outbox or the state of the target system if the job has side effects outside the database.
- Determining whether to restart the same `JobInstance` or create a new logical job according to the business.
- Ensuring the writer is idempotent before restarting or replaying.
- Recording the recovery decision so it can be audited.

If you need to fix business data, use a business process or a controlled migration. Do not directly update `STATUS`, `VERSION`, or the execution context in the `BATCH_*` tables to force a job to continue; such operations can corrupt the relationship between metadata and the checkpoint.

## Transaction propagation in services called from a batch

A tasklet or writer often calls a service annotated with `@Transactional`. The propagation determines whether the service joins the step's transaction or opens its own.

| Propagation | Behavior | Impact on consistency |
| --- | --- | --- |
| `REQUIRED` | Joins the current transaction or creates one if none exists | Typically suitable when a business update needs to commit together with the chunk/tasklet invocation and the same transaction manager |
| `REQUIRES_NEW` | Suspends the current transaction and opens a new one | The service can commit even if the step's transaction later rolls back |
| `NESTED` | Uses a savepoint in the current transaction if the resource supports it | Can partially roll back within the transaction; support depends on the manager/database |

For example, a service using `REQUIRES_NEW` to write an audit can commit the audit record even if the chunk fails. That can be correct if the audit needs to record failure events too, but it must be designed deliberately. If the audit is a checkpoint or a business change that must be consistent with the chunk, a separate transaction can cause discrepancies.

When the application has multiple datasources, specify the appropriate transaction manager with a qualifier on the service. The same `@Transactional` annotation but choosing the wrong manager can cause the operation not to participate in the transaction the step is managing.

## Concurrency and multiple nodes

In a multi-node deployment, the nodes typically share the `JobRepository` to identify instances and execution state. The business database also needs clear concurrency rules.

If two different job instances update the same set of business records, the database can encounter lock contention or lost updates if the writer does not use appropriate locks/conditions. If the same logical job is requested to run from multiple nodes, the repository helps coordinate the instance's execution but does not replace business constraints at the target database.

Commonly used measures:

- Choose identifying parameters that reflect the data scope the job owns.
- Use a unique business key and appropriate update conditions.
- Split partitions by non-overlapping ranges if parallel execution is needed.
- Use optimistic/pessimistic locking according to the data characteristics.
- Monitor deadlocks, lock waits, the connection pool, and the number of concurrent executions.
- Ensure the nodes use a compatible metadata schema and the same repository when they belong to one batch system.

## Backup, retention, and access permissions

Batch metadata and business data have different lifecycles, but when investigating or recovering a job you need to consider them together.

- Back up business data according to business requirements and the system's recovery policy.
- Back up metadata to keep history, checkpoints, and restartability.
- When you need to restore to a point in time, ensure the metadata and business data are compatible in commit state; restoring the two databases to two different points in time can create a state mismatch.
- Set up retention for completed executions but do not delete the metadata of jobs that are running or need to restart.
- Restrict read/write permissions on the `BATCH_*` tables and the business tables according to the application's roles.
- Do not store secrets or large business payloads in the `ExecutionContext`; only store the checkpoint and the necessary references.

If the metadata and business data are in two databases, the backup/restore plan needs to define how to synchronize the recovery point or how to reconcile after a restore.

## Testing transaction consistency

An ordinary successful test is not enough to prove that metadata and business data are consistent. You need to simulate failures at different points in time.

### Same resource

- Run a successful chunk and confirm the business rows and the checkpoint are committed.
- Deliberately throw an exception before the commit and confirm the business rows and the checkpoint of the chunk roll back.
- Let an earlier chunk commit successfully and a later chunk fail; confirm the earlier chunk's data is still present.
- Restart with the same identifying parameters and confirm the reader continues from the committed checkpoint.

### Different resources

- Simulate the business DB committing successfully but the metadata update failing.
- Simulate the metadata being updated but the business DB transaction rolling back.
- Restart/replay and confirm a unique key, upsert, or ledger prevents duplicates.
- Simulate the broker receiving a message but the database rolling back; confirm the consumer handles a repeated event ID safely.

### Recovery testing

- Confirm a `FAILED` job does not mean all of the job's business data was rolled back.
- Reconcile `readCount`, `writeCount`, the skip/filter counts, and the checkpoint against the actual data.
- Check the outbox state and the publisher's ability to resend events that have not been acknowledged.
- Check that the metadata/business data restore process can recover to one consistent state.

Fault injection should be done in a test environment with data that can be reset. Do not test by manually editing production metadata.

## Common design mistakes

### Assuming the same database server means the same transaction

Two datasources or two transaction managers can open independent transactions even if they point to the same server. Confirm the actual resource and transaction manager instead of only comparing the JDBC URL.

### Thinking that if the job is FAILED then all business data has rolled back

Chunks committed before the error still exist. The job status describes an execution; it is not a transaction spanning the whole job.

### Committing the checkpoint and the business update separately

This can lead to replay or omission. Share a transaction when possible; otherwise, use idempotency, a ledger, or a reconciliation process.

### Using REQUIRES_NEW without evaluating the consequences

An independent transaction can commit data even if the chunk/tasklet rolls back. Only use it when the business needs the independence and there is a plan for handling that state.

### Assuming messages or files roll back together with JDBC

Side effects outside the database do not automatically participate in the JDBC transaction. Use an outbox, temporary files, idempotency keys, or a recovery mechanism according to the target's protocol.

### Using the ExecutionContext as a store for business data

The execution context is for checkpoints and small state serving restart. Business data, large payloads, or processing history should reside in an appropriate schema/domain store.

## Design principles

When designing a production job, agree on the following points:

1. Clearly identify which tables are batch metadata and which are business data.
2. Choose where to store the `JobRepository` and the transaction manager for the step.
3. If an atomic commit is needed, configure the metadata and the business writer to use the same appropriate transaction resource.
4. If the resources are separated, clearly identify the failure windows when one side commits and the other rolls back.
5. Design an idempotent writer by business key or idempotency key.
6. Use a ledger or an outbox when you need to trace the application of items and the emission of messages.
7. Store a small, stable checkpoint in the `ExecutionContext`.
8. Check the propagation of services called from the tasklet/processor/writer.
9. Monitor the metadata together with business records when investigating a failed job.
10. Test rollback, restart, partial failure, and restore before deployment.

## Key takeaways

Batch metadata describes `JobInstance`, `JobExecution`, `StepExecution`, and checkpoints; business data is the domain data that the job processes. In a chunk or tasklet, the changes of the two groups can commit/roll back together when they participate in the same transaction resource and an appropriate transaction manager. If the metadata and business data use two databases or two independent transaction managers, there is no atomic commit by default: the business data may have been saved but the checkpoint not, or vice versa. When a shared transaction is not possible, design an idempotent writer, a business ledger, a transactional outbox, and a reconciliation process for safe restart. A job's `FAILED` status does not mean all business changes have rolled back; you need to read the metadata together with the business data to understand the actual state.
