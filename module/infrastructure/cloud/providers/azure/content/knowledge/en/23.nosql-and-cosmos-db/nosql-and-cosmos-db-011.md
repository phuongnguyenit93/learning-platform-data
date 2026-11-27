# Backup, Restore, and Access Protection for Cosmos DB

> **Chapter:** NoSQL Data with Cosmos DB  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Exploring the Microsoft Azure ecosystem from subscriptions, resource groups, and Entra ID to virtual networks, compute services, storage, and data. Learn how to deploy, monitor, secure, and control the cost of an Azure application architecture.

## Lesson Objectives

After completing this lesson, you will be able to:

1. Explain why **Azure Cosmos DB** still needs a **backup, restore, data protection, and access control** strategy despite being a multi-region managed database service.
2. Distinguish **periodic backup** from **continuous backup / point-in-time restore (PITR)**, including eligibility, retention windows, scope, and restore mechanics.
3. Separate **replication/failover**, backups, exports, and the **change feed**; define **RPO/RTO** targets and plan recovery drills.
4. Design a data recovery runbook for accidental deletions or bad updates, verify restore points, and cut applications over to restored resources.
5. Distinguish **Azure control-plane RBAC** from **Cosmos DB for NoSQL data-plane RBAC**, account keys, resource tokens, and Microsoft Entra authentication.
6. Protect Cosmos DB accounts using **firewalls, network ACLs, Private Endpoints, Private DNS, managed identities, TLS, encryption, and Key Vault**.
7. Use the **Azure CLI** to inspect configuration and manage scoped data-plane role assignments; use the **Python Azure Cosmos SDK** with `DefaultAzureCredential`.
8. Monitor operations with **Azure Monitor**, diagnostic logs, RU metrics, 429s, availability, backup/restore events, and audit logs; detect unauthorized access or inconsistent restored data.
9. Build test cases, runbooks, rollback plans, and cost estimates for safely operating a Cosmos DB architecture.

## 1. Context: Even a Managed Database Can Lose Business Data

A company runs an ordering system on Cosmos DB for NoSQL:

- The API creates and updates `orders` documents keyed by `tenantId` and `orderId`.
- Multiple application replicas run on Azure Container Apps or AKS.
- The Cosmos DB account may be multi-region for high availability.
- A buggy migration script runs `DELETE` or corrupts thousands of documents.
- A leaked credential or account key lets an unauthorized party read or wipe data.

**Managed infrastructure never prevents accidental deletes, valid yet buggy mutations, or overly broad permissions.** Deletions replicate cleanly to active replicas, because replication mirrors mutations—not an immutable historical archive.

~~~mermaid
flowchart LR
    U["Client"]
    APP["Order API\nManaged identity"]
    NET["Private Endpoint\nNetwork access policy"]
    DB["Cosmos DB account\nNoSQL database / containers"]
    BACK["Backup policy\nPeriodic or Continuous"]
    REST["Restored account\nverify and cut over"]
    MON["Azure Monitor\nLogs / Alerts"]
    U --> APP --> NET --> DB
    DB -.-> BACK
    BACK -->|"Supported restore"| REST
    DB -.-> MON
    APP -.-> MON
~~~

This diagram illustrates logical flows only. **Backup/restore does not automatically create a restored account or cut over traffic in every policy.** Exact procedures depend on API, backup mode, region, tier, and permissions. Production systems must verify recovery workflows before data is lost.

### Questions to Answer Before Deployment

| Question | Why It Matters |
|---|---|
| How quickly is bad data detected? | Drives retention and PITR windows |
| How much data loss is tolerable? | Defines RPO |
| How much downtime is tolerable? | Defines RTO |
| Must we restore the entire account or just a database/container? | Determines backup mode and runbook |
| Does the app hold permissions to delete an entire container? | Governs data-plane RBAC and account keys |
| If an account is compromised, can the attacker delete backups? | Evaluates separation of duties and admin roles |
| Does restoring create a new account and endpoint? | Shapes networking, identity, and cutover plans |
| Are there regional data-residency limits? | Governs backup/restore regions and compliance |

## 2. Scoping Azure Cosmos DB

### 2.1. Account, Database, Container, and Item

In **Azure Cosmos DB for NoSQL**, the hierarchy is:

~~~text
Azure subscription
  Resource group
    Cosmos DB account: cos-orders-prod
      API: NoSQL
      Database: commerce
        Container: orders
          Partition key path: /tenantId
          Items: JSON documents
        Container: auditEvents
          Partition key path: /eventId
          Items: JSON documents
~~~

- **Account** is the top-level boundary for endpoints, networking, consistency, regions, backup mode, and operational policies.
- **Database** groups containers and may hold shared throughput settings.
- **Container** holds items, the partition key, and indexing/TTL policies.
- **Item** is a JSON document carrying `id` and its partition key value.
- **Partition key** governs logical distribution and how items are located and restored per container; identical `id` values can exist across multiple logical partitions.

### 2.2. API Support Is Mandatory to Verify

Cosmos DB offers several APIs/models—**Cosmos DB for NoSQL**, **API for MongoDB**, **Cassandra**, **Gremlin**, **Table**, and separate MongoDB vCore products.

**This lesson uses Cosmos DB for NoSQL as its primary path.** Before applying these CLI, SDK, or data-plane RBAC examples to another API, check the **exact API, account type, and backup mode documentation**. Never assume:

- `az cosmosdb sql role assignment` applies verbatim to MongoDB or Cassandra.
- Every API supports identical continuous backup and restore granularity.
- Full-account restore and single-container selective restore follow identical steps.
- Different Cosmos DB offerings share the same account keys or permission models.

### 2.3. Cosmos DB for NoSQL Is Not PostgreSQL Backup

Cosmos DB PITR **is not** a SQL `RESTORE DATABASE` command, `.bak` file, or PostgreSQL WAL directory. Each account relies on Azure-managed backup/restore mechanisms. Manual JSON exports **do not automatically preserve** partition key designs, indexing policies, throughput, internal metadata, users, or network rules without dedicated tooling.

### 2.4. Availability and Durability Differ from Data History

Cosmos DB provides distributed durability and optional multi-region availability, yet when an app accidentally deletes an item, that delete is a **valid committed write**. Replicas faithfully propagate the deletion. Backups provide a **point-in-time recovery path** independent of replica count.

## 3. RPO, RTO, Retention, and Recovery Scenarios

### 3.1. RPO and RTO

- **RPO (Recovery Point Objective):** Maximum tolerable rewind window of lost mutations. A 10-minute business RPO target does not guarantee every backup mode provides a restore point within 10 minutes.
- **RTO (Recovery Time Objective):** Maximum tolerable downtime to restore service—including restore duration, data validation, and application cutover.
- **Retention window:** How long backup data remains available for restore per policy and service limits.

**Backup mode alone never guarantees RTO.** Restoring to a new account, validating records, and reconfiguring applications takes far longer than an automated HA failover.

### 3.2. Classifying Recovery Scenarios

| Scenario | Primary Response |
|---|---|
| Regional outage while logical data is intact | Multi-region failover / availability policy |
| Buggy script deletes a subset of items | Continuous PITR or selective restore per supported mode/API |
| Entire database or container dropped | Restore at the scope supported by backup mode |
| Over-privileged role or leaked key | Isolate access, revoke/rotate, audit, evaluate restore |
| Bug writes wrong prices for 30 minutes | Identify pre-bug restore point and plan merge/replay of valid writes |
| Data loss discovered past retention | Backups expired; rely on external exports/archives |
| Periodic analytics data copies needed | Change feed, ETL/export, or Data Factory—never abuse PITR |
| Recovery after full account deletion | Check recoverable resources/restore rules per backup mode and lifecycle; never assume guaranteed |

### 3.3. The Restore Point Differs from Detection Time

Example:

~~~text
09:00 UTC: data is healthy
09:12 UTC: buggy job deletes many items
09:18 UTC: anomaly detected
09:22 UTC: SRE halts job and blocks write identity
09:24 UTC: selects restore point prior to 09:12
~~~

Accurate recovery requires pinpointing **the first corrupting mutation**, not merely when operators noticed. Use Azure Activity Logs, application audit events, change logs, and business evidence to narrow the timestamp.

### 3.4. Full Restores Omit Valid Writes After the Restore Point

Restoring everything back to 09:11 UTC means valid orders created between 09:11 and cutover **will not exist** in the restored dataset. Plan reconciliation, selective replay, or compensating workflows from trusted event logs. Never cut traffic to a restored account and delete the old account before accounting for post-restore-point valid writes.

## 4. Periodic Backup: Scheduled Snapshot Model

### 4.1. What Is Periodic Backup?

Under a **periodic backup policy**, the service takes snapshots on a configured interval. Restore-point freshness depends on **backup interval** and retention. Defaults and customizable intervals, retention limits, and storage redundancy vary by account, API, tier, and over time.

~~~mermaid
flowchart LR
    S["Live data"]
    B1["Backup snapshot\n01:00"]
    B2["Backup snapshot\n05:00"]
    B3["Backup snapshot\n09:00"]
    I["Incident\n10:30"]
    R["Restore via\nselected backup workflow"]
    S -.-> B1
    S -.-> B2
    S -.-> B3
    I --> R
    B3 --> R
~~~

Timestamps above are **illustrative only**, not default Azure schedules. If the latest snapshot before an incident was 09:00, valid writes afterward must be reconciled or replayed during recovery.

### 4.2. Strengths and Limitations

**Strengths:**

- Fits workloads where scheduled-snapshot RPO is acceptable.
- Simpler policy when minute-by-minute rewind is unnecessary.
- Configurable storage redundancy and retention where supported.

**Limitations:**

- Cannot pick an arbitrary timestamp between scheduled snapshots like continuous PITR.
- Restores may involve **service/support-assisted workflows** rather than identical self-service continuous PITR UX.
- Restore granularity (account/database/container) and recovery speed depend on API and mode.
- Does not replace independent audit exports.

### 4.3. Questions to Verify Before Choosing Periodic

1. Does the backup interval meet your RPO?
2. Does retention cover bugs discovered days later?
3. Which backups can be selected and what is the restore request process?
4. Which regions and storage redundancy options are supported?
5. Does restore require support tickets or self-service tooling?
6. How long does spinning up and validating a restored account take?
7. Can writes occurring after the latest backup be replayed from another source?

Never assume a generic `backup` setting lets you “rewind to 10:23:45 UTC” when the account runs periodic mode.

## 5. Continuous Backup and Point-in-Time Restore (PITR)

### 5.1. Concept

**Continuous backup** supports restoring **to any supported timestamp within the retention window** on eligible Cosmos DB APIs and account types. Retention windows vary by tier; verify active configuration and service limits.

~~~mermaid
flowchart LR
    A["09:00\nHealthy data"]
    D["09:12\nAccidental delete"]
    NOW["09:18\nDetected"]
    P["09:11\nRestore point"]
    REST["Restored account\nvalidate"]
    A --> D --> NOW
    D -.->|"Pick pre-incident timestamp"| P
    P --> REST
~~~

Crucial detail: PITR lets you pick a **service-supported timestamp**, yet not every resource or arbitrary second is guaranteed restorable under all conditions. Verify earliest/latest restorable timestamps, account settings, and feature constraints.

### 5.2. Continuous vs. Periodic

| Criterion | Periodic | Continuous / PITR |
|---|---|---|
| Restore points | Scheduled backup snapshots | Timestamps within the restorable window |
| Primary goal | Periodic protection | Minimize loss from accidental edits/deletes needing rewind |
| Achievable RPO | Bound by backup interval | Often tighter where supported by feature/timestamps |
| Self-service restore | Varies by API, mode, and support process | Managed self-service restore experience where supported |
| Creates new resource on restore | Verify exact recovery behavior | Typically restores into a **new target account** |
| Selective restore | Check limits | May support account, database, or container scope per API |
| Config / billing | Per periodic policy | Per continuous tier, retention, and cost |
| Account / API / region support | Verify compatibility | Verify compatibility |

**Never assume continuous is always cheaper or faster than periodic**; restore cost and duration depend on data volume, throughput, regions, retention, and features.

### 5.3. Choosing a Retention Tier

When Azure offers distinct continuous retention tiers (such as shorter vs. longer windows), base the choice on:

- Mean time to detect bad writes or deletes.
- RPO/RTO for orders and financial workflows.
- Regional legal and compliance retention mandates.
- Data volume, region count, and backup cost.
- Granular container/database restore needs.
- Rules for switching or upgrading/downgrading retention modes.

**Never hardcode one retention limit across every API and SKU**; verify supported options and limits at account creation or modification time.

### 5.4. Restore Rarely Mutates the Primary In Place

In supported continuous PITR workflows, restoring typically creates **a brand-new Cosmos DB account**. That means:

- New endpoint and new account name.
- Network ACLs, Private Endpoints, and Private DNS must be reconfigured.
- Application identities need proper data-plane RBAC assignments.
- Throughput, indexing, partition keys, TTL, stored procedures, triggers, and roles must be verified.
- Target regions, consistency, and backup settings depend on restore options.
- Client traffic does not cut over automatically.
- Valid writes after the restore point require reconciliation or replay.

That is why you always need a **cutover runbook**, even with continuous backup enabled.

## 6. What Backups Alone Cannot Solve

### 6.1. Replication and Failover Do Not Undo Accidental Deletes

A multi-region account protects availability during regional outages. Yet when a valid `DELETE` replicates, failing over to another region does not resurrect pre-delete data. **Replication is an availability strategy, not a backup history.**

### 6.2. The Change Feed Is a Stream, Not a Complete Recovery Snapshot

The change feed powers event-driven workflows, analytics, and certain audit streams. However:

- Coverage of creates, updates, deletes, and retention depends on the supported **change feed mode**.
- Standard change feeds do not provide a complete PITR-ready snapshot.
- Consumers maintain their own checkpoints, lag, TTL, and error handling.
- Using the change feed for replay requires its own **data contract and durable storage**.

Never treat “change feed is enabled” as an undo button for accidental deletions.

### 6.3. JSON Exports Do Not Automatically Equal Service Backups

Exporting documents to Blob Storage or Data Lake helps with archival and auditing. Still, verify:

- Is the export transactionally consistent at one point in time?
- Does it capture partition keys, IDs, timestamps, and required metadata?
- Does re-importing preserve indexing policies, TTL, throughput, and unique keys?
- Does it satisfy encryption, IAM, and data residency rules?
- Can mutations occurring during export be replayed?
- Have you tested importing back into a new account with identical partitioning?

Backups, replication, archives, and exports are **distinct layers** often combined to meet RPO and RTO.

## 7. Inspecting Current Backup Policies and Restore Eligibility

### 7.1. Prerequisites Before Reading Resources

- Signed into Azure with an authorized account.
- Exact subscription ID, resource group, and Cosmos DB account name.
- Confirm whether the account uses NoSQL or another API.
- **Metadata read** permission on the account (business data read permissions are not needed just to view backup policy).
- Cost and impact approval before altering backup modes or restoring accounts.

**Bash** environment example:

~~~bash
az login
az account show \
  --query "{subscription:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

az account set --subscription "<SUBSCRIPTION_ID>"

RG="rg-cosmos-lab"
ACCOUNT="cos-orders-prod"
~~~

Replace `ACCOUNT` with your target account; `show` commands below are read-only, whereas policy edits or restores later can incur charges and impact data safety.

### 7.2. Inspecting Account Info and Backup Policy

~~~bash
# Never print keys or connection strings.
az cosmosdb show \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --query "{name:name, kind:kind, backupPolicy:backupPolicy, locations:locations, publicNetworkAccess:publicNetworkAccess}" \
  --output json
~~~

What to read:

- `backupPolicy.type` indicates `Periodic` or `Continuous` in the ARM response schema.
- Retention, tier, interval, and redundancy fields vary by policy type and API version.
- `locations` lists configured regions.
- `publicNetworkAccess` is **one** network signal—not proof that Private Endpoints, DNS, and routing are configured properly.

If a field returns `null` or is absent, **do not guess**. Inspect the full authorized JSON metadata, check CLI/API versions and documentation, and **never run `az cosmosdb keys list`** just to inspect backup policies.

### 7.3. Checking Supported Restore Commands

Azure CLI exposes command groups for **restorable resources** and Cosmos DB restores per CLI version. Check live CLI help before assuming flags:

~~~bash
az cosmosdb --help
az cosmosdb restore --help
az cosmosdb restorable-database-account --help
~~~

Some SDKs/APIs list **restorable database accounts, databases, and containers** with restorable timestamps, subject to policy and API limits. Never assume `restore --help` existing means a periodic-mode account offers identical self-service PITR.

### 7.4. Never Alter Backup Modes Without a Change Plan

Switching between periodic and continuous backup carries **one-way conversion rules, API eligibility checks, and live-account constraints**. Before changing or provisioning:

1. Verify the current mode.
2. Verify features, retention, and pricing for your API and region.
3. Document risk assessment and expected duration.
4. Test a restore in staging.
5. Clarify whether account recreation/migration is required.
6. Obtain data owner, SRE, and security approvals.

**Never run `az cosmosdb update` guessing backup policy flags**, as policy changes may be irreversible.

## 8. Recovery Runbook for Data Corruption Under Continuous Backup

### 8.1. Sample Scenario

Account `cos-orders-prod` has database `commerce` and container `orders` partitioned by `/tenantId`.

- 13:10 UTC: data is healthy.
- 13:18 UTC: a buggy batch job sets `status="CANCELLED"` on thousands of valid orders.
- 13:25 UTC: cancellation-rate alert fires.
- 13:28 UTC: SRE halts the batch job and disables the offending identity.
- 13:35 UTC: identifies valid restore point prior to 13:18.

**Critical business decision:** You may need to restore only the corrupted orders rather than swapping the entire account, since valid new orders arrived between 13:18 and 13:35.

### 8.2. Incident Coordination Steps

**Step 1 — Preserve evidence.** Record UTC timestamps, account/database/container names, deployment/job versions, `eventId`/correlation IDs, and affected item counts. Never dump raw customer PII into public reports.

**Step 2 — Stop further bad writes.** Pause the offending job or restrict its identity per runbook. Never delete the account, drop backups, or recklessly alter firewalls/keys before checking legitimate workloads.

**Step 3 — Pinpoint the restore point.** Use app audit logs, deployment history, and operation timelines to choose a timestamp **before the first bad mutation**. Compare against earliest/latest restorable timestamps and retention.

**Step 4 — Choose restore scope.** Evaluate account, database, or container restore per API/mode support. If direct selective restore is unavailable, restore broadly into a **new account** and extract only the affected records.

**Step 5 — Restore to a target environment.** Execute the restore via supported Portal/CLI/APIs, picking a unique target account name and valid regions/backup mode. This is a **billable write operation** requiring change approval.

**Step 6 — Verify metadata.** Inspect databases, containers, partition keys, indexing policies, unique keys, TTL, throughput modes, regions, stored procedures/triggers, and security/networking settings.

**Step 7 — Verify data.** Reconcile order IDs, item counts per tenant/partition, sample checksums, timestamps, and critical transactions. Never rely solely on “the Portal says restore succeeded.”

**Step 8 — Reconcile valid writes after the restore point.** Inspect audit/change logs and authoritative sources, then replay/merge **idempotently** so nothing is lost or duplicated. Account for events already sent to Service Bus, Event Hubs, or payment gateways.

**Step 9 — Controlled cutover.** Update endpoints, identity role assignments, Private Endpoints, DNS, secret references, and app configuration per plan. Avoid uncoordinated dual writes.

**Step 10 — Monitor and close incident.** Watch 429s, 401/403s, 5xx, p95 latency, failed requests, data invariants, and budgets. Clean up temporary recovery resources only after sign-off.

### 8.3. Pre-Cutover Checks for a Restored Account

| Item | Acceptance Question |
|---|---|
| API / account type | Are NoSQL API and backup mode configured properly? |
| Region / consistency | Do regions, consistency, and preferred locations match design? |
| Database / container | Do names and counts match? |
| Partition key path | Is `/tenantId` and logical partitioning intact? |
| Indexing / TTL | Do policies match expectations without unintended expiration? |
| Throughput | Is autoscale/provisioned RU/s sized for live traffic? |
| Authentication | Do app identities hold scoped data-plane role assignments? |
| Networking | Are Private Endpoints, DNS, firewalls, and public access configured? |
| CMK / encryption | Are Key Vault keys and identities accessible if CMK is used? |
| Application | Do SDK endpoints, credentials, preferred regions, and retries work? |
| Data validation | Are sampling and per-tenant/order reconciliation complete? |
| Monitoring | Are diagnostic settings, alerts, and budgets assigned to owners? |
| Rollback | Is there a safe fallback if cutover breaches SLOs? |

Never assume a restored account automatically **inherits** all role assignments, network policies, Key Vault permissions, alerts, or CI/CD mappings from the original account. Verify every item explicitly.

### 8.4. Can You Restore While Keeping Production Traffic Live?

You can restore into a **parallel** account for validation without shifting traffic. However, the restored account does not automatically receive ongoing writes hitting the original account. Cutting over requires a strategy:

- Brief write freeze / maintenance window.
- Replaying from a trusted event log.
- Verified application-level sync/merge.
- Defining an authoritative source of truth if writes split.
- Checking TTL, unique keys, partition keys, and merge conflicts.

Never let two endpoints accept conflicting writes without conflict resolution; it makes recovery vastly harder.

### 8.5. Special Check for Deleted Containers

If a container was dropped, restore eligibility depends on the deletion timestamp and resource-level restore support. Check restorable metadata and account limits—never assume a deleted container can simply be “undeleted” in place on the original account just because PITR is on.

### 8.6. When Account Keys or Credentials Leak

Data restoration **is not** the first response to a credential leak. Immediately revoke credentials, rotate keys or remove compromised role assignments, inspect data access logs, and preserve forensic evidence. Restore data only if logs show unauthorized edits or deletions.

## 9. Backup and Restore Do Not Replace Access Governance

### 9.1. Two Distinct Permission Planes

The **Control plane** manages Azure resources: accounts, regions, backups, networking, throughput, identity, and settings. The **Data plane** reads and writes items inside databases and containers.

~~~mermaid
flowchart TB
    ADMIN["Azure operator / IaC"]
    APP["Order API\nManaged identity"]
    ARM["Azure Resource Manager\nControl plane"]
    ACC["Cosmos DB account config"]
    AUTH["Cosmos DB NoSQL\nData-plane authorization"]
    DOC["Database/Container/Items"]
    ADMIN -->|"Azure RBAC permission"| ARM --> ACC
    APP -->|"Entra token / SDK"| AUTH --> DOC
~~~

**Azure RBAC `Contributor` on an account does not automatically permit reading items when using Cosmos DB native data-plane RBAC.** Conversely, an identity holding `readMetadata`/`readItems` cannot edit Azure Resource Manager backup policies.

### 9.2. Credentials to Distinguish

| Mechanism | Where Used | Risks and Notes |
|---|---|---|
| **Account primary/secondary keys** | Key-based auth per API | Extremely broad access; restrict distribution and rotate |
| **Read-only keys** | Specific read-only scenarios | Still shared secrets with broad scope; not tenant isolation |
| **Microsoft Entra ID** | Identity-based auth and NoSQL data-plane RBAC | Requires Cosmos DB role assignments and token refresh |
| **Managed identity** | Identity for Azure-hosted workloads | Holds zero data-plane rights until explicitly assigned |
| **Resource tokens** | Time- and scope-bounded tokens where supported | Requires trusted backend issuer, short TTL, strict scope |
| **Connection strings** | Typically embed endpoint + key | Never log, commit, or ship to browsers/mobile apps |
| **Key Vault references** | Injecting secrets/config from Vault | Audit vault permissions, caching, and rotation |

**Never embed a primary key in browser JavaScript.** Browser/mobile clients must talk to an authorized backend or use strictly scoped short-lived tokens where supported—never give untrusted clients account-wide authority.

### 9.3. Who Needs Which Permissions?

Example workload roles:

- `orders-api`: Read/write items in `commerce/orders`.
- `fraud-worker`: Read specific fields/items per design; cannot delete containers.
- `audit-reader`: Read-only access to the audit container.
- `platform-admin`: Manage account, backup, and network resources via Azure RBAC.
- `security-operator`: Audit configurations, inspect logs, and manage incidents with scoped roles.
- `break-glass`: Emergency access gated by MFA, logging, time bounds, and approval.

Broader permissions mean a larger blast radius. Never hand out `Owner` or an account primary key just so an API can read an order.

## 10. Microsoft Entra ID and Cosmos DB for NoSQL Data-Plane RBAC

### 10.1. Why Choose Entra ID?

Microsoft Entra ID lets Azure workloads use **managed identities** instead of long-lived shared secrets. Cosmos DB for NoSQL supports **native data-plane RBAC** for fine-grained data access.

Benefits:

- Zero account keys embedded in code.
- Permissions bound directly to service identities.
- Granular revocation and updates by principal and scope.
- Auditable role assignment changes.
- Clean separation between read-only APIs and read-write workers.

### 10.2. Role Definitions and Role Assignments

Cosmos DB for NoSQL provides **built-in data-plane roles** plus custom roles where supported. Two common built-in roles:

- **Cosmos DB Built-in Data Reader:** Permits read operations defined by the role.
- **Cosmos DB Built-in Data Contributor:** Permits read and write operations defined by the role.

**These role names belong to Cosmos DB for NoSQL data-plane RBAC—they are NOT Azure IAM “Reader” or “Contributor” roles.** Always inspect exact `dataActions` and effective scopes rather than guessing from names.

Every role assignment specifies:

1. **Principal object ID** of the user, group, service principal, or managed identity.
2. **Role definition ID** inside the Cosmos DB account.
3. **Scope** along account, database, or container paths.

Example scopes:

~~~text
/                           (account-wide root scope)
/dbs/commerce               (database scope)
/dbs/commerce/colls/orders  (orders container scope)
~~~

### 10.3. Listing Roles and Assignments via Azure CLI

**Read-only** commands:

~~~bash
RG="rg-cosmos-lab"
ACCOUNT="cos-orders-prod"

az cosmosdb sql role definition list \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --output json

az cosmosdb sql role assignment list \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --output json
~~~

Before assigning roles, verify **the account API is NoSQL**, and confirm the exact **identity object ID**, **role definition ID**, and **scope**. Never pass an app registration/client ID when the command requires the **object ID (principal ID)**.

### 10.4. Assigning Data Permissions to a Managed Identity (Authorized Environments Only)

The command below **modifies access permissions**:

~~~bash
RG="rg-cosmos-lab"
ACCOUNT="cos-orders-prod"

PRINCIPAL_OBJECT_ID="<MANAGED_IDENTITY_PRINCIPAL_OBJECT_ID>"
ROLE_DEFINITION_ID="<COSMOS_SQL_DATA_ROLE_DEFINITION_ID>"
ROLE_SCOPE="/dbs/commerce/colls/orders"

az cosmosdb sql role assignment create \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --principal-id "$PRINCIPAL_OBJECT_ID" \
  --role-definition-id "$ROLE_DEFINITION_ID" \
  --scope "$ROLE_SCOPE"
~~~

**Never execute until principal, scope, and role are reviewed.** Afterward, list assignments again and run both **positive tests** (reading/writing the intended container) and **negative tests** (confirming out-of-scope containers reject access) on lab data.

Role **propagation takes time**; troubleshoot 403s by checking role, scope, networking, and waiting briefly for propagation—never panic-paste a full-access account key to “fix” it.

### 10.5. Custom Roles When Built-In Roles Are Too Broad

If an app only needs item reads and a built-in role includes unwanted `dataActions`, create a custom role with the minimal supported actions.

Design roles around the **exact `dataActions` the SDK needs**—such as reading container metadata alongside reading/querying items—rather than granting `readItem` while omitting metadata reads required by queries. For multi-tenant apps, container-scoped RBAC **does not filter rows by `tenantId`**: the backend must still authenticate tenants, validate partition keys, and enforce business authorization.

### 10.6. Negative Authorization Testing

Examples:

| Test Case | Expected Result |
|---|---|
| `orders-api` reads an item from `orders` | Succeeds |
| `orders-api` writes to `orders` with Data Contributor | Succeeds |
| `orders-api` reads `auditEvents` without permission | Denied |
| `orders-api` attempts to list account keys | Denied by management RBAC |
| Principal with no data role queries Cosmos DB | Data access denied |
| Principal with valid data role over blocked network | Connection fails |
| Principal with IAM `Contributor` but no data role | Cannot read items via Entra data-plane RBAC |

Run these tests strictly with **lab-only identities and synthetic data**; never run destructive tests against production.

## 11. Using the Azure Cosmos SDK with Managed Identity

### 11.1. Authentication Flow

~~~mermaid
sequenceDiagram
    participant A as API / Azure workload
    participant I as Managed Identity / Entra ID
    participant C as Cosmos DB for NoSQL
    A->>I: Request access token
    I-->>A: Access token
    A->>C: HTTPS request + Entra token
    C->>C: Data-plane RBAC + network policy
    C-->>A: Item / 401, 403 error
~~~

Applications store zero master keys when identity-based auth is configured properly. **Acquiring an Entra token does not guarantee the Cosmos DB role assignment is right**; both steps must succeed.

### 11.2. Python SDK Secure Document Read

Example using `azure-cosmos` and `azure-identity` with `DefaultAzureCredential`:

~~~python
import os

from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential

endpoint = os.environ["COSMOS_ENDPOINT"]

client = CosmosClient(
    url=endpoint,
    credential=DefaultAzureCredential(),
)

database = client.get_database_client("commerce")
container = database.get_container_client("orders")

# Container /tenantId. Read item using both id and partition key value.
item = container.read_item(
    item="ORD-1001",
    partition_key="tenant-01",
)

print({
    "id": item.get("id"),
    "tenantId": item.get("tenantId"),
    "status": item.get("status"),
})
~~~

**Prerequisites:** Cosmos DB for NoSQL account, SDK version supporting `TokenCredential`, principal holding the proper data-plane role on the container, working network/TLS, and existing sample item. Locally, `DefaultAzureCredential` uses developer credentials rather than the deployed managed identity—always verify the exact active tenant and principal.

### 11.3. Why Must You Supply the Exact Partition Key?

For container `/tenantId`:

~~~json
{
  "id": "ORD-1001",
  "tenantId": "tenant-01",
  "orderId": "ORD-1001",
  "status": "NEW"
}
~~~

Point reads require **`id + partition key`** to route directly to the item. An app identity authorized on the container **does not automatically enforce per-tenant row-level authorization**. The backend must derive the tenant from verified user claims and enforce `partition_key` server-side—never trust a raw client-supplied `tenantId` unchecked.

### 11.4. Token Expiration Handling

SDKs and identity providers handle token refresh per version and runtime. Applications must still:

- Keep SDK versions current and supported.
- Never cache raw access tokens indefinitely by hand.
- Monitor 401/403s and apply appropriate conditional retries.
- Never log tokens.
- Alert if Entra token acquisition fails.
- Re-verify role assignments for the **live workload identity** after slot swaps, revisions, or service principal changes.

### 11.5. Java SDK Connection

Java services can use the Azure Cosmos Java SDK and Azure Identity:

~~~java
// Illustrative builder API: requires azure-cosmos + azure-identity
// versions supporting credential / TokenCredential.
TokenCredential credential = new DefaultAzureCredentialBuilder().build();

CosmosClient client = new CosmosClientBuilder()
    .endpoint(System.getenv("COSMOS_ENDPOINT"))
    .credential(credential)
    .buildClient();

CosmosContainer container = client
    .getDatabase("commerce")
    .getContainer("orders");

CosmosItemResponse<OrderDocument> response =
    container.readItem("ORD-1001",
        new PartitionKey("tenant-01"),
        OrderDocument.class);

// Close client only at application shutdown; never instantiate per request.
client.close();
~~~

This is an **illustrative snippet**, not a complete Java program—supply imports, dependency versions, the `OrderDocument` model, and region/network settings. Builder APIs can vary across major SDK releases; verify against your active SDK. In server apps, maintain a **singleton `CosmosClient` lifecycle** to reuse connection pools instead of constructing one per HTTP request.

## 12. Network Security: Firewalls, VNets, and Private Endpoints

### 12.1. Defense-in-Depth Architecture

A Cosmos DB account can expose a public data endpoint. TLS and authentication protect requests in flight and verify callers, yet **do not restrict which network sources can attempt connections**. Production environments typically layer:

1. Public network access policy or IP firewall/ACL allowlists.
2. VNet service endpoints or **Private Endpoints** per API and service support.
3. Private DNS zones, VNet links, and workload routing.
4. Managed identity + data-plane RBAC.
5. TLS certificate validation and observability.
6. Application-level per-tenant authorization.

### 12.2. Network Patterns

| Option | Meaning | Caveats |
|---|---|---|
| Public endpoint + IP firewall | Allows only approved public egress IPs | NAT/VPN egress IPs may differ from client local IP |
| VNet service endpoint + ACL | Allows access from configured subnets where supported | Does not assign a private IP like Private Link |
| **Private Endpoint** | Private IP/NIC inside your VNet targeting Cosmos DB | Requires Private DNS, connection approval, routing |
| Disable public network access | Blocks public data-plane paths per policy | Verify private connectivity thoroughly first |
| Private DNS | Resolves FQDN to the private endpoint IP | Not authentication or data-plane authorization |

Never assume **creating a Private Endpoint automatically disables public access** if public access remains enabled on the account. Verify both public access settings and private routing.

### 12.3. Private Endpoint Flow with Cosmos DB for NoSQL

~~~mermaid
flowchart LR
    API["AKS / App Service\nVNet-integrated workload"]
    DNS["Private DNS Zone\nCosmos DB NoSQL"]
    PE["Private Endpoint\nprivate IP"]
    COS["Cosmos DB account\nNoSQL"]
    AUTH["Entra ID + NoSQL data RBAC"]
    API --> DNS --> PE --> COS
    AUTH -.->|"Authorization"| COS
~~~

Deployment steps:

1. Confirm the account **API and Private Link subresource** match.
2. Provision the Private Endpoint in an authorized VNet/subnet.
3. Ensure Private Endpoint connection approval completes per policy.
4. Configure the Private DNS Zone and VNet links/forwarders.
5. From the **exact VM, Pod, Container App, or App Service** running the SDK, confirm the account FQDN resolves to the private IP.
6. Verify TLS, identity, and data-plane role assignments.
7. Only after validating the private path, disable public network access if required by policy.
8. Run negative connectivity tests from unauthorized public networks.

For Cosmos DB for NoSQL, Private DNS typically uses zones like `privatelink.documents.azure.com`. **Never swap the SDK hostname to a raw private IP**, never reuse MongoDB/Cassandra Private DNS zones for a NoSQL account, and never disable TLS certificate validation.

### 12.4. Gateway vs. Direct Connection Modes

Azure Cosmos DB for NoSQL SDKs offer two connection modes:

- **Gateway:** Communicates over HTTPS (typically port 443); simpler through restrictive firewalls.
- **Direct:** Opens additional direct TCP connections to backend partitions/replicas per SDK/region mechanics; typically lowers latency where permitted.

Never assume Direct mode uses only port 443. Port ranges and endpoints vary by API, SDK, Private Endpoint, and service version. **Check the current SDK's networking requirements** rather than hardcoding legacy port ranges.

If Gateway mode works while Direct mode times out, check NSGs, outbound routes, Private DNS, and required Direct-mode TCP ports before touching credentials.

### 12.5. Read-Only Network Checks

Linux/macOS:

~~~bash
ACCOUNT="cos-orders-prod"
COSMOS_HOST="$ACCOUNT.documents.azure.com"

nslookup "$COSMOS_HOST"
nc -vz "$COSMOS_HOST" 443
~~~

Windows PowerShell:

~~~powershell
Resolve-DnsName cos-orders-prod.documents.azure.com
Test-NetConnection cos-orders-prod.documents.azure.com -Port 443
~~~

Passing DNS/TCP checks **does not prove roles or credentials are valid**. Nor does DNS resolution from a laptop prove an AKS Pod uses the same DNS and egress path.

## 13. Account Keys, Resource Tokens, and Secret Rotation

### 13.1. Why Restrict Account Keys?

Account keys and connection strings grant **very broad permissions** per API/account settings. Shipping a key inside browser JavaScript or a mobile app lets attackers invoke the data plane directly, bypassing backend user authentication.

Prefer **Entra ID + native data-plane RBAC** wherever supported. Retain key-based auth only for verified compatibility needs under security review and strict secret lifecycle management.

### 13.2. Primary and Secondary Keys

On accounts supporting primary and secondary keys, rotate zero-downtime as follows:

~~~text
Clients currently use primary
  → Stage secondary secret in Key Vault
  → Test clients on secondary
  → Switch all clients to secondary
  → Regenerate primary under change approval
  → Monitor auth errors and schedule next rotation cycle
~~~

Never regenerate a key while live apps still depend on it without a cutover plan. Never run `az cosmosdb keys list` and paste outputs into logs, chat, or support tickets.

### 13.3. Read-Only Keys Are Not Tenant Isolation

Read-only keys (where supported) block writes, yet remain **broad shared secrets across the account**. They never prevent Tenant A from reading Tenant B's documents inside the same container.

### 13.4. Resource Tokens

Some Cosmos DB APIs/SDKs support **resource tokens** granting scoped, time-limited permissions. Trusted backends issuing them must:

- Authenticate the user and tenant before minting any token.
- Grant minimal scope and short TTLs.
- Never log tokens.
- Verify SDK and permission model compatibility.
- Implement revocation/expiry handling and negative access tests.

If enforcing token boundaries on untrusted clients is risky, keep Cosmos DB access **strictly server-side** and serve authorized API responses instead.

### 13.5. Secrets Management

- Store credentials in Key Vault or a managed secret store.
- Isolate Dev, Staging, and Production secrets.
- Grant Key Vault access via least-privilege managed identities.
- Never commit secrets to Git, Docker images, CI logs, or client bundles.
- Rotate on schedule and immediately upon suspected incidents.
- Test secret reload, reconnection, and recovery in apps.
- Never use an account primary key as a permanent fallback when a data-plane role assignment fails.

## 14. Encryption, CMK, and Multi-Layer Data Protection

### 14.1. At Rest and In Transit

Cosmos DB provides service-managed encryption **at rest**. In transit, clients require **TLS** with hostname and certificate validation. Both are separate layers from authorization.

Proper encryption does not stop an over-privileged app identity from deleting data. Conversely, a Private Endpoint never exempts traffic from TLS validation.

### 14.2. Customer-Managed Keys (CMK)

In supported accounts, APIs, and configurations, Cosmos DB supports **customer-managed keys (CMK)** backed by Key Vault and managed identities.

Preparation checklist:

1. Key Vault or supported key store, access policies, and compliant region.
2. Managed identity and permissions for Cosmos DB to access the key.
3. Key rotation, versioning, and policies preserving older key versions needed for restores.
4. Procedures if a key is disabled, deleted, or the Vault/network becomes unreachable.
5. Verification that **restored accounts** can access valid encryption keys.
6. Compatibility checks across CMK, regions, backup policies, and Private Link.
7. Auditing on every key, role, and Key Vault access change.

**Disabling or losing the encryption key can render data inaccessible** per service design. Never enable CMK without a tested decryption recovery runbook.

### 14.3. Comparing Security Controls

| Mechanism | Primary Protection | What It Does Not Solve |
|---|---|---|
| Private Endpoint | Private network path | Does not grant or check data read permissions |
| Entra ID + native data RBAC | Data-plane authorization | Does not replace routing or TLS |
| CMK / encryption at rest | Protects stored data at rest | Does not block a buggy valid `DELETE` |
| TLS | Encrypts transit and verifies server identity | Does not check end-user business roles |
| Backup / PITR | Recovers historical data states | Does not stop active unauthorized access |
| Audit / alerts | Detection and forensics | Does not automatically recreate deleted data |
| App tenant checks | Business-level authorization | Does not replace account networking |

### 14.4. Multi-Tenancy and Partition Keys

Partitioning `orders` by `/tenantId` organizes data, yet **does not enforce row-level tenant authorization**. A managed identity authorized on the container can query any tenant's data unless the backend restricts it.

Therefore:

- Derive the tenant from verified identity claims, never raw request bodies alone.
- Enforce server-side partition keys and tenant filters.
- Write negative cross-tenant access tests.
- Consider separate containers or accounts when strict trust boundaries are required.
- Keep sensitive values out of logs and unnecessary partition keys.

## 15. Azure Monitor, Diagnostic Logs, and Auditing

### 15.1. Three Telemetry Streams

1. **Service metrics:** RU consumption, request counts, HTTP 429s, storage, latency, availability, and supported account/API dimensions.
2. **Control-plane audit:** Azure Activity Log tracking account, region, firewall, role, backup mode, and restore changes.
3. **Application / data-plane telemetry:** Identity, tenant, operation, item IDs, business event/correlation IDs, and sanitized error details.

Never assume Azure Activity Log logs every individual JSON item mutation. Investigating mass deletions typically requires application audit logs and diagnostic settings **enabled prior to the incident**.

### 15.2. Critical Signals

| Metric or Event | Why Monitor It? |
|---|---|
| Normalized RU consumption | Capacity saturation or abnormal tasks |
| 429 / throttled requests | Requests exceeding available RUs or hot partitions |
| 401 / 403 | Credential, role/scope, or network policy failures |
| Data storage / partition growth | TTL effectiveness, cost, hot partitions |
| p95 / p99 request latency | Network, region, query, or SDK client issues |
| Backup policy changes | Unauthorized reduction of recoverability outside change windows |
| Restore account created | Legitimate recovery drill or anomalous activity |
| SQL role assignments changed | Over-privileged data access granted |
| Key regeneration | Scheduled rotation vs. emergency incident |
| Public access / firewall changes | Policy-violating network exposure |
| Unexpected mass updates / deletes | Buggy script or compromised credentials |
| Diagnostic settings disabled | Suspicious tampering with audit evidence |

Azure Monitor metric names and dimensions vary by API, tier, and region. Never copy metric names from another API account without verifying.

### 15.3. Listing Metric Definitions

~~~bash
COSMOS_ID=$(az cosmosdb show \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --query id \
  --output tsv)

az monitor metrics list-definitions \
  --resource "$COSMOS_ID" \
  --output table
~~~

This is read-only. Select metrics, time grains, aggregations, and dimensions directly from the returned definitions. Never infer a backup failure from an aggregate 429 count—separate request throttling from restore operations.

### 15.4. Sample Application Audit Log

~~~json
{
  "timestampUtc": "2026-11-20T13:18:09Z",
  "service": "orders-migration",
  "deploymentId": "release-42",
  "operation": "PatchOrder",
  "account": "cos-orders-prod",
  "database": "commerce",
  "container": "orders",
  "tenantId": "tenant-01",
  "eventId": "job-42-00013",
  "result": "success",
  "requestChargeRU": 7.1
}
~~~

This is an **application-defined illustrative schema**, not a claim that Azure logs all these fields natively. Keep PII, keys, tokens, and full document bodies out of logs. Propagating correlation IDs from API calls to database operations helps pinpoint exact fault timestamps.

### 15.5. Actionable Alerts

- Mass deletes/updates exceeding baseline per tenant/container.
- Backup policy or role assignment changes outside approved change windows.
- Unplanned re-enabling of public network access.
- Spikes in 401/403 errors suggesting credential issues or leaks.
- Rising 429s/latency or storage approaching capacity limits.
- Failed restores or restore drills exceeding RTO.
- Unscheduled account key regenerations.
- Disabled diagnostic settings or silent Log Analytics ingestion.
- Cost anomalies from lingering restored accounts.

Every alert needs an **owner, severity, threshold, action, and recovery guide**—not an unmonitored email alias.

## 16. Costs of Backup, Restore, and Access Protection

### 16.1. Cost Drivers

| Category | Cost Driver |
|---|---|
| Cosmos DB RU/s | Provisioned or autoscale throughput per mode |
| Storage | Data, indexes, replication across regions |
| Periodic / continuous backup | Mode, retention, redundancy per pricing schedule |
| Restored accounts | Parallel throughput and storage while active |
| Multi-region | Multi-region storage, throughput, replication transfer |
| Private Endpoints | Resource hours and private link data processing |
| Key Vault / CMK | Key operations and key management |
| Diagnostic logs | Log Analytics ingestion, retention, archival |
| Exports / DR copies | Blob / Data Lake storage, compute, and egress |
| Recovery drills | Restored accounts, load tests, cleanup |

No single flat price applies globally; costs vary by region, currency, API/tier, throughput, retention, and active pricing tables.

### 16.2. Estimating RUs—Do Not Confuse with Billing Quotes

Suppose 1,000 requests/second average 5 RUs each:

\[
1000\ \text{requests/s}\times5\ \text{RU/request}=5000\ \text{RU/s}
\]

This represents average RU consumption only—**not** enough to size throughput or forecast invoices. Peaks, hot partitions, query shapes, indexes, regions, retries, and autoscale all change totals, while backups and restored accounts bill separately.

### 16.3. Budget for Parallel Restores

A restore drill temporarily runs **two accounts simultaneously**: original and restored. Budget for parallel throughput, Private Endpoints, telemetry, and validation compute. Never delete a restored account before data validation and owner sign-off complete.

### 16.4. Optimizing Without Weakening Recovery Standards

- Size retention to cover realistic detection windows and compliance rules.
- Tune partition keys and queries to eliminate hot RU waste.
- Clean up stale test/restored accounts promptly upon approval.
- Never disable critical audit logs just to cut ingestion fees.
- Manage accounts, networks, and roles via reviewed IaC.
- Validate backup/restore through scheduled drills.
- Forecast data growth, multi-region multipliers, and capacity headroom.

## 17. Incident Runbook: Data Loss, Auth Failures, and Connectivity Issues

### 17.1. Quick Diagnostic Matrix

| Symptom | Possible Cause | First Check |
|---|---|---|
| DNS fails to resolve endpoint | Wrong Private DNS Zone, forwarder, or VNet link | `nslookup` from the exact client runtime |
| TCP / TLS timeout | Private Endpoint, NSG, route, firewall, SDK Direct mode | Gateway vs. Direct port requirements and path |
| HTTP 401 Unauthorized | Invalid or expired token, key, or credential | Token audience, identity, key rotation |
| HTTP 403 Forbidden | Missing/mis-scoped data-plane role, firewall/network ACL | Role assignments, IP/VNet rules, diagnostic substatus |
| HTTP 429 Too Many Requests | RU cap, hot partition, or traffic spike | RU consumption/partition metrics and SDK retries |
| Query from Tenant A returns Tenant B data | Missing tenant authorization in backend | App policy, partition key check, token claims |
| Data missing after migration | Valid `DELETE`/`UPDATE` with buggy logic | Audit timeline, backups, restore points |
| PITR lacks desired timestamp | Outside retention or unsupported mode/API | Backup policy, earliest/latest restorable time |
| Restore fails to create target | Region, feature, permission, cost, or quota block | Restorable resources, scope, Azure activity errors |
| Restored account returns 403 | Missing role assignments or wrong keys/config | Data-plane roles, identity, policy |
| Restored account times out | Private Endpoint / DNS not provisioned yet | Private path, public access, SDK mode |
| Item `read_item` fails by ID | Wrong partition key or deleted item | `id` + `partition_key`, container metadata |
| CMK / Key Vault error | Key disabled, missing Vault permission, or network block | Key Vault roles, key versions, identity |
| Cost spike after restore drill | Lingering restored account, Private Endpoint, or logs | Cost Management, resource inventory, owner |
| Multi-region failover does not restore old data | Replication is not backup | PITR/restore and reconciliation |

### 17.2. Step 1 — Classify the Incident

Before modifying settings:

- **Availability / network:** App cannot reach the account or region.
- **Authentication / authorization:** Requests reach the service and get 401/403.
- **Throttling / performance:** SDK sees 429s, high latency, or high RUs.
- **Data corruption / deletion:** Requests succeed technically yet store wrong business state.
- **Backup / restore issue:** Cannot select timestamp/target or restore validation fails.
- **Credential compromise:** Leaked key/identity or anomalous data access.

An incident can span layers; record UTC timestamps and operation IDs to correlate evidence.

### 17.3. Step 2 — Confirm the Exact Resource

~~~bash
az account show \
  --query "{name:name, subscriptionId:id}" \
  --output json

az cosmosdb show \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --query "{name:name, kind:kind, backupPolicy:backupPolicy, publicNetworkAccess:publicNetworkAccess}" \
  --output json
~~~

Never dump primary keys. Confirm whether workloads point to **prod or staging** so you never edit the wrong resource.

### 17.4. Step 3 — Network and TLS

- Test DNS FQDN resolution from the Pod, VM, or host running the SDK.
- If using Private Endpoints, verify Private DNS resolution and connection approval state.
- Inspect NSGs, UDRs, firewalls, and outbound rules.
- If Direct mode fails, test Gateway mode per runbook and compare required TCP ports; **never swap credentials to debug a network timeout**.
- Never replace the hostname with a private IP or disable TLS certificate validation.
- Run a negative connectivity test from an untrusted source after fixing.

### 17.5. Step 4 — Roles and Identities

For SDK Entra authentication:

1. Which exact identity is running (client ID, principal object ID, tenant)?
2. Does a native data-plane role assignment exist at the right role and scope?
3. Does the role definition include the required `dataActions` for queries/reads/writes?
4. Was an Azure IAM role confused with Cosmos SQL data-plane RBAC?
5. Does a newly created assignment still need propagation time?
6. Does account networking allow the request through?
7. Is `DefaultAzureCredential` accidentally picking up a developer token instead of the production managed identity?

Never “fix” a 403 by granting `Owner` or pasting a primary key into the app before identifying the root cause.

### 17.6. Step 5 — Recovering Data After Confirmed Bad Writes

1. Halt the offending writer or isolate its identity.
2. Preserve audit evidence and the event timeline.
3. Identify **when corruption started** (UTC timestamp just before the error).
4. Check backup policy, retention, and restore eligibility.
5. Restore into a separate resource if required by workflow.
6. Compare pre- and post-incident data by business IDs and tenant/partition.
7. Analyze valid writes occurring after the restore point.
8. Verify target identities, Private Endpoints, RU/s, CMK, and alerts.
9. Obtain sign-off before executing cutover or merge.
10. Monitor closely and clean up temporary resources once safe.

### 17.7. Step 6 — Post-Restore Verification

- Do critical document counts match per tenant?
- Do item IDs and partition key values match valid originals?
- Will payments, shipments, emails, or downstream events accidentally replay?
- Does the API return the exact contract with p95 latency meeting SLOs?
- Are security policies, logs, alerts, and budgets active?
- Does the restored account's backup policy still meet RPO/retention targets?
- Have you scheduled a postmortem to fix code, permissions, and processes?

**Service-level restore completion is not full business recovery.**

## 18. Designing a Complete Data-Protection Scenario

### 18.1. Ordering Architecture

~~~mermaid
flowchart LR
    W["Web / Mobile"]
    APIM["API Management\nAuth, rate limit"]
    API["Order API\nManaged identity"]
    VN["VNet / Private DNS"]
    PE["Private Endpoint"]
    COS["Cosmos DB NoSQL\ncommerce/orders"]
    EV["Event Hubs / Service Bus\nbusiness events"]
    INS["Azure Monitor\nAlerts + Audit"]
    BK["Continuous backup\nRetention per RPO"]
    REST["Restored account\nfor drill/incident"]
    W --> APIM --> API
    API --> VN --> PE --> COS
    API --> EV
    COS -.-> BK --> REST
    API -.-> INS
    COS -.-> INS
~~~

Assume container `orders` uses partition key `/tenantId`. The backend authenticates the tenant from user session/claims and enforces the partition key server-side—never trusting an unverified `tenantId` from the request.

### 18.2. Reliable Order Creation Flow

1. API authenticates user and tenant.
2. Server binds verified `tenantId` and generates `orderId`/`idempotencyKey`.
3. Cosmos SDK uses managed identity and a container-scoped data-plane role.
4. Writes the item to its partition and checks the response.
5. Emits business events via outbox / consistency-safe design.
6. Audit log records `eventId`, UTC timestamp, actor, and outcome without leaking secrets.
7. Retries 429s with SDK backoff; write retries remain idempotent.
8. On errors, classifies networking vs. authorization vs. throttling before retrying.

### 18.3. Handling Accidental Mass Deletions by a Batch Job

1. Alerts detect anomalous mass deletes.
2. Disable/freeze the buggy job and revoke unneeded permissions.
3. Log incident severity, business owner, and UTC incident timestamp.
4. Use PITR if supported by account/mode and within retention.
5. Restore into a separate account—never directly over live production.
6. Diff records and reconcile valid writes after the restore point.
7. Choose **selective merge** or **full account cutover** based on business impact.
8. Validate apps, identities, and networking; keep monitoring and run a postmortem.

### 18.4. Team Responsibilities

| Role | Responsibility |
|---|---|
| Product / data owner | RPO/RTO, recovery scope, business sign-off |
| SRE / Cloud Platform | Backup policy, accounts/networking, restore execution, monitoring |
| Security / IAM | Credential compromise response, RBAC, Private Endpoints, auditing |
| Database / Data Engineering | Document validation, partition keys, TTL/indexing, reconciliation |
| Backend team | Idempotency, app config, endpoint cutover, tenant checks |
| FinOps | Cost modeling for retention, restores, and sandboxes |
| Compliance | Data residency, retention, and audit constraints |

Never let a single principal hold simultaneous permissions to delete all data, disable logs, and weaken backup policies without peer review or break-glass controls.

## 19. Safe Hands-On Practice

### 19.1. Environment

Suppose you have a **sandbox Cosmos DB for NoSQL account**:

~~~text
Resource group:  rg-cosmos-lab
Account:         cos-orders-lab
Database:        commerce
Container:       orders
Partition key:   /tenantId
Backup mode:     lab-dependent—check first
Application:     orders-api-lab (managed identity)
~~~

**Never use production.** Without a lab account, complete the exercises below on paper; provisioning live resources is optional.

### 19.2. Part A — Read-Only Preflight

~~~bash
RG="rg-cosmos-lab"
ACCOUNT="cos-orders-lab"

az cosmosdb show \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --query "{name:name, backupPolicy:backupPolicy, publicNetworkAccess:publicNetworkAccess}" \
  --output json

az cosmosdb sql role definition list \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --output json

az cosmosdb sql role assignment list \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --output json
~~~

**Questions:**

- What is the current backup mode?
- Which data-plane role is assigned to the Order API identity?
- Can it read containers outside `orders`?
- Does `publicNetworkAccess` comply with policy?
- Can self-service restore run under the current mode and API?

Never print account keys during checks.

### 19.3. Part B — Selecting a Backup Policy

Two independent workloads:

- **App A:** Experimental reporting; tolerates losing several hours of data and already maintains external exports.
- **App B:** Production orders; bugs are caught within minutes and require rewinding to right before a bad deploy.

**Suggested answer:** App A can use periodic backup if RPO and restore workflows suffice. App B should evaluate continuous PITR with retention covering detection windows—verifying API support, cost, RTO, and reconciliation rather than assuming continuous meets every RPO/RTO automatically without testing.

### 19.4. Part C — Recovering from Bad Updates

A job at 14:05 UTC corrupts `status` on 5,000 orders. Between 14:05 and 14:30, 800 legitimate new orders arrive.

**Question:** Should you restore the whole account to 14:04 and immediately cut over?

**Answer:** No. Verify backup eligibility, restore into a new account, and **reconcile the 800 valid orders** plus valid edits after 14:04. A selective data merge may be far cleaner than a full-account swap.

### 19.5. Part D — Data-Plane Roles

Container `orders` should only be accessed by `orders-api`. A principal holds Azure IAM `Contributor` on the resource group with no Cosmos SQL data-plane role.

**Question:** Can that principal read items through the Entra SDK?

**Answer:** No. Control-plane RBAC and native data-plane RBAC are separate; you need the proper data-plane role/scope and network path.

### 19.6. Part E — Network Policy

An account has a Private Endpoint, yet public access remains enabled with an old IP firewall allowlist.

**Question:** Can you declare the database private-only?

**Answer:** No. Creating a Private Endpoint does not disable public access. Disable public network access per policy after verifying the app connects cleanly over the private route.

### 19.7. Part F — Partition Keys and Tenants

An API calls `read_item(id, partition_key=tenantId)` taking `tenantId` straight from a client query parameter.

**Question:** Has the Cosmos partition key enforced tenant isolation?

**Answer:** No. Authenticate the tenant from verified identity claims, check business ownership, and force the partition key server-side. Partition keys organize data; they are not authentication.

### 19.8. Part G — Diagnosing 403

A newly assigned managed identity has Data Contributor scoped to `/dbs/commerce/colls/orders`, yet the SDK still returns 403. What do you check?

**Answer:** Active identity, principal object ID, role definition/`dataActions`, scope, propagation delay, public network ACLs / Private Endpoint / DNS, and diagnostic substatus. Never hastily switch to a primary key.

### 19.9. Part H — Restored Account Connectivity Failure

The Portal confirms the restored account was created, yet the API times out hitting the target endpoint.

**Answer:** Check the new hostname, Private Endpoint approval, Private DNS zone links, routing, SDK Gateway/Direct port needs, TLS, and identity/role assignments. Restoring data does not recreate production networking.

### 19.10. Part I — Cost Review

A restore drill left an extra account running for 3 days with verbose diagnostic logging enabled.

**Answer:** Check Cost Management, restored account throughput/storage, regional/network charges, retention, log ingestion, and cleanup approvals. Never delete before validation and sign-off finish.

## 20. Pre-Production Checklist for Cosmos DB

- [ ] Account API, backup mode, and retention satisfy RPO requirements.
- [ ] Tested restoring to a target resource and measured actual RTO.
- [ ] Runbooks cover account, container, or item recovery per supported features.
- [ ] Practiced reconciling valid writes occurring after the restore point.
- [ ] Control-plane and data-plane roles separated with least privilege.
- [ ] Apps use managed identity / Entra instead of account keys where supported.
- [ ] Account keys secured, rotated, and governed by a break-glass runbook.
- [ ] No keys or tokens exposed in browser, mobile, or client logs.
- [ ] Private-only networking enforced if required; Private Endpoint/DNS/routes tested.
- [ ] TLS/certificate validation and SDK connection mode properly configured.
- [ ] Backend enforces tenant authorization independently of partition keys.
- [ ] CMK / Key Vault lifecycles verified if enabled.
- [ ] Azure Monitor, auditing, and alerts enabled with explicit owners.
- [ ] RUs/429s, latency, storage, and security events actively monitored.
- [ ] Budgeted for backup retention, multi-region copies, and temporary restored accounts.
- [ ] Data privacy/residency, incident escalation, and backup ownership documented.

## 21. Self-Check Questions

**Question 1.** Does Cosmos DB multi-region replication recover data accidentally deleted by an app?

**Answer:** No. Replication propagates valid writes and deletes; you need backups/PITR or an independent historical store.

**Question 2.** How do periodic and continuous backups differ in restore-point selection?

**Answer:** Periodic restores from scheduled snapshots; continuous supports PITR within a restorable window per supported API/configuration.

**Question 3.** Can an account with continuous backup restore to any arbitrary date in history?

**Answer:** No. Only within the active retention window and supported restorable timestamps.

**Question 4.** Does continuous restore automatically overwrite the live production account?

**Answer:** Never assume so. Restores typically create a new target account requiring validation and cutover.

**Question 5.** Why can restoring to 14:04 lose legitimate business data?

**Answer:** Mutations after 14:04 are absent from that snapshot and require reconciliation or replay.

**Question 6.** Does Azure IAM `Contributor` replace Cosmos DB native data-plane RBAC?

**Answer:** No. They govern different planes; Entra SDK access requires the proper data-plane role.

**Question 7.** Does Data Contributor scoped to container `orders` grant write access to all containers?

**Answer:** No. Access follows `dataActions` and assigned scope; verify with negative tests.

**Question 8.** Why must you never put an account primary key in browser JavaScript?

**Answer:** Browsers are untrusted environments and primary keys grant broad power, letting attackers call the data plane directly.

**Question 9.** Does creating a Private Endpoint automatically turn off public network access?

**Answer:** Never assume so. Verify public access policies alongside private connectivity.

**Question 10.** Is a tenant-based partition key a tenant security mechanism?

**Answer:** No. The backend must authenticate and authorize tenants; partition keys only route data.

**Question 11.** Why might Gateway mode succeed while Direct mode times out?

**Answer:** Direct mode requires additional TCP connections/routes; check Direct-mode ports, NSGs, Private Link, and DNS.

**Question 12.** Does CMK prevent an authorized app from deleting an item?

**Answer:** No. CMK protects data at rest, not authorization, backups, or application logic.

**Question 13.** Does Azure Activity Log capture every JSON item edit?

**Answer:** Not by default. Enable data-plane diagnostics and application audit logs.

**Question 14.** Does a successful restore automatically copy data-plane role assignments and Private Endpoints from the old account?

**Answer:** Never assume so. Explicitly check metadata, networking, identities, keys, and monitoring on the restored account.

**Question 15.** Which alerts catch a buggy job updating thousands of orders?

**Answer:** Mass-update/delete anomaly alerts per service/container/tenant paired with business metrics and deployment correlation.

**Question 16.** Should backup policy changes skip review because they “don't touch data”?

**Answer:** No. Policy edits impact recoverability, billing, and reversibility.

**Question 17.** Can an arbitrary JSON export file replace PITR?

**Answer:** No. Exports require verifying point-in-time consistency, partition keys/schemas, indexing/TTL, permissions, and replay paths.

**Question 18.** Why is deleting a restored account right after the Portal reports “restore succeeded” a mistake?

**Answer:** You still need data validation, app testing, reconciliation, and business sign-off; premature deletion destroys your recovery target.

## Key Takeaways

- **Managed and multi-region Cosmos DB does not prevent accidental deletions**; backups, restore drills, identity, and auditing remain your design responsibility.
- **Periodic backup** captures scheduled snapshots; **continuous backup / PITR** supports rewinding within a restorable window per eligible API and tier.
- **Restoring normally provisions a new target account requiring data, role, and network checks**, plus reconciliation of valid writes after the restore point.
- **Azure control-plane RBAC differs from Cosmos DB for NoSQL data-plane RBAC**; prefer managed identity / Entra with least-privilege scopes.
- **Account keys are broad shared secrets**; keep them out of clients and rotate strictly.
- **Private Endpoints, Private DNS, TLS, and RBAC** are complementary layers; partition keys never replace tenant authorization.
- **CMK and encryption do not replace backups or identity governance**; losing key access can lock data permanently.
- Combine **Azure Monitor, diagnostics, and business audit logs** to spot anomalous access, 429s, errors, mass edits, and backup policy changes.
- Consider data protection production-ready only with **tested RPO/RTO, restore runbooks, security tests, cost budgets, and clear ownership**.
