# Saving Sample Queries, Managing Scripts, and Reproducing Practice Datasets with Neo4j

When learning Neo4j, running a few Cypher statements in Neo4j Browser makes exploring a graph very fast. However, command history inside a single session is not enough to share exercises, review changes, or rebuild data after experimenting. A reliable practice environment needs **sample queries saved as files**, **scripts with a clear execution order**, and **datasets that can be reproduced from a known state**.

This lesson belongs to the **Developer Tools** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module. Examples use Neo4j's property graph: nodes and relationships carrying properties, Cypher queries, and constraints and indexes supporting data integrity. The workflow applies when learning Cypher, testing path queries, trying Java Driver, or preparing data for Spring Data Neo4j.

## 1. Objectives and Principles

After this lesson, you will be able to:

1. Save and name Cypher queries for lookup, re-execution, and version control.
2. Split scripts into steps for creating constraints, loading data, querying, verifying, and cleaning up data.
3. Build a sample dataset with `MERGE` so it can be run repeatedly without creating duplicate nodes or relationships for a given identifier key.
4. Distinguish **reloading** data from **restoring the exact initial dataset**, and verify results using node counts, relationship counts, and business queries.
5. Know when to use `LOAD CSV`, how to pass parameters, and how to inspect a query's execution plan.

| Item to Save | Contents | Benefit |
| --- | --- | --- |
| Sample queries | `MATCH`, `WHERE`, `RETURN`, `EXPLAIN`, `PROFILE` statements | Easy to review, reproduce bugs, compare query formulations |
| Initialization scripts | Constraints/indexes and sample data | Establishes a consistent practice environment |
| Verification scripts | Queries confirming structure and data | Detects missing data or relationships |
| Reset scripts | Deletes only experimental data | Starts exercises from a clean state |
| README and CSV files | Execution prerequisites, run order, input data | Others can repeat the exact same practice lab |

> Core principle: **every practice run must know which script version was executed, with which dataset, and what results are expected**.

## 2. Organizing the Script Directory

Place the files below in a practice directory that can be tracked in Git. This is a **suggested layout**; the code snippets in this lesson serve as the contents of those corresponding files when you create your own practice project.

~~~text
neo4j-lab/
├── README.md
├── cypher/
│   ├── 00_constraints.cypher
│   ├── 10_seed.cypher
│   ├── 20_examples.cypher
│   ├── 30_verify.cypher
│   └── 90_reset.cypher
└── data/
    └── courses.csv
~~~

The naming convention `00_`, `10_`, `20_` indicates execution order. Separate `90_reset.cypher` from loading steps to avoid accidental data deletion. Save each Cypher statement completely with a trailing `;`. Document the **purpose, inputs, expected results, and version notes** at the top of each file or in `README.md`.

A `.cypher` file can contain multiple statements, but you should not assume the entire file automatically becomes a single transaction. When atomicity or error recovery is required, design transactions and error handling appropriate for your runner tool, Neo4j version, and real requirements.

## 3. Designing a Reproducible Sample Dataset

We build a simple domain: students enroll in courses; each course covers multiple topics.

~~~mermaid
flowchart LR
    A["DemoLearner<br/>learnerId, name"] -->|ENROLLED_IN<br/>enrolledAt| B["DemoCourse<br/>code, title"]
    B -->|COVERS| C["DemoTopic<br/>slug, title"]
~~~

All three node types also carry the `LabPractice` label so data belonging specifically to this practice lab can be identified. The stable identifier keys are `learnerId`, `code`, and `slug`; do not use database-assigned internal IDs as business keys.

| Node Label | Sample Data | Expected Count |
| --- | --- | ---: |
| `DemoLearner` | L001/An, L002/Bình, L003/Chi | 3 |
| `DemoCourse` | C001/Neo4j Fundamentals, C002/Cypher Optimization, C003/Spring Data Neo4j | 3 |
| `DemoTopic` | property-graph, cypher, java-driver | 3 |
| `ENROLLED_IN` | L001→C001, L001→C002, L002→C001, L003→C003 | 4 |
| `COVERS` | C001→property-graph, C001→cypher, C002→cypher, C003→java-driver | 4 |

When complete, the graph has **9 nodes** and **8 relationships** belonging to the practice dataset. These numbers provide a concrete verification baseline.

### Step 1 — Declaring Constraints

Contents of `cypher/00_constraints.cypher`:

~~~cypher
CREATE CONSTRAINT demo_learner_id IF NOT EXISTS
FOR (l:DemoLearner)
REQUIRE l.learnerId IS UNIQUE;

CREATE CONSTRAINT demo_course_code IF NOT EXISTS
FOR (c:DemoCourse)
REQUIRE c.code IS UNIQUE;

CREATE CONSTRAINT demo_topic_slug IF NOT EXISTS
FOR (t:DemoTopic)
REQUIRE t.slug IS UNIQUE;
~~~

A uniqueness constraint ensures there cannot be two nodes with the `DemoLearner` label sharing the same `learnerId` (and similarly for the other two labels). In Neo4j, a unique constraint also creates an index supporting lookups on the constrained property; therefore, there is no need to create an additional duplicate range index on these same keys. The syntax above fits the Neo4j 5.x line; when working with other versions, check the corresponding DDL syntax.

### Step 2 — Loading Data with MERGE

Contents of `cypher/10_seed.cypher`:

~~~cypher
// 1. Learners
MERGE (l:DemoLearner:LabPractice {learnerId: 'L001'})
SET l.name = 'An';

MERGE (l:DemoLearner:LabPractice {learnerId: 'L002'})
SET l.name = 'Bình';

MERGE (l:DemoLearner:LabPractice {learnerId: 'L003'})
SET l.name = 'Chi';

// 2. Courses
MERGE (c:DemoCourse:LabPractice {code: 'C001'})
SET c.title = 'Neo4j Fundamentals';

MERGE (c:DemoCourse:LabPractice {code: 'C002'})
SET c.title = 'Cypher Optimization';

MERGE (c:DemoCourse:LabPractice {code: 'C003'})
SET c.title = 'Spring Data Neo4j';

// 3. Topics
MERGE (t:DemoTopic:LabPractice {slug: 'property-graph'})
SET t.title = 'Property graph';

MERGE (t:DemoTopic:LabPractice {slug: 'cypher'})
SET t.title = 'Cypher Querying';

MERGE (t:DemoTopic:LabPractice {slug: 'java-driver'})
SET t.title = 'Neo4j Java Driver';

// 4. Enrollment relationships: match both endpoints by key, then MERGE the relationship
MATCH (l:DemoLearner {learnerId: 'L001'})
MATCH (c:DemoCourse {code: 'C001'})
MERGE (l)-[r:ENROLLED_IN]->(c)
SET r.enrolledAt = date('2026-01-10');

MATCH (l:DemoLearner {learnerId: 'L001'})
MATCH (c:DemoCourse {code: 'C002'})
MERGE (l)-[r:ENROLLED_IN]->(c)
SET r.enrolledAt = date('2026-01-11');

MATCH (l:DemoLearner {learnerId: 'L002'})
MATCH (c:DemoCourse {code: 'C001'})
MERGE (l)-[r:ENROLLED_IN]->(c)
SET r.enrolledAt = date('2026-01-12');

MATCH (l:DemoLearner {learnerId: 'L003'})
MATCH (c:DemoCourse {code: 'C003'})
MERGE (l)-[r:ENROLLED_IN]->(c)
SET r.enrolledAt = date('2026-01-13');

// 5. Course-covers-topic relationships
MATCH (c:DemoCourse {code: 'C001'})
MATCH (t:DemoTopic {slug: 'property-graph'})
MERGE (c)-[:COVERS]->(t);

MATCH (c:DemoCourse {code: 'C001'})
MATCH (t:DemoTopic {slug: 'cypher'})
MERGE (c)-[:COVERS]->(t);

MATCH (c:DemoCourse {code: 'C002'})
MATCH (t:DemoTopic {slug: 'cypher'})
MERGE (c)-[:COVERS]->(t);

MATCH (c:DemoCourse {code: 'C003'})
MATCH (t:DemoTopic {slug: 'java-driver'})
MERGE (c)-[:COVERS]->(t);
~~~

**Why choose `MERGE`?** `CREATE` always creates a new element, whereas `MERGE` looks for a matching pattern before creating. For nodes, put the stable identifier key inside `MERGE` and update descriptive properties using `SET`. For relationships, first `MATCH` the two existing nodes, then `MERGE` the relationship between those exact endpoints; this avoids accidentally creating unexpected nodes when linking. Constraints protect node keys, while uniqueness rules for each relationship type still need to be designed and verified according to business requirements.

Re-running this script with unchanged input data keeps the 9 nodes and 8 relationships intact. However, note: **`MERGE` does not delete extra data** added during other experiments. To return to an *exact* data baseline, use a controlled reset step and then re-seed.

## 4. Saving and Using Sample Queries

The contents of `cypher/20_examples.cypher` can include the following standalone queries:

~~~cypher
// Q01: Which courses is each learner enrolled in?
MATCH (l:DemoLearner:LabPractice)-[:ENROLLED_IN]->(c:DemoCourse:LabPractice)
RETURN l.learnerId AS learnerId,
       l.name AS learner,
       collect(c.title) AS enrolledCourses
ORDER BY learnerId;

// Q02: Two hops from learner to topic through course
MATCH (l:DemoLearner:LabPractice {learnerId: 'L001'})
      -[:ENROLLED_IN]->
      (c:DemoCourse:LabPractice)
      -[:COVERS]->
      (t:DemoTopic:LabPractice)
RETURN c.code AS courseCode,
       t.slug AS topicSlug
ORDER BY courseCode, topicSlug;

// Q03: Learner count per course (including courses with no enrollments yet)
MATCH (c:DemoCourse:LabPractice)
OPTIONAL MATCH (l:DemoLearner:LabPractice)-[:ENROLLED_IN]->(c)
RETURN c.code AS courseCode, count(l) AS learnerCount
ORDER BY courseCode;
~~~

Key results to self-verify: Q01 returns three learners; Q02 returns three rows (two topics from C001 and one topic from C002); Q03 returns `C001: 2`, `C002: 1`, `C003: 1` respectively. Lists produced by `collect()` should not be assumed to have a fixed order unless the query explicitly sorts prior to aggregation.

When saving queries, document the **business question**, **required parameters**, **output shape**, and **performance notes**. For instance, to filter learners flexibly, use a parameter instead of string concatenation:

~~~cypher
MATCH (l:DemoLearner:LabPractice {learnerId: $learnerId})
      -[:ENROLLED_IN]->(c:DemoCourse:LabPractice)
RETURN l.name AS learner, c.code AS courseCode
ORDER BY courseCode;
~~~

In Neo4j Browser, you can declare the parameter separately using the Browser command `:param learnerId => 'L001'`, then run the Cypher statement above. `:param` is a tool command, not pure Cypher; do not arbitrarily mix Browser-specific commands into `.cypher` scripts meant for automated execution. In Java Driver or Spring Data Neo4j, pass parameters via the library's API rather than concatenating user values into the Cypher string.

When investigating performance, run a query with `EXPLAIN` to view the estimated plan or `PROFILE` to execute it and view actual metrics:

~~~cypher
EXPLAIN
MATCH (l:DemoLearner {learnerId: 'L001'})
      -[:ENROLLED_IN]->(c:DemoCourse)
RETURN c.code;
~~~

You can check whether the plan uses the index/constraint when looking up by `learnerId`. However, since the dataset has only a few nodes, timing numbers on this example are **not sufficient** to conclude that an index or query design will be faster on large datasets.

## 5. Verifying That the Dataset Was Created Correctly

Contents of `cypher/30_verify.cypher`:

~~~cypher
// V01: Total nodes belonging to this practice lab: expect 9
MATCH (n:LabPractice)
RETURN count(n) AS nodeCount;

// V02: Node count by type: 3 of each
MATCH (n:LabPractice)
RETURN labels(n) AS nodeLabels, count(*) AS total
ORDER BY nodeLabels;

// V03: Total relationships connecting two practice nodes: expect 8
MATCH (a:LabPractice)-[r]->(b:LabPractice)
RETURN count(r) AS relationshipCount;

// V04: Relationship breakdown: COVERS = 4, ENROLLED_IN = 4
MATCH (a:LabPractice)-[r]->(b:LabPractice)
RETURN type(r) AS relationshipType, count(r) AS total
ORDER BY relationshipType;

// V05: How many learners does each course have?
MATCH (c:DemoCourse:LabPractice)
OPTIONAL MATCH (l:DemoLearner:LabPractice)-[:ENROLLED_IN]->(c)
RETURN c.code AS courseCode, count(l) AS learnerCount
ORDER BY courseCode;
~~~

| Check | Expected Result |
| --- | --- |
| V01 | `nodeCount = 9` |
| V02 | 3 `DemoLearner` nodes, 3 `DemoCourse` nodes, 3 `DemoTopic` nodes (each also carrying the `LabPractice` label) |
| V03 | `relationshipCount = 8` |
| V04 | `COVERS = 4`, `ENROLLED_IN = 4` |
| V05 | `C001 = 2`, `C002 = 1`, `C003 = 1` |

These are queries that **report results for cross-checking**, not yet an automated test suite that raises an error when counts are wrong. In real projects, you can add assertions in integration tests (for example, running Cypher via Java Driver and comparing results against expected values) so CI pipelines catch mismatched data.

## 6. Running Scripts with Neo4j Browser and cypher-shell

You need a running Neo4j instance, an account with permissions to create schema and write data in a **dedicated practice database**, and the `cypher-shell` tool if running from a terminal.

**Manual approach:** Open Neo4j Browser, connect to the right database, paste and execute the file contents in the order `00_constraints.cypher` → `10_seed.cypher` → `20_examples.cypher` → `30_verify.cypher`. This approach is ideal when learning each statement and observing the graph directly.

**Terminal approach:** From the `neo4j-lab` directory, run sequentially:

~~~powershell
cypher-shell -a bolt://localhost:7687 -u neo4j -d neo4j -f cypher/00_constraints.cypher
cypher-shell -a bolt://localhost:7687 -u neo4j -d neo4j -f cypher/10_seed.cypher
cypher-shell -a bolt://localhost:7687 -u neo4j -d neo4j -f cypher/20_examples.cypher
cypher-shell -a bolt://localhost:7687 -u neo4j -d neo4j -f cypher/30_verify.cypher
~~~

Adjust the address, account, and database name for your environment; the tool may prompt for a password. **Never put real passwords into script files, READMEs, or Git.** When automating, fetch credentials from runtime environment secrets and stop the pipeline if any step fails. Do not proceed to verification and report success when the data-creation step failed.

With every script edit, commit the version in Git with a message describing the change; when changing data structures or sample values, also update the **expected results**. Practice seed files differ from production schema migrations: never use a data reset on real data as a substitute for migrations.

## 7. Reproducing the Dataset from a Clean State

Contents of `cypher/90_reset.cypher`:

~~~cypher
// ONLY run on the practice database dedicated to this dataset.
MATCH (n:LabPractice)
DETACH DELETE n;
~~~

The statement above deletes nodes with the `LabPractice` label **and all relationships connected to those nodes**. Therefore, the practice label must only be used on data you actively manage; ideally dedicate a separate database for experimentation. This is an intentional data-deletion script—do not include it in the default data-loading sequence.

When you want to repeat the lesson from the exact initial dataset:

1. Select the right test database and verify this is not an environment holding data you need to keep.
2. Run `90_reset.cypher` once to clear old practice data.
3. Run `00_constraints.cypher` (safe when constraints already exist with the same definition).
4. Run `10_seed.cypher` and then `30_verify.cypher`.
5. Only begin exercises or tests after the verification results match the expected counts.

Constraints still exist after deleting nodes. If you need to fully reproduce the schema, DB version, and configuration as well, spin up a fresh test database using a documented environment setup process; do not automatically drop shared constraints. Reproducibility also depends on **Neo4j version, configuration, source data, and script execution order**.

## 8. Extension: Managing Input Data with CSV

When datasets grow larger, storing source data in CSV lets learners and development teams inspect fixture changes. Example `data/courses.csv`:

~~~csv
code,title
C001,Neo4j Fundamentals
C002,Cypher Optimization
C003,Spring Data Neo4j
~~~

After placing the CSV file in an import location that the **Neo4j server** is permitted to read, you can load it with:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///courses.csv' AS row
WITH row
WHERE row.code IS NOT NULL AND trim(row.code) <> ''
MERGE (c:DemoCourse:LabPractice {code: trim(row.code)})
SET c.title = trim(row.title);
~~~

`file:///courses.csv` is resolved by Neo4j from the **server-side** configured import directory, not automatically from your current terminal working directory. When using Docker, mount the data volume and check read permissions inside the container; when using a managed Neo4j service, local file/URL read policies may differ. The CSV command above is an **alternative way to load course nodes instead of the corresponding section in the seed script**, so you do not need to run both if you want to keep the workflow simple.

For CSV files containing relationships, load nodes first, then load relationships by `MATCH`ing both endpoints by key and `MERGE`ing the edge. Normalize date formats, identifier codes, and empty values before loading; if the source can change, store a version or checksum of the fixture to identify the exact data used.

For large datasets, consider transaction batching, memory limits, and index types before importing. Because this lesson's example has only nine nodes, bulk-loading optimizations are unnecessary.

## 9. Common Errors and How to Handle Them

| Symptom | Common Cause | How to Handle |
| --- | --- | --- |
| Running seed a second time increases node count | Used `CREATE` instead of `MERGE`, or unstable identifier key | Use fixed business keys, `MERGE`, and unique constraints |
| Nodes do not duplicate, but relationships increase | Creating edges with `CREATE` on every load | `MATCH` both endpoints and `MERGE` edges using proper business identifiers |
| `MERGE` succeeds, but verification data has extras | Seed does not automatically delete old records | Reset the lab scope and re-seed in a dedicated practice database |
| `LOAD CSV` cannot find file | File is on the client machine, not in the server's import directory | Check import directory, Docker volume mounts, and read permissions |
| Sample query fails due to missing parameter | `$learnerId` not declared or not passed | Configure the parameter in the tool/app before running |
| Results differ between two machines | Different fixture, script order, configuration, or Neo4j version | Document reproduction conditions in README and verify after seeding |
| Query returns right data but is slow | Large dataset, broad MATCH pattern, suboptimal indexes | Use `EXPLAIN`/`PROFILE`, inspect filter conditions and execution plans |

## 10. Checklist and Practice Exercises

Before sharing your practice set, confirm for yourself:

- [ ] Each `.cypher` file has a clear name, complete statements, and documented run order.
- [ ] Constraints exist for identifier keys used in `MERGE`.
- [ ] Re-running the seed does not increase expected node or relationship counts.
- [ ] Sample data is sufficient to test single-hop, multi-hop, and aggregation queries.
- [ ] Verification queries exist to check counts and business results.
- [ ] Reset affects only the practice label/data and runs on the appropriate database.
- [ ] README documents Neo4j version, connection steps, import steps, and expected results.
- [ ] Passwords and environment secrets are not inside committed files.

**Practice exercises:**

1. Run `00_constraints`, `10_seed`, and `30_verify` twice. Record node and relationship counts after each run to confirm idempotency.
2. Add learner `L004` with an enrollment relationship to `C002`. Run Q03 to observe the count change, then reset and re-seed to return to the initial dataset.
3. Write a query finding learners enrolled in at least one course in common, returning pairs of learners and the shared course code; avoid returning the same pair twice in reverse order.
4. Extract courses to CSV, run `LOAD CSV`, and compare verification results with direct seeding.
5. Replace the hardcoded `learnerId` value with a parameter, try `EXPLAIN`, and explain the role of the unique constraint in the initial node lookup step.

When all scripts, fixtures, and expected results are managed together, you can hand off a Neo4j practice lab from your personal machine to a teammate's machine, re-run queries, and trace root causes whenever data or results change.
