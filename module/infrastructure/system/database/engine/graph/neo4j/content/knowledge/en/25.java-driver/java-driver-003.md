# Driver Lifecycle, Sessions, and Database Selection

## 1. Why Connection Lifecycle Matters in Neo4j

Java applications query Neo4j using the property graph model: nodes, relationships, labels, types, and properties. Whether running `MATCH`, `MERGE`, Cypher path traversals, or ingesting thousands of records, **the lifecycle of the Java Driver, Session, and Transaction** determines performance, resilience, and reliability.

Three common mistakes:

- Creating a new `Driver` per HTTP request, wasting the connection pool and incurring repeated connection setup costs.
- Sharing a single `Session` across multiple threads, risking transaction state or cursor conflicts.
- Omitting the database name, causing queries to hit the wrong home database for the environment or tenant.

In the `DATABASE_ENGINE_GRAPH_NEO4J` module, this lesson belongs to the **Java Driver** chapter and explains the **Driver lifecycle, sessions, and database selection**, connecting them to indexes, constraints, Spring Data Neo4j, and running queries on a cluster.

After this lesson, you will be able to determine **who creates/closes the Driver**, when to open/close a **Session**, how to use `executeRead`/`executeWrite`, how to pass a database name with `SessionConfig`, why routing URIs are used, and when bookmarks are needed.

> **Code scope:** Java 17+ and the synchronous API of **Neo4j Java Driver 5.x** (`org.neo4j.driver`). Newer generations preserve similar concepts, though APIs should be checked against the actual Driver and Neo4j server versions. Older `readTransaction`/`writeTransaction` methods have been replaced by `executeRead`/`executeWrite`.

## 2. Four Resource Layers

~~~mermaid
flowchart TD
  A["Application / Spring Boot"] --> B["Shared Driver"]
  B --> C["Connection pool + routing"]
  B --> D["Session for request A"]
  B --> E["Session for request B"]
  D --> F["Transaction: executeRead / executeWrite"]
  E --> G["Another transaction"]
  F --> H["Result → Record / Summary"]
  H --> I["Read data and map to DTO"]
  I --> J["Close session"]
  A --> K["Shutdown: close Driver"]
~~~

| Component | Responsibility | Thread safety | Lifetime |
|---|---|---|---|
| **Driver** | Creates connections, manages pool, TLS, auth, routing metadata | **Thread-safe** | Long-lived and shared per endpoint/credentials config |
| **Session** | Selects database, access mode, bookmarks, and initiates transactions | **Not thread-safe** | One request, job, or short unit of work |
| **Transaction** | Groups operations for atomic commit/rollback | Not shared concurrently across threads | Just long enough for one business operation |
| **Result** | Cursor/stream of `Record`s from a query | Tied to transaction/session | Read and materialize data before closing resources |

**A Driver is not a single TCP connection.** It manages a connection pool and can serve many Sessions; creating a new Session does not necessarily open a new connection immediately. Closing a Session does not close the Driver.

**A Session is not an all-day transaction.** Each Session can run multiple transactions sequentially, but those transactions commit/rollback independently. If business logic must create nodes and relationships atomically (all succeed or all fail), place them in **one transaction**.

**A Result is not standalone data.** Returning an unconsumed `Result` outside a Session's `try-with-resources` block is a lifecycle bug. Convert it to a `List<DTO>`, `Optional<DTO>`, or primitive value while the session is still open.

## 3. Initializing the Driver Properly

### 3.1. Dependency

Example Maven declaration for an application whose dependencies are not managed by Spring Boot:

~~~xml
<dependency>
  <groupId>org.neo4j.driver</groupId>
  <artifactId>neo4j-java-driver</artifactId>
  <version>5.x.y</version>
</dependency>
~~~

`5.x.y` is a **placeholder notation** to pick a compatible release, not a literal Maven version to copy verbatim. In Spring Boot, prefer the framework's BOM and dependency management to avoid Java Driver/SDN version conflicts.

### 3.2. Console Program: One Driver for the Entire Runtime

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;

public final class Bootstrap {
    public static void main(String[] args) {
        String uri = requireEnv("NEO4J_URI");
        String username = requireEnv("NEO4J_USERNAME");
        String password = requireEnv("NEO4J_PASSWORD");

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(username, password))) {
            driver.verifyConnectivity();
            System.out.println("Neo4j reachable");
            // Create multiple different Sessions on the same Driver.
        }
    }

    static String requireEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing env: " + key);
        }
        return value;
    }
}
~~~

`verifyConnectivity()` helps catch address, authentication, or connectivity issues early. However, **it does not guarantee** full permissions on a specific database, nor does it guarantee network stability on subsequent requests.

In a web server, the Driver should be created **on application startup** and closed **on application shutdown**. Do not create/close a Driver inside each controller method or repository query.

### 3.3. URI, TLS, and Routing

| URI | Meaning | Use case |
|---|---|---|
| `neo4j://host:7687` | Driver uses the routing mechanism | Topologies with router/cluster; deployments supporting routing |
| `bolt://host:7687` | Direct connection to the specified endpoint | Intentional direct server connection |
| `neo4j+s://...` | Routing with TLS verifying trusted certificates | Suitable for production with valid certificates |
| `bolt+s://...` | Direct with TLS verifying trusted certificates | Secured direct endpoint |
| `neo4j+ssc://...` | TLS accepting self-signed certificates | Only when trust implications are evaluated, mainly test environments |

Choose the URI based on topology and TLS policy. In routing mode, the Driver can route to different read/write servers depending on transaction type and access mode. `bolt://` connects to a specific endpoint and does not automatically turn into cluster routing just because multiple servers exist.

**The Driver points to the DBMS/cluster; the Session selects the database.** These are two separate configuration layers.

## 4. Connection Pool and When to Tune It

The Driver shares a pool so multiple Sessions can execute queries concurrently. Applications typically have **one Driver per endpoint and credential set**, which does not mean only one transaction can run at a time.

Example pool configuration:

~~~java
import java.util.concurrent.TimeUnit;
import org.neo4j.driver.Config;

Config config = Config.builder()
    .withMaxConnectionPoolSize(50)
    .withConnectionAcquisitionTimeout(30, TimeUnit.SECONDS)
    .build();
~~~

Then pass `config` to `GraphDatabase.driver(uri, token, config)`. The numbers 50 and 30 are purely illustrative; measure workload, query latency, server capacity, and concurrent requests before changing them.

| Observation | Likely cause | Action before increasing pool size |
|---|---|---|
| Long wait to acquire a connection | Pool full, Sessions held too long, slow queries | Check close/consume calls and transaction duration |
| Many connections while server CPU is saturated | Queries/locking are the bottleneck | `EXPLAIN`/`PROFILE`, tune Cypher and concurrency |
| Creating a Driver per request | Pool is never reused | Switch to a singleton/application-scoped Driver |
| Sessions not closed on exception | Resource or cursor leaks | Use `try-with-resources` |

A larger pool can increase lock contention, CPU, or memory pressure on the server; it **will not** automatically make an unindexed `MATCH` run faster.

## 5. Selecting the Database with SessionConfig

Instead of implicitly relying on the home database:

~~~java
try (var session = driver.session()) {
    // Database is determined by the user's home/default database.
}
~~~

specify the database explicitly:

~~~java
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

String database = System.getenv().getOrDefault(
    "NEO4J_DATABASE", "neo4j"
);

try (Session session = driver.session(
        SessionConfig.forDatabase(database))) {
    session.run("RETURN 1 AS ok").consume();
}
~~~

**Why select explicitly?**

- A single DBMS can host multiple databases; the user's home database is not necessarily the one the application needs.
- When the database is omitted, the Driver may need to resolve the home database, adding round trips depending on topology.
- When deploying to another environment, the app might read the wrong data if the home/default database differs.
- Queries targeting a nonexistent database or lacking user permissions will still fail; `SessionConfig` **does not grant permissions**.

`"neo4j"` is commonly the default database name in basic deployments, but not an invariant rule. In multi-tenant environments, map **authenticated tenant → allowed database** from trusted configuration; never pass raw HTTP parameters straight through as a database name.

### Checking Available Databases

~~~cypher
SHOW DATABASES
YIELD name, currentStatus
RETURN name, currentStatus
ORDER BY name;
~~~

Listing databases depends on privileges and edition. Use a Session configured with the right database to run `RETURN 1` or a controlled read query. `verifyConnectivity()` only checks DBMS connectivity, not business query readiness on the target database.

## 6. Access Mode Is Not a Security Permission

In Driver 5.x, you can declare read intent when creating a Session:

~~~java
import org.neo4j.driver.AccessMode;
import org.neo4j.driver.SessionConfig;

SessionConfig readConfig = SessionConfig.builder()
    .withDatabase("neo4j")
    .withDefaultAccessMode(AccessMode.READ)
    .build();

try (var session = driver.session(readConfig)) {
    long n = session.run("""
        MATCH (c:QA003Customer)
        RETURN count(c) AS n
        """).single().get("n").asLong();
    System.out.println(n);
}
~~~

`AccessMode.READ` is a **routing hint**; it is not a security firewall and does not replace Neo4j privileges. Server role configuration still governs which labels, relationships, properties, or databases can be read or written.

In typical business code, the two **managed transaction** methods express intent more clearly:

- `session.executeRead(...)` — read query; the Driver can choose a read replica in routing mode.
- `session.executeWrite(...)` — write query; the Driver can route to the writer in routing mode.

Do not use `AccessMode.READ` to assume a write-privileged account is blocked from writing; assign proper least-privilege roles in Neo4j.

## 7. Managed Transactions and Automatic Retries

~~~java
session.executeRead(tx -> {
    // Read inside a Driver-managed transaction.
    return tx.run("RETURN 41 + 1 AS answer")
             .single().get("answer").asLong();
});

session.executeWrite(tx -> {
    // Write inside a Driver-managed transaction.
    tx.run("""
        MERGE (:QA003Tag {code: 'java'})
        """).consume();
    return null;
});
~~~

The Driver opens a transaction, commits/rolls back based on the outcome, and can **retry the transaction function** on eligible transient errors. This helps handle failover scenarios and temporary contention.

**Never send emails, call payment APIs, or publish non-idempotent events inside a transaction callback.** The function may execute multiple times, while side effects outside Neo4j will not roll back with the graph transaction.

Use parameters instead of concatenating input into Cypher:

~~~java
import org.neo4j.driver.Values;

try (var session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    session.executeWrite(tx -> {
        tx.run("""
            MERGE (c:QA003Customer {customerId: $id})
            SET c.name = $name
            """, Values.parameters(
                "id", "C001", "name", "An"
            )).consume();
        return null;
    });
}
~~~

`MERGE` combined with a uniqueness constraint on `customerId` yields more idempotent behavior than `CREATE` on client/transaction retries, though you still need clear business rules, especially when updating multiple nodes and relationships.

## 8. Auto-Commit and Explicit Transactions

### Auto-commit: session.run

~~~java
try (var session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    var result = session.run(
        "RETURN $v + 1 AS next",
        Values.parameters("v", 41)
    );
    long next = result.single().get("next").asLong();
    // next = 42
}
~~~

`session.run` creates an **implicit transaction**. Consume all records or call `consume()` when results are not needed to ensure the statement completes. Do not call `session.run(...)` and discard the cursor without consuming it.

Implicit transactions do not have the managed retry mechanism of `executeRead`/`executeWrite`. Certain Cypher statements such as `CALL { ... } IN TRANSACTIONS` must run as implicit transactions rather than inside managed/explicit transactions.

### Explicit Transaction: Manual Commit

~~~java
try (var session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    try (var tx = session.beginTransaction()) {
        tx.run("""
            MERGE (:QA003Customer {customerId: $id})
            """, Values.parameters("id", "C900")
        ).consume();
        tx.commit();
    }
}
~~~

The transaction groups queries for one business operation. If the transaction is closed without calling commit, the Driver rolls it back. With explicit transactions, the application must handle any required retries itself. Do not keep a transaction open while waiting on user input, external HTTP calls, or unrelated I/O.

### Two Transactions in One Session Are Not One Transaction

~~~java
try (var session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    long before = session.executeRead(tx ->
        tx.run("MATCH (c:QA003Customer) RETURN count(c) AS n")
          .single().get("n").asLong()
    );

    session.executeWrite(tx -> {
        tx.run("""
            MERGE (:QA003Customer {customerId: 'C002'})
            """).consume();
        return null;
    });

    long after = session.executeRead(tx ->
        tx.run("MATCH (c:QA003Customer) RETURN count(c) AS n")
          .single().get("n").asLong()
    );
}
~~~

`before` and `after` belong to separate transactions and can reflect concurrent writes from other clients. If you must check and write atomically, combine them into a single transaction.

## 9. Result and Summary: Consuming While the Session Is Open

**Anti-pattern:** returning a `Result` out of a closed session:

~~~java
// WRONG: do not use in real code.
static org.neo4j.driver.Result badQuery(Driver driver) {
    try (var session = driver.session(
            SessionConfig.forDatabase("neo4j"))) {
        return session.run("MATCH (n) RETURN n LIMIT 10");
    }
}
~~~

Instead, map records into an independent structure while inside the session:

~~~java
static java.util.List<String> listCustomerIds(
        Driver driver, String database) {
    try (var session = driver.session(
            SessionConfig.forDatabase(database))) {
        return session.executeRead(tx ->
            tx.run("""
                MATCH (c:QA003Customer)
                RETURN c.customerId AS id
                ORDER BY id
                """)
              .list(record -> record.get("id").asString())
        );
    }
}
~~~

For write queries, call `consume()` to obtain the `ResultSummary` and counters:

~~~java
try (var session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    session.executeWrite(tx -> {
        var summary = tx.run("""
            MERGE (:QA003Tag {code: 'java'})
            """).consume();
        System.out.println(
            "Created: " + summary.counters().nodesCreated()
        );
        return null;
    });
}
~~~

`nodesCreated()` is the number of nodes created **during that query execution**, not the total existing nodes. If the callback is retried, logging inside the callback may appear multiple times even though only one final transaction commits.

## 10. Practice: A Dataset with Expected Answers

### Step 1 — Prepare the Test Database

The commands below are **only for a practice database** and only when no real data shares the `QA003Customer` label. If you ran a previous exercise, clean up the fixture and create the unique constraint:

~~~cypher
DROP CONSTRAINT qa003_customer_id IF EXISTS;
~~~

~~~cypher
MATCH (c:QA003Customer)
DETACH DELETE c;
~~~

~~~cypher
CREATE CONSTRAINT qa003_customer_id IF NOT EXISTS
FOR (c:QA003Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

~~~cypher
UNWIND [
  {id:'C001', name:'An'},
  {id:'C002', name:'Binh'},
  {id:'C003', name:'Chi'}
] AS row
MERGE (c:QA003Customer {customerId: row.id})
SET c.name = row.name;
~~~

Verify:

~~~cypher
MATCH (c:QA003Customer)
RETURN count(c) AS total,
       count(DISTINCT c.customerId) AS distinctIds;
~~~

**Answer:** `total = 3`, `distinctIds = 3`.

### Step 2 — End-to-End Java Program

Set the environment variables `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, and `NEO4J_DATABASE` (if the database is not named `neo4j`).

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.Values;

public class CustomerDemo {
    public static void main(String[] args) {
        String uri = env("NEO4J_URI");
        String user = env("NEO4J_USERNAME");
        String password = env("NEO4J_PASSWORD");
        String db = System.getenv().getOrDefault(
            "NEO4J_DATABASE", "neo4j"
        );

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(user, password))) {
            driver.verifyConnectivity();

            upsert(driver, db, "C001", "An Updated");
            String name = readName(driver, db, "C001");
            System.out.println("Customer C001 = " + name);
        }
    }

    static void upsert(Driver driver, String db,
                       String id, String name) {
        try (Session session = driver.session(
                SessionConfig.forDatabase(db))) {
            session.executeWrite(tx -> {
                tx.run("""
                    MERGE (c:QA003Customer {customerId: $id})
                    SET c.name = $name
                    """, Values.parameters(
                        "id", id, "name", name
                    )).consume();
                return null;
            });
        }
    }

    static String readName(Driver driver, String db, String id) {
        try (Session session = driver.session(
                SessionConfig.forDatabase(db))) {
            return session.executeRead(tx ->
                tx.run("""
                    MATCH (c:QA003Customer {customerId: $id})
                    RETURN c.name AS name
                    """, Values.parameters("id", id))
                  .single().get("name").asString()
            );
        }
    }

    static String env(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing env: " + name);
        }
        return value;
    }
}
~~~

**Expected output:**

~~~text
Customer C001 = An Updated
~~~

Then run the verification Cypher query:

~~~cypher
MATCH (c:QA003Customer)
RETURN c.customerId AS id, c.name AS name
ORDER BY id;
~~~

| id | name |
|---|---|
| C001 | An Updated |
| C002 | Binh |
| C003 | Chi |

**Why exactly 3 nodes?** `MERGE` on `customerId` matches C001 and only updates `name`, without creating a new node. Running the program again still yields three nodes. Adding a new C004 increases the total to 4.

### Step 3 — Selecting Another Database

In multi-database deployments, use:

~~~java
try (var session = driver.session(
        SessionConfig.forDatabase("some_database"))) {
    long count = session.executeRead(tx ->
        tx.run("""
            MATCH (c:QA003Customer)
            RETURN count(c) AS n
            """).single().get("n").asLong()
    );
    System.out.println(count);
}
~~~

`some_database` is only a placeholder; replace it with an existing, permitted database. Do not assume another database contains the same three fixture customers. If permissions are missing or the name is wrong, handle the error explicitly rather than silently falling back to the default database.

## 11. Bookmarks and Causal Consistency on Clusters

In a cluster, a write transaction may commit on the writer while read replicas need time to apply the changes. If a subsequent request reads right after a write, the application sometimes needs **read-your-writes** guarantees across sessions.

**Bookmarks** carry transaction progress metadata, allowing subsequent read transactions to wait until the required data state is replicated when passed the appropriate bookmark. The Java Driver supports bookmark management, for example:

~~~java
import org.neo4j.driver.BookmarkManager;
import org.neo4j.driver.BookmarkManagers;
import org.neo4j.driver.SessionConfig;

BookmarkManager manager = BookmarkManagers.defaultBookmarkManager();

SessionConfig config = SessionConfig.builder()
    .withDatabase("neo4j")
    .withBookmarkManager(manager)
    .build();
~~~

Sessions sharing a manager within a workflow can achieve appropriate causal consistency. **Do not unconditionally share one manager across all tenants/requests**, as they do not necessarily share a causal chain and doing so can introduce unnecessary wait latency.

Bookmarks are not credentials, do not grant database access, do not guarantee cross-database state alignment, and do not replace transactions or constraints.

## 12. Spring Boot and Spring Data Neo4j

With Spring Data Neo4j, Spring Boot can auto-configure and manage the `Driver` bean; connection configuration typically looks like:

~~~properties
spring.neo4j.uri=neo4j+s://db.example.com:7687
spring.neo4j.authentication.username=provided-by-deployment
spring.neo4j.authentication.password=provided-by-secret-store
spring.data.neo4j.database=neo4j
~~~

**The two credential lines above are illustrative placeholders**, not a recommendation to hardcode usernames/passwords. In production, supply secrets via environment variables or your deployment's secret manager. Check property names against your Spring Boot/SDN version; `spring.data.neo4j.database` is the standard way to specify the database for SDN.

Integration rules:

- If Spring already configures a `Driver`, reuse that bean; do not instantiate a Driver inside every controller or repository.
- Repositories and `Neo4jClient` are appropriate for data operations through Spring Data Neo4j.
- Spring's `@Transactional` manages transactions via Spring/SDN's mechanism. A direct `driver.session().executeWrite(...)` call opens a separate transaction and **does not automatically join** the repository's transaction.
- A singleton `@Service` can hold a reference to `Driver`, but **never hold a shared Session**.
- If you define a custom `Driver` bean, let the Spring context close it once on shutdown; never call `driver.close()` inside individual requests.

For example, a business workflow creating an `Order` and a `PLACED` relationship needs an atomic transaction. If you mix repository calls under `@Transactional` with a separate Driver transaction, review commit boundaries carefully because the two parts may not roll back together when one fails.

## 13. Handling Errors at the Right Layer

| Symptom | Common cause | How to check |
|---|---|---|
| `verifyConnectivity` fails | URI/DNS/TLS/credentials/DBMS | Inspect network config, certificates, auth |
| Driver connects, but querying `analytics` fails | Wrong database, offline, or insufficient permissions | Check `SessionConfig`, `SHOW DATABASES`, RBAC |
| Connection acquisition timeout | Pool exhausted or sessions/results held too long | Use try-with-resources, consume properly, inspect query latency |
| `Result` fails when caller reads it | Session already closed | Materialize Records into DTO/List before returning |
| Transaction callback logs/emails twice | Managed retry after transient error | Ensure callbacks contain only retry-safe operations |
| Read-only query is slow | Index/plan/DB Hits/page cache/server | `EXPLAIN`/`PROFILE`; do not just raise pool size |
| Newly committed write missing when reading from replica | Incorrect bookmark/routing | Check causal consistency, database, and commit status |
| `single()` throws an error | Query returned 0 or more than 1 record | Check data, uniqueness, and not-found handling |
| Permission denied | User/role lacks privileges, unrelated to Driver lifecycle | Grant least-privilege permissions in Neo4j |

**Do not swallow every exception and return HTTP 200.** With managed transactions, throwing an exception prevents normal commit; with explicit transactions, call `commit()` only when all operations succeed. API-layer retry logic must account for Driver-level retries to avoid duplicate side effects.

## 14. Right vs. Wrong Lifecycle: Quick Comparison

| Anti-pattern | Consequence | Best practice |
|---|---|---|
| Creating `GraphDatabase.driver(...)` in every query | Loses connection pooling benefits | Long-lived Driver managed by application/context |
| `static Session` shared across threads | Session/transaction conflicts | Short-lived Session per unit of work |
| `driver.session()` without knowing the database | Uses unintended home database | `SessionConfig.forDatabase(configuredDb)` |
| Returning `Result` outside `try(Session ...)` | Cursor gets closed | Map to values/DTO/List while open |
| Calling `session.run` and ignoring Result | Query may remain incomplete; leaks resources | Consume all results or call `consume()` |
| Calling external network APIs inside `executeWrite` callback | Retries may cause duplicate side effects | Idempotency or outbox pattern |
| Using `AccessMode.READ` as a security control | Does not replace Neo4j privileges | RBAC and least-privilege roles |
| Increasing connection pool when queries scan heavily | Increases server resource contention | Tune indexes/Cypher, measure CPU/I/O |
| Calling `driver.close()` after every request | Other requests lose connections | Close only on application shutdown |

## 15. Exercises with Answers

**Exercise 1 — Who lives longer?** A server receives 100 HTTP requests/s. Should it create 100 Drivers per second?

**Answer:** No. For the same endpoint/credentials, normally create **one shared Driver**. Each request can open its own Session; never share a Session concurrently across threads.

**Exercise 2 — Selecting a database.** The application must read from the `sales` database, but currently calls `driver.session()`. Where should you fix it?

**Answer:** `driver.session(SessionConfig.forDatabase("sales"))`, then verify the user has permissions and the database is online.

**Exercise 3 — Closed Result.** A method returns a `Result` from inside `try (Session session=...)`. Why does the caller fail?

**Answer:** The Session closes before the caller finishes reading the cursor. Materialize records into a `List`/DTO/primitive value while the session is still open.

**Exercise 4 — Transaction retries.** Is it safe to send an email inside an `executeWrite` callback?

**Answer:** No, unless the email operation is idempotent. Transaction functions can re-execute; external side effects do not roll back with the graph. Use an outbox/idempotency design.

**Exercise 5 — Fixture answer.** After running `upsert` for C001 with the name "An Updated", how does the node count change?

**Answer:** Still **3 nodes**; C001's name is updated while C002 and C003 remain unchanged, provided reads/writes target the test database.

**Exercise 6 — Routing.** An account can read the graph, yet a `neo4j://` application runs `executeRead` and `executeWrite` on different servers. Is this a bug?

**Answer:** Not necessarily. Cluster routing can assign different servers for reads and writes. If you need read-after-write across sessions, use bookmarks.

**Exercise 7 — Connected but unauthorized.** `verifyConnectivity()` succeeds, whereas `MATCH` on `analytics` is denied. Is there a contradiction?

**Answer:** No. `verifyConnectivity()` checks general DBMS connectivity; target database access and permissions must still be verified separately.

## 16. Cleaning Up Practice Data

Run only in the **test database** used in Section 10:

~~~cypher
DROP CONSTRAINT qa003_customer_id IF EXISTS;
~~~

~~~cypher
MATCH (c:QA003Customer)
DETACH DELETE c;
~~~

~~~cypher
MATCH (t:QA003Tag)
DETACH DELETE t;
~~~

Verify:

~~~cypher
MATCH (n)
WHERE n:QA003Customer OR n:QA003Tag
RETURN count(n) AS remaining;
~~~

**Answer:** `remaining = 0`. Nodes like C900 or `QA003Tag` from other transaction examples are also part of the fixture and will be cleaned up. Do not run if the demo labels are shared with real data.

## 17. Official References and Key Takeaways

- [Neo4j Java Driver Manual — Connect](https://neo4j.com/docs/java-manual/current/connect/): creating Drivers, URIs, auth, `verifyConnectivity`.
- [Neo4j Java Driver Manual — Query the database](https://neo4j.com/docs/java-manual/current/query-simple/): Sessions, queries, parameters, and result handling.
- [Neo4j Java Driver Manual — Transactions](https://neo4j.com/docs/java-manual/current/transactions/): managed/explicit transactions, retries, and commit/rollback.
- [Neo4j Java Driver Manual — Performance recommendations](https://neo4j.com/docs/java-manual/current/performance/): reusing Drivers, specifying databases, and avoiding performance pitfalls.
- [Neo4j Java Driver Manual — Bookmarks](https://neo4j.com/docs/java-manual/current/bookmarks/): causal consistency across Sessions.
- [Neo4j Java Driver Manual — Advanced connection information](https://neo4j.com/docs/java-manual/current/connect-advanced/): routing, pooling, TLS, and timeouts.
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/): repositories, `Neo4jClient`, and transaction management.

**Summary:** `Driver` is long-lived and thread-safe; `Session` is short-lived and not thread-safe; `Transaction` governs commit/rollback; `Result` must be consumed before closing the connection. Always **select the database explicitly** when business logic requires targeting a specific database. Proper resource lifecycles keep Cypher queries, indexes/constraints, and Java/Spring systems stable as request volume grows.
