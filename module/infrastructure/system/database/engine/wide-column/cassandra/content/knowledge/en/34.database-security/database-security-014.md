# Protecting Backups, Configurations, Logs, and Test Data

> **Chapter:** Security  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Context:** Apache Cassandra is a distributed wide-column database. Data protection must span the entire lifecycle: partition-key and query-driven table design, CQL execution, replication, consistency levels, compaction/repair, backup/restore, and Java application access.

## 1. Objectives and Opening Scenario

Suppose a Cassandra cluster serving an order system has TLS enabled, requires application authentication, and enforces role-based authorization. Later, an operations team takes snapshots, copies SSTables to a backup bucket, streams query records into a logging system, and downloads a production copy to a test machine to verify recovery. Even though the application connection to Cassandra is secured, customer data can still leak through **backups, decryption keys, config files, logs, or test environments**.

Cassandra security must cover both the **live data path** and **operational data copies**. This lesson helps you:

1. Identify assets and trust boundaries across snapshots, incremental backups, commit logs, configurations, logs, and test data.
2. Design off-fault-domain backups with **encryption, access control, integrity, retention, and restorability**.
3. Keep passwords/tokens/private keys out of repositories, scripts, CLI arguments, logs, and broadly distributed configs.
4. Bound the contents of logs, traces, metrics, and incident tickets so you can observe the cluster without exposing sensitive data.
5. Choose synthetic data or de-identified data for test environments while preserving the Cassandra properties you need to measure.
6. Use checklists and exercises to verify protections **without assuming "enabling TLS is enough."**

**Key distinction:** security configurations are inputs; **reading back backups with the right permissions, verifying data, and recovering during an incident** are the operational outcomes that must be tested.

## 2. Identifying Assets, Entry Points, and Failure Domains

### 2.1. Assets Are More Than Live Tables

| Asset | What Can It Contain? | Typical Risk |
|---|---|---|
| SSTables on nodes | Partition keys, clustering keys, column data, timestamps, tombstones, and metadata | Reading raw data if disks or files are obtained |
| Local snapshots | SSTable components at snapshot time; typically hard links | Copies remain on node volumes with broad file permissions or forgotten cleanup |
| Incremental backups, commitlog archives | Additional SSTables and mutations for version-supported recovery | Secondary datasets not encrypted/controlled like primary snapshots |
| Object-storage backups | Multiple data versions, schemas, manifests, recovery logs | Exfiltration, overwrites or mass deletion, missing decryption keys during incidents |
| Node/app configurations | Credentials, cluster addresses, TLS settings, permission policies, cert/key paths | Secrets leaked via Git, developer laptops, build artifacts, logs |
| Logs, audits, traces, crash dumps | Client IPs, roles, CQL, errors, stack traces, bind values if logged by apps/tools | Concentrating sensitive data outside database retention policies |
| Test/restore copies | May contain near-verbatim production data | Users with broader test access than production can read real data |

**Replicas are not backups.** Replication strategies and consistency levels maintain availability when nodes fail; replicas still receive the exact same `DELETE`/`UPDATE` commands and do not keep independent history to roll back bad operations. **Repair** reconciles replica differences rather than distinguishing valid business deletes from mistakes.

### 2.2. Modeling Attackers and Accidental Mistakes

A practical design should ask:

- If an application token leaks, **which keyspaces** can an attacker read? Can they read the backup bucket?
- If a cluster admin account is compromised, can it **delete all backup versions** and disable retention locks?
- If the entire primary region goes down, where are the **backup decryption keys** stored and who is authorized to use them?
- If staff attach logs to support tickets, do those logs contain passwords, JSON payloads, tenant IDs, or query values?
- If developers pull copies to laptops, is data still protected at production standards?
- When an application deletes data under legal requirements, do copies in backups and test environments comply with retention/deletion policies?

Selected controls must match **specific threats and failure domains**. Storing backups in another region protects against regional outages, yet fails against accidental deletion if the same admin privilege can wipe both places.

## 3. What Do Cassandra Backups Contain and Why Must They Be Protected Separately?

Cassandra writes data to **memtables** and flushes them to **SSTables**. Snapshots typically hold hard links to SSTable files on the node. That makes snapshots fast, yet snapshots **do not leave the node automatically and are not encrypted merely because CQL connections use TLS**.

~~~mermaid
flowchart LR
    A["CQL write / Java driver"] --> B["Coordinator and replicas"]
    B --> C["Commitlog + memtable"]
    C --> D["Flush → SSTable"]
    D --> E["Per-node snapshot"]
    E --> F["Package + manifest + checksum"]
    F --> G["Encrypt and transfer over trusted channel"]
    G --> H["Independent backup repository"]
    H --> I["Restore in isolated environment"]
~~~

A backup set may require several file types:

- **Snapshot SSTables** covering all required token ranges and tables.
- **Incremental SSTables** if using version-supported incremental backup chains.
- **Commitlog archives** if designing for point-in-time recovery (PITR); requires strict replay boundaries so erroneous deletes are not replayed.
- **CQL schemas**, UDTs, version/table IDs, replication/DC/rack settings, partitioner, required configs, and cutoff records.
- **Manifest** describing backup ID, nodes, token coverage, filenames, byte sizes, digests, creation timestamps, upload status, and decryption metadata.

**Never assume one node's snapshot holds all data.** Cassandra partitions by token; even with RF greater than one, each node holds only the partitions for which it is a replica. Cluster-wide backups require coordinating across nodes/token ranges and verifying completeness.

### 3.1. Common Misconceptions

| False Assumption | Reality to Verify |
|---|---|
| "Cassandra TLS encrypts snapshots on disk." | TLS protects configured network transit; protecting backup files at rest requires separate mechanisms |
| "RF = 3 means three independent backups." | Three replicas receive the same logical mutations; valid data loss/deletion propagates to all three |
| "`nodetool snapshot` already uploaded the backup." | Snapshot is a local operation on the targeted node; upload/verification is run by a separate pipeline |
| "The bucket is encrypted so anyone can download copies." | Encryption does not replace authorization, auditing, and data-usage limits |
| "Having SHA-256 completely prevents file tampering." | Digests detect tampering only when expected hashes are protected; an attacker able to edit both file and manifest still passes unauthenticated checks |
| "Backup upload finished means it is restorable." | Requires schema, keys, compatible versions, and passing restore drills |

## 4. Protecting Backups: Confidentiality, Integrity, Availability

### 4.1. Confidentiality: Encryption in Transit and at Rest

A backup pipeline should use:

1. **Authenticated encrypted channels** between nodes/agents and the repository; allow only valid endpoints.
2. **Encryption at rest** via approved object/volume mechanisms; consider client-side encryption to separate storage operators from key holders.
3. **Centralized key management** via KMS/HSM or an appropriate secret store, with rotation policies, decryption session controls, and auditing.
4. **Key recovery design:** if the primary failure domain is lost, can recovery roles still reach decryption keys and metadata?

Server-side and client-side encryption carry different trust models. With client-side encryption, retain enough algorithm info, key IDs, nonces/IVs, or envelope metadata to decrypt—**never store raw secret keys inside the manifest**.

Encryption should provide proper integrity/authenticity protection, such as authenticated encryption at the file layer; a plain checksum mainly catches accidental corruption when reference values are protected.

### 4.2. Integrity: Manifests, Digests, and Provenance

Logical manifest example defined by a backup team:

~~~json
{
  "backup_id": "cassandra-example-20261121T0200Z",
  "status": "COMPLETE",
  "cluster": "example-cluster",
  "scope": ["shop"],
  "data_cutoff_utc": "<verified-or-unknown>",
  "cassandra_version": "<actual-version>",
  "schema_object": "<protected-object-key>",
  "files": [
    {
      "node_id": "<node-identifier>",
      "token_scope": "<recorded-coverage>",
      "path": "<relative-path>",
      "bytes": 204800,
      "sha256": "<trusted-digest>"
    }
  ],
  "encryption_key_reference": "<key-id-not-secret>",
  "manifest_signature_reference": "<optional-signature-object>"
}
~~~

This is an **illustrative metadata template**, not a built-in Cassandra format. A trustworthy system must verify:

- Node counts, tables, SSTable components, and token ranges match the backup strategy.
- File sizes and digests; manifests/digests must be **authenticated or stored in a separate privilege domain** so attackers cannot alter both data and checksums.
- Backup status transitions to **COMPLETE** only after upload, digest checks, key checks, and mandatory metadata all pass.
- File provenance, backup ID, Cassandra/JDK versions, and cutoff timestamps are traceable during incidents.

On a **separate verification host**, you can compute/check checksums for readable authorized files:

~~~bash
sha256sum snapshot-file.db

# Trust results only when the reference checksum file comes
# from an independent or authenticated source.
sha256sum -c backup.sha256
~~~

Never put filenames containing customer info or bucket URIs containing access tokens into public logs. Digests detecting tampering do not prove source files contain valid business data—verify **provenance** and restorability.

### 4.3. Availability: Preserving Copies When the Primary Failure Domain Is Destroyed

A backup must survive the failure it is designed against:

- **Location isolation:** store off-volume, off-node, and off-AZ/region when scenarios require.
- **Privilege isolation:** the backup writer account should not hold rights to delete all versions; Cassandra admin roles must not automatically govern backup buckets.
- **Deletion limits:** retention, versioning, and WORM/object-lock/immutability per platform capabilities and business policy.
- **Appropriate key separation:** never let one IAM/KMS/region outage render every backup undecryptable.
- **Clean pre-error points:** continuously backing up a mistakenly deleted state does not replace retention of older recovery points.
- **Test downloads:** measure bandwidth, decryption time, and readability in scenarios assuming the primary failure domain is gone.

**Immutability is not immortality:** manage retention periods, elevated admin controls, lifecycles, and key recovery. Also respect data-deletion regulations; immutable backups can conflict with personal-data erasure policies, so plan retention/expiry schedules upfront.

## 5. Role-Based Backup Permissions and Least Privilege

Separate roles:

| Role | Typically Needed Rights | Rights to Restrict |
|---|---|---|
| Node snapshot agent | Snapshot scoped keyspaces/tables; read files to upload | Cluster-wide role changes, dropping keyspaces, unrelated config edits |
| Uploader | Write objects to target prefix/bucket; read verification metadata | Deleting all backup versions; accessing other environments' buckets |
| Verifier | Read manifests, sample files, verify digests and status | Overwriting snapshots or altering retention |
| Restore operator | Read selected backups, use decryption keys per workflow, build target cluster | Accessing all data stores or auto-writing to production |
| Backup administrator | Manage schedules, retention, and policies per approval | Sharing credentials with business apps or DB nodes |
| Auditor | Read evidence, policies, and operational events | Reading full customer payloads unnecessarily |

Exact object-storage/IAM/KMS permissions vary by provider. The table above defines **responsibility boundaries**, not copy-paste policies.

### 5.1. Note on Cassandra Permissions

Cassandra provides **authentication**, **authorization**, and **roles** depending on config/version. If a service only reads one table, never give it broad admin privileges. In an authorization-enabled environment, inspect rights per version syntax:

~~~sql
-- Use only when the operator holds inspection rights with approval.
LIST ROLES;
LIST ALL PERMISSIONS;
~~~

These commands can expose sensitive role/permission details; store outputs in an access-controlled evidence store. **CQL role permissions do not govern backup buckets, KMS, filesystems, Kubernetes Secrets, or CI/CD.** Control each layer separately.

Never put real passwords in `CREATE ROLE ... WITH PASSWORD = '...'` examples committed to repositories or shared in chats/tickets. Use managed secret provisioning and separate deployment rights.

## 6. Secrets and Config Files: Separating Shareable Config from Confidential Data

### 6.1. Where Secrets Commonly Leak

- Cassandra/driver/app config files, environment variables, CLI arguments, or service-manager unit files.
- **CI logs**, verbose/debug shell output, or build artifacts.
- Truststore/keystore files and their passwords; TLS private keys; object-storage, KMS, and monitoring/JMX credentials.
- Config backups, project directory archives, and VM snapshots.
- Stack traces, exception messages, request/response logs, or tickets attaching full configs.

**Not every config field is a secret.** Datacenter names, contact points, ports, or replication settings are operational details whose sharing scope should be controlled; passwords, API tokens, private keys, and session credentials are secrets needing far stricter handling.

### 6.2. Safer Application Configuration Pattern

Split responsibilities:

1. **Repository:** holds only secret-free templates; non-secret settings undergo review.
2. **Secret store:** holds credentials, private keys, or key-identifier references, with access control and rotation.
3. **Runtime:** apps obtain secrets via platform-managed mechanisms without printing values to logs. Environment variables are convenient yet not foolproof—they can leak via crash dumps, process inspection, debugging, or runtime configs.
4. **Deployment:** file/volume permissions and secret access match the service account; avoid bundling whole config folders into public artifacts.
5. **Rotation:** accounts/keys have owners, lifecycles, replacement workflows, and post-rotation connection tests.

Configuration template without sensitive values:

~~~yaml
# Illustrative application.yml containing no real passwords
cassandra:
  localDatacenter: dc1
  contactPoints:
    - cassandra-internal.example:9042
  auth:
    usernameSecretRef: "secret-store://orders/cassandra/username"
    passwordSecretRef: "secret-store://orders/cassandra/password"
  tls:
    trustBundleRef: "config-store://cassandra/cluster-ca"
~~~

This is an **application-defined illustrative format**, not a standard config automatically understood by Cassandra or the Java Driver. **Secret references** only work when the deployed application integrates a resolver and handles permission/rotation errors.

### 6.3. Node Configuration: Verify Effective Values

For Cassandra, relevant mechanisms include:

- **Client-to-node encryption** for CQL/native protocol connections.
- **Server-to-server encryption** for internode traffic.
- **Authenticator** and **authorizer**, roles/permissions.
- Management/JMX access controls and the OS account running Cassandra.
- Depending on version/distribution: audit logging, encryption at rest, or KMS integrations.

**Parameter names and support vary by version**, so verify against docs for your running Cassandra/JDK. Never claim "enabling TLS encrypts every file on disk," and never disable certificate checks just to silence connection errors.

For truststores, CA certificates may not be secret, yet **private keys and keystore passwords** must be protected. Verifying hostnames, cert chains, expirations, and access permissions belongs in deployment and recovery testing.

## 7. Java Driver: Connecting and Logging Without Leaking Information

Java apps can use **prepared statements** and **bind** typed values to avoid concatenating data into CQL strings. However, prepared statements do not keep data safe if the app subsequently logs every `BoundStatement` or column value.

Example session setup receiving secrets/TLS from the app's management layer:

~~~java
import java.net.InetSocketAddress;
import java.util.UUID;
import javax.net.ssl.SSLContext;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public class OrderReader {
    public interface Credentials {
        String username();
        String password();
    }

    // SSLContext must be configured with proper CA/server verification.
    public static void readOrder(
            Credentials credentials,
            SSLContext trustedTlsContext,
            UUID customerId,
            String orderMonth) {

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(
                        "cassandra-internal.example", 9042))
                .withLocalDatacenter("dc1")
                .withAuthCredentials(
                        credentials.username(), credentials.password())
                .withSslContext(trustedTlsContext)
                .build()) {

            PreparedStatement statement = session.prepare(
                "SELECT created_at, order_id, status " +
                "FROM shop.orders_by_customer_month " +
                "WHERE customer_id = ? AND order_month = ? LIMIT ?");

            var result = session.execute(
                    statement.bind(customerId, orderMonth, 20));

            int rows = 0;
            for (var row : result) {
                // Do not print customer ID, payload, or credentials.
                rows++;
            }
            System.out.println("Query completed; rowCount=" + rows);
        }
    }
}
~~~

**Example notes:**

- Uses **Java driver 4.x** under `com.datastax.oss.driver.api` purely to illustrate API usage; the environment needs matching dependencies, keyspace/table, and server TLS configured.
- **Credentials** and **`SSLContext`** must come from verified resolvers/resources; the example embeds no secrets and prescribes no specific secret store client.
- In real applications, **`CqlSession`** and **`PreparedStatement`** are long-lived and reused rather than created per read; the session opens inside the method only to keep the snippet self-contained.
- **`SSLContext`** must verify CAs and server identities per driver/version connection policy; never use a trust-all context.
- **`rowCount`** is low-sensitivity here, though even row counts can be sensitive in some domains. Real systems must classify log fields before collection.
- To support Java versions older than Java 10, replace `var` with explicit `ResultSet`/`Row` types.

**Strictly avoid** logging passwords, session tokens, private keys, full `SELECT` results, or raw `BoundStatement`s carrying customer values. When identifying queries for tuning, log a **query shape ID** or operation name rather than dumping all bind values.

## 8. Protecting Logs, Audits, Traces, and Diagnostic Data

### 8.1. Field Classification and Data Minimization

| Source | Keep for Operations | Avoid or Strictly Protect |
|---|---|---|
| App / Java driver | Operation name, duration, status/error code, correlation ID, retry count, permitted node/DC | Passwords, tokens, bind values, payloads, PII, full customer queries |
| Cassandra server | Node health, GC, compaction, repair, read/write timeouts, aggregate auth errors | Data payloads, paths containing secrets, stack traces with sensitive details |
| Audit logs | Who did what, when, from where, allow/deny outcome | Passwords, private keys, unnecessary returned data |
| Query tracing | Coordinator/replica path and execution timings during diagnosis | Query text/bind values if collected by tools/apps, sensitive topology info |
| Backup pipeline | Backup ID, file count, digest/status, duration, error code | Signed URLs, vault credentials, sensitive raw manifests, KMS secrets |
| Support tickets | De-identified error summary, timestamp, trace ID, vetted metric snapshots | Raw log dumps, table copies, unredacted customer IDs |

**Note:** some telemetry tools or proxies can capture CQL with bind values depending on configuration. Never guess that drivers/servers strip sensitive values—**verify actual log pipelines**, including error messages, tracing, APM, and exception handlers.

### 8.2. Safe Application Logging Rules

Instead of:

~~~text
WARN failed query="INSERT INTO orders ...", password="...", payload={...}
~~~

Prefer structured records:

~~~json
{
  "event": "cassandra_request_failed",
  "operation": "orders_by_customer_month.insert",
  "request_id": "req-8f2c",
  "consistency_level": "LOCAL_QUORUM",
  "error_class": "WriteTimeout",
  "duration_ms": 1200,
  "retry_attempt": 0
}
~~~

This JSON is an intentionally data-minimized log example, not fields emitted automatically by the driver. **`request_id`** must reveal no PII and never replace authentication; avoid using raw partition keys as correlation IDs if they contain customer data.

When investigating slow queries, log **query shapes** ("SELECT... WHERE tenant_id = ? AND day = ?"), page sizes, contacted replicas, CL, p95/p99, and controlled trace IDs. Enable **Cassandra query tracing** only for targeted diagnostic requests/environments and turn it off afterward; tracing adds overhead and captured data requires its own retention and access controls.

### 8.3. Masking Differs from Eliminating the Source

**Redaction** must occur as early as possible, before payloads cross trust boundaries. Masking only at dashboard display time can still leave raw originals sitting inside unprotected log pipelines/buckets.

Also enforce:

- Separate retention for **operational logs, audit logs, security logs, traces**, and forensic evidence.
- Role-based log access controls; audit log reads and exports.
- Encrypted log storage/transit and controls on forwarding logs to third-party services.
- Protection for **core dumps, heap dumps, thread dumps, and JVM diagnostic bundles**, which can hold data or credentials.
- Incident procedures when secrets or PII leak into logs: stop further leakage, revoke/rotate secrets, restrict access, purge copies per policy, and assess impact.

## 9. Test Data and Restore Drills: Choosing the Right Sensitivity Level

### 9.1. Prefer Synthetic Data

**Synthetic data** is generated for testing from rules and simulated distributions without copying real customer records. It should be the default for CI, tutorials, small-scale benchmarks, and CRUD logic tests.

Example CQL schema for synthetic data:

~~~sql
CREATE KEYSPACE IF NOT EXISTS lab_shop
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS lab_shop.orders_by_customer_month (
    customer_id uuid,
    order_month text,
    created_at timestamp,
    order_id uuid,
    status text,
    amount decimal,
    PRIMARY KEY ((customer_id, order_month), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);

INSERT INTO lab_shop.orders_by_customer_month
    (customer_id, order_month, created_at, order_id, status, amount)
VALUES
    (11111111-1111-4111-8111-111111111111,
     '2026-11',
     '2026-11-21T04:00:00Z',
     22222222-2222-4222-8222-222222222222,
     'CREATED', 125.00);
~~~

UUIDs are **dummy fixtures** only. When running on a single-node cluster, adjust RF to match the environment—never assume RF = 3 and `LOCAL_QUORUM` behave like production on one node.

### 9.2. When Production-Like Data Is Needed

Sometimes you need to reproduce hotspots, partition sizes, tombstones, TTLs, compaction, or rare query shapes. When synthetic data cannot represent them adequately, consider **policy-approved processed data** in an isolated environment.

| Approach | Benefit | Known Limitations |
|---|---|---|
| Synthetic data | Minimal risk of exposing real customers | Distribution must be designed carefully to stay representative |
| Pseudonymization | Preserves stable mapping for joins/reconciliation | Still re-identifiable; mapping tables and keys must be protected |
| Masking/tokenization | Hides sensitive fields per policy | Can distort data distributions or leak metadata |
| Aggregation | Eliminates per-record exposure | Unsuitable for many consistency/restore tests |
| Controlled production copy | Most faithful to real data | High risk; demands approval, isolation, tight RBAC, retention, and deletion workflows |

**Plain hashing does not guarantee anonymization**, especially over small domains (emails, phone numbers, area codes, birth dates). On partition keys, changing values alters tokens too; test designs must verify whether hotspots, partition distributions, row sizes, and clustering order remain representative. When realistic load testing is required, generate synthetic data from **statistical distributions** rather than copying real identities.

### 9.3. Pre-Test Data Checklist

1. Define purpose, column scope, retention deadline, and data-handling owner.
2. Prefer synthetic data; if real data is required, obtain formal approval and legal basis.
3. Select fields to remove/transform: names, emails, phones, addresses, tokens, payloads, documents, device IDs, payment details.
4. Protect transformation mappings/seeds/keys—never place them inside easily accessible test stores.
5. Separate accounts, networks, secrets, buckets, KMS, and logs from production; block test environments from accidentally reaching production.
6. Verify test apps cannot send emails, SMS, webhooks, payment events, or unintended side effects to real users.
7. Set TTLs/retention on data copies, test snapshots, and logs produced during testing.
8. Scan for residual sensitive data after transformation and before opening access to testers.
9. Record dataset version, generation method, owner, access scope, and deletion date; purge all auxiliary files afterward.

**Restoring a production snapshot into test** must be treated as production-sensitivity data handling until de-identification is verified complete. Never slap a "test" label on it and lower controls by default.

## 10. Building a Backup and Restore Pipeline with Clear Protection Layers

~~~mermaid
flowchart TD
    A["Cassandra nodes / SSTable snapshot"] --> B["Least-privilege backup agent"]
    B --> C["Manifest: coverage + timestamp + checksum"]
    C --> D["Encrypt / authenticate data"]
    D --> E["TLS upload to independent repository"]
    E --> F["Verify digests, permissions, and decryptability"]
    F --> G{"Backup complete and readable?"}
    G -->|No| H["Do not mark COMPLETE; alert"]
    G -->|Yes| I["COMPLETE + retention/immutability"]
    I --> J["Approved restore to isolated cluster"]
    J --> K["Verify CQL/Java and business reconciliation"]
    K --> L["Record RPO/RTO and audit logs"]
~~~

Each step has distinct duties:

**On nodes:** run under a least-privilege service user, protect snapshot folders, and watch disk space. Local snapshots retain old SSTables past compaction and can fill disks if not cleaned per retention.

**In transit:** use TLS with endpoint verification; avoid long-lived credentialed links, and forbid tokens in CLI history/logs.

**At rest:** enforce encryption at rest, prefix-scoped IAM policies, separated deletion/admin roles, retention, and key checks.

**During verification:** compute/compare checksums, verify signatures or trusted manifest sources, validate metadata, and catch missing nodes/tables/SSTable components. Mark `COMPLETE` only once all mandatory checks pass.

**During restore:** pick a clean point, use a dedicated recovery role and isolated cluster, restrict backup access, measure RPO/RTO, and test CQL/Java queries by partition key. Never drop old SSTables directly into a live writing production cluster, which risks schema/TTL/tombstone corruption and zombie data resurrection.

**During cleanup:** prune local copies per policy only after off-node backups pass verification; keep backups per retention and compliant erasure workflows. Cleanup must keep audit trails and guard against accidental bulk deletion.

## 11. Verifying Configs, Logs, and Backups Without Exposing Secrets

An inspection session can follow these steps using appropriate permissions and **test** data:

### 11.1. Inspecting Cassandra Status

~~~bash
# Observe node and datacenter states.
nodetool status

# List snapshots on the connected node.
nodetool listsnapshots

# Check table/latency metrics within permitted scope.
nodetool tablestats lab_shop.orders_by_customer_month
~~~

These commands are **not a complete security audit tool**. Nodes can show `UP`/`NORMAL` while backups are incomplete, KMS cannot decrypt, or app logs leak payloads. Metric names and syntax also depend on Cassandra version.

### 11.2. Risk Review Checklist Without Exporting Secrets

- **Backups:** is there a recent `COMPLETE` backup? Are manifest, schema, files, and checksums intact? Does a copy exist in another failure domain? Can the restore role decrypt sample files?
- **Configs:** do secrets come from an authorized store? Are any private keys/credentials in repos or build artifacts? Are TLS/auth active per version across nodes and drivers?
- **Logs:** do app/Cassandra/APM/backup logs contain CQL bind values, session tokens, signed URLs, customer data, or secret paths?
- **Test:** is data synthetic or properly de-identified? Could test traffic hit production services? Are stale test snapshots/logs left behind?
- **Audit:** who accessed backups, who altered policies/retention/keys, who ran restores, and when?

If a real secret is found, **never copy its value into the report**. Record the system name, asset type, redacted evidence, and a ticket ID; coordinate rotation/revocation per incident response.

### 11.3. Independent Recovery Drill

Pick a backup marked `COMPLETE`, spin up an isolated cluster, decrypt, and load data using a runbook matching the Cassandra version. Test multiple partition keys, clustering order, `UPDATE`/`DELETE`d rows, and TTL fields. For query-driven tables, verify business consistency across denormalized tables.

Drill output should record:

~~~yaml
drill_id: "cassandra-security-restore-example"
backup_id: "<verified-backup-id>"
backup_integrity: "PASS"
encryption_key_available_in_target_domain: true
manifest_and_schema: "PASS"
restore_environment: "isolated"
data_validation: "PASS_FOR_DECLARED_FIXTURES"
sensitive_data_in_logs: "NOT_OBSERVED_IN_TEST_SCOPE"
rpo_estimate_minutes: "<measured-or-unknown>"
rto_drill_minutes: "<measured-or-unknown>"
unverified_dependencies:
  - "<if-any>"
result: "PASS_WITH_DEFINED_SCOPE"
~~~

This is a **custom report template**, not a Cassandra configuration. If regional loss, full log pipelines, or production-scale data were not tested, explicitly state the **unverified scope**. Never mark a production system `PASS` just because a tiny fixture set restored.

## 12. Leakage and Misconfiguration Incident Scenarios

### 12.1. Backup Credential Exposed in CI Logs

**Signal:** a backup job prints a signed URL or access token in build logs accessible to many users.

1. Immediately cut off exposure paths: log read access, running jobs, and related artifacts/caches.
2. Revoke or rotate the credential and verify old tokens no longer work, accounting for token/session lifetimes.
3. Inspect audit trails to determine which objects could have been read, modified, or deleted.
4. Fix the pipeline to stop logging sensitive args/URLs, disable shell verbose mode, and use scoped workload identities instead of long-lived credentials.
5. Verify backups remain complete, intact, and clean copies survive outside the compromised permission scope.
6. Document the incident with de-identified evidence, owners, and regression tests.

### 12.2. Backup Bucket Overly Permissive

**Signal:** a bucket/prefix or policy allows reads beyond intended organizational scope.

- Lock down out-of-scope read access and audit prior shares/public URLs.
- Review access logs, inventories, retention, and checksums/signatures to see if data was downloaded or altered.
- If backups are encrypted with keys external parties cannot decrypt, risk is lowered but not zero: evaluate metadata, paths, key policies, and deployment flaws.
- Test restore after tightening policies to ensure valid DR roles were not locked out.
- Determine whether key rotation, notifications, investigations, or legal steps are required per organizational procedure.

### 12.3. Test Logs Accidentally Contain PII

**Signal:** after restoring production data into test, the app logs raw customer payloads into APM.

- Pause forwarding pipelines and restrict access and retention on affected logs.
- Switch to synthetic or de-identified datasets; inspect all sinks including APM, alerts, tickets, and archives.
- Add source-side filtering/redaction and regression tests with canary marker payloads.
- Delete/restrict sensitive log copies per policy, verifying log retention and log backups are handled too.
- Resume drills only after proving test data stays within its defined trust boundary.

## 13. Design Trade-Offs to Balance

### 13.1. Security vs. RTO

Encryption, privilege separation, and recovery approvals can add steps to restores, yet skipping them leaves backups leaked or missing when needed. The right way to improve RTO is **automating authorized checks**, testing KMS in the target domain, maintaining versioned runbooks, and rehearsing drills regularly—never storing private keys inside scripts "to skip waiting for approval."

### 13.2. Retention vs. Data Deletion Requests

Long-term backups preserve clean recovery points, yet can retain records deleted from live tables by TTL or legal requests. Operations must understand:

- Live data expiring via TTL does not erase older versions inside snapshots/backups.
- **`gc_grace_seconds`** governs tombstones/repair, not backup retention.
- Retention windows, object scopes, and deletion/exception workflows must align across backups, test data, logs, and incident records.
- When restoring from an older backup, replay/re-apply valid post-cutoff deletion requests before reopening data to users.

### 13.3. Observability vs. Data Minimization

To analyze hot partitions, operators need row counts, partition sizes, token/routing info, and latencies—rarely customer names or transaction payloads. Cassandra favors **query-driven table design**: once query patterns are known, design metrics around **query shapes**, DCs, CLs, partition-size buckets, and timeout types instead of dumping CQL values.

Well-instrumented systems answer "which table has compaction backlog, which replica is slow, which query timed out?" without showing operators order contents.

## 14. Hands-On Exercises

### Exercise 1 — Snapshots Copied Within the Same Region

A cluster uses RF = 3; node snapshots are copied to a bucket in the same region under the same admin account managing the cluster. Someone accidentally drops a table and also deletes the bucket.

**Question:** Why don't replicas save the data? What changes are needed for a more independent backup?

**Hint:** logical deletes replicate across replicas, while the bucket and cluster share the same privilege/failure domain. Retain pre-error copies in an independent domain with separated delete rights, retention/versioning/immutability, isolated decryption keys, and restore drills.

### Exercise 2 — Spot the Issues in an Error Message

A Java app logs:

~~~text
WARN Cassandra login failed for user=orders_app
password=swordfish123 customer_id=... payload={...}
~~~

**Question:** Which data types do not belong in logs? How should you handle an active incident like this?

**Hint:** passwords, customer IDs/payloads, and auth details may be exposed. Stop propagation, revoke/rotate secrets, restrict log access, scope exposure, fix log templates, and check downstream sinks.

### Exercise 3 — Are Checksums Enough Against Backup Tampering?

An uploader can modify both SSTable files in a bucket and the manifest holding SHA-256 hashes. It alters an SSTable and recomputes the digest.

**Question:** Does the current checksum verification catch it? What layers can be added?

**Hint:** verifying against the tampered manifest still passes. Store manifests in an independently protected source, add signatures/authentication, restrict overwrite permissions, and enforce retention/immutability.

### Exercise 4 — Test Data Alters Partition Keys

A team hashes every `customer_id` before loading a production snapshot into test, then claims benchmarks preserve token distribution and hotspots.

**Question:** Why might that claim be wrong? How can you verify?

**Hint:** tokens are computed from encoded partition key values; changing values changes tokens and can reshape replica distribution and hotspots. Check cardinality, skew, partition sizes, throughput, and latencies; prefer synthetic data matching measured distributions and workloads.

### Exercise 5 — Query-Driven Design and Safe Logging

Given CQL:

~~~sql
SELECT order_id, status, amount
FROM lab_shop.orders_by_customer_month
WHERE customer_id = ? AND order_month = ?
LIMIT ?;
~~~

**Task:** propose a log entry aiding **read timeout** investigation without exposing `customer_id` or `amount`.

**Hint:** log operation name, query-shape ID, keyspace/table, CL, DC, latency, timeout class, retry count, controlled tracing ID, and PII-free request ID. Never log `BoundStatement` or row payloads.

### Exercise 6 — Data Restored Yet KMS Key Lost

An out-of-region encrypted backup has valid checksums, yet only a KMS key in the primary region can decrypt it. The primary region goes completely down.

**Question:** Does the backup meet DR goals? What must be added to the runbook?

**Hint:** not met if the target domain lacks decryption keys/authority. Design multi-domain key/authorization availability for primary-region loss, test from the target domain, and measure key-access latency inside RTO.

## 15. Cassandra Operational Security Self-Check Checklist

- [ ] Identified sensitive data across **SSTables, snapshots, incremental backups, commit logs, manifests, configs, logs, and test datasets**.
- [ ] Backups reside **outside target failure domains** and are verified for full node/token coverage.
- [ ] Data is encrypted in transit and at rest; decryption keys have proper access controls, retention, and DR availability.
- [ ] IAM, CQL roles, OS permissions, JMX, KMS, and bucket policies are scoped **per layer** under least privilege.
- [ ] Zero passwords/tokens/private keys in Git, shared scripts, CLI history, build artifacts, or logs.
- [ ] Tested real **TLS/auth/authorization** matching your Cassandra version and Java Driver.
- [ ] Logs, audits, traces, and APM emit no credentials, bind values, or payloads; redaction happens at the source.
- [ ] Core/heap dumps, support bundles, and tickets have access and retention controls.
- [ ] Test environments isolate clusters, secrets, networks, buckets, and external integrations from production.
- [ ] Test datasets prefer synthetic data; any production-derived data follows formal policy and verified de-identification.
- [ ] Retention and deletion workflows apply consistently across live tables, backups, logs, test copies, and extracts.
- [ ] Backup manifests/checksums use authenticated sources to detect tampering; marked `COMPLETE` only after checks pass.
- [ ] Rehearsed restores into isolated environments checking multiple partitions, TTL/DELETEs, schemas, and Java apps.
- [ ] Measured RPO/RTO, verified decryption during primary-region loss, and updated runbooks from real findings.

## 16. Summary

Protecting Cassandra does not stop at configuring authentication and connection encryption. **Replicas** serve availability, **snapshots** capture point-in-time state, and **off-fault-domain backups** enable recovery when live data or infrastructure is destroyed. Every one of those copies—alongside configs, logs, and test data—becomes a data-leakage path without proper authorization, encryption, integrity verification, and retention/erasure lifecycles.

Resilient design means **scoping privileges by role, protecting secrets, minimizing telemetry, using safe test data, and rehearsing real restores**. Combined with wide-column modeling, partition keys, consistency levels, compaction, repair, and Java application design, these controls let Cassandra recover from incidents while minimizing data exposure throughout operations.
