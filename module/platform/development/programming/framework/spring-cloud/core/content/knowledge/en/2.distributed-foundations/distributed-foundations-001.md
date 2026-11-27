# Services, Instances, and Independent Deployment Boundaries

> **Chapter:** Distributed Foundations  
> **Module:** SPRING_CLOUD_CORE

In a distributed system, a *service* is not synonymous with a running process, and two identical processes are not necessarily two different services. Clearly distinguishing **service**, **service instance**, and **deployment boundary** is essential for designing discovery, load balancing, scaling, version upgrades, and error handling properly.

Spring Cloud Core provides the foundation for Spring Boot applications to communicate with one another through common abstractions in **Spring Cloud Commons**, combined with **Spring Cloud Context**, externalized configuration, and corresponding infrastructure implementations. This lesson builds the mental model before diving into each mechanism.

## 1. Three Concepts to Distinguish

### 1.1. Service: unit of capability and contract

A **service** is a component with a clear business or technical responsibility that exposes an **interaction contract** to other components. That contract may be a REST API, a gRPC API, events on a message broker, or another internal interface.

Example of an e-commerce system:

- `catalog-service` provides product information and contracts such as `GET /products/{id}`.
- `order-service` accepts and manages the order lifecycle.
- `payment-service` processes payment requests and notifies results.

A name like `catalog-service` is the **logical identifier** of the service, commonly called a *service ID*. This identifier must be more stable than the network address of a specific process. A service can have one or multiple instances running at the same time.

A service with a clear responsibility usually owns its API and data rules. However, having a separate name or a separate controller alone is **not enough** to claim that the component can be deployed independently.

### 1.2. Instance: a specific running copy of a service

A **service instance** is a specific process, container, or runtime unit executing a service. Multiple instances can be created from the same build artifact:

| Attribute | Instance A | Instance B |
| --- | --- | --- |
| Service ID | `catalog-service` | `catalog-service` |
| Instance ID | `catalog-a` | `catalog-b` |
| Example address | `10.0.2.11:8080` | `10.0.2.12:8080` |
| Running version | `v1.8.0` | `v1.8.0` |
| Status | Ready | Ready |

Instances share the **service contract**, but each has its own address, lifecycle, request load, and in-memory state. Instance A can be stopped and recreated at another address while the service ID remains `catalog-service`.

Key points:

- **Instances do not synchronize memory by default.** In-process caches or Java variables in one instance do not automatically appear in another instance.
- **Instance ID** is the identifier of the running copy; how it is generated, its uniqueness, and its lifecycle depend on the runtime or discovery provider.
- **Replica** usually refers to an additional running copy of the same workload to increase serving capacity; in this context, a replica is an instance.
- **Instance address** may be a host/port, a URI, or a location mapped by the routing system. You should not treat the current IP as the long-term identity of a service.
- Two instances of a service may temporarily run **different versions** during a rolling deployment; APIs need to support this transitional phase.

### 1.3. Deployment: lifecycle of a release unit

A **deployment unit** is the artifact that can be built, configured, released, scaled, or rolled back in a runtime environment: for example, a Spring Boot application packaged as a JAR/container image and a workload managing its replicas.

Distinguish the following:

| Concept | Question it answers | Example |
| --- | --- | --- |
| **Service** | What capability and contract does the component provide? | `catalog-service` |
| **Service ID** | By what logical name do other components call the service? | `catalog-service` |
| **Instance** | Which specific running copy is serving the request? | Container `catalog-a` at `10.0.2.11` |
| **Deployment/release** | Which version is deployed to the environment, with how many running copies? | Release `v1.8.0`, 3 replicas |
| **Node/host** | Where is the running copy consuming compute resources? | Virtual machine, worker node, physical host |
| **Environment** | Which context do the configuration and operating conditions belong to? | Local, staging, production |

One deployment can manage multiple instances; one service can appear across multiple environments or multiple regional deployment groups. **Service boundaries, source code boundaries, and infrastructure boundaries do not always coincide.** One repository may contain multiple services; one service may be built from multiple modules in the same repository.

## 2. From Service Name to Instance Address

Suppose `order-service` needs to look up product prices. It should express a dependency on the **catalog service**, rather than hardcoding a fixed IP in business logic:

~~~text
Logical identifier: catalog-service
API path:           /products/42

Instances at a point in time:
  catalog-a -> http://10.0.2.11:8080
  catalog-b -> http://10.0.2.12:8080
  catalog-c -> http://10.0.2.13:8080
~~~

Conceptual flow:

~~~mermaid
flowchart LR
    O["order-service\n(consumer)"]
    D["Discovery\nservice ID → instances"]
    L["Load balancer\nselect instance"]
    A["catalog-a\n10.0.2.11:8080"]
    B["catalog-b\n10.0.2.12:8080"]
    C["catalog-c\n10.0.2.13:8080"]
    O -->|"catalog-service"| L
    L <--> D
    L --> A
    L --> B
    L --> C
~~~

The diagram illustrates logical roles and **does not require a proxy load balancer sitting on the network**: with Spring Cloud LoadBalancer, instance selection can happen on the client side. If the infrastructure provides DNS or a virtual IP, address resolution works differently.

Three responsibilities that are often confused:

1. **Service registration:** an instance is published to the appropriate registry mechanism with identification and routing information.
2. **Service discovery:** the caller looks up instances currently published by the discovery source for a service ID.
3. **Load balancing:** the caller or infrastructure selects one instance to serve a request.

Spring Cloud Commons provides the corresponding common abstractions:

| Abstraction | Role |
| --- | --- |
| `ServiceInstance` | Describes a running copy: service ID, host, port, URI, metadata |
| `DiscoveryClient` | Retrieves the list of instances by service ID via a synchronous API |
| `ReactiveDiscoveryClient` | Queries discovery under the reactive model |
| `Registration` and `ServiceRegistry` | Represents instance data and service registration integration operations |
| `LoadBalancerClient` | Common contract for certain instance selection operations in synchronous flows |
| Spring Cloud LoadBalancer | Load-balancing implementation/integration mechanism for compatible HTTP clients |

**Commons does not itself act as a registry server.** Implementations such as Eureka, Consul, or Kubernetes integrations provide ways to retrieve instance information for specific environments. `SimpleDiscoveryClient` can use a static list for development or testing.

You must account for **convergence delay**: a newly started instance may not appear in the list yet; a recently terminated instance may still remain in caches. Discovery results are therefore a *point-in-time snapshot*, not a guarantee that an instance will definitely handle the next request successfully.

## 3. What Is an Independent Deployment Boundary?

A service has an **independent deployment boundary** when its team can release changes to that service without being forced to build, deploy, or stop all related services simultaneously, **provided the contracts and dependencies remain compatible**.

For example, `catalog-service` adds an optional `brand` field to its response. If consumers ignore unknown fields and existing data remains valid, catalog can release without `order-service` needing to release alongside it. Conversely, if catalog immediately removes the `price` field that order reads, both teams must coordinate changes; the deployment boundary has not achieved the desired independence.

Characteristics that enable independent deployment:

- **Stable contracts:** evolve APIs and events according to backward-compatibility rules; consumers and providers can run different versions.
- **Clear data ownership:** a service manages its business invariants and data-access interfaces; other services do not write directly into its internal tables.
- **Separate release lifecycle:** build, test, deploy, scale, and roll back each service individually when conditions allow.
- **Explicit configuration and resources:** environment values, access permissions, connection pools, and resources for each service are managed transparently.
- **Fault containment:** timeouts, concurrency limits, controlled retries, and disconnect handling prevent errors from cascading indefinitely.
- **Observability:** logs, metrics, and traces help pinpoint which version and instance caused an error.

Deployment independence **does not** mean having zero dependencies. `order-service` may still need prices from catalog to calculate totals; what must remain independent is **the decision to change versions, operate, and deploy** within the committed contract.

### 3.1. One shared application vs. multiple separate services

~~~mermaid
flowchart TB
    subgraph M["One deployment unit"]
      MC["catalog module"]
      MO["order module"]
      MP["payment module"]
    end
    subgraph S["Three deployment units"]
      SC["catalog-service"]
      SO["order-service"]
      SP["payment-service"]
    end
    MC --- MO
    MO --- MP
    SO -->|"API/event"| SC
    SO -->|"API/event"| SP
~~~

On the left, three modules may be cleanly layered in code yet share a single release lifecycle. On the right, each service can have its own pipeline, instances, and versions. The second organization enables independent scaling and releasing of each part, at the cost of handling networking, distributed data, observability, and cross-version compatibility.

**Splitting every module into a service does not automatically make a system better.** When two components must always be updated together or require a single overarching internal transaction, review the business boundaries before deciding to distribute them.

### 3.2. Data boundaries largely determine autonomy

A design prone to tight coupling:

~~~text
order-service ─┐
               ├── directly reads/writes the same inventory table
stock-service ─┘
~~~

If `order-service` directly modifies `stock-service`'s table, changing the schema or reservation rules can break the other service. They are two processes without independent data ownership.

A design with a clearer contract:

~~~text
order-service ── ReserveStock API / event ──> stock-service
                                              |
                                              v
                                       stock data managed
                                       by stock-service
~~~

In the second model, `stock-service` enforces the validity of stock deduction/reservation operations. `order-service` only knows the published interface, not internal tables or transactions. When multiple services participate in a workflow, you must design intermediate states, idempotency, and compensation or eventual consistency where appropriate; **you cannot assume a single ACID transaction spans across network requests**.

Each service does not necessarily require a separate physical database server. What matters is that **schema/data ownership and access paths** are clear enough that one service cannot inadvertently break another service's contract.

## 4. How Does a System Change When a Service Has Multiple Instances?

Suppose `catalog-service` currently has one instance. When traffic grows, the system scales up to three instances from the same image:

| State | Instance count | Meaning |
| --- | ---: | --- |
| Before scaling | 1 | A single running copy serves requests |
| After horizontal scaling | 3 | Multiple running copies can share the load |
| One instance fails | 2 remaining available | System can continue if routing detects and skips the failed instance |
| New version release | Temporarily both v1 and v2 | Consumers may hit both versions during a rolling deployment |

**Horizontal scaling** increases the number of instances. **Vertical scaling** increases CPU/RAM resources for a single instance. Neither alters the logical service contract, yet both affect performance, cost, and operations.

Multiple instances raise questions that single-process applications rarely face:

- If a session or shopping cart lives only in instance A's RAM, what happens when the next request lands on B? State must be stored in a shared store, designed to be stateless, or handled with an appropriate strategy.
- If two instances process a command concurrently, how does the system prevent duplicate updates? Locks, data constraints, idempotency, or orchestration are needed depending on the problem.
- If an instance hangs while its port stays open, how does the router determine it is no longer ready? Proper health/readiness checks are required.
- If instances span different network zones, latency and data access costs may differ; the instance selection algorithm must account for actual deployment requirements.

To achieve fault tolerance, replicas should also avoid sharing a single point of failure wherever possible: the same node, the same zone, or the same infrastructure dependency. Three containers on one host can still all go down together when that host stops.

## 5. Spring Boot Example: One Service ID, Two Instances

Example goal: run two instances of `inventory-service` and have `order-service` call them by **service ID**. The example uses static addresses to illustrate the concept without installing a registry server.

### 5.1. Two running copies of `inventory-service`

The inventory application has the configuration:

~~~yaml
spring:
  application:
    name: inventory-service

server:
  port: 8081
~~~

An illustrative endpoint in inventory:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/stock")
public class StockController {

    @GetMapping("/{sku}")
    public StockResponse getStock(@PathVariable String sku) {
        return new StockResponse(sku, 12); // Mock data for the example
    }

    public record StockResponse(String sku, int available) {}
}
~~~

If the application has the appropriate Web dependency, after building `inventory-service.jar`, you can launch **two separate processes** on the same machine on two ports:

~~~bash
java -jar inventory-service.jar --server.port=8081
java -jar inventory-service.jar --server.port=8082
~~~

Both share `spring.application.name=inventory-service`. This name identifies the application on the Spring Boot side, but **does not automatically turn it into a dynamically discoverable service**: the caller still needs a source of instance lists or an appropriate routing mechanism.

### 5.2. Defining the instance source for `order-service`

Place the configuration below in the order application:

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

`SimpleDiscoveryClient` reads a static list from configuration. In real environments, `localhost` inside a container only points to **that container itself**; if services run in different containers/nodes, you must use addresses reachable from the order service.

The order application needs an appropriate HTTP client and Spring Cloud LoadBalancer, for example `spring-boot-starter-webflux` (to use `WebClient`) along with `spring-cloud-starter-loadbalancer`. Use a **Spring Cloud BOM/release train compatible with Spring Boot** to manage dependency versions. With a real registry, add the corresponding integration.

### 5.3. Calling by service ID via `@LoadBalanced`

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class InventoryHttpClientConfig {
    @Bean
    @LoadBalanced
    WebClient.Builder inventoryWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class InventoryGateway {
    private final WebClient client;

    public InventoryGateway(@LoadBalanced WebClient.Builder builder) {
        this.client = builder.build();
    }

    public Mono<StockResponse> stockOf(String sku) {
        return client.get()
                .uri("http://inventory-service/stock/{sku}", sku)
                .retrieve()
                .bodyToMono(StockResponse.class);
    }

    public record StockResponse(String sku, int available) {}
}
~~~

When calling `stockOf("SKU-42")`, the host `inventory-service` is the **service ID**, resolved by the load-balancing mechanism to one of the configured instances. The actual request goes to `localhost:8081` or `localhost:8082`; `InventoryGateway` does not need to be modified when changing the instance source.

Basic flow:

~~~mermaid
sequenceDiagram
    participant Order as order-service
    participant LB as Spring Cloud LoadBalancer
    participant Discovery as DiscoveryClient
    participant Inventory as inventory-service instance
    Order->>LB: GET http://inventory-service/stock/SKU-42
    LB->>Discovery: Look up inventory-service instances
    Discovery-->>LB: 8081, 8082
    LB->>Inventory: Pick instance, send GET /stock/SKU-42
    Inventory-->>Order: StockResponse (via HTTP client)
~~~

**Example limitations:** Both running copies return the same mock data `available=12`. If real data were stored only in local RAM, instances could return inconsistent results. A static list does not update automatically when instances are terminated or scaled; do not use this example to infer dynamic discovery or production fault tolerance.

## 6. Instance Lifecycle and Readiness State

An instance can be **running** yet not **ready to receive traffic**. For example: the JVM has opened the HTTP port, but the application is still initializing caches, running migrations, or establishing required connections.

~~~mermaid
stateDiagram-v2
    [*] --> Starting
    Starting --> Ready: Initialization complete
    Ready --> Draining: Begin shutdown/rolling update
    Draining --> Stopped: Finish remaining requests
    Ready --> Unhealthy: Error occurred
    Unhealthy --> Ready: Recovered
    Unhealthy --> Stopped: Stopped/replaced
    Stopped --> [*]
~~~

Distinguish two common types of checks:

| Check | Question answered | Typical action |
| --- | --- | --- |
| **Liveness** | Is the process still alive according to required criteria? | Runtime may restart the process if it is stuck |
| **Readiness** | Is the instance ready to process new requests? | Stop routing new traffic to an unready instance |

With Spring Boot Actuator on a version supporting health probes, you can configure:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Commonly used endpoints include `/actuator/health/liveness` and `/actuator/health/readiness` when Actuator and the appropriate configuration are present. Routing policy depends on the runtime, integration, and actual probes. **Do not include every remote dependency failure in liveness**: a temporary database outage could cause all replicas to restart simultaneously, worsening the incident.

When shutting down an instance, a safe procedure is generally to transition out of receiving new requests, drain in-flight traffic, finish or gracefully cancel remaining work, and then stop the process. The timing of deregistration, readiness updates, drain waiting, and discovery convergence varies by environment; you cannot assume all requests stop reaching an instance immediately.

## 7. Compatible Contracts Enable Independent Deployment

During a rolling deployment, old and new instances can coexist. Moreover, consumers and providers may be released by different teams at different times. Therefore, independent deployment boundaries are always tied to **cross-version compatibility**.

Suppose `catalog-service` initially returns:

~~~json
{
  "id": "P-42",
  "name": "Keyboard",
  "price": 350000
}
~~~

The new version adds a field:

~~~json
{
  "id": "P-42",
  "name": "Keyboard",
  "price": 350000,
  "brand": "Example"
}
~~~

This **can** be a compatible change if older consumers ignore unknown properties and existing semantics remain unchanged. Conversely, changing `price` from a number to a string or removing `id` can break older clients.

| Planned change | Compatibility risk | Suggested rollout approach |
| --- | --- | --- |
| Add optional field to response | Usually low when clients ignore unknown fields | Test older consumers; preserve published semantics |
| Rename/remove a field in use | High | Keep the old field during a transition period or create a new API version |
| Change the meaning of `price` | High even if the schema is unchanged | Redefine the contract and version when necessary |
| Add nullable column to service-owned DB | Often deployable incrementally | Expand schema first, then deploy code using it |
| Rename/drop column still read by old instances | High during rolling deploy | *Expand → migrate → contract* pattern |
| Change structure of an event with active consumers | Can impact multiple services | Manage schema/versions and test reader compatibility |
| Increase replica count without changing API | Usually low contract impact | Review shared state, concurrency, and dependency capacity |

For databases, **expand → migrate → contract** means: add new structures so old versions still work, migrate data and applications in phases, and only remove old structures once confident no consumers remain. For APIs, apply contract tests and cross-version testing, especially when deployments do not happen simultaneously.

Some cases genuinely require coordinated releases, such as a security change forcing all clients to update. In those cases, explicitly define the transition window and rollback rights; do not claim absolute deployment independence.

## 8. Distributed Failures and Fault Boundaries

When `order-service` calls `inventory-service` over HTTP, failure modes arise that do not exist in in-process calls:

1. The request may **never reach** the target instance.
2. The instance may process it successfully, but the **response is lost on the way back**.
3. The instance may return an intentional error, time out, or be terminated mid-deployment.
4. Discovery may return stale addresses; an empty instance list can also be a temporary state.

This directly impacts business logic. Suppose order calls a **reserve stock** API and times out: you cannot conclusively tell whether stock was reserved or not. Blindly retrying can reserve stock twice. A common solution is an **idempotency key** for side-effecting operations, alongside business-appropriate timeouts and bounded retries.

| Mechanism | Problem addressed | Caveat |
| --- | --- | --- |
| Timeout | Prevents waiting indefinitely when a dependency does not respond | Choose thresholds based on SLOs and total time budget |
| Retry/backoff | Retries transient failures | Only retry when safe; cap attempts to avoid load amplification |
| Circuit breaker | Stops sending excessive requests to a failing dependency | Needs appropriate state-transition and recovery policies |
| Bulkhead/concurrency limit | Reduces the chance of one dependency exhausting resources | Does not replace capacity management |
| Readiness/health | Avoids sending traffic to unready instances | Accuracy depends on probes and orchestrator updates |
| Tracing/metrics | Makes errors visible across services and instances | Tag with service ID, instance, version, trace ID |

Spring Cloud Commons helps application code use shared contracts for instances, discovery, and load balancing; **it does not by itself provide full timeout, retry, circuit breaker, or data consistency policies**. Those capabilities require appropriate tools and configuration at the HTTP, resilience, message broker, and storage layers.

## 9. Role of Externalized Configuration, Context, and Version Compatibility

In the SPRING_CLOUD_CORE module, service/instance boundaries connect directly to three other foundational areas:

### 9.1. Spring Boot externalized configuration

Between staging and production, **the same artifact** can use different URLs, secrets, timeouts, ports, pool limits, or namespace names. These values should live in appropriate configuration sources rather than being hardcoded to individual instance addresses.

`spring.application.name` expresses the application name; the service ID used by the discovery system may be derived from this name or configured separately by the integration. When using a registry, check the implementation's documentation to see how naming, registration, and instance identification work.

### 9.2. Spring Cloud Context and refresh

`@RefreshScope` and the refresh mechanism in Spring Cloud Context can help update certain beans/configurations while the application is running, depending on how refresh is triggered and the configuration source. **Refreshing configuration is not equivalent to deploying a new code version.** Changing a JAR/image still requires releasing and managing the instance lifecycle.

Adding or removing instances is a change to the **runtime topology**; callers typically observe it via discovery/load balancers. Changing a `timeout` parameter is a change to **client configuration** and also depends on whether the bean/client is refreshed properly.

### 9.3. Spring Cloud and Spring Boot must be compatible

When building each service, choose a **Spring Cloud release train/BOM** compatible with Spring Boot within that service. Two services running different Boot or Cloud versions is possible if they interact over compatible network contracts; however, **within each service**, dependencies and auto-configuration must still form a supported combination.

Do not copy assumptions about APIs or starters from an older release train to a newer one. Check the official compatibility matrix when upgrading and re-verify discovery, HTTP client, load balancing, refresh, and health paths.

## 10. Testing and Operating Across Three Layers

### 10.1. Service-layer testing

Verify API/event contracts, business rules, and data ownership. With the `DiscoveryClient` interface, you can mock the `ServiceInstance` list to verify consumer logic without standing up a real registry.

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class InventoryDiscoveryTest {

    @Test
    void findsTwoInstancesOfTheSameService() {
        DiscoveryClient client = mock(DiscoveryClient.class);
        when(client.getInstances("inventory-service")).thenReturn(List.of(
            new DefaultServiceInstance("inv-1", "inventory-service", "localhost", 8081, false),
            new DefaultServiceInstance("inv-2", "inventory-service", "localhost", 8082, false)
        ));

        assertThat(client.getInstances("inventory-service"))
                .extracting(instance -> instance.getServiceId())
                .containsExactly("inventory-service", "inventory-service");
    }
}
~~~

The example assumes JUnit 5, Mockito, and AssertJ in test dependencies. This test only verifies **two running copies with the same service ID** mocked at the discovery layer; it does not verify that requests were load-balanced. Testing load balancing requires exercising the HTTP layer or verifying the corresponding instance-selection mechanism.

### 10.2. Instance-layer testing

Launch at least two instances on different ports or containers, then stop one copy and observe. Expectations must be clearly defined: does the system keep responding, how long does it take to avoid the failed instance, how many requests fail during the transition, and do retries behave safely?

Beyond success cases, test the scenario where **the instance finishes processing while the client times out** to uncover duplicate side-effecting operations.

### 10.3. Deployment-boundary testing

In a production-like environment:

1. Keep `order-service` on the old version, deploy the new version of `catalog-service`, and run contract tests.
2. Create a period where both old and new catalog instances coexist, and check whether responses/schemas remain compatible.
3. Test rolling back catalog while order is running; verify that the DB schema remains compatible.
4. Scale replicas up/down and observe health, metrics, latency, and throughput.
5. Inject a fault into an instance or dependency; inspect blast radius and recovery behavior.

When investigating errors, record **service ID, instance ID, application version, environment, trace/correlation ID**, and target URI at appropriate log levels. Looking at the service name alone is often insufficient to tell which replica originated the error.

## 11. Common Design Questions

**Can a service have only one instance?** Yes. A service is a logical unit; how many instances it has is a deployment decision. One instance may suffice locally or under low traffic, but represents a single point of failure in production without a recovery plan.

**Are two instances running different versions still the same service?** Potentially yes, if they serve a compatible logical contract during the transition window. If semantics or data are incompatible, appropriate versioning or traffic routing must be designed.

**Does using containers or Kubernetes automatically mean you have microservices?** No. Containers are a packaging/runtime mechanism; microservices depend on business boundaries, contracts, and release autonomy. A multi-container system can still require lockstep deployments due to tight coupling.

**Does Spring Cloud create business boundaries for you?** No. Spring Cloud helps implement discovery, configuration, connectivity, and required abstractions. Splitting services, owning data, and designing compatibility are architectural decisions.

**When should you not split into separate services?** When the costs of networking, integration testing, data consistency, and operations outweigh the benefits of independent releasing/scaling; especially when two components always change together and lack a stable contract.

## 12. Applied Exercise

A system has `checkout-service`, `inventory-service`, and `payment-service`. Inventory currently has two instances; checkout only knows the URI of the first instance. The inventory team wants to scale up to four replicas and release an API returning an additional `warehouseId` field.

Answer the following:

1. In this model, **how many services** and **how many inventory instances** exist before and after scaling?
2. What does checkout need to change to call by **service ID** instead of relying on a fixed IP?
3. Under what condition is adding `warehouseId` a backward-compatible change?
4. If checkout times out when calling the stock-reservation API, why can't it retry unconditionally?
5. What testing and observability evidence allows inventory to release independently while checkout keeps running?

**Self-check hints:** instance count does not increase the number of logical services; discovery provides the list and the load balancer picks an instance; contracts must support older consumers; side-effecting operations require idempotency; and rolling deployments must work while two versions coexist.

**Key takeaway:** A **service** represents responsibility and contract; an **instance** is a running copy with its own address and lifecycle; an **independent deployment boundary** is the ability to release, scale, and recover each service provided contracts remain compatible. Spring Cloud Commons and Spring Cloud integrations connect logical identifiers to concrete instances, while operational independence depends on how APIs, data, and deployment workflows are designed.
