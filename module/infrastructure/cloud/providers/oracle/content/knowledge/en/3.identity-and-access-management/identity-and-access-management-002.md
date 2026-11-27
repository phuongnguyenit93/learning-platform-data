# Groups, Application Roles, and Segregation of Duties

One engineer needs to view Compute configurations to diagnose an incident, an operator needs to monitor an integrated application, and another person is responsible for approving production deployments. If all three are added to a tenancy-wide administrator group, the work can be done, but accountability and blast radius are no longer clear.

In Oracle Cloud Infrastructure (OCI), groups help organize identities that share similar access needs. A member's permissions can come from IAM policies, identity domain administrator roles, or application roles assigned to a group. These mechanisms have different scopes; a group name or role name alone is not enough to conclude what a person is permitted to do.

This lesson belongs to the **IAM Identity and Access Management** chapter in **CLOUD_PROVIDERS_ORACLE**. The goal is to design how permissions are granted for OCI infrastructure and applications while segregating potentially conflicting duties. These choices directly affect the operation of VCN, Compute, storage, Oracle database services, monitoring, and automation.

## 1. Distinguishing Group, Policy, and Role

| Component | Role | Example |
| --- | --- | --- |
| User | Identity of a person using the system | Operations engineer An |
| Group | Collection of identities for managing memberships and assigning group-based permissions | `ShopComputeReaders` |
| OCI IAM policy | Rules defining actions on OCI resources and their applicable scope | Allow a group to read instances in a compartment |
| Application role | Permissions or permission set defined by an application/service | Monitor role in an Oracle Integration instance |
| Identity domain administrator role | Role-based permissions to administer identities and identity domain settings | User administrator |
| Database role | Permissions inside a database management system | Role granted to a database connection account |

The rows in this table represent lenses for analyzing permissions, not a claim that every role type is implemented by a completely independent technical mechanism. What must be determined is **which system enforces permissions, on which objects, and within which scope**.

One person can belong to multiple groups. A single group can also be referenced in multiple IAM policies or assigned multiple application roles. Therefore, creating an additional "low-privilege" group does not narrow the permissions a person already receives through other paths.

Questions that must be answered separately:

- What does a successful sign-in prove? The identity has been authenticated under the active sign-in flow.
- What does belonging to a group prove? The identity holds membership in a collection.
- What does being allowed to perform an action prove? The target system accepted authorization for the specific action, resource, and context.

You cannot substitute checking the first two questions for answering the third.

## 2. Tracing Permission Paths

You can use the following diagram to read an authorization design:

```text
User
  ├── Member of group A
  │     └── IAM policy
  │           └── Actions on OCI resources within the granted scope
  │
  ├── Member of group B
  │     └── Application role of application X
  │           └── Functions permitted by application X
  │
  ├── Directly assigned application role
  │     └── Functions of the corresponding application
  │
  └── Identity domain administrator role, directly or via group
        └── Identity administration tasks within the relevant scope
```

This diagram illustrates the paths to inspect; it does not assert that all applications use the same role or token mechanism. An application may maintain its own internal authorization model after receiving an identity through SSO.

### 2.1. Groups in IAM Policies

The following example grants read access to `instances` resources for a group in a hypothetical identity domain `LearningDomain`:

```text
Allow group 'LearningDomain'/'ShopComputeReaders' to read instances in compartment id <DEV_COMPARTMENT_OCID>
```

Replace the domain name, group name, and placeholder with actual values. The statement illustrates a read-only scope on instances; it does not automatically grant permission to read database contents, edit VCNs, or manage identities.

Specifying the identity domain when referencing a group prevents confusion between groups with the same name. OCI also supports referencing groups by identifier according to policy syntax; display names and identifiers must be verified against the exact target object. See [Policy Syntax](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/policysyntax.htm).

Permissions granted at a parent compartment can propagate down to child compartments. A narrower new policy does not revoke a broader grant already present at a higher level. When auditing an account, evaluate all relevant groups and policy inheritance paths. See [Policy Inheritance](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Policy_Inheritance.htm).

### 2.2. Groups Assigned Application Roles

For example, the group `ShopIntegrationMonitors` is assigned a monitor role on an Oracle application integrated with the identity domain. Members receive the corresponding in-application permissions according to that service's role assignment model.

This does not automatically generate an IAM policy allowing Compute reads or Object Storage edits. Likewise, permission to create service resources in OCI should not be used as proof that a user possesses every function inside the application provided by that service.

Oracle Integration documentation distinguishes OCI resource administrators from users holding service roles inside an instance. This is a practical example of two scopes that must be designed separately. See [Learn About Users and Resources](https://docs.oracle.com/en/cloud/paas/application-integration/security/learn-users-resources.html).

### 2.3. Identity Domain Administrator Roles

Identity domain administrator roles delegate tasks such as managing users, applications, or security configurations. Representative roles include:

| Role | Permission Focus |
| --- | --- |
| Identity domain administrator | Full administration of the associated identity domain |
| User administrator | Manage users, groups, and memberships in the domain |
| Application administrator | Manage applications and grant/revoke application access |
| Security administrator | Manage security configuration and settings of the domain |
| Audit administrator | Run identity domain reports |

This table is a summary to distinguish responsibilities; read the full scope of a role before granting it. See [Understanding Administrator Roles](https://docs.oracle.com/en-us/iaas/Content/Identity/roles/understand-administrator-roles.htm).

For domains other than Default, Identity domain administrator permissions are scoped to that domain and are not inherently tenancy-wide administration. For the Default domain and initial administrative identities, review the associated privileges and policies rather than mechanically applying conclusions from secondary domains. OCI evaluates both policies and administrator roles when determining relevant permissions. See [Overview of IAM](https://docs.oracle.com/en-us/iaas/Content/Identity/getstarted/identity-domains.htm).

Do not remove someone from a group and assume they have lost an administrator role. Direct assignments or assignments through another group may still remain. Oracle documentation notes that certain administrative groups are linked to roles, but assigning a role directly does not mean the person is added to the corresponding group. See [Groups](https://docs.oracle.com/en-us/iaas/Content/Identity/conversion/groups.htm).

## 3. Designing Groups by Job Function and Scope

### 3.1. Each Group Should Have One Clear Governance Purpose

Instead of using a single `IT-Team` group to receive every permission, separate it into:

| Illustrative Group | Purpose | Do Not Assume |
| --- | --- | --- |
| `ShopDevComputeReaders` | Read Compute details for the dev environment | Has permission to edit or delete instances |
| `ShopProdOperators` | Perform analyzed production operations | Has permission to manage IAM |
| `ShopIntegrationMonitors` | Receive the monitor role for a specific integrated app | Has permissions across all other apps |
| `ShopReleaseApprovers` | Represent approvers in a release workflow | OCI automatically blocks all self-approval |
| `ShopAccessReviewers` | Inspect evidence and review assigned access | Can edit memberships or grant roles |

These group names are example conventions, not mandatory OCI defaults. A group holds only the intended permissions when policies, role assignments, and applications enforce the design accurately.

There is no need to create a group per user or per API if doing so makes the model unwieldy. Group similar tasks together while separating across different environments, resource scopes, sensitivity levels, or approvers.

### 3.2. Document the Owner and Grant Paths

Each group should document at minimum:

- Purpose and environment scope.
- Business or technical owner.
- Membership management source: in OCI or an external identity system.
- Assigned policies, administrator roles, and application roles.
- Eligibility criteria, approver, and expiration date if temporary access.
- Conflicting groups or duties to check.
- Revocation procedure and person responsible for verification.

If memberships are synchronized from an IdP or source system, determine where changes are authorized. Manual removal at the target while the source still grants membership can cause the membership to return on the next sync cycle. Sync behavior and mappings must be verified against the active integration.

In particular, evaluate carefully before assigning sensitive permissions to a group with a very broad membership, such as a group containing all users in a domain. Onboarding convenience does not offset accidentally granting access to people without the corresponding responsibility.

### 3.3. Anyone Editing Memberships Participates in Access Granting

A policy can be very tight yet still be rendered ineffective from a governance standpoint if anyone can add themselves to the group receiving that policy. The same applies to groups assigned powerful application roles.

Verify the exact actions delegated: can a group manager edit memberships of sensitive groups, add their own alternate account, and do changes require a second approver? Do not infer the answer merely from a job title like "user administrator."

The sensitivity of group management permissions depends on **the permissions behind the group**, not only the number of members or the group's name.

## 4. Understanding Application Roles in Their Specific Scope

### 4.1. Application Roles Have Meaning Within a Specific Scope

An application role is not a "universal role across all of Oracle Cloud." To read an assignment accurately, you must know:

- Which application or service instance owns the role.
- Which functions the role permits in the active version and feature set.
- Whether the assignment is direct to a user or indirect via a group.
- Whether other roles, internal permissions, or mappings broaden access.
- Whether permissions are provisioned to the application or evaluated at access time.

A real-world example from Oracle Integration:

| Role | General Meaning Within an Instance |
| --- | --- |
| `ServiceMonitor` | Monitor features supported for the role |
| `ServiceDeveloper` | Develop components permitted by the corresponding feature |
| `ServiceAdministrator` | Administer features provided within the instance |

Detailed permissions vary by feature. Do not read the name `ServiceDeployer` and conclude it deploys all integrations; current documentation restricts this role to RPA and states it does not apply to the Integrations feature. See [Oracle Integration: Service Roles](https://docs.oracle.com/en-us/iaas/application-integration/doc/oracle-integration-roles.html).

For other services, role names and custom role capabilities may differ. Do not invent an application role name and assume it can be added to every Oracle application. If built-in roles are too broad, examine what granular authorization the service actually supports or add controls in the surrounding process.

### 4.2. Prefer Group Assignment Where Appropriate

Assigning roles via groups allows personnel changes without editing every application assignment individually. Example model:

```text
An, Binh
    └── ShopIntegrationMonitors
          └── ServiceMonitor of the assigned integration instance
```

If An changes duties, an administrator revokes the appropriate membership and re-verifies permissions. However, An might still retain the role through a direct assignment or another group. A single group's member list is only part of the evidence.

Direct assignments may be needed for specific cases, but they should be documented with justification, approver, and expiration. Avoid a normal workflow that uses groups while special cases accumulate unreviewed direct permissions.

When importing assignments, distinguish creating a role from adding members to an existing role. The import users/groups feature for Oracle application roles imports **memberships**; the role must already exist. See [Importing Users and Groups for Oracle Application Roles](https://docs.oracle.com/en-us/iaas/Content/Identity/datatransfer/import-users-and-groups-oracle-application-roles.htm).

### 4.3. SSO, OAuth Scopes, and Application Roles Are Not Identical

SSO lets an application receive an authenticated identity. The application still needs to determine which business operations that person is allowed to perform. Seeing an application tile or completing sign-in does not prove permission to approve, configure, or read sensitive data.

For custom applications, the development team must define the integration contract: where roles come from, which claims are trusted, whether an API is called to fetch permissions, and who maintains the mapping to internal permissions. Do not assume every token automatically contains all groups or application roles.

An OAuth scope is one component of an API authorization mechanism. It is not an interchangeable synonym for every application role. Inspect the client configuration, target resource, and how the application validates tokens rather than just looking for a string resembling a role name.

## 5. What Is Segregation of Duties?

Segregation/Separation of Duties (**SoD**) restricts a single person from completing a sequence of actions that could cause abuse or error without an independent check.

Examples:

- Someone requesting production access does not approve their own request.
- Someone preparing a change does not approve that same change.
- Someone undergoing an access review does not certify all of their own permissions.
- Someone deploying applications cannot arbitrarily alter pipeline approval mechanisms and grant configurations.

SoD is different from simply splitting into multiple groups. Two differently named groups where the same person owns all permissions can still create a conflict.

### 5.1. Static and Transactional Segregation

| Segregation Approach | Illustrative Rule | Where It Must Be Enforced |
| --- | --- | --- |
| Static | One person cannot simultaneously hold two conflicting permission packages in the same scope | Provisioning workflows, governance tools, or entitlement management systems |
| Transactional | One person may perform multiple roles but cannot approve a request they created themselves | Business logic or workflows validating each transaction |
| By environment | Development permissions do not automatically open production deployment permissions | Groups, policies, role assignments, and deployment paths |
| By administration | Users of sensitive permissions cannot modify the mechanism granting those permissions | Administrative permissions and change control |
| By evidence | Performers of an activity do not have full control over where audit evidence is stored | Evidence collection, access, and protection design |

In this lesson, "static" and "transactional" are SoD design patterns, not a claim that OCI automatically generates exclusion rules from group names alone.

One person may hold multiple accounts across multiple domains. When the requirement is segregation between **two independent people**, using two usernames belonging to the same person does not satisfy the requirement. There must be a way to link accounts to real individuals within the organization's governance boundary.

### 5.2. Prohibit Only Genuinely Conflicting Combinations

Not every dual responsibility is a problem. A developer who also has monitoring access in a dev environment can be a normal operational need.

A conflict rule should follow this structure:

```text
Two conflicting duties
+ System or data scope
+ Environment
+ Acceptable conditions
+ Detection and remediation method
```

For example, "preparing and self-approving the same Shop production release" is clearer than "cannot be both a developer and an operator." Overly broad rules can disrupt legitimate work and produce excessive hard-to-manage exceptions.

### 5.3. Distinguish Preventive and Detective Controls

Preventive controls reject an action before it completes, such as a backend blocking a requester from approving their own request.

Detective controls identify issues after they occur, such as a report showing that one person simultaneously holds two conflicting permission packages. Reports are valuable, but they do not replace a mandatory approval gate when business rules require prevention upfront.

Every rule should state clearly which type it is. An email sent to an audit team after deployment does not have the same effect as blocking an unapproved deployment.

## 6. Designing a Release Process with Segregation of Duties

Suppose Shop has a release request portal, a deployment pipeline into OCI, and an integrated application to track related workflows. The groups below are an illustrative organizational model, not a list of built-in OCI roles.

| Job Role | Primary Responsibility | Permissions to Segregate |
| --- | --- | --- |
| Change preparer | Create requests and supply artifacts to deploy | Self-approving their own requests |
| Approver | Review and approve identified contents | Modifying artifacts after approval without re-approval |
| Pipeline identity | Deploy authorized contents into the assigned OCI scope | Generating human approval evidence itself |
| Access administrator | Execute approved membership/assignment changes | Self-approving sensitive permissions for themselves |
| Reviewer | Read evidence and evaluate exceptions | Modifying outcomes or the storage of evidence under review |

A pipeline identity is a purpose-built automation identity, not by default a human user in a group. How permissions are granted to workloads must fit the execution service; do not use a shared staff password as a deployment mechanism.

### 6.1. Groups Solve Only Part of the Model

You can create `ShopReleaseRequesters` and `ShopReleaseApprovers` groups to represent two populations. A custom release portal must map them to corresponding business permissions and enforce conditions on each request.

The pseudocode below illustrates the required server-side logic:

```text
On approval:
    authenticate the actor
    verify approval permission for Shop production
    verify approver is not the request creator
    verify request is still in an approvable state
    record approver, request ID, artifact identifier, and timestamp

On deployment:
    verify a valid and active approval exists
    verify artifact matches the approved version
    verify deployment scope matches the approved scope
    deploy using an appropriately authorized pipeline identity
    record outcome linked to request, approval, and artifact
```

Identity, creator information, and approval state must come from server-verified sources. Never trust an `approved=true` field or approver name sent arbitrarily by a client. Checking and updating state must prevent race conditions where request contents change during approval.

If using an off-the-shelf workflow platform, verify its configuration capabilities rather than tacking logic onto a secondary UI. Hiding an Approve button in the UI is insufficient if the underlying API still permits the call.

### 6.2. Protect Paths Outside the Pipeline Too

Someone who cannot click Deploy in the pipeline but has direct permission to modify production workloads can still deploy via CLI or API. In that case, the pipeline approval gate does not cover the full execution surface.

Evaluate simultaneously:

- Human permissions on production resources.
- Permissions to use or modify the deployment identity.
- Permissions to modify the pipeline and approval rules.
- Permissions to alter artifacts or configuration variables after approval.
- Permissions to modify memberships of groups holding access to these components.

This does not mean removing all direct operational access. Break-fix actions may be necessary, but they must be designed as an access path with clear ownership, scope, and evidence.

### 6.3. Controlling Exceptions and Emergency Access

A small organization may not have enough staff to separate every duty. When an exception is needed, clearly define an independent approver, duration, impact scope, and post-event review. Unrecorded long-lived exceptions easily become the default permission model.

Powerful administrative accounts or groups should be governed under the organization's privileged access mechanisms. Oracle recommends not using tenancy-wide administrator accounts for daily work and delegating by responsibility. See [Security: OCI Administrators Group](https://docs.oracle.com/en-us/iaas/Content/Identity/conversion/security.htm).

Segregation of duties must not destroy the ability to recover administrative access. Do not practice by deleting OCI-protected admin groups or revoking all domain/tenancy management paths.

## 7. Verifying Effective Permissions Before Concluding Segregation

### 7.1. Evaluate Per Target System

Do not create a single flat sum and treat all OCI permissions and application permissions as one set checked in one place. For each action, identify which system makes the authorization decision and which sources it consults.

| Action to Verify | Permission Paths to Trace |
| --- | --- |
| Read instance details | Identity, memberships, IAM policies, compartment, and related conditions |
| Manage identities | Domain administrator roles and related IAM policies |
| Monitor integrated application | Role of the specific application/service instance, assignments, and feature-level permissions |
| Approve release request | Business permissions and workflow approval conditions |
| Deploy via pipeline | Trigger permissions, approval rules, execution identity, and resource policies |

When analyzing a user, look for all of:

- Groups assigned directly or managed through identity integrations.
- Application role assignments both direct and through different groups.
- Identity domain administrator roles.
- Broader policies at parent compartments or the tenancy.
- Permissions inside the application itself and other authorization mechanisms the application supports.

OCI provides IAM deny policies as an opt-in feature. If a tenancy uses deny policies, factor them in when evaluating OCI permissions. However, deny policies do not replace designing every permission layer; Oracle documentation states that deny policies do not override identity domain administration roles. See [Deny Policies](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/denypolicies.htm) and [Deny Policies Known Issues](https://docs.oracle.com/en-us/iaas/Content/Identity/known-issues/known-issues-deny-policies.htm).

### 7.2. Use Both Positive and Negative Tests

Testing only positive scenarios misses excess permissions. For example, a Compute reader account should be able to read instances within the lab scope while failing to read instances outside that scope unless another grant exists.

Use accounts representative of the intended permission set. A tenancy-wide administrator account is not an appropriate tool to prove that a restricted user is blocked.

Do not rely solely on a hidden button or an empty list to prove lack of access. Verify the exact action, resource identifier, compartment, region, and application instance. A "resource not found" error can relate to permissions as well as an incorrect identifier or location.

## 8. Hands-On Lab: Separating Compute Permissions, Application Roles, and Approvals

### 8.1. Prepare the Lab Scope

Prepare:

- An identity domain approved for lesson use.
- An administrative account to set up the lab and two test accounts without broad administrative rights.
- A lab compartment along with a sample instance whose OCID is known.
- Another sample instance in a lab compartment outside the granted scope to test denied access.
- If practicing application roles: an existing Oracle application/service instance available and authorized for testing, along with that service's role documentation.

Do not create paid services solely to test the application role portion. If no suitable application is available in the environment, complete the assignment design portion and explicitly note that the application permission path was not tested live.

If one person uses two accounts to learn how to test, that simulates roles. That result does not prove the organization has two independent people performing the duties.

### 8.2. Create Groups and Record Intended Assignments

Create two groups in the right domain:

| Lab Group | Intended Assignment |
| --- | --- |
| `LabComputeReaders` | IAM policy to read instances in the assigned lab compartment |
| `LabAppMonitors` | Monitor application role of the exact test application |

In the Console, open the domain, go to Groups management, and create groups with clear names and descriptions. Then add each test account to its respective group. Do not pick an existing group just because its name looks similar without verifying its owner and existing assignments. See [Creating a Group](https://docs.oracle.com/en-us/iaas/Content/Identity/groups/create-groups.htm).

The initial state summary should show:

```text
lab-reader  -> LabComputeReaders
lab-monitor -> LabAppMonitors

lab-reader:
  no monitor application role via another path

lab-monitor:
  no Compute read policy via groups or other broad permissions
```

This is a state to verify, not something automatically guaranteed by account names.

### 8.3. Assign the Properly Scoped OCI Policy

A person authorized to manage policies creates the following statement at the appropriate policy attachment point:

```text
Allow group 'LearningDomain'/'LabComputeReaders' to read instances in compartment id <LAB_COMPARTMENT_OCID>
```

Replace `LearningDomain` and the placeholder with your lab values. Use the lesson's dedicated compartment; do not broaden to `in tenancy` just to bypass missing permission errors.

If a reader using the Console cannot see a required selector or dependent detail, analyze each missing requirement individually. Never turn an observation grant into `manage all-resources`.

### 8.4. Assign the Application Role to a Separate Group

For the application authorized for practice:

1. Confirm the exact identity domain and the exact application or service instance.
2. Open the application roles management section of that application.
3. Choose a monitor or view-only role actually supported by the service.
4. Assign the `LabAppMonitors` group to the role via the service's administrative workflow.
5. Check the list of directly assigned groups and users.
6. Sign in as `lab-monitor` to verify permitted functions and restricted functions.

If using Oracle Integration, consider `ServiceMonitor` according to your environment's feature scope. Do not invent a role named `Monitor` or switch to `ServiceAdministrator` just because you have not located the right screen yet.

Assigning a group to an application and assigning a group to an application role are distinct operations depending on the service's model. The lab procedure must verify the actual role granted rather than merely recording "added group to app."

### 8.5. Test OCI Access with the Right Account

You can use an OCI CLI profile configured for `lab-reader`. The following commands are read-only:

```powershell
# Replace the placeholders with your actual lab values.
oci compute instance get `
    --instance-id '<IN_SCOPE_LAB_INSTANCE>' `
    --region '<REGION_IDENTIFIER>' `
    --profile 'lab-reader'

# Test a sample resource outside the granted scope.
oci compute instance get `
    --instance-id '<OUT_OF_SCOPE_LAB_INSTANCE>' `
    --region '<REGION_IDENTIFIER>' `
    --profile 'lab-reader'
```

The first command is expected to succeed once the grant is active and all identifiers are correct. The second command is expected to be denied under the lab model with no out-of-scope grants.

To determine why a test was denied, the administrator verifies that the resource genuinely exists in the recorded region and compartment. Do not broaden the policy before verifying these conditions.

### 8.6. Verify All Three Responsibility Scopes

| Scenario | Expected Result per Lab Design |
| --- | --- |
| `lab-reader` reads an in-scope instance | Succeeds |
| `lab-reader` reads an out-of-scope instance | Denied if no other grant exists |
| `lab-reader` accesses app feature needing monitor role | Not granted merely by Compute read policy |
| `lab-monitor` uses assigned monitoring function | Succeeds in the assigned application |
| `lab-monitor` reads Compute without corresponding policy | Denied |
| Request creator self-approves | Denied if workflow enforces SoD rule |
| Another authorized approver approves a valid request | Succeeds if business conditions are met |
| Artifact is modified after approval | Requires re-approval per workflow design |

The two approval scenarios and the artifact scenario can only be tested live when a corresponding workflow exists. Creating groups in OCI does not implement these controls automatically.

Record evidence separately for what was actually tested and what was only designed. Do not mark application roles or SoD as verified solely from Compute read results.

## 9. Managing the Grant and Revocation Lifecycle

### 9.1. Grant Permissions Through Accountable Requests

An access request should state:

- Recipient and corresponding identity/domain.
- Job to perform, systems, and environments involved.
- Group or application role to receive.
- Approver and change executor.
- Start date, expiration date if applicable, and revocation conditions.
- Segregation of duties conflict check result.

Separating the approver from the change executor prevents a technical operation from being mistaken for a business authorization decision. Someone able to add a member is not necessarily authorized to approve granting that permission.

### 9.2. Revoke All Related Permission Paths

When someone changes roles or leaves a project, follow the documented list of grant paths:

1. Update the authoritative membership source if synchronization is used.
2. Revoke memberships that are no longer needed.
3. Check direct application role assignments and assignments via other groups.
4. Check identity domain administrator roles.
5. Evaluate associated sessions, tokens, and credentials per access type.
6. Retry the action that must be blocked after the change has been applied.
7. Archive evidence and close the request.

Removing a membership does not invalidate every session or credential. With OAuth, access tokens may be validated by resource servers without re-querying the identity domain; long-lived tokens must be accounted for in revocation plans. Oracle recommends designing appropriate access token lifetimes and handling refresh tokens when timely revocation is required. See [Managing Authorization Using the API](https://docs.oracle.com/en-us/iaas/Content/Identity/api-getstarted/api-managing-authorization.htm).

Do not apply a single generic "sign out" action across all applications and conclude all permissions are revoked. Application sessions, SSO sessions, and credential types have different lifecycles. Verify against the access paths the person actually uses.

If revoking only one duty while the user continues working on other tasks, avoid deleting accounts or credentials indiscriminately. The revocation scope must match the access decision and context.

### 9.3. Periodic Reviews and Evidence

Reviews should trace **person → group → policy/role → actual actions**, rather than just counting groups. Pay special attention to direct grants, unrevoked emergency access, and changes in permissions behind an existing group.

Identity domains provide the **Application Role Privileges** report to view grants and revocations of application roles for users and groups. The Audit Log report helps inspect recorded administrative and sign-in activities. See [Types of Reports](https://docs.oracle.com/en-us/iaas/Content/Identity/reports/understand-types-reports.htm).

Useful evidence includes the actor, target object, before/after state, timestamp, reason, and link to approval. For pipelines, also link the configuration version, artifact, and execution identity. Do not assume a single log source can prove every action across all systems.

If the organization has deployed an access governance tool, use it to assist reviews and access orchestration. A tool is only valuable when it collects complete data and its rules reflect actual work scopes; creating groups does not automatically enable such a governance system.

## 10. Common Mistakes

| Mistake | Consequence | Correction |
| --- | --- | --- |
| Treating a group named `Admin` as a fixed permission type | Misunderstanding effective permissions | Trace policies and all role assignments |
| Sharing one group across unrelated systems | Adding a member for one task opens many other permissions | Split by job package and owned scope |
| Confusing application roles with IAM policies | Users receive the wrong layer of access or still cannot perform tasks | Identify which system authorizes each action |
| Creating an Approver group and assuming SoD exists | Creators can still self-approve via app or API | Enforce and test rules in the workflow |
| Checking only account names | One person uses multiple accounts to hold conflicting duties | Link to real individuals when two independent people are required |
| Separating deployers without separating pipeline editors | Approval gates can be bypassed | Control permissions to alter execution mechanisms |
| Removing one membership and closing the revocation ticket | Direct assignments or other paths still remain | Inspect all related permission paths |
| Testing permissions with a full-privilege account | Fails to catch over- or under-provisioning for normal users | Use an identity representing the exact target permission set |
| Equating Audit administrator with all OCI read access | Reviewers lack proper evidence or hold excess privileges | Distinguish domain reports, OCI resources, and app data |
| Requiring MFA and treating it as segregation of duties | One person can still execute the entire action chain alone | Design authentication and duty segregation separately |

## 11. Design Completion Criteria

A design for groups, application roles, and SoD is ready for operations when:

- Every group and role assignment has a defined purpose, scope, and owner.
- The model distinguishes OCI permissions, application permissions, and identity administration permissions.
- Membership/assignment administrators are authorized according to analyzed responsibilities.
- Conflicting duty combinations are defined by system, environment, and business process.
- Provisioning-time and transaction-time controls are documented at their actual enforcement points.
- Execution paths outside pipelines or primary UIs have been evaluated.
- Positive tests, negative tests, and post-revocation tests exist.
- Exception, emergency access, and evidence review processes are in place.
- Newly designed portions and live-verified portions are clearly distinguished in records.

The target outcome is that users can perform their jobs while action chains requiring independent oversight genuinely require independent participation. Groups and application roles are tools for representing, granting, and managing permissions; the quality of duty segregation depends on both how permissions are organized and how each system enforces workflows.
