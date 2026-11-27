# Load Testing with Realistic Relationship Distributions

## 1. Why do graphs with the same node and relationship counts perform differently?

A Neo4j system does not bear load purely based on total **node** and **relationship** counts. Performance also depends on **which nodes concentrate relationships, edge direction, relationship types, traversal depth, filtered properties, and the exact queries the application sends to the database**.

Compare two graphs that both have 100,000 nodes and 1,000,000 relationships:

- **Graph A — relatively uniform:** most nodes have around 10 relationships.
- **Graph B — heavily skewed:** most nodes have very few relationships, while a few hundred "celebrity" nodes receive thousands or tens of thousands of relationships.

Both graphs have identical node and edge totals, yet `MATCH (u)<-[:FOLLOWS]-(f)` on a celebrity node traverses orders of magnitude more links than the same query on a typical node. Two-hop queries multiply intermediate rows by the branching factor at each hop; creating or deleting relationships on heavily connected nodes exhibits very different lock contention characteristics.

Therefore, **"generating one million random edges" does not produce a dataset representative of a real system**. This lesson establishes a load-testing workflow that reflects realistic **relationship distributions** in the Neo4j property graph model, combining:

1. Safely measuring characteristics of the source graph.
2. Generating or sampling test data that preserves key structural properties.
3. Designing read/write workloads matching real application behavior.
4. Testing load, tail latency, hubs, contention, and multi-hop traversals.
5. Comparing Cypher plans, correctness, and operational metrics.
6. Documenting limitations of the test model to avoid overgeneralizing conclusions.

The goal is not to copy sensitive production data, but to **preserve the structural properties that affect queries** in a controllable, reproducible dataset.

## 2. Graph characteristics to measure before designing load

In Neo4j, nodes carry labels and properties; relationships carry types, directions, and optional properties. A graph for connection-heavy query testing must be characterized along multiple dimensions.

| Characteristic | Example | Why it matters for performance |
|---|---|---|
| Node counts by label | User, Post, Topic, Order | Determines lookup scope and index size |
| Relationship counts by type | FOLLOWS, AUTHORED, LIKED | Different edge types have different fan-out and query patterns |
| **In-degree** | How many followers a User has | Follower queries, celebrity hubs |
| **Out-degree** | How many Users a User follows | Following lists and feed generation |
| Degree distribution | Median, p95, p99, max, fraction with degree = 0 | Distinguishes typical crowd from hubs |
| In/out asymmetry | Many users have high in-degree yet low out-degree | Traversal direction dictates workload cost |
| Communities / clusters | Users sharing organization, region, or interest | Governs intra-cluster vs. cross-cluster edge probability |
| Degree correlation | Do hubs link to hubs or to low-degree nodes? | Drives branching factor and multi-hop path counts |
| Parallel edges and self-loops | Multiple edges between the same endpoints? | Affects `MATCH` row counts and aggregations |
| Temporal distribution | Most interactions are recent | Affects date filters and hot data locality |
| Property selectivity | 1% ACTIVE Users vs. 80%? | Affects indexes, Filters, and Estimated Rows |
| Query mix | 80% reads, 20% writes, multiple endpoints | Affects caches, CPU, locks, and latency |

**Degree** is the count of relationships attached to a node within the **chosen label, type, and direction**. Never report "each node has 10 relationships on average" and assume the graph is uniform: averages completely hide heavy distribution tails.

### 2.1. Which relationships define degree?

Given the model:

~~~text
(u:User)-[:FOLLOWS]->(v:User)
(u:User)-[:AUTHORED]->(p:Post)
(u:User)-[:LIKED]->(p:Post)
(p:Post)-[:IN_TOPIC]->(t:Topic)
~~~

a single User may:

- Follow 20 other Users (**FOLLOWS out-degree = 20**).
- Be followed by 10,000 Users (**FOLLOWS in-degree = 10,000**).
- Write 4 posts (**AUTHORED out-degree = 4**).
- Like 200 posts (**LIKED out-degree = 200**).

Do not lump different relationship types into one aggregate degree if your application queries only `FOLLOWS`. Measure **per relationship type and direction relevant to the workload**.

### 2.2. Communities and cross-group edges

Social graphs rarely distribute edges uniformly at random: users tend to follow others in the same field, region, or group. If a test dataset scatters edges uniformly across all Users, "friend-of-a-friend" recommendation queries will see very different candidate counts and overlap than production.

Measure the **intra-community edge ratio** and cross-community edge ratio. When generating synthetic data, preserve that mixing structure at an appropriate level rather than matching total edge counts alone.

## 3. Using Cypher to measure in-degree and out-degree distributions

The queries below use label `LoadUser` and relationship `FOLLOWS` for illustration. In real environments, substitute your business labels and types **only after evaluating permissions and query cost**.

**Warning:** Measuring degrees across a huge graph can be resource-intensive, especially when scanning many relationships. Run these on a staging copy or during approved windows—never run full-graph scans on production during peak hours.

### 3.1. Per-node in-degree statistics

~~~cypher
MATCH (u:LoadUser)
OPTIONAL MATCH (:LoadUser)-[r:FOLLOWS]->(u)
WITH u, count(r) AS inDegree
RETURN count(*) AS userCount,
       sum(inDegree) AS followsRelationships,
       min(inDegree) AS minInDegree,
       avg(inDegree) AS meanInDegree,
       percentileCont(inDegree, 0.50) AS p50InDegree,
       percentileCont(inDegree, 0.95) AS p95InDegree,
       percentileCont(inDegree, 0.99) AS p99InDegree,
       max(inDegree) AS maxInDegree;
~~~

Several critical details:

- `OPTIONAL MATCH` preserves Users with zero followers; those nodes get **inDegree = 0**.
- `count(r)` counts **relationships**, not distinct followers. If two `FOLLOWS` edges go from the same source to target, it counts 2.
- `sum(inDegree)` equals total `FOLLOWS` edges where both endpoints match the selected labels.
- `percentileCont(..., 0.99)` is an interpolated percentile and may not be an actual integer node degree. Use `percentileDisc` if you need an observed discrete percentile.

**Never use `count(*)` instead of `count(r)` in `OPTIONAL MATCH`** to count degrees: when a node has no edges, `OPTIONAL MATCH` still emits one row with `r = null`, making `count(*) = 1` instead of 0.

### 3.2. Out-degree statistics

~~~cypher
MATCH (u:LoadUser)
OPTIONAL MATCH (u)-[r:FOLLOWS]->(:LoadUser)
WITH u, count(r) AS outDegree
RETURN count(*) AS userCount,
       avg(outDegree) AS meanOutDegree,
       percentileCont(outDegree, 0.50) AS p50OutDegree,
       percentileCont(outDegree, 0.95) AS p95OutDegree,
       percentileCont(outDegree, 0.99) AS p99OutDegree,
       max(outDegree) AS maxOutDegree;
~~~

In a graph considering a single User→User `FOLLOWS` type, **total in-degree equals total out-degree** because each relationship has one source and one target. However, the **distributions** of in-degree and out-degree can differ dramatically. A network with a few ultra-popular accounts typically has a much heavier **in-degree** tail than out-degree tail.

### 3.3. Grouping degrees into a histogram

~~~cypher
MATCH (u:LoadUser)
OPTIONAL MATCH (:LoadUser)-[r:FOLLOWS]->(u)
WITH u, count(r) AS degree
WITH CASE
       WHEN degree = 0 THEN '0'
       WHEN degree <= 5 THEN '1-5'
       WHEN degree <= 20 THEN '6-20'
       WHEN degree <= 100 THEN '21-100'
       ELSE '101+'
     END AS bucket,
     CASE
       WHEN degree = 0 THEN 0
       WHEN degree <= 5 THEN 1
       WHEN degree <= 20 THEN 2
       WHEN degree <= 100 THEN 3
       ELSE 4
     END AS bucketOrder
RETURN bucket, count(*) AS users
ORDER BY bucketOrder;
~~~

The thresholds 5, 20, and 100 are illustrative. In real systems, choose buckets that separate **the majority of nodes**, **fan-out tiers critical to queries**, and **extreme hubs**. Even p99 alone can hide what happens in the top 0.01% of nodes.

### 3.4. Identifying the largest hubs

~~~cypher
MATCH (u:LoadUser)
OPTIONAL MATCH (:LoadUser)-[r:FOLLOWS]->(u)
WITH u, count(r) AS inDegree
RETURN u.userId AS userId, inDegree
ORDER BY inDegree DESC, userId
LIMIT 20;
~~~

The top 20 list helps select `userId` keys for hub load scenarios. Avoid putting real or sensitive account IDs into benchmark logs or public docs; use anonymized identifiers with internal mapping where needed.

### 3.5. Observing degree by community

~~~cypher
MATCH (u:LoadUser)
OPTIONAL MATCH (:LoadUser)-[r:FOLLOWS]->(u)
WITH u.community AS community, u, count(r) AS inDegree
RETURN community,
       count(*) AS users,
       avg(inDegree) AS meanInDegree,
       percentileCont(inDegree, 0.95) AS p95InDegree,
       max(inDegree) AS maxInDegree
ORDER BY users DESC;
~~~

This reveals groups with different edge densities. A workload sampling Users only from a small community will not represent a large community or a hub-heavy cluster.

## 4. Structural checks that histograms miss

Matching the degree distribution is **necessary but not sufficient**. Two graphs with the exact same node degree histogram can still have vastly different multi-hop path structures.

### 4.1. Intra-community vs. cross-community edge ratio

~~~cypher
MATCH (a:LoadUser)-[r:FOLLOWS]->(b:LoadUser)
RETURN a.community AS sourceCommunity,
       b.community AS targetCommunity,
       count(r) AS relationships
ORDER BY relationships DESC;
~~~

If real data concentrates edges within communities while test data wires edges purely at random, two-hop follower recommendation queries will produce completely different candidate counts.

### 4.2. Hub–hub vs. hub–regular connection patterns

Check whether high-degree nodes mostly link to one another or to low-degree nodes. A graph that "preserves follower counts" yet links hubs uniformly to random nodes can still distort two-hop and three-hop path counts.

You can export per-node degrees and compare `(sourceOutDegree, targetInDegree)` pairs across edges in an analytics environment. On large graphs, run these joins via a proper analytics pipeline rather than joining `MATCH` patterns that cause accidental Cartesian explosions.

### 4.3. Duplicate edges and self-loops

~~~cypher
MATCH (a:LoadUser)-[r:FOLLOWS]->(b:LoadUser)
WITH a.userId AS sourceId,
     b.userId AS targetId,
     count(r) AS n
WHERE n > 1
RETURN sourceId, targetId, n
ORDER BY n DESC
LIMIT 20;
~~~

~~~cypher
MATCH (u:LoadUser)-[r:FOLLOWS]->(u)
RETURN count(r) AS selfFollows;
~~~

If business rules permit only one `FOLLOWS` edge per pair and forbid self-follows, these are data errors to clean up. Conversely, if the domain allows parallel relationships for distinct reasons, do not strip them just to make the graph "cleaner". Testing must preserve **true multiplicity rules**.

### 4.4. Multi-hop path branching factor

~~~cypher
MATCH (u:LoadUser {userId: $userId})
MATCH (u)<-[:FOLLOWS]-(a:LoadUser)
      <-[:FOLLOWS]-(b:LoadUser)
RETURN count(*) AS twoHopPaths,
       count(DISTINCT b) AS distinctSecondHopUsers;
~~~

`twoHopPaths` counts **relationship-pattern paths**, whereas `distinctSecondHopUsers` counts distinct target nodes. The two numbers can diverge sharply in tightly clustered communities with many paths reaching the same person.

**Run only on test datasets or authorized starting nodes.** On large hubs, even a two-hop counting query can materialize massive intermediate row counts; bound the test scope and monitor timeouts and CPU.

## 5. Profiling workloads from application behavior

Even a realistic graph distribution is insufficient if the queries sent to Neo4j differ from production. Gather aggregate, anonymized workload metrics within authorized boundaries:

- Mix of single-key lookups, one-hop expansions, two-hop expansions, aggregations, and pathfinding.
- Read/write ratio, requests per second, and concurrency level.
- Distribution of **traversal starting points**: what share of requests hit hubs, regular nodes, and isolated nodes?
- Query parameters: `LIMIT`, date filters, status filters, pagination offsets, and relationship types.
- Number of items/records mutated per transaction.
- Cache hit ratios caused by users repeatedly accessing the same entities.
- Temporal patterns: peak hours, post-event bursts, batch imports, and scheduled jobs.

### 5.1. Example query groups for a social service

| Workload group | Representative query | Sensitivity to relationship distribution |
|---|---|---|
| Profile lookup | Find User by `userId` | Index selectivity, property size |
| Following list | User → FOLLOWS → User | Out-degree and pagination |
| Follower list | User ← FOLLOWS ← User | In-degree; celebrity hubs |
| Follow recommendations | 2-hop traversal + deduplication | Degree correlation, communities, intermediate row count |
| Home feed | Following → AUTHORED → Post | Out-degree, posts per author, recency |
| Engagement | Create LIKED or comment | Write contention on node/relationship |
| Follow / unfollow | MERGE/DELETE FOLLOWS | Same endpoint pair, write contention |
| Aggregation job | Count likes/followers by group | Scans/aggregations, background load |

Derive weights from your target business domain—never assume "80% reads, 20% writes" just because it is a common textbook ratio. A messaging platform, social network, and software dependency graph have completely different workloads.

### 5.2. Parameter sampling must reflect skew

If 5% of real traffic hits the top 0.1% celebrity accounts, a load test picking `userId` uniformly across all users will **rarely touch a hub**. That makes p95/p99 look artificially rosy.

To model skew, sample parameters using weighted strata:

- A share of requests targeting popular **hubs**.
- A share targeting **mid-degree nodes**.
- A share targeting **low-degree or isolated nodes**.
- Special cohorts such as newly registered users, high-post authors, or high-order customers.

Model **both selection probability and the degree of the selected node**. The two are logically independent: a high-degree node is not necessarily queried frequently, and a low-degree node can still be a hot key if polled repeatedly.

## 6. Choosing scale and generating reproducible test data

### 6.1. Two common options

**Anonymized, de-identified snapshot:** preserves real graph topology well, but requires authorization, security controls, data governance, and PII scrubbing/masking. Never copy raw production graphs into unsecured test environments.

**Synthetic graph:** enables reproducibility, tunable hub ratios, tunable scale, and zero personal data. However, overly simplistic generators match node/edge totals while distorting community structure and multi-hop paths.

Usually the best approach combines **aggregate source statistics** with a **parameterized graph generator**, followed by post-generation verification.

### 6.2. Do not rely solely on uniform random wiring

The pattern "for each edge, pick two nodes independently and uniformly at random" produces a far more uniform degree distribution than real-world heavy-tailed networks. It also fails to preserve communities, popularity correlations, or the fraction of degree-0 users.

A more structured generation workflow:

1. Generate node lists matching label, segment, and community proportions.
2. Assign each node a **target out-degree** drawn from the measured segment distribution.
3. Sample target nodes with probabilities matching **target in-degree** and constraints like shared community, activity level, and recency.
4. Disallow self-loops or duplicate edges if forbidden by business rules; when rejecting/retrying, compensate so the degree distribution does not drift heavily.
5. Generate each relationship type with its own cardinality model; never reuse one distribution for `FOLLOWS`, `LIKED`, and `AUTHORED`.
6. Measure the generated graph afterward. A generator is a hypothesis about the graph—**not proof that it matches reality**.

### 6.3. Thinking in terms of "degree sequences"

A helpful starting strategy is generating a target degree list per node, for example:

~~~text
User 1: in-degree 10000, out-degree 20
User 2: in-degree 5000,  out-degree 12
User 3: in-degree 40,    out-degree 25
...
User N: in-degree 0,     out-degree 1
~~~

For a directed graph containing only `FOLLOWS` edges between Users, total in-degree must equal total out-degree, and both must equal the total relationship count. If the two sums differ, the target degree list cannot be realized intact.

You can match "outgoing stubs" to "incoming stubs" per degree sequence and then adjust to raise the intra-community edge ratio. Still, not every degree sequence is realizable without **self-loops** and **parallel edges**. The generator must detect shortfalls and report target realization rates rather than silently claiming success.

### 6.4. Three scales to keep distinct

| Test scale | Goal | Interpretation limit |
|---|---|---|
| **Mini fixture** (dozens of nodes) | Verify Cypher, edge direction, correctness | Does not represent production load or cache behavior |
| **Representative subset** | Compare behavior across node types, degrees, communities | Subsetting can alter path lengths and degrees |
| **Scale-like dataset** (near target scale) | Test memory, I/O, p95/p99, contention | Still must validate against real workload, indexes, and config |

Uniformly sampling a subset of Users can **drop hubs** or sever most of a hub's edges. When downscaling is unavoidable, document the sampling method and structural bias relative to the full graph.

## 7. Building a small fixture to test the model, not to benchmark performance

The hands-on example below builds a **small, intentionally skewed** graph purely to demonstrate measurement queries. Run it only on a **dedicated test database**. Label `LoadUser` is kept separate from production `User`.

### 7.1. Prepare the constraint

~~~cypher
CREATE CONSTRAINT load_user_id_unique IF NOT EXISTS
FOR (u:LoadUser)
REQUIRE u.userId IS UNIQUE;
~~~

### 7.2. Create 12 Users across two communities

~~~cypher
UNWIND range(1, 12) AS i
MERGE (u:LoadUser {userId: 'U' + toString(i)})
SET u.community = CASE
  WHEN i <= 8 THEN 'A'
  ELSE 'B'
END,
u.segment = CASE
  WHEN i IN [1, 2] THEN 'HUB'
  ELSE 'REGULAR'
END;
~~~

Keyed `MERGE` paired with the constraint supports re-running the fixture without duplicating Users. For write-concurrency tests, add proper coordination and constraints; this fixture alone does not substitute for concurrency testing.

### 7.3. Create edges concentrated on U1

~~~cypher
UNWIND [
  {from: 'U2',  to: 'U1'},
  {from: 'U3',  to: 'U1'},
  {from: 'U4',  to: 'U1'},
  {from: 'U5',  to: 'U1'},
  {from: 'U6',  to: 'U1'},
  {from: 'U7',  to: 'U1'},
  {from: 'U8',  to: 'U1'},
  {from: 'U9',  to: 'U1'},
  {from: 'U10', to: 'U1'},
  {from: 'U11', to: 'U1'},
  {from: 'U12', to: 'U1'},
  {from: 'U2',  to: 'U3'},
  {from: 'U3',  to: 'U4'},
  {from: 'U4',  to: 'U5'},
  {from: 'U5',  to: 'U6'},
  {from: 'U6',  to: 'U7'},
  {from: 'U7',  to: 'U8'},
  {from: 'U9',  to: 'U10'},
  {from: 'U10', to: 'U11'},
  {from: 'U11', to: 'U12'}
] AS edge
MATCH (a:LoadUser {userId: edge.from})
MATCH (b:LoadUser {userId: edge.to})
MERGE (a)-[:FOLLOWS]->(b);
~~~

Starting from an empty database and running only the statements above, the fixture holds **12 LoadUser nodes and 20 FOLLOWS edges**. `U1` receives **11** incoming edges, while most other Users receive **0 or 1**. Thus `U1` acts as a **high in-degree node within this fixture**, though it is absolutely **not large enough for real throughput/latency benchmarking**.

### 7.4. Verify the created distribution

~~~cypher
MATCH (u:LoadUser)
OPTIONAL MATCH (:LoadUser)-[r:FOLLOWS]->(u)
WITH u, count(r) AS followers
RETURN u.userId AS userId,
       u.community AS community,
       followers
ORDER BY followers DESC, userId;
~~~

Count total relationships:

~~~cypher
MATCH (:LoadUser)-[r:FOLLOWS]->(:LoadUser)
RETURN count(r) AS followsCount;
~~~

If `LoadUser` data already existed from a prior run or was modified, do not assume 12/20 without verifying.

### 7.5. Intentional fixture cleanup

To remove **all `LoadUser` nodes from this practice exercise** inside an isolated test database:

~~~cypher
MATCH (u:LoadUser)
DETACH DELETE u;
~~~

This is a real deletion statement that also deletes all relationships attached to matched nodes. Run it only when you are certain `LoadUser` holds no data you need to keep; **never run it on production business labels**.

## 8. Loading a more realistic dataset via controlled edge lists

Once an external generator outputs an edge list matching the target distribution, a Java loader can feed batched lists into Cypher. Example `$edgePairs` parameter:

~~~json
[
  {"fromId": "U2", "toId": "U1"},
  {"fromId": "U3", "toId": "U1"},
  {"fromId": "U4", "toId": "U1"}
]
~~~

Batched import query:

~~~cypher
UNWIND $edgePairs AS edge
MATCH (a:LoadUser {userId: edge.fromId})
MATCH (b:LoadUser {userId: edge.toId})
WHERE a <> b
MERGE (a)-[:FOLLOWS]->(b)
RETURN count(*) AS processedRows;
~~~

Key points to remember:

- `processedRows` counts **input rows processed by the query**, not **newly created** relationships.
- A `MATCH` that fails to find either endpoint silently drops the row; reconcile source edge counts against actual persisted edges rather than overlooking missing rows.
- `MERGE` on a relationship supports idempotent re-runs for a single-edge-per-pair model under controlled ingestion, yet **does not prove uniqueness under arbitrary concurrent writes** if multiple workers write the same pair without synchronization.
- Create nodes and constraints **before** loading relationships, using stable business keys.
- Size batches moderately to avoid oversized transactions; when high throughput is required, measure retry and lock-contention costs as well.
- If the model allows multiple relationships between the same pair of endpoints, use a distinguishing key instead of merging on the bare pattern and accidentally collapsing edges.

An external generator should output its **seed, distribution parameters, edge counts per type, and checksum/manifest** so runs are reproducible. Using `rand()` inside Cypher produces different graphs across runs and makes query comparisons unreliable.

## 9. Turning data characteristics into query scenarios

A test suite needs both **purpose-built Cypher queries** and parameter pools sampled per realistic distributions.

### 9.1. One-hop lookup into a hub

~~~cypher
MATCH (u:LoadUser {userId: $userId})
MATCH (f:LoadUser)-[:FOLLOWS]->(u)
RETURN f.userId AS followerId
LIMIT $pageSize;
~~~

With `$userId = 'U1'` in the fixture, the query traverses the hub's followers. With `'U12'`, there are far fewer followers. `LIMIT` caps returned rows, yet it **does not guarantee total processing work equals `pageSize` across all plans and cases**.

If the API requires deterministic pagination:

~~~cypher
MATCH (u:LoadUser {userId: $userId})
MATCH (f:LoadUser)-[:FOLLOWS]->(u)
RETURN f.userId AS followerId
ORDER BY followerId
LIMIT $pageSize;
~~~

Sorting can force the engine to process many candidates before selecting a page. Benchmark the exact query the application runs—never drop `ORDER BY` just to make benchmark numbers look faster.

### 9.2. Two-hop traversal: row-multiplication risk

~~~cypher
MATCH (u:LoadUser {userId: $userId})
MATCH (u)<-[:FOLLOWS]-(first:LoadUser)
      <-[:FOLLOWS]-(second:LoadUser)
RETURN count(*) AS twoHopPaths,
       count(DISTINCT second) AS uniqueSecondHopUsers;
~~~

Two-hop queries explode rapidly when many first-hop nodes also have high follower counts. If the application only needs to know whether a candidate node **is connected**, consider `EXISTS` rather than materializing every combination.

On real graphs, two-hop traversals from a hub can easily saturate resources. Never start testing with the largest hubs at peak concurrency; ramp load gradually with strict timeouts.

### 9.3. Community-filtered query

~~~cypher
MATCH (u:LoadUser {userId: $userId})
MATCH (u)-[:FOLLOWS]->(v:LoadUser)
WHERE v.community = $community
RETURN v.userId AS followedUserId
LIMIT $pageSize;
~~~

The intra-community vs. cross-community edge ratio determines how many rows pass the Filter, even when out-degrees are identical. A generator with unrealistic community clustering will make `community`-filtered tests artificially easy or hard.

### 9.4. `EXISTS` query for connection checks

~~~cypher
MATCH (u:LoadUser {userId: $userId})
MATCH (candidate:LoadUser {userId: $candidateId})
RETURN EXISTS {
  MATCH (u)-[:FOLLOWS]->(candidate)
} AS isFollowing;
~~~

A query needing only **true/false** does not need to emit all rows or relationships. When checking many endpoint pairs concurrently, latency depends on node lookup indexes, cache warmth, and relationship layout.

### 9.5. Writing or deleting relationships

~~~cypher
MATCH (a:LoadUser {userId: $fromId})
MATCH (b:LoadUser {userId: $toId})
WHERE a <> b
MERGE (a)-[:FOLLOWS]->(b);
~~~

~~~cypher
MATCH (a:LoadUser {userId: $fromId})
      -[r:FOLLOWS]->
      (b:LoadUser {userId: $toId})
DELETE r;
~~~

Writing relationships requires synchronizing endpoint node connectivity structures. If every worker concurrently adds edges to hub `U1`, lock contention behaves very differently than when workers update disjoint User pairs.

**Never test creates/deletes with production IDs.** Use dedicated test node pools and clean up after write tests.

## 10. Load parameters must reflect access skew

To compare hubs and typical nodes systematically, partition requests into **parameter strata**.

| Stratum | Selection method | Issues it is designed to expose |
|---|---|---|
| Very large hubs | Nodes in the extreme degree tail | Fan-out, p99, memory, hot locks |
| Median-degree nodes | Nodes near p50/p75 | Typical user latency |
| Low/zero-degree nodes | Sparse or isolated nodes | `OPTIONAL MATCH`, empty-result handling |
| Dense communities | Communities with high node/edge counts | Filter selectivity and candidate volume |
| Small communities | Sparse communities | Alternative query plans and correctness |
| Traffic-hot nodes | Polled repeatedly | Caching, concurrency, contention |
| Cold nodes | Rarely accessed, absent from cache | Page cache misses and disk I/O |

Never assume "most followers = highest request traffic". Measure **request selection probability** from real metrics where available. If unavailable, document your assumed weights explicitly and test multiple traffic profiles.

### 10.1. Test per stratum, then test mixed workloads

A practical sequence:

1. **Single-group tests:** hubs only, regular nodes only, isolated nodes only, to see each latency curve clearly.
2. **Mixed workload:** combine strata using measured traffic proportions to evaluate overall behavior.
3. **Hotspot stress:** raise the hub request share to locate saturation thresholds.
4. **Regression:** re-run the exact same dataset/seed and parameters after query or index changes.

By separating strata, shifts in overall p95 can be diagnosed precisely: did hubs get slower, did the hub traffic share grow, or did a query plan regress?

## 11. Designing load-testing phases

Plan benchmark phases methodically rather than hitting "1,000 virtual users" and reporting a single average.

| Phase | Purpose | How to run |
|---|---|---|
| **Smoke** | Verify correctness, privileges, data, config | Few requests, low concurrency |
| **Warm-up** | Let JVM, page cache, connection pools, and plans stabilize | Exclude warm-up metrics from steady-state numbers |
| **Ramp-up** | Identify where latency starts climbing with load | Increase RPS/concurrency in steps |
| **Steady-state** | Measure throughput, p95/p99, errors at target load | Hold workload long enough for stable samples |
| **Spike** | Simulate a sudden burst hitting a hub | Monitor queues, timeouts, and recovery |
| **Stress/breakpoint** | Find where the system breaks its SLO | Include safe stop-conditions; never run on production |
| **Soak** | Catch memory/session leaks and creeping latency | Extended duration on an authorized environment |
| **Recovery** | Verify recovery after load drops | Do queues, lag, pools, and waiting transactions clear? |

### 11.1. RPS and concurrency are not the same

A system handling 100 concurrent requests that each take 10 ms has vastly different potential throughput than 100 concurrent requests taking 3 seconds each. Record **request arrival rate**, **active concurrency**, **response time**, **queue wait**, and **completed throughput**.

Two load-modeling styles:

- **Closed-loop:** each client issues a new request only after the previous one completes. When the server slows down, the arrival rate drops automatically.
- **Open-loop / arrival-rate:** dispatches requests on an arrival schedule independent of response speed. Exposes queuing collapse under backlog, though you must track delayed or dropped requests.

Using only closed-loop generators allows a slow server to trigger **coordinated omission**: fewer requests get sent precisely when the system stalls, making tail latencies look better than reality. Choose appropriate tooling and measurement, and explicitly report unsent requests, timeouts, and rejected load.

### 11.2. Never start at peak load

Begin with smoke and ramp phases. Once error rates spike, pushing even higher load often piles up queues and timeouts without yielding new insight. Define **stop criteria** covering environment authorization, time budget, CPU/memory, error rate, and impact on neighboring systems.

## 12. Measuring the right metrics and analyzing tail latency

**Throughput** and **latency** are distinct axes. A system can sustain high requests/second overall while exhibiting awful p99 on hub queries.

| Metric | Interpretation |
|---|---|
| Requests/second sent vs. completed | Input demand vs. actual capacity |
| p50 latency | Typical experience |
| p95/p99 latency | Tail latency; typically sensitive to hubs and contention |
| Timeout/error rate | Stability at target load |
| Queue/pool wait | Time waiting for resources before executing Cypher |
| Query rows / DB hits | Amount of work Cypher actually performed |
| CPU, RAM, GC, page cache, and I/O | Server resource bottlenecks |
| Active transactions, deadlocks, lock waits | Write contention and long-lived transactions |
| Bytes/records returned | Bolt, network, and materialization cost |
| Java Driver retry count | Indicator of transient errors and load pressure |
| Consumer / batch import lag | Background load competing with API queries |

If a small fraction of hub requests causes most timeouts, reporting only p50 or average latency hides the failure completely.

### 12.1. Combine aggregate scores with per-stratum scores

A strong report includes **all** of:

- Overall workload p50/p95/p99.
- **Hub-only** p50/p95/p99.
- **Mid-degree** p50/p95/p99.
- **Low-degree** p50/p95/p99.
- Proportion of requests in each stratum during the run.

When parameter sampling or hub ratios change, compare within the same stratum before concluding a database change made queries faster or slower.

### 12.2. Set business-driven SLOs instead of arbitrary thresholds

Illustrative example of application-defined targets:

~~~text
Endpoint followers
- target load: defined by operations team from metrics
- p95 latency below committed threshold
- p99 latency below alert threshold
- timeout rate within limit
- accurate results for parameter sets and pagination
~~~

There is no universal "standard" p95 value for all Neo4j graphs. Thresholds depend on the API, query shape, graph size, and user expectations. **Define acceptance criteria before testing**, rather than adjusting criteria after seeing results.

## 13. Inspecting Cypher plans across starting-node strata

Neo4j relies on its query planner, indexes, and traversal operators. The Cypher text alone does not reveal actual runtime cost.

### 13.1. `EXPLAIN` to inspect the plan without executing

~~~cypher
EXPLAIN
MATCH (u:LoadUser {userId: $userId})
MATCH (f:LoadUser)-[:FOLLOWS]->(u)
RETURN f.userId AS followerId
LIMIT $pageSize;
~~~

What to check:

- Does the query start with an **index seek** on `LoadUser.userId`?
- Is there any full label scan?
- What **Estimated Rows** does the planner predict at the Expand step?
- Are there Sort/Top/Aggregation operators, and where do they sit?
- In two-hop queries, which hop inflates estimated rows?

The constraint on `LoadUser.userId` in the fixture backs key lookups. If real queries add other `WHERE` predicates, suitable indexes depend on selectivity and the query plan.

### 13.2. `PROFILE` to measure, while executing the query

~~~cypher
PROFILE
MATCH (u:LoadUser {userId: $userId})
MATCH (f:LoadUser)-[:FOLLOWS]->(u)
RETURN f.userId AS followerId
LIMIT $pageSize;
~~~

On test data, `PROFILE` reports row counts, DB hits, and execution metrics depending on your Neo4j version. Run it with both a hub `userId` and a regular `userId` to compare.

**`PROFILE` executes the query.** Never run `PROFILE` on `CREATE`, `SET`, `DELETE`, or `DETACH DELETE` against important data just to "take a look". For write queries, inspect `EXPLAIN` first, then run/measure on a test database.

### 13.3. Do not infer speed from Cypher clause order alone

Neo4j may push down predicates or choose a starting point different from the textual order of Cypher clauses. Plans depend on statistics, indexes, data, and version. When tuning a query:

1. Ensure **both query versions satisfy the exact same business requirement**.
2. Compare plans on the same dataset configuration.
3. Measure across hubs, regular nodes, and isolated nodes.
4. Compare p95/p99 under a mixed workload.
5. Check memory, DB hits, and returned records.

An optimization for regular nodes can make hub queries worse; never benchmark with only one "nice" `userId`.

## 14. Write load testing: relationships and hub contention

Neo4j coordinates locks whenever transactions modify nodes, relationships, and graph structure. For the scenario:

~~~cypher
MATCH (a:LoadUser {userId: $fromId})
MATCH (b:LoadUser {userId: $toId})
MERGE (a)-[:FOLLOWS]->(b);
~~~

two write patterns behave very differently:

- **Dispersed:** each worker writes distinct endpoint pairs.
- **Concentrated:** many workers concurrently add/remove edges on one hub or the same node pair.

Measure transaction latency, deadlocks/retries, lock waits, and impact on concurrent read queries. **Relationship `MERGE`** does not guarantee relationship invariants under arbitrary concurrency; if each pair may have at most one `FOLLOWS` edge, explicit data design and concurrency handling are required.

### 14.1. Concurrent reads and writes

Never benchmark reads purely on a static graph if production performs heavy writes:

- Users frequently follow and unfollow.
- Workers create Posts, Likes, and Comments.
- CDC jobs synchronize state.
- GDS/analytics pipelines read or project subgraphs.
- Scheduled cleanup and index/constraint jobs run.

Mixed read/write tests expose tail latency spikes and transaction conflicts invisible to read-only tests.

### 14.2. Never use unconditional `CREATE` when measuring idempotent updates

If a benchmark replays the same edge-creation command repeatedly using `CREATE`, the graph accumulates duplicate edges and stops being comparable to earlier runs. Define whether business rules allow parallel relationships or only one; enforce keys, `MERGE`/constraints, and idempotency accordingly.

When measuring write capacity, record **final relationship counts, committed transactions, and retry counts**, not merely "statements sent".

## 15. The Java Driver in load generators and test APIs

Java applications using the Neo4j Java Driver must track **end-to-end API latency**, not only query execution time inside Neo4j. The Driver manages connections, sessions, transactions, retries, and record consumption.

Example read-only service mapping results directly:

~~~java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class FollowerReadService {
    private final Driver driver;

    public FollowerReadService(Driver driver) {
        this.driver = driver;
    }

    public List<String> followers(String userId, int requestedLimit) {
        if (userId == null || userId.isBlank()) {
            throw new IllegalArgumentException("userId is required");
        }
        int limit = Math.max(1, Math.min(requestedLimit, 100));

        String cypher = """
            MATCH (u:LoadUser {userId: $userId})
            MATCH (f:LoadUser)-[:FOLLOWS]->(u)
            RETURN f.userId AS followerId
            LIMIT $limit
            """;

        try (Session session =
                 driver.session(SessionConfig.forDatabase("neo4j"))) {
            return session.executeRead(tx ->
                tx.run(cypher, Map.of(
                    "userId", userId,
                    "limit", limit
                )).list(row -> row.get("followerId").asString())
            );
        }
    }
}
~~~

In a load harness:

- **Reuse the `Driver`** across requests; never instantiate a new `Driver` per request.
- **Keep `Session` lifecycles short** and never share a `Session` casually across threads.
- **Consume results** inside the transaction; benchmarks that skip reading records required by the real API produce misleading numbers.
- `executeRead` is a managed transaction that may retry eligible transient errors; include retry latency and counts in your observations.
- `LIMIT` reflects the endpoint contract and must be preserved; changing a query from 1,000 rows to 10 rows and claiming a speedup is invalid if the product still needs 1,000.
- This Java snippet shows a read service; it is **not a full load-testing framework** and does not generate arrival-rate traffic distributions by calling a method once.

When an API uses **Spring Data Neo4j**, run load tests through the same endpoints and projections/DTOs, as entity mapping and relationship materialization can noticeably alter application latency compared to standalone Cypher queries.

### 15.1. Direct Bolt testing vs. HTTP API testing?

| Test point | Best at exposing | Does not cover automatically |
|---|---|---|
| Driver → Neo4j over Bolt | Query, session, transaction, Bolt networking | HTTP auth, JSON serialization, app routing |
| HTTP → Application → Neo4j | End-to-end UX, validation, pools, mapping | Harder to pinpoint bottlenecks without tracing |
| GDS/analytics batch | Graph algorithm memory/CPU | Real-time endpoint latency |
| Import/CDC pipeline | Node/edge ingestion rate, checkpoints, replay | User-facing feed latency during interaction |

Maintain both **database-level benchmarks** to isolate queries and **API-level benchmarks** to observe real end-to-end behavior, using comparable datasets and parameter distributions.

## 16. Separating cache effects and hot vs. cold data

A test repeating the same 10 `userId`s hits the cache far more than a production workload spanning millions of Users. Document clearly:

- **Warm cache:** most data and index pages are already cached.
- **Cold-ish cache:** many new keys or rarely accessed graph regions.
- **Hot-key workload:** a small set of keys hit continuously.
- **Broad-key workload:** keys spread widely across the graph.

You do not always need to "flush all caches" between tests; doing so can be unrepresentative of production. Still, maintain **comparable cache conditions across runs** when checking for regressions.

### 16.1. Warm-up changes the shape of results

During warm-up, Neo4j populates page cache and indexes while the Java app warms connection pools and JIT compilation. Mixing warm-up metrics into steady-state measurements skews p95/p99 toward startup conditions rather than sustained load.

Conversely, if production experiences frequent cold starts or deploys, run a **dedicated cold-start scenario**—never ignore it just because steady-state numbers look cleaner.

## 17. Making test results reproducible

A benchmark run is only useful if it can be explained and repeated. Each run's manifest should record:

~~~yaml
runId: neo4j-load-demo-001
purpose: compare-follower-query
dataset:
  kind: synthetic
  seed: fixed-seed
  nodeCounts: recorded-by-label
  relationshipCounts: recorded-by-type
  degreeDistribution: recorded-in-degree-out-degree
  communities: recorded-mixing-ratio
workload:
  queryMix: recorded-percentages
  keyDistribution: hub-medium-cold
  concurrency: configured-value
  arrivalRate: configured-value
  duration: configured-value
environment:
  neo4jVersion: recorded
  javaDriverVersion: recorded
  cpuMemoryStorage: recorded
  indexSchema: recorded
measurements:
  latencyP50P95P99: recorded
  throughputErrors: recorded
  dbHitsRows: recorded
~~~

This is an **illustrative logging template**, not a generated manifest file or mandatory schema for a specific tool. Also record application version, query commit, generator seed, warm-up setup, timeout handling, whether data was reused or freshly seeded, and background load state.

Never compare runs that differ in database size, CPU tier, indexes, hub traffic ratio, or query mix and conclude speed changed solely because of a Cypher edit.

## 18. Common mistakes when simulating relationship distributions

| Mistake | Why it skews results | How to fix |
|---|---|---|
| Matching only total node/edge counts | Misses hubs and heavy tails | Check degree histograms, p95/p99/max |
| Wiring edges uniformly at random | Destroys skew and community clustering | Generate from degree sequences and communities |
| Measuring only mean degree | Completely hides hubs | Measure zero-degree share, p50, p95, p99, top hubs |
| Matching only in-degree | Following queries see the wrong workload | Measure in-degree and out-degree separately per type |
| Downscaling via uniform sampling | Can sever hub edges | Re-verify structure after sampling |
| Running one simple query on one ID | Misses real app workload | Mix reads/writes and parameter strata |
| Sampling IDs uniformly under skewed traffic | Fails to generate realistic hot keys | Sample per measured traffic cohorts |
| Reporting only mean latency | Hides slow hub tail queries | Report p50/p95/p99 and timeouts per stratum |
| Using a smaller `LIMIT` than production | Benchmark no longer reflects business requirements | Match production payload/page sizes |
| Testing only warm caches | Misses cold keys and deploy effects | Separate warm, cold-ish, and hot-key runs |
| Skipping Driver `Result` consumption | Ignores network/mapping costs | Consume results just like the real API |
| Ignoring errors and retries | Throughput looks high despite failing requests | Report errors, timeouts, retries, and completed RPS |
| Mutating edges without resetting fixtures | Dataset drifts across runs | Use snapshots/manifests and reset procedures |
| Running `PROFILE` on writes in production | Write statements actually execute | Use `EXPLAIN` or run on a test database |
| Ignoring community structure | Two-hop candidate counts diverge wildly | Preserve mixing ratios and correlations |
| Omitting environment metadata | Results cannot be reproduced | Record a complete run manifest |

## 19. Practice exercises

### Exercise 1 — Two graphs with identical edge counts

Graph A and Graph B both have 100,000 Users and 1,000,000 `FOLLOWS` edges. Graph A distributes edges fairly evenly; Graph B has several hubs with massive follower counts.

**Question:** Can follower-query latency on A predict hub load on B?

**Answer:** Unreliably. The two graphs have different in-degree distributions; queries starting from a hub on B traverse far more edges. Benchmark by degree stratum and inspect real plans and timings.

### Exercise 2 — Missing zero counts when counting followers

A query uses `OPTIONAL MATCH (f)-[r:FOLLOWS]->(u)` and `count(*)`. Users with zero followers get counted as 1.

**Question:** How do you fix it?

**Answer:** Use `count(r)` so only non-null relationships are counted. `count(*)` counts the null row preserved by `OPTIONAL MATCH`.

### Exercise 3 — Asymmetric degree directions

An account follows 100 people yet has only 2 followers.

**Question:** If an API lists a user's followers, which degree should stratify the workload?

**Answer:** **In-degree `FOLLOWS`**, because the relationship is directed follower → followed user. Out-degree governs the following list.

### Exercise 4 — Two-hop paths

A node has 1,000 followers, and each follower also has many followers. A two-hop query produces huge path counts yet only a few thousand distinct Users.

**Question:** Why do `count(*)` and `count(DISTINCT second)` diverge?

**Answer:** Many distinct paths can reach the same User. `count(*)` counts matched paths, while `DISTINCT` counts unique nodes; each answers a different question.

### Exercise 5 — Suspiciously "great" benchmark numbers

A test samples `userId` uniformly at random across the entire graph, whereas production sends heavy traffic to the top 0.1% celebrity accounts.

**Question:** How does this distort p99 results?

**Answer:** The test rarely touches hot hubs; average load and tail latency appear lower than production reality. Use traffic-weighted key distributions or dedicated hub strata.

### Exercise 6 — Load testing without checking results

A benchmark sends follower requests, checks only for HTTP 200, and never inspects returned IDs.

**Question:** Is this enough to certify the optimized query?

**Answer:** No. The query might return truncated data, paginate wrongly, or drop followers. Verify exact output contracts and row counts against test data.

### Exercise 7 — Concurrent writes to a hub

One thousand workers concurrently try to create `FOLLOWS` relationships targeting the same celebrity User.

**Question:** Is measuring committed transactions alone sufficient?

**Answer:** No. Also track latency, lock waits/timeouts, deadlocks/retries, actual relationships created, duplicate edges per business rules, and impact on concurrent read queries.

### Exercise 8 — Comparing two runs under mismatched conditions

You run a new query on a warm-cached 100,000-edge graph and compare it against an old query on a cold-key 1,000,000-edge graph.

**Question:** Can you claim the new query is faster?

**Answer:** No. Dataset size, skew, key distribution, and cache warmth all changed. Compare under matched conditions documented in a manifest.

## 20. Checklist before finalizing load-test results

- [ ] Recorded node counts by label and relationship counts by type/direction.
- [ ] Measured in-degree/out-degree histograms, zero-degree share, p50/p95/p99, and max.
- [ ] Measured hub, community, duplicate-edge, and correlation statistics as needed.
- [ ] Test dataset has a documented seed/origin and exposes no personal data.
- [ ] Generated/imported test data reconciled against source statistics.
- [ ] Queries and parameters match real endpoints, `LIMIT`s, filters, and access ratios.
- [ ] Stratified across hub, typical, low/isolated, and hot/cold keys.
- [ ] Executed smoke, warm-up, steady-state, and controlled ramp scenarios.
- [ ] Tracked completed RPS, p50/p95/p99, timeouts, retries, and result correctness.
- [ ] Inspected `EXPLAIN`/`PROFILE` on representative queries in a safe environment.
- [ ] Included mixed read/write load if production performs concurrent writes.
- [ ] Recorded driver/session/pool config, indexes, database version, and hardware resources.
- [ ] Defined stop criteria and SLOs upfront.
- [ ] Saved a reproducible manifest and documented known limitations of synthetic graphs.

## 21. Key takeaways

**Load testing Neo4j with realistic relationship distributions** goes far beyond generating enough nodes and relationships. You must preserve **in-degree/out-degree skew, hubs, communities, edge multiplicity, relationship types, temporal patterns, and property selectivity** wherever they affect your workload. A uniform synthetic graph standing in for a hub-heavy graph hides expensive traversals, high tail latency, and write contention.

**Measure source distributions with safe statistics, generate parameterized test graphs and verify them**, and then benchmark Cypher queries using realistic parameter distributions. Evaluate **result correctness**, p50/p95/p99, completed throughput, retries/timeouts, query plans, and resource usage across both Neo4j and the Java Driver or Spring Data Neo4j. Only when seeds, workloads, configurations, and dataset limits are clearly documented are results trustworthy enough to guide query tuning, indexing, graph modeling, and capacity planning.
