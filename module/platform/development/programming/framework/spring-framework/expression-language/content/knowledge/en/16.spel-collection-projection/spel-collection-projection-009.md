# Preserving result type and element order after projection in Spring Expression Language

Spring Expression Language (SpEL) supports projection to transform each element of a collection into a new value. The projection syntax is \`![...]\`. The inner expression is evaluated sequentially on each source element, and the resulting values are collected into a new result collection.

When using projection, it is important to understand two characteristics:

- **Result type:** projection creates a result list (List), without preserving the original collection type such as Set or Map.
- **Order:** values are produced in the iteration order of the source elements. For List and array, positional order is preserved; for Map or Set, order depends on the iteration rules of the implementation in use.

Understanding these two characteristics helps accurately predict data types, element positions, and behavior when results are passed to the next processing step.

## 1. What is projection?

Projection is the operation of mapping an expression across each element of a collection. General syntax:

~~~spel
collection.![expression]
~~~

The dot accesses an operation on the collection; the exclamation mark opens the projection; the part in square brackets is the expression evaluated on each element.

For example, if you have a list of names:

~~~spel
#names.![#this.toUpperCase()]
~~~

SpEL takes each name in turn, invokes \`toUpperCase()\`, and places the result into a new list.

If the source is:

~~~text
["ana", "minh", "linh"]
~~~

the result is:

~~~text
["ANA", "MINH", "LINH"]
~~~

Projection does not modify individual source elements merely because it creates a result collection. However, if the expression inside projection invokes a method with side effects or performs an assignment, those operations can still mutate referenced objects.

## 2. Distinguishing Projection and Selection

The two operations look similar in form but have different goals:

| Operation | Syntax | Purpose | Result |
|---|---|---|---|
| Selection | \`?[condition]\` | Keep elements matching a condition | Sub-collection |
| Projection | \`![expression]\` | Transform each element into a new value | Result list |

Example with a list of numbers:

~~~spel
#numbers.?[#this > 2]
#numbers.![#this * 10]
~~~

If the source is \`[1, 2, 3, 4]\`:

- Selection returns the elements matching the condition: \`[3, 4]\`.
- Projection computes the expression for each element: \`[10, 20, 30, 40]\`.

Selection can reduce the number of elements because it filters. Regular projection produces one result per input element, even if two elements produce the same value.

## 3. Result type of Projection

Projection creates a new result list. This means the source collection type is not preserved.

| Source type | Projection result |
|---|---|
| List | List containing projected values |
| Set / Iterable | List containing projected values |
| Array | List containing projected values |
| Map | List containing evaluation results on each entry |

For example, projecting on a Set does not return a Set just because the source is a Set. The result is a List, so two distinct source elements can produce two equal values and both still appear in the result.

Similarly, projection on a Map does not return a Map preserving the keys. The result is a List of values produced by the projection expression. If you want to retain keys, include the key in the projection expression itself or build the desired map structure with appropriate logic.

In Java, receive the result as a List when you know the expression uses projection:

~~~java
Object value = expression.getValue(context);

if (value instanceof List<?> projected) {
    // Process the result list.
}
~~~

The concrete element type depends on the projection expression and runtime data. The \`getValue()\` API returns Object, so Java code can check or convert the result according to the application's contract.

## 4. Projection on List preserves element order

A List has a deterministic iteration order. Projection evaluates elements in that order and places corresponding results at the same positions in the new list.

Example:

~~~java
List<String> names =
    Arrays.asList("ana", "minh", "linh");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("names", names);

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#names.![#this.toUpperCase()]");

List<?> result = (List<?>) expression.getValue(context);
System.out.println(result);
~~~

Result:

~~~text
[ANA, MINH, LINH]
~~~

Positional mapping:

| Source index | Source value | Value after projection |
|---:|---|---|
| 0 | ana | ANA |
| 1 | minh | MINH |
| 2 | linh | LINH |

The element at index 0 of the source produces the element at index 0 of the result; this rule continues for subsequent positions.

If the projection expression produces duplicate values, duplicates are still kept:

~~~spel
#numbers.![#this % 2]
~~~

With source \`[1, 3, 2, 4]\`, the result is \`[1, 1, 0, 0]\`. Projection does not automatically deduplicate elements.

## 5. Projection on Array

SpEL also supports projection on arrays. The result is still a List and order is preserved according to array index order.

Example:

~~~java
Integer[] scores = {80, 95, 70};

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("scores", scores);

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#scores.![#this + 5]");

List<?> adjusted =
    (List<?>) expression.getValue(context);
~~~

Result:

~~~text
[85, 100, 75]
~~~

Elements are processed at indices 0, 1, 2. The result is not a new Integer array, but a List containing the projected values.

If the application needs an array as output, you can convert the resulting List to an array in Java after evaluation.

## 6. Projection on Set and other Iterables

Projection works on Iterable objects. For a Set, result order follows the order the Set provides when iterated.

This has different implications depending on the implementation:

- LinkedHashSet preserves insertion order, so projection follows insertion order.
- TreeSet iterates in the order defined by the comparator or natural ordering.
- HashSet does not guarantee a stable iteration order; do not rely on fixed result positions across runs.

Example:

~~~java
Set<String> tags = new LinkedHashSet<>();
tags.add("backend");
tags.add("java");
tags.add("spring");

context.setVariable("tags", tags);

Expression expression =
    parser.parseExpression("#tags.![#this.toUpperCase()]");

List<?> result =
    (List<?>) expression.getValue(context);
~~~

Result in LinkedHashSet iteration order:

~~~text
[BACKEND, JAVA, SPRING]
~~~

The source is a Set, yet the result is a List. If business ordering matters, choose a source implementation with a well-defined order or sort the data before projection.

## 7. Projection on Map: result is a List of entry projections

With a Map, SpEL evaluates the projection expression on each entry. The current object on each pass is a \`Map.Entry\`, so you can access \`key\` and \`value\`.

Example:

~~~java
Map<String, Integer> prices = new LinkedHashMap<>();
prices.put("keyboard", 750);
prices.put("mouse", 250);
prices.put("monitor", 3000);

context.setVariable("prices", prices);
~~~

Retrieve list of keys:

~~~spel
#prices.![key]
~~~

Result:

~~~text
[keyboard, mouse, monitor]
~~~

Retrieve list of values:

~~~spel
#prices.![value]
~~~

Result:

~~~text
[750, 250, 3000]
~~~

Compute price after a 10 percent increase:

~~~spel
#prices.![value * 1.10]
~~~

The result is a List of values computed from each entry.

Because projection on a Map returns a List, keys are not automatically preserved in the result. If both key and value are needed, the expression can create an intermediate object containing both parts, or the application can process entries in Java to build the target Map.

## 8. Projection order on Map depends on iteration order

Projection on a Map iterates entries in the order provided by the Map's \`entrySet()\`. SpEL preserves that iteration order in the resulting List.

| Map implementation | Typical iteration order | Order in projection List |
|---|---|---|
| LinkedHashMap | Insertion order | Follows insertion order |
| TreeMap | Key order by comparator | Follows key order |
| HashMap | Not guaranteed stable | Follows iteration order of that traversal |

Example:

~~~java
Map<String, Integer> values = new LinkedHashMap<>();
values.put("first", 10);
values.put("second", 20);
values.put("third", 30);

context.setVariable("values", values);

Expression expression =
    parser.parseExpression("#values.![value * 2]");

List<?> result =
    (List<?>) expression.getValue(context);
~~~

Result:

~~~text
[20, 40, 60]
~~~

If LinkedHashMap is changed to HashMap, do not assume the order will always be \`[20, 40, 60]\` matching insertion order. Values are still projected per entry, but order depends on the implementation's iteration order.

When result order is part of the business contract, choose a Map type with deterministic ordering.

## 9. Projection produces one result per element

Regular projection does not filter elements. Each input element is used to evaluate the projection expression and produce one output element.

Example:

~~~spel
#names.![#this.length()]
~~~

With source \`["Ana", "Minh", "Linh"]\`, the result is \`[3, 4, 4]\`.

Characteristics to remember:

- The number of result elements usually equals the number of source elements.
- Two different inputs can produce the same output value; both results are still kept.
- If the projection expression returns null for an element, the corresponding position in the result List may contain null.
- Projection does not automatically flatten nested collections.

Example of projection returning collections:

~~~spel
#groups.![members]
~~~

Each output element can be a members collection. The result is then a List containing child collections, not a single flattened collection.

If elements need to be excluded by a condition, use selection or combine appropriate operations.

## 10. Null values in projection

Distinguish a null source collection, a null source element, and a null projection value.

### Null source collection

Regular projection on a null collection cannot iterate elements. Starting in Spring Framework 6.2, you can use null-safe projection:

~~~spel
#products?.![name]
~~~

If products is null, the expression returns null. The null-safe projection syntax is \`?.![]\`, distinct from the null-safe indexer \`?.[]\` and null-safe selection \`?.?[]\`.

### Null source element

Null-safe projection does not automatically protect individual elements. If a collection contains null and the expression accesses a property directly, evaluation can fail.

You can use null-safe navigation inside the sub-expression:

~~~spel
#products.![#this?.name]
~~~

When the current element is null, the sub-expression returns null; that position is preserved in the result list.

### Projection expression returning null

If an element exists but the projected property has a null value, projection can still include null in the result. Projection does not automatically remove these null values.

## 11. Distinguishing projection from selection and sorting operations

Projection and selection both create result collections, but serve different purposes:

| Operation | Syntax | Behavior | Number of elements |
|---|---|---|---|
| Projection | \`![expression]\` | Transforms each element | One result per iterated element |
| Selection | \`?[condition]\` | Keeps elements matching condition | May be fewer than source |
| First selection | \`^[condition]\` | Gets first matching element | At most one |
| Last selection | \`$[condition]\` | Gets last matching element | At most one |

Projection is not a sorting operation. It preserves the source's iteration order, without sorting by the new values.

If sorting is needed, perform the appropriate sort operation in Java or supply an already-ordered collection before projection.

## 12. Result type and receiving it in Java

Projection creates a new List, regardless of whether the source is a List, Set, array, or Map. The element type in the List depends on the projection expression.

Example:

~~~java
Expression expression =
    parser.parseExpression("#products.![name]");

Object value = expression.getValue(context);

if (value instanceof List<?> names) {
    for (Object name : names) {
        System.out.println(name);
    }
}
~~~

If the expected result type is known, you can declare the type in Java code after verifying the data contract. Java generics are not automatically guaranteed by SpEL from expression syntax alone; general \`getValue()\` returns Object.

For a projection expression on a Map, do not cast the result to Map just because the source is a Map. The projection result is a List of values produced from entries.

## 13. Complete example: preserving order and result type

Suppose the application has Products and wants to generate a list of labels in the original order:

~~~java
public class Product {
    private final String name;
    private final BigDecimal price;

    public Product(String name, BigDecimal price) {
        this.name = name;
        this.price = price;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
~~~

Prepare the data:

~~~java
List<Product> products = Arrays.asList(
    new Product("Keyboard", new BigDecimal("750000")),
    new Product("Mouse", new BigDecimal("250000")),
    new Product("Monitor", new BigDecimal("3000000"))
);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("products", products);
~~~

Projection:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "#products.![name + ' - ' + price]"
);

List<?> labels =
    (List<?>) expression.getValue(context);
~~~

Result in exact source order:

~~~text
[
  "Keyboard - 750000",
  "Mouse - 250000",
  "Monitor - 3000000"
]
~~~

Since the source is a List, element order is preserved by index. The result is a new List containing Strings, while the source Products remain the original objects.

## 14. Common misconceptions

**Misconception 1: Projection preserves the source collection type.**  
Projection creates a new List. A Set, array, or Map does not cause the result to automatically take the same source type.

**Misconception 2: Projection automatically sorts results.**  
Projection preserves source iteration order. If sorting is required, it must be done separately.

**Misconception 3: Projection removes duplicate or null values.**  
Projection does not automatically remove them. Each source element produces a corresponding result; null results and duplicate values can be retained.

**Misconception 4: Projection on a Map returns a Map.**  
Projection on a Map evaluates each Map.Entry and produces a result List. Keys are preserved only if the expression projects the key or a structure containing the key.

**Misconception 5: Null-safe projection also protects null elements.**  
Null-safe projection protects the source collection when the collection itself is null. Null elements must be handled inside the sub-expression.

## 15. Key takeaways

- Projection uses the syntax \`collection.![expression]\` to transform each element.
- Projection on List, Set, Iterable, array, or Map creates a result List.
- For List and array, source order is preserved; for Map and Set, result order follows the implementation's iteration order.
- Projection creates one result per iterated element or entry; duplicates and nulls are not automatically removed.
- Projection does not automatically flatten nested collections and does not sort results.
- For Map, the projection expression is evaluated on each entry; key and value can be accessed.
- Null-safe projection uses \`?.![]\` starting in Spring Framework 6.2, while null-safe selection uses \`?.?[]\`.
- Distinguish a null collection, a null element, and a null projection value.
- When receiving results in Java, remember \`getValue()\` returns Object and projection creates a List.

When designing a projection, identify the source type, iteration order, expression producing each element's value, and the List type that Java code will receive. That keeps results predictable and avoids wrong assumptions about data type or order.
