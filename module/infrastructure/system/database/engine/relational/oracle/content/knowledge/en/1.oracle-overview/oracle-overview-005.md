# Request Flow from Application to SQL Execution and Disk Storage

When a user clicks **"Place Order"** in an application, data is not written straight from the UI to a file on disk. The request passes through multiple layers: business code, the connection driver, Oracle Database processes, the SQL engine, memory caches, and durable storage mechanisms. Understanding this path helps separate application bugs from SQL errors, explain why queries are fast or slow, and see what actually happens when `COMMIT` is called.

In this lesson, **Oracle Database** is the relational database management system; **SQL** is the language the application uses to instruct Oracle to read or modify data. The examples use a Java application connecting to Oracle over JDBC. The core concepts apply equally when an application uses Spring Data JPA, Hibernate, or another programming language.

## 1. Big Picture: Which Layers Does a Request Traverse?

~~~mermaid
flowchart TD
    A["User / HTTP request"] --> B["Controller and application business logic"]
    B --> C["Repository / JDBC / connection pool"]
    C --> D["Oracle Net connection and DB session"]
    D --> E["Server process: parse, bind, optimize, execute SQL"]
    E <--> F["SGA: shared pool, database buffer cache"]
    E <--> G["PGA: private memory for execution"]
    F <--> H["Datafiles: data blocks of tables and indexes"]
    E --> I["Return result rows / affected row count"]
    I --> B
    B --> J["HTTP response to user"]
    E -. "On data changes" .-> K["Redo log buffer"]
    K --> L["LGWR writes online redo log"]
    F -. "DBWn writes dirty blocks when needed" .-> H
~~~

This diagram shows only the **typical** path of an application connecting directly to an Oracle instance. Real-world deployments may involve API gateways, multiple services, application-level caches, multiple instances, or specialized I/O mechanisms.

| Layer | Representative Components | Responsibility |
|---|---|---|
| User and interface | Web/mobile, HTTP, REST API | Express intent, e.g., "order 2 items"; receive result |
| Application | Controller, service, validation | Authenticate request, validate business rules, determine data operations |
| DB access | JDBC, driver, connection pool, ORM | Build/send SQL statements, bind parameters, manage connections and transactions |
| Oracle instance | Server process, SGA, PGA, background processes | Parse and execute SQL; manage memory, locks, transactions, and I/O |
| Storage | Tablespace, segment, extent, block, datafile | Organize rows and indexes into persistently stored data blocks |
| Recovery | Undo, redo, online redo log | Support read consistency, rollback, and crash recovery |

An immediate distinction to keep in mind: the **Oracle instance** comprises running memory and processes; the **Oracle database** in the storage sense comprises required files such as datafiles, control files, and online redo logs. The instance opens and operates on the database. This is the basic single-instance model; Oracle RAC can have multiple instances accessing the same database.

## 2. Running Scenario: Placing an Order and Deducting Inventory

Suppose the system has two tables:

~~~sql
CREATE TABLE products (
    product_id   NUMBER(10) PRIMARY KEY,
    product_name VARCHAR2(100) NOT NULL,
    stock_qty    NUMBER(10) NOT NULL CHECK (stock_qty >= 0)
);

CREATE TABLE orders (
    order_id   NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id NUMBER(10) NOT NULL REFERENCES products(product_id),
    quantity   NUMBER(10) NOT NULL CHECK (quantity > 0),
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

INSERT INTO products (product_id, product_name, stock_qty)
VALUES (101, 'Mechanical keyboard', 8);

COMMIT;
~~~

This example uses Oracle 12c+ identity column syntax. Tables store business data; `PRIMARY KEY`, `REFERENCES`, and `CHECK` constraints are enforced by Oracle to protect data validity. Those constraints do not replace all business validation in the application.

The user sends a hypothetical request:

~~~http
POST /orders
Content-Type: application/json

{"productId":101,"quantity":2}
~~~

The application must perform **two changes in the same transaction**:

~~~sql
UPDATE products
SET stock_qty = stock_qty - :qty
WHERE product_id = :product_id
  AND stock_qty >= :qty;

INSERT INTO orders (product_id, quantity)
VALUES (:product_id, :qty);

COMMIT;
~~~

In the illustrative SQL, `:qty` and `:product_id` are **bind variables**. The `UPDATE` statement includes an inventory check, and the application must inspect the updated row count. If it is 0, stop the order and `ROLLBACK`; never assume both statements succeeded. Checking inventory directly inside the `UPDATE` also makes the operation safer when multiple transactions contend on the same product.

A concise JDBC implementation with clear transaction boundaries:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderService {
    private final DataSource dataSource;

    public OrderService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void placeOrder(long productId, int quantity) throws SQLException {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be greater than 0");
        }

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                try (PreparedStatement reduceStock = connection.prepareStatement(
                         "UPDATE products SET stock_qty = stock_qty - ? " +
                         "WHERE product_id = ? AND stock_qty >= ?");
                     PreparedStatement createOrder = connection.prepareStatement(
                         "INSERT INTO orders (product_id, quantity) VALUES (?, ?)")) {

                    reduceStock.setInt(1, quantity);
                    reduceStock.setLong(2, productId);
                    reduceStock.setInt(3, quantity);

                    if (reduceStock.executeUpdate() != 1) {
                        throw new SQLException("Product not found or insufficient stock");
                    }

                    createOrder.setLong(1, productId);
                    createOrder.setInt(2, quantity);
                    createOrder.executeUpdate();
                }
                connection.commit();
            } catch (SQLException | RuntimeException error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }
}
~~~

JDBC uses `?` as parameter placeholders, then `setInt`/`setLong` pass values and data types. Using `PreparedStatement` keeps the application from concatenating user input into SQL strings, reducing SQL injection risk and enabling statement reuse. In a Spring application, `@Transactional` and the repository layer manage much of this plumbing; on the Oracle side, SQL, binds, sessions, and transactions are still at work.

## 3. From HTTP Request to Oracle Session

**Step 1 — Application interprets intent.** The controller receives JSON, validates fields, and delegates to the service. The service decides that a valid order requires deducting inventory and inserting an order record. Business operations do not magically turn into SQL: they must be expressed through explicit repository or ORM statements.

**Step 2 — Acquiring a connection.** `DataSource` typically uses a **connection pool** to hand out an already open physical connection. Borrowing a connection from the pool avoids opening a new TCP connection and authenticating with Oracle on every HTTP request. Nor does a single request necessarily map to only one SQL statement.

**Step 3 — Communicating with Oracle.** The Oracle JDBC driver sends statements, parameters, and transaction directives over the Oracle Net connection protocol. The **listener** helps establish the initial session and hands off the connection to the appropriate server mechanism; the listener is not the component that parses or executes every SQL statement. In dedicated server mode, one server process serves the application session; systems may also be configured with shared servers or other connection architectures.

**Step 4 — Transaction boundaries.** `setAutoCommit(false)` ensures both DML statements belong to one transaction. If the application left JDBC in auto-commit mode per statement, the `UPDATE` could commit before the `INSERT` failed, leaving inventory and orders out of sync.

## 4. What Does Oracle Do When It Receives a SQL Statement?

The logical processing pipeline is often summarized as **parse → optimize → execute → fetch**. These are conceptual phases; Oracle can reuse prior compilation work, adapt plans dynamically, and interleave steps.

### 4.1 Parse: Validating and Identifying the Statement

Oracle checks SQL syntax, resolves objects such as `products`, verifies object references and required privileges, and finds or creates an internal cursor for execution. SQL text, shared execution metadata, and related structures can be cached in the **shared pool** inside the **SGA**.

- **Hard parse**: Oracle must perform full compilation/optimization to build a suitable execution cursor; this tends to be CPU-intensive and can cause resource contention.
- **Soft parse / cursor reuse**: an existing cursor is found and eligible for reuse, reducing recomputation overhead.

Two statements `WHERE product_id = 101` and `WHERE product_id = 102` built by string-concatenating literals produce distinct SQL texts. Using a single statement `WHERE product_id = :id` with bind variables improves cursor sharing, though it **does not guarantee** every execution uses the same execution plan.

### 4.2 Optimize: Choosing How to Retrieve and Process Data

The **Cost-Based Optimizer (CBO)** weighs statistics, filter predicates, indexes, joins, data volume, and other factors to select an **execution plan**. For instance:

~~~sql
SELECT product_name, stock_qty
FROM products
WHERE product_id = :id;
~~~

Because `product_id` is the primary key, Oracle can use the supporting index to locate the row, then read the remaining columns from the table's data block. The plan may include operations such as `INDEX UNIQUE SCAN` and `TABLE ACCESS BY INDEX ROWID`. This is a **likely choice**, not a mandatory path: the optimizer can also pick a full table scan if its estimated cost is lower.

An execution plan describes **how** Oracle intends to execute or did execute SQL; it is not the result dataset. SQL states what data to read or change, while the optimizer determines many of the physical access details.

### 4.3 Execute and Fetch: Executing and Returning Results

The server process executes the plan operators: reading required blocks, evaluating filter predicates, updating rows, traversing indexes, performing joins/sorts, and so on. The PGA can hold execution state and private work areas. If a sort or hash exceeds its allocated memory work area, Oracle can spill to temporary space in the **TEMP tablespace**.

For `SELECT`, the application continues to **fetch** rows in batches and the driver returns data to Java. For `UPDATE` or `INSERT`, JDBC receives the affected row count or an error from Oracle. The wall-clock duration observed on an HTTP request includes application processing and network transit, so it is not identical to the time Oracle spends running SQL.

## 5. From Logical Table Rows to Blocks in a Datafile

Developers see **tables** and **rows**. Oracle stores data across multiple organizational tiers:

~~~text
Tablespace (logical storage space)
  └── Segment (e.g., one table or one index)
       └── Extent (contiguous group of data blocks)
            └── Oracle data block (logical storage unit)
                 └── Row data / index structure

Tablespace
  └── One or more corresponding datafiles / tempfiles
       └── Store blocks on storage devices
~~~

| Concept | Meaning Along the SQL Execution Path |
|---|---|
| **Row** | Logical record in a table, e.g., product 101 |
| **Data block** | Unit Oracle manages for reading/writing data; usually holds multiple rows or row pieces |
| **Extent** | Collection of contiguous data blocks allocated to a segment |
| **Segment** | Storage allocation for a table, index, undo, etc. |
| **Tablespace** | Logical organization layer between segments and datafiles |
| **Datafile** | Physical file (or ASM-managed file) holding the blocks of a tablespace |
| **ROWID** | Logical-physical address Oracle uses to locate a row in many standard table types |

A B-tree index stores key structures and pointers to rows; the index itself is stored in its own blocks and segment. Indexes reduce the volume of data scanned for many queries, at the cost of extra storage and maintenance overhead during writes.

### Buffer Cache: Why "Reading a Table" Might Never Touch Disk

Oracle maintains a **database buffer cache** inside the SGA. When a data block is needed:

1. Oracle looks up the block in the buffer cache.
2. If a suitable copy is already present, the process can read it from memory (**logical read**).
3. If absent and the operation requires datafile access, Oracle performs a **physical read** and can load the block into cache.
4. A typical `UPDATE` modifies the block in memory and marks it changed (**dirty block**); flushing that block back to the datafile does not happen synchronously at the moment the application calls `UPDATE`.

This path is the common model, not an absolute rule for all I/O: Oracle also has direct path I/O and other optimizations. Similarly, a **cache miss** or **physical read** does not necessarily mean a read from a spinning disk every time; underlying storage layers may have caches of their own.

## 6. On INSERT/UPDATE: Undo, Redo, Locks, and COMMIT

This is the most frequently misunderstood part of the entire pipeline.

### 6.1 Locking and Undo in an Active Transaction

When updating `products`, Oracle must protect the row being modified. Another transaction attempting to modify the same row may have to wait for the row lock to be released; Oracle does not necessarily lock the entire table.

Oracle records **undo information** sufficient to roll back changes if the transaction issues `ROLLBACK` and to support **consistent reads** for queries needing data as of their read time. Undo is typically stored in undo segments within the undo tablespace. It is not simply a list of reversed SQL statements.

In our scenario, two buyers order product 101 concurrently: `UPDATE ... stock_qty >= :qty` enforces the inventory condition inside the database, combining Oracle's locking and consistency mechanisms. The application must still handle 0 updated rows, timeouts, or contention errors as needed.

### 6.2 Redo and Datafiles Are Two Separate Write Paths

Oracle generates **redo records** capturing change information needed for recovery (including changes related to undo). Redo records are placed in the **redo log buffer** inside the SGA. The **LGWR (Log Writer)** background process writes redo to the **online redo log** on storage.

Meanwhile, modified data blocks in the buffer cache become dirty blocks. The **DBWn (Database Writer)** process flushes dirty blocks to **datafiles** at appropriate times, such as when freeing buffers or servicing checkpoints. DBWn can write blocks containing uncommitted changes; this remains safe thanks to redo/undo coordination and write-ahead logging rules ensuring redo is written before the corresponding data block.

~~~mermaid
flowchart TD
    A["UPDATE / INSERT in transaction"] --> B["Modify block in buffer cache"]
    A --> C["Generate undo and redo records"]
    C --> D["Redo log buffer"]
    D --> E["LGWR writes online redo log"]
    B --> F["Dirty data block"]
    F --> G["DBWn writes datafile when needed"]
    E --> H["COMMIT can be acknowledged once commit redo is durable"]
~~~

**`COMMIT` does not mean every modified data block has immediately been flushed to datafiles by DBWn.** Under standard commit semantics, Oracle ensures the necessary redo—including the commit record—is durably written by LGWR before reporting commit success. Data blocks may be flushed to datafiles later; Oracle uses redo during instance recovery if a crash occurs before all dirty blocks are written. Specialized asynchronous commit options exist, though they are not the default assumption here.

After commit, the transaction ends and its locks are released. If the application calls `ROLLBACK` before committing, Oracle uses undo to revert the logical effects of the transaction. **Rolling back does not erase redo history already written**, because redo and undo serve different purposes.

### 6.3 A Simple Timeline

| Time | What Happens | Accurate Understanding |
|---|---|---|
| T1 | `UPDATE products` deducts stock and generates undo/redo | The change may still be uncommitted |
| T2 | `INSERT orders` creates order and continues generating undo/redo | Both statements belong to the same transaction |
| T3 | Application calls `COMMIT` | Requests Oracle to finalize the transaction |
| T4 | LGWR ensures redo/commit record is durable, then Oracle confirms normal commit | This is the commit durability point |
| T5 | DBWn writes dirty blocks to datafiles when needed | Can occur before or after T4; not the commit signal itself |

If `INSERT` fails and the application rolls back before T3, both business changes are undone as a single unit. If the Oracle process crashes unexpectedly, during startup/recovery Oracle uses redo to restore required changes and then uses undo to roll back incomplete transactions.

**Online redo logs**, **archive redo logs** (when `ARCHIVELOG` is enabled), and **datafiles** are distinct physical objects. Redo exists for recovery, not for applications to query product records like a SQL table.

## 7. On SELECT: Is Returned Data Always the Latest Data on Disk?

Suppose another user runs:

~~~sql
SELECT product_name, stock_qty
FROM products
WHERE product_id = :id;
~~~

Under Oracle's default **`READ COMMITTED`** isolation level, each SQL statement generally sees a consistent snapshot of committed data as of the moment that statement began. Oracle uses the **System Change Number (SCN)** and undo records when needed to reconstruct the appropriate read version. Therefore:

- If the order transaction has not committed yet, an ordinary `SELECT` in another session will not see those uncommitted changes.
- If the transaction committed before the `SELECT` began, the query will generally see the changes under its read consistency rules.
- A `SELECT` can read data from the buffer cache or reconstruct a consistent version using undo. It does not have to wait for DBWn to flush all dirty blocks to datafiles before committed rows can be read.
- Two separate `SELECT` statements in the same `READ COMMITTED` transaction can observe different results if another transaction commits between them. Other isolation levels have their own rules.

This explains why "what a query currently sees" cannot be determined by opening datafiles directly at the OS level. Datafiles are not plain-text files of SQL rows; Oracle manages blocks, metadata, transaction states, and consistent read versions.

## 8. One Business Request Can Trigger Multiple SQL Operations and Many I/Os

A screen displaying the **top 10 best-selling products** might be expressed by the application as:

~~~sql
SELECT p.product_id,
       p.product_name,
       SUM(o.quantity) AS total_sold
FROM orders o
JOIN products p ON p.product_id = o.product_id
WHERE o.created_at >= :from_time
GROUP BY p.product_id, p.product_name
ORDER BY total_sold DESC
FETCH FIRST 10 ROWS ONLY;
~~~

Here, a single SQL statement performs multiple operations: filtering orders by timestamp, joining orders with products, grouping, summing, sorting, and taking the top 10 rows. Oracle can choose strategies such as nested loops or hash joins; statistics and the actual execution plan are needed to see how it executes on a specific database.

These operations can lead to:

- Reading table or index blocks in the buffer cache, plus physical reads when required.
- Using PGA for hashing/sorting, or TEMP if operations spill to temporary storage.
- Returning only 10 rows **while** processing many source rows to compute the result.
- Triggering additional network round-trips as the application fetches results.

Therefore, **rows returned**, **rows processed by Oracle**, **logical reads**, **physical reads**, and **API response time** are all distinct metrics.

## 9. Observing the Execution Flow Without Guessing How Oracle Runs

You can use `EXPLAIN PLAN` to inspect the estimated execution plan:

~~~sql
EXPLAIN PLAN FOR
SELECT product_name, stock_qty
FROM products
WHERE product_id = 101;

SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Inspect columns/sections such as **Operation**, **Name**, **Rows**, and **Cost** to see the data access strategy. You may see `INDEX UNIQUE SCAN`, `TABLE ACCESS BY INDEX ROWID`, or another access path. `EXPLAIN PLAN` shows the explained plan at the time of invocation and **does not provide actual runtime row counts or I/O** from application executions. For actual runtime analysis—given appropriate privileges and tools—you can inspect the execution plan of an executed cursor (for example via `DBMS_XPLAN.DISPLAY_CURSOR` with runtime statistics collected), SQL trace, or system monitoring tools.

When investigating a slow API, connect the evidence along the chain:

1. **Application:** which request, which business flow, which query, how many DB round-trips, and how long waiting for a connection?
2. **Oracle SQL:** which SQL text and binds, which plan, how many rows processed, and where are CPU/I/O/waits spent?
3. **Memory and storage:** was data served from cache or did it require physical I/O, did sorts spill to TEMP, or were there lock waits or LGWR waits?
4. **Response:** is overall latency dominated by SQL, network, connection pool, application processing, or a combination?

A slow `SELECT` does not automatically mean "slow disk"; it can also result from a poor plan, too many rows scanned, resource contention, DML-related waits, or an application executing SQL too many times. Conversely, fast SQL does not guarantee a fast endpoint if application processing or data serialization/transfer is expensive.

## 10. Misconceptions to Avoid

| Misconception | Accurate Understanding |
|---|---|
| "The application writes SQL tables directly as files." | The application sends SQL; Oracle manages rows, blocks, segments, datafiles, and durability. |
| "The listener executes SQL." | The listener mainly establishes connections; SQL is processed inside Oracle's server/session architecture. |
| "Having a primary key means Oracle always uses an index." | Primary keys usually have a backing index, but the optimizer decides the execution path. |
| "A SELECT equals one disk read." | Oracle has a buffer cache; a SELECT may incur zero, one, or many physical I/Os. |
| "COMMIT immediately writes all tables to datafiles." | Standard commit durability is guaranteed via durable redo; DBWn flushes data blocks on its own schedule. |
| "Redo and undo are the same thing." | Redo records recovery data for changes; undo supports rollback and consistent reads. |
| "Two consecutive SQL statements automatically form one transaction." | Proper transaction boundaries must be configured; auto-commit mode can split them. |
| "Returning only 10 rows means the query is lightweight." | Oracle may have to scan, join, aggregate, or sort a large dataset before returning 10 rows. |

## 11. Scenario-Based Self-Check

**Scenario A:** The stock-deduction `UPDATE` succeeds, but `INSERT orders` violates a constraint. If both are inside an uncommitted transaction, the application should `ROLLBACK`. The inventory deduction is undone logically; the HTTP response must report failure rather than returning success merely because the `UPDATE` ran.

**Scenario B:** The application receives `COMMIT` confirmation, and immediately afterward the instance crashes before all dirty blocks are flushed to datafiles. During recovery, Oracle uses the online redo log to preserve committed changes. Hence the point of **durable redo** matters more than seeing the new record inside a datafile at commit time.

**Scenario C:** One session is updating product 101 without committing yet; another session runs `SELECT stock_qty` in standard consistent-read mode. The reading session sees the committed version matching its statement snapshot, never partial uncommitted edits. Undo can be used to reconstruct that version.

**Scenario D:** The exact same `SELECT` is fast sometimes and slow other times. Compare bind values, execution plans, data volumes, cache/I/O, and wait events rather than judging from SQL text alone. Running a statement twice can show a different I/O profile because the first run warmed the buffer cache.

## 12. Connecting the Entire Journey

An order request follows this chain: **HTTP → Java service → JDBC/transaction → Oracle session → parse/optimize/execute SQL → buffer cache, undo, redo, and data blocks → COMMIT → response returned to the application**. Table and index data are organized as **segment → extent → data block → datafile**, while redo logs support recovery and undo supports rollback/consistent reads.

Whenever you explain an error or performance issue, pinpoint exactly where it sits along this chain. "The SQL statement ran," "the transaction committed," "the block was written to a datafile," and "the user received the HTTP response" are **four distinct events**, even though they often happen close together in a successful request.
