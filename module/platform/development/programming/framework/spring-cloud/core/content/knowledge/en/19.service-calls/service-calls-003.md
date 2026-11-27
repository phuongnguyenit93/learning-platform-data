# Instance Selection, URI Reconstruction, and Request Execution

In microservices systems, applications typically call a service by a logical name such as `inventory-service` rather than hardcoding the hostname and port of a single machine. A service can have multiple instances, each running on a different host/port that may change during deployment, scaling, or failure recovery.

Spring Cloud LoadBalancer handles that call on the client side. It retrieves the instance list from service discovery, selects a `ServiceInstance`, replaces the logical host in the URI with the instance's physical address, and lets the HTTP client send the request to that address. For clients annotated with `@LoadBalanced`, most of this process happens automatically when code calls a URL containing a service ID.

This lesson belongs to the **Service Calls** chapter of the **SPRING_CLOUD_CORE** module. The content walks through the entire lifecycle of a request: preparing the instance list, selecting an instance, reconstructing the URI, executing the HTTP request, handling no-instance scenarios, and verifying the outcome.

## 1. Learning objectives

After this lesson, you can:

- Distinguish a logical service ID from the hostname and port of a service instance.
- Explain the roles of `DiscoveryClient`, `ServiceInstanceListSupplier`, and `ReactiveLoadBalancer`.
- Read the key fields of `ServiceInstance`.
- Describe how load balancing algorithms select an instance from the available list.
- Use `LoadBalancerClient.choose()` to select an instance and `reconstructURI()` to build a physical URI.
- Explain how `@LoadBalanced` integrates with `RestTemplate`, `RestClient`, and `WebClient`.
- Understand why scheme, port, path, query, and URI encoding must be handled when reconstructing URIs.
- Distinguish instance selection from HTTP request execution.
- Identify errors when no instance is available, an instance has stopped, or the instance list is stale in cache.
- Test URI reconstruction and observe which actual instance receives requests.

## 2. Why select instances on the client side?

Suppose the system has an inventory service named `inventory-service`. The registry records three instances:

| Instance | Host | Port | Status |
| --- | --- | ---: | --- |
| `inventory-1` | `10.20.1.11` | 8081 | UP |
| `inventory-2` | `10.20.1.12` | 8081 | UP |
| `inventory-3` | `10.20.1.13` | 8081 | UP |

The order service needs to fetch the product list. If it calls `http://10.20.1.11:8081/api/items` directly, the application is hardcoded to one instance. When that instance is replaced or scaled down, the call fails even though the other two instances are still running.

Instead, the application calls by service ID:

~~~text
http://inventory-service/api/items
~~~

`inventory-service` is a logical name. LoadBalancer retrieves the matching instances, chooses one instance, and translates the URI to an actual address, for example:

~~~text
http://10.20.1.12:8081/api/items
~~~

On the next request, the algorithm can select a different instance. Business code does not need to know the IP list in advance or manage instance rotation manually.

### 2.1. Discovery and load balancing are two related steps

Service discovery answers the question: **which instances of the service currently exist?**

Client-side load balancing answers the question: **which instance should the current request be sent to?**

Spring Cloud LoadBalancer uses a discovery abstraction on the classpath, such as `DiscoveryClient`, to fetch the instance list. Then `ServiceInstanceListSupplier` provides the list for `ReactiveLoadBalancer` to choose an instance.

~~~mermaid
flowchart LR
    A[HTTP client request] --> B[Service ID]
    B --> C[ServiceInstanceListSupplier]
    C --> D[DiscoveryClient]
    D --> E[Available ServiceInstance list]
    E --> F[ReactiveLoadBalancer]
    F --> G[Selected ServiceInstance]
    G --> H[Reconstruct physical URI]
    H --> I[Execute HTTP request]
    I --> J[Remote service instance]
~~~

If the registry has no data or no available instances, LoadBalancer cannot fabricate a valid target address on its own. Having a `DiscoveryClient` bean does not guarantee that a service ID already has running instances.

## 3. What information does ServiceInstance contain?

`ServiceInstance` is an abstraction describing an instance of a service in the discovery system. Commonly used fields:

| Method | Meaning |
| --- | --- |
| `getInstanceId()` | Unique instance ID according to the registry, if provided by the provider |
| `getServiceId()` | Service ID under which the instance is registered |
| `getHost()` | Hostname or IP of the instance |
| `getPort()` | Port on which the instance is listening |
| `isSecure()` | Indicates whether connections to the instance's port use HTTPS |
| `getUri()` | URI of the instance |
| `getMetadata()` | Key/value metadata provided by the registry/provider |
| `getScheme()` | Explicit scheme if provided by the implementation |

Example of an instance:

~~~text
serviceId = inventory-service
instanceId = inventory-2
host       = 10.20.1.12
port       = 8081
secure     = false
metadata   = {zone=zone-a, version=v2}
~~~

This information is sufficient to build a physical endpoint and can be used for instance selection policies such as zone preference or metadata filtering.

### 3.1. ServiceInstance.getUri()

The default implementation `DefaultServiceInstance` constructs a URI based on host, port, and the secure flag. If `isSecure()` is `true`, the default URI uses `https`; if `false`, it uses `http`. When the port is unspecified, default URI construction may use the standard port for the scheme.

Do not assume every provider builds `ServiceInstance` identically. An implementation may provide an explicit scheme or custom metadata. When reconstructing a URI for a request, use `LoadBalancerClient.reconstructURI()` or a load-balanced HTTP client integration instead of string concatenation.

## 4. Preparing Spring Cloud LoadBalancer

Spring Cloud LoadBalancer needs an instance source, usually a DiscoveryClient from a provider such as Eureka or Consul, and the LoadBalancer module.

### 4.1. Dependencies

Add the LoadBalancer starter:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
~~~

The application also needs the service discovery provider dependency if fetching instances from a registry, such as Consul Discovery or Eureka Client. Spring Cloud dependency versions should be managed by a Spring Cloud BOM compatible with the project's Spring Boot version.

### 4.2. Service name configuration example

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    consul:
      host: localhost
      port: 8500
      discovery:
        enabled: true
        register: true
~~~

This is an illustrative configuration for Consul. For Eureka or another provider, use provider-specific properties. What matters for LoadBalancer is that DiscoveryClient must return instances whose service ID matches the logical name used by the client.

### 4.3. Static data for development and testing

If you do not want to run a registry in a local environment, you can use `SimpleDiscoveryClient` with a statically configured instance list:

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

When there is no registry-backed DiscoveryClient, Spring Cloud Commons can use `SimpleDiscoveryClient`. This approach is useful for testing instance selection and URI reconstruction without standing up Eureka/Consul. It does not automatically register instances to a remote registry.

## 5. How does LoadBalancer select an instance?

Spring Cloud LoadBalancer creates a separate LoadBalancer context for each service ID. The context is typically initialized lazily when the first request to that service needs load balancing.

### 5.1. ServiceInstanceListSupplier

`ServiceInstanceListSupplier` supplies the instance list to LoadBalancer. A supplier can:

- Fetch the list from `DiscoveryClient`.
- Read a statically configured list.
- Cache the instance list.
- Filter by zone or metadata.
- Keep only instances verified by health checks.
- Apply request-based preferences or hints.

Suppliers can be chained as delegates. For example, one supplier fetches data from discovery, a caching supplier holds the list, and another supplier filters by zone.

### 5.2. Default algorithm

Spring Cloud LoadBalancer provides `RoundRobinLoadBalancer` and `RandomLoadBalancer`. The current default configuration uses `RoundRobinLoadBalancer`.

With three available instances, round robin can distribute requests sequentially like:

~~~text
Request 1 -> inventory-1
Request 2 -> inventory-2
Request 3 -> inventory-3
Request 4 -> inventory-1
Request 5 -> inventory-2
...
~~~

This is an illustrative model. In real environments, the order may shift when the instance list updates, multiple client processes send requests concurrently, or a supplier filters instances.

Random picks an instance at random from the supplied list. You can change the algorithm via custom LoadBalancer configuration for the whole application or for a specific service ID.

### 5.3. Caching the instance list

Spring Cloud LoadBalancer supports caching the instance list. The current default configuration has a TTL of 35 seconds and an initial capacity of 256. It can be adjusted:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        ttl: 20s
        capacity: 512
~~~

Caching can be disabled:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false
~~~

Caching reduces discovery queries, but can cause the client to retain a stale list for some time after instances change. If the DiscoveryClient provider already caches data, such as Eureka Discovery Client, consider disabling one cache layer to avoid double caching and cumulative update lag.

Do not set the TTL too long if the system needs to react quickly when instances are removed from the registry. Conversely, a TTL that is too short increases discovery query load. Choose based on instance churn rate, registry scale, and operational requirements.

### 5.4. Filtering instances by zone or health

`ZonePreferenceServiceInstanceListSupplier` can prioritize instances in the same zone. The zone can come from DiscoveryClient metadata or the `spring.cloud.loadbalancer.zone` setting.

`HealthCheckServiceInstanceListSupplier` can periodically check instances and prefer returning healthy instances. If no instance passes the health check, the supplier may fall back to the fetched instance list so LoadBalancer still has options. This approach is more useful with static lists such as `SimpleDiscoveryClient`. When using an actual registry, the registry usually already provides health status; avoid unnecessary duplicate health checks.

## 6. Selecting an instance with LoadBalancerClient

`LoadBalancerClient` is a blocking abstraction. It extends `ServiceInstanceChooser` and provides operations for selecting instances, executing requests, and reconstructing URIs.

### 6.1. Calling choose()

~~~java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.LoadBalancerClient;
import org.springframework.stereotype.Service;

@Service
public class InventoryInstanceSelector {

    private final LoadBalancerClient loadBalancerClient;

    public InventoryInstanceSelector(
            LoadBalancerClient loadBalancerClient) {
        this.loadBalancerClient = loadBalancerClient;
    }

    public ServiceInstance chooseInventory() {
        return loadBalancerClient.choose("inventory-service");
    }
}
~~~

`choose(serviceId)` returns the selected instance. If no suitable instance exists, the result can be `null`; callers must handle this case instead of continuing to build a URI.

### 6.2. Inspecting the selected instance

~~~java
ServiceInstance instance =
        loadBalancerClient.choose("inventory-service");

if (instance == null) {
    throw new IllegalStateException(
            "No instance available for inventory-service");
}

System.out.printf(
        "Selected serviceId=%s, instanceId=%s, host=%s, port=%d, secure=%s%n",
        instance.getServiceId(),
        instance.getInstanceId(),
        instance.getHost(),
        instance.getPort(),
        instance.isSecure());
~~~

Do not log metadata containing sensitive information if a provider or application stores credentials in metadata. Logging instance ID, host, and port should only occur within protected observability scopes matching the system's network policies.

## 7. Reconstructing a URI from service ID to physical address

After selecting an instance, the logical host in the URI must be replaced with the instance's host/port. `LoadBalancerClient.reconstructURI(instance, original)` performs that step.

### 7.1. Basic example

Initial URI:

~~~text
http://inventory-service/api/items?status=READY&page=2
~~~

Selected instance:

~~~text
host = 10.20.1.12
port = 8081
secure = false
~~~

Physical URI after reconstruction:

~~~text
http://10.20.1.12:8081/api/items?status=READY&page=2
~~~

The logical host `inventory-service` is replaced by the instance's host. Path and query are preserved so the request reaches the right API with the right parameters.

### 7.2. Using reconstructURI()

~~~java
import java.net.URI;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.LoadBalancerClient;

ServiceInstance instance =
        loadBalancerClient.choose("inventory-service");

if (instance == null) {
    throw new IllegalStateException(
            "No instance available for inventory-service");
}

URI logicalUri = URI.create(
        "http://inventory-service/api/items?status=READY&page=2");

URI physicalUri =
        loadBalancerClient.reconstructURI(instance, logicalUri);

System.out.println("Physical URI selected: " + physicalUri);
~~~

`reconstructURI()` uses `ServiceInstance` info to replace host and port. Scheme handling also considers any scheme provided by the instance and its secure status. If the instance provides an explicit scheme, that scheme takes precedence. Otherwise, LoadBalancer uses the original scheme or defaults to `http`; when the instance requires security, a corresponding non-secure scheme like `http` can be upgraded to `https`.

### 7.3. Default ports

If the instance has a valid port, the URI uses that port. If no port is provided, the current URI implementation may use the standard port for the scheme, such as `443` for `https` or `80` for `http`.

In real service registration, always provide an explicit port to avoid relying on a default port that does not match the application's listener configuration.

### 7.4. Preserving path, query, and fragment

Example:

~~~text
Logical URI:
http://inventory-service/api/items/42?expand=warehouse&sort=name#details

Physical URI:
http://10.20.1.12:8081/api/items/42?expand=warehouse&sort=name#details
~~~

Host and port are replaced according to the instance; the remainder of the URI is preserved during reconstruction. For already-encoded paths/queries, the implementation checks encoding state before building the URI to avoid double-encoding already encoded data.

Do not concatenate strings manually like:

~~~java
String url = "http://" + instance.getHost()
        + ":" + instance.getPort()
        + originalUri.getPath();
~~~

This approach easily drops query strings, fragments, schemes, default ports, IPv6 characters, or encoding state. Use `reconstructURI()` so Spring Cloud handles URI components properly.

### 7.5. HTTPS and secure ServiceInstance

Suppose an instance is registered with `secure=true`:

~~~text
Logical URI:
http://inventory-service/api/items

Instance:
host = inventory.internal
port = 8443
secure = true

Physical URI:
https://inventory.internal:8443/api/items
~~~

The HTTPS address depends on the instance's scheme/secure info. If the service uses TLS, the server certificate must be valid for the hostname the client connects to. If the registry advertises an IP while the certificate only contains a DNS name, TLS hostname verification may fail. Register an appropriate hostname or configure the service endpoint/certificate consistently; do not disable certificate verification to mask identity errors.

## 8. Manually executing a request after selecting an instance

Selecting an instance and reconstructing a URI only produce the destination address. An HTTP client still has to send the request to that URI.

Example using Spring `RestClient` directly:

~~~java
import java.net.URI;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.LoadBalancerClient;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class ManualInventoryCaller {

    private final LoadBalancerClient loadBalancerClient;
    private final RestClient restClient;

    public ManualInventoryCaller(
            LoadBalancerClient loadBalancerClient) {
        this.loadBalancerClient = loadBalancerClient;
        this.restClient = RestClient.create();
    }

    public String getItems() {
        ServiceInstance instance =
                loadBalancerClient.choose("inventory-service");

        if (instance == null) {
            throw new IllegalStateException(
                    "No instance available for inventory-service");
        }

        URI logicalUri = URI.create(
                "http://inventory-service/api/items");

        URI physicalUri =
                loadBalancerClient.reconstructURI(instance, logicalUri);

        return restClient.get()
                .uri(physicalUri)
                .retrieve()
                .body(String.class);
    }
}
~~~

In this example, `RestClient` is a regular client, not marked with `@LoadBalanced`, because the code already selects an instance and reconstructs the physical URI manually. Both reconstructing the URI manually and using a load-balanced client on the same request can cause load balancing to run twice or lose the right service ID for selection.

### 8.1. The gap between selection and invocation

When code manually calls `choose()` and then sends the request, the instance may be deregistered or stop running in the window between the two operations. Therefore, successful selection does not guarantee the connection will succeed.

If you need LoadBalancer's lifecycle, metrics, or retry integration, use `LoadBalancerClient.execute()` or supported HTTP client integrations rather than managing the entire flow yourself. When calling an HTTP client manually, the application must handle timeouts, connection errors, retries, and observability itself.

### 8.2. Letting LoadBalancer select an instance and invoke the execute() callback

`LoadBalancerClient.execute(serviceId, request)` picks an instance for the service and then invokes the callback with the selected `ServiceInstance`. The callback can reconstruct the URI and send the HTTP request:

~~~java
import java.io.IOException;
import java.net.URI;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.LoadBalancerClient;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class ManagedInventoryCaller {

    private final LoadBalancerClient loadBalancerClient;
    private final RestClient restClient = RestClient.create();

    public ManagedInventoryCaller(LoadBalancerClient loadBalancerClient) {
        this.loadBalancerClient = loadBalancerClient;
    }

    public String getItems() throws IOException {
        URI logicalUri = URI.create(
                "http://inventory-service/api/items");

        return loadBalancerClient.execute(
                "inventory-service",
                (ServiceInstance instance) -> {
                    URI physicalUri = loadBalancerClient.reconstructURI(
                            instance, logicalUri);

                    return restClient.get()
                            .uri(physicalUri)
                            .retrieve()
                            .body(String.class);
                });
    }
}
~~~

This callback allows LoadBalancer to wrap request execution with the corresponding lifecycle and metrics. The application still needs to handle exceptions, timeouts, and retries according to business policy. `execute()` does not make the selected instance infallible; the connection can still fail after selection.

## 9. Automatic execution with @LoadBalanced

In most applications, there is no need to call `choose()` and `reconstructURI()` manually. You can annotate the HTTP client bean with `@LoadBalanced`; Spring Cloud attaches the corresponding interceptor or filter.

`@LoadBalanced` is a qualifier used to mark a `RestTemplate`, `RestClient.Builder`, or `WebClient.Builder` that needs to use LoadBalancer.

### 9.1. RestTemplate

Bean declaration:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate loadBalancedRestTemplate() {
        return new RestTemplate();
    }
}
~~~

Usage:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
public class InventoryClient {

    private final RestTemplate restTemplate;

    public InventoryClient(
            @LoadBalanced RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public String getItems() {
        return restTemplate.getForObject(
                "http://inventory-service/api/items",
                String.class);
    }
}
~~~

The URI uses the service ID as its host. The LoadBalancer interceptor extracts the service ID, chooses an instance, reconstructs the URI, and routes the request to the selected instance.

Spring Boot does not automatically create a load-balanced `RestTemplate` for every application. The application must declare the bean and attach the `@LoadBalanced` qualifier.

### 9.2. Distinguishing regular and load-balanced RestTemplate beans

You may need both a client calling fixed hosts and a client calling service IDs:

~~~java
import org.springframework.context.annotation.Primary;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate loadBalancedRestTemplate() {
        return new RestTemplate();
    }

    @Bean
    @Primary
    RestTemplate directRestTemplate() {
        return new RestTemplate();
    }
}
~~~

Injecting the right bean:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.web.client.RestTemplate;

public class OrderClient {

    private final RestTemplate directRestTemplate;
    private final RestTemplate loadBalancedRestTemplate;

    public OrderClient(
            RestTemplate directRestTemplate,
            @LoadBalanced RestTemplate loadBalancedRestTemplate) {
        this.directRestTemplate = directRestTemplate;
        this.loadBalancedRestTemplate = loadBalancedRestTemplate;
    }
}
~~~

`directRestTemplate` uses physical URLs like `https://partner.example.com`. `loadBalancedRestTemplate` uses logical URLs like `http://inventory-service`. `@Primary` helps Spring pick the default bean when multiple beans of the same type exist and an injection point does not specify a qualifier.

### 9.3. RestClient

With Spring `RestClient`, annotate the builder:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class RestClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Usage:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class InventoryRestClient {

    private final RestClient restClient;

    public InventoryRestClient(
            @LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    public String getItems() {
        return restClient.get()
                .uri("http://inventory-service/api/items")
                .retrieve()
                .body(String.class);
    }
}
~~~

LoadBalancer integrates with `RestClient` via the blocking client. If the application also has a regular builder, use qualifiers and `@Primary` to avoid injecting the wrong builder.

### 9.4. WebClient

With WebFlux, annotate `WebClient.Builder`:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class WebClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Usage:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import reactor.core.publisher.Mono;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

@Service
public class ReactiveInventoryClient {

    private final WebClient webClient;

    public ReactiveInventoryClient(
            @LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    public Mono<String> getItems() {
        return webClient.get()
                .uri("http://inventory-service/api/items")
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

With `WebClient`, Spring Cloud uses `ReactiveLoadBalancer` and an exchange filter function. Requests are processed under the reactive model; there is no need to block to select an instance.

### 9.5. Comparing the three HTTP clients

| Client | Integration mechanism | Execution API | Best fit |
| --- | --- | --- | --- |
| `RestTemplate` | LoadBalancer interceptor | Blocking | Existing Spring MVC applications |
| `RestClient` | LoadBalancer interceptor | Blocking | Modern synchronous HTTP client |
| `WebClient` | LoadBalancer exchange filter | Reactive | Spring WebFlux or reactive processing |

All of these clients can use a service ID in the URI. Choose a client based on your application's programming model, avoiding blocking a reactive pipeline just to make a service call.

## 10. How does a request flow through LoadBalancer?

For a request from a `RestTemplate` or `RestClient` annotated with `@LoadBalanced`, the high-level flow is:

1. Code invokes the HTTP client using a logical URI, for example `http://inventory-service/api/items`.
2. The interceptor extracts the host from the URI as the service ID.
3. LoadBalancer asks `ServiceInstanceListSupplier` to provide an instance list.
4. The supplier fetches the list from discovery or cache, then applies configured filters.
5. `ReactiveLoadBalancer` selects a `ServiceInstance`.
6. `BlockingLoadBalancerClient` reconstructs the physical URI with the instance's host, port, and scheme.
7. The request is passed to the HTTP transport to send.
8. The response or exception is returned to the caller; LoadBalancer lifecycle/metrics can record the result.

With `WebClient`, similar steps are coordinated along the reactive pipeline without using a blocking client underneath.

~~~mermaid
sequenceDiagram
    participant Code as Application code
    participant Http as @LoadBalanced HTTP client
    participant LB as Spring Cloud LoadBalancer
    participant Supplier as ServiceInstanceListSupplier
    participant Discovery as DiscoveryClient
    participant Instance as Selected service instance

    Code->>Http: GET http://inventory-service/api/items
    Http->>LB: Resolve service ID inventory-service
    LB->>Supplier: Get available instances
    Supplier->>Discovery: Query service instances
    Discovery-->>Supplier: Instance list
    Supplier-->>LB: Filtered instance list
    LB->>LB: Choose one ServiceInstance
    LB->>LB: Reconstruct physical URI
    LB->>Instance: Execute GET /api/items
    Instance-->>LB: HTTP response
    LB-->>Http: Return response
    Http-->>Code: Decode response body
~~~

## 11. Request transformers: adding selected instance information

Some systems need to attach the selected instance ID or metadata in an HTTP header. Spring Cloud LoadBalancer provides:

- `LoadBalancerRequestTransformer` for `RestTemplate` and `RestClient`.
- `LoadBalancerClientRequestTransformer` for `WebClient`.

Example adding an `X-InstanceId` header:

~~~java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.LoadBalancerRequestTransformer;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpRequest;
import org.springframework.http.client.support.HttpRequestWrapper;

@Bean
LoadBalancerRequestTransformer instanceHeaderTransformer() {
    return (request, instance) -> new HttpRequestWrapper(request) {
        @Override
        public HttpHeaders getHeaders() {
            HttpHeaders headers = new HttpHeaders();
            headers.putAll(super.getHeaders());

            if (instance != null && instance.getInstanceId() != null) {
                headers.add("X-InstanceId", instance.getInstanceId());
            }

            return headers;
        }
    };
}
~~~

With WebClient:

~~~java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.LoadBalancerClientRequestTransformer;
import org.springframework.context.annotation.Bean;
import org.springframework.web.reactive.function.client.ClientRequest;

@Bean
LoadBalancerClientRequestTransformer instanceHeaderTransformer() {
    return (request, instance) -> {
        ClientRequest.Builder builder = ClientRequest.from(request);
        if (instance != null && instance.getInstanceId() != null) {
            builder.header("X-InstanceId", instance.getInstanceId());
        }
        return builder.build();
    };
}
~~~

Transformers are applied according to bean order. This header is useful for tracing, logging, or diagnosing which instance received a request. Do not use it as an authentication mechanism; callers can spoof headers without a dedicated security layer.

## 12. When no instance exists or an instance is unreachable

### 12.1. No instance found

If the instance list is empty, LoadBalancer cannot choose a target. With the manual API, `choose()` may return `null`; code must stop before calling `reconstructURI()`.

With load-balanced HTTP clients, requests usually fail because no instance is found. When troubleshooting, check:

- Whether the service ID in the URI matches the registered ID.
- Whether DiscoveryClient returns any instances.
- Whether instances are marked DOWN or OUT_OF_SERVICE.
- Whether the supplier filtered out all instances due to zone, hint, or health check.
- Whether the instance list cache is holding stale data.

### 12.2. Instance exists but connection fails

The registry may still return an instance that recently crashed or has not yet been deregistered. Selecting an instance does not mean the TCP/TLS or HTTP request will succeed.

Check:

- Whether host/port are reachable from the caller's network namespace.
- Whether security groups, firewalls, NetworkPolicies, and routing allow the connection.
- Whether the instance is listening on the expected port.
- Whether HTTP/HTTPS scheme matches the listener.
- Whether the certificate and hostname verification are valid.
- Whether connection and read timeouts are appropriate.

### 12.3. Retries do not replace selecting the right instance

Retry can choose a different instance if configured and alternative instances exist. However, retries must be designed according to request type:

- GET requests or idempotent operations are usually safer to retry.
- POST requests creating orders, payments, or writing data can execute twice if the server processed the request but the response was lost.
- Idempotency keys, deduplication, or transaction semantics are needed before retrying operations with side effects.

Do not assume every HTTP error is automatically retried. Retry configuration, retried exceptions/status codes, and attempt counts depend on the version, client type, and LoadBalancer configuration.

## 13. Advanced configuration per service ID

Spring Cloud LoadBalancer supports per-service configuration. For example, you can prefer a zone or use a different algorithm for one service without affecting others.

### 13.1. Dedicated LoadBalancer client

You can use `@LoadBalancerClient` to specify configuration for a service ID:

~~~java
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.context.annotation.Configuration;

@Configuration
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerConfiguration.class)
public class LoadBalancerConfiguration {
}
~~~

`InventoryLoadBalancerConfiguration` defines LoadBalancer beans specific to `inventory-service`. Do not place this custom configuration class within regular component-scan scope if doing so would apply the beans outside the intended service ID. Follow the `@LoadBalancerClient` guidance in the release train you are using.

### 13.2. Zone preference

If instance metadata includes a zone:

~~~text
inventory-1 metadata.zone = zone-a
inventory-2 metadata.zone = zone-a
inventory-3 metadata.zone = zone-b
~~~

`ZonePreferenceServiceInstanceListSupplier` can prefer instances in the caller's zone. When no instance is in the same zone, the supplier can fall back to the original list so LoadBalancer still has choices.

### 13.3. Configuration per client ID

Some properties can be set globally as defaults or per service ID:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        ttl: 30s
      clients:
        inventory-service:
          health-check:
            interval: 15s
        pricing-service:
          health-check:
            interval: 45s
~~~

Specific supported properties depend on the supplier type and Spring Cloud LoadBalancer version. Not every global property can be overridden per client ID.

## 14. Testing instance selection and URI reconstruction

### 14.1. Unit tests for reconstructURI

You can test URI reconstruction without running a registry:

~~~java
import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.LoadBalancerUriTools;

import static org.assertj.core.api.Assertions.assertThat;

class LoadBalancerUriToolsTest {

    @Test
    void replacesLogicalHostAndKeepsPathAndQuery() {
        ServiceInstance instance = new DefaultServiceInstance(
                "inventory-2",
                "inventory-service",
                "10.20.1.12",
                8081,
                false);

        URI original = URI.create(
                "http://inventory-service/api/items?status=READY&page=2");

        URI reconstructed =
                LoadBalancerUriTools.reconstructURI(instance, original);

        assertThat(reconstructed).isEqualTo(URI.create(
                "http://10.20.1.12:8081/api/items?status=READY&page=2"));
    }

    @Test
    void upgradesHttpToHttpsForSecureInstance() {
        ServiceInstance instance = new DefaultServiceInstance(
                "inventory-secure",
                "inventory-service",
                "inventory.internal",
                8443,
                true);

        URI original = URI.create(
                "http://inventory-service/api/items");

        URI reconstructed =
                LoadBalancerUriTools.reconstructURI(instance, original);

        assertThat(reconstructed).isEqualTo(URI.create(
                "https://inventory.internal:8443/api/items"));
    }
}
~~~

These two tests confirm that the logical host is replaced with the instance host, path/query are preserved, and the scheme is upgraded to HTTPS when the instance requires security.

### 14.2. Testing with SimpleDiscoveryClient

In an integration test, configure two static instances:

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

Then use `@LoadBalanced RestTemplate`, `RestClient.Builder`, or `WebClient.Builder` to call `http://inventory-service/...`. You can start two HTTP test servers on two different ports; each server returns its instance name to observe where requests were routed.

### 14.3. Essential test cases

| Test case | What to verify |
| --- | --- |
| Single instance | Request is sent to the exact host/port |
| Multiple instances with round robin | Consecutive requests are distributed per the default algorithm |
| Empty instance list | Request fails clearly without constructing an invalid URI |
| Secure instance | Physical URI scheme uses HTTPS appropriately |
| Query with encoded characters | Query is not double-encoded or corrupted |
| Instance removed from registry | List updates according to cache/refresh policy |
| Two HTTP client beans | `@LoadBalanced` client uses service ID; regular client uses physical URL |
| Timeout or connection refused | Error is recorded; retries happen only as configured |

## 15. Troubleshooting

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| `UnknownHostException` with the service ID name | HTTP client is not load-balanced or LoadBalancer starter is missing | Check `@LoadBalanced`, dependencies, and interceptor/filter |
| No instance found | Wrong service ID or DiscoveryClient returns an empty list | Check registry and `getInstances(serviceId)` |
| Physical URI uses wrong host/port | Provider registration contains the wrong endpoint | Check `ServiceInstance.getHost()`, `getPort()`, and metadata |
| Request uses HTTP while service requires HTTPS | Incorrect scheme/secure metadata on the instance | Check `isSecure()`, `getScheme()`, and listener |
| Query parameters altered | URI built via string concatenation or encoded multiple times | Use a URI builder and `reconstructURI()` |
| Requests always hit one instance | Only one instance in supplier, stale cache, or sticky custom policy | Check instance list, cache TTL, and supplier |
| Requests still hit a shut-down instance | Discovery/cache not yet updated or health state unchanged | Check deregistration, TTL, and health-check policy |
| Cannot inject RestTemplate | Multiple beans or incompatible proxy type | Use `@LoadBalanced`, `@Primary`, `RestOperations`, or appropriate proxy configuration |
| Test cannot reach local instance | HTTP test server not started or wrong port | Check ports and `SimpleDiscoveryClient` list |

### 15.1. Diagnostic workflow

1. Identify the service ID in the logical URI.
2. Call DiscoveryClient or inspect the registry to retrieve the instance list.
3. Print the service ID, instance ID, host, port, secure flag, and relevant metadata.
4. Verify the supplier is not inadvertently filtering out all instances.
5. Inspect the URI after `reconstructURI()`.
6. Check DNS/routing/TLS from the actual runtime environment of the caller.
7. Inspect HTTP status, exceptions, timeouts, and retry logs.
8. Cross-reference cache TTL against the timestamp when instances changed.

## 16. Workflow for implementing a service call

When implementing a service call in an application:

1. Verify service discovery returns the right service ID and instances.
2. Add the Spring Cloud LoadBalancer starter and appropriate discovery provider.
3. Choose `RestTemplate`, `RestClient`, or `WebClient` according to the blocking/reactive model.
4. Annotate the builder/client with `@LoadBalanced`.
5. Call the URL using a properly formatted service ID, path, and query.
6. Verify the scheme, host, and port advertised by instances.
7. Configure timeouts and retries suited to business semantics.
8. Monitor instance IDs, request outcomes, and metrics.
9. Test when instances are added/removed, lose connectivity, or switch to HTTPS.

If step-by-step control is required, use `LoadBalancerClient.choose()` and `reconstructURI()`. For ordinary service calls, prefer `@LoadBalanced` integration so LoadBalancer handles instance selection, URI reconstruction, and request execution.

## 17. Summary

A service call in Spring Cloud starts with a logical service ID. `ServiceInstanceListSupplier` fetches the instance list from discovery or static configuration, `ReactiveLoadBalancer` selects an instance, and the URI is reconstructed to replace the logical host with the physical host/port. `ServiceInstance` provides details such as instance ID, host, port, secure flag, scheme, and metadata.

`LoadBalancerClient.choose()` enables manual instance selection; `reconstructURI()` builds a physical URI from a logical URI and the selected instance. For HTTP clients marked with `@LoadBalanced`, Spring Cloud integrates interceptors or reactive filters to perform these steps automatically when the application sends requests.

Selecting an instance does not guarantee the connection will succeed. You must verify the service ID, instance list, scheme, network, TLS, timeouts, caching, and retries. Once those steps are observable and tested, the application can call services by logical name without hardcoding individual instance endpoints.

## References

- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): `RestTemplate`, `RestClient`, `WebClient` integrations, `@LoadBalanced`, and service ID URIs.
- [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): instance selection algorithms, suppliers, caching, zone preference, health checks, retries, and request transformation.
- [LoadBalancerClient.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/loadbalancer/LoadBalancerClient.java): `choose`, `execute`, and `reconstructURI` contracts.
- [ServiceInstance.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/ServiceInstance.java): instance details and default URI construction.
- [LoadBalancerUriTools.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/loadbalancer/LoadBalancerUriTools.java): host/port replacement, scheme resolution, default ports, and preserving encoded URIs.
- [Spring Cloud LoadBalancer configuration properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): cache, retry, health check, and per-client-ID properties.

Cross-check behaviors against your project's Spring Cloud release train and Spring Framework version. Discovery providers, HTTP client integrations, caching, and retries may differ across versions.