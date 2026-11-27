# Distinguishing Consul Catalog API, Health API, and DNS

Consul provides multiple ways to locate a registered service, each answering a different question. The **Catalog API** reports which services and instances are registered. The **Health API** adds health check statuses to determine which instances are passing, warning, or critical. The **DNS interface** turns service information into A or SRV records so applications can resolve names without calling the HTTP API directly.

Choosing the wrong interface can cause consumers to receive unhealthy instances, miss port information, or mistakenly believe a service has disappeared. This lesson distinguishes the data, endpoints, filtering behavior, and limitations of each interface, and explains how Spring Cloud Consul uses the HTTP API.

## 1. Three Interfaces, Three Purposes

Suppose Consul stores three instances of `inventory-service`:

| Instance | Endpoint | Health |
|---|---|---|
| inventory-a | 10.0.1.11:8081 | passing |
| inventory-b | 10.0.1.12:8081 | warning |
| inventory-c | 10.0.1.13:8081 | critical |

The three interfaces present different views of the same underlying data:

| Interface | Primary Question | Returned Data | Health Filtering |
|---|---|---|---|
| Catalog API | Which services/instances are registered? | Service name, node, address, port, tags, metadata | Does not filter by health checks |
| Health API | What state are the service instances and their checks in? | Node, Service, Checks, check statuses | Can request only passing instances |
| DNS | Which addresses does a service name resolve to? | A or SRV records | Filters by DNS config, which may differ from Health API |

Do not treat the three interfaces as interchangeable calls. Catalog is the registration view; Health is the status view; DNS is a name-and-address resolution interface for clients.

## 2. Catalog API: Querying Registration Data

The Catalog is Consul's central registry. It tracks nodes, services, addresses, ports, tags, metadata, and details Consul needs for discovery and service mesh.

Commonly used endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /v1/catalog/services` | List registered service names and tags in the datacenter |
| `GET /v1/catalog/service/:service_name` | List nodes and registrations providing a service |
| `GET /v1/catalog/node/:node_name` | Inspect node details and services registered on the node |
| `GET /v1/catalog/nodes` | List nodes in the catalog |

### 2.1. Listing Services

Example:

~~~bash
curl http://127.0.0.1:8500/v1/catalog/services
~~~

Illustrative response:

~~~json
{
  "consul": [],
  "inventory-service": ["v1", "warehouse"],
  "order-service": ["v2"]
}
~~~

Each key is a service name; the value is that service's tag list. This endpoint is useful for checking which services have been published, but it does not indicate which instances are healthy.

### 2.2. Listing Registered Instances

Example:

~~~bash
curl http://127.0.0.1:8500/v1/catalog/service/inventory-service
~~~

Abbreviated illustrative response:

~~~json
[
  {
    "Node": "node-a",
    "Address": "10.0.1.11",
    "ServiceID": "inventory-a",
    "ServiceName": "inventory-service",
    "ServiceAddress": "10.0.1.11",
    "ServicePort": 8081,
    "ServiceTags": ["v1"],
    "ServiceMeta": {
      "zone": "zone-a"
    }
  },
  {
    "Node": "node-b",
    "Address": "10.0.1.12",
    "ServiceID": "inventory-b",
    "ServiceName": "inventory-service",
    "ServiceAddress": "10.0.1.12",
    "ServicePort": 8081,
    "ServiceTags": ["warehouse"],
    "ServiceMeta": {
      "zone": "zone-b"
    }
  }
]
~~~

The Catalog API lets you inspect registered endpoints and their metadata. It does not exclude instances by default simply because a health check is warning or critical. Therefore, if a consumer uses the catalog service list to select endpoints, it must query and evaluate health separately.

### 2.3. Catalog API Is Not the Health API

An instance appearing in the Catalog proves only that the registration exists in the catalog. It does not prove the endpoint is ready to serve traffic.

Consul intentionally separates `/catalog` and `/health`: some deployments look up registrations without enabling or depending on health checking. The Health API is the dedicated interface for querying check-related information.

The Catalog also exposes write endpoints such as `/v1/catalog/register` and `/v1/catalog/deregister`. These are low-level mechanisms. Consul documentation generally recommends using the Agent API to register services and health checks because the agent manages anti-entropy and synchronization with the catalog. In particular, writing a check entry via the Catalog does not automatically create an HTTP, TCP, or TTL probe against the node; actual check definitions must be created through the agent or agent configuration.

## 3. Health API: Querying Instances Together With Health Checks

The Health API returns registration data along with associated checks. The most important endpoint when locating instances of a service is:

~~~text
GET /v1/health/service/:service
~~~

Example:

~~~bash
curl http://127.0.0.1:8500/v1/health/service/inventory-service
~~~

The response typically contains three parts:

- `Node`: details of the node running the instance.
- `Service`: service registration details such as ID, name, address, port, tags, and metadata.
- `Checks`: node-level or service-level checks associated with the query result.

Abbreviated response example:

~~~json
[
  {
    "Node": {
      "Node": "node-a",
      "Address": "10.0.1.11"
    },
    "Service": {
      "ID": "inventory-a",
      "Service": "inventory-service",
      "Address": "10.0.1.11",
      "Port": 8081,
      "Tags": ["v1"]
    },
    "Checks": [
      {
        "CheckID": "service:inventory-a",
        "Name": "Inventory HTTP check",
        "Status": "passing"
      }
    ]
  }
]
~~~

Unlike the Catalog API, the Health API lets consumers see why an instance is considered healthy or unhealthy.

### 3.1. The passing Parameter

By default, `/v1/health/service/:service` does not restrict results to passing instances. You can add the `passing` query parameter:

~~~bash
curl "http://127.0.0.1:8500/v1/health/service/inventory-service?passing"
~~~

When `passing` is true, Consul returns only nodes where all health checks are in the `passing` state. An instance with a `warning` or `critical` check is omitted from this result.

| Query Value | Behavior |
|---|---|
| `passing` omitted or `passing=false` | Returns matching instances along with their checks and statuses |
| `passing=true` | Returns only nodes where all checks are passing |

This is an important distinction when building consumers. If the requirement is to route requests only to instances passing every check, use `passing=true` or enforce equivalent client-side filtering.

### 3.2. Other Useful Health API Endpoints

| Endpoint | Used For |
|---|---|
| `GET /v1/health/checks/:service` | View checks attached to a service |
| `GET /v1/health/node/:node` | View checks on a node |
| `GET /v1/health/state/:state` | List checks by status such as passing, warning, or critical |
| `GET /v1/health/service/:service` | Retrieve service instances along with checks |

When an instance disappears from a `passing=true` query, call the unfiltered endpoint or `/v1/health/checks/:service` to find which check is warning or critical. Do not conclude an instance was deregistered solely from an empty passing query result.

### 3.3. Node-Level and Service-Level Health Checks

An instance can be affected by multiple checks:

- Node-level checks assess the machine or agent condition. If a node is critical, services on that node can also be treated as unhealthy.
- Service-level checks assess the specific endpoint or process providing the service.
- A single service can have multiple checks; `passing=true` requires all relevant checks to pass.

Consequently, an application HTTP check returning passing may not be enough if the node has another critical check. When diagnosing, read the full `Checks` array in the response rather than inspecting only one service check.

## 4. DNS Interface: Resolving Services to Addresses

Consul DNS enables applications to query services by domain name without calling the HTTP API or integrating a Consul SDK directly.

By default, Consul DNS uses the `consul` domain and typically listens on agent port `8600`. Example service name:

~~~text
inventory-service.service.consul
~~~

For clients to use this name, the host or environment DNS resolver must forward `.consul` domain queries to an appropriate Consul agent. Not every host automatically knows how to resolve `.consul` names.

### 4.1. A Records

An A query retrieves IPv4 addresses of instances returned by DNS:

~~~bash
dig @127.0.0.1 -p 8600 inventory-service.service.consul A
~~~

Abbreviated response:

~~~text
inventory-service.service.consul. 0 IN A 10.0.1.11
inventory-service.service.consul. 0 IN A 10.0.1.12
~~~

A records provide IP addresses without service ports. The application must know the port via configuration or use another mechanism to obtain the port.

### 4.2. SRV Records

SRV records provide both the target hostname and registered port:

~~~bash
dig @127.0.0.1 -p 8600 inventory-service.service.consul SRV
~~~

Illustrative response:

~~~text
inventory-service.service.consul. 0 IN SRV 1 1 8081 node-a.node.dc1.consul.
inventory-service.service.consul. 0 IN SRV 1 1 8081 node-b.node.dc1.consul.
~~~

SRV is appropriate when the client needs both target address and port. However, the application's resolver library must support SRV queries; many standard HTTP clients only resolve A/AAAA records for hostnames and do not consume SRV records automatically.

### 4.3. Querying by Tag

You can include a tag in the query name to scope the service group, for example:

~~~bash
dig @127.0.0.1 -p 8600 v1.inventory-service.service.consul SRV
~~~

This is useful when one service name has multiple tags such as `v1`, `v2`, `blue`, or `warehouse`. The tag must be registered properly and the query name must follow Consul DNS syntax.

DNS also supports node, datacenter, and prepared query lookups using dedicated syntax. For complex filtering requirements or detailed metadata access, the Health API or prepared queries are generally a better fit.

## 5. DNS Health Filtering Differs From Health API

Do not assume DNS and the Health API share identical filtering policies.

The Health API uses the `passing=true` query parameter to return only nodes with all checks passing. DNS uses the agent-level `only_passing` configuration:

| Interface | Filter Configuration | Behavior |
|---|---|---|
| Health API | Query `?passing` | Returns only instances with all checks passing |
| Consul DNS | `dns_config.only_passing = false` (default) | Excludes nodes with critical checks; warning nodes may still appear |
| Consul DNS | `dns_config.only_passing = true` | Returns only nodes with passing checks; excludes both warning and critical |

Example agent configuration:

~~~hcl
dns_config {
  only_passing = true
}
~~~

If DNS keeps the default `only_passing=false`, a warning instance can still be resolved. If applications must call only fully passing instances, enable this setting or use the Health API with `passing=true`.

Check the filtering policy on the exact agent answering the query. Two environments with different DNS configurations can return different address sets even when looking at the same catalog.

## 6. Comparing Data and Capabilities of the Three Interfaces

| Criterion | Catalog API | Health API | DNS |
|---|---|---|---|
| Service list | Yes | Not primary purpose | Queries per name |
| Instance endpoint | Yes | Yes | Address via A; also port via SRV |
| Tags | Yes | Yes | Queryable by tag |
| Full metadata | Yes | Yes in service registration | Does not return arbitrary metadata like HTTP API |
| Detailed health checks | No | Yes | No |
| Passing-only filter | Not a health filter | Supports `passing=true` | Supports `only_passing` |
| Protocol | HTTP API | HTTP API | DNS |
| SDK or HTTP client dependency | Yes | Yes | Requires DNS resolver |
| Fit for legacy apps | Requires API integration | Requires API integration | Often easier if app already uses DNS |
| Inspection/diagnostics | Inspect registration | Inspect health status and reasons | Verify name resolves to endpoints |

How to choose:

- Use the Catalog API when inspecting inventory, service names, tags, metadata, or registrations.
- Use the Health API when applications make decisions based on check status, need passing filtering, or need diagnostics on why an instance is unhealthy.
- Use DNS when an application only needs name-to-address resolution and can accept the limitations of DNS, resolvers, and caching.

## 7. Which Interface Does Spring Cloud Consul Use?

Spring Cloud Consul Service Discovery uses the **Consul HTTP API** for registration and discovery. It does not use Consul DNS by default to implement `DiscoveryClient`.

When an application uses `spring-cloud-starter-consul-discovery`:

1. Auto-configuration creates the Consul client and discovery integration.
2. The application registers its service with Consul per configuration.
3. Spring Cloud Consul queries the API to discover instances.
4. `ConsulDiscoveryClient` maps results into Spring Cloud Commons `ServiceInstance` objects.
5. Spring Cloud LoadBalancer can use that instance list to select endpoints.

Therefore, when debugging Spring Cloud Consul, inspect the HTTP API and discovery client configuration. A service name resolving over DNS does not prove the application's `DiscoveryClient` returns the same list.

### 7.1. The query-passing Property

Spring Cloud Consul provides the property:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        query-passing: true
~~~

When `query-passing` is enabled, Spring Cloud Consul appends the `passing` parameter to `/v1/health/service/:service` queries. Consul then returns only instances where all health checks are passing.

Per current property documentation, `spring.cloud.consul.discovery.query-passing` defaults to `false`. At the default setting, Spring Cloud Consul may receive warning or critical instances in the Health API response and return them to the application depending on processing logic. If only passing instances should be used, enable this property and verify behavior on your exact release train.

This property controls Spring Cloud Consul's Health API queries; it does not alter the DNS agent's `only_passing` setting.

### 7.2. Health Check Configuration During Registration

Spring Cloud Consul typically registers an HTTP health check pointing to `/actuator/health`. Adjustable properties include:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        register-health-check: true
        health-check-path: /actuator/health
        health-check-interval: 15s
        query-passing: true
~~~

Verify exact property names and options against the Spring Cloud Consul version in use. If the application has a custom context path, servlet path, or separate management port, the health check path and address must match the actual endpoint.

`register-health-check` controls registering the health check with Consul; `query-passing` controls how consumers query instances. These two properties serve different purposes.

## 8. Caching, TTL, and Stale Data

The three interfaces exhibit different caching behaviors.

### 8.1. Catalog and Health APIs

The Catalog and Health APIs support blocking queries so clients wait for data changes instead of polling continuously. Some endpoints also support agent caching with background refresh. Consumers can use indices and `X-Consul-Index` to continue querying from the latest change via blocking queries.

Avoid sending continuous high-frequency polling requests when blocking queries or appropriate caching can be used. Handle timeouts and indices according to the API documentation.

### 8.2. DNS TTL

By default, Consul DNS returns a TTL of 0, discouraging resolvers from caching answers. A TTL can be configured for service lookups to reduce query volume and load on Consul.

A longer TTL reduces queries but increases the risk of clients holding stale addresses after instances change. A shorter TTL speeds up updates at the cost of higher query volume.

Beyond positive TTLs, watch out for **negative caching**: some operating systems and DNS forwarders cache not-found responses. When a service just re-registered, clients may still see resolution failures until the negative cache expires.

### 8.3. DNS Is Not a Full Load Balancer

Consul DNS can return multiple A or SRV records and shuffle their order to distribute selection. However, DNS does not control individual requests:

- Resolvers or applications may stick to a single address.
- Clients may cache results and reuse persistent connections.
- Some libraries do not support SRV records.
- DNS does not expose full metadata or health details for business routing logic.
- Right after an endpoint fails, caching and refresh intervals may cause clients to keep using the stale address.

When instance selection must factor in zones, metadata, tags, health, or sophisticated retry policies, using the Health API via a discovery client and load balancer is a better fit.

## 9. Security and Access Control

Both the Catalog API and Health API are governed by Consul ACLs. Tokens must grant appropriate service and node read permissions; if results are filtered by ACLs, responses can omit partial data without necessarily surfacing as a standard HTTP error.

Key principles:

- Grant `service:read` and `node:read` permissions strictly as needed.
- Store tokens in a secrets store or secure configuration management system.
- Never place tokens in URL query strings or logs.
- Restrict network access to the HTTP API and DNS agent.
- Protect registration and deregistration endpoints so unauthorized workloads cannot spoof services.
- Never store credentials or secrets inside service metadata or tags.

DNS usually exposes less information than the HTTP API, yet internal name resolution can still leak topology. Restrict which networks can query DNS and design ACLs appropriate for your environment.

## 10. API Selection Workflow When Troubleshooting

When `inventory-service` cannot be found by a consumer, inspect in this order:

1. **Catalog:** call `/v1/catalog/services` to confirm the service name exists.
2. **Catalog instance:** call `/v1/catalog/service/inventory-service` to view registrations, host, port, and metadata.
3. **Health:** call `/v1/health/service/inventory-service` to read each instance's checks.
4. **Passing filter:** append `?passing` to verify whether any instance passes all checks.
5. **DNS:** use `dig` to query A and SRV records from the Consul agent to inspect the DNS view.
6. **Spring Cloud:** if the consumer uses DiscoveryClient, inspect `query-passing`, the Health API endpoint, and the actual `ServiceInstance` list.
7. **Network:** test connectivity directly from the consumer's network to the returned endpoint.

Example interpretation table:

| Result | Possible Interpretation |
|---|---|
| Service missing from Catalog | Registration does not exist yet, wrong datacenter/namespace, or ACL filtered out results |
| Catalog has instance, Health shows critical | Registration exists, but health check is failing |
| Health API has instance, `passing` returns empty | No instance has all checks passing |
| Health API passing has instance, yet DNS returns nothing | DNS policy, datacenter, domain, or different agent view |
| DNS resolves address, yet HTTP request fails | Issue with port, network, TLS, or application |
| DNS resolves, yet Spring DiscoveryClient has no instances | Spring Cloud Consul uses HTTP API; check `query-passing`, ACLs, and client config |

Do not rely solely on the Consul dashboard. Query the exact service name, datacenter, and namespace from the specific agent/consumer experiencing the issue to avoid comparing two different views.

## 11. Summary Example

Suppose Consul holds three instances of `inventory-service`:

- `inventory-a`: passing.
- `inventory-b`: warning.
- `inventory-c`: critical.

Different queries yield different results:

| Query | Illustrative Result |
|---|---|
| `GET /v1/catalog/service/inventory-service` | Includes all three registrations |
| `GET /v1/health/service/inventory-service` | Includes all three registrations with checks |
| `GET /v1/health/service/inventory-service?passing` | Only inventory-a |
| DNS with `only_passing=false` | May return inventory-a and inventory-b; excludes inventory-c |
| DNS with `only_passing=true` | Returns only inventory-a |
| Spring Cloud Consul `query-passing=false` | Does not ask server to filter passing; app may receive warning/critical |
| Spring Cloud Consul `query-passing=true` | Requests Health API to return only passing instances |

This example demonstrates that the same catalog can produce different result sets depending on the interface and filtering policy. Therefore, when implementing consumers, explicitly select the required health threshold instead of assuming every interface excludes the same instances.

## 12. Takeaways

- The Catalog API returns registration data; it does not filter instances by health check automatically.
- The Health API returns service instances alongside checks; `passing=true` returns only nodes where all checks pass.
- Consul DNS resolves service names into A or SRV records; SRV includes port, whereas A provides only IP addresses.
- DNS uses `only_passing`; default false may still return warning instances, whereas true keeps only passing instances.
- Spring Cloud Consul uses the HTTP API for registration and discovery, not DNS by default.
- `spring.cloud.consul.discovery.query-passing` defaults to false; set it to true to request Health API filtering for passing instances.
- DNS TTL defaults to 0, though resolvers may negative-cache not-found results.
- When debugging, compare Catalog, Health, DNS, and DiscoveryClient results from the same datacenter/namespace.

Catalog, Health, and DNS are three complementary views of Consul service discovery. Understanding the data and filtering policies of each interface helps consumers select the right instances and helps operators pinpoint whether an issue stems from registration, health checks, DNS resolvers, or Spring Cloud configuration.

## References

- [Consul Catalog HTTP API](https://developer.hashicorp.com/consul/api-docs/catalog)
- [Consul Health HTTP API](https://developer.hashicorp.com/consul/api-docs/health)
- [Consul DNS overview](https://developer.hashicorp.com/consul/docs/discover/dns)
- [Consul DNS static queries](https://developer.hashicorp.com/consul/docs/discover/service/static)
- [Consul DNS configuration and TTL](https://developer.hashicorp.com/consul/docs/discover/dns/configure)
- [Spring Cloud Consul Service Discovery](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Consul configuration properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)
