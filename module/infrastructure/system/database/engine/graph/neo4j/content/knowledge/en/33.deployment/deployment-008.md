# Post-Deployment Verification of Connectivity, Data, and Indexes

## 1. Why Does a Successful Deploy Not Mean the Application Is Ready?

In the **DATABASE_ENGINE_GRAPH_NEO4J** module, Neo4j is a **property graph** database storing nodes, relationships, properties, and query-supporting structures like indexes and constraints. Applications typically access the graph using **Cypher**, the **Java Driver**, or **Spring Data Neo4j (SDN)**. A single deployment can simultaneously change connection configs, application code, schema, data, and the Neo4j version.

A pipeline reporting **deployment SUCCESS** only proves the pipeline's own steps finished. It **does not guarantee**:

- The Java Driver can connect from the actual app runtime environment over DNS/TLS and routing.
- The application account has read/write privileges on the **right database**.
- Data migrated completely with the right tenants, relationship types, and directions.
- Indexes are **ONLINE** rather than **POPULATING** or **FAILED**.
- Critical Cypher queries use execution plans with acceptable cost.
- Once traffic opens, error rates, latency, and read-after-write behavior remain within targets.

This lesson belongs to the **Deployment** chapter and focuses on designing **post-deployment verification**: from endpoint checks to validating the graph, indexes, and real application experience. Every check must define **an expectation and an action on failure**, not just be a command run for show.

### 1.1. Three Core Questions

| Question | Required Evidence | Examples of Caught Failures |
|---|---|---|
| **Can we connect?** | Driver connects, authenticates, selects database, runs READ/WRITE per role | Stale password, TLS error, wrong URI, routing advertising internal hosts |
| **Is the data right?** | Golden queries, counts at controlled checkpoints, unique keys, relationships, and tenant scope | Migration missed edges, duplicate data, cross-tenant reads |
| **Are indexes ready?** | `SHOW INDEXES`, constraints, index state, `EXPLAIN`/`PROFILE`, query measurements | Index `FAILED`, still `POPULATING`, query doing full scan |

**Passing one column does not substitute for the other two.** For instance, **`driver.verifyConnectivity()`** can succeed while the application's database is not yet ONLINE or the user lacks node-read privileges. Conversely, an ONLINE database does not guarantee the Bolt/TLS endpoint is reachable from the app pod.

## 2. Verification Gates in Deployment Order

A concise yet thorough workflow has six gates:

~~~mermaid
flowchart TD
  A["G0: Lock version, backups, baseline"] --> B["G1: TLS/DNS/Bolt/routing and auth"]
  B --> C["G2: Database ONLINE and right privileges"]
  C --> D["G3: Data, relationships, invariants"]
  D --> E["G4: Constraints/indexes ONLINE, query plans"]
  E --> F["G5: Java Driver/SDN smoke and canary"]
  F --> G{"All gates PASS?"}
  G -->|"Yes"| H["Open controlled traffic + monitor"]
  G -->|"No"| I["Hold or halt rollout, investigate, fix/rollback"]
~~~

| Gate | Typical Owner | Exit Criteria |
|---|---|---|
| **G0 — Baseline** | DevOps/DBA and app team | Know exact deployed build, reconciliation source, and recovery plan |
| **G1 — Connectivity** | Pipeline running from app network | Real connection from app network succeeds |
| **G2 — Database readiness** | DBA and service owner | Right database/role, ONLINE status, appropriate privileges |
| **G3 — Graph data** | Business/data team | Critical invariants and migration reconciliation pass |
| **G4 — Schema/performance** | DBA, query team | Required indexes ONLINE, constraints accurate, key queries show no regression |
| **G5 — Application smoke** | Java/SDN team | APIs/repositories read accurate data; zero critical runtime errors |

Never open 100% traffic based solely on **G1**. If a gate fails, **classify the blocker** and retain test evidence so the same failure does not repeat on the next deploy.

## 3. Preparing the Baseline Before Verification

Systems may host multiple databases, tenants, and API versions. Before deploying, record clearly:

1. **Release:** app commit/tag, Neo4j Server version, Java Driver, Spring Data Neo4j, and APOC/GDS plugins if used.
2. **Target database:** real database name, database alias if any, cluster/standalone/Aura environment, and admin-provisioned endpoint.
3. **Required schema:** index names, index types, labels/relationship types, properties, constraints, uniqueness/key rules.
4. **Golden queries:** representative queries reading Customer, Order, relationships, directions, missing data, and tenant isolation.
5. **Recovery:** latest backup status, how to restore or roll back the release, and which migrations are irreversible.
6. **SLOs:** p95/p99 latency, error rate, request success rate, and memory/connection pool metrics.

**A baseline is not an arbitrary count taken beforehand and compared against live continuously-mutating data minutes later.** If production continuously creates new orders, **`count(Order)`** post-deploy can legitimately differ from baseline. Use snapshots/reconciliation checkpoints, stable test tenants, or invariants independent of raw row totals at a single instant.

### 3.1. Running Fixture Used Throughout This Lesson

In a **dedicated test database**, create a fixture including the case where multiple tenants share the same IDs. Do not run these **`CREATE`** statements multiple times on the same fixture or uniqueness constraints will trigger.

~~~cypher
CREATE CONSTRAINT demo_deploy_customer_key IF NOT EXISTS
FOR (c:DemoDeployCustomer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT demo_deploy_order_key IF NOT EXISTS
FOR (o:DemoDeployOrder)
REQUIRE (o.tenantId, o.orderId) IS UNIQUE;
~~~

~~~cypher
CREATE
  (c1:DemoDeployCustomer {
    tenantId: 'shop-a', customerId: 'C-1', active: true
  }),
  (c2:DemoDeployCustomer {
    tenantId: 'shop-a', customerId: 'C-2', active: true
  }),
  (c3:DemoDeployCustomer {
    tenantId: 'shop-b', customerId: 'C-1', active: true
  }),
  (o1:DemoDeployOrder {
    tenantId: 'shop-a', orderId: 'O-1', amountMinor: 15000
  }),
  (o2:DemoDeployOrder {
    tenantId: 'shop-a', orderId: 'O-2', amountMinor: 8000
  }),
  (o3:DemoDeployOrder {
    tenantId: 'shop-a', orderId: 'O-3', amountMinor: 3000
  }),
  (o4:DemoDeployOrder {
    tenantId: 'shop-b', orderId: 'O-1', amountMinor: 9000
  }),
  (c1)-[:DEMO_DEPLOY_PLACED]->(o1),
  (c1)-[:DEMO_DEPLOY_PLACED]->(o2),
  (c2)-[:DEMO_DEPLOY_PLACED]->(o3),
  (c3)-[:DEMO_DEPLOY_PLACED]->(o4);
~~~

Initial expectations: **3 Customers**, **4 Orders**, **4 `DEMO_DEPLOY_PLACED` relationships**. IDs **C-1** and **O-1** appear in both tenants, so any query omitting the **`tenantId`** filter can be caught by tests.

Diagram:

~~~mermaid
flowchart LR
  subgraph SA["Tenant shop-a"]
    CA1["Customer C-1"] -->|PLACED| OA1["Order O-1"]
    CA1 -->|PLACED| OA2["Order O-2"]
    CA2["Customer C-2"] -->|PLACED| OA3["Order O-3"]
  end
  subgraph SB["Tenant shop-b"]
    CB1["Customer C-1"] -->|PLACED| OB1["Order O-1"]
  end
~~~

**Use this fixture only in staging/test.** In production, replace **`DemoDeploy...`** labels with approved read-only queries matching the application's data contract; never seed synthetic test data and then wipe it with broad delete queries.

## 4. G1 — Checking DNS, TLS, Bolt, and Authentication

### 4.1. Distinguishing Routing URIs from Direct URIs

The Neo4j Java Driver connects over Bolt. The scheme determines **routing** and **TLS**:

| URI | Connection | When Appropriate |
|---|---|---|
| **`neo4j://host:7687`** | Routing enabled, no TLS by scheme | Properly configured internal test networks |
| **`neo4j+s://host:7687`** | Routing and TLS with trusted CA cert | Production clusters and Aura per provisioned URI |
| **`neo4j+ssc://host:7687`** | Routing, accepts self-signed certs | Tests with explicit certificate policies |
| **`bolt://host:7687`** | Direct to a single server | Inspecting one specific instance |
| **`bolt+s://host:7687`** | Direct with trusted CA TLS | Encrypted connection to a specific server |

In a cluster, use **`neo4j+s://`** (or the system-provided routing scheme) so the driver fetches the routing table, sends **`executeRead`** to eligible readers, and sends **`executeWrite`** to the database writer. Switching to **`bolt+s://`** to bypass routing errors may "temporarily work" against one server and then fail when leadership changes.

**Do not downgrade TLS verification to work around certificate errors in production.** Inspect hostname, certificate SAN/CN, CA truststore, certificate chain trust, and organizational policy.

### 4.2. Testing from the Exact Environment Where the App Runs

A laptop connecting to Neo4j does not prove the Java pod/container can connect. Test from **the actual application network** or a CI job sharing the same DNS, subnet, egress policy, and secret retrieval path.

| Check | What to Know | Common Symptoms |
|---|---|---|
| DNS | Does the hostname resolve from the app pod? | Unknown host |
| TCP/Bolt | Is the port permitted through firewall/NetworkPolicy? | Timeout, connection refused |
| TLS | Does the cert match hostname, CA, and validity window? | SSL handshake/verification failure |
| Auth | Are account, password, and token valid? | Authentication failure |
| Routing | Are addresses **advertised** by the cluster reachable from the app? | Seed connects, then routing/driver times out |
| Database | Does the database name or alias exist and match? | Database not found, query hits wrong database |
| Permissions | Does the app role have read/write privileges on target labels/properties? | Forbidden/permission error during queries |

If a node in the routing table advertises an internal hostname unresolvable from the pod, the driver connects to the seed yet fails to reach remaining members. The root cause is **DNS/advertised address/networking**, not Cypher syntax.

### 4.3. Java Driver: Verifying Real Connectivity

**`GraphDatabase.driver(...)`** mainly initializes the driver object. Network connections are usually opened **lazily**; calling **`verifyConnectivity()`** actively tests connectivity.

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;

String uri = System.getenv("NEO4J_URI");
String user = System.getenv("NEO4J_USERNAME");
String password = System.getenv("NEO4J_PASSWORD");

try (Driver driver = GraphDatabase.driver(
        uri, AuthTokens.basic(user, password))) {
    driver.verifyConnectivity();
    System.out.println("Neo4j connectivity OK");
}
~~~

**Never** hard-code passwords or print secrets to the console. In Spring Boot, create **one shared Driver** managed by the framework; never instantiate a new Driver per HTTP request. Driver is thread-safe and relatively expensive; Session is lightweight yet **not thread-safe** and must be closed.

This succeeding call is only **connectivity-level evidence**. It **does not** prove the database is right, the data contract holds, indexes are ONLINE, or a business query can execute.

## 5. G2 — Checking the Right Database and Serving Status

### 5.1. `SHOW DATABASES` on Neo4j Enterprise

With **Neo4j Enterprise** and appropriate admin/inspection privileges, run in the **`system`** context:

~~~cypher
SHOW DATABASES
YIELD name, currentStatus, requestedStatus, access, statusMessage
WHERE name = 'neo4j'
RETURN name, currentStatus, requestedStatus, access, statusMessage;
~~~

Illustrative expected output:

~~~text
name     currentStatus  requestedStatus  access       statusMessage
neo4j    online         online           read-write   ""
~~~

**Reading the fields accurately:**

- **`requestedStatus`**: desired administrative state, e.g., **`online`**.
- **`currentStatus`**: actual state, which may be **`starting`**, **`store copying`**, **`offline`**, **`dirty`**, **`quarantined`**, or **`online`**.
- **`access`**: whether the database is **`read-write`** or **`read-only`**; a writing application must not be marked ready if the database is unexpectedly read-only.
- **`statusMessage`**: details on errors or state transitions.

**`CREATE/START DATABASE`** admin commands can return before the database is actually ONLINE because state transitions can be **asynchronous**. Pass the gate only once actual status satisfies workload needs. If a database is store copying, wait/alert per policy—never drop or restore before investigating.

**Edition note:** listing/administering multiple databases and detailed **`SHOW DATABASES`** columns are **Enterprise Edition** features in the operations docs. In Community or Aura environments with restricted admin privileges, verify using provider-supported observability tools and **execute a read query against the actual database**; never treat lack of `SHOW DATABASES` privileges as proof the database is down.

### 5.2. Explicitly Selecting the Database in Java Driver

~~~java
import org.neo4j.driver.SessionConfig;

String dbName = System.getenv("NEO4J_DATABASE");
try (var session = driver.session(
        SessionConfig.forDatabase(dbName))) {
    String database = session.executeRead(tx ->
        tx.run("CALL db.info() YIELD name RETURN name")
          .single().get("name").asString());
    System.out.println(database);
}
~~~

**`CALL db.info() YIELD name RETURN name`** verifies which database actually serves the query rather than guessing from the home database. The application should compare it against the configured target database; log only the database name, never passwords.

When using multi-database and aliases, distinguish **client-side name/alias** from the real underlying database Neo4j routes to. The Java example in section 8 checks against the real database name; if **`NEO4J_DATABASE`** intentionally uses an alias, validate against the **approved target database name** rather than strict alias-string equality. What matters is that queries are served from the approved dataset.

### 5.3. Least Privilege Must Be Tested Using the Application Account Itself

An admin succeeding with a Cypher query **does not prove** the API account has permission to run it. Test using the deployed credentials or impersonation:

~~~cypher
MATCH (c:DemoDeployCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})
RETURN c.customerId AS customerId;
~~~

If zero rows return, distinguish **missing data**, **role unable to see nodes/properties**, or **wrong parameters**. On Neo4j Enterprise with fine-grained privileges, **`TRAVERSE`** and **`READ`** privileges filter what a user sees. **`RETURN 1`** does not test graph read permissions.

WRITE verification with the app account should run only in **staging** or via a thoroughly designed canary—never create ad-hoc test nodes in production and wipe them with broad label deletes.

## 6. G3 — Verifying Data, Relationships, and Business Integrity

### 6.1. Golden Query Check by Business Key

On the section 3 fixture, query Orders for a Customer:

~~~cypher
MATCH (c:DemoDeployCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})-[:DEMO_DEPLOY_PLACED]->(o:DemoDeployOrder)
RETURN o.orderId AS orderId, o.amountMinor AS amountMinor
ORDER BY orderId;
~~~

For **`tenantId = 'shop-a', customerId = 'C-1'`**, expected:

~~~text
O-1   15000
O-2    8000
~~~

For **`shop-a / C-2`**, expect **`O-3`**; for **`shop-b / C-1`**, expect **`O-1`** of **`shop-b`**, excluding `shop-a` orders.

**Never omit `tenantId`** in `MATCH` when business rules require tenant isolation. A query that looks "fine" on small data will leak cross-tenant orders as soon as two tenants share customer IDs.

### 6.2. Count Checks in Fixed-Fixture Environments

~~~cypher
MATCH (c:DemoDeployCustomer)
RETURN count(c) AS customers;
~~~

~~~cypher
MATCH (o:DemoDeployOrder)
RETURN count(o) AS orders;
~~~

~~~cypher
MATCH (:DemoDeployCustomer)-[r:DEMO_DEPLOY_PLACED]->
      (:DemoDeployOrder)
RETURN count(r) AS placedRelationships;
~~~

Expected **`3, 4, 4`** respectively, **only when the fixture is immutable**. In continuously written production, raw counts serve only as **one signal** alongside snapshots/manifests; never compare totals across two different timestamps as a rigid PASS/FAIL gate.

### 6.3. Checking Duplicate Identifiers and Missing Keys

~~~cypher
MATCH (o:DemoDeployOrder)
WITH o.tenantId AS tenantId,
     o.orderId AS orderId,
     count(*) AS copies
WHERE copies > 1
RETURN tenantId, orderId, copies;
~~~

Expected **zero rows**. Also check:

~~~cypher
MATCH (o:DemoDeployOrder)
WHERE o.tenantId IS NULL OR o.orderId IS NULL
RETURN count(o) AS ordersMissingId;
~~~

Expected **0**. A **uniqueness constraint** protects identifier values when present, but **does not automatically require every node to carry those properties**; write policies or **key/existence constraints** where edition permits must enforce that.

### 6.4. Checking Relationship Direction and Tenant Consistency

~~~cypher
MATCH (c:DemoDeployCustomer)-[r:DEMO_DEPLOY_PLACED]->
      (o:DemoDeployOrder)
WHERE c.tenantId <> o.tenantId
RETURN count(r) AS crossTenantRelationships;
~~~

Expected **0**. Check Orders lacking exactly one source Customer:

~~~cypher
MATCH (o:DemoDeployOrder)
OPTIONAL MATCH (c:DemoDeployCustomer)-[:DEMO_DEPLOY_PLACED]->(o)
WITH o, count(c) AS placedBy
WHERE placedBy <> 1
RETURN o.tenantId AS tenantId,
       o.orderId AS orderId,
       placedBy;
~~~

Expected **zero rows** if the domain requires every Order to have exactly one placing Customer. **`count(c)`** counts matching links, so it also catches duplicate relationships between the same two nodes. However, if the business allows multiple Customers per Order, adapt the invariant accordingly.

**Watch out for NULL:** **`c.tenantId <> o.tenantId`** misses cases where one side lacks `tenantId`. Pair it with **`IS NULL`** checks for both Customer and Order if the data contract requires them.

### 6.5. Verifying Two-Phase Migrations

Suppose the old version stored **`o.legacyCustomerId`** while the new version uses **`DEMO_DEPLOY_PLACED`** relationships. During the transition rollout:

1. Run the old query on property-based data.
2. Run the new query on migrated relationships.
3. Compare **business key sets** and related properties, not just total row counts.
4. Check Orders missing relationships, cross-tenant relationships, and records whose Customer is missing.
5. Remove the old property only after all writers/readers have switched and reconciled.

If migration runs in batches and the final batch fails, committed data may sit **half-old, half-new**. Rollouts must support **controlled dual-read/dual-write** or pause dependent features during transition.

### 6.6. Verify Using Causal Checkpoints, Not Luck

In a cluster, a read query routed to a reader might not yet see a transaction just committed on the writer unless sessions are causally chained. When a smoke test writes a canary and immediately reads on a reader, use **bookmarks** within the same Session or pass bookmarks across Sessions; never rely on arbitrary **`Thread.sleep`** calls.

In environments where independent app requests accept eventual consistency, forcing global bookmarks everywhere is unnecessary. Conversely, for APIs creating an Order and immediately reading it back, ensuring **read-your-writes** is part of the data contract to verify.

## 7. G4 — Verifying Constraints and Indexes Post-Migration

### 7.1. `SHOW CONSTRAINTS`: Are Required Constraints Present?

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
WHERE name STARTS WITH 'demo_deploy_'
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;
~~~

On the fixture, expect **`demo_deploy_customer_key`** and **`demo_deploy_order_key`**, both uniqueness constraints on the exact property pairs. If the app contract requires business keys to be both **present and unique**, evaluate **node key** constraints (Enterprise) or equivalent checks; never assume uniqueness implies `NOT NULL`.

**Privilege note:** **`SHOW CONSTRAINTS`** requires appropriate privileges. A restricted API account may **not be allowed** to inspect metadata; schema verification pipelines should use a dedicated operational role instead of granting admin privileges to the app.

### 7.2. `SHOW INDEXES`: `ONLINE`, Not `POPULATING`

~~~cypher
SHOW INDEXES
YIELD name, type, state, populationPercent,
      entityType, labelsOrTypes, properties, owningConstraint
RETURN name, type, state, populationPercent,
       entityType, labelsOrTypes, properties, owningConstraint
ORDER BY name;
~~~

Common states:

| State | Meaning | Post-Deploy Decision |
|---|---|---|
| **ONLINE** | Index built and ready to serve | Proceed to query verification |
| **POPULATING** | Index currently building from existing data | Not PASS if queries depend on this index for SLOs |
| **FAILED** | Index creation or maintenance failed | FAIL gate; inspect `failureMessage`, logs, and resources |

**`populationPercent = 100`** is only a secondary hint; the readiness criterion is **`state = ONLINE`**. For constraint-backed indexes, **`owningConstraint`** identifies the constraint it backs.

Different index types serve different purposes: **RANGE**, **TEXT**, **POINT**, **FULLTEXT**, **VECTOR**, **LOOKUP**. Never replace a RANGE index with LOOKUP and assume property queries stay just as fast. For full-text/vector indexes with distinct update/consistency mechanics, verify further with **real functional queries**.

### 7.3. Waiting for Indexes with an Explicit Timeout

If a migration just added an index, wait for it to come ONLINE via procedure:

~~~cypher
CALL db.awaitIndex('demo_deploy_order_key', 300);
~~~

or wait for all indexes:

~~~cypher
CALL db.awaitIndexes(300);
~~~

Both procedures take a timeout in seconds. **Never wait indefinitely** in a pipeline; if the timeout expires, mark the gate failed/blocked and inspect whether the index is still `POPULATING` or `FAILED`. **`db.awaitIndexes()`** may wait on indexes unrelated to your release; when only one critical index matters, use **`db.awaitIndex(...)`** with its approved name.

**Check procedure execution privileges** and server/edition support; if unavailable, poll **`SHOW INDEXES`** on a schedule with an explicit timeout and exit condition.

### 7.4. An `ONLINE` Index Does Not Prove Queries Actually Use It

Run **`EXPLAIN`** with the business query and representative parameters:

~~~cypher
EXPLAIN
MATCH (o:DemoDeployOrder {
  tenantId: $tenantId,
  orderId: $orderId
})
RETURN o.amountMinor AS amountMinor;
~~~

The planner may pick **`NodeUniqueIndexSeek`**, **`NodeIndexSeek`**, or another access path depending on constraints, data, version, and statistics. The goal is confirming **a selective access path**, not forcing identical operator names across every version.

**`EXPLAIN` does not execute the query**, whereas **`PROFILE`** executes it for real:

~~~cypher
PROFILE
MATCH (o:DemoDeployOrder {
  tenantId: $tenantId,
  orderId: $orderId
})
RETURN o.amountMinor AS amountMinor;
~~~

For **read-only queries**, `PROFILE` is great for inspecting **`Rows`**, **`DB Hits`**, page cache, and memory where supported. **Never run `PROFILE` on migrations or production writes** just to view the plan, because `PROFILE` executes the query and mutates the graph.

### 7.5. Comparing Performance Against Baseline

| Metric | Meaning | Warning Sign |
|---|---|---|
| **`Rows`** per operator | Intermediate fan-out | One Expand step multiplying rows excessively |
| **`Estimated Rows`** | Planner estimate | Huge divergence from actual `Rows` |
| **`DB Hits`** | Data-access work performed | Sharp jump after missing index/plan shift |
| **`Index Seek/Scan`** | Access method | Shifting from seek to scan on very large data |
| **`p95/p99` latency** | User experience and SLO under representative load | Regression across repeated runs |
| **`Memory/Page cache`** | Resource pressure | Rising page cache misses, GC, or memory |

Never compare a query run on an idle laptop pre-deploy against a loaded production cluster post-deploy and blame the index. Compare fairly using identical parameter distributions, comparable data, documented versions, and representative load.

Do not enforce "every query must use an index seek." Queries returning large fractions of the graph may legitimately scan; base checks on **specific targets** for each critical query.

## 8. G5 — Application-Close Java Driver Smoke Test

A valuable smoke test verifies **connectivity + database + real query + business outcome** in one run. The Java snippet below is read-only, using a modern Java Driver (e.g., 5/6) and the section 3 fixture. It performs **zero** writes.

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.SessionConfig;

public final class Neo4jPostDeploySmoke {

    public static void main(String[] args) {
        String uri = requireEnv("NEO4J_URI");
        String username = requireEnv("NEO4J_USERNAME");
        String password = requireEnv("NEO4J_PASSWORD");
        String database = requireEnv("NEO4J_DATABASE");

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(username, password))) {

            driver.verifyConnectivity();

            try (var session = driver.session(
                    SessionConfig.forDatabase(database))) {

                var actualDb = session.executeRead(tx ->
                    tx.run("CALL db.info() YIELD name RETURN name AS db")
                      .single().get("db").asString());

                if (!Objects.equals(database, actualDb)) {
                    throw new IllegalStateException(
                        "Unexpected database: " + actualDb);
                }

                List<String> orderIds = session.executeRead(tx ->
                    tx.run("""
                        MATCH (c:DemoDeployCustomer {
                          tenantId: $tenantId,
                          customerId: $customerId
                        })-[:DEMO_DEPLOY_PLACED]->(o:DemoDeployOrder)
                        RETURN o.orderId AS orderId
                        ORDER BY orderId
                        """, Map.of(
                            "tenantId", "shop-a",
                            "customerId", "C-1"
                        ))
                      .list(record ->
                          record.get("orderId").asString())
                );

                if (!orderIds.equals(List.of("O-1", "O-2"))) {
                    throw new IllegalStateException(
                        "Data contract mismatch: " + orderIds);
                }
            }
            System.out.println("PASS: connection, database and data");
        }
    }

    private static String requireEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Missing required environment variable: " + key);
        }
        return value;
    }
}
~~~

This snippet is **illustrative code for staging with the fixture**. It is not a full Java project and assumes the Java Driver is on the classpath. In production, substitute approved golden queries/expected results; **never seed `DemoDeployCustomer` into a production database** just to make a test pass.

**Key points:** checking **`db.info()`** confirms the actual database accessed; **`executeRead`** verifies real graph read privileges; comparing **`O-1/O-2`** verifies both edge direction and tenant filtering. Using **`RETURN 1`** alone verifies zero data conditions.

### 8.1. Spring Data Neo4j Smoke Tests

For Spring Boot/SDN apps, add repository/service-level checks:

1. Start the application context with **stage/target** config.
2. Confirm **`Neo4jClient`/Repository** uses the right database and account.
3. Call a repository query with a custom **`@Query`** or critical relationship pattern.
4. Check entity mapping: business IDs, **`@Relationship`**, edge direction, nullable properties.
5. For write workflows, test in **staging** to verify transaction boundaries and rollbacks.

A **`driver.verifyConnectivity()`** call during bean init does not validate SDN mappings, converters, or repository queries changed in the release.

### 8.2. WRITE Canaries: Must Be Designed for Zero Side Effects

If real write permissions must be verified before opening traffic, prefer:

- **Staging** matching production schema and roles.
- If production allows canaries, identities must have a **dedicated namespace**, unique key, TTL, and **approved** cleanup workflow.
- Avoid labels/relationships that other apps, CDC, event listeners, or billing pipelines treat as real orders.
- Check side effects from indexes, triggers, APOC, service listeners, and logs before enabling write canaries.

**Rolling back a test transaction is not always harmless to external systems**: if a handler already emitted an email, queue message, or payment call before rollback, that side effect will not vanish. Never run ad-hoc `CREATE`/`DELETE` in production just to make a smoke report PASS.

## 9. Neo4j Clusters: Routing and Read-Your-Writes

### 9.1. Readers and Writers Must Serve Their Proper Roles

With a routing URI, **`executeWrite(...)`** routes to an eligible writer; **`executeRead(...)`** can use readers. In a cluster, **one database** has a leader and multiple read servers; exact roles are **per database**, not permanently fixed per machine.

Post-deploy, verify:

- Correct database name and members holding expected roles.
- Routing table refreshes after topology changes.
- **Advertised addresses** are reachable from the app network.
- Read queries do not accidentally all pile onto the writer.
- Connection pools, timeouts, retries, and latency stay within SLO.

If the app uses **`bolt://`** directly to one cluster host, simple queries may succeed while failovers break writes when leadership moves. Always test via the approved **routing URI**.

### 9.2. Do Not Confuse Replication Lag with Data Loss

A write followed by a read in a **different Session** can hit a reader that hasn't applied the prior transaction unless bookmarks are passed. The Java Driver manages bookmarks automatically for sequential transactions within one Session and for **`executableQuery()`** with a shared manager; across independent Sessions, use **`lastBookmarks()`/`withBookmarks()`** or a shared **`BookmarkManager`** when causal consistency is required.

In a read-after-write smoke test:

1. Wait for the **write transaction to commit**, not just callback start.
2. Attach the bookmark to the dependent read or reuse the same Session/manager.
3. Read from the right database with a permitted role.
4. Conclude data corruption only after ruling out routing/replication lag.

**Bookmarks do not refresh stale app caches** or fix migrations that missed relationships. They only ensure the server handling the dependent transaction has caught up to the state represented by the bookmark.

### 9.3. Distinguish Standalone from Cluster

A single Neo4j container in CI proves Cypher syntax and constraints work, yet **does not** prove cluster routing/failover. Certifying leader elections, server outages, or read-replica catch-up requires an authorized test cluster or dedicated rehearsal.

## 10. Verifying Plugins and Query Compatibility

If the app uses **APOC** or **Graph Data Science (GDS)**, verify post-deploy that required procedures/functions are actually loaded and callable by the right user:

~~~cypher
SHOW PROCEDURES
YIELD name
WHERE name STARTS WITH 'apoc.'
   OR name STARTS WITH 'gds.'
RETURN name
ORDER BY name;
~~~

~~~cypher
SHOW FUNCTIONS
YIELD name
WHERE name STARTS WITH 'apoc.'
RETURN name
ORDER BY name;
~~~

**Never check packages by assuming a JAR sitting in the plugins folder is loaded.** Match Neo4j/Plugin versions, **allowlists**, **`unrestricted`** where special procedures require it, **`EXECUTE PROCEDURE/FUNCTION`** roles, and data privileges.

Especially on **Neo4j Aura**, only a supported subset of plugins/procedures is available; you cannot drop in arbitrary JARs like self-managed. If the app depends on an unavailable APOC/GDS procedure, the gate must flag a functional blocker—never open unrestricted permissions across all namespaces in production.

### 10.1. Cypher 5 and Cypher 25

Starting with certain Neo4j releases from 2025 onward, systems support choosing between **Cypher 5** and **Cypher 25**; the default language may shift after an upgrade. When upgrading the server, run golden queries under the **pinned language** first, then test the newer language in a separate pass to isolate:

- Deprecated/incompatible syntax.
- Renamed functions/procedures.
- Changed planner/runtime behavior.
- Result differences caused by data/query changes rather than Cypher version.

Do not use the **`CYPHER 25`** prefix on servers that do not support it. Never compare execution plan text character-by-character across versions; compare semantics, access cost, and latency.

## 11. Observing After Controlled Traffic Opening

Once G0–G5 PASS in staging or on a canary, ramp traffic in stages (e.g., **5% → 25% → 100%** if infrastructure supports it) instead of flipping 100% immediately.

| Signal | Anomaly Indicator | Action |
|---|---|---|
| API success/error rate | Rising 4xx/5xx vs. baseline, excluding valid client errors | Categorize auth, query, constraint, and timeout errors |
| p95/p99 latency | Abnormal spike on critical queries | Inspect query plans, DB Hits, I/O, connection pool |
| Active/queued transactions | Long-running transactions, lock waits | Check contention, timeouts, and retries |
| Heap/page cache/GC | Rising memory pressure or cache misses | Review workload and resource sizing |
| Index state | New index not ONLINE or FAILED | Hold gate; inspect logs and resources |
| Cluster members | Member left cluster, router returns bad hosts | Check DNS/routing/leader and logs |
| Backup freshness | Backup job failed post-deploy | Halt destructive changes and protect data |
| Golden business invariants | Duplicate IDs, missing edges, or wrong tenants | Halt rollout; investigate migration/data correctness |

A release can pass every **short smoke test** yet regress after 30 minutes of real load. Maintain an **assigned observation window with human/automated owners**, rollback thresholds, and incident communication channels.

**Never automatically roll back schema/data migrations merely by reverting the app image** if the migration dropped properties or made backward-incompatible changes. Design **expand–migrate–verify–contract**, backups/restores, or compensating migrations beforehand.

## 12. Post-Deployment Triage Runbook

| Symptom | First Check | What NOT to Do |
|---|---|---|
| **Connection refused/timeout** | DNS, port 7687, firewall, pod env, driver logs | Raise timeouts indefinitely |
| **TLS handshake error** | Certificate, CA, hostname, system clock | Switch to unencrypted connections in prod |
| **Driver routing table error** | Advertised address, seed/router, DNS, cluster status | Force `bolt://` as a permanent fix |
| **Authentication failed** | Secret/version/role, DBMS auth | Put admin users/passwords in source code |
| **Database not found/offline** | Database name, alias, `SHOW DATABASES`/`statusMessage` | `DROP` database before investigating |
| **Query returns empty post-migration** | Right DB/tenant? data/edges migrated? role? | `CREATE` fake data so smoke passes |
| **Uniqueness violation** | Constraint on right key? duplicate requests or bad data? | `DROP` constraint to silence errors |
| **Index POPULATING** | Wait with timeout, inspect resources and progress | Open 100% traffic when SLO relies on the index |
| **Index FAILED** | `failureMessage`, index config, storage, and logs | Treat `populationPercent` as enough and ignore state |
| **Latency spike** | Read-only `EXPLAIN`/`PROFILE`, DB Hits, cache, load | Blame the driver without measuring |
| **Flaky read-after-write** | Sessions/bookmarks, replica lag, routing | Add random `Thread.sleep` calls |
| **APOC/GDS Unknown procedure** | Version, loaded plugin, allowlist, and privileges | Enable `unrestricted` on all namespaces |

### 12.1. Sample Release Decision Report

~~~text
Release: neo4j-app-2026-11
Database: <approved database>
Connectivity/Auth: PASS
Database status: PASS
Golden queries: PASS
Relationship/tenant invariants: PASS
Constraints and indexes: PASS
Read-only PROFILE vs baseline: PASS
Java Driver + SDN smoke: PASS
Canary monitoring: PASS
Decision: PROCEED
~~~

This is a report template, **not the output of a real deployment**. If any step could not run, mark it **BLOCKED**, stating the reason, owner, and remediation. **Never turn BLOCKED into PASS** by deleting the check line.

## 13. Automating Post-Deploy Verification in CI/CD

A pipeline can split verification into distinct jobs:

~~~text
Deploy application / database migration
  -> verify TCP/TLS/Bolt/routing from application network
  -> Java Driver verifyConnectivity and SELECT database
  -> DBA verifies currentStatus/read-write if privileged
  -> verify constraints/indexes ONLINE with timeout
  -> run golden read queries and business invariants
  -> read-only EXPLAIN/PROFILE on critical queries
  -> run SDN/API smoke with real service account
  -> open canary, monitor errors/latency/resources
  -> mark PROCEED or STOP/ROLLBACK per runbook
~~~

### 13.1. Writing Deterministic Assertions

Each script should return a **non-zero exit code** when a critical check fails. For example:

- **Database status** not ONLINE within timeout → **FAIL**.
- Missing required index or index `FAILED` → **FAIL**.
- Index still `POPULATING` after acceptable timeout → **FAIL/BLOCKED**, never force PASS.
- Duplicate business key within a tenant or Order without a valid Customer → **FAIL**.
- Data accurate yet p95 exceeds approved budget → **FAIL** per release policy.
- Unable to read metadata due to missing observability privileges → **BLOCKED**, delegate to a job with the right role.

Never create a single script running **`MATCH (n) DETACH DELETE n`** to reset production. Fixtures and test data must be managed outside real business data, ideally in isolated databases/pipelines.

### 13.2. Preserving Appropriate Evidence

| Evidence | Contents |
|---|---|
| **Deployment manifest** | App commit/tag, Neo4j version, database, driver/SDN/plugin versions |
| **Connection report** | URI type, TLS, routing, latency, auth result without secrets |
| **Schema snapshot** | `SHOW CONSTRAINTS`, `SHOW INDEXES`, and states |
| **Golden query report** | Case name, anonymized params, expected/actual, and PASS/FAIL |
| **Performance report** | `PROFILE`/DB Hits/Rows, sample count, p95, and dataset size |
| **Canary report** | Observation window, error rate, p95/p99, and decision |
| **Recovery note** | Backups, stop/rollback/restore plan, migration state |

Store reports per internal policy, **never exposing credentials or customer data**. When reproducing bugs, use synthetic or anonymized data and record all versions needed to replay.

## 14. Common Verification Design Mistakes

1. **Pinging port 7687 only.** Open TCP does not prove TLS, auth, or queries work.
2. **Calling `verifyConnectivity()` only.** Does not verify database, roles, or business Cypher.
3. **Testing with admin instead of the app account.** Masks RBAC/fine-grained privilege bugs.
4. **Not specifying the database explicitly.** Risks testing the wrong home/default database.
5. **Passing merely because an index exists.** `POPULATING` or `FAILED` indexes are not ready.
6. **Forgetting constraint-backing indexes.** Duplicate data can slip into migrations lacking proper constraints.
7. **Comparing only node counts.** Two datasets with equal counts can still differ in business keys or tenants.
8. **Running seed/demo data in production.** Causes side effects and pollutes the graph.
9. **Running `PROFILE` on production writes.** `PROFILE` actually executes the statement.
10. **Demanding identical query plans across versions.** Planners evolve while preserving accurate results and performance.
11. **Using `bolt://` on a cluster needing failover.** Loses leader/reader routing.
12. **Omitting bookmarks in read-after-write tests.** Mistakes replication lag for data loss.
13. **Ignoring plugins.** APOC/GDS may be missing or mismatched even when the database is ONLINE.
14. **Rolling back the app image when data is incompatible.** Migrated data cannot be undone simply by rolling back app code.
15. **Lacking STOP criteria.** System keeps opening traffic despite violated invariants or SLOs.

## 15. Hands-On Exercises

### Exercise 1 — Connection Analysis

An app in Kubernetes connects to **`neo4j+s://cluster.example`**, then times out reaching **`neo4j-2.internal`**. Explain why **`verifyConnectivity()`** or the first query sometimes succeeds while later requests fail. Propose checks for routing, advertised addresses, DNS, and NetworkPolicy.

### Exercise 2 — Index Verification

A release adds an index on **`DemoDeployOrder(tenantId, orderId)`**. **`SHOW INDEXES`** reports **`POPULATING 80%`**. Should you open 100% traffic if API SLOs depend on this index? Propose a timeout, **`db.awaitIndex(...)`** command, and handling if the index turns `FAILED`.

### Exercise 3 — Catching Tenant Leaks

On the section 3 fixture, intentionally omit **`tenantId`** in the query for Customer C-1. Compare results against the fixed query and explain why **counting total Orders = 4** cannot catch all tenant-isolation bugs.

### Exercise 4 — Relationship Invariants

Write Cypher to find Orders with **0** or **more than 1** incoming **`DEMO_DEPLOY_PLACED`** edges. Next, write a query detecting Customers and Orders from different tenants linked together. What do these checks catch that Order uniqueness constraints do not?

### Exercise 5 — Java Driver Smoke Test

Build a read-only Java program using **`GraphDatabase.driver(...)`**, **`verifyConnectivity()`**, **`SessionConfig.forDatabase(...)`**, and **`executeRead(...)`** to verify an exact list of business IDs. Explain why **`RETURN 1`** and running as admin are insufficient.

### Exercise 6 — Query Regression

Post-deploy, a query still returns the right Orders yet p95 triples. Compare **`EXPLAIN`/`PROFILE`**, DB Hits, Rows, indexes, parameter distributions, and background load. Why shouldn't you compare exact operator trees character-by-character across Neo4j versions?

### Exercise 7 — Rollout Decision

A release yields: connectivity PASS, database ONLINE, data PASS, constraints PASS, one index **`FAILED`**, Java read smoke PASS. Would you decide **PROCEED, BLOCKED, or ROLLBACK**? State what changes if that index is unrelated to the deployed workload.

## 16. Key Takeaways

A Neo4j deployment is ready only when the app **connects over the right network path, auth, and database**, the graph has **accurate data and business relationships**, indexes/constraints have **valid structure and status**, and core queries/APIs **meet SLOs**.

Memorable sequence:

**Baseline → DNS/TLS/Bolt/routing connectivity → database ONLINE + privileges → data and relationships → constraints/indexes ONLINE → `EXPLAIN`/`PROFILE` → Java Driver/SDN smoke → canary + monitoring → GO/NO-GO decision.**

Prefer **read-only** queries in production, run fixtures and write tests in staging, test with **the actual application account**, set timeouts on index waits, and archive PASS/FAIL evidence. Finally, keep backup/rollback plans aligned with migrations: **rolling back application code does not undo committed data changes**.

### Official Neo4j Documentation

- [Neo4j Java Driver Manual – Connection](https://neo4j.com/docs/java-manual/current/connect/)
- [Neo4j Operations Manual – Built-in procedures, db.info and db.awaitIndexes](https://neo4j.com/docs/operations-manual/current/procedures/built-in-procedures/)
- [Neo4j Java Driver Manual – Coordinate parallel transactions / bookmarks](https://neo4j.com/docs/java-manual/current/bookmarks/)
- [Neo4j Operations Manual – Show databases](https://neo4j.com/docs/operations-manual/current/database-administration/standard-databases/listing-databases/)
- [Neo4j Operations Manual – Monitor databases in a cluster](https://neo4j.com/docs/operations-manual/current/clustering/monitoring/show-databases-monitoring/)
- [Neo4j Cypher Manual – Show constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/list-constraints/)
- [Neo4j Cypher Manual – Show indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/list-indexes/)
- [Neo4j Operations Manual – Built-in procedures (db.awaitIndex/db.awaitIndexes)](https://neo4j.com/docs/operations-manual/current/procedures/built-in-procedures/)
- [Neo4j Cypher Manual – Query plans: EXPLAIN and PROFILE](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Neo4j Cypher Manual – Constraints and key constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/)
- [Neo4j Java Driver Manual – Run transactions](https://neo4j.com/docs/java-manual/current/transactions/)
