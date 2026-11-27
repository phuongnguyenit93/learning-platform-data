# Full Catalog Query Overhead and Scoping Discovery

A service registry stores information about many services and instances so consumers can look up call targets by logical name. As a system grows, the number of services, replicas, namespaces, and deployment zones increases. Reading the entire catalog can incur significant costs in network, CPU, memory, synchronization time, and access permissions. An application that only needs to call `inventory-service` yet scans every service to find the name it needs is a sign of poor design.

In Spring Cloud, distinguish querying the service list via `DiscoveryClient.getServices()` from querying instances of a single service via `DiscoveryClient.getInstances(serviceId)`. Scoping lookups helps the application process only the data it needs. However, the background cost of each registry differs: the Eureka client typically syncs a registry snapshot into a local cache, whereas Consul, ZooKeeper, and Kubernetes can support per-service or namespace-scoped queries depending on the integration.

## 1. Catalog, Service, and Instance

A catalog can contain many service IDs. Each service ID can in turn have one or more instances:

```text
Catalog
  inventory-service
    inventory-1
    inventory-2
    inventory-3
  order-service
    order-1
    order-2
  payment-service
    payment-1
  notification-service
    notification-1
    notification-2
```

Concepts:

- **Catalog:** the set of services known to the registry within a cluster, partition, namespace, or root path.
- **Service ID:** the logical name consumers use for lookups, e.g., `inventory-service`.
- **Instance:** a concrete running copy of a service, with host, port, URI, and metadata.
- **Discovery scope:** the scope of data a client is permitted or configured to discover, such as a single service ID, a namespace, or the entire catalog.

If a catalog has `S` services and `I` total instances, enumerating the full catalog may require processing data proportional to `S + I`. If a consumer only needs service `x` with `I_x` instances, querying by service can limit the data the application has to process down to roughly `I_x`. This is a conceptual cost model; actual costs also depend on the registry, cache, transport, filters, and how the provider stores data.

## 2. Two DiscoveryClient APIs with Different Scopes

Spring Cloud Commons provides the `DiscoveryClient` abstraction:

```java
public interface DiscoveryClient {
    String description();

    List<ServiceInstance> getInstances(String serviceId);

    List<String> getServices();

    default int getOrder() {
        return 0;
    }
}
```

Two important methods:

| Method | Result | When to Use |
|---|---|---|
| `getInstances("inventory-service")` | Instances of a single service ID | Consumer needs to call a specific service |
| `getServices()` | List of service IDs discoverable by the client | Admin tools, dashboards, or features that genuinely need enumeration |

Example of a consumer needing to call inventory:

```java
List<ServiceInstance> instances =
    discoveryClient.getInstances("inventory-service");
```

This is a properly scoped query. There is no need to call `getServices()` and iterate through all services to find `inventory-service`.

Anti-pattern:

```java
for (String serviceId : discoveryClient.getServices()) {
    if ("inventory-service".equals(serviceId)) {
        return discoveryClient.getInstances(serviceId);
    }
}
```

The code above performs an unnecessary enumeration step. When the catalog is large, calling `getServices()` can force the client to traverse or materialize the service list before retrieving the right instances.

Note: the abstraction only describes the API. It does not guarantee that every implementation has the same cost. One provider may return the list from a local cache; another may query an API or read a znode tree. You must examine the mechanism of the registry in use.

## 3. Sources of Overhead When Reading the Full Catalog

Enumerating the catalog can create overhead at multiple layers:

| Layer | Potential Overhead |
|---|---|
| Registry server | Processing broad requests, reading many records, filtering, and serializing data |
| Network | Transferring large payloads between the registry and client |
| Client parser | Deserializing JSON, protobuf, or znode data |
| Heap/memory | Retaining service and instance lists in cache or object graphs |
| CPU | Iterating, sorting, filtering, allocating objects, and computing metadata |
| Refresh/watch | Syncing snapshots or processing many events when the catalog changes |
| Observability | Increasing log/metric cardinality if tagged by every service or instance |
| Security | Client may read more information than its business scope requires |

A catalog-listing request may appear lightweight when the system has only a few services. However, with thousands of services, many replicas, many consumers, and dashboards polling continuously, total load can rise substantially.

Distinguish the cost of a single API call from the background cost of the registry client. For example, a Eureka client may periodically fetch the full registry into cache; calling `getInstances(serviceId)` ensures the consumer only processes the instances it needs, though it does not necessarily eliminate the full-registry fetch cost at the Eureka client layer.

## 4. Why You Should Not Enumerate on Every Request

Do not query the entire catalog on the business HTTP request path:

```java
@GetMapping("/items/{id}")
public ItemResponse getItem(@PathVariable String id) {
    List<String> services = discoveryClient.getServices();

    // Find inventory-service in the entire list
    // before calling the target service.
    return inventoryClient.getItem(id);
}
```

The service list does not need to be re-fetched for every request. A service ID is a known dependency of the application, so it can be declared statically in a Feign client or configuration. Enumerating on every request increases CPU, allocations, and latency without adding business value.

Use a client scoped by service ID instead:

```java
@FeignClient(name = "inventory-service")
public interface InventoryClient {

    @GetMapping("/api/items/{id}")
    ItemResponse getItem(@PathVariable("id") String id);
}
```

When using OpenFeign with Spring Cloud LoadBalancer and discovery integration, LoadBalancer requests the instance list for that exact service ID. The consumer does not need to traverse the catalog itself to find the target.

## 5. Eureka: Broad Registry Fetch and Client-Side Cache

Eureka clients typically fetch a registry snapshot from the Eureka Server into a local cache. Subsequent instance lookups can read from the cache instead of sending a new catalog request per call.

Common consumer configuration:

```yaml
eureka:
  client:
    fetch-registry: true
    registry-fetch-interval-seconds: 30
```

`fetch-registry` indicates whether the Eureka client fetches the registry for discovery. `registry-fetch-interval-seconds` adjusts the fetch interval depending on client version and configuration.

Key points to understand:

- Eureka clients typically receive a broad registry snapshot rather than fetching only a single service ID on each `getInstances` call.
- `DiscoveryClient.getInstances(serviceId)` typically filters from the local registry cache.
- Reducing fetch frequency can lower network/CPU load, but keeps client-side data stale longer.
- Disabling `fetch-registry` prevents the client from fetching the registry for lookups; this is not a way to restrict the catalog to one service.
- Do not assume Eureka has a universal property to fetch only a single service ID if the integration/version does not support such a mechanism.

For instance, if a consumer only needs `inventory-service`, code should still call `getInstances("inventory-service")` or use a Feign service name. That reduces enumeration work at the application layer even though the Eureka client may still maintain a broad registry cache.

### When to Re-evaluate Eureka Fetch?

- The registry has a very large number of instances.
- Many consumers are all fetching the full snapshot.
- Fetch payloads are large or deserialization time is rising.
- Heap used by the registry cache takes up a significant share.
- Refreshes cause network bursts or CPU spikes.

You can adjust the fetch interval after measuring. Do not increase the interval solely to reduce load if the application needs to detect new or removed instances quickly. Evaluate both load and update latency together.

## 6. Consul: Per-Service Queries and Filtering

Consul provides APIs to query the health of a specific service, for example:

```http
GET /v1/health/service/inventory-service
```

If you only need passing instances, you can use the `passing=true` query parameter:

```bash
curl "http://consul.internal:8500/v1/health/service/inventory-service?passing=true"
```

Querying a specific service is usually more appropriate than a catalog-wide API:

```http
GET /v1/catalog/services
```

The catalog services API lists many services in the catalog. Use it only when you genuinely need to discover the list of services, such as in an admin page or inventory tool.

Consul also supports filtering by tag, namespace, partition, or query conditions depending on version and configuration. Filters help narrow returned results, but do not replace authorization. ACL tokens are still needed to restrict which services/namespaces a client can read.

In Spring Cloud Consul, use `DiscoveryClient.getInstances(serviceId)` for per-service lookups. Options such as returning only passing instances, watches, or caching depend on the Spring Cloud Consul version; verify properties and actual behavior before relying on them in production.

## 7. ZooKeeper: Reading Only the Required Service Branch

Spring Cloud Zookeeper Discovery typically organizes registrations under a root path. Conceptually:

```text
/services
  /inventory-service
    /inventory-1
    /inventory-2
  /order-service
    /order-1
  /payment-service
    /payment-1
```

If a consumer needs `inventory-service`, the discovery integration can read the child nodes under the branch:

```text
/services/inventory-service
```

Reading a specific service branch has a narrower scope than listing all children under `/services` and then reading every instance.

However, do not manually manipulate internal znodes if Spring Cloud Zookeeper/Curator manages registration. Use `DiscoveryClient` or supported APIs. Znode layout, serialization, watchers, and caches can vary across versions.

ZooKeeper ACLs can also restrict read permissions by path. This helps isolate discovery scope: the inventory consumer only needs to read the relevant service branch, while operators get read access to the entire root if their role requires it.

## 8. Kubernetes: Limiting Namespaces and Resources

In Kubernetes, Services and EndpointSlices are partitioned by namespace. An application typically only needs to discover services within one or a few specific namespaces.

Spring Cloud Kubernetes provides options to restrict namespace discovery depending on the version, for example:

```yaml
spring:
  cloud:
    kubernetes:
      discovery:
        all-namespaces: false
        namespaces:
          - shop
          - fulfillment
```

The intent is to restrict discovery scope to configured namespaces, if the integration version in use supports these properties. Check the release train documentation before applying; property names and behaviors may vary across versions.

Kubernetes RBAC should only grant list/watch/get permissions for the required resources in permitted namespaces. Depending on the discovery mode, a client may need read access to Services, Endpoints, or EndpointSlices, and occasionally Pod metadata. Do not grant cluster-wide permissions just because an application needs to call a service in the `shop` namespace.

If you only need to call an internal Kubernetes service, Service DNS is often sufficient:

```text
http://inventory-service.shop.svc.cluster.local
```

You do not necessarily have to list every Service via the Kubernetes API to call a service with a known name. Spring Cloud Kubernetes Discovery is useful when the application needs the `DiscoveryClient` abstraction, metadata, or client-side load balancing; otherwise, DNS and ClusterIP already provide platform-level discovery for ordinary calls.

## 9. Limiting Scope by Service, Namespace, and Tenant

There are multiple ways to limit scope, depending on the registry:

| Scope | Example | Purpose |
|---|---|---|
| Service ID | Query only `inventory-service` | Consumer only needs one dependency |
| Allowlist | `inventory-service`, `pricing-service` | Application only knows about approved dependencies |
| Namespace | `shop`, `fulfillment` | Restrict by domain or environment |
| Consul namespace/partition | An assigned namespace/partition | Partition catalog by organization |
| ZooKeeper root/path | `/services/shop` | Split registration tree by domain |
| Kubernetes namespace/RBAC | Only list/watch resources in permitted namespaces | Restrict both visible data and API permissions |

Scope should reflect business and security boundaries. Never use a consumer credential with permission to read the entire registry if the consumer only needs two services.

An application-layer allowlist prevents unintended queries. Namespaces or ACLs at the registry/platform layer also reduce visible data and limit blast radius if credentials are leaked. Combining both layers is generally safer.

## 10. Cache, Refresh, and Data Freshness

Caching helps reduce repeated queries, but discovery data can become stale when instances change.

Cache layers that may exist:

- Registry server cache or response cache.
- Client registry cache, e.g., Eureka client registry snapshot.
- Discovery integration cache or watch state.
- Spring Cloud LoadBalancer instance list cache.
- DNS cache in the JVM, OS, or resolver.
- Application-created custom caches.

Do not add multiple custom cache layers without understanding TTLs and invalidation. If TTLs are too long, consumers may keep calling removed instances. If TTLs are too short, the registry is queried frequently and load increases.

A practical guideline:

1. Identify which caches already exist in the provider/client.
2. Measure instance change frequency and required convergence time.
3. Choose TTL/refresh intervals matching that requirement.
4. Use watches/events if the provider supports them and the integration implements them properly.
5. Handle cache misses or temporary registry unavailability.
6. Do not call full-catalog enumeration to force a cache refresh on every request.

A cache is not an authoritative data source. The registry manages registrations; the cache is only a copy for fast lookups.

## 11. Organizing Explicit Dependencies Instead of Discovering Every Service

An application should know in advance which services it needs to call. For example:

```yaml
app:
  dependencies:
    inventory-service: true
    pricing-service: true
    payment-service: false
```

This is an illustrative business configuration example, not a standard Spring Cloud property. Its purpose is to demonstrate an application-layer dependency allowlist.

Clients can be declared explicitly:

```java
@FeignClient(name = "inventory-service")
public interface InventoryClient {
    // ...
}

@FeignClient(name = "pricing-service")
public interface PricingClient {
    // ...
}
```

This approach helps:

- Know in advance which dependencies are required.
- Check readiness of specific critical services if the business requires it.
- Attach timeouts, retries, and circuit breakers per client.
- Restrict registry read permissions.
- Prevent service discovery from becoming an arbitrary service directory for every feature.

If a dashboard needs to list the catalog, build a dedicated administrative feature with caching, pagination/filtering if supported by the API, clear access controls, and a reasonable polling interval. Do not place that work on the business request path.

## 12. Security When Scoping Discovery

Restricting queries is also a way to reduce information exposure. Service names, topology, hosts, ports, and metadata can reveal system architecture.

Measures to apply:

- Use ACLs/tokens so consumers only read necessary services/namespaces.
- Use Kubernetes RBAC to restrict namespaces and resources.
- Use ZooKeeper ACLs to restrict roots/paths.
- Do not grant catalog-wide permissions to applications that do not need enumeration.
- Do not put tokens, passwords, or sensitive data into metadata.
- Separate provider, consumer, and operator credentials.
- Audit anomalous catalog-wide queries.
- Protect dashboard/admin endpoints because they often hold broad visibility permissions.

Client-side scope restriction does not replace server-side authorization. An application may be programmed to call only one service while its token still grants permission to read the entire catalog. If credentials are leaked, broad permissions still increase damage.

## 13. Measuring Cost and Validating Scope Restrictions

Before and after making changes, measure the appropriate metrics:

| Metric | What to Observe |
|---|---|
| Catalog response size | Payload size when fetching the full catalog |
| Discovery lookup latency | Duration of `getInstances(serviceId)` |
| Registry API request rate | Requests to the registry per client |
| Client heap | Memory used for registry snapshots and instance objects |
| CPU/GC | Parsing, filtering, and refresh costs |
| Cache hit/miss | Ratio of lookups served from cached data |
| Refresh lag | Delay from registration change to consumer visibility |
| Empty instance result | Frequency of lookups returning no instances |
| Registry error rate | Timeouts, 401/403, 5xx, or session errors |

You can use Micrometer, application metrics, registry metrics, and profilers to collect data. Avoid tagging metrics with every instance ID or URL because high cardinality can overload the monitoring system. Use service IDs or controlled service groups, and keep label counts bounded.

A simple experiment:

1. Record the current number of services and instances.
2. Measure time, payload, and heap when enumerating the catalog.
3. Measure lookups for a specific service ID.
4. Repeat the experiment with increasing service/instance counts.
5. Compare registry request rate and refresh lag.
6. Verify whether data remains fresh enough for operational requirements.

Do not use a local benchmark with a few services to extrapolate production capacity. Real-world load depends on client count, replica count, registry change rate, and caching mechanisms.

## 14. Troubleshooting

| Symptom | Possible Cause | Remediation |
|---|---|---|
| Slow startup with discovery enabled | Client syncing a large catalog or slow registry response | Measure fetch latency, payload, cache, and scope |
| CPU/heap increases with large catalog | Deserializing and retaining many services/instances | Reduce enumeration, check caches and provider scope |
| Registry receives too many requests | Dashboards or apps polling the full catalog frequently | Increase intervals, cache results, query by service |
| Eureka consumer uses high heap | Large client-side registry snapshot | Measure snapshot size, instance count, refresh interval, and discovery needs |
| Consul query returns too many results | Using catalog-wide endpoint instead of health/service | Use per-service API and appropriate filters |
| ZooKeeper reads many znodes | Traversing full root instead of service branch | Use `DiscoveryClient` and restrict root/ACLs |
| Kubernetes API load increases | Discovery watching/listing across many namespaces | Restrict namespaces and RBAC |
| Consumers see stale instances | Cache TTL/refresh or watch propagation | Check each cache layer and convergence time |
| Service not found after scoping | Namespace/path/ACL allowlist missing required service | Cross-check service ID, namespace, and read permissions |

When troubleshooting, identify whether the cost lies in the registry server, client sync, application enumeration, or LoadBalancer cache. Increasing timeouts or disabling discovery does not address the root cause if the application is simply reading too broadly.

## 15. Discovery Scope Design Checklist

1. Does the consumer genuinely need the full list of services?
2. Can `getInstances(serviceId)` be used instead of `getServices()`?
3. Is there an explicit dependency allowlist for each application?
4. Does the Eureka client need to fetch the registry, and is the current fetch interval appropriate?
5. Can Consul use the health/service API or filters instead of catalog-wide queries?
6. Can the ZooKeeper client read a service branch instead of the entire root?
7. Can Kubernetes discovery restrict namespaces and RBAC?
8. At which layers do caches currently exist, and what are their TTLs?
9. Does convergence latency meet rollout and failover requirements?
10. Do credentials have broader read permissions than actually needed?
11. Do catalog-wide dashboards have caching and a reasonable polling interval?
12. Do metrics avoid high cardinality by instance ID/URL?
13. Have payload size, latency, heap, CPU, and registry request rates been measured at expected scale?

Discovery overhead rises when clients read and process more data than actually needed. Using per-service ID queries, namespace/path restrictions, ACL/RBAC permissions, TTL-bounded caches, and dependency allowlists reduces load and narrows visible information. However, understand the limits of each provider: in particular, Eureka may still sync a broad registry snapshot in the background even if the application only looks up one service. Measure costs across the registry, client, and request path before tuning configuration.
