# Integrated Practice: Cassandra Backup and Restore with Access Control and TLS

## 1. Scenario and Objectives

A Java service stores activity logs in **Apache Cassandra**, using a wide-column table keyed by tenant and day. The operations team needs to back up data to recover after a cluster failure, while the cluster enforces **CQL credential authentication**, **role-based access control (RBAC)**, and **TLS for client connections**. If you preserve only SSTable files while neglecting schemas, roles, certificates, and network configs, the data may survive yet applications remain unable to connect—or the recovery process could expose sensitive data.

This lab centers on the question:

> How do you create, verify, and restore a Cassandra backup while guaranteeing **data integrity**, **proper access controls**, and **valid TLS connectivity**?

This exercise integrates core Cassandra fundamentals: multi-node replication, partition-key data distribution, CQL, consistency levels, SSTable snapshots, compaction, repair, single-node failures, and the Java Driver.

**Required deliverables:**

1. An activity table populated with sample data on a Cassandra cluster enforcing authentication and TLS.
2. A verifiable backup set: snapshots across relevant nodes, schema DDL, a manifest, and security configuration records **with secrets redacted**.
3. An isolated test target cluster restored from the backup using tools compatible with your Cassandra version.
4. Evidence that a read-only account **can read** and **cannot write**, and that a Java application connects over TLS and sees only authorized data.
5. An RPO/RTO report documenting snapshot limitations and simulated failure outcomes.

### Scope, Assumptions, and Safety Principles

- Use an **isolated lab cluster**, e.g., three nodes in DC `datacenter1` with `NetworkTopologyStrategy` and replication factor (RF) = 3. Replace the DC name with the actual value from `system.local`.
- Commands illustrate Cassandra **4.x with standard tooling syntax**. Before running on 4.0, 4.1, 5.x, or another distribution, verify `nodetool help`, `sstableloader --help`, and SSTable format compatibility.
- Configure CQL native transport on port 9042 with mandatory TLS, `PasswordAuthenticator`, and `CassandraAuthorizer`. If your setup differs, adapt the operational steps accordingly.
- Use non-sensitive synthetic data. Never commit real passwords, private keys, or tokens into repositories, backup bundles, or logs.
- Perform **restores onto a separate, empty target cluster**. Never load snapshots directly into a live production cluster serving traffic.
- This lab does not build a full automated backup platform or guarantee point-in-time recovery (PITR). Snapshots are only one component of a recovery plan.

## 2. Understanding What Gets Backed Up

Cassandra distributes application data by partition key across replica sets. For a table keyed by `((tenant_id, event_day), occurred_at, event_id)`, a snapshot on **a single node** captures only the SSTables residing on that node; it does not automatically hold every partition in the cluster.

`nodetool snapshot` creates a snapshot on **the invoked node**, primarily via hard links to SSTable component files. By default it flushes memtables before snapshotting unless skipping flush is specified. A snapshot is a durable point-in-time copy local to that node—**not a cluster-wide consistent transaction at one exact instant**. To cover all token ranges and replicas, coordinate snapshots across nodes according to plan and track per-node completion status. In this lab, pause application writes during the snapshot window to obtain a clean data boundary.

| Component | Included in an application keyspace snapshot? | How to protect / recover |
| --- | --- | --- |
| Table SSTables | Yes, on each node holding a replica | Snapshot every relevant node; copy off-node; verify checksums |
| Keyspace, table, index, and UDT schemas | Do not rely solely on snapshots for schema recovery | Export CQL DDL and store in versioned source control |
| Roles, credentials, `GRANT`s | Not included in **application keyspace** snapshots | Export audited role/grant lists; recreate via secure provisioning |
| Passwords and private keys | Must not accompany data backups | Store in a secret manager / PKI; reissue or rotate during restore |
| `cassandra.yaml`, TLS configs, topology | Not included in table snapshots | Back up configs with secrets redacted; manage via configuration management |
| Changes after the snapshot point | Not guaranteed to be in the snapshot | Incremental backups / commitlog archiving and tested PITR workflows if implemented |
| Expired TTL data / tombstones | Depends on write time, TTL, and SSTable state | Never assume restoring revives expired data |

**Distinguishing three mechanisms:** snapshots preserve a set of SSTables at a checkpoint; Cassandra incremental backups hard-link/copy newly flushed SSTables as configured; commitlog archiving provides raw mutations to build closer-to-real-time recovery. **Enabling incremental backups or archiving commitlogs alone does not automatically yield working PITR**: you also need manifests, application ordering, matching schemas, deduplication controls, replay testing, and retention cleanup.

### Recovery Objectives

- **RPO (Recovery Point Objective):** acceptable data-loss window. A snapshot at 10:00 followed by an incident at 10:20 can leave post-snapshot writes absent from the backup—an observed RPO of up to 20 minutes without additional mechanisms.
- **RTO (Recovery Time Objective):** elapsed time from incident onset until service restoration. RTO includes provisioning the cluster, issuing certificates, restoring schemas/roles, streaming SSTables, verifying data, and shifting traffic.
- With per-node snapshots, "10:00" is merely a **coordination timestamp**, not a guarantee that every node captured an identical logical state at 10:00. Record each node's actual snapshot timestamps and write-quiescence state.

## 3. Lab Architecture and Secure Data Flow

~~~mermaid
flowchart LR
    APP["Java App / cqlsh"] -->|"CQL over TLS: 9042"| C["Cassandra: 3 nodes"]
    ADM["Operator via secure admin channel"] -->|"nodetool + JMX"| C
    C -->|"per-node snapshot"| S["SSTable snapshots"]
    S -->|"encrypted copy + checksum"| B["Off-cluster backup store"]
    B -->|"stage for recovery"| L["sstableloader"]
    L -->|"stream over configured network"| R["Isolated restore cluster"]
    R -->|"CQL over TLS + RBAC"| T["Verify Java, roles, and data"]
~~~

| Surface | Primary control | What to verify |
| --- | --- | --- |
| Java / cqlsh to Cassandra | TLS + CQL authentication + authorization | Valid certs, plaintext rejected, accurate `GRANT`s |
| Node to node | Internode TLS if enabled | Consistent `server_encryption_options` cluster-wide |
| Operator to JMX / nodetool | JMX auth/TLS or local execution over audited SSH | JMX privileges are separate from CQL roles |
| Node to backup store | ACLs, encryption in transit and at rest | Backups cannot be modified/deleted by app roles |
| Restore operator to target cluster | OS permissions, streaming network, recovery credentials | Operates strictly on the approved target cluster |

A role granted `GRANT SELECT` in CQL does **not** gain permission to read SSTable files or run `nodetool snapshot` just because CQL allows `SELECT`. Conversely, anyone with direct OS access to data files can bypass CQL authorization. Protect snapshots at the storage and OS layers even when application RBAC is strict.

## 4. Setting Up the Cluster, TLS, and Authentication

### 4.1. Prerequisites Before Enabling Security

You need server certificates signed by a CA trusted by clients, with SANs matching connection hostnames (`cassandra-1.lab`, `cassandra-2.lab`, ...). Never reuse one unverified certificate across all nodes without identity validation. In the lab, the administrator prepares truststores and keystores; in production, use PKI/secret management with periodic rotation.

Illustrative configuration *structure* inside each node's `cassandra.yaml`:

~~~yaml
authenticator: PasswordAuthenticator
authorizer: CassandraAuthorizer
role_manager: CassandraRoleManager

client_encryption_options:
  enabled: true
  optional: false
  keystore: /etc/cassandra/tls/node-keystore.jks
  keystore_password: "<provided-by-secret-manager>"
  require_client_auth: false
~~~

- `enabled: true` enables TLS for native CQL; `optional: false` enforces TLS for all clients. Do not allow plaintext connections in this lab.
- `keystore` holds the node's key/certificate; clients need the corresponding CA/truststore. If enabling **mutual TLS**, set `require_client_auth: true` with a server truststore and supply valid client certificates.
- If encryption **between nodes** is required, also configure `server_encryption_options` (e.g., `internode_encryption: all` with matching keystores/truststores). That is a separate network path from client TLS; changes require rolling-upgrade compatibility planning and dedicated testing.
- Config files holding secrets must restrict file permissions or receive secrets via secure deployment mechanisms. Angle-bracketed values are placeholders, **not** valid passwords to leave as-is.
- Enabling auth/authz on an already-running cluster requires planning admin bootstrap and ensuring `system_auth` has proper replication; never flip it abruptly in production. This lab assumes the cluster is already configured and restarted cleanly.

**Note on TLS layers:** Client TLS does not automatically encrypt inter-node traffic, JMX, or backups on disk. Validate each path independently.

### 4.2. Verifying Datacenter, Topology, and TLS

Sign in using the lab admin role (without leaving passwords in shell history) and run:

~~~sql
SELECT cluster_name, data_center, release_version FROM system.local;
~~~

From a host holding the lab CA public cert, inspect the TLS handshake and certificate chain:

~~~bash
openssl s_client \
  -connect cassandra-1.lab:9042 \
  -servername cassandra-1.lab \
  -CAfile /secure/lab-ca.pem \
  -verify_return_error
~~~

Verify the certificate chain and SANs, and enable **hostname verification** on clients. A successful TLS handshake alone proves encryption is active; skipping hostname verification leaves clients exposed to endpoint spoofing.

Example `~/.cassandra/cqlshrc` on the workstation:

~~~ini
[ssl]
certfile = /secure/lab-ca.pem
validate = true
~~~

Connect using the TLS client:

~~~bash
cqlsh cassandra-1.lab 9042 --ssl -u lab_admin
~~~

Enter the password interactively or via a secure credential store; avoid `-p actual-password` in shell history and process arguments. Test connecting without `--ssl` (in the lab) and confirm the server rejects the handshake. If using mTLS, configure `cqlsh` client key/cert settings and verify rejection when the client cert is omitted.

### 4.3. Least-Privilege Permissions for Applications

As admin, create two application roles and grant only the required permissions. The example below uses placeholders; **substitute real secrets provisioned from your vault and never commit scripts with real passwords**.

~~~sql
CREATE ROLE IF NOT EXISTS lab_reader
WITH LOGIN = true
AND SUPERUSER = false
AND PASSWORD = '<READER_SECRET>';

CREATE ROLE IF NOT EXISTS lab_writer
WITH LOGIN = true
AND SUPERUSER = false
AND PASSWORD = '<WRITER_SECRET>';
~~~

After creating the table in the next section, grant permissions:

~~~sql
GRANT SELECT ON TABLE lab_audit.activity_by_tenant_day TO lab_reader;
GRANT MODIFY ON TABLE lab_audit.activity_by_tenant_day TO lab_writer;

LIST ALL PERMISSIONS OF lab_reader;
LIST ALL PERMISSIONS OF lab_writer;
~~~

Expected: `lab_reader` has only `SELECT` on the table; `lab_writer` has `MODIFY` (`INSERT`/`UPDATE`/`DELETE`) without implicitly receiving `SELECT`. Effective permissions can include inherited role grants; inspect the full role hierarchy if additional roles exist in your lab.

**Note:** CQL permissions do not substitute for JMX permissions, OS user permissions, or backup-store access controls. Never grant `SUPERUSER` to application accounts.

## 5. Creating Verifiable Pre- and Post-Snapshot Data

### 5.1. Creating the Keyspace and Table

In a lab with three nodes in DC `datacenter1`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS lab_audit
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS lab_audit.activity_by_tenant_day (
    tenant_id   text,
    event_day   date,
    occurred_at timestamp,
    event_id    uuid,
    actor_id    text,
    action      text,
    resource_id text,
    PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
)
WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);
~~~

This table illustrates **query-driven design**. Partition key `(tenant_id, event_day)` groups one tenant's activity for a UTC day; clustering columns sort descending by time. Snapshots must preserve partition data according to real cluster placement. Never use `ALLOW FILTERING` to count records across the whole system.

In `cqlsh` on the three-replica cluster, set the lab consistency level:

~~~sql
CONSISTENCY LOCAL_QUORUM;
~~~

With RF=3 in one DC, `LOCAL_QUORUM` requires acknowledgments from at least two local replicas per read/write. A single-node lab must adjust RF/consistency accordingly, though it cannot test quorum behavior under replica failures.

### 5.2. Writing Baseline Data

~~~sql
INSERT INTO lab_audit.activity_by_tenant_day
(tenant_id, event_day, occurred_at, event_id, actor_id, action, resource_id)
VALUES ('tenant-a', '2026-11-20', '2026-11-20T08:00:00Z',
 11111111-1111-4111-8111-111111111111,
 'user-1', 'LOGIN', 'session-1');

INSERT INTO lab_audit.activity_by_tenant_day
(tenant_id, event_day, occurred_at, event_id, actor_id, action, resource_id)
VALUES ('tenant-a', '2026-11-20', '2026-11-20T09:00:00Z',
 22222222-2222-4222-8222-222222222222,
 'user-1', 'CREATE', 'order-1');

INSERT INTO lab_audit.activity_by_tenant_day
(tenant_id, event_day, occurred_at, event_id, actor_id, action, resource_id)
VALUES ('tenant-b', '2026-11-20', '2026-11-20T07:30:00Z',
 33333333-3333-4333-8333-333333333333,
 'user-2', 'LOGIN', 'session-2');
~~~

Before backing up, verify each partition individually:

~~~sql
SELECT occurred_at, event_id, actor_id, action, resource_id
FROM lab_audit.activity_by_tenant_day
WHERE tenant_id = 'tenant-a' AND event_day = '2026-11-20';

SELECT occurred_at, event_id, actor_id, action, resource_id
FROM lab_audit.activity_by_tenant_day
WHERE tenant_id = 'tenant-b' AND event_day = '2026-11-20';
~~~

Expected result: tenant A has **two rows** and tenant B has **one row**; within tenant A, `09:00 CREATE` precedes `08:00 LOGIN`. Save the `(tenant_id, event_day, occurred_at, event_id)` keys and content checksums as your verification baseline. Never verify by scanning an entire production keyspace.

## 6. Creating and Verifying the Backup Set

### 6.1. Freezing the Checkpoint and Recording Metadata

Stop or quiesce writes from the **lab application** during capture. Confirm all three baseline writes from section 5 succeeded beforehand. Record a minimal recovery manifest:

| Manifest field | Example | Purpose |
| --- | --- | --- |
| `backup_id` | `audit-drill-20261121-a` | Uniquely identifies a backup set |
| `source_cluster` / `source_dc` | `lab-source` / `datacenter1` | Identifies source cluster and topology |
| `cassandra_version` / `partitioner` | Actual values from cluster | Verifies SSTable/streaming compatibility |
| `schema_revision` | DDL hash / file | Restores exact table structure |
| `snapshot_tag` | `audit-drill-20261121` | Identifies the snapshot on each node |
| `nodes_completed` | Node list, timestamps, statuses | Confirms full node coverage |
| `archive_checksums` | SHA-256 of backup archives | Detects archive corruption or tampering |
| `security_profile` | `PasswordAuthenticator`, `CassandraAuthorizer`, client TLS required | Restores access policies |
| `roles_and_grants_redacted` | Role names and grants; no passwords/hashes | Recreates ACLs safely |
| `rpo_reference_time` | Timestamp writes were quiesced | Reference point for post-restore checks |

Export the CQL schema using the commands supported by your `cqlsh` version:

~~~sql
DESCRIBE KEYSPACE lab_audit;

LIST ROLES;
LIST ALL PERMISSIONS OF lab_reader;
LIST ALL PERMISSIONS OF lab_writer;
~~~

Save the `DESCRIBE KEYSPACE` output to the backup metadata store. Use `LIST ROLES` and grant listings for reference, **never** storing passwords, credential hashes, private keys, tokens, or sensitive secrets. If multiple roles or inherited permissions exist, export all service-relevant entries rather than just the two example roles.

### 6.2. Snapshotting Each Node

On **every Cassandra node in the source cluster**, over SSH with appropriate operator privileges, run:

~~~bash
nodetool snapshot -t audit-drill-20261121 lab_audit
nodetool listsnapshots
~~~

Record outputs separately for `node-1`, `node-2`, and `node-3`. Never treat a successful snapshot command on a single node as a completed cluster backup.

Typical snapshot directory layout:

~~~text
/var/lib/cassandra/data/
  lab_audit/
    activity_by_tenant_day-<table-id>/
      snapshots/
        audit-drill-20261121/
          <SSTable-components>
          <version-specific-manifest/metadata>
~~~

On each node, locate the directories to archive:

~~~bash
find /var/lib/cassandra/data/lab_audit \
  -type d -path '*/snapshots/audit-drill-20261121' -print
~~~

Actual paths depend on `data_file_directories`, container mounts, and OS layout. An SSTable consists of multiple component files (`Data`, `Index`, `Statistics`, `CompressionInfo`, etc.). **Never copy only the `Data.db` file and treat it as a complete backup.**

Because snapshots use hard links on the same disk, they do not survive node or disk loss. Copy **all component files** to an off-node backup store, preserving `node/keyspace/table/snapshot_tag` hierarchy and metadata; encrypt in transit and at rest, enforce least-privilege access, and apply retention/immutability protections. Verify checksums **after** copies land in the backup store. Backup tools may compress or encrypt archives, so verify decompression and checksums in the restore environment.

**Only after off-node copies are verified** should local snapshots be cleared per policy, for example:

~~~bash
# Run on each respective node only after the archive is verified.
nodetool clearsnapshot -t audit-drill-20261121 lab_audit
~~~

In this lab you may keep local snapshots until the end of the session for easy comparison. Ensure adequate disk headroom, because hard links prevent old SSTables from being unlinked as compactions create newer files.

### 6.3. Creating a Post-Backup Write to Test RPO

Once **all nodes have finished snapshotting** and the checkpoint is logged, resume writes and insert one new event:

~~~sql
INSERT INTO lab_audit.activity_by_tenant_day
(tenant_id, event_day, occurred_at, event_id, actor_id, action, resource_id)
VALUES ('tenant-a', '2026-11-20', '2026-11-20T10:00:00Z',
 44444444-4444-4444-8444-444444444444,
 'user-1', 'UPDATE', 'order-1');
~~~

Now the source cluster has **three rows** for tenant A, whereas the snapshot captured during the write pause holds only **two rows** for tenant A. Do not add the `10:00` event to the backup archive. This intentional delta tests the RPO boundary. Under live unpaused workloads, you cannot assume a multi-node snapshot set shares such an exact cluster-wide cutoff.

## 7. Restoring to an Independent Target Cluster

### 7.1. Choosing the Restore Approach

There are two main techniques; never mix them without an explicit plan:

| Method | When to use | Key requirements |
| --- | --- | --- |
| **Bulk load/stream via `sstableloader`** | Restoring SSTable data into a running target cluster | Target cluster already has a compatible schema; compatible tool/SSTable format; streaming network, auth, and TLS configured |
| Controlled node-local SSTable placement/import | Specialized DR workflows with version-specific runbooks | Must strictly obey table ID, token ownership, node state, import/refresh, and version rules; error-prone if copying straight into live data dirs |

**This lab uses `sstableloader`** to avoid manually manipulating files inside live data directories. Never copy SSTables randomly from source nodes to target nodes and start the app as if restored; token ranges, schema/table IDs, and replica ownership can differ.

### 7.2. Provisioning the Target Cluster with Security Policies

Deploy an isolated `lab-restore` cluster configured with topology, authorization, certificates/truststores, and TLS matching the manifest. Keep the same Cassandra version (or a **supported** SSTable/loader upgrade path), same partitioner, and compatible logical schema.

Actual dependency ordering may vary, but at minimum achieve:

1. Nodes are healthy; `nodetool status` confirms expected cluster state and replication.
2. CQL native TLS is active; clients validate CA and hostname, and plaintext is rejected.
3. Admin roles are accessible securely; application roles are recreated via identity/secret management.
4. Keyspace and tables are recreated from the **exported DDL**, with replication tuned to target topology. In the lab, you may rerun the DDL block from section 5 if it matches the exported schema identically.
5. Target tables are **initially empty** so verification results are deterministic. Never restore directly on top of live application data.

**Never blindly restore `system_auth` from another cluster** as a shortcut for migrating roles/grants. Auth metadata, permissions, and caches depend on cluster topology, version, and security policy. In this lab, create fresh roles using new passwords from the vault, then replay the audited `GRANT` statements.

### 7.3. Staging SSTables for Loading

Decrypt/extract backups into a staging directory **outside running Cassandra data directories**. Verify each archive's checksum before use. Preserve per-node source metadata; restore snapshots covering all token ranges so no range owned exclusively by one node is skipped.

For `sstableloader`, organize paths in the **keyspace/table** directory hierarchy expected by your loader version so SSTable components sit directly inside the staged table directory:

~~~text
/restore/staging/
  lab_audit/
    activity_by_tenant_day-<source-table-id>/
      <SSTable-components-copied-from-snapshot>
~~~

`<source-table-id>` is a placeholder. When loading snapshots from multiple nodes, run sequentially for each node's staged SSTable set and track processed sets. Overlapping primary keys are reconciled by Cassandra during streaming, though redundant streaming increases load and does not remove the need to understand timestamps/tombstones. Never overwrite distinct SSTables that happen to share filenames; keep per-source staging directories or follow a controlled import sequence.

### 7.4. Loading Data with `sstableloader`

Illustrative command for a **restore host authorized to connect**:

~~~bash
# Password placeholders are for lab syntax only; never use literals like this in production.
# Verify exact flags with: sstableloader --help
sstableloader \
  -d cassandra-restore-1.lab,cassandra-restore-2.lab \
  -u restore_admin \
  -pw '<RESTORE_ADMIN_SECRET>' \
  -ssl \
  -ts /secure/restore-truststore.jks \
  -tspw '<TRUSTSTORE_SECRET>' \
  /restore/staging/lab_audit/activity_by_tenant_day-<source-table-id>/
~~~

- `-d` specifies contact points of the **target cluster**; verify DNS, IPs, and hostnames beforehand. Never point accidentally at the source cluster.
- `-ssl` and truststore flags configure the loader's TLS connection. If the server enforces mutual TLS, add client keystore flags per your tool version.
- Ensure network paths allow loader streaming ports and comply with inter-node TLS policies. Having CQL query privileges **does not automatically** permit running bulk loads; infrastructure runbooks must provision appropriate operational permissions.
- **Passwords on command lines can leak via process lists/logs.** This command uses placeholders to show syntax. In real environments, use your supported secret-injection method and verify how the tool handles credentials; never paste production passwords into a terminal.
- Monitor console output, streamed SSTables/bytes, and per-set errors. If the loader rejects SSTable formats, schemas, or TLS, stop and fix the root cause; never disable TLS just to "make it finish."

The loader streams valid mutations/SSTables into the cluster; ingested data still obeys Cassandra's timestamp, tombstone, consistency, and repair semantics. Streaming the expected byte count does not prove business-level recovery: you must still verify contents and permissions next.

## 8. Post-Restore Verification of Data, Permissions, and TLS

### 8.1. Verifying Data by Primary Key

On the **target** cluster, connect over TLS with an account holding `SELECT` and query:

~~~sql
CONSISTENCY LOCAL_QUORUM;

SELECT occurred_at, event_id, action, resource_id
FROM lab_audit.activity_by_tenant_day
WHERE tenant_id = 'tenant-a' AND event_day = '2026-11-20';

SELECT occurred_at, event_id, action, resource_id
FROM lab_audit.activity_by_tenant_day
WHERE tenant_id = 'tenant-b' AND event_day = '2026-11-20';
~~~

Assuming the backup was captured cleanly after the three baseline `INSERT`s and before the `10:00` `INSERT`, expect:

| Partition | Source cluster after change | Target cluster restored from snapshot |
| --- | --- | --- |
| `(tenant-a, 2026-11-20)` | 3 rows: 08:00, 09:00, **10:00** | **2 rows: 08:00, 09:00** |
| `(tenant-b, 2026-11-20)` | 1 row: 07:30 | **1 row: 07:30** |

Match records by **full primary key** and payload content, not row count alone. For real datasets, compare per-partition checksums/manifests or controlled key samples; avoid running `SELECT COUNT(*)` or scanning an entire production cluster just to verify. If the `10:00` event unexpectedly appears, check whether a post-snapshot SSTable, wrong archive, or incremental/replay stream was loaded by mistake.

### 8.2. Verifying Roles and `GRANT`s

On the target cluster, recreate `lab_reader` and `lab_writer`, apply the two `GRANT`s from section 4, and use **new** securely provisioned passwords. Then open a **new `cqlsh` session** as the reader role:

~~~bash
cqlsh cassandra-restore-1.lab 9042 --ssl -u lab_reader
~~~

In that session:

~~~sql
-- Must succeed:
SELECT occurred_at, action
FROM lab_audit.activity_by_tenant_day
WHERE tenant_id = 'tenant-a' AND event_day = '2026-11-20';

-- Must be rejected for lacking MODIFY permission:
INSERT INTO lab_audit.activity_by_tenant_day
(tenant_id, event_day, occurred_at, event_id, actor_id, action, resource_id)
VALUES ('tenant-a', '2026-11-20', '2026-11-20T12:00:00Z',
 55555555-5555-4555-8555-555555555555,
 'forbidden-user', 'DELETE', 'resource-x');
~~~

The second `INSERT` serves as a **negative test** and must fail with an authorization error; if it succeeds, inspect inherited roles, `SUPERUSER` flags, or whether the session accidentally used admin credentials. Clean up any test row if lab policy requires resetting state after permission fixes.

Repeat for `lab_writer`: writes succeed on the granted table, while ungranted `SELECT` queries fail. Never attempt test writes against someone else's real data. Permission denial is a **passing security test result**.

### 8.3. TLS and Recovery Verification Matrix

| Test | Expectation |
| --- | --- |
| Client uses TLS + valid CA + matching hostname + valid role | Connects and queries according to permissions |
| Plaintext client connects to TLS-required CQL port | Connection rejected |
| Untrusted CA or SAN mismatch against hostname | Client enforcing certificate verification rejects connection |
| Wrong role password | Authentication fails |
| Reader role attempts `INSERT` | Authorization fails |
| Client lacks certificate when `require_client_auth: true` | TLS/mTLS handshake fails |
| Backup archive altered by one byte | Checksum/signature verification fails prior to restore |
| Missing node/SSTable in backup set | Restore fails data verification or reports incomplete coverage; do not declare success |

In practice, you do not need to break the cluster to prove every row in the matrix. Several tests can run from an isolated client or against a deliberately modified copy of an archive while leaving the original backup untouched.

## 9. Connecting from a Java Application After Recovery

Example using **Apache/DataStax Cassandra Java Driver 4.x**: authenticate as `lab_reader` over TLS using a PKCS#12 truststore containing the restored cluster's CA. Passwords come from environment variables supplied by the runtime, never hardcoded.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.time.LocalDate;

public class VerifyRestoredActivities {
    static SSLContext sslContextFromTruststore() throws Exception {
        char[] secret = System.getenv("CASSANDRA_TRUSTSTORE_PASSWORD")
                              .toCharArray();
        KeyStore truststore = KeyStore.getInstance("PKCS12");
        try (InputStream input = Files.newInputStream(
                Path.of(System.getenv("CASSANDRA_TRUSTSTORE_PATH")))) {
            truststore.load(input, secret);
        }
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
            TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(truststore);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, tmf.getTrustManagers(), new SecureRandom());
        return context;
    }

    public static void main(String[] args) throws Exception {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(
                    "cassandra-restore-1.lab", 9042))
                .withLocalDatacenter("datacenter1")
                .withAuthCredentials(
                    "lab_reader",
                    System.getenv("CASSANDRA_READER_PASSWORD"))
                .withSslContext(sslContextFromTruststore())
                .build()) {

            PreparedStatement stmt = session.prepare(
                "SELECT occurred_at, event_id, action " +
                "FROM lab_audit.activity_by_tenant_day " +
                "WHERE tenant_id = ? AND event_day = ?");

            var bound = stmt.bind("tenant-a", LocalDate.parse("2026-11-20"))
                            .setConsistencyLevel(
                                DefaultConsistencyLevel.LOCAL_QUORUM);

            for (Row row : session.execute(bound)) {
                System.out.println(row.getInstant("occurred_at")
                    + " | " + row.getUuid("event_id")
                    + " | " + row.getString("action"));
            }
        }
    }
}
~~~

**Additional deployment setting to verify:** the driver must enable hostname validation against the server certificate's SAN (e.g., `advanced.ssl-engine-factory.hostname-validation` where supported by your factory/version). Passing a truststore to `SSLContext` **must not be assumed to automatically enforce hostname verification**. If enabling mTLS, initialize `SSLContext` with a **KeyManager** holding the client certificate/key in addition to the TrustManager. Always test that a hostname mismatching the SAN is rejected.

In long-running Java services, share a single `CqlSession` across the application lifecycle rather than opening a new session per request. Grant least-privilege permissions to service accounts. When failing over to a restored cluster, update contact points/DNS, truststores, and role credentials via deployment workflows; never relax ACLs or disable TLS to work around connection errors.

## 10. Common Pitfalls in Cassandra Backup and Restore

### 10.1. Snapshots Are Not Cluster-Wide Consistent Images

While writes continue, node A's snapshot may capture state before a mutation while node B's captures state after it. Replication and `LOCAL_QUORUM` provide fault tolerance when enough replicas respond, not synchronized transactional snapshots across three nodes. For workloads requiring strict recovery points, coordinate write quiescence or adopt dedicated backup/PITR architectures paired with time-ordered mutation auditing.

### 10.2. Expired TTL Data, Tombstones, and Compaction

SSTables can contain TTLs and tombstones. Restoring preserves the original write timestamps and TTLs; it **does not** reset row lifetimes. Rows whose TTL has expired by restore time will not appear in `SELECT` results even though their SSTables still consume disk space. Post-restore, monitor tombstone scan rates, compaction, disk usage, `gc_grace_seconds` policies, and repair. Never lower `gc_grace_seconds` just to "clean up faster" if a replica could have missed tombstones, as deleted data may resurrect.

SSTables captured before or between compactions are not logically independent files. Therefore, never infer row counts from file counts; query and verify by primary key.

### 10.3. Repair, Replication, and Access Control

After restore, replicas may require synchronization depending on the loading method and Cassandra version. Schedule and verify repairs per runbook, confirming all nodes received complete data. In an RF=3 single-DC cluster, one failed replica does not break `LOCAL_QUORUM`; **two unavailable replicas** will cause `LOCAL_QUORUM` reads/writes to return `Unavailable` or time out. Never lower consistency merely to make verification checks "turn green."

If you restore data without restoring roles and grants, application accounts fail with `Unauthorized`. If you restore ACLs but forget the CA/truststore or SAN, clients fail at the TLS layer before authentication even starts. Classify failures by layer rather than blindly retrying every error.

### 10.4. Troubleshooting Checklist

| Symptom | Primary suspect | Action |
| --- | --- | --- |
| `NoHostAvailable` / TLS handshake error | Hostname, CA, port, TLS mode, expired cert | Verify certificate chain, SANs, contact points, and network |
| `AuthenticationException` | Wrong password, role lacks `LOGIN`, auth config | Check vault secrets, role existence, target cluster, and authenticator |
| `UnauthorizedException` | Missing `GRANT` or wrong role | Check direct and inherited permissions on the table |
| `UnavailableException` / read timeout | Local replicas below CL, node not ready | Inspect `nodetool status`, RF, DC, repair, and logs |
| Loader rejects SSTable | SSTable version, partitioner, or schema mismatch | Stop, cross-check manifest and compatibility matrix |
| Restored table missing rows | Missing node snapshot, lost SSTable, TTL, stream failure | Verify node coverage, checksums, TTLs, snapshot time, and logs |
| Disk grows despite expired TTL | Tombstones/SSTables awaiting compaction or retained snapshot hard links | Inspect compaction, lingering snapshots, and repair |

**Never troubleshoot by** copying files straight into live data directories, using `ALLOW FILTERING` to "hunt for missing data," disabling auth/TLS, or granting `SUPERUSER` to every account.

## 11. Self-Directed Exercises and Evaluation Criteria

### Exercise A — Prove Backups Can Be Decrypted and Restored

Create a manifest containing at least the fields in section 6, download archives from the backup store to the restore host, verify checksums, and load the table with `sstableloader`. Record SSTable/file counts, byte sizes, and verified row counts per partition. State explicitly which step proves **file readability**, which proves **data ingestion**, and which proves **application usability**.

### Exercise B — Post-Restore Permission Testing

Use `lab_reader` and `lab_writer` to verify the `SELECT`/`INSERT` matrix. Add an `audit_admin` role with schema-management or lab-specific access; contrast those CQL privileges with the OS/JMX privileges required to run `nodetool snapshot`. Explain why a read-only CQL role must not be permitted to download SSTable archives to a personal workstation.

### Exercise C — Expired Certificate or CA Rotation

In an isolated environment, replace the client's trusted CA with an untrusted CA and confirm connections are rejected. Restore the valid truststore and reconnect. Propose how to monitor certificate expiration and execute CA rotation with an overlapping trust window to avoid breaking all clients simultaneously.

### Exercise D — Varying RPOs

Perform two restore drills: the first using snapshots only, and the second assuming an implemented and tested incremental + commitlog archive strategy. Compare recovery of the `10:00` event; explain why incremental SSTables alone do not guarantee capturing recent writes still sitting in memtables not yet flushed to SSTables.

### Exercise E — Single-Replica Failure

In the RF=3, CL=`LOCAL_QUORUM` lab cluster, stop one node and observe verification queries. Explain why queries still succeed with two remaining replicas, and why stopping two nodes causes failures. Document repair/backup implications rather than assuming replicas converge completely the instant a node restarts.

### Pre-Acceptance Self-Check

- [ ] Manifest accurately identifies cluster, DC, version, schema, tag, and full-node snapshot list.
- [ ] Backups were copied off-cluster, encrypted, and checksum-verified post-copy; no secrets appear in archives or manifests.
- [ ] DDL, roles, and permissions were exported/recreated separately from SSTables.
- [ ] Restore ran on an isolated target cluster with a compatible schema, capturing streaming logs and data-verification evidence.
- [ ] Post-restore, tenant A has the two pre-snapshot events and not the `10:00` event in the snapshot-only drill; tenant B has one event.
- [ ] `lab_reader` can `SELECT` but cannot `INSERT`; `lab_writer` holds only its granted permissions.
- [ ] TLS is verified against CA and hostname; plaintext and invalid certificates are rejected.
- [ ] Java Driver uses TLS, vault-sourced credentials, and a least-privilege role; post-failover connectivity is verified.
- [ ] Report documents measured RPO/RTO, replica status, compaction/repair state, and TTL/tombstone/snapshot limitations.

## 12. Recovery Drill Report Template

Use this template to present real measured results; never mark "PASS" without executing the verification:

| Item | Evidence to record | Result |
| --- | --- | --- |
| Backup coverage | Completed node count; snapshot tag; capture timestamps | `PASS/FAIL + details` |
| Archive protection | Checksums, encryption, ACLs, off-cluster storage location | `PASS/FAIL + details` |
| Restore | Loader version, SSTables/bytes loaded, errors | `PASS/FAIL + details` |
| Data verification | Keys and actions of the 3 pre-snapshot events; `10:00` event absent | `PASS/FAIL + details` |
| RBAC | Reader `SELECT` succeeds and `INSERT` rejected | `PASS/FAIL + details` |
| TLS | CA/SAN verification; plaintext/wrong-CA rejection tests | `PASS/FAIL + details` |
| Java application | Connection, prepared-statement read, CL, logs free of secrets | `PASS/FAIL + details` |
| Measured RPO/RTO | Backup/incident timestamps, full recovery completion time | `RPO/RTO + limits` |

Upon completion, learners should be able to explain that **Cassandra recovery has three tightly coupled pillars**: SSTable data backed up across the distributed topology; schemas, replication, and consistency accurately reconstructed; and access controls plus TLS independently verified from client to restored cluster. A backup has operational value only once **a restore drill proves the data is readable under the full security posture**.
