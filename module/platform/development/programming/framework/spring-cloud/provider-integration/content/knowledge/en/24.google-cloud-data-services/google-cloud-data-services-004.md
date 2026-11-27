# Spanner Transactions and Choosing How to Read Data

## Learning Objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, Spring Boot integrates managed services from AWS, Azure, and Google Cloud to access data, storage, messaging, and manage identity/permissions. On Google Cloud, **Cloud Spanner** provides a distributed relational database with ACID transactions and strong consistency. When building applications, choosing the read mode and transaction type directly affects data freshness, latency, contention, cost, and resilience.

This lesson focuses on how data is read/written in Spanner and how Spring Boot uses those mechanisms:

1. Distinguish between single-use reads, read-only transactions, and read-write transactions.
2. Understand strong reads, exact staleness, max staleness, and read timestamps.
3. Choose between reading by primary key, KeySet, or SQL query/index.
4. Use a consistent snapshot when a use case requires multiple reads.
5. Use read-write transactions for business operations requiring atomic read-then-write.
6. Distinguish between DML, mutations, batch DML, and Partitioned DML.
7. Understand transaction retries, aborts, and how to avoid repeated side effects.
8. Integrate transactions with Spring Data Spanner and test against the emulator/sandbox.

> **Scope:** Examples use the GoogleSQL interface, the Cloud Spanner Java client, and Spring Data Spanner. Spanner has its own transaction semantics; do not mechanically apply JDBC/JPA assumptions such as arbitrary isolation levels, nested transactions, or HikariCP.

## 1. Why Does Choosing the Right Read Mode Matter?

An order-detail API, an analytics dashboard, and a payment flow have different data requirements.

- A detail screen usually needs the latest result and reads by primary key.
- A dashboard can tolerate data that is a few seconds behind to reduce latency.
- A report reading multiple tables needs to see those tables at the same snapshot.
- A payment flow needs to read the status and then update it in one transaction to prevent two requests from processing the same order concurrently.
- Batch cleanup may update millions of rows and needs a mechanism suited to Partitioned DML.

If every query uses a strong read or every operation is wrapped in a read-write transaction, the application can introduce unnecessary latency and contention. Conversely, using stale reads for sensitive business decisions can cause the application to act on outdated data.

### 1.1. Questions to Ask Before Writing a Query

| Question | Example choice |
| --- | --- |
| How fresh must the data be? | Strong, exact staleness, or max staleness |
| Reading one row or many rows? | Primary key, KeySet, or SQL |
| Must multiple reads share the same snapshot? | Single-use read or read-only transaction |
| Is an atomic read-then-write required? | Read-write transaction |
| Writing a known set of rows or updating by condition? | Mutation or DML |
| Can the task run across independent partitions? | Consider Partitioned DML |
| If the transaction aborts, is the callback safe to re-run? | Idempotency and no external side effects |

## 2. Operation and Transaction Types in Spanner

### 2.1. Overview Table

| Mechanism | Reads? | Writes? | Snapshot/atomicity | Typical use case |
| --- | --- | --- | --- | --- |
| Single-use read | Yes | No | Single read operation with read timestamp via TimestampBound | Reading one row or one query |
| Read-only transaction | Yes | No | Multiple reads on the same snapshot | Reports needing multiple consistent queries |
| Read-write transaction | Yes | Yes | Atomic read/write, may abort and retry | Updating orders, inventory |
| Mutation commit | No prior read needed | Yes | Single commit containing mutations committed together | Writing known rows |
| DML | Can have predicates | Yes | Executes inside a read-write transaction | Conditional UPDATE/DELETE |
| Partitioned DML | No surrounding app transaction | Yes | Multiple partitions; not atomic across the whole statement | Large-scale backfill/cleanup |

The Spanner client manages transactions and sessions over gRPC. The application does not need to manually open a JDBC connection for each operation.

### 2.2. Selection Flowchart

~~~mermaid
flowchart TD
    START["Use case needs data access"] --> WRITE{"Need to write data?"}
    WRITE -->|"No"| SNAP{"Must multiple reads share a snapshot?"}
    SNAP -->|"Yes"| RO["Read-only transaction"]
    SNAP -->|"No"| FRESH{"Need latest data?"}
    FRESH -->|"Yes"| STRONG["Single-use strong read"]
    FRESH -->|"No"| STALE["Stale read with TimestampBound"]
    WRITE -->|"Yes"| READFIRST{"Need to read state before deciding write?"}
    READFIRST -->|"Yes"| RW["Read-write transaction"]
    READFIRST -->|"No"| BULK{"Large-scale update/delete?"}
    BULK -->|"Yes, partitionable"| PDML["Partitioned DML"]
    BULK -->|"No"| MUT["Mutation commit or DML"]
~~~

This is an initial selection guide. You must also check engine limits, transaction semantics, idempotency, and business requirements.

## 3. Strong Reads and Stale Reads

### 3.1. Strong Reads

A strong read returns the latest committed data as of the read time under Spanner's consistency guarantees. This is the safe default when the business requires up-to-date data.

Examples:

- Reading order status before allowing cancellation.
- Checking inventory before confirming a write step.
- Reading control configuration whose updates must take effect immediately.
- Reading data just written in a subsequent request.

Strong reads may need to wait to guarantee consistency based on replica location and timestamp. Latency depends on region, topology, and load. Do not automatically replace strong reads with stale reads just because a query looks slow; first check indexes, rows scanned, and workload placement.

### 3.2. Stale Reads

Stale reads allow reading a snapshot at a point in the past. The application trades data freshness for potentially lower wait times in certain workloads.

Good fits:

- Hourly order-count dashboards.
- Analytics pages that do not require seeing just-committed changes.
- Aggregate reports tolerating a few seconds of lag.
- Cache refreshes or sync jobs with explicit freshness SLAs.

Poor fits without additional design:

- Payment decisions.
- Inventory deductions.
- Order state transitions requiring protection against concurrent updates.
- Permission or security state checks requiring immediate enforcement.

Stale reads are not random or inconsistent data. They are a consistent snapshot at a timestamp older than the current time.

### 3.3. TimestampBound

The Cloud Spanner Java client represents read consistency using `TimestampBound`. Key options:

| Type | Meaning | When to use |
| --- | --- | --- |
| `TimestampBound.strong()` | Reads latest data with strong consistency | Standard business APIs |
| `TimestampBound.ofExactStaleness(n, unit)` | Reads a snapshot with exact age by the given duration | Reproducing a snapshot with a fixed lag |
| `TimestampBound.ofMaxStaleness(n, unit)` | Allows a snapshot at most this old; Spanner may pick a fresher timestamp | Dashboards needing bounded lag while prioritizing latency |
| `TimestampBound.ofReadTimestamp(timestamp)` | Reads at a specific timestamp | Multiple services reading the same snapshot point |

These methods belong to the Cloud Spanner Java client API. Choose the time overload compatible with the library version in your project's BOM.

### 3.4. Difference Between Exact Staleness and Max Staleness

Suppose the application runs at 10:00 and sets a 15-second lag:

- Exact staleness requests a snapshot at 09:59:45.
- Max staleness allows a snapshot no older than 09:59:45; Spanner may use a newer snapshot if feasible.

Exact staleness fits when you need the exact same data point in time. Max staleness is useful when a newer snapshot is acceptable to optimize latency.

Do not set an excessively large staleness window just to reduce load. Choose the maximum lag based on business needs—for example, a dashboard may tolerate 10 seconds whereas a payment status screen does not.

### 3.5. Single-Use Read Example with Strong Consistency

~~~java
import com.google.cloud.spanner.DatabaseClient;
import com.google.cloud.spanner.Key;
import com.google.cloud.spanner.ReadContext;
import com.google.cloud.spanner.TimestampBound;
import com.google.cloud.spanner.Struct;

import java.util.Arrays;

public String readOrderStatus(DatabaseClient databaseClient, String orderId) {
    ReadContext context = databaseClient.singleUse(TimestampBound.strong());

    Struct row = context.readRow(
            "Orders",
            Key.of(orderId),
            Arrays.asList("OrderId", "Status"));

    return row == null ? null : row.getString("Status");
}
~~~

Reading by primary key fits when the exact key is known. Select only the columns needed to reduce data transfer and mapping. In production code, represent the missing case using `Optional<String>` or an explicit result type rather than returning `null` if your service conventions require it.

### 3.6. Stale Read Example for a Dashboard

~~~java
import com.google.cloud.spanner.DatabaseClient;
import com.google.cloud.spanner.ReadContext;
import com.google.cloud.spanner.Statement;
import com.google.cloud.spanner.TimestampBound;
import com.google.cloud.spanner.ResultSet;

import java.util.concurrent.TimeUnit;

public long countRecentOrders(DatabaseClient databaseClient) {
    ReadContext context = databaseClient.singleUse(
            TimestampBound.ofMaxStaleness(15, TimeUnit.SECONDS));

    Statement statement = Statement.newBuilder(
            "SELECT COUNT(*) AS total " +
            "FROM Orders WHERE Status = @status")
        .bind("status").to("CONFIRMED")
        .build();

    try (ResultSet resultSet = context.executeQuery(statement)) {
        return resultSet.next() ? resultSet.getLong("total") : 0L;
    }
}
~~~

Dashboards can tolerate metrics up to 15 seconds stale. If reporting requirements change, adjust the staleness bound to match the SLA and test actual latency.

## 4. Single-Use Reads and Read-Only Transactions

### 4.1. Single-Use Reads

A single-use read executes one read or one query with one `TimestampBound`. Once the operation finishes, no transaction is kept open for additional queries.

Use when:

- Reading a single row by primary key.
- Running a single independent query.
- Each endpoint only needs its own snapshot.
- Separate queries do not need to observe the exact same data state.

If you invoke two single-use reads consecutively, the two reads may observe two different snapshots. This is not a bug; it is the semantics of two independent operations.

### 4.2. Read-Only Transactions

A read-only transaction allows executing multiple reads against the same snapshot. This is the right choice when one response combines multiple queries that must be consistent at a single point in time.

For example, an order overview screen reads:

1. Order details.
2. List of order items.
3. Payment totals.
4. Latest audit record.

Using four separate single-use reads allows data to change between reads. Use one read-only transaction so all queries observe a single snapshot.

### 4.3. Read-Only Transaction Example

~~~java
import com.google.cloud.spanner.DatabaseClient;
import com.google.cloud.spanner.ReadOnlyTransaction;
import com.google.cloud.spanner.ResultSet;
import com.google.cloud.spanner.Statement;
import com.google.cloud.spanner.Struct;
import com.google.cloud.spanner.TimestampBound;

public OrderSummary loadSummary(DatabaseClient databaseClient, String orderId) {
    try (ReadOnlyTransaction transaction =
            databaseClient.readOnlyTransaction(TimestampBound.strong())) {

        Statement itemStatement = Statement.newBuilder(
                "SELECT ItemId, ProductId, Quantity " +
                "FROM OrderItems WHERE OrderId = @orderId")
            .bind("orderId").to(orderId)
            .build();

        Struct order = transaction.readRow(
                "Orders",
                com.google.cloud.spanner.Key.of(orderId),
                java.util.Arrays.asList("OrderId", "Status", "CustomerId"));

        if (order == null) {
            return null;
        }

        try (ResultSet items = transaction.executeQuery(itemStatement)) {
            // Map rows to the response DTO.
            while (items.next()) {
                String itemId = items.getString("ItemId");
                // Add item to the summary.
            }
        }

        return new OrderSummary(
                order.getString("OrderId"),
                order.getString("Status"),
                order.getString("CustomerId"));
    }
}
~~~

This snippet illustrates multiple reads inside one transaction. Mapping items into the DTO is abbreviated to focus on snapshot semantics. If the DTO needs an item list, add a collection and map each row inside the loop.

### 4.4. Choosing a Timestamp for a Snapshot

You can use `TimestampBound.ofReadTimestamp(timestamp)` so multiple operations or services read at the same agreed-upon timestamp. This is helpful for multi-part reports or distributed processing needing a shared data point.

The timestamp must be a valid timestamp that Spanner can serve. Do not fabricate future timestamps or pick arbitrary timestamps without an appropriate timestamp source and retention policy.

### 4.5. When Is a Read-Only Transaction Unnecessary?

Do not wrap a single simple query in a multi-operation transaction if a single-use read suffices. Read-only transactions require explicit lifecycle management and must be closed upon completion.

Avoid keeping a transaction open while waiting on users, calling HTTP services, or streaming unbounded data. Read the required data, close the transaction, and then handle remaining processing.

## 5. Read-Write Transactions

### 5.1. When Is One Needed?

A read-write transaction fits when write outcomes depend on data just read and changes must commit atomically.

Order confirmation example:

1. Read the current status.
2. Verify the status is `PENDING`.
3. Read/check inventory conditions.
4. Update the order status.
5. Write an audit record or update related data.
6. Commit all changes together.

If two requests attempt to confirm the same order concurrently, Spanner's transaction semantics detect conflicts and ensure results adhere to database isolation/serializability.

### 5.2. Read-Write Transaction with the Java Client

~~~java
import com.google.cloud.spanner.DatabaseClient;
import com.google.cloud.spanner.Key;
import com.google.cloud.spanner.Mutation;
import com.google.cloud.spanner.Struct;

import java.util.Arrays;

public void confirmOrder(DatabaseClient databaseClient, String orderId) {
    databaseClient.readWriteTransaction().run(transaction -> {
        Struct order = transaction.readRow(
                "Orders",
                Key.of(orderId),
                Arrays.asList("OrderId", "Status"));

        if (order == null) {
            throw new IllegalArgumentException("Order not found");
        }

        if (!"PENDING".equals(order.getString("Status"))) {
            throw new IllegalStateException("Order is not pending");
        }

        Mutation update = Mutation.newUpdateBuilder("Orders")
                .set("OrderId").to(orderId)
                .set("Status").to("CONFIRMED")
                .build();

        transaction.buffer(update);
        return null;
    });
}
~~~

The transaction reads state and buffers mutations within the same unit of work. When the callback completes normally, the client commits the transaction. If the transaction aborts due to conflict, the client may re-run the callback according to the library's retry policy.

This is a minimal example. Real business logic should check inventory, idempotency keys, and audit records in the same transaction if that data requires atomicity.

### 5.3. Transactions Can Re-Run

Spanner can abort a read-write transaction when detecting conflicts or transient conditions. The client library automatically retries the transaction per its mechanism.

Because the callback can execute multiple times:

- Do not send emails inside the callback.
- Do not call payment gateways inside the callback.
- Do not publish messages directly from the callback.
- Do not increment external counters non-idempotently.
- Do not mutate external state assuming the callback only runs once.

Put only database operations and pure computations inside the callback. Write events/outbox rows in the same transaction, and have a post-commit worker send messages or call external systems.

### 5.4. Transaction Example with DML

You can execute DML statements inside a transaction when updating conditionally:

~~~java
import com.google.cloud.spanner.Statement;

long updatedRows = databaseClient.readWriteTransaction().run(transaction -> {
    Statement statement = Statement.newBuilder(
            "UPDATE Orders SET Status = @newStatus " +
            "WHERE OrderId = @orderId AND Status = @oldStatus")
        .bind("orderId").to(orderId)
        .bind("oldStatus").to("PENDING")
        .bind("newStatus").to("CONFIRMED")
        .build();

    return transaction.executeUpdate(statement);
});
~~~

The `Status = @oldStatus` predicate ensures the operation updates only if the status is still PENDING in the transaction. The row count helps detect when no row matched. When business logic must distinguish not-found from wrong-status, read the row inside the transaction and decide the outcome explicitly.

### 5.5. Do Not Use Read-Write Transactions for Everything

Read-write transactions carry coordination overhead, locking, and abort/retry potential. If you are only writing a known set of rows without prior reads, a mutation commit may be a better fit.

If you are only reading data, use a read context or read-only transaction. Choose transactions based on business invariants instead of wrapping every repository method in one big transaction.

## 6. Mutations, DML, and Partitioned DML

### 6.1. Mutation Commit

A mutation describes a row change: insert, update, replace, or delete. You can send a group of mutations in a single commit:

~~~java
import com.google.cloud.spanner.DatabaseClient;
import com.google.cloud.spanner.Mutation;

import java.util.Arrays;
import java.util.List;

public void createOrderRows(DatabaseClient databaseClient, String orderId) {
    Mutation order = Mutation.newInsertBuilder("Orders")
            .set("OrderId").to(orderId)
            .set("Status").to("PENDING")
            .build();

    Mutation audit = Mutation.newInsertBuilder("OrderAudit")
            .set("OrderId").to(orderId)
            .set("Action").to("CREATED")
            .build();

    List<Mutation> mutations = Arrays.asList(order, audit);
    databaseClient.write(mutations);
}
~~~

Mutations in a single commit are applied atomically. This mechanism fits when the application already knows the rows to write and does not need to read current data before deciding.

### 6.2. How Do Mutations and DML Differ?

| Criterion | Mutation | DML |
| --- | --- | --- |
| Description | Changes to specific rows | SQL INSERT/UPDATE/DELETE statements |
| Row selection | Based on primary key in the mutation | Based on SQL predicates |
| Read/write in transaction | Can be buffered in a read-write transaction | Can be executed inside a transaction |
| Best for | Writing known rows | Updating by predicate or expression |
| SQL features | Not a SQL query | Uses GoogleSQL DML |

Mutations are typically cleaner and more concise when keys/values are already known. DML fits when update conditions are expressed naturally in SQL.

### 6.3. At-Least-Once Mutations

The Java client offers `writeAtLeastOnce` for scenarios requiring lower transaction overhead. At-least-once semantics mean the application must tolerate mutations being re-applied on retry.

Use only for idempotent operations. For example, setting a column to a fixed value can be idempotent; adding to a balance or inserting new records without deduplication can produce duplicate effects if retried.

Do not use `writeAtLeastOnce` for payments, debits, or cumulative increments without deduplication/unique key design.

### 6.4. Batch DML

Batch DML allows running multiple DML statements within the same read-write transaction. Statements in the transaction commit or rollback together.

Use when a business operation requires multiple related UPDATE/DELETE statements that must commit atomically. If a batch contains many independent large-scale operations, consider splitting it or using Partitioned DML if semantics allow.

### 6.5. Partitioned DML

Partitioned DML splits an eligible DML statement across multiple partitions for large-scale processing. Example cleanup of expired records:

~~~sql
DELETE FROM OrderAudit
WHERE CreatedAt < @cutoff;
~~~

This SQL is illustrative; actual statements must use syntax/parameters supported by the API. Partitioned DML is not a single atomic transaction spanning the entire table. Partitions can commit independently, so a mid-flight failure can leave partial work completed.

Use only when:

- The update/delete task can be split into independent partitions.
- Statement-wide atomicity is not required.
- The operation is safe to re-run.
- It does not depend on external side effects during execution.
- DML limits and execution behavior for the client version have been verified.

Do not use Partitioned DML for payment or money-transfer workflows requiring multiple changes to commit atomically.

## 7. Spring Data Spanner and Transaction Boundaries

### 7.1. Using @Transactional at the Service Layer

With Spring Data Spanner, you can place a transaction at the service layer spanning multiple repository operations:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.List;

@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final OrderItemRepository itemRepository;

    public OrderApplicationService(
            OrderRepository orderRepository,
            OrderItemRepository itemRepository) {
        this.orderRepository = orderRepository;
        this.itemRepository = itemRepository;
    }

    @Transactional(transactionManager = "spannerTransactionManager")
    public void createOrder(Order order, List<OrderItem> items) {
        orderRepository.save(order);
        itemRepository.saveAll(items);
    }
}
~~~

This example assumes the starter has configured the Spanner transaction manager and corresponding repositories. If the application has only one transaction manager, specifying the name may be omitted; if JPA/Cloud SQL is also present, specify the exact manager to prevent transactions from running on a different datasource.

### 7.2. Transaction Manager vs. Native Client

The Spring transaction manager fits service-layer transaction boundaries. When you need `TimestampBound`, read timestamps, or specialized transaction APIs, you can use the Cloud Spanner Java client `DatabaseClient` directly.

Do not manually open a read-write transaction inside a method already annotated with `@Transactional` on the same database. Pick one transaction management mechanism per unit of work to avoid nested transactions or unpredictable boundaries.

### 7.3. readOnly=true Is Not a Stale Read

`@Transactional(readOnly = true)` is Spring-layer metadata/hint. Do not assume this annotation automatically selects exact staleness, max staleness, or a timestamp snapshot.

If business logic requires a specific staleness bound, configure `TimestampBound` via the Spanner client API or a mechanism explicitly supported by your Spring Cloud GCP version. Document data freshness SLAs per service/use case.

### 7.4. Isolation Levels and Spanner Semantics

Spanner provides strong transaction semantics and external consistency for committed transactions. Do not treat attributes like `isolation = READ_COMMITTED` or `REPEATABLE_READ` as ways to arbitrarily alter Spanner's internal semantics like a standard JDBC model.

Spanner read-write transactions can abort due to contention. Read-only transactions provide snapshots. Stale reads are an explicit consistency/timestamp choice. Design around these semantics instead of forcing Spanner to behave like a traditional JDBC database.

### 7.5. No Support for Nested Transactions Like JDBC Savepoints

Do not rely on nested transactions or savepoints to subdivide Spanner transactions. If a workflow has multiple independent steps, split it into multiple transactions with intermediate states, idempotency keys, and appropriate compensation mechanisms.

## 8. Choosing Read Modes by Use Case

### 8.1. Selection Matrix

| Use case | Recommended read mode | Reason |
| --- | --- | --- |
| Order details by ID | Strong single-use key read | Single row, requires latest data |
| Order list by customer | Strong SQL query or appropriate index | Filters/sorting across multiple columns |
| Analytics dashboard | Max staleness | Tolerates bounded lag within SLA |
| Multi-table report | Read-only transaction | Queries share one snapshot |
| Export at a fixed point in time | Read-only transaction with fixed read timestamp | Consistent results across multiple queries |
| Check state then update | Read-write transaction | Atomic read and write |
| Paginated list API | Indexed query and keyset/cursor | Avoids large offsets and unstable ordering |
| Cache refresh | Stale read if business permits | Optimizes latency and load |

### 8.2. Reading by Primary Key

When the full primary key is known, use the read API or repository `findById`. This is typically the most direct way to fetch one row.

For composite keys, pass all components in exact order. Do not query with a partial composite key as if it were a single key; to search by prefix, use a KeySet/range or an appropriate SQL query.

### 8.3. Reading by KeySet or Key Range

KeySet is useful when reading a known set of keys or a range in primary key order. This read style can reduce SQL parsing overhead for key-based use cases.

Do not use KeySet to express conditions on non-primary-key columns. For filtering by CustomerId, Status, or CreatedAt, you need a secondary index or SQL query.

### 8.4. SQL Queries and Secondary Indexes

Use SQL when you need filtering, joins, aggregations, sorting, or projections. Ensure the query pattern is supported by the primary key or an appropriate secondary index.

Example:

~~~sql
SELECT OrderId, Status, CreatedAt
FROM Orders
WHERE CustomerId = @customerId
ORDER BY CreatedAt DESC
LIMIT 50;
~~~

If a query filters by CustomerId and sorts by CreatedAt, a secondary index with matching key order can reduce scanning. Inspect query plans and rows/bytes read before adding indexes.

### 8.5. Pagination

Avoid large offsets on fast-growing tables when keyset pagination can be used. Store a cursor from the last row of the previous page, then query subsequent rows in a stable key/index order.

Logical example:

~~~sql
SELECT OrderId, CreatedAt, Status
FROM Orders
WHERE CustomerId = @customerId
  AND CreatedAt < @lastCreatedAt
ORDER BY CreatedAt DESC
LIMIT 50;
~~~

If multiple rows share the same CreatedAt, add a deterministic tie-breaker such as OrderId in both the index and cursor condition. If data changes between page requests, keyset pagination can still observe new changes; if a consistent snapshot is needed for an entire export, keep a read-only transaction or use a suitable read timestamp while considering snapshot retention limits.

### 8.6. Streaming Results

For queries returning many rows, read via stream/cursor and close `ResultSet` properly. Avoid loading entire tables into a `List` unnecessarily; bound page sizes, projections, and processing time.

Do not hold a read-only transaction open while slowly streaming data to clients. Read in bounded batches, close resources early, and continue via cursor if the use case allows.

## 9. Consistent Snapshots and Multi-Step Reports

### 9.1. The Multi-Query Different-Snapshot Problem

Suppose a report reads total orders, total items, and total payments. If each query is a single-use read, an order can change status between queries. The report could sum slices of data from different points in time.

A read-only transaction solves this by using one consistent snapshot for all reads inside the transaction.

### 9.2. Shared Read Timestamps

If multiple independent components need the same snapshot, the system can pass a valid read timestamp and use `TimestampBound.ofReadTimestamp(timestamp)` in each reader.

Controls required:

- A timestamp source generated by Spanner or an agreed snapshot procedure.
- All queries use the exact same timestamp.
- The timestamp remains within the window Spanner can serve.
- Services do not independently pick different timestamps while claiming the same snapshot.

### 9.3. Long Exports and Lifecycle Limits

Do not keep a transaction open for too long just to build a large export file. Long-lived transactions increase session/resource hold times and can impact operations.

For long exports, consider:
- Choosing a fixed read timestamp.
- Splitting data by primary key ranges.
- Persisting cursors/checkpoints to support resuming.
- Limiting concurrent workers.
- Measuring read throughput and cost.
- Defining a policy if the snapshot timestamp is no longer available.

## 10. Transaction Contention, Aborts, and Retries

### 10.1. Why Do Transactions Abort?

Read-write transactions can conflict when multiple concurrent requests read/write the same data or overlapping key ranges. Spanner may abort a transaction to preserve consistency.

Common symptoms:
- Transaction aborted errors or `ABORTED` status.
- Increasing retry counts.
- Latency rising under concurrent load.
- Multiple requests updating the same row/counter.
- Long transactions reading many rows before writing.

### 10.2. Reducing Contention

- Keep transactions short.
- Read only the rows needed.
- Design primary keys to distribute writes evenly.
- Avoid a single counter row becoming a hot write spot.
- Group related operations into one short transaction.
- Split large batches into independent units when business logic permits.
- Use optimistic application logic with appropriate versions/conditions.

### 10.3. Safe Retries

The client library includes retries for read-write transactions. The application should:
- Keep callbacks deterministic and safe to re-run.
- Avoid non-database I/O inside callbacks.
- Avoid generating IDs or external side effects that change outcomes across retries when IDs must be stable.
- Use idempotency keys for business requests.
- Log retry counts, latency, and final errors.
- Set deadlines/time budgets for requests.

### 10.4. Outbox Pattern

If a transaction must update an order and emit an event, write an outbox row inside the same transaction:

~~~java
databaseClient.readWriteTransaction().run(transaction -> {
    transaction.buffer(
        Mutation.newUpdateBuilder("Orders")
            .set("OrderId").to(orderId)
            .set("Status").to("CONFIRMED")
            .build());

    transaction.buffer(
        Mutation.newInsertBuilder("Outbox")
            .set("EventId").to(eventId)
            .set("AggregateId").to(orderId)
            .set("EventType").to("ORDER_CONFIRMED")
            .build());

    return null;
});
~~~

A separate worker reads the outbox, publishes the message, and marks it processed using idempotency/deduplication. Design the worker to tolerate duplicate publishes or crashes occurring after publish but before status update.

## 11. Testing Transactions and Consistency

### 11.1. Testing on the Spanner Emulator

The emulator is useful for checking:
- Basic SQL syntax and parameter binding.
- Insert/update/delete operations.
- Repository/template mappings.
- Transaction commits/rollbacks.
- Application-layer retry logic and error handling.
- Read-only transactions in scenarios supported by the emulator.

The emulator does not fully simulate multi-region latency, production-scale contention, IAM, quotas, index performance, or all consistency/performance behaviors. Do not use emulator results to draw production capacity conclusions.

### 11.2. Recommended Test Cases

| Test | Expectation |
| --- | --- |
| Strong read after commit | Sees committed data |
| Stale read with max staleness | Results may lag within configured bound |
| Two queries in read-only transaction | Same snapshot |
| Read-write transaction commit | All related changes appear together |
| Exception before commit | No uncommitted changes remain |
| Transaction abort/retry | Callback re-runs without duplicating side effects |
| Mutation commit | Group of mutations commits together |
| Partitioned DML | Does not assume entire statement is atomic |
| Keyset pagination | No duplicate/skipped rows when order and cursor are designed properly |
| IAM/network integration | Real runtime principal and network path work |

### 11.3. Concurrency Testing

Send two concurrent requests attempting to update the same order's status. Verify only one request can transition the status from PENDING to CONFIRMED per the invariant. The other request receives an appropriate conflict/business state result without overwriting confirmed data.

Do not test only single requests in isolation; transaction correctness issues surface under concurrency.

### 11.4. Testing Stale-Read SLAs

For dashboards, measure:
- Actual data lag.
- Query latency.
- Ratio of queries using stale timestamps.
- Metric variance compared to strong reads.
- Behavior as traffic increases.

Set staleness bounds according to product requirements. If users need real-time figures, stale reads are no longer an appropriate optimization.

## 12. Observability and Operations

### 12.1. Metrics

Monitor:
- Query latency p50/p95/p99.
- Read bytes/rows and query plans.
- Read/write throughput.
- Transaction abort/retry count.
- Commit latency.
- Session pool usage/exhaustion.
- Partitioned DML progress and affected rows.
- Error rates by status code and operation type.

Combine application metrics with Cloud Monitoring/Spanner metrics to pinpoint bottlenecks in queries, transaction contention, session pools, or infrastructure.

### 12.2. Useful Logs

Log:
- Operation name/use case.
- Request/correlation ID.
- Query category or statement identifier.
- Read mode (strong/stale) and staleness bound.
- Transaction duration and retry count.
- Error code/status.
- Rows returned or affected when safe.

Do not log sensitive parameter values, access tokens, service account keys, or full customer payloads.

### 12.3. Alerts

- Sudden spikes in transaction aborts.
- P95 commit latency exceeding SLA.
- Query scan/read bytes rising after a release.
- Session pool exhaustion.
- Partitioned DML failures or stalled progress.
- Stale-read age exceeding business thresholds.
- Strong read latency rising by region/traffic.

## 13. Common Errors and How to Handle Them

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Reads see stale data | Using stale read or old timestamp | Check TimestampBound/read timestamp |
| Report tables appear out of sync | Multiple independent single-use reads | Use a read-only transaction or shared timestamp |
| Transaction aborted | Contention, long transaction, or hot key | Shorten transactions, redesign keys, and retry safely |
| Duplicate emails sent after retry | Side effects inside transaction callback | Use outbox and idempotent workers |
| Update modifies zero rows | DML predicate does not match current state | Check row count and business state |
| Partitioned DML partially completed | Some partitions committed before error | Design idempotent operations and resume capability |
| Slow read queries | Missing index or scanning too many columns/rows | Inspect query plan, projections, and indexes |
| Export exhausts session pool | Holding transactions/sessions too long or too high concurrency | Shard by range, limit workers, close resources early |
| Pagination duplicates/misses rows | Unstable sort or cursor missing tie-breaker | Use deterministic ordering and keyset cursors |
| Wrong transaction manager | Application has multiple transaction managers | Explicitly specify the Spanner transaction manager |

## 14. Practical Exercises

### Exercise A — Strong Reads and Stale Reads

Create an order and read its status using a strong read. Update the status and read using max staleness of 10 seconds. Compare freshness and latency, and explain which use cases accept stale reads.

### Exercise B — Single-Use vs. Read-Only Snapshot

Write two independent queries reading Orders and OrderItems using single-use reads. Introduce concurrent updates between the two queries to observe snapshot divergence. Then use a read-only transaction and compare results.

### Exercise C — Read-Write Transactions

Write a service transitioning an order from PENDING to CONFIRMED. Run two concurrent requests; verify only one succeeds per the invariant. Write an audit row inside the same transaction.

### Exercise D — Mutations and DML

Create two known rows using a mutation commit. Then update multiple rows by predicate using DML. Compare the code, row counts, and ability to read data prior to writing.

### Exercise E — Partitioned DML

Create a test audit table with expired data. Run Partitioned DML to clean it up. Intentionally stop the job in the sandbox and design a safe way to re-run without corrupting data.

### Exercise F — Outbox and Retries

Create a transaction updating Orders and inserting into Outbox. Simulate callback retries; verify no messages are published from inside the transaction and the worker processes events idempotently.

### Exercise G — Snapshot Export

Pick a read timestamp and run multiple queries across readers sharing that timestamp. Verify the report sees the same snapshot and design checkpoints so the export can resume.

### Self-Check Questions

1. How does a strong read differ from a stale read?
2. How do exact staleness and max staleness differ?
3. When should you use a single-use read?
4. Why can multiple independent queries observe different snapshots?
5. What problem does a read-only transaction solve?
6. When is a shared read timestamp needed across multiple services?
7. Why do read-then-write operations require a read-write transaction?
8. Under what circumstances can Spanner abort a transaction?
9. Why must a transaction callback be safe to re-run?
10. How do mutations differ from DML in identifying which rows to modify?
11. When is Partitioned DML appropriate and why is it not atomic across the entire statement?
12. When should you read by primary key, KeySet, or SQL query?
13. Why does keyset pagination need a deterministic tie-breaker?
14. Why shouldn't you hold a read-only transaction open while slowly streaming data to a client?
15. Does `@Transactional(readOnly = true)` automatically choose a stale timestamp?
16. How do you avoid sending duplicate emails or publishing duplicate messages when a transaction retries?
17. What can the emulator verify and what testing can it not replace?
18. Which metrics help detect transaction contention and increased query scans?

**Expected outcome:** learners can select the proper read consistency and transaction type for each use case, use single-use/read-only/read-write transactions, mutations, and DML with correct semantics, design stale reads with SLAs, handle aborts/retries safely, and test data consistency in Spring Boot applications integrated with Cloud Spanner.

## References

- [Spanner transactions](https://docs.cloud.google.com/spanner/docs/transactions)
- [Read data with Spanner](https://docs.cloud.google.com/spanner/docs/reads)
- [Read data using SQL](https://docs.cloud.google.com/spanner/docs/query-data-sql)
- [Spanner read consistency](https://docs.cloud.google.com/spanner/docs/reads#read_consistency)
- [Mutations and commits](https://docs.cloud.google.com/spanner/docs/modify-mutation-api)
- [Partitioned DML](https://docs.cloud.google.com/spanner/docs/dml-partitioned)
- [Spring Framework on Google Cloud reference](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/)
