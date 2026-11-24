# Avoiding Dependencies on Production Services or the Public Internet

## 1. Why Must Tests Be Independent of External Systems?

An automated test should run on a developer's machine, in CI, and in development environments without calling production services or public APIs over the Internet. If a test sends requests directly to a real system, outcomes can depend on network conditions, user data, rate limits, provider uptime, or external account configuration.

These dependencies make tests hard to reproduce and can cause unintended side effects:

- An external API outage breaks builds even when application code did not change.
- Live data changes over time, causing assertions that pass today to fail tomorrow.
- Tests send emails, create orders, process payments, or write data into real accounts.
- Concurrent runs share the same resource, leading to collisions in parallel execution.
- Production tokens, credentials, or endpoints leak into logs, configuration, or CI environments.
- Tests waste time waiting on network timeouts or retries.

The goal is putting tests in control of the systems they interact with. In most tests, external services are replaced with fakes, stubs, or mocks. For infrastructure requiring real behavior checks—such as databases, brokers, or caches—you can run an isolated instance locally or inside a container. Both approaches keep tests independent of production services.

## 2. Identifying the Boundaries to Isolate

Before choosing a tool, identify what the test is verifying and which external systems lie outside that scope.

For example, an ordering application might call:

| Dependency | Impact if calling the real service | Common isolation approach |
|---|---|---|
| Payment gateway | Could trigger real transactions or hold funds | Fake `PaymentGateway`, WireMock, or a dedicated vendor sandbox for controlled contract tests. |
| Inventory API | Stock data mutates; API may rate-limit requests | Stub HTTP responses or run a local mock service. |
| Email/SMS provider | Could send notifications to real users | Fake notification port or mock SMTP server such as GreenMail/Mailpit. |
| Database | Shared data, schema, or state across tests | Dedicated database, dedicated schema, or Testcontainers. |
| Message broker | Consumers/producers may share topics and break determinism | Broker container and dedicated test topics/consumer groups. |
| Object storage | Could write/delete files in real buckets | Fake storage adapter, MinIO, or LocalStack in the test environment. |
| Public API | Depends on DNS, public Internet, quotas, and changing data | Fixtures, stub servers, or controlled snapshot data. |

Not every test needs to spin up the entire system. Unit tests should focus on logic and replace dependencies with simple fakes. Integration tests can use real databases or brokers in containers to verify mappings, transactions, and protocols. Contract tests can check compatibility between consumers and providers using stored contracts or a dedicated sandbox environment. End-to-end tests should be fewer and run only in controlled environments.

## 3. Putting External Services Behind an Interface

An effective way to isolate an application is placing each external service behind an interface belonging to the domain or application layer. Business code calls the interface; the production adapter performs HTTP calls, while tests provide a fake implementation.

Example with a payment gateway:

```java
public interface PaymentGateway {
    PaymentResult charge(ChargeCommand command);
}

public record ChargeCommand(String orderId, long amountInCents) {
}

public record PaymentResult(String transactionId, boolean approved) {
}
```

The production adapter uses `RestClient` to call the provider:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class HttpPaymentGateway implements PaymentGateway {

    private final RestClient client;

    HttpPaymentGateway(
            RestClient.Builder builder,
            @Value("${payment.api-base-url}") String baseUrl) {
        this.client = builder.baseUrl(baseUrl).build();
    }

    @Override
    public PaymentResult charge(ChargeCommand command) {
        return client.post()
                .uri("/charges")
                .body(command)
                .retrieve()
                .body(PaymentResult.class);
    }
}
```

The business service depends only on the interface:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class CheckoutService {

    private final PaymentGateway paymentGateway;

    CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    @Transactional
    public PaymentResult checkout(String orderId, long amountInCents) {
        return paymentGateway.charge(
                new ChargeCommand(orderId, amountInCents));
    }
}
```

In the service test, provide a fake implementation to control results:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.context.annotation.Import;

@SpringBootTest
@Import(CheckoutServiceTests.FakePaymentConfiguration.class)
class CheckoutServiceTests {

    @Autowired
    CheckoutService checkoutService;

    @Autowired
    FakePaymentGateway fakePaymentGateway;

    @Test
    void returnsTheConfiguredPaymentResult() {
        fakePaymentGateway.nextResult = new PaymentResult("test-tx-42", true);

        PaymentResult result = checkoutService.checkout("order-42", 2500);

        assertThat(result.transactionId()).isEqualTo("test-tx-42");
        assertThat(fakePaymentGateway.lastCommand)
                .isEqualTo(new ChargeCommand("order-42", 2500));
    }

    @TestConfiguration
    static class FakePaymentConfiguration {

        @Bean
        FakePaymentGateway fakePaymentGateway() {
            return new FakePaymentGateway();
        }

        @Bean
        @Primary
        PaymentGateway paymentGateway(FakePaymentGateway fake) {
            return fake;
        }
    }
}

class FakePaymentGateway implements PaymentGateway {

    PaymentResult nextResult = new PaymentResult("test-approved", true);
    ChargeCommand lastCommand;

    @Override
    public PaymentResult charge(ChargeCommand command) {
        lastCommand = command;
        return nextResult;
    }
}
```

In the test context, the injected `PaymentGateway` bean is the `@Primary` fake. The production HTTP adapter is not selected for this service, so the test needs no real payment credentials or endpoint. The fake also lets you inspect the exact command sent by the service to the payment gateway.

If a test specifically needs to verify how `HttpPaymentGateway` builds HTTP requests, test that adapter using `MockRestServiceServer` or a local stub HTTP server. There is no need to call the real payment service to verify URIs, headers, JSON bodies, or response handling.

## 4. Using MockRestServiceServer to Mock Outbound HTTP

`MockRestServiceServer` belongs to Spring Test and can bind to `RestClient.Builder` or `RestTemplate`. It records requests sent by the client and returns test-defined responses without opening network connections to the URI host.

Example testing a `RestClient` adapter:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

class HttpPaymentGatewayTests {

    @Test
    void sendsChargeRequestAndReadsTheResponse() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://payments.example.invalid");

        MockRestServiceServer server = MockRestServiceServer
                .bindTo(builder)
                .build();

        PaymentGateway gateway = new HttpPaymentGateway(builder,
                "https://payments.example.invalid");

        server.expect(requestTo("https://payments.example.invalid/charges"))
                .andExpect(method(HttpMethod.POST))
                .andRespond(withSuccess(
                        """
                        {"transactionId":"test-tx-42","approved":true}
                        """,
                        MediaType.APPLICATION_JSON));

        PaymentResult result = gateway.charge(
                new ChargeCommand("order-42", 2500));

        assertThat(result).isEqualTo(new PaymentResult("test-tx-42", true));
        server.verify();
    }
}
```

The `.invalid` domain is reserved for illustrative purposes and does not point to any real service. More importantly, `MockRestServiceServer` binds to the builder used by the adapter before the builder constructs the client. Thus, requests are handled by the mock server rather than a standard network request factory.

Tests can add matchers to inspect headers, query parameters, and bodies. `server.verify()` confirms every expectation was met. If the adapter builds a request with the wrong method or URL, the expectation fails.

With `RestTemplate`, usage is similar except binding happens directly to the instance:

```java
RestTemplate restTemplate = new RestTemplate();
MockRestServiceServer server = MockRestServiceServer
        .bindTo(restTemplate)
        .build();
```

`MockRestServiceServer` fits outbound HTTP adapter tests. It does not execute the application's controllers. If you want to test an HTTP client calling your own Spring MVC controllers in-process, `MockMvcClientHttpRequestFactory` is another option; if you want to test HTTP transport over sockets, use a mock server such as WireMock or MockWebServer.

## 5. Using WireMock or MockWebServer for Local HTTP Integration Tests

Sometimes a real HTTP server on loopback is needed to test client details or integrate with an HTTP library not supported by `MockRestServiceServer`. WireMock and MockWebServer can start a local server on a random port, accept requests over sockets, and return stubbed responses.

Example with WireMock:

```java
import static com.github.tomakehurst.wiremock.client.WireMock.aResponse;
import static com.github.tomakehurst.wiremock.client.WireMock.get;
import static com.github.tomakehurst.wiremock.client.WireMock.urlEqualTo;
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import com.github.tomakehurst.wiremock.WireMockServer;

import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.options;

@SpringBootTest
class InventoryClientIntegrationTests {

    private static final WireMockServer inventoryServer =
            new WireMockServer(options().dynamicPort());

    static {
        inventoryServer.start();
    }

    @DynamicPropertySource
    static void inventoryProperties(DynamicPropertyRegistry registry) {
        registry.add("inventory.api-base-url", inventoryServer::baseUrl);
    }

    @Autowired
    InventoryClient inventoryClient;

    @Test
    void readsInventoryFromTheLocalStubServer() {
        inventoryServer.stubFor(get(urlEqualTo("/items/42"))
                .willReturn(aResponse()
                        .withHeader("Content-Type", "application/json")
                        .withBody("""
                                {"id":42,"available":true}
                                """)));

        InventoryItem item = inventoryClient.findById(42);

        assertThat(item.available()).isTrue();
    }

    @AfterAll
    static void stopServer() {
        inventoryServer.stop();
    }
}
```

The example assumes `InventoryClient` reads `inventory.api-base-url` when created and calls `GET /items/{id}`. `@DynamicPropertySource` registers the base URL provided by WireMock on a random port, so the Spring context does not need to know the port before the server starts. Zero requests reach any public inventory API.

When tests run in parallel, use random ports and separate stub state per test class or test instance. If a server is shared, reset mappings and request journals before each test so stubs or request history never leak. Also consider the server's lifecycle when Spring Test caches application contexts: the server must remain active for as long as the context uses that property.

WireMock can verify headers, query parameters, JSON bodies, request ordering, and simulate timeouts or HTTP errors. MockWebServer offers a similar approach with a response queue and recorded requests. Choose one tool suited to your current stack rather than spinning up multiple mock servers for the same purpose.

## 6. Using Testcontainers for Infrastructure Requiring Real Behavior

Not every dependency should be replaced by a mock. When tests must verify SQL, transactions, constraints, migrations, broker protocols, or cache behavior, a real service in a container generally yields more reliable results than a fake database or in-memory substitute.

Testcontainers creates dedicated test containers and maps dynamic ports to the test host. Example with PostgreSQL:

With Spring Boot 3.1 and later, using `@ServiceConnection` requires the corresponding test modules. If the project uses Spring Boot dependency management, you can declare:

```groovy
dependencies {
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")
    testImplementation("org.springframework.boot:spring-boot-testcontainers")
}
```

To use WireMock, add the WireMock 3.x library to test dependencies and let the project's dependency management control the version or declare a compatible version explicitly.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class OrderRepositoryIntegrationTests {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    OrderRepository orderRepository;

    @Test
    void persistsAnOrderInAnIsolatedDatabase() {
        Order saved = orderRepository.save(new Order("order-test-1"));

        assertThat(orderRepository.findById(saved.getId())).isPresent();
    }
}
```

`@ServiceConnection` is supported from Spring Boot 3.1 and automatically provides connection details for compatible service containers. If using an older Boot version or not using Boot service connections, register the JDBC URL, username, and password via `@DynamicPropertySource`:

```java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
```

Testcontainers requires Docker or a compatible container runtime. Images may need to be pulled from a registry on the first run; to run CI completely independent of the Internet, pre-cache or mirror images in an internal registry and configure runners to use those images. Once images are available, container tests can run locally without calling production database services.

The same model applies to Redis, Kafka, RabbitMQ, Elasticsearch, or other infrastructure with Testcontainers modules. Use dedicated topic, database, schema, or bucket names for tests and delete resources after tests complete.

## 7. Configuring Spring Tests Never to Point to Production

Spring Boot supports profiles and property sources to separate test configuration from live runtime configuration. An `application-test.yml` file can contain safe defaults for the test environment:

```yaml
payment:
  api-base-url: http://127.0.0.1:9091
inventory:
  api-base-url: http://127.0.0.1:9092
notifications:
  enabled: false
```

Activate the profile in tests:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class ApplicationIntegrationTests {
}
```

The loopback addresses above are only examples. Tests should substitute dynamic ports from WireMock, MockWebServer, or Testcontainers as needed. Disabling notifications prevents sending emails/SMS during tests, yet you still need fakes or stubs for code depending on notifications so tests do not call real services.

Profiles are only a configuration selector, not a security boundary. Environment variables, system properties, or external configs can override properties in `application-test.yml`. Therefore:

- Never put production credentials into test runtime environments.
- Never use a production URL as a fallback when a test property is missing.
- For mandatory endpoint configuration, fail fast when values are missing or when a host is not in the test allowlist.
- Use random ports and loopback addresses for mock services.
- Separate CI test configurations and secrets from production secrets.

You can add configuration validation to reject unsafe endpoints when the test profile is active. The following example checks a URI's hostname before initializing an HTTP client:

```java
import java.net.URI;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("test")
class TestEndpointGuard {

    TestEndpointGuard(@Value("${payment.api-base-url}") String baseUrl) {
        URI uri = URI.create(baseUrl);
        String host = uri.getHost();

        if (host == null || !(host.equals("localhost")
                || host.equals("127.0.0.1")
                || host.equals("::1"))) {
            throw new IllegalStateException(
                    "Payment endpoint must be local while the test profile is active");
        }
    }
}
```

This is a simple guard for one test configuration. In complex systems, manage allowed endpoints per adapter and enforce egress policies in CI or network namespaces. Checking URL strings alone cannot replace network controls because DNS, redirects, and proxies can also affect connection targets.

## 8. Preventing Tests from Causing Real Side Effects

Beyond HTTP clients, side effects can arise from schedulers, listeners, message consumers, email senders, file storage, or tasks started when the application context initializes.

Common controls:

| Component | How to control in tests |
|---|---|
| Email/SMS | Replace adapter with a fake; verify generated messages instead of sending externally. |
| Payments | Fake gateway or stubbed responses; use a dedicated sandbox only in controlled contract tests. |
| Scheduler | Disable scheduling in tests or configure schedulers not to execute jobs automatically. |
| Message consumer | Use a broker container and dedicated topics; or replace consumers with fakes in service tests. |
| Cloud storage | Use local emulators/containers or fake storage ports; never use production buckets. |
| Webhooks | Send to local WireMock and verify payloads, retries, and signatures. |
| Analytics/telemetry | Use test exporters or disable outbound exporters in the test context. |
| File system | Use dedicated temporary directories for tests and clean up after completion. |

Do not simply suppress exceptions or swallow network errors to let tests continue. Doing so can hide code accidentally calling real endpoints. Make dependency replacement explicit and let tests fail if any execution path crosses outside the intended boundary.

## 9. Isolating Data and Running Tests in Parallel

Even without calling production services, tests can still become flaky if multiple tests share the same local resource. For example, two tests sharing a single database, topic, or WireMock server can overwrite each other's data and expectations.

Techniques to reduce collisions:

- Create dedicated databases/schemas/topics/buckets per test class or test suite.
- Use UUIDs or dedicated namespaces for test data, avoiding shared fixed IDs.
- Use random ports to avoid conflicts when multiple mock servers run simultaneously.
- Reset stubs, request journals, and fake state before each test.
- Never store fake outcomes in static mutable state if tests can run in parallel.
- Clean up containers, temporary files, listeners, and executors after tests finish.
- With the Spring context cache, ensure resources referenced by cached contexts are not stopped prematurely.

A test should create the data it needs and never depend on execution order. When large seed data is required, use versioned fixtures or test scripts managed alongside source code.

## 10. Distinguishing Test Isolation from Offline Builds

These two concepts are related but not identical:

| Aspect | Meaning | How to handle |
|---|---|---|
| Tests do not call production services | Application and tests send no requests or side effects to live systems. | Fakes, stubs, local servers, dedicated containers, safe test configs, and egress blocking. |
| Tests do not need Internet at runtime | Test runtime uses only local or pre-staged internal resources. | Cache/mirror images and fixtures; never call public APIs in tests. |
| Build does not need Internet | Gradle/Maven does not fetch plugins or dependencies from external repositories during that build. | Prepare dependency caches or repository mirrors; use offline mode when appropriate. |

For example, `./gradlew test --offline` tells Gradle to use dependencies already present in its cache and avoid querying remote repositories for new dependencies. That flag does not block test code from calling `https://api.example.com` with an HTTP client. Conversely, tests that make no Internet calls may still require Internet during dependency resolution if libraries are not yet cached.

To make CI truly Internet-independent, pre-populate dependencies and container images, then execute tests on runners with no outbound network access or allowed access only to designated internal services. This is a runtime environment policy, not something `@ActiveProfiles("test")` guarantees on its own.

## 11. Controlling Egress in CI

A strong layer of defense is configuring runners or network policies to allow connections only to required test services. For example, CI can:

1. Download dependencies from an internal artifact repository.
2. Pull container images from a mirrored internal registry.
3. Start databases, brokers, and HTTP stubs on a job-private network.
4. Execute tests with environment variables pointing only to internal endpoints.
5. Block outbound Internet and production network ranges during the test stage.
6. Collect logs, reports, and clean up resources after the job.

Do not rely on `/etc/hosts`, fake DNS, or replacing URLs with nonexistent strings as the sole safeguard. Those measures do not block every connection path, redirect, or proxy. A network egress policy at the runner or container level is the right boundary to stop tests from accidentally calling out.

If certain tests must call a third-party sandbox to verify contracts, separate them into a dedicated group, use low-privilege sandbox credentials, restrict schedules, and allowlist only the exact required hosts. Regular tests must still run without public Internet access.

## 12. Contract Tests to Keep Stubs Aligned with Real APIs

Fakes and stubs keep tests fast and stable, yet carry the risk of misrepresenting provider behavior. For instance, a stub always returns HTTP 200 whereas the real API returns 409 on conflict or renames a JSON field.

You can reduce this risk with contract tests:

- Store API contracts or schemas in the repository and validate consumer requests/responses against them.
- Use provider verification to confirm the service provider honors the contract.
- Run tests against real sandboxes only when necessary and never with production data.
- Version fixtures, schemas, and stub mappings so API changes are reviewed alongside code.
- Keep a set of integration tests with local servers/containers to verify serialization, HTTP status codes, and protocol behavior.

Contract tests do not require every unit test run to hit the real provider. Consumers can verify their behavior against versioned contracts; providers verify contracts in their own pipelines. When over-the-network end-to-end tests are needed, use isolated staging/sandbox environments and disposable data.

## 13. Common Mistakes

| Symptom | Cause | Solution |
|---|---|---|
| Tests fail intermittently despite unchanged code | Dependence on public APIs, network, or changing data. | Replace with fakes/stubs or local services with deterministic data. |
| CI sends real emails or triggers real transactions | Application context loads production adapters or runs schedulers automatically. | Import test configuration, replace adapters with fakes, and disable automatic side effects. |
| Test profile still calls production | Environment variable or system property overrides test URL; missing property falls back to production default. | Remove production fallbacks, validate endpoints, and isolate environment secrets. |
| WireMock test uses wrong port or fails to connect | Server not started before Spring reads properties, or fixed port collides. | Start server before context loads, use dynamic ports, and use `@DynamicPropertySource`. |
| Testcontainers fails to start offline | Docker image missing from cache or runner cannot reach registry. | Mirror/cache images before the job and configure internal image references. |
| Parallel tests corrupt each other's data | Shared database, topic, stub mappings, or static mutable fakes. | Create dedicated namespaces/resources, reset state, and use random ports. |
| Stubs pass while production integration fails | Stubs no longer match current provider contract. | Version contracts, add provider verification, or run controlled sandbox tests. |
| `--offline` set yet tests still call the Internet | Gradle offline only governs dependency resolution, not runtime test networking. | Enforce network egress policies to block outbound traffic at runtime. |

## 14. Workflow for Designing Independent Tests

When adding an external dependency to the application or tests, you can follow this sequence:

1. Identify the interface/adapter representing the external service and the code under test.
2. For unit/service tests, replace the adapter with a deterministic fake or mock.
3. For outbound HTTP adapters, use `MockRestServiceServer` to verify requests/responses without networking.
4. When testing the client's real HTTP stack, use WireMock or MockWebServer on loopback with a dynamic port.
5. For databases, brokers, or caches needing real behavior, use Testcontainers or isolated local services.
6. Configure test profiles and dynamic properties so all endpoints point to fakes/local resources; never use production credentials.
7. Isolate data and reset resources so tests run reliably in parallel and repeatably.
8. Pre-stage dependencies and container images in caches/mirrors if offline execution is required.
9. Block egress in CI to catch any code accidentally calling public or production services immediately.
10. Use dedicated contract tests to ensure fakes/stubs still reflect the API contracts the application must honor.

## 15. Conclusion

Reliable tests must control the services they depend on. Place external services behind interfaces, use fakes or `MockRestServiceServer` for focused tests, use WireMock/MockWebServer when a local HTTP server is needed, and use Testcontainers when real databases or brokers are needed in an isolated environment. Profiles and dynamic properties select the right endpoints, while CI egress policies prevent unintended connections. Finally, contract tests keep stubs aligned with provider APIs. Together, these practices let tests run repeatably in CI without touching production data, credentials, or services.
