# Reviewing Configuration Before Taking a System to Production

A MongoDB database can function properly on a developer's machine yet still be **unsafe to deploy to production**. The application inserts, updates, and queries fine while the cluster leaves ports open to the Internet, lacks authentication, uses an all-powerful account, skips TLS certificate validation, has no recoverable backups, or accidentally logs sensitive data.

Therefore, a **pre-production configuration review** (*production security readiness review*) is an activity with defined criteria, evidence, and accountable owners. The goal is not merely checking a “security enabled” box, but answering:

- Who can connect to MongoDB, from which networks, and using which mechanisms?
- Are connections encrypted and **authenticating the right server**?
- Does each account hold only the exact business permissions it needs?
- How do replica set and sharded cluster nodes authenticate one another?
- How are secrets, private keys, backup files, and data copies protected?
- Can unauthorized access, privilege changes, and anomalous behavior be detected?
- Upon data loss or a ransomware incident, can you **actually** recover within committed RPO/RTO?
- Do features such as change streams, MongoDB Search/Vector Search, analytics, and downstream systems introduce additional data-leak surfaces?
- Which conditions **must block release** until resolved?

This lesson belongs to the **Security** chapter of the **Database Engine Document MongoDB** module. It covers two primary models: **MongoDB Atlas** (managed service) and **self-managed MongoDB** (operations manages `mongod`, `mongos`, OS, certificates, and infrastructure).

> **Principle:** “The database works” does not mean “the database is securely configured.” **Every PASS determination needs deployment-appropriate evidence**, an identified reviewer, timestamp, and handling plan when configurations drift.

## 1. Define the Review Scope

Before inspecting a single parameter, know **what the real system contains**.

Example architecture:

```text
End user / Browser
        │
        ▼
API Gateway / Load Balancer
        │
        ▼
Application services
        │
        ├── MongoDB driver / connection pool
        │           │
        │           ▼
        │     MongoDB deployment
        │       ├── mongod replica set nodes
        │       ├── mongos routers (if sharded)
        │       ├── config servers (if sharded)
        │       └── Search/Vector Search (if used)
        │
        ├── Cache / Message queue
        ├── Search index / Analytics
        ├── Embedding/AI providers
        └── Monitoring / Backup
```

A checklist inspecting only `mongod.conf` will miss:

- APIs leaking connection strings in logs.
- Kubernetes Secrets readable across every namespace.
- MongoDB backups uploaded to a public bucket.
- Admins running every service under a `root` account.
- A CDC connector copying PII to another system with no retention limits.
- Search result caches returning another tenant's data.

### 1.1. Minimal Inventory

Build a table usable during the review:

| Component | Details to Record |
|---|---|
| Environment | Dev, staging, production |
| Deployment | Atlas Dedicated/Flex or self-managed |
| Versions | MongoDB Server, FCV, drivers, Search process if any |
| Topology | Standalone, replica set, sharded cluster |
| Nodes/regions | Node placement and data regions |
| Public/private endpoints | Permitted access paths |
| Applications | Services connecting to MongoDB |
| Identities | Database users, Atlas project users, service accounts |
| Data | Data types, PII, secrets, sensitivity classification |
| Key management | TLS CA, KMS, encryption keys, rotation |
| Backups | Schedule, storage location, encryption, restore drills |
| Observability | Logs, audits, metrics, alerts, recipients |
| Downstream | BI, CDC, Search, Vector Search, ETL, exports |
| Owners | Who approves and remediates each item |

If you do not yet know all clients and data flows touching MongoDB, you cannot declare the system safe after glancing at cluster settings once.

### 1.2. Severity Classification

One way to structure a pre-release quality gate:

| Severity | Examples | Decision |
|---|---|---|
| **BLOCKER** | No authentication; Internet-exposed DB; unverified TLS; cross-tenant access; missing backups for critical data | **Do not go live** |
| **HIGH** | Over-privileged service account; no rotation plan; missing audits for regulated systems; no restore tests | Remediate or obtain approved risk acceptance |
| **MEDIUM** | Unclear log retention, unoptimized alerts, upcoming index/driver upgrade | Assign owner and deadline |
| **LOW** | Incomplete asset metadata, operational runbooks needing standardization | Track for improvement |

Actual severity must reflect **data classification, exploitability, and business impact**; the table is an illustrative framework.

## 2. Reviewing Under the Shared Responsibility Model

MongoDB Atlas and self-managed differ in who runs infrastructure operations, yet neither model absolves the application from data security responsibility.

### 2.1. MongoDB Atlas

Atlas manages many deployment layers—such as provisioning, underlying infrastructure, updates, and certain backup/monitoring tiers. Still, the organization must control:

- Atlas Organization/Project roles;
- Network access lists and private connectivity;
- Database users, service accounts, and credentials;
- Encryption/KMS settings in use;
- Application authorization and tenant isolation;
- Retention, data classification, and exports;
- Backup/PITR plans per tier;
- Atlas API keys and access tokens;
- Search/Vector Search configuration and downstream data access;
- Incident monitoring and periodic access review policies.

**Managed does not mean “automatically secure for every usage pattern”.**

### 2.2. Self-Managed MongoDB

Beyond the responsibilities above, operations must also manage:

- OS, kernel, container runtime, and patching;
- Firewalls, network segmentation, DNS, and host hardening;
- Installation/versions of `mongod`, `mongos`, and config servers;
- TLS certificate/key lifecycles;
- Internal member authentication;
- Filesystem permissions and storage encryption;
- Process service accounts and service managers;
- Audit logging/configuration per edition;
- Replication, backup agents, and monitoring agents;
- Resource limits, disk, time sync, and failover;
- Restores and disaster recovery.

A dev box running `mongod --bind_ip_all` exposed to the Internet does not become production-ready simply by adding RAM.

### 2.3. Checklists Must Match the Actual Deployment

| Area | Atlas | Self-Managed |
|---|---|---|
| Database authentication | Configure database users and roles | Must enable/verify `authorization` and users |
| Client-side TLS | Use right TLS endpoint, verify certs | Provision certs/CA yourself, set `requireTLS` |
| Network | IP access list, peering/private endpoint | Firewalls/security groups, VPC, `bindIp` |
| Internal member auth | Managed by Atlas per deployment | Must configure `keyFile` or X.509 properly |
| Secrets | Accounts/URIs/Atlas API keys | All of those plus TLS private keys |
| Backup | Select/configure retention, PITR per tier | Implement and test yourself |
| Logging/auditing | Atlas/tier-supported features | Configure and protect yourself |
| Version patches | Atlas lifecycle and upgrade schedule | Manage server/OS/driver patches yourself |
| Data authorization | Application's responsibility | Application's responsibility |

## 3. Threat Model Before Inspecting Parameters

An effective review starts from **assets and threat actors**.

### 3.1. Assets to Protect

- Customer data, financial info, and PII;
- Orders, contracts, and transaction history;
- Credentials, refresh tokens, and API keys;
- Tenant metadata and RBAC/ACLs;
- Backups, snapshots, and exports;
- Search indexes and embeddings of sensitive documents;
- Audit logs;
- Encryption keys;
- Connection strings and infrastructure configs.

### 3.2. Potential Attack Paths

```text
Internet
   │
   ├── Public DB endpoint
   ├── Stolen application credentials
   ├── Compromised CI/CD secrets
   ├── Misconfigured backup bucket
   ├── Application injection / broken authorization
   └── Exposed monitoring or management API
           │
           ▼
       MongoDB / data
```

Do not ask only “does anyone know the password?”. Threat actors include:

- External Internet attackers;
- Broadly privileged insiders;
- A compromised service;
- A tenant attempting cross-tenant data access;
- Vendors/connectors with data access;
- A hijacked deployment pipeline.

### 3.3. Layered Defense Model

To read a sensitive document, an attacker should have to defeat multiple independent layers:

```text
Network boundary
   ↓
TLS verification
   ↓
Authentication
   ↓
Database RBAC
   ↓
Application authorization
   ↓
Tenant/document ACL
   ↓
Data classification / field filtering
   ↓
Logging & detection
```

**Never use one layer to substitute for all others.** For example, an IP allowlist does not replace passwords/TLS, and a database `read` role does not know which end user owns which order.

## 4. Network Review: Is the Database Exposed Externally?

### 4.1. Default Principle

MongoDB must never be exposed to the entire Internet merely for connection convenience.

Questions that must have answers:

1. Which hosts/subnets **need** to connect?
2. Is port `27017` or any configured port publicly reachable?
3. Does a valid private networking path exist?
4. Do CI/CD, admin, and support connections pass through controlled paths?
5. Is egress from apps to MongoDB restricted per policy?
6. Is bastion/VPN/zero-trust access enforced for admins?
7. Are network diagrams and owners current?

### 4.2. Atlas Network Access

For Atlas, verify:

- Is the Atlas project IP access list overly broad?
- Are there `0.0.0.0/0` or IPv6 wildcard entries?
- Have old employee, CI runner, and partner IPs been revoked?
- Are Private Endpoints, peering, or private networking used where required?
- Do permitted network identities match the design?

**The IP access list is a network control, not an authentication mechanism.** An allowlisted IP with wrong credentials must still fail. Conversely, valid credentials should never open access from everywhere.

Allow-all rules appear in dev tutorials, but are a **BLOCKER** in production without an approved exception and compensating controls.

### 4.3. Self-Managed: `bindIp` and Firewalls

Conceptual configuration example:

```yaml
# mongod.conf - illustrative only, do not copy verbatim to production
net:
  port: 27017
  bindIp: "127.0.0.1,10.10.1.25"
```

`bindIp` specifies which local network interfaces `mongod` listens on. It **does not replace host firewalls, security groups, Kubernetes NetworkPolicies, or network segmentation**.

If applications run in another subnet, pair the right interface binding with firewall rules. Never “quick-fix” by binding `0.0.0.0` on a host with a public IP.

### 4.4. Test from Both Sides

- From application subnets: connections succeed with valid TLS and credentials.
- From unauthorized networks: connections are rejected as designed.
- From admin networks: only authorized accounts and controlled paths work.
- From the Internet: database ports are unreachable if architecture mandates private-only.

In production, test only within authorized scope and change windows; avoid unauthorized network scanning.

### 4.5. Never Connect Browser Clients Directly to MongoDB

Browser and public mobile clients should call a backend API rather than embedding MongoDB connection strings with database credentials.

```text
Browser / Mobile
       │ HTTPS + user identity
       ▼
Application API
       │ MongoDB driver + service identity
       ▼
MongoDB
```

Embedding credentials in frontend JavaScript lets users extract them and bypass backend validation and authorization.

## 5. TLS: Encryption Alone Is Not Enough—Authenticate the Right Server

TLS protects data in transit between clients and the database, and between cluster components as supported by the architecture.

Reviews must confirm:

- TLS is actually required;
- Server certificates are signed by a trusted CA;
- URI hostnames match certificate SANs;
- Certificates are unexpired;
- Clients never disable certificate or hostname verification;
- Protocols and ciphers comply with policy and version;
- Private keys carry strict filesystem permissions;
- Rotation procedures exist ahead of expiration dates.

### 5.1. MongoDB Atlas URI

A structurally safe example:

```text
mongodb+srv://APP_USER:<PASSWORD>@cluster.example.mongodb.net/
  ?retryWrites=true&w=majority
```

Line breaks here are for readability only; real URIs are **single continuous strings**, and the hostname is a placeholder.

`mongodb+srv` uses DNS SRV/TXT lookups to locate hosts and options. On Atlas, use the Atlas-provided connection string with **full TLS verification**. Never hardcode URIs with passwords in source code.

### 5.2. Dangerous TLS Options

Never use in production:

```text
tlsAllowInvalidCertificates=true
tlsAllowInvalidHostnames=true
tlsInsecure=true
```

These weaken or bypass certificate verification. An application with an “encrypted connection” that skips server identity verification remains vulnerable to man-in-the-middle attacks.

In the Java MongoDB Driver, configure a valid truststore/CA instead of writing a `TrustManager` that trusts every certificate.

### 5.3. Self-Managed `requireTLS`

Reference configuration:

```yaml
net:
  port: 27017
  bindIp: "127.0.0.1,10.10.1.25"
  tls:
    mode: requireTLS
    certificateKeyFile: /etc/mongodb/tls/server.pem
    CAFile: /etc/mongodb/tls/ca.pem
```

This is **only a configuration skeleton**; production requires real certificate paths, node-specific settings, permissions, certificate chains, and verified client compatibility. Never switch `requireTLS` on abruptly and break replica sets or clients; follow a rollout plan with compatibility checks and rollback.

### 5.4. Internal TLS

With multi-member MongoDB, inspect:

- TLS between clients and servers;
- TLS between members/routers/config servers per topology;
- Internal authentication;
- TLS for monitoring and backup agents;
- TLS for Search/analytics connectors if used.

A TLS client URI **does not prove** internal links comply with policy.

## 6. Authentication: Never Leave the Database Open

### 6.1. Self-Managed `authorization`

Self-managed setups normally require:

```yaml
security:
  authorization: enabled
```

For a replica set using keyfile internal authentication, settings may include:

```yaml
security:
  authorization: enabled
  keyFile: /etc/mongodb/secrets/replica-key
```

**Never copy and restart immediately in production.** Enabling authentication on a replica set or sharded cluster requires strict sequencing, especially when previously unauthenticated or lacking initial admin users. Getting the order wrong can lock out operators or prevent members from authenticating each other.

### 6.2. Authentication Mechanisms

MongoDB supports multiple mechanisms depending on edition, version, and deployment:

| Mechanism | Context |
|---|---|
| SCRAM-SHA-256 | Common username/password auth |
| SCRAM-SHA-1 | Legacy compatibility; review policy and upgrade |
| X.509 | Certificate-based auth for clients/members per configuration |
| LDAP/Kerberos | Depending on supported edition and integration model |
| OIDC | Depending on server/Atlas/driver versions and IdP config |
| Atlas cloud/IAM integrations | Per supported Atlas mechanism and tier |

Never choose a mechanism by name alone. Verify compatibility, identity lifecycles, revocation, admin MFA, and audit requirements.

### 6.3. MFA Belongs at the Right Layer

MFA is vital for **human admin access**, such as the Atlas UI, identity providers, and operations consoles. Backend applications using service accounts do not prompt MFA per database query; instead they need short-lived identities or secret rotation, network controls, and least privilege.

Never write “MongoDB users have passwords so the system has MFA” when only the Atlas console enforces MFA.

### 6.4. The Localhost Exception Is for Bootstrapping, Not Operations

MongoDB supports creating the first admin user from localhost when no users exist yet. That is a **conditional bootstrapping mechanism**, never a routine admin workflow or an assumed safe steady state.

Ensure an admin user is provisioned before locking down access paths and verify the system is never stranded without an administrative account.

## 7. RBAC and the Principle of Least Privilege

After authentication comes: **what is the account allowed to do?**

In MongoDB, database users can receive built-in roles like `read`, `readWrite`, `dbAdmin`, `userAdmin`, plus cluster roles. Broad roles like `root`, `readWriteAnyDatabase`, and `userAdminAnyDatabase` have wide blast radii and rarely belong in ordinary applications.

### 7.1. Separating Identities

Maintain distinct identities:

| Identity | Purpose | Typical Privileges |
|---|---|---|
| Catalog read API | Queries only needed collection | Custom read role or scoped `read` on right DB |
| Order writer | Reads/writes specific business collections | Custom role with bounded actions |
| Migration job | Planned schema/index changes | Time-bounded elevated privileges |
| Backup agent | Reads data for backups per tool | Matching backup role |
| Monitoring agent | Collects metrics and status | Matching monitoring role |
| DBA/operator | System administration | Approved elevated role |
| Break-glass admin | Emergency incident recovery | Maximum privilege, isolated and audited |

Never share one username/password across APIs, workers, BI connectors, and migration jobs. When a credential leaks, blast radius must stay contained.

### 7.2. Database Roles Are Not Row-Level Tenant ACLs

An account with `read` on `orders` can read **multiple documents** in that collection within its role scope. Traditional MongoDB RBAC does not understand:

```text
user U1 may only view tenant A's orders
user U2 may only view tenant B's orders
```

Enforcing that belongs to application authorization, data access layers, or stronger tenant-isolation architectures.

In multi-tenant shared collections, require:

- Trusted tenant ID from authentication;
- Mandatory tenant predicate in queries;
- Guarded direct-by-ID access;
- Cross-tenant negative tests;
- Never letting users override scope via URL or request body.

### 7.3. Inspecting Session Privileges

In `mongosh` in an authorized environment:

```javascript
db.runCommand({
  connectionStatus: 1,
  showPrivileges: true
});
```

Useful for viewing authenticated users/roles and effective privileges per granted permissions. Exact output depends on version and permissions.

Never trust manifests alone; verify the **actual production service account** holds the expected identity and privileges.

### 7.4. Viewing Users/Roles with an Authorized Account

```javascript
use admin;

db.runCommand({
  usersInfo: 1,
  showPrivileges: true
});
```

Requires appropriate privileges, and output may expose user/role metadata. **Never paste raw output into public tickets.** For multi-database apps, inspect the exact authentication database and role scope.

### 7.5. Permissions to Manage Search Indexes and Database Indexes

Creating or dropping MongoDB Search / Vector Search indexes is an administrative operation impacting queries and cost. Ordinary APIs running `$search` or `$vectorSearch` should not hold rights to create or drop those indexes.

Likewise, never let a public-facing service edit users/roles or drop databases.

## 8. Internal Authentication in Replica Sets and Sharded Clusters

Multi-node replica sets must authenticate members to each other. Sharded clusters also include `mongos` routers and config server replica sets.

### 8.1. Why User Authentication Alone Is Insufficient

If client auth exists yet members lack properly configured internal trust, replication and failover can fail or untrusted processes can abuse internal links.

MongoDB provides internal authentication mechanisms such as:

- Shared `security.keyFile` per deployment rules;
- X.509 certificate-based member authentication;
- `clusterAuthMode` settings for migration/configuration strategies.

### 8.2. Keyfiles Are Infrastructure Secrets

A keyfile on disk must be protected:

- Never stored in plaintext in Git;
- Never sent via chat or email;
- Restricted filesystem ownership/permissions;
- Securely distributed only to authorized members;
- Scheduled for rotation;
- Backed up securely per recovery policy;
- Excluded from logs and container image layers.

On Linux/POSIX, keyfiles typically require tight permissions (e.g., owner read-only). Windows has its own ACL rules; never blindly copy `chmod` commands across platforms assuming they apply.

### 8.3. Inspect Topology Without Reckless Changes

Read-only status commands on a replica set when authorized:

```javascript
rs.status();
```

On a sharded cluster, per version/tooling:

```javascript
sh.status();
```

These report topology and availability status; they **do not audit the entire security posture**. Combine them with network, TLS, internal auth, and operational evidence.

Never run `rs.initiate()`, `rs.reconfig()`, keyfile rotation, or cluster-wide restarts during a read-only production “check”. Those belong to separate **change management** workflows.

## 9. Secrets Management: Never Hardcode, Never Log, Always Rotate

MongoDB secrets include:

- Database usernames/passwords;
- Atlas programmatic API keys;
- TLS certificate private keys;
- Internal authentication keyfiles;
- KMS credentials;
- Backup encryption keys;
- Identity provider tokens;
- Monitoring and CDC connector secrets.

### 9.1. Places Secrets Must Never Be Stored

- Source code or public repositories;
- Dockerfiles or container image layers;
- CI logs;
- Command-line history;
- Uncontrolled chat or tickets;
- Frontend JavaScript or mobile app bundles;
- Traces or raw exception dumps;
- `.env` files committed to Git;
- Copy-pasted README examples containing real passwords.

### 9.2. Java URI Loading Pattern

```java
String uri = System.getenv("MONGODB_URI");

if (uri == null || uri.isBlank()) {
    throw new IllegalStateException("MONGODB_URI is missing");
}

// In a real application, pass the URI to MongoClients.create(uri)
// and manage MongoClient across the application lifecycle.
```

Environment variables beat hardcoding, yet **are not a complete secrets manager by themselves**. In production, prefer approved secret management such as workload identities, Vault, or cloud secret stores with access policies and rotation.

### 9.3. Rotation Needs Dual Active States

Rotation workflow:

```text
1. Provision a new credential or identity.
2. Deploy clients supporting the new credential.
3. Verify connectivity works.
4. Revoke the old credential.
5. Confirm no stale clients remain.
6. Audit and record the rotation timestamp.
```

For certificate/CA rotation or internal auth keys, procedures are more intricate and must preserve inter-node compatibility during rollout.

Never swap secrets in a way that knocks all application pods offline before recovery begins.

### 9.4. Scope Secrets per Service

A catalog-read service never needs the replica set's keyfile. A monitoring agent never needs payment provider API keys. Scope secrets strictly by **need-to-know** using audited accounts.

## 10. Reviewing Encryption at Rest and Key Management

Two distinct layers:

- **Encryption in transit:** TLS protects connections.
- **Encryption at rest:** protects stored data on disks, snapshots, and backups per deployment mechanism.

On Atlas, encryption at rest is provided by tier/model, with some tiers supporting **customer-managed keys** via KMS. Self-managed options include disk/volume encryption and licensed MongoDB Enterprise features per version.

### 10.1. Questions to Confirm

1. Is MongoDB data on disk encrypted?
2. Are snapshots, backups, and exports encrypted accordingly?
3. Who owns and manages master keys / data encryption keys?
4. Is there a rotation policy?
5. Who can decrypt or restore?
6. Are keys stored alongside ciphertexts where an attacker could grab both?
7. Can data still restore if a key is lost or revoked?
8. Are KMS operations audited?
9. Are there data residency or regional requirements?

**Having encryption yet losing the key can mean losing the ability to recover data.**

### 10.2. Queryable Encryption Does Not Replace RBAC

MongoDB offers client-side encryption features like Queryable Encryption for supported query types and fields. These carry strict version, field type, operator, and performance constraints.

Never assume:

- Any encrypted field can still be queried/sorted/indexed arbitrarily;
- Client-side encryption provides tenant authorization automatically;
- Search/Vector Search works directly on ciphertext like plaintext;
- Encrypted backups alone satisfy data-deletion mandates.

If using CSFLE or Queryable Encryption, review **encrypted field schemas, key vaults, KMS, driver compatibility, client policies**, and query limits.

### 10.3. Encryption Keys Are a DR Dependency

A restore drill passes only if:

- Backups are readable;
- Keys are accessible per policy;
- The database restores cleanly;
- Users, roles, and policies are restored properly;
- Applications query restored data successfully;
- Sensitive data remains protected throughout.

## 11. Audit Logging and Tracking Sensitive Activity

Production may need to answer:

- Who created or deleted users;
- Who granted or revoked roles;
- Who changed network or cluster configurations;
- Who changed encryption or KMS settings;
- Whether unusual failed access attempts occurred;
- Whether bulk data exports happened;
- Whether out-of-process privilege escalations occurred.

### 11.1. Distinguishing Log Types

| Type | Primarily Provides |
|---|---|
| Application logs | Request IDs, business actors, business outcomes |
| MongoDB server logs | Process activity, connection errors, replication, warnings |
| MongoDB audit logs (if supported by feature/edition) | Configured auditable database actions |
| Atlas Activity Feed / Project logs | Atlas management-plane changes |
| OS/cloud audit logs | VM, IAM, KMS, network, and storage actions |
| Access gateway logs | Who entered bastions, VPNs, or consoles |
| Backup logs | Backup success/failure, restores, retention edits |

Server logs cannot tell which human clicked “Delete order” if multiple users share one backend service account. Application audit logs must include **business actor and correlation IDs** per policy.

### 11.2. Audit Logging Is Not Automatically Present on Every Edition

Availability and format depend on Atlas tier, MongoDB Enterprise/self-managed, and version. Never mark “auditing enabled” just because a server writes a log file.

Verify:

- Is database auditing genuinely supported and active?
- Do audit filters capture all mandatory operations?
- How long are logs retained?
- Where are logs stored, and are they encrypted?
- Who can delete or edit logs?
- Are alerts configured for actionable incidents?
- Were benign test events simulated to confirm end-to-end tracing?

### 11.3. Never Log PII or Secrets

Avoid:

```javascript
// Avoid in production:
printjson(db.customers.findOne({ _id: "CUSTOMER-123" }));
```

If documents contain password hashes, session tokens, emails, addresses, or financial fields, printing entire documents to stdout or CI logs causes leaks.

Prefer minimal metadata logging:

```javascript
printjson({
  traceId: "TRACE-EXAMPLE",
  operation: "customer-read",
  result: "success",
  recordCount: 1
});
```

Evaluate IDs against privacy policy too; swapping contents for an ID does not automatically make logs non-sensitive.

## 12. Backups: “Having Backups” Is Not Enough

One of the biggest production risks is running daily backup jobs while **never once testing a restore**.

### 12.1. Two Metrics to Define

- **RPO — Recovery Point Objective:** maximum acceptable data loss in an incident.
- **RTO — Recovery Time Objective:** maximum acceptable time to restore service.

Example:

```text
RPO = 15 minutes
RTO = 2 hours
```

This means the business expects at most 15 minutes of data loss and service recovery within two hours under defined incident scopes. You cannot promise a 15-minute RPO with only 24-hour snapshots and no PITR/oplog mechanism.

### 12.2. Backup Verification Questions

1. Do backups run automatically on schedule and get monitored?
2. Is retention appropriate?
3. Are backups encrypted?
4. Are copies stored **outside the primary failure domain**?
5. Are immutable or tamper-resistant copies enforced where required?
6. Are restore drills performed periodically?
7. Are MongoDB configs, users/roles, and Search index definitions backed up as needed?
8. Are disk, network, and time sufficient to restore the real dataset?
9. Can decryption keys be recovered safely?
10. Does a runbook define who may restore and validate data?

### 12.3. Replica Sets Are Not Backups

Replica sets improve availability and replication, yet:

- If an app accidentally deletes documents and it replicates, all members lose them.
- If an attacker holds `dropDatabase`, that drop replicates too.
- If data is overwritten with bad values, replication spreads bad values too.

Thus, **replication does not replace backups**. Availability and recoverability are separate capabilities.

### 12.4. Sharded Clusters Need Consistent Backups

For sharded clusters, backups must coordinate **all shards, config servers, and metadata** via a supported solution. Taking uncoordinated snapshots of shards at arbitrary times does not yield a cluster-consistent backup.

Use backup/restore workflows supported by MongoDB or your platform; never copy raw data files piecemeal while a cluster accepts writes assuming they will restore cleanly.

### 12.5. Restore Drills Must Verify Applications

```text
Backup artifact
      │
      ▼
Isolated restore environment
      │
      ▼
MongoDB starts / topology healthy
      │
      ▼
Data integrity checks
      │
      ▼
Application smoke tests
      │
      ▼
RPO/RTO recorded
      │
      ▼
Evidence + remediation items
```

Never test restores by overwriting production. Use an isolated environment and protect restored data at the same sensitivity level.

### 12.6. MongoDB Search / Vector Search After Restores

Search indexes are derived data with their own sync lifecycle. After restoring, verify:

- Search index definitions remain appropriate;
- Indexes are queryable/ready;
- Initial sync or rebuild has finished;
- Search/Vector Search results match restored source data;
- The app handles fallback if Search is not yet ready.

Never declare DR complete just because `db.collection.findOne()` works when search is a core service dependency.

## 13. Availability Is More Than Having One Primary

Production deployments must address:

- Replica sets with appropriate voting-member topology;
- Failure domains / availability zones;
- Elections and failover;
- Primary stepdowns;
- Majority write concern / read concern aligned with durability goals;
- Connection pooling and retries;
- Disk space, inodes, IOPS, CPU/RAM;
- Network partitions;
- Backups and disaster recovery;
- Sharding availability where applicable.

### 13.1. Standalone vs. Replica Set

Standalone fits local study or very narrow workloads, whereas production systems needing HA, change streams, or transactions carry replication prerequisites. Never run a single unbacked process and label it “HA”.

### 13.2. Write Concern Is Not a Security Control

`w: "majority"` confirms writes under replication durability semantics. It **does not replace TLS, authentication, RBAC, or backups**.

Similarly, `readConcern` governs read isolation semantics, not read permissions.

### 13.3. Risk of All Members Sharing One Failure Domain

Three `mongod` processes on one VM or one physical disk fail together when that VM or disk dies. Verify **independent failure domains**, not just member counts.

## 14. MongoDB Versions and Security Patches

Before go-live, confirm:

- MongoDB Server version;
- Feature Compatibility Version (FCV);
- Driver versions;
- `mongosh`, backup agents, and automation tools;
- `mongos`, config servers, and shards;
- OS/container runtimes;
- MongoDB Search/Vector Search processes if present;
- Known CVEs affecting active components;
- EOL/support status;
- Upgrade and rollback plans.

### 14.1. Commands to Check Versions

In `mongosh` when connected:

```javascript
db.version();
```

Inspect FCV with an appropriately privileged account:

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
```

Never paste internal paths or connection metadata into public documents if policy forbids it.

### 14.2. Never Assume Major Version Alone Means Safe

Two MongoDB 8.x deployments can differ in patch level, edition, build, and configuration. Never write only “8.x” in checklists. When a vulnerability is disclosed, match advisories against the **exact running build**.

### 14.3. Avoid Changing Too Many Variables at Once

When moving staging → production, avoid simultaneously:

- Upgrading major server versions;
- Changing authentication mechanisms;
- Rotating the TLS CA;
- Migrating VPCs;
- Changing shard keys;
- Switching encryption providers;
- Upgrading drivers;
- Backfilling data.

If multiple changes are needed, stage them sequentially with independent verification and rollback so failures stay isolated.

## 15. Hardening the OS, Containers, and Kubernetes

Applies to self-managed MongoDB and self-operated agents/connectors.

### 15.1. Process Identity and Filesystem

- Run `mongod` under a dedicated OS account, never `root` unless strictly required.
- Restrict data directory permissions to the required process/group.
- Enforce strict permissions on TLS private keys and internal keyfiles.
- Avoid broad host filesystem mounts into containers.
- Avoid privileged containers without formal approval.
- Keep OS packages and base images patched per policy.
- Block uncontrolled interactive shell access.
- Configure resource limits, disk alerts, and log rotation.

### 15.2. Container Security

A hardened Docker setup requires:

- Trusted base images pinned by tag/digest per policy;
- Vulnerability scanning;
- No credentials baked into images;
- Never publishing ports on all interfaces just to test;
- Encrypted/permission-controlled persistent volumes;
- Read-only root filesystems where compatible;
- Graceful replica-set startup/shutdown handling.

Development example:

```yaml
services:
  mongodb:
    image: mongo:8.0
    ports:
      - "127.0.0.1:27017:27017"
```

**This example only demonstrates binding a port to localhost in development**—it is not a production config: it lacks authentication, TLS, persistent volumes, backups, replica set topology, and more. Never deploy it as-is.

### 15.3. Kubernetes

Review:

- Namespace isolation;
- Kubernetes RBAC;
- Pod Security settings;
- `runAsNonRoot`/security contexts per image;
- `NetworkPolicy` restricting ingress/egress;
- Secrets sourced from KMS/external secret stores where needed;
- Persistent Volume encryption and access controls;
- Node/pod affinity and failure domains;
- PVC/data backups and restores;
- Image provenance;
- Audit logs;
- Readiness/liveness probes suited to MongoDB topology.

Never configure aggressive liveness probes that repeatedly kill a primary/secondary during recovery or initial sync.

### 15.4. Infrastructure as Code

Security groups, firewalls, Atlas configs, and secret bindings should be managed via IaC/policy-as-code wherever supported. Never take one “safe today” screenshot and let configuration drift for months.

## 16. Reviewing Connection Strings, Drivers, and Application Config

Backend services using MongoDB drivers rely on settings affecting both security and resilience.

### 16.1. URI and Authentication Database

Example:

```text
mongodb://APP_USER:<PASSWORD>@db-internal.example:27017/app
  ?authSource=admin&tls=true
```

In a real single-line URI, `authSource` must point to **the database holding the authenticated user**, not automatically the business database across every deployment.

Special characters in usernames/passwords must be properly **percent-encoded** in connection strings. Never weaken passwords by dropping special characters just to “connect easier”.

### 16.2. Settings to Verify

- `MONGODB_URI` loaded from a secret store;
- Full URI never logged on exceptions;
- Standard driver TLS verification active;
- Appropriate authentication mechanism;
- `retryWrites` and write concern matching requirements;
- Bounded server selection and connect timeouts;
- Properly sized connection pools;
- Never creating a new `MongoClient` per HTTP request;
- Never using admin users in business APIs;
- Never enabling `tlsInsecure`;
- Not letting URIs target databases beyond granted permissions;
- Tested failover and certificate expiry handling.

### 16.3. Java Driver: Never Disable Hostname Verification

Example reading URI:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

String uri = System.getenv("MONGODB_URI");

if (uri == null || uri.isBlank()) {
    throw new IllegalStateException("MONGODB_URI is not set");
}

try (MongoClient client = MongoClients.create(uri)) {
    var database = client.getDatabase("app");
    var collection = database.getCollection("orders");

    System.out.println("Configured MongoDB client created.");
}
```

In real web applications, `MongoClient` should have a **shared long-lived lifecycle** instead of closing per request. This snippet shows only config loading, not a full production connection manager.

Never use a trust-all custom `TrustManager` to bypass certificate errors. Fix CA/SAN/hostname alignment properly.

### 16.4. Schema Validation Remains a Safety Layer

MongoDB's document model is flexible, yet production should enforce:

- Required fields;
- Valid BSON types;
- Value bounds;
- Mandatory `tenantId` presence;
- Preventing sensitive fields from landing in public structures;
- API input validation and schema versioning.

Schema validation does not replace authentication, but it blocks malformed data from write-authorized clients.

## 17. Reviewing Apps Against Injection and Broken Authorization

MongoDB does not use SQL, yet that **does not make it immune to injection**.

### 17.1. Unsafe Operator Injection

An endpoint accepting raw JSON directly:

```javascript
// Flawed by design:
const filter = request.body;
db.users.find(filter);
```

When clients control the entire filter/operator object, they can inject unauthorized conditions or subvert application logic.

Safer approach:

```javascript
// Illustrative: take userId only from identity context,
// and search status from a validated allowlist.
const filter = {
  tenantId: trustedTenantId,
  ownerId: trustedUserId,
  status: allowedStatus
};

db.orders.find(filter);
```

Never build queries by splicing untrusted BSON/JSON fragments. Validate data types and allowlist operators.

### 17.2. Direct-by-ID Cross-Tenant Access

An API endpoint:

```text
GET /orders/ORDER-999
```

querying only `{_id: "ORDER-999"}` leaks another tenant's order whenever IDs are guessable.

Safer pattern:

```javascript
db.orders.findOne({
  _id: orderIdFromValidatedInput,
  tenantId: trustedTenantId
});
```

Pair this with business-level authorization if multiple users within a tenant hold distinct permissions.

### 17.3. Unique Indexes Do Not Replace Authorization

A unique index enforces uniqueness across its defined key/partial filter; it does not decide who may create or modify documents. For example, `unique({tenantId, orderNumber})` ensures unique order numbers per tenant, yet cannot stop an attacker writing into another tenant if API authorization checks are missing.

## 18. MongoDB Search, Vector Search, and Change Streams Need Security Too

Many production apps use more than `find()`, relying on derived pipelines as well.

### 18.1. Search Indexes Can Hold Sensitive Data

Full-text Search indexes document fields. Even as tokens or derived structures, indexes can carry sensitive information. Check:

- Do field mappings index unnecessary PII?
- Does stored source retain entire documents?
- Who is allowed to query Search?
- Are tenant filters applied?
- Is authorization re-checked after retrieval?
- Do Search logs/metrics capture raw queries?

### 18.2. Search Indexes Have Sync Lag

Timeline:

```text
T1: Admin revokes access to DOC-1.
T2: MongoDB source updates ACL.
T3: Search index has not caught up yet.
T4: User searches and sees stale candidate.
```

Relying solely on indexed ACLs risks leaking stale content. Enforce an **authoritative permission check** before returning results or passing content to rerankers/LLMs.

### 18.3. Vector Embeddings Are Not Automatically Harmless

Embeddings are numeric vectors that can encode semantic information about source text. Ensure:

- Restricted access;
- Never returning raw embeddings to frontends unnecessarily;
- Reviewing policies of external embedding providers;
- Scoping access by tenant;
- Never mixing query scopes;
- Governing cache and retention.

### 18.4. Change Streams Can Emit Pre-Deletion Data

With pre-images enabled, delete events can expose **the document before deletion**. CDC and audit consumers must protect pipelines, credentials, logs, and event stores.

Permission to read change streams does not authorize consumers to keep PII indefinitely. Enforce downstream retention and redaction.

### 18.5. Analytics / BI / ETL Exports

A BI account needing order counts must not hold permission to dump the entire customer database. Use:

- Narrowest read-only roles;
- Field-restricted views or materialized projections where appropriate;
- Data masking/pseudonymization;
- Approved export destinations;
- TTL/retention policies;
- Access auditing.

Never grant `readAnyDatabase` to a dashboard reading a handful of collections.

## 19. Personal Data and Retention Lifecycle

Security is not only blocking hackers; it is also **not retaining sensitive data longer than necessary**.

### 19.1. Data Classification

Example:

| Data Class | Additional Controls |
|---|---|
| Public catalog | Integrity and anti-tampering |
| Internal docs | Access control, logging |
| Customer PII | Retention, masking, access permissions |
| Payment-related data | Dedicated organizational/standards protections |
| Credentials/secrets | No plaintext storage, key rotation |
| Audit records | Integrity, restricted access, retention |
| Health/legal/HR records | Sensitive classification, legal/compliance review |

Legal mandates vary by country and industry. Technical reviews must coordinate with legal and security leads rather than guessing retention periods.

### 19.2. TTL Indexes Are Not Instantaneous Deletion

MongoDB TTL indexes expire documents asynchronously; never promise a document vanishes to the exact millisecond at its deadline.

For deletion mandates, account for:

- Source documents;
- Backups/snapshots;
- Search indexes;
- Change streams/pre-images;
- Caches;
- Downstream exports;
- Logs;
- Analytics tables.

### 19.3. Soft Delete Differs from Physical Delete

Soft deletion retains the document marked inactive:

```javascript
{
  _id: "CUSTOMER-1",
  deletedAt: ISODate("2026-11-14T00:00:00Z")
}
```

This does not satisfy physical-deletion requirements. When records must also disappear from Search, filter and verify current state/permissions.

## 20. Observability and Incident Detection

A production security review must confirm **you can detect when the system starts misbehaving**.

### 20.1. Metrics to Alert On

- Unusual spikes in authentication failures;
- Connection attempts from unfamiliar networks;
- Unscheduled user/role changes;
- Anomalous CPU/disk/IOPS;
- Sudden connection spikes;
- Replication lag;
- Election/primary flapping;
- Low disk space;
- Backup job failures;
- Overdue restore tests;
- Expiring TLS certificates;
- KMS errors/denials;
- Audit logging pipeline failures;
- Sudden spikes in query/export volumes;
- Search index sync lag or stale permissions;
- Overdue secret rotation.

### 20.2. Every Alert Needs an Owner

An alert without an on-call owner, escalation path, and runbook is just noise.

Every critical alert needs:

```text
Signal
   │
Threshold / condition
   │
Owner/on-call
   │
Runbook
   │
Escalation
   │
Post-incident review
```

### 20.3. Do Not Introduce Vulnerabilities via Monitoring

If an exporter uses database credentials, treat it as a security-sensitive client:

- Least privilege;
- TLS;
- Private network;
- Secret rotation;
- Never export PII;
- Dashboard access control;
- Log retention;
- TLS between exporter and monitoring backend where needed.

## 21. Read-Only Verification Commands in `mongosh`

These commands help **gather evidence**, though they do not constitute a complete security assessment. They require appropriate privileges and must run only in authorized environments.

### 21.1. Server Version

```javascript
db.version();
```

### 21.2. Session Auth and Roles

```javascript
db.runCommand({
  connectionStatus: 1,
  showPrivileges: true
});
```

Never post raw output to public tickets; extract only redacted essentials.

### 21.3. Self-Managed Startup Options

With admin privileges:

```javascript
db.adminCommand({
  getCmdLineOpts: 1
});
```

Output can contain sensitive config paths and metadata; **never paste the entire output externally**. Inspect groups such as:

- `net.bindIp`;
- `net.tls`;
- `security.authorization`;
- `security.keyFile`;
- Configured file paths.

Not every runtime parameter appears identically across deployments. On Atlas, many properties are service-managed and must be verified via **Atlas configuration/console/API** rather than inferred from this command.

### 21.4. Inspect Indexes

```javascript
db.getSiblingDB("app").orders.getIndexes();
```

Indexes support performance and scoped uniqueness, **but do not prove the database is securely configured**.

### 21.5. Inspect Replication

```javascript
rs.status();
```

Run only in a replica set context with proper rights. Reports availability and topology, not a full security audit.

### 21.6. Inspect Search Indexes

If using MongoDB Search on a supported version:

```javascript
db.getSiblingDB("app").knowledge.aggregate([
  {
    $listSearchIndexes: {}
  }
]);
```

Search index status is part of operational readiness. Review mappings, permissions, and data freshness separately.

### 21.7. Never Run Mutating Commands in Automated Preflights

An “audit” script must never execute:

```javascript
db.dropDatabase();
db.orders.deleteMany({});
db.grantRolesToUser("app", [{role:"root", db:"admin"}]);
```

These are **high-impact mutating commands**, not read-only checks. Never run them in readiness scripts; they illustrate actions strictly excluded from read-only preflight tooling.

## 22. Preflight Evidence: What to Verify from Which Source?

Practical verification matrix:

| Area | Evidence Source | PASS Condition |
|---|---|---|
| Network exposure | Firewall/SG/Atlas IP access list | Only approved networks allowed |
| Private connectivity | VPC/endpoint configuration | Uses private path where required |
| TLS | URI/driver config, cert inspection | `requireTLS` and cert/hostname verified |
| Authentication | Deployment config and connection test | No anonymous access |
| RBAC | User/role privilege review | No excess privileges |
| Internal auth | Node config/topology evidence | Members authenticate properly |
| Secret storage | Vault/IAM/CI config | No hardcoded/broadly readable secrets |
| Encryption at rest | Atlas/OS/KMS settings | Matches data policy |
| Audit logging | Config + sample event | Captures mandatory events |
| Backups | Backup jobs/retention | Schedule, storage, encryption verified |
| Restores | Restore drill report | RPO/RTO measured |
| Patch level | Version inventory/advisories | No missing mandatory patches |
| Monitoring | Dashboards/alerts/on-call | Critical alerts have owners |
| Tenant isolation | Automated security tests | No cross-tenant leaks |
| Search/CDC | Index/connector configs and tests | No leaks via data projections |
| DR | Runbook + simulation | Documented plan and evidence |
| Ownership | Service catalog | Named owners and escalation |

This is a **release readiness table**, not a claim that a single screenshot proves controls work end-to-end.

## 23. Pre-Go-Live Review Sequence

A structured workflow:

```text
Inventory & classify data
           │
           ▼
Threat model / trust boundaries
           │
           ▼
Network & TLS
           │
           ▼
Authentication & RBAC
           │
           ▼
Secrets / encryption / key management
           │
           ▼
Backups / restore / DR
           │
           ▼
Logging / audit / monitoring
           │
           ▼
Application authorization tests
           │
           ▼
Operational readiness & patching
           │
           ▼
Evidence review + release decision
```

**If a BLOCKER is found**, never proceed assuming “we'll fix it later”. You may finish remaining read-only checks, yet go-live must remain blocked until remediated or granted a formal policy exception.

### 23.1. Every Finding Needs an Owner

A finding record should include:

```text
Finding ID: SEC-MONGO-001
Environment: Production
Component: MongoDB Network Access
Severity: BLOCKER
Observed: Public access rule wider than approved
Evidence: Redacted config snapshot + timestamp
Risk: Untrusted network may reach database endpoint
Owner: Platform Team
Remediation: Restrict access and verify from approved/unapproved networks
Target date: Before release
Verification owner: Security reviewer
Status: OPEN
```

Never put passwords, keys, or overly sensitive details inside finding tickets.

## 24. Detailed Atlas Production Checklist

For Atlas, review by category:

### 24.1. Organization and Project

- Dedicated project for production, separate from dev/staging;
- Admin/user roles follow least privilege;
- SSO/MFA enforced for human operators;
- API keys/service identities properly scoped;
- No departed staff retain access;
- Alerts configured for unwanted access changes;
- Project activity audited per Atlas capabilities.

### 24.2. Cluster

- Tier fits workload and security features;
- Region/data residency approved;
- Backup/PITR settings aligned with tier;
- HA/failure domains meet SLOs;
- MongoDB version/patch level and upgrade schedule tracked;
- Search Nodes (if used) properly sized and protected;
- Monitoring active.

### 24.3. Network and Identities

- IP access list is not overly broad;
- Private connectivity active if mandated by policy;
- Database users/roles follow least privilege;
- No shared admin account used by apps;
- Connection strings/credentials stored in secret store;
- Stale permissions revoked;
- Connectors and BI accounts reviewed.

### 24.4. Data

- Data classifications complete;
- Encryption at rest / customer-managed KMS enabled if needed;
- Default TLS verified properly;
- Retention configured for backups/logs/exports;
- Search/Vector mappings exclude unnecessary sensitive fields;
- Deletion/DSR runbooks ready if needed;
- Tenant isolation tests passing.

## 25. Detailed Self-Managed Production Checklist

For self-managed, additionally review:

### 25.1. Host and Service

- OS hardened and patched;
- Database runs under dedicated service account;
- Data/log/key directories have strict permissions;
- Firewalls and private routing enforced;
- No unnecessary services or open ports;
- No insecure debug interfaces;
- NTP/time sync configured;
- Filesystem and disk encryption active;
- Monitoring and backup agents use dedicated identities.

### 25.2. MongoDB Config

- `security.authorization: enabled` per topology;
- Internal authentication (`keyFile`/X.509) configured properly;
- `net.tls.mode: requireTLS` or approved equivalent policy;
- Valid certificate SAN/CA without bypassing verification;
- `bindIp` not overly broad;
- Replica set/shard/config server auth and networking verified;
- No leftover temporary dev configurations;
- No unused users or roles;
- Logging/auditing matches edition features and policy;
- Backups and restores tested.

### 25.3. Data Directories and Host Access

Anyone able to read **data files, snapshots, or process memory** bypasses database-level RBAC. Thus MongoDB RBAC does not replace OS/filesystem access control; SSH, `root`, and volume-snapshot accounts must also be reviewed.

## 26. Failure Scenarios and How to Assess Them

### Scenario A — Authentication Disabled

```text
MongoDB is internal-only
security.authorization: disabled
Firewall allows all machines on VPN
```

Conclusion: Insufficiently secure. “Inside the VPN” does not restrict per-user or per-service permissions. This is normally a **BLOCKER** for production holding real data.

### Scenario B — TLS Enabled, Hostname Verification Skipped

```text
tls=true
tlsAllowInvalidHostnames=true
```

Conclusion: Traffic is encrypted, **yet server identity is unverified**. Fix certs/SAN/CA; never mark PASS.

### Scenario C — Application Uses `root`

```text
API service
  MongoDB user roles: root@admin
```

Conclusion: Any API vulnerability or leaked credential compromises the entire cluster. Provision a narrowly scoped service identity; this is an over-privilege finding.

### Scenario D — Backups Exist, Never Restored

```text
Backup job status: SUCCESS
Last restore test: never
```

Conclusion: RPO/RTO attainment is unproven. Backups **must not be marked fully PASS**.

### Scenario E — Search Returns Revoked Data

```text
T1: Document ACL revoked
T2: MongoDB source updated
T3: Search index not yet synced
T4: API returns content from Search
```

Conclusion: Broken authorization despite valid user login. Add an authoritative ACL check before returning content.

### Scenario F — Replica Set Only, No Backups

```text
Three replica set members
No independent backup
```

Conclusion: Replica sets do not protect against replicated deletions, business bugs, or privileged ransomware. Recoverability is unmet.

### Scenario G — Credentials Printed in CI Logs

```text
CI step prints MONGODB_URI
Logs readable project-wide
```

Conclusion: Credential exposure. Revoke/rotate the leaked secret, restrict/purge logs per policy, and fix the pipeline. Never just silence the print statement while keeping the old secret.

### Scenario H — User Guesses Another Tenant's `_id`

```text
GET /orders/ORDER-B
Backend query: {_id:"ORDER-B"}
```

Conclusion: Missing tenant/owner checks in the endpoint is an application authorization flaw. Database passwords do not stop authenticated end users from exploiting IDORs.

## 27. Readiness Report Template for Projects

A concise review report structure:

```text
MONGODB PRODUCTION SECURITY REVIEW

Environment:
Deployment type:
MongoDB Server / FCV:
Application release:
Review date:
Reviewer:
System owner:

CONTROL RESULTS
[ ] Network isolation
[ ] TLS and certificate validation
[ ] Database authentication
[ ] RBAC / least privilege
[ ] Internal member authentication
[ ] Secrets and rotation
[ ] Encryption at rest / key management
[ ] Application tenant isolation
[ ] Backup retention / restore test
[ ] Audit / log redaction
[ ] Monitoring / on-call
[ ] Server/driver patch level
[ ] Search/Vector/CDC permissions (if used)
[ ] Data retention/deletion policy
[ ] Disaster recovery runbook

Findings:
  - Finding ID:
    Severity:
    Evidence:
    Owner:
    Remediation:
    Status:

Release decision:
  GO / NO-GO / CONDITIONALLY APPROVED

Approval:
  Service owner:
  Security owner:
  Platform/DBA:
```

In regulated environments, add signatures, evidence versions, approval cadence, and audit artifacts per organizational policy.

### 27.1. Recommended GO Criteria

Approve GO only when:

1. Zero **BLOCKER** findings remain.
2. HIGH findings are resolved or covered by time-bound policy exceptions.
3. Evidence specifies dates and the exact deployment.
4. Recovery was tested and meets RPO/RTO.
5. Auth/TLS/network/least privilege are verified.
6. Tenant/field-level access is tested on realistic fixtures or data.
7. On-call, runbooks, and rollback plans exist.
8. Owners are assigned for secrets, backups, and audits.

A checklist saying “all OK” with zero evidence may aid coordination, yet is insufficient for a technical security review.

## 28. Practical Exercises

### Exercise 1 — Identify Blockers

The operations team has the following configuration:

```yaml
net:
  bindIp: "0.0.0.0"
  port: 27017
security:
  authorization: disabled
```

1. Identify at least three risks.
2. Why is a firewall mandatory yet insufficient?
3. What conditions must be met before go-live?
4. Can this be fixed simply by enabling TLS?
5. Propose a safe sequence for transitioning to authentication and TLS.

### Exercise 2 — TLS Verifying the Right Hostname

A Java app connects successfully using:

```text
tls=true&tlsAllowInvalidCertificates=true
```

1. Why is “connection succeeds” not proof of security?
2. What are the certificate chain and SAN requirements?
3. How should the CA/truststore be managed?
4. What tests should be run before deployment?
5. What is the risk of a custom `TrustManager` that accepts every certificate?

### Exercise 3 — Design RBAC for Three Services

Given:

- Catalog Reader only views published products;
- Order API reads/writes `orders`;
- Reporting worker only generates summary reports.

Propose dedicated database users/roles, specify which privileges are withheld, and explain why **row-level authorization** must still be handled in the application.

### Exercise 4 — Review Atlas Access

An Atlas project has:

```text
IP Access List:
  0.0.0.0/0
  Office old IP
  Production NAT IP
```

1. Which entry is concerning?
2. If you remove allow-all immediately, what impact could it have on the app?
3. How should network paths be verified before making changes?
4. When should a private endpoint be used?
5. Who should approve the change?

### Exercise 5 — Replica Set Keyfile

A replica set has three members, and the keyfile is stored inside the Docker image.

1. What is the primary risk?
2. Which secret distribution approach should be used instead?
3. How do you rotate keys without losing quorum?
4. Why must you not restart all three members simultaneously?
5. How does internal authentication differ from client authentication?

### Exercise 6 — Backups Without Restore Drills

The system requires RPO = 15 minutes and RTO = 2 hours, yet only runs daily backups.

1. Can the RPO target be met?
2. How should PITR/oplog coverage be factored in?
3. What should a restore drill measure?
4. How does key management affect restores?
5. If rebuilding the Search index takes a long time, does that affect RTO?

### Exercise 7 — Lock Down Cross-Tenant Access

API:

```javascript
db.orders.findOne({ _id: request.params.orderId });
```

1. What goes wrong when `orderId` is guessable?
2. Where should the tenant predicate be added?
3. Which source should `tenantId` come from?
4. Should owner/team roles also be checked?
5. Write three integration tests to prevent regressions.

### Exercise 8 — Secret Leak

A developer accidentally committed `MONGODB_URI` containing a password to the repository.

1. Is reverting or deleting just the latest commit enough?
2. How must the secret be revoked and rotated?
3. How do you assess impact across logs and CI?
4. How do secrets scanners and repository protections help?
5. How do you prevent repeat mistakes?

### Exercise 9 — Audit Monitoring Account Privileges

A metrics exporter currently uses the `root` user.

1. Why is this inappropriate?
2. Which observability privileges does it need?
3. Does it need write permissions on business data?
4. How should the exporter's credentials and TLS be handled?
5. Does the metrics endpoint itself require network/auth controls?

### Exercise 10 — Prove Backups Are Recoverable

Design a restore drill:

1. Which backup artifact do you select?
2. Where do you restore it?
3. How do you verify users, roles, and encryption keys?
4. How do you run data integrity checks and application smoke tests?
5. How do you record RPO/RTO results?
6. Who signs off on the outcome?

### Exercise 11 — Search Index and Stale ACLs

A document has been switched from public to private, yet the Search index has not synced yet.

1. Can pre-filtering return stale results?
2. At which stage do you place the post-check?
3. May unverified candidates be sent to an external LLM before the post-check?
4. When the authorization service fails, should it fail open or fail closed?
5. How must caches be handled?

### Exercise 12 — Data Lifecycle

A user requests deletion of their personal data.

1. Which data copies must be checked?
2. Does a TTL index guarantee deletion at the exact millisecond?
3. Can change stream pre-images contain old data?
4. How does backup retention factor into this?
5. What evidence does the completion verification workflow require?

### Exercise 13 — Release Gate Table

Create a table with at least 10 controls:

```text
Control | Evidence | Owner | Status | Severity | Decision
```

Assign at least three simulated findings. Decide GO or NO-GO and justify your reasoning.

### Exercise 14 — Java Connection Security

Review code calling `MongoClients.create(uri)`:

1. Where is the URI read from?
2. Could secrets be logged?
3. Is TLS verification intact?
4. Is `authSource` correct?
5. Is the `MongoClient` lifecycle appropriate?
6. Are timeouts and monitoring configured?

### Exercise 15 — Securing Self-Managed Kubernetes

A MongoDB deployment in Kubernetes uses:

- Containers running as `root`;
- A public `LoadBalancer` Service;
- Secrets mounted into all pods;
- No `NetworkPolicy`;
- No backups.

1. Identify the blockers;
2. Propose network isolation and pod security settings;
3. Design scoped secret access;
4. Outline a backup/restore plan;
5. What should readiness probes and rolling updates avoid?

### Exercise 16 — Threat Modeling for a Production System

Model:

```text
Browser → API → MongoDB Atlas
                 │
                 ├── Vector Search → RAG
                 ├── CDC → Data Warehouse
                 └── Backup → Object Storage
```

Identify:

1. Trust boundaries;
2. Data flows containing PII;
3. Identity of each service;
4. Network and TLS controls;
5. ACL re-check before RAG;
6. Permissions for CDC/warehouse;
7. Backup encryption and retention;
8. Auditing and incident response.

## 29. Handover Checklist for Operations Teams

### Access and Infrastructure

- [ ] Inventory lists owners, versions, regions, and data classifications.
- [ ] No public DB exposure outside approved scope.
- [ ] Atlas IP access list, firewalls, and security groups reviewed.
- [ ] Private connectivity used where required.
- [ ] TLS mandatory, certificates and hostnames verified.
- [ ] No `tlsInsecure` or bypassed certificate checks.
- [ ] Database authentication enabled per topology.
- [ ] Internal member authentication configured properly.
- [ ] Human admins enforce MFA/SSO per policy.
- [ ] Service identities separated and scoped to least privilege.
- [ ] No stale or unowned users/roles remain.

### Data and Keys

- [ ] Secrets stored in an approved secret store—never in repos, images, or logs.
- [ ] Key and password rotation plan exists.
- [ ] Encryption at rest matches data sensitivity and deployment model.
- [ ] Key backup/restore plan tested.
- [ ] Client-side encryption used within documented limits if enabled.
- [ ] Retention and deletion policies clearly defined.
- [ ] Data exports, analytics, Search, Vector Search, and CDC all reviewed.
- [ ] Schema validation and tenant ACL tests have recorded evidence.

### Resilience and Observability

- [ ] Backups run automatically and are monitored.
- [ ] Restore drills meet committed RPO/RTO.
- [ ] Backups reside outside the primary failure domain and are tamper-protected.
- [ ] MongoDB server and driver versions patched per policy.
- [ ] HA, failover, and recovery tested in staging.
- [ ] Audit logs genuinely capture mandatory events.
- [ ] Logs exclude credentials and unnecessary PII.
- [ ] Alerts have on-call owners and runbooks.
- [ ] Incident-response and rollback plans exist.
- [ ] Search indexes and derived data have post-restore rebuild plans.
- [ ] All BLOCKER findings closed prior to go-live.

## 30. Official Documentation References

Cross-check against official MongoDB and Atlas documentation matching the **exact version, tier, and environment** in use:

- [MongoDB Security Checklist](https://www.mongodb.com/docs/manual/administration/security-checklist/)
- [MongoDB Security Overview](https://www.mongodb.com/docs/manual/security/)
- [Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/)
- [Authentication](https://www.mongodb.com/docs/manual/core/authentication/)
- [Enable Access Control](https://www.mongodb.com/docs/manual/tutorial/enable-authentication/)
- [TLS/SSL Configuration](https://www.mongodb.com/docs/manual/tutorial/configure-ssl/)
- [Internal Authentication / Keyfile](https://www.mongodb.com/docs/manual/tutorial/enforce-keyfile-access-control-in-existing-replica-set/)
- [MongoDB Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/)
- [Audit Messages](https://www.mongodb.com/docs/manual/reference/audit-message/)
- [MongoDB Atlas Security](https://www.mongodb.com/docs/atlas/security/)
- [Atlas Network Access](https://www.mongodb.com/docs/atlas/security/ip-access-list/)
- [Atlas Private Endpoints](https://www.mongodb.com/docs/atlas/security-private-endpoint/)
- [MongoDB Atlas Backups](https://www.mongodb.com/docs/atlas/backup/cloud-backup/overview/)
- [MongoDB Encryption at Rest](https://www.mongodb.com/docs/manual/core/security-encryption-at-rest/)
- [Queryable Encryption](https://www.mongodb.com/docs/manual/core/queryable-encryption/)
- [MongoDB Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB Search](https://www.mongodb.com/docs/search/)
- [MongoDB Vector Search](https://www.mongodb.com/docs/vector-search/)
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)

## Conclusion

**Pre-production MongoDB configuration review** is not a single `db.adminCommand()` call or a “template” `mongod.conf` file. It is an end-to-end verification of **every data flow and access path**.

Foundational controls that must be confirmed include: **network isolation, TLS with certificate verification, authentication, least-privilege RBAC, internal member authentication, secrets management, data encryption, logging/auditing, tested backups and restores, patching, monitoring, and application-level authorization**. With Atlas, the organization still owns identities, network rules, and data policies; with self-managed deployments, operations must additionally protect hosts, processes, TLS/keyfiles, and cluster topology.

A deployment can have three replica set members, TLS enabled, and fast queries yet still be unsafe if **the API runs as `root`, one tenant can read another tenant's documents, or backups fail to restore**. Features like Search/Vector Search and CDC demand extra scrutiny because indexes and derived copies can hold sensitive data while syncing behind live access permissions.

**Approve GO-LIVE only when mandatory items have passing evidence, zero blockers remain, owners are assigned, recovery is proven, and incident observability is active. MongoDB security is a property of the entire operating system, not just the database engine.**
