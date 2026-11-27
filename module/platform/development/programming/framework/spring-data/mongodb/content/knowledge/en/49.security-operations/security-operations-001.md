# Managing URIs, Secrets, TLS, and Account Least Privilege

## 1. Context and Objectives

In the **SPRING_DATA_MONGODB** module, we use Spring Data MongoDB to connect, map documents, and operate on MongoDB via **MongoTemplate** or **repository**. Practicing queries, aggregations, indexes, transactions, reactive access, testing, and data performance diagnostics all depend on a properly configured database connection. The **Security and Operations** chapter focuses on how to manage that connection securely.

Suppose an order management service connects to the **shop** database. The service needs to read and update the **orders** collection, read-only access to the **customers** collection, and does not need to read **payroll** or administer MongoDB accounts. Data between Spring Boot and MongoDB must be encrypted; passwords must not be written to Git or logs; and the application account must have only the exact permissions required for business operations.

A working connection is not enough to prove a secure configuration. Four questions must be answered simultaneously:

1. **URI:** which cluster, database, authSource, and environment is the application pointing to?
2. **Secrets:** through what process are credentials provisioned, used, rotated, and revoked?
3. **TLS:** does the transport channel encrypt traffic and verify server certificates and hostnames?
4. **Least privilege:** does the account have only the required actions on the exact database/collections?

After this lesson, you will be able to analyze URIs, configure Spring Boot to receive secrets from outside the source code, set up TLS, create restricted MongoDB roles, verify permissions, and build a verifiable secret rotation workflow.

## 2. Defense Layers of a MongoDB Connection

~~~mermaid
flowchart LR
  A[HTTP client] --> B[Spring Boot service]
  C[Secret manager] -->|Credential| B
  B -->|MongoDB Driver over TLS| D[(MongoDB server)]
  D --> E[Authentication]
  E --> F[MongoDB RBAC]
  F --> G[(Allowed collections)]
~~~

| Mechanism | What it protects | What it does not replace |
| --- | --- | --- |
| Connection URI | Selects the right endpoint, database, authentication mechanism, and options | Does not keep passwords secret by itself |
| Secret manager | Manages access control, provisions, and revokes credentials | Does not encrypt the transport channel to MongoDB |
| TLS | Encrypts, protects integrity, and verifies the server when properly configured | Does not restrict an account's read/write permissions |
| MongoDB authentication | Identifies the connection identity | Does not mean access is allowed to every collection |
| MongoDB RBAC | Restricts actions and resources at the database/collection layer | Does not replace end-user tenant authorization |
| Observation and response | Detects errors, secret leaks, and expired certificates | Does not replace preventive configuration |

For example, a role allows the application account to find all documents in the orders collection. That role **does not** automatically prevent a user in tenant A from viewing orders belonging to tenant B. The application must use HTTP client authentication and tenant/owner conditions in queries.

## 3. MongoDB Connection URI Structure

### 3.1. `mongodb://` URI

General pattern:

~~~text
mongodb://[username:password@]host1[:port1][,host2[:port2],...]
           /[database][?option1=value1&option2=value2]
~~~

Example with **placeholder** values, not real login credentials:

~~~text
mongodb://{USER}:{ENCODED_PASSWORD}@db1.example.internal:27017,db2.example.internal:27017/shop?authSource=shop&replicaSet=rs0&tls=true
~~~

| Component | Meaning | Notes |
| --- | --- | --- |
| mongodb:// | List of hosts or replica set seeds | TLS can be enabled via connection options |
| username/password | Credentials used for authentication | Passwords in the URI may require percent-encoding |
| host:port | MongoDB endpoint | The driver may discover additional topology members |
| /shop | Default database for operations using the database from the URI | Does not automatically determine which database the user was created in |
| authSource=shop | Database containing the MongoDB user identity | May differ from the data database |
| replicaSet=rs0 | Expected replica set name | Must match actual infrastructure |
| tls=true | Enables TLS | Still requires CA and hostname verification |

**The database in the path and authSource are different.** If user orders_api is created in shop, you can use /shop?authSource=shop. If the user is created in admin but has a role with permissions on shop, you can use /shop?authSource=admin. Which collections an account is allowed to access is determined by roles.

If authSource is not specified, the driver uses default rules based on the URI and authentication mechanism. In multi-environment systems, authSource should be explicitly specified to avoid connection failures when changing accounts or databases.

### 3.2. `mongodb+srv://` URI

Example:

~~~text
mongodb+srv://{USER}:{ENCODED_PASSWORD}@cluster.example.net/shop?authSource=admin
~~~

With an SRV URI, the driver queries DNS **SRV** records to discover servers and may read certain options from **TXT** records. According to MongoDB URI rules, **mongodb+srv enables TLS by default** unless explicitly disabled by an option.

Do not change the prefix from mongodb:// to mongodb+srv:// if the cluster does not have proper DNS SRV records. With managed services, you must use the hostname and configuration provided for the cluster, including network and certificate requirements.

### 3.3. Percent-encoding credentials

A password may contain @, :, /, ?, #, [, ], or %, which are special URI characters. The credential part must be properly percent-encoded when placed in a URI.

~~~text
Illustrative password:  a@b/c?d
In URI:                 a%40b%2Fc%3Fd
~~~

If the secret manager stores a complete pre-encoded URI, the application consumes the string as-is; avoid double-encoding. If secrets are stored as separate username/password values, use standard APIs to build the connection string/credential instead of concatenating strings from untrusted input.

**Percent-encoding is not security encryption**: anyone with the URI can decode the password. The entire URI containing credentials must be protected as a secret.

### 3.4. Common options

| Option | Effect | Considerations |
| --- | --- | --- |
| authSource | Selects the authentication database | Must match where the user was created |
| tls | Enables/disables transport encryption | Production requires TLS and certificate validation |
| replicaSet | Specifies the replica set | Use only when matching the actual topology |
| retryWrites | Retries write operations if supported by driver and server | Does not replace business-layer error handling/idempotency |
| readPreference | Selects where reads go | May affect data freshness |
| w | Write concern | Affects write acknowledgment level, not permissions or encryption |
| serverSelectionTimeoutMS | Limits time spent selecting a server | Tune according to infrastructure and SLOs |
| appName | Attaches the application name for diagnostics | Do not put secrets in the name |

Do not add options you do not understand just to make an error disappear. Always verify against the driver, MongoDB version, and deployment policy.

## 4. Provisioning Secrets for Spring Data MongoDB

### 4.1. Spring Boot configuration

For an application using **Spring Boot 3.x** and standard MongoDB auto-configuration:

~~~yaml
# application.yml: keep only the configuration variable name
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
~~~

The MONGODB_URI variable is supplied by the runtime environment, deployment system, or secret manager. Do not place URIs containing real passwords in source code. Property names may change across Spring Boot lines (for example, MongoDB property structure in Spring Boot 4), so confirm metadata/documentation for the **exact version** used by the project. If manually creating a MongoClient or managing multiple clients, verify which auto-configuration is actually being used.

MongoTemplate, MongoRepository, or ReactiveMongoTemplate uses the configured MongoClient; the business layer does not need to access the password:

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class OrderReadService {
    private final MongoTemplate mongoTemplate;

    public OrderReadService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public long countPaidOrders(String authenticatedTenantId) {
        Query query = Query.query(
            Criteria.where("tenantId").is(authenticatedTenantId)
                .and("status").is("PAID")
        );
        return mongoTemplate.count(query, "orders");
    }
}
~~~

In a real system, the value of authenticatedTenantId must come from a verified security context/claims, never directly trusting a request parameter. This code snippet demonstrates MongoDB access, not a full Spring Security implementation.

### 4.2. Keep secrets out of common leak locations

Locations to specifically check:

- Committed application.yml, application.properties, Dockerfile, Helm values, or README files.
- Git history, CI job logs, test reports, build artifacts, tickets, and pull requests.
- Command-line arguments and shell history containing passwords.
- Startup logs, exception dumps, driver debug logs, and error collection systems.
- Monitoring dashboards, Actuator env/configprops administrative endpoints, or runtime configuration copies.

**Unsafe** example:

~~~java
// Do not use: exposes the URI containing username/password.
logger.info("MongoDB URI: {}", System.getenv("MONGODB_URI"));
~~~

Replace with non-sensitive information:

~~~java
logger.info("MongoDB client initialized for service {}", "orders-api");
~~~

If host/database diagnostics are needed, log an approved environment alias. Do not assume a custom regex masking a URI is sufficiently safe; passwords can appear in many formats and options. Restrict access to Actuator and test actual masking behavior.

### 4.3. Secret sources by environment

| Environment | Management source | Requirements |
| --- | --- | --- |
| Development | Uncommitted local secrets or a developer credential manager | Do not reuse production passwords |
| CI/Test | Dedicated test user/database, short-lived if possible | Do not grant production credentials to untrusted PRs |
| Staging | Secret manager for staging | Isolate permissions and data from production |
| Production | Secret manager or managed workload identity | Strict access control, auditing, rotation, and revocation |

In Kubernetes, Secret data is commonly represented in base64; **base64 is not secure encryption**. You must combine Kubernetes RBAC, encryption of Secrets at rest, restricting which Pods/namespaces can read them, and deployment policies. Secrets passed via environment variables can leak through debug/process dumps; mounted secrets require filesystem permissions and an appropriate reload plan.

### 4.4. Credential lifecycle

A standard workflow should include:

1. **Provisioning:** only necessary service identities/personnel are permitted to read secrets per environment.
2. **Usage:** do not place credentials in logs, telemetry, client error responses, or shell history.
3. **Auditing:** record who or which workload read/modified a secret without recording the secret value.
4. **Rotation:** follow a schedule or trigger upon suspected exposure; update applications in a controlled manner.
5. **Revocation:** disable the old identity after all dependent instances and jobs have switched to the new secret.
6. **Recovery:** maintain a re-issuance procedure if a deployment fails or a secret expires.

If a URI has ever been committed, deleting it from the current file **is not enough**: Git history, CI logs, or copies may still retain the secret. Treat it as a potentially compromised credential and rotate it according to the incident response procedure.

## 5. TLS: Protecting Transport and Server Identity

### 5.1. What does TLS guarantee?

Properly configured TLS provides:

- Encryption of requests, responses, and authentication credentials in transit.
- Integrity protection to detect tampered data.
- Verification of the server's certificate chain against a trusted CA.
- Verification that the connected hostname matches the certificate's Subject Alternative Name (SAN).

**TLS does not grant access permissions** and does not replace encryption at rest or field-level access control. An account with overly broad roles can still execute many commands over a completely valid TLS connection.

### 5.2. Enabling TLS without bypassing verification

~~~text
mongodb://{USER}:{ENCODED_PASSWORD}@db.example.internal:27017/shop?authSource=shop&tls=true
~~~

With a replica set, the driver can discover and connect to multiple different members. Certificates, hostnames, and network paths must be valid for **every selectable member**, not just the initial seed host.

Do not use **tlsAllowInvalidCertificates=true**, **tlsAllowInvalidHostnames=true**, or **tlsInsecure=true** as a workaround for errors in production. They can bypass server identity verification and expand the risk of endpoint spoofing.

### 5.3. Java truststore and internal CAs

The MongoDB Java Driver uses Java's TLS infrastructure. If the server certificate is issued by an internal CA, the JVM/MongoClient must be configured to trust that specific CA.

Example JVM **path** options, without containing a password:

~~~text
-Djavax.net.ssl.trustStore=/run/certs/mongodb-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

If the truststore has a password, that password must also be protected. JVM system properties can affect the entire process; if the application uses multiple backends with different CAs, consider a dedicated SSLContext per MongoClient to avoid altering the trust policy of unrelated connections.

If using **mTLS**, the client must present a certificate/private key as well as verify the server. MongoDB's X.509 mechanism can map a certificate to a user identity; roles/authorization still must be managed separately. Private keys must be protected and rotated as secrets.

### 5.4. Common TLS errors

| Symptom | Possible cause | Investigation direction |
| --- | --- | --- |
| PKIX path building failed | CA is not trusted or intermediate certificate is missing | Inspect the certificate chain and actual JVM truststore |
| Hostname verification failed | URI host does not match SAN | Fix DNS/URI or issue the proper certificate; do not disable hostname validation |
| SSLHandshakeException | Incompatible protocol/cipher, mTLS, or certificate | Cross-check client/server/JDK and secret-redacted logs |
| Server selection timeout | DNS, network, TLS, or topology | Check each layer rather than immediately blaming the password |
| One replica set member fails to connect | That member's DNS/certificate/network is misconfigured | Inspect every member discovered by the driver |

Do not attach private keys, passwords, full URIs, or sensitive dumps when submitting bug reports.

## 6. MongoDB Authentication and Least Privilege with RBAC

### 6.1. Authentication differs from authorization

MongoDB can authenticate user identities using SCRAM (commonly **SCRAM-SHA-256** when supported by the server) or deployment-approved mechanisms such as X.509. **Authentication** answers *which identity is connecting*; **authorization** answers *which actions that identity is allowed to perform on which resources*.

MongoDB uses **Role-Based Access Control (RBAC)** with built-in and custom roles. If only a few operations on a few collections are needed, grant a role scoped strictly to that boundary instead of granting broad administrative privileges.

Example separation of accounts:

| Account | Job | Recommended permission scope |
| --- | --- | --- |
| orders_api | Read/insert/update orders, read customers | find/insert/update on shop.orders; find on shop.customers |
| orders_report | Read-only reporting | find on strictly required collections |
| migration_job | Schema changes, creating/modifying indexes during deployment | Dedicated role, scoped to the task and execution window |
| db_operator | Create users/roles, administer database | Separate account, never used as runtime credentials |

Built-in roles such as **read** or **readWrite** may be appropriate when each application owns a dedicated database and is allowed to operate across the entire database. However, an API that only needs permissions on the orders collection should not automatically receive **dbOwner**, **root**, or **readWriteAnyDatabase**.

### 6.2. Example creating a collection-scoped role

Suppose the **shop** database has access control enabled and an operator logs in with an account authorized to create roles/users. In **mongosh**:

~~~javascript
use shop

db.createRole({
  role: "orders_api_role",
  privileges: [
    {
      resource: { db: "shop", collection: "orders" },
      actions: [ "find", "insert", "update" ]
    },
    {
      resource: { db: "shop", collection: "customers" },
      actions: [ "find" ]
    }
  ],
  roles: []
});

db.createUser({
  user: "orders_api",
  pwd: passwordPrompt(),
  roles: [
    { role: "orders_api_role", db: "shop" }
  ]
});
~~~

The **passwordPrompt()** function in mongosh prompts for the password interactively, avoiding storing the raw password in command history. In environments with a secret manager, operators should use the appropriate provisioning process while never printing passwords in scripts or logs.

The role above **only grants**:

- find, insert, update for the shop.orders collection.
- find for the shop.customers collection.
- Does not grant remove on orders or writes on customers.
- Does not grant permissions on shop.payroll, other collections, or other databases.
- Does not grant createIndex, dropCollection, createRole, createUser, or administrative commands.

This holds true as long as the account is not assigned other broad roles; effective and inherited roles must be verified. Do not run **db.createRole/db.createUser during application startup**: administrative privileges belong in a separate provisioning/operations step.

### 6.3. Separating runtime permissions from migration/index permissions

Spring Data MongoDB can create indexes via MongoTemplate.indexOps or annotations. With the role above, index creation will be denied due to missing the **createIndex** privilege. This is intentional by design: the runtime application does not need to alter schemas/indexes every time it starts.

One of the following models can be applied:

1. Use a migration_job account with appropriate permissions to create or modify indexes during deployment, then revoke temporary permissions.
2. If the architecture genuinely requires the application to manage indexes itself, grant only the necessary actions with a specific scope and monitor those changes.

For aggregations containing **$out** or **$merge** stages, you must evaluate write permissions on the target collection and related privileges; the find privilege does not automatically allow writes. Similarly, backup, monitoring, or schema migration typically require a different permission set from normal read/write APIs.

### 6.4. Watch out for GridFS and multiple collections

GridFS typically stores metadata in **fs.files** and binary chunks in **fs.chunks** (for the default bucket). If an API uses GridFsTemplate to download files, the account needs read access to **both collections**. If uploading or deleting, appropriate write/delete permissions must be added on both metadata and chunks.

Some drivers or bucket initialization workflows may need to create collections/indexes; perform this step via the migration/provisioning account. When changing the bucket prefix, verify the actual collection names rather than hardcoding fs.files/fs.chunks.

### 6.5. RBAC does not replace business authorization

The orders_api account can read any order in the orders collection. When an HTTP user requests an order, the application layer must still restrict by tenant/owner:

~~~java
Query query = Query.query(
    Criteria.where("_id").is(orderId)
        .and("tenantId").is(authenticatedTenantId)
);
~~~

In a real system, authenticatedTenantId must originate from an authenticated and authorized identity, never taken directly from a caller-supplied query parameter. If an API looks up solely by _id and omits business authorization, users can encounter **IDOR** vulnerabilities even when the MongoDB account has a tightly scoped role.

## 7. Verifying Authentication and Access Permissions

### 7.1. Connecting without putting passwords on the command line

Example mongosh with a passwordless URI, requiring TLS:

~~~bash
mongosh "mongodb://db.example.internal:27017/shop?authSource=shop&tls=true" \
  --username orders_api \
  --password
~~~

When run interactively, mongosh will prompt for the password. This avoids printing the password directly on the command line, though terminal environments, process read permissions, and error collection tools still need to be managed. If using a private CA, configure appropriate trust settings before connecting.

Inside the session:

~~~javascript
// Shows the identity and effective privileges of the current session.
db.runCommand({ connectionStatus: 1, showPrivileges: true });

// Two read-only queries matching the granted permissions.
db.orders.find({}, { _id: 1 }).limit(1).toArray();
db.customers.find({}, { _id: 1 }).limit(1).toArray();
~~~

The connectionStatus command can verify the actually authenticated user and roles. Access to its output should be controlled. Verification must use **the runtime account itself**; using root/operator cannot prove least privilege.

In **staging/test**, you can verify that forbidden operations (such as writing to customers or reading payroll) fail with an unauthorized error. Do not create negative tests that could modify or delete production data.

### 7.2. Layer-by-layer diagnostics

~~~mermaid
flowchart TD
  A[MongoDB access error] --> B{DNS and network working?}
  B -->|No| C[Check DNS, firewall, network policy]
  B -->|Yes| D{TLS handshake and cert valid?}
  D -->|No| E[Check CA, SAN, truststore, protocol]
  D -->|Yes| F{Authentication succeeded?}
  F -->|No| G[Check authSource, credentials, mechanism]
  F -->|Yes| H{Command authorized?}
  H -->|No| I[Check role, action, and collection]
  H -->|Yes| J[Measure pool, latency, and query plan]
~~~

| Symptom | Layer to check | Remediation direction |
| --- | --- | --- |
| UnknownHost / SRV lookup failed | DNS/URI | Hostname, SRV/TXT, DNS, and network policy |
| Server selection timeout | Network/TLS/topology | Check connectivity to members, certificates, and firewalls |
| SSLHandshakeException / PKIX | TLS | CA chain, truststore, hostname, expiration date |
| Authentication failed | Auth | authSource, username, password encoding, auth mechanism |
| Not authorized to execute command | RBAC | Effective roles, actions, and accessed namespace |
| Index creation denied at startup | RBAC/index lifecycle | Separate migration account or fix index management workflow |
| Wrong tenant data read | Business authorization | Verify tenant/owner conditions and HTTP authentication |
| Increased latency | Pool/query/index/DB load | Monitor timeouts, metrics, and explain; never broaden permissions to resolve |

A **successful ping command** only indicates that communication with the server succeeded at the moment of the check. It does not prove that the right cluster was used, that the account has appropriate permissions, or replace certificate/hostname verification.

## 8. Rotating Credentials and Certificates

### 8.1. Why does password rotation require coordinating multiple instances?

The MongoDB Java Driver maintains a **connection pool**. Old and new connections may be in different authentication states when a password is changed on the server. If the password is changed before applications use the new credential, instances opening new connections may begin failing.

A dual-identity workflow (when infrastructure allows):

1. **Provision new credentials** for the next user with the same role as the current account, re-verifying least privilege.
2. **Test the new connection** with valid TLS and queries within the permitted scope.
3. **Update the secret and perform a rolling deployment**; new instances create MongoClient/connection pools with the new credentials.
4. **Monitor** authentication errors, pool usage, request failures, latency, and percentage of rotated instances.
5. **Revoke the old account** once all dependent instances and jobs have successfully transitioned.
6. **Record** timestamp, secret version, test results, and owner; never include passwords in reports.

If the system only allows changing the password of a single username, do not assume both old and new passwords are accepted simultaneously. Account for maintenance windows, deployment synchronization capabilities, or transition mechanisms supported by your infrastructure.

### 8.2. Rotating CAs and TLS certificates

- Distribute truststores containing the new CA to clients before replacing server certificates, following an approved trust overlap window.
- Verify correct SANs/hostnames for every member and expiration dates.
- If using mTLS, replace client private keys/certificates and reconcile X.509 identities/roles if needed.
- Monitor handshakes during the overlap period; remove the old CA only after all clients have migrated.

Passwords, CAs, and certificates have different lifecycles; do not bundle changes without a monitoring and rollback plan.

### 8.3. When a secret leak is suspected

If a URI containing a password appears in Git, logs, or artifacts:

1. Restrict access to the exposed location and notify security/operations owners via appropriate channels.
2. **Rotate or revoke the credential**, because merely deleting the string from the current file does not remove it from Git history, caches, or copies.
3. Review audits, anomalous activity, and the permission scope of the exposed account.
4. Deploy the new secret and re-verify TLS and authentication.
5. Address the root cause: log masking, secret scanning, secret store permissions, and CI policies.

Never attach the raw leaked password to investigation reports.

## 9. Integration and Testing with Spring Data MongoDB

### 9.1. A connection and read-permission smoke test

In a Spring Boot test application configured with a URI from a test secret source:

~~~java
package example.security;

import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class MongoSecuritySmokeTest {

    @Autowired
    MongoTemplate mongoTemplate;

    @Test
    void canPingAndQueryAllowedCollection() {
        Document ping = mongoTemplate.getDb()
            .runCommand(new Document("ping", 1));
        assertEquals(1.0, ((Number) ping.get("ok")).doubleValue());

        // The collection may be empty; not throwing an error is sufficient for this smoke test.
        mongoTemplate.findOne(
            new Query().limit(1),
            Document.class,
            "orders"
        );
    }
}
~~~

This test **only proves** that a connection and a read query succeeded using the test credentials. It does not by itself prove that TLS verified the hostname, that the role is minimal, or that the API prevents cross-tenant access. Additional negative tests in staging and inspection of actual deployment environment configuration are required.

### 9.2. Security test matrix

| Scenario | Expected result |
| --- | --- |
| Missing required URI configuration | Application does not unintentionally fall back to a production database |
| Password contains special characters in URI | Connects using proper percent-encoded value; password not written to logs |
| Wrong authSource/password | Authentication rejected; error message contains no secrets |
| Invalid CA or hostname | TLS rejects connection; does not fall back to insecure mode |
| orders_api reads orders/customers | Succeeds with granted permissions |
| orders_api writes to customers | MongoDB denies in test/staging |
| orders_api reads payroll | MongoDB denies in test/staging |
| orders_api creates index/drops collection | MongoDB denies if role does not grant privilege |
| Tenant A user requests Tenant B order | HTTP/service denies per business rules |
| Credential rotation with multiple running instances | New instances authenticate successfully; old account revoked after transition |
| Certificate nearing expiration | Alert triggered ahead of expiration per policy |

Do not run destructive write/delete tests in production. In production, verify roles via configuration reads, audits, and read-only smoke tests; execute negative tests in a test environment with equivalent permissions.

### 9.3. Pre-traffic checklist

1. **URI:** correct hostname, database, authSource, replica set/SRV, and driver version.
2. **Secrets:** retrieved from an approved source, not committed/logged, readable only by required workloads.
3. **TLS:** valid CA chain, SAN/hostname, truststore, and certificates; no bypass configurations.
4. **Accounts:** correct user, roles, and actions per database/collection; migration/operator accounts separated.
5. **Spring Boot:** version-appropriate properties; MongoClient actually receives expected configuration.
6. **Application:** cross-tenant access tested, data scoped to HTTP user permissions.
7. **Rotation:** credential and certificate rotation rehearsed, with revocation/rollback plan.
8. **Monitoring:** alerts for authentication errors, TLS expiration, pool saturation, timeouts, and anomalous access.

Deployment records should capture configuration version, cluster alias, roles/collections/actions, test results, timestamp, and owner; **never store passwords, private keys, or full URIs**.

## 10. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Committing URIs with passwords to Git | Leaks via history and copies | Use a secret manager; rotate if exposed |
| Treating percent-encoding as encryption | Password can be decoded immediately | Protect the entire URI |
| Using root for a web service | Credential leak can cause broad impact | Small roles scoped by collection/action |
| Enabling TLS but skipping certificate validation | Risk of endpoint spoofing | Fix CA/certificate and verify SAN |
| Omitting authSource | Hard to diagnose authentication errors across environments | Explicitly specify the user database |
| Auto-creating indexes with a restricted runtime account | Unauthorized errors at startup | Separate index migration/provisioning |
| Granting find only on fs.files and forgetting fs.chunks | Unable to download GridFS content | Grant proper permissions on both collections |
| Assuming MongoDB roles replace tenant authorization | Possible reading of another tenant's data | Check owner/tenant in the API |
| Changing server password before deploying new clients | Connection pool fails creating new connections | Rolling rotation with verification |
| Only checking ping | Misses overly broad roles and wrong endpoints | Verify TLS, user, roles, and business authorization |
| Printing the URI in logs for debugging | Expands secret exposure scope | Log only approved environment aliases and metadata |

## 11. Hands-On Exercise

Prepare a MongoDB test environment with authentication and TLS enabled:

1. Using a test operator account, create the shop database with orders, customers, and payroll collections.
2. Create orders_api_role as shown in section 6 and provision the orders_api user via passwordPrompt or your environment's secret provisioning tool.
3. Supply the URI to Spring Boot via MONGODB_URI, enabling TLS and a truststore if needed; keep all credentials out of Git.
4. Verify MongoTemplate can read orders/customers. In staging, confirm writing to customers and reading payroll are denied.
5. Intentionally use an incorrect authSource and a truststore that does not trust the CA in a controlled test; confirm the errors and then restore valid configuration.
6. Write an endpoint that reads an order by tenantId from the security context; attempt to access an order from another tenant.
7. Create a successor identity with an equivalent role, perform a rolling deploy with the new credential, and revoke the old account after all instances stabilize.
8. Compile a report containing only non-secret configuration, granted roles/actions, test results, certificate expiration dates, and the rotation schedule.

**Self-assessment questions:**

- Why can the database path and authSource in a URI differ?
- Why must a URI with a percent-encoded password still be protected as a secret?
- When TLS is enabled without verifying certificates/hostnames, what risks remain?
- When should a custom role be used instead of granting readWrite across the entire database?
- Why does having read permission on orders in MongoDB still require tenant checks in the application?
- Why must credential rotation account for multiple instances and active connection pools?

A secure Spring Data MongoDB connection requires managing **connection target, secrets, TLS, and account permissions** together. When all four layers are verified and backed by rotation/revocation procedures, the application can use MongoTemplate or repositories reliably while limiting blast radius if misconfiguration or credential exposure occurs.

## 12. References

- [MongoDB – Connection String Formats](https://www.mongodb.com/docs/manual/reference/connection-string/): syntax for mongodb:// and mongodb+srv://.
- [MongoDB – Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/): authSource, TLS, and topology options.
- [MongoDB – Configure TLS/SSL](https://www.mongodb.com/docs/manual/tutorial/configure-ssl/): transport encryption and certificates.
- [MongoDB – Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/): the RBAC model.
- [MongoDB – User-Defined Roles](https://www.mongodb.com/docs/manual/core/security-user-defined-roles/): resources, actions, and custom roles.
- [MongoDB – db.createRole()](https://www.mongodb.com/docs/manual/reference/method/db.createRole/): creating roles.
- [MongoDB – db.createUser()](https://www.mongodb.com/docs/manual/reference/method/db.createUser/): creating accounts.
- [MongoDB Java Driver – TLS](https://www.mongodb.com/docs/drivers/java/sync/current/security/tls/): configuring TLS for the Java driver.
- [Spring Data MongoDB – Reference](https://docs.spring.io/spring-data/mongodb/reference/): accessing MongoDB with Spring Data.
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): managing configuration outside the application.
- [OWASP – Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): provisioning, protecting, and rotating secrets.
