# Basic roles, predefined roles, and custom roles in Google Cloud IAM

In Google Cloud, one person may be able to view Compute Engine VMs without deleting them; a Cloud Run application may be able to read objects in Cloud Storage without altering VPC settings; a deployment pipeline may update a service without managing permissions across the entire project. These distinctions are designed with **Identity and Access Management (IAM)**: defining **who** is allowed to perform **which action** on **which resource**, under **which conditions**.

This lesson belongs to the **IAM and authentication** chapter of the **CLOUD_PROVIDERS_GCP** module. Along the learning path from organizing projects, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage, and databases, choosing the right role type is foundational for protecting resources, automating releases, operating reliably, and controlling costs. This lesson focuses on comparing the three role categories—**basic roles**, **predefined roles**, and **custom roles**—understanding how they work, knowing when to use each, and practicing permission inspection with `gcloud`.

## 1. Fundamentals: principal, permission, role, and policy binding

### 1.1. Authentication differs from authorization

- **Authentication:** verifies the identity of a user, application, or workload. For example, a developer signs in with a corporate account; an application runs using a service account.
- **Authorization:** decides whether an authenticated identity is allowed to call an API or act on a specific resource.

In Google Cloud's IAM model, the core concepts include:

| Concept | Meaning | Example |
| --- | --- | --- |
| **Principal** | Identity requesting permissions: user, group, service account, or federated identity. | `user:lan@example.com`, `group:platform@example.com`, `serviceAccount:orders-runtime@my-prod-project.iam.gserviceaccount.com`. |
| **Permission** | A specific operational right, usually in the form `service.resource.action`. | `compute.instances.get`, `compute.instances.list`. |
| **Role** | A named collection of permissions. | `roles/compute.viewer`. |
| **Allow policy / role binding** | Attaches a role to a principal on a resource or resource scope; a binding may include an IAM Condition. | The operations group is assigned `roles/compute.viewer` on the project. |
| **Resource** | The object to protect; can sit under an organization, folder, project, or be a service resource. | Project, Cloud Storage bucket, service account, Cloud Run service. |

There is no concept of “role = user”. A **role is a set of permissions**, whereas a principal is the subject receiving permissions. Creating a role does not by itself grant access to anyone; there must be an appropriate binding in the allow policy of the resource or one of its ancestors.

### 1.2. Effective permissions across the resource hierarchy

Google Cloud uses a resource hierarchy. A binding granted on an ancestor can affect corresponding child resources, depending on service support and policies:

~~~mermaid
flowchart TB
    O["Organization"] --> F["Folder: Engineering"]
    F --> P["Project: my-prod-project"]
    P --> VM["Compute Engine VM"]
    P --> RUN["Cloud Run service"]
    P --> BUCKET["Cloud Storage bucket"]
    P --> SQL["Cloud SQL instance"]
    ROLE["Role binding on Project"] -. "Permissions can inherit downward" .-> VM
    ROLE -.-> RUN
    ROLE -.-> BUCKET
    ROLE -.-> SQL
~~~

For example, if a group is granted a Compute Engine read role at the project level, the group can generally view the relevant Compute Engine resources in that project. If it only needs to view a single bucket, consider placing the binding on the **bucket** when supported by the role and service, avoiding granting the corresponding permissions across the entire project.

Whether an operation is permitted also depends on **IAM Conditions**, ancestor policies, IAM deny policies, principal access boundary policies (when applied), organization constraints, and other controls. The diagram only illustrates the inheritance mechanism of an **allow policy**, not every condition that determines effective permissions.

### 1.3. A principal can hold multiple roles

A person or service account can receive multiple roles from different bindings. When a role permits the required operation, that operation may be allowed by the allow policy; however, applicable restrictive or deny policies can make the final outcome not permitted.

Example:

~~~text
Principal: group:dev-team@example.com

Project my-dev-project:
  roles/compute.viewer
  roles/logging.viewer

Cloud Storage bucket dev-artifacts:
  roles/storage.objectViewer
~~~

The group can view VM metadata, view logs within the granted scope, and read objects in the relevant bucket. The group is **not automatically** allowed to modify VMs, read every bucket in the organization, or view secret data across all services.

## 2. Basic roles: Viewer, Editor, and Owner

### 2.1. What are basic roles?

**Basic roles** (also called *primitive roles* in many older docs) are three very broad roles dating back to the earliest versions of Google Cloud IAM:

| Role | Identifier | Main capabilities | Risks when used broadly |
| --- | --- | --- | --- |
| **Viewer** | `roles/viewer` | View information for many types of resources. | Can access more metadata than the job requires; does not guarantee permission to read all data contents. |
| **Editor** | `roles/editor` | View and modify many types of resources. | Large blast radius for modifications, potentially causing operational incidents or costs; not equivalent to full IAM control. |
| **Owner** | `roles/owner` | Very broad administrative permissions on a project, including the ability to manage many permission configurations. | If misassigned or compromised, the impact can spread across most of the project. |

Basic roles **do not mean every permission of every service**. Google Cloud has permissions that are not included in basic roles, and services may have their own rules regarding data, permissions, or resource scope. In particular, never assume `roles/viewer` grants access to read all customer data or that `roles/editor` allows modifying all IAM policies.

For example, in an e-commerce project, assigning `roles/editor` to someone who only needs to observe VM configuration may let them modify many unrelated resources. If the task is solely viewing Compute Engine, `roles/compute.viewer` is usually more appropriate.

### 2.2. Why avoid basic roles in production?

Basic roles have the advantage of simplicity, but once a project holds VPCs, GKE, Cloud Run, Cloud SQL, Cloud Storage, and other administrative resources, a broad role creates problems:

1. **Hard to enforce least privilege:** a small task can inherit a large set of unnecessary permissions.
2. **Hard to determine blast radius:** as new resources or services are added, the permissions available through a broad role can shift under IAM mechanics.
3. **Easy to confuse viewing metadata with accessing data:** viewing bucket configuration and reading objects inside the bucket are different operations.
4. **Increased risk from compromised identities:** especially when broad permissions are granted to service accounts used in automated systems.
5. **Hard to audit:** the business justification for a role like `Editor` is far less specific than a function-based role.

For production systems, start with appropriately scoped **predefined roles**. Only consider basic roles in genuinely necessary, approved scenarios, such as certain controlled project administration tasks. Never default to granting `Editor` to developers or service accounts simply because it is the fastest way to clear a `PERMISSION_DENIED` error.

### 2.3. Right and wrong illustration

**Requirement:** an operations team member needs to check VM status to correlate alerts.

~~~text
Inappropriate:
  principal = user:operator@example.com
  role      = roles/editor
  scope     = production project

More appropriate:
  principal = group:vm-observers@example.com
  role      = roles/compute.viewer
  scope     = project containing the VMs to observe
~~~

If the operator also needs to view metrics or logs, you can add dedicated Cloud Monitoring or Cloud Logging roles at the right scope after confirming the required permissions. Do not expand to `Editor` just to cover an extra observability need.

## 3. Predefined roles: built-in roles by function

### 3.1. Characteristics

**Predefined roles** are created and maintained by Google around products, resources, or functional groups. They typically have identifiers of the form:

~~~text
roles/<service>.<roleName>
~~~

Examples:

| Need | Predefined role to consider | Notes |
| --- | --- | --- |
| View Compute Engine VMs | `roles/compute.viewer` | Suitable when only reading Compute Engine metadata within the granted scope. |
| Administer VMs | `roles/compute.instanceAdmin.v1` | Can modify many VM resources; verify exact permissions before granting. |
| Use a service account to run a workload | `roles/iam.serviceAccountUser` | Includes `iam.serviceAccounts.actAs` within the granted scope; avoid granting across the whole project if only one service account is needed. |
| Invoke an IAM-authenticated Cloud Run service | `roles/run.invoker` | Usually granted on the target Cloud Run service; deployment conditions and access configuration still need review. |
| Read Cloud Storage objects | `roles/storage.objectViewer` | Consider granting on the specific bucket when access to that bucket's data is needed. |
| Manage Cloud Storage objects | `roles/storage.objectAdmin` | Broad permissions on objects in the granted scope; does not mean administering all bucket settings. |
| Connect to Cloud SQL via a mechanism requiring IAM | `roles/cloudsql.client` | Part of the connection requirements; **does not replace** database authentication and database privileges. |
| View GKE cluster metadata | `roles/container.clusterViewer` | Pertains to cluster info; operating against the Kubernetes API may still require Kubernetes RBAC. |
| View logs | `roles/logging.viewer` | Certain sensitive logs have additional access controls. |
| View metrics and monitoring configuration | `roles/monitoring.viewer` | Suitable for observation duties, without granting rights to edit alerts/dashboards. |

The list above is an **initial set of candidates**, not a complete permission blueprint for every workload. For instance, a pipeline deploying Compute Engine may need both VM management and permission to *act as* the service account attached to the machine; VM admin rights do not automatically grant every permission related to machine identity. Google adds or updates roles over time, so read each role's latest permission list before deciding.

### 3.2. Service-level roles and data boundaries

Predefined roles embody a separation of duties:

- **Configuration viewer** differs from **configuration editor**.
- **Service invoker** differs from **new-revision deployer**.
- **Bucket administrator** differs from **object-only reader**.
- **Cloud SQL metadata viewer** differs from **database connecting identity** and **SQL table privilege holder**.
- **GKE resource manager via Google Cloud API** differs from **user allowed to create/edit Pods in the Kubernetes API**; for GKE, evaluate both Cloud IAM and Kubernetes RBAC according to the authentication and authorization mechanisms in use.

This is a vital principle when an application spans multiple products. Selecting roles by exact function lets the system run properly while reducing the risk of data exposure or accidental resource modification.

### 3.3. Inspecting permissions inside a role

Use the Google Cloud CLI to inspect predefined roles:

~~~bash
# View permission details in the Compute Engine viewer role.
gcloud iam roles describe roles/compute.viewer \
  --format="yaml(name,title,description,includedPermissions,stage)"

# View the role that allows invoking Cloud Run.
gcloud iam roles describe roles/run.invoker \
  --format="yaml(name,title,description,includedPermissions,stage)"
~~~

Key fields:

| Field | Meaning |
| --- | --- |
| `name` | Full identifier of the role. |
| `title` | Human-readable display name. |
| `description` | Purpose of the role. |
| `includedPermissions` | List of permissions included in the role at the time of inspection. |
| `stage` | Lifecycle stage of the role, such as GA or another stage if applicable. |

Do not rely solely on a role's name to guess its permissions. A role containing “admin” does not necessarily allow administering every service in a project, and a role containing “viewer” can still expose sensitive metadata if granted too broadly.

## 4. Custom roles: tailoring permission sets to requirements

### 4.1. When is a custom role needed?

**Custom roles** are roles defined by an organization or administrative team by selecting supported permissions. They address cases where existing predefined roles all contain more permissions than the job genuinely requires.

For example, a VM inventory team only needs:

~~~text
compute.instances.get
compute.instances.list
~~~

These permissions allow reading instance details subject to IAM conditions. If no predefined role matches the desired scope, an admin team can build a “VM Inventory Reader” custom role and assign it to principals at the appropriate scope.

Custom roles **do not invent new permissions**. They only group permissions that are eligible for custom roles, according to Google Cloud's supported list. Not every permission is supported; some have limitations or depend on the resource level.

### 4.2. Organization level and project level

Custom roles can be created at the **organization** or **project** level:

| Definition level | Illustrative identifier | Appropriate when |
| --- | --- | --- |
| Organization | `organizations/123456789012/roles/vmInventoryReader` | You want to share the same role definition across multiple projects in the organization, within supported binding scopes. |
| Project | `projects/my-prod-project/roles/vmInventoryReader` | The role is tied to the needs of one specific project. |

**The level where a role is defined is not the scope of permissions automatically granted.** An organization-level role does not mean a principal immediately gains permission to view every project. Permission scope depends on **where the binding is placed** and applicable policies. Conversely, creating a role without any binding grants permissions to no principal at all.

### 4.3. Steps to design a custom role

1. **Write a task description:** what must the grantee do, and on which resource types?
2. **Identify minimal permissions:** consult permission docs and test in a controlled environment; avoid guessing purely from API names.
3. **Verify custom role support:** not all permissions can be included in custom roles.
4. **Choose definition location:** project if the need is local to it; organization if the definition must be centrally managed and reused across multiple projects.
5. **Set naming and ownership:** stable role ID, clear title, and description stating the business scope.
6. **Create the role and bind at the smallest appropriate scope**, then test operations that must succeed and operations that must be denied.
7. **Review periodically:** check for no-longer-needed permissions, compatibility, and changes from Google Cloud services.

If a predefined role already meets the task with an acceptable scope, using it usually avoids custom role management overhead. Custom roles carry extra responsibility for maintenance, testing, and handling permission updates over the application lifecycle.

### 4.4. Example: creating a read-only VM inventory role

The following commands **illustrate IAM modifications**; only run them in an authorized test project after an administrator confirms the required permissions. Environment variables and email addresses are sample values that must be adapted to your organization.

~~~bash
# Bash: replace the project ID with an actually managed project.
PROJECT_ID="my-prod-project"

# Create a custom role at the project level.
gcloud iam roles create vmInventoryReader \
  --project="$PROJECT_ID" \
  --title="VM Inventory Reader" \
  --description="Read VM instance metadata for approved inventory work" \
  --permissions="compute.instances.get,compute.instances.list" \
  --stage=GA

# Inspect the newly created role definition.
gcloud iam roles describe vmInventoryReader \
  --project="$PROJECT_ID" \
  --format="yaml(name,title,description,includedPermissions,stage)"
~~~

The `compute.instances.get` and `compute.instances.list` example only covers basic VM info reading. If the inventory tool calls other APIs, displays additional attributes, or needs to read project metadata, appropriate permissions may need to be added. Verify real results rather than immediately granting resource-modification permissions.

Once scope and user group are confirmed, a project-level binding can be added as follows:

~~~bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="group:vm-auditors@example.com" \
  --role="projects/$PROJECT_ID/roles/vmInventoryReader"
~~~

This command **modifies the live IAM policy** when executed with sufficient permissions. Using a group instead of scattered individual bindings centralizes membership management. A project binding can grant read access to eligible instances in that project; if only a narrower resource is needed, check whether the resource type and role support bindings at a finer scope.

### 4.5. Updating and deprecating custom roles

Over a custom role's lifecycle, administrators can update its title, description, or permissions and manage role states as supported by Google Cloud. Adding a permission to a custom role **can expand access for every principal currently bound to that role** as soon as the policy takes effect. Therefore:

- List existing bindings using the role before modifying it.
- Analyze the impact of adding or removing permissions, including CI/CD systems and scheduled jobs.
- Test in a narrowly scoped environment and prepare a rollback or replacement plan if needed.
- Check dependencies before disabling or deleting a role; deletion does not replace revoking bindings and verifying effective permissions.

A custom role that fit well initially can still become too broad or too narrow as APIs and business needs evolve.

## 5. Comparing the three role categories

| Criterion | Basic roles | Predefined roles | Custom roles |
| --- | --- | --- | --- |
| Who defines them? | Google Cloud. | Google Cloud. | Organization or authorized administrators. |
| Examples | `roles/viewer`, `roles/editor`, `roles/owner`. | `roles/compute.viewer`, `roles/run.invoker`. | `projects/PROJECT_ID/roles/vmInventoryReader`. |
| Granularity | Low, very broad scope. | By product/function. | Administrator selects supported permissions. |
| Management effort | Low to define, but high risk of over-privileging. | Low; Google maintains permissions. | Higher; requires tracking, testing, and updates. |
| Least-privilege fit | Generally poor. | Usually the first choice. | Useful when predefined roles remain too broad. |
| Permission changes | Managed by Google. | Managed by Google. | Managed by admins within supported limits. |
| Typical usage | Certain special admin scenarios under tight scope. | Users, ops teams, applications, and pipelines by function. | Specialized tasks requiring a smaller permission set. |

Role selection logic can be expressed as a flowchart:

~~~mermaid
flowchart TD
    A["List actions and resources truly required"] --> B{"Is there a suitable predefined role?"}
    B -- "Yes" --> C["Choose the dedicated role"]
    B -- "No or too broad" --> D{"Do permissions support custom roles?"}
    D -- "Yes" --> E["Design a custom role"]
    D -- "No" --> F["Adjust workflow or split duties; evaluate alternatives"]
    C --> G["Bind at the smallest suitable scope"]
    E --> G
    F --> G
    G --> H["Test and review periodically"]
~~~

The diagram is a design guide, not a rigid rule. Before creating a new role, also evaluate whether a task can be split into two identities or two operational steps to avoid bundling sensitive permissions together.

## 6. Deployment scenario: assigning permissions for an e-commerce system

A team deploys a backend on **Cloud Run**, stores transactions in **Cloud SQL**, uses **Cloud Storage** for product images, and maintains some Compute Engine VMs and a **GKE** cluster for other workloads. They want to protect resources during automated releases while retaining sufficient observability during incidents.

### 6.1. Mapping principals by responsibility

| Principal / task | Role to consider | Recommended scope | Further verification needed |
| --- | --- | --- | --- |
| VM viewer group | `roles/compute.viewer` | Project containing the VMs to observe. | Whether logs/metrics viewing permissions are also required. |
| On-call operations staff | `roles/logging.viewer`, `roles/monitoring.viewer` | Projects tied to on-call services. | Sensitive logs, alerting permissions, and incident access workflow. |
| Cloud Run deployment pipeline | Appropriate deploy role such as `roles/run.developer`; add `roles/iam.serviceAccountUser` on the runtime service account when *act as* is needed. | Target project and relevant service account. | Permissions for registry/artifacts, networking, and pipeline steps. |
| Cloud Run runtime service account | `roles/cloudsql.client` if using a connection method requiring it; appropriate object reader role when Cloud Storage is needed. | Project/instance or bucket as supported by the service. | Database authentication and SQL privileges; object boundaries and sensitive data. |
| Component calling authenticated Cloud Run API | `roles/run.invoker` | Target Cloud Run service. | Token authentication mechanism and service-to-service calling setup. |
| Specialized VM inventory team | Custom role containing only required read permissions. | Project or supported resource. | Additional metadata APIs used by the inventory tool. |
| IAM administration | Dedicated IAM admin roles, separated by duty. | Assigned resources or portion of the organization. | Approval process, MFA, audit logging, and privilege escalation paths. |

This is an **initial sketch**. Exact roles must derive from real APIs, resources, actions, and responsibilities. For example, the service account running Cloud Run should not hold permissions to deploy new revisions just because the pipeline uses a similar role. Separating the **deployment identity** from the **runtime identity** limits damage if the application is exploited.

### 6.2. Difference between deployment permissions and runtime permissions

Suppose a pipeline needs to deploy a new Cloud Run revision. There are two identities:

~~~text
CI/CD deployer
  |-- Cloud Run deploy permissions on the appropriate project/service
  |-- actAs permission on the runtime service account when required
  '-- appropriate artifact/image read permissions to perform the release

Cloud Run runtime service account
  |-- Cloud SQL connection permissions matching the connection method
  '-- object read permissions in the application bucket
~~~

The pipeline being allowed to deploy **does not mean** the runtime service account must also be allowed to deploy. And `roles/iam.serviceAccountUser` (ability to use an identity to attach to a workload for supported actions) **is not the same as** `roles/iam.serviceAccountTokenCreator` (permissions to create credentials/tokens within the granted scope). Service account permissions must be evaluated carefully because they can open paths to all permissions held by that service account.

### 6.3. Verifying the principle of least privilege

For each principal, build a test matrix:

| Test case | Expected result |
| --- | --- |
| Observer group calls API to list Compute Engine instances. | Allowed. |
| Observer group tries to delete a VM. | Denied. |
| Cloud Run runtime reads objects in the application bucket. | Allowed if resource and conditions match. |
| Cloud Run runtime reads objects in a different finance bucket. | Denied. |
| Pipeline deploys a revision of the assigned service. | Allowed. |
| Pipeline modifies IAM policy across the entire organization. | Denied. |

Negative test cases can be checked using policy analysis tools, sandbox environments, or non-destructive methods. Never attempt to delete a production resource solely to prove a user lacks permission.

## 7. Inspecting and managing roles with gcloud

### 7.1. Viewing roles in a project's IAM policy

~~~bash
PROJECT_ID="my-prod-project"

# Read the project's IAM allow policy.
gcloud projects get-iam-policy "$PROJECT_ID" \
  --format="yaml(bindings)"
~~~

An illustrative binding output might look like:

~~~yaml
bindings:
- members:
  - group:vm-observers@example.com
  role: roles/compute.viewer
- members:
  - serviceAccount:orders-runtime@my-prod-project.iam.gserviceaccount.com
  role: roles/cloudsql.client
~~~

This output only shows **direct bindings on the project** queried; it does not fully reflect roles inherited from folders/organization or policies set on child resources. If principals use IAM Conditions, bindings also carry conditions; when investigating effective permissions, inspect all related policies.

The `get-iam-policy` command also requires the corresponding IAM policy read permission. Someone with permission to view VMs does not necessarily have permission to view all IAM bindings on the project.

### 7.2. Inspecting predefined and custom roles

~~~bash
# Read the definition of a predefined role.
gcloud iam roles describe roles/storage.objectViewer \
  --format="yaml(name,title,includedPermissions,stage)"

# List custom roles defined in the project.
gcloud iam roles list --project="$PROJECT_ID"

# View details of a project-level custom role.
gcloud iam roles describe vmInventoryReader \
  --project="$PROJECT_ID" \
  --format="yaml(name,title,description,includedPermissions,stage)"
~~~

If the role does not exist or the account lacks permission to read metadata, the command may return an error. Do not assume a custom role was deleted merely from querying against the wrong project or organization.

### 7.3. Example of binding and revoking access

Only run these commands with IAM admin authorization and after substituting the exact resource, group, and role:

~~~bash
# Grant Compute Engine viewer access to a group on the project.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="group:vm-observers@example.com" \
  --role="roles/compute.viewer"

# Revoke that exact binding when no longer needed.
gcloud projects remove-iam-policy-binding "$PROJECT_ID" \
  --member="group:vm-observers@example.com" \
  --role="roles/compute.viewer"
~~~

These commands update the project's **allow policy**; before modifying conditional or complex policies, check syntax and existing bindings to act on the exact target. Removing one binding does not prove a principal has lost all access, because other bindings may remain on ancestors or directly on the resource.

### 7.4. Investigating `PERMISSION_DENIED`

When the CLI or a workload reports a permission error, check in order:

1. **Which principal actually called the API?** User account, runtime service account, pipeline, or federated identity?
2. **Which permission does the operation require?** Based on the API, service docs, and error details; one operation may require multiple permissions.
3. **Which resource is being checked?** Project, service account, bucket, Cloud Run service, or child resource.
4. **Is the binding at the right scope?** A project role may not cover operations on resources outside the project or outside its control boundary.
5. **Are there conditions or restrictive policies?** IAM Conditions, deny policies, principal access boundaries, organization policies, VPC Service Controls, or other authorization mechanisms can affect the outcome.
6. **Does the role contain enough permissions?** Read `includedPermissions`, and use Policy Troubleshooter / Policy Analyzer if applicable and you have access.
7. **Are target-system permissions outside Cloud IAM needed?** For instance, Cloud SQL database privileges or GKE Kubernetes RBAC.

Do not resolve `PERMISSION_DENIED` by granting `roles/owner` or `roles/editor` before identifying the root cause. That masks the missing permission, widens privilege scope, and complicates future audits.

## 8. Principles for designing safe, maintainable roles

### 8.1. Seven practical rules

1. **Tie permissions to tasks:** list the APIs and resources actually needed instead of asking “what role should the whole engineering team get?”.
2. **Prefer suitable predefined roles:** evaluate custom roles next if predefined ones are still too broad; restrict basic roles in production systems.
3. **Narrow the binding scope:** if only one bucket, service, or service account is needed, consider binding directly on that resource when supported.
4. **Prefer groups for humans:** avoid hard-to-track per-user grants. For workloads, use service accounts and appropriate authentication, minimizing long-lived keys.
5. **Separate sensitive duties:** release deployers, IAM change approvers, and runtime applications may require distinct principals.
6. **Record and audit changes:** use Cloud Audit Logs according to configuration and scope; review IAM Recommender suggestions and verify before adjusting permissions.
7. **Review periodically:** permissions once needed for a test environment or short-term campaign may no longer be appropriate after stable rollout.

IAM Conditions can help restrict certain bindings using supported attributes (such as time or resource attributes), but they **do not replace** choosing the right role and scope. Not every resource or permission supports the same set of condition attributes.

### 8.2. How roles relate to reliability and cost

IAM directly affects operational behavior:

- Too few permissions for CI/CD can break releases at critical moments; test the release process using the exact real identity.
- Too broad permissions for a runtime service account can let an application compromise spill over into other data or services.
- Broad admin roles can enable creating costly resources or altering networking in ways that disrupt applications; pair them with governance, budget alerts, and change control.
- Properly scoping log, metric, and config read roles enables on-call engineers to investigate incidents without holding write privileges on unrelated products.

Still, **IAM is not the only solution** for security, cost, or reliability. VPC/firewall rules, secret management, organization policies, monitoring, backups, and operational procedures must be designed together.

## 9. Practice exercises and check questions

### Exercise 1 — Choosing a role for VM viewers

A team may only view VM status in project `my-prod-project` and must not create, edit, or delete VMs. Which role should you start with?

**Hint:** check `roles/compute.viewer`; read `includedPermissions` to confirm the required operations. `roles/editor` has far too broad a scope.

### Exercise 2 — Choosing a role for an image-reading service

A Cloud Run application only needs to read images in bucket `product-images`. Which role should be granted, and where?

**Hint:** consider `roles/storage.objectViewer` on bucket `product-images` for the runtime service account, when bucket IAM configuration supports it and data access is genuinely required. Do not grant across the whole project by default.

### Exercise 3 — Predefined role is not narrow enough

An inventory tool only calls APIs to list VMs and read details of a single VM. Propose a project-level custom role.

~~~text
Role ID: vmInventoryReader
Permissions:
  compute.instances.list
  compute.instances.get
~~~

After designing it, verify supported permissions and any additional APIs the tool actually calls. Distinguish **creating the role definition** from **binding the role to a group**.

### Exercise 4 — Diagnosing an authorization error

A pipeline has permission to update Cloud Run but fails when selecting the runtime service account. What should you check?

**Hint:** check the pipeline's identity, `iam.serviceAccounts.actAs` permission on the exact service account, and binding scope; inspect actual deployment setup along with IAM conditions. Do not default to upgrading to `Owner`.

### Exercise 5 — Comparing effective permissions

A person holds `roles/compute.viewer` on a project through a group and also has a metadata-reading custom role on the same project. Why can't you determine their exact complete permissions solely from the names of those two roles?

**Hint:** you must check `includedPermissions`, ancestor/resource bindings, IAM Conditions, deny policies, and other governance mechanisms. Assigned roles can also change contents over time.

## 10. Summary and reference links

The three role types serve different needs:

- **Basic roles** are very broad permission sets (`Viewer`, `Editor`, `Owner`); limit usage because they make least privilege hard to enforce.
- **Predefined roles** are maintained by Google by service and job function; usually the first choice when granting permissions.
- **Custom roles** let organizations choose supported permissions themselves; suitable when predefined roles remain broader than required, at the cost of managing the role lifecycle.

What matters most is **matching principal, action, resource, and binding scope**. Good design gives users the access they need to work, service accounts the access needed to execute, release teams safe automation, and operations teams system visibility without holding unrelated privileges.

Official documentation to verify when deploying on real projects:

- [Understanding roles — Google Cloud IAM](https://cloud.google.com/iam/docs/understanding-roles)
- [Create and manage custom roles](https://cloud.google.com/iam/docs/creating-custom-roles)
- [Grant, change, and revoke access](https://cloud.google.com/iam/docs/granting-changing-revoking-access)
- [IAM permissions reference](https://cloud.google.com/iam/docs/permissions-reference)
- [Google Cloud CLI: iam roles](https://cloud.google.com/sdk/gcloud/reference/iam/roles)
- [Troubleshoot access — IAM](https://cloud.google.com/iam/docs/troubleshoot-access)

When in doubt about permissions or grant requirements, check the role definitions and actual policies against the service's latest documentation. Permission lists, binding support at each resource level, and IAM features can change over time.
