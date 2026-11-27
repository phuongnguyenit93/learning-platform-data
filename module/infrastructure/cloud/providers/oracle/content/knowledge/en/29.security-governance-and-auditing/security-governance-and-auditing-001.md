# Cloud Guard targets, detector recipes, and responder recipes

## 1. Objectives and context

In the **Security, Governance, and Auditing** chapter of the Oracle Cloud Infrastructure (OCI) module, this lesson explains how to define monitoring scope, configure detection rules, and organize responses to security issues. The three central components are **target**, **detector recipe**, and **responder recipe**.

After this lesson, learners will be able to:

- Select targets appropriate for the tenancy and compartment structure.
- Distinguish between detecting risky configurations and detecting notable activities.
- Clone recipes, adjust rules, and attach the right recipes to targets.
- Distinguish between Cloud Guard administration permissions, resource observation permissions, and remediation permissions.
- Practice detecting a public bucket, performing confirmed remediation, and limiting automation.
- Collect evidence to track effectiveness, support auditing, and protect availability.

The overarching scenario is an OCI operations team managing production, development, and security lab environments. The team wants to maintain broad detection coverage while only automatically remediating resources within a verified scope.

## 2. The three components and the path of a problem

| Component | Question to answer | Example in this lesson |
| --- | --- | --- |
| Target | What scope is inspected? | The lab compartment and its child compartments |
| Detector recipe | Which conditions generate a problem? | A rule set inspecting storage configurations |
| Detector rule | Which specific signal should be detected? | A bucket is configured as public |
| Problem | What did Cloud Guard record? | A finding linked to a specific bucket |
| Responder recipe | Which response actions are available? | A rule set for notifications and remediation |
| Responder rule | Which action applies to a matching problem? | Make the bucket private |

Detectors focus on identifying problems; responders define response actions. Not every detector rule has a corresponding direct remediation responder. Available actions depend on the resource type and problem. [Oracle: About OCI Detector Recipes](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/detect-recipes-about.htm), [Oracle: About OCI Responder Recipes](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/respond-recipes-about.htm).

~~~mermaid
flowchart TD
    A["Compartment within target scope"] --> B["Detector recipe and detector rules"]
    B --> C["Problem recorded"]
    C --> D["Responder recipe"]
    D --> E["Cloud Event to forward notifications"]
    D --> F{"Matching remediation rule?"}
    F -->|"Yes: confirmation required"| G["Operator decides"]
    F -->|"Yes: automatic and eligible"| H["Responder executes"]
    F -->|"No"| I["Investigate and handle per runbook"]
    G --> J["Verify resource and save evidence"]
    H --> J
    I --> J
~~~

This diagram is the operational model for this lesson; it does not represent a mandatory ordering across all responder rules. When analyzing a problem, always verify the rule, resource, target, and actual action.

## 3. Target: designing scope by compartment

### 3.1. Target root compartment and inheritance tree

An OCI target selects a compartment to define its monitoring scope. Child compartments fall within that scope, except branches taken over by another target. A compartment is associated with only one effective target at a time. [Oracle: About OCI Targets](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/targets-about.htm).

Design example:

~~~text
Tenancy root                         [target: cg-root]
├── SharedServices                   [cg-root]
├── Production                       [target: cg-production]
│   ├── App                          [cg-production]
│   └── Database                     [cg-production]
└── Development                      [target: cg-development]
    ├── TeamA                        [cg-development]
    └── SecurityLab                  [target: cg-lab]
~~~

In this example, creating `cg-lab` causes the `SecurityLab` branch to use its own target configuration. Do not treat `cg-development` and `cg-lab` as two layers of rules applying simultaneously to a bucket in the lab.

A target at the root has special significance: Oracle requires the root compartment to be a target to monitor IAM policies. If targets are only created on child compartments, evaluate tenancy-level monitoring gaps. [Oracle: Cloud Guard Concepts](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/cg-concepts.htm).

### 3.2. Choosing purposeful boundaries

Split targets when the team needs different behavior by environment, such as requiring operator confirmation in production while allowing automatic remediation of test buckets in the security lab.

Do not create a target just because a new VCN, Compute instance, or database is added. Start with questions about compartment scope, ownership, and the recipe configuration to apply.

Distinguish two pieces of information when using the API or infrastructure tools:

- The compartment that manages Cloud Guard configuration resources.
- The resource compartment that the target monitors.

Do not infer monitoring scope solely from where a recipe is stored or from a target's name. Inspect the target details and the actual compartment tree.

## 4. Detector recipes: detecting configurations and activities

### 4.1. The two fundamental groups

| Group | Focus | Investigative question to ask |
| --- | --- | --- |
| OCI Configuration Detector | Resource configurations that may pose risks | How is the resource currently configured? |
| OCI Activity Detector | Actions on resources that may pose risks | Who performed what activity, and at what time? |

For example, the **Bucket is public** rule of the Configuration Detector alerts on public buckets. The Activity Detector has rules such as **Bastion created**, helping the team review whether a Bastion creation activity was authorized. A finding must be cross-checked against business context before deciding on an action. [Oracle: Detector Recipe Reference](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/detect-recipes.htm).

The standard workflow for creating an OCI target selects one Configuration recipe and one Activity recipe. Oracle also provides additional options such as Threat, Container Security Config, and Instance Security; these should be evaluated based on specific requirements and usage conditions. Do not assume that attaching the two basic recipes covers every workload layer. [Oracle: Creating an OCI Target](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/targets-create.htm).

### 4.2. Reading a detector rule

When preparing to operationalize a rule, create a record with the following information:

| Information | Intended use |
| --- | --- |
| Rule name and identifier | Avoid confusing rules with similar names |
| Detector type and resource type | Identify the data to cross-reference |
| Detection condition | Understand the scenario that generates a problem |
| Risk level | Prioritize handling |
| Input settings, if any | Understand applied thresholds or parameters |
| Conditional group | Identify exceptions and scope limits |
| Recipe and target in use | Trace where the configuration takes effect |
| Remediation owner | Route the problem to the right team |

This is a recommended operational record template, not an API schema.

Risk level serves investigation prioritization. When a bucket is authorized to serve public documents, the team needs to record the business decision and exception conditions; merely lowering the alert level does not change how the bucket is accessed.

## 5. Oracle-managed and user-managed recipes

Oracle provides pre-managed recipes. When deeper changes are needed, users clone them to create a user-managed recipe. For detectors, Oracle-managed recipes do not allow users to disable rules or change risk levels; user-managed recipes allow these adjustments. [Oracle: Editing Rule Settings in an OCI Detector Recipe](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/detect-recipes-modify-rules.htm).

| Need | Appropriate implementation approach |
| --- | --- |
| Start with Oracle's baseline | View and use the Oracle-managed recipe |
| Change a detector rule's status or risk level | Clone the detector recipe, then edit the rule |
| Disable an unsuitable responder rule | Use a user-managed responder recipe |
| Adjust scope for only one environment | Check the rule configuration in the corresponding target |

Cloning creates a new configuration copy; that copy must be attached to the target that needs to use it. For detectors, you can clone from an Oracle-managed or user-managed recipe within the same tenancy. [Oracle: Cloning an OCI Detector Recipe](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/detect-recipes-clone.htm).

Similarly, clone a responder recipe from the set closest to your needs, then adjust the configuration of the new copy. Give it a purposeful name, such as `cg-lab-responder-v1`, and record the owner along with the reason for the change. [Oracle: Cloning an OCI Responder Recipe](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/respond-recipes-clone.htm).

A user-managed recipe still receives rule updates from the Oracle-managed source; newly added rules are placed in the clone in a disabled state according to Oracle documentation. Therefore, the team needs a schedule to review new rules and decide whether to enable them. [Oracle: Some Common Features](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/common.htm).

A clone is not a permanently frozen snapshot. The change record should document the source recipe identifier, the actively modified rules, and the most recent review date.

## 6. Editing at the recipe level or target level?

### 6.1. Distinguishing where to edit

Recipes can be reused. Before editing, check the targets attached to that recipe; a baseline change can affect multiple environments.

For detector rules in standard OCI targets, Oracle's operational documentation states that the configuration edited at the target level is the **Conditional group**. To change other attributes, go through the appropriate recipe management section. Security Zone targets have a separate mechanism and are outside the scope of this lab. [Oracle: Editing Detector Rule Settings in an OCI Target's Recipes](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/targets-modify-rules-detect.htm).

For responders, enabling/disabling rules is performed at the recipe level and only for user-managed recipes. Settings such as execution mode and applicability conditions are edited from the rule of the recipe attached to the target. [Oracle: Editing Responder Rule Settings in an OCI Target's Recipes](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/targets-modify-rules-respond.htm).

Decision examples:

| Desired change | Starting point |
| --- | --- |
| Disable a detector rule in a custom baseline | Detector recipes → user-managed recipe → rule |
| Change the risk level of a detector rule | Detector recipes → user-managed recipe → rule |
| Set an exception for a detector in the lab | Targets → lab target → detector rule |
| Disable a responder rule in a custom copy | Responder recipes → user-managed recipe → rule |
| Choose automatic or confirmation required | Targets → corresponding target → responder rule |

### 6.2. Conditions and exceptions

A conditional group restricts where a rule applies. Conditions combined within a group use the AND operator. Conditions at the recipe level can serve as defaults when attached to a new target; check the individual configuration of existing targets. [Oracle: Some Common Features](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/common.htm).

Example internal policy proposed by this lesson:

~~~text
Detection:
    Keep the rule detecting public buckets within the lab scope.

Automatic remediation:
    Apply only in the region selected for the lab
    AND only for resources with an approved identifier,
    if the rule supports the corresponding filter parameter.
~~~

This is a statement of intent, not an expression to paste into the API. When configuring, select the exact Parameter, Operator, and Value supported by the rule; if the desired scope cannot be expressed, keep confirmation mode enabled.

An exception must have an owner, reason, scope, and expiration date. If tags are used as conditions, tag assignment permissions must also be reviewed: anyone able to change tags can alter which resources the responder acts upon.

## 7. Responder recipes: actions and execution conditions

### 7.1. Choosing actions based on impact

Examples provided by Oracle include:

| Responder | Action | Points to evaluate before use |
| --- | --- | --- |
| Make Bucket Private | Change a public bucket to private | Impact on users accessing public content |
| Enable DB Backup | Enable automatic backup for an eligible database | Backup window, retention period, and storage capacity |
| Stop Compute Instance | Stop a Compute instance | Service availability and application dependencies |
| Cloud Event | Emit problem details to Events | Notification routing and recipients |

The list above illustrates available responders; you must check which detector a rule applies to and the required parameters of that specific rule. [Oracle: Responder Recipe Reference](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/respond-recipes-reference.htm).

For production systems, evaluate impact using a concrete scenario: if an instance is stopped, will the service still have enough replicas and will database connections be maintained? Automation decisions must be grounded in application resilience.

### 7.2. Confirmation required and automatic

**Ask me before executing rule** reserves execution decisions for the operator. **Execute automatically** allows the rule to execute when configuration conditions match.

When configuring automatic execution for a remediation responder rule, Oracle requires confirming the choice and having at least one condition. Use conditions that express the approved scope, rather than an always-true condition to bypass the restriction. [Oracle: Editing Responder Rule Settings in an OCI Target's Recipes](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/targets-modify-rules-respond.htm).

A selection rule proposed by this lesson:

~~~text
Allow automatic execution only when:
    The exact action is understood
    AND the scope is defined
    AND it has been verified with test resources
    AND an owner is assigned
    AND a rollback or handling plan exists if the action causes unintended impact.
~~~

If any condition is not met, continue operating in confirmation-required mode to accumulate evidence.

### 7.3. Administrative permissions and service permissions

Separate three layers of permissions:

1. **Operators managing Cloud Guard:** view problems, edit recipes, configure targets, or perform assigned tasks.
2. **Cloud Guard service observation:** prerequisite policies allowing the service to collect necessary information.
3. **Cloud Guard service remediation:** additional policies for actions that modify resources.

Example read permissions for an audit group:

~~~text
Allow group CloudGuardReaders to read cloud-guard-family in tenancy
Allow group CloudGuardReaders to read compartments in tenancy
~~~

These two statements illustrate permissions to view data and configurations. The group name must exist in the tenancy; adjust the identity domain syntax if the group belongs to a different domain. [Oracle: Prerequisites](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/prerequisites.htm), [Oracle: Cloud Guard Policies](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/policies.htm).

For `Make Bucket Private`, an example service permission restricted to the lab compartment is:

~~~text
Allow service cloudguard to manage buckets in compartment SecurityLab
~~~

`SecurityLab` is an illustrative name and must be replaced with the actual compartment. Only add remediation policies corresponding to the chosen action; check the rule's **Required policy statements** list. Having permission to configure recipes does not automatically mean the service has permission to modify buckets. [Oracle: Policy Statements for OCI Responders](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/respond-recipes-about.htm#PolicyStatements).

## 8. Reporting region and initial setup

The reporting region is an important Cloud Guard configuration point and does not automatically match the OCI home region. Cloud Guard create, update, and delete operations must be sent to the reporting region; read operations are supported from other regions. [Oracle: Cloud Guard CLI](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/cloud-guard.html).

Before the lab, confirm:

- The tenancy has Cloud Guard active and the required prerequisite policies in place.
- The correct reporting region is recorded in tool configurations.
- The lab account has permissions on the targets and recipes to be manipulated.
- The target currently managing the lab compartment branch has been identified.
- The lab does not contain production business data or shared resources.

Oracle's onboarding documentation states that changing the reporting region requires disabling and re-enabling Cloud Guard, and disabling removes existing customizations and problem history. Therefore, do not use this operation to troubleshoot configuration or notification issues in an active environment. [Oracle: Getting Started with Cloud Guard](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/part-start.htm).

Resource changes and problem appearances may not be simultaneous. In the lab, record the timestamp of the change, wait for data to update, and verify the configuration chain before concluding that the detector is not working.

## 9. Designing baselines across environments

The following table is an illustrative plan, not an Oracle default:

| Target | Scope | Detector baseline | Initial handling approach |
| --- | --- | --- | --- |
| `cg-root` | Root and branches without a dedicated target | Tenancy-level baseline | Investigate, confirmation required |
| `cg-production` | Production | Baseline controlled by the security team | Confirmation required for resource changes |
| `cg-development` | Development, excluding the dedicated lab branch | Development baseline | Notify and handle by owner |
| `cg-lab` | SecurityLab | Cloned copy for lab use | Confirmation required initially; then test conditional automation |

The design document should specify which recipe each target uses. If two environments need different rule enable/disable states, select appropriate user-managed copies; merely splitting target names while sharing the same baseline will not necessarily achieve the desired differentiation.

When changing a recipe on an OCI target, note that only one recipe of each type can be attached at a time; adding a replacement of the same type may require detaching the currently attached one. Sequence the changes and verify the association afterward to minimize monitoring gaps. [Oracle: Editing an OCI Target and Its Attached Recipes](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/targets-modify.htm).

## 10. Hands-on lab: detecting and remediating a public bucket

This lab uses the OCI Console and an empty bucket in a test compartment. The steps below are instructions for learners to follow; they are not execution output from a live tenancy.

### Step 1 — Prepare the scope and tracking table

Choose a lab compartment where you have permissions to operate, such as `SecurityLab`. If the compartment belongs to another target, record the current configuration before creating a dedicated target.

Create a tracking table:

| Field | Value to record |
| --- | --- |
| Reporting region | Actual Cloud Guard region |
| Lab compartment | Name and OCID |
| Target | Name and OCID |
| Configuration, Activity recipes | Source OCIDs and cloned copies if applicable |
| Responder recipe | OCID and remediation rule mode |
| Bucket | Name, OCID, region |
| Owner | Learner or on-call operator |

Do not place secrets, personal information, or customer data in resource names and descriptions.

### Step 2 — Clone and attach recipes

In **Cloud Guard → Recipes**, create the copies for the lab:

- Configuration recipe: `cg-lab-config-v1`.
- Activity recipe: `cg-lab-activity-v1` if a separate baseline is needed.
- Responder recipe: `cg-lab-responder-v1`.

In **Configuration → Targets**, create or edit the `cg-lab` target for the selected compartment. Attach the appropriate Configuration recipe and Activity recipe, then attach the lab responder recipe.

For the Configuration recipe, confirm the **Bucket is public** rule is enabled and check the rule's conditions in the target. For the lab responder, keep **Make Bucket Private** in confirmation-required mode. Review other rules that modify resources before continuing.

The completion milestone for this step is seeing the correct recipe OCIDs in the target details. Seeing a recipe appear in the global list is not sufficient proof that it is being used.

### Step 3 — Create a controlled detection scenario

Create an empty bucket in the recorded compartment and region. Confirm the bucket is private, then change its visibility to public to create the test scenario. Do not upload real data into the bucket.

In Cloud Guard, locate the problem corresponding to the bucket. Cross-check:

- Resource OCID and region.
- Effective target.
- Detector and rule.
- Detection timestamp, risk level, and recommendation.

Record the time visibility was changed and the time the problem was observed. If it has not appeared yet, check filters, target scope, recipes attached to the target, rule status, and prerequisite policies.

### Step 4 — Execute the responder after confirmation

Open the problem or **Responder activity** and view the pending **Make Bucket Private** action. Read the impact and confirm execution for the test bucket.

If needed, add the service policy with the proper scope. After execution, check the responder status and open Object Storage to confirm the bucket's actual visibility is now private.

The Responder activity page can display statuses such as **Awaiting confirmation**, **Failed**, **Skipped**, and **Succeeded**. When it fails, inspect the details to distinguish missing permissions from an unavailable resource. [Oracle: Listing Responder Rule Actions and Getting the Details](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/respond-dash-work.htm).

Lab evidence must include both the responder activity and the bucket state; merely changing the status of the problem record does not prove the resource was remediated.

### Step 5 — Test automation within the lab scope

After verifying confirmation-required mode:

1. Open the **Make Bucket Private** rule from the responder recipe in the lab target.
2. Select automatic execution and confirm the choice.
3. Set a conditional group expressing the lab scope using parameters supported by the rule.
4. Verify the remediation policy remains restricted to the right compartment.
5. Use another test bucket to generate a new finding.
6. Cross-check the automatic action and final visibility.

Using a new bucket separates the automation test from the previous problem record. Do not assume that changing the trigger will immediately re-run an old problem.

Store together the applied condition, bucket OCID, detection timestamp, and responder result. If scope restriction capability cannot be verified, revert to confirmation-required mode before proceeding.

### Step 6 — Revert and conclude the lab

Switch the test buckets back to private, delete lab resources that do not need to be retained, and return rules to the mode agreed upon with the environment manager.

Review policies added solely for the lab; revoke them when no longer needed and after verifying they do not serve other workflows. If the lab modified an existing target's configuration, restore it according to the pre-change record and confirm the final monitoring scope.

Do not disable Cloud Guard tenancy-wide just to clean up a practice lab.

## 11. Forwarding notifications via Cloud Event, Events, and Notifications

The Cloud Event responder emits problem details to Events. To receive notifications, attach the responder recipe to the target and verify that the Cloud Event rule is enabled and executing automatically. The Events and Notifications services for this flow are configured in the reporting region. [Oracle: Configuring Notifications](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/export-notifs-config.htm).

~~~text
Problem
  → Cloud Event responder
  → Events rule in the reporting region
  → Notifications topic
  → Confirmed subscription
~~~

In the lab, select event type `com.oraclecloud.cloudguard.problemdetected` to test the notification route. Send it to a Notifications topic of the lab team and complete subscription confirmation if using email. [Oracle: Configuring Notifications](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/export-notifs-config.htm).

Then test stage by stage: a problem exists, a matching responder exists, the Events rule matches, and the subscription receives the notification.

Detection notifications and post-remediation notifications serve two different purposes. Internal message designs should clearly state whether a message is a request for investigation or evidence of a completed action.

## 12. Reading configuration with OCI CLI on PowerShell

The commands below are query-only. OCI CLI must be installed, authentication configured, and `<...>` placeholders replaced with actual OCIDs and regions.

### 12.1. Listing targets in the tenancy tree

~~~powershell
$tenancyOcid = '<TENANCY_OCID>'
$reportingRegion = '<CLOUD_GUARD_REPORTING_REGION>'

oci cloud-guard target list --compartment-id $tenancyOcid --compartment-id-in-subtree true --access-level ACCESSIBLE --all --region $reportingRegion
~~~

`--compartment-id-in-subtree true` requests traversing the compartment tree; `--all` retrieves all pages. With `ACCESSIBLE`, results depend on the caller's permission scope, so a list with few entries is not enough to conclude that other targets do not exist. [Oracle CLI: target list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/cloud-guard/target/list.html).

### 12.2. Checking recipes actually attached to a target

~~~powershell
$targetOcid = '<TARGET_OCID>'
$targetCompartmentOcid = '<TARGET_COMPARTMENT_OCID>'

oci cloud-guard target-detector-recipe list --compartment-id $targetCompartmentOcid --target-id $targetOcid --all --region $reportingRegion

oci cloud-guard target-responder-recipe list --compartment-id $targetCompartmentOcid --target-id $targetOcid --all --region $reportingRegion
~~~

Use the compartment containing the target according to its management details. These two queries help cross-check detector/responder associations rather than just searching for recipes by name. [Oracle CLI: target-detector-recipe list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/cloud-guard/target-detector-recipe/list.html), [Oracle CLI: target-responder-recipe list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/cloud-guard/target-responder-recipe/list.html).

### 12.3. Getting problem details

~~~powershell
$problemOcid = '<PROBLEM_OCID>'

oci cloud-guard problem get --problem-id $problemOcid --region $reportingRegion
~~~

This command retrieves a problem by identifier, which is useful when handing off investigations between teams. When saving results for auditing, control read access because resource details may contain internal information. [Oracle CLI: problem get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/cloud-guard/problem/get.html).

Do not schedule write commands automatically just because read commands ran successfully. Any workflow that modifies recipes or targets requires separate verification of identifiers, impact scope, and rollback plans.

## 13. Operations, auditing, and effectiveness tracking

### 13.1. Change record

For each Cloud Guard change, store:

| Evidence group | Contents |
| --- | --- |
| Scope | Target OCID, compartment tree, and environment |
| Baseline | Recipe OCID, source recipe, modified rules |
| Exceptions | Conditions, reason, approver, and expiration date |
| Permissions | Added policies, purpose, and scope |
| Execution | Problem OCID, responder, timestamp, and outcome |
| Verification | Resource state after the action |
| Rollback | Pre-change configuration and responsible owner |

This is a recommended organizational record. During investigations, cross-check with OCI Audit and the change management system to determine who changed the configuration or resource and whether that change was approved.

Do not use a single overview screenshot as the sole evidence of monitoring scope. The target, recipe, and rule associated with the exact resource being audited must be visible.

### 13.2. Team-defined operational metrics

Operational metrics can include:

- Number of critical compartments with confirmed targets and baselines.
- Time from problem appearance to acknowledgment.
- Time from acknowledgment to resource remediation.
- Responder success rate across eligible executions.
- Number of expired exceptions.
- Number of new rules in cloned copies not yet reviewed.
- Number of recurring problems caused by re-deployed infrastructure configurations.

When calculating rates, state the denominator and time window clearly. For example, do not mix pending approvals with executions that ran and failed.

If a bucket frequently reverts to public after a responder fixes it, inspect the configuration source such as Terraform or the application deployment pipeline. Fixing the configuration source prevents a detection-and-remediation loop.

## 14. Diagnosing common scenarios

This table is a recommended investigation sequence:

| Symptom | First point to check | Next action |
| --- | --- | --- |
| Cloned recipe, but behavior unchanged | Recipe OCID attached in the target | Attach the right copy and verify effective configuration |
| Child compartment uses an unexpected baseline | Whether a dedicated target exists in the branch | Reconcile the target tree |
| Bucket problem not visible | Scope, filters, rule status, and change timestamp | Check prerequisite policies and wait for data update |
| Desired remediation action unavailable | Responder recipe, rule, and applicability | Cross-check detector–responder mapping in rule docs |
| Responder awaiting confirmation | Rule trigger | Responsible owner decides on execution |
| Responder failed | Execution details and service permissions | Fix the root cause; avoid opening tenancy-wide permissions to test |
| Email not received | Cloud Event, reporting region, Events rule, and subscription | Check stage by stage |
| Too many findings | Resource context and existing exceptions | Narrow down with time-bound exceptions |
| Baseline edit affects other environments | Targets sharing the recipe | Roll back and split baselines if needed |
| Fewer CLI results than admin Console | Permissions and subtree query parameters | Cross-check with an appropriately privileged user |

When an incident is unclear, preserve the problem and execution history before making further edits. Changing targets, rules, policies, and notifications simultaneously makes root-cause identification difficult.

## 15. Cost and availability in response design

In the lab plan, account for accompanying resource usage: test buckets, retained data and logs, notification routes, and services incurred by remediation actions. Check pricing tables and Cost Analysis for the account in use before expanding the lab.

For responders that enable database backups, the team must align the backup window and retention period with the database administrator. For actions that stop instances or switch buckets to private, verify access flows and availability requirements before allowing automatic execution.

A rollout roadmap proposed by this lesson:

1. Start with detection and forward notifications to responsible owners.
2. Perform confirmed remediation in a test environment.
3. Measure outcomes and document exception cases.
4. Enable automatic execution for verified actions, targets, and conditions.
5. Expand scope incrementally and continue reviewing recipes and service permissions.

The desired outcome is an explainable configuration: which target each resource belongs to, which rule detected the issue, who decided on the handling, and what evidence demonstrates the post-remediation state.
