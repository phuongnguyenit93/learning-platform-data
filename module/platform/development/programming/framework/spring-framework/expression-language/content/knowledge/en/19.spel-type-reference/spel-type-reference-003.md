# Fully Qualified Package Type References in SpEL

## Objectives

Spring Expression Language (SpEL) allows referencing a Java type using the **T(...)** operator. Once the type is resolved, the expression can access static members such as constants, enum constants, or invoke static methods. For types outside the java.lang package, the fully qualified package notation helps SpEL identify the exact class without relying on short import prefixes.

This lesson focuses on the syntax of type references with fully qualified package names, the type resolution mechanism, and safe usage in EvaluationContext.

After this lesson, you can:

- Write type references using the T(fully.qualified.ClassName) syntax.
- Distinguish fully qualified package type names from imported type names.
- Access static fields, static methods, and enum constants.
- Use type references in type-checking expressions.
- Understand the role of TypeLocator and the class loader.
- Identify the limitations of SimpleEvaluationContext and the risks of evaluating untrusted expressions.

## 1. Type reference syntax

Type reference syntax:

~~~text
T(fully.qualified.ClassName)
~~~

Example:

~~~text
T(java.lang.String)
T(java.util.Locale)
T(java.time.LocalDate)
T(java.math.BigDecimal)
~~~

The part inside parentheses is the class name that SpEL needs to resolve. With a fully qualified package name, the name is written from the root package to the class, for example java.time.LocalDate.

The T(...) operator returns the Class object corresponding to the resolved type. From this Class object, the expression can access static members or use the type in checks supported by SpEL.

Fully qualified package names are especially useful when a type does not belong to java.lang. SpEL has a default import prefix for java.lang, so some common types like String can be written in short form:

~~~text
T(String)
~~~

Both of the following notations reference the same type:

~~~text
T(String)
T(java.lang.String)
~~~

When writing documentation, configurations, or long-lived stored expressions, fully qualified package names help readers recognize the exact class used and reduce dependence on TypeLocator's import prefixes.

## 2. Accessing static fields and constants

After referencing a type, you can use a dot to read a static field:

~~~text
T(java.lang.Math).PI
T(java.lang.Integer).MAX_VALUE
T(java.math.BigDecimal).ZERO
~~~

For example, the following expression returns the PI constant:

~~~text
T(java.lang.Math).PI
~~~

Some usage scenarios:

- Getting the integer limit from Integer.MAX_VALUE.
- Using BigDecimal.ZERO as an initial decimal number value.
- Reading constants defined by business classes.
- Using enum constants as configuration values.

Static fields are accessed by the class member name. The class name must be resolved first; if the package or class is wrong, SpEL cannot continue reading the field.

### Enum constants

Enum constants are also static members of an enum type:

~~~text
T(java.time.DayOfWeek).MONDAY
T(java.math.RoundingMode).HALF_UP
~~~

For example, you can pass an enum constant into a comparison expression:

~~~text
#roundingMode == T(java.math.RoundingMode).HALF_UP
~~~

This expression compares the variable roundingMode with the enum constant HALF_UP. The variable must be provided in EvaluationContext and have an appropriate type.

## 3. Calling static methods

You can call a static method by placing the method name after the type reference:

~~~text
T(java.lang.Math).max(10, 20)
T(java.util.UUID).fromString(#id)
T(java.time.LocalDate).parse('2026-11-12')
~~~

Example:

~~~text
T(java.lang.Math).max(10, 20)
~~~

The result is 20.

Another example using BigDecimal:

~~~text
T(java.math.BigDecimal).valueOf(125)
~~~

The expression calls the static method valueOf on BigDecimal and returns a BigDecimal.

For methods with multiple overloads, SpEL needs to resolve the method based on the name and argument types. Pass arguments with clear types and test cases that might cause ambiguity between overloads.

A type reference does not automatically turn an instance method into a static method. The T(...) syntax references a class; the call after the dot must match a static member provided by the class.

## 4. Using type references in type checks

A type reference can appear in the instanceof operator:

~~~text
#value instanceof T(java.lang.String)
~~~

The expression returns true if value is a String or a compatible instance according to Java's instanceof rules.

Example checking whether a variable is a BigDecimal:

~~~text
#amount instanceof T(java.math.BigDecimal)
~~~

This is useful when a variable or property can accept multiple data types and the expression needs to choose the appropriate processing branch.

It can be combined with logical operators:

~~~text
#amount != null and #amount instanceof T(java.math.BigDecimal)
~~~

Putting the null check first makes it clear that the expression only checks the type when a value is present.

Do not use instanceof to replace the application's type contract. If a property must always be BigDecimal, define the type in the model and validate at the data boundary instead of relying on a runtime expression everywhere.

## 5. Fully qualified package names and import prefixes

SpEL uses TypeLocator to resolve type names. StandardTypeLocator is the default implementation typically used with StandardEvaluationContext.

StandardTypeLocator has a default import prefix for java.lang. Therefore:

~~~text
T(String)
T(Integer)
T(Math)
~~~

can be resolved without writing java.lang.

For classes outside java.lang, you can write the fully qualified package name:

~~~text
T(java.time.LocalDate)
T(java.util.UUID)
T(java.math.BigDecimal)
~~~

Or register a package import prefix in StandardTypeLocator and then use the shorter class name. Example:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();

StandardTypeLocator typeLocator = new StandardTypeLocator();
typeLocator.registerImport("java.time");

context.setTypeLocator(typeLocator);
~~~

After registering java.time, expressions can use:

~~~text
T(LocalDate).parse('2026-11-12')
~~~

An import prefix only shortens the class name. It does not change the nature of a type reference and does not make a class a safe type permitted in every expression.

### When to use fully qualified package names?

Use fully qualified package names when:

- Expressions are stored in a database or configuration file and need to be self-describing.
- There are multiple classes with the same name in different packages.
- You do not want to depend on import prefixes registered by a specific context.
- You want reviewers to see the exact class being referenced.
- Expressions are shared across multiple applications with different TypeLocator configurations.

Use short names when the application has a clear and centrally controlled import prefix convention. If two classes share the same name in imported packages, fully qualified package names eliminate ambiguity.

## 6. Configuring TypeLocator

TypeLocator is responsible for finding the class by the name provided by the expression. StandardEvaluationContext allows replacing TypeLocator:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();

StandardTypeLocator locator = new StandardTypeLocator();
context.setTypeLocator(locator);
~~~

If additional package prefixes are needed:

~~~java
locator.registerImport("java.time");
locator.registerImport("java.math");
~~~

Then, short class names can be searched in the registered packages.

You can configure TypeLocator to use a class loader suitable for the application environment, such as when running in a container, plugin system, or environment with multiple class loaders. This is important because a class may exist in the application yet not be visible from the class loader that TypeLocator is currently using.

When a type reference works on a development machine but fails in production, check:

- Whether the class is actually on the runtime classpath.
- Whether the package and class name are accurate.
- Which class loader TypeLocator is using.
- Whether TypeLocator has the necessary import prefixes.
- Whether the application swaps EvaluationContext or TypeLocator between environments.

Do not fix errors by adding bulk package imports without identifying which classes are actually needed. Explicitly configure the packages that expressions are permitted to reference.

## 7. Combining type references with properties, variables, and other expressions

A type reference can appear inside a larger expression. For example, comparing an enum variable with an enum constant:

~~~text
#status == T(com.example.OrderStatus).APPROVED
~~~

Or using a static method to compute a value:

~~~text
T(java.lang.Math).max(#minimum, #requested)
~~~

The result can be used in a condition:

~~~text
#amount >= T(java.math.BigDecimal).ZERO
~~~

This example checks that amount is non-negative. The variable amount must be a type compatible with BigDecimal comparison; do not mix numeric types arbitrarily without defining conversions.

Type references can also be used in collection operations:

~~~text
#root.values.?[#this instanceof T(java.lang.String)]
~~~

The expression keeps the elements that are of type String. In selection, #this is the current element; the type reference simply specifies the class used in the type check.

Keep expressions readable by avoiding cramming too many static calls and type conditions onto one line. If logic requires multiple conversions or multiple branches, move the calculation into a clearly named Java method.

## 8. Limitations by EvaluationContext

Not every EvaluationContext supports type references.

StandardEvaluationContext provides a broader feature scope and supports type resolution through TypeLocator. Meanwhile, SimpleEvaluationContext is designed for a more restricted set of operations and does not support type references, constructors, or bean references.

Example context used for type references:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
ExpressionParser parser = new SpelExpressionParser();

Object result = parser.parseExpression(
    "T(java.lang.Math).max(10, 20)"
).getValue(context);
~~~

If an expression runs in SimpleEvaluationContext, do not assume T(...) will work just because property access or certain instance methods work. Choose a context that matches the capabilities the expression needs.

When the application builds EvaluationContext through a factory, use the same factory in testing and production. This helps avoid situations where an expression is validated in a broad context but runs in a more restricted context.

## 9. Safety when evaluating type references

Type references can open up access to static methods and static fields of classes that TypeLocator can resolve. If an expression comes from a user or untrusted source, this capability may exceed the permissions the application intends to grant.

For example, an expression could call a static method on a class outside the business scope. Simply requiring a fully qualified package class name does not make an expression safe; it only makes the class name explicit.

Control principles:

- Only evaluate expressions from trusted sources or those that have passed a review step.
- Use an EvaluationContext with the minimum necessary scope of capabilities.
- Configure TypeLocator in a controlled manner, allowing only the packages or classes the application needs.
- Avoid providing a broad StandardEvaluationContext to expressions entered arbitrarily by users.
- Do not let expressions call static methods with side effects if the business logic only needs computation.
- Restrict access to beans, methods, constructors, and types according to the application's design.
- Log the expression ID and version on errors for traceability.

TypeLocator is not a complete sandbox. Restricting class names needs to be paired with controlling method resolution, property access, bean resolution, and expression sources.

## 10. Common errors and diagnostics

| Symptom | Possible cause | Resolution |
|---|---|---|
| Class not found | Wrong package, wrong class name, or class not on runtime classpath | Check the fully qualified name and dependencies |
| Short name not resolved | Package not registered in TypeLocator | Use the fully qualified package name or register an import prefix |
| Ambiguous class name | Multiple classes with the same name in imported packages | Use the fully qualified package name |
| Cannot call static method | Method does not exist, does not match signature, or is not static | Check the class, method name, and argument types |
| Cannot read static field | Field does not exist or is not accessible | Check the member name and visibility |
| Type reference fails in context | Context does not support type references | Use StandardEvaluationContext when appropriate |
| Class exists but not found in production | Different class loader or runtime dependencies | Check TypeLocator and the class loader |
| Unsafe expression | Expression source can call out-of-scope classes | Restrict TypeLocator and EvaluationContext permissions |

When diagnosing, separate parse errors from type resolution errors. The T(...) string may be syntactically valid yet the class is still not found during evaluation. Once the class is resolved, the next error may lie in the static member or argument types.

## 11. Testing type references

Tests should confirm that the class is resolved, static members return the right result, and the actual context supports type references.

Example:

~~~java
@Test
void resolvesFullyQualifiedTypeReference() {
    ExpressionParser parser = new SpelExpressionParser();
    StandardEvaluationContext context = new StandardEvaluationContext();

    Expression expression =
        parser.parseExpression("T(java.lang.Math).max(10, 20)");

    assertEquals(20, expression.getValue(context, Integer.class));
}
~~~

Testing a type name outside java.lang:

~~~java
@Test
void resolvesTypeFromFullyQualifiedPackageName() {
    ExpressionParser parser = new SpelExpressionParser();
    StandardEvaluationContext context = new StandardEvaluationContext();

    Expression expression =
        parser.parseExpression("T(java.time.DayOfWeek).MONDAY");

    assertEquals(
        java.time.DayOfWeek.MONDAY,
        expression.getValue(context, java.time.DayOfWeek.class)
    );
}
~~~

If the application registers import prefixes, test both short names and fully qualified package names. If the application replaces the class loader or uses a custom TypeLocator, tests need to use that exact configuration.

Cases to test:

- Classes in java.lang.
- Classes outside java.lang using fully qualified package names.
- Classes using custom import prefixes.
- Enum constants and static fields.
- Overloaded static methods.
- Classes that do not exist or are not on the classpath.
- Contexts that do not support type references.
- TypeLocator restricted by policy.
- Runtime class loader differing from the test environment.

## 12. Best practices

- Use the T(...) syntax to reference classes explicitly.
- Use fully qualified names for classes outside java.lang when self-describing expressions are needed.
- Use fully qualified package names when class name collisions are possible.
- Only register necessary import prefixes in StandardTypeLocator.
- Check the class loader if type resolution differs between environments.
- Use static fields and methods for calculations or constants with clear meaning.
- Test overloads and argument types of static methods.
- Choose StandardEvaluationContext when expressions need type references.
- Do not assume SimpleEvaluationContext supports T(...).
- Restrict TypeLocator and other permissions when expressions come from external sources.
- Do not treat fully qualified names as a security measure.
- Move complex logic or logic with side effects into controlled Java methods.

## 13. Review checklist

Before accepting an expression with a type reference, check:

- [ ] T(...) syntax and class name are accurate.
- [ ] The class is on the runtime classpath.
- [ ] Fully qualified name is used when needed to avoid ambiguity.
- [ ] Import prefix is explicitly registered if using a short name.
- [ ] TypeLocator uses an appropriate class loader.
- [ ] The static field or method actually exists and has the expected type.
- [ ] Overloads are tested with actual argument types.
- [ ] EvaluationContext supports type references.
- [ ] SimpleEvaluationContext is not assumed to support T(...).
- [ ] Expression source and type resolution scope are controlled.
- [ ] Tests exist for valid classes, missing classes, and restricted contexts.

## Conclusion

The **T(...)** type reference lets SpEL resolve a Java class to access static fields, static methods, enum constants, or use in type checks. For classes outside java.lang, fully qualified package names identify the exact class to use without relying on import prefixes. TypeLocator and the class loader govern type name resolution; StandardEvaluationContext supports this feature, whereas SimpleEvaluationContext does not provide type references. Configure a controlled type resolution scope and test expressions in the application's actual context.
