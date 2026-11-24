# Calling Methods on Referenced Beans in SpEL

Spring Expression Language (SpEL) can reference a Spring-managed bean using the @beanName syntax, then read properties or call methods on that bean. This capability lets expressions reuse logic already encapsulated in a Spring component, such as computing a configuration value, applying a policy, or querying a dedicated facade.

A call like @pricingPolicy.calculateDiscount(#total) requires two separate capabilities: BeanResolver must locate the pricingPolicy bean in the Spring container, and then MethodResolver must find the matching calculateDiscount method on the returned object. Understanding these two steps helps configure EvaluationContext properly, troubleshoot errors more easily, and restrict which methods an expression can invoke.

## 1. Objectives and prerequisites

After this lesson, you can:

- Reference a bean using the @beanName syntax.
- Call methods on a bean and pass literals, variables, or properties as arguments.
- Configure BeanFactoryResolver when creating StandardEvaluationContext manually.
- Understand how Spring integrates bean references in @Value.
- Distinguish BeanResolver from MethodResolver and PropertyAccessor.
- Recognize the impact of overloads, parameter types, scope, and proxies.
- Diagnose errors when a bean or method fails to resolve.
- Restrict beans and methods exposed to expressions to reduce risk.

You should be familiar with the Spring IoC container, bean names, Java getters/methods, SpelExpressionParser, and passing variables through EvaluationContext.

## 2. Bean reference syntax

SpEL uses the @ symbol to reference a bean by name:

~~~text
@pricingPolicy
~~~

When reading a property of a bean:

~~~text
@pricingPolicy.defaultRate
~~~

When calling a method:

~~~text
@pricingPolicy.calculateDiscount(100)
~~~

The name after @ must be resolved by BeanResolver to a bean present in the container or an object managed by the resolver. The bean name and alias must match the Spring configuration.

Variables can be passed into the method:

~~~text
@pricingPolicy.calculateDiscount(#orderTotal)
~~~

Or properties from an object variable can be passed:

~~~text
@pricingPolicy.calculateDiscount(#order.total)
~~~

Here #orderTotal and #order are SpEL variables, while @pricingPolicy is a bean reference. The two syntaxes serve different roles:

| Syntax | Meaning |
|---|---|
| #variable | Reads a variable registered in EvaluationContext |
| @beanName | Retrieves a bean by name via BeanResolver |
| @beanName.property | Reads a property on the bean |
| @beanName.method(...) | Calls a method on the bean |

There is no need to instantiate the bean with the new syntax inside the expression. A bean reference retrieves an object managed by the Spring container, so dependency injection, lifecycle, and normal bean proxy mechanisms continue to be handled by the container.

## 3. What does BeanResolver do?

BeanResolver is the component in EvaluationContext responsible for resolving the @beanName syntax. It receives the bean name and returns the corresponding object. Once the object is obtained, SpEL continues processing properties or methods on that object.

With a manually created StandardEvaluationContext, you should not assume BeanResolver is already configured. If bean references are needed, the application must provide an appropriate resolver.

Spring provides the BeanFactoryResolver class to connect SpEL to a BeanFactory:

~~~java
import org.springframework.context.expression.BeanFactoryResolver;
import org.springframework.expression.spel.support.StandardEvaluationContext;

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setBeanResolver(new BeanFactoryResolver(beanFactory));
~~~

BeanFactoryResolver uses the supplied BeanFactory to look up beans by name. In a Spring application, beanFactory is typically an ApplicationContext or an existing BeanFactory.

Once configured, expressions can use @beanName within that context.

## 4. Example of calling a method on a bean

Suppose there is a pricing policy component:

~~~java
@Component("pricingPolicy")
public class PricingPolicy {

    public BigDecimal calculateDiscount(BigDecimal total) {
        if (total.compareTo(new BigDecimal("100")) >= 0) {
            return total.multiply(new BigDecimal("0.10"));
        }
        return BigDecimal.ZERO;
    }
}
~~~

The method can be called using SpEL:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setBeanResolver(new BeanFactoryResolver(beanFactory));
context.setVariable("total", new BigDecimal("150.00"));

Expression expression =
    parser.parseExpression("@pricingPolicy.calculateDiscount(#total)");

BigDecimal discount =
    expression.getValue(context, BigDecimal.class);
~~~

The result is 15.00 according to the example method's logic.

Processing flow:

1. SpEL encounters @pricingPolicy.
2. BeanResolver retrieves the pricingPolicy bean from the BeanFactory.
3. SpEL receives the PricingPolicy object.
4. MethodResolver finds the calculateDiscount method matching the arguments.
5. SpEL converts the arguments if needed and invokes the method.
6. The result is returned from getValue(...).

The target object receiving the method call is the bean provided by the container. There is no need to register pricingPolicy as a #pricingPolicy variable, unless the application intentionally wants to pass that object as a variable.

## 5. Passing arguments to methods

Method arguments can be literals, variables, property accesses, or results of other expressions.

### 5.1. Literals

~~~text
@pricingPolicy.calculateDiscount(150)
~~~

The value 150 is passed into the method. The literal type and the method's parameter type must be compatible or convertible.

### 5.2. Variables in context

~~~text
@pricingPolicy.calculateDiscount(#total)
~~~

Registering the variable from Java:

~~~java
context.setVariable("total", new BigDecimal("150.00"));
~~~

This approach works well when data changes per evaluation. The expression remains unchanged while the variable value is updated in the context.

### 5.3. Object properties

~~~text
@pricingPolicy.calculateDiscount(#order.total)
~~~

If order is an object with a readable total property, SpEL retrieves total and passes it to the method.

If order or total may be null, decide how to handle it before calling the method. You can check with a logical condition or use null-safe navigation combined with a default expression if the method accepts that value.

### 5.4. Multiple arguments

~~~text
@pricingPolicy.calculateRate(#customer.level, #order.total)
~~~

The target method must have a matching signature or an overload that SpEL can resolve. When multiple overloads exist, argument types and conversion capabilities affect which method is selected.

Keep arguments clear. If an expression must compute multiple values before calling the method, use parentheses to clarify order or compute the data in Java beforehand and pass it via variables.

## 6. Calling bean methods in @Value

In Spring-managed integration points, @Value supports SpEL and the container provides bean reference capability.

Example reading a property:

~~~java
@Value("#{ @pricingPolicy.defaultRate }")
private BigDecimal defaultRate;
~~~

Example calling a method:

~~~java
@Value("#{ @pricingPolicy.rateFor('VIP') }")
private BigDecimal vipRate;
~~~

Spring evaluates the expression in a context integrated with the container. The pricingPolicy bean must exist and the rateFor method must have a signature compatible with the 'VIP' argument.

Multiple beans or properties can be combined:

~~~java
@Value("#{ @featureFlags.enabled and @pricingPolicy.isAvailable }")
private boolean pricingEnabled;
~~~

The expression still follows SpEL syntax and precedence rules. For long conditions or important business logic, move the logic into a clearly named method for easier testing.

Do not confuse @Value with calling beans in a manually created StandardEvaluationContext. In @Value, Spring configures the evaluation environment for the integration point; in Java code that creates a context manually, you must configure a BeanResolver if you want to use @beanName.

## 7. How is a bean reference different from a variable and root object?

There are multiple ways to provide objects to an expression:

- Root object: the object passed to getValue(context, rootObject) or set on the context.
- Variable: an object registered via context.setVariable("name", object) and accessed via #name.
- Bean reference: an object retrieved from the container via @name.

For example, the same method can be called in three ways if the object is provided accordingly:

~~~text
calculateDiscount(#total)
~~~

~~~text
#policy.calculateDiscount(#total)
~~~

~~~text
@pricingPolicy.calculateDiscount(#total)
~~~

The first assumes the root object has the calculateDiscount method. The second uses the policy variable. The third retrieves the bean by name from BeanResolver.

Choose one approach based on object ownership. Use @beanName when the expression truly needs to access a Spring-managed component; use variables for explicitly passed data or collaborators; use the root object for expressions bound to one primary object.

## 8. BeanResolver and MethodResolver are two independent steps

A common design misconception is thinking that having a BeanResolver means every method on the bean is allowed to be called. In reality, BeanResolver only resolves the bean name. MethodResolver is responsible for finding the method on the returned object.

| Component | Question it answers |
|---|---|
| BeanResolver | Which object is the bean named pricingPolicy? |
| MethodResolver | Does that object have a matching calculateDiscount method? |
| TypeConverter | Can the argument be converted to the parameter type? |
| PropertyAccessor | Can the total or defaultRate property be read? |

StandardEvaluationContext typically has default reflective method resolution. If the application needs to restrict methods, MethodFilter or an allowlist-based custom MethodResolver can be used. Restricting MethodResolver does not automatically restrict which beans can be referenced; BeanResolver and the list of exposed beans must also be controlled.

An expression can successfully resolve a bean yet still fail if the method does not exist, is inaccessible, or has incompatible arguments.

## 9. Bean scope, proxies, and the returned object

BeanResolver retrieves beans through the BeanFactory. Therefore, scope and proxy rules managed by the Spring container still apply.

- Singleton beans typically return the same container-managed instance.
- Prototype beans may create a new instance on each BeanFactory bean retrieval.
- Request/session scope depends on an active request/session context.
- Beans wrapped by an AOP proxy may be returned as a proxy; method calls go through the proxy mechanism as usual.

This matters when an expression calls a method with transaction, security advice, or logging advice. However, do not use SpEL as a substitute for normal service call flows in Java. If a method performs an important business operation, calling it directly from Java is usually clearer and easier to trace.

Do not assume every scope is available at all times. For instance, a request-scoped bean cannot be used properly when there is no active request context.

## 10. BeanFactory and FactoryBean

Normally:

~~~text
@myBean
~~~

references the object returned by the BeanFactory for that bean name.

If a bean name represents a FactoryBean and you need the factory itself instead of the object created by the factory, Spring uses the & prefix:

~~~text
&myFactoryBean
~~~

This is a specialized case. In most business expressions, referencing regular beans with @beanName is sufficient. Only use & when you genuinely need to operate on the FactoryBean and understand its lifecycle.

## 11. Common errors and troubleshooting

| Symptom | Common cause | Resolution |
|---|---|---|
| Cannot resolve @beanName | Context has no BeanResolver or wrong bean name | Configure BeanFactoryResolver and check the bean name |
| Bean exists but method not found | Wrong method name, signature, or inaccessible method | Check method and arguments |
| Unexpected overload selected | Argument types or conversion make multiple overloads match | Use variables with explicit types and avoid ambiguous overloads |
| Argument cannot be converted | Runtime value incompatible with parameter | Check types and TypeConverter |
| Bean scope inactive | Scope requires request/session context that is absent | Check lifecycle and evaluation timing |
| Method throws exception | Error inside method logic | Handle exception according to the business contract |
| @Value fails to inject | Invalid expression syntax or bean/method not ready | Check bean name, dependencies, and expression configuration |
| Bean found but unintended methods still callable | MethodResolver is too broad | Restrict methods via facade, MethodFilter, or allowlist resolver |

When debugging, check in order: bean name, BeanResolver, received runtime object, method signature, argument types, and exceptions inside the method. This helps pinpoint whether the failure occurred at the bean lookup step or the method invocation step.

## 12. Security when calling methods on beans

Bean references in SpEL can open paths to services, repositories, or components with broad privileges. If expressions come from users or untrusted configuration sources, allowing arbitrary bean references can lead to unintended actions.

Apply these principles:

- Do not evaluate user-supplied expressions with a context that can access every bean in the ApplicationContext.
- Do not expose ApplicationContext, BeanFactory, repositories, or administrative services to untrusted expressions.
- Create a small facade containing only necessary methods.
- Restrict methods using MethodFilter or a custom MethodResolver when needed.
- Use a narrowly scoped BeanResolver if the application needs an allowed set of beans.
- Prefer read-only, side-effect-free methods with clear input/output types.
- Validate arguments before the method performs business logic.
- Do not let expressions dynamically decide arbitrary bean names from request data.
- Limit expression length and origin.

BeanResolver is not a sandbox. Even when exposing just one bean, methods on that bean might call other services or mutate state. Review the privileges of the facade and the actual behavior of each method.

## 13. Practice exercises

1. Create a PricingPolicy component with a calculateDiscount(BigDecimal) method.
2. Configure StandardEvaluationContext with BeanFactoryResolver.
3. Call @pricingPolicy.calculateDiscount(150) and read the BigDecimal result.
4. Register a total variable and pass #total as an argument.
5. Call a method with two parameters and verify argument ordering.
6. Create an expression reading @pricingPolicy.defaultRate and compare it with a method call.
7. Use @Value to inject the result from a method on a bean.
8. Create an overloaded method and check which method SpEL selects for different argument types.
9. Use a small facade instead of a large service and try restricting methods.
10. Try a non-existent bean name and observe the resolution error.
11. Test the expression when the bean is a proxy or belongs to a non-singleton scope.

## 14. Checklist before calling bean methods

- [ ] Does the bean name exist in the BeanFactory?
- [ ] Does the EvaluationContext have an appropriate BeanResolver?
- [ ] Have @beanName, #variable, and root object been properly distinguished?
- [ ] Does the method have the right name, signature, and visibility?
- [ ] Are arguments type-compatible and free of unexpected nulls?
- [ ] Are there overloads that need disambiguation?
- [ ] Does the method have side effects, I/O, or state mutations?
- [ ] Does the bean have a scope or proxy that requires attention?
- [ ] Does MethodResolver restrict which methods are allowed to be called?
- [ ] Does BeanResolver expose too many beans?
- [ ] Is the expression from a trusted source and properly bounded?

## 15. Conclusion

The @beanName syntax lets SpEL retrieve a Spring-managed bean and call methods on that object. BeanResolver is responsible for finding the bean; MethodResolver continues by finding a matching method; TypeConverter handles argument conversion. Spring automatically integrates this capability at points like @Value, while a manually created StandardEvaluationContext must be configured with BeanFactoryResolver. Expose a small facade, restrict allowed beans and methods, verify argument types, and avoid evaluating untrusted expressions with a broadly privileged context.