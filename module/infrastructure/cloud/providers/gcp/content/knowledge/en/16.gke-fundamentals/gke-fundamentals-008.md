# Deploying Deployments, Services, and ConfigMaps on GKE

> **Chapter:** GKE Fundamentals  
> **Module:** **CLOUD_PROVIDERS_GCP** — Exploring Google Cloud from project organization, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage services, and databases. Through practical deployment scenarios, learners learn how to choose services, secure resources, automate releases, and monitor reliability and cost.

A development team has packaged an application into a container image and stored it in Artifact Registry. The next step is running multiple replicas on Google Kubernetes Engine (GKE), providing a stable access address for Pods, and changing configuration without rebuilding the image for each environment. The three core Kubernetes resources in this scenario are **Deployment**, **Service**, and **ConfigMap**.

This lesson moves from concepts to an executable lab: creating a dedicated namespace, declaring a ConfigMap for a sample web page, running two Pods via a Deployment, routing traffic to Pods via a ClusterIP Service, testing, updating, rolling back, and cleaning up resources. Subsequent sections expand into **GKE Autopilot/Standard, Artifact Registry, IAM, network exposure, probes, Java applications, and cost**.

**Safety boundary:** commands that create GKE clusters, LoadBalancers, or storage can incur real charges. Use an authorized learning project/cluster, verify your kubeconfig context before any mutating command, and never apply demo manifests to a production namespace.

## Learning Objectives

After this lesson, learners will be able to:

1. Describe the roles of **Pod, ReplicaSet, Deployment, Service, and ConfigMap**, and how objects link via labels/selectors.
2. Choose between GKE **Autopilot** and **Standard** based on infrastructure management needs.
3. Prepare the right **project, cluster, location, kubeconfig context, IAM, and namespace**.
4. Write YAML for a **ConfigMap**, a **Deployment** with resource requests, health probes, and RollingUpdate, and a **ClusterIP Service**.
5. Use **`kubectl apply`, `get`, `describe`, `logs`, `rollout status/history/undo`, and `port-forward`** to validate an application.
6. Distinguish **Service `port`, `targetPort`, `containerPort`**, EndpointSlices, and Service DNS.
7. Understand that ConfigMap **env vars do not auto-update in running Pods**, whereas mounted volumes update after a sync delay and `subPath` mounts do not auto-update.
8. Know when to use **LoadBalancer/Ingress/Gateway**, how to limit public exposure, and how to control costs.
9. Troubleshoot **`ImagePullBackOff`, `CrashLoopBackOff`, `Pending`, failing readiness probes, mismatched selectors, and missing ConfigMaps**.
10. Design controlled config changes, rollbacks, and protections for Java workloads on GKE.

## 1. Three Core Resources and Related Layers

| Resource | Responsibility | What It Does Not Do Alone |
|---|---|---|
| **ConfigMap** | Holds non-sensitive key/value or file configuration | Does not encrypt secrets or run applications |
| **Deployment** | Declares Pod replica count and update/recovery strategy for stateless workloads | Does not create Service DNS or a public IP |
| **ReplicaSet** | Maintains target Pod count for a Deployment | Does not replace Deployment as the usual rollout API |
| **Pod** | Smallest deployable unit; holds one or more containers | Has no permanent IP/identity across recreations |
| **Service** | Provides a stable endpoint and matches Pods via selector | Does not change replica count or fix unready apps |
| **EndpointSlice** | Tracks Pod endpoints ready to serve a Service | Not something beginners should hand-edit when a Service has a selector |
| **Namespace** | Groups and isolates logical names/permissions in a cluster | Does not create a network firewall or Google Cloud IAM project boundary |
| **Ingress/Gateway** | Manages HTTP(S) routing, TLS, and policies via controllers | Not equivalent to a Layer 4 LoadBalancer Service |

~~~mermaid
flowchart TD
    USER["In-cluster client"] --> DNS["Kubernetes DNS\nweb-demo.gke-lab.svc.cluster.local"]
    DNS --> SVC["Service: web-demo\nClusterIP, TCP 8080"]
    SVC --> ES["EndpointSlices\nReady Pod IPs"]
    ES --> P1["Pod A: nginx\nport 80"]
    ES --> P2["Pod B: nginx\nport 80"]
    DEP["Deployment: web-demo\nreplicas = 2"] --> RS["ReplicaSet"]
    RS --> P1
    RS --> P2
    CM["ConfigMap: web-demo-config"] -. "env / mounted file" .-> P1
    CM -. "env / mounted file" .-> P2
~~~

**Control flow differs from data flow:** the Deployment controller creates and maintains Pods via a ReplicaSet; the Service selects endpoints to route traffic to Pods. ConfigMaps are injected into containers by kubelet as configured. Kubernetes does not enforce a strict creation order, yet if a Deployment references a nonexistent ConfigMap, Pods will fail to start.

### 1.1. Where Does GKE Differ from Upstream Kubernetes?

Kubernetes defines the Deployment, Service, and ConfigMap APIs and core controllers. **GKE** runs Kubernetes on Google Cloud with a managed control plane, integrated VPC networking, Compute Engine infrastructure, Artifact Registry, Cloud Logging/Monitoring, IAM, and Load Balancing integrations.

| GKE Mode | Infrastructure Management | Best Fit |
|---|---|---|
| **Autopilot** | GKE manages worker nodes and most infrastructure settings; adjusts resource requests to compute class bounds | Teams wanting to focus on apps with minimal node operations |
| **Standard** | Teams manage node pools and more infrastructure settings, though GKE still manages the control plane | Specialized node, hardware, daemon, or operational requirements |

Both support Kubernetes Deployments, Services, and ConfigMaps. In a lab, reusing an **existing cluster** is cheaper and lower-risk than creating a new cluster. If creating one, this lesson uses Autopilot to focus on the three core objects. Cluster mode, node pool behavior, and Autopilot limits evolve across versions; inspect existing cluster state before deploying workloads.

### 1.2. Stateless Does Not Mean "Has No Data"

Deployments fit web/API services whose critical state lives **durably outside the Pod** (Cloud SQL, Firestore, Cloud Storage, Pub/Sub, etc.) or uses safe cache/retry designs. Never use a Deployment with ephemeral Pod filesystems as the sole copy of user uploads, databases, or transactions.

When Pods are replaced during a rollout, local data in the container writable layer or `emptyDir` can vanish. If you need persistent per-Pod identity and storage, learn **StatefulSets** and PersistentVolumes rather than forcing a Deployment to act like a database cluster.

## 2. Lab Scenario, Assumptions, and Pass Criteria

We will deploy a minimal HTTP page using **nginx** on GKE. Nginx is convenient for demonstration because it immediately serves content from a file mounted via ConfigMap without requiring a custom image build first. Later sections extend the same principles to **Java/Spring Boot** and private images in Artifact Registry.

| Component | Illustrative Value |
|---|---|
| Google Cloud project | `YOUR_PROJECT_ID` |
| GKE cluster | `gke-app-lab` (or assigned cluster) |
| Location | `asia-southeast1` (region; adjust to actual cluster) |
| Namespace | `gke-lab` |
| ConfigMap | `web-demo-config` |
| Deployment | `web-demo` |
| Replicas | `2` |
| Container image | `nginx:stable-alpine` (lab use only) |
| Container listening port | `80/TCP` |
| Service name/type | `web-demo` / `ClusterIP` |
| Service port | `8080/TCP` |
| Service targetPort | `http` (named container port = 80) |
| Local port-forward | `localhost:8080` |
| Web page | `index.html` value from ConfigMap |

**Expected observations:**

1. Namespace **`gke-lab`** exists in the right cluster.
2. ConfigMap holds key **`APP_MESSAGE`** and file **`index.html`**.
3. Deployment reaches **2/2 Ready** once the scheduler has capacity and probes pass.
4. Service **`web-demo`** receives a ClusterIP and endpoints for the two matching-label Pods.
5. **`kubectl port-forward`** and an in-cluster Pod test return HTTP 200 and the page contents.
6. Updating the ConfigMap updates the mounted file after sync latency, while **`APP_MESSAGE`** as an env var inside running containers **does not change automatically**.
7. A rollout restart replaces Pods, loads the new environment variable, and returns replicas to 2/2.

**Note:** `nginx:stable-alpine` is a mutable tag over time. In production, build and scan images, store them in Artifact Registry, and **pin by immutable digest**. A public lab image does not cover supply-chain security.

## 3. Preflight: Project, APIs, Permissions, and kubeconfig

### 3.1. Read-Only: Check GCP Context

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
LOCATION="asia-southeast1"
CLUSTER="gke-app-lab"
NAMESPACE="gke-lab"

gcloud auth list
gcloud config list
gcloud projects describe "$PROJECT_ID"

# Check enabled APIs; do not alter production blindly.
gcloud services list --enabled --project="$PROJECT_ID" \
  --filter="name:container.googleapis.com"

# List viewable clusters.
gcloud container clusters list --project="$PROJECT_ID"

# Inspect the target cluster.
gcloud container clusters describe "$CLUSTER" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --format="yaml(name,location,status,autopilot,network,subnetwork)"
~~~

**Do not guess the location.** A GKE cluster may be zonal or regional; pass **`--location`** matching the discovered value. Inspecting in-cluster resources also requires Kubernetes API authorization and network connectivity to the control plane.

### 3.2. If No Lab Cluster Exists Yet

~~~bash
# MUTATING + INCURS COST: run only in an authorized lab project.
# APIs must be enabled; account needs permissions to create a GKE cluster,
# infrastructure/network/quotas, and IAM per GKE requirements.
gcloud container clusters create-auto "$CLUSTER" \
  --project="$PROJECT_ID" \
  --location="$LOCATION"
~~~

**Cluster creation takes time and incurs real charges.** Networking defaults, release channel, node service account, and security posture must comply with organizational policy. In production, specify a least-privilege node service account instead of relying on broad defaults. Having permission to create a cluster does not guarantee permissions to create LoadBalancers, pull private images, or reach Cloud SQL.

### 3.3. Connect kubectl to the Cluster

~~~bash
# WRITES LOCAL kubeconfig; does not create a Deployment.
gcloud container clusters get-credentials "$CLUSTER" \
  --project="$PROJECT_ID" \
  --location="$LOCATION"

# READ-ONLY — always verify context before apply/delete.
kubectl config current-context
kubectl config get-contexts
kubectl cluster-info
kubectl get namespaces
~~~

GKE may require **`gke-gcloud-auth-plugin`** matching your `gcloud`/`kubectl` versions. `get-credentials` updates your machine's kubeconfig; if working across multiple projects, **`kubectl` could point at the wrong cluster**. In production operations, specify explicit contexts or verify them in change tickets.

**IAM permissions and Kubernetes RBAC are separate:** IAM authorizes Google Cloud cluster actions/authentication; creating Deployments, Services, or ConfigMaps in a namespace also requires Kubernetes RBAC or GKE authorization. Never grant Cluster Admin to every developer just to silence Forbidden errors.

### 3.4. Create a Dedicated Namespace (Modifies Cluster)

~~~bash
# MUTATING — only in the lab cluster on the right context.
kubectl create namespace "$NAMESPACE"

# READ-ONLY — verify.
kubectl get namespace "$NAMESPACE"
kubectl get all -n "$NAMESPACE"
~~~

If the namespace already exists, run **`kubectl get namespace`** instead of recreating it. Namespaces separate resource names and RBAC, **not network traffic between namespaces**; isolating traffic requires NetworkPolicy or other GKE network controls.

## 4. Kubernetes YAML and Declarative Principles

An object manifest typically contains:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-demo
  namespace: gke-lab
spec:
  # Desired state that the controller will maintain
  replicas: 2
~~~

- **`apiVersion`**: API group and version.
- **`kind`**: resource type.
- **`metadata`**: name, namespace, labels, annotations.
- **`spec`**: desired state, such as Pod count and Pod template.
- **`status`**: actual state maintained by the control plane; **never hand-populate this in manifests**.

**`kubectl apply`** submits declarative configuration to the Kubernetes API, after which controllers reconcile actual state toward `spec`. Seeing **configured/created** only confirms the API accepted the object; it does not guarantee Pods are Running, images pulled, Service endpoints exist, or the app is healthy.

### 4.1. Labels and Selectors Are the Contract Between Deployment and Service

For example, both Deployment and Service agree on labels:

~~~yaml
app.kubernetes.io/name: web-demo
app.kubernetes.io/part-of: gke-lab
~~~

Deployment **`spec.selector.matchLabels`** must match **`spec.template.metadata.labels`**. A Deployment selector is effectively immutable after creation; changing it requires a planned migration or recreation rather than ad-hoc edits.

Service **`spec.selector`** must match actual Pod labels. If the selector is wrong, the Service still gets a ClusterIP and DNS name, yet **has no matching endpoints**, causing timeouts or connection refused depending on the path.

### 4.2. Namespaces Must Match

A ConfigMap and the Pods referencing it must normally live in the same namespace. A ConfigMap named **`web-demo-config`** in **`default`** is not automatically visible in **`gke-lab`**. Deployments and Services can share names across different namespaces, so pass **`-n gke-lab`** or set **`metadata.namespace`** explicitly.

## 5. Manifest 1 — ConfigMap for Non-Secret Configuration

Create a lab file named **`01-configmap.yaml`** with:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: web-demo-config
  namespace: gke-lab
  labels:
    app.kubernetes.io/name: web-demo
data:
  APP_MESSAGE: "Hello from GKE!"
  index.html: |
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <title>GKE Deployment + Service + ConfigMap</title>
      </head>
      <body>
        <h1>GKE lab: config version 1</h1>
        <p>This page is served from a ConfigMap mounted into the Pod.</p>
      </body>
    </html>
~~~

Meaning:

- **`data.APP_MESSAGE`** is a string that can be injected into a container environment variable.
- **`data.index.html`** holds multiline content projected by kubelet as a file inside a ConfigMap volume.
- **ConfigMaps are not for secrets.** Never put passwords, database URLs containing credentials, access tokens, or private keys inside them.
- Total size per ConfigMap is capped around **1 MiB**; larger payloads belong in Cloud Storage or an appropriate volume.

Kubernetes also supports **`binaryData`** for base64-encoded binary content. For HTML examples, **`data`** is easier to read and inspect. A ConfigMap can set **`immutable: true`** when policy forbids edits, though its `data`/`binaryData` can no longer be updated afterward—you must create a new one and update Pod references.

### 5.1. Apply and Inspect

~~~bash
# MUTATING — create/update ConfigMap in the lab cluster.
kubectl apply -f 01-configmap.yaml

# READ-ONLY.
kubectl get configmap web-demo-config -n "$NAMESPACE"
kubectl describe configmap web-demo-config -n "$NAMESPACE"
kubectl get configmap web-demo-config -n "$NAMESPACE" -o yaml
~~~

Before pasting output into tickets, check whether configuration data reveals internal details. ConfigMap values can be read by anyone with `get`/`list` permissions on `configmaps` in that namespace.

## 6. Manifest 2 — Deployment with Two Pods, Health Probes, and ConfigMap

Create **`02-deployment.yaml`**:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-demo
  namespace: gke-lab
  labels:
    app.kubernetes.io/name: web-demo
    app.kubernetes.io/part-of: gke-lab
spec:
  replicas: 2
  revisionHistoryLimit: 5
  progressDeadlineSeconds: 300
  selector:
    matchLabels:
      app.kubernetes.io/name: web-demo
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app.kubernetes.io/name: web-demo
        app.kubernetes.io/part-of: gke-lab
    spec:
      terminationGracePeriodSeconds: 30
      containers:
        - name: web
          # Lab demo: mutable public tag; production should pin a digest from Artifact Registry.
          image: nginx:stable-alpine
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 80
              protocol: TCP
          env:
            - name: APP_MESSAGE
              valueFrom:
                configMapKeyRef:
                  name: web-demo-config
                  key: APP_MESSAGE
          volumeMounts:
            - name: web-content
              mountPath: /usr/share/nginx/html
              readOnly: true
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "1000m"
              memory: "1Gi"
          readinessProbe:
            httpGet:
              path: /
              port: http
            initialDelaySeconds: 3
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /
              port: http
            initialDelaySeconds: 15
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
      volumes:
        - name: web-content
          configMap:
            name: web-demo-config
            items:
              - key: index.html
                path: index.html
~~~

**Self-review manifest before applying:**

| Field | Value | Meaning |
|---|---|---|
| `replicas` | 2 | Maintains two Pods if resources permit |
| `selector.matchLabels` | `app.kubernetes.io/name=web-demo` | Selects matching Pod templates |
| `template.metadata.labels` | Same labels | Lets the Deployment manage the right Pods |
| `containerPort` | 80, name=`http` | Nginx listens on TCP 80 |
| `resources.requests` | 500m CPU, 512Mi memory | Guides scheduler placement and autoscaling |
| `resources.limits` | 1000m CPU, 1Gi memory | Resource cap; exceeding memory can cause `OOMKilled` |
| `readinessProbe` | HTTP GET `/` | Unready Pods do not receive normal Service traffic |
| `livenessProbe` | HTTP GET `/` | Repeated failures trigger kubelet to restart container |
| `env.configMapKeyRef` | `APP_MESSAGE` | Read only when the container starts |
| `configMap` volume | `index.html` | File mounted into Nginx's serving directory |
| `RollingUpdate` | `maxSurge=1`, `maxUnavailable=0` | Aims to keep 2 Pods available during rollout; needs capacity |
| `revisionHistoryLimit` | 5 | Retains up to 5 old ReplicaSets per policy/controller |
| `progressDeadlineSeconds` | 300 | Reports stalled rollout after threshold; does not auto-rollback |

**Autopilot note:** GKE may adjust resource requests/limits per compute class, bursting policies, and valid minimums/ratios. YAML values are not automatically the final values. Inspect the accepted Pod spec after applying and monitor billing. Autopilot may also take time to provision nodes, so brief `Pending` Pods are not necessarily an app error.

### 6.1. Why Have Both Readiness and Liveness Probes?

- **Readiness:** "Can this Pod serve requests right now?" When false, the Pod is normally removed from the Service's ready endpoints.
- **Liveness:** "Does this container need to be restarted?" After consecutive failures, kubelet restarts the container.
- **Startup probe** (not used in the Nginx lab) fits slow-starting Java apps; until startup succeeds, liveness/readiness checks wait under startup probe rules to avoid pointless JVM restart loops.

Never tie liveness directly to a downstream DB that can slow down temporarily: if the DB stalls, every Pod may enter a restart loop instead of reconnecting cleanly. Readiness can reflect serviceability per application design.

### 6.2. Apply and Wait for Rollout

~~~bash
# MUTATING.
kubectl apply -f 02-deployment.yaml

# READ-ONLY / WAIT FOR rollout STATUS.
kubectl rollout status deployment/web-demo \
  -n "$NAMESPACE" --timeout=300s

kubectl get deployment web-demo -n "$NAMESPACE" -o wide
kubectl get replicasets -n "$NAMESPACE"
kubectl get pods -n "$NAMESPACE" \
  -l app.kubernetes.io/name=web-demo -o wide
~~~

If `rollout status` times out, **do not blindly delete Pods**. Check events, image pulls, scheduling, and probes; the Deployment controller may be waiting on node capacity or readiness probes. With **`maxUnavailable=0`**, lacking headroom for **`maxSurge=1`** can stall updates—a direct trade-off between availability and capacity.

### 6.3. Verify Actual Config Inside a Pod

~~~bash
# READ-ONLY — list Pods after they become Ready.
kubectl get pods -n "$NAMESPACE" \
  -l app.kubernetes.io/name=web-demo

# Pick POD_NAME from the output above; DO NOT use the literal placeholder.
POD_NAME="REPLACE_WITH_POD_NAME"

# Read the environment variable loaded when the container started.
kubectl exec -n "$NAMESPACE" "$POD_NAME" -c web -- \
  printenv APP_MESSAGE

# Read the index.html file mounted from ConfigMap.
kubectl exec -n "$NAMESPACE" "$POD_NAME" -c web -- \
  cat /usr/share/nginx/html/index.html
~~~

**Never use `kubectl exec` to run destructive commands on production Pods.** Pods can be replaced mid-command; if the Pod name disappears, fetch a fresh name via selector and check status.

## 7. Manifest 3 — ClusterIP Service and Pod Access

Create **`03-service.yaml`**:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: web-demo
  namespace: gke-lab
  labels:
    app.kubernetes.io/name: web-demo
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: web-demo
  ports:
    - name: http
      protocol: TCP
      port: 8080
      targetPort: http
~~~

The Service selects Pods labeled **`app.kubernetes.io/name=web-demo`**. Because the container declared a port named **`http`** mapped to **`80`**, Service port **`8080`** forwards to container port **`80`**.

~~~mermaid
flowchart LR
    C["Client Pod"] -->|"web-demo:8080"| S["Service ClusterIP\nport: 8080"]
    S --> E["EndpointSlice"]
    E -->|"targetPort: http = 80"| A["Pod A\nnginx :80"]
    E -->|"targetPort: http = 80"| B["Pod B\nnginx :80"]
~~~

### 7.1. Three Easily Confused Ports

| Field | Context | Meaning |
|---|---|---|
| **`containerPort: 80`** | Deployment Pod template | Declares the port the container listens on; does not create a listener or open a firewall |
| **Service `port: 8080`** | Service spec | Port that clients use when calling the Service |
| **`targetPort: http`** | Service spec | Points to the container port named `http`, i.e., TCP 80 in this lab |
| **`nodePort`** | Only for Services needing NodePort | Node-level port used depending on Service type and GKE config |
| **Local port 8080** | `kubectl port-forward` | Port on the operator's machine, not a public endpoint |

**A Service does not create Pods.** If the Deployment has no Ready Pods yet, the Service still has a ClusterIP, yet cannot route requests to an application endpoint.

### 7.2. Apply and Inspect EndpointSlice

~~~bash
# MUTATING — create/update Service.
kubectl apply -f 03-service.yaml

# READ-ONLY — IP/port/selector details.
kubectl get service web-demo -n "$NAMESPACE" -o wide
kubectl describe service web-demo -n "$NAMESPACE"

# READ-ONLY — EndpointSlices belonging to the Service.
kubectl get endpointslices -n "$NAMESPACE" \
  -l kubernetes.io/service-name=web-demo -o wide

# READ-ONLY — compare selector with Pod labels.
kubectl get pods -n "$NAMESPACE" \
  -l app.kubernetes.io/name=web-demo --show-labels
~~~

If the Service **has no endpoints**, check selectors, Pod readiness, namespace, and port names/numbers. In modern Kubernetes, `EndpointSlice` is the API used to track endpoints; **`kubectl get endpoints`** may still exist, yet should not be treated as the sole source for new designs.

### 7.3. Service DNS Names

Kubernetes DNS typically lets clients in the same namespace call **`web-demo`** or **`web-demo.gke-lab`**. The fully qualified name is typically:

~~~text
web-demo.gke-lab.svc.cluster.local
~~~

However, **the cluster domain can be customized**; never hardcode `cluster.local` if your organization uses a custom domain. Service names stay stable across Pod replacements; Pods get new IPs when Deployments scale, upgrade, or reschedule.

### 7.4. Testing via port-forward

~~~bash
# TEMPORARY ACTION — open a local tunnel to a Pod selected for the Service.
kubectl port-forward -n "$NAMESPACE" \
  service/web-demo 8080:8080
~~~

Open another terminal on the operator's machine:

~~~bash
curl -i http://127.0.0.1:8080/
~~~

Expected result: **HTTP 200**, HTML body containing **`GKE lab: config version 1`**.

**Evidence limitation:** when pointing `kubectl port-forward` at a Service, it selects a backing Pod for port forwarding and **does not necessarily traverse the ClusterIP dataplane or external load balancer**. It proves the Pod/app responds over an API-mediated tunnel, but does not replace testing Service networking from a real client Pod.

### 7.5. Testing from a Pod in the Same Namespace

Testing Service DNS, port mapping, and connectivity inside the cluster:

~~~bash
# CREATES A TEMPORARY POD and deletes it on exit.
# Image curlimages/curl is a lab client only; requires registry pull access.
kubectl run http-client \
  -n "$NAMESPACE" \
  --restart=Never \
  --image=curlimages/curl:8.12.1 \
  --rm -i -- \
  curl -fsS http://web-demo:8080/
~~~

If **`--rm`** fails to clean up the Pod due to an interrupted terminal, check status and delete only the **`http-client`** Pod you created in the lab namespace. Never delete a Pod of the same name unless you own it.

If the in-cluster request returns 200 while external clients outside the VPC cannot reach it, that is **working as designed**: ClusterIP is an internal Kubernetes endpoint and grants no public IP.

## 8. Service Types and Choosing Network Exposure

| Service Type | Meaning | When to Use |
|---|---|---|
| **ClusterIP** | Internal Service IP; default type | In-cluster workload-to-workload communication, service backends |
| **NodePort** | Opens a port on nodes per supported configuration | Specialized integration; rarely the right public choice for new apps |
| **LoadBalancer** | Requests cloud integration to provision an L4 load balancer | Need an endpoint reachable from the VPC or Internet |
| **ExternalName** | DNS CNAME to an external hostname | DNS alias only; creates no reverse proxy or HTTP route |
| **Headless (`clusterIP: None`)** | DNS publishes endpoints directly in headless mode | StatefulSets / specialized service discovery |

For multi-host/path HTTP(S) routing or TLS termination, **GKE Ingress** or **Gateway API** (when configured and supported) usually fits better than a standalone LoadBalancer Service. Never equate a Layer 4 LoadBalancer Service with an HTTP(S) Application Load Balancer.

### 8.1. External LoadBalancer — Create Only When Truly Needed

Illustrative manifest for a differently named Service so it doesn't disturb the ClusterIP lab:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: web-demo-public
  namespace: gke-lab
spec:
  type: LoadBalancer
  selector:
    app.kubernetes.io/name: web-demo
  ports:
    - name: http
      port: 80
      targetPort: http
      protocol: TCP
  # Use only real approved public CIDRs if supported by the service.
  # Never copy illustrative values when deploying.
  loadBalancerSourceRanges:
    - "198.51.100.0/24"
~~~

**Do not apply this manifest to production by default.** `LoadBalancer` instructs GKE to provision Google Cloud load balancing resources, which can allocate an **external IP and ongoing charges**; overly broad rules can expose the app to the Internet.

The **`198.51.100.0/24`** range above is a **documentation-only range**, not your network. Replace it with an approved source CIDR. Support for `loadBalancerSourceRanges` and related firewalls/policies also depends on the LoadBalancer Service type. Internet-facing workloads need authentication, TLS, WAF/Cloud Armor where appropriate, and a security posture review.

**GKE version note:** backend mechanisms for external passthrough Network Load Balancers have evolved in newer GKE releases. Never apply legacy target-pool annotations from old tutorials without checking the docs for your exact cluster version.

### 8.2. Internal LoadBalancer — VPC/Hybrid Consumers Only

When a LoadBalancer Service needs an **internal-only address**, one GKE-supported approach uses an annotation:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: web-demo-internal
  namespace: gke-lab
  annotations:
    networking.gke.io/load-balancer-type: "Internal"
spec:
  type: LoadBalancer
  selector:
    app.kubernetes.io/name: web-demo
  ports:
    - name: http
      port: 80
      targetPort: http
      protocol: TCP
~~~

Depending on GKE version and subsetting, Google Cloud also recommends **`spec.loadBalancerClass: networking.gke.io/l4-regional-internal`** for internal passthrough NLBs on supported clusters. **`loadBalancerClass` is immutable** and must be chosen before creating the Service. Never mix both methods blindly without checking docs and cluster config.

Internal load balancers serve clients with valid VPC or hybrid routes. **"Internal" does not replace authentication**: applications still require authn/authz. Both External and Internal LoadBalancers can incur charges even with minimal traffic.

### 8.3. What Should You Use in the Lab?

This lesson uses **ClusterIP + port-forward** to avoid provisioning load balancers and minimize attack surface. Deploy a LoadBalancer Service only when a lab goal requires it, the project authorizes it, and costs are reviewed. You do not need a public IP to prove Deployment, Service, and ConfigMap work together.

## 9. ConfigMap: Consumption Patterns and Update Behavior

A ConfigMap can be injected into Pods in several ways:

| Usage Pattern | Pod Configuration | Do ConfigMap Edits Reach Running Containers? |
|---|---|---|
| **Single key as env var** | `env.valueFrom.configMapKeyRef` | **No**, env vars are read only at container start |
| **Multiple keys as env vars** | `envFrom.configMapRef` | **No**, requires new Pod / restart |
| **Mounted as files** | `volumes.configMap` + `volumeMounts` | **Eventually updated by kubelet**, app must re-read the file |
| **Mounted via `subPath`** | `volumeMounts.subPath` | **Never auto-updates** ConfigMap contents at that mount |
| **Direct API read** | App reads Kubernetes API | Requires custom auth/RBAC/watch logic; unnecessary for basic apps |

### 9.1. Experiment A: Updating the HTML Page

Edit **`01-configmap.yaml`**:

- Change **`APP_MESSAGE`** to **`Hello from GKE - config 2!`**
- Change **`h1`** to **`GKE lab: config version 2`**

Then run:

~~~bash
# MUTATING ConfigMap without changing the Deployment template yet.
kubectl apply -f 01-configmap.yaml

# READ-ONLY ConfigMap metadata.
kubectl get configmap web-demo-config \
  -n "$NAMESPACE" -o yaml
~~~

Wait for kubelet to sync the volume, then test again:

~~~bash
# Terminal 1: port-forward as before.
kubectl port-forward -n "$NAMESPACE" \
  service/web-demo 8080:8080

# Terminal 2:
curl -fsS http://127.0.0.1:8080/
~~~

Expected output once the volume syncs and nginx serves the updated file: the page displays **`config version 2`**. This demonstrates a **mounted file** update—it does not guarantee every app reloads config automatically. In Java/Spring Boot, if an app reads a file only at startup, updating the mounted file still **will not reload beans or app config**.

### 9.2. Experiment B: Env Var Remains Stale in Running Pods

~~~bash
# Pick an existing Pod in the deployment.
kubectl get pods -n "$NAMESPACE" \
  -l app.kubernetes.io/name=web-demo

POD_NAME="REPLACE_WITH_POD_NAME"
kubectl exec -n "$NAMESPACE" "$POD_NAME" -c web -- \
  printenv APP_MESSAGE
~~~

While the Pod has not been replaced, **`APP_MESSAGE`** still prints the old value despite the updated ConfigMap. Container environment variables do not update dynamically from runtime ConfigMap edits.

### 9.3. Explicitly Restart the Deployment to Load New Env Vars

~~~bash
# MUTATING Pod template annotation to trigger a new rollout.
kubectl rollout restart deployment/web-demo -n "$NAMESPACE"

# READ-ONLY / WAIT.
kubectl rollout status deployment/web-demo \
  -n "$NAMESPACE" --timeout=300s

kubectl get pods -n "$NAMESPACE" \
  -l app.kubernetes.io/name=web-demo -o wide
~~~

Grab a **new Pod** name and inspect the env var again:

~~~bash
POD_NAME="REPLACE_WITH_NEW_POD_NAME"
kubectl exec -n "$NAMESPACE" "$POD_NAME" -c web -- \
  printenv APP_MESSAGE
~~~

Now it should print **`Hello from GKE - config 2!`** once the new Pod reads the updated ConfigMap key.

**A rollout restart is not "zero-impact hot reload"**: it creates new Pods and replaces old ones subject to strategy, capacity, and readiness. Verify traffic handling and resilience against SLOs.

### 9.4. Should You Edit ConfigMaps Directly in Production?

For controlled environments, store manifests in Git, update via pull requests and GitOps/CI, and then:

- Create a **new versioned ConfigMap** with a new name, such as **`web-demo-config-v2`**, or
- Update config in the manifest and **explicitly trigger a rollout restart**,
- Or let your deployment tool update a Pod template annotation with a **config checksum/revision**.

That way, you can pair **image version + config version** cleanly on rollback. Editing mutable ConfigMaps outside Git can leave the same Deployment revision running different configs that are hard to reproduce.

### 9.5. Limits to Remember

- **ConfigMaps are not Secrets**; use Secret Manager or Secrets per design with IAM/RBAC, never putting passwords in ConfigMaps.
- ConfigMaps have size limits; never stuff megabytes of build artifacts or ML models inside them.
- ConfigMap volumes have sync latency (kubelet sync/cache propagation).
- Mounting with **`subPath`** prevents live volume updates.
- Apps may still require a restart/reload even after the mounted file updates.
- **Immutable** ConfigMaps cannot have data updated; create a new ConfigMap with a new name and update Pod references.
- Deleting a ConfigMap still referenced by Pods or rollouts causes new Pods to fail container config startup.
- Referencing a **missing key** in a ConfigMap blocks container startup unless marked optional.

## 10. Deployment Updates, Rollout History, and Rollback

A Deployment maintains **desired replicas**, tracks Pod revisions via ReplicaSets, and updates per strategy. Changing the container image or Pod template typically creates a **new ReplicaSet**.

### 10.1. How Does RollingUpdate Work?

~~~mermaid
sequenceDiagram
    participant OP as Operator / CI
    participant D as Deployment controller
    participant OLD as Old ReplicaSet
    participant NEW as New ReplicaSet
    participant S as Service
    OP->>D: Apply new Pod template
    D->>NEW: Create new Pod (maxSurge)
    NEW-->>D: Pod Ready
    D->>OLD: Scale down old replica
    D->>NEW: Create additional new Pod
    S->>NEW: Route to new Ready endpoints
    D-->>OP: Rollout completes when conditions met
~~~

In our lab with **`replicas=2`**, **`maxSurge=1`** temporarily permits up to 3 Pods, while **`maxUnavailable=0`** aims to keep 2 Pods available during replacement. That requires sufficient cluster capacity and accurate readiness probes.

If new Pods fail to become Ready, the rollout reports stalled progress after **`progressDeadlineSeconds=300`**. Kubernetes **does not auto-undo** a Deployment simply because the deadline passed; operators/CI must evaluate and roll back per procedure.

### 10.2. Inspect Rollout Before and After Changes

~~~bash
kubectl rollout history deployment/web-demo -n "$NAMESPACE"

kubectl describe deployment web-demo -n "$NAMESPACE"

kubectl rollout status deployment/web-demo \
  -n "$NAMESPACE" --timeout=300s

kubectl get replicasets -n "$NAMESPACE"
~~~

Only changes to the **Pod template** create a new Deployment revision. Editing metadata outside the Pod template or editing a separate ConfigMap **does not automatically** create a Deployment revision. To capture config versions in rollout history, track config name/checksum/version in the Pod template.

### 10.3. Controlled Image Update

In this lesson, the public image used a mutable tag for demo purposes. In a real pipeline, assume an image was built, scanned, and pushed to Artifact Registry. Once you have the **actual `IMAGE_REF`**:

~~~bash
# MUTATING — run only when IMAGE_REF exists and is approved.
# Example valid IMAGE_REF:
# asia-southeast1-docker.pkg.dev/PROJECT/REPO/web-demo@sha256:ACTUAL_DIGEST

kubectl set image deployment/web-demo \
  web="$IMAGE_REF" \
  -n "$NAMESPACE"

kubectl rollout status deployment/web-demo \
  -n "$NAMESPACE" --timeout=300s
~~~

Careful: replacing Nginx with a Java app listening on port **8080** while keeping Service `targetPort` **80** and old probe paths will break the rollout. **Image, port, probes, ConfigMap, `securityContext`, and Service `targetPort` must be updated together as a coordinated change.**

### 10.4. Rolling Back a Deployment

If a new image version fails, run:

~~~bash
# READ-ONLY — retained Deployment revisions.
kubectl rollout history deployment/web-demo -n "$NAMESPACE"

# MUTATING — revert to the Pod template of the previous retained revision.
kubectl rollout undo deployment/web-demo -n "$NAMESPACE"

# READ-ONLY / WAIT.
kubectl rollout status deployment/web-demo \
  -n "$NAMESPACE" --timeout=300s
~~~

**Rollback limitations:** `undo` restores the **previous Pod template**, yet **it does not automatically roll back ConfigMap contents, Secrets, Services, external database schemas, or IAM** updated outside the Deployment. If the template referenced a mutable tag or an overwritten ConfigMap of the same name, rolling back may **fail to reproduce the exact old runtime state**.

Production releases should therefore record:

- Image digest and provenance.
- ConfigMap version/checksum.
- Service/port contract.
- Resource requests/limits and probes.
- Database migration compatibility.
- Rollback window and Artifact Registry retention.

## 11. Scaling Deployments and Understanding Service Stability

A Deployment scales quickly in a lab:

~~~bash
# MUTATING — increase desired Pods from 2 to 3.
kubectl scale deployment/web-demo \
  -n "$NAMESPACE" --replicas=3

# READ-ONLY.
kubectl get deployment web-demo -n "$NAMESPACE"
kubectl get pods -n "$NAMESPACE" \
  -l app.kubernetes.io/name=web-demo -o wide
kubectl get endpointslices -n "$NAMESPACE" \
  -l kubernetes.io/service-name=web-demo
~~~

Service **`web-demo:8080`** keeps the same name and virtual endpoint as backing Pods come and go. In Kubernetes, replaced Pods can receive new IPs; consumers must use **Service DNS**, never hardcoded Pod IPs.

Scale back to 2 replicas:

~~~bash
kubectl scale deployment/web-demo \
  -n "$NAMESPACE" --replicas=2
~~~

**GitOps and HPA note:** if a Git manifest declares `replicas=2`, the next apply/reconcile will revert manual scaling back to 2. If a Horizontal Pod Autoscaler is attached, it will also adjust replicas. Never adjust scale manually expecting it to stick when another controller owns desired state.

### 11.1. Scaling Does Not Mean Pods Are Instantly Healthy

- The scheduler needs sufficient CPU/memory and node/zone capacity.
- Containers must pull images and boot.
- Startup and readiness probes must pass.
- The Service must update Ready endpoints.
- More Pods can increase DB connection counts, downstream load, quotas, and cost.

Scaling to zero with **`replicas=0`** leaves the Service with zero Pod endpoints; that is valid for idle workloads, yet online services will fail requests. If traffic-driven scaling is required, evaluate HPA/KEDA or Cloud Run depending on architecture.

## 12. Applying to Java Applications and Artifact Registry

In the `CLOUD_PROVIDERS_GCP` module, a typical real-world path is:

~~~mermaid
flowchart LR
    SRC["Java source / Git"] --> BUILD["Maven/Gradle + tests"]
    BUILD --> OCI["Docker/OCI build"]
    OCI --> AR["Artifact Registry\nimage@sha256:digest"]
    AR --> DEP["GKE Deployment"]
    CONF["ConfigMap\nnon-secret settings"] --> DEP
    SEC["Secret Manager / identity"] -. "Dedicated credentials" .-> DEP
    DEP --> POD["Java app Pods"]
    SVC["Service ClusterIP"] --> POD
    CL["Client / Ingress / Gateway"] --> SVC
~~~

**Differences between the Nginx lab and a Java app:** Nginx listens on port 80 and serves `index.html` immediately when a volume updates. A Java/Spring Boot service usually listens on port **8080** (or app-configured port), reads config at startup, manages DB pools/queue consumers, and requires dedicated health endpoints.

### 12.1. Example Container Spec Swap for a Java API

Assume CI published a real image to Artifact Registry and the app exposes configured **`/actuator/health/liveness`** and **`/actuator/health/readiness`** endpoints. The container spec might look like:

~~~yaml
containers:
  - name: checkout-api
    image: asia-southeast1-docker.pkg.dev/PROJECT_ID/APP_REPO/checkout-api@sha256:ACTUAL_DIGEST
    ports:
      - name: http
        containerPort: 8080
    env:
      - name: APP_GREETING
        valueFrom:
          configMapKeyRef:
            name: checkout-config
            key: APP_GREETING
    resources:
      requests:
        cpu: "500m"
        memory: "1Gi"
      limits:
        cpu: "1000m"
        memory: "2Gi"
    startupProbe:
      httpGet:
        path: /actuator/health/liveness
        port: http
      failureThreshold: 30
      periodSeconds: 5
    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: http
      periodSeconds: 5
    livenessProbe:
      httpGet:
        path: /actuator/health/liveness
        port: http
      periodSeconds: 10
~~~

**This is a snippet, not a complete manifest.** You must create ConfigMap **`checkout-config`**, replace the image path with a real digest, and add Pod/Deployment metadata and labels. Actuator endpoints must **be configured and tested in the app**: if Spring Boot does not expose them or listens on another port, readiness/liveness will fail and Pods will restart repeatedly. CPU/memory values must be derived from JVM profiling, GKE mode, and policies—never copy example numbers to production untested.

### 12.2. Accompanying Service for a Java App

When the Java container actually listens on **8080**, the Service can use:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: checkout-api
  namespace: gke-lab
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: checkout-api
  ports:
    - name: http
      port: 80
      targetPort: 8080
      protocol: TCP
~~~

Here, in-cluster clients call **`checkout-api:80`**, and the Service forwards to container port **`8080`**. This **differs** from the Nginx lab's **Service port 8080 → `targetPort` 80**. Whenever changing images, always verify Service port mapping and probes; a Ready Pod with a mismatched Service `targetPort` still fails requests.

### 12.3. Private Images and ImagePull Principals

If the image sits in a private Artifact Registry repository:

- The repository must exist and contain the **exact image digest**.
- The identity pulling the image—typically involving the **node service account** or **GKE service agent / mode-supported mechanism**—must hold appropriate **Artifact Registry Reader** permissions.
- For cross-project repositories, grant IAM on the **source repository** to the actual image-pulling principal.
- If image pulls fail, check **`ImagePullBackOff`, `401`/`403`**, and node permissions before granting Editor/Owner.
- **Workload Identity Federation for GKE** is for Pods calling Google APIs once running; it does not automatically fix image pulls, which use their own identity path.
- Pin by **digest** so overwritten tags cannot leave Pods running inconsistent builds.

### 12.4. Runtime Credentials Differ from Image Registry Credentials

Once running, a Java app may call Cloud SQL, Pub/Sub, or Cloud Storage. Use **Workload Identity Federation for GKE** with a least-privilege service account—never bake JSON keys into ConfigMaps, images, or environment manifests. Image pulling may use a separate identity; design separate IAM for **artifact pulls** and **runtime API access**.

Never reuse one Admin service account for builds, image pulls, Pod runtime, and infrastructure cleanup. Those rights belong to distinct stages and trust boundaries.

## 13. Securing Deployments, Services, and ConfigMaps

### 13.1. Restricting Kubernetes API Permissions

Having access to a GKE cluster does not mean users should administer every namespace:

- Use **Namespaces + Roles/RoleBindings** to limit who can get/list/create/update Deployments, Services, and ConfigMaps.
- Use **Kubernetes ServiceAccounts** to identify Pods to the API server when needed.
- For apps that do not call the Kubernetes API, disable auto-mounting API tokens via **`automountServiceAccountToken: false`** in the Pod spec.
- **Google Cloud IAM** still governs projects, clusters, and Google APIs; Kubernetes RBAC does not replace IAM for Cloud Storage or Cloud SQL.
- Never allow dev environments to modify production namespaces via an overly broad shared ClusterRoleBinding.

Example read-only permission check:

~~~bash
kubectl auth can-i get deployments -n "$NAMESPACE"
kubectl auth can-i create configmaps -n "$NAMESPACE"
kubectl auth can-i patch deployments -n "$NAMESPACE"
kubectl auth can-i create services -n "$NAMESPACE"
~~~

If any returns **no**, request appropriately scoped permissions from an admin per job role. Never add a `cluster-admin` binding to bypass controls.

### 13.2. ConfigMap Is Not a Secrets Management Tool

| Data Type | Where to Store | Why |
|---|---|---|
| Log levels, non-sensitive feature flags | ConfigMap | Versioned, readable app config |
| DB hostname without credentials | ConfigMap or app config | Not secret on its own per policy |
| DB passwords, API tokens, private keys | Secret Manager or Kubernetes Secret per design | Needs access restriction, encryption, and rotation |
| Image digests and artifact versions | Deployment/GitOps manifest | Traceability and rollback |
| Large files or datasets | Cloud Storage / suitable volume | ConfigMap size limits |
| Config containing PII/secrets | Never in ConfigMap | Data protection and read access control |

Kubernetes Secrets alone do not automatically secure a system: combine RBAC, encryption at rest, auditing, CSI/Secret Manager integration where appropriate, and rotation. Never log Secret values or commit them to Git.

### 13.3. Images and Container Runtime

Production hardening typically includes:

- Using images checked for CVEs/SBOM and **pinned by digest**.
- Running as a non-root user when supported by the image.
- Disabling privilege escalation and dropping unnecessary Linux capabilities.
- Evaluating **`readOnlyRootFilesystem`** if the app/container works with appropriate temporary mounts.
- Using **seccomp/runtime defaults** and `securityContext` per GKE support.
- Configuring **resource requests/limits** based on load testing.
- Avoiding **`privileged: true`** or arbitrary `hostPath` mounts to work around access errors.
- Enforcing supply-chain controls with Artifact Registry and policies like Binary Authorization if required.

**Do not blindly force strict `securityContext` settings onto the Nginx lab:** the default image may write runtime files/caches or bind privileged ports. Test images and adjust containers before enabling non-root/read-only root filesystems rather than copying unsupported flags.

### 13.4. Network Exposure and NetworkPolicy

A **`ClusterIP`** Service only creates an internal cluster endpoint; it **is not a firewall rule** blocking other Pods. By default, Pods can talk across the cluster—even across namespaces—depending on network/policy settings.

To enforce isolation, use **Kubernetes NetworkPolicy** on supported GKE dataplane/network policy enforcement, or advanced network policies. Account for:

- Ingress from allowed source namespaces/workloads.
- Egress to Cloud SQL, DNS, Pub/Sub/Google APIs.
- Load balancer health check / proxy IPs.
- System / `kube-dns` traffic.
- GKE Dataplane V2 and support differences across cluster modes/versions.

A **default-deny NetworkPolicy** missing rules for DNS and health checks will break application connectivity completely. Roll out gradually and test both allowed and denied flows.

### 13.5. Securing Database Connectivity

If the Java app uses Cloud SQL:

1. Choose private connectivity, the Cloud SQL connector, or Auth Proxy per architecture.
2. Verify Pod egress and network paths from GKE → Cloud SQL.
3. Grant minimal IAM and DB permissions.
4. Manage secrets/credentials with rotation.
5. Tie readiness probes to serviceability; avoid making liveness probes brittle against temporary DB slowdowns.
6. Control DB connection counts when scaling replicas from 2 to 20.

A healthy **`checkout-api`** Service only proves the GKE app endpoint works—it does not grant database permissions or open routes to on-premises networks.

## 14. Troubleshooting by State and Layer

### 14.1. Key Inspection Commands

~~~bash
# Overview of objects in the namespace.
kubectl get deployments,replicasets,pods,services,configmaps \
  -n "$NAMESPACE"

# Deployment details, rollout conditions, and events.
kubectl describe deployment web-demo -n "$NAMESPACE"

# Pod details and events; substitute an actual Pod name.
POD_NAME="REPLACE_WITH_POD_NAME"
kubectl describe pod "$POD_NAME" -n "$NAMESPACE"

# Logs of a running container.
kubectl logs "$POD_NAME" -c web -n "$NAMESPACE" --tail=100

# When a container restarted and previous logs are still available.
kubectl logs "$POD_NAME" -c web -n "$NAMESPACE" \
  --previous --tail=100

# Events in the namespace.
kubectl get events -n "$NAMESPACE" \
  --sort-by=.metadata.creationTimestamp

# Service and endpoints.
kubectl describe service web-demo -n "$NAMESPACE"
kubectl get endpointslices -n "$NAMESPACE" \
  -l kubernetes.io/service-name=web-demo
~~~

**Never paste full log outputs containing tokens, private URLs, or customer data into public tickets.** Especially avoid running **`kubectl get secrets -o yaml`** just to "check config" without explicit authorization and need.

### 14.2. Symptom Matrix

| Symptom | Possible Causes | What to Check First |
|---|---|---|
| **`ImagePullBackOff` / `ErrImagePull`** | Missing image, wrong tag, private registry IAM, network/proxy | Pod events, image ref, Artifact Registry IAM |
| **`CreateContainerConfigError`** | Referenced ConfigMap or key does not exist | `kubectl describe pod`, namespace, and ConfigMap |
| **`CrashLoopBackOff`** | App crash, bad config, liveness restart, permissions | `kubectl logs --previous`, describe, probes |
| **`Pending` / `Unschedulable`** | Insufficient CPU/memory, quotas, Autopilot limits, taints | Pod events, requests, node capacity |
| **`Running` yet `0/1 Ready`** | Wrong readiness path/port, app still initializing | Pod conditions, probes, application logs |
| **Deployment `0/2 Ready`** | Pods not starting or readiness false | Describe Deployment/ReplicaSet/Pods |
| **Service has ClusterIP yet refuses/times out** | Mismatched selector, no Ready endpoints, wrong `targetPort` | EndpointSlices, labels, port mapping |
| **`port-forward` works yet client Pod times out** | Service dataplane/DNS/NetworkPolicy differs from port-forward | Test from client Pod, policies, DNS |
| **Service DNS fails to resolve** | Wrong namespace, CoreDNS/DNS config, network policy | `nslookup`/`dig` from Pod, verify FQDN |
| **ConfigMap file unchanged** | Kubelet sync/cache delay, `subPath` mount, or app caching | Update timestamp, `volumeMounts`, `cat` file |
| **ConfigMap env var still old** | Pod has not restarted | Check Pod age, run rollout restart |
| **Rollout stuck** | Image pull, probes, capacity, `maxSurge`, or invalid config | `rollout status` + events |
| **`OOMKilled`** | JVM memory/limits too low, oversized heap/native memory | Container `lastState`, metrics, JVM memory |
| **CPU throttling/latency** | CPU limits too tight or overload | CPU metrics, p95 latency, profiling |
| **LoadBalancer `EXTERNAL-IP` Pending** | Quotas, provisioning, IAM, subnet/networking, or controller | Describe Service, GKE/load balancer events |
| **HTTP `401`/`403`** | IAM/app auth, not necessarily firewall | Request logs, JWT/audience/principal |
| **Load balancer backend unhealthy** | Firewall/health check/probe/Service mismatch | Backend health, LB/GKE controller, logs |
| **ConfigMap updates yet app behavior unchanged** | App reads file only at startup or env frozen | App behavior, restart/reload policy |
| **New Pods pull a different image for same tag** | Mutable tag + pull policy/cache | Resolved `imageID`/digest and release pipeline |

### 14.3. Flowchart for Unresponsive Service

~~~mermaid
flowchart TD
    REQ["Cannot call web-demo:8080"] --> CONTEXT{"Right context + namespace?"}
    CONTEXT -- "No" --> FIX1["Verify kubeconfig and -n"]
    CONTEXT -- "Yes" --> SVC{"Service exists and selector matches?"}
    SVC -- "No" --> FIX2["Fix Service manifest/labels"]
    SVC -- "Yes" --> EP{"Ready EndpointSlices exist?"}
    EP -- "No" --> POD["Check Pod status + readiness + image pull"]
    EP -- "Yes" --> PORT{"port 8080 → targetPort 80 accurate?"}
    PORT -- "No" --> FIX3["Fix port mapping/probe"]
    PORT -- "Yes" --> NET["Check DNS, NetworkPolicy, VPC/LB path"]
    NET --> APP["Check HTTP response, app logs, and auth"]
~~~

### 14.4. Do Not Fix One Layer by Broadening Permissions on Another

- When a Pod hits **`ImagePullBackOff`**, never open `0.0.0.0/0` firewall ingress or grant `roles/owner`.
- When a Service selector mismatches, never bump replicas to 20 "just to test."
- When a ConfigMap key is missing, never delete and recreate the cluster.
- When a Java API returns **HTTP 403**, check auth/IAM before altering VPC networks.
- When Pods sit `Pending` on resources, check requests, quotas, and Autopilot compute classes—do not strip limits or enable privileged mode blindly.

## 15. Observing Reliability and Operating Deployments

### 15.1. Signals to Monitor

| Signal | Meaning |
|---|---|
| Deployment desired/available/unavailable replicas | Rollout health and serving capacity |
| Pod Ready/NotReady and restart count | Startup, probes, crashes |
| CPU/memory/ephemeral storage usage | Sizing and OOM/eviction risk |
| Request rate, p50/p95/p99 latency, HTTP errors | Real API quality |
| Service endpoints, DNS resolution | Service discovery and network readiness |
| Rollout duration and version/digest | Controlled releases |
| ConfigMap version/checksum | Configuration change traceability |
| Image pull errors | Registry IAM/networking/artifact retention |
| GKE cluster/node status and maintenance | Platform availability |
| Cost by namespace/workload/project when tagged/monitored | Cost allocation and FinOps |

GKE integrates with **Cloud Logging and Cloud Monitoring** per cluster settings. Pod metrics can be viewed with **`kubectl top pods`** if the Metrics API is deployed and available; do not assume every cluster exposes all metrics by default.

~~~bash
# READ-ONLY — metrics when the cluster has Metrics API.
kubectl top pods -n "$NAMESPACE"
kubectl top nodes

# READ-ONLY — rollout status.
kubectl get deployment web-demo -n "$NAMESPACE" \
  -o jsonpath='{.status.readyReplicas}/{.spec.replicas}{"\n"}'

# READ-ONLY — sample application logs.
kubectl logs deployment/web-demo -n "$NAMESPACE" \
  --all-containers=true --tail=100
~~~

**Never treat two Ready Pods as final proof of SLO compliance.** Health probes only check simple configured conditions; you still need synthetic checks, load tests, and business-level request observability.

### 15.2. PodDisruptionBudget and Zone Distribution

For high-availability applications, consider:

- **PodDisruptionBudget (PDB)** to limit voluntary disruptions within Kubernetes capabilities.
- **Topology spread constraints** or anti-affinity to avoid stacking all Pods onto one node/zone.
- Adequate replicas and capacity, plus readiness/startup/termination handling.
- Configuring **`terminationGracePeriodSeconds`** and graceful shutdown in Java.
- Ensuring backend DBs tolerate connection churn during rolling updates.
- A **Regional cluster** or multi-zone design matching SLOs.

A PDB **does not prevent all failures** (node crashes, zone outages, `OOMKilled`, app crashes), nor does it replace backups. With `maxUnavailable=0`, insufficient capacity can stall rollouts; balance SLOs against cost.

### 15.3. Java Shutdown and Retries

When a Deployment scales down or rolls out, Pods receive a termination signal. Java/Spring Boot should:

1. Stop accepting new requests and transition readiness to false / allow draining.
2. Complete in-flight requests/queue messages within the grace period.
3. Close DB pools, flush logs/metrics, and release resources.
4. Handle retries/idempotency for requests that time out on the client side.
5. Never treat **`terminationGracePeriodSeconds`** as a guarantee that arbitrarily long jobs will finish.

Never keep transaction state solely in Pod RAM or `emptyDir` expecting new Pods to resume cleanly across rollouts.

## 16. Costs: Deployments, Services, and ConfigMaps Do Not Share One Billing Model

Kubernetes resources are control plane objects, yet the Google Cloud infrastructure they request drives real charges.

| Component | Cost or Impact to Account For |
|---|---|
| **GKE cluster** | Cluster management fees and free/discount eligibility per current pricing |
| **Autopilot Pods** | Billing model by tier/config, resource requests, and Autopilot terms |
| **Standard nodes** | Compute Engine node VMs, boot disks, GPUs/Local SSDs if attached |
| **Service ClusterIP** | Does not create an external L4 load balancer; Pods/cluster still incur compute costs |
| **Service LoadBalancer** | Google Cloud load balancer, forwarding rules/IPs, network transfer, and supporting resources |
| **ConfigMap** | Not billed like a separate Cloud Storage bucket; consumes API/control-plane capacity and Kubernetes limits |
| **Container images** | Artifact Registry storage and image pull/transfer where applicable |
| **Cloud Logging/Monitoring** | Log/metric volume and retention exceeding free tiers |
| **Network egress** | Cross-region/outbound traffic per VPC and service setup |
| **Persistent storage** | PersistentVolumes/disks, snapshots, and backups |
| **Cloud NAT/Public IPv4** | Depending on network topology and assigned addresses |

### 16.1. Why Do Resource Requests Affect Cost?

In the lab, each Pod requests **500m** CPU and **512Mi** memory. With **2 replicas**, total workload requests before GKE adjustments are **1 vCPU and 1 GiB memory**—excluding limits, overhead, other workloads, and cluster fees.

Autopilot may enforce **minimums/defaults and CPU:memory ratios** per compute class, adjusting requests or rejecting out-of-bounds Pods. In Standard, requests govern scheduling and node sizing; actual compute billing usually tracks provisioned node resources. Never estimate bills with "`Pod count × memory limit`" without verifying billing mode and config.

Measure requests vs. actual usage and balance:

- Requests too low: OOMs, throttling, evictions, or unstable Pods.
- Requests too high: higher spend, scheduling failures, and wasted capacity.
- Limits too tight: Java/JVM hits `OOMKilled` even when average usage looks low.
- Too few replicas: node loss or rollouts can cause outages.
- Too many replicas: surges in DB connection counts and downstream load.

### 16.2. An Illustrative Calculation

Suppose a lab needs **two Pods** running 8 hours, each requesting **0.5 vCPU and 0.5 GiB**. Hypothetical consumption before Autopilot-specific adjustments is:

~~~text
Total CPU-request-hours:
2 Pods × 0.5 vCPU × 8 h = 8 vCPU-hours

Total memory-request-hours:
2 Pods × 0.5 GiB × 8 h = 8 GiB-hours
~~~

This **is not a Google Cloud invoice**. Current unit prices, minimums, hardware/compute classes, cluster fees, regions, networking, and Autopilot request adjustments determine real charges. Use **Cloud Billing Reports / Cost tables** alongside usage metrics to verify. If you created a LoadBalancer, charges can continue even when workloads serve zero requests.

### 16.3. Optimization Workflow

1. Choose the right **cluster/mode** and reuse authorized learning clusters.
2. Use **ClusterIP** unless external/internal L4 load balancing outside the cluster is required.
3. Right-size resource requests/limits from real usage and health telemetry.
4. Shut down/delete lab-owned resources once finished.
5. Trim log noise without disabling required security/audit logs.
6. Audit Artifact Registry images, orphaned disks, and network egress.
7. Track costs per project/workload/namespace using organization-supported cost allocation.
8. Test rollbacks and readiness so you never "save money" by sacrificing availability.

## 17. Case Study — From Java Container to Checkout Service on GKE

### 17.1. Context

A company operates **`checkout-api`** with four requirements:

- Two Ready replicas to tolerate losing one Pod.
- In-cluster services call **`checkout-api.gke-prod.svc.cluster.local`** (or actual cluster domain).
- **Non-secret configuration** such as log level and feature flags lives in a ConfigMap.
- Database credentials are managed separately, images live in Artifact Registry, and rollbacks target digests.

Planned pipeline:

~~~mermaid
flowchart LR
    C["Git commit"] --> TEST["Java tests"]
    TEST --> B["Build image"]
    B --> AR["Artifact Registry\nimage digest"]
    AR --> D["Deployment checkout-api"]
    CM["ConfigMap\nlog level, feature flags"] --> D
    D --> P["Replicas: checkout-api Pods"]
    SVC["ClusterIP Service\ncheckout-api:80"] --> P
    CL["Orders / frontend API"] --> SVC
    DB["Cloud SQL / durable database"] <--> P
~~~

### 17.2. Design Steps

| Layer | Decision | Rationale |
|---|---|---|
| Image | Verified immutable digest | Accurate traceability and rollback |
| Deployment | 2+ replicas, RollingUpdate, probes | Keeps serving when Pods are replaced |
| Service | ClusterIP | Only in-cluster consumers needed |
| ConfigMap | `APP_FEATURE_X`, `LOG_LEVEL` | Contains no secrets |
| Auth | Workload Identity Federation for GKE | No service account keys in images |
| Data | Cloud SQL or durable storage | Pod filesystems are ephemeral |
| Security | Namespace RBAC, NetworkPolicy as needed, least privilege | Limits blast radius |
| Observability | Readiness, error rate, latency, DB connections | Measures business health |
| Rollback | Manifest image digest + ConfigMap version | Restores consistent image and config |

### 17.3. Incident A — Service Has No Endpoints

The team deploys a Deployment with Pod labels **`app=checkout-api`**, while the Service selector uses **`app=checkout`**. The Service is created and DNS resolves, yet EndpointSlice has zero matching Ready Pods.

**Investigation:** compare **`kubectl get pods --show-labels`** against **`kubectl describe service`**, then align selectors/labels in Git. Never create extra LoadBalancers, bump replicas, or edit VPC firewalls to fix a label mismatch.

### 17.4. Incident B — ConfigMap Updated Yet Feature Flag Unchanged

The team updates ConfigMap **`FEATURE_CHECKOUT_V2=true`**, yet the Java app reads the flag via an environment variable at startup. Running Pods retain the old value.

**Investigation:** check Pod age, env vars, and ConfigMap version; use GitOps/rollout restart or create a newly versioned ConfigMap referenced in the Pod template. Even if an app supports file hot-reloading, verify it genuinely watches the mounted file. Never assume "applying a ConfigMap automatically reloads every app."

### 17.5. Incident C — Rollout 0/2 Ready After Image Update

The new image runs a Java server on port **8080**, while the Deployment readiness probe still hits port **80**. Pods start yet remain unready; the Service sends no traffic to the new Pods. With **`maxUnavailable=0`**, old Pods stay up while the rollout stalls unless impacted by another change.

**Investigation:** describe Pod and Deployment; verify resolved `imageID`, container ports, readiness path, and application logs. Fix the port/probe in the manifest and re-rollout, or roll back the template if needed. Never mass-delete old Pods before healthy replacements exist.

### 17.6. Incident D — Scaling to 10 Replicas Overloads the Database

The Deployment scales cleanly and the Service lists 10 endpoints, yet each Java Pod opens a pool of up to 30 connections—potentially hitting 300 DB connections before counting other services.

**Investigation:** inspect DB metrics, pool settings, retries, timeouts, and HPA; tune connection pools and database capacity rather than assuming more Pods always yield linear throughput.

### 17.7. Production Acceptance Criteria

A release passes only when:

1. Image digest and build metadata are verified.
2. Deployment reaches expected available replicas.
3. Service has Ready endpoints and DNS resolves in the right namespace.
4. ConfigMap/Secret versions match the release.
5. Functional tests traverse the real Service/Ingress path, not just `port-forward`.
6. IAM/RBAC/network exposure comply with policy.
7. Latency/error rates/DB connections stay within SLO thresholds.
8. A rollback path exists and out-of-Pod data remains intact.
9. Cost and scaling headroom have been evaluated.
10. Pipeline/GitOps retains the exact manifest for future deployments.

## 18. Controlled Lab Cleanup

**Delete only resources you created and own.** Never delete a shared namespace or shared GKE cluster for one exercise. In particular, LoadBalancer Services can provision Google Cloud infrastructure: delete the Service first, confirm the load balancer is reclaimed, and then check remaining dependencies.

### 18.1. Inventory Before Cleanup

~~~bash
# READ-ONLY — verify kubeconfig context.
kubectl config current-context

# READ-ONLY — all main objects in the lab namespace.
kubectl get deployments,services,configmaps,pods \
  -n "$NAMESPACE"

kubectl get endpointslices -n "$NAMESPACE" \
  -l kubernetes.io/service-name=web-demo
~~~

If you also created **`web-demo-public`** or **`web-demo-internal`**, verify they belong strictly to the lab with no active consumers before deleting:

~~~bash
# READ-ONLY — inspect only, do not delete yet.
kubectl get services -n "$NAMESPACE" -o wide
~~~

### 18.2. Delete the Three Lab Manifests

~~~bash
# MUTATING / DELETES RESOURCES — use only in the lab on the right context.
# Delete the Service first to stop exposing endpoints.
kubectl delete -f 03-service.yaml

# Delete the Deployment and its controller-managed Pods.
kubectl delete -f 02-deployment.yaml

# Once no Pods reference it, delete the lab ConfigMap.
kubectl delete -f 01-configmap.yaml

# READ-ONLY — verify created objects are gone.
kubectl get deployments,services,configmaps,pods \
  -n "$NAMESPACE"
~~~

If a **public/internal LoadBalancer Service** was created, **delete that Service explicitly by manifest/name** and confirm cloud load balancer resources are released. Never manually delete forwarding rules or firewall resources in the Console if GKE controllers manage them or other workloads share them.

### 18.3. Namespace and Cluster

Delete namespace **`gke-lab`** only if it was created strictly for this lesson and holds no other users' workloads:

~~~bash
# MUTATING — only when the namespace is strictly dedicated to this lab.
kubectl delete namespace gke-lab
~~~

If you **created an isolated GKE cluster purely for practice**, deleting the cluster stops ongoing infrastructure fees. However, doing so is **high-risk** if any other team has workloads, disks, or IPs there. Verify project, cluster ID, location, workload ownership, and data retention decisions through change approval before running cluster deletion.

No blanket **delete cluster** command is provided here to prevent accidental copy-pasting. Cleaning up an entire **project** or billing account is outside the scope of these three objects.

### 18.4. Post-Cleanup Cost Check

- Confirm the namespace, Service, and Deployment are gone as expected.
- Check for lingering LoadBalancers, external IPs, PersistentVolumes, or Compute Engine resources.
- If a dedicated cluster was created, ensure the approved delete/retain plan was executed.
- Review Billing Reports by Service/SKU after billing ingestion lag.
- Never delete an Artifact Registry repository or digest for a lab if shared with other pipelines.

## 19. Exercises and Self-Check Questions

### 19.1. Exercise A — Reading a Service with Port Mapping

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: billing-api
  namespace: gke-lab
spec:
  type: ClusterIP
  selector:
    app: billing
  ports:
    - port: 9000
      targetPort: 8080
      protocol: TCP
~~~

**Questions:**

1. Which port must clients in the same namespace call on the Service?
2. Which port must the billing container listen on?
3. If Pods carry label **`app=billing-v2`**, will the Service have endpoints?
4. If the Deployment has 3 replicas yet only 1 Pod is Ready, how many Pods does the Service normally route traffic to?
5. Does this Service have a public IP?

**Answers:** (1) 9000. (2) 8080. (3) No, selector mismatch excludes that Pod. (4) Normally 1 Ready endpoint (subject to `publishNotReadyAddresses` and edge cases). (5) No, internal ClusterIP.

### 19.2. Exercise B — Updating a ConfigMap

A Deployment consumes a ConfigMap in two ways:

- **`LOG_LEVEL`** via **`env.valueFrom.configMapKeyRef`**.
- **`app.yaml`** via normal **`volumeMounts`** without `subPath`.

You edit and apply the ConfigMap successfully. Answer:

1. Does `LOG_LEVEL` inside existing containers change immediately?
2. Can the mounted `app.yaml` update? Is there a delay?
3. If the Java app reads `app.yaml` only at startup, will behavior change?
4. What if the file is mounted using `subPath`?
5. What ensures a rollout reproduces the exact image + config a month later?

**Guided answers:** (1) No. (2) Yes, eventually updated by kubelet. (3) No, unless the app hot-reloads. (4) `subPath` mounts never auto-update. (5) Use an image digest and ConfigMap version/checksum in the Pod template/GitOps to create an auditable revision.

### 19.3. Exercise C — Rollout Stuck

A Deployment has **`replicas=2, maxSurge=1, maxUnavailable=0`**. On image update, the new Pod hits **`ImagePullBackOff`**. Answer:

- State why the rollout stops progressing.
- List three read-only `kubectl` commands to inspect the failure.
- State whether you should delete the two old Pods to "force the update."
- Propose a fast recovery assuming the previous revision still exists.

**Guided answers:** The new Pod cannot pull its image and never becomes Ready; inspect **`kubectl describe pod`**, **`kubectl describe deployment`**, **`kubectl rollout status`**, and events. Never delete old Pods; fix the image path/IAM or run **`kubectl rollout undo`** and re-verify.

### 19.4. Exercise D — GKE vs. Cloud Run

A Java application scales by HTTP requests and has no need for the Kubernetes API, specialized service discovery, or custom controllers. Compare deploying with **GKE Deployment/Service/ConfigMap** versus **Cloud Run** across operations, scaling, networking, CI/CD, IAM, and cost.

**Guidance:** GKE fits when you need the Kubernetes ecosystem, multiple workloads/protocols, fine-grained scheduling/networking control, and declarative Kubernetes objects. Cloud Run reduces cluster operational complexity for compatible HTTP/event workloads; never pick GKE just because you already know how to write Deployment YAML.

### 19.5. Quick Questions

1. Does a Deployment automatically create a Service?
2. Does a Service scale replicas up or down?
3. Is a ConfigMap a safe Secret store for database passwords?
4. Why shouldn't clients hardcode a Pod IP?
5. Can a LoadBalancer Service incur charges even with zero requests?
6. Does `kubectl apply` printing `created` prove Pods are Ready?
7. Does a successful `port-forward` prove an external load balancer works?
8. Does `kubectl rollout undo` automatically roll back database schemas or ConfigMaps edited outside the Deployment?
9. Why pin image digests?
10. Why must the Service selector and Pod labels align?

**Short answers:** (1) No. (2) No. (3) No. (4) Pods are replaced and IPs change. (5) Yes. (6) No. (7) No. (8) No. (9) Pins the exact artifact executed. (10) So the Service selects the right endpoints.

### 19.6. Lab Verification Log Template

~~~text
PROJECT_ID:
CLUSTER:
LOCATION:
KUBECTL_CONTEXT:
NAMESPACE:
CONFIGMAP_NAME / KEYS:
DEPLOYMENT_NAME / DESIRED_REPLICAS:
PODS_READY:
IMAGE_REFERENCE / IMAGE_ID:
SERVICE_NAME / TYPE / PORT / TARGET_PORT:
ENDPOINTSLICES:
HTTP_STATUS / RESPONSE_BODY:
CONFIGMAP_VOLUME_UPDATE:
ENV_VAR_BEFORE_RESTART:
ENV_VAR_AFTER_RESTART:
ROLLOUT_REVISION / RESULT:
LOGS / EVENTS:
LOADBALANCER_CREATED?:
COST_RESOURCES_CREATED:
CLEANUP_RESULT:
OWNER / OBSERVATION_TIME:
OPEN_ISSUES:
~~~

Record **actual observed results**, never marking PASS solely because YAML syntax was valid. Never record credentials, Kubernetes tokens, or secrets in verification logs.

## 20. Official Reference Documentation

Sources to cross-check APIs, syntax, and evolving GKE/Kubernetes behavior:

- [GKE: Deploy an app to a GKE cluster](https://docs.cloud.google.com/kubernetes-engine/docs/deploy-app-cluster)
- [GKE: Create an Autopilot cluster](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/creating-an-autopilot-cluster)
- [GKE: Autopilot overview](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/autopilot-overview)
- [GKE: Resource requests in Autopilot](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/autopilot-resource-requests)
- [GKE: Exposing applications using Services](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/exposing-apps)
- [GKE: About LoadBalancer Services](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/service-load-balancer)
- [Kubernetes: Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Kubernetes: Services](https://kubernetes.io/docs/concepts/services-networking/service/)
- [Kubernetes: ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/)
- [Kubernetes: Configure a Pod to use a ConfigMap](https://kubernetes.io/docs/tasks/configure-pod-container/configure-pod-configmap/)
- [Kubernetes: Update a Deployment](https://kubernetes.io/docs/tasks/run-application/update-deployment-rolling/)
- [GKE: Workload Identity Federation](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/workload-identity)
- [GKE: Use Artifact Registry images](https://docs.cloud.google.com/artifact-registry/docs/integrate-gke)
- [GKE pricing](https://cloud.google.com/kubernetes-engine/pricing)

GKE versions, Autopilot constraints, load balancer implementations, Kubernetes API behavior, and pricing may update over time. In real-world work, verify documentation against your environment's **cluster mode/version, Google Cloud project, region, image architecture, IAM, and network configuration**.

---

**Connecting to the `CLOUD_PROVIDERS_GCP` path:** this lesson builds on **projects/IAM, VPC networking, container images in Artifact Registry, and Compute Engine/GKE** to deploy multi-replica applications. **Deployments** maintain Pods and rollouts, **Services** provide stable endpoints, and **ConfigMaps** decouple non-secret config from images. When extending to **Cloud SQL, Cloud Storage, Pub/Sub, CI/CD, and Cloud Monitoring**, the workflow remains **right image and config → matching Pods/labels → Service with Ready endpoints → verify real request path → protect identity and data → monitor SLOs, cost, and rollbacks**.
