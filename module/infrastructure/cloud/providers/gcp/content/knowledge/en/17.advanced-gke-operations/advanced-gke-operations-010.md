# Config Sync and Policy Controller

> **Chapter:** Advanced GKE and Operations  
> **Module:** CLOUD_PROVIDERS_GCP

When an organization runs multiple **Google Kubernetes Engine (GKE)** clusters, manual `kubectl apply` easily causes drift across clusters: namespaces miss owner labels, RBAC rules get altered out-of-band, or workloads deploy in violation of security policies. Two integrated GKE tools solve **two complementary problems**:

- **Config Sync** synchronizes Kubernetes configurations from a **source of truth** (Git, OCI artifact, or Helm chart), detecting and reconciling *configuration drift*.
- **Policy Controller** validates Kubernetes resources using **constraints**: auditing violations or rejecting operations when required policies are not met.

This lesson belongs to the **CLOUD_PROVIDERS_GCP** module, spanning projects, IAM, VPCs, Compute Engine, GKE, Cloud Run, storage, databases, release automation, and reliability/cost monitoring. In the **Advanced GKE and Operations** chapter, we design a GitOps workflow for namespace `orders-lab`, then use Policy Controller to require an `owner` label on namespaces. The emphasis is **separating responsibilities, rolling out safely, and verifying real behavior**—not merely toggling two features on.

**After this lesson, you will be able to:**

1. Explain the Git → Config Sync → Kubernetes API flow and Policy Controller audit/admission paths.
2. Distinguish `RootSync`, `RepoSync`, `ConstraintTemplate`, `Constraint`, and policy bundles.
3. Design a GitOps source of truth, split platform/application team permissions, and prevent ownership collisions.
4. Configure Config Sync via fleet/Console and a Git-backed `RootSync`.
5. Author a `K8sRequiredLabels` constraint, test it in `dryrun` mode, and only then evaluate `deny`.
6. Monitor sync status, `KNV...` errors, violations, admission failures, and drift.
7. Build rollback runbooks, validation checks, and assess impacts on SLOs, security, and cost.

## 1. The Problem: Correct Configuration and Compliant Policy Are Not the Same

Suppose an enterprise runs three GKE clusters:

| Cluster | Purpose | Risk with manual management |
| --- | --- | --- |
| `gke-dev` | Development | Namespaces and RBAC created ad hoc |
| `gke-staging` | Testing | Drifts away from production configuration |
| `gke-prod` | Live customers | Operators patch directly, hard to audit |

Goal: every application namespace must carry an `owner` label identifying accountability; `Namespace`, `ResourceQuota`, `NetworkPolicy`, and `RoleBinding` configs are reviewed in Git and rolled out consistently.

~~~mermaid
flowchart LR
  DEV["Pull request + code review"] --> GIT["Git / OCI / Helm\nApproved config source"]
  GIT --> SYNC["Config Sync\nFetch · Render · Reconcile"]
  SYNC --> API["Kubernetes API\nGKE Cluster"]
  POL["Policy Controller\nConstraints + Audit"] -. "Admission checks create/update" .-> API
  POL -. "Audits existing resources" .-> REPORT["Violations / Logs / Metrics"]
  API --> STATE["Namespace · RBAC · Quota · Workloads"]
  STATE -. "Drift from manual edits" .-> SYNC
~~~

**Config Sync asks:** "Does live cluster state match the configuration managed in source?" **Policy Controller asks:** "Does this operation or resource comply with policy?" Both tools work independently; pairing them **delivers approved configurations** and **enforces guardrails**. <https://docs.cloud.google.com/kubernetes-engine/config-sync/docs/overview> ; <https://docs.cloud.google.com/kubernetes-engine/policy-controller/docs/overview>

### 1.1. Specific Responsibilities

| Aspect | Config Sync | Policy Controller |
| --- | --- | --- |
| Inputs | Git repository, OCI image, Helm chart | `ConstraintTemplate`, `Constraint`, policy bundles |
| Core action | Continuously reconciles and applies desired state | Audits resources; checks create/update at admission |
| When a resource is edited manually | Reconciles back to desired state | Intervenes only if a matching constraint is violated |
| When a manifest in Git is wrong | May fail to sync or apply the flawed config | Can block non-compliant changes if policy & admission cover it |
| When legacy objects violate policy | Config Sync has no awareness of unencoded rules | Audit reports violations; does not auto-fix every object |
| Key permissions | Read source, reconcile resources in cluster | Privileged webhook/controller; policy admin rights |
| Evidence | Git revision, sync status, resource inventory | Constraint status, violations, audit/admission logs |

**Does not replace other security layers:** Policy Controller does not enforce least-privilege IAM on Google Cloud projects, nor replace Binary Authorization, network policies, workload identity, secret management, or vulnerability scanning. Config Sync is likewise not a Git/etcd backup system or database rollback tool.

## 2. Config Sync: GitOps Synchronization

**GitOps** uses version control as the store for **desired configuration**. With Config Sync, a reconciler watches the source, renders manifests, and calls the Kubernetes API to create, update, or delete managed resources.

~~~text
Git commit R1:
  namespace orders-lab has owner=orders-team
       ↓
Config Sync applies R1 to the cluster
       ↓
Someone edits owner=unknown directly with kubectl
       ↓
Config Sync detects drift and restores owner=orders-team
~~~

This does **not** mean Config Sync always heals instantly. Sync runs periodically and can fail due to Git auth, networking, API server, RBAC, admission webhooks, or competing controllers. Tracking *which revision is applied* matters more than inspecting a single Pod in a namespace.

### 2.1. Source Types

| Source of truth | When appropriate | Notes |
| --- | --- | --- |
| **Git** | Standard PR reviews, history, branching, and rollouts | Config Sync needs read-only access; protect credentials/branches |
| **OCI image** | Packaging manifests as digest-pinned artifacts | Publish pipeline, Artifact Registry permissions, and identity |
| **Helm chart** | Chart- and values-driven configs where supported | Helm source setup has Console/`gcloud` differences; can configure `RootSync`/`RepoSync` via Kubernetes API |

**Never commit Git credentials or plaintext secrets into the repository.** Config Sync needs read access to the source; synchronized Kubernetes resources still require proper secret management.

### 2.2. `RootSync` and `RepoSync`

| Resource | Scope | Example usage |
| --- | --- | --- |
| **RootSync** | Cluster-level reconciler; can manage cluster-scoped and namespaced resources | Platform team managing Namespaces, RBAC, ResourceQuotas, Policy Controller constraints |
| **RepoSync** | Namespace-scoped reconciler; limited to namespaced resources in that namespace | Application team managing ConfigMaps, Deployments, Services in its own namespace |

- `RootSync` lives in system namespace `config-management-system`; default Config Sync installation can create a `root-sync` object.
- `RepoSync` lives inside the namespace it manages, paired with appropriate RBAC and source ownership.
- A cluster can use multiple sources, but **never let two reconcilers own the same object**. Colliding on `group/kind/namespace/name` triggers error `KNV1060`.
- Do not expect an app team to create a cluster-scoped `Namespace` via a namespace-scoped `RepoSync`.

**Ownership principle:** the platform repo creates namespaces and guardrails; app repos manage workloads inside those namespaces. Git permissions, Kubernetes RBAC, and Config Sync reconcilers must align.

## 3. Policy Controller: Audit and Admission

**Policy Controller** builds on Open Policy Agent Gatekeeper and ships libraries of **`ConstraintTemplates`**, constraints, policy bundles, and compliance observability. A template defines the rule logic and parameters; a concrete **Constraint** selects target resources and parameter values.

Example:

~~~text
ConstraintTemplate: K8sRequiredLabels
    |
    +-- Constraint "namespaces-must-have-owner"
            match: kind Namespace
            parameters.labels: owner
            enforcementAction: dryrun | warn | deny
~~~

### 3.1. Three Enforcement Actions

| Mode | On admission violation | When to use |
| --- | --- | --- |
| `dryrun` | Allows request; logs violations for evaluation | Default when testing new rules |
| `warn` | Allows request; returns an admission warning | Migration periods / notifying teams |
| `deny` | Rejects the violating request | Only after baselines, exemptions, and rollout approvals exist |

**If `spec.enforcementAction` is omitted, it defaults to `deny`.** Always specify `dryrun` explicitly when introducing new constraints onto clusters with live workloads. <https://docs.cloud.google.com/kubernetes-engine/policy-controller/docs/how-to/auditing-constraints>

### 3.2. Admission vs. Audit

- **Admission:** webhook evaluates operations sent to it by the Kubernetes API, typically create/update. `deny` blocks violating new objects or edits; **it does not delete existing non-compliant objects**.
- **Audit:** periodically scans existing cluster resources and records violations; useful for uncovering legacy drift.
- **Reliability:** per current docs, Policy Controller's webhook **fails open** when the controller is down so the cluster doesn't wedge. Do not treat it as an unbreakable guarantee that every call is blocked at all times.
- **Referential constraints:** rules referencing other objects rely on an in-memory cache and **eventual consistency**; never assume distributed transactional guarantees.

For critical controls, combine **CI policy validation**, Kubernetes RBAC, audits, admission monitoring, and other GKE/Google Cloud guardrails.

## 4. Lab Setup and Safety Principles

This lab assumes an **existing test GKE cluster** already registered to a **fleet**. Never create or modify production clusters for practice.

| Input | Illustrative value |
| --- | --- |
| Project | `LAB_PROJECT_ID` |
| GKE cluster | `gke-policy-lab` |
| Fleet membership | `gke-policy-lab` |
| Namespace | `orders-lab` |
| Git repository | `https://github.com/ORG/gke-config-lab.git` |
| Git directory | `clusters/lab` |
| Required label | `owner` |
| Constraint | `namespaces-must-have-owner` |

**Prerequisites:**

1. Sufficient permissions to enable fleet features, configure sync, and create constraints; grant specific IAM rather than project-wide Owner.
2. `gcloud`, `kubectl`, and `nomos` available; kubecontext pointing to the lab cluster.
3. Required APIs enabled per documentation, with quotas and costs approved.
4. A lab Git repo with the proper branch/revision and manifests; `auth: none` is **for public Git repos only**. For private repos, use SSH/tokens/GitHub Apps or supported Workload Identity auth.
5. No separate open-source Gatekeeper installed alongside Policy Controller unless supported; verify Autopilot/Standard support before enabling mutations or exemptions.
6. Never casually test blocking on system namespaces (`kube-system`, `gatekeeper-system`, `config-management-system`). Scope lab policies strictly to designated test targets.
7. Record prior configuration and owners; start every policy in **`dryrun`**.

**Operation warning:** `enable`, `apply`, and `delete` commands below mutate cluster/fleet state. Lab examples are for learning—never run them in production without change approval and a rollback plan.

## 5. Installing Config Sync and Connecting the Source of Truth

### 5.1. Check State Before Enabling

~~~bash
gcloud config get-value project
gcloud container fleet memberships list --project=LAB_PROJECT_ID
gcloud container clusters list --project=LAB_PROJECT_ID

# Existing Kubernetes resources (read-only, verified kubecontext)
kubectl config current-context
kubectl get ns orders-lab --ignore-not-found
kubectl get rootsync -n config-management-system
~~~

If the `RootSync` CRD is not installed yet, the last command reports an unknown resource type; that signals you need to check feature installation—not install an untrusted CRD manifest.

### 5.2. Console Installation

In Google Cloud Console, navigate to **GKE → Config** or **Config Sync** per current UI, select **Install Config Sync** for your fleet or registered lab cluster, and deploy a package from your source of truth. Monitor installation and Git sync status. The Console can register cluster membership automatically when selecting a cluster.

This is convenient for fleets; for custom `RootSync` and multi-repo setups, use the Google Cloud Kubernetes API configuration guides.

### 5.3. Example Installation via gcloud Fleet

To keep the lab steps consistent, we **enable the feature first and configure the source second**. Per current `gcloud` docs, create `apply-spec.yaml`:

~~~yaml
applySpecVersion: 1
spec:
  configSync:
    enabled: true
~~~

Once the cluster belongs to the fleet, an authorized administrator runs:

~~~bash
# Modifies fleet/cluster: run ONLY in lab
gcloud beta container fleet config-management enable \
  --project=LAB_PROJECT_ID

gcloud beta container fleet config-management apply \
  --membership=gke-policy-lab \
  --config=apply-spec.yaml \
  --project=LAB_PROJECT_ID
~~~

Verify:

~~~bash
gcloud beta container fleet config-management status \
  --project=LAB_PROJECT_ID

kubectl get rootsync -n config-management-system
~~~

If your CLI version or fleet setup differs, run `gcloud beta container fleet config-management --help` and check current installation docs—**do not** assume all versions share identical subcommands and flags. <https://docs.cloud.google.com/kubernetes-engine/config-sync/docs/how-to/installing-config-sync>

### 5.4. Configuring a Git-Backed RootSync

Create or update the `RootSync` object **in the lab environment** using `root-sync.yaml`:

~~~yaml
apiVersion: configsync.gke.io/v1beta1
kind: RootSync
metadata:
  name: root-sync
  namespace: config-management-system
spec:
  sourceType: git
  sourceFormat: unstructured
  git:
    repo: https://github.com/ORG/gke-config-lab.git
    revision: main
    dir: clusters/lab
    auth: none
    period: 60s
~~~

This illustrative config **works only if** the Git repository is genuinely public and contains manifests in that directory. For private sources, replace `auth: none` with a supported auth method and configure credentials/identity per docs (never put secrets in Git). For OCI or Helm sources, use their respective fields instead of `git.repo`.

~~~bash
# Mutates cluster: points Config Sync to the lab Git source
kubectl apply -f root-sync.yaml

# Read status
kubectl get rootsync root-sync -n config-management-system -o yaml
nomos status
~~~

If installed via Console/fleet defaults with centralized configuration, standardize on **one ownership path** so another automation tool doesn't overwrite `RootSync`.

### 5.5. Minimal Repo Layout

~~~text
gke-config-lab/
  clusters/
    lab/
      namespace-orders.yaml
      quota-orders.yaml
      constraint-owner.yaml        # add after Policy Controller is ready
~~~

`namespace-orders.yaml`:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: orders-lab
  labels:
    owner: orders-team
    environment: lab
~~~

`quota-orders.yaml`:

~~~yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: orders-quota
  namespace: orders-lab
spec:
  hard:
    pods: "10"
    requests.cpu: "4"
    requests.memory: 8Gi
~~~

Commit and push **reviewed** manifests to Git; Config Sync fetches, parses, and applies them. Ensure `ResourceQuota` allows enough headroom for Pods in the namespace; overly tight quotas prevent new workloads from scheduling.

## 6. Verifying Sync and Drift Remediation

Use `nomos status` to verify the reconciler fetched and applied the revision, rather than merely checking if the feature is installed:

~~~bash
nomos status

kubectl get ns orders-lab --show-labels
kubectl get resourcequota orders-quota -n orders-lab

kubectl get rootsync root-sync -n config-management-system \
  -o yaml
~~~

When you change `owner` in Git and commit, Config Sync updates the namespace after polling the new revision. To demonstrate drift remediation **only on your lab-owned namespace**, edit the label directly and watch it revert:

~~~bash
# Mutates resource; NEVER run on a production namespace
kubectl label namespace orders-lab owner=manual-change --overwrite

# Read-only checks to watch reconciliation
kubectl get ns orders-lab --show-labels
nomos status
~~~

**Never expect drift to heal instantaneously**; timing depends on fetch interval, API server reconciliation, permissions, and source errors. Manual changes to resources **outside Config Sync's scope** will not be reconciled by it.

To **undo** a bad desired-state push, prefer **reverting the Git commit** and letting the reconciler apply it. Manual `kubectl` edits will be overwritten. Before deleting a manifest from source, check **pruning/deletion** behavior and blast radius; removing a Namespace file from Git can tear down everything inside it.

## 7. Installing Policy Controller and Checking the Template Library

### 7.1. Enable the API and Controller via Fleet

After confirming the cluster belongs to the fleet, an admin can run:

~~~bash
# Modifies project and fleet; lab use only
gcloud services enable anthospolicycontroller.googleapis.com \
  --project=LAB_PROJECT_ID

gcloud container fleet policycontroller enable \
  --memberships=gke-policy-lab \
  --project=LAB_PROJECT_ID
~~~

Verify status:

~~~bash
gcloud container fleet policycontroller describe \
  --memberships=gke-policy-lab \
  --project=LAB_PROJECT_ID

kubectl get constrainttemplates
kubectl get pods -n gatekeeper-system
~~~

Fleet metadata may show `ACTIVE` before the controller and template library finish starting up. Policy Controller configures at the fleet level and may have **fleet defaults**. Avoid turning it on across every cluster when practicing on one membership.

Per documentation, the template library installs by default; verify with `kubectl get constrainttemplates`. If `K8sRequiredLabels` is not present yet, **do not apply a constraint referencing it** until the template is ready. <https://docs.cloud.google.com/kubernetes-engine/policy-controller/docs/how-to/installing-policy-controller>

### 7.2. Caution with Advanced Settings

- **Mutating webhooks** and certain exemption options have limitations on GKE Autopilot; check official docs before enabling.
- **Referential constraints** rely on object cache sync and can lag; never assume they are as strongly consistent as single-object admission checks.
- Policy Controller adds admission webhook latency and load to the Kubernetes API; monitor before scaling out.
- Do not install standalone OPA Gatekeeper alongside Policy Controller in the same cluster unless explicitly supported.

## 8. Writing a Constraint Requiring the `owner` Label

Once Policy Controller and its template library are ready, create a `K8sRequiredLabels` constraint. To avoid impacting system namespaces, **scope the example strictly to the test namespace** `orders-policy-test`.

`constraint-owner.yaml`:

~~~yaml
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sRequiredLabels
metadata:
  name: lab-namespace-require-owner
spec:
  enforcementAction: dryrun
  match:
    kinds:
      - apiGroups: [""]
        kinds: ["Namespace"]
    namespaces: ["orders-policy-test"]
  parameters:
    labels:
      - key: owner
~~~

**Key fields explained:**

- `kind: K8sRequiredLabels`: references the built-in template; wait until the CRD/template is ready.
- `match.kinds`: evaluates **Namespace** objects (core API group).
- `match.namespaces`: for Namespace resources, Gatekeeper treats each namespace as belonging to itself; here it targets only `orders-policy-test`.
- `parameters.labels`: requires label key `owner`; you can add `allowedRegex` per the template schema to constrain values.
- `enforcementAction: dryrun`: observes violations first **without blocking**.

**Scope distinction:** this inspects only the metadata labels of the **Namespace** object itself—it does not inspect Pods or Deployments inside that namespace. Evaluating workloads requires a separate constraint/scope.

### 8.1. Managing the Constraint with Config Sync

If the platform team uses `RootSync` pointing to `clusters/lab`, **commit the constraint into that Git directory after Policy Controller is installed** so Config Sync reconciles it.

~~~text
clusters/lab/
  namespace-orders.yaml
  quota-orders.yaml
  constraint-owner.yaml
~~~

When a constraint is **owned by Config Sync**, never run `kubectl patch` directly to flip `dryrun → deny`: the next sync reverts it back to Git. Make the change via a Git pull request to preserve auditability.

Use `kubectl apply -f constraint-owner.yaml` directly only in a test cluster where Config Sync does not manage that constraint. Never manage **the exact same constraint** through both manual commands and a GitOps source of truth.

### 8.2. Testing in `dryrun` Mode

Create `bad-namespace.yaml` on your **lab workstation**:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: orders-policy-test
  # Intentionally missing the owner label
~~~

Once the constraint is synced:

~~~bash
# Mutates lab cluster: creates a namespace without owner
kubectl apply -f bad-namespace.yaml

# Read the Constraint and audit results
kubectl get k8srequiredlabels lab-namespace-require-owner -o yaml
kubectl get ns orders-policy-test --show-labels
~~~

In `dryrun` mode, Kubernetes **accepts** the non-compliant namespace; after an audit cycle, the Constraint updates `status` fields such as `totalViolations` or `violations`. Audit findings may not appear instantaneously after `kubectl apply`.

### 8.3. Switching to `deny` After Evaluation

After verifying scope, reviewing exemptions, and obtaining approval, update **in Git**:

~~~yaml
spec:
  enforcementAction: deny
~~~

This is an **illustrative diff snippet**, not a full manifest; keep the remaining fields unchanged. After Config Sync reconciles, verify live mode with `kubectl get k8srequiredlabels ... -o yaml`.

Notice that the **already existing** `orders-policy-test` namespace missing `owner` **is not automatically deleted**. However, an **update** operation triggering the admission webhook on the still-unlabeled object can now be rejected. Test safely in the lab:

~~~bash
# Server-side check; saves nothing if --dry-run=server is supported
kubectl label namespace orders-policy-test stage=deny-test \
  --overwrite --dry-run=server
~~~

Expect the server to reject the request because the object still lacks `owner`. Next, supply a valid `owner` label and confirm behavior:

~~~bash
# Only after clean dry-run testing, add the actual label to the LAB namespace
kubectl label namespace orders-policy-test owner=orders-team

kubectl get ns orders-policy-test --show-labels
~~~

**Warning:** enforcing `deny` across all `Namespace` objects cluster-wide can break add-ons and system tooling. This lab deliberately scopes to a single namespace and is not a complete production policy. For production, design exemptions, label standards, admission workflows, audits, and migration plans with your security team.

### 8.4. Testing Conditions Properly and Avoiding False Positives

- Never flip a new constraint straight to `deny` just because the YAML passed syntax checks.
- Never apply `enforcementAction: deny` to a real cluster before validating scope and exemptions.
- Distinguish a new **admission denial** from an **audit violation** on an existing resource.
- If using `warn` during transition, warnings do not block deployments—track remaining violations down to zero.
- For constraints with multiple parameters or cross-object dependencies, inspect the `ConstraintTemplate` schema and account for eventual consistency.

## 9. Safe Multi-Cluster Rollouts

A minimal pipeline:

~~~mermaid
flowchart TD
    PR["PR updating config/constraint"] --> CHECK["Schema + Policy review + security checks"]
    CHECK --> DEV["Git source for lab cluster"]
    DEV --> DRY["Policy Controller dryrun/warn\nConfig Sync confirms Synced"]
    DRY --> RISK{"Any violations or sync errors?"}
    RISK -- "Yes" --> FIX["Fix manifest/constraint in Git"]
    FIX --> PR
    RISK -- "No" --> STAGE["Staging: test admission and readiness"]
    STAGE --> APPROVE["Change approval"]
    APPROVE --> PROD["Roll out in cluster waves"]
    PROD --> OBS["Monitor drift, violations, API errors"]
~~~

### 9.1. GitOps Ownership Boundaries

| Team | Owns | Should NOT have |
| --- | --- | --- |
| Platform | `RootSync`, namespaces, RBAC baselines, constraints/bundles | Unreviewed direct merge access |
| Application | `RepoSync` for assigned namespaces, app manifests | `cluster-admin` or fleet-wide guardrail edits |
| Security | Policy library, exceptions, `deny` approvals | Need to manually patch individual clusters |
| SRE | Health, audits, rollbacks, monitoring | Ad-hoc out-of-process Git hotfixes |

Enforce branch protection, required reviews, secret scanning, and YAML validation on Git repositories. **Anyone who can merge into the root repo holds broad cluster power**; even with Git audit logs, treat merge permissions as privileged infrastructure access.

### 9.2. Preventing Two Controllers from Fighting

Suppose another operator also edits `spec` fields on a Deployment managed by Config Sync. When two controllers repeatedly overwrite the same field, conflicts or update loops occur. Fixes:

1. Define a single **owner per field/resource** and primary management path.
2. Avoid syncing fields managed dynamically by HPA or operators per product guidance.
3. Use supported ignore-fields/ownership annotations, or exclude dynamically mutated resources from GitOps scope.
4. When `RootSync` and `RepoSync` overlap on a resource, resolve ownership; error `KNV1060` flags this common conflict.
5. **Never disable Config Sync just to legitimize drift** without checking pruning/deletion consequences.

### 9.3. Safe Rollbacks

| Incident | Preferred recovery |
| --- | --- |
| Config Sync applies bad config | Revert the Git commit; monitor sync status and runtime readiness |
| `deny` constraint blocks a release | Revert to `dryrun`/`warn` via approved Git PR; watch reconciliation |
| Git credentials expire | Fix authentication or read-only token; never make a private repo public |
| Policy Controller unavailable | Inspect controller, admission, and audit health; never treat fail-open as safe |
| Manifest accidentally deleted from Git | Assess pruning impact; restore from Git history and verify data |
| `RepoSync` conflicts with `RootSync` | Remove duplicate ownership from one source instead of patching manually |

Reverting a manifest **does not restore lost data** if a StatefulSet, PVC, or Namespace was deleted without storage protections. Maintain separate backups and DR procedures.

## 10. Observability, Troubleshooting, and Least Privilege

### 10.1. Read-Only Observation Commands

~~~bash
# Config Sync
nomos status
kubectl get rootsync -n config-management-system
kubectl get reposync -A

# Policy Controller
gcloud container fleet policycontroller describe \
  --memberships=gke-policy-lab \
  --project=LAB_PROJECT_ID
kubectl get constrainttemplates
kubectl get k8srequiredlabels lab-namespace-require-owner -o yaml

# Check lab namespaces
kubectl get ns orders-lab orders-policy-test --show-labels
~~~

`kubectl get constrainttemplates` confirms templates exist, yet **does not prove constraints are auditing or enforcing cleanly**. Inspect `enforcementAction` and `violations`; similarly, seeing a `RootSync` object does not prove the latest Git revision is `Synced`.

### 10.2. Quick Incident Matrix

| Symptom | Common cause | What to check |
| --- | --- | --- |
| Config Sync cannot fetch Git | Bad URL/branch/path, expired auth, egress DNS/network | `nomos status`, `git-sync` logs, `RootSync` status |
| Git fetched, apply fails | Incompatible manifest/CRD/RBAC/admission | `KNV...` error code, resource events, API response |
| `KNV1060` | Multiple sources manage the same resource | Locate `RootSync`/`RepoSync` colliding on group/kind/name/namespace |
| `KNV2009` | Kubernetes API apply failed | Read detailed error: RBAC, CRD, namespace, or constraint |
| Persistent drift | Sync failing or field overwritten by another controller | Compare source revision, ownership, and competing controllers |
| Constraint reports missing CRD | Template library not yet installed/ready | `kubectl get constrainttemplates` and controller status |
| Unlabeled Namespace still created | Constraint in `dryrun`/`warn`, mismatched scope, or broken webhook | Check `enforcementAction`, `match`, and admission health |
| Old non-compliant Namespace remains after `deny` | `deny` does not delete pre-existing resources | Run audit and remediate existing objects per policy |
| Add-ons blocked after enabling `deny` | Overly broad policy or missing exemptions | Revert to `dryrun` with approval and refine `match` |
| Audit violation not visible immediately | Audit runs periodically | Wait for audit cycle; check logs and Constraint status |
| CI passes, Config Sync fails | Cluster API version, CRD, or permission differences | Run server-side validation on a matching-version lab cluster |

### 10.3. Recommended Metrics and Alerts

| Category | Signals |
| --- | --- |
| Config Sync | Sync success/error counts, applied source revision, drift duration |
| Policy Controller | Violations by constraint/cluster, denies/warnings, webhook/audit health |
| Kubernetes API | Admission latency/error rate, API server load |
| Workloads | Pod readiness, Deployment rollouts, HTTP 5xx / p95 latency |
| Security | Changes to `RootSync`, constraints, roles, secrets, source credentials |
| Cost | GKE clusters/nodes, controller resources, Cloud Logging/Monitoring, Git/OCI transfer |

Too many `RootSync`/`RepoSync` objects increase API server requests as reconcilers run concurrently; do not multiply sources needlessly. Config Sync uses server-side apply, so API `PATCH` entries in audit logs do not always mean the Git source just changed.

### 10.4. IAM and Security Implications

- **Google Cloud IAM / fleet permissions** control who enables features and configures GKE at the Cloud layer.
- **Kubernetes RBAC** controls who creates/edits `RootSync`, `RepoSync`, Constraints, Namespaces, and RoleBindings.
- **Git permissions** control who merges desired state into the source repository.
- **Config Sync's service identity** needs **read access** to Git/OCI/Helm sources—never write access to the source repo.
- **Secret Manager / Workload Identity** and source credentials must follow environment isolation; never commit tokens or SSH private keys to Git.
- Config Sync and Policy Controller are **highly privileged in-cluster controllers**; keep versions patched, monitor them, and separate administrative duties.

## 11. Case Study: Standardizing GKE for an Order Platform

**Context:** the platform team owns three clusters (dev/staging/prod), the orders team owns its application namespace, and security requires every app namespace to declare an `owner` and enforce resource quotas.

Solution:

1. **`RootSync`:** rolls out baseline Namespaces, RBAC, ResourceQuotas, and constraints from the platform Git repo.
2. **`RepoSync`:** lets the orders team manage Deployments, Services, and ConfigMaps inside its assigned namespace.
3. **Policy Controller:** trials `K8sRequiredLabels` in `dryrun`; after auditing, promotes `deny` cluster by cluster or per resource group carefully.
4. **CI:** validates manifests, security rules, and PR approvals rather than relying on Config Sync alone to catch every mistake.
5. **SRE:** tracks sync status, policy violations, rollout health, and HTTP SLOs.
6. **Rollback:** reverts Git commits or flips `deny → dryrun` if a policy blocks emergency fixes, recording an audit trail.

**Design question:** if a Namespace manifest in Git lacks an `owner` label, Config Sync will attempt to apply the non-compliant object. With Policy Controller on `deny`, reconciliation fails—so **running policy checks in CI and `dryrun` before enforcement** prevents self-inflicted outages.

**Cost trade-off:** every cluster spends some compute/observability resources for controllers and team effort maintaining policies; in return, configuration drift, manual toil, and audit overhead shrink. Never promise fixed savings percentages or SLAs without empirical measurements.

## 12. Guided Hands-On Lab

**Goal:** complete two independent verifications on the lab cluster.

| Step | Action | Evidence to capture |
| --- | --- | --- |
| 1 | Inspect fleet membership, kubecontext, APIs, and permissions | Confirmed right lab project and cluster |
| 2 | Enable Config Sync and point `RootSync` to the test Git repo | `nomos status` and applied source revision |
| 3 | Commit a Namespace with `owner` and a `ResourceQuota` | Both resources appear in the cluster |
| 4 | Manually edit the lab namespace label and observe drift healing | Label reverts to the Git state |
| 5 | Install Policy Controller and its template library | Feature `ACTIVE`; `K8sRequiredLabels` present |
| 6 | Commit a `dryrun` constraint and create `orders-policy-test` without `owner` | Violation recorded; creation not denied |
| 7 | After review, flip to `deny` in Git; test an invalid server-side dry-run update | Admission rejects within scope |
| 8 | Add a valid `owner` label and inspect audit status | Violation clears on the next audit cycle |
| 9 | Gather logs, document runbook and rollback | Zero impact outside lab namespaces |

**Lab cleanup:** if `orders-policy-test` was created manually, delete only that namespace after confirming nothing else uses it. Deleting a managed namespace or removing `RootSync` can affect resources managed by Config Sync; never disable fleet features or delete shared Git repos just to finish an exercise. Verify ownership, retention, and costs before removing lab resources.

## 13. Review Questions

1. **How does Config Sync differ from Policy Controller?** One reconciles desired state; the other audits and enforces compliance constraints.
2. **How do `RootSync` and `RepoSync` differ?** `RootSync` manages cluster-scoped and namespaced resources; `RepoSync` is confined to a single namespace per config and RBAC.
3. **Can OCI or Helm serve as sources?** Yes, where supported; Helm setup differs from Git in Console/CLI.
4. **Are `ConstraintTemplate` and `Constraint` the same?** No; a template defines the rule type/schema, while a constraint binds scope and parameter values.
5. **What happens if `enforcementAction` is omitted?** It defaults to `deny`, which can disrupt workloads.
6. **Does `dryrun` automatically fix violations?** No; it evaluates and records violations without blocking or mutating resources.
7. **Does `deny` delete an old Namespace missing `owner`?** No; it rejects matching admission requests going forward.
8. **Why avoid turning on `deny` cluster-wide right away?** It can break add-ons and legitimate ops workflows; scope carefully, run `dryrun`, and manage exemptions first.
9. **Why does editing a constraint with `kubectl` revert back to the old setting?** Because Git/Config Sync owns it.
10. **What does `KNV1060` usually indicate?** Overlapping resource ownership across multiple sources of truth.
11. **Why might Git fetch succeed while apply fails?** API/CRD/RBAC mismatches, admission constraints, invalid manifests, or controller conflicts.
12. **If Policy Controller goes offline, does it block all API calls?** No; docs note its admission webhook fails open when unavailable.
13. **Does GitOps replace application backups?** No; Git stores manifests, not deleted stateful data.
14. **Which three permission layers must be aligned?** Google Cloud IAM, Kubernetes RBAC, and Git/source access.
15. **What defines a successful rollout?** Source revision is `Synced`, zero unexpected policy violations exist, and workloads/SLOs remain healthy.

## 14. Production Readiness Checklist

- [ ] Clear separation of `RootSync`/`RepoSync` ownership and Git PR review rights.
- [ ] Versioned source of truth with branch protection and zero plaintext secrets.
- [ ] Config Sync reports `Synced` on the intended revision per cluster—not just "installed."
- [ ] CI validation checks target Kubernetes APIs/CRDs and policies.
- [ ] Policy Controller templates/bundles match expected versions and are healthy.
- [ ] Constraints define explicit scopes, exemptions, parameters, and `enforcementAction`.
- [ ] Observed `dryrun`/`warn` output before enabling `deny`.
- [ ] Remediated pre-existing violations, including relevant namespaces and add-ons.
- [ ] Metrics and alerts cover sync errors, drift, admission denials, and API latency.
- [ ] IAM, Kubernetes RBAC, Git/OCI credentials, and controller identities follow least privilege.
- [ ] Runbooks exist for reverting Git, relaxing policies, and handling controller outages.
- [ ] Evaluated impact on workloads, SLOs, controller resource consumption, and costs.
- [ ] Confirmed no two reconcilers compete for ownership of the same object.

## 15. Official Google Cloud Documentation

- [Config Sync overview](https://docs.cloud.google.com/kubernetes-engine/config-sync/docs/overview) — GitOps and reconciliation.
- [Sources of truth](https://docs.cloud.google.com/kubernetes-engine/config-sync/docs/concepts/sources-of-truth) — Git, OCI, Helm; `RootSync`.
- [Install Config Sync](https://docs.cloud.google.com/kubernetes-engine/config-sync/docs/how-to/installing-config-sync) — Console, fleet, and CLI.
- [RootSync and RepoSync fields](https://docs.cloud.google.com/kubernetes-engine/config-sync/docs/reference/rootsync-reposync-fields) — CRD structure and authentication.
- [Multiple sources of truth](https://docs.cloud.google.com/kubernetes-engine/config-sync/docs/how-to/multiple-repositories) — multi-repo and ownership.
- [Use nomos](https://docs.cloud.google.com/kubernetes-engine/config-sync/docs/how-to/nomos-command) — inspecting sync status.
- [Config Sync troubleshooting](https://docs.cloud.google.com/kubernetes-engine/config-sync/docs/how-to/troubleshooting-config-sync) — diagnosing sync errors.
- [Config Sync error reference](https://docs.cloud.google.com/kubernetes-engine/config-sync/docs/reference/errors) — `KNV1060`, `KNV2009`.
- [Install Policy Controller](https://docs.cloud.google.com/kubernetes-engine/policy-controller/docs/how-to/installing-policy-controller) — fleet, APIs, and prerequisites.
- [Constraint template library](https://docs.cloud.google.com/kubernetes-engine/policy-controller/docs/latest/reference/constraint-template-library) — `K8sRequiredLabels` and many other templates.
- [Create constraints](https://docs.cloud.google.com/kubernetes-engine/policy-controller/docs/how-to/creating-policy-controller-constraints) — YAML, `match`, and `parameters`.
- [Audit constraints](https://docs.cloud.google.com/kubernetes-engine/policy-controller/docs/how-to/auditing-constraints) — `dryrun`, `warn`, `deny`.
- [Policy Controller constraint match](https://docs.cloud.google.com/kubernetes-engine/policy-controller/docs/reference/match) — scopes and namespace/label selectors.
- [GKE pricing](https://cloud.google.com/kubernetes-engine/pricing) — cluster and feature usage costs.

**Conclusion:** **Config Sync enforces desired configuration state; Policy Controller audits and enforces compliance rules.** Both work best with clear Git ownership, reviewed manifests, evidence-based progression from `dryrun` to `deny`, and monitoring across both sync status and workload health.
