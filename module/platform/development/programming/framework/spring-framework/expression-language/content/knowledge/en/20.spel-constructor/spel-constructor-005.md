# ConstructorResolver and Constructor Selection

In Spring Expression Language (SpEL), an expression can create a Java object using the **new TypeName(arguments)** syntax. When evaluating this expression, SpEL must find a constructor matching the requested type and the evaluated arguments. The component responsible for locating constructors is **ConstructorResolver**.

In **StandardEvaluationContext**, SpEL uses **ReflectiveConstructorResolver** by default to find constructors invocable via reflection. Constructor selection depends on the number of arguments, their actual data types, and the type conversion capabilities of the EvaluationContext. Therefore, when a class has multiple overloaded constructors, the types of the arguments play an important role.

## Object Creation Syntax in SpEL

General syntax:

~~~text
new fully.qualified.TypeName(argument1, argument2, ...)
~~~

The type name is written after the **new** keyword. The arguments are SpEL expressions that can be evaluated into values passed to the constructor.

For example, creating a BigDecimal from a string:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

Expression expression =
        parser.parseExpression("new java.math.BigDecimal('19.95')");

BigDecimal price =
        expression.getValue(context, BigDecimal.class);
~~~

The expression requests creating a BigDecimal instance using the constructor accepting a String. The result is a BigDecimal object with value 19.95.

For types in the **java.lang** package, SpEL can use short names because this package is imported by default in the type resolution mechanism:

~~~java
String message =
        parser.parseExpression("new String('Hello')")
                .getValue(context, String.class);
~~~

For types in other packages, use the fully qualified name so the expression unambiguously identifies the class to create. Constructor invocation does not require wrapping the class name in **T(...)**; the **T(...)** syntax is reserved for type references.

## Role of ConstructorResolver

**ConstructorResolver** is a SpEL extension point used to find a matching constructor for a type and argument list. The resolver receives information about the target type along with the argument types, then returns a constructor executor if a suitable candidate is found.

In the default configuration, **StandardEvaluationContext** includes **ReflectiveConstructorResolver**. This resolver uses reflection to locate accessible constructors on the target class and determine which constructor matches the arguments.

The processing flow can be visualized as follows:

1. The parser parses the string and produces an Expression.
2. When the Expression is evaluated, SpEL resolves the type name after the new keyword into a Class.
3. The constructor arguments are evaluated in the EvaluationContext.
4. ConstructorResolver finds a constructor matching the argument count and types.
5. SpEL applies type conversion if the context supports it and it is needed.
6. The constructor is executed and the new object is returned.

The parser only checks syntactic structure. Class lookup, constructor selection, and execution occur during the evaluation phase.

## Default ReflectiveConstructorResolver

With StandardEvaluationContext, applications typically do not need to register a custom ConstructorResolver for standard cases:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("new java.util.ArrayList()");

List<?> result =
        expression.getValue(context, List.class);
~~~

SpEL resolves java.util.ArrayList, finds the matching no-arg constructor, and creates a new instance. The returned object is a mutable ArrayList per that Java class's behavior.

If the constructor requires arguments, the expression can pass literals or values retrieved from the context:

~~~java
context.setVariable("initialCapacity", 20);

Expression expression =
        parser.parseExpression(
                "new java.util.ArrayList(#initialCapacity)");

List<?> result =
        expression.getValue(context, List.class);
~~~

The **#initialCapacity** variable is evaluated first and passed to the corresponding constructor. The runtime type of the variable is Integer, matching the constructor taking an int capacity after corresponding conversion/unboxing.

## Selecting a Constructor When Overloads Exist

A Java class can declare multiple constructors with the same class name but different parameter counts or types:

~~~java
public class Coordinate {
    private final double x;
    private final double y;

    public Coordinate(double x, double y) {
        this.x = x;
        this.y = y;
    }

    public Coordinate(String pair) {
        String[] parts = pair.split(",");
        this.x = Double.parseDouble(parts[0]);
        this.y = Double.parseDouble(parts[1]);
    }

    public double getX() {
        return x;
    }

    public double getY() {
        return y;
    }
}
~~~

Each overload can be called using an appropriate expression:

~~~java
Coordinate point1 =
        parser.parseExpression(
                "new com.example.Coordinate(10.0, 20.0)")
                .getValue(context, Coordinate.class);

Coordinate point2 =
        parser.parseExpression(
                "new com.example.Coordinate('10,20')")
                .getValue(context, Coordinate.class);
~~~

The first expression passes two numeric arguments, so the constructor accepting two double parameters is the matching candidate. The second expression passes a String, so the constructor accepting a String is selected.

The number of arguments usually eliminates non-matching constructors. When multiple overloads have the same parameter count, SpEL must examine argument types and conversion possibilities to pick a compatible candidate.

## Argument Types and Type Conversion

EvaluationContext has a **TypeConverter** to assist in converting a value when an argument does not yet have the exact constructor parameter type but is convertible.

For example, the Point class has a constructor accepting two integers:

~~~java
public class Point {
    private final int x;
    private final int y;

    public Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    public int getX() {
        return x;
    }

    public int getY() {
        return y;
    }
}
~~~

You can pass string literals if the context's TypeConverter supports converting String to integer:

~~~java
Expression expression =
        parser.parseExpression(
                "new com.example.Point('10', '20')");

Point point =
        expression.getValue(context, Point.class);
~~~

In a typical Spring environment, StandardTypeConverter relies on Spring's conversion mechanism to support many common conversions. However, do not assume every type can be converted. If no suitable converter exists, evaluation will fail.

When data comes from variables or properties, supply explicit data types whenever possible. Passing the exact type generally makes overload selection more predictable and reduces reliance on implicit conversion.

## Overloads Can Cause Ambiguity

If a class has multiple constructors accepting parameter types that can be converted from the same input value, the selection may be unclear. This situation often arises when overloaded constructors use closely related types, wrapper types, numeric types, or null values.

Example:

~~~java
public class UserKey {
    public UserKey(String value) {
        // ...
    }

    public UserKey(UUID value) {
        // ...
    }
}
~~~

An expression passing an explicit String:

~~~java
new com.example.UserKey('user-123')
~~~

will target the constructor accepting String. However, if the expression passes null or a value convertible in multiple ways, overload selection may no longer be obvious.

Do not rely on an implicit overload selection rule when the outcome carries business meaning. Pass explicitly typed variables, use a constructor with an unambiguous signature, or create a static factory method with a name clearly expressing intent.

For example, instead of multiple hard-to-distinguish overloads, the API can provide **UserKey.fromText(...)** and **UserKey.fromUuid(...)**. Expressions or Java code can then invoke the intended factory method directly.

## Argument Count and Varargs

ConstructorResolver must also consider argument count. A no-arg constructor matches only when the expression passes zero arguments; a parameterized constructor must receive the corresponding number of arguments, including varargs cases supported by the reflection mechanism.

~~~java
public class TagSet {
    private final List<String> tags;

    public TagSet(String... tags) {
        this.tags = List.of(tags);
    }
}
~~~

If using a varargs constructor, supply the arguments in a way that SpEL and the resolver of the Spring version in use can map properly. For complex expressions or overloads combined with varargs, verify with tests on the exact Spring version rather than relying on assumptions from syntax.

If argument mapping becomes confusing, a factory method with a clear signature is usually a more stable API for expressions.

## Custom ConstructorResolver

An application can register its own **ConstructorResolver** in StandardEvaluationContext when it needs control over how constructors are found and executed.

A custom resolver can be useful when:

- Only allowing specific object types to be created.
- Applying custom constructor selection rules.
- Creating objects through a factory or special instantiation mechanism.
- Restricting which constructors external expressions are permitted to invoke.
- Integrating with a different object model or container.

StandardEvaluationContext provides APIs to configure the list of constructor resolvers, for example via **setConstructorResolvers(...)** or adding a resolver per the corresponding Spring version's API. When modifying the default list, explicitly decide whether to retain ReflectiveConstructorResolver.

A custom resolver should explicitly reject disallowed types or constructors. Do not implement a resolver that only checks type names while ignoring constructor permissions or side effects during initialization.

## Constructor Invocation and SimpleEvaluationContext

**SimpleEvaluationContext** is designed for a subset of SpEL capabilities, primarily intended for data binding with a restricted access surface. It does not support constructor invocation like StandardEvaluationContext.

For example, do not expect the following expression to run in SimpleEvaluationContext:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

Expression expression =
        parser.parseExpression("new java.math.BigDecimal('19.95')");
~~~

If the use case requires creating objects with the new syntax, use a context that supports constructor invocation and configure appropriate access permissions. If only reading DTO properties is required, do not broaden the context to StandardEvaluationContext just to add unnecessary capabilities.

## Errors When Selecting or Executing a Constructor

A constructor expression can fail for several reasons:

- **Type cannot be resolved:** wrong class name, dependency missing from the runtime classpath, or ClassLoader cannot see the class.
- **No matching constructor found:** no accessible constructor matches the supplied argument count and types.
- **Arguments cannot be converted:** TypeConverter does not support converting the input type to the parameter type.
- **Ambiguous overload:** multiple constructors could match without a clear single choice.
- **Constructor throws an exception:** logic inside the constructor fails while creating the object.
- **Context does not support constructor invocation:** e.g., using SimpleEvaluationContext for the new syntax.

Distinguish parse errors from evaluation errors. The string **new com.example.Point(1, 2)** may be syntactically valid, but if the class does not exist or has no compatible constructor, the error only appears during evaluation.

~~~java
Expression expression;

try {
    expression = parser.parseExpression(
            "new com.example.Point(10, 20)");
} catch (ParseException ex) {
    throw new IllegalArgumentException("Invalid SpEL syntax", ex);
}

try {
    Point point =
            expression.getValue(context, Point.class);
} catch (EvaluationException ex) {
    throw new IllegalStateException(
            "Cannot resolve or invoke constructor", ex);
}
~~~

When logging, record the expression identifier and error type along with necessary target-type details. Avoid logging full arguments if they might contain sensitive data.

## Constructors Can Have Side Effects

Invoking a constructor is not always a pure operation. A constructor can read configuration, allocate resources, open connections, write logs, or execute other logic.

If an expression is evaluated multiple times, new objects can be created multiple times and side effects can repeat. Therefore, do not use constructor invocation in expressions that the framework evaluates frequently if object creation carries significant cost or side effects.

For domain objects or services needing lifecycle management, dependency injection and factory/service methods are generally more appropriate than direct creation via SpEL. Constructor invocation is best suited for small values or objects with straightforward initialization and minimal side effects.

## Safety When Evaluating Expressions from External Sources

Allowing constructor invocation in a broad evaluation context can give expressions the ability to create Java types resolvable by TypeLocator and ConstructorResolver. A user-provided expression could attempt to create objects outside the application's original intent.

If you must evaluate external expressions:

- Restrict resolvable types using an appropriate TypeLocator.
- Restrict constructors via an allowlist ConstructorResolver if the use case needs object creation.
- Use a small root object and supply only necessary variables.
- Avoid exposing constructors that can create resources or perform side effects.
- Limit expression sources, length, and editing permissions.
- Handle parse errors, constructor resolution errors, and initialization exceptions separately.

Package imports or merely using fully qualified class names are not security mechanisms. Object creation permissions depend on the type resolution, constructor resolver, and context provided by the application.

## When Should Constructor Invocation Be Used in SpEL?

The **new ...(...)** syntax is appropriate when you need to create a simple object directly inside an expression, such as:

- Creating a BigDecimal from a controlled numeric string.
- Creating a small value type with a clear constructor.
- Creating a utility collection or object in a restricted configuration.
- Creating an intermediate value at a Spring integration point supporting SpEL.

If the object needs lifecycle management, has side effects, requires dependency injection, or contains complex business logic, create it in Java or through an appropriate Spring bean/factory. This clarifies initialization responsibilities and makes testing easier.

## Conclusion

**ConstructorResolver** is responsible for finding a matching constructor for SpEL expressions using the **new TypeName(arguments)** syntax. StandardEvaluationContext uses ReflectiveConstructorResolver by default; overload selection depends on argument count, argument types, and the context's conversion capabilities. If no compatible constructor is found or the constructor fails, the error occurs during the evaluation phase.

When overloads exist, pass explicit argument types and avoid ambiguous cases such as null or multi-way conversions. Use a custom ConstructorResolver when you need to restrict or customize object creation. Because constructors can produce side effects, only allow expressions to create appropriate objects and never evaluate untrusted strings in a broadly privileged context.
