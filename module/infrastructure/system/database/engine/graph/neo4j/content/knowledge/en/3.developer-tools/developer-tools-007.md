# Reading Error Messages, Warnings, and Query Summary Statistics in Neo4j

> **Chapter:** Developer Tools  
> **Scope:** Neo4j, the property graph model, and Cypher queries; observing results via Neo4j Browser, `cypher-shell`, Java Driver, and Spring Data Neo4j applications.

When running Cypher on Neo4j, results do not consist solely of nodes, relationships, or values from the `RETURN` clause. The system can also return **errors**, **diagnostic notifications**, **data-modification statistics**, and **execution plans**. Knowing how to read each group of information accurately helps distinguish a syntax error, a valid query that matches no data, a query with performance risks, and a query that actually modified the graph.

## 1. Distinguishing Four Types of Signals

| Signal | Meaning | Question to Answer | Example |
|---|---|---|---|
| **Error / exception** | Neo4j could not complete the requested operation; the query or transaction may be aborted | Did it fail on syntax, parameters, data types, constraints, permissions, or connectivity? | Missing `$userId`; uniqueness constraint violation |
| **Notification / warning** | The query usually still runs, but the server detected something noteworthy | Is there a typo in a name, a disconnected graph pattern, a deprecated API, or a costly plan? | Non-existent label; Cartesian product; deprecated syntax |
| **Result records** | The records actually returned by `RETURN`/`YIELD` | How many rows are returned, and with what values? | One row `count = 0`, or 10 rows containing user names |
| **Summary / query statistics** | Information after consuming the query: write operation counts, timing, and/or metadata | Were nodes, relationships, or properties created or deleted? | `nodesCreated = 2`, `relationshipsCreated = 1` |

**Three easily confused misconceptions:**

- **No returned rows does not mean an error occurred.** A `MATCH` that finds no matching pattern can return 0 rows without throwing an exception.
- **A warning does not mean failure.** The query may still succeed yet need fixing for correctness or performance.
- **Returned rows do not mean data was modified.** `RETURN count(n)` can return a row even with zero write operations.

The exact placement and display labels of this information differ across Neo4j Browser, `cypher-shell`, drivers, configuration, and Neo4j versions. Therefore, rely on **meaning and data fields**, rather than depending verbatim on one illustrative message string.

## 2. Reading Errors: Identify the Cause Before Fixing

Error messages typically provide several components:

| Component | How to Read It |
|---|---|
| **Error code / status code** | Helps categorize errors for lookup or log classification; many versions emit codes such as `Neo.ClientError...`, `Neo.TransientError...`, or GQLSTATUS codes |
| **Message** | Describes the immediate cause, such as a missing parameter, undeclared variable, or constraint violation |
| **Position** | Line, column, or Cypher snippet causing the issue if Neo4j can pinpoint it |
| **Context** | The query, supplied parameters, database, transaction, and permission context of the executing account |
| **Application-side exception** | Drivers may wrap server errors into exceptions; network or timeout errors sometimes occur before the server returns a Cypher error code |

Do not assume every error includes all of the fields above or that every version emits the exact same error code.

### 2.1. Syntax and Variable Name Errors

Example of an intentional keyword typo:

~~~cypher
MATC (p:Person)
RETURN p.name;
~~~

Neo4j reports a syntax error and usually points to the region starting at `MATC`. Fix it to:

~~~cypher
MATCH (p:Person)
RETURN p.name;
~~~

Another error is using an undeclared variable:

~~~cypher
MATCH (p:Person)
RETURN user.name;
~~~

The variable was named `p`, not `user`. When reading the message, check exact variable names, variable scope after `WITH`, and the position indicated by the server. Avoid blindly rewriting the whole query before identifying the offending token.

### 2.2. Missing Parameters and Type Mismatches

~~~cypher
MATCH (u:User)
WHERE u.id = $userId
RETURN u.name;
~~~

`$userId` is a **parameter**, not a literal string. If the client does not pass `userId`, Neo4j reports a missing parameter. When running via Java Driver, pass it as a map:

~~~java
Map<String, Object> params = Map.of("userId", "u-101");
session.run(
    "MATCH (u:User) WHERE u.id = $userId RETURN u.name AS name",
    params
);
~~~

If the value stored in `u.id` is a number while the application passes a string, the query may run without matching any records; not every type mismatch raises an exception. When in doubt, inspect the schema, how data was imported, and the parameter's type. Never concatenate user values directly into a Cypher string; **parameterization** makes data types explicit and prevents injection.

### 2.3. Constraint, Transaction, and Permission Errors

Suppose the database has a uniqueness constraint on `User.id`:

~~~cypher
CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User)
REQUIRE u.id IS UNIQUE;
~~~

Two `CREATE` statements for a node with the same `id` will violate the constraint:

~~~cypher
CREATE (:User {id: 'u-101'});
CREATE (:User {id: 'u-101'});
~~~

If each statement runs in its own transaction, the first may have committed while the second fails. If both run in the same explicit transaction and one statement invalidates the transaction, check the transaction state and roll back per the client mechanism; **do not infer that all preceding statements committed**.

If you need to find or create a node by unique key, you can use:

~~~cypher
MERGE (u:User {id: $userId})
ON CREATE SET u.createdAt = datetime()
RETURN u;
~~~

`MERGE` does not replace designing proper constraints when multiple sessions write concurrently. Permission errors require checking roles, database, and actual privileges; they cannot be solved by editing `MATCH` or `CREATE` syntax.

### 2.4. Classifying Errors to Decide Whether to Retry

| Issue Category | Common Symptoms | Priority Action |
|---|---|---|
| Syntax, variables, parameters | Query fails to parse; missing variable/param name | Fix Cypher or parameter map |
| Schema / constraint | Duplicate key, data violates rules | Check values and constraints, consider `MERGE` |
| Permissions / database | Not permitted to read/write or wrong database selected | Check privileges, database name, and connection details |
| Network, leader switch, transient errors | Connection interrupted, transaction temporarily unable to complete | Assess retryability; apply controlled retry for eligible transactions |
| Unexpected result without an exception | Returns 0 rows or 0 updates | Check data, relationship direction, labels, and parameter values |

Codes under `TransientError` can help identify temporary errors, but **never blindly retry** a write operation that is not safe to re-execute. In Java Driver, transaction functions such as `executeRead`/`executeWrite` support retries for eligible cases; the callback must be safe for potential re-invocation. Syntax errors or constraint violations generally require fixing the root cause rather than repeating the same query.

## 3. Reading Warnings and Notifications

A **notification** is a diagnostic emitted by Neo4j for a valid query or during planning/execution. Depending on the version, each notification may contain:

- **Severity:** severity level, such as `WARNING` or `INFORMATION`.
- **Code / GQLSTATUS:** identifier for systems or tooling.
- **Title and description:** short name and explanation.
- **Position:** relevant location in the Cypher query, if available.
- **Category / classification:** groups such as performance, query pattern, deprecation, or schema; exact names and organization vary by version.

Do not rely solely on icon colors in the UI. The severity level and description are the proper basis for action.

### 3.1. Missing Labels, Relationship Types, or Properties

~~~cypher
MATCH (u:Uesr)
RETURN u.name;
~~~

If only the `User` label actually exists, this is likely a typo. Neo4j may notify that the label does not exist, and the query typically returns 0 rows. However, a new label for a feature that has no data yet is also a valid scenario. Verify the intended name and loaded data before changing the query.

Similarly, mistyping a relationship type:

~~~cypher
MATCH (u:User)-[:PURCHASEDD]->(o:Order)
RETURN o.id;
~~~

may match nothing even though `:PURCHASED` exists in the graph. In a property graph, **labels, relationship types, and arrow direction** all govern pattern matching. Read notifications alongside actual results so issues are not missed.

### 3.2. Cartesian Products and Disconnected Graph Patterns

~~~cypher
MATCH (u:User), (p:Product)
RETURN u.id, p.id;
~~~

The two patterns `u` and `p` have no connecting condition. With 1,000 `User` nodes and 2,000 `Product` nodes, the theoretical pair count reaches 2,000,000; this can be reflected via a Cartesian product notification and the execution plan. If the goal is to find products a user viewed, describe the relationship:

~~~cypher
MATCH (u:User)-[:VIEWED]->(p:Product)
RETURN u.id, p.id;
~~~

Cartesian products are not always wrong: occasionally business logic intentionally pairs every combination. In such cases, estimate intermediate set sizes, apply appropriate filters, and account intentionally for the cost.

### 3.3. Performance or Compatibility Warnings

Categories to watch for include queries using deprecated constructs, plans scanning many nodes, missing join conditions, or inapplicable planner hints. However, **no warnings does not guarantee a fast query**, and a node scan is not automatically a problem: a scan can be reasonable when most of the data must be read.

Example when looking up a user by email:

~~~cypher
MATCH (u:User)
WHERE u.email = $email
RETURN u.name;
~~~

To see whether the database has a suitable index, you can run:

~~~cypher
SHOW INDEXES;
~~~

Check the indexes associated with the `User` label and `email` property, then inspect the `EXPLAIN`/`PROFILE` plan. Do not create indexes on every property by default: creating and maintaining indexes has a cost, and the need depends on data volume, selectivity, and query patterns.

**Version note:** Starting in newer Neo4j/Driver releases, GQLSTATUS-compliant status objects are increasingly used to represent success, no-data, warnings, and exceptions. API names and surfaced notifications may change. Some clients also allow filtering severity levels or notification types, so **seeing no notification on the client does not prove the server never emitted one**.

## 4. Reading Post-Query Statistics

Neo4j can report **query statistics** or **summary counters** for an executed operation. For write statements, the following fields are especially useful:

| Counter | Interpretation |
|---|---|
| `nodesCreated` | Number of nodes created |
| `nodesDeleted` | Number of nodes deleted |
| `relationshipsCreated` | Number of relationships created |
| `relationshipsDeleted` | Number of relationships deleted |
| `propertiesSet` | Number of property set/update operations recorded |
| `labelsAdded` / `labelsRemoved` | Number of label add/remove operations |
| `indexesAdded` / `indexesRemoved` | Number of indexes added/removed by schema statements |
| `constraintsAdded` / `constraintsRemoved` | Number of constraints added/removed |
| `containsUpdates` | Whether data updates occurred |
| `containsSystemUpdates` | Whether metadata/system updates were detected, if supported by the API |

The field names here follow the Java Driver API; Browser or `cypher-shell` may display them with different wording. Counters reflect **operations recorded by the engine**, not proof that a business rule achieved the desired outcome. For example, `propertiesSet` does not tell you which property name changed or its old/new values.

### 4.1. Practice: Reads and Writes Are Two Different Kinds of Outcomes

Reading node count:

~~~cypher
MATCH (p:Person)
RETURN count(p) AS total;
~~~

The result is **one row** with column `total`, even when `total = 0`. Because the statement is read-only, write counters are typically 0. A value of `total = 100` **does not mean** 100 nodes were created.

Writing data:

~~~cypher
MATCH (p:Person)
WHERE p.active IS NULL
SET p.active = true
RETURN count(p) AS matched;
~~~

If 3 matching people exist, `matched` can be 3 and `propertiesSet` typically reflects three operations setting `active`. If no matching nodes exist, the statement is still valid, `matched = 0`, and no updates occur. When results differ from expectations, inspect both **returned row count/records** and **counters**.

Creating an edge in the graph:

~~~cypher
CREATE (a:City {name: 'Hà Nội'})
CREATE (b:City {name: 'Đà Nẵng'})
CREATE (a)-[:CONNECTED_TO]->(b);
~~~

With a normal database and write permissions, this example creates 2 nodes, 1 relationship, and their corresponding `name` properties. The statement may return zero records because there is no `RETURN`, yet counters still show the operations performed. **Do not re-run carelessly** on a shared database: `CREATE` creates new elements every time.

### 4.2. When Summary and Results Seem Contradictory

| Observation | Common Explanation | Verification Step |
|---|---|---|
| 0 rows, counters = 0 | `MATCH` matched nothing, or query has no `RETURN` and made no writes | Data, labels, relationship direction, `WHERE`, parameters |
| 1 row containing `count = 0` | The `count()` aggregate returns one row for an empty set | Distinguish row count from column value |
| 0 rows, `nodesCreated > 0` | `CREATE` query without `RETURN` | Check counters, then confirm data if needed |
| Multiple rows, counters = 0 | Pure read query | This is normal behavior |
| `propertiesSet > 0` yet business values look wrong | Query set properties, but `WHERE`/`SET` logic or data expectations may be off | Inspect representative records and application logic |

When an exception occurs, never interpret counters from an incomplete query as proof that data was committed. Check transaction boundaries and commit/rollback status.

## 5. Using EXPLAIN and PROFILE to Understand Performance Warnings

### 5.1. EXPLAIN: Viewing the Plan Without Running the Query

~~~cypher
EXPLAIN
MATCH (u:User)
WHERE u.email = $email
RETURN u.name;
~~~

`EXPLAIN` requests generating the **execution plan**: which operators will scan labels, use indexes, expand relationships, sort, or join data. Because it does not execute the query body, `EXPLAIN` cannot be used to determine actual row counts or how many writes occurred. It is useful for checking intent before a costly write statement.

### 5.2. PROFILE: Executing and Measuring on Real Data

~~~cypher
PROFILE
MATCH (u:User)
WHERE u.email = $email
RETURN u.name;
~~~

`PROFILE` actually runs the query and adds per-operator metrics, such as:

- **Rows:** number of rows passing through the operator; compare estimates against actual counts.
- **DB Hits:** indicator of data accesses by the operator; high values on large datasets may suggest bottlenecks.
- **Operator:** `NodeByLabelScan`, `NodeIndexSeek`, `Expand`, `Filter`, `Sort`, `CartesianProduct`, etc.; exact names depend on version and plan.
- **Time / memory / page cache:** some versions or environments provide additional metrics; do not assume every field is always present.

**Important warning:** `PROFILE` **also executes write queries**. Therefore, `PROFILE CREATE ...`, `PROFILE SET ...`, or `PROFILE DELETE ...` can modify real data. Always use `EXPLAIN` first; only measure write queries with `PROFILE` when you actively control the transaction, test data, and rollback/cleanup.

Read an execution plan starting from the highest-cost operators, checking whether a full scan makes sense, whether filters are applied early enough, and whether there are excessive intermediate rows or Cartesian products. A different plan does not automatically mean faster: compare under the same data, parameters, and load conditions.

## 6. Observing Feedback Across Tools

| Tool | Where to Look | Notes |
|---|---|---|
| **Neo4j Browser** | Result frame, warning/info list, and query statistics or plan tab | A query can be viewed as table/graph/text; to see optimization details use `EXPLAIN`/`PROFILE` |
| **cypher-shell** | Data printed to terminal, errors on stderr, and statistics/notification lines when supported by mode/version | Content and formatting depend on CLI flags, shell version, and server |
| **Neo4j Java Driver** | `Result`, `ResultSummary`, `SummaryCounters`, notifications or GQL status; exceptions | Must consume the result to access the final summary and handle exceptions |
| **Spring Data Neo4j** | Entity/DTO/repository result, exceptions, and logging; use Driver when detailed summaries are needed | Repositories prioritize object mapping; do not assume they expose all counters/notifications |

### 6.1. Java Driver Example: Reading Records, Warnings, and Counters

The following example illustrates common Java Driver 5.x APIs. When using a newer Driver release, check that version's GQLSTATUS API; older notification methods may be deprecated or changed.

~~~java
import java.util.Map;

import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Result;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.exceptions.Neo4jException;
import org.neo4j.driver.summary.ResultSummary;
import org.neo4j.driver.summary.SummaryCounters;

public class QueryFeedbackExample {
    public static void main(String[] args) {
        String uri = System.getenv("NEO4J_URI");
        String user = System.getenv("NEO4J_USER");
        String password = System.getenv("NEO4J_PASSWORD");

        try (Driver driver =
                     GraphDatabase.driver(uri, AuthTokens.basic(user, password));
             Session session = driver.session(
                     SessionConfig.forDatabase("neo4j"))) {

            Result result = session.run(
                    "MATCH (p:Person) WHERE p.city = $city " +
                    "RETURN p.name AS name LIMIT 10",
                    Map.of("city", "Hà Nội")
            );

            int rows = 0;
            while (result.hasNext()) {
                var record = result.next();
                System.out.println(record.get("name").isNull()
                        ? "(null)" : record.get("name").asString());
                rows++;
            }

            ResultSummary summary = result.consume();
            SummaryCounters counters = summary.counters();
            System.out.println("Returned rows: " + rows);
            System.out.println("Has updates: " + counters.containsUpdates());
            System.out.println("Nodes created: " + counters.nodesCreated());
            System.out.println("Relations created: "
                    + counters.relationshipsCreated());
            System.out.println("Properties set: " + counters.propertiesSet());

            for (var notification : summary.notifications()) {
                System.out.println("[" + notification.severity() + "] "
                        + notification.code() + " - "
                        + notification.description());
            }
        } catch (Neo4jException e) {
            System.err.println("Neo4j error code: " + e.code());
            System.err.println("Message: " + e.getMessage());
            throw e;
        }
    }
}
~~~

Environment variables must be configured before running; the `neo4j` database name in the example must be replaced with your actual database if different. The example uses a read-only query, so update counters are normally 0. The loop consumes records before `result.consume()` so needed data is not accidentally skipped; `consume()` retrieves the summary once reading finishes.

**When logging in an application:** record error code, exception type, query name or identifier, database, timestamp, and relevant metrics. Avoid logging passwords, tokens, or full parameter payloads containing personal or sensitive data. For connection-time errors, there may be no server-supplied error code; in that case log the exception category and secret-redacted connection info.

### 6.2. Spring Data Neo4j Applications

When calling a repository method like `findById` or a `@Query`-annotated method, the result is normally entities, projections, counts, or persistence-layer exceptions. If a use case requires reading **notifications, execution plans, or summary counters** in detail, design a dedicated query flow accessing Java Driver/Neo4jClient appropriate to the application architecture. Specifically, never open a separate `Session` inside a service using a Spring-managed transaction and assume both share the same transaction; verify the project's transaction integration.

## 7. Workflow for Diagnosing an Unexpected Result

1. **Record the exact symptom.** Is there an exception, notification, 0 rows, unexpected counters, or slow execution? Do not lump everything together as "query failed".
2. **Pin down the context.** Identify the database, Neo4j/Driver version, Cypher statement, parameters and data types, executing account, and transaction; redact sensitive information.
3. **If there is an error, read the code, message, and position first.** Fix syntax/params/constraints/permissions; decide on retries based on error type and operation safety.
4. **If there is no error yet the data looks wrong, check the graph pattern.** Verify label names, relationship types, relationship direction, `WHERE` conditions, and actual data using a small read query.
5. **If there is a warning or slow query, use `EXPLAIN` then `PROFILE` on a safe query.** Look for unnecessary scans, Cartesian products, large intermediate row counts, and unusual DB Hits.
6. **If writes were performed, check counters then verify the business outcome.** Changed node/relationship/property counts should match expectations; run a read query to confirm created/updated data.
7. **After fixing, re-run with the same parameters and compare.** Compare results, counters, notifications, and plans; document the root cause to prevent recurrence.

### Example A: Query Succeeds Yet Finds No Orders

~~~cypher
MATCH (u:User {id: $userId})-[:PLACED]->(o:Order)
RETURN o.id AS orderId;
~~~

If it returns 0 rows with no error: check whether `$userId` has the right type/value, whether the `User` exists, whether the relationship type is actually `PLACED`, and whether the edge points from `User` to `Order`. You can break it into smaller queries:

~~~cypher
MATCH (u:User {id: $userId})
RETURN u.id;
~~~

Then inspect the node's relationships separately. Never switch to a full-graph scan query in a large-data environment just to "fish around".

### Example B: Seeing a Cartesian Product and Huge Record Counts

~~~cypher
MATCH (u:User), (o:Order)
WHERE u.region = 'VN'
RETURN u.id, o.id;
~~~

The `u.region` condition does not connect `o` to `u`. Check whether the business problem needs every pair or each user's orders. If it needs each user's actual orders:

~~~cypher
MATCH (u:User)-[:PLACED]->(o:Order)
WHERE u.region = 'VN'
RETURN u.id, o.id;
~~~

Inspect the new plan to confirm intermediate row counts are now appropriate.

### Example C: Intended to Update 10 Nodes, Counters Report 0

~~~cypher
MATCH (p:Person)
WHERE p.status = 'PENDING'
SET p.status = 'ACTIVE'
RETURN count(p) AS updated;
~~~

If `updated = 0` and `propertiesSet = 0`, likely no nodes match `Person` + `status = 'PENDING'`. Run a read-only check:

~~~cypher
MATCH (p:Person)
RETURN p.status AS status, count(*) AS total
ORDER BY total DESC;
~~~

This may reveal data stored as `'pending'`, missing properties, or the wrong label. If `updated > 0`, compare counters and read back the data to verify business requirements.

## 8. Self-Check Exercises

**Exercise 1.** The query `MATCH (n:Person) RETURN count(n) AS total` returns one row with `total = 0`, no notifications, and all write counters equal to 0. Is this an error?  
**Answer:** No. The aggregation query executed successfully over an empty set; one `count` row is distinct from the number of matching nodes found.

**Exercise 2.** Does `EXPLAIN CREATE (:City {name: 'Huế'})` create a node? What about `PROFILE` with the same command?  
**Answer:** `EXPLAIN` only builds the plan so it creates no node; `PROFILE` executes the statement so it can create a real node.

**Exercise 3.** A query `MATCH (u:User), (p:Product) RETURN count(*)` triggers a Cartesian product warning. Can you eliminate the warning by removing `RETURN`?  
**Answer:** That does not address the root cause. You must specify the relationship/condition joining the two sets, or accept the Cartesian product if it is genuinely required by the business logic.

**Exercise 4.** An application receives a uniqueness constraint violation exception when creating a `User`, and then automatically retries the same `CREATE` statement multiple times. What is the right way to handle this?  
**Answer:** Verify the duplicate key and whether the intent is insert or upsert, then use unique keys/`MERGE` or an appropriate control mechanism; blind retries do not fix data errors and can cause unnecessary load.

## 9. Checklist When Working with Neo4j

- Read **exception code + message + position** when a query fails.
- Read **severity + description** when a notification appears, cross-checking with data and the execution plan.
- Keep **returned records**, `count()` aggregate values, and **summary counters** distinct.
- Use **`EXPLAIN` to inspect**, and **`PROFILE` to measure queries that are safe to execute**.
- Check labels, relationship types, edge direction, properties, indexes/constraints, and parameters before optimizing.
- With Java/Spring, respect transaction boundaries, retry only appropriate errors, and never leak secrets into logs.

Reading all of these layers enables developers to draw evidence-based conclusions: **did the query succeed, are the results accurate, did the graph change, and is the execution cost reasonable**.
