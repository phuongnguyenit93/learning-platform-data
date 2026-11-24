# Referencing Beans in Annotations and Configuration with Spring Expression Language (SpEL)

Spring Expression Language (SpEL) allows expressions to directly reference beans managed by the Spring container. Thanks to bean reference syntax, a value in configuration or an annotation can retrieve a property, call a method, or combine data from another bean when Spring evaluates the expression.

For example, the following expression retrieves the defaultCurrency property from the pricingService bean:

~~~text
#{@pricingService.defaultCurrency}
~~~

The @pricingService syntax identifies the bean by name. The .defaultCurrency part accesses the property of that bean. When Spring evaluates the expression in the container environment, a BeanResolver is configured to look up the corresponding bean.

This lesson covers bean reference syntax, how Spring uses SpEL in annotations and XML/Java configuration, how to manually configure EvaluationContext, the difference between SpEL and property placeholders, and common errors when referencing beans.

## 1. What is a bean reference?

A bean reference is how a SpEL expression retrieves a bean from a BeanFactory or ApplicationContext by bean name.

Basic syntax:

~~~text
@beanName
~~~

Examples:

~~~text
@pricingService
@inventoryService
@featureFlags
~~~

These expressions return the container-managed bean object itself. You can continue accessing properties or calling methods:

~~~text
@pricingService.defaultCurrency
@inventoryService.availableQuantity('SKU-100')
@featureFlags.isEnabled('new-checkout')
~~~

In the examples, @pricingService is a bean reference. The .defaultCurrency part or the method call following it is evaluated on that bean.

The bean name must match a name or alias registered in the container. Bean names are case-sensitive. If a bean name contains spaces or special characters, the name can be enclosed in single quotes:

~~~text
@'pricing service'.defaultCurrency
~~~

Using clear bean names makes expressions easier to read and reduces confusion when the application has multiple beans of the same type.

## 2. BeanResolver and how SpEL finds beans

SpEL does not automatically know which ApplicationContext to use from the expression string alone. To resolve bean references, the EvaluationContext must have a BeanResolver.

Spring provides BeanFactoryResolver, a BeanResolver implementation that uses a BeanFactory to look up beans by name.

When the Spring container evaluates SpEL in built-in mechanisms such as @Value, Spring configures an appropriate evaluation environment and provides bean resolution capability. Therefore, @beanName expressions can work without the application manually creating an EvaluationContext.

If creating an EvaluationContext manually in Java code, the resolver must be registered:

~~~java
import org.springframework.beans.factory.BeanFactory;
import org.springframework.context.expression.BeanFactoryResolver;
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

StandardEvaluationContext context = new StandardEvaluationContext();

BeanFactoryResolver beanResolver =
        new BeanFactoryResolver(beanFactory);

context.setBeanResolver(beanResolver);

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("@pricingService.defaultCurrency");

String currency = expression.getValue(context, String.class);
~~~

In the example:

- beanFactory is the BeanFactory or ApplicationContext managing the bean.
- BeanFactoryResolver translates SpEL's bean reference request into a bean lookup operation in the factory.
- setBeanResolver(...) attaches the resolver to the EvaluationContext.
- getValue(context, String.class) evaluates the expression and requests a String result.

Without an appropriate BeanResolver, an expression containing @pricingService cannot resolve the bean and evaluation will fail.

## 3. Referencing beans in the @Value annotation

@Value is one of the most common places where SpEL is used. This annotation lets Spring inject values from properties, system properties, or an evaluated expression.

Example retrieving a property from a bean:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class CheckoutSettings {

    private final String currency;

    public CheckoutSettings(
            @Value("#{ @pricingService.defaultCurrency }")
            String currency) {
        this.currency = currency;
    }

    public String getCurrency() {
        return currency;
    }
}
~~~

Spring evaluates the expression in @Value and passes the result into the constructor parameter. The pricingService bean must exist and be resolvable in the ApplicationContext.

Field injection can be used:

~~~java
@Component
public class CheckoutSettings {

    @Value("#{ @featureFlags.checkoutEnabled }")
    private boolean checkoutEnabled;

    public boolean isCheckoutEnabled() {
        return checkoutEnabled;
    }
}
~~~

Or method/parameter injection:

~~~java
@Component
public class ReportSettings {

    private String currency;

    @Value("#{ @pricingService.defaultCurrency }")
    public void setCurrency(String currency) {
        this.currency = currency;
    }
}
~~~

In these examples, the SpEL expression sits inside #{...}. Only the @ inside the expression is the bean reference symbol. These two syntax layers serve different roles: #{...} marks the expression region to evaluate, while @beanName looks up the bean in the container.

### 3.1. Retrieving a property or calling a bean method

A bean reference can be used to read a property:

~~~java
@Value("#{ @pricingService.defaultCurrency }")
private String currency;
~~~

A method can also be called if that method is accessible and the call fits the context:

~~~java
@Value("#{ @pricingService.defaultTaxRate() }")
private BigDecimal taxRate;
~~~

Literal arguments or other values can be passed into the call:

~~~java
@Value("#{ @pricingService.rateFor('VN') }")
private BigDecimal vietnamRate;
~~~

Do not use @Value to call methods that have side effects or mutate application state. Configuration expressions should produce deterministic, controllable results and not depend on unexpected initialization orders.

## 4. Bean references in XML configuration

In XML bean definitions, attribute values can contain SpEL expressions.

Example:

~~~xml
<bean id="checkoutSettings"
      class="com.example.CheckoutSettings">
    <property name="currency"
              value="#{@pricingService.defaultCurrency}" />
</bean>
~~~

Spring evaluates the expression and injects the result into the currency property of the checkoutSettings bean.

A bean reference can be used to compute a value:

~~~xml
<bean id="shippingPolicy"
      class="com.example.ShippingPolicy">
    <property name="freeShippingThreshold"
              value="#{@pricingService.defaultFreeShippingThreshold()}" />
</bean>
~~~

The expression is evaluated in the bean factory environment. The referenced bean must be present in the same container or resolvable through the configured factory mechanism.

In XML, the # symbol and curly braces must be placed properly inside the value attribute. If the expression contains characters special to XML syntax, escape them according to XML rules.

## 5. Bean references in Java configuration

In Java configuration, Spring usually recommends injecting dependencies directly via @Bean method parameters or constructors. This is a clear approach when one bean needs another bean for initialization.

Example of direct dependency injection:

~~~java
@Configuration
public class CheckoutConfiguration {

    @Bean
    public CheckoutService checkoutService(
            PricingService pricingService) {
        return new CheckoutService(pricingService);
    }
}
~~~

If a parameter needs a value computed via SpEL, @Value can be used on the parameter:

~~~java
@Configuration
public class CheckoutConfiguration {

    @Bean
    public CheckoutSettings checkoutSettings(
            @Value("#{ @pricingService.defaultCurrency }")
            String currency) {
        return new CheckoutSettings(currency);
    }
}
~~~

Here, Spring processes @Value and evaluates the bean reference in the container. The Java method body remains ordinary Java code.

Not every attribute of every annotation is a SpEL expression. Only annotations or attributes documented by Spring or integrating libraries as supporting SpEL are evaluated as expressions. For instance, you cannot arbitrarily place @pricingService into any annotation and expect Spring to resolve it.

## 6. Bean references in Spring Security method annotations

Spring Security supports SpEL in method-protection annotations such as @PreAuthorize and @PostAuthorize. Bean references help invoke a dedicated authorization-checking service.

Example:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    @PreAuthorize("@documentAuthorization.canRead(authentication, #documentId)")
    public Document readDocument(String documentId) {
        // Load and return the document.
        return loadDocument(documentId);
    }
}
~~~

The @documentAuthorization expression references the documentAuthorization bean. The canRead method takes authentication and documentId to decide whether the caller is allowed to read the document.

To use method security, the application must enable the appropriate configuration, for example:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Parameter names such as #documentId must be recognized by Spring Security. Compiler configuration that preserves parameter names or parameter annotations according to the Spring Security version in use keeps variable references stable.

A bean reference can be used in @PostAuthorize to check the return value:

~~~java
@PostAuthorize("@documentAuthorization.canReadResult(returnObject, authentication)")
public Document findDocument(String documentId) {
    return loadDocument(documentId);
}
~~~

Method security is a specific SpEL integration point. Syntax and available variables depend on the annotation type and Spring Security configuration; do not assume all annotations share the same evaluation context.

## 7. Bean references and FactoryBean

A FactoryBean is a special bean that creates another object. When looking up a FactoryBean name normally, the container usually returns the object created by the factory.

If you need to reference the FactoryBean itself, use the & prefix before the bean name:

~~~text
&reportFactory
~~~

In a bean lookup context, this syntax requests the factory bean rather than its product. This is useful when accessing metadata or behavior of the factory.

Distinguish the two objects:

- The bean created by the FactoryBean: the product object normally used by the application.
- The FactoryBean itself: the object responsible for creating the product.

Only use &beanName when the factory itself is actually needed. For regular dependencies, use a bean reference by name or standard dependency injection.

## 8. Distinguishing SpEL and property placeholders

Spring frequently uses two syntaxes that look quite similar but serve different purposes:

| Syntax | Purpose |
|---|---|
| \${property.name} | Retrieves a value from a property source or external configuration |
| #{spelExpression} | Evaluates a SpEL expression |

Placeholder example:

~~~java
@Value("\${app.checkout.currency}")
private String currency;
~~~

SpEL bean reference example:

~~~java
@Value("#{ @pricingService.defaultCurrency }")
private String currency;
~~~

Placeholders retrieve configuration values by key. SpEL evaluates expressions and can access allowed beans, properties, operators, and methods.

The two mechanisms can be combined in some expressions, but keep the boundary clear: placeholders retrieve configuration, whereas SpEL computes or accesses objects via expressions. When a value can vary by environment, externalized properties are usually easier to configure and test than hard-coding bean names in expressions.

## 9. Bean references and regular dependency injection

Bean references in SpEL do not replace all cases of @Autowired or constructor injection.

Use direct dependency injection when a class needs a dependency to perform its functionality:

~~~java
@Service
public class CheckoutService {

    private final PricingService pricingService;

    public CheckoutService(PricingService pricingService) {
        this.pricingService = pricingService;
    }
}
~~~

Use a SpEL bean reference when you need a value computed or retrieved from a bean directly in an expression-supporting location, such as @Value or a method-security annotation.

Practical differences:

- Constructor injection makes dependencies explicit in the constructor signature.
- @Value with SpEL fits configuration values computed from a bean or expression.
- Bean references in security expressions are useful when delegating authorization logic to a dedicated bean.
- Overusing bean references in configuration can make dependencies harder to spot when reading code and harder to detect circular dependencies.

Prefer direct injection for core dependency relationships. Use SpEL where expressions genuinely make configuration or policies easier to express.

## 10. Bean lifecycle and initialization dependencies

A bean reference expression can only be evaluated when the referenced bean can be resolved. If an expression in @Value references a bean that cannot yet be initialized due to a circular dependency, bean creation may fail.

Example of a relationship prone to circular dependencies:

- CheckoutSettings needs pricingService to inject currency.
- PricingService in turn needs CheckoutSettings in its constructor.

Both beans depend on each other during initialization. Using SpEL does not automatically resolve that circular dependency.

When encountering this issue:

1. Identify which bean is referencing which bean.
2. Check whether constructors, fields, setters, and @Value form a cycle.
3. Extract shared configuration into an independent bean if appropriate.
4. Use direct dependency injection when possible so relationships remain observable.
5. Avoid calling methods with side effects in initialization expressions.

Expressions should read values or compute needed results, rather than becoming a hidden mechanism controlling the entire bean lifecycle.

## 11. Common errors when referencing beans

| Error | Cause | Resolution |
|---|---|---|
| Bean not found | Wrong bean name or alias, or bean is not in the evaluating container. | Check the name and ApplicationContext/BeanFactory. |
| Bean reference does not work in manual EvaluationContext | BeanResolver not configured. | Register BeanFactoryResolver. |
| @Value does not evaluate expression | Value is not in expression form or annotation processing is not configured properly. | Check #{...} syntax and container annotation processing. |
| Confusing placeholders with SpEL | Placeholders and SpEL have different purposes. | Use placeholders for property keys, SpEL for expressions. |
| Accessing non-existent property | Bean lacks the property or a matching accessor. | Check getters, property accessors, and property name. |
| Invalid method call | Wrong name, parameters, or return type. | Check method signature and expected result type. |
| Method-security does not recognize parameter | Parameter name not detected or expression uses wrong variable. | Check parameter metadata and Spring Security configuration. |
| Circular dependency at initialization | Beans reference each other in constructors or @Value. | Extract dependencies or change initialization structure. |
| Wrong casing in bean name | Name-based bean lookup does not match. | Use the exact bean name or alias. |
| Assuming all annotations support SpEL | Only certain integration points have expression evaluation mechanisms. | Check documentation for the corresponding annotation and library. |

When diagnosing errors, separate SpEL syntax errors from bean resolution errors and property/method evaluation errors. Inspect the error message, bean name, context in use, and when the expression is evaluated.

## 12. Security notes

Bean references can expose the ability to call methods on beans. If expressions are taken from users or untrusted configuration sources, an overly broad context can allow access to unintended beans or behaviors.

Several principles:

1. Only provide beans necessary for the expression's purpose.
2. Do not arbitrarily evaluate user-submitted SpEL with a full-privilege StandardEvaluationContext.
3. Use SimpleEvaluationContext when the problem fits a restricted feature set, while understanding the capabilities that context permits.
4. With method security, keep authorization logic in dedicated services and validate their inputs.
5. Do not use expressions to bypass the application's authorization boundaries.
6. Avoid allowing expressions to access beans with destructive or state-mutating operations unless necessary.

Bean references are a useful integration mechanism, but actual access depends on the BeanResolver, EvaluationContext, and other enabled capabilities.

## 13. Takeaways

- @beanName references a bean by name in the Spring container.
- Properties can be accessed or methods called after a bean reference.
- BeanFactoryResolver connects SpEL to BeanFactory in a manually created EvaluationContext.
- @Value with #{...} is a common integration point for injecting expression results.
- XML bean definitions can use SpEL in the value attribute.
- Java configuration can use @Value on @Bean method parameters; core dependencies should usually be injected directly.
- Spring Security supports bean references in method-security expressions such as @PreAuthorize.
- &beanName is used when referencing the FactoryBean itself.
- Placeholders in dollar-brace form retrieve properties; #{...} evaluates SpEL.
- Not all annotations support SpEL.
- Check BeanResolver, bean names, initialization lifecycle, and access scope when errors occur.