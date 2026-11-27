# Setting Up Cost Alerts and Lab Resource Cleanup Procedures

An OCI learning environment can continue incurring charges after you close your browser or stop a virtual machine. Volumes, backups, databases, load balancers, and other services have their own lifecycles. If you only look at Compute status, you can easily overlook components that remain active.

Cost alerts help detect unexpected usage early; resource cleanup procedures terminate cost sources that are no longer needed. Both must be prepared before starting a lab.

This lesson guides you through designing a budget, choosing alert thresholds, defining response actions, and verifying Oracle Cloud Infrastructure environment cleanup. Numbers in the examples are hypothetical budgets, not OCI service price quotes.

## 1. Objectives and Principles

After this lesson, you will be able to:

- Design a cost-tracking scope for a practice environment.
- Create budgets and appropriate alert rules.
- Distinguish actual cost, forecasted cost, and provisioning limits.
- Respond to alerts without accidentally deleting important data or shared resources.
- Clean up resources in dependency order.
- Reconcile infrastructure state against billing data after cleanup.

Three principles to remember:

1. **A budget is a spending monitoring tool, not a guarantee that billing stops at a fixed amount.**
2. **Stopping one resource does not mean the entire related system has been cleaned up.**
3. **Deleting a resource does not erase charges already incurred prior to deletion.**

All actual deletion actions must stay within your assigned lab scope and ensure required data has been handled appropriately.

## 2. Understanding Control Mechanisms

### 2.1. Budgets, Quotas, and Cleanup Procedures Serve Different Roles

| Tool or mechanism | What it helps do | What it does not guarantee |
| --- | --- | --- |
| Budget | Tracks spending within a configured scope and period | Does not automatically enforce a hard billing cap |
| Budget alert rule | Notifies when actual or forecasted cost conditions are met | Does not automatically stop or delete resources |
| Cost Analysis | Analyzes costs across supported dimensions | Does not reclaim resources automatically |
| Compartment quota | Restricts provisioning by resource and applied scope | Does not block every type of cost at a specific dollar amount |
| Service limit | Caps service usage per OCI terms | Not a monetary budget |
| IAM | Restricts who can create, modify, or delete resources | Does not calculate costs or guarantee zero charges |
| Lab cleanup schedule and procedure | Ends usage and reclaims unneeded resources | Effective only when executed and verified |

A resource provisioned validly within quota can still incur charges. Exceeding a budget threshold does not mean OCI will immediately terminate resources.

### 2.2. Alerts Are Not an Instantaneous Cutoff Mechanism

Usage data, cost data, and alert evaluation can experience latency. Do not plan under the assumption that an alert arrives the instant an extra charge occurs.

Implications:

- Set thresholds lower than the maximum spending you can accept.
- Leave buffer room for reporting latency and operator response time.
- For high-cost-rate resources, verify pricing before creating and monitor actively during the lab session.
- Not receiving an email does not prove costs are zero.

Even if you build custom automation that reacts to alerts, it still has latency and can encounter permission or API errors. Do not treat it as a guarantee that billing stops right at the threshold.

### 2.3. Free Tier and Credits Do Not Replace a Cost Plan

Do not infer that "using a learning account" means every action is free. Free eligibility, credit usage terms, and transitions to billed resources must be verified for your specific account and service.

Common pitfalls include:

- Choosing a configuration different from the one covered by free entitlements.
- Creating extra volumes, backups, or services outside the planned scope.
- Using resources in a region or configuration that does not qualify for the entitlement.
- Leaving workloads running after a promotional period ends or when account status changes.

Before a lab, confirm current configurations and billing terms. This lesson does not use a fixed price or promotion to predict costs for every tenancy.

## 3. Preparing Lab Scope Before Creating Resources

### 3.1. Prefer a Dedicated Compartment

A dedicated lab compartment makes authorization, inventory, and cost reconciliation easier. If your organization already assigned a compartment, use that exact scope instead of inventing a new hierarchy.

Example plan:

~~~text
Lab compartment: learning-lab
Owner:           learner or lab group
Region:          assigned region
Duration:        a practice session with a scheduled end time
Resources:       an instance, volume, and network supporting the lab
~~~

Names in this example are not instructions to create real resources.

When choosing a budget scope, check carefully how the tool applies to compartments and child branches. Do not assume selecting a parent compartment tracks only resources placed directly inside it.

For simple labs, using a clearly scoped leaf compartment reduces the risk of mixing in another team's costs.

### 3.2. Distinguish Newly Created Resources from Shared Resources

Before starting, classify resources into two groups:

| Group | Example | End-of-lab rule |
| --- | --- | --- |
| Created and owned by the lab | Test instance, dedicated volume, temporary bucket | Evaluate for reclamation per plan |
| Shared or borrowed | Shared VCN, classroom subnet, centralized logging | Retain; remove only lab-specific parts when permitted |

An instance sitting inside a shared subnet does not make the entire subnet eligible for deletion.

Likewise, having delete permissions does not mean every visible resource falls within your cleanup scope.

### 3.3. Maintain a Resource Inventory

Record the following fields in your approved lab management tracker:

| Field | Purpose |
| --- | --- |
| Lab ID | Group resources belonging to the same practice session |
| Resource type and OCID | Accurate identification |
| Region and compartment | Identify where to inventory |
| Owner | Person deciding whether to keep or reclaim |
| Expiration time | Milestone when cleanup must be evaluated |
| Dependencies | Determine reclamation order |
| Data to preserve | Avoid deleting important outputs |
| Shared or dedicated | Prevent overly broad cleanup scope |
| Post-lab state | Deleted, retained with reason, or pending handling |

Tags can be used if your tenancy defines conventions such as `labId`, `owner`, and `expiresAt`. Tags assist inventory; an expired tag itself does not execute deletion.

Resource identification tags are also not automatically cost-tracking tags configured for billing reports. If you want tag-scoped budgets, satisfy the cost-tracking mechanism requirements and verify actual reporting data.

## 4. Designing a Budget for a Practice Environment

### 4.1. Define the Amount and Tracking Period

Suppose the learning budget is **20 currency units in the account's billing currency per month**.

This number merely illustrates threshold calculation. Learners must pick a budget based on:

- Planned resources and configurations.
- Expected runtime duration.
- Storage, backups, and supporting services.
- Spending already incurred during the current period.
- The account owner's cost tolerance.

Do not enter a number in VND while the UI operates in USD, or vice versa. Check the displayed currency before saving.

A periodic budget is not a counter that resets after each lab session. When sharing a monthly budget, subsequent sessions must account for what was already spent earlier in the period.

### 4.2. Choose an Appropriate Scope

Options typically considered:

- Track the entire tenancy to monitor aggregate spending.
- Track a dedicated lab compartment.
- Track by cost-tracking tag when the environment is properly configured.

Do not select a scope solely because a name looks right. Verify the compartment OCID, child hierarchy, and the actual set of resources rolled into billing data.

You can pair an account-wide budget for overall alerts with a lab budget for isolation, if features and permissions allow. In that case, understand that both budgets may reflect the same charge; do not add the two notifications together as double service usage.

### 4.3. Illustrative Thresholds

With budget B = 20:

| Alert type | Threshold | Illustrative value | Purpose |
| --- | ---: | ---: | --- |
| Actual spend | 50% B | 10 | Check consumption pace |
| Actual spend | 80% B | 16 | Pause creating new resources, audit existing ones |
| Actual spend | 100% B | 20 | Execute the agreed response plan |
| Forecasted spend | 100% B | 20 for full forecast period | Detect potential overrun before actual spend hits the cap |

Forecasted spend is not already-incurred spend. It depends on service data and forecasting methodology; it may be less meaningful with sparse data or sudden usage spikes.

A 100% threshold should never be your only alert. If it arrives after charges are already recorded, you still need time to inspect and clean up resources.

## 5. Setting Up Budgets and Alerts in the Console

### 5.1. Check Permissions and Context

Before configuring:

1. Confirm the exact tenancy and account.
2. Open the billing/cost management group and the corresponding Budgets feature.
3. Confirm the identity is allowed to view cost data, manage budgets, and configure alert rules in the required scope.
4. If the learner account lacks billing permissions, coordinate with the account owner or designated administrator.

Permission to create Compute instances in a lab compartment does not automatically grant permission to read or manage budgets. Do not grant tenancy-wide admin privileges just to complete this lesson.

Menu names and field locations may vary with UI updates. Rely on the displayed function and scope when working through the steps.

### 5.2. Create a Budget

In the budget creation workflow, verify equivalent fields:

- Identifiable name, such as `lab-monthly-budget`.
- Appropriate tenancy, compartment, or tag scope.
- Exact compartment or tag value.
- Amount and displayed currency.
- Tracking period and schedule according to supported options.
- Description noting owner and intended purpose.

After saving, reopen the budget and verify its configuration. Do not rely solely on a creation success banner.

A budget does not require creating an instance to "activate." Never create billable resources just to verify whether a budget exists.

### 5.3. Create Alert Rules

For each designed threshold:

1. Select actual spend or forecasted spend.
2. Choose how the UI expresses the threshold, such as percentage of budget or monetary amount.
3. Enter the exact value and check the unit.
4. Specify recipients using the alert delivery mechanism provided by budgets.
5. Add a response message if the UI provides an appropriate field.
6. Save and re-read the rule.

A common mistake is entering 80 without checking whether percentage or currency amount is selected. Those two settings mean very different things.

If the rule accepts an email recipient list, verify addresses and delimiters per UI requirements. Prefer a channel actively monitored by the account owner.

### 5.4. Verify the Alert Delivery Path

Check:

- Has the rule been saved and attached to the right budget?
- Are the recipients accurate?
- Does the delivery channel require a confirmation step or special conditions?
- Does the inbox filter or block notifications?
- Does the owner know how to respond?
- Is there a backup contact if the primary owner is unavailable?

If your mechanism supports test sends or configuration verification, use it within your granted permissions. If not, note the verification limitation rather than intentionally spending money to force an alert.

Do not assume creating a Notifications topic automatically links it to a budget. If you add Events, Notifications, Functions, or external workflows, configure and test that integration path separately.

### 5.5. Record Completion Status

A prepared budget should show:

~~~text
Scope:              verified
Amount and period:  verified
Actual rules:       chosen thresholds configured
Forecast rules:     configured if applicable and supported
Recipients:         cross-checked
Response process:   assigned owner
Limitation:         does not block spending automatically
~~~

If notification delivery has not been verified, do not claim the entire alerting pipeline is operational simply because a rule exists in the UI.

## 6. Responding When an Alert Arrives

### 6.1. At 50%: Inspect Usage

When actual spend hits the early threshold:

- Open Cost Analysis or the corresponding billing tool.
- Select the exact time range.
- Filter down to the budget's compartment or scope.
- Break down by service, region, or resource where data supports it.
- Cross-check against the lab resource inventory.
- Check whether any resources were duplicated or left running off-schedule.

You do not need to delete everything immediately. First identify the cost source and determine whether spending aligns with your plan.

### 6.2. At 80% or Forecasted Overrun: Reduce Overrun Risk

Take action:

1. Avoid creating unnecessary new resources.
2. Wrap up completed lab segments early.
3. Reclaim temporary resources that have no data to keep.
4. Review continuously running resources and scheduled jobs.
5. Confirm enough buffer remains for billing latency and cleanup duration.
6. Coordinate with the account owner if continuing is necessary.

If charges stem primarily from storage, stopping Compute alone may not address the main driver. Address the exact service group generating costs.

### 6.3. At 100%: Execute the Agreed Plan

This threshold requires a clear decision:

- End the lab and clean up lab-owned resources; or
- Continue under a budget approved by the responsible owner.

Do not simply raise the budget to silence alerts without understanding the root cause. Changing a threshold does not reduce charges already incurred.

During cleanup, continue protecting required data and shared resources. An overrun email is not authorization to delete everything in the tenancy.

### 6.4. Keep an Action Log

Record briefly:

~~~text
Timestamp alert received
Relevant budget and threshold
Cost period being inspected
Primary contributing service or resource
Actions taken
Intentionally retained resources and owner
Next verification timestamp
~~~

There is no need to store authentication secrets or full API headers to track cost response actions.

## 7. Preparing End-of-Lab Resource Cleanup

### 7.1. Finalize Scope Before Deleting

Cleanup starts by building a verifiable checklist, not clicking delete sequentially on whatever appears on screen.

For each resource, answer:

1. Does it belong to the right lab?
2. Do the OCID, region, and compartment match?
3. Is it shared?
4. Is there data or output that must be preserved?
5. Do any other resources depend on it?
6. Will deleting it create, retain, or affect another component?
7. Who is responsible for confirming completion?

Retaining a resource must be an intentional decision with a reason, deadline, and owner. Do not let "kept temporarily" linger indefinitely.

### 7.2. Build a Simple Dependency Map

~~~mermaid
flowchart TD
    A["Lab application or job"] --> B["Compute or database"]
    B --> C["Volume / data / backup"]
    B --> D["VNIC or endpoint"]
    E["Lab load balancer"] --> D
    D --> F["Subnet"]
    F --> G["VCN and related network components"]
~~~

Arrows depict conceptual usage or dependency, not a detailed diagram for every service.

You typically need to handle consuming components before deleting the resources they depend on. For shared components, detach only the lab-specific pieces and leave assigned shared infrastructure untouched.

### 7.3. Stop Mechanisms That Can Recreate Resources

Before cleaning up, check for:

- Scheduled jobs.
- Instance pools or autoscaling.
- Deployment pipelines.
- IaC tools managing resources.
- Functions or automation capable of re-provisioning.
- Jobs writing data, taking backups, or syncing.

If you delete an instance while a pool or pipeline recreates it, costs and resources will keep returning.

For IaC-managed resources, use that configuration's destroy workflow where appropriate after reviewing the change plan. Manual deletion can cause state drift or prompt the next deployment to recreate them.

## 8. Cleanup Procedure by Resource Group

### 8.1. Step 1: Protect Required Outputs

Identify data to save before running destructive actions:

- Source code and configurations capable of rebuilding the environment.
- Exercise outputs required for submission.
- Database data requiring export or backup.
- Objects or files needing transfer to an approved storage location.

Backups are not automatically free or automatically deleted alongside the source resource. If keeping a backup, record its expiration date and owner.

Even if no data needs to be kept, document that explicitly to avoid hesitation or confusion during later audits.

### 8.2. Step 2: Handle Workloads and Compute

- Gracefully stop running tasks.
- Detach the instance from orchestration components as needed.
- Confirm the instance does not belong to a group that will recreate it.
- If the lab is completely finished, evaluate terminating rather than merely stopping.
- Carefully read options to keep or delete boot volumes and related components.
- Wait for the operation to reach its terminal state, not just request acceptance.

Do not assume terminating an instance deletes all attached block volumes. Nor should you assume every boot volume is always preserved; behavior depends on chosen options and operation rules.

Afterward, inspect the volume and attachment lists separately within the lab scope.

### 8.3. Step 3: Handle Databases

For database services:

1. Confirm the exact service type and exact lab database.
2. Finalize data retention requirements.
3. Stop applications or jobs still connecting to it.
4. Read deletion options, final backups, and retention periods per service rules.
5. Reclaim according to permissions and plan.
6. Check remaining resources, backups, and related components.

Do not apply one identical deletion procedure across all Oracle database services. Resource structures, stop options, and backup retention behaviors differ.

Stopping a database, where supported by the service, must also be checked against components that continue incurring charges.

### 8.4. Step 4: Handle Storage

| Type | What to check |
| --- | --- |
| Boot volume | Still present after instance termination; whether it needs to be kept |
| Block volume | Remaining attachments, data, or related volume groups |
| Volume backup | Automated or manual backups requiring cleanup per plan |
| Object Storage | Objects, older versions, and incomplete multipart uploads if any |
| Bucket | Remaining data, policies, or retention rules blocking deletion |
| File Storage | Mount targets, exports, and filesystems per service relationships |

In buckets with versioning enabled, deleting the current object may not remove older object versions. Inspect versioning, delete markers, and remaining stored items.

If a retention rule or data protection lock is active, do not try to bypass it to finish cleanup. Document the reason, ongoing cost to monitor, and retention owner.

Never delete the sole backup of required data merely because it was missing from the lab inventory.

### 8.5. Step 5: Handle Endpoints and Lab Private Networking

Once workloads are no longer active:

- Reclaim lab-created load balancers or private endpoints if not needed.
- Check reserved public IPs and determine whether to release them.
- Remove lab-only attachments or connections following service procedures.
- Delete dedicated subnets once no dependent resources remain.
- Handle gateways, routes, and related networking components before deleting a dedicated VCN, per applicable OCI rules.

Do not delete shared classroom VCNs or subnets. Do not assume every networking component has identical billing behavior; check actual service and configuration details.

If a VCN fails to delete, read the dependency error and identify which resource still holds a reference. Never bulk-delete every object in a compartment to force past an error.

### 8.6. Step 6: Audit Supporting Services

Commonly overlooked resources:

- Logs and log destinations created by the lab.
- Scheduled backups or long-term archive data.
- Functions, container images, or artifacts in a registry.
- Monitoring systems, agents, or data-emitting jobs.
- Analytics or data-platform resources spun up during extensions.
- Secrets, keys, or configurations retained per organization policy.

Do not delete shared monitoring infrastructure or shared encryption keys. For keys and encrypted data, understand the consequences before revoking; doing so can render retained data unreadable.

The goal of auditing is a complete inventory, not assuming every item above incurs charges in every configuration.

## 9. Read-Only Inventory Using CLI

The commands below are learning examples for listing resources. There are no delete commands in this section.

Suppose PowerShell has the learner-prepared variables set:

~~~powershell
$env:OCI_LAB_COMPARTMENT_OCID = "<lab-compartment-ocid>"
$env:OCI_LAB_REGION = "<lab-region>"
~~~

List Compute instances in a compartment and region:

~~~powershell
oci compute instance list --compartment-id $env:OCI_LAB_COMPARTMENT_OCID --region $env:OCI_LAB_REGION --all --output json
~~~

List VCNs in the same scope:

~~~powershell
oci network vcn list --compartment-id $env:OCI_LAB_COMPARTMENT_OCID --region $env:OCI_LAB_REGION --all --output json
~~~

Interpret outputs accurately:

- `--all` fetches all pages for the command within the queried scope; it does not query every region or every compartment.
- Two commands inventory only two resource types; they do not prove volumes, databases, or buckets are gone.
- An identity with limited permissions may not see a complete picture.
- Read lifecycle states to distinguish active, in-progress, and terminated resources.
- Never include private keys or tokens in inventory reports.

If a lab spanned multiple regions or child compartments, inspect each relevant scope with appropriate tooling and permissions. Never expand your deletion scope simply because the CLI can list another team's resources.

## 10. Verifying After Cleanup

### 10.1. Infrastructure Check

A complete check verifies:

- Resources slated for deletion reached their expected terminal state.
- No unhandled attachments or dependencies remain.
- No automation is recreating resources.
- Every retained resource has a reason, owner, and review deadline.
- All used regions and compartments were checked.
- Shared resources remain in their expected state.

Some resources may continue appearing in a terminated state for a period of time. Read the state and identifier rather than only counting rows in a list.

### 10.2. Subsequent Cost Verification

Reopen billing tools once data has had time to update, and compare against the cleanup timestamp.

Keep in mind:

- Cumulative period spend does not drop back to zero after deletion.
- Delayed billing records may reflect usage prior to deletion.
- Adjustments or aggregated entries do not automatically prove new resources exist.
- If usage continues accruing for timestamps after cleanup, investigate the relevant service and resource.

View daily or appropriately scoped intervals rather than looking only at monthly totals. Where supported, group by service, region, compartment, or resource to pinpoint sources.

Do not conclude "no more charges" solely because the Compute list is empty. Nor should you conclude cleanup failed solely because the monthly total still shows previously incurred charges.

### 10.3. Keep the Budget to Monitor Residual Usage

Do not immediately delete the budget just to stop receiving emails after a lab ends. Keep monitoring active until remaining components and updated cost data have been verified.

If a budget is shared across multiple practice sessions, update notes and your resource inventory instead of treating each cleanup as a brand-new budget cycle.

Pausing or editing alert rules should follow account governance responsibilities and future usage plans.

## 11. Synthesis Scenario

### Context

A learner sets a monthly budget of 20 currency units with actual spend alerts at 50%, 80%, and 100%, plus a forecasted alert above 100%.

After the lab session, the learner stops the instance and closes the browser. A few days later, an 80% alert arrives.

### Analysis

Stopping an instance does not prove the environment was reclaimed. Check:

- Do boot volumes and block volumes still exist?
- Are load balancers or databases still active?
- Are backups or stored data being retained?
- Is any job recreating resources?
- Did the observed charges occur before or after stopping?
- Are resources sitting in another region or child compartment?

### Resolution

1. Open cost data for the right period and scope.
2. Identify the primary contributing service rather than guessing based on the most visible resource.
3. Cross-check the resource inventory and intentionally retained items.
4. Protect data that needs to be kept.
5. Reclaim lab-owned resources in dependency order.
6. Record completion timestamps for each step.
7. Monitor subsequent billing updates.
8. Improve your end-of-lab procedure so future sessions include inventory and verification steps.

The desired outcome is not "emails stopped arriving," but rather understanding the cost source and handling unneeded resources.

## 12. Verifiable Practice Exercise

This exercise can be completed by configuring a budget and drafting a cleanup plan on an existing environment. You do not need to create extra resources as examples.

### Part A: Prepare Alerts

- Identify the compartment or tracking scope.
- Choose a budget amount and period matching the billing currency.
- Define actual and forecasted thresholds where appropriate.
- Create the budget and alert rules when granted permissions.
- Re-read the configuration and recipients.
- Explicitly note what was verified and what could not be tested.

If your account lacks billing permissions, draft the plan and coordinate with your administrator; do not escalate your own privileges.

### Part B: Build a Cleanup Inventory

Pick an existing lab and complete the table:

| Resource | OCID/identifier | Keep or delete | Dependencies to handle first | Data to preserve | Approver |
| --- | --- | --- | --- | --- | --- |
| Lab instance | Actual value | Per plan | Pool, app, or related jobs | Outputs to submit | Lab owner |
| Dedicated volume | Actual value | Per plan | Attachment | Data to save | Lab owner |
| Shared VCN | Actual value | Keep | Outside deletion scope | Not applicable | Network team |

This table is a planning template, not an instruction to delete live resources.

### Part C: Verify Completion

If tasked with executing cleanup, complete it per the approved plan and record evidence:

- Resource states after operations.
- List of intentionally retained items.
- Verified region and compartment scope.
- Cleanup timestamp.
- Scheduled time to inspect billing data.
- Blockers such as missing permissions, shared dependencies, or data not yet cleared for deletion.

Never report "fully cleaned up" while items remain unchecked.

## 13. Self-Check

### Question 1: Does a budget of 20 guarantee the bill will not exceed 20?

No. Budgets and alerts are not hard billing caps. Data has latency, and resources do not stop automatically just because a rule hits its threshold.

### Question 2: Does a forecasted cost alert mean that amount has already been spent?

Not yet. Forecast is an estimate for the tracking period based on data and service methodology. Inspect actual spend separately.

### Question 3: Is stopping an instance enough to clean up a lab?

No. You must check volumes, backups, databases, load balancers, and other components, and decide whether the instance should be kept or terminated.

### Question 4: Does `--all` in a CLI command mean inventorying the entire tenancy?

No. It handles command pagination within the specified scope. Region, compartment, resource type, and permissions still constrain results.

### Question 5: After deleting resources, if the monthly total stays the same, did cleanup fail?

Not necessarily. Already-incurred costs remain recorded and data can update with delay. Analyze usage timestamps and cost sources.

### Question 6: Can you delete a shared VCN because your instance ran inside it?

No. Distinguish lab-owned resources from borrowed or shared ones. Only touch items within your authorized scope.

### Question 7: Does an `expiresAt` tag automatically delete a resource when the time arrives?

No. Tags only store metadata unless separate automation enforces that policy. Automation also needs permissions, testing, scope controls, and result monitoring.

## 14. Per-Session Lab Checklist

### Before Starting

- [ ] Confirmed billing terms for planned configurations.
- [ ] Clear compartment and region scope.
- [ ] Appropriate budget and alert thresholds configured.
- [ ] Cross-checked recipients and response ownership.
- [ ] End time, owner, and resource inventory established.
- [ ] Separated dedicated resources from shared resources.

### When Ending

- [ ] Stopped jobs capable of writing data or recreating resources.
- [ ] Preserved required outputs and data.
- [ ] Reclaimed resources in dependency order with proper data retention choices.
- [ ] Separately checked volumes, backups, databases, endpoints, and supporting services.
- [ ] Checked all used regions and compartments.
- [ ] Retained items have a documented reason, deadline, and owner.
- [ ] Recorded final states and remaining blockers.
- [ ] Scheduled a follow-up billing check once data updates.

A well-managed lab environment combines early warning signals with a clear shutdown process. Learners should know where charges come from, who responds when projections are exceeded, which resources must be reclaimed, and what evidence proves cleanup is complete.
