# Testing Multiple Instances with SimpleDiscoveryClient

When testing service discovery, you do not always need to stand up Eureka, Consul, or an external registry. Spring Cloud Commons includes `SimpleDiscoveryClient`, a `DiscoveryClient` that reads the service instance list from configuration. You can declare multiple endpoints for the same service ID, then verify discovery returns the right list and Spring Cloud LoadBalancer selects a valid endpoint.

This approach suits unit/integration tests that need to simulate multiple replicas, verify URIs, ports, metadata, instance selection, and HTTP routing. It also lets you test client-side load balancing logic without depending on a registry server, network deployment, or registry convergence timing.

This lesson belongs to the **Testing** chapter of the **SPRING_CLOUD_CORE** module. It progresses from configuring `SimpleDiscoveryClient`, testing `DiscoveryClient` directly, testing LoadBalancer selection across multiple instances, to HTTP integration tests with two mock servers and a health-check supplier.

## 1. What Is SimpleDiscoveryClient Used For?

`SimpleDiscoveryClient` is an implementation of `DiscoveryClient`. It reads service and instance information from properties prefixed with:

~~~text
spring.cloud.discovery.client.simple.instances
~~~

Example of a service with two instances:

~~~properties
spring.cloud.discovery.client.simple.instances.catalog-service[0].uri=http://127.0.0.1:8081
spring.cloud.discovery.client.simple.instances.catalog-service[1].uri=http://127.0.0.1:8082
~~~

Where:
- `catalog-service` is the service ID used by the consumer in logical URIs.
- `[0]` and `[1]` are zero-based indices of the instances in the list.
- `uri` is the actual address of each instance.
- Each URI can carry its own scheme, hostname/IP, and port.

When the application calls `DiscoveryClient.getInstances("catalog-service")`, `SimpleDiscoveryClient` returns two `ServiceInstance` objects matching the two configured URIs.

### 1.1. When Is SimpleDiscoveryClient Used?

Spring Cloud Commons uses `SimpleDiscoveryClient` when the classpath has no `DiscoveryClient` backed by a service registry such as Eureka, Consul, or Zookeeper.

This means:
- Adding `spring-cloud-starter-loadbalancer` alone does not start a registry server.
- If the test classpath contains a Eureka/Consul discovery client, `SimpleDiscoveryClient` may not be the default `DiscoveryClient` implementation selected.
- If your goal is testing `SimpleDiscoveryClient`, use a test slice/context containing only Spring Cloud Commons and LoadBalancer without pulling in unnecessary registry clients.
- If you want to test Eureka/Consul behavior, write a separate integration test with that registry implementation.

In modern Spring Cloud, `@EnableDiscoveryClient` is no longer required solely to enable discovery; placing the corresponding implementation on the classpath activates its auto-configuration.

### 1.2. SimpleDiscoveryClient Is Not a Dynamic Registry

`SimpleDiscoveryClient` reads its list from configuration. It does not automatically provide features such as:
- Registering and deregistering instances with a registry server.
- Heartbeats or leases to detect dead processes.
- State synchronization across multiple clients.
- Auto-discovering new Pods/containers.
- Updating the list from an external management system.

Therefore, it fits simulating a known instance list in tests or simple environments. It does not prove a real registry behaves properly in production.

## 2. Declaring Multiple Instances in application.yml

The list can be declared in YAML:

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
              - uri: http://127.0.0.1:8081
                metadata:
                  zone: test-a
                  version: v1
              - uri: http://127.0.0.1:8082
                metadata:
                  zone: test-b
                  version: v1
~~~

The configuration above creates two `ServiceInstance` entries for `catalog-service`. Each instance has its own URI and metadata.

If using `application.properties`:

~~~properties
spring.application.name=order-service
spring.cloud.discovery.client.simple.instances.catalog-service[0].uri=http://127.0.0.1:8081
spring.cloud.discovery.client.simple.instances.catalog-service[0].metadata.zone=test-a
spring.cloud.discovery.client.simple.instances.catalog-service[0].metadata.version=v1
spring.cloud.discovery.client.simple.instances.catalog-service[1].uri=http://127.0.0.1:8082
spring.cloud.discovery.client.simple.instances.catalog-service[1].metadata.zone=test-b
spring.cloud.discovery.client.simple.instances.catalog-service[1].metadata.version=v1
~~~

### 2.1. Service ID and URI Are Two Different Values

The consumer sends a request to the service ID:

~~~text
http://catalog-service/api/products
~~~

The instance list maps that service ID to real URIs:

~~~text
catalog-service
  ├── http://127.0.0.1:8081
  └── http://127.0.0.1:8082
~~~

Do not use the logical hostname `catalog-service` as a fixed address of an instance inside `SimpleDiscoveryClient`. LoadBalancer takes the service ID, retrieves the `ServiceInstance` list, and picks an actual URI.

### 2.2. URI Determines Host, Port, and Secure Flag

An HTTP URI:

~~~text
http://127.0.0.1:8081
~~~

An HTTPS URI:

~~~text
https://catalog-b.internal:8443
~~~

Host, port, and secure flag are derived from the URI. When testing HTTPS, beyond checking the secure flag, configure appropriate trust material for the HTTP client; `SimpleDiscoveryClient` does not generate certificates or bypass TLS validation.

### 2.3. List Indices Start at 0

Properties take the form:

~~~properties
spring.cloud.discovery.client.simple.instances.catalog-service[0].uri=http://127.0.0.1:8081
spring.cloud.discovery.client.simple.instances.catalog-service[1].uri=http://127.0.0.1:8082
spring.cloud.discovery.client.simple.instances.catalog-service[2].uri=http://127.0.0.1:8083
~~~

Index `0` is the first element. Keep indices contiguous so configuration stays readable and avoids mistakes when editing the list. In tests, verify both the count and URI of every instance.

## 3. Adding Required Dependencies

To test discovery and instance selection, the project needs Spring Cloud Commons and Spring Cloud LoadBalancer. Common dependencies are:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Use a Spring Cloud BOM compatible with Spring Boot to manage starter versions. Never arbitrarily pin a LoadBalancer version from a different release train than the remaining Spring Cloud modules.

When testing HTTP requests via mock servers, you can add `MockWebServer` in test scope:

~~~xml
<dependency>
    <groupId>com.squareup.okhttp3</groupId>
    <artifactId>mockwebserver</artifactId>
    <scope>test</scope>
</dependency>
~~~

Choose a `MockWebServer` version compatible with the OkHttp dependency managed by your project. If dependency management does not provide a version, declare the test version explicitly.

There is no need to add Eureka Server or Consul just to test `SimpleDiscoveryClient`.

## 4. Testing DiscoveryClient Returning Multiple Instances

The first step is verifying configuration binds properly and `DiscoveryClient` returns the expected list. This test focuses on discovery without testing LoadBalancer or HTTP requests yet.

Example:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

@SpringBootTest(
        classes = SimpleDiscoveryClientTests.TestApplication.class,
        properties = {
                "spring.application.name=order-service",
                "spring.cloud.discovery.client.simple.instances.catalog-service[0].uri=http://127.0.0.1:8081",
                "spring.cloud.discovery.client.simple.instances.catalog-service[1].uri=http://127.0.0.1:8082"
        }
)
class SimpleDiscoveryClientTests {

    @Autowired
    DiscoveryClient discoveryClient;

    @Test
    void returnsBothConfiguredInstances() {
        List<ServiceInstance> instances =
                discoveryClient.getInstances("catalog-service");

        assertThat(instances).hasSize(2);
        assertThat(instances)
                .extracting(ServiceInstance::getUri)
                .containsExactly(
                        URI.create("http://127.0.0.1:8081"),
                        URI.create("http://127.0.0.1:8082")
                );
    }

    @Test
    void returnsEmptyListForUnknownService() {
        assertThat(discoveryClient.getInstances("unknown-service"))
                .isEmpty();
    }

    @Test
    void exposesConfiguredServiceId() {
        assertThat(discoveryClient.getServices())
                .contains("catalog-service");
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {
    }
}
~~~

This test verifies:
- Two instance properties bind into two `ServiceInstance` objects.
- Configuration list order is preserved.
- The service ID is exposed in the services list.
- A nonexistent service returns an empty list.

### 4.1. Why Use DiscoveryClient Instead of Calling SimpleDiscoveryClient Directly?

`DiscoveryClient` is the abstraction used by application consumers. Testing through the abstraction verifies Spring context wiring and the behavior business code actually sees.

If the goal is testing `SimpleDiscoveryClient`'s property mapping specifically, you can inject `SimpleDiscoveryProperties` or `SimpleDiscoveryClient` in a dedicated test. However, testing via `DiscoveryClient` is better suited for verifying application-level integration.

### 4.2. Verifying Metadata

If the application uses metadata to filter by zone or version, verify metadata binds properly:

~~~java
@Test
void bindsMetadataForEachInstance() {
    List<ServiceInstance> instances =
            discoveryClient.getInstances("catalog-service");

    assertThat(instances).hasSize(2);
    assertThat(instances.get(0).getMetadata())
            .containsEntry("zone", "test-a")
            .containsEntry("version", "v1");
    assertThat(instances.get(1).getMetadata())
            .containsEntry("zone", "test-b")
            .containsEntry("version", "v1");
}
~~~

Metadata supplies attributes for suppliers or custom LoadBalancers to apply filtering policies. Declaring metadata alone does not automatically enable zone/version routing; you must configure the corresponding supplier if you want to filter instances by those fields.

## 5. Testing LoadBalancer Instance Selection from the List

`DiscoveryClient` only returns the list. Spring Cloud LoadBalancer decides which instance is chosen for each request.

LoadBalancer uses `ServiceInstanceListSupplier` to obtain the instance list. The default configuration uses `RoundRobinLoadBalancer`; you can also swap in `RandomLoadBalancer` or a custom implementation.

With blocking APIs, you can use `LoadBalancerClient`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.LoadBalancerClient;
import org.springframework.cloud.client.discovery.DiscoveryClient;

@SpringBootTest(
        classes = LoadBalancerSelectionTests.TestApplication.class,
        properties = {
                "spring.application.name=order-service",
                "spring.cloud.discovery.client.simple.instances.catalog-service[0].uri=http://127.0.0.1:8081",
                "spring.cloud.discovery.client.simple.instances.catalog-service[1].uri=http://127.0.0.1:8082",
                "spring.cloud.loadbalancer.cache.enabled=false"
        }
)
class LoadBalancerSelectionTests {

    @Autowired
    DiscoveryClient discoveryClient;

    @Autowired
    LoadBalancerClient loadBalancerClient;

    @Test
    void selectsOnlyFromConfiguredInstances() {
        List<URI> configuredUris = discoveryClient
                .getInstances("catalog-service")
                .stream()
                .map(ServiceInstance::getUri)
                .toList();

        for (int attempt = 0; attempt < 6; attempt++) {
            ServiceInstance selected =
                    loadBalancerClient.choose("catalog-service");

            assertThat(selected).isNotNull();
            assertThat(configuredUris).contains(selected.getUri());
        }
    }

    @Test
    void returnsNoInstanceForUnknownService() {
        assertThat(loadBalancerClient.choose("missing-service"))
                .isNull();
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {
    }
}
~~~

This test verifies LoadBalancer selects only from the list supplied by `SimpleDiscoveryClient`. It does not assert an exact selection sequence; thus the test does not depend on child context initialization order or another custom algorithm enabled in the test environment.

### 5.1. Deliberately Testing Round-Robin

If you want to verify the round-robin algorithm, pin the test configuration to `RoundRobinLoadBalancer` and invoke selection multiple times. With two instances and the default algorithm, consecutive selections alternate between the two items.

Do not write a round-robin test and run it in a context where the application might override it with `RandomLoadBalancer` or a custom policy. In that case, assertions on a specific selection sequence will fail.

An application-level test typically only needs to verify:
- Non-null result when the list contains instances.
- The chosen URI belongs to the configured list.
- Requests route to a valid endpoint.
- A service with no instances does not fabricate a dummy address.

If business logic requires even distribution, test the algorithm separately and pin the policy in that test.

### 5.2. Disabling Caching in Tests

Spring Cloud LoadBalancer caches the instance list. The current default configuration uses a 35-second TTL. Caching helps production, yet can make tests unpredictable if tests alter instance sources or expect changes to appear immediately.

In tests needing direct list reads, you can set:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false
~~~

Or the equivalent property:

~~~properties
spring.cloud.loadbalancer.cache.enabled=false
~~~

Disabling cache is not a general production recommendation. In production, caching reduces discovery call overhead; if `DiscoveryClient` already caches internally, avoid unnecessary double caching.

## 6. Testing HTTP Requests Across Two Mock Instances

Testing `DiscoveryClient` and `LoadBalancerClient` only verifies the list and selection. To prove the HTTP client actually forwards requests to multiple endpoints, stand up two mock HTTP servers on dynamic ports.

`MockWebServer` is a lightweight choice for integration tests:
- Server A returns body `node-a`.
- Server B returns body `node-b`.
- `SimpleDiscoveryClient` receives both server URIs via `DynamicPropertySource`.
- A `@LoadBalanced` `RestTemplate` calls service ID `catalog-service`.
- The test sends multiple requests and verifies both servers received requests.

Example test application configuration:

~~~java
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.web.client.RestTemplate;

@SpringBootConfiguration
@EnableAutoConfiguration
class LoadBalancedTestApplication {

    @Bean
    @LoadBalanced
    RestTemplate catalogRestTemplate(RestTemplateBuilder builder) {
        return builder.build();
    }
}
~~~

Example integration test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.client.RestTemplate;

@SpringBootTest(
        classes = LoadBalancedTestApplication.class,
        properties = {
                "spring.application.name=order-service",
                "spring.cloud.loadbalancer.cache.enabled=false",
                "spring.cloud.loadbalancer.retry.enabled=false"
        }
)
class SimpleDiscoveryHttpIntegrationTests {

    static final MockWebServer NODE_A = new MockWebServer();
    static final MockWebServer NODE_B = new MockWebServer();

    static {
        try {
            NODE_A.start();
            NODE_B.start();
            NODE_A.setDispatcher(dispatcherFor("node-a"));
            NODE_B.setDispatcher(dispatcherFor("node-b"));
        }
        catch (IOException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    @Autowired
    @LoadBalanced
    RestTemplate restTemplate;

    @DynamicPropertySource
    static void registerInstances(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.cloud.discovery.client.simple.instances.catalog-service[0].uri",
                () -> NODE_A.url("/").toString()
        );
        registry.add(
                "spring.cloud.discovery.client.simple.instances.catalog-service[1].uri",
                () -> NODE_B.url("/").toString()
        );
    }

    @Test
    void routesRequestsToBothConfiguredInstances() {
        List<String> responses = IntStream.range(0, 6)
                .mapToObj(index -> restTemplate.getForObject(
                        "http://catalog-service/node",
                        String.class
                ))
                .toList();

        Set<String> distinctResponses = responses.stream()
                .collect(Collectors.toSet());

        assertThat(distinctResponses)
                .containsExactlyInAnyOrder("node-a", "node-b");
        assertThat(NODE_A.getRequestCount()).isPositive();
        assertThat(NODE_B.getRequestCount()).isPositive();
    }

    @AfterAll
    static void stopServers() throws IOException {
        NODE_A.shutdown();
        NODE_B.shutdown();
    }

    private static Dispatcher dispatcherFor(String nodeName) {
        return new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest request) {
                return new MockResponse()
                        .setResponseCode(200)
                        .addHeader("Content-Type", "text/plain")
                        .setBody(nodeName);
            }
        };
    }
}
~~~

This example assumes LoadBalancer uses the default `RoundRobinLoadBalancer` with no custom policy overriding it. If the project uses another algorithm, replace the distribution assertion with one matching the configured policy.

### 6.1. Why Use Dynamic Ports?

Do not hard-code 8081 and 8082 for `MockWebServer` in tests:
- CI may run multiple test suites simultaneously.
- Ports may already be occupied by another process.
- Tests may run on developer machines with different topologies.
- Dynamic ports reduce environment conflicts.

`DynamicPropertySource` registers URIs after the test servers open their ports. `SimpleDiscoveryClient` receives these real addresses when the `ApplicationContext` is created.

### 6.2. HTTP Tests Differ from Instance Selection Tests

| Test | What it proves |
| --- | --- |
| DiscoveryClient test | Properties map into a `ServiceInstance` list |
| LoadBalancerClient test | Algorithm selects an instance from the list |
| HTTP integration test | Client replaces service ID with instance URI and requests reach a real server |
| Health-check test | Supplier excludes or retains instances based on health probe results |
| Registry integration test | Behavior with a real registry server, if the application uses a registry |

Never substitute one test type for another. A passing `DiscoveryClient` test does not prove HTTP requests reach the endpoint; a passing HTTP test does not prove health-check or registry lifecycle behavior.

## 7. Testing Health Checks with SimpleDiscoveryClient

`SimpleDiscoveryClient` reads a static list from properties. It does not check whether endpoints are alive. If an instance stops responding while remaining in configuration, the discovery list can still contain it.

Spring Cloud LoadBalancer provides `HealthCheckServiceInstanceListSupplier` to probe instances periodically. This mechanism is especially helpful when using `SimpleDiscoveryClient`.

Configuration example:

~~~yaml
spring:
  cloud:
    loadbalancer:
      configurations: health-check
      health-check:
        initial-delay: 1s
        interval: 5s
        path:
          catalog-service: /actuator/health
~~~

The default health check uses `/actuator/health` unless another path is configured. When using this endpoint, mock servers must expose the corresponding endpoint and tests must wait for the scheduler to complete at least one cycle before asserting the healthy list.

### 7.1. Health Checks Need a Real Endpoint

If instance A returns 200 for `/actuator/health` while instance B returns 503, the supplier can emit only instance A in the healthy list once probe results update.

In tests:
- Start two mock servers.
- Configure each server to return a different health status.
- Enable the health-check supplier.
- Wait for the first check to finish.
- Read the instance list from the supplier or call LoadBalancer.
- Verify requests target the healthy list.

Avoid overly long fixed sleeps when you can observe completion conditions or tune scheduler timing. When waiting is necessary, use Awaitility or bounded polling instead of arbitrary delays.

### 7.2. Health Check Is Not a Registry Heartbeat

`HealthCheckServiceInstanceListSupplier` sends client-side probes to configured URIs. It does not send heartbeats to Eureka/Consul and does not update status in a registry server.

Because `SimpleDiscoveryClient` has no registry server, health checks act as an extra layer helping LoadBalancer avoid unhealthy endpoints. Real service registries typically provide instance health state already and may not need duplicate probing.

### 7.3. Configuring Refetch Instances

If the underlying delegate's instance list can change without emitting an update stream, you can enable:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        refetch-instances: true
        refetch-instances-interval: 10s
        repeat-health-check: false
~~~

`refetch-instances` instructs the supplier to reload the list periodically. It does not turn `application.yml` into a dynamic registry source; `SimpleDiscoveryClient` still reads from Environment and bound properties.

If you need to alter the instance list at runtime, update the configuration source with an appropriate refresh mechanism or use a `DiscoveryClient`/registry implementation that genuinely supports dynamic instance updates.

### 7.4. Handling All Instances Unhealthy

Do not write tests assuming that when every health check fails, the supplier always returns an empty list. Fallback behavior can differ across implementations/versions; current documentation notes that the supplier may return the previously fetched list when no healthy instances exist.

Check the exact Spring Cloud BOM version you run and define the fail-open/fail-closed policy your application requires. If safety demands sending zero traffic when no healthy instances exist, test that condition explicitly and configure/customize the supplier accordingly.

## 8. Testing Metadata and Instance Filtering

`SimpleDiscoveryClient` supports per-instance metadata. Metadata can simulate zones, versions, capabilities, or deployment groups.

Example:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
                metadata:
                  zone: zone-a
                  version: v1
              - uri: http://127.0.0.1:8082
                metadata:
                  zone: zone-b
                  version: v2
~~~

If LoadBalancer is configured with `ZonePreferenceServiceInstanceListSupplier`, it can prefer instances in the same zone. With `SimpleDiscoveryClient`, zones can be supplied via metadata and `spring.cloud.loadbalancer.zone`.

### 8.1. Testing Metadata Is Not Testing Filtering

First verify metadata binds properly:

~~~java
assertThat(instances.get(0).getMetadata())
        .containsEntry("zone", "zone-a");
~~~

Then test the supplier or LoadBalancer:
- When the client zone is `zone-a`, the `zone-a` instance is preferred.
- When no instance matches the zone, verify fallback policy per supplier.
- When metadata is missing, test behavior explicitly.

Declaring metadata in YAML alone does not make LoadBalancer filter automatically. Configure the matching supplier or implement a custom filtering policy.

### 8.2. Testing Version-Aware Selection

If the application filters instances by API version, declare version metadata on each instance and configure the matching API version supplier. Tests should cover:
- Matching version instance exists.
- No matching version instance exists.
- `fallback-to-available-instances` enabled or disabled.
- Request missing version when policy requires a version.
- Consumer receives the right endpoint per policy.

Do not merge API version tests with basic `SimpleDiscoveryClient` tests; keep foundational tests verifying list/selection first, then extend to filters.

## 9. Testing Multiple Service IDs

A single `SimpleDiscoveryClient` can hold multiple services:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
              - uri: http://127.0.0.1:8082
            inventory-service:
              - uri: http://127.0.0.1:8091
              - uri: http://127.0.0.1:8092
              - uri: http://127.0.0.1:8093
~~~

Each service ID has an independent instance list. LoadBalancer also creates a separate context per service ID and initializes it lazily on the first load-balanced request.

Tests should verify:
- `catalog-service` has exactly two instances.
- `inventory-service` has exactly three instances.
- Selecting `catalog-service` never returns a URI belonging to `inventory-service`.
- Nonexistent service IDs have no instances.
- Metadata across services never mixes.

If you need to eagerly initialize LoadBalancer child contexts for specific services, use `spring.cloud.loadbalancer.eager-load.clients`. In simple tests, leave eager load disabled unless specifically testing startup or child context setup.

## 10. Caching and Test Stability

Spring Cloud LoadBalancer includes a caching implementation. The LoadBalancer starter provides a default cache; if Caffeine is on the classpath, Caffeine caching may be used.

Common properties:

| Property | Purpose |
| --- | --- |
| `spring.cloud.loadbalancer.cache.enabled` | Enable/disable LoadBalancer cache |
| `spring.cloud.loadbalancer.cache.ttl` | Cache entry time-to-live |
| `spring.cloud.loadbalancer.cache.capacity` | Initial cache capacity |
| `spring.cloud.loadbalancer.health-check.refetch-instances` | Tell health-check supplier to reload instance list |
| `spring.cloud.loadbalancer.health-check.refetch-instances-interval` | Interval for refetching the list |

When to disable caching in tests:
- Tests mutate property sources between calls.
- Tests expect to see updated lists immediately after applying configuration.
- Tests isolate `DiscoveryClient` behavior without an extra cache layer.

When to keep caching enabled in tests:
- Testing cache/TTL policies.
- Testing behavior when the instance list changes before cache expiration.
- Testing performance or `DiscoveryClient` call counts.
- Testing cache eviction.

Do not disable caching mechanically in every test. Choose based on the behavior under test.

## 11. Testing Retries and Instance Failures

When an instance returns an error or drops the connection, retries can obscure test behavior because one logical request triggers multiple instance selections.

In tests verifying basic routing, disable retry so results reflect a single attempt:

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: false
~~~

When testing retries, enable retry intentionally and verify:
- Whether retries target the same instance or the next instance.
- Which exceptions/status codes trigger retry.
- Which HTTP methods are retryable.
- Maximum retry count.
- Whether the recently failed instance is avoided.
- Final outcome when all instances fail.

Do not use side-effecting POST requests to test retries unless the mock server enforces idempotency keys or duplicate prevention. For basic tests, GET requests returning the node name suffice.

## 12. Comparing SimpleDiscoveryClient Tests vs. Real Registry Tests

| Goal | SimpleDiscoveryClient | Real registry |
| --- | --- | --- |
| Test property mapping | Suitable | Unnecessary |
| Test multiple static endpoints | Suitable | Possible, but heavier |
| Test LoadBalancer instance selection | Suitable | Suitable |
| Test HTTP routing to instances | Suitable with mock servers | Suitable |
| Test register/heartbeat/deregister | Not supported | Real registry required |
| Test lease, TTL, and registry health state | Not supported | Real registry required |
| Test discovery updates as instances appear/disappear | Not automatic | Real registry required |
| Test registry networking and auth | Not supported | Real registry required |

`SimpleDiscoveryClient` makes tests fast and isolates consumer logic. When a system relies on Eureka/Consul/Zookeeper-specific behavior, integration tests against the corresponding implementation remain necessary.

## 13. Common Mistakes

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| DiscoveryClient returns empty list | Wrong service ID or property prefix | Check service name and `simple.instances` |
| Only one instance returned | Missing index or malformed key | Check zero-based indices and list binding |
| SimpleDiscoveryClient not used | A registry-backed DiscoveryClient is on classpath | Isolate test classpath or explicitly select implementation |
| LoadBalancer fails to choose instance | Missing starter or LoadBalancer disabled | Add starter and check `spring.cloud.loadbalancer.enabled` |
| Calling `http://catalog-service` fails with DNS error | Client is not marked load-balanced | Use `@LoadBalanced` bean/client and service ID URI |
| Instance selection test is flaky | Using `RandomLoadBalancer` or custom policy | Assert valid URI set or pin algorithm in test |
| Test misses newly changed property | LoadBalancer cache still active | Disable cache in test or wait for TTL/evict properly |
| Dead instance still selected | `SimpleDiscoveryClient` has no default health check | Enable `HealthCheckServiceInstanceListSupplier` |
| Health check always fails | Mock server lacks health path or wrong port | Configure path/port and verify endpoint |
| One node receives no traffic in HTTP test | Algorithm is not round-robin or retry/cache altered outcome | Check policy, request count, and test setup |
| Test fails with port already in use | Hard-coded ports across parallel test processes | Use `MockWebServer` or dynamic ports |
| Metadata present yet no filtering occurs | Matching supplier not configured | Enable zone/version/hint supplier and test policy |
| List unchanged after editing YAML | `SimpleDiscoveryClient` does not auto-refresh config files | Create a new context or use a dynamic discovery source |

## 14. Step-by-Step Workflow from Simple to Integration Tests

An effective progression:

1. Declare at least two instances for a service ID.
2. Test that `DiscoveryClient` returns the right count, URIs, and metadata.
3. Test that an unknown service ID returns an empty list.
4. Add the Spring Cloud LoadBalancer starter.
5. Test that LoadBalancer selects an instance from the list.
6. If needed, pin `RoundRobinLoadBalancer` to test distribution.
7. Start two mock HTTP servers on dynamic ports.
8. Send requests through a `@LoadBalanced` client and verify both servers receive traffic.
9. Enable the health-check supplier and simulate an unhealthy node.
10. Test cache, retry, metadata filters, or API versions in dedicated tests.
11. Use a real registry for behavior `SimpleDiscoveryClient` cannot simulate.

Diagram:

~~~mermaid
flowchart TD
    A["Declare 2+ URIs for service ID"] --> B["Test SimpleDiscoveryClient"]
    B --> C["Test DiscoveryClient.getInstances"]
    C --> D["Test LoadBalancerClient.choose"]
    D --> E["Test HTTP across 2 mock servers"]
    E --> F["Test health-check supplier"]
    F --> G["Test cache/retry/filter separately"]
    G --> H["Integration test with real registry if needed"]
~~~

## 15. Review Checklist

- [ ] Test classpath does not accidentally include a registry-backed `DiscoveryClient` when testing `SimpleDiscoveryClient`.
- [ ] At least two instances are configured for the same service ID.
- [ ] Property indices start at 0.
- [ ] Every instance URI has a valid host/port.
- [ ] `DiscoveryClient` returns the expected count and URIs.
- [ ] Unknown service IDs return an empty list.
- [ ] `spring-cloud-starter-loadbalancer` is included when testing instance selection.
- [ ] Client uses the logical service ID and is annotated `@LoadBalanced`.
- [ ] Tests do not assume round-robin ordering unless the policy is pinned.
- [ ] HTTP tests use dynamic ports and mock servers.
- [ ] Cache/retry settings match the test goal.
- [ ] Health checks have the right endpoint and path.
- [ ] Metadata filters are tested separately from property binding.
- [ ] `SimpleDiscoveryClient` is never used to draw conclusions about heartbeats or registry lifecycles.
- [ ] Spring Cloud BOM is compatible with the project's Spring Boot version.

## Takeaways

`SimpleDiscoveryClient` lets you declare multiple `ServiceInstance` entries via properties without running a registry server. Test layer by layer: property mapping, `DiscoveryClient`, LoadBalancer selection, and real HTTP requests. Spring Cloud LoadBalancer defaults to round-robin yet can be customized; pin the policy in tests whenever verifying specific distribution behavior. When health filtering is needed, use `HealthCheckServiceInstanceListSupplier` and expose probe endpoints on each instance. `SimpleDiscoveryClient` simulates a static list and does not replace testing registration, heartbeats, or instance updates against a real registry.

## References

- Spring Cloud Commons – Common Abstractions / SimpleDiscoveryClient: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html
- Spring Cloud LoadBalancer: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html
- Spring Cloud Commons – Configuration Properties: https://docs.spring.io/spring-cloud-commons/reference/configprops.html
- Spring Boot – Testing: https://docs.spring.io/spring-boot/reference/testing/index.html
- OkHttp MockWebServer: https://github.com/square/okhttp/tree/master/mockwebserver
