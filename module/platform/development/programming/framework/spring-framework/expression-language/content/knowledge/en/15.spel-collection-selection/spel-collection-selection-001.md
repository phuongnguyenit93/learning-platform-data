# Collection Selection .?[selectionExpression] in SpEL

## 1. What is collection selection?

Spring Expression Language (SpEL) provides collection selection to filter a collection based on a condition. Selection iterates over the elements of the source, evaluates a Boolean expression for each element, and returns a new collection containing only the elements that satisfy the condition.

Basic syntax:

```text
source.?[selectionExpression]
```

For example, getting members with Serbian nationality:

```java
List<?> serbianMembers = parser.parseExpression(
        "members.?[nationality == 'Serbian']")
        .getValue(context, List.class);
```

In this example:

- `members` is the source collection.
- `nationality == 'Serbian'` is the selection expression.
- SpEL evaluates the condition on each member.
- Only members for whom the condition is true appear in the result.

Selection does not modify the source collection. It creates a separate filtered result, so the result can be used for display, calculation, or further processing.

## 2. Forms of selection

SpEL supports three selection variants:

| Syntax | Meaning | Result |
|---|---|---|
| `.?[selectionExpression]` | Get all matching elements. | A collection containing every selected element. |
| ".^[selectionExpression]" | Get the first matching element. | A single element, or null if there is no result. |
| ".$[selectionExpression]" | Get the last matching element. | A single element, or null if there is no result. |

Example with a list of numbers:

```java
List<Integer> numbers = List.of(2, 5, 8, 11, 14);
context.setVariable("numbers", numbers);

List<?> allEven = parser.parseExpression(
        "#numbers.?[#this % 2 == 0]")
        .getValue(context, List.class);
// [8, 14]

Integer firstEven = parser.parseExpression(
        "#numbers.^[#this % 2 == 0]")
        .getValue(context, Integer.class);
// 8

Integer lastEven = parser.parseExpression(
        "#numbers.$[#this % 2 == 0]")
        .getValue(context, Integer.class);
// 14
```

The all-match form is suitable when you need to process all results. The first-match and last-match forms are suitable when you only need one element according to the iteration order of the source.

## 3. Selection expression and the current element

The selection expression is evaluated individually on each element. During that process, the element being examined becomes the active context object. Therefore, you can access properties of the element directly:

```text
members.?[nationality == 'Serbian']
```

The system variable `#this` references the current element. Writing `#this` explicitly makes the expression easier to read when there are multiple object levels or multiple variables:

```text
members.?[#this.nationality == 'Serbian']
```

With a Society instance as the root object, `#root` still references the original Society, while `#this` inside the predicate references each member:

```text
members.?[#this.nationality == #root.preferredNationality]
```

The selection expression needs to return a Boolean. Comparison and logical operators are commonly used to build the condition:

```text
orders.?[status == 'PAID' and total >= 100000]
```

The condition can access properties, call methods, or combine multiple SpEL expressions. Make sure those properties and methods are accessible on the element type.

## 4. Selection on List, array, and Iterable

Selection is supported on:

- Java arrays.
- Types implementing `java.lang.Iterable`, including List and Set.
- Java Maps.

For an array or Iterable, the predicate is evaluated on each individual element. The all-match result is a collection containing the selected source elements.

Example with a List of Products:

```java
public class Product {
    private String code;
    private BigDecimal price;
    private boolean active;

    public String getCode() {
        return code;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public boolean isActive() {
        return active;
    }
}

List<Product> products = loadProducts();
context.setVariable("products", products);

List<?> activeProducts = parser.parseExpression(
        "#products.?[active]")
        .getValue(context, List.class);

List<?> affordableProducts = parser.parseExpression(
        "#products.?[active and price <= 500]")
        .getValue(context, List.class);
```

The predicate `active` reads the Boolean property of each Product. The second predicate combines the active status and price limit.

With an array, the syntax is similar:

```java
int[] values = {3, 6, 9, 12, 15};
context.setVariable("values", values);

List<?> multiplesOfThree = parser.parseExpression(
        "#values.?[#this % 3 == 0]")
        .getValue(context, List.class);
```

Although the source is an array, the selection result is a collection of the selected elements. If a Java API requires an array, convert the result explicitly.

## 5. Selecting the first and last matching element

Use `.^[...]` when you need the first element that satisfies the condition and `.$[...]` when you need the last element that satisfies the condition.

Example of getting the first order with PAID status:

```java
Order firstPaid = parser.parseExpression(
        "orders.^[status == 'PAID']")
        .getValue(context, Order.class);
```

Getting the last PAID order in iteration order:

```java
Order lastPaid = parser.parseExpression(
        "orders.$[status == 'PAID']")
        .getValue(context, Order.class);
```

If no element matches, the first/last form has no element to return and the result is null. Therefore, check for null before accessing subsequent properties:

```text
orders.^[status == 'PAID']?.orderNumber
```

First and last depend on the iteration order of the source. For a List and an array, element order is deterministic. For a Set or Map that does not guarantee encounter order, you should not assume the first/last element is stable across runs. If order matters, use a collection with deterministic order or sort the data before selection.

## 6. Selection on Map

When the source is a Map, SpEL evaluates the selection expression on each entry of type `java.util.Map.Entry`, not directly on the value. Each entry has two properties:

- `key`: the key of the entry.
- `value`: the value of the entry.

The all-match form preserves the matching key/value pairs and returns a new Map.

Example:

```java
Map<String, Integer> inventory = Map.of(
        "PEN", 12,
        "BOOK", 45,
        "BAG", 8,
        "LAMP", 30);

context.setVariable("inventory", inventory);

Map<?, ?> lowStock = parser.parseExpression(
        "#inventory.?[value < 20]")
        .getValue(context, Map.class);
// {PEN=12, BAG=8}
```

You can check both key and value:

```text
#inventory.?[key.startsWith('B') and value < 50]
```

For example, getting entries whose key starts with the letter B and whose quantity is less than 50.

With a Map, do not write the predicate as if `#this` were a plain value. `#this` represents a Map.Entry; access `key` or `value`:

```text
#inventory.?[#this.value >= 30]
```

The all-match form preserves the keys of the selected entries. When you only need a single result with first/last selection on a Map, verify the type and meaning of the return value in the specific expression because the predicate is operating on Map.Entry.

## 7. Null-safe collection selection

If the source collection may be null, standard selection can fail when SpEL attempts to process a nonexistent collection. SpEL supports null-safe selection using these operators:

| Syntax | Meaning |
|---|---|
| `?.?[selectionExpression]` | All-match selection that is safe when the source is null. |
| `?.^[selectionExpression]` | First-match selection that is safe when the source is null. |
| `?.$[selectionExpression]` | Last-match selection that is safe when the source is null. |

Example:

```java
String expression =
        "members?.?[nationality == 'Serbian']";

List<?> selected = parser.parseExpression(expression)
        .getValue(context, List.class);
```

If `members` is null, null-safe selection returns null instead of attempting to iterate over the collection. If `members` is an empty collection, the result is an empty collection. These two situations are different:

| Source | Standard selection | Null-safe selection |
|---|---|---|
| Collection with elements | Filters by predicate. | Filters by predicate. |
| Empty collection | Empty result collection. | Empty result collection. |
| Null source | May raise an error when operating on null. | Returns null. |

Null-safe selection only guards when the source collection itself is null. It does not automatically guard properties inside each element. If an element can be null, you need to check or use safe navigation inside the predicate:

```text
members?.?[#this?.nationality == 'Serbian']
```

If you still access a property of a first-match result after selection, continue using safe navigation:

```text
members?.^[nationality == 'Serbian']?.name
```

The safe navigation operator must be applied at each segment that can receive null in a compound expression. Safe navigation on the collection does not automatically make the entire subsequent access chain safe.

## 8. How does Selection differ from Projection?

Selection and projection both iterate over collections, but their purposes differ:

| Feature | Syntax | Result |
|---|---|---|
| Selection | `.?[predicate]` | Retains source elements that satisfy the condition. |
| Projection | `.![expression]` | Creates result elements from an expression applied to each source element. |

For example, selection keeps active Products:

```text
products.?[active]
```

Projection gets the code of all Products:

```text
products.![code]
```

You can combine selection first, then projection:

```text
products.?[active].![code]
```

The result is a list of codes of active Products. Selection decides which elements are kept; projection decides what value is produced from those elements.

If you want to take only one element and transform it, you can combine first/last selection with property access:

```text
products.^[active and price < 100]?.code
```

## 9. Testing examples with Java and JUnit

A good test should verify cases with multiple matching elements, no matching elements, first/last, and an empty collection.

Example with a list of numbers:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

class CollectionSelectionTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    @Test
    void selectsAllMatchingValues() {
        var context = new StandardEvaluationContext();
        context.setVariable("numbers", List.of(2, 5, 8, 11, 14));

        List<?> result = parser.parseExpression(
                "#numbers.?[#this % 2 == 0]")
                .getValue(context, List.class);

        assertEquals(List.of(2, 8, 14), result);
    }

    @Test
    void selectsFirstAndLastMatchingValues() {
        var context = new StandardEvaluationContext();
        context.setVariable("numbers", List.of(2, 5, 8, 11, 14));

        Integer first = parser.parseExpression(
                "#numbers.^[#this > 5]")
                .getValue(context, Integer.class);

        Integer last = parser.parseExpression(
                "#numbers.$[#this > 5]")
                .getValue(context, Integer.class);

        assertEquals(8, first);
        assertEquals(14, last);
    }

    @Test
    void returnsEmptyCollectionWhenNoElementMatches() {
        var context = new StandardEvaluationContext();
        context.setVariable("numbers", List.of(2, 4, 6));

        List<?> result = parser.parseExpression(
                "#numbers.?[#this > 10]")
                .getValue(context, List.class);

        assertTrue(result.isEmpty());
    }
}
```

With a Map, you should verify both the remaining entry count and the keys/values:

```java
@Test
void selectsMapEntriesByValue() {
    var context = new StandardEvaluationContext();
    context.setVariable("inventory", Map.of(
            "PEN", 12,
            "BOOK", 45,
            "BAG", 8));

    Map<?, ?> result = parser.parseExpression(
            "#inventory.?[value < 20]")
            .getValue(context, Map.class);

    assertEquals(2, result.size());
    assertEquals(12, result.get("PEN"));
    assertEquals(8, result.get("BAG"));
}
```

Null-safe selection should have separate tests for a null source and an empty source to ensure the caller understands the two different outcomes correctly.

## 10. Common mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| Selection does not filter | Predicate does not return Boolean or property name is wrong. | Test the predicate on a single element. |
| Result is a List when a Map was expected | Source is not a Map or selection is running on an Iterable. | Check the source type before selecting. |
| Map predicate cannot find key | Accessing the entry incorrectly; Map predicates use `key` and `value`. | Use `key`, `value`, or `#this.key`, `#this.value`. |
| First/last returns null | No element matches. | Check the condition and handle null before further access. |
| First/last is unstable | Source has no deterministic iteration order. | Use a List/array or a collection with a clear order. |
| Selection on a null source raises an error | Using `.?[]` with a potentially null collection. | Use null-safe selection `?.?[]`. |
| Null element causes an error in the predicate | Collection contains null elements and the predicate accesses properties directly. | Filter out null or use safe navigation on `#this`. |
| Does selection lose source data? | Confusing the filtered result with an in-place collection mutation. | Selection creates a result collection; if the source needs to be updated, do it separately in Java. |
| Confusing selection with projection | Using a predicate while expecting a transformed value. | Use `.![...]` for projection. |
| Map result is not as expected | Predicate runs on Map.Entry, not on the plain value. | Check both `key` and `value` in the condition. |

## 11. Workflow for designing and testing selection

1. Identify whether the source type is an array, Iterable, or Map.
2. Decide whether you want all matching elements, the first element, or the last element.
3. Write a simple Boolean predicate for a single element first, then apply it to the collection.
4. Use `#this` when you need to specify the current element clearly; with a Map, use `key` and `value`.
5. Test an empty source, no matching results, and a null source.
6. If order matters, confirm that the source collection has a stable iteration order.
7. If elements can be null, guard the properties read in the predicate.
8. Use projection separately if you need to transform elements after filtering.
9. Test the result and return type with the same EvaluationContext and root object as the application environment.

## 12. Key takeaways

- `.?[predicate]` gets all matching elements; ".^[predicate]" gets the first element; ".$[predicate]" gets the last element.
- Selection supports arrays, Iterables, and Maps.
- For arrays/Iterables, the predicate is evaluated on each element; for Maps, the predicate is evaluated on Map.Entry.
- Map entries provide `key` and `value` properties; all-match selection returns a Map containing the matching entries.
- `#this` references the element or entry currently being evaluated; `#root` still references the original root object.
- The predicate must produce a Boolean.
- First/last depend on iteration order; avoid relying on the unguaranteed order of Set/Map.
- Null-safe selection uses `?.?`, `?.^`, and `?.$`; a null source returns null, while an empty source returns an empty collection.
- Selection preserves source elements; projection `.![...]` creates new values from each element.
- Test null sources, empty sources, no matches, multiple matches, and null elements if the data model allows them.

## References

- [Spring Framework Reference — Collection Selection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html)
- [Spring Framework Reference — Safe Navigation and Safe Collection Selection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html)
- [Spring Framework Reference — Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-projection.html)
- [Selection AST Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/ast/Selection.html)
