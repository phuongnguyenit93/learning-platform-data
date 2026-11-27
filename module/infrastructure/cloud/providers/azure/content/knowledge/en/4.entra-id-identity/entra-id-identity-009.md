# Managing privileged access with Privileged Identity Management

## 1. Learning objectives

In the Microsoft Azure module, identity and access form a protective layer spanning subscriptions, resource groups, networks, virtual machines, storage, data, and operations tools. Administrators may need powerful permissions to troubleshoot incidents or modify configurations, yet keeping those permissions active continuously increases risk if an account is compromised or used erroneously.

After this lesson, you will be able to:

- Explain the principles of **least privilege** and **just-in-time (JIT)** access.
- Distinguish **eligible** roles, **active** roles, assignment duration, and activation duration.
- Understand how Microsoft Entra Privileged Identity Management (PIM) governs roles across Entra ID, Azure resources, and groups.
- Describe how to configure activation conditions, approval requirements, MFA, justification, ticket numbers, and notifications.
- Practice the workflow of assigning an eligible role, activating it temporarily, verifying access, and inspecting activity history.
- Identify PIM's limitations and combine PIM with RBAC, Conditional Access, monitoring, and periodic access reviews.

## 2. Risks of standing administrative privileges

Suppose an engineer needs the **Owner** role on a subscription to resolve a rare incident. If the Owner role remains continuously active, the engineer's account can modify resources, grant permissions to others, or delete critical components even outside incident response windows. A single credential leak dramatically expands the blast radius.

Common issues with standing administrative privileges include:

- **Excess standing privilege:** users retain permissions long after a project, on-call shift, or task has ended.
- **Poor visibility into timing:** it is unclear who genuinely needs elevated permissions at any moment and why.
- **Weak traceability:** permission grants are not tied to an incident ticket or an approver.
- **Increased impact on account compromise:** an attacker can immediately use already-active roles.
- **Overly broad permissions:** granting Owner at the subscription when a task only requires Contributor on one resource group.

**Microsoft Entra Privileged Identity Management** is a privileged access governance service that manages assignment, activation, and monitoring of critical permissions. PIM allows a user to be marked eligible for a role and then activate that role only when genuinely needed and for a bounded duration.

PIM does not replace RBAC. RBAC determines **which permissions a role holds and at which scope**; PIM adds governance over **who can activate the role, when, for how long, and under what conditions**.

## 3. Core concepts

| Concept | Meaning | Example |
|---|---|---|
| Privileged role | Role with sensitive access or administrative permissions | Global Administrator, Privileged Role Administrator, Owner |
| Eligible assignment | User is eligible to request role activation | Engineer can activate Contributor on the production resource group |
| Active assignment | Role permission is currently effective without an activation step for that use | Engineer has activated Contributor for 2 hours |
| Permanent eligible | Eligibility with no preset expiration date | Engineer can activate whenever needed per policy |
| Time-bound eligible | Eligibility that exists only within a specified time window | Eligible to request activation during a 7-day project window |
| Activation | Action taken by a user to convert an eligible role into a temporary active role | Activating Security Reader for 1 hour |
| Approval | Step where a designated approver reviews the activation request if required by policy | Shift lead approves an incident-response session |
| Role settings | Conditions and limits governing role activation/assignment | MFA, max duration, justification, approval, notifications |
| Access review | Periodic review of whether users still need assigned permissions | Reviewing eligible assignments quarterly |

A person may hold an **eligible assignment** lasting several months while each **activation** is limited to one or two hours. These two durations are independent. When an activation expires, active permissions are revoked by PIM; when the eligible assignment expires, the user is no longer eligible to request activation of that role.

**Eligible does not mean active.** An eligible role only grants the ability to submit an activation request. Only once activation succeeds, policy conditions are met, and effective state updates does the user hold the corresponding permissions.

## 4. What types of permissions does PIM protect?

PIM provides distinct management experiences. Never confuse directory identity roles with Azure resource management roles.

| Scope | Typical targets | Example duties |
|---|---|---|
| **Microsoft Entra roles** | Global Administrator, Privileged Role Administrator, Security Administrator, User Administrator | Managing identities, directory roles, and identity policies |
| **Azure resources** | Azure RBAC roles at management group, subscription, resource group, or resource | Modifying VM, network, storage configuration, or resource access |
| **PIM for Groups** | Membership or ownership of groups onboarded to PIM | Activating group membership used to inherit group-assigned permissions |

In some environments, groups are assigned roles or resource permissions. In those cases, **PIM for Groups** can provide an activation workflow for group membership or ownership, thereby controlling permissions granted through the group. Supported models, group types, and practical limits depend on licensing and tenant configuration; verify before selecting a design.

Important examples:

- **Global Administrator** is a Microsoft Entra ID directory role; it is not inherently Owner of every Azure subscription.
- **Owner** on a resource group is an Azure RBAC role scoped to that resource group; it does not turn a user into Global Administrator.
- **Contributor** can manage most resource configurations within its granted scope, yet typically cannot assign Azure RBAC roles like Owner or User Access Administrator.

Therefore, before configuring PIM, clearly identify **the role type, permission scope, and task to be performed**.

## 5. How PIM integrates with RBAC and Conditional Access

A privileged access decision has multiple layers:

1. **Authentication:** sign in to Microsoft Entra ID; authentication and Conditional Access requirements may apply.
2. **Eligibility:** PIM checks whether the user holds an eligible assignment for the requested role and scope.
3. **Activation conditions:** role settings may require MFA, an authentication context, justification, ticket information, or approval.
4. **Temporary elevation:** once the request is valid and approved if required, the role becomes active for the allowed window.
5. **Operation authorization:** the target service checks active RBAC or Entra role permissions before allowing the operation.
6. **Logging and expiration:** activation history, approvals, and assignment changes can be audited; permissions expire when the activation window ends per platform mechanisms.

Conceptual diagram:

~~~mermaid
flowchart TD
    A[User holds eligible assignment] --> B[Requests role activation]
    B --> C{Conditions met?}
    C -->|No| D[Complete MFA, enter justification or ticket]
    D --> C
    C -->|Yes| E{Approval required?}
    E -->|Yes| F[Approver reviews request]
    F -->|Rejected| X[Activation denied]
    F -->|Approved| G[Role becomes active for limited duration]
    E -->|No| G
    G --> H[Perform work governed by RBAC]
    H --> I[Activation expires or is deactivated]
    I --> J[Review history and audit logs]
~~~

Actual flows can differ by role and settings. For example, an MFA requirement already satisfied by a valid sign-in session may not always trigger a new MFA prompt. Propagating updated permissions to target services can also take a brief period.

## 6. Preparation before using PIM

Before enabling PIM for an administrative group, check:

**Licensing:** PIM is a capability included in Microsoft Entra plans with privileged identity governance entitlements, such as Microsoft Entra ID P2 or an appropriate Entra ID Governance plan. Specific users requiring licenses and usage rights depend on current licensing terms. Verify terms for your tenant and users rather than assuming every Azure account includes PIM.

**Setup permissions:** the person configuring PIM must hold PIM management permissions and authority at the corresponding role scope. For Microsoft Entra roles, **Privileged Role Administrator** is typically appropriate for managing assignments and role settings. For Azure resources, the manager needs appropriate permissions on the Azure scope, typically **Owner** or **User Access Administrator**. Some operations have additional requirements; exact UI and roles depend on the target objective.

**Scope:** identify the tenant, subscription, resource group, or group to protect. For Azure resources, narrower scopes help limit unintended impact.

**Identities:** users should have individual accounts, valid MFA methods, and the ability to satisfy Conditional Access requirements. Avoid shared admin accounts, which undermine accountability.

**Approvers:** if approval is required, designate people able to respond during incidents; prepare fallback approvers when primary approvers are unavailable.

**Emergency operations:** design emergency access accounts following an independent, tightly monitored, and tested security procedure. Never let total recovery of administrative access depend solely on an approval flow that could be disrupted.

## 7. Configuring an eligible role

Menu labels may vary across versions of the Microsoft Entra admin center or Azure Portal. The general workflow still consists of selecting the role type, scope, assignee, and eligible/active status.

### 7.1. Assigning an eligible Microsoft Entra role

Example: a security team member only occasionally needs the **Security Administrator** role.

1. Sign in to the **Microsoft Entra admin center** with an account authorized to configure roles.
2. Open **Identity Governance → Privileged Identity Management**.
3. Select **Microsoft Entra roles** and open **Assignments** or the corresponding add-assignment option.
4. Select the **Security Administrator** role, then select the target user.
5. Select **Eligible**; set start and end times for eligibility if required by policy.
6. Review scope, assignee, and duration before saving.
7. Check the assignments list to confirm the user is assigned as eligible as intended.

Assigning eligibility **does not grant Security Administrator immediately**. The user will need to activate the role when needed and satisfy the configured conditions.

### 7.2. Assigning an eligible Azure RBAC role

Example: an engineer needs **Contributor** in a resource group named **rg-prod-app** to deploy a patch, without needing subscription-wide permissions.

1. In the PIM experience, select **Azure resources**.
2. Select the subscription or resource group to govern. Depending on configuration, you may first need to discover and onboard the resource into PIM management.
3. Open **Roles** or **Assignments** for the selected scope.
4. Choose **Contributor**, the target user, and assignment type **Eligible**.
5. Set the eligibility duration and confirm the assignment.
6. Verify the role, resource ID/scope, and assignment type after saving.

If work only touches **rg-prod-app**, assigning Contributor at that exact resource group limits access far better than Contributor at the subscription level. Never assign Owner just to update app settings when Contributor suffices.

### 7.3. Distinguishing eligible vs. active when assigning

| Form | When does the user exercise permissions? | When to consider |
|---|---|---|
| Eligible | After activating and satisfying PIM conditions | On-demand administration, maintenance, on-call operations |
| Time-bound active | Permissions active immediately for the assigned window | A short task requiring continuous access for a fixed period |
| Permanent active | Permissions continuously active while assignment persists | Consider only with clear operational justification and compensating controls |

The goal is to reduce standing active privileges and narrow permission scopes. However, do not force every account type, service, or automated workflow into an interactive human activation pattern.

## 8. Configuring role activation policies

Settings can be managed **per role and scope**. Configurations for Microsoft Entra roles and Azure resource roles do not necessarily live on the same page.

| Setting | Effect | Internal policy example |
|---|---|---|
| Maximum activation duration | Limits how long one activation can last | Contributor: max 2 hours |
| Require MFA | Requires appropriate authentication assurance at activation | Multi-factor authentication required |
| Conditional Access authentication context | Enforces authentication conditions via linked policy | Activate only when required authentication level is met |
| Require justification | Forces entering a reason for using the role | "Fix v2.3 deployment failure" |
| Ticket information | Requires an incident or change ticket reference | "INC-2026-0427" |
| Require approval | Requires a designated approver to approve activation | SRE shift lead approves |
| Activation notifications | Sends alerts about activation events per configuration | Notify relevant administrators |
| Assignment settings | Constrains assignment types and durations | Eligibility limited to project phase |

**Note:** The table above illustrates policy design. Specific durations and options must be checked in the UI/service and within role-type limits. There is no single "best default PIM policy" for every tenant.

When configuring:

1. Select the right role and scope.
2. Assess the sensitivity of the permissions and operational risk.
3. Set an activation duration aligned with real tasks.
4. Enable authentication requirements, justification, and approval per policy.
5. Test approvers and notification delivery using an appropriately authorized test account.
6. Verify deactivation after session end and audit log retrieval.

Approval can increase incident response time, so operations teams must define backup approvers and emergency handling paths. Conversely, stripping authentication and approval requirements from sensitive roles undermines the JIT model.

## 9. How does a user activate a role?

Suppose a user holds an eligible **Contributor** assignment on **rg-prod-app** and needs to deploy a patch.

1. Open Microsoft Entra PIM from the Portal or Entra admin center.
2. Open **My roles**, choose **Azure resources**; for directory roles, choose **Microsoft Entra roles**.
3. Locate the needed eligible role and select **Activate**.
4. Select duration and enter justification and ticket info if required by policy.
5. Complete authentication checks. If approval is required, wait for a designated approver to approve.
6. Once PIM confirms activation succeeded, verify the role shows as **Active** along with its expiration time.
7. Perform only the assigned work; deactivate early if permissions are no longer needed and supported by the UI/policy.
8. Inspect activation history to confirm the activity was recorded.

Some roles may not work immediately after PIM reports success because permissions are still propagating or active tools still hold an older session/token. When needed, refresh your sign-in or management session and recheck permissions on the target service. Never grant yourself broader-scope access as a "workaround" for propagation delay.

If a request is rejected, read the reason, verify ticket/scope details, and resubmit per procedure; never treat holding an eligible assignment as entitlement to bypass approval.

## 10. End-to-end example: handling a production application incident

An Azure application uses VMs, a virtual network, and a storage account inside resource group **rg-prod-app**. An operations engineer needs to update a VM configuration during a production incident, though most of the time only Reader access is needed.

**Normal state:**

- The engineer holds Reader at the appropriate scope for monitoring and viewing configurations.
- The engineer holds an eligible Contributor assignment on **rg-prod-app**.
- The Contributor policy requires MFA, justification, ticket number, approval, and a maximum 2-hour duration.
- Owner is not granted if the task does not involve managing role assignments.

**During an incident:**

1. Monitoring raises an alert and creates ticket **INC-2026-0427**.
2. The engineer checks logs and determines a VM configuration change is needed.
3. The engineer opens PIM and requests activating Contributor on **rg-prod-app** for 60 minutes.
4. The engineer completes authentication, enters the ticket, and states the reason.
5. The shift lead reviews the request, scope, and expected impact, then approves.
6. After activation succeeds, the engineer updates the configuration within the granted scope and verifies the application.
7. When finished, the engineer deactivates the session if possible; permissions are also configured to expire automatically.
8. Operations correlates the ticket, PIM history, Azure Activity Log, and relevant logs for post-incident review.

**Key distinction:** PIM logs answer **who requested or activated permissions, when, and under what conditions**. Azure Activity Log and target service logs help investigate **how resources were actually changed**. A complete picture requires combining these sources.

## 11. Monitoring, auditing, and access reviews

JIT elevation is only half of the governance lifecycle. The other half is detecting excess permissions, watching for anomalous activations, and conducting periodic reviews.

### 11.1. What to monitor

| Data | Questions to answer |
|---|---|
| Role assignments | Who is eligible or active for which role, and at which scope? |
| Activation history | Who activated, for how long, and with what justification? |
| Approval history | Who approved or rejected requests? |
| Audit history | When and by whom were assignments or role settings changed? |
| Alerts | Are there signs of excessive privileged admins or unusual assignments? |
| Access reviews | Do users still have a business need to retain their assignments? |

Depending on resource type and integration, data can be viewed in PIM's history, audit, or alerts pages; centralized analysis may require configuring log export and appropriate retention periods. Never assume all logs are retained indefinitely by default.

### 11.2. Periodic access review workflow

1. List sensitive roles and all associated eligible/active assignments.
2. Verify account owners, current duties, and the necessity of each role.
3. Identify assignments with overly broad scope, no expiration, or no clear accountable owner.
4. Require managers or system owners to confirm whether to keep or revoke permissions.
5. Revoke eligible assignments that are no longer needed per procedure.
6. Retain evidence of the decision, timestamp, and approver.

Access reviews evaluate **whether permissions are still needed**, whereas activation history shows **how permissions were used**. Both are valuable and serve distinct purposes.

## 12. Operating PIM for Groups

PIM for Groups is considered when an organization manages permissions via groups instead of assigning every role directly to individuals. For example, a maintenance group is assigned permissions on a specific resource group; users only become active members of the group during an approved maintenance session.

Conceptual workflow:

1. Identify eligible groups to govern with PIM and how those groups grant permissions.
2. Configure eligible membership or ownership for appropriate individuals.
3. Configure duration limits and activation conditions.
4. Users activate membership/ownership when a task arises.
5. Verify effective permissions in target systems, accounting for sync or token latency.
6. Review eligible memberships and activation history.

Distinguish **group membership** from **Entra/Azure roles assigned to the group**. Activating membership only grants whatever permissions the group actually holds at its assigned scopes. Becoming a member of a group does not inherently grant Owner or Global Administrator.

## 13. Limitations and edge cases to watch

**PIM targets privileged human administration, not every identity type.** Service principals, managed identities, application accounts, and machine-to-machine authorization have their own models. Do not assume enabling PIM automatically governs secret lifecycles, API permissions, or workload identity permissions.

**Activation expiration does not always sever active connections instantaneously.** Target systems may hold tokens, caches, or experience permission propagation lag. When testing, verify both PIM status and actual ability to perform operations.

**Overly broad RBAC remains a risk.** PIM limits duration, yet it does not make Owner equivalent to Reader. Narrow roles and scopes before adding an activation workflow.

**Alternative permission paths may exist.** A user might still hold permissions via a direct active assignment, another group, or a parent-scope role. Revoking one eligible assignment does not necessarily remove every equivalent access path.

**MFA and Conditional Access must work harmoniously.** Requiring conditional activation without enrolled methods or blocking the wrong users can cause outages. Test with realistic accounts and user flows.

**Approval does not replace change impact assessment.** Role approvers should know the requester, reason, and scope; modifying a production system may still require a separate change management process.

**Emergency access must be carefully governed.** Maintain fallback options to prevent locking out the entire organization, while protecting credentials, logging every activity, and testing periodically.

## 14. Comparing standing permissions vs. PIM

| Criterion | Standing active roles | Eligible via PIM |
|---|---|---|
| Immediate availability | Generally available immediately upon sign-in and permission evaluation | Must be activated before use |
| Time-limited privilege usage | None per session unless configured otherwise | Can bound duration per activation |
| Usage justification | Not captured at access time | Can require justification/ticket |
| Pre-use approval | Not captured | Can enforce approval |
| Historical audit | Must rely on target system audits | Captures requests, activations, approvals, and assignment changes |
| Risk if account is compromised | Privileges may already be active | Attacker must also pass activation conditions, if properly configured |
| Operational complexity | Fewer user steps, risk of standing privilege | Requires managing policies, approvers, MFA, and incident paths |

PIM reduces the attack surface of high-privilege roles, though effectiveness depends on policy design, authentication strength, scoping, and monitoring.

## 15. Guided practice in a test environment

**Context:** You manage a test resource group and want an engineer to hold Contributor only during a short maintenance window.

**Prerequisites:** the tenant is licensed for PIM; you have a PIM/role-assignment admin account with appropriate permissions; a test resource group exists; the test user can complete MFA and approval if enabled.

**Tasks:**

1. Inspect existing role assignments on the resource group to avoid duplicate permissions via another active assignment.
2. Assign Contributor as eligible to the test user on the resource group.
3. Configure a short activation duration, require justification, and enable at least one authentication condition matching test policy.
4. Sign in as the test user; confirm that a write action requiring Contributor fails while the role is inactive and no other permission path exists.
5. Request activation with the reason "Test maintenance", completing conditions and approval if enabled.
6. Verify the role is active and perform **one reversible write operation** on a test resource using the granted permissions.
7. Deactivate or wait for activation expiration; refresh your session/token as needed, then re-test the write operation.
8. Open PIM history and correlate the activation timestamp with resource group activity.
9. Remove the test eligible assignment upon completing the lab, per permitted roles and procedures.

**Expected result:** the user can activate Contributor within the configured window, conditions are enforced, and the activation event is logged. Never declare the lab successful solely because PIM shows Active; verify actual permissions and expiration behavior.

If your environment lacks licensing or you lack permissions to manage assignments, complete this as a paper design exercise: build a table covering role, scope, justification, maximum duration, MFA, approver, notification recipients, and emergency handling. Never attempt to alter tenant settings without authorization.

## 16. Self-check questions

1. Can someone with an eligible Global Administrator assignment immediately modify users? Why or why not?
2. How does the Owner role on a resource group differ from Global Administrator?
3. Why must eligible assignment duration and activation duration be configured separately?
4. If a user reports having activated Contributor yet Azure still returns a permission error, what should you check?
5. Why can't you rely solely on PIM history to know every configuration change that occurred?
6. When an assignment is revoked yet a user still retains access, what alternative permission paths should you inspect?

**Hints:** focus on eligible/active status, role type, scope, inherited or group permissions, propagation latency, tokens, and audit logs from target systems.

## 17. Summary

Microsoft Entra Privileged Identity Management brings **least privilege** and **just-in-time** principles to privileged role management. With PIM, organizations can assign roles as eligible, enforce time-bound activations, add MFA/Conditional Access conditions, require justification, tickets, and approvals, and log activity. PIM maintains separate scopes for Microsoft Entra roles, Azure resource roles, and groups, so always choose the right role and scope before configuring.

In Azure architectures, PIM serves as an identity governance layer helping protect subscriptions, resource groups, and infrastructure operations. Combined with RBAC, monitoring, auditing, access reviews, and emergency procedures, it reduces standing privileges while preserving legitimate operational agility.
