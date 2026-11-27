# Read/Write Query Routing and Driver-Side Load Balancing

When Neo4j runs on a single machine, a Java application can connect to one Bolt address and execute all queries there. When data is served by a **Neo4j cluster**, that approach fails to leverage cluster members properly: write transactions must reach a member capable of accepting writes, read queries can be served across multiple machines, and after a leader change, the valid write endpoint may differ from before. **The Neo4j Java Driver supports transaction-type routing and connection management**, relieving applications from maintaining a server list and picking a machine at random per query.

This lesson belongs to the **Clustering and Scaling** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. The module uses Neo4j to store property graphs consisting of nodes, relationships, indexes, and constraints, execute Cypher, ingest data, and integrate via the Java Driver or Spring Data Neo4j (SDN). This lesson focuses on **read/write routing, connection pooling, read load distribution, causal consistency via bookmarks, and error handling when cluster topology changes**.

> **Deployment scope:** The primary/secondary cluster, discovery, and routing concepts below are based on Neo4j Enterprise 5.x and compatible releases. Neo4j Community does not provide equivalent Enterprise clustering capabilities. Neo4j AuraDB hides many topology details and exposes endpoints according to service tier. Setting names, member selection, read-routing policies, and server-side routing capabilities can differ by version/edition. Read the documentation for your exact version before making assumptions about addresses, replication lag, or availability.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the difference between **direct connections** and **routing-aware connections**.
2. Distinguish the roles of **primary**, **secondary**, and **leader** members in a cluster’s read/write paths.
3. Use `neo4j://`, `neo4j+s://`, and `Session.executeRead`/`executeWrite` for their intended purposes.
4. Explain how the driver uses the routing table and connection pool; distinguish **load balancing** from **guaranteed throughput scaling**.
5. Apply **bookmarks** for reads after writes to mitigate cases where a replica has not caught up yet.
6. Test failover, network reachability, transient errors, idempotent writes, and load distribution from real applications.
7. Choose observability metrics, benchmark scenarios, and baseline configurations for Java/Spring Data Neo4j applications.

## 2. Why Must an Application Know It Is Running Against a Cluster?

Suppose a business graph contains:

~~~text
(:Customer {customerId: 'C01'})
    -[:PLACED]->
(:Order {orderId: 'O01', totalAmount: 120000})
~~~

The application performs two types of work:

- **Reads:** displaying order history and customer relationships.
- **Writes:** creating orders, updating statuses, adding relationships, or modifying properties.

A cluster can provide multiple places to serve reads, yet that does not mean **every machine independently accepts the same write operation**. Data must be written according to cluster consistency rules and then propagated to other members. If an application hardcodes a connection to a single member’s address, losing that member or switching leaders can break requests even while the cluster remains capable of serving.

~~~mermaid
flowchart LR
    APP["Java / SDN application"] --> DRIVER["Neo4j Java Driver<br/>routing + connection pool"]
    DRIVER -->|"WRITE"| P1["Primary P1<br/>current write leader"]
    DRIVER -->|"READ"| P2["Primary P2<br/>can serve reads"]
    DRIVER -->|"READ"| S1["Secondary S1<br/>serves reads if config allows"]
    P1 <-.->|"Consensus / replication"| P2
    P1 -.->|"Data synchronization"| S1
~~~

This diagram is a **conceptual model**, not a guaranteed topology or router/reader/writer list for every cluster. A real system may have multiple primaries, multiple secondaries, multiple databases, and differing read-selection policies.

## 3. Primary, Secondary, and Leader: Do Not Confuse Roles

| Component | Conceptual role | Key takeaway |
|---|---|---|
| **Primary** | Member participating in data maintenance and cluster consensus for a database | Does not mean **every primary is leader** simultaneously |
| **Database leader** | Member currently holding write-processing responsibility under cluster consensus | The leader can change after failover |
| **Non-leader primary** | Can serve read queries per routing/topology | Do not assume direct writes are accepted just like the leader |
| **Secondary** | Typically used to scale read capacity and maintain data copies without joining primary write quorum | Read eligibility, replication lag, and routing policy depend on version/config |
| **Router** | Address where the driver fetches routing information for reads/writes | A machine can serve as router alongside other roles; there is no separate “router database” |

In Neo4j, **each database in a cluster can have its own topology and leader**. Hence a statement like “machine P1 is always the writer for the entire DBMS” is unsafe. The Driver needs to know the **target database** and use the corresponding routing information.

### More Machines Do Not Automatically Multiply Every Capability

- Adding **read** capacity can scale total read queries when workload and networking align.
- **Write** load remains bounded by leader/consensus, locks, hardware resources, and update complexity.
- An overly broad graph traversal query can consume heavy CPU on **each** replica; adding replicas does not fix that Cypher query.
- A cluster with enough servers that lacks quorum, suffers cross-zone network loss, or has lagging replicas can still experience outages or latency errors.

Always distinguish **high availability (HA)** from **horizontal read scaling**: having multiple replicas does not automatically satisfy both uptime targets and expected throughput.

## 4. How Does a Routing URI Differ from a Direct URI?

The Neo4j Java Driver infers connection behavior from the URI **scheme**. That is the first configuration setting to verify.

| URI scheme | Direction | Typical use case |
|---|---|---|
| `neo4j://host:7687` | **Routing-aware** | Cluster connections, letting the driver use the routing table |
| `neo4j+s://host:7687` | Routing-aware + **TLS with trusted certificates** | Standard for managed endpoints like AuraDB and TLS environments |
| `neo4j+ssc://host:7687` | Routing-aware + TLS accepting self-signed certificates as supported by driver | Only consider in controlled test environments; never use in place of production security |
| `bolt://host:7687` | **Direct connection** to the specified address | Standalone instances, debugging one member, or explicit direct-connection designs |
| `bolt+s://host:7687` | Direct + trusted TLS | Direct TLS connection |

**Common mistake:** changing `neo4j+s://cluster.example.com` to `bolt://node-a:7687` because `node-a` responded quickly during testing. When `node-a` disconnects, the driver cannot leverage equivalent routing; if `node-a` is no longer the writer, write transactions can also fail or be redirected depending on server/version mechanics.

**Important distinction:** a routing-aware driver does not maintain open connections to every cluster member at all times. It fetches routing info when needed, maintains a connection pool, and opens connections according to workload demand.

### The Initial Endpoint Is Not the Complete Endpoint List

With `neo4j://cluster.example.com`, the initial hostname is typically used to **bootstrap** discovery. The driver receives addresses for **routers, readers, and writers** via the routing table. Consequently, even if the bootstrap endpoint is reachable, subsequent queries will fail if the advertised addresses **are unreachable from the application’s network**.

Especially in Docker, Kubernetes, NAT, or multi-zone deployments:

1. Verify that **advertised** hostnames and ports resolve and connect from **the machine running the application**.
2. Do not test only `localhost:7687` on the Neo4j host.
3. Verify TLS certificates cover the hostnames actually used.
4. Check firewalls, DNS, private routing, and reachability to every returned member.
5. Never hardcode internal container/pod addresses unreachable from outside the cluster.

The distinction between **listen address** and **advertised address** is critical: a server listens on an interface, yet must advertise an address real clients can reach.

## 5. How Does the Routing Table Work?

On a routing-aware connection, the driver fetches and refreshes a **routing table** for the database. Conceptually, the table contains:

~~~text
Database: neo4j
Routers: [R1, R2, ...]
Readers: [P2, S1, ...]
Writers: [P1, ...]
TTL: lifetime of routing information
~~~

This is an **illustrative** example, not actual query output, a fixed reader/writer count, or a guarantee of a complete list at every moment.

~~~mermaid
sequenceDiagram
    participant A as Application
    participant D as Java Driver
    participant R as Router / cluster
    participant P as Current writer
    participant S as Selected reader
    A->>D: Create Driver with neo4j+s://
    D->>R: Discover routing for database
    R-->>D: Routing table + TTL
    A->>D: executeRead(...)
    D->>S: Send read transaction
    S-->>D: Result
    A->>D: executeWrite(...)
    D->>P: Send write transaction
    P-->>D: Commit + bookmark
    Note over D,R: Routing refreshes as needed<br/>or when topology/TTL changes
~~~

### Three Events That Trigger Routing Changes

- **Leader switch:** the database’s writer address can change.
- **Member joining/leaving the cluster:** the reader/router sets can change.
- **Routing TTL expiration or connection failure:** the driver refreshes routing info according to its version’s algorithm.

**The routing table is not a static list in source code.** Never build a custom “routing table clone” out of hardcoded IP arrays maintained by the application unless you have a specialized integration requirement and consistent management mechanism.

### Does the Driver Always Split 50/50 Across Two Readers?

**There is no default guarantee of an exact split.** Server selection can depend on:

- The actual set of readers in that database’s routing table.
- Server-provided routing policies/capabilities.
- Connection pool state, connection lifetimes, and concurrency.
- How the specific **driver library version** selects servers.
- Transaction count, query duration, and request distribution from the application.

Even if two machines receive nearly identical **transaction** counts, CPU load can differ dramatically if one transaction expands 100 relationships while another traverses millions of edges. “Load balancing” should be evaluated by **latency, throughput, and actual resource usage**, not query count alone.

## 6. Distinguishing `executeRead` and `executeWrite`

The Java Driver provides **managed transaction functions**:

~~~java
session.executeRead(tx -> {
    // Read with Cypher and return result.
    return ...;
});
~~~

~~~java
session.executeWrite(tx -> {
    // Write with Cypher and commit when callback succeeds.
    return ...;
});
~~~

**Key implications:**

1. `executeRead` tells the driver the transaction uses **read access mode**, selecting an eligible read endpoint advertised by the cluster.
2. `executeWrite` requests **write access mode**, selecting an eligible write endpoint.
3. The Driver manages transaction lifecycle and **can retry** certain transient errors within configured limits.
4. Callbacks may run **multiple times**; never perform non-idempotent external side effects inside a callback.
5. Routing path and permission **to execute an operation** are two separate concerns. Access mode **does not replace Neo4j RBAC**.

If a transaction must **read and write atomically**, run those steps **inside the same `executeWrite`**. Never split them into `executeRead` followed by `executeWrite` merely to “spread load” when logic requires a shared snapshot/transaction.

### `executeRead` Does Not Magically Speed Up Queries

An unindexed `MATCH` query will still scan on a reader. A Cypher statement with a massive `ORDER BY` will still consume substantial RAM on a reader. **Routing selects where a query runs**, whereas **Cypher optimization** still depends on indexes, schema, cardinality, the planner, and data shape.

## 7. Complete Java Driver Example: Reading and Writing in a Cluster

Suppose the cluster has database `neo4j` and schema:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT order_request_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.requestId IS UNIQUE;
~~~

**Creating constraints is a separate schema-deployment step**, requiring an account with corresponding privileges. Do not grant runtime repositories schema-admin privileges just to execute `executeRead`/`executeWrite`.

The Java 17+ class below illustrates using **one long-lived Driver**, short-lived `Session`s, and parameterized queries. In Spring Boot environments, typically configure the Driver as a singleton bean rather than recreating it per request.

~~~java
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Config;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class ClusterOrderRepository implements AutoCloseable {
    private final Driver driver;
    private final String database;

    public record OrderView(String orderId, long totalAmount) {}

    public ClusterOrderRepository(
            String uri,
            String username,
            String password,
            String database) {
        Config config = Config.builder()
                .withMaxTransactionRetryTime(30, TimeUnit.SECONDS)
                .build();
        this.driver = GraphDatabase.driver(
                uri, AuthTokens.basic(username, password), config);
        this.database = database;
        driver.verifyConnectivity();
    }

    public List<OrderView> findOrders(String customerId) {
        try (Session session =
                driver.session(SessionConfig.forDatabase(database))) {

            return session.executeRead(tx -> tx.run("""
                    MATCH (c:Customer {customerId: $customerId})
                          -[:PLACED]->(o:Order)
                    RETURN o.orderId AS orderId,
                           o.totalAmount AS amount
                    ORDER BY orderId
                    LIMIT 100
                    """, Map.of("customerId", customerId))
                    .list(record -> new OrderView(
                            record.get("orderId").asString(),
                            record.get("amount").asLong())));
        }
    }

    public String createOrder(
            String customerId,
            String requestId,
            long totalAmount) {

        try (Session session =
                driver.session(SessionConfig.forDatabase(database))) {

            return session.executeWrite(tx -> tx.run("""
                    MATCH (c:Customer {customerId: $customerId})
                    MERGE (o:Order {requestId: $requestId})
                    ON CREATE SET
                        o.orderId = $requestId,
                        o.totalAmount = $amount,
                        o.status = 'NEW'
                    MERGE (c)-[:PLACED]->(o)
                    RETURN o.requestId AS requestId
                    """, Map.of(
                        "customerId", customerId,
                        "requestId", requestId,
                        "amount", totalAmount))
                    .single()
                    .get("requestId")
                    .asString());
        }
    }

    @Override
    public void close() {
        driver.close();
    }
}
~~~

Example initialization at the entry point:

~~~java
String uri = System.getenv("NEO4J_URI");
String user = System.getenv("NEO4J_USERNAME");
String password = System.getenv("NEO4J_PASSWORD");

try (var repository = new ClusterOrderRepository(
        uri, user, password, "neo4j")) {
    var orders = repository.findOrders("C01");
    System.out.println("Orders: " + orders.size());
}
~~~

Set `NEO4J_URI` to the cluster or Aura address provided by operations, such as `neo4j+s://graph.example.org` when TLS and routing are supported. Never store passwords in source code.

**Understanding the example accurately:**

- `findOrders` is routed as **READ** when the driver connects to a routing-aware cluster. It does not guarantee exclusively targeting secondaries; read servers are supplied by topology/routing.
- `createOrder` is routed as **WRITE**. Within one transaction, the query finds the Customer, upserts the Order, and creates the `PLACED` relationship.
- `MERGE` on `requestId` backed by a uniqueness constraint reduces duplicate creation when **requests are retried**. However, if two requests reuse the same `requestId` with different payloads, this code **does not automatically detect mismatches**: validate or compare payloads before returning success.
- `.single()` requires the query to return exactly one row. If `Customer` does not exist, `MATCH` yields zero rows and the method fails; applications should map that scenario to a clear business error.
- Managed transaction callbacks must be retry-safe. **Never send emails, call payment APIs, or increment external counters** inside a callback.
- `driver.verifyConnectivity()` only checks basic connectivity at call time; it **does not** prove every member is reachable, all privileges are right, or failover will succeed.

### One Driver, Many Sessions

~~~text
Driver (long-lived, thread-safe)
    |
    +-- Session request A --> executeRead --> reader chosen by routing
    |
    +-- Session request B --> executeRead --> reader chosen by routing
    |
    +-- Session request C --> executeWrite --> writer chosen by routing
    |
    +-- Connection pools managed internally by the Driver
~~~

A single `Driver` is shared safely across threads; a `Session` is **not thread-safe** and should be scoped to one unit of work. Never hold one global Session across concurrent HTTP requests. Nor should you instantiate a new `Driver` per query, as that loses pooling benefits and adds discovery/handshake overhead.

## 8. `SessionConfig.defaultAccessMode` with Implicit Transactions

Not every application uses managed transactions. When calling `session.run(...)` outside an explicit/managed transaction, the Java Driver runs an **implicit transaction** and uses the session’s `defaultAccessMode` to choose the access mode.

Read-only example:

~~~java
import org.neo4j.driver.AccessMode;
import org.neo4j.driver.SessionConfig;

SessionConfig readSessionConfig = SessionConfig.builder()
        .withDatabase("neo4j")
        .withDefaultAccessMode(AccessMode.READ)
        .build();

try (var session = driver.session(readSessionConfig)) {
    var ids = session.run("""
            MATCH (o:Order)
            RETURN o.orderId AS id
            LIMIT 20
            """)
            .list(r -> r.get("id").asString());
}
~~~

If mode is unspecified and `executeRead` is not used, implicit transactions may default to **WRITE mode** depending on driver behavior. Then a simple read-only `MATCH` query can be sent to the writer even though logically it only reads—a common design pitfall when expecting read scale-out.

**Distinction:** `SessionConfig.withDefaultAccessMode(...)` governs paths using the default mode, whereas `executeRead`/`executeWrite` **explicitly specify** access mode per transaction call. Never try to change managed transaction routing solely by toggling the session’s default mode.

### Implicit Transactions and Retries

Managed transactions provide proper retry handling for transient errors. Implicit transactions **do not carry the same guarantee** of full callback retry across driver versions; newer versions offer limited retry support in specific scenarios. With `CALL { ... } IN TRANSACTIONS` imports, earlier batches can commit before an outer query fails. **Never blindly retry an entire statement** if the operation is not idempotent.

## 9. Consistency: Read-After-Write When Reads Route to a Replica

Suppose a request flow executes:

~~~text
T0: executeWrite creates O02 on writer -> COMMIT
T1: executeRead fetches order list from another reader
~~~

If the reader receives data via replication and has not yet applied the commit from T0, the question is: **how do you guarantee the read query reflects at least the just-written record?**

The Neo4j Java Driver supports **bookmarks** to preserve **causal consistency**: a read transaction carrying a bookmark must wait to be served until the target data reaches the required state. The Driver can wait for a read server to catch up or fail if it cannot be satisfied within limits.

### 9.1. Read-After-Write Within the Same Session

A `Session` automatically tracks bookmarks from its own transactions. Example:

~~~java
try (Session session =
        driver.session(SessionConfig.forDatabase("neo4j"))) {

    session.executeWrite(tx -> {
        tx.run("""
                MERGE (o:Order {requestId: $requestId})
                ON CREATE SET o.orderId = $requestId,
                              o.totalAmount = 120000
                """, Map.of("requestId", "READ-AFTER-WRITE-01"))
                .consume();
        return null;
    });

    var record = session.executeRead(tx -> tx.run("""
            MATCH (o:Order {requestId: $requestId})
            RETURN o.orderId AS orderId
            """, Map.of("requestId", "READ-AFTER-WRITE-01"))
            .single());

    System.out.println(record.get("orderId").asString());
}
~~~

Within the same session, the driver maintains the necessary causal ordering between the committed write transaction and the subsequent read transaction. Even if the read query routes to a different server, bookmarks enforce **read-your-writes** within supported bounds and conditions.

**Bookmarks do not mean** every read across the entire cluster instantaneously sees the latest write. Nor do they replace single-transaction isolation analysis or commit-status checks after a dropped connection.

### 9.2. When Two Sessions Belong to Two Different Requests

An application has request A writing and request B reading in separate sessions. To maintain causal consistency **across Sessions**, you must **pass bookmarks** explicitly or use a version-appropriate **BookmarkManager**. Never assume that simply because two sessions share one `Driver`, every read automatically “sees the latest data” under all conditions.

Conceptual flow:

~~~text
Request A / Session A:
  WRITE -> COMMIT -> bookmark B

Request B / Session B:
  initialized with B or using an appropriately scoped shared bookmark manager
  READ -> requires results at least consistent with B
~~~

In multithreaded applications, shared bookmark managers must align with **business boundaries**. Sharing bookmarks unnecessarily can add consistency-wait overhead and create unintended coupling across unrelated flows. For workflows where reading slightly stale data is acceptable, omit passing bookmarks from unrelated writes.

### 9.3. Do Not Pin All Reads to the Leader Just Out of Fear of Stale Data

If business logic requires read-after-write, first design **causal consistency with bookmarks**. Forcing all reads onto the writer sacrifices load distribution and can overload the leader; for scenarios requiring stronger consistency guarantees, document the requirement and verify it on your actual version and topology.

## 10. Practical Load Balancing: Pools, Sessions, and Locality

### 10.1. Connection Pool

The Java Driver manages a **connection pool** to reuse Bolt connections to selected servers. Key settings to understand:

~~~java
import java.util.concurrent.TimeUnit;
import org.neo4j.driver.Config;

Config config = Config.builder()
        .withMaxConnectionPoolSize(100)
        .withConnectionAcquisitionTimeout(20, TimeUnit.SECONDS)
        .withMaxTransactionRetryTime(30, TimeUnit.SECONDS)
        .build();
~~~

Values **100**, **20 seconds**, and **30 seconds** are illustrative only—**not optimal defaults** for every system. Size them based on CPU, memory, concurrency, application instance count, query execution times, and Neo4j connection limits.

| Setting / concept | Meaning | Common mistake |
|---|---|---|
| Pool size | Limit on connections managed by the driver within config scope | Setting it huge to “increase throughput” when the server is already saturated |
| Acquisition timeout | Max wait time to acquire a connection | Mistaking connection acquisition timeouts for slow Cypher execution |
| Max transaction retry time | Budget for retrying managed transactions | Stacking extra retry layers, causing a request storm |
| Session lifecycle | Client’s logical unit of work | Sharing one Session across threads, holding Sessions open too long |
| Routing table refresh | Refreshing read/write endpoints | Pinning all connections to a single IP |

**Load balancing does not necessarily send each individual Cypher statement to a different machine.** A transaction requires consistency and typically remains bound to its chosen server for its lifetime. The Driver can also reuse an existing connection to a chosen server across multiple transactions.

### 10.2. Network Proximity and Read Distribution

When a cluster spans multiple zones/regions:

- A distant reader can increase **network latency** even when server CPU is idle.
- Cross-region traffic incurs cost and inflates p95/p99.
- Routing/locality policies depend on server and deployment edition; never assume the driver automatically “picks the closest machine” geographically.
- Queries returning millions of rows can be dominated by network transfer speed and Java object mapping time, not just DB Hits.

When reader locality by region is needed, check the **routing policy/region affinity** features of your Neo4j version and verify the routing table reflects your intended design.

### 10.3. Balanced Read Load Still Requires Correct Results

A test that only measures CPU percentages across two readers without validating outputs can miss bookmark bugs, missing relationships, or snapshot mismatches. When benchmarking, verify both **query correctness** and **data visibility windows**.

## 11. Spring Data Neo4j: Where Does Routing Happen?

Spring Data Neo4j uses the Neo4j Java Driver as its transport layer, so **routing URIs and Driver configuration** remain critical. Repositories and templates do not implement their own cluster “load balancer.”

Spring Boot example:

~~~yaml
spring:
  neo4j:
    uri: "neo4j+s://graph.example.org"
    authentication:
      username: "order_app"
      password: "${NEO4J_PASSWORD}"
  data:
    neo4j:
      database: "neo4j"
~~~

In real applications, supply URI, username, password, and database from environment variables or a secret manager. The YAML only illustrates structure; never store production credentials in source control.

### Transaction Rules at the Service Layer

In Spring Data Neo4j, mark read transactions with **read-only** semantics when appropriate:

~~~java
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<Order> findByCustomer(String customerId) {
        return repository.findByCustomerId(customerId);
    }

    @Transactional
    public void updateStatus(String orderId, String status) {
        repository.updateStatus(orderId, status);
    }
}
~~~

This is **illustrative service-layer code**; `OrderRepository` and the `Order` entity must be defined accordingly in the application. The exact mechanism by which SDN/Spring’s transaction manager translates `readOnly` into access mode and routing must be **verified on your running framework version**; never rely on the annotation alone as proof that queries hit the intended reader.

**Note especially:** if an outer transaction is already open in WRITE mode, calling a read-only repository inside it will not necessarily switch the active transaction to a reader. The service’s outer transaction boundary carries more weight than the repository method name.

### Using `readOnly` Does Not Grant Read-Only Security

`@Transactional(readOnly = true)` is a **transaction-management and optimization hint**, not a substitute for Neo4j RBAC. If the application user has WRITE privileges, the annotation alone does not make that account read-only. Enforce Neo4j privileges, separate credentials, and test write denial whenever role isolation is required.

## 12. When Failover Happens

### 12.1. Leader Switch and Routing Refresh

When the write leader encounters an issue, the cluster determines a new write target via consensus and member health. For a window of time, transactions may:

- Fail because the old connection is dead.
- Receive transient errors regarding routing, unavailable writer, or leadership transfer.
- Wait for the routing table to refresh and a new connection to establish.
- Be **retried** by managed transactions if the error category and retry time budget permit.

**Never promise uninterrupted success for every request.** HA reduces outage risk, yet failover still introduces **latency spikes** and some failed requests.

### 12.2. Distinguishing Three Error Categories

| Category | Examples / symptoms | Action |
|---|---|---|
| Connectivity / routing failure | `ServiceUnavailableException`, no eligible reader/writer address | Check DNS, TLS, advertised address, routing table, cluster status |
| Transient session / transaction error | `SessionExpiredException`, deadlocks, or leader switch | Managed transactions can retry; callbacks must be safe |
| Non-routing request error | Cypher syntax error, missing privilege, constraint violation | Fix query, role, or data; do not retry indefinitely |

With the Neo4j Java Driver, you can configure:

~~~java
Config config = Config.builder()
        .withMaxTransactionRetryTime(30, TimeUnit.SECONDS)
        .build();
~~~

**Retry timeouts do not guarantee success** if the cluster lacks quorum, the database is offline, or the network stays partitioned for an extended period.

### 12.3. Uncertain Commit Outcomes and Idempotency

A dangerous scenario:

~~~text
Application sends CREATE Order
         |
Server commits successfully
         |
Connection drops before client receives response
         |
Application assumes failure and resends CREATE Order
         |
Two Orders may be created if a unique business key is missing
~~~

**A connection failure does not prove the transaction failed to commit.** When designing cluster writes:

1. Generate a unique `requestId` or business key **before** the first attempt.
2. Create a uniqueness constraint on that key.
3. Prefer `MERGE` on the stable key rather than unconditional `CREATE` when deduplication is needed.
4. If the same `requestId` is reused with a different payload, **detect the conflict** instead of silently reporting success.
5. Never execute external side effects inside a retry callback; use an outbox or idempotent business workflow.

When writes span multiple steps involving money or external systems, **never treat a single Neo4j transaction as global exactly-once across the distributed system**.

## 13. Cluster Configuration That the Driver Must Be Able to See

For routing to work, it is not enough that the application reaches the seed/router. Every member advertised by the cluster must be reachable under the client’s network topology.

| Item | What to check? |
|---|---|
| Initial URI | Proper `neo4j://` or `neo4j+s://` for routing, accurate hostname |
| DNS | Both bootstrap hostname and advertised server addresses resolve from the app environment |
| TLS | Correct scheme, valid CA/certificate, matching hostname |
| Bolt port | Traverses firewalls, network policies, private endpoints/proxies |
| Advertised addresses | Do not return internal pod/container IPs unreachable from the app |
| Database selection | Driver targets the explicit database; does not rely on implicit defaults |
| Access privileges | Account has `ACCESS`, `MATCH`/`READ`, or `WRITE` per business role |
| Routing / cluster health | Members, leader, quorum, and database availability are healthy |
| Timeout / pool | Sized for workload without masking infrastructure defects |

### Case Where Seed Connects but Queries Fail

For example, an application outside Kubernetes connects to `neo4j+s://cluster.company.example` successfully, yet the routing table returns internal names like `neo4j-0.neo4j.svc.cluster.local` that external machines cannot resolve. Queries after discovery fail even though the initial handshake succeeded.

**Investigation path:** inspect Neo4j topology, listen/advertised addresses, Kubernetes service routing, DNS, and TLS from **the application’s actual network location**. Never mask this by adding infinite retries in the repository.

## 14. Observing Load Distribution: What Should You Measure?

A solid dashboard tracks both the **application** and **each Neo4j member**, broken down clearly by database and role.

| Metric | Source | Meaning |
|---|---|---|
| API latency p50/p95/p99 | Micrometer / OpenTelemetry | User-perceived slowness |
| Read/write requests/s | Service instrumentation | Query demand by type |
| Query latency, query errors | Neo4j metrics / query log | Slow or failing server-side executions |
| Read transactions per server | Per-member metrics/logs where available | Actual load spread |
| Write transactions / commit errors | Member/DB metrics | Whether leader or write path is overloaded |
| Driver connection pool acquisition time | App instrumentation if available | Detects pool saturation |
| Routing / connectivity errors | Exception classes and codes | Detects bad advertised addresses or failover |
| Transaction retries / timeouts | Driver/app logs, tracing | Quantifies failover impact on requests |
| CPU, heap, page cache, GC | Per member, per deployment capability | Measures actual reader and writer utilization |
| Replication/lag, cluster health | Admin tools / supported metrics | Indicates data freshness and HA health |

**Never fabricate metrics your environment does not export.** Some Aura tiers do not expose the same host-level visibility as self-managed Enterprise. If a metric is only available in another cluster edition, explicitly document the observability gap.

### Measuring Read Balance Properly

Do not compare only `count(read queries)`. Compare **the same time window** and query mix alongside p95/p99 latency and resource utilization per server. One reader receiving fewer queries can still burn more CPU if its queries are heavier.

To trace routing behavior, use **controlled Java Driver logging** in test environments, server query logs, and cluster status (if version/edition permits) to correlate connection targets. Do not leave full DEBUG driver logging or sensitive parameter logging enabled long-term in production.

## 15. Integration Testing and Controlled Failover Drills

You do not need to shut down a production Neo4j node to prove the driver performs routing. Use an **isolated test cluster** or authorized staging environment mirroring production topology.

### 15.1. Test Matrix

| Test case | How to execute | Expected outcome |
|---|---|---|
| Read with routing URI | Invoke `executeRead` across independent requests | Accurate results; opportunity to distribute load via routing |
| Write with routing URI | Invoke `executeWrite` with unique `requestId` | Exactly one record/relationship created per business rule |
| Read-after-write same Session | Write then read using Session’s implicit bookmark | Sees just-committed data |
| Read-after-write across Sessions | Pass bookmark/manager as designed | Causal ordering preserved where supported |
| One reader unavailable | Gracefully stop a test reader | Driver routes to remaining readers or bounds failures |
| Leader change | Trigger failover per staging runbook | Writes recover via routing; measure errors/latency during switch |
| Bad DNS/advertised address | Deliberately misconfigure test routing | Fails at discovery/connect rather than misreporting query bugs |
| Increased read load | Ramp read requests on fixed dataset | Measure per-member throughput/latency without demanding 50/50 split |
| Connection pool exhaustion | Cap pool in staging and raise concurrency | Observe acquisition latency/timeouts; verify clean handling |
| Write retry after network drop | Drop connection right at commit boundary | No duplicate orders thanks to `requestId`/constraints |

### 15.2. Step-by-Step Failover Drill

1. Record **topology/leader, Neo4j and driver versions, and database** before starting.
2. Start a **representative** read/write workload carrying request IDs and traces/metrics.
3. In staging only, simulate losing one reader and observe read paths and result accuracy.
4. Following approved staging procedures, trigger a controlled leader switch or writer failure.
5. Observe transient errors, retry budget, p95/p99, successful write counts, duplicates, and read-after-write behavior.
6. Restore topology, verify database health, replication/lag, constraints, and all completed transactions.
7. Record the **outage window**, observed RTO, and deviations from SLO; never claim “zero downtime” merely because the workload eventually resumed.

**When testing connection loss right at commit time**, never merely assert “an exception was thrown.” Read back by `requestId` and verify **the final data state**.

### 15.3. Test Semantic Correctness Before Measuring Performance

For graph data, `MATCH (c)-[:PLACED]->(o)` traversals and relationship aggregations must return exact answers. If a query is rewritten to “fit a reader” at the cost of dropping relationships or multiplying rows, a faster benchmark is **worthless**.

## 16. Common Misconceptions

| Misconception | Accurate view | How to fix |
|---|---|---|
| `bolt://` load-balances clusters like `neo4j://` | `bolt://` is direct; routing-aware schemes trigger proper discovery | Use URIs supplied by your cluster/Aura deployment |
| `neo4j://` keeps connections open to all members at once | Driver creates/acquires connections on demand | Monitor real metrics and pool behavior |
| `executeRead` always runs on a secondary | Reads route across advertised readers, which may include primaries | Inspect topology and routing policy |
| `executeWrite` sends writes to any primary | Writes must route to the eligible member / current leader | Rely on routing and transaction semantics |
| Two readers always receive equal query counts | No guarantee of exact query-count symmetry | Measure query cost, latency, and resources |
| Read-after-write always sees new data in any Session | Replicas can lag; bookmarks enforce causal consistency | Pass bookmarks when required |
| `SessionConfig.defaultAccessMode(READ)` makes all managed tx read-only | `executeRead`/`executeWrite` set their own access mode | Choose the API matching business intent |
| `@Transactional(readOnly=true)` is a security boundary | Read-only is a transaction hint, not RBAC | Configure actual Neo4j privileges |
| Retries fix every routing failure | Persistent DNS/TLS/quorum issues will not heal themselves | Monitor and repair topology/networking |
| Retry callbacks execute only once | Managed transactions can re-invoke callbacks | Keep external side effects out of callbacks |
| A three-machine cluster writes three times faster | Writes remain bounded by consensus/leader/locks | Benchmark reads and writes separately |
| HA means backups are unnecessary | HA does not undo logical data deletions | Maintain backup/restore and DR per RPO/RTO |
| Creating a Driver per request helps load balancing | Adds connect/discovery overhead and defeats pooling | Reuse Driver, keep Sessions short-lived |

## 17. Practice Exercises

### Exercise 1 — Choosing the Right URI

A Neo4j Enterprise cluster has three primaries and two secondaries. A Java app uses `bolt://node-1:7687`; when `node-1` stops, every request fails even though the cluster remains healthy. Where is the design flaw?

**Answer:** The application used a **direct URI** to a single node. It needs a routing-aware endpoint such as `neo4j://`/`neo4j+s://`, and every routing address advertised by the cluster must be reachable from the app. No URI removes the need to verify quorum, DNS/TLS, and privileges.

### Exercise 2 — Read Queries Overloading the Writer

A repository calls `session.run("MATCH ... RETURN ...")` with default `SessionConfig`. Every query is a read, yet the writer experiences high load. Explain how to fix this on the Java Driver side.

**Answer:** Prefer `session.executeRead(...)` to declare read transactions. If implicit transactions are required, set `SessionConfig.withDefaultAccessMode(AccessMode.READ)`. Verify the `neo4j://` URI, routing topology, and actual queries; never diagnose solely from writer CPU.

### Exercise 3 — Read-Your-Writes

Request A writes an `Order` node on the writer and commits. Request B uses a separate Session, reads from a reader, and occasionally misses the new Order. Describe the remediation and its trade-off.

**Answer:** Pass the causal bookmark from A to B or use an appropriately scoped `BookmarkManager`. The Driver uses it to require the reader to reflect at least that commit. This can increase wait latency, and does not imply every read across the cluster is globally linearized.

### Exercise 4 — Retries During Leader Switch

During failover, `executeWrite` retries. A developer placed an HTTP payment call and `CREATE (:Order)` inside the callback. What can go wrong?

**Answer:** The callback can execute multiple times, charging payments repeatedly; if the prior commit outcome was ambiguous, duplicate Orders can also be created. Separate external side effects, use unique request IDs, uniqueness constraints, `MERGE`, and an outbox/idempotency design.

### Exercise 5 — Misguided Load-Balancing Expectations

Two readers receive 600 and 400 queries respectively in one minute. The second reader sits at 90% CPU while the first is at 40%. Can you conclude the driver picked the “wrong” reader?

**Answer:** Insufficient evidence. The two query sets may differ drastically in cost, data/cache warmth, and concurrency; the driver does not guarantee uniform query counts. Compare workloads, latency histograms, CPU, Rows/DB Hits, and routing configuration.

### Exercise 6 — Seed Connects but Queries Fail

An app outside Kubernetes connects to the router, but after discovery receives endpoints like `neo4j-0.svc.cluster.local` that it cannot reach. What should you inspect before raising timeouts?

**Answer:** Inspect advertised addresses, DNS, TLS, and Kubernetes service/network policies between the app and every member returned in the routing table. Raising timeouts will not fix unroutable addresses.

### Exercise 7 — Deciding Transaction Boundaries

A service needs to read a balance and deduct funds atomically. Should you split `executeRead` on a reader to fetch the balance and `executeWrite` to deduct funds for “load balancing”?

**Answer:** No. If business rules require atomic read-modify-write, place the logic inside **one `executeWrite` transaction** with proper guards, concurrency control, retry deduplication, and constraints. Splitting across two transactions opens a race condition.

## 18. Official Documentation

- [Neo4j Java Driver Manual — Connect to the database](https://neo4j.com/docs/java-manual/current/connect/)
- [Neo4j Java Driver Manual — Advanced connection information](https://neo4j.com/docs/java-manual/current/connect-advanced/)
- [Neo4j Java Driver Manual — Transaction management](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver Manual — Bookmarks and causal consistency](https://neo4j.com/docs/java-manual/current/bookmarks/)
- [Neo4j Operations Manual — Clustering](https://neo4j.com/docs/operations-manual/current/clustering/)
- [Neo4j Operations Manual — Routing in a cluster](https://neo4j.com/docs/operations-manual/current/clustering/)
- [Neo4j Operations Manual — Monitoring](https://neo4j.com/docs/operations-manual/current/monitoring/)
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/)

`current` documentation pages evolve across releases. When working with Neo4j 5.x, Aura, or newer releases, always verify **URI schemes, driver APIs, access modes, routing tables, bookmarks, privileges, and topology** against your live configuration rather than assuming every deployment distributes reads and writes identically.

## 19. Key Takeaways

- **Routing URIs `neo4j://`/`neo4j+s://` enable the driver to discover read/write targets**; `bolt://` is primarily a direct connection and does not provide equivalent cluster routing.
- **`executeRead` and `executeWrite` declare transaction intent** so the driver picks the right path; they do not replace RBAC or Cypher optimization.
- **Load balancing does not guarantee equal request counts** nor make a high-DB-Hit query cheap.
- **Bookmarks enforce causal consistency**, especially when reads hit replicas after a commit; across sessions, pass bookmarks or use a business-scoped bookmark manager.
- **One long-lived Driver, many short-lived Sessions, and a measured connection pool** is the standard Java pattern.
- **Failover still causes brief errors and latency spikes**, requiring bounded managed-transaction retries, idempotent writes, and read-after-write/failover tests.
- **Observe routing via real metrics and logs**, verify network reachability to all advertised endpoints, and track both application and database SLOs.
