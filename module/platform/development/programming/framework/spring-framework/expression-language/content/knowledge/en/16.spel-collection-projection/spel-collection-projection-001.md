# Collection projection `.![projectionExpression]` in SpEL

## Objective

Collection projection lets a collection supply each element in turn so that SpEL evaluates a sub-expression. The result is a new collection containing the value computed for each source element. The syntax is `.![projectionExpression]`.

Projection is commonly used to transform a list of objects into a list of properties, build display strings, compute a value for each element, or extract data from a map. For example, `members.![placeOfBirth.city]` produces a list of cities where the members were born.

Key distinction: projection transforms each element and keeps one result per source element; selection (`.?[...]`) filters elements that match a condition. Projection does not automatically remove elements with null results or duplicate values.

## 1. Basic syntax

```spel
members.![name]
members.![placeOfBirth.city]
members.![name.toUpperCase()]
```

For each element in `members`, SpEL evaluates the expression inside `![...]`. If `members` is a list of three members, `members.![name]` produces a list of three names in the same iteration order as the source.

Java example:

```java
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context = new StandardEvaluationContext(society);

Expression expression = parser.parseExpression("members.![placeOfBirth.city]");
List<?> cities = expression.getValue(context, List.class);
```

Assuming two members were born in Smiljan and Idvor respectively, the result is `['Smiljan', 'Idvor']`. Projection returns a new result collection; it does not modify the original `members` collection.

## 2. Active object inside projection

In a projection expression, `#this` is the current element being processed. At the outer level, `#root` still points to the original root object of the evaluation.

```spel
members.![#this.name]
members.![#this.placeOfBirth.city]
members.![#this.score >= #root.minimumScore]
```

- `#this.name` reads the name of the current member.
- `#this.placeOfBirth.city` navigates from the current member to the birth city.
- `#root.minimumScore` reads the threshold on the root object, while `#this.score` is the score of the member currently being processed.

In simple projections, properties can be written without `#this`, such as `members.![name]`. Using `#this` explicitly makes expressions easier to read when there are multiple object levels or when you need to distinguish the current element from the root object.

## 3. Projection on arrays, Iterable, and Map

SpEL supports projection on arrays, any type implementing `java.lang.Iterable`, and `java.util.Map`.

| Source | Projection | Result |
| --- | --- | --- |
| Array | `names.![toUpperCase()]` | Collection containing uppercased strings. |
| `List` | `members.![name]` | List of names in list order. |
| `Set` | `members.![name]` | Result list in the Set's iterator order. |
| `Map` | `officers.![value.name]` | List of names taken from each entry's value. |

With a `Set` or an unordered collection, the result order depends on the source's iterator. If order is part of the business requirement, use a source with a deterministic order, such as a `List` or `LinkedHashSet`.

### Projection on Map

When projection runs on a `Map`, the sub-expression is evaluated on each entry, which is a `java.util.Map.Entry` object. Two important properties are `key` and `value`:

```spel
officers.![key]
officers.![value]
officers.![value.name]
officers.![key + ' -> ' + value.name]
```

The result of a Map projection is a `List` containing the values computed from each entry; it is not a new Map. If you need to retain keys/values as a map, build that structure in Java or use an appropriate API/helper.

Java example:

```java
Expression expression = parser.parseExpression("officers.![key + ' -> ' + value.name]");
List<?> labels = expression.getValue(context, List.class);
```

The order of results reflects the Map's iteration order. With a `HashMap`, do not assume a stable order; use a `LinkedHashMap` or an ordered Map if needed.

## 4. Projection vs. Selection

Selection and projection both iterate over a collection, but they address two different needs:

| Operator | Syntax | Purpose | Result |
| --- | --- | --- | --- |
| Selection | `.?[condition]` | Keep elements that satisfy a condition. | Collection containing the selected source elements. |
| Projection | `.![expression]` | Compute a value from each element. | Collection containing the results of the sub-expression. |

For example, to get only the names of members with Serbian nationality:

```spel
members.?[nationality == 'Serbian'].![name]
```

SpEL first filters the members with `nationality == 'Serbian'`, then projects `name` from each retained member. The result is a list of names, no longer a list of member objects.

If elements that produce null results need to be kept, projection still keeps their corresponding positions. If you need to exclude elements that do not satisfy a condition, use selection before projection or filter the data at the application layer.

## 5. Projection can compute values and call methods

The sub-expression does not only read properties. It can concatenate strings, perform calculations, call methods, or use variables in `EvaluationContext`:

```spel
members.![name.toUpperCase()]
products.![price * #quantity]
members.![name + ' (' + nationality + ')']
members.![#prefix + #this.name]
```

Example passing a variable from Java:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("members.![#prefix + #this.name]");

StandardEvaluationContext context = new StandardEvaluationContext(society);
context.setVariable("prefix", "Member: ");

List<?> labels = expression.getValue(context, List.class);
```

`#prefix` is a variable registered by the application; `#this` changes for each member. The same expression can be evaluated with a different context to produce results based on runtime data.

Because the sub-expression runs for each element, a method call can be executed many times. Avoid calling methods with side effects such as writing to a database, sending messages, or mutating state inside a projection. Use projection expressions for predictable reads and calculations.

## 6. Nested projection

Projections can be nested to transform multi-level structures. For example, a list of orders where each order has a list of items:

```spel
orders.![items.![productName]]
```

The result is a list of lists of product names: each order produces a sublist. If you want to flatten it into a single list, SpEL projection does not flatten structures automatically; use stream/flatMap or a helper method in Java.

Projection can be combined with multi-level property navigation:

```spel
orders.![customer.address.city]
departments.![employees.![email]]
```

In nested expressions, `#this` represents the current element in the projection scope currently being executed. When you need to access the original root object, use `#root` to avoid confusing it with objects at an inner nested level.

## 7. Null and safe projection

If the source collection is null, regular projection is not a null check. With Spring Framework 6.2 and later, you can use null-safe projection `?.!`:

```spel
members?.![placeOfBirth.city]
```

If `members` is null, the expression returns null instead of throwing an error solely because the source collection is null. If `members` is not null, projection works as usual.

Null-safe projection handles a null source collection; it does not automatically handle every null object inside each element. If a member can be null or `placeOfBirth` can be null, use safe navigation inside the sub-expression:

```spel
members?.![#this?.placeOfBirth?.city]
```

When an element evaluates to null, projection still keeps that null result in the list. It does not automatically drop elements like selection does.

With Spring prior to 6.2, use an explicit null check or handle the collection in Java before evaluating the projection. The `?.!` syntax requires a framework version that supports it.

## 8. Size, order, and result type

Projection performs one evaluation per source element. For an array or `Iterable`, the result has the same number of elements as the source; for a Map, the result has one value per entry. If the sub-expression returns null, the null value still occupies a position.

Points to remember:

- Projection creates a new result collection and does not modify the source collection.
- Result values can be object references; if a projection returns `#this` itself, the elements in the result list are still the original objects, not deep copies.
- Duplicate values are not automatically removed.
- Result order follows the source's iteration order.
- For a Map, the result is a List; keys are not automatically preserved in the result structure.

Example:

```spel
members.![#this]
```

The expression above creates a new list containing references to the existing members. Changing the structure of the result list does not change the structure of the source list, but mutating the state of a member inside still affects that same object because both sides share the reference.

## 9. Reusing expressions

You do not need to re-parse the same expression every time a projection runs. You can parse it once and evaluate it with the appropriate root object/context:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("members.![name]");

List<?> namesForFirstSociety = expression.getValue(firstContext, List.class);
List<?> namesForSecondSociety = expression.getValue(secondContext, List.class);
```

A parsed expression can be reused; the data projected is taken from the root object and context on each `getValue` call. If variables in the context are used, provide the right values for each evaluation.

Do not share a mutable `EvaluationContext` across concurrent requests if those requests can modify variables or context state. Use a separate context per request or evaluation to prevent data from being overwritten.

## 10. Common errors and how to handle them

| Symptom | Cause to check | How to handle |
| --- | --- | --- |
| Using `.![]` when wanting to filter elements | Projection transforms each element; it does not test a condition to exclude elements. | Use `.?[condition]` before projection. |
| Map projection does not return a Map | Projection on a Map returns a List of results over each `Map.Entry`. | Read `key` and `value` in the expression; build a new Map in Java if keys must be retained. |
| Result contains null elements | The sub-expression returns null or safe navigation encounters a null property. | Handle null explicitly or filter elements with selection if removal is needed. |
| Null source collection causes an error | Regular projection was used on null. | With Spring 6.2+, use `?.!`; on older versions, check for null beforehand. |
| Error when a property inside an element is null | The collection is not null, but a nested object inside is null. | Use safe navigation in the projection expression, for example `#this?.placeOfBirth?.city`. |
| Unexpected result order | The source collection does not guarantee iterator order. | Use a collection with a deterministic order if order is required. |
| Method gets called multiple times | Projection evaluates the sub-expression for each element. | Avoid methods with side effects; prepare data beforehand or use read-only helpers. |
| Nested results instead of a flat list | Nested projection preserves multi-level structure. | Use `flatMap` or a Java helper to flatten. |

## Key takeaways

- `.![projectionExpression]` evaluates the sub-expression for each element and creates a new result collection.
- `#this` is the current element; `#root` remains the original root object.
- Projection supports arrays, `Iterable`, and `Map`; Map projection operates on `Map.Entry` and returns a List.
- Use `key` and `value` to read a Map entry inside projection.
- Selection `.?[...]` filters elements; projection `.![...]` transforms elements.
- Projection keeps one result per source element, even when the result is null; it does not automatically deduplicate or filter.
- Projection can call methods and perform calculations, but avoid side effects because the expression runs for each element.
- Nested projection produces nested collections; use another helper if flattening is needed.
- Spring Framework 6.2+ supports null-safe projection `?.!` for null source collections; safe navigation inside the sub-expression is still needed if element properties can be null.
- The result is a new collection, but referenced objects inside are not deep-copied.
- Parse the expression once and reuse it with the appropriate root object and context.

## References

- [Spring Framework Reference — Collection Projection](https://docs.spring.io/spring-framework/reference/6.2/core/expressions/language-ref/collection-projection.html)
- [Spring Framework Reference — Safe Navigation Operator](https://docs.spring.io/spring-framework/reference/6.2/core/expressions/language-ref/operator-safe-navigation.html)
- [Spring Framework API — Projection](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/expression/spel/ast/Projection.html)