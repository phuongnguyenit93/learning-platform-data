# Calling Procedures and Functions and Reading Input–Output Signatures in Neo4j APOC

## 1. Context and Objectives

Neo4j models data as a **property graph**, consisting of nodes, relationships, and properties; Cypher uses `MATCH`, `WHERE`, `RETURN`, and expressions to query relationships or paths. When additional capabilities are needed—such as list or string processing, configured path expansion, or batched data ingestion—the Neo4j ecosystem provides **procedures** and **functions**. The **APOC** (Awesome Procedures on Cypher) extension library supplies many utilities of this kind.

In the **APOC and Extensions** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module, this lesson focuses on **how to invoke them** and **how to read input–output signatures**, rather than trying to memorize hundreds of utility names. These skills apply to built-in procedures/functions, APOC, and custom organization-developed extensions.

After this lesson, you will be able to:

1. Distinguish procedures from functions and choose the proper syntax: `CALL ... YIELD` versus an inline expression call.
2. Use `SHOW PROCEDURES` and `SHOW FUNCTIONS` to inspect names, signatures, descriptions, access modes, and availability.
3. Read required parameters, configuration parameters, data types, output columns, and `null` handling.
4. Combine procedure outputs with `WITH`, `WHERE`, `RETURN`, and node/relationship/path patterns.
5. Diagnose missing-plugin errors, missing privileges, argument type mismatches, invalid `YIELD` column names, and version differences.

> **Prerequisites:** You know nodes, relationships, and how to run Cypher. APOC examples run only when the corresponding procedure/function **is registered and permitted** in your Neo4j version. Do not assume every Neo4j installation or every Aura tier includes the exact same APOC catalog.

## 2. How Do Procedures and Functions Differ?

| Aspect | Procedure | Function |
| --- | --- | --- |
| Role | Performs an operation, can produce **result rows**, and—for write procedures—can mutate the graph | Computes and returns **a single value** inside an expression |
| Common Invocation | `CALL procedureName(arg1, arg2) YIELD column` | `functionName(arg1, arg2)` inside `RETURN`, `WITH`, `WHERE`, or `SET` as appropriate |
| Inputs | Argument list matching the signature | Argument list matching the signature |
| Outputs | Zero to many rows; each row holds output columns declared in the signature | One value of the return type, which may be a list/map/node/path depending on the function |
| Authorization | May require execute procedure privilege and corresponding graph read/write privileges | May require execute function privilege |
| Built-in Example | `db.labels()` | `size()`, `coalesce()` |
| APOC Example | `apoc.path.expandConfig()` | `apoc.text.join()`, `apoc.coll.toSet()` |

Example using **built-in functions**:

```cypher
RETURN
  size(['A', 'B', 'C']) AS itemCount,
  coalesce(null, 'unknown') AS fallback;
```

Here `size(...)` and `coalesce(...)` appear **inside expressions** after `RETURN`, returning a number and a string respectively. You do not write `CALL size(...) YIELD ...`.

Example using a **built-in procedure**:

```cypher
CALL db.labels() YIELD label
RETURN label
ORDER BY label;
```

`db.labels()` yields rows containing the `label` column, listing node label names present in the database that the command is permitted to view. In a brand-new database, it may return zero rows. We use `YIELD` to extract the column and then continue processing it as Cypher data.

**Further distinction:** `CALL (x) { ... }` or `CALL { ... }` is also called a *subquery*; that is **not** a call to a named procedure. Similarly, `CALL { ... } IN TRANSACTIONS` is Cypher's transaction-batching syntax, distinct from the `apoc.periodic.iterate` procedure.

## 3. Finding Existing Features Instead of Guessing Names

APOC and extensions are released across many versions. A feature appearing in an online article might have changed its signature, been replaced, or be unavailable on your system. Therefore, **the connected database is the first place to check signatures**.

### 3.1. Listing procedures and signatures

```cypher
SHOW PROCEDURES
YIELD name, signature, description, mode
RETURN name, signature, description, mode
ORDER BY name
LIMIT 30;
```

Field meanings:

- `name`: callable name, such as `db.labels` or `apoc.path.expandConfig`.
- `signature`: describes input parameters, input types, and output columns.
- `description`: purpose, and may indicate limitations or notes about the procedure.
- `mode`: system-declared execution mode; typically distinguishes read-only procedures from write-capable procedures.

Viewing only APOC procedures:

```cypher
SHOW PROCEDURES
YIELD name, signature, description, mode
WHERE name STARTS WITH 'apoc.'
RETURN name, signature, mode, description
ORDER BY name;
```

Finding one specific procedure:

```cypher
SHOW PROCEDURES
YIELD name, signature, description
WHERE name = 'apoc.path.expandConfig'
RETURN name, signature, description;
```

If the query returns **0 rows**, that alone does not prove APOC does not exist: the feature may not be installed, may not be registered in the running release, or the account may lack visibility/execute permissions. See the troubleshooting section for details.

### 3.2. Listing functions and signatures

```cypher
SHOW FUNCTIONS
YIELD name, signature, description
WHERE name STARTS WITH 'apoc.'
RETURN name, signature, description
ORDER BY name;
```

Finding a specific function:

```cypher
SHOW FUNCTIONS
YIELD name, signature, description
WHERE name = 'apoc.text.join'
RETURN name, signature, description;
```

`SHOW FUNCTIONS` can list both built-in and extension functions, depending on options and system permissions. Do not look for `apoc.text.join` in the procedure list: it is a **function**. Conversely, `apoc.path.expandConfig` is a **procedure**, not a function you can put after `RETURN` as a value.

> **Read signatures for the exact version:** If `SHOW` output differs from documentation examples, trust the signature reported by your system and check the docs for that matching version. Some column names or visibility permissions in `SHOW` can vary across Neo4j versions.

## 4. How to Read a Signature

Conceptually, a signature can be expressed as:

```text
procedureName(arg1 :: TYPE_A, arg2 :: TYPE_B)
    :: (output1 :: OUTPUT_A, output2 :: OUTPUT_B)

functionName(arg1 :: TYPE_A, arg2 :: TYPE_B)
    :: RETURN_TYPE
```

The signatures in the block above are a **conceptual reading guide**, not the definition of a real Neo4j utility.

| Part | How to Read It |
| --- | --- |
| Name before `(` | Callable procedure/function name; match the exact namespace |
| `arg1`, `arg2` | Positional input arguments; pass expressions of matching types |
| `:: TYPE` | Data type required or returned by the signature |
| `MAP` | Map-typed argument, commonly used for configuration |
| `LIST<STRING>` | List of string values |
| `NODE`, `RELATIONSHIP`, `PATH` | Neo4j property graph data types |
| `(output1 :: ..., output2 :: ...)` | Procedure output columns; selected via `YIELD` |
| Return type after `::` for a function | A single value, used in expressions like `RETURN functionName(...) AS alias` |

Arguments may have **default values** or notation indicating optionality; exact formatting depends on the published signature. Do not assume that a "`MAP` argument" can be omitted: if the argument is required, you must still pass a value such as `{}` or a valid config map per the docs.

Example of **interpreting** a simple signature (illustrative, not a verbatim `SHOW` output):

```text
demo.words(texts :: LIST<STRING>, separator :: STRING) :: STRING
```

From this we deduce:

1. Two arguments must be passed in order: a list of strings and a separator string.
2. `LIST<STRING>` is not `STRING`; passing `'A,B'` instead of `['A','B']` may trigger a type error.
3. The output is a string; if this is a function, use it in a `RETURN` expression rather than `YIELD`.

### 4.1. Procedure signature versus actual call

Illustrative example of a procedure returning a `path` column:

```text
... :: (path :: PATH)
```

The call can be written as:

```cypher
MATCH (start:ApocDemoPerson {id: $startId})
CALL apoc.path.expandConfig(start, $config)
YIELD path
RETURN path;
```

Above, `$startId` is an **identifier** passed from the application, `MATCH` retrieves the node from the graph, and then the `NODE`-typed variable `start` is passed into the procedure. `$config` must be a properly formatted map and the procedure must be permitted. This avoids confusing an ID string with an argument expecting a node.

The signature tells you **column names and types**, while the description/configuration docs explain the meaning, valid values, and defaults of each config key. You cannot fully understand `relationshipFilter` or `uniqueness` simply by seeing the type `MAP`.

### 4.2. Nulls, lists, maps, and property graph types

Cypher distinguishes `null` from an empty list `[]` and an empty map `{}`. A procedure or function may accept, reject, or interpret each of these differently.

- `null`: missing or unknown value; check the function's specific rules.
- `[]`: list with 0 elements, not a missing value.
- `{}`: map with 0 keys; does **not automatically** supply required configuration keys.
- `NODE`: a graph node, not a node's string ID.
- `PATH`: a path consisting of nodes and relationships, further inspectable via `nodes(p)`, `relationships(p)`, `length(p)`.

Example:

```cypher
WITH ['A', 'B'] AS labels
RETURN size(labels) AS numberOfItems,
       labels[0] AS firstItem;
```

Here an expression consumes a list, not two separate arguments. For a procedure expecting two arguments, pass `procedureName(arg1, arg2)` per its signature; passing a single two-element list is **not equivalent** unless the signature explicitly declares a list input.

## 5. Calling APOC Functions in Cypher Expressions

APOC offers utilities for strings, lists, maps, conversions, and many other categories. A common **APOC Core** example is `apoc.text.join`:

```cypher
RETURN apoc.text.join(
  ['Neo4j', 'Cypher', 'APOC'],
  ' / '
) AS joinedText;
```

When the function is available, the result is:

```text
joinedText
-------------------
Neo4j / Cypher / APOC
```

From the call, the first argument is a **list of strings**, the second is a **separator string**, and the output is aliased with `AS joinedText`. No `CALL` and no `YIELD` are needed.

Another function example, deduplicating values according to the utility's semantics:

```cypher
RETURN apoc.coll.toSet(['graph', 'cypher', 'graph']) AS terms;
```

The resulting list contains distinct values `graph` and `cypher`. **Do not rely on display order** from a set-semantics operation unless business logic does not require order; if deterministic order is needed, add an explicit sorting step.

### 5.1. Using functions with node data

Suppose `:Article` nodes have a list property `tags`:

```cypher
MATCH (a:Article)
WHERE a.tags IS NOT NULL
RETURN a.id AS articleId,
       apoc.text.join(a.tags, ', ') AS tagText
ORDER BY articleId
LIMIT 20;
```

This assumes `a.tags` is a **list of strings**; if writers stored mixed types, normalize them first. The query is read-only: the function returns a value per row and does not create relationships or mutate properties.

### 5.2. When APOC is unnecessary

Not every task should depend on an extension. For basic operations such as `size`, `coalesce`, `toString`, `collect`, or `range`, Cypher already provides built-in functions. Choosing built-in functions when they meet the need helps reduce plugin coupling, deployment privileges, and upgrade friction.

Before using an APOC function in an application:

1. Verify it appears in `SHOW FUNCTIONS`.
2. Read its signature and test with small inputs, including `null`, empty lists, and wrong types.
3. Evaluate cost if invoked across millions of rows; a function in `RETURN` can execute **once per input row**.

## 6. Calling APOC Procedures, Extracting Columns with YIELD, and Chaining in Cypher

A clear example is `apoc.path.expandConfig`: a procedure that expands paths from a start node according to options in a configuration map.

### 6.1. Sample data

Run in a practice database:

```cypher
CREATE CONSTRAINT apoc_demo_person_id IF NOT EXISTS
FOR (p:ApocDemoPerson) REQUIRE p.id IS UNIQUE;
```

```cypher
MERGE (a:ApocDemoPerson {id: 'APOC-U1'})
MERGE (b:ApocDemoPerson {id: 'APOC-U2'})
MERGE (c:ApocDemoPerson {id: 'APOC-U3'})
MERGE (a)-[:APOC_DEMO_FOLLOWS]->(b)
MERGE (b)-[:APOC_DEMO_FOLLOWS]->(c);
```

The demo nodes use distinct IDs to avoid interfering with other practice data. `MERGE` reduces duplicates when re-running the exact sample, though in shared environments you should still inspect pre-existing relationships. Creating a constraint is a schema write operation; run it separately before ingesting data.

### 6.2. Inspecting the signature before calling

```cypher
SHOW PROCEDURES
YIELD name, signature, description, mode
WHERE name = 'apoc.path.expandConfig'
RETURN name, signature, description, mode;
```

If the procedure is present, the signature shows the input arguments and the returned `path` column. The `config` parameter is typically a `MAP`, with keys like `relationshipFilter`, `minLevel`, `maxLevel`, and `uniqueness`. Each key's meaning must be read from the dedicated documentation, not inferred from the type name alone.

### 6.3. Invoking the procedure

```cypher
MATCH (start:ApocDemoPerson {id: 'APOC-U1'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  minLevel: 1,
  maxLevel: 2,
  uniqueness: 'NODE_PATH'
})
YIELD path
RETURN [n IN nodes(path) | n.id] AS nodeIds,
       length(path) AS hops
ORDER BY hops;
```

With exactly three nodes and two demo relationships, the result describes two paths:

| `nodeIds` | `hops` |
| --- | ---: |
| `['APOC-U1', 'APOC-U2']` | 1 |
| `['APOC-U1', 'APOC-U2', 'APOC-U3']` | 2 |

Explanation by data boundary:

1. `MATCH` locates the **start node**; variable `start` has type `NODE`.
2. `CALL apoc.path.expandConfig(start, {...})` passes the node and config map in positional order.
3. `YIELD path` captures the **output column** named `path` of type `PATH`.
4. `nodes(path)` turns the path into a list of nodes to extract `id`; `length(path)` counts relationships along the path.
5. `RETURN` aliases the outputs, and `ORDER BY` sorts by hop count.

If additional relationships of the same type emanate from the demo nodes, the query can return **more paths**. Never infer that `maxLevel: 2` always yields exactly two rows; that is merely the result on this specific demo graph.

### 6.4. YIELD can alias columns

```cypher
MATCH (start:ApocDemoPerson {id: 'APOC-U1'})
CALL apoc.path.expandConfig(start, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  minLevel: 1,
  maxLevel: 2
})
YIELD path AS p
WITH p
WHERE length(p) = 2
RETURN [n IN nodes(p) | n.id] AS route;
```

`YIELD path AS p` lets you reference `p` in subsequent clauses. `WITH p` keeps the variable in scope; `WHERE length(p) = 2` filters paths of exactly two hops. Once renamed, do not keep referencing `path` downstream if it is no longer in scope.

**Do not write** `YIELD nodeIds` merely because you want your output named that way: `nodeIds` is not a column published by the procedure. Write `YIELD path` and then compute `[n IN nodes(path) | n.id] AS nodeIds`.

## 7. Write Procedures: Reading Signatures and Managing Risk

Some APOC procedures write data, execute multiple transactions, or access external resources. Before calling one:

- Check the `mode` field and description from `SHOW PROCEDURES`.
- Identify the exact nodes, relationships, properties, or external resources affected.
- Verify execution privileges, graph privileges, and plugin configuration; do not assume a procedure is safe merely because its name begins with `apoc.`.
- For bulk ingestion or update jobs, plan idempotency, retries, batch-level error handling, and failure monitoring.

For instance, `apoc.periodic.iterate` commonly takes two Cypher strings and a config map to process data in batches. **Run the following example only in a practice database**, after confirming the procedure exists and write privileges are granted:

```cypher
SHOW PROCEDURES
YIELD name, signature, mode
WHERE name = 'apoc.periodic.iterate'
RETURN name, signature, mode;
```

Once the environment is verified:

```cypher
CALL apoc.periodic.iterate(
  'MATCH (p:ApocDemoPerson) RETURN p',
  'SET p.checked = true',
  {batchSize: 2, parallel: false}
)
YIELD batches, total, failedBatches
RETURN batches, total, failedBatches;
```

In this example:

- The first argument is a **query string that selects rows**, not an already-executed outer `MATCH` result.
- The second argument is a **write statement string** applied to those rows.
- The third argument is a **configuration map**; `batchSize` caps rows per batch, and `parallel: false` disables parallel execution.
- `YIELD batches, total, failedBatches` captures statistics published by the procedure; check the exact server signature for exact names and remaining columns.

With exactly three `ApocDemoPerson` nodes, you may observe `total = 3` and `batches = 2` upon normal completion. Despite a single outer call, inner batches can have **separate transaction boundaries**. Do not treat completed batch counts as proof that all business nodes/relationships are correct; verify the resulting data after execution.

> In Neo4j, `CALL { ... } IN TRANSACTIONS` is a **different Cypher syntax** for batched transactions. Do not treat it as identical to `apoc.periodic.iterate`; each approach has its own rules regarding transactions, inputs, error handling, and privileges.

## 8. When One Call Produces Multiple Rows

Suppose `MATCH` matches 10 source nodes. Each node yields 1–5 paths from `apoc.path.expandConfig`. The output may exceed 10 rows:

```cypher
MATCH (s:ApocDemoPerson)
CALL apoc.path.expandConfig(s, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  minLevel: 1,
  maxLevel: 2
})
YIELD path
RETURN s.id AS sourceId, length(path) AS hops;
```

Never assume `CALL` produces **exactly one row** per node `s`. If the procedure yields 0 rows, that input node may **disappear** from rows after `CALL`; if it yields multiple rows, the node appears multiple times.

This matters when:

- Using `LIMIT 20`: limits output to **20 rows**, not necessarily 20 distinct source nodes.
- Using `count(*)`: counts rows after the procedure, not input nodes.
- Using `SET` downstream: check whether the mutation runs repeatedly due to multiple paths.
- Using `collect()`: consider whether `DISTINCT` is needed to avoid duplicate nodes/paths per business rules.

Example counting paths for nodes that have at least one matching path:

```cypher
MATCH (s:ApocDemoPerson)
CALL apoc.path.expandConfig(s, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  minLevel: 1,
  maxLevel: 2
})
YIELD path
RETURN s.id AS sourceId, count(path) AS matchedPaths
ORDER BY sourceId;
```

Only `s` nodes with at least one valid path enter the aggregation after `CALL` in the query above. If you also want to retain nodes with zero paths, design an optional call or aggregation over the source node set according to your Neo4j version's capabilities, rather than assuming a procedure emits `null` rows.

## 9. Privileges, Plugins, and Compatibility

### 9.1. Distinguishing built-in Neo4j from APOC

`db.labels()` is a built-in Neo4j procedure. `apoc.*` names belong to APOC extensions that must be installed/enabled according to your deployment model:

- **Neo4j Desktop/Docker/self-managed:** check Neo4j version, matching APOC Core/Extended packages, plugin directory, and privilege settings. Installation steps vary by release.
- **Managed services like Neo4j Aura:** may expose only a curated APOC subset; do not assume you can upload arbitrary plugin JARs to the server.
- **Multi-server clusters:** ensure every server executing queries shares consistent plugin JARs and procedure configuration.

Never enable broad **unrestricted** settings just to make a single example work. Procedures accessing files, networks, or OS resources must follow the principle of least privilege.

### 9.2. Three steps to check a utility

```cypher
// 1. Is the procedure name in the catalog?
SHOW PROCEDURES
YIELD name, signature
WHERE name = 'apoc.path.expandConfig'
RETURN name, signature;
```

```cypher
// 2. Is the function name in the catalog?
SHOW FUNCTIONS
YIELD name, signature
WHERE name = 'apoc.text.join'
RETURN name, signature;
```

```cypher
// 3. If the function exists, test small inputs to check privileges and types.
RETURN apoc.text.join(['A', 'B'], '-') AS sample;
```

If a step fails, distinguish **name not found**, **missing privilege**, and **wrong argument type**. Never fix a failure by switching to a "similar-sounding" procedure solely because it shares a prefix.

### 9.3. Differences when upgrading versions

APOC and Cypher evolve across versions; some utilities may be renamed, superseded by standard Cypher syntax, or marked unsuitable for new applications. In particular, environments using **Cypher 25** may differ in support for certain older procedures.

When upgrading:

1. Inventory every procedure/function called by the application.
2. Re-check `SHOW PROCEDURES` / `SHOW FUNCTIONS` and their descriptions/signatures after upgrading.
3. Consult version-accurate APOC and Neo4j docs, especially defaults, argument types, outputs, and privileges.
4. Test with small datasets, `null` cases, empty lists/maps, and multi-row results.
5. Use `EXPLAIN`/`PROFILE` appropriately to inspect query plans; for write procedures, never run `PROFILE` against production data merely to test, as it executes mutations.

## 10. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `Unknown function 'apoc.text.join'` | APOC missing/unregistered, wrong name, or inaccessible | Check `SHOW FUNCTIONS`, version/plugin, and privileges |
| `There is no procedure with the name ...` | Wrong name or procedure not provided | Check `SHOW PROCEDURES`, package, and version |
| `CALL apoc.text.join(...)` fails | Used `CALL` on a function | Move call into `RETURN`/`WITH` |
| `RETURN apoc.path.expandConfig(...)` fails | Used a procedure like a function | Use `CALL ... YIELD path` |
| `YIELD nodeIds` fails | Desired alias, not an output column | `YIELD path`, then compute `nodeIds` in `RETURN` |
| Argument type mismatch | e.g., passed `STRING` when `LIST<STRING>` was expected | Read `signature`, verify values and types |
| `YIELD` loses variables downstream | `WITH` omitted required variables | Check variable scope, carry needed variables in `WITH` |
| More rows than nodes | Procedure yielded multiple paths/rows | Distinguish row counts from entity counts; group when needed |
| Zero result rows | No matching paths or wrong data/filter | Check start node, filter config, and expansion bounds |
| Insufficient execution privileges | Account role lacks privilege or blocked by config | Request least-privilege grant from admin; do not bypass security |
| Valid syntax on another machine but fails here | Different APOC version/package | Inspect signature on the actual target database |
| Write procedure partially fails | Statement splits transactions or writes externally | Check error output, checkpoints, idempotency, and reconciliation |

## 11. Java Driver and Spring Data Neo4j Integration

### 11.1. Java Driver: passing parameters to a function

Java 17+ example with Neo4j Java Driver 5.x, assuming an initialized `Driver` instance:

```java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class ApocTextExample {
    public static String joinNames(
        Driver driver, List<String> names, String separator
    ) {
        String cypher = """
            RETURN apoc.text.join($names, $separator) AS joined
            """;

        try (Session session =
                 driver.session(SessionConfig.forDatabase("neo4j"))) {
            return session.executeRead(tx ->
                tx.run(cypher, Map.of(
                    "names", names,
                    "separator", separator
                )).single().get("joined").asString()
            );
        }
    }
}
```

This code works only if the function is in the catalog. `Map.of` disallows `null` values; validate inputs or construct the map according to your application's null policy. Parameterization avoids string-concatenating user input into Cypher and enables query plan reuse.

### 11.2. Java Driver: reading results from a procedure

```java
String cypher = """
    MATCH (start:ApocDemoPerson {id: $startId})
    CALL apoc.path.expandConfig(start, {
      relationshipFilter: 'APOC_DEMO_FOLLOWS>',
      minLevel: 1,
      maxLevel: $maxHops
    })
    YIELD path
    RETURN length(path) AS hops
    ORDER BY hops
    """;

try (var session = driver.session()) {
    var rows = session.executeRead(tx ->
        tx.run(cypher, Map.of(
            "startId", "APOC-U1",
            "maxHops", 2
        )).list()
    );
    for (var record : rows) {
        System.out.println(record.get("hops").asLong());
    }
}
```

The second example is a **snippet inside a method** that already holds `Driver driver`, unlike the complete class above. If you need to map `PATH` to a DTO, access the `path` value from `Record` and extract nodes/relationships using driver types. Never assume a single `CALL` returns only one record.

### 11.3. Spring Data Neo4j

With Spring Data Neo4j, you can execute Cypher containing APOC via `@Query` or `Neo4jClient` when the utility is installed on the Neo4j server and permitted. Ensure `YIELD` / `RETURN` columns match the expected DTO or entity projection types.

- For a function returning a scalar, map to `String`, `Long`, or the corresponding type.
- For a procedure returning multiple rows or paths, use an appropriate DTO/projection instead of assuming a single node.
- For write procedures, verify actual transaction boundaries between SDN and the procedure. Specifically, do not wrap a procedure that creates internal transactions inside an outer transaction if your version/feature does not support it.

## 12. Practice Exercises

### Exercise 1: Identify procedures and functions

Classify the following calls and pick the right syntax: `db.labels()`, `size([1,2,3])`, `apoc.text.join(['x','y'], '-')`, and `apoc.path.expandConfig(start, config)`.

**Hint:** `db.labels` and `apoc.path.expandConfig` are procedures called with `CALL`; the remaining two are functions used inside expressions.

### Exercise 2: Read signatures instead of guessing

Look up the signatures of `apoc.path.expandConfig` and `apoc.text.join` on your practice system, and note:

1. Input types and argument order.
2. Whether there is a `MAP` parameter and which config keys require checking docs.
3. Output type / output columns.
4. Is the utility available under your current privileges?

```cypher
SHOW PROCEDURES
YIELD name, signature
WHERE name = 'apoc.path.expandConfig'
RETURN name, signature;
```

```cypher
SHOW FUNCTIONS
YIELD name, signature
WHERE name = 'apoc.text.join'
RETURN name, signature;
```

### Exercise 3: Fix a YIELD error

What is wrong with the following query?

```cypher
MATCH (s:ApocDemoPerson {id: 'APOC-U1'})
CALL apoc.path.expandConfig(s, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  maxLevel: 2
})
YIELD nodeIds
RETURN nodeIds;
```

**Suggested fix:** the procedure yields a `path` column, not `nodeIds`:

```cypher
MATCH (s:ApocDemoPerson {id: 'APOC-U1'})
CALL apoc.path.expandConfig(s, {
  relationshipFilter: 'APOC_DEMO_FOLLOWS>',
  minLevel: 1,
  maxLevel: 2
})
YIELD path
RETURN [n IN nodes(path) | n.id] AS nodeIds;
```

### Exercise 4: Distinguish rows from nodes

On the demo graph, `apoc.path.expandConfig` from `APOC-U1` returns two paths of length 1 and 2 hops. What is `count(*)` after `CALL`? Why must you not conclude there are two start nodes?

**Answer:** there are two **result rows** corresponding to two paths, yet only **one start node**, `APOC-U1`. If the graph has additional branches, the row count could be even higher.

### Exercise 5: Implementation decision

An application needs to join tag strings, expand relationships with filters, and ingest millions of relationships. Propose candidate approaches for each requirement, and answer: is using APOC always faster than standard Cypher?

**Hint:** string joining can use `apoc.text.join` if available; configured path expansion can consider `apoc.path.expandConfig`; bulk ingestion warrants evaluating `LOAD CSV`, `UNWIND`, `CALL { ... } IN TRANSACTIONS`, or batch procedures depending on environment. There is no guarantee APOC is always faster: use `EXPLAIN`, `PROFILE`, benchmarks, and verify privileges/maintainability.

## 13. Checklist Before Introducing APOC into an Application

- [ ] Clearly identify whether the call is a **procedure** or a **function**.
- [ ] Run `SHOW PROCEDURES` or `SHOW FUNCTIONS` on the target database.
- [ ] Read the signature, required/optional arguments, return type, and `YIELD` columns.
- [ ] Verify map options, `null` behavior, empty lists, and defaults.
- [ ] Keep `YIELD` and `AS` in proper scope; do not confuse procedure output columns with desired aliases.
- [ ] Understand row multiplicity from procedures before applying `LIMIT`, `count`, `collect`, or writes.
- [ ] Verify plugin registration, execution privileges, and Neo4j/APOC compatibility.
- [ ] For write procedures, establish transactions, retries, privileges, idempotency, and reconciliation.
- [ ] With Java Driver/SDN, use parameters, map types accurately, and manage resources.
- [ ] Check whether standard Cypher can replace it to minimize extension dependencies.

## Conclusion

When working with APOC in Neo4j, what matters most is not memorizing every utility name, but knowing how to **look up signatures** and **invoke each type properly**. Functions return a single value and live inside expressions; procedures are called via `CALL`, produce columns, and can generate multiple rows, so you must inspect `YIELD` and output types. `SHOW PROCEDURES` and `SHOW FUNCTIONS` verify availability on the live system. Combining these habits with an understanding of property graphs, privileges, versions, transactions, and query plans enables controlled, accurate, and maintainable use of APOC.

### References

- [Neo4j APOC — Documentation](https://neo4j.com/docs/apoc/current/)
- [Neo4j Cypher Manual — CALL procedure](https://neo4j.com/docs/cypher-manual/current/clauses/call/)
- [Neo4j Cypher Manual — SHOW PROCEDURES](https://neo4j.com/docs/cypher-manual/current/clauses/listing-procedures/)
- [Neo4j Cypher Manual — SHOW FUNCTIONS](https://neo4j.com/docs/cypher-manual/current/clauses/listing-functions/)
- [Neo4j Java Driver Manual](https://neo4j.com/docs/java-manual/current/)
