# Comparing Before/After State with Two Concurrent Update Sessions in Apache Cassandra

Two users open a profile at the same time, both see `revision = 1`, and each changes a value: **what happens when both write back to Cassandra?** Does the request sent later always win, does `QUORUM` automatically prevent lost updates, and how do you prove what each session actually saw **before** and **after** writing?

In Apache Cassandra, regular `INSERT` and `UPDATE` statements are **keyed upserts**—they do not read and lock the existing row before writing. Versions of a cell are reconciled by **write timestamp** (*last-write-wins*), rather than purely by application call order. When business rules must verify "the value is still what I read," you must switch to a **lightweight transaction (LWT)** with `IF`, typically checking a `revision` column or expected state.

This Knowledge lesson belongs to the **CQL Writes and Deletes** chapter of module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**, aligned with understanding distributed Cassandra architecture, partition keys, CQL, replication, consistency levels, error handling, and Java applications. The centerpiece is a **two-session independent connection experiment** that records before/after state, observes competing updates, and builds the right handling pattern.

After this lesson, you will:

1. Set up **two `cqlsh` sessions A/B** accessing the same cluster and the exact same full primary key.
2. Distinguish **prior read**, **write request**, **acknowledgment**, **post-write read**, and **LWT `[applied]` results**.
3. Observe the winning timestamp when two sessions write **the same column**, even when execution order differs from timestamp order.
4. Compare updating **two distinct columns** against writing back a whole stale object causing a **lost update**.
5. Use `IF revision = expected` so one CAS succeeds and stale writers are rejected.
6. Analyze timeouts, retries, read/write consistency, and implementation in Java Driver 4.x.

## 1. Conventions for "concurrency" and expected outcomes

Two independent sessions do not have to send commands in the exact same microsecond. In this lab, we use two terminal windows:

- **Session A**: client A, in its own `cqlsh` shell.
- **Session B**: client B, in its own `cqlsh` shell connected to the same cluster.

Both can **read the same initial state**, then issue requests according to a prescribed schedule. This simulates controlled *interleaving* of two writers; under true parallel execution, the winning order can vary. For regular writes, the lesson uses **manual timestamps on dedicated lab keys** so reconciliation results are verifiable. For LWT, **never assign manual timestamps** and predict only the invariant "at most one CAS from the same revision can succeed" when no third writer exists.

### Five checkpoints to record in your lab notebook

| Checkpoint | What to record | Meaning |
| --- | --- | --- |
| `T0` — Before update | `SELECT` in A and B, `revision` and relevant columns | State each client observed before deciding |
| `T1` — A sends mutation | CQL, key, timestamp/condition, and response | What client A requested |
| `T2` — B sends mutation | CQL, key, timestamp/condition, and response | What client B requested |
| `T3` — Post-write read | `SELECT` from both sessions at chosen consistency | State observed by each read |
| `T4` — Reconciliation | `WRITETIME` or `[applied]`, revision, actual changes | Explains why that outcome occurred |

**Important:** a regular `UPDATE` completing **does not** mean the row previously existed, nor does it return how many rows changed. A post-write `SELECT` is a **separate request**, not an atomic snapshot returned with `UPDATE`. While A reads, B may already be writing again.

### Three conclusions never to assume

1. **"A sent after B, so A is guaranteed to win."** False when A's timestamp is lower than B's.
2. **"Both A and B succeeded, so both new values are kept."** False when two mutations contend on **the same cell**; one version wins reconciliation.
3. **"I read revision=1 beforehand, so a regular UPDATE can enforce revision=1."** False; only adding `IF revision = 1` puts that condition under LWT enforcement.

## 2. Creating the table and two safe CQL sessions

Run these commands only on a **test cluster** inside an existing `demo` keyspace. Never use real account UUIDs; keys `1111...`, `2222...`, `3333...`, and `4444...` below are dedicated lab keys for each scenario.

```sql
CREATE TABLE demo.profile_concurrency_lab (
    profile_id     uuid PRIMARY KEY,
    display_name   text,
    contact_email  text,
    account_state  text,
    revision       int,
    modified_by    text
);
```

`profile_id` is both the **partition key and full primary key**. All remaining columns are regular columns. With this schema, updates from A and B sharing `profile_id` necessarily contend in the **same logical partition**. Using different keys would fail to demonstrate competing CAS on the same resource.

Open two `cqlsh` terminals pointing to the **same cluster**. Verify both connect to the same keyspace and table—never leave one session on staging and the other on production.

**Session A**

```sql
-- Terminal A / cqlsh A:
DESCRIBE TABLE demo.profile_concurrency_lab;
```

**Session B**

```sql
-- Terminal B / cqlsh B:
DESCRIBE TABLE demo.profile_concurrency_lab;
```

`DESCRIBE` is a `cqlsh` utility, not server-side CQL for Java applications. Both sessions should display matching schemas. If authorization is enabled on the cluster, ensure both roles have appropriate lab permissions; never escalate production privileges casually.

### Consistency for the lab

If the `demo` keyspace has RF=3 and enough healthy nodes, set on **both A and B**:

```sql
CONSISTENCY QUORUM;
```

With RF=3, quorum typically requires 2 replica acknowledgments within the applicable scope. If your lab cluster uses RF=1, `QUORUM` requires only 1 replica and does not demonstrate RF=3 quorum behavior; in multi-datacenter topologies, choose `LOCAL_QUORUM`/`QUORUM` per your replication strategy. Never alter replication factor solely to match an example.

**`QUORUM` does not automatically turn a regular `UPDATE` into compare-and-set**. Choosing consistency clarifies acknowledgment and visibility guarantees; `IF` is what enforces revision conditions.

### Rules for keeping test data isolated

| Lab key | Purpose | Write mode |
| --- | --- | --- |
| `11111111-1111-4111-8111-111111111111` | Two writers on the same cell, comparing write timestamps | **Manual timestamps only** in this experiment |
| `22222222-2222-4222-8222-222222222222` | Two writers updating two separate cells | Default timestamps |
| `33333333-3333-4333-8333-333333333333` | Lost update from writing back stale read data | **Manual timestamps only** in this experiment |
| `44444444-4444-4444-8444-444444444444` | LWT/CAS with `revision` | **Default timestamps, no `USING TIMESTAMP`** |

On keys using manual timestamps, **never mix an auto-timestamped INSERT using current wall-clock time** with past illustrative timestamps: new mutations with smaller timestamps would never win. Every write on those two keys specifies an explicit timestamp from the start so results remain reproducible.

## 3. Scenario A: writing the same column — which timestamp wins?

To eliminate typing-speed variance, use three write timestamps in **microseconds since the Unix epoch**: `1700000000000100` (init), `1700000000000200` (A), and `1700000000000300` (B). These values are **strictly for a fresh lab key**, never for production timestamps.

### T0 — Initialize from A, then read from both

**Session A**

```sql
INSERT INTO demo.profile_concurrency_lab (
    profile_id, display_name, contact_email, account_state, revision
) VALUES (
    11111111-1111-4111-8111-111111111111,
    'Original', 'original@example.test', 'ACTIVE', 1
)
USING TIMESTAMP 1700000000000100;

SELECT display_name, contact_email, account_state,
       revision, WRITETIME(display_name)
FROM demo.profile_concurrency_lab
WHERE profile_id = 11111111-1111-4111-8111-111111111111;
```

**Session B**

```sql
SELECT display_name, contact_email, account_state,
       revision, WRITETIME(display_name)
FROM demo.profile_concurrency_lab
WHERE profile_id = 11111111-1111-4111-8111-111111111111;
```

**Prediction T0:** both sessions see `display_name='Original'`, `revision=1`, and `WRITETIME(display_name)=1700000000000100` assuming no other writers.

### T1 — B writes a version with a higher timestamp

**Session B**

```sql
UPDATE demo.profile_concurrency_lab
USING TIMESTAMP 1700000000000300
SET display_name = 'Name from B'
WHERE profile_id = 11111111-1111-4111-8111-111111111111;
```

**B sends before A** in this lab schedule. Regular `UPDATE` checks neither `revision` nor the old name; when acknowledged, B receives no `[applied]` signal to detect contention.

### T2 — A sends later, but with a lower timestamp

**Session A**

```sql
UPDATE demo.profile_concurrency_lab
USING TIMESTAMP 1700000000000200
SET display_name = 'Name from A'
WHERE profile_id = 11111111-1111-4111-8111-111111111111;
```

### T3 — Both read again to compare

**Run on both A and B**

```sql
SELECT display_name, contact_email, revision,
       WRITETIME(display_name)
FROM demo.profile_concurrency_lab
WHERE profile_id = 11111111-1111-4111-8111-111111111111;
```

| State | `display_name` | `revision` | `WRITETIME(display_name)` |
| --- | --- | ---: | ---: |
| Before writes | Original | 1 | 1700000000000100 |
| After B writes | Name from B | 1 | 1700000000000300 |
| After A writes with lower timestamp | **Name from B** | 1 | **1700000000000300** |

**Conclusion:** Cassandra reconciles versions of the same cell by write timestamp, not "last request sent wins" by wall-clock order. Both regular `UPDATE`s can be acknowledged, yet A's value never becomes live because A's timestamp is lower.

### What you may and may not infer

- `WRITETIME(display_name)` returns the timestamp of the cell currently read, **not a history of every request** ever sent.
- `revision` stays at 1 because both mutations wrote only `display_name`. Revisions never auto-increment or enforce optimistic locking on their own.
- `contact_email` was not rewritten simply because A/B updated the name.
- Equal timestamps use deterministic tie-breaking rules; never rely on tie-breaking as a business arbitration strategy.
- This experiment uses **manual timestamps** for deterministic results; in production, timestamps generated by drivers/coordinators are exposed to clock skew, retries, and concurrent writes.

A caller whose name update "lost" reconciliation will not necessarily know from a regular `UPDATE` acknowledgment alone. To detect stale-state conflicts, use an appropriate condition.

## 4. Scenario B: two sessions editing two different columns

Cassandra stores regular columns as individually timestamped values inside a wide row. Thus, **two partial updates modifying two distinct columns** usually do not need to load and rewrite the whole object.

### T0 — Create a dedicated row and read first

**Session A**

```sql
INSERT INTO demo.profile_concurrency_lab (
    profile_id, display_name, contact_email, account_state, revision
) VALUES (
    22222222-2222-4222-8222-222222222222,
    'Before', 'before@example.test', 'ACTIVE', 1
);

SELECT display_name, contact_email, revision
FROM demo.profile_concurrency_lab
WHERE profile_id = 22222222-2222-4222-8222-222222222222;
```

**Session B**

```sql
SELECT display_name, contact_email, revision
FROM demo.profile_concurrency_lab
WHERE profile_id = 22222222-2222-4222-8222-222222222222;
```

**Prediction T0:** both sessions observe `display_name='Before'`, `contact_email='before@example.test'`, and `revision=1`.

### T1 — A updates only the name

**Session A**

```sql
UPDATE demo.profile_concurrency_lab
SET display_name = 'After A'
WHERE profile_id = 22222222-2222-4222-8222-222222222222;
```

### T2 — B updates only the email

**Session B**

```sql
UPDATE demo.profile_concurrency_lab
SET contact_email = 'after-b@example.test'
WHERE profile_id = 22222222-2222-4222-8222-222222222222;
```

### T3 — Both sessions read the same key

**Run on both A and B**

```sql
SELECT display_name, contact_email, revision,
       WRITETIME(display_name), WRITETIME(contact_email)
FROM demo.profile_concurrency_lab
WHERE profile_id = 22222222-2222-4222-8222-222222222222;
```

| Column | Before | After both unconditional mutations |
| --- | --- | --- |
| `display_name` | Before | **After A** |
| `contact_email` | before@example.test | **after-b@example.test** |
| `revision` | 1 | **1** — does not auto-change |

With two timestamp-winning mutations on **two separate cells**, the logical row preserves **both changes**. This is why **column-selective PATCH** patterns are generally superior to reading the whole row and writing back every field read.

**However, do not infer from this example that all concurrent updates are safe.** If two clients must maintain a cross-column invariant (such as two states that cannot contradict each other), per-cell writes alone do not protect that invariant. Use an appropriate data model and CAS conditions instead.

### NULL does not mean "not sent"

If B does not intend to edit the name, never bind `display_name = NULL` in the mutation:

```sql
-- This is a request to delete the name value, NOT to skip the name.
UPDATE demo.profile_concurrency_lab
SET display_name = NULL
WHERE profile_id = 22222222-2222-4222-8222-222222222222;
```

This statement **illustrates the hazard only**; do not run it if you want to keep the lab state. Cassandra treats `NULL` on a regular column as a tombstone, whereas **omitting the column** or binding `UNSET` in the driver writes no mutation for that column. That distinction is vital when two sessions send JSON PATCH payloads.

## 5. Scenario C: lost update when writing back stale read data

A common Java application bug works like this:

1. `SELECT` the entire row.
2. Map it into a `Profile` object in memory.
3. Modify one field on the object.
4. `UPDATE` **every field**, including fields the user never touched.

If two clients start from the same stale snapshot, the later request can **overwrite** the earlier request's fresh change. That *lost update* stems from how the mutation was constructed, not because Cassandra "erases" omitted fields.

For reproducible results, use key `3333...` and manual timestamps **strictly in scenario C**.

### T0 — Both sessions read the old values

**Session A**

```sql
INSERT INTO demo.profile_concurrency_lab (
    profile_id, display_name, contact_email, account_state, revision
) VALUES (
    33333333-3333-4333-8333-333333333333,
    'Initial Name', 'old@example.test', 'ACTIVE', 1
)
USING TIMESTAMP 1700000000001100;

SELECT display_name, contact_email, revision
FROM demo.profile_concurrency_lab
WHERE profile_id = 33333333-3333-4333-8333-333333333333;
```

**Session B**

```sql
SELECT display_name, contact_email, revision
FROM demo.profile_concurrency_lab
WHERE profile_id = 33333333-3333-4333-8333-333333333333;
```

In B's memory, the email read was `'old@example.test'`. B intends to change **the name**, not **the email**. After this step, **B does not re-read** until after T2.

### T1 — A updates email first

**Session A**

```sql
UPDATE demo.profile_concurrency_lab
USING TIMESTAMP 1700000000001200
SET contact_email = 'new-a@example.test'
WHERE profile_id = 33333333-3333-4333-8333-333333333333;
```

Reading immediately after T1 shows `contact_email='new-a@example.test'` replacing the old email cell value.

### T2 — B writes both the new name and the stale email held in its object

**Session B**

```sql
-- Wrong for business intent: B only meant to update name,
-- yet the UPDATE carried along the email read earlier.
UPDATE demo.profile_concurrency_lab
USING TIMESTAMP 1700000000001300
SET display_name = 'Name from B',
    contact_email = 'old@example.test'
WHERE profile_id = 33333333-3333-4333-8333-333333333333;
```

B carries a higher timestamp than A on **the email cell**, so the old value is written back as a newer version. This is not "Cassandra restoring old data"; **client B actively sent the old value in a new mutation**.

### T3 — Re-read and build a comparison table

**Run on both A and B**

```sql
SELECT display_name, contact_email, revision,
       WRITETIME(display_name), WRITETIME(contact_email)
FROM demo.profile_concurrency_lab
WHERE profile_id = 33333333-3333-4333-8333-333333333333;
```

| Checkpoint | Name | Email | Revision |
| --- | --- | --- | ---: |
| T0 — Both read | Initial Name | old@example.test | 1 |
| T1 — A edits email | Initial Name | **new-a@example.test** | 1 |
| T2 — B writes old object + new name | **Name from B** | **old@example.test** | 1 |

The final `WRITETIME(contact_email)` equals `1700000000001300`: evidence that the latest email version came from B's mutation, **not A's**.

### Three ways to reduce lost-update risk

1. **Write only fields that actually changed**. If B only meant to edit the name, run `SET display_name = 'Name from B'`; when no cross-column invariant applies, A's email is preserved.
2. **Write conditionally by revision / old value**. If B is allowed to update only when nobody else edited the profile since the prior read, use `IF revision = expected` and increment revision in **the same mutation**.
3. **Define clear API contracts**. `PATCH` differs from full-object `PUT`; choose merging versus conflict rejection intentionally. Avoid mapping absent fields to `NULL`.

Note: selective field updates **do not automatically protect** cross-field business rules. If fields A and B must stay mutually consistent, the right tool may still be CAS or a dedicated partition model.

## 6. Scenario D: two sessions competing with IF revision

Now replace standard mutations with **LWT**. Both sessions read `revision=1` and both attempt to change `account_state`. At most one mutation conditioned on `IF revision = 1` applies before revision advances to 2, provided all relevant writers follow the same CAS convention.

**Never** combine `USING TIMESTAMP` with `IF`. LWT/Paxos manages timestamps and coordinates condition checks across replicas. Scenario D uses a fresh key with no manual timestamps.

### T0 — Initialize and have both sessions read the same revision

**Session A**

```sql
INSERT INTO demo.profile_concurrency_lab (
    profile_id, display_name, contact_email,
    account_state, revision
) VALUES (
    44444444-4444-4444-8444-444444444444,
    'Cas Lab', 'cas@example.test', 'PENDING', 1
);

SELECT account_state, revision, modified_by
FROM demo.profile_concurrency_lab
WHERE profile_id = 44444444-4444-4444-8444-444444444444;
```

**Session B**

```sql
SELECT account_state, revision, modified_by
FROM demo.profile_concurrency_lab
WHERE profile_id = 44444444-4444-4444-8444-444444444444;
```

**Prediction T0:** both see `account_state='PENDING'`, `revision=1`, and `modified_by=null`.

### T1 — A sends compare-and-set

**Session A**

```sql
UPDATE demo.profile_concurrency_lab
SET account_state = 'REVIEW',
    revision = 2,
    modified_by = 'A'
WHERE profile_id = 44444444-4444-4444-8444-444444444444
IF revision = 1;
```

Assuming no competing writer altered revision before A, the response includes `[applied] = true`. A requested a **conditional transition**; revision updates to 2 in the same mutation.

### T2 — B sends a mutation with the stale revision

**Session B**

```sql
UPDATE demo.profile_concurrency_lab
SET account_state = 'APPROVED',
    revision = 2,
    modified_by = 'B'
WHERE profile_id = 44444444-4444-4444-8444-444444444444
IF revision = 1;
```

In this lab schedule, A succeeded before B, so B's response is **`[applied] = false`**. Some Cassandra versions/CQL forms return extra columns showing current values on unmet conditions; never assume the entire row is always returned.

If A and B send **truly concurrently**, which one applies first depends on the consensus execution schedule. What is guaranteed with no third writer when every CAS increments revision is: **both cannot succeed with the same `expected revision = 1`**.

### T3 — Read after both requests

**Run on both A and B**

```sql
SELECT account_state, revision, modified_by
FROM demo.profile_concurrency_lab
WHERE profile_id = 44444444-4444-4444-8444-444444444444;
```

| Checkpoint | `account_state` | `revision` | `modified_by` | Response |
| --- | --- | ---: | --- | --- |
| T0 | PENDING | 1 | null | SELECT |
| T1 — A CAS | REVIEW | 2 | A | **`[applied] = true`** |
| T2 — B stale CAS | REVIEW | 2 | A | **`[applied] = false`** |
| T3 — Post-read | REVIEW | 2 | A | SELECT |

**Core difference from scenarios A/C:** B **could not write** its change once the condition was stale. The application learns this via `[applied]`, instead of receiving a silent upsert acknowledgment.

### How should B handle false?

B **must not** blindly swap `IF revision = 1` for `IF revision = 2` and retry. Instead, B must:

1. Read the current state to see A transitioned `PENDING -> REVIEW`.
2. Decide by business rules whether `REVIEW -> APPROVED` is permitted.
3. If permitted, send a new CAS with **expected revision = 2**.
4. If contention persists, cap retries and report a conflict to the caller.

Example only when business rules permit:

```sql
UPDATE demo.profile_concurrency_lab
SET account_state = 'APPROVED',
    revision = 3,
    modified_by = 'B'
WHERE profile_id = 44444444-4444-4444-8444-444444444444
IF account_state = 'REVIEW' AND revision = 2;
```

This LWT can return `[applied] = true` and advance revision to 3. That is a **new decision based on freshly read state**, not automatically "retrying the old request until it wins."

## 7. Comparing IF EXISTS, IF NOT EXISTS, and IF old value

Adding an `IF` keyword does not prevent every kind of conflict between two sessions equally. The condition must match the **business invariant**.

| Condition | What it protects | What it does **not** protect automatically |
| --- | --- | --- |
| `INSERT ... IF NOT EXISTS` | Creates row only if **full primary key does not exist** | Uniqueness of regular columns like email across the table |
| `UPDATE ... IF EXISTS` | Edits only if the row currently exists | Two writers overwriting the same column while the row exists |
| `DELETE ... IF EXISTS` | Deletes only if the row currently exists | Another writer recreating the row after deletion |
| `UPDATE ... IF revision = 1` | Writes only while revision matches | Write paths that **bypass** the revision convention |
| `UPDATE ... IF account_state = 'PENDING'` | Transitions from PENDING only when true | Invariants spanning other partitions |

### Why isn't IF EXISTS enough to prevent lost updates?

Suppose row `4444...` still exists:

```sql
-- Session A may send:
UPDATE demo.profile_concurrency_lab
SET display_name = 'Edited by A'
WHERE profile_id = 44444444-4444-4444-8444-444444444444
IF EXISTS;

-- Session B may send:
UPDATE demo.profile_concurrency_lab
SET display_name = 'Edited by B'
WHERE profile_id = 44444444-4444-4444-8444-444444444444
IF EXISTS;
```

Assuming no delete removes the row, **both existence checks can succeed**. `[applied] = true` on each call only means the row existed; it **does not** prove `display_name` still matched what the client read. These statements are for analysis only—**do not run them after the CAS lab if you want to keep `revision=2`**.

### Two sessions registering the same key

Suppose both A and B attempt to create the **same new `profile_id`**:

```sql
INSERT INTO demo.profile_concurrency_lab (
    profile_id, display_name, account_state, revision
) VALUES (
    66666666-6666-4666-8666-666666666666,
    'New Profile', 'PENDING', 1
)
IF NOT EXISTS;
```

If both sessions send this exact statement for the **same full primary key** before the row exists with no third writer, one request returns `[applied] = true` and the other returns `false` once the key exists. Who wins depends on the LWT decision schedule. However, **two different UUID keys** will not contend merely because `display_name` matches.

### Limitations of revisions

- Cassandra does not auto-increment `revision`. The application must send `SET revision = new` in the same mutation as `IF revision = expected`.
- If another client writes `revision` via an **unconditional** `UPDATE`, the application's CAS rule can break. All write paths for the same invariant must follow the same contract.
- Use monotonically increasing revisions instead of boolean flags to avoid **ABA** bugs (a value flipping back to an old state unnoticed), while guarding against overflow and never resetting revisions backward.
- LWT does not provide arbitrary multi-partition transactions. Email uniqueness requires an email-keyed model or dedicated workflow, not merely `IF NOT EXISTS` on `profile_id`.

## 8. Before/after state differs from acknowledgment

Running an experiment properly means more than looking at the final row: separate the **write response** from **state observed by read queries**.

### With regular UPDATE

```text
Client A: UPDATE ... SET display_name = 'A'
Server:   acknowledges mutation per write consistency level
Client A: receives no row count, no created/updated flag

Client B: UPDATE ... SET display_name = 'B'
Server:   can also acknowledge mutation

Client A/B: SELECT ... -> observes reconciled winning value
```

**Two acknowledgments** do not mean **both values survive** in one cell, nor do they reveal which value won. Reconciling requires knowing keys, timestamps, and read observations.

### With UPDATE IF

```text
Client A: UPDATE ... IF revision = 1
Server:   [applied] = true

Client B: UPDATE ... IF revision = 1
Server:   [applied] = false

Client A/B: SELECT ... -> observes state/revision
```

`[applied] = false` is a **valid unmet-condition result**, not an exception. Some LWT forms return current column values alongside `false`; **never rely on them as an immutable full-row snapshot**, since returned columns vary by statement and other writers can keep mutating after the response.

### Four-scenario comparison matrix

| Scenario | Both sessions read at T0 | Mutations | Write response | Expected after state |
| --- | --- | --- | --- | --- |
| A — Same cell, differing timestamps | Same `Original` name | B ts300; A ts200 | Both regular UPDATEs can succeed | **B's name** due to higher timestamp |
| B — Two different cells | Same initial name/email | A writes name; B writes email | Two regular UPDATEs | **Both new columns** preserved |
| C — Writing whole stale object | Same initial name/email | A edits email; B writes name + old email at higher ts | Two regular UPDATEs | **A's email is lost** |
| D — CAS on same revision | Same revision 1 | A rev1->2; B still IF rev1 | A true; B false per schedule | **A's mutation** applied |

Comparing post-write values is meaningful only when you account for other writers, consistency, and timestamps. Never treat a read from one replica at one instant as proof that **every replica** has converged.

## 9. Two sessions across replicas: read consistency and write consistency

Cassandra replicates partitions across nodes per the keyspace's replication factor and strategy. Two `cqlsh` sessions may connect to **different coordinators** while still targeting the **same partition key**. Observed results depend on which replicas received each mutation and each request's consistency level.

### Example RF=3 keyspace

| Setting | Basic meaning | Limit to remember |
| --- | --- | --- |
| Write `ONE` | Can succeed with one eligible replica ack | Other replicas may lag behind |
| Write `QUORUM` | With RF=3, typically needs 2 acks | Does not mean all replicas received the write |
| Read `ONE` | Reads from one replica | Can observe stale versions under lagging conditions |
| Read `QUORUM` | With RF=3, reads from a quorum | Improves chance of seeing quorum-completed writes, still subject to timestamps/concurrency |
| LWT `SERIAL`/`LOCAL_SERIAL` | Consensus scope for condition handling | Raising write consistency cannot replace `IF` |

With RF=3, quorum reads and quorum writes overlap at a replica, achieving strong consistency in scenarios with **no competing writers**, valid clocks/timestamps, and matching assumptions. Still, when two mutations hit the same cell with differing timestamps, timestamp reconciliation still decides the winner. **`QUORUM` does not enforce "whoever read first gets to write first."**

### Why can two SELECT sessions see different results?

If A reads at `ONE` right after a write acknowledged at `ONE`, while B reads from a replica that has not yet received the mutation, their outputs can differ. That is a **replica visibility** issue, distinct from a *lost update* caused by two writers overwriting the same cell.

To diagnose lab discrepancies:

1. Verify A and B hit the same cluster and keyspace.
2. Record each session's consistency level.
3. Check whether writes were acknowledged or timed out.
4. Check keys and write timestamps, not just typing order.
5. Re-read at an agreed consistency level rather than reading at `ONE` and assuming cluster-wide convergence.

### LWT requires serial consistency

`IF` mutations use Paxos-style consensus. Alongside the mutation's regular consistency, there is **serial consistency** such as `SERIAL` or `LOCAL_SERIAL`. In multi-datacenter clusters, pick based on topology and where clients issue CAS calls.

Never arbitrarily mix `SERIAL` and `LOCAL_SERIAL` across competing CAS writes on the same data without a cohesive multi-region consistency policy. A single-cluster lab does not validate multi-datacenter assumptions.

### Never equate read-before-write with LWT

When two sessions run:

```text
SELECT revision -> 1
... client processes input ...
UPDATE ... SET revision = 2
```

**SELECT and UPDATE are two separate requests**. No isolation prevents another client from changing revision in between. Only:

```sql
UPDATE demo.profile_concurrency_lab
SET revision = 2
WHERE profile_id = 44444444-4444-4444-8444-444444444444
IF revision = 1;
```

checks revision when deciding the mutation; and **do not run this standalone statement** right after scenario D if you want to preserve that lab's state. In real applications, when updating state, **state changes and revision increments must belong to the same mutation** so revision never bumps without the business change.

## 10. Retries, timeouts, and two interleaved sessions

A request can be accepted by the cluster while **its response fails to reach the client** due to network faults or a coordinator timeout. Therefore:

- A timeout on a regular `UPDATE` **does not** prove the mutation never reached replicas.
- A timeout on `UPDATE ... IF` **is not** equivalent to `[applied] = false`.
- Retrying a regular `UPDATE` with a new timestamp can overwrite a version another client wrote in between attempts.
- Retrying a CAS after an earlier attempt succeeded can return `[applied] = false` because revision already incremented. Never treat that `false` as definite proof "someone else won."

### Timeout example for A

```text
T0: profile revision=1
A:  UPDATE ... SET state='REVIEW', revision=2 IF revision=1
    -> cluster applies it, but true response is lost
B:  SELECT sees revision=2
A:  retries exact same CAS IF revision=1
    -> receives false
```

The retry's `false` **does not tell you** A's first attempt failed. To identify the effect of a logical request, store a **stable request ID** with the mutation and reconcile, or design a verified idempotent workflow.

### API handling rules

| Outcome | Correct interpretation | Handling |
| --- | --- | --- |
| Regular UPDATE acknowledged | Mutation met required consistency | Do not fabricate row counts or conflict-free flags |
| LWT `[applied] = true` | Condition held, mutation applied | Return success |
| LWT `[applied] = false` | Condition failed during this check | Re-read state, handle conflict / unmet precondition |
| Timeout / unknown outcome | Partial or full effect may have occurred | Do not infer false; reconcile and retry safely |
| Validation error before valid mutation | Request needs fixing | Do not blindly retry invalid input |

If an API must return `409 Conflict` or `412 Precondition Failed` for stale CAS writes, base it on **`[applied] = false`** per your contract—never turn a timeout exception into a fake conflict.

## 11. Java Driver 4.x: two logical writers sending CAS concurrently

In Java applications, two independent sessions can be two HTTP requests, two service instances, or two threads. **Apache Cassandra Java Driver 4.x**'s `CqlSession` is designed to be shared across requests; do not open a new TCP connection per writer. What must be kept separate are **each request's inputs, expected revision, and result**.

### 11.1. CAS prepared statement

```java
PreparedStatement cas = session.prepare(
    "UPDATE demo.profile_concurrency_lab " +
    "SET account_state = :next_state, " +
    "    revision = :next_revision, " +
    "    modified_by = :author " +
    "WHERE profile_id = :profile_id " +
    "IF revision = :expected_revision"
);

BoundStatement fromA = cas.boundStatementBuilder()
    .setUuid("profile_id", profileId)
    .setString("next_state", "REVIEW")
    .setInt("next_revision", 2)
    .setString("author", "A")
    .setInt("expected_revision", 1)
    .build();

BoundStatement fromB = cas.boundStatementBuilder()
    .setUuid("profile_id", profileId)
    .setString("next_state", "APPROVED")
    .setInt("next_revision", 2)
    .setString("author", "B")
    .setInt("expected_revision", 1)
    .build();
```

Both `BoundStatement`s **differ in desired state** while sharing `profile_id` and `expected_revision = 1`. The Java Driver binds typed values, while LWT evaluates the condition on the cluster. There is no need to issue a `SELECT` in Java right before every CAS when the client already holds a trusted revision and handles conflicts properly.

### 11.2. Simulating concurrent A/B with CountDownLatch

The example below uses a **non-existent lab row** and two Java tasks released nearly simultaneously. Cassandra's consensus decides the winner; `CountDownLatch` merely helps both clients **start sending around the same time**, without forcing requests to reach nodes in the same microsecond.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class CasRaceDemo {
    public static void run(CqlSession session) throws Exception {
        UUID id = UUID.fromString(
            "88888888-8888-4888-8888-888888888888");

        ResultSet created = session.execute(
            SimpleStatement.newInstance(
                "INSERT INTO demo.profile_concurrency_lab " +
                "(profile_id, account_state, revision) " +
                "VALUES (?, ?, ?) IF NOT EXISTS",
                id, "PENDING", 1
            )
        );
        if (!created.wasApplied()) {
            throw new IllegalStateException(
                "Lab ID already exists; use a fresh key for this run");
        }

        PreparedStatement cas = session.prepare(
            "UPDATE demo.profile_concurrency_lab " +
            "SET account_state = :next_state, " +
            "revision = 2, modified_by = :author " +
            "WHERE profile_id = :profile_id IF revision = 1"
        );

        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Boolean> a = pool.submit(() -> {
                start.await();
                BoundStatement stmt = cas.boundStatementBuilder()
                    .setUuid("profile_id", id)
                    .setString("next_state", "REVIEW")
                    .setString("author", "A")
                    .build();
                return session.execute(stmt).wasApplied();
            });

            Future<Boolean> b = pool.submit(() -> {
                start.await();
                BoundStatement stmt = cas.boundStatementBuilder()
                    .setUuid("profile_id", id)
                    .setString("next_state", "APPROVED")
                    .setString("author", "B")
                    .build();
                return session.execute(stmt).wasApplied();
            });

            start.countDown();
            boolean aApplied = a.get();
            boolean bApplied = b.get();

            System.out.printf(
                "A applied=%s; B applied=%s%n", aApplied, bApplied);

            if (aApplied == bApplied) {
                throw new IllegalStateException(
                    "Result did not match expected 1 true / 1 false");
            }
        } finally {
            pool.shutdown();
        }
    }
}
```

On a fresh row with no third writer and **neither call throwing an exception**, the expectation is **one `true` and one `false`**. Never hardcode "A always wins": the actual winner can swap from run to run.

If `Future.get()` throws an exception due to a timeout or driver failure, the code **does not** have both booleans to declare a winner. Handle the uncertain outcome branch separately, inspecting stored state and request IDs; **never catch exceptions and return `false`**.

### 11.3. Reading after both CAS calls

```java
PreparedStatement inspect = session.prepare(
    "SELECT account_state, revision, modified_by " +
    "FROM demo.profile_concurrency_lab WHERE profile_id = ?"
);

Row current = session.execute(inspect.bind(profileId)).one();
if (current != null) {
    String state = current.getString("account_state");
    int revision = current.getInt("revision");
    String writer = current.getString("modified_by");
    // state/author must match the writer that was applied;
    // expected revision = 2 if exactly one CAS succeeded.
}
```

`Row` is `com.datastax.oss.driver.api.core.cql.Row`. The `profileId` here must be **the exact UUID of the row just tested**, not `cqlsh`'s `4444...` key if you are inspecting Java's `8888...` row.

### 11.4. Enforcing expected revision from an HTTP API

A `PATCH /profiles/{id}` endpoint can accept a version number such as `expectedRevision = 12`. The application:

1. Validates the caller is authorized to edit `profile_id`.
2. Extracts only the fields actually changed plus valid new state.
3. Computes `nextRevision = expectedRevision + 1` with overflow checking.
4. Sends `UPDATE ... SET changed_fields, revision = nextRevision ... IF revision = expectedRevision`.
5. If `wasApplied()` is true, returns success; if false, returns `409 Conflict` or `412 Precondition Failed` per contract.
6. On timeout, never turns it into false; returns an appropriate error status and provides reconciliation.

When an API accepts optional fields, distinguish **absent columns**, **UNSET**, and **NULL**:

```java
// Prepared statement has markers :display_name and :contact_email.
// If the client only requested changing the name:
BoundStatementBuilder builder = prepared.boundStatementBuilder()
    .setUuid("profile_id", profileId)
    .setString("display_name", "New Name")
    .unset("contact_email");

// Do not use setToNull("contact_email") to represent an absent field:
// NULL is a deletion mutation; UNSET skips that field.
```

`BoundStatementBuilder` is `com.datastax.oss.driver.api.core.cql.BoundStatementBuilder`. This snippet illustrates only marker semantics declared in `prepared`; for a real CAS, the CQL must include `IF revision = ...` and its corresponding markers. Never execute a prepared statement without binding required key and revision markers.

## 12. DELETE and new writes can contend too

This chapter covers both **CQL writes and deletes**. If A deletes a row while B writes back to the same full primary key, Cassandra still reconciles the **tombstone** and the new version by timestamp.

### Demonstration on a dedicated key with controlled timestamps

```sql
-- Initialize separately for DELETE vs UPDATE scenario.
INSERT INTO demo.profile_concurrency_lab (
    profile_id, display_name, account_state, revision
) VALUES (
    77777777-7777-4777-8777-777777777777,
    'Before Delete', 'ACTIVE', 1
)
USING TIMESTAMP 1700000000002100;

-- A deletes the entire row with a newer timestamp.
DELETE FROM demo.profile_concurrency_lab
USING TIMESTAMP 1700000000002200
WHERE profile_id = 77777777-7777-4777-8777-777777777777;

-- B writes to the same key with an even newer timestamp.
UPDATE demo.profile_concurrency_lab
USING TIMESTAMP 1700000000002300
SET display_name = 'Recreated by B'
WHERE profile_id = 77777777-7777-4777-8777-777777777777;

SELECT display_name, account_state, revision
FROM demo.profile_concurrency_lab
WHERE profile_id = 77777777-7777-4777-8777-777777777777;
```

With fresh lab data and no other writers, after DELETE the old values are shadowed by the tombstone. When B writes the `display_name` cell with a timestamp **newer than the row tombstone**, the new value appears; the old `account_state` and `revision` **do not automatically return** just because B rewrote one cell.

**DELETE does not create a rule that "this key is permanently banned from reuse."** If business logic requires prohibiting recreation of deleted resources, use a business state/tombstone or dedicated creation guard rather than relying solely on a data deletion command.

### When is DELETE IF EXISTS insufficient?

`DELETE ... IF EXISTS` checks whether the row exists before deleting. It does not prevent another writer from upserting the row afterward. If the goal is transitioning `ACTIVE -> DELETED` and blocking recreation, a **soft-delete model with revision/conditions** or a separate claim/retention key is often more suitable than a plain physical delete. Align GDPR/retention/backup requirements per business policy rather than assuming soft delete replaces real erasure.

## 13. Comprehensive lab: comparing two sessions with a results table

To self-assess, run scenarios A–D **one scenario at a time** on your lab cluster. After every mutation, record **the response from the terminal that sent it** before recording **the SELECT output**. Never skip the initial reads in both A and B.

### Step 1 — Verify both sessions

Verify A and B share `demo.profile_concurrency_lab`. Record each session's consistency level. Never use production tables or keys actively used by other programs.

### Step 2 — Capture initial state

For each lab UUID, both A and B run:

```sql
SELECT display_name, contact_email, account_state,
       revision, modified_by
FROM demo.profile_concurrency_lab
WHERE profile_id = 44444444-4444-4444-8444-444444444444;
```

This query is for scenario D; swap in the UUID for whichever scenario you are testing. Record the values **before either session sends an UPDATE**. If A and B already disagree at T0, stop before drawing conclusions about writer contention; inspect consistency, seed data, and replica state.

### Step 3 — Execute the prescribed A/B schedule

- **Scenario A:** B writes the same column with timestamp 0300, then A writes with 0200.
- **Scenario B:** A writes only `display_name`; B writes only `contact_email`.
- **Scenario C:** A writes new email ts1200; B writes new name **and old email** ts1300.
- **Scenario D:** A sends `IF revision=1` first; after `true`, B sends `IF revision=1`.

Do not swap T1/T2 order if you want to verify against the expected results table. When deliberately running A and B truly in parallel, the winner is an observed variable, **not a fixed constant**.

### Step 4 — Record actual responses instead of guessing

For regular `UPDATE`s, record **success / timeout / error** as seen by the terminal; never invent a `rowsAffected` column. For LWT, record the exact `[applied]` value:

| Command | What to record in the lab notebook? |
| --- | --- |
| A's regular UPDATE | Success or exception, timestamp used |
| B's regular UPDATE | Success or exception, timestamp used |
| A's CAS | `[applied] = true/false` or timeout |
| B's CAS | `[applied] = true/false` or timeout |
| Post-write SELECT | Observed values and consistency level |

If a request times out, **never fill in the table as if it succeeded**. Mark the outcome unknown and follow the timeout guidance in section 10.

### Step 5 — Re-read from both sessions

Example for the timestamp scenario:

```sql
SELECT display_name,
       WRITETIME(display_name),
       contact_email,
       WRITETIME(contact_email),
       revision
FROM demo.profile_concurrency_lab
WHERE profile_id = 11111111-1111-4111-8111-111111111111;
```

`WRITETIME` measures the write timestamp of **the cell currently observed** in microseconds since the Unix epoch. It does not prove request submission order when timestamps are chosen manually, nor does it identify the author unless you store separate business metadata.

### Step 6 — Compare before and after

| Test | Key expectation | Explanation |
| --- | --- | --- |
| A | Even though A wrote later, B's name wins | B's timestamp is higher; not by typing order |
| B | A's new name + B's new email both survive | Two mutations touched two different cells |
| C | Email reverts to old value | B sent the old email with a higher write timestamp |
| D | A true, B false under A-then-B schedule | LWT applies only mutations whose revision still matches |

### Step 7 — Intentionally vary one lab parameter

Try one of the following variations **on a fresh lab key**:

1. Reverse A/B submission order while keeping scenario A's **write timestamps**: the higher-timestamp version still wins once all mutations are visible.
2. Remove `contact_email` from B's `SET` in scenario C: A's new email is no longer overwritten by B.
3. Replace `IF revision = 1` with `IF EXISTS` on two name updates: the existence check does not stop two clients from sequentially overwriting the same cell.
4. Run two CAS calls truly concurrently: **who wins can vary**, yet once both receive clear results, at most one mutation from the same revision applies.

Never re-run manual timestamps on **the CAS row**. Never combine `USING TIMESTAMP` with `IF`: CQL rejects that combination.

### Step 8 — Write evidence-based conclusions

A solid lab report must state:

- Which **full primary key** was targeted, and whether both sessions used the exact same key.
- What data each session read at T0.
- Whether each session wrote a single field or the entire object.
- Whether custom write timestamps were used.
- Whether mutations were standard or LWT.
- Whether responses were acknowledgments, `[applied]`, or timeouts.
- Whether `SELECT` outputs from A and B matched, and at which consistency level.
- Which evidence supports conclusions about **lost updates**, **cell merging**, or **CAS conflicts**.

Never write simply "A won" or "B lost" without citing timestamps, conditions, and keys; such summaries fail to explain correctness when topology or submission patterns change.

## 14. Common mistakes when two clients update concurrently

| Misconception | Why it is wrong | Correct approach |
| --- | --- | --- |
| "The last UPDATE sent always wins" | Cassandra reconciles by per-cell write timestamp | Inspect `WRITETIME` and timestamp sources |
| "Both succeeded, so both names were kept" | Two values contend on the same cell | Identify the live version; use CAS to detect conflicts |
| "Revision auto-increments on every UPDATE" | `revision` is an app-maintained regular column | Increment inside the same CAS checking old revision |
| "SELECT then regular UPDATE is atomic" | Another client can write between the two requests | `UPDATE ... IF revision = old` |
| "IF EXISTS acts as CAS on old name" | Checks existence only, not old values | Use `IF revision = old` or `IF col = expected` |
| "Two different fields always require LWT" | Independent cell mutations can both survive | Reserve LWT for cross-field/row invariants |
| "Writing the full object equals PATCHing one field" | Resending old fields can clobber another writer's update | Write only fields that actually changed |
| "Omitting a field from JSON equals NULL" | `NULL` deletes the value via tombstone | Omit column / bind `UNSET` for no-op |
| "QUORUM prevents lost updates" | Quorum governs replica acks, not revision checks | Enforce business preconditions via LWT |
| "applied=false is a network error" | Unmet condition is a normal LWT result | Separate conflicts from exceptions |
| "Timeout proves the mutation failed" | Cluster may have applied it with a lost response | Reconcile request ID/state, retry carefully |
| "False on CAS retry proves another writer won" | Client's own earlier CAS may have succeeded | Identify logical requests and inspect state |
| "USING TIMESTAMP protects CAS" | Custom timestamps cannot be used with LWT | Let LWT manage timestamps |
| "Two cqlsh shells on two nodes mean two partitions" | Partitions are determined by **partition key**, not client node | Verify full primary key and token mapping |
| "Write success means every replica is synced" | Consistency level only requires a subset of acks | Monitor replicas/repair and read at proper CL |
| "DELETE permanently blocks reusing the key" | New writes beating the tombstone timestamp can appear | Use business state/conditions to block recreation |
| "Multi-mutation BATCH replaces CAS" | Logged batches lack SQL read-modify-write isolation | Use LWT on supported partitions; workflows across partitions |

## 15. Self-check questions and application checklist

### Questions

1. **Why did B win in scenario A even though A sent later?** Because B's write timestamp was higher than A's on the same cell.
2. **What does `WRITETIME(display_name)` measure?** The write timestamp of the `display_name` cell currently read, in microseconds since Unix epoch; not a full request log.
3. **Do two sessions editing two different columns inevitably lose updates?** No. When each mutation writes only its target column and wins at its cell, both changes coexist.
4. **Why did B wipe out A's new email in scenario C?** Because B sent the stale email in a new mutation carrying a higher timestamp.
5. **Do regular `UPDATE`s check row existence and revisions?** No, unless the matching `IF` condition is added.
6. **Does `IF EXISTS` stop two users from changing the name on an existing row?** No; both existence checks can evaluate to true.
7. **What does `IF revision = 1` solve?** It applies the mutation only if revision is still 1 when LWT evaluates; otherwise it returns false.
8. **Why must revision be incremented in the same mutation?** Checking without incrementing lets a subsequent writer satisfy the exact same condition.
9. **If A and B run CAS truly in parallel, can you guarantee A always wins?** No. Consensus scheduling decides the winner; for two competing requests with the same expected revision that both increment it, at most one applies.
10. **Is `[applied] = false` a row count of 0?** No. It means the LWT condition was not met, not how many rows changed.
11. **Do QUORUM reads and QUORUM writes automatically form a SQL transaction?** No; replica consistency is distinct from business conditions/transactions.
12. **Does a timeout after CAS mean `[applied] = false`?** No. The mutation may have applied while the response was lost.
13. **After a row is DELETEd, can another client still write to the same key?** Yes, if the new mutation beats the tombstone's timestamp.
14. **Why must both A and B read at T0?** To verify both writers actually started from the same state and interpret contention accurately.
15. **Which Java API checks CAS conflicts?** `ResultSet.wasApplied()` for `IF` statements; exceptions and timeouts must be handled separately.

### Pre-production checklist

1. **Keys and scope:** do all writers use the exact same full primary key for the same entity?
2. **Request semantics:** standard upsert, per-field PATCH, full-object replace, or revision-based CAS?
3. **Prior reads:** when old state must be compared, is the condition enforced inside the mutation via `IF`?
4. **Revisions:** incremented in the same mutation, enforced across all related write paths, and overflow-checked?
5. **Timestamps:** uniform timestamp source, avoiding stale/future manual timestamps and clock skew?
6. **Replica consistency:** do write/read CLs, RF, and topology match what must be observed?
7. **LWT consistency:** appropriate serial consistency chosen without mixing cross-region CAS haphazardly?
8. **Retries:** on timeouts, does code track logical requests and uncertain states?
9. **Outcomes:** does the application separate regular write success, `[applied]` false, and exceptions?
10. **Payloads:** are absent columns protected from being mapped to `NULL` or overwriting with stale values?
11. **Practical testing:** have two sessions reading T0, writing T1/T2, verifying T3, and handling network faults been tested in a lab?
12. **Observability:** are logical keys, revisions, request IDs, latencies, and conflict types logged safely without leaking private data?

**Takeaway:** To understand two concurrent update sessions in Cassandra, **record initial state**, identify **the full primary key and exact mutations sent by each session**, separate **write timestamps** from request submission times, and **read post-write state** at a known consistency level. Updates to separate cells can coexist; writing back whole stale objects causes lost updates; competing writes to the same cell resolve by timestamp. Whenever stale writers must be blocked from overwriting newer state, use **`IF revision = expected` and increment revision inside the same LWT**, inspect `[applied]`, and handle timeouts/idempotency separately. That is the foundation for using distributed Cassandra with both proper consistency and business correctness in Java applications.
