# Choosing Self-Managed vs. Managed Service Based on Operational Requirements

After modeling nodes, relationships, constraints, and Cypher queries, a Neo4j development team must answer an operational question: **run Neo4j on your own infrastructure or use a managed Neo4j service?** Both can serve Java Driver and Spring Data Neo4j applications, but the level of control, maintenance responsibility, cost, and mechanisms for ensuring availability differ significantly.

This lesson belongs to the **Deployment** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. The module focuses on the Neo4j property graph, relationships and paths with Cypher, indexes/constraints, query optimization, data import, Java Driver, Spring Data Neo4j, and graph operations. This lesson presents a **decision framework** for choosing a deployment model based on actual requirements, without assuming "cloud is always better" or "self-managed is always cheaper."

> **Scope:** Self-managed Neo4j can run on virtual machines, bare metal, Docker, or Kubernetes. A typical example of a managed service is **Neo4j AuraDB**. Features, deployment regions, SLAs, backup/restore, resource limits, network permissions, plugins, GDS support, and service pricing **vary by tier and over time**. Every production decision must be verified against the contract, documentation, and features of the specific tier under consideration; tables in this lesson illustrate general responsibilities and trends, not feature promises for every tier.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish the **self-managed** model from **managed Neo4j** and explain the shared responsibility model.
2. Gather requirements for **SLO, RPO, RTO, data, security, networking, plugins, and budget** before choosing a deployment option.
3. Compare total cost of ownership (**TCO**) and risk cost, rather than just comparing server price with service subscription price.
4. Identify important differences affecting Cypher, APOC, Graph Data Science, Java Driver, and Spring Data Neo4j.
5. Diagram a minimal self-managed deployment and a connection to a managed service.
6. Build a pilot checklist, migration plan, cutover, rollback, and post-migration verification.

## 2. What Do the Two Deployment Models Mean?

### 2.1. Self-managed Neo4j

The team owns or rents infrastructure, then **deploys and manages** the Neo4j process themselves. Infrastructure may be:

- Physical servers in the organization's data center.
- Virtual machines or instances on a cloud provider.
- Docker containers for packaging and standardizing environments.
- Kubernetes with an appropriate operator/chart and operational procedures.

Operators must handle server configuration, TLS, Bolt connectivity, disk storage, version upgrades, backup/restore, monitoring, resource tuning, and if **high availability (HA)** is needed, also design multiple members, routing, and failover procedures according to the licensed Neo4j edition/version.

Self-managed **does not mean** buying physical hardware: you can self-manage Neo4j on cloud virtual machines. In that case, the cloud provider manages the underlying hardware, while **your team manages the database**.

### 2.2. Managed Neo4j (Managed Service)

A service like **Neo4j AuraDB** provides a DBMS/instance operated by the vendor at the service infrastructure level. Users primarily create instances, manage configurations exposed by the product, connect, define schemas, import data, write Cypher, and operate applications.

The provider handles many tasks such as platform deployment, partial upgrades/monitoring, resource provisioning, and backup/availability mechanisms **according to the product tier**. The application team is **still** responsible for:

- Data modeling, constraints/indexes, and Cypher correctness.
- Application accounts, credentials, authorization, and data policies within the granted scope.
- Java Driver/SDN integration, connection configuration, retries, and idempotency.
- Workload, slow queries, data volume, costs, and upgrade timing.
- Ensuring business requirements for data, backup/recovery, and DR are actually met by the chosen tier.

**Managed does not mean "no DBA/data architect needed"**: the provider keeping the server stable does not automatically fix row-exploding `MATCH` queries, missing indexes, or flawed relationship models.

## 3. Responsibility Diagram

~~~mermaid
flowchart LR
    subgraph S["Self-managed"]
      A["Application team:<br/>Cypher, schema, data"] --> B["Operations team:<br/>DBMS, backup, patching, HA"]
      B --> C["Infrastructure:<br/>VM / Docker / Kubernetes / servers"]
    end
    subgraph M["Managed service"]
      D["Application team:<br/>Cypher, schema, data"] --> E["Provider:<br/>DB platform per tier/SLA"]
      E --> F["Provider infrastructure"]
    end
~~~

| Task | Self-managed | Managed |
|---|---|---|
| Graph design, Cypher, indexes/constraints | Application/data team | Application/data team |
| Java Driver configuration, connection pool, timeouts | Application team | Application team |
| Installing DBMS, host configuration, OS patching | Infrastructure/DBA team | Largely handled by provider within service scope |
| Database replication/HA configuration | Self-designed and operated per edition | Capabilities defined by service tier; verify SLA |
| Backup schedule, storage, restore testing | Self-implemented and owned | Provider supplies features per tier; customer team must verify RPO/RTO and recoverability |
| Certificates, network perimeter, private connectivity | Self-managed DB/network | Shared based on tier network capabilities and application design |
| Query tuning, bad data, application permissions | Application/DBA team | Still customer responsibility |
| Observability and application incident handling | Application/DBA team | Customer; provider supports service-side components per tier |
| License renewal, custom plugin maintenance | Per contract and deployment | Tier-dependent; arbitrary JAR installation is usually not allowed |
| Billing reconciliation, budget, and growth | Customer | Customer |

Each row in the table represents a **responsibility model**, not an SLA commitment. For example, one Aura tier may provide different backup/restore and support options than another; the customer team must still verify specific recovery requirements before signing a contract.

## 4. Start from Requirements Instead of Product Names

You should not start with "Should we use Kubernetes or Aura?" but instead write a **verifiable requirements table**.

| Requirement Dimension | Quantitative / Verification Question | Hypothetical Example |
|---|---|---|
| Load | Queries/sec, % read/write, returned data volume, largest fan-out? | 300 requests/sec, 80% read |
| Latency | What is the target p95/p99 for the API or DB? | API p95 ≤ 200 ms |
| Data | Number of nodes, relationships, properties, growth rate? | 15M nodes, 70M relationships |
| Availability | Acceptable downtime per period? | 99.9%/month SLO |
| Recovery | How much data loss is acceptable? How fast must it recover? | 15-minute RPO, 1-hour RTO |
| Data residency | Can data be placed outside a specific jurisdiction? | Only one specific region allowed |
| Network | Are private endpoints, peering, or restricted outbound egress needed? | Private routing only |
| Security | Which RBAC roles, audit, encryption, key management are mandatory? | Fine-grained access, audit |
| Extensibility | Are custom plugins, APOC Extended, GDS, or CDC used? | One custom Java procedure |
| Operations | Is there a 24/7 on-call team and restore/cluster capability? | Only one part-time SRE |
| Cost | What is the annual budget and non-DB cost? | Quarterly TCO cap |

The numbers in the last column are **examples to learn how to write requirements**, not guaranteed Neo4j thresholds. In particular, application SLO and provider SLA are **not identical**: an API can fail due to the application or network even when the database remains available.

### Distinguishing "Must-Have" and "Nice-to-Have" Requirements

- **Mandatory requirements (hard constraints):** compliant data region, private networking, indispensable Java plugins with no replacement, contractual RPO/RTO.
- **Optimization goals (nice-to-have):** reducing on-call hours, lower latency, cost savings, fast provisioning, resource scaling flexibility.

If an option **fails a mandatory requirement**, do not choose it simply because of a higher total score or lower price.

## 5. Key Comparison Dimensions

### 5.1. Infrastructure and Configuration Control

**Self-managed** is suitable when deep customization of the OS, JVM, cluster topology, disk policies, upgrade schedules, network policies, or observability agents is needed. In return, untested configuration changes can impact data integrity and availability.

**Managed** has a limited configuration surface but reduces the number of platform operational decisions. You must accept the corresponding constraints: maintenance windows, capacity scaling methods, supported Neo4j versions, or inability to install arbitrary modules.

### 5.2. Time to Start and Staffing

- Rapid prototyping projects with few operations staff often benefit from **managed** if feature limits and data regions are compatible.
- Organizations with mature DBA/SRE teams, existing clusters, automation, and multi-layered control requirements may choose **self-managed**.
- A container running in five minutes **does not mean you have a production system** with backups, HA, security, logging, and incident drills.

### 5.3. Plugin and Algorithm Flexibility

A pure Cypher codebase is easier to move between environments than a system dependent on custom procedures. If the workload uses:

- **APOC Core:** check the supported function/procedure list and execution policy on the managed tier.
- **APOC Extended / custom Java procedures:** typically require direct plugin installation privileges, so deployment feasibility must be investigated before choosing managed.
- **Neo4j Graph Data Science (GDS):** distinguish GDS availability, versions, in-memory projections, graph size, and licensing from the **AuraDB database**. Availability may differ by product/tier.
- **Special import/export:** importing CSV from `file:///...`, reading files in `import`, or running `neo4j-admin` commands on the host may not exist in the same way in managed environments. You must design a service-supported ingestion path (API, URL, import workflow, driver).

**Do not conclude "having APOC" is enough.** Some projects only need `apoc.convert.fromJsonMap`; others need an Extended procedure or file operations. You must verify **specific procedure names** on the target environment.

### 5.4. Limits, Upgrades, and Lock-in

When running self-managed, the operations team controls many version/deployment details, but must **plan upgrades, migrations, failbacks, and security patches themselves**. With managed, upgrade policies and compatibility follow the product; this can reduce maintenance work but requires tracking deprecation/change notices.

Lock-in factors are not limited to the hosting service. A project may depend on:

- Queries using Cypher features available only in a specific Neo4j version.
- APOC/GDS/custom plugin procedures.
- Proprietary import, snapshot, or integration methods.
- Network topology, IAM, backup scripts, or monitoring tools.

Using the Java Driver over the Bolt protocol keeps application code close to Neo4j, but **does not automatically guarantee compatibility of data, procedures, or network topology** when switching environments.

## 6. HA, Backup, and Disaster Recovery (DR) Are Not the Same Thing

Three commonly confused concepts:

| Concept | Goal | What can it NOT solve alone? |
|---|---|---|
| **High availability (HA)** | Service continues or quickly resumes when a member/zone fails | Does not replace backups if data suffers logical deletion, corruption, or ransomware |
| **Backup/restore** | Having a data copy to recover after loss or human error | Does not automatically guarantee a short enough recovery time |
| **Disaster recovery (DR)** | Restoring business operations after a severe region/system outage | Ineffective without regular drills and verified procedures |

**RPO (Recovery Point Objective)** is the maximum acceptable data loss, typically measured in time. **RTO (Recovery Time Objective)** is the target duration to restore service.

Hypothetical example: a business wants **RPO ≤ 15 minutes**, **RTO ≤ 60 minutes**. You cannot assume both targets will be met just because a tier advertises "automated backups" or a cluster has three machines.

### 6.1. When Self-Managing

At minimum, you need:

1. **Failure domain model:** which servers, disks, availability zones, networks, and regions can fail together?
2. **Edition/cluster topology supporting HA:** do not assume a single container or a makeshift replica provides enterprise cluster capabilities.
3. **Verified backups:** full/incremental types supported by the Neo4j edition, schedule, encryption, isolated storage, and retention.
4. **Restore drills:** periodically restore into a clean environment and measure duration, rather than only checking "backup file exists."
5. **Replication/failover monitoring:** alerts when a member loses connectivity, write routing fails, target data lags, or backups fail.
6. **Runbook with an owner:** who diagnoses, who approves failover/restore, when to stop writes, and how to reconcile after recovery.

Backup/restore strategies for a **standalone** instance and a **cluster** can differ. Do not copy backup commands, ports, or directories from old documentation to a new Neo4j version without checking version/edition.

### 6.2. When Using Managed

Verify in the **specific tier**, via documentation/contract:

- Are backups created automatically? What are the frequency, retention period, and restore points?
- Is restore self-service or does it require a support request? Can you restore to **another instance** for testing?
- Is multi-zone/multi-region protection included? What is the procedure if an entire region fails?
- Are RPO and RTO **committed** or merely **best-effort** features?
- Is there an availability SLA? What are the calculation terms, exclusions, and support level?
- When an application bug accidentally deletes nodes/relationships, can you perform **selective** recovery or is data reconciliation needed?

The provider may operate the HA mechanism, but the application team must still ensure **idempotent transactions, retries, and leader/connection re-selection** at the Java Driver layer.

### 6.3. Evidence Table to Collect

| Requirement | Evidence |
|---|---|
| "Has backups" | Policy, actual schedule, latest copy, success/failure logs |
| "Meets 15-minute RPO" | Verified data gap measured after a test restore |
| "Meets 60-minute RTO" | Drill report from incident detection until application operates |
| "Has HA" | Topology, results from stopping one member, impact on reads/writes |
| "Has backup failure monitoring" | Dashboard, alerts, designated owner receiving and acting |
| "Restores data accurately" | Checksum/key-set comparison, constraints, node/relationship counts |

**Do not infer 99.9% API uptime from 99.9% DBMS uptime** when the API also depends on network connectivity, application code, authentication systems, and external services.

## 7. Security, Permissions, and Data Placement

### 7.1. Neo4j Access Privileges

Java Driver and Spring Data Neo4j applications need accounts with **least privilege**. A service reading `:Customer` and `:Order` does not need admin or schema modification privileges. Granular RBAC capabilities depend on the Neo4j edition/tier.

With self-managed, the operations team is responsible for implementing authentication/authorization, role assignment, transport encryption, and secret protection. With managed, the platform provides a set of administrative capabilities per tier, but **the customer must still create and manage appropriate identities**, separate runtime privileges from schema migrations, and verify actual query paths.

### 7.2. TLS and Networking

Before choosing an option, draw the connection flow:

~~~mermaid
flowchart LR
    APP["Java app / Spring Boot"] -->|"Bolt + TLS"| ENDPOINT["Neo4j endpoint"]
    ENDPOINT --> DB["Database"]
    SEC["Firewall / private networking / DNS"] -.-> ENDPOINT
    AUTH["Secrets / IAM / RBAC"] -.-> APP
~~~

- **Self-managed:** self-manage firewalls, public/private subnets, load balancer/cluster routing, DNS, TLS certificates, network egress, and secret lifecycles.
- **Managed:** verify whether the product/tier supports private endpoints, peering, IP allowlists, specific regions, and required authentication types.
- **Both:** avoid exposing Bolt ports to the public Internet unless necessary, use TLS with server identity verification, avoid hard-coding passwords, rotate credentials, and log carefully.

Do not use unencrypted `bolt://` over untrusted networks. For an endpoint with a valid certificate, `neo4j+s://` or `bolt+s://` schemes may be appropriate depending on routing/topology; choose based on the service/cluster recommendation. **Do not** disable TLS verification just to make a connection test pass.

### 7.3. Data Residency and Compliance

Some organizations require data, backup copies, logs, and data processing locations to stay within defined legal jurisdictions. "Database runs in region X" **does not automatically prove** that logs, support data, backups, or all data flows remain solely in region X.

Checklist to ask:

1. Which regions are actually offered in the **target service tier**?
2. How are primary data, backups, logs, and support data stored/transferred?
3. Are network isolation, customer-managed encryption keys, audit logs, or retention periods required?
4. Do data deletion, recovery, export, and offboarding mechanisms meet internal policies?
5. Who is responsible for fulfilling customer/user data subject requests?

If those conditions cannot be met, a managed option may be unsuitable despite simple deployment; conversely, self-managed **does not automatically achieve compliance** if the operations team lacks controls and audit evidence.

## 8. Calculating Total Cost of Ownership (TCO)

Comparing **VM price** with **a managed instance price** is an incomplete comparison. TCO must include labor, outage risk, backups, monitoring, networking, upgrades, and licensing.

### 8.1. Conceptual Formula

~~~text
TCO self-managed / period
  = compute + storage + network + license/support
  + backup/DR + monitoring/security tooling
  + DBA/SRE time + upgrade/incident cost
  + expected risk cost

TCO managed / period
  = subscription/usage + storage/compute tier
  + network/egress/private connectivity
  + support/add-ons + application and data engineering
  + migration cost + expected risk cost
~~~

This is a **cost-item framework**, not a Neo4j pricing formula. Some items are already included in managed pricing; avoid **double counting**. Similarly, self-managed deployments may incur different Enterprise license/support or cloud infrastructure costs.

### 8.2. Cost Across Growth Cycles

When 10 million nodes grow to 100 million nodes, relationship counts and property sizes may grow at different rates. You must forecast:

- Disk + transaction logs + backup retention.
- Page cache, heap, and memory overhead for queries/algorithms.
- CPU for scans, path expansions, sorting, `MERGE`, and imports.
- Network egress between application and database, especially cross-region.
- Downtime cost when running out of storage or hitting query timeouts.
- Tier upgrade or cluster expansion costs.

**Self-managed can save money** at large scale when a team already has infrastructure; **managed can save money** when operational hours and incident risk are major components. No single cost direction holds true for every workload.

### 8.3. Forecast via Measurement Instead of Guessing

Instead of sizing hardware solely by node count:

1. Generate a **representative** dataset, including relationship-to-node ratios.
2. Run real queries from the Java/SDN application.
3. Measure p50/p95/p99, queries/s, transaction rollbacks, CPU, memory, page cache, and connection acquisition latency.
4. Test imports, index builds, snapshots/restores, and peak loads.
5. Measure across comparable configurations for the options under evaluation, using identical queries and parameters.

A query with unbounded path length or missing indexes can invalidate any cost forecast based on node count.

## 9. Decision Matrix and Prioritization

Use the table below as a **discussion starting point**, not a mechanical formula.

| Criterion | Usually favors self-managed | Usually favors managed |
|---|---|---|
| OS, JVM, and infrastructure customization | Needs deep control | No platform-level intervention needed |
| Custom Java procedures / unsupported plugins | Mandatory requirement | Not needed or alternatives exist |
| On-call staffing and DBA/SRE processes | Mature team and automation | Small team wanting to reduce platform ops |
| Special region/network | Dedicated infrastructure fits better | Tier provides exact region/private connectivity |
| HA/backup | Team has design, drills, and monitoring | Tier provides mechanisms and terms meeting RPO/RTO |
| Upgrade schedule | Must actively control every phase | Accepts service-defined cycle/windows |
| Speed to provision new environments | Existing infrastructure automation | Prioritizes fast deployment and minimal ops |
| Internal observability | Needs host-level access and custom agents | Service dashboards/metrics/APIs suffice |
| Cost predictability | Existing infra, steady load, strong ops team | Wants to bundle platform costs into a service |

### Controlled Scoring Method

Before scoring, **eliminate options that fail mandatory requirements**. Then for each remaining criterion:

~~~text
score(option) = SUM(weight_i * fit(option, criterion_i))

weight_i: relative importance (e.g., total = 100)
fit: suitability rating (e.g., 1 to 5)
~~~

Example evaluation table **filled in by a team**:

| Criterion | Weight | Self-managed (1–5) | Managed (1–5) |
|---|---:|---:|---:|
| Reduce operational on-call hours | 25 | 2 | 5 |
| Mandatory plugin customization | 25 | 5 | 1 |
| Ensure recovery plan | 20 | 3 | 4 |
| Network and region fit | 20 | 4 | 4 |
| Deployment speed | 10 | 3 | 5 |

With the **hypothetical scores** above:

~~~text
Self-managed = 25*2 + 25*5 + 20*3 + 20*4 + 10*3 = 345 / 100 = 3.45
Managed      = 25*5 + 25*1 + 20*4 + 20*4 + 10*5 = 360 / 100 = 3.60
~~~

Managed has a slightly higher total score, but **if a custom plugin is a mandatory requirement and unsupported by the service**, the managed option must still be eliminated. Scoring clarifies trade-offs; it does not replace hard-requirement checks.

## 10. A Minimal Self-Managed Deployment for Learning

Example of a **standalone Neo4j Docker Compose** setup for running local exercises, **not a production HA configuration**:

~~~yaml
services:
  neo4j:
    image: neo4j:5.26
    environment:
      NEO4J_AUTH: "neo4j/${NEO4J_PASSWORD}"
    ports:
      - "127.0.0.1:7474:7474"
      - "127.0.0.1:7687:7687"
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs

volumes:
  neo4j_data:
  neo4j_logs:
~~~

The `NEO4J_PASSWORD` environment variable is loaded from the local environment (or an appropriate secret manager); **do not commit real passwords to Git**. This Compose file only illustrates:

- `7474`: HTTP (Neo4j Browser/UI when enabled).
- `7687`: Bolt for Java Driver.
- `127.0.0.1`: binds ports only to host loopback, avoiding direct Internet exposure.
- Data volumes prevent container stop/restart from automatically losing volume data.

**However, a volume is not a backup.** Volume loss, logical errors, corruption, or deletion still require an independent backup/restore process.

### What Must Be Added Before Production

1. Decide edition/license and standalone/cluster architecture per SLO.
2. Storage class, disk throughput, durability, and capacity forecasting.
3. TLS, firewall, DNS, users/roles, and secret rotation.
4. Restore-drilled backups with off-primary retention.
5. Metrics/logs/alerts, infrastructure health aggregation, and query latency tracking.
6. Upgrade windows, version pinning, and rollback verification.
7. Empirically measured resource limits, heap, page cache, query timeouts, and connection pooling.
8. Zone/host failure plan, disk exhaustion alerts, and incident on-call rotation.

Do not confuse **"the container is running"** with **"the service meets production RPO/RTO and SLA."**

## 11. Connecting to a Managed Service from Java Driver

With AuraDB or a Neo4j endpoint supporting TLS/routing, a Java Driver application usually only needs changes to **URI, credentials, target database, and connection policy** without rewriting every query.

Java 17+ example with a supported Neo4j Java Driver version:

~~~java
import java.util.Map;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class OrderLookup {
    private OrderLookup() {}

    public static void main(String[] args) {
        // Example for AuraDB service:
        // NEO4J_URI=neo4j+s://<instance-id>.databases.neo4j.io
        String uri = System.getenv("NEO4J_URI");
        String user = System.getenv("NEO4J_USERNAME");
        String password = System.getenv("NEO4J_PASSWORD");
        String database = System.getenv().getOrDefault("NEO4J_DATABASE", "neo4j");

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(user, password))) {
            driver.verifyConnectivity();

            try (Session session = driver.session(
                    SessionConfig.forDatabase(database))) {
                var result = session.executeRead(tx -> tx.run("""
                        MATCH (o:Order {orderId: $orderId})
                        RETURN o.orderId AS orderId,
                               o.amount AS amount
                        """, Map.of("orderId", "O01")).single());

                System.out.println("orderId=" + result.get("orderId").asString());
                System.out.println("amount=" + result.get("amount").asLong());
            }
        }
    }
}
~~~

**Explanation:**

- `NEO4J_URI` and credentials must come from **secret/config management**, not hard-coded in source or container images.
- For AuraDB, `neo4j+s://` is a common example for secure connections; confirm the **exact URI** provided by the instance.
- Specify the database name explicitly rather than relying entirely on defaults when operating multiple DBs/instances.
- `verifyConnectivity()` indicates basic connectivity and authentication are ready, **not** that the user has read permission across the whole graph or that queries are fast enough.
- `executeRead(...)` manages read transactions and retries per driver policy; if the same request calls multiple systems, you still need timeout and tracing management.
- In a real server application, reuse a long-lived **Driver** (typically a singleton bean) and open/close a **Session** per operation; do not create a new Driver for each HTTP request.

With a self-managed cluster, the URI can also use the appropriate routing scheme. Do not replace every URI with `bolt://localhost:7687` when moving to a cluster: the driver must discover advertised routing addresses and have network reachability to them.

### Spring Data Neo4j

Spring Boot configuration can be separated per environment:

~~~yaml
spring:
  neo4j:
    uri: "${NEO4J_URI}"
    authentication:
      username: "${NEO4J_USERNAME}"
      password: "${NEO4J_PASSWORD}"
  data:
    neo4j:
      database: "${NEO4J_DATABASE:neo4j}"
~~~

After switching endpoints, **do not only verify that "Spring context starts up."** Run real integration tests to verify repository derived queries, `@Query`, relationship mapping, transaction rollback, uniqueness constraints, and any parts using APOC/GDS.

## 12. Are Queries and the Data Model Truly Portable?

An empty new database with the same Neo4j version is **not enough** for the application to work properly. You must verify:

| Component | Must Verify |
|---|---|
| Nodes/relationships | Correct labels, relationship types, edge directions, and properties |
| Identifiers | Business-key uniqueness; do not rely on `elementId()` as a migration key |
| Schema | Range indexes, text/full-text/vector indexes, constraints, `ONLINE` status |
| Cypher | Exact language/version support, query semantics, procedures |
| Special data types | Date/time, point, list, integer/float, and null/missing values |
| APOC/GDS | Exact functions/procedures, versions, and execution privileges |
| Import pipeline | Source URLs/files/`LOAD CSV` and paths visible from the server |
| Java Driver/SDN | Driver compatibility, entity mapping, transaction semantics |
| Search/algorithms | Execution plans, required indexes, graph projections, and required memory |
| Security | Users/roles/privileges, TLS, secrets, and network policies |

Example Cypher counts by key and relationship:

~~~cypher
MATCH (c:Customer)
RETURN count(c) AS customers,
       count(DISTINCT c.customerId) AS distinctCustomerIds;
~~~

~~~cypher
MATCH (o:Order)
RETURN count(o) AS orders,
       coalesce(sum(o.amount), 0) AS totalAmount;
~~~

~~~cypher
MATCH (:Customer)-[r:PLACED]->(:Order)
RETURN count(r) AS placedRelationships;
~~~

Counts alone are **not enough** to prove two graphs are identical: both could have 1 million relationships yet connect the wrong node pairs. You should verify checksums/key sets, critical relationship patterns, and representative business queries.

## 13. Step-by-Step Migration Plan

Migrating between self-managed and managed is a **data system migration project**, not just changing a connection string.

~~~mermaid
flowchart TD
    A["Gather requirements and baseline"] --> B["Check compatibility<br/>version, plugins, network"]
    B --> C["Prepare target instance<br/>schema, privileges, secrets"]
    C --> D["Initial data load"]
    D --> E["Reconcile nodes, edges, properties"]
    E --> F["Run integration/load/restore tests"]
    F --> G{"Meet cutover criteria?"}
    G -->|No| H["Fix and retest"]
    H --> E
    G -->|Yes| I["Freeze write source, sync delta,<br/>switch endpoint"]
    I --> J["Monitor SLOs and reconcile"]
    J --> K["Stabilize, close rollback plan"]
~~~

### Step 1 — Capture Baseline

Record Neo4j version, edition, graph size, schema, update frequency, critical queries, and p95/p99 latency. Document criteria that **must be preserved**: node/relationship counts by key, zero lost business orders, RPO/RTO, and access privileges.

### Step 2 — Check Compatibility and Privileges

Do not choose the target option if:

- There is a custom Java procedure that cannot be installed and has no replacement.
- Backup/export processes fail to satisfy data retention regulations.
- The current private network cannot connect to it.
- Cypher/enterprise capabilities required by the workload are unsupported by the target tier.

### Step 3 — Prepare Database and Schema

Create the target database, credentials, and network rules, then deploy appropriate indexes/constraints. For large datasets, the order of import vs. index building can affect duration; however, upserts using `MERGE` by key usually require indexes/constraints beforehand.

### Step 4 — Load and Synchronize Data

Choose a mechanism suitable for the environment: supported backup/restore tools, export/import, `LOAD CSV`, application batching via Java Driver, or a CDC/streaming sync mechanism if part of the design. **Do not assume every tool or backup file from self-managed can be restored directly into every AuraDB tier.**

If the source continues receiving writes during the background import, you must have a way to apply **deltas** or schedule a deliberate **write freeze** window. Otherwise, the target snapshot may miss records updated after the copy began.

### Step 5 — Reconcile Data Accuracy and Behavior

Compare node counts, relationship counts, identifier keys, critical properties, aggregate metrics, and path queries. Run tests with **realistic parameter sets**, especially on graphs with one-to-many relationships, to detect row multiplication.

### Step 6 — Measure Load and Failover

Run load tests on the target database using a representative workload and appropriate resource limits; measure p95/p99, queries/s, rollbacks, deadlocks, connection pool wait, and cost. For HA/backups, obtain recovery evidence or matching SLAs instead of assuming "moved to cloud so it's safe."

### Step 7 — Cutover and Rollback

At cutover time:

1. Lock in the timing, change scope, and responsible owner.
2. Pause writes or trigger the final sync per design.
3. Run delta data checks, schema checks, and read/write smoke tests.
4. Switch `NEO4J_URI`/secrets/database via controlled deployment.
5. Monitor connection errors, p95/p99, query failures, and new business event counts.
6. Keep a clear rollback/failback plan: **reverting to the old source is unsafe if new writes exist only on the target**. You must have a policy to replay/reconcile data before failing back.

Rollback is a **data scenario**, not merely restoring a URI config.

## 14. Post-Deployment Operations: Minimal Dashboard

For both models, you need signals from **both the application and the database**:

| Signal | Source | Meaning |
|---|---|---|
| API p50/p95/p99 and error ratio | Micrometer/OpenTelemetry/application logs | Actual user experience quality |
| Query latency and failure rate | Environment-supported Neo4j metrics/logs | Slow or failing queries |
| Transaction commits/rollbacks | Neo4j metrics | Load, failures, and retries |
| Lock contention / waiting transactions | `SHOW TRANSACTIONS` or supported metrics | Long-held locks, hot nodes |
| Bolt connections / driver pool wait | Neo4j + Java instrumentation | Connection/routing bottlenecks |
| CPU, memory, page cache, disk | Self-managed infra or managed-provided metrics | Resource health |
| Backup/restore status | Backup system or managed service | Recoverability |
| Storage size and growth | Schema/data sizing, storage dashboard | Risk of capacity exhaustion, rising cost |

Not every managed tier exposes host metrics or all query log fields. When building dashboards, distinguish **actually collectible metrics** from desired ones; missing visibility must be tracked as an **observability risk**, not filled with fake zero values.

### Incident Runbooks to Maintain

**When the API cannot connect to Neo4j:**

1. Check DNS, Bolt URI, TLS certificate, and network rules/private endpoints.
2. Inspect Driver exceptions: `ServiceUnavailableException`, `SessionExpiredException`, `AuthenticationException`, timeouts.
3. Check instance/cluster status and provider incident notices if managed.
4. Do not retry indefinitely on write queries lacking idempotency keys.
5. Record timestamps, impact, root cause, and recovery path.

**When queries are slow:**

1. Separate API latency, pool wait, query execution, and lock wait.
2. Capture the actual Cypher query and run `EXPLAIN`/`PROFILE` in an appropriate environment.
3. Check indexes, `Rows`, `DB Hits`, and relationship fan-out.
4. Compare read/write load, CPU, memory, page cache, and concurrent import jobs.

If the issue lies in the managed platform, file a support case with timestamps, instance ID, query ID, or sanitized metrics — **never send passwords or sensitive data**.

## 15. Three Decision Scenarios

### Scenario A — Graph MVP for a Small Team

A four-engineer team building a friend-recommendation API has no 24/7 SRE/DBA, uses `MATCH`, `MERGE`, constraints, and Java Driver, and needs no custom plugins. Data has no special residency restrictions.

**Reasonable candidate:** managed Neo4j, provided the selected tier meets budget, network, and resource thresholds. The team must still monitor queries, privileges, backup/restore, and maintain integration tests.

**Do not conclude:** managed automatically guarantees every API SLA or eliminates the need for Cypher optimization.

### Scenario B — System with Internal Data Residency Regulations

An organization has strict data residency rules requiring all copies/backups to reside on audited infrastructure, needs a custom Java procedure, and has a Neo4j operations team and DR policy.

**Reasonable candidate:** self-managed on approved infrastructure, **provided** the operations team proves HA, restore, security, patching, and cost. Managed is only viable if a specific tier **satisfies every mandatory requirement**.

**Do not conclude:** self-managed is inherently safer. Missing restore drills or improper RBAC can create higher risk.

### Scenario C — Large, Fast-Growing Service

A transactional system analyzing multi-hop relationships experiences rapid node/relationship growth, has strict p99 latency targets, and runs nightly batch import jobs.

**Run a measured proof-of-concept for both models** rather than choosing by vendor name:

- Datasets with identical degree distributions and path structures.
- Identical Java Driver queries and parameters.
- Equivalent indexes/constraints and Cypher versions.
- Measure peak read/write, lock contention, and import job impact.
- Calculate total infrastructure, egress, licensing, support, and operational hours.
- Test failures and verify RPO/RTO.

The right option will depend on verified benchmark results, not just data scale.

## 16. Pre-Approval Checklist for Deployment Model

| Check Question | Minimum Evidence |
|---|---|
| Does the model meet region, data regulation, and private networking? | Architecture documentation and connectivity tests |
| Does it meet RPO, RTO, and availability? | SLA/design + drills or matching evidence |
| Are all mandatory APOC/GDS/custom procedures supported? | List of procedures verified running on target |
| Is there a plan for bulk data import and deltas? | Runbook, rehearsal results, error statistics |
| Are schema/indexes fully recreated? | `SHOW CONSTRAINTS`, `SHOW INDEXES`, and online checks |
| Do business queries meet functional and performance SLOs? | Integration/load tests on representative data |
| Does the app have least privilege, TLS, and secret rotation? | Privilege test results and security review |
| Are dashboards, alerts, and runbooks in place? | Live dashboard populated with data, designated on-call owner |
| Are costs within budget even under growth? | Multi-scenario TCO forecast |
| Is there a cutover, failback, and data rollback plan? | Rehearsal + go/no-go criteria |

**Approval rule:** missing evidence on a mandatory requirement must be marked **unverified**, never automatically marked "passed" just because a service is popular or a demo succeeded.

## 17. Exercises

### Exercise 1 — Identify Responsibilities

A service running on AuraDB executes a `MATCH` query expanding many relationships and causes timeouts. Who bears primary responsibility for how the Cypher is written? Can you ask the provider to rewrite the query for you?

**Suggested answer:** The application/data team is responsible for query design and tuning, checking indexes, and inspecting data. The provider is responsible for the platform within the tier scope and may assist with diagnostics, but managed services do not rewrite business query logic.

### Exercise 2 — RPO and RTO

An organization tolerates at most **10 minutes of data loss** and requires recovery within **45 minutes**. A service advertises "daily backups" and "high availability." Is that enough evidence to choose it?

**Answer:** No. Daily backups do not prove RPO ≤ 10 minutes; HA does not replace backups. You must check snapshot/recovery intervals, SLAs, recovery procedures, restore drill records, and region-failure handling.

### Exercise 3 — Custom Plugin

A system has a custom Java procedure called via `CALL com.example.graph.recompute(...)`. The managed option does not allow loading that JAR. The team still wants to score managed 5/5 because it saves SRE hours. What should they do?

**Answer:** If the procedure is mandatory and has no replacement, managed fails a hard requirement. Either redesign using supported Cypher/Java services/GDS and re-evaluate, or choose self-managed. Do not use a weighted total score to override incompatibility.

### Exercise 4 — Migration Is Not Just Changing the URI

After loading 5 million nodes into the new environment, `count(n)` matches the source, yet some `Customer-[:PLACED]->Order` queries return wrong results. Name at least four follow-up checks.

**Suggested answer:** Compare relationship counts by type/direction; verify source–target key pairs of relationships; check constraints/indexes; inspect identifier properties and mappings; check for skipped import transactions; run representative business queries and inspect pipeline error logs. Matching node counts do not prove identical graph structure.

### Exercise 5 — Avoiding Bad Rollback at Cutover

The application has been writing new orders to the target database for 30 minutes. The team wants to switch `NEO4J_URI` back to the old database for a "quick rollback." What is the risk?

**Answer:** The old database likely lacks orders written only to the target. Switching the URI immediately causes missing/inconsistent business data. You need a reverse-sync plan, delta reconciliation, or keeping the application in a safe mode until data is reconciled.

### Exercise 6 — TCO

A self-managed VM has a list price 40% lower than managed, but requires after-hours DBA/SRE on-call, cross-region backups, restore drills, and license support. Is there enough basis to conclude self-managed is cheaper?

**Answer:** No. You must compare TCO including infrastructure, licensing, support, backups, networking, staffing, monitoring, incidents, and expected risk over the same period. Comparing raw VM price against an all-in subscription is not apples-to-apples.

## 18. References

- [Neo4j Aura documentation](https://neo4j.com/docs/aura/)
- [Neo4j Operations Manual](https://neo4j.com/docs/operations-manual/current/)
- [Neo4j Operations Manual — Clustering](https://neo4j.com/docs/operations-manual/current/clustering/)
- [Neo4j Operations Manual — Backup and restore](https://neo4j.com/docs/operations-manual/current/backup-restore/)
- [Neo4j Operations Manual — Docker](https://neo4j.com/docs/operations-manual/current/docker/)
- [Neo4j Operations Manual — Kubernetes](https://neo4j.com/docs/operations-manual/current/kubernetes/)
- [Neo4j Java Driver Manual — Connect to the database](https://neo4j.com/docs/java-manual/current/connect/)
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/)
- [Neo4j Upgrade and Migration Guide](https://neo4j.com/docs/upgrade-migration-guide/current/)

`current` documentation pages may change across releases. In particular, **AuraDB backup/DR features, tiers, network limits, APOC/GDS, privileges, and pricing** must be verified for the **exact service/tier being purchased**; do not infer them from general guides.

## 19. Key Takeaways

- **Choosing a deployment model is a decision about operational responsibility and risk**, not just where data lives.
- **Self-managed** provides deep control, but requires capability for backups, restores, HA, patching, security, observability, and incident on-call.
- **Managed** reduces much of the platform operations work per tier, but **does not** replace the application team's responsibility for Cypher, schema, data, privileges, SLOs, and costs.
- **RPO, RTO, data residency, private networking, and mandatory plugins are hard constraints**; verify them before scoring options.
- **Benchmark real workloads and calculate full TCO**, comparing query latency, throughput, backup/DR, licensing, networking, and staffing.
- **Migrating Neo4j means migrating data and graph semantics**, not just changing a URI; you must have reconciliation, cutover, and safe failback plans.
