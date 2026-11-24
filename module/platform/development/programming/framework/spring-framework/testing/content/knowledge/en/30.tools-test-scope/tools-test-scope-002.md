# `@SpringBootTest` Belongs to Spring Boot and Defines Application Loading Scope

`@SpringBootTest` is an integration testing annotation from **Spring Boot**, not an annotation belonging to Spring Framework core. It instructs Spring TestContext to initialize the application using Boot's `SpringApplication` mechanism, thereby loading the primary configuration, component scanning, auto-configuration, and the beans the application creates in the test environment. This scope is broader than a test that spins up only an isolated controller or repository, making it suitable when you need to verify multiple components collaborating in an application context close to how the application starts up.

The term “full application context” is often used to describe this kind of test, but it does not mean every class in the repository is loaded. The context only contains beans that are configured, scanned, imported, or created by auto-configuration under the current conditions. Profiles, properties, `@Conditional` conditions, the web environment type, and test configuration can all alter the actual set of beans.

## An Annotation Belonging to Spring Boot

`@SpringBootTest` resides in the package:

```java
import org.springframework.boot.test.context.SpringBootTest;
```

This annotation is provided by the `spring-boot-test` module. In a typical Spring Boot application, the `spring-boot-starter-test` dependency already brings the required testing libraries onto the test classpath:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Let Spring Boot dependency management manage the version. You should not manually pick a `spring-boot-test` version from a different line than the `spring-boot` version the application is running.

Spring Framework provides the Spring TestContext Framework, `@ContextConfiguration`, `@WebAppConfiguration`, `@Transactional` for tests, and JUnit integrations. Spring Boot adds bootstrappers and test support to start the application the way Boot does. `@SpringBootTest` uses Spring's TestContext infrastructure, while deciding how to build the context based on `SpringApplication` and Boot's configuration rules.

## How Does `@SpringBootTest` Initialize the Context?

When a test runs, the Spring Boot TestContext bootstrapper locates the application configuration, prepares `SpringApplication`, applies test properties and customizers, and initializes the `ApplicationContext`. This process may include:

- Reading the primary configuration annotated with `@SpringBootConfiguration`, typically the class with `@SpringBootApplication`.
- Performing component scanning according to the application configuration.
- Applying auto-configuration matching the classpath, properties, and `@Conditional` conditions.
- Loading beans from `@Configuration`, `@Import`, component scanning, and declared test configurations.
- Applying active profiles, inline properties, dynamic properties, and Spring Boot Test customizers.
- Creating a mock web application context or starting an embedded web server depending on `webEnvironment`.

Example application:

```java
@SpringBootApplication
public class StoreApplication {

    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
```

`@SpringBootApplication` combines Boot configuration, enabling auto-configuration, and component scanning. When the test locates this class, Boot has an entry point to create a context similar to the application.

Basic integration test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class StoreApplicationTests {

    @Test
    void applicationContextLoads() {
        // If the context fails to initialize, the test fails before entering the method.
        assertThat(true).isTrue();
    }
}
```

This test verifies that the application can initialize its context under the current test configuration. It does not prove on its own that every endpoint, query, or business rule works properly; those behaviors require specific assertions.

## Where Does Boot Find the Application Configuration?

If `classes` is not specified, `@SpringBootTest` searches for the primary configuration starting from the test class. Typically, Boot searches for a class annotated with `@SpringBootConfiguration` by walking up from the test's package through parent packages. In a typical project, that annotation is provided indirectly by `@SpringBootApplication`.

Example package structure:

```text
com.example.store
    StoreApplication.java          (@SpringBootApplication)
    order/
        OrderService.java
        OrderRepository.java
    web/
        OrderController.java
    test/
        StoreApplicationTests.java
```

If the test resides in a sub-package of `com.example.store`, Boot can usually find `StoreApplication`. If the test is outside that package tree, or if the project has multiple Boot configurations, you may need to specify the class explicitly to avoid picking the wrong configuration.

```java
@SpringBootTest(classes = StoreApplication.class)
class OrderIntegrationTest {
}
```

The `classes` attribute accepts one or more configuration classes used to create the test context. When `classes` is explicitly declared, the test does not rely on default configuration discovery. Additional classes may be test configurations, though you need to understand how they participate in the context alongside the primary configuration.

## `classes`, `@TestConfiguration`, and Additional Configuration

When you need to replace a dependency or add a bean used only in tests, you do not necessarily have to create an entire fake application. You can supplement test configuration using `@TestConfiguration`:

```java
@SpringBootTest
class OrderIntegrationTest {

    @TestConfiguration
    static class TestBeans {

        @Bean
        Clock testClock() {
            return Clock.fixed(
                    Instant.parse("2030-01-15T10:00:00Z"),
                    ZoneOffset.UTC);
        }
    }
}
```

`@TestConfiguration` is designed to add beans dedicated to tests without turning that class into a primary configuration automatically picked up by regular component scanning. A nested `@TestConfiguration` inside a test is added to the application configuration by Spring Boot Test.

If you use a nested class with regular `@Configuration`, it may be treated as a replacement configuration during test configuration discovery depending on how bootstrapping works. When you want to keep the primary application configuration and add test beans, use `@TestConfiguration` or `@Import(TestConfig.class)` to express intent clearly.

Another explicit declaration approach:

```java
@SpringBootTest(classes = {
        StoreApplication.class,
        PaymentGatewayTestConfiguration.class
})
class PaymentIntegrationTest {
}
```

Include test configuration only when you need to alter specific behavior. If you replace the entire primary configuration with a small class, the test may no longer verify the auto-configuration and component scanning that the real application uses.

## Inline Properties and Command-Line Arguments

`@SpringBootTest` lets you set properties dedicated to the test:

```java
@SpringBootTest(properties = {
        "store.tax.enabled=false",
        "store.currency=VND",
        "spring.main.banner-mode=off"
})
class StoreConfigurationTest {
}
```

The `value` attribute is an alias for `properties`. You can use `args` to pass command-line arguments to `SpringApplication`:

```java
@SpringBootTest(args = {
        "--store.import.enabled=true",
        "--store.import.batch-size=50"
})
class ImportStartupIntegrationTest {

    @Autowired
    private ApplicationArguments applicationArguments;

    @Test
    void receivesBootCommandLineArguments() {
        assertThat(applicationArguments.getOptionNames())
                .contains("store.import.enabled", "store.import.batch-size");
    }
}
```

`properties` places values into the test context's Environment. `args` simulates command-line arguments passed to `SpringApplication`; options in `--name=value` form can also appear in `ApplicationArguments`. Choose `args` when you need to test behavior depending on command-line options, while `properties` is suited for adjusting test configuration.

You can use `@ActiveProfiles` to activate profiles:

```java
@SpringBootTest
@ActiveProfiles("integration")
class IntegrationProfileTest {
}
```

Profiles affect which beans and configuration files are selected. Check test profiles explicitly, especially when local, CI, and production configurations differ.

For values only available after test resources are created, such as a Testcontainers URL, use `@DynamicPropertySource`:

```java
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class DatabaseIntegrationTest {

    @Container
    static PostgreSQLContainer<?> database =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", database::getJdbcUrl);
        registry.add("spring.datasource.username", database::getUsername);
        registry.add("spring.datasource.password", database::getPassword);
    }
}
```

This snippet assumes the project has configured Testcontainers and an appropriate container lifecycle. Dynamic properties are registered for Spring to read when creating the context; they are useful when configuration values cannot be known before the test starts.

## Web Scope Determined by webEnvironment

`@SpringBootTest` has a `webEnvironment` attribute to determine the context type and how the web layer is tested. The default is `MOCK`.

| Value | Behavior | Embedded server? |
|---|---|---|
| `MOCK` | Creates a mock web environment if the application has a matching web stack; does not start a real server | No |
| `RANDOM_PORT` | Starts the web server on a random port | Yes |
| `DEFINED_PORT` | Starts the web server on the configured port, or the server's default port | Yes |
| `NONE` | Creates a non-web application context and sets the web application type to `NONE` | No |

### MOCK: simulated web context

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class OrderMockMvcIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsOrder() throws Exception {
        mockMvc.perform(get("/api/orders/42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42));
    }
}
```

`MOCK` does not open a port and does not send requests over the network stack. `@AutoConfigureMockMvc` instructs Spring Boot to configure `MockMvc` to dispatch requests through `DispatcherServlet` and the context's MVC infrastructure. Simply adding `@SpringBootTest` does not mean `MockMvc` is always created; you need the MockMvc configuration annotation or to build it manually.

This environment is suitable when you need the full Boot application context together with MVC testing via the mock servlet API. It does not test connectors, TLS, sockets, or servlet container-specific behavior.

### RANDOM_PORT: starting a server on a random port

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpIntegrationTest {

    @LocalServerPort
    private int port;

    @Autowired
    private TestRestTemplate restTemplate;

    @Test
    void servesOrderOverHttp() {
        ResponseEntity<OrderResponse> response = restTemplate.getForEntity(
                "http://localhost:" + port + "/api/orders/42",
                OrderResponse.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().id()).isEqualTo(42L);
    }
}
```

`RANDOM_PORT` starts the embedded server on a port allocated by the operating system. `@LocalServerPort` injects the actual port so the test can send requests to the server. This is how you test HTTP over the embedded server's network stack; it is suitable when you need to verify server configuration, filter chains, serialization, and components working together over real HTTP in a test environment.

### DEFINED_PORT: using a configured port

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.DEFINED_PORT)
class FixedPortHttpTest {
}
```

`DEFINED_PORT` uses `server.port` if configured; otherwise, the server uses its default port. This mode is useful when the test environment requires a known port, but it carries the risk of port conflicts when multiple tests or processes run concurrently. Unless there is a reason requiring a fixed port, `RANDOM_PORT` usually provides better isolation.

### NONE: non-web application context

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class BatchApplicationIntegrationTest {

    @Autowired
    private ImportService importService;

    @Test
    void loadsBatchServices() {
        assertThat(importService).isNotNull();
    }
}
```

`NONE` sets the web application type to `WebApplicationType.NONE`, which fits batch applications, command-line applications, or service tests that do not need a web stack. The context is still initialized by Spring Boot; only the web environment is omitted.

## Distinguishing Full Context from Test Slices

`@SpringBootTest` aims to load the application context according to the application's Boot configuration. Test slices load only a selected portion for a specific layer, making tests faster and more focused.

| Annotation | Typical scope | Purpose |
|---|---|---|
| `@SpringBootTest` | Application context per Boot configuration | Integration testing multiple beans and auto-configuration |
| `@WebMvcTest` | MVC slice | Testing controllers, mappings, converters, validation, and advice in the web layer |
| `@DataJpaTest` | JPA slice | Testing entities, repositories, and related persistence configuration |
| `@JsonTest` | JSON slice | Testing serialization/deserialization |
| `@RestClientTest` | REST client slice | Testing HTTP clients and client-side message conversion |

For example, `@WebMvcTest(OrderController.class)` typically does not load services/repositories like a full application context; the test can supply mocks for controller dependencies. If you need to verify controllers, services, repositories, and application configuration collaborating, use `@SpringBootTest` with the appropriate web environment.

Not every test needs a full context. A full context has higher startup cost and more beans, whereas slice tests are typically faster, have fewer infrastructure dependencies, and help pinpoint failures in a specific layer.

## @SpringBootTest Does Not Automatically Include Every Kind of Test Configuration

Several annotations have distinct roles and can be combined with `@SpringBootTest`:

- `@AutoConfigureMockMvc`: configures `MockMvc` in a mock web environment.
- `@AutoConfigureTestDatabase`: adjusts the test database for certain persistence configurations.
- `@ActiveProfiles`: selects profiles.
- `@TestPropertySource`: loads a test-specific property source.
- `@DynamicPropertySource`: registers dynamic properties from test resources.
- `@Import`: adds configurations or beans into the context.
- `@Transactional`: creates a test-managed transaction for a test method/class according to Spring Test rules.

Do not assume that `@SpringBootTest` automatically creates a test database, mocks every external service, enables test transactions, or replaces all external dependencies. Those parts need to be configured separately based on the test's goal.

## Test Transactions and Server Threads

If a test method is annotated with `@Transactional`, Spring Test normally rolls back the test-managed transaction when the test ends. This is useful for repository/service tests running within the test thread's transaction.

With `RANDOM_PORT` or `DEFINED_PORT`, HTTP requests are processed on the embedded server's thread. That request's transaction is a separate transaction and does not participate in the test thread's transaction. Therefore, rolling back the test-managed transaction does not automatically undo data that the server committed while handling the request.

When testing over real HTTP, you need to clean up created data separately: delete via repositories/JDBC in cleanup, use a dedicated test database/schema, or reinitialize the container/database according to the suite's strategy. Do not rely on `@Transactional` on the test to isolate side effects of requests processed on server threads.

## Context Caching and Startup Cost

Spring TestContext caches application contexts so tests with the same configuration can reuse an already created context. `@SpringBootTest` can take time to start because it has to load many beans, auto-configurations, connection pools, and infrastructure components.

Differences in configuration such as classes, active profiles, property sources, context customizers, and web environment can produce different cache keys. If every test declares its own set of properties or configuration, the number of contexts created can grow significantly.

`@DirtiesContext` tells Spring to remove the context from the cache and close it after the specified point. Use it only when a test genuinely mutates singleton/context state that cannot be restored; overusing this annotation slows down the suite because contexts have to be recreated.

For tests that should share a context, group compatible configurations together, keep test data independent, and clean up mutable state after each test. Only when a test alters a singleton bean or context configuration in an unrecoverable way should you consider `@DirtiesContext`.

## `useMainMethod` and the Application's main Method

By default, Spring Boot Test creates the application using `SpringApplication` without calling the application class's `main` method. If the `main` method contains custom logic that needs testing, you can choose the `useMainMethod` policy:

```java
@SpringBootTest(useMainMethod = SpringBootTest.UseMainMethod.ALWAYS)
class MainMethodIntegrationTest {
}
```

Options include `NEVER`, `WHEN_AVAILABLE`, and `ALWAYS`. Use `ALWAYS` when the test needs to execute the main method; `WHEN_AVAILABLE` allows calling it if a suitable main method exists; `NEVER` keeps direct initialization without calling main. This is an advanced option; most tests only need to start the application context and can stick with the default.

## When Should You Use @SpringBootTest?

Use `@SpringBootTest` when the test question involves collaboration among multiple beans or the real application configuration: a service calling a repository, security and MVC working together, auto-configuration creating the right client, or whether the application can start up in a specific environment.

Choose the web environment based on the request path you need to verify:

| Need | Suitable configuration |
|---|---|
| Full context without a server | `@SpringBootTest(webEnvironment = NONE)` |
| Full context and requests via mock servlet | `@SpringBootTest` + `@AutoConfigureMockMvc` |
| Testing HTTP via an embedded server | `@SpringBootTest(webEnvironment = RANDOM_PORT)` |
| Fixed port required by the environment | `@SpringBootTest(webEnvironment = DEFINED_PORT)` |
| Testing only a web or persistence layer | Corresponding test slice such as `@WebMvcTest` or `@DataJpaTest` |

## Common Errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| `@SpringBootConfiguration` not found | Test lies outside the application class's package tree or the project has multiple configurations | Specify `classes = StoreApplication.class` explicitly |
| Context starts but beans are missing | Bean not scanned/imported, wrong profile, or auto-config conditions unmet | Check component scanning, `@Import`, active profiles, and properties |
| Tests are too slow | Each test creates a different full context or starts unnecessary servers/containers | Reuse context configurations and use slice tests where appropriate |
| Cannot inject `MockMvc` | Only `@SpringBootTest` used without configuring MockMvc | Add `@AutoConfigureMockMvc` or build MockMvc manually |
| Requests do not reach the server | Using `MOCK` while the test calls an HTTP client over a port | Switch to `RANDOM_PORT`/`DEFINED_PORT` or use MockMvc |
| Port already in use | Using `DEFINED_PORT` across multiple processes/tests | Use `RANDOM_PORT` if a fixed port is not required |
| Data remains after HTTP test | Test transaction does not wrap the server thread's transaction | Clean up separately or isolate the database/schema |
| Test profile behaves differently from local | Profiles/property sources differ across environments | Declare `@ActiveProfiles` and test properties explicitly |
| Context keeps getting recreated | Different cache keys or excessive `@DirtiesContext` usage | Standardize test configurations and only mark context dirty when needed |

`@SpringBootTest` is the bridge from Spring TestContext to how Spring Boot starts an application. Understanding which configuration class is selected, the property sources, profiles, and `webEnvironment` helps identify precisely which context is under test. When you need to verify the application collaborating as a whole, a full Boot context is the right choice; when you only need to check a single layer, test slices keep the scope small and execution fast.
