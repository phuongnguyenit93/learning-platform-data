# Spring Boot Connection Configuration and Secret Management in Spring Data MongoDB

## 1. Context: Database Connectivity Is an Operational Contract

Spring Boot applications often connect to MongoDB with just a single URI configuration. In real-world environments, however, "being able to connect" is only the first step. The system must also:

- Select the right MongoDB deployment, database, and authentication source.
- Use TLS and verify server identity.
- Use a least-privilege principal per application and environment.
- Keep passwords or tokens out of source code, images, logs, and monitoring systems.
- Manage connection pools, timeouts, retries, topology discovery, and workloads.
- Rotate credentials and certificates without causing unexpected downtime.
- Run tests reliably and expose appropriate health signals.
- Clearly understand why Spring Boot 3.x configuration differs from 4.x.

This lesson belongs to the **Database Engine Document MongoDB** module, chapter **Spring Data MongoDB**, titled **Spring Boot Connection Configuration and Secret Management**.

### Objectives

After this lesson, you will be able to:

1. Distinguish between the MongoDB Java Driver, Spring Data MongoDB, and Spring Boot auto-configuration.
2. Choose either the synchronous or reactive dependency to match your application model.
3. Configure the URI, hostname, replica set, `authSource`, TLS, and SSL bundles.
4. Understand the configuration namespace differences between Spring Boot 3.5 and 4.x.
5. Use `application.yml`, profiles, environment variables, and externalized configuration without hardcoding secrets.
6. Load secrets from a Kubernetes-mounted configuration tree or a secret manager.
7. Customize `MongoClientSettings`, connection pools, and timeouts for the specific Boot version.
8. Configure SCRAM/X.509 authentication and identify IAM/OIDC options when supported by the deployment.
9. Design credential rotation using two principals to transition applications safely.
10. Design health checks, metrics, logging, and connection tests.
11. Diagnose DNS SRV, TLS, authentication, authorization, topology, timeout, and precedence misconfiguration errors.
12. Build a production deployment checklist and practice with scenario-based exercises.

**Scope:** Examples are based on common APIs of Spring Boot 3.5/4.x and compatible MongoDB Java Driver/Spring Data versions. Version-specific configuration details are noted separately. Never copy example credentials into production.

## 2. What Layers Make Up the System?

~~~text
HTTP Controller / Scheduled Worker
              |
              v
         Service layer
              |
      +-------+-------+
      |               |
      v               v
MongoRepository    MongoTemplate
      |               |
      +-------+-------+
              |
              v
       MongoDatabaseFactory
              |
              v
        MongoDB Java Driver
              |
        MongoClient / Pool
              |
      DNS + TLS + SCRAM/X.509
              |
              v
   MongoDB Atlas / Self-managed
~~~

- **MongoDB Java Driver:** manages the network protocol, topology discovery, connection pools, server selection, BSON, and authentication.
- **Spring Data MongoDB:** provides `MongoTemplate`, document mapping, repository abstractions, converters, and Spring integration.
- **Spring Boot:** auto-configures the relevant beans when matching dependencies and properties are present.

A connection error can originate at any layer. For example, a repository method may be completely valid, yet fail to execute queries because `MongoClient` is using the wrong `authSource`.

### 2.1. A MongoClient Should Be Long-Lived

`MongoClient` is thread-safe and designed to reuse its connection pool. Typically, one application process uses a single singleton bean managed by Spring Boot.

Do **not** create a new `MongoClient` per HTTP request. That causes connection churn, extra TLS/SCRAM handshakes, and can exhaust connection limits.

### 2.2. Spring Data Does Not Replace a Secret Manager

Spring Boot provides externalized configuration mechanisms, but `application.yml` or `@Value` alone does not provide encryption, storage, or rotation policies. You must combine them with a secrets manager, IAM, TLS, ACLs, and a credential lifecycle.

## 3. Choosing the Right Starter: Synchronous or Reactive?

If you are using Spring MVC with mostly blocking code:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
~~~

With Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'
}
~~~

If the application uses WebFlux and requires non-blocking database access:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
</dependency>
~~~

### 3.1. Do Not Mix Sync and Reactive Just Because "Reactive Is Faster"

- Synchronous: `MongoTemplate` and `MongoRepository`; blocking calls, straightforward when the rest of the stack is blocking.
- Reactive: `ReactiveMongoTemplate`, `ReactiveMongoRepository`, and Reactor types.
- A reactive endpoint calling a blocking repository will block threads unless handled properly, failing to achieve end-to-end non-blocking execution.

Include only the dependencies you actually need. Most subsequent examples use **synchronous Spring Data MongoDB**.

### 3.2. Let Spring Boot Manage Library Versions

With Maven/Gradle using the Spring Boot BOM/dependency management, avoid arbitrarily pinning MongoDB Java Driver or Spring Data versions outside the tested combination.

When upgrading the MongoDB server, verify the compatibility matrix of **server version + driver + Spring Data + Spring Boot**. Do not assume that an 8.x server is automatically supported by every older Boot/Driver release.

## 4. Crucial Detail: Spring Boot 3.x and 4.x Use Different Prefixes

Spring Boot changed the **MongoDB configuration namespace** in the 4.x line.

| Purpose | Spring Boot 3.5 | Spring Boot 4.x |
|---|---|---|
| MongoDB connection URI | `spring.data.mongodb.uri` | `spring.mongodb.uri` |
| Database name | `spring.data.mongodb.database` | `spring.mongodb.database` |
| Username | `spring.data.mongodb.username` | `spring.mongodb.username` |
| Password | `spring.data.mongodb.password` | `spring.mongodb.password` |
| Authentication database | `spring.data.mongodb.authentication-database` | `spring.mongodb.authentication-database` |
| SSL enabled | `spring.data.mongodb.ssl.enabled` | `spring.mongodb.ssl.enabled` |
| SSL bundle | `spring.data.mongodb.ssl.bundle` | `spring.mongodb.ssl.bundle` |
| Host / port | `spring.data.mongodb.host/port` | `spring.mongodb.host/port` |
| Repository settings | `spring.data.mongodb.repositories.*` | Check the exact version's configuration metadata; do not infer from the URI |

Reference sources: **Spring Boot 3.5 Common Application Properties** and **Spring Boot 4.x Common Application Properties**. When using 4.1, consult the documentation for the exact version selected.

### 4.1. Spring Boot 3.5 Example

`src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: orders-api
  data:
    mongodb:
      uri: "${MONGODB_URI}"
~~~

The environment variable corresponding to the **property** when using direct relaxed binding is `SPRING_DATA_MONGODB_URI`.

However, in the example above, the application reads a custom variable named `MONGODB_URI` via a placeholder; these are two different mechanisms and do not both need to be declared.

### 4.2. Spring Boot 4.x Example

~~~yaml
spring:
  application:
    name: orders-api
  mongodb:
    uri: "${MONGODB_URI}"
~~~

If configuring entirely through environment property names, Boot 4.x uses `SPRING_MONGODB_URI`.

### 4.3. Why Copying Old Examples Can Fail

An application upgraded from Boot 3.5 to 4.x that only keeps `spring.data.mongodb.uri` may fail to configure `MongoClient` as intended, either connecting to the default target or failing initialization. Do not verify by grepping YAML; inspect the **redacted effective configuration** and the actual server endpoint.

### 4.4. Choosing a Version-Specific Convention for Examples

From the next section onward, unless otherwise noted, the primary YAML blocks use **Spring Boot 4.x**. Every key place includes guidance for switching to the corresponding Boot 3.5 prefix.

## 5. Minimal Local Development Connection

For a lab-only local MongoDB instance, a Boot 4.x configuration:

~~~yaml
spring:
  mongodb:
    uri: "mongodb://127.0.0.1:27017/learning_db"
~~~

If using Boot 3.5:

~~~yaml
spring:
  data:
    mongodb:
      uri: "mongodb://127.0.0.1:27017/learning_db"
~~~

This is strictly a lab example. A local MongoDB without authentication or TLS is **not** a production model.

### 5.1. What Happens When No URI Is Declared?

Spring Boot has a version-specific default MongoDB URL (for example, documentation describes `mongodb://localhost/test`). Do not rely on defaults in production because:

- It is easy to connect to the wrong database or host.
- It can mask a missing environment variable incident.
- Operators may not realize where the actual target is pointing.

### 5.2. Production Should Fail Fast When Secrets Are Missing

Example:

~~~yaml
spring:
  mongodb:
    uri: "${MONGODB_URI}"
~~~

Do not place a default password or default production URI after a `:` in the placeholder. If the variable is absent, application startup should fail in a controlled manner rather than silently falling back to a lab account.

## 6. MongoDB URI: Reading the Components Correctly

A hypothetical connection string:

~~~text
mongodb://<user>:<percent-encoded-password>@db1.example.test:27017,db2.example.test:27017/orders?replicaSet=rs0&authSource=admin&tls=true&appName=orders-api
~~~

Components:

| Component | Meaning |
|---|---|
| `mongodb://` | Standard MongoDB URI protocol |
| `user/password` | SCRAM credentials if configured |
| `db1,db2` | Seed host list; the driver also discovers topology |
| `/orders` | Default database in the URI unless overridden |
| `replicaSet=rs0` | Requires the matching replica set |
| `authSource=admin` | Database where the server looks up the user for authentication |
| `tls=true` | Requires TLS |
| `appName=orders-api` | Identifies the application in client metadata/diagnostics |

**Warning:** Placeholders are not runnable URIs. Never copy a URI containing real passwords into documentation, PRs, or issues.

### 6.1. Passwords with Special Characters

In URI credentials, reserved characters such as `@`, `:`, `/`, `?`, `#`, and `%` must be percent-encoded according to MongoDB connection string rules.

For example, a password containing `@` cannot simply be inserted raw into the userinfo segment with the expectation that the parser will interpret it correctly. When possible, have the secret manager provide an already properly encoded URI, or use the `MongoCredential` and `MongoClientSettings` APIs for separated credential configuration.

### 6.2. authSource Differing from the Default Database

A user may live in the `admin` database while the application operates on `orders`:

~~~text
database used by app = orders
authSource = admin
~~~

If the user was created in another database, you must specify the matching `authSource`. An `AuthenticationFailed` error does not necessarily mean the password is wrong.

### 6.3. URI Takes Precedence Over Separate Host/Port/User/Password Properties

According to configuration metadata, when a URI is set, separate host/port/username/password properties may be ignored. Do not configure both:

~~~yaml
spring:
  mongodb:
    uri: "${MONGODB_URI}"
    username: "another-user"
    password: "another-password"
~~~

expecting the separate properties to override the credentials inside the URI. Choose **one configuration strategy** and verify the effective behavior for your Boot version.

### 6.4. Understanding Database Override

In Boot 4.x, `spring.mongodb.database` can override the database in the URI according to the docs; however, this does **not automatically change `authSource`**. Do not reuse a single app connection across multiple tenants or databases without checking permission boundaries and `MongoDatabaseFactory`.

## 7. mongodb+srv:// and MongoDB Atlas

Atlas typically provides a URI using DNS SRV:

~~~text
mongodb+srv://<user>:<encoded-password>@cluster0.example.mongodb.net/orders?authSource=admin&retryWrites=true&w=majority
~~~

With `mongodb+srv://`:

- The driver queries DNS SRV (and TXT records per MongoDB URI rules).
- Hosts are discovered from DNS rather than specifying an arbitrary seed host/port list.
- TLS is enabled by default for SRV usage per the MongoDB connection string specification, unless configured otherwise.
- DNS resolution and network connectivity to the actual hosts must work.
- The URI still requires valid credentials and permissions.

### 7.1. Atlas Requires All Three Conditions

- **Database user:** correct username, auth mechanism, and roles.
- **Network access:** IP access list, VPC/private endpoint, or appropriate network controls.
- **TLS:** verified certificate chain and hostname.

Missing any one of the three produces different failures: DNS/server selection, TLS handshake, authentication, or authorization.

### 7.2. Do Not Open a Wide IP Allowlist for Convenience

Avoid opening network access to all internet IPs in production. Use narrow network access policies, private connectivity whenever possible, and monitor changes.

### 7.3. SRV DNS Is a Distinct Failure Source

If the host running the application cannot query DNS SRV/TXT records or a policy blocks DNS, hostnames may fail to resolve even when the username and password are correct. Test DNS from the actual runtime container or VM rather than from your laptop.

## 8. Replica Set Discovery and Read/Write Semantics

Connecting to a replica set requires the driver to discover topology and identify the primary and secondaries. Configuring the seed list and `replicaSet` helps the driver validate the target topology.

### 8.1. Do Not Enable directConnection Arbitrarily

`directConnection=true` forces the driver to connect directly to a single node where permitted, altering topology discovery and behavior. It is useful in certain lab or tunneling scenarios, but is usually wrong for applications that rely on replica set failover.

### 8.2. Retryable Writes Are Not "Infinite Retries"

`retryWrites=true` lets the driver retry certain eligible writes when transient network or failover errors occur. It does not make every operation idempotent.

- Transactions follow their own retry rules.
- Business operations that emit external messages outside the DB may not be idempotent.
- Duplicate key or validation errors are not resolved by retries.

### 8.3. Read Preference, Read Concern, Write Concern

- **Read preference:** prefers reading from primary or secondaries, which can affect data freshness.
- **Read concern:** consistency and visibility guarantees for read data.
- **Write concern:** level of write acknowledgment, such as `majority`.
  
Do not arbitrarily switch `w=majority` to `w=1` to "reduce latency" without evaluating durability requirements.

### 8.4. Latency During Failover

A primary election can cause in-flight commands to fail and require the driver to perform a new server selection. Applications should set request deadlines, bounded retries, and realistic SLOs; never promise that a replica set URI eliminates all transient errors.

## 9. Spring Data: A Minimal Domain and Repository

Define a document for illustration:

~~~java
package example.orders;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import java.time.Instant;

@Document("orders")
public class Order {
    @Id
    private String id;
    private String tenantId;
    private String status;
    private Instant createdAt;

    protected Order() {
    }

    public Order(String id, String tenantId, String status, Instant createdAt) {
        this.id = id;
        this.tenantId = tenantId;
        this.status = status;
        this.createdAt = createdAt;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }
}
~~~

Repository:

~~~java
package example.orders;

import org.springframework.data.mongodb.repository.MongoRepository;
import java.util.List;

public interface OrderRepository extends MongoRepository<Order, String> {
    List<Order> findByTenantIdAndStatus(String tenantId, String status);
}
~~~

At startup, Spring Data creates the repository bean when component/repository scanning and dependencies are properly configured.

### 9.1. Collection Names Are Not Secrets

Collection, database, and environment names can still be sensitive infrastructure metadata, but passwords, private keys, and tokens are the secrets that require strict protection. Never use collection names as credentials.

### 9.2. Least Privilege

A repository that reads and writes `orders` does not need a `root` user. Create a database principal with least privilege; if a service is read-only, consider the `read` role or an appropriate custom role.

### 9.3. Auto Index Creation

Do not rely on automatic creation of all indexes in production without a migration plan, especially for large indexes or unique constraints. Manage index changes through controlled rollouts while observing write and storage effects.

## 10. MongoTemplate and MongoDatabaseFactory

Spring Boot can auto-configure `MongoTemplate` and `MongoDatabaseFactory` when the starter, settings, and conditions are met.

~~~java
package example.orders;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;
import org.bson.Document;

@Service
public class OrderLookupService {
    private final MongoTemplate template;

    public OrderLookupService(MongoTemplate template) {
        this.template = template;
    }

    public long countOrders() {
        return template.getCollection("orders")
            .countDocuments(new Document());
    }
}
~~~

This is a simple example and is not recommended as a full-collection count on hot paths with very large datasets.

### 10.1. Do Not Manually Create a MongoClient Bean If Auto-Configuration Suffices

When an application declares its own `@Bean MongoClient`, Spring Boot may back off from creating the default client and use yours instead. In that case, Boot properties you assumed were active may not be applied as expected.

Only customize the bean when there is a clear requirement, and explicitly document ownership of URI, TLS, credentials, pooling, and lifecycle configuration.

## 11. Configuration with application.properties and application.yml

Two equivalent approaches (Boot 4.x):

~~~properties
spring.application.name=orders-api
spring.mongodb.uri=${MONGODB_URI}
~~~

Or:

~~~yaml
spring:
  application:
    name: orders-api
  mongodb:
    uri: "${MONGODB_URI}"
~~~

### 11.1. Do Not Mix Multiple Property Locations Without Understanding Precedence

Spring Boot reads many property sources: command-line arguments, system properties, environment variables, external config files, classpath config, profile-specific documents, config imports, and more.

A value from a higher-precedence source can override a value in `application.yml`. Never assume "because the YAML file looks right, the runtime must be using it."

### 11.2. Verify the Target Without Printing Secrets

You need to verify that the app connects to the right cluster without logging the full URI. You can log **sanitized** metadata such as environment, application name, logical cluster ID, or permitted database name, avoiding passwords, tokens, and sensitive hostnames when unnecessary.

### 11.3. Never Use a Default Production Secret

Do not write:

~~~yaml
spring:
  mongodb:
    uri: "${MONGODB_URI:mongodb://admin:password@db.prod:27017/orders}"
~~~

This is an **anti-pattern**: when secret injection fails, the application silently falls back to hardcoded credentials.

## 12. Spring Profiles: local, test, staging, and production

Environment separation:

~~~text
application.yml
application-local.yml
application-test.yml
application-staging.yml
application-prod.yml
~~~

Common configuration:

~~~yaml
spring:
  application:
    name: orders-api
~~~

Local profile (Boot 4.x):

~~~yaml
# application-local.yml
spring:
  mongodb:
    uri: "mongodb://127.0.0.1:27017/orders_lab"
~~~

Prod profile:

~~~yaml
# application-prod.yml
spring:
  mongodb:
    uri: "${MONGODB_URI}"
~~~

### 12.1. Only Local/Test Should Have Weaker Settings in Isolated Labs

Never deploy the local profile to production. Control `SPRING_PROFILES_ACTIVE`, the runtime environment, and network access strictly.

### 12.2. Do Not Activate the Production Profile in Source Code

The active profile should be determined at the deployment layer through a controlled mechanism. Avoid letting developers switch profiles by editing and committing code.

### 12.3. Do Not Treat Profiles as a Security Boundary

A prod application running the right profile is still dangerous if its service account has overly broad permissions to read staging and prod secrets alike. Isolate real IAM, projects, database users, and KMS policies.

## 13. Environment Variables: Convenient but Limited

In Boot 4.x, there are two main strategies:

**Strategy A — Custom placeholder**

~~~yaml
spring:
  mongodb:
    uri: "${MONGODB_URI}"
~~~

The deployment provides `MONGODB_URI`.

**Strategy B — Direct relaxed binding**

Do not declare the URI in YAML; the deployment provides `SPRING_MONGODB_URI`.

In Boot 3.5, the corresponding environment property name is `SPRING_DATA_MONGODB_URI`.

### 13.1. Do Not Assume Environment Variables Are a Secure Vault

Environment variables can leak through:

- Process diagnostics and heap dumps.
- CI/CD job output.
- Debug logs and crash reporting.
- Scripts that print environment values.
- Operators with access to the container or host.

Never print the entire `env` or `printenv` output into a support ticket just to inspect one property.

### 13.2. Do Not Pass Passwords Directly in Shell History

Avoid commands containing plaintext secrets in command arguments or shell history:

~~~bash
# Anti-pattern: exposes secret in shell history/process arguments.
java -jar app.jar --spring.mongodb.uri="mongodb://admin:real-password@..."
~~~

Prefer secure secret injection from the runtime or secret manager. For a URI containing a password, treat the entire value as a secret.

### 13.3. Environment Variables Do Not Auto-Reload After Rotation

A Java process reads its environment at startup; when a Kubernetes Secret changes, the running process does not automatically receive the updated environment value. A rolling restart or a safe client recreation mechanism is required.

## 14. Spring configtree: Reading Secrets from Mounted Files

Spring Boot supports `spring.config.import` with the `configtree:` prefix. The filename becomes the property key, and the file contents become the property value.

Suppose the runtime mounts a secret:

~~~text
/run/secrets/mongodb/
    spring.mongodb.uri
~~~

The contents of `spring.mongodb.uri` hold the real URI and are managed outside Git.

Boot 4.x `application.yml`:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/mongodb/"
~~~

At startup, Spring Boot reads that file into the `spring.mongodb.uri` property.

### 14.1. Boot 3.5 Equivalent

If using Boot 3.5, the mounted filename is:

~~~text
spring.data.mongodb.uri
~~~

And `spring.config.import` still uses `configtree:/run/secrets/mongodb/`.

### 14.2. Do Not Use optional for Mandatory Production Secrets

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/mongodb/"
~~~

`optional:` allows skipping the directory if it does not exist. It is useful for certain dev setups, but in production it risks letting the app start with a default or wrong URI. If the secret is mandatory, do **not** mark it optional unless you have explicit validation and another required configuration source.

### 14.3. File Permissions

- Only the required workload identity/container should have read permission.
- Do not store private secrets at world-readable paths.
- Do not mount entire directories containing unrelated secrets.
- Avoid copying secret volumes into debug artifacts.
- Restrict access to the node and container host.

### 14.4. Mounted File Changes Do Not Mean MongoClient Changes

`configtree:` primarily loads properties during Spring startup. If the secret file changes while the process is running, an already-created `MongoClient` does not automatically update its credentials or `SSLContext`. A tested lifecycle refresh or restart is required.

## 15. Kubernetes Secrets and Spring Boot

A practical approach is provisioning a **Secret** from a secret manager/External Secrets/CSI and mounting it as a file into the Pod.

~~~text
Cloud/Vault secret source
           |
           v
    Secret delivery controller
           |
           v
     Kubernetes Pod volume
           |
     /run/secrets/mongodb/
           |
           v
     Spring configtree import
           |
           v
        MongoClient
~~~

### 15.1. Abbreviated Pod Spec Example for Boot 4.x

This is a **deployment spec excerpt**, not a complete manifest:

~~~yaml
spec:
  template:
    spec:
      containers:
        - name: orders-api
          image: registry.example.test/orders-api:approved-version
          volumeMounts:
            - name: mongodb-config
              mountPath: /run/secrets/mongodb
              readOnly: true
      volumes:
        - name: mongodb-config
          secret:
            secretName: orders-mongodb-connection
            items:
              - key: mongo-uri
                path: spring.mongodb.uri
~~~

Application configuration:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/mongodb/"
~~~

The `orders-mongodb-connection` Secret object must be provisioned through a secure workflow. Never commit a `stringData` manifest containing a real URI or password.

### 15.2. Base64 Is Not Encryption

Kubernetes Secret `data` commonly represents bytes in base64. This does **not** protect the contents from anyone with permission to read Secrets or etcd snapshots. You need Kubernetes RBAC, encryption at rest, network controls, and a secret lifecycle.

### 15.3. Grant Only Necessary Permissions

A Pod's service account should not have `get/list` permissions on all Secrets in a namespace when it only needs one mounted secret. Separate secrets by service and environment.

### 15.4. Be Careful When Using subPath

Kubernetes Secret volumes update files automatically over time, but mounts using `subPath` do not receive updates in the normal way. Even when a volume updates, the application still needs a mechanism to reload `MongoClient`.

### 15.5. Safe Rolling Restart

When credentials change:

1. Provision the new secret and corresponding database principal.
2. Start a canary Pod using the new secret.
3. Verify TLS, authentication, and business operations.
4. Roll out the remaining Pods gradually.
5. Confirm all workers and scheduled jobs have transitioned.
6. Revoke the old credential within the approved window.

## 16. Secrets Managers: Vault, AWS, Azure, Google

Typical options:

- HashiCorp Vault / Vault Agent.
- AWS Secrets Manager.
- Azure Key Vault.
- Google Secret Manager.
- Kubernetes External Secrets / CSI Secret Store integrations.
- Spring Cloud Vault / Spring Cloud Config or appropriately supported integrations.

### 16.1. Who Reads the Secret?

~~~text
Spring Boot workload identity
           |
           v
      Secret manager IAM
           |
           v
   Secret version "current"
           |
           v
   URI / username / password
           |
           v
     MongoClient startup
~~~

Prefer **workload identity** or short-lived cloud credentials instead of hardcoding a secrets manager API key just to fetch the database password.

### 16.2. Do Not Move Secrets from Git to an Unprotected Plaintext File

Moving `application.yml` out of the repository is insufficient if the file sits on a shared filesystem, public backup, or is readable by all Pods.

### 16.3. Config Import via Spring Cloud Integrations

Some Spring Cloud starters allow importing property sources from Vault or Config Server. Syntax, authentication backend, fail-fast behavior, lease renewal, and compatibility depend on the **Spring Cloud release train, Spring Boot version, and provider**. Do not assume every integration shares the same mechanism for refreshing `MongoClient`.

### 16.4. Consider Secret Manager Availability

The application may need to fetch the secret before constructing `MongoClient`. If the secret manager is unavailable, startup can fail. Design bounded retries, policy-compliant caching/leases, and safe recovery; never fall back to a hardcoded password.

## 17. SCRAM and the Authentication Database

SCRAM is the standard password-based authentication mechanism. MongoDB supports `SCRAM-SHA-256` and `SCRAM-SHA-1`; prefer the stronger mechanism supported by your deployment.

### 17.1. authSource Must Match Where the User Was Created

For example, if the service user is managed in `admin` while operating on the `orders` database:

~~~text
mongodb://<user>:<password>@db.example.test:27017/orders?authSource=admin&tls=true
~~~

If you specify `authSource=orders` when the user is actually defined in `admin`, the server may return `AuthenticationFailed` even though the password is correct.

### 17.2. Atlas Database Users Must Be Managed via Atlas

MongoDB Atlas database users are created and modified through the Atlas UI, CLI, Admin API, or supported integrations. Do not run self-managed commands like `db.changeUserPassword` directly on Atlas to manage users.

### 17.3. Creating a User in a Self-Managed Lab Environment

~~~javascript
use orders

db.createUser({
  user: "orders_api_v1",
  pwd: passwordPrompt(),
  roles: [
    { role: "readWrite", db: "orders" }
  ],
  mechanisms: ["SCRAM-SHA-256"]
});
~~~

Use this only in a self-managed lab with TLS/auth enabled and administrative privileges. If the user is created in the `orders` database, the URI uses `authSource=orders`, not `admin`.

### 17.4. Never Use the root User for Applications

A service that only reads and writes `orders` does not need `root` or `userAdminAnyDatabase`. Reduce blast radius by using dedicated principals per service, environment, and workload.

## 18. TLS: Transport Encryption and Server Identity Verification

TLS performs two critical functions:

1. Encrypts traffic from the Java Driver to MongoDB.
2. Allows the driver to verify the server via its certificate chain and hostname.

~~~text
Spring Boot / MongoClient
        |
  TLS + CA trust + SAN check
        |
        v
MongoDB / mongos
~~~

### 18.1. TLS Can Be Configured via URI

~~~text
mongodb://db.example.test:27017/orders?tls=true
~~~

With Atlas SRV, TLS is typically enabled by default per MongoDB SRV rules; CA and hostname verification must still remain enforced.

### 18.2. Do Not Use tlsInsecure as a "Quick Fix"

Options like `tlsInsecure=true`, `tlsAllowInvalidHostnames=true`, or a custom trust-all `SSLContext` weaken security and can allow server spoofing.

Fix the root cause: CA bundle, SAN, hostname, truststore, expiry, or network endpoint.

### 18.3. TLS and SCRAM Operate at Different Layers

A successful TLS handshake does not mean the username/password are valid; successful SCRAM authentication does not prove the application has the required collection write roles.

## 19. Spring Boot SSL Bundles

Spring Boot provides the **SSL bundle** concept for trust material and TLS options.

Boot 4.x:

~~~yaml
spring:
  mongodb:
    uri: "${MONGODB_URI}"
    ssl:
      bundle: "mongo-ca"
  ssl:
    bundle:
      pem:
        mongo-ca:
          truststore:
            certificate: "file:/etc/certs/mongodb-ca.pem"
~~~

Boot 3.5 uses `spring.data.mongodb.ssl.bundle` instead of `spring.mongodb.ssl.bundle`.

### 19.1. What Problem Do Bundles Solve?

Instead of writing custom `SSLContext` or trust manager boilerplate inside the application, you configure trust material through framework-supported Spring Boot SSL bundles.

### 19.2. CA Certificates Can Be Managed as Controlled Configuration

A CA public certificate is not a private key, yet truststore integrity is critical: injecting an untrusted CA can cause the driver to trust a spoofed server.

### 19.3. Client Certificates / mTLS

When using X.509 client authentication, you need an appropriate client certificate and private key in the keystore/`SSLContext`, along with MongoDB-supported user identity mapping. A truststore containing only a CA does not authenticate the client via X.509.

### 19.4. Does Replacing a Trust File Require a Restart?

Not automatically. Reload capability for SSL bundles and connection pools depends on the framework, source, implementation, and version. With `MongoClient`, creating new TLS connections or a new client is typically needed to validate against new certificates; plan a rolling restart or a controlled refresh mechanism.

## 20. X.509, IAM, and OIDC: When Not to Use Passwords

Depending on the MongoDB deployment, tier, and driver, you can use:

- X.509 certificate authentication.
- AWS IAM authentication.
- OIDC workload identity federation.

### 20.1. X.509

The client holds a private key and certificate, and MongoDB maps identity from the X.509 subject. Rotation requires managing certificates/keys, CA trust, and potentially MongoDB user mappings.

### 20.2. AWS IAM

The driver authenticates using AWS identity/credentials via supported mechanisms, avoiding long-lived MongoDB SCRAM passwords. Workloads still require proper IAM policies, credential refresh, and protection.

### 20.3. OIDC

Applications can use tokens from an IdP or workload identity federation when supported by the driver, server, and tier. Check MongoDB/Atlas support and configure `MONGODB-OIDC`/token callbacks per your driver version; never assume adding `authMechanism=MONGODB-OIDC` to the URI is enough in every environment.

### 20.4. Passwordless Does Not Mean Policy-Free

Overly permissive IAM policies, logged tokens, or exposed client private keys still create severe risk. Database permissions and token/certificate lifecycles must be evaluated independently.

## 21. Customizing MongoClientSettings Instead of Replacing the Entire Client

When auto-configuration is close to what you need, Spring Boot lets you register a `MongoClientSettingsBuilderCustomizer`.

**Version differences:**

| Spring Boot | Interface package |
|---|---|
| 3.5 | `org.springframework.boot.autoconfigure.mongo.MongoClientSettingsBuilderCustomizer` |
| 4.x | `org.springframework.boot.mongodb.autoconfigure.MongoClientSettingsBuilderCustomizer` |

### 21.1. Boot 4.x Example

~~~java
package example.orders.config;

import java.util.concurrent.TimeUnit;

import org.springframework.boot.mongodb.autoconfigure.MongoClientSettingsBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MongoTuningConfiguration {

    @Bean
    MongoClientSettingsBuilderCustomizer mongoClientTuning() {
        return builder -> {
            builder.applicationName("orders-api");
            builder.applyToConnectionPoolSettings(pool -> {
                pool.maxSize(40);
                pool.minSize(5);
                pool.maxWaitTime(2, TimeUnit.SECONDS);
            });
            builder.applyToClusterSettings(cluster ->
                cluster.serverSelectionTimeout(5, TimeUnit.SECONDS)
            );
            builder.applyToSocketSettings(socket ->
                socket.connectTimeout(3, TimeUnit.SECONDS)
            );
        };
    }
}
~~~

### 21.2. Boot 3.5 Import Change

In the code above, replace the import with:

~~~java
import org.springframework.boot.autoconfigure.mongo.MongoClientSettingsBuilderCustomizer;
~~~

Do not copy both imports at once. Ensure the actual MongoDB Java Driver and Spring Boot versions support the illustrated method signatures by using a compatible BOM.

### 21.3. Effect

- `maxSize(40)`: limits the number of connections in the pool per server.
- `minSize(5)`: minimum number of connections maintained per pool settings.
- `maxWaitTime(2s)`: maximum time to wait to check out a connection when the pool is busy.
- `serverSelectionTimeout(5s)`: time allowed to find a server eligible for the operation.
- `connectTimeout(3s)`: time allowed to establish a socket connection.

These numbers are **measurable example values**, not universal defaults or best settings for every application.

### 21.4. Do Not Overwrite Security Configuration

A customizer can modify `MongoClientSettings` as the builder is constructed. Avoid unintentionally resetting credential or SSL settings. After adding a customizer, verify URI, TLS, auth, and topology behavior as before.

### 21.5. Declaring a MongoClientSettings Bean Manually Can Cause Properties to Be Ignored

Spring Boot documentation notes that when you provide your own `MongoClientSettings` bean, auto-configuration behaves differently from auto-built settings; URI/host properties may not be applied as before. Prefer a small customizer instead of replacing the entire bean unless necessary.

## 22. Sizing the Connection Pool Through Measurement

For example, with 20 application Pods each configured with `maxSize=100`, the driver can open multiple connections to each server depending on topology and pool settings. Do not calculate exact total cluster connections as simply 20×100 without accounting for the number of target servers, monitoring connections, and actual workload activity.

### 22.1. Metrics to Monitor

- Pool checkout wait p95/p99.
- Pool checkout timeouts.
- Current/available connections on MongoDB.
- Total connections created rate.
- MongoDB command duration.
- Driver retries and server-selection timeouts.
- Node CPU, disk I/O, and queues.

### 22.2. A Larger Pool Cannot Fix Slow Queries

If a query takes 3 seconds because of a missing index, increasing the pool size allows more slow queries to run concurrently, worsening disk and CPU saturation.

### 22.3. Min Size, Idle Time, and TLS Handshakes

A higher min pool size can increase long-lived connections and startup overhead. Choose sizes based on traffic, CPU, Pod count, and connection limits—not by intuition that "more is always better."

### 22.4. Never Create a Pool per Request

Ensure the singleton `MongoClient` is a single reused bean. Multi-tenant or multi-client architectures may require multiple pools, in which case you must account for the total connection budget.

## 23. Different Timeouts—There Is No Single "Mongo Timeout"

| Timeout | Layer | Symptom When Exceeded |
|---|---|---|
| DNS resolution | DNS/OS | Host fails to resolve |
| Connection establishment | Socket/TCP/TLS | Unable to open socket/TLS |
| Server selection | Driver topology | Unable to find an eligible server |
| Pool checkout | MongoClient pool | Unable to acquire a connection in time |
| Socket read | Driver network I/O | Reading response takes too long |
| Operation deadline | Client/operation | Operation exceeds allowed duration |
| HTTP request | Application gateway/service | User-facing timeout |
| Transaction lifetime | MongoDB transaction | Transaction times out on server |

### 23.1. Example Harm of Overly Long Timeouts

If the HTTP timeout is 3 seconds while the driver server-selection timeout is 30 seconds, the request may time out for the user while background threads continue waiting. Design deadlines consistently across all layers.

### 23.2. Overly Short Timeouts Also Cause False Failures

A primary election lasting a few seconds can fall within expected failover behavior. Setting a 100ms server selection timeout on a production replica set can cause unnecessary failures.

### 23.3. Bounded Retries, Backoff, and Idempotency

Never retry indefinitely when the database is overloaded or unreachable. Retries must have a deadline, exponential backoff with jitter, and clear awareness of whether the operation is idempotent.

## 24. Managing Secrets Rotation: Same User or Two Users?

Suppose the API currently uses `orders_api_v1`. There are two strategies:

| Criterion | Rotate password on same user | Create user v2 |
|---|---|---|
| Two valid credentials simultaneously | Not with basic single-user rotation | Yes, during the transition window |
| Canary before revoking old | Harder | Easy |
| Ability to avoid downtime | Depends on exact consumer reload | Usually better |
| Cleanup | Less | Requires revoking user v1 |
| Compromised credential risk | Must revoke quickly | Do not keep v1 if compromised |

### 24.1. In Spring Boot, the Main Issue Is the Existing Pool

Changing the password in MongoDB while the application still runs a `MongoClient` built with the old password causes failures whenever the driver opens new connections. Some existing pooled connections may continue working briefly, making errors appear sporadic.

### 24.2. The Dual-Account Pattern

~~~text
Time T0:
 MongoDB: orders_api_v1 active
 Apps: all v1

Time T1:
 MongoDB: orders_api_v1 + orders_api_v2 active
 Secret Manager: v2 staged

Time T2:
 Canary app Pods: v2
 Remaining Pods: v1

Time T3:
 All Pods/workers/jobs: v2

Time T4:
 Revoke orders_api_v1
 Retire old secret version
~~~

### 24.3. Execution Steps

1. Inventory all services, batch jobs, ETL pipelines, scheduled tasks, and CI automation using v1.
2. Generate the v2 password in the secrets manager.
3. Create database principal v2 with equivalent or tightened roles.
4. Stage the new secret as a new version.
5. Roll out a canary Spring Boot Pod to **create a new MongoClient**.
6. Verify TLS, SCRAM, reads/writes, transactions, and latency.
7. Roll out gradually while monitoring auth code 18 and pool errors.
8. Verify scheduled consumers after a full run cycle.
9. Revoke user v1.
10. Retire/revoke the old secret version and retain an audit record.

### 24.4. Do Not Roll Back to an Old Password After Compromise

If rotation was triggered by credential compromise, rolling back to v1 reopens the attack vector. Follow incident response instead, revoke early, and accept containment measures within SLOs.

### 24.5. Keep Non-Secret Audit Evidence

Audit logs can record:

~~~json
{
  "event": "mongodb-credential-rotation",
  "service": "orders-api",
  "principal": "orders_api_v2",
  "result": "success",
  "newClientAuthenticated": true
}
~~~

Never store plaintext passwords or full URIs.

## 25. Secret Refresh Does Not Equal MongoClient Refresh

A common misconception:

~~~text
Kubernetes Secret updated
           |
           v
Mounted file changes
           |
      (not enough)
           |
           v
Spring Environment may not re-read yet
           |
      (not enough)
           |
           v
MongoClient pool still uses old config
~~~

### 25.1. Three Strategies

**A. Rolling restart:** simple and reliable if the application is stateless with enough replicas and solid startup/health checks.

**B. Controlled application-level MongoClient recreation:** more complex; requires draining traffic, pools, and requests and closing the old client. Never simply slap on `@RefreshScope` and assume connection pools updated.

**C. Driver-managed auth token refresh:** suitable for mechanisms such as OIDC when supported by driver and provider; must follow callback and expiration semantics.

### 25.2. Choose Based on SLA and Rotation Frequency

If passwords rotate every few months, a rolling restart is simpler than building a runtime client swap. If credentials are very short-lived, consider identity-based auth or a specialized integration.

### 25.3. Atomic Secret File Replacement

Secret mounts often swap symlinks or file metadata rather than overwriting contents in-place. A custom file watcher must handle these events appropriately; checking modification time alone is insufficient in many environments.

## 26. Health Checks with Spring Boot Actuator

Add the dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Spring Boot includes a MongoDB health contributor when matching configuration and beans are present. The `/actuator/health` endpoint can report underlying database status.

### 26.1. Expose Only Necessary Endpoints

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  endpoint:
    health:
      show-details: never
~~~

In production, `env`, `configprops`, `heapdump`, and similar endpoints require strict security policies; never expose all endpoints just to debug credentials.

### 26.2. Liveness, Readiness, and Startup Are Distinct

- **Liveness:** does the process need to be restarted?
- **Readiness:** is the process ready to receive appropriate traffic?
- **Startup:** has initialization completed?

If readiness depends unconditionally on MongoDB, a database outage can pull all Pods out of service or trigger a restart storm. Design probes around failure modes and the application's traffic strategy.

### 26.3. MongoDB Ping Does Not Guarantee Application Permissions

A successful MongoDB `ping` does not prove that repository queries have read/write permissions or that unique indexes are valid. Run separate canary business-level smoke tests and permission checks.

### 26.4. Do Not Turn Health Checks into Heavy Queries

Use lightweight operations with explicit timeouts and avoid scanning large collections. If every Pod calls `countDocuments()` across millions of documents every second, monitoring itself becomes a load generator.

## 27. Driver Instrumentation Without Data Exposure

The MongoDB Java Driver provides `CommandListener`, connection pool listeners, and monitoring hooks. A Spring Boot application can track:

- Command success/failure counts and durations.
- Pool checkout wait time.
- Server selection timeouts.
- Connections created/closed.
- TLS/auth failures.
- Retry patterns and topology changes.

### 27.1. Example Listener That Does Not Log Raw Commands

~~~java
package example.orders.config;

import com.mongodb.event.CommandFailedEvent;
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;
import java.util.concurrent.TimeUnit;

public final class SafeCommandListener implements CommandListener {
    @Override
    public void commandStarted(CommandStartedEvent e) {
        // Do not log e.getCommand(): it may contain customer PII.
        System.out.println("started " + e.getCommandName());
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent e) {
        System.out.println(
            e.getCommandName() + " success "
            + e.getElapsedTime(TimeUnit.MILLISECONDS) + "ms"
        );
    }

    @Override
    public void commandFailed(CommandFailedEvent e) {
        System.out.println(
            e.getCommandName() + " failed "
            + e.getElapsedTime(TimeUnit.MILLISECONDS) + "ms"
        );
    }
}
~~~

This code only illustrates the API. In production, use Micrometer metrics/tracing with sampling and controlled tags instead of `System.out`.

### 27.2. Registering the Listener via Customizer

In Boot 4.x:

~~~java
@Bean
MongoClientSettingsBuilderCustomizer commandObservability() {
    return builder -> builder.addCommandListener(new SafeCommandListener());
}
~~~

This bean must reside in a `@Configuration` class using the Boot 4.x import from section 21. Boot 3.5 only changes the interface import.

### 27.3. Never Log URIs or Query Values

Items to keep out of logs:

- Passwords, access tokens, and private keys.
- Full MongoDB URIs containing credentials.
- Full aggregation pipelines containing user values.
- Unredacted driver exception messages.
- Secrets manager environment variables.
- Full Actuator `/env` payloads.

## 28. Secret Masking Is Not the Only Control

Spring Boot Actuator sanitizes `env` and `configprops`, but security policy must never rely solely on masking.

- Logging frameworks may print properties before sanitization.
- Debug interceptors may print requests/responses.
- Heap dumps can retain secrets in memory.
- Build artifacts may package hardcoded `application-prod.yml`.
- K8s RBAC may permit others to read Secrets.
- CI pipelines may echo command-line arguments.

### 28.1. Use Secret Scanners

Use repository scanning, pre-commit checks, and CI secret detection. If a URI is ever committed, removing it from Git `HEAD` is insufficient: the credential must be rotated/revoked and historical exposure assessed.

### 28.2. Security Tests

You can automatically verify that:

- No literal passwords exist in `src/main/resources/application*.yml`.
- `tlsInsecure=true` does not appear in production configuration.
- `mongodb://admin:...` does not appear in logs or config.
- Containers do not run with world-readable mounted secret directories.
- Principals do not hold overly broad administrative roles beyond requirements.

## 29. Spring Boot Tests: Isolating the Test Environment

Never use production URIs in CI or test suites.

### 29.1. Use a Dedicated Test Database

~~~yaml
# application-test.yml - Boot 4.x
spring:
  mongodb:
    uri: "${MONGODB_TEST_URI}"
~~~

For Boot 3.5, switch to `spring.data.mongodb.uri`.

### 29.2. Testcontainers

Spring Boot supports Testcontainers service connections in compatible versions and dependencies. You can run integration tests against an isolated MongoDB container.

Options include:

- `@ServiceConnection` when using a compatible Spring Boot Testcontainers integration.
- `@DynamicPropertySource` to inject the container replica URI into the right property prefix.
- `MongoDBContainer` from Testcontainers (the package may vary across Testcontainers major versions).

Do **not** copy a Testcontainers 1.x import into 2.x without checking the dependency in use.

### 29.3. Idea with DynamicPropertySource

Pseudocode for Spring Boot 4.x:

~~~java
// Illustrative snippet - adjust container type/imports for your Testcontainers version.
@DynamicPropertySource
static void mongoProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.mongodb.uri", mongoContainer::getReplicaSetUrl);
}
~~~

For Boot 3.5, the key is `spring.data.mongodb.uri`. The `mongoContainer` variable must be declared and started properly per your Testcontainers setup; do not assume this abbreviated snippet compiles standalone.

### 29.4. Testing Connectivity and Permissions

Test:

1. Repository save/find operations.
2. Indexes and unique constraints per requirements.
3. Timeouts when the DB is temporarily unavailable.
4. Failover behavior if the test topology supports it.
5. Non-root privileges mirroring production least privilege.
6. Verifying CI has no access to read production secrets.

## 30. Debugging Errors: A Decision Tree

~~~text
Application cannot access MongoDB
              |
              v
      Read error category
       /       |        \
      /        |         \
 DNS/socket   TLS      Authentication
    |          |           |
    v          v           v
 Host/SRV    CA/SAN    user/authSource
 network     expiry    secret version
    |          |           |
    +----------+-----------+
               |
               v
    Server selection / topology
               |
               v
       Authorization / queries
               |
               v
       Pool and timeout / SLO
~~~

### 30.1. DNS SRV Failures

Test SRV/TXT queries directly from the Pod or VM. Possible issues include a resolver that does not support SRV, network policies blocking DNS, or stale DNS caches. Do not immediately assume a wrong password.

### 30.2. ServerSelectionTimeoutException

Possible causes:

- Seed hosts are unreachable.
- Wrong network ACL or private endpoint.
- Mismatched `replicaSet` name.
- Driver fails to discover members.
- TLS handshake failures.
- Primary unavailable.
- Timeout set too low for failover.

### 30.3. AuthenticationFailed / Code 18

Check:

- Username, password, and secret version.
- `authSource`.
- SCRAM vs. X.509/OIDC mechanism.
- URI percent-encoding.
- Whether the account was disabled, dropped, or rotated.
- Whether the user was created in the correct database or Atlas project.

Do not blindly reset the password before identifying the root cause.

### 30.4. Authorization Failure

If the connection succeeds but save/read is rejected, the user may lack required roles. The fix is granting a least-privilege role on the target resource—**never** granting `root`.

### 30.5. SSLHandshakeException / PKIX Failures

Typically inspect the CA chain, truststore, certificate SAN/hostname, expiration, and proxy/network interception. Never enable a trust-all SSL context.

### 30.6. Timeouts and Pool Exhaustion

If MongoDB commands are fast on the server but the API is slow, inspect pool checkout wait time, server selection, retries, and network latency. Do not blindly increase `maxSize`.

### 30.7. Connecting to the Wrong Database

Check the Boot version property prefix, active profile, environment precedence, database override, `authSource`, and target endpoint. Do not log the full URI "just to inspect it."

## 31. Error and Troubleshooting Table

| Symptom | Common Cause | What to Verify |
|---|---|---|
| Startup uses localhost | Property unbound or missing | Boot 3 vs 4 prefix, profiles |
| Valid URI but user auth fails | Wrong `authSource` or secret | User auth DB, credential version |
| Separate username/password ignored | URI is already set | URI precedence |
| Password with @/# fails parsing | Missing percent-encoding | URI syntax |
| Atlas SRV fails to resolve | DNS SRV/TXT/network | DNS from runtime |
| Server selection timeout | Host/TLS/topology | Driver logs, network, replica set |
| SSL handshake fails | CA/SAN/expiry | Truststore/SSL bundle |
| Ping OK but save fails | Missing authorization | Roles, collection privileges |
| App runs then pool exhausts | Concurrency/retries/pool sizing | Checkout wait, current connections |
| Only some Pods fail after secret rotation | Pods still hold v1 credentials | Rollout status and pools |
| K8s Secret updated but app uses old value | Env/startup config does not reload | Restart or client recreation |
| Prod YAML picks up lab URI | Wrong profile or precedence | Effective sanitized properties |
| Test suite writes to prod | CI uses production secret | Namespace and IAM isolation |
| Missing metrics | Actuator/exporter misconfigured | Health endpoint exposure/permissions |
| Logs contain URI | Unsafe debug/exception output | Redaction and log policy |
| New TLS cert deployed but old app keeps working | Pooled connections still alive | New TLS handshake |
| Boot 4 customizer fails to compile | Package moved | Boot 4.x import |
| Boot 3 customizer fails to compile | Wrong Boot 4.x import used | Boot 3.5 import |

## 32. Production Pre-Deployment Checklist

### Version and Dependencies

- [ ] Confirm whether Spring Boot 3.5 or 4.x is used.
- [ ] Use the property prefix matching that version.
- [ ] Use the Spring Boot BOM for Spring Data and the Java Driver.
- [ ] Choose sync or reactive to match the application architecture.
- [ ] Do not declare a custom `MongoClient` bean if auto-config suffices.
- [ ] Verify the customizer API package for the Boot version.

### Connection and Topology

- [ ] MongoDB URI points to the right cluster and region.
- [ ] `authSource` matches the database principal.
- [ ] SRV DNS works inside the runtime environment.
- [ ] TLS, CA, and hostname verification are enabled.
- [ ] Network access and Atlas project settings are correct.
- [ ] Replica set discovery and primary failover have been tested.
- [ ] Retry, read concern, and write concern match requirements.
- [ ] Connection pool is benchmarked and monitored.
- [ ] Timeouts align with HTTP request deadlines.

### Secrets

- [ ] No hardcoded credentials in Git or container images.
- [ ] URI/password come from a protected runtime secret source.
- [ ] Per-service and per-environment least-privilege DB users.
- [ ] Secret manager IAM has least privilege and auditing.
- [ ] Kubernetes RBAC and encryption at rest are configured properly.
- [ ] Do not use `optional:` for mandatory secrets without a safe fallback.
- [ ] Rotation owner, schedule, and consumer inventory are defined.
- [ ] Dual-account and rolling restart plan are in place.
- [ ] Never use compromised credentials as a rollback target.
- [ ] Logs, Actuator, metrics, and tickets do not leak secrets.

### Tests and Operations

- [ ] Isolated local and test databases exist.
- [ ] CI cannot read production MongoDB secrets.
- [ ] Health checks serve their proper role without overloading the DB.
- [ ] Canary verification covers new `MongoClient` and TLS handshakes.
- [ ] Functional tests verify queries, permissions, and business transactions.
- [ ] Alerts exist for auth failures, pool wait times, and latency.
- [ ] Runbooks exist for DNS, TLS, auth, topology, and rotation.
- [ ] Clear ownership and audit trails exist for config/secret changes.

## 33. Practice Exercises

### Exercise 1 — Technology Layers

Distinguish the roles of Spring Boot, Spring Data MongoDB, and the MongoDB Java Driver in a repository query.

### Exercise 2 — Sync or Reactive?

A Spring MVC application calls a blocking `MongoRepository`. Should it switch to reactive simply because it uses MongoDB?

### Exercise 3 — Boot 3.5 Prefix

Write an `application.yml` using `spring.data.mongodb.uri` and the `${MONGODB_URI}` placeholder.

### Exercise 4 — Boot 4.x Prefix

Write the equivalent configuration using `spring.mongodb.uri`. Name the environment variable used for direct relaxed binding.

### Exercise 5 — URI Composition

Explain `authSource`, `replicaSet`, `tls`, and `appName` in a URI.

### Exercise 6 — Credentials with Special Characters

Why must passwords containing `@` or `#` be percent-encoded when placed inside a URI?

### Exercise 7 — AuthSource

A user was created in `orders`, but the URI specifies `authSource=admin`. What can happen?

### Exercise 8 — Atlas SRV

When `mongodb+srv://` fails to resolve inside a Pod but works on a laptop, what should you check?

### Exercise 9 — Prefix Migration

An application migrates from Boot 3.5 to 4.x while keeping `spring.data.mongodb.uri`. Diagnose the symptoms.

### Exercise 10 — Property Precedence

`application-prod.yml` specifies URI A, yet at runtime the app uses URI B. Which property sources can override it?

### Exercise 11 — Profiles

Design local, staging, and production configurations that do not share database users.

### Exercise 12 — No Default Secret

Why is `${MONGODB_URI:mongodb://admin:password@...}` an anti-pattern?

### Exercise 13 — Configtree

Create a mounted file `spring.mongodb.uri` and configure `spring.config.import`. Does repository code need any changes?

### Exercise 14 — Kubernetes Secret

Explain why base64 is not encryption. Which RBAC permissions should be restricted?

### Exercise 15 — Mounted File Update

The secret mount updates inside a Pod, yet `MongoClient` does not change. Why?

### Exercise 16 — Secrets Manager

Design the flow from workload identity → secrets manager → Spring Boot, including behavior when the secret manager is unavailable.

### Exercise 17 — Least Privilege

An API that only reads reports currently uses the `root` role. Propose an appropriate principal and role.

### Exercise 18 — TLS Verification

An application fails with a PKIX error when the server rotates its CA. Why should you not enable `tlsInsecure`?

### Exercise 19 — SSL Bundle

Which property does Boot 4.x use to attach an SSL bundle to MongoDB? How does Boot 3.5 differ?

### Exercise 20 — X.509

Distinguish a CA truststore from a client certificate/keystore. Why doesn't a truststore automatically establish an X.509 database identity?

### Exercise 21 — Customizer

Write a `MongoClientSettingsBuilderCustomizer` that limits `maxPoolSize` and `serverSelectionTimeout`. State the imports for Boot 3.5 and 4.x.

### Exercise 22 — Pool Sizing

There are 20 Pods with max pool size = 100. Why can't you conclude the cluster always has exactly 2,000 active connections?

### Exercise 23 — Timeout Layers

Distinguish socket connect timeout, server selection timeout, and connection pool checkout wait.

### Exercise 24 — Dual Account

Design a v1 → v2 credential rotation covering canary, rollout, verification, and revocation.

### Exercise 25 — Secret Compromise

A production URI was committed publicly. Outline the steps to revoke, rotate, and audit—beyond just deleting the commit.

### Exercise 26 — Actuator

Why shouldn't `/actuator/env` be exposed to the internet? Does `/actuator/health` prove application reads and writes succeed?

### Exercise 27 — Testcontainers

Use `@DynamicPropertySource` to inject a MongoDB test URI. Which property keys apply to Boot 3.5 and 4.x?

### Exercise 28 — Driver Metrics

Design a `CommandListener` that logs only command name and duration without logging payloads containing PII.

### Exercise 29 — Authentication vs. Authorization

`ping`/authentication succeeds, yet repository `save` is denied. What should you investigate before changing the password?

### Exercise 30 — Topology Failures

Distinguish DNS, TLS, authentication, and server-selection timeout failures.

### Exercise 31 — Business Correctness

After MongoDB maintenance, health checks pass but paginated queries run 10x slower. Design a post-deploy verification step.

### Exercise 32 — Production Synthesis

Design a Spring Boot 4.x + MongoDB Atlas system serving an orders API:

- Use the synchronous starter and repositories.
- MongoDB SRV URI provided from a secrets manager.
- TLS trust and Atlas network controls.
- Least-privilege database user.
- Configtree volume with IAM/RBAC.
- `MongoClientSettingsBuilderCustomizer` for pool and timeouts.
- Actuator health and driver metrics.
- Integration tests with an isolated database.
- v1/v2 rotation via rolling restart.
- Alerting and an incident runbook.

## 34. Summary

**Spring Boot + MongoDB connection configuration** must be viewed as an operational design chain:

1. Spring Boot auto-configures `MongoClient` and Spring Data beans when matching dependencies and properties are present.
2. Spring Boot 3.5 uses `spring.data.mongodb.*`; the 4.x line moved connection settings to `spring.mongodb.*`.
3. The MongoDB URI governs host/SRV discovery, database, authentication source, TLS, and driver options; credentials inside the URI are secrets.
4. `application.yml` should contain placeholders or external config references, **never** production passwords.
5. Environment variables, configtree, Kubernetes Secrets, and cloud secret managers distribute secrets, but still require IAM/RBAC, auditing, encryption at rest, and lifecycle management.
6. TLS truststores/SSL bundles must verify CA and SAN; never disable hostname verification to mask connection issues.
7. `MongoClient` owns a connection pool and should be reused; timeouts and pool sizes must be measured from workloads rather than copied arbitrarily.
8. Secret rotation requires creating a new client/pool and verifying via canary; the dual-account pattern transitions workloads without abruptly cutting off the old principal.
9. Health checks, logs, driver metrics, and integration tests must validate not only connectivity pings, but also permissions and business behavior.

A secure system does not merely **connect to MongoDB**—it knows precisely **where it is connecting, under what identity, who controls the credentials, and how to rotate or revoke them without breaking the application**.

## Official References

- [Spring Boot 3.5 — Working with NoSQL Technologies](https://docs.spring.io/spring-boot/3.5/reference/data/nosql.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [Spring Boot 4.x — Working with NoSQL Technologies](https://docs.spring.io/spring-boot/4.0/reference/data/nosql.html)
- [Spring Boot 4.x — Common Application Properties](https://docs.spring.io/spring-boot/4.0/appendix/application-properties/index.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — SSL Bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html)
- [Spring Boot 3.5 API — MongoClientSettingsBuilderCustomizer](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/mongo/MongoClientSettingsBuilderCustomizer.html)
- [Spring Boot 4.x API — MongoClientSettingsBuilderCustomizer](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/mongodb/autoconfigure/MongoClientSettingsBuilderCustomizer.html)
- [Spring Data MongoDB — Connecting to MongoDB](https://docs.spring.io/spring-data/mongodb/reference/mongodb/configuration.html)
- [Spring Data MongoDB — MongoTemplate](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-api.html)
- [MongoDB Manual — Connection String Formats](https://www.mongodb.com/docs/manual/reference/connection-string/)
- [MongoDB Java Sync Driver — Connection Options](https://www.mongodb.com/docs/drivers/java/sync/current/connection/connection-options/)
- [MongoDB Java Sync Driver — Connection Pools](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/)
- [MongoDB Java Sync Driver — TLS](https://www.mongodb.com/docs/drivers/java/sync/current/security/tls/)
- [MongoDB Atlas — Database Users](https://www.mongodb.com/docs/atlas/security-add-mongodb-users/)
