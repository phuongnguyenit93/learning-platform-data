# Declaring Multiple Instances Using the simple.instances Property

Not every application needs a registry server such as Eureka or Consul. For local environments, integration tests, or a small system with a stable endpoint list, Spring Cloud Commons provides `SimpleDiscoveryClient`. This client reads the list of service instances directly from the application's configuration via the `spring.cloud.discovery.client.simple.instances` property.

You can declare multiple addresses for the same service ID, as well as multiple different services in a single YAML file. The application still uses the `DiscoveryClient` API and can combine it with Spring Cloud LoadBalancer to call services by logical name. This lesson walks through the `simple.instances` structure, how each element maps to a `ServiceInstance`, how to use it, and the limitations of static discovery.

## 1. How does SimpleDiscoveryClient work?

`SimpleDiscoveryClient` is an implementation of `DiscoveryClient` in Spring Cloud Commons. Instead of sending queries to a registry server, it reads the instance list from configuration that Spring Boot binds into `SimpleDiscoveryProperties`.

Two main operations:

- `getServices()` returns the service IDs declared in the `instances` map.
- `getInstances(serviceId)` returns the list of instances corresponding to that service ID. If the service ID does not exist, an empty list is returned.

```mermaid
flowchart TD
    YAML[application.yml]
    PROP[SimpleDiscoveryProperties]
    CLIENT[SimpleDiscoveryClient]
    API[DiscoveryClient]
    LB[Spring Cloud LoadBalancer]
    APP[Consumer application]

    YAML -->|Bind simple.instances| PROP
    PROP --> CLIENT
    APP -->|getInstances(serviceId)| API
    API --> CLIENT
    CLIENT -->|List ServiceInstance| API
    API --> APP
    APP -->|Load-balanced request| LB
```

Spring Cloud Commons auto-configures `SimpleDiscoveryClient` when no `DiscoveryClient` backed by a real service registry is on the classpath. If the application includes a Eureka or Consul starter, the corresponding implementation will be used according to the project's discovery configuration; do not assume `simple.instances` will override a registry server just because you declared these values.

`SimpleDiscoveryClient` does not start the declared services. It only provides address information so consumers can look up and call instances already running elsewhere.

## 2. Structure of simple.instances

The full property path:

```text
spring.cloud.discovery.client.simple.instances
```

This is a map:

```text
service ID -> list of instances
```

Each list element represents one service instance. The indexed property form looks like:

```text
spring.cloud.discovery.client.simple.instances.<service-id>[<index>].uri=<instance-uri>
```

Where:

- `<service-id>` is the logical name of the service that consumers will query, for example `inventory-service`.
- `<index>` is the position of the instance in the list, starting from `0`.
- `uri` is the URI of the instance, including scheme, hostname or IP, and port.

Example declaring two instances for `inventory-service`:

```properties
spring.cloud.discovery.client.simple.instances.inventory-service[0].uri=http://inventory-a:8081
spring.cloud.discovery.client.simple.instances.inventory-service[1].uri=http://inventory-b:8081
```

Those two lines create one service ID `inventory-service` with two addresses. The indices `[0]` and `[1]` are list element indices, not ports or instance IDs.

## 3. Declaring multiple instances in application.yml

In YAML, the list structure is usually easier to read than indexed properties. For example, a consumer needs to call two services, each with multiple instances:

```yaml
spring:
  application:
    name: order-consumer
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://inventory-a:8081
              - uri: http://inventory-b:8081
              - uri: http://inventory-c:8081
            payment-service:
              - uri: https://payment-a:8443
              - uri: https://payment-b:8443
```

Resulting configuration:

| Service ID | Instance Count | URI |
| --- | ---: | --- |
| `inventory-service` | 3 | `http://inventory-a:8081`, `http://inventory-b:8081`, `http://inventory-c:8081` |
| `payment-service` | 2 | `https://payment-a:8443`, `https://payment-b:8443` |

Instances belonging to the same service ID are grouped into the same list. A consumer calling `getInstances("inventory-service")` receives three instances; calling `getInstances("payment-service")` receives two instances.

### 3.1. Meaning of the URI

Spring Cloud parses the URI to extract the instance's scheme, host, and port:

| URI | Scheme | Host | Port | Secure |
| --- | --- | --- | ---: | --- |
| `http://inventory-a:8081` | `http` | `inventory-a` | 8081 | `false` |
| `https://payment-a:8443` | `https` | `payment-a` | 8443 | `true` |

A URI with the `https` scheme marks the instance as using a secure connection. Declare the exact scheme and port on which the service actually listens. Do not use a web UI or API Gateway URL if the consumer needs to call each instance directly.

### 3.2. Declaring metadata per instance

Each instance can carry key/value metadata. Metadata is useful when the LoadBalancer or application logic needs to distinguish deployment zones, versions, or processing groups:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://inventory-a:8081
                metadata:
                  zone: zone-a
                  version: v1
              - uri: http://inventory-b:8081
                metadata:
                  zone: zone-b
                  version: v2
```

When read via `ServiceInstance`, metadata can be accessed with `instance.getMetadata()`. Metadata is purely descriptive information; filtering by `zone`, `version`, or another key requires a corresponding supplier or LoadBalancer logic. Merely declaring metadata does not automatically change the instance selection algorithm.

## 4. Adding required dependencies

`SimpleDiscoveryClient` belongs to Spring Cloud Commons. If the application needs to call services by logical name and let Spring Cloud pick the instance address, add Spring Cloud LoadBalancer:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

Manage the Spring Cloud version using a BOM compatible with your project's Spring Boot version. Do not assign an independent version to the starter if the project already uses dependency management.

If you only want to call `DiscoveryClient.getInstances()` to inspect the address list, creating a load-balanced HTTP client is not strictly necessary. If you want to use `@LoadBalanced RestTemplate`, `RestClient`, or `WebClient`, Spring Cloud LoadBalancer must be on the classpath and the corresponding client configured.

## 5. Using DiscoveryClient to read the list

Example injecting `DiscoveryClient` and retrieving `inventory-service` instances:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InventoryDiscoveryController {

    private final DiscoveryClient discoveryClient;

    public InventoryDiscoveryController(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    @GetMapping("/discovery/inventory")
    public List<String> getInventoryInstances() {
        return discoveryClient.getInstances("inventory-service")
                .stream()
                .map(instance -> instance.getUri().toString())
                .toList();
    }
}
```

For Java versions prior to 16, you can replace `.toList()` with `.collect(Collectors.toList())` and import `java.util.stream.Collectors`.

You can also view the list of service IDs:

```java
List<String> serviceIds = discoveryClient.getServices();
```

With the YAML example above, the list contains the IDs `inventory-service` and `payment-service`. If you query an undeclared service ID, `getInstances()` returns an empty list; the consumer must handle the case where no instances exist.

## 6. Calling multiple instances with Spring Cloud LoadBalancer

When you want the application to call a service by logical name rather than selecting host/port manually, create an HTTP client annotated with `@LoadBalanced`.

Example with `RestTemplate`:

```java
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
```

The consumer can call:

```java
String result = restTemplate.getForObject(
        "http://inventory-service/api/items",
        String.class
);
```

Spring Cloud LoadBalancer uses `inventory-service` as the service ID, requests the instance list from `DiscoveryClient`, selects one instance, and translates the logical URI into a real address, such as `http://inventory-b:8081/api/items`.

The default LoadBalancer typically uses round-robin. When multiple instances exist, consecutive requests are distributed across the candidate list according to the configured algorithm. The list declared in `simple.instances` only supplies the candidates; it does not perform load balancing by itself if requests use a plain HTTP client without LoadBalancer integration.

## 7. Verifying bound configuration

You can verify directly with `DiscoveryClient` or set a breakpoint in the application. Here is an example startup check:

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.cloud.client.discovery.DiscoveryClient;

@Configuration
public class DiscoveryDiagnostics {

    @Bean
    ApplicationRunner printDiscoveredServices(DiscoveryClient discoveryClient) {
        return args -> {
            System.out.println("Services: " + discoveryClient.getServices());

            discoveryClient.getInstances("inventory-service")
                    .forEach(instance -> System.out.printf(
                            "service=%s uri=%s metadata=%s%n",
                            instance.getServiceId(),
                            instance.getUri(),
                            instance.getMetadata()
                    ));
        };
    }
}
```

The expected output is the three instances of `inventory-service` with their respective URIs and metadata. If the list is empty, check the service ID name, YAML structure, and the conditions for `SimpleDiscoveryClient` auto-configuration.

You should not keep logs that dump every endpoint in production if internal host details are not meant for general log readers. The runner snippet above is only suitable for demonstration or diagnostics in a development environment.

## 8. Health checking static instances

`SimpleDiscoveryClient` reads addresses from configuration. It does not send heartbeats to a registry, has no registry-managed health state, and does not automatically remove an instance when the target process stops. If three URIs are declared, discovery can still return all three URIs even when one endpoint is no longer running.

For a small number of instances, Spring Cloud LoadBalancer provides `HealthCheckServiceInstanceListSupplier` to periodically check the addresses supplied by the underlying supplier. Example builder configuration for the reactive stack:

```java
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

public class InventoryLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventoryServiceInstanceListSupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withHealthChecks()
                .build(context);
    }
}
```

Associate the configuration with the service ID to be checked:

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;

@SpringBootApplication
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerConfiguration.class
)
public class InventoryConsumerApplication {
    // main method
}
```

Keep `InventoryLoadBalancerConfiguration` outside component scan scope or omit `@Configuration` on that class so the bean is only applied within the corresponding LoadBalancer context. For the blocking stack, use `withBlockingHealthChecks()` according to your Spring Cloud LoadBalancer version.

The default health check path is usually `/actuator/health`. You can configure a custom path for a service:

```yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        path:
          inventory-service: /actuator/health/readiness
```

Only use `/actuator/health/readiness` when the target application actually exposes the readiness endpoint. LoadBalancer health checks are a consumer-side check layer; they do not turn a static list into a dynamic registry and do not replace Eureka or Consul health checks when using a real registry.

## 9. Comparing simple.instances with a service registry

| Capability | `SimpleDiscoveryClient` | Eureka / Consul |
| --- | --- | --- |
| Instance source | Configuration in application properties/YAML. | Registry server storing registrations from services/agents. |
| Adding an instance | Edit configuration. | Instance registers via client/agent or API. |
| Detecting stopped instances | Not detected automatically by a registry; LoadBalancer health checks can be added. | Uses heartbeats, leases, or health checks depending on the registry. |
| List synchronization | Follows the configuration bound in the application. | Follows the registry client's update/cache mechanism. |
| Required infrastructure | No registry server needed. | Requires a running registry server or registry cluster. |
| Suitable scenarios | Local, testing, mock endpoints, small and stable systems. | Dynamic microservices, autoscaling, multi-environment, and distributed operational needs. |

Key point: `simple.instances` is a configuration list for discovery, not a dynamic registration mechanism. When a new replica is added, consumer applications do not learn that address automatically until configuration is updated and reloaded.

## 10. Common errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `getInstances("inventory-service")` returns an empty list | Wrong service ID, wrong YAML indentation level, or list indices failed to bind | Cross-check keys under `simple.instances`, use YAML list syntax or indices starting at `[0]`. |
| `simple.instances` is declared but the client does not return the expected list | A Eureka/Consul starter is providing a registry-backed DiscoveryClient | Check the dependency tree and which DiscoveryClient implementation is active. |
| Calling `http://inventory-service/...` fails with a DNS error | HTTP client lacks `@LoadBalanced` or LoadBalancer starter is missing | Add `spring-cloud-starter-loadbalancer` and define a client bean annotated with `@LoadBalanced`. |
| A URI works on the host but fails inside Docker | Hostname only resolves from the host or `localhost` is used in the wrong network namespace | Use a DNS/service name reachable from the consumer container. |
| An HTTPS instance is called over HTTP | URI declared with wrong scheme or missing `https://` | Use the right scheme and verify the endpoint's certificate/TLS setup. |
| A stopped instance is still returned by discovery | Static list has no registry health state | Add LoadBalancer health checks or move to a registry with appropriate health checking. |
| A new instance is added but the consumer does not see it | Configuration file not updated/reloaded or consumer reads from another config source | Check active profiles, property sources, and restart/refresh according to the app's config mechanism. |

## 11. Checklist when declaring multiple instances

1. Choose a clear service ID and use the exact same name in the consumer.
2. Declare each instance as a separate element in the `simple.instances` list.
3. Use a complete URI with the accurate scheme, hostname/IP, and port.
4. Ensure the hostname is resolvable from where the consumer runs, not just from the developer's machine.
5. Declare metadata if LoadBalancer logic makes use of that metadata.
6. Add Spring Cloud LoadBalancer if you want to call services by logical name.
7. Add LoadBalancer-side health checks if you need to detect dead endpoints in a static list.
8. Verify the actual list via `DiscoveryClient.getInstances()` before testing HTTP calls.
9. Establish a process for updating configuration when instance addresses or counts change.

## 12. Key takeaways

- `spring.cloud.discovery.client.simple.instances` is a map from service ID to a list of instances.
- Element indices start at `0`; each instance is typically declared using the `uri` property.
- Multiple services and multiple instances can be declared in the same `application.yml`.
- An `https` URI creates an instance marked as using a secure connection; host and port must be reachable from the consumer.
- `SimpleDiscoveryClient` is used when no registry-backed `DiscoveryClient` is available on the classpath.
- `DiscoveryClient` supplies the list; Spring Cloud LoadBalancer selects an instance for calls using a logical service name.
- Static lists do not auto-update with service lifecycles and carry no registry health state; consider health checks or a dynamic registry when needed.

## References

- [Spring Cloud Commons: SimpleDiscoveryClient](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud LoadBalancer: Instance Health-Check](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
