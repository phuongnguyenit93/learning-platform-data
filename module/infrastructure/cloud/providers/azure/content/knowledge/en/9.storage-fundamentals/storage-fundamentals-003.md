# LRS, ZRS, GRS, and GZRS Redundancy

When deploying an application on Microsoft Azure, storing files, images, logs, backups, and transactional data often depends on Azure Storage. If a disk, server, datacenter, or an entire Azure region experiences an outage, will your data survive? Can the application still read and write immediately? If you have to fail over to a backup region, how much recently written data might be lost?

These questions relate to **storage redundancy** — how Azure maintains multiple copies of data to minimize data loss from infrastructure failures. For a Standard Storage Account, the four primary models are:

- **LRS — Locally Redundant Storage:** replicated within a single physical location in the primary region.
- **ZRS — Zone-Redundant Storage:** replicated synchronously across availability zones in the primary region.
- **GRS — Geo-Redundant Storage:** replicated within the primary region and asynchronously to a second region.
- **GZRS — Geo-Zone-Redundant Storage:** combines cross-zone replication in the primary region with asynchronous replication to a second region.

This lesson belongs to the **Azure Storage Fundamentals** chapter of the **CLOUD_PROVIDERS_AZURE** module. Within an Azure application architecture spanning subscriptions, resource groups, networking, compute, storage, and data, choosing redundancy directly impacts fault tolerance, disaster recovery design, performance, cost, and operational planning.

> **Key takeaway:** Redundancy increases data preservation against infrastructure faults, yet **it is not synonymous with backup**, does not by itself guarantee application uptime, and does not eliminate the need for disaster recovery design.

## 1. Learning Objectives

After studying this lesson, you will be able to:

1. Distinguish **durability** (data preservation), **availability** (accessibility), **RPO**, and **RTO**.
2. Explain the replication scope and mechanics of LRS, ZRS, GRS, and GZRS.
3. Evaluate fault tolerance across disk, zone, and region failures for each option.
4. Understand **intra-region synchronous replication**, **cross-region asynchronous replication**, and the risk of un-replicated data during failover.
5. Distinguish GRS/GZRS from **RA-GRS/RA-GZRS**, especially read access in the secondary region.
6. Select redundancy based on SLAs/SLOs, recovery requirements, data types, supported regions, and budget.
7. Create and inspect a Storage Account using the Azure Portal, Azure CLI, or Bicep.
8. Plan for failover, verify data, and layer on backups, versioning, soft delete, and monitoring.

## 2. Foundational Concepts to Separate

### 2.1. Region and Availability Zone

An **Azure region** is a geographic deployment area, such as **Southeast Asia**. Many regions provide **availability zones**: physically separated infrastructure locations within the same region, with independent power, cooling, and networking tailored to zone architecture.

Conceptual diagram:

~~~text
Azure Region A (primary)
├── Availability Zone 1
├── Availability Zone 2
└── Availability Zone 3

Azure Region B (secondary)
└── Geo-replicated location per service mechanism
~~~

Not every region supports every redundancy option, Storage Account kind, or SKU equally. The secondary region for geo-redundant storage is determined by Azure's supported region-pairing/geographic mechanism; you cannot assume you can arbitrarily pick any secondary region.

### 2.2. Durability vs. Availability

- **Durability:** the probability that successfully written data remains preserved, even if some storage components fail.
- **Availability:** the service's ability to accept read or write requests at the moment users access it.
- **Resiliency:** the ability to continue or recover operations when faults occur.
- **Disaster recovery (DR):** procedures for restoring a system when an incident exceeds normal operating boundaries.

For example: data replicas may remain intact after a regional outage, yet the application cannot write to the primary endpoint until failover or recovery completes. In that moment, **durability** can remain high while **write availability** is interrupted.

Conversely, a system may have a healthy endpoint while the application accidentally overwrites a valid file with bad content: redundancy may replicate that very bad content. That is not a physical fault that redundancy is designed to solve.

### 2.3. RPO and RTO

Two metrics commonly used in recovery design:

| Metric | Question to Answer | Business Requirement Example |
|---|---|---|
| **RPO — Recovery Point Objective** | What is the maximum acceptable loss of recent data? | "Must not lose more than 15 minutes of transactions." |
| **RTO — Recovery Time Objective** | After an incident, how quickly must the system be operational again? | "The application must recover within 2 hours." |

The numbers above are **illustrative requirements only**, not Azure Storage guarantees. With geo-redundant storage, cross-region replication is **asynchronous**: data acknowledged as written in primary may not yet have reached secondary if primary is lost completely.

Redundancy alone does not prove a system meets RPO/RTO. You must account for replication lag, failover procedures, DNS/client retries, networking, compute, databases, access permissions, and real recovery testing.

### 2.4. Synchronous and Asynchronous Replication

**Synchronous replication:** a write operation is acknowledged only after meeting write requirements across the mandatory replicas within the service's synchronous boundary. This model minimizes loss of acknowledged data during certain component or zone failures.

**Asynchronous replication:** the primary can acknowledge a write before that data version has finished transferring to the secondary. This supports large geographic distances, but introduces **replication lag** and the risk of losing unsynchronized changes if an abrupt switch to the secondary occurs.

In Azure Storage:

- LRS and ZRS use synchronous replication within their respective scopes in the **primary region**.
- GRS maintains LRS replicas in primary and replicates **asynchronously** to the secondary region.
- GZRS maintains ZRS replicas in primary and replicates **asynchronously** to the secondary region.

## 3. LRS — Locally Redundant Storage

### 3.1. How It Works

LRS maintains **three copies of data** within **a single physical location** in the primary region.

~~~mermaid
flowchart TB
    C["Application"] --> A
    subgraph PrimarySite["Single physical location in primary region"]
      A["Replica 1"] --- B["Replica 2"]
      B --- D["Replica 3"]
    end
~~~

Replicas are written synchronously under the LRS design. When a disk or storage hardware component fails, the system can use the remaining replicas to preserve data.

However, because replicas are concentrated in a single physical location, LRS is **not designed to survive the loss of that entire location or the primary region** the way a multi-zone or multi-region model does.

### 3.2. When to Choose LRS?

LRS fits when:

- Data can be recreated from another source.
- Development, testing, or sandbox workloads have lower availability requirements.
- The application has another tested DR/backup mechanism.
- Budget is a significant factor and the risk of losing the entire location is accepted as a business decision.

Example: a build system producing intermediate artifacts that can be regenerated from repositories and pipelines. LRS can be a sensible choice if temporary data loss does not violate service commitments.

**Do not infer** that LRS fits all infrequently accessed data. Low read frequency does not mean the data is unimportant.

### 3.3. Limitations

- Does not provide independent replicas across multiple availability zones.
- Does not provide a secondary region copy from the LRS mechanism.
- If a region goes down, choosing LRS alone provides no ready target for cross-region failover.
- Logical faults such as accidental deletion, overwrites, or malware still require separate data protection measures.

## 4. ZRS — Zone-Redundant Storage

### 4.1. How It Works

ZRS maintains data replicas **synchronously across three availability zones** within the same primary region in supported regions/services.

~~~mermaid
flowchart TB
    C["Application"] --> Z1
    subgraph PrimaryZones["Primary region — multiple Availability Zones"]
      Z1["Zone 1<br/>Replica"]
      Z2["Zone 2<br/>Replica"]
      Z3["Zone 3<br/>Replica"]
    end
    Z1 <--> Z2
    Z2 <--> Z3
~~~

When one zone experiences an outage, replicas in the remaining zones enable the service to continue operating within ZRS capabilities. ZRS is therefore suitable for data requiring zone-level fault tolerance.

For writes acknowledged as successful under ZRS synchronous replication, a single-zone outage does not normally introduce inter-zone replication lag the way asynchronous geo-replication can.

### 4.2. When to Choose ZRS?

ZRS is worth considering when:

- Production workloads need higher availability against a single availability zone failure.
- Compute or applications are deployed across multiple zones, and the storage tier also needs a zone-resilient model.
- Data must remain within a single region by policy or does not require a geographic replica.
- The organization wants stronger durability/availability than LRS without requiring geo-redundancy.

Example: a web API running across multiple availability zones using Blob Storage for attachments. If compute spans zones while storage uses only LRS, a storage site outage can still become the weak link in the architecture.

### 4.3. Limitations

- ZRS **has no copy in another region** from ZRS alone.
- If the entire primary region loses service capability, ZRS alone does not solve multi-region DR requirements.
- Not every region, account kind, access tier, or storage service permits ZRS configuration.
- Even if storage survives a zone failure, the workload can still go down if VMs, databases, DNS, or networking are not designed multi-zone.

## 5. GRS — Geo-Redundant Storage

### 5.1. How It Works

GRS combines:

1. **LRS in the primary region:** data is synchronously replicated to three copies within one physical location.
2. **Asynchronous geo-replication:** changes from primary are transferred to an Azure-designated secondary region.
3. **LRS in the secondary region:** received data maintains LRS replicas in the secondary.

Conceptually, GRS maintains **six copies** (three in primary and three in secondary) once geo-replication catches up.

~~~mermaid
flowchart LR
    A["Application write"] --> P["Primary region<br/>LRS: 3 replicas"]
    P -. "Asynchronous<br/>geo-replication" .-> S["Secondary region<br/>LRS: 3 replicas"]
~~~

**Core point:** a write acknowledged as successful by primary **does not mean** the secondary has received it immediately.

### 5.2. Value of GRS

GRS provides additional data preservation against a **severe outage in the primary region**, thanks to replicas in a second region.

Suitable when:

- Multi-region DR is required.
- The risk of losing the primary region is considered material.
- The workload tolerates a non-zero RPO due to asynchronous replication, or adds supplementary measures for ultra-critical data.
- Zone resilience in the primary is not mandatory, or is handled in another architectural layer.

### 5.3. GRS Does Not Automatically Create an Active–Active Application

With **standard GRS**, applications cannot normally write to the secondary. The secondary is a recovery replica managed by the service mechanism, not an independent writable Storage Account that the application can treat as multi-master.

When the primary region goes down, you must examine the **failover procedure** according to Storage Account kind, supportability, and Azure orchestration mechanisms. Service interruption, role reversal between regions, and loss of writes not yet replicated to secondary may occur.

If an application demands continuous user serving in two regions, GRS **alone** is not enough: you must design compute, DNS/traffic routing, identity, databases, connectivity, and state management accordingly.

## 6. GZRS — Geo-Zone-Redundant Storage

### 6.1. How It Works

GZRS combines two layers of protection:

- **ZRS in the primary region:** data is synchronized across availability zones in the primary region.
- **Asynchronous geo-replication** to the secondary region.
- **LRS in the secondary region:** the second copy is stored with local redundancy inside the secondary region.

~~~mermaid
flowchart LR
    C["Application"] --> P["Primary region<br/>ZRS: Zone 1, 2, 3"]
    P -. "Asynchronous<br/>geo-replication" .-> S["Secondary region<br/>LRS: 3 replicas"]
~~~

GZRS thus pairs **single-zone fault tolerance in primary** with the existence of a **geographic replica** for regional disasters.

### 6.2. When to Choose GZRS?

GZRS suits critical workloads when both requirements exist simultaneously:

1. You want higher continuity of data access if a single availability zone in primary fails.
2. You need a copy in a secondary region to build a disaster recovery plan.

Example: a production ordering system spanning multiple zones and storing transaction documents, while the organization also wants multi-region DR readiness. GZRS is usually a stronger candidate than LRS or GRS when primary zone resilience is mandatory.

### 6.3. Limitations to Remember

- Only the **primary** uses ZRS in standard GZRS; the **secondary** uses LRS, not ZRS.
- Cross-region replication remains **asynchronous**, so the risk of data loss during regional failover persists.
- Not every region and Storage Account supports GZRS/RA-GZRS.
- Costs may exceed single-region options; compare actual pricing by SKU and service.

## 7. Comparison Table: LRS, ZRS, GRS, GZRS

| Characteristic | LRS | ZRS | GRS | GZRS |
|---|---|---|---|---|
| Primary scope | Single physical location | Three availability zones | Single physical location | Three availability zones |
| Primary mechanism | Synchronous, 3 replicas | Synchronous across zones | Synchronous, 3 replicas | Synchronous across zones |
| Has secondary region | No | No | Yes | Yes |
| Secondary replica type | — | — | LRS | LRS |
| Cross-region sync | — | — | **Asynchronous** | **Asynchronous** |
| Designed for primary single-zone fault tolerance | Not a goal of LRS | Yes | Not a goal of primary LRS | Yes |
| Has replica for regional DR | No | No | Yes | Yes |
| Risk of losing un-replicated writes on failover | Geo N/A | Geo N/A | Yes | Yes |
| Direct secondary reads in base configuration | No | No | No; see RA-GRS | No; see RA-GZRS |
| Typical use cases | Labs, recreatable data | Production prioritizing zone resilience | Multi-region DR | Production needing zone + DR region |

**Interpret accurately:** "has replica for regional DR" does not mean "the other region is immediately writable" or "RPO equals 0." The table describes data protection goals, not a guarantee of overall application status.

### 7.1. Behavior Under Different Failure Scenarios

| Failure Type | LRS | ZRS | GRS | GZRS |
|---|---|---|---|---|
| Single disk or storage hardware fails | Local replicas exist | Cross-zone replicas exist | Local and geographic replicas exist | Cross-zone and geographic replicas exist |
| One availability zone goes down | No cross-zone design | Fault-tolerant per ZRS | Primary remains LRS in one location | Primary fault-tolerant per ZRS |
| Entire primary region suffers severe outage | No secondary | No secondary | Replicated data in secondary, requires failover process | Replicated data in secondary, requires failover process |
| File accidentally deleted or overwritten with wrong content | Not protected by redundancy alone | Same | Logical error can be replicated | Same |
| Identity compromised and data deleted | Needs separate controls/backup | Needs separate controls/backup | Needs separate controls/backup | Needs separate controls/backup |

## 8. RA-GRS and RA-GZRS: Reading from Secondary

In supported account kinds and services, Azure offers two variants:

- **RA-GRS — Read-Access Geo-Redundant Storage.**
- **RA-GZRS — Read-Access Geo-Zone-Redundant Storage.**

**RA** stands for **read access** at the secondary endpoint; it does not mean the application can write normally to the secondary while primary is active.

~~~mermaid
flowchart LR
    W["Write client"] --> P["Primary endpoint<br/>Read / Write"]
    P -. "Async replication" .-> S["Secondary endpoint<br/>Read-only"]
    R["Fallback read client"] --> S
~~~

### 8.1. When Is RA Useful?

RA-GRS or RA-GZRS can help when an application has tasks that **can tolerate stale reads** and wants to continue querying the secondary replica in appropriate scenarios, such as:

- Reading archival documents or rarely changing reference data.
- Testing a fallback read path without executing an account failover.
- Reading data while primary is temporarily unavailable, if the secondary endpoint remains operational and is supported by the service type.

However, the secondary replica **may lag behind primary**. Do not use secondary for business logic requiring **read-after-write consistency** right after writing to primary.

### 8.2. Secondary Endpoint

For Blob Storage, the secondary endpoint typically follows the pattern:

~~~text
Primary:   https://<storage-account-name>.blob.core.windows.net/
Secondary: https://<storage-account-name>-secondary.blob.core.windows.net/
~~~

This is an example pattern for the **Blob service**; not every Storage resource type uses the exact same hostname. Before deploying, verify the endpoints returned for your account kind and service, network access, authentication, and support conditions on the secondary.

RA does not make replication synchronous, nor does it automatically reroute application read traffic. The application or SDK must implement business-appropriate secondary-selection/fallback-read logic. When using the secondary endpoint, the application should surface or handle the possibility of stale data.

### 8.3. How Does GRS Differ from RA-GRS?

GRS still maintains a geographic replica, yet does not provide standard direct read access on the secondary prior to failover. RA-GRS adds secondary read capability under supported conditions. Similarly, GZRS and RA-GZRS differ in secondary read access, not in whether the secondary uses ZRS.

## 9. Geo-Replication, Replication Lag, and Failover

### 9.1. Lifecycle of a Write Operation

Suppose a user uploads the file **invoice-1042.pdf**:

1. The client sends a write request to the primary endpoint.
2. Azure acknowledges once the write satisfies **synchronous replication requirements in primary** (LRS or ZRS depending on SKU).
3. **Asynchronous geo-replication** continues transferring the data to the secondary when using GRS/GZRS.
4. Once the secondary receives and applies the change, the geographic replica catches up closer to primary's state.

If the primary region is completely lost immediately after step 2, the file may **not yet** exist in the secondary. This risk is why GRS/GZRS must never be treated as an RPO=0 solution across every regional disaster.

### 9.2. Last Sync Time

Azure exposes geo-replication status information, including **Last Sync Time** where applicable. This indicator helps gauge the point up to which data has synchronized as reported by the service.

When interpreting it:

- If the sync timestamp is close to current time, the amount of data at risk of not reaching secondary may be smaller.
- If the timestamp lags far behind current time, watch for replication lag or replication health issues.
- **Last Sync Time is not a fixed RPO SLA** and does not guarantee the exact amount of data that could be lost in every scenario.
- Availability of this status field depends on redundancy type, service, and corresponding visibility support.

To assess real RPO, beyond sync timestamps you should monitor write throughput, application mechanics, transaction logging, and post-failover data reconciliation.

### 9.3. What Is Account Failover?

**Failover** shifts the primary role to the secondary region in Azure-supported account types, services, and scenarios. Its goal is to allow applications to continue using the Storage Account after an outage in primary.

Key points:

1. Failover **is not reading the secondary** via an RA endpoint.
2. Failover may mean writes that were not yet geo-replicated **are absent on the new primary**.
3. Switchover duration, endpoint reuse behavior, DNS caching, and client retries must be anticipated.
4. After failover, **the redundancy configuration may change**; check the new state and plan to re-establish geo-redundancy per documentation.
5. Not every Storage Account kind or feature supports identical failover types.
6. Some scenarios provide planned failover or unplanned failover mechanisms; requirements for primary availability, ability to prevent data loss, and operational consequences differ. Consult current documentation before deciding.

A solid DR choice requires a clear **runbook**, not merely selecting "GRS" on the account creation screen.

### 9.4. What Happens to the Application During Failover?

Even if storage transitions roles cleanly, the application can still fail because:

- Application VMs, AKS, App Service, or databases have not been recovered in the new region.
- DNS, private endpoints, firewalls, VNets, and routing are not ready.
- Clients still cache old endpoint information or lack proper retry/backoff logic.
- Identities, managed identities, RBAC, keys/secrets, and app dependencies are not configured for DR.
- Storage Account data and database data have **different recovery timestamps**, causing business state inconsistencies.

Therefore, design **recovery for the entire workload**, not just storage redundancy.

## 10. Redundancy Is Not Backup

This is the most frequently misunderstood area when moving systems to the cloud.

**Replication** protects against infrastructure faults or maintains a near-current replica. **Backup** enables restoring data to a prior version/point in time, addressing accidental deletions, overwrites, ransomware, or application bugs.

Examples:

- An employee accidentally deletes a blob.
- An API bug overwrites a valid file with empty content.
- A compromised identity deletes or modifies data via authorized APIs.
- A deployment script mistakenly alters metadata and lifecycle rules.

LRS, ZRS, GRS, and GZRS **do not automatically restore older versions** in these cases. Logical changes can be replicated to other copies, including the secondary region.

### 10.1. Additional Protections for Blob Storage

Depending on data type and service, consider:

| Measure | Objective |
|---|---|
| Blob soft delete | Allows recovering deleted blobs within a configured retention period |
| Container soft delete | Supports recovering deleted containers within an appropriate period |
| Blob versioning | Retains blob versions so you can revert to prior versions per policy |
| Point-in-time restore | Restores data to an earlier timestamp within supported service/condition boundaries |
| Immutable storage | Protects data against unauthorized deletion/modification for a configured retention interval |
| Independent backup | Provides managed recovery points with isolated scope and retention targets |
| Least privilege and logging | Restricts delete/modify permissions and investigates anomalous changes |

Not every data protection feature is available across all Blob types, account kinds, redundancies, or access tiers. Designs must match the actual service used and recovery goals; avoid assuming features are enabled simply because a Storage Account exists.

### 10.2. Example Data Policy

The Orders application stores invoices and requires:

- Resilience against a single availability zone failure.
- A replica for regional DR.
- Recovery of accidentally deleted files within an internal retention window.
- Audit evidence and restrictions on who can delete data.

**GZRS or RA-GZRS** addresses infrastructure fault tolerance, while **soft delete/versioning/backup/immutability and RBAC** address version recovery and deletion/modification risks. One redundancy option alone cannot replace all of them.

## 11. Selecting a Model Based on Business Requirements

Decide around three major questions:

1. **What is the largest failure you must survive?** A disk, a storage facility, an availability zone, or an entire region?
2. **How much data loss and downtime can the workload tolerate?** Set concrete RPO/RTO targets.
3. **Do the service/region support that SKU and is the cost justified?**

### 11.1. Quick Decision Tree

~~~mermaid
flowchart TD
    A["Start: storage requirements"] --> B{"Need replica in<br/>a second region?"}
    B -->|No| C{"Need availability zone<br/>fault tolerance?"}
    C -->|No| L["Consider LRS"]
    C -->|Yes| Z["Consider ZRS"]
    B -->|Yes| D{"Primary needs<br/>zone resilience?"}
    D -->|No| G["Consider GRS"]
    D -->|Yes| GZ["Consider GZRS"]
    G --> E{"Need secondary reads<br/>before failover?"}
    GZ --> E
    E -->|Yes| RA["Consider RA-GRS / RA-GZRS variants"]
    E -->|No| F["Keep GRS / GZRS"]
~~~

This tree **does not replace checking SKU support, compliance requirements, RPO/RTO, and cost**. If you require RPO=0 across a full regional outage or multi-region active–active writes, you must design additional solutions at the data/application layer rather than treating GRS/GZRS alone as sufficient.

### 11.2. Four Illustrative Scenarios

| Workload | Requirement | Suggested Choice | Rationale |
|---|---|---|---|
| Recreateable build cache | Low cost, no geographic DR needed | **LRS** | Local replicas suffice for accepted risk level |
| Attachments for a multi-zone web app | Protection against single-zone failure, no regional DR | **ZRS** | Synchronous replication across zones |
| Reporting data needing a secondary-region copy | Multi-region DR, tolerates geo lag | **GRS** | Asynchronous replication to secondary region |
| Transaction documents for Orders system | Needs zone resilience and DR region | **GZRS** | Combines ZRS primary with geographic replica |

For transactional systems with very strict RPOs, supplement with application/database/backup mechanisms to meet targets. Never claim "GZRS guarantees zero transaction loss" in every disaster.

## 12. Supportability by Region, Account Kind, and Service

Before creating a Storage Account, distinguish **Storage Account redundancy** from durability mechanisms of other storage products.

### 12.1. Standard GPv2 Does Not Mean Every Service Has Identical Support

For a **general-purpose v2 Storage Account (StorageV2)**, Standard redundancy options are commonly used for Azure Blob Storage and supported services. However:

- Certain access tiers, account kinds, or features have restrictions when combined with ZRS, GZRS, or RA variants.
- **Azure Files** has its own SKU and feature support conditions.
- **Premium storage** has a different SKU list and may not offer all four models like Standard accounts.
- **Managed disks** are a different resource type from a GPv2 Storage Account; do not infer managed disk redundancy or failover behavior from Blob Storage tables.
- Services with dedicated storage engines may publish separate redundancy policies.

When encountering an "SKU not available" error, check **region, account kind, service, access tier, active features, and subscription** before altering architecture. Do not automatically downgrade to a lower SKU if doing so violates DR requirements.

### 12.2. Primary and Secondary Regions

With GRS/GZRS, Azure uses a secondary region as supported by the service. The secondary location may carry data, compliance, or business-design constraints. Evaluate:

- Data residency and jurisdictional requirements.
- Networking and application recovery capabilities in the secondary.
- Data transfer, storage, recovery, and cross-region traffic fees.
- Location of backup systems or data analytics platforms.
- Support for RA or customer-managed failover for the specific account kind.

Not every combination of primary region and residency requirement aligns with default geo-redundancy choices. Confirm the priority order among legal compliance, durability, and DR.

## 13. Azure CLI Practice: Creating and Inspecting a Storage Account

**Assumed environment:** you have a subscription authorized for lab use, Azure CLI signed in, a resource group without production data, and you want to test a **StorageV2** Storage Account. The commands below are Bash/Azure Cloud Shell examples; **do not execute lesson commands on real accounts without verifying cost and permissions**.

### 13.1. Create a Resource Group for the Lab

~~~bash
az login
az account set --subscription "<subscription-id>"
az account show --output table

RG="rg-storage-redundancy-lab"
LOCATION="southeastasia"

az group create \
  --name "$RG" \
  --location "$LOCATION"
~~~

A resource group is merely a management container. Setting a region for the resource group **does not force** resources inside it to reside in that exact region; always specify the region explicitly for the Storage Account.

### 13.2. Create a Storage Account with LRS

The Storage Account name must be **globally unique**, 3 to 24 characters long, and consist solely of lowercase letters and digits. Replace the placeholder name with a valid unused value.

~~~bash
STORAGE_NAME="<yourgloballyuniquestorageaccount>"

az storage account create \
  --name "$STORAGE_NAME" \
  --resource-group "$RG" \
  --location "$LOCATION" \
  --kind StorageV2 \
  --sku Standard_LRS
~~~

The example uses **Standard_LRS** to avoid zone/geo prerequisites while learning basic operations. When creating another new Storage Account in supported regions and services, you can choose corresponding SKUs such as:

~~~text
Standard_LRS
Standard_ZRS
Standard_GRS
Standard_GZRS
~~~

For read-access secondary variants, the related SKU names are typically **Standard_RAGRS** or **Standard_RAGZRS** in Azure CLI/API syntax. Do not assume support from the SKU name alone: verify region, features, and account kind.

### 13.3. Read the Applied Redundancy Configuration

~~~bash
az storage account show \
  --name "$STORAGE_NAME" \
  --resource-group "$RG" \
  --query "{name:name,kind:kind,sku:sku.name,location:primaryLocation,secondary:secondaryLocation,primaryStatus:statusOfPrimary,secondaryStatus:statusOfSecondary}" \
  --output json
~~~

**Illustrative example output, not from a live run:**

~~~json
{
  "name": "storderslabexample",
  "kind": "StorageV2",
  "sku": "Standard_LRS",
  "location": "southeastasia",
  "secondary": null,
  "primaryStatus": "available",
  "secondaryStatus": null
}
~~~

With LRS, there is no secondary region from geo-redundancy. If GRS/GZRS is created, the secondary field and status may display corresponding values depending on the service and inspection timing.

This output verifies management configuration, **not that the application has backups or has tested failover**.

### 13.4. List Accounts in the Resource Group

~~~bash
az storage account list \
  --resource-group "$RG" \
  --query "[].{name:name,sku:sku.name,kind:kind,primary:primaryLocation,secondary:secondaryLocation}" \
  --output table
~~~

This table is handy when auditing redundancy distribution across applications. In production, you can combine tags like **application**, **environment**, **owner**, and **dataClassification** with Azure Policy or organizational audit scripts.

### 13.5. Is Changing Redundancy Just a Simple Update Command?

**Do not assume so.** Conversion feasibility depends on the source–target pair, region, account type, service, enabled features, and data migration conditions.

Some redundancy changes are permitted directly in supported scenarios. Other changes require a migration process, prerequisite checks, or creating a new Storage Account and moving data according to a plan.

Before changing LRS → ZRS, GRS → GZRS, or any other pair:

1. Check **supported conversion paths** for the specific account kind and region.
2. Review the migration process, duration, limits, and object/feature prerequisites.
3. Audit applications, private endpoints, identities, access policies, lifecycle rules, and backups.
4. Assess potential availability impact, new pricing, and rollback.
5. Perform in a test environment or during an approved change window.
6. Verify the SKU and replication status after conversion.

Do not run **az storage account update --sku** on production under the assumption that every SKU pair converts instantaneously or without service impact.

## 14. Declaring Redundancy with Bicep

IaC keeps redundancy configuration consistent across pipeline deployments. The Bicep template below creates a new Storage Account, selects the SKU via a parameter, and sets basic security options.

~~~bicep
@description('Valid and globally unique Storage Account name')
param storageAccountName string

@description('Azure region for the Storage Account')
param location string = resourceGroup().location

@description('Standard redundancy type for the account')
@allowed([
  'Standard_LRS'
  'Standard_ZRS'
  'Standard_GRS'
  'Standard_GZRS'
])
param redundancy string = 'Standard_ZRS'

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  kind: 'StorageV2'
  sku: {
    name: redundancy
  }
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
  tags: {
    application: 'orders'
    environment: 'lab'
  }
}

output storageAccountId string = storage.id
~~~

The **@allowed** choices are constraints of **this example**, not an exhaustive list of Azure SKUs. Depending on workload type, verify support conditions and additional security requirements such as Key Vault, network access, private endpoints, and identity.

Save the contents to **storage-redundancy.bicep**, then preview changes:

~~~bash
az deployment group what-if \
  --resource-group "$RG" \
  --template-file storage-redundancy.bicep \
  --parameters storageAccountName="<uniquename>" redundancy="Standard_ZRS"
~~~

After verifying regional support and the what-if output, deploy in the lab:

~~~bash
az deployment group create \
  --resource-group "$RG" \
  --name "deploy-storage-redundancy-lab" \
  --template-file storage-redundancy.bicep \
  --parameters storageAccountName="<uniquename>" redundancy="Standard_ZRS"
~~~

**Warning about existing configurations:** this Bicep template is an example for greenfield creation. Pointing it at a running Storage Account may unintentionally overwrite properties or fail due to unsupported SKU changes. Manage the **full desired state** of the resource, inspect what-if output, and run controlled change processes.

## 15. Practice via Azure Portal

### 15.1. When Creating a Storage Account

1. Open the Azure Portal and select **Storage accounts → Create**.
2. Choose the right subscription, resource group, and Storage Account name.
3. Choose a primary region aligned with where the workload runs and residency requirements.
4. Select the account kind, performance tier, and **redundancy** from the options permitted by the Portal.
5. Read the descriptions of LRS, ZRS, GRS, GZRS, and read-access geo-redundancy options if shown.
6. Review tabs for security, networking, data protection, and encryption according to organizational policy.
7. Inspect settings on the review step, check costs/limits, and deploy.
8. Once created, open the Storage Account to inspect **Redundancy** and related status.

Menu names and positions may vary by Portal version. If an SKU does not appear, the cause may be an unsupported account kind, region, or configuration; do not assume Azure removed the feature entirely.

### 15.2. Monitoring Geo-Replication

For accounts using GRS/GZRS or RA variants, check replication status, primary/secondary regions, and **Last Sync Time** if displayed by the Portal. Use them to:

- Detect abnormal replication lag.
- Capture evidence during DR drills.
- Confirm replica locations meet data requirements.
- Support risk decisions ahead of a controlled failover operation.

Do not use a single "available" status screenshot to conclude that RPO and RTO have been tested. Actual recovery tests and data verification are required.

## 16. DR Scenario: Primary Region Outage

Suppose the Orders application uses **GZRS** for Blob Storage in the primary region. A severe regional outage occurs and primary storage operations are disrupted.

### 16.1. Before an Incident

The operations team should prepare by:

1. Confirming the Storage Account supports the planned failover mechanism.
2. Understanding which resources continue working on a **zone** failure vs. which require **region failover**.
3. Designing compute, networking, identity, DNS, and app dependencies in the backup region.
4. Defining business RPO/RTO and acceptable replication lag.
5. Enabling monitoring, logging, and data protection against logical faults.
6. Writing drill runbooks, rollback/recovery steps, and failover approval workflows.
7. Budgeting dual-region operating costs and recovery expenses.

### 16.2. When One Availability Zone Fails

With ZRS or the primary of GZRS, the Storage Account is designed to withstand a single-zone outage within supported limits. However:

- Azure Storage may keep serving requests while the application still suffers downtime due to its own compute/database/network tiers.
- Check application telemetry, timeouts/retries, endpoints, and deployment zones of other components.
- Do not automatically trigger regional failover merely because a VM in one zone failed.

### 16.3. When the Primary Region Becomes Unavailable

With GRS/GZRS:

1. Verify the incident scope and official service notifications.
2. Gather the latest primary write timestamp, Last Sync Time if available, and geo-replication status.
3. Estimate the risk of losing data that had not yet reached secondary.
4. Decide on failover per runbook, permissions, and mechanisms supported by the account type.
5. Coordinate transitioning compute, applications, networking, DNS, identity, and data dependencies.
6. After failover, verify data, read/write permissions, integrity, and business consistency.
7. Check what redundancy type the account reverted to post-failover and plan to re-establish geo-protection.
8. Document actual recovery time, unavailable data, and improvement actions.

**Do not trigger account failover on a production Storage Account as a casual exercise.** It can be a disruptive change resulting in loss of unsynchronized data. Rehearse in an appropriate environment following current Azure guidance.

### 16.4. Why Reconcile Data After Failover?

Suppose a system has:

- A database storing the status "invoice created."
- Blob Storage holding the invoice PDF file.
- A queue processing email-sending tasks.

If the three components replicate and fail over via different mechanisms, a state may arise where "the database has the record, yet the blob never reached the secondary region." The application needs reconciliation, retries, or idempotent file regeneration mechanisms.

Storage Account redundancy alone does not guarantee **transactional consistency** across multiple services.

## 17. Security and Compliance When Choosing Redundancy

When evaluating data replication models, pair storage requirements with security:

### 17.1. Data Residency

Geo-redundancy creates data replicas in another region via Azure mechanisms. Before enabling it, verify organizational policies on whether data may be replicated outside the primary region, legal obligations, and handling of sensitive information.

If data must stay inside one specific region, GRS/GZRS may be unsuitable; in that case you need a DR/backup approach satisfying the organization's residency and data governance requirements.

### 17.2. Encryption and Access Controls

Redundancy does not replace:

- Azure RBAC and data-plane permissions for Blob, File, Queue, or Table as appropriate.
- Authentication mechanisms, managed identities, and secret management.
- Data encryption according to the chosen service/key type.
- HTTPS/TLS and public network access controls.
- Firewalls, private endpoints, DNS, and NSGs per supported architecture.
- Audit logs and access review processes.

If an application needs to access the secondary endpoint of RA-GRS/RA-GZRS, verify network rules, tokens/permissions, and how the app accesses data on the secondary; never assume a firewall rule on primary covers every scenario.

### 17.3. Backups and Protection Against Human Loss

High-value transactional data should evaluate retention, versioning, soft delete, immutable storage, backup/restore, and restore testing. Approval responsibility for deleting or altering data protection policies should be separated from application operations accounts where feasible.

## 18. Cost and Performance Impact

### 18.1. Cost Is Not Only Capacity

Azure Storage may charge across multiple dimensions:

- Stored capacity (GB/month) by redundancy/SKU and access tier.
- Number and type of operations (reads, writes, listings, tier changes).
- Data retrieval and lifecycle actions across corresponding access tiers.
- Geo-replication or redundancy conversion per service terms.
- Network/egress traffic and recovery operations.
- Add-on backups, versioning, logging, and monitoring if enabled.

In general, options with broader protection incur higher storage costs than local counterparts, yet **you should not assume a fixed absolute price ranking** across all regions, tiers, and service types. Use the Azure Pricing Calculator and real account/service rate cards.

### 18.2. Performance and Latency Impact

LRS and ZRS have different synchronous replication scopes; ZRS writes across zones in primary, so latency characteristics should be validated against SLAs and specific workloads. GRS/GZRS replicate asynchronously to secondary and therefore do not wait for full geo-replication to finish before acknowledging each primary write.

However, application performance also depends on:

- Request size, concurrency, and Blob/File/Queue/Table type.
- Account limits, access tier, and data partitioning.
- Compute region relative to Storage Account region.
- Networking, private endpoints, DNS, and client retries.
- High volumes of small writes or metadata updates.

Do not promise IOPS, latency, or throughput based on redundancy name alone. Benchmark against actual data types, regions, and configurations.

## 19. Monitoring, Testing, and Operations

A Storage Account "set to GZRS" does not automatically mean availability is solved. Maintain operational checks.

### 19.1. Signals to Monitor

| Signal | Objective |
|---|---|
| Availability and request success rate | Detect storage access disruptions |
| Latency / end-to-end latency | Detect abnormal latency spikes |
| Server errors, throttling | Identify platform, client, or service-limit faults |
| Storage capacity and transaction count | Track growth and load |
| Replication status / Last Sync Time (if available) | Observe geo-replication lag risks |
| SKU, network, and RBAC changes | Detect out-of-process modifications |
| Soft delete / versioning / backup status | Verify recovery readiness against logical errors |
| Cost Management | Control expenses by SKU and workload |

You can use Azure Monitor, diagnostic settings, Activity Log, and tracking features appropriate for Azure Storage. Choose retention and log destinations per organizational policy; avoid using the same unprotected Storage Account to store the sole copy of critical logs.

### 19.2. Safe Failure Drills

- **Unit/integration tests:** test application handling of 429/5xx errors, timeouts, and retries with appropriate exponential backoff.
- **Zone failure planning:** confirm application components all follow zone-resilient architectures if required.
- **Read-secondary drill:** with RA-GRS/RA-GZRS and supported services, test reading from secondary and detecting stale data.
- **Data recovery drill:** restore a deleted Blob or older version using enabled protection features.
- **DR runbook tabletop:** walk through failover decisions, workload cutover steps, and data reconciliation.
- **Controlled failover exercise:** only in appropriate environments and account kinds, following current guidance and approvals.

Never simulate regional failure by deleting real data or triggering production failover outside change control.

## 20. Common Misconceptions

1. **"LRS only has one copy."** False. LRS maintains **three copies**, though in **a single physical location**.
2. **"ZRS protects automatically when an entire region goes down."** False. ZRS protects across zones **within one region**; ZRS alone has no secondary region.
3. **"GRS synchronously replicates data immediately to the secondary region."** False. Geo-replication is **asynchronous**.
4. **"GZRS has three zones in both primary and secondary."** False in the standard model: ZRS in primary, **LRS** in secondary.
5. **"GRS allows normal writes to the secondary."** False. GRS is not a dual-region multi-master write model.
6. **"RA-GRS means both regions have instantaneously fresh data."** False. RA allows secondary reads where supported, but data may lag.
7. **"Choosing geo-redundancy means zero data loss."** False. Un-replicated writes risk loss during regional failover.
8. **"Having 6 replicas means no backup is needed."** False. Logical deletions/overwrites can replicate to all copies.
9. **"If the Storage Account has GZRS, the app automatically has HA and DR."** False. Compute, databases, networking, DNS, identity, and runbooks must be designed separately.
10. **"Every SKU can be converted with a single command."** False. Redundancy conversion support depends on service, region, and active features.
11. **"GRS RPO is always 0."** False. Never make such a guarantee for asynchronous geo-replication.
12. **"More replicas are always best."** Not necessarily. Balance fault-tolerance needs, residency, regional support, features, and budget.

## 21. Production Redundancy Selection Checklist

- [ ] Identified whether data is critical or recreatable.
- [ ] Identified target failure domains: hardware, site, zone, region, or logical error.
- [ ] Defined RPO/RTO and availability targets; did not infer them from SKU names.
- [ ] Decided whether a replica in a secondary region is required.
- [ ] Decided whether zone fault tolerance in primary is required.
- [ ] Evaluated whether **reading secondary prior to failover** is needed.
- [ ] Checked primary/secondary regions, data residency, and legal requirements.
- [ ] Confirmed supported Storage Account kind, service, access tier, and SKU.
- [ ] Assessed replication lag and data-loss risk during unplanned failover.
- [ ] Planned appropriate backups, retention, versioning, soft delete/immutability.
- [ ] Mapped dependencies across compute, databases, networking, DNS, and identity.
- [ ] Designed DR, failover, and geo-redundancy re-establishment procedures.
- [ ] Tested data recovery and assessed cross-service consistency.
- [ ] Reviewed current pricing, quotas/limits, and operational costs.
- [ ] Assigned owners, monitoring, and a configuration review schedule.

## 22. Practice Exercises

### Exercise 1: Choose Redundancy by Scenario

Pick LRS/ZRS/GRS/GZRS for these four situations and explain why:

1. Build artifact folder of a test system that can be regenerated.
2. Multi-zone production web app storing user images; the organization does not require regional DR.
3. Record-keeping system needing a geographic copy; primary zone resilience is not mandatory.
4. Production invoicing system that must continue when a zone fails and requires a regional DR plan.

For situation 4, explain why versioning/backups and failover testing are still necessary.

### Exercise 2: Compare GRS and GZRS

Draw two write-flow diagrams from the application to primary and secondary, clearly labeling:

- Whether primary is LRS or ZRS.
- That secondary uses LRS.
- Which path is synchronous and which is asynchronous.
- What happens to writes that have not reached secondary during a sudden failover.

### Exercise 3: Can RA-GRS Serve a Dashboard?

An analytics dashboard reads data every 15 minutes. Operations considers RA-GRS to read from secondary. Analyze:

- How stale the secondary data might be.
- When displaying slightly stale figures is acceptable.
- How the application detects and notifies users of non-fresh data.
- When application-level availability design is required rather than relying solely on the RA endpoint.

### Exercise 4: CLI Hands-On in a Lab

Create a Standard_LRS Storage Account in a practice resource group, then:

1. Read back the SKU using **az storage account show**.
2. Record the primary region and secondary field.
3. Describe the prerequisites to check before switching to ZRS/GZRS.
4. Add Blob accidental-deletion protection per service capabilities.
5. Plan lab cleanup without affecting other resources.

### Exercise 5: Full-Application DR Design

The Orders system stores order state in a database and PDF invoices in GZRS Blob Storage. If the primary region is completely lost, list:

- Steps to recover the Storage Account.
- Application components that must be recovered separately.
- How to measure the risk of un-replicated data loss.
- How to reconcile transactions that have a database record but lack a PDF.
- Criteria for declaring the workload recovered within RPO/RTO.

### Self-Check Questions

1. Why do 3 LRS replicas differ from 3 ZRS replicas?
2. Does ZRS create a secondary region?
3. How many replicas exist in the GRS model once both regions are fully synchronized?
4. What is the key difference between GRS and GZRS in the primary region?
5. Why does geo-replication introduce a risk of losing recent writes during failover?
6. How does RA-GZRS differ from GZRS?
7. When is Last Sync Time useful, and why must it not be treated as an RPO SLA?
8. Why does redundancy not protect against accidental deletion or ransomware?
9. Why check account kind/region before picking an SKU?
10. Is whole-system RTO guaranteed solely by having a GZRS Storage Account?

## 23. References

- [Azure Storage redundancy — Microsoft Learn](https://learn.microsoft.com/azure/storage/common/storage-redundancy)
- [Azure Storage account overview](https://learn.microsoft.com/azure/storage/common/storage-account-overview)
- [Azure Storage disaster recovery guidance](https://learn.microsoft.com/azure/storage/common/storage-disaster-recovery-guidance)
- [Initiate a storage account failover](https://learn.microsoft.com/azure/storage/common/storage-initiate-account-failover)
- [Change how a storage account is replicated](https://learn.microsoft.com/azure/storage/common/redundancy-migration)
- [Blob data protection overview](https://learn.microsoft.com/azure/storage/blobs/data-protection-overview)
- [Azure Storage pricing](https://azure.microsoft.com/pricing/details/storage/)
- [Azure Well-Architected Framework — Reliability](https://learn.microsoft.com/azure/well-architected/reliability/)
