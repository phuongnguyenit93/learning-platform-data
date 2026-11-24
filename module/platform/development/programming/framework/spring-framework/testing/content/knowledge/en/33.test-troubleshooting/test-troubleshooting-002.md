# Missing Beans, Duplicate Beans, or Missing Test Dependencies

## Three Commonly Confused Error Categories

When Spring creates an ApplicationContext for a test, the framework must locate the required beans, select the right bean to inject, and initialize all of their dependencies. A test can fail as soon as the context starts, even before the test method executes.

Messages such as NoSuchBeanDefinitionException, NoUniqueBeanDefinitionException, UnsatisfiedDependencyException, or BeanDefinitionOverrideException are often lumped together as Spring configuration errors. However, they describe distinct problems:

| Error category | Meaning | Common symptom |
| --- | --- | --- |
| Missing bean | No bean matches the dependency required for injection | NoSuchBeanDefinitionException |
| Duplicate bean by type | Multiple matching beans exist and Spring cannot decide which to select | NoUniqueBeanDefinitionException |
| Duplicate bean name | Two definitions register the same bean name in the context | BeanDefinitionOverrideException or definition registration error |
| Missing bean dependency | The bean was found, but one of its internal dependencies could not be created | UnsatisfiedDependencyException, usually with another root cause |
| Missing test library | A class or API needed by the test is absent from the test runtime classpath, or has an incompatible version | ClassNotFoundException, NoClassDefFoundError, NoSuchMethodError |

Identifying the right error category helps you choose the right fix. Adding a mock bean can resolve a controller dependency in an MVC slice, but it will not fix a missing library on the classpath. Adding @Primary can resolve a choice between two beans of the same type, but it does not resolve two definitions sharing the same name.

## Understanding the ApplicationContext Creation Chain

When a test uses Spring TestContext or Spring Boot test support, the framework creates an ApplicationContext from the declared configurations and customizers. This process consists of the following main steps:

1. Locate the root configuration and any specified test configurations.
2. Read component scanning, @Import, auto-configuration, profiles, and configuration conditions.
3. Register bean definitions from configuration classes, components, and factory methods.
4. Apply any bean overrides or mock beans declared for the test.
5. Instantiate singletons and resolve constructor, field, or method dependencies.
6. Finalize the context before running the test method.

Errors in the early steps are usually configuration or component scan scope issues. Errors during dependency resolution are usually missing beans or multiple matching beans. Errors while instantiating a bean can stem from deeper dependencies, misconfiguration, or the bean's own initialization code.

A test slice such as @WebMvcTest intentionally loads only part of the ApplicationContext. The absence of a service from a slice can be the intended design of the slice, rather than an application-wide component scan bug.

## Diagnosing a Missing Bean

### NoSuchBeanDefinitionException

This message means Spring requires a bean of a specific type or qualifier but cannot find a matching definition in the current context.

For example, a controller requiring a service:

~~~java
@RestController
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }
}
~~~

If the test uses @WebMvcTest(OrderController.class), Spring builds the MVC slice and registers the controller in the context. Business services are typically not created as they are in a full application context, because the slice focuses on the web layer. The result can be a failure stating OrderService could not be found.

If the goal is to test the controller's HTTP contract while isolating the service, provide a mock bean:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTests {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;
}
~~~

@MockitoBean is the bean override annotation introduced in Spring Framework 6.2 and later. In older Spring Boot versions, projects may be using @MockBean from spring-boot-test. Choose the API compatible with your project's actual Spring Framework and Spring Boot versions.

If the goal is to test the real service along with its dependencies, do not mock OrderService. Use an appropriate test configuration or an integration test with a context containing the service and its required dependencies.

### Checking Component Scanning and Configuration Packages

A bean can be missing because the root configuration class does not scan the package containing the component. Spring Boot typically looks for the main configuration class annotated with @SpringBootApplication and scans from its package down into subpackages.

Example structure:

~~~text
com.example
  Application.java
  orders
    OrderService.java
  testsupport
    TestConfiguration.java
~~~

If Application resides in a subpackage such as com.example.bootstrap while OrderService lies outside the scanned package branch, the component may not be discovered. In that case, place the root configuration class in an appropriate parent package or declare scanBasePackages intentionally.

Do not arbitrarily add broad component scanning in tests to fix every missing bean error. Broad scanning can pull in adapters, clients, or production configurations outside the scope of the test, making the context harder to control and the test more coupled.

### Checking Profiles and Configuration Conditions

A bean may only be registered when a matching profile or property is active:

~~~java
@Configuration
@Profile("integration")
class IntegrationClientConfiguration {

    @Bean
    ExternalCatalogClient externalCatalogClient() {
        return new ExternalCatalogClient();
    }
}
~~~

If the test does not activate the integration profile, the bean above will not appear. You can activate the profile in the test:

~~~java
@ActiveProfiles("integration")
@SpringBootTest
class CatalogIntegrationTests {
}
~~~

Similarly, @ConditionalOnProperty, @ConditionalOnClass, @ConditionalOnMissingBean, and auto-configuration conditions can prevent a bean from being registered. In that case, check the actual properties, classpath, and conditions. Do not create an extra bean with the same functionality before understanding why the original configuration did not activate.

### Using @Import When Explicit Configuration Is Needed

If a test needs a specific configuration class or component, @Import brings it into the context without widening global component scanning:

~~~java
@SpringBootTest
@Import(PartnerClientTestConfiguration.class)
class PartnerIntegrationTests {
}
~~~

This is appropriate when a group of tests needs an extra helper bean or specific adapter. Ensure the imported configuration does not inadvertently pull in production configuration requiring credentials or external systems absent from the test environment.

## Diagnosing Multiple Beans of the Same Type

### NoUniqueBeanDefinitionException

This error occurs when a dependency requires a single type, yet multiple beans are assignable to that type. For example, an application has two PaymentGateway implementations:

~~~java
interface PaymentGateway {
    PaymentResult charge(PaymentRequest request);
}

@Component
class CardPaymentGateway implements PaymentGateway {
    // ...
}

@Component
class BankTransferGateway implements PaymentGateway {
    // ...
}
~~~

If a service injects by interface:

~~~java
class PaymentService {

    private final PaymentGateway gateway;

    PaymentService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Spring does not have enough information to choose between CardPaymentGateway and BankTransferGateway. There are three common ways to resolve this, depending on the meaning of the dependency.

### Using @Qualifier When the Consumer Needs a Specific Implementation

Place the qualifier on the bean definition:

~~~java
@Component
@Qualifier("card")
class CardPaymentGateway implements PaymentGateway {
    // ...
}
~~~

The consumer declares its choice explicitly:

~~~java
class PaymentService {

    private final PaymentGateway gateway;

    PaymentService(@Qualifier("card") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

A qualifier is appropriate when the name or role of the implementation is part of the configuration. You can define a custom qualifier annotation instead of a string if you want better type safety.

### Using @Primary When There Is a Default Implementation

If one bean should be chosen whenever a consumer does not specify a qualifier, mark that bean as primary:

~~~java
@Component
@Primary
class CardPaymentGateway implements PaymentGateway {
    // ...
}
~~~

@Primary tells Spring to prefer this bean for by-type injection when no specific qualifier is present. It does not remove the remaining beans, and it does not fix two bean definitions sharing the same name.

Do not add @Primary just to make a test start if production actually expects selection by profile or configuration. An arbitrary primary bean can let the application run while calling the wrong implementation.

### Injecting All Implementations When Business Logic Needs Them

If a consumer needs to work with multiple gateways, declare a collection:

~~~java
class PaymentGatewayRegistry {

    private final Map<String, PaymentGateway> gateways;

    PaymentGatewayRegistry(Map<String, PaymentGateway> gateways) {
        this.gateways = gateways;
    }

    PaymentGateway get(String name) {
        return gateways.get(name);
    }
}
~~~

Spring can inject a List, Set, or Map of matching beans. For a Map, the key is typically the bean name. The consumer is responsible for selecting the implementation according to business rules and handling missing keys.

## Diagnosing Beans Registered with Duplicate Names

### BeanDefinitionOverrideException

This happens when two bean definitions share the same bean name. For example:

~~~java
@Configuration
class ProductionConfiguration {

    @Bean
    ExternalClient externalClient() {
        return new ExternalClient();
    }
}

@TestConfiguration
class TestConfiguration {

    @Bean
    ExternalClient externalClient() {
        return new StubExternalClient();
    }
}
~~~

Both factory methods default to the bean name externalClient. If both are imported into the same context and bean overriding is disallowed, Spring reports a duplicate definition name error.

Do not confuse this with two differently named beans of the same type. Two differently named beans typically lead to NoUniqueBeanDefinitionException on by-type injection; two definitions with the same name lead to a registration conflict.

### Giving Distinct Names When Both Beans Are Truly Needed

If the test needs both the real implementation and the stub, assign explicit names:

~~~java
@TestConfiguration
class TestClientConfiguration {

    @Bean("stubExternalClient")
    ExternalClient stubExternalClient() {
        return new StubExternalClient();
    }
}
~~~

Then inject using a qualifier. If the test only needs to replace the production bean, use Spring Test's bean override mechanism or an intentional test configuration instead of registering another bean with a colliding name.

### Do Not Enable Global Bean Overriding as a Default Fix

Spring Boot has a property that controls bean definition overriding. Enabling it can let a later-registered definition replace an earlier one, but the outcome depends on registration order and can hide configuration conflicts.

Only enable overriding when there is a clear reason and you have verified which definition must win. For tests, prefer @MockitoBean, @TestBean, @Import, or explicit test configurations compatible with your framework version.

## Choosing the Right Way to Provide Test Beans

There are several ways to add or replace beans in a test context. Each has a different scope and purpose.

| Approach | Purpose | When appropriate |
| --- | --- | --- |
| @MockitoBean | Replace or create a bean with a Mockito mock in the test context | Isolating dependencies in a web slice or integration test |
| @MockitoSpyBean | Wrap an existing bean with a Mockito spy | Wanting to observe calls while still using real behavior |
| @TestConfiguration + @Bean | Declare test-specific supporting implementations | Fake clients, clocks, adapters, or custom fixtures |
| @Import | Bring a specific configuration or component into the context | Adding a group of beans with clear boundaries |
| @ActiveProfiles | Enable profile-specific configuration groups | Profile-dependent beans |
| @SpringBootTest | Load the application context following Boot configuration | When broader integration verification is needed |
| @ContextConfiguration | Specify Spring TestContext configuration | Tests using a minimal context or specific Spring configuration |

### @TestConfiguration for Supporting Beans

Example providing a fixed Clock for tests:

~~~java
@TestConfiguration
class FixedTimeTestConfiguration {

    @Bean
    Clock testClock() {
        return Clock.fixed(
                Instant.parse("2026-04-15T10:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

This configuration can be imported into a test:

~~~java
@SpringBootTest
@Import(FixedTimeTestConfiguration.class)
class ReservationIntegrationTests {
}
~~~

If the context already contains another Clock bean, the test may encounter multiple beans of the same type. In that case, decide explicitly whether the test should replace the existing bean or keep both and inject by qualifier. Do not create an additional Clock expecting Spring to pick the new bean automatically.

### Bean Overrides by Spring Version

In Spring Framework 6.2 and later, @MockitoBean and @MockitoSpyBean are the bean override mechanisms provided by Spring TestContext. They allow declaring mocks or spies directly on test fields or types and are applied in the test context.

Older Spring Boot projects may be using @MockBean and @SpyBean from Spring Boot Test. In Spring Boot 3.4, those older annotations were deprecated in favor of migrating to Spring Framework's bean override APIs. Do not mix annotations from both API generations without checking version compatibility.

Example using the newer API:

~~~java
@SpringBootTest
class BillingServiceTests {

    @MockitoBean
    PaymentGateway paymentGateway;
}
~~~

If you need to mock by qualifier when multiple beans of the same type exist, declare the qualifier on the field or use the appropriate annotation attribute in the version you are using. Check the exact API available in your dependencies before copying examples from newer documentation.

## Test Slices Do Not Contain All Application Beans

A common source of confusion is expecting a test slice to have the full set of beans like @SpringBootTest.

### @WebMvcTest

@WebMvcTest focuses on the Spring MVC layer: the selected controllers, MVC infrastructure, converters, validation, and related web components. Services, repositories, and business clients are typically mocked or explicitly imported.

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTests {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;
}
~~~

If the controller injects another collaborator outside the web slice, mock or import that collaborator. Do not immediately switch to @SpringBootTest if your goal is only to test the controller's mappings, validation, and HTTP responses.

### @DataJpaTest

@DataJpaTest focuses on JPA repositories, entity mappings, and database test infrastructure. Services or web controllers are not automatically included in the context.

If a repository depends on a custom converter, auditing configuration, or custom entity listener, import the needed configuration explicitly. If a test needs to verify service orchestration alongside repositories, use a more appropriate context instead of assuming the slice loaded the services.

### @SpringBootTest

@SpringBootTest loads an application context according to Spring Boot configuration. Its scope is broader, but it still depends on component scanning, profiles, conditions, auto-configuration exclusions, and test properties.

If a bean is still missing in @SpringBootTest, check the root configuration, scanned packages, profiles, and bean creation conditions. This annotation does not guarantee that every class in the repository is registered.

### @ContextConfiguration

@ContextConfiguration lets you specify the configuration used to build the Spring TestContext. If you declare only a minimal configuration, the context only contains the beans configured or imported from it. Do not expect Spring Boot component scanning and auto-configuration if the test does not bootstrap them.

## Missing Test Dependencies on the Classpath

Not every error with the word “missing” is a missing Spring bean. If the JVM cannot find a class or method needed by the test, the problem may lie in Gradle/Maven dependencies or a version mismatch.

### Distinguishing Classpath Errors from ApplicationContext Errors

| Exception or symptom | First place to check |
| --- | --- |
| NoSuchBeanDefinitionException | Is the bean in the context with the matching type/qualifier? |
| NoUniqueBeanDefinitionException | How many beans match the type? |
| UnsatisfiedDependencyException | Read the nested cause to find the first unresolved dependency |
| BeanDefinitionOverrideException | Are there two definitions with the same bean name? |
| ClassNotFoundException | Is the class on the runtime classpath? |
| NoClassDefFoundError | Is a dependency missing at runtime or did class initialization fail? |
| NoSuchMethodError | Are modules using incompatible versions? |
| NoSuchBeanDefinitionException for a test extension | Is the test support or auto-configuration loaded? |

In Gradle, libraries needed only when compiling or running tests should usually be placed in testImplementation or testRuntimeOnly, depending on usage. Spring Boot projects typically use starter-test:

~~~groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

If tests use Testcontainers, add the corresponding modules in the test scope:

~~~groovy
dependencies {
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")
}
~~~

Versions should be managed consistently using Spring Boot dependency management or the project's version catalog. Avoid manually adding a Spring Test version that differs from the Spring Framework version managed by Boot.

### Checking the Dependency Tree and Source Set

If a class is visible in the IDE but Gradle tests cannot find it, check whether the dependency belongs to the right source set and task:

~~~powershell
./gradlew dependencies --configuration testRuntimeClasspath
~~~

For a specific module, run the task from that module or specify the corresponding project path. Check for excluded dependencies, version conflicts, and test runtime configurations. Do not add a library to implementation just to make tests compile if it is only needed in the test source set.

## Reading the Stack Trace from Outside In

Spring often wraps bean initialization errors in a general exception. The first line may simply say ApplicationContext failed to load or Error creating bean, while the actual cause sits deeper in the nested cause.

Example:

~~~text
Failed to load ApplicationContext
  UnsatisfiedDependencyException:
    Error creating bean with name 'orderController'
      UnsatisfiedDependencyException:
        Error creating bean with name 'orderService'
          NoSuchBeanDefinitionException:
            No qualifying bean of type 'PaymentGateway' available
~~~

In this chain, OrderController and OrderService are merely affected beans. The first unresolved dependency is PaymentGateway. Fix it at that point instead of adding a mock for OrderController or disabling all auto-configuration.

When there are multiple nested exceptions, identify the first meaningful deepest exception, then trace back the bean requesting that dependency. Also check the condition evaluation report if the error involves auto-configuration or Spring Boot's @ConditionalOn... annotations.

## A Practical Diagnostic Workflow

1. Read the first exception and its nested causes. Distinguish among bean definition errors, injection errors, bean initialization errors, and classpath errors.
2. Identify whether the test uses @WebMvcTest, @DataJpaTest, @SpringBootTest, or @ContextConfiguration. List the beans that scope is expected to load.
3. For a missing bean, check component scanning, @Import, profiles, conditional properties, and auto-configuration.
4. For multiple beans of the same type, check qualifiers, primary markers, and whether the consumer needs one or multiple implementations.
5. For duplicate bean names, find the @Bean methods or components sharing the same name; choose an intentional bean override or distinct names.
6. For UnsatisfiedDependencyException, trace the dependency graph to the first bean or class that cannot be created.
7. For ClassNotFoundException, NoClassDefFoundError, or NoSuchMethodError, inspect testRuntimeClasspath and version alignment.
8. Choose the fix based on the test's goal: mock out-of-scope dependencies, import test configuration, enable required profiles, or expand the test context only when truly needed.
9. Re-run the exact test class or method to verify the context error is resolved and the business assertions remain meaningful.

## Fixes That Easily Mask Root Causes

### Converting Every Test Slice to @SpringBootTest

This can make a missing bean error disappear because the context is broader, but it also starts many unrelated components, increases execution time, and couples tests to infrastructure. Keep slices when the goal is to test a single layer; use the full context only when broad integration needs verification.

### Mocking Every Dependency Without Respecting Boundaries

A mock bean helps isolate a collaborator, but if you mock the bean under test or components meant to be verified together, the test only proves the mock works. Select dependencies outside the test boundary for replacement.

### Enabling Global Bean Overriding

This can cause one definition to be overwritten based on registration order, hiding duplicate configuration. Declare test replacement beans explicitly.

### Adding Broad Component Scanning

Scanning the entire root package can pull in unnecessary adapters and integration configurations. Importing the exact component or configuration the test needs is usually much clearer.

### Adding Production Dependencies to Fix Test Classpath Errors

If a library is only used in tests, add it to testImplementation or testRuntimeOnly. Keeping test dependencies on the production runtime classpath bloats the application classpath and can introduce version conflicts.

## Conclusion on Reading Errors

Missing beans, multiple beans of the same type, duplicate bean names, and missing test libraries are problems at different layers. NoSuchBeanDefinition points to context scope or registration conditions; NoUniqueBeanDefinition points to selection among candidates; BeanDefinitionOverrideException points to name collisions; UnsatisfiedDependency requires tracing the dependency graph; and classpath errors require checking dependencies and versions.

When diagnosis starts from the root exception and the actual boundary of the test context, the fix becomes smaller and more targeted: provide mocks for out-of-scope dependencies, import required configuration, select beans via qualifier or primary, rename colliding definitions, or add dependencies in the proper test scope.
