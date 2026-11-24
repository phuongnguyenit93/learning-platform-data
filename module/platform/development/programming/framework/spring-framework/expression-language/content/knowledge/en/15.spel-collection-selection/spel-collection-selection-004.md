# Selection returns a result list

SpEL provides the selection operator to filter elements of a collection based on a condition. When the source is a List, selection returns a new List containing the elements that satisfy the predicate. This notation is useful when you need to select open orders, active users, line items with quantity greater than one, or any subset of existing data.

Selection only decides which elements are kept. It does not transform each element like projection, nor does it automatically sort or modify the original data. Clearly understanding that the result is a new List, how the predicate is evaluated, and the scope of #this makes expressions more predictable.

## 1. Selection syntax on List

General selection syntax:

~~~text
collection.?[selectionExpression]
~~~

The dot before the operator indicates that selection is performed on the collection. The part inside square brackets is the condition evaluated for each element. Only elements for which the condition is true are placed into the result.

Example:

~~~text
orders.?[status == 'PAID']
users.?[active == true]
products.?[price > 100]
numbers.?[#this > 10]
~~~

If orders is a List of orders, the first expression returns a List consisting of orders whose status is PAID. If no element matches, the result is an empty List.

Java example:

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

In the example, #orders retrieves the List from the context variable. Selection iterates over each element, checks the status property, and puts matching orders into the result List.

## 2. Predicate is evaluated on each element

The expression inside square brackets is the predicate. SpEL evaluates the predicate with each element as the current object.

With a List of objects, properties can be accessed directly:

~~~text
#orders.?[total >= 100]
#users.?[enabled and verified]
#products.?[category == 'BOOK']
~~~

Inside the predicate, property names such as total, enabled, or category are resolved on the element being examined. There is no need to repeat the collection path in every condition.

For example, if an element is an Order, the expression total >= 100 is evaluated on the current Order. If the next element has a total less than 100, it is not included in the result.

The predicate should return a clear Boolean value. Write conditions specifically enough so that readers know the exact criteria used to select which elements are retained.

## 3. Roles of #this and #root

SpEL provides two useful references when selection is iterating over a collection:

- #this points to the current element that the predicate is checking.
- #root points to the root object of the entire evaluation pass.

Example:

~~~text
#orders.?[#this.total >= 100]
~~~

Here #this is each Order in the List. This explicit style is useful when the predicate has multiple properties or when you need to distinguish the current element from another object.

Suppose the root object is a Customer with a list of orders and a customer ID:

~~~text
orders.?[#this.customerId == #root.id]
~~~

In the predicate, #this is each order; #root remains the original Customer. As a result, a child collection can be filtered based on data from the root object.

When selections are nested, #this changes according to the collection being processed at the current level. Use #root when you need to reference back to the root object, especially if multiple collection levels share property names.

## 4. Selection result is a new List

With a List input, the .?[...] operator returns a List containing the matching elements. The result is a new collection; selection does not remove non-matching elements from the original List.

Example:

~~~java
List<Integer> source = List.of(1, 2, 3, 4, 5);

context.setVariable("numbers", source);

Expression expression =
        parser.parseExpression("#numbers.?[#this % 2 == 0]");

List<?> evenNumbers = expression.getValue(context, List.class);

System.out.println(evenNumbers); // [2, 4]
System.out.println(source);      // [1, 2, 3, 4, 5]
~~~

The source List keeps its elements unchanged. Selection only creates a result set for the expression or Java code to use next.

Elements are kept in the iteration order of the source List. If the source contains the same object multiple times and each occurrence satisfies the predicate, those occurrences are still retained in the result. Selection does not automatically deduplicate elements.

The result holds references to the selected elements. If an element is a mutable object, changing an object's property through that reference can still affect the original object. Creating a new result List is not equivalent to deep-copying the elements.

## 5. No matching elements

If no element satisfies the condition, selection on a List returns an empty List:

~~~text
#orders.?[status == 'CANCELLED']
~~~

Do not assume the result is null just because there are no matching results. An empty List is still a valid collection and can be used to check size, isEmpty, or be iterated over with zero elements.

Example:

~~~java
Expression expression = parser.parseExpression(
        "#orders.?[status == 'CANCELLED']"
);

List<?> cancelled = expression.getValue(context, List.class);

if (cancelled.isEmpty()) {
    System.out.println("No cancelled orders");
}
~~~

If the application needs a fallback value when no elements are found, handle it explicitly after selection or use an additional condition in the expression. Do not confuse an empty List with a null source collection.

## 6. Combining multiple conditions in a predicate

A predicate can combine comparison operators and logical operators. Example:

~~~text
#orders.?[status == 'PAID' and total >= 100]
#users.?[active and (role == 'ADMIN' or role == 'EDITOR')]
#products.?[stock > 0 and price <= #maxPrice]
~~~

Parentheses can be used to clarify groups of conditions. AND and OR short-circuit: if the left side of AND is false, the rest does not need evaluation; if the left side of OR is true, the right side is skipped.

This is useful when checking for null before deep access:

~~~text
#users.?[#this.profile != null and #this.profile.enabled]
~~~

If profile is null, the right side is not evaluated. This prevents accessing enabled on a null object.

When a predicate has multiple conditions, prefer placing simple checks that can decide the result early on the left. That both clarifies intent and avoids performing unnecessary accesses.

## 7. Accessing nested properties in a predicate

You can filter by properties at multiple object levels:

~~~text
#orders.?[customer.address.city == 'Da Nang']
#employees.?[department.name == 'Engineering']
#products.?[supplier.active == true]
~~~

Each property path is evaluated on the current element. If an intermediate object is null, accessing the next property can cause an error.

Check intermediate objects before reading deeply:

~~~text
#employees.?[department != null and department.name == 'Engineering']
~~~

Due to short-circuit AND, if department is null then department.name is not accessed.

With complex object graphs, you should prepare data with clear state or use a DTO dedicated to expressions. The more getters and nested relationships a predicate depends on, the harder it is to predict performance and runtime errors.

## 8. Nested selection

An element of a List can contain another List. Selection can be performed at multiple levels to filter the outer collection and then filter the child collection.

For example, each Order has a list of lines:

~~~text
#orders.?[status == 'PAID'].![lines.?[quantity > 1]]
~~~

The expression above first selects paid orders, then projects each order into a List of lines with quantity greater than one. The result here is a collection of child Lists because projection produces one value for each selected order.

If the goal is only to select orders that have at least one matching line, you can use an anyMatch method or a clearly named business method if the object provides one. Avoid writing an overly long nested expression when a plain method makes the intent easier to understand.

Direct selection on a sublist when each element has its own collection can be performed inside a predicate using an appropriate method or property. Check the result type and the scope of #this at each level so you do not confuse an order element with a line-item element.

## 9. Distinguishing selection from projection

Selection and projection both use bracket syntax, but their purposes differ:

| Operator | Syntax | Effect | Result |
|---|---|---|---|
| Selection | .?[condition] | Keeps elements that satisfy the condition | A subset List for a List source |
| Projection | .![expression] | Transforms each element into a value | A List of projected values |

Selection example:

~~~text
#orders.?[status == 'PAID']
~~~

The result still contains the paid Orders.

Projection example:

~~~text
#orders.![orderNumber]
~~~

The result is a List of orderNumbers, no longer a List of Orders.

You can combine both operations:

~~~text
#orders.?[status == 'PAID'].![orderNumber]
~~~

First filter the paid Orders, then retrieve the order number of each order. Choose selection when you want to keep matching objects, and projection when you want to create a new collection of values from them.

## 10. Selection on Map has a different result

Although this lesson focuses on List, remember that selection does not always return a List. When the source is a Map, selection retains the matching entries and returns a result Map.

Example:

~~~text
#scores.?[value >= 80]
~~~

In selection on a Map, the predicate is evaluated on an entry; you can access the entry's key and value. Matching key-value pairs are preserved in the result Map.

Therefore, check the source collection type before relying on the result type. For a List, the result is a List; for a Map, the result is a Map. If Java code requires a specific type, use the appropriate getValue overload or convert explicitly after evaluation.

## 11. First and last selection do not return a List

Besides standard selection, SpEL also has forms that get the first or last matching element:

~~~text
#orders.^[status == 'PAID']
#orders.$[status == 'PAID']
~~~

- .^[...] selects the first element satisfying the predicate.
- .$[...] selects the last element satisfying the predicate.

These two operators return a single matching element, not a result List. If no element matches, the result may be null.

Comparison:

~~~text
#orders.?[status == 'PAID']
#orders.^[status == 'PAID']
#orders.$[status == 'PAID']
~~~

The first expression gets all paid orders. The second gets the first matching order. The third gets the last matching order in the collection's iteration order.

If the goal is to display multiple results or continue filtering a collection, use .?[...]. If you only need the first/last element, use the corresponding operator and handle the not-found case.

## 12. Performance and side effects in predicates

Selection must check the predicate across iterated elements until the end of the collection. For a List with n elements, a simple filter usually needs to evaluate the predicate at most n times.

If a predicate calls an expensive method, accesses a lazy relationship, or performs I/O, the cost can increase significantly. Example:

~~~text
#orders.?[customer.loadRiskScore() > 5]
~~~

If there are many orders, the loadRiskScore method may be called many times. If the method queries a database or calls an external service, a short filter expression can trigger many expensive operations.

Prefer pure predicates that only read already-available data. If complex calculation is needed, prepare data beforehand or use a dedicated service/query. You should not place write operations, notifications, or state mutations inside a predicate because selection may invoke the predicate multiple times.

## 13. Controlling null and source collections

Two situations need to be distinguished:

- Source collection is null: there is no collection to select from; the expression may fail during evaluation.
- Source collection exists but has no matching elements: selection returns an empty List.

Ensure the input collection is initialized before evaluation. If data comes from a request or database, you can normalize null to an empty collection in Java before placing it into the context.

For null elements inside a List, the predicate should check #this before accessing properties:

~~~text
#items.?[#this != null and #this.active]
~~~

Short-circuit AND ensures #this.active is not evaluated when the current element is null.

Do not use a selection expression to mask unstructured input data. Define the data contract clearly and handle errors in the appropriate place.

## 14. Complete example with order data

Suppose each Order has orderNumber, status, and total. The goal is to retrieve paid orders with a total amount of 100 or more.

~~~java
ExpressionParser parser = new SpelExpressionParser();

List<Order> orders = loadOrders();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("orders", orders);
context.setVariable("minimumTotal", new BigDecimal("100.00"));

Expression expression = parser.parseExpression(
        "#orders.?[status == 'PAID' and total >= #minimumTotal]"
);

List<?> result = expression.getValue(context, List.class);

result.forEach(System.out::println);
~~~

The expression retains Orders that satisfy both conditions. The minimumTotal variable separates the configuration threshold from the expression string, so the threshold can be changed per environment or request without regenerating the rule text.

If you need to extract order numbers from the result, you can chain projection:

~~~text
#orders.?[status == 'PAID' and total >= #minimumTotal].![orderNumber]
~~~

The result is now a List of order numbers. Selection performs the filtering; projection transforms the filtered elements into the needed values.

## 15. Common mistakes

| Symptom | Common cause | Resolution |
|---|---|---|
| Empty result even though source has data | Predicate has wrong property name or overly strict condition | Test each condition on a single element |
| Null result instead of empty List | Source collection is null or using first/last selection | Distinguish null source from no matching elements |
| Error reading nested property | Intermediate object is null | Add a null check with short-circuit AND |
| Predicate reads wrong object | Confusing #this with #root | Clearly identify current element and root object |
| Result contains duplicate elements | Source List contains the same element multiple times | Use distinct in Java if business logic requires deduplication |
| Result is a Map instead of a List | Selection source is a Map | Check the input collection type |
| Result contains objects instead of properties | Using selection when element transformation was intended | Use projection .![...] |
| Selection runs slowly | Predicate calls expensive methods or getters | Prepare data beforehand and keep predicates pure |

## 16. Key takeaways

Selection on a List uses the .?[predicate] syntax and returns a new List consisting of elements that satisfy the condition. The predicate is evaluated on each element; #this is the current element, while #root is the root object of the evaluation pass. If no element matches, the result is an empty List and the source List is not filtered in place.

Selection preserves the selected objects, whereas projection .![...] creates a List of transformed values. The first and last selection operators .^[...] and .$[...] return a single element instead of a List. Check for null, keep predicates pure, verify the source collection type, and use the right operator for the result shape the application needs.