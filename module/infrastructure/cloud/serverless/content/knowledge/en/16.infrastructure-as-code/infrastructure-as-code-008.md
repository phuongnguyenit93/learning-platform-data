# Managing Infrastructure State, Detecting Drift, and Reviewing Changes

Infrastructure as Code (IaC) describes desired infrastructure using version-controlled code or configuration. When a tool such as Terraform or OpenTofu creates resources, it needs to know which resource in configuration corresponds to which object existing in the cloud. State is the record that lets the tool maintain that mapping across multiple plan and apply runs.

State is neither the desired configuration nor a complete, always-accurate mirror of the cloud. It stores mappings, metadata, and the attributes needed for the tool to compute changes. When someone edits a resource directly in the portal, another automation changes configuration, or a change happens outside the IaC pipeline, state can fall out of sync with reality. This discrepancy is called configuration drift or infrastructure drift.

Securing state, deliberately detecting drift, and reviewing plans before applying are foundational to stable serverless deployments. A small change such as modifying an IAM policy, function timeout, concurrency, queue retention, or database setting can affect security, availability, and cost across the entire system.

In the **CLOUD_SERVERLESS** module, learners build and deploy Java functions triggered by HTTP, messages, or events while handling permissions, state, retries, idempotency, cold starts, scaling, and cost. This lesson explains how to store and protect state, recognize drift, read plans, and establish an infrastructure change review workflow.

## 1. Three Concepts to Distinguish

An IaC workflow always involves at least three perspectives:

1. **Desired configuration:** the target state described in IaC files, modules, variables, and provider configurations.
2. **State:** the record the IaC tool uses to map resource addresses in code to live objects, while also storing metadata and observed attributes.
3. **Real infrastructure:** the resources actually running in the cloud or target system at the present moment.

Diagram:

~~~mermaid
flowchart TD
    C[Desired configuration] --> P[Plan / diff]
    S[Stored state] --> P
    R[Real infrastructure] -->|Refresh / read| P
    P --> D{Reviewed changes}
    D -->|Approved| A[Apply]
    A --> R
    A --> S
~~~

Plan compares the desired configuration against state after refreshing from the provider. The tool uses that result to propose create, update, replace, or destroy actions. Apply executes the approved operations and updates state after the provider returns results.

State should not be treated as an exact mirror of real infrastructure. Some attributes cannot be read back, some APIs return eventually consistent data, providers may normalize values, and state may not have been refreshed since the most recent change.

## 2. What Does State Store and Why Is It Needed?

State typically contains:

- Resource addresses in configuration, such as module, resource type, resource name, and instance key.
- Live object IDs returned by the provider or cloud API.
- Known resource attributes, including computed values returned by the provider.
- Dependencies and metadata needed to plan changes.
- Provider/resource schema information or state format version.
- Outputs and potentially sensitive data depending on configuration.

Configuration example:

~~~hcl
resource "aws_lambda_function" "orders" {
  function_name = "orders-api"
  runtime       = "java21"
  handler       = "com.example.OrderHandler"
  role          = aws_iam_role.lambda_exec.arn
  filename      = "build/orders.zip"
}
~~~

In state, the tool must know which AWS Lambda function corresponds to resource address `aws_lambda_function.orders`, along with attributes read from the provider. When a resource is renamed in code, the tool needs to know whether it is the same function moved to a new address or a different function to create.

If state is lost, the tool loses the mapping to manage existing resources. On plan, it may propose creating resources that already exist or fail to recognize resources needing updates. Therefore, state must be stored durably, backed up, and protected as critical operational data.

### State Is Not an Application Backup

State does not contain the full runtime data of functions, messages in queues, objects in buckets, or database records. Nor does it replace database or artifact backups. Backing up state only recovers the IaC mapping, not lost business data.

## 3. State Lifecycle: From Init to Apply

A typical Terraform/OpenTofu workflow:

1. Initialize the working directory and backend.
2. Load providers/modules and configuration.
3. Read current state from the backend.
4. Refresh resources readable via the provider.
5. Compare desired configuration against refreshed state.
6. Generate an execution plan containing required actions.
7. Human or policy reviews the plan.
8. Apply the approved plan.
9. Provider creates/updates/deletes resources and the tool writes the new state.

Basic commands:

~~~bash
terraform init
terraform validate
terraform plan
terraform apply
~~~

With OpenTofu, the corresponding CLI commands typically use the `tofu` prefix. Standardize on a single toolchain and version across the team; avoid having the same state manipulated by incompatible versions or provider schemas.

### What Is Refresh?

Refresh is the step where the tool calls the provider to read the current state of resources and updates observed information in the working state. Refresh lets the plan detect certain changes made outside IaC.

Refresh does not modify infrastructure to match code. It simply gives the tool a fresher view of live state before building a plan. A post-refresh plan may propose reverting the resource to desired configuration, accepting the external change by updating code, or applying another change decided by the reviewer.

## 4. Local State vs. Remote Backend

By default, Terraform can store state locally in `terraform.tfstate`. This is convenient for personal experiments, but unsuitable for teams or production pipelines without an explicit synchronization and backup process.

A remote backend stores state in a supported shared location, such as object storage or a state management service. Depending on the backend, it can provide locking, versioning, encryption, and access control.

| Criterion | Local state | Remote backend |
|---|---|---|
| Sharing across team members | Must manually transfer files | Members access the same backend |
| Locking | Hard to coordinate without external mechanisms | Can support locking depending on backend |
| Backup/versioning | Team must manage manually | Can leverage versioning or version history |
| CI/CD | Error-prone if runners hold different state copies | Pipelines use a single source of state |
| Security | Easy to accidentally commit or send files | Supports IAM, encryption, and auditing |
| Recovery | Depends on local backups | Can restore backend versions if enabled |

A remote backend is not automatically secure simply because state sits in the cloud. Encryption, access permissions, network policies, logging, and backups must be configured per system requirements.

### S3 Backend Example

The example below illustrates Terraform's S3 backend. Syntax and locking features depend on Terraform version; pin the tool version and check the corresponding backend documentation before production use.

~~~hcl
terraform {
  backend "s3" {
    bucket       = "company-iac-state"
    key          = "cloud-serverless/prod/terraform.tfstate"
    region       = "ap-southeast-1"
    encrypt      = true
    use_lockfile = true
  }
}
~~~

The bucket and object key must be provisioned via a bootstrap process. The identity running Terraform needs permissions to read/write the specific state object and any required lock permissions. If your backend version supports state locking, enable and test it; do not assume every backend or version uses the exact same mechanism.

Never place access keys or secrets in the backend block and commit them to Git. Use workload identity, role assumption, environment credentials, or a secret manager appropriate for the pipeline environment.

## 5. State Locking and Concurrent Apply

State locking prevents two processes from writing to the state of the same workspace/backend key simultaneously. If two pipelines apply concurrently, they can read the same stale state, apply conflicting changes, and overwrite each other's state. The result can be a state that no longer matches real resources.

When a backend supports locking, Terraform/OpenTofu normally acquires a lock before state-mutating operations and releases it upon completion. If a lock is already held, other processes must wait or abort according to policy.

Operational rules:

- Never run concurrent applies on the same state key.
- Never remove a lock manually just because a pipeline appears to be waiting.
- Identify the process/runner holding the lock and verify whether it has finished.
- Only force-unlock when certain the lock was orphaned and no operation is still running.
- Record the lock ID, workspace/backend key, and reason for force-unlock in an audit log.
- Split state along deployment boundaries if multiple teams need to make independent changes.

The `force-unlock` command can cause damage if used while another apply is still active. Never automate `force-unlock` in CI merely on timeout; inspect runner and backend status first.

## 6. Securing State: Treat State as Sensitive Data

A common mistake is assuming attributes marked `sensitive` are omitted from state. In Terraform, `sensitive` primarily controls how values are displayed in outputs/CLI; it does not remove values from state or plan files.

State may contain:

- Connection strings, passwords, or tokens if the provider stores them.
- Function secret environment variables.
- Database endpoints, resource IDs, and network topology.
- Private keys or credentials if configurations/providers do not handle them specially.
- Sensitive input or output data passed through resources.

Example:

~~~hcl
variable "database_password" {
  type      = string
  sensitive = true
}

resource "example_database_user" "app" {
  name     = "orders-service"
  password = var.database_password
}
~~~

Even though the variable is marked `sensitive`, the password can still be stored in state depending on the provider/resource. Read the provider documentation to understand which attributes are persisted, whether ephemeral/write-only mechanisms exist, and how to handle secrets properly.

### Protective Measures

- Enable encryption at rest for the backend and encryption in transit.
- Restrict state read permissions using least privilege; read access to state is often nearly as sensitive as apply access.
- Never commit state files, plan files, or state backups to the repository.
- Never attach state/plan files to tickets, chats, or public artifacts.
- Use a secret manager or short-lived identities to supply credentials.
- Enable audit logging for backend access and modifications.
- Configure controlled retention, versioning, and backups.
- Separate state by environment and sensitivity level.
- Redact pipeline logs and avoid printing sensitive outputs.

Saved plan files can also contain sensitive data. Protect plan artifacts just like state, limiting retention duration and download permissions.

## 7. Separating State by Environment and Ownership

Development, staging, and production should not write to the same state if they have different lifecycles, permissions, and deployment schedules.

A backend key layout might look like:

~~~text
state/
  cloud-serverless/
    dev/terraform.tfstate
    staging/terraform.tfstate
    prod/terraform.tfstate
~~~

Each environment should have:

- Its own backend key or state store.
- An appropriate cloud account/subscription/project.
- Dedicated credentials and IAM roles.
- Separate variables and secrets.
- Distinct approve/apply permissions, especially for production.
- Environment-appropriate backups, retention, and auditing.

### Are Workspaces a Security Boundary?

Terraform workspaces allow multiple state instances to share one configuration and backend. Workspaces are useful for spinning up multiple similar deployments, but should not by default be treated as a strong security boundary. Workspaces can still share code, credentials, and backend permissions.

If production requires clear isolation, separate backend keys, accounts/projects, roles, and pipelines are usually better. The exact layout depends on team ownership and audit requirements.

### Splitting State Along Boundaries

An overly large state slows down plans, holds locks longer, and expands the blast radius of applies. Splitting state by system or lifecycle lets teams deploy more independently.

Example:

- Network state manages VPC, subnets, routes, and security boundaries.
- Platform state manages shared runtimes, logging, and artifact storage.
- Application state manages Lambda/functions, APIs, queues, and permissions.
- Data state manages databases, buckets, and backup policies.

Do not split state so finely that you must wire dozens of outputs across states. Remote state outputs can create tight coupling and broaden data read permissions. Export only necessary values, avoid exporting secrets, and consider service discovery or parameter stores for shared information.

## 8. What Is Drift?

Drift occurs when live infrastructure differs from the desired state in IaC. Common causes include:

- Operators editing resources directly in the portal or CLI.
- Another pipeline or tool modifying the same resource.
- Auto-scaling, controllers, or managed services changing provider-observed attributes.
- A resource being deleted or modified outside IaC.
- Provider/API value normalization or changed defaults.
- Stale state that has not been refreshed for a long time.

For example, code defines a Lambda timeout of 30 seconds, while an operator changes it directly to 60 seconds in the console. Once plan refreshes state, the tool detects that the actual timeout is 60 while desired configuration is 30 and proposes updating it back to 30.

### Drift Is Not Always an Incident

Three situations must be distinguished:

1. **Unintended change:** accidental edit, intrusion, or out-of-process change. Restore desired state and investigate the cause.
2. **Intentional emergency change:** an operator made a change to mitigate an incident. Document, review, and bring the approved change back into code.
3. **System-managed adjustment:** autoscaling or a service-managed field changes normally. Decide whether IaC should manage that field or ignore it intentionally.

Do not automatically apply every drift back to code before understanding why it happened. If a manual change was a hotfix that should stay, update the code first to reflect the approved state, then apply subsequent changes.

## 9. Detecting Drift with Plan

A normal `plan` refreshes resources readable by the provider before computing changes, unless options alter refresh behavior.

~~~bash
terraform plan
~~~

Plan can detect:

- A resource exists, but an attribute differs from code.
- A resource was deleted outside IaC and needs to be recreated.
- Resources created outside IaC are only detected if covered by data sources, inventory, or a separate discovery process; plan does not automatically scan the entire account for unmanaged objects.
- Configuration changes requiring an update or replacement.
- Output or dependency changes cascading into other actions.

Plan does not necessarily catch every change. Providers might not expose certain attributes, APIs can be eventually consistent, or resources may sit outside state. Drift detection also depends on credentials having sufficient read permissions.

### Refresh-Only Plans

When you want to see how state differs from live infrastructure without immediately modifying infrastructure, use refresh-only mode:

~~~bash
terraform plan -refresh-only
~~~

This mode produces a plan to update state/outputs to match provider-observed values rather than modifying resources to match desired configuration. Review the results before applying a refresh-only plan.

Do not use refresh-only as a way to hide drift. If state is updated to match an external change, code may still specify the old value. The next normal plan may propose changing the resource back to the old setting. Decide whether the external change is accepted and codified, or needs to be rolled back.

### Avoid Disabling Refresh in Routine Workflows

The `refresh=false` option can speed up planning in certain scenarios, but the plan relies on stale state and can miss drift. Only use it when you understand the implications—such as a controlled diagnostic step—not as a default workaround for provider errors or to mask out-of-band changes.

## 10. Controlled Drift Remediation Workflow

When drift is detected:

1. **Scope it:** note resource address, backend key, workspace, account/Region, and plan timestamp.
2. **Verify reality:** inspect the resource via provider/API using appropriate read-only permissions.
3. **Trace the source:** check audit logs, cloud activity logs, pipeline runs, incident tickets, and who made the change.
4. **Classify:** unauthorized change, approved hotfix, automatic adjustment, or provider normalization.
5. **Choose remediation:** revert resource to desired state or update IaC to keep the new state.
6. **Review impact:** assess replacement, downtime, IAM, networking, data loss, and cost.
7. **Apply via pipeline:** execute using a reviewed plan and authorized approvers.
8. **Re-run plan:** confirm no unexpected drift remains.
9. **Record audit:** log root cause, decision, commit, and execution ID.

### Example: Java Function Timeout Modified Outside IaC

Desired configuration:

~~~hcl
resource "aws_lambda_function" "orders" {
  function_name = "orders-api"
  timeout       = 30
  memory_size   = 1024
}
~~~

An operator increases the timeout in the AWS Console to 60 seconds while investigating a downstream timeout. A subsequent plan may show an update to revert timeout back to 30.

If the 60-second hotfix is approved, update code to 60 and review related impacts such as duration billing, retries, and API Gateway timeouts. If the hotfix is rejected, keep 30 in code and apply the plan after confirming no dependencies need simultaneous adjustment.

## 11. A Plan Is a Change Proposal, Not a Harmless Command

A plan shows what the tool intends to do. Reviewers must read per-resource actions, not just the summary line `“Plan: n to add, m to change, k to destroy”`.

Common indicators in plan output:

| Symbol/Action | Meaning | What to Watch |
|---|---|---|
| + create | Create a new resource | IAM, public exposure, quotas, and cost |
| ~ update in-place | Modify existing resource | Does it cause downtime, restarts, or behavior changes? |
| - destroy | Delete resource | Will it lose data or disrupt traffic? |
| -/+ replace | Destroy then recreate per plan order | Does it cause downtime, change endpoints, or lose stateful data? |
| +/− create then destroy | Create new first then delete old when supported by provider | May need temporary quota headroom and migration checks |
| known after apply | Value available only after apply | Check downstream dependencies and outputs |

Display symbols can vary across CLI and provider versions. Always read the detailed actions in the plan rather than relying solely on a symbol.

### Review Questions

- Which resources are created, modified, replaced, or destroyed?
- Are IAM policies, trust relationships, or public network exposure changing?
- Are function runtime, handler, memory, timeout, environment variables, or concurrency changing?
- Are queue retention, visibility timeout, retries, DLQ, or event source mappings changing?
- Are databases, buckets, encryption keys, or log retention modified or deleted?
- Will resource replacement cause downtime, change ARNs/endpoints, or lose data?
- Are there changes to Region/account/workspace?
- Are provider versions or module versions changing at the same time?
- Will costs increase due to memory, provisioned capacity, replication, or logging?
- Does the plan contain sensitive values or unknowns needing closer inspection?

## 12. Saving Plans and Applying the Exact Reviewed Plan

For production pipelines, generate a saved plan:

~~~bash
terraform plan -out=tfplan
terraform show tfplan
~~~

Once reviewers approve that exact artifact, the pipeline can apply the saved plan:

~~~bash
terraform apply tfplan
~~~

Saved plans ensure apply executes the exact reviewed decision instead of recalculating an unreviewed plan. However, plan artifacts must be protected because they can contain sensitive data. Never commit `tfplan` to Git or store it in public artifacts.

A plan can become stale if state or infrastructure changes after it was created. Terraform can refuse to apply a stale plan; when that happens, generate a fresh plan and re-review it. Do not try to force-apply an outdated plan.

A safe workflow typically entails:

- Running plan against a specific commit and specific backend/workspace.
- Storing the artifact with restricted access, short retention, and tagged with the commit SHA.
- Reviewers inspecting every action, especially destroy/replacement and IAM.
- Before applying, verifying the plan is still valid and no other deployment is mutating the same state.
- Applying the exact reviewed artifact; if a new plan is required, requiring re-review.
- Recording the approver, commit, plan summary, backend key, and apply outcome.

## 13. Reading Plans in CI via Exit Codes and JSON

Terraform supports detailed exit codes for plans in automation:

~~~bash
terraform plan -detailed-exitcode
~~~

Typically:

- Exit code 0: plan succeeded with no changes.
- Exit code 1: error generating plan.
- Exit code 2: plan succeeded and changes require review.

CI must handle all three cases distinctly. Do not treat exit code 2 as a pipeline failure; it signals pending changes. Conversely, never ignore exit code 1.

You can export JSON for policy engines or review tooling to analyze:

~~~bash
terraform show -json tfplan > tfplan.json
~~~

JSON plans can contain sensitive values even when text output is redacted. Protect the file, restrict logs, and extract only needed fields into reports. Never print the entire JSON to CI logs.

Policy-as-code can enforce rules such as:

- No security groups opening SSH/RDP to the Internet without an exception.
- No public buckets holding private data.
- No deleting production databases without approval.
- Lambda roles grant only required permissions.
- Encryption and log retention must be enabled.
- Resources carry owner, environment, and cost center tags.

Policy engines help block non-compliant plans, though humans must still review changes in their business context.

## 14. Importing Existing Resources into State

Resources may have been created manually or by another system that the team wants to bring under IaC management. Importing creates a mapping between a resource address in configuration and an object ID in the provider.

In modern Terraform, you can declare an `import` block:

~~~hcl
import {
  to = aws_lambda_function.orders
  id = "orders-api"
}
~~~

Then write the matching resource configuration and run plan to see what the tool will import and whether it proposes any changes. Do not apply until you understand the plan; if configuration differs significantly from the live resource, plan may propose updates or replacement right after import.

Traditional CLI import can also be used depending on tool/version:

~~~bash
terraform import aws_lambda_function.orders orders-api
~~~

Importing does not automatically create complete desired configuration in HCL files. After importing, write or generate matching configuration, review the plan, and verify the state mapping.

Do not import the same object into multiple resource addresses in the same state unless explicitly supported by the provider model. Duplicate mappings can cause two resource blocks to fight over one object and produce unpredictable behavior.

## 15. Renaming, Moving, or Unmanaging Resources

IaC refactoring may rename resources or move them into a different module. Without declaring a migration, the tool may think the old resource should be destroyed and the new resource created.

### Moved Blocks

When changing a resource address while keeping the same live object, declare a `moved` block:

~~~hcl
moved {
  from = aws_lambda_function.orders
  to   = module.orders.aws_lambda_function.this
}
~~~

The tool uses this mapping to update the address in state instead of recreating the resource. Confirm that your Terraform/OpenTofu version supports the syntax and semantics.

### State Mv

The `state mv` command can move resource addresses in state:

~~~bash
terraform state mv \
  aws_lambda_function.orders \
  module.orders.aws_lambda_function.this
~~~

Perform this only after backing up state, locking deployments, and reviewing source/target addresses. For durable repository changes, `moved` blocks usually make migrations repeatable and reviewable alongside code.

### Unmanaging Without Deleting a Resource

Sometimes you want IaC to stop managing a resource while keeping the object in the cloud—for example, transferring ownership to another team or tool. Terraform supports `removed` blocks with `destroy = false` in compatible versions; `state rm` can also remove the mapping without calling the delete API.

~~~bash
terraform state rm aws_lambda_function.legacy
~~~

`state rm` only removes the resource from state; it does not delete the real resource. Afterward, if the resource block remains in code, plan will propose creating a new resource. Remove or adjust configuration and coordinate ownership before dropping the mapping.

Never use `state rm` to "fix" drift or make a resource disappear from plans. It is an ownership-mapping operation requiring review and auditing.

## 16. Useful State Commands and Safe Usage

| Command | Purpose | Notes |
|---|---|---|
| `terraform state list` | Lists resource addresses in state | Does not display full attribute values |
| `terraform state show ADDRESS` | Inspects resource attributes | May print secrets; avoid public logs |
| `terraform state pull` | Reads current state from backend | Sensitive output; use only in protected environments |
| `terraform state mv` | Moves a resource address in state | Back up and review mappings beforehand |
| `terraform state rm` | Removes mapping from state | Does not delete real resource; code with block may recreate it |
| `terraform import` | Imports an existing resource | Requires writing resource config and reviewing plan afterward |

Before any state-mutating operation:

1. Pause pipelines or notify the team to prevent concurrent applies.
2. Confirm backend, workspace, account, and Region.
3. Check locks and who holds the lock.
4. Create an encrypted, access-restricted state backup.
5. Record the resource address and object ID.
6. Perform a single tightly scoped operation.
7. Run plan and verify the mapping.
8. Log the audit trail and notify the team.

Never hand-edit state JSON as a routine practice. The state format carries schema, lineage, serial, and internal metadata; invalid edits can cause the tool to refuse reading it or mismanage resources.

## 17. State Backup and Recovery

A remote backend with versioning or state history enables recovery if state is corrupted or modified by mistake. Check:

- Is versioning enabled and is retention long enough?
- Are backups encrypted and read-protected?
- Can a prior version be restored without accidentally overwriting newer valid state?
- Who is authorized to restore and who approves?
- After restoring, how do you verify state matches real resources?

Basic recovery procedure:

1. Pause all pipelines capable of writing state.
2. Identify the backend key, workspace, and incident timestamp.
3. Download the current state and candidate backup versions to a secure location for comparison.
4. Identify which state version matches live infrastructure; do not blindly pick the oldest or newest file.
5. Restore using supported backend/tool mechanisms and retain an audit trail.
6. Run a plan refresh to check mappings against the provider.
7. Review every action before applying.
8. Re-enable pipelines once owners confirm.

Do not restore an old state backup blindly. If resources were created or deleted after the backup timestamp, restoring can break mappings. Reconcile provider IDs against real infrastructure before applying.

## 18. CI/CD for Plan Review and Apply

An IaC pipeline can be divided into two stages:

~~~mermaid
flowchart TD
    A[Pull request / commit] --> B[Format and validate]
    B --> C[Init and plan]
    C --> D[Publish protected plan artifact]
    D --> E[Review diff and policy checks]
    E --> F{Approved?}
    F -- No --> G[Revise or close change]
    F -- Yes --> H[Verify plan and state are current]
    H --> I[Apply reviewed plan]
    I --> J[Post-apply plan / verify]
    J --> K[Audit and monitoring]
~~~

Typical steps:

- Format and validate configuration.
- Pin provider/module versions and verify dependency lock files.
- Initialize the backend with an appropriate identity.
- Plan against the target environment/state.
- Run policy checks and security scans.
- Publish a protected plan artifact.
- Reviewers inspect actions and approve.
- Apply using an identity with only required permissions.
- Run post-apply verification and record an audit log.

### Separating Plan and Apply Permissions

Plan usually needs permissions to read state and read resource metadata from the provider. Apply additionally needs permissions to create/modify/delete resources. Different roles can be used so reviewers or plan pipelines cannot mutate production.

Even though planning may require reading state containing secrets, do not treat the plan role as harmless. Restrict backend read permissions and protect outputs/artifacts.

### Preventing Multiple Pipelines from Mutating One State

Use CI concurrency groups or locks to serialize applies per backend key. Multiple pull requests can run read-only plans, but before applying you must verify the plan is not stale and acquire the state lock cleanly. Another pipeline applying during review invalidates the old plan.

## 19. Specific Risks with Serverless Resources

When reviewing plans for serverless modules, pay close attention to high-impact resources:

| Resource/Field | Risk When Changed | Review Question |
|---|---|---|
| Function runtime/handler | Deployment failure or function fails to start | Is the artifact compatible with runtime and handler? |
| Memory/timeout | Latency, OOM, and cost changes | Have benchmarks and trigger timeout alignment been checked? |
| Reserved concurrency | Throttling or insufficient downstream protection | Does capacity match peak load and database limits? |
| Provisioned concurrency | Fixed cost and alias/version routing | Does traffic target the right qualifier and is capacity READY? |
| IAM role/policy | Privilege escalation or function loses access | Are least privilege and trust policies accurate? |
| Queue visibility/retry/DLQ | Duplicate messages, backlogs, or lost retry capability | Are timeout, max receive count, and poison queue compatible? |
| Event source mapping | Increases or decreases consumption rate | Have batching, parallelization, and partial failures been verified? |
| API Gateway route/authorizer | Misexposed endpoint or rejected clients | Are methods, auth, CORS, and throttling accurate? |
| Bucket/database replacement | Potential data loss | Are backups, retention, and migration plans in place? |
| Log retention/encryption | Increased cost or reduced investigative visibility | Does policy fit compliance and incident response? |

A plan might show a small HCL change while the provider must replace a resource or alter several dependent attributes. Always read action details and check provider documentation whenever replacement appears.

## 20. Automated Drift Detection and Alerting

You can run scheduled plans or post-change plans on sensitive stacks to detect drift. For example:

- CI runs a nightly read-only plan without applying.
- Cloud audit logs detect resources modified outside the pipeline.
- Policy engines compare critical security settings.
- Dashboards track drift count and age of unresolved drift.

A drift report should include:

- Environment/backend key and deployed commit.
- Resource address and resource ID.
- Changed field, desired value, and observed value (redacted).
- Detection timestamp and change source if known.
- Risk severity and responsible owner.
- Decision: revert, codify, intentionally ignore, or investigate further.

Never auto-apply immediately when drift detection finds a difference. A change could be a valid hotfix or autoscaling behavior. Alerting and review distinguish cases before acting.

### Intentional `ignore_changes`

Terraform lifecycle provides `ignore_changes` to ignore changes on attributes managed by another system. This is appropriate when ownership is clearly defined—for example, an autoscaler managing a resource's desired capacity.

Do not use `ignore_changes` to hide uninvestigated drift. Document the reason, ignored fields, field owner, and how changes to that field are monitored. If a critical attribute is ignored, ensure other telemetry or policies monitor it.

## 21. Common Mistakes

| Mistake | Consequence | How to Avoid |
|---|---|---|
| Committing state to Git | Secret exposure and state conflicts | Use a remote backend or protected storage |
| Assuming `sensitive` omits data from state | Credentials can remain in state/plan | Read provider schema and protect the backend |
| Using local state for production teams | Each person holds divergent mappings | Use remote backends and locking |
| Allowing concurrent pipeline applies | State overwrites or resource conflicts | Enforce locking and serialize applies |
| Force-unlocking without checking | Active apply loses coordination | Verify runner and lock owner first |
| Applying immediately on drift detection | Can overwrite hotfixes or cause outages | Classify and review the change source |
| Disabling refresh for a clean plan | Ignores real drift | Keep refresh enabled and resolve provider errors |
| Treating workspaces as a security boundary | Permissions and backend may still be shared | Separate accounts/backends/roles for sensitive environments |
| Skipping review of replacement/destroy | Data loss or downtime | Read detailed actions and require approval |
| Storing plan artifacts publicly | Sensitive data leaks | Protect and limit retention |
| Importing resources without writing config | Plan may propose large changes | Complete desired configuration and review |
| Using `state rm` to fix drift | Lost mappings and potential duplicate resources | Reserve for planned ownership migrations |
| Restoring old state backups without reconciliation | Mappings diverge from live resources | Reconcile IDs/providers and run plan before applying |
| Using `ignore_changes` to hide all drift | Loses visibility into unintended modifications | Ignore only fields with clear external ownership |

## 22. State Management and Change Review Checklist

Before applying IaC in production, confirm:

- **Backend:** state is stored durably in the environment-specific backend with appropriate backups/versioning.
- **Locking:** backend supports locking or equivalent serialization; no concurrent applies occur.
- **Encryption:** state and plans are encrypted in transit and at rest.
- **Access:** state read access is restricted; apply permissions are separated and audited.
- **Secrets:** no credentials committed; `sensitive` outputs are not mistaken for excluding secrets from state.
- **Isolation:** dev/staging/prod have separate state keys, identities, and permissions.
- **Drift:** plan refresh runs on a schedule or appropriate trigger; drift has owners and remediation procedures.
- **Review:** plans are reviewed per resource action, especially destroy, replacement, IAM, and data resources.
- **Plan artifact:** tied to commit and backend/workspace, protected, and verified non-stale before apply.
- **Import/refactor:** resource mappings are migrated via reviewed import/moved/state migrations.
- **Recovery:** state backups and recovery runbooks exist; JSON is never hand-edited.
- **Serverless impact:** runtime, memory, timeout, concurrency, IAM, triggers, queues, DLQs, and log retention are verified.
- **Post-apply:** post-deploy plan/verification runs and results are logged in audit records.

## 23. Conclusion

State is a high-value mapping that tells the IaC tool which resource in code corresponds to which cloud object. It must be stored durably, locked on writes, encrypted, backed up, and read-protected. Desired configuration, state, and real infrastructure are three distinct views; drift arises when they diverge.

A safe workflow refreshes and plans to detect discrepancies, verifies change sources, classifies drift, reviews actions, and only then applies. Saved plans ensure apply executes the exact reviewed changes, provided they are protected and checked for staleness. Import, `moved`, `state mv`, and `state rm` are ownership-mapping operations that require backups and auditing.

For serverless infrastructure, carefully review changes to IAM, runtime, memory, timeout, concurrency, queues, DLQs, API routes, and databases. When state is managed with discipline and every change passes through plan review, teams can deploy repeatably, catch configuration drift, and reduce operational risk.
