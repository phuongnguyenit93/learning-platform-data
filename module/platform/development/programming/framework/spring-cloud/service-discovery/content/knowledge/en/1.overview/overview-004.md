# End-to-End Flow from Registration to Discovery and Service Invocation

In a microservice system, a service can run as multiple instances across different machines or containers. The address of each instance can change during deployment, scaling, or restarts. Consumers therefore need to locate services by logical name rather than depending on IP addresses and ports hardcoded in source code.

**Service discovery in Spring Cloud** connects the steps of registering instances, storing information in a registry, checking serving status, querying the instance list, and selecting a destination for each request. Abstractions such as ServiceRegistry and DiscoveryClient help applications work with discovery; Eureka and Consul provide registry backends; Spring Cloud LoadBalancer assists with selecting an instance when calling a service.

This article presents the complete lifecycle from when a provider starts up to when a consumer sends a request, and then tracks the changes when instances become healthy, fail, scale, or stop. This is the foundational flow of Spring Cloud Service Discovery, covering registration, health checks, load balancing, security, and handling registry data staleness in a microservice environment.

## 1. Participating Components

Before following the flow, it helps to distinguish the role of each component:

| Component | Role | Example |
|---|---|---|
| Provider | Application providing an API or business capability | `inventory-service` |
| Provider instance | A specific running process of a provider | `10.0.1.12:8081` |
| Service registry | Stores service information and registered instances | Eureka Server, Consul catalog |
| ServiceRegistry | Spring Cloud abstraction to register, update, or deregister instances | Eureka or Consul implementation |
| DiscoveryClient | Abstraction to query service IDs and corresponding instances | `getServices()`, `getInstances()` |
| Consumer | Application that needs to call a provider | `order-service` |
| Health check | Mechanism to evaluate whether an instance meets serving conditions | HTTP health endpoint, heartbeat/lease |
| Load balancer | Selects an instance from the list of serviceable instances | Spring Cloud LoadBalancer |
| HTTP client | Sends requests to the selected endpoint | RestTemplate, WebClient, RestClient |

A **service ID** represents a logical service, such as `inventory-service`. One service ID can correspond to multiple instances. The registry stores per-instance information such as host, port, scheme, ID, and metadata depending on the backend.

Crucially, the abstractions have distinct responsibilities:

- `ServiceRegistry` belongs to the service-publishing side: the provider registers instance information and updates its status.
- `DiscoveryClient` belongs to the lookup side: the consumer queries the registry to learn which services and instances are currently published.
- `LoadBalancer` chooses an instance to serve a single call. It typically uses the instance list obtained via the discovery client.

## 2. Flow Diagram from Provider to Consumer

The overall flow can be visualized as follows:

~~~mermaid
flowchart TD
    P["Provider starts"] --> C["Read service ID, host, port, and metadata"]
    C --> SR["ServiceRegistry / Discovery adapter"]
    SR --> R[("Service Registry")]
    R --> H["Heartbeat or health check"]
    H --> S["Update instance status"]
    U["Consumer receives business request"] --> D["DiscoveryClient"]
    D --> R
    D --> I["ServiceInstance list"]
    I --> L["Spring Cloud LoadBalancer"]
    L --> E["Select an endpoint"]
    E --> HC["HTTP client sends request"]
    HC --> P2["Provider instance processes"]
    P2 --> RES["Response to consumer"]
    P2 -. "Stop / deregister" .-> SR
~~~

The flow can be divided into three phases:

1. **Service publication:** the provider builds instance information and registers with the registry.
2. **Status maintenance:** the registry receives heartbeats or executes health checks; instance status changes with the application lifecycle.
3. **Service lookup and invocation:** the consumer queries instances, the load balancer chooses an endpoint, and the HTTP client sends the request.

Specific steps differ between Eureka and Consul. The diagram describes the general contract and concept; the backend decides how registration, health checking, storage, and data updates work.

## 3. Phase 1: Provider Starts Up and Registers an Instance

Suppose the system has an inventory management service named `inventory-service`. When running an instance, the application needs to publish at least enough information for consumers to locate it:

- Service ID: `inventory-service`.
- Host or network address reachable by consumers.
- Port on which the application is listening.
- Scheme or secure connection information, if any.
- Instance ID to distinguish running copies of the same service.
- Metadata needed for routing or operations.

In Spring Boot, `spring.application.name` is typically used as the default service ID. Baseline configuration example:

~~~yaml
spring:
  application:
    name: inventory-service

server:
  port: 8081
~~~

If two instances run with this service name configuration, both publish the service ID `inventory-service`, but each must have an endpoint and instance identifier appropriate to its own running copy.

### 3.1. Registering via ServiceRegistry

Spring Cloud Commons defines the `ServiceRegistry` abstraction for registration operations. The provider or discovery integration uses a registration object containing instance information to send to the registry.

Conceptually, the sequence is:

1. Spring Boot creates the application context and initializes the discovery integration.
2. The integration determines the service ID, host, port, instance ID, and metadata.
3. The implementation builds registration details appropriate for the backend.
4. The instance is sent to the registry or the agent managing the registry.
5. The provider begins maintaining its registration status according to the backend mechanism.

Providers usually do not have to write HTTP calls to Eureka or Consul manually. Spring Cloud starters and auto-configuration provide the necessary beans and lifecycle hooks when discovery configuration is enabled.

`ServiceRegistry` is a generic registration abstraction. Backends may have different registration representations and status rules. Therefore, you should not assume all backends share the same payload, heartbeat, or deregistration behavior.

### 3.2. Provider Example Using Eureka

An application using Eureka Client can declare its name and Eureka Server address in configuration:

~~~yaml
spring:
  application:
    name: inventory-service

server:
  port: 8081

eureka:
  client:
    serviceUrl:
      defaultZone: http://localhost:8761/eureka/
  instance:
    preferIpAddress: true
~~~

For this configuration to work, the application needs a Eureka Client dependency compatible with the Spring Boot and Spring Cloud release train in use. `preferIpAddress` affects the address the client publishes where applicable; make sure that address is reachable by consumers across the deployment network.

On startup, Eureka Client registers the instance with Eureka Server and periodically renews its lease via heartbeats. Eureka Server relies on lease status and its own rules to manage instance information. This is Eureka's registration maintenance mechanism, not the default behavior of every registry.

### 3.3. Provider Example Using Consul

With Consul, applications typically connect to a Consul Agent. The agent receives the service registration and places the information into Consul's catalog. An illustrative configuration:

~~~yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      host: localhost
      port: 8500
      discovery:
        service-name: inventory-service
~~~

This example illustrates the connection properties and service name. Options for health checks, instance ID, tags, and automatic registration must be configured according to the topology and Spring Cloud Consul version in use.

Consul supports registration through an agent and health checking via multiple check types. The agent and catalog coordinate so consumers can query services along with their corresponding health status.

## 4. Phase 2: Registry Maintains Status and Health Checks

Successful registration only indicates that the registry has received the instance information. An instance can fail afterward, so the system needs mechanisms to detect and remove or mark instances that are no longer serving.

There are two related but not identical concepts:

- **Heartbeat or lease:** the client periodically confirms that the instance is still maintaining its registration. If the deadline expires, the registry can treat the registration as expired according to policy.
- **Health check:** a component performs a status check, such as calling an HTTP health endpoint or performing a TCP check. The result can determine whether the instance is considered healthy.

Eureka typically relies on client heartbeats and leases; it can integrate application health status depending on configuration. Consul can run health checks registered by the service, such as HTTP, TCP, or scripts depending on the environment. Backends differ in how they evaluate and publish status.

### 4.1. Application Health Endpoint

Spring Boot Actuator provides a health endpoint when the application adds the Actuator dependency and configures appropriate exposure. For example:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
~~~

A health endpoint should only expose information appropriate for authorized callers. If the registry or agent needs to call this endpoint, make sure the path, port, protocol, and access permissions match the health check configuration.

Health checks can include:

- Liveness: whether the process is still alive to keep running.
- Readiness: whether the instance is ready to accept business traffic.
- Dependency health: whether critical dependencies such as databases or message brokers are responding.

You should not lump every check into a single endpoint without considering its meaning. If a secondary dependency temporarily fails while the service can still handle part of its requests, the readiness policy should reflect the application's actual requirements.

### 4.2. What Happens When an Instance Is Unhealthy?

A common handling flow:

1. A health check fails or the heartbeat/lease is no longer renewed.
2. The backend updates the registration status according to policy.
3. The instance may be marked unhealthy, excluded from query results, or removed after a waiting period.
4. The discovery client or load balancer updates its instance list on a refresh/cache cycle.
5. New requests should no longer be distributed to an instance removed from the serviceable set.

Not every backend removes an instance immediately after a single failed health check. Thresholds, timeouts, intervals, deregistration delays, and caching can all shift when the new status takes effect.

## 5. Phase 3: Consumer Looks Up Service by Name

The consumer does not need to know the IP and port of each provider instance. It only needs to know the logical service ID, such as `inventory-service`.

In Spring Cloud Commons, `DiscoveryClient` provides two basic query operations:

~~~java
List<String> getServices();

List<ServiceInstance> getInstances(String serviceId);
~~~

- `getServices()` returns the service IDs visible to the discovery client.
- `getInstances(serviceId)` returns the list of `ServiceInstance` objects for the requested service ID.

`ServiceInstance` typically provides the service ID, host, port, URI, secure flag, metadata, and instance ID depending on the implementation. A consumer can inject DiscoveryClient to query:

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class InventoryDiscovery {

    private final DiscoveryClient discoveryClient;

    public InventoryDiscovery(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInventoryInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
~~~

If the returned list is empty, the consumer has not found any published instance for that service ID at the time of the query. The application must handle this situation per business requirements, such as returning a service unavailable error or applying bounded retries where appropriate.

DiscoveryClient is a query API. It does not register providers itself, does not guarantee the endpoint is alive at request time, and does not automatically load-balance every HTTP client.

### 5.1. Path of a Query

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant D as DiscoveryClient
    participant R as Registry
    participant I as ServiceInstance list
    C->>D: getInstances("inventory-service")
    D->>R: Query instances
    R-->>D: Registrations visible to client
    D-->>C: List<ServiceInstance>
~~~

Depending on the backend, the discovery client may read data from the registry directly, through an agent, or from cached data. Thus, query results represent the client's current view under its data synchronization mechanism, not an instantaneous absolute snapshot of every process on the network.

## 6. Phase 4: Load Balancer Selects an Instance

If a service has multiple instances, the consumer needs to decide which running copy to send the request to. Spring Cloud LoadBalancer provides instance selection based on the service ID and the discovery list.

Typical flow:

1. The consumer sends a request to a logical service name, such as `http://inventory-service/api/items`.
2. An HTTP client integrated with load balancing recognizes this as a service ID rather than a normal DNS hostname.
3. The load balancer requests the instance list through the discovery integration.
4. The load balancer picks an instance according to the current algorithm and configuration.
5. The HTTP client sends the request to the URI of the selected instance.

Example configuring a `RestTemplate` with load-balancing integration:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate restTemplate() {
        return new RestTemplate();
    }
}
~~~

Consumer calls by service ID:

~~~java
ItemResponse[] items = restTemplate.getForObject(
        "http://inventory-service/api/items",
        ItemResponse[].class
);
~~~

For this code to work, the application needs a compatible Spring Cloud LoadBalancer dependency and a configured DiscoveryClient implementation. Depending on the Spring Boot version and HTTP client type, the corresponding integration for WebClient or RestClient can be used.

You should avoid calling `getInstances()` and always picking the first element in business code. List order is not a load-balancing guarantee; the list may be empty, it may change, and the first instance is not necessarily the most suitable. Let the load balancer manage instance selection and apply appropriate timeout, retry, or circuit breaker policies.

### 6.1. Discovery and Load Balancing Are Two Different Steps

| Discovery | Load Balancing |
|---|---|
| Finds instances belonging to a service ID | Selects one instance for a specific request |
| Returns instance information | Uses instance information to route the request |
| Works with the registry or cached discovery data | Works with an instance list and selection policy |
| Example: `getInstances("inventory-service")` | Example: selecting one `ServiceInstance` for a request |

Having an instance list does not mean requests are already load balanced. Conversely, the load balancer needs an instance source, usually DiscoveryClient or a suitable service instance list supplier.

## 7. Phase 5: Provider Receives Request and Returns Response

After the load balancer selects an endpoint, the HTTP client connects to the published host and port. The provider processes the request like a standard HTTP request:

1. The network routes to the instance's endpoint.
2. The provider's web server receives the request.
3. Spring MVC or WebFlux routes to the controller/handler.
4. The service layer executes business logic and accesses required dependencies.
5. The provider returns a response to the consumer.

Service discovery only helps locate the destination. It does not replace caller authentication, business authorization, connection encryption, timeout control, or error handling. A request reaching the right endpoint can still be rejected by a security filter, a business error, or a provider-side dependency.

When using HTTPS, make sure the instance publishes the correct scheme and the consumer trusts the corresponding certificate. If there is a gateway, proxy, or service mesh in between, addresses and connection flows must be designed consistently with that network architecture.

## 8. Phase 6: Scaling, Status Changes, and Deregistration

Service discovery is a live flow over time, not just a one-off lookup operation.

### When Scaling Out

Suppose `inventory-service` scales from two to three instances:

1. The new instance starts up with the same service ID.
2. The new instance registers its endpoint information in the registry.
3. Health checks or registration status indicate the instance is ready per backend policy.
4. The registry publishes the new instance.
5. The discovery client and load balancer update their lists.
6. Subsequent requests can be distributed to the new instance.

Do not let an instance receive traffic before the application is ready. Coordinate readiness status, registration, and health check policies to prevent requests from reaching an initializing instance.

### When Scaling In or Deploying a New Version

When an instance needs to stop:

1. The orchestrator or application issues a shutdown signal.
2. The provider stops accepting new requests or transitions to an unready state.
3. The provider deregisters from the registry if supported by the backend mechanism and shutdown is graceful.
4. The registry updates the instance list.
5. The consumer/load balancer refreshes discovery data.
6. In-flight requests complete within the configured graceful shutdown and connection draining window.

If a process is killed abruptly, the deregistration step may not run. In that case, heartbeats, leases, or health checks detect that the instance has disappeared, though there may be a lag before registry data is updated.

### When an Instance Changes Address

If a container or virtual machine is recreated, its host and port may change. The new instance must publish its new endpoint. Consumers relying on the service ID and refreshed discovery data will find the new address without modifying URLs in business code.

## 9. How Do Eureka and Consul Implement the Flow?

Both Eureka and Consul can provide service discovery for Spring Cloud, though their mechanisms for managing registration and health differ.

| Aspect | Eureka | Consul |
|---|---|---|
| Registry component | Eureka Server | Consul Agent and Consul catalog |
| Registration | Eureka Client registers with the server | Service registers via Consul Agent or integration mechanism |
| Status maintenance | Client renews lease via heartbeat | Agent runs health checks and updates status per configuration |
| Health | Based on lease and health integration configuration | Can use HTTP, TCP, or other checks |
| Querying | Eureka client fetches registry list via client mechanism | Consul discovery queries the catalog and service status |
| Spring Cloud integration | Spring Cloud Netflix Eureka | Spring Cloud Consul |

Operational differences to keep in mind:

- Eureka typically maintains a client-cached view of the registry; changes may not appear to all consumers immediately.
- Consul attaches health checks to service registrations; querying healthy services depends on checks and discovery options.
- Timeout, interval, heartbeat, cache, deregistration, and retry settings must match the actual backend and version deployed.
- Do not infer that an instance appearing in an admin UI will immediately be seen by every consumer at the exact same moment.

Regardless of which backend is used, consumers can still operate through DiscoveryClient and load balancing abstractions when the corresponding integration is properly configured.

## 10. How Can Registry Data Become Stale or Inconsistent?

In a distributed system, providers, the registry, and consumers do not update state at the exact same instant. As a result, there can be a window where each component sees a different state.

For example:

- A provider has stopped, but its lease has not expired or health checks have not finished running in the registry.
- The registry has removed the instance, but the consumer still holds a stale cache.
- An instance is already healthy, but the consumer has not refreshed its list yet.
- A provider registered an incorrect host or port, causing consumers to find the instance but fail to connect.
- Multiple instances share a duplicate identifier, causing registrations to overwrite or delete the wrong record depending on the backend.

### 10.1. Scenarios and Troubleshooting Table

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| Service ID not found | Provider not registered yet, wrong service name, or consumer not connected to registry | Check name configuration, startup logs, and registry connectivity |
| Service name exists but has no instances | Instance not healthy yet, registration failed, or removed from catalog | Check health checks, leases, and registration status |
| Instances exist but calls time out | Wrong host/port, firewall, DNS, or unreachable route | Test the endpoint directly from the consumer's network |
| Stopped instance still appears | Cache or lease/health check has not expired yet | Check refresh intervals, TTL, and deregistration |
| New instance is running but receives no traffic | Not registered yet, not healthy yet, or consumer has not refreshed list | Check readiness and discovery refresh |
| Requests unevenly distributed | Selection policy, caching, request volume, or client configuration | Check load balancer and per-instance metrics |

### 10.2. Strategies to Reduce Staleness

- Set health check intervals, timeouts, and thresholds appropriate for startup time and application characteristics.
- Use readiness so instances only receive traffic when ready.
- Configure graceful shutdown and deregistration during controlled deployments.
- Ensure published host/port is reachable from consumers, even across multiple network segments.
- Understand caching and refresh behavior of the discovery client and load balancer.
- Set request timeouts; only retry with bounds and for appropriate operation types.
- Monitor registrations, health transitions, instance counts, and connection errors per service ID.
- Do not treat the registry list as absolute proof that an endpoint will definitely serve requests successfully.

## 11. Security Across the Entire Discovery Flow

The registry stores the system's topology: service names, instance addresses, ports, metadata, and status. If accessed without authorization, an attacker could harvest the internal map or register fake instances depending on backend permissions.

You need to protect the registration, query, and service invocation flows:

1. **Protect the registry:** restrict network access, enable authentication, and enforce authorization on management APIs.
2. **Protect registration:** allow only authorized workloads to register or modify service state.
3. **Protect metadata:** never store passwords, tokens, or secrets in metadata visible to consumers.
4. **Protect connections:** use TLS where appropriate; manage and rotate certificates/credentials.
5. **Protect health endpoints:** expose access paths only as needed for authorized registries or monitoring.
6. **Protect service APIs:** authentication and authorization are still required on the provider; knowing an instance's address does not grant permission to call its API.

If using Consul ACLs or Eureka and surrounding infrastructure security mechanisms, grant permissions following the principle of least privilege. Provider, consumer, and operator credentials should have separate scopes when supported by the backend.

## 12. Observability and Stage-by-Stage Diagnostics

When a request fails to reach the provider, determine which stage in the flow failed instead of looking only at consumer logs.

| Stage | Signals to Observe | Inspection Source |
|---|---|---|
| Provider startup | Service ID, instance ID, published endpoint | Application logs and runtime configuration |
| Registration | Success/failure, registration timestamp | Provider, registry, or agent logs |
| Health | Healthy/unhealthy, state transition times | Health checks, Actuator, registry |
| Discovery | Visible service IDs and instance lists | DiscoveryClient or registry API |
| Load balancing | Selected instance, selection errors | HTTP client and load balancer logs/metrics |
| Request | Connection, latency, status code, timeout | Consumer/provider logs and metrics |
| Deregistration | Deletion or expiration timestamp of registration | Shutdown logs and registry |

A practical investigation procedure:

1. Confirm the provider is running and the endpoint works directly from the consumer network.
2. Verify the provider registered the right service ID, host, and port.
3. Check health status and the most recent heartbeat/lease timestamp.
4. Query the instance list from the consumer's perspective.
5. Check which instance and URI the load balancer selects.
6. Send a test request to the selected endpoint, then compare the result with a request via service ID.
7. Cross-reference timestamps across provider, registry, and consumer to spot synchronization lag.

Synchronizing clocks across machines/containers helps correlate logs accurately. When logging, include service ID, instance ID, trace ID, and endpoint selection outcomes if security policy permits; avoid logging tokens, credentials, or sensitive data.

## 13. Combined Example: order-service Calls inventory-service

Suppose a system has two applications:

- `inventory-service` provides an API to read stock.
- `order-service` needs to call the inventory API before confirming an order.

Execution flow:

1. `inventory-service` starts up with `spring.application.name=inventory-service`.
2. The discovery integration registers the instance with Eureka or Consul.
3. The registry maintains the registration and updates status via heartbeats/health checks.
4. `order-service` starts up with its own service ID and connects to the same registry.
5. When stock needs to be checked, `order-service` calls the logical URL `http://inventory-service/api/items`.
6. The load balancer retrieves the list of usable healthy instances and selects one instance.
7. The HTTP client sends the request to the selected endpoint.
8. `inventory-service` processes the request and returns the response.
9. If new instances appear, or old instances fail or stop, the registry and discovery client update the list according to the backend mechanism.

The consumer does not need to edit URLs when `inventory-service` scales from one to multiple instances. It keeps calling by service ID; discovery and load balancing handle finding and selecting the endpoint.

However, a service ID does not replace DNS, routing, or network policies. The address registered by the provider must be reachable from the consumer. If services reside in different networks or clusters, you must design advertised addresses, gateways, cross-network connectivity, or an appropriate discovery mechanism.

## 14. Key Takeaways

- Providers register service instances with the registry through discovery integration and registration abstractions such as ServiceRegistry.
- The registry maintains status via heartbeats/leases, health checks, or backend-specific mechanisms.
- Consumers use DiscoveryClient to find service IDs and lists of ServiceInstance.
- Spring Cloud LoadBalancer selects an instance for each request; the HTTP client sends the request to the chosen endpoint.
- Scaling out, scaling in, restarts, and address changes continuously alter discovery data over time.
- Eureka and Consul differ in registration, health checks, caching, and querying; configure them according to the actual backend.
- Registry data can lag or become stale. Readiness, graceful shutdown, timeouts, observability, and error handling are essential.
- Securing the registry, registration, metadata, health endpoints, and provider APIs is part of service discovery design.

Once you understand the flow from registration to service invocation, you can trace each stage to pinpoint whether an issue lies in the provider, registry, health check, discovery client, load balancer, or network. This provides the foundation for running Spring Cloud Service Discovery reliably as instance and service counts continuously change.
