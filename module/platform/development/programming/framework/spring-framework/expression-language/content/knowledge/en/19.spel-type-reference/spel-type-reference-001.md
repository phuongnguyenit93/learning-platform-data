# The T(Type) Operator in SpEL

## 1. What is a type reference?

Spring Expression Language (SpEL) has a special `T(...)` operator to reference a Java type. The result of this expression is a `java.lang.Class` object representing the specified type.

General syntax:

```text
T(fully.qualified.TypeName)
```

Example:

```java
ExpressionParser parser = new SpelExpressionParser();

Class<?> dateType = parser.parseExpression(
        "T(java.util.Date)")
        .getValue(Class.class);

Class<?> stringType = parser.parseExpression(
        "T(String)")
        .getValue(Class.class);
```

`T(java.util.Date)` returns the Class object of `java.util.Date`; `T(String)` returns the Class of `java.lang.String`. This operator only references a type. It does not create a new instance of the class. To invoke a constructor, use the `new` operator.

A type reference is useful when an expression needs to:

- Access a static field or constant of a class.
- Invoke a static method.
- Reference an enum constant.
- Compare or check a type using `instanceof`.
- Return a Class object for an API or property of type `Class`.

## 2. Syntax and type naming rules

The type name in `T(...)` is resolved by TypeLocator when the expression is evaluated. With SpEL's default configuration:

- Types in the `java.lang` package can be written using their short name, for example `T(String)`, `T(Math)`, `T(Integer)`.
- Types in other packages must use their fully qualified name, for example `T(java.util.Date)`, `T(java.math.BigDecimal)`.
- Type names are not enclosed in quotes. `T('java.util.Date')` is invalid syntax because the part inside parentheses must be a type name, not a String literal.

Example:

```text
T(String)
T(java.util.UUID)
T(java.math.BigDecimal)
T(java.time.LocalDate)
```

If a non-fully-qualified name is used for a class outside `java.lang`, SpEL may fail to find the type and raise a `TYPE_NOT_FOUND` error. When import prefixes are not configured, prefer fully qualified names to keep expressions clear and avoid conflicts between classes with the same simple name.

## 3. Obtaining a Class object from T(...)

Because the result of a type reference is a `Class`, it can be assigned directly to a Java variable or passed to an API that accepts a Class:

```java
ExpressionParser parser = new SpelExpressionParser();

Class<?> dateClass = parser.parseExpression(
        "T(java.util.Date)")
        .getValue(Class.class);

Class<?> stringClass = parser.parseExpression(
        "T(String)")
        .getValue(Class.class);

System.out.println(dateClass.getName());
// java.util.Date

System.out.println(stringClass.getName());
// java.lang.String
```

If only the class name is needed, you can use the `name` property on the Class result:

```text
T(java.util.UUID).name
```

However, when accessing type metadata in Java, receiving a `Class<?>` result is usually clearer:

```java
Class<?> type = parser.parseExpression(
        "T(java.util.UUID)")
        .getValue(Class.class);

boolean isFinal = java.lang.reflect.Modifier.isFinal(
        type.getModifiers());
```

Do not confuse `T(java.util.UUID)` with `new java.util.UUID(...)`: one expression returns a Class object, while the other requests instance creation via a constructor.

## 4. Accessing static fields and constants

An important value of `T(...)` is the ability to access static members of the referenced type. After the type reference, use a dot to read a static field:

```java
Double pi = parser.parseExpression(
        "T(java.lang.Math).PI")
        .getValue(Double.class);

// pi is approximately 3.141592653589793
```

Some other examples:

```text
T(java.lang.Integer).MAX_VALUE
T(java.lang.Integer).MIN_VALUE
T(java.lang.Boolean).TRUE
T(java.math.BigDecimal).ZERO
T(java.math.BigDecimal).ONE
```

An enum constant can be referenced like a static field:

```java
Object roundingMode = parser.parseExpression(
        "T(java.math.RoundingMode).HALF_UP")
        .getValue();
```

Example comparing two enum constants in the Spring Reference:

```java
boolean result = parser.parseExpression(
        "T(java.math.RoundingMode).CEILING < " +
        "T(java.math.RoundingMode).FLOOR")
        .getValue(Boolean.class);

// true
```

Java enums implement `Comparable`, so constants of the same enum type can be compared according to their declaration order. In business rules, it is usually better to use equality or compare enums according to domain meaning so expressions remain easy to understand.

## 5. Calling static methods

After a type reference, you can call a static method using normal method invocation syntax:

```java
Integer maximum = parser.parseExpression(
        "T(java.lang.Math).max(12, 30)")
        .getValue(Integer.class);

// 30
```

Example calculating a square root:

```text
T(Math).sqrt(81)
```

Example rounding a number:

```text
T(java.lang.Math).round(12.6)
```

Example converting to a String:

```text
T(String).valueOf(12345)
```

Static methods can accept literals, variables, properties, or the result of another expression:

```java
context.setVariable("amount", new BigDecimal("125.50"));

BigDecimal absolute = parser.parseExpression(
        "T(java.math.BigDecimal).valueOf(#amount.doubleValue()).abs()")
        .getValue(context, BigDecimal.class);
```

In the expression above, SpEL finds the BigDecimal class, calls the static method `valueOf`, and then calls the instance method `abs()` on the returned result. For real currency calculations, avoid converting through double as it can lose precision; this example only illustrates combining static and instance methods.

## 6. Using T(...) with enums and business rules

Enums are a very common use case for type references. You can access an enum constant without registering each value as a variable:

```java
String state = parser.parseExpression(
        "T(com.example.OrderStatus).PAID.name()")
        .getValue(context, String.class);
```

In the example, `com.example.OrderStatus` is the fully qualified name of the enum in the application. `PAID` is the enum constant; `name()` is an instance method on that constant.

You can compare an enum property on the root object:

```text
status == T(com.example.OrderStatus).PAID
```

Or choose a display label based on status:

```text
status == T(com.example.OrderStatus).PAID ? 'Completed' : 'Pending'
```

This approach avoids comparing enums against arbitrary strings. It helps the expression reflect the exact data type of the property.

## 7. Combining type references with instanceof

The `instanceof` operator in SpEL checks whether a value belongs to the specified type. You can use `T(...)` as the type operand:

```java
boolean isString = parser.parseExpression(
        "#value instanceof T(String)")
        .getValue(context, Boolean.class);
```

Example checking if a variable is a BigDecimal:

```text
#amount instanceof T(java.math.BigDecimal)
```

Example choosing handling based on type:

```text
#value instanceof T(String) ? #value.toUpperCase() : #value
```

Use `instanceof` when an expression genuinely needs to distinguish types at runtime. If a unified API or model can be designed, relying too heavily on type checks in expressions can make rules difficult to maintain.

## 8. TypeLocator: how SpEL finds classes

SpEL uses the `TypeLocator` interface to find classes when evaluating `T(...)` expressions. In `StandardEvaluationContext`, the default implementation is `StandardTypeLocator`.

`StandardTypeLocator`:

- Uses a default ClassLoader (usually the thread context ClassLoader) if no specific ClassLoader is passed.
- Can accept a specific ClassLoader via its constructor.
- Supports import prefixes to find types by non-fully-qualified names.
- Can add or remove import prefixes using `registerImport()` and `removeImport()`.

For example, if the application has the enum `com.example.domain.OrderStatus`, you can configure a prefix to use the short name `T(OrderStatus)`:

```java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

StandardTypeLocator typeLocator =
        new StandardTypeLocator(
                Order.class.getClassLoader());

typeLocator.registerImport("com.example.domain");
context.setTypeLocator(typeLocator);

OrderStatus status = parser.parseExpression(
        "T(OrderStatus).PAID")
        .getValue(context, OrderStatus.class);
```

Once the `com.example.domain` prefix is registered, TypeLocator can try to find `OrderStatus` in that package. If multiple packages have classes with the same name, the fully qualified name remains safer and clearer.

You can view the list of currently registered prefixes:

```java
List<String> prefixes = typeLocator.getImportPrefixes();
```

And remove a prefix that is no longer needed:

```java
typeLocator.removeImport("com.example.domain");
```

TypeLocator import prefixes only serve to resolve type references in SpEL. They are not Java import statements and do not automatically apply to Java source code.

## 9. ClassLoader in Spring applications

In simple environments, the default ClassLoader can find application classes. However, in applications with plugins, modules, application servers, custom class loaders, or multiple class loaders, SpEL may fail to find a type even though the class actually exists at runtime.

When the application manages EvaluationContext itself, configure StandardTypeLocator with a ClassLoader that can see the required types:

```java
ClassLoader applicationClassLoader =
        Order.class.getClassLoader();

StandardTypeLocator locator =
        new StandardTypeLocator(applicationClassLoader);

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setTypeLocator(locator);
```

Spring also applies a similar configuration in `StandardBeanExpressionResolver` of the spring-context module: TypeLocator is created with the corresponding BeanFactory's ClassLoader.

When encountering a type-not-found error, check in order:

1. Are the class name, package, and spelling correct?
2. Is the class on the runtime classpath/module path?
3. Can the ClassLoader in use see that class?
4. If using a short name, has the import prefix been registered?
5. Are there classes with the same name in multiple packages causing ambiguity?

Do not resolve errors by arbitrarily adding import prefixes before confirming the actual ClassLoader and package.

## 10. StandardEvaluationContext and SimpleEvaluationContext

Not every EvaluationContext allows type references.

| Context | Supports `T(...)` | Purpose |
|---|---|---|
| `StandardEvaluationContext` | Yes, via TypeLocator. | Full-featured SpEL evaluation and strategy configuration. |
| `SimpleEvaluationContext` | Does not support type references. | Data binding and expressions requiring restricted capabilities. |

If an expression uses `T(java.lang.Math)` but is evaluated with `SimpleEvaluationContext`, SpEL cannot resolve the type reference and will throw an error.

Full context example:

```java
StandardEvaluationContext context =
        new StandardEvaluationContext();

Double pi = parser.parseExpression(
        "T(Math).PI")
        .getValue(context, Double.class);
```

In cases where you only need to read/write properties or filter data with a limited feature set, consider SimpleEvaluationContext. If an expression truly needs type references, it requires a context that allows that feature and must control the expression source as well as the types allowed to be accessed.

## 11. Security when using type references

Type references open up access to static fields and static methods of resolved classes. That means an expression can invoke static APIs that the application did not intend to expose to expression authors.

Therefore:

- Do not evaluate expressions supplied by users or untrusted external sources using StandardEvaluationContext with broad type access.
- Restrict the classes that an expression can resolve, rather than allowing every class on the classpath.
- If a custom TypeLocator is needed, consider allow-listing specific types instead of registering broad packages.
- Do not treat merely using fully qualified class names as a security measure; a fully qualified name only identifies the class.
- Do not assume SimpleEvaluationContext supports T(...); it intentionally excludes type references.
- Review both static methods and static fields exposed through allowed classes.

A custom TypeLocator can limit which classes SpEL finds, but restricting type references alone does not replace controlling expressions, method invocations, property access, and other objects provided by the context.

## 12. How T(...) differs from new and bean references

The following three syntaxes have different meanings:

| Syntax | Purpose | Example |
|---|---|---|
| `T(Type)` | Obtain a Class object and access static members. | `T(Math).PI` |
| `new Type(...)` | Call a constructor to create an instance. | `new java.util.Date()` |
| `@beanName` | Reference a Spring bean via BeanResolver. | `@pricingService.currentRate` |

Example:

```text
T(java.util.Date)
```

returns the Class of Date.

```text
new java.util.Date()
```

creates a Date instance.

```text
@clockService
```

references the bean named `clockService` if the EvaluationContext has a suitable BeanResolver.

Do not use T(...) to replace bean lookup. If a Spring service is needed, use the bean reference mechanism configured in the context or pass the service via the root object/variable according to the application design.

## 13. Common errors and how to handle them

| Symptom | Common cause | Resolution |
|---|---|---|
| Type not found | Wrong class name, missing package, or class not on runtime classpath. | Use the fully qualified name and check the classpath/module path. |
| `T(String)` works but `T(Date)` fails | Date belongs to java.util, not java.lang. | Use `T(java.util.Date)`. |
| Type reference fails in SimpleEvaluationContext | This context does not support type references. | Use a context that allows type references if genuinely needed, or move the logic to Java. |
| Class exists in application but SpEL cannot find it | TypeLocator uses a ClassLoader that cannot see the class. | Configure StandardTypeLocator with the application's ClassLoader. |
| Short name is not resolved | Import prefix for that package has not been registered. | Use the fully qualified name or call `registerImport()`. |
| Calling static method fails | Method is not static, wrong name/signature, or type not found. | Confirm the method is static and check the class/type locator. |
| Reading enum constant fails | Type reference points to wrong enum or constant name is wrong. | Check package, enum type, and constant name. |
| Using `T(...)` but expecting an instance | Confusing type reference with constructor. | Use `new ...(...)` to create an object. |
| Expression runs in one environment but fails in another | Different ClassLoader or import prefixes. | Configure TypeLocator consistently with the application's ClassLoader. |
| Expression can invoke unexpected static APIs | Allowing overly broad type references for untrusted expressions. | Restrict TypeLocator and do not evaluate untrusted expressions. |

## 14. Process for verifying a type reference

1. Identify the class to reference and its full package.
2. Check whether the class belongs to `java.lang` or another package.
3. Use `T(FullyQualifiedName)` first to confirm the type name.
4. Retrieve the result as `Class<?>` and check `getName()` if needed.
5. If accessing a static member, check the member name, whether it is static, and the method signature.
6. If using a short name, check the import prefixes in StandardTypeLocator.
7. If the class is not found, check the ClassLoader and runtime classpath.
8. Confirm that the EvaluationContext supports type references; SimpleEvaluationContext does not.
9. Control the types and static APIs that the expression is allowed to access.
10. Test with the same context and ClassLoader as the application environment.

## 15. Key takeaways

- `T(Type)` returns a `java.lang.Class` object; it does not create an instance.
- Names in `java.lang` can be written in short form; other packages should use fully qualified names.
- Use `T(Type).FIELD` to read a static field/enum constant and `T(Type).method(...)` to call a static method.
- Type references can be used with `instanceof` to check runtime types.
- StandardEvaluationContext uses TypeLocator; StandardTypeLocator supports ClassLoader and import prefixes.
- SimpleEvaluationContext does not support type references.
- Use `new` to create objects and `@beanName` to reference beans; these two operations differ from T(...).
- T(...) broadens access to static APIs; do not evaluate untrusted expressions and restrict resolvable types.

## References

- [Spring Framework Reference — Types and the T Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/types.html)
- [StandardTypeLocator Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardTypeLocator.html)
- [StandardEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)
- [SimpleEvaluationContext Source — Type References Excluded](https://github.com/spring-projects/spring-framework/blob/main/spring-expression/src/main/java/org/springframework/expression/spel/support/SimpleEvaluationContext.java)
- [Spring Framework Reference — EvaluationContext and Security](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
