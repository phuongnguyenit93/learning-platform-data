# Registration Control Path and Business Request Data Path

In a microservice architecture, knowing the address of another service involves two activities with distinct purposes. The system must **publish and update instance information** so components know which services exist; then the consumer must **send business requests to a specific instance**. You can view these two activities as the control path and the data path.

In Spring Cloud Service Discovery, the control path typically flows through the provider's registration mechanism, ServiceRegistry, the service registry, and health checks. The request data path flows through the consumer, DiscoveryClient or an instance list supplier, Spring Cloud LoadBalancer, and the HTTP client calling the provider. Both paths are closely connected because the data path relies on information published by the control path.

Distinguishing the two paths makes system design and diagnostics much clearer: the registry can be healthy while requests still fail due to networking or the provider; conversely, the registry may be temporarily unreachable while consumers can still call certain instances using existing cached data.

## 1. Two paths answer two different questions

Consider order-service needing to call inventory-service. There may be three inventory instances running across three different containers. The consumer should not hardcode each container's address, because addresses change when scaling, restarting, or deploying a new version.

The system needs to answer two questions:

- **Control path:** Which services are being advertised? Which instances exist? Are instances eligible to receive traffic? Has registration information changed?
- **Request data path:** For this request, which instance will the consumer choose? Which endpoint will it connect to? Does the provider process it and return a successful response?

| Aspect | Registration control path | Business request data path |
|---|---|---|
| Goal | Publish and maintain service status | Send requests to the target service |
| Key components | Provider discovery integration, ServiceRegistry, registry, health checks | Consumer, DiscoveryClient/instance supplier, LoadBalancer, HTTP client, provider |
| Primary data | Service ID, instance ID, host, port, metadata, health status | HTTP request, target URI, headers, body, response |
| Cadence | On startup, heartbeats, health checks, status changes, shutdown, and refresh | On every business request |
| Common failures | Registration failure, wrong service ID, faulty health check, slow registry updates | Timeouts, connection refused, HTTP errors, unreachable endpoint |
| Diagnostic question | Which instances is the registry currently advertising? | Which instance did the request actually reach and what was the outcome? |

The two paths are an architectural analysis model. They do not necessarily run over two separate physical networks or two separate server clusters. In a Spring Cloud deployment, some activities may share the same process, connections, or libraries.

## 2. Overall architecture diagram

~~~mermaid
flowchart TB
    subgraph CP["Registration control path"]
        P["Provider instance"] -->|"register / update / deregister"| SR["ServiceRegistry integration"]
        SR --> R[("Eureka Server / Consul")]
        HC["Health checker / agent"] -->|"probe"| P
        HC -->|"report status"| R
        R -->|"registry data / refresh"| DC["Consumer-side discovery data"]
    end

    subgraph DP["Business request data path"]
        C["Consumer"] -->|"service ID + request"| LB["Spring Cloud LoadBalancer"]
        DC -->|"instance list"| LB
        LB -->|"select endpoint"| HTTP["HTTP client"]
        HTTP -->|"HTTP request"| P
        P -->|"HTTP response"| C
    end
~~~

The control path creates and updates routing information. The request data path uses that information to pick a target and deliver business data.

Some systems may place the registry and consumers in the same internal network; others may run a local Consul Agent on each node. Regardless of topology differences, logical responsibilities can still be separated along these two paths.

## 3. Control path: provider publishes instances

The control path begins when the provider starts up. The provider must advertise its service name and an endpoint reachable by consumers.

For example, an instance of inventory-service might advertise:

| Property | Illustrative value |
|---|---|
| Service ID | inventory-service |
| Instance ID | inventory-service-8081-node-a |
| Host | 10.0.1.12 |
| Port | 8081 |
| Scheme | http |
| Metadata | zone=zone-a, version=v2 |
| Health | UP |

Specific fields depend on the implementation. What matters is that the advertised address must be routable from the consumer side. Registering an address reachable only from inside the provider's container causes discovery to return seemingly valid data while requests still fail.

### 3.1. Role of ServiceRegistry

Spring Cloud Commons defines ServiceRegistry as the abstraction for registering and updating instance status. Common contract operations include register, deregister, set status, and get status. A Registration object carries information tailored to the specific backend.

Logical flow when a provider starts:

1. Spring Boot creates the application context.
2. The discovery integration reads application settings such as service name, port, host, and metadata.
3. The integration creates a registration object.
4. The ServiceRegistry implementation sends the registration to the registry or agent.
5. The registry stores the instance details so consumers can discover it.

In Spring Cloud applications, starters typically provide auto-configuration for this process. Providers do not need to build a custom HTTP client to call Eureka or Consul registration APIs if they already use the corresponding integration.

### 3.2. Provider configuration example with Eureka

A Eureka Client application might use this configuration:

~~~yaml
spring:
  application:
    name: inventory-service

server:
  port: 8081

eureka:
  client:
    serviceUrl:
      defaultZone: http://eureka.internal:8761/eureka/
  instance:
    preferIpAddress: true
~~~

When the application starts, the Eureka Client registers the instance with Eureka Server and renews its lease on a heartbeat interval. Eureka Server maintains registration records based on leases and Eureka's operational rules.

The preferIpAddress property affects how the instance advertises its address in applicable configurations. Always verify that the advertised address is reachable from consumers, especially when running in containers or across multiple subnets.

### 3.3. Provider configuration example with Consul

With Consul, Spring Cloud applications usually register services through a Consul Agent:

~~~yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      host: consul-agent.internal
      port: 8500
      discovery:
        service-name: inventory-service
~~~

The agent receives registration details and syncs them into the catalog. Health checks, tags, instance ID, and deregistration options can be configured further depending on deployment needs and the Spring Cloud Consul version.

Consul has its own agent and catalog model. Therefore, when investigating registrations, inspect both the status on the agent and the status published in the catalog.

## 4. Control path: maintaining health and updating the registry

Successful registration does not mean an instance will remain healthy forever. The registry needs to know whether the instance is still alive and capable of receiving traffic.

Two common mechanisms:

- **Heartbeat/lease:** the client sends periodic signals to keep its registration active. If the lease expires, the registry can evict or mark the instance per policy.
- **Health check:** the agent or registry performs probes, such as HTTP or TCP checks, and updates health status accordingly.

Eureka primarily maintains registrations via client heartbeats/leases and can optionally integrate application health status per configuration. Consul supports health checks attached to service registrations, typically via the agent. Do not treat heartbeats and health checks as the same concept: heartbeats indicate the client is still renewing its registration, whereas health checks test serving readiness via a specific probe.

### 4.1. Liveness and readiness

With Spring Boot Actuator, an application can expose health endpoints. When you need to separate process survival from traffic readiness, design probes according to purpose:

- **Liveness:** is the process still running and able to continue executing?
- **Readiness:** is the instance ready to accept business requests?
- **Dependency health:** are dependencies such as databases or message brokers responding?

Example health endpoint exposure configuration:

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

Exposure configuration alone does not guarantee the registry is calling the right readiness endpoint. You must configure the corresponding path, port, protocol, and access permissions in the backend or discovery integration. Avoid exposing internal health indicator details to unauthorized parties.

### 4.2. Status transitions and convergence time

Suppose instance inventory-service-8081-node-a begins failing health checks:

1. The probe detects failures or heartbeats stop being renewed.
2. The backend applies thresholds, timeouts, and health/lease policies.
3. The registry updates status or excludes the instance from eligible results.
4. The consumer-side discovery client or instance supplier refreshes its data.
5. The load balancer uses the updated list for subsequent instance selections.

These steps do not necessarily happen instantaneously. Health intervals, failure thresholds, lease durations, caches, and refresh cycles all affect the time between when an instance fails and when all consumers stop selecting it.

The concept of **eventual consistency** is useful for understanding that lag: components can see different states for a period of time before data converges. Applications must still tolerate failed requests during the transition window.

## 5. Request data path: consumer discovers service

The consumer knows the service ID, such as inventory-service, without needing to know which host an instance runs on. In Spring Cloud Commons, DiscoveryClient provides the query API:

~~~java
List<String> getServices();

List<ServiceInstance> getInstances(String serviceId);
~~~

getServices() lists the service IDs visible to the discovery client. getInstances(serviceId) returns the matching list of ServiceInstance objects. Each instance typically provides host, port, URI, secure flag, and metadata.

Example injecting DiscoveryClient:

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class InventoryLookup {

    private final DiscoveryClient discoveryClient;

    public InventoryLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
~~~

This result reflects the discovery data currently seen by the consumer. It may come from the registry or from a client-side cache depending on implementation and configuration. A list containing an instance does not guarantee the endpoint is still healthy when a request is sent a few milliseconds later.

### 5.1. Discovery queries are not business requests

When a consumer calls getInstances(), it is asking for routing information. This request is not a business request like "fetch product list" or "create order".

This distinction matters when measuring load and diagnosing issues:

- Discovery queries place load on the registry or cache/discovery client.
- Business requests place load on provider instances.
- A business request might not hit the registry directly if the instance list is already cached and valid.
- The discovery client may refresh data in the background or according to the backend's own mechanism.

Therefore, never assume every business HTTP request triggers a network call to the registry. Refresh behavior depends on the discovery implementation, caching, and the service instance supplier.

## 6. Load balancer connects control data with business requests

When multiple instances exist, the consumer must choose one instance per call. Spring Cloud LoadBalancer uses the service ID and an instance list source to make the selection.

Logical flow:

1. The consumer calls a logical URL, e.g. http://inventory-service/api/items.
2. The load-balancing-enabled HTTP client recognizes inventory-service as a service ID.
3. LoadBalancer obtains the list of usable instances.
4. One instance is selected according to the algorithm and configuration.
5. The HTTP client sends the request to that instance's endpoint.

RestTemplate configuration example:

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

Example calling an API by service name:

~~~java
ItemResponse[] items = restTemplate.getForObject(
        "http://inventory-service/api/items",
        ItemResponse[].class
);
~~~

The application requires a compatible Spring Cloud LoadBalancer dependency and a configured discovery integration. For WebClient or RestClient, integration details depend on the Spring Boot and Spring Cloud versions in use.

### 6.1. Role of instance supplier and cache

LoadBalancer typically receives instances through a service instance list supplier. The supplier may fetch data from DiscoveryClient, apply filtering, or cache results depending on configuration.

Several concepts to distinguish:

- DiscoveryClient is the service discovery query abstraction.
- Service instance supplier provides the instance list to LoadBalancer.
- Cache holds the list for a duration to reduce repeated queries.
- LoadBalancer picks an instance from the supplied list.

Caching reduces registry load and lookup latency, yet caching for too long can retain failed endpoints. Caching for too short a period increases load and refresh overhead. Choose configuration based on instance churn rate, system scale, and request tolerance for stale data.

## 7. Business request reaches the provider

After selecting an endpoint, the HTTP client opens a connection and sends the request. From here, processing follows a normal HTTP flow:

~~~mermaid
sequenceDiagram
    participant O as order-service
    participant LB as LoadBalancer
    participant DS as Discovery data
    participant I as inventory instance
    O->>LB: GET http://inventory-service/api/items
    LB->>DS: Obtain candidate instances
    DS-->>LB: Instance A, B, C
    LB->>LB: Select one instance
    LB->>I: HTTP GET /api/items
    I-->>O: HTTP response
~~~

The provider receives the request, authenticates the caller, checks authorization, executes business logic, and returns a response. Service discovery does not perform those responsibilities on the provider's behalf.

For example, order-service may pick instance A initially and instance B on the next request. Business code still invokes the same logical URL. If the first request fails because instance A just stopped while the registry had not yet updated, the consumer needs proper timeouts and error-handling policies.

Do not blindly retry every request. Retrying non-idempotent write operations can create duplicate orders or payments. Use idempotency keys or appropriate business safeguards before enabling retries for operations with side effects.

## 8. Relationship between the two paths during scaling and deployment

The control path reflects instance lifecycle changes; the request data path uses updated information to send requests.

### 8.1. Scale out: adding instances

When inventory-service scales from two to three instances:

1. The new instance starts and advertises the same service ID.
2. The control path registers the new endpoint in the registry.
3. Health checks or readiness confirm the instance is eligible for traffic per policy.
4. The registry publishes the updated state.
5. Consumers update their instance list on their refresh cycle.
6. LoadBalancer can select the new instance for subsequent requests.

During convergence, some consumers may not yet see the new instance. This is not necessarily an error; check refresh/cache intervals and registration status.

### 8.2. Scale in: removing instances

When an instance needs to stop:

1. The provider transitions to not accepting new traffic or begins graceful shutdown.
2. The provider deregisters from the registry if its lifecycle and backend support it.
3. The registry updates its list.
4. Consumers refresh discovery data.
5. LoadBalancer stops picking the instance once the new list takes effect.
6. In-flight requests finish via graceful shutdown and connection draining.

If an instance is killed abruptly, deregistration may not execute. Heartbeats/leases or health checks will detect the outage after a period of time. Consequently, in-flight requests or consumers with cached data may still encounter errors during the transition window.

### 8.3. Deploying a new version

During a rolling deployment, old and new versions may coexist under one service ID. Metadata such as version, zone, or region can support observability or instance filtering, but only when the backend, supplier, and LoadBalancer policy are configured to use those attributes.

Do not assume that merely registering metadata causes LoadBalancer to automatically prefer or exclude a version. Selection rules must be explicitly implemented and tested.

## 9. When one path fails while the other still works

The two paths are related, yet can fail independently. Distinguishing them helps apply the right remediation.

| Scenario | Control path | Request data path | Observable impact |
|---|---|---|---|
| Registry temporarily unreachable | Registration/refresh disrupted | May still make calls using existing cache | New instances unseen; stale data may continue being used |
| Provider dead but registry has not detected it yet | Health/lease data not yet updated | Requests to that instance may time out | Connection errors even though discovery still returns the instance |
| Consumer cannot reach registry | Query/refresh fails | May use cache or fail to pick an instance | Depends on remaining cached data and error policies |
| Provider registers wrong address | Registration succeeds but endpoint is wrong | Requests cannot connect | Instance appears in registry yet calls fail |
| Network policy blocks consumer to provider | Registry may be completely healthy | Requests fail | Discovery succeeds yet the data path is blocked |
| Misconfigured LoadBalancer | Registry still publishes accurately | Picks wrong instance or rewrites URL wrongly | Consumer-side routing failures |

### 9.1. Registry disruption does not immediately stop all requests

If consumers still hold a valid cached instance list, some requests can continue reaching providers while the registry is temporarily disconnected. However:

- New instances may go undiscovered.
- Failed instances may remain in the cache.
- Cache expiration may leave consumers unable to fetch an updated list.
- Behavior when refresh fails depends on implementation and configuration.

Therefore, never design applications assuming the registry is always reachable or caches always hold accurate data.

### 9.2. A healthy registry does not guarantee request success

The registry may advertise an instance as healthy, yet requests can still fail because:

- The advertised host or port is not routable from the consumer.
- A firewall, security group, or network policy blocks the connection.
- The provider became overloaded after the latest health check.
- TLS certificates or authentication fail.
- The API returns a business or downstream dependency error.

A health check is a point-in-time signal for a specific probe. It is not a pledge that every subsequent request will succeed.

## 10. Securing both the control path and data path

The control path carries topology data and permissions to alter registrations. The data path carries business data. Both must be protected.

| Scope | Risk | Mitigation |
|---|---|---|
| Registry API | Unauthorized reading of topology or modifying registrations | Authentication, authorization, ACLs, and network restrictions |
| Provider registration | Instance spoofing a service or endpoint | Only authorized workloads may register |
| Metadata | Leaking tokens, passwords, or internal info | Do not store secrets in metadata; restrict published fields |
| Health endpoint | Exposing system internals or abuse | Restrict access to required agents/monitoring; limit response details |
| Consumer to provider | Eavesdropping or endpoint spoofing | TLS, service-to-service authentication, and certificate management |
| Business APIs | Over-privileged callers | Authentication and authorization at the provider |

With Consul, ACLs can restrict catalog read/write and service registration permissions. With Eureka, protect servers, networks, credentials, and administrative endpoints according to the deployment model. Finding an address via discovery does not mean the consumer is authorized to invoke the API.

## 11. Observing each path separately

To operate effectively, maintain separate metrics and logs for registration/discovery and for business requests.

### Observing the control path

Track:

- Number of registered instances per service ID.
- Registration and deregistration timestamps.
- Heartbeat or health check success rates.
- Time from instance startup until appearance in the registry.
- Time from instance failure until removal from discovery results.
- Connection, authentication, or timeout errors between providers, agents, and the registry.

### Observing the request data path

Track:

- Called service ID and actual selected instance.
- Request rate, latency, and status codes per instance.
- Rates of timeouts, connection refused, and TLS errors.
- Retry counts and retry outcomes.
- Traffic distribution ratios across instances.
- Trace IDs linking consumer logs to provider logs.

When logging, never write tokens, credentials, or sensitive payloads to logs. Synchronize clocks across consumers, providers, and the registry so timestamps can be compared and lag measured accurately.

## 12. Top-down diagnostic workflow

When order-service fails to call inventory-service, determine which path owns the failure:

1. **Check the provider:** is the instance running and does the API respond directly from the consumer's network?
2. **Check registration:** does the registry have the right service ID, host, port, and instance ID?
3. **Check health:** is the instance healthy/ready per configuration? Did the latest heartbeat or probe succeed?
4. **Check discovery:** does DiscoveryClient on the consumer return the instance list? Is the data stale?
5. **Check load balancing:** did LoadBalancer pick the right instance and construct the right URI?
6. **Check networking and security:** can the consumer reach the selected endpoint? Do TLS, credentials, and policies allow it?
7. **Check business logic:** did the provider receive the request, what status did it return, and which layer threw the error?

A useful test is comparing two call styles in a test environment: calling a known endpoint directly versus calling by logical service name. If direct calls succeed while logical name calls fail, focus on discovery data, load balancer, or HTTP client integration. If both fail, inspect the provider, network, and API.

## 13. End-to-end example: order-service and inventory-service

Suppose inventory-service has three instances. order-service needs to check stock quantities before confirming an order.

**Control path:**

1. Three instances start with service ID inventory-service.
2. Each instance registers its own endpoint with Eureka or Consul.
3. The registry maintains status via leases/heartbeats or health checks.
4. One instance fails; the backend updates status and consumers gradually receive the updated list.
5. A new instance is deployed; after registering and becoming healthy, it appears in discovery data.

**Request data path:**

1. order-service receives an order confirmation request.
2. The HTTP client calls http://inventory-service/api/items.
3. Spring Cloud LoadBalancer obtains the list of available instances.
4. LoadBalancer picks one instance.
5. The HTTP client sends the request to that endpoint.
6. inventory-service returns the stock quantity.
7. order-service proceeds with or rejects order confirmation based on the business result.

If the registry suffers a brief outage while consumers still hold caches, some requests may continue succeeding. If caches contain a failed instance, requests can still fail. If the registry operates normally yet a network policy blocks connections to an instance, successful discovery still will not let requests complete.

## 14. Key takeaways

- The registration control path publishes service IDs, instance endpoints, metadata, and health status.
- ServiceRegistry is the registration-side abstraction; Eureka and Consul differ in storage, heartbeat, and health mechanisms.
- The request data path uses discovery information to choose an instance and send business requests.
- DiscoveryClient fetches the instance list; Spring Cloud LoadBalancer selects an instance; the HTTP client executes the connection.
- The registry and consumers may see different states temporarily due to heartbeats, health checks, caching, and refresh cycles.
- A healthy registry does not guarantee reachable endpoints; a failed request does not necessarily mean registration failed.
- Secure the registry and registrations on the control path; secure connections and APIs on the data path.
- Monitoring registration/health separately from request latency/errors helps pinpoint exactly where a failure occurs.

Analyzing service discovery through these two paths tells you whether the system is struggling to publish and update information or struggling to use that information to route requests. This forms the foundation for designing, deploying, and operating Spring Cloud Service Discovery reliably as microservices continuously change.
