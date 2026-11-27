# Tool Authorization, Operation Auditing, and Post-Execution Verification

## 1. Why Do Cassandra Operations Require Permissions, Evidence, and Post-Checks Together?

An **Apache Cassandra** cluster can serve millions of reads and writes thanks to partition keys, the token ring, replication, and consistency levels. Yet that very distributed nature means an uncontrolled administrative command can impact multiple nodes, multiple datacenters, and data recoverability.

Consider a scenario: an operator sees N2's disk nearly full after adding node N4, and runs `nodetool cleanup` on N2. The command exits 0, so the ticket is closed. Hours later, the application reports missing data for several partitions. It turns out bootstrap/streaming had not been thoroughly verified, and nobody recorded **who ran the command, on which node, with what arguments, at what time**, or **before/after replica states**.

A reliable operational workflow must answer **three independent questions**:

1. **Who is allowed to do what?** Application users, DBAs, SREs, automation, and admin accounts must not share the same default privileges.
2. **What exact action was taken?** Identity, timestamp, target, normalized command, outcome, and change reference must be recorded—without exposing secrets.
3. **Were the expected postconditions achieved?** Launching a command or getting exit code 0 **does not always mean the cluster is in a safe state**.

**Learning objectives:** distinguish **CQL RBAC** from **JMX/nodetool and OS permissions**, apply least privilege, design an audit trail, standardize *before → execute → verify*, practice CQL and admin tools, and learn how to investigate partially executed operations or side effects.

**Scope limits:** Cassandra spans multiple generations and deployment models. CQL permissions, audit logging, JMX security, `nodetool` syntax, and SSH/container/control-plane mechanisms vary by version. Examples here are **runbook templates** and labs; never run directly on production without checking actual documentation and configuration.

## 2. Administrative Surface Map: There Is No Single "Cassandra Permission"

~~~mermaid
flowchart TD
    A["Operator / Automation"] --> B["Bastion / IAM / SSO / approval"]
    B --> C["CQL via cqlsh / Java Driver"]
    B --> D["nodetool via JMX"]
    B --> E["SSH, Kubernetes, systemd, OS"]
    C --> F["Cassandra authn/authz: roles + CQL permissions"]
    D --> G["JMX authentication/authorization + network/TLS"]
    E --> H["OS/service account, sudo, container RBAC"]
    F --> I["Keyspace/table/role/schema operations"]
    G --> J["Node management and JMX MBeans"]
    H --> K["Config, restart, file/log/snapshot access"]
    I --> L["Audit and post-change verification"]
    J --> L
    K --> L
~~~

| Access Channel | Typical Identity / Authorization | Examples | Common Mistake |
| --- | --- | --- | --- |
| **CQL native protocol** | Cassandra `Authenticator`, `Authorizer`, roles, and permissions when enabled | `SELECT`, `INSERT`, `ALTER TABLE`, `GRANT` | Assuming a `SELECT`-only role can also run any `nodetool` command. |
| **JMX/nodetool** | JMX authentication, authorization/MBean access, and network/TLS controls per deployment | `status`, `repair`, `snapshot`, `cleanup` | Assuming CQL permissions automatically restrict `nodetool repair`. |
| **OS/service manager** | SSH/SSO, sudo, file ACLs, systemd/service accounts | Reading logs, editing config, restarting nodes | Giving everyone `root` or write access to SSTable directories. |
| **Container/orchestrator** | Kubernetes/cluster RBAC, admission policies, workload identity | `kubectl exec`, swapping secrets, restarting pods | Equating namespace access with Cassandra read/write access. |
| **Backup/monitoring** | IAM, secret stores, object storage policies, JMX exporter/API credentials | Taking snapshots, exporting backups, viewing metrics | Giving a read-only dashboard account permission to delete backups. |
| **CI/CD/automation** | Service identity, short-lived secrets, pipeline approvals/policies | Schema migrations, maintenance runbooks | Sharing one superuser account across all pipelines. |

**Key takeaway:** someone restricted to `SELECT` in CQL can still make sweeping changes if they hold **SSH root** or unrestricted **admin JMX access**. Permission reviews must cover **every path capable of affecting data**, not just `GRANT` statements.

## 3. Authentication, Authorization, and Least Privilege

### 3.1. Separating Authentication from Authorization

- **Authentication:** identifies *who is connecting* (password, certificate, automation identity, or configured mechanism).
- **Authorization:** determines **which actions** that identity may perform on which resources.
- **Audit/accountability:** preserves verifiable evidence of *which identity attempted and executed what*.

In Cassandra, authn/authz is typically configured server-side; deployments may use `PasswordAuthenticator`, `CassandraAuthorizer`, or custom providers. **Do not assume a cluster enforces RBAC simply because CQL `GRANT` exists in documentation.** Verify actual server config, active enforcement, TLS on native protocol, and that default accounts are locked down.

### 3.2. Role-Based Design Instead of Broad Grants

| Business Role | Permissions to Consider | Should Not Have by Default |
| --- | --- | --- |
| **Read application** | `SELECT` on serving tables. | `MODIFY`, `DROP`, `ALTER`, `AUTHORIZE`, JMX access. |
| **Write application** | `MODIFY` on target write tables; `SELECT` if validation needed. | `CREATE ROLE`, `ALTER KEYSPACE`, snapshot/file deletion. |
| **Analytics service** | `SELECT` on allowed tables/projections, rate-limited. | Schema changes, cross-tenant access when unnecessary. |
| **Schema migration team** | Required schema permissions scoped to project and time window. | Permanent superuser, node restart permissions. |
| **Observability SRE** | Read-only JMX/metrics, status, and sensitive-data-filtered logs. | `repair`, `cleanup`, `drain`, `stop` commands when unneeded. |
| **Maintenance SRE** | Permission to run specific runbooks within approved windows. | Indefinite broad permissions across all DCs. |
| **Backup operator** | Create/export snapshots, write to designated backup bucket. | Arbitrary backup deletion or modifying CQL data. |
| **Security/auditor** | Read protected audit events and permission reports. | Modify or delete original audit events. |

**Least privilege** means granting the minimum permissions **needed to do the job**, in the narrowest **table/keyspace/node/DC** scope, for a sensible **duration**. Use distinct identities for every person and service; never share the default `cassandra` password or root accounts.

### 3.3. Schema Permissions and Data-Read Permissions Carry Different Risks

Schema changes like `ALTER TABLE`, `DROP TABLE`, or altering keyspace RF can impact **the whole cluster**. Reading data also carries security and load risks, especially `ALLOW FILTERING` or multi-partition scans. Therefore:

- CQL authorization must pair with **query limits, rate limiting, and guardrails**.
- `SELECT` is not automatically harmless: read-heavy queries can saturate replica I/O.
- `MODIFY` normally covers writing and deleting data on permitted resources; never grant it to read-only roles.
- Critical schema operations must flow through **migration approval pipelines**, not casual app config changes.

## 4. CQL RBAC Lab: A Read-Only Role and Verifying Effective Permissions

### 4.1. Creating Demo Data

Assume a lab cluster with DC `dc1`, enough nodes for RF = 3, and authentication/authorization enabled:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_ops
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_ops.device_events (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

INSERT INTO telemetry_ops.device_events
  (device_id, event_day, event_time, event_id, event_type)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T10:00:00Z',
   123e4567-e89b-42d3-a456-426614174001, 'heartbeat');
~~~

**Data model:** partition key `(device_id, event_day)` serves device/day reads; clustering `(event_time, event_id)` maintains time ordering. This design bounds unbounded partition growth, without replacing partition-size and SLO monitoring.

### 4.2. Creating a Non-Login Role as a Permission Group

Run the following **only with an appropriately privileged DBA account in the lab**, never an app account:

~~~sql
-- Group role that cannot log in directly.
CREATE ROLE IF NOT EXISTS telemetry_event_viewer
WITH LOGIN = false;

-- Allow reading only the target table; do not grant MODIFY.
GRANT SELECT ON TABLE telemetry_ops.device_events
TO telemetry_event_viewer;

-- List permissions to audit against policy.
LIST ALL PERMISSIONS OF telemetry_event_viewer;
~~~

When provisioning a human/service login account via proper identity and secret management, an administrator can grant membership:

~~~sql
-- analyst_identity is a login role provisioned separately per procedure.
GRANT telemetry_event_viewer TO analyst_identity;

-- Inspect effective permissions using version-supported syntax.
LIST ALL PERMISSIONS OF analyst_identity;
~~~

**Do not run `GRANT ... TO analyst_identity` if that role has not been provisioned.** Avoid embedding real passwords in examples/tutorials, shell history, or tickets. When creating a password-based role, use secure provisioning tools, approved secret distribution, and policy-compliant rotation/revocation.

### 4.3. Testing Both "Allow" and "Deny"

In the lab, log in with the account assigned the viewer role and test:

~~~sql
-- Must succeed if authz settings are right:
SELECT event_time, event_type
FROM telemetry_ops.device_events
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21';

-- DO NOT run on real data just to test!
-- Test on a dedicated lab table with rollback and verify the command is rejected:
-- DELETE FROM telemetry_ops.device_events
-- WHERE device_id = 'device-7' AND event_day = '2026-11-21';
~~~

Here the viewer role should only read. If `DELETE` or `ALTER TABLE` still succeeds under the read-only account, inspect **indirect role memberships, broader keyspace-level grants, superuser status, and authorizer configuration**—do not rely on a single `GRANT SELECT` line.

**After testing:** use version-supported commands to inspect roles/permissions (`LIST ALL PERMISSIONS`, `LIST ROLES` where supported) and cross-check audit events. **One Unauthorized error proves one test case was rejected**, not that the whole permission model is immune across JMX/OS paths.

## 5. `nodetool` Authorization: The Boundary Between JMX and CQL

`nodetool` typically uses **JMX** to communicate with Cassandra administrative MBeans. Some commands are read-focused:

~~~bash
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool netstats
nodetool listsnapshots
~~~

Other commands alter state or generate significant load:

~~~bash
# SYNTAX ILLUSTRATION ONLY; DO NOT run wholesale in production:
nodetool snapshot -t ops-lab-01 telemetry_ops
nodetool repair telemetry_ops
nodetool cleanup telemetry_ops device_events
nodetool flush telemetry_ops device_events
~~~

| Command | Primary Operational Risk | Postcondition to Verify |
| --- | --- | --- |
| `status`, `info` | Mostly observational; can reveal topology/operational metadata | Output captured from the right cluster at the right time. |
| `snapshot` | Pins old SSTables, potentially growing disk usage later | Snapshot tag appears on the **exact target nodes/tables**; clear retention and backup plan. |
| `repair` | Validation, streaming, CPU/disk/network load; can run long | Repair session completed across scoped ranges per logs, not merely command launch. |
| `cleanup` | Deletes data no longer owned; dangerous if topology is still shifting | Prior bootstrap/streaming completed; data intact on new natural replicas. |
| `flush` | Writes memtables to SSTables, generating I/O and compaction | Flush completed with node headroom intact; never confused with backup. |
| `compact` | Can create large SSTables and consume temporary disk | Compaction does not exhaust disk or cause runaway backlogs. |
| `drain`, `stop`, `decommission` | Impacts serving availability/topology; can break quorum | Run strictly per dedicated runbook with tight pre/post conditions. |

### 5.1. JMX Security Must Be Controlled Independently

**CQL roles do not automatically protect JMX.** For Cassandra deployments exposing remote JMX (commonly port `7199` in some configs), evaluate:

- Is the JMX endpoint restricted strictly to the management/bastion network, not exposed to the Internet or app subnets?
- Are **JMX authentication/authorization** and transport encryption enabled appropriately for your version?
- Can **metrics-reading** permissions be separated from **state-mutating MBean operations**?
- Which credentials does `nodetool` use in practice, and are passwords exposed on command lines, logs, or shell history?
- Can JMX be bypassed via SSH root, container exec, or unmanaged JMX agents?

JVM/JMX properties and MBean access controls vary by Cassandra/JDK version. **Never blindly copy JMX security configs from another version.** Above all, never disable authentication/TLS or open management ports broadly just "to make `nodetool` work".

### 5.2. Least-Privilege Deployment Model

~~~text
SRE checking status
  → SSO + bastion → read-only monitoring/JMX capability (where supported)

SRE running repair
  → change ticket + approval + temporary credential
  → automation executes nodetool on approved nodes
  → saves logs/session ID/exit status + verifies postconditions

Java application
  → native CQL with minimal SELECT/MODIFY role
  → no SSH root or JMX management access
~~~

Where granular JMX RBAC is unavailable, place an **automation wrapper/runbook** in the orchestration layer with argument allowlists, scope validation, and approval gates. Never let users pass arbitrary shell strings into high-privilege automation.

## 6. Access to Logs, Data, and Backups Is Also a Security Boundary

Even a log-viewer account can see **CQL text, node addresses, identifiers, partition keys, trace IDs, stack traces, or sensitive connection info** depending on log levels. Backups and snapshots can hold complete user datasets, so `download snapshot` permission is effectively **raw data access**, not a "harmless operational permission".

| Resource | Permissions to Control | Recommendation |
| --- | --- | --- |
| System/debug/GC logs | Read, alter retention, delete/overwrite | Separate viewers from log admins; redact secrets; retain only as needed. |
| `system_traces` and CQL audit logs | Read query text and trace events | Enforce RBAC, retention, payload limits; never ship raw logs to untrusted systems. |
| Snapshot/backup storage | Create, read, download, delete, set retention | Encrypt, enforce least privilege, separate creators from deleters, make backups immutable where possible. |
| Cassandra data directories | Read/write SSTables, commit logs, hints | Service account and special runbooks only; never delete manually. |
| Secret/config files | Passwords, TLS keys, JMX credentials | Secret manager and tight ACLs; never put in tickets, stdout, or CI artifacts. |
| Metrics endpoints | Topology, IPs, throughput, error patterns | Network/access restrictions; do not leave metrics public by default. |

**Never pass passwords or keys directly on the command line** where process lists, shell history, or pipeline logs can capture them. Exact credential injection depends on tooling and OS, while the rule holds universally: use **secret managers, short-lived identities, and redaction**—never let auditing leak secrets into logs.

## 7. Operation Auditing: Audit Logs Must Link Identity to Outcome

### 7.1. Minimum Audit Record

A useful administrative event should let someone else reconstruct **who did what, where, why, and what happened**:

~~~text
change_id            : CHG-2026-11-21-0042
action_id            : 8b31... (unique ID for this execution)
actor_identity       : sre.maintenance@example.invalid
effective_identity   : temporary-ops-role / automation-runner-01
approval_id          : CAB-1842
cluster              : cassandra-prod-main
datacenter           : dc1
node                 : cassandra-dc1-n2
operation            : nodetool.snapshot
approved_scope       : keyspace=telemetry_ops, node=dc1-n2
arguments_redacted   : snapshot tag=CHG-2026-11-21-0042
started_at_utc       : 2026-11-21T10:10:00Z
finished_at_utc      : 2026-11-21T10:10:18Z
execution_status     : command-exit-0
postcheck_status     : verified / failed / pending
evidence_refs        : log-archive-id, snapshot-inventory-id
rollback_or_recovery : reference-to-runbook
~~~

**This is an operations-designed audit schema**, not a built-in Cassandra table. Never use illustrative emails as production identities, and never store credentials, user payloads, or session tokens inside `arguments_redacted`.

Most critically, **separate `execution_status` from `postcheck_status`**. Exit code 0 only signals **the tool believes the command finished**; it does not prove post-operation data, replicas, or capacity match goals.

### 7.2. Events Worth Recording

| Phase | Events to Store | Purpose |
| --- | --- | --- |
| **Request** | Requester, reason, risk, scope, expected impact | Explains why the action was authorized. |
| **Approval** | Independent approver, expiry window, run conditions | Prevents self-approval of high-risk actions. |
| **Preparation** | Cassandra version, topology, RF/CL, node health, backups, prechecks | Provides comparison baseline and rollback/recovery readiness. |
| **Execution** | Actor, effective identity, command template + redacted args, UTC timestamps | Traces actual action and scope. |
| **Tool result** | Exit status, filtered stdout/stderr, session ID, warnings, errors | Distinguishes failure, completion, or launching background work. |
| **Post-check** | Metrics/logs/replica state, sample query outcomes, snapshot inventory | Verifies the real goal was achieved. |
| **Closure** | Conclusion, verifier, remaining issues, follow-up steps | Prevents forgotten partial runs and lingering risks. |

Audit records must be stored **in UTC with synchronized clocks, append-only/immutable where feasible**, and shipped off-node before anyone with system privileges can alter or delete local logs. Define retention, read permissions, and purge policies per security requirements.

### 7.3. Do Not Rely on CQL Audit Alone

Modern Cassandra versions support configurable **audit logging** for CQL operations. However, **not every** version, edition, or deployment logs all actions identically. Specifically:

- CQL audit logs `CREATE/ALTER/GRANT/SELECT` for enabled event categories, yet **does not automatically log all `nodetool` JMX operations**.
- OS-level actions like editing `cassandra.yaml`, restarting services, deleting files, or reading secret stores fall **outside CQL audit scope**.
- When logging is disabled, disks fill, exporters fail, or nodes crash, audit events can be lost. **Missing logs do not prove an action did not happen.**
- Auditing every `SELECT` in detail can impose heavy I/O overhead and sensitive-data risks. Apply filtering, sampling/retention, and strict read controls.

Therefore, combine **CQL audit (where enabled)**, **bastion/SSH session recording**, **JMX management wrapper logs**, **CI/CD activity**, **OS/service logs**, and **monitoring/tracing** into one evidence chain. Audit logging can impact performance; test enabling/configuring it per version.

## 8. Standard Workflow: Before → Execute → Verify → Close

~~~mermaid
flowchart TD
    A["Operation request received"] --> B["Identify actor, permissions, scope, and impact"]
    B --> C{"Valid ticket, approval, and window?"}
    C -->|No| Z["Stop / request approval"]
    C -->|Yes| D["Precheck: topology, RF/CL, disk, logs, backup"]
    D --> E{"Safety conditions met?"}
    E -->|No| Z
    E -->|Yes| F["Issue temporary credentials / run allowlisted command"]
    F --> G["Record action ID, UTC, redacted args, exit/log/session"]
    G --> H["Postcheck multiple sources, both data and resources"]
    H --> I{"Postconditions met?"}
    I -->|Yes| J["Revoke temporary access, close change, archive evidence"]
    I -->|No / unclear| K["Keep change open, investigate / recover per runbook"]
    K --> H
~~~

### 8.1. Before: Preconditions

A universal preflight checklist for impactful commands:

1. **Confirm target:** cluster, DC, node, keyspace, table, token range, snapshot tag, or session ID.
2. **Confirm impact:** read-only, file creation, data streaming, topology edit, or deleting unowned data?
3. **Verify permissions:** actor has exact scoped access, effective identity is not shared, credentials have valid expiry.
4. **Check RF/CL and health:** any `DN`, `UJ`, `UL` nodes, or concurrent topology/repair tasks?
5. **Check resources:** free disk/headroom, compaction backlog, network/streaming, heap/GC, read/write p99, and error rates.
6. **Verify recovery:** usable backups/snapshots, tested restore path, designated owner, and rollback boundaries.
7. **Check schedule:** maintenance window, concurrency caps, avoiding overlapping heavy jobs, and stakeholder notice if user-facing.
8. **Capture baseline:** UTC time, Cassandra/JDK version, `nodetool status`, metrics, and relevant sample data state.

### 8.2. Execute: Narrow, Traceable Actions

Favor **one narrowly scoped command first**, naming tags/sessions after the change ID and capturing logs immediately. When running across multiple nodes:

- Specify **node order** and cap concurrent nodes/commands.
- Never run operations concurrently that can **break quorum** or contend heavily on disk/network.
- Keep configuration/topology consistent throughout the plan; if ownership shifts mid-way, replan.
- Never interpolate user command strings into high-privilege shells without **allowlists, escaping, and validation**.
- Never edit `cassandra.yaml` or modify `GRANT`s outside approved scope.

### 8.3. Verify: Independent of Exit Code

An operation has **two distinct outcomes**:

~~~text
Tool outcome:         command exited 0 / command failed / disconnected / unknown
System postcondition: verified / failed / pending / inconclusive
~~~

For instance, `nodetool repair` returning cleanly on one node does not prove **every token range, replica/DC, and table** converged. `nodetool snapshot` succeeding does not prove **the backup was exported off-host and is restorable**. Creating a CQL role cleanly does not prove the role lacks unintended inherited privileges.

Post-checks require **evidence from the affected subsystem**, such as:

- CQL permissions: log in as the real role and test both allowed and expected-denied commands.
- Replicas/repair: inspect repair session logs, processed ranges, node health, and error counters.
- Snapshots: check `listsnapshots` inventory, backup manifests, exported data, and restore tests per procedure.
- Topology: check `status`, token map, streaming completion, natural endpoints, and controlled reads/writes.
- Performance: compare p95/p99, timeouts, free disk, and compaction/GC/hints before vs. after.

## 9. Post-Checks by Common Operation Type

| Operation | Key Pre-Checks | Key Post-Checks | Risk of Closing Ticket Too Early |
| --- | --- | --- | --- |
| **CQL schema migration** | Schema permissions, client compatibility, cluster health, migration order. | Schema agreement, accurate metadata, app read/write canary. | Schema changed while apps remain incompatible. |
| **`GRANT`/`REVOKE`** | Current roles, effective permissions, memberships. | `LIST PERMISSIONS`, allow/deny tests with real account, audit events. | Role inherited broader permissions than intended. |
| **`snapshot`** | Free disk, unique tag, backup retention. | Tag present in inventory on right nodes/tables, export manifest, restore test. | Mistaking a local snapshot for an off-cluster backup. |
| **`repair`** | RF, DC scope, token ownership, node health, tombstone deadline. | Repair completed on target ranges/participants; streaming/errors clean. | Missing a DC or silently failing subrange. |
| **`cleanup`** | Bootstrap/streaming finished, new ownership settled, backups. | Active disk/SSTable trends sane; data verified on new replicas. | Purging old copies before new owners finished receiving data. |
| **`flush`** | Disk headroom, compaction backlog. | Flush finished, SSTables and queues managed normally. | Mistaking flush for backup or replica sync. |
| **`compact`** | Disk headroom, compaction policy, overlapping jobs. | Task finished, disk not exhausted, read/write latency recovered. | Temporary output files filling the disk. |
| **Change RF / add DC** | NTS, rack/DC, capacity, streaming plan, CL. | New replicas hold data, repair/rebuild done, per-DC canary. | Running `ALTER KEYSPACE` and assuming new replicas are populated. |
| **Restart/decommission** | Quorum health, sibling nodes, automation, recovery plan. | Node/ring state matches target, client SLOs healthy, data transfer complete. | Losing another node breaks quorum. |

Note: some commands execute **in the background or across multiple phases**, and some can disconnect/time out after making partial changes. Always check version-specific command docs and **measure postconditions**, never inferring state from one line of stdout.

## 10. Lab: Monitored and Verified Snapshot

This lab practices **recording action IDs, pre-checks, and post-checks** without running risky repair/cleanup jobs. You need a lab Cassandra node, approved permissions, and the `telemetry_ops` keyspace from Section 4.

### 10.1. Pre-Checks Before Snapshotting

~~~bash
# On the approved lab node.
nodetool status
nodetool info
nodetool compactionstats
nodetool listsnapshots
nodetool help snapshot
~~~

On Linux, check the exact mount point holding the data directory:

~~~bash
df -h
~~~

Record **UTC time, node name, cluster, keyspace, version, free disk, and existing snapshots**. Some deployments auto-snapshot before truncate/drop and those snapshots follow retention too, so check inventory before creating new ones.

### 10.2. Execute on the Exact Node with the Exact Tag

~~~bash
# Lab only. Tag tied to action/change ID.
nodetool snapshot -t ops-lab-20261121-01 telemetry_ops
~~~

If your version supports selecting specific tables or extra flags, inspect `nodetool help snapshot` on **that exact version**. Never assume one command takes a cluster-wide snapshot: `nodetool snapshot` executes on the **targeted node**, and cluster/application-consistent snapshots require separate coordination.

### 10.3. Verify Result and Recoverability

~~~bash
nodetool listsnapshots
nodetool status
nodetool compactionstats
~~~

Closing checklist:

1. Does snapshot tag `ops-lab-20261121-01` appear on the **exact node/keyspace/table**?
2. Are system logs free of snapshot errors, and is disk headroom still safe?
3. Are snapshot files and metadata needed for restore fully inventoried?
4. If this were a real backup, was it **exported to independent storage**, verified via manifest/checksum, and restore-tested?
5. Did the audit event record **actor, node, tag, timestamp, exit status, and verification status**?

**Never run `clearsnapshot` in production just to wrap up a lab.** In your private lab, clear snapshots only if no recovery need remains and per verified syntax/retention; snapshots can pin old SSTables via hard links, though reclaimable bytes cannot be deduced directly from displayed snapshot size.

### 10.4. Example Post-Check Record

~~~text
action_id           : ops-lab-20261121-01
cluster/node        : lab / cassandra-lab-02
command             : nodetool snapshot -t ops-lab-20261121-01 telemetry_ops
tool_exit           : 0
observed_tag        : present on cassandra-lab-02
disk_free_after     : measured; not assumed
backup_exported     : no (local snapshot lab only)
restore_verified    : no
postcheck_status    : VERIFIED_LOCAL_SNAPSHOT_ONLY
next_action         : if production backup, export + restore validation
~~~

The status **`VERIFIED_LOCAL_SNAPSHOT_ONLY`** is far more accurate than `BACKUP_COMPLETE`. This is a vital example of **naming states by observed evidence, not wishful thinking**.

## 11. When an Operation Fails Mid-Way: UNKNOWN vs. FAILED

A classic scenario: automation launches `nodetool repair`, and SSH drops after 30 minutes. The shell returns an error due to the broken management channel, yet the repair session may still be running, partially finished, or genuinely failed.

~~~mermaid
flowchart TD
    A["Launch operation with action ID"] --> B{"Reliable completion confirmation?"}
    B -->|Yes, succeeded| C["Verify postconditions"]
    B -->|Yes, failed| D["FAILED: inspect partial impact"]
    B -->|No| U["UNKNOWN: do not assume not run"]
    U --> E["Cross-check logs, session ID, node/task state"]
    D --> E
    E --> F{"Topology/scope still valid and retry safe?"}
    F -->|Yes| G["Controlled retry, same action/runbook"]
    F -->|No| H["Stop, replan/restore per procedure"]
    C --> I{"Postconditions met?"}
    I -->|Yes| J["VERIFIED and close change"]
    I -->|No| E
~~~

**Never automatically retry a heavy or destructive command simply because the client disconnected.** Retrying can overlap repair/compaction sessions or repeat an action against changed state. Similarly:

- `ALTER KEYSPACE` times out: schema metadata may already have updated; re-read metadata/schema agreement before re-sending.
- `nodetool cleanup` interrupted mid-way: some SSTables may already be rewritten; check topology/ownership and logs.
- `snapshot` disconnects: the tag may already exist; check inventory before picking a new tag to avoid duplicates/over-retention.
- `REVOKE` outcome unclear: test permissions **with the actual effective account**, not just the API response.

A runbook should define statuses **`PENDING`, `RUNNING`, `VERIFIED`, `FAILED`, `UNKNOWN`, `NEEDS_REPLAN`**. The `UNKNOWN` state separates "lost visibility" from "Cassandra definitely did nothing".

## 12. Tracing from the Java Application: Recording Evidence Without Granting DBA Rights to the App

An **Apache Cassandra Java Driver 4.x** application is responsible for reading/writing business data under a minimal CQL role. It should log **query name, CL, duration, outcome, and warnings**, but must never be granted rights to run `nodetool`, `ALTER KEYSPACE`, or delete snapshots for convenience.

Java example reading a single partition in the lab keyspace:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ExecutionInfo;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class AuditedReadExample {
    public static void main(String[] args) {
        // Real identity/secrets/TLS must be configured via secure provisioning.
        // This example specifies only the lab local DC and contact point.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement prepared = session.prepare(
                "SELECT event_time, event_id, event_type " +
                "FROM telemetry_ops.device_events " +
                "WHERE device_id = ? AND event_day = ? LIMIT 20");

            BoundStatement read = prepared.bind(
                    "device-7", LocalDate.of(2026, 11, 21))
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            // Application-generated correlation ID for joining client logs.
            // Cassandra does not receive this ID automatically without a dedicated propagation mechanism.
            UUID correlationId = UUID.randomUUID();
            Instant startedUtc = Instant.now();
            long startedNanos = System.nanoTime();

            try {
                ResultSet result = session.execute(read);
                ExecutionInfo info = result.getExecutionInfo();
                int count = 0;
                for (Row row : result) {
                    count++;
                }
                long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - startedNanos);

                // Production: structured logging, redaction, retention.
                System.out.println("query=read_device_events"
                    + " correlation_id=" + correlationId
                    + " started_utc=" + startedUtc
                    + " cl=LOCAL_QUORUM status=success"
                    + " rows=" + count + " elapsed_ms=" + elapsedMs
                    + " warnings=" + info.getWarnings().size());
            } catch (RuntimeException ex) {
                long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - startedNanos);
                System.err.println("query=read_device_events"
                    + " correlation_id=" + correlationId
                    + " started_utc=" + startedUtc
                    + " cl=LOCAL_QUORUM status=failure"
                    + " elapsed_ms=" + elapsedMs
                    + " error_type=" + ex.getClass().getSimpleName());
                throw ex;
            }
        }
    }
}
~~~

**Points to understand accurately:**

1. `LOCAL_QUORUM` with `dc1:3` requires **two replica responses** in the local DC. One successful SELECT does not prove all full replicas are synchronized.
2. `System.nanoTime()` measures **duration**, while `Instant.now()` captures UTC wall time; never use a monotonic clock as a UTC timestamp.
3. `correlationId` here exists only in client logs; linking to server logs requires a **trace session ID or implemented correlation mechanism**, never assuming the server knows the ID automatically.
4. `ExecutionInfo.getWarnings()` captures warnings for that execution only—**not full CQL auditing**, nor every warning across the cluster.
5. Never emit `device_id`, full `payload`, secrets, login tokens, or raw CQL with sensitive literals into broad telemetry. `correlation_id` belongs in logs, never as an unbounded-cardinality metric label.
6. Application-side Java Driver logs **do not replace JMX/OS-layer auditing**. Every operational action needs its own audit trail even while applications keep running.

### 12.1. Why Separate Application and Automation Identities?

If the Java account reading events also holds schema/JMX privileges, a vulnerability in a business API can be exploited to alter or wreck the cluster. Conversely, repair automation should not hold read access to every sensitive table when it only needs specific JMX operations. Isolate **identities and blast radii** between application workloads and maintenance orchestrators.

## 13. Multi-Datacenter: Command Scope Does Not Equal Consequence Scope

With `NetworkTopologyStrategy`, a keyspace may specify `dc1:3`, `dc2:2`. A `nodetool` command on one node normally **does not verify or act on the entire cluster**:

- `nodetool status` displays membership, not whether every partition is repaired.
- `snapshot` on N1 does not simultaneously snapshot every node/DC.
- `repair` scopes nodes, keyspaces/tables, token ranges, and participant replicas per version flags; repairing only inside `dc1` does not ensure `dc2` converged.
- `cleanup` purges unowned local data; it does not stream data to a new DC.
- `ALTER KEYSPACE` changes RF metadata without verifying old data reached new replicas.

### 13.1. Checklist for Multi-DC Commands

| Question | Evidence |
| --- | --- |
| What is the keyspace's RF per DC? | `system_schema.keyspaces`, snitch/DC/rack metadata. |
| Is topology bootstrapping, moving, decommissioning, or replacing? | `nodetool status`, ring, streaming logs. |
| On which node/address did the tool run? | Action log, node identity, JMX endpoint, cluster ID. |
| Which replicas/DCs participated in the job? | Command args, session logs, token ownership, version flags. |
| Did it affect read/write CL? | Live traffic monitoring for `LOCAL_QUORUM`, `QUORUM`, `EACH_QUORUM`. |
| Have data and tombstones converged sufficiently? | Repair/streaming verification, replica health, appropriate canary queries. |

Especially when **adding/removing nodes**, avoid concurrent maintenance across multiple replicas that could break quorum. With RF = 2 in a DC, `LOCAL_QUORUM` needs **two of two** replicas; one unavailable replica breaks requests at that CL.

## 14. Simulated Incident: Ticket Marked "Snapshot Succeeded" Yet Backup Cannot Restore

### 14.1. Timeline

| UTC Time | Event | Process Gap |
| --- | --- | --- |
| 10:00 | An engineer logs into N1 using a shared SSH account. | No individual **attribution**. |
| 10:05 | Runs `nodetool snapshot -t backup-01 telemetry_ops`. | No change ID; no node/DC scope recorded. |
| 10:07 | `listsnapshots` shows the tag on N1. | Only verified a **local snapshot**. |
| 10:10 | Closes ticket as `BACKUP_COMPLETE`. | Never verified export, manifests, or restore. |
| Days later | N1 loses its entire disk; object storage has no snapshot. | Cannot recover from a snapshot on the same failed volume. |

### 14.2. Preventive Controls

1. Require **individual identities via bastion/SSO**; eliminate shared SSH accounts.
2. Require **change ID, scope, approval**, standard command templates, and UTC timestamps.
3. Separate milestones: `SNAPSHOT_CREATED`, `BACKUP_EXPORTED`, `BACKUP_VERIFIED`, `RESTORE_TESTED`.
4. Verify snapshots across **all nodes required by the backup strategy**, not just N1.
5. Verify manifests/checksums, store independently, and periodically rehearse restores in an isolated environment.
6. Ship audit events off-node and restrict backup deletion rights.

**Lesson:** "Command completed" is an operational event; "verified recoverability" is **a different business outcome** requiring different evidence.

## 15. Troubleshooting When Permissions, Auditing, or Post-Checks Fail

| Symptom | Hypothesis | Approach |
| --- | --- | --- |
| Read-only account can alter a table | Inherited keyspace grant, superuser flag, or authorizer disabled. | Check effective role with the real account; revoke excess grants via approved change. |
| `cqlsh` gets Unauthorized while `nodetool` still works | CQL RBAC and JMX/OS use separate authorization paths. | Audit JMX security, bastion, OS permissions, and tool credentials. |
| No CQL audit record for `nodetool cleanup` | JMX operations fall outside CQL audit scope. | Check session recordings, automation logs, and JMX/OS events. |
| Audit event exposes password or token in args | Command logged verbatim without redaction. | Revoke/rotate secret, lock down log access, fix audit redaction pipeline. |
| `repair` lost SSH with no finish line | Lost visibility channel; actual state unclear. | Mark `UNKNOWN`; inspect repair sessions/logs before retrying. |
| `snapshot` succeeded yet `df` did not drop | Snapshots pin hard links or live SSTables; unrelated to backup "success". | Review retention/inodes/references and backup plan. |
| Post-check `status` looks good yet reads time out | Membership is only one layer; could be GC/disk/tombstones/network. | Measure client p99, `tpstats`, sample tracing, logs, and replica latency. |
| Automation repeats a change after timeout | Command not idempotent or prior outcome unverified. | Stop, inspect state, enforce action IDs and preconditions before re-running. |
| Two SREs run repair/compaction simultaneously | Missing change locks and concurrency limits. | Add cluster/DC/node scheduling/locks, access control, and audit logging. |
| Same person approves and runs backup deletion | Inadequate separation of duties. | Enforce **separation of duties** for high-risk actions. |

**Not every operation can be rolled back with an inverse command.** `REVOKE` can undo a permission grant, whereas a mistaken `DROP`/data deletion may require backup/restore, and topology changes require dedicated streaming and repair steps. Runbooks must distinguish **config rollback** from **data recovery**.

## 16. Change-Control Runbook Template

~~~text
CHANGE ID:
Objective and reason:
Cluster / DC / node / keyspace / table / token range:
Cassandra/JDK and tool versions:
Requester / approver / executor:
Temporary role and granted permissions:
Maintenance window UTC:

PRECHECK
- [ ] Identity and scope verified.
- [ ] Approval and risk assessment documented.
- [ ] `nodetool status` and replica placement verified.
- [ ] No unexpected topology transitions active.
- [ ] RF/CL and user impact evaluated.
- [ ] Disk/GC/compaction/streaming/repair backlogs within safe bounds.
- [ ] Backup/recovery and stop/rollback plan ready.
- [ ] Baseline UTC time, metrics, and log references saved.

EXECUTION
- [ ] Approved tool/command template used.
- [ ] Executed on exact node, keyspace/table/args.
- [ ] Concurrency capped; no overlapping heavy commands.
- [ ] Action ID, redacted stdout/stderr, session/exit saved.
- [ ] On disconnect: mark UNKNOWN; no blind retries.

POSTCHECK
- [ ] Confirmed task genuinely completed.
- [ ] Verified operation-specific postconditions.
- [ ] Verified data/CQL canary, replica health, RF/CL if applicable.
- [ ] Verified p95/p99, timeouts, disk headroom, and system errors.
- [ ] Verified backup/export/restore if goal is data protection.
- [ ] Explicitly recorded VERIFIED / FAILED / PENDING with evidence.

CLOSE
- [ ] Revoked temporary privileges; closed maintenance session/credentials.
- [ ] Archived audit event off-node with proper retention and access controls.
- [ ] Independent peer review completed for high-risk changes.
- [ ] Logged follow-ups and updated runbook for any discovered gaps.
~~~

In large organizations, embed this template into **policy-enforced automation** rather than relying solely on operator memory. Even then, automation itself must be audited, argument-validated, secret-safe, and equipped with safe abort controls.

## 17. Common False Statements

| Statement | Verdict | Reason |
| --- | --- | --- |
| "Granting `SELECT` in CQL grants access to all `nodetool` commands." | **False** | JMX/OS use separate mechanisms. |
| "Blocking `DELETE` in CQL suffices to protect data from manual deletion." | **False** | Root/file access and admin commands remain impact paths. |
| "A shared SSH account makes audit management easier." | **False** | Prevents attributing actions to specific individuals. |
| "`snapshot` returning exit 0 means the backup can restore." | **False** | Requires export, manifests, and restore verification. |
| "`nodetool repair` on one node proves the whole cluster converged." | **False** | Scope/token ranges/participants/DCs may differ from expectations. |
| "CQL audit always logs JMX actions." | **False** | Two independent channels; session/automation/OS logs are needed. |
| "SSH dropping mid-command means the operation never ran." | **False** | The command may still be running or have partially executed. |
| "Logging raw commands including passwords makes audits more accurate." | **False** | Auditing must never turn into secret leaks. |
| "One successful SELECT proves all replicas match." | **False** | CL only requires a subset of responses, not full replica convergence. |
| "Time-bound privilege elevation, independent post-checks, and post-run revocation make sense." | **True** | Shrinks blast radius and improves traceability and safety. |

## 18. Exercises with Answers

**Exercise 1.** Role `analytics_viewer` has only `SELECT` on CQL tables, yet that user can SSH into the node as root. Can you assert data is protected from deletion by that user?

**Answer:** **No.** CQL RBAC does not restrict root/OS access. You must control file/JMX/SSH/container paths, separate duties, and audit all channels.

**Exercise 2.** `nodetool snapshot -t backup-01 ks` exits 0 and the tag appears in `listsnapshots` on N1. Can you record `BACKUP_COMPLETE` for the whole cluster?

**Answer:** **No.** You only have evidence of a local snapshot on N1. You must confirm node/DC scope, export to independent storage, verify manifests, and run restore checks per backup policy.

**Exercise 3.** CQL audit logs show no `nodetool cleanup` event even though automation logged running it. Does this prove automation lied?

**Answer:** **No.** `cleanup` normally runs over JMX; CQL audit does not log JMX by default. Check bastion/session recordings, automation logs, and node state.

**Exercise 4.** After launching `nodetool repair`, the pipeline loses connectivity before receiving the result. Is the right status `FAILED`, `VERIFIED`, or `UNKNOWN`?

**Answer:** **`UNKNOWN`** until completion evidence and post-checks exist. Never blindly retry without checking whether the repair session is still running or partially synced.

**Exercise 5.** Why must raw commands containing `--password my-secret` never be logged in audit systems?

**Answer:** Process lists, shell histories, and audit storage can expose secrets to many readers. Enforce redaction, proper secret managers/identities, and rotate any leaked secret.

**Exercise 6.** RF = 2 in `dc2`, and the app reads at `LOCAL_QUORUM`. An SRE wants to restart one replica of a partition while the other replica is already down. Are safety conditions met?

**Answer:** **No.** Quorum in dc2 with RF = 2 requires both replicas. If one is already down, restarting the second can make requests at that CL completely unavailable. Restore health and fix the maintenance plan first.

**Exercise 7.** A CQL viewer role has `GRANT SELECT ON TABLE ks.tbl`, yet `DELETE` still succeeds when logged in with an account assigned that role. What must you investigate?

**Answer:** The account's effective privileges may come from **another role**, keyspace-level `MODIFY`, superuser status, or an inactive/misconfigured authorizer. Inspect role memberships, effective permissions, and test with the exact identity.

**Exercise 8.** An `ALTER KEYSPACE` changing a new DC's RF returns success. Can you immediately delete old data on earlier nodes?

**Answer:** **No.** CQL updating metadata does not prove streaming/rebuild/repair populated the new replicas. Run topology, ownership, data, and backup post-checks before considering cleanup.

**Exercise 9.** A `flush` operation completes, yet disk becomes fuller. Is that a contradiction?

**Answer:** **No.** Flushing creates new SSTables and can trigger compaction requiring temporary disk space. Technical command success does not guarantee healthier resource levels; always monitor headroom.

**Exercise 10.** Which two status types must automation separate to avoid confusing "command completed" with "system is correct"?

**Answer:** Separate **tool execution outcome** (`exit 0`, failed, unknown) from **postcondition verification** (`verified`, failed, pending/inconclusive). Only close the change once valid postcondition evidence is recorded.

## 19. Summary Decision Flowchart

~~~mermaid
flowchart TD
    A["Request to run Cassandra tool"] --> B{"Identity and least privilege verified?"}
    B -->|No| C["Grant scoped CQL/JMX/OS role with expiry"]
    B -->|Yes| D["Assess change: scope, approval, recovery"]
    C --> D
    D --> E{"Topology/replica/disk/backup prechecks pass?"}
    E -->|No| F["Stop: remediate missing preconditions"]
    E -->|Yes| G["Execute narrow command via audited channel"]
    G --> H["Save actor + UTC + redacted args + result + action ID"]
    H --> I{"Postconditions verified?"}
    I -->|Yes| J["Revoke temporary access, store evidence, close change"]
    I -->|Unclear/no| K["Keep change open: investigate, replan, or restore"]
~~~

**Remember:** safe Cassandra operations require more than knowing `nodetool` or `cqlsh` syntax. Access must be controlled **across CQL, JMX, OS, and automation channels**; every action needs **identity, reason, scope, UTC timestamps, and secret-redacted logs**; and afterward you must verify **data, replica, topology, resource, and recoverability postconditions**. A command returning success is the start of post-verification, **never final proof that the cluster is safe**.
