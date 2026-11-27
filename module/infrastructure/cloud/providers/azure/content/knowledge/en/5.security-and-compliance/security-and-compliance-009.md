# Building a Security Baseline with Azure Policy

## 1. Why Do We Need a Security Baseline?

When operating multiple subscriptions, resource groups, virtual networks, virtual machines, storage accounts, and data services on Microsoft Azure, each team might create resources differently. One team enables public Internet access on a data service, another forgets to configure logging, and some resources lack ownership metadata. The system may still run fine, yet risk exposure and manual auditing costs escalate rapidly.

A **security baseline** is the minimum set of requirements a resource or environment must satisfy. A baseline must be expressed as verifiable rules with clear accountability. For example:

- Production resources may only be deployed in approved regions.
- Resources must carry tags identifying environment and owner.
- Storage accounts must enforce secure data transfer settings.
- Sensitive data services must not expose public access without an approved exception.
- Critical resources must send diagnostic logs to a centralized destination.
- Non-compliant items must have an owner, a deadline, and risk-acceptance evidence if exempted.

**Azure Policy** is a governance service used to define, assign, and evaluate rules against resources managed through Azure Resource Manager (ARM). Where appropriate, Azure Policy can also block non-compliant configuration requests or help remediate drifted settings.

The goal of this lesson is to move from security requirements to a deployable, verifiable, and operable baseline on Azure, rather than creating isolated standalone policies.

## 2. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish Azure Policy from Azure RBAC and Microsoft Defender for Cloud.
2. Explain policy definitions, initiatives, assignments, scopes, parameters, effects, compliance, and exemptions.
3. Design a baseline organized by control groups, prioritizing appropriate built-in policies.
4. Plan rollouts from audit mode to blocking violations without disrupting valid workloads.
5. Author and read a policy definition that checks tags.
6. Understand when remediation tasks, managed identities, and RBAC permissions are required.
7. Monitor compliance states, handle exceptions, and maintain the baseline over time.

## 3. What Do Azure Policy, RBAC, and Defender for Cloud Address?

These three mechanisms complement each other but do not perform the same job.

| Service | Primary Question | Example |
|---|---|---|
| **Azure RBAC** | Who is allowed to perform which actions at which scope? | Deployment team holds Contributor permissions on a resource group |
| **Azure Policy** | How are resources allowed to be configured, and do current settings meet rules? | Block creating resources in regions outside the approved list |
| **Microsoft Defender for Cloud** | Which security findings, recommendations, and risks exist in the environment? | Assess security posture and surface remediation recommendations |

For instance, RBAC allows an engineer to create a storage account in a resource group. Azure Policy can reject a storage account creation request that violates configuration standards. Defender for Cloud can surface security recommendations related to that resource or environment.

Azure Policy also does not replace Microsoft Entra Conditional Access policies, application controls, anti-malware scanning, vulnerability management, or real-time log analytics. When building a baseline, only place controls in Azure Policy that fall within what this service can actually evaluate or enforce.

## 4. Components of Azure Policy

| Component | Meaning | Example |
|---|---|---|
| **Policy definition** | Defines a rule, conditions, and outcome when conditions match | Audit resources missing the `environment` tag |
| **Policy rule** | The `if` condition logic and `then` action | If tag does not exist, then audit |
| **Effect** | How Azure Policy responds to matching resources | Audit, Deny, Modify, DeployIfNotExists |
| **Parameter** | Input value passed at assignment time to reuse a definition | List of allowed regions |
| **Initiative / policy set definition** | Groups multiple policy definitions into one control set | Production subscription baseline |
| **Assignment** | Applies a policy or initiative at a scope with specific parameter values | Assign baseline to the production management group |
| **Scope** | Position in the Azure management hierarchy where the assignment applies | Management group, subscription, resource group |
| **Compliance state** | Evaluation result comparing resources against the rule | Compliant, Non-compliant, or other states |
| **Remediation task** | Task updating existing non-compliant resources for remediation-capable effects | Deploy missing diagnostic settings |
| **Exemption** | Waives compliance evaluation under a governed exception | Time-bound exception for a legacy service |

Conceptual relationships:

~~~mermaid
flowchart TD
    A[Security Requirements] --> B[Policy Definitions]
    B --> C[Initiative: Security Baseline]
    C --> D[Assignment at Scope]
    E[Parameters] --> D
    D --> F[Azure Resources in Scope]
    F --> G[Policy Evaluation]
    G --> H[Compliance State]
    G --> I[Rule Effects]
    I --> J[Deny, Audit, or Remediate]
    H --> K[Reporting and Review]
    K --> L[Adjust Baseline and Exemptions]
~~~

A **definition** describes the rule; an **assignment** actually applies the rule to a specific environment. One definition can be assigned multiple times with different scopes and parameters. An initiative helps manage many definitions as a consistent baseline package.

## 5. Scope, Inheritance, and Exclusions

Azure organizes resources under a standard management hierarchy:

~~~text
Tenant
└── Management group
    └── Subscription
        └── Resource group
            └── Resource
~~~

Assignments at a management group generally inherit down to underlying subscriptions and resource groups. Assignments at a subscription generally apply to matching resources inside that subscription. Policies can be assigned at narrower scopes when justified by differing requirements.

For example: an enterprise maintains a shared production management group and assigns a baseline initiative there. New production subscriptions placed under that branch inherit the assignment's effects, subject to any configured exclusions or exemptions.

Distinguish three mechanisms:

- **Scope** defines where an assignment begins applying.
- **Exclusion / notScopes** removes one or more child scopes from an assignment. Resources in excluded scopes are not normally evaluated by that assignment.
- **Policy exemption** is a documented exception against an assignment, carrying a reason, category, and optional expiration. It enables governance over an accepted, controlled deviation.

Never use exclusions casually to hide violations. When a team needs an exception, record the resource, reason, approver, compensating controls, and review date.

**Access control note:** Azure RBAC controls who can create definitions and assignments, who can edit resources, and who can run remediation. Azure Policy does not automatically grant all permissions needed to modify resources.

## 6. Understanding Effects Before Choosing

Each definition specifies an effect determining how Azure Policy reacts when the `policyRule` condition matches.

| Effect | General Behavior | When Appropriate |
|---|---|---|
| **Audit** | Flags non-compliant configurations without blocking create/update requests due to this effect | Discovery and monitoring phase |
| **Deny** | Rejects ARM operations matching the violation condition when enforced | Prevent new out-of-standard configurations |
| **Disabled** | Does not evaluate or enforce that definition's effect logic | Intentionally disabling a rule in a controlled way |
| **Append** | Adds specified fields to resource requests where supported | Adding properties in certain supported cases |
| **Modify** | Mutates certain request properties/tags; can support remediating existing resources | Standardizing tags or supported settings |
| **AuditIfNotExists** | Evaluates existence or state of related resources | Detecting missing diagnostic configurations |
| **DeployIfNotExists** | When conditions match, deploys related resources if missing per rule | Assisting rollout of missing diagnostic settings |

Additional effects and usage patterns may be introduced by Azure over time. Not every effect works with every resource type or property; always verify the policy definition and corresponding aliases.

### 6.1. Audit First, Deny Later

If an organization already runs thousands of resources, jumping straight to Deny can break active deployments. A safer rollout path is:

1. Evaluate using Audit or configure the assignment with an appropriate observation enforcement mode.
2. Review violation counts and root causes.
3. Triage existing resources, business needs, and genuine exceptions.
4. Refine scope, parameters, deployment pipelines, or standardize configurations.
5. Pilot blocking rules in a small environment.
6. Enable enforcement in production after assessing impact.

**Deny does not automatically delete or fix pre-existing resources.** Legacy resources may still be flagged non-compliant, while new create/update operations violating the rule will be blocked.

### 6.2. Modify and DeployIfNotExists Require Extra Operational Steps

The **Modify** and **DeployIfNotExists** effects can involve the policy assignment's managed identity and role assignments holding sufficient rights on target resources. Required permissions are typically declared via `roleDefinitionIds` inside the policy details; operations teams must configure appropriate roles and scopes, preferring least privilege.

For **existing resources**, creating an assignment does not immediately fix old configurations. You typically need to run a **remediation task** to update eligible non-compliant resources. Monitor task results and verify actual resource changes. Deploying diagnostic settings also depends on the log destination, supported resource types, and required permissions.

### 6.3. Enforcement Mode vs. Effect

An assignment carries an **enforcement mode** setting. In certain scenarios, **DoNotEnforce** allows compliance evaluation without enforcing effect actions controlled by that mode. **Default** applies enforcement according to policy configuration.

Do not equate **DoNotEnforce** with **Disabled**. One belongs to the assignment; the other is an effect in the definition. Both have distinct implications for evaluation, deployment, and reporting.

## 7. Translating Security Requirements into a Measurable Baseline

A strong baseline starts from risk and business requirements. Each control should answer: which resource types it covers, what constitutes passing, how violations are detected, who remediates, and how exceptions are governed.

Example minimal baseline for applications running across Azure subscriptions:

| ID | Control | Expected Evaluation Method | Suggested Scope |
|---|---|---|---|
| SEC-01 | Deploy resources only in approved regions | Allowed locations, phased enforcement | Production subscriptions |
| SEC-02 | Resources have `environment`, `owner`, and `costCenter` tags where supported | Appropriate tag audit/modify policy | Resource groups and taggable resources |
| SEC-03 | Storage accounts require secure transfer and appropriate TLS settings | Built-in HTTPS/TLS policies, feature/SKU checks | Storage accounts |
| SEC-04 | Restrict public network access for sensitive data services | Public network access policies by service type | Designated databases and storage |
| SEC-05 | Enable diagnostic settings per operational standards | AuditIfNotExists, DeployIfNotExists where supported | Services supporting diagnostics |
| SEC-06 | Restrict unapproved configurations or SKUs | Allowed resource types/SKUs policies where suitable | Environments with strict security bounds |

The rows above are **design examples**, not proof that every built-in policy exists or supports every resource type at deployment time. Always look up exact policy definitions, parameters, modes, effects, versions, and support scopes.

Also recognize limitations: a policy requiring a tag does not guarantee the tag value is accurate; a policy checking that logging is enabled does not guarantee logs are retained long enough; requiring HTTPS does not replace identity checks, secrets management, and data authorization.

## 8. Prioritizing Built-in Policies and Creating Initiatives

Azure offers numerous **built-in policy definitions** and **built-in initiatives**. They are a practical starting point because common rules are pre-packaged. However, you still must evaluate whether a policy fits your environment, services, and internal standards.

Selection workflow:

1. Go to **Azure Portal → Policy → Definitions**.
2. Filter by **Built-in** type, category, or control keywords.
3. Open a definition and read its description, policy rule, mode, parameters, supported effects, and limitations.
4. Map against requirements SEC-01 through SEC-06; record the `policyDefinitionId` chosen for each control.
5. If no built-in fits, consider a **Custom** definition with clear scope and conditions.
6. Create an **initiative** bundling the corresponding definitions into a named, versioned baseline with a clear purpose description.
7. Set parameters at the initiative or assignment level per environment, such as allowed location lists and required tag names.

Purpose-driven naming examples:

- **baseline-prod-security-v1**: control set applied to production.
- **baseline-dev-security-v1**: variant with tailored parameters or requirements for development.
- **SEC-01-allowed-locations**: internal control ID mapped to the selected definition.

Internal control IDs are defined by the organization for lifecycle tracking, not Microsoft built-in identifiers. Maintain a mapping from control ID to policy definition, owner, version, and rationale to avoid confusion when built-in policies evolve.

## 9. Example Custom Policy Definition: Auditing the Environment Tag

To understand the basic structure, below is a JSON policy definition usable as a starting point when customization is required. Goal: detect taggable resources missing the **environment** tag.

~~~json
{
  "properties": {
    "displayName": "Audit resources without environment tag",
    "description": "Mark taggable resources without the required environment tag.",
    "policyType": "Custom",
    "mode": "Indexed",
    "parameters": {
      "tagName": {
        "type": "String",
        "metadata": {
          "displayName": "Required tag name"
        },
        "defaultValue": "environment"
      }
    },
    "policyRule": {
      "if": {
        "field": "[concat('tags[', parameters('tagName'), ']')]",
        "exists": "false"
      },
      "then": {
        "effect": "audit"
      }
    }
  }
}
~~~

Section-by-section explanation:

- **properties** holds metadata and definition components.
- **policyType: Custom** indicates an organization-defined policy.
- **mode: Indexed** targets resource types supporting tags and locations via the Index mechanism; it is not a universal check across all resource types.
- **parameters.tagName** allows changing the tag name without rewriting rule logic.
- **field** uses a Policy expression to inspect the tag named by the parameter.
- **exists: false** matches resources missing the checked tag.
- **effect: audit** marks violations; it neither adds the tag automatically nor rejects resource creation.

**Limitations of this example:** this policy checks only *existence* of the tag, not whether the value is valid or non-empty. Requiring values from an approved list or explicitly covering resource groups requires tailored rules and verifying modes/aliases. Never assign this sample enterprise-wide and treat it as a complete security baseline.

In the Portal, when creating a custom policy definition, the editor may expect JSON structured slightly differently by the UI wrapper. Check which fields the UI manages separately before pasting the entire block containing **properties**.

## 10. Assigning an Initiative to a Scope and Configuring Parameters

Once the **baseline-prod-security-v1** initiative is ready, admins can apply it to a test subscription first, then expand to the production management group after verifying behavior.

In **Azure Portal → Policy → Assignments → Assign policy**:

1. Select the appropriate **Scope**, such as a test subscription.
2. Choose the **Policy definition / initiative** to apply.
3. Give the assignment a name and description that distinguish baseline versions.
4. Review **Exclusions**; exclude child scopes only with clear justification.
5. Configure **Parameters** such as allowed locations, tag names, or effects if supported by the definition.
6. Consider **Enforcement mode** during the discovery phase.
7. If the initiative includes **Modify** or **DeployIfNotExists**, configure a managed identity and role assignments per instructions.
8. Inspect the Review tab, confirm scope/parameters/validity, and create the assignment.
9. Monitor compliance results after evaluation runs.

For example, the same initiative can accept different allowed locations between development and production. When managing via IaC, store parameter values explicitly in configuration code rather than re-entering them manually.

**Inheritance warning:** assignments on a management group can impact many child subscriptions beneath it. Before enabling Deny at a high scope, inventory all application teams and test their deployment pipelines.

## 11. Inspecting Compliance Results

After an assignment is created, Azure Policy evaluates matching resources per service mechanics. Compliance data does not necessarily update instantaneously; resource creates/updates, assignment edits, or periodic evaluation cycles trigger re-evaluation.

In **Azure Portal → Policy → Compliance**, you can:

1. Select the scope and assignment/initiative.
2. View summary counts of compliant and non-compliant resources.
3. Open a specific policy to inspect non-compliant resources.
4. View reasons, conditions, and relevant properties where available.
5. Identify owning teams and create remediation plans.
6. Re-evaluate after remediation or updated scans.

Possible statuses include **Compliant**, **Non-compliant**, **Exempt**, **Conflicting**, **Not started**, **Not registered**, or similar statuses depending on scenario and UI. Not every resource always has an evaluation result; scope, policy type, existence conditions, latency, and indexed data can all affect results.

A baseline summary report may look like:

| Control | Evaluated Resources | Non-Compliant | Remediation Owner | Target Due Date |
|---|---:|---:|---|---|
| SEC-01 Region | 120 | 3 | Cloud Platform | Based on priority |
| SEC-02 Tag | 120 | 18 | Respective app teams | Per standardization plan |
| SEC-03 HTTPS/TLS | 28 | 2 | Storage Team | Based on risk level |
| SEC-05 Diagnostic settings | 35 | 7 | Observability Team | Per logging rollout plan |

The numbers above are illustrative only. When compiling real reports, record scope, export timestamp, active filters, initiative version, and active exemptions. Overall compliance percentage must never be treated as certification of an absolutely secure system.

## 12. Remediation: Fixing Pre-Existing Resources

For policies with appropriate effects, a **remediation task** can help bring non-compliant resources into the desired state. For example: a `DeployIfNotExists` policy designed to deploy missing diagnostic settings sending logs to a designated Log Analytics workspace.

Practical workflow:

1. Confirm the policy and resource types support remediation.
2. Inspect evaluation conditions, deployment templates/operations in the definition, and parameters such as workspace ID.
3. Configure a managed identity for the assignment when required by the policy.
4. Grant minimum roles needed by remediation to create or update the target configuration.
5. Review affected resources and approve the change per process.
6. Create a **remediation task** in the Azure Policy experience.
7. Monitor the task for succeeded, failed, or skipped resources.
8. Verify directly on the resource and log destination; then cross-check compliance state once updated.

**Distinction:** Audit and Deny do not automatically fix old violations. Modify and DeployIfNotExists can support remediation depending on the definition and resource type; support does not guarantee every case can be remediated automatically.

Common remediation failures include missing identity permissions, resource providers not supporting the modified property, mismatched deployment templates, missing log destination parameters, or misconfigured existence conditions. Inspect task output and deployment details before retrying at scale.

## 13. Managing Exceptions While Controlling Risk

There are cases where resources must continue running outside the baseline, such as legacy systems incompatible with a new setting. Rather than silently excluding scopes from the baseline, organizations should record decisions using **policy exemptions** where appropriate.

An exemption can include:

- The assignment and scope of exempted resources.
- **Exemption category**, such as **Waiver** (formally accepting the exception) or **Mitigated** (risk addressed through alternative controls).
- Business/technical justification and supporting evidence.
- Owner, approver, change ID, or internal ticket.
- Expiration date, aligned with organizational policy.
- Compensating controls and a plan to bring the resource back into baseline compliance.

Example: a legacy application can only operate in a region excluded from the new list. Operations proposes a time-bound exemption documenting the migration plan and next review milestone. At expiration, it must either be formally renewed or remediated.

**An exemption does not change the resource's configuration itself.** It documents a governance decision regarding policy evaluation. When an exemption expires, re-check the assignment's impact and subsequent deployment operations.

## 14. Maintaining the Baseline with Policy as Code

A large baseline should not exist solely as manual clicks in the Portal. Managing it as code enables change reviews, consistent rollouts, and configuration recovery.

Artifacts to version-control:

- Custom policy definitions and policy rules.
- Initiatives and lists of referenced policy definitions.
- Assignments by management group/subscription/resource group.
- Per-environment parameters.
- Exclusions, exemptions, and metadata under controlled workflows.
- Documentation mapping controls to security requirements and owners.

Common tools are **Bicep/ARM** or Terraform integrated with appropriate CI/CD pipelines. Example command to preview a subscription-scope Bicep deployment once a template file is prepared:

~~~bash
az deployment sub what-if \
  --location southeastasia \
  --template-file security-baseline.bicep
~~~

The illustrative command assumes the team has prepared a valid Bicep template. **What-if** previews expected changes, but does not replace testing actual policy behavior on target resources. Applying templates must still pass through separate approval and deployment pipelines.

When built-in policies change or the organization updates security standards, verify impacts on definitions, parameters, effects, and compliance states; never assume identical policy names guarantee unchanged behavior.

## 15. Using Azure CLI to Inspect Assigned Policies

In an environment with Azure CLI and a signed-in account, inspect existing assignments:

~~~bash
az login
az account set --subscription "<subscription-id>"

az policy assignment list \
  --scope "/subscriptions/<subscription-id>" \
  --output table
~~~

Inspect summarized policy compliance state on a subscription:

~~~bash
az policy state summarize \
  --subscription "<subscription-id>" \
  --output json
~~~

List sample policy state records for analysis:

~~~bash
az policy state list \
  --subscription "<subscription-id>" \
  --top 20 \
  --output json
~~~

Trigger re-evaluation on a resource group if needed:

~~~bash
az policy state trigger-scan \
  --resource-group "rg-baseline-lab"
~~~

Commands are shown with placeholders and require appropriate permissions and supported CLI extensions/tools in your Azure CLI version. The **trigger-scan** command requests re-evaluation, though results do not always appear immediately. When reporting, always record scan time, query time, and scope.

State-reading commands also depend on access permissions. If output is empty, verify scope and assignments before concluding no policies apply.

## 16. Baseline Rollout Scenario for a Production System

Suppose a company operates an e-commerce app on Azure comprising APIs, VMs, VNets, Azure Storage, and a database service. Resources span multiple resource groups in a production subscription.

### Phase A: Current-State Assessment

- Inventory subscriptions, resource groups, and resource types.
- Inspect regions, tags, public network configurations, and diagnostic settings.
- Identify exemptions with valid justification.
- Select an initial control set: SEC-01 through SEC-05.
- Assign accountable owners and remediation priorities for each drift item.

### Phase B: Pilot Testing

- Create the baseline initiative and assign it to a sandbox subscription.
- Use Audit or an appropriate test mode to evaluate without blocking valid workflows.
- Deploy one compliant resource and one intentionally missing a tag.
- Verify compliance logic accurately flags each target.
- Test Deny on a well-understood policy inside the test scope.
- Confirm valid deployments are not blocked and violation messages are clear.

### Phase C: Controlled Rollout

- Deploy the initiative at the approved production scope.
- Enable Deny for critical, verified requirements.
- Use Modify/DeployIfNotExists where suitable policies, permissions, and templates exist.
- Trigger remediation tasks for selected existing resources.
- Monitor denied operations and feedback from application teams.

### Phase D: Ongoing Operations

- Include compliance reports in regular review cadences.
- Open remediation work items with owners and due dates for critical violations.
- Track exemptions and re-evaluate before expiration.
- Update the baseline when adding services, regions, or security requirements.
- Use version control and peer reviews whenever changing effects, scopes, or policy lists.

The goal is not achieving a pretty report number by excluding every difficult resource; the goal is reducing real risk and providing clear evidence for every decision.

## 17. Common Design Mistakes

**Assigning Deny too early at a management group.** Teams can get blocked mid-deployment before impacts are understood. Start in a test scope, check deployment pipelines, and roll out in phases.

**Picking policies by name without reading the rule.** A built-in policy may have unexpected parameters or effects; read the definition and verify behavior.

**Confusing compliance with total security.** Azure Policy has scope limits, especially regarding data payloads, in-app authorization, and settings not observable via ARM.

**Assuming assignments automatically fix every resource.** Remediating existing resources may require tasks, managed identities, permissions, and valid deployment templates.

**Ignoring costs and operational impacts.** Diagnostic settings generate log traffic and ingestion costs; blocking public network access may require updating apps, DNS, or private endpoints.

**Over-privileging remediation identities.** Grant only necessary permissions at the defined scope, review regularly, and audit changes made by automation.

**Failing to document exceptions.** Exclusions or exemptions lacking expiration dates and owners easily become permanent gaps in the baseline.

**Failing to govern environment differences.** Production and development may require different parameters, but exceptions must be clearly documented and reviewed.

## 18. Hands-On Lab: Creating a Tag Baseline in a Test Scope

**Prerequisites:** you hold permissions to create policy definitions/assignments in a sandbox environment, have a test resource group, and at least one taggable resource.

**Step 1.** Select the control: every taggable resource in the resource group must carry the **environment** tag.

**Step 2.** Create a custom definition with **Audit** effect based on the JSON in section 9, or pick an equivalent built-in policy after checking its rule.

**Step 3.** Assign the policy to the test resource group without exclusions, ensuring the effect is in the proper testing mode.

**Step 4.** Create or use two test resources of a supported type: one with **environment=dev**, and one without that tag. Avoid provisioning unnecessarily expensive resources.

**Step 5.** Trigger an evaluation or wait for policy compliance to refresh, then open the resource list under **Policy → Compliance**.

**Step 6.** Verify whether the untagged resource reports non-compliant while the tagged resource passes. If not visible yet, check scope, mode, indexing state, and evaluation timing.

**Step 7.** Add the tag to the non-compliant resource using an authorized management tool. Re-evaluate and monitor until results reflect the update.

**Step 8.** Record the definition/assignment IDs, scope, effect, compliant/non-compliant counts, evaluation timestamp, and causes if results differed from expectations.

**Step 9.** Clean up test resources and lab-specific assignments/definitions once no longer needed, following sandbox management procedures and permissions.

**Completion criteria:** learners can explain why the assignment detects untagged resources, why Audit does not auto-remediate, and why matching scope, mode, and supported resource types are required.

## 19. Knowledge Self-Check

1. Should policy SEC-01 be assigned at a management group or resource group when applying across all of production? How does that choice affect inheritance?
2. Why is a policy definition insufficient to protect resources without an assignment?
3. What is the difference in impact among **Audit**, **Deny**, and **DeployIfNotExists**?
4. When a DeployIfNotExists assignment is active yet older resources still lack diagnostic settings, what should you check?
5. When should an exemption be used instead of an exclusion for a temporary non-compliance case?
6. Why cannot an Azure Policy baseline replace Azure RBAC, Conditional Access, or Defender for Cloud?
7. Which fields would you record so an exception can still be audited six months later?

## 20. Summary

**Azure Policy turns security requirements into rules that can be evaluated and enforced across Azure resources.** An operable baseline needs accurate definitions, initiatives, appropriately scoped assignments, environment-specific parameters, controlled effect choices, compliance reporting, remediation, and exemption governance.

Build baselines from measurable requirements, prefer verified built-in policies, pilot in narrow scopes, assess impact before enabling Deny, and manage lifecycles as code. Combine Azure Policy with RBAC, Microsoft Entra ID, monitoring, and change governance to protect Azure application architectures consistently.
