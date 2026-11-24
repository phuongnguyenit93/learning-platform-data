# Automatic java.lang Referencing

In SpEL, the type reference operator T(...) allows an expression to access a Java class by type name. Normally, the class name needs to be fully qualified, such as T(java.time.LocalDate). However, with the default StandardEvaluationContext and StandardTypeLocator, the java.lang package is already pre-registered. Therefore, common types like String, Integer, or Math can be referenced without writing the java.lang prefix.

This mechanism makes expressions more concise, but it does not mean SpEL automatically imports every package like import statements in Java code. It is important to understand the scope of the default package, how type names are resolved, and how to register other packages when the application actually needs them.

## 1. What is a type reference T(...)?

T(...) is SpEL's type reference operator. The part inside parentheses is the class name that EvaluationContext will resolve into a Class object.

Example:

    T(String)
    T(Integer)
    T(Math)

For types belonging to other packages:

    T(java.time.LocalDate)
    T(java.math.BigDecimal)
    T(com.example.domain.Order)

The result of a type reference is a reference to the Java type, not a new instance of that class. From the type reference, SpEL can access static members or use the type in certain other checks.

For example, reading the PI constant:

    T(Math).PI

Calling a static method:

    T(String).valueOf(123)

Checking runtime type:

    #value instanceof T(String)

If you want to create a new object, the syntax is new, not just T(...):

    new java.math.BigDecimal('125.50')

Therefore, distinguish three intents: T(...) references the class, the dot after the type reference accesses a member of the class, and new invokes a constructor to create an instance.

## 2. Why is java.lang referenced automatically?

java.lang is the package containing many foundational Java types, such as:

- String, Object, and Class.
- Wrapper classes like Integer, Long, Double, and Boolean.
- Math, System, and Runtime.
- Exception types and many other foundational utility classes.

In StandardEvaluationContext, the default TypeLocator is StandardTypeLocator. When instantiated with its default configuration, this locator already has the java.lang package prefix registered. Therefore, when it encounters a short type name like String, it tries to resolve that name within the registered package.

For example, both of the following notations reference the String class:

    T(String)

    T(java.lang.String)

The short form works thanks to the default package prefix. The fully qualified form explicitly states the package and remains valid when you do not want to rely on import prefixes.

## 3. Examples using String, Integer, and Math

You can take advantage of types in java.lang to call static methods or read constants:

    T(String).valueOf(2026)

The expression returns the string "2026".

    T(Integer).MAX_VALUE

The expression returns the maximum value of the int type.

    T(Math).max(15, 28)

The expression returns the larger of the two values.

You can write the full package to express the same intent:

    T(java.lang.Math).max(15, 28)

Short names keep expressions compact, especially when they appear multiple times in configuration. Fully qualified names are useful in technical documentation, expressions with multiple classes sharing the same name, or when you want the reader to immediately recognize the exact source of the referenced type.

Note that T(Integer).MAX_VALUE reads a static member of the Integer class. It is not an instance variable and does not create a new Integer object.

## 4. Example evaluating a type reference in Java

To use a type reference, you need an EvaluationContext with a supporting TypeLocator. The following example uses the default StandardEvaluationContext:

    ExpressionParser parser = new SpelExpressionParser();

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    Expression expression =
            parser.parseExpression("T(String).valueOf(123)");

    String result = expression.getValue(context, String.class);

In this example:

1. StandardEvaluationContext provides the expression evaluation environment.
2. The default TypeLocator resolves the short name String to java.lang.String.
3. The dot accesses the static method valueOf.
4. getValue evaluates the expression and converts the result to the requested String type.

The result is the string "123".

You can read a static constant in a similar way:

    Expression maxExpression =
            parser.parseExpression("T(Integer).MAX_VALUE");

    Integer maxValue =
            maxExpression.getValue(context, Integer.class);

If an expression needs another type, you can use the fully qualified name of that type or register the appropriate package prefix in TypeLocator.

## 5. Packages other than java.lang are not automatically imported

The fact that java.lang is registered by default does not mean every package on the classpath can use short names.

For example, the following expression usually cannot be resolved using only the short class name:

    T(LocalDate)

LocalDate belongs to the java.time package, not java.lang. There are two appropriate ways to write it:

    T(java.time.LocalDate)

or register the java.time package prefix on TypeLocator:

    T(LocalDate)

Similarly, BigDecimal belongs to java.math, so it can be referenced fully with:

    T(java.math.BigDecimal)

Do not assume that a package imported in the application's Java file also automatically takes effect in SpEL. The Java compiler and SpEL TypeLocator are two independent name resolution mechanisms.

## 6. Registering package prefixes with StandardTypeLocator

If multiple expressions need to reference types in the same package, you can register the package prefix once in TypeLocator.

Example:

    StandardTypeLocator typeLocator =
            new StandardTypeLocator();

    typeLocator.registerImport("java.time");

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setTypeLocator(typeLocator);

After registering, expressions can use the short name:

    T(LocalDate).of(2026, 11, 12)

The default StandardTypeLocator object still has the java.lang package prefix. Registering java.time additionally expands the list of searched packages.

If a package prefix is no longer needed, you can remove it with:

    typeLocator.removeImport("java.time");

registerImport accepts a package name, not an individual class name. For example, use java.time to resolve LocalDate; do not register java.time.LocalDate as a package.

If there are multiple classes with the same simple name in different packages, use the fully qualified name in the expression to avoid depending on the package prefix list and resolution order.

## 7. Complete example with java.time.LocalDate

You can configure TypeLocator so the expression uses the concise LocalDate name:

    ExpressionParser parser = new SpelExpressionParser();

    StandardTypeLocator typeLocator =
            new StandardTypeLocator();

    typeLocator.registerImport("java.time");

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setTypeLocator(typeLocator);

    Expression expression =
            parser.parseExpression("T(LocalDate).of(2026, 11, 12)");

    LocalDate date =
            expression.getValue(context, LocalDate.class);

The expression references the LocalDate class, then calls the static method of to create a date value. This is a static call on the class; it is not an instance creation operation using the new operator.

If you do not want to configure a package prefix, you can write it directly:

    T(java.time.LocalDate).of(2026, 11, 12)

This fully qualified form is suitable for standalone expressions or when you want to reduce dependence on TypeLocator configuration.

## 8. TypeLocator and class loader

TypeLocator does not create or install libraries itself. It only looks up a type by name in the class loader environment it uses.

StandardTypeLocator has a default constructor and a constructor accepting a ClassLoader. If the application runs in an environment with its own class loader, such as an application server, plugins, or certain application packaging setups, you can supply the appropriate class loader:

    StandardTypeLocator typeLocator =
            new StandardTypeLocator(
                    MyApplication.class.getClassLoader());

Then you can register package prefixes as usual:

    typeLocator.registerImport("com.example.domain");

This helps TypeLocator find application classes according to the specified class loader. However, the class must still be present on the runtime classpath/module path and be loadable by that class loader. Registering a package prefix does not replace declaring dependencies or packaging libraries.

If you encounter a type-not-found error, check the fully qualified class name, registered package prefixes, and the class loader in use. Do not simply keep adding package prefixes when the class is not actually present at runtime.

## 9. StandardEvaluationContext and SimpleEvaluationContext

Not every EvaluationContext supports type references.

StandardEvaluationContext provides a fuller SpEL feature set and uses StandardTypeLocator by default. This is the right choice when expressions need T(...), static member access, or other advanced features.

SimpleEvaluationContext is designed for a more limited feature set, focusing on configured property and method access. It does not support type references by default. Therefore, the expression:

    T(String).valueOf(123)

is not suitable for an ordinary property-reading SimpleEvaluationContext.

If an expression only needs to read data from the root object, prefer a context with narrower permissions. If type references are genuinely needed, use StandardEvaluationContext and restrict other capabilities according to application needs.

## 10. Distinguishing type references from variables and property names

Type names, context variables, and root object properties are three different kinds of references.

| Notation | Meaning |
|---|---|
| T(String) | References the java.lang.String class |
| #name | Reads the variable name in EvaluationContext |
| name | Reads the property name on the root object |
| T(Math).PI | Reads the static member PI of Math |
| new String('hello') | Creates a String instance via constructor |

If you write #String, SpEL looks for a variable named String rather than interpreting it as the String class. If you write String without T(...), it is interpreted as a property or identifier in the expression context, not a type reference.

Use T(...) whenever the goal is to reference a Java type.

## 11. Common errors when referencing types

| Expression or situation | Cause | Resolution |
|---|---|---|
| T(LocalDate) type not found | java.time is not registered | Use the fully qualified name or register java.time |
| T(String) fails with restricted context | Context does not support type references | Use StandardEvaluationContext when T(...) is needed |
| T(java.time.LocalDate) class not found | Class is not in runtime or class loader cannot see it | Check dependencies and class loader |
| Using #String to reference the class | # denotes a context variable | Use T(String) |
| Using T(String) when wanting to create an object | T only references the class | Use new with the appropriate constructor |
| Two packages have classes with the same short name | Short name may resolve to an unintended type | Use the fully qualified package name |

When analyzing errors, distinguish syntax parse errors from type resolution errors during evaluation. An expression may be syntactically valid yet TypeLocator fails to find the class. In that case, checking the package and class loader is more helpful than changing other operators in the expression.

## 12. Security boundaries when using type references

Type references can expand what an expression can do. Once a class is resolved, the expression can read static fields or invoke static methods that the context permits. Therefore, do not take arbitrary expressions from external users and evaluate them with a broadly permissive StandardEvaluationContext.

Some operational principles:

- Only evaluate expressions from trusted or governed sources.
- Only register package prefixes that rules actually need.
- Use fully qualified names and type allowlists where possible to restrict referencable classes.
- Do not place privileged beans or objects into the context if expressions do not need them.
- Restrict method resolvers and property accessors to the exact scope of use.
- Test expressions and handle type resolution errors before deploying rules into critical business flows.

If type references are not needed, use SimpleEvaluationContext with a smaller feature set. If T(...) is needed, configure StandardEvaluationContext deliberately, rather than treating every SpEL expression as a harmless text string.

## 13. When to use short names and when to use fully qualified names?

Short names are suitable when the type belongs to the java.lang package that is registered by default, or when the application actively registers a package prefix and a group of expressions uniformly uses that configuration.

Example:

    T(String)
    T(Integer)
    T(LocalDate)

Fully qualified names are suitable when:

- The expression appears only once and does not warrant additional package configuration.
- There are multiple classes with the same name in different packages.
- You want the expression to be self-describing regarding its package without depending on TypeLocator configuration.
- Rules are transferred between applications with different package prefix lists.

Example:

    T(java.lang.String)
    T(java.time.LocalDate)
    T(java.math.BigDecimal)

Using short names reduces length; using fully qualified names reduces ambiguity. Prioritize rule clarity and configuration stability.

## Conclusion

With the default StandardEvaluationContext and StandardTypeLocator, the java.lang package is already registered, so types such as String, Integer, and Math can be referenced using T(String), T(Integer), and T(Math). Other packages are not automatically imported; use fully qualified names or register package prefixes with StandardTypeLocator.registerImport().

T(...) returns a reference to a class, allowing access to static members and use in expressions such as instanceof. It does not create instances; object creation uses the new syntax. SimpleEvaluationContext does not support type references by default, so choose the appropriate context. Because type references can open up access to class members, evaluate expressions only from trusted sources and restrict the types allowed to be referenced.