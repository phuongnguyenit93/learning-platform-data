# Cloud Identity and Enterprise Identity Management on Google Cloud

> **Chapter:** Organization Governance  
> **Lesson:** Cloud Identity and Enterprise Identity Management  
> **Module:** CLOUD_PROVIDERS_GCP

In the **CLOUD_PROVIDERS_GCP** module, learners explore Google Cloud from project organization, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage, and databases; through deployment scenarios, learners learn to select services, protect resources, automate releases, and monitor reliability and cost. To accomplish this at enterprise scale, an organization must manage **user and group identities** before addressing resource administration permissions.

**Cloud Identity** supports centralized management of enterprise identities under a corporate domain, groups, sign-in mechanisms, and certain device/security policies depending on edition and licensing. Together with **Google Cloud Identity and Access Management (IAM)**, Cloud Identity answers two distinct questions:

- **Who are you?** What is the authenticated identity, which organization or group does it belong to, and is the account active?
- **What are you allowed to do on which resources?** IAM roles, resource scopes, conditions, and related policies determine permissions.

This article focuses on the relationship between Cloud Identity, Google Workspace, Google Cloud Organization, IAM, and the identity lifecycle. Examples use hypothetical domains and projects and do not require creating users or changing production configurations to complete the lesson.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between **Cloud Identity**, **Google Workspace**, **Cloud IAM**, **Organization resource**, **Folder**, **Project**, and **Google Groups**.
2. Describe how a verified domain and enterprise accounts help establish the Google Cloud governance boundary.
3. Design a **joiner–mover–leaver** lifecycle: creating accounts, assigning groups, changing roles, revoking access, and handling departing accounts.
4. Separate identity administration permissions in the **Google Admin console** from resource management permissions in the **Google Cloud console**.
5. Apply MFA/2-Step Verification, SSO, session controls, privileged account protection, and access monitoring.
6. Distinguish human identities, **service accounts**, **Workload Identity Federation**, and **Workforce Identity Federation**.
7. Build a group–role–scope matrix across development, operations, and production projects.
8. Spot common mistakes: using personal accounts outside the organization, granting direct permissions broadly, overlooking inherited permissions, or mistaking a group for a role.

## 2. What Is Cloud Identity?

Cloud Identity is Google's enterprise identity and security management service. An organization can use **domain-managed accounts** to provide sign-in identities, organize users/groups, and enforce appropriate management policies.

Cloud Identity comes in **Free** and **Premium** editions, with differing feature scopes, device management, reporting, and entitlements. Whether a feature is available depends on the license type, configuration, and current policies. Enterprises already using **Google Workspace** already have a corresponding identity/admin system; there is no need to create a separate identity system solely to use Google Cloud.

### 2.1. Distinguishing the Components

| Component | Primary Responsibility | Example | Do Not Confuse With |
|---|---|---|---|
| **Cloud Identity** | Manages enterprise accounts, groups, sign-in, and identity policies | `engineer@example.com`, group `gcp-ops@example.com` | A role allowing edits to Compute Engine VMs |
| **Google Workspace** | Collaboration suite and enterprise user administration | Gmail, Drive, Calendar, and account administration | Automatically having Owner on every project |
| **Google Admin console** | Admin interface for identities, users, groups, security, and devices per privileges | `admin.google.com` | Google Cloud console for managing VMs/GKE |
| **Google Cloud IAM** | Allows or restricts principals from performing permissions on resources | `roles/run.developer` at project scope | Password/SSO authentication mechanisms |
| **Google Cloud Organization** | Root node of the cloud resource hierarchy for an organization | `organizations/123456789012` | An Organizational Unit in Cloud Identity |
| **Folder / Project** | Groups and isolates cloud resources, serving as scopes for IAM/policies | `folders/…` and `projects/…` | Google Groups |
| **Google Group / Cloud Identity Group** | Collection of users/groups for membership management and group-based IAM grants | `gcp-platform@example.com` | A role; a group carries no permissions until granted IAM |
| **Service account** | Identity for workloads running on Google Cloud | `orders-api@project.iam.gserviceaccount.com` | Employee account logging into Console |

**A managed account does not automatically have permissions on any Google Cloud resource.** The ability to sign in and permission to call APIs are two separate steps; final access depends on IAM policies, inheritance, and other controls.

### 2.2. Enterprise Users vs. Personal Users

- **Managed Google Account:** the organization can manage lifecycle and policies through its identity system; typically uses an email address under a verified domain.
- **Personal Google Account:** an account managed by an individual; it can be invited to a project within policy limits, but the enterprise does not control the full sign-in lifecycle of that account.
- **Unmanaged account using a corporate domain:** may have been created by an individual before the enterprise verified the domain. Resolving account conflicts requires a supported migration workflow, communication with the user, and admin coordination; do not assume all accounts automatically convert to managed accounts upon domain verification.

For operations and auditing, prefer organization-managed identities for staff and assign permissions via groups; external accounts must be approved and have review dates.

## 3. From Corporate Domain to Google Cloud Organization

### 3.1. Why Verify the Domain?

Cloud Identity/Google Workspace uses **domain verification** to confirm the organization controls the declared domain, such as `example.com`. Administrators typically prove DNS management control using a Google-provided verification record. This step proves domain ownership; it **does not automatically create VMs, VPCs, buckets, or IAM permissions for employees**.

High-level sequence:

1. The responsible unit confirms the primary domain and DNS administration owner.
2. Create/configure an approved Cloud Identity or Google Workspace tenant.
3. Complete domain verification following official documentation.
4. Configure administrative identities, sign-in methods, security policies, and groups.
5. Check the associated **Google Cloud Organization resource** in Google Cloud and delegate organization-level administrative roles.
6. Structure folders/projects and governance policies within the organization.

The existence and visibility of the Organization resource depend on the identity/organization setup state and IAM. If the organization is not visible in the Console, check setup prerequisites, the signed-in account, and viewer permissions; **do not hastily create another tenant** as a workaround.

### 3.2. Two Distinct Hierarchies

~~~mermaid
flowchart LR
    subgraph I["Identity: Admin console"]
      D["Verified domain"] --> OU["Organizational Units<br/>configure user policies"]
      D --> U["Managed Users"]
      D --> G["Groups and Group Membership"]
    end
    subgraph C["Resources: Google Cloud"]
      O["Organization resource"] --> F["Folder: Engineering"]
      F --> PD["Project: development"]
      F --> PP["Project: production"]
      PP --> S["Cloud Run / GKE / Cloud SQL"]
    end
    G -. "Assign group as IAM principal" .-> PD
    G -. "Assign role with appropriate scope" .-> PP
~~~

An **Organizational Unit (OU)** in the identity system applies policies to sets of users/devices per product capabilities. A **Folder** in Google Cloud Resource Manager organizes resources and applies IAM and Organization Policies across the cloud hierarchy. Both share the word "organization," yet they **are not a single automatically synchronized tree**.

For example, an employee in the `Engineering` OU in the Admin console does not automatically gain permission to modify projects in the `Engineering` folder of Google Cloud. To grant cloud access, an administrator must configure proper IAM bindings or supported delegation policies.

### 3.3. Organizations and "No Organization" Projects

Projects can exist outside an Organization resource depending on their origin and account model. When bringing a project into an organization, check **resource owners, billing, IAM, Organization Policies, networking, service accounts, and project move permissions**. Do not treat moving a project like simply renaming a directory: inherited policies at the destination can change operational behavior.

## 4. Who Administers Identity, and Who Administers Resources?

Google Admin console and Google Cloud console serve two administrative domains. Staff working across both systems may hold multiple roles, but responsibilities should be clearly separated by function.

| Admin Group | Scope | Typical Tasks | Risk if Abused |
|---|---|---|---|
| **Cloud Identity / Workspace Super Admin** | Identity tenant, highest administrative privilege per product capabilities | Account recovery, admin role management, security config, identity policies | Compromised account can impact identities broadly |
| **Delegated user/group admin** | Delegated subset of users/groups | Onboarding, group updates, lifecycle support | Adding wrong members to groups with high IAM privileges |
| **Google Cloud Organization Admin** | Google Cloud organization and resource structure | Administer organization/folders and delegate cloud roles by tier | Altering org-wide resources/policies |
| **Security administrator** | Identities, cloud policies, and monitoring per mandate | MFA, posture management, auditing, privileged access control | Control conflict if approving and self-granting permissions |
| **Project admin / workload owner** | Assigned project or resources | Manage Compute Engine/GKE/Cloud Run and data services | Overly broad permissions can affect production |
| **Auditor / FinOps** | Logs, configuration, and cost data within authorized scope | Audit IAM, changes, costs, and exceptions | Viewing sensitive data beyond need |

Someone designated as a Cloud Identity/Workspace **Super Admin** may hold initial capabilities to bootstrap Google Cloud administration depending on organization setup; however, **never infer actual permissions solely from a title**. Always read the IAM policy and verify capabilities on the exact Organization/Project. Conversely, `roles/resourcemanager.organizationAdmin` is a Google Cloud IAM role and **does not replace Super Admin privileges** in the Admin console.

### 4.1. Separation of Duties

A sound workflow should separate at least three roles:

1. **Service owner requests** permissions matching job duties.
2. **Identity administrator** confirms the user is active and adds them to the right group.
3. **Resource owner or security reviewer** approves the IAM binding/group-to-role assignment and verifies effective permissions.

Smaller organizations can combine some roles while still preserving approval trails, least privilege, and periodic independent reviews of privileged groups.

## 5. Managing Google Groups and Group-Based IAM

### 5.1. Why Prefer Groups?

Granting permissions directly to individuals creates many bindings that are hard to audit. Granting permissions to a **Google Group** keeps IAM policies stable as staff change; the identity team updates membership via standard processes.

Hypothetical example:

| Group | Members | Planned IAM Role | Scope |
|---|---|---|---|
| `gcp-dev-readers@example.com` | Devs needing visibility into dev | `roles/viewer` (evaluate exact permission level) | Development project |
| `gcp-ops-logs@example.com` | SREs, operations support | `roles/logging.viewer` | Production project |
| `gcp-run-deployers@example.com` | Authorized CI/CD operators | Appropriate Cloud Run deploy role | Target project/resource |
| `gcp-billing-auditors@example.com` | Finance/FinOps | Appropriate billing viewer/cost role | Assigned billing account |
| `gcp-security-review@example.com` | Internal audit | Appropriate read-only role | Organization/folder/project per mandate |

Group names above are **illustrative only**. A single group can hold multiple roles across multiple resources, and one person can belong to multiple groups. IAM aggregates permissions from all relevant grants rather than treating a group as an exclusive permission container.

### 5.2. Group Governance Workflow

1. **Naming:** use names reflecting product, environment, and access tier; record an accountable owner.
2. **Membership rules:** define who can join, who approves, duration, and departure criteria.
3. **Membership management:** prefer changing membership through IT/IAM workflows; never share user accounts.
4. **Role assignment:** cloud owners assign the group as an IAM principal at the lowest scope meeting the requirement.
5. **Verification:** verify members, roles, inherited permissions, and actual access.
6. **Review:** audit stale groups, members who changed roles, nested groups, and unintended privilege paths.

**Watch out:** a group whose owner can add members becomes part of the IAM control plane. If that group holds sensitive roles in production, **permission to manage group membership is indirectly a production-impacting privilege** and must be protected.

### 5.3. Illustrative Allow Policy

~~~yaml
# Illustrative binding snippet; do not use as a full policy to overwrite existing policies.
bindings:
  - role: roles/logging.viewer
    members:
      - group:gcp-ops-logs@example.com
version: 1
~~~

When a group is used as a principal, account `sre-a@example.com` must be an active member and not blocked by other policies in order to exercise the role's permissions. **Group membership does not automatically grant a role** if no IAM binding exists.

When temporary access is needed, consider **IAM Conditions** (such as time-based conditions) or **Privileged Access Manager** where supported by the organization; selecting a solution depends on approval, logging, and review requirements.

## 6. Identity Lifecycle: Joiner – Mover – Leaver

Identities must change when employment status or job duties change. A good lifecycle workflow can be partially automated from HR/directory systems, but source data must always be verified.

### 6.1. Joiner: New Employee Onboarding

**Scenario:** Minh joins the backend team and only needs to view logs in the development project.

- HR/IT confirms employment contract, corporate account, and manager email.
- Admin creates or syncs managed user `minh@example.com` in Cloud Identity/Workspace.
- Enforce sign-in policies, MFA/2SV, device posture, and account recovery per risk tier.
- Add Minh to `gcp-dev-readers@example.com` or the appropriate log-viewer group.
- The cloud owner verifies the group's IAM binding on the development project; do not grant Owner when the user only needs to read logs.
- The user tests access to the target project; record the approver and approval timestamp.

### 6.2. Mover: Team Transfer or Role Change

**Scenario:** Minh transfers from development to the SRE team supporting production.

- Remove from the development group if those permissions are no longer needed.
- Add to `gcp-ops-logs@example.com` with approved production log-viewing access.
- If deployment is needed, grant specific permissions with appropriate time-bound conditions rather than elevating everything by default.
- Audit **direct IAM bindings**, nested groups, and permissions inherited from folders/organization; do not inspect only the new group.
- Verify both expected new access and removed old access; retain audit records.

### 6.3. Leaver: Departure or Contract End

When an employee leaves the organization, an illustrative workflow:

1. HR triggers the offboarding signal and effective access-termination time.
2. IT/Identity suspends or deactivates the account per policy and revokes sessions/access as supported by the system.
3. Remove group memberships, revoke direct IAM roles, and remove access in connected systems.
4. Check tokens, personal keys/credentials, service account impersonation rights, third-party apps, and CI/CD credentials the person previously managed.
5. Hand over employee-owned resources, retained data, and administrative responsibilities; never delete corporate data in violation of retention policies.
6. Verify no sign-in/access remains and archive processing evidence.

**Removing group membership alone is insufficient** if the user still has direct IAM grants, belongs to another group, or holds independent application credentials. Both direct and indirect access paths must be checked.

### 6.4. Lifecycle Tasks and Risk Matrix

| Stage | Identity Actions | Cloud IAM Actions | Verification Outcome |
|---|---|---|---|
| **Joiner** | Create/sync user, enforce MFA policy, add to group | Group already holds appropriate project role | Can access approved functions |
| **Mover** | Leave old group, join new group | Audit direct IAM, folder/org inheritance | Old permissions removed, new permissions accurate |
| **Leaver** | Suspend/deactivate, revoke sessions as supported | Revoke group/direct roles, audit credentials | No valid access paths remain |
| **Periodic** | Audit active users, group owners, admin accounts | Review privileged roles, group-to-role, exceptions | Permission inventory has owners and justifications |

## 7. Centralized Authentication, SSO, and MFA

### 7.1. Authentication and Authorization Are Two Separate Steps

~~~mermaid
sequenceDiagram
    participant E as Employee
    participant ID as Cloud Identity / SSO
    participant C as Google Cloud Console / API
    participant I as Google Cloud IAM
    participant R as Resource
    E->>ID: Sign in + MFA check
    ID-->>E: Authenticated identity/session
    E->>C: Request operation on project
    C->>I: Check principal, permission, resource
    I-->>C: Allow or deny per policy
    C->>R: Execute if allowed
    R-->>E: Result
~~~

SSO lets users sign in consistently; IAM decides **what the signed-in user can do** on Google Cloud. Signing in successfully does not imply permission to create a GKE cluster or view production Cloud SQL.

### 7.2. Single Sign-On (SSO)

An enterprise with an existing Identity Provider (**IdP**) such as AD/Entra/Okta can configure federated sign-in via mechanisms supported by Cloud Identity/Workspace (such as **SAML SSO**). In this model, the organization manages authentication policies at the IdP and maps identities to managed Google accounts; attention must be paid to unique identifiers, account locking, session lifetimes, and fallback sign-in paths.

When implementing:

- Identify the **authoritative identity source** (HRIS/directory/IdP) and where users are created/modified/deleted.
- Synchronize user/group data using supported methods; distinguish **provisioning** from **authentication**.
- Test ID fields, email aliases, name changes, department transfers, and duplicate accounts.
- Test sign-in when the IdP is healthy, when the IdP is unreachable, and during recovery scenarios.
- Establish a policy-compliant emergency access plan without relying on a single point of failure.

**SSO does not automatically assign IAM roles.** An IdP that authenticates successfully while Google groups/IAM are out of sync or misconfigured will still result in `PERMISSION_DENIED`.

### 7.3. MFA / Two-Step Verification (2SV)

MFA reduces the risk of attackers using compromised passwords to access systems. Enterprises should prefer phishing-resistant methods such as **security keys** or **passkeys** per availability and policy; govern enrollment, account recovery, and lost-device handling.

For privileged accounts:

- Enforce strong authentication policies, controlled account recovery, and admin endpoint protection.
- Minimize the number of **Super Admins** and holders of organization-scoped cloud roles.
- Maintain at least one approved and periodically tested **break-glass** procedure; emergency accounts must be strictly protected and logged.
- Monitor suspicious sign-ins, MFA changes, admin/group changes, and IAM policy updates.

Features such as **context-aware access**, advanced endpoint management, or device conditions may depend on licensing and application type; verify availability before writing mandatory requirements for all Cloud Identity Free accounts.

## 8. Human Identities vs. Workload Identities

A Google Cloud system may have Java APIs on Cloud Run, pods on GKE, Compute Engine VMs, data sync jobs, and release pipelines. Employee accounts should never be used by all those workloads to call APIs.

| Identity Type | Used For | Preferred Management Approach |
|---|---|---|
| **Managed user** | Employees accessing Google Cloud Console, Cloud Shell, and tools | Cloud Identity/Workspace, SSO/MFA, HR lifecycle |
| **Group** | Collection of managed users or eligible principals for IAM grants | Owner, membership rules, periodic reviews |
| **Service account** | Workloads on Cloud Run, GKE, Compute Engine, and automation | Dedicated service account per app/environment; least-privilege IAM |
| **Workload Identity Federation** | External workloads outside Google Cloud (e.g., external CI or another cloud) needing Google Cloud access | Short-lived federated tokens from supported IdPs; avoid long-lived keys |
| **Workforce Identity Federation** | Employees/partners from a non-Google IdP accessing Google Cloud resources via federation policies | Configure pools/providers, IAM mappings, and appropriate org policies |

The two federation technologies have similar names but **different subjects**: *workload* is for machines/jobs; *workforce* is for human users. **Cloud Identity SSO** with managed Google Accounts is yet another pattern for employee sign-in; do not collapse all of them into a single diagram.

### 8.1. Workload Example on Cloud Run

Suppose the orders API needs to read objects in Cloud Storage and publish Pub/Sub events:

~~~text
Software developer:
  developer@example.com
  → signs in to Google Cloud with a managed account
  → granted deployment IAM role per allowed group/scope

Cloud Run runtime:
  orders-api@project-id.iam.gserviceaccount.com
  → workload identity
  → only has permission to read a specific bucket and publish to a specific topic
~~~

An employee may have permission to **deploy new revisions** without having permission to **read customer data**. Conversely, the API's service account holds runtime permissions but **should not be granted Editor/Owner** across the entire project.

On GKE, evaluate **Workload Identity Federation for GKE** so workloads use appropriate identities instead of distributing service account keys. On Compute Engine, use VM-attached service accounts with proper scopes/access controls; on Cloud Run, use the service's dedicated service identity. When external pipelines outside Google Cloud need access, prefer Workload Identity Federation over long-lived JSON keys whenever requirements allow.

## 9. Real-World Scenario: Identity Governance for a Retail Company

**Context:** `RetailOne` manages the domain `retailone.example` and deploys an ordering system on Google Cloud across three environments:

- **Development:** dev team tests Java APIs, Cloud Run, and Cloud SQL without real customer data.
- **Staging:** QA team validates releases and runs integration tests.
- **Production:** Cloud Run Orders API, Cloud SQL with customer data, Pub/Sub, Monitoring, and a separate budget.

A reference governance architecture:

~~~mermaid
flowchart TD
    ID["Cloud Identity / Google Workspace: retailone.example"]
    ID --> USERS["Users: dev, qa, sre, finance"]
    ID --> GROUPS["Groups: gcp-dev, gcp-qa, gcp-sre, gcp-finops"]
    ORG["Google Cloud Organization"] --> ENG["Folder: Engineering"]
    ENG --> DEV["Project: retail-dev"]
    ENG --> STG["Project: retail-staging"]
    ENG --> PROD["Project: retail-prod"]
    ORG --> SHARED["Folder: Shared-services"]
    SHARED --> OBS["Project: central-monitoring"]
    GROUPS -. "IAM role at appropriate project/folder" .-> DEV
    GROUPS -. "Scoped roles and least privilege" .-> STG
    GROUPS -. "Read-only production and approved permissions" .-> PROD
~~~

### 9.1. Group-Based Permission Design

| Hypothetical Group | Need | Illustrative Permissions | Control Conditions |
|---|---|---|---|
| `gcp-devs@retailone.example` | Develop APIs in dev | Roles needed to deploy/observe in dev | No default roles in prod |
| `gcp-qa@retailone.example` | Test in staging | Roles to view and run approved QA tasks | Isolated from modifying production databases |
| `gcp-sre-readers@retailone.example` | Monitor prod operations | `roles/logging.viewer`, `roles/monitoring.viewer` as appropriate | Does not automatically grant deploy or raw data read access |
| `gcp-prod-deployers@retailone.example` | Execute prod releases | Reviewed Cloud Run deploy and related roles | Approval workflow, logging, separated from app runtime |
| `gcp-finops@retailone.example` | Multi-project cost reporting | Appropriately scoped billing/cost viewer | Does not need project Owner or IAM admin |

**Cloud Run deployment roles** may require multiple permissions, including permissions on the service, images, and acting as the runtime service account; therefore, do not grant one role by name and assume the pipeline will work. Test exact operations in a sandbox and grant additional permissions narrowly.

### 9.2. Process When an Employee Moves to Production Operations

Developer `lan@retailone.example` moves to SRE.

1. The previous team owner approves removing membership from `gcp-devs` once handoff is complete.
2. The new team owner requests adding her to `gcp-sre-readers`; IT verifies active identity and policy-compliant MFA.
3. Security/cloud owner confirms production roles only allow **viewing logs/metrics**, not administering Cloud SQL.
4. If emergency deployment is required, request time-bound privileged access with logging/approval; never add permanently to a deploy group because of a single incident.
5. During periodic reviews, check group membership, direct IAM bindings, and permissions inherited from folders/organization.

### 9.3. Incident: Employee Left Yet Still Has Access

A former employee was removed from `gcp-devs`, yet an audit reveals they still appear in production policies. Possible causes:

- Granted IAM **directly** at the project level.
- Member of **another group** or a nested group.
- Inherited permissions from a **folder/organization**.
- A service account key or automation credential previously managed by the employee still exists.
- Account deactivation and session revocation were incomplete.

Resolution is to trace every grant path, revoke per policy, and verify the result. Do not blindly strip project policies, as that could break service accounts running Cloud Run or GKE.

## 10. Project Governance, IAM, and Organization Policy

Cloud Identity handles users and groups. Google Cloud needs an additional resource governance layer:

### 10.1. Organization / Folder / Project Structure

- Use the **organization** as the cloud governance boundary, assign owning teams, and protect high-privilege roles.
- Use **folders** to group products/environments or business units sharing policies.
- Use **projects** as boundaries for operations, resources, quotas, billing, and workload-scoped IAM.
- Audit **ancestor IAM bindings** because roles at the organization/folder level can grant permissions to all child projects under inheritance rules.

### 10.2. Organization Policy Is Not an IAM Role

**Organization Policy Service** enforces configuration constraints when supported resources are created, modified, or used—for example, restricting certain sharing patterns or non-compliant settings. IAM determines **who can invoke a permission**; Organization Policy can still cause an IAM-allowed operation to fail because the configuration violates a constraint.

For instance, a company wants to prevent IAM sharing with identities outside approved domains/lists. You can evaluate policies restricting allowed IAM principals per current Google Cloud capabilities; test impacts on partners, CI/CD federation, and Google service accounts before enforcing in production. **Do not assume domain verification automatically enables a policy blocking all external identities.**

### 10.3. Access Separation and Billing Management

A managed user may belong to a GKE operations group without having **billing account admin permissions**. The billing IAM model is a separate scope. Assign cost-viewing and budget management to the FinOps/Finance team; use project/label cost attribution as part of governance, rather than granting organization-wide Owner/Editor just for reporting needs.

## 11. Safe Inspection Tools and Commands

Identity and group configurations can be viewed in the **Google Admin console** at `https://admin.google.com/` with appropriate admin privileges. Google Cloud projects, IAM, resources, and audits are managed in the **Google Cloud console** at `https://console.cloud.google.com/`.

If authorized, several **read-only** commands in Cloud Shell or a workstation with Google Cloud CLI:

~~~bash
# Check the currently active CLI identity.
gcloud auth list

# List organizations the current account is allowed to view.
gcloud organizations list

# Inspect a project whose ID you already know.
gcloud projects describe PROJECT_ID \
  --format="yaml(projectId,projectNumber,name,parent)"

# Inspect project IAM (does not modify permissions).
gcloud projects get-iam-policy PROJECT_ID \
  --format=json
~~~

Replace `PROJECT_ID` with a real approved identifier. Output reflects only resources and policies you **have permission to view**, not necessarily the entire enterprise scope. An account may see users/groups in the Admin console yet lack permissions to run `gcloud organizations list` or `get-iam-policy`.

If authorized to read organization IAM, you can use:

~~~bash
gcloud organizations get-iam-policy ORGANIZATION_ID --format=json
~~~

The output shows the **allow policy at organization scope**; to explain a person's effective permissions on a VM or Cloud Run service, you must also evaluate lower-level bindings, group memberships, conditions, deny policies, and related policies.

### 11.1. Read-Only Practice

1. Identify an authorized **sandbox** project.
2. Run `gcloud auth list` and `gcloud projects describe PROJECT_ID`.
3. If the organization is visible, note the organization ID and projects within the relevant governance scope.
4. Inspect project IAM: locate a `group:...` binding and its role/scope; do not modify bindings.
5. Cross-reference which unit owns the group, who manages membership, and why the group needs that role.
6. Separately inspect **Billing**, **Monitoring**, and Compute/GKE/Cloud Run services to observe how the same identity can hold different permissions across systems.
7. Document visibility limits if the Console or CLI returns `PERMISSION_DENIED`.

No real managed users, new projects, or IAM role grants need to be created for this exercise.

## 12. Identity Security and Auditing

A strong identity management program detects misconfigurations before incidents occur.

| Risk | Signal to Monitor | Mitigation |
|---|---|---|
| Admin account compromise | Unusual sign-ins, MFA/role changes, anomalous access | Phishing-resistant MFA, monitoring, and incident response procedures |
| Uncontrolled proliferation of Super Admins | Growing admin account list, unclear owners | Limit count, use delegated admins, regular reviews |
| Widespread direct IAM grants | Many `user:...` entries in project/folder policies | Prefer group-to-role, standardize access requests |
| Ownerless production groups | Unclear who adds/approves members | Assign owners, restrict membership management, audit |
| Departed staff retaining access | Active accounts or old credentials still used | Joiner–mover–leaver, check sessions/keys, confirm offboarding |
| Service account keys stored in source code | Exposed secrets, hard-to-trace usage | Use service identities and federation, strict secret/key governance |
| Overly broad IAM scope | Organization-level roles for single-project needs | Narrow scope to project/resource and audit inherited grants |
| IdP/group sync failures | New hires lack access or movers keep old access | Monitor sync, test lifecycle flows, handle exceptions |
| Confusing OUs with Cloud Folders | Users assume OU changes grant cloud permissions | Separate controlled IAM mapping workflow |

### 12.1. Distinguishing Audit Sources

- **Google Admin/Cloud Identity audit:** events related to identities, users, groups, sign-ins, and admin config changes, depending on support tier and licensing.
- **Cloud Audit Logs:** Google Cloud resource changes, IAM policies, and service API calls/commands per log type and configuration.
- **Cloud Logging / Monitoring:** operational logs, metrics, and alerts for Compute Engine, GKE, Cloud Run, databases, and other components.
- **Ticket/HR/ITSM systems:** access requests, approvals, department transfers, and departures.

Never conclude "no group changes occurred" just because no event appears in a **project's Cloud Audit Logs**; Cloud Identity membership administration belongs to the corresponding identity audit source.

### 12.2. Audit Read Access Must Also Be Restricted

Sign-in reports, memberships, principal details, resources, and error logs may contain sensitive data. Grant read access only to authorized teams, set appropriate retention, and never publish tokens, passwords, or employee exports to public repositories.

## 13. Common Troubleshooting Scenarios

| Symptom | Possible Cause | Controlled Check |
|---|---|---|
| Employee can sign in but sees no projects | Missing IAM, wrong account, org/folder scope, or missing view permission | Check Google account, project ID, and group/role bindings |
| Group looks right in Admin console yet `PERMISSION_DENIED` | IAM not bound, role lacks permission, policy blocks, or sync pending | Check effective access, permission, scope; retry after propagation |
| Organization resource not visible | Domain/org setup incomplete, wrong account, or missing permissions | Verify tenant, domain verification, and organization view permissions |
| Cloud IAM admin cannot edit users | Cloud IAM differs from Admin console privileges | Identify approved delegated admin/Super Admin |
| Super Admin cannot operate cloud resources as expected | Role scope and IAM policy mismatch, org policy, or other control blocking | Check effective permissions on the resource rather than inferring from title |
| Departed user still appears in IAM | Direct role, another group, inherited policy, incomplete update | Audit all grant paths and account status |
| User fails to sign in via IdP | SSO linkage, identifier mismatch, certificate, sync, or auth policy | Check IdP/Cloud Identity audit logs and federation config |
| CI/CD deploy fails after employee identity change | Pipeline depended on personal credentials or service account lacks role | Switch to workload identity and specific automation roles |
| Cannot create resource despite valid IAM role | Organization Policy, API not enabled, quota, billing, or network constraint | Read service error, check policies and project status |
| Group audit logs missing | Looking in wrong system or missing permissions/retention | Separate Google Admin audit from Cloud Audit Logs |

**Diagnostic methodology:** establish **principal**, **resource**, **permission**, **IAM scope**, **timestamp**, **grant path**, and **additional policies** before proposing new permissions. When needed, use **Policy Troubleshooter for IAM** to inspect allow/deny reasons based on current data.

## 14. Design Exercise: Multi-Environment Enterprise

An enterprise owns the domain `academy.example` with 60 employees. They deploy:

- `academy-dev`: Cloud Run APIs, Cloud Storage with practice data.
- `academy-test`: GKE for integration testing.
- `academy-prod`: Cloud Run, Cloud SQL with live customer data.
- `academy-shared`: shared Logging/Monitoring and pipelines.
- One shared billing account, yet **only Finance and FinOps may view total account-wide spend**.

There are four user groups: **Developers**, **QA**, **SRE**, and **Finance**. An external contractor will assist for only 30 days; one developer just transferred to SRE; and one finance employee is about to leave.

Answer the following:

1. Why should managed Google Accounts/Cloud Identity or Google Workspace be used for employees? What operational drawbacks do personal accounts have?
2. Design two trees: **OU/user/group** in the identity system and **Organization/folder/project** in Google Cloud. How do their purposes differ?
3. Propose group names and roles/scopes for Developers, QA, SRE, and Finance. Which permissions should avoid being granted at organization scope?
4. A user is already a member of `gcp-sre@example.com` yet still cannot view production Cloud Run. What will you check?
5. When a developer moves to SRE, which permissions must the transition workflow revoke? Why is removing them from one group not enough?
6. How will the 30-day contractor be protected? Consider managed accounts, federation under an appropriate model, time-bound permissions, and approving owners.
7. When the Finance employee leaves, which sources must be checked beyond Google Groups?
8. When the Cloud Run runtime needs to read Cloud Storage, why should a dedicated service account be used instead of an SRE's account?
9. Distinguish group membership admin events from project IAM binding change events: which audit source typically records each?
10. State three criteria proving the design meets security goals and three criteria proving it does not disrupt operations.

**Reference comparison:** A strong design grants permissions via groups and narrow roles on appropriate projects, establishes clear owning accounts/groups, enforces user MFA, runs services with service identities, monitors inherited permissions, tightly governs contractor exceptions, and executes end-to-end offboarding verification. Finance holds appropriately scoped billing permissions without needing permissions to deploy Cloud Run/GKE.

## 15. Checklist for Operating Cloud Identity in an Organization

- [ ] Corporate domain is verified; DNS and tenant administrative owners are assigned.
- [ ] Super Admin/delegated admin roster, approval workflow, and access recovery procedures exist.
- [ ] Organization resource, owner, and folder/project structure are defined.
- [ ] Identity OUs are distinguished from resource folders; no assumption of automatic synchronization.
- [ ] Employees use corporate identities with MFA/SSO and appropriate session policies.
- [ ] Workflows exist to create/sync/change groups/deactivate accounts driven by HR/IT sources.
- [ ] Google Groups have owners, membership rules, grant/revocation workflows, and periodic reviews.
- [ ] IAM roles are bound to groups at the lowest sensible scope; direct and inherited grants are audited.
- [ ] Compute Engine, GKE, Cloud Run, and CI/CD services use dedicated workload identities, minimizing long-lived keys.
- [ ] Billing/FinOps permissions are separated from production resource modification permissions.
- [ ] Auditing is enabled for both identity and cloud policies; owners receive alerts on sensitive changes.
- [ ] Joiner, mover, leaver, external accounts, and emergency recovery paths have been tested.
- [ ] A plan exists to review features against current Cloud Identity/Workspace editions and policies.

## 16. References

When deploying in a live organization, always check the latest feature availability, licensing, limits, and interfaces in official documentation:

- [Cloud Identity overview](https://cloud.google.com/identity/docs/overview)
- [Cloud Identity documentation](https://cloud.google.com/identity/docs)
- [Cloud Identity editions](https://cloud.google.com/identity/pricing)
- [Google Cloud resource hierarchy](https://cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy)
- [IAM overview](https://cloud.google.com/iam/docs/overview)
- [IAM best practices](https://cloud.google.com/iam/docs/using-iam-securely)
- [Workforce Identity Federation](https://cloud.google.com/iam/docs/workforce-identity-federation)
- [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation)
- [Google Workspace Admin Help](https://support.google.com/a/)

**Key takeaway:** Cloud Identity manages **identities and user lifecycles**, whereas Google Cloud IAM manages **permissions on resources**. The most important bridge is typically **well-governed groups and properly scoped IAM bindings**. With SSO/MFA, separation of human and workload identities, joiner–mover–leaver processes, and clear auditing, an organization gains a secure foundation for running Compute Engine, GKE, Cloud Run, data services, and cost management across many projects.
