# Selection on lists, maps, and different collections

Spring Expression Language (SpEL) provides the selection operator to filter elements of a collection according to a condition. Instead of fetching all data and filtering in Java, an expression can directly select the elements that satisfy a predicate.

Selection has three main forms:

- **.?[condition]**: gets all elements satisfying the condition.
- **.^[condition]**: gets the first element satisfying the condition.
- **.$[condition]**: gets the last element satisfying the condition.

How the predicate is written depends on the structure of the data source. For lists and collections containing objects, the condition is evaluated on each element. For maps, the condition is evaluated on each entry and can access both key and value. Understanding this difference avoids writing incorrect predicates or assuming the wrong result type.

## 1. How does selection work?

### 1.1. Filtering all elements

The general selection operator has the syntax:

~~~java
collection.?[selectionExpression]
~~~

SpEL iterates over the elements of the source and evaluates selectionExpression for each element. Elements with a Boolean true result are retained.

For example, suppose the root object has a list orders:

~~~java
orders.?[total > 100]
~~~

The expression returns orders with total greater than 100.

It can be evaluated using the parser:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext(report);

List<?> selected = parser
        .parseExpression("orders.?[total > 100]")
        .getValue(context, List.class);
~~~

The example assumes orders is an iterable collection and each element has an appropriate total property.

### 1.2. #this is the element currently being examined

In a predicate, **#this** represents the current element that selection is checking.

Example:

~~~java
orders.?[#this.total > 100]
~~~

This notation is equivalent to accessing the total property directly inside the predicate:

~~~java
orders.?[total > 100]
~~~

Using #this makes the expression clearer when the predicate has multiple access levels or when you need to distinguish the current element from the root object.

**#root** still represents the root object of the EvaluationContext, while **#this** changes with the element currently being processed in selection. These two variables do not have the same meaning.

Example:

~~~java
orders.?[#this.customerId == #root.currentCustomerId]
~~~

Here, #this is each order; #root is the root object containing the orders list and currentCustomerId.

### 1.3. Empty result

If no element satisfies the predicate, selection of the form **.?[...]** returns an empty collection (or an empty map if the source is a map). This is a valid result, not a parse error.

The application needs to distinguish:

- No matching elements: empty result.
- Null collection source: needs null handling according to configuration and expression syntax.
- Predicate accesses a nonexistent property or method call fails: may raise an evaluation error.

An empty result should not be treated as proof that input data is invalid. It only indicates that no entry passed the condition.

## 2. Selection on List

### 2.1. Filtering objects in a list

A list typically contains objects with well-defined properties. Example:

~~~java
orders.?[status == 'PAID']
~~~

The expression selects all orders whose status is PAID.

Multiple conditions can be combined:

~~~java
orders.?[
    status == 'PAID' && total >= 100
]
~~~

Each element is selected only when both conditions are true.

If the condition accesses a property that may be null, guard the access with a null check and take advantage of short-circuit evaluation:

~~~java
orders.?[
    customer != null && customer.active
]
~~~

When customer is null, the right-hand side is not evaluated.

### 2.2. Filtering a list of numbers or strings

A predicate can work directly on element values:

~~~java
numbers.?[#this > 10]
~~~

~~~java
names.?[#this.startsWith('A')]
~~~

The first example retains numbers greater than 10. The second example retains strings starting with the letter A.

If elements may be null, do not call a method directly without checking first:

~~~java
names.?[#this != null && #this.startsWith('A')]
~~~

The null condition comes first to avoid calling startsWith on a null value.

### 2.3. Getting the first and last element

Besides filtering all elements, SpEL can get the first or last element satisfying the predicate:

~~~java
orders.^[status == 'PAID']
~~~

~~~java
orders.$[status == 'PAID']
~~~

- **.^[...]** finds the first element satisfying the condition in iteration order.
- **.$[...]** finds the last element satisfying the condition in iteration order.

These two operators return a single matching element, not a collection containing all results. If no element is found, the result is null.

Iteration order matters. For a List, element order is usually determined by position in the list. For other collections, order depends on the implementation and contract of that collection. Do not use first/last to express "newest" or "largest" if the data has not been sorted by the corresponding criterion.

If you need the element with the largest total, sort or compute by that criterion in Java, or prepare ordered data before using selection.

### 2.4. Selection is not Projection

Selection and projection solve two different needs:

- **Selection** filters elements and keeps the selected elements unchanged.
- **Projection** transforms each element into another value or structure.

Selection example:

~~~java
orders.?[total > 100]
~~~

The result still consists of orders.

Projection example:

~~~java
orders.![customerName]
~~~

The result consists of the corresponding customerNames, no longer the original orders.

The two operators can be combined:

~~~java
orders.?[status == 'PAID'].![id]
~~~

The expression filters paid orders and then retrieves the id of each order. Use selection first to narrow the elements to process, then projection to produce the output data.

## 3. Selection on Map

### 3.1. Predicate is evaluated on Map.Entry

Unlike a list, a map contains key-value pairs. When selecting on a map, SpEL evaluates the predicate on each entry (of Java type Map.Entry).

Two important properties accessible in the predicate are:

- **key**: the key of the current entry.
- **value**: the value corresponding to the key.

Example of a map storing quantities by product code:

~~~java
inventory.?[value > 0]
~~~

The expression retains entries with a value greater than 0.

It can be accessed more explicitly:

~~~java
inventory.?[#this.value > 0]
~~~

In this predicate, #this is the entry being examined, #this.key is the key, and #this.value is the value.

### 3.2. Filtering by key

If the condition depends on the key:

~~~java
settings.?[key.startsWith('feature.')]
~~~

The expression retains entries whose key starts with feature.

Key and value can be combined:

~~~java
settings.?[
    key.startsWith('feature.')
    && value == true
]
~~~

This example selects features whose Boolean value is true.

If key or value may be null, check for null before calling a method or comparing according to the desired rule:

~~~java
settings.?[
    key != null && key.startsWith('feature.')
]
~~~

### 3.3. Result of selection on Map

For a map, selection of the form **.?[...]** returns a new map containing the selected entries. Both key and value of each entry are preserved; the predicate does not turn the map into a list of values.

Example:

~~~java
{
    'A100': 10,
    'B200': 0,
    'C300': 25
}.?[value > 0]
~~~

The result is a map containing the entries A100 and C300.

This matters when retrieving the result in Java. If the source is a map, receive the result as a Map and verify the key/value types:

~~~java
Map<?, ?> available = parser
        .parseExpression("inventory.?[value > 0]")
        .getValue(context, Map.class);
~~~

Do not force a map selection result into a List just because the predicate iterates over each entry. Selection preserves the map structure for map sources.

### 3.4. Getting the first or last matching entry

Maps can also use first/last selection:

~~~java
inventory.^[value > 0]
~~~

~~~java
inventory.$[value > 0]
~~~

The predicate is evaluated on each entry. The result is the first or last matching entry in the map's iteration order. If you need to use the result as an entry, handle it with the appropriate Map.Entry type or convert it at the Java layer per the application's contract.

With HashMap, do not assume a stable or business-meaningful iteration order. If deterministic first/last semantics are needed, use an appropriately ordered map such as LinkedHashMap or sort the data before evaluation.

## 4. Selection on other Collections

### 4.1. Collection and Iterable

Selection is not only for List. It can be used with iterable collections (Iterable), such as:

- List: ordered and accessible by index.
- Set: guarantees uniqueness by equals/hashCode; order depends on the implementation.
- Queue or Deque: has traversal rules depending on the implementation.
- Custom Collection types implementing Iterable.

Example with Set:

~~~java
activeUsers.?[enabled]
~~~

Or with numeric elements:

~~~java
scores.?[#this >= 80]
~~~

Selection iterates over the elements and keeps those satisfying the predicate. Do not assume the result always preserves the exact concrete implementation of the source, such as LinkedHashSet or TreeSet. If the application requires a specific output collection type, convert it explicitly in Java.

### 4.2. Differences in ordering

The order of the result depends on the source's iteration order:

| Source | Ordering characteristic | Note when selecting |
|---|---|---|
| ArrayList | By element position | Result follows list order |
| LinkedList | By linked order | Result follows iteration order |
| LinkedHashSet | By insertion order | Can rely on the defined iteration order |
| TreeSet | By comparator | Result follows comparator order |
| HashSet | Does not guarantee stable order | Do not use first/last for business semantics |
| LinkedHashMap | By maintained iteration order | Map selection preserves matching entries |
| HashMap | Does not guarantee stable iteration order | Do not infer first/last by time or priority |

Selection does not sort data automatically. It only filters in the order provided by the source.

### 4.3. Array and non-Collection data

Selection is designed for iterable collections and maps. If the source data is a Java array, do not assume every SpEL configuration/version handles arrays the same way as a List or Iterable.

When selection on an array is needed, the clear approach is to convert the array into an appropriate collection in Java and place that collection into the context:

~~~java
List<String> names = Arrays.asList(nameArray);
context.setVariable("names", names);
~~~

Then use:

~~~java
#names.?[#this.startsWith('A')]
~~~

This clarifies the input data type and helps control copying or mutating the collection.

## 5. Combining selection with root object and context variables

Selection is often used on a property of the root object:

~~~java
orders.?[total > #minimum]
~~~

Where #minimum is a context variable:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(report);

context.setVariable("minimum", 100);
~~~

The predicate uses #this for the current element and uses #root or context variables to reference external data:

~~~java
orders.?[
    #this.customerId == #root.currentCustomerId
    && #this.total >= #minimum
]
~~~

This lets the expression cleanly separate:

- Data of the current element.
- Global data in the root object.
- Parameters supplied separately via context.

Only put necessary and validated variables into the context. Do not place a large object or a highly privileged service just to supply a simple value to a predicate.

## 6. Null and errors during selection

### 6.1. Collection source may be null

If the collection property may be null, a direct selection expression may not behave as it does when the source is a valid collection. You can check for null first:

~~~java
orders != null ? orders.?[total > 100] : {}
~~~

The example above is suitable when orders is a list and the default branch is an empty list. If the source is a map, use an empty map:

~~~java
settings != null ? settings.?[value == true] : {:}
~~~

Do not use **{}** as a default for a map because **{}** is an empty inline list.

If the Spring version in use supports safe selection, you can consider safe navigation syntax combined with selection. Confirm the version and test behavior with a null source before putting it into shared expressions.

### 6.2. Null elements inside a collection

A collection can contain null elements. The predicate needs to check before accessing properties:

~~~java
users.?[
    #this != null && #this.enabled
]
~~~

Without a null guard, reading enabled on a null element can raise an evaluation error.

### 6.3. Nonexistent property or method

Selection does not swallow property or method errors. Example:

~~~java
users.?[unknownProperty == true]
~~~

If the element does not have an unknownProperty property and the accessor cannot resolve it, evaluation may fail. Selection does not automatically skip failing elements.

Check the model and predicate. If elements have different types, normalize the data or write conditions based on the actual types.

### 6.4. Distinguishing empty results from errors

| Result/situation | Meaning |
|---|---|
| Collection selection returns empty | No element satisfies the predicate |
| Map selection returns empty map | No entry satisfies the predicate |
| First/last selection returns null | No matching element found |
| ParseException | Invalid selection syntax |
| EvaluationException | Predicate or data access failed |

The application should handle each case according to its own meaning. Do not catch every EvaluationException and return an empty collection, as doing so can hide misspelled property names or logic bugs.

## 7. Cost and writing efficient predicates

Selection must evaluate the predicate on elements of the source. For a collection with n elements, the basic traversal cost generally scales with the number of elements, plus the cost of the predicate.

Example:

~~~java
orders.?[
    customer != null
    && customer.active
    && total >= #minimum
]
~~~

A simple predicate accessing necessary properties is usually easier to control than an expression calling many methods or performing repeated calculations.

Some guidelines:

- Limit the number of collection elements before placing them into the context.
- Put null checks before dependent accesses to leverage short-circuiting.
- Avoid calling resource-intensive methods or methods with side effects in a predicate.
- Do not repeat the same complex calculation for every element if it can be prepared beforehand.
- If complex sorting, grouping, or joining of data is needed, do it in Java or a dedicated query layer.
- Do not use first/last as a substitute for sorting by business criteria.

With large datasets, consider filtering directly at the database or repository rather than loading the entire collection and running selection in memory.

## 8. Complete example: List and Map

Suppose the application has the data:

~~~java
public record Product(
        String code,
        boolean active,
        int stock
) {
}

public class InventoryReport {

    private final List<Product> products;
    private final Map<String, Integer> stockByWarehouse;

    public InventoryReport(
            List<Product> products,
            Map<String, Integer> stockByWarehouse) {
        this.products = products;
        this.stockByWarehouse = stockByWarehouse;
    }

    public List<Product> getProducts() {
        return products;
    }

    public Map<String, Integer> getStockByWarehouse() {
        return stockByWarehouse;
    }
}
~~~

Create the context:

~~~java
InventoryReport report = new InventoryReport(
        List.of(
                new Product("P-01", true, 10),
                new Product("P-02", false, 0),
                new Product("P-03", true, 25)
        ),
        Map.of(
                "HCM", 10,
                "HN", 0,
                "DN", 25
        )
);

StandardEvaluationContext context =
        new StandardEvaluationContext(report);

ExpressionParser parser = new SpelExpressionParser();
~~~

Filter active products:

~~~java
List<?> activeProducts = parser
        .parseExpression("products.?[active]")
        .getValue(context, List.class);
~~~

Get the first product with stock greater than 10:

~~~java
Object firstAvailable = parser
        .parseExpression("products.^[stock > 10]")
        .getValue(context);
~~~

Filter warehouses with stock remaining:

~~~java
Map<?, ?> availableWarehouses = parser
        .parseExpression("stockByWarehouse.?[value > 0]")
        .getValue(context, Map.class);
~~~

The map result keeps keys HCM and DN with their corresponding values. If you need to retrieve a specific warehouse, access the key after selection or use direct map access.

## 9. Testing selection

You should test full results, first/last, empty sources, no results, and null data.

Example with List:

~~~java
List<Integer> numbers = List.of(5, 10, 15, 20);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("numbers", numbers);

List<?> selected = parser
        .parseExpression("#numbers.?[#this >= 10]")
        .getValue(context, List.class);

assertEquals(List.of(10, 15, 20), selected);

Integer first = parser
        .parseExpression("#numbers.^[#this >= 10]")
        .getValue(context, Integer.class);

assertEquals(10, first);

Integer last = parser
        .parseExpression("#numbers.$[#this >= 10]")
        .getValue(context, Integer.class);

assertEquals(20, last);
~~~

Example with Map:

~~~java
Map<String, Integer> stock = Map.of(
        "HCM", 10,
        "HN", 0,
        "DN", 25
);

context.setVariable("stock", stock);

Map<?, ?> available = parser
        .parseExpression("#stock.?[value > 0]")
        .getValue(context, Map.class);

assertEquals(2, available.size());
assertEquals(10, available.get("HCM"));
assertEquals(25, available.get("DN"));
~~~

In addition to the cases above, you should test:

- Empty collection.
- Empty map.
- No element satisfying the predicate.
- Null elements inside a collection.
- Map with null key or value.
- Ordered collection and collection without guaranteed order.
- Predicate accessing a nonexistent property.
- Large collection near input limits.

Testing by source type is very important: list selection and map selection do not have the same result type. Do not just check the element count; verify both the type and the contents of the result.

## 10. Summary

Selection in SpEL filters data by a predicate and has three main forms:

- **.?[...]** gets all elements or entries satisfying the condition.
- **.^[...]** gets the first matching element or entry.
- **.$[...]** gets the last matching element or entry.

For List and Iterable collections, the predicate is evaluated on each element; the result is the collection of selected elements. For Map, the predicate is evaluated on Map.Entry via key and value, and general selection returns a map containing the matching entries.

Remember to use #this for the current element, #root for the root object, check for null before accessing properties, and do not assume a collection is ordered if the implementation does not guarantee it. Selection is well suited for concise in-memory filters; for large datasets or complex logic, filter at the Java or database layer to control costs better.