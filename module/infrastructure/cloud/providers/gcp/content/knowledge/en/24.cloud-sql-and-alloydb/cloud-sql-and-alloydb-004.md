# Cloud SQL High Availability and Failover Mechanics

A Java `orders-api` service running on Cloud Run stores orders in Cloud SQL for PostgreSQL. When the zone hosting the database suffers an outage, every order write request is at risk of failing. Cloud SQL **High Availability (HA)** reduces downtime by maintaining a **primary and standby across two zones in the same region**, automatically switching roles when the primary can no longer serve.

Yet **HA does not mean zero downtime**, does not replace backups, and **does not automatically recover interrupted in-flight transactions inside the application**. This lesson explains the architecture, limits, configuration, and failover testing, and then shows how to design a Java application that recovers connections without creating duplicate orders or payments.

This lesson belongs to the **Cloud SQL and AlloyDB** chapter of the `CLOUD_PROVIDERS_GCP` module, connecting project/IAM/VPC fundamentals with Compute Engine, GKE, Cloud Run, storage, databases, automated delivery, and reliability/cost monitoring. The primary examples use **Cloud SQL for PostgreSQL**; MySQL and SQL Server have their own backup, logging, and feature requirements.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish **ZONAL** from **REGIONAL (HA)**, primary, standby, and read replicas.
2. Describe **synchronous replication** and the automatic/manual failover process within a region.
3. Properly evaluate **RTO, RPO**, ambiguous transaction outcomes, and SLA boundaries.
4. Enable, verify, and rehearse Cloud SQL HA with `gcloud` in a lab environment.
5. Design Java/HikariCP connection handling, bounded retries, and idempotency for write operations.
6. Distinguish intra-region failover from **PITR, backups, read replicas, and cross-region disaster recovery**.
7. Build dashboards, runbooks, and cost estimates for production systems.

## 1. Why Does Cloud SQL Need HA?

A **ZONAL** Cloud SQL instance operates in a single zone. Cloud SQL can self-heal certain host failures, but when an **entire zone becomes unavailable**, a ZONAL instance does not automatically shift to another zone under the same HA mechanism. To mitigate that risk, choose **REGIONAL**.

| Aspect | ZONAL | REGIONAL / HA |
| --- | --- | --- |
| Database placement | Single zone | Primary and standby in **two different zones**, same region |
| Single-zone outage resilience | Requires manual recovery workflow | Has **automatic failover** when conditions permit |
| Write ownership | Single primary | Standby is promoted to primary |
| Application endpoint | Instance endpoint | **Retains same IP/connection name** during normal intra-region failover |
| Reading from standby | No standby exists | **No**; HA standby is not a read replica for read scaling |
| Committed data | Depends on availability and backups | Synchronous replication across storage in two zones to protect committed writes |
| Baseline cost | Per instance resources | Higher due to standby resources, roughly double for CPU/RAM/storage |
| Full-region outage | Requires DR/restore | **Intra-region HA is still insufficient** |

REGIONAL suits critical databases serving Cloud Run, GKE, App Engine, or Compute Engine. Not every dev/test project needs HA: standby costs and recovery testing effort should match your SLO.

## 2. Primary, Standby, and Synchronous Storage Architecture

~~~mermaid
flowchart LR
    APP["Orders API<br/>Cloud Run / GKE"] --> EP["Cloud SQL endpoint<br/>remains stable"]
    EP --> P["Primary - zone A<br/>reads + writes"]
    P --> D1[("Persistent disk A")]
    P --> SYNC["Synchronous replication"]
    SYNC --> D2[("Persistent disk B")]
    D2 --> S["Standby - zone B<br/>does not accept app queries"]
    CTRL["Cloud SQL HA control<br/>health + failover"] -.-> P
    CTRL -.-> S
~~~

Cloud SQL uses synchronous replication to storage in both zones: a transaction reports **commit success** after the corresponding write data has been durably replicated by the HA mechanism. When the primary or zone A fails, Cloud SQL can promote the zone B standby to primary and route new connections to it.

**Three design boundaries:**

- **The standby is not a read replica.** Never send `SELECT` queries directly to the standby to scale reads.
- **HA covers only one region.** If the entire region experiences a prolonged outage, you need a separate DR architecture.
- **HA does not prevent every restart.** Certain resource errors, such as running out of RAM, can trigger a Cloud SQL **restart** rather than a failover; always check the operation logs to distinguish them.

### 2.1. The Standby After Failover

Once zone B becomes the primary, B **remains the primary** even after zone A comes back online. Cloud SQL rebuilds the old primary as the **new standby**. The system **does not automatically fail back** to zone A when it recovers; if you need to return to zone A, you must schedule a separate **manual failover/failback**.

## 3. RTO, RPO, and SLA: Measuring the Right Scope

| Metric | Question | How Cloud SQL HA Addresses It |
| --- | --- | --- |
| **RTO** (Recovery Time Objective) | How long can service be disrupted before recovery? | Cloud SQL notes failover typically leaves the instance unavailable for **around 60 seconds**; actual duration may vary |
| **RPO** (Recovery Point Objective) | How much written data loss is acceptable? | Synchronous replication aims to preserve **committed writes** on single-zone loss; fundamentally different from async replica/PITR RPO |
| **SLA** | Contractual service availability level? | Depends on edition, eligible machine configuration/tier, and current SLA terms |
| **Application recovery** | Can users resubmit orders safely? | Requires retries/reconnects/idempotency and checking downstream dependencies after failover |

**Do not turn "around 60 seconds" into a guaranteed maximum RTO.** Client bugs, DNS/network behavior, connection pools, JVM warmup, post-failover saturation, and external dependencies can cause the application to take much longer to recover.

### 3.1. What Is an Ambiguous Commit Outcome?

~~~mermaid
sequenceDiagram
    participant A as Java API
    participant P as Primary
    participant S as Standby / HA storage
    A->>P: COMMIT order A100
    P->>S: Replicate committed data
    S-->>P: Sync complete
    Note over A,P: Connection drops while COMMIT response is in flight
    A-xP: No clear response received
    Note over A: Unknown whether transaction committed or not
~~~

There are two possibilities when a client loses its connection at commit time:

1. The database **committed**, yet the client never received the acknowledgment.
2. The database **did not commit**, and the transaction rolled back when the connection dropped.

Both manifest as a JDBC exception. Therefore, **never automatically retry a new order-creation statement without an idempotency key**, even when storage offers strong RPO.

### 3.2. Edition Does Not Imply the Same SLA

Cloud SQL **Enterprise** and **Enterprise Plus** have different SLAs and maintenance features; current documentation cites **99.95%** and **99.99%** respectively when eligibility conditions are met. Do not apply Enterprise Plus's 99.99% SLA to every Cloud SQL instance by default. Verify the **edition, dedicated machine class, HA setup, and SLA terms** in your project.

## 4. When Does Automatic Failover Happen?

Typical sequence:

1. The primary or the zone hosting the primary stops passing **health signals**.
2. Cloud SQL determines the failure qualifies, confirms the standby/secondary zone is healthy, and initiates failover.
3. The standby becomes the new primary, resuming read/write service on the **same instance endpoint**.
4. Existing TCP/PostgreSQL connections are dropped; **the application must reconnect**.
5. Cloud SQL provisions a new standby and restores HA protection after the incident.

~~~mermaid
flowchart TD
    A["Primary unhealthy"] --> B{"Standby/secondary zone healthy?"}
    B -->|Yes| C["Cloud SQL failover"]
    C --> D["Standby becomes primary"]
    D --> E["Clients reconnect<br/>same endpoint"]
    E --> F["Recreate standby when old zone recovers"]
    B -->|No| G["Cannot fail over normally"]
    G --> H["Incident / restore / DR runbook"]
~~~

### 4.1. Not Every Failure Triggers a Failover

| Scenario | Expected Behavior |
| --- | --- |
| Zone A fails, standby B healthy | Automatic failover when conditions are met |
| Eligible VM/primary failure | May fail over |
| Instance out of RAM or resource exhaustion | May **restart**, not necessarily fail over |
| Primary undergoing maintenance or long operation | Failover may be constrained or delayed depending on state |
| Standby/zone B unhealthy | No healthy target available for failover |
| Both zones or entire region unavailable | Intra-region HA cannot resolve |
| Application or Cloud SQL Auth Proxy loses connection | Does not prove database failed over; could be network/identity issue |

During investigation, cross-check **Operations history**, database logs, application logs, and monitoring state. Never infer a failover solely from a `connection reset` exception.

## 5. HA vs. Read Replicas, Backups, and Disaster Recovery

| Tool | Primary Goal | Characteristics |
| --- | --- | --- |
| **Cloud SQL HA standby** | Availability on zone loss | Same region, synchronous, **no direct reads**, automatic failover |
| **Same-region read replica** | Read scaling, offload primary | Different replication from HA standby; **does not auto-promote to primary** on zone loss |
| **Cross-region read replica** | Low-latency reads near users / DR | Async replication, has **replication lag**; requires promotion or separate DR procedure |
| **Automated backup + PITR** | Recovery from accidental deletes, bad logic, flawed migrations | Point-in-time restore, not instant; must be restore-tested |
| **AlloyDB HA** | Availability on a different PostgreSQL-compatible engine | Distinct storage architecture and failover operations; do not apply Cloud SQL commands to AlloyDB |

**Distinguish "HA" from "DR":** Cloud SQL HA generally handles faults within **one region**; DR handles scenarios where a **region suffers an outage** or recovery is needed from a replica/backup in another region. With **Cloud SQL Enterprise Plus**, certain configurations offer **advanced disaster recovery / designated DR replica / switchover**; that is a separate workflow, not two-zone HA standby failover.

### 5.1. A Read Replica Is Not an HA Standby

A read replica has its own endpoint and replication state, serving reads while healthy. During a primary HA failover, a replica outside the failed zone can reconnect to the new primary; a replica inside the failed zone is also disrupted. If read replicas require high availability, check replica HA support and zone placement.

**Never** switch an application from the primary to a read replica just because you see a "replica," unless you have **promoted** it, evaluated RPO, and updated connection endpoints per the runbook.

## 6. Prerequisites Before Enabling HA

The hands-on module uses **PostgreSQL**, though Cloud SQL also supports MySQL and SQL Server. Each engine has different backup and logging requirements.

| Check | Reason |
| --- | --- |
| Region supports edition and machine type | HA requires two eligible zones and regional capacity |
| Select `REGIONAL` instead of `ZONAL` | Enables the primary + standby topology |
| **Automated backups + PITR** for PostgreSQL per configuration rules | Supports backup/recovery workflows; verify before enabling HA |
| MySQL: backups and binary logs per engine requirements | Do not substitute PostgreSQL flags for `--enable-bin-log` |
| IAM `cloudsql.instances.update` and operation permissions | Only authorized deployers/DBAs can toggle HA |
| SLO, change window, and rollback plan | Enabling HA on an existing instance **causes a restart/downtime** |
| Billing budget and quota | REGIONAL increases CPU/RAM/storage costs |
| App supports reconnects and idempotency | Failover drops all existing connections |

**Do not treat enabling HA as a read-only operation.** Converting an existing instance from ZONAL to REGIONAL normally restarts it and can take several minutes or longer depending on disk size and load. In production, secure change approval and assess transaction impact first.

## 7. Read-Only Preflight with gcloud

Assume an instance named `orders-db-ha-lab` in `asia-southeast1`. Substitute an instance name you are authorized to inspect.

~~~bash
gcloud auth list
gcloud config get-value project

gcloud sql instances list --project=PROJECT_ID

gcloud sql instances describe orders-db-ha-lab \
  --project=PROJECT_ID \
  --format="yaml(name,state,region,gceZone,secondaryGceZone,connectionName,settings.availabilityType,settings.backupConfiguration,ipAddresses)"

gcloud sql operations list \
  --instance=orders-db-ha-lab \
  --project=PROJECT_ID \
  --limit=20
~~~

Compare the output against this table:

| Field | Expected Value for HA |
| --- | --- |
| `settings.availabilityType` | `REGIONAL` |
| `gceZone` | Current primary zone |
| `secondaryGceZone` | Another zone in the same region |
| `state` | Typically `RUNNABLE` when ready |
| `settings.backupConfiguration` | Backups and PITR per supported configuration |
| `connectionName` | Identifier used by connectors/Auth Proxy |
| `ipAddresses` | Active endpoints; **avoid logging public IPs unnecessarily** |

**If the instance does not exist or you lack read permissions**, do not create or modify production resources just to complete this step. These commands are for **inspection**, not forcing a failover.

## 8. Creating a PostgreSQL HA Instance in a Lab Project

Example for **authorized users** with budget who understand this instance incurs ongoing charges:

~~~bash
gcloud services enable sqladmin.googleapis.com \
  --project=PROJECT_ID

gcloud sql instances create orders-db-ha-lab \
  --project=PROJECT_ID \
  --database-version=POSTGRES_16 \
  --edition=ENTERPRISE \
  --region=asia-southeast1 \
  --cpu=2 \
  --memory=7680MB \
  --storage-size=20 \
  --storage-auto-increase \
  --availability-type=REGIONAL \
  --backup-start-time=02:00 \
  --enable-point-in-time-recovery
~~~

**This example creates real billable resources.** The `--cpu` and `--memory` flags apply to **Enterprise edition**; Enterprise Plus uses supported machine tiers and does not accept the same custom flags identically. Choose machine type, disk, private/public IP, region, backup retention, deletion protection, and CMEK per organizational policy. Never leave a database public just because it is a lab.

Some projects/regions have different quotas or zone capacities; if creation fails, check permissions, editions, or quotas rather than deleting an existing instance. Refer to the official CLI reference for any changing flags.

### 8.1. Enabling HA on an Existing Instance

If preflight reveals a `ZONAL` instance and the DBA approves:

~~~bash
# IMPACTFUL: may restart the instance and cause downtime!
gcloud sql instances patch INSTANCE_NAME \
  --availability-type=REGIONAL \
  --project=PROJECT_ID
~~~

Before running, verify PostgreSQL backup/PITR settings per Section 7. For MySQL, enabling HA requires specific backup/binary logging and configuration flags; never apply the PostgreSQL sample command and assume it covers all engines.

**Do not use `--availability-type=ZONAL` as a "simple rollback"**: disabling HA removes failover protection and can restart the instance again. Reverting production changes requires technical review and approval.

## 9. Manual Failover to Test the Application

Cloud SQL supports **manual failover** to rehearse an event similar to an actual failover. Run only on an **HA instance**, with no other operations in progress, a healthy standby, and a prepared application.

~~~bash
# STOP: run only after the instance owner approves.
gcloud sql instances failover orders-db-ha-lab \
  --project=PROJECT_ID
~~~

**Real impact:** open database connections are dropped, requests may fail, the primary switches zones, and the standby must be rebuilt. This is **not a read-only lab** and must never be run in production without a change window.

Verify afterward:

~~~bash
gcloud sql instances describe orders-db-ha-lab \
  --project=PROJECT_ID \
  --format="yaml(state,region,gceZone,secondaryGceZone,settings.availabilityType,connectionName)"

gcloud sql operations list \
  --instance=orders-db-ha-lab \
  --project=PROJECT_ID \
  --limit=20
~~~

**Expected outcome:** `gceZone` moves to the former standby zone; the instance returns to a serving state; and `connectionName` remains unchanged. Then verify the application **reconnects automatically and completes transactions**. An operation status of "DONE" alone is not enough to prove business recovery.

### 9.1. Failback Is Not Automatic

After a failover, wait until standby redundancy recovers cleanly before considering a **manual failback**. Failback triggers another failover in reverse and **also disrupts connections**. Never run a second failover just to make a diagram "go back to zone A."

## 10. What Must a Java Application Do During Failover?

Cloud SQL keeps the endpoint stable during intra-region HA failover, but **does not preserve open TCP sessions**. With Java JDBC/HikariCP:

- Avoid keeping a static, long-lived `Connection` or `PreparedStatement` across multiple requests.
- Use a pool with appropriate **connection timeout, maximum pool size, and max lifetime**.
- On network errors, discard the broken connection and obtain a fresh one from the pool.
- Retry acquiring a **new connection** with bounded backoff; avoid tight retry loops while the DB is down.
- If a failure occurs mid-transaction, **retry the entire transaction from the start** on a new connection; never reuse a failed transaction.
- Use an **idempotency key** to handle uncertain transaction outcomes at `COMMIT`.

**Cloud SQL Auth Proxy and the Java Connector do not preserve broken transactions.** Auth Proxy also loses connections on failover, and the app must establish fresh ones. Even though post-failover connections use the same `connectionName`, they cannot "resume" a lost transaction.

### 10.1. HikariCP Configuration Example

A Spring Boot service using `spring-boot-starter-jdbc`, the PostgreSQL driver, and HikariCP can start with settings such as:

~~~properties
spring.datasource.hikari.maximum-pool-size=5
spring.datasource.hikari.minimum-idle=0
spring.datasource.hikari.connection-timeout=10000
spring.datasource.hikari.validation-timeout=5000
spring.datasource.hikari.max-lifetime=1800000
spring.datasource.hikari.idle-timeout=600000
~~~

These are **examples**, not optimal values for every workload. Size pools according to `instances × concurrency × Cloud SQL max_connections`:

~~~text
Estimated max pool total = application instances × maximumPoolSize

Example: 20 Cloud Run instances × 5 = ~100 max pool connections
(excluding migrations, background jobs, monitoring, and admin tools).
~~~

If GKE/Cloud Run autoscales, total connection count can exceed DB limits faster than expected. Managed connection pooling may help where supported by edition/features, but must still be sized and tested.

### 10.2. Safe Retry Pattern

~~~text
BEGIN attempt:
  1. Acquire a new connection with a timeout.
  2. Check requestId/idempotencyKey.
  3. Execute the full transaction.
  4. COMMIT.
  5. Return a deterministic result for the same requestId.

If a connection error occurs before commit or commit outcome is unknown:
  - Discard the broken connection/transaction.
  - Wait with exponential backoff + jitter, with bounded max attempts.
  - Retry the entire transaction with the SAME idempotencyKey.
  - If attempts are exhausted, return a retryable error or enqueue to outbox.

Never retry a non-idempotent write using a brand-new requestId.
~~~

Total retry duration must fit within the caller's timeout (Cloud Run request deadline / HTTP client timeout) and workload constraints — never wait indefinitely.

## 11. Java/JDBC Exercise: Preventing Duplicate Shipping Tasks on Retry

Suppose `POST /shipments` receives a deterministic `requestId` from the client or generates and persists it before processing. PostgreSQL defines two tables:

~~~sql
CREATE TABLE IF NOT EXISTS processed_requests (
    request_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shipping_tasks (
    request_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'READY'
);
~~~

Java example handling **one transaction** on a fresh JDBC connection from the pool:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class ShippingRepository {
    // Caller closes/returns the Connection and retries the whole method with the SAME requestId.
    public static boolean createOnce(
            Connection db, String requestId, String orderId)
            throws SQLException {
        boolean originalAutoCommit = db.getAutoCommit();
        db.setAutoCommit(false);
        try {
            int inserted;
            try (PreparedStatement p = db.prepareStatement(
                    "INSERT INTO processed_requests(request_id, order_id) "
                    + "VALUES (?, ?) ON CONFLICT DO NOTHING")) {
                p.setString(1, requestId);
                p.setString(2, orderId);
                inserted = p.executeUpdate();
            }

            if (inserted == 1) {
                try (PreparedStatement p = db.prepareStatement(
                        "INSERT INTO shipping_tasks "
                        + "(request_id, order_id) VALUES (?, ?)")) {
                    p.setString(1, requestId);
                    p.setString(2, orderId);
                    p.executeUpdate();
                }
            }
            db.commit();   // Marker + side effect commit atomically.
            return inserted == 1;
        } catch (SQLException failure) {
            try {
                db.rollback();
            } catch (SQLException rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
            throw failure;
        } finally {
            db.setAutoCommit(originalAutoCommit);
        }
    }
}
~~~

**How it works:** if the commit succeeded before failover yet the client lost the response, retrying with the same `requestId` hits the unique constraint and avoids creating a second task. If the transaction had not committed, the retry inserts the marker and completes the task. The unique key holds even across concurrent Pods/instances calling the API.

**Example limitations:** in production, verify the **payload hash/`orderId`** when `requestId` already exists; reusing a `requestId` with a different payload must return a conflict rather than silently succeeding. If an error occurs during `setAutoCommit(originalAutoCommit)`, the caller must handle the tainted connection and let the pool discard it per library semantics. Side effects outside PostgreSQL (sending emails, charging payments) are **outside the JDBC transaction**: use a transactional outbox, provider idempotency keys, or reconciliation workflows.

### 11.1. Crash Window Illustration

| Failure Timing | DB State | Safe Retry Behavior |
| --- | --- | --- |
| Before `COMMIT` | Transaction rolled back | Inserts marker and creates task |
| After `COMMIT` but before response | Marker and task exist | Detects duplicate, creates nothing extra |
| After DB commit but before sending Pub/Sub event | DB updated, event may be lost | Use **transactional outbox** for atomic DB state + publish |
| While calling external payment API | Payment status unknown | Use idempotency token with payment provider + reconcile |

**Cloud SQL's strong RPO does not eliminate "unknown commit outcome" on the client side.**

## 12. Connecting from Cloud Run, GKE, and Compute Engine

| Platform | Typical Connection Method | What to Check for Failover |
| --- | --- | --- |
| **Cloud Run** | Cloud SQL integration, Java connector, or Auth Proxy/Private IP | Concurrency, `pool size × max instances`, timeouts, VPC egress, and service account |
| **GKE** | Workload Identity Federation, Cloud SQL Auth Proxy sidecar/connector, or Private IP | Many Pod replicas retrying simultaneously, Pod readiness, and NetworkPolicy |
| **Compute Engine** | VM service account + Auth Proxy/connector or protected IP | Persistent proxy lifecycle, firewall rules, service health |
| **App Engine** | Environment-specific connector/integration | Instance scaling and connection quota |
| **AlloyDB** | Separate HA API/connector | **Do not use** Cloud SQL `gcloud sql instances` commands |

### 12.1. IAM and Networking Cannot Be Skipped

- Runtime identity requires **Cloud SQL Client** when using a connector/Auth Proxy per configuration; the database still requires separate **database authentication/roles**.
- Private IP requires VPC network routing and Private Service Access/PSC configuration depending on topology.
- Use TLS/certificates, IAM DB auth, or Secret Manager per policy; **never bake DB passwords into container images**.
- Never open public IP or `0.0.0.0/0` authorized networks just to test failover.
- In cross-project topologies, check service account IAM, VPC routing, region, and quotas across projects.

A post-failover connection error may stem from the app pool, proxy, firewall, IAM, or DNS/PSC — **not necessarily because the database failed to switch primaries**.

## 13. Backups, PITR, and Data Recovery Beyond HA

HA protects against a **single-zone outage**, yet erroneous data written by an app bug or human mistake **is also replicated synchronously**:

~~~text
UPDATE accounts SET balance = 0;   -- Business logic bug
            |
            v
Corrupted data is durably written to both HA zones.
~~~

Therefore, you still need:

- **Automated backups** with retention and storage location meeting business RPO/RTO.
- **Point-in-time recovery (PITR)** to restore to a specific moment when enabled and logs remain within retention.
- Periodic **restore drills** against a test instance; never treat a backup "SUCCESS" status as proof the app can recover.
- Runbook steps covering secrets/encryption keys, IAM, connection endpoints, and migration rollbacks.
- A **cross-region DR replica** or appropriate strategy if survival across a full-region outage is required.

**RTO/RPO for PITR, backups, and async replicas differ from HA failover.** For example, recovering via an async replica may incur replication lag, while restoring from backup includes instance provisioning and consistency checks.

## 14. Operations, Logs, and Cloud Monitoring

### 14.1. Observing Failover via Operation Logs

~~~bash
gcloud sql operations list \
  --instance=orders-db-ha-lab \
  --project=PROJECT_ID \
  --limit=30

# Once you have a real OPERATION_ID:
gcloud sql operations describe OPERATION_ID \
  --project=PROJECT_ID
~~~

In the Console: **Cloud SQL → instance → Operations/Logs** shows **Failover**, **Restart**, maintenance, zone changes, and operation errors. Determining who triggered a failover may require **Cloud Audit Logs** with appropriate audit logging enabled.

Reading Cloud Logging:

~~~bash
gcloud logging read \
  'resource.type="cloudsql_database" AND severity>=ERROR' \
  --project=PROJECT_ID --freshness=1h --limit=50
~~~

**Note:** application JDBC exceptions appear in **Cloud Run/GKE/VM** logs, not necessarily in `cloudsql_database`. Combine both log sources.

### 14.2. Minimum Dashboard

| Group | Metrics / Signals | Action on Anomaly |
| --- | --- | --- |
| Cloud SQL instance | State/availability, failover/restart operations | Confirm whether a real failover occurred |
| Database | CPU, memory, disk utilization | Distinguish overload from zone fault |
| Connections | Active connections, connection errors | Detect retry storms or pool exhaustion |
| Latency | Query duration, transaction errors | Verify whether the DB is serving normally again |
| Application | HTTP 5xx, timeouts, p95/p99, retry counts | Assess user impact |
| Data | Valid order counts, duplicate IDs, invariant violations | Assess business integrity impact |
| DR | Backup/PITR status, replica lag, restore drills | Assess recovery readiness beyond HA |
| FinOps | CPU/RAM/storage, backups, networking, logs | Track cost after enabling HA |

Google Cloud documentation notes that **automatic failover metrics do not necessarily include manual failovers**. Therefore, rely on **operation history + logs + application tests** during drills; do not conclude a drill failed just because the automatic failover chart stayed flat.

## 15. Safe Failover Drill Runbook

**Mandatory prerequisites:** test/HA lab environment, owner approval, verified backups/PITR, client instrumentation, and abort criteria.

~~~mermaid
flowchart TD
    P["Preflight: DB REGIONAL + standby healthy"] --> B["Backup and verify application"]
    B --> I["Record initial zone, instance endpoint, metrics"]
    I --> F["Manual failover on LAB"]
    F --> O["Monitor operations + JDBC errors"]
    O --> R["App reconnects + bounded retries"]
    R --> D{"SLO/DB invariants met?"}
    D -->|Yes| DONE["Record observed RTO + postmortem"]
    D -->|No| STOP["Halt canary / declare incident / DR runbook"]
~~~

### 15.1. Before Failover

1. Capture `gcloud sql instances describe`, recording `gceZone`/`secondaryGceZone`, region, and availability type.
2. Confirm the standby is healthy and no long-running operation is active.
3. Run safe probes: `SELECT 1` and a test API request carrying a `requestId`.
4. Record target RTO, start timestamp, traffic rate, baseline connection errors, and app/database CPU.
5. Verify Cloud SQL backups/PITR and permissions for the environment.

### 15.2. During Failover

- DBA runs `gcloud sql instances failover` **once** on the lab instance.
- Watch operations, HTTP 5xx, JDBC connection errors, pool checkout times, retries, and DB connection counts.
- Observe whether test clients experience brief errors; **never retry infinitely** and never weaken IAM/network policies to troubleshoot.
- If aborting is necessary, prioritize **data recoverability** and coordinate with the incident lead; avoid rapid back-to-back failovers/failbacks.

### 15.3. After Failover

- Confirm the new primary zone, unchanged endpoint/`connectionName`, instance status, and standby recovery progress.
- Run `SELECT 1` and lab read/write checks; verify zero duplicate IDs and expected transaction states.
- Calculate **observed RTO** from the moment service degraded until SLO recovered (not when the CLI command returned).
- Document differences between **automatic failover, manual failover, and restart**, plus effects on backups/replicas.
- Save updated runbooks, alerts, and any required retry/backoff tuning.

## 16. Troubleshooting After Enabling HA

| Symptom | Possible Cause | How to Verify |
| --- | --- | --- |
| `availabilityType=ZONAL` | HA not enabled or patch incomplete | Describe / operation log |
| Standby zone missing | Instance not REGIONAL or still reconfiguring | `secondaryGceZone`, status, operations |
| Instance unreachable ~1 minute | Failover in progress | Operations + zone change |
| Connection dropped without Failover | Restart from memory/CPU exhaustion or network/connector issue | Operation type, resources, app logs |
| JDBC continues failing post-failover | Pool retains stale connections or retries reuse old connection | Pool metrics, connection validation |
| Cloud SQL Auth Proxy running yet app fails | Proxy does not preserve old sessions, or IAM/network/config issue | Proxy logs, reconnects, credentials |
| App retries create duplicate orders | Missing idempotency on ambiguous commit outcome | Unique request ID, DB records |
| GKE scales replicas and DB hits `too many connections` | `Pool size × Pod count` too high | Pool settings, `max_connections` |
| Read replica unavailable | Replica in failed zone or lag/misconfigured connection | Replica zone, status, replication lag |
| Enabling HA caused downtime | ZONAL → REGIONAL conversion triggers restart | Change record / operation duration |
| Manual failover didn't increment automatic failover metric | Metric tracks automatic events only | Operations history |
| Bill rises after HA | Standby CPU/RAM/storage and backups/network | Cloud Billing SKUs, edition/region |

## 17. Cost: Trading Off Against Availability

Cloud SQL HA provisions primary/standby compute and multi-zone storage. Documentation describes HA as roughly **doubling the standalone cost for CPU, RAM, and storage**, excluding backups, networking, read replicas, logging, data egress, and related services.

| Cost Item | What to Estimate |
| --- | --- |
| Primary + standby | CPU/memory by edition, tier, and region |
| Storage | Capacity, disk type, regional redundancy |
| Backups/PITR | Retention, transaction logs, restore storage |
| Read replicas/DR | Per replica, cross-region transfer, and secondary region |
| Connection/data traffic | Network/VPC, egress, Cloud SQL connectors |
| Observability | Logging, Monitoring, and traces |
| Drills | Load tests, lab instances, temporary resources |

**Never treat HA as "just paying more while changing nothing else"**: for real workloads, availability reduces outages, yet you still must tune connection pools, retries, and SLOs to realize the benefit. Use **Cloud Billing Reports, budgets, and alerts**; budget alerts **do not automatically cap spending**.

### 17.1. Simple Cost Model

Suppose the monthly CPU/RAM/storage cost of a **standalone** instance in the same tier/region is `C`:

~~~text
HA base infrastructure cost ≈ 2 × C

Total system cost ≈ HA base + backup/PITR + network
                    + read replicas/DR + observability + app resources
~~~

This is a **relative model**, not a formal quote. Look up actual pricing by engine/edition, machine, disk, region, and billing SKUs.

## 18. Synthesis Scenario: Orders API and Two-Zone Failover

**Context:** Java `orders-api` on Cloud Run, Cloud SQL PostgreSQL Enterprise HA across two zones in `asia-southeast1`, Cloud Storage holding invoices, and Pub/Sub publishing `OrderPaid`.

**Incident:** the primary zone goes down. During failover, 2% of requests briefly hit `SQLTransientConnectionException`; several order-write requests have uncertain `COMMIT` outcomes.

**Mitigation Design:**

| Layer | Control |
| --- | --- |
| Cloud SQL | `REGIONAL` primary+standby, backups/PITR, monitoring |
| Cloud Run | Bounded retries with jitter, respecting request deadlines |
| Java | HikariCP acquires fresh connections; pool sized against total instances |
| Database | Unique `request_id`/idempotency key, ACID transactions for business state |
| Pub/Sub | Transactional outbox so `OrderPaid` is not lost after DB `COMMIT` |
| Networking | Private connectivity, Auth Proxy/Java Connector, least-privilege IAM |
| DR | Cross-region replica/restore drills if region-loss resilience is required |
| SRE | Dashboards for 5xx, latency, connection errors, operation logs, restore/HA drills |

**Expected outcome:** new requests may fail briefly during the failover window, then reconnect via the existing endpoint; retried write requests with the **same idempotency key** never create duplicate orders or double charges. This is an operational target **that must be verified by testing**, not something Cloud SQL guarantees automatically for arbitrary app code.

## 19. Practice Exercises and Self-Check

**Exercise 1 — Read-only HA audit.** Run `gcloud sql instances describe` on a lab instance and identify `availabilityType`, primary/secondary zones, state, backups, and PITR.

*Pass criteria:* Two distinct zones in the same region, `REGIONAL`, and proper prerequisites.

**Exercise 2 — Measure RTO.** In an authorized environment, record the timestamp when the app starts failing, trigger a single failover, and record when the SLO recovers.

*Pass criteria:* An **observed application RTO**, not inferred from "~60 seconds" or CLI completion time.

**Exercise 3 — Transaction outcome.** Simulate a successful `COMMIT` followed by a client timeout; resend with the same `requestId`.

*Pass criteria:* Only one business record exists; the unique key preserves the invariant.

**Exercise 4 — DR design.** The database must recover after a multi-day **full-region power outage**. Propose what must be added.

*Suggested answer:* Cross-region DR replica/backups and a promotion/restore runbook matching RPO/RTO; two-zone HA alone is insufficient.

**Question 5.** Can an HA standby serve read queries like a read replica?

*Answer:* No. The HA standby is a failover target, not a read endpoint.

**Question 6.** Does failover issue a mandatory new connection string for the application?

*Answer:* For standard intra-region HA, the IP/`connectionName` stays the same; however, old TCP/JDBC connections are closed and must reconnect.

**Question 7.** If Cloud SQL HA replicates storage synchronously, do you still need backups/PITR?

*Answer:* Yes. Accidental deletes, bad schema changes, and corrupted data are also replicated, requiring restore/PITR.

**Question 8.** Does a `connection reset` error always prove a failover occurred?

*Answer:* No. It could be networking, proxy, pool expiration, maintenance, or a restart; check Operations/logs.

**Question 9.** After failover, does the primary automatically move back to zone A when zone A recovers?

*Answer:* No. Zone B stays primary; failback is a separate operation that causes another disruption.

**Question 10.** Why shouldn't you retry a transaction starting from the last `INSERT` on the failed connection?

*Answer:* The transaction/session may have aborted or have an uncertain commit outcome; acquire a new connection and retry the **entire transaction** with an idempotency key.

**Question 11.** Does a cross-region read replica guarantee RPO = 0 like two-zone synchronous HA?

*Answer:* No. Async replication can lag, requiring DR planning and lag monitoring.

**Question 12.** Is converting an instance from ZONAL to REGIONAL completely zero-downtime?

*Answer:* No. Reconfiguring triggers a restart and requires a change window.

**Question 13.** Should you raise JDBC pool sizes indefinitely during failover to reconnect faster?

*Answer:* No. Retry storms and hitting DB `max_connections` can prolong the outage; enforce pool caps and backoff.

**Question 14.** Can you apply Enterprise Plus pricing/SLA terms to an Enterprise instance?

*Answer:* No. Edition, SLA eligibility, and billing terms must be verified separately.

## 20. Production Checklist

- [ ] Critical production databases evaluated for `REGIONAL` HA across two zones.
- [ ] Edition, dedicated machine class, region, SLA, and cost approved.
- [ ] Backups/PITR have clear retention and verified restore drills.
- [ ] Primary/standby healthy; status and operations monitored.
- [ ] Applications use pools with connection validation, timeouts, and bounded retries.
- [ ] Idempotency keys protect write transactions against ambiguous `COMMIT` outcomes.
- [ ] External side effects (Pub/Sub, payments, email) use outbox or reconciliation.
- [ ] Cloud Run/GKE/VM IAM, database roles, and VPC/private networking/TLS configured properly.
- [ ] Connection budget calculated as **instances × pool size**.
- [ ] Manual failover/failback runbook tested for both positive and negative cases.
- [ ] Separate cross-region DR plan exists: replicas/backups/restore/promotion.
- [ ] Alerts configured for SQL errors, latency, connections, CPU/disk, backups, and business SLOs.
- [ ] Any production change to availability type, zone, or failover requires approval.
- [ ] Budgets and billing reviews include HA storage, replicas, backups, and networking.

## 21. Conclusion

**Cloud SQL high availability** uses a **primary–standby pair across two zones in one region**, replicating storage synchronously and failing over automatically when the primary zone or instance fails. Existing connections will drop; the application must **reconnect and retry safely**, while rolling back bad data or surviving a full-region outage requires **separate backups/PITR and DR**.

For Java services, the core operational formula is: **REGIONAL HA + explicit SLO + failover drills + bounded connection pools + full-transaction retries with idempotency keys + monitoring and cost budgeting**.

## Official References

- [Cloud SQL: Availability overview](https://cloud.google.com/sql/docs/availability)
- [Cloud SQL for PostgreSQL: High availability](https://cloud.google.com/sql/docs/postgres/high-availability)
- [Enable/disable Cloud SQL HA (PostgreSQL)](https://cloud.google.com/sql/docs/postgres/configure-ha)
- [Cloud SQL for PostgreSQL: Instance settings](https://cloud.google.com/sql/docs/postgres/instance-settings)
- [Cloud SQL for PostgreSQL: Editions and SLAs](https://cloud.google.com/sql/docs/postgres/choose-edition)
- [Cloud SQL for PostgreSQL: Manage database connections](https://cloud.google.com/sql/docs/postgres/manage-connections)
- [Cloud SQL Auth Proxy and failover](https://cloud.google.com/sql/docs/postgres/sql-proxy)
- [Cloud SQL PostgreSQL: Replication and read replicas](https://cloud.google.com/sql/docs/postgres/replication)
- [Cross-region replica promotion / DR](https://cloud.google.com/sql/docs/postgres/replication/cross-region-replicas)
- [Cloud SQL PostgreSQL: Disaster recovery](https://cloud.google.com/sql/docs/postgres/intro-to-cloud-sql-disaster-recovery)
- [Cloud SQL PostgreSQL: Logging](https://cloud.google.com/sql/docs/postgres/logging)
- [gcloud sql instances create](https://cloud.google.com/sdk/gcloud/reference/sql/instances/create)
- [gcloud sql instances failover](https://cloud.google.com/sdk/gcloud/reference/sql/instances/failover)
- [Cloud SQL pricing](https://cloud.google.com/sql/pricing)
