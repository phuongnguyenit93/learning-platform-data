# Type Has No Matching Constructor in SpEL

Spring Expression Language (SpEL) can create new objects using the **new** operator. When evaluating an expression, SpEL must find a constructor of the requested type and determine whether that constructor can accept the arguments being passed.

Example:

~~~text
new com.example.Invoice('INV-001', 125.50)
~~~

The expression only works if the Invoice type has a constructor matching these two arguments, or SpEL can convert the arguments to the types required by the constructor. If no compatible constructor exists, evaluation fails.

The "no matching constructor" error typically occurs when the argument count is wrong, argument types are incompatible, values cannot be converted, or the type only has constructors different from how the expression is calling it. Distinguish this error from cases where SpEL cannot find the class or EvaluationContext does not allow constructor expressions.

## 1. Constructor Invocation Syntax

SpEL uses the **new** keyword to create objects:

~~~text
new fully.qualified.Type(argument1, argument2, ...)
~~~

For types in the **java.lang** package, the package name can be omitted:

~~~text
new String('Spring')
new Integer(42)
~~~

For types belonging to other packages, use the fully qualified name:

~~~text
new java.math.BigDecimal('125.50')
new java.util.ArrayList()
new com.example.Invoice('INV-001', 125.50)
~~~

Example in Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();

BigDecimal amount = parser
        .parseExpression("new java.math.BigDecimal('125.50')")
        .getValue(BigDecimal.class);
~~~

SpEL parses the expression, locates the BigDecimal type, selects the constructor accepting a String, and creates a new object. The returned result is a BigDecimal instance.

A constructor invocation can appear inside a larger expression:

~~~text
new com.example.Customer('CUS-001', 'Linh').displayName
~~~

Or pass the newly created object into a method:

~~~text
@invoiceService.create(new com.example.InvoiceDraft('INV-001'))
~~~

In this case, InvoiceDraft's constructor must match the argument INV-001; then the object is passed into the create method of the invoiceService bean.

## 2. How Does SpEL Find a Matching Constructor?

SpEL uses **ConstructorResolver** to locate a constructor capable of handling the type and passed arguments. For standard EvaluationContext setups, Spring provides **ReflectiveConstructorResolver**, an implementation that uses Java reflection to search for constructors on the class.

The selection process can consider compatibility forms:

1. **Exact match:** the argument type matches the constructor parameter type identically.
2. **Inexact match:** the argument type is a subtype assignable to the constructor parameter type.
3. **Match via conversion:** the argument can be converted to the parameter type by a TypeConverter registered in EvaluationContext.

Essentially, SpEL does not merely count arguments. It also determines the type of each argument and checks whether those values can be passed into the constructor.

Example:

~~~java
public class CustomerKey {

    private final String value;

    public CustomerKey(String value) {
        this.value = value;
    }
}
~~~

The following expression matches the constructor:

~~~text
new com.example.CustomerKey('CUS-001')
~~~

However, the following expression does not match because the constructor does not accept two arguments:

~~~text
new com.example.CustomerKey('CUS-001', 'VIP')
~~~

The class exists and the expression syntax is valid, yet there is no constructor accepting the requested number and types of arguments.

## 3. Common Reasons No Matching Constructor Exists

### 3.1. Wrong Number of Arguments

A constructor is declared with a fixed number of parameters. If the expression passes too few or too many arguments, the resolver cannot find a matching signature.

Class example:

~~~java
public class Money {

    public Money(BigDecimal amount, Currency currency) {
        // ...
    }
}
~~~

Wrong expression:

~~~text
new com.example.Money()
~~~

Correct expression:

~~~text
new com.example.Money(
    new java.math.BigDecimal('100.00'),
    T(java.util.Currency).getInstance('VND')
)
~~~

Money has no no-arg constructor. To create the object, both amount and currency must be passed according to the declared signature.

### 3.2. Incompatible Argument Types

Suppose the class has a constructor:

~~~java
public class UserId {

    public UserId(UUID value) {
        // ...
    }
}
~~~

Expression passing a String:

~~~text
new com.example.UserId('8f14e45f-ea4d-4f9a-8a2d-123456789abc')
~~~

SpEL can only invoke the constructor if TypeConverter can convert String to UUID in that context. Do not assume every pair of Java types has a default converter.

A clearer way is to create the UUID first with an appropriate method and pass the result to the constructor:

~~~text
new com.example.UserId(
    T(java.util.UUID).fromString('8f14e45f-ea4d-4f9a-8a2d-123456789abc')
)
~~~

When an expression uses specialized types or converters, verify the EvaluationContext's actual conversion capabilities.

### 3.3. Selecting the Wrong Overload

A class can declare multiple constructors:

~~~java
public class ReportRequest {

    public ReportRequest(String reportId) {
        // ...
    }

    public ReportRequest(String reportId, boolean includeDetails) {
        // ...
    }

    public ReportRequest(String reportId, Locale locale) {
        // ...
    }
}
~~~

Valid expressions for the corresponding signatures:

~~~text
new com.example.ReportRequest('RPT-01')
new com.example.ReportRequest('RPT-01', true)
new com.example.ReportRequest(
    'RPT-01',
    T(java.util.Locale).US
)
~~~

If you pass the wrong count or a value whose type is incompatible with the desired overload, SpEL cannot invoke that constructor. When multiple overloads exist, write expressions with explicitly typed arguments to avoid relying on unnecessary conversions.

### 3.4. Parameter Type Is an Interface or Superclass

A constructor can accept an interface or superclass while the expression passes a concrete implementation. This can be an inexact match if the argument type is assignable to the parameter type.

Example:

~~~java
public class NotificationJob {

    public NotificationJob(List<String> recipients) {
        // ...
    }
}
~~~

An ArrayList can be passed to a constructor expecting a List:

~~~text
new com.example.NotificationJob(new java.util.ArrayList())
~~~

Conversely, if the constructor requires a concrete implementation while the expression produces an incompatible type, SpEL cannot automatically substitute a different object.

### 3.5. Class Only Has Parameterized Constructors, but Expression Calls Empty Constructor

Java does not automatically generate a no-arg constructor if the class has already declared another constructor.

~~~java
public class SearchFilter {

    public SearchFilter(String keyword) {
        // ...
    }
}
~~~

Expression:

~~~text
new com.example.SearchFilter()
~~~

is invalid because SearchFilter has no empty constructor. The right approach is passing keyword:

~~~text
new com.example.SearchFilter('spring')
~~~

If the application genuinely needs to create an empty object, deliberately provide a no-arg constructor or use an appropriate factory method. Do not add an empty constructor merely to make an expression run if it creates an invalid object state.

### 3.6. Constructor Has Restrictive Visibility or Uninstantiable Type

The constructor must be accessible to SpEL's reflection mechanism in the runtime environment. A private constructor or one restricted by modules/security may not be invocable by the default resolver as expected.

Additionally, interfaces and abstract classes cannot be instantiated directly via a regular constructor:

~~~text
new com.example.PaymentProcessor()
~~~

If PaymentProcessor is an interface, the expression cannot create a concrete instance from that interface. Use an instantiable implementation or reference a Spring-managed bean.

### 3.7. Null Arguments and Constructor Overloads

A null value cannot be passed to primitive parameters such as int or boolean. If a class has multiple overloads accepting different reference types, null can also make identifying the intended overload ambiguous.

Example:

~~~java
public class SearchFilter {

    public SearchFilter(String keyword) {
        // ...
    }

    public SearchFilter(Locale locale) {
        // ...
    }
}
~~~

Expression:

~~~text
new com.example.SearchFilter(null)
~~~

does not clearly indicate which constructor is the target. Avoid passing null when multiple reference overloads exist; pass a clearly typed value or call a factory method whose name describes the intent.

## 4. Varargs and Arrays in Constructors

SpEL supports constructors with varargs parameters.

Example:

~~~java
public class AccessRule {

    public AccessRule(String name, String... roles) {
        // ...
    }
}
~~~

You can pass varargs arguments:

~~~text
new com.example.AccessRule('invoice-read', 'ADMIN', 'AUDITOR')
~~~

When an expression supplies more arguments than fixed parameters, the resolver can consider a varargs constructor if the values match the varargs array element type.

SpEL also supports array creation syntax:

~~~text
new int[] {1, 2, 3, 4}
new String[] {'A', 'B', 'C'}
new int[5]
new int[3][4]
~~~

Array construction is a distinct form of constructor expression. When using it, distinguish creating an array from invoking a regular class constructor.

## 5. Type Conversion Can Help Find a Matching Constructor

SpEL uses Spring's ConversionService by default through EvaluationContext's TypeConverter. ConversionService includes common converters and can be extended with custom converters.

For example, a constructor accepting BigDecimal:

~~~java
public class InvoiceAmount {

    public InvoiceAmount(BigDecimal amount) {
        // ...
    }
}
~~~

An expression can use a String to create the BigDecimal inline:

~~~text
new com.example.InvoiceAmount(
    new java.math.BigDecimal('125.50')
)
~~~

This makes the argument type explicit before calling the constructor.

Do not rely on assuming SpEL will automatically convert every String into every domain type. Conversion depends on registered converters and target data types. If no matching converter exists or the converter throws an error, constructor invocation still fails.

### 5.1. Registering a Custom Converter

If the application has custom conversion rules, you can register a Converter with ConversionService and supply that service through EvaluationContext's TypeConverter.

Converter example:

~~~java
public class StringToUserIdConverter
        implements Converter<String, UserId> {

    @Override
    public UserId convert(String source) {
        return new UserId(UUID.fromString(source));
    }
}
~~~

Once the converter is registered in the ConversionService used by the context, SpEL can convert String to UserId when resolving a constructor needing type UserId.

Distinguish two responsibilities:

- **ConstructorResolver** finds a constructor that can accept the argument types.
- **TypeConverter** converts values when needed to match the parameter.

A converter does not invent a missing constructor. It can only help make an existing constructor compatible with an argument.

## 6. Type Resolution vs. Constructor Resolution

Before looking up a constructor, SpEL must identify the type invoked after the new keyword. These are two separate steps:

1. **Type resolution:** TypeLocator finds the class by name in the expression.
2. **Constructor resolution:** ConstructorResolver finds a constructor on that class that can accept the arguments.

Example:

~~~text
new com.example.CustomerKey('CUS-001')
~~~

If CustomerKey is not on the classpath or the classloader cannot see the class, SpEL cannot resolve the type. This is not a "class exists but has no matching constructor" error.

For types outside java.lang, use the fully qualified class name to avoid depending on imports or TypeLocator configuration:

~~~text
new java.math.BigDecimal('10.00')
~~~

If the application uses a custom classloader or module boundaries, ensure TypeLocator can see the class to instantiate. When the class name resolves successfully yet no constructor matches the arguments, then it is a constructor resolution issue.

## 7. Does EvaluationContext Allow Constructor Expressions?

Expression capabilities depend on the EvaluationContext.

- **StandardEvaluationContext** provides full SpEL evaluation strategies and uses reflection by default to resolve constructors.
- **SimpleEvaluationContext** is designed for a restricted feature set and excludes constructor invocation, type references, and bean references.

Therefore, if an expression contains:

~~~text
new com.example.CustomerKey('CUS-001')
~~~

but is evaluated in SimpleEvaluationContext, the error can stem from the context not supporting constructor expressions. Do not misdiagnose this as CustomerKey lacking a constructor.

If creating objects with SpEL is required, use an EvaluationContext that supports this feature and open only the permissions needed for the expression source being processed.

## 8. Do Constructor Expressions Create Spring Beans?

No. The **new** operator invokes a Java constructor to create an object directly. The created object does not automatically become a bean managed by the Spring container.

Example:

~~~text
new com.example.InvoiceDraft('INV-001')
~~~

The expression creates an InvoiceDraft instance. Spring does not automatically perform bean registration, scope management, dependency injection, lifecycle callbacks, or proxy creation for this instance.

If you want to use a Spring-managed bean, reference the bean via **@beanName** syntax in a context with a BeanResolver:

~~~text
@invoiceFactory.createDraft('INV-001')
~~~

The two approaches serve different purposes:

| Syntax | Mechanism | When to Use |
| --- | --- | --- |
| **new com.example.InvoiceDraft(...)** | Calls constructor directly | Creating value objects or short-lived objects |
| **@invoiceFactory.createDraft(...)** | Calls method on a Spring bean | Need factories, dependencies, or Spring-managed object creation rules |
| **@invoiceDraft** | Resolves a registered bean | Using a bean instance provided by the container |

If a constructor needs many dependencies, has complex initialization rules, or the object must be Spring-managed, prefer a factory bean or Java service rather than cramming excessive logic into a constructor expression.

## 9. Distinguishing Error Categories When Creating Objects

When an expression using new fails, identify which stage the error occurs in:

| Error Category | Symptom | Resolution |
| --- | --- | --- |
| Parse error | Invalid new syntax, parentheses, or argument list | Fix expression syntax |
| Type resolution error | Class not found by name | Check fully qualified name, classpath, and TypeLocator/classloader |
| Constructor not found | Class resolved, but no constructor accepts the arguments | Check argument count, types, and overloads |
| Conversion error | Argument needs conversion but lacks a converter or conversion fails | Standardize types or register an appropriate converter |
| Access/invocation error | Constructor is inaccessible or the constructor itself throws an exception | Check visibility, module access, and errors inside the constructor |
| Context restriction | EvaluationContext does not support constructor expressions | Use a context with appropriate capabilities or move object creation to Java |

SpEL evaluation errors are typically wrapped in Spring Expression's exception hierarchy. Read the root message and check the class name, argument types, and expression position to identify the exact cause. Do not just tweak argument counts when the real issue is an unresolved class or a non-working converter.

## 10. How to Diagnose "No Matching Constructor"

When encountering this error, check in the following order:

1. **Confirm the class exists:** Is the class on the runtime classpath and is the name in the expression spelled correctly?
2. **Use the fully qualified name:** For classes outside java.lang, write the fully qualified class name.
3. **List actual constructors:** Check which constructors are declared, parameter counts, and each parameter's type.
4. **Compare arguments:** Determine the types SpEL receives from literals, variables, or nested expressions.
5. **Check conversion:** If the two types differ, determine whether ConversionService has a matching converter.
6. **Check overloads:** If multiple constructors exist, clarify argument types to pick the right overload.
7. **Check EvaluationContext:** Does the context support constructor expressions and have an appropriate ConstructorResolver?
8. **Check accessibility:** Can reflection invoke the constructor in the current runtime/module?
9. **Check constructor body:** If the constructor was invoked and threw an exception, fix the cause in the initialization code.

An illustrative example:

~~~java
public class Money {

    private final BigDecimal amount;

    public Money(BigDecimal amount) {
        this.amount = amount;
    }
}
~~~

An easy-to-understand expression with an explicit argument type:

~~~text
new com.example.Money(
    new java.math.BigDecimal('99.90')
)
~~~

If you write:

~~~text
new com.example.Money('99.90')
~~~

the result depends on the EvaluationContext TypeConverter's ability to convert String to BigDecimal. Explicitly creating BigDecimal inside the expression makes the constructor signature clear and reduces reliance on implicit conversion.

## 11. When Custom Object Creation Rules Are Needed: ConstructorResolver or Factory

If the application requires object creation outside regular reflection-based constructor invocation, SpEL allows extending via **ConstructorResolver**.

A ConstructorResolver is responsible for locating a matching constructor in EvaluationContext and returning a ConstructorExecutor to carry out the call. The default implementation is ReflectiveConstructorResolver.

A custom resolver can be registered in StandardEvaluationContext when needed to:

- Allow creating only a listed set of types.
- Map a logical type name to a custom object creation strategy.
- Support an application-specific instantiation mechanism.
- Restrict or control the set of constructors expressions may invoke.

However, if you simply need to create an ordinary domain object, prefer clear Java constructors and standard converters. If the object requires multiple dependencies, validation, or initialization logic, a factory bean/service is usually more readable than a custom resolver.

Example using a factory:

~~~java
@Component
public class InvoiceDraftFactory {

    public InvoiceDraft create(String invoiceId, Customer customer) {
        // Validate and create InvoiceDraft per application rules
        return new InvoiceDraft(invoiceId, customer);
    }
}
~~~

Expression:

~~~text
@invoiceDraftFactory.create(#invoiceId, #customer)
~~~

This uses a Spring-managed factory bean and allows consolidating validation or initialization logic into an independently testable Java method.

## 12. Testing Constructor Expressions

Small tests can be written to verify the matching constructor is called:

~~~java
class ConstructorExpressionTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    @Test
    void createsMoneyUsingMatchingConstructor() {
        Money money = parser
                .parseExpression(
                    "new com.example.Money(" +
                    "new java.math.BigDecimal('99.90')"
                    + ")"
                )
                .getValue(Money.class);

        assertEquals(new BigDecimal("99.90"), money.getAmount());
    }

    @Test
    void reportsFailureWhenNoMatchingConstructorExists() {
        assertThrows(EvaluationException.class, () ->
                parser.parseExpression(
                    "new com.example.Money('unexpected', 10)"
                ).getValue(Money.class)
        );
    }
}
~~~

The first test confirms the expression uses the right constructor. The second test illustrates the case where no constructor accepts two arguments of String and Integer as supplied by the expression.

In real projects, also verify:

- No-arg constructors and parameterized constructors.
- Overloads with differing parameter types.
- Values requiring conversion.
- Varargs constructors.
- Uninstantiable types or inaccessible constructors.
- Restricted contexts that disallow constructor expressions.

If a constructor contains business logic, test that logic directly with Java unit tests. SpEL tests only confirm that the expression can resolve and invoke the constructor properly.

## 13. Quick Takeaways

- SpEL creates objects using the **new fully.qualified.Type(arguments)** syntax.
- For types in java.lang, the package can be omitted; other types should use the fully qualified name.
- SpEL supports varargs and array creation syntax.
- ConstructorResolver finds constructors by argument types and count.
- ReflectiveConstructorResolver evaluates exact matches, subtype-compatible matches, and convertibility via TypeConverter.
- There is no empty constructor if a class has declared other constructors without explicitly providing a no-arg constructor.
- Constructor expressions can fail due to wrong arity, incompatible types, failed conversion, or inaccessible constructors.
- Type resolution and constructor resolution are two separate steps.
- SimpleEvaluationContext excludes constructor invocation; StandardEvaluationContext provides fuller capabilities.
- **new** creates Java objects directly, not Spring-managed beans.
- Use a factory bean/service when object creation needs dependencies, validation, or Spring-managed lifecycle.
- When errors occur, check class, constructor signatures, argument types, converters, resolvers, and EvaluationContext in order.

## 14. Official References

- [Spring Framework — Constructor Expressions](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/constructors.html)
- [Spring Framework — EvaluationContext and Type Conversion](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [ReflectiveConstructorResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/ReflectiveConstructorResolver.html)
- [ConstructorResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ConstructorResolver.html)
- [SimpleEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
