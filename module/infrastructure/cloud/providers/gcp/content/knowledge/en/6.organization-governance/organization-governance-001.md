# Designing a Landing Zone with Organizations and Folders on Google Cloud

When a team starts using Google Cloud, they might create a **project**, enable APIs, and deploy an application. This starting approach works for small exercises, but when an organization operates dozens of projects for Compute Engine, GKE, Cloud Run, Cloud Storage, Cloud SQL, and BigQuery, governance challenges emerge: who can create projects, where is data allowed to be stored, how are production environments isolated from testing, where are logs centralized, and who is responsible for costs?

A **cloud landing zone** is a pre-designed foundation of organization, security, networking, operations, and governance so that new workloads can be deployed according to consistent rules. On Google Cloud, **organization** and **folder** are two key structural building blocks that establish those governance boundaries. A landing zone is an **architectural model together with a set of processes/configurations**, not a single resource with a "Create landing zone" button.

This lesson belongs to the **Organization Governance** chapter of the **CLOUD_PROVIDERS_GCP** module. Learners will design a resource hierarchy for a system involving IAM, VPC, Compute Engine, GKE, Cloud Run, storage services, and databases; connecting structural decisions with access permissions, release automation, reliability, and cost.

## 1. Learning Outcomes

After this lesson, learners can:

1. Distinguish between **organization**, **folder**, **project**, and **service resource**; understand parent–child relationships.
2. Explain how IAM allow policies and Organization Policies take effect across the resource hierarchy.
3. Choose a folder structure suited to the organization, production/nonproduction environments, and business groups.
4. Separate foundation projects such as networking, logging, and security from workload projects.
5. Design a process for provisioning new projects, attaching billing, identifying owners, applying labels, and enforcing initial controls.
6. Propose ways to validate a landing zone using operational questions and example `gcloud` commands.

## 2. Google Cloud Resource Hierarchy

### 2.1. Four Conceptual Levels

| Component | Role | Example | Notes |
| --- | --- | --- | --- |
| **Organization** | Root node for governing an organization's Google Cloud resources. | `organizations/123456789012` | Where many shared controls and administrative permissions are placed; linked to the enterprise identity environment following Google Cloud workflows. |
| **Folder** | Sub-grouping to organize projects and apply scoped policies. | `folders/456789012345` | Can be nested; folders are commonly used to separate environments, departments, or control levels. |
| **Project** | Fundamental unit for using APIs, managing resources, quotas, and linking billing. | `retail-orders-prod-001` | Project IDs must be designed carefully; many policies and permissions are applied at the project level. |
| **Service resource** | Specific resources created and managed by services. | VM, VPC network, GKE cluster, Cloud Run service, bucket, Cloud SQL instance. | Whether IAM can be granted directly and how lower-level organization works depend on the service. |

A project has only **one direct parent** in the resource hierarchy; the parent can be an organization or a folder. A folder has one parent, which is an organization or another folder, and folders reside within an organization. An organization can contain projects directly, but enterprise landing zones typically use folders to clarify governance boundaries.

~~~mermaid
flowchart TB
    O["Organization: example.com"] --> F1["Folder: platform"]
    O --> F2["Folder: workloads"]
    O --> F3["Folder: sandbox"]
    F1 --> P1["Project: shared-network-prod"]
    F1 --> P2["Project: central-logging"]
    F2 --> F21["Folder: production"]
    F2 --> F22["Folder: nonproduction"]
    F21 --> P3["Project: orders-prod"]
    F22 --> P4["Project: orders-dev"]
    P3 --> R1["Cloud Run / Cloud SQL"]
    P4 --> R2["Compute Engine / GKE"]
~~~

Folders in the diagram are **logical governance boundaries**; a folder does not create its own VPC, does not replace subnets/firewalls, and does not automatically isolate networks between projects. Similarly, a project is an important management boundary, but you still need to configure IAM, networking, organization policies, and specific resources to meet security requirements.

### 2.2. How Is an Organization Formed?

In an enterprise environment, the organization resource is typically associated with **Google Workspace or Cloud Identity** and an appropriate domain/identity setup. The onboarding team needs to coordinate with identity administrators to determine which organization owns the resource, which group administers it, how initial permissions are granted, and the plan for access recovery.

Do not treat creating a first project with a personal account as a complete landing zone design. An organization may have multiple projects created by different teams, but lacking an organization and shared governance processes makes permissions, billing, and ownership hard to control as scale grows.

### 2.3. How Do Folders and Projects Differ?

Suppose you need to separate the orders system and data analytics:

- The `production` folder represents the governance boundary for the environment, where stricter controls can be applied.
- The `orders-prod` project contains Cloud Run, Cloud SQL, and resources serving orders.
- The `analytics-prod` project contains data pipelines or analytics services, with its own IAM, quotas, and monitoring.
- Both projects can reside under the `production` folder while having different owners and budgets.

**Do not create a project just to mimic a folder**, or put multiple unrelated applications into a single project just to "avoid management overhead." Project design must account for workload lifecycle, administrative permissions, quotas, data sensitivity, and cost allocation.

## 3. Building Blocks of a Landing Zone

Organization and folders form the skeleton. An operational landing zone requires additional layers:

| Foundation Layer | Minimum Decisions | Common Technologies or Mechanisms |
| --- | --- | --- |
| **Identity & access** | Who administers the organization, who administers folders, who creates projects, who deploys applications? | Cloud Identity/Workspace, IAM groups, service accounts, federation, IAM Conditions. |
| **Governance & policy** | Which regions are allowed, which configurations are restricted, do policies differ between prod and dev? | Organization Policy Service, tags where appropriate, exception processes. |
| **Resource hierarchy** | Should folders be split by environment or business unit? Which projects belong in which scope? | Organization, folders, projects, project factory. |
| **Networking** | How do workloads communicate internally and externally? Who manages DNS, firewalls, and egress? | VPC, Shared VPC where appropriate, subnets, Cloud DNS, Cloud NAT, firewalls. |
| **Security & keys** | Who accesses data, encryption keys, and secrets? How are misconfigurations detected? | IAM, Secret Manager, Cloud KMS, Security Command Center depending on tier/availability. |
| **Observability** | Where do critical logs, metrics, and alerts go? Which team handles incident on-call? | Cloud Logging, Cloud Monitoring, log sinks, alerting, runbooks. |
| **Billing & cost** | Who is billed for each project, and how is spending controlled? | Cloud Billing account, budgets, labels, cost reports, and billing export when needed. |
| **Provisioning & delivery** | Who provisions new projects, and how are policy changes controlled? | Terraform or suitable IaC tools, CI/CD, code review, project templates. |
| **Reliability & recovery** | What levels of HA, backup, DR, and SLOs does the system require? | Multi-zone/multi-region architecture when needed, backups, recovery policies, testing. |

Not every enterprise needs to deploy all of these tools on day one. A good landing zone reflects **a level of control commensurate with risk and scale**, with a path to expand as the organization grows.

## 4. Choosing a Folder Strategy

### 4.1. Splitting by Environment

In this model, top-level folders reflect criticality levels:

~~~text
organization
├── platform
│   ├── production
│   └── nonproduction
├── workloads
│   ├── production
│   └── nonproduction
└── sandbox
~~~

**Pros:** easy to apply a strict security baseline for production, relax rules for dev/test within allowed bounds, and separate operational permissions and costs. **Cons:** projects belonging to the same business group are spread across multiple folders; naming, labels/tags, and ownership management are needed to link them.

### 4.2. Splitting by Business Unit or Product Line

~~~text
organization
├── retail
│   ├── production
│   └── nonproduction
├── data-platform
│   ├── production
│   └── nonproduction
└── corporate
~~~

**Pros:** easy to delegate permissions and accountability to departments and project teams. **Cons:** production policies may need to be maintained across multiple branches; if governance processes are weak, branches can drift in configuration.

### 4.3. Choosing a Structure Using Decision Questions

| Question | Design Guidance |
| --- | --- |
| Do production policies differ significantly from dev/test? | Consider environment folders to apply policies consistently. |
| Do business units have independent operations teams and accountability? | Consider folders by business unit, with an environment tier underneath. |
| Who is allowed to create and move projects? | Grant permissions at the appropriate folder level, controlled through an approval workflow. |
| Do projects need shared networking, logging, or security services? | Separate platform projects and define a controlled sharing model. |
| Do workloads handle sensitive data or specific location requirements? | Consider a dedicated branch and appropriate policies; verify support per service. |
| How many projects and teams does the organization have? | Avoid overly deep hierarchies that cause confusion, while also avoiding placing every project directly under the root. |

**A folder can only have one parent**, so you cannot independently group projects by both "team" and "environment" at the same level if those two dimensions intersect. Choose **one dimension as the primary tree**, use subfolders where helpful, and use labels/tags or an ownership catalog for the remaining dimensions.

### 4.4. Naming Conventions

Folder display names should follow conventions, such as:

- `platform`, `workloads`, `sandbox` for layers of responsibility;
- `production`, `nonproduction` for control levels;
- `retail`, `finance`, `data` for business units when needed;
- `security-logging`, `shared-network-prod` for infrastructure projects.

**Folder display name is not the ID**: a folder resource has a numeric identifier used in APIs/CLIs. Display names can collide in different locations; when scripting, use the folder ID rather than deriving it from the name.

Project IDs should follow a dedicated naming convention and remain stable over the long term; do not put secrets into project names, labels, or metadata fields that may be readable by many users.

## 5. Policy Inheritance: IAM and Organization Policy

### 5.1. IAM: Permissions at Ancestors Can Apply to Descendants

An IAM **allow policy** defines bindings between principals and roles. When a role is granted at the organization or folder level, permissions are inherited by eligible child resources, depending on how IAM is supported by each service and any conditions or restrictions.

Example:

~~~text
organization
└── folder: workloads
    ├── folder: production
    │   └── project: orders-prod
    └── folder: nonproduction
        └── project: orders-dev

group:prod-observers@example.com
  -> roles/monitoring.viewer on folder production

group:dev-team@example.com
  -> appropriate developer role on project orders-dev
~~~

The production observers group has permission to view monitoring data within the scope allowed by the role/binding on child projects; the development team granted permissions on `orders-dev` does not thereby gain access to `orders-prod`.

A project **cannot simply "remove" an allow binding granted at an ancestor** by deleting a local binding. If you do not want permissions to propagate downward, design the grant scope at a different level, use IAM Conditions where appropriate, or use permission boundary mechanisms supported by Google Cloud. IAM deny policies and principal access boundary policies (when applicable) must be evaluated separately from allow policies.

### 5.2. Organization Policy: Placing Constraints on Configuration

**Organization Policy Service** lets you place **constraints** on how resources are configured or used. Some constraints are boolean; others specify a set of allowed or denied values. Policies can be attached at the organization, folder, or project level depending on applicability; effective enforcement is determined by the ancestor hierarchy and the rules of the specific constraint.

Examples of common objectives:

| Governance Objective | Example Approach | What to Verify |
| --- | --- | --- |
| Reduce risk of static service account keys | Review constraints that restrict service account key creation. | Impact on legacy pipelines and mandatory exceptions. |
| Restrict resource locations | Review constraints that restrict resource locations. | Which services and resource types are affected, and multi-region deployment support. |
| Reduce risk of unintended network configurations | Review constraints related to VPCs, IP addresses, or service networking settings. | Compatibility, per-service support level, and legitimate connectivity cases. |
| Control resources by sensitivity level | Combine folder policies with IAM, processes, and tags where supported. | Do not assume attaching a custom tag automatically enforces all restrictions. |

Common constraint identifiers to research include `constraints/iam.disableServiceAccountKeyCreation` and `constraints/gcp.resourceLocations`. **Do not apply them broadly by copying examples**: each constraint has its own scope, inheritance behavior, exception handling, and product impact. Read the current documentation and test on a nonproduction branch before applying to production.

Organization Policy differs from IAM:

- **IAM** answers: does this principal have permission to perform that action on the resource?
- **Organization Policy** answers: does this resource's configuration or behavior satisfy the organization's constraints?
- **VPC firewalls**, application security rules, and data control mechanisms address other layers. Holding a valid IAM role does not automatically bypass an organization policy constraint.

### 5.3. Tags and Labels: Similar Names, Different Functions

| Tool | Used For | Limitations to Remember |
| --- | --- | --- |
| **Folder** | Ownership hierarchy and policy scope. | Each resource in the tree has a single ancestor path; difficult to represent every classification dimension. |
| **Resource Manager tags** | Governed classification; can participate in IAM Conditions or Organization Policies where supported. | Requires specific tag keys/values, bindings, permissions, and policies; a tag alone does not grant or deny access. |
| **Labels** | Metadata for identification, search, and cost allocation/reconciliation in supported services. | Not a security boundary or IAM policy. |

For example, a project under the `production` folder can still carry labels like `team=orders`, `cost_center=retail` alongside policy-governed tags. Do not use labels as a substitute for permissions or security constraints.

## 6. Designing Foundation Projects

A large landing zone typically separates **platform projects** from **application projects** to keep permissions and operations clear:

| Project / Project Group | Function | Controls to Consider |
| --- | --- | --- |
| **Network host** | Manages shared VPC/subnets and network components if Shared VPC is chosen. | Centralized network governance, firewalls, routes, DNS, egress, IAM on subnets. |
| **Security / KMS** | Houses certain centralized security components according to the architecture. | Key administration permissions, grant/revocation workflows, auditing. |
| **Logging / monitoring** | Receives or analyzes centralized observability data when needed. | Log sinks, data scope, retention, read permissions, and storage costs. |
| **Automation / CI/CD** | Project provisioning tooling and infrastructure delivery pipelines. | Deployment identities, least privilege, change approvals, drift tracking. |
| **Workload application** | Runs Cloud Run, Compute Engine, GKE, Cloud SQL, and application services. | Owner-scoped IAM, quotas, budgets, SLOs, backups, and network segmentation. |
| **Sandbox** | Time-boxed or budget-capped experimentation. | Controlled resource creation permissions, expiration/cleanup, blast-radius limits. |

This is a **reference model**, not a mandatory list of projects. For smaller organizations, some foundation components may share a project if governance, data, and lifecycle requirements are still met. Conversely, systems with strict security requirements may need further separation.

### 6.1. Shared VPC and Network Boundaries

**Shared VPC** allows a designated **host project** to provide networking to attached **service projects** under supported conditions. The goal is centralized network management while teams still own their own application projects.

~~~mermaid
flowchart LR
    N["Host project: shared-network-prod"] --> V["VPC / subnets / firewall"]
    V -. "Shared VPC attachment" .-> A["Service project: orders-prod"]
    V -. "Shared VPC attachment" .-> B["Service project: catalog-prod"]
    A --> R["Cloud Run / Cloud SQL"]
    B --> G["GKE / Compute Engine"]
~~~

**Folders do not automatically connect VPCs.** Without Shared VPC, each project can have its own VPC, but connectivity must be designed appropriately when applications communicate. Shared VPC also does not mean every resource type connects privately in the same way; Cloud Run, GKE, Cloud SQL, and VMs have different networking mechanisms and associated permissions.

### 6.2. Centralized Logging, Monitoring, and Security

An organization can create log sinks to route certain log types from organization, folder, or project scopes to supported destinations. When architecting this, document clearly:

1. Which log types need to be collected and their retention targets.
2. Log destinations, permissions for the log writer identity, and permissions for investigation teams.
3. How to detect missing logs or incorrect read permissions.
4. Costs of ingestion, storage, querying, and data export capabilities.

**Do not assume all logs are automatically routed to a central project** simply by creating a logging folder. Likewise, Cloud Monitoring requires configuring observation scopes, alerting, and SLOs for the actual system; folders only help organize permissions and resources.

### 6.3. Billing and Cost

A single Cloud Billing account can pay for multiple projects, while each project is linked to a billing account under the current billing model. **Billing accounts do not sit inside the folder tree like child projects.**

Right in the landing zone design, define:

- The owner responsible for costs on each project.
- The billing account used for projects and the approval mechanism for linking.
- Conventions for applying labels/tags or metadata for cost centers where services support them.
- Budgets/alerts, responsibility for handling alerts, and reporting over time.
- How to break down costs for shared networking, centralized logs, GKE, Cloud SQL, and shared resources.

**Budget alerts do not automatically stop spending.** If usage must be capped, you need to design appropriate quotas, policies, automation, and operational processes; do not rely solely on alerts.

## 7. Example Landing Zone Design for a Retail Enterprise

Suppose an enterprise has three teams: **Platform**, **Retail Applications**, and **Data Analytics**. The orders system runs on Cloud Run and Cloud SQL; the product team has some workloads on GKE; image data is in Cloud Storage; Compute Engine serves several internal tools. The enterprise wants to separate production, nonproduction, and sandbox environments and manage costs by team.

### 7.1. Reference Structure

~~~text
Organization: example.com
│
├── Folder: platform
│   ├── Folder: production
│   │   ├── Project: shared-network-prod
│   │   ├── Project: security-services-prod
│   │   └── Project: centralized-logging
│   └── Folder: nonproduction
│       └── Project: shared-network-dev
│
├── Folder: workloads
│   ├── Folder: production
│   │   ├── Project: orders-prod
│   │   ├── Project: catalog-prod
│   │   └── Project: analytics-prod
│   └── Folder: nonproduction
│       ├── Project: orders-dev
│       ├── Project: catalog-test
│       └── Project: analytics-dev
│
└── Folder: sandbox
    ├── Project: retail-lab-01
    └── Project: data-experiment-01
~~~

The diagram only shows **logical names**; when created on Google Cloud, each folder has a numeric folder ID and each project requires a valid, globally unique project ID. Sample names do not represent existing resources. An organization may also place product-group folders under `production` if multiple projects and owners need a separate permission-delegation layer.

### 7.2. Rules Differing by Tier

| Scope | Access Permissions | Networking and Data | Cost and Operations |
| --- | --- | --- | --- |
| **Organization** | Highly restricted org admin group; emergency access mechanism. | Baseline governance, shared policies, and exception process. | Billing rules, ownership, compliance monitoring. |
| **Platform production** | Platform team administers shared components; application teams receive only required usage permissions. | Production networking, centralized security, logging infrastructure. | Shared infrastructure costs, availability tracking for foundation services. |
| **Workloads production** | Application teams have well-scoped operational permissions; sensitive changes are controlled. | Restrict risky configurations; choose HA, backups, and private connectivity as required. | SLOs, alerts, cost center, and incident accountability. |
| **Nonproduction** | Dev/test have sufficient permissions to do their work within granted scope. | Use test data; avoid uncontrolled copying of sensitive data. | Appropriate budgets, lifecycle for temporary resources. |
| **Sandbox** | Time-boxed and clearly scoped experimentation permissions. | Limit workload types, locations, and access methods by risk. | Budgets/alerts, expiration dates, and cleanup mechanisms. |

Do not apply an overly restrictive policy at the organization level if it breaks an approved requirement across all environments. Instead, define a common baseline, assess risks, and place specialized rules on the appropriate folder, respecting each constraint's inheritance and exception behavior.

### 7.3. New Order Project Provisioning Flow

Suppose Retail Applications requests a new production project for the payments API. Proposed workflow:

1. The application team submits a request specifying the owner, purpose, data sensitivity, target region, networking requirements, SLO, RTO/RPO, and estimated cost.
2. Platform confirms the target folder: `workloads/production`, and checks whether the project should be separate from the existing orders system.
3. Provision the project via a controlled IaC template, choose a unique project ID, link billing, and attach ownership metadata.
4. Apply least-privilege IAM for the operations team and CI/CD identity; configure separate service accounts for runtime and deployment.
5. Attach to the network host/service project if needed; configure DNS, subnets, egress, and firewalls according to the actual architecture.
6. Enable required APIs, configure logs, metrics, budget alerts, backup policies, and security controls.
7. Run read-only checks: project placement in the hierarchy, effective policies, access permissions, network paths, billing, logs, and alerts.
8. Hand over the project along with runbooks, owner, cost estimate, and a schedule for permission/configuration reviews.

A project should only be considered "workload-ready" once provisioning, verification, and handover steps satisfy the organization's requirements.

## 8. Creating and Inspecting the Hierarchy with gcloud

The commands in this section illustrate how to inspect and create the hierarchy in Google Cloud CLI. **`list`, `describe`, and `get-iam-policy` commands are read operations. `create` commands and billing changes modify live resources**, so execute them only when authorized by your organization and following proper governance workflows.

### 8.1. Inspecting Existing Organizations and Folders

~~~bash
# Organizations visible to the currently active account.
gcloud organizations list

# List folders directly under an organization (replace with a real organization ID).
gcloud resource-manager folders list \
  --organization=123456789012 \
  --format="table(name,displayName,parent)"

# Describe a specific folder (folder ID is numeric, not the display name).
gcloud resource-manager folders describe 456789012345 \
  --format="yaml(name,displayName,parent)"

# List projects the account can enumerate.
gcloud projects list \
  --format="table(projectId,name,lifecycleState)"
~~~

Results depend on IAM permissions and CLI context. The fact that an account cannot see an organization, folder, or project does not prove that the resource does not exist. For organization-wide inventory, use an identity with appropriate read permissions or inventory tools deployed by the organization.

### 8.2. Inspecting Allow Policies at Each Level

~~~bash
# IAM allow policy attached directly to the organization.
gcloud organizations get-iam-policy 123456789012 \
  --format="yaml(bindings)"

# IAM allow policy attached directly to a folder.
gcloud resource-manager folders get-iam-policy 456789012345 \
  --format="yaml(bindings)"

# IAM allow policy attached directly to a project.
gcloud projects get-iam-policy retail-orders-prod-001 \
  --format="yaml(bindings)"
~~~

These three commands inspect bindings on **each individual resource**, but a result showing only direct bindings does not represent full **effective permissions**. To explain why a principal is allowed or denied, you must also check ancestors, conditions, deny policies, boundary policies if present, and additional control mechanisms.

### 8.3. Example Controlled Creation of Folders and Projects

The commands below **only illustrate the workflow**, using Bash syntax. They create resources and can incur costs once the project is linked to billing and uses services:

~~~bash
# Illustrative values: use approved real IDs.
ORG_ID="123456789012"
PARENT_FOLDER_ID="456789012345"
PROJECT_ID="retail-orders-prod-001"

# Create a folder under the organization; in practice, record the returned folder ID.
gcloud resource-manager folders create \
  --organization="$ORG_ID" \
  --display-name="workloads"

# Create the production folder under a confirmed parent folder.
gcloud resource-manager folders create \
  --folder="$PARENT_FOLDER_ID" \
  --display-name="production"

# Once you have the production folder ID and appropriate project creation permissions:
PROD_FOLDER_ID="567890123456"
gcloud projects create "$PROJECT_ID" \
  --folder="$PROD_FOLDER_ID" \
  --name="Retail Orders Production"
~~~

Do not run the entire example in an active organization without checking whether the folders already exist, to avoid creating duplicate structures. After provisioning a project, a real workflow must also manage billing, IAM, APIs, networking, logs, labels, and other controls; `gcloud projects create` **does not create a complete landing zone on its own**.

### 8.4. Post-Provisioning Verification

A read-only checklist might include:

~~~bash
# Check project details.
gcloud projects describe retail-orders-prod-001 \
  --format="yaml(projectId,name,parent,lifecycleState)"

# Check IAM bindings on the project.
gcloud projects get-iam-policy retail-orders-prod-001 \
  --format="yaml(bindings)"

# View enabled APIs (does not imply all resources are actively used).
gcloud services list --enabled \
  --project=retail-orders-prod-001

# View VPC networks created inside that project.
gcloud compute networks list \
  --project=retail-orders-prod-001
~~~

If the project uses Shared VPC, listing networks created **inside the service project itself** may not show subnets shared from the host project. Network verification must check associations, permissions, and actual connectivity paths. Similarly, verifying effective org policies requires using the appropriate Organization Policy tools/documentation rather than inferring them from IAM allow policy output.

## 9. Hard Decisions and Common Design Pitfalls

### 9.1. Is "One Project for Everything" Okay?

Sometimes reasonable for small projects or learning environments. For multi-team production, putting all workloads into one project can complicate permissions, quotas, billing, deployment lifecycles, and incident management. Separating projects by **groups of resources with a shared owner and lifecycle** is usually clearer.

### 9.2. Is "One Project per Microservice" Always Better?

Not necessarily. Too many projects increase administrative overhead, connectivity configuration, permission management, quotas, and tooling complexity. Create a project boundary when there is a real need for accountability, security, billing, lifecycle, or operational independence.

### 9.3. Is It True That "The Production Folder Already Protects the Application"?

Folders support inheritance of IAM and organization policies, but they do not automatically provide HA, application encryption, firewalls, or backups. A Cloud SQL instance without a restore plan can still suffer data loss; a single VM can still go down even if it resides under `production`.

### 9.4. Is It True That "Moving a Project to Another Folder Only Changes Its Group Name"?

No. **Moving a project between folders can change its effective policies** because its ancestor chain changes: administrative IAM, constraints, inherited tags, and other control requirements may shift. You need a before/after impact assessment, execution schedule, integration checks, accountable owners, and post-move access verification. Do not move production projects just to tidy up the display tree.

### 9.5. Is It True That "Labels Can Replace Folders and Policies"?

No. Labels are useful for search, categorization, and cost reporting in supported services. They do not create branches in the resource hierarchy and do not restrict permissions like IAM or Organization Policy. Tags can connect to certain policy mechanisms, but still require explicit policies to enforce controls.

### 9.6. Is It True That "Google Automatically Stops Resources When a Budget Threshold Is Reached"?

Do not assume that. Cloud Billing budgets are primarily for tracking and alerting. When automated actions based on cost thresholds are needed, you must design automation and verify its impact, especially to avoid disrupting critical workloads.

## 10. Testing the Landing Zone Before Going Live

### 10.1. Governance Test Cases

| Test Scenario | Expected Outcome |
| --- | --- |
| A developer with permissions only on `orders-dev` tries to modify IAM on `orders-prod`. | Denied unless another valid binding grants it. |
| The platform team reads the network host project configuration within its assigned scope. | Allowed. |
| A sandbox account tries to create a configuration restricted by an organization policy. | Blocked when the constraint applies to that request. |
| A new production project is provisioned from the template. | Appears under the right folder, with owner, billing, IAM, logs, monitoring, and appropriate policies. |
| A workload is added to a project without a budget owner. | The process detects missing information and requires remediation. |
| Reviewing logs of IAM change events. | Authorized teams can access required audit data according to logging and retention settings. |
| A project is scheduled to move to another folder. | Before/after policy assessment and verification plan are in place. |

"Denied" cases should be tested in a test environment, via policy analysis, or through non-destructive operations. You do not need to intentionally delete production data to verify controls.

### 10.2. Landing Zone Operational Metrics

Platform quality can be measured using internal metrics:

- Percentage of projects with a valid **owner and cost center**.
- Percentage of production projects provisioned through **standard IaC templates**.
- Number of open **policy exceptions** and their expiration dates.
- Percentage of projects with **billing and budget alerts** configured.
- Percentage of production workloads with **logs, alerts, and runbooks**.
- Lead time to provision a new project from valid request to handover.
- Number of findings for overly broad permissions or baseline drift.

Do not turn metrics into check-the-box exercises. A project labeled `owner=team-a` where nobody actually takes responsibility is still an ungoverned project.

### 10.3. Practice Exercise

**Scenario:** A company has two teams, `retail` and `analytics`, each needing `dev` and `prod`. The platform team owns shared networking and the logging system; application teams deploy Cloud Run, GKE, Compute Engine, and Cloud SQL in their own projects.

Design a resource hierarchy that satisfies:

1. Production has stricter policies than nonproduction.
2. The platform team manages the network host, while application teams have permissions to use the required subnets.
3. The analytics team cannot modify the retail team's resources by default.
4. Each project has an owner and cost allocation metadata.
5. Security logs must be collected centrally with restricted read access.

**A reference approach:** create `platform/production`, `platform/nonproduction`, `workloads/production`, and `workloads/nonproduction`; split application projects by business group; grant IAM via groups/roles and scopes; use Shared VPC if selected; configure dedicated log sinks; place baseline policies on appropriate ancestors; attach owner/cost center metadata. If separate folder-level IAM permissions are needed per team, add `retail` and `analytics` folders under each environment rather than granting all roles on the shared production folder.

Explain **why** you chose that folder level for IAM and policies, who is responsible for creating projects, and how to verify that a new project inherits the expected configuration.

## 11. Adoption Checklist and Official Documentation

Before putting the landing zone into operation, verify:

| Item | Acceptance Criteria |
| --- | --- |
| **Organization** | Owning organization, administrators, and emergency access procedures are defined. |
| **Folder tree** | Structure reflects policy and accountability boundaries; naming/ID conventions are in place. |
| **Project lifecycle** | Provisioning templates, owner assignment, folder move process, project closure, and cleanup exist. |
| **IAM** | Appropriate groups/service accounts are used; least-privilege roles; permission inheritance is evaluated. |
| **Organization Policy** | Baseline, production policies, and a verified exception process are established. |
| **Networking** | Network project, VPC/subnets, connectivity, firewalls, DNS, egress, and operational ownership are decided. |
| **Security** | Secrets/keys protection, auditing, configuration reviews, and sensitive data read access are in place. |
| **Observability** | Logs and metrics are configured; alerts, SLOs, on-call ownership, and retention are appropriate. |
| **Billing** | Projects are linked to the right billing account; owners, reporting, and budget alerts exist. |
| **Automation** | Foundation resources are managed via reviewed IaC/workflows; drift is monitored. |
| **Validation** | Allowed/denied access, policy enforcement, networking, and recovery scenarios are tested. |

Consult official documentation to verify syntax, features, and per-product applicability:

- [Google Cloud resource hierarchy](https://cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy)
- [Creating and managing folders](https://cloud.google.com/resource-manager/docs/creating-managing-folders)
- [Google Cloud setup / enterprise foundation](https://cloud.google.com/docs/enterprise/foundations)
- [Organization Policy Service](https://cloud.google.com/resource-manager/docs/organization-policy/overview)
- [IAM overview](https://cloud.google.com/iam/docs/overview)
- [Shared VPC overview](https://cloud.google.com/vpc/docs/shared-vpc)
- [Cloud Billing documentation](https://cloud.google.com/billing/docs)
- [Cloud Logging routing and storage](https://cloud.google.com/logging/docs/routing/overview)
- [Google Cloud CLI reference](https://cloud.google.com/sdk/gcloud/reference)

Key takeaway: the **organization** defines the top-level governance scope, **folders** group resources by accountability and policy boundaries, and **projects** are the unit for deploying and managing many Google Cloud services. A landing zone is only effective when the resource hierarchy is combined with IAM, Organization Policy, networking, security, billing, observability, and verifiable provisioning processes.
