# Choosing Cloud SQL, AlloyDB, and Self-Managed Databases

An enterprise is building an online learning platform on Google Cloud: Cloud Run serves APIs, GKE runs background jobs, and order, learning progress, and payment data must be stored durably. The team has three options: use **Cloud SQL**, use **AlloyDB for PostgreSQL**, or self-manage a database management system on **Compute Engine/GKE**. All three can run SQL, yet they differ significantly in **database engines, level of control, availability, performance, cost, and operational responsibility**.

In the **Cloud SQL and AlloyDB** chapter of the **CLOUD_PROVIDERS_GCP** module, this lesson provides a practical decision-making workflow that connects concepts across projects/IAM, VPC, Compute Engine, GKE, Cloud Run, storage, reliability monitoring, and budgeting. The goal is not to pick the "most powerful" product, but to choose a solution that is **fit for purpose, measurable, and operable**.

**After this lesson, you will be able to:**

1. Distinguish the management scope and supported engines of Cloud SQL, AlloyDB, and self-managed databases.
2. Evaluate compatibility, OLTP/analytics workloads, scaling, HA, backup, RPO/RTO, connectivity, and access control.
3. Build a decision matrix based on metrics rather than generic performance claims.
4. Plan migrations, benchmarks, and failover tests aligned with data risk.
5. Estimate Total Cost of Ownership (TCO) including both infrastructure resources and operational effort.
6. Inspect configurations with `gcloud`, complete a selection exercise, and explain trade-offs to an architect.

## 1. Three Relational Database Provisioning Models

### 1.1. Cloud SQL: Managed Service for Three Popular Engines

**Cloud SQL** is a managed relational database service on Google Cloud for **PostgreSQL, MySQL, and Microsoft SQL Server**. Google manages much of the infrastructure toil, such as instance provisioning, platform patching, backup mechanisms, replicas, monitoring, and configured failover.

Key points:

- Applications still communicate over the familiar SQL protocol/driver of the **chosen engine**; switching from MySQL to PostgreSQL is not just flipping a Cloud SQL flag.
- Cloud SQL offers **Enterprise** and **Enterprise Plus** editions with different performance, availability, machine, storage, and pricing characteristics depending on engine/version. Always specify the edition in your cost estimate.
- An instance by default may be **zonal** only; to withstand a zone failure, you must configure appropriate **high availability (regional)**.
- A **read replica** increases read capacity and supports certain DR strategies, but it does not automatically become an automatic HA standby.
- Managed does not mean zero DBA work: the application team still manages schemas, indexes, query plans, connection pools, data permissions, and restore testing.

**Example:** a product using MySQL 8 with straightforward backup workflows and moderate transaction load should generally evaluate Cloud SQL for MySQL first, rather than rewriting the entire application for PostgreSQL just to use a different service.

### 1.2. AlloyDB for PostgreSQL: Managed PostgreSQL for Demanding Workloads

**AlloyDB for PostgreSQL** is a **PostgreSQL-compatible** service designed for mission-critical transactional workloads, read-heavy traffic, and mixed analytical queries alongside OLTP. Unlike Cloud SQL, AlloyDB uses an architecture that **separates compute from distributed storage**, providing a primary instance and optional **read pool instances**.

- **Primary instance:** handles writes and can serve reads. HA configurations typically use redundant nodes across two zones within a region with automatic failover.
- **Read pool instance:** a group of one or more nodes serving **read-only** queries; used to scale reads or isolate query load.
- **Columnar engine:** accelerates certain scan/join/aggregate queries using in-memory columnar storage; not every SQL query benefits.
- **Backup/continuous backup, PITR, and replication/DR options:** support data protection, but must be enabled/configured and tested against RPO/RTO.

AlloyDB is **not managed MySQL or SQL Server**. Even though it is PostgreSQL-compatible, it does not automatically support every extension, superuser privilege, hook, or operational pattern of a self-managed PostgreSQL deployment. You must test **drivers, extensions, SQL dialect, migrations, replication, and query behavior** against the target version.

**Example:** a PostgreSQL system handling thousands of transactions per second alongside read-heavy analytical dashboards on the same data can evaluate AlloyDB primary + read pool + columnar engine, but should select it only after benchmarking **p95/p99, CPU, locks, I/O, lag, and cost**.

### 1.3. Self-Managed Database: Operating the Engine Yourself on Cloud Infrastructure

**Self-managed** means the organization installs and operates PostgreSQL/MySQL/SQL Server or another engine on **Compute Engine VMs**, or runs it in **GKE** with operators/StatefulSets and persistent volumes. Google manages the cloud infrastructure layer under IaaS/Kubernetes services, while the operations team assumes much broader responsibility for the database.

The team gains control over versions, OS/engine parameters, extensions, replication tooling, and failover topology. In return, you must handle:

- OS and database patching/upgrades, version compatibility, and zero-downtime maintenance if required.
- Primary/standby setup, fencing/leader election, quorum, failover, split-brain prevention, and connection load balancing.
- Backup/PITR, encryption, restore verification, cross-region DR, and zonal outage testing.
- Disk sizing/IOPS, filesystems, disk latency, capacity planning, monitoring, alerting, on-call rotation, and incident response.
- Security vulnerabilities, auditing, licensing, access control, and compliance obligations.

**Self-managing on GKE does not automatically provide HA**: three Pods can end up in the same zone; a zonal volume may fail to mount in another zone; an operator can be misconfigured; and database replication still needs data protection and leader integrity.

## 2. Quick Comparison Before Going Deeper

| Criterion | Cloud SQL | AlloyDB for PostgreSQL | Self-managed on VM/GKE |
| --- | --- | --- | --- |
| Primary engines | **PostgreSQL, MySQL, SQL Server** | **PostgreSQL-compatible** | Engine/version per team capability |
| DB infrastructure responsibility | Mostly managed | Mostly managed | User carries broad responsibility |
| OS/engine customization | Limited | Limited | Broad, depending on VM/operator and license |
| Primary target use cases | Common relational apps, lower ops burden | PostgreSQL with high performance and availability demands | Specific OS/extension/tooling dependencies, regulations, or custom topologies |
| Read scaling | Read replicas (with replication lag) | Read pool nodes; separate read routing | Self-designed and operated replicas |
| Single-zone availability | **Regional HA** configuration | HA primary per configuration | Self-designed replicas, role promotion, and volumes |
| Full-region recovery | Supported DR/cross-region configuration | Supported secondary/DR configuration | Self-built and operated DR |
| Backup/PITR | Managed features, must be enabled/tested | Managed features, must be enabled/tested | Fully self-designed |
| Cost | Instance + storage + network + backup + license/edition if applicable | Primary/read pool compute + storage + backup + network | VM + disk + network + license + DBA/on-call effort |
| Main risks | Engine/config limits, connections, and maintenance | Cost and actual PostgreSQL compatibility | Operational errors, patching, HA/DR, and staffing |

**Do not assume:** that Cloud SQL is always slower than AlloyDB, that AlloyDB is always cheaper, or that self-managed is always more economical. Such conclusions must come from **benchmarking the same workload and total cost**, not from product names.

### 2.1. Diagram of the Three Options for an Application

~~~mermaid
flowchart TB
    APP["Cloud Run / GKE<br/>Orders API"] --> CHOICE{"Engine requirements,<br/>scale, ops, RTO/RPO?"}
    CHOICE --> SQL["Cloud SQL<br/>MySQL / PostgreSQL / SQL Server"]
    CHOICE --> ALLOY["AlloyDB<br/>Primary + read pool if needed"]
    CHOICE --> SELF["Compute Engine / GKE<br/>Self-managed DB"]
    SQL --> CTRL["Secure connectivity, HA,<br/>backup, monitoring, cost"]
    ALLOY --> CTRL
    SELF --> CTRL
~~~

Before comparing infrastructure options, confirm that **a relational database is actually the right fit**: for objects/videos use Cloud Storage; for very large analytical datasets consider BigQuery; for global write scale and different consistency models consider Spanner. This lesson strictly compares the **three ways to deploy a relational database** per the assigned topic.

## 3. Decision Criteria in Priority Order

### 3.1. Start with Engine and Compatibility

This is typically an **elimination criterion**, more important than advertised performance:

| Current State / Requirement | Candidate to Evaluate First | Mandatory Verification |
| --- | --- | --- |
| App uses **MySQL** and cannot change SQL/drivers | Cloud SQL for MySQL | Version, collation, stored procedures, replication, and license dependencies |
| App uses **SQL Server**, T-SQL, or Microsoft ecosystem | Cloud SQL for SQL Server | SQL Server edition/features/agent/jobs, licensing, and migration dependencies |
| Standard PostgreSQL app, moderate load, want less DBA work | Cloud SQL for PostgreSQL | Extensions, major version, connection limits, HA, and backups |
| PostgreSQL app needing high throughput / complex reads | Cloud SQL Enterprise Plus **and** AlloyDB | Benchmark on the same dataset; read pool, columnar benefit, TCO |
| Need OS-level extensions/agents or deep privileges unsupported by managed services | Self-managed PostgreSQL / corresponding engine | Capability to operate HA/DR, patching, auditing, and staffing cost |
| Simply want to avoid managing VMs without load data yet | Cloud SQL as a reasonable baseline | Do not prematurely jump to AlloyDB based on assumptions |

**PostgreSQL compatibility** does not mean *every extension, superuser operation, filesystem interaction, replication hook, or version is supported*. A minimal migration assessment must run **DDL, critical queries, an extension inventory, and regression tests** on the real target.

### 3.2. Classify the Workload

| Signal | Meaning | Evaluation Direction |
| --- | --- | --- |
| Small/medium OLTP, short transactions, few complex queries | Operational overhead is usually a bigger risk than engine limits | Prioritize benchmarking an appropriate Cloud SQL tier |
| Write-heavy, lock contention, or hot rows | Bottleneck may be schema/transactions, not just CPU | Optimize SQL/indexes/partitioning before scaling machine size |
| Read-heavy with many concurrent users | May need read load separation | Compare Cloud SQL read replicas with AlloyDB read pool |
| Analytical SQL scans/joins/aggregations on transactional data | Queries can compete for resources with OLTP | Test AlloyDB columnar engine and read pool; consider BigQuery for large OLAP |
| Mandatory root/OS tuning or unsupported plugins | Managed services have feature boundaries | Self-managed with runbooks and qualified staff |
| Very tight budget yet high HA demands | Cost vs. risk conflict | Calculate HA costs, review SLO requirements, and adjust architecture |

**A fair test** must measure the same dataset, read/write ratio, concurrency, transaction isolation, cache hit rate, p95/p99 query latencies, checkpoint/vacuum behavior, and replication status. Never compare a benchmark on an idle primary against a self-managed system running backups.

### 3.3. Questions to Ask Before Choosing a Service

1. Is **MySQL, SQL Server, or PostgreSQL** mandatory? Which extensions, triggers, or stored procedures cannot be dropped?
2. What are the TPS, RPS, **p95/p99**, DB size, growth rate, and read/write ratio?
3. Have the SLO, RTO, and RPO been approved by the owner? Are connection drops during failover acceptable?
4. Do you need **multi-region** for DR or data residency, or only resilience against a single zone failure?
5. How will connection counts from Cloud Run/GKE grow during autoscaling? Is proper connection pooling in place?
6. Does the team have on-call DBAs, backup-restore testing practices, and engine upgrade skills?
7. Does the economic value of reducing operational toil outweigh higher compute/storage costs?

## 4. High Availability, Read Scaling, and Disaster Recovery

### 4.1. Cloud SQL: Zonal, Regional HA, and Read Replicas

Cloud SQL **zonal/standalone** is the simplest option, but when an entire zone fails there is generally no **automatic zonal failover**. With **regional high availability**, Cloud SQL maintains a primary and a standby across two zones in the same region; data is replicated synchronously by the service mechanism, with automatic failover when conditions permit.

**Applications can still experience dropped connections** during failover and must reconnect/retry safely; HA does not guarantee zero-second downtime. In-flight write queries must be handled with transactions/idempotency rather than blind retries.

A **read replica** is a copy dedicated to read queries and typically has **replication lag**. Do not use a replica to immediately read a just-committed transaction if the business logic requires strong read-after-write consistency without verification. Crucially, **a read replica does not replace an HA standby** and does not automatically take over all write traffic if the primary fails. When used for DR, you need a promotion procedure, routing updates, data verification, and acceptance of a non-zero RPO based on actual lag.

### 4.2. AlloyDB: Primary HA and Read Pool

AlloyDB consists of a **cluster** in a region, a **primary instance**, and optional **read pool instances**. Primary HA is designed with redundant nodes across multiple zones; a read pool can have one or more nodes to scale reads. Read pools **do not accept application write transactions**.

~~~mermaid
flowchart LR
    API["Cloud Run / GKE API"] -->|"Writes + consistent reads"| PRIMARY["AlloyDB primary<br/>HA within region"]
    REPORT["Reporting / search API"] -->|"Read-only traffic"| POOL["Read pool<br/>multiple nodes if needed"]
    PRIMARY <-. "Distributed storage / replication" .-> POOL
    POOL --> COL["Columnar engine<br/>if beneficial in benchmark"]
~~~

The diagram above shows the **logical flow**, not a complete physical network topology. Adding a read pool **does not automatically route** an application's `SELECT` statements to the read endpoint: you must configure client routing/connection strings or supported forwarding features. If queries require immediate read-after-write consistency, review primary read policies, replica lag, and transactions.

### 4.3. HA, Backup, PITR, and DR Solve Four Different Problems

| Mechanism | Protects Against | Does Not Guarantee |
| --- | --- | --- |
| **Multi-zone HA** | VM/zone failures within the same region per product capabilities | Accidental table drops, ransomware, full-region outage |
| **Read replica** | Read scaling, can participate in DR plans | Replacing automatic HA, strictly synchronous reads at all times |
| **Backup** | Data recovery from stored snapshots | Zero downtime; untested backups may be unusable |
| **PITR** | Restoring to a point in time before a logic error within the retention window | Recovering data beyond retention or when logs are unavailable |
| **Cross-region DR** | Regional outage according to replication/failover plan | Zero data loss under asynchronous replication, or success without drills |

**RTO** is the acceptable recovery time; **RPO** is the maximum acceptable data loss interval. They must be measured via **restore/failover drills**, not inferred directly from the word "regional" or a marketing SLA line.

For example, tuition payment transactions with a very low RPO require appropriate data consistency and reconciliation mechanisms; you may need to block writes during failover rather than allowing two active primaries.

### 4.4. With Self-Managed, HA Is a System You Must Operate

At a minimum, you must design:

- Replication mode (synchronous/asynchronous), lag monitoring, quorum/leader election, and fencing to prevent **split-brain**.
- Connection redirection (DNS, virtual IP, proxy, or service discovery), retry logic, and handling of interrupted transactions.
- Spreading replicas/disks across zones per product capabilities; a **zonal Persistent Disk** does not automatically mount in another zone after an outage.
- Independent backups, retention, PITR, checksum/restore validation, and restricted backup deletion permissions.
- Regional DR, failover/failback drills, on-call coverage, monitoring, and evidence-backed RTO/RPO targets.

Running a PostgreSQL primary in one Pod with a PVC and two replica Pods is not proof of HA until failover, data integrity, and consistency have been verified.

## 5. Connectivity, IAM, and Data Protection

### 5.1. Design the Network Path Before Creating an Instance

With Cloud SQL, choose between **private IP**, **public IP with appropriate controls**, or **Private Service Connect** in supported configurations. When using the **Cloud SQL Auth Proxy** or **Cloud SQL Language Connectors**:

- The connector supports IAM-based authentication for **connecting to the instance** and establishes an encrypted channel; it **does not replace** database-level permissions in PostgreSQL/MySQL/SQL Server.
- To use **private IP**, the client/proxy must still have a **network path to the VPC** hosting the private endpoint; the proxy does not create VPN or VPC routes on its own.
- Do not bind the Auth Proxy on `0.0.0.0` or a public port without appropriate protection; by default it only needs to bind to loopback/local sockets.
- Cloud Run/GKE must be granted the right service identity, connector permissions, and networking; avoid baking service account JSON keys into container images.

With AlloyDB, applications typically connect over **private networking** using the PostgreSQL protocol; configure networking/connectors and access controls appropriate to the product version. With self-managed databases, the operations team must design firewalls, TLS, certificate rotation, service discovery, and network isolation themselves.

### 5.2. Cloud Identity Is Separate from Database Identity

| Layer | Question | Example |
| --- | --- | --- |
| **Google Cloud IAM** | Which principal can create/manage the instance or use the connector? | Cloud Run service account has permission to connect to Cloud SQL. |
| **Database login/role** | Which tables can the app SELECT/INSERT/UPDATE? | Role `orders_app` can only access the assigned transactions schema. |
| **Network access** | Do IP/VPC/firewall rules allow the connection? | GKE workload runs in a subnet with a route to the DB private IP. |
| **Application authorization** | Which learner can read which orders? | Backend checks `student_id`/tenant before querying. |

A service account permitted to connect to Cloud SQL is **not automatically a PostgreSQL superuser**. Use IAM database authentication if supported by the engine/version and suited to your needs, or manage database credentials via Secret Manager with a rotation workflow; never hardcode passwords in source code or public Kubernetes manifests.

### 5.3. Operational Security Checklist

- Separate **dev/staging/prod** by identity and data boundary; never reuse broad-privilege DB accounts.
- Enforce TLS and secure connection channels; configure **private connectivity** when required by residency/security policies.
- Apply least-privilege IAM, schema-scoped DB roles, and redacted audit/query logs; avoid logging sensitive data or passwords.
- Manage encryption at rest/KMS/CMEK **where supported by features and policies**, including key lifecycle and recovery.
- Restrict backup access, enforce retention, and protect against accidental deletion; backups should be isolated from broad operational accounts.
- Maintain vulnerability patching workflows, maintenance windows, upgrade testing, and incident response procedures.
- Monitor connection counts: Cloud Run/GKE autoscaling can spin up hundreds of instances, each opening multiple connections and exhausting DB slots.

## 6. Scaling, Performance, and Connection Management

### 6.1. Scaling Reads Is Different from Scaling Writes

**Adding CPU/RAM** helps when queries are genuinely CPU-bound, yet many systems bottleneck on indexes, locks, I/O, connections, or long-running transactions. Read replicas/read pools can offload reads, **but do not automatically increase write throughput** on the primary in a single-writer model.

| Bottleneck | Evidence to Check | Optimization Direction |
| --- | --- | --- |
| High CPU and compute-bound queries | CPU utilization, query plans, p99 | Optimize SQL/indexes first, then test machine sizing |
| Disk I/O and read latency | IOPS/throughput, cache hit, buffer misses | Index, query, and storage tuning/class per product |
| Locks/contention | Lock waits, slow transactions, deadlock logs | Shorten transactions, reduce hot rows, partition workload |
| Too many connections | Active/idle connections, max connections, DB memory | Pooling, concurrency limits, tuning idle timeouts |
| Analytical reads slowing writes | Read-vs-write latency, large scans, pool utilization | Read replicas/pool, columnar engine, or isolate analytics |
| Replica lag | Replication delay, stale reads, data consistency | Route consistency-sensitive queries back to primary |

### 6.2. Connection Pool Example from Cloud Run

Suppose Cloud Run can scale up to **50 instances**, and each instance maintains a pool of up to **20 connections**:

\[
50 \times 20 = 1,000\ \text{potential connections}
\]

If the DB only handles roughly **200 connections** stably under real workload, a pool of 20 per instance is too large. You must **shrink the pool**, use supported pooling/proxy capabilities, cap scale/concurrency, or distribute load, then re-measure throughput. Do not simply raise `max_connections`, as every connection consumes memory and can degrade performance.

**Total latency** includes connection wait time, query execution, network, serialization, and retries. A p99 benchmark should measure **end-to-end requests**, not just SQL execution time on an already-open connection.

### 6.3. AlloyDB Columnar Engine Is Not a Universal Speedup Button

The columnar engine helps when queries scan many rows, aggregate, and join supported columns. For simple primary-key lookups, the effect may be small or negligible. Enabling and sizing the column store memory also consumes resources; benchmark with **warm/cold caches, p95/p99, and total primary/read pool cost**.

Do not point a massive analytical dashboard at your OLTP primary just because AlloyDB has a columnar engine. If pipelines require large-scale BI/warehousing, evaluate streaming/exporting data to **BigQuery** to isolate failure domains and compute costs.

## 7. Total Cost of Ownership (TCO), Not Just VM Price

### 7.1. Line Items to Include in Your Estimate

| Line Item | Cloud SQL | AlloyDB | Self-managed |
| --- | --- | --- | --- |
| Compute | Machine/edition, primary, replica/HA | Primary + read pool instances | VM/GKE nodes and headroom |
| Storage | Disk, backups, logs, replication per config | Distributed storage, backups/logs | PD/Hyperdisk, snapshots, backup repository |
| Network | Egress, cross-region/zone per pricing | Private networking, cross-region, app traffic | LB/proxy, replication, egress |
| Licensing | SQL Server/edition if applicable | Per service pricing | SQL Server/commercial engine and support if applicable |
| DR | Cross-region replica, backups, restore tests | Secondary/replication, backup/restore | Secondary cluster, orchestration, replication tooling |
| Staffing | DBA for schema, queries, data ops | DBA and advanced tuning | DBA/SRE, patching, on-call, security |
| Risk | Managed limits, engine migration | Compatibility, cost/perf mismatch | Downtime from operational errors and missing runbooks |

**Management estimation formula:**

\[
TCO = C_{\text{infrastructure}} + C_{\text{data/network}} +
C_{\text{operations staffing}} + C_{\text{DR/testing}} +
C_{\text{outage risk}}
\]

With self-managed databases, a VM being cheaper than a managed service does not make the whole option cheaper: you must add **replicas, backups, patching, DR drills, on-call, licenses, and downtime risk**. Conversely, with managed services, the application team still invests effort in query/backup/security optimization, so operational cost is never zero.

### 7.2. Estimate Across Three Load Levels

Do not price a single idle-hour configuration and call it the annual cost. Model at least:

1. **Baseline:** DB size, CPU/RAM, storage capacity, and connection counts under normal load.
2. **Peak:** concurrent users/RPS, concurrent transactions, analytical load, and 12–24 month growth.
3. **Failure mode:** when a zone or replica fails, how much capacity remains and how much redundant capacity is required?

Compare figures across the **same region, storage class, backup retention, HA/DR scope, and support tier**. Pricing and editions can change; use the **Google Cloud Pricing Calculator** and official pricing pages at decision time.

## 8. Evaluation and Migration Process Without Guesswork

### 8.1. Seven Steps to Choose a Database

1. **Inventory:** engine/version, data size, tables/indexes, extensions, stored procedures, jobs, current connections, and dependent resources.
2. **Quantify:** TPS/QPS, read/write ratio, p95/p99, peak concurrency, DB size, growth, IOPS, replication lag, and connection limits.
3. **Lock requirements:** availability SLO, RTO/RPO, residency, encryption, auditing, budget, and team operational skills.
4. **Filter by compatibility:** for example, SQL Server cannot run directly on AlloyDB; an unsupported PostgreSQL extension may force another choice.
5. **Shortlist:** Cloud SQL with the right engine/edition, AlloyDB when PostgreSQL workloads warrant it, self-managed when deep control is essential.
6. **Run a proof of concept:** use representative datasets and queries, measure performance **and** failover/restore, plus total cost.
7. **Decide with an owner:** document rationale, trade-offs, rollback criteria, and review triggers when load changes.

Never use marketing TPS numbers from two products tested under different conditions to declare one faster. A valid test must use the **same data scale and SLO**, covering schema updates/migrations and connection drops.

### 8.2. Migration Requires Two Testing Tracks

| Technical Test | Questions to Prove |
| --- | --- |
| **Schema/data** | Are DDL, data types, encoding/collation, constraints, extensions, and stored procedures still valid? |
| **Application** | Do drivers, ORMs, query semantics, transaction isolation, timezones, and pagination behave identically? |
| **Performance** | Do query plans, index hits, throughput, p95/p99, database connections, and storage I/O meet peak demands? |
| **Reliability** | Do failover/restore meet real RTO/RPO, and do app reconnect/retry paths work safely? |
| **Security** | Do IAM, DB roles, networking, TLS, secrets, encryption, auditing, and residency meet requirements? |
| **Operations** | Are backups, PITR, alerting, database patching, rollback plans, and on-call staff ready? |

**Database Migration Service (DMS)** supports specific database migration paths, including eligible PostgreSQL/MySQL/SQL Server sources to supported destinations. **Do not assume every engine/version pair or extension is supported by DMS**; check the [official supported databases list](https://cloud.google.com/database-migration/docs/supported-databases) at migration time.

Controlled cutover workflow:

~~~mermaid
flowchart LR
    A["Inventory + compatibility tests"] --> B["Provision target DB<br/>with security/HA/backup"]
    B --> C["Load data / replicate<br/>via supported path"]
    C --> D["Compare schema, row counts,<br/>checksums, and lag"]
    D --> E["Lock cutover window,<br/>stop/coordinate writes"]
    E --> F["Switch connections<br/>and run smoke tests"]
    F --> G["Monitor SLO,<br/>keep rollback plan ready"]
~~~

For migrations using asynchronous replication, **near-zero lag does not automatically equal zero**. You must plan when to stop writes, reconcile transactions, and decide when cutover is safe. Once writes are permitted on the new DB, rolling back to the old DB may require **reverse replication or reconciliation**, not just reverting a connection string.

## 9. Hands-On Exercise: Evidence-Based Inventory and Decision

This lab **does not create billable databases**. If your project already has Cloud SQL/AlloyDB and you have read permissions, use commands to inspect configuration **without reading table data**; otherwise, use the sample scenarios in the exercise section. Do not run failover/restore tests or create production instances in this lab.

### 9.1. Read-Only gcloud Commands

~~~bash
# Only use a project, region, and instance approved by the resource owner
export PROJECT_ID="YOUR_APPROVED_PROJECT"
export REGION="asia-southeast1"
export SQL_INSTANCE="YOUR_EXISTING_CLOUD_SQL_INSTANCE"
export ALLOY_CLUSTER="YOUR_EXISTING_ALLOYDB_CLUSTER"

gcloud config set project "$PROJECT_ID"
gcloud config get-value project

# List and inspect Cloud SQL metadata without reading database contents
gcloud sql instances list --project="$PROJECT_ID"
gcloud sql instances describe "$SQL_INSTANCE" \
  --project="$PROJECT_ID" \
  --format="yaml(name,databaseVersion,region,settings.edition,settings.availabilityType,settings.tier,settings.backupConfiguration,replicaNames)"

# List AlloyDB clusters in the region
gcloud alloydb clusters list \
  --project="$PROJECT_ID" --region="$REGION"

# Only run this if the cluster exists and you have view permissions
gcloud alloydb instances list \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --cluster="$ALLOY_CLUSTER"
~~~

If a product has no instances in the project, or listing permissions are denied, **record "no data / permission denied"** rather than treating it as a reason to create new resources. Do not publish raw output containing network details or sensitive configuration into public reports.

### 9.2. Inventory Table to Complete

| Field | Current Cloud SQL | Candidate AlloyDB | Candidate Self-managed |
| --- | --- | --- | --- |
| Engine/version and extensions | Fill from inventory | Check compatibility | What level of control is needed? |
| Region/zone, network/TLS | Fill current config | Design connectivity | Design VPC/firewall/proxy |
| HA and RTO/RPO | Zonal or regional HA? | Primary HA + DR? | Replication/failover operator? |
| Backup/PITR, restore drill | Schedule and test results | Schedule and test results | Tools, schedule, on-call owner |
| CPU/RAM, TPS, p99 | Measured metrics | Benchmark | Benchmark |
| Read scaling and consistency | Replica/lag | Read pool/lag | Replicas and routing |
| IAM, DB roles, secrets | Verify | Verify | Verify |
| 1-year TCO, growth | Estimate | Estimate | VM + storage + SRE/DBA |
| Risks or blockers | List | List | List |

### 9.3. SQL Example Showing Why Benchmarking Matters

On an authorized **PostgreSQL lab database** with a test table, you can inspect **one SELECT** using `EXPLAIN (ANALYZE, BUFFERS)`:

~~~sql
-- FOR LAB DB ONLY: EXPLAIN ANALYZE actually executes the query.
EXPLAIN (ANALYZE, BUFFERS)
SELECT student_id, COUNT(*) AS enrollments
FROM lab_enrollments
WHERE created_at >= TIMESTAMP '2026-01-01 00:00:00'
GROUP BY student_id;
~~~

This is a **sample query** requiring a dedicated `lab_enrollments` table; do not run it on a large production table without an impact assessment. Compared to a small primary-key lookup, a `GROUP BY` query can consume significant CPU/buffers/I/O and benefit differently from indexes, caching, read pools, or the columnar engine.

**Measure the full workload**: one faster query does not prove a DB has higher transactional throughput, lower RTO, or lower TCO.

## 10. Scenario Exercises: Choosing Solutions Based on Requirements

### A — MySQL App for a Training Center

Current state: application uses **MySQL**, ~80 GiB of data, under 500 TPS at peak, no special engine features; team has two developers and no 24/7 on-call DBA. The customer wants single-zone failure resilience and the ability to restore after accidental data deletion.

**Prompt:** pick one of the three solutions, list features to enable, and specify at least three tests.

**Guidance:** Cloud SQL for MySQL is usually the primary candidate. Evaluate **regional HA**, automated backups/PITR, private connectivity, connection pools, and alerting. Drill **reconnecting after failover**, **restore/PITR in an isolated environment**, and **peak load testing**. Do not choose AlloyDB because AlloyDB is not MySQL; self-managed requires DBA/DR capabilities the team lacks.

### B — PostgreSQL with Very Read-Heavy Dashboards

Current state: 1.5 TiB of PostgreSQL data, OLTP API is stable, but concurrent scan/aggregate queries push p99 upward; the organization has budget for improvements and the team can execute benchmarks and cutover testing.

**Prompt:** should they migrate immediately to AlloyDB?

**Guidance:** **cannot conclude immediately**. First inspect query plans/indexes/locks, test optimizations, and evaluate **Cloud SQL Enterprise Plus/read replicas** if suitable. In parallel, benchmark **AlloyDB primary + read pool**, enabling the columnar engine in a controlled test for representative queries. Measure OLTP p99, analytics p99, replication freshness, compute/read pool cost, migration effort, and rollback capability. Migrate only when evidence confirms SLO/TCO fit.

### C — PostgreSQL Requiring a Custom Extension and OS Privileges

Current state: medical imaging software depends on a custom-compiled PostgreSQL extension and a separate OS library whose support is **unverified** on managed services; the data has strict residency and audit regulations.

**Prompt:** preliminary decision and conditions for approval.

**Guidance:** first check whether the extension can be replaced/packaged or is officially supported on Cloud SQL/AlloyDB. If requirements cannot be met, **self-managed on VMs or GKE** is the technical candidate, but should be approved only with DBA/SRE staffing, HA/backup/restore, patching, access controls, auditing, networking, legal/compliance review, and DR drills in place. **Do not** use real production data for a PoC without authorization.

### D — Product Requires RPO = 0 Even on Region Loss

Business requirement: even if an entire region fails, zero committed transactions may be lost; the system must continue accepting writes in another region.

**Question:** is choosing Cloud SQL regional HA, AlloyDB HA primary, or 2-zone self-managed enough?

**Answer:** **not enough**. Those mechanisms primarily protect within a single region, while cross-region replication may be asynchronous and carry a non-zero RPO. You must clarify the strength of the commitment, cross-region data consistency strategy, synchronous/quorum options if supported, latency/cost impacts, and feasibility. You may need to **re-evaluate the service or data architecture** beyond the three options in this lesson rather than promising RPO=0 without foundation.

### E — Three Cloud Run APIs Exhausting Cloud SQL Connections

Three services connect to one Cloud SQL PostgreSQL instance. Each service scales up to 40 instances, and each instance holds a pool of 15 connections. The DB is measured to run safely at around 300 total connections.

**Calculation:**

\[
3 \times 40 \times 15 = 1,800\ \text{potential connections}
\]

**Prompt:** propose a low-risk remediation approach.

**Guidance:** reduce pool size per workload, configure concurrency/scale caps, apply appropriate pooling or connection management, inspect idle connections, and profile SQL. Re-measure at peak. Do not simply bump `max_connections` to 1,800 or migrate to AlloyDB assuming the problem will disappear.

### Fillable Decision Matrix Template

| Criterion | Org-Chosen Weight | Cloud SQL | AlloyDB | Self-managed |
| --- | --- | --- | --- | --- |
| Engine and compatibility | Mandatory / Eliminating | Pass/Fail | Pass/Fail | Pass/Fail |
| RTO/RPO and HA/DR | High | Test evidence | Test evidence | Test evidence |
| p99 and throughput by workload | High | Benchmark | Benchmark | Benchmark |
| Governance and security | High | Review | Review | Review |
| 1–3 year TCO | Per budget | Estimate | Estimate | Estimate |
| Staffing skills / on-call | Per organization | Sufficient/Gaps | Sufficient/Gaps | Sufficient/Gaps |
| Migration and rollback capability | Per risk level | Plan | Plan | Plan |

**Never score a candidate that Failed a mandatory requirement** just because it is cheap or fast in benchmarks. If none meet RTO/RPO, the right outcome is **no candidate meets requirements yet**.

## 11. Self-Check Questions

**1. Which engines does Cloud SQL support?**  
PostgreSQL, MySQL, and Microsoft SQL Server; supported features/editions/versions vary by engine.

**2. Can AlloyDB run a SQL Server application directly without changing the engine?**  
No; AlloyDB is a PostgreSQL-compatible service.

**3. Does a Cloud SQL read replica automatically replace the primary on zone failure?**  
Not automatically like an HA standby; the primary needs regional HA or an appropriate DR/promotion plan.

**4. Does an AlloyDB read pool accept writes like the primary?**  
No; read pools serve read queries, and applications must route connections appropriately.

**5. Does choosing Cloud SQL regional HA mean you have DR for a full-region outage?**  
No; you still need cross-region planning, backups, recovery procedures, and testing.

**6. Does Cloud SQL Auth Proxy create a private IP network path for the client?**  
No; the client still needs proper network connectivity to the VPC/private endpoint.

**7. Does a managed database eliminate query and schema management?**  
No; developers/DBAs still manage schemas, indexes, transactions, pools, roles, and data integrity.

**8. Why must backups be restore-tested?**  
Because the existence of a backup does not prove you can restore valid data within the committed RTO/RPO.

**9. Why shouldn't you compare only VM price against AlloyDB price?**  
Because TCO also includes HA/replicas, backups, licensing, operations, on-call, downtime risk, and networking.

**10. What should you do when PostgreSQL needs an unsupported extension?**  
Evaluate alternatives or migration paths first; if self-managed is necessary, prove sufficient operational and security capability.

**11. Do three database Pods on GKE automatically guarantee consistency/HA?**  
No; you need tested replication, leader election, fencing, storage topology, and runbooks.

**12. Is a read-after-write on a read replica guaranteed to see the latest data?**  
No; replica lag can cause stale reads, so you must design appropriate read consistency.

## 12. Google Cloud Reference Documentation

- [Cloud SQL overview](https://cloud.google.com/sql/docs/introduction) — engine support, managed components, and deployment options.
- [Cloud SQL PostgreSQL — Choose an edition](https://cloud.google.com/sql/docs/postgres/choose-edition) — Enterprise vs. Enterprise Plus comparison, defaults, and features.
- [Cloud SQL MySQL — Choose an edition](https://cloud.google.com/sql/docs/mysql/choose-edition) — choosing an edition by version/workload.
- [Cloud SQL SQL Server — Choose an edition](https://cloud.google.com/sql/docs/sqlserver/choose-edition) — editions, SQL Server versions, and limits.
- [Cloud SQL high availability](https://cloud.google.com/sql/docs/postgres/high-availability) — zonal, regional, failover, downtime, and read replicas.
- [Cloud SQL read replicas](https://cloud.google.com/sql/docs/postgres/replication) — read scaling, lag, and automatic failover limitations.
- [Cloud SQL disaster recovery](https://cloud.google.com/sql/docs/postgres/intro-to-cloud-sql-disaster-recovery) — recovery from a full-region outage.
- [Cloud SQL connection options](https://cloud.google.com/sql/docs/postgres/connection-options) — public/private IP, connectors, and database authentication.
- [Cloud SQL Auth Proxy](https://cloud.google.com/sql/docs/postgres/connect-auth-proxy) — secure channel and network path requirements for private IP.
- [AlloyDB overview](https://cloud.google.com/alloydb/docs/overview) — separated compute/storage, primary, read pools, and HA.
- [AlloyDB columnar engine](https://cloud.google.com/alloydb/docs/columnar-engine/about) — accelerating certain analytical queries.
- [AlloyDB sizing recommendations](https://cloud.google.com/alloydb/docs/use-sizing-recommendations) — sizing primary/read pools and benchmarking.
- [Database Migration Service — Supported databases](https://cloud.google.com/database-migration/docs/supported-databases) — verifying supported migration paths, engines, and versions.
- [Cloud SQL pricing](https://cloud.google.com/sql/pricing), [AlloyDB pricing](https://cloud.google.com/alloydb/pricing), [Compute Engine pricing](https://cloud.google.com/compute/all-pricing) — estimating TCO at decision time.

**Conclusion:** choose **Cloud SQL** when you need a mainstream relational engine and want to reduce infrastructure toil; evaluate **AlloyDB** when you already use PostgreSQL and have performance/availability demands justified by benchmarks and cost; choose **self-managed** when managed services cannot meet technical constraints or control requirements and your team truly has the operational capability. A decision is complete only when backed by **compatibility evidence, SLO/RTO/RPO, recovery tests, a security/migration plan, and a TCO estimate** — not just a product name.
