# GitOps and Synchronizing Desired State with Environments

## 1. What Problem Does GitOps Solve?

In cloud environments, an application can comprise deployments, services, ingress rules, network policies, runtime configs, secret references, database migrations, autoscaling rules, and numerous dependencies. When changes are applied manually via consoles or ad-hoc CLI commands, actual state quickly drifts from documentation and it becomes unclear who changed what. A direct hotfix on a cluster can be overwritten by the next pipeline run; conversely, repository configurations may no longer reflect what is serving users.

**GitOps** is an operational practice where declarative system configuration is stored in version control, while one or more controllers continuously observe the repository and target environment, converging actual state toward the approved desired state. Git provides change history, reviews, access controls, and reproducibility; controllers perform continuous or periodic reconciliation.

GitOps typically rests on four principles:

- **Declarative desired state:** describes the intended outcome, such as replica counts, image versions, routing, and policies.
- **Versioned changes:** changes flow through commits, pull requests, reviews, and an auditable history.
- **Automated reconciliation:** controllers compare desired state against actual state and apply necessary corrections.
- **Observable and recoverable operations:** sync status, health, drift, and errors are surfaced; known-good configurations can be restored.

GitOps is not merely storing YAML in Git. A repository without a reconciling controller is just a config store. A pipeline imperatively pushing commands without continuous state comparison also falls short of full GitOps.

In the **CLOUD_ARCHITECTURE** module, GitOps connects software delivery with repeatability, security, reliability, and cloud operations. It excels when managing multiple services, clusters, or environments, provided it is designed alongside database migrations, secret management, infrastructure provisioning, and incident response.

### Learning Objectives

After this lesson, you will be able to:

1. Explain GitOps, desired state, actual state, reconciliation, and drift.
2. Distinguish pull-based GitOps from push-based pipelines.
3. Structure repositories, manifests, and promotions across dev, staging, and production.
4. Design controller scopes, RBAC, trust boundaries, and separation of duties.
5. Manage secret references and encrypted secrets without committing plaintext to Git.
6. Handle drift, manual hotfixes, sync failures, pruning, and rollbacks.
7. Integrate GitOps with progressive delivery, health gates, and database migrations.
8. Establish observability, auditing, policy validation, and runbooks.

## 2. Core Concepts

| Concept | Meaning | Example |
|---|---|---|
| **Source of truth** | Authoritative store of desired configuration | Protected Git repository |
| **Desired state** | Declared target state to achieve | 4 replicas, specific image digest, network policy |
| **Actual state** | Live state currently running in the environment | 3 ready pods, running image |
| **Reconciliation** | Process of comparing and resolving divergence | Controller creates missing pod |
| **Controller / operator** | Component observing and executing reconciliation | GitOps controller, database operator |
| **Drift** | Actual state diverging from desired state | Replicas edited manually |
| **Sync** | Applying or verifying desired state against the cluster | Applying manifests at a selected commit |
| **Health** | Workload condition after syncing | Deployment available and readiness passing |
| **Revision** | Commit, tag, or artifact version being applied | Git SHA or immutable image digest |

### 2.1. Desired State vs. Actual State

Suppose a repository declares a Deployment requiring 4 replicas. The cluster currently runs only 3 pods due to a node failure. The controller detects the discrepancy and instructs Kubernetes to create a replacement replica. The Kubernetes scheduler and controllers work until the target pod count is healthy; the GitOps controller tracks sync and health status to report the outcome.

Crucially, declaring desired state does not guarantee actual state converges. The cluster might lack quotas or nodes, the image registry might be unreachable, admission policies might reject resources, or the application might crash-loop. Controllers retry according to policy, yet alerts and operators are still needed to resolve root causes.

### 2.2. The Reconciliation Loop

~~~mermaid
flowchart TD
    Git["Git repository: desired state"] --> Observe["GitOps controller observes revision"]
    Observe --> Compare["Compare desired vs actual"]
    Compare --> Diff{"Drift / changes?"}
    Diff -->|No| Health["Check sync and health"]
    Diff -->|Yes| Apply["Apply approved configuration"]
    Apply --> Platform["Cluster / cloud APIs"]
    Platform --> Actual["Actual resources and workload"]
    Actual --> Compare
    Health --> Observe
~~~

Reconciliation is a continuous loop, not a one-shot operation. When a resource is accidentally deleted, the controller can recreate it; when a field is edited manually, the controller can overwrite it or flag drift depending on policy.

## 3. Pull-Based GitOps vs. Push-Based Delivery

Two delivery models are commonly compared:

| Criterion | Pull-Based GitOps | Push-Based Pipeline |
|---|---|---|
| Who fetches config? | Controller inside target environment pulls from Git/artifact source | CI/CD runner pushes changes to the target environment |
| Cluster credentials | Typically stay inside target environment/controller | Runners typically require cluster access credentials |
| Network connectivity | Target environment needs outbound access to source/registry per design | Runners need inbound network reachability to target environment APIs |
| Reconciliation | Continuous or periodic | Typically per pipeline run unless paired with another controller |
| Drift correction | Can automatically detect and remediate drift | Typically requires re-running pipeline jobs or separate tooling |
| Auditing | Commits/revisions and controller events | Pipeline runs, identities, and deployment records |
| Primary risks | Over-privileged controllers or compromised config sources | Leaked runner credentials, broad push privileges, state drift |

Pull-based delivery reduces the need to hand cluster credentials to CI runners. However, it is not automatically more secure if controllers hold cluster-admin permissions, repositories lack protection, or Git tokens leak.

### 3.1. Typical Pull-Based Flow

~~~mermaid
sequenceDiagram
    participant Dev as Developer
    participant Git as Git repository
    participant CI as CI validation
    participant Ctrl as GitOps controller
    participant K8s as Target cluster
    Dev->>Git: Push branch / open pull request
    Git->>CI: Trigger tests and policy checks
    CI-->>Git: Validation result
    Dev->>Git: Merge approved change
    Ctrl->>Git: Poll / receive revision notification
    Git-->>Ctrl: Approved desired state
    Ctrl->>Ctrl: Render and compare
    Ctrl->>K8s: Reconcile resources
    K8s-->>Ctrl: Resource status
    Ctrl-->>Git: Status / revision / health evidence
~~~

CI validates changes before merge; the controller inside the target environment performs deployment. Webhooks or notifications speed up change detection, yet the controller must still verify revisions and permissions against trust policies.

## 4. Repositories as Governance Boundaries

Repository organization shapes review permissions, blast radius, promotion flows, and reusability.

### 4.1. Common Repository Patterns

| Pattern | Best Suited When | Trade-Offs |
|---|---|---|
| App repo holding source and deploy configs | Small teams, independent services | Code and production configs share permissions and review cycles |
| Separate platform/environment repo | Multiple services and multiple teams | Must manage mapping from source versions to deployment versions |
| Multi-service monorepo | Coordinated cross-service reviews desired | Large repos, complex CI path filters and ownership rules |
| Repo per team/service | Autonomous teams and independent releases | Policy and template fragmentation without platform standards |
| Bootstrap/platform repo | Managing controllers, cluster add-ons, and baseline policies | Broad blast radius; requires strict permissions and reviews |

No single pattern fits every organization. Balance ownership, environment count, release velocity, shared standards, and auditability.

### 4.2. Reference Structure

~~~text
platform-config/
  bootstrap/
    controllers/
    cluster-baseline/
  apps/
    booking/
      base/
      overlays/
        dev/
        staging/
        production/
    payment/
      base/
      overlays/
        dev/
        staging/
        production/
  policies/
    admission/
    network/
    security/
  clusters/
    dev-a/
    staging-a/
    production-a/
~~~

This structure is illustrative. Real repositories may use Helm charts, Kustomize, Jsonnet, or plain manifests. Explicitly define which paths controllers watch and who can modify each path.

### 4.3. CODEOWNERS and Reviews

Require appropriate owners to review sensitive areas:

- Production overlays: service owners and authorized operators.
- Cluster baselines: platform team.
- Admission/security policies: security and platform reviewers.
- Secret references: workload owners plus security when trust changes.
- Controller configurations: platform administrators.

Branch protection, required status checks, signed commits (where policy requires), `CODEOWNERS`, and protected environments reduce unauthorized modifications.

## 5. Declarative Manifests and Templates

GitOps aligns naturally with declarative configuration. Manifests describe target resources; controllers and platforms determine the sequence of actions to reach that state.

### 5.1. Declarative Deployment Example

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: booking-api
  namespace: production
spec:
  replicas: 4
  selector:
    matchLabels:
      app: booking-api
  template:
    metadata:
      labels:
        app: booking-api
    spec:
      serviceAccountName: booking-api
      containers:
        - name: api
          image: registry.example.invalid/booking-api@sha256:REPLACE_WITH_DIGEST
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /ready
              port: http
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              cpu: "1"
              memory: 1Gi
~~~

This is an illustrative configuration; adjust namespaces, digests, resources, and probes per service. Referencing immutable image digests or versions ensures a given revision deploys the exact tested artifact; mutable tags like `latest` undermine reproducibility.

### 5.2. Templates and Overlays

Base manifests hold shared configuration; overlays or environment values hold intentional differences:

- Dev uses low replicas, policy-governed debug features, and sandbox dependencies.
- Staging mirrors production networking, resources, and integrations closely.
- Production enforces SLO-aligned replicas/headroom, autoscaling, policies, and alerts.

Avoid duplicating entire manifests across environments since copies easily drift. Equally, avoid overly abstract templates that become unreadable or hide defaults altering production behavior.

### 5.3. Render Before Merging

CI should render charts and templates into final manifests and validate:

- Valid YAML and schema conformance.
- Supported Kubernetes/cloud API versions.
- Non-conflicting resource names and namespaces.
- Pinned image digests or immutable versions.
- Reasonable resource requests/limits and probes.
- Security contexts, service accounts, and network policies meeting policy.
- Diffs do not accidentally delete critical resources.

Reviewing template sources alone without inspecting rendered manifests can miss the actual values applied to clusters.

## 6. Promotion Across Dev, Staging, and Production

Promotion advances the exact same release/artifact through environments behind appropriate gates. Never rebuild separate artifacts per environment when the goal is proving the exact tested artifact runs in production.

### 6.1. Promotion Flow

~~~mermaid
flowchart LR
    Source["Source commit"] --> Build["Build immutable artifact"]
    Build --> Test["Unit / integration / security scan"]
    Test --> Dev["Deploy to dev"]
    Dev --> Stage["Promote same digest to staging"]
    Stage --> Verify["E2E / performance / policy gates"]
    Verify --> Approval["Production approval"]
    Approval --> Prod["Promote same digest to production"]
    Prod --> Observe["Observe SLO and business signals"]
~~~

Artifact digests should remain identical across environments; environment configs may vary but must stay versioned and reviewed. If platform constraints ever require separate builds, explicitly link source commits, build provenance, and deployed artifacts.

### 6.2. Promotion Is Not Copying Secrets

Each environment uses isolated secret references and identities. Repositories may store secret names, external secret references, or encrypted representations under approved schemes; never copy production credentials into staging merely to make manifests uniform.

### 6.3. Production Gates

Gates may enforce:

- CI tests, vulnerability scans, and artifact provenance.
- Rendered manifest and policy checks.
- Integration and E2E tests in staging.
- Capacity and performance checks for major changes.
- Database migration readiness and compatibility.
- Risk-calibrated change approvals.
- Post-deploy health checks and SLO observation.

Not every change requires manual approval; low-risk changes can flow automatically, while destructive policy, IAM, network, or database operations need explicit gates.

## 7. Drift Detection and Correction

**Configuration drift** occurs when live environment state diverges from approved configuration. Sources of drift include manual edits, competing controllers, admission mutations, API server defaults, autoscaling, operators, or cloud provider updates.

### 7.1. Classifying Drift

| Drift Type | Example | Handling |
|---|---|---|
| Unauthorized manual change | Editing replicas or images via console/`kubectl` | Alert and reconcile back to Git after verification |
| Emergency hotfix | Raising limits to mitigate an incident | Capture the change back into Git once stabilized |
| Expected dynamic state | HPA adjusting replica counts | Configure controller not to overwrite HPA-managed fields |
| Platform-managed mutation | API defaults or admission webhooks injecting fields | Use diff customization and clear field ownership |
| External dependency update | DNS target or provider setting changes | Sync authoritative source or import state cleanly |
| Resource deletion | Resource accidentally deleted | Recreate if still declared in Git and allowed by policy |

### 7.2. Reconciliation Can Overwrite Dynamic State

If Git declares `replicas: 4` while an HPA scales between 4 and 20, two controllers fight over the same field. Establish explicit field ownership: HPA owns `replicas`, while GitOps owns the HPA spec and other fields. Similarly, operators manage child resources they generate; avoid overlapping declarations.

### 7.3. Manual Hotfixes During Incidents

Some incidents require immediate live intervention to restore service. Follow a structured workflow:

1. Record the incident, actor, target resource, timestamp, and rationale.
2. Apply the minimal reversible change required.
3. Verify impact and confirm service recovery.
4. Open a pull request updating desired state to match.
5. Review and merge after verification.
6. Allow the controller to reconcile and confirm drift clears.

If a hotfix is never committed back to Git, the next reconciliation cycle will revert the fix and re-trigger the incident.

## 8. Sync Policies, Pruning, and Deletion Safety

Controllers can automatically apply updates and delete resources removed from desired state. Deletion privileges require special scrutiny because accidentally pruning a database, namespace, storage volume, or network resource causes data loss or outages.

### 8.1. Sync Modes

- **Manual sync:** operators confirm when changes apply.
- **Auto sync:** controller automatically applies qualifying revisions.
- **Prune:** deletes managed resources no longer present in desired state.
- **Self-heal:** automatically corrects drift when live state changes out of band.
- **Selective sync:** applies only scoped subsets or resources where supported.

Exact names and semantics vary across GitOps controllers. Understand precisely how your controller handles pruning, self-healing, retries, and resource replacement.

### 8.2. Guardrails for Pruning

- Never enable unrestricted auto-pruning across sensitive resources.
- Use protected namespaces/resources or deletion-prevention policies.
- Explicitly review diffs containing deletions.
- Protect stateful databases and storage with retention policies, finalizers, backups, and dedicated procedures.
- Require owners and approvals for destructive deletions.
- Inspect `ownerReferences` and `finalizers` to prevent orphaned retention or cascading deletions.

Git is the configuration source of truth, yet removing a manifest from Git should not imply persistent data can be wiped instantaneously. Persistent data deletion requires dedicated lifecycle policies.

## 9. Secret Management in GitOps

Git histories are long-lived and frequently cloned, forked, or cached. Committing a plaintext secret and deleting it in a follow-up commit still leaves the secret exposed in history.

### 9.1. Secret Management Patterns

| Pattern | How It Works | Notes |
|---|---|---|
| External secret manager | Manifest holds references; controller/runtime fetches secrets from vault | Identities need scoped read access to exact secrets and versions |
| Sealed / encrypted secrets | Repo stores ciphertext; cluster controller decrypts using cluster keys | Protect private keys, rotation, and backups |
| Runtime workload identity | App obtains tokens/secrets from cloud identity endpoints | Never embed credentials in images or Git |
| Deploy/runtime secret injection | Platform or sidecar injects secrets dynamically | Control logs, process environments, and file permissions |

Prefer external secret managers and workload identity. If encrypted secrets must live in Git, guarantee plaintext never leaks into diffs, build logs, rendered artifacts, or debug outputs.

### 9.2. Separating Config and Secrets

Non-secret values—such as service names, default feature flags, or secret references—belong in version control. Actual secret values live outside repositories with independent access policies, rotation, and auditing.

When secrets rotate, consumers must reload or restart appropriately; health checks verify new authentication works; and old keys revoke only after all consumers transition. GitOps controllers do not solve credential lifecycles automatically without dedicated integration.

## 10. RBAC and Controller Trust Boundaries

Controllers typically hold read access to repositories and write privileges inside clusters. If a controller or its credentials are compromised, the blast radius can be massive.

### Design Principles

- Scope each controller/project strictly to required namespaces and clusters.
- Grant service accounts least privilege; separate controller administration from workload deployment permissions.
- Production deployment repos require branch protection, reviews, and verified identities.
- Scope source-read tokens strictly to needed repos and prefer short-lived tokens where supported.
- Enforce network policies limiting controllers to authorized Git, registry, API, and secret manager endpoints.
- Enforce admission policies blocking privileged containers, `hostPath` mounts, untrusted images, and non-compliant resources.
- Audit actors, commit SHAs, controller identities, and resource mutations.
- Never allow application repositories to alter controller trust rules or `cluster-admin` bindings.

### 10.1. Multi-Tenancy

Clusters shared across teams require strict boundaries:

- Namespace/project isolation scopes.
- Team- and service-scoped RBAC.
- Resource quotas and limit ranges.
- Network policies.
- Isolated secrets and dedicated service accounts.
- Policies blocking privilege escalation or cross-ownership edits.

Namespaces alone are not hard security boundaries. Combine RBAC, network isolation, admission policies, and identity controls.

## 11. Multi-Cluster and Multi-Environment GitOps

Across multiple clusters, define what configuration is shared and which variations are permitted.

### 11.1. Management Topologies

- A management/bootstrap cluster reconciles configs across workload clusters.
- Each cluster runs its own local controller to avoid dependence on a single central control plane.
- Repositories hold overlays and cluster inventories; each controller watches only its designated paths.
- Cluster registration and credentials are governed by platform identities—never let app repos register arbitrary targets.

### 11.2. Trade-Offs

| Design | Advantages | Risks / Costs |
|---|---|---|
| Central controller | Centralized governance, fewer moving parts | Large blast radius; network and central control-plane dependency |
| Controller per cluster | Strong fault isolation; clusters reconcile independently | More controller instances to upgrade and monitor |
| Shared config repo | Easy standardization and fleet-wide visibility | Broad repo permissions; mistakes can affect multiple clusters |
| Repo per environment | Crisp approval boundaries | Harder to keep templates synchronized and manage promotions |

Never allow one cluster to grant itself management access over peer clusters simply by committing a manifest without explicit trust boundaries.

## 12. Progressive Delivery with GitOps

GitOps controllers converge desired state; progressive delivery controllers govern how releases roll out to live users step by step.

### 12.1. Rolling, Canary, and Blue–Green

- **Rolling updates:** replace replicas incrementally, keeping partial legacy capacity active.
- **Canary:** route a small traffic slice to the new version, evaluate metrics, and expand gradually.
- **Blue–green:** run two environments or replica sets and switch traffic once gates pass.

~~~mermaid
flowchart TD
    Commit["Approved release revision"] --> DeployCanary["Deploy canary"]
    DeployCanary --> Smoke["Smoke / readiness checks"]
    Smoke --> Metrics["Observe error, latency, business SLI"]
    Metrics --> Decision{"Pass analysis?"}
    Decision -->|Yes| Increase["Increase traffic / continue rollout"]
    Increase --> Complete["Promote to 100%"]
    Decision -->|No| Abort["Abort / rollback traffic"]
    Abort --> Stable["Keep stable version"]
~~~

### 12.2. Metrics to Evaluate

- Error rates and p95/p99 latencies.
- Resource saturation and restart counts.
- Business conversions, payment successes, or job completion rates.
- Dependency errors and queue age.
- Data correctness and reconciliation when releases mutate data.

Relying solely on CPU or pod readiness never proves a canary is safe. A release can pass readiness while miscalculating prices or creating duplicate bookings.

### 12.3. Rollback

Application rollback may involve reverting a manifest/image digest or shifting traffic back to the stable release. However, rolling back does not automatically reverse database schema/data migrations or external side effects. Always design backward-compatible migrations and forward-fix strategies.

## 13. Database Migrations and Stateful Workloads

GitOps excels at declarative resources, yet it does not turn every stateful mutation into a harmless idempotent `apply`.

### 13.1. Expand–Migrate–Contract

1. Expand: add schemas, fields, or indexes compatibly with old versions.
2. Deploy application versions supporting both old and new schemas.
3. Migrate: backfill/transform data with checkpoints and reconciliation.
4. Shift traffic and code to the new schema.
5. Contract: drop legacy structures only after all consumers migrate and approval is granted.

Migration jobs need dedicated identities, locking/idempotency, timeouts, status reporting, and runbooks. Never trigger destructive migrations automatically merely because a manifest merged into Git.

### 13.2. StatefulSets and Persistent Storage

GitOps can manage StatefulSets, PVC templates, StorageClasses, and operator configurations. Still:

- Understand PVC lifecycles and reclaim policies thoroughly.
- Deleting a claim or workload must not silently destroy vital data.
- Backups, restores, and consistency checks require dedicated workflows.
- Operators may generate child resources outside initial manifests.
- Version upgrades may enforce strict ordering and compatibility rules.

Never enable broad auto-pruning across persistent volumes or database resources without deletion protection and verified backups.

## 14. Policy-as-Code and Pre-Reconciliation Validation

Every manifest shapes security posture, cost, and reliability. Enforce policy checks both pre-merge and at admission/runtime.

### 14.1. Validation Layers

- Syntax and schema validation.
- Template/chart linting and API compatibility checks.
- Security policies: `runAsNonRoot`, read-only root filesystems, Linux capabilities, image trust.
- Resource policies: requests/limits, quotas, replica floors and ceilings.
- Network policies: least-privilege ingress and egress rules.
- IAM/RBAC: prohibit wildcards/admin bindings and cross-namespace escalation.
- Compliance policies: encryption, regions, labels, retention, auditing.
- Change risk: deletions, secret references, public exposure, and data migrations.

### 14.2. Two Layers of Defense

CI policy checks give fast feedback before merging; admission policies re-verify when resources are created or updated. CI alone can be bypassed or outdated relative to cluster state; admission alone catches defects too late, causing reconciliation failures and delays.

Policy exceptions require owners, justifications, expiration dates, and reviews—avoid permanent "skip policy" annotations.

## 15. Observability for GitOps

GitOps observability spans the source repository, controllers, and target environments.

| Metric / Event | Meaning |
|---|---|
| Sync status | Whether desired revision is applied or pending/out-of-sync |
| Health status | Whether workloads and resources are healthy |
| Reconciliation duration | Time elapsed from commit to converged desired state |
| Drift count | Number of resources diverging from desired state |
| Failed sync count | Number of failed apply or reconciliation attempts |
| Reconciliation retries | Whether controllers are stuck in error retry loops |
| Revision age | How long an environment has run an older commit |
| Deployment lead time | Time from merge to usable release |
| Rollback frequency | How often releases require reverting |
| Prune / deletion events | Which resources were deleted and by which revision |
| Controller health / queue | Whether controllers keep pace with incoming changes |

### 15.1. Questions Dashboards Should Answer

1. Which revision is each environment currently running?
2. Did the latest revision pass CI and reviews?
3. Is there out-of-band drift outside Git? Which resources, and who altered them?
4. Where is reconciliation waiting or failing?
5. Where have workloads synced successfully yet remain unhealthy?
6. Have any destructive prunes or policy denials occurred?
7. Did the release affect business SLIs or dependencies?

### 15.2. Alerts

- Production remains out of sync with the approved revision beyond target SLA.
- Drift detected on sensitive resources or unapproved out-of-band changes.
- Controller loses connectivity to Git, registries, or cluster APIs.
- Repeated reconciliation failures, growing queues, or API throttling.
- Workloads synced cleanly yet fail health checks.
- Unexpected prune or deletion events.
- Production running a revision older than policy allows or referencing a revoked artifact.

Avoid noisy alerts on benign diffs. Separate fields managed by autoscalers/operators and API defaults from genuine drift.

## 16. Incident Response and Runbooks

When GitOps leaves an environment out of sync or deploys a faulty release:

1. Identify the affected cluster/environment, application, revision, and controller.
2. Inspect sync status, health status, rendered diffs, and resource events.
3. Determine whether the change came from Git, manual mutation, another controller, or platform defaults.
4. If a release is defective, halt further promotion/rollouts and preserve evidence.
5. Choose manifest/image rollback or forward-fix, accounting for migrations and stateful side effects.
6. If an emergency hotfix is applied live, log exact details and update Git right after stabilization.
7. Check whether the controller will overwrite the hotfix; use time-bounded, audited sync suspension if needed.
8. Reconcile cleanly from the approved revision.
9. Verify workload health, business SLIs, zero unintended drift, and controller stability.
10. Document root cause, commit, actor, impact, and corrective actions.

Never delete controllers or disable self-heal permanently as a workaround. If pausing reconciliation is necessary during an incident, assign an owner, scope, and re-enable criteria.

## 17. Common Mistakes

| Mistake | Consequence | Remediation |
|---|---|---|
| Storing YAML in Git and calling it GitOps | No continuous reconciliation or drift correction | Run controllers and monitor sync/health |
| Giving CI runners `cluster-admin` credentials | Compromised runners compromise entire clusters | Use pull-based controllers, short-lived identities, and RBAC |
| Single controller managing every namespace | Massive blast radius | Scope by project/namespace with least privilege |
| Mutable image tags | Same revision deploys different artifacts | Pin immutable digests or versions |
| Copying full manifests across environments | Config divergence and unverified promotions | Use bases/overlays and promote identical artifacts |
| Committing plaintext secrets then deleting later | Secrets remain exposed in Git history | Use secret managers, encrypted workflows, and rotation |
| Unrestricted auto-pruning | Accidental deletion of stateful resources | Enforce deletion guards, approvals, and backups |
| Git and HPA both managing `replicas` | Controllers fight and create perpetual drift | Define explicit field ownership |
| Treating sync success as release success | Apps may be unhealthy or break business logic | Enforce health, SLO, and business gates |
| Rolling back apps without checking DB migrations | Old code breaks against new schemas | Use expand–migrate–contract and recovery plans |
| Hotfixes never committed back to Git | Next reconcile undoes the fix | Require emergency-change PRs back to Git |
| Unpinned controller/API versions | Upgrades silently alter manifest semantics | Pin versions, test compatibility, and upgrade in stages |
| Zero controller observability | Silent drift and prolonged sync failures | Build dashboards, alerts, and runbooks |

## 18. Case Study: Multi-Environment GitOps for a Booking Platform

**Context:** A booking platform runs the Booking API, Payment Service, Notification Worker, and Inventory Service across dev, staging, and production on separate clusters. Currently, CI builds images and uses a broad `kubeconfig` to deploy. Emergency hotfixes are applied directly with `kubectl` and never committed back.

### 18.1. Target Architecture

~~~mermaid
flowchart TD
    Dev["Developer"] --> PR["Protected pull request"]
    PR --> CI["CI: tests, scan, render, policy"]
    CI --> Merge["Approved merge"]
    Merge --> Config["Environment config repo"]
    Config --> DevCtrl["Dev GitOps controller"]
    Config --> StageCtrl["Staging GitOps controller"]
    Config --> ProdCtrl["Production GitOps controller"]
    DevCtrl --> DevCluster["Dev cluster"]
    StageCtrl --> StageCluster["Staging cluster"]
    ProdCtrl --> ProdCluster["Production cluster"]
    Registry["Immutable image registry"] --> DevCluster
    Registry --> StageCluster
    Registry --> ProdCluster
    Vault["Secret manager"] --> DevCluster
    Vault --> StageCluster
    Vault --> ProdCluster
    ProdCluster --> Telemetry["SLO / business / infrastructure telemetry"]
~~~

### 18.2. Release Flow

1. Developers commit code and open PRs.
2. CI runs unit/integration tests, dependency/image scans, manifest rendering, and policy checks.
3. Artifacts publish with immutable digests.
4. A PR updates the digest/config for dev; the dev controller reconciles.
5. E2E tests pass in dev, then the exact same digest promotes to staging.
6. Staging runs integration, performance, and migration compatibility checks.
7. Production overlays undergo risk-appropriate review and approval.
8. The production controller reconciles while progressive delivery shifts traffic incrementally.
9. SLOs, payment success, booking confirmations, and dependency metrics are monitored.
10. If gates fail, halt rollout and roll back traffic/manifests per runbook, checking migrations before reverting code.

### 18.3. Handling Hotfixes

If production requires scaling replicas during an incident:

- Operators log the incident ID, resource, and exact change.
- Apply the minimal emergency change needed.
- The controller may report drift; policy determines whether to suspend briefly or reconcile after assessment.
- Once stabilized, open a PR reflecting the updated desired state.
- Review, merge, and verify the controller reconciles cleanly.
- Close the incident once unintended drift clears and SLOs recover.

### 18.4. Acceptance Criteria

- CI runners hold zero production cluster-admin credentials.
- Each environment reconciles only registered paths and targets.
- Releases promote the identical image digest across dev, staging, and production.
- PRs enforce required reviews, rendered manifest checks, and policy validation.
- Production secrets never enter Git or leak into staging.
- Drift is detected, classified, and resolved by owners.
- Pruning cannot automatically delete critical databases or PVCs.
- Rollbacks are rehearsed alongside database migrations and progressive delivery.
- Dashboards clearly show revisions, sync status, health, drift, and business SLIs.

## 19. GitOps Review Checklist

### Source of Truth and Repositories

- [ ] Repositories, branches, and paths have clear owners and protections.
- [ ] Desired state is declarative, versioned, and reviewable.
- [ ] Images and artifacts reference digests or immutable versions.
- [ ] Bases/overlays or templates follow clean, readable structures.
- [ ] Rendered manifests are validated prior to merge.

### Controllers and Trust

- [ ] Pull vs. push model aligns with network and threat models.
- [ ] Controllers hold least privilege scoped to clusters, namespaces, and projects.
- [ ] Git, registry, and secret credentials are protected and rotated.
- [ ] RBAC, admission policies, and multi-tenant boundaries are enforced.
- [ ] Field ownership across GitOps, HPAs, operators, and platforms is unambiguous.

### Reconciliation and Recovery

- [ ] Sync, self-heal, prune, and retry semantics are explicitly configured.
- [ ] Destructive deletions require guardrails, backups, and approvals.
- [ ] Drift is monitored with runbooks and emergency hotfix reconciliation processes.
- [ ] Application rollbacks do not corrupt databases or persisted state.
- [ ] Stateful workloads have dedicated retention, backup, and migration policies.

### Delivery and Observability

- [ ] Promotions carry the identical artifact digest across environments.
- [ ] Progressive delivery enforces health, technical, and business gates.
- [ ] No plaintext secrets appear in Git, logs, or rendered artifacts.
- [ ] Dashboards track revisions, sync status, health, drift, reconcile duration, and SLOs.
- [ ] Alerts specify owners, severities, and runbooks.
- [ ] Controller upgrades and API compatibility are tested prior to production.

## 20. Hands-On Exercise

**Context:** A company runs three clusters: dev, staging, and production. Currently, CI deploys using an admin `kubeconfig`; production is frequently edited manually during incidents; images use the `latest` tag; charts contain plaintext secrets; HPAs scale replicas while Git manifests also hardcode fixed replica counts; and auto-prune is enabled globally for all resources.

Redesign the operating model:

1. Choose pull-based or push-based delivery and explain network and credential boundaries.
2. Design repository and path layouts for apps, environment overlays, cluster baselines, and policies.
3. Define branch protections, `CODEOWNERS`, and production approvals.
4. Replace `latest` with artifact digests and describe same-artifact promotion across environments.
5. Design workload identities for controllers and secret manager integration.
6. Define explicit field ownership between GitOps and HPAs.
7. Partition controller scopes and write RBAC and admission policy rules.
8. Design drift/hotfix reconciliation and pruning guardrails.
9. Propose progressive delivery, health/SLO gates, and rollback handling alongside DB migrations.
10. Design dashboards, alerts, and runbooks for sync failures, drift, and unexpected deletions.

**Self-Check Hint:** Git is a true source of truth only when repositories are protected and actively reconciled by controllers. Auto-sync does not mean every change is safe; pruning can destroy data. Image rollbacks do not undo external side effects or schema migrations. HPAs and GitOps must never contend over the same field.

## 21. Key Takeaways

GitOps uses versioned, reviewed declarative configuration as desired state; controllers continuously compare it against actual state and reconcile differences. Pull-based delivery keeps deployment credentials inside target environments and enables drift correction, yet real security depends on controller privileges, source trust, and repository governance.

A sound implementation requires repository/path ownership, immutable artifacts, gated promotions, externalized secret management, least-privilege RBAC, unambiguous cross-controller field ownership, deletion safety, and deep observability. Successful reconciliation alone does not prove a healthy release; monitor health, SLOs, and business metrics. Hotfixes must always flow back into Git, while database migrations and persistent data require dedicated recovery procedures. GitOps delivers value when changes become traceable, repeatable, controlled, and recoverable without endangering workload safety.
