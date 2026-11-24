# Map projection and result shape

In Spring Expression Language (SpEL), **projection** uses the **.![]** operator to apply an expression to each element of a collection and collect the generated values. When projection runs on a **Map**, SpEL evaluates the projection expression on each entry of the Map. Each entry provides two important components: **key** and **value**.

The key point to remember is that the result of projection on a Map has the shape of a **List** of values computed from each entry. Projection does not create a new Map and does not automatically retain the original keys. If you need a new Map with transformed keys and values, the application must construct that Map in Java or use an appropriate data transformation mechanism.

## Syntax of projection on Map

General syntax:

~~~text
map.![projectionExpression]
~~~

SpEL iterates over the entries of the Map. For each entry, it evaluates **projectionExpression** in the context of the current entry and appends the result to a List.

In a predicate or projection on a Map, **#this** refers to the current **Map.Entry**. You can access:

- **#this.key**: key of the current entry.
- **#this.value**: value of the current entry.

For example, retrieving all values of a Map:

~~~java
Map<String, Integer> inventory = new LinkedHashMap<>();
inventory.put("keyboard", 12);
inventory.put("monitor", 3);
inventory.put("mouse", 25);

StandardEvaluationContext context =
        new StandardEvaluationContext();
context.setVariable("inventory", inventory);

ExpressionParser parser = new SpelExpressionParser();
Expression expression =
        parser.parseExpression("#inventory.![#this.value]");

List<?> quantities =
        expression.getValue(context, List.class);
~~~

The result is a List containing the numbers **12, 3, 25** in the Map's entry iteration order. Each time projection evaluates, #this is respectively the keyboard, monitor, and mouse entry.

Because the result is a List, the return type here is **List<?>**, not Map<String, Integer>. The original keys are not retained in the result structure.

## Retrieving keys from each entry

If the projection expression returns **#this.key**, the result is a list of keys:

~~~java
Expression expression =
        parser.parseExpression("#inventory.![#this.key]");

List<?> keys =
        expression.getValue(context, List.class);
~~~

With the Map above, the result is the list **keyboard**, **monitor**, **mouse**. This is one way to produce a list of keys in the Map's current iteration order.

You can write it more concisely using the **key** property in the entry context:

~~~text
#inventory.![key]
~~~

However, writing **#this.key** makes it explicit that the key property belongs to the entry currently being processed by projection. This explicit style is especially helpful when expressions have multiple levels or when reading both key and value together.

## Projecting value to another property

A more common case is a Map containing objects. Projection can extract a property from each entry's value.

Suppose a Map maps SKU codes to Products:

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

~~~java
Map<String, Product> productsBySku = new LinkedHashMap<>();
productsBySku.put(
        "KB-01",
        new Product("Keyboard", new BigDecimal("80.00")));
productsBySku.put(
        "MN-02",
        new Product("Monitor", new BigDecimal("250.00")));
productsBySku.put(
        "MS-03",
        new Product("Mouse", new BigDecimal("25.00")));

StandardEvaluationContext context =
        new StandardEvaluationContext();
context.setVariable("productsBySku", productsBySku);

ExpressionParser parser = new SpelExpressionParser();
Expression expression =
        parser.parseExpression(
                "#productsBySku.![#this.value.name]");

List<?> productNames =
        expression.getValue(context, List.class);
~~~

The result is a List containing **Keyboard**, **Monitor**, **Mouse**. Each projection step takes the current entry, accesses value to get the Product, and then reads that Product's name property.

You can project the price:

~~~text
#productsBySku.![#this.value.price]
~~~

The result is a List of BigDecimal values. The element type of the List depends on the result type of the projection expression.

## Combining key and value into a new value

A projection expression can compute or combine entry data. For example, building a descriptive string from SKU and product name:

~~~java
Expression expression = parser.parseExpression(
        "#productsBySku.![#this.key + ': ' + #this.value.name]");

List<?> descriptions =
        expression.getValue(context, List.class);
~~~

The result has the form:

~~~text
[
  "KB-01: Keyboard",
  "MN-02: Monitor",
  "MS-03: Mouse"
]
~~~

Each entry produces a new String. The resulting List contains those Strings, while the original Map keeps its keys and values intact.

Similarly, you can produce a list of post-tax prices, display labels, or an aggregated value from each entry. However, if the transformation requires multiple steps, service calls, or complex error handling, move that logic to Java so the expression does not become hard to read.

## Result shape: List instead of Map

This is the most important point when using projection on a Map:

| Projection expression | Result shape type | Contents |
|---|---|---|
| **#map.![#this.key]** | List | List of keys |
| **#map.![#this.value]** | List | List of values |
| **#map.![#this.value.name]** | List | List of names extracted from values |
| **#map.![#this.key + ':' + #this.value]** | List | List of strings combining key and value |

Even when the input Map has type **Map<K, V>**, the projection result is still a List of computed values. Projection does not automatically build new key-value pairs and does not guarantee each result can be mapped back to its original key if the expression does not include the key in the result.

If you need to preserve the link between key and transformed value, you can project a result object containing both fields, or process the Map in Java:

~~~java
Map<String, String> namesBySku = new LinkedHashMap<>();

productsBySku.forEach((sku, product) ->
        namesBySku.put(sku, product.getName()));
~~~

This preserves the SKU keys and creates a new Map mapping SKUs to product names. It clearly expresses the desired data shape that Map projection does not provide directly.

## Element order in the resulting List

Projection preserves the entry iteration order of the input Map. Therefore, the order of the resulting List depends on the implementation and state of the Map:

- **LinkedHashMap** normally maintains insertion order, so the projected List follows that order.
- **TreeMap** iterates over entries in sorted key order, so the result List follows that order.
- **HashMap** does not guarantee a stable iteration order; do not rely on a specific order in the projected List.

If order is a business requirement, choose a Map with appropriate ordering or sort the data before evaluating the expression. Do not write tests that depend on the accidental order of a HashMap.

Example with LinkedHashMap:

~~~java
Map<String, Integer> values = new LinkedHashMap<>();
values.put("first", 10);
values.put("second", 20);
values.put("third", 30);

context.setVariable("values", values);

List<?> result =
        parser.parseExpression("#values.![#this.value]")
                .getValue(context, List.class);
~~~

The resulting List has the order **10, 20, 30**, matching the entry order of the LinkedHashMap.

## Projection on an empty Map

If the input Map is empty, there are no entries on which to evaluate the projection expression. The result is an empty List:

~~~java
context.setVariable("emptyMap", Collections.emptyMap());

List<?> result =
        parser.parseExpression("#emptyMap.![#this.value]")
                .getValue(context, List.class);
~~~

The result contains no elements. This differs from the case where the Map is null. When the input object is null, there is no Map to iterate over and evaluation can fail if regular projection is used.

If the Map can be null, decide the handling policy before evaluation: check for null in Java, supply an empty Map fallback when appropriate, or use the null-safe mechanism supported by your Spring version. Do not treat null and an empty Map as the same state if business logic must distinguish them.

## Null values inside a Map

A Map can contain an entry whose value is null. When projection accesses **#this.value** directly, the corresponding result may be null. However, if the expression continues to access a property of value, such as **#this.value.name**, accessing a property on null can cause an evaluation error.

For example, if there is an entry with a null value:

~~~text
#productsBySku.![#this.value.name]
~~~

The expression cannot read the name property from a null value. If the data allows nulls, check value before traversing deeper:

~~~text
#productsBySku.![#this.value == null ? 'Unknown' : #this.value.name]
~~~

The expression above produces a List of display names; an entry with a null value yields the string **Unknown**. This is a fallback policy explicitly expressed in the expression. Only use a default value if it matches business rules.

If you need to skip entries with null values instead of generating a default label, you can apply selection on the Map first and then project the result:

~~~text
#productsBySku.?[#this.value != null].![#this.value.name]
~~~

Selection retains matching entries; subsequent projection extracts name from value. The final result is still a List.

## Distinguishing selection and projection on Map

Selection and projection can both use #this, yet they produce different result shapes:

- **Selection .?[condition]** filters Map entries and keeps those matching the condition. The result is a Map containing the selected key-value pairs.
- **Projection .![expression]** evaluates the expression on each entry and collects the results into a List.

For example, keeping only products with a price of at least 50:

~~~text
#productsBySku.?[#this.value.price >= 50]
~~~

The result is a Map that keeps SKUs as keys and Products as values.

If you want the names of products priced at least 50:

~~~text
#productsBySku.?[#this.value.price >= 50].![#this.value.name]
~~~

The result is a List of product names. After selection, the Map retains the matching entries; projection turns those entries into name values.

If you want the SKUs of active products:

~~~text
#productsBySku.?[#this.value.active].![#this.key]
~~~

The result is a List of keys of the selected entries. Remember that selection and projection are two steps: the first filters the Map, and the second builds a List.

## #this in Map projection

In Map projection, **#this** represents the current entry. This differs from List projection, where #this is the current List element.

For Map<String, Product>:

- **#this.key** is the SKU String.
- **#this.value** is the Product.
- **#this.value.name** is the Product's name.
- **#root** remains the initial root object of the evaluation.

If the expression is evaluated with a root object of Catalog having a productsBySku property, you can write:

~~~text
productsBySku.![#this.key + ':' + #this.value.name]
~~~

Here the root object is Catalog, while #this inside projection is each Map.Entry. If you need to access a property of Catalog inside projection, use #root to reference the initial object explicitly.

## EvaluationContext and property access permissions

For projection to read key, value, and nested properties, EvaluationContext must provide the corresponding access mechanisms. **StandardEvaluationContext** supports broad property access and method invocation. **SimpleEvaluationContext** may fit when only data binding with a restricted capability set is needed, though instance method invocation is not enabled by default in the standard read-only builder.

For example, **#this.value.name** mainly needs property reading. If a projection expression invokes a method like **#this.value.name.toUpperCase()**, the context must permit instance method invocation. Enable this capability only when the use case requires it.

If the Map or values have a complex structure, custom property accessors can be used to expose the necessary data. When expressions come from external sources, restrict the root object, accessors, and variables provided rather than exposing the entire application.

## Common errors

- **Expecting projection to return a Map:** projection on a Map creates a List of computed values and does not retain original keys.
- **Confusing key and value:** Map.Entry has two parts; use #this.key for the key and #this.value for the value.
- **Forgetting Map iteration order:** the resulting List follows the Map's iteration order, which is not always insertion order or sorted order.
- **Accessing a property on a null value:** check for null or apply a fallback policy.
- **Confusing selection with projection:** selection retains matching entries and returns a Map; projection creates a List of values.
- **Calling a method unsupported by the context:** invoking methods on values requires an EvaluationContext that allows instance method invocation.
- **Not handling null or empty Maps:** an empty Map yields an empty List; a null Map requires a separate handling policy.

An expression string may parse successfully yet fail during evaluation if a property does not exist, a value is null, or the context does not support the requested operation. Separate parse errors from evaluation errors when handling exceptions, and log the expression identifier and necessary context for diagnosis.

## When to use projection on Map?

Projection on a Map fits when you need to build a list of values from entries, such as:

- Retrieving all keys or all values.
- Extracting a property from objects stored as values.
- Creating display labels combining key and value.
- Filtering a Map first and then projecting the remaining entries into a List.
- Writing a short expression at a Spring integration point that supports SpEL.

If you need to preserve keys, create a new Map, perform complex sorting, grouping, or multi-step processing, use Java Streams or explicit loops. Java constructs generally express intent better when the output shape must be controlled precisely.

## Conclusion

Projection on a Map uses the syntax **map.![projectionExpression]**. In each step, **#this** is the current Map.Entry; you can read the key via **#this.key** and the value via **#this.value**. SpEL evaluates the expression on each entry and collects the values into a **List**, so the original keys are not automatically preserved.

The order of the List depends on the Map's iteration order. If you need to keep key-value pairs, project an object holding both or build a new Map in Java. Distinguishing projection from selection, handling null values, and choosing a Map with appropriate ordering will make result shapes predictable and easy to maintain.
