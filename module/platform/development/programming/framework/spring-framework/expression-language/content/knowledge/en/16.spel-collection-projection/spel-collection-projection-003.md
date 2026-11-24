# Transforming an object collection into a value collection

Spring Expression Language (SpEL) provides **collection projection** to apply an expression to each element of a collection and produce a new result collection. Projection is especially useful when the input data is a list of objects, while downstream processing only needs one property or a value computed from each object.

For example, from a list of Orders, you can produce a list of order IDs or totals:

~~~text
#orders.![id]
#orders.![total]
~~~

Each input element is read once according to the projection expression. The result is a set of extracted or transformed values, keeping configuration concise when objects need to be turned into simple data.

## 1. Projection syntax

General syntax:

~~~text
collection.![projectionExpression]
~~~

The **.!** token is the projection operator. The part inside the square brackets is the expression evaluated for each element.

Example:

~~~text
#orders.![customer.name]
~~~

For each Order in orders, SpEL reads customer.name and puts the result into a new collection.

Suppose the input data is:

~~~java
List<Order> orders = List.of(
    new Order("ORD-001", "An", new BigDecimal("120.00")),
    new Order("ORD-002", "Binh", new BigDecimal("85.00")),
    new Order("ORD-003", "Chi", new BigDecimal("240.00"))
);
~~~

Projection:

~~~text
#orders.![id]
~~~

produces the list of IDs:

~~~text
["ORD-001", "ORD-002", "ORD-003"]
~~~

Projection:

~~~text
#orders.![total]
~~~

produces the list of totals:

~~~text
[120.00, 85.00, 240.00]
~~~

Projection:

~~~text
#orders.![customerName.toUpperCase()]
~~~

produces a list of uppercased names, provided the Order model has a customerName property and the method is permitted in EvaluationContext.

Important point: projection does not only retrieve properties. A projection expression can be a calculation, string concatenation, permitted method call, or nested property path.

## 2. How does SpEL evaluate each element?

When projection runs, SpEL iterates over the elements of the source. On each iteration, the expression is evaluated on the current element.

You can picture it as:

1. Take the first element.
2. Set that element as the current evaluation object.
3. Evaluate the projection expression.
4. Add the result to the output collection.
5. Continue with the remaining elements.

Therefore, in a projection over List<Order>, the expression:

~~~text
#orders.![customer.name]
~~~

is interpreted as reading customer.name on each Order.

### 2.1. Using properties without #this

Because the current evaluation object is the element being processed, properties can be referenced directly:

~~~text
#orders.![id]
#orders.![customer.name]
#orders.![total.multiply(1.1)]
~~~

In the last example, SpEL calls the multiply method on the total property of each Order. Make sure the method is available and compatible with the context.

### 2.2. Using #this to explicitly reference the current element

The **#this** variable always represents the current evaluation object. Inside projection, #this is the element currently being processed:

~~~text
#orders.![#this.customer.name]
#orders.![#this.total]
~~~

Both ways of writing have the same meaning in the example above. Using #this makes the expression clearer when multiple properties share the same name or when combined with complex expressions.

### 2.3. Distinguishing #this and #root

- **#this** changes with the current evaluation object; inside projection it points to the element currently being processed.
- **#root** always points to the initial root context object.

For example, suppose the root object is a ReportRequest with orders and reportName properties:

~~~text
#root.reportName + ': ' + #this.id
~~~

If this expression is used in a projection over orders, #this.id is the ID of the current Order, while #root.reportName remains the root report name.

Both can be used together to build labels:

~~~text
#root.reportName + ' / ' + #this.customer.name
~~~

## 3. Data types supporting projection

SpEL supports projection on:

- Arrays.
- Types implementing java.lang.Iterable, including List and Set.
- Maps.

The projection result is a new collection. When projection runs on a Map, SpEL evaluates the projection expression on each Map entry, represented by java.util.Map.Entry. The result of a Map projection is a List of values computed from each entry.

This is important: projection on a Map does not preserve the Map's key-value structure. If you need a new Map with selected or transformed keys and values, consider building the Map in Java or another appropriate operation.

### 3.1. Projection on List

~~~java
context.setVariable("names", List.of("An", "Binh", "Chi"));
~~~

Expression:

~~~text
#names.![#this.toUpperCase()]
~~~

Result:

~~~text
["AN", "BINH", "CHI"]
~~~

### 3.2. Projection on array

~~~java
context.setVariable("scores", new int[] {70, 85, 92});
~~~

Expression:

~~~text
#scores.![#this + 5]
~~~

The result is a collection of values incremented by 5:

~~~text
[75, 90, 97]
~~~

### 3.3. Projection on Map

~~~java
Map<String, Integer> stock = Map.of(
    "PEN", 12,
    "BOOK", 8,
    "BAG", 3
);
context.setVariable("stock", stock);
~~~

With a Map, #this is a Map.Entry. You can retrieve the key:

~~~text
#stock.![#this.key]
~~~

Or retrieve the value:

~~~text
#stock.![#this.value]
~~~

Or build a descriptive string for each entry:

~~~text
#stock.![#this.key + ':' + #this.value]
~~~

The result is a List, following the iteration order of the source Map. If order matters, use a Map with a deterministic iteration order, such as LinkedHashMap.

## 4. Transforming objects into simple values

A common case is creating a list of IDs, names, statuses, or metrics from an object collection.

Suppose you have the model:

~~~java
class Product {
    private String sku;
    private String name;
    private BigDecimal price;

    public String getSku() { return sku; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
}
~~~

Register the collection in EvaluationContext:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("products", products);

ExpressionParser parser = new SpelExpressionParser();
~~~

Retrieve the list of SKUs:

~~~java
List<?> skus = parser
        .parseExpression("#products.![sku]")
        .getValue(context, List.class);
~~~

Retrieve the list of names:

~~~java
List<?> names = parser
        .parseExpression("#products.![name]")
        .getValue(context, List.class);
~~~

Retrieve the list of prices:

~~~java
List<?> prices = parser
        .parseExpression("#products.![price]")
        .getValue(context, List.class);
~~~

You can produce computed values instead of taking raw properties:

~~~text
#products.![price * 1.08]
~~~

Or build display strings:

~~~text
#products.![sku + ' - ' + name]
~~~

Each element of the resulting collection is the result of the expression corresponding to one input Product.

## 5. Projection on nested properties

Projection can read deep into an object graph:

~~~text
#orders.![customer.address.city]
~~~

From List<Order>, the expression produces a List containing each customer's city.

Other examples:

~~~text
#employees.![department.manager.name]
#invoices.![customer.billingAddress.postalCode]
#books.![publisher.name]
~~~

You can compute a value from multiple properties:

~~~text
#orders.![customer.name + ' - ' + total]
~~~

Or return a simple data structure for each object using an inline map:

~~~text
#products.![{sku: sku, label: name, amount: price}]
~~~

The projection expression in the last example creates a Map for each Product. The result is a List of Maps, where each Map contains values extracted from one input object.

Use this approach when you need to convert domain objects into a compact structure for display or data transfer. If mapping involves many fields, complex formatting rules, or needs validation, a DTO mapper in Java is usually easier to maintain and test.

## 6. Combining selection and projection

Projection and selection have different purposes:

- **Selection** is used to filter elements by a condition.
- **Projection** is used to transform each element into another value.

For example, getting the IDs of orders with a total of 100 or more:

~~~text
#orders.?[total >= 100].![id]
~~~

It can be read in order:

1. #orders.?[total >= 100] keeps the Orders matching the condition.
2. .![id] extracts the ID from each remaining Order.
3. The final result is a List of IDs.

Example getting customer names for paid orders:

~~~text
#orders.?[status == 'PAID'].![customer.name]
~~~

Comparing expressions:

| Expression | Effect | Result |
| --- | --- | --- |
| **#orders[0]** | Get element by index | One Order |
| **#orders.?[total > 100]** | Filter Orders by condition | Collection of Orders |
| **#orders.![id]** | Convert each Order into an ID | Collection of IDs |
| **#orders.?[total > 100].![id]** | Filter then convert to IDs | Collection of IDs |

Do not use projection to filter data. If a projection expression returns true/false, the result is a list of booleans corresponding to each element, rather than a list of elements matching the condition. To drop elements, use selection.

## 7. Handling potentially null collections or elements

### 7.1. Source collection is null

Regular projection requires the source collection to exist:

~~~text
#orders.![id]
~~~

If orders is null, the expression can fail during evaluation. SpEL supports null-safe projection with the **?.!** operator:

~~~text
#orders?.![id]
~~~

If orders is null, the null-safe projection expression returns null instead of attempting to iterate over the collection.

This differs from an empty collection. If orders is an empty List, regular projection returns an empty result collection.

### 7.2. Elements inside the collection are null

Null-safe projection protects the source collection. It does not automatically protect every property access inside the projection expression.

Example:

~~~text
#orders?.![customer.name]
~~~

If the orders collection exists but an element is null, or an Order's customer is null, accessing the property can cause an error.

Use safe navigation inside the projection expression at steps that may be null:

~~~text
#orders?.![#this?.customer?.name]
~~~

In this example:

- **?.!** protects against the orders collection being null.
- **#this?.** protects the current element if that element is null.
- **customer?.name** protects customer if this property is null.

The result at the corresponding position may be null. Projection still produces one result for each iterated element; it does not automatically remove null results.

### 7.3. Wanting to skip null elements or missing data

If the goal is to retrieve only customer names that have a value, combine selection and projection:

~~~text
#orders.?[customer != null].![customer.name]
~~~

If the collection element itself can also be null, the condition needs to check the element first:

~~~text
#orders.?[#this != null and customer != null].![customer.name]
~~~

Selection removes elements that do not match the condition, and then projection extracts name from the remaining elements.

If multiple null states or complex filtering rules need to be handled, consider moving the logic into a Java service for clearer expression.

## 8. Does projection modify the original collection?

Projection creates a new result collection; it does not alter the structure of the source collection simply by performing the transformation.

Example:

~~~text
#products.![name]
~~~

creates a new List of names. It does not remove Products from products, nor does it change the order of the original data.

However, a new collection must be distinguished from a deep copy:

- If the projection returns an immutable value such as a String or a number, the result contains those values.
- If the projection returns an object property, such as **#orders.![customer]**, the new output collection contains references to the existing Customer objects.
- Projection does not automatically copy the entire object graph or clone returned objects.

Therefore, projection is suited for extracting and transforming data without modifying the source collection. If the expression calls a method with side effects or mutates objects, those side effects can still happen; keep projection expressions simple and primarily read-only.

## 9. Running projection with the SpEL API in Java

You can parse and evaluate projections using SpEL APIs:

~~~java
ExpressionParser parser = new SpelExpressionParser();

EvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

context.setVariable("orders", orders);

List<?> orderIds = parser
        .parseExpression("#orders.![id]")
        .getValue(context, List.class);
~~~

Here:

- ExpressionParser parses the expression string.
- EvaluationContext provides the orders variable and data access rules.
- getValue() evaluates the projection and returns the result List.

If you want a specific type, you can cast elements after retrieving the result or convert them to DTOs in Java. Because generic types are erased at runtime, getValue(context, List.class) only requires the result to be a List and does not verify the generic type of each element.

An example producing a list of names from a Product collection:

~~~java
context.setVariable("products", products);

List<?> names = parser
        .parseExpression("#products.![name]")
        .getValue(context, List.class);
~~~

For expressions that can run multiple times, you can parse once and reuse the Expression object:

~~~java
Expression productNames =
        parser.parseExpression("#products.![name]");

List<?> firstResult = productNames.getValue(context, List.class);
List<?> nextResult = productNames.getValue(context, List.class);
~~~

A parsed Expression can be reused with an appropriate context or root object. The input data is still retrieved at evaluation time.

## 10. Using projection in Spring Integration

Some Spring integration points provide a collection as the root object or a variable in expressions. Projection can turn a collection of messages into a collection of payloads.

For example, if the root object is a List of Messages and you need the payload of each message:

~~~text
#this.![payload]
~~~

In a message-processing flow, this expression produces a collection of payloads from the input Message list. This is a concise way to extract the main data of each message when the endpoint provides the right context.

Be sure to clearly identify the root object and element type at the integration point. An expression that is valid when the root is List<Message> may not be valid if the endpoint supplies a single Message or a different payload.

Similarly, projection can be used in expressions of other modules when the context contains an appropriate collection. Do not assume all annotations share the same root object or variables.

## 11. Limitations and performance notes

Projection is convenient for short transformations, though several limitations should be considered:

1. **The result is a new collection:** if the source has N elements, projection typically produces N results. For large data sets, mind the memory usage of the output collection.
2. **Map projection returns a List:** if key-value pairs must be preserved, build a Map in Java or use an appropriate mapping approach.
3. **Properties and methods must be accessible:** the expression only runs if EvaluationContext has suitable accessors or resolvers.
4. **Null elements need handling:** safe projection protects the source collection; inner property access still requires safe navigation when needed.
5. **Projection is not filtering:** use selection if elements need to be excluded.
6. **Avoid side effects in projection:** the expression is evaluated for each element; a state-mutating method can produce hard-to-control effects.
7. **Consider performance on hot paths:** projection is one of the expression forms that the SpEL compiler does not support compiling. If an expression runs very frequently on large collections, measure it and consider Java Streams or a dedicated mapper.

If expressions are supplied by users or external systems, restrict accessible objects, property accessors, method resolvers, and functions in EvaluationContext. StandardEvaluationContext exposes broad SpEL capabilities and should not be used to run untrusted expressions. SimpleEvaluationContext limits certain features, yet context restrictions must still be carefully designed.

## 12. Common mistakes

1. **Using selection instead of projection:** selection filters elements; projection transforms elements.
2. **Forgetting the dot before !:** projection syntax is **.![...]**.
3. **Confusing #this with #root:** #this is the current element; #root is always the root context object.
4. **Assuming Map projection keeps a Map:** projection on a Map returns a List and evaluates the expression on each Map.Entry.
5. **Not handling null elements:** the collection may exist while an element or inner property is null.
6. **Using projection to build complex DTOs:** large mappings with many rules usually belong in a Java mapper.
7. **Assuming the result is a deep copy:** projection creates a new collection, but returned objects may still be references to the original objects.
8. **Not identifying the integration point's root object:** the same expression can mean something else if the context changes.
9. **Using projection on high-performance paths without measuring:** the SpEL compiler does not support compiling expressions containing projection.

## 13. Quick takeaways

- Collection projection uses the syntax **collection.![projectionExpression]**.
- Projection evaluates the expression for each element and creates a new result collection.
- You can read properties, nested properties, call permitted methods, or compute new values.
- Inside projection, **#this** is the current element; **#root** remains the root context object.
- Projection supports arrays, Iterable, and Map.
- On a Map, projection runs over each Map.Entry and returns a List of results.
- **?.!** is null-safe projection for a source collection that may be null.
- Safe projection does not automatically protect properties inside the expression; use safe navigation at each point that may be null.
- Use **.?[...]** to filter and then **.![...]** to transform elements.
- Projection creates a new collection without deep-copying returned objects.
- Use projection for short transformations; use a Java mapper or Stream when logic is complex or performance requirements are explicit.

## 14. Official references

- [Spring Framework — Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-projection.html)
- [Spring Framework — Variables, #this and #root](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/variables.html)
- [Spring Framework — Safe Navigation for Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html)
- [Spring Framework — Evaluation and SpEL Compiler Limitations](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/)
