# State Management, Concurrency Locking, and State Recovery

Infrastructure as Code (IaC) describes desired infrastructure in code, and tooling compares that description against real-world resources to generate a plan of changes. To know which resource in the configuration corresponds to which existing resource, the tool must maintain metadata about previous deployments. In Terraform/OpenTofu, this metadata is stored in **state**.

State typically holds the mapping between a resource address in the configuration and the real resource identifier, along with attributes read from the provider. It helps the tool determine which resources to create, update, replace, or delete. Consequently, state is a critical component of the infrastructure management system. If multiple operators write to state simultaneously, if state is lost, overwritten with an older version, or exposed, the impact can directly hit production.

This lesson belongs to the **Infrastructure as Code** chapter of the **CLOUD_ARCHITECTURE** module. Its goal is to design how state is stored and protected, control concurrent runs, handle drift, and back up and recover state—while understanding the trade-offs across reliability, security, cost, and operations in the IaC workflow.

## 1. What is state and why must it be managed?

State is administrative data used by the IaC engine to track managed resources and link them to real infrastructure. State is neither the desired configuration nor a complete backup of a cloud account.

For example, a configuration declares a bucket with the logical name `uploads`. When apply succeeds, the provider creates a bucket with a concrete resource ID. State records the binding from that module resource address to the bucket's ID and metadata.

~~~mermaid
flowchart LR
    CFG["IaC configuration"] --> PLAN["Plan engine"]
    ST[("State snapshot")] --> PLAN
    LIVE["Real cloud resources"] --> REFRESH["Provider refresh / read"]
    REFRESH --> PLAN
    PLAN --> DIFF["Proposed changes"]
    DIFF --> APPLY["Apply"]
    APPLY --> LIVE
    APPLY --> ST
~~~

Without proper state, the engine cannot reliably tell which resources are already managed, what ID a real resource has, or whether a new configuration represents a brand-new resource or intends to manage an existing one.

### 1.1. What does state solve?

- **Resource mapping:** binds a configuration resource address to a provider ID.
- **Dependency metadata:** assists in determining relationships and operation ordering across resources.
- **Attribute tracking:** stores known attributes to compute diffs.
- **Module/resource addressing:** stores instance, module path, index, or key information.
- **Provider association:** tracks which provider/configuration manages each resource.
- **Outputs:** stores output values so other modules or workflows can reference them.
- **Sensitive values:** in many cases can contain sensitive values, even when outputs are marked sensitive.

State does not replace source code, variable files, a secret manager, a cloud inventory, or database backups. Treat state as operationally and security-critical metadata.

### 1.2. State is not the sole source of truth

Three perspectives must be compared:
1. **Configuration:** what the team wants the system to be.
2. **State:** what the IaC engine currently records as under management.
3. **Real infrastructure:** what the provider actually has right now.

These three perspectives can diverge. An admin may edit settings directly in the console; state still holds the old configuration. A restored state may reference resources that were already deleted. A new configuration may no longer include a resource still tracked in state.

Therefore, state must be checked alongside provider inventory, plans, refreshes, and change control processes. Never edit state just to make a plan look clean without understanding the real resources.

## 2. Resource addressing structure and mapping

In Terraform/OpenTofu, state references resource addresses including module path, resource type/name, and instance key/index.

Illustrative example:

~~~hcl
resource "aws_s3_bucket" "uploads" {
  bucket = "booking-uploads-prod"
}

module "network" {
  source = "./modules/network"
}
~~~

Addresses can take forms such as:
- `aws_s3_bucket.uploads`
- `module.network.aws_vpc.main`
- `aws_instance.worker[0]`
- `aws_instance.worker["batch-a"]`

The address name in configuration is a logical identifier. The provider resource ID is the real resource identifier. The two are not the same.

### 2.1. Renaming a resource does not have to recreate the resource

If an address changes in configuration without telling the engine it is the same resource, the plan may propose destroying the old address and creating the new one. For critical resources, this behavior can cause downtime or data loss.

Use the address-refactoring mechanism supported by your tool version—such as `moved` blocks or `state mv` commands—following a tested workflow. After the change, review the plan to confirm the engine recognizes a mapping move rather than a resource replacement.

### 2.2. One state or multiple states?

A single large state managing many components creates a large blast radius and forces multiple teams to share a lock. Multiple smaller states reduce change scope and clarify ownership, but increase dependency management and coordination effort.

| Organization model | Advantages | Risks |
|---|---|---|
| One state for the whole environment | In-state dependencies are easy to express | Lock contention, large plans, wide blast radius and broad permissions |
| State by domain/workload | Focused ownership and changes | Must manage outputs/remote dependencies |
| State by environment | Isolates dev/stage/prod | Must keep configurations and versions consistent |
| State by region | Aligns ownership and failure domains by region | Must coordinate global resources and shared services |
| State by team | Separates permissions and operational lifecycles | Can split a logical dependency chain across multiple states |

Do not split state purely by resource count. Choose boundaries based on ownership, lifecycle, access permissions, rate of change, dependencies, and blast radius.

## 3. Local state vs. remote state

### 3.1. Local state

By default or in simple setups, state may be stored in a local file inside the working directory.

Advantages:
- Easy to start and experiment with.
- No separate backend service required.
- Suitable for individual labs or throwaway environments.

Limitations:
- Cannot be shared safely across multiple people or machines.
- Easily lost if a laptop fails or a workspace is deleted.
- No centralized locking unless another mechanism is added to the workflow.
- Easy to accidentally commit to Git.
- Hard to audit and apply standard backup/retention policies.

Do not use local state as the default for team production workflows. Do not commit state into a repository as a substitute for a remote backend; state can contain secrets and sensitive metadata.

### 3.2. Remote state

A remote backend stores state in a shared service capable of enforcing access control, versioning, encryption, logging, and locking according to the backend/tool's capabilities.

Common options include:
- Object storage with versioning and a backend-supported locking mechanism.
- Terraform Cloud/HCP Terraform or equivalent state management platforms.
- HTTP backends or dedicated state services.
- Other cloud-native backends depending on engine and provider versions.

Benefits:
- A single shared state accessed under controls across runners.
- Can support locking and concurrency control.
- Can use IAM/workload identity for access control.
- Can integrate encryption, audit logs, versioning, and backups.
- Reduces the risk of state living solely on an individual's machine.

A remote backend still requires deliberate design. Object storage alone does not guarantee safe locking; versioning does not prevent two writers from overwriting each other concurrently; encryption does not replace authorization.

### 3.3. Typical remote state architecture

~~~mermaid
flowchart TB
    DEV["Developer / CI runner"] --> AUTH["Workload identity / IAM"]
    AUTH --> LOCK["Backend lock"]
    LOCK --> STORE[("Remote state storage")]
    STORE --> VER[("Version history / backup")]
    DEV --> CLOUD["Cloud provider APIs"]
    CLOUD --> LIVE["Managed resources"]
    STORE -. "State metadata" .-> DEV
~~~

The runner must authenticate to the backend, acquire the lock, read state, perform refresh/plan/apply, and write the new snapshot once the operation completes according to backend semantics. Backend permissions and provider permissions are two separate scopes; both must be controlled.

## 4. Backends, workspaces, and environment isolation

Do not mistake a workspace for a complete security boundary. Terraform workspaces can create multiple state instances for the same configuration and backend, but backend access permissions, credentials, networking, and policies still govern who can read or write.

Production environments should typically enforce clear isolation:
- Separate backends or namespaces per environment.
- Dedicated IAM roles for dev/stage/prod.
- Distinct, non-overlapping state keys/prefixes with clear naming.
- Production pipelines with approvals and protected branches.
- No casual sharing of secrets or provider credentials.
- Policies preventing non-prod runners from writing prod state.

A workspace labeled `prod` does not automatically protect production. If the same credential has write access to every state, name-based isolation is insufficient.

### 4.1. Rules for choosing state boundaries

Ask:
- Who owns the resources?
- Which resources must change together in a single operation?
- Is atomicity required between resources?
- Do states hold different levels of sensitive data?
- Which groups need read/write permissions?
- How many workloads could a failed apply impact?
- Does the state need independent recovery?
- Can dependencies be passed via outputs/APIs instead of sharing a state?

Splitting state generally increases independence at the cost of losing atomic plans across states. Pipeline processes must define apply ordering and compatibility checks between producers and consumers.

## 5. State locking and concurrent runs

When two runners read the same state version and apply concurrently, both may compute plans from the same stale snapshot. The resulting writes can overwrite or lose the other runner's updates.

**State locking** prevents multiple operations from writing to state simultaneously where supported by the backend/mechanism. When one operation holds the lock, other operations must wait or fail cleanly.

~~~mermaid
sequenceDiagram
    participant R1 as Runner A
    participant L as Lock service
    participant S as Remote state
    participant R2 as Runner B
    R1->>L: Acquire lock
    L-->>R1: Lock granted
    R1->>S: Read state version N
    R2->>L: Acquire lock
    L-->>R2: Lock held / wait
    R1->>S: Write state version N+1
    R1->>L: Release lock
    R2->>L: Acquire lock
    L-->>R2: Lock granted
    R2->>S: Read latest state N+1
~~~

Locking does not make every cloud operation an atomic transaction. Provider APIs may have already created resources before a runner fails; the state write may not have finished; external admins can still modify resources. Locking protects concurrency on the state backend within its supported scope.

### 5.1. Lock lifecycle

A standard workflow:
1. Runner authenticates to the backend.
2. Requests to acquire the lock.
3. If the lock is held, waits within a bounded timeout or exits with a clear message.
4. Reads state after acquiring the lock.
5. Executes the operation per policy.
6. Writes state when the operation completes per tool semantics.
7. Releases the lock.
8. If the runner crashes, resolves the stale lock via a supported procedure.

Never delete a lock solely because a pipeline has been waiting a long time. Before running `force-unlock`, confirm the previous operation has genuinely stopped and no process or provider operation is still active.

### 5.2. Lock ID and force-unlock

Tools typically provide a lock ID or owner metadata for diagnostics. When `force-unlock` is required:
- Identify the exact backend and workspace/state.
- Verify the lock-holding runner has exited or been terminated.
- Confirm no provider-side jobs/operations are still running.
- Record the change/incident ID and approver.
- Use only the exact lock ID of the stuck lock.
- After unlocking, re-read state and run refresh/plan.
- Do not run another concurrent apply during verification.

An improper `force-unlock` can allow two operations to write state simultaneously, making the situation worse.

### 5.3. Lock timeouts and pipeline queuing

Set lock timeouts based on expected operation duration, bounded enough to prevent runners from waiting indefinitely. CI/CD can serialize applies by state key or queue jobs targeting the same environment. Plans can run in parallel in some workflows, while applies and any state-mutating operations must respect locking semantics.

A useful rule is to structure concurrency by state boundary:
- Applies to the same state: serialized.
- Applies to independent states: can run in parallel if dependencies allow.
- Applies across producer and consumer states: ordered for compatibility.
- Drift remediation and release applies: never run concurrently on the same state.

## 6. Locking does not replace change coordination

State locks only protect operations from clients using the same locking mechanism. They do not prevent:
- Admins modifying resources directly in the console.
- Another pipeline using a different backend or state key.
- Scripts calling provider APIs outside IaC.
- A runner bypassing backend locks.
- Two separate states managing the same resource.

Therefore, also enforce:
- Cloud permissions restricting out-of-band modifications outside pipelines.
- Change management workflows for production.
- Inventory mapping to prevent two states from managing the same resource.
- Provider audit logs.
- Pre-apply policy checks.
- Runbooks for manual changes and drift.
- Clear ownership per resource domain.

Never place the same resource into two different states and expect their respective locks to coordinate. Every resource should have a single clear IaC owner.

## 7. State and sensitive data

State can store values marked sensitive in configuration, sensitive outputs, internal endpoints, resource metadata, and sometimes credentials returned by providers. Hiding an output from terminal display does not prove the value is absent from state.

### 7.1. Protective measures

- Encryption at rest via the backend/provider with appropriate key policies.
- TLS/encryption in transit.
- Least privilege: only required runners and operators get read/write access.
- Separate read and write roles where the platform supports it.
- Never share state via email, chat, or public artifacts.
- Never commit sensitive state, backups, or plan files to Git.
- Redact logs and CI output; avoid dumping state in job logs.
- Protect local caches, workspaces, and runner ephemeral storage.
- Audit every read/write/delete/version-restore event where supported by the backend.
- Enforce retention, deletion, and access reviews.
- Verify that state backups are encrypted and access-restricted just like primary state.

### 7.2. Plan files can also be sensitive

A saved plan can contain planned values and changes, including sensitive values. Protect plan artifacts:
- Store them only in a private artifact store.
- Limit their retention lifetime.
- Prevent users without apply permissions from downloading them.
- Never reuse an old plan after state or configuration changes.
- Re-plan when a plan becomes stale or state serial/lineage no longer matches.

State and plan artifacts must be treated as controlled production data.

## 8. Versioning, backups, and recovery

Remote backends may support version history, but versioning is not a complete backup strategy. If credentials are compromised, an attacker with broad permissions can delete both state and its version history. If retention lifecycles are misconfigured, older versions may expire before they are needed.

A recovery strategy requires:
- Backend versioning or snapshots.
- Independent backups in a separate account/project or trust boundary.
- Encryption keys accessible during DR.
- Approved retention policies.
- Backup integrity verification.
- Periodic restore drills.
- An inventory of state keys/workspaces and dependencies.
- A procedure for selecting the right recovery point.

### 8.1. State version, serial, and lineage

Terraform state includes metadata such as `lineage` and `serial` in its state format. `Lineage` identifies the state's history; `serial` helps identify snapshot versions per the tool's mechanism. During manual state operations, never hand-edit these fields to force the engine to accept a snapshot.

The engine/backend may reject writing an older state or a state from a different lineage to prevent unintended rollbacks. Use supported backup/restore or state push mechanisms and follow the guidance for your specific tool version.

### 8.2. Backup process

Define practices such as:
- Snapshots before every major production apply.
- Continuous versioning on the backend.
- Periodic backups to a separate region/account.
- Backups prior to state migration, `import`, `mv`, `rm`, or any state surgery.
- Recording metadata: state key, environment, workspace, timestamp, commit SHA, and change ID.
- Encrypting and restricting access to backups.
- Testing restores in an isolated environment.

Do not store a single backup in the same bucket/prefix with the same broad delete permissions as the primary state and call it DR.

## 9. Recovering lost or corrupted state

When state is missing or unparseable, halt all related apply pipelines immediately. Never run a blind apply, as the engine may assume all resources do not exist and propose duplicate creations or replacements.

### 9.1. Safe recovery sequence

1. Freeze related applies and manual changes.
2. Identify the exact backend, state key, workspace, environment, and owner.
3. Inspect backend status, version history, and audit logs.
4. Locate the latest valid snapshot/backup.
5. Verify lineage, serial, timestamp, source commit, and environment.
6. Restore to an isolated location or copy first whenever possible.
7. Validate format, checksum, and readability with the compatible engine version.
8. Compare resource mappings against provider inventory.
9. Run refresh/plan in non-apply mode to identify drift.
10. Review every proposed change—especially destroy/replace actions.
11. Re-open pipelines only after owner approval and once a fresh backup exists.

If the backend supports version restore, verify whether the operation creates a new version or overwrites the object in place. Preserve the pre-restore snapshot for investigation or rollback.

### 9.2. Stale state can be dangerous

An older state may omit newly created DR resources or resources that were already replaced. Planning against an old snapshot can cause the engine to propose duplicate creation, accidental deletion, or replacement of live production resources.

Do not select a snapshot solely because it has the newest file timestamp. Choose the snapshot consistent with lineage, apply history, commit/deployment timeline, and provider state. Importing or reconciling may be required instead of restoring an outdated snapshot.

### 9.3. Recovering when no backup exists

If no state backup is available:
- Halt all IaC infrastructure writes.
- Gather provider inventory and audit/change history.
- Identify resources belonging to the project scope.
- Rebuild state carefully via `import` or the equivalent workflow.
- Break work into small batches by domain/resource group.
- Plan and review resource by resource.
- Never apply a plan showing unexplained bulk creates/destroys.

Importing does not automatically generate complete configurations or prove resources match desired state. After importing, write/reconcile configuration, refresh, and carefully review the plan.

## 10. Drift and refresh

**Configuration drift** is the discrepancy between desired configuration and real infrastructure. Drift can result from console edits, external scripts outside IaC, provider defaults, external controllers, or an incomplete apply.

State helps detect drift via refresh/plan. Distinguish among:
- Real resource changed relative to state.
- Configuration changed relative to state.
- Provider/API changed defaults or schemas.
- A resource managed by another controller.
- A data source re-read that is not an IaC-managed resource.

### 10.1. Drift detection

Workflow:
1. Run plan/refresh in a safe mode appropriate to your tool version and workflow.
2. Inspect which resources differ.
3. Identify the actor and timestamp via audit logs.
4. Classify as a valid manual change, an emergency change, or an unauthorized change.
5. Decide whether to codify the change, revert the real resource, or import/reconcile.
6. Re-run plan and record the approval/change ticket.

Do not blindly auto-apply every drift. A direct change may be an emergency fix that must be captured in code first. Immediately applying old code could wipe out a production hotfix.

### 10.2. Not all drift is an error

Some attributes change naturally or are managed by the provider—such as timestamps, generated identifiers, autoscaling counts, or unmanaged metadata. Understand schema/provider behavior and use lifecycle `ignore_changes` or change policies only with clear justification. Overly broad ignores can mask security regressions or unintended configuration changes.

## 11. State migration and backend migration

You may need to move state from local to remote, change buckets/keys, switch workspaces, or migrate state management platforms.

The migration process should:
1. Stop applies against the old backend.
2. Identify the exact state/workspace currently in use.
3. Back up state and verify the backup.
4. Configure the new backend and access permissions.
5. Run migration using the engine's official mechanism.
6. Verify the new state preserves lineage and resource mappings.
7. Run a non-apply plan and compare the results.
8. Isolate the old backend so no runner writes to it by mistake.
9. Update pipelines, documentation, and ownership records.
10. Monitor the first apply through strict change review.

Never copy a state file that is actively in use during an apply. Use a lock or maintenance window to avoid inconsistent snapshots or two backends acting as primary writers.

### 11.1. Avoiding dual-primary state

After migration, only one backend may be authoritative. If the old backend still allows runners to write, the two states will diverge. Revoke write permissions or mark the old backend read-only/archived once migration is verified.

## 12. State operations: mv, rm, import, and push

State commands directly alter mappings. They do not call provider APIs in the usual sense, but they can cause the engine to stop managing a resource, manage the wrong resource, or overwrite state with another snapshot.

| Operation | Purpose | Risk |
|---|---|---|
| State mv | Move address mapping | Wrong destination or wrong workspace |
| State rm | Remove resource from state | Resource still exists but is no longer managed by IaC |
| Import | Add real resource into state | Wrong ID, duplicate ownership, or config mismatch |
| State push | Write a state snapshot to backend | Overwrites current snapshot if wrong |
| Force-unlock | Clear a stuck lock | Concurrent writers if the old lock was still active |
| Refresh/plan | Reconcile state with provider | Provider reads may have tool-specific side effects/limits, and a plan is not a backup |

### 12.1. Rules before any state surgery

- Verify the exact environment/workspace/backend/state key.
- Take a backup and verify it is readable.
- Record the change ID and purpose.
- Ensure no other apply is running.
- Use exact resource addresses and resource IDs.
- Preview or use dry-run/check flags if supported.
- Review output before confirming.
- Run a plan afterward to verify the impact.
- Retain an audit trail and owner record.
- Have a recovery path if the mapping is wrong.

Never edit JSON state in a text editor as a routine workaround. The state format is tool-managed data; direct edits can corrupt metadata or produce invalid snapshots. Only perform manual surgery when required by engine documentation and under a reviewed procedure.

## 13. CI/CD and concurrency governance

In organizations, state is shared across developers, platform teams, and multiple pipelines. A unified governance policy is essential.

### 13.1. Apply pipeline

A production pipeline can include:
- Format and validate checks.
- Static/security/policy checks.
- Initializing the right backend/workspace.
- Planning with pinned tool/provider versions.
- Publishing a protected plan artifact.
- Environment-specific approval.
- Verifying the plan is not stale.
- Applying under lock.
- Saving results, state metadata, and change ID.
- Post-apply verification.

Approvals should not drag out until the plan becomes stale. If state changes after planning, generate a new plan instead of blindly applying a stale artifact.

### 13.2. Serializing by state key

Examples:
- `prod/network` and `prod/app` pipelines sharing one state: must be serialized.
- `dev` and `prod` pipelines using separate states/backend identities: can run in parallel.
- Two modules in separate states modifying a shared resource: require shared ownership/processes since independent locks do not coordinate across states.

Use CI/CD concurrency groups keyed by environment/state key where supported by the platform. Backend locks remain an additional safeguard, not an excuse to omit queuing or ownership policies.

### 13.3. Pinning tool and provider versions

Version upgrades can alter state schemas, provider behavior, or plan semantics. Before upgrading:
- Read release notes and migration guides.
- Pin Terraform/OpenTofu and provider versions.
- Back up state.
- Test on non-production.
- Verify plan and state format compatibility.
- Prepare a downgrade/restore plan; do not assume older binaries can read upgraded state.

## 14. State in multi-region and DR environments

State must also be recoverable if the backend or region experiences an outage. However, never run multiple active states simultaneously as a "standby."

Determine:
- Which failure domain hosts the primary backend?
- Is there versioning/replication/backup to another region?
- During failover, does the DR region use the same state backend or a restored snapshot?
- How do you guarantee only one site has apply permissions?
- Does the restored state match live resources after the incident?
- Are credentials, KMS keys, and lock services available in DR?
- Can pipelines run if primary source control, registry, or CI is down?

During DR, a state snapshot can be restored in another region, but the old backend must be fenced or have write permissions revoked before opening the new pipeline. Two writable backends can create split-brain at the infrastructure management layer even when the workload data plane is healthy.

## 15. Observability for state and backends

Monitor:
- Lock acquisition success/failure and wait duration.
- Stale lock count/age.
- State read/write errors and latency.
- Backend availability and throttling.
- Snapshot/version creation.
- Backup age and backup verification results.
- Restore drill success/failure.
- State size and growth rate.
- Concurrent run attempts.
- Plan/apply duration and failures.
- Drift count/age by environment.
- Unauthorized read/write/delete attempts.

Never log state contents. Dashboards should track metadata and audit events rather than dumping sensitive attributes. Alert when backups age out, locks are held too long, state writes fail, or backend access policies change.

## 16. Well-Architected trade-offs

| Aspect | Good design | Risks to manage | Evidence |
|---|---|---|---|
| **Reliability** | Remote state, locking, versioning, tested restores | State loss/corruption, concurrent writes, stale snapshots | Restore drills, lock tests, backup checks |
| **Security** | Encryption, least privilege, isolated backends, auditing | State/plan leaking secrets, state deleted or tampered with | IAM reviews, access logs, secret scanning |
| **Performance Efficiency** | Appropriate state boundaries, controlled plan/apply | Oversized state, lock contention, slow plans | State size, lock wait, apply duration |
| **Cost Optimization** | Retain versions/backups per need and tier retention | Excessive retention, backend request/storage costs | Storage costs, backup inventory |
| **Operational Excellence** | Owners, runbooks, pipeline serialization, drift workflows | Manual state surgery, dual backends, missing recovery | Change audits, runbooks, restore tests |
| **Sustainability** | Right-sized state, policy-driven artifact/backup cleanup | Unbounded state/history growth | Lifecycle reviews, storage growth |

Trade-offs:
- Remote backends improve team reliability at the cost of an extra dependency and expense.
- Smaller states reduce blast radius and contention but increase cross-state coordination.
- Locking prevents concurrent writes, though a hung operation can block the team.
- Versioning aids recovery but does not replace independent backups.
- Broad read-only access eases planning/discovery but can expose sensitive data.
- Cross-region DR replication of state improves resilience but requires preventing dual writers.

## 17. State management design process

Architecture reviews should follow these steps:

1. **Define owners and scope:** which resources belong to which state, and who is accountable?
2. **Choose backend:** local for labs, remote for teams/production; verify locking and versioning support.
3. **Define boundaries:** by environment, domain, team, or region based on lifecycle and blast radius.
4. **Design access policies:** separate runner identity, operator read, break-glass, and backup admin roles.
5. **Protect data:** encryption, TLS, retention, auditing, and secret handling.
6. **Design locking:** serialize applies by state key, set timeouts, and document stale-lock runbooks.
7. **Manage plan/apply:** version pinning, approvals, stale-plan checks, and CI concurrency groups.
8. **Backups/versioning:** define snapshots, independent backups, and retention.
9. **Recovery:** test restores, verify lineage/serial, reconcile inventory, and import procedures.
10. **Drift handling:** detect, classify, codify manual changes or revert.
11. **Migration:** back up, lock, migrate, and verify the new backend.
12. **DR:** verify backup region/account, KMS, pipelines, and single-writer controls.
13. **Observability:** lock, backend, backup age, restore drill, state access, and drift metrics.
14. **Testing:** concurrent runs, runner crash, backend outage, stale backup, corrupt state, and failback.

### Pre-production checklist

| Item | PASS when |
|---|---|
| Backend | Remote backend selected with clear owner |
| Locking | Backend locking supported and tested concurrently |
| Isolation | Environment/state boundaries and IAM are independent |
| Sensitive data | State/plans encrypted with restricted access |
| Backups | Versioning and independent backups with retention |
| Restore | Tested restore drills and inventory reconciliation |
| Pipeline | Applies serialized by state, approvals, and stale-plan checks |
| Drift | Scheduled detection and designated remediation owner |
| State surgery | Backups, change control, and plan review in place |
| DR | Backend recovery and single-writer plan documented |
| Observability | Locks, state writes, backups, drift, and access monitored |
| Documentation | Runbooks, owners, escalation, and recovery steps clear |

## 18. Illustrative ADR — Remote state for the Booking Platform

> **Context:** Three teams jointly manage the Booking Platform's network, application, and database. Currently state sits on one engineer's laptop, and occasionally two people apply almost simultaneously.
>
> **Option A:** Keep local state and share the file via the repository. Easy to start, but risks committing secrets, losing files, overwriting changes, and lacking centralized locks.
>
> **Option B:** Remote backend with encryption, versioning, locking, and access policies; state split by environment and domain ownership.
>
> **Illustrative decision:** Choose B. Network, platform, and application have distinct state boundaries; each shared resource has a single owner. Production applies run through a CI identity with approvals.
>
> **Locking:** Backend locking combined with pipeline concurrency groups per state key. Force-unlock only via runbook and incident/change ID.
>
> **Recovery:** Backups before critical production applies, versioning, and an independent copy; periodic restore drills in an isolated workspace.
>
> **Security:** Runners have required read/write state permissions; developer read access is restricted; archive admin is separated from workload roles.
>
> **Verification:** Concurrent apply test, runner crash holding a lock, backend outage, restoring an older snapshot, console drift, and state migration rehearsal.
>
> **Revisit triggers:** State splitting creates excessive dependency coordination overhead, or backend locking/availability fails to meet requirements.

## 19. Hands-on exercise: handling corrupted state and concurrent applies

A team manages the production network using Terraform/OpenTofu. Remote state sits in object storage with versioning enabled, but without independent backups. CI has two pipelines:
- Pipeline A runs apply to update route tables.
- Pipeline B runs apply to update security groups.

Both share the same state, yet pipelines are not serialized. One runner loses connectivity after the provider creates a resource; the pipeline fails and the lock remains. Afterward, an admin updates a route directly in the console. A week later, the state object is accidentally overwritten with an older snapshot.

**Requirements:**
1. Identify the risks of concurrent applies and explain why backend locking must be verified.
2. Design a stale-lock verification procedure prior to `force-unlock`.
3. Determine how to recover the correct state version and verify `lineage`/`serial`.
4. Reconcile real resources after the interrupted apply.
5. Handle the manual route change and drift.
6. Design independent backups and delete/version-restore permissions.
7. Propose CI concurrency groups and state ownership.
8. Plan restore drills and required alerts.

### Solution approach

- Halt all applies targeting the network state. Inspect runners A/B, active processes/provider operations, backend lock metadata, and cloud audit logs; never `force-unlock` merely because a job failed.
- Once confirmed the runner has terminated, record the change/incident ID, pass the exact lock ID via the tool's supported command, and then run refresh/plan.
- Select the state snapshot based on apply history, lineage, serial, commit SHA, and provider inventory—not solely by timestamp.
- Restore to an isolated copy first, verify state parses cleanly, and inspect resource ID mappings. Compare against cloud inventory and audit events.
- For the interrupted apply, identify which resources the provider created that state never recorded; consider importing/reconciling rather than running a blind apply.
- Investigate the route change: if valid, codify it in configuration and review the plan; if unauthorized or undesired, revert under change approval.
- Serialize applies per state key using pipeline concurrency groups while keeping backend locks as an enforcement layer.
- Create cross-account or cross-trust-boundary backups, encrypted and protected against deletion; test restores periodically.
- Alert on concurrent runs, lock age, backend write failures, backup age, unexpected state version changes, and drift.

### Self-check questions

1. How does state differ from configuration and real infrastructure?
2. Why is local state unsuitable for production team workflows?
3. Does a remote backend automatically guarantee locking?
4. Which types of concurrency does a state lock prevent, and which changes can it not prevent?
5. Why should you never `force-unlock` before verifying the previous runner has stopped?
6. How does versioning differ from independent backups?
7. What do `lineage` and `serial` protect during a restore?
8. Why can an older state produce a dangerous plan?
9. When is `import` more appropriate than restoring a snapshot?
10. Why should the same resource never be managed by two states?
11. How do you handle a manual change without overwriting a production hotfix?
12. After restoring state, what must be verified before re-enabling applies?

Sound state management is more than picking where to store a file. It must **maintain a trustworthy mapping between configuration and real infrastructure, prevent concurrent writers, protect sensitive data, retain independent recovery points, and enforce reconciliation checks before resuming applies**. Remote backends, locking, versioning, and backups only deliver value alongside clear ownership, CI/CD governance, drift management, and tested restore drills.
