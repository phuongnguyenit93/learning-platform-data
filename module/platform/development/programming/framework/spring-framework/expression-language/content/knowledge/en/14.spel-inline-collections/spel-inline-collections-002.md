# Creating Inline Lists and Nested Lists

## Objectives

After this lesson, you can create a List directly inside a Spring Expression Language (SpEL) expression using the inline list syntax; use empty lists, single-element lists, and multi-element lists; nest lists to represent multidimensional data; and combine fixed values with variables or dynamic expressions. You will also learn how to read elements, use lists in conditions, distinguish inline lists from selection/projection, and handle null or malformed data.

## 1. What is an inline list?

An inline list is a syntax for creating a list directly inside a SpEL expression using curly braces. Elements are separated by commas:

~~~text
{'An', 'Binh', 'Chi'}
~~~

The expression above creates a List of three strings in the exact declared order. The result can be assigned to a Java variable of type List:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression =
    parser.parseExpression("{'An', 'Binh', 'Chi'}");

List<?> names = expression.getValue(List.class);
~~~

Inline lists are useful when an expression needs to assemble a few values to return, pass to a method, check membership, or use as intermediate data. The list is created in memory during expression evaluation; this syntax does not query a database and does not automatically load external data.

The curly braces in an inline list are SpEL syntax. When writing an expression string in Java, the outer string usually uses double quotes, while string literals inside SpEL can use single quotes.

## 2. Empty, single-element, and multi-element lists

SpEL supports the common forms of inline lists:

~~~text
{}
{'SPRING'}
{'JAVA', 'SPRING', 'KOTLIN'}
~~~

- `{}` creates an empty list.
- `{'SPRING'}` creates a list with one element.
- A multi-element list preserves the order written in the expression.

An element does not have to be a string. An inline list can contain numbers, booleans, null, or values evaluated from expressions:

~~~text
{10, 20, 30}
{true, false}
{'A', null, 'C'}
~~~

A list can contain multiple data types if the expression requires it. However, if the list represents a business dataset, you should keep the element type consistent so that Java code consuming the result is more predictable.

A null element is still an element in the list. It is different from the list having no element at that position. When reading or invoking methods on a null element, the application needs to handle null appropriately.

## 3. Elements can be expressions

Elements of an inline list can be fixed literals or expressions evaluated by SpEL. For example:

~~~text
{#primaryColor, #secondaryColor, #fallbackColor}
~~~

Each variable is retrieved from EvaluationContext. You can mix fixed values with dynamic values:

~~~text
{'DEFAULT', #userPreference, #systemFallback}
~~~

Java example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("{'DEFAULT', #preferred, #fallback}");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("preferred", "DARK");
context.setVariable("fallback", "LIGHT");

List<?> themes = expression.getValue(context, List.class);
~~~

The result is a list of three values in order: DEFAULT, DARK, and LIGHT.

If a variable has not been registered, a property name does not exist, or a sub-expression cannot be evaluated, the entire inline list evaluation may fail. Therefore, provide all variables and root objects that the elements need.

## 4. Using root object properties in inline lists

An inline list can read data from the root object, just like other SpEL expressions:

~~~text
{customer.id, customer.name, customer.email}
~~~

If the expression is evaluated with a Customer as the root object, SpEL reads the three properties and produces the resulting list.

You can use safe navigation if an intermediate property might be null:

~~~text
{order.id, order.customer?.name, order.customer?.email}
~~~

When customer is null, the two corresponding elements receive null instead of attempting to read further properties on a null reference. Safe navigation only protects steps written with the `?.` operator; if a path has multiple nullable levels, place the operator at each appropriate step.

This example still keeps null elements in the list. If the requirement is to completely omit missing elements from the result, you need to use a filter or build the list in Java according to business rules.

## 5. Creating nested lists

An inline list can contain other inline lists. This is a way to represent multidimensional lists or grouped data:

~~~text
{{'A', 'B'}, {'C', 'D'}}
~~~

The expression above creates an outer list with two elements; each element is a sublist:

- The first sublist contains A and B.
- The second sublist contains C and D.

You can use this structure to represent small tables, option groups, or row-based data:

~~~text
{{'Name', 'Role'}, {'An', 'Admin'}, {'Binh', 'Editor'}}
~~~

Each sublist can represent a row. The outer list preserves the row order; each sublist preserves the column order.

SpEL does not enforce that all sublists have the same number of elements. If one sublist has fewer elements, the structure can still be created, but the code consuming the result must handle that difference.

## 6. Accessing elements in nested lists

An inline list result can be accessed using an indexer just like other Lists. For example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("{{'A', 'B'}, {'C', 'D'}}");

List<?> matrix = expression.getValue(List.class);
~~~

Once you have the list, you can access it by index using SpEL if you put the list into the context:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("matrix", matrix);

Expression cell =
    parser.parseExpression("#matrix[1][0]");

String value = cell.getValue(context, String.class);
~~~

The result is C: index 1 selects the second sublist, and then index 0 selects the first element of that sublist.

Indexing starts at 0 at every level. Each access must ensure that the current list is non-null and the index is within the bounds of that specific list.

## 7. Multi-level nested lists

You can nest more than two levels if the data structure requires it:

~~~text
{
    {
        {'A1', 'A2'},
        {'B1', 'B2'}
    },
    {
        {'C1', 'C2'},
        {'D1', 'D2'}
    }
}
~~~

This is an outer list containing groups; each group contains rows; each row contains values. The structure is similar to a three-dimensional array, except the elements here are nested Lists.

Avoid deep nesting just to make an expression short. When a structure has many levels, name the data parts in Java or use a model class with clear properties. Nested lists are suitable for small data with simple structure used directly inside an expression.

## 8. Combining inline lists with conditions and methods

An inline list can be used with operators and List methods. For example, checking whether a status is in an accepted group:

~~~text
{'PAID', 'SHIPPED', 'DELIVERED'}.contains(#order.status)
~~~

If status is one of the three listed strings, the expression returns true.

You can use a list variable passed into the context:

~~~text
#allowedStatuses.contains(#order.status)
~~~

Java:

~~~java
context.setVariable(
    "allowedStatuses",
    List.of("PAID", "SHIPPED", "DELIVERED")
);

Expression expression =
    parser.parseExpression("#allowedStatuses.contains(#order.status)");

Boolean allowed = expression.getValue(context, Boolean.class);
~~~

An inline list can also be part of a larger conditional expression:

~~~text
#order != null and
{'PAID', 'SHIPPED'}.contains(#order.status)
~~~

Remember that calling `contains(...)` is a method invocation on List. It must be permitted by the EvaluationContext under the method resolution mechanism in use. If a restricted context does not allow method calls, choose an expression style or configuration that matches your application's policy.

## 9. Inline lists differ from selection and projection

These three syntaxes serve different purposes:

| Syntax | Role | Example |
|---|---|---|
| Inline list `{...}` | Create a new list from declared elements | `{'A', 'B'}` |
| Selection `.?[...]` | Filter elements of an existing collection | `#orders.?[total > 100]` |
| Projection `.![...]` | Create a result collection by evaluating an expression for each element | `#orders.![id]` |

An inline list declares which elements will be in the list. Selection and projection operate on an input collection.

For example, you can create a fixed list of status codes:

~~~text
{'PAID', 'SHIPPED'}
~~~

Whereas if you need to extract the IDs of paid orders from existing data:

~~~text
#orders.?[status == 'PAID'].![id]
~~~

Do not confuse the curly braces of an inline list with the square brackets of selection or projection. They solve different tasks and can be combined in a single expression when needed.

## 10. Fixed inline lists and dynamic expressions

SpEL can optimize a list that contains only fixed literals. A list composed solely of fixed values can be created during expression parsing and reused during evaluation.

For example:

~~~text
{'DEV', 'TEST', 'PROD'}
~~~

Conversely, if the list contains variables or expressions that must be computed at runtime:

~~~text
{#environment, #tenant, #defaultEnvironment}
~~~

the elements must be evaluated when the expression runs to produce a result corresponding to the current context.

This means the same Expression object can be parsed once yet yield different results when variables in EvaluationContext change:

~~~java
Expression expression =
    parser.parseExpression("{#first, #second}");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("first", "A");
context.setVariable("second", "B");

List<?> firstResult = expression.getValue(context, List.class);

context.setVariable("first", "X");
context.setVariable("second", "Y");

List<?> secondResult = expression.getValue(context, List.class);
~~~

The first evaluation produces the list A, B; the next uses the new values X, Y. You should not rely on the identity or mutability of the returned List object as part of an inline list's contract. If the application needs a collection with a specific lifecycle or mutation policy, create and manage it in Java.

## 11. Data types and element conversion

An inline list can contain elements of different types. For example:

~~~text
{'SPRING', 6, true, null}
~~~

The result is a List containing a string, a number, a boolean, and null. When receiving the result in Java, the appropriate generic type is usually List<?> or List<Object>.

If you need a list with a specific element type, ensure each sub-expression returns a compatible type:

~~~text
{#primaryId, #secondaryId, #fallbackId}
~~~

If the three variables represent IDs, you should provide them with the same type or consistently convertible types.

Requesting the result type List.class only confirms that the result object can be converted to List. It does not check that all elements inside have the same type. If you need to guarantee element types, validate or convert in Java after evaluation.

## 12. Common errors when creating inline lists

Some errors commonly appear when writing inline lists:

- Missing closing curly brace.
- Missing comma between two elements.
- Unbalanced quotes in string literals.
- Referencing a variable not registered in EvaluationContext.
- Accessing a property on a null object.
- Nesting lists while assuming all sublists have the same size.
- Using an out-of-bounds index when reading a nested list.
- Calling a method on a null element or on a type that does not support that method.

Valid syntax examples:

~~~text
{'A', 'B', 'C'}
{{'A', 'B'}, {'C', 'D'}}
{#first, #second, 'DEFAULT'}
~~~

When the parser reports a syntax error, check every pair of braces and commas. When parsing succeeds but getValue fails, check variables, the root object, element types, and access operations performed at runtime.

## 13. Testing nested lists

When testing inline lists, include the following cases:

| Case | What to verify |
|---|---|
| Empty list `{}` | Result has 0 elements |
| Single-element list | Element at index 0 |
| Multi-element list | Order is preserved |
| List with null element | null is kept as an element |
| List with dynamic variables | Values match the context on each evaluation |
| Nested list | Accessing the right level and right index |
| Empty sublist | No valid index inside |
| Sublists of different sizes | Consuming code handles irregular structure |
| Unregistered variable | Evaluation error handling |
| Invalid literal syntax | Parser detects error during parsing |

For multi-level lists, test each access path instead of only checking the whole result. This helps identify exactly which level can be empty, null, or lack the requested index.

## 14. When to create an inline list vs. creating a list in Java?

Use an inline list when:

- The list is short and the elements are known right inside the expression.
- You need to group a few literals or variables for a conditional check.
- You need to create small, simple data in configuration.
- The nested list has a shallow structure and is easy to read.

Create a list in Java when:

- The list is built across multiple business steps.
- You need to add, remove, sort, or transform many elements.
- You need control over generic types, implementation, or mutability.
- The data is large or loaded from a database, API, or file.
- You need to reuse a collection with a clear lifecycle.

A SpEL expression should focus on creating or checking a small set of values. When list-creation logic becomes complex, move collection construction to Java and pass the result into EvaluationContext.

## 15. Takeaways

SpEL's inline list uses the syntax `{item1, item2, ...}` to create a List directly inside an expression. A list can be empty, have one element, or have multiple elements; elements can be literals, null, variables, or expressions evaluated at runtime.

You can nest inline lists to create multidimensional structures, then use indexers to access each level. Elements preserve declaration order; sublists do not have to be the same size. Check for null and index bounds when reading nested data.

Lists containing only fixed literals may be created at parse time for optimization. Lists with dynamic expressions need to evaluate elements according to the current context. An inline list differs from selection and projection: it creates a list from declared elements, while the other two operators filter or transform an existing collection.

Use inline lists for small, clear value groups. For large structures, frequent changes, or lifecycle management, build the List in Java and pass it into SpEL.