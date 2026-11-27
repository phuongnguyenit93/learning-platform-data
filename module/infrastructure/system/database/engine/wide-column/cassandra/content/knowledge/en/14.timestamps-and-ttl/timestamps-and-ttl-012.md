# Lifetime and Expiration Timestamp Limits Across Apache Cassandra Versions

## 1. The Problem: Why Can an Arithmetically Valid TTL Still Be Rejected?

**Apache Cassandra** is a **distributed wide-column** database. For data that only needs to be retained for a finite duration, an application can specify **time to live (TTL)** in `INSERT`/`UPDATE` statements or configure `default_time_to_live` on the table. TTL is declared in **seconds** and applies to the written cells.

However, **TTL is not limited solely by the integer range accepted by CQL**. Cassandra must also represent an **absolute expiration timestamp** in its internal metadata. On version lines that store expiration times bounded by a 32-bit Unix timestamp ceiling, a very long TTL can request an expiration date **beyond what the storage format supports**.

For example, a system wants to retain data for 20 years:

```sql
-- Do not run this in production: illustrates a retention requirement only.
INSERT INTO retention_demo_by_id (item_id, payload)
VALUES (11111111-1212-4121-8121-111111111111, 'long-lived')
USING TTL 630720000;
```

`630720000` seconds is roughly 20 years (at 365 days/year). In an environment with an expiration ceiling at **2038-01-19**, this request **becomes invalid** when issued in years close to 2038, even though the number `630720000` still fits inside a 32-bit signed integer.

**Lesson objective:** distinguish **TTL numeric value limits**, **expiration date limits**, and **version/configuration-dependent overflow behavior**; and establish safe checks across CQL, the Java Driver, and cluster operations.

> **Important compatibility note:** The limits and policies discussed here reflect expiration-horizon mechanics documented across many Cassandra 3.x/4.x releases. **Never assume every Cassandra release, Cassandra-compatible distribution, and patch level shares the exact same limit or behavior.** When deploying, verify against your running version, its official documentation, and actual configuration.

## 2. Three Kinds of Time Not to Confuse

In the **Timestamps and TTL** chapter, distinguish carefully:

| Property | Unit / representation | What is it used for? | How does it relate to expiration limits? |
|---|---|---|---|
| `USING TTL N` | **Seconds** of additional life | Sets lifetime for the new cell version | Cassandra must compute the expiration date from write time + `N` |
| `default_time_to_live` | **Seconds**, table setting | Default TTL for newly written cells | Writes without an explicit TTL are still subject to expiration checks |
| **Mutation/write timestamp** | Epoch **microseconds** (64-bit integer) | Arbitrates versions of the same cell via **last-write-wins** | Not the base timestamp to which TTL is added here |
| CQL column of type `timestamp` | Epoch **milliseconds** (64-bit) | Stores business dates/times | Can store far-future dates that TTL expiration does not support |
| **Expiration / local deletion time** | Internal timestamp at second resolution | Determines when the cell expires and deletion metadata age | Can be subject to version-dependent representation limits |
| `ttl(column)` | **Remaining seconds** | Observes TTL of a live cell | Helps verify actual TTL after writing; does not show cluster-wide policy |

Specifically: **the fact that a CQL `timestamp` column can store a date past 2038 does not mean a cell is allowed to have a TTL expiring past 2038 in every Cassandra version.**

A semantically valid example:

```sql
INSERT INTO retention_demo_by_id (item_id, payload, business_deadline)
VALUES (
    22222222-1212-4121-8121-222222222222,
    'has a business deadline',
    '2045-01-01T00:00:00Z'
)
USING TTL 3600;
```

The `business_deadline` cell stores a 2045 date **as business data**, while the cell's TTL is only **3,600 seconds from the write**. Never infer expiration metadata representation capabilities from the `timestamp` column data type.

## 3. The 2038 Cutoff and 32-Bit Unix Time Representation

For a **signed 32-bit integer counting seconds since the Unix epoch**, the largest positive value is:

```text
2^31 - 1 = 2,147,483,647 seconds
          = 2038-01-19T03:14:07Z
```

This boundary is commonly known as the **Year 2038 problem**. Cassandra versions using this kind of limit for expiration timestamps must handle the condition:

```text
server time used to compute expiration + requested TTL
                  > representable expiration horizon
```

Illustration:

```text
                                  2038-01-19 03:14:07 UTC
                                            |
       write date                           | LIMIT
          |                                 |
          +-------- short TTL ------------->|  within supported horizon
          |
          +---------------- very long TTL --------------------> exceeds limit
```

When the limit is exceeded, Cassandra **cannot store the exact expiration date the client requested** under that bounded representation. Some versions have a **policy to reject the request or cap the deadline at the maximum supported timestamp**. The exact policy and configuration setting name must be verified on the running Cassandra version.

### There Is No Fixed "20-Year Maximum TTL"

If a system is bounded by the absolute cutoff `2038-01-19T03:14:07Z`, **the maximum TTL measured from the present shrinks every second**.

Arithmetic example—suppose the authoritative clock is at `2038-01-18T03:14:07Z`, i.e., **86,400 seconds** before that cutoff:

| Requested TTL | Expected expiration date | Within limit? |
|---|---|---|
| `3600` seconds | 23 hours before cutoff | Yes |
| `86400` seconds | Exactly at the boundary | Right at the edge; evaluate actual rules and safety margin |
| `86401` seconds | 1 second past cutoff | No, if bounded by this 32-bit limit |

Therefore, never hardcode a constant "20 years" as the maximum TTL for every year and every environment. Compute it dynamically from **current write time, version limit, and a safety margin**.

## 4. Numeric Bounds and Expiration Date Bounds Are Two Distinct Layers

A TTL value must pass at least two checks:

1. **Syntactically and numerically valid?** CQL TTL is expressed in seconds; negative values are rejected, and numeric types also have bounds.
2. **Is the expiration date valid under the storage format and server policy?** Even when the TTL integer fits within allowed bounds, `serverNow + ttlSeconds` can still surpass the supported expiration horizon.

Examples:

| Input | Meaning / risk |
|---|---|
| `USING TTL 3600` | 1 hour; usually easy to manage |
| `USING TTL 0` | **No TTL applied** to the new cell version; not "expire immediately" |
| `USING TTL -5` | Negative TTL: invalid |
| `USING TTL 630720000` | Roughly 20 years; may exceed expiration horizon depending on write year/version |
| `USING TTL 2147483647` | Maximum signed 32-bit integer; **does not** mean it is usable in practice |
| `USING TTL 630720000000` | Very likely a **milliseconds vs. seconds** mistake, exceeding both numeric and expiration limits |

**Unit error sign:** Java's `Duration.toMillis()` returns **milliseconds**, whereas CQL `USING TTL ?` expects **seconds**. For 30 days, the right value is `30 × 24 × 3600 = 2592000` seconds; passing milliseconds by mistake yields `2592000000`, exceeding limits and failing the intended retention semantics.

## 5. Overflow Policies When Expiration Exceeds the Horizon: REJECT and CAP

In Cassandra versions that support configuring `expiration_date_overflow_policy`, common modes include:

| Policy | Conceptual behavior on expiration overflow | Operational risk |
|---|---|---|
| `REJECT` | Rejects mutations requesting an unrepresentable expiration date | Application must handle errors, yet avoids silently altering retention |
| `CAP` | Caps/truncates expiration to the maximum supported timestamp, usually with a warning | Data can **expire earlier** than the duration the client requested |
| `CAP_NOWARN` | Caps similarly to CAP without emitting the same warning | Truncation can go **unnoticed** without explicit monitoring |

Mode names and whether the setting exists **depend on the Cassandra version or distribution**. Never copy an `expiration_date_overflow_policy` line into every `cassandra.yaml` without confirming it is recognized by that version. Nor should you assume the **default** value is identical across clusters.

For example, business rules require retaining records for 15 years, while the cluster's expiration horizon only has about 11 years left:

- With **REJECT**, writes can fail immediately. That signals the need to adjust retention or upgrade/redesign architecture.
- With **CAP**, writes may succeed while expiration is truncated. If the application assumes data is guaranteed to live a full 15 years, a **retention compliance violation** occurs.
- With **CAP_NOWARN**, the discrepancy may only surface when comparing observed TTLs, metrics, or policy audits.

**Especially dangerous:** never use CAP as a way to treat data as "never expiring." CAP can assign many records **the same distant expiration timestamp**, risking mass data loss when that moment arrives and amplifying tombstone/compaction pressure.

## 6. Distinguishing Table Default TTL and Statement-Specified TTL

A table with `default_time_to_live = 0` means **no default TTL**. When set to a positive integer, Cassandra applies that TTL to newly written cells if the statement omits `USING TTL`.

```sql
CREATE TABLE IF NOT EXISTS retention_demo_by_id (
    item_id uuid PRIMARY KEY,
    payload text,
    business_deadline timestamp
) WITH default_time_to_live = 86400;
```

With this table:

```sql
-- 1. Uses default TTL: 86,400 seconds = 1 day.
INSERT INTO retention_demo_by_id (item_id, payload)
VALUES (
    33333333-1212-4121-8121-333333333333,
    'default-retention'
);

-- 2. Explicit 1-hour TTL takes precedence over default TTL.
INSERT INTO retention_demo_by_id (item_id, payload)
VALUES (
    44444444-1212-4121-8121-444444444444,
    'short-retention'
)
USING TTL 3600;

-- 3. TTL 0 for the new version: no TTL.
INSERT INTO retention_demo_by_id (item_id, payload)
VALUES (
    55555555-1212-4121-8121-555555555555,
    'persistent'
)
USING TTL 0;
```

If mutations win by timestamp, the three `payload` cells have policies of: 1 day, 1 hour, and no TTL. Notably, **both `default_time_to_live` and `USING TTL` are subject to the server's expiration horizon**. Omitting `USING TTL` in CQL **does not bypass the limit** if the table itself has an overly long default TTL.

Changing the default TTL via `ALTER TABLE` only affects **subsequent mutations**, without recalculating expiration dates of existing cells:

```sql
ALTER TABLE retention_demo_by_id
WITH default_time_to_live = 604800;
```

New writes without an explicit TTL will use 7 days. Cells previously written with 1 day, 1 hour, or no TTL **are not automatically rewritten**.

## 7. Safe Practice: Observing TTL Instead of Intentionally Triggering Overflow Errors

To learn the mechanics without depending on a cluster's overflow policy, start with short TTLs in a test keyspace.

```sql
-- Use a fresh UUID to avoid values/tombstones from prior tests.
INSERT INTO retention_demo_by_id (item_id, payload)
VALUES (
    66666666-1212-4121-8121-666666666666,
    'ttl-120-seconds'
)
USING TTL 120;

SELECT payload,
       writetime(payload) AS write_timestamp_us,
       ttl(payload) AS remaining_seconds
FROM retention_demo_by_id
WHERE item_id = 66666666-1212-4121-8121-666666666666;
```

Expectations:

- `remaining_seconds` is a positive integer near **120**, decreasing over time.
- `write_timestamp_us` is epoch **microseconds**; it is completely distinct from TTL.
- After expiration, `payload` is no longer a live cell to observe. CQL never returns a "negative TTL."

In an isolated test environment with **confirmed version and overflow policy**, you can test error/capping cases following your operations team's guidelines. **Never run huge-TTL statements in production** just to see how the server responds; under a CAP policy, you could accidentally create data that lives for years or right up to the horizon boundary.

### Checking Version and Schema Information

Read-only reference queries in CQL:

```sql
-- Release version reported by the currently connected node.
SELECT release_version FROM system.local;

-- Replace demo_ks with your actual test keyspace.
SELECT keyspace_name, table_name, default_time_to_live,
       gc_grace_seconds
FROM system_schema.tables
WHERE keyspace_name = 'demo_ks'
  AND table_name = 'retention_demo_by_id';
```

`system.local` reports the version of the **currently connected node**, not proof that the entire cluster is uniform during a rolling upgrade. Cross-check all nodes and distributions, and verify `cassandra.yaml` documentation for your exact version to confirm support and values for `expiration_date_overflow_policy`.

## 8. When Running Multiple Versions: Where to Check?

A cluster may undergo a **rolling upgrade** for some period. Meanwhile, a Java application can connect to different coordinators via load balancing. If limits, policies, or expiration mechanics **differ across versions**, the exact same ultra-long TTL request can behave differently during the transition.

A compatibility verification sequence should include:

1. Identify the **exact Cassandra version on every node** (including patch level and distribution).
2. Read the release notes/upgrade docs for those exact versions regarding **TTL, expiration timestamps, Year 2038, overflow policies, and SSTable formats**.
3. Verify the **actual config** on each node via administrative procedures. Never assume every node picked up the new config.
4. Audit **table default TTLs** and all `USING TTL` write paths across applications and import pipelines.
5. Validate limits via **canary tests in a staging environment matching the version**, using conservative TTLs and arithmetic boundary tests—no need to create 30-year records in production.
6. Confirm **rollback and backup** plans if policy changes could make data expire early or cause mutations to be rejected.

**There is no reliable "Cassandra 3.x = X, 4.x = Y, 5.x = Z" lookup table without checking patch levels and deployment docs.** Understand the root cause at the timestamp-format layer and follow a verification process rather than memorizing a potentially outdated version threshold.

### Version Milestones and Semantic Changes

When a newer version changes expiration timestamp representation or overflow handling, upgrading from an older version **must not be assumed to automatically extend TTLs on previously written cells**. Stored expiration metadata may continue carrying the bounds/values from the original write. Always read upgrade guides, check SSTable compatibility, and test data written by the prior version.

## 9. Arithmetic Example: Computing Maximum TTL Dynamically, Not Hardcoding "20 Years"

If a deployment genuinely bounds expiration times at signed epoch seconds `2_147_483_647`, the arithmetic bound at a given moment is:

```text
maxExpirationEpochSeconds = 2_147_483_647
nowEpochSeconds            = current UTC time from a trusted source
safetyMarginSeconds        = buffer for clock skew / processing latency

maxSafeTtlSeconds =
    maxExpirationEpochSeconds
    - nowEpochSeconds
    - safetyMarginSeconds
```

With a **hypothetical** example at `2038-01-18T03:14:07Z`:

```text
maxExpirationEpochSeconds = 2_147_483_647
nowEpochSeconds           = 2_147_397_247
rawHeadroomSeconds        = 86_400
safetyMarginSeconds       = 300
maxSafeTtlSeconds         = 86_100
```

If an 86,200-second TTL is needed, the system has **insufficient safety margin**, even though it has not yet crossed the raw 86,400 ceiling. The right behavior is to **reject or switch storage policy**, not silently shrink to 86,100 when retention is a mandatory business obligation.

Use this formula only when the deployment's limit has been **confirmed**. If your version supports a different ceiling, replace both the limit and check logic accordingly. Never treat `2_147_483_647` as the permanent expiration ceiling across all Cassandra releases.

## 10. Java Driver 4.x: Validating TTL and Expiration Before Writing

In Java, a prepared statement can bind TTL as an integer number of seconds. The code below illustrates a **conservative policy for a cluster confirmed to have a signed-32-bit 2038 ceiling**; it does not apply universally to every cluster and does not replace server-side validation.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class SafeTtlWriter {
    // Use ONLY when this ceiling has been CONFIRMED on the target deployment.
    private static final long MAX_EXPIRATION_EPOCH_SECONDS = 2_147_483_647L;
    private static final long SAFETY_MARGIN_SECONDS = 300L;

    private final CqlSession session;
    private final Clock clock;
    private final PreparedStatement insert;

    public SafeTtlWriter(CqlSession session, Clock clock) {
        this.session = session;
        this.clock = clock;
        this.insert = session.prepare(
            "INSERT INTO retention_demo_by_id (item_id, payload) " +
            "VALUES (?, ?) USING TTL ?"
        );
    }

    public void saveFor(UUID id, String payload, Duration retention) {
        if (retention.isNegative() || retention.isZero()) {
            throw new IllegalArgumentException("Retention must be positive");
        }

        long seconds = retention.getSeconds();
        if (seconds <= 0 || seconds > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("TTL seconds out of int range");
        }

        long nowSeconds = clock.instant().getEpochSecond();
        long latestAllowedExpiration = MAX_EXPIRATION_EPOCH_SECONDS
            - SAFETY_MARGIN_SECONDS;
        long expiration = Math.addExact(nowSeconds, seconds);
        if (expiration > latestAllowedExpiration) {
            throw new IllegalArgumentException(
                "TTL would exceed supported expiration horizon"
            );
        }

        // Final enforcement still rests with Cassandra.
        session.execute(insert.bind(id, payload, Math.toIntExact(seconds)));
    }

    public void saveUntil(UUID id, String payload, Instant expiresAt) {
        long wholeSeconds = Duration.between(clock.instant(), expiresAt)
            .getSeconds();
        if (wholeSeconds <= 0) {
            throw new IllegalArgumentException("Already expired");
        }
        saveFor(id, payload, Duration.ofSeconds(wholeSeconds));
    }
}
```

**Intentional caveats of this example:**

- `MAX_EXPIRATION_EPOCH_SECONDS` only holds for **deployments confirmed** to have the 2038 cutoff. For versions supporting a larger horizon, supply the corresponding limit from configuration rather than keeping this constant.
- `Clock` must be synchronized with a trusted source; the server processes the write **after** the client checks. The safety margin mitigates, but does not eliminate, timing races.
- `Duration.getSeconds()` truncates to whole seconds; a retention under 1 second is rejected so it is never accidentally turned into `TTL 0`.
- `USING TTL 0` means **no TTL**, not "expire immediately." Never pass it to represent an already-passed `expiresAt`.
- `saveUntil` recomputes remaining time before calling `saveFor`; absolute deadlines still require business-layer enforcement when high precision is needed.
- You can also enforce a **product/SLA retention cap** well below technical limits; APIs should not let callers arbitrarily request multi-year TTLs.

## 11. When Required Retention Exceeds Technical Limits: What Not to Do

Several dangerous "quick fixes":

| Approach | Why it is wrong or risky |
|---|---|
| Passing `Duration.toMillis()` into `USING TTL` | Unit mix-up; produces oversized TTLs or errors |
| Using `USING TTL 0` to mean "expire immediately" | TTL 0 = **no TTL**, retaining data indefinitely |
| Picking `CAP` so requests stop failing | Can silently **shorten** mandatory retention |
| Bumping `USING TIMESTAMP` to a future date | Can "poison" LWW; **does not solve** expiration limits |
| Setting a huge `default_time_to_live` and assuming it works | Subsequent writes still go through server expiration rules |
| Splitting TTL into uncontrolled renewal jobs | Vulnerable to downtime, missed renewals, races, and premature expiration |
| Lowering `gc_grace_seconds` | Only alters tombstone protection window, **not** the expiration horizon |

If mandatory retention exceeds the supported horizon, consider:

1. **Not using TTL for that data category.** Store `expires_at`/`retention_until` as **business data**, with explicit checks on read paths and a managed archival/deletion job.
2. **Choosing a long-term storage tier** suited for retention/compliance (including backups, auditing, access control, and verified physical deletion).
3. **Upgrading or changing version/architecture** only after verifying the target version supports the new horizon and having a data migration plan.
4. **Coordinated renewal** only if aligned with business goals and accepted risk. Must have clear ownership, monitoring, retry/idempotency, failure alerting when renewals miss, and never rely on TTL alone as compliance proof.

Storing `expires_at` without TTL **does not delete data automatically**. If choosing that approach, design a **dedicated purge pipeline** and partition/time-bucket query strategy rather than scanning tables with `ALLOW FILTERING`.

## 12. Long TTLs, Tombstones, Compaction, and Repair

Once a cell's TTL expires, Cassandra no longer considers it a live value. Expiration/tombstone metadata prevents stale copies from other replicas or SSTables from resurfacing. **Physical byte reclamation** occurs during compaction when safety conditions are met, not necessarily at the moment TTL ends.

A TTL capped by `CAP` to a maximum expiration boundary can cause many cells to **expire around the same time**. Consequences to account for:

- A surge of tombstones/expired cells appearing in a short window when that boundary arrives.
- Increased **read, compaction, disk usage, and tombstone garbage-collection** pressure.
- Temporarily disconnected replicas may miss mutations, so **repair** and `gc_grace_seconds` remain critical to prevent **zombie data**.
- Logical expiration does not guarantee data vanishes immediately from **snapshots, backups, or SSTables**.

For time-series workloads with uniform retention, consider **TimeWindowCompactionStrategy (TWCS)** with an appropriate time bucket. However, ultra-long TTLs, past/future write timestamps, backfills, and random updates can cause SSTable windows to overlap and impede data cleanup. Never pick a compaction strategy solely from one TTL number.

**Replication factor (RF)** and **consistency level (CL)** are separate mechanisms: `ONE`, `QUORUM`, `ALL` neither fix expiration limits nor alter LWW arbitration by mutation timestamp.

## 13. Query-Driven Table Design for Very Long Retention

In Cassandra, design tables around **the queries the application will run**, rather than treating TTL as a sorting mechanism.

Suppose a system stores immutable transactions queried by customer and month:

```sql
CREATE TABLE IF NOT EXISTS audit_events_by_account_month (
    account_id uuid,
    event_month text,
    event_time timeuuid,
    event_type text,
    payload text,
    retention_until timestamp,
    PRIMARY KEY ((account_id, event_month), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);

SELECT event_time, event_type, retention_until
FROM audit_events_by_account_month
WHERE account_id = 77777777-1212-4121-8121-777777777777
  AND event_month = '2026-11'
LIMIT 100;
```

Here:

- `event_time` is the **clustering key** serving historical queries.
- `retention_until` is a **business timestamp** that can lie far in the future, independent of TTL.
- If required retention exceeds what TTL supports, you can **omit TTL** for this data and use a separate, controlled retention/purge process.
- `event_month` is a bucket to bound partition size; choose bucket granularity based on actual traffic.
- `timeuuid` assists time-based ordering yet does not fully solve clock skew across multiple writers. If strict business ordering is critical, use a sequence/trusted coordinator.

**Never write `ORDER BY writetime(payload)`** and never treat mutation timestamps as default retention times: that is LWW metadata, not a query structure or storage contract.

## 14. Diagnosing Errors or Truncated Long TTLs

A suitable checklist for Java/Cassandra teams:

| Symptom | Possibilities | What to check |
|---|---|---|
| `INSERT USING TTL` rejected despite positive TTL | Expiration date exceeds horizon; invalid TTL value or REJECT policy | Node version, server error, epoch seconds, requested TTL, policy |
| Write succeeded yet `ttl(col)` is much smaller than requested | CAP truncated expiration, or another write won | Overflow config, `writetime()`, update history, replicas |
| Same request sometimes succeeds, sometimes fails | Mixed coordinators/configs in a mixed-version cluster or policy change | Version/config per node, routing, logs |
| Data retained longer than required | TTL 0, no TTL, different default TTL, or repeated writes refreshing TTL | Actual CQL sent, schema, retries, winning cell's TTL |
| Data expired earlier than retention obligation | CAP policy or app capped TTL too low | Logged computed TTL, `retention_until`, `ttl()` near write time |
| `ttl(col) = null` yet value remains | Cell has no TTL | `USING TTL 0`, table default TTL, latest UPDATE |
| TTL unchanged after `UPDATE` | Mutation lost LWW or read hasn't seen the new version | `writetime()`, timestamp source, CL/replicas |
| TTL expired yet disk usage hasn't dropped | Tombstones/SSTables awaiting safe compaction | Compaction, `gc_grace_seconds`, snapshots/backups |

Use structured logging: `requestId`, operation type, `ttlRequestedSeconds`, `expiresAtBusinessUtc`, coordinator version/routing if tracked, client-supplied mutation timestamp if any, and Cassandra error details. **Never log real tokens, credentials, or unnecessary sensitive data.**

To distinguish CAP from retries/overwrites, read `ttl(col)` **immediately after a canary write** on a fresh key, then compare against the requested TTL and elapsed time. Never rely solely on a single read, since clocks, latency, and consistency level can slightly shift observed values.

## 15. Operational Procedure for Version-Based Expiration Limits

When preparing to raise TTL retention from days to multiple years, proceed in order:

1. **Define SLA and retention policy:** exact minimum retention duration, earliest allowed deletion time, and any legal/audit requirements.
2. **Inventory the Cassandra deployment:** every node's version, distribution, patch level, schema/metadata, timestamp generator, and UTC clocks.
3. **Read documentation for the exact versions:** expiration date limits, `expiration_date_overflow_policy` if present, Year 2038 changes, and SSTable upgrades.
4. **Compute the target expiration date** from a trusted time source, including a write-path safety margin.
5. **Choose behavior that protects obligations:** REJECT usually surfaces retention violations more clearly than CAP, though neither replaces error handling and recovery plans.
6. **Test in staging/canary:** verify `USING TTL`, `default_time_to_live`, TTL 0, `ttl(col)`, overflow errors, and real timing.
7. **Roll out with monitoring:** track rejected/capped requests, clock skew, tombstones/compaction, repair, and disk usage.
8. **Prepare a rollback plan** for config or schema changes; do not assume changing policy rewrites TTL metadata on already-written cells.

Administrative tasks like editing `cassandra.yaml`, upgrading clusters, or changing compaction strategies must follow controlled procedures. **Never manually modify SSTables or lower `gc_grace_seconds` to work around expiration limits.**

## 16. Scenario Exercises and Answers

**Question 1.** Why can a ~20-year TTL be numerically valid yet get rejected by a Cassandra deployment in 2026?

**Answer:** Because the expected expiration date can exceed the **maximum expiration horizon** of the metadata format/version—such as the signed-32-bit 2038 cutoff—even though `ttlSeconds` fits within the allowed integer range.

**Question 2.** On a system bounded at `2038-01-19T03:14:07Z`, is the maximum safe TTL always 20 years at any point in time?

**Answer:** No. The headroom before the boundary **shrinks over time**, so the dynamic maximum TTL must be computed from current time minus a safety margin.

**Question 3.** An expiration date overflows the limit; does the `CAP` policy always satisfy a 15-year retention requirement?

**Answer:** No. CAP can **truncate** the expiration date back to the supported boundary. If retention is a minimum obligation, this can violate requirements even while writes report success.

**Question 4.** If a CQL `timestamp` column can store a date in 2045, can you infer that a cell is always allowed to have a TTL expiring in 2045?

**Answer:** No. A `timestamp` column is **64-bit millisecond business data**; it does not determine TTL expiration metadata bounds.

**Question 5.** Is `USING TTL 0` the way to make a record expire immediately once `expiresAt` is already in the past?

**Answer:** No. TTL 0 means **no TTL**. For already-expired entities, reject the write or handle deletion/business logic appropriately.

**Question 6.** An `INSERT` statement omits `USING TTL`, yet the table has a very long `default_time_to_live`. Does it avoid expiration limits?

**Answer:** No. The default TTL still applies to newly written cells and is subject to expiration-date limit checks.

**Question 7.** A Java application passes `Duration.toMillis()` as the parameter to `USING TTL ?`. What is the bug?

**Answer:** Confusing **milliseconds** with **seconds**; convert `Duration` to valid seconds and check bounds and deadlines.

**Question 8.** During a rolling upgrade, nodes differ in version/config. Should you trust `SELECT release_version FROM system.local` on one coordinator as proof the whole cluster is uniform?

**Answer:** No. That query reflects only the connected node; inventory the versions and configs of **all nodes**.

**Question 9.** If TTL cannot be used for a 30-year retention requirement, can you store `retention_until timestamp` without TTL? What is still missing?

**Answer:** You can store the business deadline in an appropriate schema, yet you still need a separate **retention/purge workflow, backup/audit process, and deadline enforcement**. A timestamp column does not delete data on its own.

**Question 10.** What happens if many records get capped by CAP to the same expiration boundary?

**Answer:** They can **expire in a concentrated burst**, creating tombstone/compaction load and unexpected business retention risks. CAP is not a default cure-all.

---

**Key takeaway:** **TTL value limits are distinct from expiration timestamp limits**. On Cassandra versions with a signed-epoch-seconds expiration horizon, **2038-01-19** is a critical boundary that causes the maximum TTL to **shrink over time**. Overflow behavior may **reject or cap** lifetimes depending on version and `expiration_date_overflow_policy`. Before using long TTLs, verify actual versions and configs, validate in Java and on the server, never confuse TTL seconds with milli/microsecond timestamps, and never let a CAP policy silently alter retention obligations undetected.
