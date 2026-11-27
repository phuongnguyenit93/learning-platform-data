# Composite Indexes and Property Ordering by Query Pattern in Neo4j

In **Neo4j**, a query can filter nodes or relationships by multiple properties: for example, finding tickets belonging to a customer, currently open, and created within a time window. When such queries run frequently across millions of entities, a **composite index** can help reduce the amount of data read. However, deciding which order to place properties in the index is a design choice: the same set of properties in different orders serves different `WHERE` and `ORDER BY` patterns.

This lesson belongs to the **Lookup Indexes** chapter, covering the **property graph** model, **Cypher** queries, and Neo4j query tuning. We will analyze how to choose property ordering, create sample data and indexes, inspect execution plans, and weigh index maintenance overhead in applications using the **Neo4j Java Driver** or **Spring Data Neo4j**.

## 1. Distinguishing Lookup Indexes from Composite Property Indexes

In Neo4j, distinguish two concepts often loosely referred to as "lookup indexes":

| Index Type | Lookup Key | Example Purpose |
| --- | --- | --- |
| **Token lookup index** | Node label or relationship type | Finding `:Ticket` nodes or `:ASSIGNED_TO` relationships |
| **Property range index** | One or more **properties** of a node/relationship | Filtering `t.tenantId`, `t.status`, `t.createdAt` |
| **Composite range index** | An **ordered sequence** of properties | Combined filtering on `(tenantId, status, createdAt)` |

**Lookup indexes do not store `tenantId`, `status`, or `createdAt` values.** In this lesson, "composite index" primarily refers to a **composite RANGE index** on properties, created with `CREATE RANGE INDEX`. Do not confuse it with `CREATE LOOKUP INDEX`, which is for labels and relationship types.

Example of a composite index on a node:

```cypher
CREATE RANGE INDEX ticket_tenant_status_created IF NOT EXISTS
FOR (t:Ticket)
ON (t.tenantId, t.status, t.createdAt);
```

The properties `tenantId`, `status`, and `createdAt` form an ordered key sequence exactly as declared. When reading execution plans, check whether Neo4j can leverage that key sequence to seek and/or sort results.

> **Scope:** Index selection here focuses on `RANGE` indexes for equality predicates, range comparisons, and sorting. Full-text search, strings requiring linguistic analysis, or geographic data may require other index types and optimization approaches.

## 2. Start from Query Patterns, Not from a List of Properties

Suppose a support system has nodes:

```text
(:Ticket {
  ticketId: "TK-001",
  tenantId: "ACME",
  status: "OPEN",
  createdAt: datetime("2026-11-03T08:00:00Z"),
  priority: 2
})
```

The application has the following requirements:

- **Q1:** Within tenant `ACME`, fetch `OPEN` tickets from November, newest first, up to 20 tickets.
- **Q2:** Within tenant `ACME`, fetch all tickets from November, without filtering on `status`.
- **Q3:** Find all `OPEN` tickets across tenants over a date range, for the system-wide operations team.
- **Q4:** Look up a single ticket by `ticketId`.

All of them query `Ticket` data, yet they are not necessarily optimized by **a single** composite index.

Typical Q1 pattern:

```cypher
MATCH (t:Ticket)
WHERE t.tenantId = 'ACME'
  AND t.status = 'OPEN'
  AND t.createdAt >= datetime('2026-11-01T00:00:00Z')
  AND t.createdAt < datetime('2026-12-01T00:00:00Z')
RETURN t.ticketId AS ticketId,
       t.status AS status,
       t.createdAt AS createdAt
ORDER BY t.createdAt DESC
LIMIT 20;
```

Each part of the query plays a distinct role:

| Expression | Condition Type | Role |
| --- | --- | --- |
| `t.tenantId = 'ACME'` | **Equality** | Narrows down to one tenant |
| `t.status = 'OPEN'` | **Equality** | Narrows further by status |
| `t.createdAt >= ... AND < ...` | **Range** | Selects a time interval |
| `ORDER BY t.createdAt DESC` | **Ordering** | Prioritizes newest tickets |
| `LIMIT 20` | Result limit | Only needs a small batch after filtering/sorting |

Based on this pattern, the index `(tenantId, status, createdAt)` is a **strong candidate**: the two equality-filtered properties come first, followed by the range-filtered and sorted property.

## 3. Ordering Rule: Equality First, Range/Sort After

A practical guideline when designing composite range indexes is:

1. Place properties commonly compared with **equality** (`=`) at the front.
2. Place the property commonly compared as a **range** (`<`, `<=`, `>`, `>=`) after the equality group.
3. Consider `ORDER BY`: if sorting by the property immediately following the equality prefix and the plan shape fits, Neo4j **can** leverage index order instead of sorting many records.
4. Always verify with `EXPLAIN` and `PROFILE`; this is a **design guideline**, not a guarantee that the planner will choose the index for every data size or Neo4j version.

Visualize the key ordering of `(tenantId, status, createdAt)` as nested groups:

```text
tenantId
├── ACME
│   ├── CLOSED
│   │   └── createdAt: ...
│   └── OPEN
│       ├── createdAt: 2026-11-03
│       ├── createdAt: 2026-11-20
│       └── createdAt: 2026-11-25
└── BETA
    └── OPEN
        └── createdAt: ...
```

When both `tenantId` and `status` are known, the relevant `createdAt` values reside in a contiguous key region. When **omitting the `status` condition**, data for the same tenant is still partitioned by status; this index will not necessarily provide range seeking or time ordering as effectively as `(tenantId, createdAt)`.

### Comparing Three Orders over the Same Property Set

| Index Order | For Q1 (tenant =, status =, createdAt range) | For Q2 (tenant =, createdAt range) |
| --- | --- | --- |
| `(tenantId, status, createdAt)` | Strong candidate: equality before range | Has a `status` gap before `createdAt` |
| `(tenantId, createdAt, status)` | Can narrow by tenant and date range; `status` sits after range | Strong candidate for Q2 |
| `(createdAt, tenantId, status)` | Leads with time range; may need to inspect more tenants | Only worth considering if cross-tenant time-range queries dominate |

**No single order is optimal for every query.** Base the design on which queries run most often, data volume per tenant/status, range width, and sorting requirements.

### How Should "Leftmost Prefix" Be Understood?

With an index `(A, B, C)`, predicate patterns starting from `A`, then `B`, then `C` generally have an advantage. For example:

- `A = ... AND B = ... AND C >= ...`: has contiguous predicates across all three fields, fitting `(A, B, C)` very well.
- `A = ... AND B = ...`: forms a contiguous prefix; exact utilization depends on index type and execution plan.
- `A = ... AND C >= ...`: skips `B`; do not assume the index will seek efficiently directly on `C`.
- `B = ... AND C >= ...`: lacks the leading property `A`; do not treat `(A, B, C)` as a drop-in substitute for `(B, C)`.

Neo4j may choose **index seek**, **index scan**, post-filtering, or a label scan depending on version, predicate type, statistics, and selectivity. Therefore, use "leftmost prefix" as an **analytical principle**, rather than assuming any query missing a prefix can never use the index at all.

## 4. Runnable Example: Data, Indexes, and Queries

The commands in this section are for a **practice database** and can be executed sequentially in Neo4j Browser or Cypher Shell.

### 4.1. Creating the Constraint and Six Sample Tickets

The constraint below enforces unique `ticketId` values. This is a data integrity rule; the index serving multi-property filtering will be created separately in the next step.

```cypher
CREATE CONSTRAINT ticket_id_unique IF NOT EXISTS
FOR (t:Ticket)
REQUIRE t.ticketId IS UNIQUE;
```

```cypher
UNWIND [
  {id: 'TK-001', tenant: 'ACME', state: 'OPEN',
   at: '2026-11-03T08:00:00Z', priority: 2},
  {id: 'TK-002', tenant: 'ACME', state: 'OPEN',
   at: '2026-11-20T10:00:00Z', priority: 1},
  {id: 'TK-003', tenant: 'ACME', state: 'CLOSED',
   at: '2026-11-15T11:00:00Z', priority: 3},
  {id: 'TK-004', tenant: 'ACME', state: 'OPEN',
   at: '2026-10-22T09:00:00Z', priority: 2},
  {id: 'TK-005', tenant: 'BETA', state: 'OPEN',
   at: '2026-11-24T07:00:00Z', priority: 1},
  {id: 'TK-006', tenant: 'ACME', state: 'OPEN',
   at: '2026-11-25T13:00:00Z', priority: 3}
] AS row
MERGE (t:Ticket {ticketId: row.id})
SET t.tenantId = row.tenant,
    t.status = row.state,
    t.createdAt = datetime(row.at),
    t.priority = row.priority;
```

Key point: `createdAt` is a **temporal `datetime`** value, not an arbitrary string. When filtering time ranges, comparison values must have a compatible type. Keep time zones consistent when storing and comparing timestamps.

### 4.2. Creating the Index for Q1

```cypher
CREATE RANGE INDEX ticket_tenant_status_created IF NOT EXISTS
FOR (t:Ticket)
ON (t.tenantId, t.status, t.createdAt);
```

Verify the index was created and finished building:

```cypher
SHOW INDEXES
YIELD name, type, labelsOrTypes, properties, state
WHERE name = 'ticket_tenant_status_created'
RETURN name, type, labelsOrTypes, properties, state;
```

Only evaluate index plan usage after its state becomes `ONLINE`. On datasets with many existing records, bringing an index to `ONLINE` can take time.

### 4.3. Running Q1: Tenant + Status + Date Range

```cypher
MATCH (t:Ticket)
WHERE t.tenantId = 'ACME'
  AND t.status = 'OPEN'
  AND t.createdAt >= datetime('2026-11-01T00:00:00Z')
  AND t.createdAt < datetime('2026-12-01T00:00:00Z')
RETURN t.ticketId AS ticketId, t.createdAt AS createdAt
ORDER BY t.createdAt DESC
LIMIT 20;
```

Expected logical output for the sample dataset:

| ticketId | createdAt (UTC) |
| --- | --- |
| `TK-006` | `2026-11-25T13:00:00Z` |
| `TK-002` | `2026-11-20T10:00:00Z` |
| `TK-001` | `2026-11-03T08:00:00Z` |

`TK-003` does not match `OPEN`, `TK-004` falls outside November, and `TK-005` belongs to another tenant. An index **speeds up lookups**, yet **never alters the logically correct result set**.

### 4.4. Running Q2: Tenant + Date Range, Without Status

```cypher
MATCH (t:Ticket)
WHERE t.tenantId = 'ACME'
  AND t.createdAt >= datetime('2026-11-01T00:00:00Z')
  AND t.createdAt < datetime('2026-12-01T00:00:00Z')
RETURN t.ticketId AS ticketId,
       t.status AS status,
       t.createdAt AS createdAt
ORDER BY t.createdAt DESC
LIMIT 20;
```

Q2 also returns `CLOSED` tickets, so a separate index is a candidate worth evaluating if Q2 is frequent and data volume is large:

```cypher
CREATE RANGE INDEX ticket_tenant_created IF NOT EXISTS
FOR (t:Ticket)
ON (t.tenantId, t.createdAt);
```

Comparing the two indexes:

```text
(tenantId, status, createdAt)  -> suitable for Q1
(tenantId,         createdAt)  -> suitable for Q2
```

If **only** the three-property index exists, the optimizer can use the applicable portion of it, but having `status` between `tenantId` and `createdAt` can make the range filter and sorting less favorable. Measure this on a realistic dataset.

### 4.5. Running Q3: Status + Date Range, Without Tenant

```cypher
MATCH (t:Ticket)
WHERE t.status = 'OPEN'
  AND t.createdAt >= datetime('2026-11-01T00:00:00Z')
RETURN t.ticketId AS ticketId, t.tenantId AS tenantId
ORDER BY t.createdAt DESC
LIMIT 20;
```

If Q3 is an important query path, you can **consider**:

```cypher
CREATE RANGE INDEX ticket_status_created IF NOT EXISTS
FOR (t:Ticket)
ON (t.status, t.createdAt);
```

Do not create every index listed just because the syntax is valid. Each additional index consumes storage and adds write-maintenance overhead. Retain only indexes proven valuable under realistic workloads.

## 5. Does the Order Among Equality Properties Matter?

For Q1, both indexes below place **the two equality conditions** before **the range condition**:

```text
(tenantId, status, createdAt)
(status, tenantId, createdAt)
```

If a query always binds both `tenantId = ...` **and** `status = ...`, both are **reasonable candidates**; never claim one order is always faster without checking statistics and execution plans.

Across the system as a whole, however:

- Queries filtering **only by tenant** will better match an index starting with `tenantId`.
- Queries filtering **only by status** will better match an index starting with `status`.
- `status` typically has only a few values like `OPEN`/`CLOSED`, whereas `tenantId` may have many values; each predicate's selectivity depends on data distribution.
- Data density and distribution can shift over time; measure on representative data rather than relying solely on the intuition that "the highest-cardinality field must go first."

Choose equality ordering based on **common query combinations**, prefix reusability, and observed effectiveness, rather than applying a rigid rule to every model.

## 6. Index Order and `ORDER BY`

Beyond `WHERE` conditions, many list screens also request:

```cypher
ORDER BY t.createdAt DESC
LIMIT 20
```

With the `(tenantId, status, createdAt)` index and both `tenantId` and `status` pinned by equality, keys ordered by `createdAt` can suit fetching the newest tickets. If the planner supports using index order in this case, the query can avoid a costly sort.

The following case, however, is **different**:

```cypher
MATCH (t:Ticket)
WHERE t.tenantId = 'ACME'
RETURN t.ticketId, t.status, t.createdAt
ORDER BY t.createdAt DESC
LIMIT 20;
```

If only the `(tenantId, status, createdAt)` index exists, `ACME`'s tickets are grouped by `status` first and only then by `createdAt`. That tenant's entire ticket set is **not** automatically in global chronological order. For this query, `(tenantId, createdAt)` is a more natural candidate.

**Verification point:** Never infer that a query avoided sorting solely because an index exists. Check whether `Sort`/`Top` operators appear in the plan, whether `Ordered by` appears on index operators (depending on version/tool), and how many actual rows flow through each step. `LIMIT` does not automatically make a query fast if too many results must be scanned or sorted beforehand.

## 7. Using `EXPLAIN` and `PROFILE` to Verify

Two logically equivalent queries can receive different execution plans depending on existing data and indexes.

- `EXPLAIN`: **plans** without executing the query; used to see how Neo4j intends to access data.
- `PROFILE`: **actually runs the query** and adds row counts and data access counts (such as `DB Hits`) to evaluate the plan.
- For performance measurements, run on representative data, compare across multiple runs, and account for cache effects; do not draw conclusions from a six-node sample set.

Start with:

```cypher
EXPLAIN
MATCH (t:Ticket)
WHERE t.tenantId = 'ACME'
  AND t.status = 'OPEN'
  AND t.createdAt >= datetime('2026-11-01T00:00:00Z')
  AND t.createdAt < datetime('2026-12-01T00:00:00Z')
RETURN t.ticketId, t.createdAt
ORDER BY t.createdAt DESC
LIMIT 20;
```

Then you can replace `EXPLAIN` with `PROFILE` to collect execution metrics:

```cypher
PROFILE
MATCH (t:Ticket)
WHERE t.tenantId = 'ACME'
  AND t.status = 'OPEN'
  AND t.createdAt >= datetime('2026-11-01T00:00:00Z')
  AND t.createdAt < datetime('2026-12-01T00:00:00Z')
RETURN t.ticketId, t.createdAt
ORDER BY t.createdAt DESC
LIMIT 20;
```

When reading the plan, ask:

1. Did Neo4j use `NodeIndexSeek`, `NodeIndexScan`, or `NodeByLabelScan` (operator names may vary by version)?
2. Which index was actually chosen? Which properties participated in the seek, and which still required `Filter`?
3. Was `ORDER BY` satisfied by index order, or did it go through `Sort`/`Top`?
4. Did input/output row counts, `DB Hits`, and latency decrease on **representative data**?
5. Are the index creation and update costs justified by the number of read queries improved?

A plan **not using an index on six nodes** does not prove the index is wrong. On tiny datasets, a label scan can be cheaper. Conversely, seeing `NodeIndexSeek` does not prove the query is well optimized if it still filters or sorts a huge volume of data afterward.

### When Should You Try `USING INDEX`?

Cypher provides index hints to guide the planner in certain cases:

```cypher
MATCH (t:Ticket)
USING INDEX t:Ticket(tenantId, status, createdAt)
WHERE t.tenantId = 'ACME'
  AND t.status = 'OPEN'
  AND t.createdAt >= datetime('2026-11-01T00:00:00Z')
RETURN t.ticketId, t.createdAt;
```

Use hints only when you know the index exists, the query shape matches, and the automatic plan is demonstrably suboptimal. A hint **does not replace** choosing the right index structure or measuring with `PROFILE`; it can also make plans less adaptable when statistics or Neo4j versions change.

## 8. Common Pitfalls That Lead to Poor Index Selection

### 8.1. Filtering with a Function on the Property

For example:

```cypher
WHERE date(t.createdAt) = date('2026-11-25')
```

Applying a function to `t.createdAt` can prevent the planner from directly leveraging a range condition on the indexed property. When storing `createdAt` as `datetime`, consider rewriting the date filter as a range:

```cypher
WHERE t.createdAt >= datetime('2026-11-25T00:00:00Z')
  AND t.createdAt < datetime('2026-11-26T00:00:00Z')
```

The time interval must be constructed in the proper **business time zone**; the example above expresses a UTC day, not a local day by default.

### 8.2. Only Some Properties Have Values

Composite property indexes rely on indexed properties actually having values. For nodes missing `status` or `createdAt`, do not expect a three-property index to satisfy every lookup pattern the way a standalone `tenantId` index would. Check property mandatory rules and actual `IS NULL`/`IS NOT NULL` patterns before deciding.

### 8.3. Using One Overly Wide Index for Every Query

An index `(tenantId, status, createdAt, priority, ownerId)` sounds "comprehensive," yet it does not automatically serve queries filtering only on `priority` or sorting only on `createdAt`. Extra properties bloat index size and update costs and can keep prefix-missing queries from exploiting the fields they need.

### 8.4. Creating Too Many Nearly Duplicate Indexes

Every time `status`, `createdAt`, or `tenantId` changes on a `Ticket` node, affected indexes may need updating. Every index also consumes storage and administrative overhead. In write-heavy systems, monitor **write cost**, not just read speed.

### 8.5. Using the Wrong Index Type

A composite range index on properties is not the default solution for every problem:

- Looking up **node labels** / **relationship types**: lookup index.
- Filtering, range comparisons, and ordering on multiple properties: consider range index.
- Free-text search: consider full-text index or an appropriate text index depending on predicate type.
- Spatial search with coordinates: consider point index.

### 8.6. Assuming Indexes Define Data Correctness

Indexes provide **fast access**; constraints enforce **data rules**, such as unique `ticketId`. Choosing an index does not replace validating data types, tenant isolation, relationship direction, or business parameter checks.

## 9. Applying to Relationships and Java Applications

A property graph can store properties directly on relationships. Composite range index syntax for relationships mirrors node indexes:

```cypher
CREATE RANGE INDEX road_region_class IF NOT EXISTS
FOR ()-[r:ROAD]-()
ON (r.region, r.roadClass);
```

This index is a candidate for queries finding `ROAD` edges by region and road class; it does **not** automatically optimize multi-hop shortest-path searches. Path queries also depend on graph topology and traversal algorithms.

In the **Neo4j Java Driver** or **Spring Data Neo4j**, pass `tenantId`, `status`, and timestamps as **parameters** rather than concatenating user input into Cypher strings. Example application-side statement:

```cypher
MATCH (t:Ticket)
WHERE t.tenantId = $tenantId
  AND t.status = $status
  AND t.createdAt >= $from
  AND t.createdAt < $to
RETURN t.ticketId, t.createdAt
ORDER BY t.createdAt DESC
LIMIT 20;
```

`$from`/`$to` parameters should be bound using temporal types compatible with `createdAt`. Data values vary per user request; index structures and primary predicates should still be designed around the application's **stable query patterns**.

## 10. Quick Decision Table for Query Patterns

| Frequent Cypher Pattern | Index to Evaluate | Reason |
| --- | --- | --- |
| `tenantId = x AND status = y AND createdAt BETWEEN ...` | `(tenantId, status, createdAt)` | Two equalities before the time range |
| `tenantId = x AND createdAt >= ...` | `(tenantId, createdAt)` | No `status` intervening |
| `status = y AND createdAt >= ...` | `(status, createdAt)` | Serves cross-tenant queries |
| `tenantId = x ORDER BY createdAt DESC LIMIT k` | `(tenantId, createdAt)` | Opportunity to leverage date ordering within one tenant |
| `ticketId = id` | Appropriate constraint/index on `ticketId` | Point lookup by unique identifier |
| `createdAt >= ...` across all tenants | `(createdAt)` | No tenant/status prefix needed |

`BETWEEN` in the table is shorthand illustrating a value interval; in actual Cypher, write `>=` and `<` predicates as in earlier examples.

This is a **list of candidates to evaluate**, not a mandate to create every index. Prioritize critical queries, measure with `PROFILE`, examine read/write workloads, and keep the smallest index set that meets performance targets.

## 11. Self-Check Questions

**Question 1.** An index `(tenantId, status, createdAt)` is serving a query finding `OPEN` tickets for one tenant well. The product adds an "all statuses, newest first" screen. Why should you evaluate adding `(tenantId, createdAt)`?

<details>
<summary>Suggested Answer</summary>

Because the new screen does not constrain `status`. The three-property index groups results by `status` before `createdAt`, so it does not naturally provide a tenant-wide chronological `createdAt` order. The two-property index aligns better with the `tenantId` equality prefix and the chronological sort goal.

</details>

**Question 2.** For the query `WHERE tenantId = x AND status = y AND createdAt >= start`, can we assert that `(tenantId, status, createdAt)` is always faster than `(status, tenantId, createdAt)`?

<details>
<summary>Suggested Answer</summary>

No. Both place equalities before the range predicate and can be good candidates. The decision also depends on other queries filtering only one of the two fields, data distribution, statistics, and `EXPLAIN`/`PROFILE` plans.

</details>

**Question 3.** The `ticket_tenant_status_created` index is `ONLINE`, yet `PROFILE` still shows a label scan. Is this necessarily a bug?

<details>
<summary>Suggested Answer</summary>

No. The planner may estimate a label scan as cheaper on very small data or when predicates are not selective enough. Check predicate types, data size and distribution, statistics, and execution costs before changing indexes or forcing an index hint.

</details>

**Question 4.** If a query filters November using `date(t.createdAt) = date('2026-11-25')`, how should you consider rewriting it?

<details>
<summary>Suggested Answer</summary>

Convert it into a date range on the raw property, such as `t.createdAt >= datetime('2026-11-25T00:00:00Z') AND t.createdAt < datetime('2026-11-26T00:00:00Z')` when days are defined in UTC. This expresses the range predicate directly on the property, giving the planner a better opportunity to use the range index effectively.

</details>

## Key Takeaways

- **A composite index is an ordered sequence of properties**; that order should reflect your most important `WHERE` and `ORDER BY` patterns.
- For equality plus range filters, **equality first, range/sort after** is a useful starting point.
- **Skipping a property in the middle of a prefix** can make the index poorly suited to a query; one three-property index does not automatically replace every two-property index.
- **Lookup indexes** for labels/relationship types differ from **composite range indexes** on properties.
- Only evaluate speed using **`EXPLAIN`/`PROFILE` on representative data**; balance read gains against index storage and update costs.

### References

- [Neo4j Cypher Manual — Indexes for search performance](https://neo4j.com/docs/cypher-manual/current/indexes/search-performance-indexes/overview/)
- [Neo4j Cypher Manual — Indexes and query performance](https://neo4j.com/docs/cypher-manual/current/indexes/search-performance-indexes/using-indexes/)
- [Neo4j Cypher Manual — Query tuning (EXPLAIN, PROFILE)](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/query-tuning/)
