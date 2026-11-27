# Managing Multiple Tenancies with Organization Management

When an enterprise uses Oracle Cloud Infrastructure (OCI) for multiple business units or systems requiring strong isolation, a single tenancy may not fit the entire governance model. However, creating additional tenancies also brings extra work: identity administration, configuration standardization, limit tracking, and cost consolidation.

**Organization Management** helps manage tenancies within an organization: creating or inviting child tenancies, managing subscription mappings, and applying governance rules. It is an organizational tool for multi-tenancy governance that must be paired with a landing zone inside each tenancy. See [Organization Management Overview](https://docs.oracle.com/en-us/iaas/Content/General/organization/organization_management_overview.htm).

This lesson belongs to the **Resource Governance and Landing Zones** chapter of the Oracle Cloud Infrastructure module. After this lesson, learners will be able to choose between compartments and tenancies, describe parent–child relationships, organize an onboarding workflow, and verify three independent dimensions: organization membership, cost attribution, and governance status.

## 1. Parent Tenancy, Child Tenancy, and Subscription Model

In Organization Management:

- **Parent tenancy** holds responsibility for managing the organization and associated subscriptions.
- **Child tenancy** joins the organization by being newly created or accepting an invitation.
- **Subscription** provides billing terms and corresponding consumption entitlement.
- **Subscription mapping** determines which subscription a tenancy consumes from.

An organization can have multiple child tenancies and multiple subscriptions. The parent can assign subscriptions to tenancies within the organization. See [Organization Management Overview](https://docs.oracle.com/en-us/iaas/Content/General/organization/organization_management_overview.htm).

Design example:

~~~text
Organizational relationship
===========================

Parent tenancy: acmeplatform
├── Child tenancy: acmeorders
├── Child tenancy: acmeanalytics
└── Child tenancy: acmesandbox

Subscription relationship
=========================

Subscription A  ← acmeplatform, acmeorders, acmesandbox
Subscription B  ← acmeanalytics
~~~

The two halves of the diagram depict **two distinct relationships**. Adding acmeanalytics to the organization and choosing its subscription are two separate decisions that must be verified independently.

The names in this lesson are illustrative only. Never infer permissions, network configuration, or financial obligations from a tenancy name. Operational records should identify tenancies using OCIDs and actual subscription details.

A child tenancy is also not a child compartment inside the parent. It is an independent tenancy participating in a shared management model.

## 2. When Should You Use Multiple Tenancies?

OCI advises weighing the operational cost of a multi-tenancy model. Each tenancy has its own IAM, administrators, service limits, VCNs, and security configurations; if that level of isolation is unnecessary, compartments can be used instead. See [Planning Considerations](https://docs.oracle.com/en-us/iaas/Content/General/organization/organization_planning.htm).

The table below provides a recommended architecture evaluation framework:

| Need | Single tenancy with compartments | Multiple tenancies |
| --- | --- | --- |
| Teams share IAM and operational foundation | Usually simpler | Requires justifying the extra isolation benefit |
| Typical separation of applications or environments | Can be met with compartment and IAM design | Should not be chosen solely because there are many apps |
| Need separate administrators and foundational configurations | Must evaluate limits of the shared model | Worth considering |
| Onboarding a system already in its own tenancy | May require a migration project to consolidate | Can evaluate inviting it to join the organization |
| Small operations team | Fewer foundational configs to maintain | Requires capacity to manage multiple landing zones |
| Multi-unit cost aggregation | Use compartments and tags per convention | Adds tenancy and subscription as analysis dimensions |

For example, separating dev and prod does not automatically dictate creating two tenancies. If the goal is scoping developer permissions and capping test resources, evaluate compartments first.

Conversely, a newly acquired business unit that already has its own tenancy, IAM team, and database systems may need to retain that independence during a transition period. In that case, Organization Management offers a way to centralize billing management and selected controls.

Choosing multiple tenancies also does not automatically create disaster recovery capability. Application resilience still depends on deployment locations, data backups, connectivity, and failover procedures.

## 3. Governance Boundaries to Clarify

In this lesson's proposed model, divide responsibilities across roles:

| Accountable group | Scope of responsibility |
| --- | --- |
| Platform team at parent | Tenancy catalog, create/invite workflows, governance rules |
| Finance team | Subscription selection, cost reconciliation, transition-period tracking |
| Child tenancy administrators | IAM, baseline configuration, resources, and operations inside the tenancy |
| Application teams | VCN, Compute, storage, databases, and service quality |
| Security team | Auditing permissions, identities, logs, and exceptions |

This is an illustrative allocation, not roles automatically created by OCI.

Because IAM is managed per tenancy, never treat organization linking as proof that parent administrators already hold permissions to read buckets, log into servers, or operate databases in a child tenancy. If the platform team needs access in a child tenancy, design and verify those access permissions explicitly.

Likewise, cost consolidation does not create network connectivity between VCNs. If order-api in acmeorders needs to read data in acmeanalytics, you must design connectivity, name resolution, network controls, and required service permissions separately.

An entry in the tenancy catalog should answer:

~~~text
Which tenancy?
Who owns it?
Which subscription does it use?
Who holds administrative rights?
Which governance rules have applied successfully?
Which landing zone is deployed?
Who is accountable when an incident occurs?
~~~

## 4. Prerequisites Before Creating or Inviting a Tenancy

Before rolling out the model, check eligibility and actual limits:

| Item | What to verify |
| --- | --- |
| Account type | Free Tier/Trial must upgrade to paid before creating or joining |
| Child tenancy count | Parent must have sufficient organization limits |
| Regions | Regions subscribed by child must be within the set subscribed by parent |
| Creating a new child | Must be performed from the parent's home region |
| Inviting an existing tenancy | Verify paid account, same realm, and standalone status |

Paid-account eligibility does not mean sufficient limits have been granted. See [Child Tenancy Management](https://docs.oracle.com/en-us/iaas/Content/General/organization/child-tenancy-management.htm) and [Planning Considerations](https://docs.oracle.com/en-us/iaas/Content/General/organization/organization_planning.htm).

Do not confuse **home region** with all regions where resources can be deployed. The onboarding record should list the home region, subscribed regions, and organization-approved regions separately.

Beyond service prerequisites, the deployment team must align on the owner, initial administrator account, emergency access plan, and intended subscription. Make these decisions before creating any production tenancy.

## 5. Creating a New Child Tenancy

Use the create flow when you need a fresh tenancy with no existing resources and want it in the organization from day one.

Console workflow:

1. Sign in to the parent tenancy and open **Governance & Administration → Organization Management → Tenancies**.
2. Choose **Create new tenancy**.
3. Enter the name, home region, and administrator email.
4. Check the subscription; by default it uses the organization's default subscription, or you can select another eligible subscription.
5. Select governance rules to attach, or leave them to configure later.
6. Review details, create the tenancy, and monitor completion.

The child administrator receives activation instructions to set up a password and MFA. See [Creating a Child Tenancy](https://docs.oracle.com/en-us/iaas/Content/General/organization/child-tenancy-create.htm).

Example proposal record prior to creation:

| Attribute | Illustrative value |
| --- | --- |
| Name | acmesandbox |
| Purpose | Running OCI hands-on lab exercises |
| Owner | Platform team |
| Initial administrator | Organization-designated account |
| Subscription | Subscription A |
| Allowed regions | Approved lab region list |
| Resource policies | Quotas suited to learning objectives |
| Readiness criteria for use | Completed baseline and cost monitoring |

A successfully created tenancy is not yet ready for workloads. The platform team still must deploy IAM, compartments, tags, logging configuration, and appropriate networking components.

Do not treat the initial administrator account as daily access for the whole team. Design groups, automation identities, and task-based permissions during landing zone deployment.

## 6. Inviting an Existing Tenancy

Use the invite flow when you need to preserve an existing tenancy and its resources while bringing it into the organization.

From the parent tenancy, select **Invite tenancy**, enter the target tenancy OCID and recipient details, review governance options, and send the invitation. In the target tenancy, an authorized user opens the invitation, verifies the sender, and accepts. See [Inviting a Tenancy to Join an Organization](https://docs.oracle.com/en-us/iaas/Content/General/organization/sender-invitation-create.htm) and [Accepting an Invitation](https://docs.oracle.com/en-us/iaas/Content/General/organization/recipient-invitation-accept.htm).

Keep three points in mind:

- Sending an invitation does not complete the relationship.
- An invited tenancy automatically uses the default subscription upon joining; if it must use another subscription, inspect and update mapping.
- Usage reporting to the new subscription incurs a processing delay.

These behaviors are documented in [OCI's tenancy invitation workflow](https://docs.oracle.com/en-us/iaas/Content/General/organization/sender-invitation-create.htm).

Before accepting, prepare an inventory:

| Information group | Examples to record |
| --- | --- |
| Critical resources | Compute, databases, buckets, volumes, connectivity |
| Access | Admin groups, automation accounts, cross-tenancy permissions |
| Costs | Current subscription, target subscription, reconciliation period |
| Governance | Existing tag namespaces, quotas, subscribed regions |
| Operations | Backups, alerts, on-call staff, active exceptions |

Joining an organization is not an application migration plan. For customer-facing systems, identify which changes only affect billing versus which actually alter operational configurations.

## 7. Subscription Mapping and Cost Management

### 7.1. What Question Does Subscription Mapping Answer?

Mapping determines which subscription records a tenancy's usage. The tenancy uses the corresponding rate card and terms; with a Universal Credits Commitment, spend draws from that subscription's credits. Remapping switches the tenancy off the previous subscription onto the target subscription. See [Mapping Subscriptions to Tenancies](https://docs.oracle.com/en-us/iaas/Content/General/organization/subscription-mapping-create.htm).

Do not assume every subscription can be shared in the same way. OCI documentation distinguishes shareable Universal Credits from SaaS or Multicloud subscriptions that carry specific restrictions. See [Planning Considerations](https://docs.oracle.com/en-us/iaas/Content/General/organization/organization_planning.htm).

Example internal tracking:

~~~text
acmeorders:
  Intended subscription: A
  Cost owner: Orders business unit
  Standard CostCenter: CC420

acmeanalytics:
  Intended subscription: B
  Cost owner: Analytics business unit
  Standard CostCenter: CC610
~~~

This is a documentation record, not an OCI API payload. Verify actual mappings using the Console or CLI.

Changing a mapping also does not automatically transfer credits, alter contracts, or settle balances. Related commercial matters must be reconciled with Oracle through the appropriate channels. See [Inviting a Tenancy to Join an Organization](https://docs.oracle.com/en-us/iaas/Content/General/organization/sender-invitation-create.htm).

### 7.2. Consolidating at the Parent, Operating at the Child

The parent can analyze costs across the organization; each child views its own costs. Cost Analysis supports Tenant ID, Tenant Name, and Subscription ID dimensions. Both parent and child can create budgets within supported scopes; the parent can set budgets for child tenancies. Data before and after a remap remains tied to the active subscription at each point in time. See [Cost Reporting Integration](https://docs.oracle.com/en-us/iaas/Content/General/organization/organization_cost_reporting.htm).

In this example, finance should record acmeanalytics' subscription switch timestamp and reconcile both slices of the reporting period:

~~~text
Pre-switch portion of period  → old subscription
Post-switch portion of period → new subscription
~~~

Never pull only the current subscription and assume it represents the tenancy's entire cost for the full period.

Every budget needs an owner and alert recipients. Response workflows may include inspecting new resources, checking usage spikes, and consulting the application team. Never treat a budget as a guarantee that resources will automatically stop at an exact dollar figure.

## 8. Governance Rules: Shared Standards Across Tenancies

### 8.1. Control Categories

Organization Management supports three governance rule types:

| Rule type | Purpose |
| --- | --- |
| Allowed regions | Restrict which regions can be subscribed to |
| Quota policies | Enforce resource quotas or restrict services |
| Tags | Share tag namespaces and tag default configurations |

When a rule is attached, the corresponding governance resource is created and locked in the target tenancy. Child users cannot modify that locked resource on their own. See [Adding Governance to Tenancies](https://docs.oracle.com/en-us/iaas/Content/General/organization/add-governance.htm).

Recommended baseline example:

- Sandbox receives an allowed-region list suited to testing activities.
- Quotas are tailored to the resources actually needed for labs.
- The Governance namespace holds Environment, Service, and OwnerTeam.
- New resources receive metadata supporting owner lookup and cost analysis.

This is a suggested design. Quota syntax, supported services, and limit values must be selected for real workloads; never copy one sample quota blindly across every tenancy.

### 8.2. Organization Membership Differs from Governance Participation

A tenancy can share cost management without yet participating in organization governance. Check governance participation status separately. For existing tenancies, you can run an opt-in flow or require child approval; once opted in, a child cannot opt out on its own. See [Opting In Tenancies to Use Governance Rules](https://docs.oracle.com/en-us/iaas/Content/General/organization/add-governance-optinuserules.htm).

Therefore, your governance tracker should maintain independent columns:

~~~text
Tenancy OCID
Membership status
Active subscription
Governance opt-in status
Attached rules
Enforcement result per rule
~~~

Never collapse all of these into a single "onboarded" checkbox.

### 8.3. Rule Attachment Scope and Effective Enforcement

Rules can target selected tenancies or the entire organization. Organization-wide mode applies to current and future tenancies that participate in governance. When attaching a rule, monitor the work request for each target. See [Creating a Governance Rule and Attaching It to a Tenancy](https://docs.oracle.com/en-us/iaas/Content/General/organization/add-governance-createattachrule.htm).

An organization-wide change has a broad blast radius. The recommended workflow is to test on a pilot tenancy, observe impact, resolve conflicts, and only then expand scope.

Watch out for two easily misunderstood limitations:

- Allowed regions rules do not automatically unsubscribe regions already subscribed outside the list; the tenancy can still deploy resources in those already-subscribed regions.
- Editing a source resource in the parent, such as a tag namespace, still requires updating the governance rule so changes propagate to child tenancies.

See [Adding Governance to Tenancies](https://docs.oracle.com/en-us/iaas/Content/General/organization/add-governance.htm).

Accordingly, compliance verification must inspect both rule configuration and live state. A rule named approved-regions does not prove all existing resources reside inside approved regions.

## 9. IAM for Organization Management

Administrative groups should receive permissions aligned with their tasks. Examples for the Default identity domain:

~~~text
Allow group Default/OrgAdmins to manage organizations-family in tenancy
~~~

A group that only needs to accept invitations in a recipient tenancy can use:

~~~text
Allow group Default/OrgInvitationAccepters to manage organizations-recipient-invitations in tenancy
~~~

A group that only needs to inspect organization link relationships:

~~~text
Allow group Default/OrgLinkViewers to read organizations-links in tenancy
~~~

These examples follow [Required IAM Policy](https://docs.oracle.com/en-us/iaas/Content/General/organization/organization_required_iam_policy.htm). Substitute your domain and group names accordingly. Permission to read links does not include full access to view invitations or billing data.

In practice, distinguish:

- Who can create tenancies or send invitations.
- Who can accept invitations in a target tenancy.
- Who can alter subscription mappings.
- Who can alter governance rules.
- Who can view costs without modifying configurations.

Never grant an application team permission to manage the entire organizations-family just to deploy a Compute instance. Organization Management permissions and application resource permissions serve entirely different duties.

## 10. Verifying Subscription Mappings with the OCI CLI

The following example uses **Bash** in an environment with the OCI CLI configured. The profile must point to the parent tenancy and a principal authorized to read the relevant details.

~~~bash
export PARENT_TENANCY_OCID='ocid1.tenancy.oc1..replace_parent'
export SUBSCRIPTION_OCID='replace_with_actual_subscription_ocid'

oci organizations subscription-mapping list \
  --profile ORG_PARENT \
  --compartment-id "$PARENT_TENANCY_OCID" \
  --subscription-id "$SUBSCRIPTION_OCID" \
  --all
~~~

In this command:

- compartment-id uses the parent's root compartment, which is the tenancy OCID.
- subscription-id takes the **subscription OCID**, not its display name.
- all fetches all result pages.

See [OCI CLI: subscription-mapping list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/organizations/subscription-mapping/list.html).

After reading the results, reconcile against the approved tenancy catalog. If the organization has multiple subscriptions, query each relevant subscription; one call does not replace reconciling the whole organization.

When automating, separate inventory collection jobs from mapping-change jobs. A change proposal record should show the tenancy, current subscription, target subscription, and justification before the workflow is allowed to update mappings.

## 11. Combining Organization Management with Per-Tenancy Landing Zones

Organization Management handles governance at the organization level; the baseline inside each tenancy still requires its own deployment workflow.

The table below shows the design matrix for the Acme example:

| Component | Organization-wide standard | Per-child configuration |
| --- | --- | --- |
| Identity | Group conventions, MFA, task-based roles | IAM configuration and login verification |
| Compartments | Application and environment split conventions | OCIDs, structure, and owners |
| Tags | Namespaces and metadata definitions | Values for Service, OwnerTeam, CostCenter |
| Networking | Segmentation principles and IP management | VCNs, subnets, connectivity, and access rules |
| Monitoring | Alert criteria and log retention standards | Log sources, alarms, and recipients |
| Backups | Recovery targets by workload tier | Policies and recovery test results |
| Costs | Reconciliation and alerting workflows | Budgets, variance investigation owners |
| Automation | Versioned deployment templates | Parameters, runner identities, and required rights |

Not every row in the table is configured automatically by governance rules. For example, deploying VCNs, testing database recovery, or wiring alert channels requires dedicated tooling and workflows.

With IaC, you can maintain a shared landing zone template set and pass per-tenancy parameters. Each deployment record should log template version, target tenancy, and outcome. Creating a new child tenancy and forgetting to run the baseline leaves operational gaps even though the organization recognizes the tenancy.

For automation permissions, avoid sharing one admin account across all tenancies. Scope runner identities and permissions so a mistake in sandbox cannot cascade into changes across all production environments.

## 12. An Operable Onboarding Workflow

A proposed flow for acmeanalytics:

~~~text
Tenancy request
  ↓
Assess isolation requirements and accountable owner
  ↓
Verify eligibility, limits, regions, and subscription
  ↓
Create new or invite existing tenancy
  ↓
Verify organization link and subscription mapping
  ↓
Verify governance opt-in and apply rules
  ↓
Deploy landing zone baseline in child
  ↓
Verify access, monitoring, costs, and recovery
  ↓
Hand over to operations team
~~~

At handover, collect concrete evidence:

| Item | Recommended evidence |
| --- | --- |
| Organization membership | Tenancy OCID and verified parent–child link |
| Subscription | Actual mapping matches approved selection |
| Governance | Required rules successfully attached in target tenancy |
| Access permissions | Right groups can perform their assigned work |
| Networking | Required paths work; extraneous access paths eliminated |
| Operations | Logs, alerts, and recipients verified |
| Data | Backup and recovery plan matches workload tier |
| Costs | Budget owner and reconciliation schedule assigned |

You can practice this workflow in a lab using simulated records first. There is no need to spin up multiple production tenancies just to verify your documentation templates and responsibility splits.

For tenancies already running live workloads, use a change plan stating the starting baseline, post-join checks, and fallback steps if mapping or governance fails to reach the desired state.

## 13. Removing, Transferring, and Deleting Tenancies Are Distinct Actions

For an **invited child tenancy**, OCI provides a flow to remove it from the organization. Handle governance and mapping back to an appropriate standalone subscription before unlinking; also verify any dependent subscriptions. The parent will lose the ability to manage future costs and mappings for a tenancy that leaves the organization. See [Deleting Links to Invited Child Tenancies](https://docs.oracle.com/en-us/iaas/Content/General/organization/link-delete.htm).

For a **created child tenancy**, there is a CLI/API approval flow to transfer it to another organization, followed by completing invitation acceptance and mapping in the destination organization. See [Approving a Created Child Tenancy for Transfer](https://docs.oracle.com/en-us/iaas/Content/General/organization/approve-createdchildtenancy-for-transfer.htm).

Never use tenancy deletion as a substitute for changing organizational ownership or switching billing sources. If you only need to move to another subscription within the same organization, evaluate subscription mapping first.

An offboarding record should include:

1. Post-transfer owner and next billing source.
2. Central rules or workflows that must be replaced locally.
3. Affected automation identities and network connectivity.
4. Cost reconciliation snapshot at the transition timestamp.
5. Confirmation that monitoring, backups, and on-call coverage remain intact.

Never treat unlinking from an organization as revoking every configured permission or network connection. Access relationships and application dependencies must be inventoried separately.

## 14. Handling Errors and Discrepancies

| Symptom | Where to check |
| --- | --- |
| Cannot create child tenancy | Account type, organization limits, permissions, and home region |
| Cannot accept invitation | Correct recipient tenancy, invitation rights, and eligibility criteria |
| Child appears in organization but has no rules | Governance opt-in status and attached rule list |
| Rule created successfully but not enforced | Work requests in each target tenancy |
| Cost discrepancy after remap | Pre/post-switch subscriptions and query date range |
| Tag rule fails to attach | Namespace with the same name already exists in target |
| Quota rule fails to attach | Syntax, quota name, and work request error message |

OCI notes that issues like duplicate namespaces or invalid quota syntax can still result in a rule being created while attachment fails. Read work request logs and error messages to pinpoint the cause. See [Troubleshooting Organization Management](https://docs.oracle.com/en-us/iaas/Content/General/organization/organization-troubleshooting.htm).

For rules targeting multiple tenancies, record status separately per target. If acmeorders succeeds while acmeanalytics fails, do not mark the entire rollout complete.

Never resolve every error by granting broader administrative permissions. First identify whether the root cause is missing permissions, wrong scope, unmet service prerequisites, or a conflict with existing configuration.

## 15. Completion Criteria for a Multi-Tenancy Model

A design ready for operational handover should contain:

- Justification for using multiple tenancies instead of compartments alone.
- Catalog of OCIDs, owners, and missions for each tenancy.
- Live-verified subscription mappings.
- Clear IAM models for the parent and each child tenancy.
- Governance opt-in status and rule attachment results per tenancy.
- Baselines for networking, monitoring, data protection, and automation.
- Cost reconciliation workflow following subscription changes.
- Plans for exceptions, transfers, and offboarding.

In the Acme example, the expected outcome is that the central team can track tenancies, billing sources, and shared controls, while each application team retains clear operational accountability inside its own tenancy. Whenever another tenancy is added, the onboarding workflow must produce enough configuration and handover evidence for that tenancy to operate reliably.
