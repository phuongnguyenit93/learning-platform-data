# Garbage Collection, Timestamps, and Cell Lifecycle

A Java system writes sensor temperatures to **Bigtable** every minute. Each update to the same column can create a **new cell version** with a different timestamp, causing history to grow continuously. If the business only needs detailed data for 7 days and at most 3 versions per column, you must combine **garbage collection (GC)** to bound storage with **read filters** so users do not see data that has expired but has not yet been physically collected.

This lesson belongs to the **Bigtable and Memorystore** chapter in the **CLOUD_PROVIDERS_GCP** module. The focus is the **Bigtable cell** lifecycle: version creation, timestamps, per-column-family GC rules, compaction, read filtering, testing, and operations. The Memorystore section only compares **TTL/eviction** to avoid confusing the two mechanisms; they do not replace one another.

After this lesson, you will be able to:

- Explain the hierarchy `row key → column family → qualifier → timestamp → value` and multiple versions within a column.
- Distinguish microsecond units stored in timestamps from a table's **default millisecond granularity**.
- Choose `maxage`, `maxversions`, `and`, and `or` according to data retention contracts.
- Use `cbt` and the Java client to write/read multiple versions, apply GC policies, and apply read filters.
- Distinguish **asynchronous GC** from **application-initiated deletes**; avoid treating GC as an instant TTL.
- Predict the impact of backfills, future timestamps, replication, and retention changes.
- Control IAM, storage costs, read performance, policy drift, and privacy.

> **Lab environment:** operate only on test instances/tables with synthetic data, proper authorization, and known cost limits. A stricter GC rule can **permanently delete older versions**, including data written before the rule change. Never test policy changes on a production table.

## 1. A Cell in Bigtable Is a Timestamped Version

Bigtable is a **wide-column** database. A row's data consists of **column families**; each family contains multiple **column qualifiers**. An intersection `(rowKey, family, qualifier)` can store **multiple cells**: each cell is a `(timestamp, value)` version.

~~~text
Table: telemetry
Row key: device#8a7f#20261119
├── family readings
│   ├── qualifier temperature
│   │   ├── timestamp T3  → "22.4"   (newest)
│   │   ├── timestamp T2  → "21.9"
│   │   └── timestamp T1  → "21.2"   (oldest)
│   └── qualifier humidity
│       ├── timestamp T2  → "62"
│       └── timestamp T1  → "64"
└── family current
    └── qualifier status
        └── timestamp T3  → "online"
~~~

**Common points of confusion:**

- `readings:temperature` has three **cells/versions**, not three columns.
- GC applies **to the entire column family**, e.g., `readings`; however, `maxversions=2` is evaluated **independently per qualifier** within each row, rather than keeping 2 total cells across the family.
- Two families can have different policies: `readings` keeps 7 days of history, while `current` keeps only one version.
- The row key determines which data range is read; **GC does not automatically delete an entire row** based on row-key age, but evaluates cells inside families. A row with no remaining valid cells simply disappears from read results.

### Distinguishing Cell Timestamps from Business Event Times

A sensor records data on Nov 10 but uploads it to the server on Nov 19:

| Stored timestamp | How Bigtable interprets it | Consequence if GC is `maxage=7d` |
|---|---|---|
| **Nov 10** (event time) | Cell is already 9 days old | May be eligible for GC immediately upon write |
| **Nov 19** (ingestion time) | Cell was just created | Retained for roughly 7 days from ingestion |
| **Future date** | Cell has not reached the age threshold | May be retained longer than expected |
| **0 or dummy timestamp** | Synthetic/non-real timestamp | Risks premature GC or unintended retention |

Before writing policies, decide whether **retention is measured by event time or ingestion time**. If you need both, store the event time in the value/qualifier or an appropriate row-key structure, while keeping the cell timestamp consistent in meaning.

## 2. Timestamp Units: Microseconds with Default Millisecond Granularity

A Bigtable cell timestamp is a 64-bit integer representing **microseconds since the Unix UTC epoch**. However, **new tables default to millisecond granularity**, so application-supplied timestamps must be **divisible by 1,000**.

~~~text
Millis since epoch:  1795000000123
Micros since epoch: 1795000000123000   ← valid on a MILLIS table
Micros since epoch: 1795000000123456   ← may be rejected on a MILLIS table
~~~

In Java:

~~~java
long timestampMicros = System.currentTimeMillis() * 1_000L;
// Unit is micros, precision is millis; divisible by 1000.
~~~

**Do not pass `System.currentTimeMillis()` directly** to an API expecting microseconds: it will be off by a factor of 1,000 and interpreted as dates near 1970. Conversely, multiplying `Instant.now().toEpochMilli()` by 1,000 still gives millisecond precision, which is **valid** for default tables.

Under current features, Bigtable supports **true microsecond granularity** on tables created with the corresponding configuration on **Enterprise Plus edition**. Do not assume every instance/table accepts non-millisecond microsecond timestamps; check edition, table metadata, and client libraries before relying on it.

### Server/Client Timestamps and Same-Timestamp Writes

- Omitting timestamp: the client library or Bigtable assigns a "current" timestamp along the supported write path; generally use the default unless event time is required.
- Specifying timestamp: use **UTC epoch microseconds** compatible with table granularity; the application owns clock skew, backfills, and late-arriving data.
- **One column at the same timestamp cannot hold two independent values**: overwriting the exact same `(row, family, qualifier, timestamp)` tuple replaces the prior value rather than creating a separate version. If distinct events must be preserved, distinguish them in the row key/qualifier rather than forcing multiple events onto colliding timestamps.
- With `maxversions=1`, sending a cell with a **timestamp older** than the existing latest version may mean the newly sent record does not appear when reading only the latest version; **request arrival order does not determine version order**.

## 3. Cell Lifecycle: From Write to Compaction

~~~mermaid
flowchart TD
  A["Write setCell(timestamp, value)"] --> B["Cell becomes a readable version"]
  B --> C{"Matches GC policy?"}
  C -- "Not yet" --> D["Retained; may be latest or historical"]
  C -- "Yes" --> E["Eligible for deletion, NOT gone immediately"]
  E --> F["Background compaction / garbage collection"]
  F --> G["Cell physically removed, storage gradually drops"]
  E --> H["Read filter excludes cell from results before GC"]
  B --> I["Application delete mutation"]
  I --> J["Excluded from subsequent reads immediately"]
~~~

Bigtable GC runs **asynchronously** in the background during compaction on its own schedule; you cannot trigger GC immediately to save storage fees. Data past its age or version limit can still appear in reads and still accrue storage charges **until compaction removes it**. Typically this takes a few days, sometimes **up to a week**.

**Key distinction:** when an application sends a **delete mutation**, the deleted cell **is no longer visible on subsequent reads** per API semantics, even though physical cleanup may happen later. With a GC policy, the rule **does not** alter read results until the data is collected; you must use read filters.

| Action | Immediate read result | Physical space reclamation | When to use |
|---|---|---|---|
| Write a new version | Can read new version alongside older ones | Storage grows | Keeping change history |
| `maxversions=1` GC | Older versions **may still be readable** | After compaction | Automatic history cleanup |
| `maxage=7d` GC | An 8-day-old cell **may still be readable** | After compaction | Age-based retention |
| Read filter `cellsPerColumn(1)` | Returns only the latest version | **Does not delete** data | Enforcing query semantics |
| Application delete | No longer visible on subsequent reads | Physical cleanup later | Active business deletion |

**Never rely on GC alone to guarantee timely deletion for legal/security compliance**. Implement explicit deletion workflows, access-control checks, and dedicated verification/retention processes; note that backups/exports/replicas have their own lifecycles.

## 4. GC Policies Are Attached to Column Families

A Bigtable table can have multiple column families, and **each family has at most one GC policy expression** (which can be a compound expression). GC cannot be attached to an individual qualifier. Core policy types:

| Policy | Condition marking a cell for deletion | Interpretation |
|---|---|---|
| `maxage=7d` | Timestamp is **older than** 7 days | Age is evaluated from the cell timestamp |
| `maxversions=3` | Cell is **outside the 3 newest versions** of a column | Evaluated independently per row/qualifier |
| `maxage=7d or maxversions=3` | Satisfies **at least one** condition | Keep **at most 3 versions and none older than 7 days** |
| `maxage=7d and maxversions=3` | **Both** older than 7 days **and** outside the 3 newest versions | Keep at least 3 versions even when old; no hard TTL |
| Nested policy | Combines AND/OR groups | Use when complex rules have been tested |

**Easy rule of thumb:**

- **OR = deletes more broadly, keeps less**. Use when "no more than N versions **and** no older than T days" is a hard requirement.
- **AND = deletes more narrowly, keeps more**. Use when you want to keep **at least the N most recent versions**, even if they are older than T days.

### Illustration at Evaluation Time

Suppose a column has four cells ordered newest → oldest:

| Version | Age | Outside top 2? | Older than 7 days? | OR: GC'd? | AND: GC'd? |
|---|---:|---|---|---|---|
| v4 | 1 day | No | No | No | No |
| v3 | 9 days | No | Yes | **Yes** | No |
| v2 | 10 days | Yes | Yes | **Yes** | **Yes** |
| v1 | 12 days | Yes | Yes | **Yes** | **Yes** |

The difference stands out under **infrequent writes**: with just one version v1 aged 30 days, `maxage=7d or maxversions=2` marks it for **deletion**, while `maxage=7d and maxversions=2` **retains that single version**. Therefore, never write "AND caps data strictly at 7 days" in operational docs.

In the table above, **v3** is among the two newest versions even though it is 9 days old: **OR deletes v3**, whereas **AND keeps v3**. Conversely, a cell only 1 day old can still be removed by `maxversions` if enough newer versions are written during that window.

### Defaults Are Not Always the Same

Important migration detail:

- Column families created via **HBase Java client/HBase shell** typically default to keeping **1 version**, following HBase convention.
- Column families created via **`cbt`/gcloud or non-HBase clients** default to **keeping unlimited versions** unless a rule is set; there is **no default TTL**.
- Always verify the GC policy after creating a family instead of **trusting tool defaults**.

A new GC policy applies **retroactively** to existing data: tightening `maxversions` or `maxage` can remove older cells when compaction runs. Relaxing a policy **does not restore** data that has already been physically deleted.

## 5. Lab A — Creating Column Families and Inspecting Versions with cbt

This lab assumes an existing **Bigtable instance** with ID `bt-retention-lab`, the Google Cloud SDK, and the `cbt` tool. To control costs, **do not create a production cluster** just to test GC. For a new project, ask the platform team to provision an instance/cluster in the right region and edition.

### Setup and Table Creation

~~~bash
PROJECT_ID="my-bigtable-lab"
INSTANCE_ID="bt-retention-lab"
TABLE_ID="telemetry-gc-lab"
ROW="device#8a7f#lab"

# Assumes gcloud + cbt are installed and you are authorized.
gcloud config set project "$PROJECT_ID"
gcloud services enable bigtable.googleapis.com \
  bigtableadmin.googleapis.com

cbt -project="$PROJECT_ID" -instance="$INSTANCE_ID" createtable "$TABLE_ID"
cbt -project="$PROJECT_ID" -instance="$INSTANCE_ID" createfamily "$TABLE_ID" readings
cbt -project="$PROJECT_ID" -instance="$INSTANCE_ID" createfamily "$TABLE_ID" current
cbt -project="$PROJECT_ID" -instance="$INSTANCE_ID" ls "$TABLE_ID"
~~~

**Practical preflight:** verify the table/family does not exist yet, check cluster status, IAM, and backup/ownership before creating. `cbt` uses **Bigtable Admin API** permissions for schema/GC changes; if you only have data writer permissions without admin, creating a family fails with `PERMISSION_DENIED`.

### Writing Three Versions with Explicit Timestamps

Use the **current machine epoch time** in seconds converted to microseconds; timestamps 60 seconds apart are guaranteed distinct and valid on a MILLIS table:

~~~bash
# Run in Bash/Cloud Shell; date flags on other platforms may differ.
NOW_MICROS="$(($(date +%s) * 1000000))"
OLD_MICROS="$((NOW_MICROS - 120000000))"  # 2 minutes ago
MID_MICROS="$((NOW_MICROS - 60000000))"   # 1 minute ago

cbt -project="$PROJECT_ID" -instance="$INSTANCE_ID" set "$TABLE_ID" "$ROW" \
  "readings:temperature=21.2@$OLD_MICROS"
cbt -project="$PROJECT_ID" -instance="$INSTANCE_ID" set "$TABLE_ID" "$ROW" \
  "readings:temperature=21.9@$MID_MICROS"
cbt -project="$PROJECT_ID" -instance="$INSTANCE_ID" set "$TABLE_ID" "$ROW" \
  "readings:temperature=22.4@$NOW_MICROS" \
  "current:status=online@$NOW_MICROS"

# Read row: displays all versions currently stored.
cbt -project="$PROJECT_ID" -instance="$INSTANCE_ID" read "$TABLE_ID" \
  prefix="$ROW" count=1

# Read filter: returns only the 2 newest versions per qualifier.
cbt -project="$PROJECT_ID" -instance="$INSTANCE_ID" read "$TABLE_ID" \
  prefix="$ROW" count=1 cells-per-column=2
~~~

Before GC/compaction runs, `readings:temperature` holds three versions with distinct timestamps; the read with `cells-per-column=2` returns only `22.4` and `21.9`. The `current:status` column does not affect the version count of `readings:temperature`.

### Setting Per-Family GC Policies

~~~bash
# History: at most 7 days, at most 3 versions (OR).
cbt -project="$PROJECT_ID" -instance="$INSTANCE_ID" setgcpolicy \
  "$TABLE_ID" readings maxage=7d or maxversions=3

# Latest state: keep at most 1 version per qualifier.
cbt -project="$PROJECT_ID" -instance="$INSTANCE_ID" setgcpolicy \
  "$TABLE_ID" current maxversions=1

cbt -project="$PROJECT_ID" -instance="$INSTANCE_ID" ls "$TABLE_ID"
~~~

To switch `readings` semantics from **OR** to **AND** in an **isolated lab**:

~~~bash
cbt -project="$PROJECT_ID" -instance="$INSTANCE_ID" setgcpolicy \
  "$TABLE_ID" readings maxage=7d and maxversions=3
~~~

**Never toggle policies back and forth on live data to experiment:** policies apply retroactively. Before changing, inspect `cbt ls`, snapshot policy/backups per procedure, verify retention requirements, and test on a test dataset. On replicated instances, relaxing policies has extra constraints; do not blindly pass `force` just to silence warnings.

**Key expectation:** a successful `setgcpolicy` **does not immediately** cause unfiltered reads to return only N versions. In the example above, all three versions are within the limit of 3 and only 2 minutes old, so **no cells are eligible for deletion yet**; observing GC lag requires aged/excess test data in a test environment rather than waiting a few minutes.

## 6. Lab B — Java Writing and Reading with Consistent Filters

Example Java 17+ application with `com.google.cloud:google-cloud-bigtable` managed via the Google Cloud Libraries BOM. The class below uses **Application Default Credentials (ADC)** and a client supporting `RowMutation.setCell`, `Filters`, and `RowCell`.

**`GcCellLab.java`** (create inside a Java lab project configured with Maven/Gradle):

~~~java
import com.google.cloud.bigtable.data.v2.BigtableDataClient;
import com.google.cloud.bigtable.data.v2.models.Filters;
import com.google.cloud.bigtable.data.v2.models.Row;
import com.google.cloud.bigtable.data.v2.models.RowCell;
import com.google.cloud.bigtable.data.v2.models.RowMutation;
import com.google.cloud.bigtable.data.v2.models.TableId;
import java.time.Duration;
import java.time.Instant;

public final class GcCellLab {
    private static final Filters FILTERS = Filters.FILTERS;

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                "Usage: PROJECT_ID INSTANCE_ID TABLE_ID");
        }
        String project = args[0];
        String instance = args[1];
        String table = args[2];
        String rowKey = "device#8a7f#java";

        try (BigtableDataClient client =
                 BigtableDataClient.create(project, instance)) {

            // Bigtable timestamps are in micros; default tables use ms precision.
            long nowMicros = System.currentTimeMillis() * 1_000L;
            long minuteMicros = Duration.ofMinutes(1).toMillis() * 1_000L;

            RowMutation mutation = RowMutation.create(
                    TableId.of(table), rowKey)
                .setCell("readings", "temperature",
                         nowMicros - 2 * minuteMicros, "21.2")
                .setCell("readings", "temperature",
                         nowMicros - minuteMicros, "21.9")
                .setCell("readings", "temperature",
                         nowMicros, "22.4");
            client.mutateRow(mutation);

            // OR retention: 7 days + 3 versions:
            // 1) Exclude cells older than cutoff at read time.
            // 2) Keep only the 3 newest versions per column.
            long cutoff = Instant.now().minus(Duration.ofDays(7))
                .toEpochMilli() * 1_000L;

            Filters.Filter retentionFilter = FILTERS.chain()
                .filter(FILTERS.timestamp().range().startClosed(cutoff))
                .filter(FILTERS.limit().cellsPerColumn(3));

            Row row = client.readRow(
                TableId.of(table), rowKey, retentionFilter);
            if (row == null) {
                System.out.println("No matching cells");
                return;
            }
            for (RowCell cell : row.getCells()) {
                System.out.printf("%s:%s @%d = %s%n",
                    cell.getFamily(),
                    cell.getQualifier().toStringUtf8(),
                    cell.getTimestamp(), // epoch MICROSECONDS
                    cell.getValue().toStringUtf8());
            }
        }
    }
}
~~~

With the sample data, all three `readings:temperature` cells fall within 7 days and are returned in descending timestamp order. When a fourth version is added, `cellsPerColumn(3)` **immediately** returns only the 3 newest versions, even before Bigtable runs compaction to delete the fourth.

**Why does this chain match an OR policy?** For a cell to be valid, it must have `timestamp >= cutoff` **and** be within the top 3 versions. We chain **two inclusion filters** with AND, matching the deletion condition **age OR version**. For an **AND** GC policy, the read-filter logic differs: a cell must be kept if it is **not too old OR still in the top N**. Never apply an OR-retention filter to a requirement that says "always keep at least N versions."

Technical notes:

- The cutoff in the code is calculated at **read time** in epoch **microseconds**.
- `RowMutation.setCell(... timestamp, ...)` specifies an application-supplied timestamp; production typically lets the system assign the current timestamp unless event time is required.
- Reuse `BigtableDataClient` across a Java/Cloud Run/GKE app rather than creating a new client per HTTP request.
- Filtering at the Bigtable Data API prevents transferring unwanted versions to Java, but **does not reduce storage on its own**.
- Client code should not perform **Admin API policy updates**; data read/write permissions should stay separate from permissions to modify GC policies.

## 7. Business Timestamps, Backfills, and Common Mistakes

Writing correct data does not depend solely on GC rules. The **timestamp chosen by the application** governs cell age and version ordering:

| Situation | Risk | Mitigation |
|---|---|---|
| Writing a 30-day-old event into a family with `maxage=7d` | Cell becomes immediately eligible for deletion; 7-day read filter hides it | Use a separate backfill family/table, or manage retention by ingestion time |
| Producer clock runs 2 days ahead | Cell is retained longer than expected and can stick at the top as "latest" | Synchronize clocks, validate future timestamps and event-time skew |
| Two writes use the exact same timestamp for the same qualifier | Does not create two independent versions | Distinguish events in row key/qualifier, or ensure unique timestamps where needed |
| Passing Unix milliseconds into a field expecting micros | Cell is placed at an unintended historical date and may be GC'd | Standardize conversions and unit-test epoch math |
| Same `temperature` measurements arrive out of order | Latest version by timestamp is not the last arriving request | Read by event time or design explicit record identity/sequence |
| One family mixes 1-hour data and 1-year data | Cannot set different GC per qualifier | **Split column families** by retention class |

**Do not use Bigtable timestamps as an absolute version counter** if multiple writers update concurrently and business logic requires strict ordering; chosen timestamps can collide, drift, or arrive late. When unique event identity is needed, encode the event ID/sequence in the row key, qualifier, or value and enforce business rules at the application layer.

### When You Need "Keep Only the Latest Value, No History"

When only the current value matters, `maxversions=1` trims history over the long run, yet older versions **can still be read** before GC. To remove older versions immediately upon writing a new value, the application can send **delete-cells followed by set-cell in the same row mutation** per Bigtable's recommended pattern; verify concurrency, audit, and replica effects before adopting it. Specifically, **never use timestamp 0** as a shortcut to "overwrite a cell": under `maxage`, timestamp 0 is easily treated as expired.

## 8. Replication and Modifying GC Policies

Bigtable can host multiple clusters within one instance, with replication controlled by **app profiles** and application design. While GC policies belong to the table schema, **compaction timing is not synchronized across clusters**.

Warnings from current documentation:

- **Version-based GC** can generate deletions that must be **replicated across clusters**, raising CPU when lowering version limits or continuously writing excessive versions.
- **Age-based GC** expires cells independently on each cluster according to its own schedule; do not assume all clusters drop a cell at the exact same moment.
- Lowering `maxversions` on a replicated table can take **up to about a week** to synchronize deletions; read filters remain essential.
- When **increasing retention age** in a replicated instance, increase increments are bounded (current documentation states a maximum increase of **90 days at a time**) and clusters can temporarily hold differing data during transitions.
- **Age-based GC rules cannot always be removed outright** on replicated tables; review exact instance/API constraints and docs before modifying.

Tightening a GC policy **has no guaranteed data rollback**: cells removed by compaction will not reappear just because you revert the policy. Before changing a policy in production:

1. Inventory the family, current rule, mandatory retention period, data classification, and cluster replication topology.
2. Test on a synthetic-data table; verify exactly which versions **will be deleted under the new rule**.
3. Estimate impact on reads, CPU, replication backlog, and storage; verify properly protected backups/exports.
4. Review/approve the change, apply via IaC, and update **read filters simultaneously** with the retention contract.
5. Monitor storage size, read correctness, CPU, and errors for several days—not just a few minutes.

If you need to **extend retention**, update the rule **before critical data becomes eligible for deletion**, and preserve backups/exports for legal holds; relaxing retention cannot recover cells that are already gone.

## 9. Memorystore TTL/Eviction Is Not Bigtable GC

This chapter covers **Memorystore** as well, though the examples below use **Memorystore for Redis** without claiming identical configuration across every Redis Cluster or Valkey edition.

| Criterion | **Bigtable cell GC** | **Memorystore for Redis TTL/eviction** |
|---|---|---|
| Target | Cell versions in a **column family** | **Key** in Redis |
| Expiration mechanism | `maxage` based on cell timestamp | `EXPIRE`/`SET EX` based on key TTL |
| History limit | `maxversions=N` per qualifier | No built-in Bigtable-style version history |
| Query visibility | GC **does not immediately hide** eligible cells; requires read filters | Expired keys follow Redis semantics; do not treat TTL as instant RAM reclamation |
| Physical cleanup | Background Bigtable compaction, up to a week | Redis expiration and memory management |
| Eviction under memory pressure | No cache-style "evict least recently used version" | Supports **maxmemory policy** on keys when full |
| System role | Large-scale storage with history/timestamps | Cache, sessions, reconstructible ephemeral data |

Redis example in a **test network** (from a client authorized to reach the Memorystore endpoint):

~~~redis
SET cache:device:8a7f:temperature "22.4" EX 300
TTL cache:device:8a7f:temperature
GET cache:device:8a7f:temperature
DEL cache:device:8a7f:temperature
~~~

Here `EX 300` expires the key after **300 seconds**. In Memorystore for Redis, the default policy is commonly `volatile-lru`: when memory reaches capacity, Redis can evict **keys with a TTL** based on recent usage; a key may vanish before its TTL expires if memory pressure and policy permit. Under `noeviction`, writes can be rejected when full. Monitor `used memory`, `evicted keys`, `expired keys`, cache-hit ratio, and the maxmemory policy.

**Suitable architecture:** Bigtable retains 7 days of historical sensor readings; Memorystore caches **latest temperature** in Redis with a 5-minute TTL for fast dashboards. On cache miss, read Bigtable using retention-compliant filters and repopulate the cache. **Never use Memorystore as the sole copy of telemetry data required for reconciliation.**

## 10. IAM, Security, Monitoring, and Cost

### Separating Data Plane and Admin Plane Identities

| Identity | Responsibility | Reference least-privilege permissions |
|---|---|---|
| Java Cloud Run/GKE writer | Write `readings`/`current` cells | Appropriate Bigtable user/data writer; scoped to table and app |
| Java reader/dashboard | Read cells with filters | Bigtable reader or scoped authorized view |
| Platform/DB admin | Create tables/families, edit GC rules | Bigtable Admin API permissions, separated from runtime |
| Auditor/SRE | Inspect logs/metrics/policy metadata | Read permissions for Bigtable/Monitoring/Cloud Logging per policy |
| Memorystore consumer | Read/write cache | Network access and Redis AUTH/IAM depending on product type |

In Bigtable, IAM/API permissions and authorized views help narrow data exposure, **but Java read filters do not replace access control**: another client with table read permissions that omits the filter can still read GC-eligible data physically present on disk. If the goal is protecting PII past its deadline, implement explicit deletion and auditing workflows.

For Java clients using **ADC** on Cloud Run/GKE (e.g., Workload Identity Federation for GKE), never store JSON service account keys inside container images. Bigtable API access requires both networking/egress and IAM; blocking egress via NetworkPolicy/VPC causes client timeouts even with valid roles. Rely on the client library's TLS and prevent cross-project/cross-tenant unauthorized access.

### Metrics and Runbook

| Symptom | What to check |
|---|---|
| After `setgcpolicy`, reads still show 5 versions instead of 2 | Asynchronous GC; missing `cellsPerColumn(2)` in read query |
| Newly backfilled cell vanishes from filtered read | Cell timestamp is older than cutoff; policy uses event time |
| `INVALID_ARGUMENT` when writing timestamp | Micros not divisible by 1,000 on MILLIS table or invalid timestamp |
| Incorrect "latest" value | Clock skew, future timestamp, or late event stamped with old time |
| Unexpected GC behavior | Wrong column family, OR/AND mix-up, tool-specific family default |
| Storage size has not dropped yet | Compaction incomplete; still billed until physical removal |
| CPU/replication spikes after reducing versions | Version-based deletions and replication traffic |
| `PERMISSION_DENIED` when changing GC | Runtime SA only has data permissions, lacks Admin API policy permission |
| `RESOURCE_EXHAUSTED`/high latency | Large rows, overly wide scans, GC/update write load, CPU/network |
| Redis key evicted before TTL | Maxmemory policy/used memory—unrelated to Bigtable GC |

Monitor **Bigtable storage bytes**, CPU utilization, read/write latency, errors, Key Visualizer (row-key hotspots), table-level/cluster metrics, and **post-compaction storage cost**. GC reduces storage **with a delay**, and does not directly reduce read traffic if the application still scans full history without filters. For replicated instances, monitor clusters individually because CPU and compaction differ per cluster.

Total cost can include **Bigtable compute/cluster capacity, storage, backups, replication/network**, plus Cloud Run/GKE compute, Cloud Logging/Monitoring, and Memorystore memory if caching is used. Never budget as if "with 7-day GC, storage cost drops to zero at midnight on day 7"; eligible data remains billable until compaction completes.

## 11. Case Study: Temperature Telemetry and Dashboard

An IoT operations team manages **100,000 sensors**, each reporting temperature once per minute. The dashboard needs the latest reading quickly; behavioral analytics needs 7 days of detail; alerting only needs current status.

~~~mermaid
flowchart LR
  D["Devices"] --> I["Cloud Run / Pub/Sub ingest"]
  I --> B["Bigtable: readings (maxage=7d)"]
  I --> C["Bigtable: current (max 1 version)"]
  C --> M["Memorystore Redis TTL 5 min"]
  M --> API["Dashboard Java API"]
  B --> Q["Analytics / history inspection"]
~~~

**Design pitfall:** if the same qualifier `readings:temperature` is written **every minute** under `maxversions=3 or maxage=7d`, long-term storage only keeps the **last 3 minutes**, **not 7 days of detail**. That is a very common mistake when applying version-count GC limits to time-series data.

To genuinely retain 7 days of per-minute history, two options are better:

1. **One row per device/day, qualifier by timestamp or sample ID**, storing one cell per qualifier with `maxage=7d`; verify row size, timestamp/key design, and qualifier count limits.
2. **One row per device/time bucket**, sharing a qualifier across multiple versions, using only `maxage=7d` (or a `maxversions` bound sized from sampling frequency with headroom for bursts/backfills).

The `current` family keeps `maxversions=1`, and the Redis cache `EX 300` serves latest-value lookups. **Do not use Redis TTL to purge Bigtable history.** When the dashboard needs 7 days, query Bigtable with the business timestamp window and well-partitioned row keys to avoid full table scans.

Example calculation of versions needed for **1-minute intervals over 7 days** without sample loss:

~~~text
60 readings/hour × 24 hours × 7 days = 10,080 versions / column
~~~

Setting `maxversions=3` is clearly wrong if the goal is retaining full 7-day granularity. Evaluate row/key design, exact retention, read memory/CPU, and cost based on actual byte counts.

## 12. Checklist for Designing and Modifying Retention

- [ ] Defined whether retention is measured by **event time** or **ingestion time**.
- [ ] All producers write **epoch microsecond** timestamps matching table granularity, without confusing milliseconds.
- [ ] Evaluated late events, future timestamps, clock skew, and duplicate timestamps.
- [ ] Column families separated by **similar retention needs**, without expecting per-qualifier GC.
- [ ] Verified whether families were created via HBase or `cbt`/other clients and confirmed actual **default policies**.
- [ ] Tested **OR/AND** behavior against both sparse-version and high-version cases.
- [ ] Applications **always apply timestamp/version read filters** matching the data contract rather than waiting for physical GC.
- [ ] Data subject to legal deletion deadlines has explicit delete/audit workflows beyond GC.
- [ ] Policy changes have an owner, IaC review, backups/exports, canary testing, replication monitoring, and logic rollback plans.
- [ ] Understood that relaxing a GC rule **cannot recover** cells already removed by compaction.
- [ ] Tracked storage bytes, CPU, replication, read latency, and cost after changes.
- [ ] Never treated Redis TTL/eviction as a retention mechanism for Bigtable.
- [ ] Evaluated version counts from write frequency against row size, row-key distribution, and query patterns.
- [ ] Separated runtime IAM from Admin API policy permissions; no credential keys embedded in the Java app.

## 13. Practice Exercises and Knowledge Check

**Exercise 1 — Counting versions.** Row `device#1` has `readings:temperature` at timestamps T1/T2/T3/T4 and `readings:humidity` at T1/T2. With `maxversions=2`, how many cells are **retained per policy** for each qualifier? If you read immediately after changing the rule, why might more cells still be returned?

**Exercise 2 — Timestamp units.** Java passes `System.currentTimeMillis()` directly to a field expecting epoch microseconds. Explain how the timestamp is misinterpreted. Write the correct conversion and explain why a MILLIS table can reject a microsecond timestamp not divisible by 1,000.

**Exercise 3 — OR vs. AND.** A column has versions v4 (1 day), v3 (9 days), v2 (10 days), and v1 (12 days), ordered newest → oldest. Under `maxage=7d or maxversions=2`, which cells are marked for deletion? Under `maxage=7d and maxversions=2`, which cells are marked for deletion? Explain why AND keeps v3.

**Exercise 4 — cbt lab.** Create `telemetry-gc-lab` with families `readings` and `current`; write three timestamps and run `cbt read ... cells-per-column=2`. Then set `readings` to `maxage=7d or maxversions=3`. Why can unfiltered reads still return versions exceeding the rule right after setting the policy?

**Exercise 5 — Java read filters.** Starting from `GcCellLab`, update retention to **10 days and at most 2 versions**. Update the cutoff/filter and write a fourth cell. Explain the difference between the number of cells **returned** and **physically stored**.

**Exercise 6 — Late events/backfills.** A system ingests a Nov 1 data batch on Nov 19 while retaining only 7 days from cell timestamp. Propose two ways to keep the batch queryable for 7 days from ingestion without breaking event-time semantics.

**Exercise 7 — Replication migration.** A replicated table has a family with `maxversions=10`. The team lowers it to 2 and raises `maxage` from 30 to 120 days. List the constraints/warnings for replicated GC, CPU, retention expansion limits, observation windows, and how to plan safely before making the change.

**Exercise 8 — Real-world IoT.** 100,000 devices write 1 sample/minute for 7 days. Calculate samples/device over 7 days. Why is `maxversions=3` on the same qualifier wrong? Design suitable families/row keys and read filters while respecting row size limits.

**Exercise 9 — Bigtable with Memorystore.** A dashboard needs latest temperature within 5 minutes and 7 days of history. Decide where durable data vs. cache lives; write the Redis command `SET ... EX 300` and explain why a key can disappear before its TTL under memory pressure.

**Exercise 10 — Security and cost.** A developer claims: "GC is set to 30 days, so users cannot read a 31-day-old cell." Identify the flaw, and propose read filters, IAM/authorized views, active deletion when required, and dashboards tracking storage bytes and compaction timing.

## Official Reference Documentation

- [Bigtable garbage collection overview](https://cloud.google.com/bigtable/docs/garbage-collection) — background GC, client defaults, replication, and deletion timing.
- [Configure garbage collection](https://cloud.google.com/bigtable/docs/configuring-garbage-collection) — `maxage`, `maxversions`, `and`, `or`, nested rules, and `cbt`.
- [Bigtable data types and timestamps](https://cloud.google.com/bigtable/docs/data-types) — microseconds, millisecond granularity, and Enterprise Plus limits.
- [Bigtable writes](https://cloud.google.com/bigtable/docs/writes) — mutations, timestamp origin, and write timing.
- [cbt CLI reference](https://cloud.google.com/bigtable/docs/cbt-reference) — `set`, `read`, `setgcpolicy`, and reading policies.
- [Bigtable read filters](https://cloud.google.com/bigtable/docs/using-filters) — cells per column, timestamp ranges, chain filters.
- [Keep only the latest value](https://cloud.google.com/bigtable/docs/keep-only-latest-value) — delete-then-write and timestamp-0 warnings.
- [Java BigtableDataClient reference](https://cloud.google.com/java/docs/reference/google-cloud-bigtable/latest/com.google.cloud.bigtable.data.v2.BigtableDataClient) — read/filter operations.
- [Java RowMutation reference](https://cloud.google.com/java/docs/reference/google-cloud-bigtable/latest/com.google.cloud.bigtable.data.v2.models.RowMutation) — `setCell` and timestamps.
- [Bigtable IAM](https://cloud.google.com/bigtable/docs/access-control) — Data/Admin API permissions.
- [Bigtable performance and scaling](https://cloud.google.com/bigtable/docs/performance) — large rows, versions, and read design.
- [Bigtable pricing](https://cloud.google.com/bigtable/pricing) — compute, storage, replication, and networking.
- [Memorystore for Redis — memory management](https://cloud.google.com/memorystore/docs/redis/memory-management-best-practices) — expired/evicted keys and memory optimization.
- [Memorystore for Redis — supported configurations](https://cloud.google.com/memorystore/docs/redis/supported-redis-configurations) — maxmemory policies.
