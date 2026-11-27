# Backing Up Schema, Configuration, system_auth, and Related Keys/Certificates

> **Chapter:** Backup and Recovery  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — distributed architecture, wide-column model, and Apache Cassandra operations: partition keys, query-driven table design, read/write consistency levels, CQL, replication, compaction, repair, troubleshooting, and Java connectivity.

When thinking about Apache Cassandra backups, many people think only of **business table SSTables**. Yet restoring data rows without **table definitions**, without **rebuilding datacenter/rack topology**, without **login permissions**, or without **TLS/KMS keys** still leaves the system unable to serve applications.

This lesson explains how to assemble a **recoverable backup package** consisting of: (1) CQL schema, (2) node and topology configuration, (3) authentication/authorization metadata—specifically the `system_auth` keyspace when using Cassandra's built-in mechanisms, and (4) private keys, certificates, truststores/keystores, and related secret dependencies. The focus is not on copying random folders and calling it done, but on **proving you can rebuild a test cluster in the right order** while protecting sensitive material throughout the backup lifecycle.

> **Safety:** Command examples are intended solely for lab environments with admin privileges. Backing up `system_auth` and private keys creates a highly privileged copy of sensitive data. Never upload them to public/shared stores, never put passwords into shell history, Markdown docs, tickets, or logs, and never test restores directly against a live production cluster.

## 1. Learning Objectives

After this lesson, you will be able to:

1. List the artifacts that must be backed up beyond business data, explaining **what capability each artifact restores**.
2. Export CQL schema, reconcile DDL with topology, and recognize the limits of `DESCRIBE SCHEMA`.
3. Inventory critical configuration (replication, snitch/DC/rack, JVM, native transport, commit log, compaction, auth, TLS) without embedding secrets in ordinary docs.
4. Understand why `system_auth` stores auth/authorization data and is replicated and restored **differently** from business tables.
5. Distinguish public certificates, **private keys**, keystores, truststores, passphrases, and KMS keys; design dedicated backup, access control, rotation, and recovery for them.
6. Build manifests/checksum verification and restore drills anchored to RPO/RTO, proving a Java application can authenticate over TLS and read/write post-recovery.

## 2. Which Layers Does Cassandra Recovery Actually Require?

### 2.1. Four Non-Interchangeable Layers

| Layer | Typical Components | If Missing During Restore | How to Verify |
|---|---|---|---|
| **CQL Schema** | Keyspaces, RF/strategy, tables, UDTs, indexes/SAI, materialized views, functions/aggregates, TTL/compaction options | You have SSTable bytes but mismatched schema; loaders lack data types or queries fail | `DESCRIBE KEYSPACE`, `system_schema`, app runs queries |
| **Operational Configuration** | `cassandra.yaml`, snitch/DC/rack, JVM/options, endpoints, TLS/auth, logging, data/commitlog paths | Node joins wrong DC/rack, wrong RF, fails to bind ports, or enforces wrong security policy | `nodetool status`, `describecluster`, release-specific config audit |
| **Identity and Authorization** | `system_auth` with CassandraRoleManager/CassandraAuthorizer, roles, memberships, grants; external backend if used | Admin/service accounts lose privileges or access runs under wrong policies | `LIST ROLES`, `LIST ALL PERMISSIONS`, live permission tests |
| **Crypto / Secrets** | Private keys, certificate chains/CA, keystores/truststores, passwords, KMS/key-encryption material | Client/node TLS handshakes fail; encrypted data may be undecryptable | Verified TLS handshake, expiry/chain/permission checks |

These are **independent recovery layers with dependency ordering**. SSTable backups do not automatically hold all config secrets; CQL schema exports do not back up passwords/role grants; a public certificate does not replace a private key; having config files without the keystore directory still prevents a node from starting under mandatory TLS.

~~~mermaid
flowchart TD
    A["Recoverable Cassandra Backup"] --> B["1. CQL Schema / Metadata"]
    A --> C["2. Node Config, DC/Rack, and RF"]
    A --> D["3. system_auth or IdP/ACL Backend"]
    A --> E["4. Certificates, Private Keys, and Secrets"]
    A --> F["5. Data SSTables / Incremental Backups"]
    B --> G["Restore drill on isolated cluster"]
    C --> G
    D --> G
    E --> G
    F --> G
    G --> H["Verify schema, auth, TLS, CL, Java app"]
~~~

### 2.2. "Backup Succeeded" Differs from "Recovery Succeeded"

A snapshot that was created and shows up in listings does not prove that **the full dataset**, **decryption keys**, **bootstrap credentials**, and **matching point-in-time schema** reside in the backup store. Define upfront:

- **RPO (Recovery Point Objective):** maximum acceptable loss of data/configuration changes after the recovery point. For example, a 15-minute business RPO cannot be met by daily snapshots alone.
- **RTO (Recovery Time Objective):** maximum time allowed until cluster and applications serve again, **including node startup, streaming/repair, auth restoration, and testing**.
- **Disaster scope:** a corrupted SSTable, single-node loss, full DC loss, accidental table/keyspace drop, KMS outage, or private key compromise.
- **Backup consistency boundary:** schema/auth can change while SSTables are being snapshotted. Per-node snapshots do not automatically form a **single-instant cluster-wide transaction**.

If schemas and grants evolve continuously via IaC/migrations, backup schedules should combine **event-driven exports after changes** with periodic snapshots rather than relying solely on a single cron across all layers.

## 3. Backing Up Schema: Definitions Needed to Decode and Query Data

### 3.1. Which Properties Must Be Captured?

**Keyspaces:** name, replication class (e.g., `NetworkTopologyStrategy`), RF **per datacenter**, and `durable_writes`. Recording only "RF=3" without DC names is insufficient.

**Tables:** column list/types, partition key and clustering column order, `CLUSTERING ORDER BY`, compaction strategy, compression codec/chunk size, `default_time_to_live`, `gc_grace_seconds`, caching, speculative retry, and version-specific options.

**Dependent objects:** user-defined types (UDTs), indexes (2i/SAI), materialized views, user-defined functions/aggregates, and any objects used by applications in that release. Secondary objects may require post-restore builds/rebuilds and follow dependency order.

**Version compatibility:** DDL exported from Cassandra 5.x will not necessarily run verbatim on 3.11/4.0: property names, index implementations, compaction options, and CQL features differ. Record **Cassandra release and SSTable format** alongside schema.

### 3.2. Exporting DDL with cqlsh

Example in a **secure lab terminal**, assuming connection/auth configs are stored securely rather than typed into commands:

~~~bash
# Export all describable schema from cqlsh.
cqlsh -e "DESCRIBE SCHEMA" > schema-export.cql

# Or just a specific business keyspace.
cqlsh -e "DESCRIBE KEYSPACE shop_lab" > shop-schema.cql
~~~

`DESCRIBE SCHEMA` is a **cqlsh** helper command, not a CQL query you can send directly through the Java Driver. It produces human-readable, version-controllable DDL; formatting and export scope depend on the release. **Never treat a DDL export as a data backup**: it contains no business rows, SSTable bytes, certificates, or full roles/grants state.

When the cluster enforces auth, use client config files, secret injection, or a dedicated environment with tight file permissions. Avoid `cqlsh -p <password>` since CLI arguments leak into shell history and process lists.

Inside `cqlsh`, you can inspect directly:

~~~sql
SELECT release_version FROM system.local;

SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'shop_lab';
~~~

Querying `system_schema.keyspaces` helps cross-check keyspace settings, but **does not replace full DDL** for tables/indexes/UDTs. Check schema agreement with `nodetool describecluster` before exporting; if the cluster has schema disagreement, never treat one queried node as representative of all.

### 3.3. Lab DDL Example and Recovery Order

~~~sql
CREATE KEYSPACE IF NOT EXISTS shop_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS shop_lab.orders_by_customer_month (
    customer_id uuid,
    month_bucket int,
    created_at timestamp,
    order_id uuid,
    status text,
    amount decimal,
    PRIMARY KEY ((customer_id, month_bucket), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC)
  AND gc_grace_seconds = 864000;
~~~

This is merely an example assuming DC `dc1` has enough nodes; adjust RF and topology for your lab. When recovering:

1. Provision the cluster and required identity/certificates to allow administrative connections.
2. Create **UDTs and schema in dependency order**, creating keyspaces/tables matching the SSTables/loader expectations.
3. Restore data and objects needing builds/indexing per version runbook.
4. Cross-check restored tables, partition/clustering keys, RF/CL, and query correctness.

**Never use `IF NOT EXISTS` to declare schema properly restored:** if a table already exists with a different primary key or compression setting, CQL silently skips altering it. Diff the export against actual schema and resolve mismatches explicitly.

## 4. Backing Up Configuration: Preserving Topology and Node Behavior

### 4.1. Inventory Beyond `cassandra.yaml`

Filenames and locations vary by installation method (packages, containers, Kubernetes, service managers, and releases). Collect the **actual deployed configuration**, not just Git templates.

| Group | Examples to Record | Why Needed During Restore |
|---|---|---|
| Cluster identity/topology | `cluster_name`, seed providers, listen/rpc/broadcast addresses, snitch, DC/rack | Nodes join the right cluster/ring and replica positions |
| Replication | Per-DC keyspace RF; topology/node token states | Avoid accidentally missing replicas or placing data in the wrong DC |
| Data paths | Data files, commitlog, saved caches, hints directories; mount points | Nodes locate the right storage volumes with adequate space |
| JVM and OS | Java version, heap, GC, `jvm.options`, sysctl, file limits, timezone/NTP | Preserve latency/GC behavior and file descriptor limits |
| Read/write tuning | Compaction, memtable/flush, compression, caching, commitlog sync | Avoid changing durability or I/O cost post-recovery |
| Client/network | Native transport port, internode port, firewalls, DNS, routing/load balancers | Apps can connect and nodes can communicate |
| Security | Authenticator, authorizer, role manager, TLS encryption options, secret references | Restore login, authorization, and encryption enforcement |
| Observability | Exporter/JMX configs, logging, alerting, backup schedules, repair runbooks | Detect errors and keep backups running post-restore |
| Deployment | Manifests/Helm/IaC, package versions, image digests, scripts, secret mounts | Rebuild the exact release and configuration reproducibly |

**What never to do:** copy raw `system.local`, `system.peers`, or ring-state metadata from an old node onto a replacement node assuming the cluster will accept it as a new node. That metadata binds to host IDs, tokens, gossip, and topology; **node recovery** must follow release-specific bootstrap/replace procedures rather than blindly cloning system directories.

### 4.2. Typical Config Files and Easily Lost Details

Files may live inside Cassandra's config directory or be mounted by an orchestrator:

~~~text
cassandra.yaml                 # keyspace-independent settings, auth, TLS, endpoints
cassandra-rackdc.properties    # DC/rack when using GossipingPropertyFileSnitch
cassandra-topology.properties  # topology if deployed with matching snitch
cassandra-env.sh / jvm.options # JVM/heap, version, and startup flags
logback.xml                    # logging; guard against leaking secrets into logs
cqlshrc / client trust config  # admin client or connection settings
deployment manifests / Helm    # volumes, secret references, service identity
~~~

This list is a **suggested inventory**: not every cluster uses every file. In Kubernetes, values may reside in ConfigMaps/Secrets, operator CRDs, environment variables, and external secret managers; back up both definitions and how their secret sources are restored.

Never keep config files containing keystore/truststore passwords in the same plaintext store as private keys. Keep **redacted configs** in deployment artifacts and **actual secrets** in a secret manager / separately encrypted backup. During restore tests, prove both sources combine cleanly.

### 4.3. Recording Cluster Metadata at Backup Time

Useful **read-only status** commands on an authorized node:

~~~bash
nodetool status
nodetool describecluster
nodetool version
nodetool info
~~~

Record release metadata, cluster name, nodes/DCs/racks, roles, keyspace RF, snapshot tags, and repair schedules. `nodetool status` reflects one view of the cluster at query time; if nodes are bootstrapping/decommissioning/moving tokens, **defer taking a recovery baseline backup** or explicitly flag the transitional state.

## 5. system_auth: Protecting Identities and Access Permissions

### 5.1. What Does system_auth Store?

When using built-in authentication/authorization such as `PasswordAuthenticator`, `CassandraRoleManager`, and `CassandraAuthorizer`, the `system_auth` keyspace stores corresponding data such as **roles, login capabilities, hashed password representations, memberships, and grants**. Internal table names can vary across releases, so do not rely on a hard-coded table list from any lesson.

| Component | Role | Sensitivity |
|---|---|---|
| Roles / login metadata | Identities allowed to log in, admin roles | High: exposes account structure and privileges |
| Password hashes / credential metadata | Authentication verification | **Very High**: hashes are sensitive security material, not public |
| Role memberships | Privilege inheritance across roles | High: can accidentally restore overly broad privileges |
| Resource permissions / grants | Who can SELECT/MODIFY/ALTER/... on keyspaces/tables | High: missing grants cause outages; excess grants create risk |
| Per-node permission cache | Accelerates auth/authz with a TTL | Not a durable backup |

If authentication runs **outside Cassandra** (LDAP/Kerberos/cloud IAM/custom role manager), `system_auth` **may not hold the full source of truth for identities/permissions**. Back up external configs/bindings and the corresponding IdP/KMS recovery steps; never assume a `system_auth` snapshot handles all authentication.

### 5.2. system_auth Replication Needs Separate Verification

System keyspaces have different replication rules and management workflows than business tables. In many deployments, `system_auth` starts with default replication unsuitable for production (e.g., low RF); inspect and configure it properly on multi-node/multi-DC clusters per version documentation.

In `cqlsh` with valid permissions:

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'system_auth';
~~~

**Illustrative-only** example of desired configuration for a DC named `dc1` with three real replicas:

~~~sql
-- DO NOT run in production without an approved RF change plan.
ALTER KEYSPACE system_auth
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};
~~~

**Important note:** altering RF edits metadata; it **does not automatically guarantee** new replicas hold all `system_auth` data. Afterward, follow synchronization/repair procedures, verify auth behavior, and keep release-appropriate rollback/break-glass steps ready. In multi-DC setups, declare RF for **each real DC**, considering login availability even if one DC goes down.

### 5.3. Auditing Logical Roles and Grants Before Snapshotting

Administrative CQL/cqlsh statements:

~~~sql
-- Requires appropriate permissions; never embed passwords in examples.
LIST ROLES;
LIST ALL PERMISSIONS;
~~~

If permissions are restricted, results may show only roles/permissions visible to the current account. A saved text export **does not equal a complete internal database snapshot**, especially under concurrent changes or custom auth backends.

The goal of logical inspection is cataloging roles/service accounts, memberships, and approved grants—**never exporting passwords or hashes into ordinary documents**. Avoid running `SELECT * FROM system_auth.roles` in general docs/pipelines where hashes/sensitive metadata might leak.

### 5.4. Snapshotting system_auth on Each Relevant Node

With authorized OS privileges, sample snapshot commands on the **current node**:

~~~bash
# Check release syntax before operating:
nodetool help snapshot

# Example in a lab cluster, timestamped tag:
nodetool snapshot -t auth_lab_20261121 system_auth

# Inspect existing snapshots:
nodetool listsnapshots
~~~

`nodetool snapshot` creates hard links/copies via SSTable snapshot mechanics **on the targeted node**, not a synchronized distributed snapshot across all nodes. To back up `system_auth` across relevant replicas, orchestrate across multiple nodes and record tag, host ID, tokens/ranges, keyspace/table, timestamp, and schema/repair status.

**Hard-link snapshots on the same volume are not off-site backups.** Disk failure, ransomware, or node loss can wipe both SSTables and snapshots together. Ship copies to off-cluster storage, protect with encryption and least-privilege access, and **verify restorability**.

Because auth metadata can change while snapshotting multiple nodes, never assume those captures represent **a simultaneous transaction**. Strict workflows require a change-freeze window for roles/grants, metadata manifests, and post-backup verification.

### 5.5. What Are the Main Risks When Restoring system_auth?

- **Lockout / lost access:** admin/service roles missing from the restored copy, mismatched passwords, or missing grants block connections/startup.
- **Resurrecting overly broad permissions:** old snapshots hold revoked accounts or stale grants, accidentally reopening privileges.
- **Topology/RF mismatch:** auth data loaded on only one replica/DC or unsatisfied CL causes intermittent login failures.
- **Stale auth caches:** per-node role/permission caches have lifetimes; altering SSTables manually without following a runbook yields inconsistent behavior.
- **Release/backend incompatibility:** internal `system_auth` schema, hash formats, and auth implementations change across versions; cross-version restores need officially supported plans.

**Never run `DROP KEYSPACE system_auth`, `TRUNCATE system_auth.*`, manually copy SSTables into a live serving cluster, or disable auth to "get back in quickly."** Restoring `system_auth` demands a **runbook tested specifically for your Cassandra release and auth/authz backend**, ideally in an isolated cluster first, with emergency break-glass admin access protected outside the snapshot.

## 6. Keys, Certificates, and Secrets: The Most Tightly Locked Part of Backups

### 6.1. Distinguishing Cryptographic Material

| Material | What It Holds | Publishable? | Required for Recovery? |
|---|---|---|---|
| **Server certificate** | Public key and node/server identity, validity dates, CA signature | Generally shareable per internal policy | Valid cert matching endpoint required |
| **Private key** | Signing/identity-proof key, decryption/session key setup depending on protocol | **Strictly never publish** | Valid key matching cert or re-issuance required |
| **CA certificate/chain** | Certificate chain for trust verification | Public, yet trust roots must be controlled | Clients/nodes need matching trust anchors |
| **Keystore** | Certificate container that may hold private keys | Sensitive if holding private keys | Required, or rebuildable via key/cert re-issuance |
| **Truststore** | List of trusted CAs/certs | Usually lacks private keys, still security config | Required to verify peers/CAs properly |
| **Passphrase / keystore password** | Unlocks containers / protects keys | **Secret** | Required to use saved keys or replaced with new secret |
| **KMS/HSM key or key reference** | Root/master/data-encryption keys and policies | **Highly sensitive**; some keys are non-exportable | Decryption path and proper permissions must remain intact |

**Critical point:** backing up a **public certificate while losing the private key** does not let a node prove its identity; backing up **encrypted SSTables** while losing the data-encryption key cannot recover data either. For HSM/KMS setups **that forbid key export**, the right approach is backup policies, KMS replication, break-glass accounts, and cross-region/cross-tenant restore capability—not trying to "export private key files at all costs."

### 6.2. Two Separate TLS Paths

Cassandra configures encryption separately for:

1. **Client-to-node** (native protocol): Java driver/`cqlsh` verifies node certs, optionally with mutual TLS; typically under `client_encryption_options`.
2. **Node-to-node** (internode): nodes authenticate and encrypt peer traffic per configuration; typically under `server_encryption_options`.

Never assume one keystore/truststore serves both. Each path may use different CAs, SANs, rotation schedules, and client-auth rules. Maintain an **inventory mapping**:

~~~text
Node A, dc1/rack1:
  internode certificate identity -> secret ref: cassandra/dc1/A/internode
  native transport certificate   -> secret ref: cassandra/dc1/A/client
  trusted CA chain               -> trust bundle version: vN
  renewal owner/expiry           -> per PKI inventory
  key material                   -> secret manager/KMS, NEVER in plaintext manifest

Java service orders-api:
  trust bundle reference         -> app/orders-api/cassandra-ca
  client identity (if mTLS)      -> app/orders-api/client-key
~~~

In standard manifests, store only **references** or IDs, public cert fingerprints, issuers, SANs, expiry dates, versions, and re-issuance sources. Never embed private keys, passphrases, secret tokens, or decoded Kubernetes Secrets.

### 6.3. Re-Issuance vs. Restoring the Original Private Key

Depending on PKI policy, losing a certificate on a node allows:

- **Restoring the private key from a controlled backup** if preserving the exact identity is required and the key was not compromised.
- **Issuing a new key pair/certificate** with matching SANs and trust chain if PKI permits; update keystores/truststores, nodes, Java clients, and mTLS endpoints.
- **Revoking and replacing** certs/keys if compromise is suspected. Never restore a compromised private key just because a backup still works.

If the cluster uses envelope encryption for stored data, rotating TLS certs **does not** recover data-encryption keys. Separate TLS transport identities from at-rest encryption keys and dedicated KMS workflows.

### 6.4. Securing Secret Backups

Apply all of the following together:

- Encrypt at rest and in transit; store backups separate from the cluster, manage backup encryption keys via a dedicated system, and maintain a key recovery plan.
- Enforce **least-privilege** IAM, separating operators reading private-key/`system_auth` backups from those needing only schemas or logs; audit all accesses and restores.
- Maintain rotation, revocation, and expiry monitoring; never let an ancient backup cert become your sole recovery option.
- Keep **immutable/offline** copies per anti-ransomware policies, with clear retention and secure destruction upon expiry.
- Never place private keys and passphrases in the same plaintext ZIP; consider dual control for unlocking high-security backups.
- Test restores in an isolated environment **with restricted networking and access**. Restored auth data may contain still-valid accounts/passwords.

## 7. Designing a Backup Set with a Verifiable Manifest

### 7.1. Scope and Source of Truth

A good manifest answers: **which cluster, which version, which topology, what timestamp, which objects are included, and where does the restorer fetch secrets?**

Illustrative example (containing no secret values):

~~~yaml
backup_id: cassandra-lab-20261121-0900Z
cluster: cassandra-lab
release: "5.x (record actual version)"
snapshot_window_start: "2026-11-21T09:00:00Z"
snapshot_window_end: "2026-11-21T09:07:00Z"
schema_export: schema-export.cql
auth:
  backend: CassandraRoleManager/CassandraAuthorizer
  source_keyspace: system_auth
  snapshot_tags_by_node:
    node-A: auth_lab_20261121
    node-B: auth_lab_20261121
    node-C: auth_lab_20261121
topology:
  datacenters: ["dc1"]
  node_count: 3
  replication_source: system_schema.keyspaces export
config:
  source: managed IaC revision / signed config export
secrets:
  tls_bundle_reference: "secret-manager/... (reference only)"
  backup_encryption_key_reference: "kms/... (reference only)"
verification:
  sha256_manifest: "artifact checksums kept and signed separately"
  restore_drill: "pending"
~~~

The YAML above is an **inventory template**, not a schema a built-in tool automatically consumes. Recording just one snapshot tag is not enough: inventory **nodes, tables/keyspaces, SSTable snapshot files, sizes, checksums, timestamps, and off-site copy status**. A snapshot created cleanly whose copy fails mid-flight must be marked incomplete.

### 7.2. Schema and system_auth May Not Share the Exact Same Instant

For example, at 09:00 business SSTable backup starts; at 09:02 an app runs a migration adding a column and updating permissions; at 09:07 the `system_auth` snapshot finishes. Restoring 09:02 DDL with 09:00 SSTables and 09:07 grants can cause a **mismatch** in schema/role permissions.

Therefore, use a **change-freeze window** or replayable ordered event log alongside component timestamps in the manifest. Achieving cluster-wide consistent snapshots depends on backup tooling and operational design; **per-node `nodetool snapshot` does not provide a global transaction**. For tight RPOs, add appropriate incremental backups/CDC/continuous backup strategies.

### 7.3. Checksums, Completeness, and Decryptability

After copying files off-cluster:

1. Reconcile full file lists against snapshot manifests, including required SSTable metadata and directory layouts.
2. Generate/verify **cryptographic checksums** (e.g., SHA-256) per artifact; sign manifests or use object-store integrity/versioning to prevent tampering.
3. Confirm backups are encrypted and decryption keys **remain accessible under emergency procedures**; never keep the primary key solely on the backed-up node.
4. Verify the restore process **can read** DDL, config, snapshot files, and secret references on an isolated cluster.
5. Record the latest restore drill timestamp and pass/fail outcome; matching checksums only prove bytes did not flip—**they do not prove logical recoverability**.

For regulated data, enforce retention, residency, expiry deletion, and PII handling across backups; never keep snapshots alive endlessly out of a "keep everything forever" habit.

## 8. Recovery Runbook: Right Order, Controlled Access

### 8.1. Before Restoring

**Do not apply the following steps to live production.** Execute on an isolated recovery cluster / DR staging environment and verify version/compatibility first:

1. Identify incident and goal: lost node, lost DC, dropped schema, lost auth permissions, or compromised TLS private key? A plan suited for DC loss **is not necessarily** right for credential compromise.
2. Verify manifest integrity, checksums, completeness, backup encryption, and secret sources.
3. Provision a cluster with a **supported release/JVM and topology**, matching disk, DC/rack, snitch, RF, and networking. Never clone host identity directly from an old node.
4. Set up break-glass admin access in isolation with logging/auditing; avoid accidentally exposing production connections before auth is restored.
5. Provision certificate chains/truststores/keystores and secret access; if a key was compromised, **re-issue/revoke** per policy instead of reusing it.

### 8.2. Restoring Schema and Data

High-level sequence:

~~~mermaid
flowchart TD
    A["Verify backups and secret/KMS availability"] --> B["Provision matching network/DC/rack/release"]
    B --> C["Set up TLS and break-glass access"]
    C --> D["Restore CQL schema + RF"]
    D --> E["Load data SSTables via supported mechanism"]
    E --> F["Restore/reconcile auth and grants per runbook"]
    F --> G["Sync replicas / repair where appropriate"]
    G --> H["Test TLS, CL, role permissions, Java read/write"]
    H --> I["Open traffic in controlled stages, monitor RTO/RPO"]
~~~

Note that the order between loading business data and loading `system_auth` **may need to swap** if the loader tool itself requires role authentication; this depends on your authenticator, role bootstrapping, and tooling. A runbook must spell out how to break the "need auth to load auth" cycle safely.

For table data:

- Establish exact schema and replication metadata before running loaders/restores.
- Choose between **streaming SSTables** via a release-supported loader tool, or **offline SSTable restoration** followed by refresh/streaming per runbook. The right choice depends on incident type, SSTable format, keyspace/table, topology, and version.
- Restore all SSTable snapshot components, not just `*-Data.db` files when tooling expects complete metadata.
- One node's snapshot does not replace every replica/range in the cluster; verify coverage and consistency.
- For data involving tombstones/TTLs, **never blindly restore old copies** into a cluster holding newer writes: deleted values can resurrect or timestamp conflicts can arise. Follow a valid reconcile/replace plan.

### 8.3. system_auth Needs Its Own Dedicated Restore Drill

There is no universal `cp` or `sstableloader` one-liner to restore `system_auth` across all versions. Specific steps must be approved and **tested per release, auth backend, topology, and loader**, checking:

- Restored role/grant scope reflects the **desired business point in time**, without re-enabling accounts disabled after a security incident.
- Internal `system_auth` schema matches; replication spans the right DCs and data is loaded/repaired across sufficient replicas per runbook.
- Auth/permission caches and privilege propagation are accounted for, rather than assuming every node reflects changes instantaneously without verification.
- Separate break-glass admin exists, superuser passwords stay out of YAML/Markdown, and client traffic opens only after live verification.
- If using custom IAM/LDAP/Kerberos, **restore the corresponding IdP/external ACLs/keytabs** before declaring auth ready.

Never equate **restoring permissions** with **restoring old secrets**. Compromised incidents may require password resets/rotations, token revocation, or certificate re-issuance to satisfy security policy.

### 8.4. Verification from Cassandra and Java

In `cqlsh` with valid admin privileges:

~~~sql
SELECT release_version FROM system.local;

SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name IN ('shop_lab', 'system_auth');

LIST ROLES;
LIST ALL PERMISSIONS;
~~~

On each node:

~~~bash
nodetool status
nodetool describecluster
nodetool tablestats shop_lab.orders_by_customer_month
nodetool netstats
nodetool compactionstats
~~~

Check schema agreement, nodes in Up/Normal state, correct RF and DC/rack layout, no stalled streams, disk headroom, and query latency. These checks **do not automatically prove** every business row recovered; cross-check checksums/row sets and representative queries across all token ranges.

Java Driver 4.x example, assuming `CqlSession session` is built **with TLS, truststore, authentication, and local DC properly configured**:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;

// session is initialized from externalized security config outside source code.
PreparedStatement ps = session.prepare(
    "SELECT created_at, order_id, status " +
    "FROM shop_lab.orders_by_customer_month " +
    "WHERE customer_id = ? AND month_bucket = ?");

BoundStatement statement = ps.bind(
        UUID.fromString("d654b0fe-7357-497f-8db4-59b165d58a0f"),
        202611)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(100);

ResultSet result = session.execute(statement);
int rows = 0;
for (Row row : result) {
    row.getUuid("order_id");
    rows++;
}
// Reconcile counts/keys and business data against the verification set.
~~~

Here, a successful request proves at minimum that **TLS handshake, authentication, authorization, and data reads** work on that query path. Yet one SELECT does not verify all grants, all token ranges, or RPO compliance; add positive/negative permission tests, authorized writes, checksummed sample data, and multi-DC checks where applicable.

**Critical negative test:** an account granted only `SELECT` must be rejected on `MODIFY`; a revoked account must fail login. Recovering data rows while accidentally widening permissions is a security failure.

## 9. Restore Testing Checklist and RPO/RTO Evaluation

| Item | Passing Check | If Failing |
|---|---|---|
| DDL | Keyspaces, tables, types, indexes/views, RF/CL/compaction match manifest | Fix schema order, release mapping, or migrations |
| Cluster topology | Node/DC/rack/host identities and streaming complete | Fix topology/bootstrap/replace per runbook |
| system_auth | Roles, memberships, grants, backend, RF, and admin access match | Safely restore roles/grants in staging; keep traffic closed |
| TLS | Chain/SAN/expiry, mTLS if enabled, node-to-node and client-to-node valid | Re-issue/restore secrets from proper source; revoke leaked keys |
| KMS / backup encryption | Files decrypt via audited process; no keys in source repo | Restore KMS access/key dependencies without bypassing security |
| Business data | Sample keys and multi-partition/token-range coverage; timestamps/TTLs/tombstones match expectations | Audit snapshots/loader and point-in-time consistency |
| Java clients | Right local DC, TLS auth, SELECT/MODIFY permissions, p95/p99, retry errors | Fix trust bundle/credentials/CL or permissions |
| RPO/RTO | Recovery point and elapsed duration within committed targets | Adjust backup schedule and DR automation |
| Subsequent backups | Post-restore backup schedule, retention, alerting, and periodic restore drills active | Restore continuous protection |

**Never treat "cluster is Up/Normal" as sufficient.** A cluster can look healthy while missing keyspaces, carrying wrong grants, holding soon-to-expire private keys, or serving apps using invalid CL for the new DC.

### 9.1. Metrics to Measure During Drills

Sample report template—populate values **from real drills**, never fabricate numbers:

| Metric | Measured Result | Approved Target | Pass/Fail |
|---|---|---|---|
| Time from detection to admin access | _fill in_ | _fill in_ | _fill in_ |
| Time to rebuild TLS/credentials | _fill in_ | _fill in_ | _fill in_ |
| Time until schema and system_auth ready | _fill in_ | _fill in_ | _fill in_ |
| Time to restore/stream data | _fill in_ | _fill in_ | _fill in_ |
| Latest recoverable data timestamp | _fill in_ | Per RPO | _fill in_ |
| Java service passes read/write checks | _fill in_ | Per RTO | _fill in_ |
| Roles/grants reconciled count | _fill in_ | Per inventory | _fill in_ |
| Revoked/expired certificate test | _fill in_ | Connection rejected | _fill in_ |

A quick drill on one node does not substitute for multi-DC recovery, network splits, and real security constraints. In production, plan enough storage/headroom for recovery; restoring can drive streaming, compaction, and repair load that shifts p99 latency.

## 10. Common Mistakes and Fixes

| Misconception | Consequence | Correct Approach |
|---|---|---|
| "SSTable snapshots include full schema and permissions" | Restore lacks table definitions, roles, or grants | Export DDL, inventory `system_auth`, and back up config/secrets separately |
| "`DESCRIBE SCHEMA` is a full database backup" | Missing data rows and TLS keys | Save snapshots/incrementals and secret dependencies |
| "`system_auth` is just system data, no backup needed" | Login failures or lost privileges after DR | Back up securely per auth backend and test restores |
| "Having the public certificate is enough" | No private key to prove identity | Securely preserve keys or maintain re-issuance/revocation plans |
| "Password hashes are not secrets" | Leaks credential material and privilege structure | Classify `system_auth` snapshots as highly sensitive |
| "Store secrets in plaintext config files for convenience" | Leaks both keys and passwords if one artifact leaks | Separate secret manager and audited encrypted backups |
| "One node's snapshot is a cluster-wide backup" | Missing token ranges/replicas and sync metadata | Maintain per-node/range manifests and verify coverage |
| "Restore data first, figure out schema later" | Loader lacks column/type definitions or fails compatibility | Build schema and dependencies in exact order |
| "Changing `system_auth` RF auto-syncs replicas" | Logins fail intermittently across nodes/DCs | Run repair/streaming per runbook and verify roles on multiple nodes |
| "Copy old node's `system` folder to a new node" | Collides on host ID/token/gossip metadata; risks cluster failure | Bootstrap/replace properly and restore only data per guide |
| "If a key leaks, restoring from backup is safe" | Compromised key remains trusted | Revoke/rotate and re-issue; audit access |
| "Restore drill passed because SELECT returned one row" | Misses grants, token ranges, TTL/tombstones, and RPO | Verify representative datasets, positive/negative auth, TLS, checksums |
| "Disable auth/TLS briefly in production to restore" | Opens intrusion risk and policy drift | Use isolated, controlled, audited break-glass runbooks |

## 11. Scenario Exercises

### Exercise 1 — What Is Missing from the Backup?

Team A copied only SSTables for keyspace `shop_lab` along with a `schema-export.cql` file. After a full DC disaster, the Java app cannot log in and TLS handshakes fail. List at least **three missing artifact groups**.

**Hint:** `system_auth` or IdP/ACL backend, private keys/keystores/truststores/CAs and passphrases/KMS, and node/DC/rack/port/auth/TLS configuration. Snapshots of multiple replicas and repair/topology inventory may also be missing.

### Exercise 2 — Why Protect system_auth Differently from Ordinary Data?

An engineer argues `system_auth` only holds password hashes so its snapshots can sit in a public read-only bucket. Is this decision safe?

**Hint:** No. Hashes, role memberships, and grants are sensitive security data; exposure aids offline cracking and privilege analysis. Enforce encryption, access controls, auditing, retention, and least-privilege policies.

### Exercise 3 — Permission Changes Between Snapshots

09:00 business data snapshot; 09:03 `old_admin` account revoked; 09:05 `system_auth` snapshot. What state can the end-of-day backup restore? If the auth snapshot was actually captured at 08:55, what divergence risk arises?

**Hint:** Exact timestamps of each artifact must be recorded. A post-revocation auth snapshot excludes the old grant; a pre-revocation snapshot can **re-enable** `old_admin`'s privileges. During security incidents, prioritize live revocation/rotation rather than blindly trusting old backups.

### Exercise 4 — Lost KMS Key

SSTable backups are intact with matching checksums, but the at-rest decryption key existed only in the lost region's KMS. Can you recover?

**Hint:** Not necessarily—and potentially **impossible** if no key recovery path exists. Checksums do not replace keys. Design KMS replication/key escrow policies or KMS DR before disasters hit, and test in isolation.

### Exercise 5 — Drill Plan

Write a one-page runbook to restore a three-node lab cluster: list artifacts, owners, restore sequence, 5 verification checks, and RPO/RTO. For security testing, require one read-only account to pass `SELECT` while being denied `MODIFY`.

**Hint:** Combine schema + configuration + `system_auth` + TLS/KMS + SSTables + manifests/checksums; check RF/CL, role grants, TLS chains, Java read/write, and repair/streaming status. Specify where break-glass admin is needed and keep plaintext secrets out of files.

### End-of-Lesson Checklist

- [ ] Distinguish business data backups from schema, config, `system_auth`, and secret material.
- [ ] Know `DESCRIBE SCHEMA`/`DESCRIBE KEYSPACE` export only DDL, not row data.
- [ ] Know why auth data/grants must be backed up per actual backend and replication.
- [ ] Keep password hashes/private keys/keystore passphrases out of docs and public stores.
- [ ] Distinguish public certs, private keys, truststores, keystores, and KMS/data-encryption keys.
- [ ] Maintain manifests by node/tag/timestamp/version/topology/RF with checksums and auditing.
- [ ] Know a snapshot on the current node is not a cluster-wide global transaction.
- [ ] Never blindly restore ring/host-identity metadata from old nodes.
- [ ] Run restore drills verifying positive/negative authorization, TLS, and Java CQL.
- [ ] Measure RPO/RTO and maintain rotate/revoke plans for secret compromise.

## 12. References

1. Apache Cassandra Documentation — [Backup and restore](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/backups.html): snapshots, incremental backups, and recovery limits.
2. Apache Cassandra Documentation — [nodetool snapshot](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/snapshot.html) and [listsnapshots](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/listsnapshots.html): per-node operations.
3. Apache Cassandra Documentation — [CQL data definition](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html): schemas, keyspaces, tables, and options.
4. Apache Cassandra Documentation — [Security](https://cassandra.apache.org/doc/stable/cassandra/operating/security.html): authentication, authorization, and TLS.
5. Apache Cassandra Documentation — [cassandra.yaml](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html): topology, authentication, and encryption options.
6. Apache Cassandra Documentation — [Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html): post-incident replica sync and tombstone risks.
7. Apache Cassandra Documentation — [cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): admin commands and DDL export.
