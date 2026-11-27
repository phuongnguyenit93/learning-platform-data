# Provisioning Reproducible Environments and Safely Decommissioning Resources

## 1. Infrastructure environments should be built from a verifiable definition

A cloud application is more than source code. To run, it needs networks, subnets, routes, identities, compute, databases, caches, queues, object storage, security policies, DNS, logging, and numerous dependent configurations. If every environment is created manually through a console or an unmanaged checklist, environments quickly diverge, become hard to reproduce, and make it hard to tell which resources are safe to delete.

**Infrastructure as Code (IaC)** describes infrastructure using definition files managed like source code. The IaC tool compares the desired state against known state or actual state, then plans creates, updates, or deletes to bring the environment to its target state.

Within the **CLOUD_ARCHITECTURE** module, cloud architecture design moves from business requirements to networking, compute, data, and deployment choices while balancing reliability, security, scalability, cost, and operations under Well-Architected principles. IaC connects the architectural blueprint to a repeatable, reviewable, testable, auditable, and decommissionable deployment workflow.

A reproducible environment is more than "re-running the deploy command." It requires explicitly defining definition versions, inputs, state, secrets, dependencies, execution permissions, recoverable data, and resources with independent lifecycles. A safe teardown process is just as critical as provisioning.

After this lesson, you will be able to:

- Explain desired state, declarative IaC, imperative automation, and idempotency.
- Organize modules, environment configurations, and versioning to reproduce environments.
- Manage state, locking, drift, imports, and cross-resource dependencies.
- Provision ephemeral environments for pull requests, integration tests, and preview deployments.
- Manage secrets, identities, immutable artifacts, and seed data.
- Design pipelines for validation, planning, approvals, applies, and post-deploy verification.
- Safely decommission resources while protecting data and retained assets.
- Embed quotas, cost controls, auditing, and Well-Architected principles into IaC workflows.

## 2. Desired state and environment lifecycles

### 2.1. What is desired state?

Desired state describes the end result the system must achieve, for example:

- A VPC/VNet with explicit CIDRs, subnets, and routes.
- A workload identity permitted to read only its required secrets.
- Three replicas of the Booking API running an immutable image version.
- A private database with encryption at rest, backups, and policy-compliant retention.
- A queue, dead-letter queue, and scoped publisher/consumer permissions.
- Configured logs, metrics, traces, and alerts.
- Autoscaling with min/max bounds and resource budgets.

The IaC tool reads the definition and determines the actions required to reach desired state. If the definition is unchanged and the provider reports matching state, a subsequent apply typically needs zero changes. This is a major advantage of declarative configuration.

### 2.2. Imperative vs. declarative

| Approach | Description | Strengths | Risks/trade-offs |
|---|---|---|---|
| Imperative script | Lists sequential commands to execute | Flexible for custom workflows or ad-hoc tasks | Hard to know current state; reruns can duplicate or misconfigure |
| Declarative IaC | Describes target end state | Provides plans/diffs, converges to desired state, easy to review | Must manage state, provider semantics, and out-of-band edits |
| Configuration management | Configures host packages, files, and services | Useful for OS/application configuration | May require coordinating provisioning and lifecycles |
| Image-based provisioning | Packages base runtime/config into versioned images | Consistent instance startup, reduced drift | Requires managing image pipelines and patch lifecycles |

In practice, approaches can be combined: IaC provisions networks/compute/databases; image pipelines build artifacts; configuration management or `cloud-init` performs lightweight bootstrapping; and deployment controllers run application releases. Define a single source of truth for each configuration group.

### 2.3. Declarative does not automatically mean safe

A `destroy` command can delete a database or bucket if lifecycle settings allow it. An `apply` can replace critical resources when immutable properties change. State can be lost or overwritten. Therefore, plan reviews, policy guardrails, backups, approvals, and separate permissions for destructive actions are essential.

## 3. Building blocks of IaC

### 3.1. Resource

A resource is a concrete infrastructure component: network, subnet, firewall rule, VM, container cluster, database, bucket, queue, IAM role, DNS record, or monitoring alarm.

Every resource needs:

- A stable name and identifier.
- Owner, environment, service, and purpose.
- Region/zone and network/security scope.
- Tags/labels for cost allocation and lifecycle management.
- Clearly declared inputs and outputs.
- Lifecycle policies, backups, and deletion protection where needed.

### 3.2. Variables, outputs, and configuration

Variables allow the same modules to serve different environments. Outputs publish values needed by other modules or workloads, such as subnet IDs, endpoints, or identity references. Configuration holds environment-specific values.

Never hardcode passwords, tokens, private keys, or credentials inside committed variable files. For secrets, use a secret manager and workload identities; pass only references or fetch secrets at runtime per policy.

### 3.3. Module

Modules package a group of resources behind an input/output interface. Examples:

- `network-baseline`
- `private-database`
- `container-platform`
- `service-identity`
- `object-storage-private`
- `observability-baseline`

Modules should reflect capabilities or patterns sharing a lifecycle, complete with validation and documentation. Avoid overly tiny modules forcing consumers to wire hundreds of interfaces, as well as giant modules packed with dozens of confusing flags.

### 3.4. Providers and versions

Providers/plugins translate IaC definitions into cloud or platform API calls. Pin versions within tested compatibility ranges and commit dependency lockfiles if supported by the tooling.

Never rely on implicit `latest` in production pipelines. Provider updates can alter schemas, diff behavior, defaults, or resource lifecycles. Upgrades should go through reviewed changes, plan comparisons, and testing.

## 4. Multi-environment repository structure

An illustrative layout:

~~~text
infrastructure/
  modules/
    network/
    database/
    application/
    observability/
  environments/
    dev/
      main.tf
      variables.tf
      backend.hcl
    staging/
      main.tf
      variables.tf
      backend.hcl
    production/
      main.tf
      variables.tf
      backend.hcl
  policies/
    security/
    cost/
    lifecycle/
  tests/
  scripts/
~~~

Directory names and extensions depend on tooling; this structure simply illustrates separating reusable modules, environment composition, policies, and tests.

### 4.1. Separating modules from environments

Modules describe how to provision a capability. Environment configurations select module versions, inputs, regions, sizing, and policies for a specific environment.

Example:

~~~hcl
module "network" {
  source              = "../../modules/network"
  environment         = "staging"
  region              = var.region
  cidr                = var.vpc_cidr
  enable_private_link = true
}

module "booking_service" {
  source             = "../../modules/application"
  environment        = "staging"
  image_digest       = var.booking_image_digest
  subnet_ids         = module.network.application_subnet_ids
  database_secret_id = module.database.secret_reference
}
~~~

This is a Terraform-style HCL example; modules, inputs, and outputs must exist in real implementations. Never pass plaintext secret values into variables merely to relay them through modules.

### 4.2. Environment parity

Dev, staging, and production should share the same modules and architecture, differing only in controlled inputs:

| Attribute | Dev | Staging | Production |
|---|---|---|---|
| Capacity | Small, low scale | Near-production for testing | Per demand/SLO |
| Data | Synthetic/seed | Masked or synthetic | Protected real data |
| Network | Private, minimal external integrations | Similar to prod | Strict segmentation and egress |
| Identity | Dev-specific roles | Staging-specific roles | Least privilege, approvals |
| Backups | Can be shorter | Restore testing | Full policy |
| Observability | Higher sampling | Release validation | SLOs, audits, and alerts |
| Deletion | Ephemeral/auto-cleanup | Guardrails | Protected lifecycle |

Parity does not mean dev must match production sizing or hold real data. The goal is sharing architecture and relevant behavior while keeping cost, data classification, and blast radius appropriate to each environment.

## 5. Reproducing environments via pipelines

### 5.1. Overall workflow

~~~mermaid
flowchart TD
    CHANGE["IaC change / pull request"] --> FORMAT["Format + lint"]
    FORMAT --> VALIDATE["Validate syntax/schema"]
    VALIDATE --> POLICY["Security / cost / policy checks"]
    POLICY --> PLAN["Generate plan / diff"]
    PLAN --> REVIEW["Peer review + approval"]
    REVIEW --> APPLY["Apply with scoped identity"]
    APPLY --> VERIFY["Post-deploy verification"]
    VERIFY --> READY["Environment ready"]
    VERIFY --> ROLLBACK["Repair / rollback / reconcile"]
~~~

Pipelines should execute these steps:

1. Check formatting, syntax, and provider/module versions.
2. Validate inputs, naming, tags, CIDRs, regions, and policies.
3. Run static/security analysis and cost estimation.
4. Generate a plan/diff and attach the artifact for reviewer inspection.
5. Require approval aligned with blast radius and environment.
6. Apply the exact reviewed plan using a dedicated pipeline identity.
7. Run smoke tests, health checks, and security verification.
8. Record results, state versions, change IDs, and audit records.

Never regenerate a different plan after approval and apply it without reviewing the new diff. Plan artifacts may contain sensitive values depending on tooling; protect storage and access.

### 5.2. Bootstrap dependencies

Certain resources must exist before the IaC state backend can operate—such as remote state buckets, lock tables, encryption keys, or CI identities. This is the bootstrap layer.

Bootstrapping requires:

- One-time creation via a separate controlled process.
- Protecting the state backend with encryption, versioning, and access policies.
- Separating bootstrap administrator permissions from runtime deployment roles.
- Recovery documentation and backups.
- Ensuring the state backend does not circularly depend on the very state it stores in a hard-to-recover loop.

### 5.3. Controlled applies

Production applies should use short-lived/assumed roles or workload identities; restrict accounts, regions, and resources; and never use personal admin credentials. Destructive changes or changes to networking, identity, or data tiers require stronger approvals and maintenance plans where needed.

## 6. State: infrastructure management metadata

Many IaC tools store **state** to map configured resources to real resources, retaining IDs, metadata, and dependencies. State can contain sensitive details or secret values depending on the provider and resource.

### 6.1. Why remote state?

Local state on a laptop works for small experiments but fails when teams or CI collaborate:

- No consistent shared view of state.
- Losing the file loses resource mappings.
- Hard to govern backups and audits.
- Multiple people can apply concurrently.

A remote backend centralizes state and supports versioning, access controls, and locking depending on the tool/backend.

### 6.2. State locking

Locks prevent multiple writers from modifying the same state simultaneously. Never disable locking just to "bypass an error" without knowing the lock owner and whether an operation is still active.

If a pipeline crashes:

1. Inspect active runs/sessions and backend lock metadata.
2. Confirm with certainty that the previous writer is no longer running.
3. Use the tool's supported unlock procedure with approvals/logging as required.
4. Inspect state and live resources before running plan/apply again.

An improper force-unlock can cause state corruption or two writers creating duplicate resources.

### 6.3. Splitting state by blast radius

You do not need to store all infrastructure in one monolithic state. Foundation/networking, data, platform, and application layers can use separate states to:

- Reduce locking scope and plan runtime.
- Separate deploy permissions by owner.
- Shrink blast radius on changes.
- Prevent one service from altering another service's state.

In exchange, cross-state outputs/references and dependencies must be managed cleanly. Avoid circular dependencies between states.

### 6.4. State backup and recovery

State backends require:

- Encryption at rest and TLS.
- Versioning/backups aligned with RPO.
- Least-privilege read/write permissions.
- Access and mutation auditing.
- Recovery tests and import/reconciliation procedures.

Never commit plaintext state to source repositories. Never paste state in chats or tickets if it contains sensitive values. When sharing plan/state artifacts, use a secure artifact store with short retention.

## 7. Idempotency, dependencies, and resource ordering

### 7.1. Provisioning idempotency

Provisioning is idempotent when re-running with the same desired state neither creates duplicate resources nor causes unintended changes.

Declarative IaC helps maintain idempotency, yet bootstrap scripts, provisioners, or external API calls may not be idempotent. For side effects outside IaC:

- Use stable resource IDs or idempotency keys where supported by APIs.
- Check current state before creating.
- Store operation IDs and outcomes.
- Implement retry and reconciliation logic.
- Avoid generating fresh random names on every run.

### 7.2. Dependency graphs

Example:

~~~mermaid
flowchart TB
    NET["Network / subnets"] --> SEC["Security groups / endpoints"]
    SEC --> DB["Database"]
    SEC --> CLUSTER["Compute cluster"]
    DB --> SECRET["Secret reference / access policy"]
    CLUSTER --> ID["Workload identity"]
    ID --> APP["Application deployment"]
    DB --> APP
    APP --> OBS["Monitoring / alert"]
~~~

IaC tools infer dependencies from resource references or require explicit dependency declarations for out-of-graph side effects. Incorrect ordering can leave resources temporarily insecure—for example, a database existing before encryption or network policies apply.

### 7.3. Bootstrapping and race conditions

When creating many resources in parallel, API quotas, eventual consistency, or DNS propagation can cause downstream steps to fire too early. Use readiness checks or bounded retries for dependency provisioning rather than fixed sleeps.

## 8. Drift detection and out-of-band changes

**Configuration drift** occurs when live resources diverge from declared desired state—for instance, an operator manually opens a firewall rule or changes database sizing in the console.

### 8.1. Detecting drift

- Run periodic read-only `plan`/`refresh` checks.
- Use cloud configuration inventories/rules to spot non-compliant resources.
- Compare tags, IAM/network policies, encryption, and public exposure.
- Alert on unmanaged resources or broken state mappings.
- Attach findings to owners and change records.

### 8.2. Handling drift

Not every drift should be blindly overwritten. Classify:

| Drift type | Action |
|---|---|
| Approved emergency change | Update IaC after the incident/change window |
| Misconfiguration, high risk | Restore desired state per runbook |
| Resource needing management, not yet imported | Import into state after review |
| Provider-managed adjustment | Verify semantics/API; update expectations if valid |
| Drift with unknown owner | Investigate and establish ownership before modifying |

Key rule: the IaC repository is the definition source, yet state and cloud resources must be reconciled before destructive applies. Never run `apply` mechanically without understanding the drift.

### 8.3. Importing existing resources

When manually created resources must transition to IaC:

1. Verify owner and resource purpose.
2. Write the matching resource definition.
3. Import the resource ID into state using the tool.
4. Run `plan` and inspect diffs.
5. Adjust the definition to match configurations that must be retained.
6. Apply only after the plan contains no unintended changes.

## 9. Ephemeral environments for PRs and testing

Ephemeral environments are provisioned for a specific purpose and lifespan—such as pull request previews, integration tests, performance experiments, or demos.

### 9.1. Lifecycle

~~~mermaid
flowchart TD
    PR["Pull request opened"] --> CREATE["Create isolated environment"]
    CREATE --> SEED["Seed synthetic test data"]
    SEED --> TEST["Run integration / preview"]
    TEST --> REVIEW["Review / feedback"]
    REVIEW --> MERGED{"PR merged or closed?"}
    MERGED -->|"No"| TTL["TTL / owner cleanup check"]
    TTL --> REVIEW
    MERGED -->|"Yes"| DESTROY["Destroy ephemeral resources"]
    TTL -->|"Expired"| DESTROY
    DESTROY --> VERIFY["Verify resource removal"]
    VERIFY --> REPORT["Cleanup report / audit"]
~~~

### 9.2. Separate identities and boundaries per environment

Never provision preview environments using production administrator credentials. Each environment needs:

- Naming/tags containing PR ID, owner, service, and expiry.
- Separate network boundaries or namespaces matching risk.
- Dedicated IAM roles/service accounts.
- Synthetic/masked data; never casually clone production PII.
- Quotas/budgets and TTLs.
- Short-lived secret scopes.
- Short retention for observability data.

### 9.3. Avoiding collisions

Multiple PRs run concurrently. Resource names must stay stable within a PR without colliding across PRs; DNS hostnames, bucket names, DBs/schemas, and namespaces need unique scopes. Respect provider length and character limits.

### 9.4. Automated cleanup and orphan detection

Closed PRs may fail to trigger cleanup workflows if runners fail or permissions expire. Run scheduled cleanup jobs to locate expired-TTL resources, verify owners/state, and decommission per policy. Never delete a resource solely based on an expiry tag if it is shared or protected.

## 10. Building reproducible environments

### 10.1. Pinning images and dependencies

To keep environments reproducible, pin:

- IaC tool, provider, and module versions.
- Container image digests or immutable artifact versions.
- OS/base images and package versions.
- Runtime/compiler versions.
- Config schemas and migration versions.
- Database engine/versions where compatibility requires.

Mutable tags like `latest` can resolve to different contents on the next run. Image digests identify artifacts deterministically.

### 10.2. Separating configuration from secrets

Non-sensitive configuration such as regions, replica counts, and feature flags can reside in environment inputs. Secrets must come from a secret manager via workload identity and only at runtime or in authorized steps.

Never:

- Commit `.env` files containing production secrets.
- Print secrets to CI logs.
- Bake secrets into image layers.
- Pass secrets via command lines where they can be logged.
- Reuse credentials across dev, staging, and production.

### 10.3. Seed data and migrations

New environments need schemas and test data. Use versioned migrations; seed synthetic data with deterministic IDs when tests require repeatability; never import production data without approval, masking, and data access controls.

Migrations need compatibility plans—`expand → migrate → contract` when zero downtime is required. IaC provisioning a database does not replace application migration tools; keep ownership clear.

### 10.4. Environment manifests

Publish manifests recording:

~~~yaml
environment_id: pr-482
environment_type: ephemeral
owner: booking-team
source_revision: 8b2a4d1
iac_revision: c17f390
image_digest: sha256:example-digest
region: ap-southeast-1
created_at: "2026-11-18T10:00:00Z"
expires_at: "2026-11-19T10:00:00Z"
data_class: synthetic
cleanup_policy: destroy-on-close
~~~

This is an illustrative manifest. Never write secrets into manifests. Store metadata in a queryable store so cleanup jobs and audits know who owns the environment, which revisions built it, and when it expires.

## 11. Safe teardown: decommissioning without losing retained data

Destroying an environment is not simply running a command that deletes everything. Distinguish temporary resources, data-bearing resources, shared foundations, and assets retained for audits or recovery.

### 11.1. Classifying resources by lifecycle

| Category | Example | Teardown policy |
|---|---|---|
| Ephemeral compute | PR namespaces, temporary VMs, preview LBs | Can be deleted when the environment expires |
| Temporary data | Synthetic DBs/schemas, test objects | Deleted after tests or short retention |
| Persistent data | Production DBs, objects, backups | Never deleted by routine environment pipelines |
| Shared foundation | VPCs, DNS zones, clusters, KMS keys | Separate lifecycle and separate approvals |
| Audit/telemetry | Deployment records, security audits | Retained per policy; never deleted with app env |
| External side effects | DNS delegations, SaaS projects, payment sandboxes | Revoked/decommissioned via dedicated workflows and verified |

### 11.2. Protecting data resources

For databases, buckets, KMS keys, or backup vaults:

- Enable deletion protection and retention locks where appropriate.
- Take backups/PITR prior to destructive changes.
- Separate deploy permissions from destroy permissions.
- Require explicit approvals or break-glass for production data.
- Check dependencies, replication, and retention/legal holds.
- Verify recovery works before deleting originals.

Never delete encryption keys while ciphertexts or backups still rely on them. Losing a key leaves data existing yet unrecoverable.

### 11.3. Teardown workflow

1. Verify environment ID, owner, TTL, and scope.
2. Check whether resources are shared, protected, or data-bearing.
3. Block new jobs/deployments and drain workloads.
4. Export/back up data requiring retention per policy.
5. Revoke temporary credentials, endpoints, and permissions.
6. Delete resources in reverse dependency order.
7. Check external resources and potential orphans.
8. Confirm DNS records, public endpoints, IPs, roles, and storage are removed.
9. Record a cleanup report listing retained resources and justifications.

~~~mermaid
flowchart TD
    REQUEST["Teardown requested / TTL expired"] --> SCOPE["Resolve environment and resource inventory"]
    SCOPE --> GUARD{"Protected or persistent resource?"}
    GUARD -->|"Yes"| APPROVAL["Require retention/backup/approval decision"]
    APPROVAL -->|"Keep"| RETAIN["Detach from ephemeral stack; retain"]
    APPROVAL -->|"Approved delete"| BACKUP["Backup / verify retention"]
    GUARD -->|"No"| DRAIN["Drain jobs and stop workloads"]
    BACKUP --> DRAIN
    DRAIN --> DESTROY["Destroy in dependency order"]
    DESTROY --> VERIFY["Verify no orphan / public access"]
    RETAIN --> REPORT["Cleanup report + audit"]
    VERIFY --> REPORT
~~~

### 11.4. Partial failures during destroy

Teardowns can partially delete resources and fail mid-way due to quotas, API errors, networking, or permissions. Never assume a stack is clean simply because a command exited or updated partial state.

Always:

- Retain logs/results for every operation.
- Run inventory and `plan`/reconcile checks after failures.
- Identify remaining resources and their owners.
- Retry idempotent operations without recreating the stack.
- Isolate resources requiring manual intervention and document reasons.
- Alert when orphans outlive their TTL.

## 12. IaC security and policy guardrails

### 12.1. Least privilege for pipelines

Pipeline identities should:

- Manage only assigned accounts, projects, regions, and environments.
- Use federated/short-lived credentials where supported by the provider.
- Separate plan/read roles from apply/write roles where feasible.
- Lack permissions to delete data, backups, or keys in ephemeral pipelines.
- Audit apply/destroy actions and state access.
- Require approvals for privileged permissions or sensitive resources.

### 12.2. Policy as code

Before apply, policy checks can reject:

- Public databases or object storage outside policy.
- Resources lacking encryption.
- Security groups exposing management ports to the internet.
- Wildcard IAM or administrator grants without exceptions.
- Resources missing `owner`, `environment`, or `cost` tags.
- Instances/volumes exceeding size, quota, or budget limits.
- Data tiers missing backups, retention, or deletion protection.
- Plaintext secrets in configuration.

Policies should be tested and versioned; exceptions require owners, rationale, scope, and expiry.

### 12.3. IaC supply chain

IaC modules, providers, actions, and CI plugins are all dependencies capable of altering infrastructure. Use only trusted sources, pin versions, review changes, scan modules, and restrict pipeline permissions. Never execute untrusted modules or scripts with cloud administrator credentials.

## 13. Drift, replacement, and lifecycle hazards

Some attributes cannot update in place and force tools to replace resources—such as changing CIDRs, encryption settings, immutable identifiers, or disk types depending on the provider.

Plans must identify:

- Which resources will create, update, delete, or replace?
- Will downtime or data loss occur?
- Can replacement resources be provisioned in parallel?
- How will DNS/traffic cutover and connection draining work?
- Do data migrations/replication require separate steps?
- Is rollback feasible?

### 13.1. Lifecycle guards

Some tools offer lifecycle rules such as `prevent_destroy`, `create_before_destroy`, `ignore_changes`, or retaining resources. These rules carry specific semantics:

- `prevent_destroy` can block legitimate teardown pipelines if resources stay protected.
- `create_before_destroy` requires sufficient quotas for old and new resources simultaneously.
- `ignore_changes` can hide genuine drift if applied too broadly.
- Retaining resources can leave orphans needing owners and cleanup workflows.

Never turn on `ignore_changes` just to make a plan look "clean" without understanding the source of change.

## 14. Quotas, capacity, and cost of environment lifecycles

Spinning up additional environments consumes quotas and capacity. If every PR provisions its own cluster and database, environments can exhaust quotas or spike costs rapidly.

### 14.1. Budgets for ephemeral environments

Define:

- Maximum concurrent environments.
- Default TTL and TTL extension policies.
- CPU/memory/storage caps.
- Permitted counts of databases, clusters, and endpoints.
- Cost budgets per PR/team.
- Rate limits on environment creation to avoid flooding cloud APIs.

### 14.2. Cost allocation

Every resource should carry tags such as `environment_id`, `owner`, `service`, `cost_center`, `created_by`, and `expires_at`. Use billing exports/cost APIs to reconcile live resources against spend.

### 14.3. Reuse vs. create fresh?

| Model | Advantages | Trade-offs |
|---|---|---|
| Dedicated environment per PR | High isolation, near-production testing fidelity | Higher cost and quota usage |
| Shared test environment | Low cost, fewer resources | Tests interfere with each other; data/network collisions |
| Ephemeral namespace/stack on shared platform | Reuses clusters and foundations | Requires strong quotas, namespace isolation, and cleanup |
| Dedicated environment per team | Balances ownership and isolation | Idle capacity, more stacks to operate |

Choose a model based on risk, data sensitivity, test fidelity, concurrency, and cost.

## 15. Testing IaC and reproducibility

### 15.1. Test layers

| Layer | Contents |
|---|---|
| Format/lint | Style, naming, dead code, deprecated attributes |
| Validate | Syntax, types, required inputs, and provider schemas |
| Unit/policy tests | Rules, tags, identities, and network policies against expectations |
| Plan review | Diffs and resource replacements/destructions |
| Integration tests | Real provisioning in sandboxes verifying connectivity/functionality |
| Drift tests | Out-of-band changes detected reliably |
| Rebuild tests | Destroy ephemeral stack and recreate from the same revision |
| Teardown tests | Deletes target resources while keeping protected resources intact |

### 15.2. Reproducibility test

A thorough test:

1. Provisions a stack from a specific revision.
2. Records image digests, provider/module versions, and inputs.
3. Runs smoke and integration tests.
4. Runs a second `plan` and confirms zero unexpected diffs.
5. Destroys the ephemeral stack.
6. Verifies cloud inventory contains zero orphans.
7. Recreates from the exact same revision and inputs.
8. Compares topology, policies, configuration, and behavior.

Physical resource IDs do not need to match; what must be reproducible are structure, configuration, policies, and committed behavior.

### 15.3. Negative tests

- Dev pipelines cannot delete production databases.
- Environments missing an owner or TTL are rejected or quarantined.
- IaC plans opening public databases are blocked by policy.
- While a state lock is held, a second apply cannot overwrite state.
- Destroying an ephemeral stack never deletes shared networks or KMS keys.
- Secrets never appear in unprotected plans, logs, or artifacts.
- Exceeding provider quotas fails cleanly without infinite retries.

## 16. Observing and operating IaC

### 16.1. Metrics and events

Track:

- Provisioning duration and success/failure rates.
- Resource create/update/delete/replace counts.
- Plan drift counts.
- Apply/destroy failures and retries.
- State lock contention and lock age.
- Quota exceeded errors and API throttling.
- Environment counts, ages, and orphan counts.
- Cleanup completion times.
- Cost per environment and idle resource costs.

Emit events for PR opened/closed, plan generated/approved, apply started/completed, policy violations, drift detected, destroy started/completed, and manual exceptions.

### 16.2. Audit records

Every apply/destroy should capture:

- Principal/pipeline identity.
- Repository, revision, and module/provider versions.
- Environment, account, and region.
- Plan artifact ID or digest.
- Approver and change ticket.
- Resource changes.
- Outcome and correlation ID.

Never store plaintext credentials in audit logs; protect plan/state artifacts since they may hold sensitive configurations.

### 16.3. Runbooks

Runbooks should cover how to handle:

- Stuck state locks.
- Unavailable state backends.
- Provider API throttling or quota exhaustion.
- Resource drift from emergency changes.
- Mid-run apply failures.
- Partial destroys and orphaned resources.
- Protected resources blocking teardown.
- Expired credentials or certificates.
- Provider/module upgrades producing unexpected diffs.

## 17. Example pipeline for BookingCloud

~~~yaml
name: provision-preview
on:
  pull_request:
    types: [opened, synchronize, reopened, closed]

jobs:
  validate:
    if: github.event.action != 'closed'
    steps:
      - run: iac fmt-check
      - run: iac validate
      - run: policy-check infrastructure/
      - run: cost-estimate infrastructure/
      - run: iac plan -out=preview.plan

  apply:
    needs: validate
    if: github.event.action != 'closed'
    environment: preview-approval
    steps:
      - run: iac apply preview.plan
      - run: smoke-test preview
      - run: record-environment-manifest

  destroy:
    if: github.event.action == 'closed'
    steps:
      - run: verify-preview-owner-and-scope
      - run: iac plan-destroy
      - run: policy-check-destroy-plan
      - run: iac destroy
      - run: verify-no-orphans
~~~

This is a pseudoworkflow, not ready-to-run syntax for any specific CI provider. Real implementations must separate validate/apply artifacts, verify event context, scope apply/destroy permissions, enforce concurrency groups, lock state, require approvals, and enforce branch protection. Never execute apply/destroy purely on untrusted PR metadata.

## 18. Well-Architected assessment

| Perspective | Review questions | Required evidence |
|---|---|---|
| **Operational Excellence** | Can environments be recreated, reviewed, audited, and decommissioned via standard processes? | Pipelines, state backups, runbooks, manifests, cleanup reports |
| **Security** | Do pipelines enforce least privilege? Are secrets, state, and artifacts protected? | IAM policies, secret scans, state encryption, approvals, and audits |
| **Reliability** | Can mid-run apply/teardown failures reconcile and recover? | Locking, backups, idempotency, drift checks, rebuild/restore tests |
| **Performance Efficiency** | Are provisioning times, shared platforms, and capacity appropriate? | Provision durations, warm pools, quota/capacity tests |
| **Cost Optimization** | Do ephemeral/idle resources have TTLs, budgets, and owners? | Cost tags, orphan alerts, TTL cleanups, per-environment cost |
| **Sustainability** | Are idle resources, bloated logs/state, and redundant rebuilds avoided? | Lifecycle policies, reuse strategies, utilization, cleanup efficiency |

IaC changes infrastructure rapidly and consistently; therefore, pipeline privileges and guardrails must be equally strong. A well-designed reproducible environment yields equivalent outcomes from the same revision; a well-designed teardown releases temporary resources while preserving required data, audits, keys, and shared foundations.

## 19. Hands-on exercise: provisioning and decommissioning preview environments

BookingCloud wants to spin up a preview environment for every pull request to test the booking flow:

- An application namespace/compute workload.
- A small database with synthetic seed data.
- Dedicated caches and queues, or isolated namespaces.
- Private ingress, preview DNS, and TLS.
- Workload identity limited strictly to preview secrets.
- Short-retention logs, metrics, and traces.
- 24-hour TTL after last activity.
- Automatic teardown when the PR closes.

Complete the following:

**Task 1 — Resource inventory:** list resources, owners, dependencies, quotas, tags, and lifecycle classes.

**Task 2 — Module design:** split modules for networking, platform, data, application, and observability; define inputs and outputs.

**Task 3 — State:** choose remote backend, state scopes, locking, encryption, and recovery.

**Task 4 — Pipeline:** design validation, policy checks, plan artifacts, approvals, applies, smoke tests, and manifests.

**Task 5 — Security:** configure workload identities, secret access, private ingress/egress, and policies preventing public databases and credential leaks.

**Task 6 — Reproducibility:** pin IaC/provider/module/image versions, synthetic seed data, and migrations.

**Task 7 — Teardown:** classify ephemeral, persistent, and shared resources; design backups, approvals, retention, and orphan verification.

**Task 8 — Drift/failures:** simulate manual edits, lost state locks, provider quota exhaustion, and partial destroys.

**Task 9 — Cost:** configure concurrency caps, TTLs, resource sizing, budgets, and orphan alerts.

### Self-check evaluation framework

| Decision | Must demonstrate |
|---|---|
| Shared modules across envs | Differences live in reviewed inputs, not copy/pasted configs |
| Remote state | Locking, access controls, encryption, backups, and recovery tested |
| Immutable artifacts | Revision, image digest, and provider versions are deterministic |
| Ephemeral identity | Never uses production admin roles or secrets |
| Safe destroy | Never deletes retained data, foundations, or audit records |
| Drift handling | Has owners, classification, and reconciliation prior to destructive applies |
| Cleanup | TTLs, orphan detection, and reports confirming removal |
| Rebuild | Same revision/inputs recreate equivalent topology, policies, and behavior |

## 20. Checklist before promoting IaC workflows to production

- [ ] Desired state, resource owners, tags, environments, and lifecycles are declared.
- [ ] Modules, inputs/outputs, and environment compositions are versioned.
- [ ] Provider, module, and tool versions are pinned and upgraded through review.
- [ ] Remote state is encrypted, locked, backed up, and access-restricted.
- [ ] Plans/diffs are stored securely and reviewed prior to apply.
- [ ] Pipeline identities are short-lived, least-privilege, and separate destroy rights.
- [ ] Plaintext secrets never appear in source, images, plan artifacts, or CI logs.
- [ ] Networking, identity, data, and policies provision in dependency order.
- [ ] Images, runtimes, migrations, and seed data use deterministic versions.
- [ ] Drift detection, import/reconciliation, and state recovery procedures are in place.
- [ ] Ephemeral environments have dedicated owners, TTLs, budgets, and identities.
- [ ] Teardown distinguishes ephemeral, persistent, shared, and protected resources.
- [ ] Retained data and keys have backups, retention policies, and deletion protection.
- [ ] Destroy actions require plans, guardrails, proper approvals, and orphan verification.
- [ ] Load, quota, and cost checks run before spinning up multiple environments.
- [ ] Rebuilds, partial failures, state locks, and teardowns have been tested.

Provisioning reproducible environments requires declaring desired state, versioning inputs, managing state, and executing through reviewed pipelines. Safe decommissioning requires classifying lifecycles, protecting data and foundations, verifying dependencies, and confirming resources were actually released. When both workflows are automated and verified together, teams can deliver consistent environments across dev, test, staging, and production while reducing drift, controlling costs, and shrinking operational risk.
