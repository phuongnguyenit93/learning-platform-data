# Managing Secrets and Workload Identity on GKE

## Learning Objectives

After this lesson, learners will be able to:

1. Distinguish **Kubernetes ServiceAccount (KSA)**, **Google Cloud IAM service account (IAM SA)**, **node service account**, IAM policies, and Kubernetes RBAC; avoid confusing Kubernetes API permissions with Google Cloud API permissions.
2. Explain how **Workload Identity Federation for GKE** (WIF for GKE) provides short-lived credentials to Pods without storing JSON service account keys inside containers.
3. Create direct IAM bindings for a KSA principal, or link a KSA to an IAM service account via impersonation when APIs/applications require it.
4. Compare **Kubernetes Secrets**, **Google Cloud Secret Manager**, **Secret Manager add-on/CSI volumes**, and **SecretSync**; select the right approach by sensitivity, rotation needs, app interface, and operational requirements.
5. Implement a **gcloud + kubectl + YAML + Java** example so a Pod reads an authorized secret, verifies the mount, and handles rotation without exposing plaintext values.
6. Diagnose **403, `ImagePullBackOff`, `FailedMount`, ADC/token errors, and stale secrets**, while designing least-privilege IAM/RBAC, logging, auditing, HA, and cost controls.

## 1. Real-World Scenario: A Pod Needs Secrets and Cloud Access

Suppose a company deploys a retail system on **Google Kubernetes Engine (GKE)**:

- The Java/Spring Boot **`orders-api`** Deployment needs a legacy service password stored in **Secret Manager**.
- The same Pod needs permission to **read a Cloud Storage bucket**, without permission to delete or overwrite objects.
- The **`image-processor`** worker needs permission to read source images and write optimized images to a separate bucket.
- The **Cloud Build** pipeline pushes images to **Artifact Registry** and deploys new versions to GKE.
- An operations team can view Pod logs, yet **must not be permitted to read secret values**.

An insecure shortcut is baking a JSON private key or DB password into the container image, `deployment.yaml`, a ConfigMap, pipeline env vars, or Git. Any leak of source code, the registry, or logs then compromises the secret.

Instead:

1. **Workload Identity Federation for GKE** verifies *which workload the Pod is* and issues short-lived identity credentials for Google Cloud APIs.
2. **IAM** decides which specific secret or bucket the workload may access.
3. **Secret Manager** stores sensitive values, managing versions, access controls, audit logs, and rotation workflows.
4. **Kubernetes RBAC**, namespaces, Pod security, and network policies reduce the risk of other cluster workloads stealing identities or secrets.
5. **The application** must still safeguard values once read into memory, files, logs, and downstream connections.

In the **CLOUD_PROVIDERS_GCP** module, this connects projects/IAM/VPCs with Compute Engine, GKE, Cloud Run, storage, and databases, supporting release automation, resource protection, reliability tracking, and cost control.

> **Core principle:** identity and secrets are two separate problems. WIF answers "which workload is calling?", IAM answers "what is this workload allowed to do?", and Secret Manager holds "the secret value." Never grant broad IAM roles just to bypass secret mounting errors.

## 2. Identities That Are Frequently Confused

### 2.1. Comparison Table

| Concept | Where Does It Exist? | What Is It Used For? | Example |
|---|---|---|---|
| **Google Cloud user** | Google Cloud IAM/Identity | Administering GKE and cloud resources per IAM permissions | `developer@example.com` |
| **Kubernetes ServiceAccount (KSA)** | Kubernetes API, scoped to **one namespace** | Pod identity toward Kubernetes and WIF | `namespace=shop`, `name=orders-ksa` |
| **Kubernetes RBAC Role/RoleBinding** | Kubernetes cluster | Lets a KSA/user call Kubernetes API operations | get/list Pods, not get Secrets |
| **Google Cloud IAM service account (IAM SA)** | Google Cloud project | Workload identity for Google APIs; can be impersonated | `orders-gsa@shop-dev-001.iam.gserviceaccount.com` |
| **Node service account** | Compute Engine node / managed node pool | Permissions for node agents, image pulls, and node functions | `gke-nodes@...` |
| **WIF principal identifier** | Google Cloud IAM policy | Represents a KSA/namespace/cluster inside IAM | `principal://.../subject/ns/shop/sa/orders-ksa` |
| **Secret Manager secret** | Google Cloud Secret Manager | Stores secrets and their versions | `orders-db-password` |
| **Kubernetes Secret** | Kubernetes API namespace | Stores sensitive config for Pods via Kubernetes mechanisms | `db-credentials` |

**A KSA is not an IAM SA.** Both contain the words "service account," yet one lives in a cluster namespace while the other lives in Google Cloud IAM. Always distinguish the two in every step below.

### 2.2. Two Separate Authorization Planes

~~~mermaid
flowchart LR
    P["Pod orders-api<br/>serviceAccountName: orders-ksa"] --> K["Kubernetes ServiceAccount"]
    K --> R["Kubernetes RBAC<br/>Kubernetes API"]
    K --> W["Workload Identity Federation<br/>GKE metadata server"]
    W --> I["Google Cloud IAM policy"]
    I --> SM["Secret Manager"]
    I --> GCS["Cloud Storage"]
    I --> OTHER["Supported Google APIs"]
~~~

A KSA **holding a Kubernetes Role to list Pods** does not automatically gain Secret Manager access. Conversely, a KSA principal granted **`roles/secretmanager.secretAccessor`** cannot automatically list Kubernetes Secrets inside the cluster.

### 2.3. Avoid Using the `default` KSA for Every Pod

Every namespace has a KSA named **`default`**. If all apps share the `default` KSA and IAM binds permissions to that principal, workloads will **unintentionally share permissions**.

Good design:

~~~text
Namespace shop
  ServiceAccount orders-ksa        → read orders-db-password only
  ServiceAccount image-worker-ksa  → read input bucket, write output bucket

Namespace analytics
  ServiceAccount reports-ksa       → read reports bucket only
~~~

In Kubernetes workload manifests, always declare **`serviceAccountName`** explicitly for apps needing API/secret access. Never attach a privileged GSA to a shared KSA.

## 3. How Does Workload Identity Federation for GKE Work?

### 3.1. Accessing Google APIs Without Storing Service Account Keys

When WIF for GKE is enabled, Google Cloud manages a project-level **workload identity pool** formatted as:

~~~text
PROJECT_ID.svc.id.goog
~~~

Each project has a managed workload identity pool for GKE. GKE registers the cluster as an identity provider and runs the **GKE metadata server** on nodes to exchange the workload's identity assertion for short-lived credentials when calling Google APIs.

~~~mermaid
sequenceDiagram
    participant APP as Java app in Pod
    participant META as GKE metadata server
    participant STS as Google Cloud token services
    participant IAM as IAM policy
    participant SM as Secret Manager
    APP->>META: ADC requests credential
    META->>STS: Exchange workload attestation
    STS-->>META: Short-lived credential
    META-->>APP: Credential
    APP->>SM: accessSecretVersion over TLS
    SM->>IAM: Check principal / permission
    alt Authorized
        IAM-->>SM: Allow
        SM-->>APP: Secret payload
    else Unauthorized
        IAM-->>SM: Deny
        SM-->>APP: PERMISSION_DENIED
    end
~~~

The diagram illustrates the logical flow, not a claim that every internal call occurs synchronously in exact lockstep. **ADC (Application Default Credentials)** and Google Cloud client libraries handle short-lived credentials automatically without bundling JSON keys.

### 3.2. How Do Autopilot and Standard Differ?

| Cluster | WIF Status | Operational Prerequisites |
|---|---|---|
| **GKE Autopilot** | **Always enabled** | No manual WIF enablement needed; nodes use GKE-managed metadata |
| **New GKE Standard** | Can be enabled at cluster creation | Ensure cluster has a workload pool and node pools use GKE metadata server |
| **Existing GKE Standard** | Must enable on cluster, then check/update existing node pools | Enabling on the cluster **does not automatically update existing node pools** |

On Standard, when a node pool uses **`GKE_METADATA`**, Pods hitting the metadata endpoint are served by the GKE metadata server rather than the node's Compute Engine metadata server, subject to documented exceptions such as **`hostNetwork` Pods**.

### 3.3. What Does a KSA Principal Identifier Look Like?

Suppose:

~~~text
Project ID       = shop-dev-001
Project number   = 123456789012
Namespace        = shop
KSA              = orders-ksa
~~~

This KSA's principal identifier is:

~~~text
principal://iam.googleapis.com/projects/123456789012/locations/global/workloadIdentityPools/shop-dev-001.svc.id.goog/subject/ns/shop/sa/orders-ksa
~~~

**`123456789012`** is the **project number**, not the project ID. Namespace and KSA fields must match Kubernetes names exactly.

Broader selectors:

| IAM Principal Type | Scope |
|---|---|
| **`principal://.../subject/ns/shop/sa/orders-ksa`** | Any Pod running under that namespace/KSA name in the workload pool |
| **`principal://.../kubernetes.serviceaccount.uid/UID`** | One specific Kubernetes ServiceAccount by UID |
| **`principalSet://.../namespace/shop`** | All Pods in namespace `shop` within the pool |
| **`principalSet://.../kubernetes.cluster/...`** | Pods belonging to a specific cluster when using supported selectors |

Under least privilege, prefer a **specific KSA principal** rather than granting a **`principalSet` across an entire namespace or cluster** unless explicitly required.

### 3.4. "Identity Sameness" Risk Across Clusters in the Same Project

Within a single project, two GKE clusters can share the **same workload identity pool**. If both contain **namespace `shop` and KSA `orders-ksa`**, the namespace/KSA-based IAM identifier maps to **the same principal**, regardless of cluster.

This is especially dangerous when a dev cluster managed by multiple teams shares a project with a production cluster. Mitigations include:

1. **Separate clusters of different trust levels into different projects**.
2. Use strictly governed, distinct namespace/KSA names.
3. Consider **KSA UID** or cluster-constrained selectors where appropriate.
4. Enforce policies controlling who can create namespaces/KSAs and who can deploy workloads under privileged KSAs.

Never assume **cluster name** is automatically part of a namespace/name-based KSA principal string. This is a mandatory check in multi-cluster architectures.

## 4. Two Ways for Pods to Call Google Cloud APIs

### 4.1. Method A — Grant IAM Directly to the Kubernetes ServiceAccount Principal

Recommended whenever the target API supports federated principal IAM bindings:

~~~text
Pod → orders-ksa → WIF principal
                 → IAM binding on Secret Manager secret
                 → Secret Manager API
~~~

Benefits:

- No need to create a GSA solely to read Secret Manager.
- IAM directly binds one KSA to one secret or bucket.
- No long-lived service account keys to manage.
- Clean auditing per workload identity.

Limitation: a few APIs, client libraries, or use cases do not yet support direct WIF principals and may require Method B.

### 4.2. Method B — KSA Impersonates an IAM Service Account

~~~text
Pod → KSA → Workload Identity Federation
          → roles/iam.workloadIdentityUser on IAM SA
          → IAM SA credential impersonation
          → Google Cloud API
~~~

Requires **both configurations**:

1. On the IAM SA, grant **`roles/iam.workloadIdentityUser`** to the KSA using the supported member syntax.
2. Annotate the KSA with **`iam.gke.io/gcp-service-account=GSA_EMAIL`**.

Additionally, the IAM SA must hold the exact roles needed on target Google Cloud resources. Annotating the KSA without granting impersonation permission still leaves the Pod failing with **403**.

**You neither need nor should** download a GSA JSON private key into the Pod. Impersonation issues short-lived credentials and preserves IAM governance.

### 4.3. When to Choose Which Method?

| Scenario | Preferred Approach |
|---|---|
| Pod reads a Secret Manager secret | **Direct IAM KSA principal** |
| Pod accesses a Cloud Storage bucket with IAM support | Direct IAM when supported by the use case |
| Client/Google API lacks direct federated identity support | KSA → **IAM SA impersonation** |
| Legacy app checks identity via GSA email | Impersonation; verify compatibility |
| Only needs access to Kubernetes Pods/ConfigMaps | Kubernetes RBAC; **Google IAM not strictly needed** |

These two methods are not two mandatory sequential steps. Pick one clean model per workload and document IAM binding owners.

## 5. Where Are Secrets Stored? Kubernetes Secret vs. Secret Manager

### 5.1. Kubernetes Secret

A Kubernetes **Secret** is an API object inside a namespace holding sensitive data up to **1 MiB per Secret**.

Example:

~~~yaml
apiVersion: v1
kind: Secret
metadata:
  name: legacy-db
  namespace: shop
type: Opaque
stringData:
  username: training-user
  password: REPLACE_WITH_NON_REAL_VALUE
~~~

**Never commit files containing real secrets to Git**, whether using **`stringData`** or **`data`**. The **`data`** field requires base64, yet **base64 is encoding, not encryption**—anyone reading it can decode it immediately.

GKE provides default encryption at rest for customer data, including Kubernetes Secrets. For additional control with customer-managed keys, you can enable **application-layer secrets encryption with Cloud KMS** per GKE features. That **does not replace Kubernetes RBAC**: anyone permitted to read the Secret via the Kubernetes API still receives plaintext per API semantics.

### 5.2. Secret Manager

**Google Cloud Secret Manager** stores **secrets** with multiple **secret versions** (e.g., 1, 2, `latest`), offering per-secret IAM controls, audit logs, lifecycle rules, rotation schedules/notifications, and regional/CMEK options.

| Criterion | Kubernetes Secret | Secret Manager |
|---|---|---|
| Control plane | Kubernetes API | Google Cloud API |
| Identifier | `namespace/name` | `project/locations/secret/version` |
| Primary access control | Kubernetes RBAC, admission, namespaces | Google Cloud IAM and guardrails |
| Value stored in cluster state | **Yes** | **No**, when using direct API or CSI mount without syncing |
| Direct consumption | env var, secret volume, `imagePullSecrets` | SDK/API, CSI volume; SecretSync if K8s Secret is needed |
| Versioning | Updates Secret object; no Secret Manager-style versions | Versioned with aliases/`latest` |
| Rotation | Update Secret; Pod/app must pick up change | Add version; integrates with CSI refresh/sync/app reload |
| Best fit | Legacy apps, controllers requiring K8s Secrets, pull secrets | Sensitive credentials, IAM governance, auditing, multi-service sharing |

Secret Manager is recommended as the centralized secret store for workloads needing IAM governance. Kubernetes Secrets remain a valid part of Kubernetes; what matters is **controlling where secret copies reside**.

### 5.3. Do Not Confuse Three "Secret" Terms

- **Kubernetes Secret**: Kubernetes API object.
- **Secret Manager secret**: Google Cloud resource holding versions.
- **SecretProviderClass**: CSI configuration declaring **which Secret Manager versions to mount**; it contains no plaintext secret itself.

In our hands-on section, we use the **Secret Manager add-on** to mount secrets directly into Pods as files without creating an intermediate Kubernetes Secret whenever the app can read files.

## 6. Methods for Delivering Secrets to Pods

| Delivery Method | Pros | Limits / Risks | When to Use |
|---|---|---|---|
| **Kubernetes Secret → env** | App reads env vars trivially | Secret sits in cluster API; env **never auto-updates** in running containers | Legacy apps supporting env vars only |
| **Kubernetes Secret → volume** | Files update after propagation delay | Still a K8s Secret; **`subPath` never auto-updates** | Controllers/apps needing file semantics |
| **Secret Manager SDK/API directly** | No copy in K8s; clear IAM; app controls caching/retries | Requires code changes and handling API latency/quotas | Java apps able to use the SDK |
| **GKE Secret Manager add-on (CSI)** | Mounted directly as files in Pod without creating a K8s Secret; optional rotation | Depends on CSI and supported node/GKE versions; app must reload | File-reading apps wanting managed operations |
| **GKE SecretSync** | Syncs Secret Manager into a K8s Secret for standard env/volume use | Secret **is copied into cluster state** | Legacy apps/controllers strictly needing K8s Secrets |

**Selection guideline:** prefer the **SDK or CSI add-on** whenever possible. Sync into a Kubernetes Secret only when the application strictly requires that API object. This aligns with Google Cloud's Secret Manager integration guidance.

## 7. Controlling Kubernetes Secrets and RBAC

### 7.1. Base64 and Encryption

In Kubernetes manifests, **`data`** holds base64 strings while **`stringData`** takes plaintext that the API server converts to `data`. Both can leak secrets through manifests, shell history, Git, or CI logs.

~~~bash
# View metadata only; never print secret payloads to terminals/logs
kubectl get secrets -n shop
kubectl describe secret legacy-db -n shop
~~~

Never put `kubectl get secret ... -o yaml` or base64 decoding into shared runbooks, as it exposes payloads to anyone reading terminal/session logs. **`kubectl describe secret`** generally shows only key names and byte sizes; still verify what your logging tools capture.

### 7.2. Access Rights to Kubernetes Secrets

An example **Role** granting **`get` on a specific Kubernetes Secret**—including its sensitive payload—via the Kubernetes API (not metadata alone). Grant this only when an app genuinely needs to read a Secret via the Kubernetes API:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: legacy-secret-reader
  namespace: shop
rules:
  - apiGroups: [""]
    resources: ["secrets"]
    resourceNames: ["legacy-db"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: legacy-secret-reader-binding
  namespace: shop
subjects:
  - kind: ServiceAccount
    name: legacy-reader-ksa
    namespace: shop
roleRef:
  kind: Role
  name: legacy-secret-reader
  apiGroup: rbac.authorization.k8s.io
~~~

This Role affects **only the Kubernetes API**; it grants no Secret Manager access. Furthermore, a RoleBinding alone is not complete isolation if a user holds **`create` Pod rights in the same namespace**, because they could launch a Pod that mounts Secrets accessible to Pods in that namespace.

### 7.3. Privilege Escalation Risk via Pod Creation

Even without the `get` verb on Secrets, permission to **`create` Pods/Deployments** in a namespace can let a user schedule a Pod mounting a Secret in that namespace and extract its value indirectly.

Therefore:

1. Separate namespaces by trust boundary; never let untrusted users deploy into namespaces holding production secrets.
2. Restrict who can create/edit **Pods, Deployments, Jobs, and DaemonSets**, especially `serviceAccountName`.
3. Enforce **Pod Security Admission**, policy/admission controls, and network policies per architecture.
4. Never share nodes/clusters across mutually untrusted tenants if isolation needs exceed the model's guarantees.
5. Restrict **`exec` into containers**, as it can read mounted filesystems, memory, and process env vars.

### 7.4. Secret Volumes and Env Vars Update Differently

Example Pod consuming a Kubernetes Secret:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: legacy-web
  namespace: shop
spec:
  replicas: 1
  selector:
    matchLabels: {app: legacy-web}
  template:
    metadata:
      labels: {app: legacy-web}
    spec:
      containers:
        - name: web
          image: REGION-docker.pkg.dev/PROJECT_ID/REPOSITORY/IMAGE:TAG
          env:
            - name: LEGACY_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: legacy-db
                  key: password
          volumeMounts:
            - name: db-files
              mountPath: /etc/legacy-db
              readOnly: true
      volumes:
        - name: db-files
          secret:
            secretName: legacy-db
~~~

Here:

- **`LEGACY_PASSWORD`** is read once at container startup; updating the Secret **does not update env vars** in running containers.
- **Secret volumes** are normally updated by kubelet after a sync/cache delay, **unless mounted via `subPath`**.
- The app may still hold the old password in memory or its connection pool even after the file changes. Implement reload logic or trigger a rolling restart as appropriate.

In production, avoid injecting the same secret into both env vars and a volume when one channel suffices. This example shows both only to contrast behavior.

## 8. Hands-On A — Preparing GKE Workload Identity Federation

### 8.1. Lab Assumptions

| Attribute | Illustrative Value |
|---|---|
| GKE/Secret Manager project | **`shop-dev-001`** |
| Sample project number | **`123456789012`** |
| Standard or Autopilot cluster | **`shop-gke`** |
| Region | **`asia-southeast1`** |
| Kubernetes namespace | **`shop`** |
| Kubernetes ServiceAccount | **`orders-ksa`** |
| Secret Manager secret | **`orders-db-password`** |
| Test workload image | **`busybox:1.36`** (substitute an approved internal image if required) |

**This is an undeployed lab.** Project number, domain, IPs, and cluster/secret names are illustrative. Creating clusters, enabling add-ons, storing secrets, logging, and running Pods can incur charges. Run only in an authorized project.

### 8.2. Check Project, Cluster, and IAM

~~~bash
gcloud config get-value project
gcloud auth list
gcloud projects describe shop-dev-001 \
  --format="value(projectNumber)"

gcloud container clusters describe shop-gke \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --format="yaml(name,location,workloadIdentityConfig,nodePools)"
~~~

Replace **`123456789012`** in the IAM commands below with your **actual `projectNumber`**. On Autopilot, WIF for GKE is already enabled; on Standard, confirm both the cluster and relevant node pools use the GKE metadata server.

### 8.3. Enable WIF on an Existing Standard Cluster If Not Yet Enabled

~~~bash
# Impacts the cluster; requires admin permissions and a change plan.
gcloud container clusters update shop-gke \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --workload-pool=shop-dev-001.svc.id.goog
~~~

This command applies only to **Standard**. Enabling it at the cluster level does not automatically update pre-existing node pools.

### 8.4. Check Standard Node Pools

~~~bash
gcloud container node-pools list \
  --cluster=shop-gke \
  --project=shop-dev-001 \
  --location=asia-southeast1

gcloud container node-pools describe NODE_POOL \
  --cluster=shop-gke \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --format="yaml(config.workloadMetadataConfig)"
~~~

If an older node pool does not yet use the GKE metadata server, update it via an approved change procedure:

~~~bash
gcloud container node-pools update NODE_POOL \
  --cluster=shop-gke \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --workload-metadata=GKE_METADATA
~~~

Updating a node pool can cause Pods to be evicted or rescheduled; choose a rollout strategy matching your SLO. Autopilot skips this step and does not accept the Standard WIF `nodeSelector`.

### 8.5. Fetch kubeconfig and Create Namespace/KSA

~~~bash
gcloud container clusters get-credentials shop-gke \
  --project=shop-dev-001 \
  --location=asia-southeast1

kubectl config current-context
kubectl create namespace shop
kubectl create serviceaccount orders-ksa -n shop
kubectl get serviceaccount orders-ksa -n shop -o yaml
~~~

Before running, verify the namespace/KSA doesn't already exist or apply an equivalent idempotent manifest. **`get-credentials`** switches the active kubeconfig context, so confirm the **right cluster/namespace** before deploying.

### 8.6. A KSA Alone Has Zero Google Cloud Permissions

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-ksa
  namespace: shop
~~~

Creating a KSA grants no access to Secret Manager, Cloud Storage, or Cloud SQL. Next comes an **IAM binding on the target resource itself**.

## 9. Hands-On B — Direct IAM: KSA Reads Only One Secret Manager Secret

### 9.1. Prepare the Secret

First create a secret for the lab. **Never put real secret values on the command line or in Git.** Depending on process, use an approved secret-entry tool; the command below creates an empty secret container with no password version yet:

~~~bash
gcloud services enable secretmanager.googleapis.com \
  --project=shop-dev-001

gcloud secrets create orders-db-password \
  --project=shop-dev-001 \
  --replication-policy=automatic
~~~

Add a secret version with **non-sensitive lab content** for practice (a safely prepared file named **`lab-secret.txt`**):

~~~bash
gcloud secrets versions add orders-db-password \
  --project=shop-dev-001 \
  --data-file=./lab-secret.txt

gcloud secrets versions list orders-db-password \
  --project=shop-dev-001
~~~

In production, the input file must be generated securely with restricted permissions and never committed to VCS; after confirming the secret is stored, securely wipe the plaintext copy per policy. Never print the secret to the terminal to prove success.

### 9.2. Grant `secretAccessor` to the Exact KSA Principal

~~~bash
gcloud secrets add-iam-policy-binding orders-db-password \
  --project=shop-dev-001 \
  --member="principal://iam.googleapis.com/projects/123456789012/locations/global/workloadIdentityPools/shop-dev-001.svc.id.goog/subject/ns/shop/sa/orders-ksa" \
  --role="roles/secretmanager.secretAccessor"
~~~

Key points:

- The IAM binding applies to **one secret**, not the entire project.
- **`roles/secretmanager.secretAccessor`** grants access to secret version payloads for that secret only; it cannot create/delete secrets or edit IAM.
- If the cluster sits in a different project than the secret, the principal string must use the **cluster identity pool's project number/ID**, while **`--project`** targets the project holding the secret.
- If **IAM Deny, VPC Service Controls, organization policies, or network policies** block access, this role alone does not guarantee success.

### 9.3. Read Back IAM Without Reading the Secret Value

~~~bash
gcloud secrets get-iam-policy orders-db-password \
  --project=shop-dev-001

kubectl get serviceaccount orders-ksa -n shop
~~~

Confirm the policy contains the exact **`principal://.../subject/ns/shop/sa/orders-ksa`** with no unintended wildcard `principalSet`. Never grant **`roles/owner`** or **`roles/secretmanager.admin`** to an application that only reads secrets.

### 9.4. Negative Test

Create a second KSA **`unprivileged-ksa`** in the same namespace with **no IAM bindings**. A Pod using this KSA must receive **`PERMISSION_DENIED`** when calling Secret Manager. If it succeeds, check:

- Was the KSA granted IAM via a project- or ancestor-level role?
- Is the app using a JSON service account key or another ADC file instead of WIF?
- Is there an active GSA impersonation or overly broad `principalSet`?
- Do dev and prod clusters share identical namespace/KSA identifiers in the same identity pool?

**Testing only the happy path is insufficient** to prove least privilege.

## 10. Hands-On C — Using the Secret Manager Managed Add-On (CSI Volume)

### 10.1. Version Requirements and Limitations

The **GKE Secret Manager add-on** is a Google Cloud-managed component built on the **Secrets Store CSI Driver** using the **`gke`** provider and CSI driver:

~~~text
secrets-store-gke.csi.k8s.io
~~~

Prerequisites from official documentation:

| Requirement | Minimum / Condition |
|---|---|
| GKE version for add-on | **`1.27.14-gke.1042001`** or newer |
| GKE version for add-on automatic rotation | **`1.32.2-gke.1059000`** or newer |
| Node OS | **Container-Optimized OS / Ubuntu Linux** |
| GKE modes | **Autopilot and Standard** |
| Authentication | **Workload Identity Federation for GKE** |
| Windows Server nodes | **Not supported** with this add-on |
| CSI driver name | **`secrets-store-gke.csi.k8s.io`** |
| SecretProviderClass provider | **`gke`** |
| Default rotation if enabled | **120 seconds**, minimum **60 seconds** |

**Do not confuse this managed driver** with the open-source **`secrets-store.csi.k8s.io`** driver and **`gcp`** provider. Both can coexist during migrations, yet they use different manifests.

### 10.2. Enable the Add-On and Rotation on Eligible Clusters

~~~bash
# Modifies cluster configuration (authorized lab only).
gcloud container clusters update shop-gke \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --enable-secret-manager \
  --enable-secret-manager-rotation
~~~

On eligible GKE versions, you can specify a custom interval:

~~~bash
gcloud container clusters update shop-gke \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --enable-secret-manager \
  --enable-secret-manager-rotation \
  --secret-manager-rotation-interval=300s
~~~

Rotation flags will not work on unsupported older versions. **Never toggle cluster features in production just to experiment**, as changes can impact running workloads mounting secrets.

Verify configuration:

~~~bash
gcloud container clusters describe shop-gke \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --format="yaml(addonsConfig.secretManagerConfig,workloadIdentityConfig)"
~~~

### 10.3. SecretProviderClass Specifying Which Version to Mount

Save as **`orders-secret-provider.yaml`** (an illustrative filename only; do not create this practice file in this worker task):

~~~yaml
apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata:
  name: orders-secret-provider
  namespace: shop
spec:
  provider: gke
  parameters:
    secrets: |
      - resourceName: "projects/shop-dev-001/secrets/orders-db-password/versions/latest"
        path: "db-password"
~~~

Explanation:

- **`SecretProviderClass`** holds **resource names**, not plaintext passwords.
- **`versions/latest`** picks the newest version at mount/refresh per add-on rules; pinning **`versions/1`** means adding version 2 **will not automatically** update the mounted config to version 2.
- **`path`** is the filename created inside the volume—here **`db-password`**.
- For **regional Secret Manager secrets**, the resource path must include **`/locations/REGION/`** in region-specific format; do not use global syntax for a regional secret.

~~~bash
kubectl apply -f orders-secret-provider.yaml
kubectl get secretproviderclass -n shop
~~~

### 10.4. Pod Using KSA and CSI Volume

Manifest **`orders-secret-test.yaml`**:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: orders-secret-test
  namespace: shop
spec:
  serviceAccountName: orders-ksa
  containers:
    - name: test
      image: busybox:1.36
      command:
        - sh
        - -c
        - |
          if test -s /var/secrets/db-password; then
            echo "Secret mounted successfully (value hidden)"
          else
            echo "Secret file missing or empty" >&2
            exit 1
          fi
          sleep 3600
      volumeMounts:
        - name: orders-password
          mountPath: /var/secrets
          readOnly: true
  volumes:
    - name: orders-password
      csi:
        driver: secrets-store-gke.csi.k8s.io
        readOnly: true
        volumeAttributes:
          secretProviderClass: orders-secret-provider
~~~

On **GKE Standard**, if the cluster mixes node pools, add to the Pod **`spec`**:

~~~yaml
nodeSelector:
  iam.gke.io/gke-metadata-server-enabled: "true"
~~~

**Do not add this `nodeSelector` in Autopilot**: Autopilot manages WIF-enabled nodes automatically and may reject that selector.

Run:

~~~bash
kubectl apply -f orders-secret-test.yaml
kubectl get pod orders-secret-test -n shop
kubectl describe pod orders-secret-test -n shop
kubectl logs orders-secret-test -n shop
~~~

The log command only prints a success/failure message, **never the password**. This is intentional to prevent leaking secrets into terminals, CI logs, or monitoring systems.

### 10.5. Why Must the Namespace Match?

The **Pod, KSA, and SecretProviderClass** in this example all live in namespace **`shop`**. The IAM principal identifies **`shop/orders-ksa`**. Deploying the Pod in **`default`** or switching `serviceAccountName` to another KSA causes the mount to fail because WIF permissions no longer match.

### 10.6. Testing New Versions and Rotation

1. Create a new secret version via a secure process without logging the payload.
2. Keep the SecretProviderClass pointing to **`versions/latest`**.
3. With rotation enabled on an eligible GKE version, the add-on polls periodically (default 120 seconds) and updates the **mounted file** without restarting the Pod.
4. The application must **re-read the file or reload credentials/connection pools**; a Java app reading the password once at startup still holds the old value.
5. Verify rotation via **version ID, safe checksum checks, or connection behavior**, never by printing plaintext secrets.

**Important:** updating the mounted file **does not mean** existing database connections re-authenticate automatically or Spring properties auto-refresh. Design credential lifecycle handling inside the application.

## 11. Hands-On D — Using the Google Cloud Java Client to Read Secret Manager Directly

Java applications can also call the Secret Manager API directly without CSI. This lets the app control fetch timing, retries, caching, version pinning, and telemetry.

### 11.1. Workflow

1. The Pod runs with **`orders-ksa`** and working WIF.
2. The KSA principal holds **`secretmanager.versions.access`** via **`roles/secretmanager.secretAccessor`** on the secret.
3. The Java client uses **Application Default Credentials**, needing no JSON service account key file.
4. The application fetches the configured version, uses it in memory, avoids logging it, and clears/overwrites buffers where possible.

### 11.2. Java Example

Add the official **`google-cloud-secretmanager`** dependency to your Maven/Gradle BOM at an organization-approved version. Illustrative code:

~~~java
import com.google.cloud.secretmanager.v1.AccessSecretVersionResponse;
import com.google.cloud.secretmanager.v1.SecretManagerServiceClient;
import com.google.cloud.secretmanager.v1.SecretVersionName;

public final class DbSecretLoader {
    private DbSecretLoader() {}

    public static String readPassword(String projectId, String secretId)
            throws Exception {
        SecretVersionName name =
            SecretVersionName.of(projectId, secretId, "latest");

        // Client library automatically discovers Application Default Credentials.
        try (SecretManagerServiceClient client =
                SecretManagerServiceClient.create()) {
            AccessSecretVersionResponse response =
                client.accessSecretVersion(name);
            return response.getPayload().getData().toStringUtf8();
        }
    }
}
~~~

This example returns a **`String`** for readability; Java `String` objects are immutable and cannot be deterministically wiped from the heap immediately. For highly sensitive secrets, consider byte-based APIs with controlled memory lifetimes, minimizing how long secrets sit in singletons or long-lived caches.

**Never call this API on every incoming HTTP request in production**: it adds latency, quota consumption, and cost, and couples request availability directly to Secret Manager. Use bounded caching/reloading, retries with backoff, and controlled error handling.

### 11.3. Secret Manager and Spring Boot

If the application needs database credentials:

- With a **CSI volume**, read **`/var/secrets/db-password`** from disk via a compatible loader; for rotation, refresh HikariCP pool credentials via a controlled reload routine.
- With the **direct API**, fetch at startup or inside a credential provider service; refresh periodically if using **`latest`**, backed by circuit breakers and error handling.
- Never log **`spring.datasource.password`**, **JDBC URLs with embedded passwords**, or environment dumps.
- Consider **Cloud SQL IAM database authentication**, Cloud SQL connectors/proxies, or managed identity auth instead of static passwords where supported; note that WIF and DB authentication remain two distinct layers.

**Do not assume:** enabling WIF automatically lets Java log into PostgreSQL. IAM authorizes Google Cloud API calls; the database may still require its own authentication setup.

## 12. Alternative — KSA Impersonating an IAM Service Account

If an API client lacks direct KSA principal support or requires a GSA identity, use impersonation.

### 12.1. Create a Dedicated IAM SA for `orders-api`

~~~bash
gcloud iam service-accounts create orders-gsa \
  --project=shop-dev-001 \
  --display-name="GKE orders application"
~~~

The GSA email will be:

~~~text
orders-gsa@shop-dev-001.iam.gserviceaccount.com
~~~

### 12.2. Grant the GSA Access to the Secret

~~~bash
gcloud secrets add-iam-policy-binding orders-db-password \
  --project=shop-dev-001 \
  --member="serviceAccount:orders-gsa@shop-dev-001.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
~~~

### 12.3. Allow the KSA to Impersonate the GSA

~~~bash
gcloud iam service-accounts add-iam-policy-binding \
  orders-gsa@shop-dev-001.iam.gserviceaccount.com \
  --project=shop-dev-001 \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:shop-dev-001.svc.id.goog[shop/orders-ksa]"
~~~

### 12.4. Annotate the KSA

~~~bash
kubectl annotate serviceaccount orders-ksa \
  --namespace=shop \
  iam.gke.io/gcp-service-account=orders-gsa@shop-dev-001.iam.gserviceaccount.com
~~~

**Both the IAM binding and the annotation are required.** If testing **direct principal mode** in the same lab, avoid leaving unnecessary overlapping grants around; document which mode each workload uses and revoke unused roles.

### 12.5. Common Mistakes

- Wrong member syntax: **`serviceAccount:PROJECT_ID.svc.id.goog[NAMESPACE/KSA]`** is for impersonation, **different** from the full **`principal://`** syntax used in direct IAM.
- GSA lives in a different project from the cluster, causing mismatched emails/projects in bindings.
- Missing annotation on the KSA, or Pod using a different KSA.
- GSA can be impersonated, yet lacks the role on the Secret Manager secret itself.
- Pod runs on a Standard node pool without GKE metadata server enabled.
- Client sets **`GOOGLE_APPLICATION_CREDENTIALS`** pointing to an old or missing key file, causing ADC to bypass the expected WIF path.

**For apps requiring an email-formatted identity**, you can use the **`iam.gke.io/return-principal-id-as-email: "true"`** annotation per docs, provided you understand endpoint compatibility and never treat it as a substitute for IAM grants.

## 13. SecretSync — When Applications Only Understand the Kubernetes Secret API

### 13.1. Why Can't Every App Use CSI Files?

Some Helm charts, controllers, and legacy apps strictly read a **Kubernetes Secret** by name via:

- **`env.valueFrom.secretKeyRef`**.
- **`volume.secret.secretName`**.
- Custom resources referencing **`secretName`**.

When an app cannot read CSI files or use the SDK, GKE's **Secret Manager integrated secret synchronization** can create/update a Kubernetes Secret from Secret Manager.

**Understand the trade-off:** the secret **is copied into the Kubernetes API/cluster state**, bringing back all the RBAC, encryption, namespace isolation, and Pod-creation escalation concerns covered earlier. Whenever an app can read files, Google Cloud docs prefer the **Secret Manager add-on** over SecretSync.

### 13.2. Prerequisites and Flags

GKE's integrated SecretSync feature requires:

| Requirement | Details |
|---|---|
| GKE version | **`1.33` or newer** per current docs |
| Cluster mode | Autopilot and Standard |
| WIF for GKE | **Required** |
| Cluster flag | **`--enable-secret-sync`** |
| Rotation flag | **`--enable-secret-sync-rotation`**; default 120s, minimum 60s |
| K8s resources | **`SecretProviderClass`** and **`SecretSync`**, plus IAM on the KSA |

Example on an eligible cluster:

~~~bash
# Modifies cluster config; run only after verifying version and permissions.
gcloud container clusters update shop-gke \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --enable-secret-sync \
  --enable-secret-sync-rotation
~~~

**SecretSync is distinct from the CSI add-on**: enabling **`--enable-secret-manager`** for CSI mounts does not automatically enable secret synchronization. Both can use `SecretProviderClass`, yet differ in delivery mechanism and where secrets live.

### 13.3. Example `SecretSync` Resource

Assuming **`orders-secret-provider`** from Section 10 exists in namespace **`shop`**, a **`SecretSync`** resource can create Kubernetes Secret **`orders-legacy`**:

~~~yaml
apiVersion: secret-sync.gke.io/v1
kind: SecretSync
metadata:
  name: orders-legacy
  namespace: shop
spec:
  serviceAccountName: orders-ksa
  secretProviderClassName: orders-secret-provider
  secretObject:
    type: Opaque
    data:
      - sourcePath: db-password
        targetKey: password
~~~

The legacy app then consumes:

~~~yaml
env:
  - name: LEGACY_DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: orders-legacy
        key: password
~~~

**When SecretSync rotation updates the Kubernetes Secret, env vars in running containers still do not update automatically.** You still need a restart/reload workflow. Mounting the Kubernetes Secret as a volume updates after propagation delay if `subPath` is not used, though the app must still re-read the file.

### 13.4. Stopping Sync Does Not Delete Copied Secrets

Disabling SecretSync on a cluster **does not automatically delete** previously created Kubernetes Secrets. Follow a separate cleanup procedure after migration so unmanaged secret copies don't linger. Never delete a `SecretSync` or Kubernetes Secret while workloads still depend on it without a verified replacement.

## 14. Rotation: Rotating Secrets Is More Than Creating a New Version

### 14.1. What Makes Rotation Successful?

Any password-authenticated system has at least three states to coordinate:

1. **Secret Manager** stores the new secret version.
2. **Pods/applications** read the new version.
3. **Target services** (databases, third-party APIs) accept the new credential and stop accepting the old one.

Completing only step (1) leaves apps running with the old password in env vars, memory, or connection pools. Changing the database password before Pods update immediately breaks live traffic.

### 14.2. Recommended Two-Credential Overlap When Supported

~~~mermaid
flowchart LR
    A["Old credential active"] --> B["Create/allow new credential at target"]
    B --> C["Add new Secret Manager version"]
    C --> D["Canary/rollout or CSI refresh"]
    D --> E["Verify app uses new credential"]
    E --> F["Revoke old credential"]
    F --> G["Audit + clean up old version per policy"]
~~~

When target services support **two concurrent active keys or accounts**, overlapping cuts downtime risk. If a database supports only one password per account, plan a change window, retries, draining, synchronized rollouts, and a rollback plan.

### 14.3. Pinning Versions vs. Using `latest`

| Version Choice | Pros | Cons |
|---|---|---|
| **`versions/5`** (pinned) | Reproducible deployments, clean rollback to exact version | Must update manifests/configs on every rotation |
| **`versions/latest`** | Can pick up new versions automatically via CSI rotation/SDK refresh | Risk of unexpected changes; requires app reload and testing |
| **Managed version aliases** if supported | Switch alias to an approved version via workflow | Extra alias governance; not every integration handles aliases identically |

In production, align version strategy with your release process; not every secret suits **`latest`**. Database credentials require both app and target readiness, while certificates/CAs often need dual-trust windows.

### 14.4. Rotation Does Not Mean Operators Read Plaintext

Operators running a rotation pipeline may need permission to create Secret Manager versions, whereas runtime only needs **`secretAccessor`**. Separate the principals with proper review:

- **Runtime KSA**: reads published secrets.
- **Rotation service account**: adds new versions and updates credentials on scoped target systems.
- **Security/platform admin**: manages IAM, policies, audits, and lifecycle.

Never grant full **Secret Manager Admin** to a Java app just because it reads a secret at runtime.

### 14.5. Revoking and Destroying Versions

When secret exposure is suspected:

1. Revoke at the **target service** (rotate database password, revoke API key).
2. Block further issuance of the old credential via IAM or remove references.
3. Publish a new version and roll out/reload workloads.
4. Confirm via telemetry/safe checks that no workloads still use the old version.
5. **Disable** the old version to verify impact before permanently **destroying** it per policy.

Per Secret Manager best practices, **disable before destroying** so you can detect lingering dependencies. Disabling or destroying a Secret Manager version does not immediately revoke sessions/tokens already issued by a target system; revoke directly at the target.

## 15. Security Hardening for Workload Identity and Secrets

### 15.1. Multi-Layered Security Boundaries

~~~mermaid
flowchart TD
    U["Developer / CI / Admin"] --> AUTH["IAM + cluster authentication"]
    AUTH --> RBAC["Kubernetes RBAC / admission policies"]
    RBAC --> POD["Pod with dedicated KSA"]
    POD --> WIF["WIF for GKE / GKE metadata server"]
    WIF --> IAM["Google Cloud IAM on secret/bucket"]
    IAM --> SM["Secret Manager / Google API"]
    POD --> NET["NetworkPolicies, Pod security, TLS"]
    SM --> AUD["Audit/monitoring"]
    NET --> AUD
~~~

### 15.2. Hardening Checklist

| Layer | Best Practice | Risk If Ignored |
|---|---|---|
| **Cluster/project isolation** | Separate projects/clusters between prod and untrusted environments | KSA principal identity collision across clusters |
| **KSA** | Dedicated KSA per workload and namespace | Unintended IAM permission sharing across apps |
| **Google IAM** | Grant on specific resources (e.g., one secret) | Compromising one Pod exposes many secrets |
| **Kubernetes RBAC** | Restrict get/list/watch Secrets, Pod creation, and exec | Exfiltration via Kubernetes API or Pods |
| **Admission/Pod Security** | Block dangerous privileged/`hostPath`, restrict `hostNetwork` | Accessing node metadata or out-of-scope secrets |
| **Container runtime** | Non-root where possible, read-only root FS where suitable | Easier attacker persistence and extraction |
| **Secret delivery** | Prefer SDK/CSI; minimize plaintext copies | Secrets leaked in manifests, backups, or env dumps |
| **Encryption** | GKE default encryption, plus Cloud KMS app-layer encryption if needed | Lack of key governance and data-layer controls |
| **Network** | NetworkPolicy, egress/TLS, and private endpoints per architecture | Unauthorized outbound calls or secret exfiltration |
| **Logging** | Audit permissions and errors; **never log secret values** | Secrets leaked in log aggregators |
| **Supply chain** | Pin image digests, scan images, enforce deployment policies | Malicious image accesses mounted tokens/secrets |

### 15.3. Risks of `privileged`, `hostNetwork`, and Node Identity

Workloads running **`hostNetwork: true`** have special limitations: they **do not use WIF for GKE in the standard way** and may reach alternative metadata paths. Node service account permissions and node network policies therefore remain part of your threat model.

Containers running **`privileged`**, mounting host filesystems, or holding broad node capabilities can bypass Pod-to-Pod isolation. WIF is an identity mechanism—**it is not an absolute sandbox if a node is compromised**.

### 15.4. Keep Secrets Out of Hard-to-Revoke Places

Avoid:

- Container image layers and Dockerfile **`ENV`/`ARG`** with plaintext secrets.
- Kubernetes ConfigMaps, plain GitOps YAML, and unprotected Helm values.
- CLI flags passing real passwords in process args or shell history.
- Treating base64 **`data`** in Kubernetes Secrets as encryption.
- Java exceptions/stack traces, debug HTTP responses, and Spring Actuator env endpoints.
- CI/CD logs, GitHub Actions output, chat, and ticket systems.
- Unrestricted crash dumps, heap dumps, and debug shells.

For GitOps, use **external secret references** or managed secret encryption workflows. Self-managed ciphertext in Git is not safe if the decryption key sits in the same repository.

### 15.5. Image Pull Paths Differ from Pod Runtime Permissions

**`ImagePullBackOff`** may occur because the image-pulling identity lacks Artifact Registry Reader; this is **not necessarily** a missing role on **`orders-ksa`**.

On GKE, check the node service account, managed service agent, or pull identity per cluster version/mode. Never grant **`roles/artifactregistry.admin`** to `orders-ksa` just because a Pod fails to start.

### 15.6. Service Account Token Mounting Policies in Pods

Kubernetes provides **projected service account tokens** with expiration and audience for authenticating to the Kubernetes API. For Pods **that do not call the Kubernetes API**, consider setting **`automountServiceAccountToken: false`** in the Pod spec to shrink attack surface.

However, for Pods using **Workload Identity Federation**, verify token projection and metadata server requirements with GKE first. **Never blindly disable token mounting** assuming WIF will keep working; test actual workload identity after any change.

## 16. Audit Logging, Security, and Operational Performance

### 16.1. Inspect Three Distinct Sources

| Source | What It Shows | Where to Check |
|---|---|---|
| **Kubernetes Events** | CSI mount failures, scheduling, SecretSync/Pod errors | `kubectl describe pod`, `kubectl get events` |
| **Kubernetes API audit logs** | Who created/edited KSAs, Secrets, RoleBindings, Pods | GKE Cloud Logging audit logs per config |
| **Secret Manager audit logs** | Version accesses, IAM changes, permission errors | Cloud Audit Logs, Data Access logging per policy |
| **IAM policy / Policy Troubleshooter** | Why a principal was allowed or denied | IAM inheritance, deny policies, principal string |
| **Workload application logs** | ADC/SDK errors, reconnects, startup | Never log payloads or access tokens |
| **Cloud Monitoring** | Restart counts, 5xx, mount delays, quotas/latency | Per-environment SLO dashboards and alerts |

**Cloud Audit Logs Data Access** may require explicit enablement per service and policy, incurring ingestion/storage costs. Never assume every secret access is logged in detail unless auditing is configured.

### 16.2. Useful Alerts

- Spike in **`PERMISSION_DENIED`** after IAM changes.
- Mount/CSI **`FailedMount`** events or Pods stuck in **`ContainerCreating`**.
- GKE metadata server timeouts or ADC credential errors.
- Rising Secret Manager API errors, quota/rate-limit hits, or latency.
- Rotation published a new version yet the app still uses the old credential.
- New IAM binding granting **`secretAccessor`** to an overly broad `principalSet`.
- Unexpected changes to KSAs, RoleBindings, or IAM SA impersonation.
- Prolonged `ImagePullBackOff` after deployments.

Alerts should include **cluster, project, namespace, KSA, secret resource, version, and error code**, while never attaching plaintext secrets, tokens, or full payloads.

### 16.3. Performance and Cost

| Approach | Cost / Resource Drivers | Optimization |
|---|---|---|
| **Kubernetes Secret** | Cluster/control-plane storage, operational/security overhead | Never use in bulk as a general data store |
| **Secret Manager** | Active secret versions, access operations, replication/CMEK options | Do not fetch on every HTTP request; cache sensibly |
| **CSI add-on** | Pod mounts, API calls at mount/rotation, GKE resources | Tune rotation interval to need; avoid unnecessary refreshes |
| **SecretSync** | Sync operations and Kubernetes Secret objects | Enable only when legacy apps need it; clean up old copies |
| **WIF for GKE** | Token exchanges and related API calls per current quotas/pricing | Reuse SDK clients instead of instantiating per request |
| **Logging/Monitoring** | Log storage/queries, metrics, notifications | Tune log volume and retention to security/SLO needs |

Never assume every CSI refresh bills identically to a single Secret Manager API call in all cases; check **metrics, operation counts, and current pricing** when estimating TCO.

## 17. Troubleshooting by Symptom

| Symptom | Common Causes | First Checks |
|---|---|---|
| **`403 PERMISSION_DENIED`** calling Secret Manager | Wrong WIF principal, missing `secretAccessor`, IAM deny, or policy | Project number, namespace/KSA, secret IAM policy |
| **`403`** when impersonating GSA | Missing `roles/iam.workloadIdentityUser` or wrong annotation | KSA annotation, GSA IAM policy |
| App reports **`DefaultCredentialsError`** | ADC cannot reach GKE metadata server, broken env key path | `GOOGLE_APPLICATION_CREDENTIALS`, node pool, metadata server |
| **`FailedMount`** on CSI | Add-on disabled, bad `SecretProviderClass`, missing IAM, or missing version | `kubectl describe pod`, cluster add-on state, SPC `resourceName` |
| Pod runs on Standard node pool without WIF | Node pool still uses `GCE_METADATA` | `nodePools` `workloadMetadataConfig`, `GKE_METADATA` |
| Autopilot rejects WIF `nodeSelector` | Standard-only selector applied on Autopilot | Remove `iam.gke.io/gke-metadata-server-enabled` selector |
| `SecretProviderClass` created yet file missing | Pod not using the right CSI driver or wrong SPC name/namespace | Volume driver, provider `gke`, `kubectl get spc` |
| CSI file doesn't update on new version | Rotation disabled, older cluster version, or pinned version | Version support, flags, `versions/latest` |
| File updated yet Java uses old password | App reads once at startup; HikariCP holds old credentials | App reload, pool refresh, rollout |
| Kubernetes Secret env unchanged | Env vars never auto-refresh when Secret updates | Rolling restart or app reload mechanism |
| Kubernetes Secret `subPath` unchanged | `subPath` skips automatic updates | Mount directory directly; restructure volume mount |
| SecretSync doesn't create K8s Secret | GKE below 1.33, flag disabled, bad SecretSync/SPC/KSA | GKE version, sync flags, CRDs/events |
| Another KSA accesses prod secret | Overly broad IAM `principalSet`, node credentials, cross-cluster identity collision | Effective policy, identity sameness, `hostNetwork` |
| **`ImagePullBackOff`** | Registry auth / image URL / node pull identity | Artifact Registry reader, image digest, node/events |
| Java client receives `429`/`5xx` | Secret Manager quota/service/network or excessive polling | Retry/backoff, caching, quotas, Monitoring |
| Pod has WIF yet cannot call Cloud Storage | `secretAccessor` grants no Storage permissions | Add scoped bucket role, not Secret Admin |
| Another namespace cannot mount secret | `SecretProviderClass`/KSA in wrong namespace | Align namespace, KSA principal, and bindings |

### 17.1. Read-Only Commands to Use

~~~bash
# Confirm right cluster/namespace before any diagnosis
kubectl config current-context
kubectl get pod -n shop
kubectl get serviceaccount orders-ksa -n shop -o yaml
kubectl get secretproviderclass -n shop

kubectl describe pod orders-secret-test -n shop
kubectl get events -n shop --sort-by=.lastTimestamp

gcloud secrets get-iam-policy orders-db-password \
  --project=shop-dev-001

gcloud container clusters describe shop-gke \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --format="yaml(workloadIdentityConfig,addonsConfig.secretManagerConfig)"
~~~

**Never inject `cat`/print commands for secret payloads into centralized logs just to debug.** When payload inspection is strictly required, perform it in an authorized environment under confidential data rules and never store plaintext in tickets.

### 17.2. Isolate Errors by Layer

1. **Pod not starting:** image pull, scheduler, admission, PodSecurity.
2. **Pod creating yet volume fails to mount:** CSI driver, `SecretProviderClass`, GKE add-on, WIF/IAM.
3. **Pod running yet Google API returns 403:** identity principal, GSA impersonation, IAM role scope, IAM Deny/VPC SC.
4. **Secret read succeeds yet app fails:** version/format mismatch, credential at target service, Java reload/connection pool.
5. **Secret update has no effect:** rotation flags/version pinning, env vs. file, app caching.
6. **Fails only after deploying to another cluster:** identity sameness, cluster/nodepool WIF, region, namespace, IAM `projectNumber`.

## 18. Comprehensive Scenario: Java API, Cloud SQL, and Cloud Storage on GKE

**Minh Son** Enterprise runs two clusters:

- **`shop-staging`** in project **`shop-stg-001`**.
- **`shop-production`** in project **`shop-prod-001`**.

Applications:

- Java/Spring Boot **`orders-api`** reads a legacy DB secret from Secret Manager.
- Worker **`image-processor`** reads raw image buckets and writes optimized images.
- **Cloud SQL PostgreSQL** serves as the managed database; some services can use Cloud SQL IAM authentication instead of static passwords.
- Images are built in Cloud Build, stored in Artifact Registry, and deployed via an approved pipeline.

### 18.1. Proposed Diagram

~~~mermaid
flowchart LR
    DEV["CI/CD"] --> REG["Artifact Registry<br/>image by digest"]
    REG --> GKE["GKE Production"]
    GKE --> API["Pod orders-api<br/>KSA orders-ksa"]
    GKE --> IMG["Pod image-processor<br/>KSA images-ksa"]
    API --> WIF["WIF for GKE / IAM"]
    IMG --> WIF
    WIF --> SM["Secret Manager<br/>orders-db-password"]
    WIF --> ST["Cloud Storage<br/>image buckets"]
    API --> SQL["Cloud SQL PostgreSQL"]
    SEC["Kubernetes RBAC/PodSecurity"] --> GKE
    OBS["Cloud Logging/Monitoring"] --> GKE
~~~

### 18.2. Proposed Permissions

| Actor | Required Permissions | Do Not Grant by Default |
|---|---|---|
| `orders-ksa` | `secretAccessor` **on orders secret**; bucket Reader if API needs it | Secret Manager Admin, project-wide Storage Admin |
| `images-ksa` | Object Viewer on input bucket, Object Creator/User on output bucket per business logic | Permission to read DB passwords |
| CI publisher | Artifact Registry Writer on target image repo | Production runtime `secretAccessor` |
| Node/image-pull identity | Artifact Registry Reader per GKE mechanism | Application-level `secretAccessor` |
| Security team | Policy review and audit logs via appropriate roles | Plaintext secret read access if unnecessary |
| Rotation service account | Add versions / rotate credentials on scoped targets | Broad role across all secrets |

**Staging and production should live in separate projects** to isolate workload identity pools and eliminate cross-environment KSA principal collisions. Never share one project if clusters are administered by teams with different trust levels.

### 18.3. Secret Strategy

| Secret Type | Source | Pod Delivery | Rotation |
|---|---|---|---|
| Legacy DB password | Secret Manager | CSI mount or Java SDK | Add new version, coordinate DB credentials, app reload |
| Cloud Storage access | **No JSON key stored** | WIF + direct IAM | Short-lived Google tokens auto-refresh via ADC |
| Application TLS certificate | Secret Manager or approved certificate controller | File/CSI/Ingress mechanism | Renewal workflow and cert reload |
| Container registry credentials | No passwords in app Pods when GKE pull identity is used | Node/service agent, Artifact Registry IAM | Managed identity auth rotation |

### 18.4. Acceptance Test Matrix

| Test Case | Expected Result |
|---|---|
| `orders-ksa` reads `orders-db-password` | Succeeds |
| `orders-ksa` reads HR system secret | **`403`** |
| `images-ksa` reads orders DB password | **`403`** |
| Unprivileged KSA calls Secret Manager | **`403`** |
| Pod obtains credentials via WIF | No JSON key in image or Pod |
| CSI mounts into the right container | File exists; app reads without logging plaintext |
| New Secret Manager version added | CSI refreshes per version/interval when enabled |
| Java hasn't reloaded new file | Caught by tests; reload/rollout runbook covers it |
| User with Pod-read permissions only | Cannot view secret values |
| User with Pod-create rights in prod namespace | Tightly restricted due to indirect secret exposure |
| Deploy to staging cluster | Cannot reuse production's GKE WIF principal |
| Image pull after node rotation | Succeeds using proper Artifact Registry pull identity |
| Transient Secret Manager outage | App falls back via cache/backoff; SLO measured and alerted |

### 18.5. When to Choose Another Option?

- If a Java app only needs Google API permissions, **direct WIF + ADC** is simpler than managing passwords or JSON keys.
- If an app reads secrets only at startup and lacks reload logic, pair CSI mounts with controlled **rolling restarts** during rotation.
- If a Helm chart strictly requires **`secretKeyRef`** to a Kubernetes Secret, use **SecretSync** and harden RBAC/encryption.
- If strong isolation is required across untrusted teams, use **separate projects/clusters**, not just namespaces.
- If thousands of Pods fetch `latest` simultaneously at startup, evaluate rate limits, API retries, and caching to prevent thundering herds.

## 19. Applied Exercises

### Exercise A — Distinguishing Identity and Permissions

A Pod runs KSA **`shop/orders-ksa`** with a Kubernetes RBAC role to **list Pods**. Secret Manager secret **`orders-db-password`** has no IAM bindings yet.

**Question:** Can the Pod read Secret Manager? What must change?

**Answer:** No. Kubernetes RBAC does not grant Google Cloud permissions. Ensure WIF is enabled on cluster/nodes and grant **`roles/secretmanager.secretAccessor`** on that secret to the direct KSA principal (or use GSA impersonation with proper bindings).

### Exercise B — Spotting Overly Broad Permissions

A secret's IAM binding uses:

~~~text
principalSet://iam.googleapis.com/projects/123456789012/locations/global/workloadIdentityPools/shop-dev-001.svc.id.goog/namespace/shop
~~~

**Question:** Could this allow every Pod in namespace `shop` to read the secret? What should replace it?

**Answer:** Yes, that selector covers the entire namespace in the workload pool—broader than a single KSA. If only `orders-api` needs it, switch to **`principal://.../subject/ns/shop/sa/orders-ksa`** or a narrower selector.

### Exercise C — Direct IAM vs. Impersonation

A team annotated their KSA:

~~~text
iam.gke.io/gcp-service-account=orders-gsa@shop-dev-001.iam.gserviceaccount.com
~~~

yet Pods still get `403` when calling Secret Manager.

**Suggested Answer:** verify the **`roles/iam.workloadIdentityUser`** IAM binding for the KSA on the GSA, verify the GSA holds **`secretAccessor`** on the secret, check exact KSA namespace/name, and confirm the cluster/node pool uses WIF. The annotation alone is not enough.

### Exercise D — Secret Rotation

A secret is CSI-mounted with **`versions/latest`**, with default 120-second rotation enabled. Ten minutes after adding a new version, the file inside the Pod updated, yet Java still authenticates to the database with the old password.

**Question:** Is the bug in Secret Manager or the application?

**Answer:** Since the file updated, Secret Manager and CSI worked. Java likely read the file once at startup or its connection pool retained the old credential. Implement credential reloading or trigger a rollout; also verify the DB accepts the new password with overlap/rollback plans.

### Exercise E — SecretSync and Kubernetes Security

A Helm chart only supports **`env.valueFrom.secretKeyRef`**.

**Question:** Should you use the CSI add-on or SecretSync? Where does the secret live? Which permissions must be locked down?

**Answer:** Use SecretSync to materialize a Kubernetes Secret from Secret Manager on eligible GKE versions. Once synced, the secret resides in Kubernetes cluster state and Pod env vars; tighten RBAC, Pod-create/exec rights, namespace isolation, and encryption. Env vars will not auto-update, so plan restarts/reloads.

### Exercise F — Cross-Cluster Identity Sameness

Two clusters **`dev`** and **`prod`** share the same project, and both have namespace **`shop`** and KSA **`orders-ksa`**. IAM grants permissions to `subject/ns/shop/sa/orders-ksa`.

**Question:** Can `dev` inherit `prod` permissions? What are the mitigations?

**Answer:** Yes, there is real risk because namespace/KSA-based principals are shared across the project-level workload identity pool. Separate projects by trust boundary, use KSA UID or cluster-scoped selectors where applicable, restrict namespace/KSA creation, and audit effective access.

### Exercise G — Classifying Failures

| Symptom | First Investigation Step |
|---|---|
| Pod `Pending` or `ImagePullBackOff` | Scheduler, Artifact Registry pull identity, and image URL |
| Pod `ContainerCreating`, `FailedMount` | CSI driver/add-on, SPC, and IAM |
| Pod `Running`, Secret Manager API `403` | WIF principal, `secretAccessor` IAM, impersonation |
| CSI file updated yet env is stale | Env vars don't auto-refresh; restart app |
| Base64 Kubernetes Secret committed to Git | Secret compromised; revoke credential and scrub secret history per policy |
| Cannot read secret from Windows node | Managed CSI add-on does not support Windows Server nodes |

### Exercise H — Designing an Incident Runbook

Create a runbook for a leaked API key:

1. Who can revoke the key on the target service?
2. Which secrets and versions are affected?
3. How do you publish a new version in Secret Manager without logging plaintext?
4. Does GKE use SDK, CSI, or SecretSync, and how do rotation/reload work?
5. Who confirms all Pods transitioned to the new credential?
6. Could any KSA, GSA, node identity, or RBAC path allow re-exfiltrating the new key?
7. What alerts, audits, postmortem, and cleanup are required?

**Criterion:** do not stop at updating the value in Secret Manager; revoke the old credential at the target service, verify app health, tighten permissions, and audit logs.

## 20. Production Deployment Runbook

### 20.1. Before Making Changes

1. List **cluster/project/namespace/KSA**, node pools, and WIF status.
2. Verify exact **Secret Manager project/location/resource path**, secret versions, and principals.
3. Choose **direct IAM** or **GSA impersonation**; avoid granting both unnecessarily.
4. Confirm whether the app consumes secrets via **SDK, CSI, Kubernetes Secret, or SecretSync**.
5. Check GKE version/add-on/node OS limits and VPC SC policies.
6. Audit who can deploy Pods, exec, read Secrets, and edit KSAs/IAM.
7. Prepare **secret versions and a rollback plan**, never writing values into manifests or CI logs.

### 20.2. During Deployment

1. Create/grant the principal scoped to **a single secret** first.
2. Apply KSA and manifests in the **exact target namespace**.
3. Roll out staged workloads, monitoring events and readiness.
4. Run both happy-path tests and **unprivileged KSA negative tests**.
5. Confirm secrets work without appearing in logs or crash traces.
6. Record IAM changes, KSA/`serviceAccountName`, and `SecretProviderClass` version.

### 20.3. During Rotation

1. Issue the new credential on the target service and in Secret Manager.
2. If using **`latest`**, wait for the refresh interval; if version-pinned, roll out updated manifests cleanly.
3. Verify apps and connection pools adopt the new secret.
4. Canary roll out, then roll out cluster-wide with health checks.
5. Once migration is verified, revoke the old credential and disable/destroy old versions per policy.
6. Record audit trail, timestamps, versions, and SLO impact.

### 20.4. On 403 / FailedMount

1. Classify whether the error is image pull, CSI, Kubernetes RBAC, or IAM.
2. Identify the actual active principal instead of guessing from Pod name.
3. Verify GKE version, WIF pool, Standard node metadata mode, namespace/KSA/SPC.
4. Inspect secret IAM policy, IAM Deny/VPC SC, and Secret Manager API logs.
5. Apply the smallest targeted permission fix or roll back the latest change.
6. Never log plaintext secrets while debugging.

## 21. Summary and Reference Documentation

**Eight principles to remember:**

1. **Kubernetes RBAC** and **Google Cloud IAM** are two separate authorization layers; never conflate KSAs, IAM SAs, node SAs, and image-pull identities.
2. **Workload Identity Federation for GKE** lets Pods call Google APIs using short-lived credentials without JSON keys; Autopilot enables it automatically, while Standard requires checking both the cluster and node pools.
3. **Direct IAM on a KSA principal** is preferred when APIs support it; **GSA impersonation** is a compatibility path requiring both **`roles/iam.workloadIdentityUser`** and the KSA annotation.
4. **Kubernetes Secrets** are Kubernetes API objects; **base64 is not encryption**. GKE encrypts cluster data at rest, with optional Cloud KMS application-layer encryption.
5. **Secret Manager** provides centralized secret versions, IAM, and auditing; prefer the **SDK or GKE-managed CSI add-on** whenever the app supports it.
6. **SecretSync** helps apps strictly requiring Kubernetes Secrets, yet it **copies secrets into cluster state** and demands strict RBAC/namespace controls.
7. **Rotation does not finish when a Secret Manager version is added.** Files, env vars, Java memory, DB credentials, and active sessions must all transition per design.
8. **Least privilege, project separation, negative testing, audit logs, and runbooks** matter just as much as configuration commands.

**Official Google Cloud and Kubernetes Documentation:**

1. [About Workload Identity Federation for GKE](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/workload-identity) — pool/metadata server, IAM principal formats, identity sameness, and limitations.
2. [Authenticate to Google Cloud APIs from GKE workloads](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-identity) — `gcloud` cluster/node pool commands, direct principals, GSA impersonation, and KSA annotations.
3. [Use Secret Manager add-on with GKE](https://docs.cloud.google.com/secret-manager/docs/secret-manager-managed-csi-component) — CSI driver, `SecretProviderClass`, node limitations, and rotation.
4. [Synchronize secrets to Kubernetes Secrets](https://docs.cloud.google.com/secret-manager/docs/sync-k8-secrets) — `SecretSync` resource, GKE versions, sync/rotation.
5. [Access secrets in GKE using client libraries](https://docs.cloud.google.com/kubernetes-engine/docs/tutorials/workload-identity-secrets) — direct WIF secret access lab.
6. [Secret Manager best practices](https://docs.cloud.google.com/secret-manager/docs/best-practices) — rotation, version pinning, disable-before-destroy, and IAM.
7. [Secret Manager access control](https://docs.cloud.google.com/secret-manager/docs/access-control) — `secretAccessor` and IAM scope.
8. [Encrypt secrets at the application layer in GKE](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/encrypting-secrets) — Cloud KMS envelope encryption.
9. [Kubernetes Secrets](https://kubernetes.io/docs/concepts/configuration/secret/) — `data`/`stringData`, env/volume, RBAC, and 1 MiB limit.
10. [Good practices for Kubernetes Secrets](https://kubernetes.io/docs/concepts/security/secrets-good-practices/) — least privilege, access control, Pod escalation, and logging.
11. [Kubernetes Service Accounts](https://kubernetes.io/docs/concepts/security/service-accounts/) — identity tokens, `serviceAccountName`, and permissions.
12. [Kubernetes RBAC authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/) — Roles, RoleBindings, and access reviews.
13. [Cloud Storage IAM](https://docs.cloud.google.com/storage/docs/access-control/iam) — bucket-level IAM and workload principals.
