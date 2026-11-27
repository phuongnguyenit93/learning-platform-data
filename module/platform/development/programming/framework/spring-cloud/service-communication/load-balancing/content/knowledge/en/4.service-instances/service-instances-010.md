# When DNS or Infrastructure Already Provides Load Balancing

A service can be accessed through a stable address provided by DNS, a Kubernetes Service, a reverse proxy, or an infrastructure load balancer. In that case, the caller sends requests to the shared endpoint; the infrastructure component picks a healthy backend to process them. The application does not necessarily need to fetch a list of individual replicas and select an instance itself using Spring Cloud LoadBalancer.

Spring Cloud LoadBalancer solves a different layer of the problem: selecting one `ServiceInstance` from an instance list supplied by Spring Cloud discovery. If that list has already been collapsed into a single virtual address, adding an instance-selection layer inside the application may bring no benefit. Clearly establish who is responsible for backend selection, health checks, failover, and request observability before configuring the client.

## 1. Distinguishing DNS, virtual addresses, and Spring Cloud LoadBalancer

The mechanisms below all shield callers from needing to know individual replica addresses, yet they operate at different layers.

| Mechanism | What the caller sees | Component selecting the backend | Typical selection scope |
|---|---|---|---|
| DNS pointing to a virtual IP (VIP) | A stable hostname or IP | Load balancer behind the VIP | Backends belonging to the VIP's pool |
| DNS returning multiple addresses | A hostname with multiple A/AAAA records | Resolver and HTTP client choose an address at resolution/connection time; platform-dependent behavior | IPs returned by DNS |
| Kubernetes Service of type ClusterIP | Service DNS name and a ClusterIP | Cluster data plane forwards connections to endpoints | Pod endpoints of the Service |
| Reverse proxy / gateway / cloud load balancer | A gateway hostname or endpoint | Proxy or load balancer | Configured backend pool, route, zone, or region |
| Spring Cloud LoadBalancer | Service ID and `ServiceInstance` list | Client inside the application | Instances supplied by `ServiceInstanceListSupplier` |

By nature, DNS resolves names to addresses. A DNS record pointing to a VIP does not itself pick a Pod or server behind the VIP; that job belongs to the load balancer receiving traffic at the VIP.

DNS can also return multiple IP addresses to distribute traffic. However, DNS round robin is not inherently health-aware load balancing. Resolution results can be cached by the JVM, operating system, or HTTP library; connection pools and HTTP keep-alive can also pin connections to one address across many requests. Therefore, do not assume every HTTP request will be distributed to a different IP.

Spring Cloud LoadBalancer operates after obtaining a candidate list of `ServiceInstance`s. If application discovery returns multiple instances, it can apply a selection strategy such as Round Robin. If discovery returns only a single instance representing a VIP, LoadBalancer sees only one candidate; actual backend selection is still performed by the infrastructure.

## 2. Request flow when infrastructure already balances load

For example, a caller accesses `https://inventory.internal`. DNS resolves this hostname to the load balancer's address. The load balancer checks backend status and forwards the request to an inventory replica.

~~~mermaid
flowchart LR
    A["Caller service"] -->|"https://inventory.internal"| B["DNS"]
    B -->|"VIP / stable endpoint"| C["Infrastructure Load Balancer"]
    C -->|"select healthy backend"| D["inventory replica 1"]
    C -->|"or"| E["inventory replica 2"]
    C -->|"or"| F["inventory replica 3"]
~~~

In this flow, the caller only needs to know a stable hostname. The caller does not need to query a registry for individual replicas or pick an IP from a pool itself. Infrastructure manages the backend pool, health probes, and traffic routing according to configured policies.

Another example is a Kubernetes Service of type ClusterIP:

~~~mermaid
flowchart LR
    A["Caller Pod"] -->|"http://inventory-service"| B["Kubernetes DNS"]
    B -->|"Service ClusterIP"| C["Service virtual IP / data plane"]
    C --> D["inventory Pod 1"]
    C --> E["inventory Pod 2"]
    C --> F["inventory Pod 3"]
~~~

Inside the cluster, the Service name typically resolves to a ClusterIP. The cluster data plane chooses a Pod endpoint for the connection. Depending on network implementation and protocol, selection usually happens at connection level; multiple HTTP requests sharing one keep-alive connection may keep hitting the same Pod. That does not mean the Service fails to load balance: it distributes new connections across multiple endpoints.

With a Kubernetes headless Service, DNS can return Pod addresses instead of a single ClusterIP. That is a different model: the caller or resolver library must handle the address list and update DNS according to TTL. Do not treat a headless Service as equivalent to a VIP with health-aware load balancing.

## 3. When is Spring Cloud LoadBalancer unnecessary on the caller?

Client-side load-balancing integration is unnecessary when the caller already has a stable endpoint and infrastructure handles distribution across replicas. Common cases include:

- The target service is exposed via a VIP or load balancer hostname.
- The caller runs in Kubernetes and calls a ClusterIP Service via Service DNS.
- The caller goes through an API gateway or reverse proxy that already manages the backend pool.
- A cloud platform provides a stable endpoint and performs target health checks automatically.

In those cases, the HTTP client can call a standard URL. Example caller configuration:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: order-service

clients:
  inventory:
    base-url: https://inventory.internal
~~~

Creating a plain `RestClient`:

~~~java
@Configuration
public class InventoryHttpConfiguration {

    @Bean
    RestClient inventoryRestClient(Environment environment) {
        String baseUrl = environment.getRequiredProperty(
                "clients.inventory.base-url"
        );

        return RestClient.builder()
                .baseUrl(baseUrl)
                .build();
    }
}
~~~

Using the client in a service:

~~~java
@Service
public class InventoryClient {

    private final RestClient restClient;

    public InventoryClient(RestClient inventoryRestClient) {
        this.restClient = inventoryRestClient;
    }

    public InventoryResponse getInventory(String sku) {
        return restClient.get()
                .uri("/api/inventory/{sku}", sku)
                .retrieve()
                .body(InventoryResponse.class);
    }
}
~~~

Here the builder is not annotated with `@LoadBalanced`. `RestClient` sends requests to the configured hostname; DNS and network infrastructure handle resolution and traffic distribution. There is no need to put replica IP lists into code.

With `WebClient`, likewise use a plain builder:

~~~java
@Bean
WebClient inventoryWebClient(Environment environment) {
    String baseUrl = environment.getRequiredProperty(
            "clients.inventory.base-url"
    );

    return WebClient.builder()
            .baseUrl(baseUrl)
            .build();
}
~~~

WebClient can still operate reactively/non-blocking. Whether or not to use Spring Cloud LoadBalancer is a decision about target selection, independent of how the application waits on I/O.

With Spring Cloud OpenFeign, you can declare a concrete URL:

~~~java
@FeignClient(
        name = "inventory-service",
        url = "https://inventory.internal"
)
public interface InventoryFeignClient {

    @GetMapping("/api/inventory/{sku}")
    InventoryResponse getInventory(@PathVariable("sku") String sku);
}
~~~

When `url` is supplied, Feign calls that endpoint directly instead of asking Spring Cloud LoadBalancer to select a `ServiceInstance` by service ID. If `url` is omitted and only the client name is declared, load-balancing/discovery integration may be used to find instances, depending on application configuration and dependencies.

## 4. Avoiding two layers both selecting from the same replica pool

Suppose DNS already routes `inventory.internal` to a VIP, and that VIP picks one of three replicas. If the caller also declares `inventory.internal` as a service ID in Spring Cloud LoadBalancer, you must understand the exact `ServiceInstance` list provided by discovery.

If the list contains only one instance representing the VIP:

~~~text
Spring Cloud LoadBalancer
        |
        | only 1 ServiceInstance
        v
https://inventory.internal
        |
        v
Infrastructure Load Balancer
        |
        +---- inventory-1
        +---- inventory-2
        +---- inventory-3
~~~

Spring Cloud LoadBalancer does not distribute across the three replicas. It only picks the single VIP; the infrastructure load balancer selects the backend. In this case, a plain client configuration is usually simpler to understand and involves fewer moving parts.

If both Spring Cloud LoadBalancer and infrastructure select directly from a replica group, the architecture ends up with two decision layers:

~~~mermaid
flowchart LR
    A["Caller"] --> B["Spring Cloud LoadBalancer"]
    B -->|"select instance / zone"| C["Gateway or VIP"]
    C --> D["Infrastructure Load Balancer"]
    D --> E["Backend replicas"]
~~~

Two layers are not necessarily wrong. For instance, the application layer might select an appropriate region or gateway, while the in-region load balancer distributes across local replicas. Yet each layer needs a distinct purpose and a clear candidate set.

Avoid redundant configurations where both layers manage the exact same backend pool for no reason. That makes it hard to tell which layer is ejecting failing instances, where retries are happening, which backend received a request, and why load is skewed.

## 5. Distinguishing a service ID from a DNS-managed hostname

The name `inventory-service` can appear in multiple places without automatically carrying the same meaning:

- In Spring Cloud LoadBalancer, it may be a service ID used to look up a `ServiceInstance` list.
- In Kubernetes, it may be a Service DNS name, such as `inventory-service.default.svc.cluster.local`.
- In enterprise DNS, it may be a hostname pointing to a VIP or reverse proxy.

When using Spring Cloud LoadBalancer, a URI like `http://inventory-service` is treated by a load-balanced client as a logical name to resolve through Spring Cloud. This mechanism requires an instance supplier for that service ID.

When you want to call DNS or a VIP directly, configure the real hostname and use a plain HTTP client, such as `https://inventory.internal`. Do not annotate a builder with `@LoadBalanced` simply because the hostname shares the same name as a service ID. That annotation changes how URIs are resolved and requires corresponding discovery/load-balancer configuration.

Clear naming reduces confusion:

| Meaning | Example |
|---|---|
| Service ID in Spring Cloud | `inventory-service` |
| Kubernetes Service DNS name | `inventory-service.default.svc.cluster.local` |
| Internal load balancer hostname | `inventory.internal` |
| Physical replica address | `10.20.1.14:8080` |

A DNS name may literally be the Service name in Kubernetes, yet it remains a DNS/network endpoint. It does not mean Spring Cloud discovery has returned a `ServiceInstance` list to the application.

## 6. DNS round robin is not the same as health-aware load balancing

A DNS zone can contain multiple records for the same hostname:

~~~dns
inventory.internal.  30  IN  A  10.20.1.14
inventory.internal.  30  IN  A  10.20.1.15
inventory.internal.  30  IN  A  10.20.1.16
~~~

A resolver may receive multiple addresses for one query. Return order or how the client picks an address depends on the DNS server, resolver, caches, and HTTP client. The 30-second TTL in the example is the advertised cache duration, not a guarantee that every client will re-query DNS after exactly 30 seconds.

Simple DNS round robin does not inherently know which backend is failing. If an address keeps being returned after a server stops, callers may keep hitting failed connections until the record updates and caches expire. A DNS service with health checks or advanced routing may behave better, though you must verify the provider's actual policy.

Dedicated load balancers can typically check backend health, remove failing targets from the pool, restore targets once healthy again, and apply distribution policies such as least connections, weighted routing, or locality. Even so, exact capabilities depend on the load balancer type and configuration.

When using multi-address DNS, observe:

- Whether DNS returns one or multiple addresses and how ordering changes.
- How long the JVM or resolver caches results.
- Whether the HTTP client opens new connections frequently or reuses a connection pool.
- Whether health checks strip failing addresses from answers.
- How the application behaves when DNS changes while old connections remain open.

Do not conclude DNS round robin is distributing requests merely from seeing multiple DNS records. Observe the actual backends receiving requests.

## 7. Which layer owns health checks and failover?

When infrastructure handles load balancing, know where health checks run. A load balancer may use TCP probes, HTTP health endpoints, or protocol-specific checks. It can stop routing new connections to an unhealthy backend, though in-flight requests may still fail if a backend stops mid-request.

In Spring Cloud LoadBalancer, the candidate list usually comes from `ServiceInstanceListSupplier`. Suppliers can be combined to filter instances by health checks or metadata. This helps when the application picks directly across multiple instances. If discovery returns only a VIP and infrastructure checks backends, Spring-layer health checks cannot observe individual replicas behind the VIP.

Distinguish:

| Scenario | Health check to observe |
|---|---|
| Spring Cloud LoadBalancer picks multiple replicas directly | Each `ServiceInstance` the caller can choose |
| Caller calls a VIP | The VIP/load balancer and target status behind it |
| Caller calls a Kubernetes ClusterIP | Kubernetes Service endpoints and Pod readiness mechanisms |
| Caller uses multi-IP DNS | DNS health policy, TTL/cache, and connectivity to each IP |

Application readiness should reflect the ability to accept business traffic. Liveness typically drives process restart decisions. Avoid a health endpoint that checks so many external dependencies that healthy backends get cascaded as failing during a brief dependency blip.

Failover also incurs latency. A load balancer needs probe cycles to detect failure; DNS needs record updates and cache expiry; clients need new connections to use new addresses. Consequently, a newly stopped backend may continue receiving requests or causing errors for a period of time.

## 8. Timeouts, retries, and connection pools across multiple layers

When requests pass through caller, gateway, and load balancer, total processing time includes time spent at every layer. Set a deadline for the whole request and allocate reasonable timeout budgets per hop.

Example:

~~~text
Caller deadline: 2.5 seconds
    |
    +-- Connect / wait for gateway: max 2.0 seconds
            |
            +-- Load balancer picks backend
            +-- Backend processing: remaining time budget
~~~

The values above only illustrate budget splitting; measure real latencies and choose timeouts according to the service's SLA. Connect timeout and response read timeout can be two separate settings on the HTTP client.

Retries can occur at multiple layers: HTTP client, Spring Cloud LoadBalancer, gateway, or infrastructure load balancer. If every layer retries multiple times, a single initial request can fan out into many backend calls. When a service is overloaded, simultaneous retries worsen the incident.

Some principles:

1. Pick one primary layer responsible for retries per error type, or document coordination explicitly if multiple layers are required.
2. Bound total attempts and total elapsed time to the caller's deadline.
3. Use backoff and jitter to reduce synchronized retries from many clients.
4. Retry only operations safe to repeat; write operations need idempotency keys or duplicate-execution guards.
5. Distinguish connection errors, timeouts, HTTP statuses, and business errors before deciding to retry.

Connection pools and keep-alive affect how load balancing is observed. With L4 load balancing or a Kubernetes Service, many requests over one TCP connection can go to the same backend. To verify connection-level distribution, open enough new connections and check backend logs/metrics. With HTTP/2, one connection can multiplex many streams, so do not expect infrastructure to independently rebalance every request stream.

## 9. When to combine Spring Cloud and infrastructure

Some systems need multiple distribution layers because they solve different scopes. For example, an application might select a region or gateway per tenant, and then the in-region load balancer chooses a replica.

~~~text
Order service
    |
    | Spring Cloud LoadBalancer selects region
    v
Region gateway (region-a or region-b)
    |
    | Infrastructure LB selects healthy backend
    v
Inventory replica in region
~~~

To design clear coordination:

- Each layer picks only from the candidate set within its responsibility.
- The Spring layer can choose the gateway/region, while infrastructure chooses replicas within the region.
- Health checks at each layer must probe the exact object managed by that layer.
- Do not let one layer mark a gateway healthy merely because its VIP accepts TCP connections if business readiness requires deeper checks.
- Define retries and timeouts across the entire request path.
- Attach a trace ID to correlate logs from caller through gateway to backend.

Another case is when a caller uses service discovery to pick among multiple internal gateways, while each gateway manages replicas. In that setup, the `ServiceInstance` list in Spring Cloud should contain gateway endpoints. Do not mix individual Pods and gateways under the same service ID if the two endpoint types carry different semantics and routing policies.

## 10. How to verify infrastructure is actually load balancing

Do not rely solely on configuration or DNS records. Verify end to end.

**Step 1: check DNS and endpoint.**

In PowerShell:

~~~powershell
Resolve-DnsName inventory.internal
~~~

Record the returned records, addresses, and TTL. If the hostname points to a VIP, identify which load balancer receives traffic at that address.

**Step 2: send multiple requests through the shared endpoint.**

~~~powershell
1..20 | ForEach-Object {
    Invoke-RestMethod https://inventory.internal/api/instance
}
~~~

The `/api/instance` endpoint in this example must be provided by the service to return a replica identifier. If you do not want to expose replica details in production responses, inspect backend logs or traces instead.

**Step 3: check distribution at the backend.**

Compare request counts received by each replica, target status in the load balancer dashboard, and gateway access logs. If all requests hit a single replica, check connection reuse, sticky sessions, distribution policy, and actual connection count before concluding the configuration is broken.

**Step 4: test an unhealthy backend.**

Stop one replica or fail its readiness/health probe in a test environment. Observe how long the load balancer takes to remove the replica from the pool, what errors the caller sees, and how long recovery takes once the replica becomes healthy again.

**Step 5: test behavior when DNS changes.**

If using multi-address DNS, update a record in a test environment and observe how long clients take to start using the new address. Compare DNS TTL with JVM caches, connection pools, and connection lifetimes.

Record the hostname used by the caller, the VIP or gateway address, the actual backend, response times, HTTP statuses, and failover errors. This data helps separate faults across DNS, network, load balancer, HTTP client, and target application.

## 11. Checklist for choosing the right mechanism

- [ ] Identify whether the caller invokes a Spring Cloud service ID, DNS name, ClusterIP, VIP, or gateway URL.
- [ ] Identify which component selects backend replicas.
- [ ] If infrastructure already manages the backend pool, use a plain HTTP client with a stable endpoint when Spring does not need to select a gateway.
- [ ] If Spring Cloud LoadBalancer directly picks among multiple `ServiceInstance`s, clearly configure the discovery source and selection policy.
- [ ] Do not confuse DNS round robin with health-aware load balancing.
- [ ] Check TTLs, DNS caching, connection pooling, and keep-alive.
- [ ] Place health checks at the right layer and understand failover latency.
- [ ] Set timeouts aligned with end-to-end deadlines and avoid duplicate retries across layers.
- [ ] If coordinating multiple layers, separate selection scope clearly: region/gateway at one layer, replicas at another.
- [ ] Use logs, metrics, and traces to confirm which backend actually receives requests.

When DNS or infrastructure already provides a stable endpoint and takes responsibility for choosing replicas, callers usually only need to call that endpoint with a plain HTTP client. Spring Cloud LoadBalancer shines when the application must choose among multiple `ServiceInstance`s provided by discovery. Both layers can be combined as long as each has a clear selection scope, appropriate health checks, and coordinated timeout/retry policies across the entire request.
