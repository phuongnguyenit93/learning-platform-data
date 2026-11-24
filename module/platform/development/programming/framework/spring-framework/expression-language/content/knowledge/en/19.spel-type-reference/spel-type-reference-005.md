# Accessing Static Constants in SpEL

## 1. What are type references and static members?

Spring Expression Language (SpEL) has the `T(...)` type reference operator to reference a Java class in an expression. After specifying the class, the expression can access static fields, static constants, enum constants, or call static methods of that class.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("T(java.lang.Math).PI");

Double pi = expression.getValue(Double.class);
System.out.println(pi); // 3.141592653589793
~~~

In this example:

- `T(java.lang.Math)` references the `java.lang.Math` class.
- `.PI` accesses the static field `PI` of the class.
- `getValue(Double.class)` retrieves the result as the expected type.

A type reference does not create a new instance. It tells SpEL which class should be referenced to resolve static members.

## 2. T(...) syntax

General syntax:

~~~text
T(fully.qualified.TypeName)
~~~

Class names are usually written with the full package to avoid confusion:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression typeExpression =
        parser.parseExpression("T(java.lang.String)");

Class<?> stringType = typeExpression.getValue(Class.class);
System.out.println(stringType.getName()); // java.lang.String
~~~

The letter `T` must be uppercase. Inside the parentheses is the class name to reference. For classes outside the `java.lang` package, use fully qualified names such as `T(java.time.LocalDate)` or `T(java.math.BigDecimal)`.

StandardTypeLocator has a default import prefix for the java.lang package, so familiar classes in this package can usually be referenced by their short name:

~~~java
Expression expression =
        parser.parseExpression("T(Math).PI");

Double pi = expression.getValue(Double.class);
~~~

Even so, using fully qualified names often makes expressions easier to read when multiple classes share the same name or when readers are unfamiliar with the context's type lookup rules.

## 3. Accessing static constants and static fields

After the type reference, use a dot and the member name to read a static field:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Integer maxInt = parser.parseExpression(
        "T(java.lang.Integer).MAX_VALUE")
        .getValue(Integer.class);

BigDecimal zero = parser.parseExpression(
        "T(java.math.BigDecimal).ZERO")
        .getValue(BigDecimal.class);

System.out.println(maxInt); // 2147483647
System.out.println(zero);   // 0
~~~

Some common static constants:

| Class | Member | Meaning |
|---|---|---|
| `java.lang.Math` | `PI` | The constant pi |
| `java.lang.Math` | `E` | The base of natural logarithms |
| `java.lang.Integer` | `MAX_VALUE` | Maximum int value |
| `java.lang.Integer` | `MIN_VALUE` | Minimum int value |
| `java.math.BigDecimal` | `ZERO` | BigDecimal value equal to 0 |
| `java.math.BigDecimal` | `ONE` | BigDecimal value equal to 1 |
| `java.nio.charset.StandardCharsets` | `UTF_8` | UTF-8 Charset |

Examples:

~~~java
Double pi = parser.parseExpression("T(java.lang.Math).PI")
        .getValue(Double.class);

Integer maxRetries = parser.parseExpression("T(java.lang.Integer).MAX_VALUE")
        .getValue(Integer.class);

BigDecimal defaultAmount = parser.parseExpression("T(java.math.BigDecimal).ZERO")
        .getValue(BigDecimal.class);

Charset charset = parser.parseExpression(
        "T(java.nio.charset.StandardCharsets).UTF_8")
        .getValue(Charset.class);
~~~

The member name must match the referenced class and must be accessible through the evaluation context. If the class or field cannot be resolved, SpEL throws an error when evaluating the expression.

## 4. Accessing enum constants

Enum constants are also static members of an enum class. Use a type reference to select an enum value:

~~~java
Expression expression =
        parser.parseExpression("T(java.time.DayOfWeek).MONDAY");

DayOfWeek day = expression.getValue(DayOfWeek.class);
System.out.println(day); // MONDAY
~~~

For application enums, use the fully qualified package name:

~~~java
Expression expression =
        parser.parseExpression("T(com.example.order.OrderStatus).PAID");

OrderStatus status = expression.getValue(OrderStatus.class);
~~~

You can compare an enum property of the root object with an enum constant:

~~~java
Expression expression = parser.parseExpression(
        "status == T(com.example.order.OrderStatus).PAID");

Boolean paid = expression.getValue(order, Boolean.class);
~~~

Here `status` is read from the root object `order`; the `T(...)` part references the enum class and `PAID` is the constant to compare against. This style avoids comparing enums with string literals while preserving the proper enum data type.

## 5. Calling static methods

A static method is called by placing the method name and argument list after the type reference:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("T(java.lang.Math).max(12, 30)");

Integer maximum = expression.getValue(Integer.class);
System.out.println(maximum); // 30
~~~

Some other examples:

~~~java
Integer parsed = parser.parseExpression(
        "T(java.lang.Integer).parseInt('42')")
        .getValue(Integer.class);

Double squareRoot = parser.parseExpression(
        "T(java.lang.Math).sqrt(81)")
        .getValue(Double.class);

Boolean isNull = parser.parseExpression(
        "T(java.util.Objects).isNull(null)")
        .getValue(Boolean.class);
~~~

Static methods can accept literals, variables, or properties resolved from the context:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("minimum", 5);
context.setVariable("maximum", 18);

Expression expression = parser.parseExpression(
        "T(java.lang.Math).max(#minimum, #maximum)");

Integer result = expression.getValue(context, Integer.class);
System.out.println(result); // 18
~~~

SpEL resolves the method based on the referenced class, method name, argument count, and argument types. For overloaded methods, pass explicit data types if multiple overloads could match or if type conversion produces unexpected results.

## 6. Combining static constants with operations

Static constants can be used in formulas, conditions, or string concatenation:

~~~java
Expression expression = parser.parseExpression(
        "T(java.lang.Math).PI * 2");

Double circumferenceFactor = expression.getValue(Double.class);
~~~

Example using a BigDecimal constant in a condition:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("amount", new BigDecimal("125.00"));

Expression expression = parser.parseExpression(
        "#amount.compareTo(T(java.math.BigDecimal).ZERO) > 0");

Boolean positive = expression.getValue(context, Boolean.class);
~~~

Another way is to call a static method to produce the value for comparison:

~~~java
Expression expression = parser.parseExpression(
        "T(java.lang.Integer).parseInt('100') > 50");

Boolean result = expression.getValue(Boolean.class);
~~~

The type reference only supplies the class and static member; the remaining SpEL operators still behave according to standard expression rules. Use parentheses when a formula has multiple operations to clarify evaluation order.

## 7. Using static members in @Value

In Spring configuration, SpEL is often placed inside `#{...}` of the `@Value` annotation. You can inject a static constant into a bean:

~~~java
@Component
public class MathSettings {
    @Value("#{T(java.lang.Math).PI}")
    private double pi;

    @Value("#{T(java.lang.Integer).MAX_VALUE}")
    private int maximumInteger;

    public double getPi() {
        return pi;
    }

    public int getMaximumInteger() {
        return maximumInteger;
    }
}
~~~

Spring evaluates the expression when processing the bean definition and converts the result to the field type if needed. For static methods, the syntax is similar:

~~~java
@Component
public class RetrySettings {
    @Value("#{T(java.lang.Math).max(3, 5)}")
    private int retryFloor;

    public int getRetryFloor() {
        return retryFloor;
    }
}
~~~

You can inject an enum constant:

~~~java
@Component
public class OrderDefaults {
    @Value("#{T(com.example.order.OrderStatus).PENDING}")
    private OrderStatus initialStatus;
}
~~~

Keep expressions inside annotations short. If a value needs to be computed from multiple conditions or depends on multiple data sources, consider moving the decision logic to Java configuration or a clearly named bean.

## 8. Type references vs. root object and variables

Type references differ from the root object and variables in the evaluation context:

| Syntax | Meaning | Example |
|---|---|---|
| Direct property name | Read a property on the root object | `status` |
| `#name` | Read a variable in the context | `#threshold` |
| `T(...)` | Reference a Java class | `T(java.lang.Math)` |
| `@beanName` | Reference a bean in a context with a bean resolver | `@pricingService` |

They can be combined in the same expression:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setVariable("minimum", 100);

Expression expression = parser.parseExpression(
        "total >= #minimum and status == T(com.example.order.OrderStatus).PAID");

Boolean eligible = expression.getValue(context, Boolean.class);
~~~

In this example, `total` and `status` are read from the root object `order`, `#minimum` is read from a variable, and `T(...)` references the enum class. Distinguishing these data sources keeps expressions clear and easy to configure.

## 9. Using short class names via StandardTypeLocator

StandardTypeLocator is responsible for resolving class names in type references. By default, it uses the appropriate class loader and registers an import prefix for java.lang.

If the application has multiple constants classes in the same package, you can register that package to use short names:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context = new StandardEvaluationContext();

StandardTypeLocator typeLocator = new StandardTypeLocator();
typeLocator.registerImport("com.example.constants");
context.setTypeLocator(typeLocator);

Expression expression =
        parser.parseExpression("T(AppLimits).MAX_RETRIES");

Integer retries = expression.getValue(context, Integer.class);
~~~

In this example, `AppLimits` is searched in the imported package `com.example.constants`. The actual class must be loadable by the class loader used by the type locator.

You can continue using fully qualified names even when imports are registered. Fully qualified names are generally better suited for long-lived stored expressions or expressions shared across modules because they explicitly indicate the referenced class.

## 10. Configuring the class loader and type resolution

The type locator needs a class loader that can see the referenced class. In applications running with custom class loaders, plugin systems, or container environments, a class may exist in the application yet not be visible to the type locator's default class loader.

You can instantiate `StandardTypeLocator` with a specific class loader:

~~~java
StandardTypeLocator typeLocator =
        new StandardTypeLocator(MyApplication.class.getClassLoader());

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeLocator(typeLocator);
~~~

Only configure the class loader when the application actually requires it. In typical Spring applications, the default class loader is usually sufficient to resolve classes on the application classpath.

When SpEL reports that a type cannot be found, check the package/class name, whether the dependency is present on the runtime classpath, and which class loader is attached to the type locator. A type resolution error differs from an error where a static field or method is not found after the class has been loaded successfully.

## 11. Static members and instance members

Static members belong to the class; instance members belong to a specific object.

~~~java
// Static field:
T(java.lang.Math).PI

// Static method:
T(java.lang.Math).max(10, 20)

// Instance property:
customer.name

// Instance method:
customer.getName()
~~~

Do not use a type reference to read a property of an instance that has not been provided. For example, `T(com.example.Customer).name` looks up a static member `name` on the class; it does not mean reading `name` of a `customer` variable.

If you need to operate on an instance, pass a root object, variable, or bean reference into the evaluation context. If you need a fixed value of a class, use `T(...)`.

## 12. Common errors

**Forgetting the uppercase T**

Type references use `T(...)`. Lowercase `t(...)` is not type reference syntax.

**Missing package or confusing classes with the same name**

For classes outside `java.lang`, use a fully qualified name or register an import prefix in `StandardTypeLocator`. If two classes share the same name, the fully qualified name prevents resolving the wrong one.

**Confusing static fields with instance properties**

`T(SomeClass).LIMIT` accesses a static member of the class. `limit` accesses a property of the root object. Choose syntax based on where the data is declared.

**Calling the wrong static method or passing the wrong types**

Method name, argument count, and argument types must match the class's method. For overloaded methods, check input types and expected result types.

**Class missing from runtime classpath**

A class might compile in another module yet be absent from the runtime classpath of the application evaluating the expression. Check runtime dependencies and the class loader.

**Static member is not accessible**

The field or method must be accessible via reflection and the evaluation context in use. A non-existent or inaccessible member will cause an evaluation error.

**Passing untrusted expressions into a permissive context**

Type references and static method calls can significantly expand the operations an expression can perform. Do not evaluate expressions submitted arbitrarily by users with a context that allows broad class and method access.

## 13. Restricting type access when security is needed

StandardEvaluationContext supports a type locator and broad evaluation capabilities. If expressions come from a not-fully-trusted source, allowing arbitrary `T(...)` can let expressions reference classes the application does not wish to expose.

Some principles:

- Only accept expressions from application-controlled sources if type references and static methods are needed.
- Restrict allowed classes using a `TypeLocator` with an allowlist appropriate to the business domain.
- Only expose pure static methods with clear inputs/outputs; avoid methods that cause side effects or access system resources.
- Use a restricted-capability evaluation context when the need is only data binding.
- Do not treat a class or method being static as a safety guarantee.

SimpleEvaluationContext is designed for data binding scenarios with narrower capabilities and does not provide full type references like StandardEvaluationContext. If an expression does not need to reference classes, avoid enabling type access just for convenience.

## 14. Comprehensive example

The following example uses a static constant, a static method, and an enum constant together with data from the root object:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}

public class Order {
    private OrderStatus status;
    private BigDecimal total;

    public Order(OrderStatus status, BigDecimal total) {
        this.status = status;
        this.total = total;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }
}

ExpressionParser parser = new SpelExpressionParser();

Order order = new Order(
        OrderStatus.PAID,
        new BigDecimal("150.00"));

StandardEvaluationContext context =
        new StandardEvaluationContext(order);
context.setVariable("minimum", new BigDecimal("100.00"));

Expression eligibleExpression = parser.parseExpression(
        "status == T(com.example.OrderStatus).PAID "
                + "and total.compareTo(#minimum) >= 0 "
                + "and total.compareTo(T(java.math.BigDecimal).ZERO) > 0");

Boolean eligible =
        eligibleExpression.getValue(context, Boolean.class);

Integer upperBound = parser.parseExpression(
        "T(java.lang.Math).max(10, 20)")
        .getValue(Integer.class);

System.out.println(eligible);   // true
System.out.println(upperBound); // 20
~~~

The first expression reads `status` and `total` from the root object, compares status against an enum constant, uses the variable `#minimum`, and references `BigDecimal.ZERO`. The second expression calls the static method `Math.max`. Each type reference clearly indicates the class owning the needed member.

## 15. Key takeaways

- Use `T(fully.qualified.TypeName)` to reference a Java class in SpEL.
- Use `T(Class).CONSTANT` or `T(Class).FIELD` to read static fields and constants.
- Use `T(Class).method(arguments)` to call static methods.
- Enum constants can be referenced via `T(EnumType).CONSTANT`.
- `StandardTypeLocator` supports the `java.lang` import prefix by default; other packages can be registered or a class loader can be configured.
- Distinguish type references from root object properties, `#name` variables, and `@beanName` bean references.
- Keep static member usage concise in expressions; move multi-step logic into Java configuration or named methods.
- Control type access and static methods when expressions come from untrusted sources.
