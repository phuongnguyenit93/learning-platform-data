# GitOps for AKS with Flux

When a team operates an **Azure Kubernetes Service (AKS)** cluster, the number of deployed components can grow quickly: APIs, queue workers, namespaces, ConfigMaps, Services, Ingresses, Horizontal Pod Autoscalers, policies, and monitoring resources. If every change runs via `kubectl apply` from a laptop or a pipeline holding cluster-admin rights, live state easily drifts away from approved configurations. During an incident, operations teams must answer: who changed the resource, what exact version is running in production, and how do we return to a safe version?

**GitOps** solves this by using a version-controlled declarative source (typically Git) as the **source of desired state**, and running an in-cluster controller to continuously **reconcile** Kubernetes state toward that desired state. **Flux** is a GitOps toolkit/controller suite for Kubernetes; on Azure, Flux v2 integrates with AKS through the **GitOps (Flux v2)** capability and corresponding Azure Kubernetes Configuration resources.

This lesson sits in the **AKS Operations** chapter of the **CLOUD_PROVIDERS_AZURE** module. Beyond Kubernetes YAML, we place GitOps inside the Azure ecosystem spanning subscriptions and resource groups, Microsoft Entra ID and Azure RBAC, Azure Container Registry (ACR), virtual networks, storage/data services, Azure Monitor, security, and cost. The goal is building an end-to-end **review → merge → reconcile → verify → rollback** workflow rather than merely installing Flux.

After this lesson, you will be able to:

- Explain GitOps principles and the difference between **pull-based GitOps** and push-based deployment pipelines.
- Explain the roles of Flux `source-controller`, `kustomize-controller`, `helm-controller`, and image automation controllers when installed.
- Structure a Git repository for multiple environments/clusters using Kustomize or Helm, distinguishing Git sources, `Kustomization`, and `HelmRelease`.
- Configure GitOps on AKS using the Azure CLI in an authorized lab and read reconciliation status.
- Design authentication to repositories and ACR, manage secrets safely, enforce least privilege, and define boundaries across Git, Azure, and Kubernetes.
- Troubleshoot drift, invalid manifests, unreachable sources, image pull errors, failing health checks, and unintended deletions caused by `prune`.
- Roll back via a controlled Git commit, monitor the application post-rollout, and decide when to suspend reconciliation.

## 1. What Is GitOps and What Problems Does It Solve?

**GitOps** is an operational practice for declarative systems: desired configuration is stored in a version-controlled source, reviewed and approved like code, and a controller automatically synchronizes running resources to the approved configuration. Commonly, Git stores Kubernetes manifests or Helm chart/version references, and Flux controllers watch the source and apply changes into the cluster.

Suppose production runs the `orders-api` Deployment with three replicas. Someone runs:

~~~bash
kubectl -n orders scale deployment/orders-api --replicas=1
~~~

If Git declares `replicas: 3` and Flux owns that field, the next reconciliation cycle brings `replicas` back to 3. This is **drift correction**: manual edits outside the desired-state source are no longer the lasting source of truth.

However, GitOps **does not automatically distinguish dangerous changes from safe ones**. If someone with merge rights changes `replicas: 0`, Flux will still apply that configuration if policies and permissions allow it. Therefore, GitOps must be paired with code reviews, RBAC, testing, policies, image scanning, and monitoring.

### Practical Principles

1. **Declarative:** resource state is described using YAML/Kustomize/Helm values, minimizing hard-to-reproduce imperative steps.
2. **Version-controlled:** every meaningful change has a commit, history, reviewer, and linked change ticket.
3. **Automated pull/reconcile:** controllers pull desired state and update Kubernetes via its API without giving CI pipelines production kubeconfigs.
4. **Observable and self-healing:** exposes Ready/Reconciling status, events, logs, alerts, and error handling.
5. **Scoped permissions:** clearly separates who can merge, who can deploy controllers, and who can modify namespace vs cluster-scoped resources.

Simply copying YAML files into Git while still deploying manually with `kubectl apply` **does not establish a complete GitOps control loop**. Conversely, having Flux reconcile continuously without protecting the repository still lacks proper governance.

### Control Loop Diagram

~~~mermaid
flowchart LR
    DEV[Developer / Platform engineer] --> PR[Pull request]
    PR --> CHECK[Test, scan, policy, review]
    CHECK -->|Merge| GIT[(Git desired state)]
    GIT -->|Poll or webhook| FLUX[Flux controllers in AKS]
    FLUX -->|Kubernetes API| API[Kubernetes API server]
    API --> WORK[Deployments, Services, ConfigMaps...]
    WORK -. Status / events .-> OBS[Monitor + alert]
    API -. Observed state .-> FLUX
    FLUX -. Reconcile to desired state .-> API
~~~

Flux is a **reconciler**, not a source-code or image store. A Git repository, chart repository, or OCI artifact holds configuration; ACR/registries store container images. **Image building and Kubernetes deployment are two separate stages.**

## 2. Distinguishing CI, CD, GitOps, and IaC

| Activity | Input | Output | Typically Executed By |
|---|---|---|---|
| **CI** (Continuous Integration) | Source code, Dockerfile | Build/tests, image digest, scan/SBOM | GitHub Actions, Azure Pipelines, or CI runners |
| **GitOps CD** | Merged YAML/Kustomize/Helm values | Kubernetes workloads matching approved config | Flux controllers running inside AKS |
| **Infrastructure as Code** | Azure resource definitions | AKS, VNet, ACR, identities, monitoring, role assignments | Bicep/ARM/Terraform and infrastructure pipelines |
| **Kubernetes manifests** | Kubernetes object specifications | Deployments, Services, ConfigMaps, policies... | Applied by Flux via the Kubernetes API |
| **Runtime monitoring** | Metrics, logs, traces, events | Alerts, keep-or-rollback decisions | Azure Monitor, Prometheus, App Insights, ops team |

Example lifecycle for a new API version:

1. CI builds and tests the image, pushing it to ACR with an immutable tag or recording its digest.
2. A pull request in the **configuration repository** updates the image reference from `orders-api:1.4.0` to `orders-api:1.4.1`.
3. The PR goes through peer review, YAML/Kustomize validation, and policy checks.
4. Once merged, Flux pulls the new commit and applies the manifests.
5. Kubernetes creates new Pods according to the Deployment rollout strategy.
6. Monitoring validates readiness, error rates, latency, and business behavior; if broken, revert the commit instead of leaving long-lived manual hotfixes.

**Never grant CI production kube-admin access just to deploy an image.** With GitOps, CI only needs permission to push images and propose/update Git configuration through approval workflows; Flux updates Kubernetes using in-cluster permissions. Both Git credentials and Flux's own permissions must still be strictly protected.

### GitOps Does Not Replace Bicep/Terraform

Flux manages **Kubernetes API** resources and existing CRDs. It does not automatically provision a VNet, subnet, AKS cluster, Azure SQL, or ACR just because you add a Deployment to Git. While Kubernetes operators/controllers exist to manage cloud infrastructure where supported, that is an advanced architecture with its own risk and RBAC surface, not the default.

Typically:

- **Azure IaC:** AKS clusters, node pools, identities, ACR, VNets, firewalls, workload identities, Azure Monitor.
- **GitOps:** delegated namespaces, application Deployments, Services, ConfigMaps, Ingresses, HelmReleases, and permitted policies/controllers.
- **CI/CD and security:** image builds, scans, PR validation, approvals, and promotion.

## 3. What Components Make Up Flux v2?

Flux is a set of Kubernetes controllers. Which controllers or extensions are present depends on how Flux is installed, enabled features, and version—never assume every cluster automatically enables image automation.

| Component | Function | Common API Resources |
|---|---|---|
| **source-controller** | Fetches Git/OCI/Helm sources and produces artifacts for other controllers | `GitRepository`, `OCIRepository`, `HelmRepository` |
| **kustomize-controller** | Reconciles Kubernetes manifests using Kustomize | `Kustomization` (Flux CRD) |
| **helm-controller** | Reconciles Helm releases declared in Git | `HelmRelease` |
| **notification-controller** | Dispatches event alerts and receives webhooks per configuration | `Alert`, `Provider`, `Receiver` |
| **image-reflector-controller** | Scans registry image tags | `ImageRepository`, `ImagePolicy` |
| **image-automation-controller** | Updates Git per image automation policies when authorized | `ImageUpdateAutomation` |

**A Flux `Kustomization`** and **a Kustomize `kustomization.yaml` file** are two different things:

- `kind: Kustomization`, API group `kustomize.toolkit.fluxcd.io`: a Kubernetes object telling Flux **which source to read, which path to build, and how to reconcile/prune/health-check**.
- `kustomization.yaml` file inside Git: instructions for **Kustomize to assemble manifests**, bases/overlays, image overrides, namespaces, and patches.

Flux `kustomize-controller` typically renders manifests from the target path and runs server-side apply against the Kubernetes API. It tracks a resource inventory to prune objects removed from desired state per configured policy.

### Data Flow Between Controllers

~~~mermaid
flowchart TD
    GIT[(Git configuration repository)]
    GIT --> SRC[source-controller / GitRepository]
    SRC --> ART[Source artifact]
    ART --> KUST[kustomize-controller / Flux Kustomization]
    ART --> HELM[helm-controller / HelmRelease]
    KUST --> KAPI[Kubernetes API]
    HELM --> KAPI
    KAPI --> PODS[Deployments, Services, Jobs, ConfigMaps]
    REG[(ACR images)] -->|Kubelet/container runtime pull| PODS
    IMGR[Image automation controllers if enabled] -. Commits image updates .-> GIT
~~~

**ACR image pulls happen on the Pod runtime path**, not on `source-controller` reading Git. AKS nodes/kubelet need pull permissions—such as **ACR attach**, role assignments, or appropriate identities. When a Pod hits `ImagePullBackOff`, `source-controller` can still report `Ready=True` because it read the YAML cleanly; inspect Pod events and registry permissions separately.

## 4. GitOps on AKS: How Flux Integrates with Azure

You can deploy upstream Flux directly on Kubernetes or use the managed **GitOps (Flux v2)** capability integrated through **Azure Kubernetes Configuration** for AKS. Both paths differ in setup and management mechanics, yet both rely on Kubernetes controllers reconciling desired state.

With the Azure integration, typical components include:

1. **AKS cluster** and appropriately scoped control-plane access.
2. **Flux extension** (extension type `microsoft.flux`) running on the cluster.
3. **Azure Flux configuration** (`Microsoft.KubernetesConfiguration/fluxConfigurations`) referencing a Git/OCI source and one or more kustomizations.
4. **Flux Kubernetes custom resources** created/managed inside the cluster per the integration config.
5. **Azure RBAC + Kubernetes RBAC** controlling who creates configurations/extensions and what resources Flux may modify.
6. **Source credentials** for private repositories plus network connectivity to Git/OCI sources.

### Governance Architecture

~~~mermaid
flowchart TB
    SUB[Azure Subscription / Resource Group] --> AKS[AKS cluster]
    SUB --> GCFG[Azure Flux configuration]
    GCFG --> EXT[Flux extension]
    EXT --> CONTROLLERS[Flux controllers in AKS]
    REPO[(Git desired-state repository)] --> CONTROLLERS
    CONTROLLERS --> API[Kubernetes API]
    API --> NS1[Namespace orders]
    API --> NS2[Namespace payments]
    ACR[(Azure Container Registry)] -->|Image pull| NS1
    ACR -->|Image pull| NS2
    MON[Azure Monitor + Git history] -. Evidence .-> CONTROLLERS
~~~

Connecting a Git source **does not automatically grant controllers unlimited rights** across all namespaces. Execution rights depend on how Flux is installed/configured, its service accounts, and Kubernetes RBAC. In Azure configurations, choosing `cluster` vs `namespace` scope affects management boundaries; verify the extension's contract and namespace permissions before onboarding production.

### "Azure Resource Ready" Differs from "Workload Healthy"

For example, Azure Resource Manager may report the extension provisioned and the GitOps configuration created, while the Deployment fails to come up because an image tag does not exist. That is not end-to-end GitOps success. Verify **at least four layers**: Azure extension/configuration, Flux `GitRepository`/`Kustomization`, Kubernetes Deployment/Pods, and real application health via live requests.

## 5. Repository Structure for Multi-Environment AKS

Flux does not enforce a single mandatory repository layout. A clean governance pattern uses shared **bases** and environment **overlays** for dev/staging/prod, plus a `clusters` directory declaring which workloads belong to each cluster.

~~~text
gitops-config/
├── apps/
│   └── orders-api/
│       ├── base/
│       │   ├── deployment.yaml
│       │   ├── service.yaml
│       │   └── kustomization.yaml
│       └── overlays/
│           ├── dev/
│           │   └── kustomization.yaml
│           └── prod/
│               └── kustomization.yaml
├── clusters/
│   ├── aks-dev/
│   │   ├── orders-api.yaml
│   │   └── kustomization.yaml
│   └── aks-prod/
│       ├── orders-api.yaml
│       └── kustomization.yaml
└── README.md
~~~

This is an **illustrative layout for the learner's own Git repository**, not an instruction to create files outside the assigned lesson files. In a real lab, create your own repository following a reviewed structure.

Two levels to understand:

- `apps/orders-api/base` holds reusable Kubernetes configurations.
- `apps/orders-api/overlays/prod` customizes image tags, replica counts, resources, and production settings.
- `clusters/aks-prod` acts as Flux's entrypoint, declaring which apps or Kustomizations apply to the production cluster.

### One Repo or Multiple Repos?

| Approach | Pros | Risks / Limitations |
|---|---|---|
| **GitOps monorepo** for multiple apps/clusters | Easy visibility across related changes, single place for policies and reviews | Overly broad merge permissions without `CODEOWNERS`/branch protection |
| **Repo per team/app** | Clear ownership, independent pipelines | Requires bootstrap/aggregation patterns and shared standards |
| **Repo per environment** | Strong separation between staging and production | Can cause duplication and harder promotion of tested artifacts |
| **Separate source code and config repos** | Clean separation between CI and deployment permissions | Requires linking commits/image digests across both repos |

For production, enforce **protected branches, PR reviews, `CODEOWNERS`, status checks, and audit logs**. If dev and production share one Git branch, enforce strict folder boundaries and merge rules so an experimental PR cannot accidentally modify the production overlay.

## 6. Desired State: Kubernetes Manifests and Kustomize

Consider an `orders-api` workload running in the `orders` namespace. Container images come from ACR; the Deployment specifies resource requests/limits and readiness/liveness probes so rollouts have verifiable signals.

### 6.1. Base Deployment

~~~yaml
# apps/orders-api/base/deployment.yaml (illustrative example)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  labels:
    app: orders-api
spec:
  replicas: 2
  revisionHistoryLimit: 5
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: api
          image: myregistry.azurecr.io/orders-api:1.4.0
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 512Mi
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            initialDelaySeconds: 15
            periodSeconds: 20
~~~

This is a **sample manifest** that must be tuned for actual CPU/RAM, startup duration, replica count, availability zones, and SLOs. For slow-starting apps, consider `startupProbe` rather than arbitrarily inflating `initialDelaySeconds`. If readiness depends too tightly on a shared database, a DB hiccup could drop every Pod from Service endpoints.

### 6.2. Service

~~~yaml
# apps/orders-api/base/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: orders-api
spec:
  type: ClusterIP
  selector:
    app: orders-api
  ports:
    - name: http
      port: 80
      targetPort: http
~~~

`ClusterIP` keeps access internal to the cluster; it **does not expose a public Internet endpoint**. If public ingress is needed, design the ingress controller/gateway, domain, TLS/WAF, and network policies separately. Keep database credentials out of manifests.

### 6.3. Base Kustomize

~~~yaml
# apps/orders-api/base/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - deployment.yaml
  - service.yaml
~~~

### 6.4. Production Overlay

~~~yaml
# apps/orders-api/overlays/prod/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: orders
resources:
  - ../../base
images:
  - name: myregistry.azurecr.io/orders-api
    newTag: 1.4.1
replicas:
  - name: orders-api
    count: 3
~~~

If the `orders` namespace does not exist yet, create it via a managed manifest or bootstrap workflow before applying namespaced resources. Adding `namespace: orders` in Kustomize **does not prove** the namespace already exists. In multi-app GitOps setups, a dedicated platform Kustomization often manages namespaces, RBAC, quotas, and network policies, with app Kustomizations depending on that layer.

Example resource for the **platform bootstrap layer**, deployed before workloads:

~~~yaml
# platform/namespaces/orders.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: orders
  labels:
    application: orders
    environment: production
~~~

Manage this namespace inside a dedicated platform Kustomization with reviews for RBAC, quotas, and NetworkPolicies. Do not let multiple Kustomizations manage the `orders` Namespace with conflicting desired states; shared resources need one clear owner.

**Artifact recommendation:** the Kustomize `images` field uses tag `1.4.1` for illustration only. Production should use immutable tags with recorded digests, or specify images directly by digest per your tooling workflow, preventing mutable tags from silently changing contents.

## 7. Flux Custom Resources: GitRepository and Kustomization

To understand what happens under the hood, examine how Flux uses CRDs. This is the **pure Kubernetes Flux configuration approach**, separate from creating an Azure GitOps configuration in the next section; avoid applying both methods simultaneously to create the same resource.

### 7.1. GitRepository: Declaring the Configuration Source

~~~yaml
# flux-system/git-source.yaml (upstream Flux sample)
apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
metadata:
  name: platform-config
  namespace: flux-system
spec:
  interval: 1m
  url: https://github.com/example-org/gitops-config
  ref:
    branch: main
~~~

`url` is an **illustrative** repository, not a real URL. For private Git, configure authentication via supported secrets/identities; never embed tokens inside URLs or committed YAML. `source-controller` periodically fetches Git state and publishes an artifact pinned to the observed commit so Kustomizations read a consistent revision.

If the source becomes unreachable due to DNS, proxy, credentials, or wrong branch, `GitRepository` turns non-Ready and manifest updates pause until the source recovers. During temporary outages, already-deployed Kubernetes resources **do not vanish just because Git cannot be fetched**; exact behavior depends on the last applied state and controller health.

### 7.2. Flux Kustomization: Applying a Path

~~~yaml
# flux-system/orders-prod.yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: orders-prod
  namespace: flux-system
spec:
  interval: 5m
  retryInterval: 1m
  timeout: 3m
  path: ./apps/orders-api/overlays/prod
  prune: true
  sourceRef:
    kind: GitRepository
    name: platform-config
  healthChecks:
    - apiVersion: apps/v1
      kind: Deployment
      name: orders-api
      namespace: orders
~~~

Key fields:

| Field | Role | Watch Out For |
|---|---|---|
| `interval` | Normal reconciliation cadence | Not a strict per-second SLA; controllers have queues and processing limits |
| `retryInterval` | Retry cadence after errors per supported config | Does not override API or app timeouts |
| `path` | Folder inside the Git artifact where Flux builds manifests | Wrong path causes Kustomization failure or missing resources |
| `sourceRef` | Flux source consumed | Name and namespace must match |
| `prune: true` | Deletes resources previously tracked in Flux's inventory when removed from desired state per service semantics | **Can delete critical resources if a manifest is removed/renamed by mistake** |
| `healthChecks` | Checks resources post-apply | Deployment readiness differs from end-to-end business checks |
| `suspend` (if set) | Pauses reconciliation for this object | Use only per runbooks to avoid prolonged drift |

`healthChecks` waits for the Deployment to reach supported healthy conditions per Flux, yet **cannot tell** whether the API actually creates orders accurately. Production pipelines need synthetic/business tests beyond Kubernetes Ready conditions.

### 7.3. Flux Kustomization and Kustomize `kustomization.yaml`

How the two YAMLs work together:

~~~text
Flux Kustomization (CRD in cluster)
  spec.sourceRef: platform-config
  spec.path: ./apps/orders-api/overlays/prod
          |
          v
Kustomize kustomization.yaml (file in Git)
  resources: ../../base
  images: newTag 1.4.1
  replicas: count 3
          |
          v
Deployment + Service with final rendered configuration
~~~

When bootstrapping **multiple Kustomizations**, you can place Flux CRDs under `clusters/aks-prod` and configure a root Kustomization to apply them. Keep **one clear owner**: never create `orders-prod` via an Azure Flux configuration and simultaneously apply another `orders-prod` manifest that fights over it.

### 7.4. `dependsOn` and Deployment Ordering

An app may require namespaces, quotas, policies, or CRDs first. Flux Kustomizations support ordering dependencies where applicable:

~~~yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: orders-prod
  namespace: flux-system
spec:
  interval: 5m
  path: ./apps/orders-api/overlays/prod
  prune: true
  sourceRef:
    kind: GitRepository
    name: platform-config
  dependsOn:
    - name: platform-namespaces
~~~

This snippet is an **alternative variant** of the previous Kustomization, not a second identically named object to apply alongside it. `platform-namespaces` must genuinely exist and be Ready within Flux's scope. Avoid circular dependencies (A → B → A). Dependency ordering prevents missing-resource errors, though it does not replace database migrations or application-level readiness checks.

## 8. Setting Up GitOps on AKS via Azure CLI

The steps below describe **a reference lab**, not commands executed while authoring this guide. You need a test Azure subscription, an existing AKS cluster, a Git repository with safe manifests, and a valid ACR image. The operator needs permissions to manage AKS/Flux extensions/configurations plus required Kubernetes permissions.

**Lab scope boundary:** target only a dedicated test cluster. Creating extensions and Flux configurations alters how the cluster reconciles resources; never run them in production merely to test syntax.

### 8.1. Prepare Tooling

~~~bash
az login

SUBSCRIPTION_ID="<subscription-id-lab>"
RG="rg-aks-gitops-lab"
AKS="aks-gitops-lab"
CONFIG_NAME="aks-prod-config"
REPO_URL="https://github.com/example-org/gitops-config"

az account set --subscription "$SUBSCRIPTION_ID"
az account show --query "{id:id,name:name,tenant:tenantId}" -o table

# Check Azure CLI version and extension availability.
az version
az extension show --name k8s-configuration --output json
az extension show --name k8s-extension --output json
~~~

If extensions are missing, install them in an authorized environment:

~~~bash
az extension add --name k8s-configuration --upgrade
az extension add --name k8s-extension --upgrade
~~~

Flags, extension versions, and features can evolve. Check `az k8s-configuration flux --help` and `az k8s-extension create --help` on your installed CLI. Never install/upgrade extensions blindly on production runners without version pinning and testing.

### 8.2. Verify the Target Cluster

~~~bash
az aks show \
  --resource-group "$RG" \
  --name "$AKS" \
  --query "{id:id,location:location,provisioningState:provisioningState}" \
  --output json
~~~

In an authorized test environment, retrieve kubeconfig:

~~~bash
az aks get-credentials \
  --resource-group "$RG" \
  --name "$AKS"

kubectl cluster-info
kubectl get nodes
~~~

**Do not equate `get-credentials` with unlimited permissions:** Kubernetes API access also depends on Microsoft Entra integration, Kubernetes RBAC / Azure RBAC for Kubernetes authorization, and private cluster networking. Avoid `--admin` unless genuinely needed and approved.

### 8.3. Install or Verify the Flux Extension

In a supported Azure-integrated scenario, refer to this illustrative syntax:

~~~bash
az k8s-extension create \
  --resource-group "$RG" \
  --cluster-name "$AKS" \
  --cluster-type managedClusters \
  --name flux \
  --extension-type microsoft.flux \
  --scope cluster \
  --release-train stable
~~~

If the extension already exists, **do not create a duplicate**. Inspect its status:

~~~bash
az k8s-extension show \
  --resource-group "$RG" \
  --cluster-name "$AKS" \
  --cluster-type managedClusters \
  --name flux \
  --output json
~~~

Do not assume extension `ProvisioningState=Succeeded` means every Kustomization is Ready; inspect in-cluster objects and source statuses separately. Some Azure Flux configuration workflows handle or require extension setup in specific ways: check matching Azure/CLI docs before automating.

### 8.4. Create a Flux Configuration Pointing to the Repository

Example configuring a root or application path on AKS. To keep the lab simple, **point directly to the app overlay** containing Kubernetes manifests:

~~~bash
az k8s-configuration flux create \
  --resource-group "$RG" \
  --cluster-name "$AKS" \
  --cluster-type managedClusters \
  --name "$CONFIG_NAME" \
  --scope cluster \
  --namespace flux-system \
  --url "$REPO_URL" \
  --branch main \
  --kustomization name=orders-prod path=./apps/orders-api/overlays/prod prune=true
~~~

This is **one way to create an Azure-integrated configuration**, instead of manually applying the equivalent `GitRepository`/`Kustomization` CRDs from Section 7. Verify exact flags such as `--kustomization`, `--namespace`, or repo auth options via `az k8s-configuration flux create --help` for your CLI version.

**Private Git:** the example uses a public URL solely to avoid exposing credentials. For private repos, use an SSH deploy key, HTTPS credential, or supported integrated auth backed by managed secrets; never leak PATs or private keys into shell history, pipeline logs, or public YAML files.

**Input prerequisites:** the repo must exist, the path must exist, images must be pullable from ACR, required namespaces must exist, and the cluster must hold permissions to create the resources. A successful configuration creation pointing to an empty or wrong path will not deploy your workload.

### 8.5. Check Flux Configuration and Cluster Status

~~~bash
az k8s-configuration flux show \
  --resource-group "$RG" \
  --cluster-name "$AKS" \
  --cluster-type managedClusters \
  --name "$CONFIG_NAME" \
  --output json

kubectl get gitrepositories.source.toolkit.fluxcd.io -A
kubectl get kustomizations.kustomize.toolkit.fluxcd.io -A
kubectl get deployments -n orders
kubectl get pods -n orders
~~~

If the cluster lacks Flux CRDs, check the extension and installation status before blaming the Git repo. If CRDs exist but are not Ready, inspect controller logs, conditions, and source artifacts. If Flux is Ready yet Pods fail to run, check Deployment status, image pulls, and runtime readiness.

### 8.6. On-Demand Reconciliation

In a cluster with a compatible **Flux CLI** and sufficient Kubernetes permissions:

~~~bash
# Flux CLI targets the cluster selected in your active kubectl context.
flux get sources git -A
flux get kustomizations -A

# Confirm actual source/object names from flux get first.
flux reconcile kustomization orders-prod \
  --namespace flux-system \
  --with-source
~~~

`flux reconcile` triggers an immediate sync; **it does not modify Git commits** and will not force invalid manifests to apply. If a private source fails authentication, repeatedly triggering reconcile will not fix it. Fix `GitRepository` credentials/networking; if YAML fails schema or CRD checks, fix it via a Git PR.

**Watch resource names:** Azure Flux configurations may name in-cluster objects using integration naming conventions. Do not guess `GitRepository.metadata.name` from placeholder examples; list live objects first. Meanwhile, `orders-prod` matches the illustrative kustomization name passed during creation.

## 9. Promotion Strategy: Dev → Staging → Production

GitOps does not force all environments to run the same version simultaneously. A common pattern preserves an **immutable image digest** and promotes the exact tested artifact from lower environments upward.

~~~mermaid
flowchart LR
    CODE[Source commit] --> CI[Build + unit/integration + scan]
    CI --> ACR[ACR: image digest D]
    ACR --> PRDEV[PR updating dev config to D]
    PRDEV --> FLUXDEV[Flux dev reconcile]
    FLUXDEV --> TEST[Smoke + contract + load tests]
    TEST --> PRPROD[PR updating prod overlay to same D]
    PRPROD --> APPROVE[CODEOWNERS / change approval]
    APPROVE --> FLUXPROD[Flux prod reconcile]
    FLUXPROD --> MON[Health, SLO, business checks]
~~~

### Managing Overlays

~~~yaml
# apps/orders-api/overlays/dev/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: orders
resources:
  - ../../base
images:
  - name: myregistry.azurecr.io/orders-api
    newTag: 1.4.2-rc.1
replicas:
  - name: orders-api
    count: 1
~~~

Production stays on `1.4.1` until the new version is approved. **Do not just push a new tag to ACR and expect Flux to redeploy**: unless Git changes, Flux keeps reconciling the same desired image reference, unless you deliberately configured **image automation** or tag-tracking tooling.

### Branch Design and Merge Permissions

| Environment | Protection Controls |
|---|---|
| Dev | Basic PR/CI checks; only relevant teams can edit the dev overlay |
| Staging | Integration tests, contract tests, and restricted data access |
| Production | Protected branch, `CODEOWNERS`, accountable approvals, policy scans, audit, and rollback plan |

Never let CI push directly to the production branch with admin credentials bypassing reviews, even when image scans pass. **Business logic bugs still slip past security scanners.**

## 10. Reconciliation, Drift Detection, and Resource Ownership

Flux runs on a loop: fetch artifact, build manifests, diff against live state, and apply corrections per design. When someone edits a Kubernetes resource directly outside Git, Flux can revert the fields it owns back to desired state. This is a strength—and also why "quick `kubectl` hotfixes" do not stick.

### 10.1. Example Drift from Direct Edits

Desired state in Git:

~~~yaml
spec:
  replicas: 3
~~~

An operator runs:

~~~bash
kubectl -n orders scale deployment/orders-api --replicas=1
~~~

If `replicas` is managed by Flux and no conflict-avoidance mechanism is configured, the controller restores it to 3 on the next reconciliation pass.

**Important exception: HPA and field ownership.** When a Horizontal Pod Autoscaler manages `replicas`, having both Git YAML/Kustomize and HPA continually write to `replicas` causes contention or unpredictable behavior. GitOps design must explicitly define **which fields belong to Flux, HPA, or another operator**. Never assume "replicas always snap back to Git" for an HPA-managed Deployment without checking field ownership.

### 10.2. Reconciliation Interval

Values like `interval: 1m` or `5m` are target polling cadences, **not SLAs guaranteeing commits apply at exactly 60 or 300 seconds**. Actual time depends on:

- Git/artifact fetch cadence and controller state.
- Reconciliation queues and error backoff/retries.
- Object count and API server latency.
- Deployment/HelmRelease rollout time.
- Kustomization health checks and Pod readiness.
- Webhook receivers, if configured, which reduce change-detection latency.

Do not set `interval` to a few seconds across thousands of sources just to "deploy faster"; it hammers Git providers, the Kubernetes API, and controllers without improving release quality.

### 10.3. Distinguishing Three Types of Drift

| Drift Type | Example | Impact / Remediation |
|---|---|---|
| **Kubernetes runtime drift** | `kubectl edit` changes image/replicas on a Flux-managed resource | Flux reconciles back toward desired state |
| **Git/config drift** | Prod overlay specifies a different tag than approved in the release record | PR reviews, commit audits, branch protections, policies |
| **Azure infrastructure drift** | NSG/VNet/ACR roles changed outside Terraform/Bicep | Flux will not revert Azure changes unless a declarative Azure controller manages them |

Do not expect Flux to catch every form of drift. Combine Azure Policy, IaC drift detection, and Kubernetes policies/controllers for full coverage.

## 11. Prune: Powerful Feature, Significant Risk

In a Flux Kustomization, `prune: true` lets the controller delete resources **previously tracked in the Kustomization's inventory** that are no longer in the desired set. This keeps Git as the true source of desired state: deleting a manifest cleans up the corresponding cluster resource. However, a mistake in a PR can carry serious consequences.

### 11.1. Example Accident

Suppose a repo contains:

~~~text
apps/orders-api/overlays/prod/
  deployment.yaml
  service.yaml
  kustomization.yaml
~~~

A commit accidentally removes `service.yaml` from Kustomize resources. If Flux prunes that Service, the Service disappears from the cluster and API traffic breaks. For stateful resources like PersistentVolumeClaims or CustomResources with finalizers, impact depends on resource retention and protection policies; **never treat `prune` as harmless**.

### 11.2. Safeguards Before Enabling `prune`

- Require strict peer review on PRs that delete or rename resources, especially in prod namespaces.
- Run `kustomize build`/`kubectl diff` or scoped diffing tools in CI so reviewers see deleted objects clearly.
- Separate Kustomizations managing **shared/stateful resources** from stateless workload Kustomizations.
- For protected resources, evaluate Flux prune annotations/policies or supported deletion policies and verify exact behavior on your running version.
- Enforce Git history, branch protections, and code owners to block accidental deletions.
- Maintain independent backups and tested restore procedures for valuable data.

**Do not blindly set `prune: false` everywhere assuming you are safe.** Leaving deleted Git objects orphaned indefinitely in the cluster creates long-term drift and clutter. Choose policies based on **each resource's lifecycle**.

### 11.3. Transferring Resource Ownership

If you want to move a Deployment from Kustomization A to Kustomization B, plan the handoff carefully so two controllers do not fight or A does not prune the object before B takes over. Swapping owners in one uncoordinated PR is risky.

Clarify:

1. Exact Resource ID (group/version/kind/namespace/name).
2. Which Kustomization currently owns the inventory and fields.
3. Current `prune`/deletion policies.
4. When B applies, dependencies, and rollback steps.
5. How to verify zero window where the resource is orphaned or deleted.

## 12. Helm with Flux: `HelmRepository` and `HelmRelease`

Many organizations deploy ingress controllers, monitoring stacks, cert-manager, or applications via **Helm charts**. Flux manages these releases using dedicated controllers and CRDs. With GitOps, avoid running manual `helm upgrade` as your primary deployment channel on `HelmRelease`-managed resources: reconciliation will revert manual changes back to the declared spec.

### 12.1. HelmRepository

~~~yaml
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: demo-charts
  namespace: orders
spec:
  interval: 10m
  url: https://charts.example.org
~~~

`https://charts.example.org` is an **illustrative address—do not use it in production**. For OCI Helm charts or private chart registries, use the supported source type/protocol and proper authentication; do not assume HTTP chart index repositories and OCI registries use the same protocol.

### 12.2. HelmRelease

~~~yaml
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: sample-api
  namespace: orders
spec:
  interval: 5m
  chart:
    spec:
      chart: example-api
      version: "1.2.3"
      sourceRef:
        kind: HelmRepository
        name: demo-charts
        namespace: orders
  values:
    replicaCount: 3
    image:
      repository: myregistry.azurecr.io/orders-api
      tag: "1.4.1"
    service:
      type: ClusterIP
~~~

This manifest **illustrates syntax and structure only**: do not assume `example-api`, its `values`, or the endpoint exist. In a real repo, verify the chart schema, supported `HelmRelease` API version, namespace/permissions, and required chart values.

### 12.3. Kustomize or Helm via Flux?

| Criterion | Kustomize | Helm via Flux |
|---|---|---|
| Primary config model | Kubernetes YAML + base/overlay/patches | Chart templates + values + release lifecycle |
| Best fit | Internal workloads with light templating, environment overlays | Packaged apps or platform stacks with maintained charts |
| Version tracking | Git commit + manifests/images | Git commit + chart version + values/images |
| GitOps rollback | Revert/PR updating overlay, Flux reapplies | Revert chart version/values, Flux reconciles `HelmRelease` |
| Risks | Prune and field/resource mutations | Helm hooks, CRDs, dependencies, upgrade/remediation policies |

**Manual `helm rollback` will not stick** if `HelmRelease` in Git still specifies the new version. With Flux, the standard path is **reverting desired state in Git** and watching `helm-controller` reconcile. `helm-controller` supports configurable remediation strategies; still test the app and manage data migrations separately.

## 13. Image Automation with Flux: Useful, Yet Needs Controls

Flux offers optional controllers to:

1. Watch new image tags/digests in ACR or another registry (`ImageRepository`).
2. Select tags matching a policy (`ImagePolicy`).
3. Propose or commit updates back to Git (`ImageUpdateAutomation`) when authorized.
4. Trigger source/Kustomization reconciliation on the updated commit.

~~~mermaid
flowchart LR
    CI[CI build/scan] --> ACR[ACR repository]
    ACR --> REFLECT[Image reflector + ImagePolicy]
    REFLECT --> AUTO[ImageUpdateAutomation]
    AUTO -->|Git commit when authorized| GIT[Git configuration repository]
    GIT --> FLUX[Flux source/kustomize controller]
    FLUX --> AKS[AKS deployment]
~~~

Image automation **is not necessarily installed/enabled by default** across all Flux extension setups. Nor does it replace production approvals: if a controller holds direct write access to the production branch without a PR gate, an under-tested image can automatically become production desired state.

### Recommended Policy

- For **dev**, you may automate image selection from test build branches subject to policies and checks.
- For **staging**, restrict sources to scanned images passing integration tests.
- For **production**, prefer pipeline-opened commits/pull requests with **human approval or strong evidence-backed automated gates**, rather than direct branch auto-commits.
- Use immutable tags, build metadata, and recorded digests. Avoid vague policies picking `latest`.
- Scope Git write credentials tightly for automation controllers, separate dev/prod branch permissions, and protect deploy keys.
- With private-endpoint ACRs, image reflector needs registry network/DNS reachability and read rights; this path can differ from kubelet image pulls.

### Is Image Automation Mandatory for GitOps?

**No.** The most stable pattern for many teams is having CI build/push images and open a reviewed PR updating the image reference in Git, which Flux then reconciles after merge. Image automation helps with high release volume across many images once strict controls exist, yet it increases credential surface and debugging complexity.

## 14. GitOps Security: Identities, Secrets, and Permission Boundaries

GitOps shifts execution from pipelines/laptops to controllers **continuously running inside the cluster**. Consequently, controller permissions and Git source integrity become high-value assets. A malicious commit merged into the production branch becomes an automated Kubernetes mutation.

### 14.1. Four Distinct Permission Layers

| Layer | Example Permissions | Mistake to Avoid |
|---|---|---|
| **Git** | Who can view/merge repos, create tags/releases, or edit pipelines? | Repo-wide write tokens or disabled branch protection |
| **Azure control plane** | Who creates Flux extensions/configurations or manages AKS/ACR/identities? | Granting subscription-wide Owner to developers checking deployments |
| **Kubernetes API** | Which objects can Flux's service account create/delete? | App-team controllers holding `cluster-admin` across all namespaces |
| **Data plane** | Can runtime Pods read Blob/SQL/Key Vault? | Treating Flux/Kubernetes admin rights as application data access |

**Microsoft Entra ID / Azure RBAC** governs Azure resources and can integrate with Kubernetes authorization; **Kubernetes RBAC** governs Kubernetes API operations per cluster settings. Design both layers together—never assume an Azure `Contributor` role grants everything inside Kubernetes.

### 14.2. Scoping Controller Permissions

A production model:

- The platform team owns `flux-system`, core controllers, cluster-scoped CRDs, shared network policies, and admission policies.
- The `orders` team proposes manifest changes for their own app/namespace via PRs; the app's Flux Kustomization runs with a **least-privilege service account** where supported by the Flux architecture.
- The security team reviews changes affecting RBAC, ClusterRoles, admission policies, public Gateways/Ingresses, and network policies.
- CI pipelines hold permissions to build/push to ACR and open PRs, never a production admin kubeconfig.

Flux `Kustomization` supports `spec.serviceAccountName` where configured to reconcile under a scoped Kubernetes identity. When using a custom service account, grant only the permissions required for its managed resources—including get/list/watch/patch and delete if `prune` is enabled—**without granting gratuitous cluster-wide rights**. Check service account namespaces and RoleBindings/ClusterRoleBindings carefully, especially when Flux CRDs live in `flux-system` while target resources live in `orders`.

**Do not confuse `scope=namespace` on an Azure Flux configuration with a guarantee that Flux controllers cannot touch any cluster-scoped resource.** Effective authority depends on extension implementation, service account configuration, Kubernetes RBAC, and managed CRDs; verify live permissions rather than relying on a flag name.

### 14.3. Private Git Sources and Credentials

For private repositories, access options include SSH deploy keys, HTTPS tokens, or integrated identity/workload federation where supported. Rules:

1. Prefer **read-only** credentials for `source-controller`; only `image-automation-controller` needs write rights when enabled.
2. Scope tokens to specific repos/branches, enforce expiration, and rotate regularly.
3. Never paste PATs or private keys into Git manifests, Docker images, shell history, or public tickets.
4. Enforce SSH `known_hosts` / TLS certificate verification where supported.
5. Monitor authentication failures and credential rotation events.
6. Secure network paths to Git providers and registries using DNS, proxies/firewalls, or Private Endpoints as required.

If the Git source sits outside Azure, AKS networking must reach that endpoint per cluster architecture; having a Private Endpoint from AKS to ACR **does not** mean `source-controller` can reach an external Git provider.

### 14.4. Never Commit Plaintext Secrets

The following manifest **must never be committed** to a production repo:

~~~yaml
# UNSAFE EXAMPLE: do not apply and do not commit to Git
apiVersion: v1
kind: Secret
metadata:
  name: payment-key
  namespace: orders
type: Opaque
stringData:
  API_KEY: "plaintext-sensitive-token"
~~~

Base64-encoded `Secret.data` is **not secure encryption either**. Instead, adopt an enterprise-approved strategy:

- **Azure Key Vault + External Secrets Operator or Secrets Store CSI Driver** where deployed and supported: manage secrets in Key Vault, grant scoped AKS/workload identities, and sync/mount into Pods via dedicated mechanisms.
- **SOPS with KMS/Key Vault keys** where supported: commit only encrypted files and grant decryption rights strictly to the scoped Flux controller. Never commit decryption private keys into the same repo.
- **Managed identity / Microsoft Entra Workload ID**: wherever apps can access Azure data services passwordlessly, assign least-privilege data-plane RBAC and eliminate static secrets altogether.

None of these options exempt you from Key Vault access governance, rotation, audit logging, threat modeling, and application secret-reload design. With External Secrets, Flux can manage **`ExternalSecret` CRDs**, provided the operator is installed and Ready first—enforce dependency ordering.

### 14.5. Distinguishing Three Critical Identities

| Identity | Used For | Does Not Automatically Grant |
|---|---|---|
| **Flux Git source credential** | Reading the desired-state repository | Kubelet permission to pull images from ACR |
| **AKS kubelet/registry identity** | Pulling container images onto nodes | App runtime access to Azure SQL / Key Vault |
| **Pod/workload identity** | Runtime API accessing Azure services via Entra RBAC | Permission to write to Git or modify the AKS cluster |

A Ready `GitRepository` can coexist with Pods in `ImagePullBackOff` when kubelet identity lacks ACR pull rights. Conversely, successful image pulls with Pods getting 403 from Key Vault point to workload identity or Key Vault data-plane RBAC. Troubleshoot the **exact identity of the failing path**.

### 14.6. Network Policies and Supply Chain

- Prevent GitOps controllers and workloads from holding unrestricted egress where network segmentation is required; allowlist only needed domains/endpoints.
- On private AKS clusters, verify DNS/proxy routing for Git providers, ACR, and Azure management endpoints.
- Scan and pin versions of Flux extensions/controllers and CRDs before upgrading—not just application images.
- Adopt signed commits/tags, image provenance/attestation, and admission policies where required.
- Never allow arbitrary application-repo PRs to create `ClusterRoleBinding` objects or install cluster-wide CRDs.

## 15. Observing Reconciliation: Knowing Which Commit Is Running

A dashboard showing green `kubectl get pods` is not enough. Link Git commits, artifact digests, Flux reconciliation status, Kubernetes rollouts, and business metrics together.

### 15.1. Evidence Chain to Preserve

~~~text
Git commit SHA / PR / reviewer
         ↓
GitRepository artifact revision (commit)
         ↓
Flux Kustomization observed revision + Ready condition
         ↓
Kubernetes Deployment image digest / rollout condition
         ↓
Ready Pods + app synthetic tests + SLO metrics
~~~

`GitRepository Ready=True` only proves the source was fetched cleanly per contract. `Kustomization Ready=True` indicates reconciliation/health succeeded per Flux configuration—it does not guarantee payments, reports, data integrity, or external APIs are healthy.

### 15.2. Read-Only Investigation Commands

~~~bash
# Inspect Flux objects via the Kubernetes API.
kubectl get gitrepositories.source.toolkit.fluxcd.io -A
kubectl get kustomizations.kustomize.toolkit.fluxcd.io -A

# Replace namespace/name with live objects in your cluster.
kubectl -n flux-system describe gitrepository platform-config
kubectl -n flux-system describe kustomization orders-prod

# Inspect workload status.
kubectl -n orders rollout status deployment/orders-api --timeout=180s
kubectl -n orders get deploy,svc,pods -o wide
kubectl -n orders get events --sort-by=.metadata.creationTimestamp
~~~

`platform-config` comes from the upstream Flux pattern in Section 7; in Azure-managed configurations, object names may differ. List live objects before running `describe`. Always check `kubectl config current-context` before running commands so you do not query the wrong cluster.

With the Flux CLI:

~~~bash
flux get sources git -A
flux get kustomizations -A
flux get helmreleases -A

# Read errors by controller/resource.
flux logs --all-namespaces --level=error
~~~

Exact flags or options may vary across CLI/controller versions; check `flux --help`. When the Flux CLI is unavailable, use `kubectl`, the Azure Portal, and controller logs.

### 15.3. Interpreting Conditions and Events

| Condition / Event | Common Meaning | What to Check |
|---|---|---|
| Source `Ready=False` | Failed to fetch Git/OCI/Helm artifact | URL, branch, auth, DNS, TLS, rate limits |
| Kustomization `Ready=False` | Build/apply/health error or dependency unready | `path`, schema, namespace, RBAC, `healthChecks` |
| HelmRelease `Ready=False` | Chart fetch, install/upgrade, or health failure | Chart version, values, hooks, CRDs, `helm-controller` logs |
| Deployment not Ready | Insufficient replicas, failing readiness, or scheduling issue | Pod events, probes, resources, node status |
| `ImagePullBackOff` | Cannot pull container image | Registry, tag/digest, kubelet identity, network |
| Pod `CrashLoopBackOff` | App/entrypoint crashing repeatedly | Container logs, env, dependencies, startup |
| 5xx rises despite Flux Ready | Application/business logic bug or dependency outage | App Insights/traces, synthetic transactions |

### 15.4. Azure Monitor and Log Analytics

Collect across:

- Flux controller console logs and Kubernetes events.
- Azure Resource Manager Activity Logs for extension/configuration/permission changes.
- AKS Container Insights / Managed Prometheus as configured.
- Application Insights / OpenTelemetry for requests, errors, and dependency latency.
- ACR logs to audit image pushes/pulls where enabled.
- Git hosting audit logs for PR merges, branch protection edits, and token changes.

**Do not assume every log source automatically flows into a single Log Analytics table.** Configure diagnostic settings, agents/exporters, and telemetry instrumentation explicitly, then verify schemas, retention, and read RBAC. Alerts should distinguish Flux controller errors, Kubernetes workload failures, and business-layer failures.

### 15.5. GitOps Operational KPIs

| KPI | Interpretation |
|---|---|
| **Reconciliation freshness** | Time from approved commit to matching observed revision |
| **Ready coverage** | Percentage of critical Kustomizations/HelmReleases currently Ready |
| **Drift recovery** | Time to heal intentional or accidental drift |
| **Deployment lead time** | Time from commit to genuinely healthy workloads, not merely apply success |
| **Rollback time** | Time to restore service quality after a faulty release |
| **Prune incidents** | Count of unintended resource deletions caused by config/lifecycle errors |
| **Source failures** | Frequency of Git auth/DNS/provider outages disrupting reconciliation |
| **Policy violations** | PRs/manifests caught violating RBAC, image trust, or secret rules |

KPIs need **clear time windows and denominators**. If `source-controller` fails to pull Git for 30 minutes while Pods stay healthy, that is still a configuration-control outage requiring action—it may not cause immediate HTTP errors, yet it blocks emergency patches or rollbacks.

## 16. Git-Based Rollback and Emergency Handling

### 16.1. Durable Rollback via `git revert`

Suppose commit `abc1234` in the config repo bumped an image from `1.4.0` to `1.4.1`; after Flux reconciled, API errors spiked. The durable fix is **updating desired state in Git** through a controlled flow:

1. Pause promotion pipelines so new commits do not keep pushing broken versions.
2. Identify the **offending commit/PR**, running tag/digest, and impacted resource scope.
3. Create a **revert commit** or PR restoring the stable image/config; verify side effects if the original commit touched multiple resources.
4. Review, validate, and merge via approved break-glass procedures if urgent.
5. Watch `GitRepository`/`Kustomization` observed revision and the Kubernetes Deployment rollout.
6. Run smoke/synthetic/business tests and verify error rates and latency recover.
7. Log the change/incident, root cause, blast radius, and preventive follow-ups.

Bash example executed inside **your own copy of the config repository**—never run unapproved directly on production repos:

~~~bash
# Illustrative only: replace SHA with the actual commit to undo.
git log --oneline -n 10
git show --stat abc1234

# Create revert commit after confirming exact changes to undo.
git revert abc1234

# Inspect diff, run tests, open PR, and merge per process.
git show --stat --oneline HEAD
~~~

`git revert` does not necessarily run directly against a protected branch. In most organizations, creating a branch and opening an approved PR is required. If commit `abc1234` also included an incompatible database schema change, reverting manifests alone will not restore service.

### 16.2. Why `kubectl rollout undo` Is Not a GitOps Rollback

An operator might run:

~~~bash
# Break-glass example: never run in production without authorization.
# kubectl -n orders rollout undo deployment/orders-api
~~~

This temporarily alters runtime state. However, if Git still declares the newer image, **Flux will reconcile again** and push the Deployment right back to the broken desired state. Therefore, it is not a durable rollback while Flux remains active.

If emergency direct intervention is unavoidable:

- Confirm which Flux Kustomization owns the Deployment.
- Deliberately **suspend reconciliation** before applying authorized manual fixes, or update Git immediately.
- Log timestamps, owners, and every out-of-band change.
- Reconcile final desired state back into Git before resuming reconciliation cleanly.

### 16.3. Conditional Suspend/Resume

In an environment with the Flux CLI and sufficient permissions:

~~~bash
# TEMPORARILY PAUSES reconciliation of the Kustomization; can introduce drift.
flux suspend kustomization orders-prod \
  --namespace flux-system

# Once Git holds the verified desired config and change is approved:
flux resume kustomization orders-prod \
  --namespace flux-system

flux get kustomizations -A
~~~

Do not treat `suspend` as a global pause button for every controller/resource. Other Flux sources, `HelmReleases`, or Kustomizations may keep running depending on scope and dependencies. Prolonged suspension leaves security fixes unapplied, desired state unenforced, and automation broken. Record the incident, owner, resume timestamp, and verify all diffs after resuming.

### 16.4. What Git Rollback Cannot Automatically Undo

| Change | Why `git revert` Alone Is Insufficient |
|---|---|
| Breaking database schema migration | Git manifests do not restore dropped columns or altered data |
| Incompatible message/event schema | Old consumers cannot parse newly emitted events |
| Secret rotation | Old secrets may already be expired or revoked |
| PVC/PV deletion via `prune` | Underlying data may be wiped per reclaim/backup policy; recreating YAML does not restore bytes |
| External API side effects | Already-sent payments or emails do not unsend themselves |
| CRD upgrade | Custom resource storage versions may have migrated incompatibly |
| Azure resource drift | Flux does not automatically revert Azure changes outside its managed scope |

Thus, safe release engineering requires **expand–migrate–contract**, backups/restores, idempotency, versioned messages, and RPO/RTO DR plans—not just a revert button.

## 17. Layer-by-Layer GitOps Troubleshooting

When a deployment fails to update as expected, isolate the failure along **Git fetch → artifact → Kustomize/Helm → Kubernetes API → scheduling/runtime → application**. Changing multiple variables at once makes debugging non-reproducible and introduces extra drift.

### 17.1. Common Failure Modes

| Symptom | Possible Cause | Evidence / Action |
|---|---|---|
| `GitRepository Ready=False` | Wrong repo URL/branch, expired SSH key/PAT, TLS/proxy/DNS block | Describe source, `source-controller` logs, verify credentials/network |
| New Git commit not observed | Polling interval, stuck Git source, failed webhook, or wrong branch | `GitRepository.status.artifact.revision`, reconcile the exact source name |
| `Kustomization Ready=False: path not found` | Wrong `spec.path` or folder lacks `kustomization.yaml`/manifests | Check Git artifact, path, and run local Kustomize build |
| `Kustomization Ready=False: build failed` | Invalid Kustomize resources/patches or missing files | Build overlay in CI/lab and inspect controller condition |
| `Kustomization apply failed: forbidden` | Service account lacks Kubernetes RBAC | Inspect Role/RoleBinding/ClusterRole, namespace, and API permissions |
| `Health check timeout` | Deployment not Ready, failing probes, or slow API server | Describe Deployment/Pods, Pod logs/events, actual timeout |
| `HelmRelease failed` | Chart source, values, hooks, or CRD error | Describe HelmRelease, Helm repo status, `helm-controller` logs |
| `ImagePullBackOff` | ACR lacks kubelet pull rights, nonexistent tag, DNS/firewall | Pod events, registry/image digest, kubelet identity |
| `CrashLoopBackOff` | App crash, bad config/secret, OOM | Pod logs/`--previous`, env vars, resource limits, dependencies |
| Prolonged `Pending` | Insufficient node capacity, taints/tolerations/affinity/PVCs | Describe Pod, nodes/pools, scheduler events |
| `Flux Ready=True` yet HTTP 500 | Business logic bug or DB/API dependency failure | Application Insights/traces/synthetic tests, not Flux status alone |
| Resource created then disappears | `prune`, another controller owning the object, admission/policy | Git diff, Flux inventory, events, audit logs |
| `kubectl edit` gets "undone" | Flux reconciliation restoring desired state | Check Git and field ownership; open a formal PR instead |
| Git reverted yet app still broken | Kustomization not synced yet, or schema/secret/queue incompatibility | Observed revision, rollout status, data compatibility |
| Controller pods not running | Extension/cluster resources/networking or version mismatch | Flux extension status, controller events, node capacity |

**Never delete the `flux-system` namespace or reinstall the entire extension as a first troubleshooting step.** Doing so wipes controllers/configurations, removes repair paths, and disrupts workloads across teams. Always read exact error messages and isolate the failing layer first.

### 17.2. Step-by-Step Runbook

**Step 1 — Confirm exact target:** Azure subscription, AKS cluster, `kubectl` context, Flux configuration name, namespace, and Kustomization/HelmRelease.

~~~bash
az account show --query "{id:id,name:name}" -o table
kubectl config current-context
kubectl cluster-info
kubectl get nodes
~~~

**Step 2 — Azure integration:** check extension/configuration via `az k8s-extension show` and `az k8s-configuration flux show` if using Azure integration. If the extension failed, distinguish provisioning errors from Git source errors.

**Step 3 — Flux sources:**

~~~bash
kubectl get gitrepositories.source.toolkit.fluxcd.io -A
flux get sources git -A
~~~

Inspect `status.conditions`, artifact revision, and error messages. If the Git source is not Ready, do not jump straight to the Deployment guessing at runtime causes.

**Step 4 — Kustomizations/Helm:**

~~~bash
kubectl get kustomizations.kustomize.toolkit.fluxcd.io -A
flux get kustomizations -A
flux get helmreleases -A
~~~

Verify `sourceRef`, `path`, `prune`, dependencies, `serviceAccount`, and observed revision. If manifests are rejected, check API/admission errors and cluster RBAC.

**Step 5 — Kubernetes workloads:**

~~~bash
kubectl -n orders get deploy,svc,pods
kubectl -n orders describe deployment orders-api
kubectl -n orders get events --sort-by=.metadata.creationTimestamp
kubectl -n orders rollout status deployment/orders-api --timeout=180s
~~~

If Pods are not Ready, inspect container logs, readiness/liveness probes, registry pulls, resource quotas, nodes/pools, and networking. A Kustomization only waits for health if checks are configured; without matching checks, Flux may mark Ready before the app actually stabilizes.

**Step 6 — Application:** probe synthetic endpoints, check HTTP status codes, p95/p99 latency, SQL/Storage/Key Vault, ingress, external APIs, and business transactions.

**Step 7 — Durable remediation:** fix the Git PR or IaC config in the rightful source of truth; avoid live `kubectl` edits outside break-glass incidents. Confirm the controller applies the exact commit/hash and close the incident only after SLOs recover.

### 17.3. Distinguishing Git Status from Kubernetes Conditions

A merged commit only proves Git holds desired state. A Kustomization recording `lastAppliedRevision` matching that commit only proves the controller applied the version per its logic; post-scheduling Pod errors, application-layer dependency failures, and external side effects still require separate verification.

Never use a `Ready=True` column alone to auto-promote into production without smoke and business tests. Flux is a configuration synchronizer, **not a comprehensive business validation engine**.

## 18. GitOps and Controlled Rollouts on AKS

A Deployment with `strategy: RollingUpdate` and a readiness probe replaces Pods gradually. However, Flux **does not natively understand "canary 5%, 25%, 50%"** simply from reconciling a Deployment. Weighted request-level canary or blue-green rollouts require an additional rollout controller/ingress or service mesh, paired with metrics and rollback policies.

### 18.1. Three Deployment Tiers

| Tier | Mechanism | Best Fit |
|---|---|---|
| **Rolling update** | Kubernetes Deployment rolling strategy, readiness, PodDisruptionBudget where appropriate | Solid default for many stateless web APIs |
| **Traffic-split canary / blue-green** | Two versions + weighted routing controller/ingress, e.g., Flagger on a compatible stack | When shifting traffic gradually by SLO and risk |
| **User-targeted feature flags** | Application/feature management config, cohort targeting | Rolling out features without altering infrastructure traffic routing |

Having Flux installed **does not imply** Flagger, Argo Rollouts, or a service mesh is present. When adding a progressive delivery tool, Flux can manage its CRDs/configs in Git while the rollout controller shifts traffic. Verify compatibility with your chosen ingress/gateway and metric sources.

### 18.2. Per-Environment Rollout and Readiness

A reliable sequence:

1. CI builds the new artifact, runs security scans, and executes unit/integration tests.
2. PR updates the dev overlay; Flux dev reconciles.
3. Run smoke/contract tests, validate database schemas, and test dependencies.
4. PR promotes the exact same artifact to staging; measure performance/synthetic traffic.
5. Approved PR updates production; Flux prod reconciles.
6. If using a canary controller, it monitors metrics to shift or halt traffic per policy; otherwise, standard Deployment rolling updates run with Git rollback ready if SLOs breach.
7. Monitor application logs, error rates, latency, Pod restarts, cost, and incidents.

**Traffic draining:** Pod readiness turning false does not automatically ensure every active TCP/gRPC connection has drained cleanly. Tune `terminationGracePeriodSeconds`, `preStop` hooks, keep-alives, and graceful shutdown logic for real workload traffic.

### 18.3. Stateful Workloads Need Dedicated Runbooks

For StatefulSets, databases, or message brokers, rolling updates alone do not guarantee integrity. Require:

- Tested backups and restores.
- Verification of quorum/leader election, replica lag, and storage class/PVC retention.
- Version compatibility analysis between Pods and on-disk data formats.
- Schema/event versioning rules while mixed versions coexist.
- Product-specific failover/rollback commands, not just `git revert`.

Never enable `prune: true` without evaluating StatefulSet/PVC lifecycles and reclaim policies. Recreating a Kubernetes object **does not restore bytes onto a wiped volume**.

## 19. Multi-Cluster, Multi-Subscription GitOps and Recovery

Enterprises often split AKS clusters by environment, region, data sensitivity, or team ownership. GitOps helps enforce uniform standards, yet you should never create a single identity or branch able to mutate every production cluster unchecked.

### 19.1. Multi-Cluster Governance Model

~~~mermaid
flowchart TB
    POLICY[Platform governance / Git CODEOWNERS]
    POLICY --> REPO[(GitOps config repo)]
    REPO --> DEV[Flux: AKS-dev]
    REPO --> STAGE[Flux: AKS-staging]
    REPO --> PROD1[Flux: AKS-prod-region-A]
    REPO --> PROD2[Flux: AKS-prod-region-B]
    DEV --> W1[Dev workloads]
    STAGE --> W2[Staging workloads]
    PROD1 --> W3[Prod workloads A]
    PROD2 --> W4[Prod workloads B]
    MON[Azure Monitor / SLO dashboards] -. Observe .-> PROD1
    MON -. Observe .-> PROD2
~~~

Clusters may sit in different **subscriptions/resource groups** while sharing base manifests, overlays, and policies. Each cluster points to **its exact path/ref**; avoid pointing every production cluster at an ungated mutable branch/path. Isolate **cluster identities** and resource permissions per scope; avoid reusing one unrotated admin account to bootstrap everything.

### 19.2. Bootstrapping from Scratch

Suppose a production AKS cluster must be rebuilt after a catastrophic outage. For GitOps to restore workloads cleanly, you need:

1. IaC capable of recreating AKS, VNets, subnets, identities, ACR connectivity, and monitoring.
2. Reachable Git repositories and secure recovery of bootstrap credentials.
3. Compatible versions of Flux extensions/controllers installed.
4. Kustomizations reconciled **in order**: namespaces/RBAC/CRDs/operators → workloads.
5. Image digests still present in ACR/registries with working pull permissions.
6. External secrets, data, databases, and volumes restored via a separate DR plan.
7. Smoke/contract tests confirming the rebuilt system serves traffic properly.

GitOps **recreates Kubernetes objects**, but **never restores databases, blobs, PersistentVolumes, or off-cluster state**. Backups/restores and DR require dedicated runbooks, RPO/RTO targets, and failover playbooks.

### 19.3. Availability When the Git Provider Is Down

When a Git provider becomes unreachable, running workloads can keep serving as long as the cluster and dependencies remain healthy. However, you may be **unable to deploy changes or rollbacks via GitOps** until the source recovers. Prepare:

- Approved repository mirrors/backups and source-failover runbooks.
- Understanding of controller local artifact/caching behavior, without treating caches as guaranteed backups.
- Scoped, audited break-glass pipelines capable of syncing back to Git afterward.
- Configuration snapshots/backups and registry retention for critical images.

Never let a single unrotated GitHub/ADO PAT become a single point of failure across all production clusters.

## 20. Cost, Performance, and Operational Limits of GitOps

GitOps cuts manual toil, yet **does not eliminate infrastructure costs**. Azure bills resources under standard pricing models, covering AKS/nodes, registries, networking, storage, and observability. Certain extension/GitOps capabilities may also carry differing pricing or entitlement terms depending on cluster type or Azure plan—verify actual environment pricing/entitlements, particularly when managing **Azure Arc-enabled Kubernetes** rather than AKS.

### 20.1. Cost Drivers to Monitor

| Source | Impact | How to Control |
|---|---|---|
| **AKS nodes/compute** | Node pools running apps and Flux controllers, plus reserve machines | Requests/limits, node rightsizing, autoscalers, placement |
| **Azure Container Registry** | Image storage, tier, networking/transactions | Policy-driven image retention while preserving rollback digests |
| **Networking** | NAT Gateways, Azure Firewalls, Private Endpoints, outbound or cross-region traffic | Clean routing, optimize image pulls and egress |
| **Monitoring** | Log Analytics / Container Insights / Prometheus / alerts | Sampling, retention tuning, filtering noisy telemetry |
| **Storage** | PVCs/PVs, snapshots, backups, data replication | Backup lifecycle and data tiering |
| **CI/CD** | Build runners, scanners, artifact signing, Git hosting | Pipeline optimization and controlled caching |
| **Kubernetes operations** | API server load, overly frequent Flux reconciles, CRD count | Tune intervals, split Kustomizations, right-size controller resources |

Component pricing varies by region, SKU, time, and subscription terms. Monitor **Azure Cost Management**, enforce `owner`/`application`/`environment`/`costCenter` tags, set budgets, and track real spend trends. **Budget alerts do not automatically stop charges from accruing.**

### 20.2. Optimizing Reconciliation

Instead of one monolithic Kustomization managing every namespace and thousands of resources:

- Split by team/app or platform layer with clear boundaries.
- Use `dependsOn` only where ordering matters so unrelated apps do not block each other.
- Pick realistic intervals matched to change frequency, operational sensitivity, and Git/API rate limits.
- Define lightweight, useful health checks rather than hammering heavy diagnostic endpoints.
- Monitor controller CPU/memory, work queues, error rates, and Git provider limits.
- Keep manifests/configs readable and tested to reduce failed builds/applies.

Do not set `interval: 10s` on every repository solely to shave seconds off deployment lead time. Use webhook receivers and on-demand reconciliation where appropriate while evaluating load and security.

### 20.3. Upgrading the Flux Extension and CRDs

Flux controllers are operational software with their own versions and compatibility matrices. When upgrading:

1. Check AKS/Kubernetes version, GitOps extension version, and active CRD API versions.
2. Read breaking changes and custom resource deprecation/migration guides.
3. Validate on a test cluster with matching GitOps configs, testing Kustomizations and `HelmReleases`.
4. Back up manifests/configs and record pre-upgrade extension and controller versions.
5. Upgrade inside a change window while watching controller health, reconciliation errors, and app SLOs.
6. Prepare a compatibility recovery plan without assuming controller/CRD downgrades are always safe.

Do not confuse **upgrading AKS control plane/node pools** with **Flux reconciling workload manifests**. AKS upgrades, node image updates, Kubernetes API deprecations, and GitOps extension upgrades are related changes needing separate schedules and verification. If YAML uses a removed Kubernetes API version, Flux can start failing immediately after a cluster upgrade even when Git hasn't changed.

## 21. Real-World Scenario: Operating an Order Platform on AKS

**Context:** an enterprise operates two subscriptions (`app-dev` and `app-production`), two AKS clusters per environment, and one private ACR. The ordering platform includes a web API, workers reading Azure Service Bus messages, Azure SQL over Private Endpoint, and Azure Key Vault. Operations wants to move from laptop deployments to GitOps with production requirements:

- Every change requires a PR, reviewer, and recorded image digest.
- No database passwords or tokens stored in Git.
- Faulty releases can revert cleanly to a vetted image without corrupting data.
- One team cannot delete another team's resources.
- Clear drift/reconciliation visibility and alerting with accountable owners.
- Documented DR plans if the Git provider or an Azure region goes down.

### 21.1. Reference Architecture

~~~mermaid
flowchart LR
    DEV[Source PR] --> CI[CI build + test + scan]
    CI --> ACR[Private ACR: image digest]
    CI --> PR[Config PR - overlay]
    PR --> REVIEW[CODEOWNERS + policy checks]
    REVIEW -->|Merge| REPO[(Protected Git config repo)]
    REPO --> FLUXDEV[Flux controllers AKS dev]
    REPO --> FLUXPROD[Flux controllers AKS prod]
    FLUXDEV --> DEVAPP[Dev namespaces]
    FLUXPROD --> PRODAPP[Prod namespaces]
    PRODAPP --> SQL[Azure SQL private endpoint]
    PRODAPP --> BUS[Azure Service Bus]
    PRODAPP --> KV[Azure Key Vault]
    ACR -. Kubelet image pull .-> PRODAPP
    MON[Azure Monitor + App Insights] -. Observe .-> PRODAPP
~~~

### 21.2. Separation of Responsibilities

| Role | Responsibilities | Target Permissions |
|---|---|---|
| **Platform team** | AKS/IaC, Flux extension, CRDs, RBAC, namespaces, monitoring | Platform administration; audit and change approvals |
| **Application team** | Code, Dockerfiles, app manifests, tests, and image proposals | Commit/PR to app repos; no production `cluster-admin` |
| **Security team** | Policies, scans, secrets, RBAC reviews, and CVE SLOs | Approve rules/exceptions per governance |
| **Release owner** | Review config PRs, approve promotions/rollbacks | Protected merge rights, SLO oversight |
| **On-call/SRE** | Monitor health, incidents, break-glass intervention when needed | Time-bound audited emergency access |

### 21.3. Releasing Version 1.4.2

1. Developer updates API code; CI builds `orders-api:1.4.2`, scans it, and records digest `D2`.
2. Team opens a PR updating `apps/orders-api/overlays/dev` to digest `D2`.
3. Dev Flux reconciles; smoke tests, contract tests, and SQL/Service Bus integration tests pass.
4. Release owner opens a PR updating the production overlay to the exact same `D2`, never rebuilding an unverified separate production image.
5. Reviewers verify no plaintext secrets, strict namespace scope, `prune` will not delete Services/PVCs accidentally, and schemas remain compatible.
6. PR merges; prod Flux fetches the commit, Kustomization applies, and Kubernetes executes a rolling update.
7. SREs watch observed revision, Pod readiness, HTTP 5xx, p95 latency, SQL/Service Bus dependency errors, and business metrics.
8. If errors breach SLOs, open an approved revert PR returning the image to digest `D1`; verify data, queues, and in-flight jobs.
9. Archive release/incident evidence, add regression tests, and update baselines for the next cycle.

### 21.4. When `prune` Deletes the Wrong Service

Suppose a PR accidentally removes the Service from base resources and Flux prunes it. Pods stay Running yet users cannot reach the API because the Service is gone. Follow the runbook:

1. Halt promotions and identify the commit that dropped the resource.
2. Inspect Kustomization inventory/conditions, Git diff, and Kubernetes events; check whether any other resources were pruned.
3. Revert the Service manifest back to desired state via an approved emergency PR.
4. Watch Flux recreate the Service and endpoints; verify ingress, HTTP health, and transactions.
5. Assess data impact, networking, outage duration, and preventive policy checks (e.g., CI diffs flagging resource deletions).

If the pruned resource was a PVC or stateful object, restoring YAML **does not prove the underlying data survived**. Execute storage backup/restore procedures.

### 21.5. When an Azure SQL Migration Breaks the Previous Version

A new version alters columns/data formats in a way the old version cannot read. Reverting the image to `D1` leaves the API failing. Prevention pattern:

- **Expand:** add new schema structures compatible with the old code.
- **Migrate:** backfill data via controlled, checkpointed, verified jobs.
- **Dual-read/write or adapter:** while mixed code versions coexist per application policy.
- **Contract:** drop old schema only after the rollback window closes and DR is ready.

Never run destructive migrations inside every Pod's init container: new Pods can trigger migrations repeatedly across Kubernetes reschedules and Flux reconciliations.

## 22. Hands-On Exercise: Building GitOps for an AKS API

**Prompt:** you have a lab AKS cluster, a private ACR, and a Git repository you control. Application `inventory-api` runs in namespace `inventory` with endpoint `/health/ready`; stable version is `1.0.0`, new version is `1.1.0`. Deploy via Flux and prove you can roll back cleanly after observing a business-logic bug.

Complete the following:

1. **Diagram:** draw the flow CI build → ACR → Git PR → Flux controllers → Kubernetes API → Deployment/Pods.
2. **Distinguish:** what roles do GitOps `GitRepository`, Flux `Kustomization`, `kustomization.yaml`, `HelmRelease`, `Deployment`, and `replicas` each play?
3. **Repository:** create a base/overlay dev/prod layout with namespace, Deployment, Service, image tag/digest, and resource requests/limits.
4. **Source security:** describe how Flux reads private Git without committing PATs or SSH private keys to the repo.
5. **Azure:** list prerequisites before creating an extension/configuration on AKS and the Azure RBAC permissions involved.
6. **CLI:** write commands to create/verify the Flux extension, create a configuration pointing to the test overlay, and read source/Kustomization status.
7. **Kubernetes:** prove Pods run the expected image, Services target the right port, readiness probes pass, and clients can call the API.
8. **Promotion:** describe promoting the exact image digest from dev to production via PR/approval.
9. **Drift:** walk through manually scaling replicas and explain how Flux/HPA/field ownership affect drift correction.
10. **Prune:** illustrate removing a manifest from an overlay; explain when `prune=true` becomes dangerous and what safeguards to build.
11. **Helm:** if deploying an ingress controller from a chart, choose `HelmRelease` and a Helm chart source, listing CRD/permission prerequisites.
12. **Secrets:** design Key Vault + Workload Identity or SOPS safely; never treat plaintext/Base64 Secrets as encryption.
13. **Image pull:** when `GitRepository` is Ready yet Pods show `ImagePullBackOff`, identify which identities and network paths to inspect.
14. **Observability:** list at least six metrics/logs to collect, linking Git SHA to image digest and application health.
15. **Rollback:** explain why `kubectl rollout undo` is insufficient; write the Git revert sequence and post-revert verification steps.
16. **DR:** describe recovering workloads if the Git provider goes down and if the AKS cluster must be rebuilt.
17. **Cost:** estimate AKS/Flux compute, ACR, networking, Log Analytics, backups, and how to set budgets.
18. **Evidence:** capture commit, PR reviewer, observed revision, Deployment image, synthetic test results, and incident/runbook notes.

### Sample Post-Merge Verification Commands

~~~bash
# Run only against a lab cluster with verified kubeconfig context.
kubectl config current-context
kubectl get gitrepositories.source.toolkit.fluxcd.io -A
kubectl get kustomizations.kustomize.toolkit.fluxcd.io -A
kubectl -n inventory get deploy,pods,svc

# Track live Deployment rollout instead of treating a Git commit as success.
kubectl -n inventory rollout status \
  deployment/inventory-api --timeout=180s
~~~

### Verification Evidence Matrix

| Target | Required Evidence |
|---|---|
| Git repository | Branch/commit and peer-reviewed PR |
| Flux source | `GitRepository` Ready, artifact revision matches intended commit |
| Flux Kustomization | Ready, valid `sourceRef`/`path`, clear `prune`/health policy |
| Kubernetes Deployment | Image digest, replicas/rollout conditions, correct namespace |
| Pods | Running/Ready, no abnormal image pull/crash/restart loops |
| Application | Health endpoint and real API transactions succeed |
| Security | Git/ACR/Kubernetes/Key Vault permissions separated, zero leaked secrets |
| Rollback | Revert commit applied, prior image working, data compatible |
| FinOps | Clear owner, tags, budgets, and sensible log retention |

The exercise passes when the learner proves **which commit Flux observed, which objects were applied, whether the app is genuinely healthy, and how to recover from a bad release**—not merely screenshotting "Flux extension provisioning succeeded."

## 23. Production GitOps Operations Checklist

### 23.1. Before Installing Flux or Onboarding a New Cluster

- [ ] Confirmed subscription, resource group, AKS cluster, region, and `kubectl` context.
- [ ] Chosen one primary Flux installation/management method so two systems do not fight over CRDs/extensions.
- [ ] Verified compatibility across AKS/Kubernetes version and Flux extension/controllers/CRDs.
- [ ] Designed repository layout by cluster/environment/team with explicit path ownership.
- [ ] Enabled Git branch protection, PR reviews, `CODEOWNERS`, and IaC/Kubernetes manifest checks.
- [ ] Verified network/DNS paths to Git repositories, ACR, Azure services, and private endpoints.
- [ ] Provisioned read-only Git source credentials with rotation and secure secret storage.
- [ ] Scoped Azure RBAC and Kubernetes RBAC; configured scoped service accounts for Flux Kustomizations.
- [ ] Defined `prune`/deletion policies, protected stateful resources, and ownership transfer procedures.
- [ ] Configured monitoring for Flux, AKS, app telemetry, and alert owners.
- [ ] Established backup/DR plans independent of the Git repository, covering data and image registries.

### 23.2. Before Merging a Production PR

- [ ] Reviewed Git diff, YAML schemas, and `kustomize build` / Helm chart values.
- [ ] Verified Kubernetes API versions match the target AKS version.
- [ ] Image comes from a trusted registry, is scanned, and uses a reproducible tag/digest.
- [ ] Zero plaintext Secrets, PATs, private keys, or credentials committed.
- [ ] PR adds no unauthorized RBAC, public ingress, or overly broad network rules.
- [ ] No unintended deletions or renames when `prune=true`.
- [ ] Database migrations, message schemas, and image rollbacks are compatible.
- [ ] Sufficient Pod capacity, sensible readiness/startup/liveness probes, and rollout strategy.
- [ ] Change approval/owner recorded and lower-environment tests passed.
- [ ] Rollback commit/image ready, plus recovery plan if repo/registry goes unreachable.

### 23.3. After Merging

- [ ] Confirmed `GitRepository` observed the target commit.
- [ ] Confirmed `Kustomization`/`HelmRelease` reconciled the expected source/path/values.
- [ ] Checked Kubernetes resource inventory for zero unexpected prunes/deletions.
- [ ] Deployment rollout succeeded, Pods Ready, zero Pending/CrashLoop/`ImagePullBackOff`.
- [ ] Verified HTTP/API calls, databases, queues, secrets, identities, and networking.
- [ ] Monitored post-release p95/p99 latency, error rates, and resource metrics.
- [ ] If errors arise, paused promotions, executed Git-based rollback, and assessed data integrity.
- [ ] Recorded commit SHA, PR, image digest, observed revision, test results, and incidents in governance logs.

## 24. Common Misconceptions and Corrections

| Misconception | Reality to Remember |
|---|---|
| "Having a Git repo means we're doing GitOps." | Requires controller reconciliation, scoped permissions, review gates, and observability |
| "Flux replaces CI." | Flux primarily reconciles desired state; CI still builds, tests, and scans images |
| "Flux extension installed cleanly, so the app is healthy." | Extension, config, source, Deployment, and app are separate verification layers |
| "If `GitRepository` is Ready, image pulls will definitely work." | Git auth is separate from ACR kubelet identity and Pod runtime pulls |
| "`kustomization.yaml` is the same thing as a Flux `Kustomization`." | Kustomize files build manifests; the Flux CRD configures source/path/prune/health |
| "Replicas always snap back to Git, even with HPA." | HPA and Flux can contend over fields; design field ownership explicitly |
| "`prune` just cleans up unused files." | Can delete Services, CRDs, PVCs, or critical resources within its inventory |
| "`git revert` restores the entire system." | Does not automatically undo database schemas, deleted data, queues, or external side effects |
| "`kubectl rollout undo` is a durable rollback." | Flux will reconcile the broken image back if Git still declares it |
| "GitOps automatically splits canary 5% traffic." | Requires a dedicated rollout controller/ingress with weighted routing; Flux does not split HTTP traffic itself |
| "Base64 Kubernetes Secrets are safe to commit." | Base64 is encoding, not encryption; use SOPS, Key Vault, or proper secret management |
| "Flux creates all Azure resources automatically." | VNets, AKS, ACR, and data services are typically managed by separate IaC |
| "One `cluster-admin` service account for all teams is simplest." | Maximizes blast radius if a single repo or credential is compromised |
| "Three replicas guarantee safety on every deploy." | Also depends on zones, readiness, capacity, databases, and rollout behavior |
| "If `source-controller` goes offline, apps stop immediately." | Running workloads can continue serving; what breaks is syncing new changes |

## 25. Lab Cleanup and Protecting Resource Ownership

After finishing the lab, if you created Flux configurations/extensions on a test cluster, verify **who owns** each resource before deleting anything. Never delete a shared Flux extension just to clean up one app, as that halts reconciliation across multiple teams.

### 25.1. Inventory Before Acting

~~~bash
az account show --query "{id:id,name:name}" -o table

az aks show \
  --resource-group "$RG" \
  --name "$AKS" \
  --query "{id:id,provisioningState:provisioningState}" \
  -o json

az k8s-configuration flux show \
  --resource-group "$RG" \
  --cluster-name "$AKS" \
  --cluster-type managedClusters \
  --name "$CONFIG_NAME" \
  -o json

kubectl get gitrepositories.source.toolkit.fluxcd.io -A
kubectl get kustomizations.kustomize.toolkit.fluxcd.io -A
kubectl get namespaces
~~~

Only **read** existing resources in this step. If the cluster holds multiple Flux configurations, review all ownership and controllers before considering deleting the extension.

### 25.2. Cleanup Decisions

1. **Never delete production configs** just because the lab ended: separate lab vs shared platform resources.
2. Check `prune` status and resource inventory before deleting or transferring ownership of a Flux Kustomization.
3. For stateful Kubernetes resources, check PersistentVolumes/PVCs, reclaim policies, backups, and manifest-deletion impact.
4. In ACR, retain image digests needed for rollback/DR; clean up only under approved policies and owners.
5. Only consider removing configurations/extensions in service-supported order per SOP when no workloads on the lab cluster still need Flux.
6. Even if a resource group belongs entirely to the lab, inventory all VMs, AKS, ACR, Storage, and logs before deleting; never delete a group holding shared resources.
7. Check resources still accruing spend: AKS nodes, load balancers/public IPs, NAT/Firewalls, ACR, backups, and Log Analytics.

**No bulk deletion commands are included here**, since impact can reach beyond a single exercise. When cleaning up, operate only on disposable clusters/resource groups verified via operational documentation—not copy-pasted commands.

## 26. Key Takeaways

**GitOps for AKS with Flux** puts **Kubernetes desired state in Git and continuously reconciles live state via controllers**. This gives operations teams clear change history, drift correction, separation of deployment privileges from CI, and auditable rollbacks.

Core takeaways:

1. **CI produces artifacts, Flux reconciles desired state:** images are built/scanned and stored in ACR; Git declares images/versions/configs; Flux reconciles via the Kubernetes API.
2. **Flux uses specialized controllers:** `source-controller` fetches sources, `kustomize-controller` and `helm-controller` deploy; image automation is optional and needs separate privileges.
3. **Distinguish Kustomization types:** the Flux CRD configures source/path/prune/health; Kustomize `kustomization.yaml` assembles base/overlay Kubernetes manifests.
4. **Verify across layers:** Azure Flux configuration/extension, Git source, Kustomization/HelmRelease, Pods, and **real application health**.
5. **Secure Git and permissions:** branch protections, reviews, Azure RBAC, Kubernetes RBAC, least-privilege credentials, Key Vault/SOPS/Workload Identity, and artifact provenance.
6. **Mind `prune` and drift:** resources removed from Git can be pruned; manual cluster edits can be overwritten by Flux, so drive desired state through Git.
7. **Durable rollback via Git revert/PRs:** not `kubectl rollout undo` alone; preserve old image digests, backward-compatible schemas, and data/DR plans.
8. **GitOps does not do everything automatically:** AKS upgrades, CI builds, canary traffic splitting, database restores, CVE remediation, and business monitoring require complementary tools and processes.
9. **Operations and FinOps:** pick sensible reconciliation intervals, split ownership, watch source failures/reconciliation lag, and track compute, registry, log, and network costs.

A strong GitOps setup is about more than `Ready=True`. It must answer **which commit was approved, what Flux applied, whether the workload is genuinely healthy, who owns drift, and how the team recovers when a release fails**.
