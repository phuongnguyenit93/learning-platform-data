# Transaction Certification Conflicts and Application-Level Handling

In MySQL Group Replication, a transaction can run successfully on the receiving node and still be aborted at `COMMIT` time. This happens when certification detects that a previously certified transaction modified data conflicting with the current transaction. Applications must recognize this scenario and retry the entire transaction under a bounded policy.

This lesson belongs to the **DATABASE_MYSQL** module and focuses on operating highly available MySQL systems: understanding write sets and certification, distinguishing certification conflicts from deadlocks, designing safe retries, protecting business correctness, and monitoring errors in single-primary or multi-primary deployments.

## 1. Certification in Group Replication

Group Replication enables multiple members in a group to maintain consistent data. Each member can execute transactions locally; before a transaction is accepted into the shared history, the group must check for potential conflicts against already-certified transactions.

High-level flow:

1. The application opens a transaction on a member and executes read/write statements.
2. MySQL collects the write set—the set of row keys associated with the transaction's modifications.
3. At commit time, the write set enters the group's global order and is checked against previously certified write sets within the required window.
4. If no conflict exists, the transaction is certified and can complete its commit.
5. If a conflict exists, the transaction is aborted. The application receives an error on commit and must decide whether to retry or return an error to the caller.

Certification detects write conflicts across transactions. It ensures members apply the same transaction order and prevents two conflicting transactions from both committing on different members.

### How are write sets formed?

A write set describes modified rows using row-identifying keys. A primary key is best because it is unique and stable. MySQL can also use suitable unique keys. When a table lacks a suitable unique key, conflict detection and certification effectiveness suffer; Group Replication schemas should define a primary key on every table.

Example:

~~~sql
CREATE TABLE inventory (
  sku VARCHAR(40) PRIMARY KEY,
  quantity INT NOT NULL,
  updated_at TIMESTAMP NOT NULL
) ENGINE=InnoDB;
~~~

If a transaction updates the row with `sku = 'SKU-100'`, that key becomes central to identifying the write set. Two transactions modifying row `SKU-100` can conflict during certification.

Certification primarily detects conflicts on keys within write sets. It does not replace designing data constraints, foreign keys, unique constraints, or logic protecting complex business invariants. For instance, two transactions might read the same aggregate while writing to different rows; if a business rule depends on that aggregate, the application must still enforce appropriate transaction isolation and constraints.

## 2. Example of two conflicting transactions

Suppose a system runs Group Replication in multi-primary mode and two applications place orders for the same SKU. Both connect to different members and read a remaining quantity of 1.

~~~sql
-- Transaction T1 on member A
START TRANSACTION;
SELECT quantity FROM inventory WHERE sku = 'SKU-100';
UPDATE inventory
SET quantity = quantity - 1
WHERE sku = 'SKU-100';

-- Transaction T2 on member B
START TRANSACTION;
SELECT quantity FROM inventory WHERE sku = 'SKU-100';
UPDATE inventory
SET quantity = quantity - 1
WHERE sku = 'SKU-100';
~~~

Both transactions modify the same key `SKU-100`. At commit time, the transaction certified first completes; the other is rejected due to a write-set conflict. The losing transaction rolls back and must not be treated as a successful order.

The application must retry the entire transaction from the beginning. Upon re-reading the quantity after the first transaction, the application sees stock is depleted and returns out-of-stock. Re-issuing only `COMMIT` or resuming from the last statement would rely on stale read data and produce incorrect business results.

### Writing safer update statements

Instead of reading and then subtracting quantity in the application, embed the business guard directly in the update statement:

~~~sql
UPDATE inventory
SET quantity = quantity - 1,
    updated_at = CURRENT_TIMESTAMP
WHERE sku = 'SKU-100'
  AND quantity > 0;
~~~

The application checks the affected row count:

- `1`: the operation reserved one unit of stock.
- `0`: the SKU does not exist or quantity is insufficient; the application distinguishes the two cases if business logic requires.

A conditional update prevents inventory from going negative. However, in multi-primary mode, two transactions editing the same SKU can still hit a certification conflict. When that error occurs, the application must restart the transaction and re-evaluate the condition against the latest state.

## 3. How do single-primary and multi-primary affect conflicts?

Group Replication offers two write topologies:

| Mode | Where writes go | Conflict profile |
|---|---|---|
| Single-primary | One member acts as primary accepting writes at a time | Eliminates multi-member write conflicts, though deadlocks and ordinary transaction errors still occur |
| Multi-primary | Multiple members can accept writes | Transactions updating the same keys on different members can contend during certification |

In single-primary mode, write transactions funnel to one node. InnoDB handles local contention via locking and deadlock detection; certification still runs as part of group consensus. When the primary changes, applications must reroute connections and handle interrupted transactions.

In multi-primary mode, writing across multiple members adds flexibility while raising the chance that two transactions modify the same data concurrently. Tables with frequent writes to the same key—such as counters, balances, or popular SKU stock—easily become hotspots.

Choose your mode based on actual write patterns. If most transactions touch shared rows or interrelated business rules, single-primary is much easier to operate. If using multi-primary, partition workloads or route writes to minimize multiple members hitting the same keys.

## 4. Detecting certification errors in applications

A classic symptom is that all statements in a transaction succeed until an error surfaces at `COMMIT`. In Group Replication, the common error is:

- **3101 — ER_TRANSACTION_ROLLBACK_DURING_COMMIT:** the transaction rolled back during commit due to a conflict with a concurrent transaction; the error message typically instructs retrying.

Illustrative example:

~~~sql
START TRANSACTION;
UPDATE inventory
SET quantity = quantity - 1
WHERE sku = 'SKU-100';

COMMIT;
-- May return error 3101 if certification detects a conflict
~~~

Not every error at `COMMIT` is a certification conflict. Applications must classify errors by error code and connection state, not merely by where the error occurred.

### Distinguishing common errors

| Error | Common cause | Action |
|---|---|---|
| 3101 | Transaction rejected during certification | Retry the entire transaction |
| 1213 | InnoDB detected a deadlock and chose this transaction as victim | Retry the entire transaction if the operation remains valid |
| 1205 | Lock wait timeout expired | Roll back the transaction per application policy, then consider retrying |
| 1062 | Unique constraint violation | Handle per business rules; usually do not blindly retry |
| Disconnect during commit | Uncertain whether the server committed or not | Verify outcome via idempotency key or business state before resubmitting |

For error 1205, depending on `innodb_rollback_on_timeout`, MySQL may roll back only the timed-out statement rather than the entire transaction. Thus the application's transaction layer should explicitly roll back the full transaction before retrying to ensure a clean state.

Disconnecting during `COMMIT` is especially sensitive: the server may have committed even though the response never reached the client. To the application, this is an unknown outcome. Do not lump it into automatic retries like an ordinary certification conflict.

## 5. Retries must restart the entire transaction

When a certification error occurs, the current transaction has already been aborted. A proper retry means:

1. End and release the current transaction state.
2. Start a brand-new transaction.
3. Re-read required data.
4. Re-validate business conditions.
5. Re-execute all write operations.
6. Commit and return success only once commit is confirmed.

Never retry only the last statement. Never reuse data read inside an aborted transaction, because the group's data may already have changed.

### Pseudocode

~~~text
for attempt from 1 to MAX_ATTEMPTS:
    begin a new transaction
    try:
        read current business state
        validate business rules
        execute all writes
        commit
        return success
    catch a known retryable transaction error:
        rollback and release transaction state
        if attempt reached MAX_ATTEMPTS:
            return a retryable failure to caller
        wait with bounded exponential backoff and jitter
        continue with a new transaction
    catch any other error:
        rollback if needed
        return or raise the error
~~~

Condensed Java JDBC example:

~~~java
int maxAttempts = 4;

for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        try {
            reserveInventory(connection, sku, quantity);
            createOrder(connection, requestId, sku, quantity);
            connection.commit();
            return;
        } catch (SQLException error) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                error.addSuppressed(rollbackError);
            }

            int code = error.getErrorCode();
            boolean retryable =
                code == 3101 || // Group Replication certification
                code == 1213 || // InnoDB deadlock
                code == 1205;   // Lock wait timeout

            if (!retryable || attempt == maxAttempts) {
                throw error;
            }
        }
    }

    // Wait an increasing interval with jitter before the next attempt.
    backoffWithJitter(attempt);
}
~~~

This is an illustrative skeleton; `reserveInventory`, `createOrder`, and `backoffWithJitter` are application methods. In production code, keep connection hold times short, unwrap exception chains if drivers wrap errors, and ensure broken connections are evicted from the pool when their state is unreliable.

## 6. Designing a bounded retry policy

Retries help absorb transient conflicts, yet excessive retrying adds load and worsens hotspots. Policies need explicit bounds.

### Attempt limits

Set a small maximum attempt count, such as 3–5 attempts depending on SLA and transaction duration. Once exhausted, return a clean failure to the caller or enqueue the request for asynchronous retry. Never loop indefinitely inside a synchronous request.

### Exponential backoff and jitter

Increasing wait intervals reduces the odds of conflicting requests retrying in lockstep:

**delay = min(maxDelay, baseDelay × 2^(attempt - 1)) + randomJitter**

For instance, with a 20 ms base delay and 250 ms max delay, wait intervals grow across attempts without exceeding the cap. Random jitter spreads out retries across clients.

Pick values aligned with latency budgets. Short transactions on high-load systems need millisecond waits; background workers can tolerate longer pauses.

### Retry only recoverable errors

Restrict automatic retries to transient errors such as certification conflict `3101`, deadlock `1213`, and lock wait timeout `1205` after a full transaction rollback. Data errors like type mismatches, constraint violations, missing privileges, or schema incompatibilities must be addressed at their root cause.

Emit metrics for retry counts, error codes, exhausted failures, and wait durations. A sudden spike in retries signals hotspots, overly long transactions, or poor write routing.

## 7. Idempotency and external side effects

Retries can cause the same business request to be executed multiple times. Operations like creating an order, charging a payment, or calling external services must be idempotent so they do not produce duplicate side effects.

### Using an idempotency key

Each business request carries a unique key generated by the client or orchestrator. Store that key alongside the outcome inside the same transaction:

~~~sql
CREATE TABLE processed_requests (
  request_id VARCHAR(64) PRIMARY KEY,
  result_code VARCHAR(32) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
~~~

When handling a request, check or insert `request_id` in the same transaction as the business changes. If the request was already completed, return the stored result instead of creating another order or deducting inventory again. The unique key on `request_id` protects against duplicate concurrent arrivals.

Checking and recording the idempotency key must happen inside the exact same transaction as the business data. Recording the key after committing the order risks leaving a gap where a retry cannot tell if the operation succeeded.

### Avoid external service calls inside retryable transactions

Avoid sending emails, calling payment gateways, or publishing messages directly inside a transaction that may roll back and retry. External side effects do not automatically undo when a database transaction rolls back.

A reliable pattern is the transactional outbox:

1. Within the same transaction, write the business changes and an event record into an `outbox` table.
2. Commit the transaction.
3. A separate worker reads the outbox and dispatches messages or calls external services.
4. The worker marks the event processed using an idempotent identifier.

This allows the database transaction to retry freely without firing duplicate emails or payment requests during aborted attempts.

## 8. Designing transactions to reduce conflicts

Applications can lower certification conflict rates by shrinking overlapping write footprints and shortening transaction lifetimes:

- Keep transactions short; never make HTTP calls, wait on user input, or process files while a transaction is open.
- Update related rows in a consistent key order whenever possible to reduce deadlocks.
- Define explicit primary keys and unique keys on replicated tables.
- Avoid updating a single global counter row from multiple members.
- Partition data by tenant, account, or business domain so the same key normally hits one writer.
- Consider single-primary if workloads frequently write to shared data.
- Use conditional updates and database constraints to protect business invariants.

### Handling hotspots

Suppose a table tracks total request counts:

~~~sql
UPDATE global_counter
SET counter_value = counter_value + 1
WHERE counter_name = 'all_requests';
~~~

If multiple multi-primary members update that single row concurrently, write sets constantly collide. Reduce contention by sharding the counter by member or bucket and aggregating on read:

~~~sql
CREATE TABLE request_counter (
  bucket_id INT PRIMARY KEY,
  counter_value BIGINT NOT NULL
) ENGINE=InnoDB;
~~~

The application picks a bucket deterministically—such as a hash of tenant ID or workload partition. This works only when business logic accepts reading an aggregated sum across buckets rather than requiring a single atomic counter row.

## 9. Observing and measuring conflicts

Do not rely solely on retry counts in application logs. Combine application metrics, Group Replication status, and server logs to pinpoint conflict sources.

### At the application layer

Track:

- Total committed and failed transactions.
- Retry counts broken down by error codes `3101`, `1213`, and `1205`.
- Percentage of requests requiring retries and average attempt count.
- End-to-end time from first attempt to successful commit.
- Tables, operation types, and business domains involved (without logging sensitive data).
- Requests exceeding maximum retry limits.

### At the MySQL layer

Check group status:

~~~sql
SELECT
  MEMBER_ID,
  MEMBER_HOST,
  MEMBER_PORT,
  MEMBER_STATE,
  MEMBER_ROLE
FROM performance_schema.replication_group_members;
~~~

Check member statistics:

~~~sql
SELECT *
FROM performance_schema.replication_group_member_stats;
~~~

Available Performance Schema tables and columns vary across releases. Use `DESCRIBE performance_schema.replication_group_member_stats` to inspect the structure on your specific server. Also monitor applier queues, rejected transactions, and member states; exact metric column names depend on version.

When conflict rates rise, inspect whether transactions hit the same keys or tables. A small set of recurring keys points to a hotspot. If conflicts climb alongside long transactions, review statement counts, lock hold durations, and non-database work happening inside transactions.

## 10. Testing retries before deployment

Build controlled tests verifying that the application truly retries entire transactions:

1. Stand up a Group Replication test group with at least two writable members if testing multi-primary.
2. Create a table with a primary key and a row updated by concurrent transactions.
3. From two clients, start nearly simultaneous transactions updating the same key.
4. Commit on both members; observe the winning transaction and the certification error on the losing one.
5. Verify the application opens a fresh transaction, re-reads data, and re-evaluates business logic.
6. Resend the same request ID to verify idempotency.
7. Trigger a deadlock or lock wait timeout to verify error classification.
8. Simulate a disconnect during `COMMIT` and confirm the application does not blindly retry an unknown outcome.

Never run conflict-inducing stress tests on production. In the test environment, capture error codes, commit times, retry counts, and final data state for verification.

## 11. Certification conflict handling checklist

**On receiving an error**

- [ ] Error code logged and checked whether it is `3101`.
- [ ] Confirmed transaction was aborted and stale read values are discarded.
- [ ] Transaction/connection state rolled back or cleaned up.
- [ ] Certification errors distinguished from deadlocks, lock timeouts, and commit-time disconnects.

**On retrying**

- [ ] Entire transaction retried from the start.
- [ ] Bounded attempt limit and exponential backoff with jitter applied.
- [ ] Business conditions re-checked inside the new transaction.
- [ ] Requests protected by idempotency keys.
- [ ] No external side effects fired before commit.

**When conflict rates rise**

- [ ] Frequently conflicting tables and keys identified.
- [ ] Long transactions and hotspots audited.
- [ ] Write routing and single-primary/multi-primary selection reviewed.
- [ ] Primary keys and unique constraints verified on replicated tables.
- [ ] Retry rate, latency, and final failure rate measured.

## Conclusion

Certification conflicts are an integral part of Group Replication's transaction ordering guarantees. Errors may surface only at commit time even when earlier statements succeeded on the receiving member. Applications must detect error `3101`, roll back the current state, and retry the entire transaction against fresh data with bounded attempts and jittered backoff. Idempotency keys and the transactional outbox protect business side effects. When conflicts happen frequently, address the root causes—hotspots, transaction duration, and write routing—rather than simply bumping retry counts.
