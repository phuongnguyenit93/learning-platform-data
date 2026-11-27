# Network Policies and Controlling Pod-to-Pod Communication

An e-commerce application running on Azure Kubernetes Service (AKS) typically spans multiple components: a frontend receiving user requests, an API processing orders, a database storing data, and workers running background tasks. Even when pods reside in different namespaces, **separating namespaces does not automatically block network traffic between them**. If a cluster has no network policies applied and lacks enforcement controls, a compromised pod can attempt to connect to many services it has no reason to reach.

**Kubernetes NetworkPolicy** declares which **Layer 3 / Layer 4** network connections are allowed to or from pods by label, namespace, IP range, and port/protocol. On AKS, policies must be enforced by a **supported network policy engine / dataplane**. Successfully creating YAML resources is not enough to conclude traffic is blocked.

This lesson belongs to the **Azure Kubernetes Service Fundamentals** chapter along the Microsoft Azure learning path: from subscriptions, resource groups, Microsoft Entra ID, and virtual networking to compute, storage, and data, then deploying, monitoring, protecting, and controlling costs of an application architecture. The focus is turning **least privilege in pod-to-pod networking** into verifiable rules.

## Learning objectives

After this lesson, you can:

1. Explain why namespaces, Services, and Azure NSGs do not automatically replace Kubernetes NetworkPolicy.
2. Understand **default allow**, **default deny**, **Ingress/Egress** allow-lists, and how multiple policies combine.
3. Use **`podSelector`**, **`namespaceSelector`**, **`ipBlock`**, **`ports`**, and **`policyTypes`** accurately.
4. Design a three-tier flow—frontend → API → database—while blocking unnecessary connections.
5. Open DNS egress and essential infrastructure connectivity in a controlled way.
6. Distinguish Azure CNI, Cilium dataplane, and network policy engines in AKS.
7. Apply policies in a test environment and verify both allowed and denied paths.
8. Troubleshoot issues after enabling policies without breaking DNS, telemetry, or ingress.

## 1. Why protect pod-to-pod communication?

In Kubernetes, an application can span multiple namespaces to organize teams, permissions, and lifecycles:

~~~text
AKS cluster
  |
  +-- Namespace: shop-web
  |     +-- frontend pods
  |
  +-- Namespace: shop-api
  |     +-- orders-api pods
  |
  +-- Namespace: shop-data
        +-- database pods
~~~

A legitimate frontend must call the API on port 8080, yet **has no need to reach the database directly** on port 5432. The API needs the database, while a random utility pod in another namespace should not share that access. When every path is open, compromising the frontend lets an attacker probe the database over the internal cluster network.

**NetworkPolicy narrows the connectivity surface**, limiting *lateral movement* inside the cluster. It is not a full application firewall and never replaces authentication, authorization, TLS, secret management, or data protection controls.

### Three design questions

1. **Who may initiate?** Which source pods/namespaces can open connections?
2. **Where may they go?** Which destination pods/namespaces should receive traffic?
3. **Over which protocol and port?** TCP 8080, TCP 5432, UDP/TCP 53, or another port?

With sound rules, only required paths are permitted. Sitting in the same VNet or behind ClusterIP Services does not by itself create a security boundary.

## 2. Where is NetworkPolicy enforced in AKS?

Kubernetes defines the **`networking.k8s.io/v1`** API, kind **`NetworkPolicy`**. The API expresses intent, whereas permitting or dropping packets is performed by a **compatible network plugin/dataplane or policy engine**.

AKS supports multiple networking models and components across versions, regions, and cluster configurations. Key names you may encounter:

- **Azure CNI** and its pod-to-Azure-network modes, such as Azure CNI Overlay in supported configurations.
- **Azure CNI Powered by Cilium**: a Cilium-based dataplane capable of enforcing standard Kubernetes NetworkPolicies in supported models.
- **Network policy engines** such as Azure Network Policy Manager or Calico in AKS-supported environments/configs.

**Never equate Azure CNI with Azure Network Policy Manager**, nor assume "having Azure CNI" means "having Cilium." The network plugin, pod IP allocation mode, dataplane, and policy enforcement engine are related yet distinct concepts.

### Prerequisites to confirm before applying policies

| What to verify | Why it matters |
|---|---|
| Kubernetes/AKS version | Affects feature support and upgrade compatibility |
| Network plugin and plugin mode | Determines pod IP and routing model |
| Network dataplane / policy engine | Confirms whether Kubernetes NetworkPolicy is enforced |
| Linux / Windows node pools | Policy support and features can differ |
| CNI/Overlay/Pod CIDR/VNet CIDR | Clarifies packet paths and routing |
| Ingress controller and service mesh | May introduce special paths to test |
| DNS / observability agents | Essential infrastructure paths must keep working |
| Cluster admin permissions | Protects policy edits and rollback workflows |

If a cluster **lacks a supported NetworkPolicy enforcement engine**, you can apply policies without seeing any blocking behavior. When adding or switching cluster networking, check AKS documentation for migration paths; never assume every option can be toggled on a live cluster without disruption.

## 3. NetworkPolicy is an allow-list model

In standard Kubernetes NetworkPolicy, a pod is **not isolated by NetworkPolicy** by default: if no policy selects it, NetworkPolicy places zero ingress or egress restrictions on that pod.

Once a policy selects a pod for a direction:

- **Ingress isolation:** inbound connections **to** the pod are allowed only if matched by at least one ingress rule across applicable policies.
- **Egress isolation:** outbound connections **from** the pod are allowed only if matched by at least one egress rule across applicable policies.

Standard Kubernetes NetworkPolicy uses **allow rules only**, has no deny rules, and has no priority order where a later policy overrides an earlier one.

### Both directions must agree

For a frontend pod to open a connection to an API pod when both are isolated:

1. **Frontend egress** must allow traffic to the API.
2. **API ingress** must allow traffic from the frontend.

If either side is missing, the connection fails under dataplane enforcement.

~~~text
frontend pod                  api pod
shop-web                      shop-api
    |                            ^
    |  Frontend egress: allow    |
    +------ TCP/8080 ------------+
           API ingress: allow

Missing either side -> connection fails as expected
~~~

### Policies combine additively (union)

If two policies select the API pod—one allowing frontend and another allowing monitoring—then **both sources** are allowed. A default-deny policy cannot "veto" an allow rule in another policy.

Therefore:

- Never rely on **YAML apply order** to resolve conflicts.
- Never assume "a stricter new policy overrides an old policy."
- When unexpected traffic passes, inspect **all policies selecting the pod**, especially broad rules with empty selectors.

## 4. Structure of a NetworkPolicy

Simple example:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-api-from-web
  namespace: shop-api
spec:
  podSelector:
    matchLabels:
      app: api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              security-zone: web
          podSelector:
            matchLabels:
              app: frontend
      ports:
        - protocol: TCP
          port: 8080
~~~

Meaning:

| Field | Role |
|---|---|
| **`metadata.namespace`** | Namespace holding the policy; selects target pods in this same namespace |
| **`spec.podSelector`** | Selects pods governed by this policy |
| **`policyTypes`** | Directions (`Ingress`/`Egress`) isolated on selected pods |
| **`ingress.from`** | Sources permitted to call the selected pods |
| **`egress.to`** | Destinations permitted to receive traffic from selected pods |
| **`ports`** | Permitted ports/protocols for that rule direction |
| **`namespaceSelector`** | Selects namespaces by label |
| **`ipBlock`** | Selects CIDRs and exceptions per Kubernetes NetworkPolicy semantics |

A policy in **`shop-api`** cannot directly select a pod in **`shop-web`** as its target via `spec.podSelector`. To restrict frontend egress, create a policy inside **`shop-web`**.

### The importance of labels

Policies select by label, not ephemeral pod names like **`api-6f7b...`**. A Deployment can recreate pods with new names while preserving **`app: api`**, so the policy continues matching.

Conversely, if an app deploys with different labels such as **`app.kubernetes.io/name: orders-api`** while the policy selects **`app: api`**, the rule fails to match the intended pods. Always verify live labels before applying.

## 5. Default-deny all ingress

A NetworkPolicy establishing ingress isolation for every pod in a namespace:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: shop-api
spec:
  podSelector: {}
  policyTypes:
    - Ingress
~~~

**`podSelector: {}`** selects all pods in the policy's namespace. Because **`policyTypes`** lists `Ingress` with no ingress rules, zero inbound flows are allowed by this policy itself.

**Key point:** if another policy selects those same pods and allows a source, that source remains allowed via additive union. Naming a policy "default-deny" gives it zero special precedence.

### Default-deny all egress

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-egress
  namespace: shop-api
spec:
  podSelector: {}
  policyTypes:
    - Egress
~~~

Once applied, pods in **`shop-api`** cannot send traffic anywhere **under standard NetworkPolicy rules**, unless an additional egress policy allows it. DNS, databases, telemetry, Key Vault, or identity endpoints can stop working unless scoped allow rules are added.

### Default-deny both directions

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny
  namespace: shop-data
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
~~~

This is the classic baseline for building **ground-up least privilege**. However, dropping default-deny ingress+egress onto a namespace with running workloads before mapping dependencies can cause severe outages.

## 6. Selectors: distinguishing AND vs. OR

Kubernetes NetworkPolicy has a syntax subtlety that easily widens permissions by mistake.

### `namespaceSelector` and `podSelector` in a single list item

~~~yaml
from:
  - namespaceSelector:
      matchLabels:
        security-zone: web
    podSelector:
      matchLabels:
        app: frontend
~~~

This means **AND**: only pods labeled **`app=frontend`** inside **namespaces** labeled **`security-zone=web`**.

### Two separate list items

~~~yaml
from:
  - namespaceSelector:
      matchLabels:
        security-zone: web
  - podSelector:
      matchLabels:
        app: frontend
~~~

This means **OR**: allow **every pod in namespaces labeled `security-zone=web`**, **or** allow pods labeled **`app=frontend` inside the policy's own namespace**. That is far broader than "frontend inside the web namespace."

**Exact YAML indentation is a security control, not merely formatting.**

### Empty selectors

- **`podSelector: {}`** at `spec` selects all pods in the current namespace.
- A peer containing only **`podSelector: {}`** selects all pods in the NetworkPolicy's namespace.
- A peer with **`namespaceSelector: {}`** selects pods across all namespaces.
- An omitted **`from`/`to`** rule allows broad traffic in that rule's direction.

Never use empty selectors as a "quick test" in production; add only explicit, verified rules.

### Namespace labels can change

When access depends on namespace labels, anyone permitted to edit namespace labels can make another group of pods match a selector meant for someone else. Therefore, **permission to edit namespace labels** is part of your security boundary, not just an organizational convenience.

## 7. Ingress and egress through Services

Applications usually call a **`ClusterIP` Service** rather than raw pod IPs, for example:

~~~text
api.shop-api.svc.cluster.local:8080
db.shop-data.svc.cluster.local:5432
~~~

Standard NetworkPolicy selects **pods**, namespaces, IP blocks, and ports—it does not match by Kubernetes Service name. When requests pass through a Service, the dataplane forwards to backend pods; policies must match the **actual source, destination, and backend port enforced by the dataplane**.

Example:

- Frontend calls Service **`api`** on port 8080.
- Service selects backend pods labeled **`app=api`**.
- The API pods' ingress policy permits the frontend source on the matching backend port.

If a Service maps **`port=80`** to **`targetPort=8080`**, pay close attention to which port the policy evaluates on backend pod connections. Never assume every DNAT/NAT implementation preserves ports/addresses identically at every hook; test on your live AKS dataplane.

### Named ports

NetworkPolicy can specify a named port (such as **`http-api`**) when target pods declare matching `containerPort` names. This decouples policy YAML from numeric ports, though Deployment, Service, and policy must stay aligned.

### Headless Services and direct access

Policies must protect pods even when callers use a **headless Service** or direct pod IPs. Never assume lacking a public Service prevents internal workloads from reaching a pod.

## 8. Three-tier model: web → API → database

Design a sample application:

| Namespace | Namespace label | Pod | Port |
|---|---|---|---|
| **shop-web** | `security-zone=web` | frontend | TCP 8080 when receiving ingress |
| **shop-api** | `security-zone=api` | api | TCP 8080 |
| **shop-data** | `security-zone=data` | db | TCP 5432 |
| **kube-system** | Kubernetes system labels | CoreDNS | UDP/TCP 53 |

Target connectivity:

~~~text
Ingress controller
       |
       | (when permitted)
       v
frontend (shop-web)
       |
       | TCP/8080
       v
api (shop-api)
       |
       | TCP/5432
       v
db (shop-data)

Disallowed:
  frontend ----X----> db:5432
  unrelated pod ----X----> api:8080
  api ----X----> arbitrary Internet
~~~

This is a **logical model**, not proof that all system flows (DNS, telemetry, identity, private endpoints, etc.) are already open. Every dependency must go into the connectivity matrix before production rollout.

## 9. Controlled lab: preparing namespaces and labels

The manifests below target a **test cluster with an active network policy engine**. Creating namespaces/pods and applying NetworkPolicies modifies cluster state. Never apply them to production or system namespaces without approvals, rollback plans, and dependency inventories.

Create **`namespaces.yaml`**:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: shop-web
  labels:
    security-zone: web
---
apiVersion: v1
kind: Namespace
metadata:
  name: shop-api
  labels:
    security-zone: api
---
apiVersion: v1
kind: Namespace
metadata:
  name: shop-data
  labels:
    security-zone: data
~~~

Apply on the lab cluster:

~~~bash
kubectl apply -f namespaces.yaml
kubectl get namespaces --show-labels
~~~

In production, manage namespace labels via GitOps/IaC, Azure RBAC / Kubernetes RBAC, and approval policies. Never let arbitrary developers edit network-security labels on other namespaces.

## 10. Lab: creating simulated workloads for testing

You don't need a real PostgreSQL instance just to test NetworkPolicy. We run a simple HTTP server on **port 5432** in the `db` pod to verify TCP reachability through policies. **Simulating the port does not turn an HTTP server into PostgreSQL.**

File **`workloads.yaml`**:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: frontend
  namespace: shop-web
  labels:
    app: frontend
spec:
  containers:
    - name: client
      image: busybox:1.36
      command: ["/bin/sh", "-c", "sleep 360000"]
---
apiVersion: v1
kind: Pod
metadata:
  name: api
  namespace: shop-api
  labels:
    app: api
spec:
  containers:
    - name: server
      image: python:3.12-alpine
      command: ["python", "-m", "http.server", "8080", "--bind", "0.0.0.0"]
      ports:
        - containerPort: 8080
---
apiVersion: v1
kind: Pod
metadata:
  name: db
  namespace: shop-data
  labels:
    app: db
spec:
  containers:
    - name: simulator
      image: python:3.12-alpine
      command: ["python", "-m", "http.server", "5432", "--bind", "0.0.0.0"]
      ports:
        - containerPort: 5432
---
apiVersion: v1
kind: Service
metadata:
  name: api
  namespace: shop-api
spec:
  selector:
    app: api
  ports:
    - name: http-api
      port: 8080
      targetPort: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: db
  namespace: shop-data
spec:
  selector:
    app: db
  ports:
    - name: tcp-demo-db
      port: 5432
      targetPort: 5432
~~~

Apply and verify:

~~~bash
kubectl apply -f workloads.yaml
kubectl get pods -A -o wide
kubectl get services -n shop-api
kubectl get services -n shop-data
~~~

Wait for pods to run and images to pull from an environment-permitted registry. Public images are illustrative only; production must use version-managed, vulnerability-scanned images with proper pull policies.

### Connectivity baseline before applying NetworkPolicy

On a cluster supporting NetworkPolicy with no isolation rules yet in the lab namespaces, direct access between pods is permitted:

~~~bash
kubectl exec -n shop-web frontend -- \
  wget -T 3 -O - http://api.shop-api.svc.cluster.local:8080/

kubectl exec -n shop-web frontend -- \
  wget -T 3 -O - http://db.shop-data.svc.cluster.local:5432/
~~~

In this environment, the first request should reach the API; the second request is **run purely as a baseline** to demonstrate the risk of frontend reaching the database without policies. Existing cluster controls may already restrict traffic, so record observed results rather than assuming both succeed.

## 11. Lab: applying default-deny ingress and egress

Create **`default-deny.yaml`**:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny
  namespace: shop-web
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny
  namespace: shop-api
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny
  namespace: shop-data
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
~~~

Apply on the **test** cluster:

~~~bash
kubectl apply -f default-deny.yaml
kubectl get networkpolicy -A
~~~

Afterwards, `frontend` cannot resolve Service names because DNS egress is also blocked. **Do not jump to concluding that the API policy blocked traffic properly** when the test failed due to DNS. The next step opens DNS in a controlled way.

## 12. Lab: opening DNS egress

Pods need DNS queries to resolve Service names. On many AKS clusters using CoreDNS, DNS pods live in **`kube-system`** and often carry labels like **`k8s-app=kube-dns`**. **Verify live labels** before applying the example:

~~~bash
kubectl get pods -n kube-system --show-labels
kubectl get namespaces --show-labels
kubectl get services -n kube-system
~~~

If DNS uses NodeLocal DNSCache, custom DNS resolvers, or special dataplane paths, selecting CoreDNS pods alone may not suffice. Check target addresses and AKS/CNI documentation for your setup.

Example **`allow-dns.yaml`** opening UDP/TCP 53 for `web` and `api` to CoreDNS pods:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns
  namespace: shop-web
spec:
  podSelector: {}
  policyTypes: [Egress]
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
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns
  namespace: shop-api
spec:
  podSelector: {}
  policyTypes: [Egress]
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

Why open both UDP and TCP 53? DNS queries typically use UDP, yet fallback cases require TCP. Tailor DNS rules to your actual deployment—never open **`to: [{}]`** to the entire Internet just because CoreDNS pod labels weren't checked.

## 13. Lab: allowing only frontend to call API

### Egress from frontend to API

File **`allow-web-to-api.yaml`**:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-web-egress-api
  namespace: shop-web
spec:
  podSelector:
    matchLabels:
      app: frontend
  policyTypes: [Egress]
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              security-zone: api
          podSelector:
            matchLabels:
              app: api
      ports:
        - protocol: TCP
          port: 8080
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-api-ingress-web
  namespace: shop-api
spec:
  podSelector:
    matchLabels:
      app: api
  policyTypes: [Ingress]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              security-zone: web
          podSelector:
            matchLabels:
              app: frontend
      ports:
        - protocol: TCP
          port: 8080
~~~

These two policies complement each other: frontend permits **egress** and API permits **ingress**. The earlier `default-deny` policy remains active, while these new rules add the valid path.

### Verification

~~~bash
kubectl apply -f allow-dns.yaml
kubectl apply -f allow-web-to-api.yaml

kubectl exec -n shop-web frontend -- \
  wget -T 3 -O - http://api.shop-api.svc.cluster.local:8080/
~~~

If access still fails, check DNS, Pod/Namespace labels, real ports, pod state, and the policy engine. Never delete `default-deny` immediately upon hitting an error; doing so destroys evidence of which rule was missing.

## 14. Lab: allowing only API to call the database

API is permitted to call the database simulator on TCP 5432. Open **API egress** and **database ingress**:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-api-egress-db
  namespace: shop-api
spec:
  podSelector:
    matchLabels:
      app: api
  policyTypes: [Egress]
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              security-zone: data
          podSelector:
            matchLabels:
              app: db
      ports:
        - protocol: TCP
          port: 5432
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-db-ingress-api
  namespace: shop-data
spec:
  podSelector:
    matchLabels:
      app: db
  policyTypes: [Ingress]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              security-zone: api
          podSelector:
            matchLabels:
              app: api
      ports:
        - protocol: TCP
          port: 5432
~~~

Save as **`allow-api-to-db.yaml`**, then run:

~~~bash
kubectl apply -f allow-api-to-db.yaml

kubectl exec -n shop-api api -- \
  python -c "import urllib.request; print(urllib.request.urlopen('http://db.shop-data.svc.cluster.local:5432/', timeout=3).status)"
~~~

Because this is a simulated HTTP server on port 5432, the HTTP response simply proves TCP connectivity is open; it does not test PostgreSQL auth or real database TLS.

### Denied path test

Frontend **must not** reach the database:

~~~bash
kubectl exec -n shop-web frontend -- \
  wget -T 3 -O - http://db.shop-data.svc.cluster.local:5432/
~~~

With DNS already open, the request should **fail at data connection** because frontend has no egress to `db` and `db` allows no ingress from frontend. A failure caused by broken DNS or a crashed app is not sufficient proof that the policy is working.

## 15. Network flow acceptance table

After applying all policies described above:

| Source | Destination | Protocol | Expected |
|---|---|---|---|
| `frontend` / `shop-web` | `api` / `shop-api` | TCP 8080 | Allowed |
| `api` / `shop-api` | `db` / `shop-data` | TCP 5432 | Allowed |
| `frontend` / `shop-web` | `db` / `shop-data` | TCP 5432 | Denied |
| Other pod lacking required source label | `api` / `shop-api` | TCP 8080 | Denied |
| `frontend`, `api` | Selected CoreDNS | UDP/TCP 53 | Allowed |
| `api` | Arbitrary Internet | TCP 443 | Denied by applied egress policy unless explicitly permitted |
| `db` | `api` | TCP 8080 | New connections denied by sample policy |

**Return traffic** for an already-permitted session is normally handled by the dataplane's stateful connection tracking. That does not mean the database pod can initiate a **new** connection back to the API.

### Separating policy blocks from application errors

For allowed tests, verify the exact status code or payload from the target backend. For denied tests, verify DNS succeeded, target pods are healthy, and the failure is not an **application-returned HTTP 403/404**.

An L3/L4 NetworkPolicy block usually manifests as a timeout or connection failure depending on the dataplane, not an HTTP status code. Observing a test succeed at baseline and fail after applying policies gives much stronger evidence than a single failed run.

## 16. Ingress controllers and inbound traffic to frontend

In our lab, `frontend` is just a client pod with no HTTP server receiving ingress. In real apps, `frontend` receives traffic via Service/Ingress or Azure Application Gateway for Containers.

When applying default-deny ingress in **`shop-web`**, explicitly allow traffic from the **ingress controller or traffic-forwarding component** to `frontend`. For example, if an ingress controller runs as pods in a namespace labeled **`security-zone=ingress`** with pod label **`app=ingress-controller`**:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend-from-ingress
  namespace: shop-web
spec:
  podSelector:
    matchLabels:
      app: frontend
  policyTypes: [Ingress]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              security-zone: ingress
          podSelector:
            matchLabels:
              app: ingress-controller
      ports:
        - protocol: TCP
          port: 8080
~~~

This is a **conditional example**—never apply it verbatim before verifying your live ingress topology. When traffic enters via nodes, load balancers, external gateways, or undergoes SNAT/DNAT, the source IP seen by the dataplane may differ. Inspect your actual ingress controller and AKS networking path.

**A Kubernetes Ingress resource does not automatically apply a NetworkPolicy to backend pods.** Ingress/Service routes traffic; NetworkPolicy enforces connectivity rules between endpoints via the dataplane.

## 17. DNS, Azure services, and Internet egress

Default-deny egress can silently break less-obvious dependencies:

- CoreDNS or custom DNS resolvers.
- Azure Key Vault, Azure Storage, Service Bus, Container Registry, or identity endpoints.
- Azure Monitor, OpenTelemetry collectors, and log/metrics agents.
- Service mesh control planes, certificate authorities, or mTLS services.
- App update checks, telemetry, or external webhooks.
- External Internet endpoints genuinely required by the application.

Build an **egress inventory table** before enabling deny:

| Source | Destination | Port | Why needed | How to restrict |
|---|---|---|---|---|
| frontend | API pods | TCP 8080 | API calls | `namespaceSelector` + `podSelector` |
| API | DB pods | TCP 5432 | Business read/write | `namespaceSelector` + `podSelector` |
| frontend/API | CoreDNS | UDP/TCP 53 | Name resolution | Verified DNS labels |
| API | Azure Storage private endpoint | TCP 443 | Data read/write | IP/egress per dataplane & routing |
| API | Key Vault endpoint | TCP 443 | Read secrets via identity | Advanced FQDN/egress or outbound firewall |
| Workload | Telemetry collector pods | Agent TCP port | Ship logs/traces | Namespace/pod selectors |

### Standard NetworkPolicy does not filter by FQDN

The **`to.ipBlock`** field in standard NetworkPolicy accepts CIDRs only—it cannot match **`storageaccount.blob.core.windows.net`** as an FQDN rule. Public IPs of Azure services can change, making manual static IP allowlists brittle.

If requirements dictate "allow connections only to a specific domain," evaluate **Azure Firewall / FQDN filtering, proxies, Cilium-specific policies, or supported advanced egress controls** instead of assuming standard Kubernetes NetworkPolicy inspects hostnames or TLS SNI.

### Private Endpoints

When pods call Azure services via Private Endpoints, DNS must resolve to the private IP with valid routing. NetworkPolicy egress may need to allow traffic to that destination IP/port per dataplane behavior, while NSGs, UDRs, and Azure Firewall along the path must also permit it.

**A Private Endpoint does not grant data access permissions**: workloads still require managed identity / Workload Identity and data-plane roles.

## 18. `ipBlock`, CIDRs, and key limitations

NetworkPolicy supports CIDR selection:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-outbound-to-approved-range
  namespace: shop-api
spec:
  podSelector:
    matchLabels:
      app: api
  policyTypes: [Egress]
  egress:
    - to:
        - ipBlock:
            cidr: 10.90.20.0/24
            except:
              - 10.90.20.128/25
      ports:
        - protocol: TCP
          port: 443
~~~

This example allows API TCP 443 traffic to part of **`10.90.20.0/24`**, excluding the upper half **`10.90.20.128/25`**. Addresses are illustrative only and do not correspond to any real learner Azure environment.

### Key limitations

- **`ipBlock` fits stable external IP endpoints outside the pod set**; use pod/namespace selectors for pod-to-pod traffic.
- When packets pass through Services, NAT, or proxies, addresses observed by the policy depend on CNI/dataplane behavior. Never assume CIDR matches solely from a Service name.
- Standard Kubernetes NetworkPolicy does not govern all traffic from nodes, `hostNetwork` pods, or host networking components the same way it governs regular pods.
- Never open **`0.0.0.0/0`** just to fix DNS or permit blanket Internet egress if least privilege is your goal.
- IP block rules do not replace Azure Firewall/NSG policies or data-access rules on target services.

## 19. How do AKS NetworkPolicy, NSG, and Azure Firewall differ?

| Mechanism | Scope / problem addressed | Typical control unit |
|---|---|---|
| **Kubernetes NetworkPolicy** | Pod/namespace communication at L3/L4 | Pod selectors, namespace selectors, IP/CIDR, ports |
| **Azure Network Security Group (NSG)** | Azure network traffic at subnet/NIC scope where applicable | IPs, protocols, ports, Azure service tags |
| **Azure Firewall / NVA** | North-south/egress control or centralized routing | IP/network rules, select FQDN/app rules, and logging |
| **Ingress controller / Application Gateway** | Receiving and routing HTTP(S) to workloads | Hosts, paths, listeners, backends |
| **Service mesh authorization** | Layer 7 / mTLS policies between services | Workload identities, HTTP methods/paths per mesh |
| **Kubernetes RBAC / Entra ID** | Who can manipulate Kubernetes/Azure APIs | Identities, resources, verbs, scopes |

Never treat an NSG as a substitute for NetworkPolicy to distinguish **`app=frontend`** from **`app=db`**. With AKS Overlay or other CNIs, pod IPs, routing, and NAT mean NSGs lack pod-label awareness. Understand which layer enforces which rules.

### L3/L4 does not replace L7

NetworkPolicy can let frontend reach the API on TCP 8080, yet cannot tell **`GET /orders`** apart from **`DELETE /admin/users`**. Applications must still verify tokens, roles, object permissions, and API rate limits; mTLS/service meshes can add connection authentication where supported.

## 20. Inspecting AKS networking before applying policies

### Read AKS networking info

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"

az aks show \
  --resource-group "<AKS_RESOURCE_GROUP>" \
  --name "<AKS_CLUSTER_NAME>" \
  --query "{name:name,kubernetesVersion:kubernetesVersion,networkPlugin:networkProfile.networkPlugin,pluginMode:networkProfile.networkPluginMode,networkPolicy:networkProfile.networkPolicy,networkDataplane:networkProfile.networkDataplane}" \
  --output json
~~~

This confirms the plugin, mode, policy engine, and dataplane reported by the API. Fields may be absent or differ by version/feature; never assume "no security" merely because a field is null. Cross-check live cluster settings against current AKS documentation.

### Read Kubernetes policies and labels

~~~bash
kubectl get networkpolicies --all-namespaces
kubectl describe networkpolicy -n shop-api allow-api-ingress-web
kubectl get pods -n shop-api --show-labels
kubectl get namespaces --show-labels
kubectl get services -n shop-api
kubectl get endpointslices -n shop-api
~~~

These commands are primarily read-only; required access depends on RBAC. **`kubectl get networkpolicy`** proves the Kubernetes API stored the policy, **not that the dataplane is enforcing it**. Proof of enforcement comes from live connectivity tests and engine telemetry.

### Inspect policy selectors

~~~bash
kubectl get networkpolicy -n shop-api -o yaml
kubectl describe pods -n shop-api
~~~

Cross-check:

1. Policy sits in the exact target namespace.
2. Pod selector matches pod labels.
3. Namespace selector matches current labels of source/destination namespaces.
4. **`Ingress`/`Egress`** direction is right.
5. Backend ports are accurate.
6. No other policy unintentionally widens access.

## 21. Production rollout process for policies

Never drop default-deny across an entire cluster in one shot. A risk-reducing sequence:

1. **Discover:** map namespaces, pod labels, Services, ingress controllers, DNS, Azure dependencies, and the active policy engine.
2. **Start small:** pilot on a test namespace or non-critical workload.
3. **Measure baseline:** record successful/failed connections, real IPs/ports, and app logs.
4. **Author allow rules:** enumerate every legitimate path before turning on deny.
5. **Review manifests:** audit selectors, AND/OR indentation, ports, and host/network exceptions.
6. **Roll out gradually:** enable default-deny during an approved change window; watch immediately.
7. **Positive tests:** verify frontend→API, API→DB, DNS, ingress, telemetry, and identity succeed.
8. **Negative tests:** verify frontend→DB or unauthorized pods→API are blocked.
9. **Monitor:** track connection failures, DNS, timeouts, app health, and policy edits.
10. **Automate:** manage policies via GitOps/IaC with peer review and regression tests.

### Rollback

Keep previous manifest versions and a tested rollback procedure—such as updating allow rules or reverting a newly added test policy. Never treat **deleting every NetworkPolicy** as a safe production rollback, as that throws open the entire internal network.

In a dedicated lab, delete created resources only once you are certain those namespaces contain nothing else:

~~~bash
# Run on lab clusters only; all three namespaces must belong exclusively to this exercise.
kubectl delete namespace shop-web shop-api shop-data
~~~

`delete` destroys resources; **never** run it if those namespaces host workloads you need to keep. When testing policies on shared clusters, coordinate with cluster owners and follow change management.

## 22. Common failures and diagnostics

| Symptom | Possible cause | What to check |
|---|---|---|
| NetworkPolicy created yet traffic still passes | No enforcement engine active; selector mismatch; another policy permits it | Inspect AKS networking, pod labels, all policies, and re-test |
| DNS breaks after default-deny | UDP/TCP 53 egress closed or wrong CoreDNS selector | Check CoreDNS labels, NodeLocal DNS, kube-system services, test DNS |
| Frontend cannot call API | Only one side opened; missing web egress or API ingress | Check both policies and backend ports |
| API cannot call database | Wrong namespace/pod labels, port, or egress rule | Check Service endpoints, selectors, DB ingress, and API egress |
| Ingress controller returns 502/504 | Backend pods reject traffic from controller's real source | Check datapath, real source identity/IP, ingress policy, app health |
| Pod cannot reach Azure Storage / Key Vault | Egress denied, Private DNS, UDR/firewall, identity | Check DNS/IP/port first, then verify RBAC |
| Policy allows too much | `namespaceSelector` and `podSelector` placed in separate list items | Audit AND/OR structure and YAML indentation |
| One policy blocks yet connections succeed | Another policy selects the pod and allows traffic | Inspect union of all allow rules on the pod |
| ClusterIP Service looks broken | Empty Service endpoints, wrong port/targetPort, or policy block | Check Endpoints/EndpointSlice, test pod IP vs. Service |
| Inconsistent behavior across nodes/pods | Failing dataplane/policy agent, uneven rollout/config | Inspect node status, agent pods, logs, and supported versions |
| Newly deployed pod loses connectivity | Changed labels/template or missing namespace label | Compare manifests, live pod labels, and rollout |
| HTTPS fails yet TCP connects | TLS, DNS SNI, auth, or app bug—not L3/L4 policy | Check HTTP/TLS errors, certificates, and app logs |

### Layered diagnosis

1. **Application layer:** are pods Ready, and is the process listening on the expected port?
2. **Service discovery:** does DNS return the right Service/IP, and does the Service have backend endpoints?
3. **NetworkPolicy:** which policies select source and destination, and do both directions have allow rules?
4. **Dataplane / CNI:** does AKS have an enforcement engine active, and are network agents healthy?
5. **Azure networking:** are NSGs, UDRs, Azure Firewall, or Private Endpoints affecting traffic?
6. **Identity / TLS:** when TCP connects yet returns 401/403/5xx, inspect RBAC, tokens, TLS, and app code.

Never fix an application 403 error by opening egress to the whole Internet. Conversely, when DNS times out, never add Azure RBAC roles when the block comes from NetworkPolicy.

## 23. Special cases and limits of standard NetworkPolicy

### `hostNetwork` pods and node traffic

Standard NetworkPolicy targets the pod network primarily. Traffic involving **`hostNetwork`**, node-local services, kubelet, host endpoints, and certain system flows depends heavily on CNI/dataplane behavior. Never assume a namespace default-deny protects all node or host communications.

### Protocols and out-of-scope features

Standard NetworkPolicy covers TCP, UDP, and SCTP at network level. It does not express Layer 7 rules like URL paths, HTTP methods, gRPC methods, database users, or FQDNs. Engines like Cilium provide extended policies, which are **custom CRDs/extensions**, not part of the standard Kubernetes NetworkPolicy API.

### Internet egress, SNAT, and CIDR policies

Outbound traffic may traverse NAT Gateway, load balancer outbound rules, Azure Firewall, or custom routing. Pod-level NetworkPolicy and egress Azure Firewall rules must be evaluated together. The IP seen by external services may be a post-NAT address differing from the source pod IP.

### Cluster upgrades

Upgrading AKS or CNI versions can alter dataplane components or edge-case behavior, so re-test policies in staging after upgrades. Never rely on undocumented NAT/service-routing quirks outside standard Kubernetes guarantees.

## 24. Policy security and governance

### RBAC

Anyone permitted to **create/update/delete NetworkPolicies** can widen or alter pod-to-pod communications. Restrict permissions by namespace and separate app developers from cluster network administrators where appropriate.

Permissions to edit **namespace labels**, pod labels in Deployments, and admission policies also impact selector security. A tightly crafted policy becomes meaningless if any workload can freely add an allowed label to itself.

### Policy-as-code

- Store NetworkPolicies in Git alongside applications or in a governed policy repository.
- Enforce peer reviews on changes to selectors, CIDRs, and ports.
- Run CI YAML schema checks and test policies in a lab cluster.
- Enforce baselines with admission control / Azure Policy where supported.
- Monitor drift between Git and live cluster state.
- Avoid granting blanket policy bypasses for "emergencies" without formal process.

### Defense in depth

NetworkPolicy is one layer in the architecture:

~~~text
Microsoft Entra ID + Kubernetes RBAC
             |
             v
Admission / policy-as-code
             |
             v
NetworkPolicy (pod L3/L4)
             |
             v
Azure NSG / Firewall / Private networking
             |
             v
TLS / workload identity / app authorization
             |
             v
Audit logs / incident response
~~~

A pod allowed to reach a DB on TCP 5432 still requires **authorized database credentials**, TLS, and application-layer data controls.

## 25. Cost and operational impact

Standard NetworkPolicy resources do not carry a per-YAML billing meter, yet implementing network segmentation increases **operational complexity** and can influence resource spend:

- The dataplane / policy engine must be supported and operated reliably.
- Flow logging, visibility, and tracing can raise monitoring costs.
- Egress through Azure Firewall, NAT Gateway, or proxies incurs separate charges.
- Testing and CI/GitOps require staging environments.
- Workloads may need tuning for DNS, readiness, startup, and timeouts.

Never cut costs by disabling NetworkPolicy without compensating controls. Measure failed connection metrics, latency, and auxiliary networking charges, then right-size policies and observability scope.

## 26. Scenario exercise: isolating an ordering application

An enterprise runs on AKS:

- **`store-web`**: frontend receiving HTTP via an ingress controller.
- **`store-api`**: orders API; only frontend may call it on TCP 8080.
- **`store-payments`**: payment processor; only API may call it on TCP 8443.
- **`store-db`**: database; only API and payments may call it on TCP 5432 under separate allow rules.
- **`kube-system`/CoreDNS**: serves DNS.
- API calls a Storage Account over Private Endpoint on TCP 443.

### Tasks

1. Distinguish the roles of namespaces, Services, NSGs, and NetworkPolicy.
2. Assign clear namespace and pod labels to select sources and destinations.
3. Propose per-namespace default-deny ingress/egress and a phased rollout plan.
4. Design ingress allow rules for API, payments, and DB.
5. Design matching egress allow rules from frontend, API, and payments.
6. Open DNS cleanly, accounting for NodeLocal DNS if present.
7. Explain what permissions API needs to reach the Storage Private Endpoint and read data.
8. Explain why the path from the ingress controller to `web` must also be verified.
9. Show the risk of splitting `namespaceSelector` and `podSelector` into two OR items.
10. Design a test suite with one valid and one blocked connection per tier.
11. Describe how to roll back safely if a policy blocks production traffic.
12. Define logs, alerts, namespace-label governance, and policy review workflows.

### Guided solution

Apply security-meaningful namespace labels, place default-deny in each namespace, and open **ingress controller → web → API → payments/DB** per real requirements. Whenever both source and destination are isolated, every link needs egress on the source and ingress on the destination. Open DNS explicitly; Storage over Private Endpoint requires IP/routing, Private DNS, and data permissions. Never open the database directly from frontend.

If the app calls `payments` on TCP 8443, NetworkPolicy allowing that port **does not guarantee** secure payment traffic: you still need mTLS/TLS, authentication, authorization, and secret protection.

## 27. Production checklist

| Item | What to verify |
|---|---|
| AKS networking | Network plugin/dataplane/policy engine supports NetworkPolicy |
| Namespaces | Authorization labels and who can edit them are strictly controlled |
| Pod labels | Selectors match live Deployments/Pods |
| Baseline | Connection inventory documented before enabling deny |
| Default-deny | Properly scoped; never applied blindly to system namespaces |
| Ingress | API/DB accept traffic only from expected sources and ports |
| Egress | Workloads call only required backends and infrastructure |
| DNS | UDP/TCP 53 and actual CoreDNS/NodeLocal paths verified |
| Ingress controller | Traffic to frontend permitted across live datapath |
| Azure dependencies | Private Endpoints, DNS, identities, and outbound paths verified |
| Positive tests | Valid flows connect cleanly |
| Negative tests | Unlisted flows blocked by policy, not because the app is down |
| GitOps | Peer-reviewed YAML, desired state, and rollback ready |
| RBAC | Restricted edits on NetworkPolicies and namespace labels |
| Monitoring | Logs, metrics, alerts, and investigation runbooks active |
| Upgrades | Policies re-tested after AKS/CNI upgrades |

## 28. Self-check questions

1. Why doesn't creating two separate namespaces isolate pod networking automatically?
2. When does Kubernetes NetworkPolicy begin isolating ingress or egress on a pod?
3. Does standard NetworkPolicy have deny rules and priorities?
4. How do two policies selecting the same pod combine?
5. Why might a frontend → API connection require both frontend egress and API ingress rules?
6. What does **`podSelector: {}`** in `spec` mean?
7. Why does putting `namespaceSelector` and `podSelector` in one `from` item differ from two separate items?
8. Can a policy in namespace **`shop-api`** directly isolate egress of a pod in **`shop-web`**?
9. After applying default-deny egress, why might Service names stop resolving?
10. Why is opening UDP 53 alone sometimes insufficient for DNS?
11. Why doesn't NetworkPolicy simply select backends by Kubernetes Service name?
12. Why can't standard Kubernetes NetworkPolicy filter URL paths and HTTP methods?
13. When using `ipBlock`, how can NAT and Services complicate CIDR rules?
14. What are the distinct roles of AKS NetworkPolicy vs. Azure NSGs/Firewalls?
15. Why doesn't `kubectl get networkpolicy` prove the dataplane is dropping packets?
16. Why must `hostNetwork` or node traffic be evaluated separately?
17. When an app breaks after default-deny, what should you inspect before widening egress?
18. How do you prove a flow was blocked by policy rather than DNS or backend failure?
19. Why can someone with permission to edit namespace labels compromise network policies?
20. Which steps would you follow to roll out NetworkPolicy in production AKS with minimal downtime risk?

## References

- Kubernetes — *Network Policies*: https://kubernetes.io/docs/concepts/services-networking/network-policies/
- Kubernetes — *Declare Network Policy*: https://kubernetes.io/docs/tasks/administer-cluster/declare-network-policy/
- Microsoft Learn — *Secure traffic between pods using network policies in AKS*: https://learn.microsoft.com/azure/aks/use-network-policies
- Microsoft Learn — *Azure CNI Powered by Cilium*: https://learn.microsoft.com/azure/aks/azure-cni-powered-by-cilium
- Microsoft Learn — *AKS networking concepts*: https://learn.microsoft.com/azure/aks/concepts-network
- Microsoft Learn — *Azure CNI overview*: https://learn.microsoft.com/azure/aks/azure-cni-overview
- Microsoft Learn — *Control egress traffic for AKS clusters*: https://learn.microsoft.com/azure/aks/limit-egress-traffic
- Microsoft Learn — *Azure Network Security Groups*: https://learn.microsoft.com/azure/virtual-network/network-security-groups-overview
