# MongoDB Threat Model and Defense Layers

## 1. Why Is MongoDB Security Not Just About Setting a Password?

Suppose an e-commerce platform uses MongoDB to store orders, customer accounts, and shipping addresses. The system includes a Java API, admin staff, reporting tools, a backup system, and a multi-node MongoDB cluster.

If you only enable authentication and set a sufficiently long password, the following scenarios can still cause incidents:

- An attacker steals an environment variable containing the application's connection string.
- A service uses an account with the `root` role, so when exploited it can read and drop every collection.
- The connection between the application and the database does not properly verify TLS certificates.
- An endpoint allows users to pass an arbitrary BSON filter, leading to **NoSQL injection**.
- Backups are pushed to a publicly accessible storage bucket or lack immutable copies.
- The database has RBAC, but a legitimate employee exports customer data outside their job scope.
- A reporting job runs an extremely heavy aggregation that exhausts system resources.
- An accidental deletion or ransomware operation is replicated to secondaries; no recoverable backup remains.

That is why a **threat model** and **defense in depth** are necessary. A threat model answers “what needs protection, who can attack, through which paths, and what are the consequences?”. Defense in depth answers “if one layer fails, which next layer still limits the damage?”.

### 1.1. Lesson Objectives

After this lesson, you will be able to:

1. Diagram components and **trust boundaries** in a MongoDB system.
2. Identify assets, threat actors, attack surfaces, and security assumptions.
3. Analyze threats using **STRIDE** and prioritize risks.
4. Explain the roles of **network isolation, TLS, authentication, RBAC, encryption, auditing, backups, and monitoring**.
5. Defend against credential exposure, application account abuse, injection, backup leakage, data deletion, and denial of service.
6. Understand the differences between **Atlas** and **self-managed MongoDB** when implementing controls.
7. Design security checks, incident response scenarios, and safe-scope hands-on exercises.

**Scope limitation:** examples are for learning secure configuration and design, not instructions to run directly on a production cluster. Specific features may depend on **MongoDB version, deployment type, and service tier**.

## 2. Assets to Protect

Start from the assets, **not** from a list of MongoDB features.

| Asset | Examples | If Compromised |
|---|---|---|
| Customer data | Name, address, phone number | PII exposure, privacy violation |
| Business data | Orders, prices, transactions | Fraud, inaccurate reporting |
| Access identities | DB users, API keys, certificates | Impersonation of applications/administrators |
| Administrative privileges | Roles, user administration | Privilege escalation, loss of control |
| Encryption keys | KMS master key, data encryption key | Loss of decryption capability or data exposure |
| MongoDB infrastructure | Primary, secondary, mongos, config servers | Loss of availability/integrity |
| Metadata and indexes | Sharding metadata, schema, indexes | Incorrect queries or service disruption |
| Backups | Snapshots, dumps, PITR metadata | Unable to restore or stolen data |
| Audit/monitoring | Authentication events, admin actions | Loss of detection/investigation capability |
| Configuration and CI/CD pipelines | URIs, IaC, secret references | Unauthorized changes, secret leakage |

One object can belong to multiple categories. For example, the `users` collection contains both personal information and business authorization data. You must define the **data owner, sensitivity level, retention, and read permissions** for each type.

### 2.1. The CIA Triad

Three classic information security objectives:

- **Confidentiality:** unauthorized parties cannot read the data.
- **Integrity:** changes must be valid, and unauthorized modifications can be detected.
- **Availability:** the system continues serving within defined targets despite faults or incidents.

Examples:

```text
Customer address exposure -> Confidentiality
Unauthorized balance edit -> Integrity
Dropping orders collection -> Integrity + Availability
Query exhausting CPU       -> Availability
Losing decryption key      -> Availability + Confidentiality
```

### 2.2. Adding Accountability

In critical systems, you need to know **who did what, when, from where, and through which path**. Authentication, audit logs, application correlation IDs, and operational procedures support **accountability**.

Encryption alone does not provide accountability; auditing alone does not prevent data exposure; backups alone do not prevent injection. Controls must work together.

## 3. System Diagram and Trust Boundaries

An example architecture:

```text
                           INTERNET / USER
                                  |
                           [TLS HTTPS]
                                  |
                     +------------------------+
                     | WAF / API Gateway      |
                     | AuthN / Rate limiting  |
                     +------------------------+
                                  |
                 TRUST BOUNDARY A | (untrusted request)
                                  v
                     +------------------------+
                     | Java API Service       |
                     | Business authorization |
                     | Input validation       |
                     +------------------------+
                            |         |
                            |         +------------------+
                            |                            |
                       [TLS+mTLS?]                    Secrets/KMS
                            |                            |
                 TRUST BOUNDARY B                       |
                            v                            v
                 +--------------------+        +------------------+
                 | Private Network    |        | IAM / Key Store  |
                 | MongoDB endpoints  |        +------------------+
                 +--------------------+
                            |
           +----------------+----------------------+
           |                |                      |
       mongos/router      mongod nodes         Monitoring
           |                |                      |
           +-------> Shards/Replica Set <---------+
                            |
                   TRUST BOUNDARY C
                            |
                   Encrypted Backup Store
                   (separate permissions)
```

This is a **conceptual model**. For an unsharded replica set, there is typically no `mongos`. With Atlas, many components are managed by the provider, but that **does not turn the application's responsibilities into Atlas's responsibilities**.

### 3.1. What Is a Trust Boundary?

A **trust boundary** lies between two zones where one side **cannot automatically be trusted** just because the other side trusts it.

Typical boundaries:

1. **Internet → API:** every parameter from the client must be validated.
2. **API → MongoDB:** the app has credentials, but must not default to cluster-wide administrative privileges.
3. **Application → Secrets/KMS:** the application only receives the keys/secrets it needs.
4. **Primary ↔ Secondary:** nodes must also authenticate and encrypt internal connections.
5. **MongoDB → Backup storage:** backups need independent permissions, keys, and retention.
6. **Human operator → Admin interface:** administrator logins and emergency actions must be recorded.

### 3.2. Minimal Data Flow Diagram (DFD)

When building a threat model, document each flow:

```text
Flow: Java API -> MongoDB
Asset: order documents
Protocol: MongoDB wire protocol over TLS
Identity: orders_service
Permissions: read/write required collections
Network: private subnet
Trust boundary: application process -> DB tier
Log: connection/auth failures, audit policy
Data sensitivity: PII, order state
```

Do the same for monitoring, backup, ETL, admin, migration jobs, and CI/CD.

## 4. Identifying Threat Actors and Attack Surfaces

### 4.1. Actors to Consider

| Actor | Assumed Capability | Potential Goals |
|---|---|---|
| Unauthenticated Internet user | Sends requests to the API | Unauthorized read/write, DoS |
| Compromised user account | Holds a valid session | Read data outside their tenant |
| Compromised application | Holds service DB user privileges | Read/delete data within the user's scope |
| Legitimate insider | Accesses per role | Abuse privileges, export data |
| Misconfiguring operator | Holds administrative privileges | Expose ports, lose backups, delete data |
| Host/backup volume thief | Reads files/disks | Steal data or keys |
| Supply-chain attacker | Impacts images/dependencies/CI | Steal secrets, execute unauthorized code |

You do not need to assume every actor can do everything. A good threat model states clear **initial capabilities** and **realistic scope**.

### 4.2. MongoDB Attack Surface

- MongoDB connection ports (`mongod`, `mongos`).
- Application APIs that allow building filters, sorts, and aggregations.
- Database users and authentication mechanisms.
- Admin consoles, Atlas organizations/projects, and automation APIs.
- Internal replica set/sharded cluster connections.
- Secret stores, credentials in CI/CD, logs, or URIs.
- Snapshots, dumps, and backup object storage.
- Metrics/log exporters and database monitoring.
- Hosts storing data files and OS service accounts.
- Docker/Kubernetes orchestration and cloud networking.

Do not assume a database not directly exposed to the Internet is **immune**: the application can be exploited and become an indirect access path.

## 5. The STRIDE Method for MongoDB Systems

STRIDE is a widely used analysis framework:

| STRIDE | Question | MongoDB Example |
|---|---|---|
| **S — Spoofing** | Who can impersonate an identity? | Using leaked credentials to log in as `orders_service` |
| **T — Tampering** | Who can modify data/state? | Modifying an order `status` or role |
| **R — Repudiation** | Can actions be denied? | No audit trail when an operator drops a collection |
| **I — Information disclosure** | How can data leak? | Public endpoint, leaked backup, cross-tenant query |
| **D — Denial of service** | Can service be disrupted? | Heavy query/aggregation exhausting CPU/I/O |
| **E — Elevation of privilege** | Can higher privileges be obtained? | App uses the `root` role or admin secrets are stolen |

### 5.1. Applying STRIDE to a Specific Flow

Flow `Java API → MongoDB`:

**Spoofing:** if an attacker obtains the URI/password, they can impersonate the service.

**Tampering:** if the service account is allowed to update too many collections, an exploited endpoint can corrupt data.

**Repudiation:** if all microservices share the same DB user, audits cannot easily tell which service performed an action.

**Information disclosure:** an endpoint returns documents without filtering `tenantId`, or error logs print passwords.

**DoS:** an endpoint allows arbitrary `sort`/regex/aggregation, causing heavy queries.

**Elevation:** the service has unnecessary user administration privileges and can grant additional roles.

### 5.2. Every Risk Should Map to a Control

Example:

```text
Asset: orders
Threat: unauthorized status modification
Entry point: API endpoint /orders/{id}
Condition: IDOR (no tenant ownership check)
Impact: fraud and corrupted state

Defenses:
  - AuthN at API
  - Tenant/ownership AuthZ in every query
  - DB user has readWrite only within required scope
  - Schema/business invariants
  - Audit for sensitive operations
  - Recovery capability from backup/ledger
```

This is defense in depth: **no single layer** is responsible for everything.

## 6. Risk Prioritization

A threat model must move from a list of threats to actionable decisions.

### 6.1. Qualitative Matrix

| Likelihood | Low Impact | Medium Impact | High Impact |
|---|---|---|---|
| Low | Monitor | Consider mitigating | Mitigate |
| Medium | Consider | Mitigate | High priority |
| High | Mitigate | High priority | Urgent |

This is only an **illustrative matrix**. Severity must be based on real data: system exposure, data sensitivity, recoverability, attacker benefit, and incident evidence.

### 6.2. Example Risk Register

| ID | Risk | Impact | Mitigation | Control Evidence |
|---|---|---|---|---|
| R01 | Public MongoDB port | Data exposure/DoS | Private network, firewall | Security group review |
| R02 | App uses DB admin | Escalation, broad modify/drop | Least-privilege RBAC | Service roles |
| R03 | TLS without cert verification | MITM/server impersonation | Require TLS, CA/SAN validation | Connection test |
| R04 | Query operator injection | Out-of-scope read | Allowlist, typed parameters | Negative tests |
| R05 | Backups under production account | Ransomware deletes backups too | Isolation, immutability | Restore drill |
| R06 | Missing audit | Hard to investigate | Audit/events, central logs | Alerts/log retrieval |
| R07 | Encryption key alongside data | Plaintext exposure on host compromise | KMS/key separation | Key access policies |

Each item should have an **owner, deadline, status, residual risk**, and re-verification schedule.

## 7. Defense in Depth: The Protection Layers

```text
                SENSITIVE DATA
                      |
           +---------------------+
           | Application AuthZ   |
           | schema + validation |
           +---------------------+
                      |
           +---------------------+
           | MongoDB RBAC        |
           | least privilege     |
           +---------------------+
                      |
           +---------------------+
           | Identity + Secrets  |
           | SCRAM / X.509 / IAM |
           +---------------------+
                      |
           +---------------------+
           | TLS + cert checks   |
           +---------------------+
                      |
           +---------------------+
           | Private network     |
           | firewall/endpoint   |
           +---------------------+
                      |
           +---------------------+
           | OS/storage/KMS      |
           | backup/recovery     |
           +---------------------+
                      |
           +---------------------+
           | Audit/monitoring    |
           | incident response   |
           +---------------------+
```

This diagram is **not a rigid chain of dependent layers**. Client-side encryption can still protect data even when a database admin has permission to read files. Backups and auditing also operate across layers rather than only acting as an “outer ring”.

**Principle:** each control addresses a specific set of risks. You must know **what it does not protect against** to avoid a false sense of security.

## 8. Network Layer: Restricting Who Can Reach MongoDB

### 8.1. Place MongoDB in a Trusted Network

Applications typically route through:

```text
Internet -> Load Balancer -> API -> Private MongoDB subnet
```

The database should not have ports open directly to the Internet unless there is a special requirement and commensurate controls.

Measures:

- Dedicated VPC/VNet/subnet.
- Firewalls/security groups allowing only required sources.
- Private endpoint/private connectivity for managed services.
- Restrict egress from DB hosts.
- Bastion/zero-trust access for operators.
- Do not place `mongod`/`mongos` behind a public load balancer shared with web traffic.

### 8.2. `bindIp` Is a Layer, Not a Firewall

Example configuration for a **standalone lab on a local machine only**:

```yaml
net:
  port: 27017
  bindIp: 127.0.0.1
```

`127.0.0.1` only accepts connections from the local host. For replica sets or sharded clusters, nodes need to communicate over permitted private addresses; **do not copy this localhost configuration to all nodes and expect replication to work**.

Do not use:

```yaml
net:
  bindIp: 0.0.0.0
```

as a quick fix for production connection issues. It requires reviewing firewall rules, TLS, authorization, and network scope. `bindIp` does not replace authentication or firewalls.

### 8.3. Zero Trust on Every Connection

An IP inside a private subnet **does not automatically grant permission to read data**. Even services on the same network must authenticate with credentials/certificates and be granted appropriate RBAC roles.

### 8.4. Other Ports Also Need Controls

A threat model does not just look at application ports. Check:

- MongoDB wire protocol endpoints.
- Metrics/exporter ports.
- Monitoring agents.
- Admin automation/APIs.
- SSH/remote management.
- Storage snapshot interfaces.

An unauthenticated exporter can leak database names, topology, or sensitive metrics even when the DB port is closed.

## 9. TLS: Protecting Data in Transit

### 9.1. What Does TLS Protect Against?

- Eavesdropping on data in transit.
- Packet tampering during communication.
- Server impersonation when the client properly verifies certificates and hostnames.

TLS should be applied to **application ↔ MongoDB** and **MongoDB components ↔ each other** according to the architecture.

### 9.2. Illustrative Configuration for Standalone with TLS

```yaml
# mongod.conf - illustrative example, do not use verbatim in production.
net:
  port: 27017
  bindIp: 127.0.0.1
  tls:
    mode: requireTLS
    certificateKeyFile: /secure/path/server.pem
    CAFile: /secure/path/ca.pem

security:
  authorization: enabled
```

Requirements:

- Certificate/private key files have minimal ownership and read permissions.
- Valid certificate signed by a CA trusted by the client.
- Hostname/SAN matches the DNS name the client actually connects to.
- An admin user and proper bootstrapping procedure are in place.
- For replica sets/sharded clusters, **internal authentication** and inter-node TLS are also required.

Do not copy the configuration above to a new environment without setting up certificates, users, and internal cluster auth.

### 9.3. Connecting with mongosh Using TLS Verification

```bash
mongosh "mongodb://db.internal.example:27017/shop?tls=true&authSource=admin" --tlsCAFile /secure/path/ca.pem --username orders_service --password
```

`--password` is passed without a value in the example to avoid writing the password directly into shell history. Hostname/certificate and CA must match the environment.

### 9.4. Do Not Disable Certificate Verification to Fix Errors

Options such as:

```text
tlsAllowInvalidCertificates
tlsAllowInvalidHostnames
tlsInsecure
```

weaken TLS verification. Never use them in production just to “make it connect” after a hostname or CA error.

Fix the **DNS/SAN/chain/certificate trust** instead of bypassing server identity checks.

### 9.5. TLS Does Not Protect After Credentials Are Compromised

If an attacker obtains valid credentials and connects over TLS, the server still sees an encrypted connection **that may belong to the attacker**. Therefore, TLS must be paired with authentication, RBAC, network isolation, and monitoring.

## 10. Authentication: Who Is Connecting?

### 10.1. Authentication vs. Authorization

**Authentication (AuthN)**: verifies identity.

**Authorization (AuthZ)**: decides what that identity is allowed to do.

```text
SCRAM/X.509/...  ->  "This is orders_service"
RBAC             ->  "orders_service is allowed to find/write orders
                      within its defined scope"
```

A user who logs in successfully **does not** automatically have permission to read every collection.

### 10.2. SCRAM

MongoDB Community supports SCRAM, including **SCRAM-SHA-256**. In self-managed deployments, this is the common username/password authentication mechanism.

The system needs:

- Strong/unique passwords per service.
- No shared credentials across services, developers, and automation.
- A secret manager or secure provisioning solution.
- Rotation and revocation procedures.
- TLS to protect communication and authenticate the server.

### 10.3. X.509

X.509 certificate-based authentication can be useful with PKI infrastructure. It requires managing the certificate/private key lifecycle, identity verification, identity mapping, and expiration.

**TLS certificates and user identities are not always the same concept.** A system can use TLS to authenticate the server while the client still uses SCRAM to log in. If you choose X.509 client authentication, you must design client certificate requirements and role mapping separately.

### 10.4. LDAP/Kerberos/OIDC

Certain enterprise identity integration mechanisms depend on MongoDB Enterprise/Atlas, version, and specific configuration.

Do not claim a Community deployment can enable every mechanism just by adding one config line. Verify the features, prerequisites, and token/certificate lifecycle for the edition in use.

### 10.5. Internal Authentication

In a replica set or sharded cluster, MongoDB members must authenticate with one another. Options like keyfile or X.509 must be configured properly for your version.

**If you only protect client connections while skipping member-to-member authentication/TLS, the internal trust boundary remains weak.**

## 11. RBAC and the Principle of Least Privilege

MongoDB uses **Role-Based Access Control (RBAC)** to decide which privileges an identity has on which resources.

### 11.1. Never Grant `root` to an Application

An application only needs:

```text
orders_service:
  read/write shop.orders
  read shop.products
  no user/role administration
  no drop database
  no config/sharding edits
```

The `root` account has very broad administrative capabilities. If an application endpoint is exploited, the attacker can use the process's privileges; **every excess privilege increases the blast radius**.

### 11.2. Built-in Roles and Custom Roles

Some built-in roles:

- `read`: read privileges within the granted scope.
- `readWrite`: read/write privileges within the granted scope.
- `dbAdmin`: database administration within the role's scope, not read-only.
- `userAdmin`: user/role management within the relevant scope; carries escalation risk if misassigned.
- `root`: very broad administrative privileges.

**Built-in `readWrite` across an entire database can be too broad** if a service should only write to one collection. When finer-grained permissions are needed, use **custom roles with explicitly specified privileges**.

### 11.3. Example: Creating a Lab User

Only run on a **lab MongoDB instance you administer**, after setting up user creation permissions and secure bootstrapping:

```javascript
const adminDb = db.getSiblingDB("admin");

adminDb.createUser({
  user: "orders_service_lab",
  pwd: passwordPrompt(),
  roles: [
    { role: "readWrite", db: "shop_lab" }
  ]
});
```

Here the user is defined in the **`admin` database**; the `readWrite` role applies to `shop_lab`. Connections use `authSource=admin` accordingly.

`passwordPrompt()` avoids writing plaintext passwords into source files or shell history.

**Do not run user creation commands on production** as an exercise without authorization and an approved change process.

### 11.4. Limits to Remember

`readWrite` grants read/write access within the selected database; it **does not replace** tenant checks in the application when multiple tenants share a collection.

Database authorization must be combined as:

```text
API AuthN -> API AuthZ -> Tenant-aware query -> MongoDB RBAC
```

## 12. Multi-Tenant Business Authorization

### 12.1. IDOR / Broken Object Authorization Risk

Suppose the endpoint:

```text
GET /orders/O1001
```

authenticates user Alice, but the code only queries:

```javascript
db.orders.findOne({ _id: "O1001" });
```

If Alice guesses Bob's order ID, the API may return unauthorized data even though the MongoDB connection uses TLS and the DB user has valid RBAC.

### 12.2. Include Tenant/Ownership in Query Filters

Example:

```javascript
const tenantId = authenticatedContext.tenantId;
const orderId = validatedOrderId;

db.orders.findOne({
  _id: orderId,
  tenantId: tenantId
});
```

**Do not** take `tenantId` from a user-editable query parameter and trust it as the sole source of truth.

### 12.3. Updates Must Also Enforce Permissions

```javascript
db.orders.updateOne(
  {
    _id: validatedOrderId,
    tenantId: authenticatedContext.tenantId,
    status: "CREATED"
  },
  {
    $set: { status: "CANCELLED" }
  }
);
```

The filter both enforces ownership and guards a simple state transition. However, complex business rules may require transactions and additional validation; do not treat a single filter as the entire authorization system.

### 12.4. When Multiple Tenants Share a Database User

Standard MongoDB RBAC grants permissions at the database/collection/action level; it **does not automatically enforce row-level security by `tenantId`** across queries. You need API/business authorization, tenant separation architecture, or commensurate data mechanisms.

## 13. NoSQL Injection: Never Accept Client-Controlled Filters

### 13.1. Different from SQL Injection, Same Root Cause

NoSQL injection occurs when untrusted input is injected into **query/operator structure** rather than solely **data values**.

Contraindicated example:

```javascript
// Wrong: client sends a filter object directly, and the server uses it as-is.
const clientFilter = req.body.filter;
const user = db.users.findOne(clientFilter);
```

If `clientFilter` contains operators such as `$ne`, `$regex`, or other conditions, the query semantics can diverge completely from business requirements.

### 13.2. Build Fixed-Schema Filters

```javascript
function validateUsername(value) {
  if (typeof value !== "string" ||
      value.length < 1 ||
      value.length > 100) {
    throw new Error("Invalid username");
  }
  return value;
}

const username = validateUsername(req.body.username);
const user = db.users.findOne({ username: username });
```

The user only controls the **username String**, never operators or field names.

### 13.3. Disable Arbitrary Server-Side JavaScript Execution

MongoDB includes features/expressions that can execute server-side JavaScript such as `$where`, `$function`, and `$accumulator` in applicable contexts/versions.

If the application does not need these capabilities, MongoDB's security checklist documentation recommends considering **disabling server-side scripting** on self-managed deployments via appropriate configuration, while removing business dependencies on them beforehand.

Never allow users to submit these expressions to an API as code fragments and execute them as a trusted pipeline.

### 13.4. Typed APIs and Allowlists

Example product search API:

```javascript
const allowedSorts = new Map([
  ["priceAsc", { price: 1, _id: 1 }],
  ["priceDesc", { price: -1, _id: 1 }],
  ["newest", { createdAt: -1, _id: 1 }]
]);

const sort = allowedSorts.get(req.query.sort) ||
             allowedSorts.get("newest");

const limit = Math.min(
  Math.max(Number(req.query.limit) || 20, 1),
  100
);

db.products.find({
  active: true,
  tenantId: authenticatedContext.tenantId
}).sort(sort).limit(limit);
```

Do not pass `req.query.sort` directly into `sort()` if it could contain disallowed fields or operators. Also explicitly validate integer type, finiteness, and invalid inputs for `limit` in production code; this snippet only illustrates an allowlist and upper bound.

## 14. Java Driver: Avoiding Arbitrary Dynamic Filters

### 14.1. Parameterized Queries with Builders

```java
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;

import org.bson.conversions.Bson;

String tenantId = authenticatedTenantId;
String orderId = validatedOrderId;

Bson filter = and(
    eq("_id", orderId),
    eq("tenantId", tenantId)
);

Document order = orders.find(filter).first();
```

Builder APIs express **fixed fields/operators**, while input only supplies values.

### 14.2. Dangerous Approach

```java
// Contraindicated if rawJson is untrusted input.
Bson filter = Document.parse(rawJsonFromClient);
orders.find(filter);
```

The issue is not whether JSON parses cleanly; accepting an entire user-controlled query document can allow injecting operators, unauthorized fields, or expensive pipelines.

### 14.3. Do Not Log MongoDB URIs Containing Secrets

Logging example:

```java
// Not recommended:
logger.info("Mongo URI: {}", mongoUriWithPassword);

// Recommended:
logger.info("MongoDB connection initialized for service {}", serviceName);
```

Applications need redaction policies for exceptions, connection strings, authentication failures, and request logs.

## 15. Schema Validation: Reduces Bad Data, Not a Substitute for Permissions

MongoDB supports **collection validation** via `$jsonSchema`.

Example lab orders collection:

```javascript
db.getSiblingDB("security_lab_327").createCollection(
  "orders327",
  {
    validator: {
      $jsonSchema: {
        bsonType: "object",
        required: ["tenantId", "status", "total"],
        properties: {
          tenantId: {
            bsonType: "string",
            minLength: 1
          },
          status: {
            enum: ["CREATED", "PAID", "CANCELLED"]
          },
          total: {
            bsonType: ["int", "long", "decimal"],
            minimum: 0
          }
        }
      }
    },
    validationLevel: "strict",
    validationAction: "error"
  }
);
```

Collection validation can block certain cases of wrong data types or invalid values, but:

- It does not determine which user is authorized to modify which order.
- It does not replace business invariant checks spanning multiple documents.
- It does not guarantee all legacy documents are already valid.
- There may be bypass permissions/paths depending on roles or settings, which must be controlled.

**Schema validation protects structural data quality/integrity; RBAC and application AuthZ protect access permissions.**

## 16. Encryption at Rest and Client-Side Encryption

Three layers that are often confused:

| Layer | Where Is Data Protected? | Helps Protect Against | Does Not Alone Protect Against |
|---|---|---|---|
| **TLS** | In transit | Eavesdropping/MITM when certs are verified | Leaked valid credentials, authorized users reading data |
| **Encryption at rest** | Files/volumes/backups encrypted when stored | Lost disks, unauthorized physical file reads | DB users reading plaintext through a running server |
| **Client-side field encryption** | Fields encrypted **before sending to server** | Certain DB admin/host-without-key scenarios | Compromised app holding keys and plaintext |

### 16.1. Encryption at Rest

MongoDB supports storage engine encryption in applicable editions/configurations; disk/filesystem encryption or managed encryption mechanisms can also be used.

Encryption at rest reduces risks such as:

- Lost or stolen disks.
- Unauthorized access to snapshots/data files without keys.
- Physical storage removal from a host.

However, when `mongod` is running and an authorized user queries it, data can be decrypted by the server. **Encryption at rest does not replace RBAC.**

### 16.2. Client-Side Field Level Encryption (CSFLE)

CSFLE lets the client encrypt specific fields before sending them to MongoDB:

```text
Trusted application:
  plaintext PII
     |
     v
  Encrypt with DEK
     |
     v
MongoDB stores ciphertext
     |
     v
Application with appropriate key decrypts
```

Data example:

```javascript
{
  _id: "C001",
  name: "Customer A",
  personalId: /* encrypted BSON value */
}
```

The server can store the encrypted field without having the client decryption key. MongoDB read privileges on the collection **do not mean** the reader can see the plaintext of that field.

### 16.3. Queryable Encryption

Queryable Encryption enables certain queries on client-encrypted fields under supported modes and data types.

Do not assume that:

- Every encrypted field can be queried with every operator.
- Every BSON type and aggregation stage is supported.
- Search indexes, regex, sorting, joins, and ranges work just like plaintext.
- Simply enabling Queryable Encryption eliminates all risk.

**Query capabilities, type/operator limits, and performance depend on the MongoDB version**, so consult exact documentation and benchmark your workload before deploying.

### 16.4. Client-Side Encryption Cannot Save a Compromised Client

If an attacker controls an application process that has access to plaintext and the KMS, the attacker can:

- Call decryption APIs inside the process.
- Read data before it is encrypted.
- Exfiltrate data while serving legitimate requests.

Thus, CSFLE/Queryable Encryption is an **additional protective boundary**, not a replacement for application hardening and KMS access management.

## 17. Key Management: Separating Data from Decryption Capability

### 17.1. Key Hierarchy

A typical model includes:

- **Data Encryption Key (DEK):** used to encrypt data/fields.
- **Customer Master Key (CMK):** protects/wraps DEKs.
- **Key vault:** stores metadata and protected DEKs.
- **KMS:** provides management/control over master keys.

```text
Application
   |
   +--> KMS -> grants permission to decrypt/unwrap DEK
   |
   +--> MongoDB Key Vault -> encrypted DEK metadata
   |
   +--> MongoDB business collection -> encrypted fields
```

### 17.2. Principles

1. Never hardcode keys in source code or images.
2. Separate key management privileges from database read privileges.
3. Restrict which services are allowed to unwrap/decrypt.
4. Audit KMS access and rotate according to policy.
5. Maintain a key recovery plan; losing keys can mean **losing the ability to decrypt data**.
6. Test backup restores including key vault and KMS availability.

### 17.3. Encrypted Backups Require Independent Key Management

If backups are encrypted but the key is lost, you can still “restore files” without being able to use the data. Recovery objectives must cover **decryption capability and correctness verification**, not just file counts.

## 18. Secrets Management and Credential Rotation

### 18.1. Where Can Secrets Leak?

- Repositories and commit history.
- CI logs.
- Shared `.env` files.
- Container images.
- Process arguments/shell history.
- Crash dumps and application logs.
- Monitoring dashboards.
- Configuration backup outputs.

### 18.2. Useful Measures

- An appropriate secret manager/KMS/vault.
- Scoping secret read permissions by service identity.
- Separate secrets for development/staging/production.
- Never share one database admin password across all apps.
- Detect exposed secrets with scanning and have revoke/rotate procedures.
- Avoid printing full URIs in logs.

### 18.3. Rotation Is More Than Changing a String in a File

Process:

```text
1. Create a new least-privilege credential.
2. Update the secret store/application configuration.
3. Roll out services using the new credential.
4. Verify connectivity and business flows.
5. Revoke the old credential.
6. Check logs, audits, and any remaining consumers.
```

Depending on the user/scenario, tailored credential rotation approaches may be needed to avoid downtime. Do not delete the old credential before cutover is complete unless you have a rollback plan.

## 19. Host and Runtime Hardening

Even when MongoDB has authentication and TLS, a compromised host can expose data files, logs, keyfiles, or database control.

### 19.1. OS Principles

- Run MongoDB under a **dedicated OS user**, not as root unless required.
- Restrict permissions on data, config, certificate, and backup directories.
- Apply supported OS/MongoDB patches.
- Perform remote administration through access-controlled channels.
- Place services in appropriate network segments.
- Control installed packages and agents.
- Maintain configuration baselines and detect drift.

### 19.2. Containers/Kubernetes

When using containers:

- Never bake passwords into images.
- Avoid privileged containers and unnecessary host filesystem access.
- Protect PersistentVolumes/snapshots.
- Use network policies and secrets RBAC.
- Restrict Kubernetes service accounts.
- Monitor StatefulSet/Operator changes.
- Ensure backups do not depend on a single node that could disappear.

**Default Kubernetes Secrets do not replace a KMS or backup protection policy**; understand how they are stored, encrypted at rest, and authorized on the cluster.

### 19.3. Antivirus/EDR

Per MongoDB guidance, scanners can impact I/O when scanning data/log directories directly or quarantine DB files. Configure **appropriate exclusions** alongside other endpoint protections rather than disabling all EDR simply because MongoDB is disk-intensive.

## 20. Denial of Service: Protecting Resources

Not every threat is data theft. A heavy query can prevent legitimate users from accessing the service.

### 20.1. Sources of DoS

- Uncontrolled regexes without appropriate indexes.
- Multi-stage aggregations and large `$lookup` joins.
- Unindexed sorts consuming excessive RAM/disk.
- Unbounded queries with no result limit.
- Connection pools opening too many connections.
- Long-running transactions holding resources.
- Uncontrolled bulk writes.
- Backups or index builds running during peak hours.

### 20.2. Mitigation Layers

**At the API:** authentication, quotas/rate limiting, request size limits, search field allowlists, pagination.

**At the driver:** appropriate pool sizes and timeouts, bounded retries.

**At the query:** indexes, projections, `limit`, contextual `maxTimeMS`, controlled query shapes.

**At the infrastructure:** CPU/memory/disk I/O capacity, alerts, appropriate autoscaling, resource isolation.

**At operations:** backup/index maintenance windows, monitoring, and runbooks.

### 20.3. `maxTimeMS` Does Not Replace Permission Limits

Example:

```javascript
db.orders.find({ status: "PAID" })
  .limit(100)
  .maxTimeMS(2000);
```

`maxTimeMS` asks MongoDB to bound execution time under supported conditions, but it does not guarantee every operation aborts at exactly 2,000 ms or solve memory/connection exhaustion.

Do not use `maxTimeMS` to compensate for letting clients run arbitrary pipelines.

### 20.4. Availability Does Not Rely on Replica Sets Alone

A replica set tolerates some node failures, but it does not protect against:

- Valid but mistaken human delete commands.
- Compromised admin credentials.
- Heavy queries propagating across nodes.
- Region-wide outages.
- Late-discovered corruption.

You also need backups/restores, quotas, and other operational policies.

## 21. Replica Sets and Sharded Clusters Add Trust Boundaries

### 21.1. Replica Set

Members replicate data and participate in elections. Required:

- Internal authentication.
- Inter-member TLS within deployment scope.
- Secure lifecycle management for certificates/keyfiles.
- Network rules allowing only required members.
- Monitoring of elections, lag, and configuration changes.

```text
Application
    |
   TLS/AuthN
    |
  Primary  ---- replication ---> Secondary A
    |                              |
    +---- replication ----------> Secondary B
```

A secondary still holds a copy of sensitive data. **Do not encrypt or restrict only the primary.**

### 21.2. Sharded Cluster

A sharded cluster adds:

```text
App -> mongos -> shard replica sets
          |
          +-> config server replica set
```

Surfaces to protect include:

- `mongos` instances accessed by applications.
- Shard endpoints and internal auth.
- Config servers and sharding metadata.
- Admin/automation actions for the balancer, zones, and resharding.
- Network connectivity between components.

Do not let application users **connect directly to shard members** just to “skip a routing hop” if doing so violates the access model.

### 21.3. Metadata Is Also a Sensitive Asset

Sharding/cluster metadata can reveal topology, namespaces, and tenant distribution. Corrupting metadata can break data routing.

Never manually edit `config.*` via CRUD outside MongoDB-supported procedures.

## 22. Atlas vs. Self-Managed: Same Goal, Different Division of Work

### 22.1. When Using Atlas

Certain infrastructure operational components are managed by Atlas depending on the product/service tier, but the engineering team remains responsible for:

- Designing application authentication/authorization.
- Granting database user privileges and managing Atlas project/organization access.
- Protecting credentials/API keys.
- Configuring IP access lists/private connectivity.
- Selecting encryption/KMS when required by the use case.
- Enabling auditing/monitoring according to tier capabilities.
- Managing data, retention, schemas, indexes, and backup/restore policies.

Never say “Atlas is secure out of the box so the app doesn't need tenant checks”.

### 22.2. When Self-Managed

The operations team must also handle:

- Configuring `mongod`/`mongos`, user auth, and internal auth.
- TLS certs/keyfiles.
- OS patching and network/firewall rules.
- Storage encryption and disk permissions.
- Backup orchestration and restore testing.
- Monitoring/logging/auditing for the edition in use.
- Upgrades and CVE remediation.

### 22.3. Feature Parity Is Not Absolute

Examples:

- LDAP/Kerberos/OIDC mechanisms may depend on edition.
- Server-side auditing on self-managed deployments has different support between Community and Enterprise.
- Encryption at rest uses different engines/KMS/managed capabilities.
- Some Atlas management/alerting features depend on tier.

**Do not copy an Enterprise configuration to Community and assume it is supported.** Check the documentation for your exact version and edition.

## 23. Audit Logging: Knowing Who Did What and When

### 23.1. What Audits Must Answer

- Which identity logged in?
- From which host/IP?
- Were users/roles modified?
- Were there unusual administrative operations?
- Was sensitive data accessed outside permitted hours?
- Who performed restores, drops, or config changes?

### 23.2. Information Sources

- Authentication/connection events.
- MongoDB server logs.
- Auditing facility (if supported by the deployment).
- Atlas activity/project audit logs as configured.
- Application access logs/correlation IDs.
- KMS access events.
- Cloud network/storage logs.

### 23.3. More Than Just “Turning On Logs”

A reliable logging system requires:

1. Time synchronization across components.
2. Centralized collection and restricted modification permissions.
3. Retention suited for investigation/compliance.
4. Redaction of passwords, tokens, PII, and queries containing sensitive data.
5. Correlation IDs wherever possible.
6. Alerts for noteworthy events.
7. Verification that the logging pipeline stays healthy.

### 23.4. Auditing Does Not Block Attacks by Itself

If an attacker reads 50,000 documents using valid credentials, auditing helps detect it **during or after** the event, but it is not a mechanism that caps document reads. You need RBAC, tenant auth, rate limiting, anomaly detection, and egress controls.

## 24. Monitoring and Alerting

| Signal | Suggested Risk | Investigation Action |
|---|---|---|
| Many authentication failures | Credential guessing/misconfiguration | Check IP/user, auth logs |
| Unusual admin login | Credential compromise | Verify identity, timestamp, MFA |
| Spike in read volume/egress | Exfiltration or new report | Check query patterns, app releases |
| Unusual drop/rename | Tampering/ransomware | Audit, roles, change window |
| Unexpected user/role creation | Privilege escalation | Review change logs, revoke after verification |
| CPU/I/O spike, slow queries | DoS/load regression | Explain/query shape/indexes |
| Disk nearly full | Availability risk | Capacity/retention/indexes |
| Replication lag/elections | Availability | Check topology, network |
| Backup failure | Unable to recover | Run retry/alert and restore test |
| Secret scanned in repo | Credential exposure | Revoke/rotate, investigate access |

Do not conclude **every login failure is an attack**: a deployment with a misconfigured new password can also generate thousands of errors. Alerts need context, thresholds, and triage.

### 24.1. Combine Security Metrics and Performance Metrics

Example read traffic spike:

```text
T1: new report released
T2: read throughput increases 8x
T3: egress increases
```

This could be legitimate demand or exfiltration. Cross-reference the change calendar, service identity, query shapes, and business intent rather than blindly blocking all traffic without investigation.

## 25. Backup and Recovery: The Survival Layer

### 25.1. Replication Is Not Backup

If an admin accidentally runs:

```javascript
db.orders.deleteMany({ status: "PAID" });
```

on production, the delete **is replicated** to secondaries because it is a valid operation. A replica set does not automatically keep a “pre-delete” copy to roll back per business needs.

**Do not run the example command above in production**; it only illustrates propagation of valid operations.

### 25.2. Backups Must Separate Blast Radius

A ransomware-resilient design may include:

- Backup credentials **separate** from production admin accounts.
- Object storage/backup service with isolated permissions.
- Backup immutability or retention lock where supported.
- Encrypted backups and protected keys.
- Backup schedules and point-in-time recovery aligned with requirements.
- Periodic restore testing in an isolated environment.
- Tracking backup success, age, and restore duration.

### 25.3. RPO and RTO

**RPO — Recovery Point Objective:** maximum acceptable data loss upon recovery.

**RTO — Recovery Time Objective:** maximum acceptable time to restore service.

Example:

```text
RPO = 15 minutes
RTO = 2 hours
```

This means the architecture must be able to recover within those targets **under tested conditions**. Do not treat these as met SLAs merely because daily snapshots exist.

### 25.4. Restore Drills Must Be Real

A restore drill should verify:

1. Backups are accessible using recovery identities.
2. Required keys are available.
3. Data can be decrypted and read.
4. Indexes/constraints/sharding metadata are restored per the backup method.
5. Applications connect and verify critical data.
6. Actual restore duration meets the target RTO.
7. Completion logs/evidence and accountable owners are recorded.

## 26. Insider Incidents and Administrative Privileges

### 26.1. Why Are Privileged Users Still a Threat Actor?

They can:

- Export data beyond their assigned scope.
- Accidentally drop a collection.
- Grant overly broad permissions.
- Expose backups or connection strings.
- Accidentally disable auditing/monitoring.

Threat modeling does not mean suspecting every employee; it is how you design **processes and tooling that limit the impact of mistakes and risks**.

### 26.2. Separation of Duties

Example:

```text
App developer:
  Can deploy services, does not have production DB root.

DB operator:
  Can administer MongoDB, cannot read client-side encryption keys.

Security officer:
  Can view audits, cannot directly modify order data.

Backup operator:
  Can test/restore within scope,
  cannot delete all backup copies.
```

### 26.3. Break-Glass Access

Emergencies requiring elevated privileges can use **break-glass** accounts:

- Stored and issued through a controlled process.
- MFA at the admin/identity provider layer where supported.
- Time- and privilege-bounded.
- Strictly audited and reviewed post-incident.
- Credentials rotated as needed.

Never use break-glass accounts as daily application accounts.

## 27. DevSecOps and the Supply Chain

### 27.1. Protecting from Code to Runtime

```text
Source -> CI -> Artifact -> Deploy -> Application -> MongoDB
   |       |       |          |           |         |
 secret  SBOM    sign      runtime     RBAC/TLS   audit
 scan    deps    image     policies    validation  backup
```

Specific mechanisms depend on the organization, but key questions include:

- Who can modify MongoDB connection settings?
- Can pipelines read production secrets?
- Are dependency vulnerabilities detected?
- Do images have provenance/signing?
- Is there a rollback mechanism?
- Are schema/index/privilege migrations reviewed?

### 27.2. Do Not Put Credentials in Test Files

Contraindicated URI example:

```text
mongodb://admin:SuperSecretPassword@db.internal:27017/admin
```

Never commit such a URI even in a private repository. When using secret URIs, configure them via a suitable secret manager/identity and log **redacted URIs**.

### 27.3. Leaked Secrets: Deleting from Git Is Not Enough

If a password was committed, deleting it in a newer commit **does not guarantee** the secret is gone from clones, history, or logs. You must **rotate/revoke** the credential and check for unauthorized usage.

## 28. Lab: Visualizing the Protection Layers

This lab uses only a **personal MongoDB instance or authorized environment**. Never test vulnerabilities on systems you are not authorized to administer.

### 28.1. Create a Database and Simple Data

```javascript
const lab = db.getSiblingDB("security_lab_327");
const orders = lab.ordersLab327;

// Only insert into a new/empty collection.
if (orders.countDocuments({}) !== 0) {
  throw new Error("Collection already contains data; choose a new lab");
}

orders.insertMany([
  { _id:"O1", tenantId:"T01", status:"CREATED", total:100000 },
  { _id:"O2", tenantId:"T02", status:"PAID", total:250000 },
  { _id:"O3", tenantId:"T01", status:"PAID", total:500000 }
]);
```

### 28.2. Test Tenant-Aware Query Logic

```javascript
const authorizedTenant = "T01";

orders.find({
  tenantId: authorizedTenant
}, {
  _id: 1,
  tenantId: 1,
  status: 1
});
```

Application T01 should not receive O2 because O2 belongs to T02. This check illustrates **business authorization**; it does not prove the MongoDB server automatically enforces row-level policies.

### 28.3. Inspect Roles in the Lab

If the user has appropriate privileges:

```javascript
db.getSiblingDB("admin").runCommand({
  usersInfo: "orders_service_lab",
  showPrivileges: true
});
```

Not every deployment or user has permission to view this information. Never use production admin privileges to inspect other users outside an approved scope.

### 28.4. Check Indexes to Mitigate Query DoS

```javascript
orders.createIndex({ tenantId: 1, status: 1 });

orders.find({
  tenantId: "T01",
  status: "PAID"
}).explain("executionStats");
```

Indexes are not an authorization mechanism, but they reduce the cost of frequent queries. With only a few documents, explain output does not represent production performance.

### 28.5. Technical Verification Exercises

In an authorized environment, you can verify:

- Are connections without valid credentials rejected?
- Is a readonly role denied write operations?
- Does service A's user have privileges on service B's database?
- Does TLS verify CA/hostname properly?
- Can backups be restored in an isolated environment?
- Do old credentials become invalid after rotation?

You do not need to launch real attacks to verify most of these fundamental security requirements.

## 29. Threat Modeling Workshop: Execution Steps

### Step 1 — Define Scope

Example:

```text
Application: Order Management
MongoDB: 3-node replica set
Environment: Production (design model, no live actions)
Integrations: API, analytics, backup, admin
Data sensitivity: PII + order state
```

### Step 2 — List Assets

Phone numbers, addresses, orders, credentials, backups, logs, encryption keys.

### Step 3 — Draw Flows and Trust Boundaries

User → API → MongoDB; Admin → management plane; MongoDB → backup; MongoDB → monitoring.

### Step 4 — State Assumptions

Example:

- MongoDB is not publicly exposed.
- TLS and certificate verification are enabled.
- DB users only hold required roles.
- Backend verifies tenant ownership.
- Backup accounts are separated from production admins.

Flag which assumptions are **unverified**. A threat model must not treat an assumption as fact just because it is drawn on a diagram.

### Step 5 — Apply STRIDE at Every Boundary

Ask the six questions:

```text
Spoof identity?
Tamper with data?
Repudiate actions?
Disclose information?
Deny service?
Elevate privilege?
```

### Step 6 — Assess Risk

Impact, likelihood, scope, time to detect, recoverability, and regulatory requirements.

### Step 7 — Map Controls

Network, TLS, AuthN, AuthZ, app validation, encryption, backups, monitoring, and response.

### Step 8 — Verify

Collect configuration evidence, privilege tests, restore drills, log alerts, and secret scanning.

### Step 9 — Assign Owners and Deadlines

An item without an owner and completion criteria remains an unhandled risk.

### Step 10 — Update When the System Changes

Every change to topology, connected services, sensitive data, roles, KMS, or backups can open new attack surfaces.

## 30. Incident Scenario 1: Exposed Application Credential

### 30.1. Scenario

An `orders_service` token/URI appears in a CI log. The account has `readWrite` on the `shop` database.

### 30.2. What Could Happen?

If an attacker can reach the MongoDB network, they can read/write within the **role's scope**. If the service had `root`, the blast radius is far worse.

### 30.3. Layers That Limit Damage

- Private network: blocks direct access from unauthorized sources.
- TLS: protects transit, but does not block someone holding valid credentials.
- RBAC: limits privilege scope.
- Audit: detects unusual identity/IP/query activity.
- Backup: supports recovering modified/deleted data.
- Secrets rotation: invalidates the exposed credential.

### 30.4. Controlled Response Procedure

1. Determine the scope of the secret and affected systems.
2. Restrict suspicious privileges/sessions per incident policy.
3. Issue new credentials and migrate the service.
4. Revoke/rotate the exposed credential.
5. Review audits/logs to assess unauthorized access.
6. Reconcile data integrity and restore if needed.
7. Fix the secret leak source in CI/logs/repos.
8. Conduct a post-mortem and add preventive controls.

**Simply deleting the log line does not mean the incident is resolved.**

## 31. Incident Scenario 2: Dynamic Query Exposes Tenant Data

### 31.1. Scenario

The API receives:

```json
{
  "filter": {
    "tenantId": "T01"
  }
}
```

and passes `filter` verbatim to MongoDB.

### 31.2. Problem

The client can alter the filter structure. If the backend treats client-constructed filters as trusted expressions, cross-tenant access can occur even when the database user has legitimate privileges.

### 31.3. Proper Design

The backend extracts `tenantId` from the authentication context, validates business parameters, builds a fixed filter itself, and only allows predefined fields/sorts.

```javascript
const filter = {
  tenantId: authenticatedContext.tenantId,
  status: validatedStatus
};

db.orders.find(filter);
```

Write negative tests to ensure a request from tenant T01 **cannot** access T02 documents.

## 32. Incident Scenario 3: Data Deletion and Backups in the Same Blast Radius

### 32.1. Scenario

An attacker obtains admin credentials, drops collections, and uses the same account to delete backup object storage.

### 32.2. Why Is Replication Not Enough?

Valid deletes/drops replicate to secondaries. If backups live under the same privilege boundary, every recovery point can vanish.

### 32.3. Measures

- Separate backup accounts and namespaces/cloud accounts where appropriate.
- Immutable backups/retention locks.
- KMS access controls and key recovery plans.
- Audit admin and backup actions.
- Restore drills and target RPO/RTO.

This is the clearest illustration of **defense in depth**: backups must be independent enough to survive when a production administration layer fails.

## 33. Incident Scenario 4: Insider with Legitimate Read Access

A legitimate support agent has read access to the customer collection, but attempts to export all phone numbers.

### 33.1. Why Don't Passwords and TLS Solve This?

The identity is **not spoofed** and the connection uses **valid TLS**. The risk lies in overly broad real permissions or behavior beyond intended purpose.

### 33.2. Appropriate Controls

- Job-scoped roles that reduce export capabilities.
- APIs returning only necessary fields.
- Accessing sensitive data through approved workflows.
- Field-level encryption when separation of decryption privilege is required.
- Auditing, watermarking, anomaly detection, and DLP.
- Periodic access reviews.

A compliance-critical system requires both technical controls and processes, not just database configuration.

## 34. Common Misconceptions

| Misconception | Reality |
|---|---|
| Enabling a password is secure enough | You also need network, TLS, RBAC, app controls, and backups |
| TLS makes leaked credentials useless | Anyone with valid credentials can still log in if they reach the endpoint |
| Private IP means only legitimate apps connect | Machines on the network can still be compromised or misconfigured |
| A `readWrite` user always has minimal privileges | It can write to many collections across the entire database |
| DB RBAC automatically filters `tenantId` | The app needs tenant-aware authorization |
| All client-sent BSON filters are safe | Risk of NoSQL injection/operator abuse |
| Schema validation prevents all fraud | Schemas do not enforce ownership or business authorization |
| Encryption at rest hides data from querying DB admins | The server can decrypt according to valid privileges |
| CSFLE stops every attacker | An app holding plaintext/keys is still a target |
| Queryable Encryption supports every query like plaintext | Has limits on types/operators/versions |
| A replica set is a backup | Valid deletes/updates can be replicated |
| Existing backups guarantee recoverability | You must test restores + keys |
| Audit logs automatically block bad behavior | Auditing primarily supports detection/investigation |
| No public port means no injection | API flaws remain an attack path |
| Every auth failure is brute force | Can be caused by deployment/config mistakes |
| One shared admin account makes operations easy | Hurts accountability and widens blast radius |
| Removing a secret from Git HEAD makes it safe | It can remain in history/clones/logs |
| `bindIp: 0.0.0.0` is just convenient config | Expands the connection surface |
| Disabling TLS cert checks is fine since traffic is encrypted | Risks server impersonation/MITM |
| Turning on all auditing is always better | Must balance sensitive data, overhead, and log value |
| MongoDB Atlas handles all application security | The app remains responsible for AuthZ, secrets, and data |
| Every security feature exists in every edition | Depends on version, deployment, and plan |
| Risk levels follow directly from STRIDE theory | Must factor in real assets, exposure, and impact |
| A one-time config check lasts forever | Threat models must be updated as systems change |

## 35. Hands-On Exercises

### Exercise 1 — Draw Trust Boundaries

A system consists of a browser, a Java API, a MongoDB replica set, a reporting tool, and backup storage. Draw at least three trust boundaries and specify the authentication/authorization for each flow.

### Exercise 2 — CIA Classification

Classify: customer address leak, balance tampering, lost backup, CPU-exhausting query, unauthorized user role modification. For each item, state the affected CIA attributes and why.

### Exercise 3 — STRIDE

For the `GET /orders/{id}` endpoint, list one threat for each letter in STRIDE. Do not assume the attacker already has admin privileges.

### Exercise 4 — Risk Prioritization

Pick three risks: public MongoDB port, missing admin login audit, untested backup restores. Build a risk register including likelihood, impact, owner, control, and evidence.

### Exercise 5 — Least Privilege

A service only needs to read `shop.products` and write `shop.orders`. Why is the `root` role inappropriate? Compare database-level built-in `readWrite` with a collection-scoped custom role.

### Exercise 6 — Tenant Isolation

A user in tenant T01 guesses an order ID belonging to T02. Fix the `findOne()` and `updateOne()` conditions so they always bind tenant ownership from the authenticated context.

### Exercise 7 — NoSQL Injection

An API receives a raw JSON filter from the browser and calls `Document.parse()` to query. Where is the risk? Write a DTO with constrained parameters and use the builder API to construct a safe filter.

### Exercise 8 — TLS

A team encounters a certificate hostname mismatch and proposes enabling `tlsAllowInvalidHostnames` in production. Evaluate the risk and propose the proper fix.

### Exercise 9 — Three Encryption Layers

Explain the differences between TLS, encryption at rest, and CSFLE in these scenarios:

1. A disk is stolen.
2. The network connection is eavesdropped.
3. A database admin has document read privileges but lacks the client key.
4. The Java app process is compromised.

### Exercise 10 — KMS and Recovery

Backup data is encrypted, but the master key is deleted. Why does having backups not guarantee recovery? Design responsibilities for key management, rotation, and recovery.

### Exercise 11 — Replica Set

Why do secondaries also need TLS, internal authentication, OS hardening, and encryption at rest? Does a secondary automatically “save” documents deleted on the primary?

### Exercise 12 — Sharding

A system has public `mongos` instances but private shards. Which trust boundaries still exist? Why do config servers and cluster metadata also need protection?

### Exercise 13 — DoS

An application lets users submit any aggregation pipeline. Propose at least six defenses covering allowlists, timeouts, indexes, quotas, pooling, and monitoring.

### Exercise 14 — Secret Rotation

`orders_service` credentials leak in CI logs. Write a response and rotation procedure that avoids taking down the application while cutting off access for anyone holding the old credential.

### Exercise 15 — Audit and Monitoring

You observe 100 login failures in one minute, rising read traffic, and a newly created admin user. Classify the alerts, list data to investigate, identify relevant log sources, and explain how to avoid jumping to conclusions without evidence.

### Exercise 16 — Backup vs. Replication

An admin accidentally drops a collection at 10:05. The cluster has a three-node replica set. Explain why replication does not guarantee rollback, then design RPO/RTO targets and a restore drill.

### Exercise 17 — Atlas vs. Self-Managed

Build a responsibility table for OS patching, DB users, application AuthZ, VPC rules, backup policy, KMS keys, auditing, and incident response across both deployment models.

### Exercise 18 — Insider Access Analysis

A support agent needs to look up order statuses without viewing full PII. Propose ways to minimize exposed data via APIs, DB roles, and field encryption where appropriate.

### Exercise 19 — Full Threat Model

Design a threat model for this platform:

```text
User -> API -> MongoDB sharded cluster
               |
               +-> Analytics ETL
               +-> Daily backup
               +-> Audit/monitoring
```

Required deliverables:

1. Asset inventory.
2. Data flow diagram and trust boundaries.
3. At least 10 threats across STRIDE categories.
4. Prioritized risk register.
5. Threat → preventive/detective/recovery control mapping.
6. Verification evidence and owners.

### Exercise 20 — Tabletop Incident Response

Suppose there is evidence that admin credentials were compromised, customer data was read, and several collections were dropped. Plan:

- Containment without destroying evidence.
- Credential revocation, log and egress investigation.
- Data and impact classification.
- Restoring in an isolated environment.
- Integrity reconciliation.
- Service recovery and lessons learned.

Do not perform deletions or unauthorized investigations on real systems.

## 36. Pre- and Post-Deployment Security Checklist

### Before Production Go-Live

1. MongoDB endpoints are reachable only from authorized networks and identities.
2. TLS is required and certificate/hostname verification is properly enforced.
3. Client authentication and internal member authentication are configured.
4. Each service has its own DB user/identity; `root` is not shared.
5. Privileges have been reviewed against the **principle of least privilege**.
6. APIs enforce tenant/business authorization and validate inputs.
7. Queries/pagination/aggregations do not allow user-controlled arbitrary operators.
8. Data files/backups/keys are protected according to sensitivity requirements.
9. Auditing/monitoring has owners, retention, and alerts.
10. Backups have RPO/RTO policies and tested restores.
11. Secret rotation and revocation have runbooks.
12. MongoDB/OS/driver patching and CVE reviews are part of the lifecycle.

### During Operations

1. Review network exposure and IAM drift periodically.
2. Audit service account privileges.
3. Verify TLS certificate expiration/rotation.
4. Monitor auth failures, admin actions, and data egress.
5. Monitor query latency/slow operations and capacity.
6. Run restore drills, verifying KMS/key vault as well.
7. Scan for secrets in CI/repos/logs.
8. Update the threat model when adding services, regions, shards, or sensitive data.
9. Review audit retention and log read permissions.
10. Maintain incident response playbooks, owner contacts, and escalation paths.

## 37. Summary

**Threat modeling means reasoning from assets and attack paths to controls.** In MongoDB, typical risks include credential exposure, cross-tenant access, NoSQL injection, privilege abuse, backup leakage, denial of service, and data destruction. STRIDE helps ensure critical threat classes are not missed, while a risk register drives accountable prioritization.

**Defense in depth is the core principle.** Network isolation reduces reachability; TLS protects data in transit; authentication verifies identity; RBAC and application AuthZ limit actions; schema validation supports data integrity; encryption at rest and client-side encryption defend against distinct unauthorized read scenarios; auditing/monitoring detect activity; and backups/restores limit damage when an incident occurs.

**No control is an “absolute safety button”.** TLS cannot save compromised credentials, encryption at rest does not replace DB permissions, RBAC does not automatically filter tenants in a shared collection, replica sets do not replace backups, and backups without restore drills and key recovery do not guarantee recovery.

A trustworthy MongoDB system requires **least-privilege access, clear trust boundaries, observable operations, and verified recovery capability**. The threat model must be revisited whenever architecture, sensitive data, identities, or system boundaries change.

## References

- [MongoDB — Security Checklist for Self-Managed Deployments](https://www.mongodb.com/docs/manual/administration/security-checklist/): key control layers, hardening, and data protection.
- [MongoDB — Security](https://www.mongodb.com/docs/manual/security/): authentication, authorization, TLS, encryption, and auditing.
- [MongoDB — Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/): roles, privileges, and permission boundaries.
- [MongoDB — Configure TLS](https://www.mongodb.com/docs/manual/tutorial/configure-ssl/): TLS configuration and connection verification.
- [MongoDB — Client-Side Field Level Encryption](https://www.mongodb.com/docs/manual/core/csfle/): application-side field encryption.
- [MongoDB — Queryable Encryption](https://www.mongodb.com/docs/manual/core/queryable-encryption/): querying encrypted fields and its limitations.
- [MongoDB — Encryption Key Management](https://www.mongodb.com/docs/manual/core/csfle/fundamentals/manage-keys/): DEK, CMK, key vault, and KMS.
- [OWASP — Threat Modeling](https://owasp.org/www-community/Threat_Modeling): methodology for identifying threats and trust boundaries.
- [OWASP — NoSQL Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/NoSQL_Security_Cheat_Sheet.html): input validation, least privilege, and injection prevention.
