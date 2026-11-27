# Role of DNS, Routers, and Service Mesh in Discovery

## Objectives

After this lesson, you will be able to:

- Distinguish service name resolution, instance discovery, and request routing.
- Explain how DNS helps applications find service addresses and the limitations of DNS.
- Describe how routers, reverse proxies, and load balancers pick destinations for requests.
- Explain how a service mesh discovers endpoints and controls traffic between services.
- Choose how to combine DNS, registries, routers, and meshes suited to your deployment environment.

## 1. Three distinct questions in service discovery

When an application needs to call another service, there are three related yet distinct questions:

1. **What address does the service name resolve to?** For example, the name inventory.internal needs to map to an IP or an access endpoint.
2. **Which instance will the request go to?** A service may have multiple instances; the system must select a destination still capable of serving.
3. **How is the request forwarded and controlled?** The system may apply routing rules, load balancing, timeouts, retries, authentication, and traffic observability.

DNS usually answers the first question. Routers or load balancers usually participate in the second and third questions. A service mesh provides an infrastructure layer for endpoint discovery and controlling inter-service communication. Meanwhile, a registry such as Eureka or Consul stores instance information and provides APIs for other components to query.

Not every system uses all four components. One application may call a stable DNS name pointing to a load balancer; another platform may use a registry so clients pick instances themselves; Kubernetes can combine DNS, Service, EndpointSlice, and network proxies; a service mesh can pull endpoint data from the platform API and push configuration to proxies.

## 2. DNS: mapping service names to addresses

DNS (Domain Name System) is a name resolution system. Rather than hardcoding IPs in source code, applications call a hostname such as inventory.internal. A DNS resolver queries the corresponding record and returns an IP address or other target information.

Simple flow:

~~~~mermaid
sequenceDiagram
    participant App as Calling app
    participant Resolver as DNS Resolver
    participant DNS as DNS Server
    participant Target as Service address
    App->>Resolver: Resolve inventory.internal
    Resolver->>DNS: Query record
    DNS-->>Resolver: A/AAAA or CNAME
    Resolver-->>App: Resolved address
    App->>Target: Connect to address
~~~~

Common record types:

| Record | Role |
| --- | --- |
| A | Maps a hostname to an IPv4 address. |
| AAAA | Maps a hostname to an IPv6 address. |
| CNAME | Creates an alias pointing to another hostname. |
| SRV | Advertises a service's hostname and port under a service/protocol name. |

### DNS can point to one stable address or multiple addresses

A hostname can point to a load balancer's virtual IP. In that case, clients only need the service name; the load balancer is responsible for choosing backend instances. This pattern is popular because backend IPs can change without updating client configuration.

DNS can also return multiple A or AAAA records for the same hostname. Some resolvers or clients distribute results in round-robin fashion. However, returning multiple IPs does not automatically ensure every IP is healthy, reachable from the client, or evenly loaded. IP selection and retry mechanics depend on the resolver, HTTP library, and application configuration.

### DNS in Kubernetes

In Kubernetes, cluster DNS usually provides hostnames for Services. For example, a service named inventory in the commerce namespace can be reached via:

~~~~text
inventory.commerce.svc.cluster.local
~~~~

Shorter names such as inventory.commerce or inventory may work depending on the Pod's namespace and search domains. For a ClusterIP Service, DNS typically resolves the Service name to a stable ClusterIP. Traffic sent to the ClusterIP is then forwarded to an eligible backend Pod via cluster networking mechanisms.

For a headless Service (clusterIP: None), DNS can return the addresses of the Pod endpoints instead of a shared ClusterIP. This is useful when clients need to know individual endpoints, such as certain stateful systems. Clients must handle the address list and endpoint lifecycle appropriately.

### Limitations of DNS

- **TTL and caching:** resolvers, runtimes, or libraries may cache results. When endpoints change, clients may continue using old addresses until caches expire or refresh.
- **Health awareness:** DNS records do not necessarily reflect real-time application health. An address still present in DNS is not guaranteed to handle requests successfully.
- **Granularity:** DNS typically provides hostnames and addresses; it does not richly describe per-instance metadata, version, zone, weights, or circuit breaker state.
- **Endpoint selection:** returning multiple IPs does not imply a consistent load-balancing algorithm across clients.
- **Network scope:** resolved addresses must be reachable from the caller. An internal IP may not be usable from networks outside the cluster.

DNS is well suited for providing stable names that are easy to configure and compatible with almost any client. When you need to select instances by health, metadata, or complex traffic policies, you usually also need a registry, load balancer, or service mesh.

## 3. Routers and load balancers: selecting destinations and forwarding requests

In the context of service discovery, a router is a component that receives requests and decides which backend receives each request. Depending on the network layer, routers can operate at L4 (TCP/UDP) or L7 (HTTP/gRPC). Reverse proxies, ingress controllers, API gateways, and load balancers can all fulfill part of this role.

A router usually exposes a stable address or hostname to clients. It maintains or receives a configured backend list, health-checks endpoints, and applies a target selection algorithm. Backends may be statically declared, fetched from DNS, fetched from a registry like Eureka/Consul, or pushed by the platform's control plane.

~~~~mermaid
flowchart LR
    C[Client] -->|inventory.internal| D[DNS]
    D -->|VIP address| LB[Router / Load Balancer]
    LB -->|Select backend| I1[Inventory instance A]
    LB -->|Select backend| I2[Inventory instance B]
    LB -->|Select backend| I3[Inventory instance C]
~~~~

### Common routing patterns

| Pattern | How it works | Example use case |
| --- | --- | --- |
| L4 load balancing | Forwards TCP/UDP connections based on network and transport metadata. | Balancing connections across a backend pool. |
| L7 routing | Inspects application data such as host, path, headers, or method to pick a route. | /orders to order-service, /inventory to inventory-service. |
| API gateway | Provides an API entry point, routes to multiple services, and often applies auth, rate limiting, or request transformation. | External clients calling microservice APIs through a unified gateway. |
| Ingress controller | Controls external HTTP/HTTPS access to Services inside Kubernetes. | Exposing web applications by hostname and path. |
| Internal load balancer | Distributes internal traffic across instances. | One service calling another via a stable internal address. |

### Where do routers get their backend lists?

There are several ways to supply backends:

- **Static configuration:** backend addresses are declared in config files. Easy to understand, yet hard to keep up when instances change frequently.
- **DNS:** the router periodically resolves backend hostnames. Pay attention to TTL and how the router refreshes DNS.
- **Registry:** the router or an adapter queries Eureka/Consul for instance lists, metadata, and registration status.
- **Orchestration platform:** in Kubernetes, controllers or proxies can obtain endpoints from Service and EndpointSlice via the API/control plane.

Routers may run health checks independently of the registry. The registry reports registered instances; the router's health checks determine whether backends respond according to the router's operational criteria. These two states can diverge temporarily.

### Path-based routing example

An API gateway can route:

~~~~text
/api/orders/**     -> order-service
/api/inventory/**  -> inventory-service
/api/payments/**   -> payment-service
~~~~

External clients only need to know the gateway's hostname. The gateway inspects the request and chooses a target based on configured routes. Specific instance addresses can be resolved by a load balancer, registry integration, or network platform.

Key point to remember: a gateway is not necessarily a registry. Gateways typically rely on configured routing data or data synced from another discovery source. Nor should every internal request traverse a public API gateway; east-west service-to-service communication usually has better alternatives.

## 4. Service mesh: discovering and controlling east-west traffic

A service mesh is an infrastructure layer dedicated to managing inter-service communication. In the common sidecar model, each workload runs alongside an attached proxy. The application sends requests through its local proxy; the proxy connects to the destination proxy or workload using configuration received from the control plane.

A service mesh is typically split into two parts:

- **Data plane:** proxies handling actual traffic. Proxies can perform endpoint selection, load balancing, timeouts, retries, circuit breaking, authentication, and telemetry collection.
- **Control plane:** gathers service/endpoint info from the platform or registry, applies policies, and distributes configuration to proxies.

~~~~mermaid
flowchart TB
    subgraph Control[Control plane]
        K8s[Kubernetes API / Registry]
        CP[Mesh Control Plane]
        K8s --> CP
    end
    subgraph Data[Data plane]
        A[App A] --> PA[Proxy A]
        PA -->|East-west request| PB[Proxy B]
        PB --> B[App B]
    end
    CP -->|Endpoints and policies| PA
    CP -->|Endpoints and policies| PB
~~~~

When App A calls inventory-service, proxy A can accept the logical destination name. The proxy uses its latest endpoint configuration to pick an instance of inventory-service, establish the connection, and enforce policies. The application may not need to query Eureka or Consul directly on every request.

### How does a service mesh discover endpoints?

A mesh needs a data source to know which services and endpoints exist. That source can be:

- The Kubernetes API, including Service, Pod, and EndpointSlice.
- An external registry such as Consul or Eureka, via an appropriate integration.
- Endpoint configurations declared in or synced from another control system.

The control plane translates that data into configuration proxies understand. With Envoy, a common dynamic config distribution protocol is xDS; endpoint discovery can be delivered via Endpoint Discovery Service (EDS). Exact protocol names and integration mechanics depend on the mesh product and version.

Thus, a mesh does not conjure instance lists out of thin air. It needs a source of truth for services and endpoints, then distributes that information to the data plane. If the data source updates slowly or the control plane loses connectivity, proxies may keep using stale endpoint configuration for a period of time.

### What does a mesh provide beyond discovery?

- Load balancing across endpoints, optionally with locality-aware routing.
- Policy-driven timeouts, retries, and circuit breaking.
- Workload encryption and authentication, typically via mTLS and service identities.
- Traffic observability such as request rates, latencies, error rates, and trace context.
- Canary rollouts, traffic splitting, or version-based routing when supported by the mesh product.
- Inter-workload communication policies, e.g. which service is allowed to call which service.

A mesh carries operational overhead: proxies consume CPU/memory, add a request-processing layer, and require managing the control plane, certificates, policies, and network configuration. Do not deploy a mesh just to resolve a simple hostname.

## 5. Comparing DNS, routers, and service meshes

| Criterion | DNS | Router / Load balancer | Service mesh |
| --- | --- | --- | --- |
| Primary responsibility | Resolve names to addresses or service info | Pick a backend and forward requests | Manage service-to-service communication and traffic policies |
| Inputs | DNS records and resolver queries | Routes, backend pools, health state, endpoints | Services/endpoints from platform or registry plus policies |
| Typical selection unit | Hostname/IP | Connection or request | Endpoint per request/connection via proxy |
| Health awareness | Not tied to application health by default | Usually includes backend health checks | Can combine health/endpoint state with mesh policies |
| Metadata and policies | Limited | Depends on router/gateway capabilities | Usually richer for internal communication |
| Components to operate | DNS zones, resolvers, records, TTLs | Routers, gateways, load balancers, and backend configs | Control plane, data plane proxies, certificates, and policies |
| Best suited for | Stable names, simple resolution | Centralized entry points, host/path routing, and load balancing | Many services needing uniform policies, security, and telemetry |

These components can work together. For instance, DNS directs clients to an API gateway; the gateway obtains backends from a registry; east-west traffic between workloads flows through a service mesh. On another platform, Kubernetes DNS resolves the Service name, ClusterIP distributes to Pods, and mesh proxies enforce mTLS and retries.

## 6. Combining with Spring Cloud Service Discovery

Spring Cloud provides abstractions so applications are not locked into one specific registry mechanism:

- DiscoveryClient lets applications query instances by service ID.
- ServiceRegistry provides instance registration and deregistration operations.
- Spring Cloud LoadBalancer can pick an instance from discovery data when HTTP clients are configured with the appropriate integration.

With Eureka or Consul, applications usually query the registry through Spring Cloud's implementation. With Kubernetes, you can use Spring Cloud Kubernetes integration to discover Services/endpoints as configured. DNS and router addresses can also be used directly as stable targets if applications do not need to select individual instances themselves.

For example, there are three distinct calling patterns:

1. **Calling via DNS/router:** the app calls http://inventory.internal; DNS returns the load balancer's VIP and the load balancer selects a backend.
2. **Calling via Spring Cloud discovery:** the app uses service ID inventory-service; DiscoveryClient fetches the instance list and Spring Cloud LoadBalancer picks one instance.
3. **Calling via service mesh:** the app sends requests to a logical target name; the local proxy selects an endpoint using configuration pushed by the mesh control plane.

Do not assume these three calling patterns behave identically. With the first, the app may see only one VIP. With the second, the app sees the instance list. With the third, endpoint selection typically happens inside the proxy. Clearly identify which component performs discovery and which performs load balancing to avoid duplicate configurations or hard-to-diagnose behavior.

### Model selection examples

| Context | Suggested approach |
| --- | --- |
| A few internal apps with infrequent endpoint changes | DNS pointing to a stable address or internal load balancer. |
| Microservices running outside Kubernetes needing dynamic instance lookup | Eureka/Consul with DiscoveryClient and LoadBalancer. |
| Apps deployed on Kubernetes needing only internal Service calls | Kubernetes Service DNS and ClusterIP may already suffice. |
| Many workloads needing uniform mTLS, traffic policies, and telemetry | Consider a service mesh after evaluating operational cost. |
| Public APIs needing host/path routing | API gateway or ingress controller, optionally backed by a registry or mesh. |

## 7. Scenarios requiring careful handling

**Stale endpoints lingering in caches.** DNS TTLs, runtime caches, registry caches, and proxy configs refresh on different schedules. When an instance is replaced, a client can still send requests to the old address. Check cache durations at each layer, deregistration timing, and how clients handle connection errors.

**Inconsistent health checks.** An instance may remain registered in Eureka while already unready to serve. A router may mark a backend unhealthy before the registry updates; a mesh may keep an endpoint yet trip outlier detection to pause sending traffic. Clarify which status source governs actual traffic.

**Misrouting due to unreachable addresses.** DNS or a registry may advertise an IP valid only inside one subnet/container network. Verify addresses from the caller's actual network namespace, not only from a developer workstation.

**Retries amplifying load.** Retries in HTTP clients, gateways, and meshes can stack. When a backend fails, simultaneous multi-layer retries can amplify traffic. Set overall timeouts, cap retry counts, and retry only semantically safe requests.

**Two layers both load balancing.** If a client picks an instance itself and then sends through another load balancer, endpoint selection occurs twice. This is not always wrong, yet you must understand which layer owns sticky sessions, health state, and locality policies.

**Temporary control plane or registry outage.** Many proxies can continue using their latest known configuration, though that capability depends on implementation and settings. Verify behavior when losing the control plane, how endpoints update, and how recovery works before going to production.

## 8. Design and operations checklist

- [ ] Identify the service IDs and hostnames callers use.
- [ ] Identify the endpoint source of truth: DNS, Eureka/Consul, Kubernetes API, or another source.
- [ ] Specify which component selects instances: client, load balancer, gateway, or mesh proxy.
- [ ] Ensure advertised addresses are reachable from callers' networks.
- [ ] Configure TTLs/caches and refresh cycles aligned with instance churn rate.
- [ ] Design health checks and graceful deregistration to minimize requests hitting stopping instances.
- [ ] Define timeouts, retries, circuit breaking, and load limits across participating layers.
- [ ] Protect internal DNS, registries, gateways, control planes, and admin endpoints.
- [ ] Monitor name resolution errors, connection errors, unhealthy endpoints, latency, and error rates per layer.
- [ ] Test scenarios where an endpoint changes IP, an instance stops abruptly, and the registry/control plane disconnects.

## Key takeaways

- DNS answers which address a service name resolves to; TTLs and caches govern how long old addresses remain in use.
- Routers and load balancers choose backends and forward requests; backend lists can come from config, DNS, registries, or orchestrators.
- A service mesh pushes discovery and traffic policies to data-plane proxies via a control plane; the mesh still requires an endpoint data source.
- Eureka/Consul, Kubernetes DNS, routers, and meshes can complement one another at different layers.
- When designing, clearly specify the endpoint source, where instance selection happens, and where health checks, security, and retries are enforced to avoid state drift and unpredictable behavior.
