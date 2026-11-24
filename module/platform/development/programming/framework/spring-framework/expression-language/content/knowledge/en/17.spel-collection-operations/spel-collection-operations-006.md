# Preserving order when filtering and projecting collections in SpEL

## Objectives

When using Spring Expression Language (SpEL) to filter or transform a collection, the result order depends on the iteration order of the source collection and the type of structure the operator returns. With a `List` or array, element order can be preserved throughout selection and projection. With a `Set` or `Map`, you need to understand the iterator order of the source structure; do not assume every collection has a stable order.

Example:

```spel
orders.?[status == 'PAID'].![id]
```

The expression filters orders with status `PAID`, then extracts the `id` of each retained order. The result follows the encounter order of the `orders` collection. Selection removes non-matching elements; projection produces a corresponding value for each remaining element.

## 1. Order comes from the source collection

SpEL iterates over a collection according to the iterator or index mechanism provided by the structure. Selection and projection do not automatically sort data by a new criterion.

| Source collection | Iteration order | Impact on result |
| --- | --- | --- |
| Array | By index from `0` to the end | Result follows the element order in the array. |
| `List` | By the List's element order | Selection preserves the encounter order of selected elements; projection creates results in the same order. |
| `LinkedHashSet` | By insertion order | Result follows iterator order, usually the order elements were added. |
| `TreeSet` | By comparator/natural ordering | Result follows the sorted order provided by the Set. |
| `HashSet` | Order not guaranteed | Do not rely on observed positions to determine results across runs. |
| `LinkedHashMap` | By the iteration order maintained by the Map | Projection iterates entries in the order the Map provides; see the separate note on Map selection results. |
| `TreeMap` | By comparator key order | Projection iterates entries in the key order the Map provides. |
| `HashMap` | Order not guaranteed | Do not rely on key/value order observed in a single run. |

If you want a result with a stable order, start from a source with a well-defined order, such as `ArrayList`, `LinkedHashSet`, `TreeSet`, `LinkedHashMap`, or `TreeMap`, depending on business rules.

## 2. Selection preserves encounter order on Iterable

Collection selection uses `.?[condition]` to keep elements for which the condition expression returns `true`:

```spel
orders.?[status == 'PAID']
```

For an array or an `Iterable` such as `List`, SpEL iterates through the source and adds matching elements to the result collection in encounter order. Non-matching elements are skipped; the remaining elements keep their relative order.

Example ordered source:

```text
[A: PENDING, B: PAID, C: PAID, D: CANCELLED, E: PAID]
```

Selection:

```spel
orders.?[status == 'PAID']
```

Produces elements in the order `B, C, E`. Selection does not re-sort them by ID, timestamp, or a property value.

Selection can use `#this` explicitly to refer to the element being evaluated:

```spel
orders.?[#this.status == 'PAID']
```

At the condition level, `#this` is the current order. `#root` remains the root object of the entire evaluation if you need to reference a threshold or property outside the collection.

## 3. Projection preserves input element order

Collection projection uses `.![expression]` to compute a value for each element:

```spel
orders.![id]
```

For an array or `Iterable`, projection creates a result List in source iteration order. Each input element produces one corresponding result, even if the sub-expression returns null or two elements yield the same value.

Example:

```text
Input:  [Order(id=12), Order(id=7), Order(id=21)]
Output: [12, 7, 21]
```

Expression:

```spel
orders.![id]
```

Projection does not automatically sort into `[7, 12, 21]`. If sorting is required, perform an explicit sort step in Java or supply an already-sorted collection as input.

## 4. Combining selection and projection

To both filter and transform, you can chain the two operators:

```spel
orders.?[status == 'PAID'].![id]
```

The process is:

1. Iterate `orders` in source order.
2. Evaluate the condition `status == 'PAID'` on each order.
3. Keep matching orders in encounter order.
4. Evaluate `id` on each kept order.
5. Create the result List in the same order.

Example source:

```text
[Order(12, PAID), Order(7, PENDING), Order(21, PAID), Order(4, CANCELLED)]
```

Result:

```text
[12, 21]
```

This is the order of the two matching orders in the source, not ascending ID order.

If you want to filter by one property and then project multiple values, the projection expression can build an inline list for each element:

```spel
orders.?[status == 'PAID'].![{id, customer.name, total}]
```

The result is a List containing sublists, each describing one selected order. Nested projection does not automatically flatten the result.

## 5. Distinguishing order, filtering, and sorting

Selection, projection, and sorting are three different operations:

| Operation | SpEL or Java | Effect on order |
| --- | --- | --- |
| Selection | `items.?[condition]` | Removes non-matching elements; preserves encounter order of kept elements on Iterable. |
| Projection | `items.![expression]` | Transforms each element; preserves encounter order of results on Iterable. |
| Sorting | Java `List.sort`, `Stream.sorted`, or a sorted collection | Orders by a specified comparator/criterion. |

SpEL does not have a dedicated collection sort operator analogous to `.?[]` or `.![...]`. If the requirement is "filter then sort", perform explicit sorting in Java after filtering, or prepare a sorted collection before passing it into SpEL.

Java example using a comparator:

```java
List<Order> paidOrders = orders.stream()
        .filter(order -> "PAID".equals(order.getStatus()))
        .sorted(Comparator.comparing(Order::getCreatedAt)
                .thenComparing(Order::getId))
        .toList();
```

Or use SpEL to filter/project on `paidOrders` after Java has sorted it:

```spel
paidOrders.![id]
```

Defining a tie-breaker criterion such as `createdAt` then `id` makes the result order predictable when multiple elements share the same primary value.

## 6. First selection and last selection depend on source order

SpEL has selection operators to get the first or last matching element:

```spel
orders.^[status == 'PAID']
orders.$[status == 'PAID']
```

`.^[...]` finds the first matching element in source iteration order; `.$[...]` finds the last matching element in source iteration order. Therefore, "first" and "last" only have a stable meaning when the source collection has a stable order.

Example with a List:

```text
[A: PENDING, B: PAID, C: PAID, D: CANCELLED]
```

- `orders.^[status == 'PAID']` selects `B`.
- `orders.$[status == 'PAID']` selects `C`.

If the source is a `HashSet`, you should not use first/last as a business rule because iterator order is not guaranteed. Sort or convert the source into an ordered structure before using these operators.

## 7. Special notes when selecting or projecting on a Map

Map differs from a regular Iterable because each iterated element is an entry consisting of `key` and `value`, and selection and projection return different result types:

- Selection on a Map evaluates the condition on each `Map.Entry` and returns a Map containing the matching entries. Do not assume the result Map implementation preserves the source Map's order; if order matters, inspect and normalize the result in Java.
- Projection on a Map evaluates the expression on each entry and returns a List of projected values. This List follows the entry iteration order of the source Map.

Example:

```spel
officers.?[value.active == true]
officers.![key]
officers.![value.name]
officers.![key + ' -> ' + value.name]
```

Selection keeps matching key/value pairs in a Map result. Projection only creates a result List; keys are not preserved as a Map structure unless the expression includes the key in the projected value itself.

If you need to both filter a Map and produce an ordered list of labels from a Map source, you can project the entries directly or convert the entry set into an ordered List in Java before evaluation. If you need a Map with a specific order after selection, construct a `LinkedHashMap`/`TreeMap` as required in the Java layer.

## 8. Duplicates and nulls are not removed automatically

Selection and projection are not distinct operations:

- If a source List has two equal elements, selection can keep both.
- If two different elements project to the same value, projection keeps both results.
- If the projection expression returns null for an element, that corresponding result position still holds null.
- Selection only keeps/discards elements based on the condition result; it does not deduplicate kept elements.

Example:

```spel
members.![nationality]
```

If three members have nationalities `VN`, `VN`, `SG`, the result is `[VN, VN, SG]`, not automatically reduced to `[VN, SG]`. If you want deduplication, use `distinct()` in a Java Stream or a Set structure with appropriate semantics, while also determining the order to preserve.

## 9. New results and the source collection

Selection and projection create a result collection; they do not sort or modify the source collection. However, if the result contains object references from the source, those objects are not deep-copied.

Example:

```spel
orders.?[status == 'PAID']
orders.![#this]
```

Selection returns the matching orders; projection returns a List containing references to the orders. Modifying the structure of the result List does not alter the structure of the source List, but mutating the state of a referenced Order object still affects that object itself.

If an independent snapshot is needed, create copies or project into immutable DTOs/value objects in the application layer. Do not use projection returning `#this` as a deep copy.

## 10. Null-safe selection and projection

With Spring Framework 6.2 and later, you can use null-safe selection and projection when the source collection itself may be null:

```spel
orders?.?[status == 'PAID']
orders?.![id]
```

If `orders` is null, the corresponding null-safe result is null. If the collection exists, normal iteration order and selection/projection rules still apply.

Null-safe operators do not automatically handle every null property inside individual elements. If `status` or nested objects can be null, write safe sub-conditions/sub-expressions, for example:

```spel
orders?.?[#this?.customer?.active == true].![id]
```

If an empty collection is needed instead of null, you can use the Elvis operator:

```spel
(orders?.?[status == 'PAID']) ?: {}
```

In this example, `{}` is an inline empty list. Choose a clear null policy: null may mean "no data available", whereas an empty list means "evaluated and no elements found".

## 11. Reusing expressions and contexts

An Expression can be parsed once and evaluated across different root objects/contexts:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(
        "orders.?[status == #status].![id]");

StandardEvaluationContext context = new StandardEvaluationContext(customer);
context.setVariable("status", "PAID");

List<?> paidIds = expression.getValue(context, List.class);
```

The `#status` variable is read at evaluation time; result order still follows the iteration order of `orders`. If each request has a different filter status, provide a separate context for that request.

Do not share a mutable `EvaluationContext` across concurrent requests if requests can modify variables. Separating contexts per request prevents one request's filter value from overwriting another's.

## 12. Checklist for keeping the right order

Before using results in UI, reports, or business processing, verify:

1. Is the source an array, List, Set, or Map?
2. Is the iterator order of the source guaranteed?
3. Are you using selection `.?[]`, projection `.![...]`, first `.^[]`, or last `.$[]`?
4. When chaining selection/projection, must the encounter order of source elements be preserved?
5. Is sorting by a business criterion required after filtering?
6. For a Map source, must keys and Map order be preserved after selection?
7. Do duplicates or nulls need to be removed, or should the element count be kept as is?
8. Does the result need an independent snapshot or only a collection holding the original references?

## 13. Common errors and solutions

| Symptom | Cause to check | Solution |
| --- | --- | --- |
| Selection returns the right elements but in an unexpected order | Source is HashSet/HashMap or a collection without a committed iterator order. | Use a source with deterministic order or normalize/sort in Java before evaluation. |
| Projection produces non-ascending results | Projection only transforms; it does not sort. | Perform `sorted`/`List.sort` with an explicit comparator. |
| First/last selection varies across runs | Using `.^[]`/`.$[]` on a source without a stable order. | Supply a sorted List or a collection with deterministic order. |
| Map selection returns a structure not preserving expected order | Result Map is not guaranteed to keep the source Map's order. | Normalize the result into `LinkedHashMap`/`TreeMap` in Java if Map order is required. |
| Map projection loses keys | Projection returns a List of projected values. | Include `key` in the projection expression or build a new Map in Java. |
| Result still contains duplicates or nulls | Selection/projection does not auto-distinct or filter nulls from projection. | Use `distinct`, filter, or an explicit rule in Java/SpEL. |
| Result changes when source objects are updated | Projection may hold references to original objects. | Project into DTOs/value objects or create a snapshot when independence is required. |
| Null collection causes an error | Using normal selection/projection on null. | On Spring 6.2+, use `?.?[]` or `?.![]`; if an empty list is needed, combine with Elvis. |

## Key takeaways

- Selection `.?[]` filters elements; projection `.![...]` transforms each element; neither operator sorts automatically.
- For arrays and ordered Iterables, selection preserves the encounter order of selected elements; projection builds a List in source iteration order.
- List preserves element order; LinkedHashSet preserves insertion order; TreeSet uses a comparator; HashSet does not guarantee order.
- Map has its own ordering semantics; projection on a Map returns a List in source entry order, while selection returns a Map whose result order should not be assumed.
- `.^[]` and `.$[]` determine the first/last matching element in source iteration order.
- Projection retains duplicates and null results; deduplication/filtering must be stated as a separate step.
- SpEL has no dedicated collection sort operator; use a Java comparator/Stream or prepare a sorted collection.
- Selection/projection creates a result collection but does not deep-copy referenced objects.
- Spring Framework 6.2+ supports null-safe selection `?.?[]` and projection `?.![]` when the source collection is null.
- Use collections with deterministic order and separate contexts per request when results must be stable and reproducible.

## References

- [Spring Framework Reference — Collection Selection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html)
- [Spring Framework Reference — Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-projection.html)
- [Spring Framework Reference — Safe Navigation Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html)
- [Java API — List](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html)
- [Java API — LinkedHashSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashSet.html)
- [Java API — LinkedHashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html)