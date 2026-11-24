# TLS, Authentication, and Least-Privilege Data Access with MongoDB in Spring Boot

A Spring Boot service may connect to MongoDB, read, and write documents cleanly in development and still **fail production security requirements**. Common pitfalls include: clients talking to MongoDB over unencrypted connections; TLS connections accepting any certificate; applications running as `root`; multiple services sharing a single password; APIs taking `tenantId` straight from request payloads and reading another tenant's documents; or ops teams granting admin rights just to turn a health check green.

The **MongoDB** chapter of the **SPRING_BOOT_INTEGRATION** module treats MongoDB as a dependency within Spring Boot integration flows across HTTP clients, databases, caches, message brokers, and Spring Integration adapters. Therefore, beyond wiring the client, this lesson covers **data contracts, access control, transactions, idempotency, auth errors, testing, observability, and secure operations**.

Three independent objectives must all be satisfied:

1. **TLS**: protects connection confidentiality and integrity while authenticating the MongoDB server's identity.
2. **Authentication**: verifies **which client/service** is permitted to connect to MongoDB.
3. **Least-privilege authorization**: after authentication, restricts the service strictly to **necessary actions** on the target databases/collections.

A valid TLS connection **does not** mean the database account has safe privileges. A narrow collection role **does not** encrypt traffic on the wire. And collection-level MongoDB RBAC **does not isolate documents by tenant automatically**.

> **Version scope:** Examples target Spring Boot 3.x, Spring Data MongoDB 4.x, and MongoDB Java Driver 4.x/5.x. Some Spring Boot 3.x lines provide SSL bundles, while property names and customizer mechanics vary across minor versions. Server examples assume MongoDB versions supporting SCRAM-SHA-256, TLS, and role-based access control (RBAC). When upgrading Boot/driver/MongoDB or using MongoDB Atlas, verify the exact configuration and privilege model supported by your deployment.

## 1. Threat Model: What Are We Protecting?

Suppose `order-service` stores `orders`, `processed_events`, and `outbox_events` in the `orders` database. A REST controller accepts order creation requests; a worker consumes RabbitMQ events and updates payment state; an outbox relay reads unpublished outbox documents and forwards them to the broker.

~~~mermaid
flowchart TD
    USER["HTTP caller"] --> API["Spring Boot order-service"]
    API --> AUTH["Authenticate caller + verify tenant"]
    AUTH --> MONGOCLIENT["Singleton MongoClient / TLS"]
    MONGOCLIENT --> SERVER["MongoDB cluster"]
    SERVER --> ORD[("orders")]
    SERVER --> INBOX[("processed_events")]
    SERVER --> OUTBOX[("outbox_events")]
    OUTBOX --> RELAY["Outbox relay with dedicated MongoDB identity"]
    RELAY --> MQ[("RabbitMQ / Kafka")]
    ADMIN["Migration/operator identity"] --> SERVER
~~~

Key threats:

| Attack Vector / Mistake | Example | Appropriate Control |
| --- | --- | --- |
| Network eavesdropping | A network node sniffs order payloads | TLS on client–MongoDB connections |
| Rogue database server | DNS/proxy redirects client to a spoofed endpoint | Trusted CA, hostname/SAN verification, proper TLS |
| Credential exposure | Password-bearing URI logged or committed to Git | Secret manager, workload identity if supported, rotation |
| Compromised app account | Attacker abuses service's `root` DB account | Privileges scoped strictly to required collections |
| Over-privileged worker | Worker can execute `dropDatabase` | Custom roles separating DDL from runtime |
| Cross-tenant access | Caller swaps `tenantId` in JSON body | App-layer authentication; all queries scoped by tenant |
| NoSQL query injection | JSON input containing `$ne`, `$where` passed straight as filter | Typed DTOs, validation, query builders |
| Retries after network errors | Document committed yet caller timed out | Idempotency keys, unique indexes, outcome reconciliation |
| Data leaks in logs/metrics | Full documents, connection URIs, certificate keys | Redaction, data classification, access limits |
| Non-Mongo dependency failure | DB transaction commits yet broker publish fails | Transactional outbox and dedicated relay worker |

**Security boundaries** do not stop at MongoDB authentication: HTTP/broker ingress must authenticate callers; the application must protect identities and payloads; infrastructure must secure network paths, certificates, secrets, and backups.

## 2. What TLS Protects and What It Does Not Protect

The MongoDB wire protocol carries queries, responses, and admin commands over TCP; TLS provides encryption, server certificate authentication, and integrity protection in transit.

A secure TLS handshake typically involves:

1. Client opens TCP to the configured hostname/port (possibly via a load balancer).
2. Server presents its certificate chain.
3. Client verifies the certificate is signed by a trusted CA, unexpired, valid for server authentication, and **the hostname matches a Subject Alternative Name (SAN)**.
4. Both sides negotiate a policy-compliant protocol/cipher suite.
5. Once TLS succeeds, MongoDB proceeds to **client authentication** (SCRAM, X.509, etc.).

~~~mermaid
sequenceDiagram
    participant C as Java MongoDB Driver
    participant S as MongoDB Server
    C->>S: TCP connect (hostname)
    C->>S: TLS ClientHello / SNI
    S-->>C: Certificate chain
    Note over C: Verify CA, validity, SAN hostname
    C->>S: TLS handshake finished
    C->>S: MongoDB authentication (e.g. SCRAM)
    S-->>C: Auth success / auth failure
    C->>S: find / insert / update per RBAC
    S-->>C: Result or Unauthorized
~~~

TLS **does not** protect data once decrypted inside JVM memory, JSON returned to HTTP callers, unencrypted disk backups, application query logs, or overly broad DB roles.

### Anti-patterns to avoid

- `tls=false` or plaintext connections to production MongoDB when encryption is required by policy.
- `invalidHostNameAllowed(true)` or equivalents disabling hostname verification.
- Trust-all trust managers, or ad hoc truststores trusting arbitrary leaf certs without rotation processes.
- Connecting by raw IP when the certificate only has a DNS SAN, then disabling hostname verification to “make it work”.
- Terminating TLS at an intermediate proxy/sidecar while assuming the hop onward to MongoDB is automatically encrypted.
- Printing private keys, truststore passwords, or credential-bearing URIs in handshake error logs.

**An “encrypted” connection without server identity verification still permits man-in-the-middle attacks.** Skipping hostname verification defeats peer authentication.

## 3. Spring Boot: Configuring `MongoClient` and TLS per Environment

With imperative Spring Data MongoDB, a typical Maven project uses:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
~~~

Spring Boot auto-configuration creates `MongoClient` and `MongoTemplate` from MongoDB properties when no custom replacement bean overrides them. The Java driver's `MongoClient` manages connection pools, server selection, cluster monitoring, and authentication; **reuse it as a singleton** rather than creating one per HTTP request or message.

Configure in `application.yml`:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
~~~

**Structural example** of an environment variable with a percent-encoded password and DNS SANs matching the server certificate:

~~~text
MONGODB_URI=mongodb://order_app:<encoded-secret>@mongo-0.db.example:27017,mongo-1.db.example:27017/orders?authSource=orders&authMechanism=SCRAM-SHA-256&replicaSet=rs0&tls=true
~~~

This is a **template**, not a URI with real credentials. Breakdown:

- `mongodb://`: driver connection scheme; `mongodb+srv://` uses DNS SRV/TXT discovery where supported.
- `order_app:...`: MongoDB principal and password—**not** the HTTP caller's identity.
- `mongo-0.db.example,mongo-1.db.example`: hostnames matching certificate SANs and topology.
- `/orders`: client's default database.
- `authSource=orders`: database holding the `order_app` user in this example.
- `authMechanism=SCRAM-SHA-256`: enforces the authentication mechanism configured on the server.
- `replicaSet=rs0`: verifies the client connects to the expected replica set.
- `tls=true`: enables TLS on the driver; the server must also be configured for TLS.

**Never store plaintext passwords in repository files** and never log full `MONGODB_URI` values. If a password contains `@`, `:`, `/`, `?`, `#`, or `%`, URI-encode it properly in userinfo; encoding mistakes trigger parse/auth errors or route to the wrong host.

With `mongodb+srv://`, host discovery and TLS defaults have specific behavior; verify actual driver config and TLS policies in your target environment rather than guessing.

### URI vs. separate properties

Do not mix host/port/username/password properties with a URI without knowing your Boot version's exact precedence rules. Keep one URI as the **authoritative config source**, or define explicit `MongoClientSettings` when managing multiple clusters/tenants. With Spring Boot auto-config, declaring a custom `MongoClient` bean causes auto-configuration to back off, which can disable customizers and SSL bundles you expected to apply.

## 4. CAs, Truststores, SSL Bundles, and Hostname Verification

On internal networks, MongoDB often uses certificates signed by an internal CA. The JVM will not trust that private CA unless the **public CA certificate** (never the CA private key) is placed in an appropriate truststore.

### Option 1: JVM truststore

When the driver uses the default JSSE TLS context, a truststore can be supplied via JVM system properties:

~~~bash
java \
  -Djavax.net.ssl.trustStore=/run/secrets/mongo-truststore.p12 \
  -Djavax.net.ssl.trustStorePassword="$MONGO_TRUSTSTORE_PASSWORD" \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -jar app.jar
~~~

This command demonstrates the concept; in production, **passwords passed via command-line/process arguments can be exposed to OS tools and admins**. Prefer mounted secrets with a per-client SSL context or SSL bundle to keep secrets off command lines. A JVM-wide truststore also affects every other HTTP/TLS client in the JVM; if you need **distinct trusted CAs per downstream**, use per-client TLS configuration.

### Option 2: Spring Boot SSL bundle and `MongoClientSettingsBuilderCustomizer`

On Spring Boot versions **supporting SSL bundles** (3.1+), define a named JKS/PKCS12 truststore bundle:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
  ssl:
    bundle:
      jks:
        mongo-client:
          truststore:
            location: file:/run/secrets/mongo-truststore.p12
            password: ${MONGO_TRUSTSTORE_PASSWORD}
            type: PKCS12
~~~

To apply this bundle explicitly to the Boot-managed MongoDB driver, register a customizer:

~~~java
import org.springframework.boot.autoconfigure.mongo.MongoClientSettingsBuilderCustomizer;
import org.springframework.boot.ssl.SslBundles;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MongoTlsConfiguration {

    @Bean
    MongoClientSettingsBuilderCustomizer mongoTlsCustomizer(
            SslBundles sslBundles) {

        return settings -> settings.applyToSslSettings(ssl -> ssl
                .enabled(true)
                .context(sslBundles.getBundle("mongo-client")
                        .createSslContext())
                .invalidHostNameAllowed(false));
    }
}
~~~

What this does:

1. `SslBundles` provides an `SSLContext` built from the Boot-managed truststore.
2. `MongoClientSettingsBuilderCustomizer` customizes driver settings during Boot's auto-configuration.
3. `enabled(true)` enforces TLS on this configuration.
4. `invalidHostNameAllowed(false)` preserves hostname verification—**never** “fix” cert errors by setting it to `true`.
5. Avoid declaring manual `MongoClients.create(...)` beans if you rely on this customizer applying to Boot's auto-configured client.

Some Spring Boot minor releases support dedicated SSL bundle properties directly under `spring.data.mongodb.ssl.*`. Where available, **property-only configuration** is preferable to a custom bean—**never configure TLS in two places with conflicting values**. Check the metadata/docs of your exact Boot version, as auto-configuration evolves across releases.

### Hostname must match the certificate

If a certificate lists only SAN `mongo-0.db.example`, never connect via `10.10.1.17` or `localhost` and disable verification. Issue certificates with proper SANs for real hostnames, configure DNS/service discovery properly, or connect via an endpoint covered by the certificate.

Behind a proxy or load balancer, verify which certificate the **driver sees at the TLS peer**, SNI behavior, whether TLS terminates or passes through, and which hostnames are returned during replica set discovery. Reaching the first proxy node does not prove every discovered replica set member presents a valid certificate.

### Managing certificate rotation

Certificates expire; systems need:

- Expiration monitoring well ahead of outages.
- Old/new CA overlap during transition windows where policy permits.
- Valid chains presented by every MongoDB replica.
- Verification of whether the app/driver hot-reloads truststores or needs **client recreation / rolling restart**. Never assume swapping a file on disk updates an already constructed `SSLContext`.
- Testing new connections after rotation, not only pre-existing pooled sockets.

## 5. MongoDB Authentication: SCRAM-SHA-256, `authSource`, and X.509

TLS authenticates the server; **MongoDB authentication** verifies the application principal to the database/cluster. Deployments can support multiple mechanisms, and clients must use an enabled mechanism matching how the account was provisioned.

### SCRAM-SHA-256

Common choice for self-managed MongoDB database users. Key requirements:

- User is created in an **authentication database**; e.g., `order_app` created inside `orders`.
- Client sets `authSource=orders` rather than blindly passing `admin` out of habit.
- Server enables authentication and the matching SCRAM mechanism.
- Strong passwords managed via secret manager with a rotation workflow.
- Roles granted strictly on required databases/collections.

**`authSource` is not the default database you get read/write access to.** It is only where the user record is authenticated. A user authenticated in `admin` can still be granted narrow roles on `orders`, or authenticated in `orders` with roles on specific collections. Actual access depends solely on roles/privileges.

A wrong `authSource` causes `Authentication failed` even when the username/password exist in another database. Test using a restricted test identity rather than switching the app to a cluster admin account.

### X.509 client certificates

MongoDB supports client certificate authentication under **mutual TLS (mTLS)** when configured for MongoDB X.509 auth. Unlike SCRAM:

- Client presents a client certificate and private key during the TLS handshake.
- Server validates the certificate and maps its subject DN to a MongoDB user in `$external` per server rules.
- X.509 users still require explicit **roles**; having a certificate does not grant CRUD privileges.
- Client certificates need policies for EKU, CA, SAN/subject, private key protection, and rotation.

Structural X.509 URI (no password):

~~~text
mongodb://mongo-0.db.example:27017/orders?tls=true&authMechanism=MONGODB-X509&authSource=%24external
~~~

`%24external` is URL-encoded `$external`. Configure **client key material** in the SSL context (keystore with client cert + private key) and register the matching MongoDB user in `$external`. **Merely changing the URI** from SCRAM to X.509 without client key material and user mapping fails authentication.

Never reuse the server's certificate/key as a client credential; keep distinct identities and scopes. With a sidecar/service mesh performing mTLS, mesh-level authentication **does not equal** MongoDB X.509 authentication unless MongoDB itself receives and verifies the client certificate under its supported mechanism.

### Other identity options

MongoDB Atlas and some enterprise setups support cloud identity/OIDC/AWS IAM/Kerberos depending on tier, version, and driver. Never assume an arbitrary connection string activates those mechanisms on self-managed MongoDB. Pick an auth mechanism aligned with your **MongoDB edition, driver version, cluster config, and rotation workflows**.

## 6. Least Privilege in MongoDB RBAC

**RBAC** governs which **actions** a principal can execute on resources—typically databases and collections. Roles bundle privileges or inherit other roles.

Built-in roles are convenient yet frequently broader than necessary:

| Built-in Role | Purpose | Risk if Granted to Runtime Apps |
| --- | --- | --- |
| `read` | Reads data in a database | Can read more collections than the service actually needs |
| `readWrite` | Reads/writes a database per role privileges | Broader than `find/insert/update` on specific collections; may include collection/index actions depending on version |
| `dbAdmin` | Database/index/schema admin tasks | Should not be granted to business services |
| `userAdmin` | Creates/modifies users/roles within scope | Enables indirect privilege escalation; restrict to controlled operations |
| `clusterMonitor` | Cluster monitoring | Do not turn business accounts into monitors just for health stats |
| `root` | Very broad cluster admin rights | Never use as an HTTP service or worker account |

For an `order-service` that only needs to find, insert, and update orders, **collection- and action-scoped custom roles** are cleaner than database-wide `readWrite`.

### Analyzing privileges by operation

| Component | Collection | Expected Actions | Not Needed |
| --- | --- | --- | --- |
| Order API runtime | `orders` | `find`, `insert`, `update` | `dropCollection`, `createIndex`, `remove` if not deleting |
| Inbox idempotency | `processed_events` | `find`, `insert` | `drop`, `remove` |
| Outbox producer | `outbox_events` | `insert` | `remove`, `createIndex` |
| Outbox relay | `outbox_events` | `find`, `update` | Broad access on `orders` |
| Read-only report service | `orders` (or controlled view) | `find` | `insert`, `update`, `remove` |
| Schema migration | Target collections/indexes | Scoped `createCollection`, `createIndex` | Long-lived runtime credentials |
| Responsible administrator | Approved maintenance scope | Per operational runbooks | Never embedded as app credentials |

**Actions** must reflect real driver commands. If a service runs `findAndModify`, change streams, `$out/$merge` aggregations, or index creation, verify the exact required MongoDB privileges for your server version rather than guessing `find` or `update` suffices.

## 7. Creating Narrowly Scoped MongoDB Roles and Users

Example for self-managed MongoDB via `mongosh`, executed **using an appropriately privileged admin account**:

~~~javascript
use orders

db.createRole({
  role: "order_runtime",
  privileges: [
    {
      resource: { db: "orders", collection: "orders" },
      actions: ["find", "insert", "update"]
    },
    {
      resource: { db: "orders", collection: "processed_events" },
      actions: ["find", "insert"]
    },
    {
      resource: { db: "orders", collection: "outbox_events" },
      actions: ["insert"]
    }
  ],
  roles: []
});

db.createUser({
  user: "order_app",
  pwd: passwordPrompt(),
  roles: [{ role: "order_runtime", db: "orders" }]
});
~~~

`passwordPrompt()` prompts interactively so secrets stay out of command history. When collections and indexes are pre-provisioned, the runtime role needs no DDL permissions.

A **separate** identity for the outbox relay:

~~~javascript
use orders

db.createRole({
  role: "outbox_relay",
  privileges: [
    {
      resource: { db: "orders", collection: "outbox_events" },
      actions: ["find", "update"]
    }
  ],
  roles: []
});

db.createUser({
  user: "relay_app",
  pwd: passwordPrompt(),
  roles: [{ role: "outbox_relay", db: "orders" }]
});
~~~

This role layout is **illustrative**, not a script to run verbatim on every Atlas tier or enterprise setup. On MongoDB Atlas, custom roles and database users are typically managed through the Atlas UI/API; follow your platform's workflow. Version-control role, user, and resource definitions via reviewed IaC/automation while keeping passwords out of diffs.

### Never mix administrative users with application users

Never let Spring Boot run `db.createUser`, `db.createRole`, `createIndex`, or `dropCollection` on startup using a long-lived admin runtime identity. Separate:

1. **Migration/deployment identity**: scoped DDL privileges, short-lived or restricted to pipelines.
2. **Runtime service identity**: read/write only on explicitly defined collections.
3. **Outbox/consumer identity**: scoped to its specific workflow.
4. **Operator/backup identity**: administrative/backup access governed by separate roles and procedures.

Separating identities limits blast radius if a container is compromised.

## 8. Least Privilege Must Be Verified with Positive and Negative Tests

An app running smoothly as `root` **proves neither** that runtime privileges are sufficient nor that they are properly bounded. Authorization tests should include both:

- **Positive test**: `order_app` can `find`, `insert`, and `update` valid documents in `orders` and insert into `processed_events`.
- **Negative test**: the same user **cannot** `drop`, `createIndex`, or read ungranted sensitive collections.
- **Cross-service test**: `relay_app` cannot read `orders` just because it accesses `outbox_events`.
- **No-admin fallback**: when permissions fail, the app surfaces errors/alerts rather than falling back to root credentials.
- **Migration boundary test**: migration identity creates indexes; runtime identity fails DDL attempts post-deploy.

Java driver integration test example running with a restricted user:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mongodb.MongoCommandException;
import com.mongodb.client.MongoClient;
import org.bson.Document;
import org.junit.jupiter.api.Test;

class MongoPrivilegeIntegrationTest {

    private final MongoClient restrictedMongoClient;

    MongoPrivilegeIntegrationTest(MongoClient restrictedMongoClient) {
        this.restrictedMongoClient = restrictedMongoClient;
    }

    @Test
    void runtimeCanReadOrdersButCannotDropCollection() {
        var collection = restrictedMongoClient
                .getDatabase("orders")
                .getCollection("orders");

        collection.find(new Document("_id", "ORDER-42")).first();

        assertThatThrownBy(collection::drop)
                .isInstanceOf(MongoCommandException.class)
                .satisfies(error -> assertThat(
                        ((MongoCommandException) error).getErrorCode())
                        .isEqualTo(13)); // MongoDB Unauthorized
    }
}
~~~

This is a **test template**: real projects construct `restrictedMongoClient` with test credentials, pre-create databases/collections via a setup identity, and inject it via JUnit/Spring Test. Never use an admin user for negative tests. MongoDB error code `13` specifically checks `Unauthorized`; TLS or auth errors occurring earlier raise different exceptions and require separate diagnosis.

Mocking `MongoTemplate` to throw `AccessDenied` does not prove the MongoDB server enforces roles; test against a real MongoDB instance with RBAC enabled.

## 9. Separating Database Privileges from Per-Tenant Data Access

Collection- and database-level MongoDB RBAC **does not isolate individual documents by `tenantId`** inside a shared collection. Consider:

~~~json
{
  "_id": "ORDER-42",
  "tenantId": "tenant-a",
  "customerId": "CUSTOMER-9",
  "state": "PAID"
}
~~~

If `order_app` has `find` on `orders`, MongoDB RBAC permits querying documents for **every tenant in that collection**, not only `tenant-a`. The application layer must authenticate callers and scope every query by the verified tenant.

### Spring Data `MongoTemplate` with mandatory scoping

Document DTO:

~~~java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders")
public record OrderDocument(
        @Id String id,
        String tenantId,
        String customerId,
        String state,
        Instant updatedAt
) {
}
~~~

A service querying via `MongoTemplate`:

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class TenantOrderReader {

    private final MongoTemplate mongo;

    public TenantOrderReader(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public OrderDocument getOrder(
            AuthenticatedTenant caller,
            String orderId) {

        Query query = Query.query(
                Criteria.where("_id").is(orderId)
                        .and("tenantId").is(caller.tenantId()));

        OrderDocument result =
                mongo.findOne(query, OrderDocument.class);

        if (result == null) {
            throw new OrderNotFoundException();
        }
        return result;
    }
}
~~~

`AuthenticatedTenant` and `OrderNotFoundException` are application-defined types. **`caller.tenantId()` must originate from an authenticated principal/token or secure session**, never from an arbitrary JSON field supplied by the client.

For updates:

~~~java
Query query = Query.query(
        Criteria.where("_id").is(orderId)
                .and("tenantId").is(caller.tenantId()));

Update update = new Update().set("state", "SHIPPED");

var result = mongo.updateFirst(
        query, update, OrderDocument.class);

if (result.getMatchedCount() != 1) {
    throw new OrderNotFoundException();
}
~~~

**Both reads and writes** must enforce the tenant predicate. A GET endpoint that filters properly still leaves a cross-tenant vulnerability if PATCH or DELETE filters only by `_id`.

### Stronger tenant isolation

When compliance requires **database- or collection-level isolation**, consider separate collections or databases per tenant with dedicated roles/credentials—trading off connection/client counts, migrations, indexes, backups, and access management complexity. Never claim that adding a `tenantId` field gives you MongoDB RBAC document-level authorization.

## 10. Preventing NoSQL Injection and Out-of-Contract Queries

MongoDB query documents use operators like `$ne`, `$gt`, `$in`, `$regex`, and `$where`. Passing an arbitrary client-supplied JSON filter directly to the database lets callers alter query logic maliciously.

Dangerous example (illustrating what **not** to do):

~~~java
// DO NOT DO THIS: caller controls MongoDB query structure.
Document rawFilter = Document.parse(untrustedJsonFilter);
mongo.getCollection("orders").find(rawFilter);
~~~

A caller could pass:

~~~json
{"tenantId":{"$ne":"tenant-a"}}
~~~

Passed straight to MongoDB, this behaves completely differently from matching a string tenant ID. `$where` and other pipeline operators also carry resource-exhaustion risks if exposed.

Defenses:

1. Accept only **typed DTOs** with explicitly supported filter fields.
2. Validate string lengths, enum values, dates, and numeric bounds.
3. Build queries via `Criteria`/Spring Data `Query` or a controlled internal DSL.
4. **Always inject the mandatory tenant scope** from the trusted principal on every query.
5. Allowlist sort fields, projections, and aggregation stages; never let clients pick collections or databases.
6. Enforce query timeouts, limits/pagination, regex constraints, and `$in` array caps.
7. Protect any admin-only query DSL behind separate identities, auditing, and rate limits.

A role granting only `find` does not stop a `find` query from dumping an entire collection. Database least privilege must be paired with **API and application-query least privilege**.

## 11. Protecting Sensitive Data: TLS Is Not Encryption at Rest

There are at least three layers of data protection:

| Layer | Mechanism | Limitation |
| --- | --- | --- |
| In transit | TLS from Java driver to MongoDB | Does not encrypt data inside JVM memory or after decryption |
| At rest | Volume/disk encryption, managed storage encryption, encrypted backups | Database operators and apps with read privileges still see plaintext |
| Field/application level | Client-Side Field Level Encryption (CSFLE), Queryable Encryption, or designed app encryption | Adds key, query, index, and rotation complexity; does not solve general RBAC issues |

TLS and encryption at rest address **different threat boundaries**. When storing government IDs or sensitive tokens, define who may see plaintext, which encrypted fields must remain queryable, and where keys reside in KMS/HSM.

MongoDB CSFLE/Queryable Encryption imposes specific driver, library, schema/`encryptedFields`, key vault, KMS, and query constraints per version. You cannot turn it on simply by flagging `encrypted=true` on a DTO—design key management, backup/restore, rotation, and compatibility tests upfront.

Operational principles:

- Never log raw sensitive data in MongoDB command monitoring/logs.
- Use projections to return only fields the caller actually needs.
- Classify data for retention, deletion, backups, and backup read access.
- Sign/encrypt application tokens per your threat model; never use user-supplied object IDs as authorization grants.
- Audit query plans and projections as data grows; even a “read-only” endpoint can cause DoS via expensive aggregations.

## 12. TLS and Authentication Do Not Solve Transactions, Retries, or Duplicates

Suppose `payment-consumer` consumes a RabbitMQ message, updates `orders`, and inserts into `processed_events`. It can commit MongoDB and drop the broker connection right before ACK; RabbitMQ redelivers the message. Proper TLS and user roles **do not prevent** reprocessing the same event.

### Idempotency in MongoDB

One approach uses a stable unique key per consumer/event:

~~~javascript
db.processed_events.createIndex(
  { consumerId: 1, eventId: 1 },
  { unique: true, name: "uk_consumer_event" }
);
~~~

Only the migration identity holding `createIndex` should run this DDL. The runtime identity needs only `find` and `insert` on this collection.

Event:

~~~java
public record PaymentCaptured(
        String eventId,
        String orderId,
        long amountCents
) {
}
~~~

Within a MongoDB transaction on a supporting topology:

1. INSERT receipt `(consumerId, eventId)`.
2. Update `orders` guarded by valid state/version.
3. Insert `outbox_events` if downstream messaging is needed.
4. Commit the transaction.
5. After commit, the listener completes cleanly so the broker can ACK.

~~~mermaid
sequenceDiagram
    participant MQ as RabbitMQ
    participant C as PaymentConsumer
    participant TX as MongoTransactionManager
    participant DB as MongoDB
    MQ->>C: PaymentCaptured(eventId)
    C->>TX: BEGIN
    TX->>DB: INSERT processed_events unique key
    TX->>DB: UPDATE orders
    TX->>DB: INSERT outbox_events
    TX->>DB: COMMIT
    C--xMQ: ACK lost due to connection error
    MQ->>C: Redelivery with same eventId
    C->>TX: BEGIN / check key
    TX->>DB: Duplicate key / receipt already exists
    Note over C,DB: No duplicate business side effect
    C-->>MQ: ACK after appropriate duplicate handling
~~~

**Note:** if a duplicate INSERT throws inside a transaction, the transaction may abort. Never catch `DuplicateKeyException` and keep issuing MongoDB commands inside **the same failed transaction**. Let the transaction roll back, classify the duplicate outside the transaction boundary, query the receipt cleanly in a new read, and confirm whether the message was already handled. All concurrency races must be guarded by a real unique index rather than an unguarded `find` then `insert`.

### `MongoTransactionManager` and topology requirements

Spring Data MongoDB provides `MongoTransactionManager` for imperative transactions:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration(proxyBeanMethods = false)
public class MongoTransactionConfiguration {

    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory databaseFactory) {
        return new MongoTransactionManager(databaseFactory);
    }
}
~~~

Spring Boot does not always auto-create a Mongo transaction manager bean; to manage Mongo transactions via `@Transactional`, verify the manager exists and points to the right `MongoDatabaseFactory`. **MongoDB multi-document transactions require a supporting topology** such as a replica set or eligible sharded cluster; standard standalone MongoDB does not satisfy those requirements. Local tests on standalone MongoDB can look healthy until multi-document transactions fail.

In projects mixing JDBC and MongoDB, **qualify `@Transactional` explicitly**: e.g. `@Transactional(transactionManager = "mongoTransactionManager")`. A Mongo manager will never commit/roll back PostgreSQL or RabbitMQ in the same ACID transaction; use outboxes, sagas, and reconciliation across SQL/brokers/HTTP.

## 13. Retries, Timeouts, and “Unknown Commit Result”

Errors can surface at multiple stages:

| Error | Meaning | Sound Policy |
| --- | --- | --- |
| TLS handshake untrusted CA | Client rejects server identity | Fix chain/truststore; never enable insecure mode |
| Hostname/SAN mismatch | Server cert does not match endpoint | Fix DNS/certificate/endpoint |
| Authentication failed | Bad user/password/`authSource`/mechanism | Check secrets and config; never retry infinitely with bad credentials |
| Unauthorized (code 13) | Authenticated user lacks privilege | Fix role/operation contract; never switch to `root` |
| Server selection timeout | Driver cannot find an eligible node | Inspect DNS, `replicaSet`, TLS, topology, network |
| Socket/read timeout | Request/response did not finish in time | Outcome uncertain—server may have committed |
| Duplicate key (code 11000) | Unique constraint violated | Distinguish idempotent duplicate from data conflict |
| `TransientTransactionError` label | Transaction failed transiently and may be retried whole per policy | Bounded retry with the same business key |
| `UnknownTransactionCommitResult` label | Client cannot tell if commit succeeded | Retry commit per driver docs or inspect receipt; never blindly re-run business logic |
| Rate/overload/pool pressure | Resource saturation | Backoff, bound concurrency, monitor pools |

Exact Java driver exceptions and how Spring Data translates them to `DataAccessException` vary by code path and version. Never treat every exception as retryable. Classify by **MongoDB error labels, codes, causes, and transaction state**, bounding total attempts and elapsed time.

### Multi-layered timeouts

| Type | Example Driver Configuration | Question |
| --- | --- | --- |
| Connect timeout | `SocketSettings.connectTimeout` | How long to open a TCP socket? |
| Server selection timeout | `ClusterSettings.serverSelectionTimeout` | How long to locate an eligible node? |
| Read/socket timeout | Driver socket settings | How long to wait on network reads? |
| Operation deadline | `timeoutMS`/client-side operation timeout per driver version | How long may the entire operation wait? |
| MongoDB `maxTimeMS` | Per-query/command option | How long may the server execute the operation? |
| Transaction lifetime limit | Server policy | Did the transaction exceed the server's limit? |
| Business deadline | HTTP/broker orchestration | How long may the full workflow across dependencies take? |

Do not mistake `serverSelectionTimeoutMS` for an execution limit on every query—the driver might locate the primary in 100 ms while an unindexed aggregation runs for minutes. Conversely, a client timeout does not prove the server aborted the write.

### Configuring timeouts via `MongoClientSettings`

To enforce timeout policy in code while letting Boot manage `MongoClient`:

~~~java
import java.util.concurrent.TimeUnit;
import org.springframework.boot.autoconfigure.mongo.MongoClientSettingsBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MongoTimeoutConfiguration {

    @Bean
    MongoClientSettingsBuilderCustomizer mongoTimeouts() {
        return builder -> {
            builder.applyToClusterSettings(cluster ->
                    cluster.serverSelectionTimeout(3, TimeUnit.SECONDS));
            builder.applyToSocketSettings(socket ->
                    socket.connectTimeout(2, TimeUnit.SECONDS));
        };
    }
}
~~~

These numbers are examples, not production defaults. Multiple customizers (TLS/timeouts) can coexist; verify ordering and check for conflicts with URI parameters, SSL bundles, and custom `MongoClient` beans. Newer driver timeout APIs also vary—copy only APIs matching the exact version in your BOM.

## 14. Separating Connection Pools, Identities, and Client Lifecycles

The Java driver's `MongoClient` is thread-safe and manages internal connection pools. Typically **one `MongoClient` per cluster/credential/policy** is appropriate.

Avoid:

~~~java
// DO NOT DO THIS: creating a new MongoClient per HTTP request.
public OrderDocument getOrder(String id) {
    try (var client = MongoClients.create(uri)) {
        return ...; // Pays TLS handshake, auth, pool, and topology monitor costs every time.
    }
}
~~~

Inject `MongoTemplate`/repositories from Spring Boot-managed beans. Spring closes `MongoClient` on application shutdown according to bean ownership.

With multiple tenants, clusters, or credentials:

- Never spawn a new client **per tenant request** when tenants merely share a collection filtered by `tenantId`.
- If each tenant genuinely requires a separate MongoDB identity, bound cached `MongoClient`s with explicit eviction, rotation, and shutdown.
- Each client creates its own pools and monitoring threads; thousands of clients exhaust resources even at low query rates.
- Use `@Qualifier` or explicit configuration when multiple `MongoTemplate`/`MongoClient` beans exist so default beans never silently fall back to admin credentials.
- When rotating SCRAM passwords if an active client cannot refresh credentials dynamically, roll new clients intentionally or perform a rolling restart within an overlap window.

### Never swap credentials per request inside a singleton bean

A singleton client executes under its configured DB principal. Trying to rewrite URIs from an HTTP `username` field to “impersonate” end users risks secret leaks and connection explosion. Enforce caller authorization in the application; true end-user delegated DB identity requires a purpose-built security architecture tested end-to-end.

## 15. Network Perimeter, Credentials, and Secret Sources

Supplement TLS and RBAC with network isolation:

- Keep MongoDB inside a private network/VPC; restrict security groups/firewalls to services that genuinely require access.
- Never expose MongoDB ports to the public Internet merely because passwords are enabled.
- Enable TLS and authentication on all client/`mongos` and inter-cluster channels per deployment model.
- Protect Kubernetes Secrets, service accounts, mount paths, and read RBAC; base64 encoding **is not encryption**.
- Keep password-bearing URIs out of container image layers, audited shell commands, and issue trackers.
- Use secret managers/KMS and rotation, rotating per-service credentials rather than sharing one global password.
- Allow migration/admin runs only from authorized runners/pipelines with approvals and audit logs.

In Kubernetes, creating a `Secret` does not automatically keep other pods out: Kubernetes RBAC, namespaces, mounts, and workload identities all matter. Assign dedicated service accounts per deployment rather than sharing one namespace-wide identity.

### Certificate rotation and password rotation are separate processes

| Rotation | What Changes | Runtime Behavior |
| --- | --- | --- |
| TLS server cert | Certificate chain on `mongod`/`mongos`, SAN, CA if changed | Existing connections stay up; new connections fail if truststore is outdated |
| Truststore CA | Client trust material / `SSLContext` | Loaded `SSLContext` may require recreating client or restarting |
| SCRAM password | Secret in MongoDB and service secret | Clients holding stale credentials fail auth when opening new sockets |
| X.509 client cert | Client cert/private key and MongoDB user mapping if subject changes | New connections fail if key/cert/user drift out of sync |
| Encryption key | KMS/key vault/schema/key version | Verify legacy data readability and migration before rotating |

Every rotation runbook needs canary validation, positive/negative auth checks, metrics on new-connection failures, and rollback **without disabling TLS or falling back to root**.

## 16. Health Checks and Least Privilege: Do Not Over-Privilege Probes

An app can pass liveness while MongoDB is unavailable; restarting the pod may not even help. Health checks can run a lightweight command/ping, yet should never require `clusterAdmin` or `dbAdmin` on the runtime user merely to satisfy an extended indicator.

With Spring Boot Actuator:

- `/actuator/health` includes the MongoDB contributor when classpath/beans match.
- `/actuator/health/readiness` should include MongoDB only when traffic-serving policy requires it, not blindly.
- Event consumers should also watch lag, outbox age, and MongoDB operation success rates rather than ping alone.
- Custom indicators should execute **lightweight, side-effect-free** queries within existing runtime privileges, using short timeouts and redacting credentials.

**Never fix a failing health indicator by granting database-wide `readWrite`** when the service only reads one collection. Adjust the check to match runtime permissions, or use a dedicated monitoring identity for cluster telemetry.

## 17. Observing TLS, Privilege, and Data Errors Without Leaking Secrets

High-value production signals:

| Signal | How to Use It |
| --- | --- |
| TLS handshake / auth failures | Separate CA/SAN/rotation issues from password/mechanism errors |
| MongoDB Unauthorized code 13 | Catch missing privileges or unauthorized actions |
| Pool checked-out/available/wait time | Spot exhaustion, leaks, and queue growth |
| Server selection timeouts | Identify DNS/topology/replica set/TLS/network faults |
| Query p95/p99 and `maxTimeMS` errors | Distinguish slow queries from disconnects |
| Write errors and duplicate key 11000 | Track data conflicts and idempotency hits |
| Transaction aborts/retries/unknown commits | Measure retry behavior and consistency risk |
| Change stream resume failures (if used) | Assess stream recovery health |
| Outbox backlog/age | Verify timely downstream broker delivery |
| Credential/certificate expiry | Alert ahead of outages |
| Audit events | Track role/user/privilege changes and anomalous access |

Never log full connection strings, `Authorization` headers, private keys, MongoDB auth payloads, or sensitive document fields. Even a `query filter` containing emails, tokens, or ID numbers is sensitive—command monitoring must redact or omit bind values.

When combining Micrometer/Actuator with Java driver command listeners, **never turn unbounded collection names, raw queries, or document IDs into metric tags**. Stick to controlled labels like operation, collection category, exception category, and service name.

### Audit logs vs. application logs

MongoDB auditing records security events per deployment edition/tier; application logs record business context. Do not assume Community Edition and Atlas provide identical audit capabilities or retention. Define sources, retention, who can alter roles, and incident retrieval procedures.

## 18. Integration Testing TLS, Authentication, Authorization, and Idempotency

Unit tests on `MongoTemplate` verify `Criteria` construction, yet **cannot prove real MongoDB enforces CAs, roles, or transactions**. Build integration tests connecting to a MongoDB server with TLS and RBAC actually enabled.

### Test matrix

| Case | Setup | Expected Outcome |
| --- | --- | --- |
| Valid TLS | Trusted CA, unexpired cert, matching SAN | Client connects and queries cleanly |
| Untrusted/wrong CA | Truststore omits server signing CA | TLS handshake fails; no plaintext fallback |
| Hostname mismatch | Connect via hostname absent from SAN | TLS verification fails |
| Expired cert | Server presents expired certificate | Client rejects connection |
| Client disables TLS | Attempt `tls=false` against TLS-only endpoint | Connection rejected |
| Valid SCRAM | Correct user/password/`authSource` | Connects with scoped privileges |
| Bad SCRAM | Wrong password or `authSource` | Authentication failure |
| X.509 missing client cert | X.509 connect without client cert | Handshake/authentication fails |
| Unregistered X.509 subject | Valid cert not mapped in `$external` | Authentication fails |
| Permitted runtime CRUD | Insert/find/update `orders` | Succeeds |
| Forbidden runtime DDL | Attempt `drop`/`createIndex` as runtime identity | Unauthorized, code 13 |
| Read-only user writes | Attempt insert/update | Unauthorized |
| Relay user reads `orders` | Query using `relay_app` | Unauthorized |
| Cross-tenant query | Caller A requests Tenant B's order | API never returns B's document |
| Query injection | JSON filter carries `$ne` or `$where` | Rejected by validation / never passed raw |
| Duplicate message | Two concurrent events with same `eventId` | Single business effect, unique receipt |
| DB commit before lost broker ACK | Drop connection prior to ACK | Safe redelivery |
| Transaction rollback | Outbox step fails after order update | Entire transaction rolls back |
| Unknown commit result | Drop commit response | Receipt lookup prevents duplicate side effects |
| Credential rotation | Rotate secret and reconnect | Refresh/restart matches runbook |
| Certificate rotation | Update CA/cert during canary | New connections authenticate cleanly |
| Health check | Runtime privileges only, lightweight check | Requires no `dbAdmin`/`root` |

### Testcontainers does not automatically mean TLS testing

MongoDB Testcontainers lets you test schemas, repositories, indexes, and transactions (with replica set setup). However, **default containers may not enable TLS, auth, or custom roles** like production; passing default container tests does not prove production security configuration.

For TLS/RBAC verification:

1. Provision a dedicated test MongoDB instance with TLS, CA/SANs, and authorization enabled.
2. Seed schemas, indexes, users, and roles via an admin setup identity **during test setup**.
3. Run the Spring Boot application client with the **runtime user**.
4. Execute positive CRUD and negative privilege tests.
5. Add profiles/cases testing wrong CA, wrong hostname, wrong password, and wrong `authSource`.
6. Clean up fixtures with the setup/admin identity rather than giving runtime apps `dropDatabase`.
7. Test transactions against a supporting replica set/sharded topology, not standalone.
8. Keep driver/server/JDK versions close to production, especially when changing TLS protocols or MongoDB major versions.

### Spring Data repository tests with tenant boundaries

Testing principle:

~~~java
@Test
void cannotReadAnotherTenantsOrder() {
    // Existing fixture: ORDER-42 belongs to tenant-b.
    AuthenticatedTenant tenantA =
            new AuthenticatedTenant("tenant-a");

    assertThatThrownBy(() ->
            tenantOrderReader.getOrder(tenantA, "ORDER-42"))
            .isInstanceOf(OrderNotFoundException.class);
}
~~~

This is a **test outline** using application types `AuthenticatedTenant` and `OrderNotFoundException` against real MongoDB fixtures. Add tests for UPDATE, DELETE, aggregations, and any other query builders—not only GET paths.

## 19. Incident Runbooks That Do Not Weaken Security

### TLS handshake errors

1. Confirm exact target hostnames and certificate SANs.
2. Verify certificate chain, CA trust, expiry, EKU, and TLS policy.
3. Behind load balancers, check TLS termination/passthrough and every node discovered by the driver.
4. Confirm mounted secrets/SSL bundles loaded properly and whether rotation requires client recreation/restart.
5. Never install trust-all managers or disable hostname verification just to restore traffic.

### Authentication failed

1. Verify which database holds the user and check `authSource` in the URI.
2. Confirm SCRAM vs. X.509 mechanism and secret access permissions.
3. Check password URI-encoding and whether app and server rotated secrets in sync.
4. For X.509, inspect client certificate, subject DN, `$external` principal, and rotation state.
5. Never log in as `root` and leave root credentials in app config as a workaround.

### Unauthorized after login

1. Read the denied MongoDB error code/action/collection from sanitized logs.
2. Match against the **real business operation**: normal query, update, `createIndex`, change stream, or special aggregation.
3. If app code runs DDL on startup, move DDL to the migration pipeline.
4. If the privilege is legitimately needed, open a change request updating the scoped custom role by collection/action—never grant broad database access.
5. Add a negative test ensuring privileges do not creep wider in future deploys.

### Timeouts/retries/duplicates after network errors

1. Separate connect/server-selection/query timeouts from TLS, auth, and privilege failures.
2. Determine whether a write had an **unknown commit result** or rolled back cleanly.
3. Check receipts/idempotency keys before re-executing business operations.
4. With brokers, compare MongoDB commit timing against ACKs and outbox state.
5. Bound retries/backoff to prevent connection storms during DB recovery.
6. Measure backlog/latency post-recovery and verify zero duplicate documents or desynchronized state.

## 20. Common Misconceptions

**“MongoDB uses TLS, so a `readWrite` account is safe?”**

No. TLS protects transport; `readWrite` can still grant far more actions/collections than the service needs. Enforce least privilege and separate runtime from migration identities.

**“The server certificate is valid, so connecting by a different hostname should be allowed?”**

No. SAN/hostname verification is core to server authentication. Fix the endpoint or certificate instead of enabling `invalidHostNameAllowed(true)`.

**“Is `authSource=admin` always right?”**

No. It must match the database where the MongoDB user was created. Users created in `orders` use `authSource=orders` unless intentionally designed otherwise.

**“RBAC granting only `find` prevents reading another tenant's data?”**

False when tenants share a collection. `find` on that collection can still query other tenants' documents; enforce tenant scoping in the application or isolate storage resources.

**“Spring `@Transactional` wraps MongoDB, JDBC, and RabbitMQ into one commit?”**

No. `MongoTransactionManager` manages MongoDB resources only. JDBC and brokers have independent transactions; use outboxes, state machines, retries, and idempotency for cross-system consistency.

**“Updating the truststore file makes `MongoClient` trust the new CA immediately?”**

Never assume so. Loaded `SSLContext`/certificate material is often cached. Check driver/Boot behavior and prepare client recreation or rolling restarts.

**“Health checks need admin commands, so should we give the app `dbAdmin`?”**

No. Use lightweight checks inside runtime permissions or a separate monitoring identity. Never widen runtime roles just to turn probes green.

**“Adding a `tenantId` field to documents gives us row-level security?”**

No. It is just a document field; if any query omits the filter or trusts unverified caller input, data leaks. Protect scoping on every access path.

### Production checklist

1. Enable TLS, validate CA chains and SAN hostnames; **forbid insecure hostnames or trust-all modes**.
2. Provision certificates/truststores and secrets securely; never commit password-bearing URIs or private keys.
3. Pick auth mechanisms per deployment (SCRAM, X.509, or supported managed identity) with accurate `authSource`.
4. Provision separate identities for order API, workers, outbox relay, read-only reporting, migrations, and operators; **never run as `root`**.
5. Scope privileges by **collection + action**, using custom roles wherever built-in `readWrite` is too broad.
6. Run positive and negative authorization tests against MongoDB with RBAC enabled.
7. Enforce `tenantId` from authenticated principals across find, update, delete, and aggregations; block NoSQL injection.
8. Separate DDL/index migrations from runtime; verify `auto-index-creation` and schema privileges.
9. Run singleton `MongoClient` with tuned pools/timeouts and clean lifecycle handling during rotations.
10. Keep transactions inside supporting MongoDB topologies with unique idempotency receipts; never conflate Mongo transactions with brokers or HTTP.
11. Classify TLS, auth, Unauthorized, query timeout, and unknown commit results so retries match error types.
12. Protect data at rest, field-level secrets, backups, logs, and monitoring; TLS alone never covers the full lifecycle.
13. Enforce network isolation, Kubernetes/secret-manager RBAC, and least-privilege cluster access.
14. Test invalid CAs, wrong hostnames, credential rotation, missing roles, cross-tenant isolation, duplicate deliveries, and transaction rollbacks.
15. Build dashboards/alerts for auth failures, permission denials, cert expiry, pool saturation, and outbox lag, with security-preserving runbooks.

### Technical references by version

- [MongoDB – Configure TLS/SSL](https://www.mongodb.com/docs/manual/tutorial/configure-ssl/): TLS, CAs, certificate verification, and server configuration.
- [MongoDB – Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/): roles, privileges, and authorization.
- [MongoDB – Create a User-Defined Role](https://www.mongodb.com/docs/manual/tutorial/define-roles/): custom privileges per database/collection.
- [MongoDB – SCRAM Authentication](https://www.mongodb.com/docs/manual/core/security-scram/): SCRAM mechanisms and authentication.
- [MongoDB – X.509 Authentication](https://www.mongodb.com/docs/manual/core/security-x.509/): client certificates, `$external`, and account mapping.
- [MongoDB Java Driver – TLS/SSL](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/tls/): Java driver SSL/TLS settings.
- [Spring Boot – Working with SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html): SSL bundles.
- [Spring Boot – Data MongoDB](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.mongodb): MongoDB auto-configuration.
- [Spring Data MongoDB – Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): transaction managers and sessions.
- [MongoDB – Client-Side Field Level Encryption](https://www.mongodb.com/docs/manual/core/csfle/): client-side field encryption and operational constraints.

**Key takeaway:** TLS authenticates and encrypts the transport channel; authentication proves **service identity**; authorization bounds **actions and resources**; while tenant data isolation, query-injection prevention, and idempotency remain application responsibilities. A secure Spring Boot–MongoDB integration designs all these layers together and proves them with tests that **succeed with proper privileges and fail when privileges are missing**.
