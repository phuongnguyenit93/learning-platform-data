# Clock Skew and Updates with Timestamps Too Far in the Future

## 1. The Problem in Apache Cassandra

**Apache Cassandra** is a **distributed wide-column** database. Data within a partition is replicated across multiple replicas according to the **replication factor (RF)**; requests from multiple applications can arrive at different nodes at different times. When two mutations modify the same cell, Cassandra generally picks the version with the **higher mutation timestamp** under the **last-write-wins (LWW)** rule.

The problem arises when the clock of the machine generating timestamps is skewed: **a single write with a timestamp far in the future can shadow a long series of valid subsequent writes**. Cassandra does not inherently know that a user just clicked "Save" after an earlier event. It only compares the timestamp values on the mutations.

For example, in a customer profile system:

- Service A has a clock that is **30 minutes** fast and writes `display_name = 'An'`.
- One minute later in real time, Service B with an accurate clock writes `display_name = 'Bình'`.
- Because A's timestamp is higher than B's timestamp, Cassandra still displays **`'An'`**, even when B's request was successfully acknowledged by replicas.

This is a **data version ordering** bug, not merely a clock display issue or a query bug. For sensitive domains such as order processing state, a future update can leave the visible state "stuck" until a mutation arrives with a sufficiently large timestamp or a controlled recovery procedure is carried out.

## 2. Mutation Timestamps and Clocks: What Cassandra Actually Compares

A **mutation timestamp** is cell metadata representing time as a 64-bit integer in **microseconds (µs) since the Unix epoch**. It can be supplied by:

1. **CQL `USING TIMESTAMP`** when the write statement explicitly specifies a timestamp.
2. **The application** via a driver statement API, such as `setQueryTimestamp(long)` in Java Driver 4.x.
3. **The driver's timestamp generator** if the driver is configured to generate timestamps client-side.
4. **The Cassandra coordinator** when the request carries no client-supplied timestamp.

The actual timestamp source depends on the CQL, client/driver, and active configuration. Once assigned along the request-handling path, the timestamp travels with the mutation to replicas; **each replica does not independently apply its own clock to the same mutation**.

Do not confuse mutation timestamps with:

| Concept | Typical unit | Meaning |
|---|---|---|
| Mutation timestamp / `writetime(column)` | **Microseconds** | Arbitrates cell versions under LWW |
| CQL column of type `timestamp` | **Milliseconds** | Stores an application timestamp, e.g. `created_at` |
| CQL `USING TTL` / `ttl(column)` | **Seconds** | Lifetime or remaining lifetime of a cell |
| Time the request arrived at coordinator | Depends on logging system | Observational info; not necessarily the mutation timestamp |

**Microsecond resolution does not guarantee microsecond clock accuracy.** A timestamp generator may increment values to avoid collisions within the same process, yet the machine's physical clock may still run fast or slow relative to the outside world.

## 3. What Is Clock Skew and Where Does It Come From?

**Clock skew** is the difference between machines' clocks at the same instant of real time. **Clock drift** typically refers to a clock running fast or slow so that the offset accumulates over time. Cassandra is especially sensitive to clock inaccuracies because LWW compares timestamp values coming from multiple sources.

Illustrative diagram:

```text
    Real time                            10:00:00
           |
           +-- Client A (30 min fast)    10:30:00  -> writes ts ~ 10:30
           |
           +-- Client B (on time)        10:00:00  -> writes ts ~ 10:00
           |
           +-- Coordinator C (2s slow)   09:59:58  -> writes ts ~ 09:59:58

    Same cell: timestamp 10:30 wins,
    regardless of whether requests from B or C were sent later.
```

Common sources of skew:

- **Host/VM/container clocks:** a VM paused and resumed or resynchronized, unstable hypervisor clock sources, misconfigured time-sync services.
- **Client-generated timestamps:** pods/JVMs using different host clocks; one fast host causes every write it emits to carry a future timestamp.
- **Coordinator-generated timestamps:** if the driver does not send a timestamp, requests routed through different coordinators can receive out-of-order values due to differing node clocks.
- **Application-assigned timestamps:** passing epoch milliseconds as microseconds, wrong unit multipliers, using future event times, or trusting unreliable peripheral clocks.
- **Retries and event replay:** a retry assigned a new timestamp can let an older event beat a newer one; conversely, replaying with the same old timestamp may not change the data.

**Time zones are not clock skew.** `2027-01-01T08:00:00+07:00` and `2027-01-01T01:00:00Z` are the **exact same instant**. Different formatting does not mean a clock is wrong. Standardize on **UTC/epoch** when comparing and logging rather than reading local wall-clock strings.

## 4. Timeline: How One Future Timestamp Shadows Valid Writes

Suppose when machines begin processing a record, real-time timestamp is approximately `T0 = 2000000000000000 µs`. Machine A's clock is **30 minutes** fast; machine B is on time and writes **1 minute** after A.

| Mutation on same cell | Timestamp (µs) | Offset from `T0` | Value |
|---|---:|---:|---|
| Initial write | `2000000000000000` | `0` | `queued` |
| Machine A 30 min fast | `2000001800000000` | `+1,800,000,000 µs` = `+30 min` | `approved` |
| Machine B writes 1 min later in real time | `2000000060000000` | `+60,000,000 µs` = `+1 min` | `cancelled` |

```text
Real time:
  T0                      T0 + 1 minute
  |-----------------------------|
  A writes approved             B writes cancelled
  timestamp = T0 + 30 min       timestamp = T0 + 1 min
       |                              |
       +-------- larger timestamp ----+
                        |
             approved still wins

Only a valid version with timestamp > T0 + 30 min
can make the cell show a different value.
```

**Key insight:** B's update may be accepted by the coordinator and replicas at the requested consistency level, yet **never become the winning version** of the cell. "Write succeeded" only reflects that the request completed under the protocol/consistency level; **it does not guarantee the written value will be visible if a larger conflicting timestamp exists**.

The shadowed window is not a physical "lock" lasting exactly 30 minutes. As long as subsequent timestamps stay below `T_future`, they lose. Even after 30 minutes have elapsed, a new mutation only wins when **its timestamp is actually greater than** the currently winning value, subject to Cassandra's tie-breaking rules for equal timestamps.

## 5. CQL Hands-On: Reproducing the Bug on a Test Partition

Run these examples only in a pre-created/selected **test keyspace**. Use an unused UUID; the fixed timestamps below are meant to reproduce the bug and **must not be used for production data**.

### 5.1. Create the Table and Initial Values

```sql
CREATE TABLE IF NOT EXISTS profile_state_demo (
    profile_id uuid PRIMARY KEY,
    status text,
    note text,
    ttl_probe text
);

INSERT INTO profile_state_demo (profile_id, status, note)
VALUES (
    44444444-4444-4444-4444-444444444444,
    'queued',
    'created'
)
USING TIMESTAMP 2000000000000000;

SELECT status, writetime(status), note, writetime(note)
FROM profile_state_demo
WHERE profile_id = 44444444-4444-4444-4444-444444444444;
```

Expected result: `status = 'queued'`; both `status` and `note` cells have write timestamp `2000000000000000`.

### 5.2. Simulate a Fast Client Clock

```sql
UPDATE profile_state_demo
USING TIMESTAMP 2000001800000000
SET status = 'approved'
WHERE profile_id = 44444444-4444-4444-4444-444444444444;

SELECT status, writetime(status)
FROM profile_state_demo
WHERE profile_id = 44444444-4444-4444-4444-444444444444;
```

The `status` cell now has `approved` with timestamp `2000001800000000`: **30 minutes past `T0`** in the scenario.

### 5.3. Write Later in Real Time with a Lower Timestamp

```sql
UPDATE profile_state_demo
USING TIMESTAMP 2000000060000000
SET status = 'cancelled'
WHERE profile_id = 44444444-4444-4444-4444-444444444444;

SELECT status, writetime(status), note, writetime(note)
FROM profile_state_demo
WHERE profile_id = 44444444-4444-4444-4444-444444444444;
```

The result remains `status = 'approved'`, timestamp `2000001800000000`; meanwhile `note = 'created'` keeps its old timestamp. This demonstrates **cell-level LWW**, without overwriting the entire row.

### 5.4. Verify a Mutation with a Larger Timestamp

```sql
-- Only demonstrates the LWW outcome in a test environment.
UPDATE profile_state_demo
USING TIMESTAMP 2000001800000001
SET status = 'cancelled'
WHERE profile_id = 44444444-4444-4444-4444-444444444444;

SELECT status, writetime(status)
FROM profile_state_demo
WHERE profile_id = 44444444-4444-4444-4444-444444444444;
```

Now `cancelled` wins because its timestamp is **exactly 1 µs higher**. **Do not mechanically apply a "just bump the timestamp to fix it" trick in production**: overwriting with an even larger future timestamp can keep normal updates losing for even longer.

### 5.5. Tombstones Can Also Be in the Future

```sql
-- On a different test UUID to avoid colliding with previous steps.
INSERT INTO profile_state_demo (profile_id, status)
VALUES (
    55555555-5555-5555-5555-555555555555,
    'open'
)
USING TIMESTAMP 2000000000000000;

DELETE status FROM profile_state_demo
USING TIMESTAMP 2000001800000000
WHERE profile_id = 55555555-5555-5555-5555-555555555555;

UPDATE profile_state_demo
USING TIMESTAMP 2000000060000000
SET status = 'reopened'
WHERE profile_id = 55555555-5555-5555-5555-555555555555;

SELECT status
FROM profile_state_demo
WHERE profile_id = 55555555-5555-5555-5555-555555555555;
```

`status` still has no visible value, because the **tombstone** has a higher timestamp than the `reopened` record. When timestamps are equal, a tombstone takes precedence over a live value. `writetime(status)` is not a tool for directly viewing the timestamp of a deleted tombstone.

## 6. Can Raising Consistency Level Fix a Skewed Clock?

**No.** In Cassandra, these mechanisms address separate dimensions:

| Mechanism | Question it answers | What it does not solve |
|---|---|---|
| `RF` (replication factor) | How many replicas store a partition? | Does not define which timestamp is business-correct |
| Consistency level such as `ONE`, `QUORUM`, `ALL` | How many replicas/acks are required to complete a request? | Does not fix an abnormally large timestamp, does not guarantee "later request wins" |
| Last-write-wins | Which cell wins when multiple versions conflict? | Does not know whether the source clock was right or in what order users clicked buttons |
| Repair | How are replicas compared and synchronized? | Does not guess the "business-correct" value if timestamps were wrong |

Suppose `RF = 3` and all three replicas already wrote `approved@T_future`. Even if a later `cancelled@T_normal` request is sent with `CL = ALL`, the lower timestamp still loses. **Repair can bring replicas into agreement on the version with the highest timestamp**, but it does not turn a business-correct write into the winning version.

With `CL = ONE`, you may also encounter out-of-sync replicas. When diagnosing, distinguish **reading stale data due to replica lag** from **newer writes being shadowed by LWW due to timestamp**. Reading at an appropriate consistency level, combined with `writetime()` and mutation history, clarifies the root cause; simply raising CL is not a root fix.

## 7. Driver, Coordinator, and Timestamp Source Selection

In a Java application connecting to Cassandra with **Java Driver 4.x**, a request can receive its timestamp from the driver before being sent. For example, `AtomicTimestampGenerator` maintains monotonically increasing timestamps within the generator's scope even when many requests are issued rapidly. However:

- **Monotonicity within a single process** does not guarantee ordering across **multiple JVMs/pods/machines**.
- A client machine whose clock is 30 minutes fast can keep issuing timestamps 30 minutes ahead for many mutations.
- If you leave **coordinator** nodes to assign timestamps server-side, the clock-skew issue shifts to the clocks of the Cassandra nodes acting as coordinators.
- When `USING TIMESTAMP` or an application-set statement timestamp is present, driver clock-sync settings **cannot help** if the application itself supplies a future value.

Java Driver 4.x example writing with the default timestamp policy:

```java
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class ProfileStateRepository {
    private final CqlSession session;
    private final PreparedStatement updateStatus;

    public ProfileStateRepository(CqlSession session) {
        this.session = session;
        this.updateStatus = session.prepare(
            "UPDATE profile_state_demo " +
            "SET status = ? WHERE profile_id = ?"
        );
    }

    public void updateStatus(UUID id, String status) {
        // Do not set USING TIMESTAMP or setQueryTimestamp().
        // The driver/coordinator selects the timestamp per active configuration.
        session.execute(updateStatus.bind(status, id));
    }
}
```

When **deliberately** aligning order with a trusted event source, the application can choose the timestamp manually:

```java
import java.time.Instant;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

public void updateWithEventTime(UUID id, String status, Instant eventTime) {
    long micros = Math.addExact(
        Math.multiplyExact(eventTime.getEpochSecond(), 1_000_000L),
        eventTime.getNano() / 1_000L
    );

    BoundStatement statement = updateStatus.bind(status, id)
        .setQueryTimestamp(micros);

    session.execute(statement);
}
```

Use the second snippet only if **ordering by event time** is genuinely the intended business policy and event time is trustworthy. Never pass `System.currentTimeMillis()` directly to `setQueryTimestamp()` because the API expects **microseconds**, whereas that method returns **milliseconds**. `Instant` has nanosecond resolution; the conversion in the example extracts epoch microseconds and drops sub-1 µs fractions.

## 8. Interaction with TTL, Tombstones, Compaction, and Repair

Clock skew causes trickier bugs when data has a **TTL** or is deleted:

- **Mutation timestamp** determines which live record or tombstone wins during version reconciliation.
- **TTL**, declared in CQL in **seconds** (for example `USING TTL 3600`), controls the data lifetime through its own expiration mechanism. **Do not assume** that a write timestamp 30 minutes fast will automatically extend TTL by exactly 30 minutes; these are two separate mechanisms.
- A **tombstone** with a high future write timestamp can shadow live data written later with a normal timestamp.
- **Compaction** and tombstone garbage-collection policies must align with **repair** and replica health. Purging tombstones while a replica still holds an old version can cause deleted data to reappear (*zombie data*).

Example with TTL on the test table:

```sql
UPDATE profile_state_demo
USING TTL 3600
SET ttl_probe = 'temporary'
WHERE profile_id = 44444444-4444-4444-4444-444444444444;

SELECT ttl_probe, writetime(ttl_probe), ttl(ttl_probe)
FROM profile_state_demo
WHERE profile_id = 44444444-4444-4444-4444-444444444444;
```

`writetime(ttl_probe)` represents the mutation's **microseconds**; `ttl(ttl_probe)` represents the **remaining seconds**. The `ttl_probe` column was not written in previous steps, so this update does not compete against a large existing timestamp. It is a different cell from `status`: `status`'s future timestamp **does not automatically alter the TTL on `ttl_probe`**.

In real operations, never arbitrarily lower `gc_grace_seconds`, skip repair, or delete SSTable files just to "get rid of" a future timestamp. Those actions can compromise zombie protection and data safety; a proper recovery plan is needed once the root cause is identified.

## 9. How to Detect the Issue on a Running System

Common symptom: the application issues `UPDATE` successfully, yet `SELECT` still returns the old state. It is especially suspicious if `writetime()` is noticeably larger than the **epoch microseconds** corresponding to the current UTC time.

### 9.1. Read the Data and Cell Timestamp

```sql
SELECT profile_id, status, writetime(status)
FROM profile_state_demo
WHERE profile_id = 44444444-4444-4444-4444-444444444444;
```

Compare the returned number against the UTC timestamp from a **trusted time source**. For example:

```text
Actual UTC time:     T0
writetime(status):   T0 + 30 minutes
Observed offset:     +1,800,000,000 µs
```

Note that `writetime()` only reports the timestamp of the **currently visible cell**. It does not indicate **who** generated the timestamp. For deleted or TTL-expired cells, use appropriate tombstone diagnostics rather than expecting `writetime()` to always return a number.

### 9.2. Trace Back the Timestamp Source

| Question | Data to inspect |
|---|---|
| Does the query have `USING TIMESTAMP`? | Final CQL sent, code building prepared/batch statements |
| Does Java code call `setQueryTimestamp()`? | Parameters, units, code converting from `Instant` or event time |
| Does the driver generate timestamps client-side? | Timestamp generator configuration and driver version |
| Is the coordinator left to generate timestamps? | Request config, chosen coordinator, Cassandra node clock status |
| Do requests come from multiple regions/hosts? | Service names, hosts/pods, clock offsets, retry timings |
| Are there deletes/TTLs? | `DELETE` history, TTLs, tombstone timing, and repair policy |
| Are old events being replayed? | Event IDs, source ordering, retry IDs, deduplication |

Watch out for the difference between **microseconds and milliseconds**: current epoch milliseconds typically have around 13 digits, while epoch microseconds have around 16 digits. This is only a quick heuristic, **not an absolute correctness check**. Wrong-unit data can look like a timestamp far in the past; mis-multiplied data or a future clock source can look like a timestamp far in the future.

### 9.3. Node and Application Clocks

On Linux machines, operators usually check time synchronization via `timedatectl`, `chronyc tracking`, or infrastructure-equivalent tools while comparing against an authoritative UTC/NTP source. Measure on **both Cassandra nodes** and **machines running services/drivers**, since one side may generate timestamps while the other merely receives them.

Signals to monitor:

- Clock offset between hosts and the reference source, drift trends, and backward/forward clock jumps.
- Driver clock-drift/timestamp-generator warnings, if provided by the driver and configuration.
- Increases in cases where `writetime(cell) > nowMicros + threshold` on safely sampled live records.
- Unusual write timeouts/retries, or multiple actors concurrently writing the same partition or cell.
- Replica status, consistency levels, repair lag, and related compaction runs.

**Thresholds** must be decided per system based on SLA and write pattern. For instance, a historical event source may legitimately use past timestamps; valid backfill logs should not be flagged as clock skew merely because processing time differs.

## 10. Prevention: Time Synchronization and Limiting Write Sources

A good strategy is to **reduce the chance of bad timestamps at the source**:

1. **Synchronize clocks on all hosts.** Use NTP/chrony or an equivalent time service; verify sync status after reboots, suspend/resume events, and infrastructure changes.
2. **Monitor offsets with drift alerts.** Measure both the Cassandra cluster and the clients generating timestamps. Never inspect just one arbitrary node's clock.
3. **Standardize timestamps at API boundaries.** Variable/field names should make units explicit: `epochMicros`, `epochMillis`, or ISO-8601 strings with explicit offsets.
4. **Limit manual timestamp assignment.** For normal writes, prefer a well-understood generator policy; use event timestamps only when the source event has a valid ordering definition.
5. **Validate input timestamps if the business contract allows.** For example, for "happening right now" mutations, reject or quarantine requests with `eventTime > trustedNow + allowedSkew`. Do not blindly reject all past timestamps because valid imports/replays may occur.
6. **Handle retries with event identifiers.** Keep the timestamp stable for the same mutation when idempotency by source time is required; avoid letting an old retry acquire a larger timestamp than a newer update if business logic forbids it.
7. **Avoid multiple writers contending on the same cell.** If deterministic update order is required, use a coordinating owner, checked sequence/version numbers, or **lightweight transactions (LWT)** instead of relying solely on LWW.

Java example illustrating only a **future timestamp boundary check** for real-time events:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public final class EventTimeGuard {
    private final Clock clock;
    private final Duration allowedFutureSkew;

    public EventTimeGuard(Clock clock, Duration allowedFutureSkew) {
        this.clock = clock;
        this.allowedFutureSkew = allowedFutureSkew;
    }

    public void validateRealtimeEvent(Instant eventTime) {
        Instant now = clock.instant();
        if (eventTime.isAfter(now.plus(allowedFutureSkew))) {
            throw new IllegalArgumentException(
                "Event time is unreasonably far in the future"
            );
        }
    }
}
```

This guard only helps if `clock` is synchronized with a trusted source; **a machine with a wrong clock cannot prove its own clock is right**. `allowedFutureSkew` must be configured from SLAs rather than copying an arbitrary constant across systems. Historical backfill jobs require a different policy from real-time state updates.

## 11. Remediating Incidents Once Future Timestamps Exist

When affected data is discovered, the priority is to **stop the bug from repeating**, **determine the scope**, and only then modify data. A practical incident response workflow:

### Step 1 — Stabilize the Timestamp Source

Inspect and synchronize clocks on clients/coordinators; pause or isolate the component emitting bad timestamps. Confirm that `USING TIMESTAMP` / `setQueryTimestamp()` / generator configurations have been fixed, including on retry and batch paths.

### Step 2 — Determine the Impact Scope

Cross-check affected keyspaces, partition keys, clustering keys, and cells; collect `writetime()` of live cells, request logs, event IDs, and timestamps recorded by trusted sources. Check whether tombstones/TTLs are involved. **Do not assume all columns in a row are affected**, because LWW applies per cell.

### Step 3 — Choose a Recovery Option Based on Business Needs

| Option | When to consider | Limitations |
|---|---|---|
| Wait for normal mutations' timestamps to overtake the bad value | Small offset, transient state, acceptable under SLA | Unsuitable if offset is months/years or immediate fix is needed |
| Use a trusted event source to rebuild state | Clean event log/version available, valid value known | Requires designing re-writes and verifying timestamp/tombstone handling |
| Run a targeted fix on specific partitions/cells | Operational plan in place, backed up/verified, current winning timestamp known | Can create an even higher timestamp and prolong the issue if executed carelessly |
| Move to conditional updates or single-writer coordination | Multiple writers repeatedly colliding on state | Design/cost change; does not automatically repair existing data |

**Exercise extreme caution before overwriting with a timestamp higher than the bad future timestamp.** In an experiment, that proves the LWW rule; in production, it can continue "poisoning" subsequent records. Evaluate incoming requests, tombstone behavior, backups, and a safe recovery plan before intervening. Never directly delete SSTables, hack physical timestamps, or shrink grace periods just to erase traces of the incident.

### Step 4 — Verify State After Remediation

Read back the exact partitions/cells at an appropriate consistency level; verify values and `writetime()` where cells exist. Monitor application retries, writer clocks, and repair progress. Check **subsequent writes** as well to confirm no anomalous timestamp continues to dominate the data.

## 12. Relation to Query-Driven Table Design and Ordered Workflows

Cassandra designs tables around **queries**. Event timestamps used for querying are distinct from mutation timestamps used for LWW.

For example, a system receiving state per processing step that needs to retain **history**:

```sql
CREATE TABLE IF NOT EXISTS status_events_by_order (
    order_id uuid,
    event_time timeuuid,
    status text,
    source_id text,
    PRIMARY KEY ((order_id), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);

SELECT event_time, status, source_id
FROM status_events_by_order
WHERE order_id = 66666666-6666-6666-6666-666666666666
LIMIT 20;
```

This model stores events as **separate rows**, reducing direct overwrites on a single status cell. However, `timeuuid` is also typically clock-based, so clock skew can still make event ordering diverge from true business order. If strict ordering is truly required, use a **sequence/version from a trusted coordinator**, store event IDs with deduplication rules, or use LWT for conditional state transitions.

You cannot write `ORDER BY writetime(status)` to solve event ordering: Cassandra orders within a partition by the **clustering key** matching the table design, not by cell mutation-timestamp metadata.

## 13. Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| "The last write always wins." | The version with the **higher mutation timestamp** usually wins; request arrival time can differ |
| "A fast client clock only skews logs." | If the client/driver generates timestamps, data can be **overwritten out of order** |
| "Raising `CL` to `ALL` fixes future timestamps." | CL does not change LWW; it only constrains how many replicas participate/acknowledge |
| "`writetime()` shows when a user edited the data." | It shows the **winning metadata timestamp**, which may have been set manually by the client |
| "Microsecond timestamps are guaranteed accurate real time." | Resolution is not equivalent to accuracy or synchronized clocks |
| "NTP automatically fixes cells that already have future timestamps." | Clock sync helps **future writes**; already-written metadata is not rewritten automatically |
| "Just delete and recreate to clear the bug." | A **lower-timestamp tombstone** can also lose to a future version |
| "TTL in seconds automatically heals any bad write." | TTL has its own expiration mechanism; it is not a write-order recovery tool |
| "Data looks right after repair so the root cause is gone." | Repair synchronizes replicas; a bad timestamp source can still recur |

## 14. Self-Check Questions

**Question 1.** Service A writes `status = 'PAID'` with timestamp `T+30 minutes` due to a fast clock. One minute later, Service B writes `status = 'REFUNDED'` with timestamp `T+1 minute`. Which value wins?

**Answer:** `PAID`, because A's timestamp is higher. A successful write from B does not mean it wins LWW.

**Question 2.** If you switch both reads and writes to `QUORUM` or `ALL`, is `REFUNDED` guaranteed to win?

**Answer:** No. Consistency levels do not fix timestamp ordering; you must fix the time source and state-update rules.

**Question 3.** `writetime(status)` is 2 hours ahead of current UTC time. Can you conclude with certainty that the coordinator's clock is 2 hours fast?

**Answer:** Not yet. The timestamp could have come from `USING TIMESTAMP`, a Java statement, a driver generator, or the coordinator. Inspect the timestamp source and logs.

**Question 4.** A machine with a fast clock is corrected back to accurate time. Do cells that already carry future timestamps automatically lower their write timestamps?

**Answer:** No. Clock synchronization changes the **timestamp source for subsequent writes**; it does not automatically alter stored metadata.

**Question 5.** If a `DELETE` command carries a smaller timestamp than a live version in the future, will the record be removed from read results?

**Answer:** Not guaranteed; an older tombstone does not beat a live version with a higher timestamp. Check the actual timestamps of the relevant mutations.

**Question 6.** In an event history table, if you want to sort by business order, should you rely on `writetime(status)`?

**Answer:** No. Design the **clustering key** to match the query criteria, while using a reliable time source or sequence.

**Question 7.** Why can fixing a record by assigning an even larger timestamp far ahead of the present have long-term consequences?

**Answer:** It causes subsequent normal writes with lower timestamps to keep losing, prolonging the shadowing condition and complicating repair/business recovery.

---

**Key takeaway:** In Cassandra, **clock skew wherever mutation timestamps are generated can become real data corruption**, because LWW compares timestamps rather than when users performed actions. Synchronize and monitor clocks on both clients and Cassandra nodes, control manually assigned timestamps, diagnose using `writetime()` alongside request history, and choose proper coordination/business ordering mechanisms when multiple writers update the same cell.
