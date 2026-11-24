# Method Parameter Injection with SpringExtension

JUnit Jupiter allows a test method or lifecycle method to declare parameters. Instead of retrieving dependencies from injected fields, a test can receive the required beans directly in the method's parameter list. **SpringExtension** resolves those annotated parameters so that Spring supplies the beans from the `ApplicationContext`.

This style is useful when a test only needs one or two dependencies, when a lifecycle method needs a repository to prepare data, or when a parameterized test needs to combine JUnit-supplied data with a Spring-supplied service. It also lets readers immediately see which components each method depends on.

To use it, the test must integrate with the Spring TestContext Framework, typically via **@SpringJUnitConfig** or the combination of **@ExtendWith(SpringExtension.class)** and **@ContextConfiguration**. Parameters to be obtained from Spring are annotated with **@Autowired**; when multiple beans of the same type exist, **@Qualifier** can also be used to select the right bean.

## 1. How does SpringExtension participate in parameter resolution?

JUnit Jupiter provides the **ParameterResolver** mechanism. An extension implementing this interface tells JUnit which parameter types it supports and supplies the corresponding values when the test is invoked.

**SpringExtension** implements `ParameterResolver` and connects this mechanism to the Spring TestContext Framework. When `SpringExtension` identifies an autowirable parameter, it retrieves the dependency from the test's `ApplicationContext`.

Simple example:

~~~java
@Configuration
class GreetingTestConfig {

    @Bean
    GreetingService greetingService() {
        return new GreetingService("Xin chào");
    }
}
~~~

~~~java
@SpringJUnitConfig(GreetingTestConfig.class)
class GreetingServiceTest {

    @Test
    void returnsConfiguredGreeting(
            @Autowired GreetingService greetingService) {

        assertEquals("Xin chào", greetingService.greet());
    }
}
~~~

When the test runs:

1. JUnit Jupiter discovers the test class and the extension registered by **@SpringJUnitConfig**.
2. Spring TestContext creates or reuses the `ApplicationContext` according to the configuration.
3. `SpringExtension` participates in the test method invocation process.
4. For parameters annotated with **@Autowired**, `SpringExtension` resolves the matching bean from the context.
5. JUnit invokes the test method with the supplied value.

In the example, the test method receives `GreetingService` directly. There is no need to declare an **@Autowired** field in the test class.

**@SpringJUnitConfig** combines **SpringExtension** and **@ContextConfiguration**. If you do not use this composed annotation, you can declare them explicitly:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = GreetingTestConfig.class)
class GreetingServiceTest {
}
~~~

Both approaches integrate Spring TestContext with JUnit Jupiter and load the specified configuration.

## 2. Annotating parameters with @Autowired

For test method parameters, the clearest approach is to place **@Autowired** directly on the parameter that Spring should resolve:

~~~java
@Test
void findsOrder(
        @Autowired OrderService orderService,
        @Autowired OrderRepository orderRepository) {

    Order order = orderService.findById("order-17");

    assertTrue(orderRepository.existsById(order.id()));
}
~~~

Spring looks up the bean by the parameter type and applies standard autowiring rules. If there is only one matching bean, that dependency is passed into the method.

You can mix Spring parameters with ordinary local values if the method constructs them itself:

~~~java
@Test
void createsOrder(@Autowired OrderService orderService) {
    String customerId = "customer-test-7";

    Order order = orderService.create(customerId);

    assertEquals(customerId, order.customerId());
}
~~~

Method parameters do not have to be Spring beans in every case. Spring only resolves parameters that are annotated or recognized as autowirable according to Spring TestContext rules. Simple domain values such as strings, numbers, or expected values can usually be declared directly inside the test or supplied by a JUnit parameterized test.

Do not expect Spring to synthesize arbitrary values for every unannotated parameter. If a parameter is not supported by `SpringExtension` or another JUnit extension, JUnit will report a parameter resolution error.

## 3. Injecting parameters into lifecycle methods

In addition to **@Test**, `SpringExtension` can supply dependencies to JUnit Jupiter lifecycle methods, such as:

- **@BeforeEach**: runs before each test method.
- **@AfterEach**: runs after each test method.
- **@BeforeAll**: runs once before all test methods in the class.
- **@AfterAll**: runs once after all test methods in the class.

This is useful when preparing or cleaning up data requires a Spring bean.

For example, a repository is injected directly into **@BeforeEach**:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderRepositoryTest {

    @BeforeEach
    void prepareData(@Autowired OrderRepository repository) {
        repository.deleteAll();
        repository.save(new Order("order-17", "customer-7"));
    }

    @Test
    void findsPreparedOrder(@Autowired OrderRepository repository) {
        Optional<Order> order = repository.findById("order-17");

        assertTrue(order.isPresent());
        assertEquals("customer-7", order.get().customerId());
    }
}
~~~

Each test method can receive the repository in its own signature. The data preparation method also declares its own dependency, so readers know exactly which components it needs.

### Injecting parameters into @AfterEach

If a test needs to clean up data after each method:

~~~java
@AfterEach
void cleanUp(@Autowired OrderRepository repository) {
    repository.deleteAll();
}
~~~

Only use this cleanup style when the repository and cleanup operation match the test's transaction semantics. If data was committed in another transaction or has side effects outside the database, a separate cleanup strategy is needed.

### Injecting parameters into @BeforeAll and @AfterAll

By default, JUnit Jupiter requires **@BeforeAll** and **@AfterAll** to be `static`. `SpringExtension` can participate in resolving parameters for these lifecycle methods:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderSuiteTest {

    @BeforeAll
    static void verifyTestInfrastructure(
            @Autowired OrderRepository repository) {
        assertNotNull(repository);
    }

    @Test
    void testOne() {
        // Test body
    }

    @AfterAll
    static void reportCompletion(
            @Autowired ApplicationContext context) {
        assertNotNull(context);
    }
}
~~~

If you want **@BeforeAll** and **@AfterAll** to be instance methods, you can use:

~~~java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
~~~

With the `PER_CLASS` lifecycle, JUnit uses a single test instance for the entire class and allows these lifecycle methods to be non-static. Parameter injection is still handled by `SpringExtension` according to the Spring TestContext mechanism.

Do not use **@BeforeAll** to mutate shared data if test methods run in parallel or depend on the mutable state of singleton beans. Design independent data and clearly define resource lifecycles.

## 4. Injecting dependencies when multiple beans share the same type

An `ApplicationContext` may contain multiple beans of the same type. For example, an application might have two `Clock` beans: one for business logic and one for recording system audit timestamps.

If you only declare a parameter of type `Clock`, Spring may not know which bean to pick. Use **@Qualifier**:

~~~java
@Configuration
class ClockTestConfig {

    @Bean
    @Qualifier("businessClock")
    Clock businessClock() {
        return Clock.fixed(
                Instant.parse("2026-08-10T09:00:00Z"),
                ZoneOffset.UTC
        );
    }

    @Bean
    @Qualifier("auditClock")
    Clock auditClock() {
        return Clock.fixed(
                Instant.parse("2026-08-10T10:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

The test selects a specific bean:

~~~java
@SpringJUnitConfig(ClockTestConfig.class)
class ClockInjectionTest {

    @Test
    void receivesBusinessClock(
            @Autowired @Qualifier("businessClock") Clock clock) {

        assertEquals(
                Instant.parse("2026-08-10T09:00:00Z"),
                clock.instant()
        );
    }
}
~~~

**@Qualifier** narrows bean selection according to the declared qualifier. Spring still applies the container's dependency resolution rules, including type, qualifier, and primary when applicable.

If a bean is marked **@Primary**, Spring can choose that bean when multiple candidates share the same type and no specific qualifier is given. However, in tests that need to verify a specialized bean, **@Qualifier** usually makes the intent clearer.

Do not rely on renaming a Java parameter assuming its name is always a stable way to select a bean. Declare an explicit qualifier when multiple beans share the same type.

## 5. Combining Spring parameters with @ParameterizedTest

A useful case is when a test needs multiple input data sets provided by JUnit while also needing a service created in the Spring context.

JUnit Jupiter supports **@ParameterizedTest** with data sources such as **@ValueSource**, **@CsvSource**, **@MethodSource**, and **@ArgumentsSource**. `SpringExtension` can additionally supply dependency parameters annotated with **@Autowired**.

Example:

~~~java
@Configuration
class DiscountTestConfig {

    @Bean
    DiscountService discountService() {
        return new DiscountService();
    }
}
~~~

~~~java
@SpringJUnitConfig(DiscountTestConfig.class)
class DiscountServiceTest {

    @ParameterizedTest
    @CsvSource({
        "100, 10",
        "200, 20",
        "350, 35"
    })
    void calculatesTenPercentDiscount(
            int subtotal,
            int expectedDiscount,
            @Autowired DiscountService discountService) {

        int actual = discountService.calculateDiscount(subtotal);

        assertEquals(expectedDiscount, actual);
    }
}
~~~

JUnit extracts **subtotal** and **expectedDiscount** from each row of **@CsvSource**. `SpringExtension` supplies `DiscountService` for the parameter annotated with **@Autowired**.

With parameterized tests, parameters supplied by the argument source must appear before parameters supplied by `ParameterResolver`. Therefore, place Spring dependencies at the end of the parameter list:

~~~java
void test(
        String valueFromSource,
        int numberFromSource,
        @Autowired SomeService service)
~~~

If you place an extension-resolved parameter before argument source parameters, JUnit may report an error because it cannot map arguments in the expected order.

### Combining @MethodSource and Spring beans

JUnit's data source can be a method returning a stream or collection. The source method and dependency parameters are two separate mechanisms:

~~~java
@ParameterizedTest
@MethodSource("validOrderCases")
void acceptsValidOrder(
        String orderId,
        int quantity,
        @Autowired OrderValidator validator) {

    assertTrue(validator.isValid(orderId, quantity));
}

static Stream<Arguments> validOrderCases() {
    return Stream.of(
            Arguments.of("order-17", 1),
            Arguments.of("order-18", 3),
            Arguments.of("order-19", 5)
    );
}
~~~

In the example, **validOrderCases** creates test data following JUnit's rules. `OrderValidator` is resolved separately by Spring. There is no need to put Spring beans into **@MethodSource** just to pass dependencies to the test method.

If the data source needs to depend on `ApplicationContext` state, consider a different test design or use an explicit data creation mechanism. A method source is static by default and does not automatically receive beans from Spring like a test method does.

## 6. Combining built-in JUnit parameters with Spring dependencies

JUnit Jupiter provides parameters supplied by built-in extensions, such as:

- **TestInfo**: information about the current test.
- **TestReporter**: writes report entries for the test.
- **RepetitionInfo**: repetition information in **@RepeatedTest**.

`SpringExtension` can participate alongside them in resolving parameters in the same method:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderRepeatedTest {

    @RepeatedTest(3)
    void checksServiceOnEachInvocation(
            RepetitionInfo repetitionInfo,
            @Autowired OrderService orderService) {

        assertTrue(repetitionInfo.getCurrentRepetition() >= 1);
        assertNotNull(orderService);
    }
}
~~~

`RepetitionInfo` is supplied by JUnit for repeated tests; `OrderService` is supplied by Spring. Each resolver should only claim responsibility for the parameters it supports.

If multiple extensions both claim to support the same parameter, JUnit may report an error due to multiple matching resolvers. Use clear annotations and parameter types to avoid conflicts.

## 7. How do parameter injection and field injection differ?

Both approaches retrieve beans from the `ApplicationContext`, but they express dependencies differently.

### Field injection

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderFieldInjectionTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsOrder() {
        assertNotNull(orderService);
    }
}
~~~

Field injection is suitable when multiple test methods in a class share the same dependency. However, each method's dependencies do not appear in its method signature.

### Method parameter injection

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderMethodInjectionTest {

    @Test
    void createsOrder(@Autowired OrderService orderService) {
        assertNotNull(orderService);
    }

    @Test
    void queriesOrder(@Autowired OrderRepository repository) {
        assertNotNull(repository);
    }
}
~~~

Method parameter injection expresses dependencies right where they are used. It is useful when each test needs a different set of dependencies or when a lifecycle method needs its own bean.

### Comparison

| Criterion | Field injection | Method parameter injection |
|---|---|---|
| Declaration | Test class field | Method parameter |
| Scope of dependency visibility | Shared across the class | Explicit per method |
| Best suited for | Multiple methods using the same bean | Different dependencies per method |
| Lifecycle method support | Field is injected into the test instance | Can receive beans via parameters |
| Combining with JUnit data | Uses a separate field | Can combine source parameters and dependencies |
| Reuse | Convenient for shared dependencies | Good when you want methods to self-document needs |

There is no mandatory rule forcing all tests to use one style. Choose the approach that makes dependencies easy to see and tests easy to read. You can combine both styles in the same test class when each serves a clear purpose, but avoid declaring the same dependency in multiple places unnecessarily.

## 8. Difference from test class constructor injection

`SpringExtension` also supports constructor injection for test classes, but constructor selection has its own rules.

Example:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)
class OrderConstructorInjectionTest {

    private final OrderService orderService;

    OrderConstructorInjectionTest(OrderService orderService) {
        this.orderService = orderService;
    }

    @Test
    void usesInjectedService() {
        assertNotNull(orderService);
    }
}
~~~

**@TestConstructor** controls how Spring autowires test class constructor parameters. A default mode can be configured via the **spring.test.constructor.autowire.mode** system property depending on the project's Spring TestContext version and configuration.

Method parameter injection is a separate mechanism. For test methods or lifecycle methods, you can directly annotate the dependency with **@Autowired**:

~~~java
@Test
void usesInjectedService(@Autowired OrderService orderService) {
    assertNotNull(orderService);
}
~~~

Therefore, there is no need to enable constructor autowire mode just to use **@Autowired** on test method parameters.

## 9. Distinguishing Spring parameters from regular parameters

Not every test method parameter comes from Spring. A method can receive data from multiple sources:

| Source | Example | Mechanism |
|---|---|---|
| Spring `ApplicationContext` | `OrderService`, `Repository`, `Clock` | `SpringExtension` and `@Autowired` |
| JUnit argument source | CSV values, `MethodSource`, `ValueSource` | `@ParameterizedTest` |
| Built-in JUnit extension | `TestInfo`, `TestReporter`, `RepetitionInfo` | JUnit's `ParameterResolver` |
| Values created by the test | Strings, numbers, local objects | Declared in the method or helper |

Each parameter must have a clear resolution source. For example, in a **@ParameterizedTest**, CSV values are supplied by JUnit while the service is supplied by Spring. There is no need to register CSV values as Spring beans.

If a parameter is not supported by any resolver, JUnit will be unable to invoke the method and typically throws **ParameterResolutionException**. If multiple resolvers match the same parameter, JUnit may report an error due to multiple matching resolvers.

## 10. What is the lifecycle of injected beans?

Method parameter injection retrieves beans from the `ApplicationContext` managed by Spring TestContext. It does not automatically create a fresh bean copy for every test method invocation.

With singleton beans (the default), multiple test methods using the same context can receive the same instance. This means:

- Mutable state on singletons can persist between tests.
- Tests should not depend on execution order.
- Test data needs to be reset or isolated.
- The context cache can reuse beans across test classes with compatible configurations.

For example, if a test method receives a singleton fake repository and inserts data into it, a subsequent test method may see that stale data. You can clean up data in **@BeforeEach** or **@AfterEach**, use appropriate transactions, or configure beans with an appropriate scope.

Passing a dependency through a method parameter does not change the bean's scope. Spring still applies the lifecycle and scope configured in the container.

## 11. Common mistakes with parameter injection

### Missing SpringExtension

If a test only uses **@Test** without integrating Spring TestContext, Spring does not participate in dependency resolution. Use **@SpringJUnitConfig** or declare **@ExtendWith(SpringExtension.class)** with a context configuration.

### Forgetting @Autowired on the parameter

If a parameter is not supported by `SpringExtension` or another resolver, JUnit throws **ParameterResolutionException**. Annotate parameters that Spring should resolve with **@Autowired**.

### No matching bean

If the `ApplicationContext` has no bean matching the required type or qualifier, Spring cannot supply the parameter. Register the bean using **@Bean**, **@Import**, appropriate component scanning, or test configuration.

### Multiple beans of the same type

If there are multiple candidates without a clear selection, Spring may fail due to ambiguity. Use **@Qualifier** or configure **@Primary** when a sensible default choice exists.

### Wrong parameter order in parameterized tests

Parameters from argument sources must precede parameters resolved by a `ParameterResolver`. Place Spring dependencies at the end of the **@ParameterizedTest** parameter list.

### Treating JUnit data as a Spring bean

A value from **@CsvSource** or **@MethodSource** is provided by JUnit. Spring does not need to—and should not—register each of those values as beans just so the test method can receive them.

### Using mutable beans without resetting state

Singleton beans can be reused across multiple runs. Clean up data or design stateless dependencies where appropriate.

### Confusing method parameter injection with constructor autowiring

**@TestConstructor** controls the test class constructor. It is not a prerequisite for test method parameters already annotated with **@Autowired**.

### Adding parameters without a clear source

Every parameter should have a clear resolution source: a Spring bean, a JUnit argument source, or a built-in resolver. An arbitrary parameter with no provider will prevent JUnit from invoking the method.

## 12. Diagnosing ParameterResolutionException

When JUnit reports an error stating it cannot resolve a parameter, read the method info and parameter position in the exception. Then identify the source from which the parameter is expected to be resolved:

| Expected parameter | Resolution source | What to check |
|---|---|---|
| Service or repository | `SpringExtension` | Has the context been loaded and the bean registered? |
| Specific bean among candidates | `SpringExtension` | Is there a matching qualifier or primary? |
| CSV value | JUnit argument source | Are column count, data types, and parameter order correct? |
| `TestInfo` or `RepetitionInfo` | Built-in JUnit extension | Is the method of the right test/lifecycle kind? |

Quick checklist:

1. Does the test class have **@SpringJUnitConfig** or `SpringExtension` and a context configuration?
2. Does the Spring parameter have **@Autowired** or an appropriate qualifier?
3. Does the context contain a bean of the right type?
4. Are there multiple beans of the same type needing a qualifier?
5. For parameterized tests, do source parameters precede resolver parameters?
6. Is another extension also claiming the same parameter and causing a conflict?
7. Does each parameter have a single clear provider?

Do not try to fix errors by adding **@Autowired** to every parameter. First determine whether the parameter belongs to Spring or JUnit and choose the appropriate resolver.

## 13. Comprehensive example: service, lifecycle method, and parameterized test

The following example combines a Spring bean, a lifecycle parameter, and data from JUnit:

~~~java
@Configuration
class PriceTestConfig {

    @Bean
    PriceService priceService() {
        return new PriceService();
    }

    @Bean
    PriceRepository priceRepository() {
        return new InMemoryPriceRepository();
    }
}
~~~

~~~java
@SpringJUnitConfig(PriceTestConfig.class)
class PriceServiceTest {

    @BeforeEach
    void reset(@Autowired PriceRepository repository) {
        repository.deleteAll();
    }

    @ParameterizedTest
    @CsvSource({
        "100, 110",
        "200, 220",
        "350, 385"
    })
    void addsTenPercentTax(
            int netPrice,
            int expectedGrossPrice,
            @Autowired PriceService priceService) {

        assertEquals(
                expectedGrossPrice,
                priceService.grossPrice(netPrice)
        );
    }
}
~~~

In each invocation:

- JUnit extracts **netPrice** and **expectedGrossPrice** from the CSV row.
- `SpringExtension` supplies `PriceService` for the parameter annotated with **@Autowired**.
- **@BeforeEach** receives `PriceRepository` from Spring and prepares the state before each invocation.
- The test verifies the service result against the expected value declared in the data.

The example assumes `PriceService` calculates 10% tax using rounding rules matching the chosen integer values. In a real project, monetary models should use an appropriate numeric type such as `BigDecimal`, and tests should explicitly reflect scale/rounding rules.

## 14. When should method parameter injection be used?

This approach is suitable when:

- A test method only needs a few beans.
- Different tests in the class need different dependencies.
- A lifecycle method needs a repository or service to prepare, inspect, or clean up data.
- A parameterized test needs to combine JUnit-provided data with Spring beans.
- You want dependencies to be explicitly visible in the method signature.
- You need to inject a qualified bean into a specific method.

Field injection can still be appropriate when many test methods share the same dependencies. Test class constructor injection is suitable when you want to declare shared dependencies at the class level and explicitly configure the autowire mode.

Keep method signatures easy to read. If a test method requires too many beans, it may be a sign that the test covers too many responsibilities or needs a clearer fixture/helper. There is no need to put every dependency from the context into the signature just because Spring can supply them.

## 15. Checklist for using SpringExtension parameter injection

Before finalizing a test class, verify:

- The test integrates **SpringExtension** via **@SpringJUnitConfig** or equivalent configuration.
- The `ApplicationContext` contains the beans required by the test.
- Spring parameters are marked with **@Autowired** or appropriate injection metadata.
- Parameters with multiple candidate beans use **@Qualifier** or a suitable bean selection mechanism.
- Lifecycle methods receive the right dependencies and do not leak state to other tests.
- With **@ParameterizedTest**, parameters from the data source precede resolver-supplied parameters.
- JUnit parameters such as `TestInfo` and `RepetitionInfo` are resolved by the appropriate extension.
- The test does not confuse method parameter injection with constructor autowiring.
- Singleton beans and the context cache are accounted for when preparing data.
- Each parameter has a clear resolution source.

**SpringExtension** allows JUnit Jupiter to receive dependencies from the `ApplicationContext` directly in the parameters of test methods and lifecycle methods. By combining **@SpringJUnitConfig**, **@Autowired**, **@Qualifier**, and JUnit argument sources, tests can clearly express what each method needs while preserving the bean management mechanism of the Spring TestContext Framework.

