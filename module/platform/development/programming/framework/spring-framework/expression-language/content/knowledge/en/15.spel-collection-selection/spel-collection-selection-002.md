# Collection selection: filtering elements by condition on #this

## Objectives

Collection selection in Spring Expression Language (SpEL) allows filtering a collection by a condition. The selection expression is evaluated sequentially on each element, and the **#this** variable represents the element currently being examined. The result contains the elements that satisfy the condition.

Selection is useful when you need to retrieve open orders, members belonging to a group, products exceeding a price threshold, or Map entries meeting a rule. It helps express filtering close to the data, though you still need to clearly understand collection types, iteration order, and null handling.

After this lesson, you will be able to:

- Use the **.?[ ]** operator to filter all matching elements.
- Understand the role of **#this** in selection and distinguish it from **#root**.
- Use selection on List, array, Iterable, and Map.
- Select the first or last matching element using **.^[ ]** and **.$[ ]**.
- Combine selection with properties, variables, and logical conditions.
- Distinguish selection from projection and test edge cases.

## 1. Basic selection syntax

Syntax for filtering all elements:

~~~text
collection.?[selectionExpression]
~~~

Where:

- **collection** is an expression returning a collection or data structure supported by SpEL.
- **selectionExpression** is the condition evaluated for each element.
- **#this** represents the current element during that condition evaluation.

Example:

~~~text
#root.orders.?[#this.total >= 100]
~~~

The expression retrieves the list of orders from the root object, then retains orders with a total greater than or equal to 100.

If an order has a total of 80, the condition returns false and that order does not appear in the result. If the total is 120, the condition returns true and the order is retained.

Selection does not modify the source collection. It creates a new filtered result containing the selected elements.

## 2. Understanding #this and #root properly

In SpEL, **#root** represents the root object passed in when evaluating the expression. **#this** represents the current object in the evaluation context at a specific point in time.

During selection, SpEL loops over the elements and evaluates the condition on each element. Therefore, #this changes with the element being examined, while #root still points to the original root object.

Suppose the root object is a store with a list of products:

~~~java
public class Product {
    private String name;
    private BigDecimal price;
    private boolean available;

    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
    public boolean isAvailable() { return available; }
}

public class Store {
    private List<Product> products;

    public List<Product> getProducts() { return products; }
}
~~~

You can filter products that are in stock and priced under 500:

~~~text
#root.products.?[#this.available and #this.price < 500]
~~~

In the condition:

- **#root.products** accesses the product list from Store.
- **#this.available** reads the status of the current product.
- **#this.price** reads the price of the current product itself.

It can be written more concisely by using the current element's properties directly:

~~~text
#root.products.?[available and price < 500]
~~~

Both forms use the current element as the context of the condition. Writing #this explicitly is useful when the expression has multiple nested levels or when you want the reader to immediately recognize that the condition is being applied to each element.

### Using the root object in the condition

A selection condition can reference both the current element and data on the root:

~~~text
#root.orders.?[#this.total >= #root.minimumTotal]
~~~

This example retains orders whose total meets the minimumTotal threshold of the root object. #this is the current Order; #root is still the object containing orders and minimumTotal.

If the threshold is passed via a variable in EvaluationContext, you can write:

~~~text
#root.orders.?[#this.total >= #minimum]
~~~

This approach separates configuration data from the expression and helps tests vary the threshold without having to build a different expression string.

## 3. Selection on List and Iterable

For a List or an Iterable supported by SpEL, selection returns a new List consisting of the elements that satisfy the condition. The order of selected elements follows the iteration order of the source collection.

Example:

~~~text
#root.members.?[#this.active]
~~~

The expression returns a list of members whose active is true.

Filtering by a String property:

~~~text
#root.members.?[#this.department == 'Engineering']
~~~

Filtering by multiple conditions:

~~~text
#root.members.?[#this.active and #this.score >= 80]
~~~

Use parentheses when you need to combine AND and OR to properly group conditions:

~~~text
#root.members.?[#this.active and (#this.role == 'ADMIN' or #this.role == 'REVIEWER')]
~~~

The selection condition should return a Boolean. If a property may be null, determine whether null should be treated as false, invalid data, or handled separately. Do not let a null property produce unexpected behavior.

### Filtering a list of numbers

If the collection contains numbers, #this is the current numeric value:

~~~text
#root.values.?[#this > 10]
~~~

The expression keeps values greater than 10. It can be combined with another condition:

~~~text
#root.values.?[#this >= 10 and #this <= 100]
~~~

The result is a new List containing numbers in the range from 10 to 100, inclusive of both endpoints.

## 4. Selection on array

SpEL also supports selection on arrays. The result is a List containing the selected elements.

Example:

~~~text
#root.scores.?[#this >= 70]
~~~

If scores is a numeric array, the expression returns a list of scores of 70 or above.

Do not confuse selection with index access:

- **scores[0]** gets a single element at position 0.
- **scores.?[#this >= 70]** filters all elements satisfying the condition.

If the array is null, standard selection cannot iterate over elements. Starting with Spring Framework 6.2, you can use null-safe selection when the target may be null; the syntax is covered in the null-handling section.

## 5. Selection on Map

For a Map, selection filters entries and returns a new Map containing the selected entries. Each entry has a key and a value. Inside the condition, **#this** represents the entry being examined; you can access the entry's key and value.

Example of a Map storing product prices by code:

~~~java
Map<String, BigDecimal> prices = new LinkedHashMap<>();
prices.put("PEN", new BigDecimal("5.00"));
prices.put("BOOK", new BigDecimal("120.00"));
prices.put("BAG", new BigDecimal("450.00"));
~~~

Filter entries with a price above 100:

~~~text
#root.prices.?[#this.value > 100]
~~~

The result retains the key/value pairs corresponding to BOOK and BAG.

You can filter by key:

~~~text
#root.prices.?[#this.key matches '[A-Z]{3}']
~~~

Or combine key and value:

~~~text
#root.prices.?[#this.key startsWith 'B' and #this.value >= 100]
~~~

For a Map, the result remains a Map to preserve the association between key and value. Iteration order depends on the type of Map used; if business logic requires a stable order, choose an ordered Map structure such as LinkedHashMap or TreeMap.

## 6. Selecting the first or last element

Besides retrieving all elements that satisfy a condition, SpEL has two specialized selection operators:

| Operator | Meaning |
|---|---|
| **.^[condition]** | Get the first matching element |
| **.$[condition]** | Get the last matching element |
| **.?[condition]** | Get all matching elements |

Example:

~~~text
#root.orders.^[#this.status == 'PAID']
~~~

The expression gets the first order with PAID status according to the collection's iteration order.

Get the last PAID order:

~~~text
#root.orders.$[#this.status == 'PAID']
~~~

Get all PAID orders:

~~~text
#root.orders.?[#this.status == 'PAID']
~~~

The first two operators are suitable when only a single result is needed. If no element satisfies the condition, first/last selection returns null. Therefore, handle the not-found case before continuing to access properties on the result.

For a List, the first/last order is the element order in the List. For a Map, the order depends on the entry iteration order of the Map implementation. You should not use first/last selection to represent newest/oldest semantics if the collection does not have a guaranteed order.

## 7. Combining selection with projection

Selection and projection both operate on collections, but they serve different purposes:

- **Selection .?[ ]** filters and keeps the selected elements intact.
- **Projection .![ ]** transforms each element into a different value.

Example of filtering available products and then getting their names:

~~~text
#root.products.?[#this.available].![#this.name]
~~~

The steps execute in order:

1. Selection retains products where available is true.
2. Projection runs on the resulting list.
3. Each product is transformed into its name value.
4. The final result is a list of product names.

You can write selection and projection on one line, but when expressions get long, extract them into named variables or expressions in the application to make them easier to read and test.

Another example:

~~~text
#root.orders.?[#this.total >= #minimum].![#this.id]
~~~

The expression filters orders meeting the threshold and then returns a list of their IDs.

Do not use projection if the goal is only filtering. If you write **.?[#this.active]**, the result still consists of the original objects; if you write **.![#this.name]**, the result consists of the names projected from the objects.

## 8. Handling null and empty collections

Selection requires an iterable target. If the target is null, a standard selection expression may raise an evaluation error.

Starting with Spring Framework 6.2, SpEL supports null-safe selection:

~~~text
#root.orders?.?[#this.status == 'PAID']
~~~

If orders is null, the expression returns null instead of attempting to iterate over the collection. If orders exists, SpEL performs selection as usual.

Null-safe syntax for first and last selection can also be used:

~~~text
#root.orders?.^[#this.status == 'PAID']
#root.orders?.$[#this.status == 'PAID']
~~~

Confirm your Spring Framework version before using these null-safe operators. They were added in Spring Framework 6.2.

An empty collection is different from a null collection:

- Selection on an empty collection returns an empty result collection.
- First/last selection on an empty collection finds no element and returns null.
- Selection on a null target requires null-safe selection if you want to receive null instead of an error.

For conditions with intermediate properties that may be null, handle each property individually:

~~~text
#root.orders.?[#this.customer?.active == true]
~~~

Here, safe navigation guards against a null customer on each Order. The active property must still exist and be readable when customer has a value.

## 9. Common errors and diagnostics

| Symptom | Possible cause | Resolution |
|---|---|---|
| Collection not found | Wrong property name or incorrect root object | Check the root type and property path |
| Error during selection on null | Target collection is null | Validate data or use version-appropriate null-safe selection |
| No elements in result | Condition matches no data | Check the predicate and input data |
| Condition fails when reading property | Current element lacks the property or intermediate property is null | Check element type and use safe navigation where appropriate |
| Confusing #root and #this | Condition reads the wrong object | Identify the root object and current element |
| Map selection returns unexpected result | Filtering wrong key/value or expecting List instead of Map | Check Map.Entry and result type |
| First/last returns null | No matching element | Handle the not-found case before further access |
| Result varies across environments | Different collection or iteration order | Define the source structure and ordering rules |

When a predicate is complex, test it on a single element first. Only then place the condition into selection to determine whether the error comes from a property, comparison, or collection traversal.

## 10. Testing selection

A test should verify the number of selected elements, content, and result order.

Example:

~~~java
@Test
void selectsActiveMembers() {
    ExpressionParser parser = new SpelExpressionParser();
    Expression expression =
        parser.parseExpression("#root.members.?[#this.active]");

    SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

    Team team = new Team(List.of(
        new Member("Lan", true),
        new Member("Minh", false),
        new Member("An", true)
    ));

    List<?> selected = expression.getValue(context, team, List.class);

    assertEquals(2, selected.size());
}
~~~

For each source type, prepare these cases:

| Case | What to verify |
|---|---|
| Every element matches | Result keeps all elements |
| No element matches | Empty result |
| Only the first element matches | Result is in the right order |
| Only the last element matches | Result is in the right order |
| Multiple elements match | No dropped or duplicated elements |
| Predicate has external variables | Variables are provided properly in context |
| Element property is null | Condition handles null per contract |
| Null collection | Error or null-safe behavior is defined |
| Empty collection | Selection returns an empty result |
| Map | Preserves key/value of selected entries |
| First/last not found | Null result is handled |

For a Map, verify both key and value and confirm the result type is Map. For a List, confirm that the order of selected elements follows the source order.

## 11. Best practices

- Use selection when the goal is filtering elements; use projection when the goal is transforming elements.
- Write clear conditions and prefer a few readable business conditions.
- Use #this to clearly indicate the element being examined in the predicate.
- Use #root when data from the root object is needed.
- Verify the element type and properties accessed by the predicate.
- Handle null explicitly; do not assume safe navigation fixes every error inside a predicate.
- Use ^ and $ when only the first or last element is needed, while also specifying the collection order.
- With Maps, understand that the selection result retains entries rather than returning only a list of values.
- Avoid calling methods with side effects inside a predicate because selection may evaluate the condition multiple times.
- Test empty collections, no matches, multiple matches, and null data.
- If the predicate is configured outside source code, parse and evaluate it with sample data before enabling it.

## 12. Review checklist

Before accepting a selection expression, check:

- [ ] Target is a collection/array/Map supported by SpEL.
- [ ] Predicate returns a Boolean matching the business semantics.
- [ ] #this accurately represents the current element.
- [ ] #root is used when data from the root object is needed.
- [ ] Element properties and data types have been identified.
- [ ] Map selection checks the correct key or value.
- [ ] Whether the expected result is List or Map has been determined.
- [ ] Source order is sufficiently stable if using first/last selection.
- [ ] Null collections and empty collections are handled separately.
- [ ] Safe navigation is supported by the running Spring version.
- [ ] Selection is clearly distinguished from projection.
- [ ] Tests exist for empty results, multiple elements, null, and Map.

## Conclusion

Collection selection in SpEL uses **.?[condition]** to filter elements, where **#this** is the current element and **#root** remains the original root object. Selection on List, array, and Iterable produces a list of selected elements; selection on Map retains the matching entries. Use **.^[ ]** or **.$[ ]** when only the first/last element in iteration order is needed. When combining with projection, null-safe selection, and external variables, clearly define the source type, null behavior, ordering, and result type so that expressions remain easy to understand and testable.
