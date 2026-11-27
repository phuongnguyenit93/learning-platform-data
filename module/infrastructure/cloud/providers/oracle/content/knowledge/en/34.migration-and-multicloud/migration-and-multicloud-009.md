# Multicloud Oracle Database Models and Selection Criteria

In the **Migration and Multicloud** chapter of the **CLOUD_PROVIDERS_ORACLE** module, this lesson explains how to position Oracle Database when applications, data, or standby systems span multiple cloud platforms. The focus is choosing an architecture aligned with Oracle Cloud Infrastructure (OCI), while defining connectivity, authorization, monitoring, automation, availability, and cost control.

An enterprise may run applications on Azure while using a database on OCI; place an Oracle Database service directly inside an AWS data center; or maintain a primary database and replicas across two clouds. All three involve multicloud yet differ in transaction paths, operational responsibilities, and recoverability.

After this lesson, learners will be able to:

- Distinguish cross-cloud connectivity models, Oracle Database@ services, and cross-cloud data replication.
- Select database placement based on transaction characteristics, mandatory features, and where applications run.
- Evaluate latency, RTO/RPO, IAM, data security, cost, and operability.
- Prepare a test plan alongside an architecture decision record before deployment.

## 1. Classifying by Three Independent Questions

### 1.1. Where Does the Database Actually Run?

Separate the physical location of the data tier from where the service is purchased or the management console resides.

- **Database inside an OCI region:** applications in another cloud must access it across an inter-environment link.
- **Oracle Database@ service in a partner cloud:** the service's database infrastructure deploys inside the partner's data center; applications connect via the corresponding integrated networking mechanism.
- **Oracle Database on VMs or another cloud's managed service:** compatibility and administrative responsibilities vary by product.

In current documentation, Oracle uses the names Oracle AI Database@Azure, Oracle AI Database@Google Cloud, and Oracle AI Database@AWS. This lesson uses the shorthand **Database@Azure**, **Database@Google Cloud**, and **Database@AWS** when distinguishing product branding is unnecessary. These partner platforms are covered in [Oracle's multicloud database deployment guide](https://docs.oracle.com/en/solutions/oci-best-practices/deploy-multicloud-oci-oracle-database-services1.html).

### 1.2. Who Manages Each Component?

A system may simultaneously involve:

- The provider operating hardware and the underlying service layer.
- The cloud team managing tenancies, compartments, subscriptions, projects, accounts, networks, and resource-creation rights.
- The DBA managing databases, data accounts, schemas, and tasks delegated to the customer by the service.
- The application team managing connection pools, transactions, retries, timeouts, and error-handling rules.

Higher automation typically narrows the scope of configuration customers touch directly. Therefore, a requirement such as “must have OS access” must be treated as a product selection constraint.

### 1.3. How Is Data Used?

Three common usage patterns are:

1. **Single primary write source:** applications from one or more clouds access the same primary database.
2. **Single write source with replicas:** replicas serve recovery or read flows able to tolerate lagged data.
3. **Multiple write sources:** each database can accept writes under designed data-ownership rules and conflict resolution mechanisms.

Database placement, management level, and replication topology are three combinable axes. For example, a Database@ instance can serve as the primary in a supported standby setup. However, choosing Database@ alone does not define DR topology.

| Model | Typical Layout | Selection Driver | Key Question to Answer |
| --- | --- | --- | --- |
| App in other cloud, DB on OCI | Azure/AWS/Google Cloud → private link → OCI | Keep data services on OCI | Do link latency and stability meet transaction needs? |
| Database@ | App and data tier co-located in partner cloud | Reduce app–DB distance while keeping Oracle capabilities | Are target region, service, and required features available? |
| Self-managed Oracle DB on IaaS | VMs, storage, and networking of chosen cloud | Need deep control | Can internal teams operate and recover the full stack? |
| Oracle service managed by another cloud | Such as Amazon RDS for Oracle | Reduce platform administration | Do feature or privilege limits affect the application? |
| Unidirectional replication | Primary DB → standby or CDC target | DR, migration, analytics | Under what commitments is the replica protected and used? |
| Bidirectional replication or sharding | Multiple independent databases | Serve writes across multiple locations | Who owns each data slice and how are conflicts resolved? |

## 2. App in Another Cloud, Database on OCI Model

### 2.1. Architecture and Transaction Path

In what is commonly called a **split-stack** model, the application tier sits in one cloud while Oracle Database sits in OCI. Every SQL operation from app to database depends on the network path between the two environments.

~~~mermaid
flowchart LR
    subgraph Partner["Application Cloud"]
        APP["Application / connection pool"]
        NET["Application network"]
        APP --> NET
    end
    LINK["Private interconnect or VPN"]
    subgraph OCI["Oracle Cloud Infrastructure"]
        DRG["DRG / routing"]
        VCN["VCN / database subnet"]
        DB["Oracle Database"]
        DRG --> VCN --> DB
    end
    NET --> LINK --> DRG
~~~

This is a conceptual diagram for a database using a private endpoint inside a VCN. Actual endpoint and network mechanisms must match the specific service.

With Azure, Oracle Interconnect combines **OCI FastConnect** and **Azure ExpressRoute** at supported locations. Connectivity must be configured on both sides. See [Oracle Interconnect for Azure](https://docs.oracle.com/en-us/iaas/Content/multicloud/interconnect-azure.htm).

With Google Cloud, Oracle Interconnect uses **OCI FastConnect** and **Google Cloud Partner Interconnect** in supported region pairs. See [Oracle Interconnect for Google Cloud](https://docs.oracle.com/en-us/iaas/Content/multicloud/interconnect-gcp.htm).

For AWS or other locations, evaluate available interconnects, partner links, or appropriate VPNs. Never infer connectivity availability from region names. [Oracle's Multicloud Interconnect catalog](https://docs.oracle.com/en-us/iaas/Content/multicloud/interconnect.htm) is the starting point to verify supported options.

### 2.2. When Does This Model Make Sense?

This model is worth considering when an enterprise already operates a database platform on OCI, wants to preserve existing DBA and monitoring workflows, and needs the application to continue using another cloud's services.

Workloads with few round trips, batched requests, or most processing inside the database are easier to position this way than workloads issuing many small sequential queries.

For instance, a job submitting an aggregation statement and receiving one result behaves very differently from a UI screen firing dozens of queries to build a list. Even with equal bytes transferred, wait counts and user impact differ dramatically.

### 2.3. Evaluating Latency via Round-Trip Count

An initial estimation model:

~~~text
Request time ≈
  application processing time
  + database processing time
  + sequential network round trips × RTT
  + queuing and data transfer time
~~~

Suppose one operation performs 18 sequential round trips:

- App–DB RTT is 2 ms: formula wait component is roughly 36 ms.
- RTT rises to 9 ms: this component becomes roughly 162 ms.
- Roughly 126 ms of delta appears before even factoring in load growth or retries.

This is a **calculation example**, not an Oracle service measurement or performance guarantee. Query batching, multi-row fetches per round trip, and parallel calls can alter effective round trips. Re-measure with the real application, especially at p95 and p99.

### 2.4. Components That Must Be Designed Together

| Component | Work Required | Failure If Overlooked |
| --- | --- | --- |
| Network addressing | Plan non-overlapping CIDRs for connected networks | Misrouting or complex NAT additions |
| Bidirectional routes | Check forward path, return path, and route advertisements | One-way-only connectivity |
| Private DNS | Ensure app hosts resolve exact endpoint names | IP-based TCP works, yet app fails to connect |
| Network access control | Restrict app sources and actual listener ports | Overly broad exposure or blocking valid traffic |
| Transit encryption | Check encryption settings, certificates, and identity checks | Private network exists yet fails data protection rules |
| Link redundancy | Verify independent circuits, devices, paths, and endpoints | Both links fail from one shared component |
| Connection pool | Set timeouts, dead-connection checks, and retry policies | App threads hang during network blips |
| Observability | Collect RTT, packet loss, DNS, pool waits, and DB waits | Hard to separate network faults from SQL faults |

Private connectivity addresses transport and isolation. Encryption and authentication must be verified separately against organizational requirements.

## 3. Oracle Database@ in a Partner Cloud Model

### 3.1. Nature of the Model

Database@ brings the Oracle service's data tier close to applications running in a partner cloud. The location of query-serving infrastructure and control plane components can differ.

For Database@Azure, Oracle describes infrastructure in Azure data centers as a **child site** paired with an OCI **parent site**. Oracle infrastructure is operated by OCI personnel. Therefore, determining database placement must examine service architecture, not just the cloud name on an invoice. See [Oracle AI Database@Azure architecture](https://docs.oracle.com/en-us/iaas/Content/database-at-azure/getting-started-architecture.htm).

~~~mermaid
flowchart TB
    subgraph DC["Partner Cloud Data Center"]
        APP["Application"]
        INTEGRATION["Integrated networking mechanism"]
        DB["Oracle Database@ data tier"]
        APP --> INTEGRATION --> DB
    end
    CONTROL["Control plane and management services"]
    CONTROL -. "Managed per service architecture" .-> DB
~~~

Dashed arrows represent management, not that every SQL statement traverses the parent region. When designing, map data paths, management paths, backup paths, and replication paths separately.

### 3.2. Three Services Have Different Integration Mechanisms

| Service | One Integration Point to Know | Design Implication |
| --- | --- | --- |
| Database@Azure | Connects to app network via a delegated subnet per service model | Coordinate VNet, subnet, delegation rights, and related OCI resources |
| Database@Google Cloud | Uses an Oracle Database network (ODB network) to connect to app VPC | Check service networking, VPC links, and project/tenancy scope |
| Database@AWS | Uses an ODB network and ODB peering to connect to app VPC | Configure routes, DNS, and admin rights per AWS docs |

These mechanisms are covered in [Database@Azure overview](https://docs.oracle.com/en-us/iaas/Content/database-at-azure/overview.htm), [Database@Google Cloud overview](https://docs.oracle.com/en-us/iaas/Content/database-at-gcp/overview.htm), and [AWS ODB peering guide](https://docs.aws.amazon.com/odb/latest/UserGuide/configuring.html).

ODB peering is a resource connecting to an ODB network and differs from standard VPC peering. When designing across multiple VPCs, use the exact service-supported model; never assume peering is transitive. See [how Oracle Database@AWS works](https://docs.aws.amazon.com/odb/latest/UserGuide/how-it-works.html).

### 3.3. What to Verify Before Selecting

The Database@ name alone does not determine whether a configuration is deployable. The assessment record must specify:

1. Application cloud and region.
2. Region, zone, provisioning capacity, and quotas for the database service.
3. Service type needed: Exadata Database Service, Autonomous Database, or another catalog item.
4. Version, edition, features, admin limits, and resource billing model.
5. Supported backup, recovery, HA/DR, and topology scope.
6. How partner accounts link to OCI tenancy, permission sync, and cost tracking.

Never assume catalogs and support are identical across Azure, Google Cloud, AWS, or across regions. With Database@AWS, initial setup includes linking an AWS account and an OCI tenancy per [Oracle's service overview](https://docs.oracle.com/en-us/iaas/Content/database-at-aws/oaaws-overview.htm).

### 3.4. Practical Strengths and Limits

Architecturally, co-locating applications and the data tier can reduce communication wait time. This makes it worth testing for latency-sensitive apps or those hard to refactor for fewer database calls.

Still, measure from the exact application placement. An app in the wrong zone, routing through an intermediate hop, or using the wrong endpoint may miss expected gains.

Database@ also does not automatically migrate schemas, data, accounts, or app configs from legacy systems. The project team still needs a migration, reconciliation, and connection-cutover plan. Resources appearing in the partner portal also do not replace database authorization and related OCI governance.

## 4. Oracle Database on Other Cloud Infrastructure or Services

### 4.1. Self-Managed on IaaS

The enterprise deploys Oracle Database on VMs using the chosen provider's networking and storage. Operations typically handles far more:

- OS, patches, database installation, and listener setup.
- Capacity, I/O performance, backups, recovery, and integrity checks.
- Security, admin accounts, monitoring, and maintenance schedules.
- HA/DR mechanisms, automation, and incident on-call.

This model fits evaluation when workloads need control unavailable in managed services. A prerequisite is that platform, OS, machine type, and database config meet both Oracle and cloud provider support requirements.

Never infer RAC capability or database support merely because a VM has enough CPU and RAM. Storage, cluster networking, and certification requirements must be verified separately.

### 4.2. Services Managed by Another Cloud

One example is **Amazon RDS for Oracle**. The service reduces platform admin work yet imposes privilege and feature limits. For example, the master admin account in RDS is typically not equivalent to full SYSDBA privileges. See [Amazon RDS for Oracle documentation](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_Oracle.html).

RDS for Oracle typically does not support Oracle RAC. Consequently, workloads requiring RAC must pass feature screening before comparing prices. See [RDS for Oracle feature support](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Oracle.Concepts.FeatureSupport.html).

Clearly distinguish Database@AWS from RDS for Oracle: they have different service architectures, capabilities, and operational scopes. Never transfer conclusions about one product onto the other.

### 4.3. Evaluating Software Licensing and Cost

Before entering costs into a comparison table, verify facts applying to actual contracts and configurations:

- License-included service model vs. BYOL.
- Editions, options, and management packs the workload actually uses.
- Licensing scope for primary, standby, test, and parallel-run phases.
- Resource counting rules and support conditions of the chosen service.

Never take one provider's vCPU count and assume equivalence to another service's billing unit. In architectural decisions, use resource tables converted according to verified commercial records rather than guessing licensing rules.

## 5. Replicating Oracle Database Across Clouds

This is a data-design layer addable to the placement models above. Define the goal first: full database protection, feeding analytics, migration, or enabling multi-site writes.

### 5.1. Single Write Source with Oracle Data Guard

Data Guard maintains standby databases by shipping and applying redo. With physical standby, the primary database serves normal application writes; the standby protects data and can handle read workloads permitted by config, features, and licensing. See [Introduction to Oracle Data Guard](https://docs.oracle.com/en/database/oracle/oracle-database/26/sbydb/introduction-to-oracle-data-guard-concepts.html).

~~~text
App writes
     |
     v
Primary at Site A -- redo --> Standby at Site B
                                 |
                                 +-- Role transition when eligible
~~~

Two decisions to separate:

- **Redo transport mode:** synchronous or asynchronous.
- **Protection mode:** data durability requirements and behavior when connectivity drops.

Synchronous transport places standby acknowledgments in the commit path per configuration; remote RTT and I/O therefore affect transaction latency. Asynchronous allows commits without waiting for remote acknowledgment, risking missing redo at standby during an outage. See [Data Guard protection modes](https://docs.oracle.com/en/database/oracle/oracle-database/26/sbydb/oracle-data-guard-protection-modes.html).

Never promise RPO = 0 from the word “SYNC” alone. Specify protection mode, sync state, acknowledgment durability, and disconnect scenarios. Options like SYNC, FASTSYNC, and ASYNC carry distinct requirements in [managing data protection modes](https://docs.oracle.com/en/database/oracle/oracle-database/26/dgbkr/managing-data-protection-modes.html).

Building Data Guard across cloud boundaries also depends on versions, service types, automation limits, and supported topologies. Cross-check the [MAA Multicloud Certification Matrix](https://docs.oracle.com/en/database/oracle/oracle-database/19/haovw/multilcoud-certification-matrix.html) for the specific config; never assume every database pair configures identically.

### 5.2. Logical Replication and CDC with Oracle GoldenGate

GoldenGate fits evaluation when feeding data changes to another system, syncing partial data, or supporting low-downtime migrations. Source, target, data type, and replicated operation support must be checked per version.

Data Guard and GoldenGate can complement each other: one protects the database while the other distributes data or supports system transitions. Oracle outlines this combination in [Active Data Guard and GoldenGate best practices](https://docs.oracle.com/en/database/oracle/oracle-database/26/haovw/best-practice-oracle-active-data-guard-and-oracle-goldengate.html).

~~~text
Transactional Oracle Database
         |
         +-- GoldenGate / CDC --> Analytics data in another cloud
         |
         +-- Separate HA/DR mechanism matching DB protection goals
~~~

A healthy CDC pipeline does not prove the entire system can be recovered. Check un-replicated objects, security configs, jobs, integration links, and application reopening procedures too.

### 5.3. Multiple Write Sources and Active-Active

GoldenGate can support bidirectional topologies, yet it is asynchronous replication. Two databases can modify the same row concurrently before receiving each other's changes. Conflict detection and resolution are needed so data converges. See [active-active vs. active-passive](https://docs.oracle.com/en/database/goldengate/core/26/ggsol/active-active-vs-active-passive.html).

For example, two clouds both allow selling the last unit of stock. Both confirming orders simultaneously can violate inventory rules before conflicts are detected. “Last update wins” does not resolve shipping promises already sent to two customers.

Decisions required before opening dual-sided writes:

- Partition write ownership by region, branch, tenant, or business key where possible.
- Design unique keys and collision-free ID generation rules.
- Define handling for inserts, updates, deletes, and schema changes.
- Prevent replicated data from looping back to the source.
- Define behavior during disconnects, backlogs, and data reconciliation.

Conflict detection and resolution requirements are detailed in [GoldenGate active-active guidance](https://docs.oracle.com/en/database/oracle/oracle-database/26/haovw/ogg-active-active-guidance-dev-and-admin1.html).

If the core need is partitioning data by key and processing near origin, evaluate Oracle Globally Distributed Database instead of stitching multiple write sources onto one dataset. That is a specialized distributed design requiring evaluation of sharding keys, cross-shard transactions, and app requirements; see [Globally Distributed Database overview](https://www.oracle.com/database/distributed-database/).

### 5.4. Choosing Tools by Purpose

| Purpose | Primary Evaluation Path | What Not to Assume |
| --- | --- | --- |
| Protect DB with single write source | Data Guard and supported MAA topologies | Having a standby guarantees every RTO/RPO |
| Stream selective data to analytics | GoldenGate/CDC or suitable integration | Analytics target always reads latest data immediately after commit |
| Low-downtime migration | Initial load, delta sync, reconciliation, cutover | Enabling replication completes migration |
| Allow writes in multiple places | Data ownership rules, conflicts, app support | Bidirectional sync creates a global ACID transaction |
| Partition data by geography or key | Suitable sharding and routing architecture | Every query executes locally |

## 6. Selection Criteria Framework

### 6.1. Compatibility and Provisionability

This is a disqualifying criteria group. A cheaper option remains unsuitable if it lacks mandatory features.

List requirements at a verifiable level: database version, edition, RAC if needed, PL/SQL traits, data types, admin privileges, packaged app integrations, backup tools, and support needs.

For each requirement, attach evidence from docs, technical tests, or service confirmation. “Pending verification” items must be resolved before deployment decisions.

Seeing a region name in a catalog is insufficient. Check service types in that region, quotas, minimum sizes, provisioning capacity, and infrastructure lead time.

### 6.2. Transaction and Link Characteristics

| Workload Characteristic | Impact on Selection |
| --- | --- |
| Many sequential SQL round trips per request | Prioritize co-locating app and database |
| Queries returning large result sets | Bandwidth, transfer time, and egress volume matter |
| Windowed batch processing | More flexible per-query latency, yet must meet completion deadline |
| Services reading immediately after writes | Avoid routing reads to async replicas without proper consistency guards |
| Continuous write transactions | Measure redo generation, transport capacity, and apply speed |
| Clearly region-owned data | Can evaluate sharding or controlled multi-writer topology |

Beyond latency, measure throughput and concurrent connections. An option with good RTT can still bottleneck on connection pools, I/O, CPU, listeners, or replication paths.

Replication bandwidth must handle redo spikes with headroom to drain backlogs after interruptions. Using daily averages alone often leaves configurations unable to catch up during peak hours.

### 6.3. HA, DR, and Failure Domains

**HA** handles failures within a designed scope, such as an instance or infrastructure component. **DR** restores service when an entire site or larger failure domain is lost.

A system spanning two clouds can still share:

- One DNS or identity provider.
- One physical connectivity path.
- One geographic region.
- One secrets or encryption-key system.
- One release pipeline deploying bugs simultaneously to both sides.

Draw dependency diagrams and test each component-loss scenario. Never take two cloud logos as proof of independent recovery domains.

Separate two metrics clearly:

- **RPO:** maximum acceptable data loss per recovery objective.
- **RTO:** target time to restore service to an agreed operational level.

A decomposition model for planning:

~~~text
End-to-end RTO ≈
  incident detection
  + failover decision
  + database recovery or role transition
  + routing / endpoint update
  + application reconnection
  + minimum business verification
~~~

The database coming ready in minutes does not mean users can transact within that same time.

With async standbys, track **transport lag** and **apply lag** per tool definitions. Redo that arrived but has not applied can delay service reopening; redo that never arrived creates data loss if the primary is lost. Never convert a single lag metric into an RPO guarantee across all failure modes.

Replication also propagates accidental deletes or unwanted data edits. Maintain backups, retention, appropriate point-in-time recovery, and recovery drills. Ensure backups, encryption keys, and required privileges remain accessible when the primary domain fails.

### 6.4. Authorization and Data Security

A multicloud system has at least three permission layers:

| Layer | Management Scope | Example Decision Needed |
| --- | --- | --- |
| Partner cloud | Subscription/project/account, network, app resources | Who creates connections to the database network? |
| OCI | Tenancy, compartments, policies, service resources | Who manages databases, networks, backups, service settings? |
| Database | Users, roles, schema/table/procedure privileges | Which data may the application read/write? |

Logging into a cloud portal does not grant data query rights. Federation or account linking also does not automatically build least-privilege roles.

An operational plan must define:

- Separation of platform admin, database admin, and application accounts.
- Storing secrets appropriately; procedures to rotate passwords, wallets, or certificates.
- Controlling encryption key usage and restore operations.
- Collecting cloud and database audits, normalizing timestamps and event correlation.
- Controlled emergency break-glass access if the primary identity system fails.

Data protection scope must include primary, standby, analytics replicas, backups, and logs. Sending data to a second cloud for reporting creates another access-controlled scope.

### 6.5. Operability and Automation

Evaluate operations team capability across concrete tasks: patching, data recovery, certificate rotation, scaling resources, handling replication lag, and incident role transitions.

Build a responsibility matrix across providers, platform teams, DBAs, and app teams. For each task, record executor, trigger, maintenance window, and alert recipients.

Automation via Terraform or equivalent tooling must address both ecosystems simultaneously:

- Rights to create and modify resources on each side.
- Ordering of account, network, and database links.
- State, secret, and output management.
- Drift detection for manual config edits.
- Recovery when step N succeeds and step N+1 fails.

A deployment run across multiple APIs is not automatically an atomic transaction. Workflows must track which resources exist and which steps are idempotently re-runnable.

For monitoring, build dashboards linking application, network, database, replication, and backup health. A “database is up” alert is insufficient if connection pools are exhausted or the app cannot resolve endpoints.

### 6.6. Data Residency and Governance Scope

Map separately:

1. Primary database and replicas.
2. Backups and backup copies.
3. Redo, trail files, or transient pipeline data.
4. Logs, audits, and diagnostic dumps.
5. Admin, support, and observability paths.

The primary database's location answers only part of where data resides. The selection record must verify all remaining flows against internal policies and applicable service terms.

### 6.7. Total Cost of Ownership

Compare using identical workloads and protection targets:

~~~text
Periodic TCO =
  compute and database
  + related storage and I/O
  + software licensing and support
  + private interconnect / VPN / network appliances
  + traffic along actual transfer paths
  + backups and recovery target
  + standby/redundant resources
  + monitoring and operations labor
  + migration, testing, and parallel-run costs
~~~

Check each flow independently: app–DB, redo, CDC, backups, and logs. Pricing terms on one flow do not automatically apply to another. Account for both steady-state load and post-outage catch-up.

An option with lower database cost that forces the app to pull huge datasets across cloud boundaries repeatedly can yield higher TCO. Conversely, co-locating the database near the app while over-provisioning infrastructure can also be inefficient.

Budgets, alerts, and tags surface spend. Never assume budget alerts stop resources automatically. Lab cleanup workflows must inspect both live resources and active commercial commitments.

## 7. Verifiable Selection Process

### Step 1: Lock Requirements and Disqualifiers

Document current workload, app location, data size, growth, peak hours, mandatory features, SLOs, RTO/RPO, and budget.

Disqualifiers may include lacking an approved region, missing mandatory features, inability to provision on time, or exceeding approved cost limits.

### Step 2: Build a Shortlist of Viable Options

Typically compare two to three meaningfully distinct options, such as:

- App stays put, database on OCI over private interconnect.
- App stays put, database on corresponding Database@.
- Move both app and database to OCI if goals and constraints permit.

The third option provides a baseline to evaluate the cost of maintaining a cloud boundary. If the app must stay in its current cloud, disqualify that option immediately by constraint instead of scoring it.

### Step 3: Map Data Paths and Failure Domains

For each option, mark locations of app, database, standby, DNS, secrets, backups, and monitoring. Explicitly trace whether each flow crosses region, zone, or cloud boundaries.

Assign each component to an accountable team. If nobody is assigned to handle an alert, the operational design is incomplete.

### Step 4: Execute Representative Tests

Pick transactions that truly drive user experience: login, search, order creation, payments, batch runs, or report aggregation.

Keep datasets, load, and app configs equivalent when comparing. Measure normal load, peak hours, and agreed failure scenarios. Store results per condition, not just overall averages.

### Step 5: Screen First, Then Score

Score only options that passed mandatory conditions. An illustrative weighting set:

| Comparison Criterion | Illustrative Weight |
| --- | ---: |
| Performance and growth headroom | 30% |
| Recoverability and drill results | 25% |
| Workload-based TCO | 20% |
| Existing operational capability | 15% |
| Future portability and adaptability | 10% |

~~~text
Total score = sum(weight × criterion score)

Example scale: 1 to 5.
Total weight: 100%.
Each score must attach explicit evidence or stated assumptions.
~~~

This is an illustrative decision method, not an Oracle evaluation rubric. Never use a high total score to override a mandatory RPO breach or missing required feature.

### Step 6: Finalize Cutover and Rollback Plan

The design needs initial load, delta sync, reconciliation, write-close/open, and app connection update steps.

Explicitly identify until when falling back to the old system remains simple. Once the new system accepts writes, pointing endpoints back to the old source can lose or split data. That stage requires a verified reverse-sync or recovery plan.

## 8. Selection Example for a Sales App Running on Azure

### 8.1. Hypothetical Facts

An enterprise has:

- A sales application required to stay on Azure.
- Roughly 6 TB Oracle Database, heavy PL/SQL, requiring feature parity with current environment.
- Order-creation transaction performs roughly 24 sequential database round trips.
- Order-creation p99 target ≤ 250 ms.
- 30-minute RTO and max 60-second RPO for a defined DR scenario.
- DBA team familiar with OCI, without experience running self-managed databases on Azure IaaS.

Numbers in the example are strictly educational, not real customer data or service benchmarks.

Two initial options:

- **A:** app on Azure, database on OCI over private interconnect.
- **B:** app on Azure, database on Database@Azure in an eligible location.

### 8.2. Pre-Test Estimation

Suppose non-network processing takes ~95 ms and RTT for option A is 8 ms:

~~~text
Simple single-request estimate:
95 + 24 × 8 = 287 ms
~~~

This indicates A risks missing targets and warrants investigating call-count reduction. This is not a p99 calculation: summing illustrative averages cannot derive real system percentiles.

With B, proximity to the app grounds expectations of lower network wait, yet results still require load-test confirmation.

### 8.3. Illustrative Test Results and Decision

Suppose the project team verified features, provisioning prerequisites, and ran load tests. The table below contains simulated example data:

| Item | Option A | Option B |
| --- | --- | --- |
| Mandatory features | Verified met | Verified met |
| Order-creation p99 at target load | 315 ms | 185 ms |
| Target p99 ≤ 250 ms | Failed | Passed |
| RTO/RPO | Needs re-evaluation if app is refactored and retested | Passed in described drill scenario |
| Defined budget | Within limit | Within limit |
| Admin responsibilities | Assigned | Assigned across Azure, OCI, DBA, and app teams |

Under these hypotheticals, **choose B** because it meets the current application's mandatory condition. A is eliminated by performance measurement; no weighted scorecard is needed to justify that decision.

If the team refactors the app to cut round trips and retests A successfully, both can return to TCO and operability comparison. Architectural conclusions depend on measured workloads.

Before real deployment, option B still needs a migration plan and exact HA/DR record for the chosen service type. Achieving RTO/RPO in one drill does not represent every failure mode.

## 9. Hands-On Exercise: Generating Evidence for a Decision

The lab focuses on assessment and verification. Design work can proceed before provisioning paid resources.

### 9.1. Preparing the Workload Profile

Pick a familiar Java or enterprise application. Record:

- Target application cloud and region.
- Database version, size, and features to preserve.
- Three critical business flows.
- SLOs, RTO/RPO, and cost limits.
- Data staleness acceptable to each read flow.

If data is missing, mark “assumption to measure.” Never turn assumed figures into proof the system meets requirements.

### 9.2. Designing Two Options

Draw two diagrams: database on OCI over private interconnect, and Database@ in the application's cloud. Clearly mark VCN/VNet/VPC, CIDRs, DNS, permission layers, backups, standby, and monitoring paths.

If Database@ does not yet support the needed service or location, document the disqualification reason and pick another viable option. Never assume unavailable features merely to finish a diagram.

### 9.3. Testing Connectivity in a Provisioned Environment

The PowerShell example below runs from a host in the app network after replacing endpoint and port with actual service settings:

~~~powershell
$dbHostName = "db-private.example.internal"
$dbListenerPort = 1521

Resolve-DnsName -Name $dbHostName
Test-NetConnection -ComputerName $dbHostName -Port $dbListenerPort
~~~

Hostname is an example; 1521 is an illustrative port. Services or TLS configs may use different ports. Take exact values from database connection details.

A successful TCP test only proves the check reached the chosen port. It does not verify certificates, accounts, service names, schema rights, or transaction performance.

After logging in with an appropriate Oracle client, confirm session context with a read-only SQL query:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name
FROM dual;
~~~

Verify output matches the intended target database before load testing. For Java apps, use JDBC drivers and connection properties matching the chosen version, service, and security mode; keep secrets outside source code.

### 9.4. Controlled Load and Failure Testing

Build a minimum results table:

| Test | Metrics to Collect | Evidence to Retain |
| --- | --- | --- |
| Normal load | p50/p95/p99, throughput, errors | Load profile and measurement duration |
| Peak hours | Pool waits, CPU, I/O, network | Concurrent load and system state |
| Loss of one link | Detection time, dropped requests, recovery | Event timestamps and remaining active path |
| Planned role switch | End-to-end RTO and verification data | Timestamp of last committed tx before fault, post-switch results |
| Restore from backup | Restore duration and integrity | Recovery point, privileges, and keys used |

Run fault simulations only in test environments with agreed scope. For DR, use marker data or client-side transaction ledgers to reconcile transactions confirmed before the outage. Row counts alone cannot prove RPO.

These tests form a learner verification plan; the lesson does not assume they have already run on live systems.

### 9.5. Cleaning Up and Finalizing Results

If resources were provisioned, review databases, storage, backups, endpoints, network links, logs, and dependent resources before closing the lab. Verify what may be deleted, what must stay, and what costs keep accruing.

The lab output is an evidence-backed decision: chosen option, rejected options, evidence, measurement limits, and prerequisites to verify before production.

## 10. Pitfalls to Avoid

| Pitfall | How to Fix the Approach |
| --- | --- |
| Calling any Azure–OCI connection Database@Azure | Identify whether DB sits in an OCI region or service infra inside Azure |
| Assuming Database@ has the same catalog on every cloud | Verify exact services, regions, versions, and topologies |
| Comparing DB prices before checking features | Screen mandatory requirements first, then compare TCO |
| Using high bandwidth to infer low latency | Measure RTT and sequential app round trips |
| Assuming private network meets all security needs | Check permissions, encryption, certificates, secrets, and audits |
| Calling a standby an independent write source | Verify database roles and supported write flows |
| Treating low replication lag as an absolute RPO promise | Check protection modes and data behavior across outage scenarios |
| Checking only the DB after failover | Measure DNS, pools, retries, and end-to-end transaction completion |
| Assuming two clouds always equal two independent failure domains | Audit shared dependencies |
| Pointing endpoints back to old source after target accepts writes | Execute pre-designed delta-handling and reverse-sync procedures |

## 11. Architecture Decision Record Template

Use the short template below in project design documents:

~~~text
Decision: Select multicloud Oracle Database model for <workload>.

Context:
- Application location:
- Database service type and location:
- Feature requirements:
- SLOs and target load:
- RTO/RPO and failure scope:
- Budget:

Options:
- Option 1:
- Option 2:
- Rejected option and unmet conditions:

Evidence:
- Service/region/topology support documentation:
- Load test results:
- Recovery drill results:
- TCO estimate and assumptions:

Decision and Accountability:
- Selected option:
- Rationale:
- Owners for network, IAM, database, application, backup, and alerts:

Implementation:
- Initial load and synchronization:
- Pre-cutover reconciliation:
- Write close/open conditions:
- Rollback plan and cutoff point:
- Triggers requiring re-evaluation:
~~~

A usable record enables others to explain why that model was chosen, which data proves it, and which changes would require revisiting the decision.
