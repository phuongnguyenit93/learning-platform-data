# Inline Collection Literals and Element Types in SpEL

## 1. What Is an Inline Collection?

Spring Expression Language (SpEL) allows declaring a collection directly inside an expression string. This syntax is useful when needing to pass a fixed list, describe key/value-style configuration, build nested data, or provide a set of values for a calculation.

SpEL has two main inline collection forms:

- **Inline list** uses curly braces with elements separated by commas: `{value1, value2, value3}`.
- **Inline map** uses curly braces with key and value pairs: `{key1:value1, key2:value2}`.

The result of an inline list is an object of type `List`; the result of an inline map is an object of type `Map`. Both can contain subexpressions, literal values, nested collections, or values retrieved from EvaluationContext.

A key point about data types: inline collection syntax does not declare a generic type such as `List<String>` or `Map<String, Integer>`. The type of each element, key, and value is determined by the evaluation result of the corresponding expression.

## 2. Initializing Parser and EvaluationContext

Inline collections can be evaluated using the standalone SpEL API. The following example uses `SpelExpressionParser` and `StandardEvaluationContext`:

```java
ExpressionParser parser = new SpelExpressionParser();
EvaluationContext context = new StandardEvaluationContext();

List<?> levels = parser.parseExpression("{'LOW', 'MEDIUM', 'HIGH'}")
        .getValue(context, List.class);

Map<?, ?> settings = parser.parseExpression(
        "{enabled:true, retries:3, 'service.name':'catalog'}")
        .getValue(context, Map.class);
```

`getValue(context, List.class)` requests that the outermost result have type `List`; it does not declare the generic type for each element. Similarly, `Map.class` does not specify the type of keys or values.

In Spring applications, expressions can also appear in configuration such as `@Value`. In that case, `#{...}` is the delimiter of a SpEL expression, while the curly braces inside the expression are inline collection syntax:

```java
@Value("#{ {'READ', 'WRITE'} }")
private List<String> permissions;
```

## 3. Inline Lists

### 3.1. Syntax and Empty Lists

A list with elements is written using `{...}`:

```java
List<?> numbers = parser.parseExpression("{1, 2, 3, 4}")
        .getValue(context, List.class);

List<?> names = parser.parseExpression("{'An', 'Binh', 'Chi'}")
        .getValue(context, List.class);
```

`{}` is the syntax for an empty list. This is a particularly useful case when an expression needs to return a valid collection even though it currently has no elements:

```java
List<?> empty = parser.parseExpression("{}")
        .getValue(context, List.class);
```

Elements are separated by commas. Whitespace or line breaks can be added between tokens to make the expression easier to read; whitespace inside string literals remains part of the string.

### 3.2. Element Types

Each element of an inline list is an independently evaluated SpEL expression. The runtime type of an element is the type of the value that expression returns. Therefore, a list can contain different types:

```java
List<?> values = parser.parseExpression(
        "{'READY', 3, true, null, 3.14}")
        .getValue(context, List.class);
```

In this example, the elements are `String`, the integer type corresponding to literal `3`, `Boolean`, `null`, and the real number type corresponding to literal `3.14`, respectively. SpEL does not automatically turn all elements into strings or into the same type just because they are in one list.

Subexpressions can also return values from the context:

```java
context.setVariable("currentRole", "ADMIN");

List<?> roles = parser.parseExpression(
        "{'USER', #currentRole, 'AUDITOR'}")
        .getValue(context, List.class);
```

Here `#currentRole` is retrieved from the variable registered in EvaluationContext. If the subexpression returns a business object, the element in the list will keep that object value.

### 3.3. Nested Lists

An inline list can contain other inline lists. Example:

```java
List<?> matrix = parser.parseExpression(
        "{{'a', 'b'}, {'x', 'y'}}")
        .getValue(context, List.class);
```

The result is a list of two elements; each element is itself a list. Nested structures can be used to describe groups, small matrices, or hierarchical data.

Another example:

```java
List<?> groups = parser.parseExpression(
        "{'backend', {'java', 'spring'}, 'frontend'}")
        .getValue(context, List.class);
```

A nested list is not automatically flattened. The element at the second position of `groups` remains a sublist.

## 4. Inline Maps

### 4.1. Syntax and Empty Maps

An inline map uses `{key:value}` syntax. Each key-value pair is separated from the next pair by a comma:

```java
Map<?, ?> inventor = parser.parseExpression(
        "{name:'Nikola', dob:'10-July-1856'}")
        .getValue(context, Map.class);
```

`{:}` is the syntax for an empty map:

```java
Map<?, ?> empty = parser.parseExpression("{:}")
        .getValue(context, Map.class);
```

The two empty syntaxes must be clearly distinguished:

| Expression | Result |
|---|---|
| `{}` | Empty list |
| `{:}` | Empty map |

If a key/value pair is written without a colon, the parser will interpret the structure as list syntax or report an error depending on the expression; use the colon properly for each map entry.

### 4.2. Key Names and Key/Value Types

Identifier-style key names do not require single quotes:

```java
Map<?, ?> config = parser.parseExpression(
        "{name:'catalog', enabled:true, retries:3}")
        .getValue(context, Map.class);
```

If a key contains a dot or characters that make it no longer a simple identifier, enclose the key in single quotes:

```java
Map<?, ?> config = parser.parseExpression(
        "{'service.name':'catalog', 'feature.enabled':true}")
        .getValue(context, Map.class);
```

In SpEL, single quotes can also be used for ordinary string keys, even when not required:

```java
Map<?, ?> config = parser.parseExpression(
        "{'name':'catalog', 'region':'ap-southeast-1'}")
        .getValue(context, Map.class);
```

The types of keys and values are determined by the values that the corresponding expressions produce. For typical configuration maps, keys are usually `String`; values can be strings, numbers, booleans, null, lists, maps, or other objects. Inline map syntax does not force all values to the same type.

Values can be accessed by key from Java:

```java
String name = (String) config.get("name");
Boolean enabled = (Boolean) config.get("enabled");
```

When needing to read a key containing a dot using SpEL index syntax, enclose the key in single quotes:

```java
context.setVariable("config", config);

String serviceName = parser.parseExpression(
        "#config['service.name']")
        .getValue(context, String.class);
```

### 4.3. Nested Maps and Collections as Values

The value of a map entry can be an inline map or inline list. Example:

```java
Map<?, ?> application = parser.parseExpression(
        "{service:{name:'catalog', port:8080}, " +
        "features:{'search', 'audit'}, " +
        "limits:{maxRequests:100, burst:20}}")
        .getValue(context, Map.class);
```

This structure creates an outermost map with nested values:

- `service` points to a map with `name` and `port`.
- `features` points to a list of feature names.
- `limits` points to a map containing limits.

Multiple levels of lists and maps can be combined to describe structured data. Access the right level: `application.get("service")` returns a submap, not the service name directly.

## 5. Inline Collections Can Contain Dynamic Expressions

List elements and map keys/values do not have to be fixed literals. They can reference variables, properties, methods, or other SpEL expressions, depending on the configured EvaluationContext:

```java
context.setVariable("region", "ap-southeast-1");
context.setVariable("replicas", 3);

Expression expression = parser.parseExpression(
        "{region:#region, replicas:#replicas, enabled:true}");

Map<?, ?> deployment = expression.getValue(context, Map.class);
```

When a variable's value changes, the next evaluation can produce a collection with different contents. This is useful when part of the structure is fixed while the data depends on the context at runtime.

Distinguish between an expression being parsed once and the value being computed when calling `getValue()`. The parser builds the expression structure; dynamic elements are resolved when the expression is evaluated.

## 6. Constant Collections and Behavior Across Multiple Evaluations

SpEL optimizes inline collections when the entire structure consists only of fixed literals:

- An inline list consisting entirely of fixed literals may be created as a constant list and stored in the expression instead of building a new list on each evaluation.
- An inline map consisting of fixed literals, or a nested structure consisting only of constant lists/maps, may be created as a constant map.
- If any element, key, or value depends on a variable or dynamic expression, the collection must be evaluated against the context on each run.

Fixed list example:

```java
Expression fixedList = parser.parseExpression(
        "{'LOW', 'MEDIUM', 'HIGH'}");

List<?> first = fixedList.getValue(context, List.class);
List<?> second = fixedList.getValue(context, List.class);
```

Dynamic list example:

```java
context.setVariable("role", "USER");

Expression dynamicList = parser.parseExpression(
        "{'DEFAULT', #role}");

List<?> roles = dynamicList.getValue(context, List.class);
```

Constant optimization means SpEL may reuse the collection value attached to the expression. Therefore, do not assume each call to `getValue()` returns a new collection that the application can freely modify. Avoid using a fixed inline collection as a mutable temporary data area. If a separate mutable list or map is needed per request, create a copy in Java, for example `new ArrayList<>(result)` or `new HashMap<>(result)`.

That a collection is cached also does not mean inline syntax automatically declares a generic type or guarantees all elements share the same type. Constant/dynamic is an evaluation and optimization characteristic of the expression; element types still depend on each value.

## 7. Element Types, Generic Types, and Data Conversion

### 7.1. Inline Literals Do Not Declare Generic Types

Expressions such as `{'A', 'B'}` and `{name:'A'}` create lists/maps at runtime. SpEL has no syntax to declare a generic type right in the literal, for example you cannot write `List<String>{...}` or `Map<String, Integer>{...}`.

If a strongly typed collection is needed in Java code, declare the target variable or property with a generic type:

```java
List<String> names = List.of("An", "Binh");
Map<String, Integer> retryLimits = Map.of("catalog", 3);
```

When receiving results from SpEL, values can be checked or converted according to the target type. Note that `List.class` and `Map.class` only describe the outermost collection type; they carry no element generic information.

### 7.2. Conversion Based on Target Property Generic Type

SpEL integrates with Spring ConversionService. The conversion mechanism understands the target property's generic metadata, so when assigning values into a collection with a specific element type, Spring can convert each element to preserve the target type.

For example, a bean with a `List<Boolean>` property:

```java
public class FeatureFlags {
    public List<Boolean> enabled = new ArrayList<>();
}

// The bean initially has one Boolean element.
FeatureFlags flags = new FeatureFlags();
flags.enabled.add(Boolean.TRUE);

EvaluationContext context = new StandardEvaluationContext();

parser.parseExpression("enabled[0]")
        .setValue(context, flags, "false");

Boolean enabled = flags.enabled.get(0);
// enabled == Boolean.FALSE
```

The passed-in value is the string `"false"`, but the element property has type `Boolean`. ConversionService recognizes the list's generic type and converts the string into `Boolean.FALSE`.

This happens at the boundary of assigning a value to a property with type metadata. It does not mean every inline list automatically becomes `List<Boolean>` or `List<String>`. When evaluating an inline collection standalone, check the runtime type of each element or proactively convert to the target type in the application.

### 7.3. Distinguishing Collection Literals from Arrays

Inline lists and arrays are two different result types:

```java
List<?> list = parser.parseExpression("{1, 2, 3}")
        .getValue(context, List.class);

int[] array = parser.parseExpression("new int[]{1, 2, 3}")
        .getValue(context, int[].class);
```

`{1, 2, 3}` creates a list; `new int[]{1, 2, 3}` creates a primitive `int[]` array. If a Java API requires an array, you cannot rely solely on an inline list having the same values to treat the two types as equivalent. Convert explicitly or use array construction syntax.

## 8. Combining Inline Collections with Element Access

After evaluation, Java APIs can be used to read the list/map, or the result can be stored in a SpEL variable for access by index:

```java
context.setVariable("priorities",
        parser.parseExpression("{'LOW', 'MEDIUM', 'HIGH'}")
                .getValue(context));

String selected = parser.parseExpression("#priorities[1]")
        .getValue(context, String.class);
// selected = "MEDIUM"
```

For maps, use the key in square brackets:

```java
context.setVariable("limits",
        parser.parseExpression("{max:100, burst:20}")
                .getValue(context));

Integer max = parser.parseExpression("#limits['max']")
        .getValue(context, Integer.class);
```

List indices start at `0`. Maps are accessed by key; if the key is a string, enclose it in single quotes inside square brackets. For nested maps, continue indexing by level or use property/index access matching the structure.

## 9. Common Mistakes

| Symptom | Cause | How to Handle |
|---|---|---|
| Using `{}` while expecting an empty map | `{}` creates an empty list. | Use `{:}` for an empty map. |
| Map fails to parse | Entry missing `:` between key and value or missing comma between entries. | Use the form `{key:value, otherKey:otherValue}`. |
| Key with a dot is parsed as a property name | Key was not enclosed in quotes. | Use `{'service.name':'catalog'}`. |
| Casting result to `List<String>` but an element has another type | Literal does not declare generics and subexpressions may return multiple types. | Check elements or convert explicitly to the target type. |
| Assigning a string to a Boolean element fails to convert | Target lacks suitable generic metadata or ConversionService lacks the needed converter. | Check property type, TypeDescriptor, and the converter in use. |
| Modifying a fixed list/map affects subsequent evaluations | Expression may cache collections consisting of fixed literals. | Create a mutable copy in Java before modifying. |
| Array needed but List received | Inline list and array construction have different result types. | Use `new int[]{...}` or convert the list to an array. |
| Accessing the wrong level in a nested collection | An outer-level element may be a nested list/map. | Check the type and structure at each level before deep access. |

When encountering an error, break the expression into small parts: parse the list/map separately, retrieve values using `getValue()`, check runtime types and individual elements, and only then combine dynamic expressions or index operations. For conversion errors, check the target property's generic type and ConversionService instead of assuming the literal already carries the desired type.

## 10. Key Takeaways

- `{a, b, c}` creates an inline list; `{key:value}` creates an inline map.
- `{}` is an empty list; `{:}` is an empty map.
- Lists can nest lists; maps can nest maps or contain lists/maps as values.
- Each element, key, and value is evaluated to its own runtime value; inline syntax does not declare generic types.
- Identifier-style map keys may omit quotes; keys with dots such as `service.name` must be enclosed in quotes.
- Dynamic expressions can reference variables, properties, or methods in EvaluationContext.
- Structures consisting only of fixed literals may be cached as constant collections; do not assume each evaluation creates a new collection.
- ConversionService can convert elements according to the target property's generic metadata when assigning data.
- An inline list is a `List`; arrays must be created using `new Type[]{...}` syntax or converted separately.

## References

- [Spring Framework Reference — Inline Lists](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/inline-lists.html)
- [Spring Framework Reference — Inline Maps](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/inline-maps.html)
- [Spring Framework Reference — Evaluation and Type Conversion](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework Reference — Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html)
