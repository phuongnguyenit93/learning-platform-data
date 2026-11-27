# Similarity, Link Recommendation, and Node Vector Representations

In a graph, two nodes can be **similar without having a direct relationship**: two customers buying many of the same products, two articles read by the same group of users, or two accounts interacting with related topics. Graph algorithms leverage connection structure and properties to quantify similarity, recommend missing links, and represent nodes as numeric vectors for search, clustering, or machine learning models.

This lesson belongs to the **Graph Algorithms** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. Neo4j uses the **property graph** model consisting of nodes, relationships, labels, and properties; Cypher queries relationships, while **Neo4j Graph Data Science (GDS)** provides analytical algorithms such as Node Similarity, FastRP, and kNN over graphs projected into memory. Computing results typically integrates with indexes, constraints, Cypher queries, the Java Driver, or Spring Data Neo4j in production applications.

After this lesson, you will be able to:

- Distinguish **node similarity**, **link prediction**, and **node embedding**.
- Compute and interpret Jaccard, common neighbors, and structural similarity signals.
- Create in-memory graph projections, use Node Similarity to discover similar node pairs, and generate link recommendations in Cypher.
- Use FastRP to generate structural vectors, compare them with kNN, and know when to use a vector index.
- Evaluate top-K metrics, prevent data leakage when training link prediction models, handle cold start, and mitigate common biases.
- Design workflows to experiment with, deploy, and maintain algorithmic outputs without corrupting source data integrity.

## 1. Three Related Problems with Different Outputs

| Problem | Question to Answer | Output | Example |
| --- | --- | --- | --- |
| **Node similarity** | How similar are two nodes based on relationships or properties? | Node pairs and similarity scores. | U1 and U2 purchased many common products. |
| **Link recommendation/prediction** | Between two currently unconnected nodes, should an edge be suggested? | Candidate node pairs, ranking scores, or calibrated probabilities. | Recommend product P4 to U1. |
| **Node embedding** | How do we encode a node's structure/context into a sequence of numbers? | A vector \((x_1,\ldots,x_d)\) per node. | A 64-dimensional vector per user to find nearest neighbors. |

These three tasks can be combined, yet **a similarity score is not the probability a link will form**, and **vectors do not automatically capture full business semantics**. For example, two customers who both buy everyday essentials have high similarity, yet may not make good friend recommendations.

A common pipeline:

~~~text
Nodes + relationships in Neo4j
             |
             v
   Filter edge types, time window,
     tenant, and valid nodes
             |
             v
      GDS Graph Projection
             |
       +-----+------+
       |            |
       v            v
 Node Similarity   FastRP / Node2Vec
       |            |
       |            v
       |          Embeddings
       |            |
       |            v
       |           kNN
       +-----+------+
             |
             v
   Filter unlinked candidates
   + business rules and permissions
             |
             v
   Rank, evaluate, and serve
~~~

Real pipelines can be shorter: on small problems, Cypher and common-neighbor counts suffice; there is no need to train or store embeddings just to answer a simple query.

## 2. Example Graph: Users Interacting with Products

We use a *bipartite graph* model:

~~~text
(:GdsDemoUser {userId})
       |
       | [:DEMO_INTERACTED]
       v
(:GdsDemoItem {itemId})
~~~

Test data:

| User | Interacted Products |
| --- | --- |
| U1 | P1, P2, P3 |
| U2 | P1, P2, P4 |
| U3 | P2, P4 |
| U4 | P5 |

U1 and U2 share interest in P1 and P2; U2 and U3 share P2 and P4; U4 shares no products with the other three users. This model and dataset allow hand-calculating outputs to cross-check the algorithms.

Run data-creation statements only inside a **dedicated learning database safe to modify**. Labels, types, and index/constraint names carry a demo prefix to clearly separate them from application data.

### 2.1. Protecting Identifier Keys

~~~cypher
CREATE CONSTRAINT gds_demo_user_id_unique IF NOT EXISTS
FOR (u:GdsDemoUser)
REQUIRE u.userId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT gds_demo_item_id_unique IF NOT EXISTS
FOR (i:GdsDemoItem)
REQUIRE i.itemId IS UNIQUE;
~~~

These two uniqueness constraints prevent multiple nodes of the same label from sharing duplicate key values when set. In production systems, also evaluate mandatory key requirements and key/existence constraints based on your Neo4j version and edition.

### 2.2. Loading Data

~~~cypher
UNWIND [
  {userId: 'U1', items: ['P1', 'P2', 'P3']},
  {userId: 'U2', items: ['P1', 'P2', 'P4']},
  {userId: 'U3', items: ['P2', 'P4']},
  {userId: 'U4', items: ['P5']}
] AS row
MERGE (u:GdsDemoUser {userId: row.userId})
WITH u, row
UNWIND row.items AS itemId
MERGE (i:GdsDemoItem {itemId: itemId})
MERGE (u)-[:DEMO_INTERACTED]->(i);
~~~

When re-running on a clean fixture, `MERGE` avoids creating duplicate edges of the same type and endpoints in single-threaded execution. Under concurrent writes, design event/write-stream uniqueness keys if the domain forbids parallel interactions between the same pair. Neo4j does not inherently restrict "one relationship per endpoint pair" in all cases.

Verify data:

~~~cypher
MATCH (u:GdsDemoUser)-[:DEMO_INTERACTED]->(i:GdsDemoItem)
RETURN u.userId AS userId,
       collect(DISTINCT i.itemId) AS items
ORDER BY userId;
~~~

In real datasets, `DEMO_INTERACTED` might represent "ever interacted" rather than raw click counts. If every click is stored as its own event relationship, decide how to **deduplicate per product** before applying set-based neighbor similarity measures.

## 3. Similarity from Neighbor Sets

Let \(N(u)\) be the set of products user \(u\) interacted with. Structural algorithms measure relationships between \(N(u)\) and \(N(v)\) without necessarily needing text or embeddings.

### 3.1. Common Neighbors

The simplest score is the count of shared elements:

\[
\operatorname{CN}(u,v)=|N(u)\cap N(v)|.
\]

On the sample data:

- `CN(U1,U2) = 2` (sharing P1, P2).
- `CN(U2,U3) = 2` (sharing P2, P4).
- `CN(U1,U3) = 1` (sharing P2).
- `CN(U1,U4) = 0`.

Common neighbors can bias toward highly active users because they have more chances to overlap. Two pairs both scoring `2` do not necessarily share the same proportion of interests.

### 3.2. Jaccard Similarity

Jaccard normalizes common neighbor count by the size of the union:

\[
\operatorname{Jaccard}(u,v)=
\frac{|N(u)\cap N(v)|}{|N(u)\cup N(v)|}.
\]

For two non-empty sets, the result ranges from 0 to 1, where 1 means identical sets. When both sets are empty, the denominator is 0 and a handling convention must be defined rather than dividing blindly.

| Pair | Intersection | Union | Jaccard |
| --- | ---: | ---: | ---: |
| U1, U2 | 2 | 4 | 0.500 |
| U1, U3 | 1 | 4 | 0.250 |
| U2, U3 | 2 | 3 | 0.667 |
| U1, U4 | 0 | 4 | 0 |

**Key observation:** U1–U2 and U2–U3 share the same two products, yet U2–U3 has a higher overlap ratio because their combined interest set is smaller.

You can verify this calculation in Cypher:

~~~cypher
MATCH (:GdsDemoUser {userId: 'U1'})
      -[:DEMO_INTERACTED]->(ia:GdsDemoItem)
WITH collect(DISTINCT ia.itemId) AS aItems
MATCH (:GdsDemoUser {userId: 'U2'})
      -[:DEMO_INTERACTED]->(ib:GdsDemoItem)
WITH aItems, collect(DISTINCT ib.itemId) AS bItems
WITH aItems, bItems,
     size([x IN aItems WHERE x IN bItems]) AS common
RETURN common,
       size(aItems) + size(bItems) - common AS unionSize,
       toFloat(common) /
         (size(aItems) + size(bItems) - common) AS jaccard;
~~~

On the fixture, this yields `common = 2`, `unionSize = 4`, and `jaccard = 0.5`. This is easy to follow for one pair; computing across millions of pairs calls for GDS algorithms and candidate-pruning strategies.

### 3.3. Cosine, Overlap, and Methods to Dampen Hub Influence

Representing each user as a binary interaction vector gives cosine similarity:

\[
\operatorname{Cosine}(u,v)=
\frac{|N(u)\cap N(v)|}
{\sqrt{|N(u)|\,|N(v)|}}.
\]

The overlap coefficient measures \(|N(u)\cap N(v)|/\min(|N(u)|,|N(v)|)\) when the smaller set is non-empty. Overlap equals 1 whenever one user's interests are a strict subset of another's, even if the two sets differ in size.

In link prediction, an **ultra-popular product** can make everyone look "similar" simply because everyone interacts with it. Heuristics such as *Adamic–Adar* or *Resource Allocation* down-weight high-degree neighbors:

\[
\operatorname{AA}(u,v)=
\sum_{z\in N(u)\cap N(v)}\frac{1}{\log |N(z)|},
\qquad
\operatorname{RA}(u,v)=
\sum_{z\in N(u)\cap N(v)}\frac{1}{|N(z)|}.
\]

These formulas require proper degree guards; never blindly compute `log(1)=0` in the denominator. In a bipartite graph, \(N(z)\) is the set of users connected to product \(z\). These measures encode the assumption: *sharing interest in a rare product carries stronger signal than sharing a product almost everyone owns*.

No single metric fits every case. Depending on the goal, popularity can be useful signal rather than noise. Base choices on evaluation datasets and product policies.

## 4. Computing Node Similarity with Neo4j Graph Data Science

**GDS is a separate component that must be installed/licensed appropriately and matched to your running Neo4j version.** The `gds.*` procedures below will not work if the system only has Neo4j without GDS. Syntax examples target the GDS 2.x series; check docs for your installed version before deploying to production.

### 4.1. In-Memory Graph Projection

GDS computes over an **in-memory projected graph** (*named graph projection*). Projections select required labels, relationship types, orientations, and properties. They are **distinct** from the persistent graph stored in Neo4j.

~~~cypher
CALL gds.graph.project(
  'gds_demo_recommendations',
  ['GdsDemoUser', 'GdsDemoItem'],
  {DEMO_INTERACTED: {orientation: 'UNDIRECTED'}}
)
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;
~~~

This projection includes demo nodes and interaction edges, treating each edge as **bidirectional in memory** so neighbor sets can be compared. It does not alter the direction of `DEMO_INTERACTED` relationships stored in the database. Reported relationship counts reflect GDS's `UNDIRECTED` internal representation and need not equal the persistent `DEMO_INTERACTED` count.

Before creating the same name again, inspect the catalog:

~~~cypher
CALL gds.graph.list('gds_demo_recommendations')
YIELD graphName, nodeCount, relationshipCount, memoryUsage
RETURN graphName, nodeCount, relationshipCount, memoryUsage;
~~~

Named graphs consume GDS memory and have independent lifecycles. Modifying nodes/relationships in the database after a projection is built **does not auto-update projected structures**; refresh projections appropriately before re-running algorithms.

### 4.2. Running Node Similarity

~~~cypher
CALL gds.nodeSimilarity.stream(
  'gds_demo_recommendations',
  {
    topK: 10,
    similarityCutoff: 0.01
  }
)
YIELD node1, node2, similarity
WITH gds.util.asNode(node1) AS a,
     gds.util.asNode(node2) AS b,
     similarity
WHERE a:GdsDemoUser AND b:GdsDemoUser
RETURN a.userId AS userA,
       b.userId AS userB,
       similarity
ORDER BY similarity DESC, userA ASC, userB ASC;
~~~

In this projection, Node Similarity defaults to **Jaccard over neighbors**. On the clean demo data with no parallel edges, pairs U2–U3, U1–U2, and U1–U3 score roughly `0.667`, `0.5`, and `0.25`, respectively. Pairs involving U4 score 0 and thus fall below `similarityCutoff: 0.01`.

Key points to read accurately:

- `node1`, `node2` are **node IDs inside the GDS graph projection**; `gds.util.asNode(...)` maps them back to Neo4j nodes while the projection matches.
- `topK` caps pairs retained **per the algorithm's rule**, not necessarily a global top-K across the entire graph; the same pair may appear in both directions depending on configuration/output.
- Because the projection includes both `GdsDemoUser` and `GdsDemoItem`, the algorithm also evaluates product-to-product similarity. Filtering `WHERE a:GdsDemoUser AND b:GdsDemoUser` only filters user pairs **after the algorithm runs**; it does not save the cost of computing other node-type pairs.
- On large graphs, narrow node/relationship scope and use algorithm source/target filters if supported by your GDS version rather than post-filtering final output. Also evaluate memory requirements.

### 4.3. Estimating Resources Before Running

~~~cypher
CALL gds.nodeSimilarity.stream.estimate(
  'gds_demo_recommendations',
  {
    topK: 10,
    similarityCutoff: 0.01
  }
)
YIELD nodeCount, relationshipCount, requiredMemory
RETURN nodeCount, relationshipCount, requiredMemory;
~~~

`.estimate` previews algorithmic resource needs, though it is **not a runtime guarantee**. On graphs with ultra-popular items, candidate pairs can grow massive. Never extrapolate runtime or cost from four demo users to millions of users linearly.

## 5. Recommending Links from Shared Neighbors

**Node similarity** only tells you which users are alike; a product recommender needs an extra step turning similarity into **unseen products**.

### 5.1. Generating Candidate Items with Cypher

For U1, we can find peers sharing at least one product, then surface products those peers interacted with that U1 has not yet touched:

~~~cypher
MATCH (u:GdsDemoUser {userId: 'U1'})
      -[:DEMO_INTERACTED]->(seed:GdsDemoItem)
MATCH (peer:GdsDemoUser)-[:DEMO_INTERACTED]->(seed)
WHERE peer <> u
MATCH (peer)-[:DEMO_INTERACTED]->(candidate:GdsDemoItem)
WHERE NOT EXISTS {
  MATCH (u)-[:DEMO_INTERACTED]->(candidate)
}
RETURN candidate.itemId AS suggestedItem,
       count(DISTINCT peer) AS supportingPeers,
       count(DISTINCT seed) AS sharedSeedItems
ORDER BY supportingPeers DESC,
         sharedSeedItems DESC,
         suggestedItem ASC
LIMIT 10;
~~~

On the demo data, **P4** is recommended to U1 because both U2 and U3 interacted with P4 while U1 has not. Two metrics:

- `supportingPeers` counts distinct other users endorsing the item.
- `sharedSeedItems` counts distinct initial items connecting U1 to peers suggesting that candidate.

These are **ranking heuristics**, not purchase probabilities. Using `DISTINCT` avoids accidentally double-counting the same peer across multiple seed items.

### 5.2. Combining Similarity Scores with Recommendations

A more advanced idea computes \(s(u,v)\) between target user \(u\) and peer \(v\), then sums scores across peers who interacted with candidate item \(i\):

\[
\operatorname{score}(u,i)
=\sum_{v\in P(i)}s(u,v),
\]

where \(P(i)\) contains filtered peers linked to item \(i\). You can multiply by recency or signal-quality weights. Using Jaccard scores, a closer peer contributes more than a peer sharing only a single item.

**Always define each edge type's meaning:** `VIEWED`, `LIKED`, and `BOUGHT` differ in signal strength; collapsing them into one unweighted `INTERACTED` loses vital information. If users merely browse items, recommending purchases from views alone does not guarantee accurate purchase prediction.

### 5.3. Link Prediction in Homogeneous Graphs

With `(:Person)-[:FOLLOWS]->(:Person)`, the goal might be suggesting accounts to follow. Common neighbors, Adamic–Adar, or resource allocation use two-hop structures as features. However, **edge direction is a business constraint**:

~~~text
(A)-[:FOLLOWS]->(B)
(C)-[:FOLLOWS]->(B)
~~~

A and C both follow B, yet that does not prove A wants to follow C. Defining incoming/outgoing neighbor sets, candidate edge types, relationship validity, and user blocklists are integral parts of link prediction. A high score never justifies automatically writing edges into Neo4j.

## 6. Link Prediction with Machine Learning Models

Heuristics are easy to interpret, yet when combining multiple signals, a link prediction model can learn from historical data:

~~~text
Graph + historical link labels
             |
   Split train / validation / test
             |
   Build features on train graph
   (neighbors, PageRank, embeddings,
    properties, temporal signals...)
             |
   Train model
             |
   Score candidate node pairs
             |
   Evaluate and pick threshold / top-K
             |
   Deploy + monitor + retrain
~~~

GDS includes ML workflows/pipelines for link prediction depending on version and edition. Pipeline syntax, model choices, and training features evolve across releases; verify capabilities on your target system before embedding specific pipeline commands into migrations or jobs.

### 6.1. Positive, Negative, and Candidate Pairs

- **Positive:** real links formed during the observation window under a clear business definition.
- **Negative:** unlinked pairs sampled as negative examples; **missing edges do not always mean links will never form**.
- **Candidate:** valid pairs scored at inference time after filtering out existing edges and permission/status constraints.

In very sparse graphs, unlinked pairs vastly outnumber linked ones. Choosing overly easy negative samples yields flattering test scores while failing to separate hard real-world candidates in production.

### 6.2. Avoiding *Data Leakage*

Suppose you predict whether users will interact with products in October. If you build graph projections or embeddings over **all data through November**, the model may already "see" the very edges it is supposed to predict. Offline metrics then look artificially high.

Proper temporal setup:

1. Fix prediction timestamp \(T\) and events observable strictly before \(T\).
2. Compute features, graph projections, and embeddings **only from data known at \(T\)**.
3. Identify links appearing in the window after \(T\) as test labels.
4. Use validation to tune hyperparameters and a separate test split for final reporting.
5. Never include the same target edge in both the feature graph and the "to-predict" label set.

For non-temporal relationships, design edge-splitting and sampling strategies carefully while preserving sufficient structural context in the training graph. Random splits can still leak information when edges touching the same entity appear across splits.

## 7. Node Embeddings: Turning Graph Structure into Vectors

Embeddings map each node \(v\) to a vector:

\[
f(v)\in\mathbb{R}^{d},
\]

where \(d\) is the configured dimensionality (e.g., 64 or 128). A good algorithm preserves useful structural or contextual signals in vector space so related nodes sit close together.

| Method | Primary Signal | When to Consider |
| --- | --- | --- |
| **FastRP** | Random projection capturing multi-hop neighborhood structure; can incorporate node features. | Fast structural embeddings on large graphs for kNN/ML inputs. |
| **Node2Vec** | Random walks sampling node neighborhoods; learns representations from node sequences. | Tuning local vs. global exploration; acceptable walk/training cost. |
| **GraphSAGE** | Learns aggregation functions over neighbors/properties; inductive for unseen nodes when supported. | Rich node features and need to infer embeddings for new nodes. |
| **Text embedding** from descriptions | Textual semantics of titles/descriptions. | Content similarity; does not encode link structure unless combined with graph signals. |

FastRP/Node2Vec embeddings primarily capture **graph structure**. Language-model vectors primarily capture **textual content**. They are not interchangeable, nor do they share a directly comparable vector space.

### 7.1. FastRP Stream Example

After creating the `gds_demo_recommendations` projection, run:

~~~cypher
CALL gds.fastRP.stream(
  'gds_demo_recommendations',
  {
    embeddingDimension: 64,
    randomSeed: 42
  }
)
YIELD nodeId, embedding
WITH gds.util.asNode(nodeId) AS n, embedding
WHERE n:GdsDemoUser
RETURN n.userId AS userId,
       size(embedding) AS dimensions,
       embedding[0..5] AS firstFiveValues
ORDER BY userId;
~~~

Each `GdsDemoUser` receives a 64-dimensional vector; the example slices the first five values for readability. **Vector components are not human-labeled features like "affinity for product P1"**; they are learned/projected structural coordinates. Never interpret individual dimensions as standalone business rules.

`randomSeed` aids reproducibility under controlled conditions, though differing GDS versions, execution settings, data ordering, or concurrency can still alter bit-level vectors. When comparing quality across runs, log configuration, GDS version, projection data, and normalization.

### 7.2. Dimensionality and Proximity Measures

Two common vector comparison formulas:

\[
\operatorname{cosine}(a,b)
=\frac{a\cdot b}{\lVert a\rVert\lVert b\rVert},
\qquad
\operatorname{distance}_{2}(a,b)
=\sqrt{\sum_{j=1}^{d}(a_j-b_j)^2}.
\]

Cosine focuses on the **angle** between vectors, whereas Euclidean distance measures coordinate differences. The right metric depends on embedding generation, normalization, and objective. High cosine similarity does not guarantee two users are identical operationally; input data and training dictate what "close" means.

Never compare a 64-dimensional FastRP vector directly against a 64-dimensional text embedding just because they share the same length. They come from incompatible processes and vector spaces.

## 8. Combining FastRP and kNN to Find Nearby Nodes

`gds.fastRP.stream` only returns vectors in query output. To reuse them inside GDS for kNN, use **mutate** mode to store the vector property in the **in-memory graph**, without writing to persistent database nodes.

### 8.1. Writing Embeddings into the Graph Projection

~~~cypher
CALL gds.fastRP.mutate(
  'gds_demo_recommendations',
  {
    embeddingDimension: 64,
    randomSeed: 42,
    mutateProperty: 'fastRpEmbedding'
  }
)
YIELD nodePropertiesWritten
RETURN nodePropertiesWritten;
~~~

At this point, `fastRpEmbedding` lives in the GDS graph catalog. It does not appear as `n.fastRpEmbedding` when querying Neo4j nodes in Cypher.

### 8.2. Finding Nearest Neighbors on Vectors

~~~cypher
CALL gds.knn.stream(
  'gds_demo_recommendations',
  {
    nodeProperties: ['fastRpEmbedding'],
    topK: 8
  }
)
YIELD node1, node2, similarity
WITH gds.util.asNode(node1) AS a,
     gds.util.asNode(node2) AS b,
     similarity
WHERE a:GdsDemoUser AND b:GdsDemoUser
RETURN a.userId AS userA,
       b.userId AS userB,
       similarity
ORDER BY similarity DESC, userA ASC, userB ASC;
~~~

kNN finds nearest neighbors in **vector space**. Results need not match Jaccard rankings identically because FastRP compressed structure into vectors and kNN measures distance in that space. GDS kNN uses sampling/approximate search heuristics depending on configuration and scale; do not assume exact all-pairs comparison.

The example projection includes **both users and items**. `topK: 8` is wide enough for a nine-node demo graph, yet at large scale, filtering `WHERE a:GdsDemoUser AND b:GdsDemoUser` **after** kNN may leave very few users if nearest neighbors happen to be items. If the product requires top-K **strictly among users**, build a user-only vector projection or configure source/target filters supported by your GDS version before applying top-K.

### 8.3. How Stream, Mutate, and Write Differ

| GDS Mode | Output | Modifies Persistent Neo4j? |
| --- | --- | --- |
| `stream` | Returns rows/scores/vectors to Cypher or driver. | No. |
| `stats` (if supported) | Aggregate run statistics. | No. |
| `mutate` | Adds node/relationship properties to in-memory GDS graph. | Not directly. |
| `write` | Writes supported properties or relationships back to Neo4j. | Yes. |

When persisting recommendations or embeddings for repeated requests, explicitly decide storage location, refresh cadence, and result versioning. **Never treat a GDS projection as a persistent database.**

## 9. Storing Embeddings and Querying with a Vector Index

GDS kNN fits neighbor discovery over a graph projection. Once an application persists embeddings as node properties, **Neo4j's vector index** supports fast approximate top-K vector queries, commonly used on online read paths.

### 9.1. Writing Demo Vectors Back to Neo4j

On the learning database, after running `fastRP.mutate`:

~~~cypher
CALL gds.graph.nodeProperties.write(
  'gds_demo_recommendations',
  ['fastRpEmbedding']
)
YIELD propertiesWritten
RETURN propertiesWritten;
~~~

This writes the property onto demo nodes contained in the projection; it does not create predicted relationships. In production, write only to targeted node sets, check memory and vector property size, and attach operational metadata such as `embeddingVersion`/`calculatedAt`.

### 9.2. Creating a Vector Index for Users

Example Neo4j 5 syntax supporting vector indexes:

~~~cypher
CREATE VECTOR INDEX gds_demo_user_embedding_idx IF NOT EXISTS
FOR (u:GdsDemoUser)
ON (u.fastRpEmbedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 64,
    `vector.similarity_function`: 'cosine'
  }
};
~~~

`vector.dimensions` must match the actual vectors. Wait until the index reaches `ONLINE` state before treating lookup results as ready:

~~~cypher
SHOW INDEXES
YIELD name, type, state, properties
WHERE name = 'gds_demo_user_embedding_idx'
RETURN name, type, state, properties;
~~~

### 9.3. Finding Users Closest to U1's Vector

~~~cypher
MATCH (u:GdsDemoUser {userId: 'U1'})
WITH u, u.fastRpEmbedding AS queryVector
CALL db.index.vector.queryNodes(
  'gds_demo_user_embedding_idx',
  4,
  queryVector
)
YIELD node, score
WHERE node <> u
RETURN node.userId AS suggestedUserId, score
ORDER BY score DESC, suggestedUserId ASC
LIMIT 3;
~~~

This query returns nearby nodes in the index under the vector index's scoring function. It **does not prove** users will become friends or buy items; apply business filters, evaluation, and ranking. Vector index features, procedure syntax, and newer search methods can vary across Neo4j releases; verify against your target environment. Never mix vector index `score` values with Jaccard or GDS kNN scores as if on a single scale.

**Key distinction:** creating a vector index **does not generate embeddings**. You still need vector computation, persistence, and freshness checks. When embedding models or dimensions change, plan index rebuilds and compatible read-path rollouts.

## 10. Evaluating Recommendation Quality

An algorithm returning scores is not automatically useful. Evaluation must start from **product objectives** and user interaction behavior.

### 10.1. Top-K Metrics

Suppose for user U, the system recommends 5 products and during the evaluation window the user interacts with 2 of them. Common metrics:

| Metric | Meaning | Note |
| --- | --- | --- |
| Precision@K | Out of K recommendations, how many are relevant per ground truth labels? | Does not reveal whether all relevant items were found. |
| Recall@K | Out of all relevant items, how many appear in top-K? | Requires a sufficiently reliable set of relevant items. |
| Hit Rate@K | Fraction of cases with at least one relevant hit in top-K. | Can be high even when ordering and remaining items are poor. |
| MRR / NDCG@K | Evaluates ranking position of hits; NDCG also handles graded relevance. | Essential when display order matters. |
| ROC-AUC, PR-AUC | Evaluates discrimination between positive and negative pairs. | Sensitive to negative sampling; PR-AUC helps when positives are rare. |
| Coverage / Diversity / Novelty | Item catalog reach and recommendation variety. | Crucial for catching over-recommendation of popular items. |

Illustrative example: 2 hits out of 5 recommendations gives `Precision@5 = 2/5 = 0.4`. If the ground-truth test set holds 4 relevant items total, `Recall@5 = 2/4 = 0.5`. Do not apply these calculations naively to items users were never exposed to: lack of interaction does not necessarily mean disinterest.

### 10.2. Offline vs. Online Evaluation

- **Offline:** uses historical data with temporal splits, enabling repeatable algorithm comparisons before deployment.
- **Online:** monitors CTR, conversions, satisfaction, complaint rates, latency impact, and business risks.

Strong offline metrics may not translate into strong online performance due to presentation bias, feedback loops, shifting user behavior, or item freshness. Control experimental conditions when measuring real impact.

### 10.3. Representative Evaluation Datasets

At minimum, test across:

1. Low-, medium-, and high-activity users.
2. Long-tail items and ultra-popular *hub* items.
3. New users or new items (*cold start*).
4. Multiple tenants or segments with distinct data rules.
5. Node updates/deletions, permission changes, and edges arriving after embeddings were computed.
6. Tied-score pairs to verify tie-breaking and pagination stability.

For new users/items lacking edges, neighbor-based similarity yields almost no signal. Supplement with content attributes, permitted contextual features, or controlled popularity fallbacks—explicitly documented as a cold-start strategy.

## 11. Performance and Data Safety When Running Algorithms

### 11.1. Candidate Pair Explosion

With \(n\) nodes, distinct node pairs scale up to \(n(n-1)/2\). Algorithms do not necessarily check all pairs naively, yet similarity computation on large graphs still demands substantial memory and CPU—especially with **supernodes** linked to millions of nodes.

Ways to control cost:

- Project only the labels, relationship types, and time windows genuinely needed.
- Partition by tenant/business group when supported by the algorithm and model.
- Configure minimum/maximum degree cutoffs and top-K bounds where supported.
- Estimate GDS memory beforehand; schedule batch jobs around read/write load.
- Use approximate vector retrieval when latency/accuracy trade-offs permit.
- Measure p50/p95/p99 latencies, projection build time, algorithm runtime, and recompute costs—not just one demo query.

Verify carefully before dropping supernodes: popular hubs sometimes carry critical signal. Pruning them changes semantics, not just load.

### 11.2. Versioning and Embedding Freshness

A vector computed from yesterday's graph loses accuracy as new edges arrive. When persisting embeddings or recommendations for online serving, store operational metadata such as:

| Metadata | Purpose |
| --- | --- |
| `algorithmVersion`, algorithm parameters | Reproducibility of vectors/scores. |
| `graphSnapshotAt` or source watermark | Tracks input data cutoff time. |
| `embeddingDimension`, similarity function | Ensures compatibility with index and queries. |
| `calculatedAt` | Tracks output age and expiration policy. |
| `tenantId` / access scope | Prevents serving unauthorized cross-scope suggestions. |

If old and new embeddings come from **different models or vector spaces**, never mix them in nearest-neighbor searches without verifying compatibility. A standard rollout computes the new version, validates it, switches the read path, and only then retires old data/indexes.

### 11.3. Access Control and Fairness

Connections between users can be sensitive even without exposing personal attributes. Graph projections and embeddings must respect permission/tenant boundaries: never let one user infer private relationships through recommendation lists or similarity scores.

Likewise, historical interaction data can over-amplify already popular users/items while starving newcomers. Monitor coverage, diversity, subgroup fairness, and explainability for high-impact recommendations. Never treat raw algorithm scores as fully autonomous, infallible decisions.

## 12. Integrating Results with Java Driver and Spring Data Neo4j

In applications, GDS jobs typically run on a schedule to compute similarity or embeddings, while APIs read materialized outputs and enforce business rules. For small algorithmic queries, the Java Driver can also invoke procedures directly:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Record;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

import java.util.List;

public final class GraphSimilarityJob {
    private final Driver driver;

    public GraphSimilarityJob(Driver driver) {
        this.driver = driver;
    }

    public List<Record> userPairs() {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            return session.run("""
                CALL gds.nodeSimilarity.stream(
                  'gds_demo_recommendations',
                  {topK: 10, similarityCutoff: 0.01}
                )
                YIELD node1, node2, similarity
                WITH gds.util.asNode(node1) AS a,
                     gds.util.asNode(node2) AS b,
                     similarity
                WHERE a:GdsDemoUser AND b:GdsDemoUser
                RETURN a.userId AS userA,
                       b.userId AS userB,
                       similarity
                ORDER BY similarity DESC, userA ASC, userB ASC
                """).list();
        }
    }
}
~~~

This example assumes an initialized `Driver` and the named projection from Section 4; `neo4j` is illustrative. In production, map to DTOs instead of `Record`, enforce timeouts, check memory estimates, and paginate or bound results. Never run whole-graph algorithms inside synchronous HTTP requests when cost is high.

With **Spring Data Neo4j**, entities/repositories manage nodes, relationships, and properties, while GDS runs via appropriate Cypher/driver/client calls. Entity mapping annotations **do not automatically generate embeddings or compute similarity**. Separating compute jobs, persistence, and read APIs helps control freshness and resource contention.

## 13. Verifying and Cleaning Up Practice Data

If following Sections 2–9 sequentially, verify:

~~~cypher
MATCH (u:GdsDemoUser)
RETURN count(u) AS userCount;
~~~

~~~cypher
MATCH (u:GdsDemoUser)-[r:DEMO_INTERACTED]->(i:GdsDemoItem)
RETURN count(r) AS interactionCount,
       count(DISTINCT u) AS usersWithInteractions,
       count(DISTINCT i) AS itemsWithInteractions;
~~~

On the clean fixture, there are 4 users, 5 items, and 9 interaction relationships. If counts are higher, check whether old demo data remained in the database before comparing algorithm outputs.

Once done, drop the **in-memory projection**:

~~~cypher
CALL gds.graph.drop('gds_demo_recommendations');
~~~

If you created the vector index in Section 9 and no longer need it:

~~~cypher
DROP INDEX gds_demo_user_embedding_idx IF EXISTS;
~~~

To remove demo nodes from your **dedicated learning database**, delete only the exercise labels:

~~~cypher
MATCH (u:GdsDemoUser)
DETACH DELETE u;
~~~

~~~cypher
MATCH (i:GdsDemoItem)
DETACH DELETE i;
~~~

Finally, drop the two demo constraints if no longer needed:

~~~cypher
DROP CONSTRAINT gds_demo_user_id_unique IF EXISTS;
~~~

~~~cypher
DROP CONSTRAINT gds_demo_item_id_unique IF EXISTS;
~~~

`DETACH DELETE` deletes all relationships attached to target nodes; run it only after confirming those nodes belong strictly to the practice fixture. Never delete other labels/relationships or run bulk cleanup on a production database.

## 14. Common Errors and Troubleshooting

| Symptom | Possible Cause | How to Check / Fix |
| --- | --- | --- |
| `There is no procedure with the name gds...` | GDS not installed, version mismatch, or missing permissions. | Check plugin/edition, version, and execute privileges. |
| Graph projection already exists | Re-ran `gds.graph.project` with the same catalog name. | Check `gds.graph.list`; reuse existing or drop/recreate deliberately. |
| Similarity differs from hand calculation | Duplicate edges, projection orientation, weights, filters, algorithm, or top-K mismatch. | Print actual neighbor sets and cross-check metric definitions. |
| U4 receives no recommendations | No shared neighbors in the sample. | Design a cold-start fallback instead of forcing artificial similarity. |
| kNN returns items when users were expected | Projection holds both users and items; filtered after kNN. | Use a user-only projection/filter before applying top-K. |
| Embedding missing in `MATCH (n) RETURN n.embedding` | Only ran `stream` or `mutate`, not persisted to Neo4j. | Distinguish execution modes and write properties if required. |
| Vector index returns no results | Index not `ONLINE`, missing/wrong-dimension/wrong-type vectors, or incompatible query. | Check `SHOW INDEXES` and vector properties on nodes. |
| Suspiciously high offline score | Target labels/edges leaked into the feature graph. | Split train/test chronologically before computing features/embeddings. |
| Recommends already-linked items | Failed to exclude existing edges. | Use `NOT EXISTS { MATCH ... }` on relevant business relationships. |
| Cross-tenant recommendations | Projection or filter omits permission boundaries. | Enforce data-source, permission, tenant, and serving filters. |
| GDS resource usage spikes | Overly broad projection, supernodes, or pair explosion. | Run memory estimates, inspect degrees, narrow scope, and schedule jobs. |

## 15. Self-Practice Exercises

**Exercise 1 — Hand Calculation.** Given U1 = {P1, P2, P3}, U2 = {P1, P2, P4}, and U3 = {P2, P4}, compute common neighbors, Jaccard, and cosine for all three pairs. Explain why Jaccard rankings can differ from common neighbors.

**Exercise 2 — Node Similarity.** Create the Section 2 fixture and Section 4 projection, then run `gds.nodeSimilarity.stream`. Compare U1–U2 against your hand calculation; explain why U4 is absent when `similarityCutoff > 0`.

**Exercise 3 — Product Recommendations.** Write a query returning products U1 has not interacted with that peers sharing products with U1 have interacted with. Rank by supporting peer count. In the fixture, which product should rank first?

**Exercise 4 — From Heuristics to ML.** Describe a temporal train/validation/test split for predicting `:BOUGHT` edges. Explain what happens if embeddings are computed from a graph already containing test-set purchase edges.

**Exercise 5 — Embeddings and kNN.** Compute 64-dimensional FastRP vectors, mutate them into the named graph, and run kNN. Why need kNN scores not match Jaccard? Explain how to ensure all compared candidates are users before taking top-K.

**Exercise 6 — Cold Start and Operations.** A new product has no `DEMO_INTERACTED` edges yet, but has rich text descriptions. Propose how to recommend it, a vector refresh schedule, and evaluation metrics to verify whether the strategy improves user experience.

**Exercise 7 — Access Control.** A graph holds users across multiple tenants plus private relationships. Describe controls at projection, scoring, embedding storage, and API layers to prevent leaking connections outside authorized scopes.

## 16. Checklist Before Deploying Algorithms to Production

1. **Right problem:** are you measuring similarity, predicting an edge, or searching nearby vectors?
2. **Right graph:** do labels, types, orientations, weights, time windows, and tenant filters in the projection reflect authorized data?
3. **Right signals:** have duplicate edges, supernodes, cold start, popularity bias, and view vs. like vs. purchase semantics been handled?
4. **Right evaluation:** are train/test splits leak-free, top-K metrics tied to product goals, and online experiments planned?
5. **Operational readiness:** do you have memory estimates, refresh schedules, version metadata, node/edge update policies, and projection cleanup?
6. **Data authorization:** could scores, vectors, or recommendations expose private links or cross tenant boundaries?
7. **Baseline comparison:** do you have a simple Cypher/heuristic baseline proving GDS or embeddings deliver real added value?

**Core takeaway:** similarity measures structural relatedness, link prediction uses those signals to rank **missing edges**, and node embeddings compress structure/context into vectors so proximity operations run smoothly. With Neo4j, coordinate **Cypher, GDS graph projections, algorithms, indexes, and business rules**; model quality depends on input data, evaluation rigor, and operational discipline—not a single similarity number.
