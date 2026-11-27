# Timestamps Provided by Driver, Client, or Coordinator in Apache Cassandra

## 1. Why Know Who Assigns the Mutation Timestamp?

In **Apache Cassandra**, a distributed **wide-column** database, the same partition can be written to multiple replicas. When replicas hold different versions of the same cell, Cassandra uses the **mutation timestamp** (also called *write timestamp*) to reconcile them under the **last-write-wins** rule: the version with the higher timestamp typically wins.

Consequently, whoever issues an `UPDATE` later in real time is **not guaranteed** to overwrite a value with a higher timestamp. To handle conflicts properly, you need to know where the timestamp is assigned: directly in the CQL statement, via application/driver code, or at the cluster **coordinator**.

For example, two services both update `display_name` for a customer:

| Request | User action time | Assigned write timestamp (µs) | Value |
|---|---|---:|---|
| Service A | Earlier | `1767225600123500` | `'An'` |
| Service B | Later | `1767225600123400` | `'Bình'` |

If both write the same cell and there is no newer tombstone, **`'An'` wins** because A's timestamp is larger, even though B's operation happened later. The cause could be B intentionally using an older timestamp or clock skew between machines. A higher consistency level cannot fix this incorrect timestamp ordering.

> **Terminology:** `client` is the program calling Cassandra; `driver` is the client-side library, such as Apache/DataStax Java Driver; `coordinator` is the Cassandra node that receives and routes a request to the appropriate replicas. The driver also runs on the client side, yet driver-generated timestamps and application-supplied timestamps are **two distinct policies**.

## 2. Four Timestamp Sources and Precedence Order

For regular CQL write statements, there are four possible ways to assign the mutation timestamp, in **highest-to-lowest precedence order**:

1. **Inside the CQL statement itself:** `USING TIMESTAMP <epoch_microseconds>`.
2. **Application set on the statement via driver API:** e.g., `setQueryTimestamp(long)` in Java Driver 4.x.
3. **Driver-configured timestamp generator:** automatically generates a value for the request when the statement has no explicit timestamp.
4. **Server-side coordinator timestamp:** when the request carries no client-supplied timestamp.

```text
                 Java application / CQL client
                            |
                            v
                 Does CQL have USING TIMESTAMP?
                    /             \
                  Yes              No
                   |                |
         Take timestamp from CQL    v
                              Does Statement have
                             query timestamp?
                              /          \
                            Yes          No
                             |             |
                       Take from API       v
                                    Driver timestamp
                                       generator
                                      /       \
                                  Has value   Unset
                                     |           |
                            Take from generator  v
                                           Coordinator
                                        generates timestamp
                                                |
                                                v
                                Write mutations to replicas
```

This rule aligns with Java Driver 4.x and the **default timestamp** mechanism in the Cassandra native protocol: a timestamp written directly in CQL takes precedence over the default timestamp sent with the request.

| Source | Who decides? | Use case | Notes |
|---|---|---|---|
| `USING TIMESTAMP` | CQL author or CQL-generating application | Data imports, event replay, problems with a clear source timestamp | Unit is **microseconds**; highest in precedence order |
| `setQueryTimestamp()` | Application code via the driver | Specific requests needing a custom business timestamp | No need to alter CQL strings; value is epoch **microseconds** |
| Driver timestamp generator | Client library configuration and algorithm | Normal write flows needing a consistent per-client/session policy | Can increase monotonically within the driver, not cluster-wide |
| Coordinator | Cassandra node handling the request | When the client does not supply a timestamp | Depends on the coordinator node's clock; different nodes may drift |

**What to avoid:** A single request does **not** get assigned an independent timestamp at **each replica** during a normal mutation. The timestamp is determined along the request-handling path and travels with the data to replicas. Conversely, **two different requests** may have timestamps assigned by two different clients or two different coordinators, leading to conflicts.

## 3. CQL `USING TIMESTAMP`: Direct Control from the Write Statement

Create a test table in a separate **keyspace** already selected with `USE <keyspace>;`:

```sql
CREATE TABLE IF NOT EXISTS customer_profile_by_id (
    customer_id uuid PRIMARY KEY,
    display_name text,
    contact_email text
);
```

Write a value with a specific timestamp:

```sql
INSERT INTO customer_profile_by_id (customer_id, display_name, contact_email)
VALUES (
    33333333-3333-3333-3333-333333333333,
    'An',
    'an@example.com'
)
USING TIMESTAMP 1767225600123456;

SELECT display_name, writetime(display_name),
       contact_email, writetime(contact_email)
FROM customer_profile_by_id
WHERE customer_id = 33333333-3333-3333-3333-333333333333;
```

Both regular cells just written carry timestamp `1767225600123456`. The `writetime()` function reports the **currently winning write timestamp** of the cell, not the time the query was executed. It cannot be used on primary keys or counters.

Try rewriting `display_name` with a **smaller** timestamp:

```sql
UPDATE customer_profile_by_id
USING TIMESTAMP 1767225600123000
SET display_name = 'Bình'
WHERE customer_id = 33333333-3333-3333-3333-333333333333;

SELECT display_name, writetime(display_name)
FROM customer_profile_by_id
WHERE customer_id = 33333333-3333-3333-3333-333333333333;
```

The result stays `'An'` and `1767225600123456`. The statement that just ran did not win because its timestamp was older. Switch to a newer timestamp:

```sql
UPDATE customer_profile_by_id
USING TIMESTAMP 1767225600124000
SET display_name = 'Bình'
WHERE customer_id = 33333333-3333-3333-3333-333333333333;
```

Now `display_name = 'Bình'` with timestamp `1767225600124000`; `contact_email` still carries the original timestamp. LWW applies per **cell**, not by replacing the entire row by default.

CQL also supports manual timestamps for regular delete operations:

```sql
DELETE display_name FROM customer_profile_by_id
USING TIMESTAMP 1767225600125000
WHERE customer_id = 33333333-3333-3333-3333-333333333333;
```

A delete operation creates a **tombstone** carrying the corresponding timestamp. A live value written afterward with a smaller timestamp than the tombstone will not reappear. When trying the examples, use a new key if you have run them before to avoid leftover tombstones/timestamps.

**Unit warning:** `USING TIMESTAMP` requires **microseconds since the Unix epoch**. In Java, `System.currentTimeMillis()` returns **milliseconds** and must not be passed verbatim into CQL. These two timestamp values differ numerically by roughly a factor of one thousand.

## 4. Client Setting the Timestamp on a Statement via Java Driver

Java applications typically use `CqlSession` and prepared statements. If business logic has a verified timestamp from an event, Java Driver 4.x allows setting it with `Statement.setQueryTimestamp(long)`, placing the timestamp in the **request metadata** instead of concatenating `USING TIMESTAMP` into the CQL string.

```java
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class ProfileWriter {
    private final CqlSession session;
    private final PreparedStatement updateName;

    public ProfileWriter(CqlSession session) {
        this.session = session;
        this.updateName = session.prepare(
            "UPDATE customer_profile_by_id " +
            "SET display_name = ? WHERE customer_id = ?"
        );
    }

    public void rename(UUID id, String name, long epochMicros) {
        BoundStatement statement = updateName.bind(name, id)
            .setQueryTimestamp(epochMicros);
        session.execute(statement);
    }
}
```

A usage call might look like:

```java
UUID customerId = UUID.fromString(
    "33333333-3333-3333-3333-333333333333"
);
writer.rename(customerId, "Chi", 1767225600126000L);
```

**Meaning:** the driver sends timestamp `1767225600126000` via the native protocol field. Because the CQL inside the prepared statement has no `USING TIMESTAMP`, the statement-level timestamp is the one applied. This is useful when executing the same prepared statement many times while each event has its own timestamp.

In Java Driver 4.x, built-in statement types are immutable and return a **new statement** when `setQueryTimestamp()` is called. Use the returned value as shown in the example rather than calling the method and executing the old statement variable.

### When Both Methods Appear on the Same Request

Suppose the CQL query contains `USING TIMESTAMP 1767225600124000` while Java code calls `setQueryTimestamp(1767225600126000L)`. Under CQL/native protocol timestamp handling, **the timestamp written in `USING TIMESTAMP` takes precedence**, so the mutation receives timestamp `1767225600124000`.

Because this is easy to misinterpret when debugging, choose **one primary place** to set manual timestamps for each operation type. If a result differs from expectations, inspect both the CQL text and the statement's query timestamp.

## 5. Driver-Generated Timestamps: Default Policy and Monotonicity

When there is no `USING TIMESTAMP` and application code does not call `setQueryTimestamp()`, the driver's **timestamp generator** can assign a timestamp before the request is sent to Cassandra.

In **DataStax/Apache Cassandra Java Driver 4.x** under the default configuration described in the Java Driver 4.16 documentation, `AtomicTimestampGenerator` is the default choice, with these properties:

- Generates timestamps on the **client** side for the request; the coordinator node does not need to read its clock if a value is sent along.
- Maintains **monotonically increasing timestamps across threads sharing the same generator/session**. Even two dispatches very close together may be incremented by one microsecond to avoid collisions.
- Monotonic growth **does not mean** the physical clock is accurate to the microsecond. On many systems, the actual clock source only provides millisecond granularity; the microsecond portion is an added increment produced by the generator.
- If the system generates timestamps too rapidly or the clock steps backward, the generator may have to produce timestamps ahead of wall-clock time. The driver has a mechanism to log **clock skew/drift** warnings when configured with appropriate thresholds.

Illustrative HOCON configuration example:

```hocon
datastax-java-driver {
  advanced.timestamp-generator {
    class = AtomicTimestampGenerator
  }
}
```

Notable options include:

| Generator | Behavior | When to consider |
|---|---|---|
| `AtomicTimestampGenerator` | Maintains monotonically increasing values across threads sharing the generator | Normal writes within a single JVM/session; typical default in Java Driver 4.x |
| `ThreadLocalTimestampGenerator` | Monotonically increasing **per thread**, not guaranteed across threads | When threads write independently without timestamp contention |
| `ServerSideTimestampGenerator` | Does not assign client-side timestamps, leaving it to the server | When you want the coordinator to be the timestamp source for requests |
| Custom generator | Uses an application-implemented policy | When you have a dedicated, managed source of time/ordering |

Note the **scope**: a monotonically increasing generator in one JVM does not establish a global order across multiple pods, multiple JVMs, multiple regions, or different drivers. When multiple systems write to the same cell, timestamps from different sources can still conflict.

## 6. Coordinator Assigns the Timestamp When the Client Omits It

If the client does not put a timestamp in CQL, the statement has no explicit timestamp, **and the driver does not generate one**, the request arriving at Cassandra needs a default timestamp. In that case, the **coordinator** assigns the mutation timestamp server-side.

In Java Driver 4.x, you can request this policy with the corresponding generator:

```hocon
datastax-java-driver {
  advanced.timestamp-generator {
    class = ServerSideTimestampGenerator
  }
}
```

Illustrative path with replication factor `RF = 3`:

```text
Client A                          Cassandra Cluster
  |
  | UPDATE (no client timestamp)
  +------------------------------> Coordinator X
                                    |
                                    | Assigns timestamp tX
                             +------+-------+
                             |      |       |
                             v      v       v
                          Replica 1  2      3
                           writes tX tX    tX
```

The coordinator node selects the timestamp for the request; replicas receive the mutation via Cassandra's replication mechanism. **The three replicas do not independently pick three separate times for the same mutation**. However, the next request may be coordinated by **coordinator Y** with a different clock from coordinator X, so there is still a risk that timestamps do not increase in actual event order.

For example:

- Request 1 reaches coordinator X, whose clock is 20 seconds fast, and gets `t1`.
- Request 2 reaches coordinator Y 1 second later in real time, but Y's clock is accurate, so it gets `t2 < t1`.
- For the same cell, request 2 may fail to change the visible value because LWW keeps the record with the larger timestamp from request 1.

Synchronizing time across nodes is operationally mandatory. Whether timestamps are generated client-side or server-side, **NTP/chrony**, clock-skew monitoring, and a consistent timestamp policy help reduce hard-to-reproduce bugs.

## 7. Example Comparing All Three Timestamp Paths in One Table

Using the `customer_profile_by_id` table from Section 3, you can run three statements **on three distinct UUIDs** to observe timestamps created by different sources. Using separate keys prevents timestamp conflicts from mixing across tests.

**Case A — CQL decides:**

```sql
INSERT INTO customer_profile_by_id (customer_id, display_name)
VALUES (aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa, 'CQL value')
USING TIMESTAMP 1767225600123456;

SELECT display_name, writetime(display_name)
FROM customer_profile_by_id
WHERE customer_id = aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa;
```

`writetime(display_name)` returns `1767225600123456` when there is no competing value on the same key.

**Case B — Java statement decides:**

```java
UUID id = UUID.fromString("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb");
BoundStatement statement = session.prepare(
        "INSERT INTO customer_profile_by_id " +
        "(customer_id, display_name) VALUES (?, ?)"
    )
    .bind(id, "Java statement value")
    .setQueryTimestamp(1767225600124567L);
session.execute(statement);
```

Check:

```sql
SELECT display_name, writetime(display_name)
FROM customer_profile_by_id
WHERE customer_id = bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb;
```

`writetime(display_name)` returns `1767225600124567`.

**Case C — Default from driver or coordinator:**

```sql
INSERT INTO customer_profile_by_id (customer_id, display_name)
VALUES (cccccccc-cccc-cccc-cccc-cccccccccccc, 'Default value');

SELECT display_name, writetime(display_name)
FROM customer_profile_by_id
WHERE customer_id = cccccccc-cccc-cccc-cccc-cccccccccccc;
```

The timestamp read back is close to when the request was sent/processed if clocks are healthy. **Looking only at `writetime()` does not tell you whether the driver or the coordinator created it**; you must know the tool/driver sending the query and its timestamp generator configuration. For instance, `cqlsh` and a Java application may have different timestamp policies depending on version/configuration.

## 8. Application Design: Choosing a Timestamp Source by Scenario

There is no single best timestamp source for every workload. Start by asking: **what does "a newer write" mean**?

| Requirement | Usually appropriate approach | Reason |
|---|---|---|
| Normal CQL writes from one Java service | Default driver timestamp generator, clock sync | Predictable behavior without manually handling timestamps on every statement |
| Importing historical events in trusted source order | `USING TIMESTAMP` or `setQueryTimestamp()` with standardized timestamps | Preserves precedence by source time/version number if business policy requires it |
| Wanting the server to own timestamp assignment | `ServerSideTimestampGenerator` or client omitting timestamps | The coordinator takes responsibility for assigning write time |
| Multiple services contending over a critical state | Consider LWT (`IF ...`), event versioning, or write coordination | Timestamp-based LWW does not guarantee global business ordering |
| Frequent retries of update operations | Design idempotency keys and a policy to keep the timestamp stable per mutation | Prevents retries of old events from accidentally getting a newer timestamp and overwriting newer data |

Do not use `USING TIMESTAMP` as a substitute for query-driven table design or conditional updates. If you need the latest events by business time, create an appropriate **clustering key** (such as `event_time` or epoch microseconds). Cassandra does not support sorting data by `writetime()` as a general query key.

### Example of a Retry Causing an Unintended Overwrite

1. Event `E1: status = QUEUED` is emitted first, but the request times out; the application does not know which replicas received the write.
2. Event `E2: status = COMPLETED` succeeds and receives timestamp `T2`.
3. A retry of `E1` is sent with a new timestamp `T3 > T2`.
4. Cassandra can select `QUEUED`, rolling the state backward in time.

If business logic needs to replay events in source order, you can keep a fixed timestamp/sequence position per mutation (and manage timestamp collisions across sources). If you need **compare-and-set** on state, use a conditional strategy instead of trusting LWW alone.

## 9. Limitations and Special Cases

### 9.1. Lightweight Transactions (LWT)

LWTs such as `INSERT ... IF NOT EXISTS` or `UPDATE ... IF ...` are coordinated using a conditional transaction mechanism. Cassandra **does not allow arbitrary user-supplied `USING TIMESTAMP` on conditional updates**; a statement like the following is rejected:

```sql
-- Intentionally invalid example:
UPDATE customer_profile_by_id
USING TIMESTAMP 1767225600123456
SET display_name = 'Lan'
WHERE customer_id = 33333333-3333-3333-3333-333333333333
IF display_name = 'An';
```

With Java Driver 4.x, client-side protocol/generator timestamps on LWTs are ignored and the server manages timestamps according to the LWT mechanism. When conditional updates are required, understand the `[applied]` status in LWT results and coordination cost rather than trying to force ordering via manual timestamps.

### 9.2. Counters

Counters have a specialized update mechanism; standard cell-timestamp read/write rules do not apply as they do for regular columns. **Do not use `USING TIMESTAMP` on counter updates**. Choose an appropriate counting model when idempotency or replay is needed.

### 9.3. Batches and Timestamps

The Java Driver allows setting a query timestamp at the **`BatchStatement`** level, in which case the timestamp applies to child statements according to driver/protocol rules. Timestamps set via `setQueryTimestamp()` on **individual child statements inside a batch** may be **ignored**; if individual mutations in a batch need separate timestamps, structure the statements and `USING TIMESTAMP` clauses according to CQL rules. Do not treat a batch as a way to automatically guarantee wall-clock ordering or general distributed transactions.

### 9.4. TTL, Tombstones, Compaction, and Repair

Mutation timestamps (µs) decide which cell version wins; **TTL** is declared in **seconds** and governs data lifetime. Meanwhile, a CQL `timestamp` column stores business timestamps at **millisecond** resolution. These three units are not interchangeable.

When `DELETE` or TTL creates deleted/expired data, tombstones prevent replicas holding stale data from resurrecting deleted versions. **Repair** and **compaction** processes must be operated with appropriate tombstone retention policies. If a record carries a timestamp far in the future, subsequent normal mutations may continue to lose to that tombstone or stale value.

## 10. Diagnosing Bugs from Timestamp Sources

When users report "UPDATE succeeded yet reads still return the old value", inspect layer by layer:

| Step | Question | How to verify |
|---|---|---|
| 1 | Are we writing to the right partition, row, and cell? | Cross-check keyspace, table, partition key, and clustering key |
| 2 | What is the currently winning write timestamp? | `SELECT value, writetime(value) ... WHERE ...` on an existing regular column |
| 3 | Does the query include `USING TIMESTAMP`? | Inspect the actual CQL, including prepared queries |
| 4 | Does the application call `setQueryTimestamp()`? | Inspect statement-building code and the epoch microseconds argument |
| 5 | Which timestamp generator does the driver use? | Check `advanced.timestamp-generator` per driver/session/profile |
| 6 | Is the server the timestamp source? | Confirm the driver is not sending a default timestamp, then check coordinator clocks |
| 7 | Is there clock skew, retries, or tombstones? | Check clock-skew logs, event IDs, retry policy, DELETE/TTL history |
| 8 | Are replicas out of sync? | Check replication factor, consistency level, replica status, and repair |

Two important reminders:

- `writetime()` **does not directly reveal who created the timestamp**; it only reflects the value on the existing cell. Tracing the source requires combining client code, driver configuration, and logs.
- Do not diagnose by raising `CL` and assuming write ordering is fixed. `ONE`, `QUORUM`, or `ALL` adjusts how many replicas must acknowledge, **not the timestamp precedence rules**.

A helpful logging convention is to record `eventId`, `partitionKey`, `mutationTimestampMicros` (if set by the application), `timestampSource` (`cql`/`statement`/`driver`/`coordinator` if known), driver configuration, and request outcome. Avoid logging unnecessary sensitive personal data.

## 11. Self-Check

**Question 1.** An application sets both `setQueryTimestamp(5000)` and sends a CQL query containing `USING TIMESTAMP 4000`. For a normal write, which timestamp takes precedence?

**Answer:** `4000` from CQL `USING TIMESTAMP`, because it has higher precedence than the statement-level query timestamp.

**Question 2.** A Java Driver using `AtomicTimestampGenerator` produces monotonically increasing timestamps within the same session. Does that guarantee two Java services on two machines generate timestamps in absolute global order?

**Answer:** No. Each machine/session has its own generator and clock; internal monotonicity does not apply system-wide.

**Question 3.** A client neither attaches `USING TIMESTAMP` nor sets a statement timestamp, yet `writetime(display_name)` still returns a value. Who created the timestamp?

**Answer:** Either the **driver timestamp generator**, or the **coordinator** if the generator did not assign one. `writetime()` alone is not enough to tell.

**Question 4.** A server coordinator assigns a timestamp for a request with RF = 3. Do the three replicas generate three different timestamps for the same mutation?

**Answer:** No. The timestamp is determined for the mutation during coordination; replicas receive the corresponding mutation.

**Question 5.** Why is `UPDATE ... USING TIMESTAMP ... IF condition` invalid?

**Answer:** That is an LWT; Cassandra does not permit manual CQL timestamp specification on conditional updates. You must use LWT's own timestamp and coordination mechanism.

**Question 6.** If a client passes `System.currentTimeMillis()` directly into `USING TIMESTAMP`, what is the main bug?

**Answer:** The value is in **milliseconds**, whereas mutation timestamps use **microseconds**. Convert units properly or let the driver/coordinator assign it.

## 12. References

- [Apache Cassandra Native Protocol — default timestamps and how CQL overrides protocol timestamps](https://cassandra.apache.org/doc/latest/cassandra/reference/native-protocol.html)
- [DataStax Java Driver 4.16 — Query timestamps](https://docs.datastax.com/en/developer/java-driver/4.16/manual/core/query_timestamps/)
- [Java Driver 4.x — `Statement.setQueryTimestamp(long)`](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/oss/driver/api/core/cql/Statement.html)

**Key takeaway:** In Cassandra, **`USING TIMESTAMP` > `setQueryTimestamp()` > driver timestamp generator > coordinator fallback** is the precedence order of mutation timestamp sources for regular CQL writes. Regardless of which source assigns it, the timestamp is measured in **microseconds** and participates in **last-write-wins** per cell. Choose the source based on business semantics, control clock skew between clients and servers, and use LWT when conditional updates are required.
