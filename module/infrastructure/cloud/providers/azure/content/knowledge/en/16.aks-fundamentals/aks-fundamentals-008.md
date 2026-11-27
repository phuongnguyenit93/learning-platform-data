# Connecting AKS with Azure Container Registry

In a system deployed on Microsoft Azure, containerized applications are typically built from source code, packaged into images, stored in a registry, and deployed onto **Azure Kubernetes Service (AKS)**. When images reside in a private **Azure Container Registry (ACR)**, the cluster must have the right authentication mechanism and network path so Kubernetes nodes can pull images. Otherwise, Kubernetes may accept the Deployment while Pods stay stuck in **ErrImagePull** or **ImagePullBackOff**.

**Connecting AKS with ACR** is more than running `docker login`. It requires coordinating **Azure identity**, **Azure RBAC or repository permissions**, **kubelet**, **registry**, **network/DNS**, and **Kubernetes deployments**. Granting permissions to the control plane instead of kubelet, misconfiguring private endpoint DNS, or mistyping an image name can all prevent workloads from starting.

This lesson belongs to the **Azure Kubernetes Service Fundamentals** chapter in the **CLOUD_PROVIDERS_AZURE** module, where learners build Azure architectures from subscriptions, resource groups, and Microsoft Entra ID through networking, compute, storage, security, observability, and cost control. We will design and practice the flow **build image → push to ACR → grant AKS permissions → deploy Pod → verify image pull**, then walk through production scenarios.

> **Key takeaway:** **Image pull** permissions normally belong to the **AKS kubelet identity** or the cluster's configured image-pull mechanism, **not** the runtime identity of the running Java/Node.js container. In most AKS models using managed identity with ACR in traditional RBAC registry mode, **`az aks --attach-acr`** grants `AcrPull` to the kubelet identity. When ACR enables **RBAC Registry + ABAC Repository Permissions**, a different permission path is required; do not treat `attach-acr` as universally applicable.

## 1. Learning objectives

After this lesson, you can:

1. Explain the roles of ACR, AKS, nodes, kubelet, Pods, and container images in the deployment workflow.
2. Distinguish **image push** permissions for CI/CD from **image pull** permissions for AKS nodes.
3. Understand **control plane identity**, **kubelet identity**, **workload identity**, and why they do not replace one another.
4. Choose the right connection approach for **ACR RBAC Registry Permissions** vs. **ACR RBAC Registry + ABAC Repository Permissions**.
5. Use Azure CLI to inspect configs, attach ACR to AKS, or assign permissions to the kubelet identity per supported model.
6. Build/push a test image with **az acr build** and deploy a Kubernetes Deployment referencing a private registry.
7. Inspect Pod events, rollouts, node image pulls, and troubleshoot **401/403/404**, DNS, or network timeouts.
8. Design ACR private endpoints, DNS, egress, and permissions across different subscriptions or resource groups.
9. Govern image tags/digests, supply chain security, CI/CD, rotation, and rollbacks.
10. Review registry, build, networking, AKS node, and observability costs, and build a production checklist.

## 2. ACR's place in AKS architecture

**Azure Container Registry (ACR)** is Azure's managed registry service storing OCI/Docker images and supported artifacts. **AKS** orchestrates containers across Kubernetes nodes. When a Pod specifies a private image, the node must fetch manifests and layers from the registry to launch containers.

~~~mermaid
flowchart LR
    DEV["Source code"] --> CI["Build/test/scan"]
    CI -->|"Push"| ACR["Azure Container Registry<br/>myregistry.azurecr.io"]
    AKS["AKS control plane"] -->|"Schedules Pod"| NODE["AKS node + kubelet"]
    NODE -->|"Pulls image via identity & network"| ACR
    NODE --> POD["Pod running container"]
    POD --> DATA["Azure SQL / Storage / Key Vault"]
~~~

Key points in the diagram:

- **CI/CD** needs **push** (and typically read) permissions on ACR.
- **Kubelet on each node** needs **pull** permissions from ACR to start Pods.
- **Applications inside Pods** need separate permissions to access Storage, Key Vault, databases, or other services if required.
- Pull permission does not grant push, repository deletion, registry network rule edits, or application data access.

Never conclude that a successful **`docker login`** on a developer laptop proves AKS nodes can pull images. The two environments have different identities, networks, and DNS.

### 2.1. Common components involved

| Component | Purpose | Example |
|---|---|---|
| Subscription/resource group | Management, permission, and billing boundary | `rg-aks-lab`, `rg-acr-lab` |
| ACR registry | Stores images/OCI artifacts | `acrordersdemo123` |
| Login server | Endpoint used in image references | `acrordersdemo123.azurecr.io` |
| Repository | Groups images by name | `orders-api` |
| Tag/digest | Identifies image content version | `orders-api:1.0.0` or sha256 digest |
| AKS cluster | Manages Kubernetes workloads | `aks-orders-lab` |
| Node pool and kubelet | Runs Pods and pulls images | Linux agent pool |
| Kubernetes Deployment | Declares desired Pod count and container image | `orders-api` |
| Kubernetes Service | Endpoint to Pods once started | ClusterIP for lab |
| Azure identity/RBAC | Authenticates and authorizes with ACR | Kubelet identity + `AcrPull` |
| Network/DNS | Path to ACR login/data endpoints | Public egress or Private Endpoint |

### 2.2. Exact image naming

An ACR image reference has the form:

~~~text
<registry-name>.azurecr.io/<repository>:<tag>

Example:
acrordersdemo123.azurecr.io/aks-pull-demo:1.0.0
~~~

In production, images can be referenced by digest:

~~~text
acrordersdemo123.azurecr.io/aks-pull-demo@sha256:<actual-digest>
~~~

The registry hostname is part of the image reference. **myregistry** is not the same as **myregistry.azurecr.io**; tag **1.0.0** differs from **1.0** and **latest**. Kubernetes will not automatically locate an image in a private registry if you specify only the repository name without the registry hostname.

## 3. Distinguishing identity types and permissions

This is what determines whether AKS can pull images.

### 3.1. Control plane identity

AKS uses its **control plane identity** to manage Azure resources needed for cluster operations per configuration, such as load balancers or network resources. On managed-identity clusters, the **identity** field on the AKS resource reflects part of this identity information.

**Do not assume** granting `AcrPull` to the control plane identity suffices for kubelet to pull images.

### 3.2. Kubelet identity

The **kubelet identity** is used by AKS for node-level operations, notably authenticating to **pull images from ACR** in common managed identity setups.

Details typically appear under:

~~~text
AKS identityProfile.kubeletidentity
    ├── clientId
    ├── objectId
    └── resourceId
~~~

The kubelet identity may be AKS-managed or a pre-configured user-assigned managed identity. When assigning a role to a principal, pass the right **object ID/principal ID** required by the API/CLI—never mix up **client ID**, resource ID, and object ID.

### 3.3. Pod Workload Identity

**Microsoft Entra Workload ID for AKS** lets applications inside Pods acquire Azure permissions via a federated Kubernetes service account. It is designed for application calls to Blob Storage, Key Vault, and similar services.

However, at **image pull time**, the Pod is not running yet, so initial image-pull authentication cannot rely on a token the app would receive after startup. **Workload Identity does not replace kubelet identity for image pulling.**

### 3.4. CI/CD identity

Build/push pipelines need their own identity scoped to **push** only to approved registries or repositories.

Never reuse a CI/CD account's broad **Owner/Contributor** subscription privileges for AKS nodes. Separation of duties limits impact if a pipeline or workload is compromised.

### 3.5. Common registry roles

| Role/permission | Used for | Notes |
|---|---|---|
| **AcrPull** | AKS kubelet reading/pulling images from ACR in standard RBAC registry mode | Does not permit pushing images |
| **AcrPush** | Pipelines/teams pushing images in supported RBAC registry mode | Broader than pull; do not grant to kubelet just to deploy |
| **Container Registry Repository Reader** | Reading/pulling repositories in ACR **RBAC Registry + ABAC Repository Permissions** mode | Can pair with ABAC conditions to scope repositories per config |
| **Container Registry Repository Writer** or matching role | Managing repository contents in supported ABAC mode | Pick permissions matching actual push/metadata needs |
| **Owner/User Access Administrator/Role Based Access Control Administrator** | Managing role assignments by scope and conditions | Never grant to kubelet for image pulling |

Exact role lists vary by ACR mode and service updates. **AcrPull** and **Container Registry Repository Reader** are not interchangeable across all permission modes.

## 4. Choosing the ACR permission model before using attach-acr

ACR supports multiple permission control models. Two common configurations:

### 4.1. RBAC Registry Permissions

This is the traditional registry-level RBAC model. You assign the **AcrPull** role at the ACR scope to the kubelet identity.

For eligible AKS and ACR setups, Azure CLI supports:

~~~bash
# When creating a new AKS cluster (flag illustration)
az aks create ... --attach-acr <acr-name-or-resource-id>

# For an existing AKS cluster
az aks update ... --attach-acr <acr-name-or-resource-id>
~~~

Full commands appear in the hands-on sections. Here, **attach-acr** configures the required role assignment; it does not copy images into the cluster or create Kubernetes Deployments.

### 4.2. RBAC Registry + ABAC Repository Permissions

With ACR using **RBAC Registry + ABAC Repository Permissions**, administrators may need to assign **Container Registry Repository Reader** to the pulling principal, paired with ABAC repository conditions when scoping access.

**Do not rely on `az aks --attach-acr` in this mode**: the `attach-acr` integration does not assign ABAC repository roles the way the registry requires. Instead, look up the kubelet identity and assign the right Azure RBAC role with exact scope/conditions.

A registry shared across multiple teams' repositories can use ABAC conditions to prevent one kubelet identity from reading every image. Verify repository-scoping rules and condition evaluation syntax in current IAM/ACR documentation.

### 4.3. Decision rule

~~~mermaid
flowchart TD
    A["AKS needs to pull private ACR"] --> B{"ACR permission mode?"}
    B -->|"RBAC Registry Permissions"| C["Attach ACR or assign AcrPull<br/>to kubelet identity"]
    B -->|"RBAC Registry + ABAC Repository Permissions"| D["Assign Container Registry Repository Reader<br/>and ABAC condition as needed"]
    C --> E["Verify role assignment"]
    D --> E
    E --> F["Verify DNS and node → registry network path"]
    F --> G["Deploy Pod, inspect Events and image pull"]
~~~

Never try to work around ABAC errors by enabling the **ACR admin user** or assigning subscription-wide **Contributor**. Fix the right role and right principal first.

## 5. Prerequisites for the hands-on lab

The walkthrough uses:

| Item | Illustrative name |
|---|---|
| Subscription | Approved lab subscription |
| Region | `southeastasia` |
| ACR resource group | `rg-acr-lab` |
| AKS resource group | `rg-aks-lab` |
| ACR name | `acrordersdemo123` *(must be globally unique)* |
| AKS cluster | `aks-orders-lab` |
| Repository | `aks-pull-demo` |
| Image tag | `1.0.0` |
| Kubernetes namespace | `acr-pull-lab` |
| Deployment | `aks-pull-demo` |
| Service | `aks-pull-demo` (ClusterIP) |

These names are **examples**. Before running resource creation commands:

1. Ensure management rights on the right subscription/resource groups and permission to create role assignments when needed. **Network Contributor** or standard **Contributor** does not automatically grant permission to create role assignments.
2. Check whether the ACR and AKS resources already exist to avoid overwriting production resources.
3. Verify the ACR's **permission mode**: traditional vs. ABAC repository.
4. Confirm same-tenant setup or an approved cross-tenant auth plan; the attach/role assignment examples assume **the same Microsoft Entra tenant**.
5. Check AKS node/VM quotas, VNet addresses, kubeconfig, and organizational network policies.
6. Confirm whether ACR uses a public endpoint or Private Link, and whether AKS can reach both login server and data endpoints.
7. Have Azure CLI, **kubectl**, and an image build tool such as Docker or **az acr build** per permissions.
8. Ensure budget and cleanup plans; AKS nodes and ACR continue incurring charges even when no application Pods are running.

**Do not** create a new cluster if an approved AKS lab cluster already exists. Prefer authorized shared lab resources over spinning up a second cluster just to test image pulling.

## 6. Step A: create ACR or verify an existing registry

Bash examples in Azure Cloud Shell or a shell with Azure CLI:

~~~bash
az login
az account set --subscription "<subscription-id>"
az account show --output table

ACR_RG="rg-acr-lab"
REGION="southeastasia"
ACR_NAME="<globally-unique-acr-name>"

az group create \
  --name "$ACR_RG" \
  --location "$REGION"

az acr create \
  --resource-group "$ACR_RG" \
  --name "$ACR_NAME" \
  --sku Basic \
  --location "$REGION" \
  --admin-enabled false
~~~

If the registry already exists, **do not run `az acr create`**; use the read commands below instead. The ACR name must be valid and globally unique within the ACR namespace, generally using alphanumeric characters per service constraints.

### 6.1. Read registry ID and login server

~~~bash
ACR_ID=$(az acr show \
  --name "$ACR_NAME" \
  --resource-group "$ACR_RG" \
  --query id --output tsv)

LOGIN_SERVER=$(az acr show \
  --name "$ACR_NAME" \
  --resource-group "$ACR_RG" \
  --query loginServer --output tsv)

printf "ACR_ID=%s\nLOGIN_SERVER=%s\n" "$ACR_ID" "$LOGIN_SERVER"
~~~

Expected output looks like:

~~~text
ACR_ID=/subscriptions/<id>/resourceGroups/rg-acr-lab/providers/Microsoft.ContainerRegistry/registries/acrordersdemo123
LOGIN_SERVER=acrordersdemo123.azurecr.io
~~~

Confirm variables are non-empty and point to the right registry. If ACR lives in another subscription, fetch the **resource ID** under that authorized subscription/tenant rather than assuming matching names or the current subscription.

### 6.2. Determine permission mode

Check in **Azure Portal → Container registries → registry → Access control (IAM) / Properties** or the **role assignment permissions mode** configuration shown in the current Portal UI.

With Azure CLI/API, inspect the registry JSON and look at **roleAssignmentMode** where supported by the API and CLI version:

~~~bash
az acr show \
  --name "$ACR_NAME" \
  --resource-group "$ACR_RG" \
  --output json
~~~

Field names and visibility depend on API version and UI. **Do not infer permission mode from the Basic/Standard/Premium SKU**: SKU tier and permission mode are separate decisions.

## 7. Step B: verify or create the AKS cluster

### 7.1. If AKS already exists

~~~bash
AKS_RG="rg-aks-lab"
AKS_NAME="aks-orders-lab"

az aks show \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --query "{name:name,location:location,provisioningState:provisioningState,identity:identity,kubeletIdentity:identityProfile.kubeletidentity}" \
  --output json
~~~

Inspect:

- The cluster is in a healthy active state.
- Whether the identity model is **managed identity** or another mechanism.
- Which **kubeletidentity** is present and its IDs.
- Whether the cluster is in the right subscription/tenant and region.
- Whether node pools have Ready nodes to pull images.

Never save secrets from management outputs into repositories. Non-secret identity/metadata fields can be documented in runbooks appropriately.

### 7.2. If you need a new lab AKS cluster

**This operation can incur charges for AKS/node VMs, disks, networking, and logs.** Run only in an approved environment after verifying quotas and SKU/feature support.

~~~bash
az group create \
  --name "$AKS_RG" \
  --location "$REGION"

az aks create \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --location "$REGION" \
  --node-count 1 \
  --node-vm-size Standard_B2s \
  --enable-managed-identity \
  --generate-ssh-keys
~~~

This command illustrates a small Linux cluster using managed identity. Node VM SKU support, quotas, default Kubernetes version, and networking defaults vary by region and subscription. Some environments require custom VNets, Azure Policy, specific network plugins, private clusters, or specific SKUs/tiers; do not treat this minimal creation example as a production blueprint.

**Do not** create a new cluster if an eligible lab cluster already exists.

### 7.3. Read the right kubelet identity

~~~bash
KUBELET_OBJECT_ID=$(az aks show \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --query "identityProfile.kubeletidentity.objectId" \
  --output tsv)

KUBELET_CLIENT_ID=$(az aks show \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --query "identityProfile.kubeletidentity.clientId" \
  --output tsv)

printf "Kubelet objectId: %s\n" "$KUBELET_OBJECT_ID"
printf "Kubelet clientId: %s\n" "$KUBELET_CLIENT_ID"
~~~

If the object ID is empty or the cluster uses a legacy **service principal**, **stop the illustrative role assignment and identify the exact principal used for image pulls**. Never assign roles to random identities that merely "look related."

When replacing node pools/identities or recreating a cluster, verify role assignments still target the active principal.

## 8. Step C1: attach ACR to AKS in RBAC registry mode

**Applies to ACR using RBAC Registry Permissions and AKS compatible with `attach-acr`.** For new clusters, pass **`--attach-acr`** during creation; for existing clusters, use `update`.

### 8.1. Attach to an existing AKS cluster

~~~bash
az aks update \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --attach-acr "$ACR_ID"
~~~

The **`--attach-acr`** flag accepts a registry name or resource ID where supported; passing **`ACR_ID`** avoids targeting the wrong registry across resource groups or subscriptions.

**What does this operation do?**

- Targets the specified registry.
- Configures/assigns the **AcrPull** role to the appropriate AKS principal—typically the **kubelet identity** on managed-identity clusters.
- Enables nodes to authenticate and pull images from the private registry.

**What does this operation NOT do?**

- Does not build or push images.
- Does not create Kubernetes Deployments or Pods.
- Does not grant push permissions to CI/CD.
- Does not open firewalls, configure private endpoints, or fix DNS.
- Does not allow in-Pod apps to read Blob Storage or Key Vault.
- Does not guarantee pulls succeed immediately if the role has not propagated or networking cannot reach ACR.

### 8.2. Attach at cluster creation time

For a new lab and traditional RBAC registry ACR:

~~~bash
az aks create \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --location "$REGION" \
  --node-count 1 \
  --node-vm-size Standard_B2s \
  --enable-managed-identity \
  --generate-ssh-keys \
  --attach-acr "$ACR_ID"
~~~

**Use only one of the two cluster paths:** if the cluster already exists, run **`az aks update`**, not **`az aks create`** again. If using ACR ABAC repository mode, jump to Step C2 below.

### 8.3. Assigning AcrPull manually without attach-acr

When your organization manages role assignments directly:

~~~bash
az role assignment create \
  --assignee-object-id "$KUBELET_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "AcrPull" \
  --scope "$ACR_ID"
~~~

Conditions:

- Kubelet identity is the cluster's active managed identity or service principal.
- The operator has permission to **create role assignments** at the ACR scope.
- Principal and registry belong to a supported tenant/permission model.
- The registry uses a permission mode compatible with **AcrPull**.

Never assign `AcrPull` across the whole subscription when only one registry is needed. Role propagation can take a short while; if a Pod was created before propagation finished, inspect Events and allow kubelet to retry instead of escalating privileges.

### 8.4. Verify role assignment

~~~bash
az role assignment list \
  --assignee "$KUBELET_OBJECT_ID" \
  --scope "$ACR_ID" \
  --include-inherited \
  --output table
~~~

If you lack IAM read permissions, output may be incomplete. Distinguish **role not visible due to missing IAM read permission** from **role does not exist**. Always check using the real principal/object ID.

## 9. Step C2: ACR with ABAC repository permissions

**This is an alternative branch to C1, not an extra step for every registry.**

If the registry selects **RBAC Registry + ABAC Repository Permissions**, the administrator must grant **Container Registry Repository Reader** to the kubelet identity per ACR permission mode.

### 9.1. Assign Reader at ACR scope

Illustrative registry-scoped example:

~~~bash
az role assignment create \
  --assignee-object-id "$KUBELET_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Container Registry Repository Reader" \
  --scope "$ACR_ID"
~~~

Run this only after confirming the registry is truly in ABAC mode, the kubelet identity is correct, and you have role-assignment permissions. Without a repository condition, the role may grant read access across all repositories under that scope per policy.

### 9.2. When AKS should pull only a single repository

An organization sharing one ACR across teams might want:

~~~text
AKS Orders     → pull only orders/* repositories
AKS Payments   → pull only payments/* repositories
CI Orders      → push orders/* repositories without touching payments/*
~~~

Where ACR supports ABAC repository conditions, administrators attach a **condition** to the role assignment to restrict repositories. Conditions, expression syntax, and permission semantics must follow official IAM/ACR documentation—never guess them from Kubernetes namespace names.

**Kubernetes namespaces do not automatically restrict which ACR repositories the kubelet identity can pull.** The kubelet identity typically operates at cluster/node pool level in AKS; enforcing image-pull boundaries between teams requires proper ACR IAM design and cluster architecture combined with workload admission policies.

### 9.3. Constraints across permission combinations

- **`attach-acr`** does not replace assigning **Container Registry Repository Reader** in ABAC mode.
- If a registry switches permission mode after attaching to AKS, **re-evaluate roles** and re-test image pulls.
- Never rely on an old role name alone to assume authorization still works.
- Cross-tenant identity/permission setups have dedicated constraints; this lesson assumes same-tenant for CLI examples.
- After assigning permissions, wait for propagation and deploy a test Pod referencing a private image to verify live behavior.

## 10. Step D: build and push a test image to ACR

This lab needs an actual image in ACR. We use a tiny **Nginx** web container solely to verify image pull permissions. This is not a production app deployment; the container builds on a public image within an approved environment.

### 10.1. Illustrative Dockerfile

In a lab project folder, create two files:

**Dockerfile**

~~~dockerfile
# Simple demo; production requires digest pinning and CVE scanning.
FROM nginx:alpine
COPY index.html /usr/share/nginx/html/index.html
~~~

**index.html**

~~~html
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>AKS ACR demo</title></head>
<body><h1>AKS pulled image from ACR successfully</h1></body>
</html>
~~~

The app listens on HTTP/80 **inside the cluster**; this lesson does not expose it to the Internet. Because the base image is pulled from a public registry, builds need network access and may encounter rate limits; production should use approved, managed base images.

### 10.2. Build the image with ACR Tasks

From the folder containing the Dockerfile:

~~~bash
REPO="aks-pull-demo"
TAG="1.0.0"

az acr build \
  --registry "$ACR_NAME" \
  --image "$REPO:$TAG" \
  .
~~~

This command requires permission to queue ACR builds and registry/tier support for ACR Tasks. Some organizations build and push via CI/CD instead of ACR Tasks; both must follow image and tag security practices.

### 10.3. Verify the image exists in the registry

~~~bash
az acr repository show-tags \
  --name "$ACR_NAME" \
  --repository "$REPO" \
  --output table
~~~

With proper permissions, inspect manifests/digests and metadata using ACR/OCI tools. Never treat a successful build as proof that Pods can pull the image.

Construct the image reference:

~~~bash
IMAGE="$LOGIN_SERVER/$REPO:$TAG"
printf "Deploy image: %s\n" "$IMAGE"
~~~

Confirm **LOGIN_SERVER** matches the ACR where you granted roles and **REPO:TAG** exists. If using an ACR in another subscription, never mix up the login server from one registry with role assignments on another.

### 10.4. Why avoid `latest` in production?

The **`latest`** tag is mutable. If a pipeline pushes a new image under the same tag, nodes with different caches may run different images depending on `imagePullPolicy` and scheduling timing.

Recommendations:

- Tag by release version or commit SHA.
- Record the **image digest**.
- For critical workloads, deploy **`repository@sha256:digest`** to pin exact content.
- Store SBOMs, scan results, and build provenance.
- Enforce registry rules preventing overwriting production tags.
- Configure retention/garbage collection policies so rollback images are not purged prematurely.

## 11. Step E: configure kubectl and verify the target cluster

### 11.1. Fetch credentials for the lab cluster

~~~bash
az aks get-credentials \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME"
~~~

This updates kubeconfig per CLI behavior. Before deploying, **check your context** to avoid sending commands to production:

~~~bash
kubectl config current-context

kubectl cluster-info

kubectl get nodes -o wide
~~~

If nodes are not Ready, resolve AKS node health before debugging ACR pulls. A Deployment can sit unscheduled due to lack of node capacity completely unrelated to the registry.

### 11.2. Create a dedicated lab namespace

~~~bash
NS="acr-pull-lab"

kubectl create namespace "$NS"
~~~

If the namespace already exists, do not delete and recreate it just for this exercise. You can use an organization-designated namespace instead.

### 11.3. Verify Kubernetes permissions

Azure management-plane permissions on AKS do not equal Kubernetes permissions to create Deployments. If the cluster uses Kubernetes RBAC and Microsoft Entra integration, your user identity needs permissions in that namespace.

Check permissions:

~~~bash
kubectl auth can-i create deployments -n "$NS"
kubectl auth can-i get pods -n "$NS"
~~~

If lacking permission, ask the cluster admin for an appropriate Role/RoleBinding; never ask for cluster-wide **`cluster-admin`** just to run a lab Deployment.

## 12. Step F: deploy a Pod referencing the ACR image

### 12.1. Create the Deployment directly with kubectl

~~~bash
kubectl create deployment aks-pull-demo \
  --namespace "$NS" \
  --image "$IMAGE" \
  --replicas 1
~~~

This example requires no **`imagePullSecret`** when the kubelet identity holds the right role and ACR/networking conditions are met.

Watch rollout and Pods:

~~~bash
kubectl rollout status deployment/aks-pull-demo \
  --namespace "$NS" \
  --timeout=180s

kubectl get pods \
  --namespace "$NS" \
  -o wide
~~~

If it times out, **do not immediately conclude image pull failed**. Inspect events to distinguish scheduler Pending, ErrImagePull, or container CrashLoopBackOff.

### 12.2. Same Deployment in YAML

Manifest example for GitOps/IaC. **Replace** `IMAGE_PLACEHOLDER` with the full ACR image reference before applying:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aks-pull-demo
  namespace: acr-pull-lab
  labels:
    app: aks-pull-demo
spec:
  replicas: 1
  selector:
    matchLabels:
      app: aks-pull-demo
  template:
    metadata:
      labels:
        app: aks-pull-demo
    spec:
      containers:
        - name: web
          image: IMAGE_PLACEHOLDER
          imagePullPolicy: Always
          ports:
            - name: http
              containerPort: 80
          readinessProbe:
            httpGet:
              path: /
              port: http
            initialDelaySeconds: 2
            periodSeconds: 5
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              cpu: 250m
              memory: 256Mi
~~~

**`imagePullPolicy: Always`** in a lab forces kubelet to check the registry upon container creation even if cached on the node. This helps test permissions and networking, though it will not fix broken roles or DNS. In production, choose policies alongside digest pinning; pinning by digest is the clearest guarantee of immutable image content.

Save the manifest as **`deployment.yaml`** during practice, replace `IMAGE_PLACEHOLDER` with **`$LOGIN_SERVER/aks-pull-demo:1.0.0`** or a real digest, then apply:

~~~bash
kubectl apply -f deployment.yaml
~~~

Never run **`kubectl apply`** with an unreplaced placeholder: Kubernetes will attempt to pull a nonexistent image. Never commit manifests containing real credentials into source control.

### 12.3. Expose internally with ClusterIP for testing

~~~bash
kubectl expose deployment aks-pull-demo \
  --namespace "$NS" \
  --name aks-pull-demo \
  --port 80 \
  --target-port 80 \
  --type ClusterIP
~~~

Do not create a public LoadBalancer just to prove image pulls work; that incurs networking fees and opens extra attack surface.

From a machine with valid kubeconfig and network connectivity:

~~~bash
kubectl port-forward \
  --namespace "$NS" \
  service/aks-pull-demo 8080:80
~~~

In another terminal:

~~~bash
curl --fail --show-error http://127.0.0.1:8080/
~~~

If the demo page returns, the Pod is running and the Service routes traffic. However, to prove the cluster truly has permission to pull private images, inspect **Pod events, image digest/`imageID`**, and registry configuration; a cached image on a node can mask pull failures if policy does not force re-verification.

### 12.4. Separate image pull status from application status

| Pod status | Common meaning | Action priority |
|---|---|---|
| **Pending** | Not scheduled yet or waiting on constraints | Check node capacity, taints, PVCs, scheduler events |
| **ContainerCreating** | Preparing container/environment | Check image pull, CNI, volumes |
| **ErrImagePull** | Kubelet failed to pull image | Check registry permissions, image reference, network |
| **ImagePullBackOff** | Kubelet retrying with backoff after pull failure | Read Events for root cause |
| **Running yet NotReady** | Process runs but readiness fails | Check port, readiness probe, application logs |
| **CrashLoopBackOff** | Container started then crashed/restarted | Check command, env, logs, resources |
| **Running + Ready** | Pod ready to serve per readiness probe | Proceed with smoke tests and dependency checks |

## 13. Verifying AKS–ACR integration with dedicated tools

### 13.1. `az aks check-acr`

Azure CLI provides a command to test ACR connectivity from an AKS cluster:

~~~bash
az aks check-acr \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --acr "$LOGIN_SERVER"
~~~

This command may spin up test resources inside the cluster and requires suitable permissions and cluster health. It helps evaluate node/cluster registry reachability, auth, and networking within the tool's test scope.

**A PASS result from this tool is helpful, but does not replace testing a real Deployment with your image**, especially when registries use ABAC repository permissions, private networking, admission policies, or distinct image manifests.

If `check-acr` fails due to Kubernetes RBAC, NotReady nodes, or policies blocking test Pods, resolve the tool's prerequisites before concluding the registry is broken.

### 13.2. Inspect Pod details and Events

~~~bash
kubectl get pods -n "$NS" -o wide

kubectl describe deployment/aks-pull-demo -n "$NS"

kubectl get events \
  -n "$NS" \
  --sort-by=.lastTimestamp
~~~

To inspect the exact failing Pod:

~~~bash
kubectl get pods \
  -n "$NS" \
  -l app=aks-pull-demo
~~~

After grabbing the real **`POD_NAME`**:

~~~bash
POD_NAME="<pod-name-from-kubectl-get>"

kubectl describe pod "$POD_NAME" -n "$NS"

kubectl get pod "$POD_NAME" \
  -n "$NS" \
  -o jsonpath='{.status.containerStatuses[*].imageID}'
~~~

Events typically contain messages like **failed to pull image**, **unauthorized**, **manifest unknown**, **dial tcp timeout**, or DNS failures. Find the **root cause** before blindly editing roles.

### 13.3. Read logs at the right time

If the container has started:

~~~bash
kubectl logs deployment/aks-pull-demo \
  -n "$NS" \
  --tail=100
~~~

If the image **failed to pull**, the container never started and **there are no application logs** to read. Focus on **`kubectl describe pod`** and Events instead of hunting for app logs.

### 13.4. Verify the image reference the cluster is using

~~~bash
kubectl get deployment aks-pull-demo \
  -n "$NS" \
  -o jsonpath='{.spec.template.spec.containers[*].image}'
~~~

Verify exact registry login server, repository, and tag/digest. A typo like **`aks-pull-dmeo`** returns 404/manifest unknown even when permissions and networking are spotless.

## 14. ImagePullBackOff: layered analysis workflow

**ImagePullBackOff is a symptom, not a root cause.** Analyze sequentially from image configuration to permissions and networking.

~~~mermaid
flowchart TD
    A["Pod ImagePullBackOff"] --> B{"Does image reference/tag exist?"}
    B -->|No| C["Fix registry/repository/tag/digest"]
    B -->|Yes| D{"Registry auth/role valid?"}
    D -->|No| E["Check kubelet identity, permission mode, role"]
    D -->|Yes| F{"Node reaches ACR login & data endpoints?"}
    F -->|No| G["Check DNS, firewall, Private Link, routes"]
    F -->|Yes| H["Check image manifest, OS/arch, policies, registry health"]
    H --> I["Recreate Pod / wait out backoff & verify"]
~~~

### 14.1. Step 1: check image name and registry

First:

~~~bash
az acr repository show-tags \
  --name "$ACR_NAME" \
  --repository "aks-pull-demo" \
  --output table
~~~

Verify:

- Registry login server in the Pod is exact.
- Repository casing and path are exact.
- Tag/digest was genuinely pushed.
- Manifest supports the node's OS and CPU architecture.
- Image was not deleted by retention policies or purge jobs.

A missing image produces **404/manifest unknown**; granting higher roles will not materialize a missing manifest.

### 14.2. Step 2: check kubelet identity and permissions

~~~bash
az aks show \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --query "identityProfile.kubeletidentity" \
  --output json

az role assignment list \
  --assignee "$KUBELET_OBJECT_ID" \
  --scope "$ACR_ID" \
  --include-inherited \
  --output table
~~~

- For **RBAC Registry Permissions**, confirm kubelet holds **AcrPull** or an accepted equivalent.
- For **ABAC Repository Permissions**, confirm **Container Registry Repository Reader** and any repository condition match.
- For newly created roles, allow propagation time before declaring failure.
- If the cluster changed identities or was recreated, roles may still point to an old principal.
- If AKS uses a service principal instead of managed identity, verify that specific identity type.

### 14.3. Step 3: check networking from nodes to ACR

Errors like **i/o timeout**, **dial tcp**, **DNS lookup failure**, or TLS handshake errors are often unrelated to RBAC.

Verify:

1. Do AKS nodes have egress to the ACR login server on **HTTPS/443**?
2. Do ACR public network access / firewall rules permit that path?
3. If ACR uses a private endpoint, do nodes resolve the private IP accurately?
4. Are ACR domain names and data endpoints resolvable and allowed through firewalls?
5. Are NSGs, UDRs, Azure Firewall, NVAs, proxies, or NAT blocking traffic?
6. Are private/public cluster and private/public registry paired in a supported topology?

**Never open public access or a 0.0.0.0/0 firewall rule** just to make an error vanish in production. Diagnose the exact path and allow only required endpoints and traffic.

### 14.4. Step 4: check policies and limits

When roles and networking are sound, verify:

- AKS node OS/CPU architecture supports the image.
- Manifest list / OCI media types are supported by the container runtime.
- Kubernetes admission policies are not blocking the registry or tag.
- ACR image quarantine, signing, scan rules, or org policies are not blocking pulls.
- Registry and data endpoints are healthy.
- The cluster has no quota, disk pressure, container runtime, or CNI failures.
- A policy requiring signed digests is not rejecting a tag reference.

Never rely solely on repeatedly running **`kubectl delete pod`**. The Deployment controller recreates Pods, yet without fixing the root cause the error will repeat.

## 15. Private ACR, Private Endpoint, and DNS

A public ACR endpoint works in labs, whereas production often requires images to traverse private networks with public network access restricted.

### 15.1. Public ACR with controlled AKS egress

When ACR uses a public endpoint, AKS nodes need HTTPS connectivity to the registry. If AKS sits in private subnets, outbound traffic may route through NAT Gateway, Azure Firewall, or a supported egress path.

Review:

- ACR public network access and firewall rules.
- Egress source IPs or network access allowlists.
- DNS resolution of ACR login server and data endpoints.
- NSG/UDR/FQDN filtering rules.
- Whether proxies or TLS inspection affect certificate trust.
- Connectivity to Entra/Azure authentication endpoints for token acquisition.

**Never assume stable node egress IPs** unless your network architecture is explicitly designed to guarantee them.

### 15.2. ACR Private Link

To use a **private endpoint** for ACR:

- Verify ACR **SKU** and Private Link support in current feature docs; Private Endpoints generally require a suitable tier such as **Premium**.
- Create the private endpoint targeting the registry in an appropriate VNet/subnet.
- Ensure AKS nodes have routing to the private IP via the same VNet, VNet peering, or another supported link.
- Configure the **Private DNS Zone**, typically involving **`privatelink.azurecr.io`**, along with Azure-created/recommended records.
- Account for both the **login endpoint** and **data endpoints** serving image layers.
- If disabling public network access, confirm all pull, push, and build clients retain private connectivity.
- Inspect network policies, UDRs, and firewalls if traffic traverses inspection appliances.

~~~mermaid
flowchart LR
    NODE["AKS nodes/kubelet<br/>AKS subnet"] -->|"HTTPS inside VNet/peering"| PE["ACR Private Endpoint<br/>private IP"]
    PE --> ACR["ACR Premium<br/>private registry"]
    DNS["Private DNS Zone<br/>privatelink.azurecr.io"] -. "Registry name → private IP" .-> NODE
    CI["CI/CD build/push"] -->|"Dedicated private path required"| PE
~~~

### 15.3. Private AKS and Private ACR are different concepts

- **Private AKS cluster** refers to private access to the Kubernetes **API server / control plane**.
- **Private ACR** refers to the network path to the **container registry** for pushing/pulling images.
- A private AKS cluster can still pull from a public ACR if network policies and egress permit.
- A public AKS cluster can still pull from a private ACR if nodes have private routing and private DNS.

Never configure a private cluster and assume all ACR traffic automatically flows over Private Link.

### 15.4. Common DNS issues

If ACR has a private endpoint yet kubelet resolves the login server to a public IP or fails to resolve data endpoints:

1. Check the Private DNS zone and VNet links.
2. Check Azure-created A-records/aliases for the registry and data endpoints.
3. Check custom DNS servers and conditional forwarders.
4. Check ACR region and geo-replication if enabled.
5. Test DNS from **a network environment matching AKS nodes**, not only from a laptop.
6. Verify HTTPS/443 and firewalls once DNS resolves properly.

**Never create manual A-records indiscriminately** without understanding endpoint lifecycles and how Azure manages private DNS.

## 16. Cross-subscription, cross-tenant, and multi-cluster

### 16.1. AKS and ACR in separate resource groups or subscriptions

AKS in **`rg-aks-prod`** and ACR in **`rg-platform-acr`** can hold proper role assignments. Across two subscriptions in the **same tenant**, pass the **ACR resource ID** as the scope when attaching or assigning roles per supported models.

The operator needs:

- Read permissions on cluster/identity configuration.
- Read permissions on ACR plus rights to create role assignments at ACR scope.
- AKS management permissions when calling `update`.
- Network connectivity between nodes and ACR.
- Approval coordination between the two subscription owners.

Never assume **Contributor on the AKS resource group** suffices to create role assignments in the ACR subscription.

### 16.2. Cross-tenant

If AKS and ACR belong to **different Microsoft Entra tenants**, managed identity integration and `attach-acr` carry specific limits and prerequisites. Never follow same-tenant instructions mechanically.

When cross-tenant is a genuine requirement:

1. Consult official AKS–ACR cross-tenant documentation for your service version.
2. Pick an organization-approved auth mechanism: federated identity, service principal, or registry credentials where supported.
3. Design credential rotation, secret storage, and least privilege.
4. Inspect registry networking, tenant policies, and role scopes.
5. Test image pulls in a non-production environment before scaling out.

Never default to long-lived ACR admin credentials without understanding the cross-tenant trust boundary.

### 16.3. Multiple AKS clusters sharing one ACR

Multiple clusters can pull images from a single registry when authorized. However, you must govern:

- Who can push releases into the registry?
- Can dev clusters pull production images?
- Does the registry enforce repository-specific ABAC conditions?
- Is network connectivity from all regions/VNets to ACR reliable?
- Is geo-replication (a tier-dependent feature) needed to optimize pull paths?
- If the registry suffers an outage, will new nodes or Pods needing fresh pulls be impacted?

A central registry standardizes images, yet becomes a shared dependency. Plan replication, backup/export strategies, and image retention aligned with DR targets.

## 17. `imagePullSecrets`: when to use and when not to

Kubernetes supports **`imagePullSecrets`** to supply registry credentials for pulling private images. This helps with external non-Azure registries, specialized cross-tenant setups, or environments where managed identity integration is unavailable.

Example Pod structure assuming a Kubernetes Secret named **`regcred`** was created securely:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: private-image-test
  namespace: acr-pull-lab
spec:
  imagePullSecrets:
    - name: regcred
  containers:
    - name: app
      image: example-registry.invalid/repo/app:1.0.0
~~~

**This is a structural example, not a ready-to-run manifest**: hostname **`example-registry.invalid`** is a placeholder and Secret **`regcred`** must exist in the same namespace per Kubernetes requirements.

### 17.1. Risks of `imagePullSecrets`

- Secrets have lifecycles and can expire or rotate.
- Anyone permitted to read Secrets in that namespace can inspect the credential if access controls are loose.
- Secrets must be distributed and maintained across multiple namespaces/service accounts per policy.
- Credentials can easily be over-scoped, such as using a registry admin account.
- When a Secret expires, newly scheduled Pods fail even while older Pods keep running.

With AKS and ACR in the same tenant on supported setups, **kubelet managed identity + pull role** eliminates password distribution overhead compared to registry username/password secrets.

### 17.2. Never commit registry passwords to Git

Never create an `imagePullSecret` from a real username/password and commit the Base64-encoded Secret YAML thinking it is encrypted. **Base64 is encoding, not encryption.**

If secret-based credentials are unavoidable, enforce secret management/rotation, RBAC, cluster encryption at rest, and secure CI/CD handling. Never grant cluster-wide secret read permissions.

## 18. Updating images, rollouts, and rollbacks

### 18.1. Build a new version

Suppose the pipeline builds/pushes version **`1.0.1`**:

~~~bash
az acr build \
  --registry "$ACR_NAME" \
  --image "aks-pull-demo:1.0.1" \
  .
~~~

In the cluster, update the Deployment:

~~~bash
kubectl set image \
  deployment/aks-pull-demo \
  web="$LOGIN_SERVER/aks-pull-demo:1.0.1" \
  -n "$NS"

kubectl rollout status \
  deployment/aks-pull-demo \
  -n "$NS" \
  --timeout=180s
~~~

Remember **`web`** is the container name from our **YAML manifest example**; if you used **`kubectl create deployment`** earlier, the container name may differ. Check **`.spec.template.spec.containers[].name`** before running **`kubectl set image`**:

~~~bash
kubectl get deployment aks-pull-demo \
  -n "$NS" \
  -o jsonpath='{.spec.template.spec.containers[*].name}'
~~~

Never guess container names when running `set image`.

### 18.2. Rollback

If a new release pulls its image yet fails readiness or runtime checks, you can roll back to the previous revision while rollout history remains:

~~~bash
kubectl rollout history \
  deployment/aks-pull-demo \
  -n "$NS"

kubectl rollout undo \
  deployment/aks-pull-demo \
  -n "$NS"

kubectl rollout status \
  deployment/aks-pull-demo \
  -n "$NS" \
  --timeout=180s
~~~

Rolling back workloads **does not automatically roll back database schemas or data**. If the previous image was purged from ACR, new nodes cannot pull it; image retention is therefore part of rollback readiness.

### 18.3. Why choose image digests?

Tags can be overwritten, so deploying by image digest locks down the exact tested artifact:

~~~text
image: acrordersdemo123.azurecr.io/orders-api@sha256:<verified-digest>
~~~

All environments should reference the exact same artifact/digest when following "build once, deploy many." Pipelines should capture the digest after push and write it into Deployment/GitOps manifests.

Never deploy illustrative placeholder digests; fetch real digests from registry metadata using approved tools.

## 19. CI/CD and protecting the image supply chain

A production pipeline typically includes:

~~~mermaid
flowchart LR
    GIT["Git commit"] --> BUILD["Build/test"]
    BUILD --> SCAN["SCA/CVE/SBOM and policy"]
    SCAN --> PUSH["Push versioned image to ACR"]
    PUSH --> DIGEST["Record digest"]
    DIGEST --> MANIFEST["Update Deployment/GitOps manifest"]
    MANIFEST --> AKS["AKS rolling rollout"]
    AKS --> HEALTH["Readiness/smoke test"]
    HEALTH --> OBS["Logs, metrics, alerts"]
~~~

### 19.1. Separating three permission sets

1. **CI/CD build/push:** permitted to push only to required repositories/scopes.
2. **AKS kubelet pull:** permitted only to read images needed for deployment per active permission mode.
3. **Runtime application:** receives data-plane rights via service account/workload identity; needs zero registry push rights.

This separation limits supply-chain risk: a compromised Pod cannot overwrite production images in the registry.

### 19.2. Image content and security policies

- Use trusted, regularly patched base images.
- Scan for vulnerabilities and inspect dependencies.
- Use immutable tags/digests; avoid **`latest`** in production.
- Never embed passwords, tokens, SSH keys, or connection strings in Dockerfiles or image layers.
- Enforce admission policies restricting allowed registries and requiring digests/signatures where mandated.
- Verify CPU architecture compatibility with node pools (amd64/arm64).
- Maintain procedures to revoke defective images or images with critical CVEs.
- Retain enough image versions for rollbacks per retention policy.

### 19.3. ACR Tasks and AKS are separate billing and execution paths

Building images with **`az acr build`** uses registry build/Tasks capacity; deploying to AKS uses cluster node compute. Never assume building an image in ACR means the app is running, or that a green build pipeline means nodes/kubelet can pull the image.

## 20. Monitoring and costs

### 20.1. What to monitor?

| Source | Signals | Meaning |
|---|---|---|
| AKS/Kubernetes Events | Pulling, Pulled, Failed, BackOff | Distinguish pull success from failure causes |
| Pod status | ContainerCreating, ImagePullBackOff, Ready | Whether Pods started cleanly |
| Deployment rollout | Available/Unavailable replicas | Whether releases reached desired state |
| ACR metrics/diagnostics | Authentication, requests, pull/push activity in supported logs | Detect registry load/errors |
| Azure Activity Log | Role assignments, registry/network changes, AKS updates | Audit control-plane changes |
| Azure Monitor/Container Insights | Nodes, container CPU/memory, logs | Monitor runtime after image pull |
| CI/CD pipeline logs | Build/push/digest/deploy versions | Trace image provenance |
| Cost Management | ACR, AKS nodes, networking, logs | Control overall spend |

Never assume registry audit/diagnostic logs are enabled by default. Configure diagnostic settings and retention appropriately while scrubbing secrets/PII from logs.

### 20.2. Common cost lines

| Component | Potential cost drivers |
|---|---|
| ACR SKU | Registry tier and tier-included features |
| ACR Storage | Stored image layers/manifests and artifacts |
| ACR Tasks/Build | Build/automation compute per pricing and quota |
| ACR geo-replication / Private Link | Tier features, regional replicas, and private networking traffic |
| AKS nodes | VM compute, managed disks, node pools, and quotas |
| AKS management tier | Tier/SLA fee or service pricing policies |
| Load Balancer/NAT Gateway/Firewall | Network services and traffic per configuration |
| Log Analytics/Monitor | Ingestion, retention, alerts |
| Cross-region/Internet egress | Data transfer fees where applicable |

**Attaching ACR does not make image pulling free in all scenarios.** Running the registry, storage, compute nodes, logging, and networking still incurs costs.

If AKS and ACR sit in different regions, account for pull latency and cross-region data transfer fees depending on direction and configuration. In large clusters, image size and frequent node scale-outs can substantially impact bandwidth.

### 20.3. Tracking in Azure Cost Management

1. Select the right subscription/resource group or organizational billing scope.
2. Group by service/resource/meter to separate registry, AKS compute, storage, and networking.
3. Correlate costs with build/push schedules, node scale-outs, rollouts, and image pulls.
4. Review whether registry replicas, private endpoints, and network appliances are still needed.
5. Apply `owner`/`environment`/`costCenter` tags on supported resources.
6. Set budgets/alerts and review periodically.

Cost Management data can lag; never assume cost dropped to zero immediately after deleting a Pod or registry resource.

## 21. Common issues and troubleshooting

| Symptom | Possible cause | Check/remediation |
|---|---|---|
| **ErrImagePull / ImagePullBackOff** | Permission, image reference, or network error | `kubectl describe pod`, Events |
| **401 Unauthorized** | Kubelet missing token/permission or auth mismatch | Check kubelet identity and role matching permission mode |
| **403 Forbidden** | Authenticated principal denied by RBAC/ABAC or registry network policy | Check role, conditions, firewalls, and network access |
| **404 Manifest unknown** | Wrong repo/tag/digest or artifact deleted | `az acr repository show-tags`, verify exact reference |
| **i/o timeout / dial tcp** | Node cannot reach registry/data endpoint | Check DNS, NSG, firewall, UDR, NAT, Private Link |
| **x509 certificate error** | TLS interception/proxy/cert chain or wrong endpoint | Check certs, proxies, DNS, network path |
| **No matching manifest** | Image lacks node's OS/CPU architecture | Verify platform image and node architecture |
| **Role assignment exists yet Pod fails** | Role not propagated, stale principal, ABAC mode, networking | Wait for propagation, verify object ID/mode/Events |
| **`az aks --attach-acr` fails** | Missing role-assignment rights, ACR ABAC mode, or wrong scope/tenant | Read exact error and choose the right integration branch |
| **`kubectl get pods`: Forbidden** | Missing Kubernetes RBAC, not ACR permission | Check context, RoleBindings, and cluster auth |
| **Pod Pending** | Node resources/taints/PVCs/quotas | `kubectl describe pod`, scheduler events |
| **CrashLoopBackOff** | Image pulled successfully yet app crashes | `kubectl logs`, command, config, memory |
| **Running yet NotReady** | Misconfigured readiness probe or app unready | Check probe/path/port/dependencies |
| **New Pod fails while old Pod runs** | Cached image, recently changed registry role/network, deleted tag | Check `pullPolicy`, tag/digest, and active identity |
| **Purging ACR tags breaks rollback** | Old image version was purged | Align image retention with release/rollback policy |

### 21.1. Standard investigation procedure

1. Capture **namespace, Deployment, Pod, node, image reference, and failure timestamp**.
2. Read **Pod Events** to see HTTP status codes or network error types.
3. Confirm repository/tag/digest exists in ACR.
4. Read the **AKS kubelet identity** (never confuse with control plane identity).
5. Identify whether ACR uses **RBAC registry** or **ABAC repository** mode.
6. Verify role/conditions and scope; wait for propagation if newly assigned.
7. Confirm nodes have **DNS/HTTPS reachability to ACR login and data endpoints**.
8. Run **`az aks check-acr`** where appropriate.
9. Deploy a test Pod in a lab with the exact image and monitor rollout.
10. Once pulling succeeds, shift to debugging process/startup/readiness if the Pod is still NotReady.

Never troubleshoot by granting Owner to nodes or disabling ACR firewalls in production without an approved change.

## 22. Lab cleanup and revoking permissions

After verifying results and saving needed logs:

### 22.1. Delete lab Kubernetes workloads

~~~bash
kubectl delete deployment aks-pull-demo \
  -n "$NS"

kubectl delete service aks-pull-demo \
  -n "$NS"
~~~

If namespace **`acr-pull-lab`** was created solely for this exercise and holds no other resources:

~~~bash
kubectl delete namespace "$NS"
~~~

Never delete production namespaces or any namespace without checking everything inside it.

### 22.2. Controlled revocation of AcrPull

If an **`AcrPull`** role was assigned solely for testing and no workloads still use it, the IAM owner can inspect and revoke the assignment per process. Example **for ACR RBAC Registry Permissions only**:

~~~bash
az role assignment list \
  --assignee "$KUBELET_OBJECT_ID" \
  --scope "$ACR_ID" \
  --output table
~~~

Do not delete the role assignment just because the lab ended if that kubelet identity still pulls from ACR for other workloads. If attached via **`attach-acr`**, you can run **`az aks update --detach-acr`** where supported once the owner confirms and checks all dependencies.

### 22.3. Clean up Azure resources

- **ACR:** delete only if created exclusively for the lab and containing no shared images/repositories.
- **AKS cluster:** delete only if it is an owner-approved lab cluster after exporting any logs or data needed.
- **Resource group:** never bulk-delete if other resources reside inside it.
- **Private endpoints, DNS, NAT, Log Analytics:** review costs and dependencies before deleting.
- **Role assignments:** revoke individually by scope without impacting other applications.

For learning ACR integration, there is no need to delete a shared AKS cluster simply because you removed a test Deployment.

## 23. Pre-production checklist

- [ ] ACR and AKS placed in the right subscription, region, tenant, and ownership.
- [ ] Images referenced with full **`loginServer/repository:tag`** or real digest.
- [ ] Repository/tag exists and image supports node OS/architecture.
- [ ] Kubelet identity verified by exact object ID; not confused with control plane or workload identity.
- [ ] ACR permission mode verified: RBAC Registry vs. ABAC Repository.
- [ ] Pull role matches model, principal, and scope; ABAC conditions applied if repository isolation is required.
- [ ] CI/CD push identity separated from kubelet management/pull rights when unnecessary.
- [ ] ACR admin user disabled and no registry passwords in manifests where managed identity is supported.
- [ ] Nodes have HTTPS/443 connectivity to registry login and data endpoints.
- [ ] If using Private Endpoint, verified Private DNS Zone, VNet links, UDRs/firewalls, and data endpoints.
- [ ] Same-tenant / cross-subscription / cross-tenant architecture designed per supported capabilities.
- [ ] AKS nodes Ready and Kubernetes RBAC configured for deployers in the right namespaces.
- [ ] Deployment pulls cleanly from private registry, Pods Ready, and smoke tests pass.
- [ ] Image digest recording, CVE scanning, SBOM, and provenance enforced per policy.
- [ ] Rollout/rollback tested; image retention keeps required release versions.
- [ ] Logs, Events, alerts, and IAM/network change auditing configured.
- [ ] Costs for registry, AKS nodes, builds, networking, and monitoring tracked.
- [ ] Runbooks ready for image pull failures and registry/network outages.
- [ ] Clear owners assigned for role assignments, secrets, and periodic access reviews.

## 24. Practice exercises

### Exercise 1: Distinguish identities

An AKS cluster has a control plane managed identity, a kubelet identity, and a Pod using Microsoft Entra Workload ID to read Blob Storage.

Answer:

1. Which identity is normally used to pull private images from ACR?
2. Which identity is used to call Azure Storage from inside the Pod?
3. Why might granting **`AcrPull`** to the control plane identity not suffice?
4. When a Pod fails to pull its image, can Workload Identity fix that failure?

### Exercise 2: End-to-end deployment

In an approved lab environment:

1. Create/read ACR and capture login server and resource ID.
2. Identify the ACR permission mode.
3. Read AKS's kubelet identity.
4. Run **`attach-acr`** if RBAC Registry Permissions, or assign the matching role if ABAC.
5. Build/push the Nginx demo image to ACR.
6. Create a Deployment referencing the private image.
7. Inspect Events, `imageID`, and rollout status.
8. Port-forward the Service and fetch the web page.
9. Clean up the Deployment/Service without accidentally deleting a shared registry.

### Exercise 3: Diagnose ImagePullBackOff

A Pod specifies image:

~~~text
acrordersdemo123.azurecr.io/orders-api:2.4.1
~~~

Events report **unauthorized**. The operator just granted Contributor on the AKS resource group to the Pod's identity, yet the error persists. Describe step-by-step checks across: kubelet identity, ACR scope, permission mode, role assignment, propagation, and registry networking.

### Exercise 4: Switching registry to ABAC mode

An organization enables **RBAC Registry + ABAC Repository Permissions** so the Orders cluster can pull only **`orders/*`** repositories. Previously they used **`az aks update --attach-acr`**.

Explain why pull permissions must be re-evaluated and propose configuring **Container Registry Repository Reader** with a matching repository condition rather than keeping `AcrPull` assumptions.

### Exercise 5: Private ACR fails to pull

The registry has a Private Endpoint, public access is disabled, and roles are right, yet kubelet reports **`dial tcp: i/o timeout`**. Trace the path:

~~~text
AKS node → DNS → ACR private IP → login/data endpoints
~~~

Explain how to verify VNet peering, Private DNS zone, subnet routing/UDRs, firewalls, and required endpoints. Why doesn't a successful **`docker pull`** on a laptop outside the VNet prove nodes can pull?

### Exercise 6: CI/CD and rollback

A pipeline deploys **`orders-api:3.0.0`** to AKS, then needs to roll back to **`2.9.0`**:

1. How should push and pull permissions be separated?
2. Why avoid overwriting the **`latest`** tag?
3. Which digest/manifest must be preserved for rollback?
4. How do you check **`kubectl rollout history/undo`**?
5. If tag `2.9.0` was purged from ACR, what happens during scale-out?
6. Why doesn't rolling back the image automatically roll back the database?

### Self-check questions

1. What permission does **`az aks --attach-acr`** grant and to which identity?
2. How does image-pull permission differ from an application's permission to read Azure Storage?
3. What is the role of **`AcrPull`** in ACR RBAC Registry Permissions?
4. When is **`Container Registry Repository Reader`** needed instead of `AcrPull`?
5. Why can't `attach-acr` handle every ABAC registry scenario?
6. What risks do Kubernetes `imagePullSecrets` carry if using a registry admin password?
7. Is `ImagePullBackOff` always an RBAC error?
8. When do `kubectl logs` fail to help diagnose image pulls?
9. Why must you still check DNS and data endpoints even when an ACR Private Endpoint exists?
10. When should you deploy by image digest instead of a mutable tag?
11. Does a Kubernetes namespace automatically restrict kubelet to pulling repositories matching the namespace name?
12. How does **`az aks check-acr`** differ from testing a real Pod with your target image?
13. Why doesn't stopping a Pod or deleting a Deployment drop AKS node and ACR costs to zero?
14. If a cluster has multiple nodes and only newly added nodes fail to pull, what should you check?

## 25. References

- [Authenticate with Azure Container Registry from AKS — Microsoft Learn](https://learn.microsoft.com/azure/aks/cluster-container-registry-integration)
- [Azure Container Registry authentication overview](https://learn.microsoft.com/azure/container-registry/container-registry-authentication)
- [Azure Container Registry repository permissions and ABAC](https://learn.microsoft.com/azure/container-registry/container-registry-rbac-abac-repository-permissions)
- [Azure Container Registry roles and permissions](https://learn.microsoft.com/azure/container-registry/container-registry-roles)
- [Azure Container Registry Private Link](https://learn.microsoft.com/azure/container-registry/container-registry-private-link)
- [ACR networking best practices](https://learn.microsoft.com/azure/container-registry/container-registry-firewall-access-rules)
- [Azure CLI: az aks](https://learn.microsoft.com/cli/azure/aks)
- [Azure CLI: az acr](https://learn.microsoft.com/cli/azure/acr)
- [Kubernetes images](https://kubernetes.io/docs/concepts/containers/images/)
- [Kubernetes debugging Pods](https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/)
- [Azure Container Registry pricing](https://azure.microsoft.com/pricing/details/container-registry/)
- [Azure Kubernetes Service pricing](https://azure.microsoft.com/pricing/details/kubernetes-service/)
