# Plan, Review, Apply, and Change Management Process

Infrastructure as Code (IaC) allows cloud infrastructure to be described in files that can be versioned, reviewed, tested, and deployed repeatedly. However, storing configurations in Git does not automatically make infrastructure changes safe. A small one-line edit can expose a database publicly, alter an IAM policy, delete storage, modify subnet routes, or disrupt multiple workloads. Therefore, IaC requires a controlled change process from initial proposal through execution and verification of real-world state.

A common workflow is **plan → review → approve → apply → verify**, paired with state management, drift detection, rollback/recovery, and evidence collection. Planning shows what the tooling intends to do; review checks impact and correctness; approval confirms an authorized person accepts the risk; apply executes the changes; and verification validates post-deployment infrastructure and records evidence. Every step needs clear identity, permissions, state, and traceability.

This lesson belongs to the **Infrastructure as Code** section of the Cloud Architecture curriculum. Its goal is to turn infrastructure changes into a repeatable, verifiable, and resilient process while balancing security, reliability, performance, cost, and delivery velocity under Well-Architected principles.

After this lesson, you will be able to:

- Describe the lifecycle of an IaC change from pull request to production.
- Read plans and classify creates, updates, replaces, deletes, and blast radius.
- Design code reviews, policy-as-code, tests, and approvals aligned with risk levels.
- Manage state, remote backends, locking, versioning, and access permissions.
- Detect, evaluate, and remediate configuration drift.
- Execute controlled applies using concurrency guards and safe deployment strategies.
- Handle failed changes with recovery plans rather than assuming rollbacks are always safe.
- Collect evidence and govern exceptions, emergency changes, and audits.

## 1. Lifecycle of an IaC change

An infrastructure change usually begins with a targeted request, such as creating a private endpoint for a database, scaling cluster capacity, or updating a workload identity policy. The request must translate into a reviewable diff, generate a plan against trustworthy state, and apply the exact approved artifact.

~~~mermaid
flowchart TD
    REQ["Change request / work item"] --> BR["Branch and IaC change"]
    BR --> TEST["Format, validate, tests"]
    TEST --> PLAN["Generate plan"]
    PLAN --> POLICY["Policy and risk evaluation"]
    POLICY --> REVIEW["Human review"]
    REVIEW --> APPROVE{"Approval granted?"}
    APPROVE -- "No" --> UPDATE["Revise or close"]
    UPDATE --> BR
    APPROVE -- "Yes" --> APPLY["Apply approved plan"]
    APPLY --> VERIFY["Post-apply verification"]
    VERIFY --> EVIDENCE["Record evidence and state"]
    EVIDENCE --> MONITOR["Monitor drift and runtime health"]
~~~

These stages do not need to live in separate systems. They can run inside a single CI/CD pipeline, provided boundaries of responsibility and state remain clear.

### Role of each step

| Step | Question to answer | Output |
| --- | --- | --- |
| Request | Why is the change needed, who is the owner, and which environment? | Change request, acceptance criteria |
| Code | What changed in the source of truth? | Commit, pull request, diff |
| Test | Is the configuration valid and policy-compliant? | Format, validation, test results |
| Plan | What resources does the provider intend to create/modify/delete? | Plan artifact |
| Review | Are the impact, blast radius, and risks acceptable? | Review comments, risk assessment |
| Approve | Who has authority to authorize the apply? | Approval record |
| Apply | Was the approved artifact applied successfully? | Apply result, run ID |
| Verify | Do runtime state and behavior meet requirements? | Health checks, smoke tests, evidence |
| Monitor | Is there drift, errors, or unexpected impact post-deploy? | Alerts, drift reports, follow-up |

### Core principles

- Plan and apply must belong to a single traceable change chain.
- Approvers must understand the plan and risks rather than rubber-stamping approvals.
- Apply must use a dedicated identity, least privilege, and clear environment scope.
- Only one process may write to state at a time per locking semantics.
- Out-of-band changes outside the pipeline must be detected and reconciled.
- A successful apply does not mean the application works correctly; post-deployment verification is mandatory.

## 2. Change requests and change preparation

A good pull request starts with a concrete objective. If the goal is merely "optimize cloud" or "fix network," reviewers cannot easily evaluate the outcome or risk level.

### Change request contents

Document:

- Business or technical objective.
- Relevant resources, modules, accounts/projects, regions, and environments.
- Current state and desired state.
- Impacted SLOs, security controls, or policies.
- Assumptions, dependencies, and prerequisites.
- Blast radius if an operation goes wrong.
- Maintenance window or downtime requirements.
- Verification plan, rollback/recovery plan, and point of contact.
- Expected cost and budget owner if the change has meaningful cost impact.

### Risk classification

| Level | Example | Recommended controls |
| --- | --- | --- |
| Low | Adding tags, descriptions, or dashboards without affecting permissions or traffic | Automated checks and standard review |
| Medium | Increasing capacity, adding replicas, modifying non-critical configs | Plan review, testing, owner approval |
| High | Changing IAM, network routes, encryption keys, or database topology | Security/platform review, explicit approval, staged apply |
| Very high | Deleting production data, changing serving regions, altering identity boundaries | Dual review, maintenance plan, backup/restore evidence, change window |

Risk classification should reflect real-world impact, not merely resource type. Deleting a sandbox resource may be low risk; changing a shared IAM role can impact many systems.

## 3. Plan: previewing changes

A plan is the analysis comparing desired configuration, managed state, and readable provider data. It previews proposed actions, typically including:

- **Create:** create a new resource.
- **Update in-place:** modify attributes without replacing the resource.
- **Replace:** delete the old resource and create a new one, or create-before-destroy per provider rules.
- **Delete:** remove a resource.
- **No-op:** no change needed under the current model.

### Reading a plan by impact

Do not just count changed lines. Inspect:

1. Which resources change and in which environment?
2. Which attributes change? Are they mutable or do they force replacement?
3. Does create/delete ordering cause downtime or data loss?
4. Do any IAM, network, public access, or security group changes widen permissions?
5. Do encryption, keys, backups, retention, or residency change?
6. Are dependent resources forced to recreate as a cascade?
7. Are there changes outside the scope of the request?
8. Does cost increase, decrease, or introduce new data transfer charges?

### Replacements requiring attention

A change may look like an update yet require replacement by the provider—for instance, altering an identifier attribute or a resource's subnet. For databases, volumes, or buckets holding state, replacement can cause downtime or data loss if lifecycles and migrations are not properly designed.

When a plan includes replace/delete on stateful resources, verify backups, snapshots, retention, data migration, and restore tests. Never approve solely because the tool reports a valid plan.

### Plans are point-in-time snapshots

A plan is generated from state at a specific point in time. If state, provider configuration, or external resources change before apply, the plan may no longer be valid. With tools supporting saved plans, store an immutable artifact and apply the exact reviewed artifact. If a plan becomes stale or cannot be safely applied, generate a new plan and review it again.

Never silently re-run a plan after approval and apply the new result. A fresh plan may introduce new changes and must go back through review per policy.

## 4. Code review and plan review

IaC review must examine both the code and the expected provider actions. The source diff explains intent; the plan shows concrete actions. The two perspectives complement each other.

### Source review

- Do modules/resources match the objective and follow proper abstractions?
- Are naming, tags, environment, and ownership consistent?
- Do input variables have validation and safe defaults?
- Are any secrets, key material, or credentials present in code or outputs?
- Are accounts, regions, CIDRs, or identities inappropriately hardcoded?
- Are dependencies, provider versions, and module versions pinned/controlled?
- Are tests or examples included for new interfaces?
- Were out-of-scope changes bundled into the same PR?

### Plan review

- Do created/modified/deleted resources align with the diff?
- Are there unexpected replacements or destroys?
- Do IAM policies introduce wildcards or privilege escalation?
- Does networking expose public endpoints or open broad ports?
- Do databases/storage change encryption, retention, or backups?
- Are DNS, routing, load balancers, or endpoints affected?
- Does the blast radius cross services, accounts, or regions?
- Are cost estimates and capacity reasonable?

### CODEOWNERS and required reviewers

Require approvals from module or control owners. For example, network changes require platform/network owners; sensitive IAM changes require security review; database state changes require data/platform owners. Code merge permissions and production apply permissions should be separated under separation of duties.

### Review comments must be actionable

Instead of "looks risky," reviewers should specify the resource, attribute, impact, and prerequisites for approval. For example: "The plan modifies the database subnet group and recreates the instance; attach migration/restore evidence and a maintenance plan before applying."

## 5. Testing before plan/apply

Static and automated checks catch issues early, though they do not replace plan review or runtime verification.

| Check layer | Example | Catches |
| --- | --- | --- |
| Format/lint | Formatter, linter | Syntax errors, style issues, and risky patterns |
| Validate | IaC validate / provider schema | Invalid configurations, missing inputs |
| Unit/module test | Testing locals, naming, outputs, and module logic | Locally testable logic errors |
| Static security scan | Misconfiguration scan, secret scan | Public resources, missing encryption, exposed secrets |
| Policy-as-code | Region, tag, IAM, network, and backup rules | Violations of organizational guardrails |
| Integration test | Ephemeral environment deployment | Real provider/module interactions |
| Plan review | Plan artifact | Actual impact on target workspace/environment |
| Post-apply test | Smoke tests, API/connectivity checks | Resources not functioning as intended |

### Unit tests and integration tests

Unit tests suit logic that does not require calling real providers. Integration tests should run in dedicated sandboxes using test data and restricted identities. Ensure test pipelines can never accidentally apply against production or delete out-of-scope resources.

### Policy-as-code

Policies can block public databases, unencrypted resources, disallowed regions, IAM wildcards, or production resources missing owner tags. Policies should define:

- Exact scope and resource types.
- Severity and deny/warn/audit behavior.
- Business rationale and remediation guidance.
- Version, owner, and review cadence.
- Time-bound exception mechanisms.
- Positive/negative tests to prevent false positives.

Illustrative pseudocode:

~~~text
deny if environment == "production"
     and resource.type == "database"
     and resource.public_access == true

deny if resource.data_classification == "restricted"
     and resource.encryption_at_rest != true

require if resource.environment == "production"
     then resource.owner != ""
      and resource.backup_policy != ""
~~~

This is illustrative logic, not syntax for any specific policy engine.

## 6. Approval and separation of duties

Approval confirms an authorized person has reviewed the objective, plan, risks, and evidence before changes execute. A single identity should not author code, self-approve, and apply high-risk production changes without additional controls.

### Approval rules

- PRs require reviewers per CODEOWNERS or risk classification.
- Production applies require approval separate from merge permissions when dictated by risk.
- Changes involving IAM, networking, or data destruction require specialist reviewers.
- Approvals bind to a specific commit and plan artifact.
- If a plan becomes stale, the source commit changes, or policy versions change, approvals should invalidate.
- Emergency changes follow a streamlined path with logged justification and retrospective review.

### Sample role matrix

| Role | Primary permissions | Should not have by default |
| --- | --- | --- |
| Developer | Edit modules and open PRs | Production apply credentials |
| Reviewer | Review source/plans within scope | Modifying an already-approved plan |
| Platform owner | Review topology, providers, state, and capacity | Reading unrelated business data |
| Security reviewer | Approve IAM/network/encryption controls | Applying arbitrary resources |
| Release approver | Approve production changes | Editing source after approval |
| CI/CD apply identity | Apply artifacts in assigned workspace/environment | Account-wide admin if unnecessary |
| Auditor | Read-only evidence access | Modifying state, logs, or approval records |

In smaller organizations, one person may hold multiple roles, provided compensating controls exist such as dual approval, signed artifacts, immutable logs, or post-deployment reviews.

## 7. State, remote backends, and locking

IaC state maps declared code to real resources. In Terraform-like tools, state can hold resource identifiers, attributes, and occasionally sensitive data. Treat state as a critical asset requiring protection equal to or stricter than the managed infrastructure itself.

### Remote state

In teams, state typically lives in a remote backend shared by engineers and CI/CD. Backends require:

- Authentication via workload identity or short-lived credentials.
- Encryption at rest and in transit.
- Access control scoped by project/workspace/environment.
- Versioning or recovery mechanisms.
- Access/change auditing and appropriate backups.
- Controlled network paths.
- No public state objects or exposed sensitive outputs.

Never store state in public Git repos or pass state files over chat/tickets. State can contain secrets even when outputs are marked `sensitive`.

### Locking

Locking prevents two processes from modifying a workspace's state simultaneously and causing races or corruption. Pipelines should fail cleanly if they cannot acquire a lock; never delete a lock manually just because a job is waiting. Before running `force-unlock`, confirm the lock-holding process has terminated and no apply is still in progress.

### Workspaces and state isolation

Split state by environment, account, region, or domain so blast radius and access privileges remain sensible. One giant state slows down planning and couples unrelated changes; too many tiny states increase operational overhead. Draw boundaries based on lifecycle, ownership, and failure domain.

### State backup and recovery

Before state-sensitive operations or tool/provider upgrades, ensure the backend has versioning/backups and a tested recovery procedure. Never hand-edit state except through verified repair workflows. Restoring state from the wrong point in time can trick the tool into thinking live resources are missing or managing the wrong resources.

## 8. Providers, modules, and dependency versions

Reproducible plans require controlling versions of the IaC engine, providers, and modules. Fetching `latest` on every run can cause the same commit to produce different plans due to schema or behavior changes.

### Version management

- Pin providers using tested version constraints.
- Use lock files to record provider selections and checksums where supported.
- Pin module sources/tags/commits per policy.
- Upgrade versions in dedicated PRs with tests and plan reviews.
- Read release notes, breaking changes, and migration guides.
- Test provider upgrades in sandboxes before production.

### Dependency graph

Resources may depend on networking, IAM, keys, databases, DNS, or certificates. Incorrect creation/deletion ordering can break deployments or delete an in-use dependency. Prefer explicit dependencies and stable module interfaces; avoid implicit dependencies relying on naming conventions or timing.

Do not split modules merely to increase file count. Module boundaries should reflect ownership, lifecycles, and reusable interfaces.

## 9. Apply: executing the exact approved change

Apply is the step that mutates real cloud resources. It requires the right identity, workspace, provider context, commit, and plan artifact.

### Pre-apply checks

- Source commit matches the approved commit.
- Plan artifact is still valid and untampered.
- Target workspace/account/region/environment is correct.
- State lock is acquired.
- Approval remains valid and bound to the exact artifact.
- Apply credentials/identity match the scope and have not expired.
- Maintenance window and dependencies are ready.
- No concurrent out-of-band changes are underway.

### Saved plans

With tools supporting saved plans, pipelines generate a plan artifact, route it for review, and apply that exact artifact. This reduces the risk of reviewers inspecting one plan while CI executes another. Plan files can also contain sensitive data; protect the artifact store, enforce short retention, and restrict download access.

### Concurrency control

Prevent two pipelines from applying to the same workspace or overlapping resource scope simultaneously. Use environment concurrency groups alongside backend locks. State locks do not necessarily block console actions or systems outside IaC; coordinate change windows and check for drift.

### Phased applies

Large changes can be broken into phases:

1. Create new dependencies such as IAM, networking, or keys.
2. Provision target resources and verify health.
3. Shift traffic or data flows.
4. Observe and reconcile.
5. Delete legacy resources once the rollback window closes.

Do not bundle all destructive actions into a single apply when they can be staged to reduce blast radius.

## 10. Safe change rollout strategies

Not every resource calls for the same apply pattern.

| Strategy | Approach | Best suited for | Prerequisites |
| --- | --- | --- | --- |
| Small batch | Apply small groups of changes | Well-scoped changes | Independent plans and easy verification |
| Staged rollout | Roll out sequentially by environment/region | Changes verifiable incrementally | Health gates and rollback/recovery plans |
| Blue/green | Build new environment, verify, then switch traffic | Gateways, service clusters, certain managed resources | Data/schema compatibility and cutover plan |
| Canary | Shift a fraction of traffic or resource subset to new config | Workloads supporting segmentation | Automated metrics/thresholds and clear owners |
| Expand/contract | Add backward-compatible schema/config first, then remove old | Database schemas, APIs, IAM migrations | Compatibility phase maintained long enough |
| Maintenance window | Apply changes with planned downtime | Changes that cannot roll out gradually | Owner, notifications, backups, and recovery |

Infrastructure apply alone does not create canary behavior for every resource type. Check what the provider/resource supports and design at the traffic/application layer when needed.

### Expand/contract for schema changes

For example, renaming a field or migrating a database:

1. Expand: add the new field/table or target while preserving compatibility with old code.
2. Controlled dual-write/CDC if needed, with consistency/reconciliation checks.
3. Migrate/backfill and validate.
4. Cut over readers incrementally.
5. Monitor through the rollback window.
6. Contract: remove the old field/resource once zero consumers remain.

Never drop columns or endpoints before all consumers have stopped depending on them.

## 11. Post-apply verification

A successful apply only tells you the tool/provider completed API calls. It does not prove the application, security controls, or SLOs are met.

### Verification levels

| Layer | Checks |
| --- | --- |
| Resource | Resources exist with expected status and attributes |
| Network/security | Public exposure, routes, IAM, TLS, and security policies are correct |
| Application | Health checks, connectivity, request/response behavior, and smoke tests |
| Data | Schema, integrity, row counts, replication, and backups |
| Reliability | Failover/health, alerts, autoscaling, and recovery behavior |
| Cost | Capacity/tier/replicas and post-change cost estimates |
| Governance | Tags, owners, regions, audit logs, and updated evidence |

### Post-apply evidence

Record:

- Change request/PR/commit ID.
- Plan artifact hash or identifier.
- Approver and timestamp.
- Apply run ID, identity, and workspace.
- Provider/resource execution results.
- Smoke test and control verification results.
- Post-deployment drift/health scan results.
- Open exceptions or follow-up action items.

Never include secrets, raw state, or credentials inside evidence packages.

## 12. Drift detection and reconciliation

Drift is the divergence between desired IaC configuration and real-world state. Drift can stem from console edits, emergency fixes, policy automation, provider defaults, unmanaged resources, or service-managed updates.

### Types of drift

- **Configuration drift:** resource attributes differ from code/state.
- **Unmanaged resource:** a resource created outside IaC within a managed scope.
- **State drift:** state no longer accurately reflects live resources.
- **Dependency drift:** providers, modules, versions, or policies changed.
- **Data/config drift:** runtime data/configs modified outside IaC mechanisms.

### Detecting drift

- Scheduled plan/refresh jobs or cloud configuration scans.
- IaC state refreshes and comparative plans.
- Cloud asset inventory/configuration services.
- Policy-as-code and drift alerts.
- Audit logs tracking console/API changes.

### Handling drift

Not every drift should be overwritten automatically.

1. Identify who/what made the change and why.
2. Determine whether it is an emergency fix, a provider-managed field, or an unauthorized change.
3. Assess impact and whether an incident/change record is required.
4. Choose one of three paths: update code to adopt drift, revert runtime back to code, or import/adopt the resource into IaC.
5. Generate a new plan and review the impact before applying.
6. Record evidence, update inventory, and close the finding.

### Intentional ignore changes

Attributes managed dynamically by autoscalers or control planes may need to be ignored in IaC. However, overly broad ignores mask real drift. Every ignored attribute requires an owner, rationale, narrow scope, tests, and periodic review; never use ignores merely to force a green plan without understanding the underlying difference.

## 13. Rollback, recovery, and destructive changes

Infrastructure rollback is not like application code rollback. Resources may have been deleted, data schemas altered, keys rotated, or new data written. Reverting code to an older commit does not automatically restore prior state.

### Distinguishing rollback from recovery

- **Rollback:** reverting configuration/code to a pre-change version.
- **Recovery:** restoring services/data using backups, snapshots, restores, recreation, or failover.
- **Forward fix:** issuing a new change to fix an issue when rolling back is unsafe or impossible.

### Before destructive changes

- Check resource lifecycle settings and deletion protection.
- Take backups/snapshots and test restores where appropriate.
- Identify resource replacements and expected downtime.
- Verify dependencies and consumers.
- Confirm RPO/RTO and data migration plans.
- Ensure authorized operators and recovery runbooks are ready.
- Identify the point of no return—for example, once new production writes occur.

### Terraform-like lifecycle controls

Some IaC tools offer lifecycle flags such as `prevent_destroy`, `create_before_destroy`, or `ignore_changes`. These reduce risk but do not replace process:

- `prevent_destroy` can block legitimate maintenance unless a guard-removal plan exists.
- `create_before_destroy` requires naming and resource quotas that allow coexistence.
- `ignore_changes` can mask drift or hide security regressions.
- Replacements can still cause downtime if resource identities or provider semantics do not support side-by-side existence.

Use lifecycle settings only when you understand provider behavior and have tested failure paths.

## 14. Emergency changes and break-glass

Production incidents may require rapid fixes outside normal workflows. The goal is to enable timely remediation while still protecting state, identities, and audit trails.

### Emergency workflow

1. Identify the incident commander/owner authorized to make decisions.
2. Document rationale, scope, expected effect, and risks.
3. Use MFA-protected, time-bound break-glass credentials.
4. Limit changes to the minimum needed to stabilize the service.
5. Record all CLI/API changes, identity, timestamps, and resources.
6. Verify outcomes and monitor service health.
7. Open a PR for IaC reconciliation immediately once stable.
8. Conduct a post-incident review, revoke temporary access, and close exceptions.

### Out-of-band console changes

If an incident is mitigated directly via the console, do not leave runtime and code diverged for long. Decide afterward whether to preserve the fix in IaC or revert to source configuration. Never run a blind apply that could overwrite an emergency fix or cause another outage.

## 15. Protecting pipelines and apply identities

Pipelines authorized to modify production infrastructure are a critical security boundary.

### Workload identities

- Use federation/workload identities or short-lived credentials instead of long-lived access keys.
- Separate identities by environment, account, and pipeline job.
- Grant only the resource/action permissions required by the module/workspace.
- Restrict permissions to create IAM roles, attach policies, open public networks, or manage keys.
- Never allow untrusted contributors to edit pipeline definitions and execute with production credentials.

### Pipeline protection

- Branch protection and required reviews.
- Protected environment approvals.
- Pin action/plugin/provider versions and enforce supply chain controls.
- Secret scanning and dependency vulnerability scanning.
- Run applies only from trusted branches/artifacts.
- Store plan/apply artifacts in access-controlled, integrity-protected storage.
- Audit workflow modifications and permission changes.

### State and plan artifacts

State and plans can contain sensitive data. Protect storage, encryption, downloads, retention, access controls, and logs. Never print full state or plans to CI logs or attach raw files to public tickets.

## 16. Managing changes across environments and dependencies

A sound workflow progresses from lower-risk environments toward production.

### Promotion flow

~~~mermaid
flowchart LR
    DEV["Development"] --> TEST["Integration / Test"]
    TEST --> STAGE["Staging"]
    STAGE --> PROD["Production"]
    DEV -. "Same reviewed source" .-> TEST
    TEST -. "Promoted artifact/config" .-> STAGE
    STAGE -. "Approved plan for prod" .-> PROD
~~~

Distinguish code promotion from plan promotion. A staging plan cannot simply be applied to production because resources, state, accounts, regions, and policies differ. Each environment requires its own plan and risk-appropriate approval while keeping the source commit/module version consistent.

### Dependency ordering

Deployments typically follow this order:

1. Accounts/projects, baseline identities, and policies.
2. Networking, DNS, keys, and shared platform services.
3. Data, compute, and service resources.
4. Routing, access bindings, and integrations.
5. Traffic cutover and cleanup.

Exact ordering varies by system. During teardown, consumers/dependencies usually must be removed before deleting foundations, verified against the provider dependency graph.

## 17. Cost, capacity, and blast radius in reviews

IaC review is not just syntax review. Infrastructure can be technically valid yet prohibitively expensive, under-provisioned, or overly coupled in failure impact.

### Cost review

- Instance types/tiers/replica counts and autoscaling bounds.
- Storage, IOPS, backups, snapshots, and retention.
- NAT gateways, load balancers, private endpoints, and network egress.
- Cross-zone/cross-region transfer and replication.
- Log/metric ingestion volume and retention.
- Licensing/support costs and idle resources.
- Tagging, cost allocation, and budget alerts.

### Capacity review

- Peak traffic and headroom.
- Connection limits and downstream quotas.
- Remaining capacity if a node, zone, or region fails.
- Autoscaling warm-up and scale-in behavior.
- Provider quotas and service limits.

### Blast radius

Estimate how many services, tenants, regions, and data classifications could be affected by a flawed plan or interrupted apply. Split states/workspaces/modules along sensible failure domains and roll out wide changes in stages.

## 18. Evidence, auditing, and exception governance

A change record should link request, code, plan, review, approval, apply, and verification. Evidence must answer who changed what, why, on which scope, who approved it, and what the outcome was.

### Minimum evidence package

| Evidence | Contents |
| --- | --- |
| Request | Objective, owner, scope, risk |
| Source | PR, commit, module/provider versions |
| Tests | Lint, validate, security/policy scans |
| Plan | Artifact ID/hash, action summary, plan timestamp |
| Review | Reviewers, comments, risk decision |
| Approval | Approver, timestamp, environment, artifact reference |
| Apply | Run ID, identity, workspace, outcome |
| Verification | Health, security, smoke, data, and cost checks |
| Follow-up | Drift status, issues, exceptions, remediation |

### Exceptions

When a policy cannot be satisfied immediately, an exception requires:

- Affected control/policy and resources.
- Rationale, risk, and impact.
- Compensating controls.
- Owner and authorized risk acceptor.
- Expiry date, review cadence, and remediation plan.
- Automated alerting or revocation triggers.

Never grant permanent exceptions or track them only in PR comments. Upon expiry, they must be remediated or formally re-approved per policy.

## 19. Practical example: migrating a database to private connectivity

**Scenario:** A cloud application uses a managed relational database with a legacy network configuration. The platform team needs to move the database into private subnets and restrict clients solely to the application security group. Production carries live traffic; the change can affect the API, workers, migration jobs, and support tools. This is a simulated example.

### Change request

- Objective: eliminate public exposure on the database; allow connections only from approved workloads.
- Scope: production VPC, subnet group, security groups, routes, and database endpoint.
- Risk: dropped connectivity from workers/migration jobs or endpoint changes.
- Acceptance: applications/workers connect via the private path; public connections fail; latency and error rates stay within SLO.

### Plan review

Review checks:

- Will the database be replaced or restarted?
- Does the subnet group span sufficient zones and capacity?
- Does the DNS endpoint remain unchanged?
- Do security groups allow the right ports from the right sources?
- Do out-of-cluster jobs require routes or a private DNS resolver?
- Are Terraform state and the provider plan up to date?
- Are there new endpoint, NAT, or data transfer charges?

### Apply strategy

1. Provision/configure private networking and routes first.
2. Grant permissions and security groups for application, worker, and migration identities.
3. Verify connectivity from every workload in staging.
4. Generate the production plan and review it again.
5. Apply within a maintenance window if the provider requires a restart or cutover.
6. Run smoke tests, query checks, and verify public access is blocked.
7. Monitor error rates, connection pools, and audit logs.
8. Remove the legacy public path after verifying all consumers.

### Recovery

If applications fail to connect, inspect routes, DNS, security groups, and identities before reverting. If the legacy path must be temporarily re-opened, use a time-bound emergency exception with auditing and automatic revocation criteria. Never open the database to the entire internet as a stopgap.

## 20. Hands-on exercise: building a plan-review-apply pipeline

**Scenario:** A team manages infrastructure for an e-commerce platform with IaC. The repository contains network, database, compute, and observability modules. The pipeline generates plans automatically on pull requests and applies once approved. Some changes impact IAM, databases, and public endpoints. This is a simulated scenario.

### Tasks

1. **Design the workflow:** describe PR, validation, plan, policy, review, approval, apply, and post-apply verification.
2. **Design plan review:** define create/update/replace/delete risk classifications, especially for stateful resources and IAM/networking.
3. **Design state:** remote backend, encryption, locking, versioning, backups, workspaces, and permission boundaries.
4. **Design identities:** environment-specific apply identities, workload federation, least privilege, and protected environments.
5. **Design policy gates:** block public databases, missing encryption, IAM wildcards, out-of-scope regions, and ownerless resources.
6. **Design drift handling:** detect console edits, distinguish emergency drift from unauthorized changes, and define reconciliation workflows.
7. **Design recovery:** backups, destructive plan approvals, staged applies, rollback/forward-fix procedures, and restore drills.
8. **Design evidence:** connect change requests, commits, plans, approvers, apply runs, and verification.

### Test matrix

| Test | Scenario | Required evidence |
| --- | --- | --- |
| Unexpected destroy | PR accidentally deletes the database | Policy/review gate blocks or requires senior approval |
| IAM escalation | Policy adds wildcard permissions | Security scan/policy test fails |
| Public exposure | Database endpoint switched to public | Pre-deploy policy rejects |
| State concurrency | Two applies target the same workspace | Lock/concurrency group prevents concurrent writes |
| Stale plan | State/resources change after planning | Apply rejects and requires re-plan/review |
| Drift | Security group modified in console | Drift scan raises finding and triggers reconciliation |
| Failed apply | Provider fails mid-apply | Consistent state, clear runbook, and retry/recovery |
| Secret leak | State/plan contains sensitive output | Artifact access/retention and log masking protect data |
| Approval mismatch | Commit changes after approval | Approval invalidates or pipeline blocks |
| Post-apply failure | Resources created but app health fails | Roll-forward/recovery executed per runbook |
| Emergency change | Break-glass modifies network | Audit, expiry, IaC reconciliation, and review |
| Cost regression | Unexpected replica or storage increase | Cost/policy gate warns prior to apply |

### Deliverables

- Pipeline diagram and state transitions.
- Change request template and risk classification.
- Source and plan review checklists.
- State/backend/locking/access design.
- Policy-as-code rules and test cases.
- Approval/separation-of-duties matrix.
- Apply, verification, rollback/recovery, and drift runbooks.
- Evidence package schema and exception register.
- ADR documenting trade-offs, owners, and revisit triggers.

## 21. Well-Architected assessment

| Pillar | Questions for the IaC workflow |
| --- | --- |
| **Operational Excellence** | Are change flows, owners, approvals, evidence, runbooks, and drift reconciliation consistent? |
| **Security** | Are pipeline identities, state, plan artifacts, secrets, IAM reviews, and separation of duties protected? |
| **Reliability** | Have locking, stale-plan checks, staged applies, backups, restores, and recovery been tested? |
| **Performance Efficiency** | Do plan/apply execution, module graphs, resource sizing, and rollouts support delivery/performance without overload risks? |
| **Cost Optimization** | Does plan review account for compute, storage, network, backups, replicas, and operational overhead? |
| **Sustainability** | Are redundant resources, uncleaned ephemeral environments, and excessive log/plan retention avoided? |

## 22. Common mistakes

**Applying directly from any branch.** Lacks source review, plan review, or artifact-bound approval.

**Approving code without inspecting the plan.** Providers may require replace/delete actions different from what reviewers infer from the diff.

**Applying a plan different from the approved plan.** Artifact mismatch defeats the purpose of approval.

**Running two concurrent applies.** Can corrupt state or create race conditions across resources.

**Treating state/plans like ordinary files.** They can hold identifiers and sensitive data; require encryption, access controls, and retention limits.

**Granting CI/CD account-wide admin permissions.** A compromised pipeline can create out-of-scope privileges or resources.

**Treating a green plan as proof of healthy runtime.** Infrastructure can provision cleanly while applications fail to connect or security controls fail.

**Auto-approving all production changes.** Destructive, IAM, and network changes require risk-based controls.

**Rolling back by reverting commits without considering data.** Schemas, stateful resources, and rotated keys may be incompatible with older configurations.

**Ignoring drift because IaC is in use.** Console edits or policy automation can still cause runtime to diverge from code.

**Overly broad `ignore_changes`.** Real drift and security regressions can be masked.

**Skipping reconciliation after emergency changes.** Runtime and the source of truth remain diverged indefinitely.

**Failing to retain evidence.** Makes it impossible to prove who approved what, which artifact ran, and whether post-deploy checks passed.

## 23. Checklist before applying production IaC changes

- [ ] Change request includes objective, owner, scope, risk, and acceptance criteria.
- [ ] Source diff is versioned, reviewed, and bound to an immutable commit.
- [ ] Format, validate, module tests, secret/security scans, and policy tests pass.
- [ ] Plan is generated from the right state/backend with timestamp and artifact ID.
- [ ] Create/update/replace/delete actions and blast radius are analyzed.
- [ ] Stateful/destructive changes have backup, restore/migration, and recovery evidence.
- [ ] Reviewers examine both source and plan; domain owners are required based on risk.
- [ ] Approval binds to the exact commit/plan/environment and invalidates if artifacts change.
- [ ] Apply identity uses workload identity or short-lived credentials with least privilege.
- [ ] Remote state is encrypted, access-controlled, versioned, and locked.
- [ ] Concurrency guards prevent simultaneous applies within the same scope.
- [ ] Provider/module versions are controlled and upgraded with testing.
- [ ] Apply executes the exact approved plan artifact.
- [ ] Large changes are phased with maintenance and cutover plans.
- [ ] Post-apply checks verify resources, networking, security, application, data, reliability, and cost.
- [ ] Drift detection and reconciliation have owners, cadences, and runbooks.
- [ ] Rollback and recovery are clearly distinguished; points of no return are known.
- [ ] Emergency changes have break-glass controls, auditing, expiry, and IaC reconciliation.
- [ ] Evidence links request, source, tests, plan, review, approval, apply, and verification.
- [ ] Exceptions have risk owners, compensating controls, expiry, and remediation plans.

The plan, review, apply, and change management workflow turns IaC from raw configuration files into a controllable infrastructure operating model. Planning reveals expected impact; review and approval evaluate risk; apply executes the exact approved artifact; and verification plus drift monitoring confirm real-world state. State, identity, locking, evidence, and recovery form the core of the process. A change is only truly complete when infrastructure meets its objective, controls remain intact, and the organization can trace and recover if anything goes wrong.
