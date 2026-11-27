# What is Service Communication and Why is Load Balancing Needed

In a microservices architecture, a single business workflow often spans multiple services. When a user places an order, the Order service may call Inventory to check stock, Pricing to calculate prices, and Payment to process payment. Each service can run multiple replicas to increase processing capacity and maintain availability when a machine fails.

**Service communication** is how one service exchanges data or processing requests with another service. Common approaches include HTTP/REST calls, gRPC, and sending messages via a message broker. Client-side load balancing is especially useful for request-response calls: the caller needs to find an instance capable of accepting the request, choose an appropriate instance, and send the request there. This lesson focuses on HTTP clients; gRPC and message brokers have their own name resolution, routing, or load distribution mechanisms.

**Spring Cloud LoadBalancer** provides client-side load balancing for Spring applications. It receives a service ID, retrieves the corresponding list of **ServiceInstance** objects, applies filters or selection policies, and forwards the request to the physical address of the chosen instance. As a result, business code can call **inventory-service** instead of needing to know the IP and port of each replica beforehand.

## 1. Problems When Communicating Directly with a Fixed Address

Suppose **order-service** calls **inventory-service** at **http://10.0.0.21:8080**. This approach is simple when there is only one machine, but it quickly reveals limitations as the system scales:

- **Capacity limit:** one instance must handle all requests, even though more instances could be run.
- **Single point of failure:** if that machine or process stops, every request depending on this address fails.
- **Changing addresses:** upon redeployment, containers or pods may receive different IPs and ports. The configuration of calling services must be updated in sync.
- **Inflexible deployments:** scaling up, scaling down, rolling deployments, or replacing faulty machines all increase endpoint management overhead.
- **Uneven load distribution:** some instances can become overloaded while other instances still have available resources.

A load balancer can be placed on the server or gateway side to distribute requests. However, for service-to-service communication, each calling application can also select an instance itself. This is the **client-side load balancing** approach.

| Approach | Where instance is selected | Characteristics |
| --- | --- | --- |
| Calling a fixed address | No selection step | Easy to start, difficult to scale and handle failures |
| Server-side load balancing | Server-side proxy or load balancer | Client calls a stable endpoint; proxy selects backend |
| Client-side load balancing | Calling application | Client retrieves the instance list and selects the target for each request |

Client-side load balancing does not replace all roles of an API Gateway. A Gateway typically handles ingress traffic into the system, authentication, API-based routing, and edge policies. Spring Cloud LoadBalancer focuses on selecting an instance for calls from a Spring application to a service ID.

## 2. Processing Flow of Spring Cloud LoadBalancer

A service ID is the logical name of a service, for example **inventory-service**. At request time, Spring Cloud LoadBalancer works with service discovery and the HTTP client to find an actual address.

~~~mermaid
flowchart TD
    A["Order Service"] --> B["HTTP client: RestClient / WebClient / OpenFeign"]
    B --> C["Service ID: inventory-service"]
    C --> D["ServiceInstanceListSupplier"]
    D --> E["Fetch instance list from DiscoveryClient"]
    E --> F["Cache, health check, and filters"]
    F --> G["LoadBalancer selects a ServiceInstance"]
    G --> H["Send request to selected host:port"]
    H --> I["Inventory Service instance"]
    G --> J["No suitable instance available"]
    J --> K["Instance selection error returned to caller"]
~~~

The workflow typically proceeds as follows:

1. Application code creates a request to a URL whose host is a service ID, such as **http://inventory-service/api/stock/ABC**.
2. An interceptor or exchange filter integrated with the HTTP client recognizes that the request requires load balancing.
3. LoadBalancer asks **ServiceInstanceListSupplier** to provide the list of instances for **inventory-service**.
4. The supplier retrieves data from service discovery, and may then apply caching, health checks, zone preference, or other filters.
5. LoadBalancer selects an instance according to the configured policy.
6. The HTTP client replaces the service ID with the actual address, for example **http://10.0.0.22:8080/api/stock/ABC**, and sends the request.
7. The result or error is returned to the calling application. Retries and metrics may participate in the request lifecycle depending on configuration.

Two concepts should be distinguished:

- **Service discovery** answers the question: "Which instances of this service currently exist and where are they?"
- **Load balancing** answers the question: "Among the usable instances, which instance will this request go to?"

Discovery provides the input data; LoadBalancer uses that data to select a target. Having discovery does not necessarily mean having load balancing, and a LoadBalancer also needs a source that supplies instances.

## 3. Core Components

### 3.1. Service ID and ServiceInstance

A Service ID is the logical identifier that a client uses in a URL or client declaration. It usually matches the service name registered in the registry, and must be configured consistently between caller and provider.

**ServiceInstance** describes a specific deployment of a service. It typically contains:

- **serviceId:** logical name of the service.
- **host** and **port:** physical address to connect to.
- **secure:** indicates whether the instance uses HTTPS.
- **instanceId:** unique identifier of the deployment instance.
- **metadata:** additional information such as zone, version, or labels for routing.

For example, **inventory-service** can have three instances:

| Service ID | Instance ID | Address |
| --- | --- | --- |
| **inventory-service** | **inventory-1** | **10.0.0.21:8080** |
| **inventory-service** | **inventory-2** | **10.0.0.22:8080** |
| **inventory-service** | **inventory-3** | **10.0.0.23:8080** |

The client only needs to know **inventory-service**. When an instance is replaced, the registry updates the list and the client uses the new list once discovery data is refreshed.

### 3.2. DiscoveryClient

Spring Cloud Commons defines the **DiscoveryClient** and **ReactiveDiscoveryClient** abstractions. Implementations can retrieve data from Eureka, Consul, Zookeeper, or another discovery platform. Applications call the common abstraction instead of depending directly on registry-specific APIs.

In a production environment, the registry typically receives registration info when a service starts and updates status when a service stops or becomes unhealthy. Heartbeat, lease, deregistration, and refresh intervals depend on the specific registry.

If there is no implementation tied to a service registry on the classpath, Spring Cloud can use **SimpleDiscoveryClient**. This is a useful option for local examples or test environments because the instance list is declared in configuration.

Example configuring two local instances:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

**SimpleDiscoveryClient** does not automatically manage process lifecycles like a production registry. When instance addresses or counts change, operators must update the configuration accordingly.

### 3.3. ServiceInstanceListSupplier

**ServiceInstanceListSupplier** provides the list of **ServiceInstance** objects to LoadBalancer. A supplier can fetch data from a discovery client or a custom source, and chain additional processing steps.

A supplier chain may consist of:

1. A supplier that fetches the list from DiscoveryClient.
2. A supplier that caches the list to reduce discovery queries.
3. A supplier that checks health or filters instances by zone.
4. A supplier that filters by hint, metadata, or request requirements.

The order of suppliers matters. For example, cache and health-check suppliers need to be placed in the right position relative to the network-fetching supplier and request filters. When configuring manually, follow the exact order specified in the documentation for the Spring Cloud version in use.

Caching helps reduce registry query overhead, but also introduces a delay when instances are newly added or removed. Consider TTL, the registry's update cycle, and failure detection time to avoid using stale lists.

### 3.4. ReactiveLoadBalancer and Instance Selection Algorithms

Spring Cloud LoadBalancer provides the **ReactiveLoadBalancer** abstraction along with instance selection implementations. The default algorithm is **Round Robin**: consecutive requests are distributed sequentially across the available instance list.

Example with three instances:

| Request | Instance selected by Round Robin |
| --- | --- |
| 1 | **inventory-1** |
| 2 | **inventory-2** |
| 3 | **inventory-3** |
| 4 | **inventory-1** |
| 5 | **inventory-2** |

Spring Cloud also provides **RandomLoadBalancer**, which randomly selects an instance from the list. With appropriate configuration, zone preference, hints, or custom suppliers can also be used to filter the list before selection.

Round Robin does not measure CPU, memory, active request count, or response time of each instance. If one instance has much lower capacity than others, distributing the request count evenly does not guarantee even load. When weighted routing or operational-data-based routing is needed, choose an appropriate supplier/algorithm or build a custom policy.

A dedicated policy can be configured for a service ID using **@LoadBalancerClient**. The example below replaces Round Robin with Random for **inventory-service**:

~~~java
@Configuration(proxyBeanMethods = false)
@LoadBalancerClient(
    name = "inventory-service",
    configuration = InventoryRandomLoadBalancerConfiguration.class
)
class InventoryRandomLoadBalancerRegistration {
}

class InventoryRandomLoadBalancerConfiguration {

    @Bean
    ReactorLoadBalancer<ServiceInstance> randomLoadBalancer(
            Environment environment,
            LoadBalancerClientFactory factory) {

        String serviceId = environment.getProperty(
                LoadBalancerClientFactory.PROPERTY_NAME);

        return new RandomLoadBalancer(
                factory.getLazyProvider(
                        serviceId, ServiceInstanceListSupplier.class),
                serviceId);
    }
}
~~~

The example illustrates the main components; corresponding imports from Spring Cloud and Spring Framework need to be added. The configuration class passed to **@LoadBalancerClient** should reside outside component scan scope or not be registered as a global configuration, otherwise its beans may unexpectedly affect multiple LoadBalancer clients.

Other routing options include:

- **Zone preference:** prefers instances in the same zone to reduce latency and cross-zone traffic. The built-in configuration can be enabled with **spring.cloud.loadbalancer.configurations: zone-preference**.
- **Hint-based routing:** passes a hint to filter instances with matching metadata, for example routing to the group of instances serving a specific API version.
- **Same-instance preference:** prefers the previously selected instance if it is still available.
- **Sticky session:** keeps requests for a user session on one instance based on a session identifier. This approach has client-type limitations and reduces flexibility when an instance fails; only use it when the application genuinely requires it.

Do not use sticky sessions to mask locally stored session state if that state can be moved to a shared store. Stateless services are generally easier to scale and recover.

## 4. Discovery and Health Checks

### 4.1. Discovery Does Not Imply Instant Health Checks

An instance appearing in the registry does not guarantee it can always process requests at call time. The process may be hung, overloaded, lose network connectivity, or still be starting up. The registry may also take some time to notice that an instance has died.

There are three common signal layers:

- **Registration:** the instance has registered and has an address to call.
- **Readiness:** the instance is ready to receive business traffic.
- **Liveness:** the process is alive and does not need to be restarted.

Do not mechanically use liveness in place of readiness. A process that is alive but not yet connected to the database or has not finished loading data should not yet receive business requests.

### 4.2. HealthCheckServiceInstanceListSupplier

Spring Cloud LoadBalancer includes **HealthCheckServiceInstanceListSupplier** to periodically check instances provided by the underlying supplier. The supplier returns only healthy instances when at least one instance passes the check. According to the documented default behavior, if no instance passes, the supplier falls back to returning the retrieved list of instances; therefore, health checks are not a guarantee that every request will always be sent to a healthy instance.

Example configuring health checks for a reactive client:

~~~java
@Configuration(proxyBeanMethods = false)
@LoadBalancerClient(
    name = "inventory-service",
    configuration = InventoryHealthCheckConfiguration.class
)
class InventoryHealthCheckRegistration {
}

class InventoryHealthCheckConfiguration {

    @Bean
    ServiceInstanceListSupplier inventoryServiceInstanceListSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withHealthChecks()
                .build(context);
    }
}
~~~

For a blocking stack, the builder has a **withBlockingHealthChecks()** variant. Choose the variant matching the client type and Spring Cloud version in your application. The Random and health check examples in the two sections are independent configurations; if both are needed for the same service ID, merge the required beans into a single client configuration rather than registering two competing configurations.

Health check timing and path can be configured:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        initial-delay: 5s
        interval: 15s
        path:
          default: /actuator/health/readiness
~~~

The default health check path is **/actuator/health**. If using the default Actuator endpoint, the target service needs **spring-boot-starter-actuator** and the corresponding endpoint must be configured. The path **/actuator/health/readiness** only works if the application has enabled the appropriate readiness health group. Do not expose management endpoints to the Internet without access control.

Scheduled health checks are especially useful when using **SimpleDiscoveryClient** or an instance source that does not provide health status itself. With a service registry that already returns healthy instance statuses, adding a redundant periodic health check layer is usually unnecessary. Adding probes can increase check traffic and put extra pressure on instances.

Health checks also have a detection interval. An instance can fail immediately after the most recent successful probe. Therefore, timeouts, bounded retries, and error handling at the caller are still necessary.

## 5. Integration with HTTP Clients in Spring

### 5.1. Adding Dependencies

Add the Spring Cloud LoadBalancer starter to the application:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
~~~

If using OpenFeign, add the OpenFeign starter:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-openfeign</artifactId>
</dependency>
~~~

Manage versions using the Spring Cloud BOM compatible with the project's Spring Boot version. Do not manually choose a standalone LoadBalancer version if the Spring Cloud release train already manages that dependency.

### 5.2. RestClient

**RestClient** is Spring Framework's synchronous HTTP client, introduced in Spring Framework 6.1. Create a **RestClient.Builder** bean qualified with **@LoadBalanced** so Spring Cloud adds instance selection integration; use a Spring Cloud release train that supports RestClient:

~~~java
@Configuration(proxyBeanMethods = false)
class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Inject that builder into a business client and call using the service ID:

~~~java
@Service
class InventoryClient {

    private final RestClient restClient;

    InventoryClient(@LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    InventoryResponse findBySku(String sku) {
        return restClient.get()
                .uri("http://inventory-service/api/inventory/{sku}", sku)
                .retrieve()
                .body(InventoryResponse.class);
    }
}
~~~

In the URL, **inventory-service** is the service ID. LoadBalancer resolves it to the host and port of the selected instance. If a fixed URL such as **http://localhost:8081** is used, the request no longer needs instance selection by service ID.

### 5.3. WebClient

**WebClient** supports reactive programming. Create a builder with **@LoadBalanced**:

~~~java
@Configuration(proxyBeanMethods = false)
class ReactiveHttpClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Use the builder in a service:

~~~java
@Service
class ReactiveInventoryClient {

    private final WebClient webClient;

    ReactiveInventoryClient(@LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    Mono<InventoryResponse> findBySku(String sku) {
        return webClient.get()
                .uri("http://inventory-service/api/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryResponse.class);
    }
}
~~~

Spring Cloud uses a load-balancer exchange filter for **WebClient**. Keep the reactive types throughout the processing pipeline; avoid calling **.block()** inside a WebFlux request handler because it can occupy the event loop and negate the benefits of the non-blocking model.

### 5.4. OpenFeign

OpenFeign lets you declare an HTTP client using an interface:

~~~java
@EnableFeignClients
@SpringBootApplication
class OrderApplication {
}

@FeignClient(name = "inventory-service")
interface InventoryFeignClient {

    @GetMapping("/api/inventory/{sku}")
    InventoryResponse findBySku(@PathVariable String sku);
}
~~~

When Spring Cloud LoadBalancer is on the classpath, a Feign client can use the service ID in the **name** attribute. For requests to be load balanced, do not declare a fixed URL in **@FeignClient** or configure a separate URL for that client. If a fixed URL is present, Feign calls the URL directly and skips load balancing.

The OpenFeign starter treats Spring Cloud LoadBalancer as an optional dependency. Therefore, **spring-cloud-starter-loadbalancer** must be added explicitly when you want to use this integration.

### 5.5. Which Client to Choose?

| Client | Model | Common Use Cases |
| --- | --- | --- |
| **RestClient** | Synchronous, blocking | Spring MVC applications or simple business flows |
| **WebClient** | Reactive, non-blocking | WebFlux or handling high-concurrency asynchronous I/O |
| **OpenFeign** | Synchronous, interface-declared | Internal clients with a clear HTTP contract wanting to reduce repetitive HTTP call boilerplate |

Multiple client types can be used in the same system, but timeout, retry, tracing, and error handling should be standardized so behavior remains consistent across clients.

## 6. Timeouts and Retries

### 6.1. Why Must Timeouts Be Configured?

Without appropriate timeouts, a request can wait too long when the target instance hangs or the network fails. Waiting threads, connections, and requests will accumulate, exhausting the calling service's resources as well.

Distinguish between:

- **Connection timeout:** maximum time to establish a connection to the instance.
- **Read/response timeout:** time waiting for response data after the connection is established.
- **Overall deadline:** limit on total time for the entire call, including retry attempts.

Timeouts must align with business SLAs. If **order-service** only has 3 seconds to complete a request, you cannot set a 5-second timeout per call to **inventory-service** and expect the overall request to finish in 3 seconds.

Example setting connect timeout and read timeout for **RestClient** using **SimpleClientHttpRequestFactory**:

~~~java
@Bean
@LoadBalanced
RestClient.Builder loadBalancedRestClientBuilder() {
    SimpleClientHttpRequestFactory factory =
            new SimpleClientHttpRequestFactory();
    factory.setConnectTimeout(Duration.ofSeconds(1));
    factory.setReadTimeout(Duration.ofSeconds(2));

    return RestClient.builder().requestFactory(factory);
}
~~~

Example configuring Reactor Netty for **WebClient**:

~~~java
@Bean
@LoadBalanced
WebClient.Builder loadBalancedWebClientBuilder() {
    HttpClient httpClient = HttpClient.create()
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1_000)
            .responseTimeout(Duration.ofSeconds(2));

    return WebClient.builder()
            .clientConnector(new ReactorClientHttpConnector(httpClient));
}
~~~

In this example, **responseTimeout** limits the response wait time at the HTTP client layer. To limit the total time of the entire reactive pipeline, an additional **timeout(Duration)** can be placed on the request publisher.

With OpenFeign, timeouts can be configured per client name:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          inventory-service:
            connectTimeout: 1000
            readTimeout: 2000
~~~

The examples above illustrate how to set timeouts; an actual HTTP request factory or engine may need additional configuration for connection pools, TLS, and connection limits depending on load.

### 6.2. Retries at the LoadBalancer Layer

Retries allow repeating a request when the previous call failed due to a transient error. With load-balanced retries, the next attempt can select a different instance to avoid resending the request to the same failing instance.

Example configuring attempt limits:

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
        retryable-status-codes:
          - 502
          - 503
          - 504
~~~

Retry properties and how they are applied depend on the HTTP client type and Spring Cloud version:

- With **WebClient**, Spring Cloud LoadBalancer supports retries based on Reactor Retry.
- With a blocking stack, the retry mechanism requires the corresponding adapter and retry library; some integrations use Spring Retry.
- With **OpenFeign**, Spring Cloud OpenFeign provides **Retryer.NEVER_RETRY** by default, meaning Feign does not retry automatically. To retry, configure an appropriate **Retryer** or use a retry mechanism at another layer.

Do not enable broad retries for every exception and every HTTP method. A timeout can occur after the server has finished executing the operation while the response was lost. If the client resends an order creation or payment deduction command, the business operation may be executed twice. Only retry safe requests or design operations with an idempotency key so the server recognizes duplicate requests.

A responsible retry policy should:

1. Only retry errors considered transient, such as certain connection errors or HTTP 502, 503, 504.
2. Limit retry counts at both the client layer and LoadBalancer layer to avoid unexpectedly multiplying requests.
3. Prefer a different instance if the previous instance just failed and other instances are available.
4. Use backoff and jitter where appropriate so multiple clients do not retry simultaneously at the exact same time.
5. Stop retrying when the original request's deadline expires.
6. Record retry counts to detect retry storms.

Retries do not replace a circuit breaker. Retries handle occasional transient errors by trying again; a circuit breaker prevents callers from continuing to put load on a dependency that is failing consistently. The two mechanisms solve different problems and should be coordinated within the request's time budget.

## 7. Observing Errors and Performance

When a request fails, determine which step of the flow the error occurred at:

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| Instance not found or “No servers available” error | Wrong service ID, instance not registered, registry unreachable, supplier filtered out entire list | Check service name, registration status, discovery client, cache, health check, and hints |
| Connection refused | Wrong registered host/port, process not listening, or network policy blocking connection | Check instance address, port, container network, firewall, and process status |
| Connect timeout | Slow network path, wrong route, instance unreachable or overloaded | Check network latency, DNS/routes, security groups, and instance resources |
| Read/response timeout | Instance received request but takes too long to process or returns no response | Check processing time, downstream dependencies, thread pools, connection pools, and timeouts |
| HTTP 502/503/504 | Instance or proxy returns bad gateway/service unavailable/timeout error | Cross-check logs at caller, proxy, and target service; check retry policy |
| One instance receives noticeably higher load | Round Robin does not reflect actual capacity, heterogeneous instance list or metadata | Check algorithm, instance count, zones, cache, and actual load |

### 7.1. Spring Cloud LoadBalancer Metrics

Spring Cloud LoadBalancer provides **MicrometerStatsLoadBalancerLifecycle** to record request statistics if a **MeterRegistry** is present. Enable metrics via configuration:

~~~yaml
spring:
  cloud:
    loadbalancer:
      stats:
        micrometer:
          enabled: true
~~~

The main meters include:

| Meter | Meaning |
| --- | --- |
| **loadbalancer.requests.active** | Number of active requests per instance |
| **loadbalancer.requests.success** | Execution duration of requests that completed by returning a response to the HTTP client |
| **loadbalancer.requests.failed** | Execution duration of requests that ended with an exception |
| **loadbalancer.requests.discard** | Number of requests that could not obtain an instance to execute |

Combine these meters with Spring Boot Actuator, Micrometer, and monitoring systems like Prometheus to track trends. If **discard** increases, check discovery, service IDs, and instance filters. If **failed** increases on a specific instance, cross-check with that service's logs and traces.

Metric tags can include the service instance and URI. For endpoints whose paths contain variable IDs, consider **spring.cloud.loadbalancer.stats.include-path: false** to avoid creating too many high-cardinality time series.

### 7.2. Logging and Tracing

Metrics show trends; logs and distributed tracing help find the root cause of a specific request. Propagate a correlation ID or trace context across service-to-service calls. When you need to know which instance a request was sent to, you can log the service ID, instance ID, and target address at the client layer or via a LoadBalancer request transformer.

Do not log tokens, passwords, personal data, or full sensitive payloads. Log only fields sufficient for tracing such as trace ID, service ID, instance ID, HTTP method, route template, status code, duration, and retry count.

## 8. Hands-on Verification

A small test can verify load balancing configuration before deploying to a shared environment:

1. Start two instances of **inventory-service** on two different ports, for example 8081 and 8082.
2. Have each instance return a distinct **instanceId** field in its response so the handling target can be identified.
3. Configure **SimpleDiscoveryClient** with the two URIs and call the service using **http://inventory-service/...** via RestClient or WebClient.
4. Send multiple requests and observe the selected instance. With Round Robin, requests will alternate across the instance list that LoadBalancer receives.
5. Stop one instance, wait for discovery or health checks to update the list, then send more requests and observe the result.
6. Create a slow-responding endpoint to verify connect timeout, read timeout, and deadline behavior.
7. Return HTTP 503 in a controlled manner to test retries, attempt counts, and failover to another instance.
8. Inspect the **success**, **failed**, and **discard** metrics and correlate logs using the trace ID.

When testing retries, use a read endpoint or a test endpoint with an idempotency key. Do not cause real side effects just to test a retry.

## 9. Limitations to Understand Clearly

- Load balancing only selects from the instance list provided by the supplier. If the registry or cache holds stale data, LoadBalancer may select an instance that has already stopped.
- Round Robin distributes by turn, not by CPU, active requests, or latency.
- Periodic health checks have a detection delay and do not guarantee an instance will remain healthy when a request actually arrives.
- Retries can increase load right when the system is degrading. Limit retry counts and total duration.
- Client-side load balancing does not replace timeouts, circuit breakers, bulkheads, rate limits, or business-level resilience.
- If multiple clients use different HTTP stacks, retry and timeout behavior may differ. Check each adapter and test with the project's actual Spring Cloud version.

## 10. References

- [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): instance selection algorithms, suppliers, health checks, retries, metrics, and per-client configuration.
- [Spring Cloud Commons - Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): DiscoveryClient, SimpleDiscoveryClient, RestClient, and WebClient integration.
- [Spring Cloud OpenFeign](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): load balancing integration, Feign client URLs, and default retry behavior.
- [Spring Cloud LoadBalancer configuration properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): list of configuration properties and default values.
