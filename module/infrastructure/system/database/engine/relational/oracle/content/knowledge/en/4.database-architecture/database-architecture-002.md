# Parse, Bind, Execute, and Fetch Flow of an SQL Statement in Oracle

When a Java application calls `PreparedStatement.executeQuery()`, Oracle does not simply receive an SQL string and immediately return all data. On the client and server sides, there is a **parse → bind → execute → fetch** lifecycle. This lifecycle involves cursors, the shared pool, execution plans, sessions, server processes, and Oracle Net. Understanding each stage accurately helps explain why an SQL statement is slow due to excessive parsing, I/O-heavy execution, or transferring and processing too many rows.

In this lesson, we trace a parameterized statement from the moment the application prepares the SQL until it closes the results, then connect it to JDBC and practical Oracle Database observability tools.

## 1. Big Picture: What Do the Four Stages Solve?

Suppose an application wants to retrieve orders for a customer with an amount above a given threshold:

~~~sql
SELECT order_id, amount
FROM lab_orders
WHERE customer_id = :customer_id
  AND amount >= :min_amount
ORDER BY order_id;
~~~

Conceptual flow:

~~~text
Application / Oracle Client                  Oracle Server
──────────────────────────────────────────────────────────────────────
SQL text ─────── PARSE ─────────────────────▶ Check syntax, names, privileges
                                             Look up shareable cursor
                                             Build execution plan if needed

Values, types ── BIND ──────────────────────▶ Attach :customer_id, :min_amount

Run request ──── EXECUTE ───────────────────▶ Start statement
                                             SELECT: open result rows
                                             DML: perform changes

Get results ◀─── FETCH first batch of rows ── Produce/return data rows
Get next    ◀─── FETCH next batch of rows ─── Process/return next rows
            ...                              ...
No more rows◀─── End of results ─────────────

Close ResultSet/Statement                    Release active state
──────────────────────────────────────────────────────────────────────
~~~

| Stage | Focus | Outcome |
|---|---|---|
| **Parse** | Analyze SQL, check semantics, find or create a suitable cursor, optimize plan if needed | Statement is structurally ready to execute |
| **Bind** | Attach **typed values** to placeholders | Concrete input value set for this run |
| **Execute** | Start the statement and perform work appropriate to the SQL type | DML modifies data; SELECT establishes state to read results |
| **Fetch** | Produce/read and transfer SELECT rows to the client in batches | Client receives rows incrementally until results are exhausted |

**Note:** This is a logical operational model; it does not mean there are always four separate network round-trips. The Oracle JDBC driver can defer parsing, send parse/bind/execute together in one round-trip, cache statements, or prefetch data. A single API call can trigger multiple server-side stages.

## 2. Cursors and Related Memory Areas

**Cursor** is the central concept: Oracle needs to store the parsed information of an SQL statement, its execution state, and the current position for reading results. We should distinguish three levels:

1. **SQL text** is the character string statement sent by the application; for example `SELECT ... WHERE customer_id = :customer_id`.
2. **Shared SQL area / shared cursor** resides in the **library cache** inside the **SGA's shared pool**. Parsed SQL information and execution plans can be reused across sessions when compatible.
3. **Private SQL area / session cursor state** holds information specific to an execution or session, such as binds, execution state, and fetch position. Two sessions can share the shared SQL, yet do not share bind values or row fetch positions.

~~~text
             Shared pool / Library cache in SGA
             ┌────────────────────────────────────────┐
SQL text ───▶│ Parent cursor                          │
             │   ├── Child cursor A (context A)       │
             │   └── Child cursor B (context B)       │
             └─────────────────┬──────────────────────┘
                               │ shared when compatible
                   ┌───────────┴────────────┐
                   ▼                        ▼
                Session A                Session B
                Bind id = 7              Bind id = 8
                Fetched to row 10        Fetched to row 50
~~~

A **parent cursor** identifies a form of SQL text; a **child cursor** contains execution information for compatible conditions such as bind types, optimizer environment, resolved privileges/objects, or other factors. Multiple child cursors can exist for the same SQL text; you cannot assume an SQL statement will forever have only one plan.

When closing a `ResultSet` or `PreparedStatement`, the application releases the resources it was using. The shared cursor may continue to be retained by Oracle in the library cache for reuse later. **Closing a statement does not immediately remove shared SQL from the SGA.**

## 3. Parse: Understanding SQL and Deciding How to Execute It

### 3.1. What Does Parse Check?

Oracle may perform the following tasks:

- **Syntax check:** Does the SQL conform to Oracle grammar? For example, `SELECT FROM lab_orders` is invalid because the select expression list is missing.
- **Semantic check:** Can table/column names be resolved, are data types compatible, does the user have the required privileges, and what is the current schema/PDB?
- **Look up a reusable cursor:** Has this SQL been parsed previously under compatible conditions?
- **Optimize when hard parse is required:** Based on statistics, indexes, data volume, filter predicates, joins, and other factors, the optimizer chooses an **execution plan**.
- **Prepare metadata:** Parameter info, output columns, and state needed for execution.

Example:

~~~sql
SELECT order_id
FROM lab_orders
WHERE customer_id = :customer_id;
~~~

Oracle must know which table `LAB_ORDERS` refers to in the session's **PDB and schema**; identify columns `ORDER_ID` and `CUSTOMER_ID`; then reuse an existing cursor if conditions match or choose a new plan.

An SQL statement does not always mean the same thing in every session. For example, `SELECT * FROM lab_orders` can point to different tables if `CURRENT_SCHEMA` differs, or if connected to a different PDB. This is also why schema context, privileges, metadata, and object states affect cursor shareability.

### 3.2. Hard Parse vs. Soft Parse

| Term | Interpretation | Cost |
|---|---|---|
| **Hard parse** | Oracle must create/recreate an eligible cursor and perform optimization work to produce a plan | Can consume significant CPU, metadata checks, and synchronization in the shared pool |
| **Soft parse** | Oracle finds an existing compatible cursor and reuses the parsed information | Usually cheaper than hard parse, though not free |
| **Session cursor cache / statement cache** | Mechanism holding statement handles/state to reduce repeated parsing and opening/closing | Can reduce overhead in highly repetitive workloads |

The three statements below have **different SQL texts** even though only the number changes:

~~~sql
SELECT amount FROM lab_orders WHERE customer_id = 7;
SELECT amount FROM lab_orders WHERE customer_id = 8;
SELECT amount FROM lab_orders WHERE customer_id = 9;
~~~

If a program always constructs SQL by concatenating literals, the library cache can fill up with nearly identical cursors and the workload risks excessive hard parsing. Replace it with:

~~~sql
SELECT amount FROM lab_orders WHERE customer_id = :customer_id;
~~~

The SQL text stays stable and only bind values change per execution, so **cursor reuse becomes possible**. However, you cannot guarantee that every execution uses the same child cursor or plan. Oracle has **bind peeking** and **adaptive cursor sharing**; when data distribution is heavily skewed, different bind value sets may suit different plans.

### 3.3. Where Does the Execution Plan Come In?

The optimizer usually selects a plan during a hard parse. The plan describes the **row sources** and how they combine: table scans, index accesses, filters, joins, sorts, aggregates...

~~~text
SELECT STATEMENT
└── SORT ORDER BY
    └── TABLE ACCESS FULL LAB_ORDERS
        └── Filter customer_id = :customer_id
~~~

This is an illustrative diagram only. When a table has a suitable index or different statistics, Oracle may choose a different plan; certain runtime mechanisms can adapt during execution. Creating a `PreparedStatement` object in the application **does not guarantee** the optimizer has already chosen a plan on the server at that exact moment.

## 4. Bind: Attaching Values Without Rewriting SQL Syntax

A **bind variable** represents a **data value**. In Oracle SQL/PLSQL, `:name` is commonly used; in the JDBC `PreparedStatement` API, positional `?` placeholders numbered from **1** are used.

~~~sql
SELECT order_id, amount
FROM lab_orders
WHERE customer_id = :customer_id
  AND amount >= :min_amount;
~~~

If the first run uses `customer_id = 7` and `min_amount = 100`, and the second run uses `customer_id = 8` and `min_amount = 200`, the SQL text remains the exact same statement. Oracle separates **typed values** from SQL syntax, enabling cursor reuse and reducing SQL injection risk.

In JDBC:

~~~java
String sql = """
    SELECT order_id, amount
    FROM lab_orders
    WHERE customer_id = ?
      AND amount >= ?
    ORDER BY order_id
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 7L);
    ps.setBigDecimal(2, new BigDecimal("100.00"));

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("ORDER_ID");
            BigDecimal amount = rs.getBigDecimal("AMOUNT");
            System.out.println(orderId + " -> " + amount);
        }
    }
}
~~~

`setLong(1, 7L)` binds the first placeholder as a numeric type; `setBigDecimal(2, ...)` binds the second placeholder. For date/time columns, use appropriate temporal types and JDBC APIs rather than concatenating date strings that depend on `NLS_DATE_FORMAT`. When binding null values, `setNull(index, sqlType)` lets the driver know the expected type.

**Binds replace values only, not identifiers or SQL structure.** You cannot write `SELECT * FROM ?` and bind a table name to `?`, nor can you bind an `ASC`/`DESC` keyword like an ordinary value. For user-selected column names, the application should use an allowlist:

~~~java
String orderBy = switch (sortKey) {
    case "amount" -> "amount";
    case "created" -> "created_at";
    default -> "order_id";
};
String sql = "SELECT order_id, amount FROM lab_orders ORDER BY " + orderBy;
~~~

Directly concatenating untrusted input into SQL both destroys statement shareability and opens the door to SQL injection:

~~~java
// Unsafe
String sql = "SELECT * FROM lab_orders WHERE customer_id = " + input;

// Safer for a numeric value
String safeSql = "SELECT * FROM lab_orders WHERE customer_id = ?";
try (PreparedStatement ps = connection.prepareStatement(safeSql)) {
    ps.setLong(1, customerId);
    // execute/fetch
}
~~~

### When Binds Can Affect the Plan

Suppose `customer_id = 1` returns 500,000 rows, while `customer_id = 999` returns 1 row. It is the same SQL text with binds, yet selectivity differs drastically. During hard parse, **bind peeking** can factor bind values into cardinality estimates; **adaptive cursor sharing** can create or pick different child cursors. Behavior depends on version, statistics, and environment. Use binds to ensure **safe value passing and cursor reuse opportunities**; do not assume every bind runs with the same duration or plan.

## 5. Execute: SELECT Differs from DML

Once the cursor is prepared and required binds have values, Oracle begins processing the statement. **Execute for SELECT** has different semantics from **execute for INSERT/UPDATE/DELETE**.

### 5.1. SELECT: Opening the Ability to Read Results

For SELECT, execute initializes execution state and allows the client to retrieve rows via fetch. Many operations actually occur **when the client requests the next row**. Oracle's row-source mechanism is **demand-driven**: an operator needing a row asks the operator below it to produce rows.

~~~text
Client calls fetch
        │
        ▼
SELECT cursor needs rows
        │
        ▼
SORT / JOIN / FILTER / TABLE ACCESS / INDEX ACCESS
        │
        ▼
Database buffers / I/O / undo to obtain the consistent version
        │
        ▼
Return row or batch of rows to client
~~~

The first row is not always returned immediately. With an `ORDER BY` requiring a sort, the operation may have to read and sort a large volume of data before producing the first row; with an appropriate index, part of the sort may be avoided. Therefore, **`executeQuery()` returning quickly does not mean the entire SQL has finished executing**.

### 5.2. DML: Execute Performs Changes

For DML:

~~~sql
UPDATE lab_orders
SET amount = amount + 10
WHERE customer_id = :customer_id;
~~~

Execute updates the matching rows, may generate undo/redo, acquires row locks, and may encounter lock/I/O waits. The `executeUpdate()` API typically returns the **number of affected rows**, rather than creating a `ResultSet` to fetch like a standard SELECT.

Changes belong to a **transaction**. Successful execution does not mean it has been committed:

~~~java
connection.setAutoCommit(false);
try {
    String sql =
        "UPDATE lab_orders SET amount = amount + ? WHERE customer_id = ?";
    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setBigDecimal(1, new BigDecimal("10.00"));
        ps.setLong(2, 7L);
        int count = ps.executeUpdate();
        System.out.println("Rows affected = " + count);
    }
    connection.commit();
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
}
~~~

When `autoCommit` is enabled, JDBC manages commits according to statement completion rules; for operations requiring multi-step consistency, configure transactions explicitly. Oracle DDL (`CREATE TABLE`, `ALTER TABLE`...) has its own commit semantics distinct from DML. PL/SQL calls with OUT parameters or REF CURSORs may require different ways of retrieving results.

### 5.3. Read Consistency During Long-Running SELECTs

Oracle uses **multiversion read consistency** so a SELECT sees a dataset consistent as of its snapshot point and isolation level. While one session is fetching a long query, other sessions can still commit changes; Oracle uses **undo** when needed to reconstruct the appropriate data version for the older query.

If a query needs to read data that is too old and the required undo information is no longer available, `ORA-01555: snapshot too old` may occur during reading. This demonstrates that part of consistency checking/reading work can take place after the execute call, during fetch.

## 6. Fetch: Data Is Retrieved in Batches

For SELECT, JDBC typically returns a `ResultSet` object. Each call to `rs.next()` moves the client to the next row. The driver may have **prefetched multiple rows** and buffered them on the client side; a single `rs.next()` **does not necessarily** cause a network round-trip.

~~~text
Oracle server                             Client / JDBC
──────────────────────────────────────────────────────────────
FETCH request ── 50 rows ────────────────▶ Buffer of 50 rows
                                           rs.next() -> row 1
                                           ...
                                           rs.next() -> row 50
FETCH request ── 50 more rows ──────────▶ Buffer of 50 rows
                                           ...
FETCH request ── end of data ───────────▶ rs.next() -> false
──────────────────────────────────────────────────────────────
~~~

The number 50 is illustrative only. Actual batch size depends on the driver, column types, data sizes, row prefetch, fetch size, and other factors.

### 6.1. JDBC Fetch Size

~~~java
String sql = """
    SELECT order_id, customer_id, amount
    FROM lab_orders
    ORDER BY order_id
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setFetchSize(100);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong(1);
            long customerId = rs.getLong(2);
            BigDecimal amount = rs.getBigDecimal(3);
            // Process one row in Java
        }
    }
}
~~~

`setFetchSize(100)` is a **hint** to the JDBC driver; it does not guarantee exactly 100 rows in every round-trip. Too small a fetch size can increase network round-trips when tens of thousands of rows are needed. Too large a fetch size can increase client memory usage, latency to the first row, or wasted data transfer if the application stops reading early.

**Fetch size does not limit the result row count of the SQL query.** If the application only wants 20 rows, limit it in SQL:

~~~sql
SELECT order_id, amount
FROM lab_orders
ORDER BY order_id
FETCH FIRST 20 ROWS ONLY;
~~~

In the example above, `FETCH FIRST 20 ROWS ONLY` is an SQL **row limiting clause**. It is distinct from the **cursor fetch stage**. Paginated queries need a deterministic `ORDER BY` so result ordering is predictable.

### 6.2. Why Is Fetch Slow?

There are many causes:

- The query returns hundreds of thousands of rows even though the UI only needs one page.
- Each row contains too many columns, large values, or LOBs.
- Network latency is high and the driver fetches in batches that are too small.
- Sort, join, aggregate, or block-reading operations are still running to produce subsequent rows.
- The application maps objects, writes logs, or performs heavy processing per row.
- The program fires an extra SQL query for every fetched row, causing **N+1 queries**.

It helps to distinguish **time to first row** from **time to consume all rows**. A search screen needing to display the first page quickly differs from an ETL job needing to read an entire dataset efficiently.

### 6.3. How Do Execute and Fetch Affect Network Round-Trips?

If an application calls `prepareStatement()` once, `setLong()` twice, `executeQuery()` once, and `rs.next()` 1,000 times, that does not mean 1,004 round-trips occurred:

- `setXxx()` typically only updates bind value state on the client.
- The driver can combine or defer parse, bind, and execute.
- `rs.next()` usually reads from the already-fetched buffer.
- Prefetching or transaction operations can alter round-trip counts.

To measure network round-trips accurately, use proper driver/session metrics or observability tools rather than inferring from lines of Java code.

## 7. Full Hands-On Walkthrough in SQL*Plus or SQLcl

The example can be run on an application schema in a practice PDB with table creation privileges. Create the table:

~~~sql
CREATE TABLE lab_orders (
    order_id     NUMBER PRIMARY KEY,
    customer_id  NUMBER NOT NULL,
    amount       NUMBER(12,2) NOT NULL,
    created_at   DATE DEFAULT SYSDATE NOT NULL
);

INSERT INTO lab_orders (order_id, customer_id, amount)
VALUES (101, 7, 150.00);
INSERT INTO lab_orders (order_id, customer_id, amount)
VALUES (102, 7, 80.00);
INSERT INTO lab_orders (order_id, customer_id, amount)
VALUES (103, 8, 250.00);
INSERT INTO lab_orders (order_id, customer_id, amount)
VALUES (104, 7, 320.00);
COMMIT;
~~~

Initialize bind variables and run the statement:

~~~sql
VARIABLE v_customer_id NUMBER
VARIABLE v_min_amount NUMBER

EXEC :v_customer_id := 7
EXEC :v_min_amount := 100

SELECT order_id, amount
FROM lab_orders
WHERE customer_id = :v_customer_id
  AND amount >= :v_min_amount
ORDER BY order_id;
~~~

Expected output:

~~~text
ORDER_ID    AMOUNT
--------    ------
101         150
104         320
~~~

Without changing the SQL text, change only the binds:

~~~sql
EXEC :v_customer_id := 8
EXEC :v_min_amount := 200

SELECT order_id, amount
FROM lab_orders
WHERE customer_id = :v_customer_id
  AND amount >= :v_min_amount
ORDER BY order_id;
~~~

Now only row `103` with amount `250` remains. You can try `SET ARRAYSIZE 2` in SQL*Plus to change the client's array fetch size and then run a multi-row query. `VARIABLE`, `EXEC`, and `SET ARRAYSIZE` are SQL*Plus/SQLcl client commands, not standard JDBC SQL syntax.

### Corresponding Timeline in JDBC

~~~text
connection.prepareStatement(sql)
      │
      └── Prepare handle; actual parse may occur or be deferred
ps.setLong(1, ...)
ps.setBigDecimal(2, ...)
      │
      └── BIND at API layer: set values and types for placeholders
ps.executeQuery()
      │
      └── EXECUTE; driver may send PARSE + BIND in the same round-trip
rs.next() ... rs.next()
      │
      └── FETCH from buffer; when another batch is needed, driver contacts server
rs.close(); ps.close()
      │
      └── Release result/statement resources
~~~

Java does not have to call `parse()` as a separate JDBC API. Counting `prepareStatement()` calls is also insufficient to determine actual server-side hard parses because the driver and server have their own caching and deferral mechanisms.

## 8. Observing Parse, Execute, and Fetch on Oracle

An actual SQL statement can be observed via cursor statistics, execution plans, and traces. The administrative views/tools below may require appropriate privileges; results reflect the observed environment and execution.

### 8.1. Statistics from `V$SQL`

~~~sql
SELECT
    sql_id,
    child_number,
    executions,
    parse_calls,
    fetches,
    rows_processed,
    buffer_gets,
    disk_reads,
    elapsed_time
FROM v$sql
WHERE sql_id = :target_sql_id
ORDER BY child_number;
~~~

| Column | Interpretation |
|---|---|
| `SQL_ID` | Identifier for the SQL text |
| `CHILD_NUMBER` | Distinguishes child cursors of the SQL |
| `EXECUTIONS` | Number of recorded executions |
| `PARSE_CALLS` | Number of parse calls; **not synonymous with hard parse count** |
| `FETCHES` | Number of recorded fetch calls; **not synonymous with row count** |
| `ROWS_PROCESSED` | Total rows processed per cursor stats; meaning varies by statement type |
| `BUFFER_GETS` | Total logical buffer accesses |
| `DISK_READS` | Total physical reads recorded |
| `ELAPSED_TIME` | Cumulative execution time (microseconds) per Oracle statistics |

These numbers typically **accumulate over the lifetime of the child cursor** and can include multiple runs and multiple sessions. Reading `V$SQL` once does not automatically give metrics solely for the single request just measured. Cursors can also be aged out or invalidated. In RAC, consider per-instance scope; when appropriate, use the `GV$SQL` view.

### 8.2. Estimated Plan vs. Actual Execution Activity

`EXPLAIN PLAN` shows the estimated plan in the parse context; the executed plan and actual runtime statistics can be viewed using `DBMS_XPLAN.DISPLAY_CURSOR` when authorized:

~~~sql
SELECT /*+ gather_plan_statistics */
       order_id, amount
FROM lab_orders
WHERE customer_id = :v_customer_id
ORDER BY order_id;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(NULL, NULL, 'ALLSTATS LAST')
);
~~~

Output may include `E-Rows` (estimated rows), `A-Rows` (actual rows), `Starts`, and buffers. If the client only fetches part of the results and then closes, actual row counts/work may reflect **only the consumed portion**, not the full potential row count. In environments with many interleaved SQL statements, specify the exact `SQL_ID`/`CHILD_NUMBER` of the statement under analysis.

### 8.3. SQL Trace and TKPROF

Oracle SQL trace can display calls in a format like:

~~~text
PARSE ...
EXEC  ...
FETCH ...
FETCH ...
FETCH ...
~~~

**TKPROF** summarizes trace information, helping compare parse/execute/fetch call counts, CPU, elapsed time, I/O, rows, and waits. If the session has privileges, tracing can be enabled for a test run:

~~~sql
BEGIN
    DBMS_MONITOR.SESSION_TRACE_ENABLE(
        waits => TRUE,
        binds => FALSE
    );
END;
/

-- Run the target SQL and consume all result rows.

BEGIN
    DBMS_MONITOR.SESSION_TRACE_DISABLE;
END;
/
~~~

`binds => FALSE` avoids actively logging bind values into the trace since they may contain sensitive data. Trace files are created on the server and carry observation overhead; appropriate privileges and scope are required, often involving a DBA to retrieve the file and run TKPROF.

### 8.4. Diagnosing the Right Kind of Latency

| Symptom | Stage to Inspect | Practical Checks |
|---|---|---|
| High CPU when sending many SQLs differing only in literals | Parse | Hard parses, shared pool, distinct SQL texts, binding/caching |
| An `UPDATE` runs slowly or waits on locks | Execute | Plan, row locks, transactions, affected row count |
| `executeQuery()` is fast, yet reading `ResultSet` is very slow | Fetch and row sources | Row count, fetch size, network, application processing, plan |
| Query is slow for certain bind values | Parse/optimizer and execute | Selectivity, statistics, child cursors, and actual plan |
| `rs.next()` triggers thousands of extra SQLs | Application and repeated statements | N+1 queries; consider joins or batch queries |

## 9. Common Errors by Point in the Lifecycle

An exception at `executeQuery()` does not necessarily originate only from the execute stage; the driver may send parse/bind/execute in the same API call.

| Message / Symptom | Likely Source | What to Check |
|---|---|---|
| `ORA-00933` | SQL syntax at parse | Oracle SQL syntax, delimiters, SQL sent by driver |
| `ORA-00942` | Object name, schema/PDB, or privileges | User, `CURRENT_SCHEMA`, owner, grants, PDB |
| `ORA-01008` | Missing bind on execution | Have all placeholders received compatible values/types? |
| `ORA-00001` | Unique constraint violation during DML | Keys, input data, constraints |
| `ORA-00060` | Deadlock during DML/transaction | Lock ordering, involved sessions |
| `ORA-01555` | Insufficient undo for query snapshot | Long-running query, undo retention, concurrent changes |
| `ORA-01000` | Too many open cursors | Closing `ResultSet`/`Statement`, managing statement cache |
| Many fetches yet few rows returned | Batch fetch, filtering, and row-source processing | Check plan/counters instead of inferring row count from `FETCHES` |

**Note on `ORA-01000`:** this error relates to the session's open cursor count; failing to properly close statements/result sets is a frequent cause, though caching mechanisms and the `OPEN_CURSORS` configuration should also be evaluated.

## 10. Misconceptions to Avoid

1. **"Every SQL execution does a hard parse."** No. Shared cursors, soft parses, and caches reduce this work.
2. **"Calling `prepareStatement()` means the server has finished parsing."** Not necessarily. The driver may defer parsing.
3. **"Binding means substituting text into SQL and Oracle re-parsing it."** Binding passes **typed values**, separate from the SQL text.
4. **"Binds always produce a single fixed plan."** Child cursors, bind peeking, and optimizer factors can cause plans to differ.
5. **"Executing a SELECT computes the entire result set upfront."** Much of the row-producing work happens during fetch.
6. **"One `rs.next()` always equals one round-trip."** Drivers normally buffer results in batches.
7. **"Fetch size limits the query result size."** To limit rows, use conditions or a row limiting clause in SQL.
8. **"Closing a ResultSet makes Oracle delete the shared SQL."** The shared cursor can remain in the library cache.
9. **"`PARSE_CALLS` indicates the hard parse count."** No; it is the total number of parse calls.
10. **"One execute has only one fetch."** A SELECT can be fetched across multiple batches, or the client may stop reading early.

## 11. Practice Questions and Exercises

### Exercise 1: SQL Text and Cursor Sharing

An application runs three SQL texts with literals `customer_id = 1`, `= 2`, and `= 3`. Why is replacing them with `customer_id = :id` usually helpful?

**Guidance:** Keeping the SQL text stable gives Oracle the opportunity to reuse the shared cursor; binding does not guarantee a single fixed child cursor/plan.

### Exercise 2: Stopping Result Reading Early

A SELECT can potentially return 100,000 rows, yet Java calls `rs.next()` only 10 times before closing the ResultSet. Can we conclude Oracle sent all 100,000 rows?

**Guidance:** No. The driver may prefetch more than 10 rows; some operators may process substantial data before returning the first row, but there is no rule forcing the entire result set to be sent.

### Exercise 3: Executed but Not Committed

`executeUpdate()` returns `1`. The application has `autoCommit = false` and then calls `rollback()`. Does committed data change?

**Guidance:** No. The statement executed and affected one row within the transaction, but uncommitted changes can be rolled back.

### Exercise 4: Fetch Size and Latency

An ETL job reads 50,000 rows over a high-latency network with `fetchSize = 1`. Why can it be slow even when parse and execute are fast?

**Guidance:** The number of network fetches can be very high; consider increasing fetch size, reducing returned data, and measuring the duration of the entire fetch loop.

### Exercise 5: Different Plans Despite Identical SQL

With the same SQL `WHERE customer_id = :id`, one value returns one row while another returns several hundred thousand rows. Why might the plan differ?

**Guidance:** Differing selectivity, statistics, bind peeking, and adaptive cursor sharing can all contribute to Oracle using an appropriate child cursor/plan.

## 12. Quick Summary Diagram

~~~text
SQL TEXT
   |
   v
PARSE    Syntax, semantics, shared cursor, optimizer plan when needed
   |
   v
BIND     Pass parameter values and types, without changing SQL syntax
   |
   v
EXECUTE  Start SELECT or perform DML
   |       └── DML involves transactions, COMMIT / ROLLBACK
   v
FETCH    Read SELECT rows in batches; process row sources and I/O
   |
   v
CLOSE    Close cursor-related resources on the client side
~~~

When analyzing Oracle performance, ask in order: **Are there too many hard parses? Are binds properly typed with stable SQL text? Is execute spending excessive I/O or waiting on locks? Is fetch transferring too many rows or making too many round-trips?** Separating these four stages helps interpret Oracle metrics accurately and pick the right tuning measures for Java/JDBC applications.
