# Designing least privilege and separation of duties

A Google Cloud system can be properly deployed on Compute Engine, Google Kubernetes Engine (GKE), Cloud Run, and data services yet still suffer a severe incident if a human or application identity holds excessive permissions. For example, an account used to release a Cloud Run revision only needs to update its assigned service, yet is granted Owner on the entire project: if that account is compromised, an attacker can alter IAM, system configurations, and many unrelated resources.

In the **IAM and authentication** chapter of the **CLOUD_PROVIDERS_GCP** module, this lesson focuses on two principles:

- **Least privilege:** each identity is permitted to perform only the operations required for its job, on the exact resources, for the duration needed.
- **Separation of duties (SoD):** sensitive actions such as privilege approval, production deployment, billing management, and auditing are divided so that a single person or account cannot execute an entire high-risk workflow alone.

After this lesson, you can build an IAM permission matrix, select appropriate grant scopes, distinguish deployment identities from runtime identities, spot privilege escalation paths, and design workflows for granting, verifying, and revoking access. These decisions support Google Cloud's goals for resource protection, release automation, and controlled operations.

## 1. Understand IAM mechanics before designing permissions

### 1.1. Authentication and authorization are two distinct steps

**Authentication** answers the question *who is calling?* The identity may be a user, a group via user membership, a service account, or a principal representing a workload outside Google Cloud via identity federation.

**Authorization** answers the question *what is that identity allowed to do on which resource?* Google Cloud IAM evaluates relevant policies to decide whether to permit a specific operation.

For example, a developer signed in with a corporate account (authenticated) is not automatically permitted to delete a Cloud SQL instance. They still need appropriate permissions on the resource. Similarly, a service account used by Cloud Run to obtain tokens does not automatically have permission to read every bucket in the project.

### 1.2. Components of an access grant

| Component | Role in the decision | Example |
| --- | --- | --- |
| **Principal** | Identity whose access is evaluated | `user:dev@example.com`, `group:cloud-deploy@example.com`, `serviceAccount:api-runtime@PROJECT_ID.iam.gserviceaccount.com` |
| **Permission** | Specific operation on an API/resource | `run.services.update`, `storage.objects.get` |
| **Role** | Packaged set of permissions | `roles/run.developer`, `roles/storage.objectViewer` |
| **Resource** | Subject governed by policy | Organization, folder, project, Cloud Run service, bucket, or service account |
| **Allow policy / binding** | Links a principal to a role at a scope | Assigning a deploy group an appropriate role on a project or service |
| **Condition (if any)** | Condition limiting binding validity when supported | Restricting by timestamp or supported resource attributes |

Main role categories:

1. **Basic roles** such as Owner, Editor, and Viewer: broad scope, hard to control precisely; avoid using for day-to-day operations when narrower roles exist.
2. **Predefined roles**: defined by Google Cloud by product/function, such as Cloud Run Developer or Storage Object Viewer; usually the first choice.
3. **Custom roles**: organization selects a set of permissions when built-in roles grant too much or too little; requires maintenance as APIs and features change.

A role is only a collection of permissions. **Effective permissions** also depend on where the binding is attached, inheritance from the resource hierarchy, and other restricting policies.

### 1.3. Grant scope and inheritance

Google Cloud uses a governance structure:

~~~text
Organization
└── Folder: Production
    ├── Project: shop-prod
    │   ├── Cloud Run: checkout-api
    │   ├── Cloud Storage: invoices
    │   └── Service account: checkout-runtime
    └── Project: analytics-prod
~~~

An IAM allow binding granted at an organization, folder, or project is generally inherited down to child resources according to IAM rules. For example, a group holding a broad role at the Production folder can receive permissions across both `shop-prod` and `analytics-prod`. Granting a narrow role on a Cloud Run service or bucket can reduce blast radius compared to granting the same role across the whole project, **if the resource type and role support grants at that scope**.

Things to remember:

- You cannot inspect only the IAM policy directly attached to a resource and conclude its complete effective permissions; you must examine bindings inherited from ancestors.
- Adding a narrow binding on a child project generally **does not remove** permissions inherited from a folder or organization.
- The existence of an allow binding does not guarantee an operation will succeed: IAM Deny, principal access boundary, Organization Policy, other conditions, or product-level permission checks can affect the result.
- Organization Policy generally controls resource configuration and usage (such as restricting allowed actions/configurations), so it should not be treated as a replacement for IAM.

**Design rule:** grant at the lowest scope that fulfills the business requirement; only grant permissions at a folder or organization when the duty truly spans multiple projects.

## 2. Designing least privilege around real operations

“Only grant necessary permissions” is not enough if you do not know exactly what a user or application must do. Start from a list of tasks rather than starting from role names or job titles.

### 2.1. Mapping identity – operation – resource

Suppose an e-commerce system has a Cloud Run API, Cloud SQL, and Cloud Storage. The development team, CI/CD pipeline, API runtime, network ops team, and audit team need very different permissions.

| Identity or group | Required task | Resource | How to restrict |
| --- | --- | --- | --- |
| Developer | View application logs, check release status | Services and logs in the dev environment | Appropriate read permissions, avoiding IAM modification rights |
| Deployment pipeline | Update a Cloud Run service and use the designated runtime service account | Production service, runtime service account | Scoped deploy permissions + actAs permission on the exact service account |
| API runtime | Read input objects and connect to required database | Permitted bucket or data path, Cloud SQL | Narrowest role; database also has its own authentication and authorization |
| Network team | Manage subnets, routes, or network configs as assigned | Assigned project or network | Appropriate network roles; separate firewall management if needed |
| Finance team | View costs and budgets | Cloud Billing account | Appropriate Billing roles, without workload management rights |
| InfoSec team | Inspect policies, assess permissions, and review audit evidence | Projects within monitoring scope | Read-only audit roles; separate workflow when edit access is needed |

Not every task has a single predefined role that fits perfectly. When that happens, consider binding roles on specific resources, splitting workflow steps, or using custom roles if supported by the permissions list.

### 2.2. Choosing roles in order

1. **List required operations:** e.g., reading objects only, pulling images, updating Cloud Run revisions, or connecting to Cloud SQL.
2. **Find corresponding permissions:** check API methods and service IAM docs; do not infer from labels like “Viewer” or “Developer”.
3. **Prefer narrow predefined roles:** such as `roles/storage.objectViewer` for object reading or `roles/run.developer` for appropriate Cloud Run development/deployment duties.
4. **Choose the smallest binding scope:** specific bucket, specific service, or project if it cannot be narrowed further while remaining operational.
5. **Check indirect permissions:** permissions to edit workloads, attach service accounts, or modify pipelines can open a path to use a more privileged identity.
6. **Test valid and invalid operations:** verify users can do their assigned job, yet cannot modify out-of-scope resources.
7. **Review over time:** when staff change teams, services change behavior, or permissions go unused, revoke redundant bindings.

**Example:** a job that only needs to fetch product images from bucket `shop-product-images` should not be granted Storage Admin on the project. A `roles/storage.objectViewer` binding on that exact bucket is much closer to the requirement. Even so, reading all objects inside a bucket may still be broader than necessary: if data spans multiple sensitivity tiers, consider splitting buckets or designing permissions and conditions to match the data model.

### 2.3. Distinguishing view, operational, and permission-granting rights

Three categories of operations demand special care:

- **Reading sensitive data:** can directly expose customer information even without permission to change configurations.
- **Modifying services:** can alter code, container images, environment settings, networking, or data egress points. A “Developer” permission still carries significant security impact in production.
- **Administering IAM or identities:** can assign roles, edit policies, enable impersonation, or modify release paths. This is a privilege escalation vector if left uncontrolled.

A role name sounding “low privilege” is not enough to assess risk; examine both specific permissions and practical impact on the system.

## 3. Separation of duties to prevent self-granting and self-approval

Separation of duties (SoD) means sensitive steps have different accountable owners, with approval trails and post-facto auditability. The goal is to reduce the chance that an operational error, compromised account, or malicious actor causes system-wide damage.

### 3.1. Duties that should be separated

| Process | Suggested role | Key boundary |
| --- | --- | --- |
| Request IAM access | System owner or requester | Requester states task, resource, and duration; does not self-approve privileged access. |
| Approve privileges | Resource owner / security lead | Approves justification and privilege level; independent of the requester. |
| Execute IAM changes | IAM admin team or controlled config pipeline | Permitted to set policies in assigned scope, preserving history and approval source. |
| Release applications | Deployment pipeline and release team | Permitted to update required workloads; does not manage all service accounts or organization IAM. |
| Network administration | Network team | Appropriate network roles; major firewall policy changes have a separate review step. |
| Billing administration | Finance / FinOps | Views or manages Billing account; does not inherently hold permission to delete databases. |
| Inspection and audit | Security/audit team | Read access to logs and policies; independent channel to report discrepancies. |
| Emergency recovery | On-call responder with time-bound process access | Grants time-limited access, logs justification, and revokes after the incident. |

Small companies do not need a separate department for every row. What matters is **separating conflicting actions**, such as avoiding the same person self-approving Owner access, granting it to themselves, and signing off on their own audit. With smaller teams, peer approvals, pull request reviews, temporary access, and independent logging can provide compensating controls.

### 3.2. Example of an approval-based authorization workflow

~~~mermaid
flowchart TD
    R["User requests access"] --> T["Specify task, resource,<br/>role, and duration"]
    T --> A{"Resource owner / security approves?"}
    A -->|No| X["Reject or request revision"]
    A -->|Yes| I["IAM admin / pipeline applies binding"]
    I --> V["Test permissions and log event"]
    V --> M["Track expiration and review periodically"]
    M --> E["Revoke access when no longer needed"]
~~~

A valid request must give the approver enough information to answer: *Who needs access, to perform which task, on which resource, for how long, what is the impact if abused, and who is accountable?* If the answer is merely “need Editor to work conveniently,” re-analyze the task.

### 3.3. Privilege escalation paths easily overlooked

1. **Attaching a powerful service account to a workload:** a principal with permission to deploy or edit a workload plus `iam.serviceAccounts.actAs` on a privileged service account can execute code under that identity. Therefore, **Service Account User** (`roles/iam.serviceAccountUser`) must be tightly restricted.
2. **Impersonating a service account:** `roles/iam.serviceAccountTokenCreator` enables creating delegated credentials/tokens per the role's specific permissions; if granted on a high-privilege service account, the assignee can invoke APIs with that service account's permissions.
3. **Editing pipelines or trusted code repositories:** even if an editor lacks direct production access, an automated pipeline may hold production deployment rights. Protect release branches, enforce code reviews, and lock down pipeline configs.
4. **Granting IAM at parent scopes:** roles placed on a folder or organization can grant permissions across existing projects and future projects created in that branch.
5. **Sharing admin accounts:** if multiple people share one login account, accountability breaks down and revoking a single individual's access becomes difficult.

In all of these cases, checking solely whether a principal holds the Owner role is insufficient. You must evaluate **the ability to control a higher-privileged identity or workflow**.

## 4. Designing workload identities and service accounts

Applications need to call Google Cloud APIs using an identity, and that identity should not be a developer's personal account. A **service account** represents an application or automated component, enabling function-based access control and owner transitions without changing the workload's identity.

### 4.1. Separating runtime and deployment identities

Suppose a company runs an ordering API on Cloud Run:

| Identity | When used? | Permissions matching the duty |
| --- | --- | --- |
| `checkout-runtime@...` | API handling requests | Read required objects in bucket; Cloud SQL connection permissions; corresponding permissions for dependent services |
| `checkout-deploy@...` | Pipeline releasing Cloud Run revisions | Service update permissions; permission to use the exact runtime service account |
| Group `cloud-developers@...` | Developing, testing, and proposing releases | Dev environment permissions, required read access; no self-granting production IAM |
| Group `iam-reviewers@...` | Reviewing policies and approving privilege requests | Read permissions for review; IAM modification rights only under separately assigned roles |

**The runtime service account does not need permission to modify Cloud Run**, because its job is processing transactions. **The deployment service account does not need to read production order tables**, because its job is releasing application versions. That is the benefit of separating identities by duty.

~~~mermaid
flowchart LR
    Dev["Developer"] --> Repo["Reviewed pull request"]
    Repo --> CI["CI/CD pipeline"]
    CI --> DSA["Deployment service account"]
    DSA --> Run["Update Cloud Run service"]
    Run --> RSA["Runtime service account"]
    RSA --> CS[("Cloud SQL / required data")]
    RSA --> ST[("Scope-limited bucket")]
~~~

The path from pipeline to workload should be understood as **permission to update configuration/revisions**, not freedom to grant IAM across the whole project. However, someone who can alter code running under the runtime service account can leverage the permissions held by that runtime service account. Thus, source code review and release controls are integral parts of least-privilege design.

### 4.2. Three easily confused permissions

| Related permission or role | What does it allow? | Risk if granted broadly |
| --- | --- | --- |
| `roles/iam.serviceAccountUser` | Allows **actAs** on a service account, usually to attach that service account to a resource the principal is allowed to create/edit. | Can run workloads under a stronger identity if deployment is also controlled. |
| `roles/iam.serviceAccountTokenCreator` | Allows certain token/credential creation and impersonation operations per the role's permissions. | Can call APIs with the target service account's permissions. |
| Service account admin rights, e.g., `roles/iam.serviceAccountAdmin` | Manages service account resources per role scope and permissions. | Can modify identity lifecycle/configuration; should not be treated as simple read access. |

These roles **are not equivalent**. Service Account User does not inherently generate access tokens via impersonation APIs; Token Creator does not inherently allow creating VMs. Yet both must be controlled against privilege escalation paths when combined with other privileges.

When a pipeline only needs `checkout-runtime`, consider binding `roles/iam.serviceAccountUser` **on that exact service account** rather than across the entire project. Do not reuse one powerful runtime service account across all applications out of convenience.

### 4.3. Minimizing long-lived service account keys

Downloaded JSON keys can be copied, accidentally committed to repositories, leaked in logs, or reused after staff departures. In Google Cloud environments, prefer **Application Default Credentials (ADC)** with environment-provided identities rather than creating unnecessary static keys.

- **Cloud Run:** attach a dedicated service account to the service; Google Cloud libraries automatically obtain credentials from the runtime environment.
- **GKE:** consider **Workload Identity Federation for GKE** so Kubernetes workloads access Google Cloud resources using configured identities without distributing key files into pods.
- **Compute Engine:** attach an appropriate service account to the VM, managing IAM permissions and related access settings; avoid using overly privileged service accounts.
- **CI/CD outside Google Cloud:** use **Workload Identity Federation** where supported, exchanging short-lived credentials and enforcing identity constraints from trusted sources.

If an exceptional case requires a key, enforce issuance, secure storage, rotation, leak detection, and revocation procedures. Some organizations also use Organization Policy to restrict service account key creation.

**Note:** for Cloud Run, Cloud Build, GKE, and other managed services, distinguish **workload** service accounts, **deployment** service accounts, Google-managed **service agents**, and infrastructure identities. Never arbitrarily grant permissions to service agents or use a service agent as an application account.

## 5. Example permission architecture for an e-commerce system on Google Cloud

An enterprise operates:

- **Project `shop-dev`:** development and testing environment.
- **Project `shop-prod`:** Cloud Run `checkout-api`, Cloud SQL storing orders, Cloud Storage bucket `shop-invoices`, and VPC.
- **CI/CD pipeline:** runs checks, pulls vetted images, and updates production Cloud Run.
- **Operations and audit teams:** monitor performance, reliability, IAM permissions, networking, and costs.

### 5.1. Illustrative authorization matrix

| Principal | Resource/scope | Suggested permission or role | Should not have |
| --- | --- | --- | --- |
| Developers group | Project `shop-dev` | Suitable roles to develop and debug dev services | Organization Owner, production IAM edit rights |
| Production readers group | Production workload logs and status needed for inspection | `roles/logging.viewer`, appropriate service read roles | Policy editing, database modification |
| Deploy pipeline | Cloud Run `checkout-api` in `shop-prod` | Service update permissions within Cloud Run's supported scope; e.g., `roles/run.developer` when appropriate | Project-wide Owner/Editor, access to view all order data |
| Deploy pipeline | Service account `checkout-runtime` | `roles/iam.serviceAccountUser` on the **specific service account** | Permission to actAs all production service accounts |
| Checkout runtime | Required Cloud SQL and bucket | `roles/cloudsql.client` when using a connection type requiring it; `roles/storage.objectViewer` on the bucket if read-only | Project-wide Cloud SQL Admin, Storage Admin |
| Network team | Assigned projects or network resources | E.g., `roles/compute.networkAdmin` and additional roles as duties require | Billing management, application data read access |
| Finance team | Company Billing account | Suitable Billing role such as `roles/billing.viewer` for viewing | Permission to delete data or deploy services |
| Audit team | Audited resources | E.g., `roles/iam.securityReviewer` by scope; required log viewer roles | IAM modification rights, unless separately assigned remediation |

This is a **proposal for discussion**, not a complete ready-to-apply role table. Cloud Run permissions may also require Artifact Registry access, the deployment identity may need extra permissions to update image sources, and Cloud SQL connections still require authentication/authorization **inside the database**. Before implementing, cross-check every real operation against service-supported permissions and resources.

### 5.2. Permission flow from code to database

When a developer modifies the API, the release workflow can look like:

1. **Code review:** peers inspect the pull request, paying close attention to changes in IAM, secrets, CI workflows, and data access.
2. **Build/test:** the system runs tests using a build-appropriate identity and permissions; never use the production runtime identity to compile builds.
3. **Production approval:** an accountable approver signs off on the release after reviewing build results and risks.
4. **Deploy:** the pipeline's service account updates the exact Cloud Run service and is permitted to actAs the exact runtime service account.
5. **Run:** `checkout-runtime` calls only the Google Cloud APIs needed for orders; privileges inside the Cloud SQL database further restrict queries/tables appropriately.
6. **Audit:** IAM changes, deployments, and audit records can be inspected via logs, governance workflows, and monitoring tools.

If a developer edits code, approves their own pull request, and edits the runtime service account's permissions, separating IAM groups on paper loses effectiveness. Access security must cover the **entire change path**, not just the role table.

### 5.3. Separating production from testing environments

Separating dev and prod projects reduces accidental privilege grants and limits the blast radius of testing. However, if the development team holds Editor on a parent folder containing both projects, inherited permissions can erase that intended boundary.

Your design should combine:

- Folders/projects separated by environment or sensitivity tier.
- IAM bindings using clearly defined groups, preferring groups over individual grants when your organization has reliable membership governance.
- Dedicated service accounts per workload and environment; never share keys between dev and prod.
- Controls over IAM administration, release pipelines, sensitive log access, and data.
- Reviews of permissions inherited from organization levels before assessing a project's effective access.

## 6. IAM mechanisms for trimming excess permissions

### 6.1. IAM Conditions

IAM Conditions let you constrain a binding by **service-supported attributes**, such as timestamp or resource attributes in supported cases.

For example, an incident response group can receive elevated access valid only until a specified time. Check supported roles, resource types, expressions, and attributes. Conditions do not narrow permissions if the expression is flawed, the policy is bound too broadly, or the service does not support the desired attribute.

Do not rely on IAM Conditions as a complete substitute for choosing the right role and scope. Temporary access must also be revoked or expire as planned, with approval records and verification.

### 6.2. IAM Deny and principal access boundary

Beyond allow policies, Google Cloud offers advanced access controls:

| Mechanism | General purpose | Limits to understand |
| --- | --- | --- |
| **IAM Deny** | Prevents specified principals from exercising supported permissions, even if allowed. | Applies only within the permissions, conditions, and rules supported by IAM Deny. |
| **Principal access boundary (PAB)** | Sets the maximum resource boundary principals within policy scope can access, per supported mechanism. | Does not grant new permissions and does not replace allow policies; effectiveness also depends on supported resource types/permissions. |
| **Organization Policy** | Enforces constraints on configuring, creating, and using resources via constraints. | Not an allow role or an automatic limiter for all IAM permissions. |
| **VPC Service Controls** | Adds a data exfiltration control perimeter for supported services/scopes. | Does not replace IAM, database authorization, or application security. |

These mechanisms must be designed alongside IAM, tested with real workloads, and checked against current feature documentation. An overly broad blocking policy can break legitimate workloads across the system.

### 6.3. On-demand and time-bound privileged access

For high-impact admin rights such as modifying top-level IAM, consider a just-in-time access workflow with an approver and explicit expiration. Google Cloud's **Privileged Access Manager (PAM)** is one capability usable in supported scenarios and scopes; eligibility depends on verifying product requirements, admin permissions, and current access scope.

For emergency accounts, enforce strong authentication, monitoring ownership, usage justification logging, and post-incident review. A “break-glass” account should never be used for routine daily work.

## 7. Workflow for granting, verifying, and revoking access

### 7.1. Preparation before changing a policy

Before adding an IAM binding to production, create a change record covering:

1. **Principal:** exact group or service account address; avoid confusing projects inside service account emails.
2. **Task:** exact API operations needed, timing, and business justification.
3. **Resource:** Project ID and specific resource; identify any permissions that could be inherited.
4. **Role and permissions:** verify the proposed role against mandatory permissions.
5. **Indirection:** can the principal impersonate another identity, alter a pipeline, or launch a workload using a stronger account?
6. **Duration:** standing access, task-scoped temporary access, or emergency access.
7. **Approver and test plan:** who accepts the risk, which operations must succeed, and which must fail.

For large or sensitive IAM changes, managing policies via infrastructure-as-code, pull requests, and reviews preserves audit history. Avoid letting two independent policy management mechanisms overwrite the same binding without clear ownership rules.

### 7.2. Inspecting with the Google Cloud CLI

Assume the current identity has permission to read policies on project `shop-prod` and service account `checkout-runtime`. These commands are read-only:

~~~bash
# View IAM bindings attached directly on the project
gcloud projects get-iam-policy shop-prod --format=json

# View direct IAM bindings on a specific service account
gcloud iam service-accounts get-iam-policy \
  checkout-runtime@shop-prod.iam.gserviceaccount.com \
  --project=shop-prod

# Read permissions included in a predefined role
gcloud iam roles describe roles/run.developer
~~~

**Do not conclude a user lacks access merely because no binding appears in the direct policy.** Permissions may be inherited from a folder or organization, granted via groups or other identities, or affected by deny rules, conditions, and additional limits. When you must determine the exact reason behind an access decision, use effective-access analysis tools such as **Policy Troubleshooter** and appropriate IAM Policy Intelligence tools.

Example binding on a Cloud Storage bucket for runtime object reading (illustrative command with write impact):

~~~bash
# Run only after scope and identity have been approved
gcloud storage buckets add-iam-policy-binding gs://shop-invoices \
  --member="serviceAccount:checkout-runtime@shop-prod.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"
~~~

This scenario limits the object viewer role to the designated bucket; granting it on the project would be broader if the project holds multiple buckets. Before applying in production, verify the bucket exists, the principal is exact, and review the bucket's IAM policy and usage conditions. If a single bucket contains data across multiple sensitivity levels, further evaluate whether reading all objects is still too broad.

**Design anti-pattern:** instead of an object-reading role on the bucket, the team grants `roles/storage.admin` on `shop-prod` to the runtime to silence a Permission denied error. That can grant management control over many storage resources beyond business need. The proper fix is reading the error message, identifying the missing permission, and granting least privilege in the exact right place.

### 7.3. Bidirectional verification

An IAM change is only complete when you verify both sides:

- **Required tasks succeed:** e.g., runtime API reads permitted objects, connects to Cloud SQL via the designed mechanism, and the pipeline deploys revisions to the right service.
- **Out-of-scope tasks are denied:** e.g., runtime cannot delete buckets, edit project IAM, or impersonate admin service accounts; the pipeline cannot grant roles to itself.

You can use staging environments, appropriate test commands, and **Policy Troubleshooter** to analyze permissions on specific resources. For wide-reaching policy changes, consider **Policy Simulator** where supported by feature and resource scope to preview impact before applying.

Simulation output or a passing API call is not the sole proof. You still need to review IAM groups, inherited permissions, principals sharing a release path, and the actual data accessed by the workload.

### 7.4. Reviewing and revoking access

Privileges should be tied to **current duties**, not permanently accumulated from a user's past roles. A periodic governance process can include:

1. Reconciling groups and service accounts against active staff, application owners, and active pipelines.
2. Reviewing IAM Recommender suggestions (where eligible), permission usage history, and business evidence to spot underused roles.
3. Auditing Owner/Editor bindings, IAM admin roles, Token Creator rights, actAs rights, and organization/folder-level bindings.
4. Reviewing public principals such as `allUsers` or `allAuthenticatedUsers`, especially on resources holding sensitive data. Public services may need specific configs, which must be deliberate decisions.
5. Removing access for staff who switched teams, expired test accounts, and service accounts no longer used by any workload.
6. Re-testing business flows after revocation, and recording who approved it and why.

Recommender and usage metrics are only **suggestions** and may miss rare yet critical paths such as disaster recovery. Before revoking permissions, check runbooks and infrequent operational needs.

## 8. Monitoring and investigating access

### 8.1. Audit logs and evidence sources

**Cloud Audit Logs** help monitor resource access and management according to provided log types and configuration. For example:

| Log type | Investigative question |
| --- | --- |
| **Admin Activity** | Who changed an IAM policy, resource config, or admin setting? |
| **Data Access** | Which identity read/wrote data via logged APIs, if enabled and supported? |
| **System Event** | Did a Google Cloud system action relate to the incident? |
| **Policy Denied** | Was a request rejected by a logged policy mechanism? |

Audit capture capabilities, default enabled/disabled state, permissions to view log types, and retention depend on the product, event type, and configuration. **Data Access logs** may need explicit enabling and can contain sensitive data; log viewers also need appropriate permissions. Audit logs assist investigations, though they do not guarantee recording every action inside a database or application without separate logging.

Set up alerts or review processes for notable events: organization/folder IAM changes, privileged role grants, service account edits, long-lived key creation, deployment pipeline changes, or anomalous access to sensitive data.

### 8.2. Troubleshooting Permission denied errors

A 403 error can come from IAM, but can also involve authentication, quotas, API setup, Organization Policy, or product-specific authorization. Analyze in order:

1. **Who is the actual identity?** Check the logged-in account, active gcloud configuration, attached service account, ADC, and the token used by the workload.
2. **What operation was denied?** Find the permission required by the API; identify the target resource and its containing project.
3. **Where is the binding granted?** Inspect direct policies, inherited permissions, group memberships, and conditions.
4. **Is there an overriding restriction?** Check IAM Deny, principal access boundary, Organization Policy, API enablement, and other service-supported requirements.
5. **Does the workload have a separate data-access layer?** For instance, Cloud SQL IAM/connector and database users are separate layers; connection permission does not automatically grant `SELECT` on tables.
6. **Granted but not yet effective?** IAM propagation delay or cached credentials may need time or refresh; re-verify carefully.

Never resolve every 403 error by granting Editor or Owner. If an account genuinely lacks a needed permission, grant that exact permission via an appropriate role and document the reason.

## 9. Permission design exercise

### Scenario

Application `order-api` runs on Cloud Run in project `orders-prod`. Order data lives in Cloud SQL; PDF invoices are placed in bucket `orders-invoices`. One pipeline is allowed to release weekly, the support team only needs to read logs to handle incidents, and the finance team tracks budgets via Cloud Billing.

Initially, all four teams share an account `team-admin` with Owner on the project. The API runtime uses the default service account, and the dev team can directly edit the production pipeline.

**Requirement:** redesign permissions to reduce the impact of a compromised identity while maintaining releases, operations, cost monitoring, and incident recovery.

### Practice tasks

1. List at least **six identities** covering developers, release approvers, pipeline, API runtime, finance team, and auditors. Describe each identity's tasks.
2. Build a **principal – permission/role – resource – duration – approver matrix**. Indicate which roles belong on the bucket, service account, project, or Billing account.
3. Distinguish the pipeline's permissions to update `order-api` from the runtime's permissions to read objects/connect to Cloud SQL. Explain why they should not share a single service account.
4. Sketch a potential privilege escalation path if the pipeline can actAs every production service account; propose two control layers to block this path.
5. Define an approval scheme for releases and IAM: where can pull request authors, reviewers, policy changers, and auditors overlap, and where must they remain separate?
6. Design two test cases: one request that **must be allowed** and one request that **must be denied** for the API runtime.
7. Write a revocation procedure for when staff change teams or a pipeline is replaced; identify the audit trail to retain.

### Solution hints

| Initial issue | Improvement |
| --- | --- |
| Everyone uses `team-admin` | Issue separate identities by person, group, and workload; protect privileged accounts with dedicated processes. |
| Runtime uses default service account with unclear permissions | Create a dedicated runtime service account, binding roles only on genuinely needed resources; check inherited permissions. |
| Pipeline deploys with Owner | Grant Cloud Run update rights and actAs on the **exact runtime service account**, without project IAM edit rights unless needed. |
| Finance needs to view budgets | Grant appropriate Cloud Billing roles on the Billing account, separate from order data access. |
| Production changes uncontrolled | Require reviews, proper approvals, change logs, and restricted pipeline permissions. |
| No post-grant verification process | Test both valid access and access that must be denied; monitor audits and review periodically. |

### Self-check questions

**1. Why is `roles/run.developer` alone insufficient to guarantee a pipeline cannot access production data?**  
Because the pipeline can alter the code or configuration of a workload running under the runtime service account; you must evaluate service account usage permissions, runtime permissions, and release review controls together.

**2. Is Service Account User equivalent to Token Creator?**  
No. They are distinct permissions; however, both can contribute to privilege escalation when combined with workload management rights or granted on an overly powerful identity.

**3. Why can't you read only the direct IAM policy on a project to determine complete permissions?**  
Because IAM allow can be inherited from folders/organizations and multiple other controls affect access decisions.

**4. Why is merely separating dev and prod projects insufficient?**  
Because roles granted on a parent folder, shared groups, shared service accounts, or cross-environment pipeline permissions can still break isolation.

**5. If a permission needed for a rarely used recovery workflow is flagged as unused by IAM Recommender, should you remove it immediately?**  
Do not remove solely based on usage stats. Assess recovery scenarios, consider time-bound emergency access, and test runbooks.

## Official Google Cloud references for implementation

- **IAM overview:** https://cloud.google.com/iam/docs/overview — identities, permissions, roles, and policies.
- **Resource hierarchy and IAM:** https://cloud.google.com/iam/docs/resource-hierarchy-access-control — grant scope and inheritance.
- **Use IAM securely:** https://cloud.google.com/iam/docs/using-iam-securely — secure access management practices.
- **IAM Conditions:** https://cloud.google.com/iam/docs/conditions-overview — conditions and supported scenarios.
- **IAM Deny:** https://cloud.google.com/iam/docs/deny-overview — deny policies.
- **Service accounts:** https://cloud.google.com/iam/docs/service-account-overview — workload identities, impersonation, and management.
- **Workload Identity Federation:** https://cloud.google.com/iam/docs/workload-identity-federation — federating external workload identities into Google Cloud.
- **Privileged Access Manager:** https://cloud.google.com/iam/docs/privileged-access-manager — managing on-demand privileged access.
- **Cloud Audit Logs:** https://cloud.google.com/logging/docs/audit — log types and collection scope.
- **IAM Policy Intelligence:** https://cloud.google.com/iam/docs/using-policy-intelligence — evaluating and remediating inappropriate permissions.

Role names, permission lists, binding placement scope, and support for advanced mechanisms can change. When implementing in practice, always verify against the service's IAM docs, organization policies, and actual APIs before granting permissions in production.
