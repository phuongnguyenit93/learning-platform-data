# Creating MongoClient, Managing Its Lifecycle, and Reusing Connections in the MongoDB Java Driver

When a Java application needs to read or write to MongoDB, the first step is usually creating a **MongoClient** object. However, there is a very common architectural mistake: every HTTP request, every repository call, or every `insertOne()` operation creates a new `MongoClient` and closes it immediately afterward. This approach not only wastes connection setup time, but also spawns multiple **connection pools**, increases socket counts, adds authentication overhead, and triggers repeated MongoDB topology discovery.

The right design is usually much simpler: **create one MongoClient per MongoDB/cluster configuration within the application's lifecycle, share it across operations and threads, and close it when the application actually shuts down**. This object is not a single TCP socket. It is a client that manages topology, establishes and monitors connections, uses connection pools, and provides `MongoDatabase` / `MongoCollection` handles.

This lesson belongs to the **Java Driver** chapter and explains:

1. The role and cost of `MongoClient` compared to `MongoDatabase`, `MongoCollection`, and physical connections.
2. Creating a client via `MongoClients.create()`, `ConnectionString`, and `MongoClientSettings`.
3. Client lifecycle in CLI programs, long-running services, Spring Boot, batch jobs, and unit/integration tests.
4. Why **reusing MongoClient** is necessary and thread-safety boundaries when sharing across threads.
5. Connection pooling: on-demand connection creation, configuration, and behavior under overload.
6. URIs, timeouts, TLS, authentication, topology discovery, and their impact on connection counts.
7. Properly handling cursors, sessions, transactions, and shutdown.
8. Structuring repositories/services with dependency injection instead of creating clients inside individual methods.
9. Monitoring connection counts, measuring performance, and preventing pool exhaustion and connection leaks.
10. Practical Java Sync Driver examples, Spring Boot integration, exercises, and troubleshooting scenarios.

**Scope:** The primary examples use the **MongoDB Java Sync Driver**, package `com.mongodb.client`, and the `MongoClients.create()` API. The Reactive Streams Driver uses a different reactive model; certain details about threads/cursors and lifecycle should not be copied mechanically between the two drivers. When deploying, use a driver version compatible with your MongoDB server and consult that version's official documentation.

## 1. Big Picture: What Does MongoClient Manage?

A Java application may be structured as follows:

~~~text
Java application process
 |
 +-- MongoClient (lives for the duration of the app)
      |
      +-- Cluster / server topology discovery
      +-- Connection pool to appropriate servers
      +-- Monitoring and server selection
      +-- TLS / authentication configuration
      +-- Codec registry, read/write concern, retry options
      |
      +-- MongoDatabase("shop")
            |
            +-- MongoCollection("orders")
            +-- MongoCollection("customers")
            +-- MongoCollection("inventory")
~~~

Components to distinguish:

| Component | Nature | How to Create / Use |
|---|---|---|
| `MongoClient` | Owner of connection config, topology state, and pools | Create sparingly, reuse long-term, close at shutdown |
| `MongoDatabase` | Logical handle for a database with associated options | Obtain from client; lightweight; reuse if convenient |
| `MongoCollection<T>` | Logical handle for a collection and codec/options | Obtain from database; lightweight; safe to share |
| Physical connection | Socket/network connection to MongoDB server | Allocated and reused automatically by driver/pool |
| `MongoCursor<T>` | Cursor iterating over query results | Use within a short scope; close when finished |
| `ClientSession` | Client logical session, required for transactions | Create per workflow; do not share concurrently |
| `ClientSession` transaction | Context for a consistent sequence of operations | Commit/abort, handle errors, and close session |

**One MongoClient does not mean one TCP connection.** A single client can hold multiple sockets to different servers and execute multiple operations concurrently.

## 2. Why Should You Not Create a MongoClient per Request?

Suppose an API exposes an endpoint:

~~~http
GET /orders/ORDER-1001
~~~

Anti-pattern to avoid:

~~~java
// Anti-pattern for a web service handling many requests.
public Document findOrder(String orderId) {
    try (MongoClient client =
                 MongoClients.create(System.getenv("MONGODB_URI"))) {
        return client.getDatabase("shop")
                .getCollection("orders")
                .find(Filters.eq("_id", orderId))
                .first();
    }
}
~~~

Each call to `findOrder()`:

1. Creates a new client, new configuration, and associated resources.
2. Re-initializes server selection, pools, and required sockets.
3. May have to perform TLS handshakes, authentication, and wait for connections to become ready.
4. Closes the client immediately after the query, eliminating pool reuse.
5. Under concurrent requests, multiple clients and pools overlap simultaneously.

Beyond added latency, this makes it hard for the application to control the **total number of connections** to MongoDB. Closing each client properly does not make this strategy efficient.

### 2.1. The Right Way: Sharing the Client

~~~text
App start
   |
   v
MongoClient shared
   |
   +-- request 1 -> find order
   +-- request 2 -> insert order
   +-- request 3 -> update customer
   +-- scheduler -> aggregate daily report
   |
   v
App shutdown -> client.close()
~~~

Each request builds **queries/filters**, not a new `MongoClient`. `MongoCollection` objects are obtained from the shared client.

### 2.2. When Can You Have Multiple MongoClients?

Not every application is strictly limited to a single `MongoClient`. Multiple clients can make sense when:

- Connecting to **different MongoDB clusters**.
- Requiring **different credentials or TLS configurations** that cannot be safely shared.
- Having workloads that require **independent pools and timeouts**, measured and approved.
- A temporary migration process needs to read from an old cluster and write to a new cluster.

However, do not create a separate client per tenant simply because there is a `tenantId` field if all tenants share the same cluster/credentials and authorization requirements can be satisfied by proper server-side design.

**Principle:** one client per **meaningful connection configuration**, not one client per collection, repository, user, or HTTP request.

## 3. MongoDB Java Sync Driver Dependency

With Maven:

~~~xml
<properties>
    <mongodb.driver.version>5.x.y</mongodb.driver.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.mongodb</groupId>
        <artifactId>mongodb-driver-sync</artifactId>
        <version>${mongodb.driver.version}</version>
    </dependency>
</dependencies>
~~~

`5.x.y` is a placeholder: choose a **specific release** compatible with your runtime and server, using your project's dependency management or BOM. Do not copy `5.x.y` literally as a version number when building.

With Gradle (Groovy DSL):

~~~groovy
dependencies {
    implementation "org.mongodb:mongodb-driver-sync:${mongodbDriverVersion}"
}
~~~

If using Spring Boot and Spring Data MongoDB, the framework usually provides dependency management for the driver. Avoid declaring **two different driver versions** in the same dependency graph without checking compatibility.

Common classes:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
~~~

For the modern Java Sync Driver, do not use the legacy `new com.mongodb.MongoClient(...)` API pattern in new code if the project uses the `com.mongodb.client.MongoClients` namespace/API.

## 4. Creating a Simple MongoClient with a Connection String

### 4.1. Connecting to Local MongoDB

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;

public class HelloMongo {
    public static void main(String[] args) {
        try (MongoClient client =
                 MongoClients.create("mongodb://localhost:27017")) {
            MongoDatabase database =
                    client.getDatabase("java_learning");

            database.runCommand(new org.bson.Document("ping", 1));
            System.out.println("MongoDB ping succeeded");
        }
    }
}
~~~

`try-with-resources` fits here because **the entire program lifecycle executes a single short workflow**; after the `ping` command, the program exits and the client can be closed.

### 4.2. Using a MongoDB URI from an Environment Variable

~~~java
String uri = System.getenv("MONGODB_URI");
if (uri == null || uri.isBlank()) {
    throw new IllegalStateException("MONGODB_URI is required");
}

MongoClient client = MongoClients.create(uri);
~~~

Never hardcode passwords directly:

~~~java
// Do not put real username/password in source code.
String uri = "mongodb://admin:real-password@host:27017/app";
~~~

Credentials should come from the environment or a secret manager with restricted access. Never print the full URI to logs because it may expose passwords, usernames, or sensitive infrastructure details.

### 4.3. What Components Are in a URI?

Illustrative example (contains no real credentials):

~~~text
mongodb://user:ENCODED_PASSWORD@db1.example:27017,db2.example:27017/shop?replicaSet=rs0&authSource=admin&tls=true
~~~

| Component | Role |
|---|---|
| `mongodb://` | Standard connection scheme |
| `mongodb+srv://` | Uses SRV DNS discovery when deployment supports it |
| `user:password@` | Credentials; special characters must be properly percent-encoded |
| `db1,db2` | Seed host list for deployment discovery |
| `/shop` | Database in the URI; not necessarily the auth database |
| `replicaSet=rs0` | Requires/specifies the replica set name |
| `authSource=admin` | Database used for authentication, if needed |
| `tls=true` | Enables TLS |

For Atlas, use the **connection string provided for your cluster**, configure network access/TLS, and manage credentials properly. With `mongodb+srv`, DNS provides the host list and connection options; do not manually replace it with `localhost` or an arbitrary host.

### 4.4. The Constructor Is Not a Connectivity Test

~~~java
MongoClient client = MongoClients.create(uri);
~~~

Simply creating the client does not prove the application has:

- Selected an appropriate primary/secondary.
- Completed a TLS handshake.
- Authenticated successfully with MongoDB.
- Obtained read/write permissions on the target database.

The MongoDB Java Driver initializes and uses many resources/connections on demand. To verify connectivity, run an actual operation:

~~~java
client.getDatabase("admin")
        .runCommand(new Document("ping", 1));
~~~

**A successful ping** confirms a connectivity/command step; it does not prove the user has permissions on every collection. Critical business operations must be verified separately.

## 5. Creating MongoClient with MongoClientSettings

When you need to tune the pool, server selection, or application name, use **`MongoClientSettings.Builder`**:

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

import java.util.concurrent.TimeUnit;

public final class MongoClientFactory {
    private MongoClientFactory() {
    }

    public static MongoClient create(String uri) {
        ConnectionString connectionString = new ConnectionString(uri);

        MongoClientSettings settings =
                MongoClientSettings.builder()
                        .applyConnectionString(connectionString)
                        .applicationName("orders-service")
                        .applyToConnectionPoolSettings(pool -> pool
                                .maxSize(50)
                                .minSize(0)
                                .maxConnecting(2)
                                .maxWaitTime(5, TimeUnit.SECONDS))
                        .applyToClusterSettings(cluster -> cluster
                                .serverSelectionTimeout(
                                        5, TimeUnit.SECONDS))
                        .applyToSocketSettings(socket -> socket
                                .connectTimeout(
                                        3, TimeUnit.SECONDS))
                        .build();

        return MongoClients.create(settings);
    }
}
~~~

The numbers **50/0/2/5s/3s** are merely **illustrative values**, not universal defaults for every system. They must be tuned according to replica/pod count, concurrent request volume, operation duration, server resources, and latency targets.

Configuration order also matters: `applyConnectionString()` applies URI options to the builder; settings invoked **afterward** can override corresponding values. Choose one primary configuration source and avoid simultaneously setting `maxPoolSize` in the URI and `maxSize` in code without clear precedence rules.

### 5.1. How Do ConnectionString, Settings, and MongoClient Differ?

~~~text
ConnectionString
  -> Parses URI / hosts / auth / TLS / options

MongoClientSettings
  -> Client configuration (pool, topology, retry, concern, codec...)

MongoClients.create(settings)
  -> Creates the actual MongoClient with its own resource lifecycle
~~~

`ConnectionString` and `MongoClientSettings` are not the connection pool itself. The **`MongoClient`** created from settings is the object that owns the associated resources and must be closed at the right time.

### 5.2. Application Name

~~~java
.applicationName("orders-service")
~~~

Helps identify the client in MongoDB observability telemetry recorded during connection/handshake. Use traceable names like `orders-service`, `billing-worker`, or `monthly-report-job`; avoid embedding tokens, user emails, credentials, or sensitive data in the application name.

### 5.3. Avoid Configuring Dozens of Options You Do Not Understand

A configuration with:

~~~text
maxPoolSize=500
minPoolSize=500
maxConnecting=100
socketTimeoutMS=0
serverSelectionTimeoutMS=0
~~~

does not automatically make MongoDB faster. It can increase socket and memory usage and make errors harder to diagnose. Start with a minimal, measured configuration, then adjust based on a throughput/latency hypothesis and validate with metrics.

## 6. Lifecycle in Long-Running Applications

For HTTP services, consumers, schedulers, or backends running for hours or days, `MongoClient` should follow this lifecycle:

~~~text
SERVICE STARTUP
    |
    v
Create MongoClient once
    |
    v
Create repositories/services from client
    |
    v
Handle many operations concurrently
    |
    v
Stop accepting new work
    |
    v
Finish/cancel outstanding tasks safely
    |
    v
Close cursors/sessions as appropriate
    |
    v
mongoClient.close()
    |
    v
PROCESS EXIT
~~~

### 6.1. Provider Managing Client Ownership

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;

public final class MongoResource implements AutoCloseable {
    private final MongoClient client;

    public MongoResource(String uri) {
        this.client = MongoClients.create(uri);
    }

    public MongoDatabase database(String databaseName) {
        return client.getDatabase(databaseName);
    }

    @Override
    public void close() {
        client.close();
    }
}
~~~

A service bootstrap:

~~~java
MongoResource mongo = new MongoResource(
        System.getenv("MONGODB_URI")
);
try {
    MongoDatabase database = mongo.database("shop");
    OrderRepository orders = new OrderRepository(
            database.getCollection("orders")
    );

    // Start HTTP server, consumers, scheduled jobs...
    // Those components share OrderRepository/MongoResource.
} finally {
    // Runs only after all DB-using tasks have safely stopped.
    mongo.close();
}
~~~

The bootstrap code above only illustrates **ownership**. In a real web framework, do not put a `finally` block immediately after `startServerAsync()` if the start call returns immediately, because the client would be closed while the server is still serving requests.

### 6.2. Who Has the Authority to Call close()?

A straightforward rule:

> **The component that creates and owns MongoClient is responsible for closing MongoClient.** Repositories or services receiving `MongoClient` or `MongoCollection` via dependency injection **must not close** the shared resource on their own.

Bad example:

~~~java
public class OrderRepository {
    private final MongoClient sharedClient;

    public OrderRepository(MongoClient sharedClient) {
        this.sharedClient = sharedClient;
    }

    public void findSomething() {
        // ...
        sharedClient.close(); // Wrong: breaks connections for other services.
    }
}
~~~

A closed client cannot continue to be used by the application. If a restart is needed, a new client must be constructed at the proper ownership layer.

### 6.3. Shutdown Hook in Plain Java

In a Java daemon without a framework managing lifecycle, you can register a shutdown hook:

~~~java
MongoClient client = MongoClients.create(
        System.getenv("MONGODB_URI")
);

Runtime.getRuntime().addShutdownHook(new Thread(() -> {
    client.close();
}, "mongo-client-shutdown"));
~~~

This is a simple approach, though insufficient for every situation:

- Hooks are not guaranteed to run if the process is forcefully killed or power fails.
- Tasks using MongoDB should be stopped before closing the client.
- Avoid multiple components closing the same client uncoordinatedly.
- In Spring Boot, Jakarta EE, or a managed container runtime, let the **lifecycle container** manage shutdown rather than adding duplicate hooks.

### 6.4. Try-with-resources: Right and Wrong

**Right for a short-lived program:**

~~~java
try (MongoClient client = MongoClients.create(uri)) {
    client.getDatabase("admin")
            .runCommand(new Document("ping", 1));
}
~~~

**Wrong inside every HTTP request:**

~~~java
public Order loadOrder(String id) {
    try (MongoClient client = MongoClients.create(uri)) {
        // Reads one document and closes the entire pool.
    }
}
~~~

It is not that `try-with-resources` is bad, but that **the wrong scope was chosen**. The scope of `MongoClient` should match the owner's lifetime; the scope of cursors and sessions is much shorter.

## 7. Designing Repositories with Dependency Injection

A repository should receive `MongoCollection` from the bootstrap layer rather than knowing credentials or URIs itself.

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import org.bson.Document;

public final class OrderRepository {
    private final MongoCollection<Document> orders;

    public OrderRepository(MongoCollection<Document> orders) {
        this.orders = orders;
    }

    public Document findById(String orderId) {
        return orders.find(
                Filters.eq("_id", orderId)
        ).first();
    }

    public void markPaid(String orderId) {
        orders.updateOne(
                Filters.eq("_id", orderId),
                Updates.set("status", "PAID")
        );
    }

    public void insert(String orderId, String customerId) {
        orders.insertOne(
                new Document("_id", orderId)
                        .append("customerId", customerId)
                        .append("status", "NEW")
        );
    }
}
~~~

Bootstrap:

~~~java
try (MongoClient client = MongoClients.create(uri)) {
    MongoDatabase database = client.getDatabase("shop");
    MongoCollection<Document> collection =
            database.getCollection("orders");

    OrderRepository repository =
            new OrderRepository(collection);

    repository.insert("ORDER-1001", "CUSTOMER-7");
    System.out.println(repository.findById("ORDER-1001"));
    repository.markPaid("ORDER-1001");
}
~~~

In the program above, `MongoClient` lives for **the entire sequence of operations**. In a web service, the provider lives even longer and the repository is injected into shared handlers.

### 7.1. Repositories Do Not Need Separate Pools

~~~text
MongoClient shared
      |
      +--> MongoDatabase("shop")
              |
              +--> OrderRepository -> "orders"
              +--> CustomerRepository -> "customers"
              +--> InventoryRepository -> "inventory"
~~~

Each repository can hold its corresponding `MongoCollection<T>`. These handles are not separate physical connections and do not require `close()`.

### 7.2. Separating Data Access from Infrastructure Config

Centralize MongoDB configuration in one place:

- URI/KMS/TLS/credentials.
- Database name.
- Pool/timeouts/read/write concerns.
- Client initialization and shutdown.

Repositories are solely responsible for building filters, updates, and aggregations. This makes it easy to mock/test, swap environments, measure connection pools, and prevents dozens of classes from creating `MongoClient` instances independently.

## 8. Is MongoClient Thread-Safe?

**The Java Sync Driver's `MongoClient` is designed to be safely shared across multiple threads.** Handles like `MongoDatabase` and `MongoCollection` are also suitable for reuse and launching concurrent operations.

Example:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(8);
try {
    for (int i = 0; i < 100; i++) {
        final int orderIndex = i;
        executor.submit(() -> {
            String id = "ORDER-" + orderIndex;
            Document value = orders.find(
                    Filters.eq("_id", id)
            ).first();
            // Process value for this thread's request.
        });
    }
} finally {
    executor.shutdown();
}
~~~

In this example, **`orders`** is a `MongoCollection<Document>` obtained from a shared client. Ensure the executor finishes all tasks before closing `MongoClient`; `shutdown()` only stops accepting new tasks and does not wait for existing tasks to finish.

### 8.1. Objects That Must Not Be Arbitrarily Shared Across Threads

| Object | Rule |
|---|---|
| `MongoClient` | Thread-safe; safe to share |
| `MongoDatabase`, `MongoCollection` | Handles suitable for sharing |
| `ClientSession` | **Not thread-safe**; never use the same session concurrently across threads |
| `MongoCursor` | Use/close within operation scope; do not share across requests |
| Mutated `Document` | Mutable; do not modify concurrently without synchronization |
| `MongoClientSettings.Builder` | Used to build configuration at bootstrap, not a resource for multi-thread mutation |

**A thread-safe `MongoClient` does not mean every returned object is thread-safe.** Each request can create its own `Document`, `Bson` filters, cursors, and sessions as needed without creating a new `MongoClient`.

### 8.2. Does One HTTP Request Equal One Connection?

Not necessarily. A database operation checks out a connection from the pool while executing a command, then returns it to the pool. Exceptions include cursors/`getMore`, transaction/session pinning, streaming, or special topologies.

Do not assume every HTTP request is "assigned a fixed MongoDB socket" from start to finish. The driver coordinates pools per operation and runtime conditions.

## 9. Connection Pooling: MongoClient Is Not a Single Socket

When multiple threads perform MongoDB I/O, the Java Driver uses internally managed **connection pools**. A pool serves many operations over time, avoiding repeated socket openings, TLS handshakes, and authentication.

### 9.1. Basic Lifecycle of a Connection

~~~text
Thread A                       MongoDB Java Driver
   |                                  |
   |          execute find()          |
   +--------------------------------->|
   |                                  |
   |                      Select suitable server
   |                                  |
   |                      Checkout from its pool
   |                                  |
   |                         Connection available?
   |                           /          \
   |                         yes           no
   |                          |            |
   |                      Reuse        Open new if
   |                      socket       capacity allows,
   |                          |        otherwise wait
   |                          +------------+
   |                                       |
   |                           Send MongoDB command
   |                                       |
   |                           Receive response
   |                                       |
   |                           Return connection
   |                           to pool when eligible
   |                                       |
   <---------------------------------------+
           result / exception
~~~

The pool reuses valid connections. It does not guarantee that an operation will always use the exact same physical socket as the previous operation.

### 9.2. Pools Are Per Server, Not Just Per Client

In a multi-member replica set, the driver connects to and monitors servers in the topology. Total sockets do not simply equal the configured `maxPoolSize` value.

Conceptual view:

~~~text
MongoClient
   |
   +-- Server A -> operation connection pool
   +-- Server B -> operation connection pool
   +-- Server C -> operation connection pool
   +-- Monitoring/topology connections
~~~

Pools operate per **server/connection target** according to topology. Additional connections exist for monitoring. If an application runs 20 pods and each pod has one `MongoClient`, total sockets can be much higher than looking at a single client's `maxPoolSize` alone.

### 9.3. Pools Create Connections on Demand

If configured with:

~~~text
maxPoolSize = 100
minPoolSize = 0
~~~

do not assume creating `MongoClient` immediately opens 100 operational connections in MongoDB. Pools typically grow on demand up to configured limits; actual connection counts depend on load, server selection, and monitoring activity.

If `minPoolSize` is greater than 0, the driver can maintain a minimum number of connections according to policy and topology state. This helps reduce cold starts for some workloads, though it also increases baseline socket counts when many service replicas run concurrently.

## 10. Important Pool Parameters

| URI / Java Builder Option | Meaning | Impact to Observe |
|---|---|---|
| `maxPoolSize` / `maxSize()` | Maximum operation connections in the corresponding pool | Concurrent throughput, checkout waits |
| `minPoolSize` / `minSize()` | Minimum connections maintained per policy | Cold starts, baseline sockets |
| `maxConnecting` | Limits connections being established simultaneously in the pool | Pool ramp-up rate under traffic spikes |
| `maxIdleTimeMS` / `maxConnectionIdleTime()` | Max idle age before a connection may be removed from the pool | Idle sockets, stale connections |
| `maxLifeTimeMS` / `maxConnectionLifeTime()` | Maximum connection lifetime | Periodic connection recycling |
| `waitQueueTimeoutMS` / `maxWaitTime()` | Maximum time waiting to check out from the pool | Timeouts when pool is busy |

Builder/URI syntax can change or be deprecated across Java Driver versions. Names in the table illustrate the concepts; check the API for your exact version when applying them.

### 10.1. maxPoolSize Is Not the Maximum Request Count

If `maxPoolSize=50`, that does not mean the service can accept at most 50 HTTP requests. The service can accept thousands of requests while only a subset of MongoDB operations actively hold connections at the same moment; other tasks wait for checkout or are bounded at the application layer.

Conversely, one request might issue multiple sequential DB commands or run several operations in parallel. Measure **active/checked-out connections**, queue/wait latency, and throughput instead of converting HTTP RPS directly into `maxPoolSize`.

### 10.2. When the Pool Is Full

Suppose:

~~~text
maxPoolSize = 20
Connection checked out = 20
Incoming operation = 21st
~~~

The new operation does not create a 21st connection beyond the pool limit. It waits for a connection to be returned per wait-queue policy and errors if the wait timeout expires.

Pool saturation can be caused by:

- Genuine traffic spikes.
- Slow queries/aggregations holding resources for a long time.
- Long-running transactions.
- Improperly handled cursors/streaming.
- Unbounded parallel tasks lacking backpressure.
- Pool sized too small for actual concurrency.

**Increasing `maxPoolSize` is not always the right fix.** If the root cause is an unindexed query or long transaction, adding connections pushes even more slow work into MongoDB and worsens server overload.

### 10.3. maxConnecting Differs from maxPoolSize

`maxConnecting` limits how many **new connections can be established concurrently** for a pool while scaling up. It is not the long-term cap on concurrently active connections.

Illustrative example:

~~~text
maxPoolSize = 80
maxConnecting = 2
~~~

The pool can grow up to 80 connections when needed, but it will not open 80 sockets simultaneously. This acts as a throttle against connection establishment bursts.

### 10.4. Weighing minPoolSize with Many Pods

Suppose 40 service instances, each with multiple pools per topology, configure `minPoolSize=30`. Total maintained connections can become very large even under minimal traffic.

An application with uneven traffic should usually start with a low min pool size, measure cold-start impact, and raise it only if needed. Never set `minPoolSize=maxPoolSize` just to guarantee "the client is always fast."

### 10.5. Idle Time and Lifetime

Connections left idle too long can be dropped by proxies, firewalls, or load balancers. The driver has mechanisms to monitor and re-establish connections; idle/lifetime settings assist with recycling but do not replace proper network configuration.

Do not set an ultra-short lifetime just to "keep connections fresh" if it triggers dense TLS/auth handshake cycles and adds latency. Equally, do not keep connections indefinitely when environment conditions cause stale sockets without monitoring for stale-socket errors.

## 11. Timeouts: Many Different Kinds of Waiting

A request can spend time across distinct stages:

~~~text
Select server
      |
      v
Wait for pool connection
      |
      v
Establish socket/TLS if required
      |
      v
Send/receive MongoDB command
      |
      v
Fetch cursor batches
~~~

Therefore, do not group every error under a generic "MongoDB timeout" label.

| Timeout / Limit | What Does It Wait For or Bound? |
|---|---|
| Server selection timeout | Driver finding a suitable server per topology/read preference |
| Pool checkout wait timeout | Waiting for an available connection in the connection pool |
| Connect timeout | Establishing a TCP connection to the server |
| Socket read timeout / network timeout | Waiting on network I/O / response per driver policy |
| `maxTimeMS` per operation | Server-side processing time budget for eligible commands |
| Application/HTTP request timeout | Overall deadline at the web/application tier |
| Unified client-side timeout (CSOT) if supported | Overall per-operation time limit via driver API |

**Key point:** raising `serverSelectionTimeoutMS` does not fix pool checkout saturation; raising socket timeout does not make an unindexed query run fast.

### 11.1. Server Selection Timeout

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
        .applyConnectionString(new ConnectionString(uri))
        .applyToClusterSettings(cluster -> cluster
                .serverSelectionTimeout(5, TimeUnit.SECONDS))
        .build();
~~~

If the client cannot select an eligible node within the configured time, the operation fails. Causes include DNS issues, network failures, no primary available for writes, TLS errors, unstable topology, or wrong replica set configuration.

### 11.2. Checkout Timeout

~~~java
.applyToConnectionPoolSettings(pool -> pool
        .maxSize(50)
        .maxWaitTime(3, TimeUnit.SECONDS))
~~~

If the pool cannot supply a connection in time, the operation fails once the wait expires. Monitor **checked-out count**, queue wait latency, query duration, and concurrent operations.

### 11.3. Connect Timeout

~~~java
.applyToSocketSettings(socket -> socket
        .connectTimeout(3, TimeUnit.SECONDS))
~~~

Bounds socket establishment in the driver. If connect timeout expires, do not assume "MongoDB is missing an index": the operation did not even have an open network connection to run a query.

### 11.4. maxTime on a Query

~~~java
import java.util.concurrent.TimeUnit;

Document order = collection.find(
        Filters.eq("customerId", "CUSTOMER-7"))
        .maxTime(2, TimeUnit.SECONDS)
        .first();
~~~

`maxTime()` asks MongoDB to limit server-side execution time according to command semantics; it does not necessarily cover client-side time such as DNS, pool checkout, or network delays. For an end-to-end SLA, enforce application-level deadlines and consider **CSOT/unified timeout** if supported by your driver version.

### 11.5. Do Not Conflate Three Different Errors

~~~text
MongoTimeoutException: Timed out after waiting for a server
    -> check topology/server selection

Timed out waiting for connection from pool
    -> check pool saturation/checkout

Socket timeout during command
    -> check network/slow operation/timeout settings
~~~

Exact messages vary across driver versions, but the underlying root-cause categories are completely distinct.

### 11.6. Request-Tier Deadlines

If an HTTP gateway times out after 1 second while a MongoDB operation is allowed to wait 30 seconds, the server and backend keep holding resources after the caller has given up. Align deadlines consistently with SLAs, cancellation, and retry policies.

With the Sync Driver, a thread may block inside an operation. Do not assume canceling an external `CompletableFuture` immediately halts all driver I/O; rely on supported timeout/cancellation mechanisms and proper shutdown coordination.

## 12. Server Selection, Read Preference, and Topology

`MongoClient` understands MongoDB deployment types—standalone, replica set, or sharded cluster (via `mongos`/router)—through the URI and topology discovery.

### 12.1. Primary and Secondary

In a replica set, standard writes must target the primary. Reads can target the primary or secondaries depending on the configured **`ReadPreference`**.

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
        .applyConnectionString(new ConnectionString(uri))
        .readPreference(
                com.mongodb.ReadPreference.primary())
        .build();
~~~

A read preference like `secondaryPreferred` can route reads to secondaries under matching conditions, but introduces **replication lag** risk. Do not switch the entire system to secondary reads purely to offload the primary while ignoring consistency requirements.

### 12.2. Read Concern and Write Concern

`ReadConcern` and `WriteConcern` specify read and write durability/isolation guarantees. They can be configured at the client, database, collection, or operation level depending on the API.

~~~java
MongoDatabase database = client.getDatabase("shop")
        .withReadConcern(
                com.mongodb.ReadConcern.MAJORITY)
        .withWriteConcern(
                com.mongodb.WriteConcern.MAJORITY);
~~~

These return **handles with different options**; calling `withReadConcern()` or `withWriteConcern()` does not create a new `MongoClient` or a new pool.

### 12.3. Topology Changes While the Application Runs

During primary failovers, node restarts, or DNS updates, the driver rediscovers topology and selects appropriate servers. A long-lived `MongoClient` **is not permanently pinned to a single fixed host by default**.

Do not build logic that "creates a brand-new `MongoClient` on every request whenever failover happens" if errors are transient server-selection delays. Instead, use retry semantics aligned with business idempotency and driver capabilities.

### 12.4. Checking Connection Health

`client.getDatabase("admin").runCommand(new Document("ping",1))` is a simple probe. However, health checks should avoid:

- Repeatedly creating and closing new clients.
- Requiring every replica set member to be healthy at all times.
- Treating a successful ping as proof of write permissions.
- Blocking startup indefinitely if infrastructure conditions are not yet met.

Distinguish **liveness** (process is running), **readiness** (ready to serve primary workload), and **dependency health**, per your product's operational policy.

## 13. Cursors: Shorter Lifecycle Than MongoClient

A query can return many documents in batches. The Sync Driver provides `MongoCursor<T>` to iterate results, and cursors must be **closed when no longer needed**.

### 13.1. Iterating and Closing a Cursor

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import org.bson.Document;

public void processActiveOrders(
        MongoCollection<Document> orders) {

    try (MongoCursor<Document> cursor = orders.find(
            Filters.eq("status", "ACTIVE"))
            .batchSize(200)
            .iterator()) {

        while (cursor.hasNext()) {
            Document order = cursor.next();
            process(order);
        }
    }
}

private void process(Document order) {
    System.out.println(order.getString("_id"));
}
~~~

When the `try` block exits, the cursor is closed, even if processing throws an exception. **The shared `MongoClient` stays open** and continues serving other operations.

### 13.2. Iterators, Cursors, and Collection Handles Have Different Scopes

~~~text
MongoClient:     entire application lifetime
MongoCollection: reused among services/threads
MongoCursor:     one query iteration
Document:        one result / unit of work
~~~

Never call `mongoClient.close()` in place of `cursor.close()` at the end of a query.

### 13.3. Avoid Holding Cursors Across User Think Time

Do not store a `MongoCursor` in a singleton field so a later HTTP request can keep iterating. Server-side cursors can expire, bind to sessions, or break on topology changes, and multiple threads could touch the same cursor.

If pagination is needed, use query pages with proper **sort/index/keyset** pagination; do not hold a server-side cursor across multi-hour UI browsing sessions.

### 13.4. `first()` and `into()`

~~~java
Document one = orders.find(
        Filters.eq("_id", "ORDER-1001"))
        .first();
~~~

`first()` retrieves one element without requiring the service to iterate a long cursor. Similarly:

~~~java
List<Document> page = orders.find(
        Filters.eq("status", "ACTIVE"))
        .limit(100)
        .into(new ArrayList<>());
~~~

The driver handles iteration for these convenience methods; developers must still bound result size so millions of documents are never loaded into memory. For large datasets, process in batches via cursor.

### 13.5. Closing a Cursor Does Not Close the Socket

Closing a cursor frees cursor resources on the server and releases associated driver state. The connection pool is not torn down; `MongoClient` continues reusing connections.

This is why you must clearly distinguish **per-query resources** from **application-wide resources**.

## 14. ClientSession: Create per Workflow, Never Share Arbitrarily

`MongoClient` is safe to share, but `ClientSession` **must not be used concurrently by multiple threads**. Create a session when you need causal consistency across operations or to open a transaction.

### 14.1. Using a Session in a Short Scope

~~~java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;

try (ClientSession session = client.startSession()) {
    Document order = orders.find(
            session, Filters.eq("_id", "ORDER-1001"))
            .first();

    System.out.println(order);
}
~~~

The session closes at the end of the block; the **shared client** remains alive.

### 14.2. Simple Transaction

~~~java
try (ClientSession session = client.startSession()) {
    session.startTransaction();

    try {
        orders.updateOne(
                session,
                Filters.eq("_id", "ORDER-1001"),
                Updates.set("status", "PAID")
        );

        payments.insertOne(
                session,
                new Document("_id", "PAY-1001")
                        .append("orderId", "ORDER-1001")
                        .append("amount", 20000)
        );

        session.commitTransaction();
    } catch (RuntimeException e) {
        try {
            session.abortTransaction();
        } catch (RuntimeException abortError) {
            e.addSuppressed(abortError);
        }
        throw e;
    }
}
~~~

This is a structural example; real transactions require a supporting topology, appropriate write/read concerns, retry logic for **transient transaction errors / unknown commit outcomes**, idempotency, and business invariant checks. Do not copy this directly as production payment logic without full error handling.

### 14.3. Do Not Hold a Session in a Singleton

Wrong:

~~~java
public final class BadRepository {
    private final ClientSession sharedSession;

    public BadRepository(MongoClient client) {
        this.sharedSession = client.startSession();
    }

    // Multiple requests sharing sharedSession is an unsafe design.
}
~~~

Better: create the session in the **application service for a single workflow**, pass it to repositories within that workflow's scope, and close it upon completion.

### 14.4. Does a Session Pin a Connection Continuously?

Do not assume every session permanently pins a dedicated TCP connection from `startSession` to `close`. Checkout and pinning behavior depend on operation type, transactions, and topology; certain transaction states can pin resources.

Thus **long-lived sessions/transactions** can impact pools, though you cannot trivially conclude "100 sessions equals 100 sockets" across every deployment.

### 14.5. Implicit Sessions

The driver automatically manages logical sessions for supported operations. Applications do not need to call `startSession()` for every `findOne()`. Use explicit sessions only when the workflow genuinely requires them.

## 15. Spring Boot: Let the Container Manage MongoClient

With **Spring Boot + Spring Data MongoDB**, the framework automatically configures `MongoClient` and related beans when dependencies and properties are valid. It belongs to the **application context**, not recreated in every repository method.

### 15.1. Configuration via Properties

Example:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
~~~

`MONGODB_URI` comes from the environment or secret store; never store real credentials in `application.yml`.

Across different Spring Boot versions, MongoDB configuration property names (or namespaces for additional properties) may change. Consult the **Spring Boot documentation for your project's version**; if Boot already auto-configures `MongoClient`, do not declare a second `MongoClient` just to call `MongoTemplate`.

### 15.2. Repository via Spring Data

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Repository;
import org.bson.Document;

@Repository
public final class OrderStore {
    private final MongoTemplate mongoTemplate;

    public OrderStore(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public Document getOrder(String id) {
        return mongoTemplate.findById(
                id, Document.class, "orders");
    }
}
~~~

The framework injects `MongoTemplate`, which uses the Spring-managed client. `OrderStore` neither creates nor closes `MongoClient`.

### 15.3. When Defining the Bean Manually

When auto-configuration does not fit, you can configure it explicitly:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MongoConfiguration {
    @Bean(destroyMethod = "close")
    public MongoClient mongoClient(
            org.springframework.core.env.Environment environment) {
        String uri = environment.getRequiredProperty(
                "app.mongodb.uri");
        return MongoClients.create(uri);
    }
}
~~~

Beans are **singletons by default** in Spring; Spring calls `close()` when the context shuts down cleanly. If defining the bean manually like this, review auto-configuration behavior and configure `MongoDatabaseFactory`/`MongoTemplate` accordingly to avoid creating two unintended beans.

### 15.4. Do Not Close the Client in Every Repository's @PreDestroy

~~~java
@PreDestroy
public void stop() {
    sharedMongoClient.close();
}
~~~

If multiple repositories receive the same `MongoClient` bean, closing it in each repository creates ambiguous ownership and can disrupt shutdown ordering. Normally, let Spring manage closing the **`MongoClient` bean** once.

### 15.5. The Sync Driver Does Not Become Reactive Simply by Running in Spring

If an application uses **Spring WebFlux** or a non-blocking event loop, Sync Driver calls are **blocking I/O**. Do not call them directly from the event loop assuming they are non-blocking.

Either use the **Reactive Streams Driver / Spring Data Reactive MongoDB** or offload blocking operations to an appropriate thread pool by design. Even then, the principles of **client reuse and lifecycle management** remain essential, though APIs, publishers, and cancellation differ.

## 16. Batch Jobs, Schedulers, and CLIs

### 16.1. Batch Jobs Running for Minutes

A batch job performing many `insertMany`, `updateOne`, or `aggregate` calls should use **one client for the entire job** and close it when the job completes.

~~~java
public static void main(String[] args) {
    String uri = System.getenv("MONGODB_URI");

    try (MongoClient client = MongoClients.create(uri)) {
        MongoDatabase db = client.getDatabase("reporting");
        MongoCollection<Document> events =
                db.getCollection("events");

        // Multiple queries/batches reuse the same client.
        runImport(events);
        buildSummary(events);
        verifyCounts(events);
    }
}
~~~

### 16.2. Scheduled Tasks Inside a Backend

If a `@Scheduled` task runs every 5 minutes inside the same Spring Boot service, do not create a new `MongoClient` each time the scheduler wakes up. Use the injected `MongoTemplate` or repository.

### 16.3. Serverless Functions

In serverless environments, **cold starts** and **instance reuse** differ from traditional daemons. It is often beneficial to scope `MongoClient` at the **reusable process/container level** rather than recreating it per invocation, while checking:

- Actual instance lifetime.
- Concurrent invocations per instance.
- Idle sockets when an instance is frozen.
- Timeouts and network permissions.
- Sudden bursts in total instance count.

Do not rely on shutdown hooks always running in every serverless scenario. And never create thousands of clients inside a single warm instance.

### 16.4. Desktop Apps or Long-Running Interactive Programs

`MongoClient` lifecycle should align with the **main application session** or a user-opened/closed connection module. If the user switches clusters or credentials, the application may need to **close the old client and create a new one** via a controlled reconfiguration flow.

## 17. Observing Connection Pools and Driver Events

Do not tune pools by guesswork. The MongoDB Java Driver provides **Connection Pool Monitoring** (CMAP), letting applications observe when connections are created, checked out, checked in, closed, or when wait queues fail.

### 17.1. Registering a ConnectionPoolListener

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.event.ConnectionCheckedOutEvent;
import com.mongodb.event.ConnectionCheckedInEvent;
import com.mongodb.event.ConnectionCheckOutFailedEvent;
import com.mongodb.event.ConnectionPoolListener;

public final class PoolMonitoringExample {
    public static MongoClient create(String uri) {
        ConnectionPoolListener listener =
                new ConnectionPoolListener() {
                    @Override
                    public void connectionCheckedOut(
                            ConnectionCheckedOutEvent event) {
                        System.out.println("Connection checked out");
                    }

                    @Override
                    public void connectionCheckedIn(
                            ConnectionCheckedInEvent event) {
                        System.out.println("Connection checked in");
                    }

                    @Override
                    public void connectionCheckOutFailed(
                            ConnectionCheckOutFailedEvent event) {
                        System.out.println(
                                "Connection checkout failed: "
                                        + event.getReason());
                    }
                };

        MongoClientSettings settings =
                MongoClientSettings.builder()
                        .applyConnectionString(
                                new ConnectionString(uri))
                        .applyToConnectionPoolSettings(pool ->
                                pool.addConnectionPoolListener(listener))
                        .build();

        return MongoClients.create(settings);
    }
}
~~~

This is an illustrative example. In production, never print every checkout to the console, as log volume can be high and slow callbacks degrade performance. Collect counters/timers via a metrics system with controlled label cardinality, and check the exact event API for your driver version.

### 17.2. Important Metrics

| Metric | What You Want to Know |
|---|---|
| Connection created/closed | Is the pool opening/closing abnormally? |
| Checked-out connections | How many connections are actively in use? |
| Available/idle connections | Are connections ready to be leased? |
| Checkout wait p95/p99 | How long do tasks wait on the pool? |
| Checkout failures | Is the pool exhausted or are connections failing? |
| Concurrent operations | How many operations is the service sending to the DB? |
| Command latency | Is the server query slow or just the pool waiting? |
| Client instances/pods | Are too many pools being created? |
| Server connection count | How many sockets must the cluster maintain? |
| CPU/I/O/query scanned | Is MongoDB bottlenecked by workload? |

These names represent **metric categories to collect**, not a fixed set of metric keys exported identically by every MongoDB Java Driver version.

### 17.3. Checking Connections on the MongoDB Server

With appropriate privileges:

~~~javascript
db.serverStatus().connections
~~~

The output may include fields such as `current`, `available`, and `totalCreated` depending on version. This reflects the **server-side** view across multiple applications and monitoring connections, not just one Java `MongoClient`.

### 17.4. Command Monitoring Must Not Expose Data

The Java Driver provides `CommandListener` to measure command timings and outcomes. When registering a listener, collect only command name, duration, status, and safe correlation info. Never log entire command payloads, which may contain PII, credentials, or sensitive business data.

Measuring command latency separates slow server queries from slow pool checkouts, though it does not replace inspecting `explain`/indexes when tuning workloads.

## 18. Deployment Scale and Connection Storms

### 18.1. Multiple Application Replicas

Suppose 12 service instances each run one client with `maxPoolSize` of 40 per server. You cannot claim the system always holds **12 × 40 = 480** connections, because:

- 40 is an upper bound, not an always-open count.
- Pools exist per eligible server and topology.
- Read preference shifts which nodes receive workload.
- Dedicated sockets exist for monitoring, reconnects, and background tasks.
- `minPoolSize` and actual load affect socket counts.

Still, **480** serves as an upper-bound capacity estimate for one operation pool against one server if all 12 instances saturate all 40 connections. Total counts must account for the entire topology and other components.

### 18.2. Autoscaling Can Trigger Connection Storms

~~~text
Deployment scales from 5 to 100 pods
            |
            v
Each pod creates a MongoClient
            |
            v
Topology discovery + TLS + authentication
            |
            v
Many connections created during traffic surge
~~~

Mitigations: control scale-out rate, avoid multiple clients per pod, tune `minPoolSize`/`maxConnecting`/`maxPoolSize`, bound concurrency, and verify network/server connection capacity.

### 18.3. Pool Saturation Caused by Slow Queries

~~~text
maxPoolSize = 30
30 aggregations running, each taking 20 seconds
Other CRUD operations wait for checkout
~~~

Do not immediately raise the pool to 300 while ignoring the root cause. Check `explain`/indexes, limit concurrent expensive jobs, reduce documents scanned, and measure server capacity. Adding more connections against an already overloaded MongoDB can worsen overall latency.

## 19. Distinguishing Client Leaks, Cursor Leaks, and Session Leaks

### 19.1. Client Leak

~~~java
public void handleRequest() {
    MongoClient client = MongoClients.create(uri);
    // Never closed and never reused. Each request can leak new resources.
}
~~~

Too many clients spawn unfreed connection pools, topology monitors, and connections. The real fix is **sharing the client over the application lifecycle**, not merely adding `close()` at the end of every request.

### 19.2. Cursor Leak

~~~java
MongoCursor<Document> cursor = collection.find().iterator();
// Code exits method on error without closing cursor.
~~~

Even with a single `MongoClient`, unclosed cursors hold resources unnecessarily. Always wrap `MongoCursor` in `try-with-resources`.

### 19.3. Session Leak

~~~java
ClientSession session = client.startSession();
// Session not closed after workflow.
~~~

`ClientSession` must be closed when finished, especially when a transaction fails or aborts. Do not rely on server-side timeouts to replace client-side resource cleanup.

### 19.4. Do Not Rely on the Garbage Collector

Garbage collection does not guarantee timely closure of network resources. Java finalization is likewise unsuitable for managing external resources under SLAs. Define explicit ownership and close proactively.

## 20. Testing Lifecycles and Repositories

### 20.1. Unit Tests and Integration Tests

Repositories accepting `MongoCollection` via constructor cleanly decouple business logic from infrastructure. Data processing logic can be unit tested, while serialization, networking, sessions, pooling, failover, and transactions require **integration tests against a real MongoDB in a test environment**.

### 20.2. Testcontainers

An example using JUnit 5, MongoDB Java Sync Driver, and Testcontainers (dependencies/APIs must match versions):

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderRepositoryIntegrationTest {
    @Test
    void storesAndReadsAnOrder() {
        try (MongoDBContainer mongo =
                     new MongoDBContainer(
                             DockerImageName.parse("mongo:7.0"))) {
            mongo.start();

            try (MongoClient client = MongoClients.create(
                    mongo.getReplicaSetUrl())) {
                MongoCollection<Document> collection =
                        client.getDatabase("test_shop")
                                .getCollection("orders");

                OrderRepository repository =
                        new OrderRepository(collection);

                repository.insert("O-1", "C-1");

                Document result = repository.findById("O-1");
                assertEquals("C-1",
                        result.getString("customerId"));
            }
        }
    }
}
~~~

The client in the test is created for **the entire integration test**, not per MongoDB operation. Containers and clients can be reused across multiple tests if isolation and cleanup are properly designed.

**Version note:** Testcontainers' `MongoDBContainer` module/class, MongoDB image, and replica set setup change across releases. Choose images and APIs compatible with your environment rather than treating the example image tag as mandatory.

### 20.3. What to Test

- Only one client is created per configuration within the application context.
- Two different repositories genuinely share the same underlying resource.
- Sessions and cursors are closed when exceptions occur.
- Shutdown does not close the client while workers are still active.
- Pool saturation does not hang requests indefinitely.
- During primary failover, the application follows designed failure/retry behavior.
- Credentials are not logged on connection failure.
- Tests never write to or delete data from a production database.

### 20.4. Testing Shutdown and Abnormal Conditions

In integration tests, verify that operations after client closure fail rather than treating a closed client as alive. However, do not close a shared `MongoClient` mid-suite while other unit tests still depend on it if tests share a container or application context.

## 21. Retryable Reads and Writes Do Not Replace Pool Design

Under supported conditions, the Java Driver can automatically retry certain read/write operations:

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
        .applyConnectionString(new ConnectionString(uri))
        .retryReads(true)
        .retryWrites(true)
        .build();
~~~

This **does not mean** every business request is safe to retry. For instance, a payment endpoint with side effects must use idempotency keys and business constraints beyond driver-level retries.

Retries also cannot fix bad DNS/TLS, rejected credentials, or a pool saturated by a very slow query. Retrying indiscriminately can even increase latency and load.

### 21.1. Should You Create a New MongoClient When a Query Fails?

Generally **no**. The client has built-in topology monitoring/reconnection and driver retry policies. Creating a new client inside every catch block causes connection storms and destroys connection reuse.

Create a new client deliberately only when the owner properly closes the old client, when cluster/credentials/config must change, or for a validated special lifecycle case.

### 21.2. Idempotency and Ambiguous Outcomes

A write can succeed on the server while the client loses the connection before receiving the acknowledgment. If the application blindly retries without checking outcomes, duplicate business records can result.

Recommendations:

- Use deterministic `_id` or stable business IDs.
- Design idempotent upserts where appropriate.
- Inspect error categories and write concerns.
- Never map every driver exception to "insert again with a new ID."
- Treat retryable writes as a bounded driver capability, not a guarantee of exactly-once side effects for every business operation.

## 22. Common Issues When Creating and Using MongoClient

### 22.1. MongoClient Creation Succeeds, but the First Query Times Out

**Symptom:** `MongoClients.create()` throws no error; `find()` or `ping()` times out.

**Explanation:** `create()` does not necessarily execute full network/connect/auth handshakes to prove deployment readiness. Server selection, socket connect, and authorization may happen when the first operation runs.

**Action:** Check DNS/hostnames, VPN/network, Atlas IP allowlist, TLS, credentials, replica set name, and ports; test `ping` using **the exact production client configuration** in a safe environment.

### 22.2. High Pool Wait While MongoDB CPU Looks Normal

**Likely cause:** Too many operations waiting on checkout; pool too small, connections pinned/held too long, slow new-connection establishment, or application-side delays.

**Action:** Inspect checked-out count, checkout wait histograms, active sessions/transactions, query durations, and network. Never look solely at DB CPU and conclude there is no pool contention.

### 22.3. Raising maxPoolSize Does Not Improve Throughput

**Likely cause:** Bottleneck is at query/index/disk/locks/CPU or an external service; adding connections only makes more operations contend for the same bottleneck.

**Action:** Profile and `explain` heavy queries, measure end-to-end latency, and optimize indexes, batching, and concurrency. Adjust pool size incrementally against a clear baseline.

### 22.4. Database Shows Thousands of Connections Despite Low Traffic

**Likely cause:** Many application replicas, clients created per repository/request, overly high `minPoolSize`, or multiple pools across topology members.

**Action:** Audit `MongoClient` count per process, Spring wiring, autoscaling replicas, and `minPoolSize`. Never diagnose solely from a cluster-wide `serverStatus.connections.current` total.

### 22.5. `MongoClient has been closed` While Service Is Running

**Likely cause:** A repository or short-lived scope called `close()` on a client shared by multiple components; or a Spring bean lifecycle closed before background jobs finished.

**Action:** Identify the owner and shutdown sequence; only the owner closes the client after stopping incoming requests and completing/canceling in-flight operations.

### 22.6. `MongoTimeoutException` While Looking for Primary

**Likely cause:** Primary failing over, network partition, wrong `replicaSet` name, DNS/TLS error, or topology has no eligible node.

**Action:** Inspect driver server-selection diagnostics, MongoDB replica set health, and network connectivity. Never switch all reads/writes to a secondary if data consistency requirements disallow it.

### 22.7. Authentication Failed

**Likely cause:** Wrong user/password/`authSource`, rotated credentials not yet updated in the service, unencoded special characters in the URI, or mismatched auth mechanism.

**Action:** Verify secret source, `authSource`, and user roles. Never log raw URIs or passwords while debugging.

### 22.8. TLS Handshake Error

**Likely cause:** Untrusted truststore/CA chain, hostname validation failure, expired certificate, or connecting to the wrong endpoint.

**Action:** Fix TLS/certificate/hostname configuration; never disable certificate verification in production as a "quick fix."

### 22.9. `waitQueueTimeout` During Traffic Spikes

**Likely cause:** Too many concurrent operations requesting connections and checkout cannot keep up.

**Action:** Measure active checkouts vs. `maxPoolSize`, query duration, `maxConnecting`, pod count, and downstream pressure. Apply bounded concurrency/backpressure and optimize queries before considering higher `maxPoolSize` or timeouts.

### 22.10. Very Slow Queries Even with Plenty of Free Pool Connections

Pool availability does not imply good indexes or queries. Inspect execution plans, documents scanned, sort/aggregation stages, response sizes, and server load. Adding connections does not turn a collection scan into an index scan.

### 22.11. Memory Spikes When Reading a Large Collection

**Likely cause:** Calling `.into(new ArrayList<>())` or `toList` across millions of documents, buffering the entire result set into the JVM.

**Action:** Iterate with cursors in batches, close cursors in proper scope, limit results, apply filters/projections/aggregations, and process via streaming workflows.

### 22.12. Using the Same ClientSession Across Multiple CompletableFutures

**Likely cause:** Non-thread-safe session shared across parallel tasks.

**Action:** Coordinate operations belonging to a session/transaction sequentially as supported; never use one session concurrently from multiple threads, and ensure closure.

### 22.13. Production Has Two MongoClients Due to Spring Wiring

**Likely cause:** Framework auto-configuration creates a bean, and the project manually declares another bean or a service calls `MongoClients.create()` separately.

**Action:** Inspect application context and component initialization; use a single configuration source per connection requirement to avoid duplicate lifecycles and extra pools.

### 22.14. App Does Not Exit After Job Completes

**Likely cause:** `MongoClient` unclosed, executor/worker threads still alive, or another background process still running.

**Action:** Identify the owner; close the CLI/batch client when the workflow ends and shut down executors/thread pools in order. Do not simply force `System.exit(0)` to bypass resource lifecycles.

### 22.15. "Connection refused" After Changing Clusters

**Likely cause:** App still holds a client configured with the old URI, or the new endpoint lacks network access. `MongoClientSettings` are built at startup; changing an environment variable at runtime does not automatically retarget an existing client.

**Action:** Use a controlled rollout or client recreation workflow for intentional configuration changes. Never mutate URIs via reflection inside a running client.

### 22.16. MongoDB Server Reports "Too many connections"

**Likely cause:** Sum of clients, pools, pods, and monitoring connections exceeds server or hosting tier limits.

**Action:** Inventory replicas, clients per process, `minPoolSize`, and server connection capacity; eliminate client churn, consider throttling, and adjust infrastructure with measurements. Do not simply raise server `maxIncomingConnections` while ignoring leaked clients.

## 23. Connection Security and Secret Management

`MongoClient` is the entry point to the database; misconfiguration can expose sensitive data even when CRUD code is completely valid.

### 23.1. Never Store Passwords in the Repository

Wrong:

~~~java
String connectionString =
        "mongodb://root:SuperSecretPassword@db.internal:27017";
~~~

Better:

~~~java
String uri = System.getenv("MONGODB_URI");
if (uri == null || uri.isBlank()) {
    throw new IllegalStateException("Missing MONGODB_URI");
}
MongoClient client = MongoClients.create(uri);
~~~

Production environments should retrieve secrets from a secret management system with rotation and RBAC. Never write full URIs into exception wrappers, config logs, metrics, or startup banners.

### 23.2. TLS and Certificate Verification

For connections traversing untrusted networks, enforce TLS and certificate/hostname verification. When using Atlas, apply the proper TLS configuration for the endpoint.

Never create a `MongoClient` with TLS verification disabled just to "bypass certificate errors" in production. Fix the trust chain, hostname, DNS, and certificates instead.

### 23.3. Least Privilege

An orders service only needs access to the databases and collections required for its domain, not admin/root credentials. Separate users/roles for:

- Runtime business reads/writes.
- Migrations/index management.
- Backups/restores.
- Monitoring or read-only diagnostics.

`MongoClient` carries the server privileges of its configured credentials; sharing one client across threads does not mean every HTTP user shares the same business permissions. The application must still enforce authorization by tenant, role, and document.

### 23.4. Never Expose Client Credentials Publicly

Only trusted backends should hold MongoDB credentials/URIs. Never embed a database-privileged connection string in frontend JavaScript or easily decompiled mobile apps.

### 23.5. Rotating Credentials While the Service Runs

An active `MongoClient` is initialized with the credentials present at creation time. When secrets rotate, establish a rollout or client-refresh process and monitor auth errors during the transition window. Do not assume editing an external secret file instantly updates all active sockets and credential objects in memory.

### 23.6. Distinguishing Connectivity from Business Authorization

MongoDB authentication verifies service identity; business authorization verifies which orders a user may read or modify. Both are mandatory:

~~~text
User request
   |
   v
App authenticates user
   |
   v
App checks tenant/role/document rights
   |
   v
Shared MongoClient authenticates as service principal
   |
   v
MongoDB query contains mandatory business filters
~~~

Never treat a successful `MongoClient` connection as proof that every end-user request is allowed to access the entire database.

## 24. Decision Table: Which Lifecycle for Each Application Type?

| Context | Appropriate MongoClient Scope | When to Close? |
|---|---|---|
| Java CLI running a few commands | One client for the whole program | After all commands complete |
| CSV import of millions of records | One client for the entire batch job | When worker finishes, including on error |
| REST API server | Singleton/application-scoped client | When server stops and requests drain |
| Spring Boot + Spring Data | Container-managed `MongoClient` bean | When application context closes |
| Scheduler inside a service | Shared bean/client with the service | Do not close at the end of each scheduled run |
| Kafka/queue consumer | One client per process or container | After consumer stops polling and processing messages |
| Serverless function | Reuse client within warm process where suitable | Per runtime lifecycle, not per invocation |
| Single JUnit integration test | Client per test fixture/test container | After the test or test suite |
| Cross-cluster migration | One source client, one target client | After cutover/cleanup of each cluster |
| Multiple distinct MongoDB credentials | Client per genuinely needed config group | When the owner of that connection group stops |

Do not pick scope by looking at how long or short a method is. Pick scope based on **which component owns the connection and whether configuration changes**.

### 24.1. When Should You Avoid a JVM-Wide Static Singleton?

You do not need a **static global `MongoClient`** shared across every task, cluster, and credential. Singletons managed by a **dependency injection container / application context** are easier to control because they provide clean lifecycles and test isolation.

If multiple clusters/credentials exist or tests spin up isolated contexts, each context can own its appropriate client. Avoid mutable static variables silently overwritten across tests and modules.

### 24.2. Is a Static Holder Always Wrong?

A small Java program might use:

~~~java
public final class MongoHolder {
    private static final MongoClient CLIENT =
            MongoClients.create(System.getenv("MONGODB_URI"));

    public static MongoClient get() {
        return CLIENT;
    }
}
~~~

This creates one client per classloader, but **makes shutdown hard to manage**, makes overriding URIs in tests difficult, and risks initialization exceptions before the app is ready. Dependency injection or an explicit owner is usually easier to maintain.

### 24.3. Do You Need to Cache MongoDatabase/MongoCollection?

Calling `client.getDatabase("shop")` or `database.getCollection("orders")` obtains a relatively lightweight logical handle; it does not open a new `MongoClient`.

You can store `MongoCollection` in a repository for clarity or obtain it from the client when needed. **The most impactful optimization is reusing `MongoClient`**, without building a complex global cache for every collection name.

## 25. End-to-End Example: One MongoClient, Two Repositories, Multiple Operations

The following Java Sync Driver example shows a small application creating a client once, using multiple collections, and closing properly upon completion.

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import org.bson.Document;

public final class SharedMongoClientDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI missing");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("java_learning");

            MongoCollection<Document> customers =
                    db.getCollection("customers");
            MongoCollection<Document> orders =
                    db.getCollection("orders");

            customers.updateOne(
                    Filters.eq("_id", "CUSTOMER-1"),
                    Updates.set("name", "An"),
                    new com.mongodb.client.model.UpdateOptions()
                            .upsert(true)
            );

            orders.updateOne(
                    Filters.eq("_id", "ORDER-1"),
                    Updates.combine(
                            Updates.set("customerId", "CUSTOMER-1"),
                            Updates.set("status", "NEW")
                    ),
                    new com.mongodb.client.model.UpdateOptions()
                            .upsert(true)
            );

            Document customer = customers.find(
                    Filters.eq("_id", "CUSTOMER-1")
            ).first();

            Document order = orders.find(
                    Filters.eq("_id", "ORDER-1")
            ).first();

            System.out.println("Customer found: "
                    + (customer != null));
            System.out.println("Order found: "
                    + (order != null));
        }
    }
}
~~~

In this example:

- **Only one `MongoClient`** is created in `main`.
- Two `MongoCollection` handles originate from the same `MongoDatabase`.
- Multiple updates and reads share the client's pool.
- The client is not closed after each individual operation.
- Once `main` finishes, `try-with-resources` closes the client.
- `UpdateOptions.upsert(true)` makes the example idempotently re-runnable in a test collection; it does not replace production concurrency/idempotency rules.

**Never run this example against production data** without a dedicated database and appropriate write permissions. The two fixed `_id` values are purely for lifecycle demonstration.

## 26. Hands-On Exercises and Scenario Questions

These exercises test how to **create, share, and release `MongoClient`**. Learners can run them against a local MongoDB or test cluster without altering production server settings.

### Exercise 1. How Many MongoClients?

Code:

~~~java
public Document getById(String id) {
    MongoClient c = MongoClients.create(uri);
    return c.getDatabase("shop")
            .getCollection("orders")
            .find(Filters.eq("_id", id))
            .first();
}
~~~

**Question:** If the endpoint is called 10,000 times, how many `MongoClient` instances could this snippet create? What design flaw appears?

**Guidance Answer:** Up to 10,000 instances if every call executes that code. They are neither closed nor reused. Move client creation to application bootstrap, inject `MongoCollection`/repository, and close when the app shuts down.

### Exercise 2. Is Try-with-resources Always Right?

~~~java
try (MongoClient client = MongoClients.create(uri)) {
    return loadOneOrder(client);
}
~~~

**Question:** Is this right in a CLI or inside an HTTP endpoint?

**Answer:** Right when the block spans the entire lifetime of a short-lived program. Suboptimal if executed per HTTP request, because it continually creates and tears down pools.

### Exercise 3. Thread-Safety

An application has 100 worker threads that all need to read the `orders` collection.

**Question:** Do you need to create 100 `MongoClient` instances?

**Answer:** No. One `MongoClient` can be shared across threads, along with `MongoCollection` handles. The driver manages pooling. Remember that `ClientSession` and cursors are not thread-safe like the client.

### Exercise 4. MongoClient and TCP Sockets

**Question:** Can a single `MongoClient` hold more than one socket?

**Answer:** Yes. `MongoClient` manages pools per server/topology and maintains additional sockets for tasks like monitoring. One client does not equal a single TCP connection.

### Exercise 5. maxPoolSize=100

Immediately after creating the client, the service has not executed any queries yet.

**Question:** Are 100 connections guaranteed to be open right away?

**Answer:** No. Pools generally grow on demand and according to `minPoolSize`/topology settings. `maxPoolSize` is an upper bound, not an always-open count.

### Exercise 6. Full Pool

`maxPoolSize=20`, 20 operations currently hold connections, and a 21st operation arrives.

**Question:** Will the driver always open a 21st connection?

**Answer:** No. The operation waits for a connection to be returned and times out if the checkout wait limit is exceeded.

### Exercise 7. maxConnecting=2

`maxPoolSize=80` and `maxConnecting=2`.

**Question:** Can the service only run at most two operations concurrently?

**Answer:** No. `maxConnecting` limits how many new connections can be established concurrently; it is not the cap on total active connections over time.

### Exercise 8. Multiple Pods

There are 20 service instances, each with one client and a relatively high `minPoolSize`.

**Question:** Why do many connections still appear even when traffic is low?

**Guidance:** Each process maintains its own pools per server/topology, and `minPoolSize` keeps baseline sockets open even under light load. Inspect replica count, client instances, and pool settings.

### Exercise 9. Server Selection Timeout vs. Checkout Timeout

In one case the app cannot find a primary; in another case the primary is healthy, but the pool is fully occupied.

**Question:** Do both errors have the same root cause?

**Answer:** No. The first is server selection/topology/network; the second is pool checkout/concurrency. Different metrics and settings are required to investigate each.

### Exercise 10. `MongoClients.create()` Succeeds

**Question:** Does that guarantee password, TLS, and write permissions are all valid?

**Answer:** No. The first actual operation such as `ping`, `find`, or `insert` validates those conditions; and `ping` alone does not prove write privileges on the target collection.

### Exercise 11. Using a Closed Client

One repository calls `sharedMongoClient.close()` after `findOne()`.

**Question:** What problems can other services encounter?

**Answer:** Subsequent operations through the shared client fail because it is closed. Only the owner of `MongoClient` should close it when the entire application has stopped using it.

### Exercise 12. Cursor

Code:

~~~java
MongoCursor<Document> cursor =
        collection.find().iterator();
while (cursor.hasNext()) {
    process(cursor.next());
}
~~~

**Question:** What needs changing if `process()` throws an exception?

**Answer:** Wrap the cursor in `try-with-resources` so it closes whether processing finishes or throws an error. Never close `MongoClient` instead of closing the cursor.

### Exercise 13. Session

Two `CompletableFuture` tasks share one `ClientSession` running a transaction.

**Question:** Is this safe?

**Answer:** No. `ClientSession` is not thread-safe and must not be used concurrently from multiple threads. Operations belonging to the same transaction must be coordinated according to driver-supported semantics.

### Exercise 14. Spring Boot

An application already uses Spring Data MongoDB and `MongoTemplate`. A developer adds `MongoClients.create(...)` in every repository.

**Question:** How should this be fixed?

**Answer:** Use the container-managed bean/client and inject `MongoTemplate`/`MongoCollection` appropriately, avoiding duplicate pools and letting the application context close it.

### Exercise 15. Batch Job

A job imports 1 million records in batches of 500 documents.

**Question:** Create a client per batch or one client for the entire job?

**Answer:** One client for the entire job, reused across all batches, then closed upon completion or error cleanup. Each batch can use its own cursor, request payload, and retry logic.

### Exercise 16. Serverless

A function is invoked hundreds of times on the same warm container.

**Question:** Should you create a new client at the start of every invocation?

**Guidance:** Consider caching/reusing the client at process/container scope subject to concurrency and serverless lifecycle constraints; do not assume a warm instance lives forever or that shutdown hooks always execute.

### Exercise 17. Replica Set Failover

The primary changes nodes between two write operations.

**Question:** Do you need to manually create a new `MongoClient` on every request to discover the new primary?

**Answer:** Usually no. The driver handles topology monitoring and server selection. Use proper timeouts, retries, and idempotency rather than causing connection storms by recreating clients repeatedly.

### Exercise 18. Slow Queries Exhausting the Pool

There are 30 concurrent expensive aggregations, with pool `maxSize=30`.

**Question:** Will simply raising `maxSize=300` guarantee improvement?

**Answer:** No. It can overload the server further. Optimize the aggregations/indexes, set concurrency bounds, and measure before/after metrics.

### Exercise 19. Loading Many Documents into Memory

~~~java
List<Document> all = collection.find()
        .into(new ArrayList<>());
~~~

The collection has 10 million documents.

**Question:** Is using a shared client enough to make this memory-safe?

**Answer:** No. Materializing 10 million records can exhaust JVM RAM. Apply filters/projections, limits, cursors, and batch processing.

### Exercise 20. Which Timeout?

A request is waiting for a connection in the pool and has not yet sent a command to MongoDB.

**Question:** Will increasing `maxTimeMS` on `find()` fix it?

**Answer:** No. `maxTimeMS` bounds command execution on the MongoDB server, whereas the failure here occurs at pool checkout. Check wait queue timeout, pool saturation, and concurrency.

### Exercise 21. Read Preference

A service reads from secondaries to reduce primary load, but a user updates a record and immediately queries it only to see stale data.

**Question:** What could explain this?

**Answer:** The secondary may lag behind replication. Choose read preference and consistency guarantees according to business needs; do not treat every secondary read as read-your-writes.

### Exercise 22. Java Shutdown Hook

An app already lets Spring Boot manage the `MongoClient` bean. A developer adds an extra shutdown hook that closes the same client.

**Question:** Is this necessary?

**Answer:** Usually no. The container already owns the lifecycle. Duplicate hooks can make shutdown order unpredictable; it is better to let a single owner close the client after background jobs stop.

### Exercise 23. Testcontainers

Why does the test example create a `MongoClient` per test while production uses an app-scoped client?

**Answer:** Because **the owner and lifecycle differ**. The test fixture owns the resource until the test completes; the service owner owns it until app shutdown. The core rule remains: never create a client per CRUD operation.

### Exercise 24. Disconnection After a Network Outage

A developer proposes:

~~~text
catch every exception
    -> create another MongoClient
    -> retry original request blindly
~~~

**Question:** Why is this dangerous?

**Guidance:** Creating additional clients causes pool churn and connection storms while masking DNS/TLS/auth errors; blindly retrying non-idempotent business operations can cause duplicates. Categorize errors, use appropriate driver retries, and verify business outcomes.

### Exercise 25. Connection Storm After Deploy

50 pods start simultaneously, each with `minPoolSize=100`.

**Question:** What happens to the cluster and what should be measured?

**Guidance:** It can generate a massive burst of sockets and handshakes in a short time. Check replica count, per-server pools, `maxConnecting`, TLS/auth load, server connection limits, startup readiness, and autoscaling policies.

### Exercise 26. Backend Architecture Design

Requirements:

~~~text
Orders REST API       : ~200 requests/second
Customers REST API    : ~100 requests/second
Inventory background  : runs every minute
Same MongoDB cluster  : same service credentials
Deployment            : 8 application instances
~~~

Describe:

1. At which layer does `MongoClient` live?
2. How do the three repositories obtain `MongoCollection`?
3. When is the client closed?
4. Do you need three separate pools for the three collections?
5. If the inventory aggregation causes long pool waits, how do you handle it?
6. When scaling from 8 to 30 instances, what must be monitored?

**Guidance Answer:** One client per container instance for the shared cluster/config, injected into repositories and shared. Close on service shutdown. Do not create separate pools per collection. Bound concurrency/optimize the aggregation and check checkout latency, query latency, and server capacity before altering `maxPoolSize`; calculate total connections when scaling.

## 27. Pre-Deployment Checklist

### 27.1. Configuration and Security

- [ ] URI sourced from a trusted secret/config store; no passwords committed in the repository.
- [ ] TLS, certificate verification, `authSource`, and network access match the environment.
- [ ] Driver version is compatible with MongoDB server and framework/BOM.
- [ ] `ReadPreference`/`ReadConcern`/`WriteConcern` meet business requirements.
- [ ] URIs with credentials or sensitive MongoDB documents are never logged.

### 27.2. Lifecycle and Sharing

- [ ] `MongoClient` created **once per owner/configuration**, never per request.
- [ ] Repositories use injected `MongoCollection`/`MongoTemplate`.
- [ ] Only the owner or framework lifecycle closes the client.
- [ ] Service stops accepting requests/jobs and drains in-flight work before closing.
- [ ] Cursors use `try-with-resources` when iterating explicitly.
- [ ] `ClientSession` has a clear scope and is never shared concurrently across threads.
- [ ] Sync Driver blocking I/O is never mixed onto a non-blocking event loop without an explicit strategy.

### 27.3. Pools, Timeouts, and Performance

- [ ] `maxPoolSize`/`minPoolSize`/`maxConnecting` set based on measurements, not guesswork.
- [ ] Total clients/pods and per-server pools across topology calculated.
- [ ] Appropriate checkout wait timeout and server selection timeout configured.
- [ ] Operation deadlines and HTTP timeouts aligned with SLAs.
- [ ] Metrics enabled for checked-out connections, checkout waits/failures, and command latency.
- [ ] Backpressure enforced for expensive jobs and high concurrency.
- [ ] Slow queries tuned via indexes/`explain` rather than simply enlarging pools.

### 27.4. Testing and Recovery

- [ ] Integration tests run against a non-production database/container.
- [ ] Startup tested when MongoDB is unavailable or auth/TLS fails.
- [ ] Shutdown, cursor/session cleanup, and retry behavior tested.
- [ ] Plan in place for failover and connection storms during autoscaling.
- [ ] Clear owner assigned for rotating clients/URIs when credentials or clusters change.

## 28. Quick Reference Table

| Question | Short Answer |
|---|---|
| Is MongoClient a single socket? | No; it manages config, topology, and pools |
| Does each collection need its own client? | No |
| Does each request need its own client? | No |
| Can MongoClient be shared across threads? | Yes |
| Does MongoCollection need closing? | No; it is a handle |
| Should cursors be closed? | Yes, especially when using iterators directly |
| Is ClientSession thread-safe? | No; never use concurrently |
| Does every new MongoClient immediately open maxPoolSize sockets? | No; pools grow per configuration and demand |
| Will enlarging the pool fix an unindexed query? | No |
| Is try-with-resources always wrong? | No; it is wrong when applied to the wrong scope |
| Can Spring Boot manage MongoClient? | Yes, via the application context |
| Does a successful ping prove write permission? | No |
| Should a failed query immediately create a new client? | Usually no |
| Can a closed client still be used? | No |
| Does changing an env URI update a running client? | No |
| Is serverStatus connections only for one app's client? | No |
| Should the full URI be logged? | No, if it contains credentials or sensitive info |

## 29. References

When applying these practices to a project, check the official documentation for your exact **MongoDB Java Driver version**:

- [MongoDB Java Sync Driver — Connect to MongoDB](https://www.mongodb.com/docs/drivers/java/sync/current/connection/)
- [MongoDB Java Sync Driver — Connection Pools](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/)
- [MongoDB Java Sync Driver — Configure MongoClient](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/)
- [MongoDB Java Sync Driver — Connection String](https://www.mongodb.com/docs/drivers/java/sync/current/connection/connection-string/)
- [MongoDB Java Sync Driver — Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/monitoring/)
- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/)
- [MongoDB Manual — Connection Pool Overview](https://www.mongodb.com/docs/manual/administration/connection-pool-overview/)
- [MongoDB Java Driver — API Reference](https://mongodb.github.io/mongo-java-driver/)

URLs may be reorganized across documentation versions. If a page has moved, navigate to Java Sync Driver in the current documentation portal and select the version matching your project dependency.

## 30. Conclusion

A properly lifecycle-managed `MongoClient` is the foundation for a Java application that connects to MongoDB reliably, efficiently, and observably:

~~~text
                         JAVA APPLICATION
                                |
                                v
                    ONE SHARED MongoClient
                     per connection config
                                |
            +-------------------+-------------------+
            |                   |                   |
            v                   v                   v
       OrderRepo           CustomerRepo         InventoryJob
            |                   |                   |
            +-------------------+-------------------+
                                |
                                v
                   Driver connection pools
                                |
                                v
                    MongoDB deployment
                                |
                                v
                 Reuse connections across work

 Shutdown: stop work -> close cursors/sessions -> close owner client
~~~

**Core principles:**

1. **Scope `MongoClient` to the application or job**, never per request, query, or document.
2. **`MongoClient` is thread-safe** and can be shared across repositories and threads.
3. **`MongoDatabase`/`MongoCollection` are lightweight handles**; they do not imply separate sockets or pools per handle.
4. **Connection pools are managed by the driver** and generally exist per server/topology; `maxPoolSize` is an upper limit, not a fixed number of open connections.
5. **Cursors and sessions have shorter lifecycles than the client**; close them in proper scope and never share non-thread-safe objects concurrently.
6. **Only the owner closes the client**, after DB-using work has stopped; frameworks like Spring Boot should manage lifecycle via beans.
7. **Distinguish server selection, pool checkout, connect, socket, and operation timeouts** to debug root causes accurately.
8. **Never use pool size to mask slow queries**; measure command latency, checkout waits, and server capacity while tuning indexing and concurrency.
9. **Account for total service instances when sizing pools**: autoscaling creates more `MongoClient` instances and pools, risking connection storms.
10. **Protect credentials, TLS, and application authorization**, because connection reuse does not replace authentication and business access control.

The key takeaway is that **reusing a properly scoped `MongoClient` is not only a performance optimization—it is responsible resource management**. Applications become far easier to maintain when repositories do not know URIs, threads do not manually manage sockets, cursors/sessions do not outlive workflows, and shutdown has one clear owner. The MongoDB Java Driver already provides pooling and topology monitoring; the application engineer's job is to **create the client at the right boundary, share it properly, and close it only when nothing uses it anymore**.
