# Fixed Collection Literals and Dynamic Expressions

SpEL allows creating collections directly inside an expression string using inline syntax. List literals use curly braces with comma-separated elements; map literals use key-value pairs. This style is useful when an expression needs a small set of values to compare, filter, pass into a method, or combine with object data.

An important point is distinguishing collections that contain only fixed literals from collections whose elements or keys/values are computed dynamically. SpEL can cache a collection literal when all components are constant values. If there are variables, properties, or method calls, those parts must be evaluated against the context of each run.

## 1. Inline list literals

List literals are written with curly braces. Elements are separated by commas:

~~~text
{1, 2, 3}
{'red', 'green', 'blue'}
{true, false, true}
~~~

Java example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("{'red', 'green', 'blue'}");

List<?> colors = expression.getValue(List.class);

System.out.println(colors); // [red, green, blue]
~~~

SpEL parses the elements inside the curly braces and creates a List containing those values. List literals can hold strings, numbers, Booleans, null, or expressions that produce objects, as long as the values conform to the syntax and types the application needs.

When a small list is needed directly inside a condition, an inline list is usually more concise than creating a Java variable just to hold a few fixed values.

## 2. Inline map literals

Map literals are written as key-value pairs, where key and value are separated by a colon and pairs are separated by commas:

~~~text
{'name': 'Lan', 'active': true, 'level': 3}
~~~

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        "{'name': 'Lan', 'active': true, 'level': 3}"
);

Map<?, ?> profile = expression.getValue(Map.class);

System.out.println(profile.get("name"));   // Lan
System.out.println(profile.get("active")); // true
~~~

Map literals fit when an expression needs a small group of clearly named properties. For instance, you can create temporary configuration, pass a set of parameters to a method, or describe sample data directly in a rule.

Keys and values are SpEL expressions, so they do not have to be string literals. You can use numbers, variables, or calculation results as keys/values if the data type and intended usage allow it.

## 3. Fixed collection literals

A collection literal is considered fixed when all of its components are constant literals. Example:

~~~text
{1, 2, 3}
{'draft', 'review', 'published'}
{'enabled': true, 'maxRetries': 3}
~~~

For lists or maps consisting solely of fixed literals, SpEL can create the collection once when parsing the expression and cache that value for reuse in subsequent evaluations. This avoids rebuilding the same collection on every getValue call.

Example:

~~~java
Expression allowedStates = parser.parseExpression(
        "{'DRAFT', 'REVIEW', 'PUBLISHED'}"
);

List<?> states = allowedStates.getValue(List.class);
~~~

Fixed collections are suitable for small allowlists, labels, status codes, or constant sets used repeatedly. Because the value may be cached, treat this collection as read-only configuration data. Do not modify the returned collection or rely on each evaluation creating a new instance.

Caching is an implementation detail for optimizing expressions. Write expressions according to their fixed-data meaning, and do not use object identity or mutation operations to infer collection lifecycle behavior.

## 4. Collection literals with dynamic expressions

If a list element or a map key/value depends on a variable, property, or method, that component must be evaluated when the expression runs.

Dynamic list example:

~~~text
{#primaryColor, #secondaryColor, #fallbackColor}
~~~

Dynamic map example:

~~~text
{'user': #currentUser.name, 'total': #price * #quantity}
~~~

It can be evaluated with a context:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("primaryColor", "blue");
context.setVariable("secondaryColor", "green");
context.setVariable("fallbackColor", "gray");

Expression expression = parser.parseExpression(
        "{#primaryColor, #secondaryColor, #fallbackColor}"
);

List<?> colors = expression.getValue(context, List.class);
~~~

The value of each variable is retrieved from the context at the time of getValue. When the context changes, the next evaluation can produce a collection containing different data.

Unlike collections composed only of constant literals, a collection with dynamic components cannot be treated as an immutable value set of the expression. SpEL must evaluate dynamic components against the current data.

## 5. Comparing fixed collections and dynamic collections

| Characteristic | Fixed collection | Dynamic collection |
|---|---|---|
| Components | Constant literals only | Contains variables, properties, calculations, or methods |
| Value | Independent of context | Depends on the context of each evaluation |
| Processing | Can be created and cached at parse time | Components are evaluated at runtime |
| Suitable for | Status sets, labels, constants | Values per request or current object |
| Note | Do not rely on getting a new instance each evaluation | Control method calls and input data |

Example of two expressions:

~~~text
{'OPEN', 'CLOSED'}
{#currentState, #nextState}
~~~

The first expression contains only fixed string literals. The second expression depends on context variables, so the result changes according to variable values on each evaluation turn.

Simply writing a collection literal inside curly braces does not make the entire collection fixed. As soon as even one component depends on dynamic data, the expression must evaluate that component at runtime.

## 6. Nested collections

Lists can contain other lists, maps can contain lists or maps, and collections can be nested to multiple levels:

~~~text
{{1, 2}, {3, 4}}
{'colors': {'red', 'blue'}, 'enabled': true}
{'profile': {'name': 'Lan', 'active': true}}
~~~

Example creating a nested list:

~~~java
Expression expression = parser.parseExpression(
        "{{1, 2}, {3, 4}}"
);

List<?> matrix = expression.getValue(List.class);
~~~

Fixed and dynamic components can be combined:

~~~text
{'user': #currentUser.name, 'roles': {'EDITOR', 'REVIEWER'}}
~~~

Here the user key has a dynamic value taken from currentUser, while roles is a fixed literal list. This structure allows bundling needed data into a single collection.

For deeply nested structures, name variables or extract complex data into Java if the expression becomes hard to read. A short collection literal helps describe data; a large collection tree can make expressions hard to maintain and hard to type-check.

## 7. Empty collection literals

SpEL has syntax for empty collections:

~~~text
{}
{:}
~~~

Empty curly braces represent an empty list; the {:} syntax represents an empty map.

Example:

~~~java
List<?> emptyList =
        parser.parseExpression("{}").getValue(List.class);

Map<?, ?> emptyMap =
        parser.parseExpression("{:}").getValue(Map.class);
~~~

Empty collections are useful when an expression needs a collection value but currently has no elements. However, verify the type that Java code expects and avoid assuming an empty collection inherently carries specific element type information.

If a collection with a clear generic type is needed, it is usually better to create it in Java or convert through a specifically typed API rather than relying on a type inferred from an empty literal.

## 8. Using collection literals in conditions

Inline lists are often used to check whether a value belongs to an allowed set. On a list created inside an expression, you can call the contains() method:

~~~text
{'DRAFT', 'REVIEW', 'PUBLISHED'}.contains(#order.status)
~~~

Example:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

Expression expression = parser.parseExpression(
        "{'DRAFT', 'REVIEW', 'PUBLISHED'}.contains(status)"
);

Boolean allowed = expression.getValue(context, Boolean.class);
~~~

The expression returns true if order's status is in the listed set of states. This is a concise way to represent a small allowlist.

Map literals can also be used for lookups or checking keys:

~~~text
{'vi': 'Xin chào', 'en': 'Hello'}[#locale]
~~~

In the example, the locale value determines the key used to retrieve the corresponding greeting. If the key does not exist, the lookup result may be null; handle missing keys according to application requirements.

## 9. Using collection literals as method arguments

An inline list or map can be passed directly into a method:

~~~text
filterByStates({'OPEN', 'PENDING'})
configure({'timeout': 30, 'enabled': true})
~~~

Java example:

~~~java
public List<Order> filterByStates(List<String> states) {
    // Filter orders by the passed-in states
    return orders.stream()
            .filter(order -> states.contains(order.getStatus()))
            .toList();
}
~~~

SpEL can invoke the corresponding method if MethodResolver finds a matching signature and the type conversion mechanism supports the arguments. Verify the actual element types and parameter types; a collection literal does not automatically guarantee that Java generic types are inferred accurately in all cases.

When passing a map literal into a method, clearly establish the key/value types the method expects. If the method requires Map<String, Integer>, the data in the literal should be consistent with that contract.

## 10. Using dynamic expressions and per-evaluation contexts

Dynamic collections can combine multiple data sources in the context:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setVariable("currency", "VND");
context.setVariable("includeTax", true);

Expression expression = parser.parseExpression(
        "{'orderId': #root.id, "
        + "'amount': #root.total, "
        + "'currency': #currency, "
        + "'taxIncluded': #includeTax}"
);

Map<?, ?> summary = expression.getValue(context, Map.class);
~~~

On each evaluation, the summary map is built from the root object and the current variables. If another request has a different order or currency, that request's context produces the corresponding data.

Do not share a mutable context across concurrent requests if variables and the root object can be modified. Create a context for each evaluation turn or manage input data in a concurrency-safe manner.

If a collection literal contains method calls, remember those methods may be executed every time the collection is evaluated. Avoid placing methods with side effects in dynamic elements if the collection is only meant to describe data.

## 11. Distinguishing collection literals from array construction

Inline lists and maps create collections in SpEL syntax. If you need a Java array with a specific element type, SpEL has separate array creation syntax using the new keyword:

~~~text
new int[3]
new String[2]
new int[]{1, 2, 3}
~~~

Arrays differ from Lists and Maps in data type, size, and access API. Lists are typically accessed via indexers and have collection methods; Maps are accessed by key; arrays have a component type and fixed length after creation.

Example:

~~~java
Expression listExpression =
        parser.parseExpression("{1, 2, 3}");

Expression arrayExpression =
        parser.parseExpression("new int[]{1, 2, 3}");

List<?> values = listExpression.getValue(List.class);
int[] numbers = arrayExpression.getValue(int[].class);
~~~

Choose collections when you need flexible or key-value structures. Choose arrays when the target Java API requires the exact array type or when the component type is part of the contract.

## 12. Element data types and conversion

Inline collections can contain values of different types:

~~~text
{'Lan', 25, true, null}
~~~

SpEL creates a collection containing values with their corresponding runtime types. Do not assume all elements are automatically converted to the same type just because they are in one list.

With maps, keys and values can also have different types:

~~~text
{1: 'one', '2': 2, true: 'enabled'}
~~~

This structure is valid expressively, but it can be difficult to use if Java code expects homogeneous key/value types. For collections passed to methods or assigned to properties with specific generic types, standardize the data types and check conversion.

If an expression needs exact decimal numbers, use BigDecimal literals with the M suffix instead of letting floating-point numbers default to Double:

~~~text
{'price': 19.90M, 'quantity': 3M}
~~~

Element types affect subsequent operations and method calls. Design collections according to the exact types the consumer expects.

## 13. Caution with dynamic collections and side effects

A dynamic collection literal can contain method calls, property access, or expressions with side effects:

~~~text
{#service.nextId(), #service.nextId()}
~~~

Each element can trigger a method call when the collection is evaluated. If the method mutates state, sends requests, or writes data, evaluating the expression can produce side effects multiple times.

Some safety guidelines:

1. Use fixed literals for small constant sets.
2. Use variables or properties for dynamic data that changes per request.
3. Avoid calling methods with side effects inside collection literals.
4. Do not expose broad-privilege services or repositories into the context unnecessarily.
5. Control key/value types before passing the collection to other methods.
6. Do not modify collection literals used as fixed data or cached values.
7. Use DTOs or build collections in Java if the data structure is complex.

SpEL is an expression language capable of invoking methods and accessing objects. Collection literals do not reduce the privileges of expressions placed inside them.

## 14. Common errors

| Symptom | Common cause | How to check |
|---|---|---|
| Parser errors on list literal | Missing comma or unbalanced curly braces | Check every element and separator |
| Map literal fails to parse | Missing colon between key/value | Check every key:value pair |
| Values do not change across evaluations | Collection contains only fixed literals and is cached | Identify which component needs to be dynamic |
| Dynamic values are not updated | Variable or root object in context did not change as expected | Check the context for each getValue call |
| Key not found | Missing key or different type | Check the actual key and runtime type |
| Method does not accept collection | Incompatible argument type or generic contract | Check signature and converter |
| Modifying collection causes unexpected impact | Mutating a fixed collection literal or shared object | Create a mutable copy in Java if updates are needed |
| Expression hard to maintain | Deeply nested collections or many method calls | Extract complex data into DTOs/Java |

## 15. Takeaways

Inline lists use the syntax {value1, value2}; inline maps use {key: value} pairs. Collections containing only constant literals can be created and cached by SpEL at parse time. If an element, key, or value depends on a variable, property, calculation, or method, that part is evaluated against the context at runtime.

You can nest lists and maps, create empty collections, use collections in conditions, look up keys, or pass them as method arguments. If a Java array with a specific component type is needed, use the new array syntax instead of confusing inline lists with arrays.

Distinguish fixed data from dynamic data, keep element types consistent, avoid side effects in method calls, and only use collection literals for structures small enough to read, verify, and maintain directly inside the expression.