# Designing Cluster, Namespace, and Environment Boundaries

## 1. Why Design Boundaries Before Deploying Containers?

Containers help package applications and dependencies for consistent deployment. However, when multiple teams run workloads on Kubernetes or a container platform, the key question is not just where a Pod runs, but also **who owns the workload, who is allowed to modify it, which components the workload can communicate with, and how far an incident can spread**.

Three concepts are often conflated:

- **Cluster:** a control and execution domain of a container platform. A cluster has its own control plane, nodes/compute, networking, policies, and upgrade lifecycle.
- **Namespace:** a logical scope within a Kubernetes cluster used to group resources, provide naming scope, assign permissions, and apply certain scoped policies.
- **Environment:** a stage or purpose of a workload, such as development, test, staging, or production. An environment may correspond to a dedicated cluster, a set of namespaces, or a cloud account/subscription/project boundary depending on requirements.

Choosing the wrong boundaries has real consequences. If production and development share a cluster without strict controls on permissions, network policies, quotas, and node isolation, an experiment can impact customer-facing services. Conversely, spinning up a separate cluster for every test branch can drive up control plane, node, logging, upgrade, and on-call costs beyond what the team can sustain.

In the **CLOUD_ARCHITECTURE** module, organizing clusters, namespaces, and environments is an architectural decision: you must balance **reliability, security, scalability, cost, and operations**. There is no single separation diagram for every enterprise; the choice must be grounded in required isolation, ownership, and verification methods.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish between cluster boundaries, namespace boundaries, and environment boundaries.
2. Choose between dedicated and shared cluster models based on risk, team size, and operational requirements.
3. Design namespaces around ownership, application/domain, and change lifecycles.
4. Apply RBAC, ResourceQuota, LimitRange, NetworkPolicy, admission policies, and workload identity appropriately.
5. Organize dev/test/staging/production to manage configuration, data, secrets, and releases safely.
6. Identify the limits of namespaces in multi-tenancy and the evidence required for acceptance.

## 2. Layered Boundary Model

A cloud Kubernetes platform typically has multiple layers of boundaries. Each layer governs a different scope:

| Layer | Subjects | Typically Controls | Example Decision |
|---|---|---|---|
| Organization/cloud account | Organization, account, subscription, project | Billing, top-level IAM, cloud quotas, org policies | Do production workloads need a separate account/subscription? |
| Network boundary | VPC/VNet, subnets, routing, firewalls | External cluster connectivity and traffic between network domains | Should prod and dev clusters share a network? |
| Cluster | Control plane, node pools, add-ons, cluster-scoped resources | Lifecycle, cluster admin rights, failure domains, Kubernetes version | Does a team need an independent control plane and upgrades? |
| Namespace | Namespaced Kubernetes API objects | Resource names, RBAC scope, quotas, scoped policies | Which resources does the Booking team own? |
| Workload | Deployment, StatefulSet, Job, Pod, Service | Replicas, rollouts, configuration, application health | Do the API and worker scale independently? |
| Container/process | Runtime, filesystem, capabilities, user | Process isolation and runtime privileges | Does the container run as non-root with a read-only filesystem? |

**A namespace is not a virtual machine or a mini-cluster.** It does not inherently provide its own kernel, control plane, failure domain, or complete security boundary. Pods across different namespaces can still share nodes, kernels, CNI, the control plane, and cluster-scoped components.

### 2.1. Reference Logical Model

~~~mermaid
flowchart TD
    Org["Cloud organization / account boundary"]
    Org --> Net["Network boundary"]
    Net --> Prod["Production cluster"]
    Net --> NonProd["Non-production cluster"]
    Prod --> SysP["kube-system / platform services"]
    Prod --> BookP["namespace: booking"]
    Prod --> SearchP["namespace: search"]
    NonProd --> SysN["kube-system / platform services"]
    NonProd --> Dev["namespace: booking-dev"]
    NonProd --> Stage["namespace: booking-staging"]
~~~

*This diagram illustrates an organization with a dedicated production cluster and a shared non-production cluster. For sensitive workloads or strict isolation requirements, staging may also need its own cluster; for smaller organizations, the model can be simplified while still keeping permissions and policies clear.*

## 3. Dedicated Cluster vs. Shared Cluster?

This is a platform-level decision. You must evaluate the required isolation for the control plane, nodes, networking, cluster-admin permissions, upgrade cycles, cloud quotas, and failure blast radius.

| Criterion | Shared Cluster | Dedicated Cluster |
|---|---|---|
| **Control plane isolation** | Multiple teams depend on the same control plane and cluster config | Each cluster has its own control plane and lifecycle |
| **Failure blast radius** | CNI, upgrade, admission, or cluster-wide resource issues can affect many workloads | Incidents can be contained to one cluster if external dependencies are properly separated |
| **Security** | Requires strict RBAC, policies, node isolation, and governance processes | Stronger boundary at cluster level, though IAM/network/registry and control plane still need protection |
| **Upgrades** | A single upgrade schedule may require coordinating multiple teams | Independent upgrade schedules and maintenance windows |
| **Resource utilization** | Can share nodes/compute and improve utilization | Dedicated resources per cluster risk idle capacity |
| **Cost** | Typically lower cluster overhead, though may require larger node pools and governance | Additional control plane fees (if charged), baseline nodes, logging, networking, and operations |
| **Complexity** | Fewer clusters to maintain, but multi-tenant governance and coordination are complex | Clearer isolation, but requires managing multiple clusters, versions, policies, and add-ons |
| **Best fit** | Teams with relatively similar trust levels, workloads not needing hard boundaries, capable platform team | Production/regulated workloads, multiple trust domains, independent upgrade or failure requirements |

### 3.1. When Should You Separate Clusters?

Consider dedicated clusters when one or more clear reasons exist:

- **Production vs. non-production:** high isolation requirements for permissions, data, changes, and failure domains.
- **Differences in trust:** workloads belonging to teams/partners with unequal trust levels or distinct security obligations.
- **Upgrades and add-ons:** a workload requires a different Kubernetes version, CNI, CSI, service mesh, or cluster configuration that cannot coexist safely in the same cluster.
- **Scale and quotas:** high-traffic workloads or specialized node/accelerator needs that disrupt shared capacity.
- **Fault tolerance:** using a cluster as an isolated failure domain to limit the impact of upgrades, control plane outages, or cluster-wide misconfigurations.
- **Administrative privileges:** needing to separate who can grant `cluster-admin`, install CRDs, configure admission webhooks, or alter network plugins.
- **Data/location constraints:** regional, network path, or data residency requirements that the current cluster cannot satisfy.

Dedicated clusters only provide real value when critical dependencies are also evaluated. Two clusters in the same VPC, sharing the same DNS, registry, CI/CD, and root administrative account, can still share significant risk.

### 3.2. When Is a Shared Cluster Reasonable?

- Multiple application teams share similar trust levels and data classifications.
- A centralized platform team automates RBAC, policies, quotas, networking, and upgrades.
- Workloads can share node pools while meeting noisy-neighbor and availability requirements.
- Autonomy needs are not yet large enough to justify dedicated cluster costs.
- Proven incident response and permission boundaries exist at the namespace/workload level.

**Do not decide based solely on the number of teams or Pods.** A shared cluster with 5 teams can be safer than an unmanaged dedicated cluster; it can also be unsuitable if one of the five teams holds `cluster-admin` privileges and carries high risk.

## 4. Designing Namespaces Around Ownership and Lifecycle

Namespaces are useful for establishing naming scopes and applying certain policies. Namespace layout should reflect **who is responsible**, **which resources change together**, and **which lifecycles need management**.

| Model | Example | Pros | Cons |
|---|---|---|---|
| By team | `team-booking`, `team-search` | Clear ownership, easy permission delegation | One team may own multiple apps with different lifecycles |
| By application/domain | `booking`, `catalog`, `payment` | Application-centric observability and policy management | Requires managing permissions across multiple namespaces for one team |
| By environment | `booking-dev`, `booking-stage`, `booking-prod` | Name indicates environment; easy to apply different policies | Increases namespace count; risks config drift without automation |
| By customer tenant | `tenant-a`, `tenant-b` | Can be useful for internal per-tenant workloads | Insufficient as a security boundary for untrusted tenants |
| Hybrid | Prod cluster has `booking`, `search`, `payment`; non-prod cluster has `booking-dev`, `booking-test` | Flexible across ownership and risk | Requires clear naming/labeling standards and a catalog |

There is no single namespace rule. Avoid splitting by Kubernetes object type, which fragments ownership and policies. Also avoid creating namespaces for short-lived Git branches without lifecycle automation and cleanup.

### 4.1. Every Namespace Should Have an Owner and Metadata

Example of standard labels:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: booking-prod
  labels:
    app.kubernetes.io/part-of: rental-platform
    environment: production
    owner-team: booking
    data-classification: confidential
    cost-center: product-booking
~~~

Labels are merely metadata used by selectors, policies, or cost tooling; they do not automatically grant permissions or protect data. Control who can modify security- or cost-sensitive labels and validate consistency at admission or in the pipeline.

A well-owned namespace should document the team/platform contact, on-call rotation, data classification, network access requirements, quotas, LimitRanges, policies, deployment method, dashboards, backups if stateful, environment, cost center, and expected lifecycle.

## 5. How Far Do Namespace Boundaries Go?

Kubernetes namespaces provide several scoping mechanisms, but **do not automatically prevent all cross-namespace interactions**.

| Mechanism | Scope | Things to Remember |
|---|---|---|
| RBAC Role/RoleBinding | API permissions within a namespace | Users may still hold a ClusterRoleBinding or broader permissions |
| ResourceQuota | Total resource requests/limits or object counts in a namespace | Does not cap total cloud billing or all node-level resources |
| LimitRange | Defaults/min/max for resource requests/limits and certain fields by object type | Does not replace capacity planning and quotas |
| NetworkPolicy | Pod-to-pod/namespace traffic as supported by CNI | Must verify CNI support, policy isolation, and default behavior |
| Pod Security Admission | Pod security levels via namespace labels | Controls only certain Pod specs; does not replace runtime/kernel security |
| Admission policy/webhook | Validates or blocks objects at API admission | Webhooks must be protected, with availability and exception handling |
| Secret | Sensitive config data via the API | Requires encryption at rest, RBAC, external secret integration, and rotation |

Resources such as Nodes, PersistentVolumes, StorageClasses, CRDs, ClusterRoles, webhooks, many policies, and certain add-ons are not simple namespaced resources in the same way a Deployment or Service is. Users with cluster-level permissions can impact multiple tenants. Therefore, namespaces are insufficient to isolate a malicious tenant or data subject to strict isolation requirements.

If a strong trust boundary is needed, consider dedicated clusters, separate cloud accounts/projects, node/VM isolation, or specialized mechanisms depending on the threat model. Evaluate the control plane, kernel, networking, storage, credentials, and administrative paths.

## 6. RBAC: Who Can Do What in a Namespace?

**Role-Based Access Control (RBAC)** grants permissions to subjects (users, groups, or service accounts) via Roles/ClusterRoles and RoleBindings/ClusterRoleBindings.

- **Role** defines permissions within a single namespace.
- **RoleBinding** assigns permissions to subjects within the namespace where the binding exists.
- **ClusterRole** defines a set of permissions usable cluster-wide or referenced within a namespace.
- **ClusterRoleBinding** grants cluster-wide permissions across the scope of a ClusterRole.

Example where a developer group can only view and update specific workloads in the `booking-dev` namespace:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: booking-developer
  namespace: booking-dev
rules:
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets"]
    verbs: ["get", "list", "watch", "update", "patch"]
  - apiGroups: [""]
    resources: ["pods", "services", "configmaps"]
    verbs: ["get", "list", "watch"]
~~~

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: booking-developer-binding
  namespace: booking-dev
subjects:
  - kind: Group
    name: booking-developers
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: booking-developer
  apiGroup: rbac.authorization.k8s.io
~~~

This example only illustrates API scoping. In a real environment, verify specific API groups/verbs, authentication mappings, rollout permissions, and log-reading rights. Never grant wildcards or `cluster-admin` to developers just to unblock an action. Also watch out for indirect privileges: reading Secrets, creating Pods, or editing workloads can enable accessing sensitive data or executing code using the workload's service account.

### Verifying Permissions Before Handover

~~~bash
kubectl auth can-i list pods -n booking-dev --as-group=booking-developers
kubectl auth can-i create secrets -n booking-dev --as-group=booking-developers
kubectl auth can-i get nodes
kubectl get rolebindings -n booking-dev
kubectl get clusterrolebindings
~~~

These commands assume the caller has appropriate impersonation privileges. Without impersonation rights, test using actual group identities or a controlled permission-testing pipeline. A `no` result for one action does not prove all other access paths are blocked.

## 7. ResourceQuota and LimitRange

In a shared cluster, one team might accidentally create hundreds of Pods or request excessive CPU/memory. **ResourceQuota** caps total resource requests/limits or object counts per namespace. **LimitRange** sets defaults/min/max values for containers or supported object types.

Example:

~~~yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: booking-quota
  namespace: booking-dev
spec:
  hard:
    requests.cpu: "8"
    requests.memory: 16Gi
    limits.cpu: "16"
    limits.memory: 32Gi
    pods: "40"
    persistentvolumeclaims: "10"
~~~

~~~yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: container-defaults
  namespace: booking-dev
spec:
  limits:
    - type: Container
      defaultRequest:
        cpu: 100m
        memory: 128Mi
      default:
        cpu: "1"
        memory: 512Mi
      min:
        cpu: 50m
        memory: 64Mi
      max:
        cpu: "2"
        memory: 4Gi
~~~

These values are **illustrative only** and must be calibrated via load tests, sizing, node capacity, and cloud quotas. Missing requests make scheduling difficult; setting limits too low can cause throttling or OOMKills. Quotas are also not a billing budget: traffic, load balancers, storage, NAT, and logs can generate costs outside the scope of these quotas.

## 8. NetworkPolicy: Controlling Traffic Between Namespaces

NetworkPolicy defines which Pods can send/receive ingress/egress traffic based on pod selectors, namespace selectors, IP blocks, ports, and protocols. Enforcement depends on the CNI/plugin; you must verify that the cluster platform supports it and check its actual enforcement mode.

Example: isolate ingress for Pods in `booking-prod`, then allow traffic from Pods in an `edge` namespace with matching labels:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-edge-to-booking
  namespace: booking-prod
spec:
  podSelector:
    matchLabels:
      app: booking-api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              network-zone: edge
          podSelector:
            matchLabels:
              app: gateway
      ports:
        - protocol: TCP
          port: 8080
~~~

Both selectors are placed inside the same `from` element, so they are combined with AND logic: the Pod must match both the namespace label and the Pod label. Separating them into two distinct elements in the `from` list causes each element to be evaluated as an independent allowed source (OR logic).

This example only governs ingress for the selected Pods. It does not automatically create an egress allowlist, replace cloud firewalls, handle IAM, or guarantee coverage for `hostNetwork` or every CNI-defined traffic type. When applying a default-deny policy, explicitly permit DNS, monitoring, health checks, and necessary dependencies to avoid breaking core platform flows.

## 9. Organizing Development, Test, Staging, and Production Environments

Environments represent the purpose and stability level of workloads. Each environment may differ in data, permissions, capacity, domain names, secrets, connectivity, and release schedules.

| Environment | Purpose | Desired Characteristics | Controls Needed |
|---|---|---|---|
| **Development** | Rapid development and testing | Small resources, flexible creation/teardown, mocked dependencies where appropriate | No real customer data outside approved scope |
| **Test / QA** | Integration, regression, acceptance testing | Production-like configuration for aspects under verification | Controlled test data, seeding/resetting, repeatability |
| **Staging / Pre-production** | Validating release candidates | Comparable versions, network paths, policies, and monitoring where needed | Change approvals, smoke/performance tests, sanitized data |
| **Production** | Serving real customers and business traffic | SLOs, backups, auditing, on-call, rollback/roll-forward | Least privilege, controlled changes, data protection |

Not all environments need to be identical. Staging can have fewer replicas, but should retain the architectural characteristics that testing needs to validate—such as ingress/TLS, network policies, database engines, migrations, and observability. If staging uses a different network path than production, it can miss routing/DNS bugs.

### 9.1. Dedicated Cluster per Environment

~~~mermaid
flowchart TD
    Platform["Container platform"]
    Platform --> DevCluster["Dev cluster"]
    Platform --> TestCluster["Test cluster"]
    Platform --> ProdCluster["Production cluster"]
    DevCluster --> DevNs["booking-dev"]
    TestCluster --> TestNs["booking-test"]
    ProdCluster --> ProdNs["booking-prod"]
~~~

This model separates control planes, upgrades, and failure domains; in return, it increases costs, idle resources, pipelines, and multi-cluster operational effort.

### 9.2. Shared Non-Production Cluster, Dedicated Production Cluster

~~~mermaid
flowchart TD
    Dev["Non-production cluster"]
    Prod["Production cluster"]
    Dev --> D["namespace: booking-dev"]
    Dev --> T["namespace: booking-test"]
    Prod --> P["namespace: booking-prod"]
~~~

This is a common balanced option for mid-sized organizations: dev/test share a cluster under defined policies while production is isolated. However, you must still protect nodes, APIs, quotas, and networking across dev/test namespaces in the shared cluster.

### 9.3. Single Shared Cluster for All Environments

This can reduce infrastructure costs and simplify administration when workloads are small and trust levels allow. However, if developers can create arbitrary workloads, share compute resources, and potentially affect production, namespace boundaries alone are insufficient. You need verified RBAC, admission controls, policies, quotas, node isolation, and blast radius containment; otherwise, separate the clusters or cloud accounts/networks.

## 10. Environment-Specific Configuration and Secrets Management

Container images should be **promoted across environments** using the exact same identified build artifact (e.g., digest), while configuration is supplied per environment. This reduces the risk of staging and production running different binaries despite sharing a release label.

Distinguish between:

- **Image:** built application code and dependencies, tagged with version/digest.
- **ConfigMap:** non-sensitive configuration, such as feature flags or environment-specific endpoints.
- **Secret:** sensitive data like tokens, passwords, and certificates; requires RBAC controls, encryption at rest, rotation, and an appropriate source.
- **Resource requests/limits:** may vary by environment capacity, but should be measured and version-controlled.
- **Network policy/ingress:** may be stricter in production, ensuring valid dependencies and health check paths.
- **Data:** dev/test should use synthetic or masked data per policy; never copy sensitive production data arbitrarily.

Example of environment-specific configuration:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: booking-runtime
  namespace: booking-staging
data:
  LOG_LEVEL: "INFO"
  PAYMENT_MODE: "sandbox"
  FEATURE_NEW_CHECKOUT: "true"
~~~

Never store real secrets in ConfigMaps, Git, or documentation examples. For production, use a secret manager or external secrets integration where appropriate, while controlling service account and pipeline permissions so other workloads cannot read namespace secrets.

## 11. Organizing Node Pools and Workload Placement

Cluster boundaries are only part of isolation. In a shared cluster, workloads can compete for CPU, memory, disk, networking, and GPUs within the same node pool. Define node pools based on compute profiles and trust requirements when justified:

| Node Pool | Example Workloads | Design Considerations |
|---|---|---|
| General purpose | Standard APIs, workers | Capacity, autoscaling, requests/limits, topology spread |
| Memory optimized | Caches or in-memory data processing | Memory pressure, eviction, limits, and cost |
| Compute optimized | CPU-heavy workers | CPU requests, throttling, load-based scaling |
| GPU/accelerator | Model inference or accelerated processing | Device plugins, quotas, scheduling, drivers, and idle cost |
| Isolated/regulated | Workloads with higher trust requirements | Taints/tolerations, node identity, dedicated pool or separate cluster |

**NodeSelectors, affinity, and taints/tolerations do not replace security boundaries.** They control where Pods are scheduled. Combine them with RBAC, admission controls, network policies, runtime security, node hardening, and cloud IAM.

Stateful workloads must consider PersistentVolumes, StorageClasses, topology, and backups. A Pod running in its own namespace does not mean its volume is isolated from administrative access or automatically backed up.

## 12. Multi-Tenancy: One Cluster Serving Multiple Teams or Customers

Multi-tenancy can have two meanings:

1. **Platform tenancy:** multiple development teams/business units sharing a cluster.
2. **Application tenancy:** multiple customers/tenants using the same application and data layer.

These are two distinct problems. One namespace per team can support platform tenancy; it does not automatically solve application tenancy. The application must still enforce tenant authorization, tenant-scoped data access, auditing, and business quotas.

| User Type | Relative Trust Level | Architectural Recommendation |
|---|---|---|
| Internal teams sharing security processes | Can share platform with guardrails | Namespaces/roles/quotas/network policies, platform team administers cluster |
| Project teams with deploy rights but no platform admin | Must restrict API and runtime permissions | Dedicated namespaces, strict RBAC, admission, node/network controls |
| Partner workloads or externally supplied code | Low trust level | Consider separate cluster/account, workload sandboxes, and strict egress controls |
| Customer tenants with high data isolation obligations | Depends on threat model and contracts | May require dedicated namespace, cluster, account, or deployment; verify storage, identity, and network |

### Minimum Control Matrix in a Shared Cluster

- Managed namespace ownership and naming conventions.
- RBAC avoids granting `cluster-admin` to workload teams; review indirect access via Pods/Secrets/ServiceAccounts.
- ResourceQuota and LimitRange to prevent noisy neighbors at request/object levels.
- NetworkPolicy with appropriate default-deny and allowlists for required flows; CNI enforcement verified.
- Pod Security Admission/admission policies to restrict `privileged`, `hostPath`, `hostNetwork`, `hostPID`, capabilities, and image policies.
- Dedicated workload identities with least-privilege cloud permissions; avoid shared service accounts across namespaces.
- Appropriate node pools and runtime isolation; restrict daemon/host access.
- Centralized auditing/logging with alerts routed to owners.
- Offboarding process to revoke tenants, resources, secrets, volumes, and permissions when leaving the platform.

If a tenant can run arbitrary code or actively attempt container escapes, **do not treat a namespace as an independent security sandbox**. Evaluate the threat model and adopt stronger isolation mechanisms.

## 13. GitOps, IaC, and Maintaining Environment Consistency

Creating namespaces manually and editing RBAC with ad-hoc commands easily introduces drift between dev, staging, and production. Declarative management with IaC/GitOps helps:

1. **Cluster provisioning:** Terraform or cloud/IaC tools create clusters, networks, node pools, identity integration, and logging.
2. **Platform bootstrap:** install CNI, ingress controllers, DNS, CSI, metrics, policy engines, and GitOps agents in dependency order.
3. **Platform baseline:** standardized namespaces, RBAC, quotas, NetworkPolicies, Pod Security Admission/admission policies.
4. **Workload delivery:** image digests, manifests/Helm/Kustomize, non-sensitive config, and secret references.
5. **Promotion:** changes are reviewed; the same artifact moves across environments while config/policies are controlled per target.
6. **Drift detection:** compare cluster state against desired state; review before auto-reconciling sensitive changes.

Example repository structure:

~~~text
platform/
  clusters/
    dev/
    staging/
    production/
  policies/
    pod-security/
    network/
    quotas/
  namespaces/
    booking/
    catalog/
apps/
  booking/
    base/
    overlays/
      dev/
      staging/
      production/
~~~

This structure is illustrative. Choosing multi-repo vs. monorepo depends on ownership, review permissions, and promotion workflows. If anyone can merge into the production directory without policy gates, GitOps alone does not make production safe.

### 13.1. Kustomize Overlay Example

~~~yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: booking-staging
resources:
  - ../../base
images:
  - name: registry.example.com/booking-api
    newTag: "2026.11.18"
~~~

In production, prefer pinning images by digest for reproducibility and verification; tags here are illustrative. Never store secret values in Git manifests; use an appropriate secrets integration mechanism.

## 14. Cluster Upgrades and Environment Consistency

A cluster is a lifecycle unit. You must manage versions of Kubernetes, CNI/CSI, ingress, admission controllers, CRDs, node images, and autoscalers. Multiple namespaces in the same cluster are affected simultaneously if a cluster-wide change fails.

A reference upgrade strategy:

1. Track Kubernetes/cloud provider version support and end-of-life dates.
2. Check API deprecations and compatibility of CRDs, controllers, and add-ons.
3. Upgrade the dev cluster first, running workload tests and platform smoke tests.
4. Upgrade staging or a canary cluster with representative workloads.
5. Verify PodDisruptionBudgets, capacity, drain behavior, persistent workloads, and topology.
6. Schedule production, monitor errors and latency, and prepare appropriate rollback/mitigation plans.

Do not assume control plane or node versions can be downgraded arbitrarily. Rollback capabilities depend on the provider and version; maintain a verified recovery plan.

Staging does not have to match production's exact node count and capacity, but should maintain parity in ingress/TLS, Kubernetes/CNI/CSI versions, network/DNS, policies, secret delivery, rollouts, and telemetry for the aspects being tested. If staging relaxes policies or uses admin credentials to deploy, test results do not prove production will behave as expected.

## 15. Observing and Troubleshooting Across Boundaries

Each boundary needs dashboards, logs, and owners to identify whether an issue belongs to the cluster, namespace, or application.

| Scope | Signals to Monitor | Example Issues |
|---|---|---|
| Control plane | API availability/latency, admission errors, audit logs, version health | Slow API server, webhook timeouts |
| Node/pool | CPU, memory pressure, disk, kubelet, node readiness | Node NotReady, evictions, slow image pulls |
| Namespace | Quota usage, Pod restarts, pending Pods, policy denials | ResourceQuota exhausted, NetworkPolicy blocks |
| Workload | Replica availability, readiness/liveness, request latency/errors | CrashLoopBackOff, OOMKilled, readiness failures |
| Network | DNS errors, CNI, connection resets, flow denials, ingress/LB status | Misconfigured DNS, routes/firewalls, SNAT |
| Storage | PVC pending, attach/mount errors, latency, backup status | Wrong StorageClass, zone mismatch, missing permissions |
| Delivery | GitOps sync/health, admission rejections, deployment history | Broken desired state or image pull failure |

### Incident Triage Process

1. Identify the Pod, namespace, cluster, node, environment, and timestamp.
2. Run `get`/`describe` to inspect scheduler, admission, volume, and kubelet events.
3. Check workload logs/events; verify startup success and readiness checks.
4. Inspect DNS, Service, EndpointSlice, ingress, NetworkPolicy, and cloud firewalls.
5. Verify RBAC, service accounts, workload identity, and permissions to cloud dependencies.
6. Cross-check quotas, node capacity, image registries, storage, and versions.
7. Determine whether the blast radius is namespace-scoped or cluster-wide, then remediate within the smallest scope.

A Pending Pod can be caused by insufficient CPU/memory requests, node affinity, taints, quotas, or PVCs; do not default to blaming the scheduler. A Running Pod also does not guarantee passing readiness or successful business connectivity.

### Basic Inspection Commands

~~~bash
kubectl get namespaces
kubectl get pods -n booking-prod -o wide
kubectl describe pod booking-api-7d9f -n booking-prod
kubectl get events -n booking-prod --sort-by=.lastTimestamp
kubectl get networkpolicy -n booking-prod
kubectl get resourcequota,limitrange -n booking-prod
kubectl get endpointslices -n booking-prod
kubectl top pods -n booking-prod
~~~

Permissions to read resources/events/metrics depend on RBAC and add-ons. When investigating production, avoid exposing Secret values or personal data in terminal outputs or shared channels.

## 16. Case Study: Organizing Kubernetes for a Booking Platform

**Context:** An enterprise has three teams: Booking, Search, and Payments. Each team has dev, QA, and production environments. Booking and Payments handle customer/transaction data; Search primarily builds indexes and serves read queries. The Platform team has 24/7 on-call coverage, though its headcount is small. The company wants to use managed Kubernetes.

### 16.1. Comparing Three Options

| Option | Description | Strengths | Risks / Costs |
|---|---|---|---|
| **A: One cluster for everything** | 9 namespaces (3 environments × 3 teams) | Minimal cluster overhead, shared nodes and add-ons | Shared failures/control plane; difficult to enforce production isolation if governance is weak |
| **B: Shared dev/QA, dedicated production** | One non-prod cluster with 6 namespaces; one prod cluster with 3 namespaces | Balances cost while isolating production failures and upgrades | Non-prod still needs noisy-neighbor controls; prod cluster shares blast radius across all 3 teams |
| **C: Production clusters by sensitive domain** | Shared non-prod; Booking and Payments get separate prod clusters, Search prod as needed | Separates trust, data paths, and upgrade schedules by sensitivity | Multiple clusters, logs, policies, upgrades, and networks to operate |

### 16.2. Initial Recommendation

Select **Option B** as the baseline if threat modeling shows the three production teams can share a trust domain, share a failure domain, and adhere to common guardrails. The non-prod cluster has restricted permissions, quotas, and sanitized data; the prod cluster has dedicated RBAC, network policies, admission controls, appropriate node pools, logging, and strict upgrade procedures.

If Payments faces stricter isolation requirements or distinct key/identity management, or needs an independent change cycle, move to **Option C** for Payments first; there is no need to split every team just for symmetry. If data and regulations require isolation at the cloud account/network level, a separate cluster alone is insufficient.

### 16.3. Namespace and Policy Map

| Cluster | Namespace | Owner | Key Policies |
|---|---|---|---|
| Non-prod | `booking-dev`, `booking-qa` | Booking team | Small quotas, synthetic data, developer RBAC |
| Non-prod | `search-dev`, `search-qa` | Search team | Quotas tailored for read/index workloads, restricted egress |
| Non-prod | `payments-dev`, `payments-qa` | Payments team | Provider sandboxes, staging secrets, no production credentials |
| Prod | `booking`, `search`, `payments` | Respective product teams | Operational RBAC, appropriate default-deny, requests/limits, auditing, alerts |

Production namespaces still require inter-service traffic controls. For example, Booking can call the Payment API via service identity/mTLS by design, but must not have permission to read Payments Secrets. NetworkPolicy restricts IPs/ports; authorization inside Payment governs business actions.

### 16.4. Acceptance Criteria

- Booking developers cannot read Payments Secrets or create ClusterRoleBindings.
- Workloads in `booking-prod` can only reach required dependencies.
- Creating a Pod exceeding quota is rejected with a clear error message.
- Non-compliant images (e.g., disallowed registries or prohibited privileged configurations) are rejected at admission.
- Non-prod upgrades do not affect the production control plane.
- Dashboards and on-call owners exist for cluster/namespace/workload incidents.
- Production data is never copied into QA without masking and approval.

## 17. Common Pitfalls

| Pitfall | Consequence | Mitigation |
|---|---|---|
| **Treating namespaces as absolute security boundaries** | Teams can bypass boundaries via cluster-level permissions or shared nodes/kernels | Assess threat model; separate clusters/accounts when needed |
| **One cluster for all environments without policies** | Dev disrupts production, noisy neighbors | Separate environments or enforce verified RBAC, quotas, network, admission, and node isolation |
| **Creating a cluster per team without platform automation** | Costs and upgrade/monitoring burden escalate rapidly | Use controlled shared clusters or build cluster vending first |
| **Namespaces per short-lived branch** | Accumulates orphaned resources and unrevoked secrets/volumes | Enforce TTLs, owners, cleanup jobs, and clear lifecycles |
| **Limiting CPU/memory without object quotas** | Teams can create excessive Pods, PVCs, or load balancers | Apply quotas covering both compute and cloud-backed objects |
| **NetworkPolicy exists but CNI does not enforce it** | False sense of security while traffic remains unblocked | Test from source/destination Pods and verify CNI enforcement |
| **Every team gets `cluster-admin`** | Namespace boundaries become meaningless | Least-privilege roles, audited break-glass access |
| **Staging diverges too far from production** | Testing misses real infrastructure bugs | Maintain parity on critical verification attributes |
| **Using tags/labels in place of IAM** | Modified metadata can subvert policies | Enforce independent admission/permissions and policies |
| **No owner for CRDs/webhooks/add-ons** | Cluster-wide outages and painful upgrades | Maintain cluster add-on catalog, owners, versions, and runbooks |

## 18. Boundary Design and Acceptance Checklist

### Cluster

- [ ] Clear justification for shared vs. dedicated clusters based on trust, failure domains, upgrades, quotas, and cost.
- [ ] Cloud account/network, control plane, cluster identity, and `cluster-admin` holders are strictly controlled.
- [ ] Node pools, autoscaling, version policies, add-on ownership, and upgrade processes are defined.
- [ ] Shared dependencies (DNS, registry, network, CI/CD, storage) are accounted for in the blast radius.

### Namespace

- [ ] Names, owners, environment, data classification, and cost metadata are standardized.
- [ ] RBAC restricts permissions to the appropriate namespace; indirect and cluster-wide permissions are audited.
- [ ] ResourceQuota, LimitRange, and lifecycle policies are in place.
- [ ] NetworkPolicy is enforced by the CNI; both allow and deny rules have been tested.
- [ ] Pod Security/admission, Secret access, and workload identities are controlled.
- [ ] Cluster-scoped resources are not mistaken for namespace-isolated resources.

### Environment and Operations

- [ ] Dev/test/staging/prod have appropriate boundaries, permissions, data, and configuration.
- [ ] Image artifacts are promoted consistently; secrets/configs are separated per environment.
- [ ] Staging matches production across networking, policies, versions, and delivery flows under test.
- [ ] Telemetry/alerts/runbooks exist per cluster, namespace, and workload.
- [ ] Processes exist for namespace provisioning/decommissioning, drift handling, incidents, and upgrades.
- [ ] Residual risks, risk acceptances, and triggers for stronger boundary separation are documented.

## 19. Practice Exercise

**Context:** A SaaS company has four development teams; two workloads process sensitive customer data, and two are public-read workloads. All teams want to deploy onto a managed Kubernetes platform. The Platform team has only three engineers; production requires planned maintenance, while dev needs fast self-service. Teams want admin rights inside their own namespaces.

Propose the following:

1. Initial cluster count and rationale based on environments, trust domains, and failure domains.
2. Namespace naming, ownership, labels, and lifecycle management.
3. RBAC sets for developers, release pipelines, on-call operators, and platform administrators.
4. Minimum ResourceQuota, LimitRange, and NetworkPolicy for each workload group.
5. Which admission/pod security rules to enforce and how exceptions are approved.
6. The path from commit to production: image promotion, GitOps/IaC, secrets, and rollbacks.
7. Signals to collect to prove namespace/cluster boundaries are genuinely effective.
8. Triggers that would require splitting into additional clusters or cloud accounts within the next six months.

**Hint:** Namespace admin permissions must be scoped down to concrete API operations; avoid granting arbitrary workload creation if it allows accessing nodes, `hostPath`, or privileged workload Secrets. Define trust domains and data classifications before committing to a shared cluster. A small Platform team should prioritize reusable modules/policies and guardrailed self-service rather than spinning up a new cluster for every request.

## 20. Key Takeaways

A **cluster** is the larger boundary covering the control plane, lifecycle, and failure domain; a **namespace** is a logical scope to organize resources and apply scoped permissions/policies; an **environment** represents the purpose and stage of a workload. These three concepts are related, not interchangeable.

Good design starts from **ownership, trust, data classification, failure impact, upgrade needs, operational capacity, and cost**. A namespace alone is not a complete security boundary; a dedicated cluster alone does not automatically guarantee isolated data and networking. Combine RBAC, quotas, network policies, admission controls, workload identity, node isolation, telemetry, and operational processes, then validate them with real tests.
