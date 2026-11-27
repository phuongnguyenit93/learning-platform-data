# Checking Syntax Compatibility Before Using New Cypher Features

When using Neo4j to store a **property graph**, developers routinely write Cypher queries to find nodes, traverse relationships, filter properties, and query paths. A new syntax feature can make a query shorter, easier to read, or more expressive, yet not every Neo4j server, Cypher language mode, driver, and deployment environment supports the exact same feature set.

This lesson walks through systematically verifying **a new Cypher feature before introducing it into an application**. The expected outcome is concrete evidence that the query is accepted by the target version, carries the intended semantics, executes over the real connection path, and has a fallback plan if an environment is not yet compatible.

## 1. Why Check Compatibility Before Using It?

Suppose a development team adopts a new variable-import syntax in a subquery. The query runs on a developer's local machine but fails in the test environment because that server runs an older version. Or the query is accepted by Neo4j Browser while the Spring Data Neo4j application binds parameters incorrectly, causing a runtime error.

Compatibility spans multiple layers:

| Verification Layer | Question to Answer | Example |
| --- | --- | --- |
| **Syntax (parser)** | Does the target server recognize the keywords, brackets, and clause structure? | Is `CALL (p) { ... }` recognized? |
| **Semantics** | Is the statement valid with respect to variables, data types, scope, and Cypher rules? | Is variable `p` imported into the subquery properly? |
| **Server capabilities** | Do required functions, procedures, indexes, or extensions exist and have permissions? | Does `SHOW FUNCTIONS` list the desired function? |
| **Execution** | Does the query work against real data, parameters, and transactions? | Are returned values correct when a node has no relationships? |
| **Integration** | Do the Java Driver, Spring Data Neo4j, and query routing behave as expected? | Does querying through a session targeting a specific database succeed? |
| **Performance** | Are the execution plan and graph traversal cost acceptable? | Does the query scan too many nodes or expand relationships too broadly? |

**Successful syntax compilation does not mean the application is fully compatible.** For instance, `EXPLAIN` can parse and plan a query, yet it proves neither real-data correctness nor runtime performance.

## 2. Identifying Environments and Version Boundaries

Before adopting new syntax, document every environment that will run the statement: Neo4j Desktop, a self-managed instance, Neo4j Aura, or a Neo4j cluster; which database; which Java applications connect to it; and which environment has the lowest version.

### 2.1. Retrieving Server Version Information

In Neo4j Browser, Cypher Shell, or a tool authorized to run queries, you can check:

```cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
```

The output identifies the Neo4j version and edition visible to the current connection. Procedure availability and execution permissions can vary across releases and deployment configurations. If this command is restricted, obtain the version from the administration UI or operational records confirmed by the database administration team.

In a **cluster**, connecting to one server does not prove that *every* member runs the same version. Especially during rolling upgrades, verify servers reachable via both read and write routing. In multi-database systems, be sure to test against the actual target database.

### 2.2. Distinguishing Neo4j Product Versions from Cypher Language Versions

A Neo4j product version and a Cypher language mode name are related concepts, not identical ones. Newer releases may offer selections such as **Cypher 5** and **Cypher 25**; which modes can be selected, which syntax is valid, and what the default mode is all depend on the Neo4j version running.

When documentation describes a new feature, confirm all of the following together:

1. The **earliest** Neo4j version supporting the feature.
2. Whether a specific Cypher language mode is required.
3. Whether the feature is generally available, experimental, marked with a deprecation warning, or changed in semantics.
4. The minimum version across **dev → test → staging → production**.
5. Dependencies such as procedures, plugins, permissions, and the Java Driver.

**Do not blindly prepend `CYPHER 25` to "enable" a feature on an older server.** If the server version does not recognize that mode, the prefix itself triggers an error. Specify a language version option only after verifying that the server supports it and that the selection syntax matches that release's documentation.

### 2.3. Consulting the Right Documentation Version

Create a verification entry for each feature you plan to adopt, drawing from the *Cypher Manual*, *Operations Manual*, and official release notes matching your deployed version. Never assume documentation from the latest Neo4j release guarantees an older Neo4j release supports the same syntax.

A concise tracking template:

| Item | Value to Record |
| --- | --- |
| New feature | Name of Cypher construct, function, or procedure |
| Sample syntax | Minimal query taken from the target version's documentation |
| Supported versions and modes | Recorded explicitly per official documentation |
| Environments to support | Dev, test, staging, production, and each cluster |
| Legacy fallback statement | Equivalent query if the target version does not yet support it |
| Verification evidence | `EXPLAIN` output, test execution, and application checks |

## 3. Process for Verifying New Cypher Syntax

A practical workflow should move from **fewest dependencies to closest to production**.

### Step 1 — Isolate One Specific Construct

Pinpoint the exact syntax to test, such as variable import syntax in a `CALL` subquery. Avoid testing multiple new features simultaneously in one long query, because errors become hard to diagnose.

Summarize briefly:

- What is the legacy syntax currently used?
- What problem does the new syntax solve?
- Which screen/API uses this query?
- Which Neo4j versions must support it?

### Step 2 — Build a Minimal Query

Strip the query down to the minimum elements required for the parser to recognize the new syntax. Only after a minimal example passes should you add filters, sorting, parameters, indexes, and business logic.

### Step 3 — Run `EXPLAIN` First

Prepend `EXPLAIN` to the query so Neo4j parses the syntax, validates required semantic rules, and generates an execution plan **without executing the statement**:

```cypher
EXPLAIN
MATCH (p:Person)
RETURN p.name AS name
LIMIT 5;
```

If the query is invalid, Neo4j may report an invalid token, undefined variable, type mismatch, or unrecognized function/procedure. Record the **full error code, message, server version, and query**, because a single "syntax error" line is not enough to pinpoint the root cause.

For parameterized queries, supply sample values with the **exact parameter names and types** during testing. Plan generation can depend on parameters, expression shapes, and server versions.

### Step 4 — Inspect Warnings and the Execution Plan

A query accepted by `EXPLAIN` can still emit notifications/warnings. For example:

- A node label, relationship type, or property does not yet exist in the schema/sample data.
- The syntax still runs but carries a **deprecated** warning.
- Using a particular function, procedure, or planning strategy has limitations.
- The plan shows a broad scan or wide relationship expansion.

Distinguish **blocking errors** from **notifications/warnings**. A warning does not always fail the query right away, yet a deprecation warning is a signal you must plan for before future upgrades.

### Step 5 — Verify Behavior in a Test Environment

Run the actual query on a representative dataset, in the target database, covering edge cases: matching data, empty results, `null` values, missing properties, multiple relationships, long paths, and invalid parameters.

If the query includes `CREATE`, `MERGE`, `SET`, or `DELETE`, use restorable test data and appropriate transactions. **`PROFILE` actually executes the query**, so never run `PROFILE` on a write statement in production without controlling its side effects. When you only need to check plan validity and planning behavior, prefer `EXPLAIN`.

### Step 6 — Verify Through the Application and Deployment Pipeline

Execute the same query from the Java Driver or Spring Data Neo4j version used by the project. Verify parameter binding, result mapping, transactions, target database selection, and cluster routing. Release only after every required environment has passing evidence or an approved compatibility fallback.

## 4. Example: Testing Variable Declaration Syntax in a `CALL` Subquery

Suppose a graph has `:Person` nodes and `:KNOWS` relationships, and we want to count how many people each person knows.

In Neo4j versions supporting the **variable scope clause**, a query can import variables from the outer query into a subquery using `CALL (p) { ... }`:

```cypher
EXPLAIN
MATCH (p:Person)
CALL (p) {
  MATCH (p)-[:KNOWS]->(f:Person)
  RETURN count(f) AS friendCount
}
RETURN p.name AS personName, friendCount
ORDER BY personName;
```

Here:

- `MATCH (p:Person)` identifies the input nodes.
- `CALL (p)` explicitly declares that variable `p` is imported into the subquery scope.
- `MATCH (p)-[:KNOWS]->(f:Person)` traverses relationships from `p` to `f`.
- `count(f)` counts matching nodes and returns `friendCount`.
- The outer `RETURN` uses the subquery result in the outer scope.

Variable declaration inside `CALL (...)` was introduced in later Neo4j 5.x releases; **you cannot infer from a server running "Neo4j 5" that every 5.x release supports this syntax**. Check the exact support milestone and run `EXPLAIN` against the deployed version itself.

If an environment does not yet support the declaration form above, a variant using an **importing `WITH`** may work on older versions:

```cypher
EXPLAIN
MATCH (p:Person)
CALL {
  WITH p
  MATCH (p)-[:KNOWS]->(f:Person)
  RETURN count(f) AS friendCount
}
RETURN p.name AS personName, friendCount
ORDER BY personName;
```

Both queries express the same intent in this example, though support and deprecation status of importing `WITH` depend on the target Cypher language mode and version. Therefore, test **each variant** across all required environments; do not treat the legacy variant as a permanent solution for all future versions.

### Sample Data for Verifying Results

Run the data creation snippet below only on a **test database** or isolated environment:

```cypher
CREATE (an:Person {name: 'An'})
CREATE (binh:Person {name: 'Bình'})
CREATE (chi:Person {name: 'Chi'})
CREATE (an)-[:KNOWS]->(binh)
CREATE (an)-[:KNOWS]->(chi);
```

With a dataset containing only these three people and two relationships, the expected result is:

| personName | friendCount |
| --- | ---: |
| An | 2 |
| Bình | 0 |
| Chi | 0 |

Because the subquery uses the aggregating expression `count(f)`, a count of 0 is still returned for people with no matching relationships. Actual execution catches semantic discrepancies that parser validation alone cannot guarantee.

**Note:** The `CREATE` statements above add new data on every run. Use a clean test database or delete sample data deliberately; never run repeatedly on production datasets.

## 5. Distinguishing Incompatibility Errors from Other Errors

Error messages usually point to what needs checking next:

| Symptom | Possible Cause | Action Needed |
| --- | --- | --- |
| `Invalid input` / unrecognized token | Parser does not support the syntax, or query has a typo | Check minimal syntax and server version support milestone |
| `Variable ... not defined` | Variable out of scope, missing subquery import, or typo | Check `WITH`, `CALL (...)`, and variable scope |
| Function or procedure does not exist | Feature absent in target version, missing plugin, typo, or restricted permission | Check `SHOW FUNCTIONS` / `SHOW PROCEDURES` and version-specific docs |
| Query plans fine but fails at runtime | Incompatible data, parameter type, type casting, or access rights | Test with representative parameters and data |
| Succeeds with deprecation notification | Syntax still accepted but scheduled to change/be removed | Plan migration to the recommended syntax |
| Works in dev but fails in production | Version skew, different Cypher mode, wrong database, or missing plugin | Compare environment matrix and actual routing |
| Correct results but slow | Different plan, missing index, selectivity, or graph size | Inspect `EXPLAIN`; run controlled `PROFILE` on suitable data |

For example, a missing index primarily affects **performance**; do not assume a `MATCH` query emitting an index warning has a "syntax error". Likewise, a procedure failing due to insufficient privileges does not prove the server version lacks that procedure.

### Inspecting Available Server Components

Depending on version and account privileges, you can run:

```cypher
SHOW FUNCTIONS;
```

```cypher
SHOW PROCEDURES;
```

```cypher
SHOW INDEXES;
```

```cypher
SHOW CONSTRAINTS;
```

These commands inspect available functions, procedures, and schema elements; **they do not replace testing the actual invocation** with target arguments and Cypher mode. Extension procedures also depend on installed plugins and environment-specific security configuration.

## 6. Testing Through the Java Driver and Spring Data Neo4j

A query that runs in Neo4j Browser can still fail from an application due to differences in user, database, parameter binding, or transaction handling. For Java systems, include an integration test using the exact driver and configuration in production use.

Example using the **Neo4j Java Driver with `executeRead`**, running `EXPLAIN` from the application:

```java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.summary.ResultSummary;

public class CypherCompatibilityCheck {
    public static void main(String[] args) {
        String uri = System.getenv("NEO4J_URI");
        String username = System.getenv("NEO4J_USER");
        String password = System.getenv("NEO4J_PASSWORD");

        String query = """
            EXPLAIN
            MATCH (p:Person)
            CALL (p) {
              MATCH (p)-[:KNOWS]->(f:Person)
              RETURN count(f) AS friendCount
            }
            RETURN p.name AS personName, friendCount
            """;

        try (Driver driver = GraphDatabase.driver(
                    uri, AuthTokens.basic(username, password));
             Session session = driver.session(
                    SessionConfig.forDatabase("neo4j"))) {
            ResultSummary summary = session.executeRead(
                tx -> tx.run(query).consume()
            );

            System.out.println("Plan available: " + summary.hasPlan());
            summary.notifications().forEach(notification ->
                System.out.println(
                    notification.code() + ": " + notification.description()
                )
            );
        }
    }
}
```

How this test works:

- `SessionConfig.forDatabase("neo4j")` targets the specified database; replace with your real database name.
- `executeRead` sends the query through the read routing and connection policy used by the application.
- `consume()` retrieves the summary to inspect the execution plan and notifications.
- If the syntax is unsupported, the driver throws a server error; record both the error code and message.
- This snippet uses a Java version supporting text blocks and a Neo4j Java Driver version exposing the shown APIs. For older or newer driver versions, adapt according to your driver's API documentation.

This is a **syntax compatibility check**, so the query includes `EXPLAIN`. To verify returned records, remove `EXPLAIN` and assert records in a dedicated test against a test database.

In Spring Data Neo4j, also verify the Cypher inside `@Query`, whether parameter names like `$externalId` match method parameters / `@Param`, entity mapping, and Spring-managed transactions. Example:

```java
@Query("""
    MATCH (p:Person)
    WHERE p.externalId = $externalId
    RETURN p
    """)
Optional<Person> findPerson(
    @Param("externalId") String externalId
);
```

This repository example illustrates parameter matching and mapping; it does not use the `CALL (p)` construct. When introducing new syntax into a real repository, add an integration test invoking **the exact repository method being changed**, against the real server and driver versions.

## 7. Common Compatibility Traps

### 7.1. Assuming Every Server Shares the Same Features

An environment where dev runs a newer release while production runs an older release will break if a new feature is tested only on dev. Your support matrix must list the exact version per environment, not merely "all use Neo4j".

### 7.2. Confusing Core Cypher Syntax with Plugin Procedures

A call like `CALL some.procedure(...)` may depend on an installed plugin or security configuration, whereas `CALL { ... }` is core Cypher syntax. Both start with the `CALL` keyword, yet their compatibility requirements differ.

### 7.3. Placing Parameters Where Syntax Does Not Allow Them

Parameters normally supply **data values**:

```cypher
MATCH (p:Person)
WHERE p.name = $name
RETURN p;
```

Do not assume every version allows passing a label or relationship type as a plain parameter, such as `MATCH (n:$label)`. Support for dynamic labels/types varies by release and uses dedicated syntax. Where unsupported, choose from predefined query variants selected via an allowlist in the application layer; never concatenate untrusted input into Cypher strings.

### 7.4. Testing Syntax Using `PROFILE` on Production Data

`PROFILE` executes the query to gather runtime metrics. For update statements, this can **mutate the graph**. Run `PROFILE` only on controlled data and environments, after the query has already passed `EXPLAIN` and functional tests.

### 7.5. Ignoring Deprecation Warnings

A query may succeed today while emitting a warning that its syntax will change or be removed. Record warnings and schedule migration; do not wait until the next major upgrade to discover a breaking change.

### 7.6. Testing Only a Single Application Code Path

An application may use read sessions, write sessions, multiple databases, load balancers, or multiple pods. Test from the **actual execution path**, using the real service account permissions. In multi-server clusters, also account for routing to members running different versions during upgrades.

## 8. Embedding Compatibility Checks into the Development Workflow

A team can establish clear acceptance gates for pull requests introducing new Cypher syntax.

| Stage | Verification | Acceptance Criterion |
| --- | --- | --- |
| Design | Read release docs and list target environments | Minimum version, Cypher mode, and fallback (if needed) documented |
| Syntax check | Run `EXPLAIN` on the lowest supported version | Zero syntax/semantic errors; warnings evaluated |
| Functional check | Run against a test database including edge cases | Results and data mutations match expectations |
| Integration check | Execute via Java Driver / Spring Data Neo4j with real config | Parameters, mapping, database, permissions, and transactions pass |
| Performance check | Inspect plan; benchmark in staging when needed | No regression exceeding project thresholds |
| Deployment | Compare server versions / Cypher modes before release | All required environments pass or have compatibility path ready |

One CI pattern is running tests against the **lowest supported version** alongside an environment matching the newer target version. If a product genuinely must support two syntax forms, keep two explicit queries in code and select between them based on confirmed configuration or capability checks. Avoid automatic "try-and-fallback on error" for write queries, because uncontrolled retries can duplicate data mutations.

### Pre-Merge Verification Checklist Template

```text
New Cypher feature: ................................
Query / commit: ....................................
Minimum Neo4j version to support: ..................
Cypher language mode: ..............................
Referenced documentation / release note: ...........
EXPLAIN result: PASS / FAIL
Important notifications: ...........................
Dataset and functional tests: PASS / FAIL
Java Driver / Spring Data test: PASS / FAIL
Cluster / database / permissions checked: ..........
Fallback or upgrade requirement: ...................
Reviewer / check date: .............................
```

## 9. Self-Check Practice Exercise

**Scenario:** An API must return the number of acquaintances for each `Person`. The team wants to migrate from importing `WITH` inside a subquery to `CALL (p)` so variable scoping into the subquery is clearer.

1. Identify the Neo4j versions in dev and staging, along with the Cypher language modes each environment supports.
2. Run `EXPLAIN` on both variants from Section 4. Save any error messages or notifications.
3. On a clean test database, create the three nodes and two relationships from the example; run the query without `EXPLAIN` and compare outputs with the expected table.
4. Execute the new query through the actual Java Driver or Spring Data Neo4j repository method, using the real target database and application credentials.
5. If staging does not yet accept the new syntax, choose to **keep the verified compatible syntax** or **upgrade the server according to plan**; document the rationale in the pull request.
6. After upgrading, re-run verification on each environment rather than extrapolating from dev results.

**Self-assessment questions:**

- Why can a query that runs in Neo4j Browser still fail when called by a Java application?
- What does `EXPLAIN` prove, and what must be verified by actually executing the query?
- If `EXPLAIN` accepts a query yet returns a deprecation notification, should you treat it as "fully compatible long-term"?
- Why is confirming **Neo4j 5.x** not enough to guarantee every syntax introduced during the 5.x series is available?

## 10. Conclusion

When adopting a new Cypher feature, **verify the version milestone and language mode**, **test a minimal statement with `EXPLAIN`**, **read all warnings**, and then **verify real execution results and the application connection path**. For Neo4j deployments spanning multiple environments or clusters, compatibility must be proven on the lowest version you are required to support, including during rolling upgrades.

Following this process lets you take advantage of new Cypher syntax to query nodes, relationships, and paths in a property graph while keeping integration risks with the Java Driver, Spring Data Neo4j, and operations under control.
