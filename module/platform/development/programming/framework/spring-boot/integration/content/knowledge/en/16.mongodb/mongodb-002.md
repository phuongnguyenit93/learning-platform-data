# Connection URI, Database, and `spring.data.mongodb.*` Configuration

## 1. Goal and Context

When integrating MongoDB with Spring Boot, the first thing to clarify is **which MongoDB cluster the application connects to, which identity it uses, and which database it operates on**. A URI might connect to the right host yet authenticate against the wrong database, read the wrong dataset, or apply a timeout policy mismatched to the integration flow.

Within the **SPRING_BOOT_INTEGRATION** module, MongoDB can store business data, read models, integration logs, inbox/outbox records, or workflow state. These flows often also interact with HTTP clients, caches, and message brokers. Therefore, MongoDB configuration must account for data contracts, transactions, error handling, duplicate prevention, testing, and observability—beyond simply “connecting successfully”.

After this lesson, you will be able to:

1. Parse `mongodb://` and `mongodb+srv://` URIs, especially hosts, database, `authSource`, and options.
2. Configure MongoDB connections via `spring.data.mongodb.*` in Spring Boot 3.x.
3. Distinguish the application's target database from the authentication database.
4. Intentionally configure replica sets, TLS, timeouts, connection pools, and read/write concerns.
5. Use the `MongoTemplate` and `MongoRepository` auto-configured by Spring Boot.
6. Diagnose connection errors, protect secrets, and test against a real MongoDB instance.

> **Version scope:** Examples use Java 17+, **Spring Boot 3.x / Spring Data MongoDB 4.x**, and the MongoDB Java Sync Driver aligned with the Spring Boot BOM. The `spring.data.mongodb.*` properties in this lesson follow the Boot 3.x structure. When upgrading to **Spring Boot 4.x**, consult the migration guide and configuration metadata for that exact version because MongoDB property groups were reorganized; do not copy `application.yml` verbatim from 3.x without verification.

## 2. Connection Architecture in Spring Boot

```mermaid
flowchart LR
    APP["Business service / Integration adapter"] --> REPO["MongoRepository"]
    APP --> TPL["MongoTemplate"]
    REPO --> FACT["MongoDatabaseFactory"]
    TPL --> FACT
    FACT --> CLIENT["MongoClient<br/>MongoDB Java Driver"]
    CLIENT --> POOL["Connection pool / TLS / Auth"]
    POOL --> RS[("MongoDB replica set<br/>or sharded cluster")]
    CFG["spring.data.mongodb.*<br/>Environment / Secret"] --> CLIENT
    CFG --> FACT
```

Spring Boot combines Spring Data MongoDB with the MongoDB Java Driver:

| Component | Role |
| --- | --- |
| `MongoClient` | Manages connections and pools to servers in the MongoDB topology. |
| `MongoDatabaseFactory` | Determines how to obtain the `MongoDatabase` for Spring Data operations. |
| `MongoTemplate` | Convenient lower-level API for queries, updates, aggregations, indexes, and other MongoDB operations. |
| `MongoRepository` | Repository API for entities/documents, query methods, and CRUD. |
| `MongoTransactionManager` | Manages client sessions and MongoDB transactions when registered, if supported by infrastructure. |
| `spring.data.mongodb.*` | Declares location, database, credentials, and Spring Data integration settings in Boot 3.x. |

A `MongoClient` should be **reused** along with its connection pool across the application lifecycle. Never create a new `MongoClient` per HTTP request, per Kafka message, or per repository operation.

**Note on lazy connections:** initializing `MongoClient` or the Spring context does not always prove the cluster is reachable. Actual connection establishment and server selection may happen on the first operation. To verify connectivity for real, use a `ping` command, a health indicator, or a controlled read/write test.

## 3. Two MongoDB Connection String Formats

MongoDB uses a connection string/URI to describe the cluster, authentication details, default database, and driver options. There are two main formats.

### 3.1. Standard URI: `mongodb://`

```text
mongodb://[username:password@]host1[:port1][,host2[:port2],...]/[database][?options]
```

Example capturing the topology of a replica set:

```text
mongodb://app_user:<encoded-password>@mongo-1.example.internal:27017,mongo-2.example.internal:27017,mongo-3.example.internal:27017/orders_integration?authSource=admin&replicaSet=rs0&tls=true&retryWrites=true&w=majority
```

In this example:

| Part | Meaning |
| --- | --- |
| `mongodb://` | Uses an explicit host list in standard URI format. |
| `app_user` and password | Connection identity. Password is URI-encoded if it contains special characters. |
| Three hosts | Seed addresses for the driver to discover the replica set; not three independent databases. |
| `/orders_integration` | Default database in the URI, typically the database accessed by the application. |
| `authSource=admin` | Database used to authenticate credentials; not necessarily the business database. |
| `replicaSet=rs0` | Expected replica set name; helps the driver verify topology. |
| `tls=true` | Requires TLS connections. |
| `retryWrites=true` | Allows the driver to retry certain eligible write operations when deployment conditions permit. |
| `w=majority` | Sets write concern: waits for majority acknowledgment per topology. |

The host list in the URI serves **discovery and failover**; it does not mean every operation is written directly to every host by the client. The driver monitors topology and picks the appropriate server based on operation type, read preference, replica set state, and server selection policy.

### 3.2. DNS Seed List URI: `mongodb+srv://`

```text
mongodb+srv://app_user:<encoded-password>@cluster.example.mongodb.net/orders_integration?retryWrites=true&w=majority
```

With the `mongodb+srv://` prefix, the driver queries DNS SRV/TXT records according to MongoDB connection rules to discover endpoints and certain options. This format is common with MongoDB Atlas or environments using DNS SRV:

- The host part is **a single hostname** used for SRV lookup; do not list multiple hosts/ports in an SRV URI.
- TLS is enabled by default for SRV URIs unless overridden by compatible configuration per driver rules; verify actual TLS policy in production.
- Containers/Kubernetes pods must be able to resolve SRV/TXT records and reach the endpoints returned by DNS.
- Do not assume the SRV hostname points to a single server; the driver still needs access to the topology advertised via DNS and MongoDB metadata.

If the environment's DNS does not support SRV or advertised endpoints are blocked by a firewall, the application can fail with a server selection timeout even though the URI syntax is valid.

### 3.3. Encoding usernames and passwords in the URI

Reserved URI characters such as `@`, `:`, `/`, `?`, `#`, and `%` in credentials must be **percent-encoded** according to URI syntax. For example, if the logical password is `p@ss:word`, the password portion in the URI must encode reserved characters, such as `p%40ss%3Aword`.

Do not treat URI encoding as security encryption: the string can still be trivially decoded. URIs containing credentials must be managed as **secrets**: supplied via a secret manager/environment and kept out of logs, exceptions, tracing, debug screens, and source code.

When unsure of encoding rules, use a URI builder library or configure username/password separately where supported by your Boot version—never concatenate raw credentials into a connection string manually.

## 4. How Do the Target Database and `authSource` Differ?

This is one of the most common mistakes when integrating MongoDB.

Suppose the application stores data in the `orders_integration` database, while the user `order_app` is created in the `admin` database:

```text
mongodb://order_app:<encoded-password>@mongo.example.internal:27017/orders_integration?authSource=admin
```

The contract of this URI:

- `orders_integration`: the **target database** for collections such as `orders` and `integration_events`.
- `admin`: the **authentication database** where the server looks up the `order_app` account.
- Collection access still depends on the user's roles/privileges; authenticating successfully against `admin` does not grant read/write access to every database.

When a URI contains a username/password **without `authSource`**, MongoDB determines the authentication database from the database path (if present) or the applicable default—typically `admin` when no database is specified. Consequently, changing `/orders_integration` can inadvertently change where the driver looks up the user if `authSource` is not declared explicitly.

### 4.1. URI database path vs. Spring Data's database property

In Spring Boot 3.x there are two common ways to specify the application's database:

```yaml
# Option A: database specified in the URI.
spring:
  data:
    mongodb:
      uri: mongodb://localhost:27017/orders_integration
```

```yaml
# Option B: let Spring Data select the database via a separate property.
spring:
  data:
    mongodb:
      uri: mongodb://localhost:27017
      database: orders_integration
```

In Boot 3.x, `spring.data.mongodb.database` can determine the database used by `MongoDatabaseFactory` even when the URI also includes a database path. Even so, **avoid declaring two different database names** in the URI and the property: it creates confusion about which database is being read/written and affects authentication fallback. If the user authenticates against a different database, specify `authSource=...` explicitly.

A confusing configuration:

```yaml
spring:
  data:
    mongodb:
      uri: mongodb://order_app:secret@mongo:27017/legacy_db
      database: orders_integration
```

Even if Spring Data reads/writes `orders_integration`, the driver may rely on the URI path to determine the authentication source when `authSource` is omitted. Fix this to use **a single source of truth** for the database and an explicit authentication source.

> **Debugging distinction:** the database “the application reads from and writes to” comes from `MongoDatabaseFactory`, whereas the authentication source comes from the MongoDB driver's credential configuration. The two values can legitimately differ.

### 4.2. How to verify the actual database

In a test or an internal-only diagnostic endpoint:

```java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;

public class MongoConnectionCheck {
    private final MongoTemplate template;

    public MongoConnectionCheck(MongoTemplate template) {
        this.template = template;
    }

    public String databaseName() {
        return template.getDb().getName();
    }

    public Document pingServer() {
        return template.executeCommand(new Document("ping", 1));
    }
}
```

`template.getDb().getName()` reports the database name Spring Data is configured to use, but **does not prove network connectivity succeeded**. Only `pingServer()` forces the driver to execute a real command. Never expose full cluster metadata or URIs containing credentials through a public endpoint.

## 5. Dependencies and Auto-Configuration in Spring Boot 3.x

For a Spring MVC/imperative application, the starter:

```xml
<!-- pom.xml: project already uses the corresponding Spring Boot parent/BOM -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

For reactive applications, there is `spring-boot-starter-data-mongodb-reactive` with beans such as `ReactiveMongoTemplate` and `ReactiveMongoRepository`; do not swap synchronous and reactive APIs without evaluating the architecture. This lesson uses the **synchronous** starter to keep the focus on URIs and configuration.

When the right dependencies are present and the application has not defined custom replacement beans, Spring Boot 3.x typically auto-configures:

1. `MongoClient` from connection properties.
2. `MongoDatabaseFactory` selecting the database.
3. `MongoTemplate` using Spring Data converters/mapping.
4. Spring Data MongoDB Repository infrastructure for `MongoRepository` interfaces within scanned packages.

Thus, the application typically only needs to inject `MongoTemplate` or a repository. You do not need to write `MongoClients.create(...)` manually unless you have special requirements such as multiple MongoDB clusters, custom credential providers, or custom topologies.

```mermaid
sequenceDiagram
    participant B as Spring Boot
    participant C as Configuration
    participant D as MongoDB Driver
    participant M as MongoDB
    B->>C: Bind spring.data.mongodb.*
    C-->>B: URI + database + options
    B->>D: Create MongoClient / MongoTemplate
    Note over B,D: Bean creation does not necessarily ping the server
    B->>D: First query / ping
    D->>M: Server selection, auth, TLS, command
    M-->>D: Result / error
    D-->>B: Document or exception
```

## 6. Basic `spring.data.mongodb.*` Configuration

### 6.1. Recommended approach for a cluster: use a URI

```yaml
# application.yml for local environment.
spring:
  application:
    name: order-integration
  data:
    mongodb:
      uri: ${MONGODB_URI:mongodb://localhost:27017/orders_integration}
      auto-index-creation: false
```

In production, set `MONGODB_URI` via the deployment platform's secrets/environment mechanism. Avoid falling back to a local default URI in production without configuration validation, as the application could connect to the wrong cluster or silently create data in an unintended database.

`auto-index-creation: false` establishes a controlled index governance policy: indexes are created via migrations/deployment rather than unexpectedly at application startup. If auto-index creation is enabled, test the impact of index builds, unique constraints, and schema changes before deploying.

### 6.2. Separate host/port/database/credential properties

For a single server or simple setup, individual fields can be declared:

```yaml
# application-local.yml: ALTERNATIVE to URI, do not combine with the example above.
spring:
  data:
    mongodb:
      host: localhost
      port: 27017
      database: orders_integration
      username: ${MONGODB_USERNAME}
      password: ${MONGODB_PASSWORD}
      authentication-database: admin
```

If username/password are not used locally, omit those fields entirely rather than leaving dummy credentials and expecting the server to ignore them. Property names like `authentication-database` belong to Spring Boot 3.x; they differ from the MongoDB driver URI option `authSource` but serve the same purpose of specifying where authentication occurs.

**Do not configure both a URI and conflicting host/port/username/password properties.** Spring Boot follows version-specific property selection and binding rules; when a URI is present, many driver settings come from the URI. Using a single consistent approach reduces the risk of connecting to the wrong environment.

### 6.3. Common property reference

| Boot 3.x Property | Purpose | Notes |
| --- | --- | --- |
| `spring.data.mongodb.uri` | MongoDB connection string. | Contains host/topology, database, auth, and options. Treat as a secret if credentials are present. |
| `spring.data.mongodb.host` | Host for simple connections. | Prefer URI for replica sets/SRV/multi-host setups. |
| `spring.data.mongodb.port` | MongoDB port. | Usually 27017, depending on environment. |
| `spring.data.mongodb.database` | Database used by Spring Data. | Avoid differing from the URI's database path. |
| `spring.data.mongodb.username` | Connection username. | Pair with password and authentication database as needed. |
| `spring.data.mongodb.password` | Connection password. | Secret; never commit real values. |
| `spring.data.mongodb.authentication-database` | Authentication database when using separate fields. | Equivalent in purpose to `authSource` in a URI. |
| `spring.data.mongodb.auto-index-creation` | Whether to auto-create indexes from mapping annotations. | Typically `false` when managing indexes via migrations. |
| `spring.data.mongodb.gridfs.database` | Dedicated database for GridFS if GridFS is used. | Only needed when storing files via GridFS. |

Options such as `maxPoolSize`, `serverSelectionTimeoutMS`, or `retryWrites` are **MongoDB driver URI options**—do not invent properties like `spring.data.mongodb.max-pool-size` or `spring.data.mongodb.retry-writes` expecting Boot to recognize them.

## 7. Production URI Configuration

Example standard URI with driver options:

```text
mongodb://app_user:<encoded-password>@mongo-1.example.internal:27017,mongo-2.example.internal:27017,mongo-3.example.internal:27017/orders_integration?authSource=admin&replicaSet=rs0&tls=true&retryWrites=true&w=majority&appName=order-integration&serverSelectionTimeoutMS=5000&connectTimeoutMS=2000&socketTimeoutMS=10000&maxPoolSize=40&maxConnecting=4&waitQueueTimeoutMS=3000
```

These values are **illustrative examples**, not a universal preset. Analyze each group:

### 7.1. Server selection and timeouts

| URI Option | Effect | What to Watch Out For |
| --- | --- | --- |
| `serverSelectionTimeoutMS` | Limits how long the driver waits to find an eligible server for the operation. | Can time out due to topology/network issues, not just slow queries. |
| `connectTimeoutMS` | Limits how long establishing a socket connection can take. | Not the timeout for the entire business flow. |
| `socketTimeoutMS` | Socket operation wait time per driver semantics. | Can time out operations when the server takes long; verify per driver/version. |
| `waitQueueTimeoutMS` | Limits how long an operation waits to acquire a connection from the pool. | Surfaces saturation instead of waiting indefinitely. |
| `appName` | Tags the client name in connection metadata. | Helpful for diagnostics; avoid putting user/tenant IDs in the name. |

For instance, a command timeout after sending does not prove MongoDB did not process the write. For commands with side effects that are retried by the application, use a business key/unique index or an appropriate idempotency mechanism.

### 7.2. Connection pool

`MongoClient` manages connection pools per server/topology. Options:

- `maxPoolSize`: maximum number of connections held in the pool to a single server.
- `minPoolSize`: minimum number of connections the pool tries to maintain, if configured.
- `maxConnecting`: limits how many connections can be established concurrently per pool.
- `waitQueueTimeoutMS`: how long an operation waits for an available connection when the pool is busy.

Pool size must be balanced against instance/pod count, HTTP request concurrency, Kafka listeners, and the cluster's connection limits. If each pod sets max pool size to 100 and you scale to 50 pods, total potential connections far exceed a single pod. Increasing `maxPoolSize` does not fix missing indexes or slow downstreams.

Never create a new `MongoClient` per event just to switch databases; doing so creates separate pools and puts pressure on the database cluster. For multi-tenancy, explicitly design a database-per-tenant, collection-per-tenant, or tenant-field strategy, bounding allowed database names and pools instead of switching databases dynamically from arbitrary HTTP headers.

### 7.3. TLS and authentication

- Enable `tls=true` over untrusted networks or when the cluster requires TLS. Hostnames must match the server certificate.
- Configure the truststore/CA and corresponding Java TLS settings per infrastructure policy. Never disable hostname or certificate verification just to get a connection working.
- Grant user privileges according to **least privilege**: the application account should only read/write the required databases/collections.
- Separate migration/admin accounts from runtime business accounts.
- Manage credentials via a secret manager, support rotation, and avoid printing the full URI in logs.
- With SRV or managed clusters, verify the actual authentication mechanism: SCRAM, x.509, AWS IAM/OIDC, or whatever the provider supports; do not apply one username/password setup blindly across environments.

### 7.4. Replica set and durability policies

`replicaSet=rs0` must match the actual replica set name. A multi-host URI without a matching topology can cause primary selection failures or slow failover.

Options affecting durability and consistency:

| Option | Meaning | Common Misconceptions |
| --- | --- | --- |
| `retryWrites=true` | Driver can retry certain eligible writes on transient errors. | Does not guarantee every business command executes only once. |
| `w=majority` | Waits for majority write concern acknowledgment per topology. | Does not replace schema rules, unique indexes, or application transactions. |
| `readPreference=primary` | Prefers reading from the primary. | Selects the read target; does not automatically guarantee a consistent snapshot across multiple requests. |
| `readConcernLevel=majority` | Requires reads to return majority-committed data. | Not equivalent to a distributed transaction across HTTP/Kafka/database. |

Coordinate read/write concerns and sessions based on requirements. If a flow reads immediately after writing and needs causal consistency, evaluate sessions, topology, and read/write concerns rather than assuming secondary reads will always see recent writes.

## 8. Separating Local, Test, and Production Environments

Environments differ in DNS, TLS, data, and access rights. Rather than hardcoding production clusters in code, let Boot load configuration externally:

```yaml
# application.yml: choose a single configuration path via URI.
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
      auto-index-creation: false
```

Corresponding environment variable examples:

```text
# Local development (MongoDB actually running on this machine)
MONGODB_URI=mongodb://localhost:27017/orders_integration

# CI integration test (provided by test framework)
MONGODB_URI=mongodb://test-mongo:27017/orders_it

# Production (structural example, secret loaded from secret manager)
MONGODB_URI=mongodb+srv://<user>:<encoded-password>@cluster.example.mongodb.net/orders_integration?retryWrites=true&w=majority
```

**Never commit real production credentials into version-controlled files.** Inside Docker, `localhost` points to the container itself; if MongoDB runs in another container, use the DNS service name on the network or the platform-provided endpoint. On Kubernetes, ensure service/DNS, routing, network policies, and trust chains match the cluster environment.

### 8.1. Startup configuration checks

A helpful startup checklist:

1. Verify `MONGODB_URI` is present in production.
2. Validate that the scheme/host and database are on an allowlist without printing credentials.
3. Verify connectivity via a health indicator/ping (if required by production readiness).
4. Confirm critical indexes already exist before consuming messages.
5. Verify retry, timeout, connection pool, and metrics settings match instance counts.

When DNS, certificates, or credentials are missing, the application may start up and only fail on the first command. Therefore, health checks and integration tests should exercise a real operation rather than merely verifying the `MongoTemplate` bean exists.

## 9. Using `MongoTemplate` and `MongoRepository` with the Configured Database

Suppose `order-service` records an integration event for reconciliation. Define a document in `IntegrationAudit.java`:

```java
package com.example.integration.mongo;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "integration_audit")
public record IntegrationAudit(
    @Id String id,
    String sourceSystem,
    String eventType,
    Instant receivedAt
) {}
```

When Spring Data maps an `IntegrationAudit`, the `id` field maps to the MongoDB document's `_id`. The collection is `integration_audit` **within the configured database**, such as `orders_integration`.

### 9.1. Using a repository

```java
package com.example.integration.mongo;

import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface IntegrationAuditRepository
    extends MongoRepository<IntegrationAudit, String> {

    List<IntegrationAudit> findByEventType(String eventType);
}
```

A business service can inject the repository:

```java
import java.time.Instant;
import org.springframework.stereotype.Service;

@Service
public class IntegrationAuditService {
    private final IntegrationAuditRepository repository;

    public IntegrationAuditService(IntegrationAuditRepository repository) {
        this.repository = repository;
    }

    public void recordReceivedEvent(
        String eventId,
        String sourceSystem,
        String eventType
    ) {
        repository.save(new IntegrationAudit(
            eventId,
            sourceSystem,
            eventType,
            Instant.now()
        ));
    }
}
```

This example illustrates configuration and mapping. **Do not treat `save(...)` on the same `_id` as sufficient for all deduplication problems**: it can overwrite an existing document and trigger duplicate side effects if surrounding logic is not idempotent. When you need to prevent reprocessing an event, use a unique constraint/checked insert or an explicit transaction/inbox.

### 9.2. Using `MongoTemplate` directly

```java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Component;

@Component
public class AuditQueryGateway {
    private final MongoTemplate template;

    public AuditQueryGateway(MongoTemplate template) {
        this.template = template;
    }

    public List<IntegrationAudit> findBySource(String sourceSystem) {
        Query query = Query.query(
            Criteria.where("sourceSystem").is(sourceSystem)
        );
        return template.find(query, IntegrationAudit.class);
    }
}
```

Like the repository, this `MongoTemplate` uses the database selected by `MongoDatabaseFactory`. It does not automatically switch databases whenever a method receives a different `sourceSystem`/tenant; if the application uses multiple databases, design explicit routing and guard database names against untrusted input.

## 10. Indexes, Duplicate Writes, and Data Contracts

In flows consuming events from Kafka or RabbitMQ, messages can be redelivered after crashes or rebalances. MongoDB supports storage-level idempotency via unique indexes or single-document atomic operations.

Example inbox collection design:

```javascript
// Mongo shell: run via a controlled migration or provisioning task.
db.processed_events.createIndex(
  { consumerName: 1, eventId: 1 },
  { unique: true, name: "uq_consumer_event" }
);
```

Because of this index, two consumers attempting to insert the same `(consumerName, eventId)` cannot both create a marker. However, **writing a marker and then calling HTTP/email outside a transaction** can still lose side effects if the subsequent step fails.

### 10.1. Distinguishing single-document atomicity from multi-step flows

| Scenario | MongoDB Guarantee | What Must Be Added |
| --- | --- | --- |
| Updating one document with a single eligible command | Operations on a single document are atomic. | Version/ID conditions if needed to prevent stale overwrites or duplicates. |
| Two workers inserting the same unique key | Unique index blocks two duplicate records. | Classify intentional duplicates; do not mask schema errors. |
| Writing a marker to collection A and a projection to collection B | Not automatically atomic as two separate writes outside a transaction. | Multi-document transaction or single-document design. |
| Committing MongoDB then publishing to Kafka | Process can crash before sending the message. | Transactional outbox/CDC and idempotent consumers. |
| Processing an event then committing Kafka offset | Can crash after DB commit but before offset commit. | Inbox/dedup to remain safe on redelivery. |
| Calling HTTP/payment after MongoDB commit | MongoDB cannot roll back an external provider. | Stable idempotency key, inquiry, saga/compensation. |

For state-setting updates, prefer conditional commands with version/sequence guards in a single atomic update rather than unprotected read-modify-write. For balance increments/decrements, never assume `$inc` is inherently idempotent: replaying the same command will increment/decrement again.

### 10.2. MongoDB transactions

When multi-document transactions are genuinely needed and MongoDB runs on a **replica set or transaction-capable sharded cluster**, register a transaction manager:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration(proxyBeanMethods = false)
public class MongoTransactionConfiguration {

    @Bean
    MongoTransactionManager mongoTransactionManager(
        MongoDatabaseFactory databaseFactory
    ) {
        return new MongoTransactionManager(databaseFactory);
    }
}
```

When calling a service method through a Spring proxy, `@Transactional` can bind MongoDB writes to the same session/transaction, provided templates/repositories use the corresponding factory and transaction infrastructure.

**Do not assume standalone MongoDB supports multi-document transactions.** Never treat a MongoDB transaction as a shared transaction with PostgreSQL, Kafka, or an HTTP API; cross-system coordination still requires outbox, inbox, idempotency, and reconciliation.

## 11. Handling Connection Errors and Data Errors

A syntactically valid URI that fails to read data can stem from many causes. Separate them clearly:

| Symptom | Possible Cause | How to Verify |
| --- | --- | --- |
| `MongoTimeoutException` on query/ping | Unable to select an eligible server within the timeout. | DNS, firewall, advertised endpoints, replica set state, latency. |
| `MongoSecurityException` | Wrong username/password or authentication source. | Check which database owns the user, mechanism, secret rotation. |
| TLS/certificate error | Incompatible CA/truststore, hostname, or TLS version. | Check trust chain and hostname from the actual runtime environment. |
| Empty database despite successful connection | Pointing to the wrong database/cluster or credentials see a different dataset. | `MongoTemplate.getDb().getName()`, env/profile, collection names. |
| `DuplicateKeyException` in Spring Data | Unique index violation on insert/update. | Inspect index and business ID; distinguish valid replay from conflicting data. |
| Unauthorized error on create index | Runtime user lacks DDL privileges. | Separate migration user from runtime user; check `auto-index-creation`. |
| Pool wait/connection timeout | Slow queries, undersized pool, scaled-up instances, overloaded server. | Pool metrics, slow queries, indexes, topology, and capacity. |
| SRV URI fails to resolve | Missing or blocked DNS SRV/TXT records. | Check DNS from inside the container/pod, not just the developer laptop. |
| Failover causes temporary timeout spikes | Replica set election/server selection. | Check topology events, retryable errors, timeout budgets. |

Some MongoDB driver errors are translated by Spring Data into `DataAccessException` subtypes; in other cases raw driver exceptions surface. **Retry only errors classified as recoverable**, keep the same business identifier for non-read-only operations, and bound total attempts and duration.

### 11.1. Do not equate network errors with “not found”

When `repository.findById(id)` returns `Optional.empty()` after a successful query, the document may genuinely not exist. But server selection timeouts, bad auth, or decode errors are **integration errors**, not “not found”. Never catch all exceptions and return empty/default data: doing so hides outages and can cause duplicate creation or wrong business decisions.

## 12. Testing Connectivity and Database Behavior with Real MongoDB

Unit tests mocking `MongoTemplate` do not verify URIs, TLS, authentication, indexes, or BSON mapping. To validate configuration, run a MongoDB test container, CI replica set, or appropriate test cluster.

### 12.1. Test dependencies

```xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>mongodb</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
```

Example for a Testcontainers stack compatible with Spring Boot 3.x; use BOM-managed dependency versions. Docker must be available in the CI environment to launch test containers.

### 12.2. `@DataMongoTest` + Testcontainers

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@DataMongoTest
@Testcontainers
class MongoConnectionConfigurationTest {

    @Container
    static final MongoDBContainer mongo =
        new MongoDBContainer("mongo:7.0");

    @DynamicPropertySource
    static void registerMongoProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.mongodb.uri",
            () -> mongo.getReplicaSetUrl("orders_it")
        );
    }

    @Autowired
    MongoTemplate template;

    @Test
    void usesConfiguredDatabaseAndCanExecuteCommand() {
        assertThat(template.getDb().getName())
            .isEqualTo("orders_it");

        Document result =
            template.executeCommand(new Document("ping", 1));

        assertThat(((Number) result.get("ok")).doubleValue())
            .isEqualTo(1.0);
    }
}
```

In this test, `getReplicaSetUrl("orders_it")` builds a URI pointing to the test database on the container, and `DynamicPropertySource` overrides the URI before Spring builds the client. `ping` genuinely opens a connection and executes a command. If the test runs alongside an `application.yml` setting `spring.data.mongodb.database` to a different name, remove or override that property to avoid conflicts; the test should verify the exact target database.

**Environment note:** image names, Testcontainers APIs, and dependencies may differ in newer major versions; choose modules and versions aligned with your project's BOM rather than mixing Testcontainers 1.x/2.x configurations arbitrarily.

### 12.3. Key test matrix

| Test | What to Prove |
| --- | --- |
| URI with database path | Spring Data selects the expected database. |
| `authSource` different from target database | Authentication succeeds and has permissions on the intended collection. |
| Password with special characters | URI percent-encoding is valid; no parser/auth failure. |
| SRV URI | DNS SRV/TXT resolves from inside the actual container/pod. |
| Mandatory TLS | Connection succeeds with valid trust and fails with invalid trust. |
| Replica set failover | Driver recovers within defined timeout/retry policy. |
| Unique index | Two writes with the same business key cannot create duplicate records. |
| Transaction | Writes within a transaction commit/rollback together as required. |
| Wrong database | Test catches the application pointing to the wrong DB instead of silently using an empty DB. |
| Pool/timeout | When MongoDB is slow or unreachable, the client does not block threads indefinitely. |
| Health | Probe confirms the cluster executes real commands, not just that a bean exists. |

For production, provide a read-only/`ping` smoke test or a dedicated non-sensitive collection check. Never let a readiness probe write/delete real business data on every check.

## 13. Operational Observability and Security

### 13.1. Health checks and metrics

With Spring Boot Actuator, the system can expose/use the MongoDB health indicator (when the bean and corresponding auto-configuration conditions apply). Monitor:

- Server selection time, pool checkout time, and active/waiting connection counts.
- Query, write, and transaction latency, plus timeout and retry rates.
- Authentication, TLS, network, and topology/failover errors.
- HTTP/Kafka requests waiting on the database, consumer lag, or outbox backlog when MongoDB slows down.
- Collection/index growth, slow queries, document sizes, and write concern failures.

Driver metrics/command monitoring must be configured to match your actual observability stack. Only attach low-cardinality labels such as operation, collection, outcome, and exception class; avoid using customer IDs, document IDs, or full URIs as metric tags.

### 13.2. Logs and secrets

Never log `spring.data.mongodb.uri` directly when it contains a username/password. Log only safe, necessary attributes such as database name, sanitized cluster alias, application name, health check outcome, and exception category.

When debugging:

1. Check active profiles/env without printing full secrets.
2. Confirm `MongoTemplate.getDb().getName()` matches the expected database.
3. Run a `ping` or a controlled read query.
4. Inspect cluster topology, ACLs, and indexes.
5. Cross-check pool metrics, timeouts, and request latency.

Never escalate a database user to `admin` or disable TLS hostname verification just to make errors disappear.

## 14. Common Configuration Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Omitting the database path in the URI with no `database` property | Application may fail to pick the intended database or use an unexpected default. | Declare the database explicitly and test it. |
| Mistaking `authSource` for the data storage database | Authentication fails or data lands in an unexpected DB. | Distinguish the business database from the authentication database. |
| Conflicting URI and `spring.data.mongodb.database` | Hard to debug; risk of wrong database or auth fallback. | Single source of truth and explicit `authSource`. |
| Unencoded `@`/`:` in a URI password | URI parsing fails, authentication fails. | Percent-encode credentials or use appropriate credential properties. |
| Copying `mongodb://localhost` into a container | Connects to the application container itself. | Use the DNS service/cluster endpoint. |
| Using an SRV URI where pod DNS lacks SRV support | Server selection timeout. | Verify SRV/TXT resolution and outbound network access. |
| Enabling `retryWrites=true` and assuming all workflows are idempotent | Duplicate side effects or event replays still occur. | Business IDs, unique indexes, inbox/outbox. |
| Setting `maxPoolSize` too high on every pod | Cluster overwhelmed by connections. | Multiply by total instance count and measure pool utilization. |
| Enabling `auto-index-creation` arbitrarily in production | Unexpected index builds; can fail if duplicate data exists. | Controlled migration/index provisioning. |
| Expecting MongoDB `@Transactional` to work on standalone | Transactions are not supported as on a replica set/sharded cluster. | Use a supported topology and transaction manager. |
| Treating startup success as proof of DB connectivity | Application fails only on the first request. | Ping/readiness probe and integration tests. |
| Catching all MongoDB exceptions and returning empty results | Masks downtime and causes wrong business decisions. | Classify network/auth/not-found/schema errors. |
| Putting the full URI or user ID in metric tags | Leaks secrets and explodes cardinality. | Standardize labels and apply redaction. |

## 15. Connection Setup Workflow in Real Projects

1. **Choose database and topology:** standalone only where suitable locally; replica set/sharded cluster for availability, transactions, and production.
2. **Define authentication:** which database stores the user, what privileges are needed, and which auth/TLS mechanisms apply.
3. **Pick one configuration style:** database in the URI or `spring.data.mongodb.database`; do not mix conflicting host/port properties.
4. **Manage secrets:** store URIs/credentials in a secret manager; never commit or log passwords.
5. **Configure timeouts/pool:** server selection, connect, socket, wait queue, and max pool sized for concurrency and SLOs.
6. **Configure Spring Data:** pick the right sync/reactive starter, inject `MongoTemplate`/repositories, manage indexes via migrations.
7. **Finalize transactions and idempotency:** when flows involve Kafka, HTTP, or multiple collections, define atomic boundaries and inbox/outbox mechanisms.
8. **Test against the real target database:** Testcontainers/cluster tests covering ping, CRUD, unique indexes, auth/TLS, and failover scenarios.
9. **Monitor:** health, latency, pool, topology, auth errors, slow queries, and integration adapter backlogs.

**Self-check questions**

1. In the URI `mongodb://u:p@mongo:27017/orders_integration?authSource=admin`, which database stores data and which authenticates the user?
2. How does `mongodb+srv://` differ from `mongodb://` regarding host discovery and TLS?
3. Why should a URI not point to `legacy_db` while `spring.data.mongodb.database` points to `orders_integration`?
4. How does `serverSelectionTimeoutMS` differ from `connectTimeoutMS` and `waitQueueTimeoutMS`?
5. Why does a successfully started Spring context not prove MongoDB is reachable?
6. Why does `retryWrites=true` not guarantee a Kafka event is applied exactly once to business state?
7. When a MongoDB transaction commits and a Kafka publish fails, what mechanism is needed to avoid losing the event?
8. Why must total connection pool size be evaluated across all pods rather than for a single instance?

## 16. References

- [Spring Boot 3.5 — Working with NoSQL Technologies: MongoDB](https://docs.spring.io/spring-boot/3.5/reference/data/nosql.html#data.nosql.mongodb): auto-configuration, MongoDB properties, templates, and repositories.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): reference for `spring.data.mongodb.*` property names in version 3.5.
- [Spring Data MongoDB — Reference Documentation](https://docs.spring.io/spring-data/mongodb/reference/): mapping, `MongoTemplate`, repositories, indexes, and transactions.
- [MongoDB — Connection String Formats](https://www.mongodb.com/docs/manual/reference/connection-string/): standard/SRV URI syntax, database path, and authentication options.
- [MongoDB — Connection Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/): TLS, retry writes, read/write concern, timeouts, and pool options.
- [MongoDB Java Sync Driver — Connection Guide](https://www.mongodb.com/docs/drivers/java/sync/current/connection/): `MongoClient`, server selection, and connection pooling.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): integrating Testcontainers in application tests.
