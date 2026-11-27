# SimpleDiscoveryClient Using Configured Instance Lists

> **Chapter:** DiscoveryClient  
> **Module:** SPRING_CLOUD_CORE

Not every environment requires a dedicated service registry. In local applications, integration tests, demos, or small systems with a stable endpoint list, you can predeclare service instances in configuration. Spring Cloud Commons provides **`SimpleDiscoveryClient`** to read this list and expose it through the `DiscoveryClient` abstraction for the rest of the application to consume.

This mechanism lets service-calling code work with service IDs instead of hardcoding hostnames and ports everywhere. However, a static instance list is only discovery data loaded from configuration. It does not register instances, send heartbeats, check health, or synchronize lifecycle state with an external registry. This lesson covers declaring instances, reading via DiscoveryClient, integrating Spring Cloud LoadBalancer, testing, and deciding when a static list is appropriate in **SPRING_CLOUD_CORE**.

## 1. What Problem Does SimpleDiscoveryClient Solve?

In a multi-service system, clients often need to locate one or more instances by logical name. For example, `order-service` needs to call `catalog-service` without directly depending on individual machine addresses.

With service discovery, the client queries the `DiscoveryClient` abstraction to retrieve instances associated with a service ID. An implementation like Eureka or Consul can fetch data from a centralized registry. `SimpleDiscoveryClient` uses an instance list declared in application configuration.

For example:

- Service ID: `catalog-service`.
- First instance: `http://catalog-1.internal:8081`.
- Second instance: `http://catalog-2.internal:8081`.

The application can retrieve both instances through the same `DiscoveryClient` abstraction. The service-calling component can combine that list with Spring Cloud LoadBalancer to select an instance per request.

### 1.1. When Is a Static Instance List Useful?

| Environment / Scenario | Benefit |
| --- | --- |
| Local development | Declare endpoints of mock services or services running on the developer's machine |
| Integration tests | Supply a deterministic instance list to test discovery behavior |
| Demos or workshops | Demonstrate service IDs and instances without running a separate registry |
| Small systems, stable endpoints | Reduce infrastructure components to operate |
| Isolated environments | Declare internal endpoints per deployment profile |

A static list is especially suitable when topology rarely changes and operators can update configuration alongside deployments. If instances are frequently created/deleted, change IPs, or autoscale, a dynamic registry is usually more appropriate.

## 2. SimpleDiscoveryClient and DiscoveryClient

`DiscoveryClient` is an abstraction from Spring Cloud Commons. Commonly used methods include:

~~~java
public interface DiscoveryClient {
    String description();
    List<ServiceInstance> getInstances(String serviceId);
    List<String> getServices();
}
~~~

Interface details may include additional default methods or vary by Spring Cloud Commons version; the three operations above represent the core needs:

| Method | Meaning |
| --- | --- |
| `getInstances(serviceId)` | Retrieves the known instances for a service ID |
| `getServices()` | Retrieves the service IDs known to the client |
| `description()` | Describes the discovery implementation |

`SimpleDiscoveryClient` implements this abstraction by reading data from `SimpleDiscoveryProperties`. Data is organized by service ID, with each service having a list of instances.

When calling `getInstances("catalog-service")`, the client receives the instances declared under the `catalog-service` key. If the service ID does not exist in configuration, the result is typically an empty list. `getServices()` returns the service IDs present in configuration.

### 2.1. Service ID vs. Hostname and IP

A service ID is the logical name a client uses to query discovery. Hostname/IP and port are the address of each instance.

| Element | Example | Role |
| --- | --- | --- |
| Service ID | `catalog-service` | Logical name to locate a service |
| Instance URI | `http://catalog-1.internal:8081` | Address of one instance |
| Host | `catalog-1.internal` | Hostname of the instance |
| Port | `8081` | Port where the instance accepts requests |
| Metadata | `zone=zone-a` | Additional information about the instance |

One service ID can map to multiple instances. When instances change, the list must be updated in configuration or managed by another registry system.

## 3. Declaring Instances in application.yml

`SimpleDiscoveryClient` reads instance lists from the prefix:

~~~text
spring.cloud.discovery.client.simple.instances
~~~

Each key under `instances` is a service ID; the value is the list of instances for that service. Each entry typically declares `uri` and may include `metadata`.

Example:

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://catalog-1.internal:8081
                metadata:
                  zone: zone-a
                  version: v1
              - uri: http://catalog-2.internal:8081
                metadata:
                  zone: zone-b
                  version: v1
            pricing-service:
              - uri: http://pricing.internal:8082
                metadata:
                  zone: zone-a
~~~

In this configuration:

- `catalog-service` has two instances.
- `pricing-service` has one instance.
- The URI specifies each instance's scheme, host, and port.
- Metadata supplies extra information that the application or load balancer can use if designed to read it.

The service ID name must be consistent between declaration and call sites. If the client queries `catalog` while configuration only defines `catalog-service`, discovery will not infer they are equivalent.

### 3.1. Declaring Multiple Instances for One Service

A service can have one or more instances:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://inventory-a.internal:8090
              - uri: http://inventory-b.internal:8090
              - uri: https://inventory-c.internal:8443
~~~

You can use HTTP or HTTPS depending on client and environment capabilities. The URI scheme indicates an instance uses a secure connection; you still need appropriate truststores, certificates, hostname verification, and TLS policies on the HTTP client.

A configured list does not mean instances are connectivity-checked at application startup. Having a syntactically valid URI is different from the host resolving or the port listening.

### 3.2. Instance Metadata

Metadata is a key/value map attached to each instance. Example:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://catalog-a.internal:8081
                metadata:
                  zone: zone-a
                  version: v2
                  protocol: http
              - uri: http://catalog-b.internal:8081
                metadata:
                  zone: zone-b
                  version: v2
                  protocol: http
~~~

Metadata can describe zone, version, deployment group, or business labels. However, declaring metadata alone does not produce instance-filtering behavior. A metadata consumer, such as a custom supplier or load-balancer policy, must be configured to use it.

Never put passwords, access tokens, private keys, or secrets into metadata. Metadata may appear in logs, diagnostic endpoints, or client code.

### 3.3. Using Profiles to Separate Lists by Environment

You can place a shared instance list in `application.yml` and override it per profile:

`application.yml`:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:8081
~~~

`application-production.yml`:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://catalog-a.internal:8081
              - uri: http://catalog-b.internal:8081
~~~

When the production profile is active, Spring Boot loads profile config according to Config Data and property source precedence rules. For lists, merge/binding rules can differ from scalars; do not assume local elements are appended to the production list. Test binding output in the exact Spring Boot version you use.

Avoid letting local endpoints become an accidental fallback in production if the service must call internal endpoints. You can use validation or environment-specific config checks to fail fast if a critical service ID lacks instances.

## 4. Reading Instances via DiscoveryClient

When SimpleDiscoveryClient is configured and selected as the implementation, the application can inject the `DiscoveryClient` abstraction rather than depending directly on the concrete class.

Example:

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class CatalogDiscoveryService {

    private final DiscoveryClient discoveryClient;

    public CatalogDiscoveryService(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> catalogInstances() {
        return discoveryClient.getInstances("catalog-service");
    }

    public List<String> knownServices() {
        return discoveryClient.getServices();
    }
}
~~~

Discovery-calling code does not need to know whether instances come from YAML, Eureka, or another implementation. That is the benefit of the abstraction in Spring Cloud Commons.

### 4.1. Reading ServiceInstance Information

Each element is a `ServiceInstance`. Example:

~~~java
import java.net.URI;
import java.util.List;
import java.util.Map;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

List<ServiceInstance> instances =
        discoveryClient.getInstances("catalog-service");

for (ServiceInstance instance : instances) {
    String serviceId = instance.getServiceId();
    String host = instance.getHost();
    int port = instance.getPort();
    boolean secure = instance.isSecure();
    URI uri = instance.getUri();
    Map<String, String> metadata = instance.getMetadata();
}
~~~

Commonly needed properties:

- `getServiceId()`: service ID associated with the instance.
- `getHost()` and `getPort()`: host address and port.
- `isSecure()`: whether the instance is marked to use a secure connection.
- `getUri()`: base URI of the instance.
- `getMetadata()`: additional metadata.
- `getInstanceId()`: instance ID if supplied by the implementation.

Do not manually build URIs from host and port strings when `getUri()` is available. IPv6 representation, scheme, and port may need careful handling; using the ServiceInstance API keeps code consistent.

### 4.2. Handling a Service ID with No Instances

When a service ID is undeclared or the list is empty, code needs a clear policy:

~~~java
public ServiceInstance requireCatalogInstance() {
    List<ServiceInstance> instances =
            discoveryClient.getInstances("catalog-service");

    if (instances.isEmpty()) {
        throw new IllegalStateException(
                "No instances configured for catalog-service");
    }

    return instances.get(0);
}
~~~

This example picks the first element to demonstrate empty-list checking, not as a production load-balancing strategy. When multiple instances exist, let Spring Cloud LoadBalancer or a dedicated policy choose the instance instead of always calling the first element.

## 5. Does SimpleDiscoveryClient Load Balance on Its Own?

`SimpleDiscoveryClient` supplies the instance list via `DiscoveryClient`. It **does not select an instance per request**. Instance selection is the responsibility of the calling client or a load-balancing mechanism.

Spring Cloud LoadBalancer integrates with DiscoveryClient to fetch the instance list and choose an instance according to the configured policy. Hence, two concepts must be kept separate:

- Discovery answers: which instances does this service have?
- Load balancing answers: which instance should the current request be sent to?

### 5.1. Integrating with WebClient and Spring Cloud LoadBalancer

In reactive applications, you can annotate `WebClient.Builder` with `@LoadBalanced`:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

The service uses the logical name instead of a fixed hostname:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class CatalogClient {

    private final WebClient webClient;

    public CatalogClient(WebClient.Builder loadBalancedWebClientBuilder) {
        this.webClient = loadBalancedWebClientBuilder.build();
    }

    public Mono<String> getProduct(String productId) {
        return webClient.get()
                .uri("http://catalog-service/api/products/{id}", productId)
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

In the URI, `catalog-service` is the service ID. Spring Cloud LoadBalancer finds instances via DiscoveryClient and selects an appropriate instance. The application needs a compatible Spring Cloud LoadBalancer dependency and WebClient/load-balancer configuration matching the version in use.

Without a load-balanced client, a URI containing a service name may be treated by the HTTP client as an ordinary DNS hostname. Simply declaring SimpleDiscoveryClient does not automatically route all HTTP calls through discovery.

### 5.2. Instance Selection Strategy

The instance list is input to the load balancer. The selection strategy may be round robin or another policy depending on configuration and version. Do not assume YAML list order guarantees the first instance is always called, or that zone metadata automatically triggers local-zone preference.

If you need zone preference, sticky behavior, weighted routing, or metadata-based filtering, configure the corresponding Spring Cloud LoadBalancer supplier/policy. Do not scatter selection logic across business services.

## 6. When Is SimpleDiscoveryClient Activated?

In typical Spring Cloud configurations, `SimpleDiscoveryClient` is the fallback option when no other `DiscoveryClient` implementation is provided. If an application adds a discovery provider such as Eureka or Consul, auto-configuration may stop selecting SimpleDiscoveryClient as the default implementation because another provider is present.

This means merely adding `spring.cloud.discovery.client.simple.instances` in YAML does not guarantee the static list will be merged with data from another registry.

When an application has multiple discovery implementations, clearly verify:

- Which `DiscoveryClient` bean is being created.
- What ordering or composite mechanism is in use.
- Which supplier feeds LoadBalancer's instance list.
- Whether any provider backs off in auto-configuration due to bean conditions.

Do not assume SimpleDiscoveryClient and Eureka/Consul automatically merge all instances. If combining multiple sources is truly required, design an appropriate composite or supplier and test ordering, deduplication, and error handling.

## 7. SimpleDiscoveryClient Is Not a Service Registry

A static list can supply discovery information, but it lacks the capabilities of a dynamic registry.

| Capability | SimpleDiscoveryClient from Config |
| --- | --- |
| Retrieve instance list by service ID | Yes |
| Return declared service list | Yes |
| Read instance metadata | Yes |
| Auto-register local instance on startup | No |
| Heartbeat/lease with registry | No |
| Detect dead instances automatically | No |
| Auto-deregister on app shutdown | No |
| Track autoscaling or IP changes | No |
| Propagate updates to other clients | No |

If an endpoint goes down, the instance may still remain in the configured list. Requests will fail unless health-check integration, retries, a circuit breaker, or another list-refresh mechanism is in place.

For systems with frequently changing instances, a dynamic registry or platform-provided discovery is generally more suitable. SimpleDiscoveryClient can still be useful for tests or fixed endpoints, but should not be treated as an instance lifecycle management system.

## 8. Testing SimpleDiscoveryClient

An integration test can load an instance list from test properties and verify DiscoveryClient output.

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
        "spring.cloud.discovery.client.simple.instances.catalog-service[0].uri=http://catalog-a.test:8081",
        "spring.cloud.discovery.client.simple.instances.catalog-service[0].metadata.zone=zone-a",
        "spring.cloud.discovery.client.simple.instances.catalog-service[1].uri=http://catalog-b.test:8081",
        "spring.cloud.discovery.client.simple.instances.catalog-service[1].metadata.zone=zone-b"
})
class SimpleDiscoveryClientTest {

    @Autowired
    DiscoveryClient discoveryClient;

    @Test
    void returnsConfiguredInstances() {
        List<ServiceInstance> instances =
                discoveryClient.getInstances("catalog-service");

        assertThat(instances).hasSize(2);
        assertThat(instances)
                .extracting(ServiceInstance::getHost)
                .containsExactly("catalog-a.test", "catalog-b.test");

        assertThat(instances.get(0).getPort()).isEqualTo(8081);
        assertThat(instances.get(0).getMetadata().get("zone"))
                .isEqualTo("zone-a");
    }

    @Test
    void returnsEmptyListForUnknownService() {
        assertThat(discoveryClient.getInstances("unknown-service"))
                .isEmpty();
    }

    @Test
    void exposesConfiguredServiceIds() {
        assertThat(discoveryClient.getServices())
                .contains("catalog-service");
    }
}
~~~

This test assumes the context has no other discovery provider causing SimpleDiscoveryClient auto-configuration to back off. If the test shares an application context with Eureka, Consul, or another provider, inspect the injected bean before concluding SimpleDiscoveryClient configuration was ignored.

### 8.1. Testing the Load-Balancing Flow

Beyond testing discovery, verify that the client actually uses Spring Cloud LoadBalancer:

- Configure two reachable test instances.
- Call a URI by service ID through a `@LoadBalanced` client.
- Verify requests are sent to the selected instance.
- Test behavior when one instance fails or is unreachable.
- Test retry/circuit breaker behavior if enabled by the application.

Do not merely check the instance list and conclude load balancing works. The two layers have distinct responsibilities and need separate tests.

## 9. Updating Instance Lists and Managing Environments

A static instance list is part of configuration. When endpoints change, update the configuration source and deploy/refresh per the application's policy.

Several notes:

- For local/test, use profiles or test properties to supply dedicated lists.
- For staging/production, manage endpoints in controlled configuration sources and avoid committing sensitive environment details.
- When an instance is replaced, update the URI and verify clients stop calling the old endpoint.
- Do not assume editing YAML on disk automatically updates bound objects in a running JVM.
- If using Spring Cloud Config and refresh, verify the exact version and property rebinding/refresh mechanism. Updating the Environment does not guarantee every consumer has picked up the new list.
- For frequently changing lists, evaluate a dynamic registry rather than continually editing static configuration.

When multiple profiles exist, test the final resolved list after Config Data and property source precedence are applied. Pay close attention to list binding rules when a profile overrides common configuration.

## 10. Security and Operations

Instance lists often contain internal hostnames, IPs, ports, and metadata. This is system topology data and must be managed appropriately:

- Do not commit sensitive internal endpoints to public repositories.
- Do not put tokens, passwords, or credentials into metadata.
- Use proper TLS and trust configuration when instances use HTTPS.
- Restrict permissions to modify discovery configuration; wrong endpoints can redirect traffic to unintended hosts.
- Monitor service IDs with zero instances and instance connection errors.
- Record effective configuration per environment without logging secrets.
- Verify DNS, routing, firewalls, and network policies from the client's network namespace.
- Maintain an update process for endpoints when instances change or are removed.

A syntactically valid URI does not prove a service is running. Use health checks or connectivity checks at the appropriate layer if operations must know whether an instance is still serving.

## 11. Common Mistakes and How to Avoid Them

1. **Calling the wrong service ID:** keys under `instances` must match the logical name requested by the client.
2. **Confusing SimpleDiscoveryClient with a registry:** static lists have no heartbeats, registration, or deregistration.
3. **Expecting SimpleDiscoveryClient to load balance on its own:** Spring Cloud LoadBalancer or custom selection code is needed.
4. **Missing LoadBalancer dependency:** `@LoadBalanced` has no effect if the corresponding dependency and auto-configuration are absent.
5. **Assuming YAML list order dictates requests:** the load balancer policy determines which instance is selected.
6. **Expecting metadata to filter instances automatically:** a supplier/policy reading that metadata is required.
7. **Declaring another provider while expecting the simple list to merge:** verify auto-configuration and the active DiscoveryClient bean.
8. **Using local endpoints in production:** separate configs via profiles and verify the effective list.
9. **Believing listed instances are healthy:** SimpleDiscoveryClient does not probe health automatically.
10. **Editing config files and expecting the JVM to reload automatically:** verify the reload/rebind mechanism or redeploy.
11. **Skipping DNS/routing tests:** a hostname resolving from a developer machine may not resolve from the client's container.
12. **Putting secrets in metadata:** store only non-sensitive info and restrict log/diagnostic access.

## 12. Adoption Workflow

When using SimpleDiscoveryClient in a Spring Cloud application, follow this sequence:

1. Identify the service IDs that clients need to call.
2. Declare each instance under `spring.cloud.discovery.client.simple.instances`.
3. Use URIs with accurate scheme, hostname, and port; add metadata only when consumers use it.
4. Verify SimpleDiscoveryClient is actually the active DiscoveryClient implementation.
5. If calling by service ID, configure Spring Cloud LoadBalancer and a `@LoadBalanced` client.
6. Inspect the list using `DiscoveryClient.getInstances()` and `getServices()`.
7. Write tests for multi-instance services, nonexistent services, and metadata.
8. Test instance selection and actual network connectivity separately.
9. Separate lists per profile/environment and verify merge rules.
10. Evaluate a dynamic registry if instances change frequently.

**Key takeaway:** SimpleDiscoveryClient turns instance lists declared in configuration into data for the DiscoveryClient abstraction. It fits static endpoints, local development, demos, and tests; Spring Cloud LoadBalancer can use this list to pick instances when clients are properly configured. A static list does not handle self-registration, heartbeats, health checks, or lifecycle updates. Keep discovery, load balancing, and service registration clearly separated when designing inter-service communication in **SPRING_CLOUD_CORE**.
