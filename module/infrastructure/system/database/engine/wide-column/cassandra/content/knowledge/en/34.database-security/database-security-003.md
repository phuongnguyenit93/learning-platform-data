# Authentication/Authorization and Version-Specific Configuration

## 1. Why Can a Cassandra Cluster with Healthy Replication Still Be Insecure?

**Apache Cassandra** is designed to distribute partitions by token, place multiple replicas according to replication factor (RF), and satisfy reads/writes according to consistency level (CL). These mechanisms support availability and durability, but **do not decide who is allowed to read, modify, or delete data**.

For example, a telemetry service has three replicas in `dc1`, using `LOCAL_QUORUM`. If the cluster allows CQL connections without authentication, anyone with network access to the native protocol port can attempt queries prohibited by enterprise policy. **RF = 3 and `LOCAL_QUORUM` do not prevent unauthorized access**. Likewise, if an application account has superuser rights, leaking connection credentials can lead to schema modification, data deletion, or role tampering.

This lesson in the **Security** chapter focuses on **authentication**, **authorization**, and **version-specific Cassandra configuration differences**, while connecting them to TLS, JMX, the Java Driver, replication of security data, auditing, and troubleshooting.

**After this lesson, you will be able to:**

1. Distinguish authentication, authorization, transport encryption, and auditing — four layers that do not substitute for one another.
2. Understand the roles of `Authenticator`, `Authorizer`, `RoleManager`, role membership, and CQL permissions.
3. Design **least-privilege** roles for Java services, data analysts, and migration teams.
4. Explain why the `system_auth` keyspace must be cared for, especially in multi-datacenter clusters.
5. Know how to cross-check the **Cassandra version, actual configuration, and client tools** rather than copying a sample `cassandra.yaml` file.
6. Practice CQL RBAC, Java Driver 4.x connections with TLS, and verify both permitted and denied cases.
7. Plan how to enable authentication/authorization, rotate credentials, monitor, and recover from misconfigurations.

**Academic scope:** examples assume Cassandra uses standard full replicas and `NetworkTopologyStrategy`; the DC name is `dc1`. Authentication classes/plugins, TLS options, logging systems, additional permissions, credential provisioning methods, and defaults vary across Cassandra **3.x, 4.x, 5.x** as well as vendor distributions. Any sample configuration must be verified against the **deployed version**, never applied directly to production.

## 2. Four Distinct Security Questions

| Question | Mechanism | Example | What That Mechanism Does **Not** Do by Itself |
| --- | --- | --- | --- |
| **Who are you?** | **Authentication** | CQL connection uses username/password or a supported authentication mechanism. | Does not decide which tables the user may view. |
| **What are you allowed to do?** | **Authorization** | Role `events_reader` holds `SELECT` on exactly one table. | Does not encrypt passwords traveling over the network. |
| **Can data be read/tampered with in transit?** | **Transport security/TLS** | Client-to-node TLS and internode encryption. | Does not replace role policies; a TLS connection can still have overly broad permissions. |
| **Who did what, and when?** | **Audit/monitoring** | Records actor, CQL action, UTC timestamp, outcome, and change ID. | Does not prevent an action if permissions still allow it; does not replace backups. |

A secure system combines layers. Enabling **PasswordAuthenticator** while letting clients connect over unencrypted connections increases secret-exposure risk; enabling TLS while leaving **AllowAllAuthorizer** allows every connected user to perform broader operations than intended.

### 2.1. Four Common Identity Types

- **Java applications:** each service/workload has its own identity, with least privilege on only required keyspaces/tables.
- **Automation/migration:** dedicated identity for schema changes or maintenance tasks, with approval and time bounds.
- **Operators:** individual human identities via identity management/bastion, optionally granted temporary task-scoped privileges.
- **Node administration paths:** identities used for SSH, container/orchestrator, JMX, or backups; **separate from the CQL channel**.

**Do not use one superuser account for all four groups.** If everyone shares a single password, you cannot revoke a single workload independently or attribute responsibility accurately during an incident.

## 3. Authentication and Authorization Architecture in Cassandra

~~~mermaid
flowchart TD
    A["Java Driver / cqlsh"] --> B["Native protocol connection over TLS"]
    B --> C["Authenticator: verify identity"]
    C --> D{"Valid login?"}
    D -->|No| E["Authentication error"]
    D -->|Yes| F["RoleManager: role, login, membership"]
    F --> G["Authorizer: effective permissions on CQL resources"]
    G --> H{"Operation permitted?"}
    H -->|No| I["Unauthorized / permission denied"]
    H -->|Yes| J["Coordinator processes CQL and contacts replicas"]
    J --> K["Data in business keyspace"]
    L["system_auth and related metadata/caches"] -.-> C
    L -.-> F
    L -.-> G
    M["Audit / server logs / metrics"] -.-> C
    M -.-> G
    M -.-> J
~~~

Each component has distinct responsibilities:

- **`Authenticator`** verifies identity at connection establishment; common setups in Apache Cassandra use `PasswordAuthenticator` or another version-supported mechanism. `AllowAllAuthenticator` means there is no password-style CQL authentication check.
- **`Authorizer`** determines whether an action on a resource is permitted; `CassandraAuthorizer` uses Cassandra's permission system. `AllowAllAuthorizer` is not a least-privilege production configuration.
- **`RoleManager`** manages roles, `LOGIN`, `SUPERUSER` flags, authentication credentials, and role inheritance relationships. `CassandraRoleManager` is a common choice.
- **Network/DC restriction mechanisms or advanced plugins** may exist in certain versions/distributions. They supplement policy, without replacing CQL resource permission checks.

**Session note:** Authentication typically occurs when a connection is established; authorization may use caches. Revoking a role/password **does not guarantee all open connections are disconnected immediately**. Rotation and emergency revocation policies must account for connection pools, cache TTLs, and reconnections.

## 4. Version-Specific Configuration: Principles and Comparison Table

### 4.1. Why Not Copy Any Random `cassandra.yaml` File?

When reading online documentation, you may encounter configurations meant for Cassandra 3.11, 4.0, 4.1, 5.x, commercial distributions, or operator-managed environments. Even when using the same term "authentication," variants can differ in:

- **Default values** for authenticator, authorizer, TLS, and sample configs.
- **Key names** in `cassandra.yaml`, JVM properties, and dynamic reload capabilities.
- **Network/DC authorization mechanisms**, role management, certificate authentication, or extension plugins.
- **Audit logging styles**, detail/retention levels, and performance impact.
- **How TLS is configured** for native transport, internode, JMX, clients, and how truststores/keystores are handled.
- **Authorization/credential caches**, TTL intervals, and refresh mechanisms.

Therefore, deployment documentation must start with the **running version**, distribution, installation form (bare metal, VM, container/operator), and current configuration state.

### 4.2. Version-Line Orientation Table

| Scope | What You May Find | What to Verify for the Exact Release |
| --- | --- | --- |
| **Apache Cassandra 3.x** | Role/password-based auth and CQL permissions, `PasswordAuthenticator`, `CassandraAuthorizer` in applicable releases. | Documentation for the exact minor release; how TLS/JMX are enabled, external audit or available logging mechanisms, role metadata caches. |
| **Apache Cassandra 4.0/4.1** | Role/permission mechanisms continue; additional operational, logging, and security option changes compared to 3.x. | Cache property names, audit logging, extended network/DC authorization capabilities, and specific TLS mechanisms. |
| **Apache Cassandra 5.x** | The role/permission model remains foundational; certain policy features and advanced plugins continue to evolve. | Supported auth plugin types, TLS/JMX, defaults, renamed/deprecated keys, and client/driver compatibility. |
| **Managed/vendor/operator editions** | May use identity, certificates, IAM, secrets, and policies from the platform. | What is provider-managed, which permissions are tenant-controlled, and which config/`nodetool` commands are restricted. |

This table is **not a feature-guarantee matrix**. For example, never assume "every 4.x release has the exact same audit/network authorization features" or "TLS configs in 3.11 and 5.x are identical." If security documentation does not state a **version**, treat it as a **hint to verify**, not a ready runbook.

### 4.3. Illustrative Core Configuration Pattern

Many Cassandra deployments rely on entries similar to the following in `cassandra.yaml`:

~~~yaml
# CONCEPTUAL EXAMPLE — DO NOT copy to production without checking version.
authenticator: PasswordAuthenticator
authorizer: CassandraAuthorizer
role_manager: CassandraRoleManager
~~~

These are **three distinct mechanisms**, not three aliases for one feature. Some environments use custom providers, proxies, or plugins instead of password auth. Some settings require a **restart/rolling restart** and must be prepared ahead of time; never change all nodes in a cluster simultaneously without a plan to preserve quorum and emergency access.

**Do not conclude the cluster is safe just by seeing those three lines.** You must verify enforced CQL permissions, TLS, `system_auth`, JMX ports, superuser identities, auditing, and OS access paths.

## 5. The `system_auth` Keyspace: Security Data Also Needs Replication and Repair

With built-in auth mechanisms, Cassandra stores roles, protected passwords, and permissions in the **authentication-related system keyspace**, usually `system_auth`. It is distributed data serving logins and authorization decisions, not a single password file on one node.

**Consequence:** if `system_auth` has too weak an RF or replica placement, a node/DC failure can impair **the ability to open new connections or evaluate permissions**, even if business data keyspaces still have enough replicas.

### 5.1. Never Neglect Per-DC RF

For example, consider a cluster with:

~~~text
Datacenter dc1: 3 nodes
Datacenter dc2: 3 nodes
Business keyspace: NetworkTopologyStrategy {dc1: 3, dc2: 3}

Additional checks required:
  Does system_auth have suitable RF and replica placement in both DCs?
  Have new system_auth replicas received all role/permission data?
  If dc1 goes down, can clients in dc2 still log in under actual CL/caching?
~~~

Check replication metadata:

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name IN ('system_auth');
~~~

This query only shows **replication metadata**; it does not prove every `system_auth` replica has received existing data. If RF must be changed, you need **data planning and repair/streaming** for that keyspace, not just metadata edits. Experimenting with `system_auth` risks locking administrators out of the cluster; never change it casually in production.

### 5.2. What Happens When Changing `system_auth` RF?

In CQL, changing a keyspace's replication uses `ALTER KEYSPACE`; illustrative example **for reading comprehension only**:

~~~sql
-- ILLUSTRATIVE; do not run without a runbook/backup and topology verification.
ALTER KEYSPACE system_auth
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3,
  'dc2': 3
};
~~~

Conditions for such a configuration to make sense:

1. Both DCs **actually exist** with the exact names reported by the snitch, with enough nodes/racks for the target.
2. There is a safe change plan matching the running Cassandra **version** and required `ALTER` permissions.
3. After RF metadata changes, existing role/permission data must be **synchronized to new natural replicas** via the appropriate repair/streaming procedure.
4. Verified logins, effective permissions, sessions, and connectivity **in each DC** after the change.
5. A recovery plan for credentials and `system_auth` data exists if the change fails.

**Never run `TRUNCATE system_auth` or directly edit internal tables** to "reset a password" after losing access. System table schemas, bootstrap credentials, and recovery tools vary by version; use an approved runbook.

### 5.3. Caching Can Make Permissions Appear Slow to Update

To avoid reading role/permission data on every request, Cassandra can cache credentials, roles, and permissions. Consequently:

- A successful `GRANT` or `REVOKE` does not guarantee all nodes apply the result at the exact same speed.
- A newly joined node, a recently restarted node, or a client with an existing connection may behave differently during cache convergence.
- Options named like `credentials_validity_in_ms`, `roles_validity_in_ms`, or `permissions_validity_in_ms` may exist depending on version, but **defaults and behavior must be verified**.
- For **emergency permission revocation**, do not passively wait for cache TTLs; execute procedures to close sessions, revoke credentials, block network access, and verify effective privileges according to version capabilities.

Caching optimizes performance; it **does not replace policy enforcement and post-change verification**.

## 6. CQL RBAC: Resources, Permissions, and Role Membership

### 6.1. Foundational CQL Permissions

| Permission (Common) | General Meaning | Scope Examples |
| --- | --- | --- |
| `SELECT` | Read data. | A table or keyspace. |
| `MODIFY` | Permitted data changes, including write/delete operations within scope. | Tables requiring writes. |
| `CREATE` | Create a matching resource/schema type. | Keyspace, table, or supported resource. |
| `ALTER` | Modify structure or resource attributes. | A table, keyspace, or eligible role. |
| `DROP` | Drop the granted resource. | Matching table/keyspace/role. |
| `AUTHORIZE` | Grant/revoke permissions within permitted resource scope. | A table/keyspace/role. |
| Additional permissions like `DESCRIBE`, `EXECUTE` | May apply to specific resources, functions, or version-specific features. | Must check exact version. |

Permissions follow the **resource hierarchy** and can be granted at multiple scopes: table, keyspace, all keyspaces, role, all roles, or other version-supported objects. A role with `SELECT` at the **keyspace** level can read more tables than a role with `SELECT` on **one table**.

**Avoid using `GRANT ALL PERMISSIONS` for applications** unless there is an approved reason and exact understanding of the resource/version. In particular, `AUTHORIZE` or role-admin rights can let one identity grant further permissions to another identity.

### 6.2. Roles Can Be Non-Login

Group roles such as `events_reader` are typically created with:

~~~sql
CREATE ROLE IF NOT EXISTS events_reader
WITH LOGIN = false
AND SUPERUSER = false;
~~~

`LOGIN = false` makes the role act as a **permission group**, not a user that connects directly. Actual login identities can be provisioned by security/secrets tooling and assigned the group role. `SUPERUSER = false` keeps privileges ordinary; **superuser is never needed** just to read a table.

### 6.3. Role Membership Does Not Mean Two Accounts Share a Password

Suppose login account `telemetry_api_identity` **already exists**, created and credential-managed by a provisioning system:

~~~sql
-- Administrator runs commands in a lab environment with authorizer enabled.
GRANT events_reader TO telemetry_api_identity;

-- Inspect role membership and effective permissions per applicable version.
LIST ROLES OF telemetry_api_identity;
LIST ALL PERMISSIONS OF telemetry_api_identity;
~~~

Here, the login identity **inherits permissions** from the group role without needing to share any group password. When role membership changes, check all inheritance paths; `REVOKE events_reader FROM telemetry_api_identity` only removes that membership, **not direct permissions or other roles** the identity holds.

## 7. Safe Lab: Grant `SELECT` on One Table, Verify `MODIFY` Is Denied

### 7.1. Create Keyspace and Table on a Lab Cluster

Suppose the lab has DC `dc1` with at least three full replicas, authentication/authorization enabled, and an authorized admin:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_secure
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_secure.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  payload text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

INSERT INTO telemetry_secure.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, payload)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T09:00:00Z',
   123e4567-e89b-42d3-a456-426614174001,
   'temperature', '21.5');
~~~

The partition key is `(device_id, event_day)`; the clustering key is `(event_time, event_id)`. This design enables device/day lookups, but **whether a query specifies the right partition key is unrelated to whether the identity holds `SELECT`**. Authorization checks **who may read the table**; token routing decides **which replicas to read from**.

### 7.2. Create a Group Role and Grant Only Read Access

~~~sql
CREATE ROLE IF NOT EXISTS telemetry_day_reader
WITH LOGIN = false
AND SUPERUSER = false;

GRANT SELECT ON TABLE telemetry_secure.events_by_device_day
TO telemetry_day_reader;

LIST ALL PERMISSIONS OF telemetry_day_reader;
~~~

Provision `readonly_lab_identity` through the lab's approved credential-provisioning mechanism. Once that identity exists:

~~~sql
GRANT telemetry_day_reader TO readonly_lab_identity;

LIST ROLES OF readonly_lab_identity;
LIST ALL PERMISSIONS OF readonly_lab_identity;
~~~

**Note:** if `readonly_lab_identity` already had direct `MODIFY` at the keyspace level or was already a superuser, the "read-only" test is meaningless. Start with a fresh lab identity having minimal rights and inspect actual memberships/permissions.

### 7.3. Test Logging In with the Read-Only Identity

Once connected using TLS and authenticated as the right identity, run:

~~~sql
CONSISTENCY LOCAL_QUORUM;

SELECT event_time, event_type, payload
FROM telemetry_secure.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21';
~~~

**Expected:** `SELECT` succeeds if the role is properly granted and `dc1` has enough replicas to satisfy CL.

Next, verify the case that **must be denied**, without running destructive actions on real data:

~~~sql
-- ONLY use in an isolated lab, with identity readonly_lab_identity.
-- Command must be denied when MODIFY is absent:
DELETE FROM telemetry_secure.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time = '2026-11-21T09:00:00Z'
  AND event_id = 123e4567-e89b-42d3-a456-426614174001;
~~~

If `DELETE` **succeeds**, that is a **sign of a permission misconfiguration** in the lab: check `authorizer`, the logged-in user identity, superuser status, role membership, and effective keyspace/table permissions. Do not immediately conclude Cassandra "ignored the role"; the test might have accidentally used an admin account.

**Post-check:** verify using the **real account**, across **multiple nodes/coordinators** if policy and distributed caching require it; cross-check audit logs. A passing `LIST ALL PERMISSIONS` does not replace an allow/deny execution test.

### 7.4. Revoke a Group Role Within Scope

When concluding the lab:

~~~sql
-- Administrator executes in the lab; do not modify production roles.
REVOKE telemetry_day_reader FROM readonly_lab_identity;
~~~

Do not arbitrarily run `DROP ROLE` if other identities still use the role. After `REVOKE`, check effective permissions and **cache/connection convergence time**; reconnect if necessary to verify policy on new connections.

## 8. Password Policy and Bootstrapping Administrative Access

### 8.1. The First Account Is a Governance Issue, Not Just CQL

When enabling `PasswordAuthenticator` and `CassandraAuthorizer`, the cluster must have a **valid way to create/manage the initial admin identity**. In some versions or default states, a well-known default bootstrap/superuser role may exist. Any such initial password must be handled **according to version documentation**:

1. Create/verify the permitted admin access path following the exact bootstrap sequence.
2. Set a strong credential over an encrypted channel; never send passwords in tickets/chat/logs.
3. Create **individually named** admin identities and verify they work before modifying the bootstrap identity.
4. Revoke/disable the default access path per an approved runbook; do not leave default credentials active for long.
5. Verify operation across **multiple nodes/DCs**, especially if `system_auth` recently changed RF or caches have not converged.
6. Prepare an audited **break-glass procedure** with independent approvers.

Never use sample passwords from documentation as real credentials. **Never log in as superuser to run application workloads.**

### 8.2. Why Not Put Passwords in CQL Scripts or Command Lines?

`CREATE ROLE ... WITH PASSWORD = '...'` may be valid syntax, but plaintext values can end up stored in:

- Migration files/source control or `cqlsh` history.
- Terminal scrollback, shell history, or process lists if the password is a CLI argument.
- Debug/audit logs or CI/CD output when scripts are echoed.
- Workspace backups or support documents.

If provisioning requires a password:

- Retrieve the value from a **secret manager/identity provisioning system**; only the least-privileged tool should see it.
- Use **TLS connections with server verification**, never sending plaintext over the network.
- Keep secrets out of argv, unencrypted files, and logs; restrict read permissions on provisioning tools.
- Rotate when personnel change or compromise is suspected; never share secrets across dev/staging/prod.
- Account for users/connection pools reconnecting when credentials change.

In environments supporting **certificates or identity federation**, consider them if supported by your version/distribution, without assuming every Cassandra setup supports the same plugins and configuration syntax.

## 9. TLS for Native Protocol and Internode: Separate from Authorization

**Native transport** is the path applications/`cqlsh` use to connect to Cassandra (commonly port `9042`). **Internode communication** is the path nodes use to exchange mutations, reads, gossip/streaming, and distributed state. Both channels require **separate TLS design**, typically corresponding to `client_encryption_options` and `server_encryption_options`, though **exact key names vary by version**.

~~~mermaid
flowchart LR
    A["Java client + truststore"] -->|"TLS native transport"| B["Node N1: coordinator"]
    B -->|"TLS internode if configured properly"| C["Node N2: replica"]
    B -->|"TLS internode if configured properly"| D["Node N3: replica"]
    E["CQL role/permission check"] -.-> B
    F["JMX admin channel: protected separately"] -.-> B
~~~

### 9.1. TLS Checkpoints

| Area | Mandatory Question |
| --- | --- |
| **Server identity** | Does the client validate the certificate chain, hostname/SAN, and trust anchors, or does it merely "encrypt while trusting any certificate"? |
| **Protocol/cipher** | Are only policy-approved protocol versions and cipher suites accepted? |
| **Certificate lifecycle** | Who issues, distributes, rotates, and revokes certificates? What happens if a cert expires during peak load? |
| **Client certificate/mTLS** | Does the version/config require client certificates? If so, what identity do they map to? |
| **Internode** | Do all node/rack/DC links requiring encryption actually use TLS? |
| **Mixed rollout** | Is there a transition window allowing unencrypted connections? Does it expire/lock down after rollout? |
| **Network exposure** | Are CQL/JMX/internode ports unnecessarily public; are firewalls and bastions enforced? |

**Never use a "trust-all" SSLContext, skip certificate checks, or disable hostname verification** to work around TLS handshake errors. Those "quick fixes" allow clients to connect to spoofed nodes.

### 9.2. Reference Configuration Expresses **Intent** Only, Not a Complete File

~~~yaml
# CONCEPTUAL; field names/structure/defaults must be checked on your Cassandra version.
# Two common configuration blocks in cassandra.yaml:
client_encryption_options:
  enabled: true
  # truststore/keystore, client_auth, certificate policy per version

server_encryption_options:
  # protect internode traffic (node-node, cross-DC) per version
  internode_encryption: all
~~~

Do not copy this block and expect TLS to work. It **does not contain certificate policies, key material, trust stores, ports, rollout strategies**, or version specifics. When enabling TLS, verify using **real client connections with valid certificates** and **internode paths**; seeing `enabled: true` is not enough.

**Encryption at rest** is a separate concern: TLS does not automatically encrypt SSTables, commit logs, hints, snapshots, or backups on disk. You need at-rest encryption policies, volume/key management, and backup protection commensurate with data sensitivity.

## 10. Java Driver 4.x: Authenticate the Right Identity and Reject Untrusted TLS

Java applications should connect using a **dedicated identity**, configured truststore, and accurate `localDatacenter`. Example using Apache Cassandra Java Driver 4.x:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.Objects;
import javax.net.ssl.SSLContext;

public final class SecureCassandraRead {
    public static void main(String[] args) throws Exception {
        // LAB ILLUSTRATION ONLY: secrets from env vars have security limits.
        // Production should integrate a secret manager and rotation workflow.
        String username = Objects.requireNonNull(
            System.getenv("CASSANDRA_APP_USER"), "missing username");
        String password = Objects.requireNonNull(
            System.getenv("CASSANDRA_APP_PASSWORD"), "missing password");

        // A valid truststore must be preconfigured in the JVM.
        // Never use a trust-all SSLContext.
        SSLContext tls = SSLContext.getDefault();

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("cassandra.lab.example", 9042))
                .withLocalDatacenter("dc1")
                .withAuthCredentials(username, password)
                .withSslContext(tls)
                .build()) {

            PreparedStatement query = session.prepare(
                "SELECT event_time, event_type " +
                "FROM telemetry_secure.events_by_device_day " +
                "WHERE device_id = ? AND event_day = ? LIMIT 20");

            BoundStatement read = query.bind(
                    "device-7", LocalDate.of(2026, 11, 21))
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            for (Row row : session.execute(read)) {
                System.out.println(row.getInstant("event_time")
                    + " " + row.getString("event_type"));
            }
        }
    }
}
~~~

**Explanation:**

1. `withAuthCredentials` uses a provisioned identity, **not** a superuser account. Each environment/service requires its own credentials.
2. `SSLContext.getDefault()` is only safe when the JVM has a **proper truststore and server validation policy**; by default it may not trust an internal CA and connections will fail — that signals fixing trust configuration, **not disabling TLS**.
3. Environment variables are convenient for demos but can be inspected via admin/process/container access. Production should use a **supported secret manager or identity provider**, never log values, and restrict config read access.
4. `cassandra.lab.example` is an example DNS name; real endpoints must match certificate SANs/hostnames and load-balancing policies.
5. `LOCAL_QUORUM` with RF = 3 in `dc1` requires **two replicas to respond**, but CL **does not grant permission** to read the table. Authorization is evaluated independently of replica quorum.
6. Never store `password` in log messages, metrics, exceptions, or traces. Java `String` objects are hard to scrub from memory, so control process lifecycles, heap dumps, and secret handling.
7. When using paging or retries, never turn authentication/authorization errors into infinite retry loops; those errors require fixing **credentials or permissions**, not increasing timeouts.

### 10.1. Separating Layers When Errors Occur

| Observed Error | What to Check |
| --- | --- |
| TLS handshake/certificate validation failure | Truststore, CA, SAN/hostname, expiration date, TLS protocol, proxies, and clock. |
| Bad credentials/authentication error | User, secret, authenticator mechanism, account `LOGIN`, `system_auth`, and caches. |
| Unauthorized/permission denied | `CassandraAuthorizer`, effective roles, resource/permission, membership, and caches. |
| `Unavailable` | RF/CL, node/DC, and replica health; **not** a password error. |
| Read/write timeout | Latency, I/O, GC, tombstones, network, replicas, and deadlines; **does not prove** missing permissions. |
| Connection refused/no route | Port, firewall, TLS listener, node service, and routing. |

**Do not automatically retry auth/authz errors at high frequency.** Retry storms generate extra log/CPU load and may trigger security lockouts; secret rotation or role updates must follow verified procedures.

## 11. CQL, JMX, and the OS: Three Privilege Surfaces to Evaluate Independently

`PasswordAuthenticator` and `CassandraAuthorizer` govern **native CQL** as configured. They **do not implicitly grant or revoke rights** across all administrative paths:

| Channel | Action Examples | Control Mechanism |
| --- | --- | --- |
| **CQL** | `SELECT`, `INSERT`, `ALTER KEYSPACE`, `GRANT`, `REVOKE`. | Cassandra authentication/authorization and role permissions. |
| **JMX / nodetool** | `repair`, `snapshot`, `cleanup`, `drain`, inspecting MBeans. | JMX authentication/authorization, TLS/network isolation, tool access controls. |
| **OS / SSH / container** | Editing `cassandra.yaml`, reading logs, viewing data directories, restarting nodes. | OS ACLs, sudo, SSH/IAM, container/orchestrator RBAC. |
| **Backup/storage** | Reading snapshots, downloading SSTables, deleting backups. | IAM, object storage policies, encryption key access, and retention. |

An identity blocked as **Unauthorized** in CQL can still cause damage if it has root SSH or unrestricted JMX access. Conversely, a CQL account with `SELECT` must never be assumed to have permission to run `nodetool status` on the host.

**Deployment principles:**

- Never expose JMX ports to untrusted networks; use bastions/firewalls and proper authentication.
- Do not run Cassandra under an overly privileged OS account unnecessarily.
- Separate JMX viewer roles, operational admin roles, and application CQL roles where the platform supports it; if JMX lacks fine-grained authorization, wrap it with an **automation allowlist** and approval.
- Never give CI/CD a shared password capable of `DROP` or `ALTER` across all keyspaces.
- Restrict access to logs, snapshots, and backups based on sensitive-data exposure risk.

## 12. Audit and Monitoring: Successful Authentication Does Not Equal a Secure System

A cluster may reject invalid logins yet still lack clear evidence of unexpected **permission changes**, **table drops**, or **JMX exposure**. Therefore, monitor:

| Signal Category | Questions to Answer | Notes |
| --- | --- | --- |
| Failed/successful authentication | Is there a spike in failed logins, expired credentials, or brute-force attempts? | Protect PII; never log passwords. |
| Authorization denied | Which role attempted an out-of-scope operation, targeting which resource? | Distinguish app deployment bugs from anomalous access. |
| Role/permission changes | Who just ran `GRANT`, `REVOKE`, or `ALTER ROLE`? | Record change ID, approver, effective identity, and UTC timestamp. |
| Superuser usage | Are admin accounts used outside approved windows? | Alert and post-audit; never share accounts. |
| TLS/certificate events | Expiring certificates, handshake failures, cipher policy violations? | Alert well ahead of rotation/expiration. |
| `system_auth` health | Any changes in replica RF/repair/timeouts and login failures? | New login availability depends on security metadata too. |
| JMX/OS management | Who ran `nodetool`, restarted nodes, edited configs, or accessed snapshots? | CQL audit **does not automatically** capture these actions. |

Some Cassandra versions offer built-in **audit logging**, while others require platform, proxy, or collector mechanisms. Audit events must be protected from tampering/deletion, have **retention**, **UTC/NTP timestamps**, redaction, and off-node storage. **Never blindly log full traffic payloads**: doing so can cause heavy I/O and leak sensitive data.

### 12.1. Example of a Well-Structured Audit Record

~~~text
change_id          = CHG-2026-11-21-SEC-03
actor              = db-admin-session-42
effective_identity = db-security-admin
cluster            = cassandra-prod
dc                 = dc1
operation          = GRANT_SELECT
resource           = telemetry_secure.events_by_device_day
target_role        = telemetry_day_reader
timestamp_utc      = 2026-11-21T10:00:00Z
execution_outcome  = success
verification       = allow/deny test passed
secret_recorded    = false
~~~

This is an **organization-defined audit structure**, not a mandatory Cassandra schema. Keep `execution_outcome` and `verification` **separate**: a successful `GRANT` command does not prove every coordinator reflects the effective role after caching; policy testing is still needed.

## 13. Deployment Scenario: Enabling Authn/Authz on a Running Cluster

**This is a change capable of locking all clients out of the cluster**, not a toggle to flip during peak traffic. A general plan:

### Phase A — Discovery

1. Record **Cassandra version, JDK, deployment mode**, and configs across all nodes/DCs.
2. Inspect `system_auth`, replication strategy/RF, replica/repair state, backups, and recovery readiness.
3. Inventory **every client**: Java Driver, cqlsh, monitoring, migrations, Spark/analytics, backups, admin scripts, and JMX.
4. Define least-privilege roles/permissions per table/keyspace and the identity each client will use.
5. Ensure TLS/certificates are tested or have a secure transition plan.
6. Establish a **break-glass** and rollback channel usable if role/credential provisioning fails.

### Phase B — Staging Preparation

1. Build a topology and version close to production; test enabling authenticator, authorizer, role manager, and TLS.
2. Provision admin and service identities securely; never hardcode passwords in YAML, CI scripts, or tickets.
3. Verify role memberships, permitted `SELECT`/`MODIFY` calls, and **denied** accesses.
4. Test the Java Driver with TLS, truststore, local DC, and reconnection after credential rotation.
5. Test node restarts, valid DC failure simulations, and `system_auth` availability.
6. Measure throughput, p95/p99, login/authorize errors, and cache/auth overhead under realistic load.

### Phase C — Controlled Rollout

~~~mermaid
flowchart TD
    A["Inventory version, clients, system_auth, and TLS"] --> B["Design roles + bootstrap/break-glass"]
    B --> C["Staging: allow/deny tests, driver, failure modes"]
    C --> D{"Proven admin path and rollback?"}
    D -->|No| E["Stop, complete testing/recovery"]
    D -->|Yes| F["Update config per version's rolling plan"]
    F --> G["Verify authn + authz + TLS from each DC"]
    G --> H{"Apps/automation log in with right permissions?"}
    H -->|No| I["Halt rollout; investigate/controlled rollback"]
    H -->|Yes| J["Expand rollout, lock down default paths"]
    J --> K["Monitor, audit, revoke temporary credentials"]
~~~

Key considerations:

- **Rolling restart** if required by the version, preserving quorum/availability so multiple replicas do not go offline together.
- Nodes must not remain in mismatched security policy states **longer than necessary**; doing so causes inconsistent client behavior or enforcement gaps.
- Verify from **each DC** and at least two identity types (admin, application) rather than only from the deployment host.
- Open/close firewalls in a safe order; never lock the break-glass channel before proving all clients are served properly.

### Phase D — Post-Verification and Change Closure

Post-rollout checklist:

~~~text
[ ] Authenticator, Authorizer, RoleManager match intended config across nodes.
[ ] CQL connections without a valid identity are rejected per policy.
[ ] Read roles can SELECT, while INSERT/DELETE/ALTER are denied unless granted.
[ ] Write roles can MODIFY only intended tables; no unexpected SUPERUSERs exist.
[ ] Authentication error/Unauthorized are distinguished from timeout/Unavailable.
[ ] TLS handshake with server verification works; cert/truststore and expiry are monitored.
[ ] system_auth RF/repair/health are valid in every DC.
[ ] Java services, cqlsh, migration jobs, and automation have switched identities.
[ ] JMX/OS/backup paths remain controlled separately; no public admin ports exist.
[ ] Audit logs capture role changes and failed access without leaking secrets.
[ ] Default bootstrap passwords/paths are locked down per runbook.
[ ] Temporary credentials revoked; rollback/recovery verified.
~~~

## 14. Distinguishing Configuration Errors, Caching, and Cluster Faults

| Symptom | Primary Hypothesis | Verification Action |
| --- | --- | --- |
| `cqlsh` connects without credentials | `AllowAllAuthenticator`, an authenticating proxy, or connecting to the wrong cluster. | Check real endpoint, effective config, TLS, session identity, and policy. |
| `SELECT` works, `INSERT` says Unauthorized | Role only holds `SELECT` or lacks `MODIFY`. | `LIST ALL PERMISSIONS`, direct/inherited roles, exact resource, and user. |
| Just ran `REVOKE` yet an old connection still works | Effective cache has not converged or stale session/connection. | Check cache/connection lifecycle/version, test a new connection, run emergency revocation procedure. |
| Logins fail on some nodes in DC2 | `system_auth` replication/repair, caching, or node config drift. | Compare RF/NTS, node health, auth logs, repair, and effective config. |
| After enabling TLS, Java throws certificate exceptions | Mismatched CA/truststore/SAN/hostname. | Inspect real certificates and peer validation; **never use trust-all**. |
| Login succeeds but queries return `Unavailable` | RF/CL/quorum or down nodes. | `nodetool status`, keyspace RF, and replica states. |
| Login/role checks slow down when one DC disconnects | Auth data/cache/replicas or network affected. | `system_auth`, authentication metrics, and DC routing. |
| CQL role is blocked yet `nodetool` still works | JMX uses an independent security path. | JMX authz, OS/bastion credentials, firewalls, and automation audit. |
| Low-privilege role can create/drop tables | Inherited permission from another role, overly broad resource, superuser, or authorizer disabled. | Inspect all effective roles; run negative tests. |
| Audit misses SSH edits to YAML | CQL audit does not cover OS/JMX. | Cross-check bastion/OS/CI/CD session logs. |

**If admin access is lost:** do not delete/edit `system_auth` directly to try a "reset"; use the recovery runbook for your exact version/distribution, backups, snapshots, and approvers. Depending on the incident, restore access before altering any other auth parameters.

## 15. How Do Security, Query Design, and Availability Relate?

### 15.1. Authorization Does Not Fix Expensive Queries

A valid `SELECT` account can still submit:

~~~sql
-- ANTI-PATTERN: do not run on large tables.
SELECT *
FROM telemetry_secure.events_by_device_day
WHERE event_type = 'temperature'
ALLOW FILTERING;
~~~

The query omits `(device_id, event_day)`, so it is not a partition lookup; it may be rejected or scan vast amounts of data depending on Cassandra version and execution plan. Being **permitted to read a table** does not mean every query pattern on that table is **capacity-safe**.

Therefore, pair security with:

- **Query-driven partition key** design, time-series bucketing, and bounded clustering ranges.
- Rate limiting, bounded concurrency, request timeouts, and guardrails.
- Selective tracing/metrics to catch hot partitions/tombstone scans.
- Permissions scoped to **dedicated serving tables** per application/tenant when policy requires.

### 15.2. Consistency Level Does Not Affect Permissions

With RF = 3 in `dc1`, `LOCAL_QUORUM` requires two replicas to respond. An identity without `SELECT` still gets Unauthorized whether using `LOCAL_ONE`, `QUORUM`, or `ALL`. Conversely, even with `SELECT`, a request can still time out due to replicas/GC/network.

~~~text
Authentication: Is User X valid?
Authorization : Does User X have SELECT on telemetry_secure.events_by_device_day?
Routing       : Partition key → token → which natural replicas?
Consistency   : How many responses are needed to complete the request?
Encryption    : Are data/credentials protected in transit?
~~~

One layer cannot substitute for another. Increasing timeouts does not fix permission denied; increasing RF does not protect passwords; enabling TLS does not stop a superuser account from dropping tables.

### 15.3. Backups and Multi-DC Are Part of Data Security

Cross-DC replication helps serve traffic during a site outage; it **does not reliably protect against an accidental `DELETE`** replicated to all replicas. Snapshots and backups require:

- Access identities separated from workloads, **encryption at rest**, key protection, and restricted deletion rights.
- Retention/immutability per requirements, access auditing, and backup export verification.
- Restore testing in an isolated environment, not merely taking snapshots on the same Cassandra volume.
- Treating backup data read permissions as equivalent to reading the source tables.

**Do not treat backups as exempt from RBAC and auditing**: SSTable files can contain sensitive data even when CQL clients are restricted.

## 16. Self-Check Exercises with Answers

**Exercise 1.** A cluster enables native transport TLS and has RF = 3, but `authenticator` is `AllowAllAuthenticator` and `authorizer` is `AllowAllAuthorizer`. Can we say data is protected by user roles?

**Answer:** **No.** TLS protects transit and RF protects data distribution, but there is no identity/permission enforcement as required by RBAC. You must select proper authn/authz mechanisms and verify them in practice.

**Exercise 2.** `events_reader` has `SELECT` on a table with `LOGIN = false`. Is that role a login account for a Java service?

**Answer:** **No.** It is a non-login group role. You need a provisioned login identity that receives `GRANT events_reader TO identity`.

**Exercise 3.** Identity `api_v1` was only granted `SELECT` on `ks.tbl`, yet it actually succeeds at `DELETE`. Name two possible causes.

**Answer:** It may hold **inherited or directly granted `MODIFY` at a broader scope**, the identity may be a superuser, or the authorizer is not configured/enforced as expected. Inspect effective permissions and test with the exact identity.

**Exercise 4.** Someone changes `system_auth` from RF = 1 to RF = 3 using `ALTER KEYSPACE`. Can we immediately assert every node now stores all roles and permissions?

**Answer:** **No.** Changing RF metadata **does not automatically ensure existing data has reached new replicas**. You need the appropriate transfer/repair procedure and must verify logins/permissions across nodes/DCs.

**Exercise 5.** A Java client gets a TLS handshake exception because an internal CA is not yet in the truststore. Should we enable trust-all to connect quickly?

**Answer:** **No.** Configure the truststore/CA/SAN and server validation policy properly. Trust-all disables peer verification and exposes connections to endpoint spoofing.

**Exercise 6.** A role just had permissions `REVOKE`d, yet a previously opened client connection still executes an operation. Does this necessarily prove `REVOKE` failed?

**Answer:** **No.** Authorization caches, active connection sessions, and inter-node convergence can affect when policy changes take effect. Test on a new connection, inspect effective roles/caches, and apply emergency revocation runbooks if needed.

**Exercise 7.** `cqlsh` reports Unauthorized on `ALTER TABLE`, yet an engineer can still run `nodetool repair`. Why?

**Answer:** `ALTER TABLE` goes through **CQL RBAC**; `nodetool repair` typically goes through **JMX** with separate authz/OS/network controls. Blocking one channel does not prove another channel is blocked.

**Exercise 8.** Service A and Service B share one superuser password. Service A's credentials leak. Why is rotation operationally risky?

**Answer:** Because the two services share an identity, you cannot revoke A alone without breaking B; attribution is difficult and coordinating connection restarts is harder. Move to separate identities, least privilege, and a secret manager.

**Exercise 9.** A role has `SELECT` on `telemetry_secure.events_by_device_day`. A query omitting the partition key and using `ALLOW FILTERING` becomes very slow. Is this an authentication error or a query-modeling issue?

**Answer:** This is a **query-modeling/resource-usage** issue, not authentication. The role is permitted to read, but queries still need proper partition keys, clustering ranges, guardrails, and rate limiting.

**Exercise 10.** When rolling out auth config changes on a two-DC cluster, why must you test logins from both DCs even when `nodetool status` shows all `UN`?

**Answer:** `UN` membership does not prove `system_auth` has proper replicas/repairs, that every node runs the same security config, that certificates/trust match, or that permission caches have converged. Login and allow/deny tests are separate postconditions.

## 17. End-of-Lesson Checklist and Decision Tree

~~~mermaid
flowchart TD
    A["Design Cassandra security"] --> B["Identify version, edition, cluster topology"]
    B --> C["Choose Authenticator + Authorizer + RoleManager"]
    C --> D["Check system_auth RF/repair in each DC"]
    D --> E["Enable and verify client/internode TLS"]
    E --> F["Create dedicated identities + least-privilege roles"]
    F --> G["Run allow/deny tests via cqlsh and Java Driver"]
    G --> H{"Right permissions, right endpoints, no disruption?"}
    H -->|No| I["Halt rollout, check config/cache/replicas/TLS"]
    I --> G
    H -->|Yes| J["Lock default admin, audit, rotate, and monitor"]
    J --> K["Periodically review roles, restores, and incident response"]
~~~

~~~text
[ ] Recorded exact Cassandra/JDK/driver versions and deployment type.
[ ] Identified active authenticator, authorizer, and role manager mechanisms.
[ ] Not relying on AllowAll in production environments requiring RBAC.
[ ] CQL native transport uses TLS with proper CA/SAN/hostname verification.
[ ] Internode/JMX/OS/backup security addressed separately, not just CQL.
[ ] system_auth RF, DC/rack placement, health, and repair meet availability targets.
[ ] Each service has its own identity, never logging in as superuser.
[ ] Group roles use LOGIN=false; SELECT/MODIFY scoped to exact tables/keyspaces.
[ ] Tested both allow and deny with real roles, including direct/inherited rights.
[ ] Accounted for auth/permission caches and open connections on REVOKE.
[ ] Never write passwords, certificate private keys, or access tokens to logs/CI.
[ ] Audit role changes, failed logins, JMX/OS actions, and UTC timelines.
[ ] Procedures exist for credential rotation, locking bootstrap accounts, and break-glass.
[ ] Rollout tested in staging/canary with rollback, never applied blindly at once.
[ ] Backups and sensitive data protected during both export and restore.
~~~

**Conclusion:** In Cassandra, **authentication** answers *who is connecting*, **authorization** answers *what is permitted on which resource*, and **TLS** and **auditing** protect transit and traceability. Configuration must be **verified for the exact version**, never just copying three lines of `cassandra.yaml`. Distributed-system specifics — **`system_auth`, per-datacenter RF, replica health, caches, and connection lifecycles** — determine whether login and revocation remain reliable. A sound deployment combines **least privilege, separate identities, peer-verified TLS, allow/deny verification, auditing, and recoverability**, without confusing CQL RBAC with JMX or OS privileges.
