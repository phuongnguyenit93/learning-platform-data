# Data Expiration Policies and TTL Mechanisms in MongoDB Time Series

Temperature monitoring, IoT device tracking, server metrics, and operational telemetry continuously generate **streams of events with ever-increasing timestamps**. After a certain period, most raw readings are no longer needed for daily queries, yet they still consume disk, index space, and backup resources.

For example, consider a system ingesting:

~~~text
10,000 sensors
  × 1 measurement every 10 seconds
  × 86,400 seconds/day
  ÷ 10 seconds/measurement
  = 86,400,000 measurements per day
~~~

If every measurement is kept forever, accumulated volume grows rapidly. A sensible **retention** policy might require:

- Keeping **raw data** for 7 days for incident investigation.
- Keeping **hourly aggregates** for 90 days for trend analysis.
- Keeping **daily reports** for one year.
- Purging expired data when no additional retention mandate applies.

MongoDB supports automatic removal of expired data via **TTL – Time To Live**. For **time series collections**, TTL behaves differently from regular collections: MongoDB organizes measurements inside **buckets**, and expiration generally removes **entire expired buckets** rather than deleting individual measurements at the exact second they reach threshold age.

This lesson focuses on **data expiration policies and TTL mechanisms in time series contexts**, covering:

1. Distinguishing TTL, retention, archiving, downsampling, and windowed queries.
2. Creating time series collections with **`expireAfterSeconds`** and choosing `timeField`/`metaField`.
3. Understanding expiration thresholds by timestamp, bucket, granularity, and the TTL monitor.
4. Enabling, increasing, decreasing, or disabling TTL on existing collections via **`collMod`**.
5. Applying **partial TTL indexes on `metaField`** in supported versions.
6. Handling late data, bad timestamps, TTL backlogs, bulk deletions, and preserving reports.
7. Designing multi-tier storage, operational monitoring, Java/Spring Data MongoDB code, and practice exercises.

All write/delete/`collMod` commands in this lesson apply strictly to **test databases**. In production, verify retention policies, irreversible data loss risks, and backup plans before modifying TTL.

## 1. Retention Policy and TTL Are Not the Same Thing

A **retention policy** is a **business rule** answering: which data categories are kept, for how long, when they are purged, what exceptions exist, and who approves deletion.

**TTL** is a **technical mechanism** allowing MongoDB to automatically clean up aged-out documents/buckets based on a timestamp and configured seconds.

Example policy:

| Data tier | Resolution | Retention | Implementation approach |
|---|---|---:|---|
| Raw sensor readings | Every 10 seconds | 7 days | Time series collection with 7-day TTL |
| Hourly aggregates | Every 1 hour | 90 days | Separate summary collection, 90-day TTL |
| Daily aggregates | Every 1 day | 365 days | Separate summary collection, 365-day TTL |
| Audit or special records | Per legal requirements | Custom policy | Do not rely solely on default raw TTL |

TTL implements only **one part** of the policy. It does not generate summaries, move data to cold storage, enforce legal holds, or guarantee synchronized erasure across all backups.

### 1.1. Terms to Distinguish

| Term | Meaning | Example |
|---|---|---|
| TTL | Mechanism that auto-deletes data once eligible for expiration | Purge raw readings after 604,800 seconds |
| Retention | Organizational rule specifying how long and why data is kept | Raw kept 7 days, aggregates kept 90 days |
| Expiration threshold | Timestamp at which data becomes eligible for deletion | `timestamp + 7 days` |
| Physical deletion | Time when the background process actually removes data | May lag behind expiration threshold |
| Archiving | Moving data to another storage tier | Object storage or long-term archive |
| Downsampling | Reducing temporal resolution | Average temperature per hour |
| Aggregation | Computing summary statistics from data | Min/max/avg/count per sensor |
| Legal hold | Exception blocking deletion for compliance/litigation | An investigation requires preserving records |

### 1.2. Why Define the Policy Before Enabling TTL?

Suppose raw data captures a temperature spike during an hour. If you set a 24-hour TTL while daily reporting runs once a day and the batch job is delayed, input data can be purged **before the aggregation job reads it**.

Therefore, a safe policy accounts for:

- Maximum delay from **event time** until data is written into MongoDB.
- Latency of the **aggregation pipeline**.
- Headroom for **retrying failed jobs**.
- Time needed for **auditing, support, and incident response**.
- **Backup/restore** windows and report recovery procedures.
- Maximum acceptable disk capacity.

**Never pick a TTL solely from "wanting less disk usage".** An overly short TTL can destroy data before dependent workflows finish.

## 2. How Time Series Collections Store Data

MongoDB time series collections are specialized for records carrying a **measurement timestamp** and typically **source metadata**.

Example measurement:

~~~javascript
{
  timestamp: ISODate("2026-11-14T06:05:00.000Z"),
  sensor: {
    sensorId: "S-101",
    site: "HCM-01",
    retentionClass: "STANDARD"
  },
  temperatureC: 28.4,
  humidityPct: 76.2
}
~~~

Fields:

- **`timestamp`**: BSON Date identifying when the measurement occurred.
- **`sensor`**: sensor and grouping metadata, declared as **`metaField`**.
- **`temperatureC`**, **`humidityPct`**: measured values.

### 2.1. `timeField`, `metaField`, and `granularity`

When creating the collection:

~~~javascript
db.createCollection("sensorReadings", {
  timeseries: {
    timeField: "timestamp",
    metaField: "sensor",
    granularity: "seconds"
  }
});
~~~

**`timeField`** is required and holds a valid Date value under time series rules. **`metaField`** is optional and groups measurements sharing the same source/metadata. **`granularity`** describes typical temporal spacing so MongoDB can optimize bucketing.

Do not interpret **`granularity: "seconds"`** as restricting timestamps to whole seconds or storing one second per bucket. Granularity guides bucket span configuration for the time series.

### 2.2. MongoDB Packs Measurements into Buckets

At the logical user view:

~~~text
sensorReadings

S-101  06:00:00  temperature=28.0
S-101  06:00:10  temperature=28.1
S-101  06:00:20  temperature=28.3
S-101  06:00:30  temperature=28.2
S-102  06:00:05  temperature=27.8
~~~

In internal storage, MongoDB groups measurements with **identical `metaField`** and nearby timestamps into buckets:

~~~text
Bucket A: sensor S-101
   06:00:00
   06:00:10
   06:00:20
   06:00:30

Bucket B: sensor S-102
   06:00:05
~~~

This diagram illustrates the concept. Actual measurement counts, byte limits, bucket open/close behavior, and bucket placement depend on server version and load; do not assume those four readings are guaranteed to share one physical bucket.

### 2.3. Why Buckets Matter for TTL

A reading at `06:00` may exceed TTL age while its bucket also contains a `06:50` reading that has not yet expired. Time series TTL **does not necessarily delete the `06:00` reading immediately on its own**.

MongoDB may wait until **all measurements inside the bucket qualify for expiration**, after which the background TTL monitor removes the bucket.

This is a core difference from TTL on a regular collection, where a TTL index evaluates each document directly against the indexed Date field.

## 3. Creating a Time Series Collection with TTL Upfront

Suppose raw sensor data must be retained for **7 days**.

### 3.1. Converting Days to Seconds

~~~text
7 days × 24 hours/day × 60 minutes/hour × 60 seconds/minute
= 604,800 seconds
~~~

Common values:

| Retention | `expireAfterSeconds` |
|---|---:|
| 15 minutes | 900 |
| 1 hour | 3600 |
| 24 hours | 86400 |
| 7 days | 604800 |
| Fixed 30 days | 2592000 |
| Fixed 90 days | 7776000 |
| Fixed 365 days | 31536000 |

Note: **30 fixed days does not equal a calendar month**; 365 days does not cover leap years. TTL counts **elapsed seconds**, not "end of local calendar month".

### 3.2. Collection Creation Command

~~~javascript
use timeseries_ttl_lab

db.createCollection("sensorReadings7d", {
  timeseries: {
    timeField: "timestamp",
    metaField: "sensor",
    granularity: "seconds"
  },
  expireAfterSeconds: 604800
});
~~~

This creates a **time series collection** with automatic data-age expiration.

Meaning of **`expireAfterSeconds: 604800`**:

> A measurement with timestamp `T` is considered expired once elapsed time from `T` reaches 604,800 seconds; actual deletion still depends on bucket bounds and the TTL monitor.

TTL does not infer age from **insertion time** if `timeField` carries an older measurement timestamp; it evaluates the value stored in **`timestamp`**.

### 3.3. Sample Data

~~~javascript
const now = new Date();
const minute = 60 * 1000;
const hour = 60 * minute;
const day = 24 * hour;

db.sensorReadings7d.insertMany([
  {
    timestamp: new Date(now.getTime() - 1 * hour),
    sensor: {
      sensorId: "S-101",
      site: "HCM-01",
      retentionClass: "STANDARD"
    },
    temperatureC: 28.4
  },
  {
    timestamp: new Date(now.getTime() - 3 * day),
    sensor: {
      sensorId: "S-101",
      site: "HCM-01",
      retentionClass: "STANDARD"
    },
    temperatureC: 29.1
  },
  {
    timestamp: new Date(now.getTime() - 8 * day),
    sensor: {
      sensorId: "S-102",
      site: "HCM-02",
      retentionClass: "STANDARD"
    },
    temperatureC: 30.2
  }
]);
~~~

The **8-day-old** measurement already exceeds the 7-day threshold upon insertion, yet you should not expect it to vanish synchronously before `insertMany` returns. It can remain visible temporarily until bucket deletion criteria are met and the TTL monitor runs.

### 3.4. Standard Data Reads

~~~javascript
db.sensorReadings7d.find(
  {
    "sensor.sensorId": "S-101",
    timestamp: {
      $gte: new Date(Date.now() - 7 * 24 * 3600 * 1000)
    }
  },
  {
    _id: 0,
    timestamp: 1,
    sensor: 1,
    temperatureC: 1
  }
).sort({ timestamp: 1 });
~~~

This `find` query explicitly filters within the **7-day window evaluated at query time**. Query predicates are distinct from TTL: they govern what **queries return**, whereas TTL governs **asynchronous background deletion**.

If an API must guarantee **never displaying readings older than 7 days** at request time, apply a timestamp filter as shown rather than assuming the TTL monitor has already purged every expired second.

## 4. Computing Expiration Eligibility

Let:

- \(t_m\): measurement timestamp in `timeField`.
- \(R\): retention in seconds.
- \(t_e\): timestamp when the measurement **becomes eligible** for expiration.

Then:

\[
t_e = t_m + R
\]

Example with 24-hour retention:

~~~text
Measurement timestamp: 2026-11-14T10:15:00Z
Retention:             86,400 seconds
Eligible timestamp:    2026-11-15T10:15:00Z
~~~

**Eligibility is not a guarantee that MongoDB deletes the document at exactly 10:15:00Z the next day.** In time series collections, the bucket may contain newer readings, and background cleanup runs asynchronously.

### 4.1. Does TTL Measure from Event Time or Ingest Time?

Time series TTL evaluates the declared **`timeField`**, such as `timestamp`. If a sensor measures at 10:00, loses connectivity, and the app inserts at 16:00, two timestamps exist:

~~~text
eventTime:  10:00
ingestedAt: 16:00
~~~

When `timeField` is **`eventTime`**, 24-hour retention starts from **10:00**, not 16:00.

If business rules require keeping data **at least 24 hours after receipt**, design accordingly—for instance, using ingest time as `timeField` in an appropriate collection or a separate storage workflow. This choice impacts chronological ordering, bucketing, and statistical semantics.

### 4.2. Never Replace Date Timestamps with Strings

Wrong for `timeField`:

~~~javascript
{
  timestamp: "2026-11-14T10:15:00Z",
  temperatureC: 28.4
}
~~~

This is a **String**, not a BSON Date. When MongoDB requires a Date `timeField`, inserts fail or violate time series schema expectations.

Correct:

~~~javascript
{
  timestamp: ISODate("2026-11-14T10:15:00Z"),
  temperatureC: 28.4
}
~~~

In Java, pass **`java.util.Date`**, or configure an appropriate codec for **`java.time.Instant`**. Never expect MongoDB to convert ISO strings into Dates automatically.

### 4.3. UTC and Timezones

BSON Date represents a **UTC instant**. If a sensor reports "Nov 14 at 17:00 Vietnam time" (UTC+07), the corresponding instant is **`2026-11-14T10:00:00Z`**.

TTL in seconds measures elapsed physical duration, **independent of local DST transitions**. "Delete after 7 × 24 hours" maps cleanly to `604800` seconds. If the rule is "delete at the end of the following local calendar month", implement a dedicated lifecycle policy rather than expecting `expireAfterSeconds` to express local calendar rules.

## 5. Time Series TTL Deletes by Bucket, Not Per Measurement Instant

This is the single most important detail of time series TTL.

MongoDB packs measurements sharing `metaField` and nearby timestamps into **buckets**. One bucket can hold both older measurements past TTL and newer measurements still inside the retention window.

Because MongoDB purges **expired buckets**, a measurement does not automatically disappear the moment its individual age hits \(R\) seconds. **A bucket becomes eligible for deletion only once every measurement inside it has expired under the policy.**

### 5.1. Example Bucket with Three Measurements

Suppose:

~~~text
TTL: 1 hour = 3,600 seconds
Bucket A holds readings from the same sensor:

A1: 10:00:00
A2: 10:20:00
A3: 10:50:00
~~~

Individual eligibility:

~~~text
A1: eligible at 11:00:00
A2: eligible at 11:20:00
A3: eligible at 11:50:00
~~~

At **11:30:00**:

- A1 is 1 hour 30 minutes old.
- A2 is 1 hour 10 minutes old.
- A3 is only 40 minutes old.

Because A3 has not expired, Bucket A **is not eligible for full-bucket deletion**. A1 and A2 remain queryable even though their individual ages exceed retention.

After **11:50:00**, all readings in this example have crossed the 1-hour threshold. The bucket becomes eligible for TTL cleanup on a subsequent background pass, depending on bucket metadata and internal engine rules.

**This is a conceptual example**, not a promise that MongoDB always places those three timestamps in one physical bucket. It illustrates why bucket-level expiration lags behind per-measurement expiration.

### 5.2. Upper Bound of a Bucket

Conceptually:

~~~text
bucket.minTime = 10:00
bucket.maxTime = 10:50
TTL = 1 hour

A bucket cannot expire before the newest measurement
inside it has exceeded TTL.
~~~

MongoDB uses bucket **time-bound metadata** to evaluate expiration; exact upper bounds and retention margins depend on `granularity`/bucket configuration in your server version.

An intuitive formula:

\[
 t_{\text{bucket eligible}} \gtrsim t_{\text{latest measurement}} + R
\]

The \(\gtrsim\) symbol highlights that actual eligibility can depend on **bucket time boundaries**, rather than predicting exact-to-the-second cleanup directly from `max(timestamp)` visible to the application.

### 5.3. Background TTL Monitor

MongoDB runs a background **TTL monitor** task to purge expired data. MongoDB documentation notes a typical sweep interval of **around 60 seconds**, but:

- It is **not** a scheduled timer deleting individual documents at second 60.
- Under heavy deletion volume, the TTL monitor may require multiple passes.
- Busy nodes or failovers increase deletion lag.
- On time series collections, measurements must also wait for bucket eligibility.

Illustrative timeline:

~~~text
Last measurement in bucket ages past TTL
           |
           v
Bucket becomes eligible for expiration
           |
           v
TTL monitor picks up bucket in a sweep pass
           |
           v
MongoDB deletes bucket internally
           |
           v
Queries no longer return measurements from that bucket
~~~

Eligibility time and actual physical deletion time are **two distinct moments**.

### 5.4. Why Should Queries Still Filter by Time When TTL Is Enabled?

If an API requires "data from the last 24 hours", write:

~~~javascript
const since = new Date(Date.now() - 24 * 3600 * 1000);

db.sensorReadings7d.find({
  timestamp: { $gte: since }
});
~~~

The query enforces the **display requirement**. TTL manages **storage footprint and lifecycle**. Data older than \(R\) can persist temporarily after crossing the threshold, so TTL never acts as an exact real-time query filter.

### 5.5. TTL Is Not a Reporting Schedule

Never treat "TTL deleted a bucket" as a reliable signal that:

- A calendar day has ended.
- All sensors finished reporting.
- Daily reports are complete.
- Late-arrival checks can be skipped.

Reporting requires its own workflow with **event-time windows, watermarks, allowed lateness, job status, and idempotent retries**.

## 6. How `granularity` Affects Bucket Spans and Cleanup Lag

At collection creation, **`granularity`** shapes how MongoDB assigns measurements to time buckets.

Under MongoDB's standard granularity model:

| `granularity` | Typical max time span covered by a bucket |
|---|---|
| **`seconds`** (default) | Roughly **1 hour** |
| **`minutes`** | Roughly **24 hours** |
| **`hours`** | Roughly **30 days** |

These are **maximum spans under standard configuration**—not a guarantee every bucket spans that exact duration. MongoDB may close buckets earlier due to size limits, counts, or metadata.

### 6.1. Why Larger `granularity` Can Delay Deletion

Suppose a collection has a 24-hour TTL:

~~~text
granularity = "seconds"
  measurements within one bucket cover a narrower time span

granularity = "hours"
  a single bucket can span a much wider time window
~~~

If a bucket spans a wide window from start to end, older readings must wait for the newest reading in that bucket to expire. Consequently, **query-visible retention can stretch well beyond a single measurement's TTL** when bucket spans are large.

Never pick **`granularity: "hours"`** merely for smaller indexes and expect data to disappear exactly 24 hours after each measurement. Match `granularity` to **sampling cadence, query patterns, bucket size, and deletion SLAs**.

### 6.2. `granularity` Is Not a Retention Period

These two settings are independent:

~~~javascript
db.createCollection("granularityDemo", {
  timeseries: {
    timeField: "timestamp",
    metaField: "sensor",
    granularity: "minutes"
  },
  expireAfterSeconds: 604800
});
~~~

In this example:

- **`granularity: "minutes"`** guides bucket structure.
- **`expireAfterSeconds: 604800`** sets a 7-day retention period.

`granularity: "minutes"` never causes data to expire after one minute.

### 6.3. Changing `granularity` After Data Exists

Some MongoDB versions allow **increasing** `granularity` toward wider bucket spans via **`collMod`**:

~~~javascript
db.runCommand({
  collMod: "granularityDemo",
  timeseries: {
    granularity: "hours"
  }
});
~~~

Do not treat this as freely reversible like TTL. Restrictions on altering `granularity` and bucket settings depend on server version; in many cases **you cannot decrease `granularity`** with a reverse `collMod`.

Before changing it, evaluate consequences on bucketing, operations, and expiration lag. **This alters collection storage behavior**, not a shortcut to fix retention policies.

### 6.4. Custom Bucket Spans in Newer Versions

In versions supporting custom bucketing, time series collections accept:

- **`bucketMaxSpanSeconds`**
- **`bucketRoundingSeconds`**

in place of standard `granularity`, subject to version bounds and rules.

Illustrative configuration on a supporting server:

~~~javascript
db.createCollection("customBucketReadings", {
  timeseries: {
    timeField: "timestamp",
    metaField: "sensor",
    bucketMaxSpanSeconds: 3600,
    bucketRoundingSeconds: 3600
  },
  expireAfterSeconds: 86400
});
~~~

Here the bucket span is configured explicitly instead of using **`granularity`**. Versions typically require both values to be equal and within valid bounds.

**Never combine `granularity` and custom bucketing** simultaneously unless explicitly supported. Verify your MongoDB server version and FCV before deploying to production.

### 6.5. What If Exact-Time Deletion SLAs Are Mandatory?

If a requirement states "data must never be accessible after exactly 24 hours":

- Time series TTL **must not be the sole access barrier**.
- Enforce timestamp filters on all data-serving queries.
- If strict physical erasure by a hard deadline is mandated, build and verify a dedicated purge mechanism; background bucket TTL does not guarantee second-level erasure.
- Manage backups, replicas, exports, and downstream copies as well.

Legal erasure deadlines follow different standards from "24h TTL to save disk". Never evaluate both under the same acceptance test.

## 7. Time Series TTL vs. TTL Indexes on Regular Collections

MongoDB implements TTL on **regular collections** via a **TTL index** on a Date field:

~~~javascript
db.normalEvents.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 86400 }
);
~~~

On time series collections, the standard mechanism sets **`expireAfterSeconds` as a collection option**:

~~~javascript
db.createCollection("readings24h", {
  timeseries: {
    timeField: "timestamp",
    metaField: "sensor",
    granularity: "seconds"
  },
  expireAfterSeconds: 86400
});
~~~

### 7.1. Comparison Table

| Criterion | Regular collection with TTL index | Time series with retention |
|---|---|---|
| Common setup | `createIndex` on a Date field | `expireAfterSeconds` via `createCollection`/`collMod` |
| Expiration unit | Document whose Date field passes threshold | Measurement via `timeField`; whole bucket deleted once eligible |
| Per-record custom expiration | Possible via explicit Date field + `expireAfterSeconds: 0` | Collection-level TTL applied to `timeField` |
| Deletion lag | Background TTL monitor; non-instant | Background TTL monitor **plus** waiting for bucket expiration |
| Optimization target | General document workloads | Timestamped measurement streams |
| Per-subset TTL | Partial TTL index on supported predicates | Partial TTL on `metaField` in supported versions |
| Bulk deletion | Scales with documents and indexes | Drops buckets, still requires backlog/resource planning |

### 7.2. Do Not Create Arbitrary Compound TTL Indexes

Standard TTL indexes impose **type and field constraints**. Do not write:

~~~javascript
// Not a valid way to define TTL across two fields:
db.normalEvents.createIndex(
  { sensorId: 1, createdAt: 1 },
  { expireAfterSeconds: 86400 }
);
~~~

In MongoDB's TTL index engine, **TTL requires a single-field index**, not an arbitrary compound TTL index. Keep **query indexes** separate from **TTL policies/indexes**, or use a valid partial TTL index in supported versions.

### 7.3. TTL Indexes Do Not Replace Schema Validation

If a regular collection's Date field is mistakenly stored as a String, the TTL index cannot expire it as a BSON Date. Time series collections likewise require **`timeField` to be a valid Date**.

Enforce types at write time, standardize on UTC, and validate/migrate schemas. TTL will not fix corrupted timestamps or convert Strings to Dates.

## 8. Enabling TTL on an Existing Time Series Collection

A time series collection may initially be created **without an expiration policy**:

~~~javascript
use timeseries_ttl_lab

db.createCollection("sensorReadingsNoTTL", {
  timeseries: {
    timeField: "timestamp",
    metaField: "sensor",
    granularity: "seconds"
  }
});
~~~

If the business later decides to keep raw measurements for 30 days, run **`collMod`**:

~~~javascript
db.runCommand({
  collMod: "sensorReadingsNoTTL",
  expireAfterSeconds: 2592000
});
~~~

In this command:

- **`collMod`** names the target collection in the current database.
- **`expireAfterSeconds`** specifies retention in seconds.
- The policy applies to the time series collection's **`timeField`**.

### 8.1. Collection-Level `collMod` vs. Index `collMod`

For time series **collection-level TTL**, run:

~~~javascript
db.runCommand({
  collMod: "sensorReadingsNoTTL",
  expireAfterSeconds: 2592000
});
~~~

For a TTL index on a regular collection, modifying the **index's** `expireAfterSeconds` uses the **`index`** subdocument in `collMod`:

~~~javascript
db.runCommand({
  collMod: "normalEvents",
  index: {
    keyPattern: { createdAt: 1 },
    expireAfterSeconds: 7200
  }
});
~~~

These two syntaxes target **different configuration layers**. Never apply the index-modification syntax expecting it to update collection-wide time series retention.

### 8.2. Enabling TTL Does Not Synchronously Purge History

If a collection already holds two years of data and you enable 30-day retention:

~~~text
Data older than 30 days: begins qualifying for deletion
Buckets also holding newer data: not yet eligible
TTL monitor: gradually purges eligible buckets
~~~

A successful `collMod` response **does not mean all expired data was deleted before the command returned**.

On large datasets, abruptly enabling a short retention creates a **TTL backlog**, spiking I/O and hurting query latency. Plan rollouts carefully, monitor cleanup progress, and validate in staging first.

### 8.3. Age Is Still Evaluated Against Original `timeField`

Suppose a record is inserted today carrying a timestamp from three months ago:

~~~javascript
db.sensorReadingsNoTTL.insertOne({
  timestamp: new Date(Date.now() - 90 * 24 * 3600 * 1000),
  sensor: {
    sensorId: "S-OLD",
    retentionClass: "STANDARD"
  },
  temperatureC: 25.0
});
~~~

With a 30-day retention, this measurement is already expired by **event timestamp**. There is no automatic "30 extra days" counted from import time.

When backfilling historical data for reporting, use an appropriate staging/archiving strategy rather than expecting TTL to pause just because records were recently inserted.

## 9. Changing Retention Duration via `collMod`

Data policies evolve as storage grows, analytics needs shift, or regulations update.

### 9.1. Increasing TTL from 7 Days to 30 Days

~~~javascript
db.runCommand({
  collMod: "sensorReadings7d",
  expireAfterSeconds: 2592000
});
~~~

**Increasing TTL affects only data that still exists.** It **never restores** buckets already purged under the previous 7-day policy. Recovering purged history requires valid backups or archives.

### 9.2. Decreasing TTL from 30 Days to 7 Days

~~~javascript
db.runCommand({
  collMod: "sensorReadingsNoTTL",
  expireAfterSeconds: 604800
});
~~~

This carries far greater operational impact:

~~~text
Before change:
  30 days of data retained

After change:
  only 7 days within desired retention

Consequence:
  buckets spanning days 8 through 30
  can become eligible for expiration simultaneously
~~~

Before executing in production:

1. Confirm older data is no longer required.
2. Complete required archiving or downsampling.
3. Estimate the volume becoming eligible for deletion.
4. Schedule the change during low-traffic windows.
5. Monitor the TTL monitor, I/O, disk usage, replication lag, and query latency.
6. Ensure backup recovery covers policy requirements.

Never treat changing `expireAfterSeconds` as casually as tweaking an API timeout.

### 9.3. Disabling Automatic Expiration

In supported MongoDB versions, disable collection-level time series TTL with:

~~~javascript
db.runCommand({
  collMod: "sensorReadings7d",
  expireAfterSeconds: "off"
});
~~~

This uses the **special string `"off"`**, distinct from the number `0`.

**`expireAfterSeconds: 0`** means data becomes eligible for expiration as soon as `timeField` is reached or passed—it **does not disable TTL**.

After disabling, remaining data is no longer purged by collection-level TTL, yet **previously deleted buckets do not return**. If the collection also holds **partial TTL indexes**, inspect them separately: disabling collection-level TTL does not automatically disable partial TTL indexes.

### 9.4. Re-Enabling After Disabling

~~~javascript
db.runCommand({
  collMod: "sensorReadings7d",
  expireAfterSeconds: 604800
});
~~~

If TTL was off for a long time, re-enabling it can trigger a massive deletion wave. Plan the rollout just as carefully as shortening retention.

### 9.5. Inspecting the Active Policy

Read collection metadata via:

~~~javascript
db.runCommand({
  listCollections: 1,
  filter: {
    name: "sensorReadings7d"
  }
});
~~~

Look for:

~~~javascript
{
  name: "sensorReadings7d",
  type: "timeseries",
  options: {
    timeseries: {
      timeField: "timestamp",
      metaField: "sensor",
      granularity: "seconds"
    },
    expireAfterSeconds: 604800
  }
}
~~~

This is an **abbreviated excerpt**, not an exhaustive list of every field `listCollections` returns across versions. When TTL is disabled, options may display `"off"` or omit/represent it per your server version's metadata format.

### 9.6. Querying `getCollectionInfos()`

In `mongosh`, you can also run:

~~~javascript
db.getCollectionInfos({
  name: "sensorReadings7d"
});
~~~

This returns matching collection metadata documents. Inspect **`options.expireAfterSeconds`** and **`options.timeseries`** rather than guessing TTL from sample documents.

### 9.7. Never Modify `system.buckets` to Alter TTL

Time series collections use internal storage exposed under namespaces like **`system.buckets.<collection>`**. Never run:

~~~javascript
// DO NOT run on real data:
db.getCollection("system.buckets.sensorReadings7d")
  .deleteMany({});
~~~

Manually manipulating bucket internals violates time series engine invariants. Manage retention strictly through **supported APIs** on the **logical collection**—never delete internal buckets directly to "speed up TTL".

## 10. Partial TTL Indexes: Different Retention by Metadata

A common requirement:

~~~text
All sensors:
  retain raw readings 7 days

TEST sensor group:
  retain raw readings only 1 day
~~~

In MongoDB **7.0+** and versions supporting the feature, you can create a **partial TTL index** on a time series collection to enforce a shorter TTL for **measurements matching a `metaField` predicate**.

### 10.1. Why Use Partial TTL?

Suppose you create:

~~~javascript
db.createCollection("readingsByClass", {
  timeseries: {
    timeField: "timestamp",
    metaField: "sensor",
    granularity: "seconds"
  },
  expireAfterSeconds: 604800
});
~~~

Collection-level TTL: **all measurements** get a baseline **7-day** retention.

To expire sensors with `retentionClass: "SHORT"` sooner, add a partial TTL index:

~~~javascript
db.readingsByClass.createIndex(
  { timestamp: 1 },
  {
    name: "ttl_short_class_1d",
    expireAfterSeconds: 86400,
    partialFilterExpression: {
      "sensor.retentionClass": "SHORT"
    }
  }
);
~~~

Key details:

- The index key is **`timeField: timestamp`**.
- **`expireAfterSeconds: 86400`** sets a 1-day TTL for the matching subset.
- **`partialFilterExpression`** references only **`metaField` or its valid subfields**.
- The 7-day collection-level TTL still governs all other measurements.

### 10.2. Illustrative Data

~~~javascript
db.readingsByClass.insertMany([
  {
    timestamp: new Date(),
    sensor: {
      sensorId: "S-TEST",
      site: "LAB",
      retentionClass: "SHORT"
    },
    temperatureC: 22.5
  },
  {
    timestamp: new Date(),
    sensor: {
      sensorId: "S-PROD",
      site: "HCM",
      retentionClass: "STANDARD"
    },
    temperatureC: 28.5
  }
]);
~~~

By policy:

| Measurement | Metadata value | Effective configured TTL |
|---|---|---|
| `S-TEST` | `retentionClass = SHORT` | 1 day |
| `S-PROD` | `retentionClass = STANDARD` | 7 days |

Note that this sets the **eligibility threshold**, not a guarantee `S-TEST` vanishes on the exact second after 1 day if its bucket still contains unexpired readings under matching rules.

### 10.3. Partial TTL Cannot Extend Retention Beyond Collection-Level TTL

Suppose collection-level TTL is 7 days, while a partial TTL index for **`PREMIUM`** specifies 30 days:

~~~javascript
// This configuration does not yield 30-day retention if
// the collection-level TTL still deletes after 7 days.
db.readingsByClass.createIndex(
  { timestamp: 1 },
  {
    name: "ttl_premium_30d",
    expireAfterSeconds: 2592000,
    partialFilterExpression: {
      "sensor.retentionClass": "PREMIUM"
    }
  }
);
~~~

**You cannot use a longer TTL in a partial index to override a shorter collection-level TTL.** The 7-day collection-level policy still qualifies buckets for deletion well before 30 days.

To implement:

~~~text
SHORT    -> 1 day
STANDARD -> 7 days
PREMIUM  -> 30 days
~~~

either:

- Set collection-level TTL = **30 days**, with shorter partial TTLs for `SHORT` and `STANDARD` where supported, or
- Split into separate collections with distinct TTLs.

Never pick the shortest collection-level TTL expecting partial indexes to keep a subset alive longer.

### 10.4. Partial TTL When the Collection Has No Global TTL

A time series collection without `expireAfterSeconds` can still use a metadata-scoped partial TTL index on supported versions:

~~~javascript
db.createCollection("mixedRetention", {
  timeseries: {
    timeField: "timestamp",
    metaField: "sensor",
    granularity: "seconds"
  }
});

db.mixedRetention.createIndex(
  { timestamp: 1 },
  {
    name: "ttl_test_sensors_1d",
    expireAfterSeconds: 86400,
    partialFilterExpression: {
      "sensor.retentionClass": "SHORT"
    }
  }
);
~~~

Here, only measurements matching `SHORT` are governed by the partial TTL policy; other measurements **have no collection-level expiration**.

This works well when only test/debug subsets need automatic expiration while production tiers follow separate lifecycle policies.

### 10.5. Why Must the Filter Reference Only `metaField`?

Partial TTL on time series collections enforces a constraint: `partialFilterExpression` must filter on **`metaField`**. You cannot arbitrarily expire by measurement fields:

~~~javascript
// NOT a valid partial TTL to express
// a measurement-value-based policy:
partialFilterExpression: {
  temperatureC: { $gt: 40 }
}
~~~

Temperature is a **measurement field**, not series metadata. If retention depends on data tier, encode a **stable classification inside `metaField`** at write time or separate collections.

Do not distort `metaField` solely to work around this rule if doing so changes series semantics or inflates cardinality and bucket counts.

### 10.6. Be Careful with Multiple Partial TTL Indexes

If one measurement matches multiple TTL policies, the shorter expiration removes data before the longer policy takes effect. Avoid unintentional overlapping filters:

~~~text
Policy A: sensor.site = LAB -> 1 day
Policy B: sensor.retentionClass = STANDARD -> 7 days

A sensor in LAB with retentionClass STANDARD
matches both policies.
~~~

Define explicit **precedence** and valid metadata combinations, or split collections to eliminate ambiguity. Before altering partial TTLs, audit existing indexes sharing the key pattern and verify version rules.

## 11. When to Split into Multiple Time Series Collections

Not every system should manage multi-tier retention inside one collection with multiple partial TTL indexes.

Suppose three sensor classes exist:

| Tier | Retention | Cadence | Purpose |
|---|---:|---|---|
| `TEST` | 1 day | 1/sec | Short-term debugging |
| `PRODUCTION` | 30 days | 1/10 sec | Live operations |
| `REGULATED` | 365 days | 1/min | Compliance retention |

Two deployment models:

### 11.1. Single Collection, Multiple Policies

~~~text
sensorReadings
  collection TTL: 365 days
  partial TTL TEST: 1 day
  partial TTL PRODUCTION: 30 days
  REGULATED: inherits 365 days
~~~

Pros:

- Centralized queries and data model.
- Single namespace for reads.
- Easy cross-tier aggregations when metadata suffices.

Cons:

- Partial TTL requires server-version support.
- Policies limited to allowed `metaField` predicates.
- Index and bucket management become more complex.
- Risk of overlapping filters or metadata drift.

### 11.2. Separate Collections per Retention Class

~~~text
testReadings1d          -> TTL 1 day
productionReadings30d   -> TTL 30 days
regulatedReadings365d   -> TTL 365 days
~~~

Pros:

- Each collection's retention policy is explicit in its metadata.
- Eliminates complex partial TTL filters.
- Simple to isolate resources, granularity, and operational procedures per tier.

Cons:

- Writers must route to the right namespace.
- Cross-tier analytical queries must combine multiple collections.
- Requires keeping schemas, indexes, and migrations synchronized.

Choose based on **query patterns**, number of retention classes, MongoDB version, storage scale, and isolation requirements. Neither blindly split everything nor cram complex policies into fragile partial indexes.

### 11.3. Does Arbitrary Per-Measurement Expiration Fit Time Series TTL?

If every individual measurement carries a custom **`expireAt`**:

~~~javascript
{
  timestamp: ISODate("2026-11-14T10:00:00Z"),
  expireAt: ISODate("2026-11-17T12:34:56Z")
}
~~~

collection-level TTL on `timestamp` **does not read `expireAt`** to expire individual measurements on custom dates.

When per-record arbitrary expiration is required, consider:

- A **regular collection with a TTL index on `expireAt`**, if volume and queries fit.
- Separate time series collections per retention tier.
- A **custom scheduled purge workflow** with authorization and controls.
- Encoding a finite, stable `retentionClass` inside `metaField`.

Never stamp an `expireAt` Date onto measurements assuming time series TTL honors it automatically unless an explicitly supported configuration targets that field.

## 12. Late Arrivals and Backfills

Telemetry systems do not always deliver readings on schedule:

~~~text
10:00 Sensor records measurement
10:01 Sensor loses connectivity
16:00 Sensor reconnects and sends batch with timestamp 10:00
~~~

If the collection has a 4-hour TTL on **event timestamp**, the 10:00 measurement is already expired when inserted at 16:00.

### 12.1. Example: Backfilling Older Data

~~~javascript
const now = new Date();
const eventTime = new Date(now.getTime() - 10 * 24 * 3600 * 1000);

db.sensorReadings7d.insertOne({
  timestamp: eventTime,
  sensor: {
    sensorId: "S-OFFLINE",
    site: "HCM-03",
    retentionClass: "STANDARD"
  },
  temperatureC: 31.5,
  receivedAt: now
});
~~~

At insertion time, `eventTime` is already older than the 7-day retention. It quickly becomes eligible for removal once its bucket qualifies and the TTL monitor runs.

**A fresh `receivedAt` does not extend TTL**, because `timeField` is declared as `timestamp`. `receivedAt` is merely an auxiliary measurement field unless the collection is designed differently.

### 12.2. Two Different Interpretations of Retention

| Policy | Anchor time | Meaning |
|---|---|---|
| Event-time retention | Measurement `timestamp` | Keep data from the last 7 event days |
| Ingest-time retention | Server receipt time | Keep data at least 7 days after ingestion |

These behave differently when late data arrives.

**Event-time retention** aligns naturally with event-time analytics, yet can expire old backfills immediately. **Ingest-time retention** keeps newly imported records longer, though the collection's time axis reflects receipt time rather than sensor measurement time.

Never redefine `timeField` mid-project without auditing every query and time calculation.

### 12.3. Designing Historical Batch Imports

If you must import six months of raw history to build a report while the live raw collection keeps 7 days:

1. Import into a **separate staging collection without a short TTL**.
2. Run aggregations/downsampling from staging.
3. Write outputs to a summary collection with its own retention.
4. Reconcile counts and coverage.
5. Drop staging on an approved schedule.

This prevents a race condition between **backfill ingestion** and the **TTL monitor** on the live raw collection.

### 12.4. Early Arrivals and Future Timestamps

A device with clock skew might send:

~~~javascript
{
  timestamp: ISODate("2035-01-01T00:00:00Z"),
  sensor: { sensorId: "S-BADCLOCK" },
  temperatureC: 28.0
}
~~~

If `timestamp` sits years in the future, the measurement will not qualify for TTL deletion for a very long time; it also distorts bucket organization and time-range queries.

**Never trust device clocks blindly** under strict retention requirements. You should:

- Validate timestamps against reasonable bounds relative to server time.
- Define maximum tolerated clock skew.
- Store `receivedAt` for diagnostics.
- Maintain remediation workflows for misconfigured device clocks.
- Explicitly define whether future-dated readings are rejected or quarantined.

### 12.5. Extremely Old or Out-of-Range Timestamps

Some MongoDB versions have specific TTL/bucketing constraints for time series timestamps falling outside supported historical or future ranges. Never assume arbitrary Dates from centuries past or future are processed by TTL identically to current timestamps.

Enforce **realistic timestamp bounds** at ingestion and verify version compatibility before importing historical archives.

### 12.6. Server Clock Skew

The TTL monitor evaluates expiration against server clock time, while sensors supply event time. Large clock drift across nodes, backends, or devices causes premature deletions or extended retention.

Synchronize infrastructure clocks (NTP) and monitor clock skew—never blindly add arbitrary offsets to timestamps without an explicit policy.

## 13. Confusing "24 Hours" with "Calendar Days"

TTL in seconds measures elapsed duration. Many reporting rules, however, speak in **local calendar days**.

### 13.1. A 86,400-Second TTL Is Not "End of Tomorrow"

Example measurement at:

~~~text
2026-11-14T10:15:00Z
~~~

With `expireAfterSeconds: 86400`, it becomes eligible after exactly **24 hours**:

~~~text
2026-11-15T10:15:00Z
~~~

It does not wait until **23:59:59 on Nov 15 in `Asia/Ho_Chi_Minh`**, nor align with a site's reporting cutoff.

### 13.2. A Local Day Can Be 23 or 25 Hours Long

Regions observing DST—such as `America/New_York`—have **23-hour** and **25-hour** calendar days across clock transitions. "Keep exactly 48 hours" differs from "keep until the same local wall-clock hour two calendar days later".

If retention must align with **business calendar days**, simple `expireAfterSeconds` may be insufficient; calculate date ranges and manage lifecycle per design.

### 13.3. Daily Reporting and Hourly/Second TTL Coexist Cleanly

You can:

- Query raw readings over `[startOfLocalDay, nextLocalDay)` converted to UTC.
- Aggregate local days into hourly/daily summary collections.
- Set raw TTL in seconds to bound storage.

These responsibilities complement each other as long as **raw retention is long enough** for daily jobs and retries to finish.

### 13.4. Never Replace Sensor Time with Local Time Strings

Instead of:

~~~javascript
{ timestamp: "14/11/2026 17:00" }
~~~

store a UTC BSON Date and keep the sensor/site timezone in metadata when needed for display or local-day aggregation:

~~~javascript
{
  timestamp: ISODate("2026-11-14T10:00:00Z"),
  sensor: {
    sensorId: "S-101",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

This gives TTL an unambiguous reference instant while giving reports everything required for local calendar boundaries.

## 14. TTL Is Not an Archiving or Downsampling Engine

A common misconception:

> Enabling a 7-day TTL tells MongoDB to convert raw data into 7-day summaries and then purge the raw points.

MongoDB TTL **handles expiration and deletion only**—it never computes min/max/avg rollups or exports data to archive storage.

### 14.1. Multi-Tier Data Architecture

~~~text
Sensor / Metrics SDK
         |
         v
Raw time series collection
  7-day TTL
         |
         +----------> Real-time dashboard (last 7 days)
         |
         v
Scheduled aggregation pipeline / job
         |
         v
Hourly aggregates collection
  90-day TTL
         |
         v
Daily aggregates / object storage
  Long-term policy retention
~~~

This is a reference architecture. Not every workload needs three tiers, yet separating tiers balances storage cost and query latency across short-, medium-, and long-term horizons.

### 14.2. Hourly Aggregation Pipeline

Suppose the raw collection stores:

~~~javascript
{
  timestamp: ISODate("2026-11-14T10:05:00Z"),
  sensor: {
    sensorId: "S-101",
    site: "HCM-01"
  },
  temperatureC: 28.4
}
~~~

An aggregation computing avg/min/max/count per sensor and UTC hour:

~~~javascript
db.sensorReadings7d.aggregate([
  {
    $match: {
      timestamp: {
        $gte: ISODate("2026-11-14T00:00:00Z"),
        $lt: ISODate("2026-11-15T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        sensorId: "$sensor.sensorId",
        hourStart: {
          $dateTrunc: {
            date: "$timestamp",
            unit: "hour",
            timezone: "UTC"
          }
        }
      },
      count: { $sum: 1 },
      minTemperatureC: { $min: "$temperatureC" },
      maxTemperatureC: { $max: "$temperatureC" },
      avgTemperatureC: { $avg: "$temperatureC" }
    }
  },
  {
    $sort: {
      "_id.sensorId": 1,
      "_id.hourStart": 1
    }
  }
]);
~~~

This pipeline only **returns aggregated results**; it does not persist hourly summaries. To persist them durably, use **`$merge`**, application writes to a target collection, or a dedicated workflow with proper operational controls and unique business keys.

### 14.3. Why You Cannot Aggregate After TTL Purges Raw Data

Once TTL deletes raw measurements, you can no longer reconstruct exact min/max/avg from the raw collection.

Therefore:

- Run aggregations **before raw expiration**.
- Include buffer margins for data latency and job retries.
- Track watermarks or completed days/hours.
- Record **successful aggregation checkpoints**.
- Keep a recovery source if recomputation is needed past raw TTL.

### 14.4. Aggregations Must Be Idempotent

If an hourly job retries after a timeout, it must never append duplicate documents for the same hour.

A sound logical key:

~~~text
(sensorId, hourStart)
~~~

Use **keyed upserts/`$merge`** or a unique index in a regular summary collection. If summaries live in a time series collection, account for time series unique-index restrictions rather than assuming any unique index works.

### 14.5. Archiving vs. Backups

**Archives** hold data retained for querying/restoration per retention rules; **backups** enable disaster recovery. TTL purging documents from a live collection **does not erase bytes from existing backups**.

When compliance demands permanent deletion on schedule, manage **backup retention, snapshots, exports, analytical copies, and logs** separately. Never present database TTL as a complete legal-erasure solution.

## 15. Monitoring the TTL Monitor and Expired Data

Because TTL runs asynchronously, never inspect **`expireAfterSeconds`** alone and assume cleanup keeps pace. Monitor **backlogs, aged bucket/measurement counts, disk resources, and node state**.

### 15.1. Viewing MongoDB TTL Metrics

With appropriate privileges in `mongosh`:

~~~javascript
db.serverStatus().metrics.ttl;
~~~

Depending on server version, **`metrics.ttl`** may report:

- **`deletedDocuments`**: server-counted deletions by the TTL mechanism.
- **`passes`**: completed TTL sweep passes.
- **`subPasses`**: TTL sub-passes.
- Additional timing, examined document, or key counters depending on version.

These are **node-level cumulative counters since startup**, not remaining counts in a specific collection. On time series collections, deletions operate on bucket storage—**never treat `deletedDocuments` as the exact number of sensor readings purged in a day** without verifying your version's metric definition.

### 15.2. Rising `passes` Does Not Mean All Old Data Is Gone

Suppose the TTL monitor completed a new pass while a sensor bucket still holds one unexpired reading:

~~~text
TTL monitor active: yes
Bucket has expired + unexpired measurements: yes
Eligible for whole-bucket deletion: no
~~~

Seeing an old measurement **does not automatically mean the TTL monitor failed**. Distinguish **old data held by an ineligible bucket** from **eligible data awaiting monitor processing**.

### 15.3. Estimating Measurements Past Threshold Age

Example checking data older than 7 days:

~~~javascript
const cutoff = new Date(
  Date.now() - 7 * 24 * 3600 * 1000
);

db.sensorReadings7d.countDocuments({
  timestamp: { $lt: cutoff }
});
~~~

If greater than 0, logical measurements exist past their individual age threshold—though this **does not prove their buckets are eligible for deletion** at that moment.

On very large collections, counting all aged documents is expensive. In production, use sampling, scoped queries, or pre-evaluated monitoring checks instead of heavy full scans on a frequent dashboard poll.

### 15.4. Checking the Oldest Remaining Timestamp

~~~javascript
db.sensorReadings7d.find(
  {},
  { _id: 0, timestamp: 1, sensor: 1 }
).sort({ timestamp: 1 }).limit(10);
~~~

Useful when investigating which devices hold very old records, though performance depends on indexes, query plans, shard layout, and collection size.

Never use the collection-wide **oldest timestamp** as your sole TTL backlog indicator: one delayed sensor, skewed clock, or outlier bucket can skew the minimum.

### 15.5. Distinguishing TTL Lag from Replication Lag

These are distinct delays:

| Metric | Describes |
|---|---|
| TTL expiration delay | Time from data/bucket becoming eligible until physical deletion |
| Replication lag | Delay for secondaries to apply operations from primary |
| Ingestion lag | Delay from sensor event generation to MongoDB write |
| Aggregation lag | Delay from raw availability to updated summary/report |

A measurement may already be deleted on the primary while a lagging secondary still serves it; conversely, raw data arriving very late can already be expired upon insertion.

When inspecting metrics, clarify **which delay** is measured rather than blaming one dashboard for every kind of lag.

### 15.6. Auditing Active Retention Settings

An operational runbook should run:

~~~javascript
db.getCollectionInfos({
  name: "sensorReadings7d"
});
~~~

and verify:

- Is the collection type genuinely `timeseries`?
- What is **`timeField`**?
- What is **`metaField`**?
- What are **`granularity`** or custom bucket settings?
- What is **`expireAfterSeconds`**, or is it disabled?
- Do any **partial TTL indexes** exist?

Never rely solely on application source code. Prior migrations or admin commands may have altered TTL on the database.

### 15.7. Listing Indexes

~~~javascript
db.sensorReadings7d.getIndexes();
~~~

On time series collections, displayed index definitions may differ from regular collections depending on version and bucket index mapping. Distinguish:

- Query indexes on `metaField`/`timeField`.
- **Partial TTL indexes** with `expireAfterSeconds` and `partialFilterExpression`.
- Collection-level TTL in **`options.expireAfterSeconds`**.

Never conclude a collection **has no TTL** merely because no index named `"ttl_timestamp"` appears in `getIndexes()`.

## 16. Impact of TTL on Replication, Sharding, and Storage

MongoDB executes time series TTL inside the server. In a replica set, deletions run on the **primary** and replicate to secondaries.

### 16.1. Do Not Expect Independent TTL Sweeps on Secondaries

In a standard replica set, TTL deletions are coordinated by the **primary** per MongoDB rules; secondaries do not run independent business expirations to "catch up" on their own clocks.

Why this matters:

~~~text
Primary:   expired bucket already deleted
Secondary: may not have applied the delete operation yet
~~~

Reading with `secondary` read preference right after deletion can surface records already gone on primary during replication lag. APIs must never rely on TTL as a strict real-time filter.

### 16.2. TTL Generates Write I/O

When TTL deletes data, MongoDB must still:

- Modify storage structures.
- Update affected indexes.
- Record oplog entries and replicate them.
- Manage memory, disk, and background threads.

Shortening TTL from 365 days to 7 days on a huge collection marks vast numbers of buckets for cleanup. Automatic deletion is never "free".

### 16.3. TTL and Sharded Time Series

In sharded deployments supporting time series collections, data distributes across shards by shard key/metadata. Each shard executes TTL cleanup on its own owned data ranges.

Monitor:

- Which shards hold expired data.
- Which shards experience heavy TTL backlogs.
- Whether TTL I/O degrades regional query latency.
- Whether concurrent chunk migrations or rebalancing add pressure.
- Whether read preferences hit lagging secondaries.

Never assume **one TTL metric on a single node** reflects the whole sharded cluster.

### 16.4. Disk Usage Does Not Always Shrink Immediately After Deletion

After TTL removes many buckets, the storage engine gains **internal free space for reuse**, while OS file sizes may stay unchanged.

Thus:

~~~text
Measurement count drops
          |
          v
MongoDB reuses internal free space
          |
          v
Data files on disk do not necessarily shrink immediately
~~~

Never conclude TTL is broken simply because OS "file size" charts do not drop right away. Distinguish **logical data size, storage size, free/reusable space**, and storage-engine file management.

### 16.5. Mass Deletions Can Pressure Backups

Bulk deletions also impact:

- Elevated oplog/replication traffic.
- Change volume tracked by continuous backups.
- Point-in-time restore behavior across deletion windows.
- I/O spikes during maintenance windows.

Major retention changes require DBA and backup-team review—not just backend approval.

### 16.6. TTL Does Not Replace Tiered Partitioning/Archiving

If the business wants:

~~~text
0–7 days hot data on fast storage
7–180 days warm data on cheaper storage
Delete after 180 days
~~~

a 7-day TTL on the raw collection simply **deletes data from that collection**. It never automatically migrates data to a warm tier as a complete archival pipeline.

You still need export pipelines, summary collections, and dedicated SLAs/controls.

## 17. Safely Changing Retention in Production

A TTL change can cause irreversible data loss on an online collection. Change management must document **old retention, new retention, affected data, and deletion sign-off**.

### 17.1. Before Making Changes

Gather:

1. **Namespace** and collection type.
2. Current **`timeField`, `metaField`, `granularity`**.
3. Current retention and any partial TTL indexes.
4. Current data volume and percentage of aged measurements.
5. Queries or reports still requiring older data.
6. Approved backups/archives and restore readiness.
7. Tolerable I/O overhead.
8. Post-change monitoring window.

### 17.2. Classifying Changes

| Change | Primary impact |
|---|---|
| No TTL → 7 days | Many historical buckets may immediately become eligible |
| 30 days → 7 days | Risk of TTL backlog and rapid loss of raw history |
| 7 days → 30 days | Existing data stays longer; already deleted data does not return |
| 7 days → `"off"` | Disables collection-level expiration; storage keeps growing |
| `"off"` → 7 days | Can trigger cleanup of large accumulated history |
| Add 1-day partial TTL | Matching metadata subset expires sooner |
| Change `granularity` | Affects bucketing/TTL lag; constrained by server version |

### 17.3. Beware "Rolling Back" TTL

A sequence:

~~~text
30 days -> 7 days -> 30 days
~~~

is **not a complete data rollback**. While TTL was 7 days, buckets covering days 8–30 may already have been deleted. Setting TTL back to 30 days does not recreate lost buckets.

Metadata rollback is not **data recovery**.

### 17.4. Never Clean Up Internal Buckets Manually

To accelerate mass deletion, never touch **`system.buckets`**. Check valid time series delete commands and field constraints for your version, or consider staging/migration workflows with proper operational support.

Running ad-hoc deletes on raw production collections can be irreversible; never execute a "delete all old timestamps" script without verifying time series rules and following change control.

### 17.5. Post-Deployment Verification

An operational checklist includes:

- Collection options reflect the intended TTL.
- Partial TTL indexes do not conflict with intended policies.
- TTL monitor is active and metrics progress.
- Aged-out measurement counts in queries decline as expected.
- CPU, I/O, and replication lag stay within thresholds.
- Aggregations and downsampling jobs do not lose inputs.
- Backups and restore capabilities remain policy-compliant.

Verification belongs to a **live operational runbook**, not a single `mongosh` command assumed to validate everything.

## 18. Java MongoDB Sync Driver: Creating Time Series Collections with TTL

In Java applications, the **MongoDB Sync Driver** creates time series collections with options matching `mongosh`.

### 18.1. Connecting and Creating the Collection

Assume the project includes a server-compatible **`mongodb-driver-sync`** dependency and **`MONGODB_URI`** points to a test MongoDB instance with collection-creation privileges.

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.CreateCollectionOptions;
import com.mongodb.client.model.TimeSeriesGranularity;
import com.mongodb.client.model.TimeSeriesOptions;

import java.util.concurrent.TimeUnit;

public class CreateSensorTimeSeries {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database =
                    client.getDatabase("timeseries_ttl_lab");

            TimeSeriesOptions timeSeriesOptions =
                    new TimeSeriesOptions("timestamp")
                            .metaField("sensor")
                            .granularity(TimeSeriesGranularity.SECONDS);

            CreateCollectionOptions options =
                    new CreateCollectionOptions()
                            .timeSeriesOptions(timeSeriesOptions)
                            .expireAfter(7, TimeUnit.DAYS);

            database.createCollection(
                    "sensorReadingsFromJava",
                    options
            );

            System.out.println("Created time series with TTL 7 days");
        }
    }
}
~~~

On Java Driver versions supporting those builders, this creates:

~~~javascript
{
  timeseries: {
    timeField: "timestamp",
    metaField: "sensor",
    granularity: "seconds"
  },
  expireAfterSeconds: 604800
}
~~~

Verify enum/method names against your exact **`mongodb-driver-sync`** version. If a collection with the same name already exists, `createCollection` does not alter its TTL; use **`collMod`** or an administrative migration.

### 18.2. Do Not Run `createCollection` on Every Request

In a REST API, collection creation and TTL setup belong to **schema migration/bootstrap**, never to per-reading requests:

~~~text
Deploy / migration
  -> ensure time series collection exists with valid TTL

Runtime ingest service
  -> insert measurements only
~~~

If every API instance attempts to create or modify TTL on startup, instances can contend or inadvertently overwrite active retention policies.

### 18.3. Writing Measurements with BSON Date

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.time.Instant;
import java.util.Date;

public class SensorMeasurementWriter {
    public static void write(
            MongoCollection<Document> collection,
            String sensorId,
            double temperatureC,
            Instant measuredAt) {

        Document sensor = new Document("sensorId", sensorId)
                .append("retentionClass", "STANDARD");

        Document measurement = new Document(
                "timestamp",
                Date.from(measuredAt)
        )
                .append("sensor", sensor)
                .append("temperatureC", temperatureC);

        collection.insertOne(measurement);
    }
}
~~~

**`Date.from(measuredAt)`** ensures the timestamp serializes as a BSON Date via the default codec. Saving `measuredAt.toString()` stores a String, which does not carry BSON Date semantics.

### 18.4. Validating Event Time Origins

When a device supplies `measuredAt`:

~~~java
Instant measuredAt = Instant.parse(
        "2026-11-14T10:15:00Z"
);
~~~

the application should verify `measuredAt` falls within sensible bounds:

~~~java
Instant receivedAt = Instant.now();

boolean tooOld = measuredAt.isBefore(
        receivedAt.minusSeconds(7 * 24 * 3600L)
);

boolean tooFarInFuture = measuredAt.isAfter(
        receivedAt.plusSeconds(5 * 60L)
);

if (tooOld || tooFarInFuture) {
    throw new IllegalArgumentException(
            "Measurement timestamp outside allowed ingestion window");
}
~~~

This is an **illustrative application validation policy**, not a MongoDB rule. Systems needing historical backfills should route older data through a controlled staging/import workflow rather than rejecting valid records.

### 18.5. The Java Driver Does Not Change TTL Asynchrony

Even after a Java insert succeeds, an already-expired measurement can remain visible to `find` briefly. The driver never waits for the TTL monitor to purge a bucket before acknowledging an insert.

If an API must restrict returned readings to 7 days, Java queries must apply their own timestamp filter independently.

### 18.6. Filtering Time Windows in Java

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.time.Instant;
import java.util.Date;

public class SensorWindowReader {
    public static void readLastSevenDays(
            MongoCollection<Document> collection,
            String sensorId) {

        Instant now = Instant.now();
        Date from = Date.from(
                now.minusSeconds(7L * 24 * 3600)
        );
        Date to = Date.from(now);

        Bson filter = Filters.and(
                Filters.eq("sensor.sensorId", sensorId),
                Filters.gte("timestamp", from),
                Filters.lt("timestamp", to)
        );

        try (MongoCursor<Document> cursor = collection
                .find(filter)
                .sort(Sorts.ascending("timestamp"))
                .iterator()) {

            while (cursor.hasNext()) {
                System.out.println(cursor.next().toJson());
            }
        }
    }
}
~~~

The **`[from, to)`** pattern makes query bounds unambiguous. It does not claim every measurement older than seven days has been deleted from storage; it simply instructs MongoDB **not to return them**.

## 19. Java Driver: Updating TTL and Reading Collection Metadata

Beyond `mongosh`, the MongoDB Java Sync Driver can issue **`collMod`** to change time series retention.

### 19.1. Updating Collection-Level TTL

~~~java
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class UpdateTimeSeriesTTL {
    public static Document setRetentionToThirtyDays(
            MongoDatabase database) {

        Document command = new Document(
                "collMod",
                "sensorReadingsFromJava"
        ).append(
                "expireAfterSeconds",
                30 * 24 * 3600
        );

        return database.runCommand(command);
    }
}
~~~

**Note:** this is a **collection administration** operation. Invoke it only via approved migrations, never automatically from an API ingestion endpoint.

### 19.2. Disabling TTL with `"off"`

~~~java
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class DisableTimeSeriesTTL {
    public static void disable(
            MongoDatabase database) {

        database.runCommand(
                new Document(
                        "collMod",
                        "sensorReadingsFromJava"
                ).append(
                        "expireAfterSeconds",
                        "off"
                )
        );
    }
}
~~~

**`"off"` does not equal `0`**. On supported versions, `"off"` disables collection-level expiration; `0` sets a zero-second offset against `timeField`.

### 19.3. Fetching Metadata with `listCollections`

~~~java
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class ShowCollectionRetention {
    public static Document listInfo(
            MongoDatabase database) {

        Document command = new Document(
                "listCollections",
                1
        ).append(
                "filter",
                new Document("name", "sensorReadingsFromJava")
        );

        return database.runCommand(command);
    }
}
~~~

The command returns a response containing a `cursor`/`firstBatch` with collection metadata. Administrative tools should parse it properly and handle missing collections.

### 19.4. Managing Retention Settings as Versioned Migrations

Organizations can track retention versions in source control:

~~~text
Schema migration V001:
  Create sensorReadingsFromJava
  timeField: timestamp
  metaField: sensor
  expireAfterSeconds: 604800

Schema migration V007:
  Change collection TTL to 2592000
  Reason: extend raw window before hourly aggregation
  Approval: data platform
~~~

Manage this **outside MongoDB measurement data**, with changelogs and data-recovery plans. Tracking configuration in code informs operators of approved policies, while live metadata audits detect drift.

## 20. Spring Data MongoDB: Creating and Querying Time Series with Retention

Spring Data MongoDB provides **`MongoTemplate`** and mapping/collection APIs. Because specific fluent builders for time series and TTL vary across Spring Data versions, **`MongoTemplate.executeCommand`** clearly demonstrates executing MongoDB's native BSON commands.

### 20.1. Creating a Time Series Collection via `MongoTemplate`

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;

public class TimeSeriesCollectionSetup {
    private final MongoTemplate mongoTemplate;

    public TimeSeriesCollectionSetup(
            MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public void createRawReadings() {
        Document command = new Document(
                "create",
                "springSensorReadings"
        ).append(
                "timeseries",
                new Document(
                        "timeField",
                        "timestamp"
                )
                        .append("metaField", "sensor")
                        .append("granularity", "seconds")
        ).append(
                "expireAfterSeconds",
                604800
        );

        // Run once during migration/schema bootstrap.
        mongoTemplate.executeCommand(command);
    }
}
~~~

This requires `MongoTemplate` to target **`timeseries_ttl_lab`**. If the collection already exists, `create` throws an error; never swallow all errors silently when schema/TTL might be misconfigured.

### 20.2. Updating TTL from Spring Data

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;

public class TimeSeriesRetentionAdmin {
    private final MongoTemplate mongoTemplate;

    public TimeSeriesRetentionAdmin(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public Document setSevenDayTTL() {
        return mongoTemplate.executeCommand(
                new Document(
                        "collMod",
                        "springSensorReadings"
                ).append("expireAfterSeconds", 604800)
        );
    }
}
~~~

In production, guard such operations with admin authorization and approval workflows—never expose an unauthenticated **`POST /set-ttl?seconds=0`** endpoint.

### 20.3. Querying Time Windows with `Criteria`

~~~java
import java.time.Instant;
import java.util.Date;
import java.util.List;

import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class TimeSeriesQueryService {
    private final MongoTemplate mongoTemplate;

    public TimeSeriesQueryService(
            MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Document> getReadings(
            String sensorId,
            Instant from,
            Instant to) {

        if (!from.isBefore(to)) {
            throw new IllegalArgumentException(
                    "Invalid time range");
        }

        Query query = Query.query(
                Criteria.where("sensor.sensorId").is(sensorId)
                        .and("timestamp")
                        .gte(Date.from(from))
                        .lt(Date.from(to))
        );

        return mongoTemplate.find(
                query,
                Document.class,
                "springSensorReadings"
        );
    }
}
~~~

This filters by **metadata and time range**, allowing MongoDB to prune unrelated buckets when collection/index configuration matches. It never relies on the TTL monitor having finished cleaning up.

### 20.4. Understanding Annotations and Schema Creation

Framework annotations on a class **do not guarantee a retention policy is active in MongoDB** if auto-creation is disabled or the collection already existed with old options.

In production, verify:

- The collection actually has type **`timeseries`**.
- `timeField`/`metaField` match application mappings.
- `expireAfterSeconds` matches the approved policy.
- Expected indexes exist.
- Staging and production have no configuration drift.

### 20.5. Do Not Emulate TTL with `Repository.deleteByTimestamp`

Some developers write scheduled cleanup jobs:

~~~java
// Pseudocode: not a better default choice than TTL
// repository.deleteAllByTimestampBefore(cutoff);
~~~

However, time series collections impose version-specific delete/update restrictions, and custom delete jobs must handle load, retries, concurrency, and cleanup themselves.

Whenever supported TTL expresses the retention requirement cleanly, prefer MongoDB's native mechanism. Write custom delete jobs only when TTL cannot meet a requirement and after verifying operation support on your server version.

## 21. Designing TTL Around Business Requirements

### 21.1. Infrastructure Metrics

Requirements:

~~~text
Raw CPU samples:     3 days
5-minute rollups:   90 days
Daily rollups:     365 days
~~~

Proposal:

- Time series collection **`rawCpu3d`** with `259200`-second TTL.
- **`cpuFiveMinute90d`** holding 90 days of 5-minute rollups.
- **`cpuDaily365d`** or long-term archive.

Rollup jobs require watermarks, retries, and buffer margins before raw expiration.

### 21.2. Industrial Equipment Sensors

Requirements:

~~~text
Production sensors: raw 30 days
Test/lab sensors:   raw 1 day
~~~

If your version supports **partial TTL indexes on `metaField`**, use a 30-day collection-level TTL plus a 1-day partial TTL on **`sensor.retentionClass = "TEST"`**. Otherwise, split collections or apply another version-supported policy.

### 21.3. Compliance Monitoring Data

Requirements:

~~~text
Raw operational metrics: 7 days
Legal-hold subset:       must not be deleted
~~~

Never leave a 7-day collection-level TTL covering data under legal hold, because global TTL will purge it.

Options include:

- Moving records to a dedicated **legal-hold collection** with no automatic TTL.
- Using a collection whose TTL applies only to non-held subsets via partial TTL where supported.
- Writing to an immutable archive/ledger under separate governance.

Never treat a **`legalHold: true`** measurement field as blocking collection-level TTL without an architecture enforcing it.

### 21.4. Events from Offline Devices

Requirements:

~~~text
Sensors may be offline for 14 days
Raw data must stay processable 7 days after receipt
~~~

If `timeField` is measurement time, readings arriving after 14 days are already older than a 7-day TTL. Adjust the policy:

- Extend raw event-time retention beyond maximum offline duration.
- Stage offline uploads before processing.
- Maintain a dedicated ingest-time series for lifecycle management.
- Compute aggregates upon receipt and archive raw per policy.

**Setting retention shorter than valid arrival delay** risks losing data before processing.

### 21.5. End-of-Month Deletion Schedules

"Delete all October readings at 00:00 on January 1 in the business timezone" does not mean "keep 60 × 24 hours from each timestamp".

You may need:

- An approved monthly scheduled purge workflow.
- Per-month collections/partitions in an appropriate model.
- Archiving and dropping monthly collections after period close.

Never assume `expireAfterSeconds` can express arbitrary accounting-calendar rules.

## 22. Common Incidents and Investigation

### 22.1. TTL Set to 1 Hour, Yet Queries Still Return 90-Minute-Old Data

Possible causes:

1. The older measurement shares a bucket with a newer, unexpired measurement.
2. Bucket time bounds delay eligibility.
3. The TTL monitor has not swept yet or has a backlog.
4. Reads hit a secondary lagging behind the primary's delete.
5. The collection lacks the expected `expireAfterSeconds`.
6. Queries hit a **different collection**, archive, or cache.

Diagnostic commands:

~~~javascript
db.getCollectionInfos({
  name: "sensorReadings7d"
});

db.sensorReadings7d.getIndexes();

db.serverStatus().metrics.ttl;
~~~

Cross-check metadata, bucket behavior, and operational metrics. Never manually delete `system.buckets` as a "quick fix".

### 22.2. TTL Runs, Yet Disk Usage Does Not Shrink

Usually **WiredTiger reuses internal free space inside data files**. Logical data size drops while OS file size stays flat.

Check logical counts/sizes, storage size, and free/reusable space. Never run `compact` or initial sync solely to reclaim disk without a procedure and risk assessment.

### 22.3. CPU and I/O Spike After Shortening Retention

Changing TTL from 365 days to 7 days makes vast numbers of buckets eligible at once. The TTL monitor generates heavy background writes, adding load to replication and backups.

Mitigate with phased rollouts, resource monitoring, backlog tracking, and DBA coordination. **No single TTL command guarantees "purging a year of data with zero production impact".**

### 22.4. Data Still Disappears After Disabling TTL

Check:

- Is a **partial TTL index** still active?
- Is an external manual delete or lifecycle job running?
- Are queries reading a different collection?
- Did a migration, drop, or rebuild occur?
- Was the data purged **before** TTL was disabled?

**Collection-level `"off"`** does not halt every other deletion mechanism.

### 22.5. Partial TTL Index Fails to Expire Target Subset

Verify:

- Does your server version support partial TTL on time series?
- Did index creation succeed?
- Is the index key the collection's **`timeField`**?
- Does the filter reference only valid **`metaField`/subfields**?
- Do actual metadata values match exact type/case (e.g., **`"SHORT"`** vs. **`"short"`**)?
- Does a shorter collection-level TTL supersede the partial index?
- Is the containing bucket fully eligible yet?

Do not declare the index broken merely because `SHORT` readings from the same day still sit inside an unexpired bucket.

### 22.6. Future-Dated Sensor Readings Never Expire

Usually caused by sensor clock skew. Because TTL evaluates `timeField`, future timestamps have not aged out. Validate and quarantine future data, fix device clocks, and decide how to remediate already-stored records.

Never tweak collection-wide TTL to work around a few bad timestamps—that impacts every measurement.

### 22.7. Backfill Data Purged Before Reports Run

If backfilled events already exceed event-time retention, TTL can delete them before pipelines finish. Use:

- Separate staging.
- Long enough TTL for backfill windows.
- Aggregation jobs before cleanup.
- Checkpoints, watermarks, and verification.

A 7-day policy does not know a batch was imported today if its measurement timestamps are 90 days old.

### 22.8. One Group Needs 30-Day Retention While Collection-Level TTL Is 7 Days

A 30-day partial TTL index **cannot extend lifetime beyond** a 7-day collection-level TTL.

Redesign: set collection-level TTL to the longest retention (30 days) with shorter partial TTLs for shorter tiers, or split into separate collections.

### 22.9. Creating a TTL Index Fails

Do not assume any arbitrary index can act as a TTL index. MongoDB enforces:

- Standard TTL requires a **single-field index**.
- Time series partial TTL supports only **`timeField` key + `metaField` filter** on compatible versions.
- `createIndex` cannot convert an existing identical key pattern into a TTL index simply by adding options if disallowed.
- Invalid data types, options, or server/FCV versions cause errors.

Read exact error messages and version docs. Never drop a critical production index just to retry without checking query impact.

### 22.10. Deleted Measurement Counts Do Not Match `metrics.ttl.deletedDocuments`

Time series uses bucket storage; TTL metrics count server-level deletion operations as tracked by MongoDB, not a 1:1 count of logical measurements.

Never use metric deltas as an audit receipt proving "exactly N readings of sensor `S-101` were deleted". Business-level deletion audits require dedicated telemetry/audit logs.

### 22.11. Expired Measurements Still Appear in Read Models

Copies exported to Elasticsearch, data warehouses, Redis, or API caches **do not expire automatically** with MongoDB's raw TTL. Configure lifecycle/retention in each downstream system.

If the application must never serve aged records, enforce time filters on the read path and govern downstream caches/indexes.

### 22.12. Raw Data Expires While an Aggregation Job Is Running

With long-running jobs or repeated retries, an overly tight TTL can delete inputs mid-pipeline. Add safety margins, pin event-time windows, aggregate early, and alert on job delays.

### 22.13. Duplicate Measurements from Sensor Retries

TTL **is not a deduplication mechanism**. If a sensor retries and writes two records with identical `sensorId`/`timestamp`, TTL keeps both until expiration.

Eliminate duplicates using stable `eventId`s, ingestion idempotency, or deduplication jobs while respecting time series unique-index constraints. Never treat TTL as duplicate prevention.

### 22.14. Collection Remains Huge Despite Active TTL

Often driven by sheer ingestion volume:

~~~text
Ingest 86 million measurements/day
7-day TTL

Estimated active logical volume:
  ~ 7 × 86 million = 602 million measurements
~~~

You still need storage for the full retention window, metadata/indexes/overhead, and operational headroom. TTL bounds lifecycle—**it does not shrink storage requirements to zero**.

## 23. Diagnostic Runbook for Unexpected TTL Behavior

### Step 1 — Verify Collection Type

~~~javascript
db.getCollectionInfos({
  name: "sensorReadings7d"
});
~~~

Check `type` and `options.timeseries`.

### Step 2 — Verify Expiration Policy

Inspect **`options.expireAfterSeconds`** and indexes:

~~~javascript
db.sensorReadings7d.getIndexes();
~~~

Check whether partial TTL indexes exist on `retentionClass`.

### Step 3 — Verify Timestamps

Confirm sample records hold valid BSON Dates within expected bounds:

~~~javascript
db.sensorReadings7d.find(
  {},
  {
    _id: 0,
    timestamp: 1,
    sensor: 1
  }
).sort({
  timestamp: 1
}).limit(5);
~~~

If extreme future or ancient timestamps appear, audit ingestion validation.

### Step 4 — Compute Individual Age Threshold

~~~javascript
const ttlSeconds = 604800;
const cutoff = new Date(
  Date.now() - ttlSeconds * 1000
);

print("Cutoff UTC:", cutoff.toISOString());
~~~

Timestamps older than `cutoff` are past **individual threshold age**, though their buckets may still await eligibility.

### Step 5 — Evaluate Buckets and Granularity

Check `granularity` or custom bucket spans, data distribution sharing `metaField`, and whether newer readings keep buckets alive. Avoid guessing exact physical bucket assignments from a handful of timestamps alone.

### Step 6 — Inspect TTL Monitor Metrics

~~~javascript
db.serverStatus().metrics.ttl;
~~~

Track counters over time to verify monitor progress without treating counters as exact purged measurement counts.

### Step 7 — Check Topology

Across replica sets and sharded clusters, inspect primary vs. secondaries, replication lag, and per-shard backlogs. Never conclude primary deletion succeeded or failed from a single secondary read.

### Step 8 — Identify Which Data Source the Application Reads

Check caches, archives, analytics read models, and API fallbacks, verifying retention and filters across each layer.

### Step 9 — Assess Impact Before Modifying TTL

Avoid toggling `expireAfterSeconds` repeatedly "just to see if it deletes". Diagnose root cause first, then schedule controlled changes.

### Step 10 — Document Findings and Evidence

Record:

- Collection name and observation time.
- Active TTL, `granularity`, and indexes.
- Sample counts and ages beyond threshold.
- TTL monitor and topology status.
- Confirmed or suspected root cause.
- Remediation steps and acceptance criteria.

A clear runbook prevents knee-jerk reactions like "saw old data → dropped the collection".

## 24. Quick Decision Matrix

| Business need | Recommended approach |
|---|---|
| Retain raw time series for fixed N seconds/days | Collection-level `expireAfterSeconds` |
| Shorter TTL for one sensor tier | Partial TTL index on `metaField` in supported versions |
| Keep one tier longer than collection TTL | Raise collection TTL or separate collections; longer partial TTL will not save it |
| Stop automatic expiration | `collMod` with `expireAfterSeconds: "off"` where supported |
| Shorten TTL on collection with existing history | Approved migration, assess TTL backlog and backups |
| Read exactly the last N hours | Filter timestamp `[from, to)` in queries; do not rely on cleanup |
| Delete at the exact second of expiration | Bucket-based background TTL does not meet this SLA |
| Delete at local month-end | Calendar-driven lifecycle or monthly collections |
| Devices may arrive later than retention | Staging or extend retention/adjust policy |
| Retain data for long-term reporting | Downsample/aggregate before raw TTL expires |
| Keep raw years while querying recent data | Archive or tiered storage architecture |
| Erase from backups and external systems | Manage retention per system; MongoDB TTL alone is insufficient |
| Future-dated skewed timestamps | Validate/quarantine/fix clocks; never raise TTL blindly |
| Measure aged measurement backlog | Dedicated query/metric accounting for bucket lag |
| Disk files do not shrink after TTL | Separate logical data size from reusable free space |

## 25. Practice Exercises on Time Series TTL

Exercises use **`timeseries_ttl_lab`** and the lab collections introduced above. Do not re-run `createCollection` with duplicate names without checking first. Only test TTL changes on sample datasets—never in production.

### Exercise 1. Convert Retention to Seconds

A raw collection retains **14 days**, and an hourly summary collection retains **180 days**.

**Task:** Compute `expireAfterSeconds` for each collection.

**Answer:**

~~~text
Raw 14 days:
14 × 24 × 60 × 60 = 1,209,600 seconds

Hourly 180 days:
180 × 24 × 60 × 60 = 15,552,000 seconds
~~~

Note these are **fixed 14- and 180-day spans**, not calendar months.

### Exercise 2. Create a Time Series Collection with 48-Hour TTL

Design:

- Collection: **`labMetrics48h`**
- `timeField`: **`measuredAt`**
- `metaField`: **`source`**
- `granularity`: **`seconds`**
- TTL: **48 hours**

~~~javascript
db.createCollection("labMetrics48h", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "source",
    granularity: "seconds"
  },
  expireAfterSeconds: 172800
});
~~~

**Question:** If a document also has **`createdAt`** set to today while `measuredAt` is three days ago, which field drives TTL?

**Answer:** **`measuredAt`**, because it is the declared `timeField`—MongoDB does not switch to `createdAt`.

### Exercise 3. Determine Expiration Eligibility Time

A measurement:

~~~text
measuredAt = 2026-11-14T08:30:00Z
TTL        = 3,600 seconds
~~~

**Question:** When does the measurement become aged out under TTL?

**Answer:** **`2026-11-14T09:30:00Z`**. However, it may remain visible afterward until its bucket and the TTL monitor sweep it.

### Exercise 4. Bucket Containing Newer Readings

Suppose a logical bucket contains:

~~~text
10:00
10:15
10:50
~~~

TTL = 1 hour. At `11:30`, which measurements are individually past age? Can the entire bucket be deleted yet?

**Guided Answer:** `10:00` and `10:15` are past one hour; `10:50` is not. Because the bucket still holds an unexpired reading, it is **not yet eligible for whole-bucket deletion** under time series TTL.

### Exercise 5. Choosing `granularity`

One sensor logs every 10 seconds; another logs every 2 hours. Choose appropriate `granularity` values and explain their impact on bucketing and TTL lag.

**Guidance:** Base the choice on timestamp spacing, query patterns, and storage limits. `seconds` and `hours` differ in maximum bucket spans; never pick `hours` for high-frequency data thinking it "deletes after one hour". **`granularity` is not a TTL setting**.

### Exercise 6. Enabling TTL on an Existing Collection

An existing time series collection **`oldReadings`** has no automatic expiration. Enable a 30-day TTL.

~~~javascript
db.runCommand({
  collMod: "oldReadings",
  expireAfterSeconds: 2592000
});
~~~

**Question:** If the collection holds one year of data, does a successful command response mean everything older than 30 days is immediately gone?

**Answer:** No. Eligible buckets are purged asynchronously by the background TTL monitor, which may incur backlog and delay.

### Exercise 7. Disabling TTL

Write the command to disable collection-level expiration:

~~~javascript
db.runCommand({
  collMod: "oldReadings",
  expireAfterSeconds: "off"
});
~~~

**Question:** Why not use `expireAfterSeconds: 0`?

**Answer:** `0` does not mean "off"; it sets zero-second offset past `timeField`, making buckets eligible immediately.

### Exercise 8. Raising TTL Does Not Restore Purged Data

On day 1, a 7-day TTL purged older data. On day 2, the DBA raises retention to 30 days.

**Question:** Does MongoDB restore data already deleted by TTL?

**Answer:** No. Increasing TTL only keeps surviving buckets longer; recovering purged data requires valid backups or archives.

### Exercise 9. Partial TTL on `metaField`

Collection **`classMetrics`** has:

~~~javascript
{
  timeseries: {
    timeField: "measuredAt",
    metaField: "source"
  },
  expireAfterSeconds: 2592000
}
~~~

Requirement: `source.retentionClass = TEST` must be retained for only 1 day. Write the partial TTL index on a supporting version:

~~~javascript
db.classMetrics.createIndex(
  { measuredAt: 1 },
  {
    name: "ttl_test_1d",
    expireAfterSeconds: 86400,
    partialFilterExpression: {
      "source.retentionClass": "TEST"
    }
  }
);
~~~

**Question:** Is `source.retentionClass` inside `metaField` or a measurement field? Why does this matter?

**Answer:** It is a subfield of `metaField` **`source`**, satisfying time series partial TTL constraints. An arbitrary filter on measurement values cannot replace this rule.

### Exercise 10. Partial TTL Longer Than Collection-Level TTL

Collection-level TTL is 7 days; partial TTL for `VIP` is 30 days.

**Question:** Is `VIP` guaranteed 30-day retention?

**Answer:** No. The 7-day collection-level TTL still applies and can purge `VIP` before 30 days. To give `VIP` 30 days, adjust the collection-level policy or split collections.

### Exercise 11. Offline Data

Sensor `S-101` goes offline for 12 days, then uploads a reading timestamped 12 days ago into a raw collection with a 7-day TTL.

**Question:** Is the reading kept for 7 days from upload time?

**Answer:** Not under an event-time `timeField`. The measurement is already expired at import time. Use staging or align retention with ingestion lag.

### Exercise 12. Future Timestamps

A device sends a 2035 timestamp while the system runs in 2026.

**Question:** Will a 7-day TTL purge this record soon?

**Guidance:** Do not expect it to. Future timestamps prevent aging out. Audit clock skew, fix the device, and enforce reject/quarantine policies.

### Exercise 13. Distinguishing Query Filters from TTL

A collection has a 30-day TTL, while an API returns only the **last 24 hours**. Write the query filter.

~~~javascript
const now = new Date();
const from = new Date(now.getTime() - 24 * 3600 * 1000);

db.sensorReadings7d.find({
  timestamp: {
    $gte: from,
    $lt: now
  }
});
~~~

**Guided Answer:** Filtering `[from, now)` is the query's responsibility; do not shorten collection-wide TTL to 24 hours just to serve one endpoint.

### Exercise 14. Downsampling Before TTL

Raw data is kept 7 days; hourly aggregation runs once daily. The job fails for three consecutive days.

**Question:** What is the risk and how should the design be hardened?

**Guidance:** Once raw data expires, the job loses source inputs needed to aggregate. Build enough buffer for outages/retries, track watermarks, alert on failures, checkpoint progress, and keep a recovery source.

### Exercise 15. TTL Monitor Lag

An expired measurement remains in the collection while TTL `passes` increases.

**Question:** Can you conclude the TTL monitor is broken?

**Answer:** Not yet. Its bucket may contain newer readings, or background cleanup/backlog/replication may add lag. Inspect policy, `timeField`, `granularity`, and topology.

### Exercise 16. Disk Space After Deletion

After TTL deletes most history, logical measurement counts drop while disk file sizes stay nearly flat.

**Question:** Did TTL definitely fail?

**Answer:** No. The storage engine retains internal space inside files for reuse. Distinguish logical data size from physical file allocation.

### Exercise 17. Mismatched Metadata Filter

Partial TTL filter:

~~~javascript
{
  "sensor.retentionClass": "SHORT"
}
~~~

Document contains:

~~~javascript
{
  sensor: {
    retentionClass: "short"
  }
}
~~~

**Question:** Does the document match under standard string equality?

**Answer:** No, default string comparison is case-sensitive. Normalize metadata at write time—never assume `"SHORT"` matches `"short"`.

### Exercise 18. Legal Hold

A subset of readings requires 3-year retention while collection-level TTL is 7 days.

**Question:** Is adding `legalHold = true` to measurements enough to block MongoDB TTL?

**Answer:** No. Collection-level TTL still expires by `timeField`. Isolate legal-hold data or design a policy exempting it from short TTL.

### Exercise 19. Investigating Secondary Reads

The primary already deleted a bucket via TTL, yet a client reading from a secondary still sees old measurements.

**Question:** What explains this temporary discrepancy?

**Guidance:** The secondary may not have applied the delete yet due to replication lag. TTL does not enforce strong read consistency across secondaries.

### Exercise 20. Designing a Metrics System

Build a system with:

~~~text
Raw server metrics:         3 days
Hourly rollups:            90 days
Monthly reports:            2 years
Allowed sensor backfill:   24 hours
Allowed aggregation retry: 48 hours
~~~

Propose:

1. Which collections should be time series?
2. TTL for each tier.
3. Whether 3-day raw retention leaves enough margin for 24-hour ingestion delay plus 48-hour retries, or needs extra headroom.
4. How to prevent aggregation retries from duplicating summaries.
5. Which time range real-time dashboards query.
6. What backup/archival policies are needed alongside TTL.

**Guidance:** Use a 3-day raw time series collection only if actual SLAs and safety margins fit comfortably, an hourly collection with 90-day TTL, and an appropriate 2-year report store. Add checkpoints/watermarks, keyed upserts on `(sensor, hour)`, and separate backup governance—never treat three TTL numbers as a complete architecture.

## 26. Sample Rollout Roadmap for a Sensor System

### Phase 1. Agree on the Data Contract

Each measurement contains:

~~~javascript
{
  timestamp: ISODate("2026-11-14T10:00:00Z"),
  sensor: {
    sensorId: "S-101",
    site: "HCM-01",
    retentionClass: "STANDARD"
  },
  temperatureC: 28.5,
  receivedAt: ISODate("2026-11-14T10:00:03Z")
}
~~~

Explicit rules:

- `timeField` is **`timestamp`** representing event time.
- `receivedAt` records ingestion time to measure lag.
- `sensorId`/`site`/`retentionClass` are stable metadata.
- Out-of-bounds past/future timestamps follow an explicit policy.

### Phase 2. Size Retention for Downstream Pipelines

Example:

~~~text
Max sensor offline duration: 1 day
Aggregation job retries:     2 days
Extra incident buffer:       2 days
Raw retention:               7 days
~~~

This illustrates buffered retention. If retries can exceed 7 days, increase retention or introduce staging/archival storage.

### Phase 3. Create the Collection

~~~javascript
db.createCollection("rawMetrics7d", {
  timeseries: {
    timeField: "timestamp",
    metaField: "sensor",
    granularity: "seconds"
  },
  expireAfterSeconds: 604800
});
~~~

### Phase 4. Build the Downsampling Job

Run hourly, persist summaries under fixed business key **`(sensorId, hourStart)`**, track watermarks, and make retries idempotent.

### Phase 5. Display Only Valid Windows

Real-time APIs filter:

~~~javascript
{
  timestamp: {
    $gte: from,
    $lt: to
  }
}
~~~

Never rely on TTL having removed every expired timestamp on deadline.

### Phase 6. Monitor Operations

Track retained measurement counts, TTL monitor metrics, query latency, I/O, replication lag, job watermarks, and sensor clock-skew rates.

### Phase 7. Control Changes

Version all TTL and partial TTL updates, assess deletion impact, verify backups/archives, and require formal approval.

## 27. Version-Specific Reference Documentation

TTL and time series capabilities vary across **MongoDB versions and Feature Compatibility Versions**. Always consult official documentation for your exact running version:

- [MongoDB Manual — Automatic Removal for Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-automatic-removal/)
- [MongoDB Manual — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB Manual — Time Series Indexes](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-index/)
- [MongoDB Manual — collMod](https://www.mongodb.com/docs/manual/reference/command/collmod/)
- [MongoDB Manual — Create and Query Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-procedures/)

**Note:** `/manual` URLs typically point to the current release; for MongoDB 6.x, 7.x, or 8.x environments, select the matching version in the docs to verify partial TTL support, custom bucketing, and index/operation limits.

## 28. Conclusion

MongoDB TTL is an effective mechanism for keeping **time series storage within a bounded lifecycle**, provided its mechanics are well understood:

~~~text
Measurement with BSON Date timestamp
                 |
                 v
TTL threshold = timestamp + expireAfterSeconds
                 |
                 v
Measurement exceeds threshold age
                 |
                 v
Is its bucket eligible for expiration?
            /                  \
          No                    Yes
           |                     |
      Wait for newer             v
      readings to expire    TTL monitor sweeps in background
                                 |
                                 v
                          Bucket is deleted
                                 |
                                 v
                        Storage space becomes
                        available for reuse
~~~

**Core principles:**

1. **Time series TTL evaluates `timeField`**, never automatically substituting insertion time or an arbitrary `expireAt` field.
2. **Measurement expiration and bucket deletion are separate moments.** The background TTL monitor gives no exact-second physical deletion guarantee.
3. **`granularity` governs bucket spans**, not retention. Wide bucket spans can keep expired readings alive longer.
4. **Collection-level `expireAfterSeconds`** can be set at creation or updated via `collMod`. Use **`"off"`** to disable on supported versions, never `0`.
5. **Time series partial TTL** on supporting versions filters on `metaField` to expire a subset **sooner**; it cannot keep a subset longer than a shorter collection-level TTL.
6. **Backfills and sensor clock skew** can trigger premature deletion or unexpected persistence. Decide explicitly between event time and ingest time.
7. **TTL is neither a query filter, an archive, nor a downsampling job.** Each responsibility requires its own mechanism and SLA.
8. **Shortening retention can trigger massive deletions that cannot be rolled back by raising TTL again.** Check backups, I/O, replication, and dependent reports beforehand.
9. **MongoDB TTL does not purge copies in backups, caches, or warehouses.** Retention and deletion policies must span the entire data lifecycle.
10. **Monitor TTL using actual data and relevant metrics**, not merely `expireAfterSeconds` or OS file sizes.

With well-designed `timeField`, retention windows, bucketing, partial TTL, and aggregation pipelines, MongoDB time series collections efficiently store short-term raw streams while supporting long-term analytics. The critical question is not "after how many seconds does data vanish?"—it is **"until when must data remain usable, when is MongoDB permitted to remove it, and has the entire system finished processing it before it disappears?"**
