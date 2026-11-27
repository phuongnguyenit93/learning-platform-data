# Managing Credits, Lab Resources, and Accrued Costs on Google Cloud

While learning Google Cloud, you may spin up Compute Engine VMs to test SSH, deploy apps on Cloud Run, create GKE clusters, provision Cloud SQL databases, or store data in Cloud Storage. Every step gives hands-on practice but can also incur **usage charges**. Promotional credits or free usage tiers can lower what you owe, yet they do not mean every resource is free or that experimentation is always cost-safe.

This lesson belongs to the **Billing and Budgets** chapter in the `CLOUD_PROVIDERS_GCP` module. When studying project organization, IAM, VPC, Compute Engine, GKE, Cloud Run, storage, databases, and release automation, you must simultaneously know how to scope experiments, monitor reliability, and understand associated costs. The practical goal is to help learners **track credits, spot lingering billable resources, and wrap up labs verifiably**.

## Learning objectives

After this lesson, you will be able to:

1. Distinguish between **credits**, **Free Tier**, **budgets**, **quotas**, and **actual charges**.
2. Identify the relationship between projects, Cloud Billing accounts, and eligible credits.
3. Read Cloud Billing Reports to analyze costs before and after credits by project, service, and SKU.
4. Configure budgets, alert thresholds, and response workflows when costs exceed projections.
5. Identify ongoing costs from VMs, disks, IPs, GKE, Cloud SQL, storage, logs, and data transfer.
6. Plan labs, clean up resources in the proper order, and verify charges after cleanup.
7. Apply cost-management discipline to development, CI/CD, and production environments.

## 1. Four frequently confused concepts

| Concept | Meaning | What you should not infer |
| --- | --- | --- |
| **Credits** | Promotional or partner-granted credits under specific terms that can offset eligible charges. | Not cash; do not automatically apply to every service or every billing account. |
| **Free Tier** | Free usage allowance for certain products under published limits and conditions. | Does not mean all usage of a service is free; exceeding limits can incur charges. |
| **Budget** | A tool that tracks spend and sends notifications when actual or forecasted thresholds are hit. | **Not a hard spending cap** and does not stop resources by default. |
| **Quota/limit** | Limits on resources or API/service usage, primarily to protect system capacity and operations. | Does not guarantee total spend stays within budget; other resources can keep billing. |

A single project can simultaneously receive Free Tier allowances, draw down credits, and exceed its configured budget. Therefore, seeing a **current payable amount of 0** does not mean **no billable usage is occurring**.

### 1.1. Usage cost and payable balance are two different views

Illustrative example—all amounts below are **hypothetical**, not Google Cloud pricing quotes:

| Period line item | Hypothetical amount |
| --- | ---: |
| Eligible usage cost calculated before credits | 32 USD |
| Promotional credits applied to eligible portion | -25 USD |
| Usage cost outside credit eligibility | 4 USD |
| **Remaining balance before taxes/other adjustments** | **11 USD** |

In this example, credits do not make consumption free: total usage cost is 36 USD, credits offset 25 USD, and 11 USD remains payable. Actual invoices may also include taxes, adjustments, discounts, posting timing differences, and specific credit-application rules.

**Effective tracking habit:** monitor both **gross usage cost** (usage cost before credits) and **net cost** (cost after applied offsets). Temporarily low net cost can mask a resource-hungry workload.

## 2. Credits on Google Cloud: types, scope, and lifecycle

Credits can come from free trials, educational programs, events, promotions, or partner offers. Program terms vary, so **never hardcode credit amounts, validity days, or eligible service lists** into operational runbooks.

When receiving credits, read and record the following details:

| Information to verify | Why it matters |
| --- | --- |
| **Issuing program** | Determines terms, usage limits, and associated support. |
| **Linked Billing account** | Credits may be tied to a specific billing account or scope defined by the program. |
| **Eligible services and SKUs** | Certain usage may not be covered even while the project holds active credits. |
| **Expiration date** | Unused credit balances expire once the program period ends. |
| **Usage limits/restrictions** | Credit types can carry restrictions on purpose, services, transfers, or geographic scope. |
| **Behavior upon credit exhaustion** | Apps may continue billing to the paid account; some trial programs follow distinct rules. |
| **How credits appear on reports/invoices** | Helps reconcile gross charges, deductions, and payable amounts. |

### 2.1. Free Trial, promotional credits, and Free Tier

Three common terms:

- **Free Trial** is a time-bound trial program with specific conditions and may include trial credits. Limits and post-trial behavior depend on the program and upgrade status to a paid account.
- **Promotional credits** are credits granted under a specific offer. They may only offset a subset of services or SKUs.
- **Free Tier** is a conditional free usage allowance per product. It is a usage-based allowance mechanism, **not a credit wallet**.

For every program, check the **Cloud Billing → Credits** page, applicable terms, and official documentation before budgeting. Never assume examples or credit balances from another account apply to yours.

### 2.2. At what scope are credits managed?

Relevant governance hierarchy:

~~~mermaid
flowchart TD
    O["Organization"]
    F["Folder: Nonproduction"]
    P1["Project: learning-gcp-dev"]
    P2["Project: learning-gcp-lab"]
    B["Cloud Billing account"]
    C["Program-eligible credits"]
    O --> F
    F --> P1
    F --> P2
    P1 -. "Billing link" .-> B
    P2 -. "Billing link" .-> B
    C -->|"Applied per terms"| B
~~~

Organizations and folders govern permissions and policies; the billing account handles payment. **A project is not an independent credit wallet.** Projects link to a billing account to record charges, while whether credits apply depends on offer rules and the linked billing account.

A project typically links to **one active billing account at a time**. Multiple projects can share one billing account. When changing a billing link, evaluate impacts on cost governance, credits, permissions, and operations; never hop between accounts merely to chase credit offsets.

## 3. Credits do not guarantee zero charges

Consider three states:

1. **Credits remain and usage is eligible:** part or all of eligible charges may be offset.
2. **Credits remain, but ineligible charges occur:** a payable balance can still appear immediately.
3. **Expired, depleted, or program ended:** new usage becomes payable charges according to billing account status and program terms.

Verify these states via credit details and actual billing reports. Never assume that when credits run out, Google Cloud **will automatically stop** all running VMs, databases, or services.

### 3.1. Example of forecasting credit burn

Suppose a team has 60 USD in eligible credits, has spent 18 USD of eligible usage after 6 days, and still has 24 lab days remaining.

If eligible consumption continues at 3 USD/day:

- Modeled remaining credit: `60 - 18 = 42 USD`.
- Projected eligible cost over 24 days: `24 × 3 = 72 USD`.
- Modeled cost exceeding credits: `72 - 42 = 30 USD`.

Additionally, if 5 USD of ineligible charges accrue, total **hypothetical** payable spend could reach 35 USD before taxes or other adjustments. This is an **illustrative math exercise**, not a commitment on how Google Cloud deducts individual items. Actual charges and credit application timing can vary.

Lesson: looking only at today's credit balance without checking **burn rate** and **expiration date** leads to bad forecasts.

## 4. Viewing costs and credits in Cloud Billing

In Google Cloud Console, open **Billing** and select the right billing account. Users need appropriate billing read permissions; permissions to edit project resources do not automatically allow viewing all billing account details.

### 4.1. Useful screens

| Section | What is it for? |
| --- | --- |
| **Billing overview** | View summary status of the billing account. |
| **Credits** | Check active credits, expiration dates, or offer terms surfaced by the UI. |
| **Reports** | Analyze costs over time by project, service, SKU, and filters. |
| **Cost table / Cost breakdown** | Reconcile detailed usage, credits, and adjustments where supported by data period. |
| **Budgets & alerts** | Create budgets, alert thresholds, and configure recipients/notifications. |
| **Billing export** | Export billing data to BigQuery for detailed analysis, if configured. |

Menu labels and visibility may vary with UI updates, account permissions, and billing mode.

### 4.2. How to read a cost report

Follow this sequence:

1. Select the **billing account** and **time range** under analysis.
2. Filter to the **test/lab project**, avoiding accidentally summing production projects.
3. Group by **service** to identify top spend drivers: Compute Engine, GKE, Cloud SQL, Cloud Run, Cloud Storage, etc.
4. Drill down to **SKU** to understand specific consumption types: CPU, RAM, disks, storage, network egress, requests, or companion services.
5. Check how **credits/discounts** are displayed and compare gross vs. post-credit costs. Never subtract or add the same item twice.
6. Check timestamps, update latency, data types, and adjustments before drawing conclusions.

Example: a lab project report shows Compute Engine 8 USD, Cloud SQL 12 USD, Cloud Storage 2 USD, and networking 3 USD. **Total usage cost is 25 USD**. If the report shows 15 USD of eligible credits applied, 10 USD remains in this example before other invoice items.

### 4.3. Why can costs appear with a delay?

Billing data may **not update in real time**. Latency exists between resource consumption, appearance in Reports/Exports, and aggregation onto invoices.

Therefore:

- Do not treat a dashboard momentarily showing `0 USD` as proof that a newly created VM is free.
- Do not assume deleting every resource at 17:00 means reports will stop changing at 17:01.
- Re-check after enough time has passed for billing ingestion to settle; reconcile billing periods and invoices per organizational policy.

When near-real-time visibility is required, pair resource-utilization metrics with reported costs, without assuming metrics equal invoice dollar amounts.

## 5. Creating budgets and alerts to limit risk

**Cloud Billing Budgets** monitor spend and send notifications. Budgets can be scoped to an appropriate billing account, project, service, or UI-supported filters. Thresholds can evaluate actual spend and, in certain configurations, forecasted spend.

### 5.1. Creating a lab budget

Suppose a team plans to experiment with Cloud Run and Cloud Storage for 2 weeks with a **20 USD** monitoring target. This is an illustrative amount.

1. Open **Billing → Budgets & alerts**.
2. Click **Create budget** and enter a name such as `lab-commerce-nov`.
3. Select the billing account and **filter to the exact lab project**; add service filters if needed.
4. Choose the time range or budget period matching the lab.
5. Set the target budget amount to `20 USD`.
6. Configure thresholds such as **25%, 50%, 80%, 100%** of the budget.
7. Configure organization-supported email or notification channels, and assign an owner to respond.
8. Save, double-check filters, and confirm alert delivery settings.

| Threshold on 20 USD budget | Equivalent amount | Suggested action |
| --- | ---: | --- |
| 25% | 5 USD | Check running services and compare against the lab plan. |
| 50% | 10 USD | Audit active VMs/SQL/GKE and leftover storage resources. |
| 80% | 16 USD | Stop creating new resources; decide whether to proceed or clean up the lab. |
| 100% | 20 USD | Trigger overspend response workflow; notify owner and approvers. |

**Important note:** 100% of budget **is not a spending kill switch**. Spend can keep rising before, during, or after notifications reach recipients. Alerts can also rely on delayed billing data.

### 5.2. Can Pub/Sub and automation be used?

Cloud Billing can emit budget notifications via **Pub/Sub**, depending on configuration. An automated system can consume those notifications to alert teams or trigger workflows.

~~~mermaid
flowchart LR
    A["Services consume resources"] --> B["Cloud Billing records charges"]
    B --> C["Budget evaluates thresholds"]
    C --> D["Email / notification channels"]
    C --> E["Pub/Sub (when configured)"]
    E --> F["Verification and approval workflow"]
    F --> G["Controlled adjustment or resource cleanup"]
~~~

Never build automation that immediately **deletes projects, databases, or disables billing** upon hitting a threshold without classifying environment, owner, and criticality. That can cause outages or data loss. For non-production labs with synthetic data, controlled resource-shutdown workflows can be built, provided they are thoroughly tested with clear guardrails.

### 5.3. When do quotas help control costs?

Resource quotas can prevent spinning up too many VMs, CPUs, or API call rates. Yet a single permitted VM running for many days still accrues charges without hitting quota. Thus quotas are a **complementary guardrail**, not a substitute for budgets, usage monitoring, and cleanup policies.

## 6. Lab resources that commonly keep accruing charges

A common mistake is watching only resources "visibly running on screen." Many components have independent lifecycles and billing mechanics.

| Resource/service | When to pay attention? | Pre-teardown check before ending a lab |
| --- | --- | --- |
| **Compute Engine VM** | CPU/RAM while running; some associated components may still bill when VM is stopped. | Check VM state and attached resources. |
| **Persistent Disk / Hyperdisk** | Provisioned capacity can keep billing while the VM is stopped or if the disk remains after VM deletion. | List boot/data disks and confirm whether any disk still needs retention. |
| **Snapshots / images** | Separately stored backups and custom images can continue accruing charges. | Find snapshots and images created during the lab. |
| **External IP addresses / forwarding rules / load balancers** | IP and network infrastructure charges can accrue depending on type and status. | Inspect reserved addresses, forwarding rules, and load balancers. |
| **Cloud NAT / networking** | Traffic processing, network resources, and data transfer may incur fees. | Inspect NAT configuration, transfers, and egress. |
| **GKE** | Clusters, node pools, node VMs, disks, and networking carry associated charges. | Check clusters, node pools, PV/PVCs, and disks after deleting workloads. |
| **Cloud Run** | Costs depend on requests, allocated CPU/RAM, min-instances settings, connections, and companion services. | Check services/jobs, min instances, revisions, and networking. |
| **Cloud SQL** | Instances, storage, backups, HA, and networking can accrue charges. | Check instances, backups, read replicas, and storage size. |
| **Cloud Storage** | Object data, requests, retrieval, and egress depend on storage class and terms. | Check buckets, objects, object versions, lifecycle rules, and replication. |
| **Artifact Registry** | Container images/artifacts stored across builds/deployments. | Check repositories and artifacts no longer needed. |
| **Cloud Logging / Monitoring** | Certain ingestion volumes, retention periods, or features can incur charges. | Review log sinks, log buckets, metrics, and retention settings per service. |

**Stop does not mean Delete; Delete does not always end every charge.** For instance, stopping a VM stops CPU charges, while persistent disks, snapshots, or reserved IPs remain. Deleting a GKE workload may leave the cluster and node pools intact. Deleting a Cloud Run service does not automatically remove container images, logs, or backend services.

### 6.1. Invisible costs when learning VPC networking

Declaring a VPC network itself does not follow the same billing model as a VM, yet **networking is not automatically free**. Network egress, load balancers, NAT, external IP addresses, and certain connections can incur costs. Account for inter-region/inter-zone traffic and pulls from Cloud Storage or databases when calculating total lab spend.

### 6.2. Pre-flight checklist before trying GKE or Cloud SQL

These two service groups are typically more complex than a stateless app:

- **GKE:** check cluster mode, node pools, node VMs, persistent volumes, disks, load balancers, and companion services.
- **Cloud SQL:** check instance tier, storage, backups, HA, read replicas, and connection setup.
- If the goal is simply learning API calls or basic workflows, consider emulators, sample apps, organization-approved sandboxes, or smaller services with lower estimated cost.

## 7. Designing controlled labs: from pre-creation to teardown

Example: the Commerce team needs to test a Java API on Cloud Run, upload images to Cloud Storage, and possibly test Cloud SQL in a single study session. They choose a dedicated project named `atlas-commerce-lab` (illustrative name), assign a clear owner, and plan to conclude the lab within the day.

### 7.1. Before running

Prepare these details:

| Item | Example |
| --- | --- |
| Owner | Commerce team, designated billing watcher |
| Project | `atlas-commerce-lab` |
| Environment | `lab`; isolated from production projects |
| Start/end window | 09:00–17:00 on lab day |
| Estimated spend | E.g., 10 USD, calculated with current pricing tools |
| Alert budget | E.g., 10 USD with 50%, 80%, 100% thresholds |
| Permitted services | Cloud Run, Cloud Storage; Cloud SQL only if approved |
| Management labels/metadata | `environment=lab`, `team=commerce`, `owner=...` where supported |
| Cleanup plan | Resource owner verifies and cleans up per checklist |

Never copy production secret keys or real customer data into lab projects. Use synthetic data and least-privilege IAM. Confirm the project links to the right billing account, verify credit availability if relying on credits, and note program limits.

### 7.2. While the lab is running

Watch two signal groups:

- **Service consumption:** VM, node, and instance counts, storage bytes, request counts, network egress.
- **Billing:** costs by project/service, applied credits, actual/forecasted budgets, and triggered alerts.

A simple workflow:

~~~mermaid
flowchart TD
    A["Start lab"] --> B["Verify credits, billing, budget, and owner"]
    B --> C["Create resources with labels/naming conventions"]
    C --> D["Monitor usage and alerts"]
    D --> E{"Lab finished or threshold hit?"}
    E -->|No| D
    E -->|Yes| F["Inventory resources and data to keep"]
    F --> G["Clean up deletable resources"]
    G --> H["Check for leftover resources"]
    H --> I["Monitor updated billing reports and close lab"]
~~~

### 7.3. After the lab completes

Keep a short closeout log: project ID, services created, resources deleted, resources retained with justification, end timestamp, estimated cost, and report follow-up schedule. The owner must know which resources will keep incurring charges.

For labs holding data worth keeping, retention vs. deletion decisions must happen before teardown. **Never delete real data solely because a budget alert triggered.**

## 8. Inventorying resources with Google Cloud CLI

The commands below are **read-only** to inspect active resources. Run them after authenticating with Google Cloud CLI and verifying permissions. Replace `PROJECT_ID` with your actual project.

~~~bash
# Verify active project
gcloud config get-value project

# Check project billing link info
gcloud billing projects describe PROJECT_ID

# Compute Engine instances, disks, and IP addresses
gcloud compute instances list --project=PROJECT_ID
gcloud compute disks list --project=PROJECT_ID
gcloud compute addresses list --project=PROJECT_ID

# GKE clusters and Cloud SQL instances
gcloud container clusters list --project=PROJECT_ID
gcloud sql instances list --project=PROJECT_ID

# Cloud Run services and Cloud Storage buckets
gcloud run services list --project=PROJECT_ID
gcloud storage buckets list --project=PROJECT_ID
~~~

Some commands may require enabled APIs, resource-viewing permissions, or location flags depending on setup. If the CLI omits a resource due to missing permissions, **you cannot conclude the resource does not exist**.

The commands above **do not cover every billable resource type**. Also inspect snapshots, images, load balancers, Cloud NAT, Artifact Registry, logs, database backups, and resources from any other tested services. In larger organizations, Cloud Asset Inventory and administrator-approved inventory tools can broaden coverage.

### 8.1. Lab project cleanup checklist

- [ ] Verify project ID and owner; confirm it is not a production project.
- [ ] Record resources/data to preserve and cross-service dependencies.
- [ ] Stop resource-creating pipelines: CI/CD workflows, schedulers, automation, or jobs.
- [ ] Tear down unused workloads (VMs, Cloud Run, GKE, Cloud SQL, etc.) following approved procedures.
- [ ] Check for orphaned disks, snapshots, reserved IPs, load balancers, NAT, buckets, artifacts, and backups.
- [ ] Review which services still bill even with zero active workloads.
- [ ] Re-list resources via CLI/Console after cleanup.
- [ ] Re-check Cloud Billing Reports once billing data settles to catch lingering charges.
- [ ] Document the accountable owner if any resource must remain.

If a lab exists solely for a single course and the entire project can be removed, consider the **project shutdown** procedure in line with permissions and organization policy. However, closing/deleting a project heavily impacts data and services; verify target project ID, dependencies, recoverability, and retention windows beforehand. Shutting down a project also does not erase previously accrued charges from reports immediately.

## 9. Release automation and cost risks

In the Google Cloud module, you learn to deploy apps via CI/CD. Automation speeds up delivery but can also accidentally **provision resources repeatedly**.

Scenarios to guard against:

1. Pipelines creating VMs or databases on every run without post-test teardown.
2. Per-pull-request ephemeral environments not cleaned up when PRs close.
3. Container images built continuously and accumulating in Artifact Registry.
4. Cloud Run services left with high min instances or overly frequent scheduled jobs.
5. Test GKE clusters leaving node pools running after tests finish.
6. Snapshots/backups retained indefinitely due to missing lifecycle policies.
7. Verbose logging, long retention, or unintended cross-region data transfers.

### 9.1. Three layers of control

| Control layer | Examples | Purpose |
| --- | --- | --- |
| **Preventive** | Dedicated lab projects, least-privilege IAM, quotas, CI/CD environment caps, approvals before costly provisioning | Reduce the chance of unintended spend |
| **Detective** | Billing Reports, budgets, actual/forecast alerts, usage metrics, resource inventories | Spot budget overruns early |
| **Corrective** | Pause pipelines, scale down, clean up expired resources, inspect leftover data | Stop the root cause driving costs up |

In production environments, cost-optimization decisions must balance **reliability, performance, availability, and data-retention obligations**. Uncontrolled instance cuts or backup deletions can cause far more damage than the money saved.

## 10. Choosing a tracking tool: Reports, Budgets, or BigQuery export?

The three tools serve different needs:

| Need | Appropriate tool |
| --- | --- |
| Which services did the lab project spend money on yesterday? | **Cloud Billing Reports** grouped by project/service/SKU |
| Receive alerts when this month's spend exceeds plan | **Budgets & alerts** |
| Analyze multiple projects, join cost-center data, or automate recurring reports | **Cloud Billing export to BigQuery** |
| Estimate costs before enabling GKE/SQL or sizing VMs | **Google Cloud Pricing Calculator** and current pricing docs |
| Check which resources still exist after a lab | **Console/CLI**, Cloud Asset Inventory per permissions |

### 10.1. Billing export to BigQuery

If a team needs deep analytics, configure Cloud Billing export to a governed BigQuery dataset. Exported data enables analysis across time, projects, SKUs, locations, labels, and credit fields when present in the chosen export type.

Points to note:

- Exports may only record data from enablement onward or have varying historical backfill windows depending on export type and configuration.
- Exports have latency, and BigQuery incurs storage/query charges.
- Credit data can span multiple rows/types; in SQL aggregations, avoid duplicating costs through careless `UNNEST` joins.
- Access to billing datasets must be governed since they contain organizational spend and operational structure.
- When evaluating final payable amounts, reconcile against invoices and how Google Cloud applies credits, taxes, and adjustments.

Reports/Budgets are sufficient for many small labs. BigQuery export fits better when **repeatable analytics** across multiple projects or governance reporting are required.

## 11. Scenario: credit balance remains, yet charges still increase

A team tests Cloud SQL and GKE in project `atlas-learning-lab`. After a few days, the Credits screen still shows a promotional balance, yet Billing Reports display real charges.

Troubleshoot in order:

1. **Identify the exact billing account** for the project. Do the viewed credits actually belong to the account/terms covering this usage?
2. **Read the credit scope**: are the credits expired, restricted by service/SKU, or subject to unmet conditions?
3. **Filter reports by project, service, and SKU**: do charges come from GKE nodes, Cloud SQL, disks, networking, or elsewhere?
4. **Compare total usage cost against recorded credits**: are there ineligible items or reporting delays?
5. **Inspect live resources**: node pools, disks, backups, reserved IPs, buckets, artifacts.
6. **Take appropriate action**: clean up expired lab resources, scale down, pause automation, or notify the owner.
7. **Verify again after reports settle**: confirm no unexpected consumption continues before closing the incident.

Never assume Cloud Billing miscalculated or try switching billing accounts to tap another account's credits. Verify program terms and data first.

## 12. Self-check exercises

**Q1.** You have 40 USD in credits remaining and set a 10 USD budget. When Reports reach 10 USD, does Google Cloud automatically stop all VMs?

*Suggested answer:* No. Budgets trigger threshold alerts; they do not enforce a hard cap automatically. You need monitoring, response procedures, and proper resource cleanup.

**Q2.** You stop a Compute Engine VM but still see costs in the project. List three possible causes.

*Suggested answer:* Persistent disks, snapshots, external IP addresses or network resources, and related storage/logging services can keep incurring charges. In addition, billing data updates with latency.

**Q3.** Are Free Tier, Free Trial credits, and Budgets the same thing?

*Suggested answer:* No. Free Tier is a product-specific free usage allowance; Free Trial credits are promotional credits under a trial program; Budgets are cost-monitoring and alerting tools.

**Q4.** Shortly after creating a Cloud Run service with image storage and Cloud SQL, cost reports look low. Can you rely on that number to confidently estimate the entire month's bill?

*Suggested answer:* No. Account for consumption rate, runtime duration, min instances, databases, storage, network egress, requests, and billing ingestion latency. Use pricing calculators and monitor actual spend over time.

**Q5.** A production project and a lab project share one billing account. Should you place a budget on the entire account or specifically on the lab project?

*Suggested answer:* You may need **both** for different purposes. An account-wide budget monitors overall spend; a lab-project-filtered budget surfaces experimental costs without being masked by production figures.

**Q6.** A test GKE Deployment was deleted, yet reports still show GKE/Compute Engine charges. What should you check?

*Suggested answer:* The cluster and node pools may still exist; node VMs, persistent disks, IPs, or load balancers can keep billing. Always inventory underlying infrastructure, not just Kubernetes workloads.

**Q7.** A report shows 36 USD usage cost and 25 USD applied eligible credits. With no other adjustments in this example, what is the remaining amount?

*Suggested answer:* 11 USD. However, the real invoice amount still depends on taxes, posting timing, and applicable adjustments.

## 13. Checklist to carry forward into upcoming GCP lessons

- **Use a dedicated lab project** to simplify cost filtering and limit permission boundaries.
- **Check credits on the right billing account**, verifying terms, expiration dates, and eligible services.
- **Estimate before deploying**, especially for VMs, GKE, Cloud SQL, networking, and long-term storage.
- **Create budgets and assign alert recipients**, without treating budgets as absolute cost blockers.
- **Track both gross usage cost and net cost**, not only the net balance after credits.
- **Clean up resources and their dependencies**, checking disks, snapshots, IPs, backups, buckets, images, logs, and automation.
- **Re-check after billing figures settle** before confirming a lab has stopped generating unexpected charges.
- **Balance cost with reliability and data safety** when optimizing real-world environments.

As you progress into Compute Engine, GKE, Cloud Run, databases, or release automation, make the question **"Who will clean up this resource, when, and how will we confirm charges have stopped?"** a mandatory part of every deployment plan.

## Official reference documentation

- [Cloud Billing documentation](https://cloud.google.com/billing/docs)
- [View and manage credits — Google Cloud](https://cloud.google.com/billing/docs/how-to/credits)
- [Cloud Billing Reports](https://cloud.google.com/billing/docs/how-to/reports)
- [Create, edit, or delete budgets and budget alerts](https://cloud.google.com/billing/docs/how-to/budgets)
- [Programmatic notifications for budgets](https://cloud.google.com/billing/docs/how-to/notify)
- [Export Cloud Billing data to BigQuery](https://cloud.google.com/billing/docs/how-to/export-data-bigquery)
- [Google Cloud Free Program](https://cloud.google.com/free/docs/free-cloud-features)
- [Google Cloud Pricing Calculator](https://cloud.google.com/products/calculator)
