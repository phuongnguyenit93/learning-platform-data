# @SpringBootTest, Test Slices, and Choosing the Testing Scope

## 1. Choosing the Right Testing Scope

In the **SPRING_BOOT_NATIVE_IMAGE** module, a Spring Boot application is processed by Spring AOT and then compiled into a GraalVM Native Image. To verify the application reliably, multiple testing levels are needed: unit logic tests, Spring slice tests, full ApplicationContext tests, and native executable tests in a production-like environment.

Both `@SpringBootTest` and test slices create a Spring test context, but they have different goals and costs:

- `@SpringBootTest` loads the application's ApplicationContext using a configuration close to actual runtime. Use it when verifying multiple collaborating beans, auto-configuration, transactions, security, or cross-layer integration.
- Test slices such as `@WebMvcTest`, `@DataJpaTest`, and `@JsonTest` only load configuration groups relevant to one part of the application. Use them when you want to verify a layer quickly, in isolation, with explicit external dependencies.
- Native executable tests verify the application after AOT processing and GraalVM compilation. This step is essential for catching discrepancies caused by reachability, reflection, resources, proxies, JNI, or service loading.

No single annotation fits every test. Choose the smallest scope that still verifies the target behavior, then add targeted integration/native tests for end-to-end paths.

## 2. Looking at the Test Pyramid

~~~mermaid
flowchart TB
    N["Native executable / deployment tests"]
    I["@SpringBootTest integration tests"]
    S["Spring test slices"]
    U["Unit tests"]
    U --> S
    S --> I
    I --> N
~~~

| Testing Level | Spring Context | Scope | Relative Cost |
| --- | --- | --- | --- |
| Unit test | None | Single class or pure logic | Low |
| Test slice | Partial context | MVC, JSON, persistence, client, or specific layer | Low to medium |
| `@SpringBootTest` | Nearly full context | Bean interactions and application configuration | Medium to high |
| Native/deployment test | Native-compiled application | Executable, OS, container, libraries, and runtime behavior | High |

The pyramid is not a rigid rule about exact counts. An adapter calling an SDK might need its own contract tests; a critical payment flow might need several integration tests. What should be avoided is using a full context for every case merely out of convenience.

## 3. Unit Tests Without Spring

If a class receives dependencies via its constructor and its logic does not depend on the container, test it directly with JUnit:

~~~java
class InvoiceCalculatorTests {

    private final InvoiceCalculator calculator =
        new InvoiceCalculator();

    @Test
    void calculatesTotalWithoutLosingDecimalPrecision() {
        Money net = new Money(new BigDecimal("100.25"), "USD");
        Money tax = new Money(new BigDecimal("8.02"), "USD");

        Money total = calculator.add(net, tax);

        assertThat(total.amount())
            .isEqualByComparingTo("108.27");
    }
}
~~~

This test does not need `@SpringBootTest`, does not start an ApplicationContext, and does not require GraalVM. It is the fastest way to verify calculation rules, pure validation, simple mapping, or algorithms.

If a service depends on a repository/gateway, pass a fake/mock through the constructor to test how the service collaborates. When you need to confirm that Spring actually creates and injects beans, move to a test slice or integration test.

## 4. Using @SpringBootTest for the Full ApplicationContext

`@SpringBootTest` creates a test ApplicationContext via Spring Boot's bootstrapping mechanism. By default, Spring searches for the main application configuration (usually the class annotated with `@SpringBootApplication`) starting from the test's package or parent packages.

Example:

~~~java
@SpringBootTest
class BillingApplicationTests {

    @Autowired
    InvoiceService invoiceService;

    @Test
    void applicationContextProvidesInvoiceService() {
        assertThat(invoiceService).isNotNull();
    }
}
~~~

This test is useful when verifying that the bean graph, component scanning, auto-configuration, and dependency injection work together.

### 4.1. Specifying the Configuration Class

If the test resides outside a package where the application class can be discovered, specify the configuration explicitly:

~~~java
@SpringBootTest(classes = BillingApplication.class)
class BillingApplicationTests {
}
~~~

The `classes` attribute is also helpful for applications with multiple bootstrap configurations or when testing a specific Spring Boot module.

### 4.2. Passing Properties to Tests

You can declare properties directly on the annotation:

~~~java
@SpringBootTest(properties = {
    "app.invoice.currency=USD",
    "app.invoice.tax-rate=0.08"
})
class InvoiceConfigurationTests {
}
~~~

Or use `@ActiveProfiles` and `@TestPropertySource` when sharing test configuration:

~~~java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = "app.storage.bucket=contract-test")
class StorageIntegrationTests {
}
~~~

These properties participate in configuring the test context. With AOT processing, distinguish between properties used to decide bean structure at build time and properties only bound to beans at runtime. If changing a property alters the bean graph, you cannot assume an AOT output generated under one configuration represents every other profile/condition.

## 5. Choosing the webEnvironment of @SpringBootTest

The `webEnvironment` attribute determines which type of web context Spring Boot creates:

| Value | Behavior | When to Use |
| --- | --- | --- |
| `MOCK` | Creates a mock web ApplicationContext; does not start an embedded server | Testing MVC with MockMvc or verifying the web context without opening a port |
| `RANDOM_PORT` | Starts a real server on a random port | Testing HTTP over the real network stack |
| `DEFINED_PORT` | Starts the server on the configured port | Only when a fixed port is needed and port conflicts are controlled |
| `NONE` | Creates a non-web ApplicationContext | Batch apps, services without a web server, or tests not needing web |

`MOCK` is the default. Example testing an HTTP controller via MockMvc:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class InvoiceHttpIntegrationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void createsInvoiceThroughMvcPipeline() throws Exception {
        mockMvc.perform(post("/api/invoices")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "customerId": "customer-01",
                      "currency": "USD"
                    }
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").isNotEmpty());
    }
}
~~~

`@AutoConfigureMockMvc` registers MockMvc and related MVC components in the context. Requests pass through Spring MVC filters, argument resolvers, validation, message converters, and controller advice, without traversing an embedded server socket.

### 5.1. When a Real HTTP Server Is Needed

Use `RANDOM_PORT` when verifying server startup, the HTTP connector, the network stack, or interaction with a real client:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class InvoiceServerTests {

    @Autowired
    TestRestTemplate restTemplate;

    @Test
    void respondsThroughRunningServer() {
        ResponseEntity<String> response =
            restTemplate.getForEntity("/api/status", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
    }
}
~~~

Spring Boot provides a test client configured to call the running server. `WebTestClient` can also be used when appropriate for your stack and test setup.

An important note: when a test uses `RANDOM_PORT` or `DEFINED_PORT`, requests are handled on a server thread separate from the test thread's transaction. `@Transactional` on the test method does not automatically roll back database changes made by HTTP requests. Clean up data explicitly via APIs/fixtures or use a dedicated test database/schema.

## 6. What Is a Test Slice?

A test slice configures only the subset of the ApplicationContext relevant to a testing goal. Spring Boot provides annotations for common slices:

| Annotation | Primary Components | Purpose |
| --- | --- | --- |
| `@WebMvcTest` | Spring MVC, controllers, converters, filters, and relevant MVC advice | Testing controllers on the servlet stack |
| `@WebFluxTest` | WebFlux controllers and reactive web infrastructure | Testing reactive controllers |
| `@JsonTest` | JSON mapper and JSON test support | Testing serialization/deserialization |
| `@DataJpaTest` | JPA repositories, entities, and persistence configuration | Testing mappings/queries/repositories |
| `@JdbcTest` | JDBC infrastructure and embedded database support | Testing JDBC components |
| `@DataJdbcTest` | Spring Data JDBC repositories | Testing JDBC aggregate repositories |
| `@RestClientTest` | REST client components and mock server support | Testing HTTP client adapters |
| `@DataMongoTest` | MongoDB mapping/repository infrastructure | Testing the MongoDB data layer |

A slice does not mean only a single bean is created. It loads auto-configurations and components associated with that slice. Other services, integration adapters, or application configurations may not be scanned automatically.

If a test requires additional configuration, use `@Import` or a nested `@TestConfiguration`. Add only the necessary dependencies so the test continues to reflect the slice boundary.

## 7. @WebMvcTest for Controllers

`@WebMvcTest` is suitable when verifying controller routing, binding, validation, serialization, status codes, and exception mapping without starting all services, repositories, and databases.

Example:

~~~java
@WebMvcTest(InvoiceController.class)
class InvoiceControllerTests {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    InvoiceService invoiceService;

    @Test
    void returnsCreatedWhenInvoiceIsAccepted() throws Exception {
        given(invoiceService.create(any()))
            .willReturn(new InvoiceResponse("inv-100", "USD"));

        mockMvc.perform(post("/api/invoices")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"customerId":"customer-01","currency":"USD"}
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value("inv-100"));
    }
}
~~~

`@MockitoBean` belongs to newer Spring Framework versions (Spring Framework 6.2, typically paired with Spring Boot 3.4+). On older Spring Boot versions, a project may use `@MockBean`; check your version before choosing the annotation.

If the controller relies on `@ControllerAdvice`, converters, or custom security configuration, ensure they are loaded by the slice. Use `@Import` to bring in the required configuration. Do not import the entire application configuration just to make a test pass, as doing so can turn the slice into a near-full-context test.

### 7.1. Validation and HTTP Errors

Include tests for:

- requests missing required fields;
- invalid JSON data types;
- bean validation failures;
- domain exceptions thrown by services;
- unauthenticated or unauthorized users;
- responses having the expected status, error code, and JSON structure.

Slice tests verify a controller's HTTP contract faster than a full context. Some filter/security concerns still require testing with the real security configuration imported into the slice.

## 8. @JsonTest for JSON Contracts

If the goal is solely to verify Jackson mapping, use `@JsonTest`:

~~~java
@JsonTest
class MoneyJsonTests {

    @Autowired
    JacksonTester<Money> json;

    @Test
    void serializesMoneyUsingPublicContract() throws Exception {
        Money money = new Money(new BigDecimal("10.25"), "USD");

        assertThat(json.write(money))
            .isEqualToJson("""
                {
                  "amount": 10.25,
                  "currency": "USD"
                }
                """);
    }
}
~~~

`@JsonTest` creates a JSON slice and supplies helpers such as `JacksonTester` or `JsonbTester` depending on the JSON technology. It is useful for testing custom serializers, deserializers, naming strategies, mix-ins, and related module registrations.

If a module is registered via a Spring bean or `@JsonComponent`, verify that the slice picks up that component. Also test invalid inputs, nulls, missing fields, and numeric precision.

A JSON slice test on the JVM does not prove Jackson reflection works in a Native Image. Native tests are needed for critical endpoints or serialization paths.

## 9. @DataJpaTest for the Persistence Layer

`@DataJpaTest` focuses on entities, repositories, and JPA infrastructure:

~~~java
@DataJpaTest
class InvoiceRepositoryTests {

    @Autowired
    InvoiceRepository invoiceRepository;

    @Test
    void persistsAndFindsInvoiceByReference() {
        Invoice invoice = new Invoice("INV-100", "USD");
        invoiceRepository.save(invoice);

        assertThat(invoiceRepository.findByReference("INV-100"))
            .isPresent();
    }
}
~~~

This slice typically runs inside a transaction and rolls back after each test. By default, Spring Boot may configure an embedded database if the appropriate dependency is present; when you need to test real database behavior, use Testcontainers or configure an explicit test datasource.

For example, with Testcontainers, Spring Boot versions supporting `@ServiceConnection` can automatically create connection details from the container:

~~~java
@DataJpaTest
@Testcontainers
class InvoiceRepositoryPostgresTests {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

Check your project's Spring Boot/Testcontainers version. If not using `@ServiceConnection`, you can pass the URL/username/password via `@DynamicPropertySource`. Do not place real credentials in test source files.

## 10. @RestClientTest for HTTP Client Adapters

When a class calls external APIs via `RestClient`, `RestTemplate`, or a Spring Boot-supported client, `@RestClientTest` creates a slice for the client and configures a mock server:

~~~java
@RestClientTest(ExchangeRateClient.class)
class ExchangeRateClientTests {

    @Autowired
    ExchangeRateClient exchangeRateClient;

    @Autowired
    MockRestServiceServer server;

    @Test
    void mapsExchangeRateResponse() {
        server.expect(requestTo("/rates/USD"))
            .andRespond(withSuccess(
                """
                {"base":"USD","rate":1.0}
                """,
                MediaType.APPLICATION_JSON
            ));

        assertThat(exchangeRateClient.rateFor("USD"))
            .isEqualByComparingTo("1.0");
    }
}
~~~

The mock server checks URLs, HTTP methods, headers, bodies, and how the client maps responses into objects. It does not verify networking, TLS, DNS, or real service behavior. For those guarantees, separate contract/deployment tests against a sandbox or test server are required.

## 11. Adding Configuration to a Test Slice Without Over-Expanding

A slice may need a configuration bean or custom converter. Two common approaches exist:

~~~java
@TestConfiguration(proxyBeanMethods = false)
static class TestBeans {
    @Bean
    Clock fixedClock() {
        return Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"),
            ZoneOffset.UTC
        );
    }
}
~~~

Import the configuration into the test:

~~~java
@WebMvcTest(InvoiceController.class)
@Import(InvoiceControllerTests.TestBeans.class)
class InvoiceControllerTests {
}
~~~

Or import a small, well-scoped production configuration:

~~~java
@JsonTest
@Import(MoneyJacksonConfiguration.class)
class MoneyJsonTests {
}
~~~

Do not use broad component scanning or arbitrarily import the main application class. If you have to import too many beans for a slice to work, the test may be covering more than one layer; consider `@SpringBootTest` in that case.

## 12. Managing Context Caching and Test Execution Time

Spring TestContext caches ApplicationContexts across tests sharing the same configuration. The cache key can differ when tests alter:

- configuration classes and initializers;
- active profiles;
- property sources;
- context customizers, mocks/bean overrides;
- parent context and web resource base path.

If every test uses a distinct combination of profiles, properties, or mocks, the number of contexts created grows and the suite slows down.

Ways to keep it under control:

- share test configurations across groups of tests with the same requirements;
- avoid declaring duplicate properties with different ordering/values unnecessarily;
- use `@DirtiesContext` only when a test genuinely mutates context state;
- clean up database/external resource state instead of repeatedly tearing down the context;
- place mocks at the exact slice that needs them.

`@DirtiesContext` marks a context as unusable and instructs Spring to evict it from the cache. Overusing it increases context startup time and can mask state-dependent tests.

## 13. Choosing Scope in Native Image Applications

There are three distinct questions:

1. **Does the test need Spring?** If not, use a unit test.
2. **Which part of Spring does the test need?** Use a slice if only testing MVC, JSON, persistence, or an HTTP client.
3. **What must the test prove after native compilation?** Run the native executable and verify real behavior.

`@SpringBootTest` and slice annotations primarily help build Spring test contexts on the JVM. They do not automatically turn every test into a native test. When running the native executable, you need to confirm the actual native artifact built from AOT output works properly.

### 13.1. What Should Be Tested with a Full Context

Use `@SpringBootTest` for flows requiring multiple components working together:

- application startup and bean graph;
- security + controller + service + repository;
- transaction boundaries spanning multiple beans;
- event listeners and application lifecycle;
- configuration properties alongside multiple integration adapters;
- custom auto-configuration and bean conditions.

If the test needs a real HTTP stack, select `RANDOM_PORT`. If you only need to invoke the MVC pipeline inside the full context, use `MOCK` and `@AutoConfigureMockMvc`.

### 13.2. What Should Be Tested with a Slice

| Need | Choice |
| --- | --- |
| Controller mapping, validation, exception handling | `@WebMvcTest` |
| Reactive controller | `@WebFluxTest` |
| JSON contracts and custom modules | `@JsonTest` |
| Entities, queries, and repositories | `@DataJpaTest` |
| JDBC queries/mappers | `@JdbcTest` |
| HTTP client mapping | `@RestClientTest` |

Slice tests typically run faster and clarify which layer is under verification. However, they do not prove that layers are wired properly in the full application context; keep a few integration tests to verify that wiring.

### 13.3. What Must Be Verified with the Native Executable

Native testing should focus on paths with high risk of differing from the JVM:

- application startup using the built executable;
- controller request/response over HTTP;
- Jackson serialization/deserialization for key DTOs;
- reflection, proxies, service loading, and resource lookups;
- drivers/databases/client libraries with reachability metadata;
- JNI and shared libraries if used by the application;
- runtime configuration, file mounts, permissions, and container environment.

A common pattern is using a JVM test runner to launch the native process/container, send HTTP requests or invoke real protocols, and inspect responses, logs, and exit codes. The test runner does not need to be embedded inside the application's native image.

If your project's Native Build Tools setup includes a native test task, verify exactly which environment that task runs test code in and what its test target is. Do not assume `nativeTest` is automatically equivalent to running every `@SpringBootTest`/slice context inside the native executable; integration details depend on plugin and project configuration.

## 14. A Practical Test Matrix

Example for a billing service:

| Behavior | Unit | Slice | Full Context | Native Executable |
| --- | --- | --- | --- | --- |
| Calculate invoice total | Yes | Not needed | Not needed | Only if specific risk exists |
| `Money` JSON | Possible | `@JsonTest` | Optional | Test via endpoint/serialization path |
| Controller validation | Insufficient | `@WebMvcTest` | Possible | Smoke/HTTP test |
| Repository queries | Insufficient | `@DataJpaTest` | Possible | Test when driver/metadata carries risk |
| Security + service + database | Insufficient | Insufficient | `@SpringBootTest` | Native HTTP test for critical flows |
| HTTP client mapping | Possible | `@RestClientTest` | Possible | Native test if client uses reflection/resources |
| Startup and bean conditions | No | Insufficient | `@SpringBootTest` | Launch native executable |
| JNI codec | Fake adapter | Unsuitable | Possible wiring | Native test on target OS/CPU |

There is no need to duplicate every JVM test as a native test. Select paths exposed to closed-world constraints, reflection, resources, JNI, service loading, or runtime differences for native execution.

## 15. Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `@SpringBootTest` cannot find application configuration | Test is outside package scan or multiple configurations exist | Specify `classes = ...` |
| `@WebMvcTest` is missing a service bean | Slice does not create the service layer | Use `@MockitoBean`/`@MockBean` or import the needed bean |
| Slice unexpectedly returns 401/403 | Security filter/chain is still applied | Configure user/authorities or import suitable security test config |
| `@DataJpaTest` uses embedded DB instead of real DB | Auto-config selects embedded database | Use Testcontainers or configure a test datasource |
| Test using `RANDOM_PORT` does not roll back database | Request runs on a separate server thread | Clean up data explicitly or use a dedicated database/schema |
| Suite creates too many ApplicationContexts | Profiles/properties/mocks produce different cache keys | Standardize context configurations |
| JVM tests pass but native endpoint fails | Missing reflection/resource/proxy/JNI metadata | Run the native path, read the stack trace, and add exact hints |
| Native test cannot find service provider | Missing service descriptor or provider metadata | Inspect dependency JARs and native reachability metadata |
| Test slice passes but production context fails | Slice does not load full application wiring | Add a few `@SpringBootTest` integration tests |

When reporting failures, record the annotations, web environment, active profiles, Spring Boot/JDK/GraalVM versions, and sanitized stack traces with secrets removed.

## 16. Workflow for Selecting Tests for a New Feature

Suppose you are adding an invoice creation endpoint with validation, `Money` JSON mapping, and a repository:

**Step 1 — verify standalone logic**

Test `InvoiceCalculator` and domain rules with unit tests without starting Spring.

**Step 2 — verify JSON**

Use `@JsonTest` to verify `MoneySerializer` and `MoneyDeserializer`, including inputs with missing fields or wrong types.

**Step 3 — verify the controller**

Use `@WebMvcTest(InvoiceController.class)` to verify routes, validation, status codes, and JSON responses. Mock `InvoiceService`.

**Step 4 — verify persistence**

Use `@DataJpaTest` to verify entity mappings and repository queries. Use a compatible database if queries rely on vendor-specific behavior.

**Step 5 — verify end-to-end wiring**

Use a few `@SpringBootTest` tests to verify that controller, service, repository, security, and configuration work together. Pick `MOCK` or `RANDOM_PORT` based on HTTP testing needs.

**Step 6 — verify natively**

Build the native executable, start it in the target environment/container, send an invoice creation request, and verify the response, database read/write, JSON mapping, and logs. If JNI or service providers are used, exercise those integration paths directly.

## 17. Pre-Release Checklist

- [ ] Unit tests do not start Spring when no container is needed.
- [ ] Each test slice loads only the layer under verification.
- [ ] `@SpringBootTest` is reserved for behaviors requiring the full context.
- [ ] The web environment (`MOCK`, `RANDOM_PORT`, `DEFINED_PORT`, `NONE`) matches the goal.
- [ ] Real HTTP tests handle data/transaction cleanup explicitly.
- [ ] Dependent beans are mocked or imported intentionally.
- [ ] Test profiles and properties do not unintentionally alter the AOT bean graph.
- [ ] Context cache is not fragmented by overly broad `@DirtiesContext` usage.
- [ ] Integration tests exist to verify wiring not covered by slices.
- [ ] Native tests launch the actual executable built from AOT output.
- [ ] Native tests cover risky reflection, JSON, resources, providers, JNI, or drivers.
- [ ] Tests run on an OS/CPU/container compatible with the deployment environment.
- [ ] Spring Boot, JDK, GraalVM, and Native Build Tools versions are documented.

**Key takeaway:** use unit tests for pure logic, test slices for a single Spring layer, `@SpringBootTest` for interactions requiring the full context, and native executable tests for post-compilation behavior. Slice tests and full-context tests on the JVM provide evidence of wiring and framework behavior; they do not replace testing the native executable in the target environment.

## References

- [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): `@SpringBootTest`, test slices, test utilities, and testing configuration.
- [Spring Boot Reference — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): bootstrapping contexts, web environments, and test properties.
- [Spring Boot Reference — Testing Auto-configurations](https://docs.spring.io/spring-boot/reference/testing/test-auto-configuration.html): test slices and auto-configuration.
- [Spring Framework — TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html): context caching, test execution, and Spring test support.
- [GraalVM Native Build Tools](https://graalvm.github.io/native-build-tools/latest/): Maven/Gradle integration and native test execution.
