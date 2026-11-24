# Combining projection with selection in Spring Expression Language (SpEL)

In SpEL, **selection** filters elements of a collection according to a condition, while **projection** transforms each element into another value or structure. Combining these two operations lets an expression both select the right data needed and produce results in a shape suitable for the next processing step.

A common pattern is filtering a list of paid orders and then extracting only the total of each order:

~~~text
orders.?[status == 'PAID'].![total]
~~~

The selection part keeps orders whose status is PAID. The projection part extracts the total property from each selected order and creates a list of totals.

This lesson explains the syntax, order of execution, result types, how to apply them to List and Map, selection variants, null handling, and Java examples you can use in applications.

## 1. Selection and projection do two different jobs

Selection and projection both operate on collections, but they serve different purposes.

**Selection** answers the question: which elements are kept?

~~~text
orders.?[total >= 100]
~~~

The expression above keeps orders whose total is greater than or equal to 100.

**Projection** answers the question: from each element, what value should be extracted or computed?

~~~text
orders.![total]
~~~

The expression above creates a new list containing the total of each order.

You can picture it as:

| Operation | Input | Result |
|---|---|---|
| Selection | Collection and Boolean condition | Collection of elements satisfying the condition |
| Projection | Collection and transformation expression | Collection of results of the expression on each element |

Selection decides which elements continue into the result. Projection decides what data is produced from each element.

## 2. Selection syntax in SpEL

Selection uses a question mark after the dot, followed by a condition expression in square brackets:

~~~text
collection.?[selectionExpression]
~~~

SpEL evaluates the condition on each element of the collection. While evaluating the condition, the current element becomes the active object and can be accessed via its properties or via the special variable #this.

Examples:

~~~text
customers.?[active]
customers.?[age >= 18]
customers.?[country == 'VN' and verified]
customers.?[#this.age >= 18]
~~~

The expressions above respectively filter customers who are active, of age, in country VN and verified, or of age by explicitly referencing #this.

The selection condition must produce an appropriate Boolean result. If the condition expression references a non-existent property or produces a type that cannot be used as Boolean, evaluation may fail.

### 2.1. Selection taking all matching elements

The .?[...] operator retains all elements for which the condition is true.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("customers.?[active]");

List<?> activeCustomers =
        expression.getValue(context, List.class);
~~~

If the input collection is a List, the selection result is a collection containing matching elements in the order encountered in the list. Retained elements are the original objects themselves, not yet transformed into another property.

### 2.2. Selection taking the first or last matching element

SpEL also provides two variants:

| Syntax | Meaning |
|---|---|
| .?[...] | Get all matching elements |
| .^[...] | Get the first matching element |
| .$[...] | Get the last matching element |

Examples:

~~~text
orders.^[status == 'PAID']
orders.$[status == 'PAID']
~~~

The first expression returns the first order whose status is PAID. The second expression returns the last order with that status.

With first or last selection, the result is a single element rather than a collection. If no matching element is found, the result is null. Therefore, Java code must handle the case where there is no result.

## 3. Projection syntax in SpEL

Projection uses an exclamation mark after the dot, followed by an expression in square brackets:

~~~text
collection.![projectionExpression]
~~~

SpEL evaluates the projection expression for each element and collects the results into a List.

Examples:

~~~text
customers.![name]
orders.![total]
products.![price * quantity]
~~~

The expressions respectively produce a list of customer names, each order's total, and price multiplied by quantity for each product.

In projection, #this references the element currently being processed. Therefore, the following two expressions have the same meaning:

~~~text
orders.![total]
orders.![#this.total]
~~~

Projection normally produces a result List even when the inner expression returns a simple type such as String, Integer, or Boolean. Each element in the List is the result of the corresponding projection expression.

### 3.1. Projection creates new data without modifying source elements

Suppose each Customer has name and age. Projection:

~~~text
customers.![name]
~~~

creates a list of names. It does not remove age from Customer, nor does it modify the source objects.

Similarly, projection:

~~~text
orders.![total * 1.1]
~~~

computes a new value for each order. The expression does not automatically assign the result back to the total property.

If you need to change an object's property, that is a property write operation via an API or appropriate assignment expression; projection only produces results from the iterated elements.

## 4. Combining selection then projection

When you want to filter a collection first and then take only part of the data from the remaining elements, chain the two operators:

~~~text
collection.?[condition].![projectionExpression]
~~~

Example:

~~~text
orders.?[status == 'PAID'].![total]
~~~

SpEL executes in order:

1. Read the orders collection.
2. Selection evaluates status == 'PAID' on each order.
3. Keep the orders matching the condition.
4. Projection evaluates total on each selected order.
5. Return a List of total values.

Another example:

~~~text
customers.?[active and age >= 18].![name]
~~~

The expression retrieves only the names of customers who are active and aged 18 or older.

If no elements match the condition, selection produces an empty collection and projection on an empty collection also yields an empty result. The application can handle this result as a list with zero elements.

## 5. Combining projection then selection

You can apply projection first and selection afterward:

~~~text
collection.![projectionExpression].?[condition]
~~~

In this case, selection operates on the values produced by projection rather than on the original source objects.

For example, extracting scores and keeping only scores of 80 or above:

~~~text
students.![score].?[#this >= 80]
~~~

This order differs from:

~~~text
students.?[score >= 80].![score]
~~~

The first expression projects each Student into a score value and then filters numeric values. The second expression filters Students by score and then projects the remaining Students into score.

If you only need a list of passing scores, both expressions may produce similar values. However, if you need to use additional properties of Student in the filter condition, selection before projection preserves the original objects so the condition can access those properties.

Example:

~~~text
students.?[score >= 80 and active].![name]
~~~

This form is clearer if the requirement is to filter by both score and active, and then return name.

## 6. Java example: filtering orders then retrieving totals

Create a simple Order class:

~~~java
public class Order {
    private final String code;
    private final String status;
    private final BigDecimal total;

    public Order(String code, String status, BigDecimal total) {
        this.code = code;
        this.status = status;
        this.total = total;
    }

    public String getCode() {
        return code;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

Create an object containing the collection:

~~~java
public class OrderReport {
    private final List<Order> orders;

    public OrderReport(List<Order> orders) {
        this.orders = orders;
    }

    public List<Order> getOrders() {
        return orders;
    }
}
~~~

Prepare the data and evaluate the expression:

~~~java
List<Order> orders = Arrays.asList(
        new Order("A-100", "PAID", new BigDecimal("120.00")),
        new Order("A-101", "PENDING", new BigDecimal("80.00")),
        new Order("A-102", "PAID", new BigDecimal("250.00"))
);

OrderReport report = new OrderReport(orders);

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        "orders.?[status == 'PAID'].![total]"
);

List<?> paidTotals = expression.getValue(report, List.class);
~~~

The result is a list containing 120.00 and 250.00. Order A-101 does not appear because its status is PENDING.

If the application wants order codes instead of totals, just change the projection expression:

~~~text
orders.?[status == 'PAID'].![code]
~~~

Selection stays the same; projection decides which data field is returned.

## 7. Java example: filtering with multiple conditions then creating result objects

Projection does not only extract a single property. It can produce another result structure, such as an inline map for each element:

~~~text
orders.?[status == 'PAID'].![{'code': code, 'amount': total}]
~~~

The result is a List of Maps. Each map contains code and amount for a paid order.

You can use this structure to produce data for reporting or pass it to another processing layer:

~~~java
Expression expression = parser.parseExpression(
        "orders.?[status == 'PAID']."
        + "![{'code': code, 'amount': total}]"
);

List<?> rows = expression.getValue(report, List.class);
~~~

Each element of rows is a Map. When receiving the data, use List<?> and check each element's type if the expression structure may change.

Projection can also compute values:

~~~text
orders.?[status == 'PAID'].![total * 1.1]
~~~

The expression computes the total multiplied by 1.1 for each selected order. This is only a computed value in the result, without updating total on Order.

## 8. Selection and projection on Map

SpEL also supports selection on Map. When selection processes a Map, the condition is evaluated on each Map.Entry. You can access key and value of the current entry.

Example:

~~~text
scores.?[value >= 80]
~~~

The expression retains entries whose value is 80 or above. The result of selection on a Map is still a Map, preserving the keys and values of the selected entries.

Projection on a Map processes each entry and creates a result List:

~~~text
scores.![key]
scores.![value]
scores.![key + ':' + value]
~~~

These expressions respectively create a list of keys, a list of values, or a list of strings combining key and value.

You can combine selection and projection:

~~~text
scores.?[value >= 80].![key]
~~~

The result is a list of keys for entries with scores of 80 or above.

Java example:

~~~java
Map<String, Integer> scores = new LinkedHashMap<>();
scores.put("An", 92);
scores.put("Binh", 75);
scores.put("Chi", 86);

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("scores", scores);

Expression expression = parser.parseExpression(
        "#scores.?[value >= 80].![key]"
);

List<?> qualifiedNames = expression.getValue(context, List.class);
~~~

With the data above, qualifiedNames contains An and Chi. Using LinkedHashMap keeps insertion order during iteration in the example.

## 9. Results and data types when combining the two operations

The result type depends on the input collection and the type of selection/projection used.

| Expression | Result |
|---|---|
| list.?[condition] | List of source elements matching the condition |
| list.^[condition] | First source element matching the condition, or null |
| list.$[condition] | Last source element matching the condition, or null |
| list.![expression] | List of projected values |
| list.?[condition].![expression] | List of values projected from selected elements |
| map.?[condition] | Map retaining entries matching the condition |
| map.![expression] | List of projection results on each entry |
| map.?[condition].![expression] | List of projection results from selected entries |

If the input is an empty collection, selection keeps zero elements and projection produces an empty List. If the input is null, regular selection or projection can fail during evaluation; use safe navigation when data may be null.

Selection and projection do not guarantee generic types such as List<String> at runtime. In Java, receive List<?> first and then check or convert elements if a specific type is required.

## 10. Null handling and safe navigation

A collection may be null, or a property accessed in the selection condition may be null. Distinguish between the two situations.

**Null input collection:** safe navigation can prevent executing selection or projection on a null collection.

~~~text
orders?.?[status == 'PAID']
orders?.![total]
~~~

If orders is null, the safe navigation expression returns null instead of trying to iterate over the collection.

**Null element property:** safe navigation can be used when accessing nested properties. Example:

~~~text
customers.?[address?.city == 'Hanoi'].![name]
~~~

The expression uses safe navigation when reading city from address. Clearly define how nulls should be handled according to business requirements; a null value should not be assumed by default to satisfy a condition.

You can combine safe navigation on both selection and projection:

~~~text
orders?.?[status == 'PAID']?.![total]
~~~

The result can be null if the root collection is null, or a List if the collection exists. Therefore, Java code receiving the result should check for null before iterating.

## 11. Selection variants when combining with projection

First and last selection can be combined with projection if you want to extract one value from the selected element:

~~~text
orders.^[status == 'PAID']?.total
orders.$[status == 'PAID']?.total
~~~

These expressions get the total of the first or last PAID order. If there is no matching order, the selection result is null; safe navigation ?.total avoids accessing a property on null.

If you need a list of totals for all paid orders, use:

~~~text
orders.?[status == 'PAID'].![total]
~~~

Choose the operator based on the shape of result you need: a single element, a single property, or a new collection.

## 12. Common mistakes

| Error | Cause | How to handle |
|---|---|---|
| Using .![] when wanting to filter | Projection transforms every element and does not exclude elements by condition. | Use .?[] for selection. |
| Using .?[] when wanting only one property | Selection retains the source objects. | Chain .![] to project the needed property. |
| Reversing selection and projection order | A condition after projection operates on the new values, no longer the original source objects. | Filter first if the condition needs multiple properties of the element. |
| Forgetting #this in expressions needing explicit reference | Can cause confusion about the active object in nested expressions. | Use #this.property when context needs to be explicit. |
| Using .^[...] but expecting a List | First selection returns a single element or null. | Use .?[...] if a collection is needed. |
| Selection on Map with wrong key/value access | The active element is Map.Entry. | Use key and value of the entry. |
| Accessing a property on a null selection result | No matching element was found. | Use safe navigation or null checks. |
| Input collection may be null | Selection/projection can fail when iterating null. | Use safe navigation and handle null results in Java. |
| Casting result to List<T> without checking | Generic type is not verified by List.class alone. | Receive List<?> and validate each element. |
| Thinking projection modifies source objects | Projection only creates results from expressions; it does not assign properties back. | Use a separate write operation if data updates are needed. |

## 13. How to structure readable expressions

For long expressions, break them into meaningful parts:

~~~text
orders
    .?[status == 'PAID' and total >= 100]
    .![{'code': code, 'amount': total}]
~~~

In Java code, you can place the expression across multiple lines in concatenated strings or store it in separate configuration. Give variables and properties meaningful names so selection conditions and projection expressions stay easy to understand.

A few practical guidelines:

1. Selection before projection when filtering depends on properties of the source object.
2. Projection before selection when the filter condition applies to transformed values.
3. Use parentheses when a condition expression has multiple logical operators.
4. Use #this to clarify the active element in nested expressions.
5. Handle nulls for collections and nested properties.
6. Use a general return type and validate element types at the Java boundary when needed.
7. Split complex expressions into variables or testable processing steps if they become hard to read.

## 14. Key takeaways

- Selection uses .?[condition] to keep matching elements.
- .^[condition] gets the first matching element; .$[condition] gets the last matching element.
- Projection uses .![expression] to produce a List from the expression results on each element.
- Selection then projection has the form collection.?[condition].![expression].
- Projection then selection filters on transformed values, so its semantics can differ.
- Selection on a Map retains matching entries; projection on a Map creates a result List.
- Safe navigation is helpful when a collection or property can be null.
- Selection/projection produces new results; projection does not automatically modify properties of source elements.
- Check the result type and null before using it in Java code.
