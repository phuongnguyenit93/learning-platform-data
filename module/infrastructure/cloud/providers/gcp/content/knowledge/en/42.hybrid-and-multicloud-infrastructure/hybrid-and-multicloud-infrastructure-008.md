# Managing Kubernetes Policies and Configuration Across Clusters

An organization may operate multiple Kubernetes clusters: production GKE across different regions, staging GKE, on-premises Kubernetes in a data center, and clusters managed by another cloud provider. When each cluster is configured manually, policies governing access control, pod security, namespaces, networking, and quotas quickly diverge. One cluster may block privileged containers while another still allows them; the same application may work in staging yet be rejected when deployed to production.

Cross-cluster configuration management is a problem of **desired state, ownership, change distribution, and compliance verification**. On Google Cloud, GKE fleets and tools such as Config Sync and Policy Controller help enforce consistent governance within supported scope. For clusters in external environments, organizations can also use GitOps controllers, admission policies, and independent verification systems. What matters is designing a shared contract and change-control process rather than assuming that registering a cluster to a fleet automatically applies every policy to it.

## 1. Distinguishing Configuration, Policy, and Operational State

Three related concepts that do not replace one another:

| Concept | Example | Goal |
| --- | --- | --- |
| Desired configuration | `Namespace`, `ResourceQuota`, `Deployment`, `ConfigMap`, RBAC | Define which resources must exist and with what values |
| Policy | Block privileged pods, require labels, restrict image registries | Define which configurations or behaviors are acceptable |
| Operational state | Pod Ready, HPA scaling, request latency, alerts | Verify the actual system outcome after applying configuration |

A GitOps controller can sync a Deployment to match Git, yet the Deployment can still fail due to image-pull errors or insufficient resources. An admission policy can reject non-compliant manifests, yet cannot guarantee the application serves traffic within SLOs. Therefore, observe sync status, policy compliance, and workload health together.

A measurable governance goal: every production cluster must enforce equivalent pod security policies, namespaces must have clear team ownership, no manual changes may persist beyond an allowed window, and whenever a policy causes an outage, a rehearsed rollback procedure must exist.

## 2. Inventorying Clusters and Classifying Management Scope

Before deploying tooling, build a complete cluster inventory:

| Attribute | Example | Why it matters |
| --- | --- | --- |
| Environment | dev, staging, production | Determines control rigor and release cadence |
| Platform | GKE, on-prem Kubernetes, EKS, AKS | Differences in IAM, CNI, admission, and management features |
| Kubernetes version | Minor version and supported APIs | Prevents applying incompatible manifests |
| Location | Region, zone, datacenter | Latency, residency, connectivity to Git |
| Owner | Platform team, business team | Who can modify configurations and respond to incidents |
| Criticality | Tier 0/1/2 | Determines validation gates and canary rollouts |
| Config source | Git repo, branch, revision, sync controller | Identifies source of truth and update progress |
| Policy baseline | Pod Security, RBAC, NetworkPolicy, quotas | Identifies clusters lacking required controls |

Do not lump all clusters into a uniform group merely because they all run Kubernetes. For example, GKE Dataplane V2 and an on-prem CNI may enforce `NetworkPolicy` differently; Pod Security Admission is widely supported in Kubernetes, yet exemptions and admission webhooks may differ. Validate every policy on each platform type.

## 3. Dividing Responsibilities Across Fleet, Cluster, and Namespace

In Google Cloud, a **fleet** provides a grouping and identification model for clusters sharing GKE management capabilities. Fleet members can include supported cluster types, though the availability of Config Sync, Policy Controller, or other fleet features depends on cluster type, version, location, and licensing/permissions.

Divide configuration into three layers:

1. **Organization/fleet baseline:** mandatory rules for labels, Pod Security, auditing, image registry standards, and admin permissions.
2. **Cluster configuration:** ingress, storage classes, network configuration, system namespaces, and valid cluster-specific exceptions.
3. **Application/namespace configuration:** Deployments, Services, ConfigMaps, HPAs, quotas, and RoleBindings per workload.

Platform teams typically own cluster-scoped objects and security policies. Application teams own only resources within authorized namespaces. Separating permissions at this boundary prevents an application pull request from accidentally modifying ClusterRoles, webhooks, or cluster-wide policies.

Within a cluster, cluster-scoped resources do not benefit from namespace isolation. Therefore, never allow arbitrary teams to create ClusterRoles, CustomResourceDefinitions, or ConstraintTemplates through the same unreviewed GitOps flow without special approval.

## 4. Reference Architecture: Git as the Source of Truth

A common deployment pattern stores configurations and policies in protected repositories, validates them via CI, and lets each cluster's controller pull the approved revision and reconcile actual state toward desired state.

~~~mermaid
flowchart TB
  Dev["Platform / Security / App teams"] --> PR["Pull request + review"]
  PR --> CI["Schema, policy, security and dry-run tests"]
  CI --> Git["Git config repositories"]
  Git --> DevSync["GitOps controller - staging"]
  DevSync --> Staging["GKE staging"]
  Git --> ProdSync["GitOps controller - production"]
  ProdSync --> Prod["GKE production"]
  Git --> HybridSync["GitOps controller - external cluster"]
  HybridSync --> Hybrid["On-prem / other cloud"]
  Staging --> Observe["Sync status + policy compliance + workload health"]
  Prod --> Observe
  Hybrid --> Observe
  Observe --> Feedback["Alert, rollback, remediation"]
  Feedback --> PR
~~~

Controllers run inside or near clusters, pull configurations from trusted sources, and apply them using scoped identities. This **pull** model typically removes the need to store `cluster-admin` kubeconfigs for every cluster on a central CI runner.

A change is complete only when it has been committed/approved, synced to the target cluster, accepted by admission, and confirmed by stable operational signals. Merging a pull request does not guarantee every cluster has successfully applied the configuration.

## 5. Designing Multi-Cluster Repositories

You can separate platform management repositories from application repositories, or use a monorepo with strict CODEOWNERS rules. Example platform repository:

~~~text
platform-kubernetes-config/
├── base/
│   ├── namespaces/
│   ├── rbac/
│   ├── network-policies/
│   ├── quotas/
│   └── policy-constraints/
├── overlays/
│   ├── staging/
│   ├── prod-asia/
│   ├── prod-europe/
│   └── onprem/
├── rendered/
│   ├── staging/
│   ├── prod-asia/
│   ├── prod-europe/
│   └── onprem/
├── tests/
└── README.md
~~~

The **base** directory holds shared rules and configs; **overlays** hold approved per-environment differences; **rendered** holds output YAML if the pipeline renders Kustomize/Helm in CI before the GitOps controller syncs. This is an organizational choice, not a mandatory Config Sync directory layout.

Avoid duplicating entire manifests for every cluster. Duplication forces security fixes to be repeated across many directories and makes omissions likely. Conversely, do not force every cluster onto one undifferentiated file when CNI, Kubernetes versions, or data residency requirements differ.

A clear strategy uses a common baseline, applies minimal differences in overlays, and documents justifications for every exception. For instance, production enforces tighter quotas and namespace policies than staging, while on-prem uses a dedicated storage class yet follows the same label and non-root container standards.

## 6. Kustomize and Helm in the Distribution Pipeline

**Kustomize** works well when environments share Kubernetes resources while differing in replicas, namespaces, images, or select fields. **Helm** works well when applications are packaged as charts with well-defined values interfaces and release lifecycles. Inspect the rendered output of both before deploying.

Example Kustomize overlay changing replica count:

~~~yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../base/orders-api
patches:
  - target:
      kind: Deployment
      name: orders-api
    patch: |-
      - op: replace
        path: /spec/replicas
        value: 3
~~~

This is the `kustomization.yaml` file in the production overlay. The base Deployment resource must match the exact name and path shown. Preview the rendered YAML before pushing it to the sync source:

~~~bash
kubectl kustomize overlays/prod-asia
~~~

With Helm, similarly run `helm template` with the target chart and values to generate manifests and evaluate policies. Never let a pipeline write unreviewed rendered output directly across multiple production clusters.

Config Sync and other GitOps controllers do not handle Kustomize/Helm identically across all versions. One way to reduce coupling is rendering in CI and placing validated YAML in the directory the controller actually tracks. If you want the controller to render directly, check your product version's capabilities and settings, and decide where output reproducibility is guaranteed.

## 7. Config Sync on GKE: Role and Sync Mechanics

**Config Sync** applies declarative configurations to clusters and detects/remediates drift within its management scope. Core object types:

| Object | Scope | Role |
| --- | --- | --- |
| `RootSync` | Syncs configurations that may include cluster-scoped and namespace-scoped objects per permissions | Typically owned by the platform team |
| `RepoSync` | Syncs configurations restricted to a single namespace under appropriate authorization | Useful for letting app teams manage their own namespace resources |
| Git or supported source | Holds desired state | Requires authentication, commit checks, and change monitoring |
| Sync/reconciler status | Reports fetch, render, and apply state | Used to detect errors or lagging cluster revisions |

`RootSync` and `RepoSync` are Config Sync Custom Resources, not built-in features on a cluster without Config Sync installed. Operating in GitOps mode, the controller periodically reconciles resources against desired state and can revert direct manual edits back to the source values.

Automatic drift remediation is valuable, yet carries risk: if a bad commit lands in the source, the controller can roll out the mistake across many clusters. Therefore, require approvals, staged rollouts, and an emergency sync-pause mechanism.

## 8. Example RootSync for a Cluster

Example `RootSync` syncing rendered manifests for a production cluster from a dedicated directory:

~~~yaml
apiVersion: configsync.gke.io/v1beta1
kind: RootSync
metadata:
  name: root-sync
  namespace: config-management-system
spec:
  sourceType: git
  git:
    repo: https://git.example.com/platform/kubernetes-config.git
    branch: main
    dir: rendered/prod-asia
    auth: none
    period: 60s
~~~

This example assumes a public read-only repository purely to illustrate syntax. **`auth: none` is unsuitable for private Git repositories**; real environments must use an authentication method supported by Config Sync (such as SSH credentials/tokens or workload identity where supported) with read-only scope. Never commit private keys, access tokens, or kubeconfigs into manifests.

`rendered/prod-asia` must contain valid objects for the target cluster. Never share the same path for both staging and production if the two environments enforce different policies. Pointing to the `main` branch can work if promotion workflows control each directory's contents; if environments need pinned revisions, design a versioning or promotion strategy using fields supported by your Config Sync version.

Once Config Sync is installed and authorized, inspect status:

~~~bash
kubectl --context=GKE_PROD_CONTEXT \
  -n config-management-system get rootsync

kubectl --context=GKE_PROD_CONTEXT \
  -n config-management-system describe rootsync root-sync
~~~

Do not treat a successful `kubectl apply` as proof of synchronization. Inspect sync/reconcile status and any fetch, authorization, render, or admission errors; verify that target resources reflect the expected version and contents.

## 9. RepoSync and Namespace-Scoped Ownership

`RepoSync` supports delegating management so teams control resources inside their own namespaces while the platform team retains control over cluster-level components.

A sound workflow:

1. Platform team creates namespaces, quotas, RBAC, and baseline security first.
2. Platform approves the identity used by `RepoSync` to sync inside that namespace.
3. Application teams manage Deployments, Services, ConfigMaps, and HPAs within granted permissions.
4. Admission policies prevent resources from crossing security boundaries.
5. The controller syncs and reports errors if permissions are insufficient or configs are rejected.

Never grant `cluster-admin` to `RepoSync` just to bypass permission errors. If an application genuinely needs a ClusterRole, CRD, or webhook, route that change through the platform management workflow with dedicated review. Expanding a controller service account's permissions is a security change and must be reviewed like production code.

## 10. Policy Controller and Admission Policies

**Policy Controller** in the GKE ecosystem uses OPA/Gatekeeper-based mechanisms to evaluate resources against declared policies. This differs from Config Sync:

- Config Sync works to make managed resources match Git.
- Policy Controller evaluates whether resources comply with constraints; applicable modes can validate at admission time, audit existing resources, or enforce progressively.

A rule may require namespaces to carry an `owner` label, block images from unapproved registries, or forbid privileged workload settings. Constraint template libraries provide built-in policy types; custom policies must be tested thoroughly because broken webhooks can block deployments across the cluster.

Distinguish three stages:

| Stage | How it works | Goal |
| --- | --- | --- |
| CI check | Validate rendered manifests before merge | Give early feedback to developers |
| Audit / dry-run | Observe existing resources violating the policy | Estimate impact and avoid sudden blocks |
| Enforce | Block non-compliant creates/updates at admission | Protect the cluster after handling exceptions |

Never enable fleet-wide deny immediately upon writing a new constraint. Test with real workloads and API versions, evaluate critical system controllers and namespaces, and then raise enforcement levels.

## 11. Example Policy Requiring a Namespace Owner Label

Policy Controller/Gatekeeper can use the `K8sRequiredLabels` constraint kind if the corresponding `ConstraintTemplate` has been installed from a compatible policy library.

~~~yaml
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sRequiredLabels
metadata:
  name: namespaces-require-owner
spec:
  enforcementAction: dryrun
  match:
    kinds:
      - apiGroups: [""]
        kinds: ["Namespace"]
  parameters:
    labels:
      - key: owner
~~~

This example uses **dryrun** mode to inventory violations instead of immediately blocking requests. Once compatibility is verified, existing resources are remediated, and exception workflows exist, the team can adopt the appropriate `enforcementAction` to block non-compliant changes.

Note that the constraint does not define `K8sRequiredLabels` by itself. The cluster must have a valid `ConstraintTemplate`/constraint type installed; otherwise, the Kubernetes API rejects the manifest as an unrecognized resource kind. Verify template names and schemas against your installed library version.

A compliant Namespace carrying an `owner` label:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: orders
  labels:
    owner: commerce-platform
    environment: production
~~~

The `owner` label helps trace the responsible team; it is not an authentication mechanism and must never serve as an authorization boundary in place of RBAC/IAM. If you need to restrict allowed owner values, the policy must define explicit validation conditions.

## 12. Kubernetes Policy Layers to Standardize

Do not expect a single tool to cover every control. A strong baseline combines multiple layers:

| Control | Tool or mechanism | What to verify |
| --- | --- | --- |
| Pod Security | Pod Security Admission, policies, or Gatekeeper per design | Block privileged workloads and dangerous settings |
| RBAC | Controlled Roles, RoleBindings, ClusterRoles | Who can read, edit, or create resources |
| Network segmentation | `NetworkPolicy` with a supporting data plane | Which namespaces can talk to which namespaces |
| Resource isolation | `ResourceQuota`, `LimitRange` | Prevent one team from exhausting cluster capacity |
| Image controls | Admission checks, artifact signing, registry policies | Do workloads run only trusted images? |
| Secrets | Secret Manager, CSI drivers, or suitable mechanism | Who can read secrets and where keys reside |
| Audit | Kubernetes audit logs and Cloud Audit Logs per platform | Who modified policies, RBAC, or workloads |
| GitOps integrity | Protected branches, reviews, provenance, sync status | Do deployed configs match approved revisions? |

Example `NetworkPolicy` blocking default ingress in namespace `orders`:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: orders
spec:
  podSelector: {}
  policyTypes:
    - Ingress
~~~

This policy does not block egress by default, nor does it create the allow rules needed by the application. After applying it, add explicit policies permitting intended ingress. `NetworkPolicy` enforcement depends on the CNI and cluster setup; test the actual data plane before treating a YAML file as an active security barrier.

With Pod Security Admission, levels like `privileged`, `baseline`, and `restricted` are meaningful in Kubernetes, yet namespace exemptions and compatibility for system workloads must be designed intentionally. Accidentally blocking controller or CNI admission can disrupt cluster-wide operations.

## 13. Separating Cloud IAM and Kubernetes RBAC

When managing multiple clusters, at least two identity planes exist: permissions to call cloud infrastructure management APIs, and permissions to call the Kubernetes API inside a cluster. Someone permitted to view a GKE cluster does not automatically hold full administrative permissions inside Kubernetes.

On GKE, account for Google Cloud IAM, control-plane authentication identities, Kubernetes RBAC, and Workload Identity Federation for GKE so workloads can access Google Cloud APIs. On EKS/AKS/on-prem, identity mappings, OIDC, and cloud permissions differ.

Principles:

- People editing Git configurations do not necessarily need direct `kubectl` `cluster-admin` access.
- A GitOps controller's identity holds permissions only for the resources and namespaces it manages.
- CI needs read and validation permissions on manifests; direct write access to production APIs should be restricted under a GitOps pull model.
- Application workload identities stay separate from sync controller identities.
- Permissions to create admission webhooks, CRDs, ClusterRoles, and elevated privileges require separate review.

Never store long-lived kubeconfigs with high-privilege credentials in repositories or shared CI runners. Use short-lived credentials and audited identity authentication wherever supported.

## 14. Secrets, ConfigMaps, and Sensitive Data

ConfigMaps suit non-sensitive configuration; a Kubernetes Secret must not be treated as a secure vault merely because values are base64-encoded. Secrets still depend on RBAC, encryption at rest, transport security, controllers, and node-level read mechanics.

For GCP applications, integrate Secret Manager or a supported sync/CSI mechanism to supply secrets to workloads. In hybrid/multicloud setups, distinguish the source secret store, short-lived issuance mechanics, per-cluster access permissions, and residency constraints.

Never commit plaintext tokens, passwords, or service account keys to a GitOps repo. If configs reference secrets, document clearly the responsibilities of the External Secrets operator/CSI driver or chosen tool, along with access controls and rotation workflows. A Kubernetes manifest referencing a missing Secret can sync cleanly while the workload fails to start; monitor both layers.

## 15. Staged Promotion and Controlled Change Rollout

Changing a cluster-scoped policy has a larger blast radius than updating one Deployment. A safe rollout follows a structured sequence:

1. **Design review:** identify affected resources and clusters, new policies, exceptions, and rollback criteria.
2. **Static checks:** validate YAML/schemas, Kustomize/Helm output, API versions, and security rules.
3. **Test cluster:** apply in an environment hosting representative workloads.
4. **Audit/dry-run:** collect violation lists and estimate impact before enabling deny.
5. **Canary cluster:** select a production cluster with acceptable risk scope; watch syncs and deployments.
6. **Controlled expansion:** roll out by region, environment, or cluster group, halting on alerts.
7. **Completion verification:** confirm synced commits, new violation counts, and workload health.

You can use tags/branches or separate promotion directories to pin production configurations to stable revisions. Regardless of pattern, avoid letting production automatically pick up untested changes simply because every cluster tracks `main`. Critical gates must run before a revision reaches production clusters.

If a new policy blocks a legitimate application, roll back the policy revision or switch enforcement back to audit mode via the agreed workflow. Never recover by disabling all admission controls when only a single constraint is at fault.

## 16. Drift Detection and Emergency Changes

**Configuration drift** occurs when live resources no longer match the declarative source. Causes include direct `kubectl` edits, another controller modifying shared fields, API server defaulting, or a mutating admission webhook modifying objects.

Drift is not always malicious. For example, an HPA scaling replicas while GitOps continuously forces the Deployment back to a fixed replica count creates a control conflict. Define field ownership: HPA owns the replica count when autoscaling is enabled; GitOps owns the HPA spec and other fields without fighting normal runtime behavior.

When drift is detected:

1. Identify the affected resource, cluster, field, and timestamp.
2. Check audit logs, actors, admission webhooks, and involved controllers.
3. Determine whether Git or another controller should be the source of truth for that field.
4. If drift is unplanned, remediate via commit or controlled reconciliation.
5. If caused by a production incident, log **break-glass** access with an accountable owner and expiration time.
6. After mitigation, fold emergency changes back into declarative source control to avoid unexpected controller overwrites.

Never edit a GitOps-managed resource directly and forget to update Git. The controller may revert the change on the very next sync cycle. For break-glass, document clearly how to pause or scope sync per product, enforce least privilege, and re-enable sync so governance is not lost.

## 17. Avoiding Conflicts Across Multiple Controllers

A cluster might simultaneously run Config Sync, Flux/Argo CD, Helm release controllers, HPAs, and application operators. If two controllers manage the same object or field with different targets, reconciliation loops can fight over the resource continuously.

Publish an ownership matrix:

| Resource or field group | Recommended owner |
| --- | --- |
| ClusterRole, ConstraintTemplate, policy baselines | Platform GitOps |
| Namespaces and quotas | Platform, or teams delegated by policy |
| Deployment image and container config | Application GitOps/CI |
| HPA target and min/max replicas | Application GitOps |
| Deployment replicas while HPA is active | HPA, via supported integration |
| Secret data | Secret management controller or designated vault |
| Status fields of Kubernetes resources | Kubernetes controllers; never tracked as desired state in Git |

A manifest may be altered by API server defaulting or mutating webhooks. Configure GitOps ignore-differences/ownership rules with accurate semantics and check security implications; avoid ignoring entire resources just to silence drift alerts.

## 18. Hybrid/Multicloud: Compatibility and Connectivity

Cross-cluster management does not mean every cluster shares an identical runtime environment. Separate portable parts from parts needing platform-specific adapters:

| Topic | Shareable portion | Platform-specific assessment |
| --- | --- | --- |
| Namespace labels, basic RBAC | Many standard Kubernetes manifests | Identity providers and user groups |
| Pod security | Intent to block dangerous privileges | Admission versions, exceptions, pod/system add-ons |
| `NetworkPolicy` | Segmentation intent | Whether CNI and data plane fully support it |
| Storage | PVC and StorageClass references | CSI drivers, class names, topology, snapshots |
| Ingress/Gateway | Supported API versions | Controllers, load balancers, TLS, and DNS |
| Workload identity | No static keys, least privilege | IAM/OIDC mappings across GCP, AWS, Azure, on-prem |
| Container registry | Pin digests, sign and verify images | Pull permissions, regions, and private endpoints |

A data-center cluster may not maintain uninterrupted connectivity to central repositories. Designs must define acceptable disconnection windows, Git/registry mirroring where needed, certificates, proxies, and offline emergency patching procedures. Never assume controllers apply a new policy within minutes if network paths or source access are broken.

To manage fleets containing clusters on other clouds, check exact support conditions for attached/registered clusters and policy products for your version. Seeing a membership in the console does not guarantee admission webhooks or manifest syncing are installed and healthy.

## 19. Observing Sync Status and Compliance

A multi-cluster dashboard should display:

- Expected clusters vs. clusters actively receiving configurations.
- Desired config revision/commit vs. applied revision on each cluster.
- Last sync timestamp, staleness duration, and fetch, auth, render, apply, and retry error counts.
- Drifted resources, clusters with prolonged drift, and causes.
- Audit-mode constraint violations and admission denials by policy type.
- Pod Ready ratios, deployment availability, error rates, and latency for changed workloads.
- Certificate/webhook health, admission latency, and Kubernetes API server load.

Set realistic management-plane SLOs—for example, most production clusters apply approved revisions within a target window after promotion, and no cluster stays in sync error beyond a threshold; tune specific numbers to connectivity and change frequency.

If GitOps reports Synced while the application is not Ready, that is a workload or dependency issue, not necessarily a sync bug. Conversely, if workloads run fine while a cluster remains out of sync for days, drift and delayed security patches still require remediation.

## 20. Runbook When Configurations or Policies Cause an Incident

**Scenario:** after a pull request updating a policy, multiple production Deployments are rejected when creating new Pods.

Procedure:

1. Identify affected clusters and namespaces; compare the applied commit against the last known-good commit.
2. Check sync status of `RootSync`/`RepoSync` or equivalent controller; look for manifest apply errors.
3. Inspect admission denials from the policy engine, noting the constraint name and rejected objects.
4. Determine whether the manifests are genuinely non-compliant or the new policy is overly strict/incompatible.
5. If caused by the new policy, revert the commit or lower enforcement per the agreed workflow; prioritize fixing the offending constraint.
6. Monitor workload rollouts once the policy is fixed; confirm Pod Ready status, error rates, and SLOs return to normal.
7. Document root cause, blast radius, approvers, and add regression tests in CI.

Avoid using manual `kubectl apply` to patch dozens of GitOps-owned resources without a reconciliation plan. When the API server or admission webhooks fail, inspect `failurePolicy` types and security impact before flipping fail-open/fail-closed modes. Allowing every resource through merely to clear deployment errors can create a larger vulnerability.

## 21. Lab: Maintaining Three Clusters With Two Policy Tiers

**Scenario:** An organization runs GKE staging, GKE production, and on-premises Kubernetes. The team wants every application namespace to require an `owner` label, block privileged workloads in production, and let app teams self-manage Deployments in their own namespaces.

Tasks:

1. Build a cluster inventory: platform, Kubernetes version, cluster context, owner, and policy capabilities.
2. Design a `base/overlays/rendered` repository with a shared baseline and documented exceptions.
3. Create sample Namespaces with `owner` and `environment` labels; configure per-namespace quotas and RBAC.
4. Configure a test `RootSync` on GKE staging pointing to a read-only repo and dedicated directory.
5. Install/verify required `ConstraintTemplate`s and apply the owner-required constraint in `dryrun` mode.
6. Create two test namespaces: one with an `owner` label and one missing it; record violations in the audit report.
7. After verification, test enforcement on a test namespace before considering production.
8. Make a manual edit to a GitOps-managed resource and verify drift/reconciliation.
9. Revoke repository read access in the test environment; observe sync errors and alerting.
10. Present a promotion plan to GKE production and the on-prem cluster, including rollback paths.

**Deliverables:** ownership diagram, repository structure, two sample manifests, policy test results, sync status before/after changes, controller permission matrix, and recovery runbook.

Never use real production clusters to test admission denials, Git outages, or destructive config changes without formal approval and a safe test environment.

## 22. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming fleet registration applies policies automatically | Some clusters remain unmanaged in practice | Verify installation, eligibility, sync, and policy status per cluster |
| Mixing platform and app permissions in one repo | App PRs can alter cluster-wide policies | Separate sources, CODEOWNERS, and controller permissions |
| Enabling fleet-wide deny from day one | Breaks rollouts or system components | Audit/dry-run, staging, canary, then enforce |
| Duplicating full manifests per cluster | Security fixes easily missed | Shared base, minimal overlays, and drift reviews |
| Granting `cluster-admin` to all GitOps controllers | Expanded blast radius if repo/credentials leak | Least privilege scoped by object and namespace |
| Having both HPA and GitOps enforce replicas | Continuous reconciliation fights or broken autoscaling | Define field ownership and controlled ignore rules |
| Putting plaintext Secrets in Git | Credentials leaked in Git history | Use secret stores and proper identity/secret injection |
| Monitoring only Git Sync status | Misses policy violations or unready workloads | Monitor sync, compliance, and runtime health separately |
| Ignoring CNI/API differences across clusters | Valid manifests whose policies have no effect | Test compatibility on each cluster type |
| Editing production directly without updating Git | Controller unexpectedly reverts the change | Audited, time-bound break-glass with clear reconciliation |
| Rolling back source without checking cluster state | Clusters may still fail or lag behind old revisions | Verify applied revision and workload health after rollback |

## 23. Pre-Rollout Cross-Cluster Kubernetes Management Checklist

- Inventoried all clusters and genuinely supported management features.
- Clear source of truth and owners defined for cluster-scoped resources, namespace-scoped resources, and policies.
- Repositories enforce branch protection, reviews, promotion workflows, and commit/release metadata.
- Config Sync or GitOps controllers run on the right clusters with least-privilege identities.
- `RootSync`/`RepoSync` roles separated properly; namespace teams are never granted `cluster-admin`.
- Configurations are rendered, validated, and security-checked before syncing.
- Policies tested in audit/dry-run and staging before expanding enforcement.
- Pod Security, RBAC, `NetworkPolicy`, quotas, and image trust rules evaluated per platform.
- GitOps, HPAs, operators, and secret controllers have non-conflicting field ownership.
- No secrets or long-lived credentials in Git or container images.
- Observability covers revision/sync latency/drift, admission violations, and workload health.
- Alerts trigger on out-of-sync clusters, broken policy webhooks, or post-rollout workload degradation.
- Rollback, break-glass, Git-reconciliation procedures, and recovery drills exist.
- Per-cluster exceptions have justifications, approvers, and review dates.
- Offline clusters, repository reachability, registry access, and DNS addressed for hybrid/multicloud setups.

Effective cross-cluster Kubernetes policy and configuration management combines GitOps with admission control and clear authorization. GKE fleets organize supported clusters; Config Sync delivers declarative state; and Policy Controller enforces matching rules. Yet true reliability comes from defining clear sources of truth, testing in stages, limiting permissions, monitoring drift, and maintaining tested recovery plans when configs go wrong. This approach establishes a consistent foundation across Google Cloud, data centers, and other clouds without masking the technical differences between them.
