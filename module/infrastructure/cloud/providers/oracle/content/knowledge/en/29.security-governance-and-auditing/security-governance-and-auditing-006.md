# Data residency and designing controls for compliance requirements

## 1. Objectives and scope

In the **Security, Governance, and Auditing** chapter of the **CLOUD_PROVIDERS_ORACLE** module, data residency is an architectural requirement spanning tenancy, IAM, networking, Compute, storage, databases, and operations. Choosing a region for a database only determines the location of one component. Replicas, backups, logs, identity data, and technical support paths must also be evaluated.

This lesson guides how to turn compliance requirements into verifiable deployment decisions on Oracle Cloud Infrastructure. After this lesson, learners will be able to:

- Distinguish storage location, processing location, access permissions, and jurisdiction.
- Build a data inventory along with flow diagrams across services and third parties.
- Evaluate regions, realms, home regions, and identity domains against data scope.
- Design controls for deployments, replication, backups, logs, encryption keys, and support.
- Link each requirement to an owner, verification method, and evidence.
- Balance data location constraints against availability, recoverability, and cost.

The geographic conditions, retention periods, and recovery targets in the examples are **project assumptions**, not legal conclusions for any country. In real deployments, use requirements confirmed by the data owner and compliance function as inputs.

## 2. Distinguishing requirements that are often conflated

### 2.1. Concepts to keep separate

| Concept | Design question to answer |
| --- | --- |
| Data residency | In which geographic locations is data stored? |
| Processing location | Where do applications, analytics, content scanning, or AI jobs process data? |
| Data localization | Is there a requirement to keep or process a data scope within a defined territory? |
| Data sovereignty | What jurisdictional and operational control requirements apply to the data? |
| Access control | Which identities may read, export, modify, or administer the data? |
| Data transfer control | Which flows are permitted to send data to other locations or recipients? |

This is a requirement breakdown for technical design. The binding meaning of each term must be defined in the governing documents applicable to the project.

A system might store its database in an allowed region while still sending full request payloads to an observability platform outside that scope. Another system might never replicate its database to another region, yet support staff can download exports to personal machines. Both scenarios must be examined in the data map.

Encryption protects confidentiality and controls key usage. It does not change the physical location of the ciphertext. Therefore, "encrypted" is not sufficient to confirm a replica location requirement has been met.

### 2.2. Five dimensions of an actionable requirement

A statement like "data must stay in an approved area" is too broad. Break it down into five dimensions:

1. **Object:** which data, including which attributes and derived copies?
2. **Activity:** storage, processing, replication, access, transmission, or deletion?
3. **Location:** which regions, countries, geographic groups, or environment types?
4. **Principal:** which applications, operators, providers, and recipients?
5. **Evidence:** which configurations, logs, service documentation, or approval records prove it?

For example, instead of merely writing "customer data in Europe", a hypothetical project might specify:

> Customer profile payloads, backups, and export files may only be stored or processed in two commercial OCI regions, eu-frankfurt-1 and eu-amsterdam-1. Logs must not contain profile payloads. Identity data flows, operational metadata, and technical support paths must be evaluated separately before placing the system into production.

The condition above still requires verifying feasibility for each service. It does not automatically assert that two regions satisfy all legal, jurisdictional, or operational sovereignty requirements of the project.

## 3. Understanding OCI boundaries accurately

### 3.1. Regions, availability domains, and fault domains

A region is a localized geographic area. Availability domains reside within a region; fault domains separate infrastructure inside an availability domain. Distributing workloads across fault domains or availability domains does not equate to deploying to another region. Availability domain counts and service availability must be verified for the chosen region. [OCI Regions and Availability Domains](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/regions.htm).

When evaluating data residency, distinguish:

- Primary resource location.
- Same-region replica locations.
- Cross-region replica locations.
- Locations of machines or services processing data.
- Transport paths and locations of recipients.

An application running in an allowed region can still read a database outside the allowed scope. Conversely, a database in the right region does not prevent an application from sending data out to an external API.

### 3.2. Compartments are administrative boundaries

Compartments organize resources and grant permissions; they are not geographic locations. The same compartment can contain resources in multiple regions.

Names like `EU-Production` or tags like `Residency=EU` help with classification but do not create a geographic barrier on their own. To treat them as a control, there must be a mechanism to read values, evaluate conditions, and block or detect misconfigurations.

Similarly, a separate tenancy separates administrative scope and accountability. Splitting tenancies does not automatically prove that all services, identity domains, and replicas in a tenancy reside in the desired location.

### 3.3. Home region must be decided early

A tenancy's home region holds IAM definitions and related account information; a tenancy's home region cannot be changed after provisioning. Many IAM resources are cross-regional in scope, and changes propagate across the tenancy's regions. [Managing Regions and Home Region](https://docs.oracle.com/en-us/iaas/Content/Identity/regions/managingregions.htm).

Therefore, do not choose a home region solely based on latency to an administrator's laptop. Before creating a tenancy, evaluate administrative and identity data, the planned region topology, operational requirements, and service availability.

Nor is the home region a mandate forcing all business workloads to run there. Resources such as Compute, buckets, or databases have service-specific deployment locations.

### 3.4. Identity domains have separate replication and DR

The Default identity domain automatically replicates to regions to which the tenancy has subscribed. Additional identity domains have a home region chosen at creation and replicate to other regions only when enabled. Enabling or disabling replication does not alter the identity domain's disaster recovery mechanism. [Identity Domain Replication](https://docs.oracle.com/en-us/iaas/Content/Identity/domains/to-manage-regions-for-domains.htm).

For regions with cross-region DR for identity domains, Oracle manages the DR region pairs. This mechanism must be evaluated separately from customer-configured replication. [Disaster Recovery and Identity Domains](https://docs.oracle.com/en-us/iaas/Content/Identity/domains/disaster_recovery_and_domains.htm).

The design implications are:

- Subscribing to an additional region can affect the data scope of the Default domain.
- An additional domain supports intentional replication choices, but is insufficient on its own to conclude all identity data exists in only one region.
- You must verify DR regions, protected data, and the behavior of the actual domain type.
- "Business payloads in two allowed regions" and "all identity data in one country" must be evaluated as two separate requirements.

Do not satisfy a strict identity requirement merely by looking at the database's region.

### 3.5. Realms and sovereign environment choices

OCI regions are grouped into realms. Oracle EU Sovereign Cloud operates in a realm isolated from standard commercial regions and has a distinct operating model. Choosing a commercial region located in the EU does not mean you are using EU Sovereign Cloud. [Oracle EU Sovereign Cloud](https://docs.oracle.com/en-us/iaas/Content/sovereign-cloud/eu-sovereign-cloud.htm).

When evaluating a sovereign environment, verify location, legal/operational entity model, support personnel, available services, connectivity, contracts, and customer responsibilities.

Even with realm boundaries, applications must still control data export flows executed by authorized users or programs. Do not use a product name as evidence in place of data flow diagrams and deployment configurations.

## 4. Building a data inventory and flow diagram

### 4.1. Do not inventory only primary database tables

An inventory sufficient for design should cover:

| Data category | Places to inspect |
| --- | --- |
| Business payloads | Databases, Object Storage, files, messages, caches |
| Derived copies | Reports, search indexes, analytics datasets, embeddings |
| Recovery copies | Backups, snapshots, standbys, restore targets |
| Operational data | Logs, traces, application errors, crash dumps |
| Identity data | User profiles, authentication attributes, federation configs |
| Keys and secrets | Vault, replicas, related secrets management systems |
| Support data | Ticket attachments, diagnostic bundles, access sessions |
| Development data | Fixtures, exports, test copies, CI/CD artifacts |

Caches or temporary files remain copies for as long as they exist. A log record containing only part of a payload can still carry sensitive information. Renaming fields or omitting usernames does not prove on its own that data is anonymized.

### 4.2. Every flow must have a source, destination, and purpose

For each flow, record at least:

~~~text
Flow ID:
Data owner and approver:
Data category / attributes:
Source: service, tenancy, region:
Destination: service, recipient, location:
Processing purpose:
Transport mechanism and executing identity:
Intermediate storage / cache:
Retention period and deletion method:
Control mechanism:
Evidence to collect:
Unverified points:
~~~

For example, a "database → email service" flow must check whether emails contain customer profiles or only business notification codes. These two payloads can trigger different control requirements. Do not classify an entire flow by service name while ignoring the actual content transmitted.

### 4.3. Reference diagram for location-restricted workloads

~~~mermaid
flowchart LR
    U["User / integrator"] --> A["Application API"]
    subgraph P["Approved primary region"]
        A --> DB["Database"]
        A --> O["Object Storage"]
        A --> L["Payload-free logs"]
        K["Keys / secrets"] --> A
    end
    subgraph S["Approved DR region"]
        DBR["Database recovery copy"]
        OR["Approved object replica"]
        KR["Keys needed for recovery"]
    end
    DB -->|"Verified recovery flow"| DBR
    O -->|"Approved replication"| OR
    K -->|"Per supported service mechanism"| KR
    A --> X["External integration: data assessment required"]
    L --> E["Evidence store in approved location"]
~~~

This diagram is a design model; it does not assert that every Oracle Database service or every Vault type supports the same replication method. Every arrow must be replaced with a concrete mechanism, real location, and verification evidence prior to deployment.

## 5. Turning requirements into a control matrix

### 5.1. Start from acceptance criteria

Every requirement needs clear pass criteria. The example below continues assuming only the two commercial regions `eu-frankfurt-1` and `eu-amsterdam-1` are approved for business payloads.

| ID | Hypothetical requirement | Proposed control | Evidence |
| --- | --- | --- | --- |
| RES-01 | Primary payload in allowed regions | IaC config and region-scoped deployment perms | Plan, inventory, permission test results |
| RES-02 | Replicas and backups also in scope | Verify replication, backup, and restore targets | Source/dest configs, replica catalog |
| RES-03 | Logs exclude profile payloads | Attribute-allowlist logging design | Logger config, inspected log samples |
| RES-04 | Only authorized groups export data | Read/export permissions and download channel controls | IAM, matching access logs, approval records |
| RES-05 | Support receives no real data in standard tickets | Sanitized diagnostic bundle procedure | Bundle template, ticket, and check confirmation |
| RES-06 | Recovery in approved locations | Tested restore/failover scenarios | Drill report, target resources |
| RES-07 | Configuration drift detectable | Periodic inventory and change tracking | Reconciliation output, alerts, and handling |

This matrix is a project design, not a list of features automatically enabled by OCI.

The evidence column helps spot unimplemented requirements. If a team only answers "we picked the right region" for RES-02 without knowing where backups reside, that requirement lacks sufficient evidence.

### 5.2. Assigning ownership

The data owner defines which data falls in scope. Compliance confirms applicable conditions. Platform implements IAM, regions, and shared configurations. Application teams own payloads, logging, and integrations. Operations retains evidence, checks drift, and runs recovery drills.

Oracle and the customer share security responsibility: Oracle is responsible for infrastructure and platform operations within service scope; the customer is responsible for appropriate workload configuration and usage. [OCI Shared Responsibility Model](https://docs.oracle.com/en-us/iaas/Content/cloud-adoption-framework/security.htm).

A provider certification or report can serve as evidence for provider-side controls. It does not prove the customer's application configured backups properly, stripped payloads from logs, or prevented users from exporting data.

## 6. Designing multi-layered controls

### 6.1. Restricting deployment permissions by region

OCI IAM can use the `request.region` condition to restrict where a grant statement applies. Illustrative example for a Compute admin group:

~~~text
Allow group 'Default'/'ResidencyComputeOps' to manage instance-family in compartment RegulatedProd where any {request.region = 'fra', request.region = 'ams'}
~~~

Here, `fra` and `ams` are region keys, different from the region identifiers `eu-frankfurt-1` and `eu-amsterdam-1` used in CLI/provider configurations. Cross-check the region table for the live environment, especially when switching realms. [How to Restrict Access by Region](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/commonpolicies.htm).

The example assumes domain `Default`, the group, and the compartment already exist. It illustrates permissions on `instance-family` only; networking, volume, or dependent resource permissions must be designed separately.

There are two critical limitations:

1. `Allow` statements grant permissions additively. A region-conditioned policy does not revoke broader permissions a principal already received via another policy or group. [How OCI IAM Policies Work](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/policies.htm).
2. Request region does not automatically represent every data destination. For copy, replication, or export APIs, inspect destination parameters and specific permissions used by the service.

Do not assume a `request.region='fra'` statement blocks all copies from Frankfurt elsewhere. Services may evaluate permissions at the source, at the destination, or via specialized condition variables.

For example, copying Block Volume backups involves source and destination permissions; Oracle describes restricting by `request.region` and `target.region` for this case. Use only conditions supported by the corresponding API. [Copying Volume Backups Across Regions](https://docs.oracle.com/en-us/iaas/Content/Block/Tasks/copy-bv-backup.htm).

Beyond user policies, review dynamic groups, workload principals, service principals, and cross-tenancy permissions if any. An inadequately controlled pipeline can create data paths different from standard admin accounts.

### 6.2. Checking configurations before deployment

An IaC pipeline should inspect fields related to data location, not just the provider region variable:

- Primary resource region.
- Replication destination region and bucket.
- Locations of backups, standbys, and resources created during restore.
- Regions of keys, secrets, and replicas.
- Destinations of connectors forwarding logs, traces, or messages.
- External endpoints and intended outbound data.
- Provider aliases or modules that might deploy to another region.

An allowlist can be expressed as design data:

~~~json
{
  "policyVersion": "example-1",
  "dataClass": "customer-profile",
  "allowedStorageRegions": [
    "eu-frankfurt-1",
    "eu-amsterdam-1"
  ],
  "allowedProcessingRegions": [
    "eu-frankfurt-1",
    "eu-amsterdam-1"
  ],
  "allowedReplicaRegions": [
    "eu-frankfurt-1",
    "eu-amsterdam-1"
  ],
  "payloadInApplicationLogs": false,
  "externalExportRequiresApproval": true,
  "identityResidencyReview": "required"
}
~~~

This is an **illustrative project-defined schema**, not an OCI resource or policy you can send directly to an API. The deployment team must build checks that read it, map fields to the plan, and handle unknown fields.

Place check gates in version-controlled pipelines and restrict bypass permissions. Checking a single input variable helps only if every resource and deployment path uses that exact variable.

### 6.3. Preventing unintended data paths

For VCNs and workloads, inspect egress to public APIs, SaaS, email systems, artifact repositories, admin hosts, and on-premises networks. Choose network mechanisms and application policies aligned with approved destinations.

Distinguish **connectivity** permissions from **data read** permissions. An egress-restricted application can still send data to an authorized destination if that destination accepts inappropriate payloads. Someone authorized to download objects can copy them to an external device even while the bucket remains in the right region.

Private endpoints or dedicated links help control access paths. They do not prove the storage, processing, and operational location of the system at the other end. For physical link constraints, verify both the route and the connectivity provider's scope commitments.

For remote administrative access, define permitted devices, download storage locations, copy/paste capabilities, access grant duration, and session logs where needed. This is part of data flow design, not just firewall configuration.

### 6.4. Using Security Zones within their true scope

Security Zones inspect resource operations covered by a recipe's policies and deny violating operations. Control groups can include restricting public access, requiring encryption, and limiting certain resource move/association actions. [Security Zone Policies](https://docs.oracle.com/en-us/iaas/Content/security-zone/using/security-zone-policies.htm).

When applying them, check the specific recipe, resource types, and covered APIs. A security zone is a configuration control boundary; do not equate it with a country or a list of permitted regions.

In the compliance matrix, record exactly which policy protects which path. Do not write vaguely "Security Zones are enabled so no data can leave the area".

### 6.5. Detecting configuration drift and permission changes

Combine periodic inventories with change tracking to detect:

- Resources or replicas appearing in unlisted regions.
- Changes to replication, backup targets, connectors, or endpoints.
- New policies granting broader rights than approved conditions.
- Added group memberships or dynamic group edits granting principals extra privileges.
- Log changes causing sensitive payloads to be recorded.
- Expired exceptions whose configurations remain active.

Tags and resource names aid searching, but reconciliation must rely on actual locations and configurations. Detection tools need sufficient observation permissions; a permission-limited inventory does not prove the rest of the tenancy lacks resources.

## 7. Controls by data layer

### 7.1. Databases, backups, and recovery

For Oracle Database on OCI, lock down the exact product and deployment model before deciding on redundancy mechanisms. Database on Compute, DB System, Exadata, and Autonomous Database differ in features, limits, and administration.

Verification checklist includes:

| Item | Question to answer |
| --- | --- |
| Primary database | What are the service, region, processing location, keys, and access paths? |
| Backup | What are the storage location, schedule, retention, and copy mechanisms? |
| Standby or replica | Which region, what data is synced, and who can change the target? |
| Restore/clone | Where will the system be created, and who can pick the region? |
| Export | To which bucket/host are files written, and where else are they stored? |
| Diagnostic data | Do traces, dumps, or support bundles contain real data? |

Do not assume identical backup behavior across all database services. Keep documentation and configuration of the exact service type in use as evidence.

A restore scenario must account for the database, keys, secrets, identity, networking, and log destinations. Restoring in the right region when required keys reside only in an unavailable or unauthorized location leaves the recovery plan incomplete.

### 7.2. Object Storage and replicas

Object Storage replication specifies a target region and bucket. Creating a replication policy is a configuration change point that must be controlled, not just initial bucket creation. [Creating an Object Storage Replication Policy](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingreplication_topic-To_create_a_replication_policy.htm).

During inventory, also examine:

- Source bucket, destination bucket, and corresponding regions.
- Permissions of who creates or modifies replication.
- Manual copy flows or programs downloading/exporting objects.
- Object versions, in-flight staging copies, and retention policies.
- Copies used for testing, analytics, or third-party integrations.

Disabling a replication stream does not mean previously replicated data has been deleted. Check destination state, retention duration, and evidence of handling existing copies per requirements.

### 7.3. Block Volumes, images, and files

Volume backups, cross-region copies, custom images, and export files can contain application data or secrets written to disk. Do not classify them as "infrastructure-only" when real data resides inside.

When controlling recovery copies, evaluate the entire disk contents, not just the primary data directory. Temporary files, swap, local logs, and caches can make the data scope larger than expected.

### 7.4. Logs, traces, and diagnostic data

Design logging around approved attributes. For example, use business reference IDs and error codes instead of logging full request bodies, attachments, or connection strings.

Before forwarding logs to Object Storage, SIEM, or external observability platforms, inspect payloads, target locations, and access permissions. Audit or logs moved to an investigation store also become data requiring classification.

Stripping payloads at the source is usually easier to control than expecting every downstream system to mask data accurately. However, treat this control as effective only after inspecting real log samples across both success and error paths.

### 7.5. Encryption keys and secrets

Placing keys in an approved location is a separate decision from placing databases or buckets. Verify key region, usage permissions, replication mechanisms, and failover dependencies.

Vault supports replication between regions within the same realm; availability depends on vault type and status. Do not assume every existing vault is replicable or that replicating a vault means secrets share the exact same mechanism. [Vault and Key Replication](https://docs.oracle.com/en-us/iaas/Content/KeyManagement/Tasks/replicatingvaults.htm).

Encryption and key management support data confidentiality controls. They must be paired with controls over replica locations, decryption permissions, and post-decryption processing flows.

### 7.6. Support data and service metadata

Before submitting diagnostic bundles, check for real payloads, tokens, keys, customer names, IPs, or sensitive paths. Use approved procedures to generate synthetic reproducers and minimal support packages.

For data processed by the provider to deliver the service, review the corresponding agreements and service descriptions. Oracle documentation notes that data processing may depend on service terms rather than solely on the customer-selected region. [OCI Data Privacy Features](https://docs.oracle.com/en-us/iaas/Content/Resources/Assets/whitepapers/oci-privacy-features.pdf).

In architecture records, clearly separate customer content, identity data, operational metadata, and commercial info by applicable scope. Unclear cases must be logged as items to verify, not converted into a blanket claim that "all data stays in one region".

## 8. Balancing data residency with availability and cost

### 8.1. Clarify the failure model to withstand

A single-region option can still deploy multiple intra-region redundancy layers. However, that option does not solve an outage rendering the entire region unavailable.

Compare three options against project requirements:

| Option | Primary value | Points to accept or verify |
| --- | --- | --- |
| Single region, intra-region redundancy | Limits location scope, reduces cross-region dependencies | Full-region outage risk and recovery time |
| Two approved regions | Can recover if primary region is lost | Service support, replica flows, keys, and cost |
| No suitable DR region | Preserves existing geographic limits | Must adjust targets, deployment model, or evaluate alternatives |

A target such as **15-minute RPO, 4-hour RTO** is only a hypothetical requirement until proven by architecture and drill results. RPO relates to tolerable data loss; RTO relates to service restoration time. Do not use database replica metrics alone to claim the whole application achieves the same target.

If the residency boundary lacks a compliant standby location, explicitly record the conflict. Do not quietly pick an out-of-scope region just to complete a DR diagram.

### 8.2. Verify every dependency in failover

Failover scenarios must answer:

- In which region will the new application process payloads?
- Where are databases, objects, files, and caches restored from?
- Are decryption keys, secrets, and identities available?
- Do log channels and support systems remain within scope?
- Do DNS, client configs, and endpoints point to approved targets?
- During failback, how are temporary data copies and DR resources handled?

Drill using synthetic or authorized data. Record actual resources created and actual flows generated—not merely checking that a "failover" button finished.

### 8.3. Evaluating cost across the data lifecycle

Budget for standby compute, replica capacity, backups, object versions, log retention, analytical queries, keys, and required connectivity. A small initial replica can grow with retention duration and data churn rate.

Trimming unnecessary data before replicating or forwarding logs can simultaneously reduce cost and control scope. However, deletion timelines must align with business, recovery, and evidence retention requirements.

Spending limits, quotas, and budget alerts serve resource management. To rely on them in compliance design, verify their concrete enforcement scope; cost alerts do not stop data from leaving a location.

## 9. Hands-on lab: inventorying and detecting out-of-list destinations

This lab can start with queries and mock data. There is no need to move real data to an out-of-scope region to prove a design fails requirements.

### 9.1. Preparation

Assume the project approved two regions for payloads:

~~~text
eu-frankfurt-1
eu-amsterdam-1
~~~

Learners need:

- An identity with read permissions for configurations to inspect.
- OCI CLI profile `RESIDENCY_READER` pointing to the right tenancy and endpoint.
- List of in-scope compartments, services, and data categories.
- Permissions to view replication/backup configs or configuration exports provided by an administrator.

Missing read permissions must be recorded as an observation limitation. Do not treat an authorization error as proof that no resources or replication exist.

### 9.2. Listing tenancy region subscriptions

PowerShell example:

~~~powershell
$residencyTenancy = '<TENANCY_OCID>'

$residencyOutput = & oci iam region-subscription list `
    --profile RESIDENCY_READER `
    --tenancy-id $residencyTenancy `
    --all `
    --output json

if ($LASTEXITCODE -ne 0) {
    throw 'Unable to read region subscriptions; check profile and permissions.'
}

$residencyJson = [string]::Join(
    [Environment]::NewLine,
    [string[]]$residencyOutput
)
$residencySubscriptions = $residencyJson |
    ConvertFrom-Json -ErrorAction Stop

if ($null -eq $residencySubscriptions.data) {
    throw 'No data field in query output.'
}

$residencySubscriptions.data | Select-Object `
    @{Name = 'Region'; Expression = { $_.'region-name' }}, `
    @{Name = 'HomeRegion'; Expression = { $_.'is-home-region' }}, `
    status
~~~

This command lists tenancy region subscriptions; `--all` retrieves all result pages for this operation. [CLI Region Subscription Reference](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/iam/region-subscription/list.html).

The output is only a tenancy inventory step. A subscribed region does not mean all data may be deployed there; a resource absent from the current screen does not prove the entire tenancy lacks such resources.

Next, reconcile the home region and region subscriptions with the IAM/identity domain assessment. Do not modify subscriptions during an inventory exercise just to make the list look cleaner.

### 9.3. Inventorying replication paths, not just primary resources

Pick an assigned workload and build a table:

| Component | Data | Source region | Destination region | Observed configuration |
| --- | --- | --- | --- | --- |
| Primary database | Customer profiles | Primary region | Not applicable | Service and OCID |
| Database recovery plan | Recovery copies | Primary region | DR region | Mechanism of exact service |
| Document bucket | Business files | Primary region | If replicated | Policy and destination bucket |
| Application logs | Approved fields | Processing region | Central store | Connector or agent |
| Keys | Workload-required keys | Key region | If replicated | Vault/key metadata |
| Support exports | Sanitized data | Generation site | Recipient site | Process and approval record |

If a destination is unknown, record `UNKNOWN` and keep it on the action list. Do not substitute the source region by guesswork.

### 9.4. Checking a simulated design

The following PowerShell snippet only checks an in-memory mock list. It makes no API calls and alters no resources:

~~~powershell
$allowedDataRegions = @(
    'eu-frankfurt-1',
    'eu-amsterdam-1'
)

$designLocations = @(
    [pscustomobject]@{
        Component = 'Primary database'
        Region = 'eu-frankfurt-1'
    },
    [pscustomobject]@{
        Component = 'Object replica'
        Region = 'us-ashburn-1'
    },
    [pscustomobject]@{
        Component = 'Recovery environment'
        Region = 'eu-amsterdam-1'
    }
)

$residencyViolations = @(
    $designLocations | Where-Object {
        $allowedDataRegions -notcontains $_.Region
    }
)

if ($residencyViolations.Count -gt 0) {
    $residencyViolations | Format-Table Component, Region
    throw 'Design contains locations outside the approved list.'
}
~~~

Expected output is detecting `Object replica` in `us-ashburn-1` and throwing an error. This is a condition of the example, not a conclusion that Ashburn is prohibited for every project.

To apply this in a real pipeline, extract locations from actual plans or configurations, covering module/provider aliases, destination parameters, and unknown components. A manually typed list only checks that list itself.

### 9.5. Verifying permissions and deployment paths in a test environment

If an admin-provided test environment is available, use a pipeline-representative identity to test in-scope operations:

- Do required operations in allowed regions have sufficient permissions?
- Are corresponding out-of-scope operations blocked by the expected controls?
- Do other groups or policies grant the principal broader permissions?
- Do copy/replication APIs properly check both source and destination?
- Do direct Console or API changes create a bypass around the pipeline?

Use empty resources or synthetic data, approved operations, and appropriate verification mechanisms. Never use real data to test whether a transport path is valid.

Lab output is a clearly scoped inventory, one identified non-compliant flow, and a re-testable control plan. This output does not replace full service and contract reviews for a production system.

## 10. Evidence and continuous operations

### 10.1. An evidence package sufficient to reproduce conclusions

An evidence package can include:

- Approved requirements and versioned list of allowed locations.
- Data flow diagrams showing sources, destinations, data categories, and owners.
- Region subscriptions, home region, and identity domain/DR assessments.
- Actual configurations of resources, replicas, backups, and keys.
- Effective policies, permission check scopes, and verification results.
- Pipeline gate results alongside direct deployment paths.
- Evidence of payload exclusion from logs and control of log forwarding destinations.
- Restore/failover/failback drill reports and handling of temporary copies.
- Service documentation, terms, and required provider attestations.

Each record should include collection timestamp, source, tenancy, region, compartment, and collector identity where applicable. Save configuration exports sufficient for re-verification while protecting the records themselves, as they may contain sensitive metadata.

Distinguish three types of evidence: documentation describing service capabilities, enabled configuration, and live observed results. A documentation page saying "supports region restriction" does not prove the restriction is active for the project's principals.

### 10.2. Re-evaluating upon changes

Events that should trigger a review include:

- Subscribing to a new region or creating a new identity domain.
- Adding database, AI, analytics, or third-party integration services.
- Changing replica regions, backup targets, or endpoints.
- Routing logs to a central store or altering logger contents.
- Granting new export, service principal, or cross-tenancy permissions.
- Changing support providers or diagnostic procedures.
- Changing data scope, contracts, or retention periods.

Also reconcile actual configurations against the design periodically. Resources created outside pipelines or emergency incident changes can cause the two to diverge.

### 10.3. Managing time-bound exceptions

An exception must specify the data, flow, location, reason, owner, approver, expiration, compensating controls, and termination procedure. If platform conditions do not permit approving an exception, change the solution instead of merely logging the risk.

When an exception ends, verify both halting the flow and handling created data: export files, destination buckets, backups, caches, data on recipient systems, and temporary permissions.

In emergencies, break-glass procedures must still define action scope, record evidence, and require post-incident review. Rapid recovery needs must be built into the design beforehand.

## 11. Conclusions to avoid

| Hasty conclusion | Appropriate verification method |
| --- | --- |
| "Database is in the right region so the whole system meets residency" | Inventory all replicas, processing flows, and recipients |
| "Compartment name already states the region" | Verify actual locations and enforcement mechanisms |
| "Encrypted, so it can be copied anywhere" | Separately check replica locations and key requirements |
| "Region policy exists so all export paths are blocked" | Check additive permissions, target APIs, and exports |
| "Domain only replicates where chosen so no DR exists elsewhere" | Separately evaluate service replication and DR |
| "Using an EU region means using EU Sovereign Cloud" | Verify realm, environment type, and agreements |
| "No resources seen so no out-of-scope data exists" | Check observation permissions, regions, and inventory scope |
| "Disabling replication means old data was deleted" | Check remaining copies and cleanup procedures |
| "Provider is certified so the application is compliant" | Map shared responsibilities and check workload configs |

A well-founded deployment decision must link **which data, which activity, which location, which principal, and which evidence**. In OCI, this method connects compliance requirements to regions, IAM, backups, networking, and operations, while surfacing unverified conditions before the system handles real data.
