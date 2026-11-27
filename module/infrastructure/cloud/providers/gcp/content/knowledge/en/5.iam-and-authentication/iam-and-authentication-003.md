# Effective permissions and IAM policy inheritance

When a developer opens Google Cloud Console and sees they have permission to view a project yet cannot deploy Cloud Run, a common question is: **“Why do I have a role on the Folder and still get denied?”** The opposite case is even more dangerous: the team removed a permission in the production project, yet a user can still perform the operation because the permission was granted from the Organization or a parent Folder.

This is why you need to understand **effective permissions** and **IAM policy inheritance**. In Google Cloud, IAM does not evaluate only the policy attached directly to the target resource: the system also considers policies at ancestor levels and other access-restricting mechanisms.

This lesson belongs to the **IAM and authentication** chapter of the **CLOUD_PROVIDERS_GCP** module. Effective permission calculation comes up in every task across the module: project separation, using VPCs, deploying Compute Engine, GKE, and Cloud Run, accessing Cloud Storage/databases, automating releases, and controlling security, cost, and reliability.

After this lesson, you can:

- Distinguish **principal**, **role**, **permission**, **policy**, and **binding**.
- Identify which resources inherit Allow policies from Organization, Folder, and Project.
- Explain why deleting a binding at the project level does not revoke permissions granted from a parent level.
- Identify the impact of **IAM Deny**, **IAM Conditions**, and **Principal Access Boundary**.
- Evaluate a specific access request by principal, permission, resource, and context.
- Verify permissions using Console, `gcloud`, and **Policy Troubleshooter**.

## 1. Concepts to distinguish

Google Cloud IAM decides **who can perform which action on which resource, under which conditions**.

| Concept | Meaning | Example |
|---|---|---|
| **Principal** | Identity whose permissions are checked | User, Google Group, service account, workforce/workload identity |
| **Permission** | A specific action required by an API | `resourcemanager.projects.get`, `run.services.update` |
| **Role** | A collection of permissions managed together | `roles/viewer`, `roles/run.admin` |
| **Allow policy** | Policy containing role bindings that grant permissions to principals | Policy on project `orders-dev` |
| **Role binding** | Binds a role to one or more principals, optionally with a condition | Group `devs@example.com` receives `roles/viewer` |
| **IAM Condition** | Expression limiting when/under what context a binding applies | Only valid until a specific timestamp |
| **Deny policy** | Policy denying permissions for specified principals | Prevent a group from using a dangerous permission |
| **Principal Access Boundary (PAB)** | Policy restricting the set of resources a set of principals is eligible to access | Only eligible to access resources within a defined scope |

**A role is not equivalent to a permission.** A role contains multiple permissions; to know whether a specific operation can be performed, you must find the permissions the API actually checks. A role name suggests its intended purpose, but is not enough to conclude every access capability.

**A principal is not necessarily a person.** Applications running on Cloud Run, VMs, or CI/CD pipelines can use service accounts; in that case, the workload identity's permissions differ from those of the developer deploying the application.

**Authentication differs from authorization:** authentication identifies who is sending the request; IAM authorization decides what that identity is allowed to do. Logging in successfully does not mean automatically receiving permissions on a project.

## 2. IAM policies attached to the resource hierarchy

A company's system might be organized as follows:

~~~text
Organization: example.com
├── Folder: engineering
│   ├── Folder: nonproduction
│   │   ├── Project: orders-dev
│   │   └── Project: orders-staging
│   └── Folder: production
│       └── Project: orders-prod
│           ├── Cloud Run service: orders-api
│           └── Cloud Storage bucket: orders-exports
└── Folder: security
    └── Project: security-logs
~~~

Lower-level resources have an **ancestry chain**:

~~~text
orders-api
→ orders-prod
→ production
→ engineering
→ example.com
~~~

When evaluating permissions on `orders-api`, IAM inspects Allow policies attached directly to the resource (if supported by the service) and at ancestor levels. IAM does not pull policies from `orders-dev` or `security-logs` because those two projects are not ancestors of `orders-api`.

**Key point:** placing a binding at the Organization affects a wide scope; placing one at a Folder affects resources inside that Folder; placing one at a Project affects only that project and its resources; bindings directly on service resources (when supported) usually have a narrower scope.

Not every service supports attaching IAM policies directly at every child resource level. Therefore, check the IAM documentation for Compute Engine, GKE, Cloud Run, Cloud Storage, or the specific service before designing binding scope.

## 3. How does Allow policy inheritance work?

**Allow policies inherit top-down.** A binding placed at an Organization, Folder, or Project applies to that resource and its child resources within supported scope. Inherited bindings and directly attached bindings are both evaluated when computing permissions.

You can picture a resource's **effective allow policy** as the union of:

~~~text
Allow policy on the resource
+ Allow policy on the parent project
+ Allow policy on the parent folder and ancestor folders
+ Allow policy on the organization
---------------------------------------------------
= Effective allow policy (bindings that can grant permissions)
~~~

This is a **union of permission-granting opportunities**, not an intersection. If a valid binding at a parent level grants the permission in question, a narrower Allow policy at the project level cannot by itself “negate” that binding. Each binding is evaluated independently, including any condition attached to it.

### Example: granting permissions at three levels

Suppose the system has the following Allow bindings:

| Level | Principal | Role | Meaning |
|---|---|---|---|
| Organization `example.com` | `group:auditors@example.com` | `roles/viewer` | Audit group receives the view permissions included in the role across many projects |
| Folder `nonproduction` | `group:developers@example.com` | `roles/editor` | Development group receives relatively broad permissions in dev/staging |
| Folder `production` | `group:developers@example.com` | `roles/viewer` | In production, developers primarily have the view permissions matching the role |
| Project `orders-prod` | `serviceAccount:deploy-orders@ci-tools.iam.gserviceaccount.com` | `roles/run.admin` | Deployment identity has permissions to manage Cloud Run within the project scope |

*Note:* `roles/editor` is a **broad basic role**, used here to clearly illustrate differences across levels; real systems should prefer specific predefined roles following least privilege.

If **Lan** belongs to `developers@example.com`, we get:

| Access | Relevant binding | Conclusion at the Allow layer |
|---|---|---|
| Lan operates on `orders-dev` | `roles/editor` inherited from `nonproduction` | Has Editor permissions applicable to that resource and request |
| Lan operates on `orders-staging` | `roles/editor` inherited from `nonproduction` | Same as `orders-dev` |
| Lan views info in `orders-prod` | `roles/viewer` inherited from `production` | Has view permissions granted by this role |
| Lan edits production Cloud Run | Only Viewer from `production` | Viewer does not inherently grant deployment rights; must check other bindings if any |
| Deployment service account edits production Cloud Run | `roles/run.admin` on project `orders-prod` | Can receive Cloud Run permissions from the role, still must satisfy other operation requirements |

This example only shows **which permissions Allow can grant**. The final access outcome also depends on Deny, PAB, conditions, and other technical requirements.

### A person with multiple bindings accumulates permissions

If Lan also belongs to `auditors@example.com`, Allow bindings from both groups are considered. IAM does not pick “the role closest to the resource” or “the role with the smaller name”; any valid matching Allow binding can grant the needed permission.

Google Group memberships and service account identities can obscure permissions if you look at only a single binding. When analyzing a user's permissions, check the groups they belong to, including nested group relationships supported by the service.

## 4. Why can't you “remove permissions at the project” to block a parent level?

Suppose `developers@example.com` receives `roles/editor` at Folder `engineering`. An administrator opens IAM on `orders-prod`, sees no Editor binding for the group at the project level, and removes local bindings to restrict access.

Result: **Editor permissions from Folder `engineering` are still inherited.** Removing a binding at the project does not erase bindings granted at a Folder or Organization.

To handle this properly, choose the approach that matches your goal:

1. **Narrow Allow scope:** remove the broad role at Folder `engineering`, then re-grant it at Folder `nonproduction` or only the projects that genuinely need it. This is usually the simplest and cleanest approach.
2. **Use more specific roles:** replace broad basic roles with predefined/custom roles containing only the needed permissions.
3. **Use IAM Deny when exceptions are needed:** if a permission must be prohibited in a subset of resources despite being Allowed at a parent level, consider a Deny policy using supported permissions.
4. **Use PAB when limiting a principal's resource scope:** for example, restricting a set of identities so they are only eligible to access resources within a defined boundary.

**Common mistake:** thinking that placing Viewer on the production project will “override” Editor inherited from the Folder. In IAM, Allow bindings do not override one another like CSS rules; they add together in their ability to grant permissions.

## 5. Deny policies and blocking mechanisms

**IAM Deny** policies are created and attached at the Organization, Folder, or Project level. They apply to the resource where they are attached and its descendants, similar to Allow policy inheritance. A Deny rule can define denied principals, denied permissions, exception principals, and certain supported conditions.

When a Deny rule applies and blocks the permission being checked, that permission is denied **even if** an Allow policy at the same or another level grants it.

~~~text
Allow: group is granted permission P at Folder engineering
                         │
                         ▼
Project orders-prod: Deny permission P for that group
                         │
                         ▼
Request using P on orders-prod resource: BLOCKED
~~~

Example scenario: an enterprise has a shared admin team across many projects, but wants to prohibit certain especially dangerous operations in the production project. They can evaluate attaching a Deny policy on the production project for **permissions supported by IAM Deny**, instead of banning those operations across every project.

Limitations to keep in mind:

- **Deny does not delete Allow bindings.** It blocks the permission when the policy applies; the Allow binding still exists.
- **Not every permission is supported in Deny.** Check the list of Deny-supported permissions before designing.
- **Deny can include principal exceptions**, but exceptions must be configured carefully and never grant permissions to anyone on their own.
- **Conditions in Deny are more restricted than IAM Conditions in Allow**, such as conditions using resource tags as defined by the service.
- A Deny change at the Organization level can affect many projects; assess scope, machine identities, and recovery plans before applying.

Do not use Deny as a band-aid for every case of overly broad grants. Narrow Allow according to least privilege first; Deny fits when you genuinely need a clear prohibition boundary or exception against inherited permissions.

## 6. How does Principal Access Boundary (PAB) differ from Deny?

**Principal Access Boundary** defines which resources the principals in a **principal set** are eligible to access. PAB **does not grant permissions**; it only caps the resource scope that Allow can grant.

For example, an organization wants to restrict service accounts created by a group of projects so they are only eligible to access resources within a defined scope. Even if a service account receives an Allow binding at a broader scope, PAB can block access outside the allowed boundary for permissions governed by this mechanism.

| Factor | Allow | Deny | PAB |
|---|---|---|---|
| Purpose | Grant permissions | Block permissions | Restrict resources principals are eligible to access |
| Attachment scope | Resource / ancestor supporting IAM | Organization, Folder, Project | Principal set, not attached to resources like Allow/Deny |
| Grants permissions on its own? | Yes, if binding matches | No | No |
| Inherits down resource tree? | Yes | Yes | Not in the same way; depends on principal set membership |
| Used to answer | Who can do what on a resource | Which permissions are banned regardless of Allow | Which zone of resources a principal can reach |

PAB has a **defined scope of permissions governed by the mechanism** and its own evaluation rules. Do not claim a single PAB is an “absolute firewall” for every API. Before using it in production, check supported versions, applicable permission sets, and how multiple relevant PABs combine.

**Distinguish from Organization Policy:** Organization Policy sets constraints on how services, resource types, configurations, or locations can be used; it is not an Allow binding and does not replace IAM. An operation allowed by IAM can still be rejected by Organization Policy, VPC Service Controls, network controls, or service-specific logic.

## 7. IAM Conditions and when permissions take effect

An Allow binding can attach an **IAM Condition** to restrict permissions by supported context: request time, resource attributes, or resource tags in supported cases.

Example of a binding for a support team allowed access during an incident response window until a cutoff time:

~~~json
{
  "role": "roles/viewer",
  "members": [
    "group:support@example.com"
  ],
  "condition": {
    "title": "temporary_support_access",
    "description": "Read access expires after support window",
    "expression": "request.time < timestamp('2027-01-01T00:00:00Z')"
  }
}
~~~

This is only **an illustrative binding** inside an Allow policy, not a complete standalone policy file to apply directly. When a request does not satisfy the condition, this binding grants no permissions. If the same principal still has **another binding** (on this resource or an ancestor) granting that permission unconditionally, access can still be Allowed.

Common mistakes:

- Adding a condition at the project level while overlooking an unconditional binding on a Folder.
- Using condition attributes not supported for the target service or resource being checked.
- Misinterpreting time zones or condition expiration timestamps.
- Assuming a condition in one Allow binding automatically blocks permissions from other roles.

IAM Conditions should be tested with the actual permissions and resources. When investigating time- or request-attribute-dependent scenarios, provide sufficient context to Policy Troubleshooter.

## 8. How to determine the effective permissions of a request

To accurately answer **“Can principal A use permission P on resource R?”**, you need at least four inputs:

1. **Principal:** user email, service account, or workload identifier actually making the request.
2. **Permission:** exact permission checked by the API, e.g., `resourcemanager.projects.get`.
3. **Resource:** full target resource, e.g., project, bucket, or Cloud Run service.
4. **Request context:** timestamp, resource attributes, tags, and relevant conditions.

Conceptual evaluation flow:

~~~mermaid
flowchart TD
    A["Principal sends request for P on R"] --> B{"Matching Allow binding on R or ancestors?"}
    B -- "No" --> X["IAM does not grant access"]
    B -- "Yes" --> C{"Condition of at least one Allow binding satisfied?"}
    C -- "No" --> X
    C -- "Yes" --> D{"Deny rule applies and blocks P?"}
    D -- "Yes" --> Y["IAM denies"]
    D -- "No" --> E{"Relevant PAB blocks access on R?"}
    E -- "Yes" --> Y
    E -- "No" --> F["Permitted by IAM"]
    F --> G["Service may still check APIs, network, Org Policy, and other conditions"]
~~~

This diagram is a **learning model**; it does not depict every internal step of the IAM engine or every policy type Google Cloud supports. Some resource types have dedicated mechanisms or check multiple permissions simultaneously.

You can summarize it as an expression:

~~~text
IAM permits by policy when:
  a matching Allow binding exists (and its condition evaluates to TRUE)
  AND no Deny rule is blocking the permission
  AND no relevant Principal Access Boundary blocks it
~~~

**No Allow** generally means no access, even without a Deny. **Having Allow** is also insufficient if Deny or PAB blocks it. Even when policy permits, the actual request can still fail due to disabled APIs, quotas, network config, other missing permissions, Organization Policy, or service-specific access controls.

### Permissions of groups, users, and service accounts

In a CI/CD system, a user might be allowed to **impersonate** a service account while the final API call runs under the service account identity. You must verify both layers:

- Does the user have permission to use/impersonate the service account via the appropriate mechanism?
- Does the service account have the required permissions on the target resource?

A user having `roles/viewer` on a project does not guarantee a Cloud Run service runs under that user's account, and permissions of the Cloud Run runtime service account do not automatically become permissions of the deployer.

## 9. Practice calculating permissions through scenarios

### Scenario A — Folder permissions propagating down to Projects

Folder `nonproduction` contains `orders-dev` and `orders-staging`. The developers group is granted a role allowing project metadata reads at the Folder level.

**Question:** do group members need the same binding on both projects?

**Answer:** usually no. The Folder binding applies to child projects; if the permissions fit and nothing else blocks them, both projects receive the inherited permissions. Duplicating bindings per project makes auditing harder.

### Scenario B — Project cannot negate Organization-level Allow

The Organization grants a broad role to the operations group. Project `orders-prod` only grants Viewer to that group.

**Question:** does the Viewer role on the project cap permissions down to Viewer?

**Answer:** no. Allow at the project adds to inherited Allow. To reduce permissions, adjust the binding where it was broadly granted or apply a properly scoped restriction mechanism.

### Scenario C — Allowed but Blocked by Deny

The operations team receives Allow at a Folder for a permission. On the production project, a Deny rule targeting that group and permission is configured as supported by IAM.

**Question:** can the user perform the operation in production?

**Answer:** no, if the Deny genuinely applies and no valid exception covers them. In the dev project outside the Deny scope, the same permission may still be Allowed.

### Scenario D — User has multiple permission paths

A user belongs to both `developers` and `security-reviewers`. The `developers` binding has an expired condition, while `security-reviewers` is granted the same permission unconditionally.

**Question:** does expiration of the developers binding remove the user's access?

**Answer:** not necessarily. You must check all matching Allow bindings for the user, including roles obtained from other groups or ancestors.

## 10. Inspecting policies with Console and gcloud

### Viewing policies at each level

In Google Cloud Console, open **IAM & Admin → IAM** in the project. The UI lets you see granted permissions and their inheritance source. When investigating a principal, note the project, Folder, Organization, and scope of each role binding.

With the Google Cloud CLI, run **read-only** commands:

~~~bash
# Policy attached directly at the project (replace with real project ID).
gcloud projects get-iam-policy orders-prod --format=json

# Direct policy of a folder (replace with real FOLDER_ID).
gcloud resource-manager folders get-iam-policy FOLDER_ID --format=json

# Direct policy of an organization (replace with real ORG_ID).
gcloud organizations get-iam-policy ORG_ID --format=json
~~~

**Important:** `get-iam-policy` on a project mainly returns the **policy attached directly to that project**. It is not an automatic aggregation of every binding from Folders, Organization, and service-level policies. Not seeing a role in the project output does not let you conclude the principal has no inherited permissions.

For specific resources, run the corresponding `get-iam-policy` command if supported by the service. For example, a Cloud Storage bucket or Cloud Run service can have its own policy; inspect the target resource's policy too when permissions on that resource are the focus.

### Finding the reason with Policy Troubleshooter

**Policy Troubleshooter** takes three key inputs: principal, full resource name, and permission. It evaluates Allow/Deny policies and, where supported, Principal Access Boundary to explain why access is granted or denied.

Example checking whether a user has permission to **view a project**:

~~~bash
gcloud policy-intelligence troubleshoot-policy iam \
  "//cloudresourcemanager.googleapis.com/projects/orders-prod" \
  --principal-email="lan@example.com" \
  --permission="resourcemanager.projects.get"
~~~

If you need to analyze PAB where supported, current documentation directs using the **beta** command version:

~~~bash
gcloud beta policy-intelligence troubleshoot-policy iam \
  "//cloudresourcemanager.googleapis.com/projects/orders-prod" \
  --principal-email="lan@example.com" \
  --permission="resourcemanager.projects.get"
~~~

Replace placeholder project and email values with real ones, enable the Policy Troubleshooter API, and ensure you have permission to view the relevant policies. Check `gcloud policy-intelligence troubleshoot-policy iam --help` as options and support status can change.

Read the output in order:

1. Do the principal and resource match the failing request?
2. Is the permission truly the one the API requires?
3. Which binding from project/Folders/Organization granted Allow? Is its condition satisfied?
4. Does any Deny rule apply? Are there exception principals?
5. Is any PAB restricting scope?
6. Are there policies the person running the tool **lacks permission to view**?

**Limitations:** Troubleshooter does not fully replace checking service-specific access controls, Cloud Storage ACLs, or VPC Service Controls. Time- or request-attribute-dependent conditions require adequate context; results can also be incomplete if the investigator lacks permission to read relevant policies or custom roles. The tool supports analyzing individual principals/eligible identities; do not assume it can directly evaluate every kind of principal set or Google Group as if it were a single user.

### Reading Audit Logs when errors occur

If a live command fails with `PERMISSION_DENIED`:

- Identify the **exact caller** in Audit Logs or the error message; the caller might be a service account different from the account currently open in Console.
- Locate the permission, API, resource, and request timestamp. Do not guess solely from role names.
- Use that information to run Troubleshooter; for IAM Conditions, verify the time and resource context.
- After fixing IAM, wait for policy propagation and retry. Do not rush to grant `Owner` just to get past the error.

## 11. Designing safe IAM across multiple environments

Example: a team developing an order system has:

~~~text
Folder nonproduction
├── orders-dev
└── orders-staging

Folder production
└── orders-prod
    └── Cloud Run orders-api
~~~

Recommended model:

| Group/identity | Where to grant permissions | Purpose |
|---|---|---|
| `developers@example.com` | Dev project or nonproduction Folder, specific roles | Write and test applications |
| `qa@example.com` | Staging project and relevant test resources | Run tests and inspect results |
| `prod-observers@example.com` | Production project, appropriate observer roles | Read required status, metrics/logs |
| `deploy-orders@ci-tools.iam.gserviceaccount.com` | Production Cloud Run project/resource and permitted service account | CI/CD deployment via approved workflow |
| `platform-admins@example.com` | Infrastructure scopes requiring administration | Audited management of networking, permissions, and policies |

For real Cloud Run deployments, the CI/CD identity must have permissions covering Cloud Run actions, images, and the ability to **use the runtime service account**; a single Cloud Run role may not cover every step. The runtime identity should only have the database/bucket permissions needed at runtime, independent of the deployment identity.

Design rules:

1. **Place Allow at the smallest scope that satisfies the need.** A Folder fits when every project underneath truly needs the same role; avoid broad grants at the Organization for convenience.
2. **Use Google Groups for humans**, dedicated service accounts for workloads and CI/CD. Maintain membership offboarding procedures.
3. **Prefer minimal predefined/custom roles**, limiting broad basic roles in production.
4. **Review inherited permissions before adding new grants.** A Folder role may already cover it; duplicating on projects increases audit overhead.
5. **Assess impact when moving a project to another Folder.** Changing ancestry can alter all inherited Allow/Deny and Organization Policies.
6. **Verify by specific permissions**, not merely by comparing role names.
7. **Ensure authorized responders can inspect and remediate** if Deny/PAB or Organization-level changes lock out operational access across multiple projects.
8. **Track IAM change history** via review workflows, Infrastructure as Code where appropriate, Audit Logs, and periodic reviews.

### Why moving a project can change permissions

Suppose `orders-staging` is moved from Folder `nonproduction` to `production`. After the move, the project no longer inherits bindings belonging solely to the old branch; it receives the applicable Allow/Deny and organization policies of the new branch. Permissions change without touching IAM directly on the project.

Before moving, list principals relying on inherited permissions, CI/CD services, network/shared resources, Organization Policies, and incident responders. Moves should be reviewed as security changes.

## 12. Common misconceptions

| Statement | True or false? | Explanation |
|---|---|---|
| “Deleting a role on a project deletes permissions from the Folder.” | **False** | Folder bindings are still inherited |
| “Granting Viewer on a Project overrides Editor at the Organization.” | **False** | Allow bindings are additive |
| “Having an Allow binding guarantees the API call succeeds.” | **False** | Deny, PAB, conditions, other IAM checks, and service controls also apply |
| “Deny at Organization affects child projects.” | **True** | If the Deny applies to that permission/principal |
| “PAB grants access to resources inside its boundary.” | **False** | PAB only limits eligibility; Allow is still required |
| “Checking project `get-iam-policy` shows all effective permissions.” | **False** | Must inspect ancestor policies and service-resource policies |
| “A member of two groups can receive permissions from both.” | **True** | Matching bindings are evaluated independently |
| “IAM and Organization Policy are the same type of policy.” | **False** | IAM grants/denies permissions; Organization Policy sets configuration and usage constraints |
| “Moving a project to another Folder can alter permissions.” | **True** | Ancestry and inherited policies change |

## 13. Checklist for troubleshooting and reviewing permissions

- [ ] Identified the **principal making the request**, avoiding confusing a user with a service account.
- [ ] Identified the exact **permission** and **full resource name**.
- [ ] Inspected Allow policies at the resource, project, and all relevant ancestor levels.
- [ ] Verified group memberships and binding conditions.
- [ ] Checked Deny policies, exceptions, and supported permission scope.
- [ ] Checked PAB if used by the organization and applicable to the permission.
- [ ] Distinguished **IAM-permitted** status from API, networking, or Organization Policy failures.
- [ ] Run Policy Troubleshooter with sufficient read permissions and request context.
- [ ] Assessed impact on dev, staging, and production before editing parent-level IAM.
- [ ] Recorded and reviewed changes, verifying behavior after policy propagation.

**Applied exercise:** Organization `example.com` has Folder `engineering` with two child Folders `nonproduction` and `production`. Group `developers` receives Viewer on `engineering` and Editor on `nonproduction`. A user in `developers` is additionally granted a Cloud Run role on project `orders-prod`. Answer: (1) can the user view the staging project, and why; (2) can the user edit Compute Engine in production solely via Editor on nonproduction; (3) does removing the Cloud Run role on `orders-prod` strip all of the user's permissions on that project; (4) if a Deny applies to a Cloud Run permission in production, what happens; (5) which commands/tools would you use to verify your conclusions? For each answer, state the resource level holding the binding and the permission to check rather than only naming roles.

## Official references

- [IAM overview](https://cloud.google.com/iam/docs/overview) — principals, roles, permissions, and policies.
- [Understanding allow policies](https://cloud.google.com/iam/docs/allow-policies) — Allow inheritance and effective allow policies.
- [Deny access to resources](https://cloud.google.com/iam/docs/deny-access) — Deny policies, scope, and exceptions.
- [Principal Access Boundary policies](https://cloud.google.com/iam/docs/principal-access-boundary-policies) — restricting a principal's resource scope.
- [Policy types](https://cloud.google.com/iam/docs/policy-types) — distinguishing Allow, Deny, and other policy types.
- [Troubleshoot IAM permissions](https://cloud.google.com/policy-intelligence/docs/troubleshoot-access) — Policy Troubleshooter and evaluation limits.
- [Google Cloud IAM Conditions](https://cloud.google.com/iam/docs/conditions-overview) — conditions usable in bindings.
