# BeanFactoryResolver and Bean Resolution Mechanism

In Spring Expression Language (SpEL), the **@beanName** syntax allows an expression to reference a bean in the Spring container. As a result, an expression can call methods or read properties of a service, policy object, or configuration bean without manually passing that bean in as a variable.

This syntax works through a **BeanResolver** attached to the **EvaluationContext**. Spring provides the **BeanFactoryResolver** implementation, which uses a BeanFactory to look up beans by name. When SpEL encounters a bean reference, the resolver receives the bean name and resolves it to the actual object so the expression can continue evaluating.

Key point to remember: the @ symbol does not automatically search for beans across the entire application. The EvaluationContext must be configured with an appropriate resolver, or the expression must be evaluated within a Spring integration point that has already set up that resolver.

## 1. Bean references in SpEL

Basic syntax:

~~~text
@beanName
~~~

Example calling a method on a bean:

~~~text
@discountPolicy.calculate(#order)
~~~

Reading a property of a bean:

~~~text
@appSettings.region
~~~

Accessing deeper into an object returned by a bean:

~~~text
@appSettings.database.connectionTimeout
~~~

Bean references are typically used when an expression needs to invoke a rule encapsulated in a Spring bean. For example, instead of writing all authorization or pricing logic in an expression string, you can call a clearly named method on a dedicated bean.

~~~java
@Component("discountPolicy")
public class DiscountPolicy {

    public BigDecimal calculate(Order order) {
        // Application discount calculation rule
        return order.getSubtotal().multiply(new BigDecimal("0.05"));
    }
}
~~~

In an evaluation context with a bean resolver:

~~~text
@discountPolicy.calculate(#order)
~~~

SpEL looks up the bean named discountPolicy, calls calculate() with the order variable, and returns the method's result.

The name after the @ symbol is the **bean name** managed by the Spring container. For a bean declared with @Component, the default name is usually the class name with a lowercase initial character; the name can be specified explicitly in the annotation or bean configuration.

## 2. Distinguishing bean references, variables, and root objects

These three access mechanisms have different meanings:

| Syntax | Data source | How it is provided |
| --- | --- | --- |
| **#order** | Variable in EvaluationContext | Registered via setVariable() or provided by an integration point |
| **@orderService** | Bean in the Spring container | BeanResolver looks up the bean by name |
| **order** | Property of the current root object | Passed as the root object to getValue() or set by the context |

Example:

~~~java
context.setVariable("request", request);
~~~

Expression:

~~~text
#request.customerId
~~~

Here request is a variable registered by the creator of the context.

If the application has a bean named customerService, the expression:

~~~text
@customerService.find(#request.customerId)
~~~

references the container-managed bean and then calls a method on that bean.

You cannot replace @customerService with #customerService unless a variable with the same name has been registered. Conversely, a bean named customerService does not automatically appear as the variable #customerService.

## 3. What is BeanResolver?

**BeanResolver** is a Spring Expression SPI that provides the capability to resolve bean references inside expressions.

This interface receives the EvaluationContext and the bean name to look up, and returns the corresponding object. SpEL does not need to know whether the bean is stored in a singleton registry, which scope it belongs to, or which factory created it; those details belong to the resolver.

Roles of the components:

- **ExpressionParser:** parses the expression string and creates an Expression object.
- **EvaluationContext:** provides the root object, variables, functions, property accessors, method resolvers, type converter, and other components needed for evaluation.
- **BeanResolver:** handles bean reference syntax starting with @.
- **BeanFactory:** where Spring manages and looks up beans.
- **BeanFactoryResolver:** a BeanResolver implementation that uses a BeanFactory to find beans.

If the context does not have a BeanResolver, expressions containing @beanName cannot be resolved, even if that bean exists in the ApplicationContext.

## 4. How does BeanFactoryResolver work?

Spring provides the class:

~~~java
org.springframework.context.expression.BeanFactoryResolver
~~~

This class takes a BeanFactory in its constructor. When SpEL asks to resolve a bean name, BeanFactoryResolver delegates the request to the BeanFactory to retrieve the bean by name.

You can visualize the processing flow:

~~~text
Expression: @discountPolicy.calculate(#order)
             |
             v
        SpEL parser
             |
             v
       EvaluationContext
             |
             v
         BeanResolver
             |
             v
      BeanFactoryResolver
             |
             v
    BeanFactory.getBean("discountPolicy")
             |
             v
       DiscountPolicy bean
             |
             v
     call calculate(order)
             |
             v
       expression result
~~~

The core point of BeanFactoryResolver is **delegating bean lookup to the BeanFactory**. The resolver does not create its own registry, does not manage bean lifecycles itself, and does not replace dependency injection.

Because the BeanFactory is responsible for providing instances, Spring's existing bean management rules continue to apply: singleton, prototype, request/session scope when valid, lazy initialization, FactoryBean, and container-provided proxies.

## 5. Manually configuring BeanFactoryResolver in Java

When creating a SpEL parser and EvaluationContext manually, attach a BeanFactoryResolver to the context if the expression uses @beanName.

Example:

~~~java
ApplicationContext applicationContext = ...;

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("order", order);
context.setBeanResolver(
        new BeanFactoryResolver(applicationContext)
);

ExpressionParser parser = new SpelExpressionParser();

BigDecimal discount = parser
        .parseExpression("@discountPolicy.calculate(#order)")
        .getValue(context, BigDecimal.class);
~~~

ApplicationContext implements the required BeanFactory contracts, so it can be passed directly into BeanFactoryResolver. If a specific BeanFactory is already available, that BeanFactory can be passed instead of ApplicationContext.

The important step is calling:

~~~java
context.setBeanResolver(new BeanFactoryResolver(beanFactory));
~~~

Simply creating a StandardEvaluationContext does not automatically connect the context to the Spring container. If attaching the resolver is skipped, expressions with @beanName will not find the bean.

### 5.1. Using a bean reference to read a property

A bean does not have to be invoked via a method. Properties of a bean can be read:

~~~java
@Component
class AppSettings {

    public String getRegion() {
        return "ap-southeast-1";
    }
}
~~~

Expression:

~~~text
@appSettings.region
~~~

SpEL resolves the appSettings bean, then reads the region property through the EvaluationContext's property access mechanism.

Nested properties can continue to be read:

~~~text
@appSettings.database.connectionTimeout
~~~

In this case, appSettings is the bean reference; database and connectionTimeout are properties of the corresponding objects.

### 5.2. Using a bean reference in an expression with variables

Bean references can be combined with variables:

~~~text
@permissionService.canRead(#document, #currentUser)
~~~

Here:

- permissionService is the bean looked up in the BeanFactory.
- document and currentUser are variables provided in the EvaluationContext.
- The return value from canRead() is the result of the expression.

This approach separates business rules into independently testable Java methods, while SpEL merely acts as glue to connect data and invoke methods.

## 6. At which integration points does Spring automatically configure a bean resolver?

When an expression is evaluated by the Spring container or an integrating module, Spring typically creates an appropriate EvaluationContext and configures a BeanResolver so the expression can reference beans.

Example with @Value:

~~~java
@Component
class RuntimeSettings {

    @Value("#{ @appSettings.region }")
    private String region;

    @Value("#{ @discountPolicy.defaultRate }")
    private BigDecimal defaultRate;
}
~~~

During @Value expression processing, Spring uses a bean expression resolver tied to the BeanFactory. Therefore, bean references can be resolved without the user having to manually create a StandardEvaluationContext.

Several other integration points also allow calling beans from SpEL, depending on the module and annotation attribute:

~~~java
@Cacheable(
    cacheNames = "products",
    key = "@cacheKeyGenerator.forProduct(#product)"
)
public Product find(Product product) {
    // ...
}
~~~

With method security:

~~~java
@PreAuthorize("@permissionService.canRead(#document)")
public Document read(Document document) {
    // ...
}
~~~

In these examples, Spring Security and Spring Cache create contexts according to each module's rules. You should not assume that the root object, variables, or method metadata across integration points are identical. However, bean references are still resolved through the resolver capability provided by the module's context.

If a specific annotation or attribute does not support bean references, the @beanName syntax will not work automatically just because the application has a bean with that name. Check the documentation for the exact module and version you are running.

## 7. Bean names, aliases, and names with special characters

BeanFactoryResolver resolves beans by names managed by the Spring container. That name can be a default name, an explicitly declared name, or an alias.

Example:

~~~java
@Component("discountPolicy")
class DefaultDiscountPolicy {
    // ...
}
~~~

Reference expression:

~~~text
@discountPolicy
~~~

If a bean is declared with an alias, the alias can also be used as the lookup name if the BeanFactory registers that alias.

For bean names with special characters or dots, the name can be enclosed in single quotes:

~~~text
@'billing.discount-policy'
~~~

Quotes help the parser treat the entire name portion as the bean name. When naming new beans, prefer simple, stable names without special characters so expressions remain easy to read.

Referencing beans by name also means that renaming a bean or removing an alias can break expressions even if the Java class has not changed. Therefore, bean names used in expressions are part of the configuration contract and must be managed during refactoring.

## 8. Bean scope and lifecycle when resolving beans

BeanFactoryResolver calls the BeanFactory to retrieve beans. Thus, how an instance is returned depends on the bean's scope and configuration.

### 8.1. Singleton

For a singleton bean, repeated resolutions typically return the same container-managed instance:

~~~text
@discountPolicy.calculate(#order)
~~~

SpEL does not create a new DiscountPolicy for each evaluation. The BeanFactory applies the configured singleton scope.

### 8.2. Prototype

For a prototype bean, each call to BeanFactory.getBean() may create a new instance. Because BeanFactoryResolver delegates to BeanFactory, resolving a prototype bean may trigger creating a new instance according to prototype rules.

This should be considered if the expression is evaluated frequently or the bean is expensive to initialize.

### 8.3. Request and session scopes

Request- or session-scoped beans require an active request or session context. If the expression is evaluated outside that scope, the BeanFactory may not be able to resolve the corresponding scoped bean.

In web applications, Spring often uses scoped proxies so beans can be injected or referenced through a proxy. BeanFactoryResolver retrieves the bean in the way the BeanFactory provides it, so container proxies and scope rules continue to apply.

### 8.4. Lazy initialization and initialization errors

If a bean is configured as lazy, the first time an expression references the bean may be the moment it gets initialized. If a constructor, dependency, or initialization process fails, that error surfaces when resolving/evaluating the expression.

Therefore, a bean reference is not just looking up a key in a map. Calling getBean() can trigger container lifecycle behavior.

## 9. When do bean references fail to work?

There are several common errors when using @beanName.

### 9.1. EvaluationContext does not have a BeanResolver

Example:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

Expression expression =
        parser.parseExpression("@discountPolicy.calculate(#order)");

expression.getValue(context);
~~~

The context above has no BeanResolver attached. Even though discountPolicy exists in the ApplicationContext, SpEL has no mechanism to locate that bean.

How to fix it:

~~~java
context.setBeanResolver(
        new BeanFactoryResolver(applicationContext)
);
~~~

### 9.2. Bean name does not exist

If the bean name or alias is not registered in the BeanFactory, the resolver cannot return the corresponding object. Check the bean name, aliases, and component scan or @Bean method configuration.

Do not confuse class names with bean names. A class may be registered under a different name, and a bean may be declared without using the class name as its default name.

### 9.3. Bean exists but initialization fails

The BeanFactory may find the bean definition but fail to create the instance due to a missing dependency, constructor error, or misconfiguration. In this case, the error comes from bean creation, not from SpEL syntax.

### 9.4. Resolution succeeds but method/property is inaccessible

After the resolver returns the bean, SpEL still has to resolve the subsequent method or property:

~~~text
@discountPolicy.calculate(#order)
@appSettings.region
~~~

If the method does not exist, the signature does not match, the property cannot be read, or an intermediate object is null, the expression can fail at the subsequent evaluation step.

Three categories of errors should be separated:

- **Parse error:** invalid expression syntax.
- **Bean resolution error:** no resolver or bean not found by name.
- **Evaluation error:** bean was resolved, but the method/property or input data does not meet requirements.

## 10. Writing a custom BeanResolver when custom resolution rules are needed

BeanFactoryResolver is suitable when you want to directly use Spring BeanFactory's bean lookup rules. In some applications, a different resolver may be needed, for example allowing only a specific set of beans to be accessed or mapping expression names to a service facade.

BeanResolver is an SPI, so a custom resolver can be implemented:

~~~java
public class RestrictedBeanResolver implements BeanResolver {

    private final Map<String, Object> allowedBeans;

    public RestrictedBeanResolver(Map<String, Object> allowedBeans) {
        this.allowedBeans = Map.copyOf(allowedBeans);
    }

    @Override
    public Object resolve(EvaluationContext context, String beanName)
            throws AccessException {

        Object bean = allowedBeans.get(beanName);

        if (bean == null) {
            throw new AccessException(
                    "Bean is not available to this expression: " + beanName
            );
        }

        return bean;
    }
}
~~~

Then attach the resolver to the context:

~~~java
context.setBeanResolver(
        new RestrictedBeanResolver(allowedBeans)
);
~~~

A custom resolver should clearly define behavior for invalid bean names, access permissions, and exception types. If the goal is to access beans in the Spring container in the standard way, there is no need to write a custom resolver; BeanFactoryResolver already provides that implementation.

## 11. Bean references and security boundaries

Bean references can open paths for expressions to invoke methods on services in the application. Therefore, external users should not be allowed to submit arbitrary SpEL strings and have them evaluated with a broadly privileged context.

For example, a context allowing references to @paymentService or @accountAdmin could expose operations that the expression author should not be permitted to invoke.

Several principles:

1. Only evaluate expressions from trusted or controlled sources.
2. Only register a BeanResolver when the feature genuinely needs bean references.
3. If only reading data is needed, consider SimpleEvaluationContext with restricted accessors. SimpleEvaluationContext does not provide bean references like StandardEvaluationContext.
4. If a resolver must be used, restrict the set of allowed beans using a facade or a custom resolver.
5. Do not expose beans with data-writing, payment, administrative, or secret-accessing privileges directly to contexts meant for untrusted expressions.
6. Test both allowed beans and rejected beans.

Restricting the resolver is part of expression security design. Merely hiding bean names in documentation or the UI is not an access control measure.

## 12. Testing bean resolution

BeanFactoryResolver can be tested using a test ApplicationContext:

~~~java
class BeanReferenceExpressionTest {

    @Test
    void resolvesBeanByName() {
        try (AnnotationConfigApplicationContext app =
                     new AnnotationConfigApplicationContext(TestConfig.class)) {

            StandardEvaluationContext context =
                    new StandardEvaluationContext();

            context.setBeanResolver(new BeanFactoryResolver(app));
            context.setVariable("amount", new BigDecimal("100"));

            BigDecimal result = new SpelExpressionParser()
                    .parseExpression("@discountPolicy.apply(#amount)")
                    .getValue(context, BigDecimal.class);

            assertEquals(new BigDecimal("95.00"), result);
        }
    }

    @Configuration
    static class TestConfig {

        @Bean
        DiscountPolicy discountPolicy() {
            return amount -> amount.multiply(new BigDecimal("0.95"));
        }
    }
}
~~~

The example illustrates three key steps:

1. Create an ApplicationContext with the discountPolicy bean registered.
2. Attach BeanFactoryResolver to StandardEvaluationContext.
3. Evaluate the expression using @discountPolicy.

In real tests, also verify invalid bean names, a context without a resolver, missing methods, and beans with special scopes if the application depends on those scopes.

If the expression is evaluated automatically by Spring via @Value or another annotation, write an integration test at the exact integration point rather than only testing the parser standalone. That test verifies that Spring provided the required resolver and context.

## 13. Quick takeaways

- **@beanName** references a bean in the Spring container.
- **BeanResolver** is the SPI handling SpEL bean reference resolution.
- **BeanFactoryResolver** is the implementation using BeanFactory to look up beans by name.
- When creating a StandardEvaluationContext manually, call setBeanResolver(new BeanFactoryResolver(beanFactory)).
- Spring automatically configures the expression context at integration points supporting bean references, such as @Value; each module has its own context.
- **#variable** is a variable in EvaluationContext; **@beanName** is a bean in BeanFactory.
- BeanFactoryResolver delegates to BeanFactory, so scope, aliases, lazy initialization, and container lifecycle continue to apply.
- SimpleEvaluationContext is restricted and does not support bean references like StandardEvaluationContext.
- Missing a resolver, wrong bean names, bean initialization failures, or inaccessible methods/properties can all cause expressions to fail at different stages.
- Do not evaluate untrusted expressions with a resolver that has access to all beans in the application.

## 14. Official references

- [Spring Framework — Bean References in SpEL](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/bean-references.html)
- [Spring Framework — EvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [BeanFactoryResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/expression/BeanFactoryResolver.html)
- [BeanResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/BeanResolver.html)
- [BeanFactory Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/BeanFactory.html)
- [SimpleEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
