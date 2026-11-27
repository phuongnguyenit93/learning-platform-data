# Prefer Set-Based SQL Before Using Loops

## Objectives

After this lesson, you will be able to:

- Identify problems that can be solved with a single set-based SQL statement.
- Replace row-by-row loops with `UPDATE ... JOIN`, `INSERT ... SELECT`, `DELETE ... JOIN`, aggregates, and `CASE` expressions.
- Use CTEs, derived tables, and window functions to transform grouped data.
- Choose a batching approach when a single statement is too large or holds locks for too long.
- Explain when a cursor inside a stored program is genuinely necessary.
- Properly use the MySQL cursor lifecycle: `DECLARE`, `OPEN`, `FETCH`, and `CLOSE`.
- Handle `NOT FOUND`, SQL errors, and close cursors safely.
- Avoid common pitfalls such as N+1 queries, `NOT FOUND` handlers accidentally catching `SELECT INTO`, and long-running transactions.
- Measure effectiveness using execution plans, affected row counts, locks, and execution time.

This lesson focuses on MySQL 8.0/8.4 and stored procedures. Examples use illustrative tables; adapt column names, data types, and business conditions to your actual schema.

## 1. Set-Based Thinking

SQL is designed to describe the desired outcome over a set of rows. You state the filter conditions and transformations; the optimizer decides how to read indexes, join, filter, group, and write data.

For example, raising prices by 5% for all products in a category:

```sql
UPDATE products
SET price = ROUND(price * 1.05, 2)
WHERE category_id = 12
  AND status = 'ACTIVE';
```

An application-layer loop typically has to:

1. SELECT the list of products.
2. Read each row.
3. Calculate the new price in the application.
4. Send an UPDATE for each product.

A single set-based `UPDATE` statement expresses the entire job. MySQL can choose an appropriate access plan and perform the operation in one statement.

### 1.1. Why Prefer Set-Based SQL?

- **Fewer round trips:** the application sends fewer statements over the network.
- **Broader optimizer visibility:** MySQL can optimize joins, filters, grouping, and indexes across the whole query.
- **Less orchestration code:** reduces loop state, temporary variables, and error branches in application code.
- **Clearer consistency:** one statement generally has simpler execution and error boundaries than many scattered statements.
- **Easier observability:** you can use `EXPLAIN`, `EXPLAIN ANALYZE`, `ROW_COUNT()`, and Performance Schema to measure.

Set-based does not mean every operation is cheap or always fast. A massive UPDATE can lock many rows, generate heavy undo/redo, or cause replication lag. In such cases you need indexes, better filters, or batching—not defaulting to a cursor.

### 1.2. First Questions Before Writing a Loop

Ask yourself:

1. Can the target row set be expressed with `WHERE`?
2. Can source data be linked using `JOIN`?
3. Can the result be computed using `CASE`, aggregates, or window functions?
4. Can data be written directly using `INSERT ... SELECT`, `UPDATE`, or `DELETE`?
5. Is row-by-row processing order required because each step depends on the previous step's result?
6. Are there per-row side effects that SQL cannot reasonably express?

Only when answers to the final questions show that sequential coordination is required should you consider a cursor or an application-layer loop.

## 2. Replacing Loops with Set-Based UPDATE

Suppose we have the table:

```sql
CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL,
    category_id BIGINT UNSIGNED NOT NULL,
    price DECIMAL(12,2) NOT NULL,
    stock INT NOT NULL,
    status VARCHAR(20) NOT NULL,
    stock_state VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN',
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (product_id),
    KEY idx_products_category_status (category_id, status)
) ENGINE = InnoDB;
```

### 2.1. Updating Many Rows with the Same Rule

Instead of fetching each product and updating individually:

```sql
UPDATE products
SET status = 'INACTIVE',
    updated_at = CURRENT_TIMESTAMP(6)
WHERE category_id = 12
  AND stock = 0
  AND status = 'ACTIVE';
```

The filter conditions identify the row set. Every row in the set is updated by the same rule.

### 2.2. Multiple Business Branches with CASE

When each row receives a different value depending on conditions, an IF inside a loop is unnecessary:

```sql
UPDATE products
SET stock_state = CASE
        WHEN stock = 0 THEN 'OUT_OF_STOCK'
        WHEN stock < 10 THEN 'LOW_STOCK'
        ELSE 'AVAILABLE'
    END,
    updated_at = CURRENT_TIMESTAMP(6)
WHERE status = 'ACTIVE';
```

`CASE` evaluates conditions for each row within the same statement. Order branches by priority: more specific conditions should appear before more general ones.

### 2.3. Updating from Another Table with UPDATE JOIN

Suppose customer credit limits need syncing from a policy table:

```sql
UPDATE customers AS c
JOIN customer_policies AS p
  ON p.policy_id = c.policy_id
SET c.credit_limit = p.credit_limit,
    c.updated_at = CURRENT_TIMESTAMP(6)
WHERE c.policy_id IS NOT NULL
  AND c.credit_limit <> p.credit_limit;
```

A single `UPDATE ... JOIN` replaces reading each customer, querying the matching policy, and running per-row UPDATEs.

The `<>` predicate skips unchanged rows to reduce unnecessary writes. If columns are nullable, use an appropriate null-safe comparison such as `NOT (c.credit_limit <=> p.credit_limit)`.

### 2.4. Updating from Aggregate Results

Suppose the `orders` table stores order totals. We need to update total paid revenue per customer:

```sql
UPDATE customer_summary AS s
JOIN (
    SELECT
        customer_id,
        SUM(total_amount) AS paid_total
    FROM orders
    WHERE status = 'PAID'
    GROUP BY customer_id
) AS x
  ON x.customer_id = s.customer_id
SET s.paid_total = x.paid_total,
    s.updated_at = CURRENT_TIMESTAMP(6);
```

A derived table computes sums per customer, then joins to update the summary table. If totals must be reset to 0 for customers with no paid orders, use a `LEFT JOIN` from the customers/summary table with `COALESCE`, while clearly defining which customer set to sync.

### 2.5. Notes When Using UPDATE JOIN

- The JOIN condition must determine a single source value for each target row; if one target row matches multiple source rows with different values, results may not match business expectations.
- Create appropriate indexes on JOIN and filter columns.
- Check affected row counts before running in production.
- For risky operations, run a SELECT with the exact same JOIN conditions to preview the affected row set.
- Do not drop tenant, date range, or status filters when moving logic from application code to SQL.

## 3. Replacing Loops with INSERT ... SELECT

When generating summary records or moving data from a source table to a target table, use `INSERT ... SELECT`.

Example daily report table:

```sql
CREATE TABLE daily_customer_sales (
    sales_date DATE NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_count BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(18,2) NOT NULL,
    PRIMARY KEY (sales_date, customer_id)
) ENGINE = InnoDB;
```

Generate the summary for one day:

```sql
INSERT INTO daily_customer_sales (
    sales_date,
    customer_id,
    order_count,
    total_amount
)
SELECT
    DATE(created_at) AS sales_date,
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_amount
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-11-01 00:00:00'
  AND created_at <  '2026-11-02 00:00:00'
GROUP BY DATE(created_at), customer_id;
```

No per-customer loop is needed. MySQL groups the data and inserts the results directly.

### 3.1. Avoiding Duplicate Processing on Retries

If a job may retry, establish an idempotent strategy. For summary tables, you can delete the date range and reload within a proper transaction:

```sql
START TRANSACTION;

DELETE FROM daily_customer_sales
WHERE sales_date = '2026-11-01';

INSERT INTO daily_customer_sales (
    sales_date,
    customer_id,
    order_count,
    total_amount
)
SELECT
    DATE(created_at),
    customer_id,
    COUNT(*),
    SUM(total_amount)
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-11-01 00:00:00'
  AND created_at <  '2026-11-02 00:00:00'
GROUP BY DATE(created_at), customer_id;

COMMIT;
```

If a statement fails, the application handles the error and runs `ROLLBACK`. This works well when the date range is small enough and tables use a transactional engine like InnoDB.

### 3.2. Upserting with a Unique Key

When overwriting or accumulating on a unique key, you can use `INSERT ... ON DUPLICATE KEY UPDATE`. Design the update operation so retries do not double-count. For example, assigning the newly computed total is more idempotent than adding the same total each time a job reruns.

## 4. Replacing Loops with DELETE JOIN

Suppose we need to delete expired sessions belonging to locked users:

```sql
DELETE s
FROM user_sessions AS s
JOIN users AS u
  ON u.user_id = s.user_id
WHERE u.account_status = 'LOCKED'
  AND s.expires_at < CURRENT_TIMESTAMP;
```

`DELETE ... JOIN` selects and deletes the target row set in a single statement. Before running, preview with a SELECT:

```sql
SELECT s.session_id, s.user_id, s.expires_at
FROM user_sessions AS s
JOIN users AS u
  ON u.user_id = s.user_id
WHERE u.account_status = 'LOCKED'
  AND s.expires_at < CURRENT_TIMESTAMP;
```

If deleting in batches to reduce lock duration, limit rows per statement with `ORDER BY ... LIMIT` in a single-table DELETE, or select primary keys per batch and delete via JOIN against that key set. Do not switch to a cursor simply because a table has many rows.

## 5. Aggregates, CTEs, and Window Functions Instead of Calculation Loops

### 5.1. Aggregates Instead of Loop Counters

There is no need to read every order row just to sum revenue:

```sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_amount,
    AVG(total_amount) AS average_order_amount
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id;
```

`GROUP BY` performs grouping inside the database. To persist results, combine with `INSERT ... SELECT` or UPDATE JOIN.

### 5.2. CTEs to Separate Logical Steps

CTEs make multi-step queries readable without declaring variables for every row:

```sql
WITH customer_totals AS (
    SELECT
        customer_id,
        SUM(total_amount) AS paid_total
    FROM orders
    WHERE status = 'PAID'
    GROUP BY customer_id
), ranked_customers AS (
    SELECT
        customer_id,
        paid_total,
        DENSE_RANK() OVER (ORDER BY paid_total DESC) AS revenue_rank
    FROM customer_totals
)
SELECT customer_id, paid_total, revenue_rank
FROM ranked_customers
WHERE revenue_rank <= 10;
```

The query ranks top customers using a window function instead of iterating over every customer and maintaining rankings in application variables.

### 5.3. Window Functions Instead of Running Variables

Example calculating a running balance per account:

```sql
SELECT
    account_id,
    entry_id,
    posted_at,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY posted_at, entry_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_balance_change
FROM ledger_entries;
```

Ordering must be deterministic. `entry_id` serves as a tie-breaker when multiple transactions share the same `posted_at`.

### 5.4. UPDATE from a CTE or Derived Result

When writing statuses based on rankings, you can place a CTE before UPDATE in MySQL 8.0:

```sql
WITH ranked AS (
    SELECT
        employee_id,
        ROW_NUMBER() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC, employee_id
        ) AS salary_position
    FROM employees
)
UPDATE employees AS e
JOIN ranked AS r
  ON r.employee_id = e.employee_id
SET e.salary_band = CASE
        WHEN r.salary_position = 1 THEN 'TOP'
        WHEN r.salary_position <= 3 THEN 'HIGH'
        ELSE 'STANDARD'
    END;
```

Verify syntax on your target MySQL version and evaluate the execution plan on large datasets.

## 6. N+1 Queries: Loops Often Hide in Application Code

A common loop pattern does not use SQL cursors at all—it appears in application code:

1. SELECT 100 customers.
2. For each customer, run a SELECT to fetch orders.
3. For each order, run another SELECT to fetch line items.

With 100 customers, round trips can multiply into hundreds. That is the N+1 query problem.

Replace it with a JOIN:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.created_at,
    o.total_amount
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID'
WHERE c.tenant_id = ?
ORDER BY c.customer_id, o.created_at DESC, o.order_id DESC;
```

Or fetch two datasets in batch and assemble them in the application if JOIN causes excessive row multiplication or aggregates need separate handling. The key is reducing round trips and avoiding repeated queries per ID.

## 7. Batching When a Set-Based Statement Is Too Large

A single set-based statement might touch millions of rows. Even with minimal round trips, it can hold locks too long, generate huge undo/redo, increase replication lag, or pressure the buffer pool.

Batching keeps set-based SQL operating in small chunks.

### 7.1. Batched UPDATE Pattern

For example, updating at most 1,000 old orders per pass:

```sql
UPDATE orders
SET archive_candidate = 1
WHERE archive_candidate = 0
  AND created_at < '2025-01-01 00:00:00'
ORDER BY order_id
LIMIT 1000;
```

The application or orchestrating job repeats this statement in short transactions:

1. `START TRANSACTION`.
2. Execute the batch UPDATE.
3. Capture changed rows with `ROW_COUNT()` immediately after UPDATE.
4. `COMMIT`.
5. If row count is 0, stop; otherwise, run the next batch.

Committing each batch releases locks and bounds undo size. The `archive_candidate = 0` predicate prevents already-processed rows from being selected again. Ensure no concurrent process continuously inserts matching rows that would keep the job running indefinitely.

### 7.2. Why Not Use OFFSET for Batching?

`LIMIT 1000 OFFSET 500000` still scans and discards many rows. For large tables, use keyset pagination or an indexed primary key condition:

```sql
SELECT order_id
FROM orders
WHERE order_id > ?
  AND created_at < '2025-01-01 00:00:00'
ORDER BY order_id
LIMIT 1000;
```

The application saves `last_order_id` from the processed batch and feeds it to the next batch. If multiple workers must run concurrently, use a safe batch-claiming mechanism such as a claim status, row locks, or key-range partitioning; never share a single cursor across workers.

### 7.3. Choosing Batch Size by Measurement

Batches that are too small increase round trips and commit overhead. Batches that are too large hold locks longer and strain I/O. Start with a moderate size, measure duration, row count, lock waits, redo/undo, and replication lag, then tune.

### 7.4. Ensuring Consistency Across Multi-Transaction Batches

Multiple separately committed batches do not share a single snapshot for the entire job. New data can appear between batches; rows can change filter eligibility. Determine:

- Should the range be bounded by a high-water mark?
- Should rows inserted while running belong to the current job?
- If a batch fails, is re-running safe?
- Is a checkpoint saved to resume?
- Is an idempotency key or job progress table required?

## 8. When Is a Loop Genuinely Necessary?

A loop is appropriate when a workflow has sequential dependencies or per-item orchestration that cannot reasonably be expressed in a single SQL statement.

Examples:

- Each entity must invoke a specialized stored procedure with multi-step branching rules.
- An allocation algorithm maintains remaining state after each allocation, where processing order is part of the business rule.
- Early stopping is required based on conditions computed from preceding rows.
- A step requires isolated per-item error handling recording independent success/failure outcomes.
- Interaction with resources outside the database is needed; this case usually fits an application loop better than holding a MySQL cursor and transaction open.

Before picking a cursor, check whether window functions, recursive CTEs, staging tables, stateful queues, or keyset batches can solve the problem more simply.

### 8.1. Cursors Are Not a Default Replacement for SELECT

A cursor reads rows one by one from a result set for stored program processing. Each `FETCH` loads values into local variables; subsequent logic runs row by row.

Cursors can be useful, but typically add:

- Cursor state and termination handlers.
- `OPEN`, `FETCH`, `CLOSE` control code.
- Per-row processing overhead.
- Risk of holding transactions/locks too long if read/write logic takes time.
- Memory or temporary table pressure if the result set is large.

If an `UPDATE JOIN` or `INSERT ... SELECT` expresses the same business logic, prefer that statement.

## 9. Characteristics of Cursors in MySQL

Cursors in MySQL stored programs have three key characteristics:

- **Asensitive:** the server may use an internal copy of the result set; applications should not rely on underlying table modifications updating rows currently being traversed.
- **Read-only:** you cannot use a cursor to directly update the current row via positioned update syntax.
- **Nonscrollable:** `FETCH` moves forward only; you cannot jump backward or move to an arbitrary position.

MySQL cursors are used inside stored programs. A cursor is declared for a SELECT query; it is not an arbitrary client-side scrollable or updatable cursor.

### 9.1. Cursor Lifecycle

```text
DECLARE cursor
      |
      v
    OPEN
      |
      v
    FETCH -----> process row
      |              |
      |              +----> next FETCH
      v
   NOT FOUND
      |
      v
    CLOSE
```

Steps:

1. `DECLARE CURSOR FOR SELECT ...` declares the cursor query.
2. `OPEN cursor_name` executes the query and opens the cursor.
3. `FETCH cursor_name INTO ...` retrieves the next row into variables.
4. When no rows remain, MySQL raises the `NOT FOUND` condition with SQLSTATE class `02`.
5. `CLOSE cursor_name` releases the cursor.

### 9.2. DECLARE Ordering Rules

Within a `BEGIN ... END` block, the declaration order is:

1. Local variables and conditions.
2. Cursors.
3. Handlers.

Example:

```sql
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_customer_id BIGINT UNSIGNED;

    DECLARE cur_customers CURSOR FOR
        SELECT customer_id
        FROM customers
        WHERE account_status = 'REVIEW'
        ORDER BY customer_id;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    -- OPEN, FETCH, CLOSE in block body
END;
```

Do not place `DECLARE CURSOR` after an executable statement or after a handler in the same block.

### 9.3. Cursor SELECT Should Have Deterministic Ordering

If logic requires ordered processing, the SELECT query must have `ORDER BY` with a unique tie-breaker:

```sql
SELECT account_id
FROM accounts
WHERE needs_review = 1
ORDER BY priority DESC, account_id ASC;
```

Do not rely on physical row order or arbitrary index order. Even when ordering is not a business requirement, deterministic ordering makes testing and recovery predictable.

## 10. Cursor Example with Handlers and Cleanup

Suppose each account needs to run a dedicated stored procedure `sp_reconcile_one_account`. The child routine encapsulates isolated business logic. The following example illustrates cursor lifecycle and error handling; it is not a suggestion to replace a simple UPDATE JOIN with a cursor.

```sql
DELIMITER $$

CREATE PROCEDURE sp_process_reconciliation_batch(
    IN p_batch_limit INT
)
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_cursor_open BOOLEAN DEFAULT FALSE;
    DECLARE v_account_id BIGINT UNSIGNED;

    DECLARE cur_accounts CURSOR FOR
        SELECT account_id
        FROM accounts
        WHERE needs_reconciliation = 1
        ORDER BY account_id
        LIMIT p_batch_limit;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        IF v_cursor_open THEN
            CLOSE cur_accounts;
        END IF;
        RESIGNAL;
    END;

    IF p_batch_limit IS NULL OR p_batch_limit < 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'p_batch_limit must be greater than zero';
    END IF;

    OPEN cur_accounts;
    SET v_cursor_open = TRUE;

    read_loop: LOOP
        FETCH cur_accounts INTO v_account_id;

        IF v_done THEN
            LEAVE read_loop;
        END IF;

        CALL sp_reconcile_one_account(v_account_id);
    END LOOP;

    CLOSE cur_accounts;
    SET v_cursor_open = FALSE;
END$$

DELIMITER ;
```

Key points to understand:

- `v_done` catches the end-of-result-set signal.
- `v_cursor_open` lets the handler know the cursor is open so it closes on error.
- `EXIT HANDLER FOR SQLEXCEPTION` cleans up the cursor and calls `RESIGNAL` so the caller receives the original error.
- `LIMIT p_batch_limit` bounds the number of rows fed into the batch cursor.
- `ORDER BY account_id` provides deterministic ordering.
- Child routines need a clear contract for transactions and errors; they should not commit unilaterally if the caller owns the transaction.

### 10.1. Caller-Owned Transactions

The procedure above does not call `START TRANSACTION`, `COMMIT`, or `ROLLBACK`. The caller defines transaction boundaries:

```sql
START TRANSACTION;
CALL sp_process_reconciliation_batch(100);
COMMIT;
```

If `CALL` raises an error, the caller must `ROLLBACK` instead of COMMIT. Applications should use try/catch/finally to roll back when the procedure fails and return the connection to the pool in a clean state.

Do not arbitrarily add `START TRANSACTION` inside a called procedure when the caller's transaction is open. Starting a new transaction can end the active transaction with an implicit commit. Clearly designate a single transaction owner.

### 10.2. If Per-Batch Transactions Are Needed

The example procedure keeps the caller's transaction open across the entire batch. With high volume, you may need to commit after each batch to release locks. In that case, the application/job scheduler should orchestrate each batch using keysets or claim statuses and open a new transaction for each batch.

Never simply put `COMMIT` inside a loop without agreeing on the contract with the caller. Doing so can commit unrelated caller work on the same connection.

## 11. NOT FOUND and SELECT ... INTO Errors

`NOT FOUND` does not occur only when a cursor runs out of rows. It also occurs when a `SELECT ... INTO` returns no rows.

This is a common source of bugs:

```sql
DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_done = TRUE;
```

If the same block both FETCHes a cursor and executes `SELECT ... INTO`, a secondary query returning no result can set `v_done = TRUE`. The loop will terminate even though the cursor still has rows.

### 11.1. Safe Approach: Use a Nested Block with Its Own Handler

```sql
read_loop: LOOP
    FETCH cur_customers INTO v_customer_id;

    IF v_done THEN
        LEAVE read_loop;
    END IF;

    BEGIN
        DECLARE v_missing BOOLEAN DEFAULT FALSE;
        DECLARE v_customer_name VARCHAR(160);
        DECLARE CONTINUE HANDLER FOR NOT FOUND
            SET v_missing = TRUE;

        SELECT customer_name
          INTO v_customer_name
          FROM customers
         WHERE customer_id = v_customer_id;

        IF v_missing THEN
            -- Handle the case where no matching record exists.
            SET v_customer_name = NULL;
        END IF;
    END;

    -- Continue processing the current cursor row.
END LOOP;
```

The handler inside the child block handles only `NOT FOUND` from the secondary query. The outer block's cursor handler continues managing FETCH exhaustion.

### 11.2. Better Approach When Possible: Include the Data in the Cursor SELECT

If the cursor needs the customer name, JOIN directly inside the SELECT statement:

```sql
DECLARE cur_customers CURSOR FOR
    SELECT c.customer_id, c.customer_name
    FROM customers AS c
    WHERE c.account_status = 'REVIEW'
    ORDER BY c.customer_id;
```

Then FETCH both columns. This eliminates repeated per-row queries and avoids needing an extra handler.

## 12. Closing Cursors and Handling Exceptions

Cursors must be closed both during normal execution and when errors occur.

### 12.1. Normal Close

```sql
OPEN cur_customers;

read_loop: LOOP
    FETCH cur_customers INTO v_customer_id;
    IF v_done THEN
        LEAVE read_loop;
    END IF;

    -- Process current row.
END LOOP;

CLOSE cur_customers;
```

### 12.2. Closing on Error

If the routine can raise an SQL exception after opening a cursor, use an EXIT handler for cleanup:

```sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    IF v_cursor_open THEN
        CLOSE cur_customers;
    END IF;
    RESIGNAL;
END;
```

Set `v_cursor_open = TRUE` immediately after OPEN succeeds and reset it to FALSE after CLOSE. If OPEN fails, the handler does not attempt to close an unopened cursor.

### 12.3. RESIGNAL Preserves the Error for the Caller

`RESIGNAL` re-raises the condition currently handled by the handler. If a handler only logs and swallows the error, the caller may think the batch succeeded even though part of the work failed.

If error logging is needed, design the log table, transactions, and error rules explicitly. A log INSERT inside the same transaction rolls back with the business data; if logs must survive rollback, evaluate a dedicated logging mechanism and its replication impact.

## 13. Transactions, Locks, and Long-Running Cursors

A cursor does not automatically start its own transaction. It operates within the current session and transaction context.

Opening a transaction and iterating over thousands or millions of rows can prolong transactions and cause:

- Long-held locks if the routine runs UPDATE/DELETE.
- Growing undo history and delayed purge.
- Lock waits or deadlocks when other transactions touch the same data.
- Replica lag if the batch writes heavy changes.
- Increased temporary table resources from the cursor result set.

### 13.1. Deliberately Separate Reads and Writes

If a cursor only reads an ID list and calls a procedure to write each ID, determine whether data can change between opening the cursor and processing each row.

Cursors are asensitive; do not rely on changes to underlying rows updating the open cursor list. If status must be re-verified before writing, the child routine must check current conditions and handle cases where the row was modified or deleted.

### 13.2. Choose Isolation Level by Requirement

Do not raise the isolation level just to "make cursors safe." Determine whether you need a consistent snapshot, row locks to claim work, or simply checking eligibility at UPDATE time.

For multi-worker jobs, you can use a queue table with states `READY`, `PROCESSING`, `DONE`, lease/timeouts, and claim locking. Claiming must be atomic so two workers do not accidentally process the same row.

### 13.3. Prefer Short Batches

When business rules allow, process each batch in a short transaction, commit, and record a checkpoint. Holding a cursor open across a huge dataset is rarely a good way to implement long-running jobs.

## 14. Indexes and Execution Plans Still Matter for Set-Based SQL

Set-based SQL is not automatically fast if indexes are missing or predicates are non-sargable.

Example query:

```sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE customer_id = 1001
  AND status = 'PAID'
  AND created_at >= '2026-11-01 00:00:00'
  AND created_at <  '2026-12-01 00:00:00';
```

Potentially suitable index:

```sql
CREATE INDEX idx_orders_customer_status_created
ON orders (customer_id, status, created_at);
```

Column order depends on actual workload. Equality filter columns usually precede range columns, though selectivity, other queries, and write overhead must be evaluated.

### 14.1. Avoid Wrapping Filter Columns in Functions Unnecessarily

A predicate like:

```sql
WHERE DATE(created_at) = '2026-11-01'
```

can prevent range access on the `created_at` index. Use a half-open interval:

```sql
WHERE created_at >= '2026-11-01 00:00:00'
  AND created_at <  '2026-11-02 00:00:00'
```

### 14.2. Inspect EXPLAIN

```sql
EXPLAIN FORMAT=JSON
SELECT order_id, customer_id, total_amount
FROM orders
WHERE customer_id = 1001
  AND status = 'PAID'
  AND created_at >= '2026-11-01 00:00:00'
  AND created_at <  '2026-12-01 00:00:00';
```

Inspect selected indexes, row estimates, filtering, join order, and filesorts. For SELECT queries safe to run in an appropriate environment, use `EXPLAIN ANALYZE` to compare estimates with actual figures; note that this command actually executes the query.

### 14.3. Measure Both the Statement and the Workload

When comparing cursors vs. set-based SQL:

- Measure end-to-end time, not just SQL server time.
- Count round trips and statements.
- Measure rows read/written and rows changed.
- Check lock waits, deadlocks, and replication lag.
- Measure CPU, I/O, temporary tables, and memory usage.
- Use data distributions representative of production.

## 15. Patterns to Avoid

### 15.1. SELECT Followed by Row-by-Row UPDATE

Inefficient pattern:

```text
SELECT id, value FROM source_rows;
FOR EACH row:
    new_value = calculate(row.value)
    UPDATE target_rows SET value = new_value WHERE id = row.id;
```

If the calculation can be expressed in SQL, use UPDATE JOIN or CASE.

### 15.2. Cursor Just to Count or Sum

Do not iterate row by row just to increment counters or sum amounts. Use `COUNT(*)`, `SUM()`, `GROUP BY`, or window functions.

### 15.3. Cursor Just to Copy Rows

Do not FETCH and INSERT row by row when `INSERT INTO target (...) SELECT ... FROM source ...` works.

### 15.4. Cursor to Delete by Condition

Do not FETCH IDs and DELETE row by row when `DELETE ... WHERE` or `DELETE ... JOIN` works.

### 15.5. Loops Without Clear Termination Conditions

Every loop must have a provable termination condition. With cursors, check `v_done` right after FETCH before using fetched variables.

### 15.6. Swallowing Exceptions

An empty handler or one that merely sets a flag and continues can make a routine report success even though data was only partially processed. Continue only when skippable error types and recording rules are explicitly defined.

## 16. Decision Table: Set-Based SQL, Batch, or Cursor?

| Requirement | Preferred Choice | Reason |
|---|---|---|
| Update many rows with the same rule | `UPDATE ... WHERE` | One statement processes the entire set |
| Update using data from another table | `UPDATE ... JOIN` | Avoids row-by-row SELECT/UPDATE |
| Generate summary data | `INSERT ... SELECT` + `GROUP BY` | Database groups and writes directly |
| Delete based on relationships | `DELETE ... JOIN` | Eliminates ID looping |
| Compute rankings or running totals | Window functions | Ordered processing per partition |
| Dataset too large for one transaction | Set-based batching with checkpoints | Bounds locks and undo |
| Each row requires sequential logic depending on the prior row | Controlled cursor or loop | Genuine sequential state exists |
| Need to call external services for each row | Application/worker loop | Avoids holding DB cursors and transactions across network waits |
| Need concurrent multi-worker processing | Queue/batch claiming | Safe, recoverable work distribution |

## 17. Practice: Converting a Loop into Set-Based SQL

### 17.1. Problem

Every night, the system must set `review_required = 1` for customers who had at least three refunded orders in the last 90 days.

### 17.2. Loop-Based Approach

A suboptimal approach selects each customer, counts refunded orders in a separate query, and updates each customer one by one. This generates many round trips and repeated queries.

### 17.3. Set-Based Approach

```sql
UPDATE customers AS c
JOIN (
    SELECT customer_id
    FROM orders
    WHERE status = 'REFUNDED'
      AND refunded_at >= CURRENT_DATE - INTERVAL 90 DAY
    GROUP BY customer_id
    HAVING COUNT(*) >= 3
) AS r
  ON r.customer_id = c.customer_id
SET c.review_required = 1,
    c.updated_at = CURRENT_TIMESTAMP(6)
WHERE c.review_required = 0;
```

The subquery identifies eligible customers. UPDATE JOIN updates the entire matching set. If customers who are no longer eligible must have the flag cleared, define the reset rule clearly and write a separate statement or synchronize the entire set via LEFT JOIN.

### 17.4. Verify Before Running

```sql
SELECT
    customer_id,
    COUNT(*) AS refund_count
FROM orders
WHERE status = 'REFUNDED'
  AND refunded_at >= CURRENT_DATE - INTERVAL 90 DAY
GROUP BY customer_id
HAVING COUNT(*) >= 3;
```

Cross-check the list against business rules, verify indexes, and estimate affected customer count. After running UPDATE, record changed rows and execution time.

## 18. Pre-Cursor Checklist

- [ ] Tried expressing the problem with `UPDATE`, `INSERT ... SELECT`, or `DELETE`.
- [ ] Considered JOIN, aggregates, CTEs, `CASE`, and window functions.
- [ ] Identified why sequential row-by-row processing is necessary.
- [ ] Bounded the number of rows the cursor reads; avoided unbounded cursors on huge sets unless necessary.
- [ ] Cursor SELECT includes filters and deterministic `ORDER BY` when order matters.
- [ ] Declared variables/conditions, cursors, and handlers in exact order.
- [ ] Included a `NOT FOUND` handler and checked the flag right after FETCH.
- [ ] Checked whether `SELECT ... INTO` could trigger the same `NOT FOUND` handler.
- [ ] Included an EXIT handler to close the cursor on SQL exceptions.
- [ ] Included `RESIGNAL` when the caller must know the operation failed.
- [ ] Clearly defined transaction ownership between caller and procedure.
- [ ] Batches and checkpoints support safe retries.
- [ ] Checked indexes, execution plans, locks, and replication lag.
- [ ] Tested on production-like data and measured end-to-end.

## 19. Conclusion

Set-based SQL lets you describe operations across an entire row set so MySQL can optimize filtering, joins, aggregations, and writes. Before writing a loop, check whether `UPDATE ... JOIN`, `INSERT ... SELECT`, `DELETE ... JOIN`, `CASE`, CTEs, or window functions can express the business logic. If a single statement is too large, split it into set-based batches with short transactions and checkpoints.

Cursors should appear only when genuine sequential coordination is required. In MySQL, cursors are asensitive, read-only, and nonscrollable; their lifecycle consists of `DECLARE`, `OPEN`, `FETCH`, and `CLOSE`. `NOT FOUND` handlers must be properly scoped because they can also catch a `SELECT ... INTO` returning no rows. On exceptions, close the cursor and `RESIGNAL`, and clearly establish who owns the transaction. Use execution plans and workload metrics to validate your choice.

## References

- [MySQL 8.4 Reference Manual: Cursors](https://dev.mysql.com/doc/refman/8.4/en/cursors.html)
- [MySQL 8.4 Reference Manual: DECLARE Statement](https://dev.mysql.com/doc/refman/8.4/en/declare.html)
- [MySQL 8.4 Reference Manual: FETCH Statement](https://dev.mysql.com/doc/refman/8.4/en/fetch.html)
- [MySQL 8.4 Reference Manual: Condition Handling](https://dev.mysql.com/doc/refman/8.4/en/condition-handling.html)
- [MySQL 8.4 Reference Manual: UPDATE Statement](https://dev.mysql.com/doc/refman/8.4/en/update.html)
- [MySQL 8.4 Reference Manual: INSERT ... SELECT Statement](https://dev.mysql.com/doc/refman/8.4/en/insert-select.html)
- [MySQL 8.4 Reference Manual: EXPLAIN Statement](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
