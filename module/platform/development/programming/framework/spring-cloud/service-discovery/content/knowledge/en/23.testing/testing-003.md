# Using SimpleDiscoveryClient to Test Service-Calling Applications

When testing a Spring Cloud application that calls another service, you do not always need to spin up Eureka Server, Consul, or ZooKeeper. With a fixed list of endpoints in the test environment, **SimpleDiscoveryClient** lets you declare instances through configuration and expose them via the `DiscoveryClient` abstraction.

Combining SimpleDiscoveryClient with Spring Cloud LoadBalancer allows the application to still call services by service ID, such as `http://catalog-service/...`. LoadBalancer retrieves the list of instances from the discovery client, selects an address, and forwards the request to the corresponding HTTP server. As a result, integration tests can verify the service-calling flow closely to how the application runs in production without depending on an external registry.

This article covers configuring static instances in tests, inspecting the list via DiscoveryClient, calling providers by service ID with `@LoadBalanced RestTemplate`, using a mock HTTP server to verify requests, and testing scenarios where no instances exist or the provider fails.

## 1. What types of tests does SimpleDiscoveryClient fit?

SimpleDiscoveryClient reads the list of service instances from configuration. It is well suited when:

- You want to test a consumer without starting a real registry.
- The provider has a fixed endpoint in tests or is replaced by a mock HTTP server.
- You want to test service ID, host, port, metadata, and the load-balancing flow.
- You need fast integration tests independent of Docker Compose or registry infrastructure.
- You want to simulate multiple instances using different URIs.

For example, the consumer calls `catalog-service`; in tests, this service ID maps to a mock HTTP server:

~~~mermaid
flowchart LR
    TEST["Integration test"]
    APP["Consumer application"]
    DC["SimpleDiscoveryClient"]
    LB["Spring Cloud LoadBalancer"]
    MOCK["Mock HTTP provider"]
    TEST --> APP
    APP -->|"catalog-service"| LB
    LB --> DC
    DC -->|"URI from test properties"| LB
    LB -->|"HTTP request"| MOCK
~~~

The call flow still uses the service ID. Tests can swap URIs in configuration without modifying consumer code.

SimpleDiscoveryClient does not simulate the full behavior of Eureka, Consul, or ZooKeeper. It does not test heartbeats, dynamic registration, lease expiration, ACLs, watches, registry health checks, or catalog synchronization. Those aspects require separate integration tests with the corresponding registry.

## 2. Required dependencies

A consumer using `RestTemplate` and Spring Cloud LoadBalancer may need the following dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>com.squareup.okhttp3</groupId>
        <artifactId>mockwebserver</artifactId>
        <version>${mockwebserver.version}</version>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`spring-cloud-starter-loadbalancer` provides load-balancing integration and Spring Cloud Commons discovery components. MockWebServer spins up a lightweight HTTP server in tests to receive requests and return mocked responses. Declare the `mockwebserver.version` property matching the compatible OkHttp version your project uses; manage Spring Cloud versions with a Spring Cloud BOM compatible with Spring Boot.

If you are only testing `DiscoveryClient` directly, no HTTP client or mock server is needed. If you are testing the full call flow, you need an HTTP client integrated with Spring Cloud LoadBalancer.

### Avoiding accidental use of a real registry in tests

SimpleDiscoveryClient is typically used as a simple implementation when no other discovery client is present. If the test runtime also includes a Eureka, Consul, or ZooKeeper starter, auto-configuration may pick that implementation instead of the SimpleDiscoveryClient list.

To keep tests deterministic:

- Include only the required discovery dependencies in the test runtime whenever possible.
- Use a test profile or dedicated test configuration.
- Prevent production registry endpoint settings from being loaded in integration tests.
- Verify that the active DiscoveryClient bean actually serves instances from the simple.instances properties.

Never let tests accidentally connect to a shared development or production registry.

## 3. Declaring instances in configuration

SimpleDiscoveryClient uses properties of the form:

~~~text
spring.cloud.discovery.client.simple.instances.<service-id>[<index>].uri
~~~

Example in `application-test.yml`:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:18081
                metadata:
                  zone: test-zone
                  version: v1
              - uri: http://localhost:18082
                metadata:
                  zone: test-zone
                  version: v1
            pricing-service:
              - uri: http://localhost:18083
                metadata:
                  zone: test-zone
                  version: v2
~~~

In this example:

- `catalog-service` has two instances.
- `pricing-service` has one instance.
- Each instance has its own URI and metadata.
- The consumer looks up by service ID without needing to know a concrete host/port.

The URI should include a scheme such as `http` or `https`. Metadata consists of key-value pairs for tests to inspect or apply filters against. It does not automatically create health checks or load-balancing policies.

## 4. Consumer calling a service by service ID

Example configuration of a `RestTemplate` with load-balancing integration:

~~~java
@Configuration(proxyBeanMethods = false)
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate restTemplate(RestTemplateBuilder builder) {
        return builder.build();
    }
}
~~~

`@LoadBalanced` marks the RestTemplate so Spring Cloud LoadBalancer resolves service ID hostnames. If you omit the annotation or use a RestTemplate without the load-balancing interceptor, `catalog-service` will be treated as a regular DNS hostname.

Consumer code only needs to know the service ID:

~~~java
@Service
public class CatalogClient {

    private final RestTemplate restTemplate;

    public CatalogClient(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public CatalogItem find(String id) {
        return restTemplate.getForObject(
            "http://catalog-service/api/items/{id}",
            CatalogItem.class,
            id
        );
    }
}
~~~

Response DTO:

~~~java
public record CatalogItem(String id, String name) {
}
~~~

When `find("42")` is called, LoadBalancer looks up `catalog-service`, selects a `ServiceInstance` provided by SimpleDiscoveryClient, and replaces the service ID with the actual URI before sending the HTTP request.

## 5. Testing DiscoveryClient directly

You can test the instance list and metadata without sending HTTP requests:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class SimpleDiscoveryClientTest {

    @Autowired
    DiscoveryClient discoveryClient;

    @Test
    void returnsConfiguredInstancesAndMetadata() {
        List<ServiceInstance> instances =
            discoveryClient.getInstances("catalog-service");

        assertEquals(2, instances.size());
        assertTrue(instances.stream().anyMatch(instance ->
            "test-zone".equals(instance.getMetadata().get("zone"))
                && "v1".equals(instance.getMetadata().get("version"))));
    }

    @Test
    void returnsEmptyListForUnknownService() {
        List<ServiceInstance> instances =
            discoveryClient.getInstances("unknown-service");

        assertTrue(instances.isEmpty());
    }
}
~~~

The first test verifies that the service ID has the expected instance count and metadata. The second verifies that an undeclared service ID returns an empty list.

If instance order is not part of the contract, avoid checking host/port by a fixed index in the list. You can assert by converting the list into a set of URIs or looking up instances by metadata so tests do not depend on ordering.

## 6. Integration testing with MockWebServer

Testing DiscoveryClient alone only proves configuration was read. To verify that the application actually sends requests to a provider, use an HTTP mock server on a dynamic port.

### Starting a mock provider and passing its URI to SimpleDiscoveryClient

~~~java
@SpringBootTest
@ActiveProfiles("mock-provider")
class CatalogClientIntegrationTest {

    private static final MockWebServer BACKEND = startBackend();

    @Autowired
    DiscoveryClient discoveryClient;

    @Autowired
    CatalogClient catalogClient;

    @DynamicPropertySource
    static void discoveryProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.cloud.discovery.client.simple.instances.catalog-service[0].uri",
            () -> BACKEND.url("/").toString()
        );
        registry.add(
            "spring.cloud.discovery.client.simple.instances.catalog-service[0].metadata.zone",
            () -> "test-zone"
        );
        registry.add(
            "spring.cloud.discovery.client.simple.instances.catalog-service[0].metadata.version",
            () -> "v1"
        );
    }

    @Test
    void discoversConfiguredInstance() {
        List<ServiceInstance> instances =
            discoveryClient.getInstances("catalog-service");

        assertEquals(1, instances.size());
        assertEquals("test-zone",
            instances.get(0).getMetadata().get("zone"));
    }

    @Test
    void callsProviderUsingServiceId() throws Exception {
        BACKEND.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "application/json")
            .setBody("{\"id\":\"42\",\"name\":\"Keyboard\"}"));

        CatalogItem item = catalogClient.find("42");

        assertEquals("42", item.id());
        assertEquals("Keyboard", item.name());

        RecordedRequest request =
            BACKEND.takeRequest(1, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("GET", request.getMethod());
        assertEquals("/api/items/42", request.getPath());
    }

    @Test
    void providerErrorDoesNotRemoveStaticInstance() {
        BACKEND.enqueue(new MockResponse().setResponseCode(503));

        assertThrows(HttpServerErrorException.class,
            () -> catalogClient.find("42"));

        assertEquals(1,
            discoveryClient.getInstances("catalog-service").size());
    }

    @AfterAll
    static void stopBackend() throws IOException {
        BACKEND.shutdown();
    }

    private static MockWebServer startBackend() {
        MockWebServer server = new MockWebServer();
        try {
            server.start();
            return server;
        } catch (IOException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }
}
~~~

Key imports include:

~~~java
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
~~~

Imports for JUnit, Spring Boot Test, RestTemplate, HttpServerErrorException, IOException, List, and TimeUnit also need to be added as used in the code.

`@DynamicPropertySource` injects MockWebServer's dynamically assigned URI into the exact property read by SimpleDiscoveryClient. The test does not hard-code a fixed host port and does not need to start a registry. MockWebServer records incoming requests to verify the consumer called the expected path.

Use a dedicated `mock-provider` profile for this test and avoid loading the two-URI list from the earlier `application-test.yml` example at the same time. If base configuration or an active profile declares other instances, exclude them from test property sources so only the dynamic MockWebServer endpoint remains.

The 503 error test demonstrates an intentional limitation: SimpleDiscoveryClient continues returning the declared instance even when the provider returns an HTTP error. It does not perform health checks or evict endpoints from the list.

## 7. Testing multiple instances

You can start two mock servers and bind each server's URI to two indices:

~~~java
registry.add(
    "spring.cloud.discovery.client.simple.instances.catalog-service[0].uri",
    () -> backendA.url("/").toString()
);
registry.add(
    "spring.cloud.discovery.client.simple.instances.catalog-service[1].uri",
    () -> backendB.url("/").toString()
);
~~~

Then verify:

- DiscoveryClient returns both instances.
- Both URIs have valid scheme, host, and port values.
- LoadBalancer can send requests to instances in the list.
- Each instance's metadata is preserved accurately.

Avoid asserting a fixed alternating request order unless the algorithm and seed are explicitly configured. Round-robin may start at a different position depending on internal state. For distribution tests, send enough requests and verify the set of endpoints that received requests rather than assuming the first request always hits instance A.

## 8. Testing metadata and instance filters

If the application uses metadata to filter by zone or version, declare separate metadata for each URI:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:18081
                metadata:
                  zone: zone-a
                  version: v1
              - uri: http://localhost:18082
                metadata:
                  zone: zone-b
                  version: v2
~~~

Tests can verify the filter's input data:

~~~java
List<ServiceInstance> instances =
    discoveryClient.getInstances("catalog-service");

assertTrue(instances.stream().anyMatch(instance ->
    "v2".equals(instance.getMetadata().get("version"))));
~~~

If you need to test the filtering policy of a `ServiceInstanceListSupplier`, test the supplier directly with a known list of instances and metadata. You can then add an integration test through LoadBalancer to confirm the final request reaches the expected mock provider.

Distinguish two goals:

- Discovery tests verify SimpleDiscoveryClient provides the right instances and metadata.
- Routing tests verify the supplier/load balancer applies the filter and selects the right endpoint.

Merely checking that metadata is present does not prove the routing filter works correctly.

## 9. Testing when no instances exist

When a service ID has no configured URIs, DiscoveryClient returns an empty list. When called through LoadBalancer, the request cannot be routed to a provider and typically fails with a no-available-instance error.

Example discovery check:

~~~java
@Test
void unknownServiceHasNoInstances() {
    assertTrue(
        discoveryClient.getInstances("missing-service").isEmpty()
    );
}
~~~

If you need to verify the HTTP client error, call an unconfigured service ID and assert that the application translates the failure into an appropriate response or exception. The exact exception type may vary across Spring Cloud LoadBalancer versions and consumer error handling; test the application's error contract rather than locking tests to internal framework messages.

## 10. Testing timeouts and unresponsive providers

MockWebServer can simulate:

- 500 or 503 responses.
- Responses slower than the response timeout.
- Connections closed before returning a body.
- Malformed JSON bodies.
- Incorrect headers or content types.

Example delayed response:

~~~java
BACKEND.enqueue(new MockResponse()
    .setResponseCode(200)
    .setBody("{\"id\":\"42\",\"name\":\"Keyboard\"}")
    .setHeadersDelay(3, TimeUnit.SECONDS));
~~~

For timeout tests to be meaningful, the HTTP client must be configured with appropriate connect and read/response timeouts. Do not just add a delay to the mock server and assume the application will time out if the client has no wait limit.

Scenarios to verify:

1. The consumer finishes within the configured timeout.
2. The error is translated into an exception or response per the application contract.
3. Retries, if enabled, are bounded in count.
4. Non-idempotent operations are not retried unintentionally.
5. Logs and metrics record the service ID and error type to aid diagnostics.

## 11. Distinguishing discovery tests from registry integration tests

SimpleDiscoveryClient is suitable for testing consumer behavior against a static list of URIs. When you need to verify real registry behavior, you need a separate test category.

| Goal | SimpleDiscoveryClient | Real registry |
|---|---|---|
| Consumer looks up service ID | Yes | Yes |
| LoadBalancer selects URI | Yes | Yes |
| Verify metadata mapping | Yes | Yes |
| Provider self-registration | No | Possible |
| Provider deregisters on shutdown | No | Possible |
| Heartbeat/lease/session | No | Yes |
| Registry health checks | No | Depends on implementation |
| Registry ACL, TLS/mTLS | No | Yes |
| Watch or catalog sync | No | Depends on implementation |

You can organize tests into layers:

- Unit tests for response processing logic and DTO mapping.
- Integration tests with SimpleDiscoveryClient and MockWebServer for the service ID → LoadBalancer → HTTP flow.
- Contract tests between consumer and provider to verify the API contract.
- Registry integration tests with Eureka, Consul, or ZooKeeper for registration, health checks, security, and instance lifecycle.

There is no need to put every test in an infrastructure-dependent suite. Layering keeps consumer tests fast while still testing registry-specific features separately.

## 12. Keeping test configuration isolated from real environments

Principles to prevent tests from hitting the wrong endpoints:

- Place instance lists in `application-test.yml` or `@DynamicPropertySource`.
- Use mock server hostnames/ports, never production addresses.
- Do not load production tokens, passwords, or certificates into tests.
- If the application includes Eureka/Consul/ZooKeeper starters, isolate dependencies or auto-configuration so SimpleDiscoveryClient is actually used.
- Shut down mock servers after tests to release sockets.
- Do not rely on instance ordering unless the algorithm guarantees it.
- Disable or bound retries in failure tests to avoid redundant requests and slow tests.
- Use dynamic ports to avoid collisions when tests run in parallel.

If tests run in parallel, each test context or test class should manage its own MockWebServer lifecycle. Do not share a mutable mock server across concurrent tests because the response queue can be consumed out of order.

## 13. Common testing issues

| Symptom | Possible cause | How to fix |
|---|---|---|
| `getInstances()` returns empty list | Wrong service ID or wrong property prefix/index | Check `simple.instances.<service-id>[index].uri` |
| URI is read but calling service ID fails | RestTemplate lacks `@LoadBalanced` or missing LoadBalancer starter | Check beans and dependencies |
| Test accidentally calls real registry | Another registry starter is present on the test runtime | Isolate dependencies or auto-configuration |
| `localhost` cannot reach mock server | Mock server not started or port property bound too early | Use `@DynamicPropertySource` with a statically started server |
| Metadata does not appear | Wrong key path or metadata property failed to bind | Check `metadata.<key>` property and ServiceInstance result |
| Multi-instance test is flaky | Assumes fixed round-robin order | Check the set of endpoints or configure algorithm explicitly |
| Provider returns 503 yet stays discovered | Normal behavior for a static instance list | Test health checks separately or use a registry with health integration |
| Timeout test hangs | HTTP client has no timeout configured | Set connect/read timeouts on the client |
| Test depends on a fixed port | Port already in use by another process | Use MockWebServer dynamic ports |

## 14. Integration test checklist

1. Confirm the test runtime uses SimpleDiscoveryClient.
2. Declare service IDs and URIs via test properties.
3. Use `DiscoveryClient.getInstances()` to verify instance count and metadata.
4. Verify a non-existent service ID returns an empty list.
5. Start a mock HTTP provider on a dynamic port.
6. Use a `@LoadBalanced` client to call by service ID.
7. Verify HTTP method, path, headers, and body received by the mock server.
8. Simulate success responses, server errors, and timeouts.
9. Verify HTTP errors do not cause SimpleDiscoveryClient to drop URIs.
10. Shut down the mock server and ensure tests do not use production config or secrets.

SimpleDiscoveryClient makes it easy to test service lookup and invocation against a controllable endpoint list. When paired with Spring Cloud LoadBalancer and an HTTP mock server, integration tests can confirm that the consumer uses service IDs, selects instances, and sends requests properly. Keep in mind this tests the call flow against static configuration; dynamic registration, health checks, heartbeats, security, and registry synchronization still need dedicated tests against real implementations.
