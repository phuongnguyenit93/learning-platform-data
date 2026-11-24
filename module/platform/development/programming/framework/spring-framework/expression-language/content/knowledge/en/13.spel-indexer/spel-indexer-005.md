# Index Expressions and Dynamically Computed Values in SpEL

## Objectives

An indexer is the square-bracket syntax `[...]` of Spring Expression Language (SpEL), used to retrieve an element or property from the structure being accessed. The index does not have to be a hardcoded number or key: the content inside `[...]` is a SpEL expression evaluated when the outer expression runs.

As a result, an application can select an element by variable, property, calculation, or lookup value at runtime. For example, `items[#selectedIndex]` selects an element by the `selectedIndex` variable, while `officers[#role]` looks up a map by a key provided by the context.

## 1. Basic Syntax and 0-Based Indexing

An indexer uses square brackets after the object or property to be accessed:

```spel
items[0]
officers['president']
members[0].name
```

For arrays and positionally indexed structures, indexing starts at `0`: the first element is `[0]`, the second element is `[1]`. Do not use 1-based conventions like user-facing ordinal numbers.

SpEL supports indexers on many kinds of structures:

| Structure | How to Access | Return Value |
| --- | --- | --- |
| Array | `inventions[3]` | Element at the fourth position. |
| `List` | `members[0]` | First element. |
| Other Collection such as `Set` | `members[0]` | First element in the order returned by the iterator. |
| `Map` | `officers['president']` | Value corresponding to the key `president`. |
| `String` | `name[7]` | Character at the eighth position, as a `String`. |
| Object | `#root['name']` | Property named `name`. |

For `List`, SpEL accesses directly by position. For a non-`List` Collection such as `Set`, SpEL traverses via `Iterator` to retrieve the nth element. Because the order of some collections is not guaranteed, avoid positional indexing on collections without a deterministic order if the result must be deterministic.

## 2. The Index Inside Square Brackets Is an Expression

The part inside `[...]` is parsed as a SpEL expression. Therefore, the index can be a literal, a variable, a property, or a calculation:

```spel
items[2]
items[#selectedIndex]
items[#page * #pageSize]
items[#page * #pageSize + #offset]
```

In the last example, SpEL computes `#page * #pageSize + #offset` first, then uses the result as the index. When the variables change, the same parsed expression can select a different element.

For a `Map`, the expression inside square brackets produces a key:

```spel
officers['president']
officers[#selectedRole]
prices[#productCode]
```

The key can be a string, number, enum, or another type matching the map's key type. If the map has a declared key type, SpEL can use the evaluation context's `TypeConverter` to convert the key to that type. It is better to pass the key with the exact type from the start so the expression is clear and avoids relying on implicit conversion.

## 3. Computing Indices Dynamically from the EvaluationContext

The easiest way to keep control is to pass the index value into the evaluation context via a variable. There is no need to rebuild the expression string every time the index changes.

Suppose the root object `Order` has an `items` property, and each item has `productName`. The application wants to read an item by the position chosen by the user:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("items[#selectedIndex].productName");

StandardEvaluationContext context = new StandardEvaluationContext(order);
context.setVariable("selectedIndex", requestedIndex);

String productName = expression.getValue(context, String.class);
```

`requestedIndex` is supplied as a data value. SpEL evaluates the variable `#selectedIndex`, uses the result to get an element from `items`, and then reads the `productName` property of that element.

For example, with an `items` list having names `Keyboard`, `Mouse`, `Monitor` and `requestedIndex = 1`, the result is `Mouse`.

Variables in SpEL have a `#` prefix. The name passed to `setVariable` does not include `#`:

```java
context.setVariable("selectedIndex", 1);
```

```spel
items[#selectedIndex]
```

Do not splice `requestedIndex` directly into the expression source using string concatenation. Passing it through the context separates data from expression syntax, avoids errors when input contains special characters, and allows reusing the parsed expression.

## 4. Combining Indices with Properties and Other Expressions

Indexers can be chained with property navigation, method invocation, and other indexers:

```spel
members[#memberIndex].name
orders[#orderIndex].items[#itemIndex].productName
products[#productIndex].price * #quantity
names[#position].toUpperCase()
```

The expressions above respectively:

- Select a member and read `name`.
- Select an order, then select an item inside the order and read the product name.
- Retrieve the product price and multiply it by a quantity passed via a variable.
- Select a character from a string and call `toUpperCase()` on that single-character string.

The string indexer returns a `String`, not a `Character`. This is useful when you need to concatenate characters, call string methods, or compare the result with a string literal.

An index can also be computed using a conditional expression or other operators:

```spel
items[#useLast ? #itemsCount - 1 : #selectedIndex]
```

This example selects the last element if `#useLast` is true; otherwise, it uses `#selectedIndex`. Ensure the variables exist and the expression returns an index type compatible with the target structure.

## 5. Example with a Map and Dynamically Computed Key

Suppose the root object has an `officers` map with `String` keys. The application determines the role at runtime:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("officers[#role]");

StandardEvaluationContext context = new StandardEvaluationContext(society);
context.setVariable("role", requestedRole);

Inventor officer = expression.getValue(context, Inventor.class);
```

If `requestedRole` is `president`, SpEL retrieves the value of `officers['president']`. When the role changes to `secretary`, the same expression looks up a different key.

For maps with non-string keys, supply a value of the correct type. For example, a map using an enum `Color` as key can be accessed using a type reference:

```spel
fruitMap[T(example.Color).RED]
```

In a real expression, the enum's package must match the class in the application and the type locator must permit referencing that class. If the key comes from a context variable, you can pass the enum instance into `#color` and use `fruitMap[#color]`.

If the key does not exist, `Map.get(key)` typically returns `null`. That differs from an out-of-bounds index on a list/array. If you need to distinguish a missing key from a key with a null value, check `containsKey` on the map.

## 6. Reading Object Properties with an Indexer

Besides maps, indexer syntax can also read an object's property by name:

```spel
#root['name']
#root['placeOfBirth']
```

This is similar to property access using dot notation:

```spel
name
placeOfBirth
```

Property-style indexers are useful when the property name is computed dynamically:

```java
context.setVariable("propertyName", requestedProperty);
```

```spel
#root[#propertyName]
```

Only use this approach when the context's property accessor permits accessing that property. Do not treat making the property name a dynamic variable as meaning every property should be exposed to expressions.

## 7. Controlling Nulls and Out-of-Bounds Indices

A normal indexer requires the target to exist and the index to be valid. Common scenarios include:

| Scenario | Behavior to Note |
| --- | --- |
| List/array/string with valid index | Returns the corresponding element or character. |
| Negative or out-of-bounds index | Usually raises `SpelEvaluationException` due to an invalid or out-of-bounds index. |
| Map missing key | `Map.get` usually returns `null`. |
| Target collection/map is null | A normal indexer cannot access a null target. |
| Index expression returns null or an unconvertible type | Cannot produce a valid index; evaluation may fail. |

With Spring Framework 6.2 and later, you can use null-safe indexing with the `?.[` syntax:

```spel
members?.[0]
officers?.['president']
customer?.orders?.[#selectedIndex]
```

If the target immediately before `?.[` is null, the result of the indexer is null instead of throwing an error solely because the target is null. Null-safe indexing does not turn an out-of-bounds index into a valid value and does not automatically apply a default value to a null result.

With Spring Framework 7.0, null-safe indexing also supports structures wrapped in `Optional`: if the Optional is null or empty, the null-safe access result is null; if a value is present, SpEL indexes into the inner value.

If you want to use the result with a default value, you can combine it with the Elvis operator:

```spel
members?.[#selectedIndex] ?: #fallbackMember
```

Here `#fallbackMember` is only used when the access result is null. Distinguish between a null target, a missing map key, and an element whose actual value is null if the business logic needs to handle them separately.

## 8. Indexing and Mutating Data

Indexers are not only for reading. With a writable expression, `setValue` can update an element of a supported structure, for example:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("items[#selectedIndex].status");

StandardEvaluationContext context = new StandardEvaluationContext(order);
context.setVariable("selectedIndex", 1);

expression.setValue(context, "SHIPPED");
```

Whether writing succeeds depends on whether the target and accessor support writing. Lists and maps can update elements/keys; arrays can update existing elements; strings cannot be modified directly because `String` is immutable. For custom structures, an accessor supporting writes must be registered.

If `autoGrowCollections` is enabled in `SpelParserConfiguration`, certain writes to a List can automatically grow the list when the index is past the last element, within `maximumAutoGrowSize`. This is a configuration behavior intended for writing scenarios; do not rely on it to mask index errors when reading. Arrays cannot auto-grow in size.

## 9. IndexAccessor for Custom Structures

Starting from Spring Framework 6.2, applications can implement and register an `IndexAccessor` so that SpEL supports structures that are not standard arrays, collections, maps, strings, or object properties.

For example, a `FruitMap` type has `getFruit(Color)` and `setFruit(Color, String)` APIs but does not implement `Map`. You can register a `ReflectiveIndexAccessor`:

```java
IndexAccessor accessor = new ReflectiveIndexAccessor(
        FruitMap.class, Color.class, "getFruit", "setFruit");
context.addIndexAccessor(accessor);
context.setVariable("fruitMap", new FruitMap());
```

Once registered, expressions can read and write using indexer syntax:

```spel
#fruitMap[T(example.Color).RED]
#fruitMap[T(example.Color).RED] = 'strawberry'
```

`ReflectiveIndexAccessor` uses the public read-method and, if configured, the public write-method matching the provided signature. If compilation support is needed for expressions using a custom accessor, the accessor must implement `CompilableIndexAccessor`; the built-in reflective accessor also supports compilation for reads that meet the API's conditions.

## 10. Reusing an Expression with Changing Indices

There is no need to re-parse the expression each time the index changes. You can parse once and then update the variable in the context:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("items[#index].productName");

StandardEvaluationContext context = new StandardEvaluationContext(order);

context.setVariable("index", 0);
String first = expression.getValue(context, String.class);

context.setVariable("index", 2);
String third = expression.getValue(context, String.class);
```

The parsed expression retains its syntactic structure; the `#index` variable is re-read when `getValue` runs. This reduces parsing work and keeps changing data from becoming part of the expression source.

If the context is used concurrently from multiple threads, do not share a single mutable context and mutate the `#index` variable between evaluations. Create a separate context per evaluation or per request so requests do not overwrite each other's variables.

## 11. Common Errors and How to Handle Them

| Symptom | Cause to Check | How to Handle |
| --- | --- | --- |
| Wrong element retrieved | Mistaking indexing as 1-based or relying on unstable Set order. | Use zero-based indices; for Sets, convert to a List with deterministic order if stable position is needed. |
| Index out of bounds | Dynamically computed value is negative or greater than structure size. | Validate the index and size before evaluation, or select elements via controlled rules. |
| Map returns null | Key does not exist or the value mapped to that key is null. | Check `containsKey` if you need to distinguish the two cases. |
| Cannot convert map key | Map's key type differs from the index value type. | Pass the key with the right type or configure an appropriate TypeConverter. |
| Null-safe index still produces null | Target is null, map key is missing, or the element itself has a null value. | Identify the source of null; use Elvis/default or separate checks per business logic. |
| `?.[` fails to parse | Application runs Spring Framework prior to 6.2. | Use explicit null checks or upgrade the framework version if this syntax is needed. |
| Custom object cannot be indexed | No compatible `IndexAccessor` in the evaluation context. | Register an appropriate `IndexAccessor` or `ReflectiveIndexAccessor`. |
| Expression behaves wrongly under multiple requests | Shared mutable context and index variable gets overwritten. | Use a separate evaluation context for each request/evaluation. |

## Key Takeaways

- `[...]` is an index expression; its inner content is evaluated at runtime.
- Numeric indices of arrays, lists, collections, and strings start at `0`.
- Lists are accessed by position; collections other than List are traversed via Iterator, so order may not be stable.
- Maps use the expression inside square brackets as a key; dynamic keys can be passed via `#variable`.
- String indexers return characters as `String`; object indexers can access properties by name.
- Use `items[#selectedIndex]` and `map[#key]` to pass dynamic data via `EvaluationContext` instead of concatenating expression strings.
- Spring Framework 6.2 adds null-safe indexing `?.[` and `IndexAccessor` for custom structures; Spring 7.0 extends null-safe indexing to structures inside Optional.
- Out-of-bounds indices are still errors; null-safe indexing only handles a null target.
- `setValue` can be used to write if the target/accessor supports it; collection auto-grow only applies according to configuration and limits.
- Parse the expression once and reuse it with an appropriate context; do not share a mutable context across concurrent requests.

## References

- [Spring Framework Reference — Properties, Arrays, Lists, Maps, and Indexers](https://www.springframework.org/spring/reference/core/expressions/language-ref/properties-arrays.html)
- [Spring Framework Reference — Safe Navigation Operator](https://springframework.org/spring-framework/reference/7.1/core/expressions/language-ref/operator-safe-navigation.html)
- [Spring Framework API — IndexAccessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/IndexAccessor.html)
- [Spring Framework API — ReflectiveIndexAccessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/ReflectiveIndexAccessor.html)
- [Spring Framework source — Indexer](https://github.com/spring-projects/spring-framework/blob/main/spring-expression/src/main/java/org/springframework/expression/spel/ast/Indexer.java)