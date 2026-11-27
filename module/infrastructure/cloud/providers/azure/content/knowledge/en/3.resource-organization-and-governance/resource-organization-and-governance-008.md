# Azure Policy, Initiatives, and Remediation

Azure Policy is a governance service that helps organizations define and enforce rules on Azure resources. You can use policies to control deployment regions, require tags on resources, audit security configurations, restrict allowed resource types, and detect configurations that do not meet standards.

As the number of subscriptions and resource groups grows, instructing each team manually to follow a set of rules becomes hard to sustain. Azure Policy turns those rules into definitions that can be assigned across scopes, evaluated automatically, and tracked centrally. Within the **CLOUD_PROVIDERS_AZURE** ecosystem, this is a key part of organizing resources, protecting application architectures, and governing Azure environments at scale.

This lesson focuses on three interconnected components:

- **Policy definition** describes a single rule to evaluate.
- **Initiative** (policy set definition) groups multiple related policies into a single standard set.
- **Remediation** executes corrective actions on existing resources when the policy supports that mechanism.

## 1. What Problem Does Azure Policy Solve?

Suppose a company operates development, testing, and production environments across multiple subscriptions. The company wants to:

- Deploy resources only in approved Azure regions.
- Require every resource group and resource to carry `Environment`, `Owner`, and `CostCenter` tags.
- Require storage accounts to enforce secure data transfer.
- Disallow creating certain resource types outside the standard catalog.
- Detect virtual machines or services whose configurations do not meet internal policies.

With manual checks, each team might apply different standards and drift can easily go unnoticed. Azure Policy evaluates resources against assigned definitions, records compliance states, and can block certain resource creation or update requests.

Azure Policy works alongside Azure Resource Manager (ARM). When a resource management request goes through ARM, policies applied at the corresponding scope can evaluate that request. Beyond evaluating during create or update operations, Azure Policy also periodically evaluates existing resources to refresh compliance data.

Azure Policy and Azure role-based access control (Azure RBAC) serve different roles:

| Component | Question the component answers |
|---|---|
| Azure RBAC | Who is allowed to perform which actions on which scope? |
| Azure Policy | Does the resource or change request comply with governance rules? |
| Azure Resource Manager | How is the resource management request received and executed? |

For example, a user with Contributor permissions can still be denied by policy when attempting to create a resource in a disallowed region. RBAC lets the user perform the create action, while policy controls the configuration of that resource.

## 2. Core Concepts

| Concept | Meaning |
|---|---|
| Policy definition | Defines a rule, evaluation condition, and effect to apply |
| Policy assignment | Assigns a policy or initiative to a specific scope and supplies parameter values |
| Initiative / policy set definition | Bundles multiple policy definitions into one standard set |
| Scope | Target boundary where assignment applies, such as management group, subscription, or resource group |
| Exclusion / notScopes | Child scopes excluded from an assignment |
| Exemption | Documented exception with a reason and optional expiration date |
| Compliance state | Compliance evaluation result of a resource against a policy assignment |
| Remediation task | Task to fix existing resources for policies whose effects support remediation |

General workflow:

1. Create or select a policy definition.
2. If there are multiple related rules, group them into an initiative.
3. Create an assignment at the appropriate governance scope and set parameters.
4. Azure Policy evaluates resources, records compliance results, and enforces effects.
5. Investigate non-compliant resources; create a remediation task if the policy can auto-remediate.
6. Monitor results, handle exceptions, and update the standards set over time.

## 3. Policy Definition: Defining the Rule

A policy definition describes the condition to evaluate and the corresponding action. Azure provides Microsoft-authored built-in policies. You can also author custom policies to reflect your organization's specific standards.

A policy definition typically includes these components:

- `displayName`: human-readable name of the rule.
- `description`: explains purpose and scope.
- `mode`: which resource types the policy evaluates.
- `parameters`: values that can vary at assignment time.
- `policyRule`: the `if` expression identifying target resources or requests, and the `then` block specifying the effect.
- `metadata`: categorization, versioning, or governance metadata.

Inside the `if` block, policies use fields and aliases to inspect resource properties. An alias is an Azure-provided path allowing policies to access properties of a resource type. When authoring custom policies, check available aliases for the exact resource provider and API version; not every property in ARM documentation can be used directly as an alias.

### Example: Allow Deployments Only in Approved Regions

The following definition illustrates a policy denying requests to create or update resources whose location is not in the allowed list:

```json
{
  "properties": {
    "displayName": "Allow only approved regions",
    "description": "Denies resources outside the list of allowed Azure regions.",
    "policyType": "Custom",
    "mode": "Indexed",
    "metadata": {
      "category": "Locations"
    },
    "parameters": {
      "allowedLocations": {
        "type": "Array",
        "metadata": {
          "displayName": "Allowed regions",
          "description": "List of Azure regions approved by the organization."
        }
      }
    },
    "policyRule": {
      "if": {
        "field": "location",
        "notIn": "[parameters('allowedLocations')]"
      },
      "then": {
        "effect": "deny"
      }
    }
  }
}
```

In this example:

- `allowedLocations` is an array parameter. Specific values are provided at the assignment step.
- `field: location` reads the resource's deployment location.
- `notIn` checks whether the location falls outside the allowed list.
- The `deny` effect rejects requests that do not satisfy the condition.

This example illustrates policy structure. In production implementations, verify mode, aliases, resource types, and workload exceptions within the target scope.

### Policy Parameters and Assignments

Parameters make a single definition reusable across multiple environments. For example, the same policy can be assigned to a development subscription with two allowed regions and to a production subscription with three approved regions.

Parameter values are passed into the assignment, eliminating the need to create a separate policy definition for each subscription. This keeps rules uniform while allowing per-environment configuration differences.

### Common Effects

The effect determines how Azure Policy handles a request or resource.

| Effect | Behavior |
|---|---|
| `Audit` | Records non-compliant resources without blocking requests |
| `Deny` | Rejects create or update requests that violate the rule |
| `Append` | Adds properties to create or update requests when the property supports this effect |
| `Modify` | Modifies supported properties, commonly used for tags or modifiable aliases |
| `AuditIfNotExists` | Checks for existence of a related resource; flags non-compliance if missing |
| `DeployIfNotExists` | Deploys a related resource when required conditions are not met |
| `Disabled` | Turns off the policy's effect in the corresponding assignment |

Key points to remember:

- `Audit` is well suited when an organization wants to survey current state before enforcing strict rules.
- `Deny` directly impacts deployment workflows. Evaluate workloads before enabling it.
- `Append` and `Modify` do not apply to every property. Modification capability depends on aliases and effect limitations.
- `AuditIfNotExists` and `DeployIfNotExists` are used to inspect or create related resources, such as diagnostic settings, security configurations, or auxiliary components.
- `DeployIfNotExists` and `Modify` may require a managed identity with appropriate Azure RBAC permissions when deploying or remediating.
- `Append` and `Deny` affect create/update requests; they do not automatically fix all pre-existing resources.

You can roll out policies in phases: start with `Audit`, review reports and refine scope; once teams resolve drift, switch to an enforcing effect such as `Deny` where appropriate.

## 4. Assignments and Application Scope

A policy definition only describes a rule. To put the rule into effect in an environment, you must create a policy assignment.

Azure Policy supports these primary governance scopes:

- **Management group:** applies to subscriptions within the management group hierarchy.
- **Subscription:** applies within a single subscription.
- **Resource group:** applies within a resource group and the resources in that scope.
- **Resource:** in supported scenarios, assignments can target an individual resource.

An assignment typically specifies:

- The assigned policy definition or initiative.
- The target scope.
- Parameter values.
- Excluded scopes, if any.
- Enforcement mode.
- Managed identity and identity location when the effect needs to deploy or modify resources.

### Choosing the Right Scope

Suppose a company has three subscriptions: `sub-dev`, `sub-test`, and `sub-prod`. Rules for allowed regions and mandatory tags can be assigned at the management group containing all three subscriptions. A production-only rule can be assigned specifically at `sub-prod`.

Assignments at a parent scope can inherit down to child scopes. Therefore, when investigating a non-compliant resource, inspect both direct and inherited assignments.

### Exclusions and Exemptions

These two mechanisms serve different purposes:

- **Exclusion** (typically configured with `notScopes` on the assignment) removes a child scope from the assignment's evaluation scope. This is a scope-configuration decision.
- **Exemption** creates an auditable exception record for a policy assignment or specific policies within an initiative. An exemption can record a reason, category, and expiration date.

Exemptions are usually better suited when a workload needs a controlled exception. For example, a legacy application cannot yet enable a required encryption setting during a migration phase. The owning team can propose a time-bound exemption with a documented reason and remediation plan.

Avoid excluding an entire subscription just to accommodate one individual resource. Keep exceptions to the smallest possible scope and set a review expiration.

### Enforcement Mode

An assignment can use enforcement mode `DoNotEnforce` to evaluate the policy without enforcing its effect. This mode is useful when testing a new policy or observing impact before enabling enforcement.

When switching to default enforcement, effects like `Deny` can begin blocking new requests. Notify development and operations teams before changing assignments in critical environments.

## 5. Initiatives: Grouping Policies into a Standard Set

An initiative, also called a policy set definition, is a collection of related policy definitions. Instead of creating many scattered assignments, you can assign one initiative to roll out a unified set of standards.

For example, a "Workload security baseline" initiative might contain:

1. Policy requiring storage accounts to use secure transfer.
2. Policy auditing resources for an owner tag.
3. Policy auditing diagnostic settings.
4. Policy restricting deployment regions.
5. Policy auditing virtual machine security configurations.

An initiative contains policy references to identify each member policy. An initiative can also declare shared parameters and map them to child policies. This allows administrators to configure them once at the initiative assignment.

Abbreviated structural example:

```json
{
  "properties": {
    "displayName": "Workload governance baseline",
    "policyType": "Custom",
    "description": "Collection of baseline governance rules for workloads.",
    "metadata": {
      "category": "Governance"
    },
    "parameters": {
      "allowedLocations": {
        "type": "Array",
        "metadata": {
          "displayName": "Allowed regions"
        }
      }
    },
    "policyDefinitions": [
      {
        "policyDefinitionId": "<POLICY_DEFINITION_RESOURCE_ID>",
        "policyDefinitionReferenceId": "approved-locations",
        "parameters": {
          "allowedLocations": {
            "value": "[parameters('allowedLocations')]"
          }
        }
      }
    ]
  }
}
```

This is an abbreviated example showing how an initiative references policy definitions and maps parameters. When creating a complete initiative, each item in `policyDefinitions` must point to a valid policy definition; mapped parameters must be compatible with the referenced definition.

### Benefits of Initiatives

- **Centralized management:** one assignment can deploy multiple rules sharing a common goal.
- **Reusability:** the same initiative can be assigned to multiple subscriptions or management groups.
- **Consistency:** teams share a single standard set and naming structure.
- **Reporting:** compliance status can be viewed by initiative and by individual member policy.
- **Maintainability:** standards sets can be updated via versioning and change governance workflows.

Avoid bundling every policy into a single monolithic initiative. Group them by clear objectives, such as security baseline, tagging standards, cost governance, or workload compliance requirements. Overly large initiatives make permission scoping, phased rollouts, and result analysis harder.

## 6. Remediation: Fixing Non-Compliant Resources

A non-compliant result indicates that a resource violates a rule. It does not mean Azure Policy has automatically fixed the resource.

**Remediation** is the process of applying corrective actions to existing resources. Remediation capability depends on the policy's effect:

- Policies using `DeployIfNotExists` can deploy missing related resources.
- Policies using `Modify` can update supported properties on existing resources.
- Policies using only `Audit` or `Deny` do not automatically modify existing resources. Operations teams must update resources manually per guidance or use a policy with a remediation-capable effect.

### Managed Identity and Required Permissions

For `DeployIfNotExists` or `Modify`, the assignment may require a managed identity to perform changes. That identity must be granted the required Azure RBAC permissions at the scope of the resources to be remediated.

In a policy definition, the effect configuration can declare required role definition IDs. When creating the assignment, the administrator must ensure the managed identity receives the corresponding roles at the appropriate scope. Creating an identity without granting required permissions will cause remediation to fail.

Permission-granting principles:

- Grant only the roles the policy actually requires.
- Limit the scope to the relevant subscription or resource group whenever possible.
- Review both template deployment permissions and target resource modification permissions.
- Verify the assignment's identity and role assignments before running remediation.
- Monitor the identity's permissions as policies or deployment scopes change.

Never use a personal user account as a long-term remediation identity. An assignment-bound managed identity gives automated actions a dedicated identity controllable via Azure RBAC.

### Creating a Remediation Task

A remediation task is typically created after the assignment exists, the policy has evaluated resources, and the managed identity has been granted permissions.

Procedure:

1. Open Azure Policy, go to Compliance, and select the assignment with non-compliant resources.
2. Inspect policy details to confirm the effect supports remediation.
3. Verify the assignment's managed identity and assigned roles.
4. Choose remediation for the corresponding policy or policy reference.
5. Specify the scope and target resources to remediate.
6. Create the remediation task and monitor status along with succeeded or failed resource counts.
7. Re-evaluate compliance to confirm the outcome.

In the Azure Portal, this action is usually performed from the Policy assignment page or compliance details. Menu labels may vary depending on Portal updates and policy types.

Remediation can be managed via Azure CLI. The example below illustrates creating a task at the resource group scope for an existing assignment:

```bash
az policy remediation create --name "remediate-workload" --policy-assignment "<POLICY_ASSIGNMENT_ID>" --resource-group "<RESOURCE_GROUP_NAME>"
```

To view task details:

```bash
az policy remediation show --name "remediate-workload" --resource-group "<RESOURCE_GROUP_NAME>"
```

Replace placeholders with actual assignment IDs and resource group names. The remediation scope must match the assignment's scope and target resources. For assignments at a subscription or management group scope, specify the corresponding scope parameter per the Azure CLI command syntax.

Remediation runs asynchronously and can take time depending on resource count. A failed task does not necessarily mean the policy definition is wrong; the identity may lack permissions, the deployment template may fail, a resource may no longer exist, or the configuration cannot be modified automatically.

### Remediation Does Not Replace Evaluation

After remediation, check the task result and trigger or wait for the next compliance evaluation cycle. Some changes take time to be reflected in Azure Policy.

If resources remain non-compliant:

- Check whether the remediation task failed or skipped resources.
- Inspect detailed errors from the deployment or modification step.
- Verify the identity has the right roles and scope.
- Check policy conditions, aliases, and parameter values.
- Confirm the resource has actually reached the required configuration.

Remediation cannot fix every violation. In some cases, application updates, architectural changes, or controlled manual actions are required.

## 7. Tracking Compliance and Investigating Violations

Azure Policy provides compliance data by assignment and by resource. Statuses tell administrators which rules are satisfied, which are violated, and which cases require further investigation.

Common compliance states:

- **Compliant:** the resource satisfies the policy or evaluation conditions detected no violation.
- **Non-compliant:** the resource violates the policy.
- **Exempt:** the resource has an active valid exemption for the corresponding policy.
- **Conflict:** there is a conflict between policies or applied rules that needs investigation.
- **Not started / Unknown / Error:** results have not been generated yet, are undetermined, or evaluation encountered an error.

Do not treat a missing result as compliant. Check evaluation timestamps, assignment scope, and policy errors before drawing conclusions.

### Viewing Compliance in the Azure Portal

In the Azure Portal:

1. Search for the Policy service.
2. Open the Compliance page for an overview.
3. Filter by subscription, management group, or assignment.
4. Select an assignment to view member policies.
5. Select a non-compliant resource to read the reason and violating property details.
6. Create an exemption or remediation if appropriate under your governance process.

### Viewing Status with Azure CLI

List assignments at a subscription:

```bash
az policy assignment list --scope "/subscriptions/<SUBSCRIPTION_ID>" --output table
```

View recent policy states:

```bash
az policy state list --subscription "<SUBSCRIPTION_ID>" --top 50 --output table
```

Request Azure Policy to trigger a re-evaluation scan on a subscription:

```bash
az policy state trigger-scan --subscription "<SUBSCRIPTION_ID>"
```

Re-evaluation can take time. After triggering a scan, check compliance data once the evaluation updates; do not assume results change instantaneously.

When reporting is needed, filter by assignment, policy definition, resource ID, or time window to identify root causes and accountable teams. In large environments, integrate Azure Policy data with governance and monitoring tools to track violation trends.

## 8. Exemptions and Exception Governance

Not every resource can satisfy every policy immediately. Legacy workloads, compatibility constraints, or technical limitations may require transition time.

Azure Policy supports policy exemptions to record controlled exceptions. Two common exemption categories are:

- **Waiver:** the organization approves waiving policy enforcement for the specified scope.
- **Mitigated:** the policy's intent is already met through an alternative measure or compensating control.

An exemption should include:

- A clear name and description.
- The related policy assignment.
- The smallest necessary scope.
- Exemption category and justification.
- Accountable individual or team.
- Expiration date if the exception is only valid temporarily.
- Evidence or reference to an internal approval decision.

Exemptions do not alter policy definitions and do not grant Azure RBAC permissions. They record that a scope is exempted from evaluation for the configured assignment.

Review exemptions periodically. When an exemption expires or the exception condition no longer applies, remove the exemption and verify that the resource complies with the policy.

## 9. Example Rollout of a Governance Suite

Suppose a platform team needs to apply a baseline to new workloads in a production subscription.

**Objectives**

- Allow only two approved Azure regions.
- Mandate `Owner` and `Environment` tags.
- Require storage accounts to enable secure data transfer.
- Flag resources missing diagnostic settings for operations teams to address.

**Design**

1. Select appropriate built-in policies for storage security and diagnostics.
2. Create custom policies checking mandatory tags and the region list.
3. Group the policies into an initiative named "Production workload baseline".
4. Assign the initiative at the production subscription, passing the region list and tag parameters.
5. Start evaluation rules with `Audit` if baseline discovery is needed.
6. Monitor compliance, notify resource owners, and resolve violations.
7. Switch stabilized rules to `Deny` when ready to block new misconfigurations.
8. For policies deploying diagnostic settings via `DeployIfNotExists`, configure a managed identity and grant required roles.
9. Create remediation tasks for existing resources, then verify deployments and compliance.
10. Document exception cases using exemptions with justification, scope, and expiration.

**Expected outcome**

New workloads are governed right from deployment time; legacy resources are detected and addressed in phases; the platform team can track compliance status by subscription and initiative. Phased rollout minimizes the risk of disrupting running applications.

## 10. Common Issues and Troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| Resource denied during deployment | An assignment uses `Deny` and the request violates conditions | Read the policy error, verify scope and parameters, update config or request an approved exemption |
| Resource stays non-compliant after fix | Evaluation hasn't rerun, policy still sees violating property, or wrong resource fixed | Trigger scan if needed, inspect compliance details, and re-check conditions |
| Remediation task fails | Managed identity lacks role, deployment template fails, or alias does not support modification | Read task/deployment error, inspect role assignments, scope, and policy configuration |
| Member policy in initiative does not behave as expected | Parameters mapped incorrectly or incorrect policy reference | Check initiative parameters, policy reference IDs, and assignment |
| Resource missing from compliance report | Wrong scope, resource out of scope, exclusion, or evaluation incomplete | Check inherited assignments, notScopes, evaluation time, and resource type |
| New policy blocks active workloads | Switched to enforcement effect without assessing impact | Use Audit or DoNotEnforce to evaluate first, plan fixes, and enable enforcement only after verification |

When investigating, start with the effective assignments on the resource, inspect the policy definition and parameters, and then examine remediation or exemptions. This identifies the exact configuration layer causing the issue.

## 11. Hands-On Practice

Perform this exercise in a test subscription where you have administrative permissions:

1. Open Azure Policy and locate a built-in policy checking deployment location or tags.
2. Read the policy definition, identifying the `if` condition, effect, and parameters.
3. Create an assignment on a test resource group or suitable scope.
4. Select an auditing effect like `Audit` or enforcement mode `DoNotEnforce` to observe first.
5. Create or select one compliant resource and one non-compliant resource in the test environment.
6. Open Compliance and determine the status of each resource.
7. Try creating an initiative containing two or more related policies and assign it at a test scope.
8. If a policy uses `DeployIfNotExists` or `Modify`, check managed identity and role requirements; only trigger remediation after verifying permissions and scope.
9. Document the rationale for a hypothetical exception and describe how to create a time-bound exemption.
10. Once finished, delete test assignments or clean up test configurations per your environment's procedures.

**Completion criteria:** you can explain how a policy definition differs from an assignment; understand how initiatives group policies; distinguish exclusions from exemptions; interpret compliance states; and determine when remediation can automatically fix existing resources.

## Conclusion

Azure Policy helps organizations turn governance standards into assignable, evaluable, and trackable rules across Azure. Policy definitions describe individual rules, initiatives bundle rules into standard sets, and assignments determine target scopes and parameters. Compliance shows adherence levels; remediation fixes existing resources when effects and managed identity permissions allow. Combining these components with Azure RBAC, time-bound exemptions, and review workflows helps organizations maintain a consistent, secure, and auditable Azure environment.
