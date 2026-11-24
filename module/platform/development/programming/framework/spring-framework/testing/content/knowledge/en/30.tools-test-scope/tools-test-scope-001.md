# What Mechanisms Does Spring Test Provide, and What Do Assertion Libraries Provide?

## 1. Distinguishing Testing Infrastructure from Result Verification

In a Spring project, multiple components participate in a test, yet they do not share the same responsibility.

**Spring Test** provides the infrastructure to load and manage the Spring ApplicationContext in tests, inject dependencies, set up a mock web environment, run tests inside transactions, create mock servlet requests/responses, and supply clients that help test the web layer. It enables a test to run the application or part of the application in a controlled environment.

**Assertion libraries** provide expressions to compare actual results against expected results. They answer questions such as: are values equal, does a collection contain this element, was an exception thrown, does JSON have the right field, or does a condition become true after a period of time.

You can picture a test following this flow:

~~~text
JUnit / TestNG
   |
   | discover and run test methods
   v
Spring Test
   |
   | load context, inject beans, create test fixtures,
   | manage transactions, mock web environment
   v
Application / Controller / Service / Repository
   |
   | actual result
   v
Assertion and verification libraries
   |
   | compare, describe failures, verify interactions
   v
PASS / FAIL
~~~

JUnit is typically the test framework and test engine. Spring Test integrates Spring into that framework's lifecycle. AssertJ, Hamcrest, or JUnit Assertions express the conditions that must hold. Mockito creates mocks and verifies interactions; it has a verification API, but does not replace a general-purpose assertion library.

Distinguishing these roles helps you choose the right dependencies and avoid expecting that simply adding Spring Test gives you every verification tool.

## 2. What Is Spring Test and Where Does It Live?

Spring Test is the **spring-test** module of the Spring Framework. It is a module used in tests that provides APIs and infrastructure for testing Spring applications.

Some important packages:

| Package | Role |
|---|---|
| **org.springframework.test.context** | TestContext Framework, loading ApplicationContext, managing lifecycle and listeners |
| **org.springframework.test.context.junit.jupiter** | Integrating Spring Test with JUnit Jupiter |
| **org.springframework.test.context.transaction** | Support for test-managed transactions |
| **org.springframework.test.web.servlet** | MockMvc and Spring MVC testing APIs |
| **org.springframework.test.web.reactive.server** | WebTestClient for WebFlux and some MVC scenarios |
| **org.springframework.test.web.client** | MockRestServiceServer for synchronous REST clients |
| **org.springframework.mock.web** | Mock Servlet APIs such as request, response, session, and servlet context |
| **org.springframework.test.util** | Testing utilities such as ReflectionTestUtils and AopTestUtils |

Spring Test is not a standalone test runner. It does not discover and run test methods on its own. With JUnit Jupiter, the JUnit test engine runs methods, while **SpringExtension** connects the test lifecycle to the Spring TestContext Framework.

Spring Test also does not provide a general-purpose assertion library like AssertJ by default. Some Spring Test APIs have their own expectation DSLs, such as MockMvc and WebTestClient, but those DSLs are focused on HTTP responses and often integrate with matchers or other assertion libraries.

## 3. What Does the TestContext Framework Do?

The TestContext Framework is the central infrastructure of Spring Test. It manages how tests obtain a Spring context and how extensions/listeners participate in the test lifecycle.

A test may need to:

- Load Java or XML configuration to create an ApplicationContext.
- Inject services, repositories, or controllers into the test class.
- Use profiles and properties dedicated to tests.
- Run setup before a test method and cleanup after the test.
- Manage transactions and roll back data.
- Mark a context as needing recreation when a test mutates context state.
- Integrate listeners to manage dependency injection, transactions, SQL scripts, or application events.

Example with JUnit Jupiter:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;

@SpringJUnitConfig(AppConfig.class)
class PricingServiceTest {

    @Autowired
    private PricingService pricingService;

    @Test
    void shouldCalculateDiscountedPrice() {
        Money result = pricingService.priceFor(
                new Product("book", new Money("100.00")),
                true
        );

        assertThat(result.amount()).isEqualByComparingTo("90.00");
    }
}
~~~

**@SpringJUnitConfig** is a composed annotation combining registering **SpringExtension** for JUnit Jupiter and **@ContextConfiguration** to specify context configuration. It lets tests use Spring beans without manually creating an ApplicationContext in every method.

For tests that need a web application context, you can use **@SpringJUnitWebConfig**. This annotation combines JUnit Jupiter integration, context configuration, and **@WebAppConfiguration**.

### SpringExtension

**SpringExtension** implements the JUnit Jupiter extension API. It coordinates with TestContextManager to perform steps such as:

- Preparing the test instance and injecting dependencies.
- Invoking TestExecutionListeners according to the lifecycle.
- Managing callbacks before/after test methods.
- Supporting test-managed transactions when configured.
- Providing the context for Spring testing annotations.

Example of explicit declaration:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = AppConfig.class)
class InventoryServiceTest {
}
~~~

This approach is equivalent in intent to using **@SpringJUnitConfig(AppConfig.class)**. You should pick one declaration style that fits your project's conventions.

## 4. Commonly Used Spring Test Annotations

Spring Test provides many annotations to control the context and test behavior.

| Annotation | Purpose |
|---|---|
| **@ContextConfiguration** | Specifies configuration classes or resources to load the ApplicationContext |
| **@SpringJUnitConfig** | Combines SpringExtension and ContextConfiguration for JUnit Jupiter |
| **@SpringJUnitWebConfig** | Configures tests with a WebApplicationContext |
| **@WebAppConfiguration** | Requests creating a WebApplicationContext instead of a regular context |
| **@ActiveProfiles** | Selects the profiles activated in the test |
| **@TestPropertySource** | Adds a property source dedicated to the test |
| **@DirtiesContext** | Marks the context as modified and needing removal from the cache |
| **@Transactional** | Runs the test method inside a Spring Test-managed transaction if a transaction manager is present |
| **@Commit** | Commits the test transaction instead of the default rollback |
| **@Rollback** | Chooses whether to roll back the transaction after the test |
| **@Sql** | Executes SQL scripts before or after a test |
| **@TestExecutionListeners** | Registers or customizes TestExecutionListeners |

Example of selecting profiles and properties:

~~~java
@SpringJUnitConfig(AppConfig.class)
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "catalog.endpoint=http://localhost:9001",
        "feature.discount.enabled=false"
})
class CatalogServiceTest {
}
~~~

These properties can be injected into beans via **@Value** or Environment. This helps tests use deterministic configuration instead of depending on configuration files on a developer's machine.

### Context caching

Spring Test can cache ApplicationContexts across tests with compatible configurations. This reduces test suite startup time.

If a test mutates a singleton bean or context configuration in a way that affects other tests, **@DirtiesContext** may be needed so Spring removes that context from the cache. Do not add this annotation out of habit, because recreating the context can slow down the test suite significantly.

Context caching does not automatically reset databases, Redis, message brokers, or files outside the Spring context. Those resources require their own fixtures and cleanup.

## 5. What Mocks and Web Tools Does Spring Test Provide?

Spring Test includes mock objects that help test web layers without starting a real servlet container.

### Mock Servlet API

In the **org.springframework.mock.web** package, you can find:

- **MockHttpServletRequest** and **MockHttpServletResponse**: simulate servlet requests/responses.
- **MockHttpSession**: simulates an HTTP session.
- **MockServletContext**: simulates a ServletContext.
- **MockMultipartFile**: creates simulated file uploads in tests.

They are useful when you need to create requests, set headers, parameters, session attributes, or file uploads in memory.

These mocks do not open sockets and do not fully simulate the behavior of a servlet container like Tomcat or Jetty. They create a test environment for Spring MVC to process requests within the scope of the test.

### MockMvc

**MockMvc** lets you send requests through the Spring MVC infrastructure without an HTTP server listening on a port. Requests are dispatched through MVC components such as DispatcherServlet, handler mappings, controllers, argument resolvers, message converters, and exception resolvers.

Example:

~~~java
mockMvc.perform(get("/api/products/{id}", 42)
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value(42));
~~~

MockMvc provides API groups such as:

- Request builders to construct GET, POST, PUT, DELETE, and multipart requests.
- Request post-processors to add users, sessions, cookies, or attributes.
- Result matchers to verify status, headers, content, view, model, and JSONPath.
- Result handlers to print or record the request/response when a test fails.

MockMvc is well-suited for verifying MVC contracts and controller logic. If you need to verify TCP, server ports, TLS, or connector behavior, you need an HTTP integration test with a real server.

### WebTestClient

**WebTestClient** is a testing client with a fluent API, commonly used with WebFlux and also usable in some Spring MVC scenarios.

It can bind to controllers, router functions, an application context, or a running server. When bound to mock infrastructure, it does not open a socket; when bound to a server, it sends real HTTP requests.

Example expectations:

~~~java
webTestClient.get()
        .uri("/api/products/42")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.id").isEqualTo(42);
~~~

WebTestClient supports verifying status, headers, body, JSONPath, and asynchronous responses. With reactive endpoints, it can be combined with Reactor Test to verify publishers and events.

### MockRestServiceServer

**MockRestServiceServer** helps test a synchronous HTTP client in your application, such as RestClient or RestTemplate, by simulating the server the client calls.

It can verify the URI, method, headers, body, and the response returned to the client. It is not a real TCP server; requests are handled through a request factory bound to Spring's mock mechanism.

This is useful when testing integration between a service and a REST client without calling an external service.

## 6. Spring Test and Spring Boot Test Are Not the Same Module

Spring Framework provides **spring-test**. Spring Boot adds its own testing modules such as **spring-boot-test**, **spring-boot-test-autoconfigure**, and the aggregate starter **spring-boot-starter-test**.

Several familiar annotations belong to Spring Boot rather than Spring Framework Test:

| Annotation / API | Source |
|---|---|
| **@SpringBootTest** | Spring Boot Test |
| **@WebMvcTest** | Spring Boot Test AutoConfigure |
| **@WebFluxTest** | Spring Boot Test AutoConfigure |
| **@AutoConfigureMockMvc** | Spring Boot Test AutoConfigure |
| **@AutoConfigureWebTestClient** | Spring Boot Test AutoConfigure |
| **@MockBean** (older Boot versions) | Spring Boot Test |
| **@MockitoBean** / **@MockitoSpyBean** | Spring Framework Test in supported Spring Framework versions |

Spring Boot Test builds on Spring Test and adds auto-configuration following Boot conventions. For example, **@SpringBootTest** locates the Boot application configuration and creates the context the way Boot manages it.

Therefore, when reading a test, you should know which package an annotation comes from. Do not say **@WebMvcTest** is a Spring Framework annotation simply because it uses MockMvc and Spring Test underneath.

### @SpringBootTest

Used when you need to load most or all of a Spring Boot application:

~~~java
@SpringBootTest
class OrderServiceIntegrationTest {
}
~~~

You can choose the web environment:

- **MOCK**: creates a mock web application context without opening a server port.
- **RANDOM_PORT**: starts a real server on a random port.
- **DEFINED_PORT**: starts a real server on the configured port.
- **NONE**: does not create a web environment.

### @WebMvcTest and @WebFluxTest

These are slice tests. They only load the configuration related to MVC or WebFlux and selected beans, making controller tests faster than starting the entire application.

If the controller depends on a service, the service is typically mocked in a slice test. With Spring Framework 6.2 and later you can use **@MockitoBean**; older Spring Boot versions typically use **@MockBean**.

## 7. Spring Test Supports Transactions and SQL Fixtures

Spring Test integrates with transaction management. When a test method is annotated with **@Transactional** and the context has an appropriate transaction manager, Spring Test can start a transaction before the test and roll it back after the test by default.

~~~java
@SpringJUnitConfig(DataConfig.class)
@Transactional
class AccountRepositoryTest {

    @Autowired
    private AccountRepository repository;

    @Test
    void shouldPersistAnAccountInsideTestTransaction() {
        repository.save(new Account("A-100"));

        assertThat(repository.findByNumber("A-100")).isPresent();
    }
}
~~~

This mechanism is useful for tests that call repositories/services within the same transaction managed by the test framework.

You can use **@Commit** to commit or **@Rollback(false)** to disable rollback. Only do so when the test genuinely needs data committed and you already have a cleanup plan.

### @Sql

**@Sql** runs SQL scripts to prepare or clean up data:

~~~java
@Test
@Sql("/sql/accounts-before.sql")
@Sql(
        scripts = "/sql/accounts-after.sql",
        executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
void shouldFindAnAccount() {
    assertThat(repository.findByNumber("A-100")).isPresent();
}
~~~

Spring Test also has transaction test listeners and callbacks such as **@BeforeTransaction** or **@AfterTransaction** when setup/cleanup is needed outside the test transaction.

Note: a test method's transaction does not automatically wrap HTTP requests processed by a server on a separate thread or reactive pipeline. With **RANDOM_PORT**, endpoints have their own transactions. In that case, you need explicit fixture cleanup or a dedicated database/schema.

## 8. Test Utilities in Spring Test

Spring Test provides several useful utilities when testing Spring components.

### ReflectionTestUtils

**ReflectionTestUtils** lets you read or write fields, invoke non-public methods, and access certain members via reflection.

~~~java
ReflectionTestUtils.setField(service, "clock", fixedClock);

Object value = ReflectionTestUtils.getField(service, "clock");
~~~

It can be helpful with legacy code or tests that need to replace a dependency in a component not designed for constructor injection. However, tests relying on private fields are often brittle when implementation changes. Prefer constructor injection and public APIs whenever possible.

### AopTestUtils

**AopTestUtils** helps access the target object inside a Spring AOP proxy:

~~~java
Object target = AopTestUtils.getTargetObject(proxiedBean);
~~~

It is useful when you need to inspect an object wrapped by a proxy, such as a transaction proxy or scoped proxy. Be cautious because calling the target directly bypasses the proxy behavior that the test might want to verify.

### ApplicationEvents

Spring Test supports recording application events in tests using **@RecordApplicationEvents** and injecting **ApplicationEvents**:

~~~java
@SpringJUnitConfig(AppConfig.class)
@RecordApplicationEvents
class OrderEventTest {

    @Autowired
    private ApplicationEvents events;

    @Test
    void shouldPublishOrderCreatedEvent() {
        orderService.createOrder(command);

        assertThat(events.stream(OrderCreatedEvent.class))
                .hasSize(1);
    }
}
~~~

This mechanism is useful for verifying that a bean published an event within the application context. If you need to test asynchronous event handling or delivery through an external message broker, you need to wait and assert at the corresponding boundary.

## 9. What Do JUnit Jupiter Assertions Check?

JUnit Jupiter provides basic assertions in the **org.junit.jupiter.api.Assertions** package. This is the default choice when a project uses JUnit 5 and wants to avoid adding another assertion library.

Some commonly used APIs:

| API | Purpose |
|---|---|
| **assertEquals(expected, actual)** | Compares two values |
| **assertNotNull(value)** | Verifies a value is not null |
| **assertTrue(condition)** / **assertFalse(condition)** | Verifies a boolean condition |
| **assertThrows(type, executable)** | Verifies code throws an exception of the expected type |
| **assertDoesNotThrow(executable)** | Verifies code does not throw an exception |
| **assertAll(...)** | Runs multiple assertions and reports all failures together |
| **assertTimeout(...)** | Verifies code completes within a time limit |

Example:

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DiscountServiceTest {

    @Test
    void shouldApplyDiscount() {
        Money result = service.applyDiscount(new Money("100.00"), 10);

        assertEquals(new Money("90.00"), result);
    }

    @Test
    void shouldRejectNegativeDiscount() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> service.applyDiscount(new Money("100.00"), -5)
        );

        assertTrue(error.getMessage().contains("discount"));
    }
}
~~~

JUnit assertions are simple, built-in, and suitable for many tests. When checking nested objects, collections, strings, or domain objects with more readable expressions, AssertJ is often more convenient.

JUnit Assertions are not all of JUnit. JUnit also provides lifecycle annotations, parameterized tests, assumptions, extensions, and the test engine.

## 10. AssertJ Provides Fluent Assertions

**AssertJ** is an independent assertion library focused on a readable fluent API and contextual failure messages.

Example of numeric comparison:

~~~java
assertThat(actualPrice)
        .isEqualByComparingTo("90.00");
~~~

Checking a collection:

~~~java
assertThat(products)
        .hasSize(2)
        .extracting(Product::name)
        .containsExactly("Keyboard", "Mouse");
~~~

Checking an exception:

~~~java
assertThatThrownBy(() -> service.findById("missing"))
        .isInstanceOf(ProductNotFoundException.class)
        .hasMessageContaining("missing");
~~~

Comparing objects by properties:

~~~java
assertThat(actual)
        .usingRecursiveComparison()
        .isEqualTo(expected);
~~~

AssertJ has assertions for primitives, objects, collections, maps, streams, files, exceptions, and many other data types. It also provides **SoftAssertions** to collect multiple assertion failures in a single test instead of stopping at the first failure.

Do not use recursive comparison for every object. For entities with bidirectional relationships, technical fields, or data outside the contract being verified, select meaningful properties instead of comparing the entire object graph.

## 11. Hamcrest and Matchers in MockMvc

**Hamcrest** provides matchers to express conditions on values. Matchers can be composed into expressions such as **equalTo**, **containsString**, **hasSize**, **hasItem**, **allOf**, or **not**.

Example:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.hasSize;

mockMvc.perform(get("/api/products"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.name", equalTo("Keyboard")))
        .andExpect(jsonPath("$.description", containsString("wireless")))
        .andExpect(jsonPath("$.items", hasSize(2)));
~~~

MockMvc has its own **ResultMatcher** DSL in Spring Test. Matchers like **status()**, **header()**, **content()**, **view()**, **model()**, and **jsonPath()** are Spring Test APIs. When passing a matcher to the JSONPath overload, Hamcrest can supply the condition that compares that value.

Thus, the two components cooperate:

- Spring Test knows how to extract status, header, model, or JSON properties from an MVC result.
- Hamcrest expresses the condition that the value must satisfy.

Not every assertion in MockMvc requires Hamcrest. Many matchers have direct methods such as **isOk()**, **exists()**, **isArray()**, or **doesNotExist()**.

## 12. JSONPath and JSONAssert Verify JSON Structure

JSON has structures consisting of objects, arrays, strings, numbers, booleans, and null. Assertions on JSON should verify that structure rather than using **String.contains(...)** across the entire response.

### JSONPath

JSONPath selects a node in JSON using an expression. For example:

- **$.id**: the id property at the root.
- **$.customer.name**: the nested customer name.
- **$.items[0].sku**: the SKU of the first element.
- **$.items.length()**: the number of elements in the array according to the syntax supported by the implementation.

In MockMvc:

~~~java
mockMvc.perform(get("/api/orders/42"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.customer.name").value("Linh"))
        .andExpect(jsonPath("$.items").isArray())
        .andExpect(jsonPath("$.items.length()").value(2));
~~~

In WebTestClient, you can use the corresponding JSONPath expectation:

~~~java
webTestClient.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.customer.name").isEqualTo("Linh");
~~~

JSONPath is especially useful when you only need to check a few properties without locking the test to the entire response.

### JSONAssert and content().json(...)

JSONAssert compares two JSON documents structurally. It has strict and non-strict modes depending on whether the test requires extra properties or array ordering.

In MockMvc, you can use:

~~~java
mockMvc.perform(get("/api/products/42"))
        .andExpect(content().json("""
                {
                  "id": 42,
                  "name": "Keyboard"
                }
                """));
~~~

**content().json(...)** is a Spring Test matcher; the JSONAssert library may be used underneath to compare JSON. For large bodies, choose strictness that matches the API contract. JSON objects generally do not need to depend on property order, whereas element order in arrays is often significant.

If you only need to check for missing fields, null values, or specific data types, JSONPath or parsing the response into a JsonNode can express intent more clearly.


## 13. Mockito Is a Mock Framework, Not a General Assertion Library

**Mockito** creates mocks, stubs dependency behavior, and verifies interactions between objects.

Stubbing a service:

~~~java
when(productService.findById(42L))
        .thenReturn(new Product(42L, "Keyboard"));
~~~

Verifying a service was called:

~~~java
verify(productService).findById(42L);
~~~

Using ArgumentCaptor to inspect passed data:

~~~java
ArgumentCaptor<CreateOrderCommand> captor =
        ArgumentCaptor.forClass(CreateOrderCommand.class);

verify(orderService).create(captor.capture());

assertThat(captor.getValue().customerId()).isEqualTo("C-42");
~~~

**verify(...)** is behavioral verification: it confirms that an interaction occurred. AssertJ or JUnit then checks the captured value. The two tools complement each other.

Avoid verifying every internal call of a service. Verify the interactions that matter to the component's contract, such as a service calling a gateway once with the right command or not calling a repository when a request is invalid.

## 14. Reactor Test and Awaitility for Asynchronous Results

### StepVerifier

With Reactor, results are usually **Mono** or **Flux**. Do not call block just to test every reactive flow. **StepVerifier** belongs to the **reactor-test** module and lets you verify a sequence of signals: next, complete, error, and cancellation.

~~~java
StepVerifier.create(service.findProducts())
        .expectNextMatches(product ->
                product.name().equals("Keyboard"))
        .expectNextMatches(product ->
                product.name().equals("Mouse"))
        .verifyComplete();
~~~

Checking errors:

~~~java
StepVerifier.create(service.findById("missing"))
        .expectError(ProductNotFoundException.class)
        .verify();
~~~

StepVerifier does not belong to Spring Test or AssertJ. It is Project Reactor's reactive stream testing tool. You can use AssertJ inside **expectNextMatches(...)** if more complex assertions are needed.

### Awaitility

Some systems process work asynchronously via executors, event listeners, or message brokers. Results may appear after an indeterminate delay. **Awaitility** lets you wait for a condition to be satisfied within a maximum duration:

~~~java
await()
        .atMost(Duration.ofSeconds(3))
        .untilAsserted(() ->
                assertThat(repository.findById(orderId)).isPresent()
        );
~~~

Awaitility fits eventual consistency and background tasks. Do not replace every synchronous assertion with await. Use it only when system behavior is genuinely asynchronous and has a clear eventual condition.

## 15. Which Dependencies Need to Be Added?

### Spring Framework projects without Spring Boot

A plain Spring project typically needs Spring Test and the test framework/assertion libraries chosen by the team.

Gradle:

~~~groovy
dependencies {
    testImplementation("org.springframework:spring-test")
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.assertj:assertj-core")
    testImplementation("org.hamcrest:hamcrest")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.assertj</groupId>
        <artifactId>assertj-core</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.hamcrest</groupId>
        <artifactId>hamcrest</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Versions should be managed using the Spring Framework BOM, Spring Boot dependency management, or a unified project dependency management strategy. Do not pin arbitrary differing versions if they might conflict.

### Spring Boot projects

With Spring Boot, the commonly used dependency is:

~~~groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

This starter brings together Spring Boot Test, Spring Test, and popular test libraries such as JUnit Jupiter, AssertJ, Hamcrest, Mockito, JSONassert, and JsonPath aligned with the Spring Boot version in use.

If you need to test Reactor publishers with StepVerifier, add **reactor-test**:

~~~groovy
dependencies {
    testImplementation("io.projectreactor:reactor-test")
}
~~~

If you need Awaitility, add its test dependency separately using the version managed by your project. There is no need to add every assertion library if the project only uses a single assertion style.


## 16. Combining Spring Test and Assertions in the Same Test

A test often uses multiple API layers together. Spring Test creates the environment and executes requests; an assertion library checks data; a mock framework verifies interactions if needed.

Controller slice example with Spring Boot:

~~~java
@WebMvcTest(ProductController.class)
class ProductControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private ProductService productService;

    @Test
    void shouldReturnAProduct() throws Exception {
        given(productService.findById(42L))
                .willReturn(new ProductResponse(42L, "Keyboard"));

        mockMvc.perform(get("/api/products/42")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.name").value("Keyboard"));

        then(productService).should().findById(42L);
    }
}
~~~

In the example:

- **@WebMvcTest** is Spring Boot's slice test mechanism.
- **MockMvc** and **jsonPath/status()** are Spring Test APIs to dispatch requests and inspect the MVC result.
- **@MockitoBean** replaces the ProductService bean in the context with a Mockito mock in supported Spring Framework versions.
- **given(...).willReturn(...)** and **then(...).should()** belong to the Mockito BDD API.
- Assertions in MockMvc matchers are executed through Spring Test's expectation DSL; JSONPath matchers can use Hamcrest when custom matchers are needed.

If an older Spring Boot project does not yet have **@MockitoBean**, use the corresponding mock bean annotation supported by that Boot version, typically **@MockBean**. When upgrading Spring, check the packages and migration guide for the version in use.

Plain service test example with a Spring context:

~~~java
@SpringJUnitConfig(AppConfig.class)
class ProductServiceTest {

    @Autowired
    private ProductService service;

    @Test
    void shouldReturnTheExpectedProduct() {
        Product result = service.findById(42L);

        assertThat(result)
                .extracting(Product::name)
                .isEqualTo("Keyboard");
    }
}
~~~

Here Spring Test only handles loading the context and injecting the service. AssertJ performs the result comparison. MockMvc is not needed if the test does not check HTTP.

## 17. Choosing Assertions by the Data Being Verified

| Data or behavior | Suitable tool |
|---|---|
| Primitive values, booleans, basic exceptions | JUnit Assertions |
| Objects, collections, maps, and domain values | AssertJ |
| Composable matchers or condition expressions | Hamcrest |
| Status, headers, content, and MVC model | MockMvc ResultMatchers |
| Specific JSON properties | JSONPath via MockMvc or WebTestClient |
| Comparing two JSON documents | JSONAssert or content().json(...) |
| Dependency interactions | Mockito verify and ArgumentCaptor |
| Mono/Flux signals, completion, and errors | Reactor StepVerifier |
| Outcomes appearing eventually after async processing | Awaitility |
| XML structure | XMLUnit or suitable XML matchers |

There is no single library that must be used for every test. Choose the tool that makes the assertion's intent clearest and avoid mixing multiple styles within the same test unnecessarily.

A convention that is usually easy to maintain is using AssertJ for general Java assertions, Spring Test matchers for HTTP/MVC, StepVerifier for Reactor, and Mockito for stubbing/verification.

## 18. Common Misconceptions

| Misconception | Reality | Correct understanding |
|---|---|---|
| Spring Test is a test runner | Spring Test integrates Spring into a test framework | Use JUnit Jupiter or the corresponding test framework to run tests |
| Spring Test is an assertion library | Spring Test provides infrastructure and some domain-specific expectation DSLs | Use JUnit Assertions, AssertJ, Hamcrest, or specialized libraries for conditions |
| MockMvc starts a real web server | MockMvc dispatches requests in a mock servlet environment | Use RANDOM_PORT and an HTTP client when a real socket is needed |
| WebTestClient always uses a socket | WebTestClient can bind to a mock context or a server | Check the bind mode before concluding the test is checking transport |
| Mockito is an assertion library | Mockito creates mocks, stubs, and verifies interactions | Use AssertJ/JUnit to inspect captured values |
| @SpringBootTest belongs to Spring Framework | It is a Spring Boot Test annotation | Distinguish spring-test from spring-boot-test |
| @Transactional on a test always rolls back endpoint data | Test transactions do not propagate across HTTP to the server | Clean up data created by HTTP requests |
| @DirtiesContext deletes all test data | It removes the Spring context from the cache | Clean up databases, queues, files, and external resources separately |
| Asserting status 200 proves the response body is correct | Status only confirms the HTTP code | Also verify content type, headers, and body per the contract |
| assertTimeoutPreemptively is safe for all Spring tests | It runs code on a different thread and can miss ThreadLocal context | Be careful with thread-bound transaction, security, and request contexts |

### Note on assertTimeout and assertTimeoutPreemptively

JUnit has two common timeout forms. **assertTimeout(...)** measures execution time while running the code on the current thread; if the limit is exceeded, the assertion fails after the code completes. **assertTimeoutPreemptively(...)** runs the code on another thread so it can abort early when the limit is exceeded.

In tests using Spring transactions, security context, or request context based on ThreadLocal, running code on another thread can prevent the code from seeing the context that Spring set up for the test method. Do not use preemptive timeouts mechanically around code that depends on thread-bound context. Use appropriate timeouts at the HTTP client, Reactor, or test framework layer based on specific requirements.

## 19. A Readable Test Structure

A good test typically has three parts:

1. **Arrange:** prepare the context, fixtures, mocks, and input data.
2. **Act:** call the service or send a request via MockMvc/WebTestClient.
3. **Assert:** verify results with appropriate assertions and verify necessary interactions.

Service test example:

~~~java
@Test
void shouldCalculateTheOrderTotal() {
    // Arrange
    List<OrderLine> lines = List.of(
            new OrderLine("book", new BigDecimal("20.00"), 2),
            new OrderLine("pen", new BigDecimal("5.00"), 1)
    );

    // Act
    BigDecimal total = calculator.total(lines);

    // Assert
    assertThat(total).isEqualByComparingTo("45.00");
}
~~~

HTTP test example:

~~~java
mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "customerId": "C-42",
                          "items": [{"sku": "book", "quantity": 1}]
                        }
                        """))
        .andExpect(status().isCreated())
        .andExpect(header().exists("Location"))
        .andExpect(jsonPath("$.status").value("PENDING"));
~~~

Arrange/Act/Assert is not a mandatory Spring rule. It is an organizational pattern that helps readers see what the test prepares, what behavior it invokes, and what it verifies.

## 20. Summary of Responsibility Boundaries

| Component | What does it provide? | What should you not expect? |
|---|---|---|
| JUnit Jupiter | Test engine, lifecycle, parameterized tests, basic assertions | Does not automatically load a Spring context without integrating an extension |
| Spring Test | TestContext, SpringExtension, mock web APIs, MockMvc, WebTestClient, transaction test support, and utilities | Does not replace the test runner or every assertion library |
| Spring Boot Test | Boot application context testing, slice tests, and test auto-configuration | Not all APIs belong to Spring Framework |
| AssertJ / Hamcrest | Ways to express conditions and compare results | Does not start the application or inject Spring beans |
| Mockito | Creating mocks, stubbing dependencies, and verifying interactions | Does not replace assertions on responses or domain values |
| JSONPath / JSONAssert | Querying and comparing JSON structures | Does not test full HTTP transport |
| Reactor Test | Verifying signals and timing of Mono/Flux | Does not replace HTTP server integration tests |
| Awaitility | Waiting for asynchronous conditions to be met within a deadline | Does not make an operation without a termination condition safe |

When designing a test suite, select each component by its responsibility: Spring Test prepares and integrates the Spring environment; JUnit orchestrates the tests; assertion libraries verify results; mock frameworks verify interactions; specialized tools check JSON or reactive streams. Keeping roles clearly separated keeps dependencies lean and makes test failures easier to diagnose.

