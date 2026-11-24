# @Autowired for Test Fields, Setters, and Constructors

In Spring Test, a test class can also receive beans from the `ApplicationContext` via dependency injection. The `@Autowired` annotation can be placed on a field, setter method, or constructor so that Spring supplies dependencies to the test instance.

These three approaches serve the same purpose but differ in injection timing, how dependencies are expressed, and the ability to preserve immutability. Field injection is concise, setter injection allows assigning a dependency through a method, and constructor injection makes required dependencies explicit as soon as the test instance is created.

For injection to work, the test must be connected to the Spring TestContext Framework, typically via `@SpringJUnitConfig` or the combination of `@ExtendWith(SpringExtension.class)` and `@ContextConfiguration`. Simply adding `@Autowired` to a plain JUnit class does not automatically create an `ApplicationContext`.

## How does Spring inject into a test instance?

The test class is created and its lifecycle is managed by JUnit. The Spring TestContext Framework prepares the test instance by retrieving beans from the `ApplicationContext` and injecting them into the marked injection points. The test class does not need to be declared as a bean with `@Component`; Spring Test handles the test object separately during test execution.

With JUnit Jupiter, `SpringExtension` connects JUnit's lifecycle with `TestContextManager`. The main participating components are as follows:

~~~mermaid
sequenceDiagram
    participant J as JUnit Jupiter
    participant S as SpringExtension
    participant T as TestContextManager
    participant C as ApplicationContext
    J->>S: Create test instance
    S->>T: Prepare TestContext
    T->>C: Retrieve beans to inject
    C-->>T: Return dependencies
    T-->>J: Test instance prepared
    J->>J: Run @BeforeEach and @Test
~~~

There are two points in time to distinguish:

- **Constructor injection:** `SpringExtension` participates in resolving constructor parameters while JUnit creates the test instance. Dependencies are passed into the constructor so the object is created fully initialized.
- **Field and setter injection:** the test instance is created first, and then Spring Test performs dependency injection during the test instance preparation step, before `@BeforeEach` methods and test methods run.

In the Spring TestContext Framework, `DependencyInjectionTestExecutionListener` performs injection of fields and methods annotated with `@Autowired` into the test instance. `SpringExtension` supports constructor injection for JUnit Jupiter through the `ParameterResolver` mechanism.

## Requirements for @Autowired to work in tests

The most common declaration is `@SpringJUnitConfig`, an annotation that combines JUnit Jupiter integration with `ApplicationContext` configuration:

~~~java
@SpringJUnitConfig(TestConfig.class)
class CustomerServiceTest {
    // Dependencies are retrieved from the ApplicationContext of TestConfig.
}
~~~

This can also be written explicitly with two annotations:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfig.class)
class CustomerServiceTest {
    // ...
}
~~~

`SpringExtension` connects JUnit to the Spring TestContext Framework. `@ContextConfiguration` specifies the configuration source used to create the `ApplicationContext`. Without the appropriate extension or integration mechanism, JUnit does not know how to resolve Spring beans for the test.

Minimal configuration example:

~~~java
@Configuration
class TestConfig {

    @Bean
    CustomerRepository customerRepository() {
        return new InMemoryCustomerRepository();
    }

    @Bean
    CustomerService customerService(CustomerRepository repository) {
        return new CustomerService(repository);
    }
}
~~~

The following examples assume `TestConfig` provides the required beans. In a real application, the configuration may be a configuration class, an XML resource, a Spring Boot configuration, or an imported test configuration.

## Field injection: injecting directly into a field

Field injection places `@Autowired` on a field of the test class. Spring assigns the corresponding bean to the field during the test instance preparation step.

~~~java
@SpringJUnitConfig(TestConfig.class)
class CustomerServiceFieldTest {

    @Autowired
    private CustomerService customerService;

    @Test
    void findsCustomer() {
        var customer = customerService.findById("C-100");

        assertThat(customer).isPresent();
    }
}
~~~

This approach is easy to read and concise, especially for tests with only a few dependencies. The field can be `private`; Spring uses reflection to perform the injection.

Key points to remember:

- The field must be an instance field; do not use `static` for dependencies that need to be injected per test instance.
- The dependency is only ready after Spring prepares the test instance; do not access the field inside the constructor.
- `@BeforeEach` methods and test methods can use the dependency after injection completes.
- If there are multiple beans of the same type, you must specify the bean using `@Qualifier` or configure an appropriate `@Primary` bean.

Example when there are two implementations:

~~~java
@Autowired
@Qualifier("cachedCustomerService")
private CustomerService customerService;
~~~

Field injection is suitable when conciseness is preferred and the test does not need to express dependencies through a constructor. However, the list of dependencies is scattered throughout the class, fields may remain uninitialized right after the constructor, and it is difficult to maintain immutability with `final`.

## Setter injection: injecting through a method

Setter injection places `@Autowired` on an instance method. Spring invokes that method and passes the bean into its parameter.

~~~java
@SpringJUnitConfig(TestConfig.class)
class CustomerServiceSetterTest {

    private CustomerService customerService;

    @Autowired
    void setCustomerService(CustomerService customerService) {
        this.customerService = customerService;
    }

    @Test
    void findsCustomer() {
        var customer = customerService.findById("C-100");

        assertThat(customer).isPresent();
    }
}
~~~

Setter injection makes the dependency reception point explicit as a method. It can be useful when assignment logic or state normalization is needed when receiving the dependency, although most setter injections in tests only need a simple assignment.

You can use `@Qualifier` on a setter parameter when there are multiple beans of the same type:

~~~java
@Autowired
void setCustomerService(
        @Qualifier("cachedCustomerService")
        CustomerService customerService) {
    this.customerService = customerService;
}
~~~

Some notes:

- The injection method typically accepts one or more parameters that Spring can resolve.
- Do not call the setter manually before Spring prepares the test instance if the method requires a bean from the context.
- If the setter contains additional logic, keep it small and easy to understand so that test preparation does not introduce extra side effects.
- A setter allows the dependency to be changed after the object is created; therefore, the test must clearly manage state if the setter is also called in other methods.

Setter injection is appropriate when a dependency is optional or when an explicit setup method is needed. For required test dependencies, constructor injection usually expresses that requirement better.

## Constructor injection: receiving dependencies when creating the test instance

Constructor injection passes dependencies into the constructor. With JUnit Jupiter, Spring can resolve constructor parameters through `SpringExtension`.

An explicit approach is to use `@TestConstructor` to ask Spring to automatically autowire all constructor parameters:

~~~java
@SpringJUnitConfig(TestConfig.class)
@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)
class CustomerServiceConstructorTest {

    private final CustomerService customerService;

    CustomerServiceConstructorTest(CustomerService customerService) {
        this.customerService = customerService;
    }

    @Test
    void findsCustomer() {
        var customer = customerService.findById("C-100");

        assertThat(customer).isPresent();
    }
}
~~~

In `ALL` mode, Spring resolves all constructor parameters from the `ApplicationContext`. The test instance is only created once the required dependencies have been supplied. Using `final` fields prevents dependencies from being modified after the constructor completes.

You can place `@Autowired` directly on a constructor to request autowiring for that constructor:

~~~java
@SpringJUnitConfig(TestConfig.class)
class CustomerServiceAutowiredConstructorTest {

    private final CustomerService customerService;

    @Autowired
    CustomerServiceAutowiredConstructorTest(CustomerService customerService) {
        this.customerService = customerService;
    }
}
~~~

`@TestConstructor` is useful when you want to explicitly configure constructor injection mode for a test class or a group of tests via a meta-annotation. The `autowireMode` attribute has the following options:

| Mode | Meaning |
|---|---|
| `ALL` | Automatically autowires all constructor parameters |
| `ANNOTATED` | Only autowires parameters or constructors marked appropriately, such as `@Autowired`, `@Qualifier`, or `@Value` |

If you want to set a default mode for the entire test suite, you can configure the `spring.test.constructor.autowire.mode` property, for example in `junit-platform.properties`:

~~~properties
spring.test.constructor.autowire.mode=all
~~~

When the default configuration is `all`, test class constructors can receive dependencies from Spring without repeating `@TestConstructor` on each class. This configuration should be clearly documented in the project because it affects how JUnit creates test instances.

Constructor injection is suitable when dependencies are required and you want to express them clearly right in the constructor signature. It also lets tests use `final` fields and reduces the chance of accidentally using an uninjected dependency.

## Comparing the three injection approaches

| Criterion | Field | Setter | Constructor |
|---|---|---|---|
| Injection point | Field | Method | Constructor parameter |
| Timing | After instance creation, during test preparation | After instance creation, during test preparation | During instance creation |
| Expressing required dependencies | Less explicit | Fairly clear via setter | Clear via constructor signature |
| Can use `final` fields | No | No with post-construction assignment | Yes |
| Suitable for optional dependencies | Possible, but needs explicit configuration | Yes | Possible, but the constructor needs appropriate rules |
| Code structure | Concise | Has a setup method | Explicit, more boilerplate declarations |

No single injection approach fits every test. For tests with few dependencies where conciseness is desired, field injection is often easy to use. For optional dependencies or when a dedicated setup point is needed, setter injection can be suitable. For required dependencies, constructor injection helps the test express the full conditions needed to create an instance.

## Lifecycle order and when dependencies can be used

With field and setter injection, the general order of JUnit Jupiter and Spring Test is:

1. JUnit creates the test instance via the constructor.
2. Spring Test prepares the test instance and performs field/setter injection.
3. JUnit invokes `@BeforeEach` methods.
4. JUnit runs the test method.
5. JUnit invokes `@AfterEach` methods.

With constructor injection, dependencies are resolved in the first step, while creating the test instance. Subsequent preparation steps still proceed as normal.

Example:

~~~java
@SpringJUnitConfig(TestConfig.class)
class LifecycleInjectionTest {

    private final CustomerService constructorService;

    @Autowired
    private CustomerRepository fieldRepository;

    LifecycleInjectionTest(CustomerService constructorService) {
        this.constructorService = constructorService;
    }

    @BeforeEach
    void setUp() {
        // Both constructor dependency and field dependency are ready here.
        assertThat(constructorService).isNotNull();
        assertThat(fieldRepository).isNotNull();
    }

    @Test
    void executesWithInjectedDependencies() {
        // ...
    }
}
~~~

To make this example explicitly use constructor injection by default, you can add `@Autowired` to the constructor or declare `@TestConstructor(autowireMode = ALL)`. Fields are injected by Spring after the constructor finishes and before `@BeforeEach`.

Do not access an injected field inside the constructor: at that moment Spring has not yet run the field injection step. If the constructor needs a dependency, receive it via a constructor parameter.

With JUnit Jupiter's default `PER_METHOD` lifecycle, each test method gets its own test instance. Spring prepares and injects that instance. If `@TestInstance(TestInstance.Lifecycle.PER_CLASS)` is used, one instance is shared across multiple test methods; field and setter injection are performed when the instance is prepared, so you should not mutate dependencies or keep shared mutable state across test methods.

## Combining @Autowired with qualifiers and values

The injection mechanism in tests supports annotations that specify the bean or value to receive:

- `@Qualifier` selects a specific bean when multiple beans share the same type.
- `@Value` receives a property or expression resolved by Spring.
- `@Primary` on a configuration bean marks the preferred choice when resolving by type.

Example of a field receiving a property:

~~~java
@SpringJUnitConfig(TestConfig.class)
class EndpointConfigurationTest {

    @Value("${service.base-url}")
    private String baseUrl;

    @Test
    void usesConfiguredEndpoint() {
        assertThat(baseUrl).startsWith("http");
    }
}
~~~

Example of a constructor receiving a qualified bean:

~~~java
@SpringJUnitConfig(TestConfig.class)
@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)
class RepositorySelectionTest {

    private final CustomerRepository repository;

    RepositorySelectionTest(
            @Qualifier("jdbcCustomerRepository")
            CustomerRepository repository) {
        this.repository = repository;
    }
}
~~~

If there are multiple beans of the same type without a matching qualifier or primary bean, Spring may report an error indicating that a unique bean could not be resolved. This is a dependency resolution failure during test context or test instance preparation; check bean definitions and qualifiers before modifying assertions.

## Constructor injection and test method parameters

Constructor injection for a test class is different from Spring resolving parameters for individual test methods.

JUnit Jupiter has a `ParameterResolver` mechanism. `SpringExtension` can supply dependencies to constructors and test/lifecycle methods according to Spring's parameter support rules. For example, a test method can receive a bean through an annotated parameter:

~~~java
@Test
void findsCustomer(@Autowired CustomerService customerService) {
    assertThat(customerService.findById("C-100")).isPresent();
}
~~~

Passing a dependency via a method parameter is useful when only a single test method needs a bean. It does not turn the bean into a field of the test class and does not change how other test methods receive dependencies.

Do not confuse parameter resolution with field/setter injection performed by `DependencyInjectionTestExecutionListener`. Constructor and method parameters are handled by `SpringExtension` through JUnit Jupiter's parameter extension mechanism; fields and setters are handled in the dependency injection step of the TestContext Framework.

When a test method has multiple extensions that both want to resolve a parameter, make sure the resolvers do not conflict. For regular Spring dependencies, marking them with `@Autowired` makes the resolution intent clear.

## JUnit 4 and JUnit Jupiter

Constructor injection for test classes is tied to the test engine's instance creation mechanism. JUnit Jupiter has `ParameterResolver`, so `SpringExtension` can supply constructor parameters. Traditional JUnit 4 typically requires test classes to have a no-argument constructor and lacks an equivalent `ParameterResolver` mechanism; therefore, field or setter injection is commonly used with `SpringRunner`.

If a project migrates from JUnit 4 to JUnit Jupiter, it can gradually adopt constructor injection for tests that need to express required dependencies. Be sure to use the right extension and annotations for the JUnit version being run, and do not mix JUnit 4's `@RunWith(SpringRunner.class)` with JUnit Jupiter's `@ExtendWith(SpringExtension.class)` in the same test class.

## Common mistakes

**Forgetting to register SpringExtension.** `@Autowired` does not work on its own in plain JUnit. Use `@SpringJUnitConfig` or register `SpringExtension` and configure the context.

**Reading a field before Spring injects it.** Field injection occurs after the constructor. Do not access that field inside the constructor; use a constructor parameter if you need it immediately when the instance is created.

**Constructor has parameters without autowiring configured.** Check `@Autowired`, `@TestConstructor`, or the `spring.test.constructor.autowire.mode` property. JUnit must have `SpringExtension` to resolve dependencies.

**Multiple beans of the same type.** Use `@Qualifier` or `@Primary`, and check the active profiles.

**Using field injection and assuming the field is immutable.** An injected field can be reassigned in a test. If a dependency is required and should remain stable, constructor injection with `final` fields is clearer.

**Putting business logic in setter injection.** Setters are called when Spring prepares the test instance. Keep this method focused on receiving the dependency; scenario-specific fixtures and setup should go into the appropriate lifecycle or test method.

**Using constructor injection while the constructor does too much.** A test constructor should receive and store dependencies. Creating data, calling services, or mutating system state should take place in setup/test methods to keep the lifecycle easy to follow.

**Sharing a test instance and mutable state.** With `PER_CLASS`, multiple test methods share the same instance. Reset test data in `@BeforeEach` and avoid mutating injected dependencies.

## Choosing an injection approach for a test class

Start from the role of the dependency:

- Required dependencies for most behaviors in the class: prefer constructor injection, especially when using JUnit Jupiter.
- Simple dependencies where the test class needs minimal boilerplate: field injection is a concise choice.
- Dependencies needed only in some cases or requiring a dedicated setup method: consider setter injection.
- A bean needed by only one test method: you can use a method parameter resolved by `SpringExtension`.
- Multiple beans of the same type: specify using a qualifier or primary.
- Need consistent constructor injection configuration across a group of tests: use `@TestConstructor` or the JUnit Platform default property.

Whichever approach you choose, ensure Spring Test creates the appropriate `ApplicationContext` and injects dependencies before the test uses them. Field and setter injection occur during test instance preparation; constructor injection occurs during instance creation via `SpringExtension`. Understanding this difference helps avoid null errors, clarifies the lifecycle, and properly expresses the dependencies a test needs.
