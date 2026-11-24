# Referencing Beans to Compute Controlled Configuration Values in SpEL

Spring Expression Language (SpEL) can reference a Spring-managed bean using the @beanName syntax, then read a property or call a method to produce a configuration value. This approach is useful when a value needs to be computed from multiple configured sources, such as environment-based timeouts, profile-based connection limits, or batch sizes based on expected load.

To keep configuration controllable, the referenced bean should have a small API, a clear name, and computation methods with well-defined input/output types. Methods should be pure, perform validation, and avoid performing I/O or mutating system state. Expressions should only wire trusted values together; do not let arbitrary input decide which bean name or method is called.

## 1. Objectives and prerequisites

After this lesson, you can:

- Reference a bean using the @beanName syntax in SpEL.
- Call a method on a bean to compute a constructor or property value.
- Use bean references in @Value, XML bean definitions, and Java configuration.
- Distinguish injecting a bean directly via ref/constructor injection from calling a method through an expression.
- Design a calculator bean with a narrow API that is deterministic and easy to test.
- Control parameter types, return types, null handling, defaults, and business limits.
- Understand when an expression is evaluated in the bean lifecycle.
- Avoid dependency cycles and side effects during bean initialization.
- Test configuration values inside an ApplicationContext.
- Restrict expression sources and bean access at runtime.

You should know the Spring IoC container, bean names, dependency injection, @Value, SpelExpressionParser, and how to pass variables in an EvaluationContext.

## 2. Bean reference syntax

SpEL uses the @ symbol to retrieve a bean by name:

~~~text
@configValueCalculator
~~~

Properties can be read:

~~~text
@deploymentDefaults.baseTimeoutMillis
~~~

Or methods can be called:

~~~text
@configValueCalculator.calculateTimeout(5000, 2)
~~~

In the expression, @configValueCalculator is resolved by BeanResolver into an object managed by the Spring container. SpEL then uses its property or method resolution mechanism to read the property or invoke the method.

At integration points such as @Value and Spring-managed bean definitions, the container configures the expression context to access beans. If you create a StandardEvaluationContext manually in Java, you need to configure an appropriate BeanResolver, such as BeanFactoryResolver.

The bean name must match a registered bean name or alias. Use stable, meaningful names and do not construct bean names dynamically from request data.

## 3. Example: a calculator bean for computing timeout

Suppose the application has base configuration values:

~~~java
@Component("deploymentDefaults")
public class DeploymentDefaults {

    public long getBaseTimeoutMillis() {
        return 5_000L;
    }

    public BigDecimal getTimeoutMultiplier() {
        return new BigDecimal("1.5");
    }
}
~~~

Create a dedicated bean for computing values:

~~~java
@Component("configValueCalculator")
public class ConfigValueCalculator {

    public long calculateTimeout(
            long baseTimeoutMillis,
            BigDecimal multiplier) {

        if (baseTimeoutMillis <= 0) {
            throw new IllegalArgumentException(
                "baseTimeoutMillis must be positive");
        }

        if (multiplier == null
                || multiplier.compareTo(BigDecimal.ZERO) <= 0) {
            throw new IllegalArgumentException(
                "multiplier must be positive");
        }

        BigDecimal calculated =
            BigDecimal.valueOf(baseTimeoutMillis)
                .multiply(multiplier);

        return calculated.longValueExact();
    }
}
~~~

The target bean can use the result:

~~~java
@Component
public class HttpClientSettings {

    private final long timeoutMillis;

    public HttpClientSettings(
            @Value("#{ @configValueCalculator.calculateTimeout(" +
                   "@deploymentDefaults.baseTimeoutMillis, " +
                   "@deploymentDefaults.timeoutMultiplier) }")
            long timeoutMillis) {
        this.timeoutMillis = timeoutMillis;
    }

    public long getTimeoutMillis() {
        return timeoutMillis;
    }
}
~~~

With the example data, the result is 7500 milliseconds.

Evaluation flow:

1. Spring creates an expression context for the injection point.
2. BeanResolver looks up configValueCalculator and deploymentDefaults.
3. SpEL reads the two properties from deploymentDefaults.
4. SpEL calls calculateTimeout with the resolved arguments.
5. The method returns a long.
6. Spring injects the result into HttpClientSettings's constructor.

The calculator does not need to know which bean will consume the result. It simply receives typed values, performs the calculation, and returns the result.

## 4. Designing a small-scoped calculator bean

A bean referenced from an expression should have a simple API. Instead of exposing an entire business service, create a component dedicated to computing configuration values.

A good calculator typically has these characteristics:

- A bean name that expresses its purpose, such as configValueCalculator or batchSizingPolicy.
- Method names that describe the result, such as calculateTimeout or resolveBatchSize.
- Concrete parameter types, avoiding unnecessary Object or Map types.
- A clear return type matching the target property/constructor.
- Deterministic methods: the same valid inputs produce the same output.
- Validation performed right at the method boundary.
- No calls to databases, HTTP, file system, or message brokers.
- No mutation of bean state or application state.
- Does not return a broad-privilege object just so the expression can chain further method calls.

If multiple calculations are needed, split them into small methods by purpose. Do not turn the calculator into an all-in-one service capable of performing arbitrary operations.

## 5. Using bean methods in @Value

@Value supports SpEL on fields, setters, and constructor parameters of Spring-managed beans.

### 5.1. Constructor injection

~~~java
@Component
public class BatchSettings {

    private final int batchSize;

    public BatchSettings(
            @Value("#{ @batchSizingPolicy.resolveBatchSize(" +
                   "@deploymentDefaults.expectedRecordCount) }")
            int batchSize) {
        this.batchSize = batchSize;
    }

    public int getBatchSize() {
        return batchSize;
    }
}
~~~

Constructor injection ensures the object is created with required values from the start. If the expression cannot be resolved or the method throws an exception, bean creation fails fast.

### 5.2. Field injection

~~~java
@Component
public class RetrySettings {

    @Value("#{ @configValueCalculator.calculateRetryLimit(3, 2) }")
    private int retryLimit;

    public int getRetryLimit() {
        return retryLimit;
    }
}
~~~

Field injection can be concise, but constructor injection usually expresses dependencies more clearly and makes testing the object easier.

### 5.3. Setter injection

~~~java
@Component
public class MessageSettings {

    private String welcomeMessage;

    @Value("#{ @messageFactory.defaultWelcomeMessage }")
    public void setWelcomeMessage(String welcomeMessage) {
        this.welcomeMessage = welcomeMessage;
    }
}
~~~

Use a setter when the property can genuinely be configured after object creation or when a framework requires a setter. For required and immutable values, prefer constructors.

## 6. Using bean references in XML bean definitions

XML can call another bean's method inside an expression:

~~~xml
<bean id="clientSettings" class="com.example.ClientSettings">
    <property name="timeoutMillis"
              value="#{@configValueCalculator.calculateTimeout(
                  @deploymentDefaults.baseTimeoutMillis,
                  @deploymentDefaults.timeoutMultiplier)}" />
</bean>
~~~

The expression returns the value used to assign the timeoutMillis property.

If you only need to inject the calculator bean itself as a dependency of an object, use ref directly:

~~~xml
<property name="calculator" ref="configValueCalculator" />
~~~

Distinguish the two needs:

- ref passes the bean object itself into the constructor/property.
- value with @beanName calls a method or reads a property and then passes the result.

Do not use SpEL merely to replace a simple bean reference. Declaring direct dependencies is clearer and helps Spring track the bean graph.

## 7. Using bean references in Java configuration

With Java configuration, @Value can be used on parameters of @Bean methods:

~~~java
@Configuration
public class ClientConfiguration {

    @Bean
    public ClientSettings clientSettings(
            @Value("#{ @configValueCalculator.calculateTimeout(" +
                   "@deploymentDefaults.baseTimeoutMillis, 2) }")
            long timeoutMillis) {

        return new ClientSettings(timeoutMillis);
    }
}
~~~

An alternative is injecting the calculator directly and computing the value in Java:

~~~java
@Configuration
public class ClientConfiguration {

    @Bean
    public ClientSettings clientSettings(
            ConfigValueCalculator calculator,
            DeploymentDefaults defaults) {

        long timeout = calculator.calculateTimeout(
            defaults.getBaseTimeoutMillis(),
            defaults.getTimeoutMultiplier()
        );

        return new ClientSettings(timeout);
    }
}
~~~

The second approach is usually easier to refactor and verify with the compiler. SpEL fits when configuration needs a short expression; if the logic starts having multiple branches or multiple dependencies, typed Java configuration is usually clearer.

## 8. Bean references and property placeholders

Placeholders and SpEL solve two different needs:

- Property placeholders retrieve configuration values from property sources.
- SpEL evaluates expressions, and can reference beans and call methods.

For example, a placeholder provides the base value:

~~~properties
app.client.base-timeout-millis=5000
~~~

You can inject that value into a defaults bean, then use the calculator to compute:

~~~java
@Component
public class DeploymentDefaults {

    private final long baseTimeoutMillis;

    public DeploymentDefaults(
            @Value("$" + "{app.client.base-timeout-millis:5000}")
            long baseTimeoutMillis) {
        this.baseTimeoutMillis = baseTimeoutMillis;
    }

    public long getBaseTimeoutMillis() {
        return baseTimeoutMillis;
    }
}
~~~

SpEL:

~~~text
#{ @configValueCalculator.calculateTimeout(
    @deploymentDefaults.baseTimeoutMillis, 2) }
~~~

Keep property placeholders for retrieving raw configuration and use SpEL for small calculations. There is no need to wrap a simple placeholder in an expression if no transformation needs to be performed.

## 9. Controlling input and output types

The expression passes arguments into the method using the runtime types of the source values. SpEL can use a TypeConverter to convert if the method signature and conversion service allow it.

To avoid unpredictable results:

- Use properties with clear types such as long, int, BigDecimal, or Duration.
- Avoid passing numeric strings if Java can parse and validate them beforehand.
- Avoid overloading multiple methods with the same name and similar parameter types.
- Return the exact type that the target constructor/property needs.
- Do not rely on conversion to determine rounding or units.
- Check for overflow and value range limits inside the calculator.
- For currency, explicitly define currency, scale, and rounding.
- For time, explicitly define milliseconds/seconds units or use Duration.

For example, if a method returns long while the target property is Integer, conversion can fail or lose representability when the value exceeds the limit. It is better for the output type to match the consumer's contract.

## 10. Handling null and default values

A bean method may receive null from a source property or return null. For required configuration, it is usually better to fail fast rather than silently produce an unclear default value.

Example using Elvis if null means choosing a default:

~~~text
#{ @deploymentDefaults.optionalMultiplier ?: 1 }
~~~

Or handle defaults inside the calculator:

~~~java
public long calculateTimeout(
        Long baseTimeoutMillis,
        BigDecimal multiplier) {

    if (baseTimeoutMillis == null) {
        throw new IllegalArgumentException(
            "baseTimeoutMillis is required");
    }

    BigDecimal effectiveMultiplier =
        multiplier == null
            ? BigDecimal.ONE
            : multiplier;

    // Validate range and calculate.
}
~~~

Choose one place responsible for defaults so rules are not duplicated between the expression and the Java method.

Do not use defaults for secrets, required endpoints, or security values if missing configuration should stop application startup. Misconfiguration should be caught early with a clear message.

## 11. When expressions are evaluated

In @Value and bean definitions, Spring evaluates expressions when processing injection points or resolving bean definition values during bean creation.

For singleton beans, values are normally resolved when the singleton is created. If a configuration value changes later, injected field or constructor values do not automatically update just because a property source changed.

For prototype beans, instance creation happens multiple times, so the expression may be re-evaluated on each instance creation, depending on the specific integration point and scope.

Do not treat @Value as a self-refreshing dynamic configuration mechanism. If the application needs configuration changes at runtime, use a dedicated refresh/configuration mechanism, a provider queried at usage time, or redesign the component lifecycle.

Also distinguish the creation time of the calculator bean from the invocation time of its method. The method is called when the expression is evaluated; the bean is resolved according to the container's lifecycle and scope rules.

## 12. Avoiding dependency cycles when calling bean methods

An expression can create an indirect dependency that bean definitions do not make as obvious as regular constructor injection.

For example:

- ClientSettings needs a result from configValueCalculator.
- ConfigValueCalculator in turn injects ClientSettings.
- When Spring creates ClientSettings, the expression requests the calculator.
- The calculator needs ClientSettings, which has not finished initializing.

This is a dependency cycle and can prevent the ApplicationContext from starting up.

Better design:

- The calculator only depends on base configuration values or a small interface.
- The defaults-providing bean does not depend on consumers needing the result.
- Consumers receive the computed result without being referenced back by the calculator.
- Do not call methods on a bean that is still initializing if the method depends on incomplete state.
- Use constructor dependency injection to make the bean graph explicit whenever possible.

If complex computation logic is needed, computing it inside a @Bean factory method after dependencies are injected is usually easier to follow than nested expressions.

## 13. Keeping the calculator pure and avoiding side effects

A method called in an expression may run while Spring is creating beans. If the method sends HTTP requests, reads a database, writes files, or mutates state, application startup can trigger hard-to-control actions.

A suitable method:

~~~java
public int resolveBatchSize(int expectedRecords, int maxBatchSize) {
    if (expectedRecords < 0 || maxBatchSize <= 0) {
        throw new IllegalArgumentException("Invalid batch limits");
    }

    return Math.min(expectedRecords, maxBatchSize);
}
~~~

This method only computes from inputs and returns a result.

Avoid methods like:

~~~java
public int calculateAndPersistSettings() {
    // Read database, write configuration, or call external services.
}
~~~

If I/O is needed to fetch configuration data, perform it at the configuration loading layer or service orchestration layer with a clear lifecycle. Then pass the typed results into the pure calculator.

## 14. Restricting allowed beans and expressions

Bean references in SpEL are a capability. If an expression comes from an untrusted source and the context can access many beans, it can invoke methods beyond the goal of computing configuration.

Principles:

- Only reference dedicated, clearly named beans.
- Do not expose ApplicationContext or BeanFactory to untrusted expressions.
- Do not let clients submit bean names or method names themselves.
- Do not evaluate arbitrary expressions with a broad context.
- Restrict exposed methods using small facades and appropriate resolvers when needed.
- Do not expose repositories, process runners, file services, or administrative services.
- Only use template/configuration expressions from approved sources.
- Review expression changes alongside bean API changes.
- Version configuration if expressions are stored outside source code.

Fixed bean names in expressions help reviewers know exactly which dependency is used. Dynamic bean names taken from requests make the permission scope hard to determine and should not be used for regular configuration.

## 15. Testing the calculator independently

Because the calculator is a Java bean with a clear API, test its methods directly before testing SpEL integration.

For example:

~~~java
class ConfigValueCalculatorTest {

    private final ConfigValueCalculator calculator =
        new ConfigValueCalculator();

    @Test
    void calculatesTimeoutUsingMultiplier() {
        long result = calculator.calculateTimeout(
            5_000L,
            new BigDecimal("1.5")
        );

        assertThat(result).isEqualTo(7_500L);
    }

    @Test
    void rejectsNonPositiveBaseTimeout() {
        assertThatThrownBy(() ->
            calculator.calculateTimeout(
                0L,
                BigDecimal.ONE
            )
        ).isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

Calculator tests should cover:

- Normal values.
- Minimum and maximum supported values.
- Null if the input type allows null.
- Invalid negative numbers or zero.
- Overflow and rounding.
- Out-of-bounds multiplier values.
- Results in the right unit.

Unit tests confirm Java logic independently of the Spring container and SpEL.

## 16. Testing expression integration in ApplicationContext

After unit tests, verify whether Spring resolves the bean name, invokes the method, and injects the right result.

Integration test example:

~~~java
class ClientSettingsContextTest {

    @Test
    void injectsCalculatedTimeoutFromBeanReference() {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(TestConfig.class)) {

            HttpClientSettings settings =
                context.getBean(HttpClientSettings.class);

            assertThat(settings.getTimeoutMillis())
                .isEqualTo(7_500L);
        }
    }
}
~~~

TestConfig needs to register deploymentDefaults, configValueCalculator, and HttpClientSettings. Use a small configuration containing only the necessary beans so the test does not depend on databases or external services.

Integration cases to test:

- Bean name is correct and bean exists.
- Expression calls the right method and passes the right arguments.
- Result value has the right type for the property/constructor.
- Bean method throwing an exception causes startup to fail as expected.
- Incorrect bean name is caught early.
- Dependency cycles are caught in context tests.
- Different profile configurations produce appropriate results.
- No unexpected I/O or side effects occur during context startup.

## 17. Diagnosing common errors

| Symptom | Common cause | Resolution |
|---|---|---|
| Cannot find @beanName | Wrong bean name or expression context has no BeanResolver | Check bean name and ApplicationContext |
| Bean exists but method cannot be called | Wrong method name, signature, or resolver cannot resolve it | Check public method, parameters, and input types |
| Method receives wrong value | Source property or conversion has wrong type | Check runtime type and TypeConverter |
| Constructor/property does not accept result | Incompatible return type | Return the right type or configure explicit conversion |
| ApplicationContext fails to start | Calculator throws exception or invalid expression | Inspect cause chain and test calculator separately |
| Bean has circular reference | Calculator depends back on consumer | Separate calculator from consumer and clarify dependency graph |
| Value does not update when property changes | @Value already resolved during bean creation | Use appropriate refresh/provider mechanism |
| Startup triggers unexpected I/O | Calculator method has side effects | Move I/O to configuration loading/service orchestration |
| Configuration can invoke unintended bean | Context exposes too many beans or untrusted expression | Narrow bean access and expression sources |
| Wrong value for profile | Defaults or profile properties not resolved as expected | Check active profiles and configuration sources |

When debugging, check in order: expression source, bean name, bean lifecycle, method signature, runtime arguments, return type, conversion, and dependency graph.

## 18. Practice exercises

1. Create a DeploymentDefaults bean providing base timeout and multiplier.
2. Create ConfigValueCalculator with a pure method computing timeout.
3. Use @Value with @configValueCalculator.calculateTimeout(...) to inject a constructor parameter.
4. Create an XML bean definition calling the same method via a value expression.
5. Write an equivalent Java @Bean factory method and compare clarity.
6. Add validation for negative timeout, null multiplier, and overflow.
7. Create a calculator method returning Duration instead of long and inject it into a Duration-typed property.
8. Create a calculator bean depending back on the consumer to observe a dependency cycle, then refactor it.
9. Write unit tests for the calculator and integration tests for ApplicationContext.
10. Try changing profile/configuration properties and confirm when values are resolved.
11. Verify the calculator does not perform database/network/file I/O.
12. Review expressions to ensure only approved beans are referenced.

## 19. Checklist before referencing beans to compute configuration

- [ ] Is the bean name stable and clear in purpose?
- [ ] Does the method have a small API with concrete input/output types?
- [ ] Is the method deterministic and free of side effects?
- [ ] Are parameters validated and do they have clear units?
- [ ] Does the result match the target constructor/property type?
- [ ] Are nulls and defaults handled according to business rules?
- [ ] Could ref or direct constructor injection be used instead of an expression?
- [ ] Is the expression too long or does it have too many layers of bean references?
- [ ] Does the bean graph avoid dependency cycles?
- [ ] Have you identified when the expression is evaluated?
- [ ] Is it understood that @Value does not auto-refresh when a property source changes?
- [ ] Do the expression and referenced beans come from trusted sources?
- [ ] Does the context expose only the necessary bean scope?
- [ ] Have both the calculator unit tests and ApplicationContext integration tests been written?

## 20. Conclusion

SpEL can reference beans using @beanName to read properties or call methods and use the result as configuration values. A safe design exposes a dedicated calculator bean with clearly typed, deterministic, validated, side-effect-free methods. Use @Value or XML value expressions when calculations are short; use ref/constructor injection for direct dependencies and Java configuration when logic requires multiple steps. Control lifecycle, conversion, nulls, dependency cycles, and expression sources, then test both the calculator and ApplicationContext creation.