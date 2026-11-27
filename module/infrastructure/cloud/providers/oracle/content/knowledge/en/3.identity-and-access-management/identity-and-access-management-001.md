# Identity Domains and User Lifecycle Management

## 1. Objectives and Context

In Oracle Cloud Infrastructure (OCI), someone who can log in to the Console does not necessarily have permission to view a Compute instance, edit a VCN, or manage an Autonomous Database. An organization must manage identity, authentication methods, and access permissions simultaneously throughout a person's tenure.

This lesson belongs to the **IAM Identity and Access Management** chapter of the **CLOUD_PROVIDERS_ORACLE** module. It focuses on Identity Domains and user lifecycle management, establishing the foundation for operating OCI infrastructure with least-privilege access, monitoring, automation, cost control, and sustained governance during incidents.

After this lesson, you will be able to:

- Distinguish between tenancy, compartment, Identity Domain, user, and group.
- Explain the relationship between sign-in, domain administrator roles, IAM policies, and application permissions.
- Design workflows for onboarding, role changes, suspension, and termination of access.
- Distinguish between federation, provisioning, and Just-in-Time provisioning.
- Practice creating a test user, granting limited read access, and verifying revocation.
- Identify the evidence required to prove that a permission change has taken effect.

The running example is an organization with a development team and a platform operations team. Employee An starts working in the development team, later transfers to the production support team, and eventually concludes the contract.

## 2. What is an Identity Domain?

An **Identity Domain** is a management space for a population of users along with their associated identity and security configurations. A domain can contain users, groups, applications, sign-on settings, MFA, and federation configurations with external identity providers. OCI IAM uses Identity Domains for authentication, SSO, and identity lifecycle management for Oracle applications as well as third-party applications. [Oracle: IAM with Identity Domains](https://docs.oracle.com/en-us/iaas/Content/Identity/)

A domain helps answer the following questions:

- Which account represents employee An?
- Does An sign in using a local account or through the corporate identity system?
- Which groups contain An?
- Which sign-on rules apply to An?
- Who is allowed to support the account or administer the domain configuration?

A domain is neither a DNS domain nor a private network containing Compute instances.

### 2.1. Distinguishing Related Concepts

| Concept | Role | Enterprise Example |
| --- | --- | --- |
| Tenancy | OCI account boundary within which an organization manages resources and policies | The company's OCI account |
| Compartment | Organizes resources and serves as the scope for applying OCI permissions | Development compartment and production compartment |
| Identity Domain | Manages an identity population along with identity configurations | Employee domain or partner domain |
| User | An account record within a domain | An's account |
| Group | A collection of users used to organize permission or application assignments | Compute readers group |
| Domain administrator role | Delegates identity administration tasks within a domain | User and group administrator |
| IAM policy | Grants permissions to perform actions on OCI resources | Allow a group to read instances in a compartment |
| Application role | Business or administrative permissions within an integrated application | Report viewer role in an application |

An account belonging to a domain does not mean the resources it uses must reside in a compartment of the same name. Whether OCI permits an action on a resource depends on the permissions granted to the principal and the corresponding resource scope.

**A domain is where identities are organized; a compartment is where resources are organized.** To connect the two sides, appropriate permissions must be configured.

### 2.2. Default Domain and Additional Domains

A tenancy using Identity Domains has a **Default identity domain** and can have additional domains for other populations. One design approach is to separate employees and partners when the two groups have different administrators, identity sources, or sign-on rules. Oracle also describes separating domains to meet governance and user population isolation requirements. [Oracle: IAM Security Structure](https://docs.oracle.com/en-us/iaas/Content/cloud-adoption-framework/iam-security-structure.htm), [Oracle: Differences Between Tenancies With and Without Identity Domains](https://docs.oracle.com/en-us/iaas/process-automation/oci-process-automation/differences-tenancies-and-identity-domains.html)

There is no need to create a separate domain for every project. For multiple teams sharing the same identity source and sign-on requirements, combining groups with compartments can be easier to operate. This is a design choice that should be weighed against organizational requirements.

Before adding a domain, determine:

1. Are the user populations and administrative responsibilities genuinely different?
2. Is it necessary to separate IdP, MFA, or application configurations?
3. Who will be responsible for account synchronization, support, and access reviews?
4. Does the selected domain type have suitable features, limits, and billing?
5. Will duplicating accounts across multiple domains create extra offboarding overhead?

Do not assume that separating domains automatically separates all resources, costs, or OCI permissions. Those requirements also demand corresponding compartments, policies, and governance processes.

## 3. Three Layers to Check When Evaluating Permissions

A useful analysis method is to separate the access path into three layers:

~~~mermaid
flowchart LR
    P["User"] --> A["Local authentication or via IdP"]
    A --> D["Account in Identity Domain"]
    D --> G["Assigned groups and roles"]
    G --> I["IAM policy on OCI resources"]
    G --> R["Domain administration permissions"]
    G --> S["Application assignment and application role"]
    I --> C["Compute, VCN, storage, Database services"]
~~~

This diagram illustrates conceptual relationships and does not fully depict all protocols or internal processing order.

### 3.1. Authentication: Who Is This Person?

For local accounts, the domain manages the corresponding sign-in mechanism. For federated accounts, the external IdP authenticates the user according to the federation configuration. MFA adds authentication evidence, but it does not by itself grant resource management permissions.

### 3.2. OCI Authorization: What Can This Person Do?

An IAM policy defines a principal's permissions on resources within a tenancy or compartment. An OCI policy has the basic syntax:

~~~text
Allow <subject> to <verb> <resource-type> in <location>
~~~

For example, suppose a group and compartment already exist for lab practice:

~~~text
Allow group 'Default'/'iam-lab-readers' to read instances in compartment iam-lab
~~~

This policy grants members of the group permission to read `instance` resources within the specified scope. It does not grant permission to create instances, configure networks, or administer the domain. Reading all information related to an instance may require permissions on other resource types, such as networking details or volumes; do not broaden the policy just to make every Console page display completely.

The domain name in the subject clarifies which group is being referenced. When using a domain other than Default, specify the corresponding domain; avoid assuming that two groups with the same name in two different domains represent the same principal. [Oracle: IAM Policies Overview](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/policy-syntax.htm), [Oracle: Subjects](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/subject.htm)

### 3.3. Domain Administration and Application Permissions

A **User administrator** can manage users, groups, and group memberships within a domain. A **Help desk administrator** handles support tasks such as unlocking accounts and resetting authentication factors within the assigned scope. An **Identity domain administrator** holds broad administrative permissions within the domain and must be assigned deliberately. [Oracle: Understanding Administrator Roles](https://docs.oracle.com/en-us/iaas/Content/Identity/roles/understand-administrator-roles.htm)

Do not treat a domain administrator role as synonymous with permission to administer all Compute instances or all compartments. Domain roles and IAM policies have different scopes, and a user's complete set of effective permissions must always be evaluated. [Oracle: Security](https://docs.oracle.com/en-us/iaas/Content/Identity/conversion/security.htm)

Similarly, permission to manage a Database service through OCI does not automatically replace permissions inside the database itself. SQL logins, application roles, and host OS logins are separate surfaces that must be managed independently if the system uses them.

**Operational implication:** successfully supporting a sign-in only proves that the authentication layer works. It does not prove that resource permissions are accurate, sufficient, and properly bounded as required.

## 4. Identifying Identity Data Sources

Before creating many users, decide which system is the authoritative source of truth for each type of data.

| Data | Recommended Source of Truth | Questions to Resolve |
| --- | --- | --- |
| Employee ID, start date, end date | HR system | When is the termination event emitted? |
| Corporate account | Company directory or IdP | Who is responsible for verifying the account owner? |
| User attributes in OCI | Approved synchronization rules | Which fields are edited locally and which are overwritten? |
| Business groups | Entitlement catalog and approvers | Who can request and approve memberships? |
| Privileged admin roles | Access governance workflow | Who approves, who executes, and who reviews? |
| Provisioning and revocation results | Target enforcement and verification system | Is there confirmation from the target system or only a request? |

The table above is a suggested process organization, not a default set of data sources configured automatically by OCI.

Link records using a stable employee or partner identifier rather than relying solely on display names. Email addresses can change when employees transfer departments, and display names can collide. When someone returns to work, reconcile history and approvals instead of automatically restoring all previous permissions.

A change in the source of truth has operational value only after it has been applied and verified at the target. A "request submitted" status is different from "successfully revoked."

## 5. User Lifecycle Model

OCI describes the account lifecycle with stages including non-existent, deactivated, activated, and deleted. State transitions are tied to organizational events or schedules. [Oracle: Lifecycle for Managing Users](https://docs.oracle.com/en-us/iaas/Content/Identity/users/lifecycle-managing-users.htm)

An internal workflow can be structured as follows:

~~~mermaid
flowchart TD
    N["No account"] --> C["Create account upon approval"]
    C --> W["Keep inactive if before start date"]
    C --> A["Activate when eligible"]
    W --> A
    A --> M["Update permissions on role change"]
    M --> A
    A --> D["Deactivate on suspension or departure"]
    D --> V["Review before reactivation"]
    V --> A
    D --> X["Delete per retention policy"]
~~~

Boxes such as "Keep inactive" and "Review" are business process steps, not mandatory status names shown in the Console.

Distinguish between the following states:

- **Incomplete invitation or sign-in setup:** the user has not completed onboarding steps yet.
- **Locked due to sign-in failures:** resolve the root cause and verify identity before unlocking.
- **Deactivated by an administrator:** requires an authorization decision before re-enabling activity.
- **Deleted:** the account has been removed; creating a new account with the same name should not be treated as a complete rollback of history.

Resetting a password does not substitute for an authorization decision. Unlocking an account also does not permit bypassing offboarding or access suspension workflows.

## 6. Joiner: Onboarding New Users

The goal of onboarding is to create the right account for the right person, grant the minimum required permissions, and verify the outcome.

### 6.1. Information Required Before Creation

For employee An, an onboarding request should contain:

- Employee or partner identifier and responsible manager.
- Target domain and authentication method.
- Start date; end date if on a fixed-term contract.
- Approved groups, justification for access, and resource scope.
- Applications required.
- Separate approval for privileged or production permissions.

Never share a single account across a team. Individual accounts provide traceability of who performed an action and allow access to be revoked when one member leaves the team.

### 6.2. Recommended Onboarding Sequence

1. Cross-check against the source of truth to avoid creating duplicate accounts.
2. Select the right domain before creating or synchronizing the user.
3. Create the account through an approved workflow; set the appropriate activation timing.
4. Assign approved groups; verify there are no unintended administrator roles.
5. Complete the invitation, first sign-in, and MFA according to policy.
6. Verify access to authorized resources.
7. Verify that an out-of-scope action is denied.
8. Save evidence of the account, memberships, timestamp, and executor.

A successfully sent invitation does not prove the employee has completed MFA or received the right permissions. Record notification delivery, sign-in results, and permission check results separately.

### 6.3. Keep Default Permissions Small

For An in the development team, start with a group that has necessary read access in the development environment. When infrastructure deployment is needed, the supplemental access workflow must evaluate specific actions on Compute, VCN, storage, or Database.

Do not place users into broad administrator groups merely as a quick fix for "cannot see resources." Always verify the domain, compartment, region, and policy first.

## 7. Mover: Changing Roles Without Privilege Creep

When An transfers from development to production support, simply adding new groups leaves old permissions behind. After multiple role transfers, effective permissions can grow far beyond what the current job requires.

A better management approach is to compute the delta between current permissions and newly approved permissions:

~~~text
Permissions to add    = Newly approved permissions - Current permissions
Permissions to remove = Current permissions - Newly approved permissions
~~~

This calculation must account for groups, administrator roles, applications, and any direct permission assignments. The formula only describes the governance objective and does not replace how OCI evaluates policies.

Role transfer sequence:

1. Identify responsibilities and the effective transfer date.
2. List all existing permissions along with the source of each permission.
3. Approve the new permission set and a handover window if needed.
4. Remove old permissions as planned; add new permissions during the approved transition window.
5. Verify that new actions are permitted and old actions are denied.
6. Set an expiration date for any handover exception and archive verification results.

OCI policies grant permissions through allow statements; you cannot add an arbitrary deny statement to override a permission already granted by another policy. Therefore, if An is removed from a group but still retains access, you must locate the other grant sources. [Oracle: IAM Policies Overview](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/policy-syntax.htm)

For example, An might still be able to read development resources because another group holds broader permissions at a parent compartment. Checking a single group membership is insufficient to conclude that a permission transfer is complete.

## 8. Leaver: Revoking Access on Departure

Offboarding must address both the sign-in path and all previously issued access credentials.

### 8.1. Do Not Treat Deactivate as Revoking Everything

OCI allows activating or deactivating accounts. Oracle documentation notes that a user with an active session when deactivated may still access that session with limited capabilities; once signed out, they cannot sign back in. Therefore, do not assume that Deactivate immediately terminates every session and every access path. [Oracle: Changing a User's Status](https://docs.oracle.com/en-us/iaas/Content/Identity/users/change-status-user-account.htm)

Catalog the surfaces the user actually holds:

| Surface | What to Check During Revocation |
| --- | --- |
| Corporate IdP account | Has authentication been blocked per the offboarding decision? |
| User in Identity Domain | Has the account been deactivated in the right domain and for the right identity? |
| Groups, administrator roles, app assignments | Have invalid permissions been removed? |
| Domain sign-in sessions | Have session types been handled using supported mechanisms? |
| Application sessions and tokens | Has the target application terminated or invalidated remaining access? |
| User-bound OCI credentials | Have API signing keys, auth tokens, customer secret keys, or other active credentials been inventoried and revoked? |
| Server and database access | Have SSH keys, OS accounts, and standalone SQL accounts been addressed? |
| Automation tools | Do any pipelines depend on this personal identity or secret? |

This table is a verification checklist tailored to the actual environment. Not every user holds all credential types listed above.

### 8.2. Scope of Session Clearing Operations

OCI provides a **Clear all signed-in sessions** action for **Keep me signed-in** sessions, provided that feature is enabled and the user holds such sessions. Do not interpret the action name as a guarantee that all application sessions or API tokens are invalidated. [Oracle: Clearing All Keep Me Signed-In Sessions for a User](https://docs.oracle.com/en-us/iaas/Content/Identity/users/clear-signed-in-sessions-for-users.htm)

The offboarding runbook should specify each session type, credential, and corresponding revocation evidence. If an application maintains its own session state, operators must check the session termination mechanism of that specific application.

### 8.3. Recommended Processing Sequence

1. Verify the offboarding decision and the effective termination timestamp.
2. Block authentication at the source and at the domain according to organizational design.
3. Revoke invalid privileged roles, group memberships, and application assignments.
4. Handle remaining credentials, tokens, and active sessions.
5. Revoke access to independent systems such as servers or Databases.
6. Hand over automation tasks and resource operational ownership.
7. Verify that critical access paths fail as expected.
8. Archive evidence; delete the account after satisfying retention requirements.

For urgent security incidents, prioritize paths that still permit active access first; the exact order must be documented in the organization's runbook.

Do not assume that deleting a user deletes Compute instances, buckets, or databases that the user created. Resources must be handed over and ongoing costs reviewed through a separate resource management process.

### 8.4. Reactivation Must Include a Permission Review

An account deactivated for a leave of absence can be reactivated when eligible. Before doing so, check the permissions retained during the leave and reconcile them against the new role.

For someone returning after termination, never reuse old permission grants as current approvals. Treat the return as a new business event requiring verification.

## 9. Federation, Provisioning, and JIT

These three concepts are related but solve different problems.

| Mechanism | Primary Purpose | What Not to Assume |
| --- | --- | --- |
| Federation/SSO | Allows using a configured IdP to authenticate to services | Automatically syncs all users, groups, and departures |
| Provisioning | Creates, updates, deactivates, or deletes records in target systems per integration config | One successful login proves synchronization is healthy |
| Just-in-Time provisioning | Creates or updates identities during the sign-in flow per configuration | Departure events are always handled even if the user stops signing in |

Oracle supports federating an Identity Domain with an external IdP. SAML JIT can create an account when a user signs in for the first time and can update attributes or memberships as configured. [Oracle: Managing Identity Providers](https://docs.oracle.com/en-us/iaas/Content/Identity/identityproviders/manage-identity-providers.htm), [Oracle: Adding a SAML Just-in-Time Identity Provider](https://docs.oracle.com/en-us/iaas/Content/Identity/identityproviders/add-saml-idp-jit-prov.htm)

Example:

- The company authenticates An at the corporate IdP.
- A configured provisioning mechanism pushes the required record and memberships to the domain.
- When An signs in, federation handles authentication.
- When An leaves, the offboarding flow must update the target and address associated credentials, sessions, and applications.

If you rely solely on updates during the next JIT sign-in, a departed employee who no longer signs in will never trigger the update flow the process expects. Therefore, an independent revocation flow and periodic reconciliation are required.

**SCIM**, short for System for Cross-domain Identity Management, is a standard that supports exchanging and managing users and groups between systems. In an appropriate integration, SCIM helps automate provisioning; it does not replace SSO. Supported operations and sync direction depend on the chosen connector, application, and configuration. [Oracle: Integrating Custom Applications with IAM](https://docs.oracle.com/en-us/iaas/Content/Identity/scim/overview.htm)

Before putting an integration into production, check:

- Record matching rules and how duplicate users are prevented.
- Which attributes are overwritten by the source of truth.
- How groups are mapped and how privileged groups are handled.
- How deactivation or deletion events at the source are represented at the target.
- How partial failures, retries, and alerts are handled.
- Who is responsible when integration credentials or certificates are about to expire.

Never map administrative groups from attributes that users can edit themselves. A single group-mapping mistake can grant privileged access en masse.

## 10. Desired-State Automation

Automation workflows should compare the desired state with the actual state, apply the delta, and verify again. Never simply run a sequence of "add user, add group" commands and assume completion.

The following pseudocode illustrates the idea and is not directly executable OCI commands:

~~~text
handle_event(event):
    verify_source_and_approval(event)
    user = find_by_stable_identifier(event.person_id, event.domain_id)

    desired = compute_approved_state(event)
    actual = read_current_state(user)

    changes = diff(actual, desired)
    apply_per_runbook(changes)

    verified = read_back_and_verify(desired)

    if verified:
        record_completed(event)
    else:
        record_incomplete_and_alert(event)
~~~

Key design properties:

- **Idempotent:** reprocessing the same event does not create duplicate users or memberships.
- **Ordered:** a delayed onboarding event must not accidentally reactivate someone who has already departed.
- **Reconciled:** detects drift even if a synchronization event was missed.
- **Exception-controlled:** temporary permissions have an owner, approval, and expiration date.
- **Bounded retries:** distinguishes transient errors from configuration errors requiring human intervention.
- **Readback verification:** confirms completion only when the target state matches expectations.
- **Data protection:** logs capture required identifiers and results without recording passwords or secret tokens.

These are workflow design principles. Choose APIs, connectors, and operational credentials according to the capabilities of your actual environment.

For workloads on OCI, evaluate instance principals, resource principals, and dynamic groups when supported by the service to reduce reliance on personal credentials. Workload identities must be managed according to the workload lifecycle; do not use them as a substitute for tracking human actions.

## 11. Monitoring and Operational Evidence

Monitor both sign-in activity and permission changes. Identity Domains provide reports such as successful sign-ins, failed sign-ins, inactive users, audit activity, and application access. Permission to view reports depends on assigned roles. [Oracle: Types of Reports](https://docs.oracle.com/en-us/iaas/Content/Identity/reports/understand-types-reports.htm), [Oracle: Running Reports](https://docs.oracle.com/en-us/iaas/Content/Identity/reports/run-reports.htm)

A permission change record should answer:

| Question | Suggested Evidence |
| --- | --- |
| Who or which system requested it? | Request ID and event source |
| Who approved it? | Approval tied to scope and duration |
| Which identity was changed? | Domain, user identifier, and source identifier |
| What changed? | Before and after status, groups, roles, or credentials |
| When was it applied? | Timestamp with time zone |
| Has it taken effect? | Readback and appropriate access verification |
| Did any part fail? | Failed target system, owner, and remediation deadline |

You can build the following operational metrics; these are organization-designed metrics, not a claim that OCI provides each metric out of the box:

- Time from termination decision to completed revocation.
- Number of failed provisioning requests.
- Number of accounts still active past contract end dates.
- Number of expired temporary permissions.
- Number of accounts or memberships that fail reconciliation against the source of truth.
- Number of privileged permission changes lacking valid approval.

Do not rely solely on a "no recent sign-in" report to conclude an account is inactive across all channels. API usage and credentials outside Console sessions must be reviewed using their corresponding logging sources.

Select evidence storage locations and retention periods based on organizational requirements and service capabilities. Do not assume that domain reports and OCI Audit share the same source, scope, or retention duration.

## 12. Hands-On Lab: Granting Read Access and Verifying Revocation

### 12.1. Prerequisites

Use a lab environment with:

- A domain approved by an administrator for lab use, such as Default.
- An existing test compartment named **iam-lab**.
- An administrative account authorized for the required user, group, and policy operations.
- A test mailbox under your control to complete onboarding steps if needed.
- A separate administrative session to avoid locking yourself out of management access.

This lab does not require creating Compute instances, VCNs, or Databases. If the compartment has no instances, an empty list is a valid result when verifying list permissions.

Do not modify the administrative account you are using to complete the lab. Do not use production accounts as targets for deactivation tests.

### 12.2. Execution Steps

**Step 1 — Confirm scope.**

In the Console, open Identity & Security, locate Domains, and select the target domain. Record the domain name, administrative account, and lab compartment. Screen labels or layouts may vary; always confirm the domain on the details page before modifying users.

**Step 2 — Create the lab group.**

Create the group **iam-lab-readers** in the selected domain. Do not assign any domain administrator roles to this group.

**Step 3 — Create the test account.**

Create a user, such as **an.iam.lab**, with a contact address you control. If the environment uses federation or provisioning, create it through the source of truth via the configured workflow to avoid duplicate records.

**Step 4 — Assign membership.**

Add the user to the **iam-lab-readers** group. Verify the user does not belong to other groups with broader permissions and holds no unintended administrator roles.

**Step 5 — Grant a limited policy.**

An authorized administrator creates a policy in the appropriate scope, such as at root for the approved lab:

~~~text
Allow group 'Default'/'iam-lab-readers' to read instances in compartment iam-lab
~~~

If the domain or compartment has a different name, substitute the exact identifiers. Do not alter existing administrator group policies for this exercise.

**Step 6 — Complete sign-in.**

Open a separate browser session, sign in as the test user, and complete authentication steps per policy. Verify the correct tenancy, domain, region, and compartment.

**Step 7 — Verify permitted access.**

Open the Compute instances list in the lab compartment. Record the outcome:

- Listing succeeds, possibly returning an empty list.
- No permission to view another component not granted by the exercise.
- Or the list instances request is denied and requires investigation.

Only the first outcome proves the read test passed. Missing related data in the UI is not a reason to automatically grant broader permissions.

**Step 8 — Verify permission boundaries.**

Verify the user cannot modify configurations or administer other users. Do not create billable resources solely to test a denied action. You can use policy evidence and a read request against an existing out-of-scope resource designated by the instructor.

If no out-of-scope resource exists for testing, note explicitly that that check was not performed; do not treat an empty list as evidence of denied access.

**Step 9 — Revoke membership.**

In the separate administrative session, remove the user from the lab group. Re-check membership and the read operation in an appropriate session after the change has been applied. If access persists, look for other groups, other policies, or unpropagated state at the target.

Do not commit to a fixed number of seconds for all permission changes. If the result remains incorrect after the runbook's wait threshold expires, log an issue for investigation.

**Step 10 — Practice deactivation.**

Deactivate the test user and verify that a new sign-in attempt is blocked. Handle any sessions or credentials created during the lab scope. This result is distinct from checking loss of read permission in step 9.

**Step 11 — Cleanup.**

Following your environment's process, delete the test user after saving required evidence, remove the lab policy, and delete the group once it is no longer referenced. Clean up only objects created for the exercise; do not delete shared compartments or resources.

### 12.3. Completion Criteria

The lab passes when evidence exists for all three items:

1. The user is identified in the correct domain.
2. The user receives only the approved read permission within the lab scope.
3. Group membership and sign-in capability are revoked through separate verification steps.

Do not capture or store passwords, secrets, MFA codes, or tokens in the lab records.

## 13. Troubleshooting Common Scenarios

| Scenario | Cause to Check | Remediation |
| --- | --- | --- |
| User not found | In the wrong domain or sync not yet complete | Confirm domain and source identifier |
| Signed in successfully but cannot see instances | Missing policy, wrong compartment, or wrong region | Check scope and permissions in sequence |
| Group exists but policy does not grant expected access | Referenced wrong domain or group | Reconcile policy subject with actual group |
| Removed a group but user still has access | Another permission grant source exists | Review all related memberships, roles, and policies |
| Newly deactivated user still has a session | Previously established session remains | Handle each session type using supported mechanisms |
| Cannot sign in to Console but other access remains | Credentials or target accounts managed separately | Inventory each channel and verify revocation |
| Attribute edited locally gets reverted | Provisioning source overwrites it | Update at the source of truth or adjust sync rules |
| Terminated in HR system but OCI user remains active | Broken revocation flow or mismatched record mapping | Remediate urgently based on risk and fix integration |
| New user has overly broad permissions | Wrong default group, mapping, or role | Revoke excess permissions and fix grant root cause |
| Repeated unlocks still fail | Stale credentials or faulty auth configuration | Investigate sign-in source before continuing unlocks |

When troubleshooting, separate the question "has authentication succeeded?" from "is this action authorized?" That separation avoids editing policies to fix password errors or resetting MFA to fix missing resource permissions.

## 14. Relationship to Cost and Availability

Identity lifecycle management directly affects OCI infrastructure operations:

- **Cost:** overly broad resource creation permissions or unrevoked stale accounts can lead to unplanned resources. Deleting a user does not substitute for resource and budget inventories.
- **Administrative availability:** if only one person holds privileges or all logins depend on a single failing integration, the operations team can lose the ability to respond to incidents.
- **Workload availability:** pipelines using personal credentials can break when the owner leaves.
- **Investigability:** individual accounts, change trails, and approval records help establish accountability during incidents.

An operational design should maintain multiple appropriately authorized administrators, controlled break-glass accounts, and procedures to verify access when the IdP experiences an outage. Break-glass accounts must be protected, monitored, and reviewed; do not use them for daily work.

Before major federation or sign-on rule changes, test on a small group and keep an approved rollback path. For automation, define workload ownership so handover does not depend on a specific employee.

## 15. Self-Check Questions

1. Why doesn't a user in an Identity Domain automatically have permission to manage resources in a compartment of the same name?
2. Is someone with the User administrator role necessarily allowed to create Compute instances?
3. If An transfers teams, why is simply adding a new group membership insufficient?
4. Why doesn't a successful SSO login prove that provisioning and offboarding are working?
5. Can you conclude all access channels have been revoked simply by deactivating a user?
6. What should you check if a group was removed yet the user can still read resources?
7. Does deleting a user resolve the costs of running instances or Databases?
8. What evidence distinguishes a submitted revocation request from an actually completed revocation?

A sound design must connect the entire chain: **right identity → right authentication → right permissions → event-driven changes → verified revocation**. On OCI, this chain requires coordinating Identity Domains, groups, administrator roles, IAM policies, credentials, and the target systems users access.
