# Combining selection and projection in a single expression

## Objectives

After this lesson, you can combine selection and projection in Spring Expression Language (SpEL) to filter a collection and then transform the matching elements into result data; understand the execution order and result type after each step; use the `#this` variable in the right scope; and apply operation chaining to List, arrays, Iterable, and Map. You will also know how to handle empty collections, null, nested elements, and situations where logic should be moved to Java.

## 1. Selection and projection solve two different tasks

SpEL provides two groups of operators that are often used together:

- **Selection** filters elements of a collection according to a condition.
- **Projection** evaluates an expression on each element to create a new result collection.

Selection typically uses the syntax:

~~~text
collection.?[condition]
~~~

Projection uses the syntax:

~~~text
collection.![expression]
~~~

For example, given a list of orders, you can filter the paid orders:

~~~text
#orders.?[status == 'PAID']
~~~

The result is still the order objects that satisfy the condition. If only the order IDs are needed, each order can be projected to its id property:

~~~text
#orders.![id]
~~~

The result is a list of IDs, no longer a list of Order objects.

Combining the two operations lets the expression perform a short pipeline: select the needed elements first, then extract the exact data that the next step needs.

## 2. Common pattern: filter first, project second

The common combined syntax:

~~~text
collection.?[condition].![projectionExpression]
~~~

For example:

~~~text
#orders.?[status == 'PAID'].![id]
~~~

SpEL executes in this order:

1. Iterate through the elements of `#orders`.
2. Evaluate `status == 'PAID'` on each order.
3. Create a collection containing the matching orders.
4. Evaluate `id` on each selected order.
5. Return the collection of order IDs.

Suppose the initial data is:

| id | status | total |
|---|---|---:|
| O-101 | PAID | 250 |
| O-102 | NEW | 180 |
| O-103 | PAID | 420 |
| O-104 | CANCELLED | 90 |

The expression returns the list `['O-101', 'O-103']`.

This is the appropriate way to write it when you need to discard unrelated objects and then extract only one or a few properties of the remaining ones. It also clarifies intent: the condition decides which elements are kept, while the projection decides what information is output.

## 3. The result changes after each step

You need to understand the type and shape of the data after each operator in order to write the next part correctly.

For a List or Iterable:

- Normal selection `.?[...]` returns a List containing the matching elements.
- Projection `.![...]` returns a List containing the expression result on each element.
- Projection can produce a List of objects, strings, numbers, booleans, or nested collections.

For example:

~~~text
#employees.?[active == true]
~~~

returns the active employees.

~~~text
#employees.?[active == true].![name]
~~~

returns the list of names of those active employees.

~~~text
#employees.?[active == true].![salary]
~~~

returns the list of salaries of that group of employees.

After projection, each result element is the value of the projection expression. If the projection retrieves `name`, the result elements are names; if it retrieves `salary`, the result elements are salaries. You cannot continue accessing Employee properties on a result that is now only a String or a number.

## 4. Using #this in selection and projection

In selection and projection, `#this` represents the current element being processed.

For example:

~~~text
#numbers.?[#this >= 10]
~~~

In each iteration, `#this` is a number in the collection. The condition checks whether the current number is greater than or equal to 10.

In projection:

~~~text
#employees.![#this.name]
~~~

`#this` is the current employee; the expression retrieves the name property of that employee.

If the property is directly on the element, SpEL usually allows a shorthand form:

~~~text
#employees.?[active].![name]
~~~

In selection, `active` is read on the current element. In projection, `name` is also read on the current element.

You can reference variables from the EvaluationContext in both stages:

~~~text
#orders.?[total >= #minimumTotal].![id]
~~~

`#minimumTotal` is a variable provided by the application; `#this` is implicitly the current order in the condition and projection.

`#root` still references the root object of the evaluation. When selection or projection is nested, `#this` changes to the element of the collection being processed at the current level, while `#root` does not change.

## 5. Filtering by condition and then extracting multiple properties

Projection does not only retrieve a single property. It can produce a composite expression from multiple properties of the current element.

For example:

~~~text
#orders.?[status == 'PAID'].![id + ':' + total]
~~~

Each paid order is transformed into a string containing its ID and total amount.

You can project into an inline list for each element:

~~~text
#employees.?[active].![{id, name, department}]
~~~

The result is a List in which each element is itself a sublist consisting of the id, name, and department of the corresponding employee.

For data that requires a result structure with explicit field names, consider creating a DTO or Map in Java. A list of positional values can become hard to maintain if the number of fields grows or the order of fields changes.

## 6. Combining nested selection and projection

A collection can contain nested collections. Selection and projection can be nested to filter across multiple levels.

For example, to retrieve the names of items with a requested SKU across all orders:

~~~text
#orders.![items.?[sku == #targetSku].![name]]
~~~

How to read it:

1. The outer projection iterates over each order.
2. For each order, access the items list.
3. The inner selection keeps items whose sku equals `#targetSku`.
4. The inner projection transforms each selected item into its name.
5. The outer projection produces one result corresponding to each order.

The result is a List of Lists of item names. Each sublist corresponds to one order; an order with no matching items will have an empty sublist.

If the goal is to collect all matching item names from all orders into a single flat List, this nested expression does not flatten the result automatically. Use Java to flatten it, or design the data source as a flat collection before evaluation.

For example, finding orders that have at least one item with a specific SKU, and then retrieving the order IDs:

~~~text
#orders.?[items.?[sku == #targetSku].size() > 0].![id]
~~~

The inner selection checks the items list of the current order. The outer selection keeps the order only when the number of matching items is greater than 0. The final projection retrieves the id.

## 7. Operation order affects the result

Selection and projection cannot be swapped arbitrarily because projection can discard information needed by the filter condition.

Filter objects first, then extract the total amount:

~~~text
#orders.?[status == 'PAID'].![total]
~~~

The result is the totals of the paid orders.

Project the totals first, then filter the numeric values:

~~~text
#orders.![total].?[#this >= #minimumTotal]
~~~

The result is the total values that meet the threshold, but the original Order objects have already been replaced by numbers.

The two expressions can return lists of different types and serve different purposes:

| Order | Result | Retained information |
|---|---|---|
| Selection then projection | List of values projected from the matching objects | Only the fields produced by the projection |
| Projection then selection | List of projected values satisfying the post-projection condition | Projected values, no longer the full original objects |

If the condition needs `status` but the projection already converted objects into `total`, the subsequent selection step can no longer access status. Choose the order so that the data needed for the condition still exists at the corresponding step.

## 8. Combining first or last selection with projection

In addition to normal selection, SpEL has first selection and last selection:

- `.^[...]` retrieves the first matching element in iteration order.
- `.$[...]` retrieves the last matching element in iteration order.

If you only need the ID of the first paid order:

~~~text
#orders.^[status == 'PAID']?.id
~~~

If you need the ID of the last paid order:

~~~text
#orders.$[status == 'PAID']?.id
~~~

In these two examples, first or last selection returns a single object or null. Safe navigation at the id retrieval step helps avoid accessing a property on a null result when no order is found.

If you need a list of IDs of all paid orders, use normal selection followed by projection:

~~~text
#orders.?[status == 'PAID'].![id]
~~~

Do not use first or last selection when the business requirement needs all results. These two operators also do not sort the collection; first and last are determined by the current iteration order.

## 9. Combining with Map

SpEL supports selection and projection on Map. The selection condition is evaluated on each Map.Entry; the `key` and `value` properties can be accessed.

For example, filter entries whose value is greater than a threshold and then extract the keys:

~~~text
#pricesBySku.?[value > #minimumPrice].![key]
~~~

Selection on a Map keeps the matching entries in a Map; projection afterward creates a List of keys of the selected entries.

You can project the value:

~~~text
#pricesBySku.?[value > #minimumPrice].![value]
~~~

If you only need a Map containing the matching entries, stop after selection:

~~~text
#pricesBySku.?[value > #minimumPrice]
~~~

With a Map, iteration order depends on the implementation. HashMap does not guarantee a stable order; LinkedHashMap preserves insertion order; TreeMap iterates in key order. When using first or last selection on a Map, make sure you understand the iteration order of the implementation being used.

## 10. Handling null collections, empty collections, and null elements

Three states need to be distinguished:

1. The source collection is null.
2. The collection exists, but is empty or has no matching elements.
3. The collection contains null elements.

With normal selection, if the source is valid but no element matches, the result is an empty collection. Projection on an empty collection also produces an empty result collection.

If the source is null, normal selection or projection operations may fail. You can guard with a condition or safe navigation appropriate to the Spring version being used.

Example using an explicit condition:

~~~text
#orders != null ? #orders.?[status == 'PAID'].![id] : {}
~~~

If `#orders` is null, the expression returns an empty inline list. If the collection exists, the expression filters and then projects the order IDs.

With null elements, a condition such as `status == 'PAID'` may fail to read the property on a null element. You can check beforehand:

~~~text
#orders.?[#this != null and status == 'PAID'].![id]
~~~

The logical and operator uses short-circuit evaluation, so accessing status is only evaluated when the current element is non-null.

If a property inside the element can also be null, handle that link properly with safe navigation or an explicit condition. Do not use projection to hide missing required data errors.

## 11. Result types in Java

After combining selection and projection, the element type of the result depends on the projection expression.

For example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "#orders.?[status == 'PAID'].![id]"
);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("orders", orders);

List<?> paidOrderIds =
    expression.getValue(context, List.class);
~~~

Here, the result is a List of id values. If id is a String, the application can convert or check each element for the desired type.

Requesting `List.class` specifies the outer collection type; it does not guarantee the generic type of every element. If you need a validated List<String> or List<Long>, check element types or convert them in Java.

With nested projection, the result can be a List of Lists. With Map selection followed by projection, the projection result is a List of the projected values. Determine the result type based on the final operator and the type of the inner expression.

## 12. Method access conditions and EvaluationContext

Selection and projection can invoke methods in the expression, for example:

~~~text
#orders.?[customer.isPreferred()].![customer.getDisplayName()]
~~~

The ability to invoke methods depends on the method resolver and access permissions provided by the EvaluationContext. StandardEvaluationContext generally has a more flexible configuration; SimpleEvaluationContext requires explicitly enabling the needed capabilities via its corresponding builder.

If using a restricted context, verify that the configured property accessors and method resolvers allow the operations in both the condition and the projection. You should not switch to a more permissive context just to make an expression run without first determining the access requirements.

A getter or method invoked on each element can also be expensive or have side effects. Prefer simple, stable data reads and avoid calling a service for each element in a collection.

## 13. Performance and collection size

Combining selection and projection typically iterates through data in steps:

1. Selection iterates over the source collection to evaluate the condition.
2. Matching elements are kept in a result collection.
3. Projection iterates over the selected collection to produce result values.

If the source has N elements and M elements match, this generally requires one pass evaluating the condition across N elements and one pass evaluating the projection across M elements. This is an intuitive description of the number of passes; actual cost also depends on collection type, sub-expressions, getters, and invoked methods.

To avoid unnecessary work:

- Filter before projecting if the condition needs data from the original object.
- Only project the fields actually needed.
- Avoid invoking expensive queries or services in the condition for every element.
- Do not create many intermediate collections if the data is very large.
- For data stored in a database, consider filtering and selecting columns right at the query layer.
- Measure performance with representative data before optimizing.

If the collection is very large or requires pagination, SpEL is usually better suited for rules on an already-bounded dataset. Loading all data into memory and filtering with SpEL can increase execution time and memory usage.

## 14. Complete Java example

The following example filters paid orders whose total meets a threshold, and then extracts their IDs and totals:

~~~java
import java.math.BigDecimal;
import java.util.List;

import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

public class SelectionProjectionExample {

    public List<?> findPaidOrderTotals(
            List<Order> orders,
            BigDecimal minimumTotal) {

        ExpressionParser parser = new SpelExpressionParser();

        Expression expression = parser.parseExpression(
            "#orders.?[status == 'PAID' and total >= #minimumTotal].![{id, total}]"
        );

        StandardEvaluationContext context =
            new StandardEvaluationContext();

        context.setVariable("orders", orders);
        context.setVariable("minimumTotal", minimumTotal);

        return expression.getValue(context, List.class);
    }
}
~~~

Each element of the result is a sublist containing the id and total of a matching order. This representation is concise for a small result. If you need a data structure with field names, explicit generic types, or one used widely across the application, create a DTO in Java.

## 15. Common mistakes

Some common mistakes when combining selection and projection:

- Using `.![...]` before filtering and then trying to access an original property no longer present in the result.
- Confusing normal selection with first or last selection.
- Forgetting that `#this` is the current element and changes when entering a nested collection.
- Assuming the projection result still has the source object type.
- Not handling null collections or null elements.
- Using methods not permitted by the EvaluationContext.
- Assuming Map, Set, or other collections have the same iteration order as List.
- Using expressions nested so deeply that it is hard to determine the data type at each step.
- Calling expensive operations for every element.

When an expression becomes hard to read, extract intermediate data in Java, name variables meaningfully, or move multi-step rules into a business method.

## 16. Testing the selection and projection pipeline

With the expression:

~~~text
#orders.?[status == 'PAID'].![id]
~~~

Test the following cases:

| Source data | Expected result |
|---|---|
| Multiple orders, with some paid orders | List of IDs of the paid orders |
| No paid orders | Empty List |
| Empty collection | Empty List |
| Null collection | Handled according to the chosen guard branch or safe navigation |
| Contains null elements | Condition needs a null check before reading properties |
| ID of a matching element is null | Result may contain null |
| Projection returns sublists | Verify the nested structure is correct |
| Map source | Verify the Map or List result type after each step |
| Source order changes | Does the result order change accordingly |

You should also test the same collection with normal selection, first selection, and last selection if the business logic has different result-count requirements. This helps catch choosing the wrong operator.

## 17. Key takeaways

Selection uses `.?[...]` to filter elements; projection uses `.![...]` to transform each element into a new value or result structure. The common pattern is `collection.?[condition].![expression]`: filter first, project second.

The order of the two operations affects the type and remaining information. After projection, the result elements are the projected values, so properties of the original object can no longer be accessed by default. In each condition or projection expression, `#this` is the current element; with nested collections, the current scope changes by level.

Selection on a Map keeps matching entries; projection on a Map creates a List of projected results. For List, arrays, and Iterable, selection/projection creates result collections according to SpEL rules. Handle null, empty collections, null elements, and iteration order carefully.

Use combined selection and projection for small, readable pipelines on data already in memory. For large collections, expensive queries, multi-step business logic, or results requiring explicit data types, consider handling them in Java or at the appropriate query layer.

## References

- [Spring Framework Reference — Collection Selection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html)
- [Spring Framework Reference — Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-projection.html)