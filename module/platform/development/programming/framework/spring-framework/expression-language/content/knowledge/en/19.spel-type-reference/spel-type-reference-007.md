# TypeLocator and Package Imports

In Spring Expression Language (SpEL), **TypeLocator** is the component responsible for resolving a type name written in a **T(...)** type reference into a usable Java class during expression evaluation. It enables an expression to reference a static method, static field, or enum constant of a type without passing an instance of that type as the root object.

**StandardTypeLocator** is the default implementation typically used with StandardEvaluationContext. It supports looking up types by fully qualified name and by short name within imported packages. A package import here is a TypeLocator configuration for SpEL; it is not an import statement in Java source code.

## Type references and the role of TypeLocator

Type reference syntax:

~~~text
T(fully.qualified.TypeName)
~~~

For example, calling a static method of Math:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

Expression expression =
        parser.parseExpression("T(java.lang.Math).max(10, 25)");

Integer maximum =
        expression.getValue(context, Integer.class);
~~~

When evaluating **T(java.lang.Math)**, SpEL asks TypeLocator to find the type named java.lang.Math. Once it has the corresponding Class, the expression can call the static method max.

If the type name cannot be resolved, an error occurs during the evaluation phase. The expression string can still parse successfully because looking up the Java class is performed when SpEL evaluates the type reference.

## StandardTypeLocator

**StandardTypeLocator** is the TypeLocator provided by Spring. It looks up classes using a class loader and supports a list of package imports so short type names can be used.

StandardEvaluationContext has a StandardTypeLocator by default. Therefore, for ordinary expressions, there is no need to create a TypeLocator manually:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("T(java.lang.Math).PI");

Double pi =
        expression.getValue(context, Double.class);
~~~

The fully qualified name **java.lang.Math** precisely identifies the class to find. StandardTypeLocator also imports the **java.lang** package by default, so some types in this package can be referenced by their short name:

~~~java
Expression expression =
        parser.parseExpression("T(Math).max(10, 25)");

Integer maximum =
        expression.getValue(context, Integer.class);
~~~

In the example, **T(Math)** is resolved to java.lang.Math because the java.lang package is imported by default.

Although short names are convenient, fully qualified names are usually easier to read and less prone to confusion when expressions are shared across modules or stored in configuration.

## Registering package imports

If a type resides outside already imported packages, you can register its package with StandardTypeLocator using **registerImport(...)**.

For example, using LocalDate from the java.time package:

~~~java
StandardTypeLocator typeLocator =
        new StandardTypeLocator();

typeLocator.registerImport("java.time");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeLocator(typeLocator);

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("T(LocalDate).of(2026, 12, 31)");

LocalDate deadline =
        expression.getValue(context, LocalDate.class);
~~~

After registering **java.time**, SpEL can resolve the short name **LocalDate** to java.time.LocalDate. The expression calls the static method **of(...)** to create a date value.

If you do not register the package, you can write the fully qualified name:

~~~java
Expression expression =
        parser.parseExpression(
                "T(java.time.LocalDate).of(2026, 12, 31)");
~~~

Both approaches reference the same type. Using the fully qualified name does not require adding a package import, provided the class loader can find that class.

## Package imports apply only to type resolution in SpEL

It is important to distinguish TypeLocator package imports from imports in Java:

- **Java imports** are used by the compiler to shorten type names in source files.
- **TypeLocator package imports** are used by SpEL at runtime to resolve type names in T(...) expressions.
- TypeLocator import configuration does not change the classpath, load additional dependencies, or automatically register Spring beans.

For example, the Java line **import java.time.LocalDate;** in a source file does not automatically enable every SpEL expression to use **T(LocalDate)**. To use the short name in SpEL, the corresponding package must be in the import list of the TypeLocator used by the EvaluationContext.

Conversely, calling **registerImport("java.time")** does not create a Java import in source code. It only affects how SpEL resolves type names in expressions evaluated with that context.

## Configuring TypeLocator on EvaluationContext

You can create a separate StandardTypeLocator and attach it to StandardEvaluationContext:

~~~java
StandardTypeLocator typeLocator =
        new StandardTypeLocator();

typeLocator.registerImport("java.time");
typeLocator.registerImport("java.util");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeLocator(typeLocator);
~~~

From this point on, expressions evaluated with the context can use short names for types in java.time and java.util:

~~~java
Expression dateExpression =
        parser.parseExpression("T(LocalDate).now()");

Expression localeExpression =
        parser.parseExpression("T(Locale).US");

LocalDate today =
        dateExpression.getValue(context, LocalDate.class);

Locale locale =
        localeExpression.getValue(context, Locale.class);
~~~

In the example:

- **T(LocalDate)** is resolved in java.time.
- **T(Locale)** is resolved in java.util.
- **now()** and **US** are respectively a static method and a static field/enum constant accessed via the type.

One context can use one TypeLocator with multiple package imports. Only register packages that are genuinely needed so expressions remain understandable and short names are less likely to become ambiguous.

## Using fully qualified names and avoiding type name collisions

Two different packages can contain classes with the same simple name. If both packages are imported, a type reference using a short name can become ambiguous or resolve differently than the author intended.

For example, many libraries may provide a **Date**, **Path**, or **Config** type. When a name collision is possible, use the fully qualified name:

~~~java
Expression expression =
        parser.parseExpression(
                "T(java.time.LocalDate).of(2026, 11, 12)");
~~~

The fully qualified name states the exact type the expression requires. This is a good choice in critical configurations, in long-lived stored expressions, or when multiple modules contribute package imports.

Do not add packages indiscriminately just to shorten expressions. The broader the import list, the higher the chance of name conflicts and confusion.

## Choosing a ClassLoader for StandardTypeLocator

Type resolution ultimately depends on a **ClassLoader** capable of loading the class. StandardTypeLocator has a constructor that allows passing a specific ClassLoader:

~~~java
ClassLoader applicationClassLoader =
        Thread.currentThread().getContextClassLoader();

StandardTypeLocator typeLocator =
        new StandardTypeLocator(applicationClassLoader);

typeLocator.registerImport("java.time");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeLocator(typeLocator);
~~~

This configuration is useful in applications with multiple class loaders, plugins, containers, or deployment environments where the default class loader cannot see all required classes.

If TypeLocator fails to find a type, check:

- Whether the type name in T(...) is accurate.
- Whether the package import is registered properly if using a short name.
- Whether the class is actually on the runtime classpath.
- Whether the passed ClassLoader has permission to load that class.
- Whether the class is isolated in a separate module or class loader.

Package imports only help locate a class by short name; they cannot make a dependency missing from the runtime classpath available.

## Using a custom TypeLocator

In cases where strict control over which types may be referenced is required, the application can supply its own implementation of **TypeLocator** and attach it to EvaluationContext.

The TypeLocator interface defines the operation to resolve a type name into a Class:

~~~java
Class<?> findType(String typeName) throws EvaluationException;
~~~

A custom TypeLocator can allow only a specific set of types and reject other names. For example, an application might expose only a few safe utility classes to configuration expressions.

Illustrative code:

~~~java
public class AllowListTypeLocator implements TypeLocator {
    private final Map<String, Class<?>> allowedTypes;

    public AllowListTypeLocator(Map<String, Class<?>> allowedTypes) {
        this.allowedTypes = Map.copyOf(allowedTypes);
    }

    @Override
    public Class<?> findType(String typeName) {
        Class<?> type = allowedTypes.get(typeName);

        if (type == null) {
            throw new SpelEvaluationException(
                    SpelMessage.TYPE_NOT_FOUND, typeName);
        }

        return type;
    }
}
~~~

In a real application, complete the imports, exception types, and naming conventions according to the Spring version in use. The example illustrates the idea: only names registered in the allowlist are resolved.

You can attach this locator to the context:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeLocator(allowListTypeLocator);
~~~

When using a custom TypeLocator, control both fully qualified names and short names in accordance with application policy. Checking one name form while overlooking an equivalent form can defeat the allowlist's purpose.

## Package imports are not a security mechanism

Registering a package import does not mean restricting expressions to only classes in that package. TypeLocator can still resolve the fully qualified name of a class if the class loader finds it, depending on the implementation and policy in use.

Therefore, do not treat **registerImport(...)** as an allowlist or sandbox. It is primarily a convenience utility for shortening type names.

If expressions come from users or an untrusted source, carefully consider whether to allow **T(...)**. Type references can lead to static methods or static fields of resolved classes. Some static methods can allocate resources, read system state, or cause other side effects.

Appropriate control measures include:

- Only use StandardEvaluationContext with application-controlled expressions.
- If evaluating external expressions is necessary, consider an allowlist-based TypeLocator.
- Only expose types and methods that are truly needed.
- Restrict the root object, property accessors, method resolvers, and variables in the context.
- Avoid exposing APIs that can access the filesystem, network, processes, or sensitive resources.
- Validate the expression source and handle parse/evaluation errors explicitly.

If the use case only requires reading properties of a DTO, SimpleEvaluationContext has a more limited feature surface and does not support type references. In that case, do not open up StandardEvaluationContext merely for the convenience of an unnecessary T(...) syntax.

## Handling type resolution errors

Errors can occur at two different stages:

- **ParseException:** the SpEL string has invalid syntax, such as malformed T(...) structure.
- **EvaluationException:** the expression parses, but TypeLocator cannot find the type, the method or field does not exist, or the operation cannot be performed in the current context.

Example:

~~~java
Expression expression;

try {
    expression = parser.parseExpression("T(LocalDate).now()");
} catch (ParseException ex) {
    throw new IllegalArgumentException("Invalid SpEL syntax", ex);
}

try {
    LocalDate today =
            expression.getValue(context, LocalDate.class);
} catch (EvaluationException ex) {
    throw new IllegalStateException(
            "Cannot resolve or evaluate the requested type", ex);
}
~~~

If the expression uses a short name, check package imports. If it uses a fully qualified name, check the classpath and ClassLoader. If the class was resolved but the static method cannot be called, check the method signature and argument types.

Do not catch all errors and return a default value without logging the cause. A misconfigured type reference can cause the application to use the wrong rules or data.

## When should package imports be registered?

Package imports are useful when a group of expressions frequently references types in the same package, such as:

- **java.time** for LocalDate, LocalDateTime, and date/time types.
- **java.util** for Locale, UUID, and utility types.
- Internal utility packages containing classes with pure static methods and clear contracts.

If there are only one or two type references, using fully qualified names is usually simpler than modifying the context. If expressions need to remain stable across multiple modules, fully qualified names also avoid depending on package import lists configured elsewhere.

## Conclusion

**TypeLocator** resolves type names in SpEL **T(...)** type references. **StandardTypeLocator** supports fully qualified names, package imports, and ClassLoader configuration; the **java.lang** package is imported by default. Use **registerImport(...)** to allow short names from other packages, or pass an appropriate ClassLoader when the application has a special class loading environment.

Package imports are only a convenience mechanism for name resolution, not Java imports and not a security allowlist. When expressions come from external sources, control type resolution with an appropriate TypeLocator and expose only the necessary types.
