# Balancing Read Speed Against Write Cost, Storage, and Index Maintenance

In Neo4j, an *index* helps Cypher locate nodes and relationships faster without scanning the entire graph. However, every index is also a data structure that must be stored, maintained, and monitored. For a **DATABASE_ENGINE_GRAPH_NEO4J** system, the goal is not "create as many indexes as possible," but rather choosing indexes that enable critical queries to meet required performance at acceptable write, storage, and operational costs.

The **Lookup Indexes** chapter focuses on **token lookup indexes**—indexes that look up **node labels** and **relationship types**. To balance costs accurately, distinguish them from **property indexes** such as range, text, and point indexes, which resolve predicates on property values.

## 1. Which Queries Do Lookup Indexes Support?

A property graph in Neo4j consists of nodes, relationships, and properties. In a sales system, there may be **Customer**, **Product**, and **Order** nodes along with **PURCHASED** and **VIEWED** relationships. When running:

~~~cypher
MATCH (c:Customer)
RETURN c
LIMIT 20;
~~~

Neo4j needs to find nodes carrying the **Customer** label. The **node label lookup index** can assist in accessing this node set. Similarly:

~~~cypher
MATCH ()-[r:PURCHASED]->()
RETURN r
LIMIT 20;
~~~

The **relationship type lookup index** can help look up relationships of type **PURCHASED**. The *query planner* chooses to use the index or an alternative access strategy depending on the query, data, statistics, and version.

| Characteristic | Node Label Lookup | Relationship Type Lookup |
|---|---|---|
| Mapping | Label → nodes carrying that label | Type → relationships of that type |
| Supported predicates | **MATCH (n:Customer)** | **MATCH ()-[r:PURCHASED]->()** |
| Does not directly resolve | **n.email = $email**, **n.age > 18** | **r.amount > 100**, **r.createdAt > $t** |
| Scope | All labels in the database | All relationship types in the database |
| Maximum count | **One** | **One** |

In a new Neo4j database, **both lookup indexes are pre-created by default**. They also assist during the initial *population* of other indexes. Dropping them can cause severe performance degradation and is not a standard write optimization.

**Critical limitation:** a lookup index is **not** an index on a property. Even with a lookup index for the Customer label, a query finding a Customer by email may still have to scan the Customer set and filter on email unless an appropriate property index exists.

**Version compatibility:** databases created on **Neo4j 4.3 or later** usually have both default lookup indexes. Databases created prior to 4.3 and upgraded may lack the relationship type lookup index; use **SHOW** commands to verify rather than guessing.

## 2. Four Dimensions of an Indexing Decision

| Trade-off Dimension | Benefit or Cost | What to Verify |
|---|---|---|
| **Read speed** | Narrows the set of nodes/relationships inspected | How much does query p95 improve? How many DB Hits are saved? |
| **Write cost** | Modifying indexed data triggers index updates | How do write latency and transaction throughput change? |
| **Storage** | Indexes consume disk space, add I/O load, and can increase page cache pressure | Actual index size, growth rate, and I/O usage? |
| **Maintenance** | Indexes must be built, status-monitored, deployed, and recovered if needed | Is it ONLINE? How long does population take? Any FAILED errors? |

There is no fixed formula like "adding one index slows writes by 10%." Impact depends on node and relationship counts, write patterns, label counts, property index counts, data distribution, query frequency, hardware, and Neo4j version.

### 2.1. Faster Reads Depend on Selectivity

Example:

~~~cypher
MATCH (c:Customer {email: $email})
RETURN c;
~~~

If the dataset has millions of Customers and emails are nearly unique, finding by label alone and then filtering email can require substantial work. A suitable **range index** or **uniqueness constraint** on Customer.email lets the planner consider direct property-value access, typically via an operator like **NodeIndexSeek**. With only a few nodes, the planner may instead estimate a label scan as cheaper.

**An index only helps when queries actually have an access path that leverages it.** Queries returning most of the database, computing graph-wide aggregations, or traversing already-known relationships will not necessarily speed up just because another property index exists.

### 2.2. Writes Incur Cost Where Indexed Data Changes

| Operation | Impact on Lookup Index | Impact on Property Index |
|---|---|---|
| Creating a labeled node | Adds label–node mapping | Updates applicable property indexes for that node |
| Adding/removing a node label | Updates label–node mapping | May add/remove index entries tied to that label |
| Creating/deleting a relationship | Updates type–relationship mapping | Updates relevant relationship property indexes |
| Updating an **unindexed** property, keeping label and type unchanged | Normally no lookup entry change | No change to unrelated indexes |
| Updating an **indexed** property | No lookup update needed merely for property value changes | Maintains indexes depending on that property |

Therefore, a system continuously updating **lastSeenAt** does not have to update the token lookup index just because that property changes, as long as the node's labels remain unchanged. However, adding a property index on lastSeenAt can require maintaining that additional index on every update.

Neo4j updates indexes automatically alongside data; Java Driver or Spring Data Neo4j applications do not manually refresh indexes after writes. Especially for standard performance indexes, do not view an index as an asynchronous cache detached from transactions.

### 2.3. Storage and Over-Indexing

Lookup indexes are two structures **shared across all labels and all relationship types**; you cannot create a separate lookup index per label. Over-indexing typically needs scrutiny among **property indexes**: many single-property indexes on rarely filtered fields, redundant indexes, or indexes created speculatively without workload evidence.

You cannot calculate exact disk bytes or RAM strictly from index count. To decide whether the trade-off is worthwhile, observe database/index storage, I/O, page cache behavior, latency, and throughput on representative data.

## 3. Inspecting Current State on the Database

Status-reading queries can run on systems where the account has privileges to view indexes. The **CREATE** and **SET** examples further below should only be run on a test database.

### 3.1. Listing Token Lookup Indexes

~~~cypher
SHOW LOOKUP INDEXES
YIELD name, entityType, state, populationPercent
RETURN name, entityType, state, populationPercent
ORDER BY entityType;
~~~

Field meanings:

- **name:** index name; default indexes may have auto-generated names.
- **entityType:** **NODE** or **RELATIONSHIP**.
- **state:** **ONLINE** when ready for use; **POPULATING** while building; **FAILED** if building failed.
- **populationPercent:** index build progress, **not** the percentage of queries using the index.

To distinguish index types and spot constraint-owned indexes:

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, state, owningConstraint
RETURN name, type, entityType, state, owningConstraint
ORDER BY type, name;
~~~

**type = LOOKUP** indicates a token lookup index; **RANGE**, **TEXT**, and **POINT** are property performance index types; **FULLTEXT** and **VECTOR** serve specialized search cases. If **owningConstraint** is populated, inspect the managing constraint before altering the schema.

**ONLINE** does not mean the planner is using the index for critical queries; inspect actual query plans to verify.

### 3.2. Reading EXPLAIN and PROFILE

~~~cypher
EXPLAIN
MATCH (c:Customer)
WHERE c.region = $region
RETURN c.customerId
LIMIT 20;
~~~

**EXPLAIN** plans the query **without executing it**. When running the query for real:

~~~cypher
PROFILE
MATCH (c:Customer)
WHERE c.region = $region
RETURN c.customerId
LIMIT 20;
~~~

**PROFILE** executes the query and reports row counts, **DB Hits**, and operators in the plan. Operators you may encounter include **NodeByLabelScan**, **NodeIndexSeek**, **NodeIndexScan**, or others depending on version and optimization. If the planner scans most Customer nodes before filtering region, you may need to adjust the access path with an appropriate property index.

Note: **LIMIT 20** only caps returned rows; the system may still inspect many candidates to find 20 matching records.

## 4. Self-Runnable Example: When Is Lookup Enough, When Is It Not?

Run **once on a test database**, because the data-creation statement below will create duplicates if executed repeatedly:

~~~cypher
CREATE
  (c1:DemoLookupCustomer {code: 'DL-001', region: 'north'}),
  (c2:DemoLookupCustomer {code: 'DL-002', region: 'south'}),
  (c3:DemoLookupCustomer {code: 'DL-003', region: 'north'}),
  (p1:DemoLookupProduct {sku: 'DL-P-001'}),
  (c1)-[:DEMO_VIEWED]->(p1),
  (c2)-[:DEMO_VIEWED]->(p1);
~~~

### 4.1. Querying by Label or Type

~~~cypher
EXPLAIN
MATCH (c:DemoLookupCustomer)
RETURN c.code, c.region;
~~~

~~~cypher
EXPLAIN
MATCH ()-[r:DEMO_VIEWED]->()
RETURN r;
~~~

In a database with the two default lookup indexes, the planner has access paths by **node label** and **relationship type**. With a tiny example, EXPLAIN output primarily helps learners practice reading plans; **never use the timing of three nodes to draw production performance conclusions**.

### 4.2. Filtering by Property

~~~cypher
PROFILE
MATCH (c:DemoLookupCustomer)
WHERE c.code = 'DL-001'
RETURN c.code, c.region;
~~~

**code** is a property, not a label. If similar queries occur frequently on a large dataset with high selectivity, consider adding a range index:

~~~cypher
CREATE RANGE INDEX ix_demo_lookup_customer_code IF NOT EXISTS
FOR (c:DemoLookupCustomer) ON (c.code);
~~~

Monitor status:

~~~cypher
SHOW RANGE INDEXES
YIELD name, state, populationPercent
WHERE name = 'ix_demo_lookup_customer_code'
RETURN name, state, populationPercent;
~~~

Once the index reaches **ONLINE**, re-run the PROFILE query to compare. The planner **may still pick a label scan** on a tiny dataset; that is a reasonable decision if scanning is cheaper than index access.

If **code** is an identifier that must be unique, an appropriate **uniqueness constraint** can be better than a standalone index because it both enforces integrity and provides a backing lookup index. Check existing constraints to avoid duplicate definitions.

### 4.3. Changing Properties vs. Changing Labels

~~~cypher
MATCH (c:DemoLookupCustomer {code: 'DL-001'})
SET c.region = 'central'
RETURN c.code, c.region;
~~~

This command does not alter the node's labels: the lookup index does not update label mappings just because region changed. If a **property index on region** exists, the system does need to maintain that index.

~~~cypher
MATCH (c:DemoLookupCustomer {code: 'DL-001'})
SET c:DemoLookupPriority
RETURN labels(c) AS labels;
~~~

The **SET c:DemoLookupPriority** operation alters the label set and therefore touches the **node label lookup index**. If a data model churns labels continuously to represent short-lived states, weigh both label-update overhead and query semantics before deciding between labels and properties.

## 5. Protecting Default Lookup Indexes and Managing Property Indexes

Because there is at most **one node lookup index** and **one relationship lookup index** per database, you cannot create extra standalone lookup indexes to "separately optimize" each node kind. Dropping a lookup index can severely harm query performance and slow down population of other indexes. That is a foundational change that should only be evaluated in exceptional operational situations with clear data and measurements.

If a lookup index is missing, the recovery syntax is:

~~~cypher
CREATE LOOKUP INDEX node_label_lookup IF NOT EXISTS
FOR (n) ON EACH labels(n);
~~~

~~~cypher
CREATE LOOKUP INDEX relationship_type_lookup IF NOT EXISTS
FOR ()-[r]-() ON EACH type(r);
~~~

If an equivalent index already exists, **IF NOT EXISTS** causes the command to skip creating another index and may return a notice. Token lookup indexes **have no supported OPTIONS configuration**.

On a large database missing a relationship type lookup index due to pre-4.3 origins, rebuilding it may scan huge numbers of relationships. Plan for I/O load and population duration, and monitor state until **ONLINE**.

For genuinely redundant **property indexes**, evaluate: does the index serve a rare yet critical query? Is it owned by a constraint? If dropped, how will **PROFILE** plans and query p95 change? Is there a safe schema rollback plan? Do not drop an index solely because no reads were observed during a brief monitoring window.

## 6. Choosing a Strategy by Usage Pattern

| Workload | Strategy to Consider | Reason |
|---|---|---|
| Frequent queries by node label and relationship type | Keep both lookup indexes | They serve as shared access paths for labels and types |
| Looking up one Customer by email/code | Appropriate range index or uniqueness constraint | Lookup indexes do not support property-value filters |
| High-frequency writes to a rapidly changing property | Index that property only if read gains justify it | Avoids unnecessary index maintenance on every update |
| Bulk loading nodes and relationships | Measure load speed alongside index cost; plan property index population | Indexes must update on writes; post-load index creation also takes time and resources |
| Filtering on multiple properties together | Evaluate a composite range index | Can fit better than multiple single indexes, depending on actual predicate shapes |
| Rapidly growing database under storage pressure | Measure which indexes benefit the workload; review property indexes first | Do not recklessly sacrifice the two foundational lookup indexes |
| Property requiring uniqueness | Use a uniqueness constraint when appropriate | Enforces data integrity with a backing index underneath |

### Example Where Poor Decisions Happen Easily

An application records user activity:

~~~cypher
MATCH (u:User {id: $userId})
SET u.lastSeenAt = datetime();
~~~

If the system rarely filters on **lastSeenAt**, creating a property index on it increases index updates without meaningfully improving critical queries. Looking up User by **id** is what needs an appropriate property access path. Conversely, if a query like "users active in the last 5 minutes" runs continuously under a strict SLO, a timestamp index can yield substantial gains. Decisions must rest on measurements.

## 7. Measure Instead of Guessing Performance

To evaluate a **property index planned for addition or removal**, keep the default lookup indexes in both test configurations and compare under closely matched conditions.

**Step 1 – Select a representative workload.** Gather critical read/write queries, parameter distributions, selectivity, node/relationship counts, and read/write transaction ratios. Infrequent yet business-critical queries must still be accounted for.

**Step 2 – Capture baseline metrics.** Record p50/p95 for read queries, plus **DB Hits**, row counts, and operators from **PROFILE**; for writes, record p95 transaction latency, transactions/second, CPU, and I/O; for storage, record index space and page cache impact.

**Step 3 – Change one indexing decision.** Apply the change in a representative environment, wait for the index to reach **ONLINE**, and re-run the workload with identical parameters, data, hardware, and load profile. Run sufficient warm-up iterations before comparing.

**Step 4 – Compare both benefits and costs.** If read p95 drops yet write p95 breaches its SLO or storage exceeds budget, that index may not be worth keeping. Decisions must reflect net impact rather than a single attractive latency number.

| Metric | Before Change | After Change | Acceptance Criterion |
|---|---|---|---|
| Key read query p95 | Measured | Measured | Meets read SLO |
| **PROFILE** / DB Hits | Recorded | Recorded | Reduces unnecessary reads |
| Write transaction p95 | Measured | Measured | Does not breach write SLO |
| Throughput (tx/sec) | Measured | Measured | Handles peak-hour load |
| Storage, I/O, and page cache | Measured | Measured | Within resource budget |
| **SHOW INDEXES** | Recorded | Recorded | Required indexes are ONLINE |

The table above is an **experiment log template**, not performance numbers guaranteed by Neo4j.

## 8. Operations and Maintenance

### 8.1. Index Lifecycle

- **POPULATING:** currently building. Cannot yet be treated as ready to serve normal queries.
- **ONLINE:** index is ready for the planner to consider when conditions match.
- **FAILED:** diagnose the root cause via status/error messages and operational logs, then execute an appropriate remediation plan.

Run **SHOW INDEXES** periodically as part of monitoring workflows. Managing indexes requires appropriate privileges, such as **SHOW INDEX** for reading status and schema creation/drop privileges for changes. Avoid running unconditional schema creation or deletion on every application startup without deployment controls.

### 8.2. Common Misconceptions

1. **"Every index helps reads"** – False; queries must have an access path that benefits from the index and sufficient selectivity.
2. **"Lookup indexes speed up email lookups"** – False; lookups only resolve node labels and relationship types.
3. **"Every label needs its own lookup index"** – False; one node label lookup index is shared across all labels.
4. **"An ONLINE index means it is being used"** – False; verify with **EXPLAIN** or **PROFILE**.
5. **"Updating any property rewrites lookup indexes"** – False; changing property values alone does not alter labels or relationship types.
6. **"Drop both lookup indexes to optimize writes"** – High risk due to impact on many queries and building other indexes.
7. **"A property index unread for a week is definitely useless"** – Insufficient evidence; account for periodic jobs, incident queries, and constraint-owned indexes.

### 8.3. Pre-Schema-Change Checklist

- Identify target queries, selectivity, and required SLOs.
- Run **SHOW INDEXES** to classify lookup indexes, property indexes, and constraint-managed indexes.
- Capture baseline **EXPLAIN/PROFILE** plans alongside read/write metrics.
- Evaluate storage, I/O, population cost, and write impact on representative data.
- Prepare a deployment window, **ONLINE** verification, and a proper rollback plan.
- Monitor metrics after the change to detect regressions.

## 9. Practice Exercises

**Exercise 1 – Identifying indexes.** Given three queries:

~~~cypher
MATCH (n:Customer) RETURN n LIMIT 10;

MATCH ()-[r:PURCHASED]->() RETURN r LIMIT 10;

MATCH (n:Customer {email: $email}) RETURN n;
~~~

Identify which lookup index can assist the first two queries, and why the last query may require an additional property index or constraint.

**Exercise 2 – Balancing costs.** An application creates 20 million event relationships daily, while only a few reports filter by **eventTime**. List the measurements needed before adding a property index on eventTime. Should you drop the relationship type lookup index to reduce write costs?

**Exercise 3 – Reading plans.** On the Section 4 test data, run **PROFILE** before and after creating a range index on **DemoLookupCustomer.code**. Explain why results on three customers cannot represent 10 million customers.

**Exercise 4 – Monitoring population.** A new index is in **POPULATING** state with **populationPercent = 35**. Why can't you conclude the index is already speeding up queries? What must you wait for and verify?

## Conclusion

**Token lookup indexes** form the foundation for Neo4j to find nodes by **label** and relationships by **type**; most modern databases already include both defaults. Optimizing the read–write–storage balance typically starts by **keeping the foundational lookup indexes**, then carefully evaluating each **property index** or **constraint** against actual queries and workloads. Validate every decision with **EXPLAIN/PROFILE**, **SHOW INDEXES** status, and before/after measurements across both reads and writes.

### Official Reference Documentation

- [Neo4j Cypher Manual – Performance indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/)
- [Neo4j Cypher Manual – Create indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/create-indexes/)
- [Neo4j Cypher Manual – Show indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/list-indexes/)
- [Neo4j Cypher Manual – The impact of indexes on query performance](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/using-indexes/)
- [Neo4j Operations Manual – Index configuration](https://neo4j.com/docs/operations-manual/current/performance/index-configuration/)
