# Array and Collection Construction in SpEL

## Objectives

Spring Expression Language (SpEL) can create Java arrays, instantiate classes via constructors, and create collections directly inside an expression. These three mechanisms have different results and characteristics: array construction creates an array with a defined component type; constructor invocation creates an instance of the specified class; inline list/map creates a collection literal provided by SpEL.

This topic is useful when an expression needs to create intermediate data, pass a list of parameters to a method, initialize configuration values, or build small objects from runtime data. The main syntaxes use `new` for arrays/constructors, while `{...}` and `{key:value}` are inline collection literals.

## 1. Creating Arrays with a Fixed Size

SpEL uses syntax similar to Java to create arrays:

```spel
new int[4]
new java.lang.String[3]
new boolean[2]
```

The expression creates a new array with the specified size. Elements are initialized according to Java's default rules:

| Element Type | Initial Value |
| --- | --- |
| `int`, `long`, `double`, and other numeric primitives | `0` or `0.0` respectively. |
| `boolean` | `false`. |
| `char` | Null character (`\u0000`). |
| Reference types such as `String` or objects | `null`. |

Example evaluation in Java:

```java
ExpressionParser parser = new SpelExpressionParser();
EvaluationContext context = new StandardEvaluationContext();

int[] numbers = parser.parseExpression("new int[4]")
        .getValue(context, int[].class);

String[] names = parser.parseExpression("new java.lang.String[3]")
        .getValue(context, String[].class);
```

`numbers` has four elements initially equal to `0`; `names` has three elements initially equal to `null`. An array has a fixed size after creation, just like a regular Java array.

## 2. Creating Arrays with an Initializer

If the required elements are already known, you can supply an initializer directly when creating the array:

```spel
new int[] {1, 2, 3}
new java.lang.String[] {'red', 'green', 'blue'}
new boolean[] {true, false, true}
```

The initializer is evaluated to populate values into the new array. The element type of the array is determined by the type preceding `[]`; initializer values must be compatible with or convertible to that type.

Example:

```java
ExpressionParser parser = new SpelExpressionParser();
EvaluationContext context = new StandardEvaluationContext();

int[] primes = parser.parseExpression("new int[] {2, 3, 5, 7, 11}")
        .getValue(context, int[].class);

String[] roles = parser.parseExpression(
        "new java.lang.String[] {'READER', 'EDITOR'}")
        .getValue(context, String[].class);
```

Array initializers are especially useful when an API requires `int[]`, `String[]`, or an array with a specific component type. An inline list `{2, 3, 5}` creates a `List`, whereas `new int[] {2, 3, 5}` creates an `int[]`; the two results cannot be treated as the same type.

## 3. Multidimensional Arrays

SpEL supports creating multidimensional arrays by declaring the size of each dimension:

```spel
new int[4][5]
new java.lang.String[2][3]
```

Java example:

```java
int[][] matrix = parser.parseExpression("new int[4][5]")
        .getValue(context, int[][].class);
```

The expression creates an outer array with four rows, each row being an `int` array with five elements. Primitive elements initially default to `0`.

SpEL currently does not allow providing an initializer when creating a multidimensional array. Therefore, forms like `new int[2][2] {{1, 2}, {3, 4}}` are not supported. If you need a matrix with initial data, create the array in Java or populate individual elements in application code.

## 4. Dynamically Computed Array Sizes

The size of each dimension is an expression evaluated when creating the array. You can use variables or properties in `EvaluationContext`:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("new int[#size]");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("size", 5);

int[] values = expression.getValue(context, int[].class);
```

During this evaluation, `#size` is `5`, so the array has five elements. You can reuse the expression with a different size using a new context or by updating the variable before the next evaluation.

The size value must be a valid integer and within the application's memory limits. Negative sizes, unconvertible values, or overly large arrays can cause evaluation to fail or create memory pressure. Validate the size before putting it into the context.

## 5. Invoking Constructors to Create Objects

The `new` operator is also used to call a class constructor. For classes outside `java.lang`, use the fully qualified class name including the package:

```spel
new java.math.BigDecimal('19.95')
new java.util.Date()
new com.example.Point(10, 20)
```

For types in `java.lang`, you can use short names such as `new String('hello')` or `new Integer('42')` if the class/constructor remains appropriate for the running JDK. In new code, avoid deprecated wrapper constructors and use factories such as `Integer.valueOf` when appropriate.

Java example:

```java
ExpressionParser parser = new SpelExpressionParser();
EvaluationContext context = new StandardEvaluationContext();

BigDecimal price = parser.parseExpression(
        "new java.math.BigDecimal('19.95')")
        .getValue(context, BigDecimal.class);
```

SpEL locates a matching constructor on the specified class, then converts arguments if the context's `TypeConverter` supports it. The invoked constructor must be accessible according to the configured reflection mechanism.

## 6. Passing Dynamic Arguments to Constructors

Constructor arguments can be literals, variables, properties, operations, or the result of another expression:

```spel
new java.math.BigDecimal(#amount)
new com.example.Range(#minimum, #maximum)
new com.example.UserProfile(#userId, #displayName)
```

Example:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(
        "new java.math.BigDecimal(#amount)");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("amount", "125000.50");

BigDecimal amount = expression.getValue(context, BigDecimal.class);
```

SpEL evaluates `#amount` and passes that value to the constructor. Input data remains data without needing to concatenate it into the expression source. Passing via variables prevents syntax errors when input contains quotes or special characters.

If the class has multiple overloaded constructors, SpEL picks a constructor based on argument count, argument types, and the context's conversion capabilities. When multiple signatures could match, pass explicitly typed arguments or design less ambiguous constructors/APIs.

## 7. Creating Collection Types Using Constructors

To obtain a specific Java collection, invoke the constructor of the desired implementation:

```spel
new java.util.ArrayList()
new java.util.LinkedList()
new java.util.HashSet()
new java.util.LinkedHashSet()
new java.util.HashMap()
new java.util.LinkedHashMap()
```

Example:

```java
List<?> list = parser.parseExpression("new java.util.ArrayList()")
        .getValue(context, List.class);

Set<?> set = parser.parseExpression("new java.util.LinkedHashSet()")
        .getValue(context, Set.class);

Map<?, ?> map = parser.parseExpression("new java.util.LinkedHashMap()")
        .getValue(context, Map.class);
```

Choosing the implementation affects the collection's behavior:

| Type | Common Characteristics |
| --- | --- |
| `ArrayList` | Ordered list, fast index-based access, allows duplicate elements. |
| `LinkedList` | Ordered list, supports adding/removing at both ends; index-based access is typically slower than ArrayList. |
| `HashSet` | Does not preserve iteration order; removes duplicates via `equals`/`hashCode`. |
| `LinkedHashSet` | Preserves insertion order and removes duplicate elements. |
| `HashMap` | Key/value map with no guaranteed iteration order. |
| `LinkedHashMap` | Preserves entry insertion order under default configuration. |

The constructor must exist and be accessible. Use the fully qualified class name for types such as `java.util.ArrayList` and `java.util.LinkedHashMap`.

## 8. Initializing Collections with Initial Elements

A constructor can accept another collection as an argument. You can combine an inline list or inline map with a collection constructor:

```spel
new java.util.ArrayList({'READ', 'WRITE'})
new java.util.LinkedHashSet({'RED', 'GREEN', 'BLUE'})
new java.util.LinkedHashMap({'primary': 'blue', 'secondary': 'green'})
```

In these examples, the inline list/map creates the source collection; the constructor of `ArrayList`, `LinkedHashSet`, or `LinkedHashMap` receives that collection and creates a new instance of the requested type.

Java example:

```java
List<?> permissions = parser.parseExpression(
        "new java.util.ArrayList({'READ', 'WRITE'})")
        .getValue(context, List.class);

Set<?> colors = parser.parseExpression(
        "new java.util.LinkedHashSet({'RED', 'GREEN', 'BLUE'})")
        .getValue(context, Set.class);

Map<?, ?> palette = parser.parseExpression(
        "new java.util.LinkedHashMap({'primary': 'blue', 'secondary': 'green'})")
        .getValue(context, Map.class);
```

This is a way to create a specific collection implementation when an expression requires a `List`, `Set`, or `Map` with particular semantics. If only a simple collection literal is needed, `{...}` or `{key:value}` is more concise and requires no constructor call.

## 9. Distinguishing Array Construction, Inline Collections, and Collection Constructors

These three ways of creating data are not interchangeable:

| Syntax | Result Type | When to Use |
| --- | --- | --- |
| `new int[] {1, 2, 3}` | `int[]` | The API requires a primitive array or an array with a specific component type. |
| `new String[] {'a', 'b'}` | `String[]` | Need an object array with a specific element type. |
| `{1, 2, 3}` | SpEL inline `List` | Small literal list without needing to specify an implementation. |
| `{'a': 1, 'b': 2}` | SpEL inline `Map` | Small literal map without needing to specify an implementation. |
| `new java.util.ArrayList({'a', 'b'})` | `ArrayList` | Need a mutable List or a specific implementation. |
| `new java.util.LinkedHashSet({'a', 'b'})` | `LinkedHashSet` | Need duplicate removal and insertion-order preservation. |

An inline list can be optimized by SpEL into a constant collection when all elements are fixed literals. A collection constructor creates an instance via the invoked constructor; do not assume it shares the same caching behavior as an inline constant list.

## 10. Using Inside Spring `@Value`

SpEL can initialize arrays or collections inside the `@Value` annotation. The outer `#{...}` pair is the delimiter for Spring to evaluate the expression; the inner `new ...` part is SpEL initialization syntax:

```java
@Component
public class FeatureConfiguration {

    @Value("#{new int[] {1, 2, 3}}")
    private int[] retryDelays;

    @Value("#{new java.util.ArrayList({'READ', 'WRITE'})}")
    private List<String> permissions;

    @Value("#{new java.util.LinkedHashMap({'primary': 'blue', 'secondary': 'green'})}")
    private Map<String, String> palette;
}
```

Spring performs conversion/binding of the result onto the target property. Generic types such as `List<String>` or `Map<String, String>` belong to the Java declaration and property metadata; SpEL constructor syntax does not write Java-style generic type arguments.

## 11. Parser Configuration and Compiler Limitations

Array construction is part of constructor reference syntax in SpEL. However, expressions containing array construction are currently not compiled into bytecode by the SpEL compiler. The expression can still be parsed and evaluated via the interpreter; this limitation only means the compiler does not support that expression kind.

If the application enables compiler mode (`SpelCompilerMode.IMMEDIATE` or `MIXED`), note that expressions containing `new int[4]`, `new int[] {1, 2, 3}`, or other array constructions will not be compiled. If performance is needed for repeatedly creating arrays, consider creating the array in Java and passing it via the root object or a variable.

`SpelParserConfiguration` can control certain parser behaviors such as auto-growing null references and collections when indexing into an appropriate element. Auto-grow does not change array constructor rules: an array created with `new` has the size specified by the construction expression, and Java arrays do not automatically resize after creation.

## 12. Controlling Object Creation Permissions

Constructor invocation can create instances of classes that `TypeLocator` and `ConstructorResolver` allow to be found. Untrusted expressions should not be evaluated with a `StandardEvaluationContext` that has full reflection permissions and arbitrary object creation capabilities.

Principles to apply:

- Allow only necessary classes in expressions.
- Use custom type locators and constructor resolvers if a class/constructor allowlist is needed.
- Avoid exposing constructors with side effects, file access, network connections, or heavy resource consumption.
- Validate array sizes, element counts, and arguments before evaluation.
- Pass runtime data via context variables rather than concatenating input into the expression source.
- For user-supplied expressions, consider a narrow helper API or restricted context instead of arbitrary constructor invocation.

`SimpleEvaluationContext` is designed with a restricted feature set for data binding and does not support type references; if creating objects with `new` is necessary, explicitly define the context and constructor permissions the application allows.

## 13. Common Errors and How to Handle Them

| Symptom | Cause to Check | How to Handle |
| --- | --- | --- |
| Array has default values instead of expected data | Used `new Type[size]` without an initializer. | Use `new Type[] { ... }` if you want to populate values immediately. |
| Received a List when the API expects an array | Used an inline list `{...}` instead of array construction. | Use `new int[] { ... }` or the appropriate array component type. |
| Class not found when calling constructor | Class name lacks package or classloader/type locator cannot find the class. | Use the fully qualified name, e.g., `new java.util.ArrayList()`. |
| No matching constructor found | Wrong argument count, incompatible types, or inaccessible constructor. | Verify constructor signature; pass explicitly typed arguments. |
| Unexpected constructor overload selected | Multiple constructors can accept the arguments after conversion. | Avoid ambiguous overloads; convert arguments explicitly or create a dedicated factory/helper. |
| Cannot initialize multidimensional array with initializer | SpEL currently does not support initializers for multidimensional arrays. | Create the array and populate elements in Java. |
| Array expression not compiled by the compiler | Array construction falls under SpEL compiler limitations. | Let the expression run interpreted or create the array in Java. |
| Array size causes error or high memory usage | Size is negative, invalid, or too large. | Validate size limits before evaluation. |
| Collection does not preserve expected order | Used `HashSet`/`HashMap` while expecting insertion order. | Use `LinkedHashSet`/`LinkedHashMap` if insertion order must be preserved. |

## Key Takeaways

- `new int[4]` creates an array of four default elements; `new int[] {1, 2, 3}` creates an array with an initializer.
- Multidimensional arrays can be created with `new int[4][5]`; SpEL currently does not support initializers for multidimensional arrays.
- Array sizes can come from runtime variables/properties; always validate the size.
- `new fully.qualified.ClassName(args)` invokes a class constructor; `java.lang` and primitives can use short names per SpEL syntax.
- You can create `ArrayList`, `LinkedList`, `HashSet`, `LinkedHashSet`, `HashMap`, or `LinkedHashMap` via constructors.
- Combine collection constructors with inline lists/maps to build specific implementations with initial data.
- `{...}` creates an inline List; `{key:value}` creates an inline Map; `new Type[] {...}` creates an array.
- SpEL syntax does not declare generic type parameters like Java; generics are handled on properties/binding or in Java code.
- Array construction is not compiled by the SpEL compiler; expressions can still run using the interpreter.
- Restrict the type locator/constructor resolver and validate inputs if expressions come from untrusted sources.

## References

- [Spring Framework Reference — Array Construction](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/array-construction.html)
- [Spring Framework Reference — Constructors](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/constructors.html)
- [Spring Framework Reference — Inline Lists](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/inline-lists.html)
- [Spring Framework Reference — Inline Maps](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/inline-maps.html)
- [Spring Framework Reference — Evaluation and Compiler Limitations](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework API — ConstructorResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ConstructorResolver.html)