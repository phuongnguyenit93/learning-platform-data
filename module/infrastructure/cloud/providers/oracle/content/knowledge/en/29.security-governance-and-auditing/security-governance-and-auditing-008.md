# Periodic access reviews and emergency access procedures

## 1. Objectives and overarching scenario

An Oracle Cloud Infrastructure (OCI) system may be properly authorized at deployment time yet gradually accumulate excess permissions: staff transfer teams while retaining production access, pipeline accounts lose their owners, or an incident-response grant is never revoked. At the same time, the organization still needs to restore access when an external identity provider fails or regular administrators are unavailable.

In the **Security, Governance, and Auditing** chapter of the `CLOUD_PROVIDERS_ORACLE` module, this lesson connects two practices: periodically confirming that permissions remain necessary and preparing controlled emergency access paths. The scope covers tenancy, compartments, IAM, infrastructure deployment identities, and operational evidence for OCI workloads.

After this lesson, learners will be able to:

- Scope access reviews across users, groups, policies, identity domain roles, and machine identities.
- Trace effective permissions back to their grant source, including inherited permissions or memberships in other groups.
- Record keep, reduce, or revoke decisions with owners and execution evidence.
- Design emergency access for scenarios where normal authorization paths still work or have failed.
- Verify revocation, close incidents, and preserve access recovery capabilities.

**Scenario:** an enterprise operates a Java application in compartment `ProductionApps`. The application uses Compute, Object Storage, and an Oracle Database; the network team manages the VCN in another compartment. Employees log in via the corporate IdP, while deployment pipelines have dedicated identities. At quarter-end, the security team discovers an engineer who transferred teams still has permissions to update production infrastructure. In another incident, an IdP outage prevents on-call engineers from signing into the OCI Console.

Both scenarios share the same foundation: knowing where permissions come from, who owns them, and what evidence proves permissions are under control.

## 2. Access reviews must inspect effective permissions

### 2.1. Model of an access decision

The grant path can be described as follows:

```text
Identity or resource calling an API
→ Group, federation mapping, or dynamic group
→ Policy statements and applicability conditions
→ Resource type, verb/operation, and compartment scope
→ Usable permissions in a specific context
```

For identity domain administration, also include the path via administrator roles. Do not treat a single group membership list as a proxy for all permissions.

An example policy to read Compute information:

```text
Allow group Workforce/ProdObservers to read instance-family in compartment ProductionApps
```

`Workforce` and `ProdObservers` are illustrative domain and group names. OCI lets you identify groups by domain/group pair or OCID; record the exact identifier to avoid confusing similarly named groups across two domains. [Oracle: Subjects](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/subject.htm).

When a reviewer evaluates this policy line, the questions to answer include: who belongs to the group, does the read need still exist, is the compartment scope appropriate, and does that person receive stronger permissions from somewhere else?

### 2.2. Additive and inherited permissions

OCI IAM policies grant permissions via `Allow` statements. Permissions needed for an operation can come from multiple statements or multiple groups; adding a narrow policy does not automatically cancel broader permissions granted elsewhere. Inappropriate grant paths must be removed or narrowed. [Oracle: IAM Policies Overview](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/policy-syntax.htm).

Child compartments inherit effects of policies applied at parent scopes. Therefore, reviewing only policies located in `ProductionApps` can miss permissions granted at the tenancy or an ancestor compartment. [Oracle: Policy Inheritance](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Policy_Inheritance.htm).

Example of engineer An having two access paths:

```text
An → Workforce/ProdObservers → read Compute in ProductionApps
An → Workforce/LegacyOperators → manage Compute at a parent scope
```

Removing An from `ProdObservers` does not remove administrative permissions. Revocation conclusions must rely on the remaining set of grant paths and an appropriate live verification test.

### 2.3. Distinguishing domain administration from tenancy administration

Identity domain administrator roles and OCI resource management policies have different scopes. An administrator role may allow managing users, groups, applications, or authentication configs within a domain; these privileges must also be included in reviews. [Oracle: Understanding Administrator Roles](https://docs.oracle.com/en-us/iaas/Content/Identity/roles/understand-administrator-roles.htm).

The Default identity domain contains the `Administrators` group with tenancy-wide admin rights. Conversely, admin rights over another domain do not automatically mean tenancy-wide administration. OCI requires the `Administrators` group to always have at least one member; never rely on removing the last member as a way to end emergency access. [Oracle: The Default Identity Domain](https://docs.oracle.com/en-us/iaas/Content/Identity/domains/the_default_domain.htm).

For the Java application in this lesson, OCI permissions to manage a DB system must also be distinguished from SQL accounts, database roles, OS accounts, and in-application permissions. Reviews must clearly state which layers were checked and which follow separate processes.

## 3. Setting scope, responsibilities, and cadence

### 3.1. Unit of review

A useful review unit is a permission relationship with complete context:

```text
Identity + grant source + resource scope
+ business need + approver + evidence
```

A row containing only a person's name and "approved" fails to explain what that person can do or how to revoke it.

| Subject | What to review |
| --- | --- |
| Employees and contractors | Employment status, groups, domain, production scope, expiration |
| User groups | Members, sync source, owner, associated policies |
| Policies | Subject, verb, resource type, compartment, conditions, inherited rights |
| Domain admin roles | Assigned users or groups, need, and ability to alter authentication |
| Pipeline identities | Owner, authentication method, environment, deployment permissions |
| Dynamic groups | Matching rules, current matching resources, and potential future matches |
| Credentials | Type, owner, status, usage location, and replacement plan |
| Emergency accounts | Usability, custodians, sign-in path, and monitoring |
| Cross-tenancy access | Grantee, scope, purpose, and agreement validity |

For credentials, collect only necessary metadata such as ID, fingerprint, creation time, or owner. Review reports must never contain private keys, passwords, auth tokens, or live secrets.

### 3.2. Separating decision-makers and executors

| Role | Primary responsibilities |
| --- | --- |
| Workload owner | Confirm business need and impact of reducing permissions |
| HR or contractor manager | Confirm employment status and role changes |
| Security reviewer | Assess privilege level, segregation of duties, and exceptions |
| IAM admin or automation | Execute changes at the true grant source |
| Independent verifier | Re-read configuration and test revocation outcome |
| Emergency process owner | Maintain backup accounts, run drills, and close incidents |

For privileged access, avoid letting one person request, approve, execute, and declare completion alone. In small teams, some roles may overlap, but document the independent verifier and verification timestamp.

### 3.3. Risk-based cadence

An internal schedule example might be monthly reviews for strong administrative rights, quarterly reviews for standard permissions, and immediate reviews when staff leave the organization, change roles, or end contracts. This is an **illustrative schedule**, not a universal OCI mandate.

An urgent revocation event must not wait for the next cycle. Periodic reviews supplement missed-permission detection; offboarding or incident response must run on dedicated timelines.

When critical policies, matching rules, IdP mappings, or compartment scopes change, trigger targeted reviews for affected groups instead of waiting solely for fixed dates.

## 4. Collecting sufficient data to decide

### 4.1. Documenting snapshot scope and limitations

Each collection must record UTC timestamp, tenancy, domain, compartment, collector identity, data sources, and visibility limits. When an API returns an error or a reviewer lacks permission to inspect a scope, mark it **unverified**—never interpret it as "no permissions granted".

Cross-check the following sources:

- HR records, contractor owners, and on-call rosters.
- Users, groups, memberships, administrator roles, and IdP mappings.
- Policies at tenancy, ancestor compartments, and workload scopes.
- Matching rules along with resource lists tied to machine identities.
- Audit, sign-in activity, and change history.
- Access request tickets, exceptions, deployment history, and business justifications.

A point-in-time snapshot can go stale quickly. When executing revocations days later, re-read the grant path before editing and check for changes that occurred after the snapshot.

### 4.2. Example of reading policies with OCI CLI

The following commands are data-reading examples for learners in an authorized environment. They do not determine full effective permissions on their own.

```powershell
$ReviewProfile = '<OCI-CLI-profile-with-read-access>'
$IamRegion = '<appropriate-IAM-endpoint-region>'
$TenancyId = '<tenancy-OCID>'
$ParentCompartmentId = '<parent-compartment-OCID>'
$WorkloadCompartmentId = '<ProductionApps-OCID>'

$PolicyScopeIds = @(
  $TenancyId
  $ParentCompartmentId
  $WorkloadCompartmentId
) | Select-Object -Unique

foreach ($PolicyScopeId in $PolicyScopeIds) {
  Write-Output "Policy scope: $PolicyScopeId"
  oci iam policy list `
    --compartment-id $PolicyScopeId `
    --all `
    --profile $ReviewProfile `
    --region $IamRegion

  if ($LASTEXITCODE -ne 0) {
    throw "Failed to read policy scope: $PolicyScopeId"
  }
}
```

Add all ancestor compartments if the hierarchy has multiple levels. `--all` retrieves pages of that call; it does not automatically traverse every compartment. `policy list` returns policies defined in the specified compartment, and statements must be read to analyze granted subjects. [Oracle CLI: policy list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/iam/policy/list.html).

### 4.3. Reading the right identity domain

Example listing users using the endpoint of the domain under review:

```powershell
$ReviewProfile = '<OCI-CLI-profile-with-read-access>'
$IdentityDomainEndpoint = '<identity-domain-endpoint-URL>'

oci identity-domains users list `
  --endpoint $IdentityDomainEndpoint `
  --all `
  --profile $ReviewProfile

if ($LASTEXITCODE -ne 0) {
  throw 'Failed to read user list in domain.'
}
```

The command requires the identity domain endpoint; one domain does not represent every identity in the tenancy. User results also do not replace group, membership, role, and application lists. [Oracle CLI: identity-domains users list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/identity-domains/users/list.html).

If permissions are synced from an IdP or identity governance system, record which source is authoritative. Removing membership in OCI while leaving rights intact at the sync source can cause permissions to return on the next sync.

### 4.4. Do not conclude from last login alone

Seeing no Console sign-ins does not prove an identity is inactive: pipelines or users may call APIs using other credentials. Conversely, recent activity does not prove broad permissions are still required.

Use logs to add context to business needs. For standby permissions, infrequent use may be by design; inspect the owner, purpose, and usability instead of auto-deleting based on a "no login" criterion.

## 5. Deciding, executing, and verifying

### 5.1. Questions for reviewers

For each permission relationship, reviewers should answer:

1. Are the identity and responsible owner still valid?
2. Which specific task requires this permission, and in which environment?
3. Can the verb/operations and scope be narrowed?
4. Are there alternative broad grant paths or permissions to alter grant mechanisms?
5. Does the true grant source live in OCI, the IdP, or another system?
6. If permissions are reduced, which operational flows require testing?
7. When should temporary permissions be re-reviewed or automatically terminated?

Especially scrutinize permissions to manage memberships, credentials, policies, and authentication configs. These privileges can alter other people's access, making their impact broader than business role names suggest.

### 5.2. Classifying outcomes

| Outcome | Recording criteria | Next step |
| --- | --- | --- |
| Keep | Valid need, appropriate scope, clear owner | Document rationale and next review date |
| Reduce | Access needed, but level or scope is too broad | Design replacement grant, verify, then remove broad path |
| Revoke | Need no longer exists or identity is invalid | Execute at source, re-read, and probe access |
| Time-bound exception | Temporary need with accepted risk | Record approver, compensating controls, and end date |
| Undecided | Missing owner or evidence | Assign handler, deadline, and interim controls |

Do not automatically convert overdue items to "keep". An item with a revoke decision remains open work until the change is implemented and verified.

### 5.3. Completion path of a review item

```mermaid
flowchart LR
    A[Collect permission relationship] --> B[Reviewer confirms need]
    B --> C[Decision and rationale]
    C --> D[Modify at grant source]
    D --> E[Re-read configuration]
    E --> F[Verify permissions and workload]
    F --> G[Close review item with evidence]
```

For An in the opening scenario, the outcome might be removing production operations group membership at the IdP source, retaining read permissions for the new support role, checking mappings, and confirming no inherited admin paths remain. There is no need to delete the entire account if An remains employed with valid duties.

Conversely, when staff leave the organization, handling scope may cover identities, credentials, and active sessions across relevant systems. Changing a Console password does not prove API keys, auth tokens, or dedicated database accounts were disabled.

After changes, account for propagation time and test using the exact access type being revoked. Do not assume all sessions, tokens, or caches invalidate instantaneously. When credential compromise is suspected, follow incident response procedures to check and handle each credential type rather than merely removing one membership.

## 6. Machine identities and indirect administrative privileges

A dynamic group determines members via matching rules; new resources meeting conditions can become privileged principals. Therefore, reviews must evaluate both **what currently matches** and **which resources could match in the future**. [Oracle: Managing Dynamic Groups](https://docs.oracle.com/iaas/Content/Identity/dynamicgroups/managingdynamicgroups.htm).

Illustrative rule example:

```text
ALL {instance.compartment.id = '<pipeline-compartment-OCID>'}
```

This rule must be evaluated alongside permissions to create and manage instances in that compartment. If membership scope is too broad for the pipeline's purpose, the workload owner must propose tighter conditions and verify impact on legitimate jobs.

| Machine entity | Additional questions |
| --- | --- |
| Deployment pipeline | Are identities separated per environment? Who manages config and credentials? |
| Instance principal | Which workload uses the rights? Who can create or control matching instances? |
| Resource principal | Do resource type, compartment, and conditions fit the purpose? |
| Integration credentials | Which systems use them? Can they be rotated and revoked without outage? |
| Applications in domain | To whom are admin or application roles assigned? |

After changing a matching rule, do not test too early and conclude the change failed. Oracle notes roughly one hour for matching rule updates to take effect; revocation plans must account for this behavior. [Oracle: Updating Dynamic Groups](https://docs.oracle.com/en-us/iaas/Content/Identity/dynamicgroups/Updating_Dynamic_Groups.htm).

High-scrutiny cases include identities able to update their own workload's policies, users able to control resources that receive strong privileges, and integration accounts shared across multiple applications. The review goal is determining true scope and appropriate privilege reduction while keeping valid flows running.

## 7. Two forms of emergency access

### 7.1. Temporary privileges while authorization systems work

Suppose an on-call engineer needs to replace a failed instance while the IdP and IAM workflows still function. Scoped permissions can be granted to an individual identity or a pre-staged on-call group, tied to an incident and an expiration time. Privilege levels must match the recovery task rather than defaulting to tenancy-wide admin.

Records must specify who or what mechanism revokes access upon expiration. A timestamp in a ticket or a group named `Temporary` does not automatically expire memberships or OCI policies. If the organization uses automation or time conditions, verify they truly restrict access and assign someone to handle revocation failures.

### 7.2. Local recovery accounts when primary login fails

When an external IdP is unavailable, adding memberships through that IdP may be impossible. A pre-configured local sign-in path independent of the same failure point is required. Oracle recommends maintaining local admin access capability for federation outages while controlling credential access and monitoring activity. [Oracle: IAM Federation](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/iam_security_topic-IAM_Federation.htm).

In the tenancy-admin emergency access account model, Oracle describes a local user in the Default identity domain belonging to the `Administrators` group, protected by MFA, with monitored usage. Authentication factors must be available during an incident; FIDO security keys held under controlled custody are one option mentioned in the documentation. [Oracle: Managing Emergency Access Accounts in OCI](https://www.oracle.com/a/ocom/docs/security/oci-iam-emergency-access-accounts-v1.8.pdf).

This account may retain standing admin rights for recovery when needed. What is time-bound operationally is **access to and use of the account for a specific incident**, plus any extra grants issued during response. Do not assume the account's admin rights vanish when a ticket closes.

| Attribute | Temporary grant for on-call | Local recovery account |
| --- | --- | --- |
| Scenario | Normal authorization path still works | Primary login or admin path is disrupted |
| Identity | Explicitly recorded individual | Dedicated account, with user logged per incident |
| Scope | Restricted to task and workload | May be tenancy admin to restore access paths |
| Pre-staging | Group, policy, approval, revocation mechanism | Account, MFA, custody, tested sign-in path |
| Closure | Revoke incident-specific grant | End sessions, handle credentials, restore custody state |

The local path still depends on the OCI IAM service and underlying infrastructure. It does not guarantee access if OCI's authentication service itself is disrupted, nor does it bypass Security Zones or service-level constraints.

## 8. Preparing recovery capability before incidents

### 8.1. Mapping dependencies

Operations teams should assess dependencies of the emergency path:

```text
Authorized on-call engineer
→ Obtains runbook and tenancy/domain details
→ Accesses credentials via custody mechanism
→ Uses MFA factor
→ Reaches local sign-in path
→ Executes recovery operations
→ Monitors receive alerts and evidence
```

For each arrow, ask: if the corporate IdP or the primary administrator's account is down, can this step still proceed? If SSO login is required to read the runbook, open the secrets vault, or receive MFA codes, the backup path may lock out right alongside the primary system.

You do not need to eliminate every dependency at any cost. Identify shared points of failure, pick suitable alternatives, and prove them in a drill.

### 8.2. Custody and accountability

Recommended organizational design:

- Assign an account owner, authentication material custodians, and backups for absences.
- Log credential checkouts with incident ID, recipient, and return-to-custody timestamp.
- For high privileges, apply two-person verification as operational capacity allows.
- Also control account recovery methods, associated emails, and MFA changes.
- Never use emergency accounts for daily work or pipeline tasks.
- Never create standing API keys on this account merely for convenient scripted logins.

The points above are recommended process design and must be tailored to the organization. If multiple people can use the same dedicated account, a single principal log does not identify the operator; link it with handover logs, timestamps, and incident IDs. Never use that account as a shared identity for routine operations.

### 8.3. Verifying sign-in configuration

Before relying on an emergency path, verify the account is active, its password works, MFA is enrolled, and sign-on policies allow the intended login method. Evaluate network conditions, rule ordering, and constraints that might inadvertently block on-call staff.

When editing configurations that risk admin lockout, keep an active admin session open and test in an independent browser session before closing the old one. An already-signed-in session does not prove the new sign-in path still works.

Console MFA also does not replace API credential controls. OCI Console MFA policies scope Console access; reviews must examine the actual authentication type used on each access path. [Oracle: IAM MFA](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/iam_security_topic-IAM_MFA.htm).

### 8.4. Preparing alerts and monitoring

Every use of an emergency account must be visible to monitors, including logins during drills. Operations should verify detections for:

- Successful logins or unusual bursts of failures.
- Password, recovery method, or MFA changes.
- Membership, role, or policy changes involving the account.
- New credentials created within an incident window.
- Account usage outside logged incident windows.

Choose alert integrations compatible with supported event sources in the tenancy and test notifications end to end. Routing via notification services to monitoring systems or on-call staff is possible, but a configured email alone does not prove the right handler received it. Measure latency and maintain an alternate channel suited to the IdP outage scenario.

## 9. Activation, usage, and closure runbook

### 9.1. Activation conditions

Valid triggers under internal procedures may include loss of login due to an IdP outage, permission misconfigurations blocking recovery actions, or unavailability of required admins during a severe incident.

Do not use emergency mechanisms for routine inconvenience, bypassing reviews, or unverified requests. While a scoped authorization path still works, prioritize that path per organizational design.

### 9.2. Operational steps

| Step | Action required | Minimum evidence |
| --- | --- | --- |
| 1. Open incident | Describe impact, recovery goal, and broken access path | Incident ID, time, scope |
| 2. Choose access path | Scoped temporary grant or local recovery account | Selection rationale and planned actions |
| 3. Record authorization | Identify operator, observer, window, and stop conditions | Owner, deadline, communication channel |
| 4. Activate | Grant temporary rights or check out prepared account | Timestamp and executing identity |
| 5. Initial check | Confirm right tenancy, domain, compartment, and principal | Check results, pre-change state |
| 6. Recover | Execute required actions, logging changes chronologically | Request IDs, affected resources, outcomes |
| 7. Hand back | Verify normal access paths and workload health | Verifier and verification tests |
| 8. End access | Revoke temporary rights, handle sessions and credentials | Post-change config, test results |
| 9. Close and review | Complete evidence, independent review, and follow-ups | Closure record, owners of open items |

If the primary approver is unavailable, the runbook must name alternates or pre-agreed delegation mechanisms. Never leave a technical fallback existing with no one authorized to approve its use within the required timeframe.

### 9.3. Discipline during the emergency window

The operator addresses only the defined objective, logs related changes, and pauses when out-of-scope requests arise for lead evaluation. If the window expires before recovery finishes, log the extension decision, new owner, or alternative plan.

Never record secrets in tickets, screenshots, or shared command histories. Evidence should include timestamps, operation types, resource IDs, and results sufficient for investigation.

An emergency change may create new resources, backups, logs, or permissions for a support group. Document them so closure steps know what to revoke or clean up and avoid lingering costs.

### 9.4. Closing incidents according to access type

**For temporary grants:** remove incident-specific memberships, roles, or statements at the true source; check no unexpected alternate paths remain; complete session, token, or credential cleanup required by design.

**For recovery accounts:** terminate relevant sessions using supported mechanisms, handle used or created credentials, update custody records, and verify the backup path remains usable. Changing a password does not prove all other sessions or credentials were revoked.

Do not delete or disable the sole recovery account merely because the incident closed. Preserve fallback admin capability while removing temporary grants to other identities and any out-of-design modifications.

## 10. Audit evidence and operational metrics

### 10.1. Linking decisions to actions

A sufficient evidence package should connect:

```text
Review cycle or incident
→ Identity and grant path
→ Decision and responsible owner
→ Actual change
→ Post-change state
→ Verification test and confirmer
```

In OCI Audit, search by the exact compartment, time window, and operation; watch time zone conversions when reconciling with internal logs. Oracle notes logs typically appear within roughly 15 minutes of an API call, though processing time can vary. [Oracle: Viewing Audit Log Events](https://docs.oracle.com/en-us/iaas/Content/Audit/Tasks/viewinglogevents.htm).

Zero logs in one search does not prove an action never happened. First check scope, read permissions, event source, latency, and UTC timestamps.

For identity domain log integrations, do not build new pipelines assuming the legacy `AuditEvents` endpoint still receives new data. Oracle announced that this endpoint and certain Reports API templates stopped returning new data after December 15, 2024, directing users to OCI Audit. Verify which data source your organization's integrations currently use. [Oracle: Using the Audit Event APIs](https://docs.oracle.com/en-us/iaas/Content/Identity/api-getstarted/usingauditeventapis.htm).

### 10.2. Meaningful metrics

| Metric | Interpretation |
| --- | --- |
| Scope collection coverage | Share of target subjects with actual data out of planned scope |
| Verified review rate | Share of items decided, executed, and fully verified |
| Unexecuted revocations | Items still open despite reviewer choosing revoke |
| Time to complete revocation | From decision to verifying access no longer works |
| Overdue exceptions | Accepted grants past expiration still unresolved |
| Unexplained emergency account uses | Activity not linked to a valid incident |
| Time to regain access | From activation to executing the planned recovery action |
| Drill results | Accessible, alerts delivered, and closed in proper state |

For example, a cycle has 100 items, reviewers decided all 100, yet 8 revocations remain unapplied. Do not report 100% control completion; separate decision rate from verified execution rate.

## 11. Hands-on lab: reviewing and revoking in a lab compartment

### 11.1. Preparation

Use a lab compartment, a dedicated test identity, and a prepared lab Compute instance. Never use a live tenancy-admin emergency account for this membership test.

Prerequisites:

- Lab administrator has permission to create groups and grant access within assigned scope.
- Test identity is not in admin groups and has no other path to read the instance.
- An authenticated CLI profile exists for the test identity; if using a local user, configure auth per organizational policy.
- You know the instance OCID, compartment, identity domain, and region of the lab.
- Someone records state before and after changes.

The lab does not require creating extra Compute resources if a suitable test resource already exists. The goal is testing permissions with read operations—avoid deleting or changing instance state as a negative test.

### 11.2. Creating a review item

Example entry recorded directly in the lab sheet:

```text
Review ID: AR-LAB-001
Identity: user-lab-review
Domain: LabDomain
Grant source: direct membership in group LabComputeReaders
Resource: a test Compute instance in the lab compartment
Need: read instance details for post-deployment verification
Post-test decision: revoke due to end of assignment
Executor: lab admin
Verifier: assigned reviewer
```

This is an illustrative record containing no credentials. If practicing in a domain synced from outside, determine beforehand where to edit memberships to avoid sync re-provisioning.

### 11.3. Three verification checkpoints

In the Console, the administrator creates group `LabComputeReaders` in the right domain and a policy to read instances in the lab compartment. Replace example names with real values:

```text
Allow group LabDomain/LabComputeReaders to read instances in compartment AccessReviewLab
```

Run the check using the **test identity's profile**:

```powershell
$LabProfile = '<profile-of-user-lab-review>'
$LabRegion = '<lab-instance-region>'
$LabInstanceId = '<lab-instance-OCID>'

oci compute instance get `
  --instance-id $LabInstanceId `
  --profile $LabProfile `
  --region $LabRegion

$AccessProbeExitCode = $LASTEXITCODE
Write-Output "Exit code: $AccessProbeExitCode"
```

| Checkpoint | Admin action | Expected result when running command as test identity |
| --- | --- | --- |
| A. Without membership | Test user not yet added to group | Cannot read instance due to missing permissions |
| B. During assignment | Add test user to policy-granted group | Can read instance once permissions take effect |
| C. End of assignment | Remove user from group per review decision | Can no longer read once change takes effect |

Confirm principal, target, and auth path at all three checkpoints. A non-zero exit code is meaningful only after ruling out wrong region, wrong OCID, network errors, or invalid credentials. Compare error messages and configurations to distinguish auth errors from authorization errors.

If checkpoint C still succeeds in reading, check permissions from other groups, inherited policies, sync sources, propagation time, and active sessions. Never grant extra rights or switch to an admin profile just to make a test "pass".

### 11.4. Lab completion criteria

A review item passes when pre-change state, revocation decision, executor, post-change membership, and a test proving loss of access are all documented. Also verify the lab policy does not grant permissions outside the intended compartment.

Afterward, clean up groups, policies, and credentials created solely for the lab within the lab scope; do not delete shared resources to practice revocation. If cleanup remains open, record the owner and deadline.

## 12. Controlled IdP outage drill scenario

Drilling the emergency path is separate from the membership lab. Do not intentionally break the production IdP; simulate by having participants use the prepared local sign-in path during a monitored window.

Suggested scenario:

1. Open a drill incident and agree on a harmless read operation to prove admin capability.
2. Assigned personnel retrieve the runbook, tenancy/domain details, and auth materials via the fallback mechanism.
3. Sign in using an independent browser session, complete MFA, and confirm the exact principal.
4. Verify monitors receive alerts and link them to the incident.
5. Perform the planned operation, logging timestamps and evidence.
6. End the session, process credentials per runbook, and return materials to custody.
7. Verifier checks no temporary grants or new credentials were left behind.
8. Record execution duration, friction points, and improvement owners.

Pass criteria must cover **accessible**, **observable**, and **closed in the right state**. Merely checking that a password exists in a vault does not prove recovery capability.

After changing MFA, passwords, sign-on policies, custodians, or storage mechanisms, re-drill the affected portion. Choose a drill cadence aligned with risk and actual changes.

## 13. When automating with Access Governance

Oracle Access Governance supports one-time, periodic, and event-driven review campaigns across users, policies, or permission sets. It is an optional capability for organizing large-scale reviews; configure integrations and scope before treating data as complete. [Oracle: Access Governance](https://docs.oracle.com/en-us/iaas/Content/cloud-adoption-framework/security-access-gov.htm).

Reviewers can make decisions on identity access, group memberships, or policies depending on configured task types and workflows. Documentation describes remediation requests sent to target systems upon revocation. In operations, track outcomes on the target system to know whether changes succeeded or errored. [Oracle: Perform Access Reviews](https://docs.oracle.com/en-us/iaas/Content/access-governance/perform-access-reviews.htm).

Before scaling automation, organizations should verify a complete end-to-end cycle:

```text
Collect data from source
→ Reviewer sees accurate identity and permissions
→ Revocation decision
→ Target system receives change
→ Access truly ceases working
→ Evidence links back to review item
```

Do not let automated recommendations replace human confirmation of need for infrequently used emergency permissions. Also estimate service, integration, and evidence storage costs under current configurations; automating more tasks does not prove operating costs decrease.

## 14. Record templates and criteria for OCI workloads

### 14.1. Minimum template for a permission relationship

| Field | Information to record |
| --- | --- |
| Review or incident ID | Link to review cycle or incident |
| Subject | Principal type, ID, domain, and owner |
| Grant source | Group, role, policy, mapping, or matching rule |
| Scope | Tenancy, compartment, and resource types |
| Business purpose | Specific task requiring access |
| Decision | Keep, reduce, revoke, or exception |
| Decision owner | Decision-maker and rationale |
| Effective window | Expiration if any, closure mechanism, failure handler |
| Implementation | Actual change, executor, timestamp, and reference |
| Verification | Re-read configuration and verification test |
| Final state | Completed or remaining open work |

### 14.2. System-level completion criteria

For the Java application in this lesson, a complete control cycle must demonstrate:

- Lists of privileged humans and machines are reconciled against the right domains, grant sources, and compartments.
- Permissions of the engineer who changed teams are handled at the source, with no unnecessary production admin paths remaining.
- The pipeline retains valid deployment flows after privilege reduction and has a clear owner.
- OCI permissions for networking, storage, and databases are distinguished from OS, database, and in-application permissions.
- The local emergency path works in an IdP-outage scenario with active monitoring and accountability logs.
- Incident-related temporary grants, sessions, and credentials are handled by type; tenancy recovery capability remains intact.
- Review, remediation, and drill outcomes include evidence and owners for open improvements.

Access reviews keep access aligned with current duties. Emergency procedures preserve recovery capability when normal paths fail. Both practices meet in the evidence: who had access, why they needed it, how it was used, and whether the final state matches the design.
