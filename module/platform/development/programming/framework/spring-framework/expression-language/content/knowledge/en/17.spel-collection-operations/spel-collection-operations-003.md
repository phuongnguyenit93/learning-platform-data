# Querying the first, last, and matching elements

SpEL provides three selection operators to find elements in a collection based on a condition: .?[...] retrieves all matching elements, .^[...] retrieves the first matching element, and .$[...] retrieves the last matching element. All three evaluate a predicate on the collection elements, but the shape of the result and the number of returned elements differ.

These operators are useful when you need to find the first pending order, the last in-stock product, all active users, or the first entry in a Map that satisfies a condition. Choosing the right operator makes the expression clearly express the query intent and avoids filtering the entire collection in Java just to obtain a single result.

## 1. The three selection forms in SpEL

General syntax:

~~~text
collection.?[condition]
collection.^[condition]
collection.$[condition]
~~~

Meaning:

| Operator | Purpose | Result |
|---|---|---|
| .?[condition] | Retrieve all elements satisfying the condition | Result collection |
| .^[condition] | Retrieve the first element satisfying the condition | One element or null |
| .$[condition] | Retrieve the last element satisfying the condition | One element or null |

The predicate sits inside square brackets. SpEL evaluates the condition on each element under consideration. For a List, element order in the result follows the iteration order of the source List.

Example with a list of orders:

~~~text
#orders.?[status == 'PAID']
#orders.^[status == 'PAID']
#orders.$[status == 'PAID']
~~~

The first expression returns all paid orders. The second expression returns the first paid order according to List order. The third expression returns the last paid order according to List order.

## 2. Retrieving all matching elements with .?[...]

Normal selection uses .?[...]. It iterates over the collection and keeps every element whose predicate is true.

~~~java
ExpressionParser parser = new SpelExpressionParser();

List<Order> orders = List.of(
        new Order("A-01", "PAID"),
        new Order("A-02", "PENDING"),
        new Order("A-03", "PAID")
);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("orders", orders);

Expression expression = parser.parseExpression(
        "#orders.?[status == 'PAID']"
);

List<?> paidOrders = expression.getValue(context, List.class);

System.out.println(paidOrders.size()); // 2
~~~

The result contains both orders A-01 and A-03. The source collection is not filtered in place; SpEL creates a new result collection containing the matching elements.

Use .?[...] when you need to display a list of results, continue processing multiple elements, or obtain the count of elements satisfying the condition. If only one result is needed, consider the first or last selection operator to express intent directly.

## 3. Retrieving the first matching element with .^[...]

The .^[...] operator stops at the first element satisfying the predicate and returns that element itself:

~~~text
#orders.^[status == 'PAID']
~~~

If the List has the order A-01, A-02, A-03 and A-01 is a paid order, the expression returns A-01. Subsequent elements do not need to be checked once the first match is found.

Java example:

~~~java
Expression firstPaid = parser.parseExpression(
        "#orders.^[status == 'PAID']"
);

Order first = firstPaid.getValue(context, Order.class);

if (first != null) {
    System.out.println(first.getOrderNumber());
}
~~~

The result is not a List containing one element; it is the selected Order object. If no element matches, the result is null.

This operator is appropriate when the collection order already carries business meaning, such as processing priority order, display order, or a pre-sorted order. If you want the order with the earliest creation time, make sure the collection is already sorted by time before using .^[...]. Selection does not sort data automatically.

## 4. Retrieving the last matching element with .$[...]

The .$[...] operator retrieves the last element satisfying the predicate:

~~~text
#orders.$[status == 'PAID']
~~~

If orders A-01 and A-03 are both paid, the expression returns A-03 because it appears last in the List's iteration order.

Example:

~~~java
Expression lastPaid = parser.parseExpression(
        "#orders.$[status == 'PAID']"
);

Order last = lastPaid.getValue(context, Order.class);

if (last != null) {
    System.out.println(last.getOrderNumber());
}
~~~

The result is also a single object or null. It is not a result collection.

Use .$[...] when you need the last matching element in the existing order. If the goal is to get the largest, newest, or highest-priority value, do not assume the last element satisfies that. Sort the collection by the desired criterion first or use a computation suited to the goal.

## 5. The predicate and the current object

A predicate is a Boolean expression evaluated for each element. During selection, #this represents the current element.

~~~text
#orders.^[#this.total >= 100]
#users.$[#this.active]
#products.?[#this.stock > 0]
~~~

Properties can be accessed directly without writing #this if there is no ambiguity:

~~~text
#orders.^[total >= 100]
~~~

When the predicate needs to compare an element against data outside the collection, you can use #root or context variables:

~~~text
#orders.^[total >= #minimumTotal]
~~~

Example:

~~~java
context.setVariable("minimumTotal", new BigDecimal("100.00"));

Expression expression = parser.parseExpression(
        "#orders.^[total >= #minimumTotal]"
);

Order qualifyingOrder = expression.getValue(context, Order.class);
~~~

Here total is read on the current Order, while #minimumTotal is taken from a context variable. Use meaningful variable names so readers recognize the search criterion.

## 6. Result when no element is found

The three operators represent a non-matching result differently:

- .?[...] returns an empty collection if no element matches.
- .^[...] returns null if no element matches.
- .$[...] returns null if no element matches.

Example:

~~~text
#orders.?[status == 'CANCELLED']
#orders.^[status == 'CANCELLED']
#orders.$[status == 'CANCELLED']
~~~

If there are no cancelled orders, the first expression returns an empty List; the latter two return null.

This is an important difference when Java code receives the result. With select-all, you can check isEmpty(). With first/last selection, you need to check for null before invoking methods or accessing properties.

Example:

~~~java
Order firstCancelled = parser.parseExpression(
        "#orders.^[status == 'CANCELLED']"
).getValue(context, Order.class);

if (firstCancelled == null) {
    System.out.println("No cancelled order found");
}
~~~

Do not confuse a null source collection with a valid collection that has no matching elements. If the `#orders` variable is null, there is no collection to select from; the expression may raise an error during evaluation. Normalize or check the data source before querying.

## 7. Distinguishing first/last selection from index access

Index access retrieves the element at a fixed position:

~~~text
#orders[0]
#orders[#orders.size() - 1]
~~~

First/last selection finds the first/last element satisfying a condition:

~~~text
#orders.^[status == 'PAID']
#orders.$[status == 'PAID']
~~~

The two groups of syntax serve different purposes:

| Need | Syntax |
|---|---|
| Element at position 0 | #orders[0] |
| Last element by index | #orders[#orders.size() - 1] |
| First element with status PAID | #orders.^[status == 'PAID'] |
| Last element with status PAID | #orders.$[status == 'PAID'] |
| All elements with status PAID | #orders.?[status == 'PAID'] |

Use an indexer when the position is known. Use selection when you want to search by condition. You should not retrieve the first or last element by index and then check a condition if the real goal is to find the first/last element satisfying a predicate.

## 8. Collection order determines the first and last results

First and last selection depend on the iteration order of the collection. With a List, this order is usually clear because List preserves element order.

With a Set or other collection, order depends on the implementation. HashSet does not guarantee a stable iteration order. LinkedHashSet preserves insertion order; TreeSet iterates in comparator order. If you use .^[...] or .$[...] on a collection without a defined order, the result may not be stable for business logic.

Example:

~~~java
Set<String> states = new LinkedHashSet<>();
states.add("PENDING");
states.add("PAID");
states.add("CANCELLED");

context.setVariable("states", states);
~~~

With LinkedHashSet, iteration follows insertion order. But if replaced with HashSet, you should not rely on a specific element always being the first or last result.

If order matters, supply a sorted List or a collection with a deterministic order. Selection does not add any sorting rules to the source.

## 9. Selection on a Map

When the source is a Map, the predicate is evaluated on its entries. Inside the predicate, key and value of the entry can be accessed.

Example:

~~~java
Map<String, Integer> scores = new LinkedHashMap<>();
scores.put("Lan", 92);
scores.put("Minh", 75);
scores.put("An", 88);

context.setVariable("scores", scores);
~~~

Retrieve all entries with a score of 80 or higher:

~~~text
#scores.?[value >= 80]
~~~

Selection on a Map returns a Map containing the matching entries. Original keys and values are preserved.

You can find the first or last entry satisfying the condition:

~~~text
#scores.^[value >= 80]
#scores.$[value >= 80]
~~~

With first/last selection on a Map, the result is the selected entry, not a Map containing the whole result. You can read key and value from that entry. First/last order depends on the Map's iteration order; if stable results are needed, use an ordered implementation such as LinkedHashMap or TreeMap with an appropriate comparator.

Do not confuse value in a Map.Entry predicate with a value property on a domain object. In Map selection, key and value are the two components of the entry being evaluated.

## 10. Combining selection with projection

Selection preserves matching elements. Projection .![...] transforms each element into another value. You can combine them to filter first and then extract only the needed data.

~~~text
#orders.?[status == 'PAID'].![orderNumber]
~~~

The expression above retrieves all paid orders and then creates a List of order numbers.

If you only need the first order number matching the condition, you can access a property or invoke a method on the first selection result:

~~~text
#orders.^[status == 'PAID'].orderNumber
~~~

If no element is found, the first selection result is null; subsequent property access needs to be guarded or handled separately. You can retrieve the object in Java first and then read the property for clear null control.

For a Map, selection returns a Map or an entry depending on the operator; determine the result type before chaining further property access, indexers, or method calls.

## 11. Combining multiple conditions in a predicate

A predicate can contain multiple conditions combined with AND, OR, and NOT:

~~~text
#orders.^[status == 'PAID' and total >= 100]
#users.$[active and (role == 'ADMIN' or role == 'EDITOR')]
#products.?[stock > 0 and price <= #maxPrice]
~~~

Use parentheses to express condition grouping. AND short-circuits when the left side is false; OR short-circuits when the left side is true. You can leverage this to check for null before accessing nested properties:

~~~text
#orders.^[customer != null and customer.active]
~~~

If customer is null, the customer.active part is not evaluated.

Predicates should focus on selection conditions. Avoid putting methods with side effects such as writing data, sending notifications, or mutating state inside a predicate, because the number of calls depends on the collection and the operator used.

## 12. Performance and number of elements checked

Select-all .?[...] needs to iterate through the collection to determine all matching elements. For n elements, the predicate is typically evaluated n times.

First selection .^[...] can stop as soon as it finds the first matching element. If the first element satisfies the condition, subsequent elements do not need to be checked.

Last selection .$[...] needs to determine the last matching element, so normally it must continue iterating to the end of the collection. If the collection is large and only the last element by some criterion is needed, consider sorting or querying the data at the source layer instead of always passing the entire collection into SpEL.

Actual cost also depends on the predicate. A simple property-reading condition is usually cheaper than a method call that runs a database query or complex calculation. Prepare data ahead of time, avoid unexpected lazy loading, and keep predicates pure.

## 13. Null in elements and nested properties

If the collection can contain null elements, check #this before accessing properties:

~~~text
#items.^[#this != null and #this.active]
#items.$[#this != null and #this.score >= 80]
~~~

Short-circuit AND ensures the right-hand side does not execute when the current element is null.

For nested properties:

~~~text
#orders.^[customer != null and customer.address != null and customer.address.city == 'Da Nang']
~~~

Each condition verifies the intermediate object before accessing deeper. This approach helps avoid null errors during selection.

If the source collection is null, the predicate cannot start running. Check the source or normalize null to an empty collection before placing it into the EvaluationContext.

## 14. Complete query example

Suppose you need to find the first order that is paid and has a total meeting a threshold. If no matching order exists, the application needs to display a message.

~~~java
ExpressionParser parser = new SpelExpressionParser();

List<Order> orders = loadOrders();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("orders", orders);
context.setVariable("minimumTotal", new BigDecimal("100.00"));

Expression expression = parser.parseExpression(
        "#orders.^[status == 'PAID' and total >= #minimumTotal]"
);

Order selected = expression.getValue(context, Order.class);

if (selected == null) {
    System.out.println("No matching order found");
} else {
    System.out.println(selected.getOrderNumber());
}
~~~

If all matching orders are needed, switch to .?[...] and receive a List. If the last matching order in collection order is needed, use .$[...]. The predicate logic can stay the same; only the selection operator and result type change.

When business logic asks for "newest", make sure orders is already sorted by time ascending before using .$[...], or query directly from the database with ORDER BY and a result limit. The last operator only means last in the existing iteration order.

## 15. Common mistakes

| Symptom | Common cause | Solution |
|---|---|---|
| Receiving a List when only one object is needed | Using .?[...] instead of .^[...] or .$[...] | Choose the operator based on the result shape |
| Result is null even though the collection has data | No element satisfies the predicate | Check the condition against each element |
| Wrong first/last element retrieved | Collection is not sorted by business criteria | Sort the source before selection |
| Result changes across runs | Source is a Set/Map with unstable iteration order | Use a collection with deterministic order |
| Accessing a property on null | Element or nested object is null | Guard against null using short-circuit AND |
| Confusing key/value in Map | Predicate is evaluating Map.Entry | Use key and value appropriately for the context |
| Slow selection | Predicate calls expensive methods or getters | Prepare data beforehand and keep predicates pure |
| Accessing a property after first selection fails | No matching element so the result is null | Check for null before reading properties |

## 16. Key takeaways

Use .?[...] to retrieve all elements satisfying a condition, .^[...] to retrieve the first element, and .$[...] to retrieve the last element. For a List, the first/last result is a single element or null; select-all returns a List, which may be empty. For a Map, select-all returns a Map, whereas first/last selection returns the selected entry.

First and last results always depend on the collection's iteration order. Selection does not sort data automatically and does not modify the source collection. Clearly determine the collection type, order, not-found case, and result type before continuing to use the result.

Keep predicates simple, check for null before deep access, and avoid side effects in conditions. When business logic requires stable results, sort or query data at the appropriate layer before evaluating SpEL.