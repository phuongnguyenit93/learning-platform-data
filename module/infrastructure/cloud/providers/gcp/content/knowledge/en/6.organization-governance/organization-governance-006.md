# Cloud Asset Inventory and Configuration Inventory on Google Cloud

> **Chapter:** Organization Governance  
> **Module:** **CLOUD_PROVIDERS_GCP** — Explore Google Cloud from project organization, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners learn to select services, protect resources, automate releases, and monitor reliability alongside cost.

When an organization has hundreds of projects and thousands of resources, the platform team needs to know **what exists, where it resides, who owns it, which IAM permissions are assigned, and which configurations just changed**. Individual service consoles only show a slice of infrastructure state.

**Cloud Asset Inventory (CAI)** is a Google Cloud service for searching, listing, analyzing, exporting, and monitoring metadata of supported resources and policies at the project, folder, or organization scope. CAI supplies critical data for configuration inventory, IAM governance, auditing, drift detection, and lifecycle management.

A key principle from the start: **CAI observes metadata; it does not automatically ensure every resource is secure, does not replace data backups, and is not an instantaneous database for every change**.

## Learning Objectives

After this lesson, learners can:

1. Explain assets, asset types, content types, scopes, snapshots, and metadata changes.
2. Distinguish **SearchAllResources**, **SearchAllIamPolicies**, **ListAssets**, **ExportAssets**, **GetAssetHistory**, and feeds.
3. Use read-only `gcloud` commands to inventory resources, locations, labels, and IAM bindings within granted scope.
4. Design inventory rules by owner, environment, location, resource type, IAM, and lifecycle.
5. Describe how to export snapshots to Cloud Storage/BigQuery and use Pub/Sub to observe changes.
6. Understand limitations around history, consistency, data completeness, access permissions, and cost impact.
7. Analyze a multi-project audit scenario involving Compute Engine, GKE, Cloud Run, VPCs, and storage.

## 1. Assets and the Goals of Configuration Inventory

An **asset** is a governed object or metadata supported by Cloud Asset Inventory. For example:

- Compute Engine VMs, disks, VPC networks, or subnets.
- Cloud Storage buckets.
- GKE clusters, node pools; Cloud Run services.
- Certain Cloud SQL, BigQuery, or other service resources per the supported catalog.
- IAM allow policies, Organization Policies, Access Context Manager policies.
- Certain OS inventory metadata and resource relationships depending on product capabilities.

Each asset has a **type** such as **compute.googleapis.com/Instance** or **storage.googleapis.com/Bucket**, a **full resource name**, a scope, and other attributes matching its content type. Metadata structures can differ between services.

Simplified example:

~~~yaml
# Illustrates concepts only; not verbatim JSON/YAML returned by the API.
name: //compute.googleapis.com/projects/shop-prod/zones/us-central1-a/instances/123456789
assetType: compute.googleapis.com/Instance
location: us-central1-a
labels:
  environment: production
  team: payments
  application: checkout
~~~

An asset's full resource name is not identical to a VM's display name; project ID, project number, and resource ID also serve different roles. To reconcile data across systems, preserve **canonical identifiers** and each source's normalization rules.

### 1.1. Why Is Periodic Inventory Needed?

Infrastructure changes from many sources: Terraform, CI/CD pipelines, Console, CLI, autoscaling, and direct operator actions. Resources are created, have permissions altered, change locations when recreated, get relabeled, or get deleted. A manual spreadsheet quickly goes stale.

A good inventory cycle helps answer:

| Governance Question | Required Data | Possible Action Triggered |
|---|---|---|
| Which resources lack an owner? | Asset type, project, labels/tags | Identify owner, update metadata via IaC |
| Which VMs or databases sit outside approved regions? | Location, resource configuration | Review data residency requirements and migration plan |
| Who holds sensitive roles? | IAM allow policy, principal, role, scope | Verify least privilege and exception approvals |
| Are there forgotten experimental resources? | Labels, create/update time, project | Check dependencies and cost before cleaning up |
| Which resources appeared since yesterday? | Two snapshots or feeds | Cross-check PRs and audit logs |
| Were configurations changed outside pipelines? | Asset snapshots, feeds, IaC state, audit logs | Investigate drift and reconcile source of truth |

CAI is an **observational data source**. It does not automatically answer "who is the owner" if the organization has not standardized owner metadata and populated those fields.

## 2. Relationship to the Resource Hierarchy

Google Cloud organizes resources into organizations, folders, and projects. CAI lets you operate at the scope matching your permissions and API method.

~~~mermaid
flowchart TD
    O["Organization"]
    F1["Folder: commerce"]
    F2["Folder: analytics"]
    P1["Project: shop-dev"]
    P2["Project: shop-prod"]
    P3["Project: data-prod"]
    R1["VM / VPC"]
    R2["GKE / Cloud Run / Cloud SQL"]
    R3["BigQuery"]
    O --> F1
    O --> F2
    F1 --> P1
    F1 --> P2
    F2 --> P3
    P1 --> R1
    P2 --> R2
    P3 --> R3
    CAI["Cloud Asset Inventory"] -. "Search/List within authorized scope" .-> O
    CAI -. "Or select folder/project" .-> P2
~~~

- **Organization:** broad scope for centralized inventory, requiring permissions at that level.
- **Folder:** supports grouping administrative units; many CAI operations accept folders as a scope.
- **Project:** an easy starting scope when learning or when authorized to observe only one product/environment.

**Never assume an organization query always sees all data**: API type, scope permissions, supported asset types, filters, pagination, and index freshness all affect results. If a tool returns only 100 resources, check limits/pagination before claiming the organization has exactly 100 resources.

### 2.1. Related Products Do Not Replace One Another

| Product / Mechanism | Primary Value | Limitations for Inventory |
|---|---|---|
| **Cloud Asset Inventory** | Metadata catalog, policies, snapshots, search, feeds | Does not capture every runtime/data event |
| **Cloud Audit Logs** | API events, actions, and actors per log type | Not a complete snapshot of current state |
| **Cloud Monitoring** | Metrics, alerts, uptime/SLOs | Does not fully describe ownership and policies |
| **Security Command Center** | Findings, vulnerabilities, misconfigurations depending on tier | Does not replace full operational inventory |
| **Cloud Billing** | Costs by project/service/SKU | Does not show all security configurations |
| **Terraform/IaC state** | Resources managed by code | Does not see resources created outside state |
| **Organization Policy and IAM** | Enforce permissions and constraints | Not an aggregate table of all resources |

To answer "who created the VM?", check audit logs. To answer "does the VM have OS vulnerabilities?", use the corresponding vulnerability/OS inventory solution. To answer "where do VMs currently exist and what labels do they carry?", CAI is the right starting point.

## 3. Content Type and Asset Type

An **asset type** describes the kind of object, such as **compute.googleapis.com/Instance**. A **content type** specifies which layer of content to retrieve.

| Content Type | Content | Example Use Case |
|---|---|---|
| **RESOURCE** | Resource configuration metadata | Inventory of VMs, buckets, clusters, and locations |
| **IAM_POLICY** | IAM allow policies on supported resources | Find principals/roles assigned to resources |
| **ORG_POLICY** | Supported Organization Policies | Audit location rules and governance constraints |
| **ACCESS_POLICY** | Supported Access Context Manager metadata | Inspect parts of access policies |
| **OS_INVENTORY** | OS inventory details when integrated | Support OS metadata inventory |
| **RELATIONSHIP** | Relationships between supported asset types | Trace relevant infrastructure dependencies |

Not every asset type works with every API or content type. **RELATIONSHIP** and advanced analysis features may require **Security Command Center Premium/Enterprise** or specific product conditions. Support lists evolve; always check [Supported asset types](https://docs.cloud.google.com/asset-inventory/docs/asset-types) before building automation.

### 3.1. Three Metadata Layers to Distinguish

1. **Normalized fields:** full resource name, asset type, scope, location, create/update timestamps, labels if present.
2. **Service-specific payload:** detailed fields for Compute Engine, GKE, Cloud Run, or databases.
3. **Policies/relationships:** IAM bindings, Organization Policies, and service-supported relationships.

A simple rule like "VM missing owner label" can rely on normalized metadata. A rule like "VM has a specific protection setting enabled" may require reading the `RESOURCE` payload and verifying against the Compute Engine API.

### 3.2. CAI Is Not a Data Backup

Inventorying a Cloud Storage bucket does not mean CAI backs up every object. Likewise, inventorying a Cloud SQL instance does not copy database table contents. To track object uploads, data access, or protect data, use the appropriate service's event, logging, and backup mechanisms.

## 4. Choosing the Tool: Search, List, Export, History, and Feed

~~~mermaid
flowchart LR
    R["Resource / policy metadata"] --> S["SearchAllResources / SearchAllIamPolicies"]
    R --> L["ListAssets"]
    R --> E["ExportAssets"]
    R --> H["GetAssetHistory"]
    R --> F["Feeds → Pub/Sub"]
    S --> Q1["Fast query investigation"]
    L --> Q2["In-scope snapshot"]
    E --> Q3["BigQuery / GCS reporting"]
    H --> Q4["Recent history"]
    F --> Q5["Near real-time change reaction"]
~~~

| Operation | Primary Use Case | Notable Distinctions |
|---|---|---|
| **SearchAllResources** | Search by name, type, location, labels, and supported fields | Uses CAI search syntax; not SQL |
| **SearchAllIamPolicies** | Search IAM allow bindings by role/principal/condition | Returns only bindings matching the query, not all effective permissions |
| **ListAssets** | Retrieve an asset snapshot by scope/content type | Suitable for building point-in-time inventory |
| **ExportAssets** | Export asset snapshots into Cloud Storage or BigQuery | Suitable for auditing and large-scale analysis |
| **GetAssetHistory** | View creations/updates/deletions within the history window | Bounded by time window and scope |
| **Feeds** | Publish supported metadata change notifications to Pub/Sub | Requires a consumer handling retries/duplicates and verifying state |
| **QueryAssets** | Analyze assets directly using BigQuery-compatible SQL syntax | Subject to tier/feature and permission requirements |

**Key point on freshness:** CAI provides **eventual consistency** for current data and **best-effort consistency** for historical data. A newly created resource may not immediately appear in search results; a snapshot alone is never sufficient evidence for deletion or emergency permission revocation.

## 5. SearchAllResources: Finding Resources by Criteria

### 5.1. Read-Only gcloud Commands

Requires `gcloud` CLI installed and authenticated, the Cloud Asset Inventory API available, the principal holding **cloudasset.assets.searchAllResources** on the scope, and necessary quota project/Service Usage configuration.

~~~bash
PROJECT_ID="shop-dev"

# View searchable resources in the project.
gcloud asset search-all-resources \
  --scope="projects/$PROJECT_ID" \
  --format="table(name,assetType,location)"

# View only Compute Engine instances.
gcloud asset search-all-resources \
  --scope="projects/$PROJECT_ID" \
  --asset-types="compute.googleapis.com/Instance" \
  --format="table(name,assetType,location,labels)"

# Find asset names containing checkout.
gcloud asset search-all-resources \
  --scope="projects/$PROJECT_ID" \
  --query="name:checkout" \
  --format="table(name,assetType,location)"
~~~

These commands **do not create or modify resources**. If no results appear, check permissions, scope, asset types, query syntax, and indexing delay before drawing conclusions.

### 5.2. Querying by Location and Labels

~~~bash
# Example finding resources in locations containing us-central1.
gcloud asset search-all-resources \
  --scope="projects/$PROJECT_ID" \
  --query="location:us-central1" \
  --format="table(name,assetType,location)"

# Example finding label metadata containing production.
gcloud asset search-all-resources \
  --scope="projects/$PROJECT_ID" \
  --query="labels:production" \
  --format="table(name,assetType,labels)"
~~~

The syntax **labels:production** performs an indexed search; it is not an exact SQL check like **environment = production**. When using results to enforce policies, verify exact key/value pairs against the schema or specific query fields supported by CAI. Avoid treating keyword search results as absolute compliance proof.

### 5.3. Searching Within an Organization or Folder

~~~bash
ORG_ID="123456789012"
FOLDER_ID="234567890123"

# Only principals granted permission on the organization can query that scope.
gcloud asset search-all-resources \
  --scope="organizations/$ORG_ID" \
  --asset-types="compute.googleapis.com/Instance" \
  --format="table(name,assetType,location)"

gcloud asset search-all-resources \
  --scope="folders/$FOLDER_ID" \
  --query="name:checkout"
~~~

These IDs are placeholders. View permissions at a project do not automatically grant organization-wide queries. When extracting at broad scope, topology data and application names can be sensitive; restrict recipients and retention periods.

### 5.4. Search Query vs. gcloud Filter

**--query** is evaluated server-side by Cloud Asset Inventory with its own operators and syntax. **--filter**, when used, is client-side/gcloud result filtering. The two expressions differ in purpose and syntax. For complete results, account for **--limit**, pagination, and supported asset types.

## 6. SearchAllIamPolicies: Inventorying IAM Allow Bindings

An IAM allow policy contains bindings between principals, roles, and resources. **SearchAllIamPolicies** helps find policies containing:

- **roles/owner** or high-privilege roles.
- User, group, or service account emails.
- **allUsers** or **allAuthenticatedUsers** principals.
- IAM conditions related to resources under review.

### 6.1. Read-Only gcloud Examples

~~~bash
PROJECT_ID="shop-dev"

# Bindings with roles/owner.
gcloud asset search-all-iam-policies \
  --scope="projects/$PROJECT_ID" \
  --query="policy:roles/owner" \
  --format="json"

# Bindings for a specific service account.
gcloud asset search-all-iam-policies \
  --scope="projects/$PROJECT_ID" \
  --query="policy:caller@shop-dev.iam.gserviceaccount.com" \
  --format="json"

# Bindings containing allUsers.
gcloud asset search-all-iam-policies \
  --scope="projects/$PROJECT_ID" \
  --query="memberTypes:allUsers" \
  --format="json"
~~~

Search results may include **only the bindings matching the query**, not the entire IAM policy of each resource. Searching requires **cloudasset.assets.searchAllIamPolicies** on the scope.

### 6.2. Do Not Confuse Found Bindings with Effective Permissions

| Question | What IAM Policy Search Provides | What Still Needs Checking |
|---|---|---|
| Where is the Owner role granted? | Bindings matching the query | Actual scope, conditions, and principals |
| Does a user inherit access from a parent folder? | May show bindings in broader scopes | Resource hierarchy inheritance, group memberships |
| Can a principal read a bucket? | Can locate related policies | Role permissions, conditions, deny policies, other policies |
| Can a service account be impersonated? | Some relevant bindings | Service Account Token Creator grants and other policies |
| Is a resource truly public? | May show `allUsers` bindings | Product configuration and effective policies |
| Will an API call succeed? | Does not fully determine | Effective IAM, quotas, enabled APIs, networking, service status |

When analyzing "**who can access which resource**," use **IAM Policy Analyzer**, evaluate inheritance, and inspect deny/conditional rules; searching allow bindings is only one step. For custom roles, analyzing constituent permissions may also require **iam.roles.get**.

**Never run automated binding-deletion scripts solely from search results.** You must verify the role, accountable owner, production impact, and approval workflow.

## 7. ListAssets and the 35-Day Configuration History

**ListAssets** lists assets in a scope for a given content type.

~~~bash
PROJECT_ID="shop-dev"

# List RESOURCE metadata in the project.
gcloud asset list \
  --project="$PROJECT_ID" \
  --content-type=resource \
  --format="json"

# Restrict to supported VMs.
gcloud asset list \
  --project="$PROJECT_ID" \
  --asset-types="compute.googleapis.com/Instance" \
  --content-type=resource \
  --format="json"
~~~

Note that if no content type is specified, the API may return only basic fields like asset name and type. For large inventories, export snapshots or process paginated output rather than dumping huge JSON payloads to the terminal.

### 7.1. Querying a Snapshot Time

~~~bash
# Example using a date within the supported history window.
gcloud asset list \
  --project="shop-dev" \
  --content-type=resource \
  --asset-types="compute.googleapis.com/Instance" \
  --snapshot-time="2026-11-18T00:00:00Z" \
  --format="json"
~~~

Per documentation, CAI allows retrieving create/update/delete history for **up to 35 days**. For assets unchanged during that window, the system can return the latest state. The dedicated **GetAssetHistory** API supports history at **organization and project** scopes, without folder scope like search/list operations.

**35 days is not enough for multi-quarter audit history.** If long-term history is needed, design **periodic snapshots, change logs, and retention** from the start.

### 7.2. History and Audit Logs Serve Different Roles

- **Asset history:** metadata state and changes stored by CAI.
- **Cloud Audit Logs:** API calls, actors, and timestamps by log type.
- **Git/IaC history:** which commit/PR reviewed and introduced the change.
- **Monitoring:** whether the change impacted traffic, latency, errors, and SLOs.

For example, CAI shows an IAM policy changed on a given date, but to find **who performed it and why**, correlate with audit logs and related PRs/tickets.

## 8. ExportAssets to BigQuery or Cloud Storage

**ExportAssets** writes metadata snapshots to an administrator-configured destination. It suits periodic inventories, audits, dashboards, and retention longer than CAI's history window.

~~~mermaid
flowchart TD
    CAI["Cloud Asset Inventory"] --> E["ExportAssets"]
    E --> GCS["Cloud Storage: snapshot with retention"]
    E --> BQ["BigQuery: inventory table"]
    BQ --> CHECK["SQL: labels, location, owner, policy"]
    CHECK --> REPORT["Dashboard or exception report"]
    REPORT --> REVIEW["Owner verifies and fixes via IaC"]
~~~

### 8.1. Example Exporting Snapshots to BigQuery

The following command **writes data to BigQuery** and is not part of read-only practice. Run it only when authorized to create tables, configure APIs, and hold permissions on both the source scope and destination dataset.

~~~bash
SOURCE_PROJECT="shop-dev"
BQ_PROJECT="inventory-admin"
BQ_DATASET="asset_inventory"
BQ_TABLE="snapshot_20261119"

gcloud asset export \
  --project="$SOURCE_PROJECT" \
  --content-type=resource \
  --asset-types="compute.googleapis.com/Instance,storage.googleapis.com/Bucket" \
  --bigquery-table="projects/$BQ_PROJECT/datasets/$BQ_DATASET/tables/$BQ_TABLE"
~~~

When exporting to an existing table, verify **overwrite, append, and partitioning** behavior beforehand. The **--output-bigquery-force** flag can overwrite data in applicable modes, so never add it to pipelines without destination controls.

Documented limitations: not every asset field is supported in exports; some frequently changing fields may export as **null**; exporting per asset type has limitations across different GKE resource types. Inventory rules must treat **null = undetermined** when data is missing rather than defaulting to "pass" or "fail."

### 8.2. Asset Export vs. Cloud Billing Export

| Cloud Asset Inventory export | Cloud Billing export |
|---|---|
| Metadata on resources, configurations, and policies | Usage cost data, service, SKU, credits |
| Shows which resources exist and how they are configured | Shows what items are incurring charges |
| Easy to organize as point-in-time snapshots | Follows billing data recording mechanics |
| Primary key usually based on asset/resource name | Resource ID may be absent on certain line items |
| Used for configuration governance | Used for FinOps/invoice reconciliation |

To find ownerless VMs that still incur charges, combine both sources after normalizing identifiers and time windows. **Never join on fuzzy/similar names** and assume exact accuracy; billing resource identifier coverage varies by service and export type.

### 8.3. Scheduling Snapshots Properly

1. Fix the **scope, asset types, content type**, and collection timestamp.
2. Export into protected buckets/datasets with retention and clear ownership.
3. Log job status, record counts, schema, and any permission errors.
4. Compare the new snapshot against the previous snapshot using stable IDs.
5. Classify **created / updated / deleted / unknown**.
6. Verify significant changes via target APIs and audit logs.
7. Open tickets/PRs for owners; re-verify after remediation.

If the asset count drops from 500 to 450, do not immediately conclude 50 resources were deleted. First check **job failures, filters, permissions, schema, and sync latency**.

## 9. QueryAssets with SQL and Usage Prerequisites

Google Cloud supports querying assets directly with **BigQuery-compatible SQL** in Asset Inventory. Per current documentation, this capability requires an eligible tier/entitlement, such as **Security Command Center Premium/Enterprise or Gemini Cloud Assist**. Not every project has the QueryAssets tab or API enabled.

Illustrative example:

~~~sql
-- Example executed in Asset query when authorized.
SELECT
  name,
  resource.location
FROM
  compute_googleapis_com_Instance
WHERE
  resource.location LIKE '%asia%'
~~~

The QueryAssets table name converts **compute.googleapis.com/Instance** to **compute_googleapis_com_Instance**. Do not blindly run this exact SQL against a BigQuery table created by ExportAssets without checking the target schema: the two methods may use different table layouts.

Without direct QueryAssets entitlement, you can export snapshots to BigQuery and query the exported table with appropriate permissions. Monitor storage and query costs, especially for large inventories.

## 10. Feeds and Pub/Sub: Detecting Metadata Changes

Daily snapshots can miss an IAM change created and deleted within the same day. **Cloud Asset Inventory feeds** send notifications when supported resource metadata or policies change, using **Pub/Sub** as the transport.

~~~mermaid
sequenceDiagram
    participant A as Admin / Terraform / CI
    participant GCP as Google Cloud resource
    participant CAI as Cloud Asset Inventory feed
    participant PS as Pub/Sub topic
    participant W as Cloud Run checker
    A->>GCP: Create/modify resource or policy
    GCP-->>CAI: Supported metadata change
    CAI-->>PS: Welcome message or TemporalAsset event
    PS-->>W: Deliver notification
    W->>W: Inspect event, idempotency, rules
    W-->>A: Alert or ticket for verification
~~~

### 10.1. What Goes Into a Feed Configuration?

- **Scope:** project, folder, or organization.
- **Asset types/names:** resource types or names to monitor.
- **Content type:** `RESOURCE`, `IAM_POLICY`, or other supported types.
- **CEL condition:** filters change types where supported.
- **Pub/Sub topic:** notification destination.
- **Service agent permissions:** grants the feed permission to publish and perform related management tasks.

Per Google Cloud documentation, the **first** notification after creating a feed can be a **string welcome message**, while subsequent notifications use **TemporalAsset** format. Consumers must distinguish both to avoid false alerts.

### 10.2. Example Creating a Feed in a Test Environment

~~~bash
# Command modifies live resources; run only in an authorized project.
gcloud asset feeds create inventory-vm-changes \
  --project="shop-dev" \
  --pubsub-topic="projects/monitoring-dev/topics/asset-changes" \
  --asset-types="compute.googleapis.com/Instance" \
  --content-type=resource
~~~

You must prepare the Pub/Sub topic, service agent publish permissions, and quotas beforehand. **Creating, updating, or deleting a feed can take around 10 minutes to take effect.** Absence of immediate events is not sufficient reason to conclude the feed is broken.

**Limitation:** feeds observe changes to supported asset metadata. For instance, uploading a new object to a Cloud Storage bucket does not mean the **bucket** metadata changed, so never use a bucket feed to monitor every object upload.

### 10.3. Designing a Safe Consumer

- Distinguish welcome messages from `TemporalAsset` payloads.
- Extract asset name, asset type, and change timestamp.
- Handle **duplicate messages** using verifiable event keys/fingerprints.
- Bound retries, use dead-letter topics where appropriate, and monitor backlog.
- Before taking critical actions, verify current state via the target API because indexes can lag.
- Create alerts/tickets with owners; do not auto-rollback every IAM change by default.
- Avoid logging excessive sensitive metadata.

An IAM change may be a legitimate part of a release or incident response. Therefore, automated remediation must rely on the **approved IaC source of truth and policies**, not merely on receiving an event.

## 11. Inventory Rules and Configuration Drift Detection

**Configuration drift** is divergence between the **desired state** in IaC/policies and the **observed state** of live resources.

~~~mermaid
flowchart LR
    D["Desired: Terraform / policy / exceptions"] --> COMP["Compare"]
    A["Observed: CAI snapshot + feed"] --> COMP
    LOG["Audit logs / PR / owner"] --> COMP
    COMP --> OK["Compliant"]
    COMP --> DRIFT["Drift / violation / unknown"]
    DRIFT --> REVIEW["Owner review"]
    REVIEW --> FIX["Fix via approved IaC/API"]
    FIX --> A
~~~

Avoid treating fields **managed automatically by services or changing continuously** as dangerous drift. GKE node count increasing due to autoscaling may be intended behavior; evaluation requires workload context.

### 11.1. Sample Rules

| Rule | Inventory Data | Outcome on Deviation |
|---|---|---|
| Production must have owner/team | Asset labels and project mapping | Request metadata update after confirming owner |
| Databases in approved regions | Resource location and org rules | Review data residency and migration plan |
| `roles/owner` bindings must be justified | IAM allow bindings, exception registry | Open review ticket |
| VMs with public IPs must be approved | Compute Engine metadata, network policy | Check ingress/firewalls; do not delete IP immediately |
| Expired experimental resources | `lifecycle`/`expires_on` labels | Verify dependencies, data, and owner |
| Production has proper backups/HA | Service-specific `RESOURCE` and target API | Verify RTO/RPO and actual configuration |
| Out-of-band IAM or location changes | Feeds, snapshots, audit logs, PRs | Investigate drift, record remediation |

Example internal inventory contract:

~~~yaml
# Sample definition, not a Cloud Asset Inventory API configuration.
controls:
  - id: required-owner
    applies_to: supported_production_resources
    required_labels: [team, application, environment]
    action: report_to_owner

  - id: restricted-location
    applies_to: regulated_data_resources
    allowed_regions: [approved-region-1, approved-region-2]
    exception_requires: [ticket, approver, expires_on]

  - id: excessive-iam
    scope: organization
    review_roles: [roles/owner]
    action: manual_review

  - id: resource-expiry
    scope: development
    requires: [lifecycle, expires_on]
    action: check_dependencies_before_cleanup
~~~

The names **approved-region-1/2** are placeholders, not real region names. Production rules must bind to proper authoritative metadata; relying solely on project names containing "prod" can fail if naming is unstandardized.

### 11.2. Three Result States

Every check should return at least:

- **PASS:** sufficient data and policy-compliant.
- **FAIL:** sufficient data, violates condition.
- **UNKNOWN:** missing metadata, missing permissions, unsupported asset type, or read error.

**UNKNOWN must never be counted as PASS.** If 20% of projects could not be collected due to IAM errors, reporting "100% compliant" on the remaining 80% is misleading.

### 11.3. Governance Metrics to Track

1. **Coverage:** percentage of projects/scopes successfully collected.
2. **Completeness:** percentage of label-supporting resources with complete owner/team/environment labels.
3. **Compliance:** verified PASS rate; keeping UNKNOWN separate.
4. **Detection latency:** time from change to alert.
5. **Remediation latency:** time until verified fix.
6. **Recurring drift:** repeat violations after remediation.
7. **Export integrity:** snapshot job success rate and record count stability.

Measurements must separate cases where an asset type **does not support the checked field** from cases where a resource **is genuinely missing configuration**.

## 12. IAM, Inventory Protection, and Cost Accountability

CAI data can contain network topology, IAM identities, service names, project relationships, and sensitive governance details. Read access to inventory must be controlled.

| Operation | Typical Permission | Notes |
|---|---|---|
| Search resources | **cloudasset.assets.searchAllResources** | Granted at authorized scope |
| Search IAM | **cloudasset.assets.searchAllIamPolicies** | Results contain allow bindings matching query |
| List resources | **cloudasset.assets.listResource** or granular list permissions | Can be narrowed by asset type |
| IAM analysis | **cloudasset.assets.analyzeIamPolicy** plus related permissions | May require `iam.roles.get` and group info |
| QueryAssets SQL | **cloudasset.assets.queryResource** or corresponding content-type permission | Tier-dependent |
| Export and feeds | Appropriate CAI permissions and Cloud Storage/BigQuery/Pub/Sub destination permissions | Includes service agent permissions |

Per CAI documentation, API calls also require permissions such as **serviceusage.services.use** on the appropriate project. A role like **roles/cloudasset.viewer** can help, though it does not guarantee every action. Never grant Owner to an inventory pipeline just to make commands run.

**Data protection practices:**

- Place inventory buckets/datasets in a governance project with least-privilege IAM.
- Restrict who can download full IAM/topology reports.
- Apply appropriate retention and storage locations.
- Separate report readers from the collection service account.
- Monitor costs for BigQuery storage/queries, Cloud Storage, Pub/Sub, and Cloud Run consumers.
- Never publish snapshots or paste sensitive full policies into uncontrolled tickets.

## 13. Read-Only Practice in a Training Project

This lab **does not create or modify resources**; it only requires an authorized project and `gcloud` CLI.

### 13.1. Verify Identity

~~~bash
gcloud auth list
gcloud config list

PROJECT_ID="my-training-project"
gcloud projects describe "$PROJECT_ID" \
  --format="table(projectId,name,projectNumber)"
~~~

### 13.2. Sample Inventory

~~~bash
gcloud asset search-all-resources \
  --scope="projects/$PROJECT_ID" \
  --format="table(name,assetType,location)" \
  --limit=100
~~~

Note that **--limit=100** samples at most 100 results, not the entire project if the project has more than 100 assets. For a complete inventory, collect all pages or run an export.

### 13.3. Inspect VMs and Labels

~~~bash
gcloud asset search-all-resources \
  --scope="projects/$PROJECT_ID" \
  --asset-types="compute.googleapis.com/Instance" \
  --format="table(name,location,labels)"
~~~

Record the results in a table:

| Full resource name | Project | Zone/location | Environment | Owner/team | Notes |
|---|---|---|---|---|---|
| … | … | … | … | … | … |

If no VMs appear in scope, record "**no matching VMs found within the authorized search scope**." Do not infer that no VMs exist in the organization.

### 13.4. Inspect Sensitive IAM

~~~bash
gcloud asset search-all-iam-policies \
  --scope="projects/$PROJECT_ID" \
  --query="policy:roles/owner" \
  --format="json" \
  --limit=20
~~~

Record only the resource, principal, role, and condition if any; do not modify IAM in this lab. If an Owner binding is found, write down the verification question for the owner.

### 13.5. Summarize Results and Recommendations

Short report template:

~~~text
Inventory scope:
Collection time (UTC):
Asset types queried:
Total records returned:
Was result limited/paginated:
Projects covered:
Missing owner/team labels:
Suspicious IAM bindings:
Resources outside approved locations:
UNKNOWN due to missing data/permissions:
Proposed owner and next action:
~~~

A report is valuable when **scope, timestamp, and limitations** are explicit. Readers must know whether "0 violations" came from checking the entire scope or from incomplete data.

## 14. Case Study: Pre-Audit Production Inventory

**Hypothetical scenario:** an enterprise has 60 projects across three folders: **commerce**, **data**, and **shared-platform**. The payment application runs on Cloud Run, GKE, Cloud SQL, Cloud Storage, and several Compute Engine VMs. The security team needs a report confirming:

- Every production resource has a clear owner.
- No Owner roles or public bindings exist outside approved exceptions.
- Sensitive-data workloads reside in approved regions.
- Evidence exists for IAM and critical configuration changes.
- Expired temporary dev resources are reviewed.

### 14.1. Inventory Design

~~~mermaid
flowchart TD
    O["Organization scope"] --> SEARCH["Search resources + IAM bindings"]
    SEARCH --> SNAP["Export snapshot GCS / BigQuery"]
    FEED["Change feeds"] --> PUB["Pub/Sub"]
    PUB --> CHECK["Cloud Run rule checker"]
    SNAP --> RULES["Check labels/location/IAM"]
    CHECK --> TICKET["Tickets and alerts with owners"]
    RULES --> TICKET
    LOG["Audit Logs + IaC + exceptions"] --> TICKET
    TICKET --> VERIFY["Direct verification + fix via PR"]
~~~

**Day one:** grant appropriately scoped read permissions, inventory resources/policies, export snapshots, and classify assets by project/service type.

**Daily:** consume feeds on IAM/supported resource changes, alert on sensitive bindings or new ownerless resources; verify against live state before acting.

**Weekly:** compare snapshots, audit IAM/locations/metadata, follow up with owners on deviations, and manage exceptions.

**Before the audit:** archive scope, timestamps, asset types, PASS/FAIL/UNKNOWN results, audit log evidence, PRs, tickets, and remediation status.

### 14.2. Three Scenarios Requiring Analysis

**A — Newly created VM is missing.** Check eventual consistency, permissions/scope, and the Compute Engine API. Never conclude a VM does not exist from a single search.

**B — `roles/owner` found on a parent folder.** Evaluate inheritance down to projects and effective permissions. Reading only project-level direct bindings can miss it.

**C — Asset count drops by 20 compared to yesterday.** Before logging 20 deleted resources, check snapshot completeness, scanner permissions, schema, and filters.

### 14.3. Sustainable Improvement Steps

Recurring findings should be fixed at the **Terraform templates, pipelines, IAM policies, Organization Policies, and metadata conventions** rather than manually patching individual resources. CAI provides detection and verification signals; the governance source of truth must be maintained by system owners.

## 15. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| "CAI reflects everything instantaneously." | Current data has eventual consistency. |
| "CAI history stores forever." | Only roughly 35 days via the API; long-term history requires separate snapshots. |
| "Search returning 0 means no resources exist." | Could be wrong scope, missing permissions, filters/limits, or indexing delay. |
| "CAI backs up all data in buckets/databases." | CAI inventories supported metadata; it does not replace backups. |
| "IAM search is a complete effective IAM analyzer." | Inheritance, groups, conditions, deny policies, and other constraints still apply. |
| "Increasing asset count increases cost proportionally." | Costs depend on SKUs, usage, duration, storage, network, and discounts. |
| "Feeds track every object event in a bucket." | Feeds track supported asset metadata, not every data operation. |
| "A drop in asset count proves assets were deleted." | You must verify data completeness, permissions, schema, filters, and target APIs. |
| "Every resource type has identical labels and payload." | Schemas and CAI support differ by asset type. |
| "QueryAssets SQL is available in every project." | Depends on tier/entitlement and permissions. |
| "Having one CAI report completes the audit." | Evidence, exceptions, audit logs, owners, and effectiveness checks are required. |
| "Detecting drift means auto-rollback immediately." | Many changes are valid; verify against the source of truth and assess impact. |

## 16. Official Documentation References

- [Cloud Asset Inventory overview](https://docs.cloud.google.com/asset-inventory/docs/asset-inventory-overview)
- [Supported asset types](https://docs.cloud.google.com/asset-inventory/docs/asset-types)
- [Roles and permissions](https://docs.cloud.google.com/asset-inventory/docs/roles-permissions)
- [Search resources — gcloud reference](https://docs.cloud.google.com/sdk/gcloud/reference/asset/search-all-resources)
- [Search IAM allow policies — gcloud reference](https://docs.cloud.google.com/sdk/gcloud/reference/asset/search-all-iam-policies)
- [List assets — gcloud reference](https://docs.cloud.google.com/sdk/gcloud/reference/asset/list)
- [Get asset histories](https://docs.cloud.google.com/asset-inventory/docs/get-asset-history)
- [Export asset metadata to BigQuery](https://docs.cloud.google.com/asset-inventory/docs/export-bigquery)
- [Monitor asset changes with Pub/Sub](https://docs.cloud.google.com/asset-inventory/docs/monitor-asset-changes)
- [Query assets with SQL](https://docs.cloud.google.com/asset-inventory/docs/query-assets-with-sql)

Features, asset types, history windows, permissions, and syntax can change. When designing for production, verify against current documentation and your Google Cloud organization's configuration.

---

**Connection to the CLOUD_PROVIDERS_GCP track:** knowledge of **organizations, folders, projects, IAM, and VPCs** defines the scope to inventory. Lessons on **Compute Engine, GKE, Cloud Run, storage, and databases** provide the resource types to observe. **Cloud Asset Inventory**, combined with **audit logs, IaC, CI/CD, Billing, Monitoring, and Security Command Center**, turns infrastructure governance into a repeatable loop: **collect state → detect deviations → route to the right owner → remediate under control → verify outcomes**.
