# Monitoring Bigtable Performance with Key Visualizer

An online learning platform writes millions of learning-progress events to **Bigtable**. Google Cloud dashboards show cluster average CPU is not overly high, yet write p99 latency spikes sharply during peak hours. The root cause may not be a lack of total resources: row keys shaped like `2026-11-19#event-id` are pushing most new writes into **a single contiguous key range**. Adding nodes may not eliminate that hotspot.

**Key Visualizer** is Bigtable's observability tool for inspecting activity levels, latency, and warnings **across row-key ranges over time**. This lesson belongs to the **Bigtable and Memorystore** chapter of the **CLOUD_PROVIDERS_GCP** module: connecting VPC, Compute Engine/GKE/Cloud Run, storage, reliability monitoring, and cost into a workflow for pinpointing what slows down a Bigtable table. The subject here is **Bigtable Key Visualizer**, not Memorystore Redis monitoring.

After this lesson, you will be able to:

1. Read heatmaps along the time and key-range axes, understanding `key bucket`, colors, and data constraints.
2. Select the right metrics—`Ops`, `Read/Write pressure index`, `Latency`, `Large rows`—during investigations.
3. Distinguish hot rows/ranges, periodic access, sequential scans, and table-wide incidents.
4. Combine Key Visualizer with Monitoring, hot tablets, and client metrics to avoid misdiagnosis.
5. Propose row-key schema fixes, caching, filters, batching/deduplication, and verify them under representative load.
6. Execute a **read-only** lab and solve scenarios covering hotspots, availability, and cost.

## 1. Why Can Bigtable Run Hot on One Part of the Keyspace?

Bigtable stores data in a **row key → column family/qualifier → cells** layout; row keys are sorted **lexicographically by bytes**. Contiguous rows are managed in storage regions called **tablets**; the infrastructure distributes, moves, and splits tablets across nodes. This makes prefix-based range scans highly efficient while also creating the risk of **traffic concentrating on a small set of rows/ranges**.

~~~mermaid
flowchart TB
    A["Cloud Run / GKE app<br/>reading and writing Bigtable"] --> B["Row keys sorted<br/>in ascending byte order"]
    B --> T1["Tablet: A–F"]
    B --> T2["Tablet: G–N"]
    B --> T3["Tablet: O–Z"]
    T1 --> N1["Node 1"]
    T2 --> N2["Node 2"]
    T3 --> N3["Node 3"]
    KV["Key Visualizer"] -. "Observes usage<br/>by key buckets" .-> B
    MON["Cloud Monitoring"] -. "Observes CPU, latency,<br/>cluster/tablet" .-> N2
~~~

This is a **conceptual diagram**. A `tablet` is Bigtable's serving/storage unit; a `key bucket` is Key Visualizer's **display/statistics aggregation unit**. **Never equate** one bucket on the heatmap with one tablet or one node.

### 1.1. Three Bottlenecks Frequently Confused

| Symptom | Manifestation | Supporting tools |
| --- | --- | --- |
| **Entire cluster overloaded** | High CPU across many nodes, broad read/write latency increase | Cloud Monitoring cluster CPU, node count, request latency |
| **Hot row or hot range** | Specific key ranges show high read/write pressure despite lower average CPU | Key Visualizer, Hot tablets, hottest-node CPU |
| **Slow app/network** | Client p99 is high with no hot keys and stable server latency | Client metrics, gRPC retries, VPC/network, connection pools |

Do not assume every slow request requires changing the row key. If all ranges spike in latency simultaneously, investigate quotas, cluster CPU, networking, replica routing, or broad outages first.

### 1.2. Row-Key Anti-Patterns

~~~text
# Unsuitable for tables with heavy system-wide sequential INSERTs
2026-11-19T10:00:00.001Z#event-001
2026-11-19T10:00:00.002Z#event-002
2026-11-19T10:00:00.003Z#event-003

# Pattern to evaluate: place a high-cardinality identifier before the timestamp
student-a17#2026-11-19T10:00:00.001Z
student-b42#2026-11-19T10:00:00.002Z
student-c09#2026-11-19T10:00:00.003Z
~~~

In the first design, the leading timestamp strictly increases; new rows pile up at the tail of the keyspace. The second design distributes across students **if many students write concurrently**, while enabling prefix reads of a student's event stream. Yet if one student accounts for 80% of traffic, that prefix can still become a hotspot: always measure actual distribution.

## 2. What Does Key Visualizer Observe?

Key Visualizer generates a **heatmap**: the **X-axis is time**, the **Y-axis is row-key ranges**, and color represents the intensity of the selected metric. Darker colors represent lower values; brighter colors represent higher values **relative to the values currently displayed**.

Because Bigtable can hold vast numbers of row keys, Key Visualizer divides the keyspace into roughly **1,000 contiguous key buckets** (each holding approximately equal numbers of row keys) and displays appropriate aggregations. Under **Warnings** and **Performance**, the tool can provide finer detail on problematic keys or key ranges. Bucket boundaries adjust with data; never assume the same Y-coordinate across different scans always points to the exact same row.

### 2.1. Visibility Prerequisites and Permissions

- Per current Bigtable guidance, a table must hold **at least 1 GB of data per cluster** for Key Visualizer to render visual data; it can take **up to an hour** after crossing the threshold for data to appear.
- Select **the right table and cluster**: a Bigtable instance with multiple clusters can receive different traffic based on app profiles/replication.
- Viewers need appropriate Bigtable and Key Visualizer permissions, such as `bigtable.keyvisualizer.get` and `bigtable.keyvisualizer.list`. Apply least-privilege roles per policy—**never grant Bigtable Admin solely to view charts**.
- Key Visualizer can expose **row key prefixes/ranges**; if row keys contain emails, customer IDs, or PII, heatmap screenshots/tooltips are sensitive too. Share only with authorized personnel and redact contents before attaching to tickets.

**A table under 1 GB without scans does not imply healthy operation.** For small tables, use Cloud Monitoring, application metrics, hot tablets when supported, and load tests to investigate. Never inject synthetic production data solely to cross the threshold.

### 2.2. Key Buckets Are Not Raw Per-Row Data

| Misconception | Accurate understanding |
| --- | --- |
| "One bright stripe = one specific row" | Most heatmaps aggregate **a range of many rows**. Drill down into Warnings for details where available. |
| "One bright stripe = one Bigtable node" | Key ranges/buckets **do not** map fixed 1-to-1 to nodes. |
| "Yellow means an error" | `Ops`/Reads/Writes use relative coloring; check Warnings, latency, and actual impact. |
| "A dark chart means p99 is always low" | Network/client issues may exist, or data is unscanned/averaged out. |
| "Changing the time window keeps Y aligned to the same row" | Bucket boundaries can be recomputed; always verify the actual key range/tooltip. |

## 3. Core Metrics to Know When Investigating

| Group | Key Visualizer metric | How to use |
| --- | --- | --- |
| **Activity** | `Ops` | Approximate read + write activity, measured in **operations per row per minute**. Start investigations here. |
| **Warnings** | `Read pressure index` | Composite index based on read CPU/latency for a row/key range; **sustained ≥100** warrants investigation. |
| **Warnings** | `Write pressure index` | Equivalent for writes; sustained ≥100 may indicate hot writes or oversized rows. |
| **Warnings** | `Large rows` | Detects rows **>256 MB** or key ranges averaging **>200 MB/row**; review row design/data retention. |
| **Reads** | `Read CPU`, `Read bytes client` | Identifies which range consumes read compute or returns heavy bytes to clients. |
| **Writes** | `Write CPU`, `Write bytes client` | Identifies which range carries heavy write load or large write payloads. |
| **Performance** | `Latency`, `Latency (max)` | Correlates hotspots with processing latency on a row/key range. |
| **Size** | `Data stored`, `Rows` | Distribution of **compressed** storage size and approximate row counts per bucket. |

**Note on pressure index:** it is a **unitless composite index that does not convert to CPU%**. Do not write alerts like "read pressure 100 = 100% CPU." Values of **100 or higher** across multiple 15-minute intervals generally signal poor performance in that key range; apply duration criteria and verify latency and frequency rather than reacting to a single data point.

### 3.1. Combining Metrics Instead of Reading One Heatmap Alone

~~~text
Bright Ops at a prefix
  ├─ Bright Read CPU / Read bytes + high Read pressure
  │    -> Check excessive reads, broad scans/filters, huge rows, caching.
  ├─ Bright Write CPU / Write bytes + high Write pressure
  │    -> Check hot row/range, timestamp-leading keys, duplicate writes.
  ├─ Bright Large rows
  │    -> Check data piling into few rows, cell/version counts, GC.
  └─ Latency stays low, no Warnings
       -> High activity may be completely normal.
~~~

**Do not equate byte volume with operation count:** a handful of reads on huge rows can elevate `Read bytes client` without making `Ops` stand out. Conversely, massive numbers of tiny point lookups make `Ops` relatively brighter.

## 4. Reading Heatmaps by Pattern

Color patterns suggest hypotheses—they are **not automatic diagnoses**. Always cross-check the current metric, time window, row-key prefix, logs, and actual traffic.

| Heatmap pattern | Common hypothesis | Next check |
| --- | --- | --- |
| **Sustained bright horizontal band** at one key range | A row set receives heavy reads/writes or contains large rows | Read/Write pressure, Latency, Large rows; drill into key range |
| **Bright diagonal band** sweeping across key ranges over time | Sequential table scan or monotonically increasing key writes/reads | Query patterns, batch import timing, timestamp-leading schema |
| **Periodic bright/dark bands** | Scheduled batch jobs, reports, or hourly traffic waves | Align with Cloud Scheduler/Dataflow/ETL schedules and p99 |
| **Sudden brightening at one range** | A new job or consumer started hitting that range | Deploy timing, workload logs, query filters/prefixes |
| **Many ranges brighten together across an X slice** | System-wide burst, traffic surge, or broad incident | Cluster CPU, network, app profiles, client/server latency |
| **Evenly distributed fine-grained speckle** | Load spread reasonably evenly across keyspace | Verify latency/SLOs; no need to "fix" isolated bright pixels |

### 4.1. Horizontal Band: Hot Key Range or Valid Activity?

Suppose table `student-progress` has keys:

~~~text
course-001#student-0001
course-001#student-0002
course-001#student-0003
course-002#student-0001
...
~~~

During a new course launch hour, `course-001` receives most reads to display student rosters. Key Visualizer may show a bright horizontal band at this prefix.

**Diagnostic sequence:**

1. Open `Ops` to pinpoint the exact time and prefix with elevated activity.
2. Switch to `Read pressure index`, `Latency`, and `Read bytes client` on that exact region.
3. If pressure/latency remain healthy, the workload may be normal; monitor capacity and SLOs instead of rushing a schema change.
4. If heavy reads push p99 up, try **filters to trim bytes**, cache popular read results, or redesign key/range distribution. Never put transactional data requiring strict freshness into a cache without TTL/invalidation.

### 4.2. Diagonal Band: Is a Sequential Scan Always Wrong?

A backup/aggregation job scanning range by range over a long window can create a diagonal band. If the job is scheduled and CPU/latency remain within SLO, that is **expected behavior**. If instead it comes from writers inserting sequential `timestamp#eventId` keys with high **Write pressure**, it may be a **write hotspot**.

Distinguish them using **metrics, job schedules, read/write mix, and latency**. A diagonal shape alone does not prove the row key needs changing.

### 4.3. Vertical Band: An Incident Not Tied to One Prefix

If many key ranges experience elevated latency at the same time:

- Check cluster-wide CPU, node balancing, and how autoscaling is responding.
- Check app profile routing: did applications shift all requests onto a single cluster?
- Check client-side retries/deadlines, VPC/network health, and server connectivity.
- Check bulk imports/batch jobs or code changes hitting multiple prefixes.

Key Visualizer reflects only part of the performance picture. Never use it as a substitute for Cloud Monitoring or client traces.

## 5. Workflow for Opening Key Visualizer and Isolating Incidents

### 5.1. Before Opening: Lock Down the Scope

Record **project, Bigtable instance, cluster, table, app profile, incident window, SLOs, and granted permissions**. An instance with multiple clusters and distinct routing can mislead you if you compare cluster A's heatmap against client latency from apps mainly reading cluster B.

Authorized operators may use the Console or the following **read-only** commands to confirm resources (if supported by your CLI version):

~~~bash
# Read-only. Run after confirming the project is authorized.
gcloud config get-value project
gcloud bigtable instances list --project="YOUR_PROJECT_ID"

# If commands/flags differ in your SDK version, check --help.
gcloud bigtable instances describe "YOUR_INSTANCE_ID" \
  --project="YOUR_PROJECT_ID"
~~~

Do not paste full network details or resource names into public channels. Viewing Key Visualizer below is **read-only**—it requires no table creation, data writes, or node scaling.

### 5.2. Direct Steps in Google Cloud Console

1. Select **the right project**, then open **Bigtable → Instances**.
2. Select the target **instance**; in the left navigation, choose **Key Visualizer**.
3. Select the **table** and **cluster**, then click **Select**.
4. Choose the incident window via the **time-range sliders**, then click **Update**; Key Visualizer shows available scan intervals, not necessarily to the exact second selected.
5. Start at `Ops`. Record notable prefixes/ranges, start/end times, and whether the pattern repeats.
6. Switch to **Warnings**: `Read pressure index`, `Write pressure index`, `Large rows`. If an item is disabled, there may be no warnings of that type in the viewed window.
7. Compare **Read/Write CPU and bytes**, `Latency`/`Latency (max)`, then use **Multimetric** to view metrics side by side.
8. **Zoom/drill down** into the region; use tooltips/pins and the key hierarchy to inspect actual prefixes.
9. Document your hypothesis, p99 impact, proposed remediation, and before/after evidence. Never alter a row-key schema based solely on one bright color.

**Timing note:** heatmaps reflect scanned/computed intervals—**they are not a real-time per-request log**. A table that just crossed 1 GB may lack scans for up to roughly an hour. During an active live incident, start with Monitoring and logs first.

### 5.3. Combined Investigation Flow

~~~mermaid
flowchart TD
    INC["Alert: p99 / error rate rises"] --> FIX["Lock project, cluster,<br/>table, time window, SLO"]
    FIX --> OPS["Key Visualizer: Ops"]
    OPS --> WARN{"Warnings / Latency<br/>abnormal?"}
    WARN -->|Yes| DRILL["Zoom key range + tooltip;<br/>read Read/Write CPU & bytes"]
    WARN -->|No| OTHER["Check cluster CPU,<br/>client latency, network, quota"]
    DRILL --> CORR["Compare hot tablets, Monitoring,<br/>job/deploy timeline"]
    OTHER --> CORR
    CORR --> HYP["Pick hypothesis and<br/>test approved change"]
    HYP --> VERIFY["Measure before/after:<br/>p99, pressure, errors, cost"]
~~~

### 5.4. Least-Privilege Access and Protecting Key Information

- Viewing Key Visualizer requires appropriate permissions such as `bigtable.keyvisualizer.list` and `bigtable.keyvisualizer.get`, plus view permissions on the related instance/table; **check existing roles** before requesting new grants.
- Roles like Bigtable Reader/User may carry **data read permissions** broader than monitoring requires. In sensitive environments, consider a **custom role** per organizational policy instead of granting an overly broad role.
- Row keys may contain PII or customer info if legacy schemas placed emails/phone numbers in keys. Before attaching heatmap screenshots, **redact prefixes, project/instance IDs**, and sensitive tenant details.
- Never alter IAM, routing, autoscaling, GC, or schemas during **initial investigation**. Every change requires an owner, rollback plan, and success metrics.

## 6. Placing Key Visualizer Alongside Other Tools

| Tool | Perspective | When to use |
| --- | --- | --- |
| **Key Visualizer** | Activity/pressure/latency/size by **row-key range and time**. | Finding hot keyspaces, oversized rows, or hourly patterns. |
| **Cloud Monitoring cluster charts** | Average CPU and **hottest node**, node counts, throughput, latency, autoscaling. | Determining whether the cluster is overloaded or a single node is hot. |
| **Hot tablets** | Tablets consuming high CPU, tied to key ranges. | Isolating hot tablets and correlating with key prefixes. |
| **Client-side metrics** | End-to-end latency, app blocking, gRPC attempts/retries/deadlines. | Server looks healthy while users still experience slowness. |
| **Cloud Logging/application traces** | Request paths, jobs, batches, deploys, app errors over time. | Finding what triggered a burst or broad scan. |
| **Bigtable Access patterns/System insights** | Query types/load models and aggregate insights. | Adding context around Key Visualizer findings. |

For example, **hottest-node CPU much higher than average CPU** paired with `Write pressure index` concentrated on one row range strongly supports a hotspot hypothesis. Conversely, **very high CPU across all nodes** with many ranges rising together usually points to broader capacity or workload rate issues.

Note for **replicated Bigtable instances**: each cluster has independent capacity, read/write traffic per app profiles, and replication behavior. Compare both per-cluster latency/CPU and replication latency; Key Visualizer for **one cluster** does not reflect all actual traffic hitting other clusters.

## 7. Choosing Remediations by Root Cause

### 7.1. Hot Write Range from Sequential Row Keys

A hotspot-prone layout:

~~~text
20261119T100001Z#student-001#event-aaa
20261119T100002Z#student-002#event-bbb
20261119T100003Z#student-003#event-ccc
~~~

Because the leading timestamp strictly increases, writes pile onto one end of the keyspace. Options to **benchmark before migrating**:

| Design | When to consider | Trade-off |
| --- | --- | --- |
| `studentId#reverseTimestamp#eventId` | Many students write independently; need recent events **per student**. | A single ultra-active student can still run hot; not optimal for global latest events. |
| `shard#studentId#reverseTimestamp#eventId` | A few students are very hot; need to spread writes across shards. | Querying one student must read multiple shards and merge/sort; complicates migration and indexing. |
| `hash(eventId)#eventId` | Primarily point lookups by `eventId`, no time scans. | Time/user range queries require another table/materialized view. |

**Reverse timestamps** order newest events first within **each prefix**, but do not prevent hotspots on their own if a single prefix receives all writes. Better to combine **high-cardinality leading keys** aligned with access patterns.

Example generating a **16-shard row key** (Python illustration only; does not write to Bigtable):

~~~python
import hashlib

def make_row_key(student_id: str, event_id: str, epoch_ms: int) -> bytes:
    if not (0 <= epoch_ms <= 9_999_999_999_999):
        raise ValueError("timestamp out of supported range")
    digest = hashlib.sha256(event_id.encode("utf-8")).digest()
    shard = int.from_bytes(digest[:4], "big") % 16
    reverse_ms = 9_999_999_999_999 - epoch_ms
    # Avoid emails/PII in keys; student_id is a controlled opaque ID.
    return f"{shard:02d}#{student_id}#{reverse_ms:013d}#{event_id}".encode()
~~~

This spreads prefixes more evenly **if event IDs carry sufficient entropy**. Splitting into 16 buckets **does not guarantee balance** if the app generates skewed event IDs or uneven traffic; load-test and measure. Reading all events for one student requires querying every shard prefix for that student and merging by timestamp. Adding shards **does not automatically migrate legacy data** to the new schema.

### 7.2. Hot Read Range from Overly Popular Data

For instance, 70% of requests read progress for one classroom. When both `Read pressure index` and latency rise on that prefix:

1. Measure **request rate to the same key/range** and returned payload size.
2. Narrow **row-range scans** and apply **filters** so unneeded columns/versions are not returned.
3. Cache frequently read, infrequently changing data (e.g., course metadata) in **Memorystore (Redis)** or another cache layer with TTL/invalidation and sensitivity controls.
4. If a single row is read excessively, consider **splitting content** or maintaining managed read replicas suited to access patterns, accepting consistency and update-cost trade-offs.
5. If cluster-wide capacity is also constrained, scale nodes/autoscaling per plan—but never use node scaling to ignore a hot row.

**Memorystore does not replace Bigtable as the primary datastore in every case**: caches can expire, lose state, or evict keys depending on configuration. Critical learning-progress data requires durable storage and an explicit invalidation strategy.

### 7.3. Large Rows: Avoid Accumulating Excessive Cells/Versions

Key Visualizer flags `Large rows` when a single row exceeds **256 MB** or a range averages over **200 MB/row**. Bigtable recommends avoiding rows >256 MB as they degrade performance and readability.

For example, row `student-42` accumulates **years of progress history** and millions of cell versions. Even partial reads may have to process the huge row. Design remedies:

- Split data into **multiple rows by day/month/course** while keeping prefixes aligned with queries.
- Set **garbage collection policies** by version count or age to cap accumulation; understand GC does not necessarily delete instantly or reclaim all space in seconds.
- Offload large blobs to Cloud Storage, keeping only lookup metadata/indexes in Bigtable.
- Try filters to reduce returned bytes, keeping in mind **filters do not shrink an already oversized row**.

Never bulk-delete production data immediately upon seeing a warning. Verify retention, backups, recoverability, and downstream consumers relying on older data.

### 7.4. Duplicate or Overly Frequent Writes

A batch job might rewrite unchanged state repeatedly or replay entire writes after timeouts. Mitigations:

- Batch writes appropriately on the client, bound concurrency, and apply backoff retries.
- **Deduplicate** by event/business key before constructing mutations where business logic permits.
- Enforce idempotency for side effects; avoid creating new qualifiers/versions from uncontrolled retries.
- Measure **actual write volume, retries, latency, and conflicts**; never assume batching always reduces stored bytes.

### 7.5. When Should You Add Nodes?

If CPU is high across many nodes, throughput consistently exceeds cluster capacity, and access patterns are reasonably balanced, adding nodes or enabling autoscaling improves serving capacity. However, for a **hot single row/tablet** absorbing a huge share of load, adding total nodes yields limited relief; fix the access pattern/row keys.

Adding nodes incurs **cost**, and autoscaling does not guarantee instant protection against sudden traffic spikes. Every capacity change must be weighed against SLOs, quotas, product limits, and budget.

## 8. First 15–30 Minute Runbook for a Latency Incident

The runbook below covers **investigation only**. Changes to schemas, node counts, or caches must go through change review.

| Step | Action | Evidence to record |
| --- | --- | --- |
| 1 | Confirm **symptoms** in the application: p95/p99, deadline exceeded, failed request count. | Request ID/trace, time window, service/region. |
| 2 | Select the exact **project–instance–cluster–table** and app profile. | Cluster route, time window, pre-incident baseline. |
| 3 | Check **average CPU and hottest node** in Monitoring; check hot tablets if needed. | Whole cluster or only a few hot ranges/nodes? |
| 4 | In Key Visualizer: `Ops` → Warnings → `Latency` → read/write CPU/bytes. | Key ranges, timestamps, abnormal metrics. |
| 5 | Correlate with **deploys, ETL jobs, query logs/client metrics** at the same time. | Who generated the load, read/write mix, payload/scan size. |
| 6 | Pick **one primary hypothesis** and a low-risk action: trim scans, cache, throttle batch overload. | Owner, approval, rollout/rollback, and expected impact. |
| 7 | Compare post-change results in Monitoring and the next scan. | p99, error rate, pressure duration, bytes/ops, cost. |

**Example of a sound conclusion:** "From 10:00–10:30, `student-42#...` showed `Read pressure index >100` alongside elevated read p99; simultaneously 80% of reporting requests hit this prefix. Test TTL caching and narrower scans, then re-measure." Never write "Key Visualizer shows Bigtable is broken" without proving causality.

### 8.1. When Key Visualizer Has No Scan or Shows No Warnings

| Observation | Likely explanation | Next step |
| --- | --- | --- |
| Table cannot be selected | Below 1 GB **per cluster** or insufficient processing time; wrong permissions/scope | Check storage/cluster/permissions and Monitoring; never load fake data just to trigger scans |
| `Warnings` disabled | No warnings of that category in the viewed window | Check `Ops`, `Latency`, Monitoring, and client errors |
| All keys look uniformly dark or bright | Relative color scale/brightness or low contrast | Read tooltips and absolute values; switch metrics/brightness |
| "Key space not to scale" | Key distribution is uneven for clean bucket splitting | Do not treat as a storage error; cross-check Monitoring/hot tablets |
| "Values per row are approximate" | Rapidly changing table/data skews estimates | Cross-check other metrics and newer scan intervals |
| Bright colors but no errors | High load still within capacity | Verify SLOs; do not change schemas needlessly |

During an **active incident**, do not wait for Key Visualizer to update before starting triage; use Monitoring, client logs, and node/tablet telemetry with shorter reporting latency.

## 9. Read-Only Observation Lab: Investigating a Hot Key Range

**Goal:** use an **existing** Bigtable table to complete a Key Visualizer diagnostic sheet; **do not** create instances, modify autoscaling, insert data, or delete tables. If you lack access or the table is below the display threshold, complete the **paper lab** in Section 9.3.

### 9.1. Prerequisites and Setup

Obtain owner approval to inspect a **Bigtable instance, table, and cluster** with appropriate Key Visualizer/Monitoring read permissions. In production, observe only; learners must never alter configurations or inject test traffic.

In your lab worksheet, record:

~~~text
Project:        <approved>
Instance:       <approved>
Cluster:        <approved>
Table:          <approved>
App profile:    <if applicable>
Time window:    <incident time or representative window>
Read/write SLO: <agreed p95/p99 and error budget>
~~~

For eligible tables, go to Google Cloud Console → **Bigtable → Instances → select instance → Key Visualizer → select table/cluster**. Set the time-range slider to cover the target event. Never download or share raw row keys if they contain sensitive IDs.

### 9.2. Collecting Evidence in Sequence

| Console step | Question to answer | Notes |
| --- | --- | --- |
| **Ops** | Which range/prefix is noticeably brighter and at what hours? | Record only anonymized prefixes and time windows. |
| **Read pressure** | Is there a sustained ≥100 warning on that exact range? | If none, record "no warning observed." |
| **Write pressure** | Is there localized hot write activity? | Compare against deploy/ETL timeline. |
| **Large rows** | Any row >256 MB or oversized range? | Never query whole rows to verify in production. |
| **Latency** | Does the high-pressure region show elevated latency at the same time? | Compare against app p95/p99. |
| **Read/Write CPU, bytes** | Is the bottleneck driven mainly by request count or large payloads? | Classify before altering schemas. |
| **Monitoring/hot tablets** | Is a node/tablet overloaded, or is the entire cluster saturated? | Record average CPU vs. hottest node. |

**Short investigation report template:**

~~~text
Symptom: read p99 climbed from [baseline] to [observed] at [time].
Scope: [instance/cluster/table]; request path [redacted].
Key Visualizer: abnormal [metric] at prefix [masked-prefix].
Corroboration: [Monitoring/hot tablets/client logs] at the same window.
Hypothesis: [hot read / hot write / large row / unrelated to keyspace].
Proposed action: [single change, owner, rollback plan].
Verification criteria: p99 < [SLO], error rate < [SLO],
                       pressure improves, cost stays within budget.
~~~

If Ops is bright without pressure warnings, the right answer may be **"insufficient evidence of an SLO-impacting hotspot"**—do not force-fit a bug to fix.

### 9.3. Paper Lab When No Eligible Bigtable Is Available

Inspect the **hypothetical dataset** below. All keys are anonymized and numbers are strictly for analysis practice—**they are not real Google Cloud metrics or screenshots**.

| Key range | Relative Ops | Read pressure | Write pressure | Relative p99 latency | Large rows |
| --- | ---: | ---: | ---: | --- | --- |
| `00#student-*` | 35 | 12 | 22 | Low | No |
| `01#student-*` | 420 | **125** | 34 | **High** | No |
| `02#student-*` | 60 | 10 | 18 | Low | No |
| `03#student-*` | 70 | 16 | **140** | **High** | No |
| `04#student-*` | 8 | 7 | 9 | Low | **Yes** |

**Questions:**

1. Which range is suspected of hot reads? — `01#student-*`, due to Read pressure ≥100 paired with high latency.
2. Which range is suspected of hot writes? — `03#student-*`, due to Write pressure ≥100 paired with high latency.
3. Which range needs a row-size check? — `04#student-*`, despite low Ops.
4. Should you add nodes immediately? — **Insufficient data**; inspect per-node/tablet CPU, request patterns, and abnormal row sizes before deciding.
5. Why not conclude `00#student-*` has a bug? — Relative Ops is not an error; pressure and latency show no issue.

Based on these results, propose **three independent experiments**: caching/filtering for the hot read range; removing timestamp-leading/hot writes for the hot write range; splitting rows or adjusting retention for large rows. Measure each change against baseline; never apply all simultaneously if you want to isolate what caused the improvement.

## 10. Design Scenarios and Exercises

### Scenario A — Leading Timestamp, Rising Write p99

A Pub/Sub → Dataflow → Bigtable pipeline writes `rowKey=YYYYMMDDHHmmss#eventId`. At 6,000 events/s peak, cluster-wide average CPU is ~40%, yet hottest-node CPU nears saturation and Key Visualizer shows a diagonal band with high Write pressure.

**Task:** provide a diagnosis, key redesign, and two verification methods.

**Solution guide:** suspect a timestamp-leading hotspot. Consider leading with a high-cardinality ID (user/device) if queries are ID-based, or adding a shard prefix derived from event ID when needed. Verify via **Key Visualizer pressure/hot tablets** and **write p99/hottest-node CPU** under representative load. Plan migration/backfill and update query/read paths.

### Scenario B — One Course Experiences a Read Spike

The platform publishes exam results; 80% of GET requests read the same prefix `course-top-42#...`, read latency climbs, and writes remain normal.

**Task:** should you convert all row keys to random UUIDs?

**Solution guide:** do not blindly rewrite the whole table. Measure `Read pressure`, `Read bytes client`, and row sizes; consider valid caching (e.g., Memorystore for published course metadata/summary scores), filters, splitting oversized rows, or managed read copies. Random UUIDs across all rows destroy course-level query locality.

### Scenario C — Large Row with Low Request Volume

A row accumulates years of learning-state versions, reaching ~300 MB compressed. `Ops` is unremarkable, yet `Large rows` triggers and reads occasionally fail.

**Task:** list two remedies and their risks.

**Solution guide:** split history across multiple rows by day/month/course; configure GC policies/retention per requirements, or move large blobs to Cloud Storage. Requires data migration, dual-reads during transition, backups, and validation against data loss. Adding nodes will not shrink a single oversized row.

### Scenario D — White Heatmap, Healthy SLOs

A nightly analytics job sequentially scans part of a table, producing a very bright diagonal band. `Read/Write pressure` shows no warnings and client p99 stays within SLO.

**Task:** is this an incident and what should you do?

**Solution guide:** not necessarily. Correlate with the job schedule, verify quotas/cost/capacity, and check impact on other workloads. Leave as-is, or adjust scheduling/smaller batches if cost or latency rises later. **Relative brightness alone is not an actionable alert**.

### Scenario E — No Scan Visible in Console

A new Bigtable table holds 200 MB/cluster and a team wants to "test Key Visualizer" by pumping 800 MB of dummy data into production.

**Task:** should they do this? Propose a safer path.

**Solution guide:** **no**. The tool requires at least 1 GB per cluster for scans, but loading arbitrary dummy data incurs fees, pollutes data, and risks impacting live systems. Use Cloud Monitoring/hot tablets/client metrics or paper exercises; if a real benchmark is needed, provision a separate **approved test project/instance and budget**.

### Quantitative Exercise: Understanding Load Skew

In one minute, a table handles 2 million operations: 1.2 million hit **one prefix**, while 0.8 million spread across many prefixes.

1. What percentage of operations hits the hot prefix? **60%**.
2. Can `60% Ops` alone prove latency must be high? **No**; cross-check pressure, latency, and actual serving capacity.
3. If those are 60% **reads** and a valid cache reduces Bigtable requests **within the hot prefix** by 50%, how many requests are avoided? **600,000/minute** in this hypothetical model, excluding cache misses/invalidation.
4. Why not use that model directly as an exact cost forecast? — Real cache hit rates, traffic dynamics, request sizes, and pricing/capacity structures vary.

## 11. Checklist for Long-Term Monitoring

| Requirement | Acceptance criterion |
| --- | --- |
| **Baseline** | Read/write p95/p99 SLOs, CPU, hottest node, throughput, and cost measured pre-incident. |
| **Drill-down workflow** | On-call engineers know how to select project/instance/cluster/table, time window, metrics, and prefixes. |
| **Corroborating sources** | Monitoring, client metrics, hot tablets, and deploy/job timelines are available. |
| **Appropriate alerts** | Alerts trigger on real p99/errors/CPU; Key Visualizer is used for root-cause investigation. |
| **Schema reviews** | Row keys checked for timestamp/sequence prefixes, hot entities, or oversized rows. |
| **Safe changes** | Never modify production from a heatmap alone; require owner, approval, benchmark, and rollback. |
| **Security** | Grant only viewing permissions; redact heatmap screenshots/key prefixes if PII is present. |
| **TCO** | Evaluate node costs, reads/writes, replication, caches, storage/GC, and migration costs. |

### Self-Check

1. **How does Key Visualizer differ from Monitoring cluster CPU?** — It breaks down activity by **key ranges**, whereas Monitoring provides broader infrastructure/latency views.
2. **What are the X/Y axes of the heatmap?** — X: time; Y: row-key ranges.
3. **Does one key bucket equal one tablet?** — No; a bucket is a statistical display unit.
4. **Does white `Ops` always mean an error?** — No; colors are relative—check Warnings and SLOs.
5. **What does sustained Read/Write pressure ≥100 mean?** — A signal of potential poor performance in that row/range requiring investigation.
6. **When does `Large rows` trigger?** — Rows >256 MB or key ranges averaging >200 MB/row.
7. **Why are scans missing on small tables?** — Requires at least 1 GB of data **per cluster**, plus processing time.
8. **What risk do leading timestamps in row keys carry?** — Sequential writes concentrate in one key region.
9. **Does adding nodes automatically fix every hotspot?** — No; hot rows/ranges may require schema/access changes.
10. **What must you do before sharing heatmap screenshots?** — Inspect and redact row-key prefixes, projects, and sensitive data.

## 12. Official Documentation

- [Bigtable — Overview of Key Visualizer](https://cloud.google.com/bigtable/docs/keyvis-overview): heatmaps, key ranges, and tool limitations.
- [Bigtable — Use Key Visualizer](https://cloud.google.com/bigtable/docs/keyvis-getting-started): 1 GB/cluster requirement, UI, time windows, and inspecting warnings.
- [Bigtable — Key Visualizer metrics](https://cloud.google.com/bigtable/docs/keyvis-metrics): Ops, pressure indexes, latency, size, and key buckets.
- [Bigtable — Heatmap patterns](https://cloud.google.com/bigtable/docs/keyvis-patterns): horizontal bands, periodic access, diagonal bands, and bursts.
- [Bigtable — Explore heatmaps](https://cloud.google.com/bigtable/docs/keyvis-exploring-heatmaps): zooming, multimetric views, tooltips, and key formatting.
- [Bigtable — Diagnostic messages](https://cloud.google.com/bigtable/docs/keyvis-diagnostics): warnings, approximate values, and scan limitations.
- [Bigtable — Hot tablets](https://cloud.google.com/bigtable/docs/hot-tablets): isolating hot tablets and node CPU.
- [Bigtable — Schema design best practices](https://cloud.google.com/bigtable/docs/schema-design): row-key distribution, time-based rows, and hotspot mitigation.
- [Bigtable — Monitoring](https://cloud.google.com/bigtable/docs/monitoring-instance): cluster/system insights and infrastructure-level observability.
- [Bigtable — Troubleshoot latency](https://cloud.google.com/bigtable/docs/latency): distinguishing node overutilization, hotspots, and client-side latency.
- [Bigtable — IAM roles and permissions](https://cloud.google.com/iam/docs/roles-permissions/bigtable): least-privilege permissions for viewing data/Key Visualizer.
- [Bigtable — Pricing](https://cloud.google.com/bigtable/pricing): evaluating node, replication, and storage costs over time.

**Conclusion:** Key Visualizer answers **"which row keys and time windows concentrate latency and load?"** Read `Ops` to locate activity, verify with **Read/Write pressure, Latency, and Large rows**, and cross-check **Monitoring, hot tablets, and client metrics**. The ultimate goal is not making the heatmap dark, but maintaining **SLOs, balanced load distribution, accurate data, and budgeted costs** through measured, reversible schema and caching changes.
