# The `[applied]` Field and Current Values When Conditions Fail

> **Chapter:** LWT and Concurrency  
> **Scope:** Apache Cassandra, CQL, and Java applications using Cassandra Java Driver 4.x.

## 1. Why Read Both `[applied]` and the Current Values?

Cassandra is a distributed *wide-column* database. Data is distributed by **partition key** and replicated across nodes. With regular `INSERT` or `UPDATE`, Cassandra does not check by default whether the record already exists or whether its data still matches the state the application just read. When multiple actors modify the same row concurrently, one actor can overwrite another actor's decision.

**Lightweight Transactions (LWT)** provide conditional writes using *compare-and-set* (CAS) semantics and rely on Paxos to coordinate replicas. The typical forms are:

- `INSERT ... IF NOT EXISTS`: creates the row only if it does not yet exist.
- `UPDATE ... IF <condition>`: updates only when the specified columns satisfy the condition.
- `UPDATE ... IF EXISTS` or `DELETE ... IF EXISTS`: acts only when the row exists.

At the protocol/result layer, a completed LWT returns **one result row** containing a special column named `[applied]`:

| `[applied]` Value | Meaning | Handling Direction |
| --- | --- | --- |
| `true` | The CAS condition held and the operation was accepted to be applied. | Confirm success for the corresponding request. |
| `false` | The CAS condition failed; **the requested change was not applied**. | Read the returned conflict info; decide whether to return a business error, re-read, or retry carefully. |
| No result received due to timeout/disconnect | Uncertain whether the operation was applied or not. | Reconcile state and evaluate idempotency; never infer `false`. |

`[applied]` is a **column in the conditional statement's result**, not a column stored in the table schema. `[applied]=true` means the condition succeeded; it does not assert that the new value differs from the old value. Conversely, `[applied]=false` is a **normal condition conflict**, not a syntax error or connection error.

## 2. When It Fails, What Values Does Cassandra Return?

An easily overlooked detail is that the result row can also include the **existing values at the time of the CAS check**. Which columns are returned depends on how the condition is written:

| CQL Statement | When `[applied]=true` | When `[applied]=false` |
| --- | --- | --- |
| `INSERT ... IF NOT EXISTS` | Usually only `[applied]`. | Contains `[applied]` and **the columns of the existing row** at that primary key, including `null` values. |
| `UPDATE ... IF col_a = ... AND col_b = ...` | Usually only `[applied]`. | Contains `[applied]` and **the current values of the columns named in the `IF` clause** (`col_a`, `col_b`). |
| `UPDATE ... IF EXISTS` | Only `[applied]`. | Only `[applied]`; no row contents included. |
| `DELETE ... IF ...` | Conditional outcome per the `IF` clause. | Rely only on the columns returned by that specific condition form; do not assume the whole row is returned. |

Therefore, **never write application code assuming every failed LWT returns the entire record**. An `UPDATE ... IF version = ?` lets you inspect the current version on conflict, but it does not automatically return `quantity`, `status`, or other fields not mentioned in `IF`. An additional `SELECT` may be necessary to recompute business logic.

### Reading `null` Values vs. Absent Columns Properly

Two very different cases:

- **Column is present in the result with value `null`**: the result includes that column, but it currently has no value (or its value is no longer live)—for example, an existing row where `note` was never written.
- **Column is completely absent from the result metadata**: this LWT form does not return that column. You cannot conclude the column in the database is `null` just because the result omits it.

Before reading optional fields, the application must know the result schema for the statement it sent; you can inspect `Row.getColumnDefinitions()` when handling multiple statement forms.

## 3. CQL Practice: Creating Rows, Updating, and Detecting Conflicts

Assume you are using a **test keyspace** and an inventory table queried directly by `sku`, its partition key. The examples below assume the key `'BOOK-42'` does not exist before the first step.

```cql
CREATE TABLE IF NOT EXISTS stock_guard (
    sku text PRIMARY KEY,
    quantity int,
    version int,
    updated_by text
);
```

### Step A — Create the Row with `IF NOT EXISTS`

```cql
INSERT INTO stock_guard (sku, quantity, version, updated_by)
VALUES ('BOOK-42', 10, 1, 'seed')
IF NOT EXISTS;
```

When the row does not exist, an illustrative `cqlsh` output is:

```text
 [applied]
-----------
      True
```

Send another insert for the same primary key with different contents:

```cql
INSERT INTO stock_guard (sku, quantity, version, updated_by)
VALUES ('BOOK-42', 99, 1, 'worker-B')
IF NOT EXISTS;
```

Expected result, shown concisely:

```text
 [applied] | sku     | quantity | version | updated_by
-----------+---------+----------+---------+-----------
     False | BOOK-42 |       10 |       1 | seed
```

The second statement is rejected; **`quantity` remains 10**, not 99. The columns after `[applied]` are the data from the **existing** row, not the `99` and `worker-B` values the second actor attempted to write. This information is useful for detecting conflicts when claiming unique names, creating keyed resources, or preventing duplicate creation.

### Step B — Writing Against an Observed Version

One actor read `quantity=10` and `version=1`, then decided to decrement stock to 7. It executes:

```cql
UPDATE stock_guard
SET quantity = 7,
    version = 2,
    updated_by = 'worker-A'
WHERE sku = 'BOOK-42'
IF quantity = 10 AND version = 1;
```

Result:

```text
 [applied]
-----------
      True
```

Both conditions held at CAS time, so the update succeeded. Another actor, still believing inventory is 10 at version 1, executes next:

```cql
UPDATE stock_guard
SET quantity = 9,
    version = 2,
    updated_by = 'worker-B'
WHERE sku = 'BOOK-42'
IF quantity = 10 AND version = 1;
```

The failed result looks like (column display order may vary):

```text
 [applied] | quantity | version
-----------+----------+--------
     False |        7 |       2
```

Values `7` and `2` show the state that caused actor B's condition to fail. **`updated_by` does not have to be returned**, because that column does not appear in `IF`. The actual stored data remains from A's update.

This is the key insight: the client can immediately inspect the **current stored values under comparison** without guessing why CAS failed. However, those values reflect only the moment the condition was evaluated; an actor C may update the data again before B decides its next step.

### Step C — `IF EXISTS` Does Not Reveal Row Contents

```cql
UPDATE stock_guard
SET updated_by = 'worker-C'
WHERE sku = 'NOT-FOUND'
IF EXISTS;
```

```text
 [applied]
-----------
     False
```

The statement fails because the row does not exist. The result does not include `quantity`, `version`, or `updated_by`; the application must not try to read those fields from `Row`. If you actually need the data state for the next decision, issue an appropriate query.

## 4. Reading Conflicts in a Write Race

Suppose two services A and B both read the state `(quantity=10, version=1)`.

| Step | Actor | Action | Response |
| --- | --- | --- | --- |
| 1 | A | CAS from `(10, 1)` to `(7, 2)`. | `[applied]=true`. |
| 2 | B | CAS from `(10, 1)` to `(9, 2)`. | `[applied]=false`; `quantity=7`, `version=2`. |
| 3 | B | Re-evaluate its inventory deduction against the newly learned state. | May issue a new CAS against version 2 if stock and business rules permit. |

If B still needs to decrement stock by 1, it must recompute from state `7` to propose `6` conditioned on `IF quantity=7 AND version=2`. If another actor already moved the row to version 3 before B sends that statement, the next CAS returns `false` again; that is how the guard prevents updates based on stale data.

**Do not turn a CAS loop into infinite retries.** A sound strategy bounds the number of attempts, applies backoff under high contention, re-evaluates business rules on each iteration, and returns a clear conflict status once attempts are exhausted.

## 5. Reading `[applied]` and Current Columns in Java Driver 4.x

Cassandra Java Driver 4.x provides `ResultSet.wasApplied()` to read the CAS outcome. This method **does not consume the result row**; you can call `result.one()` afterward to read the columns on conflict.

The example below assumes a `CqlSession` is already configured to connect to the keyspace containing `stock_guard`. `expectedQuantity` and `expectedVersion` must come from a prior read or previous CAS round; for instance, passing `(10, 1)` corresponds to Step B.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public final class StockCasExample {
    public static void tryUpdate(
            CqlSession session,
            String sku,
            int expectedQuantity,
            int expectedVersion,
            int newQuantity) {

        PreparedStatement prepared = session.prepare(
            "UPDATE stock_guard " +
            "SET quantity = ?, version = ?, updated_by = ? " +
            "WHERE sku = ? IF quantity = ? AND version = ?"
        );

        BoundStatement statement = prepared.bind(
                newQuantity,
                expectedVersion + 1,
                "java-service",
                sku,
                expectedQuantity,
                expectedVersion)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL);

        ResultSet result = session.execute(statement);

        if (result.wasApplied()) {
            System.out.println("CAS succeeded");
            return;
        }

        // Because IF checks quantity and version, both columns
        // appear in the result row when the condition fails.
        Row current = result.one();
        if (current == null) {
            throw new IllegalStateException("Missing LWT result row");
        }

        Integer actualQuantity = current.isNull("quantity")
                ? null : current.getInt("quantity");
        Integer actualVersion = current.isNull("version")
                ? null : current.getInt("version");

        System.out.printf(
            "CAS conflict: quantity=%s, version=%s%n",
            actualQuantity, actualVersion
        );

        // Here: revalidate business rules before deciding whether
        // to report conflict, issue an extra SELECT, or attempt a new CAS.
    }
}
```

**Explanation of common pitfalls in code:**

1. `wasApplied()` reflects condition status only when the statement is an LWT. For regular statements, the API may return `true` by convention; never use it to infer that a regular write created or modified a row.
2. `result.one()` returns the LWT result row. Check `[applied]` first because on success, `quantity` and `version` are not part of the result.
3. `isNull(...)` checks for `null` on columns **guaranteed to exist in this result**. If writing a shared handler for `IF NOT EXISTS`, `IF EXISTS`, and `IF col=...`, check column metadata before reading.
4. `LOCAL_QUORUM` is the regular write consistency level, whereas `LOCAL_SERIAL` governs the LWT condition phase within one datacenter. Choose `SERIAL` or `LOCAL_SERIAL` and the regular write level to match your topology and consistency requirements; they are distinct settings.

If using low-level row APIs, the returned field name is **`[applied]` (with square brackets)**; using `wasApplied()` avoids mistaking it for `applied`.

## 6. Decisions After Receiving `[applied]=false`

Depending on the domain, a CAS failure should not always be retried:

- **Creating a unique record:** a failed `INSERT ... IF NOT EXISTS` can be mapped to `409 Conflict`, using the key or existing row details to explain the conflict. Never overwrite the existing data merely because the new request differs from it.
- **Optimistic locking:** a failed `UPDATE ... IF version=?` means the expected version is no longer current. Return the actual version, re-query if more fields are needed, and ask the caller to resolve the discrepancy or recompute.
- **Decrementing stock or transitioning state:** re-check all invariants, such as non-negative inventory or valid state transitions; issue a new CAS only if current state permits.
- **Failed `IF EXISTS`:** understand that the row does not exist for that check; the result will not include substitute row data.

Also distinguish three cases in the application:

| Scenario | Considered a Successful Write? | Should You Immediately Retry the Exact Same Statement? |
| --- | --- | --- |
| Received `[applied]=true` | Yes, for the CAS just executed. | No need. |
| Received `[applied]=false` | No; condition did not hold. | Never blindly; re-evaluate state and business rules. |
| Received timeout/communication error before result | **Indeterminate.** | Reconcile first, especially for operations with business side effects or non-idempotent steps. |

Because LWT relies on Paxos, each conditional operation requires extra round trips among replicas and typically has higher latency/cost than regular writes. Reserve LWT for places that genuinely need concurrency conditions, and design partition keys around queries to bound coordination scope. LWT is not an RDBMS-style multi-table/multi-partition transaction.

## 7. Common Misconceptions

**"`false` means Cassandra errored."** False. It is a deterministic result stating the condition was not satisfied and the update was rejected.

**"When `false`, all returned columns are the values I wanted to write."** False. For `INSERT IF NOT EXISTS`, they are the existing row's data; for `UPDATE ... IF`, they are the current values of the compared columns.

**"When `false`, the entire row is always returned to reuse."** False. `UPDATE ... IF version=?` mainly returns `version`; `UPDATE ... IF EXISTS` typically returns only `[applied]`.

**"The returned values stay the latest until my next write."** False. They reflect the state observed when CAS evaluated the condition. Other actors may have created newer versions immediately afterward.

**"A timeout is the same as `[applied]=false`."** False. Timeouts or dropped connections leave the CAS outcome indeterminate; reconcile or use a safe retry strategy.

## 8. Hands-On Verification

On an isolated test table, do the following in order:

1. Create `stock_guard` and insert a new SKU using `IF NOT EXISTS` twice. Compare the number of returned columns between the successful attempt and the rejected attempt.
2. Run an `UPDATE` with matching `IF quantity = ... AND version = ...`; then rerun the stale condition after the version increments. Identify the current columns returned on the failure.
3. Try an `UPDATE ... IF EXISTS` for a non-existent SKU; verify that the result includes no row data.
4. In Java, print `wasApplied()` and then read the `Row` on conflict. Try issuing a follow-up `SELECT` to compare, keeping in mind that the `SELECT` may observe an even newer state under concurrency.

**Remember:** check `[applied]` first, read **only the columns that the condition form returns** on failure, and treat those values as input for a fresh concurrency decision—not permission to overwrite current state.

## References

- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/dml.html): `INSERT IF NOT EXISTS`, `UPDATE IF` syntax, and cost of conditions.
- [DataStax — Lightweight Transactions, specialized results](https://docs.datastax.com/en/drivers/python/3.1/lwt.html): shape of `[applied]` and returned columns for each condition type.
- [Apache Cassandra Java Driver 4.19 — ResultSet](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/cql/ResultSet.html): contract of `wasApplied()`.
