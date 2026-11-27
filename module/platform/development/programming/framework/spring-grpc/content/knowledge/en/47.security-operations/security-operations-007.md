# Network Policies for gRPC Ports

gRPC runs over HTTP/2 on top of TCP. In Kubernetes, `NetworkPolicy` controls which pods are allowed to open connections to which pods and over which ports. For Spring gRPC, proper policy configuration ensures only required workloads reach the gRPC listener while keeping DNS, health checks, and auxiliary flows operating as required by the deployment.

`NetworkPolicy` is a Layer 3/4 network control. It can permit TCP traffic to a gRPC port, but it does not distinguish methods such as `GetOrder` or `CancelOrder`, authenticate users, or replace TLS. Method-level authorization still requires authentication/authorization in the application or a proxy/service mesh layer capable of Layer 7 enforcement.

## 1. Identifying the Exact Port Being Protected

A gRPC service typically opens a single TCP listener and multiplexes multiple RPCs over the same HTTP/2 connection. Therefore, a `NetworkPolicy` usually only needs to allow TCP to that listener port; do not allocate a separate port per RPC method.

Example workload:

| Component | Illustrative Value |
| --- | --- |
| Server namespace | `catalog` |
| Server pod label | `app: catalog-grpc` |
| Container listener | TCP `9090` |
| Kubernetes Service | `catalog-grpc` |
| Client namespace | `commerce` |
| Client pod label | `app: checkout` |
| Service DNS | `catalog-grpc.catalog.svc.cluster.local` |

Example Service:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog-grpc
  namespace: catalog
spec:
  selector:
    app: catalog-grpc
  ports:
    - name: grpc
      protocol: TCP
      port: 9090
      targetPort: 9090
~~~

`port` is the port clients call on the Service; `targetPort` is the listener port inside the pod. In `NetworkPolicy`, rules generally must match the destination port on the pod, i.e., `targetPort`/listener `9090`. If a Service exposes `port: 443` and forwards to `targetPort: 9090`, check which port your CNI enforces on pod endpoints and verify with real tests; never assume the Service port and container port are identical.

## 2. Understanding Kubernetes Isolation and Allow Semantics

`NetworkPolicy` has important semantics:

- Pods not selected by any ingress policy remain open to ingress by default.
- Once a policy with `policyTypes: [Ingress]` selects a pod, that pod becomes ingress-isolated; only traffic allowed by applicable ingress policies can enter.
- Egress works the same way: a pod becomes egress-isolated only when an egress policy selects it.
- Allow rules across multiple `NetworkPolicy` resources are additive; policies do not have deny-overrides priority ordering.
- For traffic between two pods, both the source's egress policy and the destination's ingress policy must permit the connection.
- Allowed connections are stateful; return packets for an allowed connection are permitted without opening a reverse inbound rule.

Because allow rules are additive, adding a narrow policy does not restrict an already-existing broad policy. Before applying default-deny, audit all existing policies in the namespace to understand the full effective rule set.

## 3. Default-Deny Ingress for the Server Namespace

First, isolate ingress to pods in the `catalog` namespace:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: catalog
spec:
  podSelector: {}
  policyTypes:
    - Ingress
  ingress: []
~~~

This policy selects all pods in the `catalog` namespace and opens zero ingress rules. Pods that need to receive traffic must have explicit allow policies. If the namespace hosts diverse workloads, select by label or separate namespaces for clearer scope boundaries.

## 4. Allowing Only Selected Clients to Call the gRPC Server

The following policy allows `app: checkout` pods in the `commerce` namespace to reach `app: catalog-grpc` pods on TCP port `9090`:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-checkout-to-catalog-grpc
  namespace: catalog
spec:
  podSelector:
    matchLabels:
      app: catalog-grpc
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: commerce
          podSelector:
            matchLabels:
              app: checkout
      ports:
        - protocol: TCP
          port: 9090
~~~

`namespaceSelector` and `podSelector` sit inside the same peer item, so they are combined with logical AND: the source must be an `app: checkout` pod in the `commerce` namespace. Separating them into two items in the `from` list changes the meaning to OR, potentially allowing far broader traffic than intended.

The `kubernetes.io/metadata.name` label is normally added automatically by Kubernetes to Namespaces. If your cluster or test environment lacks this label, use an organization-managed namespace label and verify the selector matches the intended namespace.

If traffic traverses an ingress controller, gateway, or service mesh gateway, the source observed by the server may be the gateway pod rather than the client pod. In that case, allow the exact gateway namespace/pod. Never open entire CIDRs or all namespaces just to get connectivity working.

## 5. Default-Deny Egress and Client Allow Rules

If the client namespace enforces default-deny egress, the client must be granted egress to both the gRPC server and the DNS resolver. Example default-deny for the checkout pod:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: checkout-default-deny-egress
  namespace: commerce
spec:
  podSelector:
    matchLabels:
      app: checkout
  policyTypes:
    - Egress
  egress: []
~~~

The following policy opens only the gRPC destination and DNS:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: checkout-egress
  namespace: commerce
spec:
  podSelector:
    matchLabels:
      app: checkout
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: catalog
          podSelector:
            matchLabels:
              app: catalog-grpc
      ports:
        - protocol: TCP
          port: 9090
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

The DNS rule lets the client resolve Service names before connecting. CoreDNS/kube-dns labels vary by cluster installation; inspect your actual DNS pod labels and adjust the selector. Some CNIs handle traffic to the DNS Service IP or node-local DNS specially, so verify policy behavior on your active CNI.

Default-deny egress will block checkout's other dependencies unless allowed: databases, identity providers, telemetry collectors, message brokers, or external APIs. Add each required flow by destination, protocol, and port; never open `0.0.0.0/0 TCP` just to avoid connection failures.

## 6. Ports, Protocols, and HTTP/2

Standard gRPC uses TCP. A `NetworkPolicy` for the listener must specify `protocol: TCP`; opening UDP on the same port will not make gRPC work. A single HTTP/2 connection carries many concurrent RPCs, so all methods on the same listener share the same port.

Key items to verify:

- The container listener actually binds to `0.0.0.0:9090` or the appropriate pod address; binding to `127.0.0.1` will reject traffic from other pods.
- `containerPort`, Service `targetPort`, and `NetworkPolicy` destination port must be consistent.
- If TLS terminates at the gRPC server, the policy still permits TCP to that TLS listener.
- If TLS terminates at a gateway, the policy between gateway and backend must allow the actual backend port.
- HTTP/2 keepalive does not require opening an extra port; it rides on the existing TCP connection.

`NetworkPolicy` does not inspect ALPN, HTTP/2 frames, `:path`, or gRPC methods. Standard Kubernetes policies cannot express rules like "only allow `/acme.orders.v1.OrderService/GetOrder`". Use interceptors, authorization policies, or an L7 proxy/service mesh when RPC-method-level control is required.

## 7. Combining NetworkPolicy with TLS and Authentication

`NetworkPolicy` restricts which network sources can reach a pod. It does not prove the caller is a legitimate workload and does not encrypt data. An allowed pod reaching port `9090` could still be compromised or send forged requests.

Defense in depth typically includes:

1. **NetworkPolicy:** restricts namespace, pod, direction, and TCP port.
2. **TLS/mTLS:** encrypts transport; mTLS authenticates workload identity via certificates.
3. **Authentication:** verifies principals/tokens when APIs require user or service account identity.
4. **Authorization:** checks whether the principal is permitted to call the service/method and access the resource.
5. **Audit/telemetry:** records identity, method, status, and access decisions without logging secrets.

Do not treat `NetworkPolicy` as the sole security boundary. Once a client pod is allowed to reach the gRPC port, the server must still authenticate and authorize according to contract.

## 8. Health Checks and Operational Flows

Kubernetes can run liveness/readiness probes against container ports; gRPC can also expose the Health Checking Protocol via `grpc.health.v1.Health`. Distinguish between:

- **Kubelet probes:** traffic originated by the node/kubelet. How a CNI applies `NetworkPolicy` to node-originated traffic depends on implementation and configuration.
- **Client/proxy health checks:** traffic from other pods, requiring matching allow selectors and ports.
- **gRPC health RPC:** uses the gRPC listener; no extra port is needed if the health service shares the listener.

Do not assume every CNI handles kubelet probes identically. After enabling default-deny ingress, verify readiness/liveness probes still reach pods on your actual CNI. If separate rules are needed for nodes or probe sources, use mechanisms supported by your CNI and scope tightly to the node/port; avoid opening cluster-wide ingress.

Beyond health checks, check other operational flows:

| Flow | Direction | Considerations |
| --- | --- | --- |
| Prometheus scrape | Ingress to metrics port | Allow only scraper namespace/pods |
| Trace/metric export | Egress from server | Allow specific collector and required port |
| DNS | Egress from client/server | UDP/TCP 53 to appropriate resolver |
| Identity provider | Egress | Allow only credential verification endpoint/port |
| Database/broker | Egress from worker/service | Dedicated rule per workload and port |
| Ingress gateway | Ingress to gRPC pod | Allow exact gateway pod/namespace |

If the metrics listener runs on a port other than `9090`, do not bundle it into the gRPC rule when the scraper is a different workload. Separating policies keeps access scopes clear.

## 9. IPBlock, Service IPs, and Portability Limits

`ipBlock` is useful for external CIDRs or fixed network ranges, but is usually a poor choice for identifying in-cluster pods. Pod IPs change during rollouts or rescheduling; use namespace/pod selectors for internal workloads.

When applying policies to traffic traversing NodePort, LoadBalancer, NAT, or ingress gateways, the source/destination addresses visible at the enforcement point may depend on the CNI, kube-proxy mode, and traffic path. Never assume `ipBlock` always sees the original client IP. For production flows, verify with CNI documentation and flow logs.

Standard `NetworkPolicy` does not support portable FQDN selectors. Some CNIs provide FQDN policy extensions, but those are CNI-specific features and must be managed as platform dependencies.

## 10. Safe Rollout Process

Apply policies step by step:

1. Identify listener ports, namespaces, pod labels, clients, gateways, DNS, and health/metrics traffic.
2. Inventory current ingress/egress flows from manifests, service maps, and telemetry.
3. Verify the CNI supports Kubernetes `NetworkPolicy` and the required semantics.
4. Create narrow allow policies for intended gRPC flows.
5. Verify selectors match the right pods; mistyped selectors leave workloads unmatched.
6. Apply default-deny in a small scope, then verify every required flow.
7. Monitor connection failures, readiness, DNS, and CNI flow logs during rollout.
8. Expand policies to subsequent namespaces/workloads after verification.

`NetworkPolicy` allow rules are additive. Before rollout, audit all policies selecting a pod to ensure no broader rules remain. Keep manifests in GitOps so selector and port changes are reviewed as security changes.

## 11. Testing gRPC Connectivity

Test both allowed and disallowed clients. First inspect policies and pod labels:

~~~bash
kubectl get networkpolicy -n catalog
kubectl describe networkpolicy allow-checkout-to-catalog-grpc -n catalog
kubectl get pods -n catalog --show-labels
kubectl get pods -n commerce --show-labels
~~~

From an allowed checkout pod, test the TCP port:

~~~bash
nc -vz catalog-grpc.catalog.svc.cluster.local 9090
~~~

Then invoke an RPC with `grpcurl` using TLS/certificates appropriate for the environment. The example below uses plaintext only for test clusters explicitly configured for plaintext:

~~~bash
grpcurl -plaintext catalog-grpc.catalog.svc.cluster.local:9090 list
~~~

The `list` command requires reflection enabled on the server. If production disables reflection, invoke a specific method using a proto descriptor or `-proto` rather than enabling reflection just to test.

Repeat the test from a pod in a disallowed namespace. The connection must be blocked at the network layer; simultaneously verify whether DNS resolves to distinguish DNS errors from policy blocks. On TCP timeout, inspect CNI flow logs or policy traces to identify which rule dropped the traffic.

A successful test from an allowed client does not prove least-privilege enforcement. You also need negative tests from disallowed workloads plus checks for auxiliary flows like DNS, health probes, metrics, and egress dependencies.

## 12. Recommended Test Matrix

| Source | Destination | Expected Outcome |
| --- | --- | --- |
| `commerce/app=checkout` | `catalog/app=catalog-grpc:9090/TCP` | Allow |
| Other pod in `commerce` | `catalog/app=catalog-grpc:9090/TCP` | Deny unless another allow policy applies |
| Disallowed namespace | `catalog/app=catalog-grpc:9090/TCP` | Deny |
| `commerce/app=checkout` | CoreDNS UDP/TCP 53 | Allow |
| `commerce/app=checkout` | Other port on catalog pod | Deny unless another rule applies |
| Prometheus scraper | Metrics port | Allow per dedicated metrics policy |
| Kubelet/node | Probe port | Verify per CNI and cluster config |
| Selected gateway | Backend gRPC port | Allow per gateway selector |

When a connection is rejected, check DNS, Service endpoints, listener port, `NetworkPolicy` selectors, and CNI enforcement in order. Never fix issues by opening all traffic; locate the missing network edge and add a narrow rule.

## 13. Takeaways and Self-Check

**Network policy for gRPC ports** is a Layer 3/4 configuration restricting which workloads can connect to the Spring gRPC TCP listener. Pair default-deny with namespace/pod selectors and destination ports; if client egress is isolated, also allow DNS and required dependencies. Policies do not distinguish RPC methods, encrypt traffic, or authenticate principals, so TLS/mTLS and authentication/authorization remain essential at their respective layers.

Self-check:

1. Why does gRPC typically need only one TCP port for multiple RPC methods?
2. When must both the server's ingress policy and the client's egress policy allow traffic?
3. Are two selectors within the same peer item combined with AND or OR?
4. Why can default-deny egress cause DNS lookups to fail?
5. Why does `NetworkPolicy` not replace TLS or authorization?
6. What should be checked if kubelet probes fail after enabling default-deny?
7. Why are negative tests from disallowed pods necessary?

A `NetworkPolicy` designed around actual traffic flows ensures Spring gRPC accepts traffic only from required workloads, shrinks the attack surface, and keeps vital operational flows running reliably.
