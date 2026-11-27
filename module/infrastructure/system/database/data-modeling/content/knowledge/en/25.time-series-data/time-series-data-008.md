# Retention by Granularity Level and Traceability Requirements

## Learning Objectives

After this lesson, you will be able to:

- Design **retention policies** for time-series data across resolution tiers: raw measurements, 1-minute, 1-hour, and 1-day rollups, and incident data.
- Distinguish **granularity**, **freshness**, **retention duration**, **event time**, and **ingestion time**; never conflate data downsampling with erasing business history.
- Choose statistics that merge accurately from finer to coarser tiers while recognizing information that **cannot be recovered** after downsampling.
- Define **traceability requirements** across levels: KPI verification, incident diagnosis, source reconciliation, and retaining verifiable evidence.
- Design keys, time buckets, partitions, rollups, indexes, data lineage metadata, and deletion/archival workflows using PostgreSQL examples.
- Handle late-arriving data, duplicate records, retroactive corrections, device clock drift, missing measurements, and legal/investigative holds.
- Make grounded trade-offs among storage cost, query speed, privacy, and reproducibility rather than applying one uniform TTL across all data.

In the **DATABASE_DATA_MODELING** module, data design does not stop at tables, keys, indexes, and write-time consistency. For **time-series data**, another critical decision is: **at what level of detail should data be kept, and for how long, to both answer reports and retain sufficient evidence when issues occur?** Keeping every raw measurement forever can drive storage and operational costs sky-high. Conversely, keeping only daily averages can make a multi-minute incident vanish from history. This lesson focuses on that trade-off and how to turn it into a verifiable data contract.

## 1. Running Scenario: Cold-Chain Temperature Monitoring

Suppose a pharmaceutical logistics company operates multiple cold warehouses. Each sensor device sends **one temperature reading per minute**. The platform must satisfy the following needs:

1. **Immediate operations:** know which warehouse just breached a threshold; open a detailed chart of the last 30 minutes to inspect fluctuations.
2. **Short-term analysis:** compare hourly minimum, maximum, and average temperatures over 6 months.
3. **Long-term analysis:** track daily trends and out-of-range duration percentages over multiple years.
4. **Incident investigation:** when an alarm triggers at 10:15, locate the relevant measurements, sample quality, ingestion timestamps, device details, and active threshold policy.
5. **Contractual compliance:** confirmed incidents may require long-term evidence; routine readings do not necessarily share the same retention term.
6. **Privacy and data lifecycle:** personnel/location data, if present, must not be kept indefinitely merely because storage capacity exists.

The retention durations below are **design assumptions for learning**, not pharmaceutical regulations or universal compliance advice:

| Data Tier | Grain / Level of Detail | Example Retention | Purpose Served |
| --- | --- | --- | --- |
| Raw measurements (hot raw) | One sample per device and measurement time | 30 days in fast-query store | Debugging, alerting, detailed charts |
| Raw measurements (cold archive) | Still individual raw samples | Additional 150 days, 180 days total | Delayed investigations and reprocessing if needed |
| 5-minute rollup | One device–one 5-minute bucket | 180 days | Observing short-term swings more cheaply than raw |
| 1-hour rollup | One device–one UTC hour | 3 years | Seasonal reports, operational quality |
| 1-day rollup | One device–one business calendar day | 5 years | Long-term trends, defined KPIs |
| Critical incident evidence package | One incident plus relevant raw slices/metadata | Per contract, e.g., 5 years | Decision traceability and independent inspection |
| Pipeline audit / lineage | One ingest run, transform version, manifest | Per separate audit policy | Explaining how data was produced and changed |

**Note:** "30 days hot raw + 150 days cold" represents **two storage tiers of the same detail level**, not two separate business records. You must decide the **total** retention term and deletion responsibility for each copy; never assume 30 hot days plus a 180-day archive means 210 days if the contract specifies 180 days total.

### Three Questions Before Setting Any TTL

- **If raw data is deleted after 180 days, do reports still need to know an incident happened at minute 15?** If yes, store exceedance events or detailed evidence before purging.
- **If only daily averages remain, can you prove a sensor never crossed the threshold?** No; an average captures neither all extremes nor exceedance durations.
- **If a raw measurement belongs to an open investigation, should normal TTL delete it?** That depends on evidence-hold policies. You need controlled hold flagging and release schedules rather than blind deletion.

## 2. Do Not Confuse Resolution with Retention Period

Two independent design axes:

- **Resolution:** does a row represent a single measurement or a 5-minute/hourly/daily bucket?
- **Retention period:** how long can rows at that resolution remain accessible from the retention anchor timestamp?

Commonly confused concepts:

| Concept | Meaning | Example |
| --- | --- | --- |
| Sampling cadence | Expected interval at which a device emits samples | Every 60 seconds |
| Event time / observed_at | When temperature was actually measured per a trusted clock source | 10:15:00Z |
| Ingest time / received_at | When the platform received the sample | 10:16:12Z |
| Bucket start | Start of the aggregation window per defined standard | 10:00:00Z for a 1-hour bucket |
| Granularity | How much time and entity scope one summary row represents | One device–one hour |
| Freshness | How far source data has progressed through the pipeline | Processed source data through 10:20Z |
| Retention cutoff | Cutoff before which aged data is archived/deleted per policy | Raw before day D−180 |
| Completeness | Whether a bucket has sufficient data per source/policy | Received 58/60 expected samples |
| Traceability | How far evidence can be explained or reconciled | Report → bucket → raw reading or archive |

**A 1-hour bucket does not necessarily hold exactly 60 readings**, even at a 1-minute cadence. Devices can lose connectivity, backfill, resend duplicates, or change sampling intervals. Never infer `sampleCount = 60` solely from an hourly table name.

### Data Volume Illustration

With **1,000 sensors**, each sending one sample per minute:

\[
N_{\text{raw/day}}=1000\times 60\times 24
=1,440,000\;\text{samples}.
\]

Keeping 90 days of raw equals roughly **129.6 million samples** before duplicates, metadata, indexes, backups, or burst anomalies. Meanwhile, a 1-hour rollup holds at most **24,000 rows per day** if every device produces one row/hour. This is a **record-count** calculation, not a benchmarked byte estimate; actual footprint depends on compression, data types, DBMS overhead, indexes, and metadata volume.

This row-reduction ratio explains why rollups are usually kept longer than raw. Yet reducing row counts is only worthwhile if you do not erase **information essential for intended use**.

## 3. Grain at Every Tier Must Be Explicitly Defined

For temperature telemetry, you can state:

| Table / Tier | Grain Statement | Candidate Unique Key |
| --- | --- | --- |
| sensor_reading | One measurement from one device, by source-issued timestamp and sequence | tenant, device, observedAt, sourceSequence |
| temperature_5m | One device within one 5-minute UTC bucket | tenant, device, bucketStart |
| temperature_1h | One device within one 1-hour UTC bucket | tenant, device, bucketStart |
| temperature_daily | One device within one defined **business day** | tenant, device, businessDate, calendarPolicyVersion if needed |
| temperature_excursion | One **continuous threshold breach** confirmed by policy | tenant, excursionId |
| evidence_manifest | One evidence package with independent identity | tenant, evidenceId |

For every table, you must answer:

1. **What is one row?** An actual sample, statistics across samples, or a detected incident?
2. **Which identity key stays stable across retries?** Generating a fresh `eventId` on every ingest attempt breaks deduplication.
3. **Is tenant/device scope clear?** Two distinct sensors can share the exact same timestamp.
4. **Where does a day start?** A 1-hour UTC bucket differs from a local-timezone business day.
5. **How is sample quality handled?** Are `INVALID`/`SUSPECT` samples excluded from averages?
6. **What happens on historical corrections?** Record corrections, recompute rollups, or publish a new version?

Grain is not just the column order of a `PRIMARY KEY`. It is a **commitment to row semantics** so every report remains verifiable.

## 4. Designing a Multi-Tier Data Pipeline

~~~mermaid
flowchart TB
    D["Sensors + gateway<br/>deviceId, sequence, observedAt"]
    I["Ingest<br/>validate, dedup, clock/quality checks"]
    R["Raw readings<br/>hot → cold archive"]
    F["5-minute rollup<br/>count, sum, min, max, quality"]
    H["1-hour rollup<br/>count, sum, min, max, quality"]
    Y["Daily rollup<br/>explicit timezone/cutoff"]
    X["Anomaly detection<br/>excursion event + evidence"]
    A["Lineage / watermark / audit"]
    Q["Chart API, BI, reconciliation"]

    D --> I
    I --> R
    R --> F
    F --> H
    H --> Y
    R --> X
    X --> A
    R --> A
    F --> A
    H --> A
    Y --> A
    F --> Q
    H --> Q
    Y --> Q
    X --> Q
~~~

This diagram shows functional layers; not all data must flow strictly sequentially raw → 5 minutes → 1 hour → daily. You can compute 1-hour rollups directly from raw or from 5-minute buckets **provided the statistics merge cleanly**. For local-timezone daily reporting, never automatically sum 24 UTC buckets starting at `00:00Z` when the local day has different boundaries.

**The authoritative source remains the sample/event recording store**, not downsampled chart series. An hour showing `avg = 5 °C` does not prove every sample stayed at `5 °C`.

## 5. Downsampling Without Distorting Measurements

Suppose one bucket holds valid temperature values:

~~~text
04:00  3°C
04:01  4°C
04:02  10°C
04:03  3°C
~~~

Then:

- `sampleCount = 4`.
- `sumTemperature = 20`.
- `average = 5 °C`.
- `min = 3 °C`, `max = 10 °C`.

If the allowed limit is at most 8 °C, **the 5 °C average completely misses that a point breached the threshold**. `MIN`/`MAX` reveal an extreme occurred, yet still cannot answer how long the breach lasted, whether it was continuous, or whether it happened before/after a cold-room door-open event.

### Keep Enough Statistics to Merge Multiple Buckets

An hourly rollup should retain at least the quantities required for KPIs:

\[
\text{avg}=\frac{\text{sum}}{\text{validCount}}
\quad\text{when validCount}>0.
\]

To merge multiple buckets:

\[
\text{sum}_{all}=\sum_i \text{sum}_i,\quad
\text{validCount}_{all}=\sum_i \text{validCount}_i,\quad
\text{min}_{all}=\min_i \text{min}_i,\quad
\text{max}_{all}=\max_i \text{max}_i.
\]

**Never average averages** when sample counts differ. For example, bucket A has one 10 °C sample and bucket B has nine 2 °C samples:

~~~text
Wrong:   (10 + 2) / 2 = 6°C
Correct: (10 × 1 + 2 × 9) / (1 + 9) = 2.8°C
~~~

The difference is not rounding error; it is **wrong grain and wrong weighting**.

### Not Every Statistic Merges from `avg`/`min`/`max`

| Needed KPI | What Must Be Kept When Downsampling? | Derivable from `avg`/`min`/`max`/`count`? |
| --- | --- | --- |
| Sample-based average | `sum` and `validCount` | Yes, if `sum`/`count` retain sufficient precision |
| Overall interval min/max | Per-bucket `min`/`max` | Yes, if buckets are complete and identically defined |
| Count of samples above 8 °C | `aboveThresholdCount` with policy version | No |
| **Continuous minutes** above threshold | State intervals/segments and interpolation rules | No |
| p95 percentile | Raw or mergeable histogram/sketch per chosen technique | Generally no; hourly p95s do not merge into daily p95 |
| **Time-weighted** true average | Time-integrated value and total valid duration | No, if only sample-count average is stored |
| Exact timestamp of peak | `max` plus `argmax` timestamp or raw | Max value alone is insufficient |
| Ordering of anomalous points | Raw or stored event sequence | No |

Under irregular sampling, sample-based average and time-weighted average are not equivalent. You may need:

\[
\overline{T}_{time}
=\frac{\sum_i T_i\,\Delta t_i}{\sum_i \Delta t_i},
\]

where \(\Delta t_i\) comes from an explicit **interpolation/hold rule** capped when a device drops out for long periods. Never assume every sample represents equal duration when cadence fluctuates.

### Store Quality Signals Too

Beyond `sum`/`count`/`min`/`max`, consider:

- `observedCount`: total received samples at the grain.
- `validCount`, `suspectCount`, `invalidCount` under a versioned quality rule set.
- `expectedCount` when a known cadence and device active schedule exist; never guess blindly from bucket length.
- `coverageRatio = validCount / expectedCount`, when `expectedCount` is genuinely meaningful.
- `peakAt` or `thresholdBreachCount` if required by reports.
- `watermark`/`completeFlag` and `transformVersion` to show whether a bucket may still change.

When `validCount = 0`, average should be **`NULL`**, not 0 °C. "Could not measure" is completely different from "measured a temperature of 0."

## 6. Traceability Is a Concrete Requirement, Not Just an ID Column

Stakeholders saying "it must be traceable" may actually mean very different capabilities:

| Traceability Tier | Question to Answer | Minimum Data Likely Needed |
| --- | --- | --- |
| KPI / result explanation | How was the daily average computed? | Formula, `count`/`sum`, interval, source, and transform version |
| Input data inspection | Which samples went into this bucket? | Source keys, raw or retrievable source/batch list |
| Incident diagnosis | When was the threshold breached and for how long? | Sufficiently granular raw or excursion segment with quality/evidence |
| Investigation / reconciliation | Who edited data, which threshold applied, when was the report closed? | Audit, rule version, event/correction lineage, manifest |
| Independent verifiable evidence | Can raw data and the processing chain be re-examined? | Retained raw samples, checksums/signatures if needed, tool versions, access controls |

**You cannot promise per-sample traceability after purging all raw records** without keeping an appropriate archive. A daily row with min/max, checksum, or `eventId` proves limited facts; it cannot reconstruct lost individual measurements.

### Linking Keys and Lineage

A sensible traceability graph:

~~~mermaid
flowchart LR
    B["Daily report D<br/>reportRunId + policy"]
    H["Hourly rollup<br/>tenant, device, bucket"]
    M["Raw manifest<br/>partition/object, checksum"]
    R["Raw samples<br/>source sequence, observedAt"]
    E["Excursion evidence<br/>incidentId, raw snapshot"]
    P["Device / config / calibration"]
    B --> H
    H --> M
    M --> R
    E --> R
    E --> P
    B --> P
~~~

While raw stays in hot or cold archive, a manifest locates source files/partitions. Once raw expires and is purged per policy, the manifest can prove **which sources were used in the past**, yet cannot reconstruct sample values itself. Designers must state **how deep traceability goes and for how long**.

### Hashes, Signatures, and Integrity

Checksums/hashes detect whether a retrieved raw file differs from what the manifest recorded. However:

- A hash **does not replace** raw sample content.
- A plain hash **does not prove** who created the data or when.
- Signatures, immutable storage, access controls, operation logs, and clock synchronization may be required for formal investigations.
- Store hashing algorithm, manifest version, and canonicalization method; you cannot verify the same digest if row ordering or formatting shifts arbitrarily.

A retention policy with strict evidentiary needs must be designed **before raw data gets purged**, not after a dispute begins.

## 7. Two Clocks: Occurrence Time vs. Receipt Time

A device measures a sample at 10:15, but due to lost connectivity the gateway delivers it to the server at 12:00:

~~~text
observed_at  = 2026-10-15 10:15:00Z  (measurement time)
received_at  = 2026-10-15 12:00:00Z  (platform receipt time)
bucket_start = 2026-10-15 10:00:00Z  (1-hour UTC bucket)
~~~

Assigning samples to buckets by `received_at` corrupts hourly measurement semantics. Relying blindly on `observed_at` without detecting skewed device clocks misclassifies data too. Design must:

1. Define which timestamp is **authoritative event time**, its trust source, and clock-correction rules.
2. Store receipt time to measure latency and reconcile offline reconnects.
3. Apply consistent timezone/cutoff rules per bucket type.
4. Flag suspicious records when `observed_at` sits too far in the future/past relative to policy.
5. Distinguish **late-arriving** events from **bad timestamps**; they need different handling.

### A Day Is Not Always 24 Hours

If an organization operates warehouses across timezones, a business day might start at 06:00 local time; regions observing DST also have 23- or 25-hour local days. A UTC 1-hour rollup has 24 buckets per UTC day, yet you cannot assume every **local day** contains 24 local-hour buckets.

Store **`bucket_start` in UTC** at minute/hour tiers, then compute **`business_date`** using the device/warehouse timezone and effective cutoff policy. When historical timezone or cutoff definitions change, retain calendar policy versions if past reports must be reproduced.

## 8. PostgreSQL Data Model: Raw and Rollups

The examples below use PostgreSQL to clarify grain, constraints, partitioning, and SQL aggregation. A specialized time-series database or columnar warehouse may use different TTLs, compression, or materialized views; **do not treat this SQL as the mandatory optimal architecture for every production workload**.

### 8.1. Raw Table Partitioned by Event Time

~~~sql
CREATE SCHEMA IF NOT EXISTS telemetry;

CREATE TABLE telemetry.sensor_reading (
    tenant_id UUID NOT NULL,
    device_id UUID NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    source_sequence BIGINT NOT NULL CHECK (source_sequence >= 0),
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    temperature_c NUMERIC(8, 3) NOT NULL,
    quality_code VARCHAR(12) NOT NULL
        CHECK (quality_code IN ('VALID', 'SUSPECT', 'INVALID')),
    source_batch_id UUID,
    PRIMARY KEY (tenant_id, device_id, observed_at, source_sequence)
) PARTITION BY RANGE (observed_at);

-- Example partition: all observed_at in November 2026 UTC.
CREATE TABLE telemetry.sensor_reading_2026_11
    PARTITION OF telemetry.sensor_reading
    FOR VALUES FROM ('2026-11-01 00:00:00+00')
               TO   ('2026-12-01 00:00:00+00');

CREATE INDEX sensor_reading_device_time
    ON telemetry.sensor_reading (tenant_id, device_id, observed_at DESC);
~~~

**Why partition by `observed_at`?** Queries commonly filter by measurement intervals; retention archival/deletion by event age can also operate on monthly/daily partitions. Practical constraints apply:

- PostgreSQL requires **unique keys on partitioned tables to include the partition key**; the PK above includes `observed_at`. It **does not guarantee** `(tenantId, deviceId, sourceSequence)` uniqueness if the same sequence arrives with a different timestamp. If the source promises sequence as stable identity, add a separate ingest ledger/dedup key or upstream deduplication before insert.
- `sourceSequence` can reset on device reboots or firmware updates. Include `bootSessionId`/`sourceEpoch` or a truly invariant `eventId` if so.
- If the same PK is re-sent with a different temperature, **`ON CONFLICT DO NOTHING`** can hide corrections; define a conflict/correction policy.
- Late-arriving data may target an archived or dropped partition; handle explicitly rather than silently recreating expired partitions.
- When multiple tenants with different retention terms share one time partition, **`DROP`ping the whole partition** risks deleting un-expired or held data. Separate storage by retention class, run selective deletes, or manage archives appropriately.
- A valid timestamp format does not prove the device clock is accurate; validate clock sanity and quality in ingestion.

If full correction lineage is needed, store a separate correction log or raw versions instead of overwriting measured temperatures in place and losing original values.

### 8.2. Hourly Rollup Table

~~~sql
CREATE TABLE telemetry.temperature_hourly (
    tenant_id UUID NOT NULL,
    device_id UUID NOT NULL,
    bucket_start TIMESTAMPTZ NOT NULL,
    observed_count BIGINT NOT NULL CHECK (observed_count >= 0),
    valid_count BIGINT NOT NULL CHECK (valid_count >= 0),
    suspect_count BIGINT NOT NULL CHECK (suspect_count >= 0),
    invalid_count BIGINT NOT NULL CHECK (invalid_count >= 0),
    temperature_sum NUMERIC(24, 6) NOT NULL DEFAULT 0,
    temperature_min NUMERIC(8, 3),
    temperature_max NUMERIC(8, 3),
    source_watermark TIMESTAMPTZ,
    transform_version INTEGER NOT NULL CHECK (transform_version > 0),
    rollup_version BIGINT NOT NULL DEFAULT 1 CHECK (rollup_version > 0),
    is_finalized BOOLEAN NOT NULL DEFAULT FALSE,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, device_id, bucket_start),
    CHECK (observed_count = valid_count + suspect_count + invalid_count),
    CHECK (
        (valid_count = 0 AND temperature_min IS NULL
         AND temperature_max IS NULL)
        OR
        (valid_count > 0 AND temperature_min IS NOT NULL
         AND temperature_max IS NOT NULL
         AND temperature_min <= temperature_max)
    )
);

CREATE INDEX temperature_hourly_device_time
    ON telemetry.temperature_hourly
        (tenant_id, device_id, bucket_start DESC);
~~~

These columns store **sufficient statistics to merge sample-based averages, min/max, and quality counts**. For SLA continuous-breach duration, add dedicated duration/segment fields rather than trying to infer them from `temperature_sum`.

There is no physical `average` column, avoiding redundant derived data that drifts out of sync. If BI tools need `average`, expose it via a derived expression/view with explicit formula and precision.

### 8.3. Computing a Full Bucket Interval Without Partial Overwrites

PostgreSQL 14+ provides `date_bin` for fixed-stride bucketing. Recomputing **a full UTC hour**:

~~~sql
INSERT INTO telemetry.temperature_hourly AS target (
    tenant_id, device_id, bucket_start,
    observed_count, valid_count, suspect_count, invalid_count,
    temperature_sum, temperature_min, temperature_max,
    source_watermark, transform_version, is_finalized
)
SELECT
    r.tenant_id,
    r.device_id,
    date_bin(
        INTERVAL '1 hour',
        r.observed_at,
        TIMESTAMPTZ '1970-01-01 00:00:00+00'
    ) AS bucket_start,
    COUNT(*) AS observed_count,
    COUNT(*) FILTER (WHERE quality_code = 'VALID') AS valid_count,
    COUNT(*) FILTER (WHERE quality_code = 'SUSPECT') AS suspect_count,
    COUNT(*) FILTER (WHERE quality_code = 'INVALID') AS invalid_count,
    COALESCE(
        SUM(temperature_c) FILTER (WHERE quality_code = 'VALID'),
        0
    ) AS temperature_sum,
    MIN(temperature_c) FILTER (WHERE quality_code = 'VALID'),
    MAX(temperature_c) FILTER (WHERE quality_code = 'VALID'),
    :source_watermark,
    :transform_version,
    FALSE
FROM telemetry.sensor_reading AS r
WHERE r.tenant_id = :tenant_id
  AND r.device_id = :device_id
  AND r.observed_at >= :bucket_start
  AND r.observed_at <  :bucket_end
GROUP BY r.tenant_id, r.device_id,
    date_bin(
        INTERVAL '1 hour',
        r.observed_at,
        TIMESTAMPTZ '1970-01-01 00:00:00+00'
    )
ON CONFLICT (tenant_id, device_id, bucket_start)
DO UPDATE SET
    observed_count = EXCLUDED.observed_count,
    valid_count = EXCLUDED.valid_count,
    suspect_count = EXCLUDED.suspect_count,
    invalid_count = EXCLUDED.invalid_count,
    temperature_sum = EXCLUDED.temperature_sum,
    temperature_min = EXCLUDED.temperature_min,
    temperature_max = EXCLUDED.temperature_max,
    source_watermark = EXCLUDED.source_watermark,
    transform_version = EXCLUDED.transform_version,
    rollup_version = target.rollup_version + 1,
    is_finalized = FALSE,
    computed_at = CURRENT_TIMESTAMP;
~~~

**Preconditions for using this statement safely:**

1. `:bucket_start` and `:bucket_end` must span **an exact hour** aligned to `date_bin`; never scan just 15 minutes and overwrite a full 1-hour bucket with partial data.
2. Raw must be complete up to the **agreed watermark/lateness policy**, or the bucket must be flagged provisional/incomplete.
3. Only `VALID` samples feed `min`/`max`/`sum` in this policy example; if quality criteria change, increment `transformVersion` and decide whether to backfill history.
4. When raw has **no samples**, `SELECT` emits zero rows. If empty buckets with `validCount = 0` are needed, generate the bucket/device schedule from an authoritative active calendar and `LEFT JOIN`; never equate "no rows" with `0 °C`.
5. If a rollup is already finalized, the pipeline must verify **reopen/restate policy** before overwriting; the SQL shows the recompute branch without approval gating for closed periods.
6. Concurrent batches updating the same keys need versioning/cutoff checks and proper transactions so older runs never overwrite newer results.

### 8.4. Computing Accurate Averages from Hourly Rollups

~~~sql
SELECT
    tenant_id,
    device_id,
    SUM(temperature_sum)
        / NULLIF(SUM(valid_count), 0) AS sample_weighted_avg_c,
    MIN(temperature_min) AS min_c,
    MAX(temperature_max) AS max_c,
    SUM(valid_count) AS valid_samples,
    SUM(observed_count) AS all_received_samples
FROM telemetry.temperature_hourly
WHERE tenant_id = :tenant_id
  AND device_id = :device_id
  AND bucket_start >= TIMESTAMPTZ '2026-10-01 00:00:00+00'
  AND bucket_start <  TIMESTAMPTZ '2026-10-02 00:00:00+00'
  AND is_finalized = TRUE
GROUP BY tenant_id, device_id;
~~~

If some hours are not yet finalized, this query **aggregates only finalized hours** and does not prove all 24 hours are complete. To report a complete day, verify expected buckets, completion status, and watermarks—never write `WHERE is_finalized = TRUE` alone and present the output as a full day.

For local business-day grouping, re-slice timestamp ranges by timezone/cutoff rather than relabeling days after aggregating over the wrong span.

## 9. There Is No Single TTL Across Raw, Rollups, and Evidence

A policy can be described using fields such as:

~~~text
retention_class       = RAW_NORMAL / ROLLUP_5M / ROLLUP_1H /
                        DAILY / INCIDENT_EVIDENCE / AUDIT
scope                 = tenant, device group, data category
time_anchor           = observed_at / bucket_end / incident_closed_at
hot_until             = time_anchor + hot_duration
archive_until         = time_anchor + total_retention
delete_after          = archive_until, unless a valid hold applies
traceability_level    = aggregate-only / raw-replay / evidence-package
late_arrival_policy   = accept / restate / quarantine / reject
approver_and_version  = who approved the policy, which version
~~~

Delete data only after verifying:

- **Which policy applies to which data?** Operational sensor readings differ from employee location events or incident evidence.
- **From what anchor is retention measured?** Raw normally starts at measurement time; incident files may start when an incident closes or settles, per contract.
- **Have required rollups been built and reconciled?** Never purge raw before dependent tiers are verified.
- **Is cold archive genuinely retrievable?** Copying files to object storage proves nothing without indexes, manifests, access permissions, and tested restore procedures.
- **Are any records under an investigative hold?** A hold needs target scope, reason, approver, scope manifest, and review expiration.
- **Are personal-data deletion policies respected?** Never keep everything forever just because a future report might want it.

### Ensuring Rollups Do Not Destroy Incident Evidence

Suppose a rule defines a breach as temperature above 8 °C **continuously for at least 10 minutes**. An hourly `max = 10 °C` does not prove 10 continuous minutes; an hourly `avg = 5 °C` does not rule out a violation either. You need:

1. An anomaly detector operating on **sufficiently high-resolution series**.
2. A crisp definition of continuity: max allowed gap in seconds, interpolation rules, and whether `SUSPECT` samples count.
3. When a breach confirms, record an **excursion event** with start/end, `thresholdRuleVersion`, device, effective period, and supporting readings.
4. For independent inspection, preserve the **relevant raw slice** (e.g., a chosen margin before/after the incident) plus metadata and checksum/manifest—not `min/max` alone.
5. Capture evidence before retention purges the underlying raw data. While an incident stays open, policies may extend holds via formal approval.

If telemetry drops out for a 20-minute gap, **you cannot conclude no violation occurred** merely because remaining readings stayed below the threshold. Policies must represent missing/unverifiable coverage explicitly.

## 10. Designing Traceability Records for Incidents

A logical evidence structure:

| Field | Example | Why Needed |
| --- | --- | --- |
| `incidentId` | EX-901 | Identifies incident independently of raw points |
| `tenantId` / `deviceId` | T, D | Identifies source and access boundary |
| `eventStart` / `eventEnd` | 10:11–10:28Z | Event time span |
| `detectedAt` / `confirmedAt` | 10:12 / 10:45Z | Separates detection from confirmation |
| `policyId` / `policyVersion` | TEMP_HIGH / v4 | Records active thresholds and rules |
| `sourceClockQuality` | Synced / Unsynced / Suspect | Evaluates timestamp trustworthiness |
| `evidenceObjectRef` | Access-controlled internal URI | Retrieves preserved raw slice |
| `evidenceChecksum` | Digest of canonicalized raw bundle | Detects tampering or corruption |
| `manifestVersion` / `schemaVersion` | M1 / S3 | Interprets source bundle accurately |
| `transformVersion` | anomaly-detector v7 | Identifies algorithm applied |
| `reviewer` / `decision` | Reviewer and determination | Business decision audit trail |
| `retentionClass` / `holdId` | CRITICAL_INCIDENT / H-22 | Protects evidence under retention policy |

**An evidence package has its own lifecycle**, distinct from retaining all raw data forever. It may carry tighter access controls than operational charts, logged export workflows, and scheduled destruction/anonymization upon expiration.

### Traceability Chain When a Report Is Challenged

Suppose a report states "October had 12 threshold breaches." A clear traceability chain:

~~~text
report_run_id R-2026-10
  → metric "confirmed_excursions" version 4
  → incident IDs EX-901 ... EX-912
  → each incident links threshold rule/version and decision
  → evidence manifest, source device, time window
  → raw archive (if still within retention)
  → checksum, download permissions, evidence export audit
~~~

Once raw has been legitimately purged, explanations must stay strictly within remaining evidence; never claim you can **replay every individual reading** once raw access is gone.

## 11. Binding Data Retention to Partitions and Storage Lifecycles

In relational systems, time partitioning simplifies managing expired data batches. Yet dropping entire partitions must be gated by policy, not a blind cron job:

~~~mermaid
flowchart LR
    P["Raw partition nearing expiry"]
    W{"Rollups complete and reconciled?"}
    H{"Hold or special retention active?"}
    A["Archive raw + manifest<br/>verify restorable"]
    D["Detach / drop or controlled delete"]
    Q["Retain or handle exception"]
    L["Audit: scope, policy version, timestamp"]
    P --> W
    W -->|"No"| Q
    W -->|"Yes"| H
    H -->|"Yes"| Q
    H -->|"No"| A
    A -->|"PASS"| D
    D --> L
~~~

In the 30-day hot + 150-day archive example:

1. On day D, raw buckets with event times before D−30 move out of the hot tier per policy.
2. Rollups are built and reconciled before removing/evicting hot source rows.
3. Cold archive retains raw up to 180 days total with manifests and lookup by tenant/device/time.
4. Upon total expiry, delete only if no legal/business hold or overriding policy applies.
5. Raw slices copied into incident records may follow **separate retention**; never freeze an entire multi-tenant partition indefinitely just because one slice is under investigation.

**Time partitioning alone cannot satisfy per-tenant retention differences.** If multiple tenants share one partition where one requires 180 days and another requires 365 days, you cannot `DROP` the partition while protected data remains. Use policy-tiered physical separation, selective deletion, or dedicated archive management.

**Operational illustration—never run blindly:**

~~~sql
-- Execute only after approval, cutoff verification,
-- rollup reconciliation, and archive/hold/backup policy checks.
-- This detaches an example time partition; it is NOT an automatic TTL command.
--
-- ALTER TABLE telemetry.sensor_reading
--   DETACH PARTITION telemetry.sensor_reading_2026_11;
--
-- Handle the detached table only after data is archived/deleted
-- per policy; never DROP the active month while evidence
-- or late-arriving data remains pending.
~~~

While partition commands themselves run fast, **the time required for safety checks** and protecting un-expired data is the true core of retention operations.

## 12. Late Data and Historical Fixes After Bucket Finalization

This is one of the toughest challenges in multi-tier retention. Scenario:

- 10:00–11:00: devices emit normal samples.
- 11:10: pipeline finalizes the 10:00 bucket and builds the hourly rollup.
- 12:00: gateway transmits an offline-buffered 10:15 reading after reconnecting.
- 40 days later: hot raw for that day has moved to cold archive, while rollups remain active.

Without explicit rules, 10:00 hourly figures and all dependent daily/monthly rollups **drift**.

### Watermarks and Late-Arrival Windows

A **watermark** is a conditional commitment on event-time progress, not a promise that older data no longer exists anywhere in the world. You can define:

~~~text
UTC bucket 10:00-11:00
allowed lateness = 15 minutes (illustrative example)
provisional until = 11:15 if source checkpoints suffice
finalized when = source watermark passes bucket end + policy checks PASS
~~~

When a sample arrives after finalization:

| Policy | Behavior | Consequences to Control |
| --- | --- | --- |
| Reopen / restate | Recompute hourly bucket and dependent daily/monthly rollups | Past reports may change; store versions/audit |
| Record adjustment | Emit separate adjustment record; KPI sums base + adjustments | Avoid updating base AND adding adjustment twice |
| Quarantine / manual review | Route late sample to review queue for investigation | Needs clear SLA and queue state |
| Drop by policy | Keep closed bucket unchanged; count dropped samples | Acceptable only when business/audit signs off |

For temperature safety data, never default to **drop**. A late sample can carry a critical breach. Choose based on domain risk and obligations.

### Fixing Rollups After Raw Has Been Purged

With only `average`/`min`/`max`/`count`, you cannot arbitrarily recompute **every statistic** over a corrected sample set:

- Adding a new valid sample can update `sum`, `count`, and potentially `min`/`max`.
- **Removing or editing a sample that formed `min` or `max`** cannot reconstruct the new `min`/`max` without raw data or auxiliary sketches.
- Recomputing percentiles, exceedance durations, or continuous-breach detection requires raw or specialized detailed state.

Align **raw editability retention** with **correction windows and reporting close SLAs**, or maintain archives/evidence to rebuild when necessary. Never promise full recomputation after purging detailed inputs.

## 13. Cost, Footprint, and Choosing Query Serving Tiers

You cannot evaluate retention trade-offs without estimating volume and query patterns. Define variables:

- \(N\): number of devices;
- \(f\): expected samples per device per day;
- \(s_{raw}\): average stored bytes per sample, **including engine-specific index/metadata/compression estimates**;
- \(R_{raw}\): days raw is retained;
- \(b\): buckets generated per device per day;
- \(s_{bucket}\): bytes per rollup row;
- \(R_{bucket}\): days rollups are retained.

Rough estimate:

\[
\text{RawBytes}\approx N \times f \times R_{raw}\times s_{raw},
\]

\[
\text{RollupBytes}\approx N \times b \times R_{bucket}
\times s_{bucket}.
\]

With replicas, indexes, cold storage, data transfer, and backups, total cost exceeds raw payload estimates alone. Measure **compression ratio, cardinality, partition sizes, throughput, restore times, p95 query latency, and storage unit prices** on your target engine.

### Query Tier Selection Matrix

| Requirement | Candidate Tier | Caveat |
| --- | --- | --- |
| Chart of last 30 minutes | Raw / 1-minute | Preserves short swings, higher sample query load |
| 24-hour average temperature | 1-hour rollup or raw | Needs weighted `sum`/`count` and complete buckets |
| Monthly peak temperature | 1-hour rollup with `max` | Exact timestamp of peak unknown without `argmax` |
| Daily trend over 3 years | Daily rollup | Cannot investigate multi-minute fluctuations |
| Detect 12 continuous minutes above limit | Raw or duration-aware excursion events | Daily `avg`/`min`/`max` cannot answer |
| Reconcile disputed report | Raw archive + lineage or evidence package | Cannot replay once raw source is purged |
| Dashboard refreshing every 5 seconds | Near-real-time stream/projection | Freshness is completely separate from retention |

**Cache is a serving tier, not primary retention.** A dashboard with a 15-minute cache may read 30-day raw underneath; clearing cache does not erase ground truth, and keeping cache never replaces raw evidence when required.

## 14. Separating Routine Data, Anomalies, and Personal Data

Do not retain everything under the longest retention rule of your highest-risk category:

- **Routine telemetry:** progressively downsample and purge raw on schedule.
- **Alert/excursion events:** may require retaining an identified record, investigation status, rule version, and source links longer than hourly averages.
- **Confirmed incident evidence:** may need a scoped raw/metadata package per policy.
- **Location / personal data:** requires explicit purpose, narrow access, and minimal retention per policy and applicable obligations.
- **Access and audit logs:** follow dedicated retention; never let logs carrying sensitive payloads live forever by default.

### Retention Holds and Deletion Rights

A hold must not be an unmanaged boolean flag. A hold record can include:

| Field | Purpose |
| --- | --- |
| `holdId`, `scope` | Pinpoints exact tenant/device/time/object covered |
| `reasonCode` | Explains why data must be held |
| `approverId`, `createdAt` | Who approved it and when |
| `reviewBy` / `expiresAt` | When to review or release |
| `affectedObjects` / `manifest` | Which raw/rollup/evidence objects are in scope |
| `releaseAt`, `releasedBy` | Audit trail for lifting the hold |

A personal-data deletion request can conflict with legitimate retention duties. Never hard-code ad-hoc universal rules. Systems need approved policies, data minimization, separation of identifying metadata, access restrictions, and formal review processes when obligations compete.

When raw data lives in archives, backups, or partner stores, deleting from hot tables **does not prove data disappeared from every copy**. State deletion scope, backup expiry schedules, and execution guarantees honestly.

## 15. Across Physical Data Models: Relational, Document, Time-Series, and Analytical

| Storage Approach | How Multi-Tier Retention Fits | Pitfalls |
| --- | --- | --- |
| Relational / PostgreSQL partitions | Event-time raw partitions, separate rollup tables, policy-driven archive/drop | Multi-tenant/hold mixing inside partitions; late `UPDATE`s and hot indexes |
| Time-series engine | Retention/compression policies, continuous aggregates or materialized views per product | Failing to check dependencies before TTL; assuming auto-rollups support corrections |
| Document store | Raw docs with TTL indexes/expiration; bucketed rollup collections | TTLs are not instantaneous; rollups may lag behind deletions |
| Object store / data lake | Manifest-tracked raw files, partitioning, lifecycle rules, table snapshots | Orphaned files/backups or broken manifest links; compaction/versioning overhead |
| Columnar analytical warehouse | Multi-tier rollups, partitioning, clustering, materialized KPIs | Broad scans, grain-mixing queries, unsuitable as operational write guard |
| Graph | Links incident–device–rule–evidence–approver for root-cause graphs | Graph edges do not replace raw readings, checksums, or real retention enforcement |

Switching storage engines never removes core invariants: **grain, event time, policy version, idempotency, completeness, traceability, and data ownership**. A store with a "90-day TTL" toggle must still prove what gets deleted and which evidence stays protected.

### Choosing Between Recomputation and Storing Published Snapshots

For official KPIs, two strategies apply:

1. **Recomputable:** retain sufficient raw/metadata to recompute any bucket inside the published window.
2. **Versioned / published result:** store finalized values, `transformVersion`, input lineage, and correction history, accepting that expired raw can no longer replay everything from scratch.

You can combine both by time horizon or event class. Above all, **never promise full recomputation if retention rules already purge the required inputs**.

## 16. Testing Retention and Traceability as System Capabilities

Do not test only that data disappears after TTL expires. Also verify that data **does not disappear prematurely** and reports stay accurate:

| Scenario | Outcome to Prove |
| --- | --- |
| Raw reaches 30 days; rollup exists but un-reconciled | Precondition check blocks premature deletion/eviction |
| Raw expires hot tier and archives | Manifest locates file; checksum matches; authorized restore succeeds |
| Raw reaches 180 days with no hold | Controlled deletion executes with audit log and copy-scope tracking |
| Raw slice tied to open incident | Evidence slice stays protected per policy without accidental purge |
| Same sample re-sent twice | Not double-counted; conflicting payloads flagged |
| 10:15 sample arrives at 12:00 | 10:00 event-time bucket updated per late-data policy |
| Closed bucket receives correction | Restatement/adjustment versioned and downstream updated |
| Bucket has 0 valid samples | Average is `NULL`, never reported as 0 °C |
| Two buckets have unequal sample counts | Merged average uses `sum/count`, not `AVG` of averages |
| 5 minutes missing within an hour | Completeness flag/coverage exposes the gap |
| One 10 °C point among fifty-nine 3 °C points | `max` still surfaces 10 °C despite low average |
| Threshold config shifts from 8 °C to 7 °C | Historical outputs record `policyVersion`; backfill policy explicit |
| Source resets sequence or clock drifts | Tagged with quality/epoch and reconciled without corrupting dedup |
| Tenant with longer retention shares partition | Partition is not dropped prematurely |
| Request to audit a 2-year-old report | Returns exact remaining evidence level and whether raw replay is available |

### Operational Metrics to Track

- Ingestion lag by **event time** and source.
- Valid/invalid sample counts and missing rate against defined cadence.
- Provisional vs. finalized buckets, incomplete buckets, and restatement counts.
- Duplicate events and payload conflicts.
- Raw-vs.-rollup reconciliation drift by device and day.
- Archive restore success rate and manifest/hash verification failures.
- Active holds and holds overdue for review.
- Storage footprint/cost across hot raw, cold raw, 5-minute, hourly, daily, and evidence tiers.
- Unanswerable audit/investigation requests due to missing data, with root causes.

These metrics reveal whether retention truly serves **intended usage** or merely cuts storage indiscriminately.

## 17. Practice Exercise: Smart Electric Meter Telemetry

**Context:** A building management firm operates 2,000 smart electric meters. Each meter emits cumulative energy (kWh) every 15 minutes; counters occasionally reset after hardware replacement. The platform must:

- Display recent power/energy per apartment.
- Report daily and monthly electricity consumption over 5 years.
- Audit bills when tenants dispute charges from 18 months ago.
- Detect silent meters or anomalous drops in readings.
- Limit storage of resident-linked detail per privacy policy.

### Questions

1. Write the **grain** for raw, hourly rollup, daily rollup, and dispute records. What keys prevent duplicates when gateways resend?
2. Propose a **retention table** across hot/cold raw, 1-hour, 1-day, and evidence tiers. Which numbers are assumptions requiring authoritative sign-off?
3. Meters report **cumulative kWh**, not 15-minute incremental consumption. Can you directly sum all kWh readings in a day to get total energy used? Describe delta calculation and reset handling.
4. If you kept only hourly average kWh readings, could you audit an 18-month-old bill? What start/end meter readings, valid deltas, corrections, tariff policies, and evidence must be retained?
5. A 17:45 reading arrives after the 17:00 rollup finalized; how should daily rollups and billing stay consistent?
6. If a tenant disputes a bill from a month whose raw data is expiring yet policy requires re-verification, what must happen **before TTL executes**?
7. Design two tests for **duplicate sequences** and **counter resets**, one test for **late data**, and one test for **investigative holds**.

### Reference Solution Guide

**Raw grain:** one meter reading `(tenantId, meterId, sourceEpoch, sequence, observedAt)` recording `cumulativeKwh`, `receivedAt`, and quality. If devices reset sequence numbers, `sourceEpoch`/`bootSessionId` separates emission runs; `observedAt` alone may not uniquely identify samples.

**Never `SUM` cumulative kWh:** values `100, 101, 103` are **cumulative balances**. Consumption across that span is `103 − 100 = 3 kWh`, not `304 kWh`. A reset from `103` down to `0` requires a reset/meter-swap event marker and valid delta logic—never recording `−103 kWh` as negative consumption.

**Hourly/daily rollups:** store `meterStartKwh`, `meterEndKwh`, `validConsumptionKwh`, coverage, `resetCount`, `sourceEventRange`, `policyVersion`, and finalization timestamp. One day may span multiple segments across resets. Total consumption comes from **validated deltas**, never from averaging cumulative readings.

**Billing disputes:** trace meter ID, readings used, billing cutoff, applied tariff/rate table, meter replacements, corrections, and raw/evidence slices if contracts mandate full recomputation. Storing only the final invoice amount without rules and inputs prevents reconciliation.

**Late data:** never abandon readings arriving for closed periods; run policy-compliant reopen/restate or billing adjustment workflows with invoice versioning, customer reconciliation, and approval logs. **Holds:** scope must be identified and applied prior to deletion, then released once the dispute concludes legitimately.

## 18. Decision Checklist and Conclusion

- Does every tier clearly specify **grain, keys, cadence, and bucket/timezone**?
- Does the retention policy document **total term, hot/cold tiers, time anchor, tenant scope, and approval**?
- Have you identified exactly which KPIs can be recomputed from **`sum`/`count`/`min`/`max`** and which require raw or specialized state?
- Are you avoiding unweighted averages of averages, defaulting missing data to 0, and conflating sample mean with time-weighted mean?
- Do rollups carry quality counts, completeness, source watermarks, and `transformVersion` to show data trustworthiness?
- Before deleting raw data, do you reconcile rollups, generate manifests/archives/evidence, and check holds?
- Does the committed traceability level state clearly whether it goes **to raw samples**, **to statistics**, or **to incident evidence packages**?
- Once raw is purged, do you avoid claiming full raw replay remains possible?
- Are event time, ingest time, business day, and retention cutoff cleanly separated and consistent?
- Do workflows cover late events, corrections, clock drift, duplicates, expired partitions, and report versions?
- Are data privacy, backup expiry, access controls, and audit retention evaluated separately instead of keeping everything for the longest horizon?
- Have you actually tested archive restores, active incident holds, rollup reconciliation, and safe deletion?

**Conclusion:** Time-series retention must be defined **by resolution tier and intended obligation**, not via one uniform TTL across every table. Raw measurements support diagnosis and reprocessing; minute/hour/day rollups enable long-term analytics at lower cost; incident records and lineage preserve explainability and proof at the committed tier. A sound design states explicitly **what is kept, until when, anchored on which timestamp, to what degree it stays reproducible, and which detail becomes permanently unrecoverable**. Answering those questions alongside grain, statistics, transactions, traceability policies, and access controls keeps a data model verifiable and evolvable without silently sacrificing business correctness.
