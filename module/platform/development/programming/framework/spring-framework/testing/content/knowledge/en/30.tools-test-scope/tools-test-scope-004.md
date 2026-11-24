# Distinguishing @TestConfiguration from Regular Spring Framework Configuration

**Context:** Spring Framework Testing → Tools and Scope.

When writing tests for a Spring application, you sometimes need to register extra beans solely for test scenarios: a fixed Clock, a fake gateway, a special data converter, or a bean that helps observe behavior. An important question is whether to declare that bean using regular **@Configuration** or **@TestConfiguration**.

The two annotations are related, yet serve different purposes:

- **@Configuration** is the standard configuration annotation of Spring Framework. An annotated class can declare beans for an application's or a test's ApplicationContext.
- **@TestConfiguration** is a Spring Boot Test annotation used to declare additional configuration dedicated to tests. It is designed not to be automatically discovered by regular component scanning.

This distinction affects how Spring locates configuration, how test configuration combines with application configuration, and the risk of a test-only configuration accidentally entering an unintended context. Choose the annotation based on how the context is initialized and the scope in which the bean should exist.

## 1. Origin and Role of Both Annotations

### 1.1. @Configuration belongs to Spring Framework

@Configuration resides in the org.springframework.context.annotation package. It is the foundational annotation for declaring Java-based configuration.

~~~java
@Configuration
class ApplicationConfig {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }

    @Bean
    OrderService orderService(OrderRepository repository, Clock clock) {
        return new OrderService(repository, clock);
    }
}
~~~

Spring reads the configuration class and registers the beans declared with @Bean. This configuration can be loaded via component scanning, @Import, or specified directly in @ContextConfiguration.

A regular @Configuration does not inherently mean the beans only exist in tests. If that class is loaded into the application's ApplicationContext, its beans belong to that context.

### 1.2. @TestConfiguration belongs to Spring Boot Test

@TestConfiguration resides in the org.springframework.boot.test.context package. It is a test-focused specialization of @Configuration.

~~~java
@TestConfiguration
class OrderTestConfiguration {

    @Bean
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2025-01-15T10:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

This annotation is provided by Spring Boot in the spring-boot-test module. It is not an annotation belonging to Spring Framework core. Projects using only plain Spring Framework and Spring Test will not have @TestConfiguration unless Spring Boot Test is added.

@TestConfiguration also lets you declare beans with @Bean, import other configurations, and combine with regular Spring configuration mechanisms. The key difference is that the class is marked as a test component and therefore excluded from discovery by regular component scanning.

### 1.3. Comparison table

| Criterion | @Configuration | @TestConfiguration |
|---|---|---|
| Source | Spring Framework | Spring Boot Test |
| Purpose | Declare beans for an ApplicationContext | Declare additional configuration for tests |
| Regular component scanning | Can be discovered as a configuration component | Excluded from regular component scanning |
| Usage scope | Runtime application and tests | Primarily test contexts |
| Uses @Bean | Yes | Yes |
| Automatically replaces application beans? | No | No |
| Can be loaded with @Import | Yes | Yes |
| Can be used in @ContextConfiguration | Yes | Yes when the project has Spring Boot Test |
| Fits Boot test slices | Possible, if explicitly imported | Typically suited to supplement test beans |
| Automatically creates a separate context? | No | No |

Point to remember: @TestConfiguration changes how the configuration class is recognized during component scanning. It does not automatically create a separate ApplicationContext, does not automatically mock existing beans, and does not automatically override application configuration.

## 2. Why Does Spring Boot Provide @TestConfiguration?

In a Spring Boot application, the primary configuration is typically discovered from a class annotated with @SpringBootApplication or @SpringBootConfiguration. Tests often want to keep the primary application configuration and only add a few beans for a scenario.

For example, a test needs to replace the system Clock with a fixed Clock so results do not depend on execution time. If you declare a nested class using only @Configuration inside the test class, Spring Boot may treat that class as the primary configuration discovered for the test. This can cause the test to load only that small configuration instead of the application configuration.

@TestConfiguration is designed to solve this situation: a nested test configuration is used alongside the application's primary configuration.

~~~text
@SpringBootTest
      |
      v
Locate primary application configuration
@SpringBootApplication
      |
      +---- Application beans
      |
      +---- Test-only configuration
              @TestConfiguration
              |
              +---- fixed Clock
              +---- fake gateway
              +---- test helper bean
~~~

With a nested @TestConfiguration, Spring Boot can use that configuration together with the primary configuration the test requests. With a top-level @TestConfiguration class, tests typically import it explicitly with @Import to bring the configuration into the context.

## 3. Component Scanning and Discovery Scope

### 3.1. @Configuration can be discovered by component scanning

@Configuration is a component candidate. If the class's package falls within component scan scope, Spring can discover the configuration class and register its beans.

~~~java
@Configuration
class SharedApplicationConfiguration {

    @Bean
    Clock systemClock() {
        return Clock.systemUTC();
    }
}
~~~

If this class sits in a package scanned by @SpringBootApplication, it can be loaded in the application's ApplicationContext. Therefore, placing a test-only configuration in a production package can cause it to be discovered unintentionally if regular @Configuration is used.

A separate test source set is typically not packaged into the production artifact, yet scan configuration and module organization still need to be clear. Do not rely solely on a file living in src/test/java to assume component scanning will or will not find it in every type of test context.

### 3.2. @TestConfiguration is excluded from regular component scanning

@TestConfiguration is annotated as a test component. Spring Boot uses this characteristic to exclude that configuration from discovery by regular component scanning.

~~~java
@TestConfiguration
class TestClockConfiguration {

    @Bean
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2025-02-01T00:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

The class above will not automatically appear in the application context merely because package scanning passes over its location. Tests must load it intentionally, such as via @Import or the nested test configuration mechanism.

This helps prevent test-only configuration from accidentally being registered when the application starts normally.

### 3.3. Do not confuse component scanning with explicit import

Being excluded from component scanning does not mean Spring cannot load @TestConfiguration. When a test explicitly specifies the class via @Import or @ContextConfiguration, Spring still processes that configuration.

~~~java
@SpringBootTest
@Import(TestClockConfiguration.class)
class OrderServiceTests {
    // The test uses the Clock declared in TestClockConfiguration.
}
~~~

Component scanning is a mechanism for automatically finding components by package. @Import is an explicit request to include a configuration class or component in the context. These two mechanisms are different.

## 4. Using Nested @TestConfiguration in Spring Boot Tests

### 4.1. Nested configuration supplements application configuration

A common approach is to declare a static nested class directly inside the test:

~~~java
@SpringBootTest
class OrderServiceIntegrationTest {

    @Autowired
    OrderService orderService;

    @TestConfiguration
    static class TestConfig {

        @Bean
        Clock fixedClock() {
            return Clock.fixed(
                    Instant.parse("2025-03-01T09:00:00Z"),
                    ZoneOffset.UTC
            );
        }
    }

    @Test
    void createsOrderWithDeterministicTimestamp() {
        // The test uses fixedClock loaded alongside the application context.
    }
}
~~~

The nested class must be static so it does not depend on an instance of the test class. The configuration is used in addition to the Spring Boot test's primary configuration, so other production beans can still be loaded according to the test setup.

This approach fits when the configuration serves only one test class and does not need to be reused elsewhere.

### 4.2. Nested @Configuration has a different meaning

If you replace @TestConfiguration with @Configuration:

~~~java
@SpringBootTest
class OrderServiceIntegrationTest {

    @Configuration
    static class TestConfig {

        @Bean
        Clock fixedClock() {
            return Clock.systemUTC();
        }
    }
}
~~~

A nested @Configuration can be treated by Spring Boot as the primary configuration discovered for the test, rather than merely an addition to the application configuration. As a result, the test may fail to load the primary configuration the author intended.

This is why Spring Boot distinguishes the two annotations. When you want to keep the application's primary configuration and add test-specific beans, use @TestConfiguration for the nested class.

### 4.3. When nested config is no longer the best choice

If multiple test classes need the same fake, Clock, or test helper, you can extract the configuration into a top-level class in the test source set:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class SharedOrderTestConfiguration {

    @Bean
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2025-03-01T09:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

Then import it in the tests that need it:

~~~java
@SpringBootTest
@Import(SharedOrderTestConfiguration.class)
class OrderServiceIntegrationTest {
    // ...
}
~~~

~~~java
@SpringBootTest
@Import(SharedOrderTestConfiguration.class)
class OrderControllerIntegrationTest {
    // ...
}
~~~

A top-level configuration can be reused while still being loaded only in tests that import it. Because @TestConfiguration is not automatically discovered by regular component scanning, sharing it still requires explicit importing.

## 5. Using @TestConfiguration in Test Slices

### 5.1. Test slices load only part of the application

Spring Boot test slices such as @WebMvcTest, @DataJpaTest, or @JsonTest load only the components relevant to one testing layer. They do not create the full ApplicationContext like @SpringBootTest by default.

Example:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {
    // Loads only the MVC slice needed for the controller test.
}
~~~

If the controller depends on a gateway or service that the slice does not create automatically, you can supply a mock bean or import a test configuration.

### 5.2. Adding beans for @WebMvcTest

~~~java
@WebMvcTest(OrderController.class)
@Import(OrderMvcTestConfiguration.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;
}

@TestConfiguration(proxyBeanMethods = false)
class OrderMvcTestConfiguration {

    @Bean
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2025-04-01T00:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

The additional configuration contains only the beans the MVC test needs. Business dependencies can be mocked separately using the bean override mechanism appropriate for the Spring Boot/Spring Framework version in use.

Do not import the entire production configuration just to grab one small bean if doing so pulls in datasources, brokers, or clients outside the slice's scope. Keeping test slices focused helps tests start fast and verify the right layer.

### 5.3. Adding configuration for @DataJpaTest

~~~java
@DataJpaTest
@Import(JpaTestClockConfiguration.class)
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository repository;
}

@TestConfiguration(proxyBeanMethods = false)
class JpaTestClockConfiguration {

    @Bean
    Clock testClock() {
        return Clock.fixed(
                Instant.parse("2025-05-01T12:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

If the test needs a bean supporting an entity listener or auditing, you can import a small configuration. Check whether the current slice already provides that bean to avoid duplicate declarations or unintended changes.

### 5.4. A test slice does not mean test config is loaded automatically

A top-level class annotated with @TestConfiguration is not brought into a slice merely by residing in the same package. Import it explicitly or declare a nested class following Spring Boot test rules.

If you forget to import it, the test may report a missing bean when the context initializes. Do not fix this by adding a broad @ComponentScan across the whole application, as that can break slice scope and cause the test to load too many beans.

## 6. Using Configuration in Plain Spring Framework

### 6.1. @TestConfiguration does not belong to Spring Framework core

If a project uses only Spring Framework and Spring Test without Spring Boot Test, the @TestConfiguration annotation is not available.

In that case, use regular @Configuration while loading it explicitly in the test context:

~~~java
@Configuration
class OrderTestBeans {

    @Bean
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2025-06-01T00:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

Test:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = {
        OrderService.class,
        OrderTestBeans.class
})
class OrderServiceTest {

    @Autowired
    OrderService orderService;
}
~~~

Here, @ContextConfiguration specifies the exact configuration and components to place into the context. The test configuration is not loaded by the application's component scanning if the test does not ask to scan that package.

### 6.2. Using @Import to separate configuration

You can declare a base configuration and import test config:

~~~java
@Configuration
@Import(OrderTestBeans.class)
class OrderTestContextConfiguration {

    @Bean
    OrderService orderService(
            OrderRepository repository,
            Clock fixedClock) {
        return new OrderService(repository, fixedClock);
    }
}
~~~

Test:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = OrderTestContextConfiguration.class)
class OrderServiceTest {
    // ...
}
~~~

This approach works with plain Spring Framework. The idea remains the same as in Spring Boot: separate test configuration and load it only into the designated context.

### 6.3. When is @Configuration still used in test sources?

In projects without Spring Boot, @Configuration is the standard way to declare beans in tests. In projects with Boot, @Configuration can still be used for test configuration if the test actively specifies that class via @ContextConfiguration or @Import and does not cause confusion with primary configuration discovery.

There is no need to add Spring Boot Test just to get the @TestConfiguration annotation if the project does not use Boot. Choose dependencies based on the project's actual foundation.

## 7. @TestConfiguration Does Not Automatically Replace Production Beans

This is a common misconception. The annotation's name does not mean every bean declared inside it will replace a bean of the same type in the application context.

Suppose the application has:

~~~java
@Configuration
class PaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new HttpPaymentGateway();
    }
}
~~~

The test adds:

~~~java
@TestConfiguration
class PaymentTestConfiguration {

    @Bean
    PaymentGateway fakePaymentGateway() {
        return new FakePaymentGateway();
    }
}
~~~

If both beans are loaded, the context may contain two beans of type PaymentGateway. When a constructor requests PaymentGateway, Spring may fail to determine a suitable bean if there is no explicit selection rule.

### 7.1. Using @Primary to prefer a test bean for injection

~~~java
@TestConfiguration(proxyBeanMethods = false)
class PaymentTestConfiguration {

    @Bean
    @Primary
    PaymentGateway fakePaymentGateway() {
        return new FakePaymentGateway();
    }
}
~~~

@Primary marks the preferred bean when Spring must pick one candidate among multiple beans matching a dependency injection point.

It does not remove the production bean from the context. If code injects using a qualifier, requests a bean by name, or retrieves all beans via a collection/map, the production bean can still appear.

### 7.2. Using @Qualifier for explicit selection

~~~java
@Bean
@Qualifier("testPaymentGateway")
PaymentGateway fakePaymentGateway() {
    return new FakePaymentGateway();
}
~~~

At the injection point:

~~~java
OrderService(
        @Qualifier("testPaymentGateway") PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

A qualifier helps select the right bean for the purpose. However, if production code is designed to always inject a bean by a specific name, adding another test bean does not replace that bean.

### 7.3. Using bean override when the goal is replacing a dependency

If you need to replace a real bean with a mock in tests, use the bean override mechanism supported by the Spring version in use, such as @MockitoBean in Spring Framework 6.2+ or the corresponding Spring Boot Test annotation in older versions.

~~~java
@SpringBootTest
class PaymentServiceTest {

    @MockitoBean
    PaymentGateway paymentGateway;

    @Autowired
    PaymentService paymentService;

    @Test
    void handlesApprovedPayment() {
        given(paymentGateway.charge(any()))
                .willReturn(PaymentResult.approved());

        // Verify business logic.
    }
}
~~~

Bean override has a different goal from adding a bean via @TestConfiguration. When you want to add a collaborator or test utility, test configuration is appropriate. When you want to replace a specific dependency, bean override usually expresses intent more accurately.

### 7.4. Do not rely on implicit bean definition overriding

Declaring two beans with the same name or expecting a later-registered bean to override an earlier one depends on bean definition overriding rules and context configuration. In many modern Spring Boot configurations, bean definition overriding is disabled by default.

Do not design tests that depend on component scan order or import order so that a test bean wins by chance. Use @Primary, @Qualifier, or the bean override API explicitly.

## 8. proxyBeanMethods and How @Bean Methods Are Declared

Both @Configuration and @TestConfiguration support configuring proxyBeanMethods.

### 8.1. Default full configuration

With the default proxyBeanMethods setting, Spring can create a subclass proxy for the configuration class so that calls between @Bean methods are routed through the container.

~~~java
@TestConfiguration
class OrderTestConfiguration {

    @Bean
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2025-07-01T00:00:00Z"),
                ZoneOffset.UTC
        );
    }

    @Bean
    OrderPolicy orderPolicy() {
        return new OrderPolicy(fixedClock());
    }
}
~~~

In full configuration, calling fixedClock() from another @Bean method is intercepted to return the container-managed bean rather than creating a new instance outside the container.

### 8.2. proxyBeanMethods = false

If beans are wired via method parameter injection, you can disable proxying:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class OrderTestConfiguration {

    @Bean
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2025-07-01T00:00:00Z"),
                ZoneOffset.UTC
        );
    }

    @Bean
    OrderPolicy orderPolicy(Clock fixedClock) {
        return new OrderPolicy(fixedClock);
    }
}
~~~

This approach is typically cleaner and more efficient for small test configurations. Spring still manages the beans, but direct calls between @Bean methods are not intercepted to fetch instances from the container.

If orderPolicy() calls fixedClock() directly under lite mode, that call can create a new Clock instance instead of obtaining the managed bean. Use method parameter injection to express dependencies clearly.

### 8.3. Choosing when to disable proxying

Use proxyBeanMethods = false when:

- Beans are independent or wired together through method parameters.
- There is no need to call one @Bean method from another @Bean method.
- You want lightweight, easy-to-read test configuration.

Keep the default mode when full configuration semantics are needed and there is a clear reason. Do not disable proxying and then continue calling @Bean methods directly as if they always return the same singleton.

## 9. Organizing Test Configuration by Scope

A project can organize test configurations into several groups:

| Scope | Suitable location | How it is loaded |
|---|---|---|
| Single test method/class | Nested @TestConfiguration | Used by Boot tests alongside primary configuration |
| Multiple tests in a package | Top-level @TestConfiguration in test sources | @Import on tests that need it |
| MVC test slice | Small test configuration | @Import alongside @WebMvcTest |
| JPA test slice | Persistence-related test configuration | @Import alongside @DataJpaTest |
| Plain Spring Framework | Top-level @Configuration in test sources | @ContextConfiguration or @Import |
| Shared production configuration | @Configuration in main sources | Component scanning or application import |

Do not create one giant test configuration containing every fake, mock, Clock, converter, and datasource for the entire repository. When every test imports the same large configuration, contexts can pull in unrelated beans and cache keys become harder to reuse.

Splitting configurations by purpose helps readers see clearly which beans a test needs and avoids accidentally bringing unnecessary infrastructure into the context.

## 10. Combining with @Import and Existing Configuration

### 10.1. Importing test configuration into a test class

~~~java
@SpringBootTest
@Import(OrderTestConfiguration.class)
class OrderIntegrationTest {
    // ...
}
~~~

This works well when the test uses the application's primary configuration and only adds a few test beans.

### 10.2. Importing multiple small configurations

~~~java
@SpringBootTest
@Import({
        FixedClockConfiguration.class,
        FakeCatalogConfiguration.class,
        TestEventPublisherConfiguration.class
})
class OrderIntegrationTest {
    // ...
}
~~~

Each configuration has a narrow responsibility. The test imports only the parts it needs.

### 10.3. Using profiles for environment-specific test configuration

@Profile can restrict a configuration by active profile:

~~~java
@Configuration
@Profile("test")
class TestProfileConfiguration {

    @Bean
    Clock testClock() {
        return Clock.systemUTC();
    }
}
~~~

Profiles and @TestConfiguration solve two different problems. @Profile controls whether configuration is activated based on the environment profile. @TestConfiguration represents additional configuration for tests and excludes it from regular component scanning.

Do not replace @TestConfiguration with @Profile("test") if the main goal is to prevent test configuration from being discovered by component scanning in unintended contexts. A profile can still be activated in an application context running outside tests if the configuration is scanned and the profile is enabled.

## 11. Common Mistakes and How to Fix Them

### Nested @Configuration hides the primary application configuration

**Symptom:** The test only sees a small group of beans or reports missing production beans after adding a nested @Configuration.

**Cause:** Spring Boot may pick the nested @Configuration as the primary configuration for the test.

**Resolution:** If you want to add beans to the application configuration, switch the nested class to @TestConfiguration. If you need a completely separate context, intentionally declare the primary configuration via @ContextConfiguration or an appropriate mechanism.

### Top-level @TestConfiguration is not loaded

**Symptom:** A bean is declared in the class, yet Spring throws NoSuchBeanDefinitionException.

**Cause:** @TestConfiguration is excluded from regular component scanning.

**Resolution:** Import the class with @Import or specify it explicitly in the test configuration. For test slices, import it into the test class using that slice.

### Two beans of the same type cause NoUniqueBeanDefinitionException

**Symptom:** Spring finds multiple beans of the same type when injecting a dependency.

**Cause:** The test configuration adds a new bean while the production bean still exists.

**Resolution:** Use @Primary or @Qualifier if you need to select one candidate; use @MockitoBean or a bean override mechanism if the goal is to replace an existing dependency.

### Expecting a test bean to automatically override a production bean

**Symptom:** Context initialization fails with a bean definition conflict, or the test still uses the production bean.

**Cause:** @TestConfiguration is not a bean override command.

**Resolution:** Clarify whether the goal is adding or replacing. Choose additional configuration, qualifiers, primary, or the corresponding bean override API.

### Test slice cannot find a test bean

**Symptom:** @WebMvcTest or @DataJpaTest reports a missing dependency even though the test configuration lives in the test source set.

**Cause:** Test slices have restricted component scan scope and top-level test configurations are not automatically imported.

**Resolution:** Use @Import or an appropriate nested @TestConfiguration. Avoid widening application-wide component scanning just to find one test bean.

### Test configuration accidentally gets loaded in another application context

**Symptom:** A test-only bean appears in an unintended context.

**Cause:** The configuration is annotated with @Configuration and package scanning traverses that class.

**Resolution:** Use @TestConfiguration for test configuration when Spring Boot Test is available, keep it in the test source set, and import it explicitly. With plain Spring Framework, control the class list in @ContextConfiguration and avoid unintentionally scanning packages containing test configurations.

### proxyBeanMethods is disabled but @Bean methods call each other

**Symptom:** Multiple instances of a dependency exist instead of the registered singleton bean.

**Cause:** Direct Java calls between @Bean methods are not intercepted by a proxy when proxyBeanMethods = false.

**Resolution:** Inject beans via @Bean method parameters or enable full configuration if calling through methods is needed.

### Adding @TestConfiguration alters the context cache

**Symptom:** More contexts are created and the test suite runs slower.

**Cause:** Imported configurations, bean overrides, or context customizers can produce different cache keys across test classes.

**Resolution:** Reuse small, stable test configurations for groups of tests with the same needs. Avoid creating unnecessarily different configurations in each test class when they do not require different beans.

## 12. Complete Example: Replacing Clock with Test Configuration

Suppose a service uses Clock to timestamp orders:

~~~java
record Order(String id, Instant createdAt) {}

class OrderService {

    private final Clock clock;

    OrderService(Clock clock) {
        this.clock = clock;
    }

    Order create(String id) {
        return new Order(id, Instant.now(clock));
    }
}
~~~

Production configuration:

~~~java
@Configuration
class TimeConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

Test configuration:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class FixedTimeTestConfiguration {

    @Bean
    @Primary
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2025-08-10T12:30:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

Test:

~~~java
@SpringBootTest
@Import(FixedTimeTestConfiguration.class)
class OrderServiceIntegrationTest {

    @Autowired
    OrderService orderService;

    @Test
    void createsOrderAtFixedInstant() {
        Order order = orderService.create("ORD-100");

        assertThat(order.createdAt())
                .isEqualTo(Instant.parse("2025-08-10T12:30:00Z"));
    }
}
~~~

In this example, the production configuration still creates the system Clock. The test configuration adds a fixed Clock and marks it @Primary so dependency injection picks it when OrderService requests a Clock. The production bean still exists in the context; the test simply prioritizes the test bean for injection by type.

If the test needs to completely replace the production Clock bean, an appropriate bean override mechanism can be used instead of adding a second bean. The choice depends on how the application is configured and the contract the test wants to verify.

## 13. Complete Example: MVC Test Slice with a Fake Service

Suppose a controller depends on OrderQueryService:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderQueryService queryService;

    OrderController(OrderQueryService queryService) {
        this.queryService = queryService;
    }

    @GetMapping("/{id}")
    OrderResponse find(@PathVariable String id) {
        return queryService.find(id);
    }
}

record OrderResponse(String id, String status) {}
~~~

Test configuration providing a fake service:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class OrderMvcTestConfiguration {

    @Bean
    @Primary
    OrderQueryService fakeOrderQueryService() {
        return id -> new OrderResponse(id, "PAID");
    }
}
~~~

Test slice:

~~~java
@WebMvcTest(OrderController.class)
@Import(OrderMvcTestConfiguration.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsOrderFromTestService() throws Exception {
        mockMvc.perform(get("/orders/ORD-100"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("ORD-100"))
                .andExpect(jsonPath("$.status").value("PAID"));
    }
}
~~~

This example assumes OrderQueryService is an interface or type that can be implemented with a lambda as shown. The configuration only adds the dependency needed for the controller test. @WebMvcTest maintains the MVC slice scope and @Import brings the fake into the context.

In another test, if you need to verify how the controller handles multiple outcomes or exceptions, you can use a stateful fake created specifically for the test or a mock bean override. Do not share a mutable singleton fake across concurrent tests without an isolation mechanism.

## 14. Annotation Selection Checklist

| Question | Suitable choice |
|---|---|
| Is this production configuration used by the application? | @Configuration |
| Is this additional configuration only for Spring Boot tests? | @TestConfiguration |
| Need to add beans to @SpringBootTest while keeping primary configuration? | @TestConfiguration + @Import or nested @TestConfiguration |
| Need to add beans to @WebMvcTest/@DataJpaTest? | @TestConfiguration + @Import |
| Project uses only Spring Framework, not Boot Test? | @Configuration + @ContextConfiguration/@Import |
| Need to replace a dependency with a Mockito mock? | @MockitoBean or corresponding bean override mechanism |
| Need to add a bean of the same type and prioritize it for injection? | @Primary or @Qualifier |
| Top-level test configuration is not found automatically? | Explicit import |
| Want test configuration excluded from regular component scanning? | @TestConfiguration in Spring Boot Test |

## 15. Practical Guidelines

1. Remember that @Configuration belongs to Spring Framework, while @TestConfiguration belongs to Spring Boot Test.
2. Use @Configuration for application bean configuration or test configuration explicitly loaded in plain Spring Framework.
3. Use @TestConfiguration to declare additional beans solely for Spring Boot tests.
4. Use a nested static @TestConfiguration when the configuration is only needed within one test class.
5. Use a top-level @TestConfiguration and @Import when multiple tests need to reuse the same configuration.
6. Do not assume a top-level @TestConfiguration is automatically discovered by component scanning.
7. With @WebMvcTest, @DataJpaTest, and other slices, explicitly import the required test configuration.
8. Do not treat @TestConfiguration as a mechanism that automatically overrides production beans.
9. Use @Primary or @Qualifier to select beans; use the bean override API when replacing dependencies.
10. Use proxyBeanMethods = false when beans are wired via method parameter injection and full configuration proxying is unnecessary.
11. Do not place test-only configuration in production packages where it could be scanned unintentionally.
12. Keep test configurations small, purposefully named, and containing only beans the test actually needs.

@Configuration is Spring Framework's general bean declaration mechanism. @TestConfiguration adds an explicit way to express test-only configuration in the Spring Boot ecosystem and prevents that class from being discovered by regular component scanning. Choosing the right annotation, importing configuration intentionally, and clearly distinguishing adding beans from replacing beans keeps test contexts well-scoped, easy to understand, and free of unintended side effects.

