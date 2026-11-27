# Network Endpoint Groups for VMs, GKE, and Serverless

An enterprise deploys an order service on **Cloud Run**, a product catalog API on **Google Kubernetes Engine (GKE)**, and a legacy application on a **Compute Engine VM**. Operations wants to use one unified HTTPS domain, forwarding `/orders` requests to Cloud Run, `/catalog` to GKE, and `/legacy` to the VM. Beyond choosing the load balancer type and configuring TLS, you must define **what actual backend receives traffic** and how Google Cloud knows which endpoints are serving.

A **network endpoint group (NEG)** is a configuration resource describing a group of network endpoints or services that a load balancer can use as a backend. Depending on the NEG type, an endpoint can be a **VM's IP:port**, a **GKE Pod's IP:port**, or a **reference to a serverless service**. NEGs enable defining backends at a finer granularity than merely managing VM lists via instance groups.

This lesson belongs to the **Load Balancing and Content Delivery** chapter of the **CLOUD_PROVIDERS_GCP** module. Knowledge of NEGs bridges project organization, IAM, VPC, and deploying Compute Engine, GKE, and Cloud Run with resource protection, release automation, reliability monitoring, and cost management. The focus is **choosing and operating the right NEG for VMs, GKE, and serverless**; other NEG types are introduced to avoid confusion.

## 1. Understanding NEGs in the Load Balancing Architecture

### 1.1. Where Does a NEG Sit?

With an **Application Load Balancer** (HTTP/HTTPS load balancing), the logical flow typically includes:

~~~mermaid
flowchart LR
    U["User / client"] --> F["Frontend: IP, port, TLS"]
    F --> P["Target HTTP(S) proxy"]
    P --> M["URL map: host/path"]
    M --> B1["Backend service: orders"]
    M --> B2["Backend service: catalog"]
    M --> B3["Backend service: legacy"]
    B1 --> N1["Serverless NEG"]
    B2 --> N2["GKE zonal NEGs"]
    B3 --> N3["VM zonal NEGs"]
    N1 --> R["Cloud Run service"]
    N2 --> K["GKE Pods: IP:port"]
    N3 --> V["App VM: IP:port"]
~~~

This is the model of an application-layer load balancer. Components and rules for a **proxy Network Load Balancer** or **passthrough Network Load Balancer** may differ. When using this example, distinguish five roles:

| Component | Responsibility |
| --- | --- |
| **Frontend / forwarding rule** | IP address, port, and mechanism for receiving client traffic. |
| **Target proxy and URL map** | Handles HTTP(S) sessions, TLS, and selects a backend service by host/path for the corresponding Application Load Balancer type. |
| **Backend service** | Aggregates one or more backends, configures traffic distribution, and enforces policies supported by the load balancer type. |
| **NEG** | Identifies the endpoints or services to which the backend service can send traffic. |
| **Actual endpoint/backend** | The VM process, Pod container, or serverless service receiving and processing requests. |

**A NEG is not a complete load balancer.** Creating a NEG does not automatically provide a public IP, HTTPS certificate, URL map, or Internet traffic route. Conversely, a backend service must reference an appropriate NEG compatible with the load balancer type in use.

### 1.2. Why Not Use Instance Groups for Every Workload?

**Instance groups** aggregate VMs for management and load balancing at the instance level. **NEGs** let you describe endpoints more precisely:

- One VM can serve multiple processes on different ports; a `GCE_VM_IP_PORT` NEG can target a specific `IP:port`.
- One GKE node can run many Pods; with container-native load balancing, backends are represented by the **Pod's IP address and port**, instead of forcing traffic through a node port just to reach a Pod.
- Cloud Run does not give users a fixed VM or Pod IP to manually register as a backend. A **serverless NEG** references the Cloud Run service via a supported mechanism.

Instance groups remain well suited for many Compute Engine models, especially workloads needing VM-level autohealing/autoscaling. NEGs do not replace **Managed Instance Groups**, the Kubernetes scheduler, or Cloud Run autoscaling; each component solves a distinct responsibility.

### 1.3. Common NEG Types

| NEG Type | Typical API Endpoint Type | Scope | Use Case |
| --- | --- | --- | --- |
| **Zonal NEG for IP and port** | `GCE_VM_IP_PORT` | Zone | VMs running apps on specific ports; GKE Pods under container-native mode. |
| **Zonal NEG for IP only** | `GCE_VM_IP` | Zone | VMs or GKE nodes with supported **passthrough Network Load Balancers**. |
| **Serverless NEG** | `SERVERLESS` | Region | Cloud Run, Cloud Run functions, App Engine, and other serverless platforms per supported Application Load Balancer type. |
| **Hybrid connectivity NEG** | `NON_GCP_PRIVATE_IP_PORT` | Zone | Private endpoints outside Google Cloud reached over compatible hybrid connectivity. |
| **Internet NEG** | `INTERNET_IP_PORT`, `INTERNET_FQDN_PORT` | Global or regional | Backends with IP/FQDN reachable over the Internet. |
| **Private Service Connect NEG** | `PRIVATE_SERVICE_CONNECT` | Per service/LB capability | Backend representing a service published via Private Service Connect. |

**You cannot arbitrarily pair every NEG type with every load balancer.** For instance, serverless NEGs are for supported **Application Load Balancers**, not a generic backend for all Network Load Balancers. `GCE_VM_IP` and `GCE_VM_IP_PORT` also correspond to different load balancer types and endpoint models. In real designs, always cross-check Google Cloud's **NEG–load balancer compatibility matrix**.

## 2. Zonal NEGs for Compute Engine VMs

### 2.1. What Is an `IP:port` Endpoint?

Suppose a VM has internal IPv4 address `10.10.1.12` and the application listens on port `8080`. A `GCE_VM_IP_PORT` endpoint can be represented as:

~~~text
NEG:       neg-legacy-a
Zone:      asia-southeast1-a
VPC:       retail-vpc
Subnet:    app-subnet
Instance:  legacy-vm-1
Endpoint:  10.10.1.12:8080
~~~

Such a NEG can contain multiple eligible endpoints in the **same zone**, tied to the matching network/subnet. The IP address must belong to supported addresses on the VM interface, such as a primary internal IPv4 or alias IP per specification. For IPv6/dual-stack configurations, support depends on NEG type, interface type, and release stage; this lesson uses IPv4 examples for clarity.

**The endpoint port matters operationally:** if the process listens on `8080` while the NEG registers `9090`, the load balancer cannot serve the application just because the VM is `RUNNING`.

### 2.2. How Does a `GCE_VM_IP` Zonal NEG Differ?

`GCE_VM_IP` represents a VM by IP address **without an endpoint port**. It is used with supported **passthrough Network Load Balancers** and handles packets differently from proxy/Application Load Balancers.

| Comparison Point | `GCE_VM_IP_PORT` | `GCE_VM_IP` |
| --- | --- | --- |
| Endpoint identifier | `IP:port` attached to compatible VM/interface. | IP attached to compatible VM/interface. |
| Typical scenario | Application/proxy load balancing, VM apps, and GKE Pods. | Passthrough network load balancing; some GKE `LoadBalancer` Services using node IPs. |
| Routing to app port | Port is part of the endpoint definition. | Port is not in the endpoint; depends on forwarding rule and passthrough model. |
| Health checks | Backend service uses compatible health check mechanism. | Backend service uses health check mechanism compatible with the LB type. |

Choose the NEG type based on the required **traffic architecture**, not merely on "whether the backend is a VM".

### 2.3. Example: Creating a VM NEG with gcloud

Assume the project, VPC, subnet, and VM already exist. The `create`/`update` commands below **modify real resources**, so use them only in authorized environments after verifying parameters.

~~~bash
# Bash example; replace names and project with real resources.
PROJECT_ID="retail-prod"
ZONE="asia-southeast1-a"
NETWORK="retail-vpc"
SUBNET="app-subnet"
NEG="neg-legacy-a"

# Create a GCE_VM_IP_PORT zonal NEG; default-port is optional.
gcloud compute network-endpoint-groups create "$NEG" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --network="$NETWORK" \
  --subnet="$SUBNET" \
  --default-port=8080

# Register the endpoint of an existing VM in the same zone.
gcloud compute network-endpoint-groups update "$NEG" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --add-endpoint="instance=legacy-vm-1,ip=10.10.1.12,port=8080"
~~~

If the same service runs across multiple zones, you need **corresponding zonal NEGs**. Creating only one NEG in zone A does not make the load balancer discover VMs in zone B. For VMs managed by a Managed Instance Group, design membership sync when VMs are created/deleted; manual registration will not keep the NEG synchronized across autoscaling events.

### 2.4. Inspecting NEGs and Endpoints

The following commands are **read-only**:

~~~bash
gcloud compute network-endpoint-groups list \
  --project="$PROJECT_ID"

gcloud compute network-endpoint-groups describe "$NEG" \
  --project="$PROJECT_ID" \
  --zone="$ZONE"

gcloud compute network-endpoint-groups list-network-endpoints "$NEG" \
  --project="$PROJECT_ID" \
  --zone="$ZONE"
~~~

Listing endpoints only confirms configuration presence. To conclude an endpoint is **actively receiving traffic**, inspect the linked backend service, health checks, firewalls, logs, and run live HTTP/TCP tests.

### 2.5. Attaching a NEG to a Backend Service

Assuming a backend service for a **global external Application Load Balancer** already exists:

~~~bash
# Write command: updates an existing backend service.
gcloud compute backend-services add-backend legacy-backend \
  --project="$PROJECT_ID" \
  --global \
  --network-endpoint-group="$NEG" \
  --network-endpoint-group-zone="$ZONE"
~~~

Depending on the Application Load Balancer type, a backend service can be **global or regional** and accept different flags. Match the exact load balancer type, scope, health check, and backend service. Do not attach `--global` to a regional backend service just because you want to balance across multiple zones.

## 3. NEGs for GKE: Container-Native Load Balancing

### 3.1. Why Route Directly to Pods?

In Kubernetes, applications are typically accessed via a **Service**, while Pods are created/deleted or moved across nodes during rollouts, scaling, and rescheduling. An older model sends load balancer traffic to a **node**, and then `NodePort`/kube-proxy forwards it to a Pod. The **container-native load balancing** model lets supported load balancers use **`GCE_VM_IP_PORT` zonal NEGs** with **Pod IP:container port** endpoints.

~~~mermaid
flowchart LR
    C["HTTPS client"] --> LB["Application Load Balancer"]
    LB --> BS["Backend service"]
    BS --> NEG1["Zonal NEG - zone A"]
    BS --> NEG2["Zonal NEG - zone B"]
    NEG1 --> P1["Pod A: 10.50.1.20:8080"]
    NEG1 --> P2["Pod B: 10.50.1.21:8080"]
    NEG2 --> P3["Pod C: 10.50.2.20:8080"]
    K["GKE NEG controller"] -. "Syncs Pod endpoints" .-> NEG1
    K -.-> NEG2
~~~

Result: the load balancer can health-check and send traffic to backends at the **Pod level**, rather than only seeing whether a node is alive. This is helpful when a single node runs multiple applications or when individual Pod status must be reflected during releases.

GKE also has a **`LoadBalancer` Service** pattern that uses `GCE_VM_IP` zonal NEGs with **node VMs** as endpoints in supported passthrough cases. Therefore, saying "every GKE NEG points straight to Pods" is inaccurate. Identify the exact controller, Service type, load balancer type, and NEG type in use.

### 3.2. Who Manages the Pod Endpoint List?

When using **GKE Ingress**, the **GKE Gateway controller**, or **standalone NEGs** in supported setups, the **GKE NEG controller** creates/updates NEGs and keeps endpoints synced as Pods change. Operators must manage:

- `Deployment` or workload resources, labels, selectors, and actual Pod ports.
- `Service` along with required annotations or controller configurations.
- Managed `Ingress`, `Gateway`, `HTTPRoute`, or backend service resources accordingly.
- Probes, readiness, VPC connectivity, firewalls, and controller permissions.

**Never manually edit membership of a NEG owned by the GKE controller** if you want GKE to keep syncing properly. Manual edits can be overwritten or cause drift when the controller reconciles.

### 3.3. Example: Standalone NEG via Kubernetes Service

The example below creates a **declarative manifest** for a Service with an annotation instructing GKE to create zonal NEGs for port `80`. Pods selected by `app: catalog-api` must listen on port `8080`. This manifest applies only in an eligible GKE cluster with a matching workload.

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog-api
  namespace: retail
  annotations:
    cloud.google.com/neg: '{"exposed_ports":{"80":{}}}'
spec:
  type: ClusterIP
  selector:
    app: catalog-api
  ports:
    - name: http
      protocol: TCP
      port: 80
      targetPort: 8080
~~~

With **standalone NEGs**, you manage the load balancer configuration (or an integration tool referencing the NEG) yourself, depending on the deployment model. If the cluster uses **GKE Ingress** with the corresponding annotation, the controller can automatically create/manage load balancer components. Never have two controllers manage the same backend without clearly defining **which owns the configuration**.

In some Ingress models, the annotation:

~~~yaml
metadata:
  annotations:
    cloud.google.com/neg: '{"ingress":true}'
~~~

indicates NEGs will be used for Ingress backends per GKE conditions. With **Gateway API**, the GKE controller can also create NEGs for referenced Services. Exact configurations vary by cluster, version, and load balancer type; these examples do not substitute for each controller's compatibility documentation.

### 3.4. Inspecting GKE-Managed NEG Status

~~~bash
# Read commands: inside the kubeconfig/context of the target GKE cluster.
kubectl -n retail get service catalog-api -o yaml
kubectl -n retail describe service catalog-api
kubectl -n retail get endpointslices -l kubernetes.io/service-name=catalog-api

# When the cluster/controller exposes ServiceNetworkEndpointGroup resources:
kubectl -n retail get svcneg

# From an environment with Compute API read permissions:
gcloud compute network-endpoint-groups list --project=retail-prod
~~~

In the Service metadata, inspect the **`cloud.google.com/neg-status`** annotation: it shows the names of NEGs created by the controller and their corresponding zones. Auto-generated NEG names can be long and differ from the Service name; never guess names and accidentally delete or edit the wrong NEG.

Also verify `Ready` Pod counts, selectors, port mappings, and controller events. **Existing Kubernetes endpoints** do not guarantee the load balancer considers them `HEALTHY`: LB health checks and Pod readiness are two distinct checks to cross-verify.

### 3.5. Health Checks, Readiness, and Rolling Deployments

To ensure applications receive traffic cleanly:

1. Configure Pod `readinessProbe` to reflect when the application can genuinely serve requests.
2. Pick the matching **protocol, path, and port** on the load balancer's backend service health check.
3. Ensure firewall policies allow traffic/health check sources for the **exact load balancer type** to `Pod IP:port` inside the VPC.
4. Track **NEG readiness gates** when used by the controller to synchronize Pod readiness with LB health state; do not assume every standalone pattern shares identical behavior.
5. Test rolling updates, scale-ups/downs, Pod termination, and connection draining.

In some global external Application Load Balancer models, common health check ranges are `35.191.0.0/16` and `130.211.0.0/22`; however, **do not blindly copy these ranges to every load balancer**. For regional Envoy-based load balancers, the path to backends also involves a **proxy-only subnet**. Always verify the firewall/health check docs for your chosen LB type.

## 4. Serverless NEGs for Cloud Run and Supported Services

### 4.1. Serverless NEGs Do Not Contain `IP:port` Lists

Unlike VMs and Pods, Cloud Run runs on self-managed infrastructure that scales dynamically with traffic. A **serverless NEG** has endpoint type `SERVERLESS` and references a supported serverless resource or **URL mask**. It **has no `IP:port` list** for administrators to add or remove manually.

~~~mermaid
flowchart LR
    C["Client"] --> LB["Application Load Balancer HTTPS"]
    LB --> BS["Backend service: orders"]
    BS --> SN["Serverless NEG (regional)"]
    SN --> RUN["Cloud Run service: orders-api"]
    RUN --> REV["Revisions / instances managed by Cloud Run"]
~~~

Mandatory design rules:

- **Serverless NEGs are regional**, and the referenced Cloud Run/App Engine/functions/API Gateway resource must reside in an eligible region per service rules.
- The serverless backend resource and the NEG normally must reside in the **same project** per serverless NEG constraints.
- One serverless NEG represents **one logical endpoint** (a resource or URL mask), not multiple VMs or Pods.
- A backend service can use multiple serverless NEGs across different regions in supported load balancer topologies; distribution and failover depend on the LB type and actual configuration.
- Serverless NEGs work with supported **Application Load Balancers**, not as backends for passthrough/proxy Network Load Balancers.

Beyond Cloud Run, variants exist for **Cloud Run functions, App Engine**, and **API Gateway**, though support varies across Application Load Balancer types. When building a new system, verify exact product, runtime generation, region, and LB type before choosing.

### 4.2. Creating a Serverless NEG Referencing Cloud Run

Suppose Cloud Run service `orders-api` is already deployed in `asia-southeast1` inside project `retail-prod`:

~~~bash
PROJECT_ID="retail-prod"
REGION="asia-southeast1"

# Inspect existing service.
gcloud run services describe orders-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="yaml"

# Write command: create regional serverless NEG referencing the service.
gcloud compute network-endpoint-groups create orders-run-neg \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --network-endpoint-type=serverless \
  --cloud-run-service=orders-api

# Re-read NEG configuration.
gcloud compute network-endpoint-groups describe orders-run-neg \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="yaml"
~~~

Creating the NEG **does not deploy the Cloud Run service** and does not create an HTTPS frontend. If the service does not exist yet, is in the wrong region/project, or is not a supported resource type, the setup will not work as intended.

### 4.3. Attaching to a Compatible Backend Service

Example building a **global external Application Load Balancer** with `EXTERNAL_MANAGED` mode, where backend service `orders-run-backend` uses a serverless NEG:

~~~bash
# Write command: create compatible global backend service.
gcloud compute backend-services create orders-run-backend \
  --project="$PROJECT_ID" \
  --global \
  --load-balancing-scheme=EXTERNAL_MANAGED \
  --protocol=HTTP

# Write command: attach regional serverless NEG to the backend service.
gcloud compute backend-services add-backend orders-run-backend \
  --project="$PROJECT_ID" \
  --global \
  --network-endpoint-group=orders-run-neg \
  --network-endpoint-group-region="$REGION"

# Read command: confirm backend service.
gcloud compute backend-services describe orders-run-backend \
  --project="$PROJECT_ID" \
  --global
~~~

For users to reach it via a real domain, infrastructure teams **must still** configure the URL map, target HTTPS proxy, certificate, forwarding rule, DNS, and related policies. This example only illustrates the backend portion. For **regional external** or **internal Application Load Balancers**, backend service settings and `--region` scope must follow their respective guides.

### 4.4. Serverless NEG Health Checks Differ from VM/GKE

Common pitfall: a backend service with a **serverless NEG does not support traditional health checks like a zonal NEG** and has no `port` endpoint to probe. Balancing mode parameters such as `RATE`, `UTILIZATION`, or `CONNECTION` also do not apply the way they do to VM backends.

However, some load balancer types support **outlier detection** based on HTTP responses or **Cloud Run service health** to help detect and steer away from failing serverless backends. These capabilities are conditional on LB type, region, and configuration; they **do not mean a traditional health check is attached to the serverless backend service**.

When a serverless backend returns `5xx`, inspect **Cloud Run request logs**, revisions, concurrency, timeouts, quotas, cold starts, and data dependencies—not merely whether the NEG exists.

### 4.5. Ingress and Authentication

Putting a load balancer in front of Cloud Run provides a shared domain, TLS, URL routing, and features such as **Cloud Armor** or **Cloud CDN** where allowed by the LB/backend. However, **the load balancer does not automatically complete end-user authentication**. If Cloud Run requires authentication, design how clients are authorized—such as **Identity-Aware Proxy (IAP)** in supported topologies or appropriate application-level auth.

For Cloud Run fronted by an external Application Load Balancer, consider the **`internal-and-cloud-load-balancing`** ingress mode if appropriate, to restrict direct access paths that bypass the load balancer. Ingress settings, IAM Invoker, domain mappings, and IAP solutions must align; never toggle one setting and assume all requests are protected.

If planning to use **Cloud CDN and IAP on the same backend service**, verify current compatibility limits; in standard configurations, both cannot be enabled simultaneously on the same backend service.

## 5. Placing Three Workload Types Behind One Domain

### 5.1. Route-Based Design

Suppose users visit `https://shop.example.com`:

| Host/Path | Backend Service | NEG and Destination | Owner |
| --- | --- | --- | --- |
| `/orders/*` | `orders-run-backend` | Regional serverless NEG → Cloud Run `orders-api`. | Orders backend team. |
| `/catalog/*` | `catalog-gke-backend` | Zonal NEGs → GKE Pods `catalog-api`. | Product catalog team. |
| `/legacy/*` | `legacy-vm-backend` | Zonal NEG → VM `IP:port`. | Legacy maintenance team. |

The Application Load Balancer's URL map classifies requests into **three separate backend services**. Each backend service uses a valid NEG governed by that backend type's rules.

**Do not combine a Cloud Run serverless NEG and a GKE zonal NEG in the same backend service** expecting the load balancer to split traffic by percentage: that combination is unsupported. Instead, split routes via the URL map to separate backend services and use traffic management features supported by the load balancer type for advanced rollout needs.

### 5.2. Distinguishing "Routing" from "Capacity"

When a client sends `/orders/123`, the URL map selects `orders-run-backend`; the backend service/NEG then forwards the request to Cloud Run via serverless mechanics. How Cloud Run scales instances is Cloud Run's responsibility, subject to quotas, concurrency, and runtime settings.

For `/catalog/123`, the URL map selects `catalog-gke-backend`, and the backend service uses zonal NEGs containing Pod `IP:port` endpoints; health check status and endpoint membership govern which Pod receives the request. As replicas scale, the GKE controller updates NEGs.

For `/legacy/report`, the URL map selects the VM backend; if the VM or application process fails health checks, that backend can be marked unhealthy per LB rules. **NEGs do not restart VMs automatically**; Managed Instance Group autohealing or dedicated operational processes handle that.

### 5.3. Questions to Answer Before Deploying

1. Are clients on the Internet, internal VPC, or both? Select the matching **external/internal Application Load Balancer**, **global/regional/cross-region**, and network tier.
2. Is HTTP path/host routing needed, or TCP/UDP balancing? If only L4 passthrough is needed, the compatible NEG types differ.
3. Which zones/regions host the workloads? Are multi-region, DR, or cross-region failover needed?
4. Who manages backends: VM team, GKE controller, Cloud Run, or IaC? Avoid two tools editing the same resource concurrently.
5. Do routes need header/path rewrites, end-to-end TLS, session affinity, caching, WAF, or IAP? Verify support for the exact backend type.
6. Does rollback handle route and endpoint membership changes, or only image/revision rollbacks?

## 6. Health Checks and Endpoint Lifecycle

### 6.1. Monitoring Backend Status

| Backend | Appropriate Monitoring Mechanism | Common Pitfalls |
| --- | --- | --- |
| **VM zonal NEG `GCE_VM_IP_PORT`** | Backend service health check to `IP:port`, routing, and firewalls. | VM running while process isn't listening on port, wrong health check path. |
| **GKE Pod zonal NEG** | LB health check + Kubernetes readiness/lifecycle + NEG controller sync. | Pod IP changes, readiness not met, stale endpoint lingering in NEG. |
| **Serverless NEG** | Cloud Run/app logs and service health/outlier detection where supported. | No traditional NEG health check; failing revisions may still receive traffic. |

Example of an **HTTP health check** for a zonal NEG using the **serving port** declared by the endpoint:

~~~bash
# Write command: creates health check; use only for compatible backends.
gcloud compute health-checks create http hc-catalog \
  --project=retail-prod \
  --request-path=/healthz \
  --use-serving-port
~~~

The health check must also be attached to the appropriate **backend service**. Endpoints must return the status code and content expected by the health check; routes and firewalls must permit checker traffic to reach endpoints. Do not apply this example to a serverless NEG backend service.

### 6.2. Connection Draining and Version Changes

For zonal NEGs, when an endpoint is removed from a backend, open connections can be governed by **connection draining** and backend service limits. This is especially critical when:

- A GKE rolling deployment replaces Pod `IP:port` endpoints.
- A VM is removed from the pool for software updates.
- Port or network interface configurations change.
- Operators shift traffic between zones or backends.

Application design requires sensible timeouts and retries, idempotency for write requests, and graceful shutdown. A backend marked healthy does not guarantee every long-running transaction can finish if an endpoint is being terminated.

### 6.3. Separating Autoscaling from NEGs

**A NEG is a backend representation**, not a capacity controller:

- **Compute Engine:** Managed Instance Groups scale/manage VMs; NEG membership is maintained by the corresponding tool/architecture.
- **GKE:** Horizontal Pod Autoscaler or other autoscalers adjust Pod counts; the controller syncs the NEG.
- **Cloud Run:** the platform scales automatically per settings and demand; the serverless NEG simply points to the service.

If all endpoints in a zonal NEG lose health or no eligible backends remain, traffic can fail even while the load balancer frontend is up. Likewise, a valid serverless NEG does not prevent Cloud Run from hitting quotas or a backend database from saturating.

## 7. Security and Access Boundaries

### 7.1. Networking and Firewalls

For **VM/GKE zonal NEGs**, identify whether the load balancer uses Google Front Ends or Envoy proxies, then apply matching firewall rules and network scopes:

- Allow traffic to endpoints on the required protocol/port.
- Allow health checker ranges or the proxy-only subnet matching the LB type and deployment scope.
- Restrict direct access to VMs/backends if architecture dictates traffic must traverse the load balancer.
- For GKE, also check Kubernetes `NetworkPolicy` (if used), Pod IP ranges, VPC routes, and cluster config.

Creating a NEG alone does not open firewalls. Conversely, opening NodePort/Pod/VM ports too broadly can expose paths bypassing load balancer policies.

### 7.2. IAM and Application Identity

**IAM for LB/NEG administration** differs from **workload IAM**:

- Pipelines need permissions to create/update backend services, URL maps, and NEGs in the target project/resources, without needing broad organization-wide Owner roles.
- The GKE controller must be authorized to manage NEGs and backend resources per deployment architecture; users should not hand-edit controller-owned NEGs.
- The Cloud Run runtime service account needs permissions to call Cloud SQL, Cloud Storage, or Secret Manager per business needs; serverless NEG admin roles do not grant data access.
- Callers hitting Cloud Run endpoints need proper authentication, ingress settings, and app policies; a load balancer does not automatically replace all authorization checks.

When using **Shared VPC** or **cross-project service referencing** on supported Application Load Balancers, verify specific constraints and IAM permissions. Having a backend in another project does not automatically allow referencing it just because both projects share an organization.

### 7.3. Cloud Armor, IAP, and CDN

Compatible Application Load Balancers with NEG backends can integrate:

| Component | Role | What to Check |
| --- | --- | --- |
| **Cloud Armor** | Security policies at HTTP/HTTPS layer or blocking unwanted traffic. | LB/backend compatibility, policy attachment point, and direct backend bypass risk. |
| **IAP** | Identity-based user access control to apps in supported topologies. | Backend support, OAuth client, and compatibility with Cloud CDN. |
| **Cloud CDN** | Caches eligible content close to users when supported by backend/LB. | Cache headers, personal data, cache TTLs, purging, and cache/egress cost. |

Never accidentally cache responses containing private user order details. **Attaching a CDN is not automatically safe**, nor does Cloud Armor replace IAM, session handling, or application authorization checks.

## 8. Monitoring, Troubleshooting, and Cost

### 8.1. Layered Diagnostics

When users encounter `502`, `503`, or high latency, inspect from the outside in:

1. **Frontend:** IP/DNS, certificate/TLS, forwarding rule, listener.
2. **Routing:** do host/path rules and the URL map pick the right backend service?
3. **Backend service:** is the right NEG type, scope, and region/zone attached?
4. **NEG:** are VM/GKE endpoints properly registered/synced? For serverless, does the NEG point to the right Cloud Run service?
5. **Health/availability:** are VMs/GKE healthy? Does Cloud Run have revision/concurrency/quota errors?
6. **Networking and permissions:** are routes, firewalls, ingress, IAM, IAP, or Cloud Armor blocking requests?
7. **Application:** code, database, dependencies, timeouts, exceptions, and detailed logs.

**HTTP 403** often points to authorization, ingress, IAP, or security policies; **HTTP 404** can come from the URL map/path or the app; **HTTP 502/503** can involve unhealthy backends, timeouts, or connection failures. Never rely on a single HTTP status code alone to conclude the exact root cause.

### 8.2. Read-Only Inspection Commands

~~~bash
PROJECT_ID="retail-prod"

# Inventory NEGs and their types/scopes.
gcloud compute network-endpoint-groups list \
  --project="$PROJECT_ID"

# Inspect a zonal NEG for VM or GKE.
gcloud compute network-endpoint-groups describe neg-legacy-a \
  --project="$PROJECT_ID" \
  --zone=asia-southeast1-a

# For a zonal NEG, list currently registered IP:port endpoints.
gcloud compute network-endpoint-groups list-network-endpoints neg-legacy-a \
  --project="$PROJECT_ID" \
  --zone=asia-southeast1-a

# Inspect a regional serverless NEG.
gcloud compute network-endpoint-groups describe orders-run-neg \
  --project="$PROJECT_ID" \
  --region=asia-southeast1

# Inspect a global backend service and attached NEGs.
gcloud compute backend-services describe orders-run-backend \
  --project="$PROJECT_ID" \
  --global
~~~

To check health of compatible backends, run:

~~~bash
# Example: backend service for zonal NEGs created with global scope.
gcloud compute backend-services get-health legacy-backend \
  --project=retail-prod \
  --global
~~~

This command must target an **existing backend service**, compatible load balancer type, and proper read permissions. For serverless NEGs, do not rely on `get-health` the way you inspect VM/Pod health; check Cloud Run metrics, logs, and supported service health/outlier detection features.

### 8.3. Telemetry to Observe

| Layer | Signals to Monitor | Operational Question |
| --- | --- | --- |
| Load balancer | Requests, 4xx/5xx errors, latency, backend response status. | Are errors occurring at the frontend, proxy, or backend? |
| Zonal NEG/backend | Endpoint count, health status, membership changes. | Are enough healthy endpoints available across zones? |
| GKE | Pod readiness, restarts, events, NEG sync status, rollouts. | Is there drift between Pods and endpoints in the NEG? |
| Cloud Run | Requests, latency, 5xx, concurrency, instances, revision logs. | Does the service have capacity, timeouts, or failing dependencies? |
| Application | End-to-end SLIs such as order creation success rate. | Are users actually completing business journeys? |

A `load balancer up` indicator is not enough to claim the system meets its SLO. A frontend serving TLS while the database fails to write orders is still a business outage. Combine Cloud Monitoring, Cloud Logging, Cloud Trace, and application logs according to need and supported scope.

### 8.4. Cost and Scaling Capacity

Do not treat "NEG" as a way to eliminate load balancing fees. Relevant cost items can include:

- Load balancer rule/hourly charges and data processing fees per current pricing.
- Compute Engine VMs, GKE nodes/Pods, and autoscaling configurations.
- Cloud Run requests, CPU/memory, concurrency, and execution duration.
- Cloud CDN cache/egress, Cloud Armor, or IAP when used.
- Inter-zone/inter-region traffic, outbound data transfer, logging, and monitoring.

Per GKE standalone NEG documentation, using standalone NEGs **does not itself add an extra per-NEG fee** in that model, though backends, networking, and load balancers still carry costs. For production estimates, rely on current Google Cloud pricing tables, Billing reports, and real request/traffic profiles.

## 9. Quick Selection Table

| Scenario | NEG to Evaluate | Accompanying Configuration |
| --- | --- | --- |
| HTTP app on VM, port `8080`, needing HTTPS and path routing. | Zonal `GCE_VM_IP_PORT`. | Application LB, backend service, health check, firewalls, membership updates. |
| Passthrough TCP/UDP to VMs/nodes in supported models. | Zonal `GCE_VM_IP`. | Matching passthrough Network LB and compatibility limits. |
| API running on GKE Pods, wanting LB straight to each Pod. | GKE-managed `GCE_VM_IP_PORT` zonal NEGs. | GKE Ingress/Gateway/standalone controller, Service, health/readiness, backend service. |
| Cloud Run needing a shared domain, HTTPS, and routing. | Regional `SERVERLESS`. | Supported Application LB, backend service, ingress/IAP/WAF as needed. |
| On-premises app over VPN/Interconnect. | Hybrid `NON_GCP_PRIVATE_IP_PORT`. | Hybrid connectivity, DNS, routing, health checks, and firewalls. |
| Public backend outside Google Cloud by IP/FQDN. | Appropriate Internet NEG. | Supported LB type, outbound security, and external dependency risk management. |

Choosing a NEG is **one step in an architectural decision**, not an isolated choice. Backend protocols, global/regional scope, VPC, security policies, health checks, and workload ownership determine whether the solution is operable.

## 10. Common Configuration Mistakes

| Symptom | Possible Cause | Inspection Steps |
| --- | --- | --- |
| NEG exists but has no endpoints. | VM not added; wrong GKE selector; Pods not synced by controller. | `list-network-endpoints`, Service labels/annotations, and GKE events. |
| GKE NEG not created. | Malformed JSON annotation, Service port mismatch, unsupported cluster/controller, or permissions error. | `kubectl describe svc`, `neg-status`, `svcneg`, and events. |
| VM zonal NEG reports backend unhealthy. | Wrong `IP:port`, process not listening, wrong health path, firewall blocking checks. | Inspect endpoints, health check, firewalls, and VM logs. |
| GKE Pods `Ready` yet LB returns 502/503. | LB health differs from readiness, NEG not synced, backend service missing/misconfigured. | Backend service health, Pod readiness gates, NEG status. |
| Cloud Run NEG not working. | Wrong project/region, service doesn't exist, incompatible backend type/LB. | `describe` serverless NEG, Cloud Run service, and backend service. |
| Cloud Run returns many 5xx yet NEG doesn't mark unhealthy. | Serverless NEGs don't use traditional health checks; app/revision is failing. | Cloud Run logs, metrics; evaluate service health/outlier detection if supported. |
| `/catalog` routes to `/orders`. | URL map has wrong host/path rule or priority. | Inspect URL map and corresponding backend service config. |
| 403 from LB domain or Cloud Run URL. | IAM, ingress, IAP, Cloud Armor, or application authorization. | Cross-check permissions, ingress, logs, and security policies. |
| Errors appear after GKE rolling update. | Pod termination/draining, health transitions, insufficient capacity. | Monitor rollout, NEG sync, request logs, and graceful shutdown. |
| Costs rise after enabling LB. | Data processing/egress, region scope, caching, logging, or backend autoscaling. | Cloud Billing, traffic metrics, and networking configuration. |

## 11. Hands-On Exercises

### Exercise 1 — Choose the Right NEG Type

An application has three components:

1. Compute Engine VM running HTTP on `10.10.1.12:8080`.
2. GKE Service with three Pods: `10.50.1.20:8080`, `10.50.1.21:8080`, `10.50.2.20:8080`.
3. Cloud Run service `orders-api` in `asia-southeast1`.

**Question:** choose the NEG type, zone/region scope, and endpoint management approach for each component.

**Hint:** VM uses zonal `GCE_VM_IP_PORT` with managed membership; container-native GKE uses GKE-managed zonal `GCE_VM_IP_PORT` with the controller syncing Pods; Cloud Run uses regional `SERVERLESS` referencing the service, with no Pod/VM IP list.

### Exercise 2 — Trace the Request Flow

A user accesses `https://shop.example.com/catalog/42`. Describe the sequence **frontend → HTTPS proxy → URL map → backend service → zonal NEG → Pod**. What happens if a URL map rule is wrong even while Pods are healthy?

**Hint:** the request can be sent to the wrong backend service, returning 404/403 or unintended content. Always test every path/host after configuration changes.

### Exercise 3 — Diagnose a 502

A GKE Deployment has 4 `Ready` Pods and a Service with a valid NEG annotation, yet the load balancer returns `502`.

**Check in order:** did the controller create the NEGs; does the endpoint list match `Pod IP:port`; did the backend service attach the right NEGs; are the health check path/port and firewalls correct; does the app return successful HTTP responses when called directly on the internal network?

### Exercise 4 — Separation of Duties

The frontend team's pipeline needs to update the load balancer's URL map without reading order data in Cloud SQL. Explain why LB admin roles and data access roles must be separated, and define who approves production routing changes.

### Exercise 5 — Design a Rollback

The product team deploys a new Cloud Run revision while simultaneously rolling out GKE Pods. When the `order_success_rate` SLI drops, propose separate rollback paths for the **Cloud Run revision**, **GKE Deployment**, and **URL map/backend routing**. Which metrics confirm users have actually recovered?

## 12. Pre-Production Checklist

| Item | Verification Criteria |
| --- | --- |
| **LB type** | Right Application/Network, external/internal, global/regional choice per requirements. |
| **NEG type** | `GCE_VM_IP`, `GCE_VM_IP_PORT`, or `SERVERLESS` compatible with the LB type. |
| **Ownership** | Clear owner creating/editing NEGs: operator, GKE controller, or IaC. |
| **Endpoint identity** | VM `IP:port` in right zone/subnet; Pod `IP:port` matching Service; Cloud Run in right project/region. |
| **Backend service** | NEGs attached with right scope; no mixing of unsupported backend types. |
| **Health/availability** | VM/GKE health checks and readiness; serverless metrics/service health as supported. |
| **Network security** | Firewalls, proxy/health-check traffic, ingress settings, and direct backend exposure checked. |
| **IAM** | Least-privilege permissions for deployment identities, controllers, and runtimes. |
| **TLS and routing** | Certificates, DNS, host/path rules, URL map, and backend mappings verified. |
| **Deployment** | Rollout, draining, canary/rollback, or compatible traffic shifting plan in place. |
| **Observability** | Request logs, 4xx/5xx, backend health, GKE events, Cloud Run logs, and end-to-end SLOs. |
| **Cost & scale** | Estimates for LB/egress/backend capacity, quotas, and budget alerts. |

## 13. Official Documentation and Takeaways

NEG types, support across Application/Network Load Balancers, and features like outlier detection or service health can evolve. When deploying in real environments, consult current documentation:

- [Network endpoint groups overview](https://cloud.google.com/load-balancing/docs/negs)
- [Zonal network endpoint groups overview](https://cloud.google.com/load-balancing/docs/negs/zonal-neg-concepts)
- [Set up zonal NEGs](https://cloud.google.com/load-balancing/docs/negs/setting-up-zonal-negs)
- [Container-native load balancing with standalone NEGs on GKE](https://cloud.google.com/kubernetes-engine/docs/how-to/standalone-neg)
- [GKE container-native load balancing](https://cloud.google.com/kubernetes-engine/docs/concepts/container-native-load-balancing)
- [Serverless NEGs overview](https://cloud.google.com/load-balancing/docs/negs/serverless-neg-concepts)
- [Set up external Application Load Balancer with serverless backend](https://cloud.google.com/load-balancing/docs/https/setting-up-https-serverless)
- [Load balancing health checks](https://cloud.google.com/load-balancing/docs/health-check-concepts)
- [Google Cloud CLI: network-endpoint-groups](https://cloud.google.com/sdk/gcloud/reference/compute/network-endpoint-groups)

**A NEG describes where the load balancer sends traffic, but it does not automatically guarantee the backend works well.** For VMs, watch `IP:port` and health checks; for GKE, watch controllers, Pod readiness, and endpoint sync; for Cloud Run, watch serverless references, ingress, identity, and health-checking boundaries. When these layers work together cleanly, a single frontend can serve diverse workloads, handle safe releases, and measure service quality from the user's perspective.
