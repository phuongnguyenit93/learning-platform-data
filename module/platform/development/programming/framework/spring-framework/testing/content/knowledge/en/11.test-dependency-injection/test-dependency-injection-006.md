# Combining Spring Parameters with Other ParameterResolvers

JUnit Jupiter allows extensions to supply arguments to test constructors and test methods via `ParameterResolver`. Spring TestContext participates in this mechanism through `SpringExtension`, enabling tests to receive beans from the `ApplicationContext`. Mockito, JUnit's built-in resolvers, and project-defined extensions can also provide parameters in the same test.

Combining multiple parameter sources makes test signatures clearly express the dependencies and data they need. Every parameter must have a single, unambiguous resolver responsible for it. If multiple resolvers claim to support the same parameter, JUnit reports an error because it cannot pick a single resolver.

## Learning Objectives

After this lesson, you will be able to:

- Explain the role of JUnit Jupiter's `ParameterResolver`.
- Use `SpringExtension` to inject beans into test method parameters.
- Combine Spring parameters with Mockito, `TestInfo`, `TestReporter`, and custom resolvers.
- Distinguish `@ParameterizedTest` arguments from extension-supplied parameters.
- Understand constructor injection for test classes.
- Recognize errors caused when multiple resolvers support the same parameter.
- Design custom resolvers with narrow conditions to avoid conflicts.
- Diagnose `ParameterResolutionException` and organize maintainable extensions.

## 1. What is ParameterResolver in JUnit Jupiter?

JUnit Jupiter lets extensions participate in test preparation and execution. An extension implementing `ParameterResolver` can supply values for parameters of a test constructor or test method.

The interface has two primary methods:

~~~java
public interface ParameterResolver extends Extension {

    boolean supportsParameter(
        ParameterContext parameterContext,
        ExtensionContext extensionContext
    ) throws ParameterResolutionException;

    Object resolveParameter(
        ParameterContext parameterContext,
        ExtensionContext extensionContext
    ) throws ParameterResolutionException;
}
~~~

`supportsParameter` answers whether the resolver is responsible for the parameter under inspection. If it returns `true`, JUnit invokes `resolveParameter` to obtain the value to pass into the test.

~~~mermaid
flowchart TD
    A["JUnit prepares test method"] --> B["Inspects each parameter"]
    B --> C["Queries ParameterResolvers"]
    C --> D{"Exactly one resolver supports?"}
    D -->|Yes| E["Calls resolveParameter"]
    E --> F["Passes value to test"]
    D -->|None| G["ParameterResolutionException"]
    D -->|Multiple resolvers| H["Competing resolvers error"]
~~~

A parameter may be supplied by Spring, Mockito, JUnit, or a custom extension. JUnit must identify a single matching resolver for every parameter resolved by an extension.

## 2. How does SpringExtension supply Spring parameters?

`SpringExtension` connects JUnit Jupiter to the Spring TestContext Framework. Beyond managing the `ApplicationContext` and test callbacks, this extension implements `ParameterResolver` to retrieve dependencies from Spring.

In a test method, Spring can supply parameters marked with appropriate annotations such as:

- `@Autowired`: instructs Spring to inject the dependency.
- `@Qualifier`: specifies the matching bean when multiple beans share the same type.
- `@Value`: retrieves a value from a property or Spring expression.

Example:

~~~java
@SpringJUnitConfig(ReportConfiguration.class)
class ReportServiceTest {

    @Test
    void generatesReport(
            @Autowired ReportService reportService) {

        Report report = reportService.generate();

        assertNotNull(report);
    }
}
~~~

`@SpringJUnitConfig` combines test context configuration with `SpringExtension`. When JUnit prepares to invoke the test method, `SpringExtension` recognizes the `@Autowired` parameter, asks Spring to resolve the dependency, and passes the bean into the method.

A qualifier can be used:

~~~java
@Test
void usesTheBusinessClock(
        @Autowired @Qualifier("businessClock") Clock clock) {

    assertNotNull(clock);
}
~~~

If a property is needed, `@Value` can be used:

~~~java
@Test
void receivesConfiguredCurrency(
        @Value("${app.currency}") String currency) {

    assertEquals("VND", currency);
}
~~~

Parameters lacking an appropriate Spring annotation are generally not claimed as dependencies by `SpringExtension`. This allows other resolvers to supply the remaining parameters.

`SpringExtension` does not turn every test method parameter into a bean lookup. Annotating parameters clearly identifies which parameters belong to Spring.

## 3. Registering SpringExtension with other extensions

You can combine Spring with other extensions using `@ExtendWith`. For example, `MockitoExtension` supports parameters annotated with `@Mock`.

~~~java
@SpringJUnitConfig(PricingConfiguration.class)
@ExtendWith(MockitoExtension.class)
class PricingTest {

    @Test
    void calculatesPrice(
            @Autowired TaxPolicy taxPolicy,
            @Mock DiscountGateway discountGateway,
            TestInfo testInfo) {

        when(discountGateway.discountFor("BOOK-1"))
            .thenReturn(BigDecimal.valueOf(10));

        PriceCalculator calculator =
            new PriceCalculator(taxPolicy, discountGateway);

        BigDecimal result = calculator.calculate("BOOK-1");

        assertEquals(BigDecimal.valueOf(90), result);
        assertTrue(testInfo.getDisplayName().contains("calculatesPrice"));
    }
}
~~~

In this example, there are three parameter sources:

| Parameter | Provider |
|---|---|
| `taxPolicy` | `SpringExtension` via `@Autowired` |
| `discountGateway` | `MockitoExtension` via `@Mock` |
| `testInfo` | Built into JUnit Jupiter |

The test retrieves the real `TaxPolicy` from Spring, receives a mock `DiscountGateway` from Mockito, and instantiates `PriceCalculator` itself to test. This is useful when you want to combine Spring configuration with a mocked collaborator in a test.

An important note: a `@Mock` parameter created by Mockito is only a mock object passed into the test method. It does not automatically replace an existing bean in the `ApplicationContext`. If `PriceCalculator` is already created by Spring and needs a mock replacing an internal dependency in the context, use the bean override mechanism appropriate for your Spring version, such as `@MockitoBean` in supported Spring Framework versions. Do not assume a mock parameter will automatically be injected into a singleton bean.

`@SpringJUnitConfig` already registers `SpringExtension` via a meta-annotation. Therefore, there is no need to add `@ExtendWith(SpringExtension.class)` again when using this composed annotation.

If you use `@ContextConfiguration` instead of `@SpringJUnitConfig`, register `SpringExtension` explicitly:

~~~java
@ExtendWith({
    SpringExtension.class,
    MockitoExtension.class
})
@ContextConfiguration(classes = PricingConfiguration.class)
class PricingTest {
}
~~~

Multiple extensions can participate in the same test class. The key is that each resolver only claims the parameters belonging to its responsibility.

## 4. Combining Spring parameters with JUnit's built-in resolvers

JUnit Jupiter includes built-in resolvers to provide metadata about the test run. Common types include:

- `TestInfo`: information about the current test or container.
- `TestReporter`: publishes report entries during test execution.
- `RepetitionInfo`: repetition info in `@RepeatedTest`.

Spring can inject beans into the same method where JUnit supplies these parameters:

~~~java
@SpringJUnitConfig(AuditConfiguration.class)
class AuditServiceTest {

    @Test
    void recordsAnEvent(
            @Autowired AuditService auditService,
            TestInfo testInfo,
            TestReporter reporter) {

        auditService.record("test-started");

        reporter.publishEntry(
            "test", testInfo.getDisplayName()
        );
    }
}
~~~

`SpringExtension` claims `auditService` because it has `@Autowired`. JUnit supplies `TestInfo` and `TestReporter` via its built-in resolvers.

For repeated tests:

~~~java
@SpringJUnitConfig(CounterConfiguration.class)
class RepeatedCounterTest {

    @RepeatedTest(3)
    void incrementsCounter(
            @Autowired CounterService counterService,
            RepetitionInfo repetitionInfo) {

        assertTrue(repetitionInfo.getCurrentRepetition() >= 1);
        assertEquals(3, repetitionInfo.getTotalRepetitions());

        counterService.increment();
    }
}
~~~

`RepetitionInfo` is only meaningful in a repeated test context. Do not declare it in a regular `@Test` and expect JUnit to supply a value.

Parameters supplied by JUnit's built-in resolvers do not need `@Autowired`. Keep Spring annotations strictly on the parameters that need to be retrieved from the container.

## 5. Combining Spring with @ParameterizedTest

`@ParameterizedTest` receives data from a source such as `@ValueSource`, `@CsvSource`, `@MethodSource`, or `@ArgumentsSource`. Beyond the arguments from the data source, JUnit allows parameters at the end of the list to be supplied by a `ParameterResolver`.

The practical rule is to place data-source-supplied parameters first, followed by extension-resolved parameters at the end.

Example using `@CsvSource` with a Spring bean:

~~~java
@SpringJUnitConfig(CalculatorConfiguration.class)
class CalculatorParameterizedTest {

    @ParameterizedTest
    @CsvSource({
        "2, 4",
        "3, 9",
        "5, 25"
    })
    void calculatesSquare(
            int input,
            int expected,
            @Autowired SquareService squareService) {

        assertEquals(expected, squareService.square(input));
    }
}
~~~

The first two parameters `input` and `expected` come from each row of `@CsvSource`. The last parameter `squareService` is injected by `SpringExtension` from the context.

If you place an `@Autowired` parameter between data source parameters, parameterized test argument mapping may fail the resolution rules. Keep the data source parameter group at the beginning and the resolver-supplied group at the end of the method parameter list.

With `@MethodSource`, the data source can return `Stream<Arguments>`:

~~~java
@SpringJUnitConfig(CalculatorConfiguration.class)
class CalculatorMethodSourceTest {

    static Stream<Arguments> squareCases() {
        return Stream.of(
            Arguments.of(2, 4),
            Arguments.of(4, 16),
            Arguments.of(6, 36)
        );
    }

    @ParameterizedTest
    @MethodSource("squareCases")
    void calculatesSquare(
            int input,
            int expected,
            @Autowired SquareService squareService) {

        assertEquals(expected, squareService.square(input));
    }
}
~~~

`MethodSource` only supplies business data for each run. The Spring bean is still supplied by `SpringExtension`.

With `@MethodSource` in the default setup, the factory method is typically `static`. If the test class uses `@TestInstance(TestInstance.Lifecycle.PER_CLASS)`, an instance factory method can be used per JUnit rules. Changing the test instance lifecycle does not change where Spring beans are provided from.

## 6. Combining constructor parameters and method parameters

JUnit can also resolve parameters of a test class constructor. Spring TestContext supports constructor injection for test classes according to the configured mode.

You can instruct Spring to automatically inject all constructor parameters using `@TestConstructor`:

~~~java
@SpringJUnitConfig(OrderConfiguration.class)
@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)
class OrderServiceSpringTest {

    private final OrderService orderService;

    OrderServiceSpringTest(OrderService orderService) {
        this.orderService = orderService;
    }

    @Test
    void createsOrder() {
        Order order = orderService.create("ORD-1");

        assertEquals("ORD-1", order.getNumber());
    }
}
~~~

`@TestConstructor(autowireMode = ALL)` tells Spring to resolve all test class constructor parameters from the `ApplicationContext`. A default mode for the test suite can be configured via `spring.test.constructor.autowire.mode` if the project needs a uniform policy.

If constructor autowiring is not enabled, use field injection or method parameter injection according to the test configuration. Do not assume Spring will automatically resolve all constructor parameters solely because the class has `@SpringJUnitConfig`.

When coordinating multiple different resolvers, the test method is usually the easiest place to separate responsibilities: Spring claims `@Autowired` parameters, Mockito claims `@Mock` parameters, and JUnit handles built-in info types. With constructor `ALL` mode, Spring is asked to handle every constructor parameter, making it unsuitable for arbitrarily mixing parameters meant for other resolvers into the same constructor.

## 7. Writing a custom ParameterResolver

A custom extension can supply objects based on a project-defined annotation. For example, many tests might need a default tenant. You can create a `@CurrentTenant` annotation and a corresponding resolver.

Annotation:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
public @interface CurrentTenant {
}
~~~

Data type:

~~~java
public record Tenant(String id) {
}
~~~

Resolver:

~~~java
import org.junit.jupiter.api.extension.ExtensionContext;
import org.junit.jupiter.api.extension.ParameterContext;
import org.junit.jupiter.api.extension.ParameterResolutionException;
import org.junit.jupiter.api.extension.ParameterResolver;

public class CurrentTenantResolver implements ParameterResolver {

    @Override
    public boolean supportsParameter(
            ParameterContext parameterContext,
            ExtensionContext extensionContext) {

        return parameterContext.isAnnotated(CurrentTenant.class)
            && parameterContext.getParameter().getType().equals(Tenant.class);
    }

    @Override
    public Object resolveParameter(
            ParameterContext parameterContext,
            ExtensionContext extensionContext) {

        return new Tenant("tenant-test");
    }
}
~~~

Registering the resolver alongside Spring:

~~~java
@SpringJUnitConfig(TenantConfiguration.class)
@ExtendWith(CurrentTenantResolver.class)
class TenantServiceTest {

    @Test
    void processesCurrentTenant(
            @CurrentTenant Tenant tenant,
            @Autowired TenantService tenantService) {

        assertEquals("tenant-test", tenant.id());
        assertTrue(tenantService.isEnabledFor(tenant));
    }
}
~~~

The resolver only claims parameters that have both the `@CurrentTenant` annotation and type `Tenant`. `SpringExtension` claims `tenantService` because it is marked with `@Autowired`. Because both resolvers have clear boundaries, they can coexist cleanly.

### Designing supportsParameter narrowly and deliberately

A common mistake is writing a resolver that checks only the type:

~~~java
return parameterContext.getParameter().getType().equals(String.class);
~~~

If Spring can also claim a `String` parameter annotated with `@Value`, or another resolver also provides a `String`, JUnit may detect multiple resolvers supporting the same parameter.

It is better to check both a dedicated annotation and the type:

~~~java
return parameterContext.isAnnotated(CurrentTenant.class)
    && parameterContext.getParameter().getType().equals(Tenant.class);
~~~

`supportsParameter` should only decide whether the resolver applies. Do not create resources, open connections, or mutate state inside this method because JUnit may invoke it multiple times during test preparation.

`resolveParameter` is where creating or retrieving the value happens. If the parameter cannot be supplied, throw `ParameterResolutionException` with a message clear enough for readers to see which annotation, type, or condition is missing.

## 8. What happens when multiple resolvers support the same parameter?

JUnit Jupiter does not use extension registration order as a resolver priority mechanism. If multiple `ParameterResolver` implementations return `true` for the same parameter, JUnit does not automatically pick the first one. The test will fail with a `ParameterResolutionException` reporting competing resolvers.

For example, a custom resolver claiming every `String`:

~~~java
@Override
public boolean supportsParameter(
        ParameterContext parameterContext,
        ExtensionContext extensionContext) {

    return parameterContext.getParameter().getType().equals(String.class);
}
~~~

If a test method has the parameter:

~~~java
@Test
void readsCurrency(
        @Value("${app.currency}") String currency) {
}
~~~

`SpringExtension` can claim the parameter because `@Value` asks Spring to resolve the value. The custom resolver also claims it because it accepts every `String`. As a result, two resolvers compete.

How to fix:

- Narrow `supportsParameter` with a dedicated annotation.
- Avoid using common types like `String`, `Integer`, or `Object` as the sole condition.
- Remove duplicate extension registrations or remove annotations that cause another resolver to match the same parameter.
- Choose a single provider for each parameter.
- If two values share the same type but have different meanings, use qualifiers or separate annotations to distinguish them.

Example fix for the resolver:

~~~java
return parameterContext.isAnnotated(CurrentTenant.class)
    && parameterContext.getParameter().getType().equals(String.class);
~~~

Then the resolver only claims `String` parameters annotated with `@CurrentTenant`. Still, a dedicated annotation should express the data's true domain meaning; if the parameter is a tenant, using the `Tenant` type is usually clearer than `String`.

## 9. Distinguishing data-source parameters from resolver parameters

In `@ParameterizedTest`, not every parameter is supplied by a `ParameterResolver`. JUnit has its own mechanism to obtain arguments from an `ArgumentsProvider` or data source.

Example:

~~~java
@ParameterizedTest
@CsvSource({
    "VND, 100",
    "USD, 10"
})
void convertsAmount(
        String currency,
        int amount,
        @Autowired ExchangeService exchangeService,
        TestInfo testInfo) {

    // currency and amount come from CsvSource.
    // exchangeService comes from Spring.
    // testInfo comes from JUnit.
}
~~~

There are three groups:

| Parameter group | Source | Example |
|---|---|---|
| Per-invocation arguments | `@CsvSource`, `@MethodSource`, `@ValueSource` | `currency`, `amount` |
| Spring parameters | `SpringExtension` | `@Autowired ExchangeService` |
| Other extension parameters | Mockito, JUnit, or custom resolver | `@Mock`, `TestInfo`, `@CurrentTenant` |

The parameterized test data source supplies arguments positionally. Parameters requiring resolvers should be placed after the data source argument group. This ordering lets JUnit clearly tell which data belongs to each invocation and which parameters need extension resolution.

## 10. Combining with @TempDir and other extensions

JUnit has built-in extensions supporting parameters such as `@TempDir` to provide a temporary directory. A test can simultaneously receive a Spring bean, a temporary directory, and `TestInfo`:

~~~java
@SpringJUnitConfig(FileServiceConfiguration.class)
class FileServiceTest {

    @Test
    void writesReport(
            @Autowired FileReportService reportService,
            @TempDir Path temporaryDirectory,
            TestInfo testInfo) throws IOException {

        Path report = temporaryDirectory.resolve("report.txt");

        reportService.write(report, "test report");

        assertTrue(Files.exists(report));
        assertTrue(Files.size(report) > 0);
    }
}
~~~

Here:

- `FileReportService` comes from Spring.
- `temporaryDirectory` is supplied by JUnit via `@TempDir` support.
- `TestInfo` comes from JUnit's built-in resolver.

Each parameter has a clear source. The test does not need to create the temporary directory manually or access `ApplicationContext` by hand.

Other extensions can also supply parameters in the same way. When adding an extension to a test class, inspect the annotations or conditions that extension checks in `supportsParameter`, and verify whether those conditions overlap with Spring or existing resolvers.

## 11. Distinguishing Spring parameter injection from manual bean lookup

Some tests retrieve beans directly via `ApplicationContext`:

~~~java
@Autowired
ApplicationContext applicationContext;

@Test
void getsServiceManually() {
    ReportService service =
        applicationContext.getBean(ReportService.class);

    assertNotNull(service);
}
~~~

This is valid, but if the test only needs one dependency, it can be injected directly as a parameter:

~~~java
@Test
void usesReportService(
        @Autowired ReportService reportService) {

    assertNotNull(reportService);
}
~~~

Parameter injection offers several benefits:

- Dependencies are expressed directly in the method signature.
- The test method only receives the beans it actually needs.
- There is no need to keep field injections for dependencies used by only one method.
- It combines cleanly with parameters from other resolvers.

However, field injection remains useful when many methods in the same class share the same bean. Choose the style that expresses dependencies most readably for the test class.

## 12. Diagnosing ParameterResolutionException

When JUnit cannot supply a parameter, the message typically includes `ParameterResolutionException`. Read the message to identify the situation.

### No resolver supports the parameter

Common causes:

- The parameter lacks the annotation required by the resolver.
- The extension has not been registered.
- The parameter's type is not supported by the resolver.
- The test uses Spring annotations, yet `SpringExtension` has not been activated.

For example, a `ReportService` parameter without `@Autowired` in a Spring test may not be recognized by `SpringExtension` as a dependency.

Fix: mark the parameter with the appropriate Spring annotation or register the resolver responsible for supplying it.

### Multiple resolvers support the parameter

Common causes:

- A custom resolver claims every parameter of a given type.
- Two extensions both claim the same annotation or type.
- A single parameter carries multiple annotations causing multiple resolvers to claim it.
- An extension is registered twice via both a meta-annotation and `@ExtendWith`.

Fix: narrow `supportsParameter`, remove duplicate registrations, and assign a single unambiguous source per parameter.

### Resolver supports it, yet resolution fails

If `supportsParameter` returns `true` but `resolveParameter` cannot produce a value, check the resolver's initialization conditions and dependencies. Error messages should clearly state the parameter type, annotation, and root cause.

Do not return `null` to hide the fact that a resolver could not create a value, unless `null` is genuinely a valid value under the parameter's contract.

### Spring fails to load the context

Sometimes an error surfaces during parameter resolution when the real cause is that the `ApplicationContext` failed to initialize. In that case, look for the root exception related to bean creation, configuration, or data source setup. Changing a `ParameterResolver` cannot fix a failing context load.

## 13. Common mistakes when combining resolvers

- **Assuming the first resolver wins:** JUnit fails if multiple resolvers support the same parameter.
- **Custom resolver accepting any String:** overly broad conditions easily conflict with `@Value` or other resolvers.
- **Forgetting to register the extension:** a custom resolver is never called unless registered with `@ExtendWith` or an equivalent mechanism.
- **Registering SpringExtension twice:** `@SpringJUnitConfig` already includes `SpringExtension`; do not declare it again.
- **Putting Spring parameters before @CsvSource arguments:** place source arguments first and extension parameters at the end of the method parameter list.
- **Thinking a @Mock parameter replaces a Spring bean:** a mock created by Mockito does not automatically become a bean in the context.
- **Using @TestConstructor(ALL) and expecting another resolver to handle part of the constructor:** this mode asks Spring to resolve all constructor parameters.
- **Using TestInfo outside a JUnit-supported context:** parameters must appear in a lifecycle where the built-in resolver can supply them.
- **Doing work inside supportsParameter:** this method should only check eligibility without creating side effects.
- **Swallowing errors in resolveParameter:** throw `ParameterResolutionException` with a clear cause to make diagnosis easy.

## 14. Workflow for designing tests with multiple parameter sources

When a test method needs parameters from Spring and other extensions, follow this sequence:

1. List the values the test needs and the source producing each value.
2. Mark Spring dependencies with `@Autowired`, `@Qualifier`, or `@Value` as appropriate.
3. Mark mocks or special data with the annotations supported by their respective extensions.
4. Register the required extensions; use `@SpringJUnitConfig` if the test needs Spring TestContext.
5. Place parameters supplied by `@ParameterizedTest` sources at the start of the parameter list.
6. Place parameters supplied by `ParameterResolver` at the end of the parameter list.
7. Check `supportsParameter` in custom resolvers to ensure conditions are narrow enough.
8. Run the tests and address any `ParameterResolutionException` based on which resolvers are claiming the parameter.
9. If a mock needs to replace a bean inside the context, use an appropriate bean override mechanism rather than merely accepting a mock parameter.
10. Keep each test method accepting only the parameters genuinely needed for the behavior under test.

## Conclusion

`SpringExtension` enables Spring TestContext to supply beans to test method and constructor parameters following autowiring rules. JUnit Jupiter also provides built-in `ParameterResolver`s, while Mockito and custom extensions can provide mocks or specialized data. These sources can coexist in the same test class as long as every parameter has one clear resolver responsible for it.

When combining with `@ParameterizedTest`, place arguments from data sources first and extension-resolved parameters at the end. For custom resolvers, constrain `supportsParameter` with specific annotations and types. If multiple resolvers claim the same parameter, JUnit reports a conflict error; clarify the provider instead of relying on extension registration order.

