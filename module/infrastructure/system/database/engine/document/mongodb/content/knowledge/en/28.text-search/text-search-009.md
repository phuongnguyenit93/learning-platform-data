# Search Index Update Lag, Monitoring, and Result Quality Evaluation in MongoDB

## 1. Opening Scenario: Product Updated, Yet Search Still Misses It

An e-commerce application stores products in MongoDB. A staff member updates a product title:

```javascript
db.products.updateOne(
  { _id: productId },
  {
    $set: {
      title: "Tai nghe Bluetooth chống ồn",
      status: "ACTIVE",
      updatedAt: new Date()
    },
    $inc: { version: 1 }
  }
);
```

The update API succeeds. When the staff member opens the product detail page backed by `findOne({_id: productId})` on the primary, the new name appears immediately. Yet searching **"chống ồn"** via MongoDB Search `$search` still does not return the product. A few seconds later, with no further changes, the product appears in search results.

This illustrates **search indexing lag**. Specifically with **MongoDB Search** (formerly commonly called *Atlas Search*), writing data to MongoDB and making that change searchable inside the search index are **two separate milestones**.

Conceptual flow:

```text
Application writes product
          |
          v
MongoDB collection
   receives write
          |
          | changes synced to search service
          v
Search index ingestion
          |
          | tokenize, update search structures,
          | refresh queryable state
          v
Search index sees new data
          |
          v
$search API returns matching results
```

Between **write acknowledgment** and **search visibility**, a lag window can exist. When write throughput spikes, analyzers/index definitions change, or a Search component lacks resources, that lag can grow.

This lesson, **"Search Index Update Lag, Monitoring, and Result Quality Evaluation"**, belongs to MongoDB's **Text Search** chapter. Afterward, you will be able to:

1. Distinguish **MongoDB Search indexes** from MongoDB **legacy text indexes**.
2. Understand the stages producing indexing lag and why a majority write does not guarantee immediate search visibility.
3. Design **freshness** measurements using test documents with stable unique identifiers.
4. Monitor index status, sync lag, queries, resource load, and error rates.
5. Distinguish **misses due to indexing lag** from analyzer, mapping, query, or authorization bugs.
6. Evaluate result relevance using labeled query sets, `Precision@K`, `Recall@K`, `MRR`, and `nDCG`.
7. Evaluate Vietnamese text, diacritics, compound words, synonyms, autocomplete, and realistic keyword cases.
8. Test ranking improvements offline, via canary rollouts, and with A/B tests.
9. Roll out new search indexes safely with observability and rollback plans.
10. Practice MongoDB Search on an authorized test environment.

## 2. First, Distinguish Two Types of "Text Search Index"

MongoDB provides multiple text-search mechanisms. Whenever referring to a "search index," specify which engine is used.

### 2.1. Native MongoDB Text Index and the `$text` Operator

MongoDB supports built-in **text indexes** integrated into the database's native indexing layer:

```javascript
db.products.createIndex({
  title: "text",
  description: "text"
});

db.products.find({
  $text: {
    $search: "tai nghe"
  }
});
```

This is **native text search** using `$text`. The index lives inside the database/index structures on MongoDB members. Data writes and index updates on the writing node follow MongoDB's standard index maintenance; when reading from a secondary, **replication lag** still applies.

With `$text`, freshness troubleshooting focuses on:

- Did the write succeed, and is the query reading the right node/cluster?
- Is the secondary lagging?
- Was the text index created on the right fields?
- Are the text index's language, stemming, stop words, and tokenizer suitable?
- Does the query use valid `$text` syntax and `textScore` projection?

Do not project the asynchronous MongoDB Search service refresh model onto every `$text` query.

### 2.2. MongoDB Search Index and the `$search` Stage

**MongoDB Search** delivers advanced full-text search over a dedicated search index infrastructure, providing capabilities such as:

- Analyzer-based word/token processing;
- Relevance scoring;
- Compound queries and dedicated search operators;
- Synonyms, fuzzy search, or autocomplete when configured;
- Highlighting, facets, and version-dependent features;
- Composing search seamlessly with aggregation pipelines.

Example:

```javascript
db.products.aggregate([
  {
    $search: {
      index: "products_text_v1",
      text: {
        query: "tai nghe chống ồn",
        path: ["title", "description"]
      }
    }
  },
  { $limit: 10 },
  {
    $project: {
      title: 1,
      description: 1,
      score: { $meta: "searchScore" }
    }
  }
]);
```

MongoDB Search synchronizes and indexes data **asynchronously** relative to collection writes. Therefore, a **write acknowledgment** does not guarantee `$search` immediately sees the new content.

### 2.3. Comparing the Two Mechanisms

| Aspect | Native `$text` + Text Index | MongoDB Search `$search` |
| --- | --- | --- |
| Structure | Database-integrated index | Separately managed Search index |
| Query syntax | `find({$text: ...})` | `$search` aggregation stage |
| Index update on write | Follows database node index mechanics | Asynchronous search sync/indexing |
| Lag to observe | Write ACK, secondary replication, query | All relevant factors plus **search index visibility** |
| Analyzers and ranking | Traditional text search capabilities | Rich analyzers, scoring, facets, autocomplete |
| Relevance score | `{$meta:"textScore"}` | `{$meta:"searchScore"}` |
| Index management | `createIndex()` / `getIndexes()` | `createSearchIndex()` / `getSearchIndexes()` or equivalent |
| Deployment requirement | Any MongoDB supporting text indexes | Deployment with MongoDB Search enabled |

Both mechanisms can coexist on one collection, yet they **do not share index definitions**. Running `createIndex({title:"text"})` **does not create** a MongoDB Search index for `$search`.

### 2.4. Do Not Confuse MongoDB Search with MongoDB Vector Search

MongoDB also offers vector/semantic search, which involves embedding models, vector indexes, and its own sync mechanics. Freshness and ranking principles overlap at a high level, but **approximate nearest-neighbor recall**, embedding drift, and semantic evaluation add separate concerns.

This lesson focuses on **text search**, MongoDB Search, and native `$text` comparisons—never assume every search index is a vector index.

## 3. What Is Search Indexing Lag Actually Measuring?

### 3.1. Timestamps Along an Update Lifecycle

An update passes through several stages:

```text
T0: Client sends product update
T1: MongoDB acknowledges write under chosen write concern
T2: Search component receives/detects change to index
T3: Change is processed into search index structures
T4: New $search query reflects updated membership/ranking
T5: Application UI or cache displays new results
```

Not every monitoring stack exposes `T2`, `T3`, or `T4` directly. Distinguish **what you want to measure** from **what you can actually observe**.

Latencies:

\[
\text{Write latency} = T_1 - T_0
\]

\[
\text{Search visibility lag} \approx T_4 - T_1
\]

\[
\text{User-observed freshness lag} \approx T_5 - T_1
\]

If the UI caches responses for 30 seconds, `T5 - T1` will be large even if the Search index updated instantly. Never blame MongoDB Search for all user-observed staleness.

### 3.2. Why Do Search Indexes Update Asynchronously?

A search engine typically must:

1. Detect inserted, updated, or deleted documents.
2. Read mapped field contents.
3. Normalize strings, tokenize, and apply analyzers, stemming, or synonyms.
4. Update inverted index and search structures.
5. Manage segments/memory and publish changes to queryable state.
6. Keep sync aligned with search configuration, write traffic, and topology.

These steps do not have to finish before the driver receives a MongoDB write acknowledgment. That is an **architectural trade-off** for rich search capabilities, not evidence of a broken database.

### 3.3. Three Distinct Lag Scenarios

**Insert lag:** a new document exists in MongoDB, yet `$search` does not return it for matching keywords yet.

**Update lag:** a document changes from `"Tai nghe có dây"` to `"Tai nghe Bluetooth"`, yet the index still holds old tokens. Queries for the new term miss it, while queries for the old term may briefly still match it.

**Delete or unpublish lag:** a document is deleted or set to `status: "INACTIVE"`, yet the index has not processed the change; search hits and source-collection reads may disagree briefly depending on how results are fetched.

The third case is especially critical: whenever **access permissions, product recalls, or sensitive visibility states** depend on fresh state, never rely solely on an asynchronously updated search index as the final security gate.

### 3.4. "Stale Membership" vs. "Stale Document"

Suppose a document:

```javascript
{
  _id: "P-10",
  title: "Tai nghe có dây",
  version: 3
}
```

is updated to:

```javascript
{
  _id: "P-10",
  title: "Tai nghe Bluetooth",
  version: 4
}
```

Before the search index syncs:

- Querying `"Bluetooth"` may **miss** the document.
- Querying `"có dây"` may **still match** it.
- Under certain `$search` execution paths, returned fields fetched from the MongoDB collection reflect the newer document even though index tokens/scores matched the older version. Results can therefore **match old terms while displaying new fields**.

When testing freshness, verify **index membership and scoring**, not merely `fullDocument.title` in the returned payload.

### 3.5. `READY` Index Status Does Not Mean Zero Lag

Search index states such as `building`/`ready`/`queryable` describe build readiness per your version's admin interface. A Search index can be queryable while **brand-new writes are still queued to become visible**.

False conclusion:

> "Search index status = READY, so every newly written document is guaranteed searchable immediately."

Accurate conclusion:

> "The index is eligible to serve queries; we still must monitor freshness for changing data."

## 4. When Does Indexing Lag Grow?

### 4.1. High Write Volume or Heavy Indexed-Field Updates

A bulk import of 2 million products creates heavy change volume for Search to ingest:

```text
MongoDB write throughput
          |
          v
Search indexing workload
          |
          +-- tokenization
          +-- index segment updates
          +-- delete/update bookkeeping
          +-- refresh/query workload
```

If sustained change rates exceed indexing capacity, backlogs and visibility lag grow. A brief spike during a burst differs from a **continuously growing backlog**.

### 4.2. Complex Mappings and Analyzers

Dynamic fields with multiple types, many analyzers, autocomplete/n-grams, huge synonym maps, or indexing excessive fields make Search index builds and updates heavier.

"More indexed fields" does not always mean better queries. Dynamic mapping across whole documents bloats indexes, increases cost, and pulls unneeded fields into Search.

### 4.3. Rebuilds or Index Definition Changes

Creating a new index or editing an index definition may trigger a rebuild. During this window:

- The new index may not be queryable yet.
- Resource consumption rises.
- Build progress/status transitions occur.
- Analyzer changes can alter rankings even when source data is unchanged.

Never mistake an active index build for a broken legacy index; track active deployment changes.

### 4.4. Resource-Constrained Search Nodes

On deployments with dedicated Search infrastructure, inspect:

- Sustained CPU saturation.
- Memory or cache pressure.
- Disk capacity, IOPS, and read/write latency.
- Search index size and segment/merge activity.
- Network health between database and Search components.
- Concurrent search query volume.

Exact metric names depend on Atlas/MongoDB Search deployment, version, tier, and dashboard. Never invent a metric like `replicationLagMs` assuming every cluster exposes it.

### 4.5. Expensive Queries Competing for Resources

Overly broad fuzzy queries, wildcards, multi-field autocomplete, low-selectivity filters, or huge `$searchMeta` total counts elevate query cost.

Depending on architecture, indexing and querying contend for shared resources; monitor **both indexing freshness and query latency**. Looking at QPS alone never proves spare capacity.

### 4.6. Misconfiguration or Sync Failure

If a document stays missing for many minutes, do not assume it is "normal lag":

- Field is unmapped.
- BSON data type mismatches the mapping.
- Search index is not queryable or failed to build.
- Query references the wrong index name.
- Analyzer strips or transforms tokens unexpectedly.
- `tenant`/`status` filters exclude the document.
- Data was written to the wrong database or collection.
- Query hits a stale cache or wrong environment.
- Sync error or infrastructure limit prevents Search from catching up.

Follow a structured **triage workflow** before scaling capacity blindly.

## 5. Result Freshness and Read–Write Consistency

### 5.1. Write Acknowledgment Is Not Search Acknowledgment

Example:

```javascript
const result = db.products.updateOne(
  { _id: productId },
  { $set: { title: "Máy pha cà phê mini" } },
  { writeConcern: { w: "majority" } }
);
```

Succeeding with `w:"majority"` satisfies replica-set durability rules. It **does not mean the MongoDB Search index has finished indexing the write**.

Separate two contracts:

- **Database durability / commit:** how MongoDB confirms persistence.
- **Search freshness:** whether the change is discoverable via `$search`.

Changing write concern does not turn Search into synchronous indexing.

### 5.2. "Read-Your-Writes" on Search APIs

A user creates a product and searches for it right away. Three design options exist depending on required guarantees:

**Option A — Redirect by ID to the database:** return `productId` after creation and load the detail view via `findOne` from the source. The search page can indicate that new items take a moment to appear in search.

**Option B — Bounded Search polling:** after writing, poll a targeted query with a strict **deadline and backoff** until the document appears or fall back to an "indexing in progress" state. This is application-level waiting, not an instant-visibility guarantee.

**Option C — Result merging:** show the newly created item from the database alongside search hits, deduplicating carefully and avoiding faking a relevance score for it.

### 5.3. Business Flows That Must Never Depend Solely on Search Freshness

Never rely exclusively on `$search` to:

- Check latest access permissions;
- Enforce unique SKUs or usernames;
- Deduct inventory or quotas;
- Confirm payment status;
- Gate sensitive deletions;
- Enforce "locked/disabled" state right after revoking access.

For those invariants, use **MongoDB queries, atomic updates, unique indexes, and transactions**, enforcing authorization against authoritative source data.

Use Search to **retrieve candidates and rank them**, never as the transactional ledger for strong-consistency decisions.

### 5.4. Re-Check Permissions When Search Indexes Can Be Stale

Suppose a document switches from `visibility:"PUBLIC"` to `"PRIVATE"`. During the lag window, Search may still hold the old state.

Running only:

```javascript
$search: {
  compound: {
    filter: [
      { equals: { path: "visibility", value: "PUBLIC" } }
    ]
  }
}
```

and returning results without verification exposes **stale index state**.

For sensitive content:

1. Use Search filters to narrow candidates.
2. Verify access permissions against the **authoritative** MongoDB source with appropriate consistency.
3. Return only documents the user is currently authorized to view.
4. Never expose sensitive snippets in highlights, facets, or logs **before authorization is verified**.

This is a **security requirement**, not merely a UX lag concern.

## 6. Designing Clear, Observable Search Indexes

### 6.1. Sample Index Definition

A MongoDB Search index named `products_text_v1`:

```javascript
{
  mappings: {
    dynamic: false,
    fields: {
      title: {
        type: "string",
        analyzer: "lucene.standard"
      },
      description: {
        type: "string",
        analyzer: "lucene.standard"
      },
      tenantId: {
        type: "token"
      },
      status: {
        type: "token"
      }
    }
  }
}
```

Here:

- `title` and `description` support `text` queries.
- `tenantId` and `status` use `token` mapping for **exact-value matching** via `equals` in supported MongoDB Search versions.
- `dynamic:false` indexes only declared fields, preventing unnecessary field indexing.

Mapping types, analyzers, and operators vary across releases. If targeting older versions without `token` support in this form, verify compatible mappings before deploying—never swap `token` to `string` assuming `equals` keeps identical semantics.

### 6.2. Querying with the Right Index and Filters

```javascript
db.products.aggregate([
  {
    $search: {
      index: "products_text_v1",
      compound: {
        must: [
          {
            text: {
              query: "tai nghe bluetooth",
              path: ["title", "description"]
            }
          }
        ],
        filter: [
          {
            equals: {
              path: "tenantId",
              value: "TENANT-A"
            }
          },
          {
            equals: {
              path: "status",
              value: "ACTIVE"
            }
          }
        ]
      }
    }
  },
  { $limit: 10 },
  {
    $project: {
      _id: 1,
      title: 1,
      status: 1,
      score: { $meta: "searchScore" }
    }
  }
]);
```

`compound.filter` narrows candidates without contributing to relevance scores; `compound.must` drives matching and scoring. Depending on needs, combine `should` and `minimumShouldMatch`.

**Never** take `tenantId` from unauthenticated user input. This example shows query syntax, not authentication logic.

### 6.3. Checking Index Status in `mongosh`

On a MongoDB Search-enabled deployment:

```javascript
const products = db.getSiblingDB("shop").getCollection("products");

printjson(products.getSearchIndexes());
```

Or for a named index:

```javascript
printjson(
  products.getSearchIndexes("products_text_v1")
);
```

Useful fields to inspect:

- Index name and type;
- Active definition and mappings;
- Reported build/indexing status;
- Queryable state;
- Any build or definition errors;
- Definition version where supported.

**Never assume response field names are identical across all Atlas/MongoDB Search versions.** And remember: `READY`/queryable status never replaces per-update freshness probing.

### 6.4. Creating and Replacing Indexes Safely

In `mongosh` on supported deployments:

```javascript
db.products.createSearchIndex(
  "products_text_v1",
  {
    mappings: {
      dynamic: false,
      fields: {
        title: { type: "string" },
        description: { type: "string" }
      }
    }
  }
);
```

The command returns before the new index finishes building; monitor status rather than shifting traffic right away.

In production:

- Never run `createSearchIndex()` on unsupported environments.
- Never overwrite an active index name without a migration plan.
- Never `dropSearchIndex()` an old index before validating the replacement.
- Use versioned names (`v1`, `v2`) for safe comparison and rollback when quotas allow.
- Account for the storage/compute cost of running two indexes concurrently during cutover.

## 7. Measuring "Has the Search Index Seen the New Write?" with Probes

### 7.1. Define the Measurement Before Writing Scripts

A reliable probe records:

- A stable `writeId` or `probeId`.
- Expected `documentId` and `version`.
- Timestamp when the app received **write acknowledgment**.
- A query uniquely selecting that document once indexed.
- Timestamp of the first observation matching the condition.
- Polling interval, timeout, and any intermediate errors.

Then:

\[
\text{Observed visibility lag}
=
\text{First observed visible time}
-
\text{Write acknowledged time}
\]

This is **polling-observed lag**. It can **exceed** the true moment data became visible by up to one polling interval plus network/query time; it is not an internal engine timestamp.

### 7.2. Never Measure with Overly Generic Queries

Inserting `"iPhone"` and searching `"iPhone"` returns thousands of pre-existing hits—getting a hit **proves nothing about whether the new document is indexed**.

Use a **unique marker** and a predicate targeting that exact document:

```javascript
{
  _id: probeId,
  runId: "row308-unique-run",
  probeToken: "probe-unique-identifier",
  title: "Search freshness check",
  version: 1
}
```

Count **insert visibility** only when Search returns that exact `probeId`/token. Never rely on general hit counts or arbitrary rankings.

### 7.3. Measure Three Mutation Types

A thorough probe suite tests:

**Insert visibility:** insert a document with a unique token and poll until Search returns it.

**Update visibility:** change the token from `probe-old-XYZ` to `probe-new-XYZ`, poll until the new query matches, and optionally check when the old query stops matching.

**Delete visibility:** delete the document and poll until Search stops returning it. Distinguish **index membership** from post-delete document fetches—an empty result early on does not prove postings were purged without proper checks.

Testing all three catches update/delete pipeline regressions that insert-only probes miss.

### 7.4. Track a Freshness SLO Over Time

Illustrative internal SLO (**example only**):

```text
99% of ACTIVE product changes
must be searchable within 15 seconds
after majority write acknowledgment,
measured via unique-ID probes on the same index stream.
```

From this, track:

- `p50_visibility_lag_seconds`.
- `p95_visibility_lag_seconds`.
- `p99_visibility_lag_seconds`.
- Share of probes missing the deadline.
- Lag broken down by insert, update, and delete.
- Lag by region, collection, index version, or product slice.

**The 15-second threshold is an illustrative product contract, not a MongoDB default SLA.** Choose targets based on product needs, traffic, and empirical measurements.

### 7.5. Account for Probe Failures Caused by Other Errors

A probe can fail due to:

- Index still building.
- Broken query mapping.
- Probe worker/logging failure.
- Unrecorded write acknowledgment timestamp.
- MongoDB Search timeout.
- Analyzer/token mismatch.
- Unindexed token field.

Never report "lag > deadline" when the probe query itself failed. Classify **failed query**, **mapping mismatch**, **index unavailable**, and **valid query with document not yet visible** separately.

## 8. Monitoring Search Indexes: Core Dimensions

### 8.1. Index Lifecycle and Health

Monitor:

- Building, queryable, errored, or deleted index states.
- Whether the active index definition matches the deployed version.
- Build/rebuild duration.
- Index creation/update error counts.
- Search service/node availability via supported dashboards.
- Storage and compute headroom for index data.

An index can report `READY` while delivering poor results due to a bad analyzer—monitor **both index health and query quality**.

### 8.2. Freshness

Monitor:

- Write-to-search visibility time;
- Rate of inserts/updates/deletes exceeding deadlines;
- Collection write rate vs. search catch-up rate where exposed;
- Search backlog/lag metrics exposed by Atlas or deployment telemetry;
- Probe timeout counts;
- Index builds/rebuilds coinciding with lag spikes;
- Divergence between MongoDB source counts and searchable counts.

Whenever tools label a metric "indexing lag" or "replication lag," verify its **exact definition**: lag between MongoDB and Search differs completely from replica-set secondary replication lag.

### 8.3. Query Latency and Throughput

Monitor:

- QPS by query class.
- p50/p95/p99 query latency.
- `$search` timeout and error rates.
- Zero-result rates.
- Average results returned per query.
- Traffic split across fuzzy, autocomplete, and index versions.
- End-to-end API latency including network, authorization, caching, and querying.

Fast queries returning irrelevant results remain a poor user experience. Conversely, great rankings with terrible p99 latency miss user SLOs.

### 8.4. Cost and Resources

Inspect alongside freshness and latency:

| Dimension | Signals to Watch | Diagnostic Questions |
| --- | --- | --- |
| CPU / search nodes | Sustained high CPU | Query complexity or indexing burst? |
| Memory / cache | Memory pressure, evictions, throttling | Oversized index or abnormal workload? |
| Disk / storage | Growing size, I/O latency | Overly broad mapping, rebuild, or index growth? |
| Network | RTT, bandwidth, errors | Is change-sync traffic to Search bottlenecked? |
| Index builds | Build time, status | Is another index build running concurrently? |
| Database writes | Insert/update/delete rate | Did a batch import queue up indexing? |
| API caching | Hit rate, cache TTL/age | Is stale UI caused by cache or Search index? |

Never assume every metric name exists on every MongoDB plan. On managed deployments use **Atlas metrics/logs**; on self-managed Search use corresponding telemetry.

### 8.5. Useful Custom Metrics

A service can export:

```text
search_probe_visibility_seconds
search_probe_timeout_total
search_probe_query_error_total
search_queries_total
search_query_latency_seconds
search_no_results_total
search_index_version_traffic_total
search_relevance_feedback_total
search_result_clicks_total
search_sessions_success_total
```

These are **custom suggested names**, not built-in MongoDB metric fields. Attach low-cardinality labels like `index_version`, `query_class`, and `region`—never put raw user queries or `productId` in Prometheus labels where cardinality explodes.

## 9. Designing Operational Dashboards and Alerts

### 9.1. A Meaningful Dashboard Layout

Place correlated charts side by side:

```text
+-----------------------+-----------------------+
| Search freshness p95  | Search freshness p99  |
+-----------------------+-----------------------+
| Search query QPS      | Search latency p95    |
+-----------------------+-----------------------+
| Index status/build    | Query error rate      |
+-----------------------+-----------------------+
| No-results rate       | Search success rate   |
+-----------------------+-----------------------+
| CPU / Disk / Memory   | DB write throughput   |
+-----------------------+-----------------------+
```

When p95 freshness rises alongside a write-throughput spike, suspect an indexing backlog. When query latency climbs while freshness stays normal, focus on query complexity, caching, and query compute.

### 9.2. Alert on Symptoms, Not Just `READY` Status

Sample alert matrix:

| Illustrative Condition | Business-Dependent Priority | Response Direction |
| --- | --- | --- |
| Search index not queryable | High if serving primary traffic | Check build/errors; engage fallback |
| p95 visibility breaches freshness SLO | Freshness degradation alert | Triage write load and indexing |
| p99 query latency breaches API SLO | UX degradation alert | Inspect query shapes and capacity |
| Zero-results spike after analyzer deploy | Relevance regression risk | Compare index versions; replay queries |
| Query errors/timeouts spike | Availability risk | Triage Search nodes and command errors |
| Probes stop emitting samples | Blind monitoring | Repair probe; never treat stale zeros as healthy |
| Offline relevance drops below threshold | Quality risk | Hold rollout or roll back index version |

Configure **evaluation windows**, minimum sample counts, and grouping to avoid paging on transient single-probe network blips.

### 9.3. Composite Scorecards

For product stakeholders, maintain a balanced scorecard:

| Dimension | Metric | Question |
| --- | --- | --- |
| Freshness | p95/p99 indexing visibility | Are updated products searchable quickly? |
| Availability | Query success rate | Is Search reliably up? |
| Latency | p95 API search duration | Are users waiting too long? |
| Retrieval quality | `Recall@K`, no-results rate | Are valid products being missed? |
| Ranking quality | `MRR`, `nDCG@K` | Do the best hits rank near the top? |
| Product outcome | Click success, conversion, reformulation | Are users accomplishing their goals? |
| Cost | Resources per QPS / index size | Is cost efficiency acceptable? |

Never collapse everything into a single opaque "search health score" where faster latency hides collapsing relevance.

## 10. Investigation Runbook When Search Misses a New Document

### 10.1. Step 1 — Verify Source Data

First, read the document by ID from the source MongoDB collection:

```javascript
db.products.findOne(
  { _id: productId },
  { title: 1, status: 1, tenantId: 1, version: 1, updatedAt: 1 }
);
```

Check:

1. Did the write actually succeed?
2. What did `matchedCount` / `modifiedCount` / `upsertedId` report?
3. Is the document in the expected database and collection?
4. Do `status`, `tenantId`, or scope filters exclude it?
5. Did another worker overwrite it afterward?

If MongoDB itself lacks the new title, it is not Search lag.

### 10.2. Step 2 — Verify Index Name and Mappings

```javascript
printjson(
  db.products.getSearchIndexes()
);
```

Check which index the API queries, which fields are mapped, and index status. If the source field is `productName` while Search maps only `title` under `dynamic:false`, searching `title` will miss it.

After an analyzer or definition change, verify whether traffic points to the old or new index version.

### 10.3. Step 3 — Simplify the Query

Replace complex compound queries with a minimal `text` query:

```javascript
db.products.aggregate([
  {
    $search: {
      index: "products_text_v1",
      text: {
        query: "bluetooth",
        path: "title"
      }
    }
  },
  { $limit: 10 },
  {
    $project: {
      title: 1,
      score: { $meta: "searchScore" }
    }
  }
]);
```

Once the minimal query works, add clauses back incrementally:

- Tenant filter;
- Status filter;
- Additional search paths;
- Fuzzy / synonyms;
- Custom scoring;
- Projection and pagination.

If the minimal query finds the document while the full query misses it, the bug is **mapping, filter, or ranking logic**, not lag.

### 10.4. Step 4 — Compare Timestamps and Progress

Compare:

```text
Write acknowledgment:  10:00:00.000
Probe first visible:   10:00:03.500
Observed lag:          3.5 seconds
```

These are sample numbers. For real incidents, collect:

- Document ID and version.
- Index name.
- Executed query (scrubbed of sensitive data).
- Server/application timestamps.
- Index build/sync progress and queryable state.
- Multi-sample probe results.

Without document-specific measurements, vague reports like "a user didn't see it" cannot distinguish lag from analyzer mismatches.

### 10.5. Step 5 — Separate Search Lag from Cache/UI Lag

Inspect:

- CDN or HTTP response caches.
- Redis / application-level caches.
- Browser cache or frontend state.
- Page-1 limits and score shifts.
- Query-param differences between admin and user views.
- Time zones, status filters, and effective dates.

If `$search` in `mongosh` returns the document while the UI still misses it, debug layers downstream of Search.

### 10.6. Triage Matrix

| Observation | Likely Cause | Next Action |
| --- | --- | --- |
| `findOne` misses the update | Write never landed or reading wrong source | Check write result, namespace, and node |
| `findOne` sees it; `$search` misses briefly then finds it | Search indexing lag | Measure visibility and backlog |
| `$search` never finds a field | Unmapped field, wrong type, or analyzer mismatch | Inspect index definition and schema |
| Minimal query hits; filtered query misses | Filter/tenant/status bug or stale index state | Verify filter semantics and authoritative source |
| Index not queryable | Build, error, or deployment issue | Check status and runbook |
| `mongosh` finds it; UI misses it | Caching, pagination, or API mapping | Trace end-to-end |
| Old keyword matches yet new title displays | Stale index membership, fresher doc fetch | Run update probe and check version |
| Accented Vietnamese misses | Analyzer, Unicode, or tokenization | Test normalization and query pairs |
| Rankings shift post-deploy | Changed definition, analyzer, or boosts | Compare offline judgments and canary metrics |
| All queries slow while freshness is normal | Index, query complexity, or capacity pressure | Inspect explain, QPS, and resources |

## 11. Result Quality: What Does "Good Search" Mean?

### 11.1. No Single Metric Captures Everything

A search system can:

- Respond ultra-fast with irrelevant documents;
- Find the right documents buried on page 5;
- Excel on exact spelling while failing on typos;
- Work well in English while breaking on Vietnamese compounds;
- Rank accurately yet lag tens of seconds behind fresh writes;
- Show high CTR simply because users always click result #1 regardless of quality.

Evaluation therefore spans five pillars:

1. **Retrieval:** does the system find relevant matches?
2. **Ranking:** do the best matches appear near the top?
3. **Freshness:** how quickly does search reflect recent changes?
4. **Reliability / latency:** do queries meet response deadlines?
5. **Business outcome:** do users achieve their goal?

### 11.2. Relevance Is Context-Dependent

For query `"tai nghe"`:

- For a shopper: matching headphone products are relevant;
- For a support agent: headphone warranty guides are relevant;
- For warehouse staff: SKU inventory records are relevant.

An evaluation dataset must specify:

- User intent;
- Language and locale;
- Document type;
- Business filters (stock, active, tenant);
- Expected relevance scale;
- Data snapshot timestamp;
- Query class (exact, broad, long-tail, typo, synonym).

There is no "universal relevance score" without first defining the task.

### 11.3. Binary vs. Graded Relevance Labels

**Binary labels**:

```text
0 = not relevant
1 = relevant
```

**Graded labels**:

```text
0 = completely irrelevant
1 = weakly relevant
2 = fairly relevant
3 = highly relevant / exact intent
```

Graded labels are ideal for ranking metrics such as **nDCG**, because they reward placing exact hits above loosely related hits.

Provide clear annotator guidelines, audit inter-annotator disagreement, and involve domain experts for specialized queries.

## 12. Building an Offline Relevance Evaluation Suite

### 12.1. Representative Query Mix

An evaluation suite should cover diverse groups:

| Group | Example | What to Verify |
| --- | --- | --- |
| Exact name | `"tai nghe bluetooth"` | Exact title matching |
| Multi-word | `"tai nghe bluetooth chống ồn"` | Term co-occurrence and ranking |
| Synonyms | `"headphone không dây"` | Synonyms and mixed languages |
| Typos | `"bluetooh"` | Bounded fuzzy matching |
| Accented / unaccented | `"may loc khong khi"` / `"máy lọc không khí"` | Unicode and analyzers |
| Product code | `"WH-1000XM"` | Exact / structured token matching |
| Rare technical terms | `"màng lọc HEPA H13"` | Precision on rare tokens |
| Broad queries | `"máy"` | Relevance, facets, pagination |
| Zero-hit queries | `"sản phẩm không tồn tại 308XYZ"` | Correct empty state and suggestions |
| Multi-tenant | Same keyword across two tenants | Isolation and authorization |
| Newly added products | Unique token written moments ago | Freshness |
| Discontinued products | Previously matching item now `INACTIVE` | Indexing lag and filter correctness |

Never build a test set exclusively from the top 10 head queries. **Long-tail queries**, typos, and specific intents uncover far more bugs.

### 12.2. Golden Dataset

Example stored judgment record:

```json
{
  "queryId": "Q-001",
  "query": "tai nghe bluetooth",
  "tenantContext": "TENANT-TEST",
  "locale": "vi-VN",
  "intent": "find_product",
  "judgments": [
    { "documentId": "P-001", "relevance": 3 },
    { "documentId": "P-002", "relevance": 2 },
    { "documentId": "P-003", "relevance": 0 }
  ]
}
```

Best practices:

- Pin or snapshot the test corpus.
- Record index version, query version, and analyzer version.
- Record `ACTIVE`/in-stock status at judgment time.
- Distinguish **unjudged** documents from documents **judged irrelevant**.
- Strip real customer PII from shared evaluation artifacts.

If the underlying test data mutates constantly, ranking comparisons between two indexes are polluted by **freshness or data drift** rather than algorithmic changes.

### 12.3. Tiered Evaluation Suites

Recommended structure:

1. **Smoke set:** small set with clear expected hits, run after every deploy.
2. **Regression set:** queries tied to historical bugs or customer complaints.
3. **Representative set:** sampled proportionally from real traffic and user segments.
4. **Stress / edge set:** long queries, diacritics, typos, SKUs, and zero-hit queries.
5. **Freshness set:** recent inserts, updates, and deletes with visibility assertions.
6. **Safety / authorization set:** verifies zero cross-tenant or restricted-data leaks.

Weight categories according to business risk rather than treating every query identically.

## 13. `Precision@K`, `Recall@K`, and Hit Rate

### 13.1. `Precision@K`

**`Precision@K`** measures the proportion of relevant results within the **top K hits**:

\[
\operatorname{Precision@K}
=
\frac{\text{number of relevant results in top K}}{K}
\]

Example top-5 binary labels:

```text
Rank      1   2   3   4   5
Relevant  1   0   1   0   1
```

Three out of five are relevant:

\[
\operatorname{P@5}=3/5=0.60
\]

`0.60` indicates 60% of the top 5 positions are relevant per labels. It **does not measure** how many relevant documents were missed overall.

### 13.2. `Recall@K`

**`Recall@K`** measures the fraction of all relevant documents retrieved inside the top K:

\[
\operatorname{Recall@K}
=
\frac{\text{number of relevant results in top K}}
{\text{total relevant results in evaluation set}}
\]

Suppose the labeled corpus has **4 relevant documents** total, and top 5 retrieves 3:

\[
\operatorname{Recall@5}=3/4=0.75
\]

Meaningful recall requires knowing or reliably estimating the **full relevant set**. Labeling only today's top 5 and assuming everything else is irrelevant severely distorts recall.

### 13.3. `Hit Rate@K` / `Success@K`

When users need **at least one right answer**:

```text
Hit@K(query) = 1 if top K contains at least one relevant result,
               0 otherwise.
```

Averaging `Hit@K` across queries measures the chance of finding **at least one good hit** in the first K positions.

While intuitive, it fails to distinguish "right answer at rank 1" from "right answer at rank K"—pair it with `MRR` or `nDCG`.

### 13.4. Handling Queries with Zero Valid Results

When a query genuinely has zero relevant documents:

- Recall has denominator 0; define explicit evaluator handling.
- Returning empty results is the **correct** outcome.
- A search engine that forces 10 irrelevant hits is worse than one returning `[]` cleanly.

For out-of-stock or nonexistent items, measure **no-result correctness** and suggestion quality rather than inflating recall with noise.

## 14. `MRR` and `nDCG`: Measuring Ranking Order

### 14.1. `MRR` — Mean Reciprocal Rank

`MRR` rewards placing the **first relevant result** as high as possible.

For one query:

\[
\operatorname{RR}(q)
=
\frac{1}{\text{rank of first relevant result}}
\]

If the first relevant hit is at rank 2:

\[
\operatorname{RR}(q)=1/2=0.5
\]

Across `N` queries:

\[
\operatorname{MRR}
=
\frac{1}{N}
\sum_{q=1}^{N}\operatorname{RR}(q)
\]

If no relevant hit appears within cutoff K, convention sets `RR=0`.

`MRR` excels for **navigational search** or single-target lookups (like SKU lookup or a specific support page). It ignores ranking quality beyond the first relevant hit.

### 14.2. `DCG` and `nDCG` — Evaluating Graded Relevance

With graded labels from 0 to 3, **Discounted Cumulative Gain**:

\[
\operatorname{DCG@K}
=
\sum_{i=1}^{K}
\frac{2^{rel_i}-1}{\log_2(i+1)}
\]

where `rel_i` is the relevance grade at rank `i`. Dividing by `log₂(i+1)` discounts lower positions.

`nDCG` normalizes `DCG` against the ideal ranking:

\[
\operatorname{nDCG@K}
=
\frac{\operatorname{DCG@K}}
{\operatorname{IDCG@K}}
\]

where `IDCG@K` is the maximum possible `DCG` for the known labels. For non-empty positive label sets, `nDCG` ranges from 0 to 1.

Example:

```text
Rank:       1   2   3   4   5
Relevance:  3   1   0   2   0
```

A stronger ranking:

```text
Rank:       1   2   3   4   5
Relevance:  3   2   1   0   0
```

The second order places grade `2` ahead of grade `1`, yielding **higher DCG and nDCG** even though both retrieve the same set of documents.

When a query has zero positive relevance labels, `IDCG@K=0`; evaluators must handle that case without dividing by zero.

### 14.3. Choosing Metrics by Task

| Task | Useful Metrics | Caveat |
| --- | --- | --- |
| Exact page/code lookup | `MRR@K`, `Hit@1` | `MRR` ignores hits below the first relevant one |
| Product comparison browsing | `nDCG@10`, `P@10` | Requires reliable graded labels |
| Comprehensive document retrieval | `Recall@K`, coverage | Requires knowing the full relevant set |
| Autocomplete | `MRR@5`, suggestion acceptance | Short prefixes produce broad matches |
| Returning empty accurately | No-result correctness | Never force hits on empty topics |
| Support docs search | `nDCG@5`, task success | A click does not prove the issue was solved |
| Freshness-critical search | Freshness / visibility latency | High relevance on stale data falls short |

Select **metrics tied to product goals** rather than adopting `nDCG` just because it sounds rigorous when reliable graded labels are absent.

## 15. Search Quality for Vietnamese and Multilingual Data

### 15.1. Vietnamese Diacritics and Unicode

Pairs like:

```text
"máy lọc không khí"  /  "may loc khong khi"
"điện thoại"        /  "dien thoai"
"cà phê"            /  "ca phe"
```

often need equivalent search matching in Vietnamese apps. However, stripping diacritics carelessly causes issues:

- Boosts recall for unaccented queries.
- Increases false positives, hurting precision.
- Collapses distinct words into identical tokens.
- Affects highlighting, exact matching, and proper nouns.

Evaluate with accented/unaccented **query pairs** against actual data and analyzers. If using custom analyzers or Unicode folding filters, configure them explicitly in the Search index definition and verify with tests—never assume `lucene.standard` solves all Vietnamese nuances automatically.

### 15.2. Unicode Normalization

Accented characters can exist in multiple Unicode encodings (precomposed vs. base character + combining mark). Text pasted from external systems often mixes forms.

Without a normalization policy:

```text
Client A sends "café" (precomposed character)
Client B sends "café" (e + combining mark)
```

the two strings look identical yet have different code-point sequences. Enforce **Unicode normalization** at ingestion or in the analyzer, and inspect raw bytes/code points when debugging mismatches.

### 15.3. Compound Words, Proper Names, and SKUs

Vietnamese uses spaces inside compound words:

```text
"máy lọc không khí"
"tai nghe chống ồn"
"điện thoại thông minh"
```

Because analyzers split syllables on whitespace, `phrase` matching does not automatically understand every semantic nuance. Verify:

- `phrase` queries;
- Multi-word synonyms;
- Tokenization and positions;
- Title vs. description boosts;
- Exact matching for SKUs;
- Prefix matching in autocomplete.

SKUs like `"AB-1200-X"` may be split into separate tokens by prose analyzers. Use dedicated exact/`token` fields alongside full-text fields rather than forcing one analyzer across everything.

### 15.4. Version and Test Synonyms

Examples:

```text
"tai nghe" ~ "headphone"
"điện thoại" ~ "smartphone"
"máy tính xách tay" ~ "laptop"
```

Synonyms expand recall yet reduce precision when terms only overlap in narrow contexts.

Workflow:

1. Version-control the synonym dictionary.
2. Run queries with and without synonyms.
3. Compare `P@K`, `Recall@K`, and `MRR`/`nDCG`.
4. Measure latency and result-count shifts.
5. Canary before rolling out to 100% traffic.

Never dump thousands of unvetted synonyms hoping search becomes "smarter."

### 15.5. Fuzzy Matching and Typos

Fuzzy queries recover typos:

```text
"bluetooh"  -> "bluetooth"
"samssung"  -> "samsung"
```

Allowing excessive edit distances on short tokens creates noise. `maxEdits`, `prefixLength`, and `maxExpansions` are governed by Search operator and version limits.

Measure:

- Typo recovery rate;
- False positive rate;
- Query latency;
- Impact on top-5 rankings;
- Divergence between product codes and regular words.

Product codes and IDs usually need **exact or strict prefix matching**, not heavy fuzziness.

### 15.6. Autocomplete Differs from Full-Text Search

Autocomplete serves users mid-typing:

```text
"tai" -> "tai nghe bluetooth", "tai nghe chụp tai", ...
```

Use an `autocomplete` field mapping and `autocomplete` operator rather than treating a full-text `text` query as typeahead.

Evaluate separately:

- Suggestion quality at 2, 3, and 4 characters;
- Latency under rapid keypress bursts;
- Typos and Vietnamese diacritics;
- Session success rate;
- Request caps, debouncing, and rate limits.

N-gram-heavy autocomplete indexes increase storage and update cost. Do not apply full-search freshness or ranking thresholds without defining clear UX contracts.

## 16. Inspecting Relevance Scores for Diagnostics

### 16.1. `searchScore` Is a Relative Score, Not a Probability

```javascript
db.products.aggregate([
  {
    $search: {
      index: "products_text_v1",
      text: {
        query: "máy lọc không khí",
        path: ["title", "description"]
      }
    }
  },
  { $limit: 10 },
  {
    $project: {
      title: 1,
      score: { $meta: "searchScore" }
    }
  }
]);
```

`score` provides **relative ranking within a single query and configuration**. Never interpret `score=7.3` as "73% probability this is the right product."

Scores across different queries, index definitions, or corpora are not on a uniform scale. Evaluate **rank order and relevance labels** instead of raw score magnitudes.

### 16.2. Field Boosts Can Improve Quality or Cause Regressions

Example query boosting `title`:

```javascript
db.products.aggregate([
  {
    $search: {
      index: "products_text_v1",
      compound: {
        should: [
          {
            text: {
              query: "tai nghe bluetooth",
              path: "title",
              score: { boost: { value: 3 } }
            }
          },
          {
            text: {
              query: "tai nghe bluetooth",
              path: "description"
            }
          }
        ],
        minimumShouldMatch: 1
      }
    }
  },
  { $limit: 10 },
  {
    $project: {
      title: 1,
      score: { $meta: "searchScore" }
    }
  }
]);
```

Boosting `title` lifts title-matching products above description-only hits. Yet `boost=3` is **purely illustrative**, not a universal optimum. Validate against golden queries—especially when titles are short or keyword-stuffed.

### 16.3. Search Score Details / Explain

In supported versions and configurations, MongoDB Search exposes scoring explanations (such as `scoreDetails` and corresponding metadata) to inspect:

- Which fields matched;
- Which clauses contributed to the score;
- How boosts and synonyms affected scoring;
- Why one document outranked another.

In production, scoring details enlarge payloads and add overhead. Enable them only on scoped diagnostic queries, and never log sensitive document data.

### 16.4. `$searchMeta` and Result Counts

To retrieve **estimated or total match counts**:

```javascript
db.products.aggregate([
  {
    $searchMeta: {
      index: "products_text_v1",
      text: {
        query: "tai nghe",
        path: ["title", "description"]
      },
      count: {
        type: "total"
      }
    }
  }
]);
```

MongoDB Search supports count types such as `total` and `lowerBound` depending on operator and version. `total` can be costlier on large workloads; `lowerBound` is not an exact total for strict pagination.

Never use `$searchMeta` counts as proof that a recent write is visible—counts reflect **the Search index's queryable state at that instant**.

### 16.5. `$search` and Aggregation Pipeline Order

`$search` must be the first stage in its pipeline (including supported nested pipeline contexts per version). Never write:

```javascript
// Not the right way to "pre-filter" $search.
db.products.aggregate([
  { $match: { status: "ACTIVE" } },
  { $search: { index: "products_text_v1", text: {
    query: "tai nghe", path: "title"
  } } }
]);
```

Instead:

```javascript
db.products.aggregate([
  {
    $search: {
      index: "products_text_v1",
      compound: {
        must: [
          { text: { query: "tai nghe", path: "title" } }
        ],
        filter: [
          { equals: { path: "status", value: "ACTIVE" } }
        ]
      }
    }
  },
  { $limit: 10 }
]);
```

Filtering inside `$search` requires matching field mappings and operators. Filtering after `$limit` risks returning fewer than K valid items.

## 17. Online Evaluation: CTR, Conversion, and A/B Testing

### 17.1. Offline Metrics Are Not the Final Answer

A new index may raise offline `nDCG` on labeled queries yet cause real users to:

- Be confused by altered ordering;
- Miss familiar expected hits;
- Click clickbait titles that do not satisfy their need;
- Reformulate queries repeatedly;
- Experience higher latency;
- See discontinued items due to worse freshness.

Always pair offline evaluation with **online user outcomes** and strict guardrails.

### 17.2. Common Online Metrics

| Metric | Description | Caution |
| --- | --- | --- |
| `CTR@K` | Click-through rate in top K | Heavily skewed by position bias; not pure relevance |
| Search success rate | Share of sessions achieving defined goal | Requires clear definition of success |
| Query reformulation rate | Share of users immediately retyping queries | Can rise naturally during valid exploratory search |
| No-results rate | Share of queries returning zero hits | Zero is correct when no valid item exists |
| Add-to-cart / conversion | Downstream business actions after search | Influenced by price, stock, UX, and promos |
| Abandonment rate | Users leaving the search flow | May mean they already saw enough info without clicking |
| p95/p99 latency | Execution performance | Does not reflect ranking accuracy |
| Freshness probe rate | Share of changes visible within SLO | Measured via synthetic probes / expected membership |

Never declare a ranking change better based on **CTR alone**: users disproportionately click rank 1, and UI tweaks also shift click rates.

### 17.3. Running a Fair A/B Test

Comparing two indexes:

```text
Control:   index products_text_v1
Treatment: index products_text_v2
```

Protocol:

1. Ensure both indexes are queryable and operating over comparable data/timeframes.
2. Assign users/sessions deterministically so users do not flip versions mid-session.
3. Keep UI, filters, and success definitions identical across buckets.
4. Log index and query versions alongside impression/click events.
5. Watch freshness and latency guardrails continuously.
6. Slice results by query segment (head/long-tail, accented Vietnamese, SKUs).
7. Define stopping criteria and statistical confidence thresholds up front.

If the treatment index is **still building** or lagging worse than control, conversion drops reflect broken freshness rather than analyzer quality.

### 17.4. Privacy-Preserving Telemetry

An observability record might capture:

```json
{
  "requestId": "req-308-example",
  "indexVersion": "products_text_v2",
  "queryCategory": "generic-product",
  "latencyMs": 47,
  "returnedCount": 10,
  "topDocumentIds": ["P-1", "P-2"],
  "hadClick": true,
  "hadConversion": false
}
```

In real systems, query text may contain PII, phone numbers, addresses, secrets, or sensitive health terms. Always:

- Minimize raw query logging;
- Mask or tokenize sensitive strings;
- Enforce retention policies and RBAC;
- Keep personal data out of metric labels;
- Apply access controls when sharing search relevance datasets.

## 18. Rolling Out New Indexes and Analyzers Safely

### 18.1. Never Edit a Live Production Index Blindly and Hope

Suppose you need a new Vietnamese analyzer or an extra `keywords` field. A controlled rollout looks like:

```text
products_text_v1  <-- currently serving 100% traffic
      |
      | create in parallel
      v
products_text_v2  <-- building / indexing
      |
      | queryable + smoke tests + quality/freshness checks
      v
canary 1% -> 10% -> 50% -> 100%
      |
      v
keep v1 during rollback window before cleanup
```

Percentages are illustrative; real rollouts depend on load, SLOs, tier quotas, and dual-index routing support.

### 18.2. Pre-Cutover Checkpoints

Before shifting traffic:

- `v2` is queryable.
- Zero index build errors or mapping warnings.
- Smoke queries return expected documents by ID and keyword.
- Golden query set meets minimum relevance thresholds.
- Freshness probes satisfy target SLOs.
- Query latency and resource headroom look safe.
- Application selects index names via config or feature flag.
- Rollback to `v1` has been rehearsed in staging.

"Index ready" is a **necessary condition**, never a sufficient one.

### 18.3. Rollbacks Must Also Revert Query Versions

Analyzer or mapping changes often ship alongside query-shape changes:

```text
v1: text title + description
v2: autocomplete title + synonyms + boosted title
```

Reverting only the index name back to `v1` while still firing `autocomplete` against an unmapped field will break queries.

Manage **versioned configuration bundles**:

```text
searchConfigVersion = {
  indexName,
  queryTemplateVersion,
  analyzerContractVersion,
  scoreSettings
}
```

Roll back the entire coherent config bundle rather than flipping a single string.

### 18.4. Cost of Keeping Two Indexes Concurrently

During cutover, `v1` and `v2` both consume:

- Index storage;
- CPU for processing writes;
- Memory, cache, and I/O;
- Sync visibility headroom;
- Managed Search infrastructure billing.

On a heavily loaded cluster, building `v2` can degrade `v1` freshness. Ensure capacity headroom, monitor closely, and schedule builds during low-traffic windows.

### 18.5. Abort / Roll Back When Guardrails Trip

Define explicit rollback triggers beforehand:

- Search error rate breaches guardrail;
- Freshness p95 exceeds target significantly;
- Zero-results rate spikes on head queries;
- `nDCG`/`MRR` drops beyond tolerance;
- p99 latency threatens API SLAs;
- Search resources approach exhaustion.

Never wait days for conversion drops when **clear, verified technical regressions** are already firing.

## 19. `mongosh` Lab: Creating Probes and Measuring Search Visibility

### 19.1. Prerequisites

**Requires a MongoDB Search-enabled deployment**, such as an Atlas test cluster with Search enabled. A plain local standalone `mongod` **does not automatically support `$search` and Search indexes** just because MongoDB Server is running.

The script below:

- Uses a dedicated lab database;
- Creates a **unique collection per run**;
- Creates a dedicated Search index;
- Writes only synthetic probe data;
- Uses `_id` and `runId` to query and clean up safely;
- Leaves production search indexes untouched.

If you lack a Search-capable test environment, study the syntax and principles **without running DDL**—never spin up paid cloud resources without authorization.

### 19.2. Connect to the Right Cluster and Create a Unique Namespace

Illustrative URI:

```bash
mongosh "mongodb+srv://<test-cluster-host>/" 
```

Inside an authenticated shell:

```javascript
const lab = db.getSiblingDB("mongo_search_row308_lab");
const runId = "row308-" + new ObjectId().toHexString();
const collectionName = "products_" + runId.replaceAll("-", "_");

if (lab.getCollectionNames().includes(collectionName)) {
  throw new Error("Namespace already exists; refusing to overwrite.");
}

lab.createCollection(collectionName);
const products = lab.getCollection(collectionName);
const searchIndexName = "row308_text_v1";

print("database=" + lab.getName());
print("collection=" + products.getName());
print("runId=" + runId);
```

If your `mongosh` runtime lacks `replaceAll`, use `runId.replace(/-/g, "_")`. The goal is isolating each run in its own collection without altering pre-existing collections.

### 19.3. Create a Dedicated Lab Search Index

```javascript
products.createSearchIndex(
  searchIndexName,
  {
    mappings: {
      dynamic: false,
      fields: {
        title: { type: "string" },
        description: { type: "string" },
        tenantId: { type: "token" },
        status: { type: "token" },
        probeToken: { type: "token" }
      }
    }
  }
);
```

On compatible MongoDB Search versions, `token` supports `equals` on single strings. Adjust mappings if your environment has version differences before running—never test unverified configs in production.

Check index build status:

```javascript
printjson(
  products.getSearchIndexes(searchIndexName)
);
```

**Do not run `$search` immediately and treat build-in-progress as an error.** Inspect the server-returned status. Initial index build time is normal setup overhead, distinct from ongoing sync lag after the index is ready.

### 19.4. Write a Document with a Unique Marker

Once the index is queryable:

```javascript
const probeId = new ObjectId();
const probeToken = "probe-" + probeId.toHexString();
const testTenantId = runId;

const writeStart = new Date();
const writeResult = products.insertOne(
  {
    _id: probeId,
    runId,
    tenantId: testTenantId,
    status: "ACTIVE",
    probeToken,
    title: "Tai nghe thử nghiệm Search",
    description: "Document used to measure index freshness",
    version: 1,
    createdAt: new Date(),
    updatedAt: new Date()
  },
  {
    writeConcern: { w: "majority", wtimeout: 10000 }
  }
);
const writeAcknowledgedAt = new Date();

printjson({
  writeResult,
  writeStart,
  writeAcknowledgedAt,
  probeId,
  probeToken
});
```

`writeAcknowledgedAt` is recorded client-side upon response. This is a **client-observed timestamp** including network RTT, not an internal MongoDB Search clock.

If you hit a write concern timeout, **never assume the insert failed**. Check `_id`/`runId` in the collection before retrying with a new ID.

### 19.5. Read Source MongoDB by ID

```javascript
printjson(
  products.findOne({
    _id: probeId,
    runId
  })
);
```

When this returns the document, source persistence is confirmed under your read concern. It does not yet prove the Search index sees it.

### 19.6. Query Search by Exact Token

```javascript
function findProbeInSearch() {
  return products.aggregate([
    {
      $search: {
        index: searchIndexName,
        compound: {
          filter: [
            {
              equals: {
                path: "probeToken",
                value: probeToken
              }
            },
            {
              equals: {
                path: "tenantId",
                value: testTenantId
              }
            }
          ]
        }
      }
    },
    { $limit: 5 },
    {
      $project: {
        _id: 1,
        probeToken: 1,
        title: 1,
        version: 1
      }
    }
  ]).toArray();
}

printjson(findProbeInSearch());
```

If an empty array returns immediately after insert, the index may still be syncing or a mapping/query bug exists. Verify index readiness and query syntax before blaming lag.

### 19.7. Bounded Polling to Measure Visibility Time

Only on an authorized test cluster, run a **bounded** polling loop:

```javascript
let firstObservedAt = null;
let lastProbeError = null;
const maxAttempts = 30;
const pollIntervalMillis = 500;

for (let attempt = 0; attempt < maxAttempts; attempt++) {
  try {
    const hits = findProbeInSearch();
    const found = hits.some(
      (doc) => doc._id.toHexString() === probeId.toHexString()
    );
    if (found) {
      firstObservedAt = new Date();
      break;
    }
  } catch (error) {
    lastProbeError = {
      name: error.name,
      message: error.message
    };
    break;
  }

  sleep(pollIntervalMillis);
}

printjson({
  firstObservedAt,
  observedVisibilityLagMs:
    firstObservedAt
      ? firstObservedAt.getTime() -
        writeAcknowledgedAt.getTime()
      : null,
  pollIntervalMillis,
  lastProbeError,
  timedOutWithoutVisibility:
    !firstObservedAt && !lastProbeError
});
```

Explanation:

- Exits early as soon as the exact document is found.
- 30 attempts at 500 ms is a **short test probe**, not a default SLO target.
- A timeout means **"not observed within the test window,"** not automatically "Search lost data."
- Query errors are tracked separately so they never pollute visibility-lag histograms.
- Polling can miss the exact sub-interval moment visibility occurred.
- Never fire thousands of concurrent probes that overload Search itself.

### 19.8. Measuring Update Freshness Separately from Inserts

An update test:

```javascript
const newTitle = "Máy chiếu bỏ túi đặc biệt row308";

const updated = products.updateOne(
  { _id: probeId, runId, version: 1 },
  {
    $set: {
      title: newTitle,
      updatedAt: new Date()
    },
    $inc: { version: 1 }
  }
);

printjson(updated);
```

To verify the index updated `title`, query `text` on the new title while **scoping to the exact probe**:

```javascript
const updatedHits = products.aggregate([
  {
    $search: {
      index: searchIndexName,
      compound: {
        must: [
          {
            text: {
              query: "máy chiếu bỏ túi",
              path: "title"
            }
          }
        ],
        filter: [
          {
            equals: {
              path: "probeToken",
              value: probeToken
            }
          }
        ]
      }
    }
  },
  { $limit: 5 },
  { $project: { title: 1, version: 1 } }
]).toArray();

printjson(updatedHits);
```

If the source document is already `version: 2` while `updatedHits` is empty, Search has not indexed the new tokens yet. When Search matches the new title tokens, that confirms **update visibility**.

To measure exact update lag, record `updatedAcknowledgedAt` right after the update succeeds and poll using a predicate matching the **new keywords**—never inspect only `version: 2` because the fetched document can be newer than the index membership.

### 19.9. Clean Up Only Your Test Data

Verify before deleting:

```javascript
print("database=" + lab.getName());
print("collection=" + products.getName());
print("runId=" + runId);

printjson(
  products.findOne(
    { _id: probeId, runId },
    { title: 1, probeToken: 1, runId: 1 }
  )
);
```

Delete only the document you created:

```javascript
const removed = products.deleteOne({
  _id: probeId,
  runId
});

printjson(removed);
print(
  "remaining=" +
    products.countDocuments({ _id: probeId, runId })
);
```

Deletions also sync asynchronously to the Search index, so running `$search` right after `deleteOne` **does not prove index deletion finished**. Never drop indexes or databases when namespaces might be shared.

The lab collection and Search index remain after deleting the probe document. On billed environments, authorized administrators should **decommission lab resources via approved cleanup workflows** only after verifying namespace/index ownership. Never run `dropSearchIndex()` or `dropDatabase()` on shared environments merely to clean up a lesson.

## 20. Testing Native `$text` to Contrast with MongoDB Search

In a **separate** collection on test MongoDB (distinct from the Search lab index/namespace):

```javascript
const nativeDb = db.getSiblingDB("mongo_search_row308_lab");
const nativeColl = nativeDb.getCollection(
  "native_text_" + new ObjectId().toHexString()
);

nativeDb.createCollection(nativeColl.getName());

nativeColl.createIndex({
  title: "text",
  description: "text"
});

const nativeId = new ObjectId();

nativeColl.insertOne({
  _id: nativeId,
  title: "Tai nghe Bluetooth",
  description: "Simulated product for native text search"
});

printjson(
  nativeColl.find(
    { $text: { $search: "Bluetooth" } },
    {
      title: 1,
      textScore: { $meta: "textScore" }
    }
  ).sort({
    textScore: { $meta: "textScore" }
  }).toArray()
);
```

Key differences:

- Used `createIndex({title:"text"})`, **not `createSearchIndex()`**.
- Queried with `$text`, not `$search`.
- Retrieved score via `textScore`, not `searchScore`.
- Primary reads follow database index mechanics, without a separate Search-service sync loop like MongoDB Search.
- If routed to a secondary, replication lag and read preference apply.

Delete only the test record:

```javascript
nativeColl.deleteOne({ _id: nativeId });
```

Never drop arbitrary collections just because names look like examples. Dedicated namespaces can be retired per lab procedures once ownership is confirmed.

## 21. Integrating Relevance Evaluation into CI/CD and Operations

### 21.1. Before Deploying a New Index

An engineering pipeline can:

1. Run query templates against a staging index over stable test data.
2. Collect top-K document IDs and search scores.
3. Compare against golden relevance judgments.
4. Compute `P@K`, `MRR@K`, `nDCG@K`, and `Hit@K` per query category.
5. Run insert/update/delete freshness probes.
6. Measure p95/p99 query latency under representative load.
7. Assert zero regressions in tenant isolation or inactive-item filtering.
8. Emit a **v1 vs. v2** comparison report.

Never allow CI test scripts to mutate production indexes; enforce strict environment and permission isolation.

### 21.2. Sample Comparison Report

| Metric | v1 | v2 | Assessment Needed |
| --- | ---: | ---: | --- |
| `nDCG@10` (offline) | 0.72 | 0.79 | Likely ranking improvement |
| `MRR@5` (SKU queries) | 0.94 | 0.88 | Regression on exact lookups |
| `Recall@10` (synonym queries) | 0.61 | 0.78 | Improved recall |
| No-results rate | 8.0% | 6.2% | Verify fewer empty results are actually valid |
| Search p95 latency | 75 ms | 105 ms | Slower queries |
| Visibility p95 | 4 s | 9 s | Worse freshness |
| Index storage | 18 GiB | 29 GiB | Higher storage cost |

These figures are **hypothetical examples**. Even with higher `nDCG` and `Recall`, **v2 is not automatically better**: if the API requires exact SKU lookup and 5-second freshness for new items, the SKU `MRR` and freshness regressions could be blockers.

### 21.3. Never Compare Metrics Across Inequivalent Datasets

If v1 ran against Monday morning's snapshot and v2 ran against Tuesday's snapshot with 10% more products, ranking metrics cannot be compared directly without adjustment.

For valid comparisons, hold constant:

- Query set;
- Relevance judgments;
- Dataset version or paired snapshot;
- Business filters;
- Cutoff K and metric formulas;
- Load-test conditions (or explicitly document differences).

When live data changes continuously, combine a **static offline corpus** with **online A/B evaluation** so conclusions are never distorted by data drift.

### 21.4. Post-Deploy Verification

After shifting traffic:

```text
Index queryable?
       |
       v
Smoke queries correct?
       |
       v
Freshness probes within SLO?
       |
       v
Latency and errors within guardrails?
       |
       v
Offline + online quality acceptable?
       |
       v
Continue rollout / keep observing
```

If any gate fails, diagnose and **roll back the canary**—never keep ramping traffic merely because the index reports `READY`.

## 22. Runbook When Search Syncs Slowly or Result Quality Drops

### 22.1. Case A — Freshness Degrades While Queries Stay Fast

Suppose:

```text
Search query p95: 55 ms
Insert visibility p95: 45 seconds
Previous visibility p95: 4 seconds
MongoDB write QPS: increased 5x
```

Investigation steps:

1. Confirm probe queries are valid with adequate sample counts.
2. Inspect write rate, update patterns, and Search node resources.
3. Check whether an index rebuild or migration is running.
4. Check index status, indexing errors, or backlog metrics if available.
5. Throttle **non-urgent batch jobs** if permitted.
6. Reassess capacity or index mappings based on observed metrics.
7. Do not crank up probe polling QPS—it only adds load to Search.

### 22.2. Case B — Query Latency Spikes While Freshness Stays Normal

```text
Query p95: increased from 80 ms to 400 ms
Visibility p95: held steady at 3 seconds
```

Investigation checklist:

- Are new query patterns using overly broad fuzzy settings?
- Are expensive `$searchMeta` total counts running?
- Did `$limit` or pagination `skip` grow excessively?
- Are queries scanning or projecting too many fields?
- Did Search QPS, CPU, cache misses, or network RTT spike?
- Is the API calling extra downstream services or missing caches?

Never alter indexing configs for query-latency spikes caused by new query patterns or API layers.

### 22.3. Case C — Zero-Results Spike After Analyzer Change

```text
Index v1: query "dien thoai" returns good results
Index v2: same query returns empty
```

Investigation steps:

1. Confirm v2 is queryable and caught up on freshness.
2. Compare field mappings and analyzers.
3. Compare query templates and operators between versions.
4. Inspect Unicode/diacritic normalization.
5. Replay accented and unaccented golden queries.
6. Roll back to v1 if a clear regression is confirmed.

Never "fix" this by stripping diacritics blindly across all fields before measuring false positives.

### 22.4. Case D — Search Returns Unauthorized Documents

Priorities:

1. Stop leakage immediately via **authoritative authorization/filtering** prior to returning responses.
2. Inspect the source document and current permissions.
3. Check Search index status and update/delete lag.
4. Inspect API and UI caches.
5. Purge caches or temporarily suppress affected search results if needed.
6. File a security incident per organizational policy.

Never dismiss this as "slightly off relevance"—it is a privacy and access-control failure.

### 22.5. Case E — New Index Build Fails

Check:

- Does the definition contain invalid field mappings or analyzers?
- Are sufficient CPU, memory, and storage available?
- Are namespace and index name valid?
- Do deployment, tier, and server version support all used operators?
- Is another conflicting DDL/index change running?
- Do malformed BSON field values break the mapper?

Never drop the working legacy index just because the new build failed. Fix the definition in staging and re-run the rollout plan.

## 23. Common Mistakes

| Mistake | Reality and Fix |
| --- | --- |
| "Majority write succeeded so `$search` must see it immediately" | MongoDB Search updates asynchronously; measure visibility separately |
| "Native `$text` and MongoDB Search use the same index" | Two distinct engines, index types, and syntaxes |
| "Index `READY` means every recent write is indexed" | `READY`/queryable does not guarantee zero lag |
| "`findOne` sees the new title so Search index is updated" | Source docs can be newer than Search token membership |
| "Search missed it so data was lost" | Could be lag, analyzer, mapping, filter, tenant, or cache |
| "Search returned the new title so index membership is fresh" | Returned fields may come from collection fetches while index matched old terms |
| "Poll every 1 ms to reduce lag" | Polling does not speed up indexing; it only adds load |
| "Lag measured from document `updatedAt` is exact" | Client clock skew, retries, polling interval, and network RTT distort it |
| "Measuring inserts alone covers freshness" | Updates and deletes have distinct behaviors and risks |
| "Low Search p95 latency means Search is healthy" | Relevance and freshness can still be broken despite fast queries |
| "Lower no-results rate is always better" | Queries with no valid matches should return empty |
| "Higher CTR proves better relevance" | Position bias, UI, and pricing skew CTR |
| "Computing `Recall@K` using only labeled top-K hits" | Requires estimating the full relevant set; never label unjudged docs 0 blindly |
| "`searchScore` is the probability a product is right" | Scores rank relatively; they are not calibrated probabilities |
| "Huge boosts always improve quality" | Can shove irrelevant hits to the top |
| "Stripping Vietnamese accents is always better" | Raises false positives; measure precision and recall |
| "Wider fuzziness is always better" | Short queries turn noisy and slow |
| "Cut over 100% traffic as soon as v2 is created" | Wait for queryable status and verify freshness, quality, and latency |
| "Rollback only needs swapping `indexName`" | Query templates, operators, and analyzers must also match v1 |
| "Search filter is a sufficient security boundary" | Indexes can lag; re-verify permissions from authoritative sources |
| "Use Search to enforce uniqueness/inventory" | Use MongoDB unique indexes and atomic writes/transactions |
| "A 5-second SLO is a MongoDB guarantee" | SLOs are application/ops targets, not built-in defaults |
| "Keeping two indexes costs nothing" | Dual indexing increases storage, CPU, and write/update load |
| "All Atlas dashboard metrics share identical names" | Verify exact deployment, version, tier, and metric definitions |

## 24. Practical Exercises

### Exercise A — Distinguish Text Indexes and Search Indexes

Given:

```javascript
db.products.createIndex({ title: "text" });
db.products.find({ $text: { $search: "bluetooth" } });
```

1. Is this native text search or MongoDB Search?
2. Which query uses `$search`?
3. When reading from a secondary, what can affect freshness?
4. Can `getSearchIndexes()` inspect the index above?

### Exercise B — Calculate Visibility Lag

A probe receives write ACK at `10:00:00.000`. Polling every 500 ms first observes the document at `10:00:04.500`.

1. What is the observed visibility lag?
2. Did the index definitely update at `10:00:04.500`?
3. Why must you attach a unique token?
4. If a query throws a mapping error, should you record a 4.5-second sample in the lag histogram?

### Exercise C — Search Shows "Contradictory" Output

A document updates `title` from `"Giày chạy bộ"` to `"Giày đi bộ"`. Querying `"chạy bộ"` still returns the document, yet `title` in the output already says `"Giày đi bộ"`.

1. Why can this happen?
2. Why is reading `title` alone insufficient to measure index freshness?
3. Which probe condition confirms the search index ingested the new tokens?

### Exercise D — Dashboard Design

Metrics:

```text
Query p95 latency:       50 ms (stable)
Write throughput:        increased 6x
Search visibility p95:   from 3 s to 40 s
Index status:            READY
```

1. Why can you not declare Search completely healthy?
2. Which resource metrics should you inspect?
3. Why does `READY` status not prove new writes are visible?
4. Should you scale probes up to thousands of QPS right now?

### Exercise E — Precision and Recall

Binary relevance for the top 5:

```text
Rank:      1  2  3  4  5
Relevant:  1  0  1  0  1
```

The evaluation set contains **4** relevant documents total.

1. Compute `Precision@5`.
2. Compute `Recall@5`.
3. Why do these two numbers differ?
4. If a document has not been judged yet, should you automatically assign `0`?

### Exercise F — MRR and nDCG

Graded relevance results for one query:

```text
Ranking A: 3, 1, 0, 2, 0
Ranking B: 3, 2, 1, 0, 0
```

1. Does `MRR` differ between A and B when both place the first relevant hit at rank 1?
2. Why does `nDCG` rate B higher than A?
3. If the sole goal is finding one exact product code, which metric matters more?

### Exercise G — Accented and Unaccented Vietnamese

Given query pairs:

```text
"điện thoại" / "dien thoai"
"máy lọc không khí" / "may loc khong khi"
"cà phê" / "ca phe"
```

Propose a workflow measuring `Recall@10`, `P@10`, and zero-results before and after changing an analyzer. Why is "total hit count increased" insufficient proof of improvement?

### Exercise H — Upgrading Index v1 to v2

Index v2 improves `nDCG@10` from 0.72 to 0.79, while query p95 rises from 75 ms to 105 ms and visibility p95 rises from 4 s to 9 s.

1. Should you immediately shift 100% traffic?
2. Which SLOs must be checked?
3. Design a canary rollout and rollback triggers.
4. Why must query templates also be versioned?

### Exercise I — Permissions and Stale Index

An internal document changes from `visibility:"PUBLIC"` to `"PRIVATE"`. `$search` with the `PUBLIC` filter still returns it for a few seconds.

1. Is this a freshness issue or a relevance issue?
2. Why must snippets/highlights never be sent before authorization checks?
3. Which source must serve as the authoritative access check?
4. Which metrics and incident classification apply?

### Exercise J — Separating Search Lag from Cache Lag

`findOne` sees the update; `$search` in `mongosh` also sees the update; the web API still serves stale data for 30 seconds.

1. Where does the cause likely sit?
2. Which metrics help isolate it?
3. Should you immediately scale up Search node CPUs?
4. How do you measure latency from **Search visible** to **UI visible**?

## 25. Official References

Exact details depend on **MongoDB server / Atlas Search version, index mappings, deployment type, and driver**. Consult documentation for your exact running version:

- [MongoDB Search Overview](https://www.mongodb.com/docs/atlas/atlas-search/) — architecture and text search capabilities.
- [Create a MongoDB Search Index](https://www.mongodb.com/docs/atlas/atlas-search/create-index/) — defining, creating, and managing indexes.
- [MongoDB Search Index Field Types](https://www.mongodb.com/docs/atlas/atlas-search/field-types/) — field mappings and type selection.
- [`$search` Aggregation Stage](https://www.mongodb.com/docs/atlas/atlas-search/aggregation-stages/search/) — query syntax and operators.
- [`$searchMeta` Aggregation Stage](https://www.mongodb.com/docs/atlas/atlas-search/aggregation-stages/searchMeta/) — metadata, counts, and facets where supported.
- [MongoDB Search Score](https://www.mongodb.com/docs/atlas/atlas-search/scoring/) — relevance scoring and boost options.
- [MongoDB Search Analyzers](https://www.mongodb.com/docs/atlas/atlas-search/analyzers/) — analyzers and tokenization.
- [MongoDB Search Synonyms](https://www.mongodb.com/docs/atlas/atlas-search/synonyms/) — synonym management.
- [`db.collection.getSearchIndexes()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.getSearchIndexes/) — inspecting Search indexes per version.
- [`db.collection.createSearchIndex()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.createSearchIndex/) — creating Search indexes where supported.
- [Text Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/) — native MongoDB text indexes.
- [`$text` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/text/) — native text search queries.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — distinguishing write acknowledgment from search visibility.

Product names, documentation pages, and metric fields can evolve between releases; when building production runbooks, always verify **the exact semantics of your version and service** rather than treating any example here as an immutable API contract.

## 26. Conclusion

**MongoDB Search indexes** power full-text search with analyzers, relevance ranking, and specialized features, yet search index state can **lag behind** recent writes to MongoDB. **Write acknowledgment**, **index queryable status**, **search visibility**, and **UI freshness** are distinct concepts. A successful majority write does not force `$search` to see the new document instantaneously.

To operate reliably, measure **insert/update/delete visibility lag** using unique markers and deadline-bounded polling while monitoring index lifecycles, query latency, resources, errors, and caches together. When results look wrong, inspect source data, mappings, analyzers, query filters, and index versions before assuming Search is merely lagging.

Search quality is more than returning hits. A strong system **retrieves relevant matches**, **ranks important hits near the top**, **stays sufficiently fresh**, and **serves within latency budgets**. Use `Precision@K`, `Recall@K`, `MRR`, `nDCG`, golden query sets, and online telemetry to measure changes—testing Vietnamese keywords, diacritics, synonyms, typos, and SKUs thoroughly. Roll out new indexes via versioning, canarying, and rollback plans rather than flipping 100% traffic blindly.

**Core message:** "Search index is READY" does not mean "every newly written document is searchable," and "fast queries" do not mean "good results." Reliable search requires measuring **freshness, relevance, latency, and business correctness** together.
