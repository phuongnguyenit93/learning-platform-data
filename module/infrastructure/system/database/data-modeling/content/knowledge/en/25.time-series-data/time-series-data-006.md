# Late-Arriving Data, Concurrent Timestamps, and Measurement Corrections

## 1. Why Does Time-Series Data Not Always Arrive in Order?

In a cold-storage monitoring system, a sensor measures temperature at **10:01:00** but loses connectivity; only at **10:36:00** does the device deliver the reading to the server. Another gateway may resend the same reading three times after timeouts. After calibration, a technician also confirms that an earlier value **7.0 °C** must be corrected to **6.5 °C**. If a table has only `measured_at` and `value`, the application easily ends up:

- Dropping the late reading because it is “older than the latest record”.
- Falsely merging two readings with the **same timestamp** even though they are genuinely distinct measurements.
- Adding one sample multiple times into averages or sums when duplicate messages arrive.
- Overwriting a correction with a delayed older message.
- Keeping a 15-minute summary table wrong even after the granular table was corrected.
- Being unable to explain **what the system knew before calibration**.

The core problem is **modeling measurement identity, revision order, and time dimensions** before choosing a database or writing aggregations. Time-series data may live in relational tables, time-series engines, document stores, or analytical warehouses; wherever it resides, rules for keys, measurement semantics, lateness, and corrections must be explicit.

Our running example uses temperature sensor `SEN-A` in a cold room. Values and timestamps below are illustrative:

| Message Received | Underlying Measurement | Measured Time (UTC) | Value | Server Received Time (UTC) | Meaning |
| --- | --- | --- | ---: | --- | --- |
| E1 | M-101, rev 1 | 10:01:00 | 7.0 °C | 10:01:05 | Initial reading. |
| E2 | M-102, rev 1 | 10:01:00 | 9.0 °C | 10:03:00 | **Distinct measurement**, sharing timestamp with M-101. |
| E3 | M-101, rev 1 | 10:01:00 | 7.0 °C | 10:04:00 | Retry of the same revision. |
| E4 | M-101, rev 2 | 10:01:00 | 6.5 °C | 11:50:00 | Justified correction. |
| E5 | M-099, rev 1 | 09:59:00 | 5.0 °C | 10:30:00 | **Late-arriving** sample from prior window. |

If both M-101 and M-102 are eligible for the sample average in window 10:00–10:15, post-correction there must be **two samples**, summing to **15.5 °C** with an average of **7.75 °C**. E3 must not increase sample count. E5 must be attributed to window **09:45–10:00**, not to its arrival window at 10:30.

## 2. Four Timestamps and Two Orderings That Must Stay Separate

A time-series model typically needs more than one timestamp.

| Attribute | Meaning | What Is It Used For? |
| --- | --- | --- |
| `measured_at` / `event_time` | When the measurement or event occurred per device/source. | Placing samples on the true timeline and into analysis windows. |
| `source_emitted_at` | When the source packaged or sent the message, if reliably provided. | Analyzing device/gateway lag. |
| `received_at` | When the system received the message at the ingestion boundary. | Tracking network and queue latency. |
| `recorded_at` / `ingested_at` | When the record was persisted in the processing store. | Auditing ingestion and handling retries. |
| `correction_decided_at` (if any) | When an authoritative source confirmed a correction. | Explaining when the revised value became recognized. |
| `source_revision` | Revision sequence **for the same measurement** per authoritative source. | Selecting effective revision and preventing stale overwrites. |
| `device_sequence` (if any) | Per-session or per-device sample counter per source contract. | Detecting gaps and emission order. |

**Do not conflate these axes:**

- **Message arrival order** differs from **measurement order**.
- **Revision order of a single measurement** differs from **sequence across a sensor's measurements**.
- A newer `recorded_at` does not prove a measured value is more accurate.
- Two sources may have unsynchronized clocks; comparing timestamps requires assessing trust and clock skew.
- An event with a past `measured_at` whose new revision is confirmed today is still a **new correction**, not something to wedge invisibly into old version history.

~~~mermaid
sequenceDiagram
    participant S as Sensor
    participant G as Gateway
    participant DB as Data Store
    S->>G: M-101 rev1: measured at 10:01
    G->>DB: Send M-101 rev1 at 10:01:05
    G->>DB: Retry M-101 rev1 at 10:04
    Note over DB: Do not create second sample
    S->>G: M-099 rev1 measured at 09:59 (offline)
    G->>DB: Receive M-099 at 10:30
    Note over DB: Route to 09:45 bucket
    G->>DB: Calibrated M-101 rev2 at 11:50
    Note over DB: Replace M-101 rev1 contribution
~~~

This diagram separates timing roles; it does not imply sensors self-issue approved calibration revisions. In practice, revisions may be emitted by devices, calibration services, or authorized operations teams—explicitly define who has authority to revise data.

## 3. Distinguishing Duplicates, Collisions, Updates, and Corrections

The phenomena below cannot all be handled by a single `ON CONFLICT DO NOTHING` statement.

| Phenomenon | How to Identify | Expected Behavior |
| --- | --- | --- |
| **Duplicate message** | Same event/source version ID, equivalent payload. | Idempotent: do not multiply samples or aggregates. |
| **Two valid measurements sharing a timestamp** | Identical `measured_at`, **distinct `measurement_id`** per source contract. | Store both if the grain allows multiple samples per timestamp. |
| **Conflicting payloads for same ID and revision** | Same measurement key/revision with differing value or timestamp. | Quarantine/investigate; never blindly pick whichever arrived last. |
| **Correction** | Same measurement key, higher revision with revised value or timestamp. | Preserve revision history; update effective row and aggregates. |
| **Retraction / invalidation** | New revision invalidates the prior measurement. | Keep a tombstone/new version so stale data never resurrects. |
| **Late new sample** | New measurement key, `measured_at` older than arrival time. | Record sample in its proper business time window. |
| **Sensor emits two readings without distinct IDs** | Only `sensor_id + timestamp` with differing values. | Insufficient evidence to distinguish duplicates from distinct readings; extend contract or apply approved rules. |

**“Same timestamp” does not mean “duplicate reading”.** A device may measure two temperature channels, truncate timestamps to whole seconds, or sample twice in the same second. Enforcing `UNIQUE(sensor_id, measured_at)` drops valid measurements unless the domain commits to strictly **one** measurement per key.

For systems genuinely taking one temperature sample per minute per channel, you can define grain `(sensor_id, channel_id, sample_slot)`. Make clear that `sample_slot` is a scheduled measurement slot, not an arbitrarily rounded timestamp. Collapsing two samples in one slot via average or “last sample” is a **business rule**, not natural deduplication.

## 4. First Understand Measurement Kind: Gauge, Counter, Delta, or Event

How late data and corrections propagate depends on **measure semantics**.

| Measurement Kind | Examples | Directly `SUM` Over Time? | On Correction / Retraction |
| --- | --- | --- | --- |
| **Gauge / point-in-time value** | Temperature, pressure, humidity, battery level. | Usually no; summing samples rarely has business meaning. | Replace sample value; affected windows' AVG/MIN/MAX change. |
| **Cumulative counter** | Cumulative kWh meter, total bytes sent. | Never `SUM` raw counter levels as consumption. | Recompute adjacent differences and handle resets/wraps. |
| **Delta / increment** | Items added in a cycle, water volume over 5 minutes. | Yes if windows, units, and sources align without overlap. | Subtract old contribution, add new contribution to target period. |
| **Occurrence / event** | Alarm triggered, device rebooted. | Usually `COUNT` unique occurrences, not `AVG` values. | Canceling/editing requires exact ID reference and count logic. |
| **State transition** | Machine from `RUNNING` to `STOPPED`. | Never sum states; compute time spent per state. | Corrections can affect durations both before and after. |

For **irregularly sampled gauges**, the unweighted sample mean differs from **time-weighted mean**. For instance, one 30 °C sample and 100 samples at 20 °C during a brief burst pull the sample mean near 20 °C without proving the room stayed at 20 °C most of the time. If time-weighted averages are required, specify interpolation/hold policies, missing-data limits, and window bounds explicitly.

For **cumulative counters**, a late reading landing between two existing points alters **two adjacent deltas**; patching by “adding to counter values” is guaranteed wrong. For finance or billing, never treat measurements as silently overwritable amounts; confirmed transactions typically require domain corrections or reversals.

## 5. Define Grain and Keys Before Creating Tables

A sound design for the temperature scenario:

> **One business measurement** is identified by `(tenant_id, source_system, sensor_id, measurement_id)`. Each confirmation or revision of that same measurement carries a monotonically increasing `source_revision` per the source contract.

Where:

- `tenant_id`: data ownership boundary and customer isolation.
- `source_system`: provider/ingestion pipeline namespace; never assume IDs from two sources refer to the same reading.
- `sensor_id`: standardized sensor/channel identifier per contract.
- `measurement_id`: **durable identifier for one reading**, invariant across corrections.
- `source_revision`: logical order of authoritative source versions; selects the active version.

**Never make `measured_at` the default unique key.** Timestamps serve ordering and windowing. A new revision may even correct `measured_at` when a device clock was wrong; the business key must remain stable for traceability.

### What If the Device Lacks a `measurement_id`?

Several options exist, each requiring an explicit contract:

1. Construct a stable ID from `device_id + channel + boot_session + sequence` if those fields are **unique, non-reused, and identical on replay**.
2. If only `measured_at` exists under a strict one-sample-per-slot contract, key by sensor/slot *after* validating slot rules.
3. If a gateway assigns IDs on first receipt, store a source mapping or dedup token; generating a fresh ID on every retry breaks deduplication.
4. If the source provides neither distinct identifiers nor rules distinguishing concurrent timestamps, **it is impossible to guarantee** both zero dropped valid samples and zero duplicates. Extend the protocol or document the limitation openly.

### Distinguishing Measurement ID from Message ID

One revision can traverse a broker multiple times. `measurement_id` says “which reading”; `source_revision` says “which version”; `source_event_id` or `message_id` says “which source message”, if the source issues stable message IDs. Never use `message_id` in place of `measurement_id` if each retry assigns a new `message_id`.

## 6. Measurement Event and Correction Contract

A well-structured message contract lets pipelines validate units, timestamps, provenance, and revision lineage.

~~~json
{
  "tenant_id": "00000000-0000-4000-8000-000000000001",
  "source_system": "cold-room-gateway",
  "sensor_id": "SEN-A",
  "measurement_id": "M-101",
  "source_revision": 2,
  "source_event_id": "GW-REV-101-2",
  "operation": "UPSERT",
  "measured_at": "2026-11-20T10:01:00Z",
  "source_emitted_at": "2026-11-20T11:49:30Z",
  "correction_decided_at": "2026-11-20T11:49:00Z",
  "value": 6.5,
  "unit_code": "CELSIUS",
  "quality_code": "ACCEPTED",
  "reason_code": "CALIBRATION_CORRECTION",
  "calibration_reference": "CAL-2026-119",
  "supersedes_revision": 1
}
~~~

This contract enforces key invariants:

1. `measurement_id` stays constant across revisions; `source_revision = 2` updates M-101 rather than creating a second measurement.
2. `measured_at` remains the measurement timestamp, **not** 11:49 just because the correction was approved at 11:49.
3. `correction_decided_at` states when the fix was approved, not when the measurement window closed.
4. `operation = UPSERT` provides a new effective value; `RETRACT` invalidates the measurement. For `RETRACT`, specify ID, revision, and reason without inventing a bogus numeric value like 0.
5. `unit_code` and `quality_code` must be governed; °C cannot be summed with °F without an approved unit conversion.
6. `source_event_id` remains stable across retries of the same revision if supported by the source; otherwise rely on measurement + revision keys and payload checks.

A correction does not have to alter **only the numeric value**. It can fix `measured_at` due to clock drift, downgrade `quality_code` from `ACCEPTED` to `INVALID`, or retract a reading entirely. Any of these changes can affect buckets, counts, and safety reports.

**Never treat every unusual reading as an error.** A 45 °C reading might be a real emergency alarm, not a duplicate. Validation rules must separate physical sensor bounds, source quality codes, and business anomaly alerts.

## 7. PostgreSQL Schema: Revision History and Current State

One clean design retains **revision history** as an auditable reference and **current measurement** as a fast read projection. This does not force full event sourcing across the entire architecture; it simply models a measurement's true lifecycle.

### Stable Key Table to Serialize Operations per Measurement

~~~sql
CREATE TABLE measurement_key (
    tenant_id       UUID NOT NULL,
    source_system   VARCHAR(64) NOT NULL,
    sensor_id       VARCHAR(100) NOT NULL,
    measurement_id  VARCHAR(120) NOT NULL,
    PRIMARY KEY (
        tenant_id, source_system, sensor_id, measurement_id
    )
);
~~~

This compact key table lets workers insert the identity row first and acquire `SELECT ... FOR UPDATE`, protecting even **before any `measurement_current` row exists**. Locking only existing `current` rows cannot prevent races when two workers insert a brand-new measurement simultaneously.

### Storing Every Accepted Source Revision

~~~sql
CREATE TABLE measurement_revision (
    tenant_id           UUID NOT NULL,
    source_system       VARCHAR(64) NOT NULL,
    sensor_id           VARCHAR(100) NOT NULL,
    measurement_id      VARCHAR(120) NOT NULL,
    source_revision     BIGINT NOT NULL CHECK (source_revision > 0),
    source_event_id     VARCHAR(160),
    measured_at         TIMESTAMPTZ NOT NULL,
    source_emitted_at   TIMESTAMPTZ,
    received_at         TIMESTAMPTZ NOT NULL,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    correction_decided_at TIMESTAMPTZ,
    operation           VARCHAR(8) NOT NULL
                        CHECK (operation IN ('UPSERT', 'RETRACT')),
    value_num           NUMERIC(18, 6),
    unit_code           VARCHAR(24),
    quality_code        VARCHAR(24) NOT NULL,
    reason_code         VARCHAR(80),
    PRIMARY KEY (
        tenant_id, source_system, sensor_id,
        measurement_id, source_revision
    ),
    FOREIGN KEY (
        tenant_id, source_system, sensor_id, measurement_id
    )
    REFERENCES measurement_key (
        tenant_id, source_system, sensor_id, measurement_id
    ),
    CHECK (
        (operation = 'UPSERT'
            AND value_num IS NOT NULL AND unit_code IS NOT NULL)
        OR
        (operation = 'RETRACT' AND value_num IS NULL)
    )
);
~~~

For `operation = RETRACT`, still record `measured_at` to trace which slot was retracted; aggregations must never treat a retracted row as a 0 sample.

### Latest Effective Version per Measurement Key

~~~sql
CREATE TABLE measurement_current (
    tenant_id        UUID NOT NULL,
    source_system    VARCHAR(64) NOT NULL,
    sensor_id        VARCHAR(100) NOT NULL,
    measurement_id   VARCHAR(120) NOT NULL,
    source_revision  BIGINT NOT NULL CHECK (source_revision > 0),
    measured_at      TIMESTAMPTZ NOT NULL,
    operation        VARCHAR(8) NOT NULL
                     CHECK (operation IN ('UPSERT', 'RETRACT')),
    value_num        NUMERIC(18, 6),
    unit_code        VARCHAR(24),
    quality_code     VARCHAR(24) NOT NULL,
    applied_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (
        tenant_id, source_system, sensor_id, measurement_id
    ),
    FOREIGN KEY (
        tenant_id, source_system, sensor_id, measurement_id,
        source_revision
    )
    REFERENCES measurement_revision (
        tenant_id, source_system, sensor_id,
        measurement_id, source_revision
    ),
    CHECK (
        (operation = 'UPSERT'
            AND value_num IS NOT NULL AND unit_code IS NOT NULL)
        OR
        (operation = 'RETRACT' AND value_num IS NULL)
    )
);

CREATE INDEX ix_measurement_current_time
    ON measurement_current
        (tenant_id, sensor_id, measured_at DESC, measurement_id)
    WHERE operation = 'UPSERT';

CREATE INDEX ix_measurement_revision_received
    ON measurement_revision
        (tenant_id, received_at DESC);
~~~

**DDL Assumptions and Limitations:**

- The composite key includes source namespace to prevent colliding measurements from distinct systems. The example assumes strictly increasing revisions **within each measurement key**.
- `measurement_revision` holds every received version; `measurement_current` is a derived projection rebuildable from complete revision history.
- **Do not delete the current row on `RETRACT`.** Keeping a high-revision tombstone stops a late-arriving older `UPSERT` from resurrecting a retracted reading.
- `recorded_at` belongs to ingestion tracking, never replacing `measured_at`. PostgreSQL's `now()` returns transaction start time, which can differ from commit time; rely on a trusted source mechanism rather than this timestamp if commit ordering matters.
- The time index supports querying active current readings. With massive sensor counts per tenant, evaluate selectivity, partitioning, and device types before adding indexes.
- `NUMERIC(18,6)` provides exact decimal representation in examples at higher cost than floating point. Pick numeric precision based on sensor specs and tolerance—more digits do not raise physical sensor accuracy.
- `CHECK` constraints enforce only basic structure. Validate schema, tenant access, correction authority, units, value bounds, and timestamp sanity in the ingestion layer.

If `source_event_id` is guaranteed unique per namespace by the source, add a matching unique constraint and reconciliation rule. Never enforce global uniqueness if IDs can repeat across gateways or be absent.

## 8. Safe Ingestion: Locking, Revisions, Idempotency, and Corrections

Suppose two workers simultaneously receive M-101 revision 2. If both check “revision 2 not seen yet” and write concurrently, they can corrupt aggregates. Serialize decisions on **the exact measurement key** and commit related updates atomically.

### Recommended Transaction Workflow

1. Validate source, signatures/auth if applicable, schema, tenant, and units. Compute a canonical representation of business fields to detect **same-ID/revision conflicts**.
2. `BEGIN`. Ensure the `measurement_key` row exists and lock it so only one writer processes that key at a time.
3. Check if `(tenant, source, sensor, measurement_id, source_revision)` already exists. If payloads match: handle as **idempotent retry**; if payloads differ: **conflict**—roll back, quarantine, and never pick a winner by arrival order.
4. If the revision is new, insert into `measurement_revision`. A `source_revision` lower than current can still be logged for auditability, yet **must never overwrite current**.
5. Read `measurement_current`. Promote the incoming revision to current **only if** its revision is **strictly greater than** the current revision.
6. If current changes, compute aggregate deltas for **old** and **new** states, updating current and aggregates in the same transaction when inside the same database. If projections live elsewhere, write to an outbox/offset and enforce idempotency downstream.
7. Record source receipts/checkpoints safely without skipping uncommitted records. `COMMIT`.
8. Acknowledge the broker only after commit; if a worker crashes before ack, retries must yield the exact same single effect.

The locking core can look like:

~~~sql
BEGIN;

INSERT INTO measurement_key (
    tenant_id, source_system, sensor_id, measurement_id
)
VALUES (
    :tenant_id, :source_system, :sensor_id, :measurement_id
)
ON CONFLICT DO NOTHING;

SELECT 1
FROM measurement_key
WHERE tenant_id = :tenant_id
  AND source_system = :source_system
  AND sensor_id = :sensor_id
  AND measurement_id = :measurement_id
FOR UPDATE;

-- Within the same transaction:
-- 1. check revision/payload and insert revision if absent;
-- 2. read current and compare revision order;
-- 3. update current + affected aggregates;
-- 4. store related checkpoint/outbox if inside the same transaction boundary.

COMMIT;
~~~

This SQL block **illustrates the locking mechanism**, not a complete runnable procedure omitting the steps in the comments. Production code or stored procedures must implement full revision comparisons and conflict rollbacks. Locking `measurement_key` prevents concurrent edits to **the same measurement**, whereas shared multi-measurement aggregate rows still require atomic updates or row locks.

### Special Cases

| Case | Revision in History | Current | Aggregate |
| --- | --- | --- | --- |
| M-101 rev 1 arrives first time | Insert rev 1. | Set rev 1. | Add 1 sample. |
| Rev 1 resent with identical payload | Do not insert again. | Keep rev 1. | Unchanged. |
| Same rev 1 with differing payload | Quarantine conflict. | Unchanged. | Unchanged. |
| Rev 3 arrives before rev 2 | Accept rev 3 per policy. | Set rev 3 if source guarantees ordering. | Apply rev 3 contribution. |
| Rev 2 arrives after rev 3 | Optionally store rev 2 for audit. | **Keep rev 3**. | Unchanged. |
| Rev 4 = `RETRACT` | Insert rev 4. | Keep tombstone rev 4. | Subtract rev 3 contribution if present. |

**Caution with missing revisions:** when revisions carry **full state**, rev 3 contains complete effective data and can update current without waiting for rev 2. However, if revisions are **deltas/patches** depending on prior state, rev 3 cannot be applied before rev 2; buffer, fetch missing revisions, or materialize reliable full states. Distinguish these two contracts up front.

If the source **does not provide reliable revisions**, never assume “last received message wins”. Rely on per-key CDC commit ordering or an authoritative correction workflow issuing server-managed version numbers. Without an authoritative order, surface conflicts explicitly rather than picking arbitrarily by timestamp.

## 9. Worked Example: Correctness Under Concurrent Timestamps, Retries, and Corrections

Assume the aggregation policy accepts all `operation = UPSERT` and `quality_code = ACCEPTED` readings, computing **sample averages** per 15-minute window per sensor. Both M-101 and M-102 fall in the same window.

Before correction:

| `measurement_id` | Effective Revision | `measured_at` | Value |
| --- | ---: | --- | ---: |
| M-101 | 1 | 10:01:00 | 7.0 |
| M-102 | 1 | 10:01:00 | 9.0 |

`count = 2`, `sum = 16.0`, `avg = 8.0`. Duplicate message E3 for M-101 rev 1 changes nothing.

After correction M-101 rev 2 = 6.5:

| `measurement_id` | Effective Revision | `measured_at` | Value |
| --- | ---: | --- | ---: |
| M-101 | 2 | 10:01:00 | 6.5 |
| M-102 | 1 | 10:01:00 | 9.0 |

Now `count = 2`, `sum = 15.5`, `avg = 7.75`. Never simply **add 6.5**, because revision 2 **replaces** M-101's prior value of 7.0.

If rev 3 moves M-101's timestamp from 10:01 to 09:59, the effective update must:

1. **Subtract** M-101's contribution from window 10:00–10:15.
2. **Add** M-101's contribution to window 09:45–10:00.
3. Preserve M-101's identity and update current to the new revision.
4. Record the timestamp change in revision history.

Thus, timestamp is a **mutable attribute**, not an immutable unique key of the measurement.

## 10. Time Windows, Watermarks, and Accepted Lateness

A window `[10:00, 10:15)` includes readings at `10:00:00` and **excludes** readings at `10:15:00`. Half-open intervals prevent boundary double-counting.

In stream processing, a **watermark** typically expresses estimated progress in **event time**: records earlier than that mark are *expected* to have mostly arrived. It is not absolute proof that no late arrivals remain. Guarantees depend on source behavior, watermark generation rules, completeness, and allowed lateness.

For example:

- At 10:25, the pipeline advances the watermark to 10:20, indicating expected progress per source logic.
- A reading from 10:08 arriving at 10:30 is a **late event** relative to that watermark.
- If policy keeps window 10:00–10:15 mutable for 1 hour, aggregates update normally.
- If the window is already **finalized**, decide whether to permit restatement, publish separate adjustment records, or log late exceptions for reconciliation. **Never silently drop** late data when reports claim completeness.

Distinguish useful window states:

| Window State | Meaning | Late Data / Corrections |
| --- | --- | --- |
| **OPEN** | Actively accepting and accumulating samples. | Updated normally with deduplication. |
| **PROVISIONAL** | Past window end time, still within allowed lateness. | Updates metrics; publishes revisions if previously reported. |
| **FINALIZED** | Closed per SLA/policy. | Handled via transparent restatement or exception workflows; closing does not turn estimates into “absolute truth”. |
| **RESTATED** | Published figures recalculated due to new evidence. | Tracks report version, publication time, and downstream impact. |

Decide explicitly between **event-time windows** and **processing-time windows**. Cold storage asking “temperature at 10:00” needs event time. An operational chart of “messages received by server in the last 5 minutes” uses received/processing time. Never reuse one metric for both.

### Building Stable Buckets in PostgreSQL

On PostgreSQL versions supporting `date_bin`, group readings into 15-minute buckets anchored to a fixed UTC origin:

~~~sql
SELECT
    sensor_id,
    date_bin(
        INTERVAL '15 minutes',
        measured_at,
        TIMESTAMPTZ '2000-01-01 00:00:00+00'
    ) AS bucket_start_utc,
    unit_code,
    COUNT(*) AS sample_count,
    SUM(value_num) AS sample_sum,
    AVG(value_num) AS sample_average
FROM measurement_current
WHERE tenant_id = :tenant_id
  AND operation = 'UPSERT'
  AND quality_code = 'ACCEPTED'
  AND sensor_id = :sensor_id
  AND measured_at >= :from_utc
  AND measured_at < :to_utc
GROUP BY sensor_id, bucket_start_utc, unit_code
ORDER BY bucket_start_utc;
~~~

This computes a **sample-count average**, not a time-weighted average. Grouping by `unit_code` prevents mixing units; if a sensor changes units, convert using governed conversion rules before combining. Display timezones can differ from UTC, provided bucket origin and timezone rules are explicit. `date_bin` cannot use variable calendar months as a fixed stride.

### Business Days Do Not Always Match UTC Days

When reporting by local warehouse day, store absolute instants and track the warehouse/tenant timezone. On DST transition days, local days can last 23 or 25 hours; never hard-code `24 * 60` minutes as a local day. Weekly/monthly aggregations require calendar/timezone rules, not blind timestamp shifting.

## 11. Updating Aggregates Without Double-Counting

An example summary table for **sample-averaged gauges**:

~~~sql
CREATE TABLE sensor_15m_summary (
    tenant_id         UUID NOT NULL,
    sensor_id         VARCHAR(100) NOT NULL,
    unit_code         VARCHAR(24) NOT NULL,
    bucket_start_utc  TIMESTAMPTZ NOT NULL,
    sample_count      BIGINT NOT NULL DEFAULT 0
                      CHECK (sample_count >= 0),
    sample_sum        NUMERIC(24, 6) NOT NULL DEFAULT 0,
    revised_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (
        tenant_id, sensor_id, unit_code, bucket_start_utc
    )
);
~~~

When each sample contributes **exactly once**, compute:

~~~text
average = sample_sum / sample_count, if sample_count > 0
~~~

When the current state of a measurement key transitions from `old` to `new`, **never blindly add the incoming value**. Apply the net difference:

~~~text
If old.operation = UPSERT and old.quality = ACCEPTED:
    old_bucket = bucket(old.measured_at)
    apply_delta(old_bucket, count = -1, sum = -old.value_num)

If new.operation = UPSERT and new.quality = ACCEPTED:
    new_bucket = bucket(new.measured_at)
    apply_delta(new_bucket, count = +1, sum = +new.value_num)

Write new as current; commit deltas and current in the same transaction.
~~~

**Why does this stay accurate?**

- **Value update in same bucket:** count goes −1 then +1 (unchanged); sum shifts by `new - old`.
- **Timestamp moves to another bucket:** old bucket decrements by 1; new bucket increments by 1.
- **`RETRACT`:** subtracts old contribution without adding a bogus 0.
- **Quality downgraded to `INVALID`:** removes contribution per filter while preserving revision history.
- **Late correction with higher revision:** updates historical buckets cleanly per policy.
- **Retry of same revision:** applies no second delta.

With concurrent workers, summary rows also require **atomic `UPDATE`s or row locks** so two transactions never read stale sums and overwrite each other. Locking `measurement_key` serializes updates on **the same measurement**, not across different measurements sharing the same bucket.

### Atomic Delta Update Pattern

For **adding a contribution** (`count = +1`), upsert to create the bucket if absent or increment if present. For **removing an old contribution** (`count = -1`), update only an **existing** bucket—never attempt an `INSERT` with `sample_count = -1`, since the non-negative check will reject it even before conflict resolution.

~~~sql
-- Add a new valid sample to bucket (delta_count = +1).
INSERT INTO sensor_15m_summary (
    tenant_id, sensor_id, unit_code,
    bucket_start_utc, sample_count, sample_sum
)
VALUES (
    :tenant_id, :sensor_id, :unit_code,
    :bucket_start_utc, 1, :new_value
)
ON CONFLICT (
    tenant_id, sensor_id, unit_code, bucket_start_utc
)
DO UPDATE SET
    sample_count = sensor_15m_summary.sample_count + 1,
    sample_sum = sensor_15m_summary.sample_sum + EXCLUDED.sample_sum,
    revised_at = now();

-- Remove prior sample contribution; 0 rows returned = needs investigation.
UPDATE sensor_15m_summary
SET sample_count = sample_count - 1,
    sample_sum = sample_sum - :old_value,
    revised_at = now()
WHERE tenant_id = :tenant_id
  AND sensor_id = :sensor_id
  AND unit_code = :unit_code
  AND bucket_start_utc = :old_bucket_start_utc
  AND sample_count >= 1
RETURNING sample_count;
~~~

These two statements show **illustrative branches**, not both executing unconditionally on every event. A correction with valid old and new states subtracts the old contribution and adds the new **within the same transaction** updating `measurement_current`; brand-new readings only add, while retractions only subtract. If the removal branch returns 0 rows or detects drift, roll back and investigate/rebuild instead of ignoring it. When a correction spans **two buckets**, enforce a consistent lock ordering to avoid deadlocks. Atomic increments in `ON CONFLICT DO UPDATE` protect the summary row, not measurement-key revision ordering or idempotency.

### `AVG`, `MIN`/`MAX`, and Metrics That Resist “Subtraction”

- `SUM` and `COUNT` support clean incremental deltas via exact inverses.
- `AVG` is derived from `sum / count`, never by averaging group averages when counts differ.
- `MIN` and `MAX` often require **recomputation** when the extreme sample itself is modified or retracted.
- `MEDIAN`, percentiles, and quantile sketches generally do not support exact single-point deletion; use specialized algorithms or recompute.
- **Time-weighted gauge averages** and **counter deltas** depend on **neighboring** samples, so revising one point affects multiple intervals. Never apply the same delta helper blindly to every metric type.

In many architectures, **recomputing affected buckets from `measurement_current`** and publishing a new summary version is safer whenever exact inverse operations do not exist. The trade-off is re-reading bucket samples; choose based on load, SLAs, and correctness demands.

## 12. Current-State Read Tables, Correction History, and “As-Of” Queries

In a system allowing corrections, at least two distinct questions arise:

1. **What is M-101's currently recognized value?** Requires the latest effective revision.
2. **At 10:15 before calibration, what did the system know and report?** Requires *when-known / when-recorded* history, not event time alone.

`measurement_current` answers the first question. `measurement_revision` with `recorded_at` aids ingestion auditing, while accurately reconstructing “what the system knew at time T” additionally requires:

- Consistent commit ordering when revisions arrive closely together.
- Clear rules for accepting corrections, handling conflicts, and closing watermarks.
- Storing versions of published projections/KPIs when reports undergo restatements.
- Distinguishing `recorded_at` from when a correction was **business-approved/effective**.

Rebuilding current from revision history for reconciliation:

~~~sql
WITH latest AS (
    SELECT DISTINCT ON (
        tenant_id, source_system, sensor_id, measurement_id
    )
        tenant_id, source_system, sensor_id,
        measurement_id, source_revision,
        measured_at, operation, value_num,
        unit_code, quality_code
    FROM measurement_revision
    WHERE tenant_id = :tenant_id
    ORDER BY
        tenant_id, source_system, sensor_id,
        measurement_id, source_revision DESC
)
SELECT *
FROM latest
WHERE operation = 'UPSERT'
  AND quality_code = 'ACCEPTED';
~~~

This selects the **highest stored revision** per measurement key, assuming revisions carry reliable full-state ordering and no unverified disputed revisions sit in the table. It does not prove by itself that the revision came from an authorized source.

### “As-Known” History vs. “Effective” History

Suppose at 10:15 the dashboard published an average of 8.0 °C. At 11:50 a correction updates M-101, changing that window's average to 7.75 °C.

- **Report published at 10:15:** 8.0 °C based on information known then.
- **Restated report post-correction:** 7.75 °C.
- **Sensor diagnostics:** needs to know when the correction was decided, its reason, and its magnitude.

Strict auditing requires storing **`published_at`, `report_version`, `source_cutoff`/`watermark`, and `metric_definition_version`** for each publication. Overwriting summary rows in place erases what numbers were previously displayed.

## 13. Late Data in Batch, CDC, and Analytical Pipelines

Streaming is not alone in facing late data. Daily ETL jobs receive yesterday's files today or backfill multi-day offline sensor logs.

A reference pipeline:

~~~mermaid
flowchart LR
    S["Sensors / gateways"] --> L["Landing + source metadata"]
    L --> V["Validate, identity, revision, dedup"]
    V --> H[("Measurement revision history")]
    V --> C[("Measurement current")]
    C --> B["Aggregate/rollup by event-time"]
    B --> D[("Dashboard / analytical warehouse")]
    H --> R["Recompute / historical reconciliation"]
    R --> B
~~~

Consistent contracts across stages:

1. **Landing:** preserve source, batch/message ID, arrival time, and format metadata; route schema failures to a restricted quarantine area.
2. **Deduplication:** key by measurement identity + revision; never merge rows solely because timestamps match.
3. **Effective upsert:** update current according to authoritative revision order.
4. **Aggregation:** update or recompute buckets by `measured_at`, including older buckets opened for accepted revisions.
5. **Checkpointing:** advance ingestion checkpoints **only after committing target writes** or inside the same transaction. For brokers/CDC, use offsets/cursors guaranteed not to skip uncommitted records.
6. **Reconciliation:** verify measurement key counts, latest revisions, retraction counts, and current-to-report totals.
7. **Publication:** when finalized figures change, trigger restatements, downstream notifications, and cache invalidations per policy.

### Never Use Uncommitted `MAX(id)` as a Watermark

In databases allocating sequences before commit, transaction A may receive ID 101 yet commit after transaction B commits ID 102. An ingestion reader polling “all `ID <= 102`” and advancing its cursor to `ID > 102` skips event 101 permanently. Use a cursor contract aligned with **commit order** or a safe snapshot + change-stream mechanism—never infer completeness from sequence allocation or wall clocks.

### When Sources Send Snapshots Only

If a gateway periodically emits the latest 100 measurements and the next poll shows only 90, **never** automatically treat the 10 absent IDs as deleted readings unless you verify the snapshot is **complete, identically scoped, and authoritative**. Many protocols send sliding “last 100” windows that do not represent full historical existence.

## 14. Physical Optimization: Partitioning, Indexes, Retention, and Rebuilds

Time-series stores can hold billions of readings. Adding revision history and current tables increases footprint, so optimize for real query paths.

| Query Problem | Suggested Structure | Trade-Offs |
| --- | --- | --- |
| Inspect correction history of one measurement | Key `(tenant, source, sensor, measurement_id, revision)`. | Long composite PK; normalize IDs if needed. |
| Read current temperatures by sensor/time | Filtered index on `(tenant, sensor, measured_at)` for valid rows. | Ingestion/corrections update index; verify selectivity. |
| Minute/hour/day summaries | Materialized aggregates or TSDB rollups. | Must recompute on late/corrected data; track version/lag. |
| Monthly scans across many sensors | Partitions / time-series chunks on `measured_at`. | Changing timestamps moves rows across partitions; cross-partition uniqueness has DB limits. |
| Audit arrivals during a period | Store `received_at`/`recorded_at` and lineage. | Decide whether every retry transmission must be kept. |
| Long-term BI | Columnar analytical warehouse with clear grain/metrics. | Backfills, retention, schema evolution, reconciliation. |

### Partitioning Must Account for Unique Keys

PostgreSQL restricts unique/primary keys on partitioned tables: unique constraints normally must include the partition key columns. If you partition `measurement_revision` by `measured_at` while requiring **unique measurement ID + revision independent of time**, a simple partitioned unique constraint cannot enforce that globally.

One solution is **keeping a separate unpartitioned identity/receipt table** enforcing global uniqueness while time-partitioning history; alternatively, choose an engine or partitioning design suited to those guarantees. Never “fix” the constraint error by adding `measured_at` to the unique key and accidentally letting the same measurement/revision be inserted at two timestamps.

### Retention for History and Aggregates

- **Current:** retain active rows plus tombstones needed to block resurrection from stale revisions.
- **Revision history:** retain per audit and correction windows; purging old revisions limits replay and explanation of past corrections.
- **Raw landing** and retry logs can have shorter retention than normalized history depending on reconciliation needs.
- **Rollups** may outlive raw data, yet cannot materialize brand-new metrics once granular inputs are purged.
- **Snapshots/backups** must obey retention and privacy rules; deleting from `current` does not erase data from backups.

If a correction arrives after raw data has expired past retention, policy must specify whether corrections are still allowed, whether tombstones/receipts are recorded, and how stale historical reports are flagged. Never promise full rebuilds after purging the underlying detail.

## 15. Data Quality, Security, and Source Accountability

Valid JSON does not imply physically valid telemetry.

### Ingestion-Time Checks

- **Identity:** complete measurement key; never merge distinct sensors, tenants, or sources.
- **Clock drift:** `measured_at` unreasonably far in the future or past gets quarantined for adjustment rather than silently overwritten without lineage.
- **Unit/scale:** `6.5 CELSIUS` differs from `6.5 FAHRENHEIT`; conversions must follow governed contracts.
- **Range:** check readings against sensor limits while separating faulty readings from genuine temperature emergencies.
- **Revisions:** monotonic per key, authorized actor, valid reason; conflicting payloads at the same revision must error.
- **Sequence gaps:** detect missing `device_sequence` numbers where guaranteed; never infer missing samples solely from irregular timing on event-driven sensors.
- **Tenant isolation:** every lookup, key, query, and report must enforce tenant/source boundaries.
- **Preserve correction lineage:** record source, actor/device approval, and explanation for every change.

### Privacy

Time-series data is not inherently “non-sensitive”. GPS traces, appliance power usage, wearables, and activity timelines reveal personal behavior. Enforce subject-level access controls, minimize directly identifying metadata, govern retention, execute controlled deletion/anonymization, and audit copies across raw, history, rollup, search, and backup stores.

Never assume `hash(sensor_id)` or stripping usernames suffices when temporal patterns still re-identify devices or individuals. Any audit exemption from deletion must be documented and policy-backed.

## 16. Observability: Measuring Real Data Quality and Latency

Monitoring should cover both **pipeline health** and **data trustworthiness**:

| Metric | Meaning | Watch Out For |
| --- | --- | --- |
| `ingest_lag = received_at - measured_at` | Delay from measurement to receipt. | Negative spikes may indicate clock skew; don't trust skewed clocks for SLAs. |
| `processing_lag` | Delay from receipt to projection availability. | Averages hide p95/p99 tails. |
| `duplicate_rate` | Share of repeated messages by ID/revision. | Never classify two distinct samples at one timestamp as duplicates. |
| `revision_conflict_count` | Cases sharing ID/revision with differing payloads. | Group by source/device and investigate. |
| `late_event_rate` | Share of events arriving past watermark / window close. | Reflects watermark policy, not measurement errors. |
| `correction_rate` | How many measurement keys receive new revisions. | Separate calibration, clock fixes, and invalidations. |
| `retraction_rate` | Share of samples legitimately retracted. | Never count retractions as zero values. |
| `bucket_drift` | Discrepancy between rollups and recomputed current. | Compare at a consistent data snapshot. |
| `missing_sequence_count` | Gaps in guaranteed device sequences. | Inapplicable to devices without contiguous sequences. |

### Data Verification Queries

Find measurement keys with more than one revision:

~~~sql
SELECT tenant_id, source_system, sensor_id, measurement_id,
       COUNT(*) AS revisions_received,
       MAX(source_revision) AS latest_revision
FROM measurement_revision
WHERE tenant_id = :tenant_id
GROUP BY tenant_id, source_system, sensor_id, measurement_id
HAVING COUNT(*) > 1;
~~~

Find `current` rows out of sync with `history` **at a synchronized checkpoint**:

~~~sql
WITH latest AS (
    SELECT tenant_id, source_system, sensor_id,
           measurement_id,
           MAX(source_revision) AS max_revision
    FROM measurement_revision
    WHERE tenant_id = :tenant_id
    GROUP BY tenant_id, source_system, sensor_id, measurement_id
)
SELECT l.*
FROM latest l
LEFT JOIN measurement_current c
  ON c.tenant_id = l.tenant_id
 AND c.source_system = l.source_system
 AND c.sensor_id = l.sensor_id
 AND c.measurement_id = l.measurement_id
WHERE c.source_revision IS DISTINCT FROM l.max_revision;
~~~

If a pipeline allows storing **pending unverified revisions** prior to updating current, the second query will show expected differences. Add a status (`accepted`/`pending`/`rejected`) to revision history and compare only against **accepted** revisions; this lesson's schema assumes all recorded revisions are accepted with no staging state.

Beyond version checks, reconcile `current` sample sets against rollups by bucket, unit, and quality—checking `SUM`, `COUNT`, bucket moves, and retractions. Always run comparisons against **a consistent snapshot**, never comparing two concurrently mutating tables and mistaking in-flight timing for drift.

## 17. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `UNIQUE(sensor_id, measured_at)` for every series | Drops valid measurements sharing a timestamp. | Define exact grain and measurement ID/slot. |
| Treating equal payloads with different IDs as duplicates | Deletes independent readings. | Deduplicate via source identity/contract, not value/time guesses. |
| Picking “last message received wins” | Stale delayed message overwrites newer correction. | Use authoritative source revisions/cursors. |
| Deleting row instead of storing tombstone on retraction | Late older revision resurrects retracted sample. | Keep `RETRACT` status and highest revision in `current`. |
| Adding retries into `SUM`/`COUNT` again | Skewed averages and event counts. | Key+revision idempotency; commit aggregates with `current`. |
| Treating corrections as brand-new measurements | Inflates counts instead of replacing old values. | Subtract old contribution, add new contribution. |
| Updating only the new bucket when timestamp changes | Old bucket retains phantom contribution. | Recompute or update both old and new buckets. |
| Grouping temperatures by `received_at` | Offline telemetry lands in wrong hours. | Use event-time windows on `measured_at`. |
| Assuming watermark means zero late arrivals | Drops valid post-close telemetry. | Define allowed lateness and restatement/exception rules. |
| Using `SUM(counter_value)` as total consumption | Double-counts cumulative totals. | Difference counters with reset/wrap and order handling. |
| Using `AVG(AVG(...))` across groups of unequal size | Wrong overall mean. | Compute from total sum / total count or proper weights. |
| Mixing °C and °F in aggregates | Meaningless KPIs. | Normalize units and version rules. |
| Updating `current` without updating materialized rollups | Historical reports stay stale after corrections. | Apply deltas/recompute plus reconciliation and invalidation. |
| Partitioning by timestamp and losing logical ID uniqueness | Same measurement/revision lands in multiple partitions. | Enforce uniqueness via non-partitioned receipts/constraints. |
| Keeping only rollups while promising full metric replay | Missing granularity for new formulas. | Align retention with explicit rebuild guarantees. |

## 18. Practical Exercise: Late Cold-Storage Telemetry and Retroactive Calibration

**Context:** Two sensors `SEN-A` and `SEN-B` in a cold room emit readings with 1-second UTC timestamps. Gateways occasionally go offline and replay batches. A calibration team can issue new revisions or retractions. Dashboards show 15-minute average temperatures, valid sample counts, and threshold breaches.

Messages arrive in **server arrival order**:

| Arrival Order | Sensor | `measurement_id` | Revision | `measured_at` | Value | Operation |
| ---: | --- | --- | ---: | --- | ---: | --- |
| 1 | SEN-A | A-01 | 1 | 10:01:00 | 7.0 | UPSERT |
| 2 | SEN-A | A-02 | 1 | 10:01:00 | 9.0 | UPSERT |
| 3 | SEN-A | A-01 | 1 | 10:01:00 | 7.0 | UPSERT (retry) |
| 4 | SEN-A | A-01 | 3 | 10:01:00 | 6.5 | UPSERT (calibrated) |
| 5 | SEN-A | A-01 | 2 | 10:01:00 | 6.8 | UPSERT (late revision) |
| 6 | SEN-A | A-03 | 1 | 09:59:00 | 5.0 | UPSERT (late sample) |
| 7 | SEN-B | B-01 | 1 | 10:01:00 | 4.0 | UPSERT |
| 8 | SEN-A | A-02 | 2 | 10:01:00 | None | RETRACT |

Assume all `UPSERT`s have `quality_code = ACCEPTED` and unit `CELSIUS`; revisions are **full-state** and monotonically increasing per measurement key. Numbers are technical scenarios, not food-safety guidance.

### Tasks

1. **Define grain:** specify `(tenant, source, sensor, measurement_id)`. Why must A-01 and A-02 remain separate despite identical `measured_at`?
2. **Separate time axes:** for A-03, measured at 09:59 and received after 10:01, which bucket does it belong to? Which timestamp measures ingestion latency?
3. **Determine current state:** after all eight messages, what are the effective revision and state of A-01, A-02, A-03, and B-01?
4. **Compute per-sensor aggregates:** in `SEN-A` bucket `[10:00, 10:15)`, how many valid samples remain, and what are their sum and average? What is in `SEN-A` bucket `[09:45, 10:00)`? Do not mix `SEN-B` into `SEN-A`.
5. **Retries and out-of-order revisions:** why does message 3 create no new sample, and why must revision 2 arriving after revision 3 not overwrite revision 3?
6. **Retraction:** why must A-02 retain a rev-2 tombstone in `current` instead of deleting the key outright?
7. **Schema:** design `measurement_revision` and `measurement_current` with unique constraints, FKs, and time indexes without using timestamp as the PK.
8. **SQL:** write queries fetching latest revision per key and grouping `UPSERT`/`ACCEPTED` current rows into 15-minute `date_bin` buckets separated by unit.
9. **Worker concurrency:** two workers concurrently receive A-01 rev 4. Propose locking or CAS, conflicting-payload handling, and atomic aggregate updates.
10. **Timestamp move:** rev 4 of A-01 changes `measured_at` from 10:01 to 09:59. Which buckets change, and how do you verify results?
11. **Watermark:** when A-03 arrives after the 09:45 window was finalized, propose an intentional restatement/exception workflow.
12. **Counter devices:** a cumulative power meter reports 100, 110, 125, then resets to 3. Explain why `SUM(values)` is not energy consumed, and how corrections/late arrivals affect deltas.
13. **Report versioning:** if dashboards already published pre-correction averages, what metadata do you store to explain subsequent changes?
14. **Operations/retention:** pick metrics for lag, duplicate rate, conflict rate, and bucket drift; describe the impact if a correction arrives after raw data has expired.

### Quantitative Verification Guide

Under these assumptions, after processing all eight messages:

- `SEN-A`, window **10:00–10:15** retains only A-01 rev 3 = **6.5 °C** since A-02 was retracted; **count = 1, sum = 6.5, average = 6.5 °C**.
- `SEN-A`, window **09:45–10:00** has A-03 = **5.0 °C**; **count = 1**.
- `SEN-B`, window **10:00–10:15** has B-01 = **4.0 °C**; **count = 1**.
- Late A-01 rev 2 may still be recorded in revision history, yet **`current` retains rev 3**, and no aggregation adds 6.8 again.
- A-02 `current` holds `operation = RETRACT`, contributing zero to counts or sums. Any subsequent replay of A-02 rev 1 is rejected from becoming active.

### Self-Assessment Checklist

| Criterion | Expected Outcome |
| --- | --- |
| **Grain** | Never merges two independent measurements solely because timestamps match. |
| **Dedup** | Retries of the same revision neither add samples nor re-apply aggregates. |
| **Ordering** | Older revisions never overwrite newer `current`; same-revision payload conflicts are caught. |
| **Corrections** | Correctly handles edits to value, `measured_at`, quality, and `RETRACT`. |
| **Time axes** | Event-time buckets stay separate from processing time; explicit watermark/lateness policy exists. |
| **Math** | `SUM`/`COUNT`/`AVG` match grain and metric kind; never sum counters or mixed units. |
| **Consistency** | Revision history, current, summary, and checkpoints share clear transaction/idempotency bounds. |
| **Reproducibility** | Summary tables reconcile against `current` at a consistent snapshot; retention limits are stated. |
| **Governance** | Tenant/source namespaces, correction permissions, sensitive data, and audit trails are enforced. |

**Conclusion:** reliable time-series handling begins by **decoupling measurement identity from timestamps**, separating **measurement time from arrival time**, and distinguishing **duplicate retries, concurrent distinct measurements, revision corrections, and retractions**. Late data must land in its proper business window; corrections must replace old contributions rather than inflate counts; published aggregates require verifiable restatement policies. Whether backed by relational tables, time-series engines, document stores, or analytical warehouses, these rules form the bedrock of evolvable, auditable, and accurate telemetry.
