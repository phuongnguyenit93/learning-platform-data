# Calling Static Methods via Type References in SpEL

## Objectives

Spring Expression Language (SpEL) can invoke a static method of a class without creating an instance. The approach is to use the `T(...)` type reference to specify the class, then use a dot to call a static method or read a static field.

Example:

```spel
T(java.lang.Math).max(10, 20)
T(java.lang.Integer).parseInt('42')
T(java.time.LocalDate).of(2026, 11, 12)
```

`T(...)` makes the class the target object of the subsequent access. SpEL looks up the static member on that class and performs the call using the evaluation context's method resolution mechanism.

## 1. Type reference syntax

General syntax:

```spel
T(fully.qualified.ClassName)
```

To call a static method, append the method name and arguments:

```spel
T(java.lang.Math).sqrt(81)
T(java.util.UUID).randomUUID()
T(java.lang.Integer).parseInt('123')
```

To read a static field, use the same type reference syntax:

```spel
T(java.lang.Math).PI
T(java.lang.Integer).MAX_VALUE
```

A type reference uses the uppercase `T` syntax with parentheses surrounding the class name. The class name can be a fully qualified name including the package. For classes in `java.lang`, `StandardTypeLocator` registers this package by default, so you can write the short form:

```spel
T(Math).max(10, 20)
T(Integer).parseInt('42')
```

For classes outside `java.lang`, use the fully qualified name or register a package import in the type locator.

## 2. Complete Java example

To evaluate a static method call via SpEL, create a parser, an evaluation context, and retrieve the result in the required type:

```java
ExpressionParser parser = new SpelExpressionParser();
EvaluationContext context = new StandardEvaluationContext();

Integer max = parser.parseExpression("T(java.lang.Math).max(10, 20)")
        .getValue(context, Integer.class);

Integer parsed = parser.parseExpression("T(java.lang.Integer).parseInt('42')")
        .getValue(context, Integer.class);

LocalDate date = parser.parseExpression(
        "T(java.time.LocalDate).of(2026, 11, 12)")
        .getValue(context, LocalDate.class);
```

In the example above:

- `Math.max` calls the static method and returns the larger number.
- `Integer.parseInt` converts the string to an integer.
- `LocalDate.of` creates a date value from year, month, and day.

There is no need to create `new Math()`, `new Integer()`, or `new LocalDate()` to call these static methods. The type reference points to the class containing the member to be invoked.

## 3. Static methods with dynamic arguments

Arguments to a static method can be literals, properties of the root object, or variables in `EvaluationContext`. This allows reusing the same expression with changing data:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(
        "T(java.lang.Math).max(#minimum, #candidate)");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("minimum", 10);
context.setVariable("candidate", 27);

Integer result = expression.getValue(context, Integer.class);
```

The result is `27`. If `candidate` changes in the context of the next evaluation, the same expression will call the method with the new value.

Properties from the root object can also be used:

```spel
T(java.lang.Math).max(minimumAllowed, requestedValue)
```

Here the properties are resolved from the root object; `T(java.lang.Math)` still identifies the class containing the static method.

## 4. Registering package imports for the type locator

SpEL uses `TypeLocator` to find the class named in `T(...)`. `StandardTypeLocator` supports fully qualified names and the `java.lang` package by default. If you want to write short class names for another package, register a package import:

```java
StandardEvaluationContext context = new StandardEvaluationContext();
StandardTypeLocator typeLocator = new StandardTypeLocator();
typeLocator.registerImport("java.time");
context.setTypeLocator(typeLocator);

ExpressionParser parser = new SpelExpressionParser();
LocalDate today = parser.parseExpression("T(LocalDate).now()")
        .getValue(context, LocalDate.class);
```

After registering `java.time`, the expression can use `T(LocalDate)` instead of `T(java.time.LocalDate)`. If no import is registered, use the fully qualified class name to avoid type-not-found errors.

Registering an import only affects how `TypeLocator` finds classes. It does not import static methods in the Java syntax sense and does not allow methods to be called without `T(...)`.

## 5. Calling overloaded static methods

Static methods can also be overloaded just like instance methods. SpEL selects the signature based on the method name, the number and runtime types of arguments, and the conversion capabilities provided by `TypeConverter`.

Example:

```spel
T(java.lang.Math).max(10, 20)
T(java.lang.Math).max(10.5, 20.5)
```

The first call provides integers; the second call provides decimal numbers. SpEL resolves the overload compatible with the argument types. When a class has multiple overloads and arguments can be converted to multiple types, produce arguments with explicit types instead of relying on implicit conversion.

Example using an explicit `Long`:

```spel
T(java.lang.Long).valueOf('9000000000')
```

The result of `valueOf` is a `Long`, which can be passed onward to a method requiring `Long` or `Number`.

The target type passed to `getValue(context, TargetType.class)` is only used to convert the result after the expression is evaluated; it does not force SpEL to choose a specific static overload.

## 6. Static fields and enum constants

Type references are not only for methods. You can read a public static field or enum constant through the class:

```spel
T(java.lang.Math).PI
T(java.lang.Integer).MAX_VALUE
T(com.example.OrderStatus).PAID
```

The last example accesses the enum constant `PAID` of the `OrderStatus` enum. The package and class names must match the actual application, and the type locator must be able to find that class.

Static fields are often useful for constants provided by a library or application. If a value needs to be configured per environment or request, pass it through a property/variable instead of hardcoding it in the expression.

## 7. Static methods and constructors are two different operations

A type reference calls a static method on a class. If you want to create an instance via a constructor, use SpEL's `new` constructor syntax:

```spel
T(java.time.LocalDate).now()
new java.math.BigDecimal('19.95')
```

The first expression calls the static method `now()` of `LocalDate`. The second expression calls the constructor of `BigDecimal`. Do not use `T(...)` as a way to create instances; `T(...)` only references the class.

If a class provides static factory methods such as `valueOf`, `of`, or `from`, you can call that factory via a type reference:

```spel
T(java.math.BigDecimal).valueOf(100L)
T(java.time.LocalDate).of(2026, 11, 12)
```

Factory methods often express how to create a value more clearly according to the class's API.

## 8. Scope of EvaluationContext support

`StandardEvaluationContext` supports type references through `TypeLocator`, as well as reflective method resolution. It is the common choice when an expression needs to invoke static methods on a class.

`SimpleEvaluationContext` is designed for data binding with a restricted feature set; it does not support type references. If an expression needs `T(...)`, use a context that supports this feature and restrict access according to application policy.

In a custom context, the type locator can be replaced with a custom implementation to control which classes are allowed to be referenced. The method resolver and type converter can also be configured to control how methods are found and arguments are converted.

## 9. Safety when evaluating type references

Type references can open a path to static methods and static fields of classes that are allowed to be found. Therefore, do not evaluate expressions supplied by users or untrusted sources with a `StandardEvaluationContext` that has full reflection permissions without restrictions.

Practical principles:

- Only allow the type locator to find classes necessary for business logic.
- Avoid exposing classes with static methods that can perform sensitive operations or cause side effects.
- Restrict method resolvers and objects placed in the root/context to actual needs.
- For user-controlled expressions, consider a restricted context and an allowlisted helper API instead of allowing arbitrary type references.
- Do not treat restricting package imports as a complete sandbox; other objects in the context may still expose their own methods.
- Do not concatenate external input directly into class names or expression source. Pass data via strongly typed variables.

For example, if you only need to compute the larger of two numbers, you can expose a helper with a narrow API or check the values in Java instead of letting users choose arbitrary classes and methods.

## 10. Common errors and how to handle them

| Symptom | Cause to check | Resolution |
| --- | --- | --- |
| `T(...)` fails to parse | Syntax error, missing parentheses, or lowercase `t` instead of `T`. | Use `T(package.ClassName)` with an uppercase T. |
| Class not found | Wrong package/class name, package not imported, or classloader cannot see the class. | Use the fully qualified name; check `TypeLocator` and the classloader. |
| `T(LocalDate)` does not work | `java.time` has not been registered in the type locator. | Use `T(java.time.LocalDate)` or register the `java.time` import. |
| Static method not found | Wrong name, wrong argument count, method is not public, or incompatible signature. | Check the class API, argument types, and method resolver. |
| Unexpected overload selected | Ambiguous argument types or arguments convertible to multiple signatures. | Pass arguments with specific types or use a helper with a dedicated signature. |
| `T(...)` works in one context but fails in another | Contexts differ in TypeLocator or context type is restricted. | Check `EvaluationContext`; `SimpleEvaluationContext` does not support type references. |
| Expression runs but causes unintended side effects | Invoked static method mutates state or accesses resources. | Only expose and call pure/permitted methods; restrict the type locator and resolver. |

## Key takeaways

- `T(fully.qualified.ClassName)` references a class in SpEL.
- Call a static method with `T(Class).method(arguments)`; read a static field with `T(Class).FIELD`.
- `StandardTypeLocator` supports `java.lang` by default; other packages can use fully qualified names or registered imports.
- Static methods can be overloaded; argument types, argument count, and TypeConverter affect signature selection.
- The target type of `getValue` converts the result; it does not select an overload.
- `T(...)` references a class; `new ...` invokes a constructor.
- `StandardEvaluationContext` supports type references; `SimpleEvaluationContext` does not.
- Restrict TypeLocator, MethodResolver, and exposed objects when expressions are not completely trusted.
- Pass runtime data through typed variables instead of concatenating data into the expression source.

## References

- [Spring Framework Reference — Types (Type References)](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/types.html)
- [Spring Framework Reference — Methods](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/methods.html)
- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework API — StandardTypeLocator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardTypeLocator.html)
- [Spring Framework API — StandardEvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)