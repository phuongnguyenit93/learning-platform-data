# Referencing Beans in ApplicationContext with Spring Expression Language

Spring Expression Language (SpEL) can directly reference a Spring-managed bean by bean name. This syntax helps expressions read properties or call methods on a component in the ApplicationContext, such as \`@pricingService.calculateTotal(...)\`.

To resolve a bean reference, SpEL needs a \`BeanResolver\` in the EvaluationContext. In a Spring application, built-in mechanisms typically connect the resolver to the ApplicationContext's BeanFactory. When creating an EvaluationContext manually in Java, the application must configure a resolver if it wants to use the \`@beanName\` syntax.

## 1. What is a bean reference?

A bean is an object created, configured, and lifecycle-managed by the Spring IoC container. A bean can be registered via component scanning, configuration annotations, XML, or other bean registration mechanisms.

SpEL uses the \`@\` symbol to reference a bean by name:

~~~spel
@pricingService
~~~

The expression above asks the resolver to look up the bean named \`pricingService\` in the configured BeanFactory.

After obtaining the bean, the expression can continue accessing properties or calling methods:

~~~spel
@pricingService.defaultCurrency
@pricingService.calculateTotal(#order)
~~~

A bean reference does not create a new object with the \`new\` operator. It asks the Spring container to provide a managed bean by name or alias.

## 2. Distinguishing bean references, variables, and root properties

The three notations below have different meanings:

| Syntax | Value source | Meaning |
|---|---|---|
| \`@pricingService\` | BeanResolver / BeanFactory | Retrieves a Spring bean by name |
| \`#minimum\` | Variable in EvaluationContext | Retrieves the value of a registered variable |
| \`customer\` | Root object or current object | Reads a property on the current object |

Example:

~~~spel
@pricingService.calculate(#order, #minimum)
~~~

In this expression:

- \`@pricingService\` is a bean resolved from the container.
- \`#order\` is a variable registered in the EvaluationContext.
- \`#minimum\` is another variable in the same context.
- \`calculate(...)\` is a method called on the located bean.

Do not replace \`@pricingService\` with \`#pricingService\` unless the application actually registers a variable named \`pricingService\`. Bean names and variable names are two separate namespaces.

## 3. BeanResolver is responsible for resolving beans

SpEL defines the \`BeanResolver\` interface to separate bean lookup from expression syntax. When encountering a bean reference, SpEL calls the resolver configured in the EvaluationContext.

Spring provides \`BeanFactoryResolver\`, an implementation that uses a BeanFactory to look up beans by name. Because ApplicationContext inherits BeanFactory capabilities, ApplicationContext can be used as the source for the resolver.

Processing flow:

~~~text
Expression: @pricingService
          |
          v
SpEL recognizes bean reference
          |
          v
EvaluationContext retrieves BeanResolver
          |
          v
BeanFactoryResolver.resolve(...)
          |
          v
BeanFactory.getBean("pricingService")
          |
          v
Spring bean is returned
          |
          v
SpEL continues reading property or calling method
~~~

If the context does not have a BeanResolver, SpEL cannot resolve the bean reference syntax. If a resolver is present but does not find a bean with that name, evaluation also fails.

## 4. Manually configuring BeanFactoryResolver

When an application creates a \`StandardEvaluationContext\` manually, it can connect it to an ApplicationContext or BeanFactory using \`BeanFactoryResolver\`.

Example:

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;
import org.springframework.context.expression.BeanFactoryResolver;

ApplicationContext applicationContext = ...;

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setBeanResolver(
    new BeanFactoryResolver(applicationContext)
);

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("@pricingService.defaultCurrency");

String currency =
    expression.getValue(context, String.class);
~~~

Here:

1. ApplicationContext is the container that provides the bean.
2. BeanFactoryResolver connects SpEL to the container.
3. setBeanResolver registers the resolver on the EvaluationContext.
4. The expression \`@pricingService.defaultCurrency\` retrieves the bean by name and then reads the property.
5. getValue returns the property value as the requested String type.

Merely creating a StandardEvaluationContext without calling setBeanResolver will not make bean references work automatically in that context.

## 5. Calling methods on a bean

An application often references a bean to invoke a service or policy managed by Spring.

Suppose there is a service:

~~~java
public class PricingService {
    public BigDecimal calculateTotal(
            BigDecimal price,
            int quantity) {
        return price.multiply(BigDecimal.valueOf(quantity));
    }
}
~~~

The bean is registered under the name \`pricingService\`. Its method can be called from SpEL:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setBeanResolver(
    new BeanFactoryResolver(applicationContext)
);

context.setVariable("price", new BigDecimal("250000"));
context.setVariable("quantity", 3);

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "@pricingService.calculateTotal(#price, #quantity)"
);

BigDecimal total =
    expression.getValue(context, BigDecimal.class);
~~~

Result:

~~~text
750000
~~~

SpEL performs two consecutive steps:

- BeanResolver looks up the \`pricingService\` bean.
- MethodResolver finds and calls the \`calculateTotal\` method on that bean object.

Bean resolution and method resolution are two distinct steps. The bean can be found successfully, yet the method call can still fail if the method name, signature, or access permissions do not match.

## 6. Referencing beans in @Value

In Spring applications, bean references often appear inside SpEL expressions used with the \`@Value\` annotation.

Example:

~~~java
@Component
public class InvoiceSettings {

    @Value("#{ @taxPolicy.defaultRate }")
    private BigDecimal taxRate;

    public BigDecimal getTaxRate() {
        return taxRate;
    }
}
~~~

Suppose there is a bean named \`taxPolicy\` with a \`defaultRate\` property. Spring evaluates the expression during dependency injection and assigns the value to the \`taxRate\` field.

A bean method can be called in the expression:

~~~java
@Value("#{ @currencyPolicy.defaultCurrency() }")
private String currency;
~~~

In a normally configured Spring environment, the expression resolver mechanism integrates with the BeanFactory so bean references can be resolved without manually creating a StandardEvaluationContext for each annotation.

Be sure to distinguish the syntax:

- \`@Value(...)\` is a Spring annotation used to provide a value for a field, parameter, or method.
- \`#{...}\` encloses a SpEL expression inside the annotation string.
- \`@taxPolicy\` inside the expression is a bean reference.

## 7. Bean names, aliases, and names with special characters

Beans are usually referenced by their registered name:

~~~spel
@pricingService
@taxPolicy
~~~

If the BeanFactory registers an alias for a bean, the alias can also be used when the resolver supports alias lookup through the BeanFactory.

For bean names containing special characters or dots, the name can be placed in single quotes:

~~~spel
@'pricing.service'
~~~

This notation helps the parser distinguish the bean name from the rest of the expression syntax.

The bean name must match a name or alias registered in the container. If the name is misspelled, the resolver will not find the bean and evaluation will fail.

## 8. Referencing a FactoryBean with the & symbol

Spring has a special type of bean called \`FactoryBean\`. When looking up a bean produced by a FactoryBean, the BeanFactory usually returns the factory's product object.

If you want to reference the FactoryBean object itself, use the \`&\` prefix before the bean name:

~~~spel
@&myFactory
~~~

Where:

- \`@myFactory\` references the product provided by the FactoryBean.
- \`@&myFactory\` references the FactoryBean itself.

For example, if a bean is named \`clientFactory\`, the expression \`@&clientFactory\` asks the container to return the factory object rather than its product.

This syntax is only appropriate when the bean name corresponds to a FactoryBean. For regular beans, there is no reason to add the \`&\` prefix.

## 9. Bean references and bean lifecycle

Bean references are resolved through the BeanFactory, so the behavior depends on the bean's scope.

| Scope | Behavior when retrieving the bean |
|---|---|
| singleton | The container shares a single instance within the BeanFactory's singleton scope |
| prototype | The container creates a new instance for each bean request |
| request | Instance bound to the current HTTP request |
| session | Instance bound to the current HTTP session |
| application | Instance bound to the ServletContext |
| custom scope | According to the rules of the Scope registered by the application |

For example, a singleton bean typically returns the same instance when referenced across different evaluations in the same BeanFactory. A prototype bean may return a new instance when the resolver performs a new lookup.

Web-bound scopes such as request or session require the corresponding scope to be active. If the expression is evaluated outside a valid scope, the BeanFactory may raise an error because the scope is not active.

A bean reference therefore preserves Spring's lifecycle management mechanism. It is not equivalent to manually calling a constructor in Java.

## 10. Bean references and AOP proxies

If a bean is wrapped by Spring with an AOP proxy, resolving the bean through the BeanFactory typically returns the object managed by the container, which may be the proxy itself.

When SpEL calls a method on a bean reference:

~~~spel
@accountService.loadAccount(#accountId)
~~~

the call is made on the object provided by the container. If it is a proxy, the corresponding interceptors such as transaction, security, or logging may participate according to the AOP configuration.

This is one reason to reference beans through the container rather than creating an instance with \`new\`: the application continues to use the object configured and managed by Spring.

## 11. Bean references in template expressions

Bean references can also appear in template expressions if the parser is provided with an appropriate ParserContext.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();
ParserContext templateContext = new TemplateParserContext();

Expression expression = parser.parseExpression(
    "Total: #{ @pricingService.calculateTotal(#price, #quantity) }",
    templateContext
);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setBeanResolver(
    new BeanFactoryResolver(applicationContext)
);
context.setVariable("price", new BigDecimal("250000"));
context.setVariable("quantity", 3);

String message =
    expression.getValue(context, String.class);
~~~

Result:

~~~text
Total: 750000
~~~

ParserContext identifies the literal text and the SpEL portions in the template. BeanResolver still belongs to EvaluationContext and is responsible for looking up beans at evaluation time.

These two components have different responsibilities: ParserContext determines how the string is parsed; EvaluationContext provides the execution environment.

## 12. Common errors when referencing beans

### 12.1. Missing BeanResolver

The expression:

~~~spel
@pricingService
~~~

cannot be resolved if the EvaluationContext does not have a BeanResolver.

For a manually created context, register:

~~~java
context.setBeanResolver(
    new BeanFactoryResolver(applicationContext)
);
~~~

In a built-in Spring environment, verify whether the expression resolver is properly connected to the BeanFactory.

### 12.2. Wrong bean name or alias

If a bean is not registered under the name written in the expression, BeanFactoryResolver cannot find it.

Check:

- The actual bean name.
- Registered aliases.
- Case sensitivity.
- Whether names containing dots or special characters are properly enclosed in single quotes.

### 12.3. Bean found, but property or method does not exist

Example:

~~~spel
@pricingService.unknownMethod()
~~~

BeanResolver may find the bean successfully, but MethodResolver cannot find the corresponding method. Similarly, property access can fail if the bean does not have a matching property or accessor.

Distinguish between errors retrieving the bean and errors operating on the bean after it has been retrieved.

### 12.4. Inactive scope

If a bean belongs to request scope or session scope but the expression is evaluated outside the corresponding web scope, retrieving the bean may fail.

Check where and when the expression is evaluated, as well as the bean's scope.

### 12.5. Bean initialization or dependency errors

The BeanFactory may find the bean definition, yet creating the instance fails because of a failing dependency, constructor, or lifecycle callback.

In that case, the error does not come from the bean reference syntax. Inspect the root exception from the bean initialization process.

## 13. Controlling access through bean references

Bean references can open paths to services, repositories, or components with permissions to modify application state. Therefore, an expression can do more than just read data.

Example:

~~~spel
@accountService.disableAccount(#accountId)
~~~

If the method is allowed to be called and the bean is resolved, the expression can perform a real business operation.

When evaluating expressions obtained from users or untrusted sources, you should not provide a BeanResolver that can access the entire container without restriction. Consider:

- Providing only the beans that the expression actually needs.
- Using a context with an appropriate access scope.
- Restricting methods with side effects.
- Validating input data and business permissions.
- Not treating SpEL syntax as a security boundary.

If the application does not need bean references, do not register a BeanResolver for that context.

## 14. Complete example: calling a bean in ApplicationContext

Suppose there is a service:

~~~java
@Component("discountPolicy")
public class DiscountPolicy {

    public BigDecimal discountFor(BigDecimal total) {
        if (total.compareTo(new BigDecimal("1000000")) >= 0) {
            return new BigDecimal("0.10");
        }
        return BigDecimal.ZERO;
    }
}
~~~

Create the context and evaluate the expression:

~~~java
ApplicationContext applicationContext = ...;

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setBeanResolver(
    new BeanFactoryResolver(applicationContext)
);

context.setVariable(
    "total",
    new BigDecimal("1500000")
);

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "@discountPolicy.discountFor(#total)"
);

BigDecimal discountRate =
    expression.getValue(context, BigDecimal.class);

System.out.println(discountRate);
~~~

Result:

~~~text
0.10
~~~

Processing flow:

1. The \`discountPolicy\` bean is registered in the ApplicationContext.
2. BeanFactoryResolver connects EvaluationContext to the container.
3. The \`total\` variable is registered in the context.
4. SpEL resolves \`@discountPolicy\` to the bean object.
5. MethodResolver finds and calls \`discountFor(BigDecimal)\`.
6. The method returns a BigDecimal and getValue receives the result in the requested type.

## 15. Takeaways

- Bean references use the \`@beanName\` syntax to retrieve a bean by name from the container.
- BeanResolver is the component responsible for resolving bean references.
- Spring provides BeanFactoryResolver to connect SpEL to BeanFactory; ApplicationContext can be passed into the resolver.
- A manually created StandardEvaluationContext must have a BeanResolver configured before using the @ syntax.
- In Spring's @Value expressions, the built-in expression resolver mechanism integrated with BeanFactory usually already provides bean reference capability.
- \`#name\` is a variable in EvaluationContext, whereas \`@name\` is a bean reference.
- Properties can be accessed and methods called on the bean after the bean is resolved.
- \`&beanName\` is used to retrieve the FactoryBean itself instead of the product created by the factory.
- Bean scope, AOP proxies, and container lifecycle remain in effect when beans are retrieved via the resolver.
- Bean references should not be opened broadly to untrusted expressions without controlling access permissions and side effects.

When using bean references in SpEL, identify the bean name, ensure EvaluationContext has an appropriate BeanResolver, and separately verify the bean lookup step and the property access or method call step on that bean.
