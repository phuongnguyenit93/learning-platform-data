# Selecting Exadata Based on Performance and Data Residency Requirements

## 1. Goal of the Architectural Decision

In the **Exadata and Cloud@Customer** chapter of the Oracle Cloud Infrastructure (OCI) track, selecting Exadata must start from system requirements: how fast transactions must be, where data is permitted to reside, where applications connect from, and who holds operational responsibility.

This lesson walks through moving from those requirements to a verifiable decision. The scope covers evaluating Oracle Database workloads, placement of primary and copies, network connectivity, scalability, availability, permissions, monitoring, and cost.

After completing this lesson, you will be able to:

- Distinguish the need for higher performance from the need to change deployment location.
- Identify metrics to measure before choosing an Exadata configuration.
- Compare Exadata Database Service on OCI against Exadata Database Service on Cloud@Customer under real constraints.
- Design tests to confirm application latency, capacity, and behavior when part of the resources is unavailable.
- Write a selection decision documenting assumptions, evidence, and conditions that trigger a review.

The guiding principle is to **eliminate options that fail mandatory constraints first, then optimize among the viable candidates**. A high-throughput configuration cannot compensate for placing data outside the scope approved by the organization.

## 2. Separate Four Questions Often Lumped Together

### 2.1. Do You Need Exadata?

Exadata integrates software and infrastructure optimized for Oracle Database. However, "the database is slow" is not by itself proof that you must move to Exadata.

Identify the root cause:

- SQL reading excessive data or using poor execution plans.
- CPU, memory, or I/O capacity shortages at peak load.
- Lock contention, hot blocks, or transactions holding locks too long.
- Applications making too many sequential network calls to the database.
- Multiple workloads contending for the same resources.
- Current infrastructure unable to meet growth and availability requirements.

If the root cause is hundreds of sequential database calls per request, speeding up database execution solves only part of the problem. If the root cause is flawed SQL logic, fix the logic before using measurements for sizing.

An Exadata evaluation should keep a baseline: the current system after reasonable tuning, and a smaller Oracle Database option if it can satisfy requirements. For moderate workloads with low growth that do not need Exadata capabilities, another option may fit better both in capacity and operations.

### 2.2. Which Operational Model Do You Need?

Even on the same Exadata technology, self-management scope varies. Exadata Database Service is a co-managed service; do not interpret it as Oracle operating the entire application and data stack on the customer's behalf.

The project team must clarify who manages databases, access settings, customer-scoped patches, backup schedules, recovery checks, and application connectivity. If a different level of automation is needed, evaluate the corresponding service separately rather than inferring from hardware naming.

### 2.3. Where Will Data and Applications Reside?

A database close to end users is not necessarily close to the application. Users may be in Vietnam while application servers sit in a different cloud region. The application-to-database network hop is often a direct component of request latency.

Distinguish:

- End-user location.
- Application server and connection pool locations.
- Primary database location.
- Standby, backups, restore-drill environments, and analytics data locations.
- Key management, monitoring, and related log locations.

### 2.4. Which Configuration and Scale Should You Choose?

Select resources only after determining the operational model, location, and workload. The configuration must cover peak load, growth, background jobs, and committed degraded-capacity scenarios.

Do not size by database size alone. Two 10 TB databases can have completely different demands: one performs short key lookups while the other continuously scans and aggregates terabytes of data.

## 3. Distinguish Deployment Options

| Option | Infrastructure Location | Characteristics to Include in Evaluation |
| --- | --- | --- |
| Exadata Database Service on Dedicated Infrastructure in OCI | Dedicated customer Exadata infrastructure in an OCI cloud region offering the service | Application connectivity, resource availability, service limits, and co-management responsibilities |
| Exadata Database Service on Exascale Infrastructure in OCI | Resources from shared cloud infrastructure under the service model | Required isolation level, provisioning model, starting scale, and regional availability |
| Exadata Database Service on Cloud@Customer | Infrastructure in customer data center or service-designated facility | Site conditions, OCI management connectivity, on-site operations, and outbound data flows |
| Self-deployed Exadata Database Machine | Location chosen and prepared by the organization | Procurement, support, and operational model differ from cloud services |

Oracle describes service options including dedicated, shared Exascale, and Cloud@Customer. These options differ in location and infrastructure provisioning; confirm availability at the target location. [Exadata Database Service FAQ](https://www.oracle.com/engineered-systems/exadata/database-service/faq/).

This table does not mean every combination of version, topology, and service is equivalent. Nor should the term "Cloud@Customer" be used for a customer-purchased Exadata Database Machine sitting in a server room; those are distinct service and responsibility models.

Outside OCI, options exist to deploy Exadata in certain other cloud environments. When applications live there, supported options can enter the candidate list; evaluate actual placement, features, and service terms separately. This lesson focuses on the selection process within OCI and Cloud@Customer contexts.

Hardware generation specs, compute billing units, shapes, minimum allocations, and pricing can change. The decision record must cite the exact service, generation, region, and quote date; never treat an outdated spec sheet as a deployment commitment.

## 4. Translate Business Requirements into a Workload Profile

### 4.1. Identify Work Types and When They Occur

An inventory should separate OLTP, reporting, batch, ETL, and operational tasks.

| Component | Information to Collect | Rationale |
| --- | --- | --- |
| Online transactions | Transactions/sec, concurrent requests, p95/p99 response time, error rate | Assess serving capacity and tail latency |
| Critical SQL | Execution frequency, elapsed time, CPU time, logical/physical reads, plans | Identify what truly consumes resources |
| Batch and ETL | Start times, completion windows, read/write volume, parallelism | Detect overlap with OLTP loads |
| Data | Used space, growth rate, hot working set, LOBs, and indexes | Size storage, memory, and cache |
| Redo and commits | Redo generation rate, commit frequency, related wait events | Evaluate write paths and data protection needs |
| Operations | Backups, restores, stats gathering, maintenance, test clones | Avoid sizing solely for application traffic |
| Network | RTT, jitter, packet loss, usable throughput, round-trip count | Evaluate application-to-database placement |

p95 is the threshold that roughly 95% of observations do not exceed; p99 is the same for 99%. State the transaction type, measurement window, load level, and sample count. A single p95 mixing logins, searches, and report exports hides which transaction is violating targets.

Open sessions do not equal sessions actively demanding CPU. A connection pool holding many idle connections waiting for work does not prove the database needs more compute.

### 4.2. Capture Full Business Cycles

Do not size from a single day's average CPU. Cover all impactful cycles:

- Daily peak hours.
- Period-end, month-end, or financial close.
- Traffic campaigns and bulk data loads.
- Backups overlapping reporting or ETL.
- Post-maintenance periods while caches warm up.
- Scenarios missing a node or undergoing partial infrastructure maintenance.

Use OS telemetry, application traces, database metrics, and authorized observability tools. If using AWR, ASH, SQL Monitor, or tools with specific licensing conditions, verify usage rights under your service and contract.

### 4.3. Set Measurable Targets

Hypothetical requirements example:

~~~text
Order creation transaction:
- 1,200 transactions/sec at target load.
- p95 at most 150 ms.
- p99 at most 400 ms.
- Error rate at most 0.1% within the test window.
- Measured from application servers across the intended production topology.

End-of-day batch:
- Processes representative dataset in at most 45 minutes.
- Runs concurrently with agreed online load.
- Online load continues meeting its own thresholds.

Growth:
- Data grows 25%/year in the baseline scenario.
- Includes a high-growth scenario and a procedure to provision additional resources.
~~~

These figures are illustrative design data, not Oracle specifications or SLAs. They must be signed off by business and engineering teams before a PoC.

## 5. Evaluate Performance Benefits by Bottleneck

### 5.1. OLTP Requires Testing Reads, Writes, and Contention

For OLTP, useful measurements include short SQL execution times, commit latency, index lookups, concurrent transaction count, and stability as load climbs.

Exadata features database servers, intelligent storage servers, and an internal interconnect optimized for Oracle Database. Still, concrete gains depend on access patterns, caching, allocated resources, and application design. [Exadata Architecture](https://www.oracle.com/database/technologies/exadata/architecture/).

Do not extrapolate HTTP request latency solely from published internal I/O latency. A request also includes queuing, Java processing, multiple SQL calls, network round-trips, and external integrations.

Issues such as a single row updated sequentially or transactions holding locks too long require separate analysis. Adding hardware does not remove serialization bottlenecks.

### 5.2. Analytics and Data Scans

Smart Scan can offload portions of SQL processing down to storage servers, reducing data sent back to database servers for eligible operations. This provides technical justification for testing Exadata on heavy scan and analytics workloads. [Exadata Smart Scan](https://www.oracle.com/database/technologies/exadata/software/smartscan/).

Not every SQL statement uses Smart Scan or benefits equally. During a PoC, inspect execution plans, actual bytes read, observed offload ratios, and elapsed time at target concurrency.

Do not build a benchmark around one scan-friendly query and use it to represent an application dominated by short key lookups.

### 5.3. Multi-Database Consolidation

Another goal is placing multiple databases on shared infrastructure. Benefits can come from better resource utilization and standardized operations, provided contention is controlled.

Build a combined load schedule:

~~~text
09:00–11:00: online transaction peak
10:00–12:00: management reporting
22:00–01:00: batch and ETL
23:00–03:00: backup
Month-end day: batch runs into morning hours
~~~

Evaluate resource management and isolation at layers supported by the service. Splitting databases into multiple PDBs or VM clusters does not make total CPU, memory, and I/O infinite.

Consolidation units must also account for admin privileges, upgrade schedules, blast radius, and data residency rules. Two databases with incompatible residency requirements should not be merged just because their combined size fits one box.

## 6. Application Placement Can Decide Performance Outcomes

### 6.1. Account for the Cost of Sequential Round-Trips

A simple model for a request:

~~~text
Approximate request time =
    application processing
  + database processing
  + total network round-trip time
  + queuing and other dependencies
~~~

Suppose a request makes 30 sequential application-to-database round-trips. With a fixed modeled RTT of 12 ms, network waiting alone is approximately:

~~~text
30 × 12 ms = 360 ms
~~~

If the application is placed near the database and modeled RTT drops to 1 ms, that term becomes 30 ms.

This illustrates sequential round-trips, not a prediction of real-world p95 or p99 latency. Never sum individual percentiles to derive end-to-end request percentiles; measure complete requests.

The result points to a key architectural insight: faster SQL execution in the database may fail to meet user-experience goals if the application still crosses a distant network dozens of times.

### 6.2. Three Approaches to Compare

1. Place application servers close to the database at an approved site.
2. Reduce round-trips via batching, fetch-size tuning, operation consolidation, or data-access refactoring.
3. Keep applications on-premises and place the database near immovable dependencies.

For Java applications, check how many SQL statements the ORM emits per request, N+1 patterns, connection pools, result-set sizes, and connection hold durations. Migrating the database without inspecting this layer easily leads to wrong conclusions about the platform.

Do not blindly raise batch or fetch sizes: measure memory impact, transaction size, lock duration, and how much data the application actually consumes.

### 6.3. Private Circuits Do Not Erase Distance

FastConnect can be part of OCI connectivity, yet the name of a connectivity service does not guarantee application latency targets will be met. Latency still depends on physical geography, actual routing, equipment, congestion, and network design.

For each candidate, measure:

- RTT and jitter from actual application servers.
- Usable throughput for bulk transfers.
- Behavior when a circuit or link fails.
- DNS, routing, firewalls, and reachability to required endpoints.
- Performance when backups, replication, and application traffic share the circuit.

Exadata services in OCI require designing VCNs, client networks, backup networks, and routes to associated services per official requirements. [Exadata Cloud Infrastructure Network Setup](https://docs.oracle.com/en-us/iaas/exadatacloud/doc/ecs-network-setup.html).

## 7. Determine Data Residency by Mapping Every Copy

### 7.1. Distinguish Requirement Types

In this lesson:

- **Data residency**: where data or any copy physically resides.
- **Access scope**: who can access it, from where, and via which mechanism.
- **Control authority**: which organization manages keys, permissions, changes, and operations.
- **Auditability**: what evidence proves those requirements are enforced.

These are architectural evaluation dimensions. A region name, TDE encryption, or a data center street address does not by itself prove full governance compliance.

Do not translate legal regulations into technical rules on your own. Policy owners must provide an approved scope—for example, "business data and all recoverable copies must remain within two approved sites." Architecture then turns that scope into configurations and evidence.

### 7.2. Inventory Copies Beyond the Primary

| Data / Copy Type | Question That Must Be Answered |
| --- | --- |
| Primary datafiles, redo, and temporary data | Where do they reside during normal operation? |
| Standby and shipped redo | Is the DR location within approved scope? |
| Backups and long-term archives | What are the destination, storage region, retention, and secondary copies? |
| Restore drills and dev/test environments | Is real data ever restored elsewhere? |
| Exports, ETL, reports, and caches | Does data flow onward to analytics platforms or integrations? |
| Logs, audit trails, traces, and support bundles | Do they contain SQL, bind values, PII, or business data? |
| Keys and access secrets | Where do they reside, who controls them, and how are they recovered? |
| Service metadata and telemetry | What content is sent to management systems, under which settings? |

For each flow, record at least: data type, source, destination, purpose, protocol, owner, and configuration evidence.

Neither lump all telemetry into business data nor assume telemetry is always non-sensitive. Identify exact payload contents and handling mechanisms.

### 7.3. Cloud@Customer Must Be Evaluated at the Right Boundaries

With Cloud@Customer, the database VM cluster runs on hardware inside the customer's data center, while control plane servers connect to an OCI region for automation and management. Keep these two flows distinct in your design. [Exadata Cloud@Customer Networking](https://docs.oracle.com/en/engineered-systems/exadata-cloud-at-customer/eccid/exacc_network.html).

Keeping the primary on-premises does not automatically prevent backups from leaving for the cloud. Cloud@Customer supports different backup targets; using OCI Object Storage requires appropriate connectivity, whereas on-site NFS or ZDLRA carries different requirements. [Cloud@Customer Network Requirements](https://docs.oracle.com/en-us/iaas/exadata/doc/ecc-network-requirements.html).

Therefore, never describe Cloud@Customer as a completely air-gapped system by default. Nor should you assume what continues or stops if OCI connectivity drops; verify each feature's behavior from documentation, configuration, and testing.

Customers must control access to networking, VMs, and databases within their responsibility scope. Service-level controls do not replace database user privileges or application authorization. [Cloud@Customer Security Guide](https://docs.oracle.com/en-us/iaas/exadata/doc/ecc-secguide.html).

### 7.4. Diagram the Decision Flow Before Picking a Deployment Site

~~~mermaid
flowchart TB
    REQ["Business requirements and verified data residency scope"]
    INV["Inventory: data, copies, applications, integrations"]
    LOC["Candidate locations"]
    GATE{"Meets mandatory requirements?"}
    POC["Measure applications, workloads, network, and recoverability"]
    COST["Calculate total system cost"]
    DEC["Decision and review triggers"]
    REV["Adjust plan or requirements"]

    REQ --> INV
    INV --> LOC
    LOC --> GATE
    GATE -->|"Yes"| POC
    GATE -->|"No"| REV
    POC --> COST
    COST --> DEC
    REV --> LOC
~~~

Mandatory requirements may include location, control authority, version compatibility, connectivity, or delivery timeline. Only candidates passing this gate should be scored by weighted preferences.

## 8. Multi-Dimensional Resource Sizing

### 8.1. Compute and Memory Must Be Measurement-Driven

Do not copy legacy server core counts onto a new quote and call it complete sizing. Factor in CPU generation, service allocation units, concurrency, per-core performance, and tuned workloads.

Separate these figures:

- Physical infrastructure resources.
- Resources allocated to the VM cluster.
- Compute enabled or billed under the service.
- Resources usable after a component drops out of service.
- True demand of concurrently running databases.

Adding compute does not scale every related resource proportionally. Verify memory allocation, storage, and scaling mechanics for the exact service. Oracle documents scaling and configuration options for Exadata Dedicated Infrastructure separately. [Dedicated Infrastructure Service Description](https://docs.oracle.com/en-us/iaas/exadatacloud/doc/exa-service-desc.html).

For memory, evaluate SGA, PGA, OS, operational tasks, and parallelism. Hot working sets and sort/hash memory matter more than forcing the entire database into RAM.

### 8.2. Storage Must Use Consistent Units and Tiers

Distinguish:

- Raw device capacity.
- Usable capacity after platform protection and allocation overhead.
- Capacity provisioned to a database or storage area.
- Actual used capacity.
- Headroom reserved for growth, temporary spikes, and operations.

Do not compare raw TB from one proposal against usable TB from another. Also do not treat advertised flash/cache capacity as general-purpose data capacity.

Hypothetical sizing example—all numbers below use decimal TB at the same **usable** tier:

~~~text
Current business data:                            12.00 TB
25%/year growth over 3 years:
    12 × 1.25^3                                   23.44 TB

Projected TEMP at design time:                     3.00 TB
Projected UNDO:                                    1.00 TB
Projected local recovery area:                     6.00 TB
Illustrative total usable demand:                 33.44 TB

If targeting max 80% utilization:
    required usable capacity ≈ 33.44 / 0.80       41.80 TB
~~~

This is neither an off-the-shelf Oracle configuration nor a universal reserve ratio. In practice, reconcile every actual storage pool, platform limits, and service-mandated reserve/rebalance margins to avoid double-counting or omissions.

Standby and off-box backups must be sized separately. Do not take 41.80 TB and claim all copies are covered.

### 8.3. Sizing for Degraded Capacity

Suppose a PoC normalizes capacity into an effective CPU unit for the same workload:

~~~text
Peak load demand:                    84 units
Two nodes, each providing:           64 units

Normal:                             128 units
After losing one node:               64 units
~~~

The configuration suffices in normal operation but fails peak load if only one node survives.

With a three-node layout of the same per-node capacity, losing one node leaves 128 units. At a 70% target utilization ceiling, the demand budget is 89.6 units, exceeding the 84-unit example.

This is a conceptual capacity exercise, not an OCPU/ECPU conversion or purchasable shape guarantee. A PoC must still verify load distribution, per-node limits, and application behavior; workloads do not always balance perfectly.

### 8.4. Core Counts Do Not Substitute for Storage Throughput

For mixed OLTP and batch workloads, verify concurrently:

- Read/write latency at required load.
- IOPS and I/O sizes.
- Scan, bulk load, and backup read throughput.
- Redo generation rate and replication capacity.
- Degradation during background tasks or component loss.

An option with spare CPU but saturated storage or networking can still violate p99. Sizing should identify which resource is expected to hit its ceiling first and the corresponding scaling action.

## 9. Availability Drives Site Selection

Primary placement cannot be finalized without selecting the recovery location.

Answer:

- Do primary and standby share power, racks, infrastructure, or network circuits?
- Is the DR location legally/policy-permitted to store the same data?
- Can applications fail over to that location?
- Does the standby have capacity to absorb target load?
- Are backups stored outside the primary failure domain?
- Can operations access keys and recovery tools if the primary site is lost?

RPO is acceptable data loss; RTO is service restoration time per agreed milestones. Put both into the requirements matrix per scenario rather than writing "HA required."

RAC, Data Guard, and backups protect different scopes. In the selection decision, verify the chosen option provides sufficient locations, capacity, networking, and budget for every required mechanism.

For example, picking Cloud@Customer at site A for on-premises primary residency is still incomplete if a site-loss goal requires a standby at site B while B is unready or unauthorized to hold the data.

Conversely, picking an OCI region for the primary does not prove RTO if applications and fallback circuits still depend on the lost customer data center.

## 10. Deployment Prerequisites and Operational Ownership

### 10.1. For Cloud@Customer

Inspect the site before locking schedules:

- Floor space, delivery path, and floor loading.
- Power, redundant feeds, grounding, and cooling.
- Cabling, uplinks, IP space, VLANs, DNS, NTP, and required routes.
- Security policies permitting management connectivity to OCI.
- Physical access, maintenance, and incident coordination procedures.

Physical requirements vary by configuration and generation; survey against current documentation. [Cloud@Customer Site Requirements](https://docs.oracle.com/en-us/iaas/exadata/doc/ecc-site-requirements.html).

Insufficient power or blocked management connectivity is an unmet prerequisite, not a flaw that high benchmark scores can offset.

### 10.2. For Exadata in OCI

Verify regional service and resource availability, quotas/limits, VCN/subnet design, application connectivity, IAM, DNS, and paths to required services.

Do not use successfully launching a small VM as proof that desired Exadata infrastructure can be provisioned immediately. Confirm real candidate availability and project lead times.

### 10.3. Assigning Responsibilities

A project responsibility matrix should specify:

| Work Area | Question to Lock Down |
| --- | --- |
| Infrastructure and platform maintenance | What does Oracle handle, and what must the customer prepare or coordinate? |
| Customer-scoped databases and software | Who schedules, verifies compatibility, and validates post-change? |
| Networking | Which teams manage VCNs, private circuits, on-site firewalls, and DNS? |
| Backup and recovery | Who sets retention, verifies protection points, and runs restore drills? |
| Keys and access | Who manages IAM, database privileges, keystores, and audits? |
| Applications | Who updates connection strings, retries, timeouts, and validates transactions? |
| Monitoring | Who receives alerts, responds, and tracks service targets? |

The matrix organizes project execution; it does not replace each service's official responsibility boundaries.

Automation via Console/API or declarative tools can standardize deployments. Even so, an owner must still maintain configuration, verify outcomes, and manage post-migration changes.

## 11. Plan a PoC with Pre-Agreed Pass Criteria

### 11.1. Choose Representative Data and Workloads

A useful PoC reflects the intended production system:

- Dataset large enough to exhibit hot/cold working sets, distribution, and skew.
- SQL, transaction mix, and read/write ratios matching critical periods.
- Client counts, arrival rates, and run duration sufficient for steady-state observation.
- Matching intended application-to-database topology.
- Concurrent jobs such as batch, backups, or ETL.
- Security and network settings matching target production.

If real data is disallowed in the PoC environment, use synthetic or appropriately masked data. Check whether masking significantly alters value distribution, compression ratios, or query behavior.

### 11.2. Hold Comparison Conditions Constant

Record for every test run:

~~~text
Candidate and location:
- Service, region/site, infrastructure generation, provisioned configuration.

Database:
- Version, patches, relevant parameters, schema, and statistics.
- Execution plan characteristics of key SQL statements.

Application:
- Version, JVM, pool, access configuration, and client placement.

Data and load:
- Size, distribution, transaction mix, arrival rate, concurrency.
- Warm-up duration, measurement duration, and background activity.

Results:
- Successful throughput, p50/p95/p99, error rate.
- CPU, memory, I/O, network, redo, and top wait events.
~~~

Do not compare an isolated run on candidate A against a run overlapping backups on B and attribute the entire gap to deployment location. When mandatory conditions differ, document the differences and measure their impact.

### 11.3. Required Test Phases

| Phase | Objective | Evidence |
| --- | --- | --- |
| Baseline | Know how the current system performs | Results on the same business flows and comparison data |
| Normal load | Confirm day-to-day targets | Throughput, percentiles, errors, and resource usage |
| Peak load | Find saturation limits as demand rises | Point where queuing, errors, or threshold breaches begin |
| Mixed load | Check contention | OLTP alongside scheduled batch/backups |
| Degraded resources | Verify serviceability under chosen failure scope | Application results with a component offline |
| Recovery | Confirm data currency and restoration time | Restore/role transition and post-recovery transactions |
| Scaling | Test scaling operations and limits | Execution duration, impact, and post-change results |

Perform fault-injection tests only within approved test environments and plans. Never run destructive component tests on production just to fill in a scorecard.

### 11.4. Evaluate Results Against Pass Criteria

Example of two hypothetical test results for order creation:

| Metric | Target | Candidate A | Candidate B |
| --- | --- | --- | --- |
| Successful throughput | At least 1,200 transactions/sec | 1,250 | 1,800 |
| p95 | At most 150 ms | 130 ms | 190 ms |
| p99 | At most 400 ms | 320 ms | 470 ms |
| Error rate | At most 0.1% | 0.03% | 0.02% |

If all four rows are mandatory requirements, B fails despite higher throughput. Do not pick B just because it "processes more transactions."

If A passes only under normal conditions but fails the committed degraded-capacity scenario, A also lacks sufficient evidence. Adjust sizing, agree on load-shedding rules for that scenario, or reconsider the option.

### 11.5. Avoid Conclusions Beyond the Measured Data

Common pitfalls:

- Runs too short to reveal backlogs or resource exhaustion.
- Measuring only averages while ignoring p99 and errors.
- Running a dataset that fits entirely in cache and extrapolating to a much larger dataset.
- Backing off request rates when the system slows without recording dropped work.
- Picking one favorable SQL query instead of the real transaction mix.
- Failing to test the application from its real placement.
- Omitting patch levels, plans, or resource management settings.

Valid conclusions stay bounded to what was actually tested. A 2 TB PoC does not automatically prove behavior at 40 TB; explain scaling factors and plan follow-up verification.

## 12. Calculate Total Solution Cost

### 12.1. Compare Apples to Apples

Do not compare cloud compute bills solely against on-premises hardware purchase prices. Use the same time horizon, same workload, and same protection level.

A calculation framework:

~~~text
Total solution cost =
    infrastructure and compute
  + licenses/subscriptions and related support
  + storage for primary, standby, backups, and test environments
  + connectivity and data transfer
  + operations, monitoring, security, and drills
  + site requirements if applicable
  + migration, validation, and parallel-run window
~~~

Clearly mark what is already included in a subscription to avoid double-counting. For BYOL, confirm entitlements cover the exact service, quantity, features, production/standby, and related environments under applicable terms.

Costs and licensing rules must come from official quotes, service documentation, and active contracts. Do not infer legal entitlement simply because a feature ran during a PoC.

### 12.2. Separate Fixed from Variable Costs

In a dedicated or on-premises model, reducing active compute does not necessarily reduce total infrastructure cost proportionally. In other provisioning models, billable components and minimums may differ.

The financial record should separate:

- Committed spend or baseline platform costs that must be sustained.
- Costs varying with compute/storage/traffic.
- Step-function cost jumps when crossing current capacity limits.
- One-time vs. recurring costs.
- Primary costs vs. full-service recovery costs.

Model three demand scenarios: low, baseline, and high growth. For each scenario, note when scaling is triggered and how additional capacity will be provisioned.

### 12.3. Use Meaningful Unit Economics

You can calculate:

~~~text
Cost per 1 million compliant transactions =
    cost for the period
    / successful transactions meeting target in the period
    × 1,000,000
~~~

Do not use this metric to mask unmet mandatory requirements. A cheap candidate that violates data residency or p99 targets is still unviable.

For reporting workloads, the unit can be cost per batch cycle completing within its window. Pick units matching the business and keep assumptions consistent.

## 13. Selection Matrix and Two Decision Examples

### 13.1. Step One: Elimination Gate

| Mandatory Requirement | How to Verify | If Unverified |
| --- | --- | --- |
| Primary and copies within approved scope | Data-flow map, target config, and policy sign-off | Not yet eligible for selection |
| Supported version, features, and integrations | Service docs, inventory, and PoC | Must close gaps first |
| Latency and capacity meet targets | PoC results on intended topology | Adjust or eliminate |
| Site and connectivity ready | Site survey, network test results, deployment plan | Cannot commit go-live date |
| Feasible RPO/RTO | Design and drills within target scope | Insufficient evidence |
| Valid licensing and resource availability | Contract, entitlement, and service confirmation | Cannot lock configuration/cost |

Use statuses **Pass**, **Fail**, and **Unverified**. Never promote "Unverified" to "Pass" out of schedule convenience.

### 13.2. Step Two: Score Candidates Passing Mandatory Requirements

Hypothetical weights and scores on a 1–5 scale:

| Priority Criterion | Weight | OCI Dedicated, App Moved Near DB | Cloud@Customer, App On-Premises |
| --- | --- | --- | --- |
| Performance and scaling headroom | 35% | 4 | 5 |
| Fit with connectivity and dependencies | 20% | 4 | 5 |
| Fit with operational capabilities | 20% | 4 | 3 |
| Cost under baseline scenario | 15% | 4 | 2 |
| Deployment lead time | 10% | 5 | 2 |
| Weighted score out of 100 | 100% | 82 | 77 |

Formula: sum of `weight × score / 5`, with weights expressed on a 100-point scale.

Scores reflect a hypothetical project evaluation, not a universal product ranking. For an organization with an existing prepared site and operations team, scores could invert completely.

Run sensitivity analysis: if reasonable weight changes flip the winner, explicitly state which priorities drive the decision.

### 13.3. Example A: Data Must Stay in Two Approved Data Centers

Suppose the organization confirms:

- Primary, standby, backups, and restored copies with real data may reside only at site A or B.
- Applications have many internal dependencies that cannot move yet.
- Management and support traffic must undergo separate security review.
- Workload has proven need for Exadata capabilities.

Evaluation path:

1. OCI public regions outside the approved location list fail the residency gate regardless of strong PoC performance.
2. Cloud@Customer at site A advances as a candidate for further evaluation.
3. Backup/DR design must stay within A/B as required, using service-supported options.
4. Verify site B, network paths, keys, and recovery procedures.
5. Vet control plane, telemetry, log, and support flows before concluding the overall solution is compliant.

A sound initial conclusion is "Cloud@Customer has sufficient basis to proceed to PoC and security vetting," not "Cloud@Customer automatically satisfies all requirements."

If the site fails readiness or mandatory flows remain unapproved, adjust the plan or clarify requirements. Never bypass mandatory gates to force a product choice.

### 13.4. Example B: Approved Region Allowed and Applications Can Move

Assumptions:

- Data residency permits a verified OCI region.
- Java applications can deploy near the database.
- Peak loads are high and growing.
- The organization prefers not to build new physical site infrastructure.

Exadata on OCI can enter the PoC alongside corresponding VCN, IAM, networking, and DR designs. If dedicated physical isolation is not required, evaluate Exascale options as well; if dedicated isolation is mandatory, keep the dedicated candidate.

Base the decision on application behavior after moving near the database, not on RTT from the old on-premises application servers.

Still account for application migration costs, integration updates, links back to remaining on-premises systems, and all data copies. Database cloud approval does not automatically optimize the rest of the hybrid architecture.

## 14. Migration Planning Is Part of the Selection

### 14.1. Verify Data Transfer Feasibility

Determine:

- Transfer method compatible with source, target, and downtime limits.
- Actual bytes to transfer, achievable compression, and usable bandwidth.
- Rate of ongoing data changes during transfer.
- Data validation, connection cutover, and application handling.
- Retention window for the legacy system and rollback triggers.

Example: transferring 20 TB initially over 1 Gbit/s usable throughput, using decimal units and ignoring other overhead:

~~~text
Modeled minimum time =
    20 × 10^12 bytes × 8 / 10^9 bits/sec
    = 160,000 seconds
    ≈ 44.4 hours
~~~

This is neither estimated downtime nor total migration duration. Preparation, read/write overhead, validation, incremental sync, and cutover still add time.

If data keeps changing, synchronization must have enough headroom to catch up. An option that works well in steady state may still miss project deadlines if the migration path cannot finish on schedule.

### 14.2. Rolling Back After New Writes Occur

A rollback plan cannot be just flipping the connection string back to the old database. After cutover, the new database may have accepted transactions absent from the old source.

Define:

- Up to what milestone rollback is possible without data reconciliation.
- Beyond that milestone, how new data will be brought back or reconciled.
- Who decides to halt, roll back, or push forward with remediation.
- How to handle integrations that already fired external transactions.

Rollback feasibility and parallel-run duration must factor into selection cost, schedule, and risk.

## 15. Lab: Writing a Selection Decision Package

This exercise produces a self-contained architectural decision for an Oracle Database workload. The items below define the required template; no extra files outside the lesson are needed to understand the workflow.

### 15.1. Minimum Input Set

Collect or clearly document simulated inputs for:

1. Three critical business flows and response-time targets.
2. Normal load, peak load, and batch/backup schedules.
3. Storage volume, growth, hot working set, and redo rate.
4. Application placement, dependencies, and network metrics.
5. Residency scope for primary, standby, backups, test copies, and logs.
6. Per-scenario RPO/RTO and operational capabilities.
7. Delivery deadline, site readiness, and scoped budget.

When using hypothetical inputs, keep them distinct from measured results. Never paste brochure specs into a PoC results column.

### 15.2. Execution Sequence

- Identify candidates matching residency and operational model requirements.
- Check mandatory gates, explicitly flagging unverified items.
- Build initial sizing with assumptions and growth scenarios.
- Design the PoC, pass criteria, and degraded-resource scope.
- Calculate costs over the same horizon and protection level.
- Compare candidates, state selection conditions, and outline migration.
- Set review triggers tied to observed metrics.

### 15.3. Architectural Decision Template

~~~text
Decision title:
Platform and location selection for database <system name>.

Context:
Workload, application topology, and problem to solve.

Mandatory requirements:
Data residency, compatibility, service targets, control requirements.

Candidates:
Services, locations, and configurations evaluated.

Evidence:
PoC results, network measurements, site survey, capacity confirmation,
recovery verification, and scoped quotes.

Selection:
Chosen option and rationale tied to evidence.

Trade-offs:
Cost, dependencies, scaling limits, and operational responsibilities.

Pre-deployment conditions:
Open items, owners, and target resolution milestones.

Migration:
Method, cutover, data validation, and rollback handling.

Review triggers:
Load, growth, application placement, policy, or resource provisioning
capabilities exceeding documented assumptions.
~~~

A strong record lets readers distinguish known facts, measured data, and remaining assumptions. Where evidence is missing, keep status as unverified rather than phrasing it as a product guarantee.

## 16. Operating After the Choice Is Made

Selection does not end at database provisioning. Build dashboards around the exact metrics used in the decision: business throughput, p95/p99, errors, CPU, memory, I/O, network, storage, backups, and recovery target readiness.

Bind resource modification rights to appropriate IAM and database privileges; retain audit trails of changes. When using automation or declarative infrastructure, clearly define which settings are managed where so tools do not overwrite each other.

Set alerts before hitting tested limits. When reality diverges from assumptions, use the workload profile to decide between SQL tuning, reducing network round-trips, adding resources, splitting workloads, or changing deployment location.

The right Exadata choice is the option that **meets application targets in approved locations, provides sufficient recoverability, and operates within an approved budget**. Reaching that conclusion requires measurements, data mapping, and concrete ownership—not just a platform name or peak headline numbers.
