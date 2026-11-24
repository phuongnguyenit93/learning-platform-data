# SpEL in @Value in Spring Framework

Spring provides the @Value annotation to inject configuration values or the result of an expression into fields, constructor parameters, method parameters, or setters. When the content is written inside curly braces with a hash sign, Spring evaluates it using the Spring Expression Language (SpEL).

For example, the following expression computes a numeric value:

~~~java
@Value("#{2 * T(java.lang.Math).PI}")
private double circleConstant;
~~~

The expression retrieves the PI constant from java.lang.Math and multiplies it by 2. Spring converts the result to the double type of the field.

SpEL in @Value can also read properties, invoke beans, perform calculations, select default values, and create collections. This article presents the syntax, commonly used value types, how to combine it with property placeholders, how Spring performs type conversion, and mistakes to avoid.

## 1. @Value and three forms of values

@Value can receive values in three common ways:

| Form | Example | Meaning |
|---|---|---|
| Literal value | @Value("Spring") | Injects a literal string into the injection point. |
| Property placeholder | @Value("${app.name:Demo}") | Reads a property from external configuration; the part after the colon is the default if the key has no value. |
| SpEL expression | @Value("#{2 * 3}") | Evaluates the SpEL expression and injects the result. |

Example:

~~~java
@Component
public class AppSettings {

    @Value("Spring")
    private String label;

    @Value("${app.name:Demo}")
    private String applicationName;

    @Value("#{2 * 3}")
    private int batchSize;
}
~~~

The delimiters are very important:

- ${...} is the property placeholder syntax.
- #{...} is the SpEL expression syntax.
- A string without either of the two forms above is usually processed as a literal value.

Do not confuse placeholders with SpEL. A placeholder looks up a configuration value by key; SpEL parses and evaluates an expression.

## 2. SpEL syntax in @Value

A SpEL expression in @Value usually has the form:

~~~java
@Value("#{expression}")
private SomeType value;
~~~

The part inside #{...} is the SpEL expression. It can be a literal, an operation, a property access, a method call, a bean reference, or a combination of multiple operations.

Example:

~~~java
@Value("#{10 + 5}")
private int limit;

@Value("#{T(java.lang.Math).max(10, 20)}")
private int maximum;

@Value("#{ 'Hello ' + 'Spring' }")
private String greeting;
~~~

Spring evaluates the expression during dependency injection processing. The result is then supplied to the corresponding field or parameter.

SpEL does not require every expression to return the same type as the injection target. Spring can use ConversionService or the context's conversion mechanism to convert the result to the target type if an appropriate converter is available.

## 3. Injection via constructor, field, and setter

@Value can be used at multiple injection points. Constructor injection usually makes dependencies and configuration explicit right when the object is created.

### 3.1. Constructor parameter

~~~java
@Component
public class CheckoutSettings {

    private final String currency;
    private final int retryLimit;

    public CheckoutSettings(
            @Value("#{ 'VND' }") String currency,
            @Value("#{2 + 3}") int retryLimit) {
        this.currency = currency;
        this.retryLimit = retryLimit;
    }

    public String getCurrency() {
        return currency;
    }

    public int getRetryLimit() {
        return retryLimit;
    }
}
~~~

In the example, Spring evaluates each expression and passes the results to the constructor. The fields are assigned in the constructor and can be declared final.

### 3.2. Field injection

~~~java
@Component
public class FeatureSettings {

    @Value("#{true}")
    private boolean checkoutEnabled;

    @Value("#{100 * 2}")
    private int maximumItems;

    public boolean isCheckoutEnabled() {
        return checkoutEnabled;
    }

    public int getMaximumItems() {
        return maximumItems;
    }
}
~~~

Field injection is concise, but the values are only available after Spring processes the bean. Do not read an injected field inside the bean's own constructor because field injection happens after the constructor runs.

### 3.3. Setter or method parameter

~~~java
@Component
public class ReportSettings {

    private String reportTitle;

    @Value("#{ 'Monthly report' }")
    public void setReportTitle(String reportTitle) {
        this.reportTitle = reportTitle;
    }
}
~~~

Spring evaluates the expression and calls the setter with the result. @Value can be used on parameters of Spring-managed methods, such as a parameter of a @Bean method.

## 4. Property access and operations

SpEL can read properties of the root object or properties provided in the evaluation context. In @Value, Spring prepares a context suited to the integration mechanism.

Some examples:

~~~java
@Value("#{systemProperties['user.language']}")
private String language;

@Value("#{systemEnvironment['JAVA_HOME']}")
private String javaHome;

@Value("#{2 * 60 * 1000}")
private long timeoutMillis;
~~~

Arithmetic, comparison, and logical operators can be combined:

~~~java
@Value("#{10 + 5}")
private int total;

@Value("#{100 > 50}")
private boolean thresholdReached;

@Value("#{true and (5 < 10)}")
private boolean enabled;
~~~

When an expression is long, use parentheses to clarify the order of evaluation. A configuration expression should be short, have clear meaning, and be easy to verify.

## 5. Referencing beans in @Value

SpEL can reference a bean managed by the Spring container using the @ symbol before the bean name.

For example, suppose the application has a pricingService bean with a defaultCurrency property:

~~~java
@Component
public class CheckoutSettings {

    private final String currency;

    public CheckoutSettings(
            @Value("#{ @pricingService.defaultCurrency }")
            String currency) {
        this.currency = currency;
    }
}
~~~

A bean's method can be called if the method is appropriate for the expression:

~~~java
@Value("#{ @pricingService.defaultTaxRate() }")
private BigDecimal taxRate;
~~~

Or pass arguments:

~~~java
@Value("#{ @pricingService.rateFor('VN') }")
private BigDecimal vietnamRate;
~~~

The bean must exist in the ApplicationContext that is processing @Value, and the reference name must match the bean name or alias. If the bean cannot be resolved, expression evaluation will fail.

Do not call methods with side effects inside @Value. Configuration values should produce deterministic results and not mutate application state when the bean is initialized.

## 6. Using static methods and type references

SpEL uses the T(...) operator to reference a Java type. Static constants can then be accessed or static methods called.

Example:

~~~java
@Value("#{T(java.lang.Math).PI}")
private double pi;

@Value("#{T(java.lang.Math).max(12, 30)}")
private int maximum;

@Value("#{T(java.util.Locale).ROOT.toString()}")
private String rootLocale;
~~~

Type references are useful when built-in constants or calculations from Java libraries are needed. Use only the necessary types and methods; configuration expressions should not become a place for complex logic.

If the application needs business logic that can be tested independently, move that logic into a bean/service and reference the bean from the expression or inject the dependency directly.

## 7. Property placeholders and SpEL can be combined

The placeholder ${...} retrieves data from a property source. SpEL #{...} evaluates the result. In Spring environments configured with embedded value resolution, placeholders can be resolved before the SpEL expression is evaluated.

For example, the app.timeout-seconds property provides a number of seconds; the expression multiplies that value by 1000 to produce milliseconds:

~~~java
@Value("#{${app.timeout-seconds:30} * 1000}")
private long timeoutMillis;
~~~

If the property is not declared, the placeholder uses the default of 30. SpEL then performs the multiplication.

A plain placeholder can be used when you only need to retrieve configuration:

~~~java
@Value("${app.name:Demo}")
private String applicationName;
~~~

Use placeholders for environment-dependent values such as URLs, application names, timeouts, or feature configuration. Only add SpEL when you actually need computation or access to other data.

Combined syntax should be tested in the actual application configuration, especially when the property value contains special characters or when the value itself needs to be interpreted as an expression.

## 8. Default values and the Elvis operator

There are two common ways to provide default values.

### 8.1. Property placeholder default

~~~java
@Value("${app.region:unknown}")
private String region;
~~~

If the app.region property is not found or no value is provided by the placeholder mechanism, the part after the colon is the default value.

### 8.2. Elvis operator in SpEL

The Elvis operator ?: chooses the right-hand side when the left-hand side is null or an empty string. If the left-hand side has a valid value, the expression keeps that value.

~~~java
@Value("#{systemProperties['app.region'] ?: 'unknown'}")
private String region;
~~~

Elvis can be used with a bean property:

~~~java
@Value("#{ @applicationSettings.region ?: 'unknown' }")
private String region;
~~~

In the example, if the region property returns null or an empty string, the result is unknown.

Distinguish between the two mechanisms: placeholder defaults handle cases where a property key has no value yet; Elvis handles the value evaluated by SpEL. If you need to distinguish between null, an empty string, and a whitespace-only string, write explicit logic for each case.

## 9. Safe navigation and null handling

When a property might be null, accessing the next property can cause an error. SpEL provides the safe navigation operator ?. to stop the access chain and return null when the object on the left is null.

Example:

~~~java
@Value("#{ @applicationSettings.contact?.email }")
private String contactEmail;
~~~

If contact is null, the expression returns null instead of attempting to access email on null.

It can be combined with Elvis to provide a default:

~~~java
@Value("#{ @applicationSettings.contact?.email ?: 'support@example.com' }")
private String contactEmail;
~~~

Safe navigation only protects the access step to which it is applied. If the expression calls a method or accesses another property that might be null, check each necessary position.

Also distinguish between a null object and a nonexistent bean. Safe navigation does not automatically create a bean or handle every bean resolution failure; bean names must still be resolved by the container according to configuration.

## 10. Inline collections in @Value

SpEL supports creating lists and maps directly inside an expression. This is useful when injecting a fixed set of values.

List example:

~~~java
@Value("#{ {'reader', 'editor', 'admin'} }")
private List<String> roles;
~~~

Map example:

~~~java
@Value("#{ {'maxAttempts': 3, 'enabled': true} }")
private Map<String, Object> options;
~~~

Elements in an inline collection are evaluated according to the type of each expression. For heterogeneous lists or maps, choose an appropriate general target type and avoid assuming all elements have the same type.

Target arrays or collections can be created when the target type and conversion mechanism support it. If the application requires a specific generic type, verify the result and element types rather than relying on unchecked casts.

## 11. Result type conversion

The result of SpEL can be a String, Boolean, number, collection, or object. Spring converts the result to the target type of the field or parameter if an appropriate converter is available.

Example:

~~~java
@Value("#{ '42' }")
private int maximumItems;

@Value("#{ 'true' }")
private boolean enabled;

@Value("#{2 * 60}")
private long timeoutSeconds;
~~~

The examples above require Spring to convert the values to the field types. For complex types, ensure ConversionService has a suitable converter.

Example of injecting a Duration directly from an expression that returns a Duration:

~~~java
@Value("#{T(java.time.Duration).ofSeconds(30)}")
private Duration cacheTtl;
~~~

When types are incompatible or no suitable converter exists, Spring may report an error during bean creation. Verify the actual type of the expression and the target type before deploying.

## 12. Evaluation timing and value stability

@Value is processed while Spring creates and injects the bean. The expression result becomes the value injected into the field or parameter at that time.

Example:

~~~java
@Value("#{T(java.lang.System).currentTimeMillis()}")
private long createdAt;
~~~

The expression is evaluated when the value is injected. The field does not update automatically whenever the time changes.

Similarly, if @Value reads a property from another bean, the result is usually the value retrieved during injection. It does not automatically become a reactive binding to the source bean's property.

If you need an always-fresh value, inject the dependency and call a method when needed, or use a dynamic configuration mechanism suited to your application architecture. Do not use @Value as a mechanism for continuous change tracking.

## 13. Using @Value on @Bean parameters

Java configuration allows Spring to inject values into parameters of @Bean methods:

~~~java
@Configuration
public class ApplicationConfiguration {

    @Bean
    public RetryPolicy retryPolicy(
            @Value("${app.retry-limit:3}") int retryLimit,
            @Value("#{2 * 1000}") long delayMillis) {
        return new RetryPolicy(retryLimit, delayMillis);
    }
}
~~~

Spring resolves placeholders and SpEL and passes the results into the bean factory method. This keeps configuration close to where the bean is declared.

If a bean needs another dependency to perform its function, prefer declaring the dependency directly via a @Bean method parameter or constructor. Use @Value for configuration values or appropriate expression results.

## 14. Common mistakes

| Mistake | Cause | How to handle |
|---|---|---|
| Using a placeholder when calculation is needed | Placeholders only look up properties. | Use #{...} for SpEL expressions. |
| Using #{...} when only reading configuration | The expression makes configuration unnecessarily complex. | Use a placeholder with key and default. |
| Missing curly braces or hash sign | Spring does not recognize the SpEL region properly. | Verify the #{expression} syntax. |
| Bean reference does not exist | Wrong bean name or bean is not in the current context. | Check the bean name, alias, and ApplicationContext. |
| Nested property may be null | Continuing access on null causes an error. | Use safe navigation and an appropriate default. |
| Value cannot be converted | Expression type is incompatible with the target type. | Choose an appropriate literal type or configure a converter. |
| Calling a method with side effects | Bean creation may cause unexpected state changes. | Prefer pure expressions and read-only getters/methods. |
| Expecting the field to update automatically after injection | @Value provides the value at bean processing time. | Inject the dependency and query the value when needed. |
| Using overly long expressions | Logic is hard to read and hard to test. | Move the logic to a dedicated bean or Java code. |
| Passing user-controlled expressions into @Value | May open up unexpected evaluation behavior. | Only use trusted configuration expressions and restrict input sources. |

When diagnosing, distinguish between placeholder resolution errors, SpEL parse errors, expression evaluation errors, bean lookup errors, and type conversion errors. Inspect the exception message and injection point to identify the failing stage.

## 15. Usage principles

1. Use placeholders for environment-based configuration and use SpEL when computation or object access is needed.
2. Prefer constructor injection to make configuration values and dependencies explicit.
3. Use clear bean and property names when referencing beans.
4. Use Elvis or placeholder defaults when a reasonable fallback value exists.
5. Handle null at each level of a property path.
6. Choose a target type compatible with the result and check converters when needed.
7. Keep expressions short and readable; move complex business logic to Java.
8. Do not use @Value to call methods with side effects or perform write operations.
9. Do not evaluate untrusted expressions or expressions concatenated directly from user data.
10. Remember that values are injected during bean processing and do not update continuously.

## 16. Key takeaways

- @Value("#{...}") instructs Spring to evaluate a SpEL expression.
- ${...} is a property placeholder; #{...} is SpEL.
- SpEL in @Value can use literals, operators, properties, methods, bean references, and type references.
- Values can be injected via constructor parameters, fields, setters, or @Bean method parameters.
- The Elvis operator ?: provides a fallback value when the result is null or an empty string.
- Safe navigation ?. helps avoid accessing properties on a null object.
- Inline lists and maps can be created directly inside an expression.
- Spring converts the result to the target type if a suitable converter is available.
- @Value is evaluated during bean injection; fields do not update automatically when the source changes.
- Keep configuration expressions clear, concise, and from trusted sources.
