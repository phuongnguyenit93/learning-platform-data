# SpEL in configuration conditions and bean properties

Spring allows using SpEL in many configuration points to compute values for bean properties or decide whether a configuration should be applied. In annotations, two common approaches are using @Value with a SpEL expression and using @ConditionalOnExpression in Spring Boot to decide whether to register a bean.

When reading configuration, distinguish property placeholders from SpEL. A placeholder retrieves a value from a configuration source by property name; SpEL parses and evaluates an expression that can access objects, call methods, perform operations, or read beans. The two mechanisms can be combined, but they have different syntax and processing timing.

## 1. Using SpEL in @Value

The @Value annotation supports SpEL expressions placed inside the #{} delimiters. Spring evaluates the expression and assigns the result to the matching field, constructor parameter, or method parameter.

Example:

~~~java
@Component
public class AppInfo {

    @Value("#{ 'Spring Framework' }")
    private String productName;

    @Value("#{2 * 3}")
    private int workerCount;

    @Value("#{T(java.lang.Math).PI}")
    private double pi;
}
~~~

The first expression returns a string. The second performs multiplication. The third references the static field PI via the type reference T(...).

SpEL does not merely read an existing property. It can compute values from literals, variables, properties, methods, or bean references that Spring's EvaluationContext allows accessing.

Use @Value when the value to inject can be expressed concisely as an expression. If the calculation contains many business rules or needs complex error handling, move the logic into a clearly named bean or method and inject the required result.

## 2. Distinguishing property placeholders from SpEL

Property placeholders and SpEL serve different purposes:

| Syntax | Mechanism | Purpose |
|---|---|---|
| ${app.name} | Property placeholder | Retrieve a property value from Environment or a configuration source |
| #{2 * 3} | SpEL | Evaluate an expression |
| #{${app.limit:10} * 2} | Placeholder combined with SpEL | Retrieve the property, then use the value in an expression |

Placeholder example:

~~~java
@Value("${app.name:Spring}")
private String appName;
~~~

Spring looks up the app.name property. If it is absent, the default value Spring is used.

SpEL example:

~~~java
@Value("#{2 * 3}")
private int limit;
~~~

Here no external property is read; Spring evaluates the arithmetic expression and injects the result 6.

The two mechanisms can be combined:

~~~java
@Value("#{${app.limit:10} * 2}")
private int doubledLimit;
~~~

The placeholder is resolved first to substitute the value of app.limit, then the part inside #{} is evaluated as SpEL. If app.limit has the value 15, the injected result is 30.

Do not confuse the delimiters. Use ${...} when you only need to read a configuration property; use #{...} when you need to evaluate an expression. Only combine them when you genuinely need to perform calculations or object access on a property value.

## 3. Using placeholders for simple configuration

For simple configuration values, placeholders are usually the clearest choice:

~~~java
@Component
public class MailSettings {

    @Value("${mail.host:localhost}")
    private String host;

    @Value("${mail.port:25}")
    private int port;

    @Value("${mail.enabled:false}")
    private boolean enabled;
}
~~~

Properties can come from application.properties, application.yml, environment variables, command-line arguments, or other configuration sources supported by Environment.

Spring handles type conversion when injecting values into fields. For example, the string "25" can be converted to int if an appropriate conversion exists. If the property has an invalid format or cannot be converted, bean creation may fail.

Placeholders are suitable when configuration only needs a single value. There is no need to wrap every property in SpEL if there is no calculation or additional logic.

## 4. Using SpEL to compute configuration values

SpEL can combine properties to produce a new value:

~~~java
@Component
public class RetrySettings {

    @Value("#{${retry.base-delay:1000} * 2}")
    private long secondDelay;

    @Value("#{${retry.max-attempts:3} + 1}")
    private int totalAttempts;
}
~~~

The first expression multiplies the retry.base-delay value by 2. The second adds one more attempt to retry.max-attempts.

Arithmetic, comparison, logical, and conditional operators can be used to compute values. When an expression grows long, move the formula into a method or configuration bean for easier verification.

Identify the target type of the field. The SpEL result must be compatible with that type or convertible through Spring's conversion mechanism. If the result is null while the field is a primitive, injection may fail.

## 5. Accessing Environment in SpEL

In a Spring environment, expressions can access objects provided in the evaluation context, including Environment in appropriate contexts.

Example:

~~~java
@Value("#{environment['app.region']}")
private String region;

@Value("#{environment['feature.audit.enabled']}")
private boolean auditEnabled;
~~~

This syntax uses a property accessor to read a key from Environment. If the property might not exist, decide how to handle null or provide a default value using a placeholder:

~~~java
@Value("${app.region:local}")
private String region;
~~~

For configuration that only needs to retrieve a single property, a placeholder is usually easier to read. Accessing Environment via SpEL is useful when that value is part of a larger expression or needs to be combined with other objects.

Do not assume every SpEL expression automatically has an environment variable available. Accessibility depends on the EvaluationContext Spring creates for the specific configuration location.

## 6. Using SpEL with bean references

SpEL can reference beans in the Spring container using the @beanName syntax, provided the EvaluationContext has an appropriate BeanResolver.

Example:

~~~java
@Component
public class GreetingProvider {

    public String greeting() {
        return "Hello from Spring";
    }
}

@Component
public class WelcomeMessage {

    @Value("#{ @greetingProvider.greeting() }")
    private String message;
}
~~~

The expression calls the greeting() method on the greetingProvider bean. The method result is injected into the message field.

Bean references can be used to retrieve properties or call methods with arguments:

~~~java
@Value("#{ @currencySettings.defaultCurrency }")
private String currency;

@Value("#{ @priceCalculator.withTax(100, 0.08) }")
private BigDecimal total;
~~~

The bean must be registered in the ApplicationContext and resolvable from the context evaluating the expression. A wrong bean name or inaccessible method/property will cause an error during injection or evaluation.

Only use bean references for small, easy-to-understand operations. If @Value calls a chain of multiple methods or depends on multiple services, create a dedicated configuration bean to avoid hiding initialization logic inside annotations.

## 7. Calling static methods and type references

SpEL supports the T(...) type reference to access classes and call static methods:

~~~java
@Value("#{T(java.lang.Math).max(10, 20)}")
private int maximum;

@Value("#{T(java.util.UUID).randomUUID().toString()}")
private String instanceId;
~~~

The first expression calls Math.max. The second generates a UUID and converts it to a String.

Static methods can be convenient for small calculations or utilities. However, methods that generate random values or depend on system state can produce different results across evaluations. Consider when the bean is created and whether the value needs to remain stable throughout the bean lifecycle.

If a fixed value from configuration is needed, use a placeholder. If testable logic or multiple service dependencies are needed, move the logic to a dedicated bean.

## 8. Conditional configuration with @ConditionalOnExpression

Spring Boot provides @ConditionalOnExpression to register a bean or configuration only when a SpEL expression returns true.

Example:

~~~java
@Configuration
@ConditionalOnExpression("${feature.audit.enabled:false}")
public class AuditConfiguration {

    @Bean
    public AuditService auditService() {
        return new AuditService();
    }
}
~~~

If the feature.audit.enabled property is true, the configuration is applied and the AuditService bean is registered. If the value is false, the configuration is excluded from the ApplicationContext.

Because the expression is evaluated as a Boolean condition, ensure the result has a Boolean meaning. An incompatible string or object can cause a conversion or evaluation error.

@ConditionalOnExpression belongs to Spring Boot, not core Spring Framework annotations. It is commonly used in auto-configuration or Spring Boot application configuration.

## 9. Combining multiple properties in a condition

A condition can be based on multiple properties:

~~~java
@Configuration
@ConditionalOnExpression(
    "${feature.audit.enabled:false} and ${app.environment:dev} == 'prod'"
)
public class ProductionAuditConfiguration {
}
~~~

The intent is to apply the configuration only when audit is enabled and the environment is prod. In practice, pay attention to how placeholders are resolved and the data types of the values. The final expression after placeholder substitution must be valid SpEL syntax.

Another approach is to use Environment or a configuration bean directly if the context supports it. However, multi-property conditions are often easier to manage if placed in a composite property or a clearly named Java condition.

Use parentheses when combining AND/OR to avoid confusion about condition grouping:

~~~text
(feature.alpha.enabled and app.region == 'west')
or feature.override.enabled
~~~

Keep conditions concise so readers can understand why a bean was registered or excluded.

## 10. When to use @ConditionalOnProperty instead of SpEL?

If only checking a single Boolean property or comparing a property against a fixed value, @ConditionalOnProperty is usually clearer.

Example:

~~~java
@Configuration
@ConditionalOnProperty(
        prefix = "feature.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class AuditConfiguration {
}
~~~

This annotation directly expresses the intent: enable the configuration when feature.audit.enabled is true. There is no need to construct a SpEL expression.

Use @ConditionalOnExpression when the condition genuinely needs to combine multiple expressions or SpEL operations. If the condition is just toggling a feature on/off, prefer @ConditionalOnProperty. For complex conditions that need to query application state, a custom Condition implementation may be easier to test and maintain.

## 11. Caution when referencing beans in conditions

Avoid referencing business beans in @ConditionalOnExpression unless truly necessary. Spring Boot evaluates conditions during configuration processing. Referencing a bean in an expression can cause that bean to be initialized very early, ahead of its normal timing and before some post-processors can be fully applied.

This can result in the bean not being processed as expected, especially if the bean depends on proxies, AOP, or other post-processing.

Configuration conditions should primarily rely on available properties and environment information. If complex logic or reading bean state is needed, consider an appropriate Condition implementation or organize configuration so the condition does not initialize business beans prematurely.

Do not use methods with side effects in condition expressions. Conditions may be evaluated during startup and should not send notifications, write data, or mutate application state.

## 12. SpEL in XML bean definitions

SpEL can also be used in XML configuration to set properties or constructor arguments:

~~~xml
<bean id="cacheSettings" class="com.example.CacheSettings">
    <property name="maximumSize" value="#{100 * 2}" />
    <property name="enabled" value="#{systemProperties['app.cache.enabled']}" />
</bean>
~~~

The value attribute contains an expression inside #{}. Spring evaluates the expression and converts the result to the target property type if needed.

Another bean can be referenced in the expression:

~~~xml
<property name="defaultCurrency" value="#{@currencySettings.defaultCurrency}" />
~~~

If you only need to inject a configuration property, XML can also use the ${...} placeholder through placeholder resolver configuration. Keep the style consistent and choose the mechanism that fits the data source.

## 13. Injecting into fields, constructors, and methods

@Value can be used on fields, constructor parameters, or method parameters depending on how the bean is configured.

Constructor injection example:

~~~java
@Component
public class ApiSettings {

    private final String baseUrl;
    private final int timeout;

    public ApiSettings(
            @Value("${api.base-url}") String baseUrl,
            @Value("${api.timeout:5000}") int timeout) {

        this.baseUrl = baseUrl;
        this.timeout = timeout;
    }
}
~~~

SpEL can be used on parameters:

~~~java
public ApiSettings(
        @Value("#{${api.timeout:5000} * 2}") int timeout) {
    this.timeout = timeout;
}
~~~

Constructor injection makes required dependencies and configuration visible right when the object is created. For closely related configuration values, a @ConfigurationProperties class is often more convenient than many scattered @Value annotations.

## 14. @Value and @ConfigurationProperties

@Value is suitable for a few individual values or a small expression. When many properties belong to the same group, @ConfigurationProperties is usually easier to organize.

Example:

~~~java
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    private String host;
    private int port = 25;
    private boolean enabled;

    // getters and setters
}
~~~

Structured configuration is bound to the object. This mechanism supports type conversion and validation suited for property groups.

SpEL in @Value can compute an individual value, but it should not be used to replace the entire process of binding a large configuration tree. Choose @ConfigurationProperties when structured configuration, multiple fields, and centralized validation are needed.

## 15. Evaluation timing and bean lifecycle

@Value expressions are usually processed while Spring creates and configures the bean. The value is injected when processing the corresponding bean definition/bean instance, after placeholders and SpEL are resolved by the container's mechanism.

For singleton beans, the injected field value is typically retained in that instance. If the source property changes after the bean is created, the field does not update automatically just because Environment changed.

If refreshable configuration is needed, use your application's appropriate refresh/configuration mechanism instead of expecting @Value to track every change automatically.

The @ConditionalOnExpression condition is used to decide whether a configuration or bean is registered during ApplicationContext initialization. It is not a condition re-evaluated automatically on every method call or every request.

## 16. Handling missing values, null, and wrong types

A placeholder without a value can cause an error if there is no default and no corresponding property. A default can be specified:

~~~java
@Value("${app.region:local}")
private String region;
~~~

With SpEL, an expression can return null:

~~~java
@Value("#{systemProperties['missing.key']}")
private String optionalValue;
~~~

If the target field is a reference type, null can be assigned if conversion and injection allow it. If the field is a primitive such as int or boolean, null cannot be represented and may cause an error.

For multi-step expressions, check for null before deep access or calling methods. If configuration is mandatory, let the application fail-fast with a clear message instead of silently using an inappropriate default value.

## 17. Testing configurations using SpEL

Beans and conditions can be tested with the Spring test context. Some cases to include:

- The property is set properly and the expression returns the expected result.
- The property does not exist and the default is applied.
- A malformed property value causes a conversion error.
- A true condition causes the bean to be registered.
- A false condition causes the bean not to be registered.
- A condition combining multiple properties handles each branch properly.
- Bean references in the expression are resolved properly.
- The configuration does not unexpectedly initialize dependent beans too early.

With @ConditionalOnExpression, test both missing properties and malformed Boolean values. Conditions are evaluated when the context initializes, so tests should create an ApplicationContext with a dedicated property set for each case.

Do not only check that a field has a value; also verify whether the bean exists in the context when conditional configuration is used.

## 18. Common mistakes

| Symptom | Common cause | How to handle |
|---|---|---|
| Placeholder is not replaced | Wrong property name or missing property resolver | Check configuration sources and defaults |
| SpEL fails to parse | Missing #{} or invalid expression syntax | Check delimiters and expression |
| Wrong type injected | Result cannot be converted to the field type | Check TypeConverter and target type |
| Null value into primitive | Expression returns null but field is primitive | Provide a default or use a wrapper |
| Bean is not registered | @ConditionalOnExpression returns false | Check property values after resolution |
| Configuration condition causes an error | Final expression is not a valid Boolean | Check expression and value type |
| Bean initialized too early | Condition references another bean | Avoid bean references in conditions |
| Overly complex SpEL in annotations | Business logic hidden in configuration | Move logic to a dedicated bean or Condition |
| Configuration does not update after property changes | Value was already injected when the bean was initialized | Use an appropriate refresh mechanism if needed |

## 19. Key takeaways

Use ${...} to retrieve properties from Environment and #{...} to evaluate SpEL. @Value supports placeholders, SpEL expressions, and combinations of both mechanisms. SpEL can compute values, read properties, call methods, and reference types or beans if EvaluationContext permits.

In Spring Boot, @ConditionalOnExpression uses SpEL to decide whether a configuration or bean is registered. For simple conditions based on a single property, @ConditionalOnProperty is usually clearer. Avoid referencing business beans in conditions as it can cause premature bean initialization.

For large configuration groups, consider @ConfigurationProperties instead of many scattered @Value annotations. Keep expressions in annotations short and readable, specify defaults and target types clearly, and test cases for missing properties, wrong types, and true/false conditions.