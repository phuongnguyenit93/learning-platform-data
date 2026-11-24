# SpEL in Java Configuration

## 1. Where Is SpEL Used in Java Configuration?

Spring Java configuration uses classes annotated with @Configuration and @Bean methods to declare objects managed by the IoC container.

SpEL can participate in bean configuration when Spring processes metadata or an injection point that supports expressions. In Java configuration, the common approach is placing @Value on a field, setter, constructor parameter, or parameter of a Spring-managed method.

Example:

    @Configuration
    public class PricingConfiguration {

        @Bean
        public PricingPolicy pricingPolicy(
                @Value("#{systemProperties['pricing.region'] ?: 'VN'}")
                String region) {

            return new PricingPolicy(region);
        }
    }

Spring evaluates the expression in @Value, converts the result to the parameter type if needed, and then calls the pricingPolicy method to create the bean.

SpEL is processed by Spring at places where the container knows it needs to resolve values. Arbitrary Java strings or @Bean method bodies are not automatically scanned for #{...}.

## 2. What Do @Configuration and @Bean Do?

@Configuration marks a class as a source of bean definitions. @Bean marks a method that creates an object which Spring registers and manages in the ApplicationContext.

Example:

    @Configuration
    public class AppConfiguration {

        @Bean
        public CurrencyFormatter currencyFormatter() {
            return new CurrencyFormatter();
        }

        @Bean
        public InvoiceService invoiceService(
                CurrencyFormatter formatter) {
            return new InvoiceService(formatter);
        }
    }

In this example, Spring invokes the factory methods and manages the returned objects. The `formatter` parameter is resolved as a dependency of the `invoiceService` bean.

SpEL does not replace this dependency injection mechanism. If a @Bean method needs another bean as a dependency, declaring a parameter by bean type is usually clearer and safer than writing an expression to look up the bean by name.

SpEL is suitable when the injected value must be computed from properties, system properties, the environment, or another bean.

## 3. Using @Value with SpEL in @Bean Method Parameters

A @Bean method can accept parameters annotated with @Value.

Example:

    @Configuration
    public class PricingConfiguration {

        @Bean
        public PricingPolicy pricingPolicy(
                @Value("#{systemProperties['pricing.region'] ?: 'VN'}")
                String region,
                @Value("#{T(java.lang.Math).max(1, 5)}")
                int minimumTier) {

            return new PricingPolicy(region, minimumTier);
        }
    }

Spring processes each @Value parameter before calling the method:

- region receives the `pricing.region` system property if it has a value.
- If the property is null or an empty string, Elvis selects `VN`.
- minimumTier receives the result of the Math.max expression.
- Values are converted to the corresponding parameter types if conversion is supported.

This combines a Java factory method with values computed via SpEL. The method body remains normal Java code.

## 4. Using @Value on Fields, Setters, and Constructors

SpEL in Java configuration is not limited to @Bean method parameters. The @Value annotation can also be placed on fields, setters, method parameters, and constructor parameters of beans created by Spring.

Field example:

    @Component
    public class RegionSettings {

        @Value("#{systemProperties['user.region'] ?: 'VN'}")
        private String region;
    }

Setter example:

    @Component
    public class LocaleSettings {

        private String locale;

        @Value("#{systemProperties['user.language'] ?: 'en'}")
        public void setLocale(String locale) {
            this.locale = locale;
        }
    }

Constructor parameter example:

    @Component
    public class CatalogService {

        private final String catalogName;

        public CatalogService(
                @Value("#{environment.getProperty('catalog.name') ?: 'default'}")
                String catalogName) {
            this.catalogName = catalogName;
        }
    }

Spring must manage the object and have the corresponding annotation processing mechanism active for @Value to be applied. If you instantiate an object manually with `new` in Java, Spring does not automatically run annotation injection on that object.

## 5. Distinguishing Property Placeholders ${...} from SpEL #{...}

In Java configuration, the two forms often appear together in @Value but have different responsibilities.

| Syntax | Mechanism | Purpose |
| --- | --- | --- |
| ${app.currency} | Property placeholder resolution | Read a configuration value by key |
| ${app.currency:VND} | Placeholder with default | Use VND if the property is not declared |
| #{systemProperties['user.region']} | SpEL evaluation | Read a system property via expression |
| #{T(java.lang.Math).max(1, 5)} | SpEL evaluation | Compute a value via expression |
| #{pricingPolicy.defaultCurrency} | SpEL in bean-definition context | Read a property of another bean |

Placeholder example:

    @Value("${app.currency:VND}")
    private String currency;

Spring looks up the `app.currency` property. If no value is present, the placeholder uses the default `VND`.

SpEL example:

    @Value("#{systemProperties['user.region'] ?: 'VN'}")
    private String region;

Spring evaluates the expression, reads the system property, and chooses the default using Elvis.

Placeholder resolution and SpEL evaluation are two separate steps. Placeholders are used to retrieve configuration values; SpEL is used to compute or access objects using an expression language.

## 6. Combining Placeholders and SpEL Appropriately

One injection point can use @Value with SpEL to produce a dynamic value, while property placeholders continue to be used at other injection points.

Example:

    @Configuration
    public class CheckoutConfiguration {

        @Bean
        public CheckoutPolicy checkoutPolicy(
                @Value("${checkout.currency:VND}")
                String currency,
                @Value("#{T(java.lang.Math).max(0, 3)}")
                int retryLimit) {

            return new CheckoutPolicy(currency, retryLimit);
        }
    }

Here `currency` comes from the property source, while `retryLimit` is the result of an expression.

Do not put all configuration into a long expression just because SpEL can compute it. Use placeholders for simple configuration values and use SpEL when an expression is truly needed.

If an expression needs to use an already-resolved property, clearly determine the order and processing mechanism of the injection point. Avoid nesting multiple levels of placeholders and expressions if a separate Java parameter makes the logic clearer.

## 7. Accessing System Properties and Environment

In Spring's bean-definition expression context, several objects are provided out of the box under familiar names, including `environment`, `systemProperties`, and `systemEnvironment`.

Example reading a system property:

    @Value("#{systemProperties['user.region']}")
    private String region;

Example reading environment:

    @Value("#{environment.getProperty('app.region') ?: 'VN'}")
    private String region;

Example reading an environment variable:

    @Value("#{systemEnvironment['APP_REGION'] ?: 'VN'}")
    private String region;

These expressions are evaluated by Spring inside the container's context. There is no need to create a StandardEvaluationContext manually just to use these predefined variables in @Value.

If you create SpelExpressionParser and StandardEvaluationContext manually in Java code, the predefined variables of the bean-definition context do not appear automatically. In that case, you must provide the required root object, variables, or resolvers yourself.

## 8. Referencing Other Beans in Java Configuration

Spring allows expressions in the bean-definition context to reference properties of other beans by bean name.

Example:

    @Component
    public class NumberGuess {
        public double getRandomNumber() {
            return 42.0;
        }
    }

    @Component
    public class ShapeGuess {

        private double initialShapeSeed;

        @Value("#{numberGuess.randomNumber}")
        public void setInitialShapeSeed(double value) {
            this.initialShapeSeed = value;
        }
    }

In the bean-definition processing context, beans in the ApplicationContext are provided as predefined variables by bean name. Therefore, the expression uses `numberGuess.randomNumber`.

This is the syntax of Spring's bean-definition evaluation context. Do not confuse it with any standalone EvaluationContext.

If you create a StandardEvaluationContext manually and want to use bean references with the `@beanName` syntax, you need to register an appropriate BeanResolver, such as BeanFactoryResolver. A standalone context does not automatically know about the application's ApplicationContext.

When you only need a dependency between two beans, prefer declaring the dependency via a constructor or `@Bean` method parameter. Use SpEL bean references when you need to fetch a value or compute something in metadata.

## 9. Producing Values with Operations and Static Methods

SpEL can perform operations or call static methods to produce injected values.

Example:

    @Value("#{T(java.lang.Math).max(10, 20)}")
    private int threshold;

Random number example:

    @Value("#{T(java.lang.Math).random() * 100.0}")
    private double initialSeed;

String concatenation example:

    @Value("#{systemProperties['user.name'] + '-service'}")
    private String serviceLabel;

The expression is evaluated when Spring processes the injection point. For singleton beans, the injected value is typically retained on that instance; it does not recompute every time the field is read.

If you need a value that changes per request or on every call, place the computation in a method/service with an appropriate lifecycle rather than expecting @Value to continuously refresh.

## 10. Injecting Inline Collections and Data Structures

SpEL can create inline Lists or Maps to inject into fields or parameters.

Map example:

    @Component
    public class CatalogSettings {

        private final Map<String, Integer> counts;

        public CatalogSettings(
                @Value("#{{'Thriller': 100, 'Comedy': 300}}")
                Map<String, Integer> counts) {
            this.counts = counts;
        }
    }

The expression creates a Map containing two entries. Spring converts the result to the `Map<String, Integer>` parameter type using appropriate conversion.

List example:

    @Bean
    public FeaturePolicy featurePolicy(
            @Value("#{{'search', 'checkout', 'profile'}}")
            List<String> enabledFeatures) {

        return new FeaturePolicy(enabledFeatures);
    }

Inline collection syntax inside @Value can have multiple pairs of curly braces: the outer pair is for the SpEL delimiter in the annotation, and the inner part is SpEL's collection syntax.

Check the target type and generic types when injecting collections. Do not use an empty List in place of an empty Map or vice versa.

## 11. SpEL in Java Configuration vs. Java Method Bodies

A common misconception is thinking that any string containing `#{...}` in a @Configuration class is automatically evaluated.

Example:

    @Configuration
    public class AppConfiguration {

        @Bean
        public String greeting() {
            String value = "#{systemProperties['user.name']}";
            return value;
        }
    }

The method above returns the literal string `#{systemProperties['user.name']}`. Spring does not automatically parse every String created in a method body.

To use SpEL at an injection point, use @Value:

    @Bean
    public Greeting greeting(
            @Value("#{systemProperties['user.name']}")
            String userName) {

        return new Greeting(userName);
    }

Or if you need to evaluate an expression explicitly in Java code, invoke ExpressionParser and provide an appropriate EvaluationContext:

    ExpressionParser parser =
        new SpelExpressionParser();

    Expression expression =
        parser.parseExpression(
            "T(java.lang.Math).max(10, 20)"
        );

    Integer result =
        expression.getValue(Integer.class);

This is the application explicitly calling the SpEL API, which differs from Spring processing @Value.

## 12. Bean Definition Expressions and @beanName Syntax

In Spring's bean-definition evaluation context, beans are provided as predefined variables by bean name. Therefore, Spring documentation uses the form:

    #{numberGuess.randomNumber}

This is not the same context as an expression evaluated with a standalone StandardEvaluationContext.

In a SpEL context with a BeanResolver, the general bean reference syntax is:

    @numberGuess.randomNumber

Example of configuring a standalone context:

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setBeanResolver(
        new BeanFactoryResolver(applicationContext)
    );

    Expression expression =
        parser.parseExpression(
            "@numberGuess.randomNumber"
        );

The two forms serve two different resolution environments. When writing @Value in Java configuration, use bean-definition expression syntax as documented by Spring, such as `#{numberGuess.randomNumber}`.

## 13. Configuring PropertySourcesPlaceholderConfigurer

Property placeholders are used to resolve values of the form `${...}`. When an application needs strict control over missing placeholders, a PropertySourcesPlaceholderConfigurer can be registered.

Example:

    @Configuration
    @PropertySource("classpath:application.properties")
    public class AppConfiguration {

        @Bean
        public static PropertySourcesPlaceholderConfigurer
                propertySourcesPlaceholderConfigurer() {

            return new PropertySourcesPlaceholderConfigurer();
        }
    }

In Java configuration, the method creating PropertySourcesPlaceholderConfigurer should be static so the bean factory post-processor is registered at the right time during container initialization.

This configurer helps Spring process property placeholders from registered property sources and can cause initialization to fail when a required placeholder cannot be resolved.

Placeholder configuration and SpEL are two coordinating yet separate parts. PropertySourcesPlaceholderConfigurer handles placeholders; BeanExpressionResolver handles SpEL expressions in bean metadata.

## 14. @Value vs. @ConfigurationProperties

@Value is suitable when injecting a single value or expression into a field, setter, or parameter.

When there is a large, structured group of configuration settings requiring typed binding, @ConfigurationProperties is usually more suitable.

| Need | Suitable Approach |
| --- | --- |
| A single value | @Value |
| A value computed with SpEL | @Value with #{...} |
| Reading a property with a default | @Value with ${key:default} |
| Configuration group with many fields | @ConfigurationProperties |
| Typed configuration binding | @ConfigurationProperties |
| Accessing another bean to compute a value | SpEL at the injection point if truly needed |

Do not use SpEL to replace the entire externalized configuration mechanism. SpEL is an expression language; @ConfigurationProperties and Environment are dedicated configuration management mechanisms.

In addition, a value stored in application.properties is not automatically evaluated as SpEL merely because it contains the string `#{...}`. SpEL is processed at injection points or where the application explicitly invokes the expression engine.

## 15. Evaluation Timing and Bean Lifecycle

Spring evaluates expressions when processing bean metadata or injection points during bean creation.

Example:

    @Component
    public class FeatureSettings {

        @Value("#{systemProperties['feature.mode'] ?: 'safe'}")
        private String mode;
    }

When Spring creates FeatureSettings and processes @Value, the expression is evaluated and the resulting value is assigned to the field.

With singleton beans, the field retains the injected value throughout the instance's lifecycle. Changing the system property afterward does not automatically update the field.

If you need to read fresh values over time, consider reading from Environment inside a method, using an appropriate refresh mechanism, or designing the bean with a scope/lifecycle that meets the requirement.

Do not put expressions with side effects or unstable results into @Value if the application expects a fixed, predictable value.

## 16. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| @Value injects literal #{...} | Annotation processing is inactive or object is not Spring-managed | Check ApplicationContext and annotation config processing |
| Placeholder ${...} does not resolve | Missing property source or unsuitable placeholder configurer | Check @PropertySource, Environment, and configurer |
| SpEL cannot find bean | Wrong bean name or expression runs in a different context | Check bean-definition context or BeanResolver |
| Using @beanName in @Value does not work as expected | Confusing bean-definition expression with standalone StandardEvaluationContext | Use bean name as predefined variable in bean-definition expressions |
| Cannot convert parameter type | Expression result is incompatible with target type | Check the value and ConversionService |
| Expression returns null | Property or system/environment key does not exist | Use an intentional default and inspect the property source |
| @Bean method returns literal string #{...} | Java method body is not automatically parsed | Use @Value or call the SpEL API explicitly |
| Circular dependency when referencing another bean | Expression creates a reverse dependency during initialization | Prefer explicit constructor/method injection and review the dependency graph |
| Value does not change after configuration update | @Value was injected when the bean was created | Use a refresh mechanism or read Environment as needed |

When debugging, determine whether the error occurs during placeholder resolution, SpEL parsing, expression evaluation, type conversion, or bean creation. These steps have different error messages and causes.

## 17. Security and Maintainability

Expressions in Java configuration normally reside in source code controlled by the application. However, SpEL can read beans, properties, and call methods according to the evaluation context's permissions.

Some principles:

- Do not concatenate untrusted input into @Value expressions.
- Do not put secrets into expression literals.
- Keep expressions short and focused on computing configuration values.
- Prefer dependency injection via constructor or @Bean method parameters for normal bean relationships.
- Do not create dependency cycles between beans through expressions.
- Do not call methods with side effects in configuration expressions if they can be handled cleanly in Java code.
- Use @ConfigurationProperties for complex configuration groups instead of building one large expression.
- When evaluating SpEL manually in Java, configure EvaluationContext according to least privilege.

If rules or expressions can be edited by users, do not evaluate them with a context that has broad access just because the application happens to use SpEL in @Value.

## 18. Key Takeaways

- Java configuration uses @Configuration and @Bean to declare Spring-managed beans.
- SpEL is commonly used in Java configuration via @Value on fields, setters, methods, or constructor parameters.
- @Value can also be used on parameters of @Bean methods.
- `#{...}` is SpEL syntax in bean-definition expressions.
- `${...}` is a property placeholder; the two mechanisms have different responsibilities.
- Spring's bean-definition context provides beans by name as predefined variables, e.g., `#{numberGuess.randomNumber}`.
- A standalone StandardEvaluationContext requires a BeanResolver to use `@beanName` syntax.
- System properties, system environment, and Environment can be accessed in the bean-definition expression context.
- Operations, static methods, Elvis, and inline Lists and Maps can be used to produce injected values.
- `@Bean` method bodies and ordinary Java Strings are not automatically parsed as SpEL.
- Spring processes `@Value` during bean creation; injected values do not automatically refresh on each read.
- Use `@ConfigurationProperties` for large configuration groups and explicit dependency injection for ordinary bean relationships.
- Do not evaluate untrusted expressions in a context with broad permissions.

When using SpEL in Java configuration, place expressions at the exact injection points supported by Spring, distinguish placeholders from expressions, and keep bean creation in Java code readable. SpEL should complement dependency injection and externalized configuration, not replace them.

## References

- Spring Framework Reference — Expressions in Bean Definitions: https://docs.spring.io/spring-framework/reference/core/expressions/beandef.html
- Spring Framework Reference — Using @Value: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html
- Spring Framework Reference — Java-based Container Configuration: https://docs.spring.io/spring-framework/reference/core/beans/java.html
- Spring Framework Reference — Externalized Configuration: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
