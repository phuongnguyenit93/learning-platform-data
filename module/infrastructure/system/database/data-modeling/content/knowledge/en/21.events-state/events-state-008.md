# State Snapshots to Support Replaying Long Histories

## 1. The Problem: As History Grows, Loading State Gets More Expensive

In an **event sourcing** model, an entity's current state is usually constructed by reading its accepted events in exact order and applying a state-transition function. For an equipment rental contract, the event stream might start with `RentalStarted` and continue through thousands of extensions, fee assessments, payments, adjustments, and inspections.

If every command handler always reads the entire stream starting from event 1, cost scales linearly with history length:

~~~text
Without a snapshot:
initial_state
  + event 1 + event 2 + ... + event 9,998 + event 9,999 + event 10,000
  = current_state@version 10,000
~~~

This is acceptable for a few dozen events, yet quickly increases read latency, I/O volume, and transition work when aggregates accumulate long histories.

A **snapshot** is a **derived state copy at a specific version of an event stream**. When reloading state, the system reads the latest compatible snapshot and replays only events occurring after that version:

~~~text
With a snapshot at version 9,500:
snapshot(state@9,500)
  + event 9,501 + ... + event 10,000
  = current_state@version 10,000
~~~

A snapshot is an **optimization for reading long histories**, not a new event and not a second source of truth. To design and use snapshots properly, define aggregate boundaries, stream version, state content, format compatibility, concurrent-write conditions, and fallback recovery when a snapshot is unusable.

## 2. Distinguishing Snapshots, Events, Projections, and Backups

Terms like “snapshot” and “state” are easily confused in data modeling:

| Concept | Data represented | Role | Rebuildable from events? |
| --- | --- | --- | --- |
| **Domain event** | An accepted business fact, e.g., `DepositCaptured`. | Source of truth in event sourcing. | Not disposable derived data; original history must be protected. |
| **Aggregate snapshot** | State of **one aggregate at stream version N**. | Reduces number of events replayed when loading the aggregate. | Yes, if historical events and interpretation logic remain intact. |
| **Projection/read model** | Query-serving table or document such as `rental_current`. | Fast reads tailored to UI/report queries. | Yes, if event source and projection rules remain intact. |
| **Projection checkpoint** | Position up to which a projector has processed. | Resume after failures; avoid duplicate application. | Process metadata; must coordinate with derived state for safe recovery. |
| **Database backup/snapshot** | Copy of data or storage state at a technical point in time. | Infrastructure recovery; disaster protection. | Cannot be replaced by aggregate snapshots, as purpose and scope differ. |
| **CDC initial snapshot** | Existing rows read to bootstrap a change-sync pipeline. | Loads pre-existing data for downstream consumers. | Does not mean business events just occurred when the snapshot ran. |

A `rental_current` table might hold the exact same fields as an aggregate snapshot, yet its lifecycle and purpose usually differ: the current-state table updates continuously on new events to answer queries; a snapshot stays anchored at **an immutable version of logical state** and serves as a starting point for subsequent replay.

In systems storing only **state + audit log**, periodic state copies may be saved for backup or auditing. However, do not casually call them event-sourcing snapshots: if the audit log lacks enough semantics to rebuild state, there is no guarantee of independent replay from the log.

## 3. Running Example: Snapshot for an Equipment Rental Contract

Consider the `Rental` aggregate with ID `RENT-204`. A simple history:

| stream_version | Event | Accepted change |
| ---: | --- | --- |
| 1 | `RentalStarted` | Equipment rented, due back at 10:00, deposit 200,000 VND. |
| 2 | `DepositCaptured` | Successfully captured 200,000 VND. |
| 3 | `RentalDueDateExtended` | Due time validly extended to 11:00. |
| 4 | `EquipmentDroppedOff` | Customer handed over equipment at kiosk. |
| 5 | `EquipmentReturnAccepted` | Staff confirmed inspection passed. |
| 6 | `DepositRefundRequested` | Refund request recorded; **not** yet counted as refunded. |
| 7 | `DepositRefundConfirmed` | Payment source confirmed refunding 200,000 VND. |
| 8 | `RentalClosed` | Contract closed once obligations completed. |

Suppose after applying event version 5, the system creates a snapshot:

~~~json
{
  "snapshot_schema_version": 2,
  "reducer_version": "rental-state-v2",
  "aggregate_type": "Rental",
  "aggregate_id": "RENT-204",
  "stream_version": 5,
  "state": {
    "rental_status": "RETURN_ACCEPTED",
    "payment_status": "PAID",
    "currency": "VND",
    "deposit_captured_minor": 200000,
    "deposit_refunded_minor": 0,
    "due_at": "2026-11-20T04:00:00Z",
    "equipment_return_accepted": true
  }
}
~~~

This snapshot **includes only events 1–5** and accurately reflects state at version 5. When loading state at version 8:

1. Read snapshot version 5, validate format and origin.
2. Apply `DepositRefundRequested` version 6; refunded amount remains 0.
3. Apply `DepositRefundConfirmed` version 7; refunded amount becomes 200,000.
4. Apply `RentalClosed` version 8; contract status transitions to `CLOSED`.

The final result matches replaying all 8 events, while applying only three events after the snapshot. If you need **state at version 4**, you cannot take snapshot version 5 and “rewind” by arbitrarily subtracting one event; pick a snapshot with version **less than or equal to 4**, or replay from the beginning.

**Monetary note:** `deposit_captured_minor` and `deposit_refunded_minor` use integers per `currency` minor-unit rules. `DepositRefundRequested` must not add to `deposit_refunded_minor` because a request does not prove actual cash refund completion.

## 4. Which Fields Must a Snapshot Contain?

A trustworthy snapshot must answer “whose state is this, after which event, and under which interpretation?”. A minimal design should include:

| Field | Meaning and requirement |
| --- | --- |
| `tenant_id` (if multi-tenant) | Ownership and isolation scope, especially when IDs collide across tenants. |
| `aggregate_type`, `aggregate_id` | Identifies the exact stream. |
| `stream_version` | **Last applied** version used to build this state; not the latest stream version at write time. |
| `snapshot_schema_version` | How to decode/deserialize the stored state structure. |
| `reducer_version` or `state_model_version` | Semantic version of state-building logic; detects snapshots incompatible with current replay logic. |
| `state` | Complete state required to continue applying events within the aggregate boundary. |
| `created_at` | When the snapshot was persisted to storage; operational metadata, not a substitute for stream version. |
| `checksum`/digest (optional) | Helps detect corrupted snapshot data or encoding; requires standardized serialization/hashing rules. |
| `last_event_id` (optional) | Cross-checks which event produced the snapshot at the stated version. |

For a **state-building** snapshot, the data must suffice to interpret subsequent events accurately. If rules after version 5 need the list of captured `payment_id`s to prevent duplicates, storing only the total amount is insufficient; keep the required IDs or ensure the writer enforces deduplication consistently through another store. Likewise, a snapshot storing total `100` cannot replace detailed history if subsequent logic needs to identify **which specific fee** is being reversed.

Commonly misused fields:

- `created_at` **does not** indicate the snapshot includes the latest event; snapshot version 80 may finish writing to disk after snapshot version 100 due to async worker lag.
- `stream_version` is **not** `schema_version`: stream version 10,000 may contain event schema v1, v2, and v3.
- Event `recorded_at` is not apply order; replay follows **the logical order committed by the store within the stream**.
- `reducer_version` is useful only with a defined compatibility policy. Refactoring code without changing semantics does not necessarily invalidate snapshots; changing state-calculation rules can invalidate old snapshots even though JSON still parses cleanly.

## 5. Algorithm for Loading State From a Snapshot and Event Tail

The goal is to load aggregate state at **target version T** with the exact same outcome as replaying from event 1. Illustrative algorithm:

~~~text
load_state(stream_key, target_version=T, expected_reducer):
    snapshot = find_latest_compatible_snapshot(
        stream_key=stream_key,
        reducer=expected_reducer,
        snapshot_version <= T
    )

    if snapshot is valid:
        state = deserialize_and_validate(snapshot.state)
        v = snapshot.stream_version
    else:
        state = initial_state()
        v = 0

    events = load_events(
        stream_key=stream_key,
        version > v AND version <= T,
        order_by=stream_version
    )

    for event in events:
        require event.stream_version == v + 1
        state = apply(state, upcast_event_if_needed(event))
        v = event.stream_version

    require v == T
    return (state, version=T)
~~~

**Four non-negotiable conditions:**

1. **Select a snapshot from the right stream** and compatible with current processing logic; never mix snapshots across tenants or aggregates.
2. **Select only snapshots with version ≤ T.** To build state at version 50, a version 80 snapshot is data “from the future”.
3. **Read all events after the snapshot in contiguous version order.** Never skip version 51 and apply 52; a missing event must halt and trigger recovery.
4. **Keep `apply` deterministic.** Never call refund APIs, send emails, read wall-clock time, or look up mutable price tables to re-decide history.

If the latest snapshot is invalid, try an older **compatible** snapshot or replay from the beginning. If early history was purged, “fallback replay from scratch” may be impossible; document limits explicitly and design separate recovery plans.

### Reading While the Stream Keeps Receiving New Events

Suppose the system processes a new command while the stream is at version 200. While loading snapshot 180 and events 181–200, another writer might append 201. Safe handling:

- Obtain **target version 200** from a committed source under the guarantee that events 1–200 are atomically appended per stream.
- Read a snapshot ≤ 200 and events strictly up to 200, without accidentally mixing 201 into the same state load.
- When appending the new event, specify **expected version 200** inside the transaction. If another writer already moved the stream to 201, the command hits a conflict and re-evaluates against the newer state.

Using snapshots for speed never replaces concurrency control. Snapshots build state from history; **expected-version checks** protect decisions under concurrent writers.

## 6. Creating Snapshots Safely While the System Is Still Writing

**When to snapshot** can be every N events, when state-load latency crosses a threshold, or on a schedule. Regardless of trigger, the snapshot must represent **exact state at the version stamped on the record**.

### Option A: Create Synchronously Inside the Append Transaction

During command processing, the system already holds the new state and knows the latest appended version. Writing the event and snapshot can be serialized inside the same event-store transaction.

Advantage: trivial to bind state and committed version. Trade-off: serializing/compressing snapshots lengthens transactions, increasing contention and write latency. Use only when snapshots are lightweight and taken at sensible intervals.

### Option B: Create Asynchronously After Commit

An independent worker:

1. Receives a job to snapshot stream `Rental/RENT-204` at version **N = 500**.
2. Builds state from an earlier snapshot and events **strictly up to N**, or from a state proven to be at version N.
3. Serializes/validates state with reducer version and stamps `stream_version = 500`.
4. Stores the snapshot with a unique key on stream, reducer, and version.
5. Even if the stream reached version 530 by write completion, the snapshot **remains version 500**. It cleanly supports replaying 501–530 afterward.

~~~mermaid
flowchart LR
    E[("Event stream at version 500")] --> T["Request snapshot@500"]
    T --> R["Replay strictly up to version 500"]
    R --> S["Serialize state + reducer version"]
    S --> W[("Save snapshot@500")]
    E --> N["Writers append 501..530"]
    W --> L["Next read picks suitable snapshot then replays tail"]
    N --> L
~~~

**Common bug:** the worker loads state at version 500, finishes computing, then reads `current_version = 530` and stamps the snapshot as `snapshot@530`. On subsequent loads, the system skips events 501–530 even though state never applied them. That is **logical data loss** even while the event store remains intact.

### Multiple Workers Snapshotting the Same Stream

Two workers may snapshot versions 500 and 600, with the version 500 worker finishing later. If the system keeps only one `latest_snapshot` slot with unconditional overwrites, the older snapshot can overwrite the newer one. Storing by **stream + version key** and querying `MAX(stream_version)` meeting compatibility rules prevents completion-time race errors. If storing only one snapshot, use a conditional update “replace only if new version exceeds existing version”, along with handling reducer-version changes.

**Snapshots are derived data:** older snapshots can be pruned under a proper retention policy as long as original history remains sufficient to recover and active read paths are unaffected.

## 7. Example PostgreSQL Schema for Events and Snapshots

The design below uses a shared multi-aggregate schema with tenant keys. Stream management holds the latest accepted version; event store holds history; snapshot holds derived state. This is a structural example, not a complete authorization or domain-validation specification.

~~~sql
CREATE TABLE event_stream (
    tenant_id        UUID NOT NULL,
    aggregate_type   VARCHAR(80) NOT NULL,
    aggregate_id     VARCHAR(100) NOT NULL,
    current_version  BIGINT NOT NULL DEFAULT 0
                     CHECK (current_version >= 0),
    PRIMARY KEY (tenant_id, aggregate_type, aggregate_id)
);

CREATE TABLE event_store (
    event_id         UUID PRIMARY KEY,
    tenant_id        UUID NOT NULL,
    aggregate_type   VARCHAR(80) NOT NULL,
    aggregate_id     VARCHAR(100) NOT NULL,
    stream_version   BIGINT NOT NULL CHECK (stream_version > 0),
    event_type       VARCHAR(100) NOT NULL,
    event_schema_version SMALLINT NOT NULL
                         CHECK (event_schema_version > 0),
    occurred_at      TIMESTAMPTZ NOT NULL,
    recorded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload          JSONB NOT NULL
                     CHECK (jsonb_typeof(payload) = 'object'),
    FOREIGN KEY (tenant_id, aggregate_type, aggregate_id)
        REFERENCES event_stream
        (tenant_id, aggregate_type, aggregate_id),
    UNIQUE (tenant_id, aggregate_type, aggregate_id, stream_version)
);

CREATE TABLE aggregate_snapshot (
    tenant_id        UUID NOT NULL,
    aggregate_type   VARCHAR(80) NOT NULL,
    aggregate_id     VARCHAR(100) NOT NULL,
    reducer_version  VARCHAR(80) NOT NULL,
    stream_version   BIGINT NOT NULL CHECK (stream_version > 0),
    snapshot_schema_version SMALLINT NOT NULL
                            CHECK (snapshot_schema_version > 0),
    state            JSONB NOT NULL
                     CHECK (jsonb_typeof(state) = 'object'),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (
        tenant_id, aggregate_type, aggregate_id,
        reducer_version, stream_version
    ),
    FOREIGN KEY (tenant_id, aggregate_type, aggregate_id)
        REFERENCES event_stream
        (tenant_id, aggregate_type, aggregate_id)
);
~~~

**Schema constraints and limitations:**

- The snapshot key permits multiple snapshots across versions while preventing two snapshots with the same **stream + reducer + version**. Key column order aligns with finding the latest compatible snapshot.
- **`event_store.stream_version`** is unique per stream; contiguous increments and synchronization with `current_version` must be enforced by the append transaction.
- The foreign key from snapshot to stream ensures the stream exists; it **does not** prove snapshot version N was actually built from all events 1–N. That belongs to the snapshotting and verification pipeline.
- The schema does not use `created_at` to determine which snapshot is “state-latest”. Within a given reducer, `stream_version` alone decides.
- If state is large or contains sensitive data, consider storing compressed/encrypted snapshots in external object storage while keeping metadata and checksums in the table. Define sync, access control, and handling for missing or undecryptable files.
- Do not add indexes across arbitrary fields inside `state JSONB` by default, since this table's primary job is **loading by stream + version**, not ad-hoc business queries. Screen queries belong on dedicated read models.

### Query to Find the Latest Compatible Snapshot

~~~sql
SELECT stream_version, snapshot_schema_version,
       reducer_version, state
FROM aggregate_snapshot
WHERE tenant_id = :tenant_id
  AND aggregate_type = 'Rental'
  AND aggregate_id = :rental_id
  AND reducer_version = :reducer_version
  AND stream_version <= :target_version
ORDER BY stream_version DESC
LIMIT 1;
~~~

The handler must know which `snapshot_schema_version` values it can decode and can filter for compatible schema versions before picking a snapshot. If the chosen snapshot fails decoding or structural checks, fall back to an earlier compatible version or replay from event 1.

Then load the tail:

~~~sql
SELECT event_id, stream_version, event_type,
       event_schema_version, payload
FROM event_store
WHERE tenant_id = :tenant_id
  AND aggregate_type = 'Rental'
  AND aggregate_id = :rental_id
  AND stream_version > :snapshot_version
  AND stream_version <= :target_version
ORDER BY stream_version;
~~~

For streams without snapshots, set `:snapshot_version = 0`. Leading `:` denotes query parameters supplied by the data layer; this is illustrative parameterized SQL. During a state-loading read, `:target_version` should come from a source-consistent rule—such as reading committed `current_version` and not reading past it.

### Writing Snapshots From a Worker

The worker builds state at version N, verifies contiguous events, and writes to `aggregate_snapshot` with the matching `reducer_version` and `snapshot_schema_version`. If two workers write the same key, handle conflict intentionally: compare checksums/states and investigate any discrepancy rather than letting last-write-wins silently prevail. Snapshots regenerated with the same reducer over the same history must produce identical state.

Creating a snapshot **does not** increment `event_stream.current_version`, because it is optimization data rather than a domain event appended to the stream.

## 8. Choosing Snapshot Frequency Based on Performance and Cost

There is no mandatory rule like “snapshot every 100 events”. Start with a sensible threshold, then measure production load.

A rough cost model:

~~~text
Cost to load state with snapshot
    ≈ cost to locate snapshot
    + cost to read and deserialize snapshot
    + tail event count × cost to apply one event
~~~

If a stream has 10,000 events and snapshots every 500 events, the tail from the latest snapshot usually holds at most around 499 events when snapshots keep pace and versions are contiguous. This is **not a latency guarantee**: snapshot size, storage read speed, `apply` complexity, async snapshot lag, and network conditions all matter.

| Strategy | Best suited when | Trade-off |
| --- | --- | --- |
| **Every N events** | Average apply cost is fairly uniform; simple to implement. | Some events may be much heavier than others. |
| **Time-based** | Want periodic snapshots for active streams. | Streams with very few events may be snapshotted unnecessarily. |
| **By replay size/cost** | Event sizes and complexity vary widely. | Requires measurement and more complex trigger logic. |
| **By state-load latency** | Clear read/write SLOs; tune to measured outcomes. | Requires telemetry and threshold tuning mechanisms. |
| **Hybrid threshold + schedule** | Bursty traffic; need to bound both spikes and time since last snapshot. | More conditions to govern and deduplicate. |

**Snapshotting more often is not always faster:** snapshotting every event increases serialization CPU, I/O, storage footprint, contention, and storage cost. Conversely, snapshotting too rarely creates long replays. Measure at minimum:

- P50/P95/P99 aggregate load time; number of events replayed since snapshot.
- Snapshot generation duration and resource usage; snapshot failure rates.
- State size and growth rate per version.
- Frequency of fallbacks due to stale or incompatible snapshots.
- Impact on command latency and event store operational cost.

You can snapshot only **long-lived or frequently accessed** aggregates instead of every stream. A 4-event order likely needs no snapshot; a contract modified thousands of times benefits noticeably.

## 9. Snapshots and Schema or Interpretation Logic Changes

Snapshots store **computed state**, creating at least two independent version axes:

1. **Snapshot schema version**: how state is serialized and deserialized; e.g., changing a single `status` string into separate operational and payment statuses.
2. **Reducer/interpretation version**: meaning of numbers or statuses; e.g., net-refund calculation changing under a new policy.

Do not confuse these two axes with `event_schema_version` of source events or `stream_version` of the aggregate.

Suppose an old snapshot stored:

~~~json
{
  "snapshot_schema_version": 1,
  "state": {
    "status": "CLOSED",
    "refund_amount": 200000
  }
}
~~~

Later, the new model separates `rental_status`, `payment_status`, `deposit_captured_minor`, `deposit_refunded_minor`, and `currency`. Two paths exist:

- **Equivalence-proven snapshot migrator:** transform old state to the new schema if sufficient information exists and old fields are unambiguous. Verify continued event replay after the migrated snapshot.
- **Discard old snapshots and replay source events:** usually safer when logic changes carry semantic impact or old snapshots lack required fields. After replay, generate fresh snapshots under the new reducer version.

If early events were deleted and old snapshots lack enough data to apply the new rules, **you cannot claim a complete rebuild**. Evaluate retention design, storage history, migration rules, and verifiable bounds before deleting events.

### Replaying Old Results vs. Replaying Under New Rules

Two distinct needs exist:

- **Reproducing the state the system originally computed at version N**: requires historical logic or a reducer version compatible with that era.
- **Building a new projection under current definitions**: may use approved new logic, provided semantic shifts are documented and reconciled against source data.

An old snapshot is not proof that a new projection shares the same meaning. Successfully parsing JSON does not prove **business compatibility**.

## 10. Limits of Snapshots When Querying History

A snapshot at version N answers “**what was the state after N events?**”. It does not necessarily answer:

- How many fee adjustments occurred before N?
- How long elapsed between refund request and payment-provider confirmation?
- Who approved each extension?
- What drove state changes step by step?
- What granular facts are needed to rebuild an analytical report under a new definition?

If a snapshot holds only `current_due_at` and `current_balance`, these questions still require **event history** or a separately maintained historical read model. Deleting old events “because we have snapshots” destroys audit capability, temporal analytics, and the ability to fix logic later.

### State “At a Point in Time” Is Not Simply Picking a Snapshot by Date

To reconstruct state **at version T**, pick a snapshot ≤ T and replay up to T. However, knowing “**what state was in effect at 10:00 on day X**” may require rules over:

- `occurred_at`: when the occurrence was confirmed to have happened.
- `recorded_at`: when the system learned and saved it.
- `effective_at`: when a value takes effect per business rules.
- Retroactive adjustment events carrying an old `effective_at` and a new version.

An adjustment event at version 200 may alter a deadline retroactively from an earlier version. Answering both “what did the system know at 10:00?” and “given current knowledge, what was in effect at 10:00?” requires **bitemporal** modeling and queries when the problem demands it. Snapshot@version only shortens replay to a specific progression milestone; it does not resolve those two temporal perspectives by itself.

### Snapshots Across Multiple Aggregates Are Not Globally Consistent

If `Order` is snapshotted at version 10 and `Payment` at version 8 at different moments, the two snapshots do not form a “system-wide snapshot at the same instant”. Cross-service reporting requires synchronization points, guaranteed source cursors/watermarks, or coordinated source queries. Never use individual aggregate snapshot creation times to claim a consistent distributed transaction snapshot.

## 11. Recovering When Snapshots Are Corrupted or Missing

Snapshots are optimization data, so design a clear fallback path when one cannot be read.

~~~mermaid
flowchart TD
    A["Request to load state at version T"] --> B["Find compatible snapshot ≤ T"]
    B --> C{"Decodes and passes validation?"}
    C -->|"Yes"| D["Replay events after snapshot up to T"]
    C -->|"No"| E["Try older snapshot or initial state"]
    E --> D
    D --> F{"Contiguous event versions and valid state?"}
    F -->|"Yes"| G["Return state@T"]
    F -->|"No"| H["Halt and report integrity/missing-data error"]
~~~

**Useful verification steps:**

- Matching `stream_key` (including tenant if applicable), compatible reducer, and compatible snapshot schema version.
- `snapshot.stream_version <= target_version`; never silently relabel an old snapshot as a newer version.
- Valid state structure with values consistent with core invariants.
- If checksums are used, recompute using canonical serialization and compare; checksums only detect corruption under storage assumptions, not business correctness.
- During replay, every event after the snapshot must be contiguous; verify outcomes against expected state and periodically compare full replays against snapshot + tail on sample streams.

A snapshot with a wrong monetary amount that is still valid JSON can cause worse damage than a parse failure, because it corrupts results silently. Therefore, run sample-based verification: select streams, reconstruct state **from event 1**, and compare with **snapshot + tail** under the same reducer version. This serves as operational verification; deeper academic QA checks can occur at another stage of the training workflow.

### Snapshots Do Not Replace Backups

If the event store loses data, per-aggregate snapshots do not necessarily hold enough evidence or sequence detail to recover all business workflows. You still need backup/restore for the **source of truth**, recovery drills, retention policies, and monitoring. If snapshots live in a separate store, also manage encryption key lifecycles, access controls, and external references.

## 12. Common Implementation Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Picking the snapshot with the largest `created_at` | May load an older-version snapshot written late. | Pick largest `stream_version` **≤ target** for matching stream and compatible reducer. |
| Stamping state@500 as `snapshot@530` | Skips events 501–530 during replay. | Stamp the exact last version applied to state. |
| Assuming a snapshot is always up to date with the live stream | Commands decide on stale state. | Replay tail to target version and check expected version on append. |
| Using snapshot version 100 to load `state@80` | Returns future data erroneously. | Pick only snapshots ≤ target, or replay from start. |
| Applying tail events ordered by `occurred_at` | Late-arriving data scrambles order. | Replay strictly by `stream_version`. |
| Snapshot omits state needed by subsequent events | Snapshot + tail diverges from full replay. | Capture complete aggregate state and verify invariants. |
| Bumping schema version without checking semantics | Old state decodes but gets processed under wrong rules. | Version reducers/migrators or replay from source events. |
| Snapshotting on every single event | Inflates write cost, CPU, and storage. | Choose thresholds grounded in latency, state size, and workload. |
| Deleting all events prior to a snapshot | Loses history, audit trail, and ability to rebuild new projections. | Retain events per requirements or adopt approved archival policies stating limits explicitly. |
| Treating snapshots of different aggregates as one point-in-time image | Cross-aggregate reports become inconsistent. | Use proper source synchronization or watermark models. |
| Having no fallback when a snapshot fails | One bad snapshot renders an aggregate unreadable. | Fall back to older snapshots or full replay; error if history is missing. |
| Triggering side effects from snapshots during replay | May double-refund or resend emails. | Keep `apply` pure; isolate side effects from replay. |

## 13. Exercise: Choosing Snapshot Placement and Verifying Replay

**Context:** an online course platform manages access under an `Enrollment` aggregate. Every enrollment, extension, pause, plan change, or reinstatement appends an accepted event. Some enrollments accumulate over 12,000 events over several years. When a learner opens the page, the system must load access status, expiration date, and related payment summary within acceptable latency.

### Practice Tasks

1. **Stream selection:** define the `Enrollment` stream key, specifying when access state belongs to one aggregate and when payments belong to a separate `Payment` aggregate. Explain why the two streams do not share version numbers.
2. **Snapshot state definition:** choose fields required to apply subsequent events; separate event-derived state from personal or payment details that should not be embedded.
3. **Replay math:** given a 12,340-event stream and a compatible snapshot at version 12,000, how many tail events must be applied? If `state@11,500` is needed, can `snapshot@12,000` be used? Explain.
4. **Concurrency:** a worker starts snapshotting `state@12,000` while 15 new events commit concurrently. Which version must the snapshot carry? Which mechanism must new commands use to guard version?
5. **Schema design:** propose an `enrollment_snapshot` table with stream ID, version, reducer version, snapshot schema, state, and created timestamp; add appropriate keys/unique constraints.
6. **Logic evolution:** when migrating expiration from a calendar date to a UTC timestamp and introducing a new extension policy, can old snapshots be used directly? When is a migrator sufficient, and when must you replay from scratch?
7. **Failure recovery:** the latest snapshot is corrupted. Describe the recovery path and the conditions under which full rebuild becomes impossible.
8. **Analytics:** operations wants to know how many times learners paused during the past year. Is a snapshot holding only `current_access_status` enough? Propose an appropriate read model.
9. **Performance:** list metrics to decide between snapshotting every 100, 500, or 1,000 events; explain why picking a fixed number without data is poor practice.

### Self-Verification

| Criterion | How to confirm |
| --- | --- |
| Equivalence | Replay from start and snapshot + tail yield identical state for the same version/reducer. |
| Right snapshot selection | Snapshot matches stream, logic version, and `snapshot_version <= target_version`. |
| No missing events | Tail contains every contiguous version up to target. |
| Concurrency safety | Command appends validate expected version or lock read state. |
| Recoverability | Corrupted snapshots have fallbacks; source events are intact or limits are documented. |
| No side effects | Replay never calls payment APIs, sends emails, or emits new commands. |
| Measurable improvement | Replayed event count and state-load latency drop per measurements, with reasonable snapshot overhead. |

**Design conclusion:** a snapshot is a **precomputed starting checkpoint** for replay, bound to a specific stream, version, state format, and interpretation version. It enables fast reads over long histories, yet correctness holds only if the snapshot accurately reflects all events up to its version, the tail is read completely and in order, logic stays compatible, and commands still enforce concurrency control. Event history remains the source of truth; how many snapshots to retain, and whether in relational or document storage, must follow query needs and measured operational telemetry.
