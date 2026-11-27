# Configuring URIs, Authentication, TLS, and Selecting Databases and Collections in the MongoDB Java Driver

A Java application that wants to read orders from MongoDB must answer several questions before running `find()`: which machines to connect to, whether the target is a replica set or an Atlas cluster, which database authenticates the account, whether the transport uses TLS, which CAs are trusted, and which database and collection the application will operate on. A single misconfigured parameter can cause connection failures; worse, using the wrong database or disabling certificate verification can lead to operating against an unintended environment or weakening security.

With the **MongoDB Java Sync Driver**, the connection string (connection URI), `MongoClientSettings`, and `MongoCredential` handle connection configuration. After creating `MongoClient`, the application retrieves `MongoDatabase` and then `MongoCollection<T>` to read and write. These handles are designed to be reused: there is no need to create a separate network connection per collection or per HTTP request.

This lesson belongs to the **Java Driver** chapter of the *Database Engine Document MongoDB* module. It focuses on the Java Sync Driver while explaining differences from other driver options. Hostnames, database names, and certificates used in examples are **illustrative** and do not represent a real cluster. APIs and defaults may vary by MongoDB Java Driver, JDK, MongoDB Server, and Atlas version; when applying them in production, check the compatibility matrix and documentation for your chosen versions.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between `mongodb://` and `mongodb+srv://`, and understand seed hosts, replica set discovery, and DNS SRV/TXT.
2. Read URI structure including hosts, database path, query options, and authentication parameters.
3. Explain `authSource`, `authMechanism`, and the difference between the authentication database and the application database.
4. Configure username/password securely using `MongoCredential` without embedding secrets in source code.
5. Understand SCRAM-SHA-256, other authentication mechanisms, and environment-specific support limits.
6. Enable TLS and verify the CA chain, SAN/hostname, and certificate validity.
7. Use the JVM truststore or an `SSLContext` with an appropriate trust manager.
8. Distinguish TLS server authentication from mTLS/client certificates, including `MONGODB-X509`.
9. Create `MongoClient` using a direct URI or `MongoClientSettings.builder()`.
10. Understand connection pools, timeouts, server selection, and the client object lifecycle.
11. Select a database with `getDatabase()` and a collection with `getCollection()`; understand that obtaining a handle does not automatically create data.
12. Use `MongoCollection<Document>`, type mapping, and POJO codecs as needed.
13. Configure read preference, read concern, and write concern without confusing them with credentials.
14. Connect to a replica set or Atlas with proper topology, TLS, and network requirements.
15. Analyze `Authentication failed`, `Unauthorized`, certificate, DNS, and server selection errors.
16. Design multi-environment configuration, secret handling, logging, and safe connection testing.

## 2. Scope: Java Sync Driver and Application Types

MongoDB offers Java drivers/libraries serving multiple models:

| Option | Characteristics | Example Use Cases |
|---|---|---|
| **MongoDB Java Sync Driver** | Blocking API; returns results directly or via cursor | Synchronous Java services, batch jobs, CLI tools |
| Java Reactive Streams Driver | Non-blocking API following Reactive Streams | Reactive applications |
| Spring Data MongoDB | Repository/template abstraction over the driver | Spring apps wanting mapping/repositories |
| MongoDB Java Driver core | Low-level component of the driver ecosystem | Typically used by higher-level drivers |

This lesson primarily uses the following types:

~~~java
com.mongodb.client.MongoClient
com.mongodb.client.MongoDatabase
com.mongodb.client.MongoCollection
org.bson.Document
~~~

Do not confuse `com.mongodb.client.MongoClient` from the Java Sync Driver with legacy MongoDB Java APIs or reactive clients in different packages.

### 2.1. Dependency

With Gradle, specify the Java Sync Driver version compatible with your JDK and MongoDB Server:

~~~kotlin
dependencies {
    // Replace with a specific version tested and pinned by the project.
    implementation("org.mongodb:mongodb-driver-sync:REPLACE_WITH_PINNED_VERSION")
}
~~~

With Maven:

~~~xml
<dependency>
    <groupId>org.mongodb</groupId>
    <artifactId>mongodb-driver-sync</artifactId>
    <version>REPLACE_WITH_PINNED_VERSION</version>
</dependency>
~~~

`REPLACE_WITH_PINNED_VERSION` is a placeholder, **not a valid version number**. Use a compatible release managed via your project's dependency catalog, BOM, or policy; avoid picking a random version just because an online example uses it.

### 2.2. When Is mongosh Useful?

`mongosh` is useful for testing a cluster, database user, and TLS independently of the Java runtime. However, if `mongosh` connects successfully while Java fails, the issue may lie in the **JVM truststore, driver version, URI parsing, or runtime dependencies**. Do not treat a `mongosh` test alone as proof that your Java configuration is correct.

## 3. From URI to Collection: Architecture Diagram

~~~mermaid
flowchart TD
    Config["URI + credentials + TLS policy"] --> Settings["MongoClientSettings"]
    Settings --> Client["MongoClient: topology + connection pools"]
    Client --> DB1["MongoDatabase: shop"]
    Client --> DB2["MongoDatabase: audit"]
    DB1 --> C1["MongoCollection<Document>: orders"]
    DB1 --> C2["MongoCollection<Document>: customers"]
    DB2 --> C3["MongoCollection<Document>: events"]
    C1 --> Query["find / insertOne / aggregate"]
    C2 --> Query
    C3 --> Query
~~~

A single `MongoClient` manages server selection and **connection pools**. From it, you can obtain multiple `MongoDatabase` and `MongoCollection` handles to operate on multiple namespaces.

### 3.1. MongoDB Namespace

A collection is identified by the pair:

~~~text
<database>.<collection>

shop.orders
shop.customers
audit.events
~~~

`shop.orders` and `audit.orders` are two different collections. Specifying a default database or authentication database in the URI does not make every command automatically target the right collection; your code must still select them explicitly.

### 3.2. When Does the Actual Connection Happen?

Creating `MongoClient` may initialize monitoring, pools, and topology management, but **does not guarantee** that a command has succeeded against MongoDB. Calling `getDatabase()`/`getCollection()` only creates handles. To verify connectivity and authentication, execute an actual command such as `ping`.

## 4. Basic Structure of a Connection URI

MongoDB uses two primary forms:

~~~text
mongodb://[username:password@]host1[:port1][,host2[:port2]...]/[defaultDb][?options]

mongodb+srv://[username:password@]dnsServiceName/[defaultDb][?options]
~~~

Square brackets in the syntax description denote optional components—**the actual string should not include those brackets**. In real URIs, IPv6 literals require their own URI bracket syntax.

Components:

| Component | Role | Example |
|---|---|---|
| Scheme | Direct seed host connection or DNS SRV discovery | `mongodb://`, `mongodb+srv://` |
| Host/seed list | Starting point for cluster discovery | `mongo1.db.internal:27017` |
| Database path | Default database / can affect default `authSource` | `/shop` |
| Auth credentials | Database user if placed in URI | `username:password@` |
| Query options | TLS, replica set, authSource, timeouts... | `?tls=true&replicaSet=rs0` |

### 4.1. URI for a Standalone Lab MongoDB

~~~text
mongodb://127.0.0.1:27017/
~~~

Suitable only when lab MongoDB is listening on localhost and security policy permits it. Never default to plaintext in production. With TLS and a certificate for `mongo1.db.internal`:

~~~text
mongodb://mongo1.db.internal:27017/?tls=true
~~~

### 4.2. URI with a Database Path

~~~text
mongodb://mongo1.db.internal:27017/shop?tls=true
~~~

Here `shop` is the database in the connection string; when using the Sync Driver, the application should still explicitly call `client.getDatabase("shop")`. Do not confuse this path with a collection name; the URI never selects `shop.orders` automatically.

### 4.3. URI with Multiple Options

~~~text
mongodb://mongo1.db.internal:27017,mongo2.db.internal:27017,mongo3.db.internal:27017/shop?replicaSet=rs0&authSource=admin&tls=true&appName=order-service
~~~

The application receives the seed host list, replica set name, `authSource`, and options. The system must have DNS and network reachability to **every advertised member** discovered by the driver, not just the first host.

## 5. `mongodb://` with a Replica Set

When connecting to a replica set, provide multiple seed hosts to reduce reliance on any single member:

~~~text
mongodb://mongo1.db.internal:27017,mongo2.db.internal:27017,mongo3.db.internal:27017/?replicaSet=rs0&tls=true
~~~

The driver uses seed hosts to discover topology, track primary and secondaries, and select nodes based on read preference, health, and server selection rules.

### 5.1. Seed Hosts Are Not a Static Node List

The driver receives topology metadata from `hello`/topology discovery and connects to the hostnames advertised by the replica set. Therefore:

- DNS for advertised hosts must resolve from where Java runs.
- Network policies must permit connections.
- Certificate SANs must match the hostnames the driver actually uses.
- `replicaSet=rs0` must match the exact replica set name.

An initial connection succeeding via an intermediate seed hostname does not guarantee reliable failover if the advertised member hosts are unreachable.

### 5.2. `directConnection=true`

`directConnection=true` instructs the driver to connect directly to a single server instead of performing normal topology discovery in supported scenarios. It is useful for certain tests or specialized topologies, but **it is not a valid way to bypass replica set failover** for production applications.

~~~text
mongodb://mongo1.db.internal:27017/?directConnection=true&tls=true
~~~

Do not use direct mode to mask DNS or advertised-host errors in a replica set. When automatic primary discovery and failover are needed, configure the replica set properly.

### 5.3. Never Put a Port After an SRV DNS Service Name

`mongodb+srv://` is designed for a DNS service hostname, not a `host:port` list like `mongodb://`. Keep the two schemes clearly distinct.

## 6. `mongodb+srv://` and DNS SRV/TXT

With a DNS SRV connection:

~~~text
mongodb+srv://cluster0.example.mongodb.net/?retryWrites=true&w=majority
~~~

The driver queries DNS SRV records to discover hosts/ports for the service, and can also read TXT records containing supported options. This is the standard connection method for Atlas, and can also be used in self-managed deployments if DNS and driver support are properly configured.

### 6.1. Default TLS with SRV

`mongodb+srv://` typically **enables TLS by default** unless validly overridden. For production/Atlas, keep TLS and hostname verification enabled per security policy; never disable TLS to work around certificate errors.

### 6.2. DNS Risks

SRV connections depend on DNS resolution and accurate records. If the Java host cannot resolve SRV/TXT records or DNS returns unroutable hostnames, the driver will fail before even reaching MongoDB login.

### 6.3. Do Not Mistake SRV for a Proxy

SRV helps **discover a list of endpoints**; it is not itself a MongoDB wire-protocol load balancer. The driver still handles topology discovery, connections, and failover.

### 6.4. Review Copied Atlas URIs Carefully

Atlas provides a starter connection string. Before placing it into production config, verify:

- Correct project and cluster.
- Correct database user and auth mechanism.
- TLS/CA trust.
- Network path, IP allowlist, or private endpoint.
- Appropriate `retryWrites`, write concern, and timeouts.
- No real password stored in source code.

## 7. URIs, Secrets, and Special Characters

A URI containing an embedded password can leak into source control, startup logs, crash dumps, process arguments, or metrics. Never put real secrets into copy/paste examples or exception messages.

### 7.1. Which Characters Need Percent-Encoding?

If username/password are included in a URI, reserved characters such as `@`, `:`, `/`, `?`, `#`, and `%` must be percent-encoded per URI grammar:

| Character | Percent Encoding |
|---|---|
| `@` | `%40` |
| `:` | `%3A` |
| `/` | `%2F` |
| `?` | `%3F` |
| `#` | `%23` |
| `%` | `%25` |

If a password is `a@b/c` and written raw into a URI, the parser may mistake `@` for the credentials/host separator and `/` for the path delimiter. Avoid building URIs by concatenating unencoded sensitive values.

### 7.2. `URLEncoder` Is Not a Generic URI Encoder

`java.net.URLEncoder` applies `application/x-www-form-urlencoded` rules (for example, spaces become `+`), which does not match RFC 3986 percent-encoding for all URI components. Use driver utilities or a proper **URI userinfo component** encoder whenever credentials must be embedded.

### 7.3. Better Approach

Keep passwords out of the URI. Use a host-only URI in configuration and supply `MongoCredential` via a controlled secrets manager or secret injection mechanism. Even secrets passed via environment variables need protection, as privileged processes/users can inspect them; an enterprise secret management platform is preferred.

## 8. Authentication Database vs. Application Database

The **authentication database** is where MongoDB looks up the user identity for the matching mechanism. The **application database** is where your code reads and writes collections. These two databases can be different.

Example:

~~~text
Application database: shop
Authentication database: admin
MongoDB user: shopAppUser created in admin
~~~

Connection URI:

~~~text
mongodb://mongo1.db.internal:27017/shop?authSource=admin&tls=true
~~~

In Java:

~~~java
MongoDatabase db = client.getDatabase("shop");
MongoCollection<Document> orders = db.getCollection("orders");
~~~

The application authenticates using the user defined in `admin`, then reads `shop.orders` according to its granted roles.

### 8.1. Default `authSource`

For common authentication mechanisms like SCRAM, if the URI specifies a database path without `authSource`, that path database may be used as the default authentication database; if no path is present, it defaults to `admin`. Other mechanisms like X.509 use `$external`. **Setting `authSource` explicitly** prevents configuration drift across environments.

### 8.2. `getDatabase("shop")` Does Not Change `authSource`

Once `MongoClient` has authenticated against `admin`, calling `getDatabase("shop")` does not cause the driver to look up users in `shop`. It only selects the target namespace for subsequent operations.

### 8.3. Authenticated Does Not Mean Authorized

If the user exists and the password is valid, but the user lacks `read` permission on `shop.orders`, MongoDB will still return an **Unauthorized** error. Authentication answers "who are you?"; authorization answers "what are you allowed to do?"

## 9. SCRAM-SHA-256 and Authentication Mechanisms

For applications using username/password, `SCRAM-SHA-256` is the standard mechanism supported in modern MongoDB versions.

| Mechanism | Purpose | Notes |
|---|---|---|
| `SCRAM-SHA-256` | Username/password authentication | Preferred when deployment supports it and policy permits |
| `SCRAM-SHA-1` | Compatibility with legacy setups | Evaluate migration/policy |
| `MONGODB-X509` | Client certificate authentication | Requires PKI, TLS client cert, `$external` |
| `MONGODB-AWS` | AWS IAM-based auth in supported deployments | Depends on runtime, version, and provider |
| OIDC / enterprise mechanisms | Federated identity in supported environments | Separate configuration, roles, and credential providers |

Do not assume every mechanism is available on every MongoDB Server, Atlas tier, or driver version. Cloud identity and enterprise mechanisms have specific policies and credential providers.

### 9.1. SCRAM Does Not Replace TLS

SCRAM is never a reason to omit TLS. TLS protects queries, results, connection metadata, and traffic beyond the login exchange. Always enable TLS in production even though SCRAM protects passwords during authentication.

### 9.2. Choose One Source for Credentials

Applications can supply credentials in the URI or via `MongoCredential`; avoid overlapping configurations that obscure which username/`authSource` takes effect. Separating connection topology from secrets is much easier to govern.

## 10. Creating MongoClient with a Basic URI

Minimal example:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class SimpleMongoConnection {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("admin");
            Document result = db.runCommand(new Document("ping", 1));
            System.out.println(result.toJson());
        }
    }
}
~~~

### 10.1. Why Run `ping`?

`MongoClients.create()` instantiates the client object, but does not verify that MongoDB connectivity, DNS, TLS, and auth all succeed on that line. `db.runCommand({ping:1})` forces the driver to perform server selection and execute a command, catching misconfigurations early.

### 10.2. URIs from the Environment Still Need Validation

Never write the raw URI into exceptions or logs if it contains a password. If missing, log only the missing variable name; if URI parsing fails, redact credentials before sending error context to observability systems.

### 10.3. Choosing the Database for `ping`

`admin` is a common choice for `ping`, though command availability depends on server and privilege policies. `ping` primarily verifies client reachability—it does not prove read/write rights on every collection.

## 11. Creating MongoClient with MongoClientSettings

When an application needs fine control over pools, timeouts, auth, or TLS, use the builder:

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.MongoCredential;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

public class ConfiguredMongoClient {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        String username = System.getenv("MONGODB_USERNAME");
        char[] password = System.getenv("MONGODB_PASSWORD").toCharArray();

        MongoCredential credential =
            MongoCredential.createScramSha256Credential(
                username,
                "admin",
                password
            );

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .credential(credential)
            .applicationName("order-service")
            .applyToConnectionPoolSettings(pool -> pool.maxSize(50))
            .applyToClusterSettings(cluster ->
                cluster.serverSelectionTimeout(5, TimeUnit.SECONDS)
            )
            .applyToSocketSettings(socket ->
                socket.connectTimeout(10, TimeUnit.SECONDS)
            )
            .build();

        try (MongoClient client = MongoClients.create(settings)) {
            System.out.println(
                client.getDatabase("admin")
                    .runCommand(new Document("ping", 1))
                    .toJson()
            );
        }
    }
}
~~~

This is a configuration example and does not cover null environment variable checks, secret rotation, or service lifecycle management. In production code, validate required variables before calling `toCharArray()`, isolate the builder in a configuration module, and never log passwords.

### 11.1. Order of Applying Settings

`applyConnectionString` populates options from the URI, and subsequent setters can override individual settings. To stay predictable, establish clear precedence: for example, URI provides topology/TLS, `MongoCredential` supplies secrets, and the builder configures pools/timeouts. Avoid putting a username in the URI only to override it with a different user in the builder unintentionally.

### 11.2. `applicationName`

A short, stable application name helps logs and monitoring identify connections. Never place user tokens or sensitive data in the application name.

### 11.3. Credentials with `char[]`

`MongoCredential.createScramSha256Credential` accepts `char[]` rather than requiring a `String`. This can reduce how long uncontrolled password copies linger in memory, though it does not guarantee every runtime copy is wiped. Manage secret lifecycles at the application layer and keep secrets out of logs.

## 12. URI vs. Builder: Which Should You Choose?

| Approach | Pros | Watch-outs |
|---|---|---|
| `MongoClients.create(uri)` | Concise, convenient with config/Atlas | Long URIs can make secrets/options harder to manage |
| `MongoClients.create(settings)` | Separates topology, auth, TLS, pool/timeouts | Must clarify precedence; more verbose configuration code |
| Framework auto-configuration | Integrates lifecycle/DI | Must understand how framework maps properties to the driver |

For services with strict security requirements, **a password-free URI + credential provider + explicit TLS config** is usually easier to audit. For smaller apps, a URI from a secret manager is still acceptable if protected and never logged.

### 12.1. Never Build URIs by Arbitrary String Concatenation

Anti-pattern:

~~~java
// DISCOURAGED: unencoded password and easily leaked to logs.
String uri = "mongodb://" + username + ":" + password +
    "@mongo1.db.internal:27017/shop";
~~~

This breaks on passwords containing `@`, `:`, or `/` and creates multiple `String` copies of credentials. Passing credentials via `MongoCredential` avoids parser/encoding pitfalls.

### 12.2. Never Hardcode Environments

Never put production URIs directly in source code. Separate dev/staging/prod via deployment configuration, with isolated secret scopes and reviewed IP allowlists/cluster identifiers.

## 13. Common URI Options

| Option | Example | Purpose |
|---|---|---|
| `replicaSet` | `rs0` | Verify/discover replica set |
| `authSource` | `admin` | Database containing authentication user |
| `authMechanism` | `SCRAM-SHA-256` | Login mechanism |
| `tls` | `true` | Enable TLS |
| `appName` | `order-service` | Identify application in diagnostics |
| `retryWrites` | `true` | Enable retryable writes when operation/topology supports |
| `retryReads` | `true` | Enable retryable reads as supported |
| `readPreference` | `primary` | Select member type for reads |
| `w` | `majority` | Write concern |
| `readConcernLevel` | `majority` | Read concern |
| `serverSelectionTimeoutMS` | `5000` | Max wait for driver to find an eligible server |
| `connectTimeoutMS` | `10000` | Max time to establish socket connection |
| `socketTimeoutMS` | `30000` | Socket read timeout per driver settings |
| `maxPoolSize` | `50` | Max connections in pool per config |
| `minPoolSize` | `0` | Min connections in pool per config |
| `compressors` | `zstd,snappy,zlib` | Wire compression when both sides support it |
| `directConnection` | `true` | Connect directly to endpoint where appropriate |

**Do not copy every option into a URI without evaluating it.** Timeouts, retries, read/write concerns, and pools must match your workload. Defaults and support vary across driver/server versions.

### 13.1. URI Options Do Not Replace Collection Selection

`authSource`, `readPreference`, or `tls` do not select a collection name. The application must call `getDatabase("...").getCollection("...")` or use appropriate framework mapping.

### 13.2. Never Use `socketTimeoutMS` to Fix Missing Indexes

Raising timeouts can hide slow queries caused by `COLLSCAN` or server overload. Always inspect query performance before raising timeouts arbitrarily.

## 14. MongoClient Lifecycle and Connection Pools

`MongoClient` is **thread-safe** and designed for reuse. A service typically creates one `MongoClient` per cluster/credential configuration and keeps it alive until application shutdown.

~~~mermaid
flowchart TD
    Start["Application startup"] --> Load["Load config + secrets"]
    Load --> Client["Create MongoClient"]
    Client --> Ping["Run ping / readiness"]
    Ping --> Serve["Serve many HTTP requests"]
    Serve --> Reuse["Reuse MongoDatabase/MongoCollection handles"]
    Reuse --> Serve
    Serve --> Shutdown["Graceful shutdown"]
    Shutdown --> Close["Close MongoClient"]
~~~

### 14.1. Anti-Pattern: Client per Request

~~~java
// Do NOT do this in an HTTP handler:
try (MongoClient client = MongoClients.create(uri)) {
    return client.getDatabase("shop")
        .getCollection("orders")
        .find().first();
}
~~~

Each request creates a new pool, topology monitor, and TLS connections, driving up CPU, latency, and socket counts.

### 14.2. Lifecycle in Spring/Jakarta Services

If the framework creates a singleton `MongoClient` bean, let dependency injection manage its lifecycle. Do not manually instantiate clients per repository or per transaction.

### 14.3. Multiple Clusters

If a service genuinely connects to two MongoDB clusters with distinct credentials or trust stores, each cluster typically needs its own `MongoClient` settings. Do not try to "switch clusters" using `getDatabase()`; that method only switches namespaces **within that `MongoClient`'s cluster**.

## 15. Pool Size and Server Selection Are Not Authentication

Common performance parameters:

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToConnectionPoolSettings(pool ->
        pool.maxSize(50)
            .minSize(0)
            .maxWaitTime(2, TimeUnit.SECONDS)
    )
    .applyToClusterSettings(cluster ->
        cluster.serverSelectionTimeout(5, TimeUnit.SECONDS)
    )
    .build();
~~~

Numbers are illustrative only, not universal recommendations.

### 15.1. Server Selection Timeout

`serverSelectionTimeoutMS` controls how long the driver waits for an eligible server. It is not an overall cap on all database operations. Server selection failures can stem from DNS, TLS, auth-related connection failures, replica set state, or networking.

### 15.2. Connection Timeout

`connectTimeoutMS` governs socket establishment; `socketTimeoutMS` governs socket read/response waiting per driver semantics. Do not treat either as a simplistic "query execution timeout."

### 15.3. Max Pool Size

Increasing pool size excessively creates high connection, CPU, and resource pressure without improving throughput if the bottleneck is on the server or indexes. Measure pool wait, concurrency, thread counts, CPU, DB connections, and latency.

## 16. What Is TLS in Java → MongoDB Connections?

TLS encrypts network traffic and verifies server identity via certificates. In production, you typically want:

1. Java driver TLS enabled.
2. `mongod`/`mongos` servers presenting valid certificates.
3. JVM trusting the CA chain that signed the certificates.
4. Connection hostname matching a **Subject Alternative Name (SAN)**.
5. Unexpired certificates with appropriate key usage/EKU.
6. TLS protocol/cipher versions compatible with both JDK and server.

~~~mermaid
sequenceDiagram
    participant Java as Java MongoDB Driver
    participant DB as mongod / mongos
    Java->>DB: TLS handshake
    DB-->>Java: Server certificate chain
    Java->>Java: Verify trust, SAN, validity, policy
    Java->>DB: Establish encrypted channel
    Java->>DB: MongoDB authentication (SCRAM/X.509)
    DB-->>Java: Auth result
    Java->>DB: ping/find/insert
~~~

TLS does not replace MongoDB RBAC. An encrypted TLS connection still requires a database user with read/write permissions on the target database/collection.

### 16.1. Enabling TLS via URI

~~~text
mongodb://mongo1.db.internal:27017/?tls=true
~~~

Do not assume `mongodb://` enables TLS automatically without explicit configuration. `mongodb+srv://` generally enables TLS by default; JVM trust and certificate validation are still required.

### 16.2. Enabling TLS via MongoClientSettings

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToSslSettings(ssl ->
        ssl.enabled(true)
           .invalidHostNameAllowed(false)
    )
    .build();
~~~

`invalidHostNameAllowed(false)` explicitly enforces **strict hostname validation**, appropriate for production. Adjust builder/API details per driver version as needed.

### 16.3. Never Use a Trust-All SSLContext

Creating a `TrustManager` that blindly accepts every certificate allows the client to establish encrypted channels with **impostor servers**, defeating server identity verification. Fix CA trust and SANs rather than bypassing validation.

## 17. TLS Certificates: CA, SAN, Chain, and Validity

| Component | Meaning |
|---|---|
| Root CA | Root of trust; must be protected |
| Intermediate CA | Signs leaf certificates per PKI policy |
| Server leaf certificate | Proves identity of `mongod`/`mongos` |
| Private key | Secret held by the certificate subject |
| CA truststore | Store where JVM looks up trusted public CAs |
| SAN | DNS/IP names for which the certificate is valid |
| EKU | Extended Key Usage such as `serverAuth` or `clientAuth` |
| NotBefore/NotAfter | Validity window of the certificate |

### 17.1. SAN Must Match the URI Host

If the URI uses `mongo1.db.internal`, the leaf certificate needs `DNS:mongo1.db.internal`. If the URI uses IP `10.20.0.5`, a DNS SAN does not substitute for an IP SAN.

### 17.2. Replica Sets Have Multiple SAN Requirements

After initial connection, the driver connects to `mongo2.db.internal`/`mongo3.db.internal` from topology discovery. Each member's certificate must be valid for the hostname the driver actually uses. Testing only one seed host is insufficient.

### 17.3. Do Not Confuse CN-Only with SAN

Modern hostname validation relies primarily on SANs. Never issue certificates with only a Common Name (CN) and expect every Java/JDK version to accept them.

### 17.4. Clock Skew and Expiry

Incorrect clocks on the JVM or server can trigger "certificate not yet valid" or expired errors. Use NTP, monitor expiration dates, and rotate certificates ahead of expiry.

## 18. JVM Default Truststore

Java ships with a default truststore depending on the JDK distribution/runtime. If the server certificate is signed by a CA the JVM already trusts, no custom truststore may be needed.

When using a **private CA**, Java generally needs the CA certificate supplied via:

- A dedicated JVM truststore (JKS/PKCS#12).
- A custom `SSLContext` built with `TrustManagerFactory`.
- Trust management provided by the framework/platform.

Never assume that "installing a CA in the Linux OS store" automatically makes **every JVM** trust that CA; many JVMs use their own separate truststore.

### 18.1. Java Truststore with PKCS#12

Example properties:

~~~text
-Djavax.net.ssl.trustStore=/etc/app/tls/mongo-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
-Djavax.net.ssl.trustStorePassword=TRUSTSTORE_SECRET
~~~

These are illustrative property names, not a production script with real secrets. Placing passwords directly in command-line arguments can leak them via process inspection, deployment manifests, or logs. Use secret injection/configuration approved by your organization.

### 18.2. Truststores Hold CAs, Not MongoDB Passwords

A truststore verifies **server certificates**; it is not where MongoDB database user passwords are kept. SCRAM credentials and CA trust are two distinct layers.

### 18.3. Do Not Arbitrarily Import Leaf Certificates

Pinning a specific certificate can be done in special cases, but importing leaf certs instead of the CA chain can cause outages whenever servers rotate leaf certificates. Usually you should trust an approved issuer CA with a rotation process; use pinning only when required by your threat model/policy with an overlap plan.

## 19. Building an SSLContext from a Truststore in Java

For applications needing per-cluster truststores without altering the global JVM truststore, build a custom `SSLContext`:

~~~java
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;

public class MongoTlsContextFactory {
    public static SSLContext fromTrustStore(
            Path path,
            char[] trustStorePassword
    ) throws Exception {
        KeyStore trustStore = KeyStore.getInstance("PKCS12");
        try (InputStream stream = Files.newInputStream(path)) {
            trustStore.load(stream, trustStorePassword);
        }

        TrustManagerFactory trustManagers =
            TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
            );
        trustManagers.init(trustStore);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(
            null,
            trustManagers.getTrustManagers(),
            new SecureRandom()
        );
        return context;
    }
}
~~~

Pass the context to the driver:

~~~java
SSLContext tlsContext = MongoTlsContextFactory.fromTrustStore(
    Path.of("/etc/app/tls/mongo-truststore.p12"),
    trustStorePassword
);

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .applyToSslSettings(ssl ->
        ssl.enabled(true)
           .context(tlsContext)
           .invalidHostNameAllowed(false)
    )
    .build();
~~~

Imports for `Path`, `SSLContext`, and driver classes must be declared in your actual Java file. The factory example configures **trust managers** only, not client certificates. For mTLS, you also need appropriate key managers.

### 19.1. Why Build a Dedicated Context?

- Multiple clusters use different CAs.
- Avoid overriding the global JVM truststore for all HTTP/TLS clients in the process.
- Control certificate lifecycle/reloading per policy.

### 19.2. Truststore Passwords Differ from MongoDB Passwords

The truststore password protects the truststore file at the format/key-management level. The MongoDB SCRAM password authenticates the database user. Do not reuse the same secret for both out of habit.

### 19.3. Rotation

When a CA or leaf certificate changes, the process may need to recreate its `SSLContext`/`MongoClient` or reload trust per runtime support. Never assume replacing a `.p12` file on disk updates active TLS connections or loaded trust managers immediately.

## 20. TLS Combined with SCRAM: Complete Configuration

A clean Java pattern:

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.MongoCredential;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.Document;

public class ScramTlsApp {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        String username = System.getenv("MONGODB_USERNAME");
        String passwordText = System.getenv("MONGODB_PASSWORD");

        if (uri == null || username == null || passwordText == null) {
            throw new IllegalStateException(
                "Missing MongoDB connection configuration"
            );
        }

        char[] password = passwordText.toCharArray();
        MongoCredential credential =
            MongoCredential.createScramSha256Credential(
                username, "admin", password
            );

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .credential(credential)
            .applyToSslSettings(ssl -> ssl.enabled(true))
            .build();

        try (MongoClient client = MongoClients.create(settings)) {
            Document ping = client.getDatabase("admin")
                .runCommand(new Document("ping", 1));
            System.out.println(ping.toJson());
        }
    }
}
~~~

The URI from the environment should **contain only hosts/options**, with no conflicting username/password. If using a private CA, add the JVM truststore or custom `SSLContext` from the previous sections.

### 20.1. Holding Passwords as Strings

Reading from environment variables keeps the example clear; in high-security systems, use a secret provider/injection mechanism to minimize plaintext passwords in `String` objects. Even after calling `passwordText.toCharArray()`, the original `String` remains on the heap until JVM garbage collection reclaims it.

### 20.2. TLS Client Certificates Are Not Required for SCRAM

When the TLS server allows clients without client certificates, the application can use TLS server-auth and authenticate with SCRAM. Do not confuse "using TLS" with "must create a client keyStore."

## 21. TLS and MONGODB-X509: When Client Certificates Are Required

In mTLS, the MongoDB server verifies the client certificate. When using `MONGODB-X509` for database authentication, MongoDB maps the identity from the certificate subject to a user and roles per policy.

Illustrative URI:

~~~text
mongodb://mongo1.db.internal:27017/?tls=true&authMechanism=MONGODB-X509&authSource=%24external
~~~

`%24external` is the URI-encoded form of `$external`.

### 21.1. Both keyStore and trustStore Are Required

The Java application must:

1. Trust the CA that signed the **server certificate** via a truststore.
2. Hold a **client certificate and private key** to present to the server.
3. Have a client certificate with EKU/subject valid for X.509 authentication.
4. Have a matching MongoDB user/roles, typically in `$external`.

A JVM can be configured with:

~~~text
-Djavax.net.ssl.trustStore=/etc/app/tls/server-trust.p12
-Djavax.net.ssl.trustStoreType=PKCS12
-Djavax.net.ssl.keyStore=/etc/app/tls/app-client.p12
-Djavax.net.ssl.keyStoreType=PKCS12
~~~

Passwords for `keyStore` and `trustStore` must be supplied securely via a secret mechanism—never placed literally in command-line arguments, repos, or logs.

### 21.2. Custom SSLContext with Client Key Managers

If not using global JVM properties, construct a `KeyManagerFactory` from the client keyStore and a `TrustManagerFactory` from the server CA trustStore, then call `SSLContext.init(keyManagers, trustManagers, ...)`. You can reuse the structure from Section 19 and add client key managers.

### 21.3. Authentication Differs from TLS Handshake

A client certificate can pass the TLS layer while `MONGODB-X509` still fails due to a subject mismatch with the database user, wrong `authMechanism`/`authSource`, or missing privileges. Conversely, a server cert missing a SAN will fail TLS **before** MongoDB login even begins.

### 21.4. Never Use Cluster Member Certificates for Applications

Certificates used for internal replica set or sharded cluster membership carry special identity/privilege requirements. Never reuse those certificates/secrets for normal applications. Separate PKI profiles and enforce least privilege.

## 22. TLS for Atlas and Managed Systems

An Atlas connection string typically uses `mongodb+srv://...`. Along with username/password or supported IAM/OIDC configuration, the Java runtime needs:

- DNS SRV/TXT resolution.
- Network access (IP access list, peering, or private endpoint per deployment).
- TLS and certificate trust.
- Credentials provisioned with the right database and roles.
- Driver/JDK versions compatible with the cluster.

**Password-free** URI example:

~~~text
mongodb+srv://cluster0.example.mongodb.net/?retryWrites=true&w=majority&appName=order-service
~~~

This is an illustrative hostname, not a real Atlas cluster. Inject `MongoCredential` or use secret injection per policy, then call `getDatabase("shop")`.

### 22.1. Confirm Atlas `authSource`

Most applications use an Atlas-provisioned database user and appropriate SCRAM mechanism; however, do not infer from the SRV scheme that all mechanisms/`authSource` settings are identical. Follow the connection instructions for your actual deployment.

### 22.2. Never Disable TLS If You See `PKIX path building failed`

JVM trust-chain errors must be fixed with the proper CA, JDK, or truststore. Disabling certificate verification exposes the application to connecting to rogue servers.

### 22.3. Verify the Right Project/Cluster

Atlas may contain similarly named projects and clusters. Track cluster identity and environment in configuration management, guard production secrets, and avoid targeting the wrong cluster during migrations.

## 23. Selecting a MongoDatabase: `getDatabase()`

Once you have a client:

~~~java
MongoDatabase shop = client.getDatabase("shop");
MongoDatabase audit = client.getDatabase("audit");
~~~

These two variables are handles to two databases **within the same MongoDB cluster managed by the client**.

### 23.1. Obtaining a Handle Does Not Create the Database

~~~java
MongoDatabase future = client.getDatabase("database_chua_ton_tai");
~~~

This call **does not create a database on the server** immediately. A database/collection normally materializes when data is written or a collection creation command is explicitly issued with permissions. Calling `getDatabase` is therefore not an existence check.

### 23.2. Never Take Database Names from Raw User Input

Anti-pattern:

~~~java
MongoDatabase db = client.getDatabase(request.getParameter("database"));
~~~

If a request can choose an arbitrary database, the application could access unintended namespaces using the service account's privileges. Use allowlists, mappings derived from authenticated tenants, environment config, and least-privilege roles.

### 23.3. Selected Database Is Not the Default Auth Database

Calling `client.getDatabase("audit")` does not re-authenticate against `audit`; connections still use `MongoClient`'s configured credentials.

## 24. Selecting a MongoCollection: `getCollection()`

~~~java
MongoDatabase db = client.getDatabase("shop");
MongoCollection<Document> orders = db.getCollection("orders");
MongoCollection<Document> customers = db.getCollection("customers");
~~~

`MongoCollection<Document>` is a reusable handle for running queries, writes, index commands, aggregations, change streams, and related operations.

### 24.1. Obtaining a Handle Does Not Create the Collection

~~~java
MongoCollection<Document> future = db.getCollection("new_collection");
~~~

This does not create a collection on the server. Collections can be created implicitly upon an authorized write, or explicitly via:

~~~java
db.createCollection("new_collection");
~~~

Explicit collection creation requires privileges and errors if conditions fail (for example, if the collection already exists). Never run `createCollection` on every HTTP request.

### 24.2. Collection Names Are Part of the API Contract

`orders`, `order`, and `Orders` can be distinct namespaces depending on naming and environment rules. Use clear constants or validated config mappings; never concatenate tenant IDs or HTTP parameters directly into collection names without validation.

### 24.3. Generics Control Document Decoding

`MongoCollection<Document>` decodes to `Document`. `MongoCollection<Order>` decodes to a POJO when an appropriate codec is configured. Generic types **do not replace authentication or authorization**.

## 25. End-to-End Data Read Example

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

public class ReadShopOrders {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("shop");
            MongoCollection<Document> orders = db.getCollection("orders");

            try (MongoCursor<Document> cursor = orders.find(
                    Filters.and(
                        Filters.eq("tenantId", "t-01"),
                        Filters.eq("status", "PAID")
                    ))
                .projection(Projections.fields(
                    Projections.include(
                        "_id", "orderNo", "status", "total"
                    )
                ))
                .sort(Sorts.descending("createdAt", "_id"))
                .limit(20)
                .iterator()) {

                while (cursor.hasNext()) {
                    System.out.println(cursor.next().toJson());
                }
            }
        }
    }
}
~~~

This example assumes the database and collection exist, the URI includes TLS, and credentials are properly provisioned. If `MONGODB_URI` is missing, validate it as shown in Section 10. In production, avoid printing real data to stdout or logs.

### 25.1. Filters and Projections Serve Two Goals

- `Filters.eq("tenantId", "t-01")` scopes the query to the authenticated tenant.
- `Projections.include(...)` reduces the payload returned.

Projections cannot salvage the security of a query that is missing a tenant filter.

### 25.2. Indexes Still Matter

When filtering by tenant/status and sorting by `createdAt`, you need an index matching that access pattern. Valid connectivity and small projections do not prevent a `COLLSCAN` on their own.

## 26. Writing Data to the Selected Collection

~~~java
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import org.bson.Document;

// Assume db and orders were obtained from a valid MongoClient.
orders.insertOne(new Document("_id", "O-1001")
    .append("tenantId", "t-01")
    .append("status", "PENDING")
    .append("total", 120000));

orders.updateOne(
    Filters.and(
        Filters.eq("_id", "O-1001"),
        Filters.eq("tenantId", "t-01")
    ),
    Updates.set("status", "PAID")
);
~~~

**Run on lab environments only**: `insertOne`/`updateOne` will mutate live data if the URI points to production.

### 26.1. Databases and Collections Can Appear on Write

If a database or collection does not yet exist, an authorized write can implicitly create the namespace, depending on validators and options. Consequently, a typo in a database name may silently create a new collection instead of failing as the author expected. Use constants and integration tests to verify namespaces.

### 26.2. Write Permissions

A user with a read-only role can run `find()` successfully while `insertOne()`/`updateOne()` fail with Unauthorized. Verify user roles on the authentication database and the scope of granted privileges.

### 26.3. Mind `_id`

MongoDB requires `_id` to be unique within each collection. If omitted, the driver or server generates an ID depending on the API; the demo above sets an explicit ID for easy verification and to avoid accidental duplicate inserts.

## 27. Typing a Collection with a POJO

`Document` is flexible, but Java services often map documents to domain classes:

~~~java
public class Order {
    private String orderNo;
    private String status;
    private long total;

    public Order() {}

    public String getOrderNo() { return orderNo; }
    public void setOrderNo(String orderNo) { this.orderNo = orderNo; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public long getTotal() { return total; }
    public void setTotal(long total) { this.total = total; }
}
~~~

With a POJO codec:

~~~java
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.MongoCollection;
import org.bson.codecs.configuration.CodecRegistry;
import org.bson.codecs.pojo.PojoCodecProvider;

import static org.bson.codecs.configuration.CodecRegistries.fromProviders;
import static org.bson.codecs.configuration.CodecRegistries.fromRegistries;

CodecRegistry pojoRegistry = fromRegistries(
    MongoClientSettings.getDefaultCodecRegistry(),
    fromProviders(PojoCodecProvider.builder().automatic(true).build())
);

MongoDatabase db = client.getDatabase("shop")
    .withCodecRegistry(pojoRegistry);

MongoCollection<Order> typedOrders =
    db.getCollection("orders", Order.class);
~~~

Snippets belong in their respective files/classes with complete imports when integrated. `PojoCodecProvider.automatic(true)` is an easy-to-follow example; in production, carefully evaluate mapping conventions, immutable classes, IDs, enums, schema evolution, and testing.

### 27.1. Codecs Do Not Grant Extra Permissions

`MongoCollection<Order>` still uses `MongoClient`'s original credentials. POJO mapping only governs conversion between BSON and Java objects.

### 27.2. Field/ID Mismatch

If a document stores `_id: ObjectId` while the POJO declares `String id` without a compatible mapping, decoding will fail. Never assume merely changing the generic type makes the driver understand arbitrary schemas.

### 27.3. Decimals and Money

For monetary values, choose `Decimal128`/`BigDecimal` or integer minor units per your schema—avoid `double`, which introduces floating-point rounding errors. This is a data modeling decision, not a URI setting.

## 28. Configuring Concerns and Read Preference on Handles

After selecting a database, you can apply read/write policies to handles:

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;

MongoDatabase shop = client.getDatabase("shop")
    .withReadConcern(ReadConcern.MAJORITY)
    .withWriteConcern(WriteConcern.MAJORITY);

MongoCollection<Document> orders = shop.getCollection("orders")
    .withReadPreference(ReadPreference.primary());
~~~

### 28.1. `readPreference`

Controls which replica set member type the driver selects for reads when supported by topology. `primary` suits operations requiring primary reads; `secondary` can offload the primary while accepting potentially stale data per system semantics.

### 28.2. `readConcern`

Controls consistency and visibility guarantees of read data. It is not an authentication mechanism.

### 28.3. `writeConcern`

Controls write acknowledgment and durability policies. Never weaken it merely to lower latency when business rules require `majority` durability.

### 28.4. Handle Methods Return a New Handle

`withReadConcern`, `withWriteConcern`, and `withReadPreference` return a newly configured handle rather than mutating the entire `MongoClient` across all namespaces. Keep track of which handle serves which workload.

## 29. Configuring Multiple Databases in One Application

Example service using:

~~~text
MongoClient: mongodb://replica-set-cluster
    shop.orders
    shop.customers
    audit.events
~~~

Code:

~~~java
MongoDatabase shopDb = client.getDatabase("shop");
MongoDatabase auditDb = client.getDatabase("audit");

MongoCollection<Document> orders =
    shopDb.getCollection("orders");
MongoCollection<Document> customers =
    shopDb.getCollection("customers");
MongoCollection<Document> auditEvents =
    auditDb.getCollection("events");
~~~

### 29.1. One Client Does Not Span Multiple Clusters

If `shop` resides on cluster A and `audit` resides on cluster B, you need two `MongoClient` instances with matching URIs, credentials, and pools. Calling `getDatabase("audit")` on a client connected to cluster A **does not** switch to cluster B.

### 29.2. Role Boundaries

A user granted access to both `shop` and `audit` has a wider blast radius than a user restricted to `shop`. If privileges differ across services, consider separate clients and credentials per least privilege.

### 29.3. Dynamic Tenant Databases

If each tenant uses its own database, never take the database name directly from a user request without validation. Validate tenant identity from the auth context, map to allowed namespaces, and enforce quotas and permission isolation.

## 30. Do Database/Collection Handles Check Existence?

`getDatabase` and `getCollection` do not verify existence:

~~~java
MongoDatabase maybe = client.getDatabase("typo_databse");
MongoCollection<Document> coll = maybe.getCollection("orders");
~~~

Both lines succeed even with a misspelled database name. When you need to verify:

~~~java
for (String databaseName : client.listDatabaseNames()) {
    System.out.println(databaseName);
}

MongoDatabase db = client.getDatabase("shop");
for (String collectionName : db.listCollectionNames()) {
    System.out.println(collectionName);
}
~~~

### 30.1. Listing Is Not Always Complete for Every User

Results of listing databases/collections depend on privileges, authorization policies, and MongoDB options. A low-privilege user may be unable to list the entire cluster even when authorized to query its granted namespace. Avoid running an admin list operation in a read-only app's readiness check unless necessary.

### 30.2. `ping` Does Not Prove a Namespace Exists

`ping` can succeed while `shop.orders` has not been created yet or the user lacks permissions on it. To verify business readiness, run a **non-destructive** read/write smoke test with the actual credentials.

## 31. MongoDB Server Authentication vs. Internal Cluster Auth

For a Java application:

- The driver sends credentials for the **application user**.
- Self-managed clusters may use `keyFile` or X.509 between members; that is **internal cluster authentication**, not credentials the Java application supplies.
- Application→`mongod`/`mongos` TLS and inter-member cluster TLS are two distinct network paths.

Never attempt to read `mongod`'s `security.keyFile` and pass it to a service's `MongoClient`. Doing so crosses privilege boundaries and risks exposing cluster-wide shared secrets.

### 31.1. The Application Need Not Know a Fixed Primary

With a proper replica set URI/topology, the driver handles server selection. Never hardcode a primary hostname as a standalone server if automatic failover is required.

### 31.2. Sharded Clusters

Standard applications connect to `mongos` routers or the managed service endpoint, never writing directly to shard members to bypass routing and metadata. TLS and credentials must match the router endpoint.

## 32. Common URI Mistakes

| Error | Symptom | Fix |
|---|---|---|
| Invalid `mongodb+srv` syntax | Parser/DNS failure | Use valid `mongodb+srv://` syntax |
| Appending a port after SRV DNS name | Invalid URI | SRV takes a service hostname, not a port like standard URIs |
| Unencoded `@` in password | Host parsing/auth failure | Use `MongoCredential` or percent-encode properly |
| Missing `?` before options | URI parser error | Check path/options syntax |
| Unquoted `&` in shell | Shell splits command | Quote the URI properly in the shell |
| Wrong `replicaSet` | Server selection failure | Verify replica set name |
| Misused `directConnection=true` | No discovery/failover | Use normal replica set URI |
| Wrong `authSource` | Authentication failed | Specify database where user is defined |
| Unroutable hostname | Timeout/DNS failure | Fix DNS/network/advertised hosts |
| Outdated driver/JDK | SRV/TLS/mechanism unsupported | Upgrade to a tested compatible release |

### 32.1. Never Print Full URIs While Debugging

On parser errors, an app may accidentally log `mongodb://username:secret@...`. Redact usernames if needed and always strip passwords/tokens before emitting logs.

## 33. Distinguishing Important Connection Errors

| Symptom | Likely Layer | Check |
|---|---|---|
| `MongoConfigurationException` / URI parser | Client config | Scheme/options/credential format |
| DNS SRV lookup failure | DNS | SRV/TXT records, resolver/network |
| `MongoSocketOpenException` | Network | Host, port, firewall, running service |
| `MongoTimeoutException` / server selection timeout | Topology/connection | Nested causes, replica set health, DNS, TLS |
| `SSLHandshakeException` | TLS | CA, SAN, expired cert, protocol/EKU |
| `PKIX path building failed` | JVM trust | Truststore CA/intermediate chain |
| `MongoSecurityException` / Authentication failed | Login | Username/password, `authSource`, mechanism |
| `MongoCommandException` code Unauthorized | Authorization | Roles/collection privileges |
| `MongoWriteException` duplicate key | Data/index | Duplicate `_id`/unique index |
| Successful `ping` but `find` fails | Namespace/privilege/query | Roles, database name, collection name |

No single exception covers everything; the driver often wraps nested causes. Read the **root cause after redacting secrets**.

### 33.1. ServerSelectionTimeout Does Not Always Mean the Server Is Down

The driver may fail to select a server due to network issues, TLS handshake failures, wrong `replicaSet` name, nodes being secondary-only, firewalls, or DNS. Increasing the timeout does not fix the root cause.

### 33.2. Authentication Failed vs. Unauthorized

"Authentication failed" means identity could not be verified with the given credentials/mechanism; "Unauthorized" usually means identity was verified, but the user lacks permission for the command.

### 33.3. TLS Fails Before SCRAM

If the JVM does not trust the certificate, the connection aborts during the handshake before password verification even runs. Do not rotate database passwords when the root cause is `PKIX path building failed`.

## 34. Safe TLS Diagnostics

To inspect the server certificate from an authorized host:

~~~bash
openssl s_client \
  -connect mongo1.db.internal:27017 \
  -servername mongo1.db.internal \
  -CAfile /etc/app/tls/mongo-ca.pem \
  -verify_return_error
~~~

Inspect a public certificate file:

~~~bash
openssl x509 -in mongo-server.crt \
  -noout -subject -issuer -dates -ext subjectAltName
~~~

### 34.1. OpenSSL Success Is Not Enough

`openssl s_client` checks the TLS endpoint, not the MongoDB wire protocol, user authentication, replica discovery, or Java truststore. Follow up with your Java application or a Java `ping` smoke test.

### 34.2. Java SSL Handshake Logging

The JVM supports `javax.net.debug` options, though output can be massive and expose sensitive metadata. Enable only temporarily in sandbox/test with redaction and restricted access—never leave it enabled indefinitely in production.

### 34.3. Never Use `invalidHostNameAllowed(true)`

If SANs do not match, fix the hostname or PKI. Disabling hostname verification makes endpoint spoofing trivial and is unsuitable for production.

## 35. Secret Management and Per-Environment Config

Example configuration layout:

~~~text
Environment: production
MONGODB_URI = mongodb+srv://cluster-prod.example.mongodb.net/?tls=true
MONGODB_AUTH_DB = admin
MONGODB_TARGET_DB = shop
MONGODB_USERNAME = read from secret store
MONGODB_PASSWORD = read from secret store
MongoDB CA trust = managed by TLS trust configuration
~~~

In code, use strongly typed configuration and startup validation. Never allow a Java service to pick a production cluster from raw HTTP input.

### 35.1. Dev/Staging/Prod Isolation

Use separate MongoDB users per environment, preferably isolated clusters and restricted network access. A staging bug must never be able to write to production.

### 35.2. Credential Rotation

When passwords or CAs rotate, existing pooled connections may remain open while new connections use updated driver settings. Design a reload/restart mechanism and an overlap deployment plan; do not assume updating a secret file on disk updates running `MongoClient` instances automatically.

### 35.3. Never Hardcode Connection Strings in the Repository

Even without passwords, hostnames and cluster IDs reveal network architecture. Govern configuration via policy and avoid unnecessarily exposing production topology.

## 36. A Service Configuration Factory

Example helper creating `MongoClientSettings` from validated configuration:

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.MongoCredential;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

import java.util.Objects;
import java.util.concurrent.TimeUnit;

public final class MongoClientFactory {
    private MongoClientFactory() {}

    public static MongoClient create(
            String uri,
            String username,
            char[] password,
            String authDatabase
    ) {
        Objects.requireNonNull(uri, "uri");
        Objects.requireNonNull(username, "username");
        Objects.requireNonNull(password, "password");
        Objects.requireNonNull(authDatabase, "authDatabase");

        MongoCredential credential =
            MongoCredential.createScramSha256Credential(
                username, authDatabase, password
            );

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .credential(credential)
            .applicationName("order-service")
            .applyToSslSettings(ssl -> ssl.enabled(true))
            .applyToClusterSettings(cluster ->
                cluster.serverSelectionTimeout(5, TimeUnit.SECONDS)
            )
            .applyToConnectionPoolSettings(pool -> pool.maxSize(50))
            .build();

        return MongoClients.create(settings);
    }
}
~~~

This factory is illustrative: production also requires a truststore/`SSLContext` if using a private CA, audited settings, and lifecycle management. The URI must not contain conflicting credentials. The caller is responsible for closing the client at application shutdown.

### 36.1. Obtaining a Collection from the Factory

~~~java
MongoClient client = MongoClientFactory.create(
    uri, username, password, "admin"
);

MongoCollection<Document> orders = client
    .getDatabase("shop")
    .getCollection("orders");
~~~

In a real service, execute this once in startup/composition root and inject `orders` into components—never per HTTP request.

## 37. Integration Smoke Test

A connection smoke test should verify:

1. The URI parses cleanly.
2. Driver connects and TLS/auth succeed.
3. Namespace is right (no staging/prod mix-up).
4. Collection read permission is granted.
5. Query returns expected type and sample data.

~~~java
try (MongoClient client = MongoClients.create(settings)) {
    MongoDatabase admin = client.getDatabase("admin");
    admin.runCommand(new Document("ping", 1));

    MongoDatabase shop = client.getDatabase("shop");
    MongoCollection<Document> orders = shop.getCollection("orders");

    Document one = orders.find(
        Filters.eq("tenantId", "t-01")
    ).projection(Projections.include("_id", "orderNo")).first();

    System.out.println("Connectivity and authorized read OK");
}
~~~

Real code needs proper imports, null handling, and assertions; `one` may be `null` if no matching record exists. Never log documents containing PII unnecessarily. Only tests in an isolated environment with controlled fixtures can confirm correctness.

### 37.1. Testing Missing Privileges

A read-only account should fail writes as required by policy. Verify least privilege in integration/security tests, **never by attempting destructive writes against production**.

### 37.2. Testing Failover

In a staging replica set, test that the driver continues operating after a controlled failover, verifying hostname SANs, DNS, server selection, and retry behavior. Never step down a production primary solely to test a URI.

## 38. Resilience and Retryable Operations

A URI may include `retryWrites=true` and `retryReads=true` when supported by the driver and topology, however:

- Not every operation is retryable.
- Retries do not make an arbitrary non-idempotent command unconditionally safe.
- An operation that fails on the client may already have been applied on the server before the connection dropped.
- Applications need idempotency keys and duplicate handling where business rules demand it.

### 38.1. Retrying Is Not a Fix for Bad Credentials

If credentials are wrong, retrying repeatedly will not succeed; it can generate alert noise or trigger account lockouts in external identity systems.

### 38.2. Do Not Bypass TLS Handshake Errors

If the CA or SAN is wrong, retrying repeatedly will not fix the certificate. Fix trust and configuration.

### 38.3. Network Partitions

When no eligible primary exists, server selection timeouts will occur. Application-level retries must use deadlines, backoff, and business semantics to prevent overload when the cluster recovers.

## 39. Pre-Release Production Configuration Check

| Area | Question |
|---|---|
| URI | Do scheme, hosts, `replicaSet`, and SRV match the cluster? |
| Credentials | Are user, `authSource`, and `authMechanism` accurate and secrets not hardcoded? |
| TLS | Is TLS enabled with valid CA trust, SANs, expiry, and hostname verification? |
| Network | Are DNS, firewall/IP allowlist, and private endpoints working? |
| Driver | Do JDK/driver versions support the MongoDB Server, codecs, and auth? |
| Lifecycle | Is `MongoClient` singleton/pool reused and closed on shutdown? |
| Namespace | Do database/collection constants match production config? |
| RBAC | Does the user have least-privilege roles on the right namespaces? |
| Resilience | Have pool, timeouts, and retries been tested against workload? |
| Observability | Do metrics/logs redact secrets and include `appName`? |
| Tests | Have ping, query, failover, and negative auth tests passed? |

Never mark connectivity as "verified" merely because a `MongoClient` object was instantiated in the JVM.

## 40. Practice Exercise A — Reading a URI

Given:

~~~text
mongodb://mongo1.db.internal:27017,mongo2.db.internal:27017/shop?replicaSet=rs0&authSource=admin&tls=true&appName=warehouse-service
~~~

Answer:

1. What is the scheme?
2. What are the seed hosts?
3. Is `shop` a database path or a collection?
4. What is the authentication database?
5. What Java code obtains the `orders` collection handle?
6. Is TLS requested?

## 41. Practice Exercise B — URIs and Special Characters

A lab account password contains `@`, `/`, and `#`. Explain why concatenating it directly into the URI can break parsing. Write an approach using `MongoCredential.createScramSha256Credential` instead of URI userinfo.

## 42. Practice Exercise C — Authentication Source

A MongoDB user `orderApp` is created in the `admin` database with a role to read `shop.orders`. Java uses:

~~~text
mongodb://mongo1.db.internal:27017/shop?tls=true
~~~

but authentication fails. Assuming credentials are correct, which option should you inspect? Once authentication succeeds, does `getDatabase("shop")` authenticate a second time?

## 43. Practice Exercise D — Truststore

A Java app reports `PKIX path building failed` when connecting to MongoDB with a private-CA-signed certificate. `mongosh` connects successfully using `--tlsCAFile`. Outline the steps to check the JVM truststore, intermediate chain, SANs, and JDK TLS support.

## 44. Practice Exercise E — Replica Set Failover

A seed URI connects to `mongo1.db.internal` successfully. After the primary steps over to `mongo2.db.internal`, Java reports a hostname mismatch. Explain topology discovery, why `mongo2`'s certificate needs a matching SAN, and why `invalidHostNameAllowed(true)` must not be enabled.

## 45. Practice Exercise F — Selecting Databases and Collections

Write Java code using **one `MongoClient`** to access `shop.orders`, `shop.customers`, and `audit.events`. Then answer:

- Do `getDatabase`/`getCollection` automatically create namespaces?
- Do they re-authenticate with MongoDB?
- When are two `MongoClient` instances needed instead of one?

## 46. Practice Exercise G — POJO Mapping

Write an `Order` class and configure a `CodecRegistry` to obtain `MongoCollection<Order>`. State the risk if `_id` in MongoDB is an `ObjectId` while the POJO only defines a `String` without custom mapping.

## 47. Practice Exercise H — Distinguishing Errors

An application encounters these errors:

~~~text
1. SSLHandshakeException: certificate_unknown
2. Authentication failed
3. Unauthorized
4. MongoTimeoutException: server selection timeout
~~~

Classify each by TLS, authentication, authorization, or topology/network, and state the first check to perform.

## 48. Practice Exercise I — Settings Precedence

A URI contains `authSource=shop`, while the builder constructs `MongoCredential` with auth database `admin`. Explain why having two configuration sources causes confusion, and propose a clear policy so only one source determines the authentication database.

## 49. Practice Exercise J — Atlas SRV

A Java service is given the hostname:

~~~text
cluster0.example.mongodb.net
~~~

Construct a syntactically valid `mongodb+srv://` URI and list DNS SRV/TXT, TLS, network access, and credential requirements. Why must you not append `:27017` immediately after the SRV service name?

## 50. Practice Exercise K — Lifecycle and Pool

An HTTP service creates a new `MongoClient` on every request and closes it right before returning the response. Explain the cost of topology discovery, TLS, and pooling, how to refactor to a singleton, and which metrics to monitor (connections, pool wait, latency, CPU).

## 51. Practice Exercise L — Namespace Safety

An endpoint reads `database` and `collection` query parameters and passes them directly to `getDatabase`/`getCollection`. Identify risks of cross-tenant data exposure or writing to unintended namespaces. Design an identity-based allowlist/mapping.

## 52. Practice Exercise Answer Hints

**A:** Scheme `mongodb://`; seed hosts `mongo1`/`mongo2`; `shop` is the database path; `authSource=admin`; Java uses `client.getDatabase("shop").getCollection("orders")`; `tls=true` requires TLS.

**B:** Reserved characters in passwords break URI parsing if unencoded. Pass username/authDb/password via `MongoCredential` and keep only topology/options in the URI.

**C:** Ensure `authSource=admin` since the user lives in `admin`. `getDatabase("shop")` only selects the namespace and does not re-login.

**D:** The JVM truststore may lack the private CA even though `mongosh` received a separate CA file. Check root/intermediate CAs, SANs, validity, and JDK protocols; never bypass validation.

**E:** The driver connects to advertised replica set hosts; `mongo2`'s certificate must include a SAN for its actual hostname. Disabling hostname validation exposes the connection to MITM attacks.

**F:** One `MongoClient` can access multiple databases/collections in the same cluster; getting handles neither creates namespaces nor re-authenticates. Two separate clusters/credentials require separate clients/settings.

**G:** Use `PojoCodecProvider` + `CodecRegistry` and `getCollection("orders", Order.class)`; schema ID/type mismatches cause codec/decoding errors.

**H:** 1 TLS; 2 authentication user/mechanism/source; 3 authorization roles; 4 server selection/topology/DNS/TLS nested cause.

**I:** Avoid overlapping config; when using `MongoCredential`, omit conflicting auth user/password or `authSource` from the URI and document precedence in app config.

**J:** `mongodb+srv://cluster0.example.mongodb.net/?tls=true` illustrates the format. The driver needs DNS SRV/TXT, network access, CA trust, and credentials; SRV hosts cannot take ports like standard URIs.

**K:** Creating a client per request causes overhead and socket churn. Use a DI/container-managed singleton `MongoClient`; monitor pool waits, connections, CPU, and p95/p99 latency.

**L:** Validate tenant principal and map to allowed databases/collections; never accept raw user input as a namespace and never grant overly broad service-account roles.

## 53. Common Mistakes and Anti-Patterns

| Anti-Pattern | Consequence | Better Approach |
|---|---|---|
| Hardcoding passwords in URI/source | Secret leakage | Secret manager + `MongoCredential` |
| Leaving userinfo unencoded | Strange URI/auth errors | Percent-encode properly or separate credentials |
| Confusing `authSource` with target database | Authentication failed | Identify the DB holding the user |
| Using `getDatabase` to check if DB exists | False conclusions | Query/list with proper privileges |
| Creating `MongoClient` per request | Excess pools/TLS handshakes | Reuse singleton |
| Hardcoding replica set primary | Broken failover | Replica set URI / topology discovery |
| `directConnection=true` to hide DNS errors | No proper discovery | Fix advertised hosts/network |
| Java missing CA that `mongosh` has | TLS fails only in Java | Configure JVM truststore/`SSLContext` |
| Using trust-all `SSLContext` | Loses server identity verification | Install proper CA chain |
| Disabling hostname validation | Vulnerable to MITM | Fix SAN/DNS |
| Using cluster member cert for apps | Exposes internal identity | Use dedicated client PKI |
| Staging URI pointing to prod | Writes to wrong environment | Isolate environment config |
| Taking collection name from raw URL param | Reads/writes wrong namespace | Use allowlist mapping |
| Using root user for services | Huge blast radius | Enforce RBAC least privilege |
| Assuming `ping` proves write permission | Unauthorized errors on write | Run smoke test on right namespace/role |
| Raising pool/timeouts indefinitely | Resource pressure / hides root cause | Benchmark and troubleshoot |
| Logging full connection string | Exposes credentials/topology | Redact secrets |
| Treating `MongoCollection<Order>` as schema validation | Decode/logic errors | Use POJO codec + schema validation |
| Disabling TLS due to cert errors | Loses network security | Fix PKI/truststore |

## 54. Review Questions

**1. Which `MongoClient` interface does the MongoDB Java Sync Driver use?** — `com.mongodb.client.MongoClient`.

**2. Does `MongoClients.create(uri)` prove login succeeded?** — No; run `ping` or an operation to verify.

**3. How do `mongodb://` and `mongodb+srv://` differ?** — Direct seed hosts vs. discovery via DNS SRV/TXT records.

**4. Can you append a port after an SRV hostname like a standard URI?** — Not under standard SRV syntax.

**5. What is `replicaSet` in a URI used for?** — Identifying and discovering the target replica set.

**6. Is `directConnection=true` suitable for default automatic failover?** — No; use only when direct single-node mode is intentionally desired.

**7. What is `authSource`?** — The database used to authenticate the MongoDB user.

**8. Does `authSource=admin` force all queries to run against `admin`?** — No; `getDatabase("shop")` still selects `shop`.

**9. Does `getDatabase()` create a database on the server?** — No; it only creates a handle.

**10. Does `getCollection()` create a collection on the server?** — No; it only creates a handle.

**11. Can one client be used across multiple collections?** — Yes, within that client's cluster and credentials.

**12. Should you create a client per HTTP request?** — No; `MongoClient` is thread-safe and manages a pool.

**13. Where should SCRAM passwords be stored?** — In an appropriate secret management system, avoiding hardcoding and logs.

**14. Why do passwords containing `@` require care?** — Reserved characters confuse URI parsing if left unencoded.

**15. What does `MongoCredential.createScramSha256Credential` take?** — Username, authentication database, and password `char[]`.

**16. How does TLS server authentication differ from SCRAM?** — TLS secures and verifies the transport connection; SCRAM authenticates the database user.

**17. What does Java use a truststore for?** — Trusting the server's CA/certificate chain.

**18. Is the JVM truststore always identical to the OS CA store?** — Not necessarily.

**19. Does a SAN mismatch with the URI host cause problems?** — Yes; hostname validation will reject the connection.

**20. Which auth database does `MONGODB-X509` use?** — Typically `$external` per mechanism rules.

**21. Does mTLS automatically grant MongoDB `readWrite` permissions?** — No; the user and roles must still be configured.

**22. Does Atlas SRV use TLS?** — `mongodb+srv://` enables TLS by default; verify deployment settings and keep validation enabled.

**23. Does `Unauthorized` mean the password is wrong?** — Not necessarily; it usually means an authenticated user lacks permissions.

**24. Is `MongoTimeoutException` always caused by the server being down?** — No; it can be DNS, topology, TLS, or network issues.

**25. Does `readPreference` change the authentication source?** — No; it controls which topology member handles reads.

**26. Does `writeConcern` fix missing query indexes?** — No; it governs write acknowledgment and durability.

**27. What is a POJO codec used for?** — Mapping between BSON and Java classes.

**28. Can one `MongoClient` switch clusters via `getDatabase()`?** — No; `getDatabase()` only selects a DB on the connected cluster.

**29. Does a successful `ping` prove a collection exists?** — No.

**30. What is a sound connection testing approach?** — Verify URI/secrets/TLS, run `ping`, and execute a smoke test with the right namespace and roles.

## 55. Quick Reference Table

| Need | Mechanism / API |
|---|---|
| Connect via MongoDB URI | `MongoClients.create(uri)` |
| Detailed client configuration | `MongoClientSettings.builder()` |
| Parse URI | `new ConnectionString(uri)` |
| SCRAM user | `MongoCredential.createScramSha256Credential(...)` |
| Auth database | URI `authSource` or `MongoCredential` authDb |
| Select replica set | URI `replicaSet=rs0` |
| DNS SRV | `mongodb+srv://hostname/` |
| Enable TLS | URI `tls=true` or SSL settings |
| Trust private CA | JVM `trustStore` or custom `SSLContext` |
| Client mTLS | `KeyStore` + key managers/certificate |
| X.509 database auth | `MONGODB-X509`, `$external` |
| Connection pool | Shared `MongoClient` + pool settings |
| Test connectivity | `runCommand(new Document("ping",1))` |
| Select database | `client.getDatabase("shop")` |
| Select BSON collection | `db.getCollection("orders")` |
| Select POJO collection | `db.getCollection("orders", Order.class)` |
| Explicitly create collection | `db.createCollection("orders")` |
| Filter | `Filters.eq(...)` |
| Projection | `Projections.include(...)` |
| Bounded query | `find(...).limit(20)` |
| Read concern | `db.withReadConcern(...)` |
| Write concern | `db.withWriteConcern(...)` |
| Read preference | `collection.withReadPreference(...)` |
| List databases | `client.listDatabaseNames()` |
| List collections | `db.listCollectionNames()` |
| Close client | `client.close()` at shutdown |

## 56. Deployment Checklist

- [ ] Compatible Java Sync Driver and JDK versions selected?
- [ ] Correct URI scheme (`mongodb://` or `mongodb+srv://`)?
- [ ] Accurate replica set name, seed hosts, or SRV records?
- [ ] DNS, ports, firewalls/IP allowlists, and private endpoints working?
- [ ] TLS enabled per policy, no unapproved plaintext in production?
- [ ] JVM trusts the CA chain and SANs match every advertised host?
- [ ] Certificates unexpired with a rotation plan in place?
- [ ] No trust-all `SSLContext` or disabled hostname verification?
- [ ] Username/password retrieved from secret management, never hardcoded or logged?
- [ ] `authSource` and `authMechanism` match the provisioned user?
- [ ] No conflicting credential config between URI and builder?
- [ ] User has least-privilege roles on the target database/collections?
- [ ] `MongoClient` created once per cluster/settings and pooled?
- [ ] Pool sizes and timeouts benchmarked and monitored?
- [ ] Startup `ping` checks server selection, auth, and TLS?
- [ ] Database/collection selected via constants or validated mappings?
- [ ] Namespace names never constructed from raw user input?
- [ ] Understood that `getDatabase`/`getCollection` only return handles?
- [ ] POJO codec/schema mapping tested if using typed collections?
- [ ] Read concern, write concern, and read preference match business needs?
- [ ] Proper retry, backoff, and idempotency in place?
- [ ] Integration smoke test verifies privileges and target environment?
- [ ] Replica set failover tested in staging?
- [ ] Logs/metrics redact credentials, PII, and sensitive URIs?
- [ ] Runbooks exist for TLS, DNS, `authSource`, `Unauthorized`, and timeout errors?
- [ ] Secret/CA rotation and graceful shutdown plans established?

## 57. Conclusion

Connecting to MongoDB from Java requires configuring **the right topology, identity, and namespace**. `mongodb://` lets you specify seed hosts explicitly, while `mongodb+srv://` uses DNS SRV/TXT to discover endpoints; options such as `replicaSet`, `authSource`, `authMechanism`, and `tls` dictate how the driver locates servers and authenticates. Separate passwords from the URI using `MongoCredential` or a secret management system to minimize credential leakage risk.

**TLS** protects the network transport and verifies the MongoDB endpoint; private CAs must be trusted by the JVM, hostnames must match SANs, and certificates must be valid. For client certificates / `MONGODB-X509`, configure a `keyStore` and corresponding database user/roles. Never confuse the TLS handshake with SCRAM login, and never use a trust-all context to work around certificate errors.

After creating `MongoClient`, use `getDatabase()` and `getCollection()` to obtain handles—**not to create new databases or collections every time**. Reuse `MongoClient` and its connection pools across the application lifecycle; create a new client only when clusters, settings, or credentials genuinely require separation. Finally, consider configuration complete only after running `ping` and a **properly authorized read/write smoke test on the target namespace**, ensuring secret handling, TLS, logging, and failover all behave safely.
