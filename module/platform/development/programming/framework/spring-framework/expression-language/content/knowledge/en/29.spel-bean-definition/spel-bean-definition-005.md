# Referencing Beans in Configuration with SpEL

## Objectives

Spring Expression Language (SpEL) can reference a Spring-managed bean using the @beanName syntax. When an expression is evaluated inside a Spring container, a bean reference allows reading properties, calling methods, or combining data from a bean with other values in the expression.

Example:

~~~spel
@pricingPolicy.defaultRate
@currencyCatalog['USD']
@featurePolicy.enabledFor('checkout')
~~~

Bean references are useful when you need to compute a configuration value from another bean, or when an expression needs to invoke a calculation provided by the application context. However, if the goal is simply to inject a dependency into a class for use in Java code, constructor injection is usually clearer and easier to test.

## 1. Bean Reference Syntax

The basic syntax is the @ symbol followed by the bean name:

~~~spel
@pricingPolicy
@pricingPolicy.defaultRate
@pricingPolicy.calculateTax(amount)
~~~

- @pricingPolicy references the bean instance named pricingPolicy.
- @pricingPolicy.defaultRate reads the defaultRate property of that bean.
- @pricingPolicy.calculateTax(amount) calls a method on the bean.

The bean name must match a bean name or alias registered in the BeanFactory. For bean names with special characters or that do not fit a standard identifier, enclose the name in single quotes:

~~~spel
@'legacy.pricing-policy'.defaultRate
~~~

The @ symbol is SpEL syntax. It differs from #variable: variables are registered directly in EvaluationContext, whereas bean references are resolved through BeanResolver.

## 2. BeanResolver Is Responsible for Resolving Beans

SpEL does not automatically know about every bean in every EvaluationContext. For an expression to resolve @beanName, the context must have a BeanResolver.

In a Spring ApplicationContext, Spring's expression infrastructure typically configures the resolver for expressions used in bean definitions and @Value. When manually creating a parser and StandardEvaluationContext in Java, the application must register the resolver explicitly.

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context = new StandardEvaluationContext();
context.setBeanResolver(new BeanFactoryResolver(beanFactory));

Expression expression = parser.parseExpression("@pricingPolicy.defaultRate");
BigDecimal rate = expression.getValue(context, BigDecimal.class);
~~~

BeanFactoryResolver is an adapter connecting SpEL to a Spring BeanFactory. When an expression references a bean, the resolver asks the BeanFactory for the bean with the specified name.

Common imports:

~~~java
import org.springframework.beans.factory.BeanFactory;
import org.springframework.context.expression.BeanFactoryResolver;
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;
~~~

If StandardEvaluationContext is created manually without calling setBeanResolver(...), the expression @pricingPolicy will not be resolved. Simply creating a SpelExpressionParser does not automatically connect the parser to ApplicationContext.

## 3. Using Bean References in @Value

Spring can evaluate SpEL in the @Value annotation. For example, reading a property from a policy bean:

~~~java
@Component
public class InvoiceConfiguration {

    @Value("#{ @pricingPolicy.defaultRate }")
    private BigDecimal defaultRate;
}
~~~

A method can also be called to compute the injected value:

~~~java
@Component
public class FeatureConfiguration {

    @Value("#{ @featurePolicy.enabledFor('checkout') }")
    private boolean checkoutEnabled;
}
~~~

In this example, Spring evaluates the expression when processing dependency injection for the bean. The enabledFor method is called at the time the expression is evaluated; the injected value does not automatically update whenever a property of featurePolicy changes.

If the policy is needed at multiple points in the application lifecycle, constructor injection is usually more appropriate:

~~~java
@Service
public class CheckoutService {

    private final FeaturePolicy featurePolicy;

    public CheckoutService(FeaturePolicy featurePolicy) {
        this.featurePolicy = featurePolicy;
    }

    public boolean isCheckoutEnabled() {
        return featurePolicy.enabledFor("checkout");
    }
}
~~~

This approach makes the dependency explicit and allows calling methods whenever needed in the processing flow.

## 4. Using Bean References in XML Bean Definitions

Bean definitions can contain SpEL expressions in property values or constructor arguments. Expressions are enclosed in #{...}:

~~~xml
<bean id="invoiceConfiguration"
      class="com.example.InvoiceConfiguration">
    <property name="defaultRate"
              value="#{ @pricingPolicy.defaultRate }"/>
</bean>
~~~

Bean references can be used to produce a value for a constructor argument:

~~~xml
<bean id="reportSettings"
      class="com.example.ReportSettings">
    <constructor-arg
        value="#{ @reportPolicy.defaultFormat }"/>
</bean>
~~~

If you only need to assign a bean as a dependency to a property, using the XML `ref` attribute is usually clearer:

~~~xml
<property name="pricingPolicy" ref="pricingPolicy"/>
~~~

Use SpEL when you need to read a property, invoke a calculation, or combine data in an expression. Do not replace regular dependency wiring with an expression if you only want to inject the bean itself.

## 5. Combining Bean References with Arguments and Operations

Bean references can be used together with root properties, variables, and literals:

~~~spel
@pricingPolicy.rateFor(#order.customer.region)
@discountPolicy.discountFor(customer.tier, #requestedDate)
@currencyCatalog[#currencyCode].symbol
~~~

In a Java example, an expression can use a root object and variables:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(
        "@pricingPolicy.rateFor(#order.customer.region)");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setBeanResolver(new BeanFactoryResolver(beanFactory));
context.setVariable("order", order);

BigDecimal rate = expression.getValue(context, BigDecimal.class);
~~~

In this example:

- @pricingPolicy is resolved through BeanResolver.
- #order is a variable registered by the application.
- customer.region is read from the order object.
- The rateFor method is called on the pricingPolicy bean.

The name passed to setVariable does not include #; the # symbol only appears when referencing the variable in the expression.

## 6. Calling Methods and Reading Properties on Beans

After resolving a bean, SpEL can use property access and method invocation according to the access rules of the evaluation context:

~~~spel
@taxPolicy.defaultRate
@taxPolicy.rateFor('VN')
@featurePolicy.isEnabled('new-checkout')
@catalog.findProduct(#productCode).displayName
~~~

Property access generally relies on getters or an appropriate property accessor. Method invocation requires an accessible method with a signature compatible with the passed arguments.

Keep methods called from expressions short, predictable, and free of side effects. If an expression is evaluated multiple times, the method may also be called multiple times. Do not call methods that send emails, write to databases, publish messages, or perform external actions simply because an expression is reading a value.

## 7. Distinguishing Bean References, Variables, and Type References

The following three forms of references serve different purposes:

| Syntax | Referenced Source | Example |
| --- | --- | --- |
| @pricingPolicy | Bean managed by BeanFactory, resolved via BeanResolver. | @pricingPolicy.defaultRate |
| #pricingPolicy | Variable registered in EvaluationContext. | #pricingPolicy.defaultRate |
| T(com.example.PricingPolicy) | Class located by TypeLocator. | T(java.lang.Math).max(10, 20) |

Do not confuse @ with #. If the application calls context.setVariable("policy", policy), the expression uses #policy. If policy is a Spring bean and the context has a BeanResolver, the expression uses @policy.

A type reference T(...) designates a class, not a bean instance. Use it to access static methods or static fields, not to retrieve a Spring-managed bean.

## 8. FactoryBean and the & Prefix

A FactoryBean is a special bean that creates another object. Normally, when referencing a bean name, Spring returns the object created by the FactoryBean. If you need to reference the FactoryBean itself, prepend & before the bean name in the bean reference:

~~~spel
@&clientFactory
~~~

For example, if clientFactory is a FactoryBean creating an HTTP client:

- @clientFactory references the HTTP client provided by the factory.
- @&clientFactory references the factory object itself.

Only use the dereference form when you genuinely need to interact with the FactoryBean. In most application configurations, the needed dependency is the product object, so a normal bean reference or dependency injection is more appropriate.

## 9. Bean Scope and Resolution Timing

A bean reference is resolved when the expression is evaluated. The result depends on the bean's scope:

| Scope | Behavior When Resolved |
| --- | --- |
| singleton | Returns the singleton instance managed in BeanFactory. |
| prototype | Each time BeanFactory retrieves the bean, it may create a new instance. |
| request/session | Requires the corresponding scope to be active; if used outside scope, resolution may fail. |
| scoped proxy | The expression receives a proxy; the proxy delegates calls to the target matching the scope. |

Distinguish when an expression runs from when a bean is resolved:

- In @Value or a bean definition, the expression is typically evaluated during bean creation or property injection. Scalar values computed then are not automatically recomputed later.
- In expressions parsed and evaluated by the application with repeated getValue calls, the bean reference is resolved on each evaluation.
- If an expression touches a lazy bean, resolution can trigger initialization of that bean.
- With a prototype bean, a re-evaluated expression may receive a new instance; with a singleton bean, it usually receives the same singleton instance.

If you need values that vary per request, call the bean in the appropriate execution flow or evaluate the expression when needed instead of injecting a fixed scalar at initialization.

## 10. Bean References in Configuration vs. Dependency Injection

Both bean references in SpEL and dependency injection can access beans, but their usages differ:

| Need | Recommended Approach |
| --- | --- |
| A class needs to use a service in multiple methods | Constructor injection. |
| A configuration property needs a value from another bean at initialization | @Value with SpEL may be suitable. |
| A bean definition needs to compute a property from another bean | SpEL in #{...} value may be suitable. |
| An expression needs to invoke a calculation from an exposed bean | @beanName.method(...) with an appropriate resolver. |
| Dependency needs to be called at multiple times or per request | Inject the bean and call it from Java. |

Constructor injection example:

~~~java
@Service
public class InvoiceService {

    private final PricingPolicy pricingPolicy;

    public InvoiceService(PricingPolicy pricingPolicy) {
        this.pricingPolicy = pricingPolicy;
    }

    public BigDecimal calculateRate(String region) {
        return pricingPolicy.rateFor(region);
    }
}
~~~

This makes the dependency visible in the constructor, easy to mock in unit tests, and independent of whether an expression resolver is configured.

## 11. Bean Lifecycle and Circular Dependencies

An expression in a bean definition or @Value can require Spring to resolve another bean while the current bean is being created. If two beans reference each other during initialization, the application can encounter a circular dependency or access an object that is not ready yet.

Design example to avoid:

- Bean A needs a property from bean B during initialization.
- Bean B in turn needs to call a method on bean A to initialize itself.
- A's expression resolves B, and B's method turns around and requests A.

To reduce risk:

- Use constructor injection and design a unidirectional dependency graph whenever possible.
- Avoid calling business methods on other beans in initialization expressions.
- Do not use bean references to hide dependencies among multiple beans.
- If configuration values are needed, consider placing data in configuration properties or an independent configuration object.
- Keep methods used in expressions independent of partially initialized state.

## 12. Access Control and Security

Bean references can significantly expand what an expression is allowed to do. If the context can resolve a broad service, the expression can call public methods on that service according to the configured method resolvers.

For expressions supplied by users, tenants, external configuration files, or untrusted sources:

- Do not allow users to submit arbitrary SpEL source and evaluate it against the entire ApplicationContext.
- Only expose beans necessary for the use case.
- Prefer facade or policy beans with small, read-only, and predictable APIs.
- Do not expose repositories, HTTP clients, filesystem services, process runners, or administrative beans if the expression does not need them.
- Avoid methods with side effects, write operations, or external resource access.
- Use a restricted context and resolver allowlist if externally controlled expressions must be supported.
- Validate input data and do not concatenate input into expression source.

SimpleEvaluationContext does not support bean references. If a use case requires @beanName, a context with an appropriate BeanResolver must be used; explicitly restrict the exposed beans and methods instead of granting unnecessary broad access.

## 13. Common Errors and Troubleshooting

| Symptom | Cause to Check | Resolution |
| --- | --- | --- |
| @beanName is not resolved | EvaluationContext has no BeanResolver. | Configure BeanFactoryResolver or use Spring's configured expression infrastructure. |
| Bean not found | Wrong bean name, alias, or bean not registered. | Check the bean name and BeanFactory configuration. |
| Expression works in @Value but fails with manual parser | Spring container configured the resolver; manually created StandardEvaluationContext did not. | Explicitly register BeanResolver in the manual context. |
| #beanName returns null or has no value | Using variable syntax for a bean reference. | Use @beanName for beans; use #name for registered variables. |
| Method on bean cannot be called | Method is inaccessible, wrong parameter count, or incompatible argument types. | Check the method signature and method resolver. |
| Bean scope does not work | Request/session scope is not active or proxy is not configured. | Evaluate within a valid scope or use an appropriate scoped proxy. |
| @Value does not update after bean changes | Expression was evaluated at injection; stored scalar does not recompute. | Inject the bean and read the value at the time of use. |
| Bean initialization fails due to circular dependency | Expression resolves another bean while the dependency graph forms a cycle. | Simplify the dependency graph; avoid calling methods via bean references during init. |
| Expression performs unintended actions | Exposed bean has write methods or resource access. | Narrow the bean allowlist; expose only read-only APIs and move actions to service flows. |

## Takeaways

- @beanName references a Spring bean via BeanResolver; #variable references a variable in EvaluationContext.
- The bean name must match a registered bean name or alias; use single quotes if the name contains special characters.
- Spring's expression infrastructure typically configures a bean resolver for bean definitions and @Value.
- When creating StandardEvaluationContext manually, register BeanFactoryResolver to use @beanName.
- Properties can be read, methods called, or Maps accessed on a bean once resolved.
- @Value and bean definition expressions are typically evaluated during bean creation; scalar values do not automatically update later.
- @&factoryName references the FactoryBean itself; @factoryName normally references the object created by the factory.
- Singleton, prototype, request, and session scopes affect the resolved instance.
- Use constructor injection when a class needs a dependency for use in Java code.
- Avoid circular dependencies and methods with side effects in initialization expressions.
- Do not evaluate untrusted expressions against the entire ApplicationContext; restrict the bean resolver and exposed APIs.
- SimpleEvaluationContext does not support bean references.

## References

- [Spring Framework Reference — Bean References](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/bean-references.html)
- [Spring Framework Reference — Expression Support for Defining Bean Definitions](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-expression-language.html)
- [Spring Framework Reference — Using @Value](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html)
- [Spring Framework API — BeanFactoryResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/expression/BeanFactoryResolver.html)
- [Spring Framework API — StandardBeanExpressionResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/expression/StandardBeanExpressionResolver.html)