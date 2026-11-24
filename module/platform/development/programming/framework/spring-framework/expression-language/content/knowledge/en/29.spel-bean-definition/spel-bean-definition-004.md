# SpEL in @Bean Methods and Initialization Values in Spring Framework

In Spring, beans can be created by methods annotated with @Bean. This method returns an object managed by the Spring container. Values passed to the object's constructor or setters can come from external properties, other beans, or a Spring Expression Language (SpEL) expression.

A common approach is to use @Value on a parameter of the @Bean method:

~~~java
@Configuration
public class BillingConfiguration {

    @Bean
    public BillingSettings billingSettings(
            @Value("#{2 * 60}") int timeoutSeconds) {
        return new BillingSettings(timeoutSeconds);
    }
}
~~~

Spring evaluates the expression and passes the result to timeoutSeconds before calling the bean creation method. The body of billingSettings remains ordinary Java code.

SpEL can also be used in property values of bean definitions, in XML, or in other Spring configurations that support expressions. This lesson explains evaluation locations, initializing beans with dynamic values, bean references, placeholders, type conversion, and lifecycle considerations.

## 1. What Is a @Bean Method?

A @Bean method resides in a Spring configuration class and returns the object to be registered in the container.

~~~java
@Configuration
public class ApplicationConfiguration {

    @Bean
    public GreetingService greetingService() {
        return new GreetingService("Hello");
    }
}
~~~

When the container processes the configuration, Spring calls the greetingService() method and registers the returned object as a bean. By default, the bean name is the method name, which in this example is greetingService.

A @Bean method can accept parameters. Spring resolves those parameters from the container, including other dependencies or values injected via @Value.

~~~java
@Configuration
public class ApplicationConfiguration {

    @Bean
    public GreetingService greetingService(
            MessageCatalog messageCatalog) {
        return new GreetingService(messageCatalog.defaultGreeting());
    }
}
~~~

Here, MessageCatalog is a dependency directly injected by Spring. When a parameter needs to be a value computed from an expression, @Value can be placed on that parameter.

## 2. SpEL in @Bean Method Parameters

@Value can be placed on a @Bean method parameter. If the value has the form #{...}, Spring evaluates the inner part with SpEL and converts the result to the parameter type if needed.

~~~java
@Configuration
public class ReportConfiguration {

    @Bean
    public ReportSettings reportSettings(
            @Value("#{10 + 5}") int pageSize,
            @Value("#{true}") boolean includeSummary) {

        return new ReportSettings(pageSize, includeSummary);
    }
}
~~~

When creating ReportSettings:

1. Spring processes the parameters of the @Bean method.
2. The expression #{10 + 5} is evaluated to the number 15.
3. The expression #{true} is evaluated to Boolean true.
4. The results are converted to the corresponding parameter types if needed.
5. Spring invokes the reportSettings(...) method with the prepared values.
6. The returned object is registered in the container.

This approach is suitable for concise initialization values such as limits, toggle flags, or a value computed from configuration.

## 3. Combining Property Placeholders with SpEL

Property placeholders use the syntax ${property.name:default}. Placeholders retrieve values from the Environment or property sources. SpEL uses the syntax #{...} and is used to compute values or access objects.

The two mechanisms can be combined when a property needs to be computed before being passed into a @Bean method.

For example, configuring seconds in application.properties:

~~~properties
app.cache.ttl-seconds=45
~~~

Use that property to create a Duration:

~~~java
@Configuration
public class CacheConfiguration {

    @Bean
    public CacheSettings cacheSettings(
            @Value("#{T(java.time.Duration).ofSeconds(${app.cache.ttl-seconds:30})}")
            Duration ttl) {

        return new CacheSettings(ttl);
    }
}
~~~

The placeholder is resolved to the configuration value, and then SpEL invokes Duration.ofSeconds(...) to create a Duration object. If the property is not provided, the placeholder uses the default value 30.

If you only need to inject the configuration value without computation, using a placeholder directly is usually simpler:

~~~java
@Bean
public CacheSettings cacheSettings(
        @Value("${app.cache.ttl-seconds:30}") long ttlSeconds) {
    return new CacheSettings(Duration.ofSeconds(ttlSeconds));
}
~~~

Choose placeholders for environment-dependent configuration. Only add SpEL when you need calculations, bean access, or more complex value creation.

## 4. Referencing Beans in Initialization Values

SpEL can reference another bean in the container using the @ symbol before the bean name. This allows a new bean's value to depend on a property or method of an already registered bean.

~~~java
@Configuration
public class BillingConfiguration {

    @Bean
    public BillingSettings billingSettings(
            @Value("#{ @pricingService.defaultCurrency }")
            String currency) {

        return new BillingSettings(currency);
    }
}
~~~

Here, Spring evaluates the expression to retrieve defaultCurrency from the pricingService bean and passes the result to the BillingSettings constructor.

A bean method can also be called:

~~~java
@Bean
public ShippingSettings shippingSettings(
        @Value("#{ @pricingService.defaultShippingThreshold() }")
        BigDecimal threshold) {

    return new ShippingSettings(threshold);
}
~~~

The referenced bean must be resolvable in the ApplicationContext. The bean name or alias in the expression must match the registered name.

When the dependency is an object that the @Bean method needs to use across multiple operations, prefer injecting the dependency directly via a method parameter instead of fetching a single property via SpEL:

~~~java
@Bean
public BillingService billingService(PricingService pricingService) {
    return new BillingService(pricingService);
}
~~~

Direct dependency injection makes relationships between beans clearer. SpEL bean references are better suited when you need to compute a configuration value right at the injection point.

## 5. SpEL in Bean Constructor and Setter Values

A @Bean method typically initializes an object using a constructor or creates the object and then sets properties. SpEL can provide values for the input parameters of the @Bean method, while Java code decides how to use those values to create the instance.

Constructor example:

~~~java
public class RetryPolicy {
    private final int maxAttempts;
    private final Duration delay;

    public RetryPolicy(int maxAttempts, Duration delay) {
        this.maxAttempts = maxAttempts;
        this.delay = delay;
    }
}

@Configuration
public class RetryConfiguration {

    @Bean
    public RetryPolicy retryPolicy(
            @Value("${app.retry.max-attempts:3}") int maxAttempts,
            @Value("#{T(java.time.Duration).ofMillis(500)}") Duration delay) {

        return new RetryPolicy(maxAttempts, delay);
    }
}
~~~

The maxAttempts value comes from a property placeholder. The delay value is created using SpEL via Duration's static method.

If properties need to be set after creating the object, the @Bean method can call setters like ordinary Java code:

~~~java
@Bean
public ReportSettings reportSettings(
        @Value("#{ 'Monthly report' }") String title) {

    ReportSettings settings = new ReportSettings();
    settings.setTitle(title);
    return settings;
}
~~~

SpEL only supplies the value for the parameter. Calling the setter in the method body is still performed by Java.

## 6. SpEL in XML Bean Definitions

In an XML bean definition, a property value can contain a SpEL expression. Spring evaluates the expression when creating and configuring the bean.

~~~xml
<bean id="reportSettings"
      class="com.example.ReportSettings">
    <property name="pageSize" value="#{10 + 5}" />
    <property name="title" value="#{'Monthly report'}" />
</bean>
~~~

Placeholders can be used together with SpEL:

~~~xml
<bean id="cacheSettings"
      class="com.example.CacheSettings">
    <property name="ttlSeconds"
              value="#{${app.cache.ttl-seconds:30}" />
</bean>
~~~

In the example, the placeholder supplies the number of seconds and SpEL evaluates that value. XML configuration must follow XML escaping rules if the expression contains special characters.

SpEL in XML bean definitions is an integration point of the Spring container. Do not assume that every XML attribute or every annotation automatically supports SpEL.

## 7. Creating Collections and Maps as Initialization Values

SpEL supports inline lists and inline maps. They can be used as bean configuration values if the target type and conversion mechanism support them.

Example:

~~~java
@Configuration
public class AccessConfiguration {

    @Bean
    public AccessSettings accessSettings(
            @Value("#{ {'reader', 'editor', 'admin'} }")
            List<String> roles) {

        return new AccessSettings(roles);
    }
}
~~~

Inline map:

~~~java
@Bean
public FeatureSettings featureSettings(
        @Value("#{ {'checkout': true, 'new-search': false} }")
        Map<String, Boolean> flags) {

    return new FeatureSettings(flags);
}
~~~

Inline collection elements are evaluated according to the type of each expression. If a collection has elements of multiple different types, use a general receiving type and check the actual types before using them.

If the bean needs a mutable collection, consider making a defensive copy in the constructor. Do not assume a collection literal in SpEL is a safe place to store mutable state.

## 8. Using Type References and Static Methods

The T(...) operator allows SpEL to reference Java types. Static methods can be called to create objects or compute values.

Example:

~~~java
@Bean
public Duration requestTimeout(
        @Value("#{T(java.time.Duration).ofSeconds(20)}")
        Duration timeout) {

    return timeout;
}
~~~

Another example using Math:

~~~java
@Bean
public Integer maximumBatchSize(
        @Value("#{T(java.lang.Math).max(50, 100)}")
        int maximum) {

    return maximum;
}
~~~

Type references are useful when creating a small value from a Java API. If initialization logic is complex or needs independent testing, move the logic to a Java method or a dedicated bean.

## 9. Default Values, Elvis, and Null

Default values can be used in placeholders:

~~~java
@Bean
public RegionSettings regionSettings(
        @Value("${app.region:unknown}") String region) {

    return new RegionSettings(region);
}
~~~

The Elvis operator in SpEL provides an alternative value when the left-hand side is null or an empty string:

~~~java
@Bean
public RegionSettings regionSettings(
        @Value("#{ @applicationSettings.region ?: 'unknown' }")
        String region) {

    return new RegionSettings(region);
}
~~~

The two mechanisms have different purposes:

- Placeholder defaults handle the case where a property key has no resolved value.
- Elvis handles the result of a SpEL expression.

If an expression accesses nested properties that may be null, use safe navigation:

~~~java
@Value("#{ @applicationSettings.contact?.email ?: 'support@example.com' }")
private String supportEmail;
~~~

Safe navigation protects the property path at the position where it is used. It does not automatically handle a nonexistent bean name or other evaluation errors.

## 10. Type Conversion Before Invoking the @Bean Method

A SpEL value has a runtime type. A @Bean method parameter has a specific Java type. Spring can convert the value when an appropriate converter exists.

Example:

~~~java
@Bean
public RetryPolicy retryPolicy(
        @Value("#{ '5' }") int maxAttempts,
        @Value("#{ 'true' }") boolean enabled) {

    return new RetryPolicy(maxAttempts, enabled);
}
~~~

String values can be converted to int and boolean thanks to Spring's conversion mechanism. If no suitable converter exists, parameter resolution can fail during bean creation.

For complex types, directly creating a value with an explicit type in SpEL is usually easier to understand:

~~~java
@Bean
public CacheSettings cacheSettings(
        @Value("#{T(java.time.Duration).ofMinutes(5)}")
        Duration ttl) {

    return new CacheSettings(ttl);
}
~~~

When configuring a custom converter, verify that it is registered in the conversion environment used by the @Value mechanism. Do not assume every manually created context or integration point shares the same ConversionService.

## 11. Evaluation Timing and Bean Lifecycle

Values in @Value are resolved while Spring creates and injects beans. The resulting value is passed into the constructor, field, or setter when the bean is processed.

Example:

~~~java
@Bean
public StartupInfo startupInfo(
        @Value("#{T(java.lang.System).currentTimeMillis()}")
        long createdAt) {

    return new StartupInfo(createdAt);
}
~~~

createdAt reflects the time the expression was evaluated when the bean was initialized. It does not automatically update afterward.

If the expression references another bean, that bean must be resolvable when Spring evaluates the parameter. If two beans have a circular dependency during initialization, SpEL cannot automatically resolve the cycle.

For example, if BillingSettings needs PricingService to obtain currency, while PricingService needs BillingSettings in its constructor, the application may encounter a circular dependency error. Review the dependency graph, extract shared configuration, or inject dependencies in an appropriate way.

Do not use initialization expressions to call methods with side effects or perform long-running work. Bean creation should be predictable and easy to test.

## 12. @Bean Methods, @Configuration, and Inter-Bean Calls

In a full @Configuration class, Spring can proxy calls between @Bean methods to preserve singleton semantics for container-managed beans.

Example:

~~~java
@Configuration
public class ServiceConfiguration {

    @Bean
    public PricingService pricingService() {
        return new PricingService();
    }

    @Bean
    public CheckoutService checkoutService() {
        return new CheckoutService(pricingService());
    }
}
~~~

In a full @Configuration setup, the call to pricingService() from checkoutService() is handled by the container through a proxy to obtain the managed bean.

If using lite configuration mode, such as a class with only @Bean and not full @Configuration, directly calling a @Bean method can behave as an ordinary Java call and create a new instance. When a dependency is needed, a @Bean method parameter is usually clearer:

~~~java
@Bean
public CheckoutService checkoutService(PricingService pricingService) {
    return new CheckoutService(pricingService);
}
~~~

SpEL does not change proxy rules or Java call semantics between @Bean methods. Distinguish expressions evaluated by Spring from method calls executed in the Java body.

## 13. Distinguishing SpEL Values from Java Code in @Bean Methods

This is an important distinction when reading configuration.

In the example:

~~~java
@Bean
public ReportSettings reportSettings(
        @Value("#{10 + 5}") int pageSize) {

    return new ReportSettings(pageSize);
}
~~~

SpEL only appears in the @Value annotation on the parameter. Spring evaluates the expression and passes the number 15 into the method. The statement new ReportSettings(pageSize) is Java code, not SpEL.

Similarly:

~~~java
@Bean
public ReportSettings reportSettings(Environment environment) {
    int pageSize = environment.getProperty(
            "app.report.page-size",
            Integer.class,
            15
    );

    return new ReportSettings(pageSize);
}
~~~

This is Java reading Environment directly. There is no SpEL expression in this example.

You can choose between the two approaches based on your needs:

- Use @Value with SpEL for short values declared right at the parameter.
- Use Environment or Java code when multiple processing steps, validation, or conditional branches are needed.
- Use direct dependency injection when another bean is needed as a long-lived dependency.

## 14. Common Errors

| Error | Cause | Resolution |
|---|---|---|
| Thinking a @Bean method body is automatically SpEL | SpEL is only evaluated at integration points that support expressions. | Place the expression in @Value or an appropriate bean-definition value. |
| Using a placeholder when computation is needed | Placeholders only retrieve properties by key. | Use #{...} to evaluate SpEL. |
| Forgetting #{...} delimiters | Spring does not recognize the expression region. | Check annotation syntax or XML value. |
| Bean reference cannot be resolved | Wrong bean name or bean does not belong to the current container. | Check the bean name, alias, and context. |
| Parameter cannot be converted | Result type is incompatible with the target Java type. | Use an appropriate literal type or converter. |
| Circular bean dependency | Initialization values reference back and forth between beans. | Separate dependencies or redesign initialization. |
| Calling a method with side effects during initialization | The expression runs during bean creation. | Prefer pure calculations and read-only methods. |
| Treating @Bean calls like ordinary Java calls | Lite configuration lacks full proxying for inter-bean method calls. | Inject the bean via a @Bean method parameter. |
| Expecting @Value to update automatically | The value is injected when the bean is processed. | Query the dependency when a fresh value is needed or use a dynamic configuration mechanism. |
| Putting untrusted expressions into configuration | Expressions can access many capabilities of the evaluation context. | Only evaluate trusted configuration expressions and restrict access rights. |

When diagnosing, distinguish placeholder resolution errors, SpEL parsing errors, bean lookup errors, type conversion errors, and errors inside the Java method body. These errors occur at different stages of bean creation.

## 15. Best Practices

1. Use @Bean parameters to make clear the values and dependencies needed for object creation.
2. Use @Value("#{...}") when you need to evaluate SpEL at a Spring-supported injection point.
3. Use placeholders for environment-dependent properties and add SpEL when computation is required.
4. Prefer direct bean injection if the method needs to use the dependency as an object.
5. Use type references for small calculations or value creation; move complex logic to Java.
6. Handle null and default values explicitly.
7. Verify type conversion between expression results and method parameters.
8. Avoid circular dependencies between beans during initialization.
9. Do not confuse Java code in a @Bean method body with SpEL expressions.
10. Keep expressions short, readable, and free of side effects.

## 16. Takeaways

- A @Bean method is a Java method that creates a bean and returns a Spring-managed object.
- @Value on a @Bean method parameter allows Spring to evaluate SpEL before calling the method.
- SpEL can also be used in bean definition property values, such as XML configuration.
- Placeholder ${key:default} retrieves configuration; #{...} evaluates an expression.
- Expressions can reference beans, properties, methods, types, operations, and inline collections.
- Spring converts the result to the parameter type if a suitable converter exists.
- Values are evaluated during bean creation and injection; they do not update continuously.
- SpEL does not alter Java or proxy rules between @Bean methods.
- Use direct dependency injection for long-lived dependencies; use SpEL for configuration values computed at the injection point.
- Keep initialization logic predictable, avoiding side effects and dependency cycles.
