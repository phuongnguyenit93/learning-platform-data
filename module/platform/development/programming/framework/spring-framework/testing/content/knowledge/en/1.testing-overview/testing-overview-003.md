# The Role of Spring Test Alongside JUnit and Assertion Libraries

When testing a Spring application, there are three distinct questions to answer:

1. Who discovers and runs each test, and manages the test lifecycle?
2. Who prepares the Spring environment that the code needs to operate, such as the ApplicationContext, dependency injection, transactions, or web infrastructure?
3. Who checks whether the actual result matches the expected result?

JUnit, Spring Test, and assertion libraries handle those three groups of responsibilities. They work together within the same test, yet do not replace one another. Understanding this boundary helps you choose the right test type, avoid starting the entire application when you only need to verify one class, and still verify behaviors that depend on the Spring container.

## Three Components, Three Responsibilities

| Component | Primary Responsibility | Examples |
|---|---|---|
| JUnit | Test organization and execution: test discovery, lifecycle callbacks, running test cases, supporting parameterized tests and extensions | `@Test`, `@BeforeEach`, `@AfterEach`, `@ParameterizedTest` |
| Spring Test | Connects tests to Spring mechanisms: creates and manages the ApplicationContext, injects beans into tests, sets up profiles/properties, transactions, and web testing utilities | `@SpringJUnitConfig`, `@ContextConfiguration`, `@ActiveProfiles`, `MockMvc` |
| Assertion library | Expresses expected conditions and compares actual results against those conditions | JUnit Assertions, AssertJ, Hamcrest |

JUnit answers the question "which test should run, and in what order/lifecycle?". Spring Test answers "what kind of Spring environment does the test need?". The assertion library answers "is this result right?".

A single test can use all three: JUnit invokes the test method; Spring Test prepares the beans and environment; the test method calls the object under test and then uses AssertJ to verify the outcome.

~~~mermaid
flowchart TD
    A["JUnit Jupiter discovers and runs tests"] --> B["SpringExtension integrates with JUnit"]
    B --> C["Spring Test prepares TestContext and ApplicationContext"]
    C --> D["Inject beans / configure test environment"]
    D --> E["Test invokes behavior under test"]
    E --> F["Assertions verify results"]
~~~

### JUnit: The Test Execution Framework

JUnit is the Java testing foundation. With JUnit Jupiter, developers mark methods with `@Test`, prepare data with `@BeforeEach`, clean up with `@AfterEach`, group tests with nested tests, or run multiple datasets with parameterized tests.

JUnit does not automatically know how to create a Spring ApplicationContext just because a test is checking a service annotated with `@Service`. If a test needs dependency injection or Spring configuration, an integration point must connect JUnit with Spring. Spring Test provides that integration point.

JUnit also includes basic assertions such as `assertEquals`, `assertTrue`, and `assertThrows`. Therefore, a JUnit test can run completely without AssertJ or Hamcrest.

### Spring Test: Environment and Spring Integration

Spring Test is the testing support module of the Spring Framework. It lets tests rely on the capabilities the real application depends on, for example:

- Loading configuration and creating an ApplicationContext so beans are initialized according to Spring's rules.
- Injecting beans into the test class itself.
- Activating profiles and properties dedicated to the test environment.
- Managing transactions for tests, typically allowing data to roll back after a test finishes.
- Providing web-layer testing tools such as MockMvc and WebTestClient.
- Coordinating test preparation, execution, and cleanup steps through the TestContext Framework and test execution listeners.

Spring Test does not decide whether a test passes or fails. It sets up the conditions so the test can exercise the behavior to verify.

### Assertion Libraries: Expressing Expectations

Assertion libraries make check conditions clear and readable. For example, with JUnit you can write:

~~~java
assertEquals(new BigDecimal("110.00"), actual);
~~~

With AssertJ, you can write:

~~~java
assertThat(actual).isEqualByComparingTo("110.00");
~~~

Hamcrest typically expresses expectations using matchers:

~~~java
assertThat(actual, is(equalTo(expected)));
~~~

These libraries focus on expressing and verifying outcomes. They do not start Spring, inject beans, or create transactions on their own. A project may use JUnit assertions, AssertJ, Hamcrest, or a combination depending on its needs.

## How Does Spring Test Integrate with JUnit?

Spring Test integrates with JUnit Jupiter through `SpringExtension`. This extension participates in JUnit's lifecycle and delegates Spring-related work to the TestContext Framework. As a result, a test can receive beans from the ApplicationContext just like a Spring-managed component.

Direct declaration typically combines `@ExtendWith(SpringExtension.class)` and `@ContextConfiguration`. Spring also provides the composed annotation `@SpringJUnitConfig` for a more concise declaration.

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;

@SpringJUnitConfig(InvoiceTest.TestConfig.class)
class InvoiceTest {

    @Autowired
    private InvoiceService invoiceService;

    @Test
    void calculatesTotalWithTax() {
        var total = invoiceService.total(new BigDecimal("100.00"));

        assertThat(total).isEqualByComparingTo("110.00");
    }

    @Configuration
    static class TestConfig {
        @Bean
        TaxPolicy taxPolicy() {
            return new TaxPolicy(new BigDecimal("0.10"));
        }

        @Bean
        InvoiceService invoiceService(TaxPolicy taxPolicy) {
            return new InvoiceService(taxPolicy);
        }
    }
}
~~~

In this example:

- `@Test` belongs to JUnit Jupiter and marks the method to run.
- `@SpringJUnitConfig` belongs to Spring Test. It connects Spring with JUnit and specifies the configuration used to create the ApplicationContext.
- `@Autowired` instructs Spring to inject the bean into the test.
- `@Bean` declares the objects to be managed inside the ApplicationContext.
- `assertThat` belongs to AssertJ and checks the business result.

The example assumes `InvoiceService` and `TaxPolicy` are business classes with matching constructors. The key observation is that the test receives `InvoiceService` from the container; it does not instantiate the service with `new`. Consequently, the test also verifies how Spring wires dependencies together.

If you remove Spring Test, JUnit can still invoke a test method, but there is no longer a mechanism to create the ApplicationContext and inject `InvoiceService` as shown. If you remove AssertJ, the test can still run using JUnit assertions. If you remove JUnit, another test runner is needed to discover and execute the tests.

In projects using JUnit 4, Spring previously integrated via `SpringRunner`/`SpringJUnit4ClassRunner` with `@RunWith`. With JUnit Jupiter, the modern integration is `SpringExtension`; you should not mix annotations from both JUnit generations in the same test class.

## What Capabilities Does Spring Test Provide?

### 1. Creating and Reusing the ApplicationContext

Many behaviors only appear when objects are created through Spring: constructor injection, field injection, AOP proxies, bean scopes, event listeners, transaction proxies, or configuration from `@Configuration` classes. Calling a service's constructor directly in a unit test does not verify those container behaviors.

The TestContext Framework manages the ApplicationContext for tests that need Spring. It can reuse contexts across tests that share the same configuration, reducing startup cost. The more test configurations diverge, the more contexts are likely to be created, making the suite take longer to run.

Some common annotations:

| Annotation | Meaning |
|---|---|
| `@ContextConfiguration` | Specifies configuration classes or resources used to load the ApplicationContext |
| `@SpringJUnitConfig` | Combines Spring integration for JUnit Jupiter with context configuration |
| `@SpringJUnitWebConfig` | Variant intended for web context configuration |
| `@ActiveProfiles` | Activates profiles when creating the test context |
| `@TestPropertySource` | Declares additional or overriding properties for tests |
| `@DynamicPropertySource` | Registers dynamic properties, often useful when a test service's address or port is only known at runtime |
| `@DirtiesContext` | Marks a context as modified so it must be evicted from the cache and recreated |

For example, a test requiring the `test` profile can declare:

~~~java
@SpringJUnitConfig(AppTestConfig.class)
@ActiveProfiles("test")
@TestPropertySource(properties = {
    "feature.invoice.enabled=true"
})
class InvoiceFeatureTest {
    // Tests use beans created with the profile and properties above.
}
~~~

`@DirtiesContext` should be used only when a test genuinely alters configuration state or beans in the context to a degree that cannot be safely restored. Overusing this annotation defeats context caching and forces subsequent tests to recreate the context.

### 2. Managing Transactions for Tests

When testing repositories or data-writing business flows, tests often need transactions to isolate data. Spring Test supports test transactions through `@Transactional` and a transaction manager in the context.

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Transactional
class AccountRepositoryTest {

    @Autowired
    private AccountRepository accountRepository;

    @Test
    void savesAndFindsAccount() {
        accountRepository.save(new Account("A-100", "Lan"));

        var account = accountRepository.findByCode("A-100");

        assertThat(account).isPresent();
        assertThat(account.get().getName()).isEqualTo("Lan");
    }
}
~~~

With transactions managed by Spring Test, the default behavior is typically to roll back when the test completes. This keeps data created during a test from remaining as committed data afterward. You can adjust this behavior with `@Commit` or `@Rollback(false)` when a test scenario requires it.

Understand the exact scope of rollback: it applies only to the transaction managed by the test. An HTTP call to another system, a file write, a message sent to a broker, or work running on another thread is not automatically rolled back with the test transaction. If the application opens an independent transaction or commits explicitly, the test cannot assume all changes are undone either.

Spring Test also supports running SQL scripts for tests with `@Sql`, which is useful for preparing data or checking database state for a specific scenario.

### 3. Testing the Web Layer

A Spring MVC controller is not just a Java method. When handling a request, it also involves URL mapping, parameter binding, validation, converters, exception handlers, interceptors, and response formatting. Calling a controller method directly only tests the method's logic; it bypasses most of the Spring MVC HTTP pipeline.

MockMvc lets you send simulated requests through the Spring MVC infrastructure and inspect responses without opening an HTTP port or starting a real server.

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@RestController
class GreetingController {
    @GetMapping("/greeting")
    String greeting(@RequestParam(defaultValue = "world") String name) {
        return "Hello, " + name;
    }
}

class GreetingControllerTest {
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
            .standaloneSetup(new GreetingController())
            .build();
    }

    @Test
    void returnsGreeting() throws Exception {
        mockMvc.perform(get("/greeting").param("name", "Lan"))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello, Lan"));
    }
}
~~~

Here, JUnit manages the test lifecycle; MockMvc belongs to the Spring Test ecosystem and simulates requests/responses through the Spring MVC pipeline; `ResultMatcher` instances assert HTTP status and body. You can also combine AssertJ when checking data extracted from the response.

The example uses `standaloneSetup` to instantiate the controller directly, which fits when focusing on controller mappings and behavior. It does not prove that the full application configuration, dependency injection, or MVC components declared in the ApplicationContext work properly. When you need to verify those configurations, build MockMvc from a WebApplicationContext or use the appropriate Spring Boot test configuration.

For reactive applications, WebTestClient provides a client-style request/response testing API. It can target a mock environment or a live server depending on configuration. Choosing MockMvc or WebTestClient depends on the web stack and test objective, not on which assertion library you use.

## How Do Spring Framework Test and Spring Boot Test Relate?

Spring Framework provides Spring Test as a testing foundation integrated with the container and framework modules. Spring Boot builds additional utilities on top to test auto-configured Boot applications.

Several common annotations belong to Spring Boot Test, not to core Spring Framework Test:

- `@SpringBootTest` initializes the application according to Spring Boot configuration for integration testing.
- `@WebMvcTest` narrows the context to an MVC slice.
- `@DataJpaTest` focuses on persistence/JPA components.
- `@AutoConfigureMockMvc` configures MockMvc within a Spring Boot context.

Spring Boot Test uses Spring Test underneath, yet the two names are not synonymous. When reading dependencies or annotations in a project, distinguish whether a feature comes from Spring Framework or from Spring Boot's additions. For instance, `@SpringJUnitConfig` is from Spring Test; `@SpringBootTest` is from Spring Boot Test.

## Plain JUnit or Adding Spring Test?

Not every test in a Spring project needs to start Spring. The decision should rest on what the test needs to prove.

| Test Objective | Appropriate Tooling | Reason |
|---|---|---|
| Calculation functions, pure Java business rules, no beans needed | JUnit + assertion library | Runs fast, minimal dependencies, easy to isolate |
| Service needing dependency injection or bean configuration verification | JUnit + Spring Test | Requires a real ApplicationContext |
| Repository needing mapping and query verification against a test database | JUnit + Spring Test and appropriate test database | Needs persistence infrastructure and transactions |
| Controller needing Spring MVC mapping, binding, status, and response verification | JUnit + MockMvc | Needs the MVC pipeline, usually without a real server |
| Application flow needing multiple beans and Boot configuration working together | JUnit + Spring Test/Spring Boot Test | Needs a broader context scope |

A balanced strategy usually has many small, fast unit tests, a set of slice tests checking individual layers, and a number of integration tests verifying that components collaborate. There is no need to turn every test into an integration test just because the application uses Spring.

## Common Misconceptions

**Thinking having JUnit means you are already testing Spring.** JUnit executes tests, but does not create an ApplicationContext or perform injection by itself. Tests using `@Autowired` require integration with Spring Test.

**Thinking Spring Test replaces JUnit.** Spring Test adds the Spring environment and testing utilities. JUnit typically remains the framework driving test execution in projects using JUnit Jupiter.

**Thinking AssertJ or Hamcrest can start Spring.** Assertion libraries only check outcomes. They do not manage beans, profiles, transactions, or web contexts.

**Starting the entire context for a simple calculation.** If a class can be tested by passing dependencies directly through its constructor, a plain JUnit unit test is usually faster and clearer. Only use Spring Test when Spring integration behavior itself is within the scope to verify.

**Thinking rollback covers every side effect.** Transaction rollback does not retract sent HTTP requests, published messages, written files, or operations outside the transaction. Those side effects require separate isolation and cleanup mechanisms.

**Overusing `@DirtiesContext`.** This annotation can undermine context caching efficiency. Before using it, identify what state the test modified and whether that state can be restored directly.

**Using MockMvc and concluding that the live server works properly.** MockMvc tests the Spring MVC pipeline in a mock environment. It does not test port binding, network configuration, TLS, or the full behavior of a running server. If those factors are within requirements, an integration test against a real server is needed.

## How to Remember When Designing Tests

Start by identifying the behavior you need to prove:

- If you only need to invoke a Java object and compare results, JUnit plus an assertion library is enough.
- If you need Spring to create beans, inject dependencies, load profiles/properties, or manage transactions, add Spring Test.
- If you need to test requests flowing through Spring MVC, use MockMvc; if testing a reactive application, consider WebTestClient.
- If you need to verify auto-configuration and how Spring Boot starts the application, use Spring Boot Test utilities with an appropriate context scope.
- Choose an assertion library based on the clarity of check conditions; changing the assertion library does not change how the Spring context is initialized.

JUnit drives the test, Spring Test prepares and integrates the Spring environment, and the assertion library verifies the result. When these three responsibilities are cleanly separated, each test accurately reflects what it verifies and avoids paying unnecessary infrastructure startup costs.
