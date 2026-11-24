# Accessing Properties of a Spring Bean

## 1. What is a bean reference in SpEL?

Spring Expression Language (SpEL) can access objects managed by the Spring IoC container through a **bean reference**. The syntax uses the @ symbol before the bean name:

    @beanName

After retrieving the bean, the expression can read properties, access nested properties, or call methods on that bean.

Example:

    @pricingSettings.defaultCurrency

The expression above tells SpEL to look up the bean named pricingSettings, then read the defaultCurrency property of the bean.

These are two separate steps:

1. BeanResolver finds the bean in the Spring BeanFactory.
2. PropertyAccessor accesses the property on the returned object.

Therefore, bean references and property access work together, but they are not the same mechanism.

## 2. Distinguishing bean references, variables, and the root object

SpEL has multiple ways to determine the starting object for a path:

| Notation | Meaning |
| --- | --- |
| customer.name | Reads the name property from the root object |
| #customer.name | Reads the customer variable in EvaluationContext and then gets name |
| @customerService.name | Finds the bean named customerService in the Spring container and then reads name |

All three forms can point to objects of the same type, but the source providing the object is different.

Root object example:

    StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

    Expression expression =
        parser.parseExpression("name");

Variable example:

    context.setVariable("customer", customer);

    Expression expression =
        parser.parseExpression("#customer.name");

Bean reference example:

    Expression expression =
        parser.parseExpression("@customerService.serviceName");

Do not use @ just to access any object. Only use @ when the object to retrieve is a bean registered in the BeanFactory. If the object is passed in per evaluation, the root object or a variable is usually more appropriate.

## 3. Syntax for accessing beans and properties

Basic syntax:

    @beanName.propertyName

Examples:

    @applicationSettings.applicationName
    @applicationSettings.defaultLocale
    @featureFlags.checkoutEnabled

SpEL finds the bean by name, then uses the property access mechanism to read the corresponding value.

For standard JavaBeans, properties are exposed via getters:

    public class ApplicationSettings {
        private String applicationName;
        private String defaultLocale;

        public String getApplicationName() {
            return applicationName;
        }

        public String getDefaultLocale() {
            return defaultLocale;
        }
    }

When the expression reads:

    @applicationSettings.applicationName

SpEL uses a property accessor to retrieve the value from the bean. In the standard JavaBean case, the accessor recognizes the getApplicationName() getter corresponding to the applicationName property.

A property can be a String, number, boolean, enum, collection, or another object. The result type of the expression depends on the actual value returned by the getter.

## 4. Complete example with a Spring bean

Suppose the application has a configuration bean:

    @Component("applicationSettings")
    public class ApplicationSettings {
        public String getApplicationName() {
            return "Order Service";
        }

        public String getDefaultCurrency() {
            return "VND";
        }
    }

The bean can be referenced from a SpEL expression processed by Spring:

    @Value("#{ @applicationSettings.applicationName }")
    private String applicationName;

    @Value("#{ @applicationSettings.defaultCurrency }")
    private String currency;

Spring processes the expressions during bean creation and assigns the results to the corresponding fields.

Resulting values:

    applicationName = "Order Service"
    currency = "VND"

The @ symbol inside the expression is SpEL's bean reference syntax. It is not a standalone Java annotation. The @Value annotation is simply an integration point asking Spring to evaluate the expression.

## 5. Accessing nested properties

A bean can contain other objects. SpEL allows multi-level access using dots.

Example:

    @shopSettings.checkout.currency.code

The path is processed in order:

1. Find the shopSettings bean.
2. Read the checkout property.
3. From the checkout object, read the currency property.
4. From the currency object, read the code property.

A simple object model:

    public class ShopSettings {
        private CheckoutSettings checkout;

        public CheckoutSettings getCheckout() {
            return checkout;
        }
    }

    public class CheckoutSettings {
        private CurrencySettings currency;

        public CurrencySettings getCurrency() {
            return currency;
        }
    }

    public class CurrencySettings {
        private String code;

        public String getCode() {
            return code;
        }
    }

Expression:

    @shopSettings.checkout.currency.code

can return VND if the intermediate objects exist and code has the value VND.

Each property access step depends on the object returned from the previous step. If an intermediate object is null, a regular path can throw an evaluation error.

## 6. Handling potentially null intermediate properties

If nested properties can be null, use safe navigation at the exact steps where the receiver might be null.

Example:

    @shopSettings.checkout?.currency?.code

If checkout is null, accessing currency returns null. If currency is null, the subsequent access to code also returns null.

This can be combined with the Elvis operator to select a default value:

    @shopSettings.checkout?.currency?.code ?: 'VND'

If code is null or an empty string, Elvis returns VND. If code has a value, that result is preserved.

Remember that safe navigation protects the operation immediately following it. Do not place just one ?. at the start of the path and assume every subsequent property is safe.

## 7. Bean names with special characters

Simple bean names can be referenced directly:

    @pricingService

If a bean name contains dots or special characters, enclose the bean name in single quotes:

    @'order.service'.baseUrl

Example:

    @'billing.gateway'.timeout

Single quotes help the parser recognize the entire enclosed content as the bean name, rather than interpreting dots as part of a property path.

Whenever possible, name beans according to simple, consistent conventions so expressions stay readable. If a bean with a special name must be referenced, use the quoted bean name form.

## 8. Accessing beans in Java code with BeanResolver

When using SpEL in a Spring integration point like @Value, Spring configures the bean resolution mechanism for the expression.

However, if creating a parser and StandardEvaluationContext manually in Java, creating SpelExpressionParser does not automatically connect it to ApplicationContext.

A BeanResolver must be registered:

    ApplicationContext applicationContext = ...;

    ExpressionParser parser =
        new SpelExpressionParser();

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setBeanResolver(
        new BeanFactoryResolver(applicationContext)
    );

    String currency = parser
        .parseExpression("@applicationSettings.defaultCurrency")
        .getValue(context, String.class);

BeanFactoryResolver is the standard implementation of BeanResolver. It uses the supplied BeanFactory to look up beans by name.

Key imports:

    import org.springframework.context.ApplicationContext;
    import org.springframework.context.expression.BeanFactoryResolver;
    import org.springframework.expression.ExpressionParser;
    import org.springframework.expression.spel.standard.SpelExpressionParser;
    import org.springframework.expression.spel.support.StandardEvaluationContext;

If the context does not have a BeanResolver registered, the expression may parse successfully but fail during evaluation with an error stating that no bean resolver is configured.

This is an EvaluationContext configuration error, not a syntax error in @beanName.

## 9. Calling methods on a bean

After referencing a bean, SpEL can call methods on that bean.

Example:

    @pricingService.calculateTotal(#order)

Or:

    @customerService.findById(#customerId)

Where:

- @pricingService or @customerService retrieves the bean from BeanResolver.
- The method name identifies the operation to invoke.
- Arguments can be literals, variables, or other expressions.

Example in Java:

    context.setVariable("amount", 1_000_000);

    Expression expression =
        parser.parseExpression(
            "@pricingService.calculateTax(#amount)"
        );

    BigDecimal tax =
        expression.getValue(context, BigDecimal.class);

The method is located and invoked via EvaluationContext's MethodResolver mechanism. The method must be accessible and have parameters compatible with the passed values.

Do not use a method call instead of property access when simply reading a value. Use:

    @applicationSettings.applicationName

rather than calling an explicit getter method if the goal is simply to read a JavaBean property.

## 10. Bean references and FactoryBean

Spring has the concept of FactoryBean: a special bean used to create or provide another object.

When referencing:

    @someFactoryBean

SpEL retrieves the object provided by the FactoryBean via the BeanFactory.

If you need to retrieve the FactoryBean itself instead of the object it creates, add the & symbol before the bean name:

    &someFactoryBean

Example:

    @myClientFactory

retrieves the object provided by the factory.

    &myClientFactory

retrieves the factory bean itself.

This syntax is useful when you need to inspect or operate on the FactoryBean. For regular beans that do not implement FactoryBean, there is no need to use the & prefix.

## 11. Bean scope and access timing

A bean reference is resolved when the expression is evaluated. The BeanFactory is responsible for returning the bean according to that bean's scope configuration.

Examples:

- Singleton: normal lookups return the same singleton instance.
- Prototype: each lookup can create a new instance according to prototype rules.
- Request or session scope: the instance depends on the current scope and requires the scope to be validly active.
- Beans wrapped in a proxy: the expression receives the object returned by the BeanFactory, typically the proxy if the bean is configured that way.

This means the expression does not manage the bean lifecycle itself. It merely asks the BeanResolver to look up the bean by name at evaluation time.

If an expression is retained and evaluated multiple times, the bean reference is still resolved according to the context's BeanResolver and BeanFactory. Do not assume the object is pinned simply because the expression was parsed earlier.

## 12. Using bean references in Spring annotations

SpEL bean references commonly appear in annotations that support expressions.

Example:

    @Value("#{ @applicationSettings.defaultCurrency }")
    private String currency;

Another example:

    @Value("#{ @featureFlags.checkoutEnabled }")
    private boolean checkoutEnabled;

Bean references can be combined with variables or the root object if the integration point provides them:

    @Value("#{ @pricingService.calculate(#root.amount) }")
    private BigDecimal total;

The exact syntax and available root/variable data depend on the annotation or Spring component processing the expression. Not every annotation containing # or @ uses the same EvaluationContext.

When an expression runs in @Value, Spring's bean expression resolver integrates with the BeanFactory. When parsing manually in Java, a BeanResolver must be configured as shown in the previous section.

## 13. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| No bean resolver registered | EvaluationContext has no BeanResolver | Register BeanFactoryResolver or an appropriate resolver |
| No bean named ... | Wrong bean name or bean does not exist in BeanFactory | Check bean name and component/bean configuration |
| Property cannot be read | Getter or PropertyAccessor does not support the property | Check property name, getter, and accessor |
| NullPointerException on nested property | An intermediate object is null | Use safe navigation at each potentially null step |
| Method cannot be found | Method name or parameters do not match | Check method signature and MethodResolver |
| Dotted bean name parsed incorrectly | Bean name is not quoted | Use @'order.service' |
| Retrieved FactoryBean by mistake | Wanted factory but expression retrieved product or vice versa | Use & before the name when FactoryBean is needed |

Split the debugging process into two questions:

1. Did BeanResolver find the right bean?
2. After obtaining the bean, could PropertyAccessor or MethodResolver perform the subsequent operation?

Separating these two steps helps determine whether the error lies in bean lookup or in operating on the object.

## 14. Restricting access and security

Bean references allow expressions to reach objects managed by the application. Depending on the configured accessors and resolvers, an expression can read properties or call methods on that bean.

Therefore:

- Do not evaluate arbitrary expressions supplied by untrusted users in a context that has access to all beans.
- Only register or permit the beans that the expression genuinely needs.
- Avoid placing services with side effects or broad administrative privileges into contexts for untrusted expressions.
- Restrict method and property access according to the business goal.
- Verify the origin of expressions before feeding them into evaluation points.

SimpleEvaluationContext is designed for a restricted feature set and does not support bean references. If the business requirement calls for @beanName, an EvaluationContext with an appropriate BeanResolver is needed, usually StandardEvaluationContext.

Using StandardEvaluationContext does not automatically make an expression safe. Actual access depends on the objects and resolvers provided.

## 15. Key points to remember

- Bean references use the @beanName syntax.
- After a bean reference, properties, nested properties, or methods can be accessed.
- BeanResolver is responsible for looking up beans; PropertyAccessor is responsible for reading properties.
- A manually created StandardEvaluationContext does not automatically connect to the Spring container.
- Use BeanFactoryResolver to connect EvaluationContext to BeanFactory.
- In @Value and Spring integration points, Spring configures the bean resolution mechanism for expressions.
- Bean names containing dots or special characters must be placed inside single quotes.
- Use &beanName when you need the FactoryBean itself rather than the object provided by the factory.
- Safe navigation should be placed at every step that might receive a null receiver.
- Bean scope and proxies remain managed by the Spring container.
- Do not evaluate untrusted expressions with broad bean access permissions.

When writing SpEL to access beans, clearly identify the bean name, the property to read, any intermediate objects, and the EvaluationContext being used. Distinguishing bean lookup from property access makes expressions easier to debug, easier to maintain, and better controlled in terms of access permissions.

## References

- Spring Framework Reference — Bean References: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/bean-references.html
- Spring Framework Reference — Understanding EvaluationContext: https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html
- Spring Framework Javadoc — BeanFactoryResolver: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/expression/BeanFactoryResolver.html
- Spring Framework Javadoc — BeanResolver: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/BeanResolver.html
