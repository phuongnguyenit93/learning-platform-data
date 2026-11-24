# Do Not Use new Instead of Dependency Management

## Objectives

Spring Expression Language (SpEL) supports the **new** operator to create an object by invoking a Java class constructor. This syntax is useful when an expression needs to create a value or small object during evaluation. However, an object created with new does not automatically become a Spring bean and does not have its lifecycle or dependencies managed by the container.

This is a key distinction when designing Spring applications: **new is Java's object creation mechanism; dependency injection is Spring's mechanism for managing and providing dependencies**. Do not use constructor expressions to manually create services, repositories, clients, or components that should be managed by Spring.

After this lesson, you will be able to:

- Write constructor expressions using the new operator in SpEL.
- Understand how SpEL resolves classes and constructors.
- Distinguish objects created with new from Spring-managed beans.
- Recognize why manually instantiating dependencies bypasses injection, proxies, and lifecycle management.
- Use constructor injection in Java and bean references in SpEL when appropriate.
- Choose the right use cases for new and test expressions safely.

## 1. Constructor Invocation in SpEL

SpEL uses the **new** keyword to call a class constructor:

~~~text
new fully.qualified.ClassName(arguments)
~~~

Example creating a Date object:

~~~text
new java.util.Date()
~~~

Creating a String:

~~~text
new String('Hello SpEL')
~~~

Creating a business type:

~~~text
new com.example.Money(125, 'USD')
~~~

For classes outside the java.lang package, you normally need to write the package-qualified class name. SpEL has a default import prefix of java.lang, so you can write String instead of java.lang.String.

A constructor expression is parsed into a SpEL expression. When the expression is evaluated, SpEL finds the matching class and constructor, converts arguments if needed per the EvaluationContext's TypeConverter, and then invokes the constructor.

Example evaluating in Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context = new StandardEvaluationContext();

Expression expression =
    parser.parseExpression("new java.math.BigDecimal('125.50')");

BigDecimal amount = expression.getValue(context, BigDecimal.class);
~~~

The result is a BigDecimal with value 125.50. This is an appropriate example because BigDecimal is a value type and the constructor simply creates the value needed in the expression.

## 2. Class Names and Constructor Resolution

When encountering new, SpEL must identify the requested class. TypeLocator in EvaluationContext participates in resolving the class name. Then, ConstructorResolver finds a constructor matching the argument count and types.

Points to remember:

- Use the fully qualified class name for classes outside java.lang.
- The class must be on the runtime classpath and visible to the class loader used by TypeLocator.
- The constructor must be accessible to the configured constructor resolution mechanism; public constructors are the normal choice.
- Argument count and types must match a constructor.
- TypeConverter can convert certain argument types, but do not rely on implicit conversion if the data contract is unclear.
- If a class has multiple overloaded constructors, test with the actual argument types to confirm which constructor is selected.

Example:

~~~java
public class Money {
    private final BigDecimal amount;
    private final String currency;

    public Money(BigDecimal amount, String currency) {
        this.amount = amount;
        this.currency = currency;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public String getCurrency() {
        return currency;
    }
}
~~~

The expression:

~~~text
new com.example.Money(125.50, 'USD')
~~~

works only if the actual class has a constructor compatible with the two arguments SpEL resolves. If the constructor only takes BigDecimal while the first argument resolves to another numeric type, the outcome still depends on TypeConverter and constructor resolution rules. For monetary types, it is usually better to pass or create BigDecimal explicitly:

~~~text
new com.example.Money(T(java.math.BigDecimal).valueOf(125.50), 'USD')
~~~

## 3. Objects Created with new Are Not Spring Beans

An object created by a constructor expression is a plain new Java object. The Spring container does not automatically register that object as a bean merely because the expression was evaluated inside a Spring application.

Example:

~~~text
new com.example.PaymentService()
~~~

This expression calls the PaymentService constructor directly. It does not ask ApplicationContext to look up a PaymentService bean and does not trigger bean creation steps like when the container initializes a component.

A Spring-managed bean can be created via component scanning, Java configuration, XML configuration, or other bean registration mechanisms. The container retains responsibility for initialization, dependency injection, post-processing, proxies, and lifecycle.

Therefore, the following two forms have different meanings:

~~~text
new com.example.PaymentService()
@paymentService
~~~

- **new com.example.PaymentService()** creates a new instance via constructor.
- **@paymentService** references the bean named paymentService through the EvaluationContext's BeanResolver.

Bean references only work when the context is configured with a suitable BeanResolver. In Spring applications, the integration layer typically uses BeanFactoryResolver. Not every EvaluationContext automatically has bean resolution.

Do not use new to replace @beanName or constructor injection when an object needs to be managed by the container.

## 4. Why Manually Instantiating Dependencies Loses Control

A service or repository typically has dependencies and behavior tied to the application's configuration. If you call new manually, those dependencies are not automatically supplied by Spring.

Example:

~~~java
public class InvoiceService {
    private final InvoiceRepository repository;

    public InvoiceService(InvoiceRepository repository) {
        this.repository = repository;
    }
}
~~~

If you write:

~~~text
new com.example.InvoiceService()
~~~

the expression cannot automatically know which InvoiceRepository bean to retrieve. The current constructor also requires an argument, so an expression without matching arguments will fail. Even if arguments are passed manually, the InvoiceService object remains an expression-created object and does not automatically become a managed bean.

Manually creating services can cause the following issues:

- **Dependencies are not injected:** repositories, clients, configuration, or dependent services do not appear automatically.
- **Lifecycle is bypassed:** the container does not manage initialization callbacks, destruction callbacks, or post-processing steps as it does for beans.
- **Proxies are not applied:** proxy-based mechanisms such as transactions, method security, caching, or asynchronous interception may not function on manually created objects.
- **Scopes are not applied:** the object does not follow singleton, request, session, or custom bean scopes.
- **Configuration is scattered:** object creation and dependency wiring can be duplicated across multiple expressions.
- **Testing is harder:** it is difficult to replace dependencies with mocks or test doubles through standard container configuration.
- **State is duplicated:** each expression evaluation can create a new instance instead of using a centrally managed and configured instance.

Even when a constructor receives a bean as an argument, the new object still does not automatically become a Spring bean. It only receives the passed reference; the container does not manage the lifecycle of that object itself.

## 5. Use Constructor Injection for Dependencies

For application dependencies, let Spring create the object and supply dependencies via constructor injection.

Example:

~~~java
@Service
public class InvoiceService {
    private final InvoiceRepository repository;
    private final TaxCalculator taxCalculator;

    public InvoiceService(
            InvoiceRepository repository,
            TaxCalculator taxCalculator) {
        this.repository = repository;
        this.taxCalculator = taxCalculator;
    }

    public Invoice calculate(InvoiceRequest request) {
        // Business logic using repository and taxCalculator.
        return new Invoice();
    }
}
~~~

The Spring container locates beans matching the InvoiceRepository and TaxCalculator types and passes them into the constructor when creating InvoiceService.

Benefits:

- Dependencies are declared explicitly in the constructor.
- The object cannot be created if required dependencies are missing.
- The container manages instantiation and lifecycle steps.
- Beans can be swapped in tests via test configuration or mock beans.
- Proxies and post-processing can be applied per Spring configuration.
- Dependency wiring rules are centralized rather than repeated in expressions.

In SpEL, if you genuinely need to reference a container-managed bean, use a bean reference with an EvaluationContext that has a BeanResolver:

~~~text
@invoiceService
~~~

However, bean references should be used deliberately in controlled configuration expressions. For ordinary business logic, invoking services from Java code via dependency injection is usually clearer and easier to test.

## 6. When Is Using new Appropriate?

Constructor expressions remain useful when the created object is merely an intermediate value or a simple object that does not need Spring management.

Typically appropriate cases:

- Creating immutable value types such as BigDecimal or small value objects.
- Creating simple DTOs for calculations or expressions.
- Creating an object with no bean dependencies, no need for proxies, and no need for Spring lifecycle.
- Creating a new value from arguments already available in the expression.
- Using a constructor in an internal, fixed, controllable expression.

Example:

~~~text
new java.math.BigDecimal('99.95')
~~~

~~~text
new com.example.Range(10, 20)
~~~

~~~text
new java.lang.String('approved')
~~~

These examples create values from concrete arguments. They do not require the container to manage the object.

Before using new, ask yourself:

1. Does this object need a repository, service, client, or other dependency?
2. Does the object need transactions, security, caching, or proxies?
3. Does the object need Spring configuration, lifecycle callbacks, or scopes?
4. Does the object need to be shared and centrally managed?
5. Is creating a new object on every expression evaluation appropriate?

If the answer to any of the above questions is yes, consider redesigning so Spring manages the object or perform the logic in a Java service.

## 7. Constructor Expressions and Bean References in the Same EvaluationContext

StandardEvaluationContext supports constructor resolution and can be further configured with TypeLocator, ConstructorResolver, and BeanResolver. However, a context supporting many capabilities does not mean every expression should use all of them.

Example creating a context with bean resolution in a Spring application:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setBeanResolver(new BeanFactoryResolver(applicationContext));
~~~

Then an expression can reference a bean:

~~~text
@invoiceService
~~~

While a constructor expression still creates a new object:

~~~text
new com.example.Range(10, 20)
~~~

The two syntaxes do not replace each other. One retrieves an instance managed by the container; the other calls a constructor to create a new instance.

If an expression needs both a new value object and an existing bean, they can be combined when the context is properly configured and the expression source is trusted. However, if the expression begins accumulating multiple service calls or business logic, move that part into Java so dependencies and execution flow remain explicit.

## 8. EvaluationContext and Constructor Limitations

StandardEvaluationContext has a broad feature scope and supports constructor invocation via ConstructorResolver. The default configuration typically uses ReflectiveConstructorResolver.

SimpleEvaluationContext is designed for scoped data binding scenarios. It does not provide constructor references, type references, or bean references. Therefore, expressions using new require an EvaluationContext that supports constructor resolution, such as StandardEvaluationContext with an appropriate configuration.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context = new StandardEvaluationContext();

Expression expression =
    parser.parseExpression("new java.math.BigDecimal('10.25')");

BigDecimal result = expression.getValue(context, BigDecimal.class);
~~~

If the same expression is evaluated in SimpleEvaluationContext, do not expect constructor invocation to work.

When an application has a factory creating EvaluationContext instances, choose the context based on the features genuinely needed. Do not broaden permissions just to make an expression run if that logic can be expressed in Java.

## 9. Safety When Evaluating Constructor Expressions

Constructor invocation increases an expression's capabilities: it can create instances of classes that TypeLocator finds and ConstructorResolver allows calling. If an expression is supplied by a user or untrusted source, this can create unexpected objects or trigger constructors with side effects.

Control principles:

- Evaluate expressions only from trusted or validated sources.
- Do not let end users enter arbitrary SpEL into an ordinary business flow.
- Restrict resolvable classes via TypeLocator when the design permits.
- Restrict constructor resolution and other EvaluationContext capabilities.
- Do not let constructor expressions invoke classes whose constructors write files, open connections, mutate state, or perform unwanted I/O.
- Limit the length and complexity of configured expressions.
- Record expression IDs and versions for error tracing.
- Prefer creating objects in controlled Java code when complex initialization logic is needed.

A fully qualified class name clearly identifies the class, yet it is not a security measure. A class referenced by its full name can still have a constructor unsuitable for calling from an expression.

## 10. Common Errors and How to Diagnose Them

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Class not found | Wrong package, class missing from runtime classpath, or TypeLocator cannot resolve it | Check fully qualified name and class loader |
| No matching constructor found | Wrong argument count or types | Check constructor signature and data types |
| Unexpected constructor overload selected | Ambiguous argument types or unexpected conversion | Use explicit argument types and write tests |
| Expression works in one context but not another | Context does not support constructor invocation | Check ConstructorResolver and context type |
| Manually created service misses dependencies | Constructor requires Spring-managed dependencies | Use constructor injection or controlled bean references |
| Transactions/security/caching do not work | Manually created instance does not go through Spring proxies | Use a Spring-managed bean |
| Every evaluation creates new state | Constructor expression is invoked again whenever evaluated | Put stateful objects in the container if sharing is needed |
| Constructor throws exception | Invalid initialization logic or arguments | Check constructor and input data |

When diagnosing, separate parse errors from evaluation errors. The `new` syntax may parse successfully while the class or constructor is only resolved during evaluation. If the constructor was invoked, the exception may come from the initialization logic inside the class itself.

## 11. Testing Constructor Expressions

Tests should confirm that the class is resolved, the matching constructor is called, and the result has the expected type.

Example with BigDecimal:

~~~java
@Test
void createsValueObjectWithConstructorExpression() {
    ExpressionParser parser = new SpelExpressionParser();
    StandardEvaluationContext context = new StandardEvaluationContext();

    Expression expression =
        parser.parseExpression("new java.math.BigDecimal('10.25')");

    BigDecimal result = expression.getValue(context, BigDecimal.class);

    assertEquals(new BigDecimal("10.25"), result);
}
~~~

If using a business class, test:

- Constructor with exact argument count and types.
- Correct overload is chosen.
- Argument conversion matches the contract.
- Constructor handles null and invalid data properly.
- Expression is evaluated in the same kind of EvaluationContext as production.
- Whether repeated evaluation creates new instances as expected.
- No unintended side effects inside the constructor.

For Spring dependencies, test the container separately: confirm beans are created, dependencies are injected, and required proxies/lifecycle behave properly. Do not use a constructor expression test as a substitute for testing dependency injection.

## 12. Decision Workflow Before Using new

When writing an expression that needs to create an object:

1. **Identify the object's role.** Is this an intermediate value object/DTO or a service/component with dependencies?
2. **Check dependencies.** If the object needs repositories, clients, or other services, identify which beans must supply those dependencies.
3. **Check lifecycle.** Determine whether the object needs Spring proxies, transactions, security, caching, scopes, or callbacks.
4. **Choose the creation mechanism.** Use new for simple objects not needing the container; use constructor injection so Spring builds dependencies.
5. **Keep expressions small.** If constructor arguments or initialization logic grow complex, move to a clearly named Java method.
6. **Check context.** Ensure EvaluationContext supports constructor invocation if new is actually used.
7. **Test.** Confirm constructor, argument types, results, and behavior under repeated evaluation.
8. **Control expression sources.** Do not evaluate arbitrary constructor expressions from untrusted sources.

## 13. Best Practices

- Use new to create simple value objects or intermediate objects.
- Use constructor injection for services, repositories, clients, and components with dependencies.
- Do not expect objects created with new to automatically become Spring beans.
- Do not expect manually created objects to receive AOP proxies, scopes, or lifecycle callbacks.
- Use @beanName only when BeanResolver is configured and the expression has a trusted source.
- Write package-qualified class names when explicit resolution is needed.
- Test constructor overloads and argument types.
- Avoid constructors with side effects in expressions evaluated repeatedly.
- Move complex initialization logic to Java.
- Restrict constructor resolution and TypeLocator when expressions are externally configured.

## 14. Review Checklist

Before accepting a constructor expression, verify:

- [ ] Class name and package are exact.
- [ ] Class is on the runtime classpath.
- [ ] Constructor is accessible and has a matching signature.
- [ ] Argument types and count are identified.
- [ ] Argument conversions are tested.
- [ ] Created object genuinely does not require Spring lifecycle or proxies.
- [ ] Required dependencies are supplied via constructor injection.
- [ ] new is not used to manually create services/repositories/clients that require container management.
- [ ] EvaluationContext supports constructor invocation.
- [ ] Expression source and class scope are controlled.
- [ ] Tests exist for results, constructor errors, and repeated evaluation.

## Conclusion

The new operator in SpEL invokes a Java constructor and creates a new instance when the expression is evaluated. It is suitable for simple value objects or intermediate objects. That object does not automatically become a Spring bean, does not automatically receive dependency injection, and does not automatically go through the container's lifecycle or proxies. For services, repositories, clients, or components needing dependencies, let Spring manage object creation via constructor injection; only use bean references in SpEL when the context and expression source are controlled.