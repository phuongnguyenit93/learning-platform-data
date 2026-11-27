# Selecting locations for latency, availability, and data residency

Choosing where to deploy is a critical architectural decision when building systems on Google Cloud. A region closer to users can deliver faster responses, but the system must also withstand failures, satisfy data residency requirements, and operate within budget constraints. This decision affects Compute Engine, Google Kubernetes Engine (GKE), Cloud Run, storage services, databases, VPC, networking, and operations.

In the **Resource Hierarchy and Locations** chapter, we analyze three questions:

1. **Latency:** How long does it take users and application components to exchange data?
2. **Availability:** How long does the system keep serving or take to recover when a zone or an entire region experiences an outage?
3. **Data residency:** Where are primary data, replicas, backups, and processed data permitted to reside?

After this lesson, you will be able to distinguish Google Cloud resource location scopes, build a candidate region list, measure meaningful latency, and reason about redundancy solutions alongside data constraints.

## 1. Resource location is not project location

Google Cloud organizes governance resources as **organization → folder → project → resource**. This structure serves policies, IAM permissions, and cost management. A project does not automatically pin all resources inside it to a single region; each service has its own location scope.

| Concept | Meaning in design | Key considerations |
| --- | --- | --- |
| **Region** | Geographic area for placing regional services. | Services, configurations, pricing, and quotas can vary across regions. |
| **Zone** | Deployment domain within a region, used for resources such as Compute Engine VMs. | Zones within a region isolate certain failure types but still share region-level risk. |
| **Dual-region / multi-region** | Location types supported by certain services to store or replicate data across a scope broader than one region. | Replication mechanics, latency, failover behavior, and limits vary by service. |
| **Global resource / global endpoint** | Resources or entry points with global scope, such as a VPC network or certain load balancers. | Global does not guarantee customer data is stored in a single chosen place or everywhere. |
| **Edge / CDN** | Points of presence near visitors to accept requests or cache content. | Edge location differs from backend, database, and cached-content origin locations. |

For example, a system might use a global VPC network, regional subnets, a VM in one zone, Cloud Run in another region, and a Cloud Storage bucket with a separately configured location. Project-level IAM can grant access to these resources without forcing them into the same location.

| Service | Location typically selected | Notes |
| --- | --- | --- |
| Compute Engine | Zone for VMs; some instance groups can span multiple zones | Avoid relying on a single VM or zone when HA is required. |
| GKE | Zonal or regional cluster; node placement also matters | A regional cluster helps survive zone failures; it does not replace region-wide disaster recovery. |
| Cloud Run | Region to run the service | Consider the location of databases and heavily called services. |
| Cloud SQL | Region and zone, HA/replica settings per configuration | In-region HA and cross-region redundancy address different failure modes. |
| Cloud Storage | Region, dual-region, or multi-region depending on location type | Check replication rules, data placement, and data transfer fees. |
| BigQuery | Location of the dataset and related jobs | Do not assume all queries or transfers across locations are permitted and direct. |
| Cloud Spanner | Regional or multi-region instance configuration | Consider replica placement, consistency, latency, and cost. |

Supported products, machine types, configurations, and features per region can change. Having Compute Engine in a region does not mean every Google Cloud service supports the configuration you need there.

## 2. Latency: measure the entire request path

### 2.1. The region closest to users is not always the fastest for the app

Response time includes network transit from the client, load balancer/edge point, application processing, database queries, calls to dependent services, and returning the result. For sequential steps, it can be approximated as:

**T response ≈ T client network + T backend + sum of dependent service wait times + T response return.**

This is a mental model for finding bottlenecks, not a rigid formula: parallel calls, caching, payload size, and connection reuse all affect the outcome.

~~~mermaid
flowchart LR
    U["Users"] --> E["Entry point / load balancer"]
    E --> A["API in region A"]
    A --> D[("Database in region A")]
    A -. "Cross-region calls" .-> S[("Service in region B")]
~~~

Moving the API closer to users will not resolve the bottleneck if the API still makes multiple sequential calls to a distant database. Global load balancing and CDNs can help distribute traffic, but they do not automatically move backend data or eliminate inter-region network costs.

**Principle:** keep frequently communicating components close together, while choosing an entry point suited to where users actually connect from.

### 2.2. Choose business-meaningful measurements

Before deciding, test an application setup sufficiently representative of production:

1. **Locate traffic sources:** user counts by city/country, mobile vs. fixed-line ISPs, peak hours, and integration partner locations.
2. **Build a candidate region list:** initially retain only regions that offer the required services and satisfy mandatory data requirements.
3. **Run equivalent test deployments:** identical API, resource configuration, HTTPS endpoint, payload size, and representative database queries.
4. **Measure from multiple networks:** sample during both peak and off-peak hours; record response times, errors, throughput, and cross-region calls.
5. **Evaluate percentiles:** p50 reflects typical requests; p95 and p99 reveal slow experiences hidden by averages.
6. **Test under load:** test cache misses, request spikes, connection reuse, and degraded/slow dependencies.

Example command to time an HTTPS request:

~~~bash
curl -s -o /dev/null \
  -w 'connect=%{time_connect}s first_byte=%{time_starttransfer}s total=%{time_total}s\n' \
  https://example.test/health
~~~

This is only a single observation from the machine running the command. A health-check endpoint usually does not execute full authentication, queries, and business logic. Therefore, collect multiple samples with representative APIs from real user networks; never draw conclusions from a single ping.

### 2.3. Latency comparison example

Suppose a retail service serves users in Hanoi and Ho Chi Minh City, and the API needs p95 under 250 ms. The team selects two candidate regions after verifying data scope and service availability. The results below are **entirely hypothetical**, not Google Cloud performance benchmarks:

| Measurement | Region A | Region B |
| --- | ---: | ---: |
| p95 API response from representative user networks | 145 ms | 195 ms |
| p95 completion of multi-query DB operation | 220 ms | 310 ms |
| Frequently called components co-located in API region | Yes | No |

With a p95 target under 250 ms, A is better suited in this illustrative benchmark. However, if A fails to satisfy data policies, quotas, availability requirements, or service features, A must be disqualified even though it is faster.

## 3. Availability: distinguishing zone failures from region failures

Availability is a system's ability to continue providing service. Disaster recovery is the ability to bring a system back after a major incident. A solid design must specify which failure modes it must withstand and what level of business loss is acceptable.

- **SLO:** service level objective, such as success rate or latency over a measurement window.
- **RTO (Recovery Time Objective):** maximum acceptable time to recover after a service disruption.
- **RPO (Recovery Point Objective):** maximum age/window of recent data that may be lost upon recovery.
- **Failure domain:** the blast radius of an incident, such as an instance, zone, region, application, network, operational action, or bad data.

| Architecture | More resilient against | Limitations |
| --- | --- | --- |
| Single VM/database in one zone | Minimal redundancy | VM, zone failure, or maintenance can take the service down. |
| Application distributed across zones in one region | Loss of some instances or a single zone | Still shares region-wide risk; data tier also requires HA. |
| Deployed across multiple regions | Certain wide-area incidents taking out an entire region | Must handle data replication, traffic shifting, consistency, quotas, operations, and testing. |

For example, you can use a regional managed instance group for Compute Engine or a regional cluster for GKE to survive single-zone failures. For Cloud SQL, in-region HA differs from cross-region read replicas. Role promotion, data loss bounds, and recovery time depend on the service and configuration. **Enabling HA or creating a replica does not automatically complete a cross-region recovery workflow.**

~~~mermaid
flowchart TB
    C["Users / entry point"] --> R1
    C -. "Reroute on incident" .-> R2
    subgraph R1["Primary region"]
      A1["API - zone 1"] --> DB1[("Primary database")]
      A2["API - zone 2"] --> DB1
    end
    subgraph R2["Standby region"]
      A3["Standby API"] --> DB2[("Replica / restored data")]
    end
    DB1 -. "Replication or backup per policy" .-> DB2
~~~

This diagram illustrates a design target, not a built-in automatic configuration for every database. Some asynchronous replication mechanisms can lose un-replicated updates; traffic rerouting may require manual intervention or consistency verification.

To recover in another region, you must prepare container images or release artifacts, configurations, secrets, IAM, networking, DNS/load balancers, databases, resource quotas, monitoring, and cutover procedures. Having backup data in a region where the application cannot start still fails to meet RTO.

**Three scenarios to test separately:**

1. **Loss of one zone:** instances in remaining zones keep serving if the app, load balancing, and data are designed for HA.
2. **Loss of an entire region:** designs spanning only zones within one region may go down; a cross-region plan is needed if business requires it.
3. **Accidental deletion or bad data update:** replicas can replicate mistakes too. Point-in-time backup/restore, access controls, and restore drills are required.

Do not assume multi-region is always optimal. It increases cost, operational complexity, data coordination difficulty, and sometimes write latency. Number of regions, replication strategy, and failover automation must derive from RTO/RPO, SLOs, and acceptable business impact.

## 4. Data residency: inspect every copy and processing flow

**Data residency** is the requirement specifying the geographic locations where covered data types are stored or processed under specific policies and commitments. It must be distinguished from **data sovereignty** (jurisdictional and control requirements), IAM access control, and data encryption. Choosing a region or enabling encryption **does not automatically prove** compliance with every legal requirement.

Some products carry different commitment scopes for customer data, metadata, backups, support access, and where processing steps execute. Thus the right question is not only “where does the database sit?” but also “where does data appear throughout its entire lifecycle?”

| Data category | Questions to verify |
| --- | --- |
| Database, object storage | Where do the instance/bucket, replicas, and restore targets reside? |
| Backups, snapshots, and replicas | In which location are they stored, and are they replicated across borders? |
| Logs, traces, metrics, crash dumps | Do they contain IPs, emails, payloads, or personal data; where are they stored and for how long? |
| Pipelines, BI, AI, caches, temp files | In which location do processing jobs and intermediate data execute or reside? |
| CDN and edge points | What data is cached/distributed at the edge, where, for how long, and is it permitted? |
| Third-party services | In which countries do webhooks, payment gateways, email senders, or analytics tools receive data? |

For example, a database may reside in an approved region while an analytics pipeline extracts personal data into a BigQuery dataset in another location. Picking the right place for the database alone does not guarantee the entire data flow is compliant.

### 4.1. Organization policies do not replace product verification

Google Cloud allows enforcing policies across the organization/folder/project structure. The Organization Policy constraint **gcp.resourceLocations** can restrict where certain supported resource types are created. You must verify its applicability for each service, existing resources, and data export/replication paths; this constraint does not by itself guarantee all data residency or processing behaviors system-wide.

Verification workflow:

1. **Document constraints clearly:** approved territories/locations, covered data types, and rules for replicas, backups, logs, and retention.
2. **Map the data:** inventory all systems that ingest, create, copy, cache, or export data.
3. **Verify each product:** available regions, commitment scope, exceptions, metadata, replication mechanics, and current contract terms.
4. **Apply controls:** Organization Policy where supported, least-privilege IAM, change reviews, and Infrastructure as Code checks.
5. **Verify post-deployment:** audit actual deployed resource locations, monitor export flows, and retain evidence for audits.

If data is mandated to remain within a territory that available services or regions do not support, reject that design, pursue another architecture/provider, or obtain formal legal review. A geographically “nearby” region does not mean it lies within the required jurisdiction.

For regulated systems, engineering teams must coordinate with legal and information security to assess regulations, contracts, exceptions, and data-processing obligations. Compliance cannot be concluded from a region name alone.

## 5. Decision-making method: filter mandatory conditions first

A common mistake is ranking regions by ping first, only to discover later that the fastest region lacks needed services, is disallowed for data storage, or cannot meet recovery requirements. A more effective approach separates **non-negotiable constraints** from **optimization criteria**.

### 5.1. Round 1: eliminate invalid candidates

A region should advance only when it simultaneously satisfies:

- **Data scope:** all places required to store/process primary data, replicas, backups, and logs fall within permitted locations.
- **Services and capacity:** required products, HA configurations, machine types, versions, and quotas/capacity exist or can be provisioned.
- **Networking and integration:** connectivity to internal services, partners, private networks, and management systems has a viable design.
- **Recovery:** a feasible design exists for the workload's RPO/RTO with sufficient resources to execute it.
- **Organization policy:** resources can be created, operated, and monitored within Organization Policies and access controls.

Mandatory constraints must not be scored as a "penalty" offset by a faster region. Shaving 50 ms of latency does not legitimize storing data in a prohibited location.

### 5.2. Round 2: select the best among valid candidates

For the remaining candidates, compare user-weighted p95/p99 latency, total cost, recovery complexity, and operational overhead. Weights can vary by system, but evidence sources should be transparent.

| Criterion | Measurement or evidence |
| --- | --- |
| User latency | Benchmark business requests from representative networks; compare p50/p95/p99, timeout rate, and throughput. |
| Inter-component latency | Trace API ↔ database, queues, external services; count cross-region calls. |
| Reliability | Results from instance/zone/region failure tests; failover time, data integrity, and backup restore results. |
| Total cost | Compute, database, storage, replicas, backups, egress, inter-zone/inter-region transfer, monitoring, and operational staffing. |
| Scalability | Regional quotas, machine types, scaling limits, growth needs, and capacity allocation ability. |
| Operations | Runbook quality, configuration management mechanisms, team readiness, and incident response speed. |

Pricing can differ across regions. Accessing or replicating data across regions can incur network charges depending on the service. Comparing only VM unit rates or storage gigabytes can severely underestimate total cost.

### 5.3. Practical example: e-commerce API

**Hypothetical context:** most customers are in Hanoi and Ho Chi Minh City. The API needs p95 under 250 ms; order data requires **RPO ≤ 15 minutes**, **RTO ≤ 60 minutes**. Authorized stakeholders have confirmed a set of permitted locations for data storage and processing. These targets are illustrative figures, not default Google Cloud SLAs.

| Task | Required evidence before deciding |
| --- | --- |
| Confirm data placement | Primary region, recovery region, backup, log, cache, and analytics locations fall within permitted scope. |
| Verify service support | Cloud Run or Compute Engine/GKE, database HA, networking, image registry, and observability support desired configurations. |
| Load testing | Exercise the API from both cities across multiple ISPs; record p95/p99, error rates, and database query latency. |
| Zone redundancy | Multiple instances or managed services with appropriate HA; database resilient to zone failure. |
| Region redundancy | Data replicated or backed up within RPO; procedures to start standby region and shift traffic within RTO. |
| Recovery drills and cost estimation | Simulate zone loss, region loss, replica restore; estimate costs for replicas, transit, and standby capacity. |

If region A is faster than B yet cannot recover within RTO/RPO, refine the architecture and retest or select another design. If both options meet business thresholds, cost and operational simplicity can outweigh saving a few extra milliseconds.

### 5.4. Record the decision for easy audit and revision

An architecture decision record should include fields such as:

~~~yaml
workload: "checkout-api"
users: "Primarily in Vietnam"
data_classification: "Customer and order data"
allowed_locations: "<approved location set>"
primary_region: "<selected region>"
recovery_region: "<standby region if permitted>"
required_p95_ms: 250
required_rpo_minutes: 15
required_rto_minutes: 60
evidence:
  - "Benchmark results from multiple user networks"
  - "Location mapping table for services and replicas"
  - "Failover and restore drill records"
decision_owner: "<responsible team>"
~~~

Strings in angle brackets are placeholders for verified values; this example is a decision-record template, not a directly deployable configuration.

## 6. Verifying decisions with tools and operational workflows

Google Cloud Console lets you view/select region, zone, or location fields for many resources upon creation. With Compute Engine, you can begin exploring the list of regions and zones using two **read-only** commands:

~~~bash
gcloud compute regions list
gcloud compute zones list
~~~

The output above does not confirm supported locations for all products. For Cloud Run, GKE, Cloud SQL, Cloud Storage, BigQuery, and specific features, check current location documentation, quotas, capabilities, and actual project configurations. Verification should cover standby regions as well, not just the primary runtime region.

### Before release

1. **Declare locations intentionally:** region/zone/location for apps, subnets, databases, buckets, datasets, logging, and backups in deployment configs. Use Infrastructure as Code and change reviews where appropriate.
2. **Validate data constraints:** inspect actual deployed locations, export rules, replicas, and third-party systems; do not rely solely on intended config values.
3. **Observe end-to-end performance:** track SLOs, p95/p99, timeouts, errors, and paths to databases/dependencies from the user's perspective.
4. **Test availability:** run drills losing an instance, a zone, a dependency, and a region; measure actual recovery time and data loss.
5. **Test restores and replicas:** test backup recovery, access permissions, associated encryption keys, data integrity, and cutover order.
6. **Check costs:** monitor egress, inter-location data transfer, backups, standby capacity, and variances between estimates and invoices.

### When the application changes

Re-evaluate region choices when entering new markets, adding analytics/AI tools, experiencing traffic growth, changing databases, receiving new data requirements, or expanding products to other regions. Changing location is not always just flipping a parameter: depending on the service, it may require creating new resources, migrating data, updating connection configs, scheduling write freezes, and executing a cutover.

For stateful systems, a region migration plan should explicitly define synchronization methods, write-freeze timing, post-migration data reconciliation, rollback procedures if errors occur, and who is authorized to approve traffic cutover.

## 7. Applied scenario: evaluating a deployment plan

A team proposes placing the frontend behind a CDN, the API on Cloud Run, the database on Cloud SQL, and files on Cloud Storage. They chose the API region because it won a ping test; the database is in another region because of attractive pricing; bucket and logging locations are left unspecified. The proposal simply adds “use global services so it is always available.”

To evaluate the plan, build a four-column table: **component**, **actual location**, **constraints**, **verification evidence**. At least five tasks must be addressed:

1. Measure p95/p99 of **complete business flows**, including the cross-region API → Cloud SQL call path and data returned to the user.
2. Verify that buckets, backups, logs, CDN-cached data, and all data import/export flows comply with permitted scopes.
3. Separate API/database zone-fault tolerance from recovery plans when an entire region fails; define and test RTO/RPO.
4. Calculate additional costs from cross-region data exchange, maintaining replicas, backups, and standby capacity.
5. Document measurements, constraints, missing assumptions, and architectural decisions for future audits.

The design is ready for approval only when **all mandatory constraints are verified**, the application path meets required latency, and recovery drills demonstrate the system achieves the chosen downtime/data-loss targets. Fast execution in one region solves only part of the problem.

## Verification sources during deployment

- **Google Cloud locations:** https://cloud.google.com/about/locations — check the catalog of available infrastructure and locations.
- **Individual Google Cloud service documentation:** review the Locations, High availability, Disaster recovery, Data residency, and Pricing sections of each product in use.
- **Resource hierarchy / Organization Policy:** consult Resource Manager guides and the scope of support for the **gcp.resourceLocations** constraint.
- **Google Cloud Architecture Center:** reference designs for HA, multi-region, disaster recovery, reliability, and SLO-based monitoring.

These sources should be checked at deployment time because supported regions, features, quotas, replication mechanics, data residency commitments, and pricing can change.
