# Cloud Service Mesh in Multi-Environment Architectures

An enterprise operates microservices across two Google Kubernetes Engine (GKE) clusters, some legacy services on Compute Engine VMs, and an on-premises data center. The team wants services to call each other securely, route around regional outages, observe cross-environment latency, and gradually roll out new versions without rewriting every application. VPC connectivity, Cloud VPN, or Cloud Interconnect only establish network paths: they do not automatically provide workload identity, service-to-service access policies, or application-layer traffic control.

**Cloud Service Mesh** is Google Cloud's service mesh solution, built on technologies like Istio and Envoy or Google Cloud service routing APIs depending on the platform. A service mesh places a traffic-control and policy layer between workloads: service discovery, load balancing, mTLS, identity verification, authorization, traffic splitting, and telemetry. It unifies operations across many services, yet **does not replace underlying network connectivity** and **does not guarantee every cluster, VM, or cloud can join the same managed mesh**.

In the **CLOUD_PROVIDERS_GCP** module, hybrid and multicloud architectures must coordinate projects, IAM, VPCs, GKE, Compute Engine, cloud networking, access control, and observability. This lesson places Cloud Service Mesh into that picture, compares control-plane options per environment, describes east-west connectivity paths, and provides Istio configuration examples alongside a controlled rollout workflow.

After this lesson, you will be able to:

- Distinguish a service mesh, API gateway, load balancer, VPC peering, and VPN/Interconnect.
- Explain control plane, data plane, Envoy sidecars, proxyless gRPC, service identity, and trust domains.
- Choose managed Cloud Service Mesh for GKE or Compute Engine, and recognize limitations for Kubernetes outside Google Cloud.
- Design multi-cluster setups with fleets, certificate authorities, DNS, pod connectivity, and east-west gateways.
- Apply STRICT mTLS, `AuthorizationPolicy`, and canary routing with Istio APIs on supported platforms.
- Plan migrations from a single-cluster mesh to multiple clusters or multiple environments.
- Set SLIs/SLOs for service-to-service communication while managing proxy overhead and operational costs.
- Troubleshoot discovery, routing, certificate, policy, and telemetry failures.

## 1. When Does a System Need a Service Mesh?

Suppose a `checkout` service calls `payment`, `inventory`, and `notification`. When adding a cluster in another region or on-premises, new questions arise:

1. Which hostname does `checkout` use to reach `payment`?
2. Which endpoints are healthy and should receive requests?
3. Can `checkout` call `payment` while blocking other services?
4. How do we encrypt service-to-service traffic without every team manually managing TLS certificates?
5. How do we send 5% of traffic to a new `payment` version and roll back quickly?
6. How do we tell whether failures originate at the client, proxy, gateway, or backend across the WAN?

A service mesh addresses these challenges at the workload-to-workload communication layer. However, if you have only two simple services, low traffic, and no need for uniform policies, the operational overhead of a mesh can outweigh its benefits. Evaluate actual needs before installing one.

### What does a mesh NOT replace?

| Component | Primary problem solved | Relationship with service mesh |
|---|---|---|
| VPC, subnets, routes, firewalls | IP connectivity and network controls | Mesh requires valid network paths first |
| Cloud VPN/Cloud Interconnect | Connects on-premises and Google Cloud | Carries traffic between networks; does not create workload identity |
| Cloud Load Balancing/GKE Gateway | North-south entry points, TLS/public/private ingress | Can sit in front of the mesh or mesh gateways |
| API gateway | API policies, consumer auth, quotas, developer experience | Complements east-west policies, not strictly equivalent |
| Service mesh | Policies and orchestration for inter-workload traffic | Provides ingress/egress gateways, mTLS, routing, telemetry |
| IAM | Access rights to Google Cloud resources/control plane | Does not replace per-request `AuthorizationPolicy` inside the mesh |
| Kubernetes NetworkPolicy | Pod network-layer traffic control | Adds defense in depth alongside service identity policies |

Therefore, solid designs combine them: Global/Regional Load Balancers for external ingress, Cloud Service Mesh for internal communication, IAM for Google APIs, and VPC firewalls/NetworkPolicy to lock down unnecessary network paths.

## 2. Components of Cloud Service Mesh

### Control plane

The control plane stores and distributes routing configuration, endpoint discovery, and security policies to the data plane. When configured with Istio APIs, Kubernetes custom resources such as `VirtualService`, `DestinationRule`, `PeerAuthentication`, and `AuthorizationPolicy` describe desired behavior. Envoy proxies receive executable configuration via xDS.

The control plane does not necessarily sit in the path of every user request. In the sidecar model, most traffic flows directly between Envoy proxies; the control plane pushes updated endpoint lists and policies as the system changes.

### Data plane

The data plane enforces routing, mTLS, policies, load balancing, retries, and telemetry collection. On GKE using Istio APIs, this is typically an **Envoy sidecar** running alongside the application in each Pod. Sidecars consume CPU/RAM and can add latency; include them in capacity planning.

In deployments based on **Google Cloud Service Routing APIs** for VMs and eligible workloads, the data plane can be an Envoy proxy or **proxyless gRPC** supporting xDS. Proxyless gRPC replaces part of the sidecar's role inside supported applications and does not have 1:1 feature parity with all Istio APIs.

### Service identity and CA

Workloads use identities bound to service accounts and trust domains. A Certificate Authority issues and rotates certificates, enabling workloads to mutually authenticate using mTLS. On GKE, you can use **Mesh CA** or **Certificate Authority Service (CA Service)** in supported combinations.

If two clusters use incompatible CAs or trust domains, valid network routes alone will not make mTLS succeed. Trust chains, certificate validity windows, source identities, and authorization policies must align.

~~~mermaid
flowchart TB
    CP[Cloud Service Mesh control plane]
    CA[Mesh CA or CA Service]
    subgraph G1[GKE Cluster A]
      PA[Envoy sidecar A]
      SA[Service checkout]
    end
    subgraph G2[GKE Cluster B]
      PB[Envoy sidecar B]
      SB[Service payment]
    end
    CP -. xDS discovery / policy .-> PA
    CP -. xDS discovery / policy .-> PB
    CA -. certificates / trust .-> PA
    CA -. certificates / trust .-> PB
    SA --> PA
    PA <-->|mTLS / service routing| PB
    PB --> SB
~~~

This diagram illustrates a logical model for a compatible multi-cluster mesh; it does not imply all workloads across distinct physical networks automatically have direct reachability. If Pod IPs are not routable across networks, a gateway or suitable connectivity solution is required.

## 3. Selecting a Deployment Model by Environment

The product name **Cloud Service Mesh** encompasses several deployment models. Two systems labeled "Cloud Service Mesh" do not necessarily share the same control plane, APIs, or management mechanics.

| Environment | Primary option | How it is controlled | What to verify |
|---|---|---|---|
| GKE on Google Cloud | Managed Cloud Service Mesh, recommended for new deployments | Istio APIs with managed `TRAFFIC_DIRECTOR` control plane | Fleet, GKE version, region, Mesh CA/CA Service, supported features |
| Compute Engine VMs or mixed VM + GKE/proxyless gRPC | Managed Cloud Service Mesh via Service Routing APIs | Google Cloud networking/service routing APIs, Envoy or proxyless gRPC | Do not copy Istio `VirtualService`/`AuthorizationPolicy` verbatim into a different API |
| Google Distributed Cloud software-only on-premises | In-cluster Cloud Service Mesh | Customer-operated Istio APIs and control plane | Version/platform support, connectivity, gateways, CA, upgrade ownership |
| Kubernetes in another cloud, e.g., EKS/AKS | Only under currently supported off-Google Cloud options | In-cluster Istio APIs; check attached-cluster limits | Deprecations, support lifecycle, cross-platform discovery, networking |
| Legacy GKE with in-cluster `ISTIOD` or managed `ISTIOD` | Legacy/deprecated | Requires a modernization plan to managed `TRAFFIC_DIRECTOR` | API compatibility, rollout ordering, downtime, and end-of-support dates |

**Key point:** a managed control plane for GKE on Google Cloud does not equate to a managed control plane for a Kubernetes cluster on AWS, Azure, or on-premises. For clusters outside Google Cloud, current documentation describes an **in-cluster control plane** with conditional platform support. Older hybrid/multicloud guides may reference legacy versions or control-plane models and should not be copied verbatim for new fleets.

### Product lifecycle note

Per release notes published in September 2026, both in-cluster `ISTIOD` and managed `ISTIOD` on GKE in Google Cloud are deprecated, with end of support scheduled for **March 1, 2028**. The in-cluster control plane on Google Distributed Cloud software-only continues to be documented as supported. Support for certain attached EKS/AKS clusters and GKE on AWS/Azure follows separate deprecation schedules; attached clusters carry a noted **March 17, 2027** milestone. Before designing an expansion, always check the Supported Platforms, Deprecations, and Release Notes pages for your exact platform and version.

A durable hybrid design may consist of **two separately managed meshes** connected through protocols/gateways and API contracts, rather than forcing every workload into an unsupported single control plane.

## 4. Single-Cluster, Multi-Cluster, and Multi-Network

### Single-cluster

One cluster, one endpoint discovery domain, and Envoy sidecars. This is the easiest model to deploy and observe. Use it as a pilot to validate mTLS, authorization, TLS identities, and proxy overhead.

### Multi-cluster, same network

Two or more GKE clusters in one mesh—potentially across regions or projects—sharing endpoint discovery and routing to services in another cluster. Typical prerequisites:

- Clusters belong to the **same fleet host project**.
- If across projects, GKE clusters use Shared VPC on the **same network** per managed multi-cluster guidance.
- Valid Pod-to-Pod connectivity and firewalls exist for cross-cluster traffic.
- Compatible CA/trust model: shared Mesh CA or compatible CA Service hierarchy.
- Consistent namespaces and service identities by design.
- Service FQDNs/DNS resolve properly; may require DNS proxy/endpoint discovery configuration.

If two clusters sit in different VPCs, **sharing a fleet does not automatically create cross-VPC routes**. You must explicitly determine multi-network/gateway support for your exact version rather than assuming "cross-cluster just works."

### Multi-network and hybrid

When Pod IPs cannot reach each other directly across networks, one or more **east-west gateways** act as mTLS termination/forwarding points bridging mesh networks. WAN or cross-cloud paths require proper links, routes, firewalls, and gateway reachability. You may use Cloud VPN/Interconnect, private connectivity, or approved exposed gateways matching organizational policy.

~~~mermaid
flowchart LR
    U[Client applications]
    L[Global/Regional LB or API Gateway]
    subgraph GCP[Google Cloud]
      A[GKE Cluster A / checkout service]
      GA[East-west gateway A]
    end
    subgraph EDGE[On-premises or other cloud]
      GB[East-west gateway B]
      B[Payment / inventory service]
    end
    U --> L --> A
    A --> GA
    GA <-->|VPN/Interconnect or approved link| GB
    GB --> B
~~~

This diagram shows **integration capability**; it is not a claim that a managed GKE mesh and every on-prem/EKS mesh can share the same control plane. Always verify topology types and feature matrices—hybrid setups in particular carry specific guides, Kubernetes API server/gateway reachability requirements, and cases where private clusters are unsupported.

## 5. Elements to Standardize Across Clusters

### Fleet and membership

A fleet is the logical boundary managing GKE clusters. In managed Cloud Service Mesh with Istio APIs, the fleet API enables the mesh feature and provisions the managed control plane for memberships. Clusters joining the same mesh must be registered to the right fleet, and multi-cluster services should standardize namespace and Kubernetes Service names.

### Namespace sameness and service naming

If the `payment` service shares the same name across two clusters, namespaces, service accounts, labels, and ports must remain consistent. Unexpected discrepancies in namespaces or ports can prevent the control plane from merging endpoints properly or cause policies to apply incompletely.

Examples use Kubernetes FQDNs such as `payment.shop.svc.cluster.local`, though DNS proxy/endpoint discovery settings must be verified in multi-cluster setups. Namespace sameness does not require every application instance to run the exact same code version.

### Network identity

Clusters or networks require consistent network identifiers in multi-network deployments. Gateways and endpoint discovery rely on network metadata to determine whether an endpoint sits on the same network or a remote network.

### Trust domain

A trust domain is a certificate identity boundary, not a subnet CIDR. In a GKE fleet using Mesh CA, service identities typically correspond to the fleet workload identity pool, formatted as **FLEET_PROJECT_ID.svc.id.goog**. When writing `AuthorizationPolicy` rules by principals, specify the actual trust domain rather than hardcoding `cluster.local` from another environment.

### CA and certificates

Clusters must be able to verify each other's certificate chains. With CA Service, this may require subordinate CA pools under a shared root CA or trust configurations per documentation. Monitor certificate rotation, clock skew, SAN identities, and handshake errors—especially at east-west gateways.

## 6. Preparing and Enabling Managed Cloud Service Mesh for GKE

The example below illustrates only the core steps for **GKE managed Cloud Service Mesh using Istio APIs**; it does not apply to off-cloud in-cluster installations. Clusters must meet Google Cloud's published requirements for GKE version, region, IAM permissions, fleet registration, and networking.

### Step 1: Check the fleet

~~~bash
export FLEET_PROJECT_ID="platform-fleet-prod"
export MEMBERSHIP_NAME="gke-checkout-asia"
export MEMBERSHIP_LOCATION="asia-southeast1"

gcloud container fleet memberships list \
  --project="$FLEET_PROJECT_ID"
~~~

If the cluster is not yet a membership, register it following current provisioning docs. Do not proceed if the fleet membership points to the wrong project or cluster.

### Step 2: Enable the mesh feature

~~~bash
gcloud container fleet mesh enable \
  --project="$FLEET_PROJECT_ID"
~~~

### Step 3: Configure automatic management for the membership

~~~bash
gcloud container fleet mesh update \
  --management=automatic \
  --memberships="$MEMBERSHIP_NAME" \
  --location="$MEMBERSHIP_LOCATION" \
  --project="$FLEET_PROJECT_ID"
~~~

If the membership is in `global` or was registered with a different CLI version, look up its actual location via `fleet memberships list`. For Shared VPC setups, grant appropriate roles to mesh service agents on the network host project per documentation. With CA Service, CA setup steps differ and must be completed before enabling.

### Step 4: Verify the control plane

~~~bash
gcloud container fleet mesh describe \
  --project="$FLEET_PROJECT_ID"
~~~

Inspect membership state, control plane state, and deployed version/channel. Do not assume command success means every Pod's data plane is ready. Configure namespace injection and roll out workloads only after checking your environment's revision-label guidance.

### Step 5: Inspect workloads and sidecars

~~~bash
kubectl get pods -n shop -o wide
kubectl get peerauthentications,authorizationpolicies -n shop
kubectl get virtualservices,destinationrules -n shop
~~~

Select the right `kubectl` context for each cluster before running commands. Namespace `shop` is illustrative and must already exist. With a managed data plane, injection/revision mechanics and in-cluster components are system-managed; do not manually alter labels or webhooks based on outdated guides incompatible with your running version.

## 7. Securing Traffic With mTLS and AuthorizationPolicy

### What is mTLS?

Mutual TLS authenticates both client and server during connection setup. With mesh sidecars, Envoy manages certificates and TLS on behalf of applications. However, an encrypted connection **does not mean the client is authorized to call every API**. Pair mTLS with `AuthorizationPolicy` to control which service can call which service.

### PeerAuthentication STRICT

Example restricting all proxy-enabled workloads in namespace `shop` to accept mTLS only:

~~~yaml
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: require-mtls
  namespace: shop
spec:
  mtls:
    mode: STRICT
~~~

Apply:

~~~bash
kubectl apply -f peer-authentication.yaml
kubectl -n shop get peerauthentication
~~~

This is a namespace-level policy. Apply it only after verifying all relevant clients and servers have compatible proxies/transports; enabling `STRICT` too early can break legacy workloads not yet onboarded to the mesh. In managed `TRAFFIC_DIRECTOR`, `PeerAuthentication` `DISABLE` is not supported; if temporary compatibility is needed, follow the corresponding transport security/destination policy guidance.

### AuthorizationPolicy by service account identity

Suppose only the `checkout` service account in namespace `shop` may call the `payment` service labeled `app=payment`. Actual principal identities must match the **fleet trust domain**:

~~~yaml
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: payment-only-checkout
  namespace: shop
spec:
  selector:
    matchLabels:
      app: payment
  action: ALLOW
  rules:
  - from:
    - source:
        principals:
        - "FLEET_PROJECT_ID.svc.id.goog/ns/shop/sa/checkout-sa"
    to:
    - operation:
        methods: ["POST"]
        paths: ["/payments"]
~~~

Replace `FLEET_PROJECT_ID` with your actual value and trust domain before applying. Once at least one `ALLOW` policy applies to a workload, requests not matching any rule are denied under Istio authorization semantics. For non-HTTP traffic, path/method filtering does not apply the same way and must be designed around ports and identities.

**Safe rollout order:** enable telemetry and observe → verify `PERMISSIVE` mTLS during transition → test client identities → enable `STRICT` → run positive/negative permission tests → apply authorization per service. Always verify that an unauthorized workload is blocked rather than merely checking that valid requests succeed.

### Mesh CA does not replace IAM

`AuthorizationPolicy` governs service-to-service requests inside the mesh. When `payment` calls BigQuery or Secret Manager, Google Cloud API IAM is still required. When employees access a UI, end-user authentication is still required. Maintain defense in depth across layers.

## 8. Controlling Traffic With VirtualService and DestinationRule

A major benefit is canary-deploying new versions without shifting all traffic immediately.

### DestinationRule defining subsets

Suppose Kubernetes Service `payment` backs two Pod groups labeled `version=v1` and `version=v2`:

~~~yaml
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: payment-destination
  namespace: shop
spec:
  host: payment.shop.svc.cluster.local
  subsets:
  - name: v1
    labels:
      version: v1
  - name: v2
    labels:
      version: v2
~~~

### VirtualService splitting 90/10

~~~yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: payment-routing
  namespace: shop
spec:
  hosts:
  - payment.shop.svc.cluster.local
  http:
  - route:
    - destination:
        host: payment.shop.svc.cluster.local
        subset: v1
      weight: 90
    - destination:
        host: payment.shop.svc.cluster.local
        subset: v2
      weight: 10
~~~

These examples route traffic to two service versions; **they do not create the v1 and v2 Deployments/Services**. They work only when Pod labels, ports, and the Service already exist. In multi-cluster setups, rules apply according to configuration scope and endpoint discovery; never assume a simple `VirtualService` forces traffic to a specific region without appropriate topology/routing policies.

### Canary with SLO gates

A sound progression plan:

1. Deploy v2 without public traffic; test health and mTLS.
2. Shift 1–5% of traffic to v2 if policies allow.
3. Compare p95 latency, error rates, and business success between v1 and v2.
4. Increase to 10%, 25%, 50%, and 100% with observation windows.
5. If SLOs degrade, set v2 weight back to 0 and verify the config reached the data plane.

For every traffic policy change, watch **config propagation delay**. Managed `TRAFFIC_DIRECTOR` may take time to validate and push policies to proxies; do not treat `kubectl apply` success as instant traffic switching across every Pod.

## 9. Timeouts, Retries, and Circuit Breaking Across Environments

Traffic crossing regions or WAN links experiences higher latency and jitter than intra-node traffic. Misconfigured retries can amplify load on a struggling system, while overly short timeouts can trigger false failures.

### Example timeout and bounded retries

~~~yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: inventory-policy
  namespace: shop
spec:
  hosts:
  - inventory.shop.svc.cluster.local
  http:
  - timeout: 3s
    retries:
      attempts: 2
      perTryTimeout: 1s
      retryOn: "connect-failure,refused-stream,unavailable"
    route:
    - destination:
        host: inventory.shop.svc.cluster.local
~~~

This policy is illustrative; exact support for retry fields must be checked against the managed Cloud Service Mesh feature matrix. Apply retries only to idempotent operations or APIs with deduplication safeguards. If a Java/Spring application also retries, avoid multiplying retry attempts across layers.

### Circuit breaking and outlier detection

`DestinationRule` can configure connection pool limits and outlier detection with varying levels of support. Verify your version and how the xDS implementation handles them; do not copy every upstream Istio attribute blindly into a managed service. Overly aggressive settings can turn a brief error spike into ejecting all healthy endpoints.

Across WAN links, do not use a mesh to paper over chatty synchronous designs with too many round trips. Business flows that do not require immediate synchronous responses can move to Pub/Sub events or queues, reducing cross-region dependencies in the request path.

## 10. East-West Gateways in Hybrid/Multi-Network Setups

**North-south** traffic flows from external clients into the system. **East-west** traffic flows between workloads, clusters, VPCs, or networks. Multi-network service meshes typically rely on east-west gateways to proxy traffic across network boundaries when Pod IPs are not directly routable.

### What must a gateway satisfy?

- Reachable from the peer network over allowed IPs/ports.
- Valid certificates/identities and matching trust chains.
- Exposes only services/ports permitted by policy.
- Health checking, capacity headroom, failover, and observability.
- Never exposes the Kubernetes API server or gateways to the public internet beyond explicit requirements.
- Proper return paths, NAT/MTU handling, and accurate DNS/SNI configuration.

### Common pitfalls

1. **VPC peering is not transitive:** if traffic must cross an intermediate network, design explicit routes/gateways; sharing a mesh does not route packets across non-transitive VPCs.
2. **Gateways do not replace ACLs:** mTLS authenticates the gateway/workload, while authorization decides whether the request is permitted.
3. **Mismatched SNI, host, and trust domain:** hostnames may resolve properly yet TLS handshakes fail due to mismatched server identities.
4. **Public gateways are not secure by default:** enforce firewalls/allowlists, rate limiting, authentication, logging, and private connectivity where possible.
5. **Same fleet does not mean same network:** verify reachability before enabling multi-cluster endpoint discovery.

### Hybrid limitations to read before deploying

Google publishes specific guides for "Set up a hybrid mesh" and "Set up a multi-cluster mesh outside Google Cloud" with strict prerequisites. Some topologies require all clusters to share a fleet host project, reachable control plane and gateway addresses, and **private clusters may be unsupported in corresponding hybrid guides**. Never apply a managed GKE multi-cluster guide to EKS, AKS, or GDC on-premises without checking Supported Platforms/Features and deprecations.

## 11. Cross-Environment Monitoring and Failure Analysis

Cloud Service Mesh provides service graphs and telemetry for eligible services using Cloud Monitoring, Cloud Logging, and optionally Cloud Trace depending on configuration. Envoy sidecars observe HTTP traffic by source and destination; telemetry distinguishes latency, success/error rates, and service dependencies.

### SLIs/SLOs to track

| Metric | Interpretation | Why it matters |
|---|---|---|
| Request success rate | Percentage of requests completing without error per business definition | Detects failures in mesh paths and backends |
| p50/p95/p99 latency | Latency broken down by source, destination, and route | Reveals WAN/gateway overhead and tail latency |
| Error code distribution | 4xx, 5xx, gRPC status codes, connection failures | Separates auth failures from service failures |
| mTLS handshake failures | Certificate/trust validation errors | Catches CA, clock skew, or trust-domain mismatches |
| Authorization denied | Requests blocked by policy | Confirms least privilege and spots anomalies |
| Endpoint health | Ready endpoints per cluster | Detects routing/failover misconfigurations |
| Cross-region bytes | Egress and cross-boundary bandwidth | Tracks cost and bottlenecks |
| Proxy resource utilization | CPU/memory/connection counts | Capacity planning for sidecars/gateways |
| Configuration age | Delay from policy edit to proxy adoption | Detects stale policies |

Example SLOs—such as 99.9% availability over 28 days or p95 latency under 250 ms—are **illustrative only**; tune them to each protocol, service type, and serving region. Mesh HTTP telemetry alone cannot measure business outcomes like completed orders; add application instrumentation and distributed tracing.

### Inspection tools

~~~bash
gcloud container fleet mesh describe \
  --project="$FLEET_PROJECT_ID"

kubectl -n shop get pods -o wide
kubectl -n shop get svc,endpoints
kubectl -n shop get peerauthentication,authorizationpolicy
kubectl -n shop get virtualservice,destinationrule
~~~

With Istio APIs, `istioctl` can assist in inspecting proxy configs and policies where supported by your version. Example:

~~~bash
istioctl proxy-status
istioctl analyze -n shop
~~~

With distroless managed data planes, do not expect `bash` or `curl` inside sidecars. When packet or network inspection is needed, use ephemeral debug containers or approved logging/tracing tools per organizational policy.

### Layered triage when a request fails

1. Does DNS resolve the right hostname?
2. Do the Service and endpoints exist in the right cluster/namespace?
3. Are networks, routes, firewalls, and gateway ports open?
4. Do workloads have sidecars/proxies running with the latest config?
5. Are mTLS certificates, trust domains, and SNI valid?
6. Is an `AuthorizationPolicy` blocking the request?
7. Do `VirtualService`/`DestinationRule` target the right subset and port?
8. Is the backend application returning errors or timing out?
9. Are retries/circuit breakers amplifying errors?
10. Do telemetry and traces pinpoint the failing hop?

## 12. Designing a Sample System Across Three Environments

### Scenario

An enterprise operates:

- **GKE A (asia-southeast1):** production `checkout` and `payment`, high traffic.
- **GKE B (asia-east1):** standby/redundant deployment to mitigate regional outages.
- **On-premises:** `inventory` service talking to a legacy ERP, connected over Cloud Interconnect.

Goal: `checkout` calls `payment` securely across both GKE clusters; `inventory` remains on-premises yet reachable via a restricted endpoint; the system tracks latency and prepares for gradually migrating `inventory` to GKE.

### Phase 1: Mesh on GKE

1. Standardize GKE versions, supported regions, Fleet host project, and Shared VPC.
2. Enable managed Cloud Service Mesh for each compatible membership.
3. Verify proxy injection, endpoint discovery, CA/trust domains, and telemetry.
4. Enable `STRICT` mTLS and `AuthorizationPolicy` in namespace `shop` via staged rollout.
5. Test canary v1/v2 routing inside a single cluster before expanding multi-cluster.

### Phase 2: GKE multi-cluster

1. Ensure Pod-to-Pod reachability if selecting a same-network topology.
2. Verify cross-cluster firewalls/routes and namespace sameness.
3. Use a shared fleet and CA trust per the managed multi-cluster guide.
4. Verify discovery, DNS, and traffic reaching endpoints in both clusters.
5. Test endpoint loss, single-cluster failure, and traffic fallback behavior.

### Phase 3: Integrating on-premises inventory

Two options to weigh:

**A. Keep inventory outside the mesh:** expose `inventory` via a private endpoint or dedicated mTLS gateway over Cloud Interconnect/VPN, with GKE gateways/proxies calling that endpoint per contract. Manage certificates and ACLs cleanly at the boundary. This reduces dependency on a single cross-platform mesh.

**B. Build a supported hybrid mesh:** deploy off-Google Cloud in-cluster Cloud Service Mesh on a compatible on-premises platform, verify version/topology support, and connect east-west gateways, CA/trust domains, and service discovery per documentation. Confirm explicitly that the GKE managed control plane is not applied to off-cloud workloads where unsupported.

In both options, `inventory` may require longer timeouts than intra-cluster services; avoid deep synchronous call chains, bound retries, and consider event-based integration for flows not needing immediate consistency.

### Phase 4: Validation and cutover

Run contract tests, canaries, and controlled chaos tests. Verify:

- Valid traffic is encrypted with accurate workload identities.
- Unauthorized services cannot reach `payment`.
- `inventory` is reachable only over the approved path.
- Losing one gateway/cluster does not push the entire product outside SLOs.
- Telemetry captures sources, destinations, and traces sufficient for debugging.
- A rollback plan exists if new configs increase error rates.

## 13. Cost and Performance Impact

A service mesh reduces duplicated security and routing code, yet introduces costs:

| Component | Cost driver |
|---|---|
| Envoy sidecars | CPU/memory per Pod, raising cluster compute requests |
| East-west gateways | Pod/VM capacity, load balancers, public/private IPs |
| Cross-region/cross-cloud traffic | Network egress, VPN/Interconnect, WAN bandwidth |
| Telemetry | Cloud Monitoring metrics, log ingestion, traces, and retention |
| Certificates/CA | CA Service fees if chosen, policy and key operations |
| Control plane/licensing | Cloud Service Mesh/GKE Enterprise pricing per configuration |
| Operations | Engineering time for policy reviews, upgrades, incident response |

Never estimate mesh cost solely by cluster count. A cluster with thousands of Pods incurs significant sidecar overhead, while a chatty cross-region design can generate egress costs dwarfing control-plane fees.

### Measuring before and after enabling the mesh

1. Baseline request latency, error rates, and Pod CPU/memory before rollout.
2. Enable the mesh on a representative service group.
3. Compare sidecar overhead, p95/p99 latency, network egress, and throughput.
4. Scale traffic and Pod count to test control-plane propagation and endpoint churn.
5. Tune proxy resource requests/limits and telemetry sampling to fit SLOs.
6. Document realized value: consistent policies, faster delivery, lower incident MTTR.

## 14. Safe Production Change Workflow

A mesh has a wide blast radius: a misconfigured `AuthorizationPolicy` can block dozens of services, and a bad `VirtualService` can route traffic to unready Pods.

Recommended workflow:

1. Store Istio manifests, gateway configs, and fleet configs in Git.
2. Validate schemas against your actual control plane's supported feature matrix.
3. Assess impact per namespace/service and require owner reviews.
4. Test in an isolated cluster or equivalent staging environment.
5. Apply policies narrowly before mesh-wide rollout.
6. Monitor config propagation and request error rates.
7. Expand rollout by cohort/namespace.
8. Keep rollback configs, dashboards, and on-call contacts ready.
9. Re-verify policies after GKE/channel/mesh version upgrades.
10. Periodically audit principal rules, certificate trust, and exposed gateways.

### Security rollout principle

Never turn on mesh-wide `STRICT` immediately while workloads without sidecars still exist. Start with lower-risk services, verify traffic from non-mesh workloads, and tighten gradually. When a service handles both HTTP and TCP, check port-specific policies independently; never treat an HTTP-method rule as filtering every protocol.

## 15. Common Errors and Troubleshooting

| Symptom | Possible cause | How to inspect |
|---|---|---|
| GKE mesh not ACTIVE after enabling | Fleet/permissions, GKE version, or API prerequisites unmet | Fleet membership, feature state, service agent roles, release channel |
| Service cannot find endpoints in another cluster | Endpoint discovery disabled, DNS/FQDN, or namespace mismatch | `asm-options`, DNS proxy, namespace sameness, service ports |
| Endpoints exist, yet cross-cluster calls time out | Pod networks not routable or firewalls blocking | VPC/Shared VPC, routes, firewalls, gateway reachability |
| mTLS handshake failure | Different CA/trust domain, invalid/expired cert, or SNI mismatch | Certificate chains, Mesh CA/CAS config, time sync |
| Client gets HTTP 403 after policy | Wrong principal or rule missing method/path | AuthZ policy, trust domain, source SA, access logs |
| Legacy workloads lose connectivity under STRICT | Client outside mesh or sending plaintext | Audit clients, transition via `PERMISSIVE` per supported policy |
| Canary traffic ignores 90/10 split | Wrong subset labels, stale proxy config, low sample size | `VirtualService`, `DestinationRule`, Pod labels, rollout delay |
| Errors spike when enabling retries | Stacked retry layers, non-idempotent requests | Istio + app retry policies, request IDs, and timeout budgets |
| Cross-cloud gateway reachable, service call fails | Broken endpoint discovery, TLS identity, or auth boundary | Gateway config, SNI, CA, service mappings, policies |
| Mesh UI missing metrics | Sidecar/telemetry/export broken or unsupported protocol | Proxy status, Cloud Monitoring, sampling, protocol |
| Proxy CPU/memory spikes | Undersized sidecar, traffic/telemetry surge | Resource sizing, connection pools, sampling |
| Control plane applies policies slowly | `TRAFFIC_DIRECTOR` config propagation characteristics | Monitor config age and endpoint health; avoid repeated blind applies |

## 16. Pre-Production Design Checklist

- [ ] Clearly identified workloads on GKE, Compute Engine VMs, on-premises, or external Kubernetes.
- [ ] Verified Managed vs. in-cluster options against Supported Platforms and deprecations.
- [ ] Not assuming off-Google Cloud clusters share GKE's managed control plane.
- [ ] Fleet host project/memberships standardized for managed multi-cluster.
- [ ] Network routes, Pod CIDRs, DNS, gateways, and firewalls mapped.
- [ ] Multi-network setups select east-west gateways or alternative boundary protocols.
- [ ] CA, trust domain, certificate rotation, and service accounts verified.
- [ ] Phased mTLS rollout and workload-identity authorization planned.
- [ ] Google API IAM not confused with in-mesh request authorization.
- [ ] Consistent namespaces, Kubernetes Service names, labels, and ports defined.
- [ ] Timeout/retry/circuit-breaking policies avoid duplicating mutating writes.
- [ ] `VirtualService`/`DestinationRule` canary-tested with rollback paths.
- [ ] Request success, latency, auth denies, and certificate errors measured.
- [ ] Health checks, capacity headroom, and failover configured for east-west gateways.
- [ ] Hybrid/private-cluster/attached-cluster constraints checked for exact versions.
- [ ] Sidecar, egress, telemetry, and licensing costs evaluated.
- [ ] GitOps/IaC, reviews, audits, and cross-environment incident runbooks established.

## 17. Design Exercise

Design a system spanning GKE A in Singapore, GKE B in Taiwan, and `inventory` on-premises:

1. Decide whether GKE A/B belong to one fleet and Shared VPC or separate networks.
2. Select managed Cloud Service Mesh for GKE, verifying region and GKE version support.
3. Map communication paths for `checkout` → `payment` and `checkout` → `inventory`.
4. List where CA trust, mTLS, `AuthorizationPolicy`, and IAM are needed.
5. Choose between keeping `inventory` outside the mesh via a private gateway or using a supported hybrid mesh.
6. Define the source identity permitted to call `payment`; all other identities must be denied.
7. Build a `payment` v2 canary plan with SLIs and rollback triggers.
8. Document application behavior if the link to on-premises drops for 5 minutes.
9. Estimate preliminary costs for extra proxies, gateways, and egress.
10. Create a minimal verification matrix covering networking, DNS, policies, certificates, traffic, and telemetry.

**Self-assessment question:** If two GKE clusters belong to the same fleet yet lack Pod-to-Pod reachability, is sharing a fleet enough for Cloud Service Mesh to work cross-cluster? **No.** Endpoint discovery, routes/firewalls, and sometimes east-west gateways must still meet topology prerequisites. If `inventory` runs in another cloud, verify the control-plane model and support status before claiming a single unified mesh.

## 18. Conclusion

Cloud Service Mesh provides a uniform communication layer for microservices through discovery, routing, mTLS, authorization, and telemetry. In multi-environment architectures, its primary value lies in **enforcing consistent policies across supported workloads** and eliminating repetitive TLS/routing boilerplate in each service.

However, the underlying platform dictates what is actually possible: GKE on Google Cloud should favor managed Cloud Service Mesh with its current control plane; Compute Engine VMs use Service Routing APIs; and on-premises or external Kubernetes clusters follow in-cluster Istio API models with specific limits. A hybrid architecture does not automatically become a single managed mesh simply by connecting a VPN or registering to a fleet.

Progress systematically from **platform support → network reachability → identity/trust → endpoint discovery → mTLS/authorization → traffic policies → observability → rollout**. When each layer is validated independently and integrated step by step, a service mesh enhances security and reliability without becoming an unmanageable single point of failure.

## References

- [Cloud Service Mesh overview](https://docs.cloud.google.com/service-mesh/docs/overview)
- [Cloud Service Mesh supported platforms](https://docs.cloud.google.com/service-mesh/docs/supported-platforms)
- [Supported features: managed control plane and Istio APIs](https://docs.cloud.google.com/service-mesh/docs/supported-features-managed)
- [Supported features: in-cluster control plane](https://docs.cloud.google.com/service-mesh/docs/supported-features-in-cluster)
- [Managed control plane overview and modernization](https://docs.cloud.google.com/service-mesh/docs/managed-control-plane-overview)
- [Provision a managed Cloud Service Mesh control plane on GKE](https://docs.cloud.google.com/service-mesh/docs/onboarding/provision-control-plane)
- [Set up a multi-cluster mesh on managed Cloud Service Mesh](https://docs.cloud.google.com/service-mesh/docs/operate-and-maintain/multi-cluster)
- [Set up a hybrid mesh](https://docs.cloud.google.com/service-mesh/docs/operate-and-maintain/hybrid-mesh)
- [Set up multi-cluster Cloud Service Mesh outside Google Cloud](https://docs.cloud.google.com/service-mesh/docs/operate-and-maintain/off-gcp-multi-cluster-setup)
- [Configure mTLS transport security](https://docs.cloud.google.com/service-mesh/docs/security/configuring-mtls)
- [Cloud Service Mesh authorization policy](https://docs.cloud.google.com/service-mesh/docs/security/authorization-policy-overview)
- [Cloud Service Mesh observability overview](https://docs.cloud.google.com/service-mesh/docs/observability-overview)
- [Cloud Service Mesh release notes](https://docs.cloud.google.com/service-mesh/docs/release-notes)
- [Architecture: GKE Gateway and Cloud Service Mesh](https://docs.cloud.google.com/architecture/build-apps-using-gateway-and-cloud-service)
