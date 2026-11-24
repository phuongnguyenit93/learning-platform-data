# Circular Dependencies When Expressions Reference Other Beans

Spring Expression Language (SpEL) allows an expression to reference a Spring bean using the **@beanName** syntax. This capability is useful when bean configuration needs to retrieve a value or call a method from another bean. However, if the expression is evaluated while Spring is creating a bean, that reference can trigger the initialization of another bean and create a circular dependency.

Circular dependencies are often harder to detect when dependencies are hidden inside SpEL strings. Looking at a class's constructor or field injection, one might not see which bean depends on which bean. Only when the expression is evaluated does Spring look up the bean and potentially encounter a bean that is currently in creation.

Key principle: **do not use bean references in SpEL to create circular dependencies or hide dependencies between beans**. Declare dependencies explicitly, extract shared parts, or defer the lookup until the appropriate runtime point when truly necessary.

## 1. Bean References in SpEL

### 1.1. The @beanName Syntax

SpEL uses the @ symbol to reference a bean by name:

~~~java
@currencyRules.defaultCurrency
@pricingService.calculate(order)
~~~

The expression requires an EvaluationContext with a BeanResolver. In a Spring context, BeanFactoryResolver can resolve bean names through BeanFactory or ApplicationContext.

Example in configuration:

~~~java
@Value("#{currencyRules.defaultCurrency}")
private String currency;
~~~

Spring evaluates the expression and retrieves the defaultCurrency property from the currencyRules bean to assign to the currency field.

### 1.2. A Bean Reference Is More Than Just Reading a Value

When the resolver processes @currencyRules, it must look up the corresponding bean. If the bean has not been created yet, the lookup can cause Spring to start initializing that bean.

Therefore, the expression:

~~~java
@Value("#{currencyRules.defaultCurrency}")
private String currency;
~~~

can create a dependency relationship during initialization:

1. Spring is creating the bean containing the currency field.
2. Spring evaluates the @Value expression.
3. BeanResolver looks up currencyRules.
4. If currencyRules has not been created yet, Spring starts creating this bean.
5. If creating currencyRules in turn needs the original bean, a circular dependency arises.

This is why a short expression can affect initialization order and the state of the entire ApplicationContext.

### 1.3. Evaluation Timing Matters Greatly

SpEL expressions can be parsed and evaluated at different times:

- During bean definition processing or bean creation, such as expressions in XML or @Value annotations.
- While a bean is having its properties populated or dependencies injected.
- When the application manually parses and evaluates an Expression at runtime.
- When a method invokes expression evaluation logic in a business flow.

An expression evaluated after ApplicationContext has finished initializing may not cause an initialization cycle at startup. But if an expression is evaluated in a constructor, field initializer, @PostConstruct, or during bean creation, it can still trigger a circular initialization chain.

Do not look only at syntax; determine accurately at which stage the expression is evaluated.

## 2. How Circular Dependencies Form

### 2.1. Example of Two Beans Depending on Each Other via SpEL

Suppose there are two beans:

~~~java
@Component
public class PricingPolicy {

    @Value("#{currencyRules.defaultCurrency}")
    private String currency;

    public String getCurrency() {
        return currency;
    }
}
~~~

~~~java
@Component
public class CurrencyRules {

    @Value("#{pricingPolicy.currency}")
    private String defaultCurrency;

    public String getDefaultCurrency() {
        return defaultCurrency;
    }
}
~~~

Dependency relationship:

~~~text
PricingPolicy -> CurrencyRules
CurrencyRules -> PricingPolicy
~~~

Creating PricingPolicy requires reading currencyRules.defaultCurrency. Creating CurrencyRules in turn requires reading pricingPolicy.currency. Spring starts creating one bean, evaluates the expression to retrieve the other bean, and the other bean then needs the first bean. Depending on timing and configuration, the process may end with a bean-currently-in-creation error.

This example only illustrates the structure of a circular dependency. Two beans like this should not be used in a real application.

### 2.2. Direct Cycles and Hidden Cycles

Direct circular dependencies are usually easy to spot:

~~~java
@Component
public class ServiceA {

    public ServiceA(ServiceB serviceB) {
    }
}
~~~

~~~java
@Component
public class ServiceB {

    public ServiceB(ServiceA serviceA) {
    }
}
~~~

Hidden circular dependencies can reside inside expressions:

~~~java
@Value("#{serviceB.someValue}")
private String value;
~~~

The class may not declare ServiceB in its constructor or fields, yet SpEL still requires Spring to look up ServiceB when evaluating.

Hidden dependencies are harder to detect because:

- They do not appear explicitly in constructor signatures.
- Tools that inspect dependency graphs may not capture relationships arising from expression strings.
- Bean initialization depends on evaluation timing.
- Changing a configuration expression can introduce a new cycle without editing the bean's Java code.
- The error may only appear under a specific profile or environment configuration.

Treat every bean reference in an expression evaluated at startup as a dependency that needs to be considered in the design.

### 2.3. Circular Dependencies Across Multiple Beans

Cycles do not have to involve just two beans:

~~~text
OrderService
    -> PricingPolicy
    -> CurrencyRules
    -> ApplicationSettings
    -> OrderService
~~~

One bean may reference a second bean using SpEL; the second bean injects a third bean; the third bean uses @Value to reference a fourth bean; and finally the fourth bean needs the first bean.

When investigating, trace the entire chain of beans being created rather than looking only at the first bean shown in the exception.

## 3. Why Circular Dependencies Cause Errors

### 3.1. Bean Currently in Creation

Spring manages the bean lifecycle and tracks singletons currently being created. If a bean requires itself directly or indirectly before creation completes, the container can detect the bean-in-creation state and throw an error.

A common exception is:

~~~text
BeanCurrentlyInCreationException
~~~

This exception may be wrapped in BeanCreationException or another ApplicationContext startup error. Inspect the cause chain to determine which bean requested which bean at the time the error occurred.

### 3.2. Constructor Cycles

Circular dependencies through constructors usually cannot be resolved by creating an incomplete instance:

~~~java
@Component
public class ServiceA {

    public ServiceA(ServiceB serviceB) {
    }
}
~~~

~~~java
@Component
public class ServiceB {

    public ServiceB(ServiceA serviceA) {
    }
}
~~~

To create ServiceA, Spring needs a complete ServiceB. To create ServiceB, Spring needs a complete ServiceA. Neither instance can be created first to break the cycle.

If SpEL references a bean while a bean's constructor or dependencies are being processed, it can also lead to a similar dependency chain.

### 3.3. Setter/Property Cycles and Early References

Some circular dependencies between singleton beans using setter or field injection can be resolved by Spring in certain configurations via the early singleton reference mechanism. This mechanism allows a bean to be referenced before its initialization is complete.

However, this capability has limitations:

- It does not resolve constructor cycles.
- Not all proxy types or bean post-processors are compatible with early references.
- It does not apply as a general solution for all scopes.
- It does not guarantee the bean is used in a fully initialized state.
- It can make initialization order and runtime errors harder to understand.

Do not design an application relying on Spring incidentally resolving a setter injection cycle. If a cycle exists, review the responsibilities and relationships between the beans.

### 3.4. Prototype and Other Scopes

The circular reference handling mechanism for singletons cannot be extrapolated to prototype or all other scopes. Prototype beans are created on demand, and the container does not manage a singleton cache to provide early references in the same way.

If prototype A and prototype B require each other during creation, the circular dependency can still fail. With request, session, or custom scopes, behavior also depends on the configured scope and proxies.

Check the actual scope of each bean when investigating errors.

## 4. Why SpEL Makes Dependencies Harder to Recognize

### 4.1. Dependencies Inside Strings

Compare two approaches:

~~~java
public PricingPolicy(CurrencyRules currencyRules) {
    this.currencyRules = currencyRules;
}
~~~

and:

~~~java
@Value("#{currencyRules.defaultCurrency}")
private String currency;
~~~

The first approach makes the dependency explicit in the constructor. The second puts the bean name inside an expression string; readers must know SpEL mechanics and when @Value is evaluated to notice the relationship.

Explicitly declared dependencies are usually easier to:

- Read and review.
- Build dependency graphs from.
- Unit test.
- Detect circular dependencies in.
- Refactor without missing bean reference strings.

### 4.2. Property Expressions Can Trigger Bean Initialization

An expression that only reads a property can look harmless:

~~~java
@Value("#{appSettings.defaultLocale}")
private Locale locale;
~~~

But if appSettings is a bean that has not been created yet, the bean lookup can still trigger initialization. If appSettings depends on the current bean, a cycle occurs even though the expression calls no methods with side effects.

### 4.3. Method Expressions Make Dependency Chains More Complex

Example:

~~~java
@Value("#{pricingService.defaultPriceList()}")
private PriceList priceList;
~~~

In addition to looking up pricingService, the expression calls a method. The method may read a repository, call another service, or request additional beans through its internal logic.

A long chain of method calls in @Value makes bean creation unpredictable. Avoid using SpEL to perform orchestration or access multiple services during initialization.

### 4.4. Do Not Confuse with Configuration Placeholders

Property placeholders:

~~~java
@Value("$" + "{app.currency:VND}")
private String currency;
~~~

differ from bean references:

~~~java
@Value("#{currencyRules.defaultCurrency}")
private String currency;
~~~

Placeholders retrieve values from Environment or property sources. Bean references require BeanResolver to look up a bean in the container.

If you only need a configuration value such as currency, endpoint, or limit, prefer configuring via application properties, environment variables, or @ConfigurationProperties rather than creating a bean solely so expressions can read its values.

## 5. How to Detect Circular Dependencies

### 5.1. Read the Full Exception

When ApplicationContext fails to start, inspect:

- The outer BeanCreationException.
- BeanCurrentlyInCreationException if present.
- The name of the bean being created at the time of failure.
- The cause chain and beans requested during creation.
- The stack trace at the expression evaluation or bean resolution step.

Specific messages depend on the Spring version and initialization path. Do not rely only on the first exception line; locate the root cause and the bean reference being evaluated.

### 5.2. Search for Bean References in Configuration

Search for expressions with @beanName syntax in:

- @Value annotations.
- XML bean definitions.
- Java configuration calling a parser or Expression.
- Configuration files containing SpEL.
- Classes manually creating StandardEvaluationContext and attaching BeanResolver.
- Policies or helpers evaluating expressions during startup.

When found, determine whether the expression is evaluated at startup or runtime. Then trace the referenced bean and its dependencies.

### 5.3. Build a Dependency Diagram

Record relationships in the direction of one bean needing another:

~~~text
Bean A --SpEL--> Bean B
Bean B --constructor--> Bean C
Bean C --@Value SpEL--> Bean A
~~~

A diagram helps reveal cycles that individual classes alone may not show clearly.

If many beans are involved, list each edge and mark whether it comes from constructor injection, setter injection, @Value, @DependsOn, or a bean lookup inside a method.

### 5.4. Test ApplicationContext Startup

A minimal test creating an ApplicationContext can reproduce the issue without running the full application:

~~~java
@Test
void applicationContextShouldStart() {
    try (AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext(TestConfig.class)) {
        assertNotNull(context.getBean(PricingPolicy.class));
    }
}
~~~

If the context fails to start, the test will reveal the error during bean creation. Create a small test with the relevant configuration to shorten the investigation cycle.

With Spring Boot, you can use a context test or ApplicationContextRunner to test isolated configurations. Ensure the test loads the same profiles, property sources, and bean conditions as the environment where the error occurs.

## 6. Best Fix: Eliminate the Circular Dependency

### 6.1. Extract Shared Logic into a Third Bean

Suppose PricingPolicy and CurrencyRules need the same currency rules. If they reference each other, extract the shared data or rules into an independent bean:

~~~text
PricingPolicy -----> CurrencySettings
CurrencyRules -----> CurrencySettings
~~~

Example:

~~~java
@Component
public class CurrencySettings {

    public String defaultCurrency() {
        return "VND";
    }
}
~~~

~~~java
@Component
public class PricingPolicy {

    private final CurrencySettings settings;

    public PricingPolicy(CurrencySettings settings) {
        this.settings = settings;
    }
}
~~~

~~~java
@Component
public class CurrencyRules {

    private final CurrencySettings settings;

    public CurrencyRules(CurrencySettings settings) {
        this.settings = settings;
    }
}
~~~

Both beans depend on a shared abstraction or data source, without depending back on each other.

This is usually the most sustainable fix because it clarifies responsibilities and the dependency graph.

### 6.2. Move Configuration Data to @ConfigurationProperties

If an expression only references a bean to read configuration values, place those values into a configuration properties class:

~~~java
@ConfigurationProperties(prefix = "app.currency")
public record CurrencyProperties(String defaultCurrency) {
}
~~~

Configuration:

~~~yaml
app:
  currency:
    default-currency: VND
~~~

Beans that need the value can inject CurrencyProperties:

~~~java
@Component
public class PricingPolicy {

    private final CurrencyProperties properties;

    public PricingPolicy(CurrencyProperties properties) {
        this.properties = properties;
    }
}
~~~

This removes the need to look up another bean through SpEL just to fetch a value. It also makes data types, validation, and configuration sources clearer.

### 6.3. Put Dependencies in the Constructor

If one bean genuinely needs another bean to operate, declare the dependency using constructor injection:

~~~java
@Component
public class PricingPolicy {

    private final CurrencyRules currencyRules;

    public PricingPolicy(CurrencyRules currencyRules) {
        this.currencyRules = currencyRules;
    }
}
~~~

The dependency is clearly shown in the class signature. If constructor injection forms a cycle, that is an architectural signal to revisit rather than hide behind SpEL.

Prefer constructor injection for required dependencies. It ensures an object cannot be constructed in a state missing its dependencies.

## 7. When Bean Lookup Must Be Deferred

Some cases genuinely need to look up a bean at the time of use rather than at bean creation time. Provider or proxy mechanisms can be used to defer obtaining the dependency, though they only change the lookup timing; they do not eliminate logical cycles by themselves.

### 7.1. ObjectProvider

Spring provides ObjectProvider to retrieve beans on demand:

~~~java
@Component
public class PricingPolicy {

    private final ObjectProvider<CurrencyRules> rulesProvider;

    public PricingPolicy(
            ObjectProvider<CurrencyRules> rulesProvider) {
        this.rulesProvider = rulesProvider;
    }

    public String currencyForOrder(Order order) {
        CurrencyRules rules = rulesProvider.getObject();
        return rules.currencyFor(order);
    }
}
~~~

ObjectProvider is injected without immediately creating CurrencyRules. The bean is only looked up when getObject() is called.

This can defer lookup until a runtime method runs, after beans have initialized. However, if currencyFor() is called while CurrencyRules is still being created and needs PricingPolicy, the cycle still happens.

### 7.2. @Lazy

@Lazy can be used on a dependency to create a proxy and defer initializing the target bean until the proxy is used:

~~~java
@Component
public class PricingPolicy {

    private final CurrencyRules currencyRules;

    public PricingPolicy(@Lazy CurrencyRules currencyRules) {
        this.currencyRules = currencyRules;
    }
}
~~~

@Lazy can help defer initialization in some cases. However, when an expression accesses a property or calls a method on the lazy bean, the proxy may trigger creation of the target bean right then.

Therefore, @Lazy is not a general solution for circular dependencies. Only use it when deferral is an intentional part of the design and usage timing is controlled.

### 7.3. Provider and Lookup Methods

Jakarta Inject Provider or lookup method mechanisms can also defer retrieving a dependency. They are appropriate when objects have different lifecycles or when a fresh instance is needed on demand.

Verify lifecycles and when the provider is invoked. If two beans still call each other during initialization, changing the lookup mechanism does not fix the root cause.

### 7.4. Using Bean References in SpEL at Runtime

If an expression needs to reference a bean but does not need the value at startup, evaluation can be deferred to a business method called after the context is ready:

~~~java
public boolean isEligible(
        String expressionSource,
        EvaluationContext context) {

    Expression expression =
            parser.parseExpression(expressionSource);

    return Boolean.TRUE.equals(
            expression.getValue(context, Boolean.class)
    );
}
~~~

This approach is only suitable when the source and context are controlled, and evaluation does not happen during bean initialization. Do not push all initialization logic to runtime just to dodge an error if the dependencies still form a logical cycle.

## 8. Why @DependsOn Does Not Break Cycles

@DependsOn tells Spring that one bean must be initialized after another bean:

~~~java
@DependsOn("currencyRules")
@Component
public class PricingPolicy {
}
~~~

It controls bean initialization and destruction order in certain situations. It does not remove a bidirectional dependency relationship.

If PricingPolicy needs CurrencyRules and CurrencyRules also needs PricingPolicy, adding @DependsOn in either direction may just cause the container to enter the other bean creation chain first and still come back to the bean currently being created.

Do not use @DependsOn as a fix for dependency cycles. Use it for genuinely independent initialization ordering requirements with no reverse dependency.

Similarly, @Order controls ordering in certain mechanisms such as collection injection or ordered processing; it does not resolve bean initialization cycles.

## 9. Circular References and Spring Boot Configuration

### 9.1. Circular Dependency Support

Spring Framework has mechanisms to handle certain singleton circular dependencies, especially in setter/property injection cases. This capability depends on dependency types, scopes, proxies, bean post-processors, and container configuration.

Constructor cycles cannot be resolved via early singleton references because no instance exists yet to supply.

### 9.2. Spring Boot Can Reject Circular References

Some Spring Boot versions disallow circular references by default and may halt startup when a cycle is detected. Exact configuration and behavior depend on the Boot version in use.

In versions supporting the property:

~~~properties
spring.main.allow-circular-references=true
~~~

enabling this option may permit certain singleton cycles that Spring is able to resolve. It does not make every cycle valid and does not resolve constructor cycles.

Do not enable this option just to make the application start. Treat the exception as a signal to inspect the dependency graph and refactor.

### 9.3. Difference Between Startup and Runtime Lookup

A bean reference in @Value may be evaluated during initialization. An expression evaluated manually by the application after startup can look up beans once the context is complete.

The two cases have different timings and risks. When troubleshooting errors, determine whether the expression is used in a bean definition, field injection, lifecycle callback, or a runtime business flow.

## 10. Common Design Mistakes

| Practice | Issue | Resolution |
|---|---|---|
| @Value referencing a bean that depends back on it | Creates hidden dependency | Split beans or use explicit configuration |
| Two beans reading each other's properties via SpEL | Hard-to-spot initialization cycle | Move shared data to a third bean |
| Calling service methods inside @Value | Bean init may trigger business logic | Move logic to a service/runtime flow after startup |
| Using @Lazy to mask a cycle | Only defers when the failure may occur | Identify and eliminate the circular relationship |
| Using @DependsOn in both directions | Only controls order, does not break dependency | Redesign the relationship |
| Enabling allow-circular-references to ignore errors | Can hide fragile design | Refactor and prefer constructor injection |
| Calling ApplicationContext.getBean in constructor | Creates hidden lookup and hard-to-control runtime deps | Inject dependencies explicitly or use a provider |
| Using SpEL to read simple config values | Increases unnecessary coupling | Use @ConfigurationProperties or placeholders |
| Catching BeanCurrentlyInCreationException and returning default | Hides initialization errors | Fix the dependency graph and preserve the cause |

## 11. Investigation and Fixing Workflow

When encountering a circular dependency caused by an expression referencing another bean, you can follow this sequence:

1. **Identify the beans in the exception.** Note the bean being created and the bean requested at the time of error.
2. **Locate the relevant expressions.** Check @Value, XML bean definitions, and code manually evaluating SpEL.
3. **Determine evaluation timing.** Distinguish startup, property population, @PostConstruct, and runtime.
4. **Trace downstream dependencies.** Inspect constructors, fields, setters, @DependsOn, and other bean references of the looked-up bean.
5. **Draw the cycle.** Record every dependency edge and mark edges coming from SpEL.
6. **Identify the data actually needed.** It may just be a configuration value, a predicate, or a small policy.
7. **Refactor.** Extract a shared component, move configuration to @ConfigurationProperties, inject dependencies explicitly, or defer lookup if genuinely required.
8. **Test startup.** Create an ApplicationContext with realistic configuration and verify no cycle remains.
9. **Test runtime behavior.** Ensure expressions still return correct results and do not trigger lookups at unexpected stages.

Do not simply add @Lazy or enable circular references and conclude the issue is fixed. Verify that the dependency cycle has genuinely been eliminated or that deferred lookup is intentional and safe.

## 12. Testing Circular Dependencies

### 12.1. Testing Context Startup

You can write an integration test to ensure ApplicationContext can create the relevant beans:

~~~java
@SpringBootTest
class ApplicationContextTest {

    @Autowired
    private PricingPolicy pricingPolicy;

    @Test
    void contextStartsAndPricingPolicyIsAvailable() {
        assertNotNull(pricingPolicy);
    }
}
~~~

If the test fails while creating the context, inspect the cause chain to find the beans and expression causing the cycle.

### 12.2. Testing the Expression Independently

If an expression only needs to retrieve a value, it can be tested in an already-initialized context:

~~~java
Expression expression =
        parser.parseExpression("@currencyRules.defaultCurrency");

String currency =
        expression.getValue(evaluationContext, String.class);

assertEquals("VND", currency);
~~~

This test verifies that bean reference and property resolution work in a runtime context. It does not replace an ApplicationContext startup test if the expression is used in @Value or a bean definition.

### 12.3. Testing Error Cases

If the application configures expressions per environment, also test profiles or property sources that could alter bean references.

Tests should verify:

- Context starts with valid configuration.
- Referenced beans exist.
- Expressions return the expected type and value.
- No unexpected lookups happen in constructors or @PostConstruct.
- Configuration missing a bean reports a clear error.
- No silent fallback hides initialization errors.

## 13. Summary

Bean references in SpEL use the **@beanName** syntax and can cause Spring to look up or initialize a bean when the expression is evaluated. If the referenced bean in turn depends on the bean being created, the application may encounter a circular dependency and errors like BeanCurrentlyInCreationException.

- Dependencies hidden in SpEL strings are harder to notice than constructor injection.
- Property expressions can also trigger bean lookups, not just method calls.
- Constructor cycles generally cannot be resolved; some singleton setter cycles can only be handled under limited conditions.
- @Lazy and ObjectProvider can defer lookups but do not automatically eliminate logical cycles.
- @DependsOn only controls ordering, not bidirectional dependencies.
- Do not enable circular references just to mask errors.
- Prefer extracting shared components, moving configuration values to @ConfigurationProperties, and declaring dependencies explicitly.
- Test both startup and runtime evaluation timing.

SpEL is suited for expressing a short value or predicate. When an expression must look up multiple beans or coordinate initialization logic, move dependencies to Java and redesign the beans so each component has clear responsibilities without needing circular back-references.