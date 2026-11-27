# Using Static Discovery for Testing and Small-Scale Systems

Not every application needs a dynamic registry such as Eureka or Consul. For tests, demos, local environments, or small systems with a few stable endpoints, service addresses can be pre-declared in configuration. Spring Cloud Commons provides `SimpleDiscoveryClient` to turn a static URI list into `ServiceInstance` objects that code still looks up through the familiar `DiscoveryClient` abstraction.

Static discovery reduces the number of components to operate and makes test environments easy to reproduce. In return, the instance list does not update automatically when a process starts, stops, changes IP, or changes port. You must understand this boundary clearly so static discovery is not treated as a registry with health checks and self-healing capabilities.

## 1. What is static discovery?

Static service discovery is the practice of pre-declaring service endpoints in a configuration file or property source. Consumers look up targets by service ID, while the application uses the declared list to locate endpoints.

For example, an `order-service` application needs to call two instances of `inventory-service` and one instance of `payment-service`:

```text
order-service
  ├── inventory-service
  │     ├── http://localhost:8081
  │     └── http://localhost:8082
  └── payment-service
        └── http://localhost:8091
```

With `SimpleDiscoveryClient`, this list is bound from Spring Boot configuration. There is no need to run a Eureka Server or Consul Agent just for the consumer to know the URIs above.

Static discovery is appropriate when:

- Integration tests need mock endpoints or test services at fixed addresses.
- Local development involves a few services running on different ports.
- Demos or prototypes have few instances and relatively stable lifecycles.
- Internal tools or small systems have endpoints managed manually by operators.

It is not suitable when instances frequently scale up/down, are deployed across multiple nodes with changing IPs, require automatic health checks, or require registry updates without restarting consumers.

## 2. SimpleDiscoveryClient in Spring Cloud Commons

`SimpleDiscoveryClient` is a `DiscoveryClient` implementation that retrieves service and instance details from properties. According to Spring Cloud Commons, this implementation is used when the classpath does not contain a `DiscoveryClient` backed by a service registry such as Eureka, Consul, or ZooKeeper.

That has two important consequences:

1. Merely adding `spring.cloud.discovery.client.simple.instances` configuration does not guarantee the Simple client will be selected if the application still has a registry-backed `DiscoveryClient` on the runtime classpath.
2. Spring profiles only select configuration files; profiles do not remove dependency JARs from the classpath. If you want tests to use the Simple client instead of Eureka/Consul, design the dependency/runtime classpath accordingly or use a separate test application/module.

In modern Spring Cloud, `@EnableDiscoveryClient` is no longer strictly required just to enable discovery. Having the corresponding implementation on the classpath and auto-configuration is usually sufficient. With static discovery, no separate annotation is needed to register static endpoints.

Spring Cloud provides both the blocking `DiscoveryClient` API and the reactive `ReactiveDiscoveryClient` API. Simple discovery has implementations for both models so application code can use the abstraction matching its stack.

## 3. Declaring instances with YAML

Suppose a consumer needs to call two instances of `inventory-service` and one instance of `payment-service`. Place the configuration in `application.yml` or the corresponding profile file:

```yaml
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
            payment-service:
              - uri: http://localhost:8091
```

Meaning of the structure:

| Configuration Part | Meaning |
|---|---|
| `spring.cloud.discovery.client.simple.instances` | Prefix holding the map of service IDs and instance lists |
| `inventory-service` | Service ID the consumer uses for lookup |
| `[0]`, `[1]` (implicit via YAML list) | Instance index, starting from 0 in property syntax |
| `uri` | Full URI of the instance, including scheme, host, and port |

The URI must be an address reachable by the consumer itself. The example above uses `localhost` assuming services run on the same machine. When running in containers or across different machines, replace it with a DNS name/IP routable from the consumer's environment.

### 3.1. Properties format

The same list can be written in `application.properties`:

```properties
spring.application.name=order-service

spring.cloud.discovery.client.simple.instances.inventory-service[0].uri=http://localhost:8081
spring.cloud.discovery.client.simple.instances.inventory-service[1].uri=http://localhost:8082
spring.cloud.discovery.client.simple.instances.payment-service[0].uri=http://localhost:8091
```

Indices inside square brackets start at `0`. The service ID is the part between `instances.` and the index; the URI is the actual endpoint.

### 3.2. HTTP and HTTPS URIs

The URI carries the scheme, hostname, and port. HTTPS can be declared if the endpoint uses TLS:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            secure-catalog:
              - uri: https://catalog-a.internal:8443
              - uri: https://catalog-b.internal:8443
```

Do not embed usernames, passwords, API keys, or tokens into URIs committed to a repository. Endpoint configuration and credentials should be managed separately via secrets or environment variables.

## 4. Separating endpoint lists by profile

Static discovery is often most useful when each environment has a different list of endpoints. You can keep shared configuration in `application.yml`, then declare local endpoints in `application-local.yml` and test endpoints in `application-test.yml`.

`application.yml`:

```yaml
spring:
  application:
    name: order-service
```

`application-local.yml`:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
            payment-service:
              - uri: http://localhost:8091
```

`application-test.yml`:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:18081
            payment-service:
              - uri: http://localhost:18091
```

Activate a profile from the command line:

```bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=local
```

Or run the JAR:

```bash
java -jar target/order-service.jar --spring.profiles.active=test
```

Do not place `spring.profiles.active` inside `application-local.yml` or `application-test.yml` itself; the active profile must be selected from a profile-independent configuration document, environment variable, or runtime argument.

**Note on classpath:** if `order-service` still has a Eureka/Consul starter on the runtime classpath, switching to the `test` profile will not automatically select the Simple client. The condition for choosing `SimpleDiscoveryClient` depends on whether a registry-backed `DiscoveryClient` is on the classpath. Inspect the actual test runtime dependencies; you can split out a `consumer-test` module or configure the build to exclude registry starters when testing with static discovery.

## 5. Looking up instances with DiscoveryClient

Application code still uses the common abstraction, without needing to know whether URIs come from YAML or a dynamic registry:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
class InventoryLocator {

    private final DiscoveryClient discoveryClient;

    InventoryLocator(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    List<ServiceInstance> findInventoryInstances() {
        return discoveryClient.getInstances("inventory-service");
    }

    List<String> availableServices() {
        return discoveryClient.getServices();
    }
}
```

`getInstances("inventory-service")` returns the `ServiceInstance` objects declared for that exact service ID. `getServices()` returns the list of service IDs present in the Simple client configuration. If the service name does not match, `getInstances` returns an empty list.

You can iterate over endpoints to verify configuration:

```java
List<ServiceInstance> instances =
        discoveryClient.getInstances("inventory-service");

for (ServiceInstance instance : instances) {
    System.out.printf(
        "service=%s host=%s port=%d uri=%s secure=%s%n",
        instance.getServiceId(),
        instance.getHost(),
        instance.getPort(),
        instance.getUri(),
        instance.isSecure());
}
```

This is a way to diagnose the endpoint list. In real applications, avoid manually picking `instances.get(0)` for every request because that ignores all remaining instances and provides no load-balancing policy.

## 6. Combining with Spring Cloud LoadBalancer

`SimpleDiscoveryClient` only supplies the instance list. It does not select an instance for each HTTP request. If you want to call by service ID such as `http://inventory-service`, you need an HTTP client integrated with Spring Cloud LoadBalancer.

Add the LoadBalancer starter:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

Do not declare an explicit version when the Spring Cloud BOM already manages dependencies.

With Spring `RestClient`, declare a `@LoadBalanced` builder:

```java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
```

Inject the builder to call the service by logical service ID:

```java
import org.springframework.stereotype.Service;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.web.client.RestClient;

@Service
class InventoryClient {

    private final RestClient restClient;

    InventoryClient(@LoadBalanced RestClient.Builder loadBalancedRestClientBuilder) {
        this.restClient = loadBalancedRestClientBuilder.build();
    }

    String getProducts() {
        return restClient.get()
            .uri("http://inventory-service/api/products")
            .retrieve()
            .body(String.class);
    }
}
```

LoadBalancer retrieves the `ServiceInstance` list from `DiscoveryClient` and picks one endpoint to replace the logical host `inventory-service` with a physical address. The URI used in the call must be the service ID, not the hostname of a specific instance.

Without Spring Cloud LoadBalancer, `inventory-service` will not automatically resolve to an address from Simple configuration. You can call a physical URI directly, but then the application manages endpoint selection itself and does not leverage the service ID abstraction.

## 7. Testing with mock endpoints

Static discovery is useful when you want to test a consumer without starting a registry. You can run one or more HTTP mock servers on fixed ports, then declare their URIs in `application-test.yml`.

Example configuring one mock server:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:18081
```

A test can initialize the Spring context with the `test` profile:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class InventoryClientTest {

    @Test
    void applicationContextLoads() {
        // Verify wiring and discovery configuration.
    }
}
```

The test above only verifies that the context starts. To test actual requests, start the mock server on the declared port, configure expected responses, and invoke the method on `InventoryClient`. If the test uses a random port assigned by the mock server, pass the actual port into the property before the context starts; do not hardcode a fixed port and assume the mock server will always use it.

Static discovery does not check whether the mock server is running. If the endpoint has not started, `DiscoveryClient` can still return the URI from configuration; the error only surfaces when the consumer sends a request.

## 8. SimpleDiscoveryClient and health checks

Simple discovery reads URI lists from properties. It does not ping endpoints, send heartbeats, automatically remove instances when processes stop, or receive health status from a registry. This is an important difference compared to Eureka or Consul.

| Capability | SimpleDiscoveryClient | Dynamic Registry like Eureka/Consul |
|---|---|---|
| Declare service ID and endpoint | Yes, via configuration | Yes, via registration |
| Auto-detect new instances | No | Yes, when instances register |
| Auto-detect stopped instances | No | Yes, via lease/health check depending on registry |
| Heartbeat | No | Can be supported |
| Health state from registry | No | Yes |
| Change endpoints without updating consumer config | No | Usually yes |
| Operate an additional registry server/agent | No | May be required |

If you want to check the health of static endpoints, you can build custom health checks in the application or configure Spring Cloud LoadBalancer's `HealthCheckServiceInstanceListSupplier`. However, this is a consumer-side verification layer; it does not turn `SimpleDiscoveryClient` into a registry with registration, heartbeats, or state synchronization.

In particular, do not rely on an endpoint appearing in `getInstances()` to conclude that it is healthy. The list only reflects bound configuration.

## 9. Managing endpoint changes

When instance addresses change, static discovery requires updating the corresponding configuration. A straightforward workflow can be:

1. Identify the service ID to change.
2. Update the URI in the active profile or property source.
3. Verify the new endpoint is reachable from the consumer.
4. Restart the consumer or execute a configuration refresh mechanism that has been designed and tested.
5. Call `DiscoveryClient.getInstances(serviceId)` to confirm the new list.
6. Send a request via the LoadBalancer to confirm routing to the new endpoint.

Do not assume that editing a YAML file on disk causes a running Spring `ApplicationContext` to automatically update its instance list. If you want dynamic refresh, configure an appropriate external configuration/refresh mechanism and verify `SimpleDiscoveryProperties` rebinds properly.

For long or frequently changing endpoint lists, storing URIs in a dedicated config file or external config server can help management; however, an update/refresh process is still required. When multiple teams edit the same list, manage change permissions and validate endpoints before release.

## 10. Limitations of static discovery in small systems

Static discovery simplifies operations but shifts the responsibility of updating endpoints to configuration and deployment processes. Consider:

- **Endpoint stability:** IPs/ports must stay stable long enough that configuration does not constantly go stale.
- **Reachability:** every URI must be valid from the consumer's network namespace, especially in Docker or multi-host environments.
- **Instance count:** large and frequently changing lists are hard to maintain manually.
- **Health:** the list does not automatically drop dead endpoints; health checks or client-layer checks are needed.
- **Updates:** configuration changes require a release or refresh workflow.
- **Security:** do not store credentials in URIs; use a secret store and TLS when needed.
- **Availability:** if every declared instance fails, static discovery has no registry to self-heal or discover replacements.

For small systems, static discovery can be used when endpoints are few, changes are controlled, and release-based updates are acceptable. When you need autoscaling, service registration, heartbeats, health states, failover, or multiple dynamic environments, move to Eureka, Consul, or a platform-provided discovery mechanism.

## 11. Common errors

| Symptom | Cause | Resolution |
|---|---|---|
| `getInstances()` returns an empty list | Wrong service ID or YAML bound with wrong structure | Compare keys under `simple.instances` with the string passed to `getInstances()` |
| Simple client is not used | Eureka/Consul/ZooKeeper DiscoveryClient is still on the runtime classpath | Inspect the dependency tree and the actual `DiscoveryClient` bean |
| LoadBalanced request reports no instance found | Missing URI for the service ID or missing LoadBalancer starter | Check config and add `spring-cloud-starter-loadbalancer` |
| Request connection refused | Declared endpoint has no process listening | Start the service/mock server and verify host/port from the consumer |
| Consumer in a container fails calling `localhost` | `localhost` points to the consumer container itself | Use service/container DNS or a routable address |
| Only one instance gets called | Code manually picks the first element instead of using LoadBalancer | Use a `@LoadBalanced` HTTP client or `LoadBalancerClient` |
| YAML changed but the list stays the same | `ApplicationContext` does not auto-reload configuration files | Restart or implement a tested refresh mechanism |
| List contains stopped endpoints | Simple client does not perform health checks | Use a health-check supplier or move to a dynamic registry |

## 12. Checklist

- [ ] Confirmed this environment is suited for static discovery.
- [ ] No registry-backed `DiscoveryClient` is on the runtime classpath if the Simple client should be auto-selected.
- [ ] Declared the exact service ID and URI for each instance.
- [ ] Indices in properties format start at `0` with no duplicates.
- [ ] URIs have the appropriate scheme, host, and port.
- [ ] Endpoints are reachable from the consumer's network namespace.
- [ ] Separated local/test endpoints using profiles or property sources.
- [ ] Understood that profiles do not remove dependencies from the classpath.
- [ ] Added Spring Cloud LoadBalancer if calling by service ID.
- [ ] Tested what happens when an endpoint stops and understood that static lists do not remove endpoints automatically.
- [ ] Established a configuration update workflow when URIs change.
- [ ] No credentials or secrets stored in URIs.

## References

- [Spring Cloud Commons 5.1.0 — Common Abstractions: SimpleDiscoveryClient](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons 5.1.0 — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
- [Spring Cloud Commons — Spring RestClient as a LoadBalancer Client](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons — SimpleDiscoveryClient source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/simple/SimpleDiscoveryClient.java)
- [Spring Cloud Commons — SimpleDiscoveryClient auto-configuration source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/simple/SimpleDiscoveryClientAutoConfiguration.java)
