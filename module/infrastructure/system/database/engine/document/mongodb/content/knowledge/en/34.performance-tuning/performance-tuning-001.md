# Building Representative Load Tests and Measurement Criteria for p50, p95, and p99 in MongoDB

## 1. Why Does a Fast Single Query Not Prove the Database Is Fast Enough?

A rental housing application uses MongoDB to manage listings, users, appointments, and transaction activity. A developer opens `mongosh` and runs:

~~~javascript
db.listings.find({ status: "active" }).limit(20);
~~~

The query returns results in a few milliseconds. The team concludes that MongoDB is already optimized. However, during peak hours, users experience search pages taking several seconds, some requests time out, and database CPU spikes.

The difference comes from **non-representative load testing**:

- Production has **millions of documents**, not a few hundred sample records.
- There are multiple query patterns: searching listings by city/price, viewing details, aggregations, and updating statuses.
- Many users send requests **concurrently**.
- Some tenants/cities receive significantly more traffic than the rest.
- Warm/cold cache states change cache hit ratios and disk I/O.
- Indexes benefit reads but increase write overhead.
- Network, TLS, connection pools, replication, and write concern can all increase latency.
- Slow requests in the tail of the distribution may barely affect the average but severely degrade user experience.

Therefore, the right question is not:

> "How many milliseconds does MongoDB take to run this one query?"

But rather:

> "With production-like data, read/write ratio, query distribution, concurrency, and request rate, does MongoDB meet the **SLOs for latency, throughput, and errors**, including p95/p99, over the required duration?"

### Learning Objectives

After this lesson, you will be able to:

1. Define a **workload profile** from real traffic and queries.
2. Design a test dataset that approximates production in **volume, cardinality, distribution, selectivity, and document size**.
3. Distinguish between **offered load, achieved throughput, concurrency, utilization, service time, queueing time, and response time**.
4. Distinguish between **closed-loop** and **open-loop load generation**; understand **coordinated omission**.
5. Compute and interpret **p50, p95, and p99** using a documented percentile method.
6. Define **SLIs/SLOs** per query type and for the overall system.
7. Run a MongoDB lab with deterministic data, query shapes, and intentional indexes.
8. Read **explain("executionStats")**, driver metrics, server metrics, and infrastructure metrics to analyze bottlenecks.
9. Build a basic Node.js benchmark that separates warmup from measurement and records errors and timeouts.
10. Make optimization decisions **based on latency distributions and representativeness**, rather than a single best execution time.

> **Scope:** This lesson belongs to **Database Engine Document MongoDB → Performance Tuning**. All seed commands use only the **mongo_perf_lab_362** database with dedicated IDs prefixed with **b362-**. The benchmark defaults to **read-only** with bounded concurrency; write mode is used only on the lab's dedicated counters when explicitly enabled. **Do not generate load tests directly against production** without a plan, limits, approval, and rollback strategy.

## 2. Quantities to Measure

### 2.1. Response Time and Latency

From the user's perspective, API response time can consist of:

~~~text
Request arrives at API
    |
    +--> Queueing at load balancer/server
    +--> Authentication and business logic processing
    +--> Waiting for a connection from the driver pool
    +--> DNS/TLS/network to MongoDB
    +--> Waiting/queueing at the database
    +--> Query/index scan execution
    +--> Network returning documents
    +--> Response serialization
    |
    v
Response to client
~~~

Meanwhile, `explain`'s **executionTimeMillis** reflects only part of the database-side execution time under the explain mechanism. It is **not equivalent** to the API latency seen by the client.

When reporting latency, always specify **where it was measured**:

- **End-to-end API latency:** from when the client sends the request until the full response is received.
- **Driver operation latency:** from when the application invokes the driver until the Promise resolves, typically including pool wait/network/server/deserialization.
- **MongoDB command duration:** measured via driver command monitoring; scope depends on the event/driver.
- **Server query execution:** metrics from explain/profiler, excluding all time outside the server.

Do not compare API p99 with explain p99 and call them the same SLI.

### 2.2. Throughput

**Throughput** is the number of operations completed per unit of time:

\[
\text{Throughput} = \frac{\text{Number of successfully completed operations}}{\text{Observation duration}}
\]

For example: 12,000 operations completed successfully in 60 seconds corresponds to **200 successful operations/second**.

If 13,000 requests are sent, 12,000 succeed, and 1,000 fail, the report must include all of:

- **Offered load:** number of requests sent/offered to the system.
- **Successful throughput:** number of successful requests per unit time.
- **Error/timeout rate:** rate of unsuccessful requests.

Do not claim the system achieves a healthy 216 RPS simply because 13,000 requests were **sent** in 60 seconds.

### 2.3. Offered Load and Achieved Load

~~~text
Load generator attempts to send 500 requests/s
       |
       v
Server only completes 300 requests/s
       |
       +--> Queue grows
       +--> Timeouts begin appearing
       +--> p95/p99 increase
~~~

In this case:

- **Offered rate:** 500 RPS.
- **Achieved success rate:** approximately 300 RPS.
- **Gap:** may be queue backlog, errors, throttling, or load generator limits.

Measuring both is required to distinguish between **the database failing to keep up with load** and **the load generator failing to generate enough load**.

### 2.4. Concurrency

Concurrency is the number of tasks active/awaiting completion at the same time. It is **not synonymous** with throughput.

For example, a closed-loop client has 10 workers, where each worker sends a new request immediately after the previous one completes:

- Average latency 50 ms: ideally around 200 requests/s (ignoring overhead).
- Average latency 200 ms: drops to around 50 requests/s if still using 10 workers.

When the server slows down, **closed-loop load generation automatically reduces offered throughput**, which can mask a peak-hour crisis.

### 2.5. Little's Law

Under appropriate steady-state system conditions, the approximate relationship is:

\[
L = \lambda W
\]

Where:

- **L:** average number of requests in the system.
- **λ:** average throughput / arrival rate.
- **W:** average time a request spends in the system.

For example, **200 req/s × 0.1 s = 20 requests** present on average. This is a tool for reasoning about capacity and queueing, not a license to derive p99 from average latency.

### 2.6. Utilization and Saturation

60% CPU does not necessarily mean MongoDB has 40% useful capacity remaining. A bottleneck may lie in:

- A single CPU core or a sequential stage.
- Disk latency / IOPS / throughput.
- WiredTiger cache pressure.
- Network bandwidth.
- Connection pool wait.
- Locks/tickets/admission control.
- Replica set majority/journal wait.
- A hot shard or tenant hot spot.

**Saturation** is the state where additional load causes queueing/latency or error rate to rise rapidly, while increasing offered traffic no longer yields a proportional increase in successful throughput.

## 3. What Are p50, p95, and p99?

### 3.1. Percentile Concept

Given N latency observations:

- **p50:** roughly 50% of operations have latency not exceeding this threshold according to the percentile method.
- **p95:** roughly 95% of operations have latency not exceeding this threshold; the remaining tail is roughly 5%.
- **p99:** roughly 99% of operations do not exceed this threshold; the remaining tail is roughly 1%.

**p99 is not the maximum latency.** There are still requests above p99, sometimes very slow ones. A percentile is a threshold in an observed distribution, not a per-request guarantee.

### 3.2. Intuitive Example

Suppose 100 operations are sorted in ascending order of latency. Using **nearest-rank**:

- p50 is the **50th** observation.
- p95 is the **95th** observation.
- p99 is the **99th** observation.

If 95 operations finish in at most 80 ms, the next four take 300–500 ms, and the last one takes 2,000 ms, **p95 can still be 80 ms**, while p99 will reflect the slower tail.

### 3.3. Why Can the Average Be Misleading?

Suppose:

~~~text
99 requests: 20 ms
 1 request:  2,000 ms
~~~

Mean:

\[
\frac{99\times20+2000}{100}=39.8\text{ ms}
\]

A mean of around **39.8 ms** sounds good, yet one user waited **2 seconds**. In an application making many requests per session, slow tail requests can occur frequently in the overall user experience.

Therefore, track at least **p50, p95, p99, throughput, and error rate**; in special scenarios, also track max/p99.9 or tail timeouts.

### 3.4. Percentiles Have Multiple Statistical Definitions

There is no single percentile interpolation formula used by all libraries. Two different measurement systems may return slightly different values on the same list, especially with small sample counts.

This lab uses **nearest-rank**:

1. Sort the N latencies in ascending order.
2. Compute rank **ceil(p × N)** for p between 0 and 1.
3. Take the element at that 1-based position.

\[
P_p=x_{(\lceil pN\rceil)}
\]

With N=20: p50 is the 10th observation, p95 is the 19th, and p99 is the 20th. Thus **p99 equals the max when there are only 20 samples**. This shows that p99 on too small a set is highly unstable.

### 3.5. Percentile Function in JavaScript

~~~javascript
function percentileNearestRank(values, p) {
  if (!Array.isArray(values) || values.length === 0) {
    return null;
  }
  if (p < 0 || p > 1) {
    throw new Error("p must be in [0, 1]");
  }
  if (!values.every(v => Number.isFinite(v) && v >= 0)) {
    throw new Error("Latency must be a finite non-negative number");
  }

  const sorted = [...values].sort((a, b) => a - b);
  const rank = Math.max(1, Math.ceil(p * sorted.length));
  return sorted[rank - 1];
}

const latenciesMs = [
  18, 23, 21, 20, 19, 24, 22, 26, 27, 25,
  29, 31, 28, 30, 32, 35, 34, 40, 120, 600
];

printjson({
  p50: percentileNearestRank(latenciesMs, 0.50),
  p95: percentileNearestRank(latenciesMs, 0.95),
  p99: percentileNearestRank(latenciesMs, 0.99)
});
~~~

Results using nearest-rank:

~~~text
p50 = 27 ms
p95 = 120 ms
p99 = 600 ms
~~~

Here there are only **20 samples**. Never use a p99 computed from 20 requests to promise a production SLO.

### 3.6. Why Are Many Samples Needed?

With nearest-rank:

| Sample Count | p99 Rank | Notes |
| ---: | ---: | --- |
| 20 | 20 | Equals max, too noisy |
| 50 | 50 | Still equals max |
| 100 | 99 | Only a couple of tail observations |
| 1,000 | 990 | Roughly 10 samples above p99 |
| 10,000 | 9,900 | 100 samples above p99 |
| 100,000 | 99,000 | 1,000 samples above p99 |

These numbers only explain percentile rank positions; they **do not guarantee confidence intervals**. Latency is often correlated over time due to request bursts, GC, and incidents; 10,000 consecutive samples are not necessarily equivalent to 10,000 independent observations.

### 3.7. Do Not Average p99 Values

Suppose two minutes:

~~~text
Minute A: 10,000 requests, p99 = 100 ms
Minute B:    100 requests, p99 = 1,000 ms
~~~

Do not compute the p99 of all 10,100 requests as:

~~~text
(100 + 1000) / 2 = 550 ms   // WRONG
~~~

Nor can you take a weighted average of two p99 values to obtain an exact combined p99. You must **merge raw observations or mergeable histograms/summaries of sufficient accuracy**, then compute the percentile of the merged distribution.

### 3.8. Percentiles per Operation Type

A read by `_id` may take 2–10 ms, while an aggregation report takes 300–600 ms. If combined:

~~~text
95% of requests are fast point lookups
 5% of requests are slow aggregations
~~~

The overall p95 can **completely hide** the aggregation latency. Therefore:

- Measure p50/p95/p99 **per operation/endpoint/query shape**.
- Add overall p50/p95/p99 to track aggregate user experience.
- Always report sample count and traffic share for each group.

## 4. Defining SLIs, SLOs, and PASS/FAIL Criteria

### 4.1. SLI

A **Service Level Indicator** is a measurable metric, for example:

- p95 latency of the search API.
- p99 latency of point lookups.
- Successful throughput.
- Error rate (including timeouts).
- Percentage of requests completed within a time budget.

### 4.2. SLO

A **Service Level Objective** is a chosen target for an SLI over a clearly defined time window.

Hypothetical example for the lab/illustrative system:

| Workload | Offered Load Rate | p50 | p95 | p99 | Error Rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| **Search feed** | 140 req/s | ≤ 40 ms | ≤ 150 ms | ≤ 300 ms | ≤ 0.2% |
| **Point lookup** | 40 req/s | ≤ 15 ms | ≤ 60 ms | ≤ 120 ms | ≤ 0.2% |
| **Aggregation summary** | 20 req/s | ≤ 100 ms | ≤ 400 ms | ≤ 800 ms | ≤ 0.5% |
| **Bounded update** | 10 req/s | ≤ 40 ms | ≤ 180 ms | ≤ 400 ms | ≤ 0.2% |

The numbers in the table are **self-defined illustrative targets**, not MongoDB standards or mandatory requirements for every product. They must be calibrated from business SLOs, network location, data size, hardware, and cost.

### 4.3. Recording Measurement Conditions Alongside Criteria

A verifiable statement:

> Over 30 minutes of steady-state in a staging environment with a production-equivalent dataset and indexes, when the load generator offers 200 req/s according to the workload mix, Search Feed must achieve p95 ≤ 150 ms, p99 ≤ 300 ms, error rate ≤ 0.2%, and a minimum achieved successful throughput of 139 req/s for this workload alone.

You must also record:

- Client and database location.
- Instance count / cluster size.
- Driver version, pool settings.
- Warmup time.
- Write concern / read preference / read concern.
- Cache/dataset state.
- Retry and timeout policies.
- Definition of "success" and sampling method.

### 4.4. Do Not Evaluate a Single SLO in Isolation

A system can meet p95 because it **rejected 30% of requests** or because the generator only produced half of the intended load. Therefore, PASS criteria must include:

1. **Offered load meets the target** with the proper request mix.
2. **Successful throughput** meets the minimum threshold.
3. **Latency percentiles** per operation type meet thresholds.
4. **Error/timeout rate** does not exceed threshold.
5. No unbounded queue backlog growth.
6. No severe anomalies in replication, storage, or resources.
7. Results have sufficient sample size and are repeatable.

### 4.5. Percentiles vs. Threshold Compliance Ratios

Two descriptions:

~~~text
p95 response time <= 150 ms
95% of requests complete <= 150 ms
~~~

are conceptually closely related, but you must standardize how **failed requests, timeouts, late completions, sampling, and the percentile method** are handled. The SLO "95% of requests under 150 ms" is often convenient for **good events/total events** calculations, while p95 is a summary statistic. In operations, both should have clear definitions.

## 5. Building a Representative Workload from Production

### 5.1. A Workload Is More Than Read/Write Ratio

Two systems can both be "80% read, 20% write" yet behave completely differently:

~~~text
System A:
  80% indexed reads by _id
  20% small inserts

System B:
  80% multi-stage aggregations with large sorts
  20% updates to a single document containing a very long array
~~~

CPU, I/O, lock, cache, and index maintenance costs differ dramatically.

Therefore, the profile must include **query shapes**, selectivity, payload sizes, and actual frequencies.

### 5.2. Collecting Query Shapes

From logs, authorized APM/profiler, application metrics, or workload discovery:

- Endpoint/operation name.
- MongoDB command and query shape.
- Filter fields and operators.
- Sort, projection, limit, skip.
- Index used and execution plan.
- Frequency and time-of-day pattern.
- Response size.
- Error, timeout, and retry rates.
- Tenant/city/product distribution.

Do not place raw queries containing PII or passwords directly into benchmark suites without a data handling policy.

### 5.3. Example Workload Matrix

A hypothetical mix:

| Operation | Share | MongoDB Pattern | Key Data/Cost Factors |
| --- | ---: | --- | --- |
| **SearchFeed** | 70% | find tenant/city/status/price + sort + limit | Range/selectivity, sort/index |
| **GetListing** | 15% | findOne by _id | Point lookup, cache |
| **CitySummary** | 10% | aggregate match/group | Docs scanned, CPU |
| **UpdateCounter** | 5% | updateOne counter with fixed ID | Write lock/journal/contention |

Total share = **100%**. Measure each operation individually and concurrently at the proper weights to observe read/write interference.

**Warning:** The 70/15/10/5 workload is only an example. For a real-time event-ingestion system, the write ratio can be much higher.

### 5.4. Skewed Tenant Distribution

Production often exhibits skew:

~~~text
Large tenant t001: 60% of traffic
Smaller tenants:   40% of traffic
~~~

The dataset and query generator should reflect this. If a benchmark distributes queries uniformly across 100 tenants, it may miss:

- Hot partitions/chunks.
- Continuously accessed index ranges.
- Cache locality.
- Lock/contention on specific documents.

### 5.5. Hot and Cold Data

Typically, newly posted or popular listings are read far more often than older ones. The query mix should include:

- **Hot reads**: repeated hits on a small working set.
- **Warm reads**: moderate concentration.
- **Cold reads**: scanning/reading data rarely present in cache.

Querying the same document by `_id` one million times can produce an artificially rosy benchmark because everything stays in cache.

### 5.6. Document and Array Sizes

Performance can be affected by:

- Small 1 KiB documents vs. 100 KiB documents.
- Arrays with a few elements vs. thousands of elements.
- Deeply nested embedded documents.
- Number of projected fields.
- Index cardinality.
- Multikey index entries.
- Rate of updates that grow document size.

A dataset consisting solely of uniform small documents does not represent an application with large arrays and metadata.

### 5.7. Time-of-Day and Seasonality

A system may experience:

- Heavy search reads in the morning.
- 3× midday bursts.
- End-of-day aggregation jobs.
- End-of-month payment reconciliation.
- Large bulk data imports.

Therefore, multiple scenarios—**steady, peak, batch overlap, recovery catch-up**—may be needed rather than a single static test.

## 6. Test Data Must Match Production Characteristics

### 6.1. Size Is Not the Only Factor

To model a 100-million-document collection, a small lab cannot necessarily create all 100 million documents. However, you must recognize that if you only have 5,000 documents and all of them fit inside the WiredTiger cache, conclusions about I/O cannot be generalized to production.

When scaling down a dataset, explicitly document the differences:

- Total documents/bytes.
- Number of tenants and hot tenant share.
- Cardinality of city/status/category.
- Distribution of price and createdAt.
- Proportion of large documents and array entry counts.
- Working set vs. RAM/WiredTiger cache.
- Selectivity of each filter.

### 6.2. Purposeful Synthetic Data

You do not necessarily need to copy real PII. You can generate synthetic data while preserving key statistics: price distributions, record counts per city, metadata lengths, listings per tenant, and temporal concentration.

Do not just use uniform random values:

~~~text
tenantId uniform random 1..1000
city uniform random 1..100
price uniform random 1..100
~~~

if production has 65% of listings in one city, many listings in mid-range prices, and only a few large tenants.

### 6.3. Recording Data Provenance

A benchmark should record the dataset version:

~~~text
datasetName: listings-synthetic-v1
documents: 12000
tenantDistribution: skewed
cityDistribution: synthetic
embedding: none
payloadSize: bounded
seed: deterministic
indexes: captured separately
~~~

When results improve after optimization, you must know whether the data or indexes changed unexpectedly.

## 7. mongosh Lab: Creating a Reproducible Load-Test Dataset

### 7.1. Lab Scope

Database:

~~~text
mongo_perf_lab_362
  lab_listings
  lab_counters
~~~

Plan:

- Seed **12,000 listings** with deterministic IDs.
- Use a tenant distribution with one hot tenant group.
- Include city, status, category, price, createdAt, and an amenities array.
- Create explicitly chosen indexes.
- Seed **16 counters** dedicated to write testing without touching real business data.
- Do not drop the database or collections.
- Do not generate heavy load during seeding beyond bounded batches.

### 7.2. Idempotent Seed Script

Run in `mongosh` on an **isolated local/staging** environment with write/`createIndex` permissions:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_perf_lab_362");
  const listings = lab.getCollection("lab_listings");
  const counters = lab.getCollection("lab_counters");
  const tag = "mongo-perf-362-v1";
  const total = 12000;
  const batchSize = 400;
  let ops = [];

  function writeBatch() {
    if (ops.length === 0) return;
    listings.bulkWrite(ops, { ordered: false });
    ops = [];
  }

  for (let i = 0; i < total; i++) {
    const tenantId = i % 10 < 6
      ? "t001"
      : "t" + String((i % 24) + 2).padStart(3, "0");
    const city = ["HCM", "HN", "DN"][i % 3];
    const category = ["studio", "apartment", "house"][i % 3];
    const id = "b362-listing-" + String(i).padStart(6, "0");

    const doc = {
      _id: id,
      labTag: tag,
      tenantId,
      city,
      category,
      status: i % 10 === 0 ? "inactive" : "active",
      rentMillion: 6 + (i % 35),
      createdAt: new Date(Date.UTC(2026, 0, 1) + i * 60000),
      title: "Synthetic listing " + i,
      amenities: i % 4 === 0
        ? ["desk", "wifi", "parking", "balcony"]
        : ["wifi"],
      description: "Lab-only document for query-shape testing."
    };

    ops.push({
      replaceOne: {
        filter: { _id: id, labTag: tag },
        replacement: doc,
        upsert: true
      }
    });

    if (ops.length >= batchSize) {
      writeBatch();
    }
  }
  writeBatch();

  for (let id = 0; id < 16; id++) {
    counters.updateOne(
      {
        _id: "b362-counter-" + id,
        labTag: tag
      },
      {
        $setOnInsert: {
          labTag: tag,
          increments: 0,
          updatedAt: new Date(0)
        }
      },
      { upsert: true }
    );
  }

  listings.createIndex(
    {
      tenantId: 1,
      city: 1,
      status: 1,
      createdAt: -1,
      _id: -1
    },
    { name: "ix_b362_tenant_city_status_recent" }
  );

  listings.createIndex(
    {
      tenantId: 1,
      status: 1,
      city: 1
    },
    { name: "ix_b362_tenant_status_city" }
  );

  printjson({
    labListings: listings.countDocuments({ labTag: tag }),
    labCounters: counters.countDocuments({ labTag: tag }),
    indexNames: listings.getIndexes().map(x => x.name)
  });
})();
~~~

Expected output:

~~~text
labListings = 12000
labCounters = 16
~~~

**Run only on an authorized lab database.** The script intentionally does not drop the collection; subsequent runs replace the lab listings with the same `_id` and preserve existing counters. If an `_id` collides with a non-lab document, the **labTag** filter prevents overwriting it, though the upsert will raise a duplicate key error; stop and investigate rather than deleting non-lab data.

### 7.3. Inspecting Dataset Distribution

~~~javascript
const lab = db.getSiblingDB("mongo_perf_lab_362");
const listings = lab.getCollection("lab_listings");

printjson(
  listings.aggregate([
    { $match: { labTag: "mongo-perf-362-v1" } },
    {
      $group: {
        _id: {
          tenantId: "$tenantId",
          city: "$city",
          status: "$status"
        },
        n: { $sum: 1 }
      }
    },
    { $sort: { n: -1 } },
    { $limit: 20 }
  ]).toArray()
);
~~~

The goal is to verify the distribution, not to measure latency performance with a single aggregation run.

### 7.4. Query A — Search Feed

~~~javascript
const lab = db.getSiblingDB("mongo_perf_lab_362");
const listings = lab.getCollection("lab_listings");

const feedQuery = {
  labTag: "mongo-perf-362-v1",
  tenantId: "t001",
  city: "HCM",
  status: "active",
  rentMillion: { $lte: 20 }
};

printjson(
  listings.find(
    feedQuery,
    {
      _id: 1,
      title: 1,
      rentMillion: 1,
      createdAt: 1
    }
  )
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .toArray()
);
~~~

Query A combines **tenant + city + status + price range + sort + limit**. This is a pattern commonly seen in listing search applications.

With the index **ix_b362_tenant_city_status_recent**, the equality and sort fields can benefit; **rentMillion** is not in this index, so MongoDB may still need additional filtering. Do not assume the plan is optimal without checking `explain`.

### 7.5. Query B — Point Lookup

~~~javascript
printjson(
  listings.findOne(
    { _id: "b362-listing-004200" },
    {
      projection: {
        _id: 1,
        tenantId: 1,
        title: 1,
        city: 1
      }
    }
  )
);
~~~

Lookup by **_id** typically has a very different access path from a multi-document range+sort query. Do not use Query B's p99 to infer Query A's p99.

### 7.6. Query C — Aggregation Summary

~~~javascript
printjson(
  listings.aggregate([
    {
      $match: {
        labTag: "mongo-perf-362-v1",
        tenantId: "t001",
        status: "active"
      }
    },
    {
      $group: {
        _id: "$city",
        count: { $sum: 1 },
        avgRentMillion: { $avg: "$rentMillion" }
      }
    },
    { $sort: { count: -1 } }
  ]).toArray()
);
~~~

This aggregation examines far more documents than a point lookup and may consume more CPU/index reads. Include it in the workload mix to see its real impact when running concurrently with search.

### 7.7. Query D — Counter Update (Lab Only)

~~~javascript
const counters = lab.getCollection("lab_counters");

printjson(
  counters.updateOne(
    {
      _id: "b362-counter-0",
      labTag: "mongo-perf-362-v1"
    },
    {
      $inc: { increments: 1 },
      $set: { updatedAt: new Date() }
    }
  )
);
~~~

This is a write **with side effects**; run it only when intending to test writes. The counter is isolated to the lab's dedicated collection. Because the document is a hot key, contention behavior may differ from the real application's write workload; if production writes are distributed, replace Query D with a more representative pattern.

### 7.8. How Does the Lab Dataset Differ from Production?

12,000 small documents do not yet represent:

- Millions of documents occupying hundreds of GiB.
- A dataset that does not fit in the WiredTiger cache.
- Cross-region replication.
- Multi-collection transaction chains.
- Search indexes / vector / geospatial workloads.
- Sharded clusters and hot shards.

**Do not use lab latency numbers as production promises.** The lab teaches measurement methodology, not capacity proof.

## 8. Indexes and Explain: Preparing Before Applying Load

### 8.1. Checking Actual Indexes

~~~javascript
const lab = db.getSiblingDB("mongo_perf_lab_362");
const listings = lab.getCollection("lab_listings");
printjson(listings.getIndexes());
~~~

Confirm the expected indexes exist. If an index build is still in progress, the load test may measure build overhead rather than steady-state workload performance.

### 8.2. Explaining Query A

~~~javascript
const q = {
  labTag: "mongo-perf-362-v1",
  tenantId: "t001",
  city: "HCM",
  status: "active",
  rentMillion: { $lte: 20 }
};

const plan = listings
  .find(
    q,
    { _id: 1, title: 1, createdAt: 1, rentMillion: 1 }
  )
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");

printjson(plan);
~~~

Focus on:

- **winningPlan**.
- **totalKeysExamined**.
- **totalDocsExamined**.
- **nReturned**.
- **executionTimeMillis**.
- Stages such as **IXSCAN, FETCH, SORT, COLLSCAN** when present.

Stage names and output structure can vary across **MongoDB versions/query engines**; do not write brittle tests asserting that every index scan must appear at one exact JSON path.

### 8.3. Examined-to-Returned Ratio

Suppose:

~~~text
totalDocsExamined = 50,000
nReturned = 20
~~~

This signals the query is examining many documents to return very few results. It is **not enough** on its own to conclude which exact index to create, but it indicates you should inspect selectivity/sort, filter fields, index prefixes, and data distribution.

If `totalDocsExamined=20` yet latency remains high, investigate network, disk/cache, document size, pool queueing, and concurrent workload.

### 8.4. Explain Is Not a Throughput Benchmark

**Explain** helps you understand the query plan; it is not the sole source for measuring user-perceived latency. Explain plans carry overhead and may differ from natural execution in some situations; a single explain does not reveal the p95/p99 distribution.

Use:

~~~text
explain -> identify execution path and server cost
load test -> measure behavior under concurrent load
monitoring -> pinpoint system bottlenecks
~~~

### 8.5. Do Not Create Indexes Mid-Comparison Without Versioning

When running before/after optimization tests:

1. Record initial index definitions and dataset version.
2. Run multiple baseline iterations.
3. Add the approved index.
4. Wait for the index build to finish and the system to stabilize.
5. Re-run the exact same workload/conditions.
6. Compare read latency, write latency, storage, and cache together.

Do not compare a cold-cache baseline run with a warm-cache after run and conclude the new index cut latency by 80%.

## 9. Open-Loop vs. Closed-Loop Load Generators

### 9.1. Closed-Loop

Each worker sends a new request when the previous request finishes:

~~~text
Worker 1: req -> wait -> req -> wait -> ...
Worker 2: req -> wait -> req -> wait -> ...
Worker 3: req -> wait -> req -> wait -> ...
~~~

Pros:

- Easy to implement.
- Enforces bounded concurrency.
- Suitable for modeling a fixed number of clients with request-response behavior.

Cons:

- When the server slows down, workers issue new requests more slowly.
- Offered load automatically drops right when the system degrades.
- Hard to prove the system sustains a fixed peak arrival rate.

### 9.2. Open-Loop

The generator schedules requests at an arrival rate largely independent of prior request completion times:

~~~text
Timeline: 0 ms, 10 ms, 20 ms, 30 ms, ...
           |      |      |      |
           +--> Requests are scheduled

Requests can queue up if the
server cannot keep up.
~~~

Open-loop is appropriate when asking:

> "If real users arrive at 200 req/s for 5 minutes, what will the system do?"

However, you must **bound the number of in-flight requests**, implement backpressure/abort mechanisms, and ensure the load generator itself does not become the bottleneck. Firing unbounded requests without guardrails can cause an unintended outage.

### 9.3. Coordinated Omission

**Coordinated omission** occurs when the measurement system inadvertently omits waiting time that real users would experience because request dispatch timing adjusts to system slowdowns.

Example:

~~~text
Intent: send 1 request every 10 ms.

Server stalls for 1,000 ms.

Closed-loop:
  sends only 1 request, measures 1,000 ms latency,
  then sends the next request.

Scheduled open-loop:
  there are ~100 arrival slots in
  1,000 ms; queueing of those requests
  must be reflected or reported as dropped/late.
~~~

With closed-loop, many requests that should have arrived during the stall **are never issued**, so the histogram can miss the tail latency of the true offered arrival process.

### 9.4. Avoid "Fixing" Coordinated Omission with Fabricated Numbers

Do not synthesize 99 fake requests with guessed latencies and call them real measurements. Instead:

- Use a load generator that supports **constant arrival rate** and scheduled latency histograms.
- Record **scheduled time**, **actual start time**, and **completion time**.
- Track **queue wait, in-flight count, and dropped/rejected requests**.
- Enforce a clear policy when the generator is overloaded.
- Document the load model so readers understand the percentile semantics.

### 9.5. Relationship to User Behavior

Not every application requires pure open-loop load. Real users have **think time**, response-dependent actions, and sequential dependencies between requests. A representative workload may combine:

- Sessions with think time (paced closed-loop).
- API/automation traffic by arrival rate (open-loop).
- Peak-hour bursts.

The key is choosing a model matching **the behavior under evaluation** and documenting the methodology.

## 10. Experimental Plan with Warmup and Phases

### 10.1. Warmup

When a test starts:

- New connections are opened.
- TLS handshakes occur.
- The connection pool ramps up to steady-state.
- Caches begin warming up.
- Query planner and runtime components stabilize.

If production typically runs continuously, include a **warmup** before the measurement phase. If cold start is what you want to evaluate, run a **dedicated cold test**; do not discard cold start and claim cold performance is good.

### 10.2. Baseline

Run a small load to verify:

- The script uses the intended query shapes.
- Credentials have no errors.
- Indexes are ready.
- The server has no pre-existing anomalies before the test.
- The load generator has spare CPU/memory/network capacity.

If the baseline already times out, there is no reason to rush to maximum load.

### 10.3. Ramp-Up

Example:

~~~text
0-5 min:    50 RPS
5-10 min:  100 RPS
10-15 min: 150 RPS
15-20 min: 200 RPS
~~~

Monitor p95/p99, queueing, throughput, errors, and resources at each step. Avoid ramping too quickly, which blurs stages together and makes the saturation point hard to identify.

### 10.4. Steady-State

Hold a constant load long enough, such as 20–30 minutes, to gather sufficient samples and observe:

- Cache stability.
- Batching/journaling/replication effects.
- Periodic background jobs.
- Recurring failure modes under load.

An appropriate duration depends on workload type and statistical requirements; 30 minutes is just an example.

### 10.5. Spike

For example, jump from 200 to 500 RPS for 30 seconds. Measure:

- How the system reacts.
- Whether queues accumulate.
- Errors/timeouts and recovery time.
- Whether load shedding or offered-load throttling occurs.

Spike tests require strict safety boundaries and should not be run casually on production.

### 10.6. Soak

Run for multiple hours to uncover:

- Memory leaks / client connection leaks.
- Cache churn.
- Disk/journal pressure.
- Oplog lag.
- Accumulating slow operations.
- Periodic jobs overlapping load.

Soak testing has a different goal than "finding the highest RPS in 60 seconds."

### 10.7. Scenarios to Separate

| Scenario | Objective |
| --- | --- |
| Cold-start | Initial latency / empty cache |
| Warm steady | Normal SLOs |
| Peak | Peak-hour capacity |
| Spike | Behavior under sudden arrival-rate surges |
| Soak | Long-term stability |
| Batch overlap | Impact of concurrent imports/reporting |
| Replica lag stress | Write concern / read preference under replication delay |
| Recovery scenario | Recovery after failover, in a dedicated chaos environment |

Do not cram every question into a single scenario and end up unable to isolate the cause of the results.

## 11. Basic Node.js Benchmark: Closed-Loop, Bounded Concurrency

### 11.1. Why Use the Node.js Driver?

The MongoDB driver lets you measure **end-to-end operation duration from the application** (including driver/network/server wait as experienced by the Promise). This is closer to backend reality than a standalone `explain`.

However, the script below is a **closed-loop demo** and cannot replace a professional distributed load generator supporting constant arrival rate and coordinated-omission correction.

### 11.2. Preparation

In a lab directory you manage (not project files created by a Worker), you can install:

~~~bash
npm init -y
npm install mongodb
~~~

Ensure a Node.js version supported by the corresponding MongoDB Node.js driver and an environment variable **MONGODB_URI** pointing to an authorized lab instance.

The example script uses ES module syntax; save it as **bench362.mjs** in your learning environment. These commands are instructions in the documentation, **not executed by a Worker**.

### 11.3. Benchmark Script

~~~javascript
// bench362.mjs
import { MongoClient } from "mongodb";
import { performance } from "node:perf_hooks";

const uri = process.env.MONGODB_URI;
if (!uri) {
  throw new Error("Missing MONGODB_URI");
}

const concurrency = 8;
const warmupSeconds = 10;
const measureSeconds = 30;
const allowWrites = process.env.BENCH362_ALLOW_WRITES === "true";
const tag = "mongo-perf-362-v1";

const client = new MongoClient(uri, {
  maxPoolSize: 16,
  serverSelectionTimeoutMS: 5000,
  socketTimeoutMS: 10000,
  retryWrites: false
});

function percentile(values, p) {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.max(1, Math.ceil(p * sorted.length)) - 1;
  return sorted[index];
}

function summarize(name, values, errors, elapsedSeconds) {
  return {
    operation: name,
    completedSuccess: values.length,
    errors,
    successfulOpsPerSecond:
      Number((values.length / elapsedSeconds).toFixed(2)),
    p50Ms: percentile(values, 0.50),
    p95Ms: percentile(values, 0.95),
    p99Ms: percentile(values, 0.99),
    maxMs: values.length
      ? values.reduce((max, value) => Math.max(max, value), -Infinity)
      : null
  };
}

await client.connect();

try {
  const lab = client.db("mongo_perf_lab_362");
  const listings = lab.collection("lab_listings");
  const counters = lab.collection("lab_counters");

  const exists = await listings.countDocuments({
    labTag: tag
  }, { limit: 1 });
  if (exists === 0) {
    throw new Error(
      "Lab data has not been seeded yet. Run section 7 first."
    );
  }

  const operations = allowWrites
    ? [
        ...Array(14).fill("feed"),
        ...Array(3).fill("point"),
        ...Array(2).fill("summary"),
        "counter"
      ]
    : [
        ...Array(14).fill("feed"),
        ...Array(4).fill("point"),
        ...Array(2).fill("summary")
      ];

  const measures = Object.fromEntries(
    [...new Set(operations)].map(name => [
      name, { latencies: [], errors: 0 }
    ])
  );

  async function perform(name, workerId, iteration) {
    if (name === "feed") {
      return listings.find({
        labTag: tag,
        tenantId: "t001",
        city: "HCM",
        status: "active",
        rentMillion: { $lte: 20 }
      }, {
        projection: {
          _id: 1,
          title: 1,
          rentMillion: 1,
          createdAt: 1
        },
        maxTimeMS: 3000
      })
      .sort({ createdAt: -1, _id: -1 })
      .limit(20)
      .toArray();
    }

    if (name === "point") {
      const idNumber = (workerId * 997 + iteration * 47) % 12000;
      const id = "b362-listing-" +
        String(idNumber).padStart(6, "0");

      return listings.findOne(
        { _id: id, labTag: tag },
        {
          projection: { _id: 1, title: 1, tenantId: 1 },
          maxTimeMS: 3000
        }
      );
    }

    if (name === "summary") {
      return listings.aggregate([
        {
          $match: {
            labTag: tag,
            tenantId: "t001",
            status: "active"
          }
        },
        {
          $group: {
            _id: "$city",
            count: { $sum: 1 }
          }
        }
      ], { maxTimeMS: 3000 }).toArray();
    }

    if (name === "counter" && allowWrites) {
      return counters.updateOne(
        {
          _id: "b362-counter-" + (workerId % 16),
          labTag: tag
        },
        { $inc: { increments: 1 } },
        { upsert: false, writeConcern: { w: "majority" } }
      );
    }

    throw new Error("Invalid operation name: " + name);
  }

  const testStart = performance.now();
  const measureStart = testStart + warmupSeconds * 1000;
  const measureEnd = measureStart + measureSeconds * 1000;

  async function worker(workerId) {
    let iteration = workerId;
    while (performance.now() < measureEnd) {
      const name = operations[iteration % operations.length];
      const started = performance.now();
      let error = null;

      try {
        await perform(name, workerId, iteration);
      } catch (e) {
        error = e;
      }

      const ended = performance.now();
      const inMeasurementWindow =
        started >= measureStart &&
        ended <= measureEnd;

      if (inMeasurementWindow) {
        if (error) {
          measures[name].errors++;
        } else {
          measures[name].latencies.push(
            Number((ended - started).toFixed(3))
          );
        }
      }

      // Even when errors occur, the script continues to measure
      // error rate. Do not retry manually so errors are not hidden.
      iteration++;
    }
  }

  await Promise.all(
    Array.from({ length: concurrency },
      (_, id) => worker(id))
  );

  const report = Object.entries(measures).map(
    ([name, data]) => {
      const row = summarize(
        name, data.latencies, data.errors, measureSeconds
      );
      const total = data.latencies.length + data.errors;
      return {
        ...row,
        errorRatePct: total
          ? Number((100 * data.errors / total).toFixed(3))
          : null
      };
    }
  );

  console.log(JSON.stringify({
    mode: "closed-loop",
    concurrency,
    warmupSeconds,
    measureSeconds,
    allowWrites,
    report
  }, null, 2));
} finally {
  await client.close();
}
~~~

### 11.4. Running in Read-Only Mode

Set the `MONGODB_URI` environment variable according to your OS and secret policy, then run:

~~~bash
node bench362.mjs
~~~

The default mode **does not invoke counter updates**. The workload consists of 70% feed, 20% point, and 10% summary based on scheduled turns per worker.

### 11.5. Enabling Writes Only in the Lab

Once you have confirmed **mongo_perf_lab_362.lab_counters** is lab data:

~~~bash
# For bash shell on the lab machine:
BENCH362_ALLOW_WRITES=true node bench362.mjs
~~~

The workload changes to **70% feed, 15% point, 10% summary, 5% counter update**. Because operations take different amounts of time and the generator is closed-loop, **the completion ratio within a time window may deviate** slightly from the scheduled turn ratio.

If you do not want any writes to occur, **do not enable BENCH362_ALLOW_WRITES**.

### 11.6. What Does This Script Measure?

For each operation:

- Number of successful requests completed **within the measurement window**.
- Number of failed operations.
- p50/p95/p99 from **successful operations**.
- Successful operations per second over the measurement window.

**Important:** errors and timeouts are reported separately and **excluded from latency percentiles** in this simple script. If you need an end-to-end SLO across all requests, report the good events/total events ratio and handle timeouts according to policy. Do not hide a high timeout rate behind percentiles computed solely from successful requests.

### 11.7. Technical Limitations of the Demo

This is an educational script, not a production load test:

- **Closed-loop**: does not guarantee an offered arrival rate.
- Single process; generator CPU itself can become a bottleneck.
- Stores samples in an Array; unsuitable for tens of millions of observations.
- Does not emit mergeable histograms or confidence intervals.
- Does not separately measure driver pool queue-wait.
- No advanced warm/cold isolation.
- Does not track failed requests completing after the measurement window.
- Does not capture raw server metrics or index statistics in the same report.
- Uses a single very hot feed query rather than modeling full query parameter diversity.
- Iteration-based request ratios do not guarantee a traffic distribution identical to production.

For rigorous benchmarking, use a load generation tool supporting **arrival-rate control, histograms, labels, distributed load generation, and metrics integration**, or build a harness with those capabilities.

### 11.8. An Easy-to-Miss Measurement Bug: Warmup Must Have the Same Mix

Running warmup with only point lookups and then steady-state with aggregations and writes can produce an unintended cache/pool state. In this demo, the same operations run across both warmup and measurement, reducing unnecessary discrepancies.

## 12. Computing p50/p95/p99 When Errors and Timeouts Occur

### 12.1. Successes and Failures

Suppose at a load of 200 req/s:

~~~text
Completed requests: 10,000
Success:             9,700
Timeout/error:         300
~~~

Error rate:

\[
\frac{300}{10,000}\times100\%=3\%
\]

If only the 9,700 successful latencies are included in p99, you might see a good-looking p99 even though 3% of customers hit errors. Therefore, report **successful p99 + error/timeout rate**, or also use an SLI such as "percentage of all requests completing successfully under 300 ms."

### 12.2. Requests Still In-Flight at the End of the Window

A benchmark runs for 60 seconds and stops collecting samples. Requests sent during the window that finish after second 60 will be missing from the report without a clear policy.

Options:

- Count by **completion timestamp** within the steady-state window.
- Count by **arrival timestamp** and wait for in-flight requests to finish with a deadline.
- Track **in-flight/drained counts** and report truncated requests separately.

The chosen method must be documented; otherwise p99 can suffer from **survivorship bias** because the slowest requests have not finished yet.

### 12.3. Histograms

Instead of retaining every individual sample unboundedly, real systems use **histograms**:

~~~text
Latency buckets:
  <= 10 ms
  <= 25 ms
  <= 50 ms
  <= 100 ms
  <= 250 ms
  <= 500 ms
  <= 1,000 ms
  > 1,000 ms
~~~

A histogram needs **bucket boundaries aligned with SLOs**. If the p99 target is 300 ms but the buckets only have 100 and 1,000 ms, the estimated p99 will be too coarse to decide pass/fail near 300 ms.

### 12.4. HdrHistogram and Fixed Buckets

Specialized tools may use HdrHistogram or other mergeable histogram formats under specific rules. Key points:

- The histogram must preserve tail precision adequately.
- Workers must use compatible bucket schemes.
- Merge **counts per bucket** before computing percentiles.
- Never average individual workers' p99s.
- Clearly document units (**microseconds** vs. **milliseconds**).

### 12.5. Sample Count and Low-Traffic Endpoints

An endpoint with only 30 requests in 30 minutes lacks enough observations to derive a reliable p99. You should:

- Report sample count alongside the percentile.
- Use a longer window or dedicated synthetic load.
- Inspect max and individual slow traces.
- Consider confidence intervals / bootstrapping when comparing two versions.
- Do not artificially boost an endpoint from 0.01 RPS to 100 RPS and still label it "representative" if your goal is measuring normal total load.

### 12.6. Outliers Are Not Automatically Measurement Errors

A request taking 5 seconds could be:

- Client GC pause.
- Network stall.
- TLS reconnect.
- Connection pool timeout.
- Disk I/O spike.
- Server failover.

Do not discard all outliers just to make p99 look cleaner. If removing a sample due to a proven instrumentation bug, define criteria beforehand and keep an audit trail.

## 13. When Is the Generator the Bottleneck?

### 13.1. Symptoms

- Load generator CPU near 100%.
- Generator cannot dispatch the full offered RPS.
- Large event loop lag.
- Growing memory from storing too many raw samples.
- Client network interface hitting throughput limits.
- Misconfigured connection pool or too few connections.
- TLS/DNS/serialization consuming most client-side time.

If the generator caps out at 150 RPS, you cannot conclude MongoDB's maximum capacity is also 150 RPS.

### 13.2. Separating Load Generators from the Database

A professional test may use:

~~~text
Load Generator A ----+
Load Generator B ----+----> App / MongoDB
Load Generator C ----+
~~~

And collect:

- Offered RPS per generator.
- Achieved RPS.
- Client CPU/network.
- Mergeable latency histograms.
- Connection error rates.
- Clock synchronization and timestamp conventions.

### 13.3. Do Not Measure from the Same Host If Real Network Effects Matter

Running `mongosh` on the same host as `mongod` can significantly reduce network/TLS latency. If production runs the app in a different AZ/region, the benchmark must replicate equivalent network placement.

Conversely, do not place the generator across an unusually distant network and blame MongoDB for all added latency.

## 14. MongoDB-Side Metrics to Explain p99

### 14.1. Client Metrics and Server Metrics Must Be Correlated

An investigation table:

| Client Symptom | MongoDB/Infrastructure Data to Inspect |
| --- | --- |
| p99 rises while p50 is stable | GC, pool waits, disk spikes, slow queries, failover |
| Throughput plateaus as offered load rises | CPU, admission queues, disk throughput, lock contention |
| High update p99 | Journal/durability, lock/write conflicts, majority replication |
| Query with small nReturned is slow | Keys/docs examined, disk misses, sort, network |
| Feed slows down during aggregation | CPU/cache/IO contention, spill, concurrent requests |
| Timeouts increase | Pool size, server selection, network, maxTimeMS, overload |

### 14.2. serverStatus

With an account holding appropriate metrics read privileges:

~~~javascript
const admin = db.getSiblingDB("admin");
const status = admin.runCommand({ serverStatus: 1 });

printjson({
  uptime: status.uptime,
  connections: status.connections,
  opcounters: status.opcounters,
  wiredTiger: {
    cache: status.wiredTiger?.cache
  }
});
~~~

The output can be large and field names depend on server version/topology. **Counters such as opcounters are typically cumulative**, so compute the **delta between two timestamps** rather than treating absolute totals as ops/second.

### 14.3. WiredTiger Cache

Track relevant signals such as:

- Cache used/dirty bytes.
- Pages read into cache.
- Pages written/evicted.
- Eviction activity.
- Disk read/write latency.
- Ratio of working set exceeding cache capacity.

A benchmark whose dataset fits in RAM can look good at p99, but when the working set exceeds cache, read latency and disk I/O increase sharply.

### 14.4. Connections and Pool

MongoDB server tracks connections; the driver manages its own **connection pool**.

If the app has:

~~~text
maxPoolSize = 10
200 requests in flight
~~~

many requests must wait for an available socket. Client p99 latency can climb due to pool queueing even while server query execution stays fast.

Measure driver pool checkout wait alongside server metrics to determine whether to increase pool size, lower concurrency, or fix slow queries holding connections too long.

### 14.5. Slow Operations / Profiler

MongoDB provides a database profiler and slow query logs/APM mechanisms, depending on version and configuration.

In a lab with admin privileges, you can check profiling level:

~~~javascript
const lab = db.getSiblingDB("mongo_perf_lab_362");
printjson(lab.getProfilingStatus());
~~~

Enabling the profiler adds overhead, stores sensitive query contents/metadata, and behaves differently on some Atlas deployments. **Do not enable profiling level 2 in production solely to gather extra benchmark metrics** without evaluating cost and retention.

### 14.6. currentOp

When long-running slow operations occur, `currentOp` or appropriate monitoring tools can inspect active commands, elapsed time, and wait states within granted permissions. Do not overuse `killOp` or alter a running system without assessing side effects.

### 14.7. Replication and Write Concern

In a replica set, writing with **w:"majority"** involves replication/durability; write latency is not just updating the document on the primary.

Monitor:

- Secondary replication lag.
- Primary/secondary health.
- Oplog window.
- Write concern timeouts.
- Elections/failovers during the test.

Do not compare write p99 across two experiments if one uses `w:1` and the other uses `w:"majority"` while presenting both as the same workload.

### 14.8. Atlas Metrics

On MongoDB Atlas, you can view corresponding charts/metrics such as CPU, memory, operation execution, connections, cache, disk, replication, and slow queries depending on cluster/tier. Record a time window matching the benchmark.

Select metrics for the actual cluster under test; do not look at a 24-hour averaged chart to explain a 30-second spike.

## 15. Optimize Based on Bottlenecks, Not Intuition

### 15.1. If p99 Rises Due to COLLSCAN

Approach:

1. Inspect query shape and selectivity.
2. Check whether a suitable index already exists.
3. Measure keys/docs examined.
4. Consider an index/compound index matching filter and sort.
5. Evaluate write/index-size trade-offs.
6. Re-run with the same dataset/workload.

Do not create a new index for every single field just because a query has multiple predicates.

### 15.2. If p99 Rises Due to SORT

An unindexed sort may require extra memory and can spill to disk (depending on operation/configuration). Inspect:

- Equality prefix and sort order.
- Cardinality, limit, and query projection.
- Suitable index.
- Number of documents scanned before sorting.

Do not conclude "not enough RAM" before checking the execution plan.

### 15.3. If p99 Rises Due to Pool Queueing

Steps:

- Measure checkout wait and checked-out connection counts.
- Check whether queries hold sockets too long.
- Check total app instances and server connection counts.
- Tune concurrency/pool through controlled experiments.

Increasing `maxPoolSize` arbitrarily can put excessive pressure on the server. A bigger pool will not fix queries blocked on disk I/O.

### 15.4. If p99 Rises Due to Disk

Check:

- Working set vs. WiredTiger cache.
- Disk latency/IOPS/throughput.
- Compaction, backups, index builds, or running batch jobs.
- Read preference, tier, and storage performance.

An index that reduces docs examined can reduce disk reads; however, if the workload genuinely needs to read large amounts of data, you must redesign pagination/read models or infrastructure accordingly.

### 15.5. If Update p99 Is High

Investigate:

- Hot document contention.
- Number of indexes updated per write.
- Array growth or in-place document updates.
- Write conflicts/retries.
- Journal/storage latency.
- Write concern majority and secondary lag.

If you only benchmark a single hot counter while production writes are distributed, you might wrongly conclude all writes require sharding.

### 15.6. If App Logic Is the Bottleneck

When database queries are fast but API p99 is high:

- Check serialization/decompression.
- Service logic and external API calls.
- Connection pool wait.
- Large response payloads.
- Thread pool / event loop blocking.
- GC pauses.

**Do not tune MongoDB indexes to fix an issue occurring entirely before or after the query.**

## 16. Fair Before/After Optimization Comparisons

### 16.1. Hold Conditions Constant

Example report:

~~~text
Baseline:
  dataset: synthetic-v1
  indexes: ixA
  cluster: staging-M
  load: 200 RPS, 70/15/10/5
  duration: 30 min

Change:
  add ixB

After:
  dataset: synthetic-v1
  indexes: ixA + ixB
  cluster: staging-M
  load: 200 RPS, 70/15/10/5
  duration: 30 min
~~~

Results are valid when **only the factor under test changes**, aside from documented and evaluated variance.

### 16.2. Repeat Multiple Runs

A single run:

~~~text
Before p99 = 290 ms
After p99  = 260 ms
~~~

is not enough to prove a consistent improvement. Run multiple iterations in an appropriate order, recording noise factors such as cache, GC, background maintenance, and cross-system traffic.

If natural run-to-run variance is 30–50 ms, a 30 ms difference may not be trustworthy without enough samples/repetitions.

### 16.3. Report Both Performance and Cost

An index might:

- Reduce feed p95 from 180 down to 95 ms.
- Increase insert p99 from 120 up to 190 ms.
- Increase index storage by 25%.

Do not report only the improved feed and deploy if the write SLO starts failing.

### 16.4. Percentile Difference

When comparing before/after:

~~~text
p99 before: 300 ms
p99 after:  240 ms
~~~

Absolute reduction is **60 ms**, relative reduction is **20%**. However, verify **confidence**, sample count, achieved target workload, and error rate. If "after" has more timeouts, a lower successful-request p99 is not necessarily an improvement.

### 16.5. Save Benchmark Artifacts

At minimum record:

- Timestamp, owner, commit/version.
- MongoDB version and FCV if relevant.
- Driver/runtime version.
- Topology / cluster size / network.
- Dataset version and document counts.
- Index definitions.
- Query shapes/mix.
- Load model, offered rate, concurrency, warmup, duration.
- SLI/SLO pass/fail.
- Per-operation samples, percentiles, throughput, errors.
- Client, server, and resource charts.
- Known limitations.

Do not save just a dashboard screenshot with no environment metadata.

## 17. Time-Window Analysis

### 17.1. Aggregated p99 Hides Incidents

A 30-minute test might contain:

~~~text
25 stable minutes: p99 80 ms
 5 disk spike min: p99 2,000 ms
~~~

A single 30-minute aggregate percentile may be meaningful, yet it does not tell you **when** the spike occurred. You need time-series buckets, such as 1-minute intervals, alongside an aggregated histogram for the full run.

### 17.2. Do Not Average Per-Minute Percentiles

Each minute has a different request count. To report "overall p99 for the run," calculate it over the merged distribution. To find the **worst per-minute p99**, that is a separate metric:

~~~text
max( p99_of_minute_1, ..., p99_of_minute_30 )
~~~

Do not call the max of per-minute p99s the overall p99, and do not call their average the total percentile.

### 17.3. Sliding Windows

A dashboard may use rolling 5-minute/30-minute histograms. Key checks:

- Does each window have enough samples?
- Are histograms merged correctly?
- Do time buckets share the same units/semantics?
- Are errors/timeouts wrongly excluded?

If sample count is low, display a **low sample size** warning instead of an overly confident p99 figure.

## 18. Mixed Read/Write Workload Analysis

### 18.1. Running Each Group Alone Is Insufficient

If benchmarking separately gives:

~~~text
SearchFeed alone: p99 100 ms
Update alone:     p99 50 ms
~~~

that does not mean running them concurrently:

~~~text
SearchFeed 140 RPS + Update 10 RPS
~~~

will keep both p99s unchanged. They can contend for CPU, disk, WiredTiger cache, write tickets, or locks.

### 18.2. Designing a Mixed Scenario

A scenario:

~~~text
SearchFeed:    70%
GetListing:    15%
CitySummary:   10%
UpdateCounter:  5%
~~~

Maintain the proportions over time, track actual achieved ratios, and report p50/p95/p99 **per operation**.

### 18.3. Hot Write Skew

If 10 workers update the same document, contention occurs. If production writes each request to a different document, a single hot-key benchmark intentionally measures **worst-case contention**, not general write throughput.

Ideally, include all of:

- A distributed write workload.
- A hot-spot workload at realistic proportions.
- A dedicated contention stress test.

### 18.4. Index Trade-Offs

Adding a compound index to serve reads forces every insert/update to maintain additional index entries. Measure **read and write SLOs together** to avoid local optimization.

## 19. Query Pagination and Response Payload

### 19.1. Offset Pagination

~~~javascript
db.listings.find({ status: "active" })
  .sort({ createdAt: -1 })
  .skip(100000)
  .limit(20);
~~~

With a very large `skip`, the database may have to scan/discard many entries. If production uses deep pagination, benchmarking only page 1 misses the true cost.

### 19.2. Keyset Pagination

Often a better approach for feeds with a deterministic sort order:

~~~javascript
db.listings.find({
  tenantId: "t001",
  status: "active",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $lt: lastId }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

The variables **lastCreatedAt/lastId** come from the previous page; the code illustrates shape only. The query requires a matching index as well as pagination token and tenant authorization handling. When comparing `skip` and keyset, keep page depth, data, and response size identical.

### 19.3. Projection

If the API returns only title/price, do not benchmark fetching long descriptions, embedded image metadata, and nested arrays and compare it against a real API projecting a few fields. Conversely, if the real API sends large payloads, an overly narrow projection in the benchmark artificially improves network latency.

### 19.4. Cursors and Batching

Measuring `find` only up to cursor creation without consuming documents is **not equivalent** to measuring until the API consumes the results. In the Node.js benchmark, **toArray()** ensures retrieval/transfer/deserialization of the result set is included in the Promise latency.

For very large result sets, use streaming/pagination rather than `toArray()` in production, and measure latency by user-visible chunks or complete response as appropriate.

## 20. Sample Evaluable Benchmark Report

### 20.1. Environment Information

~~~yaml
benchmarkId: "mongo-perf-362-example"
environment: "staging-isolated"
dataset: "synthetic-v1"
mongoVersion: "CAPTURE_FROM_DEPLOYMENT"
driverVersion: "CAPTURE_FROM_PACKAGE"
topology: "replica-set"
loadModel: "open-loop-constant-arrival"
warmupMinutes: 5
steadyMinutes: 30
offeredRps: 200
mix:
  searchFeed: 0.70
  getListing: 0.15
  citySummary: 0.10
  updateCounter: 0.05
~~~

This is a team-defined metadata template, not a mandatory MongoDB configuration.

### 20.2. Illustrative Results Table

| Operation | Successful Count | p50 | p95 | p99 | Errors/Timeouts | SLO |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| SearchFeed | 251,000 | 38 ms | 141 ms | 280 ms | 0.1% | PASS |
| GetListing | 53,800 | 9 ms | 44 ms | 107 ms | 0.1% | PASS |
| CitySummary | 35,900 | 86 ms | 390 ms | 870 ms | 0.3% | FAIL p99 |
| UpdateCounter | 17,700 | 45 ms | 175 ms | 420 ms | 0.1% | FAIL p99 |

**All numbers in the table are illustrative**, not measured from this lab. PASS/FAIL evaluation assumes the SLOs in section 4 and an environment meeting the target load.

### 20.3. Reading the Report

- SearchFeed meets the 300 ms p99 target and error rate.
- GetListing meets the 120 ms p99 target.
- CitySummary exceeds the 800 ms p99 target; inspect aggregation plan/CPU/cache.
- UpdateCounter exceeds the 400 ms p99 target; inspect hot document, write concern, and storage.

Unanswered questions:

- Did the generator actually send the full 200 RPS? Need offered vs. achieved.
- Did the last minute spike to 5 seconds p99? Need time series/histograms.
- Was a background index build running? Need environment logs.
- What is the confidence in before/after differences? Need repeat runs and variance.

### 20.4. Optimization Decision

A good report concludes with **verifiable actions**:

~~~text
Issue:
  CitySummary p99 exceeds 800 ms at offered 200 RPS.

Hypothesis:
  Aggregation reads too many documents and incurs cache misses.

Evidence needed:
  explain executionStats, WiredTiger cache,
  disk latency, operator-level time series.

Change:
  test appropriate index or summary precomputation.

Verification:
  re-run the same workload and verify
  SearchFeed, UpdateCounter, and storage cost as well.
~~~

Do not end simply with "add more CPU" before identifying the bottleneck.

## 21. Common Measurement Pitfalls

| Mistake | Misleading Outcome | Fix |
| --- | --- | --- |
| Running a query once | No p95/p99 distribution | Collect many observations |
| Benchmarking on 100 documents | Cache/index trivially fast | Dataset matching working set/selectivity |
| Measuring only the mean | Hides tail latency | p50/p95/p99 + errors |
| Measuring only p99 | Hides throughput and error rate | Report multiple SLIs |
| p99 from 20 samples | p99 nearly or exactly equals max | Report sample count, extend duration |
| Averaging per-minute p99s | Not the combined p99 | Merge histograms/raw data |
| Combining all operations | Slow operations masked by fast traffic | Split by endpoint/query shape |
| Excluding timeouts from reports | Percentiles look artificially good | Report error/timeout and good-event rates |
| Stopping test with in-flight requests | Drops slow tail requests | Clear in-flight/drain policy |
| Closed-loop generator at peak | Offered load drops when server slows | Open-loop arrival-rate benchmark |
| Not measuring generator CPU | Mistakes generator cap for DB limit | Client resource telemetry |
| Testing only hot cache | Cold I/O is hidden | Separate cold-start scenario |
| Testing only page 1 | Misses deep pagination cost | Mix realistic page depths |
| Testing only _id lookups | Misses aggregation/sort cost | Representative query mix |
| Missing write workload | Misses index maintenance/contention | Run mixed read+write workload |
| Uniform random seed data | Misses hot tenants/data skew | Distribution matching production |
| Mixing w:1 and w:majority | Write latencies incomparable | Fix write concern |
| Client proximity differs from prod | Wrong network latency | Equivalent network placement |
| Using explain as latency SLI | Not client response time | Measure from driver/API |
| Creating indexes mid-test | Workload shifts during measurement | Separate baseline and after runs |
| Single-run testing | Noise mistaken for "improvement" | Repeat experiments |
| Watching only average CPU | Misses disk/pool/queue bottlenecks | Multi-dimensional resource metrics |
| Unreported driver auto-retries | Alters error/rate/latency | Document retry policy/attempts |
| Data changes between comparisons | Cannot isolate cause | Stable dataset/version |
| Query results differ across runs | Not the same workload logic | Verify counts/semantic correctness |
| Uncontrolled load on production | Potential outage | Isolated environment, guardrails |

## 22. Checklist from Requirements to Decision

### 22.1. Before Benchmarking

1. Document target SLOs and measurement duration.
2. Break down p50/p95/p99 per **operation**.
3. Collect query shapes and traffic mix from appropriate sources.
4. Record data size/cardinality/selectivity/hot keys.
5. Record index definitions.
6. Define load model and offered RPS/concurrency.
7. Choose client location, driver, TLS, and pool settings.
8. Prepare backup/rollback and an authorized environment.

### 22.2. During Execution

1. Verify seed data, indexes, and cluster health.
2. Run warmup aligned with test goals.
3. Record sample counts, offered load, and achieved throughput.
4. Measure successes/failures/timeouts separately.
5. Record latency histograms per operation.
6. Monitor database CPU, cache, disk, connections, and replication.
7. Monitor load generator resources.
8. Stop/throttle load per safety limits if disruption risk arises.

### 22.3. During Analysis

1. Check whether data has enough samples for p99.
2. Do not average percentiles.
3. Compare per-operation SLOs and overall UX.
4. Verify offered load vs. actual throughput.
5. Analyze time series to spot spikes.
6. Inspect explain/slow query/profiler within authorized scope.
7. Distinguish server bottlenecks, network delays, and pool queueing.
8. Document sources of variance and measurement limitations.

### 22.4. When Optimizing and Retesting

1. State **one specific hypothesis**.
2. Change one intentional group of factors.
3. Keep dataset, workload, and environment virtually unchanged.
4. Repeat the test enough times.
5. Compare read/write p50/p95/p99, errors, and throughput.
6. Measure storage/CPU/IO trade-offs.
7. Update runbooks/dashboards and make the deployment decision.

## 23. Practice Exercises

### Exercise 1 — Reading Percentiles

Explain p50, p95, and p99 across 100 requests. Is p99 the slowest latency?

### Exercise 2 — Nearest-Rank

Given 20 latencies: 18, 23, 21, 20, 19, 24, 22, 26, 27, 25, 29, 31, 28, 30, 32, 35, 34, 40, 120, 600 ms, compute p50/p95/p99 using nearest-rank.

### Exercise 3 — Mean vs. Tail

99 requests take 20 ms, and one request takes 2,000 ms. Calculate the mean. Why can relying solely on the mean cause a team to misjudge user experience?

### Exercise 4 — p99 with Few Samples

With 20 samples, which statistic is p99 roughly equal to? Why does an endpoint with 30 requests/day require different SLO reporting than an endpoint with 100,000 requests/minute?

### Exercise 5 — Non-Additive Percentiles

Two workers have p99 of 80 ms and 500 ms, with counts of 10,000 and 100 respectively. Can you compute the combined p99 via simple or weighted averaging? What data do you need?

### Exercise 6 — Workload Mix

A system has 70% feed, 15% detail, 10% summary, and 5% write. At 200 offered RPS, how many RPS are offered for each operation?

### Exercise 7 — Offered vs. Achieved

The generator tries to send 500 RPS but only completes 300 successful RPS with 10% errors. What statistics do you need to determine whether it is server saturation or a generator bottleneck?

### Exercise 8 — Concurrency

A closed-loop test has 20 workers, and average latency increases from 50 to 200 ms. Approximately how does throughput change assuming negligible think time and overhead?

### Exercise 9 — Coordinated Omission

Suppose arrivals are expected every 10 ms and the server stalls for 1 second, while a closed-loop client has only one pending request. Why can the histogram miss the experience of the other arrival slots?

### Exercise 10 — Dataset Skew

Production has tenant `t001` accounting for 60% of traffic, while the test dataset distributes evenly across 200 tenants. Which hot spots might the benchmark miss?

### Exercise 11 — Lab Seed

Run the section 7 seed script on a lab MongoDB instance and verify 12,000 listings and 16 counters. Explain the `upsert` mechanism and why the filter includes `labTag`.

### Exercise 12 — Checking Distribution

Run the aggregation grouped by `tenantId`/`city`/`status`. Do the active ratio and tenant concentration match the initial assumptions?

### Exercise 13 — Explain Feed

Run `explain("executionStats")` on Query A. Record `winningPlan`, keys examined, docs examined, and `nReturned`. When should you test a new compound index?

### Exercise 14 — Sort

Compare feed sorted by `createdAt` vs. sorted by `rentMillion`. With the existing indexes, what differences in sort stage and latency may appear?

### Exercise 15 — Point Lookup

Run Query B with several IDs. Why does a point lookup generally have a different cost profile from Query A, and why can lookup p99 not replace the feed SLO?

### Exercise 16 — Aggregation

Run Query C and explain the `$match`/`$group` stages. If latency increases when running concurrently with feed, which CPU/cache/IO metrics should you inspect?

### Exercise 17 — Write Concern

Compare two identical write workloads where one uses `w:1` and the other uses `w:"majority"`. Why can you not attribute all differences to indexes?

### Exercise 18 — Node.js Benchmark

Run the read-only closed-loop script in the lab. Record sample counts per operation, p50/p95/p99, errors, and throughput. Why are these numbers not production results?

### Exercise 19 — Mixed Read/Write

In the lab, enable `BENCH362_ALLOW_WRITES=true` and compare against read-only. What differences in contention, journaling, and write rate may emerge?

### Exercise 20 — Warmup

Compare the first run on a cold cache with a run after warmup. Why must you never compare a cold baseline with a warm post-change run to claim an optimization?

### Exercise 21 — Timeouts

A workload has 10,000 requests, 9,700 successes, and 300 timeouts. Calculate the error rate. If successful p99 is 100 ms, can you declare the system fully meets its SLO?

### Exercise 22 — In-Flight Requests

At the end of the measurement window, 50 requests remain unfinished, many hanging for a long time. How would you define the sample window/drain policy so tail latency is not hidden?

### Exercise 23 — Pool Queueing

Server query execution is around 5 ms, yet client p99 is 500 ms. Propose how to measure connection pool checkout wait, network time, and service time.

### Exercise 24 — Generator Capacity

Load generator CPU is at 100% and fails to send the full offered RPS while MongoDB CPU is 35%. Can you conclude the database can handle higher load? How should the experiment be changed?

### Exercise 25 — Deep Pagination

Compare offset `skip(100000)` against keyset pagination with the same sort and page size. Which metrics prove improvement? What conditions must be held constant?

### Exercise 26 — Read/Write Trade-Off

A new index cuts feed p99 from 300 to 220 ms but raises update p99 from 180 to 260 ms. Which SLOs determine whether to keep the index?

### Exercise 27 — Computing RPS

30 minutes of steady-state yields 360,000 successful operations. Compute the average successful throughput. If the load generator targeted 250 RPS, was the offered target met?

### Exercise 28 — Windowed Statistics

A test has 25 normal minutes and a 5-minute disk spike. Why are both overall p99 and per-minute p99 time series needed? Can you average per-minute p99s as the overall p99?

### Exercise 29 — Dashboard

Design a dashboard with offered RPS, success RPS, error rate, p50/p95/p99 per operation, pool wait, WiredTiger cache, disk latency, CPU, and replication lag.

### Exercise 30 — SLO Pass/Fail

Design PASS criteria for SearchFeed at 140 offered RPS, p95 ≤ 150 ms, p99 ≤ 300 ms, error ≤ 0.2%, with warmup and steady-state. When must the verdict be INCONCLUSIVE rather than PASS?

### Exercise 31 — Investigating p99

At 200 RPS, p50 is unchanged while p99 climbs from 90 to 800 ms. Order your investigation steps across client, pool, slow queries, disk, GC, background jobs, and failover.

### Exercise 32 — Peak Plan

Production normally runs at 200 RPS but reaches 650 RPS during a 5-minute peak. Design a ramp/peak/spike test with guardrails to find saturation and recovery time.

### Exercise 33 — Before/After Report

Draft a benchmark report documenting database/driver versions, dataset, indexes, mix, concurrency/arrival rate, warmup, duration, sample counts, histograms, p50/p95/p99, errors, throughput, and evidence-backed conclusions.

### Exercise 34 — Capstone

A product has 10 million listings, multiple tenants, 65% SearchFeed, 20% Detail, 10% Summary, 5% Write, targeting 250 ms feed p99 at 500 RPS. Design the complete workflow: representative synthetic data, query shapes, indexes, open-loop generator, warmup, scenarios, SLIs/SLOs, metrics, safe test environment, and optimization decision process.

## 24. References

- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/).
- MongoDB Manual — [Query Plans](https://www.mongodb.com/docs/manual/core/query-plans/).
- MongoDB Manual — [Performance Best Practices](https://www.mongodb.com/docs/manual/administration/analyzing-mongodb-performance/).
- MongoDB Manual — [Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/).
- MongoDB Manual — [serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/).
- MongoDB Manual — [currentOp](https://www.mongodb.com/docs/manual/reference/command/currentOp/).
- MongoDB Manual — [WiredTiger Storage Engine](https://www.mongodb.com/docs/manual/core/wiredtiger/).
- MongoDB Manual — [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/).
- MongoDB Manual — [Indexing Strategies](https://www.mongodb.com/docs/manual/applications/indexes/).
- MongoDB Node.js Driver — [Monitor Commands](https://www.mongodb.com/docs/drivers/node/current/monitoring-and-logging/monitoring/).
- MongoDB Node.js Driver — [Connection Pools](https://www.mongodb.com/docs/drivers/node/current/connect/connection-options/connection-pools/).
- MongoDB Atlas — [Monitor Database Deployment Metrics](https://www.mongodb.com/docs/atlas/monitor-cluster-metrics/).
- Brendan Gregg — [USE Method: Utilization, Saturation, Errors](https://www.brendangregg.com/usemethod.html).
- Gil Tene — [How NOT to Measure Latency](https://www.youtube.com/watch?v=lJ8ydIuPFeU) (discussion on coordinated omission and tail latency).

**Conclusion:** A MongoDB optimization study is only trustworthy if the **load test represents production behavior** across data, query shape, read/write ratio, concurrency, hot/cold distribution, and arrival rate. **p50** describes the typical experience, **p95** reveals the more frequent tail, and **p99** uncovers the slowest requests in the top 1%; yet all must be accompanied by **sample count, percentile method, measurement duration, throughput, and error rate**. Use **explain** to understand queries, **driver/API metrics** to measure experience, and **server/cache/disk/replication metrics** to locate bottlenecks; avoid **coordinated omission**, averaging percentiles, and unfair before/after comparisons. The goal is not a pretty chart, but proving the system **meets p50/p95/p99 SLOs at the true offered load, with controlled errors and repeatability**.
