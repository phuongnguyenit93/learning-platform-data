# SpEL in Bean Constructor Arguments and Properties

Spring Expression Language (SpEL) can be used directly in bean configuration values to compute constructor arguments or property values before Spring creates and configures the object. Instead of passing only a fixed literal, a bean definition can contain an expression such as #{T(java.lang.Math).PI}, read a system property, reference another bean, or combine multiple values.

In Spring, SpEL appears in XML bean definitions, the @Value annotation, and several other configuration integration points. When used in the right place, it makes configuration flexible. However, it is necessary to distinguish expressions from regular bean references, understand when the container evaluates expressions, check the target assignment type, and consider the scope of permissions the expression is allowed to use.

## 1. Objectives and Prerequisites

After this lesson, you can:

- Use SpEL in bean constructor arguments and property values.
- Distinguish value expressions from injecting bean references via `ref`.
- Understand how `#{...}` syntax is processed in XML and `@Value`.
- Combine SpEL with system properties, environment, and bean references.
- Distinguish property placeholders from SpEL.
- Understand type conversion from expression results to constructor/property types.
- Recognize when expressions are evaluated in the bean lifecycle.
- Choose between XML, annotations, and Java configuration.
- Restrict expression sources and capabilities to avoid unsafe configurations.

You should know the Spring IoC container, bean definitions, constructor injection, setter/property injection, ApplicationContext, and basic SpEL syntax.

## 2. SpEL in Bean Definitions

A bean definition describes how Spring creates and configures a bean. In XML, a property value or constructor argument can contain a SpEL expression enclosed by #{ and }.

Example:

~~~xml
<bean id="reportSettings" class="com.example.ReportSettings">
    <property name="maxRows" value="#{100 * 5}" />
    <property name="pi" value="#{T(java.lang.Math).PI}" />
</bean>
~~~

Spring evaluates each expression when resolving bean definition values. The results are used to assign the corresponding properties.

In the example:

- maxRows receives the result of multiplying 100 * 5.
- pi receives the PI constant from the java.lang.Math class.
- The value part is a SpEL expression because it has the #{...} delimiter.

If a value is just a literal string, there is no need to wrap it in SpEL. Only use an expression when you need computation, data access, or dynamic referencing.

## 3. Using SpEL for Constructor Arguments

Constructor injection allows Spring to pass resolved values to a constructor when creating a bean. XML can use expressions in the value attribute of constructor-arg.

~~~xml
<bean id="reportSettings" class="com.example.ReportSettings">
    <constructor-arg value="#{100 * 5}" />
    <constructor-arg value="#{T(java.lang.Math).PI}" />
</bean>
~~~

Example class:

~~~java
public class ReportSettings {
    private final int maxRows;
    private final double pi;

    public ReportSettings(int maxRows, double pi) {
        this.maxRows = maxRows;
        this.pi = pi;
    }
}
~~~

SpEL produces a result for each argument. BeanFactory then converts the result to the constructor parameter type if needed and if the conversion service supports it.

If the constructor has multiple overloads, declare an appropriate index or type in the bean definition when needed to clarify how Spring selects the constructor. Do not rely on implicit conversion to distinguish constructors with very similar signatures.

### 3.1. Passing Values from System Properties

Spring provides system variables in the bean expression context. You can read a system property using systemProperties:

~~~xml
<bean id="clientSettings" class="com.example.ClientSettings">
    <constructor-arg value="#{systemProperties['user.language']}" />
</bean>
~~~

The result is the value of the user.language system property at the time the expression is evaluated. The result type is typically String, matching a constructor that takes a String.

Do not use system properties as a source of security data or business data that can change without control. Clearly identify the configuration source and default value if the property might not exist.

## 4. Using SpEL for Property Values

With setter/property injection, the expression is placed in the value attribute of the property element:

~~~xml
<bean id="featureSettings" class="com.example.FeatureSettings">
    <property name="enabled" value="#{true}" />
    <property name="retryCount" value="#{3 + 2}" />
    <property name="description" value="#{'Default configuration'}" />
</bean>
~~~

Spring evaluates the expression and assigns the result to the corresponding property. If the result type does not yet match the property, BeanFactory can use TypeConverter or ConversionService to convert it.

Example class:

~~~java
public class FeatureSettings {
    private boolean enabled;
    private int retryCount;
    private String description;

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public void setRetryCount(int retryCount) {
        this.retryCount = retryCount;
    }

    public void setDescription(String description) {
        this.description = description;
    }
}
~~~

The property must have an appropriate write mechanism. With standard JavaBeans, setters are the common way. If a property only has a getter or the object is immutable, assignment via property injection may not be suitable; use constructor injection or a factory that creates the complete object.

## 5. Referencing Other Beans in Constructor/Property Expressions

SpEL can retrieve a bean from the Spring container using the @beanName syntax, then read a property or call a method if the context allows it.

XML example:

~~~xml
<bean id="endpointSettings" class="com.example.EndpointSettings">
    <property name="baseUrl" value="#{@endpointProvider.defaultUrl}" />
</bean>
~~~

Here:

1. BeanResolver looks up the endpointProvider bean in BeanFactory.
2. SpEL reads the defaultUrl property on that bean.
3. The result is assigned to the baseUrl property of endpointSettings.

Methods can also be called:

~~~xml
<bean id="messageSettings" class="com.example.MessageSettings">
    <property name="welcomeMessage"
              value="#{@messageFactory.createWelcomeMessage()}" />
</bean>
~~~

Only use an expression when you need to compute or retrieve a value from another bean. If the goal is just to inject that bean itself into the property, using `ref` is clearer:

~~~xml
<property name="messageFactory" ref="messageFactory" />
~~~

Similarly, for a constructor argument that only needs a bean reference, use `constructor-arg ref` instead of an expression. Declaring `ref` expresses a direct dependency and helps the container track dependency relationships more clearly.

## 6. Distinguishing Value Expressions from Bean References

XML bean definitions have several ways to pass values:

| Need | Declaration |
|---|---|
| Pass a literal | value="ACTIVE" |
| Evaluate SpEL | value="#{...}" |
| Inject a bean reference | ref="someBean" |
| Inject via expression to read a property/compute | value="#{@someBean.someProperty}" |

Example:

~~~xml
<bean id="serviceSettings" class="com.example.ServiceSettings">
    <property name="mode" value="SAFE" />
    <property name="timeout" value="#{30 * 1000}" />
    <property name="policy" ref="accessPolicy" />
    <property name="policyName" value="#{@accessPolicy.name}" />
</bean>
~~~

policy receives the accessPolicy object. policyName receives a value read from that bean. The two properties can have different types and serve two different purposes.

Do not use an expression just to replace a simple `ref`. An expression adds a resolution step and can make dependencies harder to spot when reading bean definitions.

## 7. Distinguishing Property Placeholders from SpEL

Spring typically uses two different configuration syntax forms:

- Property placeholder: a dollar sign followed by curly braces.
- SpEL expression: a hash sign followed by curly braces.

Placeholders retrieve values from property sources, such as application.properties, environment variables, or configuration sources registered with Spring.

SpEL evaluates an expression and can perform operations, access properties, reference beans, or call permitted methods.

A placeholder example in an annotation can be written with a Java string constant:

~~~java
@Value("$" + "{app.name}")
private String appName;
~~~

SpEL example:

~~~java
@Value("#{T(java.lang.Math).PI}")
private double pi;
~~~

Placeholders can be combined inside SpEL when the application has placeholder processing configured. The placeholder is resolved into a configuration value before SpEL evaluates the expression part. Nested syntax must maintain proper quotes and delimiters; if no computation is needed, using a placeholder directly is simpler.

Do not confuse placeholders with SpEL. A placeholder substitutes a configuration value; SpEL evaluates an expression.

## 8. Using @Value on Fields, Setters, and Constructor Parameters

The @Value annotation allows using SpEL in Spring-supported injection points.

### 8.1. Field Injection

~~~java
@Component
public class MathSettings {

    @Value("#{T(java.lang.Math).PI}")
    private double pi;
}
~~~

Spring evaluates the expression and converts the result to the field type if needed.

### 8.2. Setter Injection

~~~java
@Component
public class RetrySettings {
    private int retryCount;

    @Value("#{2 + 3}")
    public void setRetryCount(int retryCount) {
        this.retryCount = retryCount;
    }
}
~~~

### 8.3. Constructor Parameters

~~~java
@Component
public class ReportService {

    private final int maxRows;

    public ReportService(
            @Value("#{100 * 5}") int maxRows) {
        this.maxRows = maxRows;
    }
}
~~~

Constructor parameters are suitable when the value is a required dependency and the object should be created in a complete state. For configurations with many related fields, consider a configuration properties object instead of many scattered expressions.

## 9. Using SpEL in Java Configuration

In Java configuration, `@Value` can be used on parameters of `@Bean` methods:

~~~java
@Configuration
public class AppConfig {

    @Bean
    public ReportSettings reportSettings(
            @Value("#{100 * 5}") int maxRows,
            @Value("#{T(java.lang.Math).PI}") double pi) {
        return new ReportSettings(maxRows, pi);
    }
}
~~~

Spring resolves `@Value` parameters before invoking the bean creation method. The Java method itself remains responsible for creating the object and can apply clear validation or default logic.

If a value only needs to be injected directly from another bean, you can declare a bean parameter in the `@Bean` method:

~~~java
@Bean
public ReportService reportService(AccessPolicy accessPolicy) {
    return new ReportService(accessPolicy);
}
~~~

This approach is usually clearer than using SpEL to retrieve a bean reference and pass it along.

## 10. Bean Expression Context and Evaluation Timing

In a typical ApplicationContext, Spring integrates a BeanExpressionResolver to evaluate expressions in bean definitions and configuration points that support SpEL. StandardBeanExpressionResolver is the standard resolver.

This context is connected to BeanFactory and provides capabilities such as:

- Referencing beans with @beanName.
- Accessing systemProperties and systemEnvironment.
- Accessing the environment according to Spring configuration.
- Reading properties on the object provided as the root.
- Using type conversion according to the container's configuration.

When a bean definition is resolved to create a bean, the expression value is evaluated while the container prepares arguments/properties. With singleton scope, bean creation typically happens once during the ApplicationContext lifecycle; with prototype scope, bean creation happens each time the container creates an instance. The specific scope and lifecycle affect when values are resolved.

Do not assume every expression is evaluated exactly once at application startup. Consider the bean scope, how instances are created, and the data source the expression reads.

## 11. Configuring BeanExpressionResolver When Creating BeanFactory Manually

When using a standard ApplicationContext, Spring typically configures the required resolver. If you create a standalone BeanFactory or customize how the container initializes, ensure a bean expression resolver is installed.

Illustrative example:

~~~java
DefaultListableBeanFactory beanFactory =
    new DefaultListableBeanFactory();

beanFactory.setBeanExpressionResolver(
    new StandardBeanExpressionResolver()
);
~~~

In a real application, you must connect the resolver with the appropriate class loader, bean factory, and conversion components. Do not create an isolated resolver and assume it automatically knows all beans or the application environment.

When using GenericApplicationContext or AnnotationConfigApplicationContext, prefer the standard context lifecycle so Spring configures the integrated components. Only customize BeanExpressionResolver when there is a specific requirement and you understand the impact on all bean definitions.

## 12. Converting Result Types to Constructor/Property Types

An expression can return a type different from the target constructor parameter or property type. BeanFactory uses the container's TypeConverter and ConversionService to convert it if a suitable converter exists.

Example of an expression returning a number:

~~~xml
<property name="retryCount" value="#{2 + 3}" />
~~~

If retryCount has type int, the result can be assigned directly or converted via the type conversion mechanism.

Distinguish between:

1. Does the expression evaluate successfully?
2. Can the result be converted to the target type?
3. Does the setter or constructor accept the value according to business rules?

Successful type conversion does not guarantee a valid value. For example, retryCount equal to -1 is still a valid int, but it may violate application rules.

For dates, times, currencies, enums, or domain types, configure ConversionService explicitly and validate the data. Do not rely on the server's default format.

## 13. Handling Null Values and Defaults

An expression can return null if the source variable/property is null or a bean method returns null. When the result is used as a constructor argument or property value, you need to know whether the target accepts null.

You can use Elvis to provide a default value:

~~~xml
<property name="displayName"
          value="#{@profileProvider.displayName ?: 'Guest'}" />
~~~

Or use safe navigation:

~~~xml
<property name="city"
          value="#{@customerProvider.currentCustomer?.address?.city}" />
~~~

Safe navigation returns null when the receiver at a guarded link in the chain is null. If the target property does not accept null, provide a default or validate before creating the bean.

Do not apply defaults mechanically. For required configuration such as secrets, endpoints, or database names, a missing value should fail startup with a clear message rather than silently falling back to an unsafe value.

## 14. Referencing Static Fields and Static Methods

SpEL can use T(...) in bean definitions to read static fields or call static methods.

Example:

~~~xml
<property name="pi" value="#{T(java.lang.Math).PI}" />
<property name="maxConnections"
          value="#{T(java.lang.Math).max(10, 20)}" />
~~~

T(...) uses the evaluation context's TypeLocator to resolve the class. SpEL then accesses static members through the corresponding property/method mechanism.

Use static members for constants or pure, simple calculations. Do not use expressions to call static APIs with side effects or access system resources in configuration unless truly necessary.

## 15. When to Use SpEL vs. Typed Configuration?

SpEL is useful when you need to compute a short value from existing sources:

- Computing a constant.
- Selecting a value from a system property or environment.
- Reading a property from a managed bean.
- Combining a few configuration values.
- Providing a simple default.

Typed configuration properties or Java configuration should be used when:

- There are many related configuration fields.
- Complex validation is needed.
- Binding large lists or maps is needed.
- Profiles, metadata, and configuration documentation support are needed.
- Type, unit, range, or format control is needed.
- Calculation logic is long or has multiple branches.

Do not turn bean definitions into a container for entire business rules. Long expressions are hard to debug, hard to test, and obscure dependencies between beans.

## 16. Security and Reliability of Expressions in Configuration

Bean definitions normally come from source code or configurations controlled by the development team. However, if the application allows users or tenants to upload configurations containing SpEL, expressions can access many capabilities of the EvaluationContext.

Risks include:

- Calling methods on referenced beans.
- Accessing static methods through T(...).
- Creating objects via constructors if that capability is granted.
- Reading properties or calling methods on the root object.
- Triggering side effects if an expression calls APIs with side effects.

Do not evaluate untrusted expressions with a broad context. If administrator-configured expressions are required, put a validate, review, approve, and publish process in place; restrict the beans, types, methods, and properties allowed to be accessed.

If only data configuration is needed, prefer property placeholders and configuration properties. Do not allow arbitrary expressions just to vary a simple value.

## 17. Common Errors and Troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| Value #{...} is not evaluated | BeanExpressionResolver is not configured or syntax is wrong | Check ApplicationContext/BeanFactory and delimiters |
| Bean not found in @beanName | Wrong bean name or resolver does not have that bean | Check the bean name and context |
| Unexpected constructor selected | Multiple overloads and ambiguous argument types | Declare index/type or use clear constructors |
| Property injection fails | Missing setter or property is not writable | Check JavaBean property or use constructor |
| Conversion error | Expression result cannot be converted to target type | Check TypeConverter/ConversionService and result type |
| Null value causes bean creation failure | Constructor/property does not accept null | Use a suitable default or fail-fast validation |
| Placeholder is not resolved | Property placeholder processor not configured or wrong key | Check PropertySourcesPlaceholderConfigurer and property source |
| Expression runs at unexpected time | Bean scope or lifecycle differs from assumption | Check singleton/prototype and instance creation timing |
| Dependency cycle when referencing bean | Expression fetches another bean during init causing a cycle | Use direct dependency injection or restructure the bean graph |
| Configuration can invoke unintended methods | Untrusted expression source or overly broad context | Restrict expression sources and EvaluationContext |

When debugging, check in order: whether the bean definition is loaded, whether the expression is parsed, whether BeanResolver finds the bean, whether the expression returns the right type, whether conversion succeeds, and whether the constructor/setter accepts the value.

## 18. Practice Exercises

1. Create a bean with a constructor taking `int` and `double`; pass both values using SpEL in `constructor-arg`.
2. Use SpEL in a property value to compute `retryCount` and read `Math.PI`.
3. Create a provider bean with a `defaultUrl` property and reference that property using `@beanName`.
4. Compare `property ref` with a value expression when injecting a bean.
5. Use `@Value` on a field, setter, and constructor parameter.
6. Combine a placeholder with SpEL to fetch a configuration value and transform it.
7. Create a target property of type enum or `BigDecimal` and verify conversion.
8. Test a property expression returning `null` against nullable and non-nullable target properties.
9. Create a prototype bean with an expression reading runtime data and observe resolution timing.
10. Inspect the error when an expression references a nonexistent bean or creates a dependency cycle.

## 19. Checklist Before Using SpEL in Bean Definitions

- [ ] Is an expression truly needed, or is a literal/ref/placeholder enough?
- [ ] Is the correct #{...} syntax used?
- [ ] Is SpEL distinguished from property placeholders?
- [ ] Does the target constructor/property have a compatible type and accept the value?
- [ ] Are there constructor overloads causing ambiguity?
- [ ] Would a direct `ref` bean reference be clearer?
- [ ] Does the referenced bean exist and avoid dependency cycles?
- [ ] Have the bean scope and expression evaluation timing been determined?
- [ ] Are null and defaults aligned with business rules?
- [ ] Does ConversionService support the target type and expected format?
- [ ] Does the expression come from a trusted source?
- [ ] Does EvaluationContext expose broader capabilities than needed?
- [ ] Is the logic short enough to read and maintain?

## 20. Conclusion

SpEL can be used in bean constructor arguments and property values via the `#{...}` expression delimiter. Spring evaluates the expression in the bean expression context and converts the result to the target type if needed. Use SpEL for short calculations, reading configuration, or retrieving a property from another bean; use `ref` for direct dependencies and placeholders for simple configuration values. Understand the bean lifecycle, handle null/conversion explicitly, and only evaluate expressions from trusted sources with an appropriately scoped context.