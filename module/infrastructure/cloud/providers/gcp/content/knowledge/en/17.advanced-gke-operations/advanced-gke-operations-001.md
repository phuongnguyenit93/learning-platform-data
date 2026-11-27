# Workload Identity Federation for GKE and Service Access

A Java service `orders-api` running on Google Kubernetes Engine (GKE) needs to read configuration from Secret Manager, download documents from Cloud Storage, and publish events through Pub/Sub. A simple but dangerous approach is creating a **JSON service account key**, baking it into the container or storing it in a Kubernetes Secret, and pointing `GOOGLE_APPLICATION_CREDENTIALS` to its path. If the key leaks, anyone holding it can use it outside the cluster until it is revoked; the operations team also has to manage the key's lifecycle and rotation.

**Workload Identity Federation for GKE** solves this by letting Pods use a **Kubernetes ServiceAccount (KSA) identity** to obtain **short-lived credentials** when calling Google Cloud APIs. There is no need to create or distribute IAM service account private keys to applications. Access is managed through **Google Cloud IAM** and can be scoped down to the exact bucket, secret, topic, or resource required.

This lesson belongs to the **Advanced GKE and Operations** chapter in the **CLOUD_PROVIDERS_GCP** module: exploring Google Cloud from projects, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage, and databases; working through deployment scenarios to protect resources, automate releases, and monitor reliability and cost.

After this lesson, you will be able to:

- Distinguish between a Kubernetes ServiceAccount, a Google Cloud IAM service account, a node service account, and a workload IAM principal.
- Explain the credential flow through the **GKE metadata server**, the Kubernetes API, and the **Security Token Service (STS)**.
- Choose between **direct resource access** (granting IAM directly to a KSA principal) and **IAM service account impersonation**.
- Configure Workload Identity Federation for GKE on **GKE Standard** and understand why **Autopilot** does not require manual enablement.
- Deploy a Java Pod that reads Cloud Storage using **Application Default Credentials (ADC)** without mounting a JSON key.
- Design cross-project access, protect against **identity sameness** across clusters, and manage IAM following the principle of least privilege.
- Diagnose `403` errors, metadata timeouts, NetworkPolicy issues, ImagePullBackOff, and quota limits.
- Prepare a migration from node credentials or JSON keys, including logging, rollback, and a production checklist.

> **Practice scope warning:** Project names, clusters, buckets, namespaces, IAM service accounts, and images in the examples are all placeholders. Modifying IAM or updating node pools can cause running workloads to lose access. Test in an authorized environment, review permissions, and have a rollback plan before executing changes.

## 1. The Problem: Which Identity Should a Pod Use to Call Google Cloud?

Suppose three applications share a cluster:

| Workload | Needs access to | Should not have permission to |
|---|---|---|
| `orders-api` | Read one configuration secret, read one documents bucket | Delete buckets, manage IAM, read HR data |
| `payment-worker` | Publish to one Pub/Sub topic | Subscribe to sensitive topics, create VMs |
| `report-generator` | Write to one reports bucket | Delete payment secrets, modify firewall rules |

If all three Pods use a **node service account** with broad permissions, compromising one Pod can expose the resources of other applications. If each application carries a JSON key, IAM scope can be narrowed, but you introduce the risk of **distributing or stealing long-lived private keys**.

Workload Identity Federation for GKE establishes a relationship between **a workload identity in Kubernetes** and **an IAM policy on Google Cloud services**. Applications receive short-lived tokens that carry only the permissions IAM grants to that principal or to the IAM service account it is allowed to impersonate.

### Four Frequently Confused Concepts

| Identity | Where is it defined? | What is it used for? |
|---|---|---|
| **Kubernetes ServiceAccount (KSA)** | Kubernetes API, scoped to a namespace | Identity for processes inside a Pod; used for Kubernetes and federation |
| **Federated IAM principal** | Workload identity pool managed by GKE in IAM | Represents a KSA so roles can be granted on Google Cloud resources |
| **IAM service account (GSA)** | Google Cloud IAM, email `name@project.iam.gserviceaccount.com` | Service account identity with IAM roles; can be impersonated by a KSA |
| **Node service account** | Attached to GKE node VMs | Used by the node and system agents to call APIs, such as pulling container images |

**A KSA is not automatically a GSA.** With **direct resource access**, the KSA has its own IAM principal and **does not require creating a GSA or a linking annotation**. With **impersonation**, the KSA is authorized to obtain tokens for a GSA via the IAM Credentials API; that requires both an IAM binding and a KSA annotation.

### Kubernetes RBAC Is Different from Google Cloud IAM

- **RBAC** controls operations against the Kubernetes API: listing Pods, creating Deployments, reading Kubernetes Secrets.
- **Google Cloud IAM** controls calls to Cloud Storage, Secret Manager, Pub/Sub, BigQuery, Cloud SQL Admin API, and many other services.
- A KSA with IAM `roles/storage.objectViewer` **does not automatically** gain permission to list Kubernetes Secrets.
- A user with Kubernetes `cluster-admin` **does not automatically have every IAM role** in every Google Cloud project. However, permission to create or modify Pods or KSAs can allow abuse of workload identities that already hold IAM permissions, so RBAC must be protected accordingly.

## 2. How Does Workload Identity Federation for GKE Work?

GKE manages a **workload identity pool** for the project named:

~~~text
PROJECT_ID.svc.id.goog
~~~

When a Pod uses a Google Cloud client library or the HTTP metadata endpoint to fetch credentials, the **GKE metadata server** on the node intercepts the request. It obtains a Kubernetes ServiceAccount token from the Kubernetes API and exchanges it via the **Security Token Service (STS)** for a short-lived **federated access token**.

~~~mermaid
sequenceDiagram
    participant APP as Java Pod (KSA)
    participant META as GKE metadata server
    participant K8S as Kubernetes API
    participant STS as Security Token Service
    participant API as Google Cloud API
    APP->>META: ADC requests access token
    META->>K8S: Request KSA token
    K8S-->>META: JWT with KSA identity
    META->>STS: Exchange JWT
    STS-->>META: Federated access token
    META-->>APP: Short-lived credential
    APP->>API: API request + bearer token
    API-->>APP: Result per IAM policy
~~~

**In the impersonation case:** after STS, the GKE metadata server also calls the **IAM Service Account Credentials API** to obtain an access token on behalf of the linked GSA. The Google Cloud API receives the token under the GSA identity; therefore, resource roles must be granted to the **GSA**, and the KSA must hold `roles/iam.workloadIdentityUser` on that GSA.

### Security Benefits and Limitations

- No JSON private keys need to be mounted in Pods or CI artifacts.
- Credentials have a limited lifetime and are typically **automatically refreshed by Google Cloud client libraries**.
- IAM roles can be finely scoped: one KSA can read objects in only one bucket, or publish to only one topic.
- When an IAM binding is revoked, new access is blocked subject to propagation and token lifetime; **revocation does not immediately invalidate every already-issued access token**.
- If a Pod is compromised, an attacker can use that KSA's permissions for as long as they control the Pod. Federation **does not replace** sandboxing, Pod Security, NetworkPolicy, and application security.

**Terminology:** GKE previously referred to this feature as **Workload Identity**. The current name **Workload Identity Federation for GKE** emphasizes federation and distinguishes it from Workload Identity Federation for self-managed Kubernetes, EKS, or AKS.

## 3. Two Permission Models: Direct and Impersonation

### Model A — Grant IAM Directly to the KSA Principal

~~~text
Pod (KSA: apps/orders-reader)
       │ federated credential
       ▼
IAM principal://.../subject/ns/apps/sa/orders-reader
       │ roles/storage.objectViewer on a bucket
       ▼
Cloud Storage bucket
~~~

When a Google Cloud API supports federated principals, grant the role **on the actual resource** to the KSA's principal. This is usually the **preferred** approach because it reduces the number of identities and intermediate IAM bindings; no GSA needs to be created.

### Model B — KSA Impersonates an IAM Service Account

~~~text
Pod (KSA: apps/orders-reader)
       │ Workload Identity User on GSA
       ▼
IAM service account: orders-reader@security-project.iam.gserviceaccount.com
       │ roles/storage.objectViewer on bucket
       ▼
Cloud Storage bucket
~~~

This requires **both** (1) an IAM binding for `roles/iam.workloadIdentityUser` on the GSA for the KSA and (2) the `iam.gke.io/gcp-service-account` annotation on the KSA. Having only one side will not work.

| Criterion | **Direct resource access** | **GSA impersonation** |
|---|---|---|
| Principal receiving IAM role on resource | IAM principal representing the KSA | GSA |
| Separate GSA required? | No | Yes |
| KSA annotation pointing to GSA required? | No | Yes |
| `iam.workloadIdentityUser` role required? | No | Yes |
| IAM configuration | Fewer layers | Adds a link between KSA and GSA |
| API support | Depends on whether the Google Cloud API/method accepts federated principals | Useful for APIs/methods that do not support direct access |
| Audit identity | Can be the federated KSA principal | Typically shows the GSA; delegation info must be checked to trace back to the KSA |
| Permission management | Role on resource for the specific KSA principal | Resource role for GSA plus impersonation permission |

**How to choose:** start with direct access when the Google Cloud API and operation type support it; use impersonation when a service account email identity is required, for signed URLs, for legacy APIs/clients, or for other limitations confirmed by the service documentation. Do not choose impersonation merely out of habit with `*.iam.gserviceaccount.com`.

## 4. IAM Principal Syntax and the Identity Sameness Issue

### A Specific KSA Principal

~~~text
principal://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/PROJECT_ID.svc.id.goog/subject/ns/NAMESPACE/sa/KSA_NAME
~~~

Explanation:

- `PROJECT_NUMBER` and `PROJECT_ID` belong to **the project containing the GKE cluster** and workload identity pool, **not necessarily the project containing the target bucket or secret**.
- `NAMESPACE` is the Kubernetes namespace, for example `apps`.
- `KSA_NAME` is the Kubernetes ServiceAccount name, for example `orders-reader`.
- `PROJECT_ID.svc.id.goog` is the pool name created by GKE; do not substitute an arbitrary custom IAM pool.
- The `principal://` prefix identifies **a single identity**; `principalSet://` identifies **a set of identities**.

Example with project number `123456789012` and project ID `platform-prod`:

~~~text
principal://iam.googleapis.com/projects/123456789012/locations/global/workloadIdentityPools/platform-prod.svc.id.goog/subject/ns/apps/sa/orders-reader
~~~

### Group Grants: Why Be Careful?

~~~text
# Every Pod in the same namespace, potentially across multiple clusters in the same project:
principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/PROJECT_ID.svc.id.goog/namespace/NAMESPACE

# Every Pod in a specific GKE cluster:
principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/PROJECT_ID.svc.id.goog/kubernetes.cluster/https://container.googleapis.com/v1/projects/PROJECT_ID/locations/LOCATION/clusters/CLUSTER_NAME
~~~

These two patterns serve different scenarios. For an application that only needs access to one bucket, **grant permissions to a specific KSA principal** rather than an entire namespace or cluster. A `principalSet` can easily grant unintended permissions when teams add new workloads.

### Identity Sameness Across Clusters in the Same Project

GKE creates the workload identity pool **at the project level**. If two clusters in the same project share the `apps` namespace and the `orders-reader` KSA, an IAM principal based on **namespace/name** treats them as the **same identity**, even though the Pods run in two different clusters!

~~~text
Project: platform-prod (pool platform-prod.svc.id.goog)
    ├── Cluster A: namespace apps, KSA orders-reader ─┐
    └── Cluster B: namespace apps, KSA orders-reader ─┴──> Same principal by name
                                                        │
                                                IAM bucket access
~~~

This is **identity sameness**. If Cluster B belongs to an untrusted group that can create a KSA with the same name, it can receive the same IAM role via the principal name.

Mitigation approaches:

1. **Separate clusters with different trust boundaries into different projects** so each has its own workload identity pool.
2. Use distinct namespace/KSA names when clusters need different permissions, and control who can create namespaces and KSAs.
3. For finer-grained requirements, use a principal based on **ServiceAccount UID**, a cluster-scoped `principalSet`, or context-aware IAM Conditions to restrict scope; consider the UID lifecycle when a KSA is deleted and recreated.
4. Do not allow untrusted users or teams to arbitrarily `create/edit Pod`, `ServiceAccount`, or `RoleBinding` in namespaces containing privileged IAM principals.

**Note:** Simply renaming a GKE cluster does not change the pool. When an IAM binding is based on namespace/KSA name, **it does not include the cluster name** in that identifier. Project-level isolation is part of workload identity security design.

## 5. Prerequisites and Preparation Before Configuration

To practice safely, prepare:

- A Google Cloud project containing the GKE cluster, with `container.googleapis.com` and billing enabled.
- An existing **GKE Autopilot or Standard cluster** with an appropriate version and network configuration.
- `gcloud`/`kubectl` authenticated with sufficient permissions to access the cluster and update IAM on the target resource.
- IAM permissions to manage clusters/ServiceAccounts when enabling the feature, such as `roles/container.admin` and `roles/iam.serviceAccountAdmin` for the responsible operator, plus permission to modify IAM on the bucket/secret/topic.
- Target APIs enabled; GKE documentation requires the **IAM Service Account Credentials API** (`iamcredentials.googleapis.com`) in setup instructions, which is especially important when impersonating a GSA.
- A lab Cloud Storage bucket or test resource **without sensitive data** for read-only permission testing.

**Caution:** Permissions to enable GKE features and grant IAM are used by the platform/security team, **not** by `orders-reader` at runtime. Never grant `roles/container.admin` or `roles/iam.serviceAccountAdmin` to a KSA just so an application can read objects.

### Autopilot vs. Standard

| Step | Dedicated GKE Autopilot cluster | GKE Standard cluster |
|---|---|---|
| Workload Identity Federation for GKE at cluster level | **Always enabled** | Must be enabled or verified |
| GKE metadata server on nodes | Managed by GKE | Node pools must use `GKE_METADATA` |
| Can you select a node pool without WIF enabled? | No under the standard Autopilot model | Yes if the cluster still has older node pools using `GCE_METADATA` |
| Pod `nodeSelector: iam.gke.io/gke-metadata-server-enabled` | **Do not use**; Autopilot may reject the selector | Can be used to schedule Pods onto nodes with the metadata server |
| IAM binding for KSA or GSA | Still must be created on the target resource | Still must be created on the target resource |

**Enabling WIF does not automatically grant Google Cloud API permissions.** A Pod still cannot read Cloud Storage without an IAM binding, even if the metadata server returns a token.

## 6. Enabling Workload Identity Federation on a Standard Cluster

Assume the Standard cluster already has a project and node pools. Using Bash/Cloud Shell:

~~~bash
CLUSTER_PROJECT="my-gke-lab-project"
CLUSTER="orders-standard"
LOCATION="asia-southeast1"
NODEPOOL="app-pool"

gcloud config set project "$CLUSTER_PROJECT"
gcloud services enable \
  container.googleapis.com \
  iamcredentials.googleapis.com

# Read-only: inspect the current pool.
gcloud container clusters describe "$CLUSTER" \
  --location="$LOCATION" \
  --format="value(workloadIdentityConfig.workloadPool)"

# Run ONLY when you have a plan to enable WIF on the Standard cluster.
gcloud container clusters update "$CLUSTER" \
  --location="$LOCATION" \
  --workload-pool="$CLUSTER_PROJECT.svc.id.goog"

# NEW: any node pool created after WIF is enabled on the cluster usually uses WIF.
# OLD: pre-existing node pools do not automatically change metadata mode.
gcloud container node-pools describe "$NODEPOOL" \
  --cluster="$CLUSTER" \
  --location="$LOCATION" \
  --format="value(config.workloadMetadataConfig.mode)"

# Update ONLY after verifying each workload no longer depends on the node SA.
gcloud container node-pools update "$NODEPOOL" \
  --cluster="$CLUSTER" \
  --location="$LOCATION" \
  --workload-metadata=GKE_METADATA
~~~

**Potential outage point:** Updating a node pool to `GKE_METADATA` prevents Pods on that node pool from **obtaining node service account credentials** the old way. If a workload still relies on node SA permissions, API calls may start returning `401/403`. Migrate one node pool at a time after granting roles to KSAs and testing applications.

When a Standard cluster has node pools using both `GCE_METADATA` and `GKE_METADATA`, Pods needing WIF must be scheduled onto the right node pool. You can add a `nodeSelector` to the **Pod spec**:

~~~yaml
spec:
  nodeSelector:
    iam.gke.io/gke-metadata-server-enabled: "true"
~~~

**Do not add this node selector in Autopilot.** On Standard, if you use a DaemonSet or Pods with other node affinity/taints, review scheduling compatibility. Certain Windows or host-networking configurations have specific limitations; verify before migrating workloads.

## 7. Lab A: KSA Reading Cloud Storage Directly via IAM

Goal: a Pod in namespace `apps` using KSA `orders-reader` is allowed to **list and read objects** in **only one lab bucket**. No GSA is created and no JSON key is used. Examples assume the cluster already has WIF enabled and the node pool (if Standard) has the GKE metadata server enabled.

### Step 1 — Identify the Cluster Project and Bucket Project

~~~bash
CLUSTER_PROJECT="my-gke-lab-project"
CLUSTER="orders-standard"
LOCATION="asia-southeast1"
NAMESPACE="apps"
KSA="orders-reader"

BUCKET="my-orders-documents-lab-unique"
# The bucket may live in another project; this is the BUCKET NAME, not a project ID.

gcloud config set project "$CLUSTER_PROJECT"
gcloud container clusters get-credentials "$CLUSTER" \
  --location="$LOCATION"

gcloud projects describe "$CLUSTER_PROJECT" \
  --format="value(projectNumber)"
~~~

Record the `PROJECT_NUMBER` returned by the command above. **Do not use the bucket project's project number** to build the principal if the bucket resides in a different project. The namespace and KSA belong to the cluster in `CLUSTER_PROJECT`'s workload identity pool.

### Step 2 — Create a Dedicated Namespace and KSA

~~~bash
kubectl create namespace "$NAMESPACE"
kubectl create serviceaccount "$KSA" \
  --namespace="$NAMESPACE"

kubectl get serviceaccount "$KSA" \
  --namespace="$NAMESPACE" \
  -o yaml
~~~

If the namespace or KSA already exists, `kubectl create` reports `AlreadyExists`; do not delete and recreate them just to make the command succeed. In production, declare Kubernetes ServiceAccounts via GitOps/Helm/Kustomize and align on namespace ownership.

Equivalent manifest:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-reader
  namespace: apps
~~~

**There is no `iam.gke.io/gcp-service-account` annotation** in the direct access model. The KSA is identified by its namespace and name in the federated principal.

### Step 3 — Build the Principal and Grant the Role on the Bucket

~~~bash
PROJECT_NUMBER="$(gcloud projects describe "$CLUSTER_PROJECT" \
  --format='value(projectNumber)')"

PRINCIPAL="principal://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$CLUSTER_PROJECT.svc.id.goog/subject/ns/$NAMESPACE/sa/$KSA"

# Grant Object Viewer only on the bucket that actually needs to be read.
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="$PRINCIPAL" \
  --role="roles/storage.objectViewer" \
  --condition=None

# Read back the IAM policy to confirm the member and scope.
gcloud storage buckets get-iam-policy "gs://$BUCKET"
~~~

This command **modifies the bucket's IAM** and requires permission to update the bucket IAM policy. If the policy already uses IAM Conditions, `--condition=None` indicates the new binding has no condition; do not overwrite or remove other bindings. Operators must verify that the bucket does not contain production data outside the lab's scope.

With the direct model, **you do not need**:

~~~text
gcloud iam service-accounts create ...
roles/iam.workloadIdentityUser
iam.gke.io/gcp-service-account
JSON service account key
~~~

### Step 4 — Attach the KSA to a Pod

A debug Pod using the Cloud SDK image strictly for practicing identity verification. Replace the image in this manifest if your organization uses a private registry mirror:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: wi-debug
  namespace: apps
spec:
  serviceAccountName: orders-reader
  # STANDARD ONLY: remove this nodeSelector on a dedicated Autopilot cluster.
  nodeSelector:
    iam.gke.io/gke-metadata-server-enabled: "true"
  containers:
    - name: debug
      image: gcr.io/google.com/cloudsdktool/google-cloud-cli:stable
      command: ["sh", "-c", "sleep 3600"]
      resources:
        requests:
          cpu: "500m"
          memory: "512Mi"
          ephemeral-storage: "100Mi"
~~~

For **Autopilot**, remove the entire `nodeSelector` field including the `iam.gke.io/gke-metadata-server-enabled` key; Autopilot manages the node metadata server automatically. On Standard, the selector only helps when a matching pool exists and has sufficient node capacity.

~~~bash
# Assuming the sample manifest above is temporarily saved on the lab machine as wi-debug.yaml.
kubectl apply -f wi-debug.yaml
kubectl -n apps get pod wi-debug -o wide
kubectl -n apps describe pod wi-debug
kubectl -n apps get pod wi-debug \
  -o jsonpath='{.spec.serviceAccountName}'
~~~

In this lab, do not copy the full YAML into a project repository if the current task only involves Markdown documentation. Learners execute these steps in an independent lab environment.

### Step 5 — Verify Access from Inside the Pod

~~~bash
# Check that the token endpoint responds, without printing the token to logs/terminal.
kubectl -n apps exec wi-debug -- sh -c \
  'curl -fsS -H "Metadata-Flavor: Google" \
    http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token \
    >/dev/null && echo "metadata token endpoint reachable"'

# Run gcloud inside the Pod to call Cloud Storage using discovered credentials.
kubectl -n apps exec wi-debug -- \
  gcloud storage ls "gs://$BUCKET"
~~~

Expected result: the metadata endpoint works and listing the bucket returns objects or succeeds if the bucket is empty. When granting a role to a direct principal, **only that exact KSA** has access; another Pod in the same namespace using the `default` KSA will not inherit access unless IAM grants it.

**Important distinction:** a successful metadata token response only proves credentials can be obtained; **it does not prove the bucket IAM role is right**. Running `gcloud storage ls` or an HTTP API call against the bucket is what actually verifies authorization.

If you need to test permission boundaries, use a second lab bucket without the role binding and expect `403` on access. Do not attempt to delete objects just to prove lack of write access, as that can cause unintended changes.

### Step 6 — Revoke Permissions When Finishing the Lab

~~~bash
# Remove only the exact binding that was added; do not alter other members' permissions.
gcloud storage buckets remove-iam-policy-binding "gs://$BUCKET" \
  --member="$PRINCIPAL" \
  --role="roles/storage.objectViewer" \
  --all

# Delete the lab Pod/ServiceAccount only when certain no one else uses them.
kubectl -n apps delete pod wi-debug
~~~

Do not delete the `apps` namespace or an entire production bucket just to clean up a lab exercise. Check IAM policies and Pods using the KSA before removing anything.

## 8. Java Applications Using Application Default Credentials

The most important takeaway for developers: **Java code does not need to parse KSA JWTs, call STS, or load private keys**. Google Cloud Java client libraries support **Application Default Credentials (ADC)** and automatically fetch tokens via the metadata server when running in a configured GKE cluster.

### Java Example Listing Cloud Storage Objects

Assuming the project declares a current JDK-compatible version of `com.google.cloud:google-cloud-storage`:

~~~java
import com.google.api.gax.paging.Page;
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

public final class ListOrders {
    public static void main(String[] args) {
        String bucket = System.getenv("ORDERS_BUCKET");
        if (bucket == null || bucket.isBlank()) {
            throw new IllegalArgumentException("ORDERS_BUCKET is required");
        }

        // ADC retrieves credentials from the GKE metadata server when running in a Pod.
        // Do not bundle a JSON key into the image or a Kubernetes Secret.
        Storage storage = StorageOptions.getDefaultInstance().getService();

        Page<Blob> page = storage.list(
            bucket,
            Storage.BlobListOption.prefix("incoming/")
        );
        for (Blob blob : page.iterateAll()) {
            System.out.println(blob.getName());
        }
    }
}
~~~

Key points to remember:

- Inside GKE, `StorageOptions.getDefaultInstance()` uses ADC and the credentials issued for the **KSA the Pod uses** or its linked GSA under impersonation.
- On a developer workstation, ADC may use user credentials from `gcloud auth application-default login`. That is a **different environment** and does not prove production Pods have the right IAM bindings.
- Do not set `GOOGLE_APPLICATION_CREDENTIALS` pointing to an old JSON key inside the Pod, because ADC may prioritize that key over the metadata server.
- Never log tokens, JWTs, raw metadata JSON, or secret values.
- For older client libraries, upgrade to versions that support reliable token refresh and federation.

### Sample Deployment

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: apps
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      serviceAccountName: orders-reader
      containers:
        - name: api
          image: asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-api:v1
          env:
            - name: ORDERS_BUCKET
              value: my-orders-documents-lab-unique
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            periodSeconds: 10
      # Standard with mixed node pools: place nodeSelector here if needed.
~~~

**The manifest is an example**: the Java image must exist and implement the corresponding `/ready` endpoint. If using Standard node pools mixing `GCE_METADATA` and `GKE_METADATA`, add `nodeSelector` under `spec.template.spec` of the Deployment; do not use that selector on Autopilot. If the application needs to publish to Pub/Sub or read Secret Manager, grant IAM on those specific resources instead of using Owner.

### Image Pull vs. Runtime Permissions

If a Pod enters `ImagePullBackOff` while pulling a private image from Artifact Registry, check the **node service account and its image-pull permissions**, registry/network configuration, and image tag. **Granting `roles/artifactregistry.reader` to the runtime KSA will not fix image pull errors**, because kubelet/the node pulls the image before the container can start.

## 9. Lab B: KSA Impersonating an IAM Service Account

Use this when an API service or workflow genuinely needs a GSA identity—for example, an API method that does not support direct federation, a legacy application requiring an IAM service account email, or signing operations unsupported by a federated principal. Keep the **KSA → GSA** mapping close to 1-to-1 for critical applications unless sharing has been explicitly evaluated.

Suppose:

~~~text
GKE cluster project: my-gke-lab-project
Namespace/KSA: apps/orders-reader
IAM SA project: my-security-project
IAM SA name: orders-runtime
IAM SA email: orders-runtime@my-security-project.iam.gserviceaccount.com
Target bucket: my-orders-documents-lab-unique
~~~

### Step 1 — Create the IAM Service Account

~~~bash
CLUSTER_PROJECT="my-gke-lab-project"
IAM_SA_PROJECT="my-security-project"
IAM_SA_NAME="orders-runtime"
NAMESPACE="apps"
KSA="orders-reader"
BUCKET="my-orders-documents-lab-unique"

GSA_EMAIL="$IAM_SA_NAME@$IAM_SA_PROJECT.iam.gserviceaccount.com"

# Run only if the service account does not exist yet and complies with org policy.
gcloud iam service-accounts create "$IAM_SA_NAME" \
  --project="$IAM_SA_PROJECT" \
  --display-name="Runtime for orders API"
~~~

### Step 2 — Grant Resource Permissions to the GSA

~~~bash
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$GSA_EMAIL" \
  --role="roles/storage.objectViewer" \
  --condition=None
~~~

The GSA is now allowed to read the bucket per IAM. However, **the KSA is not yet allowed to use the GSA** until a `WorkloadIdentityUser` binding exists.

### Step 3 — Allow the KSA to Impersonate the GSA

~~~bash
gcloud iam service-accounts add-iam-policy-binding "$GSA_EMAIL" \
  --project="$IAM_SA_PROJECT" \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:$CLUSTER_PROJECT.svc.id.goog[$NAMESPACE/$KSA]"
~~~

**Note the syntax:** in GKE KSA → GSA linking as documented, `--member` uses the format:

~~~text
serviceAccount:CLUSTER_PROJECT_ID.svc.id.goog[NAMESPACE/KSA_NAME]
~~~

This is **not the GSA email** and not the `principal://` syntax from the direct approach in section 7. Do not replace `CLUSTER_PROJECT` with `IAM_SA_PROJECT` if the two projects differ.

### Step 4 — Annotate the KSA

~~~bash
kubectl annotate serviceaccount "$KSA" \
  --namespace="$NAMESPACE" \
  "iam.gke.io/gcp-service-account=$GSA_EMAIL" \
  --overwrite

kubectl get serviceaccount "$KSA" \
  --namespace="$NAMESPACE" \
  -o yaml
~~~

With GitOps, place the annotation in the KSA manifest instead of patching manually:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-reader
  namespace: apps
  annotations:
    iam.gke.io/gcp-service-account: orders-runtime@my-security-project.iam.gserviceaccount.com
~~~

To work, **both the IAM binding and the annotation** must be present. If the annotation points to the wrong email, or the binding targets the wrong namespace/KSA, the metadata server cannot mint a GSA access token even though a direct federated token may still exist.

### Step 5 — Verify and Plan Rollback

~~~bash
gcloud iam service-accounts get-iam-policy "$GSA_EMAIL" \
  --project="$IAM_SA_PROJECT"

gcloud storage buckets get-iam-policy "gs://$BUCKET"
kubectl -n apps get serviceaccount "$KSA" -o yaml

# If Pods were created BEFORE the annotation changed, test with fresh Pods.
kubectl -n apps rollout restart deployment/orders-api
kubectl -n apps rollout status deployment/orders-api
~~~

`rollout restart` replaces Pods gradually; it can cause disruption if the Deployment has few replicas or misconfigured readiness/surge settings. In production, apply annotations and bindings through reviewed CI/CD pipelines and verify in staging first.

If IAM SA impersonation fails, check for `iam.serviceAccounts.getAccessToken denied` errors, the `WorkloadIdentityUser` binding, the annotation email, IAM propagation, and whether the Pod actually uses the configured KSA. Do not broadly grant `roles/iam.serviceAccountTokenCreator` or create a service account key just to bypass the error.

**Revocation:** remove the KSA annotation and `WorkloadIdentityUser` binding once the application has moved to a new setup, then remove resource IAM roles from the GSA if no consumers remain; do not delete a shared GSA without checking dependencies.

## 10. Cross-Project Access and Project Separation Principles

The GKE cluster, IAM service account, and Google Cloud resources do not have to live in the same project:

~~~text
Project A: gke-prod
  ├── GKE cluster
  └── Workload Identity pool: gke-prod.svc.id.goog
       └── KSA apps/orders-reader

Project B: data-prod
  ├── Cloud Storage bucket
  └── Secret Manager secret

Project C: identities-prod (optional)
  └── GSA orders-runtime@identities-prod.iam.gserviceaccount.com
~~~

**Direct:** the bucket/secret IAM policy in project B must reference the principal containing **A's project number and pool**. **Impersonation:** the GSA in C is granted resource permissions in B; the KSA in A is granted `roles/iam.workloadIdentityUser` on the GSA in C. IAM authorization can also be further constrained by Organization Policy, IAM Deny, Principal Access Boundary, or VPC Service Controls.

| Component | Value used to build principal/binding |
|---|---|
| GKE pool | `A_PROJECT_ID.svc.id.goog` |
| Principal URL project number | **Project A's number**, where the GKE cluster runs |
| IAM binding on resource | Specific bucket/secret/topic in **project B** |
| GSA email for impersonation | `name@C_PROJECT_ID.iam.gserviceaccount.com` |
| WorkloadIdentityUser member | `serviceAccount:A_PROJECT_ID.svc.id.goog[apps/orders-reader]` |

Avoid granting IAM at the **Organization** level or across all of project B when only one bucket is needed: broader roles mean a larger blast radius. Cross-project access still requires verifying VPC networking, Private Google Access, DNS, and policy perimeters; **IAM permission does not automatically create a network path** to the API.

## 11. Connecting Common Services with the Right IAM Roles

Suppose a Java service performs three tasks: reading files, reading secrets, and publishing events. Each permission should be granted on the specific resource:

| Service | Business permission | Reference IAM role | Notes |
|---|---|---|---|
| **Cloud Storage** | List/read objects | `roles/storage.objectViewer` | Grant on the bucket, not project-wide when unnecessary |
| **Secret Manager** | Read a secret version | `roles/secretmanager.secretAccessor` | Grant on the **specific secret**, not all secrets |
| **Pub/Sub** | Publish to a topic | `roles/pubsub.publisher` | Grant on the **specific topic** |
| **Pub/Sub** | Consume a subscription | `roles/pubsub.subscriber` | Grant on the required subscription |
| **Artifact Registry** | Pull container images | `roles/artifactregistry.reader` | Usually granted to the **node service account**, not the runtime KSA |
| **Cloud SQL** | Connect to instance via connector/Cloud SQL Auth Proxy | `roles/cloudsql.client` per supported resource/IAM type | Still requires **DB user/auth**, networking, and database configuration |
| **BigQuery** | Run queries and read datasets | `roles/bigquery.jobUser` plus appropriate dataset permissions | Two layers: project job role and dataset permissions |
| **Cloud KMS** | Use key to decrypt | `roles/cloudkms.cryptoKeyDecrypter` or equivalent narrow role | Grant on the exact key; protect decrypted data |

Example granting direct IAM on a Pub/Sub topic using the `PRINCIPAL` created in section 7:

~~~bash
TOPIC="orders-events"
TOPIC_PROJECT="my-events-project"

gcloud pubsub topics add-iam-policy-binding "$TOPIC" \
  --project="$TOPIC_PROJECT" \
  --member="$PRINCIPAL" \
  --role="roles/pubsub.publisher"
~~~

Example granting direct IAM on a Secret Manager secret:

~~~bash
SECRET="orders-api-config"
SECRET_PROJECT="my-secrets-project"

gcloud secrets add-iam-policy-binding "$SECRET" \
  --project="$SECRET_PROJECT" \
  --member="$PRINCIPAL" \
  --role="roles/secretmanager.secretAccessor"
~~~

These commands assume the APIs and resources already exist and that the service's IAM supports federated principals directly. For any specific product or API that does not yet support federation, check **supported products and limitations** and use GSA impersonation if appropriate. Do not assume every API, SDK version, and signed URL method supports direct principals.

### Cloud SQL Has an Additional Authentication Layer

A KSA/GSA with `roles/cloudsql.client` enables calling the Cloud SQL API/connector or establishing a supported connection, **not automatic database superuser access**. The application still needs a DB user or IAM DB authentication per the database engine, an IP/network path to the instance, connection pooling, and backup/HA setup. With the Cloud SQL Auth Proxy or Java Connector, use ADC via the metadata server instead of a JSON key, and protect DB credentials under a separate process.

### Signed URLs and APIs Requiring a GSA Email

Some URL-signing, byte-signing, or API calls require an **IAM service account email or private signing capability** rather than a pure federated principal. In those cases, evaluate **GSA impersonation and the IAM Credentials API** per the service documentation without exporting private keys to Pods. Signing permissions must be narrow and monitored; a **signed URL** grants read/write capability independently of the downloader's identity for its lifetime, so restrict expiration time, object scope, and HTTP methods.

## 12. Metadata Server, DNS, and NetworkPolicy

Applications using ADC on GKE typically request tokens from:

~~~text
http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token
http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token
~~~

To call the metadata server, HTTP requests require the header:

~~~http
Metadata-Flavor: Google
~~~

The **GKE metadata server** intercepts these requests and handles them according to the Pod's KSA. Not every **Compute Engine metadata server** endpoint exists on the GKE metadata server: only a subset for workload identity and certain cluster/node attributes is exposed. Querying an unsupported metadata field can return `404` even when IAM is configured correctly.

### Default-Deny Egress NetworkPolicy

If a namespace enforces a **NetworkPolicy** that blocks all egress, Pods may not reach the metadata server. According to GKE documentation:

- For standard GKE networking: allow egress to `169.254.169.252/32` on **TCP port 988**.
- For **GKE Dataplane V2**: allow egress to `169.254.169.254/32` on **TCP port 80**.

This requirement applies to the path to the GKE metadata server, **not** whitelisting the entire Internet. The exact policy depends on the CNI/Dataplane in use; check the cluster configuration before applying.

Example of a **dedicated** NetworkPolicy for Pods labeled `app=orders-api` in a GKE Dataplane V2 environment:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-gke-metadata
  namespace: apps
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes:
    - Egress
  egress:
    - to:
        - ipBlock:
            cidr: 169.254.169.254/32
      ports:
        - protocol: TCP
          port: 80
~~~

**Warning:** this example opens **only the single metadata flow** needed for GKE Dataplane V2; it does not open DNS, Cloud SQL, Google APIs, or general application traffic. In a namespace using default-deny, you must add **other policies** for DNS `53`, HTTPS `443`, databases, and required flows. This policy is **not equivalent** to the rule for environments using `169.254.169.252:988`.

### Nodes/Firewalls Must Reach STS

The metadata server on the node must connect to `sts.googleapis.com` over TCP 443 to exchange tokens. If a VPC has default-deny egress/firewall rules or routes traffic through an appliance that blocks STS, Pods may see `504 Gateway Timeout` or timeouts even when the local metadata endpoint is reachable.

When investigating, distinguish each hop:

~~~text
Pod → GKE metadata server (link-local / NetworkPolicy)
Node/metadata server → Google STS API (network/firewall/route)
Pod → Google Cloud resource API (network/firewall/DNS)
Google Cloud IAM → authorize or deny (IAM roles/conditions)
~~~

Network reachability to the target API and IAM roles are two **independent** requirements. A Pod with a valid token that cannot reach `storage.googleapis.com` still fails; a Pod that reaches the Storage API without Object Viewer still gets `403`.

## 13. Special Cases: hostNetwork, Service Mesh, and Token Refresh

### Pods Using hostNetwork

A Kubernetes Pod declaring:

~~~yaml
spec:
  hostNetwork: true
~~~

Typically, these Pods **do not use Workload Identity Federation for GKE** on the default path: GKE may route metadata requests from host-network Pods to the **Compute Engine metadata server**, exposing the node service account identity and permissions instead of the KSA identity.

**Specific exception:** the Cloud Storage FUSE CSI driver on certain newer GKE Standard versions provides a mechanism to authenticate KSAs for `hostNetwork: true` Pods (documented starting in **1.33.3-gke.1226000** when using the corresponding driver and configuration). Do not assume that exception applies to arbitrary hostNetwork applications.

**Safe practice:** avoid `hostNetwork` for normal applications; if a DaemonSet or agent must run with `hostNetwork`, separately audit its credential path, node SA, and node least privilege. Never assume node-level system agents use isolated KSAs the way application Pods do.

### Cloud Service Mesh / Istio Sidecar

If the application container starts before the sidecar proxy is ready, metadata requests can be refused or time out. With Istio and Cloud Service Mesh, you can configure the annotation:

~~~yaml
metadata:
  annotations:
    proxy.istio.io/config: '{ "holdApplicationUntilProxyStarts": true }'
~~~

Place this on the **Pod template metadata** per mesh documentation; verify your mesh version and Pod admission to ensure the annotation takes effect. In parallel, Java clients should **retry with backoff** when token retrieval fails at startup rather than crashing permanently on a single early failure.

### Token Lifetime and Caching

Federated and GSA access tokens are **short-lived**; GKE documentation notes a default access token lifetime of **1 hour**. The GKE metadata server caches tokens, and Google Cloud client libraries automatically refresh them before expiration.

- **Reuse client library objects** rather than creating a new credential or client for every data record or HTTP request.
- Do not store a token in an immutable application setting and reuse it indefinitely.
- Never log `Authorization: Bearer ...` or write tokens into Kubernetes ConfigMaps.
- For custom clients calling the metadata REST endpoint directly, check `expires_in` or expiry and refresh with backoff.
- When an IAM role has just changed, account for propagation and token caching before concluding whether the policy is effective.

The metadata server may need **a few seconds after Pod creation** before it begins responding. If credential requests fail during startup, use **retries** or an init container checking metadata readiness; do not disable TLS validation or fall back to static keys.

## 14. Least Privilege and Protecting Kubernetes ServiceAccounts

Workload Identity Federation for GKE provides a safer authorization mechanism than **distributing JSON keys**, yet overall security still depends on Kubernetes and IAM permissions.

### Isolate KSAs by Function

~~~text
Namespace: payments
  ├── KSA payment-api       → Secret Manager secret payment-config
  └── KSA payment-publisher → Pub/Sub topic payment-events

Namespace: reports
  └── KSA report-reader     → Cloud Storage bucket report-inputs
~~~

**Do not attach powerful roles to the `default` KSA** and let every Pod in the namespace use it. Every workload should explicitly specify `spec.serviceAccountName`; avoid sharing KSAs across application groups without a clear need and risk assessment.

### Defense-in-Depth Principles

| Layer | Control | Rationale |
|---|---|---|
| **IAM resource** | Grant roles on specific buckets/secrets/topics | Limits data readable/deletable if a Pod is compromised |
| **KSA identity** | Dedicated KSA per namespace/workload | Separates identities and simplifies auditing |
| **Kubernetes RBAC** | Restrict permission to create/modify Pods, KSAs, and RoleBindings | Prevents users from picking a privileged KSA to run a Pod |
| **Pod Security** | Restrict privileged containers, hostPath, and hostNetwork | Limits escalation via host/node |
| **NetworkPolicy** | Restrict ingress/egress while allowing metadata | Reduces exfiltration risk and auth failures |
| **IAM Conditions** | Restrict by time or resource attributes where supported | Narrows grant scope |
| **GKE project boundary** | Isolate untrusted clusters in separate projects | Prevents identity sameness |
| **Audit/Monitoring** | Track IAM policy changes, access failures, and identity usage | Detects unintended access |

A Pod with IAM permission to read sensitive secrets can still leak data through a vulnerable HTTP endpoint or SSRF; WIF does not stop an application from **sending credentials or secrets itself** to an attacker. Patch libraries, block SSRF, validate destination URLs, and control outbound traffic.

### Runtime Identity and Deployment Permissions

A developer or pipeline that only needs permission to update Deployments should not necessarily have permission to:

- Create or edit KSAs that already have powerful IAM roles.
- Change a Pod's `serviceAccountName` to another team's KSA.
- Create a `ClusterRoleBinding` with `cluster-admin`.
- Modify admission policies or NetworkPolicies to break network boundaries.

If a namespace is shared by multiple teams, RBAC and admission policies must restrict these actions. **An IAM role granted to a KSA is a security capability**, so govern KSAs like secrets or roles rather than treating them as decorative Pod metadata.

### IAM Conditions and Deny

Granting `roles/storage.objectViewer` directly on a bucket may be sufficient. If you must grant a role at the project level or temporarily during incident response, use **IAM Conditions** (where supported by the resource and attributes), such as expiration via `request.time`. In organizations using **IAM Deny**, **Principal Access Boundary**, or **VPC Service Controls**, an Allow binding alone may not suffice; evaluate full effective access.

## 15. Migrating from Node Service Accounts or JSON Keys

An older project may have many workloads using `GOOGLE_APPLICATION_CREDENTIALS=/var/secrets/key.json` or relying on the node service account. **Do not switch a node pool to `GKE_METADATA` before knowing which applications still depend on old credentials.**

### Recommended Migration Process

1. **Inventory:** list workloads, namespaces, KSAs, image versions, Kubernetes Secrets/volumes, node pools, and Google Cloud APIs called. Do not print private key contents to logs.
2. **Design permissions:** create dedicated KSAs per app, choose direct access or impersonation, catalog required IAM roles/resources; check cross-project and identity sameness concerns.
3. **Enable cluster-level WIF:** on Standard clusters; prefer creating a **new node pool with `GKE_METADATA`** to canary compatible applications.
4. **Assign resource IAM:** grant roles to KSA principals/GSAs first and wait for IAM propagation before shifting traffic.
5. **Update applications:** use Google Cloud Java client library versions supporting ADC; remove secret key mounts and `GOOGLE_APPLICATION_CREDENTIALS` once ready.
6. **Deploy canary:** test credentials, scoped read/write permissions, and behavior during restarts and scale-out on the new node pool or Autopilot.
7. **Roll out gradually:** roll out by namespace/workload; watch Google API error rates, token failures, and business metrics.
8. **Revoke old keys:** after confirming zero remaining dependencies, disable/delete service account keys per security policy; do not delete a GSA that still has valid consumers.
9. **Trim node SA permissions:** review excess roles, retaining permissions needed for image pulling, logging/monitoring, and node-level services.
10. **Document runbook/rollback:** define success criteria, failure modes, who is authorized to roll back, and completion criteria.

### Notes on Updating Node Pools

Switching an existing node pool to `GKE_METADATA` affects **every Pod on it immediately**. If only one workload is ready, create a **new node pool** and migrate in a controlled fashion before updating the old pool. A Standard cluster can temporarily run both node pool types; add explicit node selectors or affinity for migrated workloads.

Do not roll back by permanently reopening broad node metadata access in production. If an application requires an emergency rollback, it can temporarily use the older node pool under an approved incident plan, but **you must schedule remediation to return to WIF**. On **Autopilot**, WIF is always enabled and there is no Standard-style toggle to bypass authentication issues.

### GitOps and Deployment Order

~~~text
IAM roles and resource policies
  → Workload Identity Federation cluster/node pool
  → Namespace / KSA / annotation (if impersonation)
  → Deployment spec.serviceAccountName
  → Canary API access
  → Production traffic rollout
  → Remove old key mounts / revoke static keys
  → Audit effective permissions
~~~

In GitOps, **IAM bindings are often managed with Terraform** while KSAs and Deployments are managed via Kubernetes manifests. Enforce clear operational ordering: Terraform completing an IAM change does not guarantee instant propagation; CI/CD should run controlled retry checks rather than deploying immediately and assuming every `403` is a code bug.

## 16. Common Errors and Diagnostic Workflow

When a Pod fails to call a Google Cloud API, start by checking **which identity the Pod is actually using** and **which API returned the error**. Never blindly broaden IAM roles.

| Symptom | Possible cause | What to check |
|---|---|---|
| `403 PERMISSION_DENIED` reading bucket | Wrong project number in principal, missing role/bucket scope, or IAM Conditions | KSA, member in bucket policy, target resource |
| `iam.serviceAccounts.getAccessToken denied` | Missing `roles/iam.workloadIdentityUser` on GSA, wrong annotation, propagation delay | IAM SA policy, KSA annotation, wait for propagation |
| `401 UNAUTHENTICATED` | Failed to obtain token, expired token, misconfigured library/ADC | Metadata endpoint, client auth config, logs |
| Metadata timeout `169.254...` | Blocked by NetworkPolicy/Dataplane, server not ready, sidecar race | Metadata path, Pod startup, Istio |
| `504 Gateway Timeout` exchanging token | STS `443` blocked by firewall or egress routing error | Node/network path to `sts.googleapis.com` |
| `404` on a metadata attribute | GKE metadata server does not support that field | Metadata endpoint documentation |
| `ImagePullBackOff` | Node SA lacks Artifact Registry Reader or bad image/network | Node identity, registry, image tag |
| Works on Standard but fails on Autopilot | Node selector rejected or invalid Pod security/resource requests | Events, mode, and manifest |
| Another cluster can access the same bucket | Same namespace/KSA in the same WIF project pool | Identity sameness and IAM principal |
| GSA access works but signed URL fails | API/library requires signing capability/email unsupported by current token | GSA impersonation, IAM Credentials, signing permissions |
| Sudden failures after node pool update | Pods previously relied on node SA | Node pool `workloadMetadataConfig.mode`, migration |
| Token error right at Pod boot | Metadata server not yet ready | Retry/backoff or init readiness |
| Missing permissions cross-project | Binding placed in wrong target project or Organization Policy/Perimeter | Source/target projects, IAM, and VPC-SC |

### Step 1 — Verify the Cluster and Node Pool

~~~bash
CLUSTER="orders-standard"
LOCATION="asia-southeast1"
NODEPOOL="app-pool"
NAMESPACE="apps"
POD="orders-api-EXAMPLE"

gcloud container clusters describe "$CLUSTER" \
  --location="$LOCATION" \
  --format="value(workloadIdentityConfig.workloadPool)"

gcloud container node-pools describe "$NODEPOOL" \
  --cluster="$CLUSTER" \
  --location="$LOCATION" \
  --format="value(config.workloadMetadataConfig.mode)"

kubectl -n "$NAMESPACE" get pod "$POD" -o wide
kubectl -n "$NAMESPACE" describe pod "$POD"
kubectl -n "$NAMESPACE" get pod "$POD" \
  -o jsonpath='{.spec.serviceAccountName}'
~~~

On **Autopilot**, skip Standard-specific node pool checks; focus on the KSA, IAM, NetworkPolicy, and Pod events. If node mode is `GCE_METADATA` on Standard, that Pod is not yet on the expected WIF path.

### Step 2 — Inspect the KSA and Resource Roles

~~~bash
kubectl get serviceaccount orders-reader -n apps -o yaml
gcloud storage buckets get-iam-policy "gs://my-orders-documents-lab-unique"

# For impersonation only:
gcloud iam service-accounts get-iam-policy \
  orders-runtime@my-security-project.iam.gserviceaccount.com \
  --project=my-security-project
~~~

Verify that the member name uses the **correct project containing the GKE cluster**, namespace, and KSA. For impersonation, both the annotation and the `WorkloadIdentityUser` role must be present, and resource roles must be granted to the GSA rather than only the KSA.

### Step 3 — Test the Metadata Path Without Logging Tokens

~~~bash
# Run inside a lab Pod with curl; never print the access token to the terminal.
curl -sS --fail \
  -H 'Metadata-Flavor: Google' \
  'http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token' \
  >/dev/null && echo "token endpoint OK"
~~~

If metadata succeeds but the Google API still returns `403`, check **IAM**, resource scope, and API federation support first. If metadata fails, inspect **NetworkPolicy**, STS network reachability, node mode, Cloud Service Mesh, and the GKE metadata server.

### Step 4 — Check GKE Metadata Server Readiness

~~~bash
# Standard cluster: permission to view kube-system is required.
kubectl -n kube-system get pods -l k8s-app=gke-metadata-server

# When unsure of exact labels, run:
kubectl -n kube-system get pods
~~~

The GKE metadata server runs as a DaemonSet on Linux nodes (and the corresponding service on Windows). If the metadata Pod is OOMKilled/crashing or takes a few seconds to become ready, some auth requests can fail. Do not delete the Google-managed DaemonSet to "reset" it before diagnosing the root cause.

### Step 5 — Diagnose by Error Message

~~~text
Could not find default credentials
  → Is the app using ADC? Where is GOOGLE_APPLICATION_CREDENTIALS pointing?
  → Is metadata DNS/IP reachable? Is the node pool on GKE_METADATA?

403 from IAMCredentials.GenerateAccessToken
  → Is the GSA annotation correct? Does WorkloadIdentityUser match namespace/KSA?
  → IAM propagation, IAM Deny, or policy context?

403 from storage.googleapis.com
  → Correct bucket? roles/storage.objectViewer on that bucket?
  → Direct principal vs GSA? Does the bucket policy have the right member?

ImagePullBackOff
  → Kubelet/node SA + Artifact Registry access;
     DO NOT just tweak IAM on the runtime KSA.
~~~

To avoid confusing the two layers, always note **which API returned the 403**. IAM Credentials returning `403` when **generating a GSA token** is completely different from Cloud Storage returning `403` when **reading an object**.

## 17. Reliability, Quotas, and Performance of the Credential Path

Every Pod can call metadata to obtain an access token, but the **GKE metadata server does not have infinite capacity**. If an application constructs too many clients or requests a fresh token on every HTTP request, latency can spike or quotas can be hit.

Notable limits and behaviors from current GKE documentation:

| Component | Limit or behavior | Design guidance |
|---|---|---|
| **STS Exchange Token API** | Reference quota of **6,000 token exchanges/minute** per GKE docs, depending on current config/quota | Cache tokens, reuse client libraries, request quota increases with evidence |
| **GKE metadata server** | Up to **500 concurrent connections per node**; exceeding this can queue requests and cause `HTTP/499` on client timeout | Do not create new credential clients per request; monitor connections and latency |
| **Token lifetime** | Default around **3,600 seconds** | Reuse and refresh with backoff |
| **Pod startup** | Metadata server may not be ready in the first few seconds | Retry or use an init readiness check |
| **Large KSA counts** | Above roughly **3,000 KSAs in a cluster**, metadata server Pods may face memory pressure/OOM per docs | Split clusters / prune unused KSAs, monitor system Pods |
| **IAM binding propagation** | Role grants can take a few minutes to take effect | Wait and retry instead of adding broader roles |
| **Control plane unavailability** | Can impact the issuance of new tokens | Use HA control plane architectures, add retries/circuit breakers |

Thresholds vary by version and project quota; always verify **Quotas & System Limits** at operation time. Do not treat numbers in this article as SLA guarantees or committed throughput levels.

### Distinguishing STS and IAM Credentials Quotas

- **Direct resource access** primarily uses STS token exchanges.
- **GSA impersonation** additionally requires operations such as `GenerateAccessToken` or `GenerateIdToken` from the **IAM Service Account Credentials API**.
- GKE supports specifying a different **quota project** for certain IAM Credentials calls; this feature has version and permission prerequisites and does not raise quotas on downstream target services.

Example when shifting IAM Credentials quota to a dedicated project:

~~~bash
QUOTA_PROJECT="my-identity-quota-project"

# PROJECT_NUMBER and PRINCIPAL belong to the GKE cluster project.
gcloud projects add-iam-policy-binding "$QUOTA_PROJECT" \
  --member="$PRINCIPAL" \
  --role="roles/serviceusage.serviceUsageConsumer" \
  --condition=None

kubectl annotate serviceaccount orders-reader -n apps \
  "iam.gke.io/credential-quota-project=$QUOTA_PROJECT" \
  --overwrite
~~~

This is an optional setting for **IAM Service Account Credentials API quota** scenarios, not a mandatory step for every workload. Operators must verify `serviceusage.services.use` permission, which project is billed quota, and actual usage on the Quotas dashboard.

### Optimization Guidelines for Java Applications

1. Initialize Google Cloud Storage/Pub/Sub/Secret Manager clients once or a controlled number of times, reusing them via connection pools or managed singletons.
2. Rely on ADC with automatic refresh; do not call the metadata endpoint manually on every business request.
3. Implement retries with backoff and jitter for transient failures, but do not retry `PERMISSION_DENIED` indefinitely when policy is missing.
4. Set separate timeouts for metadata/token calls, target APIs, and downstream databases.
5. Monitor `request latency` and token errors after Pod scale-outs, node drains, and GKE upgrades.
6. Never log access tokens; log identity labels, operation names, and redacted error codes.

## 18. Cloud Audit Logs and Observing Actual Permissions

**Declared IAM permissions** and **actively used permissions** are not always identical. To narrow permissions based on real usage, inspect Cloud Audit Logs and application error metrics.

### Audit Checkpoints

| Source | What to observe |
|---|---|
| **IAM Cloud Audit Logs** | Who changed role bindings on resources/GSAs, and which conditional policies changed |
| **Target service Data Access logs** | Secret reads, object reads, and message publishes per service logging settings |
| **IAM Credentials API logs** | `GenerateAccessToken`/impersonation activity where logged |
| **GKE metadata server logs** | Token exchange failures, metadata path connectivity/availability |
| **GKE Kubernetes Audit Logs / events** | Who created/modified KSAs, Deployments, ServiceAccount annotations, and RBAC |
| **Application logs and Monitoring** | `401/403/429/5xx`, latency, retries, initialization failures |

In the **direct** model, Cloud Audit Logs can record the federated identity in `authenticationInfo.principalSubject` or equivalent service fields. In the **impersonation** model, some logs show the GSA as the acting principal along with delegation details. **Do not assume every service logs the exact same fields**; inspect real log entries from the API you use.

An illustrative Logs Explorer filter **for investigating authorization failures**:

~~~text
protoPayload.status.code=7
~~~

gRPC code `7` generally represents `PERMISSION_DENIED`; this filter does not automatically cover every application HTTP error. You can combine filters:

~~~text
protoPayload.serviceName="storage.googleapis.com"
protoPayload.status.code=7
~~~

If logs are missing, check the **project containing the target resource**, Logging viewer permissions, log types, and whether **Data Access Audit Logs** are enabled for that method. Do not enable unbounded Data Access logging everywhere without weighing sensitive data exposure and cost.

### Recommended Dashboards and Alerts

| Metric / signal | What it detects |
|---|---|
| `UNAUTHENTICATED`/`PERMISSION_DENIED` counts by workload | Misconfigured bindings or regressions during migration |
| STS/IAM Credentials API quota errors | Overloaded token refresh or low quota |
| Metadata latency/timeouts, unhealthy `gke-metadata-server` | Bottlenecks on the credential path |
| GKE Pod restarts and readiness failures | Applications failing to boot due to missing credentials |
| Count of KSA/GSA bindings and broad roles | Privilege creep, stale identities |
| Cloud Storage/Secret Manager access by KSA/GSA | Access outside the expected permission model |
| IAM policy changes outside CI/CD | Emergency changes, drift, or unauthorized modifications |

For traceability, applications should log `namespace`, workload name, API operation purpose, and correlation IDs **without secrets**. During IAM reviews, compare "granted roles" against "actually used permissions", then remove excess permissions using a reversible process.

## 19. Cost and Lifecycle Governance

A major benefit of Workload Identity Federation for GKE is reducing the risk and operational overhead of private keys. However, **it does not make GKE, Pub/Sub, or Storage APIs free**, nor does it eliminate all operational costs:

- **GKE:** cluster fees, nodes or Pods under Standard/Autopilot, logging, and networking.
- **Target Google Cloud APIs:** object/secret reads, Pub/Sub publishes, Cloud SQL connections, and data transfer.
- **IAM/STS/IAM Credentials:** managing token exchange quotas, client caching, and current limits; check specific pricing if any enabled capability carries charges.
- **Cloud Logging/Monitoring:** ingest, retention, and metric costs when collecting high event volumes.
- **CI/CD/GitOps:** maintaining Terraform IAM bindings, Kubernetes KSA manifests, and audits.

A Java service creating a new client per request can generate unnecessary token-exchange load and increase errors and latency. Proper client reuse and caching keep the system stable and reduce overhead.

**FinOps/ownership:** label applications and namespaces for GKE cost allocation, track service accounts by owner/team, and periodically delete unused bindings. Never leave a `"shared-runtime-admin"` GSA around for years with `Editor` across multiple projects merely for deployment convenience.

Cloud Billing budget alerts help catch abnormal spending, but **they do not automatically revoke IAM permissions**. IAM reviews, access monitoring, and change-management processes must still run independently.

## 20. Case Study: Three Java Services in an Order System

An enterprise runs a regional GKE cluster in project `gke-prod`, while data lives in separate projects:

~~~text
                         Google Kubernetes Engine
                         Project: gke-prod
                 Workload pool: gke-prod.svc.id.goog
                                  │
                 ┌────────────────┼────────────────┐
                 │                │                │
         namespace orders   namespace payments  namespace reports
         KSA orders-api     KSA payment-worker   KSA report-reader
                 │                │                │
                 ▼                ▼                ▼
         Secret Manager       Pub/Sub topic    Cloud Storage bucket
         orders-config        payment-events     report-inputs
         Project secrets-prod Project events-prod Project data-prod
~~~

### Initial Permissions

| KSA | Direct grant | Not granted |
|---|---|---|
| `orders/orders-api` | `roles/secretmanager.secretAccessor` on one secret | Read access to the entire Secret Manager project |
| `payments/payment-worker` | `roles/pubsub.publisher` on topic `payment-events` | `roles/pubsub.admin`, permission to delete topics |
| `reports/report-reader` | `roles/storage.objectViewer` on one bucket | `roles/storage.admin` |

The platform team enables WIF; the IAM/security team grants resource roles; application teams set `serviceAccountName` in their Deployments. Java code uses ADC; GitOps manages KSAs/Deployments, and Terraform manages IAM role bindings.

### Business Change: payment-worker Needs Signed URLs

If an API or SDK requires an IAM service account for signing, the Payments team creates a **dedicated GSA** `payment-signer@identities-prod.iam.gserviceaccount.com`, grants only the required signing resource permissions, gives KSA `payments/payment-worker` `roles/iam.workloadIdentityUser` on that GSA, and adds the annotation. The other services continue using direct federation.

Do not convert all three services to GSA impersonation just because one service needs signed URLs. A hybrid setup keeps IAM simpler for most applications while accommodating special requirements.

### Infrastructure Change: Creating a Staging Cluster in the Same Project

Another team creates an `orders` namespace and an identically named `orders-api` KSA in a staging cluster inside the **same `gke-prod` project**. With a direct principal keyed by namespace/KSA, staging can be treated as the same identity as production.

**Risk:** staging Pods could read the production secret if the new cluster does not share the same trust boundary. The preferred fix is placing staging in a **different project** (such as `gke-staging`), giving it a separate pool and granting access only to staging resources. Changing the KSA name reduces collisions too, but does not replace project-level trust isolation.

### Handling Mass 403s After a Node Pool Update

During a Standard node pool upgrade, an older application relying on the node SA breaks. Runbook:

1. Verify the node pool is on `GKE_METADATA` and the Pod uses a KSA with IAM roles.
2. Check whether errors come from the metadata server or the target Google Cloud API.
3. If a binding is missing, grant the proper resource role, wait for propagation, and retry a canary.
4. If the application still misuses JSON keys or ADC, fix the configuration or temporarily route to the old pool per the approved plan.
5. Track user-facing error metrics, SLOs, `401/403` counts, and time to recovery.
6. Complete the migration before stripping broad permissions from the node service account.

**Lesson from the scenario:** granting IAM to the right principal and right resource matters more than just "getting a token issued." WIF is a credential delivery mechanism; effective permissions, network paths, Pod governance, and application security determine whether the system is actually safe.

## 21. Production Deployment Checklist

### Identity and IAM Design

- [ ] Each workload needing distinct permissions has its own namespace/KSA and does not rely on the `default` KSA.
- [ ] Direct principals are chosen where APIs support them; GSA impersonation is used only when specifically needed.
- [ ] For direct access, principal URLs use the **project number and pool of the GKE cluster project**.
- [ ] For impersonation, both the **`WorkloadIdentityUser` IAM binding** and the **exact KSA annotation** are in place.
- [ ] IAM roles are scoped to specific buckets/secrets/topics/keys/resources, avoiding broad `Owner`/`Editor` grants.
- [ ] Multi-cluster setups in the same project are audited for **identity sameness**, trust boundaries, and KSA creation rights.
- [ ] Owners are assigned to revoke permissions and clean up obsolete KSAs and GSAs.

### GKE and Applications

- [ ] Autopilot always has WIF enabled; Standard clusters and node pools enable `GKE_METADATA` on schedule.
- [ ] Every Pod requiring WIF explicitly sets `serviceAccountName`.
- [ ] Standard mixed pools use appropriate selectors/affinity; Autopilot **does not set the metadata server `nodeSelector`**.
- [ ] Java SDKs use ADC without mounting static JSON keys via Kubernetes Secrets.
- [ ] Host-network Pods, service meshes, and system agents have their credential paths evaluated individually.
- [ ] The **node** image-pull identity retains appropriate Artifact Registry permissions.
- [ ] Metadata endpoints, DNS, STS `443`, and Google Cloud API egress are permitted by NetworkPolicy/VPC rules.
- [ ] Applications retry startup metadata token errors with backoff and refresh credentials automatically.

### Operations and Incident Response

- [ ] Tested accessing both permitted and denied resources from the target Pod/KSA.
- [ ] Dashboards exist for `401/403`, token failures, quotas, latency, and application SLOs.
- [ ] Cloud Audit Logs / IAM change logs and access logs are enabled at the necessary scope.
- [ ] Migrations never switch node pools en masse while Pods still depend on the node service account.
- [ ] Canary/rollback plans and procedures to delete static keys after cutover are in place.
- [ ] STS/IAM Credentials quotas, deployment regions, IAM propagation, and concurrency have been reviewed.
- [ ] API, logging, and node/Pod costs are reviewed; no ownerless identities remain.

## 22. Practice Exercises and Scenario Questions

### Exercise A — KSA Reading Exactly One Bucket

A team runs `report-service` in namespace `analytics` on a GKE Standard cluster in project `gke-learning`; the bucket `reports-private-lab` lives in another project.

1. Write the commands to inspect the cluster workload pool and node pool metadata mode.
2. Create KSA `report-reader` and a Deployment referencing this `serviceAccountName`.
3. Construct a direct principal URL using **gke-learning**'s project number, not the bucket project's number.
4. Grant `roles/storage.objectViewer` on **only the target bucket**.
5. Test both the metadata token endpoint and reading an object; explain why these two tests differ.
6. Describe how to revoke permissions when the team moves to a new bucket without deleting the data bucket.

### Exercise B — Choosing Impersonation When a Service Account Is Needed

Application `invoice-api` needs to generate signed URLs, and the current SDK requires an IAM service account email:

1. Explain why GSA impersonation may be required instead of a direct principal.
2. Write the commands to create a GSA in project `identity-prod` and grant resource permissions in project `billing-prod`.
3. Write the `roles/iam.workloadIdentityUser` binding for KSA `invoices/invoice-api`.
4. Add the `iam.gke.io/gcp-service-account` annotation and explain what happens if it is omitted.
5. Contrast two `403` errors: a `GenerateAccessToken` failure vs. a Cloud Storage access failure, and describe separate checks for each.

### Exercise C — Identity Sameness and Trust Boundaries

Two clusters `gke-prod-a` and `gke-test-b` in the same project `team-platform` both have namespace `orders` and KSA `orders-api`.

1. Explain why both workloads can resolve to the **same principal** when IAM bindings rely on namespace/name.
2. Identify the risk when an admin of the test cluster can create new Pods.
3. Propose three ways to reduce the risk; explain why **project separation** is generally strongest.
4. Distinguish between `principal://.../subject/ns/.../sa/...` and `principalSet://.../namespace/...`.
5. If a KSA is deleted and recreated with the same name, how do name-based and UID-based principals differ?

### Exercise D — Post-Migration Incident

A Java service reading from Pub/Sub starts failing a few minutes after a node pool switches to `GKE_METADATA`. Pods have the right `serviceAccountName`, yet application logs show both `403` errors and metadata timeouts:

1. Which commands inspect the node pool, KSA, and Pod scheduling?
2. If errors come from `iamcredentials.googleapis.com`, which IAM binding might be missing?
3. If metadata does not respond, which IP and port must NetworkPolicy allow on GKE Dataplane V2?
4. Why must STS egress on port `443` remain open even though the metadata endpoint uses a link-local IP?
5. If an IAM binding was just added and `403` errors persist, how should you factor in IAM propagation and token caching?
6. State controlled rollback criteria and steps to avoid reverting to JSON keys.

### Exercise E — Java and Authentication Performance

A Java worker creates a new Cloud Storage client for **every Pub/Sub message** and logs the full access token on error.

1. Identify the security and performance risks.
2. Write how to initialize the client once using ADC.
3. Explain the metadata server concurrent connection limit and token refresh behavior.
4. Propose metrics to monitor `403`, `429`, metadata latency, and Cloud Storage operations.
5. Propose strategies for log redaction, IAM role reviews, and managing quota projects if needed.

**Synthesis question:** If a Pod successfully obtains a federated token but cannot read `gs://orders-prod`, distinguish at least four possibilities: (1) wrong principal/binding; (2) IAM Deny/Conditions; (3) the Google Cloud API does not support direct federation for the called operation; (4) broken network/API path. Explain how to verify each possibility before deciding to switch from direct access to impersonation.

## Official References

- [About Workload Identity Federation for GKE](https://cloud.google.com/kubernetes-engine/docs/concepts/workload-identity) — architecture, token flow, principal identifiers, and identity sameness.
- [Authenticate to Google Cloud APIs from GKE workloads](https://cloud.google.com/kubernetes-engine/docs/how-to/workload-identity) — enabling WIF on Standard, granting direct IAM, KSA-GSA linking, and verification.
- [Troubleshoot GKE authentication issues](https://cloud.google.com/kubernetes-engine/docs/troubleshooting/authentication) — IAM 403s, NetworkPolicy, metadata timeouts, quotas, and node pools.
- [Best practices for hardening GKE security](https://cloud.google.com/kubernetes-engine/docs/how-to/hardening-your-cluster) — KSA isolation, IAM least privilege, and guardrails.
- [IAM principal identifiers for GKE](https://cloud.google.com/kubernetes-engine/docs/concepts/workload-identity#principal-identifiers) — `principal://` and `principalSet://`.
- [IAM Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation) — federation concepts and short-lived credentials.
- [Google Cloud Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials) — credential resolution order in client libraries.
- [Cloud Storage IAM roles](https://cloud.google.com/storage/docs/access-control/iam-roles) — Object Viewer and bucket-level IAM grants.
- [Secret Manager access control](https://cloud.google.com/secret-manager/docs/access-control) — permissions for accessing secret versions.
- [Pub/Sub access control with IAM](https://cloud.google.com/pubsub/docs/access-control) — Publisher/Subscriber roles per topic/subscription.
- [IAM service account impersonation](https://cloud.google.com/iam/docs/service-account-impersonation) — impersonation and delegation controls.
- [Cloud SQL connector authentication](https://cloud.google.com/sql/docs/mysql/connect-connectors) — IAM/ADC, networking, and database authentication.
- [Cloud Audit Logs overview](https://cloud.google.com/logging/docs/audit) — tracing access and IAM changes.
- [GKE pricing](https://cloud.google.com/kubernetes-engine/pricing) — cluster, node, Pod, and dependent resource costs.
