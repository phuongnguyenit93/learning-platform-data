# Setting Up Budgets and Cost Alerts

## 1. Why Are Budgets Needed When Operating Azure Applications?

On Azure, applications can incur continuous costs from virtual machines, App Service, databases, storage, network traffic, log ingestion, and managed services. Seemingly minor changes such as increasing replica counts, selecting a higher SKU, keeping snapshots too long, or extending log retention can push total spend over projections. If engineering waits for the end-of-month invoice, problems are usually discovered too late.

In the **Cost Management** chapter of the `CLOUD_PROVIDERS_AZURE` module, this lesson guides you through using **Azure Cost Management budgets** to set spending targets and configure alerts when actual or forecasted costs cross thresholds. The material connects directly to organizing subscriptions, resource groups, Microsoft Entra ID/RBAC, networking, compute, storage, databases, and monitoring for an Azure application.

**A budget is a tracking and alerting threshold; by default it does not block resource usage, stop VMs, or impose a hard cap on the invoice.** Upon receiving a notification, operations teams must still investigate the root cause and take deliberate action following an approved workflow.

After this lesson, you will be able to:

1. Distinguish budgets, actual costs, forecasted costs, cost analysis, anomalies, and invoices.
2. Select the right budget **scope**, period, amount, filters, and responsible owners.
3. Create a budget in the Azure Portal and understand **Actual** and **Forecasted** alert configurations.
4. Deploy a sample budget with Bicep following Infrastructure as Code (IaC) practices.
5. Build a runbook for handling 60%, 80%, or 100% forecasted thresholds with proper access control, security, and production safeguards.
6. Verify notifications, evaluate data discrepancies, and track cost control effectiveness over time.

## 2. Foundational Concepts

### 2.1. Azure Cost Management and Budgets

**Azure Cost Management** lets you view, analyze, allocate, and manage costs at supported scopes. Two distinct workflows are involved:

- **Cost analysis:** Answers "where did costs occur, when, and which services or teams are generating them?"
- **Budgets:** Answers "is spend in this scope approaching or projected to exceed the target, and who needs to be notified?"

A budget typically includes these properties:

| Property | Role | Example |
| --- | --- | --- |
| **Scope** | Cost boundary being tracked | Resource group `rg-orders-dev` |
| **Amount** | Budget target per cycle | 1,200 USD/month |
| **Time grain** | Budget evaluation cycle | Monthly |
| **Time period** | Effective start and end dates | From November 2026 to October 2027 |
| **Filters** | Narrows charges included in the budget, where supported | Service, resource group, tag |
| **Notifications** | Rules triggering alerts at thresholds | Actual 80%; Forecasted 100% |
| **Recipients** | Individuals or groups receiving alerts | Email and supported Action Groups |

A monthly budget can span multiple months: **the amount resets every month**, while the time period defines which months the budget remains active. You do not need to recreate a new budget every month if the configuration still fits.

### 2.2. Actual Cost, Forecasted Cost, and Invoices

**Actual cost** is the spend recorded by Cost Management within the scope and period based on currently available data. **Forecasted cost** is an estimate of spend for the remainder of the cycle using Azure's data and forecasting model, where supported for the given scope.

Example on day 20 of a month:

~~~text
Monthly budget:                1,200 USD
Recorded actual cost:            710 USD
Full-month forecasted cost:    1,340 USD

Actual / budget ratio:         710 / 1,200 = 59.2%
Forecast / budget ratio:     1,340 / 1,200 = 111.7%
~~~

In this case, current spend has not crossed **Actual 80%**, yet the forecast has already exceeded **Forecasted 100%**. Forecast alerts enable application teams to react earlier than waiting for the final bill to overshoot.

**Actual and Forecasted are not final invoice figures.** Cost data has ingestion latency and may be subject to adjustments, tax rules, credits, spend commitments, discounts, and differing display conventions depending on account/agreement. Forecasts also carry margin of error; unusual spend occurring after the projection timestamp can shift outcomes substantially.

### 2.3. Actual Cost vs. Amortized Cost

When analyzing costs, know which accounting view the dashboard displays:

- **Actual cost:** Reflects charges recorded at billing/posting time according to the account's mechanism.
- **Amortized cost:** Distributes eligible upfront purchases or commitments (such as Reservations) across usage time to reflect resource consumption across periods.

Datasets and budget evaluation rules depend on account type, scope, and supported Cost Management options. When reconciling a budget against Cost Analysis or an invoice, **verify identical scope, time range, cost type, currency, and filters**; never assume a bug simply because two reports use different recognition views.

### 2.4. How Budget Alerts Differ from Anomaly Detection

| Mechanism | Question Answered | Example |
| --- | --- | --- |
| **Budget alert** | Has cost reached a percentage of the defined target? | Actual hit 80% of 1,200 USD |
| **Forecasted budget alert** | Is full-period cost projected to exceed the target? | Monthly forecast is 1,340 USD |
| **Cost anomaly detection** | Is the spending pattern abnormal compared to historical trends? | Log ingestion jumped suddenly after deploy |
| **Azure Monitor metric alert** | Did a technical resource metric cross a threshold? | High CPU, increased autoscale events |
| **Invoice/billing review** | What is the final payable or reconcilable amount? | Reviewing invoice cycle and adjustments |

Budgets work best when paired with **cost owners and post-alert actions**. Anomaly detection, where available at the scope/account, complements budgets by catching unexpected pattern shifts; it does not replace committed budget thresholds.

## 3. Choosing the Scope: Tracking Who, Which Services, and Which Budget?

A budget is meaningful when its scope aligns with an individual's or team's accountability. On Azure, costs can be viewed at different scopes depending on account type and permissions: subscription, resource group, management group, or supported billing scopes.

### 3.1. Common Scopes

| Scope | Best Fit When | Things to Keep in Mind |
| --- | --- | --- |
| **Subscription** | Tracking an entire environment or business unit with its own subscription | Covers multiple resource groups; avoid double counting when rolling up reports |
| **Resource group** | An application/environment resides primarily in one resource group | Shared dependencies in other resource groups may not appear |
| **Management group** | An organization monitors multiple subscriptions under one governance tree | Budget creation/viewing and charge types depend on scope permissions and support |
| **Billing scope** | FinOps/accounting tracks budgets under billing agreement structures | Naming and permissions vary by billing account/agreement type |

**Never blindly add child budgets to parent budgets.** A subscription budget already encompasses all costs from resource group budgets inside it. These two figures are **two governance targets** over overlapping scopes, not two independent spending pools.

### 3.2. Choosing a Scope Structure in a Project

Suppose the `orders` system has three environments and a shared platform group:

~~~mermaid
flowchart TB
    S["Application subscription"] --> P["rg-orders-prod<br/>Budget: 8,000 USD/month"]
    S --> D["rg-orders-dev<br/>Budget: 1,200 USD/month"]
    S --> T["rg-orders-test<br/>Budget: 900 USD/month"]
    S --> O["rg-platform-shared<br/>Shared costs"]
    S -. "Tracks total" .-> B["Subscription budget<br/>May encompass all groups above"]
~~~

If the shared platform holds Log Analytics workspaces, DNS, firewalls, or shared network links, the budget for `rg-orders-dev` **does not necessarily reflect total cost of ownership** for the dev environment. You need a shared-cost allocation model by owner, team, product, or Cost Allocation matching organizational data.

A practical operational strategy:

1. **Subscription budget** to track overall executive ceiling and trends.
2. **Environment/team budgets** to assign operational accountability.
3. **Shared cost reporting** for networking, monitoring, backups, or shared services.
4. **Service/SKU-level forecasting** to explain changes rather than watching total spend alone.

### 3.3. What Are the Limits of Tags and Filters?

Tags such as `costCenter`, `environment`, `application`, or `owner` help filter and group costs where data and resources support them. However:

- Not every charge type or resource carries identical tags or inherits tags as expected.
- Certain billing-scope charges, commitment charges, or shared services may not map cleanly to a single resource group/tag.
- Adding tags today does not necessarily backfill all historical cost records.
- Budget filter support and UI/API capabilities vary by scope and billing agreement.

Therefore, after applying a tag filter, **compare the filtered cost total against Cost Analysis** to avoid creating a budget that silently misses a major portion of spend.

## 4. Designing the Budget Amount Before Opening the Portal

An arbitrary threshold without historical data or load plans alerts either too early or too late. Start by establishing a baseline per service and expected usage.

### 4.1. Monthly Budget Calculation Example

A development environment for an Azure application has projected costs:

| Category | Cost Driver | Monthly Projection |
| --- | --- | ---: |
| App Service / compute | Hourly instances, autoscale | 480 USD |
| Database | SKU, storage, backup/I/O | 280 USD |
| Storage and backup | Stored GB, access operations | 95 USD |
| Networking | Data transfer, public IP, gateway, or NAT | 110 USD |
| Azure Monitor / Log Analytics | Billable ingestion, retention, queries where applicable | 135 USD |
| **Baseline total** | | **1,100 USD** |
| **Estimated contingency buffer** | Load variations, ingest spikes, and other variance | **100 USD** |
| **Target budget** | | **1,200 USD/month** |

From the 1,200 USD budget, define alert thresholds:

| Threshold | Corresponding Value | Operational Meaning |
| --- | ---: | --- |
| **Actual 60%** | 720 USD | Reminder to review trends and allocation |
| **Actual 80%** | 960 USD | Investigate major spend drivers; evaluate optimizations |
| **Actual 100%** | 1,200 USD | Trigger escalation workflow for over-target spend |
| **Forecasted 100%** | Projected above 1,200 USD | Early root-cause analysis of projected overrun before period end |

These are **illustrative thresholds**, not mandatory Azure standards. A dev workload might use 50/75/90, whereas production may use thresholds tailored to scale and business requirements.

### 4.2. Accounting for Seasonality, Pricing, and Business Factors

Account for:

- **Fixed or committed costs:** Reservations or commitments that cannot be scaled down immediately.
- **Variable costs:** Traffic, instance counts, storage volume, log ingestion, and queries.
- **Product events:** Marketing campaigns, migrations, load tests, DR drills, or major releases generating unusual load.
- **Safe minimum floor:** You cannot arbitrarily turn off databases, backups, security monitoring, or production workloads solely because a budget threshold was hit.
- **Currency and terms:** Set budgets in the same currency displayed by the UI/billing scope; never convert invoices manually using rough exchange rates.

You can set a budget from a multi-month average plus a buffer, provided you clarify which expenses are one-off versus recurring. The goal is an **actionable budget**, not just a round number.

## 5. Preparing Permissions and Data Before Creating a Budget

Sign in to Azure with an Entra ID account authorized in the target tenant. Before making changes, verify:

1. **Subscription/billing scope:** You are viewing the exact scope where costs accrue.
2. **Cost Management permissions:** Appropriate read, budget creation/edit, or billing roles at that scope; cost visibility may also depend on billing agreement settings.
3. **Data history:** Is there sufficient history and acceptable latency to establish a baseline?
4. **Recipients:** Active team distribution emails and an Action Group in the right subscription/scope if used.
5. **Owners:** Who approves amount changes, who receives alerts, and who is authorized to optimize resources.
6. **Escalation path:** When spend exceeds target, is it routed via tickets, ChatOps, or change management?

Roles like **Cost Management Reader** typically allow reading data, while editing budgets requires higher permissions such as **Cost Management Contributor** at supported scopes. Billing-scope access may be governed by separate billing roles. Verify specific feature entitlements rather than assuming one role works everywhere.

**Least privilege:** Budget email recipients do not need permissions to modify VMs, Azure SQL, or production resources. Budget operators should likewise not be granted subscription Owner solely to view costs or edit alerts.

## 6. Creating a Budget in the Azure Portal

The UI evolves over time, but the core workflow involves choosing scope, amount, period, and notifications.

### Step 1 — Open the Right Cost Management Scope

1. Sign in to the **Azure Portal** and verify the active tenant/subscription.
2. Open **Cost Management + Billing** or open **Cost Management** inside the target subscription/resource group.
3. Under Cost Management, select **Budgets**.
4. Check the **scope** pill at the top of the screen. To scope the budget solely to `rg-orders-dev`, ensure you are inside that resource group or apply Portal-supported filters properly.

Do not create a subscription-wide budget assuming it only tracks the resource group you were viewing on another tab.

### Step 2 — Set Amount and Time Period

Example:

~~~text
Name:                 budget-rg-orders-dev
Scope:                Resource group rg-orders-dev
Budget period:        Monthly
Amount:               1200 (account display currency)
Start date:           2026-11-01
End date:             2027-10-31
Owner:                Orders / Dev Team
~~~

`Monthly` evaluates the 1,200 limit each month; start/end dates define the active validity window. When choosing dates, follow UI and API rules for period boundaries, effective span, and timezones. If the UI displays a currency other than USD, **adjust the amount to that actual currency**—never copy 1,200 blindly.

### Step 3 — Add Filters If Needed

If the scope is already `rg-orders-dev`, a redundant `ResourceGroupName=rg-orders-dev` filter is usually unnecessary. Add service or tag filters only when scoping to a sub-workload and confident the data classifies cleanly.

Check the resulting spend shown in the Portal's preview chart/table. If networking or storage charges fall outside the filter, the budget may under-cover the application's real footprint.

### Step 4 — Add Actual Alerts

Define notifications for recorded actual spend within the cycle:

| Illustrative Rule Name | Condition | Recipients |
| --- | --- | --- |
| `actual-60` | Actual exceeds 60% of budget | FinOps / owner email |
| `actual-80` | Actual exceeds 80% of budget | Owner + operations team |
| `actual-100` | Actual exceeds 100% of budget | Owner + budget approver |

In the Portal, choose type **Actual** where available, enter each threshold, and add **email recipients** or a supported Action Group. Confirm all rules apply to the same scope and amount.

### Step 5 — Add Forecasted Alerts

Create a **Forecasted 100%** rule if supported by the scope and UI. This helps when current burn rate indicates a likely overrun even before actual spend crosses 100%.

Not every scenario has enough history for reliable forecasts. Depending on scope and day of month, forecasted thresholds may be unavailable or shift as new usage arrives.

### Step 6 — Save and Verify

After saving, return to the Budgets list at **the exact selected scope** and verify:

- Name, amount, currency, reset period, and effective dates.
- Filters, Actual/Forecasted types, thresholds, and recipient list.
- Who holds permissions to maintain the budget going forward.
- Links to runbooks and owners if your organization maintains related documentation.

**Budget alerts are not real-time per-transaction or per-minute triggers.** Costs must flow through the billing/Cost Management pipeline, post, and be evaluated; latency exists between resource usage and alerting. Never rely solely on budget alerts to prevent runaway high-velocity spend.

## 7. How Actual and Forecasted Alerts Work

Suppose a 1,200 USD/month budget configures Actual 80%, Actual 100%, and Forecasted 100%.

~~~mermaid
flowchart TD
    A["Cost data for scope + period"] --> B["Compute actual / amount"]
    A --> C["Estimate forecast / amount if supported"]
    B --> D{"Actual > 80%?"}
    D -->|"Yes"| E["Notify Actual 80%"]
    B --> F{"Actual > 100%?"}
    F -->|"Yes"| G["Notify Actual 100%"]
    C --> H{"Forecasted > 100%?"}
    H -->|"Yes"| I["Notify Forecasted 100%"]
    E --> J["Recipients / Action Group"]
    G --> J
    I --> J
    J --> K["Cost analysis and decision runbook"]
~~~

The diagram illustrates **conceptual logic**. Exact evaluation cadence, threshold timing, notification frequency, and behavior under fluctuating spend are governed by the platform. In live deployments, select the UI/API threshold operator (e.g., **GreaterThan**) and validate against real data; never assume an alert fires strictly once or instantaneously the moment spend touches a round figure.

### 7.1. Month-by-Month Milestone Illustration

| Hypothetical Date | Actual | Forecast | Assessment |
| --- | ---: | ---: | --- |
| 11/05 | 220 USD | 1,050 USD | Below Actual thresholds; forecast on target |
| 11/12 | 525 USD | 1,270 USD | May trigger Forecasted 100% |
| 11/20 | 970 USD | 1,410 USD | Actual crossed 80%; Forecasted still over |
| 11/28 | 1,230 USD | 1,260 USD | Actual crossed 100% |

This example is illustrative only. Because data has latency and forecasts shift with usage trends, **the actual day an alert arrives may differ** from the day simple arithmetic suggests a threshold was crossed.

### 7.2. Why Might an Expected Alert Fail to Arrive?

Several causes to inspect:

- Budget was created on the wrong scope or filters excluded target charges.
- Wrong currency/amount or expired/future effective dates.
- Cost data has not yet updated and evaluated the threshold.
- Notification rule is disabled, recipient address is wrong, or email landed in spam/quarantine.
- Action Group changed, requires verification, or target channel failed.
- Forecast/threshold type is unsupported at this scope, or forecast prerequisites aren't met yet.
- The user is inspecting Cost Analysis with different filters/views than the budget.

**Troubleshooting approach:** First verify the budget exists and conditions were met using identical scope/period data; then check recipient and Action Group settings. If still anomalous, capture redacted configuration screenshots, UTC timestamps, and data window details to investigate or escalate.

## 8. Email Notifications and Azure Monitor Action Groups

### 8.1. Direct Email

Email works well for notifying FinOps, owners, or team mailing lists. Prefer **monitored team distribution lists** over individual addresses that break when people change roles or go on leave. Establish a process to review recipient lists during team transitions.

Alert emails should guide operators to Cost Analysis, the budget scope, and the runbook. When Azure-generated email templates allow limited customization, use clear budget names and keep internal documentation links accessible.

### 8.2. Action Groups

**Azure Monitor Action Groups** provide notification channels and supported workflow integrations. Where permitted at the budget scope, linking an Action Group lets you:

- Deliver notifications to appropriate recipient lists.
- Trigger webhooks, Logic Apps, or workflows per organizational policy.
- Route alert details into incident/ticketing systems.
- Request on-call analysis and approval for cost-saving changes.

Not every Action Group action type suits every scenario or account offer. Verify exactly which action types the budget UI allows, required permissions, and payload schemas before configuring. Automations calling external systems may need authentication, retries, and deduplication.

### 8.3. Budgets Do Not Automatically Stop Resources

Hitting 100% **does not automatically**:

- Stop App Service or VMs.
- Delete databases, disks, backups, or snapshots.
- Reject customer requests.
- Block new resources from incurring charges.
- Lock subscriptions across all account types.

Some offers/subscriptions have a separate **spending limit** feature, which should not be confused with an Azure Cost Management budget. To enforce hard guardrails, implement **Azure Policy**, provisioning approvals, quotas, RBAC, autoscale caps, or controlled automation. Never automatically stop or delete production resources solely on a budget alert.

## 9. Deploying a Budget with Bicep

Declaring budgets as IaC provides version control, change review, cross-environment consistency, and easy recovery. Azure Resource Manager exposes the **Microsoft.Consumption/budgets** resource type at supported scopes.

**Standalone example:** `budget.bicep` deploys **at the resource group scope** `rg-orders-dev`. It creates a monthly budget at the deployment target scope. Names, dates, amounts, and email addresses are parameterized; adapt them to your organization and verify API versions and feature support before running.

~~~bicep
targetScope = 'resourceGroup'

@description('Budget name within the target resource group.')
param budgetName string = 'budget-rg-orders-dev'

@description('Budget amount in the billing scope currency.')
@minValue(1)
param budgetAmount int = 1200

@description('Start date at the beginning of a billing cycle: YYYY-MM-DDT00:00:00Z.')
param budgetStartDate string

@description('Effective end date in ISO 8601 UTC format.')
param budgetEndDate string

@description('Team email responsible for monitoring the budget.')
param notificationEmail string

resource monthlyBudget 'Microsoft.Consumption/budgets@2023-05-01' = {
  name: budgetName
  properties: {
    category: 'Cost'
    amount: budgetAmount
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: budgetStartDate
      endDate: budgetEndDate
    }
    notifications: {
      actual80: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 80
        thresholdType: 'Actual'
        contactEmails: [
          notificationEmail
        ]
      }
      actual100: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 100
        thresholdType: 'Actual'
        contactEmails: [
          notificationEmail
        ]
      }
      forecast100: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 100
        thresholdType: 'Forecasted'
        contactEmails: [
          notificationEmail
        ]
      }
    }
  }
}

output configuredBudgetName string = monthlyBudget.name
~~~

Across different API versions or scopes, schemas, supported fields, and notification limits may vary; validate the template against the resource provider on an actual account. This is a **configuration example**, not a claim that every billing scope supports identical fields.

### 9.1. Key Elements in the Template

- `targetScope = 'resourceGroup'` scopes the budget to the target resource group at deployment time.
- `category: 'Cost'` defines a cost budget rather than a resource-count budget.
- `amount` is the absolute per-period amount in the scope's currency.
- `timeGrain: 'Monthly'` controls the evaluation cycle, distinct from `timePeriod` which defines overall lifetime.
- `notifications` defines three separate rules: two Actual and one Forecasted.
- `contactEmails` lists alert recipients, not Microsoft Support contacts.
- `operator: 'GreaterThan'` triggers when *exceeding* the percentage. If policy requires triggering on exact equality too, check API-supported operators and adjust accordingly.

### 9.2. Validating and Deploying with Control

After confirming the active subscription and ensuring the target resource group exists, use these illustrative CLI commands:

~~~bash
az account show --query "{subscription:id,tenant:tenantId}" -o json

az deployment group validate \
  --resource-group rg-orders-dev \
  --template-file budget.bicep \
  --parameters \
    budgetAmount=1200 \
    budgetStartDate=2026-11-01T00:00:00Z \
    budgetEndDate=2027-10-31T00:00:00Z \
    notificationEmail=finops@example.com

# Deploy only after validation, scope, and permissions are verified.
az deployment group create \
  --resource-group rg-orders-dev \
  --template-file budget.bicep \
  --parameters \
    budgetAmount=1200 \
    budgetStartDate=2026-11-01T00:00:00Z \
    budgetEndDate=2027-10-31T00:00:00Z \
    notificationEmail=finops@example.com
~~~

The commands use `bash` line continuations. In PowerShell, adjust line-continuation syntax or run on a single line. `finops@example.com` is an **illustrative** address, not a real production notification target. The illustrative dates fit an exercise in November 2026; in other periods, select dates compliant with budget date rules.

After deployment, inspect `rg-orders-dev` in the Azure Portal to **verify the name, amount, effective period, thresholds, and recipients**. Successful template validation and deployment do not prove emails will be delivered or cost data will refresh instantaneously.

### 9.3. When to Use Bicep, Portal, or Automation?

| Method | Strengths | Considerations |
| --- | --- | --- |
| **Azure Portal** | Easy to inspect scope, cost chart, and notification UI | Manual edits can drift across environments |
| **Bicep/ARM** | Version control, peer review, repeatable rollout, parameter policies | Must manage API versions, permissions, and time-period rules |
| **REST/API/SDK** | Suited for managing many budgets and governance platform integration | Authentication, retries, rate limits, and drift |
| **FinOps reporting** | Aggregates multiple scopes, explains variance and trends | Must keep data sources, filters, and cost types consistent |

Avoid turning budget amount changes into unreviewed manual edits. For critical systems, changing amounts or recipients should go through peer review like any other IaC change.

## 10. Runbook for Responding to Cost Alerts

Budget alerts are far more effective when paired with a threshold-driven investigation and response workflow. The sample below targets `orders-dev` with a 1,200 USD monthly budget.

### 10.1. General Workflow

~~~mermaid
flowchart TD
    A["Receive Actual / Forecasted alert"] --> B["Verify scope, date, currency, threshold"]
    B --> C["Open Cost Analysis for same scope and period"]
    C --> D["Group by service / resource / tag"]
    D --> E["Cross-check deployments, scaling, logs, traffic"]
    E --> F{"Is cost increase expected and approved?"}
    F -->|"Yes"| G["Document rationale; update forecast / budget per authority"]
    F -->|"No or unclear"| H["Select safe optimization actions"]
    H --> I["Review impact, approve, deploy change"]
    I --> J["Monitor costs and SLOs post-change"]
    G --> J
    J --> K["Archive evidence and update plan"]
~~~

**Step 1 — Confirm the alert.** Read the budget name, scope, monthly period, amount, Actual/Forecasted type, and threshold. Record the UTC receipt timestamp and assigned responder. If the email leaves scope ambiguous, verify in the Portal before acting.

**Step 2 — Inspect cost breakdown.** In Cost Analysis, select the identical scope and timeframe; slice by service, resource, resource group, tag, and daily cost. Compare the rise against baseline and planned events.

**Step 3 — Check recent changes.** Audit scale-outs, SKU upgrades, database throughput, snapshots, storage replication, outbound traffic, Log Analytics ingestion/retention, and uncleaned test resources. Cross-reference Activity Logs or CI/CD pipelines to pinpoint causes.

**Step 4 — Classify and decide.** Categorize the spend: planned growth, unexpected spike, misallocation, missing tags, technical regression, or reporting lag/billing adjustment.

**Step 5 — Optimize safely.** Adjust dev VM auto-shutdown schedules, scaling rules, log retention, unused storage, right-sizing, and quotas when approved. Never disable replication, backups, key management, security monitoring, or production resources without evaluating SLOs, RTO/RPO, and organizational policy.

**Step 6 — Verify.** Monitor cost trends once fresh billing data lands, and confirm application, security, throughput, and availability metrics. A cost reduction that causes severe downtime is a failure.

### 10.2. Accountability by Threshold

| Alert | Primary Responder | Priority Checks | Output |
| --- | --- | --- | --- |
| Actual 60% | Service owner | Cumulative spend and burn rate vs. remaining days | Status note and assessment |
| Actual 80% | Owner + FinOps | Top cost drivers and recent changes | Actionable ticket with assigned owner |
| Forecasted 100% | Owner + budget approver | Projection, planned load, fixed vs. flexible spend | Optimization plan or approved budget increase |
| Actual 100% | FinOps + business owner | Overrun magnitude, production obligations, operational risk | Budget decision and remediation plan |
| Anomaly below threshold | SRE/FinOps | Cost anomalies and unplanned resources | Rapid check to halt runaway growth |

Severity is not determined by percentage alone. A tiny budget crossing 100% may have negligible financial impact, whereas a sharp spike on a large budget demands attention even at 50%. Combine **absolute amount**, burn velocity, forecast, and technical risk.

## 11. Real-World Scenario: Log Analytics Driving Up Costs

**Context:** The `orders-dev` team has a 1,200 USD/month budget. After a release, developers enabled debug logging across several services and pushed heavy event volume into Log Analytics. Forecast jumped to 1,500 USD while actual sits at 780 USD.

### 11.1. Investigation Questions

1. Which resource group does the budget cover? Is the Log Analytics workspace inside that resource group or in a shared platform group?
2. Did cost increase in **Azure Monitor/Log Analytics** or in compute/networking? Is associated data transfer or App Insights ingestion involved?
3. Starting with which release and date did log volume change?
4. Are legitimate activities like DR drills, load tests, or incident investigations requiring extended logging?
5. If sampling or retention is reduced, will security monitoring, compliance, or incident forensics be impaired?

### 11.2. Appropriate Actions

Illustrative remediation steps, subject to policy:

- Turn off excessive debug logging in dev once investigation finishes.
- Add source-side filtering/sampling where supported without dropping critical telemetry.
- Differentiate retention by log category, separating long-term audit logs from ephemeral debug logs.
- Add post-release log ingestion reviews and require owner sign-off for major telemetry changes.
- Compare before/after forecasts across at least one billing refresh cycle; do not expect same-day chart drops.

**Do not** disable Azure Monitor entirely, turn off audit logs, or drop intrusion-detection logs just to meet a budget. Controls must preserve security, forensics, and compliance.

## 12. Real-World Scenario: Idle Test VMs Left Uncleaned

**Context:** A load-testing environment kept VMs and managed disks running for days after testing ended. Actual spend crossed 80%, driven by compute and disks.

Investigation steps:

- List newly created resources by resource group, `owner`/`exercise` tags, deployment time, and test schedule.
- Confirm the VM is not serving active users or critical batch jobs; never assume a `test` name guarantees safety.
- Verify how VMs are stopped: a **guest OS shutdown** does not equal **deallocate** for stopping compute billing. Managed disks, public IPs, or storage can still incur charges after shutdown.
- Check snapshots, unattached disks, retained resources, and storage before requesting deletion.
- For dev VMs with predictable hours, set auto-shutdown or governed schedules; assess developer experience and backup needs.

Example: shutting down a VM reduces compute charges once deallocated, yet does not eliminate every associated fee. Re-check Cost Analysis after the next data refresh to verify actual impact.

## 13. Action Group Automation: How Far Should You Go?

You can connect an Action Group to a workflow to open tickets or request approvals. A sound flow:

~~~mermaid
flowchart LR
    B["Budget notification"] --> AG["Action Group / workflow"]
    AG --> T["Create cost ticket"]
    T --> O["Owner inspects Cost Analysis"]
    O --> P{"Approve action?"}
    P -->|"Yes"| C["Controlled automation modifies resource"]
    P -->|"No"| R["Log exception / approved budget increase"]
    C --> V["Verify SLO, security, and cost"]
    R --> V
~~~

**Automation safeguards:**

- Validate payloads, scope, and caller identity; never trust unauthenticated requests.
- Use least-privilege identities; never store client secrets in source code or public webhook URLs.
- Enforce **idempotency** so repeated alerts do not spawn dozens of tickets or repeat destructive actions.
- Automate read-only steps (reporting, ticketing) first; production resource changes require strict conditions and approvals.
- Maintain an audit trail: which alert triggered which decision, who approved, what automation ran, and whether it succeeded/failed.
- Provide rollback for SKU/scale edits; evaluate availability, backup, and data impacts.

**Anti-pattern example:** "If budget hits 100%, delete the entire resource group" risks catastrophic data loss and violates availability requirements. Replace it with alerts, investigation, and approved optimization.

## 14. Verifying Budgets and Notification Rules After Setup

A successfully deployed budget still fails its purpose if the scope is wrong or recipients never act.

### 14.1. Acceptance Checklist

| Check | Required Evidence |
| --- | --- |
| Scope | Exact subscription, resource group, or billing scope name |
| Amount and currency | Matches plan and account currency |
| Period and validity | Monthly and valid start/end dates |
| Filters | Cost Analysis at same scope matches intended spend boundary |
| Actual notifications | Correct thresholds and operators, rules enabled |
| Forecasted notification | Present and supported at selected scope/account |
| Recipients | Active mailing list; confirmed owner |
| Action Group (if used) | Proper channel, permissions, and tested configuration |
| Maintenance access | Authorized maintainers and scheduled review process |
| Runbook | Clear triage and escalation steps with named owner |

### 14.2. Testing Delivery Without Triggering Unnecessary Costs

Create a pilot budget at a suitable scope/environment with test recipients and use **notification channel testing** where supported. You can test an Action Group separately with Azure's built-in test button, though that validates only the Action Group channel—it **does not prove end-to-end Cost Management budget evaluation** triggered.

Avoid intentionally generating large spend just to test an alert. When picking a test threshold near current spend, accept that ingestion latency and evaluation cadence may delay delivery rather than treating immediate silence as a guaranteed platform defect.

### 14.3. Troubleshooting Missing Notifications

If no email arrives:

1. Confirm the budget is active, on the right scope, and has sufficient recorded spend to exceed the threshold.
2. Check that the rule is enabled, along with threshold type, operator, and recipients.
3. Inspect Action Group status, inbox, spam/quarantine, and mailing list delivery rules.
4. Wait for the next cost data refresh cycle and compare against recorded UTC timestamps.
5. Document configuration, actual/forecast spend, timestamps, and checks attempted; escalate to Azure Support if evidence indicates malfunctioning behavior.

Never assume exact notification SLAs unless explicitly documented by the service. Certain resource charges may also post late or adjust retroactively.

## 15. Common Configuration Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Budget not visible on current page | Viewing wrong subscription, resource group, or billing scope | Switch to the right scope and verify permissions |
| Cannot create/edit budget | Missing scope permissions; billing policy or entitlement difference | Check Cost Management/billing role assignments |
| Forecasted alert missing/not firing | Scope, API, or forecast model unsupported for scenario | Check feature support at scope and choose valid rules |
| Email not arriving | Wrong recipient, blocked mail, or spend hasn't crossed threshold | Verify config, data freshness, and delivery channels |
| Budget at 80% differs from billing chart | Different period, filter, cost type, or latency/adjustments | Match scope, currency, cost type, and timestamp |
| Tag-filtered budget misses spend | Untagged resources, un-taggable charges, or historical records | Audit allocation and data limitations |
| Exceeded 100% but resources keep running | Budgets only alert | Implement runbooks and separate guardrails if needed |
| Auto-shutdown caused outage | Automation lacked approvals and dependency checks | Add approvals, allowlists, rollback, and SLO checks |
| Costs rose despite VM Stop | VM not deallocated or disks/network still billing | Check VM power/allocation state and individual meters |
| Budget generates alerts but no action | Missing owner, priorities, or threshold actions | Link runbooks, ticketing, and review cadence |
| Resource group budget misses full app cost | Shared services reside outside scope | Build separate showback/chargeback reporting |

## 16. Capstone Lab: Creating a Budget for an Azure Application

**Scenario:** A company runs `orders-dev` using App Service, Azure SQL, Storage, VNet, Log Analytics, and shared data services. Engineering is accountable for a **1,200 USD/month** controllable target, and FinOps needs alerts on rising spend.

### Task A — Define Scope and Baseline

1. Choose resource group `rg-orders-dev` for direct environment resource budgeting; list shared services outside that scope.
2. From Cost Analysis, tabulate projected costs for compute, data, storage, network, and monitoring; compare against history and planned events.
3. Decide whether a subscription-level budget is needed to capture shared costs.
4. Record owner, allocation method, currency, and data limitations.

**Output:** A `scope → owner → cost driver → budget target` table explaining any spend excluded from the budget.

### Task B — Create the Budget and Notifications

In the Azure Portal or an authorized test resource group:

~~~text
Budget name: budget-rg-orders-dev
Period:      Monthly
Amount:      1,200 (displayed currency)
Actual:      60%, 80%, 100%
Forecasted:  100% if supported
Recipients:  Approved operations and FinOps teams
Time period: First of current month to appropriate end date
~~~

After saving, verify the configuration at that exact scope. If using Bicep, adapt Section 9's template ensuring all parameters, dates, and recipients are valid. Never use arbitrary personal emails or unconfirmed recipients.

### Task C — Simulate Alert Triage Without Generating Real Spend

Suppose by day 20 actual is 970 USD and forecast is 1,410 USD. Determine:

- Which Actual thresholds have been crossed and which have not?
- Would a Forecasted 100% alert reasonably fire?
- Which spend drivers should the owner inspect first, and who must be notified?
- If the end-of-month invoice differs from the forecast, what factors must be checked?

**Suggested answer:** Actual crossed 60% and 80%, not 100%. Forecast is projected over 100%. Inspect cost drivers by service/resource, SKU/log-ingest changes, scope/account, accounting method, and data timestamp; then execute safe actions.

### Task D — Draft a Runbook for the 80% Alert

Create a concise checklist covering recipients, response SLA, Cost Analysis link, scope/currency verification, deployment evidence, valid optimizations, approval authority, and verification criteria. Assume an idle load-test VM was found running off-hours: document verifying necessity, deallocating upon approval, and tracking residual disk/network fees.

### Task E — Review Output and Document

Submit:

| Deliverable | Required Contents |
| --- | --- |
| Budget configuration | Scope, amount, currency, dates, time grain |
| Alerts | Actual/Forecasted rules, thresholds, recipients |
| Data source | Cost Analysis views and applied filters |
| Permissions | Read/edit roles, owner, and review cadence |
| Runbook | Verification, investigation, optimization, and approval criteria |
| Evidence | Redacted configuration screenshot, explanation of check logic |
| Residual risks | Ingestion delay, shared costs, untagged spend, forecast variance |

**Pass criteria:** Budget placed at the right scope, at least two Actual thresholds plus one Forecasted rule where available, named owner, clear overrun triage plan, and explicit recognition that budgets do not automatically cap spend.

## 17. Long-Term Budget Operations and Review

A budget accurate at creation can drift out of date as applications scale, SKUs change, or subscriptions reorganize. Maintain a review cadence:

- **Weekly or risk-based:** Inspect actuals, forecasts, top cost drivers, and unowned alerts.
- **Monthly:** Compare budget against posted charges, explain variances, and update workload plans and idle resource cleanup.
- **Around major releases:** Estimate cost impact of database tiers, autoscale, logging, DR, networking, and storage replication.
- **During reorganization:** Audit scopes, filters, tags, permissions, and recipient lists.
- **After cost incidents:** Archive timeline, root-cause analysis, remediation, and verification checks.

Track operational metrics such as % of budgets with assigned owners, alert response rate, forecast-vs-actual accuracy, time-to-detect spend spikes, % unallocated spend, and verified post-change savings.

If an alert causes chronic noise due to a low threshold or missing owner, tune it from data—never silence it blindly without another observability mechanism.

## 18. Key Principles to Remember

1. **A budget is an alerting tool**, not an automatic spending kill-switch. Blocking or modifying resources requires separate policies and workflows.
2. **Scope determines a budget's usefulness:** Subscription, resource group, and billing scopes reflect distinct accountability boundaries.
3. **Actual and Forecasted complement each other:** Actual measures recorded spend; Forecasted warns early about projected period overruns where data allows.
4. **Azure cost data has latency and differing accounting views:** Align scope, period, cost type, currency, and filters before drawing conclusions.
5. **Notifications need accountable owners:** Emails and Action Groups only pay off when linked to investigation runbooks, controlled optimization, and post-change verification.
6. **IaC enables repeatable, auditable configuration:** Bicep can declare amount, period, thresholds, and recipients, but must be validated against API versions and scope permissions.
7. **Never sacrifice reliability or security for short-term savings:** Changes that compromise data, backups, or SLOs can cost far more than the infrastructure saved.

Properly designed budgets and cost alerts enable engineering, operations, and FinOps teams to spot Azure spending trends early, assign clear accountability, and keep application architectures aligned with performance, security, and financial goals.
