# Inline Lists Are Optimized into Constant Collections When Possible in SpEL

## Objectives

SpEL allows declaring a list directly inside an expression using the `{...}` syntax. An inline list can contain literals, expressions, or nested inline lists. When all elements of the list are constants, SpEL can create a constant list and reuse that value across evaluations, instead of creating a new list every time.

This is an expression-level optimization: it reduces collection-building work and object garbage created when the same expression is evaluated repeatedly. To take advantage of this optimization, you need to understand which elements are considered constant, which elements depend on runtime, and when to copy the result to work with a mutable collection.

## 1. Inline list syntax

An inline list uses curly braces `{}` and separates elements with commas:

```spel
{1, 2, 3, 4}
{'red', 'green', 'blue'}
{true, false, null}
```

When evaluated, SpEL returns a Java `List` object. `{}` represents an empty list.

Java example:

```java
ExpressionParser parser = new SpelExpressionParser();

List<?> numbers = parser.parseExpression("{1, 2, 3, 4}")
        .getValue(List.class);

List<?> colors = parser.parseExpression("{'red', 'green', 'blue'}")
        .getValue(List.class);
```

An inline list is suitable when the list is part of a rule, configuration, or expression. If the data already resides in an application property or collection, you can access that property directly instead of copying the data into the expression.

## 2. Nested lists

An element of an inline list can be another inline list. This syntax creates a multi-level structure:

```spel
{{'a', 'b'}, {'x', 'y'}}
```

The result is a `List` with two elements, each of which is a `List` of two strings. Example:

```java
Expression expression = parser.parseExpression("{{'a', 'b'}, {'x', 'y'}}");
List<?> matrix = expression.getValue(List.class);

List<?> firstRow = (List<?>) matrix.get(0);
String firstValue = (String) firstRow.get(0); // "a"
```

Nested lists are useful for small configurations in the form of groups, tables, or matrices. If the structure is large, changes frequently, or requires strict data type checking, manage the data in Java configuration or dedicated objects.

## 3. When does SpEL create a constant list?

SpEL inspects the structure of the inline list's elements. If all elements are constants, or are nested inline lists that themselves contain only constants, SpEL can create a constant list representing the expression node.

Examples of lists that can be considered constant:

```spel
{1, 2, 3}
{'READ', 'WRITE', 'DELETE'}
{true, false, null}
{{'a', 'b'}, {'x', 'y'}}
```

In these examples, the value of each element does not depend on the root object, variables, methods, or runtime data. Nested lists also contain only fixed values, so the entire structure can be created as a constant value.

The constant list is created lazily on the first evaluation that needs that value, and then retained in the expression node so subsequent `getValue()` calls reuse it. This way, SpEL avoids rebuilding the same collection on every evaluation.

This is an AST/evaluation optimization in SpEL, not synonymous with having to enable the SpEL bytecode compiler. Constant-list optimization can be applied when the expression is evaluated under normal interpreted execution.

## 4. When is a list not constant?

If an element depends on runtime data, the entire inline list containing that element cannot be considered constant. SpEL needs to evaluate the dynamic element and create a list result matching the current evaluation.

Example:

```spel
{#primary, #secondary}
{1, #limit, 3}
{customer.name, 'UNKNOWN'}
{#service.nextId(), #service.nextId()}
```

The expressions above use variables, object properties, or method calls. Results can change depending on the evaluation context or the state of the object/method, so the entire list cannot be cached as a constant.

Example with variables:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("{#primary, #secondary}");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("primary", "READ");
context.setVariable("secondary", "WRITE");

List<?> first = expression.getValue(context, List.class);

context.setVariable("primary", "VIEW");
List<?> second = expression.getValue(context, List.class);
```

The first evaluation creates a list containing `READ` and `WRITE`; the next pulls the new value from the context and creates a result containing `VIEW` and `WRITE`. The parsed Expression can be reused, but dynamic values are still evaluated against the context of each call.

## 5. Nested lists with dynamic elements

The constant rule applies recursively to nested structures. If all elements of every sublist are constant, the parent list can also be constant. As soon as one branch contains a runtime expression, the parent list is no longer wholly constant.

```spel
{{'a', 'b'}, {'x', 'y'}}
```

The entire structure is constant.

```spel
{{'a', #currentValue}, {'x', 'y'}}
```

The first sublist contains the `#currentValue` variable, so it is not constant. The outer list also cannot be cached as a complete constant list.

This matters when building multi-level configuration tables: even a small literal mixed with a dynamic variable or property forces the entire list containing it to be re-evaluated.

## 6. Using inline lists in Java and Spring configuration

In Java, parse the expression once and evaluate when needed:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression permissionsExpression = parser.parseExpression(
        "{'READ', 'WRITE', 'DELETE'}");

List<?> permissions = permissionsExpression.getValue(List.class);
```

In Spring, inline lists can also appear in `@Value`. Because `@Value` uses `#{...}` to surround SpEL, the curly braces of the inline list form a nested pair:

```java
@Component
public class AccessConfiguration {

    @Value("#{{'READ', 'WRITE', 'DELETE'}}")
    private List<String> permissions;
}
```

Here the outer `#{...}` is the SpEL delimiter in the annotation; the inner `{...}` is the inline list syntax. The result is converted into the `permissions` property via Spring's type conversion mechanism.

If an expression needs a root object or variables, supply them via `EvaluationContext` when using the SpEL API directly. Do not concatenate user data into expression source to build a list; pass data through variables or clearly typed properties.

## 7. Constant lists and modifying collections

A constant list is a value cached and reused by SpEL for the same expression node. Therefore, you should not treat a constant list result as a fresh, independent collection for each `getValue()` call.

In particular, do not modify the contents of a list returned from a constant expression. If a caller adds, removes, or replaces elements on the reused object, subsequent evaluations may observe the mutated state. APIs should also not depend on whether that collection permits mutation.

If you need a mutable list for separate processing, create a copy on the Java side:

```java
Expression expression = parser.parseExpression("{'READ', 'WRITE'}");
List<?> evaluated = expression.getValue(List.class);

List<Object> mutableCopy = new ArrayList<>(evaluated);
mutableCopy.add("ADMIN");
```

`mutableCopy` is a new collection owned by the application; modifying it does not alter the constant value held in the expression.

For inline lists with dynamic elements, each evaluation produces a result based on the current runtime values. Even so, if you need to edit the list, still establish ownership clearly and make a copy when the list is not owned by the caller.

## 8. A constant list is not an immutable domain model

The word "constant" here describes SpEL recognizing and caching the value of an expression node. Do not infer that the elements or the collection are guaranteed immutable under a Java API contract.

For example, a list containing reference objects may hold mutable objects inside. If an element is an object kept as a constant reference, mutating internal state of that object is a separate issue from SpEL rebuilding the list. Therefore:

- Prefer immutable literals such as Strings, numbers, Booleans, and null for constant lists.
- Do not place mutable objects into a structure the application intends to treat as immutable configuration.
- If editable data is needed, create new objects or collections at the application layer.
- Do not use constant inline lists to store state across requests.

## 9. Distinguishing inline lists, array initializers, and collections from variables

These three ways of creating or obtaining a collection serve different purposes:

| Syntax | Result | When to use |
| --- | --- | --- |
| `{1, 2, 3}` | Java `List` | Small list described directly in the expression. |
| `new int[]{1, 2, 3}` | Java array `int[]` | Need an array with a specific element type. |
| `items` or `#items` | Existing collection in root object/context | Data managed by the application that can change independently of the expression. |

An inline list does not automatically create a Java array. If an API requires `int[]`, use array construction or an intentional type conversion at the application layer.

## 10. Expression reuse and performance

Parsing an expression once and reusing it is usually more efficient than re-parsing the same string on every request:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression fixedPermissions = parser.parseExpression(
        "{'READ', 'WRITE', 'DELETE'}");

for (int i = 0; i < 100; i++) {
    List<?> permissions = fixedPermissions.getValue(List.class);
    // use as read-only data
}
```

With a constant inline list, SpEL can also reuse the constant value instead of creating a new list on each evaluation. With an inline list containing variables or runtime properties, the dynamic elements still have to be evaluated and the result list built per call.

Do not turn every collection into an inline list solely expecting optimization. If data is large, loaded from a database, changes frequently, or is shared across components, let the application manage it with an appropriate collection or service. Constant-list optimization is most useful for small, fixed sets of values belonging to the expression itself.

## 11. Common errors and how to handle them

| Symptom | Cause to check | Resolution |
| --- | --- | --- |
| Expecting list to change but result stays the same | Expression contains only literals, so SpEL caches a constant list. | Use dynamic variables/properties if values must vary with context; do not try to use a constant expression to store state. |
| Modifying list affects subsequent evaluations | Caller mutated a constant value reused by the expression. | Treat constant list results as read-only; create `new ArrayList<>(result)` before modifying. |
| List is not optimized into a constant | At least one element is a variable, property, method call, or runtime expression. | Identify the dynamic element; this is necessary behavior if the value depends on runtime. |
| Parent list is not constant even though many elements are literals | A nested sublist contains a dynamic element. | Check the entire nested structure; one dynamic branch prevents the parent list from being wholly constant. |
| `@Value` cannot parse inline list | Confusing annotation's `#{...}` delimiter with list's `{...}`. | Use nested form such as `@Value("#{{'READ', 'WRITE'}}")`. |
| API expects an array but receives a List | `{...}` creates a Java List. | Use `new int[]{...}` or convert explicitly to the required array type. |
| Expression produces different results across requests | Variables or root object change per EvaluationContext. | Use the right context for each request; parsed expressions can be reused, but runtime data must be supplied separately. |

## Takeaways

- `{...}` creates a Java `List`; `{}` is an empty list.
- Inline lists can be nested to represent multi-level structures.
- If all elements are constants, including nested inline lists that contain only constants, SpEL can create and cache a constant list.
- A constant list is created lazily when needed and reused across evaluations, reducing collection construction work and garbage.
- Variables, properties, or method calls make the list runtime-dependent; those values are re-evaluated when the expression runs.
- A dynamic branch in a sublist prevents the parent list structure from remaining wholly constant.
- Constant describes an internal expression optimization, not a guarantee that the collection is immutable.
- Treat constant list results as read-only; create a mutable copy if changes are needed.
- `{...}` returns a List; `new int[]{...}` creates an array.
- Parse expressions once and reuse them; keep changing data in the context or objects managed by the application.

## References

- [Spring Framework Reference — Inline Lists](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/inline-lists.html)
- [Spring Framework API — InlineList](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/ast/InlineList.html)
- [Spring Framework source — InlineList](https://github.com/spring-projects/spring-framework/blob/main/spring-expression/src/main/java/org/springframework/expression/spel/ast/InlineList.java)