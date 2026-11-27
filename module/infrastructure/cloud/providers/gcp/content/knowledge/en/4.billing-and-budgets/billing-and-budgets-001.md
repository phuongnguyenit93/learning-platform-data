# Cloud Billing Account and Project Linking

In Google Cloud, simply creating a **project** does not mean it is ready to use billable services. For deployments of Compute Engine, Google Kubernetes Engine (GKE), Cloud Run, Cloud Storage, databases, and networking components to work properly, administrators must understand who is responsible for payment, which account the project is linked to, and who is permitted to change that link.

This lesson belongs to the **Billing and Budgets** chapter of the **CLOUD_PROVIDERS_GCP** module. It lays the groundwork for cost management, setting budgets and alerts, protecting resources with IAM, and reliable system operations. You will learn how to distinguish a **Cloud Billing account** from a **Google Cloud project**, link and verify billing status, manage permissions, switch billing accounts, and handle common risks.

## 1. What is a Cloud Billing account?

A **Cloud Billing account** is an account that tracks and pays for the usage costs of Google Cloud services across the projects linked to it. It is a billing and cost-management entity—not a server, deployment region, or folder containing application resources.

To understand the model accurately, you must distinguish three components:

| Component | Primary function | Example |
| --- | --- | --- |
| **Google Cloud project** | Contains, identifies, and governs resources; defines the scope for many APIs, IAM policies, quotas, logs, and costs. | A production project running Cloud Run, Cloud SQL, and Cloud Storage. |
| **Cloud Billing account** | Specifies the account responsible for usage costs from linked projects; provides related reports, budgets, and payment configurations. | A company's billing account covering the costs of three projects. |
| **Google payments profile** | Stores payment details such as payer information and payment methods according to the account model. | Business details, address, and payment method attached to the Cloud Billing account. |

A Cloud Billing account covers Google Cloud costs and eligible products that share Cloud Billing. A Google Workspace billing account is a separate system; the two account types should not be confused.

### 1.1. Relationship between projects and Cloud Billing accounts

- **One Cloud Billing account can be linked to multiple projects.** For example, development, testing, and production projects can share a single corporate billing account.
- **At any given time, a project can be linked to at most one Cloud Billing account.** To change the paying entity, you switch the link to another account.
- **A Cloud Billing account does not replace projects or the resource hierarchy.** Organizations, folders, and projects remain the resource governance units; a Billing link is strictly a cost-responsibility relationship.
- **Linking billing does not automatically grant permissions to operate on applications.** Someone allowed to use a Billing account to link a project is not automatically permitted to read databases, modify VMs, or deploy to Cloud Run.

~~~mermaid
flowchart TB
    O["Organization / Folder"] --> P1["Project dev"]
    O --> P2["Project staging"]
    O --> P3["Project production"]
    B["Cloud Billing account<br/>BILLING-TEAM"] -. "Pays costs" .-> P1
    B -. "Pays costs" .-> P2
    B -. "Pays costs" .-> P3
    P1 --> R1["Dev resources"]
    P2 --> R2["Staging resources"]
    P3 --> R3["Production resources"]
~~~

The diagram illustrates the billing relationship for three projects; it does not mean that resources inside those projects share the same IAM, VPC, or region. Project structure and access permissions still need to be designed separately.

### 1.2. When is billing enabled?

A project is considered **billing enabled** when **both conditions** are met:

1. The project is linked to a Cloud Billing account.
2. That Cloud Billing account is **active and in good standing** (not closed or suspended).

Simply having a Billing account ID in the configuration is not enough to conclude that the project can use services normally. If the account is closed or suspended, the project may be affected just as if billing were disabled. Under current Google Cloud guidelines, using Google Cloud services in a project requires linking to an active Billing account, even when only using services with a free usage tier.

**Distinguishing the states:**

| State | Meaning | Implications to note |
| --- | --- | --- |
| Project not linked to a Billing account | There is no paying account for the project. | Not eligible to run services that require billing. |
| Project linked to an active account | Both the link and the account state are valid. | Billing is enabled; usage costs may accrue depending on products and consumption. |
| Project linked to a closed/suspended account | A link exists, but the account is not in an active, valid state. | Services may be stopped and resource access affected. |
| Project switched to another active account | The paying entity for the project is updated. | Usage accrued after switching the link is recorded to the new account, according to usage reporting. |

A service having zero usage cost up to a certain tier does not mean you can skip setting up a Cloud Billing account. Conversely, **enabling billing does not mean you are immediately charged a fixed fee**: actual charges depend on products, configurations, usage levels, and pricing policies.

## 2. How are Cloud Billing accounts created and managed?

Before linking a project, the team needs an appropriate Cloud Billing account for the paying unit. The account has its own **Billing account ID**, which is distinct from the **Project ID** and **Project number**. The display name can be descriptive, but when performing technical operations you must verify the exact ID to avoid linking the wrong account.

Typically, the person responsible for billing creates the account via **Google Cloud Console → Billing**, selecting the appropriate billing configuration and payments profile. The account can follow the **self-serve** model (automatic payment via the payment method stored on the payments profile) or **invoiced** billing (periodic invoicing if approved by Google). Not all organizations have the same billing options; eligibility depends on country, legal entity, and commercial agreements.

Details to determine early:

1. **Paying entity:** the legal entity, group, or budget unit responsible for the account.
2. **Payment method and profile:** payment method, invoice details, country, and applicable currency.
3. **Billing administrators:** who has permission to manage payment details, grant access, and view cost reports.
4. **Project linking conventions:** which projects are allowed to use this account, and who approves new project creation or account changes.
5. **Budgets and alerts:** how to monitor consumption early, especially for production projects, testing, and resource-intensive workloads.

Do not assume that attributes such as billing country, currency, or account type can always be changed arbitrarily after creation. When major commercial details need adjustment, consult current Cloud Billing documentation and your organization's finance procedures.

### 2.1. One or multiple Billing accounts for an enterprise?

**One billing account for multiple projects** enables centralized billing management. This is appropriate when the same unit pays for dev, staging, and production and wants to separate costs using project filters or labels.

**Multiple billing accounts** may be appropriate when legal entities, invoice-receiving units, or financial workflows must be kept separate. However, creating more accounts means managing additional access controls, reports, budgets, and project migration procedures. The decision should be based on actual financial and governance requirements.

You do not need to create a separate Billing account for each project just to see which project costs the most: Cloud Billing can view and allocate costs by project, service, and supported dimensions.

## 3. IAM permissions for linking projects

Changing a Billing link is an operation that affects financial responsibility and system operability. The person performing it needs permissions on **both sides**: the project to be linked and the target Cloud Billing account. Simply being a Project Editor or having permission to view Billing is not necessarily enough.

| IAM role | Common assignment scope | Related capabilities |
| --- | --- | --- |
| **Billing Account Administrator** — roles/billing.admin | Billing account or appropriate organization scope | Administers the Billing account and related permissions; a broad, privileged role. |
| **Billing Account User** — roles/billing.user | Billing account | Allows using the Billing account to link projects when paired with the required project-side permissions. |
| **Billing Account Viewer** — roles/billing.viewer | Billing account | Views Billing account details and links within permitted scope. |
| **Project Billing Manager** — roles/billing.projectManager | Project or supported parent scope | Manages a project's billing link without granting resource deployment permissions. |
| **Project Browser / Service Usage Viewer** | Project or appropriate parent scope | Provides supplemental read/lookup permissions that UI and operational workflows may require. |

When enabling billing for an existing project, one role combination recommended in Google Cloud documentation is:

- **On the project:** Project Billing Manager, Project Browser, and Service Usage Viewer; **or** Project Owner.
- **On the target Billing account:** Billing Account User and Billing Account Viewer; **or** Billing Account Administrator.

Roles can be inherited from an organization or folder depending on how IAM is assigned. Effective permissions and additional constraints such as Organization Policies, conditional role restrictions, re-authentication, or link locks must still be verified. Avoid granting Project Owner or Billing Account Administrator to someone who only needs to link a project: narrower roles make responsibility and auditing easier to control.

~~~mermaid
flowchart LR
    U["Operator"] --> P["Link management permission<br/>on the project"]
    U --> B["Permission to use<br/>target Billing account"]
    P --> L{"Sufficient permissions and<br/>policy compliant?"}
    B --> L
    L -->|Yes| OK["Linking permitted"]
    L -->|No| NO["Check IAM / policy"]
~~~

**Example separation of duties:** the platform team can manage projects and deploy services, the finance team can view invoices, and an operations group is granted Billing Account User along with Project Billing Manager to link approved projects to the designated account. This avoids granting account-wide admin permissions to every developer.

## 4. Linking a project to a Cloud Billing account

### 4.1. Procedure in Google Cloud Console

Menu labels in the UI may change, but the common sequence is:

1. Sign in to Google Cloud Console with an account that has appropriate permissions and select the **correct project** from the project list.
2. Open **Billing**. If not yet linked, the UI may indicate that the project has no Billing account and offer the **Link a billing account** option.
3. Select the **active Billing account** approved for the project; verify both the display name and ID to avoid selecting another team's account.
4. Confirm the link action. If the UI prompts for re-authentication for this sensitive action, follow your organization's policy.
5. Check the project's Billing page or the Billing account's **Account management / My projects** section to confirm the project is now linked properly.

If starting from the Billing account page, authorized users can inspect the **Projects linked to this billing account** list and verify whether the project appears in the right list.

### 4.2. Checking with gcloud CLI

The following commands inspect status **without creating new resources**. You need gcloud CLI installed and authenticated as an identity with the corresponding read permissions.

~~~bash
# List Billing accounts visible to the current identity
gcloud billing accounts list

# View Billing information currently attached to a project
gcloud billing projects describe PROJECT_ID
~~~

Example output of the describe command might look like:

~~~yaml
billingAccountName: billingAccounts/01ABCD-02EFGH-03IJKL
billingEnabled: true
name: projects/shop-prod/billingInfo
projectId: shop-prod
~~~

Explanation:

- **billingAccountName:** The Billing account linked to the project.
- **billingEnabled: true:** Indicates that billing is enabled based on the current state of the project and linked account.
- **projectId:** The Project ID, not the Project number or display name.

The sample above only illustrates output structure; it is not real data. When an application encounters Billing-related errors, verify both the linked account **and the active status of the Billing account**.

To link or switch to a new account, the standard command is:

~~~bash
# Replace PROJECT_ID and ACCOUNT_ID with actual approved values
gcloud billing projects link PROJECT_ID \
  --billing-account=ACCOUNT_ID
~~~

**The link command is a write operation with billing impact.** Run it only after confirming the project, Billing account, IAM permissions, organization policies, and paying entity. In the example, ACCOUNT_ID is the Billing account ID, not the Project ID.

### 4.3. Verifying results after the operation

After linking, verify from both directions:

~~~bash
# Check which Billing account a project belongs to
gcloud billing projects describe PROJECT_ID

# List projects attached to a Billing account
gcloud billing projects list --billing-account=ACCOUNT_ID
~~~

Verify that the expected project appears under the right account and that **billingEnabled** is **true**. If the project is accessible but does not appear in the current user's list, the cause may be missing view permissions, a different signed-in identity, or an access-restricted list; do not jump to the conclusion that the project was deleted.

## 5. Switching a project to another Billing account

There are many valid reasons to change the link: another department taking over operations, corporate legal entity restructuring, allocating billing to a client, or replacing an old Billing account. **Changing a project's Billing account does not migrate application resources to another project, region, or organization.** The Project ID and the project's resources remain intact during a normal billing link change.

For example, the **shop-prod** project is linked to **BILLING-A** and needs to move to **BILLING-B**. Once the link to BILLING-B succeeds, the new account is charged for usage occurring after the change according to Cloud Billing's reporting mechanism. Usage accrued prior to the switch may still be reported and billed to the old account; cost data does not necessarily appear immediately.

~~~mermaid
flowchart LR
    BA["BILLING-A<br/>old account"] -. "Link before switch" .-> P["Project shop-prod"]
    P --> R["Compute / Network / Database"]
    BB["BILLING-B<br/>new account"] -->|"Link after switch"| P
~~~

Before switching, check:

1. **Target account is active:** verify payment status and ability to pay, avoiding switching to a closed or suspended account.
2. **Permissions on all involved sides:** the operator changing the link needs permissions on the project as well as both the old and new Billing accounts per current documentation.
3. **Organizational constraints:** check whether an Organization Policy restricts allowed Billing accounts or whether a **Billing link lock** prevents switching.
4. **Related commitments and products:** review committed-use discounts (CUDs), contracts, credits, budgets, notifications, and how costs will be calculated after the switch.
5. **Financial reporting:** agree on the cutover timestamp, reconciliation across both accounts, and responsibility for delayed charges.
6. **Post-switch visibility:** verify budgets, alerts, cost exports, and administrator permissions on the new account.

With gcloud CLI, **use the link command directly to the new account** once approved; there is no need to unlink first:

~~~bash
gcloud billing projects link shop-prod \
  --billing-account=NEW_ACCOUNT_ID

gcloud billing projects describe shop-prod
~~~

In the example, **NEW_ACCOUNT_ID** is a placeholder for the actual target account ID. The first command changes billing responsibility; the second verifies the result. Unlinking and then re-linking creates a window where billing is disabled on the project, risking production service outages.

### 5.1. How do permissions when switching differ from initial linking?

When a project has never been linked to any Billing account, the main action is creating a link to the target account. When it is already linked to an old account, switching requires the ability to both remove the old link and establish the new one. Google Cloud enforces specific IAM requirements on the project, the current account, and the target account; certain supplemental read permissions are also required for the UI to function properly.

If you can see the new account but cannot switch the link, check permissions on the **current account** and the project rather than only requesting higher permissions on the new account. If the link is locked, an authorized administrator must handle the lock according to governance procedures first.

## 6. Disabling Billing is different from stopping resources

**Unlink** means detaching a project from its active Cloud Billing account, resulting in **billing disabled**. This operation can stop running Google Cloud services, impact users, and render some resources or data partially unrecoverable. Google Cloud also places restrictions on disabling Billing when a project has active or pending usage commitments.

~~~bash
# High-impact illustrative command: DO NOT use for experimentation
gcloud billing projects unlink PROJECT_ID
~~~

The command above **should not be used as a routine way to pause costs**. Usage incurred before disabling Billing must still be paid; some charges may appear late in reports. Re-enabling Billing does not guarantee that all services will automatically restart immediately, and some resources may already have been deleted.

| Goal | More appropriate action | Why |
| --- | --- | --- |
| Monitor risk of cost overruns | Create budgets, alerts, and analyze costs by project and service. | Provides signals for early intervention without arbitrary disruption. |
| Reduce testing/lab costs | Stop or delete unneeded resources following each service's documentation, and check for resources that still incur charges. | Targets the specific components generating costs. |
| Move a project to another paying unit | Use **link** directly to an active target Billing account. | Avoids a billing gap caused by unlinking and re-linking. |
| Decommission all services and shut down a project | Plan backups, stop services, reclaim resources, and handle Billing by procedure. | Reduces the risk of data loss and lingering charges. |

Before any operation to disable Billing, understand the workload state, data ownership, and financial commitments. Disabling Billing does not immediately erase payment obligations for prior usage.

## 7. Billing links form the foundation for budgets and cost reporting

When multiple projects share a single Billing account, administrators can analyze consumption by **project**, **service**, **SKU**, time, and other product-supported dimensions. This lets you break down costs across development teams, testing environments, and production even under one billing account.

### 7.1. Projects are a key cost-allocation boundary

Suppose a company has three projects:

| Illustrative Project ID | Role | Linked Billing account | Monitoring approach |
| --- | --- | --- | --- |
| store-dev | Development environment | BILLING-COMPANY | Budget filtered to the dev project; monitor experimental resources. |
| store-staging | Release testing | BILLING-COMPANY | Separate budget by project; watch load-test runs. |
| store-prod | Production environment | BILLING-COMPANY | Budget, multi-threshold alerts, track costs by service and upward trends. |

All three projects share one Billing account but can each have budgets with corresponding filters. If more granular cost allocation within a project is needed, consider labels/tags, how they are recorded in Billing reports, and resource naming standards. Do not assume every SKU supports label-based allocation or the same level of granularity.

### 7.2. Budgets and alerts are not hard spending caps

Cloud Billing provides **Budgets & alerts** to track actual or forecasted spend within a configured scope. For example, creating an illustrative budget of **5,000,000 VND/month** for the dev project, with alerts at 50%, 90%, and 100% of the budget.

| Threshold | Operational signal |
| --- | --- |
| 50% | Check growth against forecast and inspect experimental resources. |
| 90% | Identify anomalously rising services, consult the project owner, and consider scaling down non-essential resources. |
| 100% | Trigger the team's budget-overrun response procedure; take controlled action. |

**Standard budgets send alerts; they do not automatically impose a spending cap or automatically stop all resources when thresholds are reached.** Cost recording and alert delivery may lag behind actual usage. Therefore, you should not claim that a 5 million budget guarantees the bill cannot exceed 5 million.

If you design a system that reacts automatically to alerts, strictly control permissions, verify scope, and test thoroughly to avoid disrupting critical services. Cost management also requires quotas, resource policies, scheduled shutdowns for test environments, database reviews, and anomaly monitoring.

### 7.3. Billing reports and data export

In Cloud Console, **Billing Reports** let you inspect costs over time, by project, or by service. For detailed reconciliation and long-term analysis, you can configure **Cloud Billing export to BigQuery** if aligned with permissions and data residency requirements.

When configuring export, pay attention to:

- **BigQuery dataset location** and applicable data residency policies.
- **IAM permissions** to configure Billing export, access the dataset, and view cost data.
- **Data ingestion latency:** usage, adjustments, and cost data can arrive with a delay; do not equate an immediate report with the final period invoice.
- **Cost of the analytics system:** storing data and running BigQuery queries can incur charges.
- **Allocation model:** discounts, credits, taxes, support fees, adjustments, and project/SKU granularity must be properly understood before concluding actual net costs.

For example, when a project switches Billing accounts mid-month, finance personnel must aggregate data from **both the old and new accounts** to reconcile the full period. You cannot infer the entire month's cost from reports of only the new account.

## 8. Common causes when Billing cannot be linked

| Symptom | Possibilities to check | Verification and remediation |
| --- | --- | --- |
| Expected Billing account is not visible in the list | Account lacks view/use permissions; signed in with wrong identity; account is in another scope. | Check identity, IAM on the Billing account, and the ID provided by finance. |
| Console reports insufficient permissions to link project | Missing permissions on the project or target Billing account. | Verify Project Billing Manager, required read roles, and Billing Account User/Viewer. |
| Cannot switch from old account to new account | Missing permissions on old account, link is locked, or organization policy restricts it. | Check permissions on both sides, link locks, Organization Policy, and approval workflows. |
| Project has a Billing account ID but still has billing errors | Account is closed, suspended, or not in a valid active state. | Check the billingEnabled field and account status via Console/verification docs. |
| Project services stopped after unlink | Billing was disabled. | Confirm data status, link to an active account; follow each service's recovery runbook. |
| Budget reached 100% but resources keep consuming | Budget alerts are not a hard-stop mechanism. | Analyze reports, inspect resources, and apply appropriate cost-control procedures. |
| Charges still appear on the old account after switching | Pre-switch usage was recorded with a delay. | Reconcile timestamps, transaction details, reports, and adjustments across both accounts. |

When troubleshooting, do not resolve issues by granting Administrator roles to everyone or unlinking an active project. First determine accurately whether the root cause is missing read permissions, missing link permissions, an invalid account state, or a policy constraint.

## 9. Deployment scenario: separating environments with centralized billing

A team deploys an e-commerce service on Google Cloud: Cloud Run serves APIs, Cloud SQL stores orders, Cloud Storage holds product images, and some workloads run on Compute Engine/GKE. The team creates three projects—**commerce-dev**, **commerce-test**, and **commerce-prod**—to isolate IAM, APIs, quotas, and resource lifecycles.

The finance team specifies that a single legal entity pays for all three environments. The team can use one shared Cloud Billing account and follow these steps:

1. Finance creates/manages the Billing account, completes payment details, and approves the list of projects permitted to link.
2. The platform team creates the projects under the organization/folder hierarchy and assigns proper IAM roles. Link managers are granted permission to use the Billing account along with Billing management permissions on the required projects.
3. After linking Billing, the team verifies that each project has **billingEnabled: true**, the right Billing account ID, and that the account remains active.
4. Engineering deploys Cloud Run, Cloud SQL, Cloud Storage, or GKE within each project. They still must govern IAM, VPC, data location, security, and reliability; Billing links do not replace those architectural responsibilities.
5. FinOps/finance creates per-project budgets, sets up alerts, and uses Reports or exports to monitor costs by environment, service, and time.
6. Before scaling up or running load tests, the team checks quotas, projected costs, infrastructure limits, and the owner accountable if costs exceed forecasts.

After some time, the production product is transferred to a subsidiary with its own Billing account. Administrators verify legal conditions, permissions on both accounts, link locks, CUDs, and reconciliation readiness, then **link commerce-prod directly to the new Billing account**. This does not require automatically migrating Cloud SQL or Cloud Run to another project. However, budgets and cost-viewing permissions for the receiving party must be prepared in advance.

## 10. Non-resource-provisioning lab exercise

Suppose you are granted read permissions in a Google Cloud organization that already has projects. Complete the exercise in order:

**Step 1 — Identification:** Separately record the Project ID, Project number (if needed), Billing account ID, and paying unit name. Explain why these three types of identifiers must not be used interchangeably.

**Step 2 — Inspect status:** Use the Console or two read-only commands:

~~~bash
gcloud billing accounts list
gcloud billing projects describe PROJECT_ID
~~~

Determine which account the project is linked to, whether **billingEnabled** is true or false, and what additional evidence is needed to confirm the account is active.

**Step 3 — Review permission model:** Assume a developer has permission to deploy Cloud Run but cannot see the account designated by finance. Identify the permission groups to check on the **project** and **Billing account**; propose a least-privilege assignment without granting unnecessary admin roles.

**Step 4 — Draft an account-switch plan (on paper):** The company requests moving the production project to a new account. Prepare a checklist covering both account IDs, active status, IAM roles, link locks, paying organization, cutover time, CUDs, budgets, and report reconciliation. Do not run link/unlink commands without operational approval.

**Step 5 — Budget analysis:** The three projects (dev, test, prod) have different illustrative budgets. Propose alert thresholds and on-call actions when dev experiences an anomalous consumption spike. Explain why reaching a 100% alert does not mean charges stop automatically.

### Self-check questions

1. Why might a project with a Billing account ID still not be in the billing enabled state?
2. How many projects can one Cloud Billing account pay for? Can a project use two Billing accounts simultaneously?
3. Does someone with permission to view invoices automatically have permission to modify VMs, Cloud SQL, or Cloud Run in a project?
4. When switching the paying account, do all resources have to be moved to a new project? How is usage accrued before the switch handled?
5. Why should you not unlink Billing to pause a production environment, and why are budget alerts not a hard spending limit?

**Suggested answers:** (1) The account may be closed or suspended; both a valid link and an active account are required. (2) One account can be linked to multiple projects; each project can have at most one account at a time. (3) No, Billing permissions and resource permissions are separate. (4) No; pre-switch costs still belong to the old account based on usage time and billing ingestion. (5) Unlinking can stop services and impact data; budgets only monitor and alert unless separate custom response mechanisms are engineered.

## Google Cloud documentation to reference during operations

- **Manage your Cloud Billing account:** https://cloud.google.com/billing/docs/how-to/manage-billing-account — Billing account structure, payment methods, and account management.
- **Enable, disable, or change billing for a project:** https://cloud.google.com/billing/docs/how-to/modify-project — IAM conditions, linking, switching, and disabling Billing.
- **Verify the billing status of your projects:** https://cloud.google.com/billing/docs/how-to/verify-billing-enabled — checking whether a project has billing enabled.
- **Cloud Billing access control:** https://cloud.google.com/billing/docs/how-to/billing-access — IAM roles for Billing accounts and projects.
- **Create and manage budgets:** https://cloud.google.com/billing/docs/how-to/budgets — budget scope, thresholds, and alerts.
- **Export Cloud Billing data to BigQuery:** https://cloud.google.com/billing/docs/how-to/export-data-bigquery — exporting data for cost analysis.
- **gcloud billing projects:** https://cloud.google.com/sdk/gcloud/reference/billing/projects — syntax for describe, list, link, and unlink commands.

IAM permissions, service behavior when Billing is disabled, payment terms, and supported features may change. Before applying changes to a real project, consult official documentation alongside your organization's governance and finance policies.
