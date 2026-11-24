# Distinguishing projection from mapping in Java code

Projection in SpEL and mapping in Java can both transform a set of objects into a new set of values. For example, from a list of orders, we can extract a list of order codes, customer names, or totals. The external result may look similar, yet the two mechanisms differ in syntax, execution time, data typing, compile-time checking, and scope of processing.

In SpEL, projection uses the .![...] syntax. In Java, mapping is commonly performed with the Stream API's map(). Understanding both approaches helps choose the right tool: SpEL is convenient for short expressions that are configured or evaluated dynamically; Java fits complex transformations requiring static types, multi-step processing, or large pipelines.

## 1. What is projection in SpEL?

Projection is the operation of applying an expression to each element of a collection to produce corresponding results. Basic syntax:

    collection.![projectionExpression]

The dot accesses an operation on the collection, the exclamation mark denotes projection, and the expression inside square brackets is evaluated for each element.

For example, suppose an order has a list of line items, each containing a product and a quantity. To retrieve the names of all products:

    lines.![product.name]

SpEL takes each element of lines in turn, reads product.name on the current element, and puts the result into the output collection. If the input list has five line items, the result has five corresponding values.

Projection does not modify elements of the source collection. It builds a new result from the value computed for each element. If the expression returns a property, the result is the set of those properties; if the expression performs a calculation, the result is the set of computed values.

Example getting the total amount of each line item:

    lines.![unitPrice * quantity]

Example building a label from multiple properties:

    lines.![product.name + ' x ' + quantity]

In each evaluation, #this represents the current element. Therefore, the following expression is equivalent to the example retrieving product names:

    lines.![#this.product.name]

Writing #this explicitly is helpful when expressions are nested or when you need to distinguish the current element from the root object.

## 2. Mapping in Java with Stream.map()

In Java, the Stream API provides the map() method to transform each input element into an output value. The equivalent example for retrieving product names:

    List<String> productNames = order.getLines().stream()
            .map(LineItem::getProduct)
            .map(Product::getName)
            .collect(Collectors.toList());

Each call to map() takes a Function and returns a new Stream containing the transformed results. You can chain multiple map() steps to traverse properties or convert data. collect() is a terminal operation that ends the pipeline and gathers results into a List.

If only one step is needed, you can write:

    List<String> productNames = order.getLines().stream()
            .map(line -> line.getProduct().getName())
            .collect(Collectors.toList());

This style clearly expresses that each LineItem is converted into a Product name. The Java compiler checks the types of method references, lambdas, and results based on generic declarations.

## 3. The same problem in SpEL and Java

Suppose the root object is Order, with a lines property of type List<LineItem>. Each LineItem has product, and Product has name.

### Writing it in SpEL

    ExpressionParser parser = new SpelExpressionParser();

    EvaluationContext context =
            SimpleEvaluationContext.forReadOnlyDataBinding().build();

    Expression expression =
            parser.parseExpression("lines.![product.name]");

    List<?> productNames =
            expression.getValue(context, order, List.class);

Here, lines is read from the root object order. Projection runs the expression product.name on each LineItem and returns the resulting collection.

If using a variable instead of a root property:

    context.setVariable("order", order);

    Expression expression =
            parser.parseExpression("#order.lines.![product.name]");

The variable is referenced with the # prefix. The property path inside projection is still evaluated on each line item.

### Writing it in Java

    List<String> productNames = order.getLines().stream()
            .map(line -> line.getProduct().getName())
            .collect(Collectors.toList());

Both approaches produce a list of product names in the source's iteration order. However, SpEL expresses the transformation inside an expression string; Java expresses it using typed functions checked by the compiler.

## 4. #this and root object in projection

In regular SpEL expressions, #root references the root object of the evaluation. When entering a projection, #this changes for each element currently being processed.

Example:

    lines.![#this.product.name]

On each iteration:

- #this is the current LineItem.
- #this.product is that line item's Product.
- #this.product.name is the product name placed into the result.

If you need to combine data of the current element with a property on the root Order:

    lines.![#this.quantity * #root.exchangeRate]

Here, quantity belongs to the current LineItem; exchangeRate belongs to the root object Order. Using #this and #root properly avoids reading a property on the wrong level of object.

In Java Stream, the lambda receives the current element via its parameter:

    order.getLines().stream()
            .map(line -> line.getQuantity() * order.getExchangeRate())
            .collect(Collectors.toList());

The line parameter plays a role similar to #this; the order variable referenced from the outer scope plays the role of the root data needed by the lambda.

## 5. Projection is not the same as Selection

Projection and Selection are often chained together, but they have different purposes:

- Projection (.![...]) transforms each element and creates a result for every element.
- Selection (.?[...]) filters elements by a condition and keeps elements satisfying the condition.

For example, getting only product names from line items with quantity greater than 1:

    lines.?[quantity > 1].![product.name]

SpEL performs selection first, then projection on the filtered result set.

Java can express the same pipeline using filter() followed by map():

    List<String> productNames = order.getLines().stream()
            .filter(line -> line.getQuantity() > 1)
            .map(line -> line.getProduct().getName())
            .collect(Collectors.toList());

If you use map() without filter(), Java still transforms every element. If you use projection without selection, SpEL likewise produces results for all input elements. Do not confuse selecting a property with filtering elements.

## 6. Differences in data typing and compile-time checking

The Java Stream API uses generics and functional types. Example:

    Stream<LineItem> lines = order.getLines().stream();

    Stream<String> names = lines.map(LineItem::getProduct)
            .map(Product::getName);

The compiler knows the input is LineItem and the final result is String. Calling a non-existent method on Product or returning an incompatible type is normally caught at compile time.

SpEL is an expression language parsed and evaluated at runtime. The string:

    lines.![product.name]

is not checked by the Java compiler for the product or name properties. If the runtime type lacks that property, the error only surfaces when SpEL evaluates the expression.

When receiving results from SpEL via getValue, the application can request a target type, yet that does not turn the entire expression into static typing like Java generics. Expressions must be tested with realistic data and evaluation errors handled appropriately.

## 7. Differences in execution timing

A Stream pipeline in Java is normally lazy. The map() and filter() steps only describe the pipeline; most of the work happens when calling a terminal operation such as collect(), count(), or forEach().

Example:

    Stream<String> names = order.getLines().stream()
            .map(line -> line.getProduct().getName());

    List<String> result = names.collect(Collectors.toList());

The transformation executes when collect() consumes the stream.

SpEL projection is evaluated when getValue() is called. Once the evaluation completes, the projection result has already been built. It does not return a lazy Java Stream to continue chaining Stream API processing steps.

This matters when data is large or transformations are costly. Java Streams support lazy pipelines and can be paired with parallel streams when appropriate. SpEL projection is aimed at evaluating expressions on supplied data, not replacing stream processing mechanisms for large data volumes.

## 8. Projection on Map and collections

Projection is not limited to List. SpEL supports projection on collections and arrays. For a Map, the projection expression is evaluated on each Map.Entry; the result is a collection of projected values.

For example, if the prices map holds product codes as keys and prices as values:

    #prices.![#this.key + ':' + #this.value]

The expression creates strings combining the key and value of each entry. #this in this case is the current Map.Entry.

Remember that projection on a Map is not an operation that preserves the key-value structure like a map-to-map transformation. The projection result is a collection of computed values. If you need to build a new Map preserving keys or transforming them with complex rules, Java Stream with Collectors.toMap() is usually clearer.

Java example creating a new Map:

    Map<String, BigDecimal> normalizedPrices =
            prices.entrySet().stream()
                    .collect(Collectors.toMap(
                            Map.Entry::getKey,
                            entry -> entry.getValue().setScale(2)
                    ));

When you need to preserve data structure or handle duplicate keys, process it explicitly in Java rather than assuming projection will preserve a Map.

## 9. Null handling in projection and mapping

An intermediate property may be null. For example, product may be null or name may be null. Regular projection:

    lines.![product.name]

can fail if a line item's product is null.

You can use null-safe navigation to protect properties that may be missing:

    lines.![#this?.product?.name]

If an element of the collection is null, #this?.product makes the access return null for that element. If only product can be null, you can write:

    lines.![product?.name]

In Java, null handling must be expressed explicitly via filter, Optional, or conditionals inside lambdas:

    List<String> productNames = order.getLines().stream()
            .filter(Objects::nonNull)
            .map(LineItem::getProduct)
            .filter(Objects::nonNull)
            .map(Product::getName)
            .collect(Collectors.toList());

The two approaches can produce different results depending on whether null elements are dropped or nulls are kept in the result collection. Decide the output contract clearly: keep positions with null values, exclude elements missing data, or use a default value.

If the input collection itself is null, check it before invoking projection or creating a stream. Null-safe navigation on each element's properties does not automatically handle a null root collection.

## 10. Do projection and mapping modify source data?

Normally, both SpEL projection and Java map() produce transformed results without modifying the source collection. Example:

    lines.![product.name]

only reads product names and creates a result collection. It does not change product.name in the LineItems.

Similarly:

    order.getLines().stream()
            .map(LineItem::getQuantity)
            .collect(Collectors.toList());

produces a list of quantities; it does not update the original line items.

However, if the expression invokes a method with side effects or a Java lambda mutates referenced objects, behavior can differ. Therefore, use read-only properties/getters in projections and use map() for clear value transformations. If the goal is to update existing objects, perform it with intentional Java logic that is easy to test and transactionally controlled.

## 11. Projection is not database projection

Projection in SpEL operates on collections or arrays already in memory for the evaluation. It does not automatically translate expressions into SQL, does not instruct JPA to fetch only certain columns, and does not optimize database queries.

Example:

    order.lines.![product.name]

only reads product.name on the line items that the object graph has already provided. If order.lines is a lazy JPA association, accessing it may trigger data loading depending on ORM configuration. SpEL does not automatically prevent N+1 queries or ensure only one query runs.

If you need true database projection, use DTO projections, JPQL constructor expressions, Spring Data interface projections, or appropriate SQL queries. Fetch the right data at the persistence layer, then use SpEL or Java to handle the needed expression logic.

## 12. When should you use SpEL projection?

SpEL projection fits when:

- Transformation rules are short and readable.
- The expression is used in Spring configuration or a feature already integrated with SpEL.
- You need to extract a property or compute a simple value on each element.
- Input data is already prepared in memory.
- You want to manage the projection as a configurable and independently testable expression.

Examples:

    members.![name]
    orders.![total * taxRate]
    lines.?[quantity > 0].![product.name]

Do not force it into SpEL when:

- The transformation has many steps, branches, or requires detailed error handling.
- You need to build a new Map with complex key rules or handle duplicate keys.
- You need grouping, partitioning, flatMap, parallel processing, or large pipelines.
- You need strict compile-time type checking by the compiler.
- The transformation has side effects or needs to update domain state.

In these cases, Java Streams, collectors, or a clearly named domain method are usually easier to maintain.

## 13. Quick comparison table

| Criterion | SpEL projection | Java Stream mapping |
|---|---|---|
| Syntax | .![expression] | map(function) |
| Input | Collection, array, or Map | Stream of elements |
| Transformation | Expression evaluated for each element | Function or method reference |
| Data types | Resolved primarily at runtime | Generics and compile-time checking by compiler |
| Execution | When getValue() is called | Lazy until terminal operation |
| Result | Projection result collection | New Stream, then collectable |
| Map handling | Projects each Map.Entry into a value | Can use entrySet() and Collectors |
| Advanced pipelines | Focused on expressions | filter, flatMap, grouping, partitioning, parallel |
| Best suited for | Short rules, dynamic configuration | Complex transformation logic, static typing needs |

## 14. Testing and operations

Whether using SpEL or Java, collection transformations should be tested with representative data:

- Collections with multiple elements to verify order and result count.
- Empty collections to verify empty results.
- Null elements or null intermediate properties to verify the handling policy.
- Properties with edge values or unexpected data types.
- Maps with missing keys/values or duplicate keys when building a new Map.
- Large collections to evaluate cost and choose an appropriate processing approach.

With SpEL, test both parsing and evaluation. A string can parse successfully yet still fail when a property is missing on the runtime type or when data is null. Parse stable expressions once, evaluate with an appropriate context, and expose only the necessary properties.

With Java Streams, the compiler catches many type errors earlier, yet lambda logic, null handling, and collectors still require testing. In particular, if using parallel streams, consider thread safety and result ordering.

## Conclusion

Projection in SpEL uses .![...] to apply an expression to each element and build a result collection. Mapping in Java typically uses Stream.map() with a lambda or method reference. Both approaches can produce identical data, yet they differ in static typing, execution timing, pipeline composability, and error control.

Use SpEL projection for short, configurable projections on data already in memory. Use Java mapping when you need compiler type checking, multi-step pipelines, collectors, grouping, or complex domain logic. Neither automatically turns into a database projection nor automatically modifies source data; place querying, transforming, and updating in the layers responsible for them.