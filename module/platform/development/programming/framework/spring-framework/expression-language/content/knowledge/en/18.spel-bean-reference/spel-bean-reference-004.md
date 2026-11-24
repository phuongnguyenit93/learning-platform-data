# Bean Names with Special Characters and Reference Syntax

## Objectives

After this lesson, you can reference a Spring bean in Spring Expression Language (SpEL); distinguish bean reference syntax from variables and regular properties; properly write bean names containing dots or special characters using string literals; configure a BeanResolver when manually creating an EvaluationContext; and understand how to reference a FactoryBean. You will also learn how to handle bean resolution errors and restrict which beans an expression is allowed to access.

## 1. What is a bean reference in SpEL?

SpEL can retrieve a bean from the Spring container using the @ symbol before the bean name. Example:

~~~text
@orderService
~~~

The expression asks the EvaluationContext's BeanResolver to look up the bean named orderService and return the corresponding object.

A bean reference can be used as a value in an expression, to read a property, or to call a method on the bean:

~~~text
@pricingService.defaultCurrency
~~~

~~~text
@pricingService.calculate(#order)
~~~

In the second example, SpEL retrieves the pricingService bean, then calls the calculate(...) method with the #order variable.

Bean references help expressions connect to business components already managed by Spring. They do not create a new bean and do not automatically look up beans by Java type; they require resolution by bean name.

## 2. Regular bean reference syntax

With simple bean names, they are usually used directly:

~~~text
@orderService
@inventoryService
@customerRepository
~~~

The @ symbol tells the parser that this is a bean reference. The name portion that follows is passed to the BeanResolver to look up the object.

Java example with a manually created EvaluationContext:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setBeanResolver(
    new BeanFactoryResolver(applicationContext)
);

Expression expression =
    parser.parseExpression("@orderService");

Object orderService = expression.getValue(context);
~~~

BeanFactoryResolver is a built-in adapter for using a BeanFactory as the bean resolution source. ApplicationContext is also a BeanFactory, so it can be passed directly into the constructor as shown in the example.

If the application has a custom BeanResolver, that resolver can be registered via context.setBeanResolver(...). The resolver is responsible for receiving the bean name and returning the appropriate object.

## 3. Why do bean names with special characters need quotes?

Regular bean names usually use alphanumeric characters following the camelCase convention. However, Spring allows bean names or aliases to contain dots and other special characters.

In SpEL syntax, a dot also means accessing a property or calling a method. Therefore, if a bean name contains dots or special characters, the parser needs to know that the entire portion is a single bean name.

Enclose the bean name as a string literal inside single quotes:

~~~text
@'order.service'
~~~

Some examples:

~~~text
@'order.service'
@'payment-service'
@'legacy$processor'
~~~

Do not write a name containing dots like a regular bean reference:

~~~text
@order.service
~~~

The notation above may be interpreted as referencing the order bean and then accessing the service property, instead of looking up a bean named order.service.

When using a string literal, the quotes encompass the entire bean name. The parser then passes that exact name to the BeanResolver.

## 4. Using beans with special names in larger expressions

After referencing the bean, you can continue accessing properties, calling methods, or combining with other operators.

Example reading a property:

~~~text
@'order.service'.defaultCurrency
~~~

Example calling a method:

~~~text
@'payment-service'.authorize(#payment)
~~~

Example combining with a condition:

~~~text
@'feature.toggle'.isEnabled('new-checkout') and #order.total > 0
~~~

The bean name remains a string literal placed after the @ symbol. What follows the bean name is an operation on the object returned by the resolver.

Called methods must exist and be accessible according to the EvaluationContext's method resolver configuration. Successfully resolving a bean does not guarantee that every subsequent method call or property access is valid.

## 5. Configuring BeanResolver when creating a context manually

A new StandardEvaluationContext does not automatically know about the application's Spring container. If you manually create a parser and context outside Spring's expression processing mechanism, a BeanResolver must be registered.

Example using BeanFactoryResolver:

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.context.expression.BeanFactoryResolver;
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

public class SpelBeanLookup {

    public Object findOrderService(ApplicationContext applicationContext) {
        ExpressionParser parser = new SpelExpressionParser();

        StandardEvaluationContext context =
            new StandardEvaluationContext();

        context.setBeanResolver(
            new BeanFactoryResolver(applicationContext)
        );

        Expression expression =
            parser.parseExpression("@orderService");

        return expression.getValue(context);
    }
}
~~~

In the example:

1. The parser parses the @orderService expression.
2. The context is attached with BeanFactoryResolver.
3. During evaluation, SpEL calls the resolver to look up the bean named orderService.
4. The result is the instance managed by the Spring container.

If setBeanResolver(...) is omitted, a bean reference in a manual context will have no resolver to handle it and may throw a SpelEvaluationException stating that no BeanResolver is registered.

Manually registering a resolver is not required in every situation. When an expression is evaluated by Spring's built-in mechanism, such as @Value processing, the framework provides an appropriate bean context. Check how the expression is created and evaluated before configuring it manually again.

## 6. Bean references in @Value

In Java code, @Value is a Spring annotation. Inside the annotation's SpEL string, the @ symbol is also used to reference a bean.

Example:

~~~java
@Component
public class CheckoutConfiguration {

    private final String currency;

    public CheckoutConfiguration(
            @Value("#{ @pricingService.defaultCurrency }")
            String currency) {
        this.currency = currency;
    }
}
~~~

Here:

- @Value is an annotation instructing Spring to obtain a value for the constructor parameter.
- #{ ... } marks the SpEL expression part.
- @pricingService is the bean reference inside the expression.
- .defaultCurrency reads the property from the resolved bean.

Bean names with special characters can be used in @Value SpEL:

~~~java
@Value("#{ @'order.service'.defaultCurrency }")
private String currency;
~~~

Distinguish the @ symbol of a Java annotation from the @ symbol in the SpEL language. The meaning of the symbol at each position depends on its surrounding syntax.

## 7. Bean names, aliases, and resolution behavior

A bean in Spring can have a primary name and one or more aliases. A bean reference can use any name or alias recognized by the container.

Example declaring a bean with an alias in Java configuration:

~~~java
@Bean(name = {"orderService", "order.service"})
public OrderService orderService() {
    return new OrderService();
}
~~~

It can be referenced using the simple name:

~~~text
@orderService
~~~

Or using the dotted alias as a string literal:

~~~text
@'order.service'
~~~

Both names point to the same bean if the container has registered them as aliases of one another.

When naming beans, prefer simple, readable, and consistent names. Aliases with special characters are useful when compatibility with legacy configuration or integration with an external naming convention is required. In SpEL expressions, always use the exact registered name or alias.

Bean names are resolved by exact name match. Do not assume the parser automatically strips hyphens, converts uppercase to lowercase, or searches for a similar bean when a name does not exist.

## 8. Referencing a FactoryBean

FactoryBean is a Spring mechanism that allows one bean to produce another object. When referencing the bean by its normal name, the container returns the product created by the FactoryBean.

If you need to access the FactoryBean itself, use the & prefix before the bean name:

~~~text
&orderServiceFactory
~~~

BeanResolver receives the name &orderServiceFactory and asks the container to return the factory instance instead of the factory's product.

You can distinguish:

| Reference style | Requested object |
|---|---|
| @orderServiceFactory | The product created by the FactoryBean |
| &orderServiceFactory | The FactoryBean itself |

This is a difference in the object retrieved from the container. Only use the & prefix when you actually need to operate on the factory, such as inspecting the factory's configuration or state.

Spring documentation notes that the name passed to BeanResolver has the & prefix when requesting a FactoryBean. If the referenced factory bean has a special name, check the parser syntax of the Spring version in use and ensure the name is passed intact to the resolver.

## 9. Distinguishing bean references, variables, and properties

The three notations below do not have the same meaning:

| Syntax | Meaning |
|---|---|
| @orderService | Retrieves the bean named orderService via BeanResolver |
| #orderService | Reads the variable orderService in EvaluationContext |
| orderService | Reads the property orderService from the current root object |

For example, an application might register both a bean and a variable with the same name:

~~~java
context.setVariable("orderService", serviceMock);
~~~

In SpEL:

~~~text
@orderService
~~~

references the bean found by the resolver in the container.

~~~text
#orderService
~~~

reads the serviceMock variable registered in the context.

Without a @ or # prefix, the parser looks up a property on the root object according to property access rules. Use the correct prefix to avoid referencing the wrong data source.

## 10. Combining bean references with variables and the root object

Bean references can work together with data passed into the context:

~~~text
@pricingService.calculate(#order, #discountRate)
~~~

In the example:

- @pricingService retrieves the service from the container.
- #order retrieves the order from a context variable.
- #discountRate retrieves the discount rate from a context variable.
- calculate(...) calls the method on the service.

The root object can also be used:

~~~text
@authorizationService.canAccess(authentication, resourceId)
~~~

In this case, authentication and resourceId are read from the root object if they are accessible properties.

Keep responsibilities clearly separated: the container provides collaborators, while EvaluationContext provides input data for the expression. Do not embed user data directly into a bean name string or concatenate strings to build dynamic expressions when data can be passed through variables.

## 11. Common errors when referencing beans

Some common errors:

- **Missing BeanResolver:** the manual context did not call setBeanResolver(...).
- **Wrong bean name:** the name or alias is not registered in the container.
- **Forgetting quotes for special names:** names containing dots or special characters were not placed inside a string literal.
- **Confusing bean reference with variable:** using @name when the data was actually only registered via setVariable.
- **Confusing FactoryBean with its product:** forgetting the & prefix when the factory itself is needed.
- **Access errors after resolution:** the bean was found, but the subsequent property or method does not exist or cannot be accessed.
- **Bean fails to create product:** the FactoryBean throws an error when the container requests the product.

When debugging, split the process into two steps: verify whether the resolver can find the bean with the right name, then verify whether the expression can access the desired property or method on the returned object.

Do not catch all SpEL errors and return null as if the bean reference succeeded. Log the bean name and resolution cause so you can fix the configuration or bean registration accurately.

## 12. Restricting bean access permissions

A bean reference can unlock more capabilities than a simple property read. Once the bean is obtained, the expression can call methods permitted by the EvaluationContext. If the bean is a service with permission to write data, send messages, or perform transactions, the expression can trigger that action.

Therefore:

1. Only register a BeanResolver when the expression genuinely needs beans.
2. Do not expose the entire ApplicationContext to untrusted expressions.
3. For expressions coming from users or external sources, consider a BeanResolver that only allows a selected list of beans.
4. Only expose necessary methods with clear effects.
5. Avoid letting configuration expressions call state-mutating methods if the purpose is only computation or data reading.
6. Validate permissions and input data in the Java service; do not rely on SpEL syntax to replace business access controls.

BeanResolver is part of the access permission boundary. Restricting referenced beans helps reduce the chance of expressions accidentally or arbitrarily calling components in the application.

## 13. Comprehensive example

Suppose the Spring container has a service bean with a regular name and an alias containing a dot. Both forms can be evaluated:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setBeanResolver(
    new BeanFactoryResolver(applicationContext)
);

Expression regularReference =
    parser.parseExpression("@pricingService");

Expression specialNameReference =
    parser.parseExpression("@'order.service'");

Object pricingService =
    regularReference.getValue(context);

Object orderService =
    specialNameReference.getValue(context);
~~~

If the two names are registered as two aliases of the same bean, both expressions return the same container-managed instance.

Example calling a method on a bean with a special name:

~~~java
Expression calculate = parser.parseExpression(
    "@'order.service'.calculate(#order)"
);

context.setVariable("order", order);

Object total = calculate.getValue(context);
~~~

This expression resolves the bean first, then calls the method on the returned object. The type and value of the order variable must be compatible with the calculate method signature.

## 14. Testing bean references

When testing an expression with a bean reference, include:

| Case | What to verify |
|---|---|
| Regular bean name | Resolver returns the right bean |
| Name with dots | Uses string literal form, e.g. @'order.service' |
| Name with hyphens or special characters | Parser treats the entire name as one literal |
| Bean alias | Alias resolves to the same instance |
| Context without resolver | Detects missing BeanResolver error |
| Non-existent bean name | Detects bean resolution error |
| Bean reference with method call | Method and arguments are accessed properly |
| Bean reference with property | Property can be read and has the expected type |
| Regular FactoryBean | Receives the factory's product |
| & prefix | Receives the FactoryBean itself |
| Variable with the same name as a bean | Distinguishes @name and #name |

Test using a Spring context or BeanFactory configured closely to the real runtime environment. A mock BeanResolver can be useful for unit tests, but does not replace integration checks against the container's bean naming and alias rules.

## 15. Takeaways

Bean references in SpEL use the @ symbol to retrieve a bean via BeanResolver. Regular names can be written directly such as @orderService. If a name contains dots or special characters, enclose the entire name in a string literal, such as @'order.service'.

When manually creating a StandardEvaluationContext, a BeanResolver must be registered, often using BeanFactoryResolver with an ApplicationContext or BeanFactory. Built-in Spring mechanisms such as @Value processing already provide an appropriate bean resolution context.

The & prefix is used to request the FactoryBean itself instead of the product created by the factory. Bean references differ from #name variables and unprefixed root object properties.

Use exact bean names, verify aliases and the resolver, and separate resolution errors from subsequent property or method access errors. Only provide the beans that the expression truly needs, especially when the expression originates from untrusted sources.

## References

- [Spring Framework Reference — Bean References](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/bean-references.html)
- [BeanResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/BeanResolver.html)
- [BeanFactoryResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/expression/BeanFactoryResolver.html)