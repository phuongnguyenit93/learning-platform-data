# Data Residency Requirements and Workload Execution Location Controls

When deploying compute in the cloud, where data is created and processed can be just as critical as CPU, memory, or network configuration. A workload can run across multiple regions, zones, or infrastructure tiers; its data can also appear in object storage, databases, snapshots, backups, logs, caches, telemetry, model artifacts, and disaster recovery replicas. Selecting only a region for virtual machines without governing accompanying data flows can still inadvertently move data outside permitted boundaries.

Data residency requirements mandate that data be stored or processed within specific geographic locations. Workload execution location controls ensure compute, supporting services, and data paths obey those boundaries. These two requirements are related yet distinct: data may be stored in one region while processed by a workload in another; conversely, compute may run locally while logs, backups, or telemetry ship elsewhere.

This lesson explains how to translate data residency requirements into enforceable, auditable technical policies. Topics include data classification, geographic scoping, region selection, compute placement restrictions, replica and data-flow controls, support access governance, DR design, policy-as-code, and audit evidence collection. After this lesson, you will be able to:

- Distinguish data residency, data sovereignty, data localization, and data locality.
- Identify which data must be stored, processed, backed up, or accessed within specific geographic boundaries.
- Map workload data and dependencies across regions and services.
- Design region allowlists, organizational policies, and guardrails preventing mislocated deployments.
- Control placement for VMs, containers, Kubernetes nodes, serverless functions, and accelerators.
- Evaluate snapshots, backups, logs, telemetry, caches, secrets, and model artifacts.
- Design cross-region replication and disaster recovery aligned with residency constraints.
- Test, monitor, and retain evidence covering execution locations and data flows.

## 1. Key Concepts to Distinguish

Data geography terms are often used interchangeably in conversation, yet they describe distinct aspects. When translating legal, contractual, or internal policy mandates into cloud configurations, specify exactly what must stay where and who may access it.

| Concept | Meaning | Key Question |
|---|---|---|
| Data residency | Geographic location where data is stored or maintained | Which country/region holds the data? |
| Data sovereignty | Jurisdiction and laws applicable to the data or the provider controlling it | Which laws and authorities govern the data? |
| Data localization | Mandate that data within a scope be stored or processed within a specific country/region, sometimes restricting transfer out | Must the data stay inside borders? |
| Data locality | Proximity between data and compute to reduce latency, transfer costs, and network load | How close is the workload to the data? |
| Processing location | Location where data is read, decrypted, transformed, or used for inference | Where is the data processed? |

Data residency does not automatically answer every sovereignty question. Data stored in one region may still fall under laws governing the provider or controlling organization. Likewise, data locality is typically a performance and cost goal; it does not substitute for legal residency mandates.

### Distinguishing Example

An application serving customers in Vietnam stores its database in a Singapore region, runs workers in that region, and sends backup copies to another region:

- The database location establishes part of residency.
- Workers in Singapore establish the processing location.
- Backups in the second region create an additional data copy that must be evaluated.
- Support engineers accessing the database from another country raise cross-border access and sovereignty questions.
- Placing the database near workers improves data locality, yet does not prove localization compliance.

You cannot conclude whether this setup is compliant without knowing the data classification, contracts, applicable laws, customer requirements, and organizational policies.

## 2. Defining the Scope of Residency Requirements

A statement like "data must stay in country X" is too vague to implement. Clarify which data, which operations, which actors, and which service scopes are constrained.

### Questions to Clarify

1. **Data subjects/objects:** personal data, financial records, health data, public data, internal data, source code, model weights, or anonymized data?
2. **Geographic scope:** country, territory, cloud region, availability zone, or data center site?
3. **Data states:** primary data, replicas, backups, snapshots, caches, logs, exports, intermediate files, and deleted data?
4. **Operations:** storage, processing, transit, backup, restore, display, operational support, or administrative access?
5. **Accessors:** end users, workloads, providers, support teams, contractors, or third-party services?
6. **Duration:** continuous applicability, contract duration, processing-only, or post-termination retention?
7. **Exceptions:** are DR, emergency support, encrypted transfers, or de-identified data permitted?
8. **Evidence:** which configurations, audit logs, attestations, region reports, or audit records are required?

### Differentiating Rules by Data Type

Do not apply one blanket geographic rule across an entire workload if data carries varying sensitivity levels. Build a matrix:

| Data Type | Example | Location Requirements to Define |
|---|---|---|
| Core business data | Customer records, transactions | Storage, processing, backup regions, and access permissions |
| Identifying data | Names, addresses, government IDs | Storage, access, transfer, and deletion boundaries |
| Pseudonymized/anonymized data | Tokens replacing IDs, aggregate statistics | Criteria determining whether re-identification remains possible |
| Logs and audits | Request IDs, IPs, principals, payload metadata | Log region, retention, SIEM export, and read permissions |
| Telemetry | Traces, metric labels, crash dumps | Whether payloads, identifiers, or secrets are present |
| Caches and ephemeral data | Redis, local disks, temporary files | Location, TTL, cleanup, and replicas |
| Backups/snapshots | Database snapshots, disk images | Region, vault, replication, retention, and restore location |
| Model/data artifacts | Weights, feature stores, datasets | Provenance, storage location, download, and inference/training sites |
| Secrets and key material | API keys, encryption keys | Management location, access rights, backups, and key residency |

A log containing only timestamps and status codes may be less sensitive than one containing request bodies, emails, or IPs. Classify by actual contents and linkability, not solely by the name of the system emitting the log.

## 3. Data Inventory and Data Flow Mapping

To enforce residency, first know every component data passes through. Architecture diagrams showing only APIs and databases rarely suffice; include secondary flows such as logs, metrics, backups, caches, replication, support tooling, and CI/CD artifacts.

### Building the Inventory

For each dataset, record:

- Owner and business purpose.
- Data classification and tenant/subject scope.
- System of record and data origin.
- Storage service, account/project/subscription, and region.
- Reading/writing workloads and processing locations.
- Outbound transfers, endpoints, and recipients.
- Snapshots, backups, replicas, and retention.
- Encryption keys, key owners, and key locations.
- User groups and workloads with access.
- Deletion, export, audit, and retention requirements.

### Flow Mapping

~~~mermaid
flowchart TD
    C["Client / data subject"] --> A["API in Region A"]
    A --> F["Compute workload in Region A"]
    F --> D[("Database in Region A")]
    F --> O[("Object storage in Region A")]
    F --> L["Logs / traces / metrics"]
    D --> B["Backup service"]
    O --> R["Replication / export"]
    L --> S["Central observability"]
    B --> DR["DR region"]
    R --> DR
~~~

The diagram above is an analysis framework. Every arrow should document data type, purpose, protocol, source/destination regions, encryption, authorization, and retention. If a service automatically replicates data or ships telemetry, include that flow in the inventory even if the application never calls it explicitly.

### Checking Indirectly Generated Data

Commonly overlooked sources:

- Crash dumps or heap dumps may contain in-memory data.
- Trace spans may record URLs, queries, headers, or payloads.
- API Gateway, load balancer, and WAF logs may store IPs or request metadata.
- Disk snapshots may capture temporary files, swap, or caches.
- Container images may bake in datasets, models, or config files.
- CI artifacts and build caches may retain input data.
- Support bundles and diagnostic packages may be downloaded to support workstations.
- Search indexes, data warehouses, and feature stores may create copies of business data.

## 4. Translating Requirements into Technical Policies

A residency requirement can be expressed as concrete constraints:

- Allow compute and storage provisioning only in approved regions.
- Allow workloads processing data class X to connect only to storage in the same scope.
- Prohibit replication, exports, or backups outside permitted zones.
- Allow only identities in approved groups/tenants to access the data.
- Store logs, traces, and audits containing sensitive data in systems within the required location.
- Restrict DR to evaluated and approved standby regions.
- Require review and evidence for region or data-flow changes.

### Policy Categories

| Control Layer | Objective | Example |
|---|---|---|
| Preventive | Block non-compliant configs before resource creation | Deny regions outside allowlist |
| Detective | Detect mislocated resources or flows post-deployment | Config rules, asset inventory, flow logs |
| Corrective | Remediate violations in a controlled way | Isolate workload, migrate data, revoke access |
| Governance | Define approvers and exceptions | Owner, ticket, expiry, risk acceptance |

Do not rely solely on detective controls when misdeployments can be blocked upfront. Yet preventive policies do not replace inspecting data flows created by managed services or application configs.

### Region Allowlists and Deny-by-Default

Organizations can define approved region lists per workload category. A policy denying non-allowlisted regions by default reduces accidental region selection errors. Maintain allowlists against an evaluated region catalog rather than automatically permitting every new region launched by a cloud provider.

A region allowlist alone is not complete residency proof. A workload running in an approved region can still ship logs, backups, or data to out-of-scope endpoints.

## 5. Controlling Compute Locations

Compute takes many forms: VMs, autoscaling groups, container services, Kubernetes nodes, serverless functions, managed jobs, GPU clusters, or inference services. Each has distinct region selection and placement mechanics.

### Virtual Machines and Node Pools

For VMs:

- Specify region and zone in resource configuration.
- Restrict instance families and host locations if infrastructure-type mandates apply.
- Place autoscaling groups inside approved subnets and zones.
- Keep disks, snapshots, images, and backups within the same geographic scope.
- Monitor VM creation across console, API, IaC, and child accounts.

Autoscalers must never pick regions outside the allowlist just to find cheaper capacity or available quota. If an approved region runs out of capacity, follow an approved fallback procedure.

### Containers and Managed Container Services

For containers:

- Deploy clusters or services in approved regions.
- Verify where registries and image layers are stored.
- Control log drivers, tracing exporters, and artifact downloads.
- Confirm service meshes, ingress, egress, and sidecars do not transmit data out of scope.
- Verify where volumes, persistent disks, and ephemeral storage reside.

A cluster in a valid region pulling images from a registry in another region still creates cross-region traffic. Evaluate image registries, caches, and mirrors as well.

### Kubernetes Node Placement

Kubernetes can constrain Pod placement via node labels, node affinity, taints/tolerations, and admission policies. However, self-assigned node labels are not trustworthy geographic proof if workload users can edit labels.

Example where a trusted platform or automation applies the location label:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: regulated-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: regulated-api
  template:
    metadata:
      labels:
        app: regulated-api
    spec:
      nodeSelector:
        topology.example.com/data-zone: approved-region-a
      containers:
        - name: api
          image: registry.example.com/regulated-api:2.4.0
          resources:
            requests:
              cpu: "1"
              memory: "2Gi"
~~~

The `topology.example.com/data-zone` label in this example is an internal convention, not a standard Kubernetes label, and must be applied by a trusted component. For geographic constraints, combine:

- Node pools provisioned in approved regions.
- Labels/taints managed by the platform team and locked against tenant edits.
- Required node affinity (`requiredDuringSchedulingIgnoredDuringExecution`) when hard enforcement is needed.
- Admission policies rejecting Pods lacking compliant placement constraints.
- Cluster autoscalers restricted to scaling only approved node pools.

If Pods get rescheduled, the scheduler must still obey constraints. Also check init containers, sidecars, DaemonSets, and ephemeral workloads.

### Serverless Functions and Managed Jobs

For serverless:

- Select the region for functions and associated triggers.
- Identify the region of event sources, queues, schedulers, and destinations.
- Check where environment variables, deployment packages, and logs are stored.
- Control cross-region invocations and cross-region service access.
- Verify where managed runtimes process or store metadata according to service documentation.

A function in region A reading data from a bucket in region B still processes data in A and transfers data across boundaries. Evaluate against the exact mandate definitions.

### Accelerators and Inference Workloads

GPU/accelerator pools are also compute locations. For training or inference workloads:

- Model weights and datasets require approved storage locations.
- GPU nodes, host memory, scratch disks, and caches must remain within scope.
- Serving endpoints and request logs must match the same data classification.
- Model artifacts pulled from registries must have verified origins and regions.
- Multi-region inference requires explicit data partitioning and routing policies.

## 6. Controlling Storage, Snapshots, and Backups

Selecting a region for a database or bucket only governs the primary data copy. Verify automated replication mechanisms:

- Read replicas and cross-region replicas.
- Backup vaults, snapshot copies, and archive tiers.
- Object replication and versioning.
- Database exports, dumps, and data pipelines.
- Disk images and machine images.
- Cache persistence and recovery files.
- Search indexes, analytics stores, and data warehouses.

### Backups Are Not Automatically Exempt

A backup still holds original or recoverable data. If residency applies to stored data, backups generally require evaluation under the same scope. Never assume backups in another region are compliant merely because they are rarely accessed.

### Regional Backup Design

Options include:

- Same-region backups separated by account/project and security boundaries.
- Multi-zone backups within the same region if availability requirements are met.
- Cross-region backups restricted strictly to pre-approved regions.
- Immutable backups or vault locks preventing tampering/deletion.
- Encryption using keys aligned with governance and location mandates.

If data must remain in a single country, DR may have to stay within that same country or permitted territory. This can reduce region options and impact RTO/RPO. Document trade-offs and obtain approvals if DR options cannot satisfy every requirement simultaneously.

### Testing the Restore Path

Do not inspect only where backups are written. Test:

1. Who holds restore permissions?
2. Can restores target a region outside the allowlist?
3. Where do temporary restore artifacts land?
4. How long are intermediate logs and snapshots retained?
5. Are keys accessible in the DR region?
6. Post-recovery, do traffic and replication create cross-region flows?
7. How are temporary datasets and old copies purged?

## 7. Controlling Logs, Telemetry, and Observability

Logs and telemetry are often overlooked as operational data. In practice, they can contain personal data, identifiers, request contents, filenames, SQL statements, URL queries, tokens, or stack traces.

### Components to Review

- Application logs and audit logs.
- API Gateway, load balancer, WAF, and firewall logs.
- Distributed traces and span attributes.
- Metric labels and exemplars.
- Crash dumps, heap dumps, and diagnostic bundles.
- APM/SaaS exporters and incident management integrations.
- SIEMs, data lakes, and log archives.

### Minimizing Sensitive Data Before Log Export

- Do not log raw request bodies unless necessary.
- Redact tokens, emails, government IDs, and secrets.
- Use request IDs or pseudonymous identifiers where appropriate.
- Cap label cardinality to keep identifiers out of metrics.
- Set sampling and retention by data classification.
- Export exclusively to approved observability endpoints.

### Location of the Observability Platform

A workload may run in an approved region while shipping telemetry to a SaaS control plane elsewhere. Verify the region of log workspaces, trace backends, backups, and support access. Where providers offer dedicated telemetry residency options, configure them and save corresponding evidence.

Do not place sensitive data into metric labels or traces simply for debugging convenience. When investigating, use temporary, approved, audited access mechanisms.

## 8. Network Egress and Cross-Region Data Flows

Execution location controls cannot be separated from network controls. A workload in an approved region can still transmit data to public endpoints or services in another country.

### Mapping Egress

Inventory:

- Destination IP, hostname, service endpoint, and region.
- Protocol, port, and data types transmitted.
- Business justification and owner.
- Whether TLS/mTLS encryption is enforced.
- Whether data is persisted at the destination.
- Whether the destination uses subprocessors or replicas elsewhere.

### Control Mechanisms

- Egress firewalls or cloud network firewalls.
- Managed route tables and NAT gateways.
- Private endpoints/PrivateLink/service endpoints for cloud services.
- DNS policies and domain allowlist enforcement.
- Service mesh egress gateways.
- VPC flow logs or network telemetry to detect unexpected destinations.
- DLP or proxy inspection where permitted and appropriate.

Private connectivity avoids the public Internet and shrinks the attack surface, yet does not guarantee residency. A private endpoint can still point to a service in another region or a service whose control plane/data processing sits in a different scope. Verify actual locations and service semantics.

### Cross-Region APIs and Replication

When a workload invokes an API in another region, determine whether requests carry regulated data. For replication, establish what data replicates, when, retention, and destination access controls. Even if only non-sensitive metadata crosses boundaries, check whether metadata can be linked to identify subjects.

## 9. Cross-Border Administrative and Support Access

Data residency is not solely where disks sit. Access by operations staff, vendors, and support teams creates another boundary.

Determine:

- Who can open consoles, shells, remote sessions, or database queries?
- Can support engineers inspect payloads, logs, or snapshots?
- Is access restricted by country, group, time window, or ticket?
- Are just-in-time access and approvals enforced?
- Are sessions recorded and audited?
- Can masked data or diagnostic metadata replace raw data?
- Which subprocessors or support locations does the vendor contractually use?

### Just-in-Time and Break-Glass

Emergency access should enforce:

1. Specific incident or ticket with justification.
2. Independent approver commensurate with risk.
3. Least privilege and short duration.
4. MFA and strong authentication.
5. Session logging or audit trails.
6. Automatic revocation on expiration.
7. Post-incident review.

Break-glass must never be an uncontrolled shared account. If mandates bar access from certain locations, enforce this through identity/network conditions and tailored support workflows—not merely instructions in a runbook.

### Encryption and Key Control

Encryption at rest and in transit lowers exposure risk but does not replace residency mandates. Examine who controls keys, where keys are stored, who can call decrypt, and where services handle plaintext.

Customer-managed keys strengthen key lifecycle control and auditing, yet do not prove data cannot be accessed from outside the region. Analyze decrypt permissions, key replication, HSM regions, key backups, and recovery procedures.

## 10. Region Selection and Service Eligibility

Not every cloud service, feature, or instance family exists in every region. When choosing a region, evaluate geographic mandates alongside technical capability.

### Region Selection Matrix

| Criterion | Evaluation Question |
|---|---|
| Residency | Is the region within permitted boundaries? |
| Service availability | Are compute, storage, database, key management, and logging services available? |
| Instance/accelerator | Do required CPU/GPU types have quota and capacity? |
| Network | Are private connectivity and required endpoints available? |
| DR | Does an approved standby region meet RTO/RPO? |
| Data transfer | Does it introduce cross-region flows or costs? |
| Support | Do support models and access controls align? |
| Audit | Are location evidence, logs, and policies sufficient for audits? |
| Cost | Are compute, storage, network, and licensing costs acceptable? |

### When a Service Is Unavailable in Permitted Regions

Do not automatically move data to another region just to use a missing feature. Options include:

- Choosing an alternative service or instance already available in-region.
- Running the needed component on self-managed VMs/containers in-region.
- Designing around the missing feature.
- Waiting for provider support in the target region.
- Requesting an exception backed by risk assessment and legal/contractual review.

If no compliant option exists, document the constraint and business decision. You cannot claim compliance when core services process data outside required boundaries.

## 11. Enforcing Regions via Organizational Policies

Cloud providers offer organization/account/project/subscription-level policies to restrict where resources are created. Names vary by platform, yet the goal is centralized guardrails.

### Common Policy Layers

- Allowed locations or region restrictions.
- Organization policies / Service Control Policies.
- IAM conditions on region or resource location.
- Resource policies restricting sources and destinations.
- Cloud governance rules or policy-as-code.
- Kubernetes admission policies.
- IaC policy checks in CI/CD.

### Design Principles

1. Define allowlists by workload category and data class.
2. Enforce at organization/account levels so teams cannot pick arbitrarily.
3. Default-deny unapproved regions.
4. Separate exception approval rights from everyday deployment rights.
5. Check services that handle location constraints differently from compute.
6. Put policies in version control and review them like code.
7. Monitor policy drift and out-of-band resource creation.

### Declarative Policy Example

This YAML illustrates an internal policy for an IaC validation pipeline. It is not a standard schema of any cloud provider; translate it into the syntax of your organization's policy engine.

~~~yaml
policy:
  name: compute-region-allowlist
  effect: deny
  applies_to:
    resource_types:
      - virtual_machine
      - kubernetes_node_pool
      - serverless_function
  allowed_locations:
    - approved-region-a
    - approved-region-b
  exception:
    requires:
      - owner
      - approval_ticket
      - expiry
      - data_classification
~~~

Policies must evaluate both create and update operations. A resource created in an approved region can later be modified or attached to out-of-region services.

## 12. Location Controls in Kubernetes

In Kubernetes, placement and location can be expressed through multiple mechanisms:

- Node labels for region, zone, and node pool.
- Node selectors and required node affinity.
- Taints/tolerations to isolate node pools.
- Topology spread constraints to distribute replicas within permitted zones.
- Admission controllers to reject non-compliant manifests.
- RBAC restricting who can edit node labels, namespace policies, and workloads.
- Cluster autoscalers/provisioners constrained to approved instance types and regions.

### Never Trust Tenant-Supplied Labels

A Pod can request `data-zone=approved-region-a`, yet if users can edit node labels or spin up nodes in another region and apply that label, the constraint becomes meaningless. Geographic labels must be applied by cloud controllers or RBAC-protected platform automation.

### Admission Policies

Admission policies can inspect namespaces, workload labels, node selectors, volumes, image registries, and service accounts before admitting Pods. For example, workloads labeled `data-class=restricted` must specify node affinity targeting approved node pools and must not mount volumes from unapproved storage classes.

Admission policies only inspect Kubernetes objects. They cannot verify the real location of external databases, registries, log sinks, or endpoints. Pair them with cloud-layer inventories and policies.

### Topology Spread

Topology spread distributes replicas across zones to improve availability, but must stay within permitted zones/regions. If residency allows only a single region, spread replicas across multiple zones inside that region; never expand into another region solely for availability.

## 13. Location Controls for Serverless and Managed Services

Managed services reduce operational toil yet can abstract away location details. Before using them with regulated data, verify:

- Region of resource endpoints and data planes.
- Where metadata, backups, and logs are stored.
- Default replication behavior.
- Where support/diagnostic data is processed.
- Whether multi-region or global endpoints are enabled.
- Whether control planes can sit in a different location from data planes.
- Whether the service provides explicit residency commitments in contracts or documentation.

### Global Endpoints and Routing

Global load balancers, CDNs, API gateways, or DNS-based routing can direct requests across regions. For restricted data, routing must guarantee requests carrying such data hit only in-scope compute. Check automatic failover: if the primary region fails, can traffic shift to an unapproved region?

### Event Buses and Queues

Queues or event buses may live in separate regions. When a function in region A reads messages from queue B, payloads cross boundaries. Identify what data messages hold, where retention resides, and whether dead-letter queues follow identical policies.

Dead-letter queues are often missed in data flow maps. They can retain failed payloads longer than primary queues and carry broader access permissions.

## 14. Cross-Region Replication, DR, and RTO/RPO

Disaster recovery normally recommends replicas in another region to survive regional outages. Under residency mandates, however, DR regions must also stay within permitted bounds or hold explicit exceptions.

### RTO and RPO

- **RTO (Recovery Time Objective):** maximum target time to restore service.
- **RPO (Recovery Point Objective):** maximum tolerable data loss, usually expressed as time since last sync.

Residency constraints can narrow available DR regions, increasing RTO/RPO or costs. Design around actual provider capabilities and approved policies.

### DR Models

| Model | Characteristics | Residency Considerations |
|---|---|---|
| Same-region backup/restore | Backups within same geographic region | May not survive full-region outages |
| Multi-zone | Replicas or backups in another zone of the same region | Verify zone independence and region geography |
| In-country cross-region | Replicas in another region within the same permitted country | Verify services, contracts, and routing |
| Cross-border DR | Replicas outside national borders | Use only with valid legal basis and formal approval |
| Active-active | Multiple regions handle live traffic | Must control where requests and data are routed |

### Failover Must Not Break Constraints

DR runbooks must specify:

- Which regions/zones are permitted to receive data.
- Who authorizes failover.
- Where traffic routing may shift.
- Whether keys and secrets are available in the DR region.
- Whether replicas and backups are consistent.
- Where DR logs and audits are stored.
- How temporary data and out-of-scope replicas are handled post-recovery.

If no compliant DR region exists, document the availability risk and formally accept it or adjust requirements. Never silently copy data into unapproved regions during an incident.

## 15. Data Residency in CI/CD Pipelines and Artifacts

Build/deploy pipelines also handle data and can spawn copies across locations:

- Source code, configuration, and IaC state.
- Build logs and test outputs.
- Container images, packages, and model weights.
- Build caches and artifact repositories.
- Test datasets, fixtures, and production dumps used for debugging.
- Deployment packages and crash reports.

### Controls

- Place runners/agents and artifact stores in approved locations.
- Never use production data in tests without authorization and safeguards.
- Redact secrets and personal data from build logs.
- Pin approved registries and package mirrors.
- Restrict artifact download rights and IaC state access.
- Enforce retention and cache purging per policy.
- Record regions of runners, registries, artifact stores, and deployment targets.

If a runner in another region pulls sensitive source or datasets to build, that constitutes a data flow requiring evaluation even if the final application deploys in the right location.

## 16. Policy-as-Code and Pre-Deployment Checks

Policy-as-code automates configuration validation prior to resource creation. Tools can inspect IaC plans, Kubernetes manifests, or cloud resource configurations.

### Conditions to Check

- Region/location is in the allowlist for the data class.
- Resources carry owner, data classification, and environment tags/labels.
- Databases, buckets, disks, and backups use compliant locations.
- Encryption and key references are configured.
- Cross-region replication targets only permitted destinations.
- Functions, node pools, and managed jobs lack unauthorized global routing.
- Kubernetes Pods enforce placement constraints for restricted data classes.
- Image registries, log sinks, and artifact sources remain in scope.
- Exceptions carry tickets, owners, justifications, and expirations.

### Example: Checking a Kubernetes Manifest with Internal Policy

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: restricted-worker
  labels:
    data-class: restricted
    owner: risk-platform
spec:
  replicas: 2
  selector:
    matchLabels:
      app: restricted-worker
  template:
    metadata:
      labels:
        app: restricted-worker
    spec:
      nodeSelector:
        topology.example.com/data-zone: approved-region-a
      containers:
        - name: worker
          image: registry.approved.example/restricted-worker:3.1.0
          volumeMounts:
            - name: data
              mountPath: /data
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: restricted-data
~~~

This manifest illustrates placement and registry conventions. The policy engine must also check PVCs, StorageClasses, PV topology, and the storage backend's real region. A node selector alone cannot ensure a volume stays in the same zone if the storage class or CSI driver allows cross-zone/region attachment.

### Failing Builds on Violations

In CI, enforce:

1. Parse IaC plans or manifests.
2. Identify data classification and owner.
3. Resolve resource locations.
4. Compare against allowlists and dependency maps.
5. Fail the pipeline on violations or missing required metadata.
6. Permit exceptions only with formal approval and expiration.

Never let pipelines auto-"fix" a region without knowing whether data can legally move there. Data relocation requires a migration plan and separate approval.

## 17. Drift Detection and Continuous Monitoring

A configuration compliant at deployment can change later. Operators can create resources via the console, automation can alter regions, or services can enable default replication.

### Detective Controls

- Periodic asset inventories recording location, owner, and data classification.
- Config rules or cloud posture management catching non-allowlisted regions.
- Audit logs tracking create/update/delete and policy edits.
- Network flow logs detecting connections to unapproved destinations.
- Storage access logs catching anomalous access or replication.
- Kubernetes admission/audit logs monitoring Pod placement and node pools.
- Alerts whenever backups, exports, or log sinks change location.

### Handling Drift

When a mislocated resource is detected:

1. Identify data class, owner, and what data actually resides there.
2. Halt further data expansion if needed and approved.
3. Preserve audit evidence.
4. Assess notification duties and organizational incident workflows.
5. Plan controlled data migration or deletion.
6. Verify remaining backups, replicas, caches, logs, and copies.
7. Fix the root cause in IaC, policies, or deployment permissions.
8. Re-verify and close the incident per process.

Never immediately delete violating resources before assessing data impact, evidence, recoverability, and retention mandates.

## 18. Exception Management

Some scenarios require exceptions: capacity shortages in permitted regions, unavailable services, DR events, or vendor support needs. Manage exceptions as bounded risk decisions.

An exception record should contain:

- Resource/workload and data classification.
- Original requirement and exempted policy.
- Specific region/source/destination.
- Permitted data types and operations.
- Business purpose and justification.
- Technical owner and risk approver.
- Compensating controls such as encryption, masking, tokenization, or access restrictions.
- Start date, expiry, and exit plan.
- Monitoring method and evidence.

Never use indefinite exceptions or wildcard regions. Upon expiration, automation should alert or revoke related permissions/flows per approved procedures.

## 19. End-to-End Example: Region-Restricted Data Processing Workload

An application processing customer records has an internal mandate: identifying data and record contents may only be stored and processed in approved regions within the same geographic boundary. The app includes APIs, workers, databases, object storage, queues, a log pipeline, and backups.

### Design

1. Apply data classifications to database records, objects, queue payloads, and logs that may carry data.
2. Provision a dedicated workload account/project with a region allowlist.
3. Place APIs, workers, databases, buckets, queues, and keys inside approved regions.
4. Use node pools and admission policies to lock Pod placement.
5. Block replication and exports to destinations outside the allowlist.
6. Configure log redaction and in-scope log sinks.
7. Store backups in permitted regions/zones and test restores.
8. Restrict support access via JIT, approvals, and session audits.
9. Verify runners, image registries, and IaC state do not pull sensitive data out of bounds.
10. Collect asset inventories, policy evaluations, and audit evidence.

### Data Flow Diagram

~~~mermaid
flowchart TD
    U["Client"] --> API["API / compute in permitted region"]
    API --> Q["In-region queue"]
    Q --> W["Worker in controlled node pool"]
    W --> DB[("In-scope database")]
    W --> OBJ[("In-scope object storage")]
    DB --> BK["Approved backup vault"]
    OBJ --> BK
    API --> LOG["Redacted logs"]
    W --> LOG
    LOG --> OBS["Approved observability workspace"]
    POL["Organization policy + admission + egress policy"] -. "Constraints" .-> API
    POL -. "Constraints" .-> W
    POL -. "Constraints" .-> DB
~~~

### Testing

- Creating a VM or node pool in an unapproved region must be denied by policy.
- Creating a restricted Pod without node affinity must be denied by admission policy.
- Configuring replication to an out-of-region bucket must be blocked.
- Logs containing sensitive fields must be redacted prior to export.
- Backup restores must permit only valid destinations.
- Unapproved principals cannot read data or open support sessions.
- Changing a region via console must generate an audit event and alert.

This example shows how to translate a requirement into layered guardrails. It does not assert that a specific configuration satisfies every country's laws; legal/contractual requirements must be interpreted by owners and authorized counsel before deployment.

## 20. Compliance Evidence and Auditing

To prove controls are operating, retain traceable evidence:

| Evidence | What It Proves |
|---|---|
| Cloud asset inventory | Resource ID, account/project, region, zone, owner, data class |
| Organization policies | Active region allowlists and deny rules |
| IaC plans/reviews | Location changes reviewed prior to deployment |
| Kubernetes admission logs | Workloads denied or admitted per placement policy |
| Network flow logs | Actual egress flows and destinations |
| Storage replication config | Destinations, encryption, retention, and status |
| Backup/restore reports | Backup locations and restore targets |
| IAM/access audits | Principals, timestamps, resources, and access actions |
| Exception register | Exceptions, approvals, expirations, and compensating controls |
| Incident records | Violations, remediation, root causes, and closure evidence |

Evidence requires timestamps, sources, owners, and appropriate retention. Single console screenshots rarely suffice because they go stale quickly; prefer reproducible config exports, audit logs, and inventory reports.

## 21. Common Mistakes

1. **Picking a region only for VMs:** overlooks databases, backups, logs, caches, registries, and telemetry.
2. **Equating residency with sovereignty:** ignores applicable laws, access rights, and provider models.
3. **Allowing every newly launched region:** allowlists expand automatically without review.
4. **Trusting tenant-applied node labels:** placement constraints can be spoofed.
5. **Skipping volume topology checks:** Pods land on the right node while persistent storage sits in another zone/region.
6. **Forgetting dead-letter queues:** failed payloads linger elsewhere or under longer retention.
7. **Overlooking support access:** staff or subprocessors access data from other locations.
8. **Assuming encryption solves residency:** ciphertext can still fall under storage and governance mandates.
9. **Not testing failover:** systems automatically route traffic to unapproved regions.
10. **Using unrestricted global endpoints:** requests reach compute outside allowed boundaries.
11. **Failing to classify telemetry:** traces and crash dumps carry sensitive data.
12. **Not testing restores:** backups sit in the right place while restores write copies to the wrong region.
13. **Checking only at deploy time:** drift from console, API, or automation goes unnoticed.
14. **Non-expiring exceptions:** temporary exemptions turn into permanent privileges.
15. **Auto-moving data when policies fail:** can trigger new violations or data loss.

## 22. Design and Operations Checklist

- [ ] Residency mandates are translated into specific data, operations, and geographic scopes.
- [ ] Data classification and owners are assigned to workloads and related resources.
- [ ] Inventory covers databases, objects, queues, caches, logs, telemetry, backups, and artifacts.
- [ ] Data flow maps specify sources, destinations, regions, purposes, and data types.
- [ ] Region allowlists are approved and centrally managed.
- [ ] Organizational policies block creating compute/storage outside permitted regions.
- [ ] VMs, node pools, serverless, managed jobs, and accelerators enforce appropriate placement constraints.
- [ ] Kubernetes node labels are platform-controlled; admission policies validate workloads.
- [ ] PVCs, PVs, StorageClasses, and CSI topology align with allowed regions.
- [ ] Registries, images, model artifacts, CI runners, and build caches are evaluated.
- [ ] Backups, snapshots, replicas, and DR destinations are pre-approved.
- [ ] Logs, traces, metrics, and crash dumps are classified, redacted, and stored in-region.
- [ ] Egress, private endpoints, global routing, and cross-region APIs are controlled.
- [ ] Support access, break-glass, and key management are audited.
- [ ] Failover/restores are tested without breaching geographic boundaries.
- [ ] Policy-as-code runs in CI and detects post-deploy drift.
- [ ] Exceptions carry owners, approvals, expirations, and compensating controls.
- [ ] Audit evidence is retained, timestamped, and retrievable.
- [ ] Runbooks exist for handling mislocated resources and out-of-scope data copies.

## 23. Practice Exercise

An organization deploys a workload processing customer records. Internal policy mandates that identifying data be stored and processed only in region A or region B. The workload runs on Kubernetes in region A; its database and object storage are also in A. However:

- Database backups are copied to region C.
- The log pipeline ships traces to a SaaS workspace in region D.
- The cluster autoscaler is permitted to provision nodes in A and C.
- The API Gateway uses global routing and can fail over to C.
- Support engineers hold snapshot read permissions from a shared admin account.

1. List the flows or components at risk of violating the requirement.
2. Distinguish residency, processing location, access, and data locality issues in this scenario.
3. Propose guardrails for the cluster autoscaler, API routing, and backups.
4. How must logs/traces be modified before shipping to the observability workspace?
5. How should support permissions and snapshots be governed?
6. Propose automated tests and audit evidence to prove compliance after remediation.

Hint: regions C and D lie outside the hypothetical policy allowlist, so backups, node pools, failover, and telemetry must change or receive approved exceptions. Restrict node pools to A/B; configure routing to fail over only to permitted regions; move backups to a compliant vault; redact payloads/identifiers before log export and use an in-region workspace. Separate support identities, enforce JIT access, approvals, MFA, and session audits. Test policy denials, admission, replication destinations, egress, restore locations, and failover targets; retain inventory, policy evaluations, flow logs, and access audits.

## Conclusion

Data residency requirements must be implemented across the full lifecycle of data and processing locations—not just where primary servers sit. Start with data classification and a data flow map, then enforce region allowlists, organizational policies, placement constraints, and controls over storage/backups, egress, telemetry, and support access. DR and failover must respect the same boundaries or carry approved exceptions. Policy-as-code, drift monitoring, and audit evidence sustain control long after workloads enter production.
