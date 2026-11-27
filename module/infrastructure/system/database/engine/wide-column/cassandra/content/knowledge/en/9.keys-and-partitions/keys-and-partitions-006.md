# Uniqueness Within Primary Key Scope

In Apache Cassandra, **`PRIMARY KEY` is the unique identifier of a logical row in a table**. If two write operations share the *entire* primary key value, they operate on the same row; Cassandra does not create two rows merely because `INSERT` was called twice. Conversely, if even one component of the primary key differs, they are two distinct logical rows, even if they carry the same `event_id`, email, or transaction code in another column.

Distinguishing this uniqueness scope is critical when designing Cassandra tables around queries. In the distributed wide-column model, the **partition key** selects the partition and replica set, while **clustering columns** distinguish rows within the partition. Cassandra does not natively provide arbitrary `UNIQUE` constraints like some relational DBMSs: a business attribute is only unique if key selection and write workflows genuinely enforce it.

This lesson focuses on understanding row identity, handling duplicate writes, concurrent writes, and controlling uniqueness via CQL as well as Java applications. These concepts form the foundation for table design, read/write consistency levels, replication, and error handling in distributed Cassandra systems.

After this lesson, you will be able to:

- Identify the set of columns forming the **complete identifier of a row**.
- Distinguish uniqueness of the **primary key**, the **clustering key within a partition**, and a **system-wide business identifier**.
- Explain why a normal Cassandra `INSERT` has **upsert** semantics.
- Recognize when `INSERT ... IF NOT EXISTS` is needed and the cost of a **lightweight transaction (LWT)**.
- Design *retryable* write operations without accidentally creating duplicate events.
- Implement a Java Driver example that inspects conditional write outcomes.

## 1. What does "unique" mean in Cassandra?

Consider a table storing events for each account by day:

```sql
CREATE TABLE events_by_account_day (
    account_id   uuid,
    event_day    date,
    occurred_at  timestamp,
    event_id     uuid,
    event_type   text,
    amount       decimal,
    PRIMARY KEY (
        (account_id, event_day),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
);
```

In this table:

| Component | Column(s) | Meaning |
| --- | --- | --- |
| Composite partition key | `(account_id, event_day)` | Each account has its own partition per day. |
| Clustering column 1 | `occurred_at` | Distinguishes/orders by event timestamp. |
| Clustering column 2 | `event_id` | Distinguishes two events sharing the same `occurred_at`. |
| Full primary key | `(account_id, event_day, occurred_at, event_id)` | **Identifies a unique logical row** in the table. |
| Regular columns | `event_type`, `amount` | Event payload; does not participate in row identity. |

Cassandra will not create two rows with the same full primary key tuple in a table. A row can be updated many times, yet it remains the **same logical coordinate**.

```text
Partition key: (account A, 2026-11-21)
│
├── Clustering key (08:00:00, event-1) → logical row X
├── Clustering key (08:00:00, event-2) → logical row Y
└── Clustering key (08:01:00, event-1) → logical row Z

X ≠ Y: different event_id
X ≠ Z: different occurred_at
Y ≠ Z: different occurred_at and event_id
```

Within a partition, the clustering column tuple uniquely identifies a row. However, a given `event_id` can still appear at **multiple timestamps or across multiple partitions** because it is not the entire primary key by itself.

> **Core rule:** Cassandra guarantees each **primary key combination** has at most one current logical row in a table. This does **not** imply every column inside the primary key has globally unique values when considered individually.

## 2. Uniqueness scope of each key declaration

CQL's parentheses syntax determines the exact scope of uniqueness.

```sql
-- Example A: only user_id is the primary key and partition key.
PRIMARY KEY (user_id)

-- Example B: user_id is the partition key; event_id is a clustering column.
PRIMARY KEY (user_id, event_id)

-- Example C: composite partition key (tenant_id, user_id).
PRIMARY KEY ((tenant_id, user_id))

-- Example D: composite partition key with clustering columns.
PRIMARY KEY ((tenant_id, user_id), event_day, event_id)
```

| Declaration | When do two records share a primary key? | What is **not** guaranteed |
| --- | --- | --- |
| A | Same `user_id` | Does not forbid duplicate emails across two different `user_id`s. |
| B | Same `user_id` **and** `event_id` | Does not forbid `event_id` from appearing under two different users. |
| C | Same `tenant_id` **and** `user_id` | Does not forbid `user_id` from appearing in another tenant. |
| D | Same `tenant_id`, `user_id`, `event_day`, **and** `event_id` | Does not forbid the same `event_id` on another day or another user. |

One easy mistake:

```sql
PRIMARY KEY (tenant_id, user_id, event_id)
```

Here only `tenant_id` is the partition key; `user_id` and `event_id` are clustering columns. **Row uniqueness** still depends on all three columns. The difference compared to `PRIMARY KEY ((tenant_id, user_id), event_id)` lies in how partitions are divided and which queries are supported.

### Case with no clustering column

```sql
CREATE TABLE customer_by_id (
    customer_id uuid PRIMARY KEY,
    email text,
    display_name text
);
```

One `customer_id` designates one row. Writing again with that `customer_id` operates on the existing row rather than creating a second row.

### Case with clustering columns

```sql
CREATE TABLE messages_by_conversation (
    conversation_id uuid,
    sent_at timestamp,
    message_id uuid,
    sender_id uuid,
    body text,
    PRIMARY KEY (conversation_id, sent_at, message_id)
);
```

A conversation has multiple message rows thanks to clustering columns. Two messages with the same `sent_at` are still two rows if `message_id` differs. However, if they share `message_id` yet differ in `sent_at`, they are still treated as **two rows**. To use `message_id` as a system-wide unique identifier, merely making it one clustering key component is **not enough**.

## 3. Creating two rows or updating the same row?

Using `events_by_account_day`, suppose an event occurs at 09:00:00 UTC:

```sql
INSERT INTO events_by_account_day (
    account_id, event_day, occurred_at, event_id, event_type, amount
) VALUES (
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T09:00:00Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'purchase',
    120.00
);
```

Now write again with the **same primary key tuple**, changing `amount`:

```sql
INSERT INTO events_by_account_day (
    account_id, event_day, occurred_at, event_id, event_type, amount
) VALUES (
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T09:00:00Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'purchase',
    125.00
);
```

This is an **upsert**: if the row does not exist yet, Cassandra creates it; if it already exists, it writes the specified column values to the same logical row. In a sequential, conflict-free scenario where the second write has a higher write timestamp, `amount` read back will be `125.00`.

Query identifying the row by the full primary key:

```sql
SELECT event_type, amount
FROM events_by_account_day
WHERE account_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T09:00:00Z'
  AND event_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

The result contains **at most one logical row** corresponding to this tuple.

If you change `event_id` to another UUID, Cassandra can create an additional row in the **same partition**. If you change `event_day`, that goes to a **different partition**. If you change `occurred_at`, that is a different row even when `event_id` stays unchanged.

### `INSERT` does not mean "insert only if absent"

Unlike scenarios using unique constraints in relational SQL, a standard Cassandra `INSERT` statement **does not automatically fail on primary key collision**. It performs a write/upsert.

```sql
-- If the row already exists, amount can still be updated:
UPDATE events_by_account_day
SET amount = 130.00
WHERE account_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T09:00:00Z'
  AND event_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

A standard `UPDATE` in Cassandra can also write data for a key that does not exist yet (upsert). Therefore, you cannot infer from the statement keyword `INSERT` or `UPDATE` alone that the system checked existence before writing.

## 4. Duplicate writes and per-column updates: key aspects of upsert

Data in Cassandra carries write timestamps at the cell level. Two writes with the same primary key do not necessarily form a "replace the whole record" operation in the Java object sense.

For example, after a row already exists, we write only `amount`:

```sql
INSERT INTO events_by_account_day (
    account_id, event_day, occurred_at, event_id, amount
) VALUES (
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T09:00:00Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    140.00
);
```

The `event_type` field is **not mentioned** in this statement. The old value of `event_type` is not deleted just because the statement omitted that column. This differs from passing `null` for a column, which can create a tombstone under CQL semantics.

If two clients concurrently write to a cell and replicas receive commands in different orders, Cassandra resolves versions using write timestamps and timestamp tie-breaking rules. Consequently:

- "Whichever command finished later according to the application clock" is not guaranteed to be the "winner" in every case.
- Different columns in the same row can have **different write timestamps**.
- Writing the same primary key with different data across multiple requests does not automatically produce an atomic whole-object replacement.
- When retrying after a timeout, the previous command's effect may **already have been applied**, even though the client did not receive acknowledgment.

For an event log, a safer behavior is to associate each business event with **one stable identifier** and write only one consistent payload for that identifier. If rejecting writes when the key already exists is required, conditional writes must be used.

## 5. When is `INSERT ... IF NOT EXISTS` needed?

Cassandra supports **lightweight transactions (LWT)** through conditional statements, such as `IF NOT EXISTS`. The condition is evaluated via the Paxos consensus protocol, ensuring two clients competing for the **same primary key** cannot both succeed in newly creating that row.

```sql
INSERT INTO events_by_account_day (
    account_id, event_day, occurred_at, event_id, event_type, amount
) VALUES (
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T09:00:00Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'purchase',
    120.00
)
IF NOT EXISTS;
```

When the row does not yet exist, the condition can be applied successfully; when the row already exists, Cassandra does not overwrite that row's data under the conditional `INSERT` and returns a non-applied status.

CQL returns a result containing the `[applied]` column:

```text
[applied]
---------
true       -- Condition met, record created
```

Or, if the same key already exists:

```text
[applied] | ...
----------+----
false     | ... -- Existing values may appear in the result
```

The displayed table is illustrative. The set of columns returned alongside `[applied]` depends on the statement and outcome; inspect the `[applied]` field by name rather than relying on column position.

### Why not use LWT for every write?

LWT must perform extra coordination/consensus round-trips and typically incurs higher latency and cost than normal writes. Only use it when the business requirement **genuinely requires an atomic existence check**.

| Requirement | Suitable approach |
| --- | --- |
| Writing sensor readings repeatedly where the same key can update to a newer value | Normal write/upsert if update semantics are acceptable. |
| Must never overwrite an accepted payload for the same `event_id` and key | `INSERT ... IF NOT EXISTS` or an appropriate versioning mechanism. |
| Claiming a natural key / unique transaction code for a workflow | Identify a key with the right scope; consider LWT to allocate/reserve it. |
| Preventing duplicates on a column outside the primary key | Must model an additional write check via a separate keyed table; LWT on the original table does not check that column across all rows. |

LWT coordination scope is limited to the partition key being operated on. Do **not** infer that two different tables or multiple partitions are updated atomically merely because each individual statement uses `IF NOT EXISTS`.

### LWT timeouts can also leave an uncertain outcome

If the client receives a timeout, do not immediately conclude the write failed. The operation may already have been applied in the cluster while the response failed to arrive in time.

When retrying, use the **exact same key and original business payload**. If the retry returns `[applied] = false`, read/verify the current value: it may be the very record created by the prior call, or created by a competing client. A `false` result alone does **not** prove who created the row.

## 6. How does primary key uniqueness differ from business uniqueness?

Suppose the system requires each normalized email to belong to only **one user across the entire application**. The following table does not guarantee that requirement:

```sql
CREATE TABLE users_by_id (
    user_id uuid PRIMARY KEY,
    email_normalized text,
    display_name text
);
```

Two different `user_id`s can easily contain the same `email_normalized`. Cassandra does not have an independent `UNIQUE(email_normalized)` constraint as in many relational DBMSs.

A common pattern is creating a table that **claims email ownership** using the email itself as the primary key:

```sql
CREATE TABLE email_owner_by_address (
    email_normalized text PRIMARY KEY,
    user_id uuid
);
```

During registration, attempt to claim email ownership:

```sql
INSERT INTO email_owner_by_address (
    email_normalized, user_id
) VALUES (
    'alice@example.com',
    8817a208-1858-4144-86e9-b24d9083e478
)
IF NOT EXISTS;
```

Because `email_normalized` is the sole primary key of the claim table, registration requests for the **same normalized email string** contend on the exact same row. LWT ensures only one request succeeds in creating the claim under contention.

However, this design has important limitations:

1. **Normalization must be consistent** across all reads and writes: uppercase, lowercase, Unicode, whitespace, and domain/email rules must follow product requirements. Two different strings produce two different primary keys.
2. `email_owner_by_address` and `users_by_id` are **two separate tables**. Successfully creating the claim does not simultaneously create the user profile in a multi-table atomic transaction.
3. If writing the user profile fails after claiming the email, the system can end up with an **orphan claim**. If writing the profile first and claiming the email fails, there can be an **unclaimed/invalid profile**.
4. You need a defined state workflow (*reserved*, *active* if used), consistent retries, reconciliation checks, and recovery jobs when one step succeeds and the next fails.
5. If a claim is deleted or expires via TTL, the email may become available for allocation again even if old profile data remains. Reuse must follow clear business rules.

This is an example of **query- and constraint-driven data modeling** in Cassandra. Do not treat a claim table as a complete cross-table transaction.

## 7. Idempotency on retry: choose the ID before sending the command

In distributed systems, writes can time out or connections can drop after the server has already processed the request. Clients often need to retry to ensure business progress. If each retry generates **a new primary key**, the system can duplicate events.

### How events get duplicated easily

```text
Business request: record money transfer event T

Attempt 1: event_id = UUID-A, client times out
Attempt 2: event_id = UUID-B, client receives success

If both writes are applied:
    -> two different primary keys
    -> two event rows
```

If you use `now()` for a `timeuuid` clustering key, it generates a new value on every execution; hence retrying an `INSERT` with `now()` **does not automatically ensure idempotency**.

### How to keep logical identity stable

```text
Business request: record money transfer event T
     |
     v
Generate/look up stable event_id for T = UUID-A
     |
     +-- Attempt 1: full primary key (..., UUID-A)
     |
     +-- Attempt 2: full primary key (..., UUID-A)
     |
     v
Same logical row coordinate; does not create a second row on retry.
```

Condition: preserve **all** primary key components, including the partition key, time bucket, and clustering timestamp. Keeping only `event_id` constant while recomputing `occurred_at` or `event_day` can still create a different row.

A practical strategy:

- Use a stable business identifier `event_id`, generated **once per event** or derived from the request's idempotency key.
- Keep `occurred_at` and `event_day` consistent across retries.
- Write the same payload for the same logical identity, or use LWT if modifying an already-accepted record is forbidden.
- Verify the outcome on ambiguous timeouts; do not assume a client timeout means the cluster did not write.
- For financial operations or external side effects, distinguish "not creating two Cassandra rows" from "executing the entire business action exactly once" — these two requirements are **not equivalent**.

**Note:** upserting with a stable key prevents creating extra rows, yet resending an `INSERT` with a new write timestamp/TTL can affect expiration time or write conflicts. If the logic requires "apply only once," use conditional writes or appropriate orchestration.

## 8. Changing identity and deleting data

The primary key is a row's **coordinate**. You cannot treat updating a primary key component like editing a regular column with `UPDATE`.

For example, if `event_day` was written incorrectly, the proper fix typically is:

1. Write a row with the **new** primary key containing the correct `event_day`.
2. Verify the result and business dependencies.
3. Delete the old row by the **full old primary key** if needed.

```sql
-- Delete the event row using the exact full old identifier:
DELETE FROM events_by_account_day
WHERE account_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-20'
  AND occurred_at = '2026-11-21T09:00:00Z'
  AND event_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

Cassandra uses **tombstones** to represent deletions; compaction and repair/tombstone mechanisms must process deleted data across replicas. Writing a new row and deleting the old row across **two different partition keys** does not constitute an atomic multi-partition transaction.

TTL also affects row existence scope: if cells expire via TTL or are deleted, the fact that "a record existed previously" is not preserved forever automatically. A future `INSERT ... IF NOT EXISTS` can be accepted once the old row no longer exists according to data state at check time. If you need **never to reuse a business code permanently**, store an identifier/claim record with an appropriate lifecycle or dedicated workflow; do not rely on a short-TTL event table.

## 9. Java application: conditional write by primary key

The example below uses the Java Driver 4.x API, assuming `CqlSession` is connected and the keyspace contains `events_by_account_day`. An event is represented by a **full primary key** keeping the same values across invocations.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class EventRepository {
    private final CqlSession session;
    private final PreparedStatement insertIfAbsent;

    public EventRepository(CqlSession session) {
        this.session = session;
        this.insertIfAbsent = session.prepare(
            "INSERT INTO events_by_account_day " +
            "(account_id, event_day, occurred_at, event_id, event_type, amount) " +
            "VALUES (?, ?, ?, ?, ?, ?) IF NOT EXISTS"
        );
    }

    public boolean createIfAbsent(
            UUID accountId,
            LocalDate eventDay,
            Instant occurredAt,
            UUID eventId,
            String eventType,
            BigDecimal amount) {

        ResultSet result = session.execute(insertIfAbsent.bind(
            accountId, eventDay, occurredAt, eventId, eventType, amount
        ));
        return result.wasApplied();
    }
}
```

Usage:

```java
UUID accountId = UUID.fromString(
    "327a71e9-f562-4b54-94b9-2138a9e30b12"
);
UUID eventId = UUID.fromString(
    "8817a208-1858-4144-86e9-b24d9083e478"
); // Stable ID for one event, reused on retry.

boolean created = repository.createIfAbsent(
    accountId,
    LocalDate.of(2026, 11, 21),
    Instant.parse("2026-11-21T09:00:00Z"),
    eventId,
    "purchase",
    new BigDecimal("120.00")
);
```

Explanation:

- `result.wasApplied() == true` indicates this LWT execution created the row when the condition was met.
- `false` indicates a row already existed at check time; the application should consider reconciling data in case it was an earlier successful write.
- If the request times out or hits a network error, do **not** infer `false` or `true`; the outcome is unknown to the client. Retries must preserve the exact key tuple and payload.
- LWT queries incur consensus overhead; consider latency, timeout settings, and the application's retry policy.

When specific consistency levels are required, the driver allows configuring the query's **consistency level** and **serial consistency** for LWT (such as `SERIAL` or `LOCAL_SERIAL` depending on topology). Choose a policy matching the keyspace's replication strategy; raising consistency does not turn an unconditional statement into an "insert if absent" check.

### Standard write with a fixed ID

If upsert is the desired semantics, the same method can replace the CQL string with `INSERT ... VALUES (...)` without `IF NOT EXISTS`. In that case `wasApplied()` does not carry "newly created" semantics, because standard writes **do not evaluate an existence condition**. Write success merely confirms the operation at the chosen consistency level.

## 10. Common misconceptions

| Claim | Why is it wrong/incomplete? | What to do |
| --- | --- | --- |
| "Having `PRIMARY KEY (..., event_id)` makes `event_id` unique across the whole table." | Other components can differ between two rows. | Identify the **full primary key tuple** and the business scope requiring uniqueness. |
| "Duplicate-key `INSERT` should raise an error like SQL." | Standard `INSERT` is an upsert. | Use `IF NOT EXISTS` when overwrites must be rejected. |
| "Reusing the same UUID on retry is enough." | Day bucket or clustering timestamp could change between calls. | Fix the **entire primary key**. |
| "Putting email as a regular column in the user table prevents duplicates." | Cassandra does not enforce regular column uniqueness. | Create an email claim/index mechanism with proper constraints and LWT. |
| "LWT on the claim table plus writing the profile table is a cross-table transaction." | The two operations can succeed or fail independently. | Design state transitions and recovery for partial writes. |
| "Client timeout means the write did not happen." | The response may be lost after the cluster already processed it. | Retry safely and reconcile current state. |
| "Increasing consistency is enough to guarantee a code is created only once." | Consistency level generally does not replace a conditional creation check. | Use a properly scoped key, LWT, or required coordination mechanism. |
| "Deleting a row permanently prevents that code from being reused." | Rows/tombstones/TTL have lifecycles; existence state can change. | Store a long-lived claim if business rules forbid reuse. |
| "Two writes with the same primary key must replace the whole record." | Cassandra updates per column/cell with timestamps; omitted columns can keep old values. | Understand cell-level upserts; define clear update rules. |

## 11. Self-check exercises

Consider the table:

```sql
CREATE TABLE invoice_events_by_month (
    tenant_id      text,
    month_bucket   text,
    invoice_id     uuid,
    event_time     timestamp,
    event_id       uuid,
    event_kind     text,
    PRIMARY KEY (
        (tenant_id, month_bucket),
        invoice_id,
        event_time,
        event_id
    )
);
```

Suppose the following rows exist:

| Row | `tenant_id` | `month_bucket` | `invoice_id` | `event_time` | `event_id` |
| --- | --- | --- | --- | --- | --- |
| A | acme | 2026-11 | I-1 | 09:00 | E-1 |
| B | acme | 2026-11 | I-1 | 09:00 | E-2 |
| C | acme | 2026-12 | I-1 | 09:00 | E-1 |
| D | beta | 2026-11 | I-1 | 09:00 | E-1 |
| E | acme | 2026-11 | I-1 | 09:00 | E-1 |

The notations `I-1` and `E-1` are shorthand for hypothetical UUID values, not CQL literals.

**Questions:**

1. Which rows among A–E share the same primary key?
2. Are A and B in the same partition? Can they coexist at the same time?
3. A and C share `event_id` but have different months; will Cassandra block them as duplicate IDs?
4. Using normal `INSERT` to write E after A: does Cassandra add a new row or affect row A?
5. If using `INSERT ... IF NOT EXISTS` for E when A already exists, what is `[applied]` expected to be?
6. If an application requires every `invoice_id` to be globally unique across the system, does the schema above guarantee that?
7. Is writing `amount` to another table after a successful claim automatically atomic with the claim's LWT?

**Answers:**

1. **A and E** share the full tuple `(tenant_id, month_bucket, invoice_id, event_time, event_id)`.
2. **Yes**, same partition because they share `(tenant_id, month_bucket)`; **yes**, they can coexist because `event_id` differs.
3. **Not blocked**: different `month_bucket` means different primary key and different partition.
4. Normal `INSERT` will **upsert row A**, not create a new row.
5. **`[applied] = false`**, because a row with the matching primary key already exists.
6. **No**. The same `invoice_id` can still appear in another tenant/month or another event row. Define "unique invoice" using an identifier table matching business requirements.
7. **No**. Different tables and partitions require explicit coordination and recovery for partial writes.

## 12. Design principles to take into practice

- Uniqueness in Cassandra is always evaluated across the **entire primary key**, scoped to a single table.
- **Partition keys** determine the partition; **clustering columns** identify rows within the partition. An individual clustering column value is not inherently table-wide unique.
- Standard `INSERT` and `UPDATE` have **upsert** semantics and do not automatically reject an existing key.
- `IF NOT EXISTS` uses LWT to perform **conditional creation** at the exact key; you pay coordination overhead and still must handle ambiguous timeouts.
- Idempotency on retry requires **stabilizing the entire key tuple** and payload semantics, not merely generating a random new UUID on every call.
- If a **business attribute** such as email, invoice number, or transaction code must be unique beyond the current key scope, build a dedicated identifier/claim mechanism and clearly define write, recovery, and data lifecycle workflows.
- With replicated data, distinguish **row logical uniqueness**, **conditional write consensus**, **read/write consistency levels**, and **end-to-end business completion** — these are separate concerns.

Understanding "uniqueness within primary key scope" correctly helps you avoid duplicated events, unintended overwrites, and wrong expectations about uniqueness in Cassandra. From this foundation, you can proceed to query-driven table design, safe write flows from Java applications, and selecting appropriate replication, consistency, and error-handling mechanisms.
