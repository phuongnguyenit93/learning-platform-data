# Bookmarks, Causal Consistency, and Cluster Routing

## 1. Why Does a Java Application Need Bookmarks in a Neo4j Cluster?

In Neo4j, nodes, relationships, and properties form a **property graph**. A Java application might write an order node via Cypher, then immediately read it back to display status, traverse paths, or load the order's relationships. When connecting to a **Neo4j cluster**, write transactions normally go to the database **writer**, whereas read transactions can run on a different **reader** that applies replicated changes asynchronously.

For example, a Java service executes in order:

1. **T1:** create **(:DemoBookmarkOrder {id: 'O-101'})** and commit successfully.
2. **T2:** from another session or service, read order **O-101** immediately after T1.
3. At the moment T2 starts, the chosen reader may not yet have applied the state T1 just committed.

If T2 must see T1, the application needs to express the dependency **T1 happens before T2**. A **bookmark** is a token allowing the Neo4j Java Driver to pass this dependency to the next query. The server will only execute the dependent transaction once the chosen cluster member reaches at least the database state represented by that bookmark.

This lesson belongs to the **Java Driver** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module, focusing on:

- The difference between **a successful commit**, **reader catch-up**, and **causal consistency**.
- The **bookmark** mechanism, automatic scoping, and passing bookmarks across **sessions**, threads, or services.
- **Routing URIs**, routing tables, and **reader/writer** roles in a cluster.
- Practical patterns with modern Java Drivers, failover handling, retries, and latency tuning.

This lesson covers consistency and routing when accessing graphs from Java. It does **not** replace transaction design, indexes, constraints, or Cypher tuning; those still determine application correctness and performance.

## 2. Consistency Model: What Must Be Guaranteed?

### 2.1. Commit Does Not Mean Every Reader Shows Changes Immediately

In a Neo4j cluster, a database can span multiple servers. Write transactions are coordinated by the database **leader/writer**, while other members receive and apply changes later. The Driver can route read transactions to a reader to distribute load.

Illustration:

~~~mermaid
sequenceDiagram
    participant App as Java application
    participant W as Writer
    participant R as Reader
    App->>W: T1: CREATE Order O-101
    W-->>App: Commit + bookmark B1
    Note over W,R: Reader may still be catching up to T1
    App->>R: T2: MATCH Order O-101 + B1
    R-->>R: Wait for state B1 if needed
    R-->>App: Return Order O-101
~~~

**Bookmarks do not force every cluster member to synchronize instantaneously.** A bookmark sets a **precondition before running a dependent query**: the serving member must be caught up at least to the bookmark. The query may wait, reroute, or fail if the condition cannot be met within the timeout.

### 2.2. Distinguishing Types of Guarantees

| Concept | What is guaranteed or described | What must **NOT** be assumed |
|---|---|---|
| **ACID transaction** | One transaction commits or rolls back as an atomic unit | Every other reader sees the commit at the exact same instant |
| **Eventual consistency under replication** | When stable, replicas eventually catch up | Any arbitrary reader reading right after commit always sees the latest write |
| **Causal consistency via bookmarks** | A dependent transaction will not run before the bookmarked state exists on its serving member | All transactions from all users share one global app-enforced wall-clock order |
| **Read-your-writes** | Subsequent reads in the same causal chain see what you wrote | Another process's query automatically knows the bookmark without passing it |
| **Linearizability / global latest-state reads** | A stronger guarantee on real-time observable ordering | A single bookmark does not turn independent read/write streams into linearizable ones |

Bookmarks establish a **happens-before** relation for explicitly dependent operations. They are not reliable timestamps for comparing wall-clock times, not node IDs, and cannot replace concurrency control when multiple transactions mutate the same entity.

### 2.3. When Is Causal Chaining Needed?

- **Read right after write:** one API creates a profile and another API immediately fetches the new profile.
- **Sequential workflow:** create a Customer first, create an Order linked to Customer next, then read the graph containing both.
- **Fan-in:** two independent tasks create A and B; a third task must see **both A and B**.
- **Queue handoff:** worker B should only execute after data created by worker A is visible.

Not every query needs to wait for the latest bookmark. Independent analytical reports or public listings can tolerate replication lag to reduce wait time and improve throughput.

## 3. What Is a Bookmark in the Java Driver?

A bookmark is an **opaque token** representing a state reached on **one database**. The Java Driver models it with the **org.neo4j.driver.Bookmark** interface. Applications should **store, pass, and restore** it without parsing its internal string or fabricating predictable values.

Lifecycle:

~~~mermaid
flowchart LR
    A["Transaction T1 commits"] --> B["Driver receives bookmark B1"]
    B --> C["Next Session receives B1"]
    C --> D["Server waits for state >= B1"]
    D --> E["T2 can read T1's data"]
    E --> F["T2 finishes and yields new bookmark"]
~~~

**Scope rules to remember:**

1. Within **a single Session**, the driver automatically chains **sequential** transactions using the session's latest bookmark.
2. With **Driver.executableQuery()**, the driver uses a default bookmark manager to link consecutive calls on the **same driver**.
3. Two **independent Sessions** do not share bookmarks merely because they came from the same Driver. You need **Session.lastBookmarks()**, **SessionConfig.withBookmarks(...)**, or a shared **BookmarkManager**.
4. Two **separate Java processes/services** do not share an in-memory manager automatically. If causal ordering crosses service boundaries, pass bookmark tokens or design another state-propagation mechanism.
5. Bookmarks belong to a specific **database**. Never mix bookmarks across different databases in the same DBMS, or across separate clusters.

**Do not confuse temporal proximity with causal dependency.** Independent transactions can run concurrently; only transactions that truly need to observe each other's outputs should share a bookmark chain.

### 3.1. Key APIs

| Java Driver API | Role |
|---|---|
| **Session.lastBookmarks()** | Retrieves the session's latest bookmark set after work completes |
| **SessionConfig.Builder.withBookmarks(...)** | Attaches initial bookmarks to a new session |
| **SessionConfig.Builder.withBookmarkManager(...)** | Uses a manager to coordinate bookmarks across multiple sessions |
| **BookmarkManagers.defaultManager(config)** | Creates a shared manager using the driver's bookmark tracking |
| **Driver.executableQueryBookmarkManager()** | Retrieves the default manager used by **executableQuery()** calls |
| **Bookmark.value()** | Extracts the opaque string for cross-process transfer |
| **Bookmark.from(value)** | Restores a Bookmark from a driver-produced string |

Documentation and examples below use modern **Neo4j Java Driver 5/6** APIs, verified specifically against **6.x**. Starting in Java Driver 6, the singular **Session.lastBookmark()** is removed; use **Session.lastBookmarks()**. Check your application's driver version before copying code.

## 4. Routing URIs and Reader/Writer Roles in a Cluster

### 4.1. URI Choice Controls Whether the Driver Routes

The Java Driver speaks the **Bolt** protocol. The URI scheme controls connection behavior:

| URI | Connection mode | Encryption / trust | When to use |
|---|---|---|---|
| **neo4j://host:7687** | Uses **routing** | No TLS enabled by scheme | Local environment or cluster with appropriate security setup |
| **neo4j+s://host:7687** | Routing | TLS, certificate signed by trusted CA | Production clusters, **Neo4j Aura** per provided URI |
| **neo4j+ssc://host:7687** | Routing | TLS accepting self-signed certificates | Test environments with explicit certificate policies |
| **bolt://host:7687** | **Direct** to specified server | No TLS enabled by scheme | Direct single-instance connection, intentional diagnostics |
| **bolt+s://host:7687** | Direct | TLS, trusted CA certificate | Specific server with TLS |
| **bolt+ssc://host:7687** | Direct | TLS accepting self-signed certificates | Direct testing with self-signed certificates |

**Do not change neo4j+s:// to bolt+s:// just because both use encryption.** The **neo4j** scheme performs routing; the **bolt** scheme talks directly to one machine. For clusters requiring failover and read scaling, use the **routing URI provided by your administrator or Aura**.

Never enable **+ssc** to bypass certificate verification errors in production when trusted CAs are required. Scheme, DNS, certificates, and endpoints must match your actual environment.

### 4.2. How the Routing Table Works

With the **neo4j** scheme, the driver contacts an entry address (*seed/router*), fetches the **routing table** for the database, and routes transactions to appropriate servers. A routing table contains:

- **Routers:** members supplying fresh routing tables.
- **Writers:** servers capable of handling writes for the database, usually the current **leader**.
- **Readers:** members serving read queries per cluster policy.

~~~mermaid
flowchart TD
    A["Java Driver neo4j+s://cluster"] --> B["Fetch routing table for database"]
    B --> C{"Transaction type?"}
    C -->|"WRITE"| D["Writer / leader"]
    C -->|"READ"| E["Suitable reader"]
    D --> F["Commit + bookmark"]
    F --> E
    E --> G["Wait for bookmark if needed, then return result"]
~~~

**Roles are scoped per database.** In multi-database systems, one server may be writer for one database and reader for another. Routing tables have a time-to-live (*TTL*); the driver refreshes them periodically or upon detecting topology/leader changes.

A single seed entrypoint can still be a weak spot before obtaining the routing table: if that first address is down, the driver cannot discover the cluster. In production, consider DNS names with multiple A/AAAA records, a custom resolver per documentation, or a highly available entrypoint.

### 4.3. DNS or Advertised Address Failures After Reaching the Seed

A common issue in Docker, Kubernetes, or private networks: Java connects to **cluster.example.com:7687**, yet the routing table returns member addresses like **neo4j-1.internal:7687** that are unreachable from the app. The driver throws connection acquisition or routing errors even though the seed endpoint works.

To fix this, verify **advertised Bolt addresses**, DNS, firewalls, ports, certificates, and client-facing hostnames. Never use **bolt://** to hide that error and declare the cluster healthy; a direct connection will work only until leadership moves to another node.

## 5. Practice: Preparing Data and Java Connectivity

Run this constraint once on a **test database**:

~~~cypher
CREATE CONSTRAINT demo_bookmark_order_id IF NOT EXISTS
FOR (o:DemoBookmarkOrder)
REQUIRE o.id IS UNIQUE;
~~~

Examples use **(:DemoBookmarkOrder {id, status})**. This label keeps practice data separate from real **Order** nodes. `MERGE` creates or updates a specific order, so repeated runs with the same ID update status instead of creating duplicates.

### 5.1. Proper Driver Initialization Lifecycle

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;

String uri = System.getenv("NEO4J_URI");
String username = System.getenv("NEO4J_USERNAME");
String password = System.getenv("NEO4J_PASSWORD");

try (Driver driver = GraphDatabase.driver(
        uri, AuthTokens.basic(username, password))) {
    driver.verifyConnectivity();
    // Subsequent examples use this driver.
}
~~~

Set **NEO4J_URI** to your environment's endpoint (e.g., **neo4j+s://...** issued by Aura). Never hardcode passwords or log credentials. The Driver should be created **once per application connection config** and reused across threads, as it manages the connection pool and routing table. **Sessions** are lightweight and **not thread-safe**; create them per unit of work and close via **try-with-resources**.

Java snippets in the following sections assume they sit **inside a method with `Driver driver` and database name `dbName` in scope**; set **dbName** to your test database. Examples use a Java version supporting **text blocks**.

## 6. Within One Session: Bookmarks Are Maintained Automatically

When consecutive transactions run inside the same session, the driver automatically propagates causal state between them:

~~~java
import java.util.Map;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

String dbName = "neo4j";
String orderId = "O-101";

try (Session session = driver.session(
        SessionConfig.forDatabase(dbName))) {

    session.executeWriteWithoutResult(tx -> {
        tx.run("""
            MERGE (o:DemoBookmarkOrder {id: $id})
            SET o.status = $status
            """, Map.of("id", orderId, "status", "CREATED"))
            .consume();
    });

    String status = session.executeRead(tx ->
        tx.run("""
            MATCH (o:DemoBookmarkOrder {id: $id})
            RETURN o.status AS status
            """, Map.of("id", orderId))
          .single().get("status").asString()
    );

    System.out.println(status); // CREATED
}
~~~

**executeWriteWithoutResult(...)** commits before **executeRead(...)** starts. The driver retains the corresponding bookmark inside the session, chaining the read to the write's commit state. **executeRead(...)** also declares read intent so the driver can route to a cluster reader.

If two Cypher statements must be **atomic** with each other, place them in **one transaction** inside a single callback. Bookmarks order **committed transactions sequentially**, without merging two transactions into one ACID unit.

## 7. Across Two Sessions: Passing lastBookmarks to withBookmarks

An HTTP endpoint may write in one short-lived session, close it, and have subsequent code open another session to read. Independent sessions must pass bookmarks when **read-your-writes** is required.

~~~java
import java.util.Map;
import java.util.Set;
import org.neo4j.driver.AccessMode;
import org.neo4j.driver.Bookmark;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

String dbName = "neo4j";
String orderId = "O-102";
Set<Bookmark> afterWrite;

// T1: write, commit, then retain the session's bookmarks.
try (Session writer = driver.session(SessionConfig.forDatabase(dbName))) {
    writer.executeWriteWithoutResult(tx -> {
        tx.run("""
            MERGE (o:DemoBookmarkOrder {id: $id})
            SET o.status = 'CREATED'
            """, Map.of("id", orderId))
            .consume();
    });
    afterWrite = Set.copyOf(writer.lastBookmarks());
}

// T2: another session, reading on a reader that must see T1.
try (Session reader = driver.session(SessionConfig.builder()
        .withDatabase(dbName)
        .withBookmarks(afterWrite)
        .withDefaultAccessMode(AccessMode.READ)
        .build())) {

    String status = reader.executeRead(tx ->
        tx.run("""
            MATCH (o:DemoBookmarkOrder {id: $id})
            RETURN o.status AS status
            """, Map.of("id", orderId))
            .single().get("status").asString()
    );

    System.out.println(status); // CREATED
}
~~~

**Why retrieve bookmarks after the callback?** Only after a transaction **commits successfully** does its bookmark represent the state subsequent transactions must see. Never capture bookmarks mid-callback before commit, and never assume a rolled-back transaction produces a bookmark for unwritten data.

Here **Set.copyOf(...)** keeps an immutable copy in application memory. **withBookmarks(...)** accepts the initial bookmark set, and the driver continues updating bookmarks inside the read session. Bookmarks may be empty in certain scenarios; production code must follow API and transaction outcomes rather than fabricating bookmarks from system time.

### 7.1. Fan-In: Needing Results from Two Parallel Writers

Suppose session A creates a Customer and session B creates a Product; session C needs to link them with a relationship. Tasks A and B can run in parallel, while **C starts only after both commit**. Once both writers finish:

~~~java
import java.util.HashSet;
import java.util.Set;
import org.neo4j.driver.Bookmark;
import org.neo4j.driver.SessionConfig;

Set<Bookmark> dependencies = new HashSet<>();
dependencies.addAll(sessionABookmarks);
dependencies.addAll(sessionBBookmarks);

try (var sessionC = driver.session(SessionConfig.builder()
        .withDatabase(dbName)
        .withBookmarks(dependencies)
        .build())) {
    sessionC.executeWriteWithoutResult(tx -> {
        tx.run("""
            MATCH (c:DemoBookmarkCustomer {id: $customerId})
            MATCH (p:DemoBookmarkProduct {sku: $sku})
            MERGE (c)-[:DEMO_BOOKMARK_BUYS]->(p)
            """, Map.of("customerId", "C-101", "sku", "P-201"))
            .consume();
    });
}
~~~

Here **sessionABookmarks** and **sessionBBookmarks** are **Set<Bookmark>** instances obtained via **lastBookmarks()** after each task committed; Customer and Product must exist in the test database if running this snippet. The Java Driver requires database state satisfying **both dependencies** before executing T3.

Combining bookmarks from different databases into one session makes no sense. Furthermore, **combining bookmarks does not lock data**; if another task modifies the Customer after A commits, concurrency must still be handled via transactions and constraints.

## 8. BookmarkManager: Sharing State Across Multiple Sessions

Passing **lastBookmarks()/withBookmarks()** manually works well for a few explicit dependencies. When a business flow opens multiple sessions in the **same JVM**, sharing a **BookmarkManager** lets the driver collect and propagate bookmarks automatically.

### 8.1. Creating a Manager Scoped to One Dependency Flow

~~~java
import java.util.Map;
import org.neo4j.driver.BookmarkManager;
import org.neo4j.driver.BookmarkManagerConfig;
import org.neo4j.driver.BookmarkManagers;
import org.neo4j.driver.SessionConfig;

BookmarkManager manager = BookmarkManagers.defaultManager(
    BookmarkManagerConfig.builder().build());

SessionConfig writeConfig = SessionConfig.builder()
    .withDatabase(dbName)
    .withBookmarkManager(manager)
    .build();

try (var writer = driver.session(writeConfig)) {
    writer.executeWriteWithoutResult(tx ->
        tx.run("""
            MERGE (o:DemoBookmarkOrder {id: $id})
            SET o.status = $status
            """, Map.of("id", "O-103", "status", "PAID")).consume()
    );
}

SessionConfig readConfig = SessionConfig.builder()
    .withDatabase(dbName)
    .withBookmarkManager(manager)
    .build();

try (var reader = driver.session(readConfig)) {
    String status = reader.executeRead(tx ->
        tx.run("""
            MATCH (o:DemoBookmarkOrder {id: $id})
            RETURN o.status AS status
            """, Map.of("id", "O-103"))
            .single().get("status").asString()
    );
    System.out.println(status); // PAID
}
~~~

**The manager instance must actually be shared**: each call to **BookmarkManagers.defaultManager(...)** creates a separate manager, so do not create a new manager per session expecting causal chaining. Share a manager only across tasks targeting **the same database that are genuinely related**; using one global manager across thousands of unrelated requests forces queries to wait on unrelated writes.

By default, a **Session** does not automatically share a BookmarkManager with other sessions. **Intra-session** bookmark tracking still works without configuring a shared manager.

### 8.2. Driver.executableQuery(): Built-In Bookmark Management

**executableQuery()** is convenient for standalone single-query transactions:

~~~java
import java.util.Map;
import org.neo4j.driver.QueryConfig;
import org.neo4j.driver.RoutingControl;

driver.executableQuery("""
    MERGE (o:DemoBookmarkOrder {id: $id})
    SET o.status = 'SHIPPED'
    """)
    .withParameters(Map.of("id", "O-104"))
    .withConfig(QueryConfig.builder()
        .withDatabase(dbName)
        .build())
    .execute();

var result = driver.executableQuery("""
    MATCH (o:DemoBookmarkOrder {id: $id})
    RETURN o.status AS status
    """)
    .withParameters(Map.of("id", "O-104"))
    .withConfig(QueryConfig.builder()
        .withDatabase(dbName)
        .withRouting(RoutingControl.READ)
        .build())
    .execute();

System.out.println(result.records().get(0).get("status").asString());
~~~

**executableQuery()** calls using the default manager of the **same Driver** are causally linked; the subsequent read can specify **RoutingControl.READ** to declare read routing intent. Configuring **withBookmarkManager(null)** disables manager usage for that call; avoid doing so if code relies on read-your-writes guarantees.

When mixing **executableQuery()** and sessions in the same dependency chain, pass the driver's default manager into the session:

~~~java
SessionConfig sharedConfig = SessionConfig.builder()
    .withDatabase(dbName)
    .withBookmarkManager(driver.executableQueryBookmarkManager())
    .build();

try (var session = driver.session(sharedConfig)) {
    session.executeRead(tx ->
        tx.run("RETURN 1 AS ok").single().get("ok").asInt()
    );
}
~~~

**Do not assume every Session created from the Driver shares this manager automatically**: explicitly attach **withBookmarkManager(...)** whenever linking with `executableQuery`.

## 9. Passing Bookmarks Across Service Boundaries

If service A commits a transaction and sends an event to service B over HTTP or a message broker, **the BookmarkManager in JVM A does not automatically transfer to JVM B**. When the workflow requires B to see A's just-committed data:

1. A **commits successfully**.
2. A extracts **Set<Bookmark>** from its session.
3. A sends those opaque token values to B over a reliable channel, along with **database name / dependency flow context**.
4. B restores the bookmarks and opens a new session with **withBookmarks(...)**.
5. B runs its transaction against the **same logical database**, allowing the server to wait for the required state if needed.

Serialization in Java:

~~~java
import java.util.List;
import org.neo4j.driver.Bookmark;

// Service A: after commit, prepare payload to send to service B.
List<String> tokens = writerBookmarks.stream()
    .map(Bookmark::value)
    .toList();

// Service B: receive validated payload and attach to a new session.
List<Bookmark> restored = tokens.stream()
    .map(Bookmark::from)
    .toList();

try (var session = driver.session(SessionConfig.builder()
        .withDatabase(dbName)
        .withBookmarks(restored)
        .build())) {
    session.executeRead(tx ->
        tx.run("RETURN 1 AS reachable")
          .single().get("reachable").asInt()
    );
}
~~~

Above, **writerBookmarks** comes from A's completed transaction, **tokens** travel over the inter-service channel, and service B substitutes real received values. `RETURN 1` only demonstrates session setup; replace it with your dependent node/relationship query.

**Never replace bookmarks with timestamps or auto-incrementing transaction IDs.** Bookmarks are database/driver-defined tokens. Treat them as workflow metadata: bound size, validate the sender, avoid logging unnecessary tokens, and never expose them in public URLs. Do not persist bookmarks indefinitely as permanent application state; manage lifetimes and malformed tokens per system policy.

If service A writes to database **orders** while service B reads a separate **analytics** database, passing orders bookmarks **does not guarantee** the data has arrived in analytics. Cross-database synchronization requires dedicated mechanisms (CDC, ETL, events, workflows, or progress checkpoints).

## 10. Routing Read and Write Queries Properly

### 10.1. Managed Transactions: executeRead / executeWrite

When using **neo4j://** or **neo4j+s://**, express intent explicitly so the driver distributes load:

~~~java
try (var session = driver.session(
        SessionConfig.forDatabase(dbName))) {

    long total = session.executeRead(tx ->
        tx.run("MATCH (o:DemoBookmarkOrder) RETURN count(o) AS total")
          .single().get("total").asLong()
    );

    session.executeWriteWithoutResult(tx ->
        tx.run("""
            MERGE (o:DemoBookmarkOrder {id: $id})
            SET o.status = $status
            """, Map.of("id", "O-105", "status", "CREATED"))
          .consume()
    );
}
~~~

**executeRead** routes read transactions to readers per the routing table; **executeWrite** routes write transactions to the database writer. The Driver can retry **managed transaction** callbacks on recognized transient errors.

**Never use access mode as an authorization mechanism.** Real READ/WRITE permissions must still be granted or denied through Neo4j roles and database privileges. **executeRead** is a *routing/intent hint*, not a security boundary replacing user privileges.

### 10.2. Explicit Transactions and session.run()

With explicit transactions:

~~~java
import org.neo4j.driver.AccessMode;

SessionConfig readOnlyRouting = SessionConfig.builder()
    .withDatabase(dbName)
    .withDefaultAccessMode(AccessMode.READ)
    .build();

try (var session = driver.session(readOnlyRouting);
     var tx = session.beginTransaction()) {
    long count = tx.run("MATCH (o:DemoBookmarkOrder) RETURN count(o) AS n")
        .single().get("n").asLong();
    System.out.println(count);
    tx.commit();
}
~~~

**withDefaultAccessMode(AccessMode.READ)** is especially important for **explicit transactions** and **session.run(...)** when reads should hit readers. Managed **executeRead** and **executeWrite** automatically select access mode from the method used. Avoid routing every read query to the writer by default, as that adds unnecessary load to the writer member.

With **session.run(...)** (*auto-commit*), consume results or confirm completion before relying on bookmarks or committed state. Compared to managed transactions, auto-commit differs in retry semantics and commit timing; do not use it for multi-step transactions needing coordinated retries.

### 10.3. Selecting the Database Explicitly

~~~java
SessionConfig config = SessionConfig.builder()
    .withDatabase("neo4j")
    .build();
~~~

All examples should **specify the database**, even in single-database setups. Omitting it may force the driver to ask the server for the home database, adding round trips and risking targeting the wrong database if accounts or deployments change. In multi-database clusters, routing tables and writers are resolved **per database**.

Prefer **SessionConfig.withDatabase(...)** over relying on **USE** in every Cypher statement; **USE** may trigger server-side routing and complicate routing plans.

## 11. Failures, Failover, and Limitations of Bookmarks

### 11.1. Reader Fails to Catch Up to Bookmark

Scenario: T1 commits, and T2 carries the bookmark to a reader that has not yet applied T1. The driver/server may **wait** for the reader to catch up. If waiting exceeds limits or the member becomes unavailable, the application may receive a **timeout/transient error**.

Do not conclude bookmarks are "broken" simply because T2 takes longer. That extra time may be the **cost of waiting for replication** to satisfy causal consistency. Monitor request latency, transaction retries, routing errors, cluster health, and replication lag before changing configuration.

### 11.2. Leader Switch and Stale Routing Tables

During a cluster leader election, a writer listed in a stale routing table can no longer accept writes. The Driver refreshes the routing table and **retries** managed transactions on transient errors.

However, **executeWrite** callbacks can **re-run**. Therefore:

- Keep only database operations and retry-safe computations inside callbacks.
- **Never** send emails, charge payments, or call non-idempotent external APIs inside callbacks.
- Use a **requestId/idempotency key** and constraints when business rules require single application.
- Never retry endlessly; let the driver bound transient retries or apply a measured retry policy.
- Distinguish **routing failures**, **bookmark wait timeouts**, **authentication/permission errors**, and **constraint violations**; never retry blindly.

### 11.3. What Bookmarks Do Not Solve

| Problem | Does a bookmark solve it? | Proper approach |
|---|---|---|
| A reader must see an earlier write transaction | **Yes**, when bookmarks are properly passed/managed | Chain via bookmarks |
| Two transactions increment a counter causing lost update | **No** | Atomic Cypher updates, locking/constraints |
| Two services create duplicate Customers due to missing unique key | **No** | Uniqueness constraints and `MERGE` on stable keys |
| Reading stale data from an unrefreshed application cache | **No** | Invalidate/update cache via dedicated workflow |
| Keeping two independent databases consistent | **Not automatically** | CDC/outbox/ETL and progress checkpoints |
| Lowering latency of all queries | **No**; waiting for bookmarks can raise latency | Link only genuinely dependent queries |
| Replacing user WRITE/READ privileges | **No** | RBAC, graph/database privileges, secure config |

### 11.4. Do Not Habitually Use One Global Manager

Suppose an app serves thousands of users independently creating and reading orders. A **single app-wide BookmarkManager** forces unrelated queries into artificial dependency chains, making each request wait for writes from other users. When causal guarantees are needed **per request or per user**, scope managers or bookmarks to **that specific business flow**.

Common strategies:

| Dependency scope | Appropriate design |
|---|---|
| Multiple operations within one transaction | Single transaction |
| Sequential transactions within one Session | Single Session |
| Multiple Sessions in one Java workflow | Pass bookmarks or share a scoped manager |
| Combining `executableQuery` with Sessions | **driver.executableQueryBookmarkManager()** |
| Multiple services/JVMs | Pass bookmark tokens across service boundaries, or use another sync mechanism |
| Independent tasks tolerating replication lag | Do not chain bookmarks unnecessarily |

## 12. Testing Cluster Behavior

Practice requires at least **one test database**, a Java account with read/write privileges, and a routing endpoint. To observe readers catching up to writers in real life, test against a multi-member cluster; a single Neo4j instance validates APIs, but cannot demonstrate routing/replication behavior.

### 12.1. Testing Read-Your-Writes

1. Use **executeWrite** to write a new **DemoBookmarkOrder**.
2. Read in **another Session** using the writer's bookmarks and **executeRead**.
3. Verify **status** matches the just-committed data.
4. Repeat across multiple IDs and iterations to verify stability.

Expected outcome: a bookmark-constrained reader **never returns state older than the dependent transaction**. Tests do not need artificial **Thread.sleep** delays; real cluster replication lag is non-deterministic.

### 12.2. Testing Fan-In

1. Use two independent sessions/writer threads to create a Customer and a Product.
2. Wait for **both transactions to commit**, collecting both bookmark sets.
3. Pass the **union** of both bookmark sets to a third session to create the relationship.
4. Verify both endpoints exist and the relationship is created properly.

If one write branch fails, **never** treat the other branch's bookmark as proof both nodes exist. Run the joining transaction only after preconditions succeed.

### 12.3. Testing Routing and Failover

1. Connect via **neo4j+s://...** per cluster setup; run **executeRead** and **executeWrite**.
2. Inspect driver or cluster logs/metrics to confirm queries hit appropriate roles and routing tables refresh.
3. In an administrator-approved test environment, trigger a leader switch or pause a member to observe transient errors, retries, and recovery.
4. Verify every **advertised address** resolves from the application host/container, even after failover.

**Never test failover directly in production without an operational plan.** Do not use **bolt://** URIs to evaluate routing, since the driver connects directly to one member.

### 12.4. Metrics to Measure

- p50/p95 latency of **read-after-write** versus independent reads without bookmarks.
- Retry rates on **executeRead/executeWrite**, timeout errors, and routing errors.
- Time to detect unavailable members and refresh routing tables.
- Writer vs. reader load and latency, plus cluster replication health.
- Connection pool contention, unclosed sessions, and long-running transactions.

Disable bookmarks only when the workload genuinely **tolerates** reading lagging data. This is a **consistency requirement** decision, not merely a performance trick.

## 13. Common Design Mistakes

1. **Using `bolt://` to connect to a cluster needing automatic failover.** The Driver lacks routing to other writers/readers and breaks if that single target stops.
2. **Assuming commit makes every reader see data immediately.** Replicas need time to apply changes; bookmarks ensure dependent queries wait for the required state.
3. **Thinking sharing a Driver shares bookmarks across all Sessions.** Bookmarks are tracked per session or via an explicitly configured manager/handoff.
4. **Capturing bookmarks before commit.** Tokens must represent committed state, not in-flight mutations.
5. **Merging bookmarks from two separate databases.** Bookmarks are database-scoped, not cross-database sync tools.
6. **Running every query in `executeWrite` by default.** Read-only queries get routed as writes, overloading the writer.
7. **Using read mode for security.** Routing intent never replaces user READ/WRITE privileges.
8. **Using one global bookmark manager for all unrelated requests.** Adds unnecessary wait dependencies and inflates p95 latency.
9. **Calling external services inside retryable callbacks.** Retries duplicate side effects; use outbox/idempotency.
10. **Omitting the database name.** Triggers home-database discovery round trips and complicates routing.
11. **Not closing Sessions/Drivers.** Leaks connections/resources and starves the pool.
12. **Parsing bookmark strings as sequence numbers.** Bookmarks are opaque tokens; use only `Bookmark.value()`/`Bookmark.from()`.

## 14. Exercises and Scenario Questions

### Exercise 1 — Read-Your-Writes

Service A creates an `Order O-200` node, and service B immediately reads it on a reader. Explain why knowing **when A returned HTTP 200** is not enough for B to safely pick any reader, and sketch the flow passing the **Bookmark** from A to B.

### Exercise 2 — Two Independent Sessions

Write a Java method with two sessions. The first **MERGE**s a Customer and captures **lastBookmarks()** after commit. The second uses **withBookmarks(...)** and **executeRead(...)** to verify the newly created Customer. Explain when **BookmarkManager** should be used instead of manual handoff.

### Exercise 3 — Fan-In After Two Parallel Branches

Two workers create a Product and a Category in two independent transactions. A third transaction creates **(:Product)-[:IN_CATEGORY]->(:Category)**. List the preconditions to wait for and explain why passing only one bookmark can be insufficient.

### Exercise 4 — Choosing a URI

Given **neo4j+s://cluster.example**, **bolt+s://server-1.example**, and **neo4j+ssc://test.example**. Identify which use routing, which are direct, and their certificate verification requirements. Why should you not switch from **neo4j+s** to **bolt+s** to "fix" a routing error without fixing the root cause?

### Exercise 5 — Incident Analysis

After a leader switch, a Java application reports errors reaching **server-2.internal** even though the seed hostname works. Propose checks for DNS, advertised addresses, routing tables, and firewalls from inside the application container.

### Exercise 6 — Performance Trade-Off

An application runs 90% analytical report reads and 10% order-creation flows requiring immediate read-after-write. Would you share one bookmark across all requests or scope it to dependent chains? Describe how measuring p95 and consistency requirements guides the choice.

## 15. Summary

In Neo4j Java Driver, **bookmarks** allow a subsequent transaction to observe state committed by an earlier transaction, even when reads route to another cluster member. The Driver automatically tracks bookmarks within **a single Session** and through **executableQuery()**'s default manager; across independent sessions or services, the application must **pass bookmarks** or **share a BookmarkManager** where true dependencies exist.

Cluster connections require a **routing URI** in the **neo4j://** family (typically **neo4j+s://** with standard TLS), explicit **database** selection, **executeRead** for reads, **executeWrite** for writes, a long-lived Driver, and timely Session closure. Bookmarks guarantee **causal ordering** for linked operations; they do not replace ACID transactions, constraints, lost-update protection, cache invalidation, or cross-database synchronization.

### Official Documentation

- [Neo4j Java Driver Manual – Coordinate parallel transactions (bookmarks)](https://neo4j.com/docs/java-manual/current/bookmarks/)
- [Neo4j Java Driver Manual – Connect to the database and cluster](https://neo4j.com/docs/java-manual/current/connect/)
- [Neo4j Java Driver Manual – Advanced connection information](https://neo4j.com/docs/java-manual/current/connect-advanced/)
- [Neo4j Java Driver Manual – Run your own transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver Manual – Performance recommendations](https://neo4j.com/docs/java-manual/current/performance/)
- [Neo4j Java Driver Manual – Upgrade from older versions](https://neo4j.com/docs/java-manual/current/upgrade/)
- [Neo4j Java Driver API – SessionConfig.Builder](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/SessionConfig.Builder.html)
- [Neo4j Java Driver API – BookmarkManagers](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/BookmarkManagers.html)
- [Neo4j Operations Manual – Leadership and routing](https://neo4j.com/docs/operations-manual/current/clustering/setup/routing/)
