# Invoking Static Methods via Type Reference

In Spring Expression Language (SpEL), a **type reference** allows an expression to reference a Java type via the **T(...)** operator. Once the type is referenced, the expression can invoke **static methods** or read **static fields** of that type.

This syntax is useful when an expression needs to use a utility function, constant, or enum value without needing an instance object as the root object. Common examples are calling **Math.max(...)**, generating a UUID with **UUID.randomUUID()**, or reading the **Math.PI** constant.

## T(...) syntax and static methods

General syntax:

~~~text
T(fully.qualified.TypeName).staticMethod(arguments)
~~~

Where:

- **T(...)** is SpEL's type reference operator.
- The content inside parentheses is the Java type name that the type locator can resolve.
- After the dot is a static method of that type.
- Arguments are passed according to the method signature and SpEL's type conversion rules.

Example of calling the Math.max method:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

Expression expression =
        parser.parseExpression("T(java.lang.Math).max(10, 25)");

Integer result =
        expression.getValue(context, Integer.class);
~~~

The result is 25. The expression directly references the java.lang.Math type and calls the static method max. There is no need to instantiate a Math object because the methods in Math are static.

Other static methods can be invoked:

~~~java
Double randomValue =
        parser.parseExpression("T(java.lang.Math).random()")
                .getValue(context, Double.class);

Integer absoluteValue =
        parser.parseExpression("T(java.lang.Math).abs(-12)")
                .getValue(context, Integer.class);
~~~

In these examples, **random()** and **abs(...)** are invoked on the Math type. The result depends on the called method and arguments, rather than on a root instance object.

## Type reference is not an instance method call

Distinguish invoking a static method via a type reference from invoking an instance method on an object:

~~~java
// Invoke static method on a Java type
Expression staticCall =
        parser.parseExpression("T(java.lang.Math).max(10, 25)");

// Invoke instance method on the root object
Expression instanceCall =
        parser.parseExpression("name.toUpperCase()");
~~~

The first expression locates the Math type and calls the static method max. The second expression reads the name property from the root object and calls the instance method toUpperCase on that value, if the evaluation context allows it.

Another way to distinguish them:

| Syntax | Meaning |
|---|---|
| **T(java.lang.Math).max(1, 2)** | Invoke static method on a Java type |
| **name.toUpperCase()** | Invoke instance method on a property value |
| **#value** | Read a variable in EvaluationContext |
| **@pricingService** | Reference a bean if the context has a BeanResolver |

A type reference does not create a Spring bean. It resolves a Java class by type name. If you need to invoke logic on a Spring service or component, use a bean reference in an appropriate context or call the service from Java according to the application design.

## Reading static fields and constants

Type references can also be used to access static fields:

~~~java
Double pi =
        parser.parseExpression("T(java.lang.Math).PI")
                .getValue(context, Double.class);
~~~

Here, **PI** is a static field of Math. The expression reads the constant value without instantiating a Math object.

The same syntax can be used with public static final constants in application-defined types:

~~~java
String defaultRegion =
        parser.parseExpression(
                "T(com.example.config.AppDefaults).REGION")
                .getValue(context, String.class);
~~~

The type name in the example must be the fully qualified name that the type locator can find. The field must be accessible according to the access mechanism supported by SpEL.

Type references are also commonly used to obtain enum constants:

~~~java
DayOfWeek day =
        parser.parseExpression("T(java.time.DayOfWeek).MONDAY")
                .getValue(context, DayOfWeek.class);
~~~

An enum constant is a static member of the enum type. This style is useful when an expression needs to compare against or select a specific enum value.

## Invoking static methods of application-defined types

Suppose the application has a utility class:

~~~java
package com.example.util;

public final class PriceRules {
    private PriceRules() {
    }

    public static BigDecimal addTax(
            BigDecimal amount,
            BigDecimal taxRate) {
        return amount.multiply(BigDecimal.ONE.add(taxRate));
    }
}
~~~

The static method can be called using the fully qualified type name:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("amount", new BigDecimal("100.00"));
context.setVariable("taxRate", new BigDecimal("0.08"));

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        "T(com.example.util.PriceRules).addTax(#amount, #taxRate)");

BigDecimal total =
        expression.getValue(context, BigDecimal.class);
~~~

In the expression:

- **T(com.example.util.PriceRules)** references the utility class.
- **addTax(...)** is the static method being called.
- **#amount** and **#taxRate** are variables set by the application in EvaluationContext.
- The result is retrieved as BigDecimal.

This approach allows an expression to combine a static method with dynamic data from the context. However, if the tax calculation logic is an important business rule, consider placing business decisions and control in a Java service. SpEL should keep the role of declaring short expressions at appropriate integration points.

## Fully qualified type names and the java.lang package

Typically, type references use fully qualified type names, such as **T(java.lang.Math)** or **T(java.time.LocalDate)**. The **java.lang** package is imported by default by StandardTypeLocator, so in the default configuration certain types in this package can be referenced by short name:

~~~java
Expression expression =
        parser.parseExpression("T(Math).max(10, 25)");
~~~

Even so, using the fully qualified name usually makes expressions easier to understand and avoids confusion when multiple types share the same name.

For types in other packages, you can use the fully qualified name or register package imports with StandardTypeLocator. Do not assume all packages on the classpath are automatically imported.

## Configuring TypeLocator

When SpEL evaluates **T(...)**, it uses a component called **TypeLocator** to resolve the type name into a Java Class. **StandardEvaluationContext** uses StandardTypeLocator by default.

If you want to add package imports, you can configure the locator:

~~~java
StandardTypeLocator typeLocator =
        new StandardTypeLocator();

typeLocator.registerImport("com.example.util");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeLocator(typeLocator);
~~~

After registering the import, the expression can use the short type name if that name resolves uniquely among the imported packages:

~~~java
Expression expression =
        parser.parseExpression("T(PriceRules).addTax(#amount, #taxRate)");
~~~

Registering a package helps shorten names in expressions. It does not automatically create beans, nor does it mean every class in the package is a business API that should be exposed to expression authors.

StandardTypeLocator can also be created with a specific ClassLoader:

~~~java
StandardTypeLocator typeLocator =
        new StandardTypeLocator(applicationClassLoader);
~~~

This is useful in applications with custom class loaders, plugins, or special deployment environments. A type can only be resolved if the class is within the scope of the class loader used by the locator and can be loaded at evaluation time.

## Type references and EvaluationContext

Type references are a SpEL capability that must be supported by the evaluation context. **StandardEvaluationContext** provides a type locator and the mechanisms needed to use the T(...) syntax.

By contrast, **SimpleEvaluationContext** is designed for a subset of SpEL capabilities, primarily for data binding. This context does not support type references, constructor invocation, or bean references like StandardEvaluationContext.

For example, do not expect the following expression to work in a read-only SimpleEvaluationContext:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

Expression expression =
        parser.parseExpression("T(java.lang.Math).max(1, 2)");
~~~

If the use case strictly requires calling static methods via T(...), a context that supports type references is needed. In that case, carefully consider the scope of classes the expression can access and which static methods can be invoked.

If the goal is only to read properties of a DTO, use SimpleEvaluationContext and avoid enabling unnecessary type references.

## Overloading and argument types

A Java class can have multiple static methods with the same name but different parameter types. SpEL must select the matching overload based on the types of the arguments and type conversion capabilities in the context.

Example:

~~~java
Expression expression =
        parser.parseExpression("T(java.lang.Math).max(10, 25)");

Integer result =
        expression.getValue(context, Integer.class);
~~~

In this case, the two arguments are integers, so the corresponding overload is selected. If arguments come from variables or properties with unclear types, supply data with explicit types to avoid unintended overload selection.

When a method accepts BigDecimal, LocalDate, or a custom type, place a variable of the right type into the context rather than passing a string and expecting SpEL to convert it automatically. If multiple overloads or null values make method selection ambiguous, it may be necessary to convert the data beforehand in Java or call a wrapper method with a simpler signature.

## Error handling when resolving types and invoking static methods

There are two error categories to distinguish:

- **Parse error:** invalid expression syntax, such as malformed T(...) structure, missing parentheses, or misplaced method call.
- **Evaluation error:** the expression parses successfully, but the type cannot be resolved, the static method does not exist, arguments are incompatible, or the method throws an error at runtime.

Error handling example:

~~~java
Expression expression;

try {
    expression = parser.parseExpression(
            "T(java.lang.Math).max(10, 25)");
} catch (ParseException ex) {
    throw new IllegalArgumentException("Invalid SpEL syntax", ex);
}

try {
    Integer result =
            expression.getValue(context, Integer.class);
} catch (EvaluationException ex) {
    throw new IllegalStateException(
            "Cannot resolve type or invoke static method", ex);
}
~~~

If the error comes from the class loader, check the type name, package, module, and class loader being used. If the error is caused by overloading or argument types, check the runtime types of variables and properties. If the static method throws an exception internally, handle the root cause in the method itself rather than just changing the parser.

## Risks when allowing type references in external expressions

Type references open up access to any Java types that TypeLocator can resolve. When combined with static methods, expressions can invoke functions with side effects such as creating resources, accessing the system, or performing other operations depending on the API called.

Therefore, do not evaluate arbitrary expressions from users with a StandardEvaluationContext that has a broad type locator and a root object containing many capabilities. An external expression can do much more than the calculations or comparisons the initial interface suggests.

If externally supplied expressions must be supported:

- Expose only the types and methods that are genuinely necessary.
- Use an allowlist-based TypeLocator if the application needs to permit specific classes.
- Restrict the root object, variables, property accessors, and method resolvers.
- Avoid exposing services, repositories, or objects with resource access permissions.
- Control expression sources, length, editing permissions, and error handling.
- Prefer small, pure wrapper methods with clear contracts instead of exposing a utility class with many capabilities.

Registering package imports in StandardTypeLocator makes resolving short names more convenient, but imports themselves are not a sandbox mechanism or a complete allowlist policy. If security control is needed, you must restrict type resolution and the components the context allows accessing.

## When should static methods be invoked via SpEL?

The T(...) syntax is appropriate when an expression needs a short utility calculation or a constant from a Java type, for example:

- Calling **Math.max(...)**, **Math.min(...)**, or a simple math function.
- Reading constants such as **Math.PI**.
- Referencing an enum constant.
- Calling a static helper with a simple signature and no side effects.
- Using an expression at a Spring integration point that already supports SpEL.

If a method performs multiple business steps, accesses resources, writes data, or requires permissions and transactions, call it from a Java service. If expressions are evaluated from external data, allow only explicitly selected types and methods.

## Conclusion

The **T(...)** type reference allows SpEL to reference a Java type to invoke static methods or read static fields. StandardEvaluationContext provides a TypeLocator to resolve type names; you can use fully qualified names or register package imports when needed. This capability differs from instance method calls, variable references, and Spring bean references.

T(...) is useful for simple calculations and constants, yet it also expands what an expression can perform. Use an appropriate context, control TypeLocator, and expose only necessary types, especially when expressions come from external sources.
