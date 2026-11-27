# Distinguishing Community, Enterprise, and Neo4j Service Tiers

*Chapter: Neo4j Environment Setup.*

## 1. Why Is It Necessary to Distinguish Them?

Neo4j stores data as a **property graph**: entities are *nodes*, connections are *relationships*, and both can carry *properties*. You use Cypher to match relationships and paths; Java applications can connect via the Neo4j Java Driver or Spring Data Neo4j. These foundational skills can be practiced across many Neo4j deployment forms.

However, when designing real-world systems, the question is not just "can it run Cypher?" but also:

- Do we need one or multiple *databases* inside the same DBMS?
- If a server goes down, does the system automatically fail over to another machine to keep serving?
- Do we need fine-grained authorization across multiple user groups and centralized authentication?
- Do we need backups while the service remains online, and how long must backups be retained?
- Will the team manage servers and Neo4j upgrades itself, or use a Neo4j-operated managed service?
- What are the node, relationship, memory limits, and availability commitments (*SLA*) of the current plan?

**Lesson goal:** distinguish the two self-managed editions (Community, Enterprise) and the four common AuraDB tiers, verify your current environment yourself, and choose a configuration suited to a given problem.

## 2. Two Classification Axes Not to Confuse

Neo4j has two main deployment models:

1. **Self-managed:** you install Neo4j on a personal machine, server, VM, Docker, or Kubernetes; you choose **Community Edition** or **Enterprise Edition**, and take responsibility for configuration, backups, and operations.
2. **Managed cloud (Neo4j AuraDB):** Neo4j operates the service; you create an instance and pick a **tier/service plan** such as **Free**, **Professional**, **Business Critical**, or **Virtual Dedicated Cloud (VDC)**.

| Concept | What question does it answer? | Examples |
|---|---|---|
| **Edition** | Which feature set does the self-installed Neo4j software belong to? | Community, Enterprise |
| **Deployment** | Who operates the servers and infrastructure? | Self-managed via Docker; AuraDB service |
| **AuraDB tier** | What quotas, availability, and support level does the cloud service provide? | Free, Professional, Business Critical, VDC |
| **Version** | Which software version is running? | Neo4j 5.x, calendar-versioned branches like 2026.x |
| **License / subscription** | What usage rights and service terms apply? | GPLv3 for Community; commercial/evaluation agreement for Enterprise; AuraDB subscription |

**Key takeaway:** an AuraDB instance may use Enterprise server capabilities, yet the edition name in query output does not tell you which AuraDB tier the instance belongs to. Conversely, running Enterprise yourself does not automatically give you an HA system: you must configure clustering, sufficient servers, and operational procedures.

## 3. Community Edition vs. Enterprise Edition: Practical Differences

Both editions support property graphs, nodes, relationships, properties, Cypher queries, ACID transactions, basic indexes, edition-appropriate constraints, and communication over Bolt/Drivers. You can learn data modeling and write most Cypher queries on Community before deploying to production.

| Capability | Community Edition (CE) | Enterprise Edition (EE) |
|---|---|---|
| **Typical purpose** | Learning, prototyping, single-server apps, or small/medium self-managed projects | Applications requiring advanced security, high availability, scalability, and administration |
| **License** | Open source under GPLv3; must comply with corresponding license obligations | Commercial license or evaluation license under Neo4j terms |
| **Graph model, Cypher, ACID, Driver** | Yes | Yes |
| **Number of standard databases per DBMS** | One standard data database, alongside the <code>system</code> database | Supports multiple standard databases, depending on resources and design |
| **Clustering, writer election, automatic failover** | No built-in clustering | Supports clustering architecture; must be properly deployed to achieve HA |
| **Backup** | Offline backup via dump when database-stop requirements are met | Supports online backup and recovery for operational needs |
| **Advanced security** | Basic authentication and security config; lacks EE's fine-grained RBAC | Role-based access control, fine-grained permissions, LDAP/Active Directory integration |
| **Other advanced capabilities** | Sufficient for developing most foundational graph examples | Includes features such as Change Data Capture, parallel runtime, and enterprise admin/monitoring options |

### 3.1. A database is different from a DBMS

In a standard setup, the **DBMS** is the Neo4j process managing databases. The <code>system</code> database handles metadata and administration—it is not where applications store business graphs.

Community allows **one standard database** (commonly named <code>neo4j</code> by default) alongside <code>system</code>. Enterprise supports managing multiple standard databases, such as <code>catalog</code>, <code>recommendation</code>, and <code>fraud</code>. You do not need Enterprise just to have multiple node labels or relationship types within **the same graph**: labels such as <code>User</code>, <code>Product</code>, and <code>Order</code> can coexist in a single Community database.

A single transaction does not automatically span multiple databases. When splitting databases in Enterprise, design query, transaction, and administrative boundaries explicitly.

### 3.2. Clustering and backup are two separate requirements

**Clustering** improves availability and serving capacity, but requires multiple data replicas, coordination mechanisms, monitoring, and failover testing. Enterprise provides this capability; running Enterprise on a single machine does not protect you from host failure.

**Backup** enables recovery from accidental deletes, data corruption, or other incidents. A cluster replicates both valid data and accidental delete operations, so **clustering does not replace backups**. Community supports offline backup procedures when appropriate; Enterprise includes online backup. In AuraDB, the service manages snapshots/backups per tier with varying frequencies and retention windows.

### 3.3. Security and performance

Community includes authentication and can configure encrypted connections; do not assume "Community has no security." Enterprise adds features such as **role-based access control (RBAC)**, finer-grained authorization, and enterprise identity provider integration.

Both editions still require proper indexes, good query plans, and bounded result sets. Enterprise unlocks additional optimization and execution options, but it will not fix poorly written Cypher queries or a flawed graph model.

> **License note:** pulling the Enterprise Docker image and accepting its terms in Docker does not grant commercial usage rights. Verify valid licensing/subscriptions for your deployment purpose.

## 4. When Using Neo4j AuraDB: Comparing the Four Service Tiers

AuraDB is Neo4j's managed graph database service. Rather than picking Community/Enterprise binaries, you choose a **tier** suited to your data, operational requirements, availability targets, and budget. The table below summarizes published AuraDB documentation at the time of writing (11/2026); quotas and terms can change, so verify the official site before deploying.

| AuraDB Tier | Best fit | Key operational differences |
|---|---|---|
| **Free** | Learning Cypher, demos, small prototypes | No uptime SLA or HA; currently published Free limits up to **200,000 nodes**, **400,000 relationships**, **1 GB storage** |
| **Professional** | Apps needing scalable resources and better backup management than Free | Paid by resources; no HA/uptime SLA; scheduled daily snapshots with published retention of **7 days** |
| **Business Critical** | Systems requiring high availability and service continuity | Multi-node HA architecture, **99.95%** uptime SLA, hourly snapshots; published retention of **30 days** |
| **Virtual Dedicated Cloud (VDC)** | Organizations needing isolated environments and strict infrastructure/security requirements | Dedicated environment, HA and **99.95%** SLA; snapshot policies, retention, and configurations depend on version/contract |

Tiers may differ in their **databases-per-instance** limit. According to the current AuraDB limits table, Free and Professional allow **1 database per instance**, while Business Critical and VDC permit more according to tier quotas. Therefore, **never assume "Aura uses the Enterprise engine so every tier supports multiple databases."**

When comparing tiers, do not look only at graph size. Evaluate all of the following together:

- **Node/relationship** quotas, storage, RAM, and scaling headroom.
- **HA, SLA**, regions, private connectivity, or network isolation requirements.
- **Snapshot schedules, backup retention, export, and restore options**.
- Administrative features, access controls, integration capabilities, and growth cost.

**AuraDB vs. AuraDS:** AuraDB targets operational graph storage and querying; AuraDS focuses on data science workloads. Product names, tiers, and usage rights must be checked separately.

## 5. Accurately Identifying Your Current Environment

You cannot determine a system's edition or tier from a project name, client tool, or documentation example alone. Follow this workflow to **verify the environment you are actually using** rather than guessing.

### Step 1 — Identify where you are connecting

- If you run Neo4j Server yourself via installer, Neo4j Desktop, Docker, or Kubernetes, identify it as **self-managed** and inspect its edition.
- If you created an instance in **Neo4j Aura Console** and use an Aura-issued URI (typically <code>neo4j+s://...</code>), check the **instance name and tier in Aura Console**. The URI alone cannot reveal the tier.
- If connecting through another team's infrastructure, ask the administrator about the deployment method and console/admin access; a read-only data account may not be able to inspect all metadata.

### Step 2 — Query the version and edition

Log into the assigned DBMS via Neo4j Browser or cypher-shell and run a **read-only metadata** query:

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions[0] AS version, edition;
~~~

Illustrative output (actual edition/version values must be read from the live system):

| name | version | edition |
|---|---|---|
| Neo4j Kernel | 2026.x.y | community or enterprise |

If <code>edition = community</code>, the server is running Community. If <code>edition = enterprise</code>, that indicates the engine edition; **it still does not tell you the AuraDB tier**. This command may be restricted by privileges or vary by version; if it errors, check your version's docs and confirm with an administrator rather than guessing the edition from a permission error.

### Step 3A — If self-managed: inspect the package/deployment

With Docker, inspect the actual running image:

~~~bash
docker ps --format "table {{.Names}}\t{{.Image}}"
~~~

By official image convention, Neo4j Community tags omit the <code>-enterprise</code> suffix; Enterprise tags include it (for example <code>neo4j:2026.10.2-enterprise</code>). Combine **image tag**, `dbms.components()` output, and license records to verify. Never treat the container name alone as proof of edition.

For native installations, check the installed package and deployment config. With Neo4j Desktop, the Desktop app itself is not the DBMS edition: inspect the specific DBMS instance you opened.

### Step 3B — If using AuraDB: read the tier in Console

1. Open [Neo4j Aura Console](https://console.neo4j.io/) and select the right **organization/project**.
2. Locate the **instance** matching your app's URI and verify the instance ID/name and region.
3. Read the **tier / plan** in the instance details (Free, Professional, Business Critical, or Virtual Dedicated Cloud), and inspect resource sizing and backup settings.
4. If you have billing access, verify the subscription/contract. Only authorized users can view certain billing or administrative sections.

**Do not use** <code>CALL dbms.components()</code> to infer the AuraDB tier. Its output may only report the engine edition. For example, seeing <code>enterprise</code> does not prove you are paying for Business Critical or covered by a 99.95% SLA.

### Step 4 — Record an "environment profile"

Fill out this table from verified details of the **exact connected instance**:

| Attribute to record | Value to verify |
|---|---|
| Deployment location | Self-managed / AuraDB |
| DBMS edition | Community / Enterprise / insufficient privileges to confirm |
| AuraDB tier (if applicable) | Free / Professional / Business Critical / VDC |
| Version | Value from <code>dbms.components()</code> |
| Application database | Database name selected by Driver/Cypher |
| Key limits / features | Database count, quotas, HA, backups, access control |
| Evidence source | DBMS query, instance details, deployment config, contract |

This profile matters for Java applications: the same code using the Neo4j Java Driver or Spring Data Neo4j can connect across multiple environments, yet **database creation rights, backup capabilities, quotas, clustering support, and admin privileges differ**.

## 6. Safe Practice: Observing Shared Capabilities

Before trying Enterprise administrative commands, run a small property graph example on a **writable database**. The snippet below uses <code>MERGE</code> so repeated sequential runs by one user do not duplicate nodes with the same key.

~~~cypher
MERGE (u:User {userId: 'u-001'})
SET u.name = 'An'
MERGE (p:Product {sku: 'neo4j-book'})
SET p.name = 'Book about Cypher'
MERGE (u)-[:VIEWED]->(p);
~~~

~~~cypher
MATCH (u:User {userId: 'u-001'})-[:VIEWED]->(p:Product)
RETURN u.name AS userName, p.name AS productName;
~~~

On a fresh practice database, consider adding a uniqueness constraint on the identifier property:

~~~cypher
CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User) REQUIRE u.userId IS UNIQUE;
~~~

Uniqueness constraints, indexes, and basic graph queries **are not reasons that force you to buy Enterprise by default**. On a system with existing data, check for duplicates and constraint-creation privileges beforehand; the statement can fail if existing data violates uniqueness or the user lacks permissions. The <code>MERGE</code> example above illustrates syntax and does not replace concurrency strategies in production.

You can also inspect index and constraint metadata in the current database (run each command separately):

~~~cypher
SHOW INDEXES;
SHOW CONSTRAINTS;
~~~

Both commands inspect query structures, but **do not identify the AuraDB tier**. Commands such as <code>CREATE DATABASE</code>, <code>SHOW ROLES</code>, server/cluster operations, or restores depend on edition, tier, and account privileges. Never try creating/dropping databases or altering production config just to "test" whether a feature is supported.

## 7. Choosing the Right Option for Your Requirements

| Use case | Option to evaluate first | Reason |
|---|---|---|
| Learning nodes, relationships, Cypher, indexes, constraints; running locally | **Community** or **AuraDB Free** | Full core graph capabilities; Free carries its own data quotas |
| Small self-operated app; maintenance windows and offline backups acceptable | **Community** | Reduces licensing cost, in exchange for the team owning recovery and availability |
| Self-managing graphs for multiple teams, multiple databases, RBAC, clustering, online backup | **Enterprise** | Provides advanced governance and operations features; requires licensing, infrastructure, and setup |
| Want managed service for a growing app, no SLA-backed HA required yet | **AuraDB Professional** | Scales resources and includes scheduled backups per plan |
| Order/recommendation or fraud-detection service requiring HA and explicit SLA | **AuraDB Business Critical** | Provides HA and published SLA; still requires suitable application architecture |
| Need dedicated cloud environment with strict isolation or custom infra requirements | **AuraDB VDC** | Dedicated environment and enterprise options per configuration/contract |

### Decision-making example

A team builds a **user — viewed — product — belongs_to_category** graph to prototype recommendations. During the modeling and Cypher learning phase, Community or AuraDB Free is usually enough if the graph is small. When deploying a real application, the team must measure node/relationship counts, query latency, and backup needs before choosing the next tier.

If a transactional system runs 24/7, requires surviving server loss, and enforces role-based access control, running a single Enterprise container is not enough. You need a cluster architecture or an HA-backed service, tested backup/restore plans, and appropriate SLA terms.

### Common misconceptions

- **"Community doesn't support Cypher/indexes."** False. These are core Neo4j capabilities; major differences center on enterprise and operational features.
- **"Community is limited to 200,000 nodes."** False. That is a published quota for **AuraDB Free**, not a general limit on self-managed Community.
- **"Having Enterprise automatically gives you HA."** False. Clustering must be architected, deployed, operated, and tested.
- **"With a cluster, you don't need backups."** False. Logical data corruption or accidental deletion still requires restoring from a proper backup.
- **"AuraDB Professional definitely has HA/SLA like Business Critical."** False according to the current AuraDB limits table.
- **"The query returned <code>enterprise</code>, so I'm on AuraDB Business Critical."** False. Engine edition and cloud tier are two separate pieces of information.
- **"If <code>SHOW ROLES</code> fails, it must be Community."** Insufficient evidence: it may be due to user permissions or managed-environment restrictions.

## 8. Post-Lesson Self-Check

Pick a Neo4j instance you genuinely have access to and complete these steps:

1. Run <code>CALL dbms.components()</code> and record the returned version and edition.
2. Determine whether the instance is self-managed or AuraDB; if AuraDB, open Console to verify the **tier**.
3. Record database, capacity, HA, backup, and access limits from the docs/console applicable to that instance.
4. Run a <code>MATCH</code> query on your practice graph; run <code>SHOW INDEXES</code> and <code>SHOW CONSTRAINTS</code> if permitted.
5. For a scenario with 1 million nodes, daily backups required, and HA optional, explain why AuraDB Free cannot be chosen by default; list at least two alternatives and the operational costs to weigh.
6. For a scenario requiring zero downtime when losing a node, specify which edition/tier supports HA **capability**, how deployment/SLA guarantees work, and why backups remain mandatory.

**Completion criteria:** you can present "deployment — edition — tier" separately, cite evidence for which configuration you are running, and map each requirement (database count, authorization, HA, backups, quotas) to actual features.

## References

Official Neo4j pages are the authoritative source for verifying features and quotas as versions or service plans change:

- [Neo4j Operations Manual — Introduction / editions](https://neo4j.com/docs/operations-manual/current/introduction/): distinguishing Community, Enterprise, and capability tables.
- [Neo4j Operations Manual — Database administration](https://neo4j.com/docs/operations-manual/current/database-administration/): database limits by edition.
- [Neo4j Operations Manual — Built-in procedures](https://neo4j.com/docs/operations-manual/current/procedures/built-in-procedures/): the <code>dbms.components()</code> procedure.
- [Neo4j Operations Manual — Docker introduction](https://neo4j.com/docs/operations-manual/current/docker/introduction/): image tagging by edition and license requirements.
- [Neo4j Aura — Quotas and limits](https://neo4j.com/docs/aura/quotas-and-limits/): node, relationship, database, HA, SLA, and backup limits by tier.
- [Neo4j Aura — Backup, restore and export](https://neo4j.com/docs/aura/managing-instances/backup-restore-export/): snapshot schedules, restore, and tier conditions.
- [Neo4j Pricing](https://neo4j.com/pricing/): up-to-date comparison of plans, features, and commercial terms.

*Edition and tier details were compiled from Neo4j documentation at the time of writing, November 2026. Quotas, plan names, capabilities, and licensing policies may change; the documentation and contract governing your actual environment are always the final authority.*
