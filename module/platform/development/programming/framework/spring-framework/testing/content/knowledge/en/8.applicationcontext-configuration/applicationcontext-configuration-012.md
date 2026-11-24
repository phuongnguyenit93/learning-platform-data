# Loading Only the Components Needed for the Risk Under Test

When testing a Spring application, the scope of the ApplicationContext determines which beans, configurations, and infrastructure are initialized. Loading the entire application for every test can make tests slow, hard to diagnose, and dependent on unrelated configurations. Conversely, trimming the context too aggressively can omit the very integration piece at risk of failing.

The guiding design principle is to **choose the smallest scope that genuinely verifies the risk of interest**. If the risk lies in a service's business rules, a Spring context is usually unnecessary. If the risk lies in request mapping and HTTP conversion, use an MVC test slice. If the risk lies in JPA mappings or queries, use a JPA slice. Only when you need to confirm multiple components are wired and collaborating under real application configuration is a broader context needed.

## 1. Start from the Risk, Not from the Annotation

Before picking @SpringBootTest, @WebMvcTest, or @DataJpaTest, articulate what could break and what evidence you need to observe.

A risk is the possibility that the system fails to uphold a commitment under specific conditions. For example:

- A controller might map a URL incorrectly, bind requests improperly, or return wrong JSON.
- A service might miscalculate business rules when a dependency returns edge-case data.
- A repository might generate invalid queries, map entities incorrectly, or fail to enforce constraints.
- Spring might fail to create a bean due to missing dependencies or unmatched conditional configuration.
- Transactions, caching, security filters, or AOP proxies might not behave as expected.
- Multiple components might work in isolation yet fail to collaborate when wired together in an ApplicationContext.

Each risk requires a different observation boundary. A test that simply instantiates a Java object and calls a method can prove object logic, yet cannot prove Spring injected the bean. A test using a mock repository can prove the service passes the right arguments, yet cannot prove real SQL or transactions work.

### Risk and Test Scope Matrix

| Risk to Verify | Typically Suitable Scope | Evidence |
|---|---|---|
| Pure Java rules in a service | Unit test without loading Spring | Return values, exceptions, object state |
| Controller mapping, binding, validation, response | @WebMvcTest | HTTP status, headers, body, model |
| Entity mapping, repository queries, persistence | @DataJpaTest | Data saved and queried through a test database |
| JSON serialization/deserialization | @JsonTest | JSON output and object structure |
| REST client request/response mapping | @RestClientTest | Outbound requests and response handling |
| Wiring of a specific group of beans | @ContextConfiguration or custom test slice | Beans instantiated and collaborating properly |
| Broad application configuration, multi-layer integration | @SpringBootTest | Application flow inside a real context |
| Transaction/cache/security/AOP proxies | Spring context test with relevant configuration | Behavior through proxies and real infrastructure |

This table is a starting point, not a rigid rule. For instance, an MVC slice may include security configuration if security filters are part of the risk; if the goal is solely controller JSON mapping, a narrower slice configuration may be appropriate.

## 2. Distinguishing Unit Tests from Spring Context Tests

Pure unit tests instantiate classes directly and pass dependencies via constructors or setters. They do not need a Spring container:

~~~java
class PriceServiceTest {

    private final DiscountPolicy discountPolicy =
            Mockito.mock(DiscountPolicy.class);

    private final PriceService priceService =
            new PriceService(discountPolicy);

    @Test
    void appliesVipDiscount() {
        Mockito.when(discountPolicy.rateFor("VIP"))
                .thenReturn(new BigDecimal("0.10"));

        BigDecimal total = priceService.calculate(
                new BigDecimal("100.00"), "VIP");

        assertEquals(new BigDecimal("90.00"), total);
    }
}
~~~

This test focuses on PriceService's algorithm. It runs fast and has no dependence on Spring configuration. However, it does not verify:

- Whether PriceService is discovered by component scanning.
- Whether the right DiscountPolicy bean is injected.
- Whether profiles or conditional configurations create the right bean.
- Whether transactional, caching, or AOP proxies are applied.
- Whether beans in the context can initialize together.

When the risk lies solely in the class's logic, that scope is ideal. When the risk lies in the container or integration, a test with a Spring context is needed.

### Not Every Class Annotated with @Service Needs @SpringBootTest

The @Service annotation marks a class for Spring to manage as a bean. It does not make all behavior of the class dependent on the container. If a test only needs to verify public methods and dependencies can be replaced with mocks, instantiating the object directly is enough.

Use a context when Spring's own behavior is what you need to verify: component scanning, bean conditions, dependency injection, proxies, transactions, security, or integration configuration.

## 3. Test Slices: Loading Part of the ApplicationContext by Component Type

Spring Boot provides test slices to focus on one area of an application. Each slice selects a set of auto-configurations and components matching its purpose.

Common annotations:

| Annotation | Focused Scope | Example Risks |
|---|---|---|
| @WebMvcTest | Spring MVC and related web components | Controller mapping, binding, validation, responses |
| @DataJpaTest | JPA, entities, repositories, and persistence test support | JPQL, derived queries, mappings, constraints |
| @JdbcTest | JDBC and related datasource configuration | SQL via JdbcTemplate |
| @JsonTest | JSON mappers and JSON test support | Serialization and deserialization |
| @RestClientTest | REST client test support | Request factory, URIs, headers, response conversion |
| @WebFluxTest | WebFlux controllers and reactive web infrastructure | Reactive handlers and responses |
| @DataMongoTest | MongoDB mapping and repository slice | Document mapping, MongoDB queries |
| @DataRedisTest | Redis data support | Serialization and Redis operations |
| @GraphQlTest | GraphQL controllers and related GraphQL infrastructure | GraphQL mappings and resolvers |

The exact list and scope depend on the Spring Boot version. Consult your project version's documentation to know which auto-configurations and component filters are activated.

### @WebMvcTest for MVC-Layer Risks

For example, a controller accepts a customer creation request and returns a response DTO. The risk to verify is that the request binds properly, validation is applied, and the response has the right structure.

~~~java
@WebMvcTest(CustomerController.class)
class CustomerControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private CustomerService customerService;

    @Test
    void returnsCreatedCustomer() throws Exception {
        given(customerService.create(any()))
                .willReturn(new CustomerResponse(42L, "Linh"));

        mockMvc.perform(post("/customers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "name": "Linh"
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.name").value("Linh"));
    }
}
~~~

@WebMvcTest loads only the required MVC components instead of the entire application. The service is replaced with a mock because service logic is outside the risk verified by this test.

If you need to test service logic, write a separate service unit test. If you need to verify that the real controller and service collaborate through bean wiring, choose a broader integration test.

### @DataJpaTest for Persistence-Layer Risks

When you need to test derived queries, entity mappings, or database constraints, the test requires JPA infrastructure and a test database:

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void findsCustomerByEmailIgnoringCase() {
        customerRepository.saveAndFlush(
                new Customer("linh@example.com"));

        Optional<Customer> result =
                customerRepository.findByEmailIgnoreCase(
                        "LINH@EXAMPLE.COM");

        assertTrue(result.isPresent());
        assertEquals(
                "linh@example.com",
                result.orElseThrow().getEmail());
    }
}
~~~

@DataJpaTest typically configures an embedded database when an appropriate dependency is present and runs each test inside a transaction that rolls back afterward. If the application depends on behavior specific to PostgreSQL, MySQL, or another specific database, use the same database engine in tests, often via Testcontainers. Embedded databases may not reproduce production dialects, constraints, collations, or SQL behavior.

### @JsonTest for JSON Risks

If the goal is to verify that Jackson serializes and deserializes DTOs accurately, there is no need to load MVC controllers or the whole application:

~~~java
@JsonTest
class CustomerJsonTest {

    @Autowired
    private JacksonTester<CustomerResponse> json;

    @Test
    void serializesCustomerResponse() throws Exception {
        CustomerResponse response =
                new CustomerResponse(42L, "Linh");

        assertThat(json.write(response))
                .extractingJsonPathNumberValue("$.id")
                .isEqualTo(42);

        assertThat(json.write(response))
                .extractingJsonPathStringValue("$.name")
                .isEqualTo("Linh");
    }
}
~~~

This test slice focuses on JSON support. It does not prove that a real endpoint returns valid JSON through the full MVC pipeline.

## 4. When Is @SpringBootTest Needed?

@SpringBootTest builds an ApplicationContext closer to the real Spring Boot application configuration. It fits when the risk lies in interactions across multiple beans or broad configuration.

For example, a customer registration workflow involves a controller, service, repository, transaction manager, and event publisher working together. If the goal is verifying that the entire flow works with real wiring, a broader context may be necessary.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class CustomerRegistrationIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void registersCustomerThroughApplicationFlow() throws Exception {
        mockMvc.perform(post("/customers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "name": "Linh",
                                  "email": "linh@example.com"
                                }
                                """))
                .andExpect(status().isCreated());

        assertTrue(customerRepository
                .findByEmail("linh@example.com")
                .isPresent());
    }
}
~~~

This example uses a broad context and MockMvc to traverse the real controller, service, and repository. The test asserts both the HTTP response and the persisted data.

Do not use @SpringBootTest if the goal is merely checking that one controller returns HTTP 201 or one repository query works. A broad context increases startup cost and the number of configurations that can affect the test. Save it for risks requiring multiple components working together.

### Choosing the Right Web Environment

@SpringBootTest supports several web environment modes:

| Mode | Meaning | When It Fits |
|---|---|---|
| MOCK (default) | Creates a mock web ApplicationContext without opening a real server | Using MockMvc or WebTestClient with appropriate mock server setup |
| RANDOM_PORT | Starts the server on a random port | Testing HTTP through a real server in tests |
| DEFINED_PORT | Starts the server on the configured port | Only when tests require a fixed port and controlled environment |
| NONE | Creates no web environment | Testing non-web application configuration |

Example using a real server:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CustomerHttpIntegrationTest {

    @LocalServerPort
    private int port;

    @Test
    void servesHealthEndpoint() {
        // Send HTTP client request to localhost and the assigned port.
    }
}
~~~

Use RANDOM_PORT when you need to test actual server startup, sockets, servlet containers, or end-to-end HTTP communication. If you only need to test handler mappings and responses through MVC, MockMvc is usually enough without opening a port.

## 5. Loading Exact Configuration with @ContextConfiguration

Not every test needing a Spring context requires Spring Boot. The Spring TestContext Framework lets you explicitly specify configurations to load using @ContextConfiguration.

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = {
        ServiceTestConfiguration.class,
        PricingService.class
})
class PricingServiceContextTest {

    @Autowired
    private PricingService pricingService;

    @Test
    void calculatesPriceUsingConfiguredPolicy() {
        // Verify behavior via beans in a small context.
    }
}
~~~

This approach fits when testing a specific set of Spring beans, such as constructor injection or a configuration class. It avoids whole-application component scanning and avoids pulling in unrelated auto-configuration.

A test configuration can declare test dependencies:

~~~java
@Configuration
class ServiceTestConfiguration {

    @Bean
    DiscountPolicy discountPolicy() {
        return new FixedDiscountPolicy();
    }
}
~~~

You can use @Import to bring required configurations or components into the context:

~~~java
@Configuration
@Import({PricingService.class, ServiceTestConfiguration.class})
class TestRootConfiguration {
}

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestRootConfiguration.class)
class PricingServiceContextTest {
    // ...
}
~~~

Place @Import on a configuration class loaded by @ContextConfiguration so Spring registers the exact specified components and configurations. The key is including only beans serving the test goal. Avoid importing a large configuration package if the test needs just one bean.

## 6. Intentionally Supplying Missing Dependencies

A test slice might not automatically load services, mappers, or custom components required by a controller. If that dependency is not part of the risk under test, replacing it with a mock usually makes sense. If the real dependency is part of the risk, import or configure it explicitly.

For example, an MVC slice needs a custom formatter to parse request parameters:

~~~java
@WebMvcTest(InvoiceController.class)
@Import(InvoiceWebConfiguration.class)
class InvoiceControllerTest {
    // ...
}
~~~

If you only need to swap the service:

~~~java
@WebMvcTest(InvoiceController.class)
class InvoiceControllerTest {

    @MockitoBean
    private InvoiceService invoiceService;
}
~~~

Decide based on these questions:

- Does the service contain logic currently under test? If not, mock it.
- Does the converter/formatter have behavior that needs verification? If yes, load the real implementation.
- Are security filters part of the risk? If yes, keep the relevant security configuration.
- Is a bean merely unrelated supporting infrastructure? Exclude it from the context or replace it with a test double.

### @Import and @TestConfiguration

@TestConfiguration allows declaring beans exclusively for tests. Example:

~~~java
@TestConfiguration
class FakeClockConfiguration {

    @Bean
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC);
    }
}
~~~

Then import it into the test:

~~~java
@SpringBootTest
@Import(FakeClockConfiguration.class)
class BillingServiceTest {

    @Autowired
    private BillingService billingService;
}
~~~

A nested @TestConfiguration is usually not automatically picked up by regular component scanning as a primary application configuration, so it can be imported intentionally. Exact usage should follow your project's Spring Boot version and test layout.

If you need to replace a real bean with a mock in the context, use the bean-override mechanism appropriate for your version. With Spring Framework 6.2 and later, you can use @MockitoBean. Some older Spring Boot projects use @MockBean. Avoid mixing multiple override mechanisms without good reason.

## 7. Creating Custom Test Slices When Built-In Slices Do Not Fit

Standard slices do not cover every architecture. If a group of tests repeatedly needs the same specialized set of configurations, you can create a meta-annotation or shared test configuration.

A custom slice typically combines:

- @BootstrapWith or the corresponding Spring Boot test bootstrapper.
- @TypeExcludeFilters to limit which component types are loaded.
- @ImportAutoConfiguration to load the right group of auto-configurations.
- Additional configuration annotations suited to the goal.

This is an advanced technique. Do not build a custom slice for a single test when a simple @Import or @ContextConfiguration suffices. Custom slices are useful when many tests along the same boundary need a consistent, reusable, maintainable configuration.

When creating a custom slice, document which components are permitted to load and why. If a filter accidentally excludes a needed bean, tests might only pass via mocks or manual setup without reflecting the intended boundary.

## 8. Selecting Components for Specific Risks

### Risk: Controller Has Correct Mapping and Validation

Use @WebMvcTest for the controller, keep MVC infrastructure and related validation, and mock the service if service logic is out of scope.

~~~java
@WebMvcTest(RegistrationController.class)
class RegistrationControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    RegistrationService registrationService;

    @Test
    void rejectsInvalidEmail() throws Exception {
        mockMvc.perform(post("/registrations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "email": "not-an-email"
                                }
                                """))
                .andExpect(status().isBadRequest());
    }
}
~~~

If the test fails to trigger Bean Validation because validator configuration was excluded from the slice or a required dependency is missing, check test dependencies and validation configuration. Do not jump straight to a full context if adding a suitable MVC/validation configuration is all that is needed.

### Risk: Repository Queries Work Against a Real Database

Use @DataJpaTest and an appropriate database. If queries depend on production-specific dialects or extensions, configure Testcontainers or a matching test datasource. Do not mock the repository, as doing so skips the very query you need to test.

### Risk: @Transactional Actually Opens and Rolls Back Transactions

This requires a Spring context with a transaction manager and matching resources. The test can invoke the bean through its Spring proxy and assert transaction outcomes. Unit tests instantiating objects directly bypass proxies. If you need to verify commit/rollback across multiple transactions or threads, design tests matching real transaction boundaries.

### Risk: Profiles and Conditional Beans Select the Right Implementation

Load the required configuration with a specific profile, or use a Spring Boot context test if conditions depend on application configuration. Verify the actual bean injected or the behavior of the chosen implementation. Mock beans can hide bean-creation condition bugs, so never override the very bean being verified.

### Risk: Controller and Service Collaborate via Dependency Injection

If you only need to verify HTTP mapping, use an MVC slice and mock the service. If you need to verify the controller receives the real service bean under application configuration, load a broader context or a custom test context containing both components. No real database is needed if the repository is outside the risk.

### Risk: Full Flow from HTTP to Database

Use @SpringBootTest or an integration test with equivalent scope, a real test database, and requests going through HTTP or MockMvc as required. This is where a broad context delivers valuable evidence.

## 9. Avoiding Over-Loading and Under-Loading

Two opposite mistakes frequently occur:

**Over-loading:** using @SpringBootTest for a service calculation or simple controller response. The test boots many beans, requires extensive configuration, and can fail due to an unrelated subsystem. Execution time grows and failure root causes become harder to pinpoint.

**Under-loading:** using unit tests with mocks for a risk involving Spring proxies, SQL, validation infrastructure, or security filters. The test passes yet real behavior can still fail because the risky part never ran.

A good strategy is escalating scope only as far as needed:

~~~text
Pure Java logic
      |
      v
Unit test without Spring
      |
      | need to verify specific infrastructure?
      v
Test slice / narrowly configured context
      |
      | need multiple layers working together?
      v
@SpringBootTest or end-to-end test
~~~

Not every test type needs to appear in every project. The goal is having evidence right where the risk exists.

## 10. Speed and Context Caching

Initializing an ApplicationContext takes time. The Spring TestContext Framework caches contexts so tests with equivalent configurations can reuse an already initialized context.

Factors that make contexts differ and reduce reuse include:

- Different configuration classes.
- Different active profile lists.
- Different property sources.
- Different context initializers.
- Different bean overrides.
- Different context hierarchies.

Using consistent test configuration for tests sharing the same goal helps leverage the cache. However, do not force all tests to share one giant context just to maximize cache hits. The context must match the risk being verified first.

A small test slice usually starts faster than a full context. A pure unit test is faster still because there is no container. In a suite with hundreds of tests, separating scopes significantly cuts total execution time.

## 11. Profiles, Properties, and Conditional Configuration

Configuration risks can be verified by loading a context with specific profiles or properties.

Example:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class PaymentConfigurationTest {

    @Autowired
    PaymentGateway paymentGateway;

    @Test
    void usesTestPaymentGateway() {
        assertInstanceOf(
                StubPaymentGateway.class,
                paymentGateway);
    }
}
~~~

If a bean is selected by property:

~~~java
@SpringBootTest(properties = {
        "payment.mode=stub"
})
class PaymentModeConfigurationTest {
    // Verify the bean created according to the property.
}
~~~

Identify clearly which configuration is under test. If a test uses @MockitoBean to replace PaymentGateway, it no longer proves that conditional configuration chose the right implementation. For wiring risks, let the real bean be created and assert its implementation or behavior.

## 12. Security and Filters: Keep Them When They Are the Risk

@WebMvcTest can load security configuration and related filters depending on the application and test setup. If the test aims to confirm an endpoint rejects unauthorized users, security infrastructure must participate in the test.

~~~java
@WebMvcTest(AdminController.class)
class AdminControllerSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void deniesAnonymousRequest() throws Exception {
        mockMvc.perform(get("/admin/users"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

The actual status could be 401, a 302 redirect, or another status depending on the application's authentication mechanism and entry point. Tests must assert the configured security contract.

If an MVC test focuses solely on JSON mapping and security is out of scope, you can configure the test to bypass filters or supply an appropriate security collaborator. Never disable filters in a test claiming to verify authorization.

## 13. Using @DirtiesContext Selectively

@DirtiesContext marks an ApplicationContext as no longer fit for caching and instructs Spring to evict that context after the test or class according to the declared mode.

It can be necessary when a test mutates a singleton bean or context state in a way that cannot be safely restored. However, overusing this annotation forces Spring to restart the context repeatedly and slows down the suite.

Before using it, ask:

- Did the test genuinely alter the structure or shared state of the ApplicationContext?
- Can bean state be reset in @AfterEach?
- Can a dedicated context with its own configuration be used?
- Is the test modifying an external resource or just database records? If it is only data, transaction rollback or proper cleanup may suffice.

@DirtiesContext does not replace cleaning up databases, files, or external services. It only manages the ApplicationContext lifecycle in Spring TestContext.

## 14. Common Mistakes When Choosing Context Scope

### Using @SpringBootTest for Every Test

Booting the whole application makes tests slow and introduces unrelated failure points. Choose unit tests or slices when they suffice to observe the behavior under test.

### Mocking the Very Bean That Represents the Risk

If the goal is confirming Spring creates the right interface implementation for a profile, replacing that bean with a mock skips the risk. Keep the real implementation in the test context.

### Importing Unnecessary Production Configuration

A configuration class can pull in datasources, brokers, clients, or other services. Choose smaller configurations or supply test configurations tailored to the test.

### Trimming the Context Too Deeply

If the risk involves transaction proxies, a unit test calling the object directly bypasses the proxy. If the risk involves repository queries, mocking the repository skips the database. Expand scope up to the exact infrastructure under test.

### Disabling Filters in Security Tests

Disabling filters can make tests easy to pass while removing the very mechanism that needs verification. Only skip filters when security is outside the test's risk.

### Using an Embedded Database for Every Repository Test

Embedded databases are not necessarily compatible with the production database. Use the same database engine or Testcontainers when dialect differences could affect results.

### Using @DirtiesContext to Fix Every Test Failure

A dirtied context does not fix dirty database records, leftover temporary files, or stateful external services. Identify which kind of state needs resetting.

### Assuming Context Startup Success Is Enough

Successful context startup only proves beans can be created under the test configuration. It does not prove requests, transactions, queries, or business flows are right. Tests must still trigger behavior and assert outcomes.

## 15. Workflow for Selecting an ApplicationContext for a New Test

1. **Describe the risk:** what can go wrong and what observable consequence does it cause?
2. **Identify the boundary:** class logic, MVC, persistence, JSON, REST client, proxy, or full flow?
3. **List required components:** keep only the beans, filters, converters, transaction managers, or databases needed to exercise that boundary.
4. **Pick the smallest scope:** unit test, test slice, @ContextConfiguration, or @SpringBootTest.
5. **Replace out-of-scope collaborators:** use mocks or fakes for isolation, without replacing the component under test.
6. **Add configuration intentionally:** use @Import, @TestConfiguration, profiles, and properties appropriately.
7. **Check the evidence:** the test must exercise real behavior at the chosen boundary and assert directly against the risk.
8. **Evaluate cost:** if the context loads many unrelated components, reconsider the scope; if the test skips proxies, databases, or filters that carry risk, widen the scope.

### Scope Decision Example

Suppose you need to test an invoice creation endpoint:

- If the risk is whether the controller returns HTTP 201 and valid JSON, use @WebMvcTest and mock InvoiceService.
- If the risk is whether InvoiceService calculates tax accurately, unit-test the service and stub the tax policy.
- If the risk is whether InvoiceRepository saves totals and queries accurately, use @DataJpaTest with an appropriate database.
- If the risk is whether @Transactional ensures multiple writes succeed or roll back together, use a Spring context with a transaction manager and database.
- If the risk is the entire invoice creation request flowing through controller, service, repository, and database, use a broader integration test.

A single feature may need multiple tests at different boundaries. Each test should prove a clear group of risks so that when a failure occurs, you know which layer to investigate.

## Conclusion

Choosing ApplicationContext scope based on the risk under test keeps tests fast and produces accurate evidence. Unit tests fit pure Java logic; test slices fit MVC, JPA, JSON, or clients; @ContextConfiguration and @Import fit when a specific group of beans is needed; @SpringBootTest belongs to risks requiring multiple collaborating components or full application configuration. Keep only the required infrastructure, replace out-of-scope collaborators, and never mock the component you are trying to verify.
