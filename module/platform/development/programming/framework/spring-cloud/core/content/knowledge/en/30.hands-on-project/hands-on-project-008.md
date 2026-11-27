# Looking Up Instances with SimpleDiscoveryClient

## 1. Lab Objectives

In microservices systems, a single service may run multiple instances. Consumers need to know the addresses of instances belonging to a service ID to inspect topology or route requests through a load balancing mechanism.

Spring Cloud Commons provides the `DiscoveryClient` abstraction. When an application has no service-registry-backed discovery client such as Eureka, Consul, or Zookeeper on the classpath, Spring Cloud can configure `SimpleDiscoveryClient`. This implementation reads service and instance lists from application properties.

In this lab, we build a `discovery-inspector` application that can:

- Declare two instances of `catalog-service` and one instance of `payment-service`.
- Inject `DiscoveryClient` to look up the list of services.
- Look up instances by service ID.
- Display host, port, URI, HTTPS flag, instance ID, and metadata.
- Return an empty list when a service ID is not configured.
- Write tests verifying that property entries are mapped into `ServiceInstance` objects.

This lesson belongs to the **Hands-on Project** chapter of the **SPRING_CLOUD_CORE** module. The module helps learners understand Spring Cloud Commons, Spring Cloud Context, externalized configuration, Spring Boot compatibility, refresh scope, discovery, service registry, service communication, and how to test and operate common abstractions.

## 2. Understanding the Role of SimpleDiscoveryClient

### 2.1. DiscoveryClient Is the Lookup Contract

`DiscoveryClient` provides these core read operations:

| API | Meaning |
| --- | --- |
| `getServices()` | Returns the service IDs known to the discovery client |
| `getInstances(serviceId)` | Returns the instances belonging to the requested service ID |
| `description()` | Describes the implementation, commonly used in health indicators |
| `probe()` | Verifies whether the discovery client can perform lookups; defaults to calling `getServices()` |

Each returned element is a `ServiceInstance`, exposing information such as:

- `getServiceId()`: the service ID.
- `getInstanceId()`: the unique ID of the instance if available.
- `getHost()` and `getPort()`: physical address.
- `getUri()`: access URI.
- `isSecure()`: whether the instance uses HTTPS or HTTP.
- `getMetadata()`: additional key/value pairs.

Consumers should depend on the `DiscoveryClient` interface so the exact same code works with Simple Discovery, Eureka, Consul, or other implementations.

### 2.2. Where Does SimpleDiscoveryClient Get Data?

Simple Discovery uses the property prefix:

```text
spring.cloud.discovery.client.simple.instances
```

The data structure is a map from service ID to a list of instances. For example:

```text
spring.cloud.discovery.client.simple.instances.catalog-service[0].uri=http://catalog-1:8081
spring.cloud.discovery.client.simple.instances.catalog-service[1].uri=http://catalog-2:8081
```

Where:

- `catalog-service` is the service ID.
- `[0]` and `[1]` are the indices of the two instances, starting at 0.
- `uri` is the address where the instance can be reached.

If no registry-based discovery client is on the classpath, Spring Cloud auto-configures `SimpleDiscoveryClient`. If the application already includes an Eureka, Consul, or Zookeeper starter, that corresponding implementation may be selected instead. Therefore, during this lab, avoid adding unrelated registry starters.

With current Spring Cloud versions, `@EnableDiscoveryClient` is not needed just to activate discovery when an implementation is already auto-configured on the classpath.

### 2.3. SimpleDiscoveryClient Is Not a Service Registry

Simple Discovery reads a static list from configuration. It does not automatically:

- Register instances with a registry server.
- Send heartbeats or leases.
- Discover newly deployed instances.
- Evict dead instances from the list.
- Check whether an endpoint is actually healthy before returning results.

Accordingly, Simple Discovery suits local development, demos, tests, or small topologies managed via configuration. For systems requiring dynamic registration and health-aware discovery, use an appropriate registry or combine Spring Cloud LoadBalancer with a health-check supplier as needed.

## 3. Preparing the Project

### 3.1. Dependencies

The application needs Spring Boot Web and Spring Cloud Commons. Dependency management should use a Spring Cloud BOM compatible with the project's Spring Boot version.

Example Maven dependencies:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-commons</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

If the project already manages Spring Cloud via a BOM, do not declare a separate version for `spring-cloud-commons`. Do not add Eureka/Consul/Zookeeper starters to this lab, as the goal is for Simple Discovery to be selected as the implementation.

### 3.2. Source Structure

You can organize the project as follows:

```text
discovery-inspector/
└── src/
    ├── main/
    │   ├── java/com/example/discovery/
    │   │   ├── DiscoveryInspectorApplication.java
    │   │   ├── DiscoveryController.java
    │   │   └── InstanceView.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/discovery/
            └── SimpleDiscoveryLookupTests.java
```

## 4. Declaring Multiple Instances in application.yml

Create `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: discovery-inspector
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:8081
                instance-id: catalog-1
                metadata:
                  zone: zone-a
                  version: v1
              - uri: https://localhost:8443
                instance-id: catalog-2
                metadata:
                  zone: zone-b
                  version: v2
            payment-service:
              - uri: http://localhost:8090
                instance-id: payment-1
                metadata:
                  zone: zone-a
                  version: v1
server:
  port: 8080
```

This configuration creates the following topology:

| Service ID | Instance ID | URI | Metadata |
| --- | --- | --- | --- |
| `catalog-service` | `catalog-1` | `http://localhost:8081` | zone-a, v1 |
| `catalog-service` | `catalog-2` | `https://localhost:8443` | zone-b, v2 |
| `payment-service` | `payment-1` | `http://localhost:8090` | zone-a, v1 |

Key points to note:

- The Service ID is the map key under `instances`; consumers must query using that exact key.
- List indices are bound automatically by Spring Boot from YAML. If using `.properties`, the first index is `[0]`.
- The URI must include the `http` or `https` scheme and a valid address/port.
- `metadata` is a string key/value map describing zone, version, or routing details.
- `instance-id` distinguishes multiple instances of the same service.
- In Docker/Kubernetes, do not use `localhost` to point to another container; use a DNS/service name resolvable from the application's network.

Even if only the URI is declared, Spring Cloud can still build a `ServiceInstance`. The `host`, `port`, and `secure` fields are derived from the URI. Additional metadata can be declared for consumers or load balancers to use when needed.

## 5. Creating the Spring Boot Application

### 5.1. Application Entry Point

```java
package com.example.discovery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DiscoveryInspectorApplication {

    public static void main(String[] args) {
        SpringApplication.run(DiscoveryInspectorApplication.class, args);
    }
}
```

`@EnableDiscoveryClient` is not required in this example. Spring Cloud Commons auto-configuration creates the Simple Discovery client when no other service-registry-backed client is present.

### 5.2. Creating a DTO for Instances

Do not return internal discovery client implementation objects directly from an API. Create a stable DTO to control which fields are exposed:

```java
package com.example.discovery;

import java.net.URI;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.cloud.client.ServiceInstance;

public record InstanceView(
        String serviceId,
        String instanceId,
        String host,
        int port,
        boolean secure,
        URI uri,
        Map<String, String> metadata) {

    public static InstanceView from(ServiceInstance instance) {
        Map<String, String> source = instance.getMetadata();
        Map<String, String> safeMetadata = source == null
                ? Map.of()
                : new LinkedHashMap<>(source);

        return new InstanceView(
                instance.getServiceId(),
                instance.getInstanceId(),
                instance.getHost(),
                instance.getPort(),
                instance.isSecure(),
                instance.getUri(),
                safeMetadata
        );
    }
}
```

Metadata may be used internally for discovery. If metadata contains sensitive information, do not expose the entire map on a public API; filter it using an allowlist.

### 5.3. Creating the Lookup Endpoints

Inject the `DiscoveryClient` interface into the controller:

```java
package com.example.discovery;

import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/discovery")
public class DiscoveryController {

    private final DiscoveryClient discoveryClient;

    public DiscoveryController(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    @GetMapping("/implementation")
    public String implementation() {
        return discoveryClient.description();
    }

    @GetMapping("/services")
    public List<String> services() {
        return discoveryClient.getServices().stream()
                .sorted()
                .toList();
    }

    @GetMapping("/services/{serviceId}/instances")
    public ResponseEntity<List<InstanceView>> instances(
            @PathVariable String serviceId) {

        List<InstanceView> result = discoveryClient.getInstances(serviceId)
                .stream()
                .map(InstanceView::from)
                .toList();

        return ResponseEntity.ok(result);
    }
}
```

The three endpoints perform three distinct operations:

- `GET /api/discovery/implementation`: confirms which implementation is injected.
- `GET /api/discovery/services`: lists configured service IDs.
- `GET /api/discovery/services/{serviceId}/instances`: looks up the instances of a service.

For a non-existent service ID, `SimpleDiscoveryClient.getInstances()` returns an empty list. The controller preserves these semantics and returns HTTP 200 with an empty array. If a business API needs to distinguish an unknown service from a service with zero instances, define an explicit convention at the application layer.

## 6. Running the Application and Looking Up Instances

Start the application via your IDE or your project's Spring Boot run command. Once the application is ready on port 8080, call the following endpoints.

### 6.1. Confirming the Implementation

```bash
curl http://localhost:8080/api/discovery/implementation
```

Expected output when no registry-backed discovery client is present:

```text
Simple Discovery Client
```

If the output reports a different implementation, inspect the dependency tree and remove registry starters from the lab profile.

### 6.2. Listing Service IDs

```bash
curl http://localhost:8080/api/discovery/services
```

Example output:

```json
[
  "catalog-service",
  "payment-service"
]
```

Element ordering may vary by implementation. The controller sorts the results by name for a deterministic lab response.

### 6.3. Looking Up catalog-service Instances

```bash
curl http://localhost:8080/api/discovery/services/catalog-service/instances
```

Example abbreviated output:

```json
[
  {
    "serviceId": "catalog-service",
    "instanceId": "catalog-1",
    "host": "localhost",
    "port": 8081,
    "secure": false,
    "uri": "http://localhost:8081",
    "metadata": {
      "zone": "zone-a",
      "version": "v1"
    }
  },
  {
    "serviceId": "catalog-service",
    "instanceId": "catalog-2",
    "host": "localhost",
    "port": 8443,
    "secure": true,
    "uri": "https://localhost:8443",
    "metadata": {
      "zone": "zone-b",
      "version": "v2"
    }
  }
]
```

The `host`, `port`, and `secure` fields are inferred from the configured URI. Metadata is preserved as a key/value map.

### 6.4. Looking Up an Unconfigured Service

```bash
curl http://localhost:8080/api/discovery/services/shipping-service/instances
```

Output:

```json
[]
```

This is normal behavior for Simple Discovery when the map does not contain the requested service ID. The consumer must decide the next business action, such as returning a service-unavailable error or using a fallback.

## 7. Writing an Integration Test for SimpleDiscoveryClient

The test below boots the Spring context with test-specific properties. No Eureka/Consul server is required because Simple Discovery reads only configuration.

```java
package com.example.discovery;

import java.net.URI;
import java.util.List;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
        "spring.application.name=discovery-inspector",
        "spring.cloud.discovery.client.simple.instances.catalog-service[0].uri=http://catalog-1:8081",
        "spring.cloud.discovery.client.simple.instances.catalog-service[0].instance-id=catalog-1",
        "spring.cloud.discovery.client.simple.instances.catalog-service[0].metadata.zone=zone-a",
        "spring.cloud.discovery.client.simple.instances.catalog-service[1].uri=https://catalog-2:8443",
        "spring.cloud.discovery.client.simple.instances.catalog-service[1].instance-id=catalog-2",
        "spring.cloud.discovery.client.simple.instances.catalog-service[1].metadata.zone=zone-b",
        "spring.cloud.discovery.client.simple.instances.payment-service[0].uri=http://payment-1:8090"
})
class SimpleDiscoveryLookupTests {

    @Autowired
    DiscoveryClient discoveryClient;

    @Test
    void usesSimpleDiscoveryImplementation() {
        assertThat(discoveryClient.description())
                .isEqualTo("Simple Discovery Client");
    }

    @Test
    void listsConfiguredServices() {
        assertThat(discoveryClient.getServices())
                .containsExactlyInAnyOrder(
                        "catalog-service",
                        "payment-service"
                );
    }

    @Test
    void returnsAllCatalogInstances() {
        List<ServiceInstance> instances =
                discoveryClient.getInstances("catalog-service");

        assertThat(instances).hasSize(2);

        ServiceInstance first = instances.get(0);
        assertThat(first.getServiceId()).isEqualTo("catalog-service");
        assertThat(first.getInstanceId()).isEqualTo("catalog-1");
        assertThat(first.getUri())
                .isEqualTo(URI.create("http://catalog-1:8081"));
        assertThat(first.isSecure()).isFalse();
        assertThat(first.getMetadata()).containsEntry("zone", "zone-a");

        ServiceInstance second = instances.get(1);
        assertThat(second.getUri())
                .isEqualTo(URI.create("https://catalog-2:8443"));
        assertThat(second.isSecure()).isTrue();
    }

    @Test
    void returnsEmptyListForUnknownService() {
        assertThat(discoveryClient.getInstances("unknown-service"))
                .isEmpty();
    }
}
```

This test verifies four contracts:

1. Simple Discovery is used at runtime.
2. Service IDs are read from the properties map.
3. URI, HTTPS flag, and metadata are mapped onto `ServiceInstance`.
4. An unknown service ID returns an empty list.

Do not assert instance ordering if ordering is not part of your application's contract. In the test above, order is checked by list index because the configuration declares two items at indices 0 and 1. If another implementation or configuration source does not guarantee ordering, look up the instance by `instanceId` before asserting.

## 8. From Lookup to Calling a Service

### 8.1. DiscoveryClient Only Returns Instance Details

The snippet:

```java
List<ServiceInstance> instances =
        discoveryClient.getInstances("catalog-service");
```

only looks up addresses. It does not send HTTP requests, choose a retry policy, or verify whether an endpoint is actually reachable.

Do not manually pick `instances.get(0)` as a load-balancing strategy in business code. That always favors the first element and lacks health-aware selection, retries, or request metrics.

### 8.2. Using Spring Cloud LoadBalancer When Calling by Service ID

If you want to call `catalog-service` by logical service ID instead of physical address, add the Spring Cloud LoadBalancer starter compatible with your project's release train. Create an HTTP client annotated with `@LoadBalanced` and call a URI such as:

```text
http://catalog-service/api/catalog
```

LoadBalancer uses the instances supplied by `DiscoveryClient` to choose a physical address. With Simple Discovery, the input list still comes from properties in `application.yml`.

If constructing a `RestClient.Builder` or another builder manually, apply the corresponding Spring Boot customizers/configurers to preserve observation and tracing. Consult the Spring Cloud Commons documentation on `@LoadBalanced` builders for `RestClient`/`RestTemplate`/`WebClient`.

Simple Discovery does not verify health on its own. For small topologies, you can configure Spring Cloud LoadBalancer's health-check supplier to exclude unresponsive instances from selection. The health check mechanism needs appropriate timeouts, intervals, and paths for the application.

## 9. Troubleshooting

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Cannot inject `DiscoveryClient` | Missing Spring Cloud Commons or discovery disabled | Check dependency management, classpath, and `spring.cloud.discovery.enabled` |
| Implementation is not Simple Discovery | Another registry-backed discovery client is on the classpath | Check Eureka/Consul/Zookeeper starters and active profiles |
| `getServices()` misses expected service | Wrong prefix or service ID key | Check `spring.cloud.discovery.client.simple.instances` and service names |
| `getInstances()` returns empty list | Wrong service ID or no instance elements bound | Match exact service ID and ensure indices start at 0 |
| Only one instance returned | Elements reuse the same index or list syntax is invalid | Use sequential indices `[0]`, `[1]`, ... |
| URI missing host/port or invalid | URI missing scheme or port | Declare full URIs like `http://catalog-1:8081` |
| HTTPS instance has `secure=false` | URI uses `http` scheme or config bound incorrectly | Use `https://` and verify `ServiceInstance.isSecure()` |
| Metadata missing | Wrong key structure or metadata not bound | Check `metadata.zone`, `metadata.version`, and test properties |
| Discovery returns URI but request fails | Instance not running, DNS fails, or port blocked | Check network, health endpoint, and firewall; discovery lookup is not a health check |
| Works locally but fails in containers | Config uses `localhost` to target another container | Use DNS/service names on the container network |
| Tests pass but real app misses Simple Discovery | Tests lack registry starter while runtime includes one | Compare dependencies/profiles between tests and runtime app |

### 9.1. Quick Debugging Checklist

1. Confirm `spring-cloud-commons` is on the runtime classpath.
2. Confirm no registry-backed discovery client is present if you intend to use Simple Discovery.
3. Confirm `spring.cloud.discovery.enabled` is not turned off.
4. Check the exact prefix and service ID.
5. Check that list indices start at 0 with no duplicates.
6. Check URI, scheme, host, and port.
7. Call `/api/discovery/implementation`, `/services`, and then the instances endpoint.
8. If planning to send HTTP requests, verify health and networking independently of discovery results.

## 10. Extension Exercises

After completing the basic lab, try these exercises:

1. Add a third instance for `catalog-service` with metadata `zone: zone-c`.
2. Add `shipping-service` with two instances and confirm `getServices()` updates.
3. Extend the controller to accept a `zone` query parameter, returning only instances with matching zone metadata.
4. Write tests for the zone filter and for the case where metadata does not contain a `zone` key.
5. Add a registry-backed discovery starter in a separate profile and observe how the selected implementation changes.
6. Add Spring Cloud LoadBalancer and call an endpoint by service ID `http://catalog-service`.
7. Configure a health-check supplier and simulate an unresponsive instance to observe instance selection.

## 11. Completion Criteria

The lab meets requirements when:

- The application starts without needing Eureka, Consul, or Zookeeper.
- `DiscoveryClient.description()` confirms Simple Discovery is active.
- `getServices()` returns all declared service IDs.
- `getInstances("catalog-service")` returns two instances with exact URIs and metadata.
- The HTTPS instance is identified via `isSecure()`.
- An unknown service ID returns an empty list.
- Integration tests verify all contracts above.
- Learners can explain the difference between discovery lookup, health checks, and load balancing.

## 12. Official References

- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): conditions for using `SimpleDiscoveryClient`, property prefixes, and the service discovery abstraction.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): properties under `spring.cloud.discovery.client.simple.*`.
- [DiscoveryClient API](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/DiscoveryClient.java): contracts for `getServices()`, `getInstances()`, `description()`, and `probe()`.
- [SimpleDiscoveryClient source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/simple/SimpleDiscoveryClient.java): how properties are mapped to a list of `ServiceInstance` objects.
- [ServiceInstance API](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/ServiceInstance.java): fields for service ID, instance ID, host, port, URI, secure, and metadata.
- [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): how to use the instance list from `DiscoveryClient` to select instances when calling services.

**Key takeaway:** `SimpleDiscoveryClient` is a property-backed discovery client. It lets an application look up instance lists by service ID through the same `DiscoveryClient` contract, without providing a dynamic registry, heartbeats, or health checks. When you need to call services by name and pick instances, combine discovery with Spring Cloud LoadBalancer.
