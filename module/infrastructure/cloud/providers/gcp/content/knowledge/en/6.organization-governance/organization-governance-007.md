# Policy Analyzer and Permission Reviews on Google Cloud Resources

When an enterprise operates many Google Cloud projects, the security question is not merely "who was granted what role in this project?" Administrators also need to know **who can access a specific resource**, whether permissions are granted directly or **inherited from the organization/folder**, and which permissions may be overly broad. These questions matter for Compute Engine VMs, GKE, Cloud Run, Cloud Storage, BigQuery, Cloud SQL, service accounts, and administrative APIs.

Google Cloud's **Policy Analyzer for allow policies** analyzes IAM allow bindings by identity, permission, and resource. This lesson belongs to the **Organization Governance** chapter of the `CLOUD_PROVIDERS_GCP` module: beyond selecting services, learners must govern IAM/VPCs, protect workloads, automate deployments, monitor reliability, and identify operational and cost risks. The focus here is **evidence-based permission reviews on resources**, understanding the limits of analysis results, and turning findings into safe governance actions.

## Learning Objectives

After this lesson, you will be able to:

1. Explain what questions Policy Analyzer answers and what its input data is.
2. Distinguish **principal, role, permission, resource**, and **query scope**.
3. Run queries to see who holds permissions on a resource, what permissions a principal holds, or which resources a principal can access according to IAM allow policies.
4. Understand the role of **IAM inheritance**, user groups, IAM conditions, and service account impersonation.
5. Use Google Cloud Console and `gcloud asset analyze-iam-policy` for read-only reviews.
6. Explain why Policy Analyzer results are **not a final effective-access check**.
7. Combine Policy Analyzer, Policy Troubleshooter, IAM Recommender, and Cloud Asset Inventory in a periodic permission review workflow.

## 1. The Problem: Who Actually Has Permissions on a Resource?

Suppose Atlas Corp has the following resource hierarchy:

~~~mermaid
flowchart TD
    O["Organization: Atlas"]
    F1["Folder: Production"]
    F2["Folder: Nonproduction"]
    P1["Project: commerce-prod"]
    P2["Project: commerce-dev"]
    B["Cloud Storage bucket: order-exports"]
    SA["Service account: orders-api"]
    O --> F1
    O --> F2
    F1 --> P1
    F2 --> P2
    P1 --> B
    P1 --> SA
~~~

The Security team asks: **"Who has permission to read data in the `order-exports` bucket?"** Looking solely at the IAM policy attached directly to the bucket can miss permissions granted at the project, folder, or organization level.

For example, three permission sources can exist simultaneously:

- At the **organization** level, group `security-auditors@example.com` holds an appropriate read-only role across the organization.
- At the **Production folder**, group `prod-operators@example.com` holds a role with required administrative permissions.
- At the **bucket**, service account `orders-api@commerce-prod.iam.gserviceaccount.com` is granted `roles/storage.objectViewer`.

Every IAM allow binding associates a **role** with one or more **principals** at a resource scope. When inherited, permissions at higher levels can apply to child resources. If a principal belongs to a Google Group that was granted a role, the principal's access can also come from **group membership**, without their individual email appearing in the binding.

Running `gcloud storage buckets get-iam-policy` or `gcloud projects get-iam-policy` once only shows the direct policy of the queried resource. Therefore, a thorough permission review must analyze **ancestor grants** and pinpoint the **specific permissions** of concern.

## 2. Concepts to Distinguish

| Term | Meaning | Example |
| --- | --- | --- |
| **Principal / identity** | Identity granted permissions: user, group, service account, domain, or workload identity | `user:dev@example.com`, `group:auditors@example.com` |
| **Role** | Collection of permissions | `roles/storage.objectViewer` |
| **Permission** | Specific action controlled by IAM | `storage.objects.get`, `resourcemanager.projects.setIamPolicy` |
| **Allow policy** | Policy consisting of role bindings granting permissions, optionally with conditions | Group A granted role B on project C |
| **Resource** | Target object: project, bucket, service account, and many other resource types | `//cloudresourcemanager.googleapis.com/projects/123456789012` |
| **Ancestor** | Higher-level resource in the hierarchy | Organization → Folder → Project |
| **Query scope** | Organization/project/folder scope that Policy Analyzer is asked to analyze | `organizations/987654321098` |
| **Condition** | Expression limiting when an allow binding applies | Active only before a specific timestamp |
| **Effective access** | Actual ability to exercise a permission after accounting for deny policies, boundaries, other policies, and context | Someone has an allow binding yet is still blocked by IAM Deny |

Distinguishing **role** and **permission** is critical. Asking "Who has `roles/editor`?" differs from "Who has `storage.objects.get`?" A permission can appear in many different roles, including predefined or custom roles. When investigating a specific action, query by **permission** if the exact permission name is known.

## 3. How Does Policy Analyzer Work?

**Policy Analyzer for allow policies** belongs to the Policy Intelligence suite and uses the IAM policy analysis capabilities of **Cloud Asset Inventory**. You supply an **analysis query** to find role bindings matching criteria:

- **Principal:** who is being analyzed?
- **Access:** which role or permission?
- **Resource:** which target resource?
- **Scope:** analyze within which organization, folder, or project?
- **Condition context:** in some cases, a hypothetical timestamp to evaluate IAM conditions.

Usually you specify only one or two search criteria; the remaining fields become the discovery output in the results.

~~~mermaid
flowchart LR
    Q["Permission review question"] --> S["Select query scope"]
    S --> I["Select principal (optional)"]
    I --> A["Select role / permission (optional)"]
    A --> R["Select resource (optional)"]
    R --> C["Policy Analyzer reads relevant IAM allow bindings"]
    C --> K["Result: binding, principal, access, resource, condition"]
    K --> V["Evaluate limits and verify further if needed"]
~~~

### 3.1. Three Typical Question Patterns

| Business Question | Query Fields to Provide | What to Inspect |
| --- | --- | --- |
| Who is allowed to read the order-exports bucket? | Resource + permission `storage.objects.get` | Principals, groups, bindings, and policy-attached resources |
| What roles does Developer A hold on the production project? | Principal + resource | Matching role bindings and where they are attached |
| Which resources can the deployment service account modify? | Principal + sensitive permission | List of resources/bindings within analysis scope |
| Who has permission to change project IAM policies? | Permission `resourcemanager.projects.setIamPolicy` | Principals granted the permission, especially broad higher-level grants |
| Who can impersonate the deployment service account? | Service account resource + impersonation permissions and impersonation analysis option | Identity delegation permissions and potential grant chains |

**Do not use overly broad queries by default.** An organization with many projects, groups, and policies can return massive results. Start with the specific resource and permission under investigation and broaden scope only with justification.

### 3.2. Query Scope vs. Resource Filter

**Scope** determines the set of IAM allow policies the query is authorized/instructed to examine: at that organization, folder, or project and its covered descendants. **Resource filter** specifies the resource whose access you want to inspect.

For example:

- Scope `projects/commerce-prod`: the query primarily examines policies inside the project and supported child resources.
- Scope `organizations/987654321098`, filtered to project `commerce-prod`: analysis can also include ancestor allow bindings (organization/folder) affecting that project.

An easily missed detail: running at **project** scope may omit bindings **attached to parent folders/organization**. When you need to account for all inherited permissions on a resource, choose a sufficiently high scope with appropriate read access.

## 4. Policy Analyzer Limitation: Analyzes IAM Allow Policies Only

This is the most important limitation in this lesson. Policy Analyzer for allow policies analyzes **permissions granted by IAM allow bindings**, without fully evaluating every access control mechanism that can make an API call succeed or fail.

Per Google Cloud documentation, this tool **does not account for** several control layers such as:

- **IAM Deny policies**.
- **IAM Principal Access Boundary (PAB) policies**.
- **Kubernetes RBAC** in GKE.
- **Cloud Storage ACLs** and **Cloud Storage public access prevention**.
- Service-specific conditions, limits, or request context outside allow-policy analysis.

For example, a user may hold a role containing `storage.objects.get` at the organization level, yet an IAM Deny policy blocks that permission on the relevant resource. **Policy Analyzer can still list the allow binding**, even though actual object read requests are denied.

~~~mermaid
flowchart TD
    A["Matching IAM allow binding"] --> B["Policy Analyzer can list the permission"]
    B --> C["Check IAM Deny / PAB / other conditions"]
    C --> D{"Do final controls allow?"}
    D -->|Yes| E["Proceed to check actual API request"]
    D -->|No| F["Request denied despite allow binding"]
~~~

Therefore, when writing reports, phrase findings as **"granted by IAM allow policy"** rather than asserting unconditionally **"can access the resource."** If the question is why a principal using a specific permission is blocked, pair with **Policy Troubleshooter**.

### 4.1. IAM Inheritance

Policy Analyzer can trace bindings across the hierarchy when the **scope** is broad enough. For example, an operations team holds a role on the Production folder; there is no direct binding on the project, yet an inherited grant exists. Querying from organization scope reveals where the grant originates.

### 4.2. IAM Conditions

If an allow binding has a **condition**, Policy Analyzer returns condition details. Some resource-attribute conditions can be evaluated automatically; time-based conditions require supplying **access time** via CLI/API to evaluate at a hypothetical timestamp.

When context is insufficient to evaluate, the result may be marked **`CONDITIONAL`**. Never treat `CONDITIONAL` as equivalent to `TRUE`. A condition warrants additional verification.

### 4.3. Data Freshness and Completeness

Policy Analyzer relies on the Cloud Asset API, which provides **best-effort** data freshness; recent IAM changes typically appear after a delay rather than instantaneously. Console queries may also hit timeouts and show **incomplete results**. The API returns a `fullyExplored` field indicating whether the analysis result was fully explored; check it when using results for automation or audit evidence.

If a role was revoked at 10:01, an analysis at 10:02 may still reflect the previous state. Never rely solely on a single snapshot to confirm an immediately applied permission change.

## 5. Distinguishing Policy Analyzer from Related Tools

| Tool | Primary Question | Limitations / Usage |
| --- | --- | --- |
| **Policy Analyzer for allow policies** | Who is granted which role/permission on which resource via IAM allow? | Analyzes bindings, inheritance, and certain conditions; does not fully evaluate deny/PAB |
| **Policy Troubleshooter** | Can principal X use permission Y on resource Z under supported policies, and why? | Ideal for single principal–permission–resource questions, covering allow/deny/PAB where supported |
| **IAM Recommender** | Which permissions can be reduced based on usage signals and analysis? | Recommendations only; review workload, job schedules, and operational needs before applying |
| **Cloud Asset Inventory / Policy Search** | Which IAM policies/resources exist in scope? | Useful for inventory; a single binding alone may miss inherited permissions |
| **`gcloud ... get-iam-policy`** | What policy is attached directly to this resource? | Does not show the full hierarchy picture on its own |
| **Organization Policy Analyzer** | How are Organization Policy constraints enforced or impacting resources? | For organizational configuration constraints, distinct from IAM allow bindings |
| **Cloud Audit Logs** | Which API actions occurred, by which principal, within enabled log coverage? | Actual activity trail; does not replace granted-permission inventory |

These tools complement one another. When reviewing risks like "who can modify policies?", start with Policy Analyzer. When a team just hit `403 PERMISSION_DENIED`, Policy Troubleshooter is better suited to analyze access for that specific request.

## 6. Preparing Permissions and Analysis Environment

To read policies and run analyses, the account needs appropriate permissions on the **query scope**; a commonly used role is **Cloud Asset Viewer** (`roles/cloudasset.viewer`). When analyzing custom IAM roles, **Role Viewer** (`roles/iam.roleViewer`) may be needed. When running via Google Cloud CLI, **Service Usage Consumer** (`roles/serviceusage.serviceUsageConsumer`) on the consumer project may be required.

Permissions associated with Cloud Asset IAM Policy Analysis include:

~~~text
cloudasset.assets.analyzeIamPolicy
cloudasset.assets.searchAllIamPolicies
cloudasset.assets.searchAllResources
~~~

In addition, you need:

- The **Cloud Asset API** enabled on the project making API calls if not already enabled.
- An account or ADC suitable for Console, CLI, or API calls.
- Accurate organization/folder/project identifiers.
- Appropriate permissions for Google Workspace groups or custom roles when expanding details.
- Awareness of quotas, feature limits, and query costs; for large environments, check current pricing and quota docs.

**Least-privilege principle:** someone auditing the whole organization should be granted read access at the corresponding scope per organizational policy—they do not need `roles/owner` just to view results. If permissions cover only a project scope, do not interpret results as a complete organization audit.

## 7. Hands-On in Google Cloud Console

Suppose the Security team wants to know which principals hold IAM administration permissions on a production project.

1. Open Google Cloud Console and navigate to the **Policy analyzer** page under Policy Intelligence.
2. In the policy analysis area, select **Create custom query**.
3. Choose a **query scope** high enough to cover relevant ancestors; for example, the organization if tracing inherited permissions.
4. Select **Permission** and enter `resourcemanager.projects.setIamPolicy`; if supported by the UI, add a **Resource** filter for the target project.
5. Run the query and inspect results by principal, role binding, policy source, and affected resource.
6. If groups, conditions, or service accounts appear, review expansion options while keeping track of scope and analysis context.
7. Check query completion status. If the UI reports incomplete results, do not conclude the final list is exhaustive.
8. Record findings as input for IAM owner reviews—never modify permissions solely from a single query.

Button/label names may vary by Console version; official documentation at the end provides links for reference.

### Query Design Tip

Do not start by "listing all permissions across the organization" when the question is "who can modify IAM on one project?" Filter by **resource + permission** first, then expand groups/roles only as needed for investigation. This reduces result volume and ties actions directly to real risk.

## 8. Hands-On with Google Cloud CLI

The commands in this section are **analysis/read-only** and do not modify IAM. They require the Cloud Asset API, appropriate permissions, and an authenticated account.

### 8.1. Checking Account and Identifiers

~~~bash
gcloud auth list
gcloud config get-value project
gcloud organizations list
~~~

The following sample values are illustrative only:

~~~text
Organization ID: 987654321098
Project ID: commerce-prod-example
Project number: 123456789012
Principal: user:reviewer@example.com
~~~

**Project ID differs from project number.** When using `--project` for scope, either ID or number may work depending on command support. With `--full-resource-name`, you must use the resource type's **full resource name** format, not just a display name.

### 8.2. Who Has Permission to Modify a Project's IAM Policy?

~~~bash
gcloud asset analyze-iam-policy \
  --organization=987654321098 \
  --full-resource-name="//cloudresourcemanager.googleapis.com/projects/123456789012" \
  --permissions="resourcemanager.projects.setIamPolicy"
~~~

This query uses organization scope to examine relevant allow bindings, including potentially inherited permissions. Equivalent question: **"According to IAM allow policies, which principals are granted `resourcemanager.projects.setIamPolicy` on this project?"**

When reading output, inspect the role binding containing the permission, where the policy is attached, and the principals involved; verify that the resource name and project number match the intended target.

### 8.3. What Permissions Does a Person Have in a Project?

~~~bash
gcloud asset analyze-iam-policy \
  --organization=987654321098 \
  --full-resource-name="//cloudresourcemanager.googleapis.com/projects/123456789012" \
  --identity="user:reviewer@example.com"
~~~

This query finds allow bindings matching the specified principal for the project. When you need to uncover **group memberships** and roles granted through groups, check **group expansion** settings, group membership read permissions, and related limits. Do not assume searching an individual email automatically lists every permission held indirectly via groups without proper configuration and verification.

### 8.4. On Which Resources Is a Service Account Granted a Permission?

~~~bash
gcloud asset analyze-iam-policy \
  --organization=987654321098 \
  --identity="serviceAccount:deploy-bot@commerce-prod-example.iam.gserviceaccount.com" \
  --permissions="resourcemanager.projects.setIamPolicy"
~~~

Querying by principal + permission reveals allow bindings granting policy-modification permissions across resources in the organization. To narrow output, switch to a folder/project scope for focused checks, keeping in mind that grants attached to ancestors outside that scope may be excluded.

### 8.5. Checking Time-Based Permissions on Conditional Bindings

~~~bash
gcloud asset analyze-iam-policy \
  --organization=987654321098 \
  --identity="user:temporary-reviewer@example.com" \
  --full-resource-name="//cloudresourcemanager.googleapis.com/projects/123456789012" \
  --access-time="2026-11-20T09:00:00Z"
~~~

`--access-time` supplies a hypothetical timestamp (RFC 3339/ISO 8601 with timezone) so the tool can evaluate supported time-based conditions. Not every IAM Condition type can be decided solely by a timestamp; read the `TRUE`/`CONDITIONAL` evaluation and context.

### 8.6. Investigating Service Account Impersonation Paths

An advanced CLI option analyzes impersonation paths reflected in IAM allow policies:

~~~bash
gcloud asset analyze-iam-policy \
  --organization=987654321098 \
  --permissions="storage.objects.get" \
  --analyze-service-account-impersonation
~~~

During this extended analysis, Policy Analyzer can examine permissions related to acting as a service account such as `iam.serviceAccounts.getAccessToken`, `iam.serviceAccounts.signJwt`, and `iam.serviceAccounts.actAs`. **These permissions serve different mechanisms**; an `actAs` binding does not by itself prove a principal can directly mint OAuth access tokens via the IAM Credentials API.

Use impersonation results as an **investigation signal**, then verify actual IAM and credential-issuing mechanics. In large organizations, an impersonation query without resource filters can produce huge output; add appropriate resource or permission filters before running.

### 8.7. When to Enable Expansion Options?

Several options are supported by the CLI/API:

| Option | Effect | Things to Watch |
| --- | --- | --- |
| `--expand-groups` | Expands groups into members when permissions/conditions allow | Subject to member count limits, nested group limits, and group read permissions; works only on applicable query types |
| `--expand-roles` | Displays permissions inside roles | Usage constraints; documentation notes it is available only when the query omits roles/permissions |
| `--expand-resources` | Lists related child resources in results | Subject to resource count limits; not guaranteed to expand entire large trees |
| `--analyze-service-account-impersonation` | Additionally analyzes principals with eligible impersonation paths | Does not replace effective-access verification |
| `--access-time` | Provides time context to evaluate IAM Conditions | Cannot evaluate every condition solely from time |

You do not need to enable every option on every query. Enable only what addresses the question at hand and record query parameters so others can reproduce the result.

## 9. Reading Analysis Results Accurately

A Policy Analyzer query can return details such as:

- **Binding:** granted role, principals in the binding, and IAM Condition if present.
- **Policy attachment:** resource where the binding is attached.
- **Access:** role/permission relevant to the query.
- **Resources:** target resources or related child resources when expansion is enabled.
- **Principal/group details:** matching identities and authorized expanded details.
- **Condition evaluation:** `TRUE`, `CONDITIONAL`, or other status per supported context/mechanism.
- **Exploration/completeness:** whether the query explored results completely (especially in the API).

An illustrative output could be interpreted as:

~~~text
Scope: organizations/987654321098
Resource: //cloudresourcemanager.googleapis.com/projects/123456789012
Permission: resourcemanager.projects.setIamPolicy

Binding source: organizations/987654321098
Role: roles/resourcemanager.projectIamAdmin
Principal: group:platform-admins@example.com
Condition: none
Interpretation:
  The platform-admins group holds an allow binding with the relevant permission
  at the organization level, so inheritance down to the project must be reviewed.
~~~

This is an **illustrative interpretation**, not a real API response. When working with live data, take role IDs, resource names, conditions, and IAM bindings directly from the system.

### 9.1. What Does an Empty Result Mean?

**"No bindings found in this result"** is only an observation for the current query's scope, filters, read permissions, expansion options, timestamp, and data freshness. It is insufficient to assert "nobody has access" when:

- The scope excludes the ancestor where the permission is granted.
- A principal gains access indirectly via groups or service account impersonation.
- The query timed out or hit result limits.
- Cloud Asset data has not yet reflected recent updates.
- The resource is governed by another mechanism outside IAM allow.
- The querying account lacks permissions to read required details.

Audit reports must preserve these caveats, especially when results serve as evidence for approving changes.

## 10. Reviewing Groups, Conditions, and Service Accounts

### 10.1. Google Groups and Indirect Identities

If a binding grants access to `group:platform-admins@example.com`, Policy Analyzer may report the group rather than individual people. To see which specific users belong to the group, inspect membership or use **group expansion** where permissions and limits allow.

Even after expanding, watch for nested groups and membership state at review time. Never assume a group is well-governed from its display name alone; identify its owner, membership approval workflow, and review schedule.

### 10.2. Conditional Bindings

Suppose an allow binding is valid only before a specific timestamp. To evaluate it, context must be supplied. If the result is `CONDITIONAL`, the reviewer must verify further before concluding the permission holds in all situations.

A practical review record should capture:

| Field | Example |
| --- | --- |
| Principal | `group:prod-operators@example.com` |
| Role/permission | Project metadata read permission |
| Granted at | Production Folder |
| Affected resource | Commerce production project |
| Condition | Applies only during approved window |
| Analyzer result | `CONDITIONAL` |
| Next action | Verify condition and run Policy Troubleshooter for specific scenarios |

### 10.3. Service Accounts and Impersonation

A service account may hold permission to read a bucket while another principal holds permission to **impersonate** that service account via IAM mechanisms. Checking only the service account email misses potential indirect access paths.

For example, in a CI/CD system: `deploy-bot` can deploy Cloud Run, while developers are only supposed to impersonate service accounts in dev. Without auditing impersonation paths and scopes, an unintended privilege escalation path can slip through.

Distinguish **permission to attach a service account to a workload**, **permission to mint access tokens as a service account**, and **roles granted on target resources**. They involve different permissions and conditions.

## 11. Periodic Permission Review Workflow

Running a query once is just the first step; Policy Analyzer's value comes from a workflow with clear ownership, risk criteria, and post-change verification.

~~~mermaid
flowchart TD
    A["Select sensitive resources and owners"] --> B["Identify principals / permissions to review"]
    B --> C["Run Policy Analyzer with appropriate scope"]
    C --> D["Record bindings, sources, conditions, completeness"]
    D --> E{"Broad permissions or suspicious access paths?"}
    E -->|Yes| F["Verify with Policy Troubleshooter, owner, and audit logs"]
    E -->|No| G["Archive evidence and schedule next review"]
    F --> H["Propose least privilege / controlled change"]
    H --> I["Execute after approval per workflow"]
    I --> J["Verify after change and record decision"]
    J --> G
~~~

### Step 1: Choose Scope and Criticality

Prioritize resources holding sensitive data, deployment service accounts, production projects, or permissions capable of altering IAM/application configurations. Organization-wide reviews are useful, yet should start from **specific questions**.

Three example periodic checks:

1. Who is granted `resourcemanager.projects.setIamPolicy` on production projects?
2. Who can read Cloud Storage buckets holding customer data according to IAM allow policies?
3. Who can impersonate service accounts authorized to deploy Cloud Run or administer GKE?

### Step 2: Capture a Baseline

Record at minimum: query timestamp, scope, filters, expansion options, completion status, principal, role, permission, binding source, and reviewer. When supplying audit evidence, store results via organization-approved channels rather than sharing full permission dumps broadly.

### Step 3: Triage Findings

| Finding | Potential Risk | Question to Verify |
| --- | --- | --- |
| Broad role at organization | Permissions propagate to many projects | Is org-wide scope required, or only a folder? |
| Production project receives grants from wrong folder | Environment privilege boundary skewed | Is the project under the right parent? |
| Group with hundreds of members | Many people hold indirect access | Which memberships are still needed, and who owns the group? |
| Impersonation on highly privileged service account | May open extra access paths | Does the principal genuinely need impersonation? |
| Unresolved conditional grant | Hard to tell when access applies | Which access time or context is needed? |
| No workload currently using a role | Excess privilege that could be trimmed | Do scheduled jobs or DR procedures still use it? |

### Step 4: Verify Before Changing

Use Policy Troubleshooter for specific principal, permission, and resource cases; cross-check IAM Deny, PAB, and service-specific policies when needed. If proposing role removal, confirm with the workload owner and job schedules to prevent outages.

Least privilege must be grounded in **actual business need**, not just usage observed over a short window. A permission used only during disaster recovery may still be legitimate, though it should be governed via an appropriate mechanism.

### Step 5: Controlled Change and Verification

Once authorized stakeholders approve, modify IAM at **the resource where the role binding is attached**. If a permission comes from the organization, deleting roles on the project does not remove the inherited binding. If access comes from a group, adjusting group membership may be more appropriate than deleting the entire group's binding.

Re-run the query after data updates, test affected workload requests, and document the rationale for keeping or revoking access. Never treat an immediate re-query as final confirmation because Cloud Asset has propagation latency.

## 12. Real-World Scenario: Before Deploying Production Cloud Run

The Commerce team wants to deploy `orders-api` on Cloud Run in project `commerce-prod`, using Cloud Storage and Cloud SQL. Security requires confirming there are no unexpected broad deployment or administrative permissions.

**Planned structure:**

~~~text
Organization: Atlas
└── Folder: Production
    └── Project: commerce-prod
        ├── Cloud Run: orders-api
        ├── Service account: orders-runtime
        ├── Cloud SQL: orders-db
        └── Cloud Storage: order-exports
~~~

**Review checklist:**

| Target | What to Verify | Why |
| --- | --- | --- |
| Project `commerce-prod` | Who has `resourcemanager.projects.setIamPolicy`? | Prevent unintended IAM modifications |
| Service account `orders-runtime` | Who can impersonate/attach it to workloads? | Prevent abuse of a data-privileged identity |
| Bucket `order-exports` | Who has `storage.objects.get`? | Audit read paths to sensitive data |
| CI/CD deployer | Which roles/permissions does it hold in production? | Bound deployment privileges |
| Production Operators group | Who are the members? | Reduce unintended indirect permissions |

**Hypothetical finding:** the query discovers group `dev-all@example.com` holds a broad role at the organization level containing administrative permissions on production projects. Remediation steps:

1. Confirm whether the root binding is on the organization or a folder.
2. Verify whether the role actually contains the permission in its current definition.
3. Analyze group memberships and related IAM conditions.
4. Use Policy Troubleshooter with a specific principal to inspect allow/deny/PAB effects.
5. Coordinate with owners to adjust IAM at the right scope: narrow scope, swap roles, or adjust group membership.
6. After the change, re-test legitimate deployment pipelines and verify unintended access paths are closed.

This aligns with the broader GCP track: when deploying Compute Engine, GKE, Cloud Run, or accessing Cloud SQL/Storage, IAM reviews are part of protecting resources and maintaining reliability. Overly broad permissions introduce security and cost risks (such as unexpected resource creation); mistakenly revoked permissions can break CI/CD or live applications.

## 13. Large Queries, Exports, and Reporting

When an organization has many projects and thousands of IAM bindings, an interactive query may hit timeouts or result limits. Policy Analyzer supports **long-running** analysis to export results to BigQuery or Cloud Storage via the `analyzeIamPolicyLongrunning` API.

Preparation checklist:

- Define a scope and filters narrow enough to answer the audit question.
- Grant required policy read permissions and write permissions to the export destination.
- Restrict access to the BigQuery dataset or Cloud Storage bucket holding analysis outputs; an IAM inventory itself reveals sensitive organizational structure.
- Evaluate quotas, query limits, runtime, and **costs** of the feature per current documentation.
- Verify completion status, freshness, and missing fields before turning outputs into formal reports.

Illustrative logical schema for internal reporting (illustrative only, not a standard API output schema):

~~~text
review_id
analysis_time
analysis_scope
resource_full_name
principal
role
permission
attached_policy_resource
condition
completeness
review_owner
decision
next_review_date
~~~

Recording **query options** helps future auditors reproduce what the results mean. In particular, never sum expanded group rows and binding rows as independent permissions; a single grant can expand into many principals.

## 14. Common Mistakes and Misconceptions

| Misconception | Consequence | How to Handle |
| --- | --- | --- |
| "Policy Analyzer says access exists, so API calls will definitely succeed." | Ignores deny/PAB and other access mechanisms | State accurately "per IAM allow"; verify with Policy Troubleshooter |
| "I checked project IAM, so I know all inherited permissions." | Misses grants at folder/organization | Pick a sufficiently high query scope and inspect binding sources |
| "User's name is absent from bindings, so they have no access." | Misses group membership or impersonation paths | Check group memberships and impersonation |
| "All IAM Conditions are fully evaluated." | Wrong conclusions about time-bound access | Supply context and inspect `CONDITIONAL` status |
| "Empty results guarantee nobody has access." | Ignores scope, data freshness, and read permission limits | Check query, completeness, and complementary methods |
| "Broader reviews are always better." | Huge noisy output, hard to analyze, wastes resources | Start from high-risk permissions/resources |
| "Revoking the grant on the project is enough." | Inherited grant remains active | Modify at the actual binding source |
| "Right after removing a role, queries must update immediately." | Misinterpretation due to data propagation delay | Wait for updates and verify via appropriate methods |
| "Policy Analyzer also checks Organization Policy constraints." | Confuses governance layers | Use Organization Policy Analyzer for constraint questions |
| "Any role unused recently can be deleted immediately." | May break periodic jobs or disaster recovery | Combine owner review, usage signals, and testing plan |

## 15. Self-Check Exercises

**Question 1.** Group `prod-operators` holds a role on the Production folder. No binding is attached directly to project `commerce-prod`. Could the group still have permissions on the project via IAM allow?

*Hint:* Yes, if the binding inherits appropriately. Run Policy Analyzer with a scope covering the relevant folder/organization rather than inspecting only direct project IAM policies.

**Question 2.** Policy Analyzer reports a user is granted `storage.objects.get` on a bucket. Can you conclude the user can read every object in all cases?

*Hint:* No. Policy Analyzer for allow policies does not fully evaluate deny policies, PAB, ACLs, and all service mechanisms; verify context and effective access.

**Question 3.** You need to know **why** `user:dev@example.com` receives `403` when calling an API on a specific resource. Which tool should you use first?

*Hint:* Policy Troubleshooter is suited for checking a principal–permission–resource tuple and evaluating supported allow/deny/PAB policies. Policy Analyzer is useful for finding broadly granted bindings.

**Question 4.** A time-based IAM Condition appears in results as `CONDITIONAL`. Does it definitely hold at all times?

*Hint:* No. Supply `--access-time` or corresponding context if supported by that condition type and read the evaluation result.

**Question 5.** Why can granting a role to a group result in more people effectively holding access than the emails listed in the IAM policy?

*Hint:* Group bindings apply through membership; nested groups may exist and membership changes over time. Group expansion/group inspection with proper permissions is needed.

**Question 6.** A project-scoped query finds no admin grant, yet Security suspects a grant comes from the organization. What adjustment helps most?

*Hint:* Re-run at organization scope (or a sufficiently broad ancestor) while filtering for the specific project/permission to uncover inherited grants.

**Question 7.** A principal is allowed to use `iam.serviceAccounts.actAs` on a service account. Does that mean the principal can definitely call the IAM Credentials API to mint OAuth tokens for that service account?

*Hint:* No. `actAs` and `getAccessToken` are distinct permissions serving different actions. Analyze the exact mechanism used.

**Question 8.** Minutes after modifying permissions on a production project, Policy Analyzer still displays the old binding. Should you conclude the change failed?

*Hint:* Not yet. Cloud Asset API has best-effort freshness. Check the source policy directly and wait for updated results alongside behavioral verification.

**Question 9.** When should you use long-running analysis and export results to BigQuery/Cloud Storage?

*Hint:* When result volume is large, detailed audit analysis is needed, or interactive queries are incomplete; control permissions, quotas, costs, and sensitivity of exported data.

## 16. Permission Review Practice Checklist

- [ ] State the security question clearly: which principal, permission, and resource are under review?
- [ ] Choose an organization/folder/project scope broad enough to capture inherited grants.
- [ ] Verify the analyzing account holds required policy-read permissions.
- [ ] Use targeted filters; avoid overly broad queries unnecessarily.
- [ ] Record binding attachment source, role/permission, principal, and IAM Condition.
- [ ] Check group memberships, impersonation paths, and expansion options where applicable.
- [ ] Verify result completeness and freshness.
- [ ] For specific access decisions, cross-check deny/PAB with Policy Troubleshooter where appropriate.
- [ ] Coordinate with workload owners before proposing permission reductions.
- [ ] Verify post-change across appropriate scope, timing, and methods.
- [ ] Archive decisions, evidence sources, executors, and the next review cycle.

## 17. Key Takeaways

- **Policy Analyzer for allow policies** answers IAM allow-binding questions along **who – what permission – which resource**.
- **Scope** dictates where the tool searches policies; to include inherited grants, pick a sufficiently high scope.
- **Results are not final effective access** because IAM Deny, Principal Access Boundary, IAM Conditions, and service-level controls still apply.
- **Groups, service account impersonation, and custom roles** can make indirect access hard to spot.
- **Policy Troubleshooter** is the right fit to check whether a specific principal can use a specific permission on a specific resource under supported policies.
- Permission reviews must tie into **owners, evidence, workload impact, and post-change verification**.

When deploying Compute Engine, GKE, Cloud Run, Cloud Storage, Cloud SQL, or CI/CD in the Google Cloud module, ask three questions before granting permissions: **"Who genuinely needs this permission? Should it live at the project, folder, or specific resource? How will we detect and revoke it when no longer needed?"** Policy Analyzer supplies answers from IAM allow data; sound governance turns those answers into safe decisions.

## Official Documentation References

- [Policy Analyzer for allow policies — Overview](https://cloud.google.com/policy-intelligence/docs/policy-analyzer-overview)
- [Analyze allow policies](https://cloud.google.com/policy-intelligence/docs/analyze-iam-policies)
- [gcloud asset analyze-iam-policy](https://cloud.google.com/sdk/gcloud/reference/asset/analyze-iam-policy)
- [Cloud Asset Inventory API: analyzeIamPolicy](https://cloud.google.com/asset-inventory/docs/reference/rest/v1/TopLevel/analyzeIamPolicy)
- [IAM Policy Troubleshooter](https://cloud.google.com/policy-intelligence/docs/troubleshoot-access)
- [Policy Intelligence overview](https://cloud.google.com/policy-intelligence/docs/overview)
- [Cloud Asset Inventory roles and permissions](https://cloud.google.com/asset-inventory/docs/roles-permissions)
