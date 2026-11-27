# Network Policies and Pod Traffic Segmentation in GKE

An e-commerce company runs `storefront`, `orders-api`, and payment workers on **Google Kubernetes Engine (GKE)**. The frontend needs to call the orders API, the API needs to connect to **Cloud SQL**, and the payment worker must contact specific services. If every Pod in the cluster can reach every other Pod by default, a compromised container can attempt port scans, hit unrelated services, or move laterally into other namespaces.

**Kubernetes NetworkPolicy** is a declarative mechanism specifying **which Pods are allowed to receive or initiate network connections** based on Pod/namespace selectors, IP addresses, protocols, and ports. On GKE, these policies are enforced by a compatible data plane / network policy provider. Using NetworkPolicies properly enables **microsegmentation** at the network layer—limiting blast radius when an application is compromised, isolating environments or services, and controlling egress flows.

This lesson belongs to the **Advanced GKE and Operations** chapter of the **CLOUD_PROVIDERS_GCP** module. It connects project/IAM/VPC concepts, Compute Engine, GKE, Cloud Run, Cloud Storage, Cloud SQL, and Artifact Registry with resource protection, GitOps/CI/CD rollouts, reliability management, and cost tracking. The focus is **Pod traffic segmentation with NetworkPolicy in GKE**, rather than replacing Google Cloud's entire network security architecture.

## 1. Learning Objectives and Scope

After this lesson, learners will be able to:

1. Explain **ingress**, **egress**, **isolation**, and the allow-list semantics of Kubernetes NetworkPolicy.
2. Accurately interpret `podSelector`, `namespaceSelector`, `ipBlock`, `policyTypes`, `ports`, and how multiple policies combine.
3. Distinguish the **Calico network policy** engine from **GKE Dataplane V2**, along with deployment constraints across Standard and Autopilot.
4. Design a **default-deny → explicit allow** model for frontend, API, database, and DNS traffic.
5. Contrast NetworkPolicy with **VPC firewall rules**, **IAM**, **Kubernetes RBAC**, **Cloud Armor**, **service mesh authorization**, and advanced egress controls.
6. Author manifests, apply them incrementally, build allow/deny tests, and troubleshoot issues without breaking production services.
7. Monitor, audit, roll back, and evaluate security, reliability, and operational impacts.

**Example convention:** namespace, service, IP, project, and region names are purely for learning. Commands with `apply`, `create`, `label`, or `delete` **modify real resources**; run them only in an authorized lab cluster. Some features depend on GKE release channel, version, cluster mode, and active data plane; verify against official documentation before deploying.

## 2. Why Segment Network Traffic Between Pods?

### 2.1. Default Connectivity Is Not a Security Boundary

In Kubernetes, when **no policy isolates a Pod**, traffic in the corresponding direction is generally permitted at the NetworkPolicy layer, even if other network or application controls exist. This model is convenient during development, but carries risks:

- A compromised Pod can probe other services the application author never intended it to reach.
- A public service in namespace `web` can probe sensitive backends in `payments`.
- A batch worker meant only to read Cloud Storage gains a network path to unrelated databases.
- A team's misconfigured network change can unexpectedly expose traffic across tenants.

**A namespace is not a firewall by itself.** Namespaces organize resources, RBAC, quotas, and ownership; restricting Pod-to-Pod traffic across namespaces requires NetworkPolicies or another network control layer.

### 2.2. System Before and After Segmentation

~~~mermaid
flowchart LR
    W["storefront Pod"] --> A["orders-api Pod"]
    W -. "Unnecessary connection" .-> D["postgres Pod in lab"]
    A --> D
    P["payments-worker Pod"] -. "Unintended connection" .-> W
~~~

After configuring policies, we want:

~~~mermaid
flowchart LR
    W["storefront: retail-web"] -->|"TCP 8080"| A["orders-api: retail-api"]
    A -->|"TCP 5432"| D["postgres: retail-data"]
    P["payments-worker"] -. "Not directly allowed" .-> D
    W -. "Not directly allowed" .-> D
~~~

The arrows represent **security intent**; actual enforcement holds only when source/destination policies, namespace labels, Pod labels, data plane, and service paths all align. Never assume the diagram becomes reality just because three namespaces exist.

### 2.3. The "Only Necessary Flows" Rule

Before writing YAML, operations teams should build a **traffic matrix**:

| Source | Destination | Protocol/port | Reason | Decision |
| --- | --- | --- | --- | --- |
| `storefront` in `retail-web` | `orders-api` in `retail-api` | TCP 8080 | Send order requests. | Allow. |
| `orders-api` | Lab PostgreSQL in `retail-data` | TCP 5432 | Query order data. | Allow. |
| `storefront` | Lab PostgreSQL | TCP 5432 | Direct connection unnecessary. | Deny. |
| `payments-worker` | `storefront` | TCP 8080 | Not part of business flow. | Deny. |
| Pods using DNS | Cluster-configured DNS resolver | UDP/TCP 53 or specific mechanism | Resolve service/API hostnames. | Controlled allow. |
| Production `orders-api` | Cloud SQL private endpoint | TCP 5432 if PostgreSQL | Database runs outside the cluster. | Allow to actual destination. |

**Not all traffic is Pod-to-Pod:** Cloud SQL, Google APIs, load balancer proxies, the control plane, and node connections have separate network paths and authorization layers. Pod policies are only one layer in that picture.

## 3. How Does Kubernetes NetworkPolicy Work?

### 3.1. Namespace Scope and Selected Pods

A NetworkPolicy is a **namespaced** Kubernetes resource. Its `spec.podSelector` picks **which Pods inside that same namespace** the policy governs.

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: api-ingress-example
  namespace: retail-api
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes:
    - Ingress
  ingress: []
~~~

This policy **isolates ingress** for Pods labeled `app=orders-api` in namespace `retail-api`. Because `ingress: []` defines no allow rules, new inbound connections covered by ingress enforcement are blocked per NetworkPolicy semantics. This policy **does not isolate egress** from those Pods.

Setting `podSelector: {}` selects **all Pods in that namespace**; it does not select Pods in other namespaces across the cluster.

### 3.2. Ingress and Egress Are Independent Directions

**Ingress:** controls traffic **entering** the target Pods selected by the policy.

**Egress:** controls traffic **leaving** the source Pods selected by the policy.

A Pod can be:

- Ingress-isolated only (egress unrestricted).
- Egress-isolated only (ingress unrestricted).
- Isolated in both directions.
- Unisolated in either direction.

For a **Pod A → Pod B** connection to succeed when both sides are isolated, **both egress on A and ingress on B must allow it**. Allowing one side does not open the other.

### 3.3. Policies Are Additive Allow-Lists

Standard Kubernetes NetworkPolicy follows **allow-list** semantics:

1. If no policy selects a Pod for a given direction, the Pod is not isolated by NetworkPolicy in that direction.
2. Once at least one policy selects a Pod and isolates that direction, only connections permitted by **one or more policies** succeed.
3. When multiple policies select the same Pod, the allowed traffic is the **union of their allow rules**.
4. **There is no rule priority order** across standard NetworkPolicies; basic `networking.k8s.io/v1` has no `deny` action that overrides `allow`.

For example, if one policy allows TCP 8080 ingress from the frontend and another allows TCP 9090 from monitoring, the Pod accepts **both flows** where matching. Adding a `default-deny` policy does not erase existing allow rules.

### 3.4. `policyTypes` and Defaults

`policyTypes` can include `Ingress`, `Egress`, or both. When omitted, Kubernetes defaults to `Ingress`, and adds `Egress` if egress rules are specified per API semantics. Throughout this lesson, every policy **declares `policyTypes` explicitly** to prevent ambiguity.

| Field | Meaning |
| --- | --- |
| `spec.podSelector` | Pods governed by the policy within the policy's namespace. |
| `spec.policyTypes` | Which directions (ingress/egress) are isolated and evaluated. |
| `spec.ingress` | List of ingress allow rules; `[]` means no ingress allow exceptions. |
| `spec.egress` | List of egress allow rules; `[]` means no egress allow exceptions. |
| `from` / `to` | Peers or CIDRs permitted by each rule. |
| `ports` | Permitted protocols/ports; omitting `ports` allows all ports for that rule. |

**Return traffic for an already-allowed connection** is typically handled by the data plane's connection tracking (stateful tracking); you do not write reverse rules for ACK/response packets. However, a **new connection initiated from the reverse direction** is evaluated independently and can be blocked.

## 4. Reading `podSelector`, `namespaceSelector`, and `ipBlock` Correctly

### 4.1. Pod Selector in the Same Namespace

Inside a `from`/`to` peer entry, a standalone `podSelector` matches Pods in the **NetworkPolicy's own namespace**. For example, in a policy in `retail-api`:

~~~yaml
from:
  - podSelector:
      matchLabels:
        app: internal-client
~~~

This rule allows peer Pods with `app=internal-client` **inside `retail-api`**—it does not allow Pods with the same label in `retail-web`.

### 4.2. Namespace Selector

~~~yaml
from:
  - namespaceSelector:
      matchLabels:
        access-zone: web
~~~

This rule matches **all Pods in namespaces labeled `access-zone=web`** when other rule conditions match. If users can freely edit namespace labels, they could bring an arbitrary namespace into the allow-list; therefore, **control RBAC permissions for modifying namespace labels**.

### 4.3. AND Within One Peer, OR Across Two Peers

This is a classic YAML pitfall. Writing **a single list item** containing both `namespaceSelector` and `podSelector` means **AND**:

~~~yaml
from:
  - namespaceSelector:
      matchLabels:
        access-zone: web
    podSelector:
      matchLabels:
        app: storefront
~~~

Only Pods with `app=storefront` **inside a namespace labeled `access-zone=web`** match.

Conversely, **two separate list items** mean **OR**:

~~~yaml
from:
  - namespaceSelector:
      matchLabels:
        access-zone: web
  - podSelector:
      matchLabels:
        app: storefront
~~~

The second item matches `app=storefront` Pods **in the policy's own namespace**; the first item matches **every Pod in any `access-zone=web` namespace**. That is drastically broader. **Indentation and a single `-` dash can completely alter your security boundary.**

### 4.4. `ipBlock` for IP Addresses / CIDRs

~~~yaml
to:
  - ipBlock:
      cidr: 10.70.0.0/24
      except:
        - 10.70.0.128/25
~~~

`ipBlock` specifies allowed IP ranges minus excluded subranges under `except`. It fits **external non-Pod endpoints** with stable IP addresses where supported by data plane semantics. For traffic passing through a Kubernetes Service, DNAT/SNAT before or after policy evaluation can affect the visible IP; **never rely blindly on `ipBlock` to target Pods**.

Specifically on **GKE Dataplane V2**, `ipBlock` **must not be used to select Pod IPs** per product design; use `podSelector` and `namespaceSelector` for Pod-to-Pod traffic. When restricting Google APIs or cloud services by IP, factor in DNS, NAT, private endpoints, and IP rotation; dedicated egress solutions are often a better fit.

### 4.5. Rule `ports`, `from`, and `to`

Within an ingress rule, the peer list (`from`) and port list (`ports`) combine to define allowed traffic. Multiple entries inside `from` or inside `ports` act as **OR** choices within their respective lists. Example:

~~~yaml
ingress:
  - from:
      - podSelector:
          matchLabels:
            app: metrics-scraper
    ports:
      - protocol: TCP
        port: 9090
~~~

This allows `app=metrics-scraper` Pods in the same namespace to reach selected Pods on TCP 9090. `endPort` or named ports can help on supported platforms, yet **they do not replace verifying which port the application actually listens on**.

**Beware empty allow rules:** an `ingress` rule item that **omits `from` or sets `from: []`** places no source restriction, allowing any source to reach the rule's ports. Similarly, omitting `ports` allows all ports. This differs completely from **`ingress: []` at the `spec` level**, which means zero ingress allow rules exist in the policy.

### 4.6. Limitations of Standard NetworkPolicy

Standard Kubernetes NetworkPolicy operates primarily at **L3/L4**:

- Cannot distinguish HTTP `GET /orders` from `POST /payments` using NetworkPolicy alone.
- Does not understand OAuth users, JWT claims, or Kubernetes RBAC.
- Does not handle TLS termination, mTLS certificates, or database authentication.
- Standard NetworkPolicy has no destination FQDN/hostname selector field.
- Cannot block specific Google Cloud API resources based on service accounts.
- Does not necessarily treat traffic from **host networks**, nodes, or the control plane identically; check actual data plane behavior.

When you need L7 authorization, service identity, FQDN-aware egress, or fine-grained external egress control, evaluate **GKE Dataplane V2 extensions**, service mesh, egress gateways/proxies, IAM, and firewalls—never assume advanced features are built into standard `networking.k8s.io/v1` YAML.

## 5. How Does GKE Enforce NetworkPolicy?

### 5.1. The Kubernetes API Needs an Enforcement Provider

The Kubernetes API server can store `NetworkPolicy` objects, yet **storing an object does not mean policies are enforced** if the data plane/CNI lacks support or has the feature disabled.

On GKE, two main architectures apply:

| Model | Enforcement mechanism | Operational considerations |
| --- | --- | --- |
| **GKE Standard with legacy Network Policy/Calico** | Network policy enforcement configured on the cluster/node pools via the supported toggle. | Enabling it on a running cluster can modify or recreate node pools; plan maintenance windows and Pod impact. |
| **GKE Dataplane V2** | GKE's eBPF data plane enforces Kubernetes NetworkPolicy natively. | Differs in `ipBlock`/Pod IP handling and observability tools; never run legacy Calico enable commands on Dataplane V2 clusters. |

On **GKE Autopilot**, GKE manages the data plane/networking choices; NetworkPolicy behavior still depends on the active cluster mode and version. Do not assume Autopilot permits customizing node-level CNIs or installing Calico as on self-managed Standard clusters.

### 5.2. Dataplane V2 Is Not "Calico Plus Extras"

**GKE Dataplane V2** is a distinct data plane with its own enforcement and observability stack. If a cluster uses Dataplane V2, do not follow legacy "enable Calico network policy" instructions. Review implementation limits and semantics for your release channel/version.

Likewise, never install a second CNI or DaemonSet tinkering with the data plane just because a NetworkPolicy seems inactive. Switching networking engines impacts the entire cluster and requires a dedicated migration plan.

### 5.3. Inspecting Cluster Configuration with gcloud

~~~bash
PROJECT_ID="retail-lab"
REGION="asia-southeast1"
CLUSTER="retail-gke"

# READ-ONLY: identify the cluster and active data plane mode.
gcloud container clusters describe "$CLUSTER" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format=yaml
~~~

Output includes fields such as `networkPolicy`, `datapathProvider`, `networkConfig`, or version-specific equivalents. Match them against your **GKE cluster mode** and current docs. `kubectl get networkpolicy` only proves the policy is stored; proving enforcement requires **actual allow and deny connectivity tests**.

### 5.4. Considerations When Enabling on a Live Cluster

For an existing Standard cluster without network policy enforcement enabled:

1. Inventory Pods/workloads, critical services, maintenance windows, and PodDisruptionBudgets.
2. Identify whether Calico or Dataplane V2 applies to your cluster.
3. Read the enablement docs for node recreation requirements, version constraints, and rollback options.
4. Test the change in a matching nonproduction environment with both allowed and blocked traffic.
5. Plan SLO protections before enabling enforcement or applying default-deny in production.

**Never assume adding `NetworkPolicy` YAML alone works** if the engine lacks support; equally, never toggle cluster-wide network policy in production without assessing node disruptions.

## 6. Preparing the Lab: Namespaces, Labels, and Workloads

### 6.1. Three-Tier Context

We use three namespaces:

~~~text
retail-web
  Pod: app=storefront
  Service: storefront

retail-api
  Pod: app=orders-api
  Service: orders-api (TCP 8080)

retail-data
  Pod: app=postgres (lab-only)
  Service: postgres (TCP 5432)
~~~

In production, Cloud SQL should be evaluated instead of a self-managed database Pod where appropriate, but we use a lab PostgreSQL Pod inside the cluster here to illustrate **Pod-to-Pod rules**. Later we include an egress example **to a Cloud SQL private IP outside the cluster**.

### 6.2. Creating and Labeling Namespaces

The following commands **modify the Kubernetes cluster**:

~~~bash
# WRITE: run only in the verified lab cluster context.
kubectl create namespace retail-web
kubectl create namespace retail-api
kubectl create namespace retail-data

# WRITE: namespace labels used by NetworkPolicy selectors.
kubectl label namespace retail-web access-zone=web --overwrite
kubectl label namespace retail-api access-zone=api --overwrite
kubectl label namespace retail-data access-zone=data --overwrite

# READ-ONLY: verify namespace labels.
kubectl get namespaces --show-labels
~~~

`kubectl create namespace` returns `AlreadyExists` if rerun on existing namespaces. In existing environments, never "quick-fix" labels referenced by admission policies, CI/CD, or other NetworkPolicies without checking impact. **Restrict permission to edit namespace labels**, as a label change can open new traffic paths.

### 6.3. Verifying Target Pod Labels

~~~bash
# READ-ONLY: confirm which Pods selectors actually match.
kubectl -n retail-web get pods --show-labels
kubectl -n retail-api get pods --show-labels
kubectl -n retail-data get pods --show-labels

# READ-ONLY: where do Service endpoints point?
kubectl -n retail-api get service orders-api
kubectl -n retail-api get endpointslices \
  -l kubernetes.io/service-name=orders-api
~~~

**NetworkPolicy selects Pods by labels**, not Kubernetes Services by name. A Service named `orders-api` selecting Pods labeled `app=order-worker` will not match a policy selecting `app=orders-api`. During troubleshooting, align **both the Service selector and the NetworkPolicy `podSelector`**.

## 7. Starting with Default-Deny

### 7.1. Default-Deny Ingress in One Namespace

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: retail-api
spec:
  podSelector: {}
  policyTypes:
    - Ingress
  ingress: []
~~~

This policy selects every Pod in `retail-api` and isolates ingress. **Egress remains unisolated** by this policy. For a lower-risk rollout, teams often isolate ingress first and validate required exceptions before isolating egress.

### 7.2. Default-Deny Both Ingress and Egress

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: retail-api
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
  ingress: []
  egress: []
~~~

This establishes **baseline isolation**. Once active, selected Pods have no allow exceptions for new connections in either direction unless **other policies** grant them. Keep in mind:

- Policies are **additive**: default-deny does not override existing allow rules.
- Node/host or system component traffic can have implementation-specific semantics; never claim a policy blocks every packet across the entire VPC.
- Applications may depend on DNS, metrics, tracing, registries/Google APIs, databases, and webhooks; turning on full deny before adding exceptions can break production.

### 7.3. Do You Need Policies in Every Namespace?

Policies are namespaced, so `default-deny-all` in `retail-api` **does not isolate `retail-web` or `retail-data`**. To apply consistent baselines across namespaces, manage separate `NetworkPolicy` objects via GitOps/Helm/Kustomize or IaC templates with clear ownership.

Standard Kubernetes NetworkPolicy is **not a cluster-scoped resource that enforces cluster-wide default-deny with a single object**. Some add-ons offer cluster-scoped policies, but verify the implementation and never confuse them with the standard API.

## 8. Allowing DNS After Isolating Egress

### 8.1. Why DNS Is Usually the First Forgotten Flow

Pods typically reach services by name, such as `orders-api.retail-api.svc.cluster.local`, or call Google APIs by hostname. When egress is isolated without a DNS allow rule, applications fail with errors like:

~~~text
lookup orders-api.retail-api.svc.cluster.local: i/o timeout
Temporary failure in name resolution
connection timeout to external API
~~~

Operators often blame the API or database when the Pod simply **cannot resolve DNS**.

### 8.2. Illustrative Policy for `kube-dns` Pods

In a cluster running **`kube-dns` Pods** with matching labels, a policy can permit `orders-api` to send DNS queries to those Pods:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns-to-kube-dns
  namespace: retail-api
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
~~~

**This sample only works when the DNS resolver actually consists of `kube-dns` Pods with those exact labels.** Before applying:

~~~bash
# READ-ONLY: inspect the actual DNS implementation.
kubectl -n kube-system get pods --show-labels
kubectl -n kube-system get services
kubectl -n retail-api exec deploy/orders-api -- cat /etc/resolv.conf
~~~

If the cluster uses **NodeLocal DNSCache, Cloud DNS for GKE, or another resolver**, the packet path and destination IP differ; the `kube-dns` Pod selector above **may not suffice**. Base your policy on the actual cluster DNS architecture and corresponding GKE docs. `kubectl exec` requires `cat` inside the running container; for minimal images without a shell, use an approved debug Pod.

### 8.3. Testing DNS

~~~bash
# READ-ONLY network probe: run only in a Pod with diagnostic tools.
kubectl -n retail-api exec deploy/orders-api -- \
  nslookup orders-api.retail-api.svc.cluster.local
~~~

If DNS succeeds while HTTP still fails, inspect source egress on TCP 8080 and destination ingress on TCP 8080. **DNS resolution and opening a TCP connection are two separate steps.**

## 9. Allowing Frontend-to-API Calls Across Namespaces

### 9.1. Ingress Policy on the API

Placed in namespace `retail-api`; allows only `app=orders-api` Pods to receive TCP 8080 from `app=storefront` Pods in namespaces labeled `access-zone=web`:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-api-allow-storefront
  namespace: retail-api
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              access-zone: web
          podSelector:
            matchLabels:
              app: storefront
      ports:
        - protocol: TCP
          port: 8080
~~~

Notice this is **a single peer combining both selectors**, creating an AND condition. Do not split them into two `-` list items, which would broaden access.

### 9.2. Egress Policy on the Frontend

If `retail-web` enforces default-deny egress, allow `storefront` to reach `orders-api`:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: storefront-egress-orders
  namespace: retail-web
spec:
  podSelector:
    matchLabels:
      app: storefront
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              access-zone: api
          podSelector:
            matchLabels:
              app: orders-api
      ports:
        - protocol: TCP
          port: 8080
~~~

If egress in `retail-web` was not yet isolated, adding this egress policy **immediately isolates egress for `app=storefront` Pods** to only what is listed across all policies. Therefore, **never apply this policy alone in production** without DNS, metrics, outbound APIs, and other dependencies storefront needs. Deploy the **complete policy set** together in one rollout plan.

### 9.3. Interpreting Outcomes

| Traffic | Allowed if corresponding default-deny is active? | Condition |
| --- | --- | --- |
| `storefront` → `orders-api:8080` | Yes, when both policies above and labels match. | Both source egress and destination ingress allow it. |
| `storefront` → `orders-api:9090` | No, unless another policy allows it. | Port 9090 is not listed. |
| `random-pod` in `retail-web` → `orders-api:8080` | No, if destination is isolated. | Does not match `app=storefront`. |
| `storefront` → `postgres:5432` | No, if destination Postgres is ingress-isolated without another allow rule. | No allow rule covers that path. |
| `orders-api` → Internet | Depends on other egress policies selecting the Pod. | Ingress policies do not restrict egress. |

Traffic permitted by NetworkPolicy can still fail due to **Kubernetes Service selectors**, Pod readiness, VPC firewalls, a service not listening on the port, or application-layer authorization.

## 10. Allowing the API to Connect to an In-Cluster Database

### 10.1. Source Side: Egress in `retail-api`

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-egress-postgres
  namespace: retail-api
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              access-zone: data
          podSelector:
            matchLabels:
              app: postgres
      ports:
        - protocol: TCP
          port: 5432
~~~

### 10.2. Destination Side: Ingress in `retail-data`

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: postgres-allow-orders-api
  namespace: retail-data
spec:
  podSelector:
    matchLabels:
      app: postgres
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              access-zone: api
          podSelector:
            matchLabels:
              app: orders-api
      ports:
        - protocol: TCP
          port: 5432
~~~

When database Pods are protected by an ingress policy, **both API egress and database ingress policies matter**. Calling Service `postgres.retail-data.svc.cluster.local:5432` does not bypass matching the **destination Pod endpoints**.

**You still need database authentication and least-privilege SQL roles.** NetworkPolicy only restricts the **TCP path**; it has no idea which SQL user is allowed to run `DROP TABLE`.

### 10.3. Database Pod Is Only a Lab Example

In production, databases often live outside the cluster on **Cloud SQL**. In that case, `podSelector: app=postgres` in `retail-data` **will not match Cloud SQL**; you must design egress toward the real private endpoint, proxy, or connection architecture. The next section details that difference.

## 11. Egress to Cloud SQL, Google APIs, and External Destinations

### 11.1. A Cloud SQL Private IP Is Not a Pod

Suppose Cloud SQL for PostgreSQL has an illustrative private IP `10.70.4.12` on a reachable route. If `orders-api` connects directly on TCP 5432 and your data plane supports `ipBlock` for that destination, an egress policy can use `ipBlock`:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-egress-cloudsql
  namespace: retail-api
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes:
    - Egress
  egress:
    - to:
        - ipBlock:
            cidr: 10.70.4.12/32
      ports:
        - protocol: TCP
          port: 5432
~~~

This is an **illustrative IP address**, not a recommendation to hardcode IPs everywhere. Always verify:

- Does Cloud SQL use **Private Service Access**, **Private Service Connect**, or another connectivity model?
- Is the backend IP stable, and do routes/peering/DNS exist?
- Does the workload connect **directly** or via the Cloud SQL Auth Proxy / connector? Proxies/connectors also call Google APIs requiring TCP 443 and DNS.
- How are IAM/Cloud SQL Client roles, database credentials, and TLS configured?
- Do namespace egress policies, VPC firewall rules, or VPC Service Controls affect the path?

A NetworkPolicy never grants IAM permissions and never establishes VPC peering or Private Service Connect.

### 11.2. Google APIs and Artifact Registry

`orders-api` may call Cloud Storage or Pub/Sub via Google APIs, while GKE nodes must reach Artifact Registry to pull images. **Distinguish where each connection originates:**

| Flow | Who initiates it? | What NetworkPolicy means |
| --- | --- | --- |
| Pod calls Cloud Storage REST API | Pod/application or Pod-local proxy. | Pod egress policy may need to permit DNS/TCP 443 per topology. |
| Pod uses Cloud SQL Auth Proxy sidecar | Pod/sidecar. | Egress must cover proxy target IPs/ports, including Google APIs if used. |
| Node pulls image from Artifact Registry | Node runtime/kubelet per architecture. | Do not treat app Pod policies as the mechanism enabling node image pulls. |
| Frontend Application LB to Pod NEG | LB/proxy/health-checker infra to backend. | Check Pod ingress and whether LB/health-check traffic is subject to enforcement; depends on network mode. |
| Pod calls Kubernetes API | Pod to API server endpoint. | May be subject to egress policies on that path, alongside Kubernetes RBAC/IAM. |

Do not lazily allow `0.0.0.0/0:443` just because an app calls Google APIs. If a broad rule is used temporarily during migration, document the exception, inspect flows, and narrow it using supported **Private Google Access / restricted VIPs, egress gateways, firewall policies, or FQDN-aware policies**.

### 11.3. FQDNs and Changing IPs

Standard NetworkPolicy **has no** selector such as:

~~~text
allow egress to api.example.com on TCP 443
~~~

For Internet services whose IPs rotate, a static `ipBlock` is brittle. GKE offers advanced FQDN traffic controls under Dataplane V2 on supported versions, yet **never write FQDN YAML as if it were standard NetworkPolicy**. Read the GKE FQDN Network Policies docs, DNS caching limits, and enforcement caveats before using it.

### 11.4. Cloud NAT and VPC Firewalls Still Matter

NetworkPolicy governs Pod traffic at the data plane, whereas **VPC firewall rules** govern VM/node-level network flows, endpoints, network tags/service accounts, and hierarchical policies. **Cloud NAT** provides outbound SNAT when configured—it is not a per-Pod allow-list.

Example when a Pod calls the Internet:

~~~text
Pod egress allowed by NetworkPolicy
       ↓
VPC route + egress firewall/policy
       ↓
Cloud NAT/proxy (if needed)
       ↓
External API
~~~

If any layer blocks the packet, the connection fails. A Kubernetes allow policy does not open VPC firewall rules or create NAT.

## 12. Flows from Ingress/Gateway and Health Checks to Pods

### 12.1. Do Not Confuse the Client IP with the Packet Source Reaching the Pod

When a browser hits `https://shop.example.com`, the path can look like:

~~~mermaid
flowchart LR
    C["Internet client"] --> LB["Application Load Balancer"]
    LB --> BS["Backend service"]
    BS --> NEG["GKE NEG / Pod endpoints"]
    NEG --> P["storefront Pod"]
    H["Health checker"] -. "Probe per LB type" .-> P
~~~

A Pod often sees a source address **different from the original client IP** due to proxying or NAT. With GKE Ingress/Gateway and container-native load balancing, verify whether the backend uses **Pod NEGs, nodes/NodePort, or another backend type**. `namespaceSelector`/`podSelector` **cannot match a Google Front End or external Envoy proxy** outside the cluster as if it were a labeled Pod.

### 12.2. Allowing Ingress for Load-Balanced Backends

To design an ingress policy for Pods behind an Application Load Balancer:

1. Identify the LB type: **global/regional external**, **internal**, Gateway/Ingress implementation, and GKE data plane.
2. Trace the backend path: direct Pod IPs, nodes, proxy-only subnets, health checkers, and required source ranges.
3. Check GKE NetworkPolicy guidance for your LB to see how health-check and proxy traffic interact with enforcement.
4. Write source `ipBlock` rules only after confirming observed source IPs and LB IP/NAT behavior.
5. Test **both real user requests and health checks** after applying changes—never test only with `curl` from another in-cluster Pod.

Applying `default-deny-ingress` to `storefront` without allowing LB traffic can mark backends unhealthy and fail user requests. **Never open `0.0.0.0/0` to every Pod just to turn health checks green** when security requires a narrower scope.

### 12.3. Ingress Policy vs. Application Authorization

Even when an ingress policy permits only the LB proxy, **any Internet user passing through that proxy** can still invoke the API if the endpoint is public and lacks app-level authentication. For public endpoints, pair HTTPS, OAuth/JWT, Cloud Armor, IAP (where appropriate), rate limiting, and application-level authorization.

**NetworkPolicy does not replace a Web Application Firewall or order-ownership checks.**

## 13. Validating NetworkPolicy Before and After Applying

### 13.1. Verify Context and Permissions

~~~bash
# READ-ONLY: check current context so you never mix up production and lab.
kubectl config current-context
kubectl get namespaces --show-labels

# READ-ONLY: verify permission to create policies.
kubectl auth can-i create networkpolicies.networking.k8s.io \
  -n retail-api

# READ-ONLY: list existing policies.
kubectl get networkpolicies -A
~~~

If `kubectl get networkpolicy` returns Forbidden, that is a Kubernetes RBAC issue—**not proof that the data plane is blocking Pod traffic**.

### 13.2. Review YAML Before Deploying

Assuming manifests are stored in reviewed Git/IaC directories:

~~~bash
# READ-ONLY server-side validation; saves no new policies.
kubectl apply --dry-run=server -f network-policies/ \
  --namespace=retail-api

# WRITE: run only after changes and target namespaces are approved.
kubectl apply -f network-policies/
~~~

Note that `metadata.namespace` inside each file takes precedence during resource application, so **do not expect `--namespace` to fix a file declaring the wrong namespace**. `--dry-run=server` checks API schema, permissions, and admission, **not selector intent, live connectivity, or SLOs**.

### 13.3. Inspect Applied Policies

~~~bash
# READ-ONLY: inspect policies stored by the API server.
kubectl -n retail-api get networkpolicy
kubectl -n retail-api describe networkpolicy orders-api-allow-storefront
kubectl -n retail-api get networkpolicy \
  orders-api-allow-storefront -o yaml

# READ-ONLY: inspect Pod labels and Service endpoints.
kubectl -n retail-api get pods --show-labels
kubectl -n retail-api get endpointslices
~~~

If a policy looks right yet has no effect, verify the **GKE policy enforcement provider** in cluster config and run real network probes. Never draw conclusions from `kubectl get` alone.

### 13.4. Allow and Deny Test Matrix

A proper test suite verifies both **permitted flows** and **flows that must fail**:

| Test source | Destination | Expected result | Purpose |
| --- | --- | --- | --- |
| `storefront` | `orders-api:8080` | Succeeds. | Primary application allow path. |
| Any non-frontend Pod | `orders-api:8080` | Fails when API is isolated. | Blocks lateral movement. |
| `storefront` | `postgres:5432` | Fails when DB is isolated. | Prevents bypassing the API to hit the DB. |
| `orders-api` | `postgres:5432` | Succeeds. | Data-tier allow path. |
| `orders-api` | DNS resolver | Succeeds. | Preserves service name resolution. |
| `orders-api` | Unapproved external endpoint | Fails when egress is properly isolated. | Validates egress boundary. |
| Ingress/Gateway → `storefront` | HTTP plus health checks | Succeeds per architecture. | Confirms user and probe traffic work. |

Results depend on **the full set of policies active across both namespaces**, the engine, namespace labels, and network topology. If DB ingress is not yet isolated, `storefront → postgres` can still succeed even when the API has an ingress policy.

### 13.5. Running a Network Probe in the Lab

Where policies permit, a debug Pod containing `curl`, `nc`, or `nslookup` can test:

~~~bash
# READ/CONNECT: run from an existing Pod that includes curl.
kubectl -n retail-web exec deploy/storefront -- \
  curl -sS --connect-timeout 3 \
  http://orders-api.retail-api.svc.cluster.local:8080/healthz
~~~

Minimal production images often omit `curl`; in that case, use an approved debug image, ephemeral debug container, or network observability tools. If you launch a **new test Pod**, mind its labels: a Pod labeled `debug=true` **will not match a policy selecting `app=storefront`**. That difference is worth testing intentionally, not a policy bug.

Never treat a timeout as automatic proof that NetworkPolicy blocked the packet. Timeouts also happen from DNS failures, wrong Service selectors, unready Pods, wrong ports, VPC firewalls, or app crashes.

## 14. Rolling Out Policies Safely in Production

### 14.1. Why Can a Rushed Default-Deny Cause an Outage?

A healthy production service typically has **far more network dependencies than the high-level business diagram shows**:

- DNS.
- Metrics / Prometheus / OpenTelemetry collectors.
- Service mesh sidecars and control planes.
- Cloud SQL connectors or Auth Proxy.
- Cloud Storage, Pub/Sub, Secret Manager APIs.
- Admission webhooks and load balancer health checks.
- Log exporters, tracing backends, or license servers.

Applying `default-deny-all` in production without inventorying dependencies can leave **Pods Running and Ready while real user transactions fail**. Local liveness/readiness probes often miss blocked outbound dependencies.

### 14.2. Phased Rollout Plan

1. **Discover:** map the traffic matrix from architecture, logs, and observed flow telemetry.
2. **Classify:** tag mandatory business flows, platform/infra flows, debug-only flows, and unwanted paths.
3. **Prepare:** author narrow allow policies, review labels/namespaces/ports, and verify enforcement.
4. **Test in staging:** deploy the same policy bundle to an environment matching workloads and topology.
5. **Canary:** start with a less sensitive namespace or Pod group; verify SLIs plus negative deny tests.
6. **Enforce default-deny:** roll out per namespace within scheduled windows and approved rollback paths.
7. **Observe:** monitor 5xx rates, p95/p99 latency, DNS, DB connection errors, and denied-flow logs where supported.
8. **Refine:** tighten temporary exceptions, record owners, and update the traffic matrix.

Standard Kubernetes NetworkPolicy **has no built-in global audit-only mode**. Certain tools or data planes provide dedicated observability or dry-run simulators; never assume `kubectl apply --dry-run=server` dry-runs live packet enforcement.

### 14.3. Controlled Rollback

When a new policy triggers an outage:

- Identify the recently modified policy/namespace and the exact blocked flow.
- If authorized, add a **narrow allow rule** for the missing dependency instead of tearing down all defenses.
- If fast recovery fails and rollback is approved, revert the exact commit/manifests applied.
- Verify no unintended broad allow policies remain after rollback.
- Record an incident postmortem: root cause, wrong label, wrong port, or missed dependency.

**Never run `kubectl delete networkpolicy --all -A` as a blanket fix.** That wipes out all Pod segmentation across every team's namespaces. Rollbacks must target only the specific objects owned by your pipeline or team.

### 14.4. GitOps and Drift Prevention

NetworkPolicy manifests fit GitOps/IaC workflows cleanly:

~~~text
Git review → policy manifests → CI schema validation
    → staging connectivity tests → approval
    → production apply → telemetry/rollback
~~~

Clarify who owns namespace labels, who owns NetworkPolicies, and who can create broad RoleBindings or permissive policies. Never let a GitOps sync loop and another controller fight over the same resource.

## 15. How NetworkPolicy Differs from Other Security Controls

| Mechanism | Scope | Example problem it solves |
| --- | --- | --- |
| **Kubernetes NetworkPolicy** | Pod L3/L4 traffic by selectors/IPs/ports. | Only `storefront` may call `orders-api:8080`. |
| **VPC firewall / hierarchical policies** | VPC, VM, subnet, and supported endpoint flows. | Restricts sources reaching GKE nodes, proxy-only subnets, or DB endpoints. |
| **Kubernetes RBAC** | Who can call the Kubernetes API to read/edit resources. | Developers cannot delete `Deployment` or `Secret` objects. |
| **Google Cloud IAM** | Permissions on Google Cloud resources/APIs and admin identities. | Workers cannot read buckets or modify project IAM. |
| **Workload Identity Federation for GKE** | Pod identity used when calling Google APIs. | `orders-api` Pods can read only approved Secret Manager secrets. |
| **Cloud Armor / WAF** | HTTP(S)/edge filtering depending on LB topology. | Blocks or rate-limits malicious Internet requests. |
| **Service mesh / mTLS / L7 authorization** | Application/service identity and L7 policy. | Only authenticated services can invoke payment endpoints. |
| **Private GKE control plane** | Kubernetes API management path. | SREs manage the cluster only via approved endpoints/paths. |
| **Cloud NAT / egress gateway** | Outbound routing and centralized egress control per architecture. | Workloads reach the Internet via controlled egress points. |

**Never treat one layer as a substitute for another.** A NetworkPolicy allowing TCP to Cloud SQL does not grant SQL privileges; Kubernetes RBAC allowing Pod reads does not prove HTTP ingress is secure.

## 16. Observing Traffic and Troubleshooting Blocked Flows

### 16.1. Common Symptoms

| Symptom | Possible cause | Check next |
| --- | --- | --- |
| Pod calls to a service by name fail | DNS egress blocked or unexpected DNS resolver | `/etc/resolv.conf`, DNS implementation, TCP/UDP 53 rules |
| Direct Pod IP works, Service hostname fails | DNS or Service selector/endpoint routing | `nslookup`, `get svc`, `get endpointslices` |
| `storefront` → `orders-api` times out | Missing web egress, missing API ingress, or label/port mismatch | Policies in both namespaces, Pod labels, and ports |
| Debug Pod blocked while `storefront` works | Debug Pod lacks label `app=storefront` | `kubectl get pods --show-labels`, policy selectors |
| Only one namespace's Pods can connect | Mismatched namespace label or policy scope | Labels and AND/OR peer nesting |
| API cannot reach Cloud SQL | Missing egress, wrong private IP, DNS/PSC/PSA/routing, IAM/DB auth | Policy, real endpoint, Cloud SQL logs, and networking |
| App returns 503 after default-deny | Blocked dependency, readiness probe, or health checker | SLIs, backend health, logs, traces, flow telemetry |
| NetworkPolicy created, deny test still connects | Enforcement disabled, overlapping allow policy, or host-traffic exception | Cluster data plane, full policy list, real source/dest |
| `ipBlock` fails to match Pod IPs on Dataplane V2 | Dataplane V2 does not match Pod traffic with `ipBlock` | Switch to `podSelector`/`namespaceSelector` |
| SREs cannot run `kubectl` against cluster | Control-plane endpoint/IAM/RBAC, usually unrelated to Pod policies | Verify Kubernetes API reachability and permissions first |
| DNS healthy, HTTP returns `403` | Application, IAM, mesh, or WAF denial | HTTP logs, tokens, authorization; don't blame NetworkPolicy for everything |
| Metrics vanish after applying policy | Collector or exporter lost ingress/egress path | Scrape targets, labels, namespaces, and ports |

### 16.2. Layered Troubleshooting Workflow

1. **Right cluster/context?** Avoid confusing staging and production.
2. **Is the engine enforcing?** Inspect GKE data plane / `networkPolicy` config and run a controlled deny test.
3. **Which Pods are source and destination?** Gather Pod IPs, namespaces, labels, Service endpoints, and app ports.
4. **Which direction is isolated?** List every policy selecting the source (egress) and destination (ingress).
5. **Do peer selectors match?** Check AND/OR indentation, namespace labels, and Pod labels.
6. **Is it DNS/IP/NAT?** Resolve names, check actual IPs, Google APIs/PSC/Cloud SQL paths, and Service routing.
7. **Is an outer layer blocking it?** Check VPC firewalls, proxies, NetworkPolicy extensions, service mesh, IAM, and the app itself.
8. **Are SLIs recovered?** Verify end-to-end user requests rather than stopping at a single ping/curl.

### 16.3. Read-Only Inspection Commands

~~~bash
# READ-ONLY: confirm source and destination Pods.
kubectl -n retail-web get pods -o wide --show-labels
kubectl -n retail-api get pods -o wide --show-labels
kubectl -n retail-data get pods -o wide --show-labels

# READ-ONLY: all policies across the cluster.
kubectl get networkpolicies -A
kubectl -n retail-api describe networkpolicy

# READ-ONLY: Service endpoints.
kubectl -n retail-api get services
kubectl -n retail-api get endpointslices
~~~

On GKE Dataplane V2 clusters, you can enable **Network Policy Logging / observability** and GKE diagnostic tools where supported. Never assume every blocked packet is logged by default; log volume, sampling, retention, and costs require deliberate configuration.

### 16.4. Advanced Verification Edge Cases

**Pods using `hostNetwork`:** policy behavior can differ from standard Pods; verify against your specific CNI/data plane. Never use `hostNetwork` in production workloads as an intentional bypass.

**Service DNAT/SNAT:** addresses seen by network policies can depend on implementation and processing order, especially with NodePort/LoadBalancer, external traffic, or certain egress paths. Test real network paths instead of inferring purely from ClusterIPs.

**Pod label permissions:** anyone allowed to attach `app=storefront` to a Pod can place that Pod inside an allowed group. NetworkPolicy is part of a **multi-tenant** design, yet it does not replace RBAC or admission policies controlling who deploys Pods and edits labels.

**Multiple policies:** a seemingly tight policy can be widened by another policy because allow rules form a union. When auditing a Pod, inspect **every NetworkPolicy selecting that Pod in the relevant direction**, not just the one named `default-deny`.

## 17. Production Scenario: Segmenting an E-Commerce System

### 17.1. Context

An organization operates:

- Namespace `retail-web`: `storefront`, accessed by users through an Application Load Balancer.
- Namespace `retail-api`: `orders-api`, communicating with **Cloud SQL for PostgreSQL**.
- Namespace `retail-batch`: image-processing workers reading/writing **Cloud Storage** and pulling jobs from Pub/Sub.
- Namespace `retail-observability`: metrics/trace collectors.
- **Artifact Registry** serving images to GKE node pools.
- **Cloud Run** hosting external APIs that call `orders-api` via an approved gateway.

Security requirements: the frontend must not reach the database directly, image workers must not call payment APIs, only collectors may scrape metrics, and Pods may egress only to necessary services. Reliability requirements: during sales peaks, never disrupt DNS, health checks, Google APIs, or data paths.

### 17.2. Flow Design

~~~mermaid
flowchart TB
    USERS["Browser clients"] --> LB["HTTPS Application Load Balancer"]
    LB --> WEB["storefront Pods"]
    WEB -->|"HTTP 8080"| API["orders-api Pods"]
    API -->|"PostgreSQL 5432 over private network"| SQL["Cloud SQL"]
    BATCH["Image workers"] -->|"HTTPS via approved egress"| STORE["Cloud Storage / Pub/Sub"]
    OBS["Telemetry collector"] -. "Approved metrics port" .-> WEB
    OBS -.-> API
    API -. "No allow rule" .-> BATCH
    WEB -. "No allow rule" .-> SQL
~~~

Do not naively draw "NetworkPolicy blocks Cloud Run": Cloud Run sits outside the cluster, so Cloud Run-to-API traffic depends on gateways/LBs, real source IPs, Kubernetes policies, and authentication. Design the full end-to-end path rather than assuming Cloud Run has Pod labels.

### 17.3. Three-Phase Plan

**Phase 1 — Discovery and validation:**

1. Inventory namespace/Pod/Service labels, Service endpoints, and external dependencies.
2. Build the traffic matrix; collect logs or network flow telemetry if available.
3. Check the cluster's GKE data plane and confirm how enforcement works.
4. Pilot policies with `retail-batch` in staging, as it is less latency-sensitive than live checkout.

**Phase 2 — Apply isolation:**

1. Add allow policies for DNS and required infrastructure flows.
2. Isolate `orders-api` ingress, then frontend egress.
3. Add Cloud SQL egress to the real private endpoint, plus Google APIs/Pub/Sub egress per network topology and security policy.
4. Isolate ingress/egress for batch workers, tracking exceptions with owners and expiration dates.
5. Verify live Application LB / health check flows and Cloud Run traffic through the gateway.

**Phase 3 — Operations:**

1. Apply default-deny per namespace once all exceptions are verified.
2. Run allow/deny connectivity tests in CI/staging and synthetic checks in production.
3. Watch 5xx rates, p95 checkout latency, DB connection errors, DNS failures, Pub/Sub backlogs, and metric exporters.
4. Review policies whenever app topology, Service ports, node networking, or database endpoints change.

### 17.4. Ownership and Responsibilities

| Team | Appropriate permissions | Guardrails |
| --- | --- | --- |
| Platform/network | Manage GKE data plane and namespace policy baselines. | Never alter CNIs/nodes outside change windows; review egress exceptions. |
| Application team | Propose required app flows and run tests. | Cannot alter namespace security labels or create cluster-wide allow-alls. |
| Security team | Audit policy drift and unexpected flows. | Approve exceptions; restrict RBAC over policies and labels. |
| CI/CD deployer | Apply approved policies/manifests in allowed namespaces. | Needs no project-wide Owner; maintain audit trails and rollback commits. |
| SRE/on-call | Read logs/metrics and execute approved recovery runbooks. | Resolve outages without disabling all defenses. |

In GitOps, separate **who defines desired state** from **the pipeline identity that applies it**; anyone allowed to edit Namespace labels can alter allowed sources without ever touching a NetworkPolicy file.

### 17.5. Incident Test Scenarios

| Simulated incident | Expected outcome |
| --- | --- |
| Pod in `retail-batch` tries calling PostgreSQL private endpoint | Blocked without a matching namespace/Pod/destination allow rule. |
| `orders-api` resolves DNS hostnames after default-deny | DNS continues working through the approved resolver. |
| CI deploys a new version with changed Pod labels | Policy is reviewed/updated; never silently break a valid service. |
| A namespace is mistakenly labeled `access-zone=web` | Alert/review catches the namespace label change; no unauthorized Pods enter sensitive paths. |
| L7 backend shows Healthy yet checkout fails | Check dependencies/egress and SLIs rather than relying only on LB health. |
| Metrics collector gets blocked | Restore the exact metrics port/source without opening all ingress. |
| Cloud SQL changes connection method | Update topology, routes, IAM, and network policies for the new endpoint. |

## 18. Cost, Monitoring, and Change Management

### 18.1. Does NetworkPolicy Generate a Separate Line Item?

Kubernetes NetworkPolicy is a policy API. GKE infrastructure costs still come from **nodes, clusters, networking, logging/telemetry, and add-on security tools**; advanced observability features can affect log volume and operational overhead. Never claim a NetworkPolicy object has a fixed price or is universally free of indirect costs across every feature set.

Factors to measure:

- Number of policies/namespaces and maintenance/testing effort as app topologies evolve.
- Network Policy Logging / flow telemetry: record volume, retention, and alerting costs.
- Data plane latency/CPU overhead relative to SLOs at large policy scales.
- Egress through Cloud NAT, VPC data transfer, or gateways.
- Mean time to resolve outages caused by misconfigured rules and user impact.

### 18.2. Track Security and Application SLIs Together

| Signal group | Examples |
| --- | --- |
| **Security** | Denied flows by namespace/Pod where logged, policy drift, sensitive label edits. |
| **Network** | DNS errors, TCP resets/timeouts, egress gateway logs, NAT saturation. |
| **Application** | HTTP 5xx, p95/p99 latency, checkout success rate, batch backlog. |
| **Platform** | Pod readiness, GKE data plane health, Deployment rollouts, node conditions. |
| **Cost** | Logging volume, network transfer, node capacity, egress services. |

A "deny event" can simply prove a policy is blocking unwanted traffic—**it is not automatically an incident**. Conversely, a blocked legitimate flow breaking checkout is a real SLO incident even without detailed deny logs.

### 18.3. Audit Principles

Preserve evidence of:

1. Who approved the traffic matrix and exceptions.
2. Which commit changed NetworkPolicies or namespace labels.
3. Who applied manifests to production and via which pipeline/principal.
4. Preflight results, allow/deny test runs, and pre/post-rollout metrics.
5. Rollback timestamps, reasons, and blast radius.

**Kubernetes audit logs** and **Cloud Audit Logs** differ in scope and configuration; never assume every change or dropped packet is logged by default. Check which logging features, retention policies, viewer permissions, and data-governance rules apply in your GKE environment.

## 19. Self-Practice Exercises

### Exercise 1 — Namespace Isolation vs. NetworkPolicy

A cluster has namespaces `web`, `api`, and `payments` with no policies applied. Can you claim `web` cannot reach `payments` Pods simply because they live in separate namespaces? Explain namespace separation versus network isolation.

**Hint:** namespaces isolate resource organization and RBAC; Kubernetes NetworkPolicy is what enforces Pod network allow/deny rules when an enforcement provider is active.

### Exercise 2 — Ingress or Egress?

Pod A in `web` calls Pod B in `api`. A has an egress policy allowing only TCP 443; B has an ingress policy allowing only TCP 8080 from A. Will a client call on TCP 8080 from A to B succeed? Which side needs updating? What would change if A had no egress isolation?

### Exercise 3 — AND/OR

Compare the two snippets:

~~~yaml
# Option A: one peer with two selectors
from:
  - namespaceSelector:
      matchLabels: {access-zone: web}
    podSelector:
      matchLabels: {app: storefront}
~~~

~~~yaml
# Option B: two independent peers
from:
  - namespaceSelector:
      matchLabels: {access-zone: web}
  - podSelector:
      matchLabels: {app: storefront}
~~~

**Question:** which option allows only `storefront` Pods inside web namespaces? Which unintentionally opens access to all Pods in web namespaces?

### Exercise 4 — Default-Deny All Directions

Write a `default-deny-all` manifest for namespace `retail-batch`; explain why DNS policies and data-service egress rules are still needed. Give an example where system traffic can depend on implementation and should not be assumed universally blocked.

### Exercise 5 — DNS After Policy Enforcement

`orders-api` can reach `10.70.4.12:5432` by IP yet fails when using the database hostname. Distinguish a DNS policy issue, resolver config issue, and IP connectivity issue. If the cluster uses NodeLocal DNSCache, should you blindly reuse the `kube-dns` Pod selector policy from section 8?

### Exercise 6 — Cloud SQL and Identity

A Pod has an egress policy for TCP 5432 to Cloud SQL's private IP, yet gets `password authentication failed`. Does this prove the NetworkPolicy is wrong? Which database/IAM controls should you inspect?

### Exercise 7 — GKE Dataplane V2

Why avoid `ipBlock` for selecting Pod IP ranges in GKE Dataplane V2? Redesign a policy allowing only namespace `retail-web` and Pod label `app=storefront` to call the API, and list tests proving enforcement.

### Exercise 8 — Allowing the Load Balancer

After applying default-deny ingress in `retail-web`, the external Application Load Balancer returns 503. List the questions you must answer about backend NEGs/nodes, health-checker/proxy sources, and NetworkPolicies before adding an allow rule. Why shouldn't you blindly open TCP 8080 to all IPs?

### Exercise 9 — Another Policy Widens Access

A namespace has `default-deny-all` and `allow-api-from-web`. Another teammate adds a policy with an ingress rule containing `from: []` and `ports: [{protocol: TCP, port: 8080}]`. What happens to the permitted source set? Contrast **`from: []` inside a rule** with **`ingress: []` at the `spec` level**, and explain why a policy's name does not reveal its true security posture.

**Hint:** `from: []` or omitting `from` inside **an ingress rule** imposes no source restriction for that rule; `ingress: []` means the policy contains no ingress allow rules. Because policies selecting a Pod merge by union, one broad rule opens traffic despite a default-deny policy.

### Exercise 10 — Production Rollout

Propose a NetworkPolicy rollout plan for `retail-api` with a 99.9% SLO, dependencies on Cloud SQL/Pub/Sub/Secret Manager, health checks, and OpenTelemetry. Specify traffic discovery, policy ordering, test timing, approvers, and how to roll back without deleting another team's policies.

## 20. Pre-Production Checklist

| Item | What to confirm |
| --- | --- |
| **GKE data plane** | Cluster uses Calico, Dataplane V2, or another supported provider, and enforcement actually works. |
| **Standard/Autopilot** | Network policy features and node/CNI constraints match cluster mode and version. |
| **Traffic matrix** | Sources, destinations, namespaces, labels, ports, protocols, and owners are documented. |
| **Default isolation** | Default-deny applied to the right namespaces and directions without breaking dependencies. |
| **Selector logic** | `podSelector`/`namespaceSelector` AND/OR logic verified with no YAML indentation widening. |
| **Namespace labels** | Label edit permissions restricted so tenants cannot add themselves to allowed groups. |
| **Pod labels** | Deployment labels and Service selectors match policy selectors. |
| **DNS** | Actual resolver (`kube-dns`/NodeLocal/Cloud DNS) and TCP/UDP 53 handled accurately. |
| **Database** | Cloud SQL / private endpoint / Pod DB, ports, routes, IAM/DB auth, and TLS aligned with architecture. |
| **Google APIs** | Egress, DNS, PGA/NAT/PSC, node image-pull identity, and Pod runtime identity distinguished. |
| **Ingress/Gateway** | LB backends, health checks, proxy sources, and Pod ingress policies tested end to end. |
| **L7 & IAM** | NetworkPolicy does not replace mTLS, service authorization, RBAC, or Google IAM. |
| **Testing** | Both positive and negative connectivity tests run against the traffic matrix. |
| **Rollout** | Staging, canary, approvals, SLO monitoring, and controlled rollback in place. |
| **Audit/observability** | Policy changes, label changes, flow telemetry where supported, logs, and incident evidence. |
| **Cost** | Logging, network egress, node performance, and operational overhead accounted for. |

## 21. Official References and Key Takeaways

Enforcement capabilities, Dataplane V2 features, NetworkPolicy logging, FQDN-aware policies, and Service/load-balancer traffic handling can vary across GKE versions. Before applying policies to a live cluster, verify current documentation:

- [Kubernetes Network Policies — concepts](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [GKE network policy overview](https://cloud.google.com/kubernetes-engine/docs/concepts/network-policy)
- [Configure network policies in GKE](https://cloud.google.com/kubernetes-engine/docs/how-to/network-policy)
- [GKE Dataplane V2 overview](https://cloud.google.com/kubernetes-engine/docs/concepts/dataplane-v2)
- [GKE FQDN network policies](https://cloud.google.com/kubernetes-engine/docs/how-to/fqdn-network-policies)
- [GKE VPC-native clusters](https://cloud.google.com/kubernetes-engine/docs/concepts/alias-ips)
- [GKE Ingress and load balancing](https://cloud.google.com/kubernetes-engine/docs/concepts/ingress)
- [Workload Identity Federation for GKE](https://cloud.google.com/kubernetes-engine/docs/concepts/workload-identity)
- [Cloud SQL private IP connectivity](https://cloud.google.com/sql/docs/postgres/private-ip)
- [GKE troubleshooting](https://cloud.google.com/kubernetes-engine/docs/troubleshooting)
- [Kubernetes NetworkPolicy API](https://kubernetes.io/docs/reference/kubernetes-api/policy-resources/network-policy-v1/)

**Core takeaway:** NetworkPolicy is a **Pod-level L3/L4 allow-list**, scoped to a namespace and merged additively. Protection works only when the GKE data plane enforces policies, selectors match the exact Pods and namespaces, and both ingress and egress are designed consistently. Start from a traffic matrix, test default-deny alongside required exceptions (especially DNS, load balancers, and data paths), and keep IAM, RBAC, VPC firewalls, and application-layer controls in place as independent layers of defense. Operational success is measured by **unauthorized flows being blocked while legitimate transactions continue meeting SLOs**.
