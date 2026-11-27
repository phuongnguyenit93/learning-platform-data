# Separating the Search Store from the Operational Database

## 1. Why Should You Not Use a Transactional Database for Every Query Type?

An operational database is typically optimized for well-structured transactions: creating bookings, updating payment status, checking ownership, and enforcing data constraints. This is an **OLTP (Online Transaction Processing)** workload—dominated by small reads/writes requiring transactions, consistency, and controlled key or index lookups.

When a product needs full-text search, suggestions, multi-attribute filtering, relevance ranking, text analysis, or searching across millions of documents, running everything on the transactional database can spike CPU, I/O, locks, index size, and latency for critical transactions. Complex search queries also have fundamentally different access patterns from booking writes.

A common architecture is **separating the search store/index from the operational database**:

- The operational database holds authoritative data and executes transactions.
- The search store holds a projection/index structured for search, filtering, text analysis, and ranking.
- A synchronization pipeline propagates required changes from the operational database to the search store.
- The application uses the search store to find candidates, then verifies data and permissions against the authoritative source before performing critical business operations.

In the **CLOUD_ARCHITECTURE** module, this decision touches data architecture, compute, networking, and deployment models. You must balance **reliability, security, performance, scalability, cost, and operations** under a Well-Architected mindset.

Running example: a booking platform has millions of properties/rooms. Guests search by city, check-in/check-out dates, guest count, amenities, price range, ratings, and keywords. The operational database remains responsible for final pricing, room availability, bookings, and payments; the search store serves fast filtering and result ranking.

## 2. Distinguishing an OLTP Database from a Search Store

The two systems serve distinct purposes:

| Criterion | Operational Database (OLTP) | Search Store |
| --- | --- | --- |
| Primary goal | Accurately read/write business state | Fast search, filtering, analysis, and ranking |
| Structure | Relational tables, documents, or key-value for transactions | Inverted indexes, term dictionaries, field indexes, vectors, or search-optimized structures |
| Data writes | Business transactions, constraints, controlled updates | Typically consumes projections/batches/events from another source |
| Queries | Lookups, joins, and structured conditions | Full-text, fuzzy, faceted filtering, relevance, geo, or vector search depending on product |
| Consistency | Typically the authoritative source for transactions | Can lag behind the source depending on the pipeline |
| Workload profile | Short reads/writes, transactions, concurrent updates | Read-heavy, multi-condition queries, refresh/indexing, and aggregations |
| Recoverability | Backups, replication, transaction recovery | Can be rebuilt from the authoritative source and pipeline |
| Cost drivers | Priced by transactions, compute, storage, replicas, backups | Priced by shards/partitions, replicas, index size, ingest, queries, and operations |

A search store is not simply a full copy of the database. Typically it stores a **read model/projection**: only the fields and structures needed for defined search queries. A search document might aggregate fields from property, location, amenities, and reviews without storing full payment histories or sensitive personal details.

### 2.1. A Search Index Is Not an Authoritative Data Source

Search indexes can lag behind, receive duplicate events, or temporarily reflect outdated state. Therefore:

- Never treat search index results as final proof that a room is still available.
- Never update prices or payment status based solely on a document in the search store.
- Before confirming a booking, verify availability, final pricing, and business rules at the authoritative service/database.
- When the index fails or lags, explicitly define which features keep working, which must reject requests, and which show stale data with clear indicators.

**Search answers "which items appear to match for display?"; the operational database answers "is this operation valid and allowed to commit?"**

## 3. Overall Architecture and Data Flow

~~~mermaid
flowchart LR
    USER["Web / Mobile"]
    API["Search API"]
    DB[("Operational DB<br/>Authoritative data source")]
    OUTBOX["Outbox / CDC / Change Stream"]
    PIPE["Indexer / Projection Worker"]
    SEARCH[("Search Store<br/>Inverted index / Search documents")]
    BOOK["Booking Service"]
    USER --> API --> SEARCH
    API -->|"Candidates and IDs"| BOOK
    BOOK --> DB
    DB --> OUTBOX --> PIPE --> SEARCH
~~~

Read paths and synchronization paths are decoupled:

1. The Search API receives filters, validates the request, and queries the search store.
2. The search store returns IDs, relevance scores, and permitted display fields.
3. The API can fetch extra display details from read models or services; for sensitive fields or transactional decisions, it verifies against the authoritative source.
4. The operational database commits changes.
5. An outbox, CDC pipeline, or change stream delivers changes to the indexer.
6. The indexer transforms source records into search documents per mapping rules and creates/updates/deletes documents in the search store.

Exact components depend on the platform. Outbox is an application pattern; CDC reads database change logs; change streams are database-provided mechanisms; indexers may be self-managed workers or integrated services. What matters is **end-to-end traceability from source commit to index state** and clean error handling between steps.

### 3.1. Search Document Example

A property search document might look like:

~~~json
{
  "propertyId": "property-91",
  "cityId": "city-hcm",
  "name": "Riverside Garden Hotel",
  "description": "Hotel near downtown and riverside",
  "amenities": ["wifi", "pool", "parking"],
  "location": {
    "lat": 10.776,
    "lon": 106.701
  },
  "rating": 4.6,
  "priceFrom": 1250000,
  "currency": "VND",
  "searchable": true,
  "sourceVersion": 1842,
  "indexedAt": "2026-11-18T04:30:00Z"
}
~~~

These fields are illustrative. Documents should include only data required for searching, filtering, ranking, and display—never payment credentials or unnecessary personal data. Standardize currency units, coordinates, amenity normalization, update timestamps, and the exact meaning of `searchable`.

## 4. Identify Access Patterns Before Choosing a Search Engine

Not every search requirement justifies a standalone search engine. Measure and catalog real queries:

| Need | Example | Potentially Suitable Mechanism |
| --- | --- | --- |
| Lookup by ID | Fetch a property by exact ID | Database primary key/index or cache |
| Structured filtering | City, dates, guest count, status | B-tree/indexes, search filters, or both depending on load |
| Full-text search | Keywords in titles and descriptions | Full-text / inverted index |
| Fuzzy / autocomplete | Typos, type-ahead suggestions | Analyzers, n-grams, edge n-grams, or completion features |
| Faceted search | Result counts by district, amenity, price tier | Aggregations/facets in the search store |
| Geo search | Within a radius or map bounding box | Geo index/queries |
| Semantic / vector search | Finding conceptually similar content | Vector index and embedding models |
| Transactional decisions | Room availability and final price | Authoritative operational database or transactional service |

If you only have a few simple filter queries and the operational database meets SLOs cheaply, adding a search cluster may overcomplicate the architecture. A search store pays off when queries are diverse, read-heavy, full-text/fuzzy/geo/aggregation-oriented, or when search load noticeably degrades transactional performance.

## 5. Designing Projections and Source-to-Index Mappings

An indexer should never mirror every source column blindly. Define an explicit **projection contract**:

- Which entities compose a single search document?
- Which fields are normalized, aggregated, or transformed?
- When a related entity changes, which search documents must update?
- Which fields must be searchable, filterable, sortable, facetable, or stored only for display?
- Which fields must be stripped as sensitive or unnecessary?
- If a document joins multiple sources, which version of each source is combined?

### 5.1. Field Mapping by Usage

| Field | Usage | Representation to Consider |
| --- | --- | --- |
| `propertyId` | Exact identifier | Keyword/exact value; use as document ID if appropriate |
| `name` | Full-text search, autocomplete | Analyzed text, optionally with an exact/sort subfield |
| `cityId` | Exact filtering | Keyword or exact-match field type |
| `amenities` | Multi-value filtering | Array/set field with exact matching |
| `priceFrom` | Filtering/sorting/ranges | Numeric with explicit currency unit |
| `rating` | Sorting/filtering/ranges | Numeric; define missing-value handling |
| `location` | Radius/map queries | Geo point or engine-supported geo type |
| `description` | Full-text | Language-appropriate text analyzer |
| `indexedAt`/`sourceVersion` | Operations/reconciliation | Timestamp and version number |

Full-text fields and exact-match fields typically require different indexing modes. If `cityId` is analyzed like prose text, queries may tokenize unexpectedly. If `description` is stored strictly as a keyword, word-level search inside it will not behave as expected.

### 5.2. Analyzers and Language Handling

Vietnamese search must handle diacritics, spelling variants, tokenization, compound words, and typos. You may need:

- Unicode normalization and diacritic folding/matching rules.
- Analyzers/tokenizers suited to Vietnamese or tested custom analyzers.
- A dedicated subfield for accent-insensitive search when required, without overwriting original display text.
- Versioned synonym lists with an update workflow.
- Evaluation against real queries: place names, brand names, short keywords, typos, and multi-word phrases.

Never enable stemming, accent stripping, or global synonyms blindly. Such transformations can raise recall while hurting precision, pushing irrelevant results to the top.

## 6. Data Synchronization: Outbox, CDC, and Polling

Separating the database from the search store requires an update pipeline. Three common approaches:

| Approach | How It Works | Pros | Limitations |
| --- | --- | --- | --- |
| Transactional outbox | Writes business data and outbox event in one transaction; publisher emits events | Application-level event control; avoids commit/publish gaps | Must manage outbox table, publisher, cleanup, and backlogs |
| CDC (Change Data Capture) | Tails database change logs and streams changes | Avoids table polling; near real-time | Coupled to log/connector, source schema, and read permissions; requires snapshot/restart handling |
| Watermark polling | Periodically queries records modified after advancing timestamp/version | Simple to start; minimal specialized infra | Periodic lag, repeated read load, easy to miss rows with naive watermarks |

### 6.1. Transactional Outbox

When a booking/property updates, the application writes the entity and an outbox row in the same transaction:

~~~sql
BEGIN;

UPDATE property
SET name = 'Riverside Garden Hotel',
    version = version + 1
WHERE property_id = 'property-91';

INSERT INTO outbox_events (
    event_id, aggregate_type, aggregate_id, aggregate_version, event_type
)
VALUES (
    'evt-abc', 'Property', 'property-91', 1842, 'PropertyUpdated'
);

COMMIT;
~~~

A publisher reads the outbox and forwards events to the broker/indexer. If the transaction rolls back, neither the property update nor the event exists. If the publisher emits an event and crashes before marking it done, the event can be replayed; the indexer must be idempotent by event ID/version.

### 6.2. CDC

CDC captures changes from the write-ahead log/binlog/change stream or equivalent log mechanism. It is useful for syncing existing datasets or many tables without adding event publishing to every business code path.

CDC requires careful attention to:

- DDL/schema changes and how connectors emit schema events.
- Combining an initial snapshot with continuous log streaming.
- Storing and recovering offsets/checkpoints.
- Replication slot/log retention inflating source storage if a connector stalls for long.
- Representing deletes, truncates, multi-row transactions, and event ordering.
- Stripping sensitive fields so they never enter the stream/index.

CDC reflects raw database changes; it does not automatically carry rich domain semantics. A single row update may not explain "booking confirmed" when business rules span multiple tables or states.

### 6.3. Polling

Polling can rely on a `version` or `updatedAt` column. However, coarse timestamp precision, clock skew, delayed transaction commits, or multiple rows sharing a timestamp can drop records if watermark queries are naive. Use composite cursors, overlap windows, deduplication, and periodic reconciliation.

## 7. Eventual Consistency and Search Index Freshness

Search indexes are typically updated asynchronously and are therefore **eventually consistent**. After a user updates a property, search results may still display the prior state briefly.

Define business-driven freshness SLOs:

| Change Type | Illustrative Acceptable Lag | Behavior While Out of Sync |
| --- | --- | --- |
| Property description/photos | A few minutes | Temporarily showing prior content is acceptable |
| Amenities/attributes | Tens of seconds | Filter hits may lag; UI handles detail/index differences |
| Advertised price | Very short or verified real-time | Never use indexed price to finalize a transaction |
| Room availability | Never rely on index as confirmation source | Verify at inventory/booking service before placing hold |
| Removing/hiding policy-violating content | Tight SLA for safety/compliance | May require tombstones or immediate serving-layer blocks |

These durations are examples only. For each field, measure p95/p99 end-to-end latency from source commit to index visibility—not merely when the broker receives the event.

### 7.1. Read-After-Write

If an admin edits a property's name and immediately searches for it before indexing finishes, the UX can feel broken. Options include:

- Returning an "indexing in progress" status with the current version.
- Reading details from the operational database briefly right after a write.
- Using read-your-writes session/version tokens so queries wait or bypass until the index reaches the expected version.
- For small scopes, blending search hits with fresh source updates in a controlled manner.

Never force synchronous index refreshes on every write if doing so crushes throughput and spikes latency. Use immediate refresh only where the business genuinely requires it and the cost has been measured.

## 8. Handling Duplicate, Out-of-Order, and Stale Events

Event pipelines can deliver duplicates or out-of-order messages due to retries, multiple publishers, partitioning, and parallel workers. If an indexer blindly applies whichever event arrives last, an older event can overwrite a newer projection.

### 8.1. Per-Entity Versioning

Each entity maintains a monotonically increasing version. The search document stores `sourceVersion`. The indexer applies updates only if the incoming version is newer:

~~~text
if event.aggregateVersion > document.sourceVersion:
    apply_projection(event)
else:
    ignore_as_duplicate_or_stale()
~~~

This is pseudocode. Use atomic conditional updates or optimistic concurrency supported by your search engine; reading the version in application code and writing unconditionally still leaves a race between concurrent workers.

### 8.2. Deletes and Tombstones

When the source deletes a property, the pipeline must propagate that removal to the search store. Delete events may arrive late or race ahead of a retried older update. Store tombstones/versions to prevent stale retries from resurrecting a deleted document.

For content that must vanish immediately for safety/compliance, do not rely solely on indexer lag. Pair the delete pipeline with a serving-layer denylist or authoritative visibility check, ensuring the denylist itself is highly available.

## 9. Deletes, Mappings, and Composite Document Updates

A single search document often combines multiple entities—for example, property details, city, amenities, reviews, and policies. When a secondary entity updates, the indexer must know which search documents are affected.

Options:

- **Denormalize into the document:** fast queries with no search-time joins, but related updates require fan-out.
- **Store reference IDs:** the indexer or API fetches details from owning services, reducing duplication at the cost of extra calls and latency.
- **Domain-owned projector:** one projector owns the search document and aggregates required domain events.
- **Query-time joins:** more flexible in certain engines, yet can raise latency and distributed complexity.

When a property changes cities or is deleted, identify affected documents, caches, and saved results. For large one-to-many fan-outs, queue and batch updates to prevent indexing storms.

## 10. Reindexing, Backfills, and Mapping Changes

When analyzers, field mappings, or document schemas change, never alter a live production index without a rollback path. A standard pattern is **blue-green indexing**:

~~~mermaid
flowchart TD
    SRC[("Operational DB / CDC")]
    PIPE["Projection pipeline"]
    OLD[("Search Index v1")]
    NEW[("Search Index v2")]
    ALIAS["Read alias"]
    SRC --> PIPE
    PIPE --> OLD
    PIPE --> NEW
    OLD --> ALIAS
    NEW -. build + validate .-> ALIAS
~~~

Workflow:

1. Create Index v2 with the new mappings/analyzers.
2. Take a source snapshot or record a safe starting checkpoint.
3. Backfill v2 in batches.
4. Concurrently stream live updates during backfill, using watermarks/versions so stale snapshot rows never overwrite fresher updates.
5. Compare document counts, field coverage, sample queries, relevance, freshness, and mapping errors.
6. Route canary/shadow queries to v2.
7. Flip the read alias/routing to v2 once criteria pass.
8. Retain v1 for the defined rollback window before retiring it.

Never rely solely on document counts to declare a reindex valid. Documents can miss fields, use wrong analyzers, or hold stale versions even when total counts match. Verify with sample audits, representative query suites, and source reconciliation.

### 10.1. Backfills Must Not Overload the Operational Database

Backfilling millions of records can put heavy read pressure on OLTP. Safeguards:

- Read from a replica or export/snapshot where architecture allows and freshness suffices.
- Batch with bounded concurrency, rate limits, and checkpoints.
- Schedule during low-traffic windows or approved maintenance slots.
- Monitor CPU, I/O, locks, replication lag, and transactional latency.
- Support pause/resume, idempotent retries, and progress tracking.
- Isolate backfill queues from real-time streams so live updates are never starved.

## 11. Search Queries and Protecting the Operational Database

Separating a search store only helps if the Search API avoids turning search hits into a storm of heavy operational DB lookups.

### 11.1. Avoiding N+1 Lookups

Suppose search returns 100 property IDs and the API fires 100 individual DB queries for names, photos, and prices. The OLTP database still takes heavy load even though the main search ran elsewhere.

Mitigations:

- Store non-sensitive display fields directly in the search document.
- Batch-fetch IDs instead of querying one by one.
- Use read models/caches for low-sensitivity display attributes.
- Query the authoritative source only for checks required before transactional actions.
- Cap page sizes and returned fields.

### 11.2. Search Followed by Booking Confirmation

Reference flow:

1. Search store matches eligible properties/rooms and returns candidates.
2. User picks an option.
3. Booking Service receives the request and validates permissions, dates, guest count, final price, and availability at the authoritative source.
4. The service executes a hold/transaction following concurrency rules.
5. Post-commit, outbox/events update the search projection as needed.

Search results may be slightly stale, yet must never produce an invalid confirmed booking. When the authoritative check rejects a stale candidate, the UI should clearly inform the user that availability or price just changed.

## 12. HA, Backups, and Recovery for the Search Store

Even though a search store can be rebuilt from the source and pipeline, you cannot skip HA or backups. Reindexing billions of records can take hours or days, strain the source database, and violate SLOs.

| Objective | Design Questions |
| --- | --- |
| Availability | Does the search cluster distribute replicas/shards across fault domains? |
| Recovery | Can it restore from snapshots or must it rebuild from scratch; how long does each take? |
| RPO | How many index updates could be lost on recovery? Do source and log/event retention cover rebuilding? |
| RTO | Must search return in minutes, or can it run in degraded mode during rebuild? |
| Capacity | Do replacement nodes have enough CPU/memory/disk to allocate shards and index catch-up traffic? |
| Pipeline | Can offsets/checkpoints, outbox/CDC backlogs, and schema mappings resume cleanly after failure? |

### 12.1. Controlled Degradation Plan

If the search store becomes temporarily unavailable:

- Return retryable errors or serve safe cached results.
- Keep core booking transactions and authoritative data operations running independently if the business allows.
- Never fall back to heavy full-table scans on the OLTP database.
- Temporarily disable expensive filters rather than overloading the database.
- Monitor sync backlogs and execute catch-up once the search store recovers.

Search result caches carry their own freshness and privacy constraints. Never serve one tenant's cached search results to another, or keep serving hidden/deleted items when policy mandates immediate removal.

## 13. Security and Data Governance in the Search Store

Search indexes often have broader read access than operational databases to support multiple apps. Design permissions and data minimization deliberately:

- Index only required fields; never place passwords, tokens, payment details, or unnecessary PII in search documents.
- Use private network endpoints/security policies and TLS between apps/indexers and the search cluster.
- Authenticate service identities and scope permissions per index/collection and query/write/admin role.
- Enforce tenant filtering server-side from verified identity; never trust client-supplied tenant filters alone.
- Protect sensitive fields via field-level security and response projections.
- Query logs can capture personal search terms; apply masking, retention limits, and strict log access controls.
- Enforce encryption, access controls, and data-residency policies on search snapshots, backups, and exports too.

### 13.1. Search Query Injection and Resource Abuse

Never concatenate client query strings directly into DSL/query syntax without validation. Bound query depth, clause counts, wildcards/regexes, aggregation buckets, page sizes, and timeouts per engine capabilities. Even a syntactically valid query can be prohibitively expensive. Rate-limit by route and query cost, not just raw requests/sec.

## 14. Observing the Pipeline and Search Quality

Monitor both sides: **technical health of the index** and **quality of user results**.

| Category | Metrics / Signals to Track |
| --- | --- |
| Source | Transaction latency, DB CPU/IO, log retention, replication lag |
| Pipeline | Outbox/CDC backlog, oldest event age, consumer lag, retries, DLQs, processing rate |
| Indexing | Indexing latency, bulk failures, rejected documents, mapping exceptions, refresh lag |
| Search cluster | Query p95/p99, CPU, memory/heap, disk, shard allocation, rejected queries, cache hits |
| Freshness | Elapsed time from source commit until the document version appears in search |
| Correctness | Document counts, missing fields, duplicate/stale versions, sample mismatches |
| Search quality | Zero-result rate, click-through rate, conversion, relevance feedback, filter success |
| Security | Cross-tenant access attempts, forbidden field exposure, unusual exports/queries |
| Cost | Storage/index replicas, ingest, query compute, cross-zone traffic, snapshots, reindexing |

Never optimize NDCG or click-through rates by sacrificing pricing or inventory accuracy. Search relevance guides ranking; authoritative sources and business rules remain mandatory gates for transactions.

## 15. Design Process and Architectural Decisions

~~~mermaid
flowchart TD
    A["Define search access patterns and SLOs"]
    A --> B{"Does OLTP meet load and features?"}
    B -->|Yes| C["Keep suitable queries in the database"]
    B -->|No| D["Design search projection/store"]
    D --> E["Choose outbox, CDC, or polling"]
    E --> F["Define mappings, freshness, and versioning"]
    F --> G["Backfill + dual-run + validation"]
    G --> H["Canary / cutover / rollback"]
    H --> I["Observe freshness, quality, SLOs, and cost"]
    I --> J["Reconcile, tune, and review"]
~~~

For every query flow, document:

1. User/actor and business goal.
2. Fields to search, filter, sort, aggregate, and display.
3. Which fields tolerate lag versus require real-time verification.
4. Authoritative source for each field and delete handling.
5. Write frequency, read frequency, bursts, document size, and growth rate.
6. Sync mechanism, versioning, deduplication, retries, backfills, and reconciliation.
7. Security, tenant isolation, retention, backups, and access controls.
8. SLIs/SLOs, runbooks, degraded modes, RTO/RPO, and cost.

## 16. Lab: Separating Search from a Booking System

**Hypothetical scenario:** A platform has 5 million properties/rooms, 20 million search queries per day, 100,000 property updates per day, and even more frequent price/availability changes. OLTP handles bookings and payments; search currently relies on heavy multi-table joins that push transactional p95 latency higher.

### Tasks

1. List at least eight search access patterns and classify which queries should stay in the operational database.
2. Design the search document/projection; specify searchable, filterable, sortable, and facetable fields, plus sensitive fields excluded from indexing.
3. Choose outbox, CDC, or polling; diagram the end-to-end flow from source commit → pipeline → index visibility.
4. Define freshness SLOs for descriptions, amenities, prices, room availability, and hidden/deleted content.
5. Design versioning, idempotency, handling of duplicate/out-of-order events, tombstones, and reconciliation.
6. Design a v2 reindexing workflow with backfill, catch-up stream, quality validation, canary, cutover, and rollback.
7. Design a degraded mode when the search store goes down without overloading OLTP.
8. Define metrics for the pipeline, search cluster, search relevance, security, and cost.
9. Write an ADR explaining why an independent search store is needed, rejected alternatives, and remaining trade-offs.

### Sample Source-of-Truth Matrix

| Field | Authoritative Source | Indexed? | Used to Confirm Transactions? |
| --- | --- | --- | --- |
| Property name/description | Property Service DB | Yes | No |
| City/amenities | Property Service DB | Yes | Can filter candidates; not a commit condition |
| Search rating summary | Review Service DB/projection | Yes | No |
| Advertised price | Pricing Service DB | Can index for rough ranking | Must verify final price at Pricing/Booking |
| Availability | Inventory/Booking Service | Optional cache/projection | Must verify real-time before hold/booking |
| Payment status | Payment Service DB | Not needed for search | Only Payment Service is authoritative |

### Completion Criteria

- Clearly separates OLTP from the search store; never treats the index as source of truth.
- Search projection serves queries without duplicating unnecessary sensitive data.
- Pipeline supports retries, deduplication, backfills, and reconciliation.
- Freshness is measured from source commit to index visibility with per-field SLOs.
- Reindexing avoids overloading OLTP and supports cutover/rollback.
- Search failures neither break transactions nor trigger dangerous full-scan fallbacks.
- Tenant isolation, permissions, retention, backups, RTO/RPO, and cost are controlled.

## 17. Well-Architected Checklist Before Deploying a Search Store to Production

- [ ] Verified that queries and load genuinely require a separate search store.
- [ ] Operational database remains the authoritative source for transactional state.
- [ ] Search projection includes only needed fields and has an owner and mapping contract.
- [ ] Full-text, exact, numeric, geo, vector fields, and analyzers match access patterns.
- [ ] Outbox/CDC/polling has checkpoints, retries, deduplication, and explicit delete semantics.
- [ ] Per-entity versioning prevents older events from overwriting newer documents.
- [ ] Freshness SLOs are measured from source commit to index visibility.
- [ ] Pricing, availability, permissions, and sensitive state are verified at authoritative sources.
- [ ] Backfill/reindexing, dual-run, validation, canary, alias switch, and rollback exist.
- [ ] Backfills never overload OLTP; real-time pipelines are protected from starvation.
- [ ] Reconciliation detects missing, duplicate, stale, or mis-mapped documents.
- [ ] Search store has appropriate HA, snapshot/rebuild strategy, capacity, and RTO/RPO.
- [ ] Degraded mode avoids fallbacks that trigger full scans or pressure transactional DBs.
- [ ] Tenant isolation, IAM, TLS, field minimization, retention, and auditing are verified.
- [ ] Metrics cover query latency, index freshness, backlogs, relevance, security, and cost.
- [ ] ADR documents trade-offs across reliability, security, performance, cost, and operations.

**Key takeaway:** Separating the search store from the operational database lets each engine optimize for its own workload and cuts resource contention. In exchange, the architecture must manage **projections, asynchronous syncing, consistency lag, duplicate events, reindexing, security, and recovery**. A design succeeds only when the search store accelerates queries without corrupting authoritative data or endangering business transactions.
