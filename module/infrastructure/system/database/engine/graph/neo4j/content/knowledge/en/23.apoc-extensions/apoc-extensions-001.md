# What is APOC and When to Extend Beyond Cypher

**Cypher** is the primary language for querying and updating a **property graph** in Neo4j: nodes, relationships, labels, relationship types, and properties. Common tasks such as pattern matching, property filtering, aggregations, path finding, or graph updates usually have direct solutions in Cypher. However, real-world systems also encounter requirements like JSON processing, string normalization, graph traversal with specialized rules, data integration, or administrative tasks. **APOC** is an extension library of functions and procedures that helps address many of those needs directly from a query.

This lesson belongs to the **APOC and Extensions** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. The goal is not to use APOC for every operation: you need to know **what Cypher already does**, **what capabilities APOC adds**, which version/components are available, and the trade-offs in operations, security, and performance. The examples connect to data import, relationship/path queries, indexes, the Java Driver, and Spring Data Neo4j; features must always be verified against the running **Neo4j version, APOC version, and Cypher language version**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain what APOC is and distinguish between a **function** and a **procedure**.
2. Distinguish between **APOC Core** and **APOC Extended**; recognize deployment and version constraints.
3. Choose between **plain Cypher**, **APOC**, and **external processing outside Neo4j** for a given requirement.
4. Use small examples such as `apoc.text.clean`, `apoc.convert.fromJsonMap`, and `apoc.path.expandConfig`.
5. Check which procedures/functions are allowed, and state the risks of loading data from URLs, accessing files, and running dynamic statements.
6. Evaluate performance impact, maintainability, and alternatives in newer Cypher versions.

## 2. What is APOC?

APOC is an acronym commonly expanded as **Awesome Procedures On Cypher**. It is an extension library providing **user-defined procedures** and **user-defined functions** implemented in Java, to be called from Cypher. Neo4j provides the mechanism to invoke such capabilities, while APOC packages ready-made functionality so users do not have to write Java plugins from scratch.

~~~text
        Java Application / Spring Data Neo4j / Neo4j Browser
                            |
                            v
                      Cypher Query
                   /               \
      MATCH, WHERE, MERGE       Call Extensions
      WITH, RETURN, CALL {}     apoc.* function/procedure
                   \               /
                    \             /
                        Neo4j
                Node --Relationship--> Node
~~~

APOC is **not** a separate database, **does not replace** Cypher, and is **not** Graph Data Science (GDS). A single query can combine standard Cypher with APOC functions or procedures, but compatibility depends on installed components and account privileges.

### How do functions and procedures differ?

| Concept | Common Usage | Example | Characteristics |
|---|---|---|---|
| **Function** | Inside expressions in `RETURN`, `WITH`, `WHERE`, ... | `apoc.text.clean('Hello World!')` | Takes arguments, returns **a single value** usable in an expression |
| **Procedure** | `CALL ... YIELD ...` | `CALL apoc.path.expandConfig(...) YIELD path` | Can return a **stream of rows**; some procedures perform reads, writes, or external operations |

Example of a function that only processes a string without modifying the graph:

~~~cypher
RETURN apoc.text.clean('Hello World!') AS normalized;
// Expected: "helloworld"
~~~

Example of a path-traversal procedure that can produce **multiple `path` rows**:

~~~cypher
MATCH (start:Person {personId: $personId})
CALL apoc.path.expandConfig(start, {
    relationshipFilter: 'FOLLOWS>',
    minLevel: 1,
    maxLevel: 2
})
YIELD path
RETURN path;
~~~

Do not use a function name as a procedure, or invoke a procedure using expression syntax. Read/write procedures also have their own execution permissions and transaction impacts that must be checked.

## 3. APOC Core and APOC Extended

Since Neo4j 5, APOC has been split into two libraries:

| Component | Key Characteristics | When to Pay Attention |
|---|---|---|
| **APOC Core** | Commonly used functionality, officially supported by Neo4j | Data processing, utility functions, certain path queries, and in-graph tasks |
| **APOC Extended** | Additional community-maintained extensions, including features relying on external libraries or serving specialized scenarios | When a needed procedure **is not in Core** and the environment allows installing extras |

There is no single **APOC Full** package for Neo4j 5 like in older versions. **Extended does not replace Core**; if you need functions from both, a self-hosted environment may require installing both compatible artifacts.

**Do not infer availability solely from the `apoc.*` name.** A function name does not guarantee whether it belongs to Core or Extended, whether it is loaded on the server, whether it is available in Neo4j Aura, or whether it is restricted by user permissions. Always look up the corresponding procedure/function in the documentation for the **exact version**.

### Why do versions matter so much?

- APOC ties into Neo4j's APIs, so you must use a release **compatible** with the running Neo4j version; looking only at major version `5` is not enough to guarantee compatibility across all releases.
- Starting with Neo4j **2025.06**, there are two language versions to distinguish: **Cypher 5** and **Cypher 25**. Deprecated or replaced APOC features may depend on the Cypher version.
- In Neo4j **2026.02+**, Cypher 25 is the default for databases of the corresponding release generation. If legacy documentation or code relies on Cypher 5 behavior, check specific support and version-selection syntax.
- Newer APOC releases continue migrating overlapping functionality into **plain Cypher**. Do not build new projects around an APOC procedure that already has a Cypher equivalent and is deprecated.

Because versions are released frequently, **do not copy installation rules from an old blog post while ignoring the compatibility matrix in the official documentation**.

## 4. Common Requirement Categories That Prompt Considering APOC

| Requirement | What Plain Cypher Already Has | What APOC Can Add | Initial Decision |
|---|---|---|---|
| Pattern querying on nodes/relationships | `MATCH`, `WHERE`, `OPTIONAL MATCH`, subqueries | Specialized traversal utilities | **Prefer Cypher** when the pattern is clear |
| Filtering, aggregation, sorting | `WITH`, `count`, `sum`, `ORDER BY` | Collection and data helper functions | Use Cypher if sufficient and easy to optimize |
| String normalization | `trim`, `toLower`, `replace`, and supported string expressions | More utility operations, e.g., `apoc.text.clean` | Compare semantics before choosing |
| Converting JSON to Cypher structures | Application input handling, map/list parameters | `apoc.convert.fromJsonMap` | Useful when JSON appears as a **string** inside Cypher |
| Complex rule-based graph traversal | Path patterns, quantified path patterns, filters | `apoc.path.expandConfig` with filters, uniqueness, limits | Consider APOC if Cypher is hard to express or maintain |
| Data import/export | `LOAD CSV`, Java Driver, import tools | Procedures to load JSON, export data, integrate | Check network/file permissions, data volume, and schema |
| Bulk updates | `CALL { ... } IN TRANSACTIONS` and version-dependent concurrency | `apoc.periodic.iterate` in legacy systems | **Prefer newer Cypher features** if equivalent |
| Specialized graph algorithms | Path queries and aggregations in Cypher | A few graph utilities | Check **Graph Data Science** when dedicated analytical algorithms are needed |
| Displaying temporary structures | Returning nodes, relationships, maps/paths | Functions creating virtual entities for display | Use only when the consuming tool supports them |

The existence of an APOC procedure **does not prove** that it is faster than Cypher. It helps **express operations that are difficult or missing natively** in a specific environment.

## 5. Example 1 — String Normalization and Recognizing Limitations

Suppose an application imports data from multiple sources with inconsistent names. The following function strips non-alphanumeric characters and converts to lowercase:

~~~cypher
RETURN apoc.text.clean('Hello___World!') AS cleaned;
// cleaned = "helloworld"
~~~

A **different**, though not completely equivalent, approach in plain Cypher:

~~~cypher
WITH '  Hello___World!  ' AS raw
RETURN toLower(trim(raw)) AS cleaned;
// cleaned = "hello___world!"
~~~

This comparison shows why you must define the exact **normalization rule**: `trim` only removes leading/trailing whitespace, and `toLower` converts to lowercase; `apoc.text.clean` also removes non-alphanumeric characters. They cannot be substituted for one another mechanically.

**Note on Vietnamese data:** before applying a "clean" function, test it against diacritics, Unicode, spaces, hyphens, and search requirements. Normalization for building a **lookup key** may differ from the policy for storing a **display name**. Do not overwrite original data without evaluating these differences.

**When to use APOC:** when you need a specific normalization rule, the corresponding function has been verified on real data, and compatibility is acceptable. If the task involves intensive text processing, it may be more appropriate to process it in the Java service and pass the normalized property into Neo4j.

## 6. Example 2 — Converting a JSON String to a Cypher Map

Java Driver applications can usually pass `Map`/`List` parameters directly. However, in legacy data, a property sometimes holds a **JSON string**:

~~~text
{"orderId":"O-7","total":125000,"customer":{"id":"C-2"}}
~~~

`apoc.convert.fromJsonMap` can parse a JSON object into a Cypher map:

~~~cypher
WITH apoc.convert.fromJsonMap(
    '{"orderId":"O-7","total":125000,"customer":{"id":"C-2"}}'
) AS doc
RETURN doc.orderId AS orderId,
       doc.total AS total,
       doc.customer.id AS customerId;
~~~

Expected result:

| orderId | total | customerId |
|---|---:|---|
| O-7 | 125000 | C-2 |

In this example, `fromJsonMap` only **converts data values**; it does not create nodes or relationships. You still need `MERGE`/`CREATE` and key checks if you decide to write to the graph. Do not blindly call JSON conversion on huge numbers of rows; measure the cost and consider parsing in the application when data arrives from HTTP/APIs.

**Distinguish** `apoc.convert.fromJsonMap` from `apoc.load.json`: the former takes an **existing JSON string**, whereas the load procedure can read from permitted URLs/file sources. Data-loading procedures bring configuration, network control, and access-permission requirements.

## 7. Example 3 — Path Traversal with Configuration Rules

Cypher already offers several ways to describe paths. APOC is useful when traversal requirements combine **relationship-type filters, direction, hop limits, and node/relationship uniqueness strategies** in a single configuration.

Create a sample graph in a **dedicated practice database**. The following `MERGE` statements can be re-run without creating duplicate node/relationship patterns when initial data is consistent:

~~~cypher
CREATE CONSTRAINT demo_person_id IF NOT EXISTS
FOR (p:DemoPerson)
REQUIRE p.personId IS UNIQUE;
~~~

~~~cypher
MERGE (a:DemoPerson {personId: 'A'})
MERGE (b:DemoPerson {personId: 'B'})
MERGE (c:DemoPerson {personId: 'C'})
MERGE (d:DemoPerson {personId: 'D'})
MERGE (a)-[:FOLLOWS]->(b)
MERGE (a)-[:FOLLOWS]->(d)
MERGE (b)-[:FOLLOWS]->(c)
MERGE (c)-[:FOLLOWS]->(a);
~~~

The graph contains a cycle `A → B → C → A`. Query from `A` following outgoing `FOLLOWS` relationships, from 1 to 2 hops:

~~~cypher
MATCH (a:DemoPerson {personId: 'A'})
CALL apoc.path.expandConfig(a, {
    relationshipFilter: 'FOLLOWS>',
    minLevel: 1,
    maxLevel: 2,
    uniqueness: 'NODE_PATH',
    bfs: true,
    limit: 20
})
YIELD path
RETURN [n IN nodes(path) | n.personId] AS route,
       length(path) AS hops
ORDER BY hops;
~~~

On the sample graph (containing only the edges created above), the expected paths include `A → B`, `A → D`, and `A → B → C`. `NODE_PATH` guarantees **not repeating a node within the same path**, yet it can still return multiple distinct paths leading to the same node in a more complex graph. If business logic requires each node to be visited only once **across the entire traversal**, investigate `NODE_GLOBAL` and its effect on returned paths.

| Parameter | Meaning |
|---|---|
| `relationshipFilter: 'FOLLOWS>'` | Follow only outgoing `FOLLOWS` relationships |
| `minLevel`, `maxLevel` | Minimum and maximum number of relationships along a path |
| `uniqueness: 'NODE_PATH'` | Prevent repeating a node **within each path** |
| `bfs: true` | Breadth-first search |
| `limit: 20` | Limit the number of returned paths; **does not mean** an absolute cap on all traversal work |

**Note:** changing configuration can alter the **result set**, not just speed. For example, `NODE_GLOBAL` and `NODE_PATH` differ in semantics; do not swap them merely to "improve performance" without checking business requirements. On graphs with high branching, always specify hop limits and measure the number of expanded paths/nodes. APOC documentation also notes that `apoc.path.expandConfig` is not supported in the **parallel runtime** due to multi-threaded safety characteristics.

## 8. Example 4 — Batch Update Jobs: APOC or Cypher?

Some legacy systems use `apoc.periodic.iterate` to select rows with a first Cypher statement and update them in batches with a second Cypher statement:

~~~cypher
// Maintenance example on a practice database; has a WRITE effect.
CALL apoc.periodic.iterate(
    'MATCH (p:DemoPerson) RETURN p',
    'SET p.isActive = true',
    {batchSize: 1000, parallel: false}
)
YIELD batches, total, failedBatches
RETURN batches, total, failedBatches;
~~~

Depending on record count, the procedure splits work into batches and returns statistics. **Do not assume** `total` is always the number of **new** nodes or nodes whose **values changed**: in this example it is the number of source rows processed by the procedure.

However, **do not treat APOC as the default choice for new code**:

- Neo4j already supports `CALL { ... } IN TRANSACTIONS` for batched update queries (syntax depends on version; must run in an **implicit transaction**).
- In **Neo4j 2026.04 and Cypher 25**, `apoc.periodic.iterate` is marked **deprecated**; documentation points toward `CALL { ... } IN CONCURRENT TRANSACTIONS` when concurrent transaction processing is needed.
- Cypher queries passed as **strings** to procedures like `apoc.periodic.iterate` must be constructed carefully: never concatenate untrusted input directly into Cypher strings.
- Any batching approach requires designing for **idempotency**, error handling, commit monitoring, and batch sizing before running against critical data.

Thus, the main value of APOC here may be **maintaining legacy systems** or using procedure options not yet suitably replaced in a particular Neo4j version; when your environment already has equivalent Cypher syntax, prefer trying plain Cypher first.

## 9. Checking Whether APOC Is Installed and Permitted

Documentation alone is not sufficient proof that APOC is available on the server. Verify **on the actual database using the actual account**:

~~~cypher
SHOW PROCEDURES
YIELD name, signature
WHERE name STARTS WITH 'apoc.'
RETURN name, signature
ORDER BY name
LIMIT 30;
~~~

~~~cypher
SHOW FUNCTIONS
YIELD name, signature
WHERE name STARTS WITH 'apoc.'
RETURN name, signature
ORDER BY name
LIMIT 30;
~~~

In environments with privilege management, you can check which procedures the current account can execute:

~~~cypher
SHOW PROCEDURES EXECUTABLE BY CURRENT USER
YIELD name
WHERE name STARTS WITH 'apoc.'
RETURN name
ORDER BY name;
~~~

The lists of procedures and functions may differ. When calling `CALL apoc.path.expandConfig(...)` fails with a "procedure not found" message, check:

1. Are the name and syntax of the **procedure/function** accurate for the version's documentation?
2. Has Neo4j loaded the **right APOC Core or Extended** version?
3. Do execution privileges, the allowlist, and security restrictions permit calling the procedure?
4. Is the account connected to the **right DBMS** and targeting the right database?
5. Has the feature been deprecated/removed in **Cypher 25** or the currently installed release?

A missing procedure on the server and missing execution privileges are **two different causes**; do not grant higher privileges to an application just to test a statement.

## 10. Installation and Secure Configuration Principles

### 10.1. Installing the right components

In **self-hosted** environments, APOC Core may be bundled in the `labs` directory of the Neo4j distribution. The typical process is placing the compatible JAR into `plugins` and **restarting** Neo4j; enabling it via Neo4j Desktop or Docker depends on the deployment method. APOC Extended requires the matching release package and may have additional dependencies. Before deploying, read the installation guide for the **exact release**.

In **Neo4j Aura**, APOC Core is available within the platform's supported scope, but users cannot install arbitrary Extended JARs. Therefore, a solution that relies on Extended locally may **not port directly to Aura**.

### 10.2. Separating Neo4j configuration from APOC configuration

In Neo4j 5 and later, options prefixed with `apoc.*` belong in `apoc.conf` (in the same configuration directory as `neo4j.conf`) or corresponding environment variables; do not keep putting `apoc.*` keys in `neo4j.conf` as older guides did. Options controlling procedure loading and privileges belong in Neo4j security configuration, such as `dbms.security.procedures.allowlist` or `dbms.security.procedures.unrestricted`, depending on version support.

Example configuration showing **restrictive defaults for file access**:

~~~properties
# apoc.conf: conservative illustrative values
apoc.import.file.enabled=false
apoc.export.file.enabled=false
~~~

Do not enable read/write across the entire filesystem just to run an example. If real file reading is required, permitted access locations must be restricted to the proper directory and OS permissions of the Neo4j service account. Separate **local file**, **HTTPS URL**, and **in-memory JSON string** data sources: each carries distinct risks and permission mechanisms.

### 10.3. Least privilege and URL access principles

Some procedures can read/write files, call URLs, or execute dynamic Cypher. These capabilities can affect **data security, server resources, and internal networks**. When using URL-loading procedures such as `apoc.load.json`:

- Allow only necessary data sources; consider blocking internal network addresses to prevent **SSRF** (server-side request forgery).
- Do not pass user-supplied URLs, filenames, or Cypher strings into sensitive procedures without validation rules and limits.
- Use allowlists and granular execution privileges; unrestrict only procedures that truly require it.
- Protect credentials at the configuration/secret-management layer; avoid putting tokens directly into logged queries.
- Limit payload sizes, timeouts, and request counts; treat external data as **untrusted**.

Being "callable" does not equate to being "safe to expose in production."

## 11. Comparing Approaches: Cypher, APOC, or Java?

Consider a practical scenario: a Spring Data Neo4j application receives a list of orders from a REST API as JSON, wants to normalize customer names, attach `PLACED` relationships, and compute total amounts.

**Cypher + Java Application Approach**

1. The application calls the API, validates the response, and parses JSON into DTOs/Maps.
2. The application normalizes currency types, customer identifiers, and business fields.
3. The Java Driver or Spring Data Neo4j passes parameters into Cypher, using `UNWIND` + `MERGE` with appropriate constraints.
4. Revenue totals are aggregated via `sum` or queries with subqueries when needed.

This approach usually provides a clear control boundary between external data and the database; testing transformation logic in Java is also straightforward.

**APOC-Assisted Approach**

If the JSON source is already stored inside a property as a **string**, `apoc.convert.fromJsonMap` helps parse it right inside Cypher. If business logic requires traversing with complex label filters and uniqueness rules, `apoc.path.expandConfig` can reduce the number of hand-written query branches. When operations depend on Core/Extended, ensure the deployment environment supports those features.

| Criterion | Plain Cypher | APOC | Java / Application Service |
|---|---|---|---|
| Relationship queries and aggregations | Primary choice, understood directly by the planner | Adds specialized operations | Can orchestrate, though avoid pulling excessive data to the app |
| External JSON/API processing | Accepts map/list parameters; not a general-purpose ETL tool | Has parsing functions and data-loading procedures | Flexible for validation, retries, schemas, and integration security |
| Rule-based path traversal | Depends on Cypher version capabilities | Provides detailed traversal configuration | Often harder if a large graph must be pulled to the client |
| Operations and upgrades | Few extra dependencies | Must track versions, Core/Extended, and privileges | Has separate application and infrastructure dependencies |
| External data access control | Based on roles and deployment setup | Watch out for network/file access procedures | Can manage tokens, URL allowlists, and rate limits at the service layer |

No single option wins in every scenario. **Choose the approach based on where data should be processed, correctness, version support, and operational cost**, and only then optimize performance.

## 12. Performance and Verification

APOC runs inside Neo4j, but that does not mean every procedure is always faster than a plain Cypher solution. Some APOC operations are a "black box" to the planner: the Cypher optimizer cannot inspect logic inside a procedure the way it analyzes pure Cypher expressions and patterns.

When comparing two approaches:

1. **Ensure identical business results.** A traversal using `NODE_GLOBAL` may yield different results from one using `NODE_PATH`; never compare speed while ignoring this difference.
2. **Keep the same data and parameters** across runs; avoid changing both schema/indexes and the query at the same time.
3. Use `EXPLAIN` and `PROFILE` on the Cypher portions to inspect the plan, `Rows`, and `DB Hits`. Operator statistics outside a procedure may not reveal every internal step occurring inside APOC.
4. Measure latency across multiple runs after comparable warm-up; monitor memory, returned row counts, and resource usage during large traversals/ETL jobs.
5. For procedures with **write side effects**, run `PROFILE` only on a test database: `PROFILE` **executes** the query and can mutate real data.
6. Verify compatibility when upgrading Neo4j/APOC/Cypher, especially for deprecated functions and procedures.

Example of tracing the initial node lookup followed by path expansion:

~~~cypher
PROFILE
MATCH (a:DemoPerson {personId: 'A'})
CALL apoc.path.expandConfig(a, {
    relationshipFilter: 'FOLLOWS>',
    minLevel: 1,
    maxLevel: 2,
    uniqueness: 'NODE_PATH'
})
YIELD path
RETURN length(path) AS hops, count(*) AS paths
ORDER BY hops;
~~~

The `:DemoPerson(personId)` constraint enables the `MATCH` step that locates the start node to use an index. Traversal cost can still be high if the node has many relationships; check `maxLevel`, `relationshipFilter`, and the number of paths returned. Do not equate **fast start-node lookup** with **an optimized overall graph traversal**.

## 13. Common Errors and Pitfalls

| Symptom | Possible Cause | How to Check and Resolve |
|---|---|---|
| `Unknown function 'apoc....'` | Missing Core/Extended, wrong name, or incompatible version | `SHOW FUNCTIONS`; check documentation for the exact version |
| `There is no procedure with the name ...` | Procedure not loaded or restricted | `SHOW PROCEDURES`, plugins, allowlist, and privileges |
| Works locally but fails on Aura | Different plugin installation/permission capabilities | Check the list of APOC features supported by Aura |
| File import denied | `apoc.import.file.enabled` restricted by default or invalid path | Check `apoc.conf`, import directory, and OS permissions |
| Graph traversal too slow, too many paths | Unbounded `maxLevel`, high branching factor | Reduce hops, filter direction/type/label, measure path count |
| Traversal result differs from Cypher query | Different `uniqueness` and filter semantics | Compare concrete paths on a small graph, pick the right rule |
| Old function deprecated or removed | Upgraded Neo4j/Cypher/APOC | Check migration guide, prefer Cypher equivalent |
| JSON processing produces wrong property types | JSON, map, and property types do not align 1:1 | Normalize numbers/dates/IDs, validate schema before `SET`/`MERGE` |
| Batch update job writes unexpected counts | Rollbacks, retries, duplicates, or wrong transaction boundaries | Monitor commits, check idempotency, compare source/target counts |

## 14. Practice Exercises

### Exercise 1 — When is APOC not needed yet?

You need to retrieve all products with `price >= 100000`, sorted by ascending price, returning at most 20 rows. Should you use APOC because the project already has Core installed?

<details>
<summary>Suggested Answer</summary>

Not needed yet. `MATCH (p:Product) WHERE p.price >= 100000 RETURN p ORDER BY p.price LIMIT 20` already solves the problem in Cypher. Design an appropriate index and inspect `EXPLAIN`/`PROFILE` if optimization is required; APOC offers no clear extension benefit here.

</details>

### Exercise 2 — Explaining function output

Compare:

~~~cypher
RETURN apoc.text.clean('Hello___World!') AS apocValue,
       toLower(trim('Hello___World!')) AS cypherValue;
~~~

Why do the two values differ? When should you avoid using `apoc.text.clean` for a person's name?

<details>
<summary>Suggested Answer</summary>

APOC strips non-alphanumeric characters and lowercases, returning `helloworld`; `trim` does not remove underscores, so the Cypher expression returns `hello___world!`. For display names, stripping diacritics or characters can lose information; distinguish between the original display property and a normalized lookup key.

</details>

### Exercise 3 — Designing a traversal

A graph has `FOLLOWS` relationships with many cycles. You want to retrieve paths starting from node `A`, up to 3 hops, avoiding repeated nodes **within each path**. Write a query using `apoc.path.expandConfig`. If you replace `NODE_PATH` with `NODE_GLOBAL`, what needs to be re-checked?

<details>
<summary>Suggested Answer</summary>

~~~cypher
MATCH (a:DemoPerson {personId: 'A'})
CALL apoc.path.expandConfig(a, {
    relationshipFilter: 'FOLLOWS>',
    minLevel: 1,
    maxLevel: 3,
    uniqueness: 'NODE_PATH'
})
YIELD path
RETURN path;
~~~

`NODE_PATH` prevents node repetition within each individual path. `NODE_GLOBAL` restricts node visits across the entire traversal, which can change which paths are returned; verify the output against business requirements before choosing it.

</details>

### Exercise 4 — Choosing the right tool

A Java service receives JSON from an external API, saves `Order` nodes into Neo4j, and periodically needs to update millions of records. Propose where to parse JSON, how to run batch updates, and cases where APOC would genuinely be needed.

<details>
<summary>Suggested Answer</summary>

You can parse/validate JSON in Java and pass `Map`/`List` as parameters, using Cypher `UNWIND` and `MERGE` with constraints to write. For large datasets, use batched transactions or `CALL { ... } IN TRANSACTIONS` as supported by your version. Use APOC only if there is a specific requirement—such as data already stored as JSON strings needing in-Cypher parsing, specialized traversal configuration, or maintaining a legacy APOC pipeline. For newer Cypher 25 environments, check the deprecation status of `apoc.periodic.iterate`.

</details>

## 15. Official Documentation for Version Verification

- [Neo4j APOC Core — Introduction and Support Scope](https://neo4j.com/docs/apoc/current/introduction/)
- [Installing APOC Core](https://neo4j.com/docs/apoc/current/installation/) and [APOC Extended](https://neo4j.com/labs/apoc/5/installation/)
- [APOC and Cypher Versions](https://neo4j.com/docs/apoc/current/apoc-and-cypher/cypher-versions/)
- [Migrating APOC Functionality to Plain Cypher](https://neo4j.com/docs/apoc/current/apoc-and-cypher/cypher-migration/)
- [APOC Core Functions/Procedures Overview](https://neo4j.com/docs/apoc/current/overview/)
- [APOC Configuration](https://neo4j.com/docs/apoc/current/config/)

The `current` pages change across releases. When learning or deploying, select the exact version on the documentation site and verify which features are loaded on your server.

## 16. Key Takeaways

- **APOC is a library of functions and procedures extending Cypher**, not a replacement language or database for Neo4j.
- **Plain Cypher is the first choice** for read/write patterns and aggregations that it already expresses clearly; APOC adds value when solving genuine additional needs.
- **Core and Extended have different scopes, support levels, and deployment methods**. Always check versions, privileges, and environment constraints (especially Aura).
- **APOC evolves alongside Cypher**: many features have equivalents in Cypher 25 and some are deprecated; check the migration guide when writing new code.
- **Correctness, least privilege, operational manageability, and measured benchmarks** matter more than whether a query happens to use APOC.
