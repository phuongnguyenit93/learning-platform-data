# Distinguishing regular selection from first or last selection

## Objectives

After this lesson, you will be able to distinguish three ways to select elements in Spring Expression Language (SpEL): regular selection to get all matching elements, first selection to get the first matching element, and last selection to get the last matching element. You will know the syntax of each operator, how to use #this in conditions, how to combine selection with projection, and how to handle collections with no results.

## 1. What is selection in SpEL?

Selection is the operation of filtering a collection based on a condition. SpEL evaluates the condition on each element and chooses the ones that satisfy it.

Regular selection syntax:

~~~text
collection.?[selectionExpression]
~~~

For example, getting all paid orders:

~~~text
#orders.?[status == 'PAID']
~~~

The expression checks the status property of each order. Orders whose status equals PAID are placed into the result.

Regular selection is suitable when the application needs all elements satisfying the condition, such as:

- Getting all orders with a paid status.
- Finding all employees belonging to a department.
- Filtering products priced below a threshold.
- Retrieving records satisfying a business rule.

The result is a new collection containing the subset of matching elements. For an array or Iterable source, the result is a collection of the selected elements. For a Map source, SpEL evaluates the condition on each Map.Entry and returns a Map containing the matching entries.

## 2. Regular selection: getting all results

The .?[] operator does not stop at the first matching element. It continues inspecting the entire source and collects every element satisfying the condition.

Example with a list of numbers:

~~~text
{2, 5, 8, 11, 14}.?[#this > 7]
~~~

The result contains 8, 11, and 14.

Example with a list of orders:

~~~text
#orders.?[total >= 1000]
~~~

The result contains all orders with a total greater than or equal to 1000.

If no element matches, regular selection returns an empty collection. This differs from first or last selection, which look for only a single element.

Choose regular selection when all matching elements matter for the next processing step. If only a single representative result is needed, you can use first or last selection to avoid creating a collection the application does not need.

## 3. First selection: getting the first matching element

First selection uses the .^[] operator:

~~~text
collection.^[selectionExpression]
~~~

Example:

~~~text
{2, 5, 8, 11, 14}.^[#this > 7]
~~~

The result is 8, because this is the first element in iteration order satisfying the condition #this > 7.

With a list of orders:

~~~text
#orders.^[status == 'PAID']
~~~

The expression returns the first paid order found in the list's iteration order.

First selection is useful when:

- Only the first matching record is needed.
- The list is already sorted by priority order.
- You need to pick the first candidate according to source order.
- You do not need to keep the remaining matching results.

First selection does not sort the collection automatically. If you want the element with the smallest value, newest timestamp, or highest priority, ensure the source already has the right order before evaluation, or sort the data in Java.

If no element matches the condition, the result of first selection is null. Therefore, when continuing to access properties of the result, handle the not-found case.

## 4. Last selection: getting the last matching element

Last selection uses the .$[] operator:

~~~text
collection.$[selectionExpression]
~~~

Example:

~~~text
{2, 5, 8, 11, 14}. $[#this > 7]
~~~

When writing an actual expression, do not put a space between the dot and the operator; the correct syntax is:

~~~text
{2, 5, 8, 11, 14}.$[#this > 7]
~~~

The result is 14, because this is the last element in iteration order satisfying the condition.

With a list of orders:

~~~text
#orders.$[status == 'PAID']
~~~

The expression returns the last paid order in the list's iteration order.

Last selection is useful when:

- You need the last matching element in an ordered list.
- You need to get the last record in a sorted data group.
- You want to find the last element satisfying a condition without collecting the entire result collection.

Last selection also does not sort the source. "Last" means last in the current iteration order, not newest or largest by default.

If no element matches, the result of last selection is null.

## 5. Comparing the three operators

The three operators share the same condition syntax but differ in the number of results returned:

| Type | Syntax | Result |
|---|---|---|
| Regular selection | .?[condition] | All matching elements in a collection |
| First selection | .^[condition] | One first matching element, or null |
| Last selection | .$[condition] | One last matching element, or null |

Example with the same source:

~~~text
#numbers.?[#this > 5]
#numbers.^[#this > 5]
#numbers.$[#this > 5]
~~~

Suppose #numbers is [2, 7, 9, 3, 12]:

- Regular selection returns [7, 9, 12].
- First selection returns 7.
- Last selection returns 12.

Regular selection returns an empty collection when there are no results. First and last selection return null when no matching element is found. This difference affects how the result is used in subsequent expressions and how the receiving type is declared in Java.

## 6. #this in selection conditions

In selection, #this represents the current element being checked.

Example:

~~~text
#numbers.?[#this >= 10]
~~~

While iterating through each number, #this takes the value of the current element in turn. The condition is evaluated separately for each element.

With objects:

~~~text
#employees.^[salary > #minimumSalary]
~~~

Inside the condition, salary is a property of the current employee. It can be written explicitly:

~~~text
#employees.^[#this.salary > #minimumSalary]
~~~

The #minimumSalary variable is retrieved from EvaluationContext, while #this changes for each employee being examined.

If selection expressions are nested, #this corresponds to the element of the collection at the innermost level currently being evaluated. Identify the current collection properly to avoid confusing properties of the outer object with properties of the inner element.

## 7. Selection on Map

SpEL supports selection on Map. The condition is evaluated on each Map.Entry object; the two properties key and value can be accessed in the expression.

For example, filtering entries with a value less than 27:

~~~text
#scoresByName.?[value < 27]
~~~

The result is a new Map containing the entries that satisfy the condition.

You can filter by key:

~~~text
#settings.?[key.startsWith('feature.')]
~~~

This example assumes key is a String and the startsWith method is allowed in EvaluationContext.

Regular selection on a Map returns all matching entries. When only one element by iteration position is needed, first or last selection can be used to get the first or last matching result. With Map, the condition is still evaluated on Map.Entry; handle the corresponding result type if the application needs to work directly with the entry.

Map iteration order depends on the implementation. LinkedHashMap preserves insertion order; TreeMap iterates in key-sorted order; HashMap does not guarantee a stable order. Therefore, do not use first or last selection on an unordered Map if business logic requires stable results.

## 8. Selection on arrays and Iterable

Selection can be applied to arrays and objects implementing Iterable, including List and Set.

Example with an array:

~~~java
int[] values = {3, 8, 12, 17};

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("values", values);

ExpressionParser parser = new SpelExpressionParser();
Expression expression =
    parser.parseExpression("#values.?[#this >= 10]");

Object selected = expression.getValue(context);
~~~

The condition is checked on each element of the array. You can replace .?[] with .^[] if only the first element meeting the condition is needed, or .$[] if the last element meeting the condition is needed.

For a List, element order is usually the order stored in the list. For a Set, order depends on the implementation. A LinkedHashSet preserves insertion order, while HashSet does not guarantee a stable iteration order.

Because first and last selection depend on iteration order, check the input collection type before using these two operators in business rules.

## 9. Combining selection with projection

Selection and projection have different roles:

- Selection .?[...] filters elements and preserves the matching elements themselves.
- Projection .![...] transforms each element into a new value and creates a result collection.

They can be combined:

~~~text
#orders.?[status == 'PAID'].![id]
~~~

The expression filters all paid orders, then retrieves the id of each matching order.

First selection can be combined with property access on the found element:

~~~text
#orders.^[status == 'PAID']?.id
~~~

The expression gets the first paid order and then reads id. Safe navigation in the next step makes the result null if no matching order exists.

Similarly, last selection:

~~~text
#orders.$[status == 'PAID']?.id
~~~

If you need a list of IDs of all matching orders, use regular selection combined with projection. If you only need the ID of the first or last matching order, use first or last selection and then access the property.

## 10. Nesting selection inside selection

A selection condition can contain another selection. For example, finding all customers who have at least one paid order:

~~~text
#customers.?[
    orders.?[status == 'PAID'].size() > 0
]
~~~

The inner selection filters the orders list of the current customer. If there is at least one paid order, that customer is retained in the outer result.

First selection can be used to find the first customer with a priority order:

~~~text
#customers.^[
    orders.^[priority == true] != null
]
~~~

In the outer selection, #this is the current customer. In the inner selection, #this is the order being checked. The result of the inner first selection is null if the customer has no matching priority order.

Nested expressions can be hard to read when there are multiple levels. Use line breaks and clear parentheses; if a rule requires multiple steps or service calls, move the complex processing into Java.

## 11. Handling null collections and empty results

There are two different situations:

1. The source collection does not exist or is null.
2. The collection exists, but no element satisfies the condition.

With regular selection, no matching results produce an empty collection. With first or last selection, no matching results return null.

If the source collection may be null, guard before selection:

~~~text
#orders != null ? #orders.^[status == 'PAID'] : null
~~~

Or use safe collection selection when the Spring version in use supports that syntax:

~~~text
#orders?.?[status == 'PAID']
~~~

Safe selection returns null when the source collection is null; it does not turn null into an empty collection. If the application must always receive a collection, normalize input data in Java or use an intentional default expression.

With first or last selection, handle null before accessing properties:

~~~text
#orders.^[status == 'PAID']?.id
~~~

Do not assume that having no results will return an empty object. Null results must be handled explicitly.

## 12. Performance and choosing the right operator

Regular selection needs to iterate over the entire source to find all matching elements. First selection can stop after finding the first matching element. Last selection needs to determine the last matching element in iteration order, so it generally has to iterate to the end of the source.

Therefore:

- Use .?[] when all results are needed.
- Use .^[] when only the first result in iteration order is needed.
- Use .$[] when only the last result in iteration order is needed.
- If you need the largest, smallest, or an element by another sorting criterion, sort or compute in Java instead of confusing it with first/last selection.

Do not choose an operator based on performance alone. Choose according to business semantics and the result type needed. For very large collections or out-of-memory data queries, filter at the appropriate data layer instead of loading all data and using SpEL to filter.

## 13. Complete Java example

The example below evaluates all three selection forms on the same list of orders:

~~~java
import java.math.BigDecimal;
import java.util.List;

import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

public class SelectionExample {

    public static void main(String[] args) {
        List<Order> orders = loadOrders();

        StandardEvaluationContext context =
            new StandardEvaluationContext();

        context.setVariable("orders", orders);

        ExpressionParser parser = new SpelExpressionParser();

        Expression allPaid =
            parser.parseExpression("#orders.?[status == 'PAID']");

        Expression firstPaid =
            parser.parseExpression("#orders.^[status == 'PAID']");

        Expression lastPaid =
            parser.parseExpression("#orders.$[status == 'PAID']");

        Object all = allPaid.getValue(context);
        Order first = firstPaid.getValue(context, Order.class);
        Order last = lastPaid.getValue(context, Order.class);
    }

    private static List<Order> loadOrders() {
        // Load data from the application's source.
        return List.of();
    }
}
~~~

In the example, all receives a collection containing all paid orders; first and last receive a single first or last matching Order. If the list has no paid orders, first and last are null.

In a real application, the Order class needs a status property readable by SpEL. If using a restricted context, method/property access must be configured appropriately for the expression.

## 14. Testing edge cases

On the same collection, test:

| Source data | Condition | Regular selection | First selection | Last selection |
|---|---|---|---|---|
| [2, 7, 9, 3, 12] | #this > 5 | [7, 9, 12] | 7 | 12 |
| [1, 2, 3] | #this > 5 | [] | null | null |
| [5, 5, 5] | #this == 5 | [5, 5, 5] | 5 | 5 |
| [] | #this > 0 | [] | null | null |

In addition to the cases above, check:

- Source collection is null.
- Collection element is null.
- Condition accessing nested properties may encounter null.
- Collection with stable order and collection without guaranteed order.
- Map with null key or value.
- First or last element does not match, while middle elements match.
- No matching element.
- First/last result is further accessed via a property or method.

Testing helps confirm the application properly understands the difference between an empty collection and a null value, as well as the iteration order of the source.

## 15. Key takeaways

Regular selection uses .?[condition] to get all matching elements and returns a collection. First selection uses .^[condition] to get the first matching element. Last selection uses .$[condition] to get the last matching element.

First and last are determined by the current iteration order of the source; these operators do not sort the collection automatically. For Lists and arrays, the order is usually clear. For Sets or Maps, check whether the implementation guarantees order.

Inside a selection condition, #this is the element currently being examined. Regular selection on a Map evaluates each Map.Entry and keeps the matching entries. You can combine selection with projection to extract properties of all results, or use first/last selection when only one object is needed.

Distinguish an empty collection from null: regular selection with no results returns an empty collection, whereas first/last selection with no results returns null. Choose the operator based on the number of results business logic requires and handle null sources or no-match cases explicitly.

## References

- [Spring Framework Reference — Collection Selection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html)