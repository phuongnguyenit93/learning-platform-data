# `#this` and the Current Object in SpEL Scope

## Objectives

In Spring Expression Language (SpEL), `#this` represents the object currently being evaluated at the current position. This object is called the *active evaluation object* or *current object*. The value of `#this` can change when SpEL enters a child scope, especially in collection selection (`.?[...]`) and collection projection (`.![...]`).

`#root` represents the root object of the entire evaluation. The root object remains stable throughout the evaluation, even when SpEL is processing individual elements in a collection.

Distinguishing these two special variables helps expressions state clearly which property belongs to the current object and which property belongs to the root object. For example, in `members.?[#this.score >= #root.minimumScore]`, `#this.score` is the score of the member being evaluated, while `#root.minimumScore` is the threshold on the root object.

## 1. `#this` at the top level

When an expression begins evaluating, `#this` usually points to the same object as `#root`. If the root object is a `Person`, the following expressions have equivalent meaning:

```spel
name
#this.name
#root.name
```

`name` is a property resolved implicitly on the current object. `#this.name` explicitly states that the property belongs to the active object. `#root.name` explicitly states that the property belongs to the root object.

Java example:

```java
ExpressionParser parser = new SpelExpressionParser();
Person person = new Person("Lan", 28);
StandardEvaluationContext context = new StandardEvaluationContext(person);

String implicitName = parser.parseExpression("name")
        .getValue(context, String.class);

String currentName = parser.parseExpression("#this.name")
        .getValue(context, String.class);

String rootName = parser.parseExpression("#root.name")
        .getValue(context, String.class);
```

All three expressions read the name of the root `person` in this example. At the top level, `#this` and `#root` point to the same root object.

## 2. Where is the root object set?

The root object is supplied to the evaluation context or to a specific `getValue` call. You can set the root when creating `StandardEvaluationContext`:

```java
StandardEvaluationContext context = new StandardEvaluationContext(person);
```

Or create the context first and then set the root:

```java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setRootObject(person);
```

You can also pass the root object directly to a `getValue` overload:

```java
Expression expression = parser.parseExpression("#root.name");
String name = expression.getValue(context, anotherPerson, String.class);
```

In this evaluation, `anotherPerson` is the root object used for the expression. When no root object is passed in that overload, SpEL uses the root object set in the context.

`EvaluationContext` is the container that holds the root object, variables, property accessors, method resolvers, type converters, and other evaluation mechanisms. It is not the root object itself.

## 3. `#this` changes in collection selection

Selection uses `.?[condition]` to filter elements in a collection. When SpEL evaluates the condition for each element, `#this` points to the current element being checked.

Suppose the root object `Society` has a `members` property, where each element is an `Inventor`:

```spel
members.?[nationality == 'Serbian']
```

In this condition, `nationality` is resolved on each `Inventor` being checked. Writing `#this` explicitly gives an equivalent result:

```spel
members.?[#this.nationality == 'Serbian']
```

You can combine the current object with the root object:

```spel
members.?[#this.score >= #root.minimumScore]
```

Here:

- `#this` is each `Inventor` being checked.
- `#this.score` is the score of the current inventor.
- `#root` remains the original `Society`.
- `#root.minimumScore` is the score threshold retrieved from the society.

Java example:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(
        "members.?[#this.score >= #root.minimumScore]");

StandardEvaluationContext context = new StandardEvaluationContext(society);
List<?> eligibleMembers = expression.getValue(context, List.class);
```

Selection changes the active object while evaluating each condition, without changing the root object.

## 4. `#this` changes in collection projection

Projection uses `.![projectionExpression]` to compute a value for each element. In the sub-expression, `#this` is the current element being projected:

```spel
members.![name]
members.![#this.name]
members.![#this.placeOfBirth.city]
```

In the second example, `#this.name` reads the name of the current inventor. You can reference the root object at the same time:

```spel
members.![#this.name + ' - ' + #root.name]
```

Assuming `#root.name` is the society name, each result combines the member's name with the society's name. `#this` changes for each member, while `#root` remains the society.

Java example:

```java
Expression expression = parser.parseExpression(
        "members.![#this.name + ' - ' + #root.name]");

List<?> labels = expression.getValue(
        new StandardEvaluationContext(society), List.class);
```

Projection produces one value for each source element. `#this` lets the sub-expression clearly access the object being transformed.

## 5. Unprefixed properties and `#this.property`

Within a selection/projection scope, unprefixed properties are typically resolved on the current active object. Therefore:

```spel
members.?[active == true]
members.?[#this.active == true]
members.![name]
members.![#this.name]
```

are equivalent forms for accessing the current property.

Use the concise property form when the expression is simple. Use `#this` explicitly when:

- The expression also references `#root`.
- There are multiple object levels and you need to avoid confusing which object a property belongs to.
- Future readers of the expression need to see the current object clearly.
- A condition or projection has multiple operands and method calls.

`#this` is not a variable name registered by the application. It is a special variable provided by SpEL during evaluation; there is no need to call `setVariable("this", ...)`.

## 6. Nested scopes

Selection and projection can be nested. Each inner collection scope sets the active object to the element currently being processed in that scope. Therefore, when entering an inner projection or selection, `#this` represents the element of the innermost scope.

For example, a society has multiple departments, and each department has multiple employees:

```spel
departments.![employees.![#this.email]]
```

In the innermost projection, `#this` is the current employee. The result is a list of email lists, one sublist per department.

Example of nesting selection inside projection:

```spel
departments.![employees.?[#this.active == true].![#this.email]]
```

In the inner selection, `#this` is the employee being checked; in the projection after the selection, `#this` continues to be the employee being projected. `#root` still points to the original root object of the entire expression.

Do not assume `#this` inside a nested scope is still the outer scope's element. If you need data from the root object, use `#root`. If you need data from an intermediate parent object, access it via a path from root or design the expression/helper so the parent object is clearly provided via a context variable.

## 7. `#this`, `#root`, and expression variables

These three reference forms often appear together but serve different roles:

| Syntax | Role | How the value is created |
| --- | --- | --- |
| `#root` | Root object of the evaluation pass. | Set via `EvaluationContext` or a `getValue` overload. |
| `#this` | Active object in the current scope. | Automatically updated by SpEL during evaluation, e.g. each selection/projection element. |
| `#threshold` | Variable passed into the expression by the application. | Registered via `context.setVariable("threshold", value)`. |

Example:

```java
StandardEvaluationContext context = new StandardEvaluationContext(society);
context.setVariable("threshold", 80);
```

```spel
members.?[#this.score >= #threshold and #root.enabled]
```

In this expression, `#this.score` is the score of the member being evaluated, `#threshold` is application-provided data, and `#root.enabled` is the state on the society.

Variable registration does not include `#`; `#` appears only when referencing the variable in an expression. `#root` and `#this` are two special variables built into SpEL.

## 8. `#this` when calling methods

In a scope where the current object is a collection element, you can invoke methods on that element via `#this`:

```spel
members.?[#this.isEligible()]
members.![#this.getDisplayName()]
```

If a method is a property-style getter, SpEL usually allows accessing it by property name:

```spel
members.![displayName]
```

The method is called on the current object of the scope. If a method has side effects, it may be called many times as SpEL iterates over the collection; prefer data-reading or pure computation methods in selection/projection.

## 9. Distinguishing the current object from an object accessed via a property

`#this` is the current object of the evaluation scope. A property accessed from that object may return another object, but reading a property does not mean the root object of the entire evaluation changes.

Example:

```spel
customer.address.city
```

At the top level, the root/current object is customer. `address` is an object accessed from customer, and `city` is a property of address. If you need to make the path explicit, you can write:

```spel
#root.customer.address.city
```

In selection/projection, the active object is the collection element. Subsequent properties form a path from that element; root remains unchanged.

Do not confuse `#this` with "the last object in a property path". When you need to state clearly which scope an object belongs to, use `#this` for the current element and `#root` for the root object.

## 10. Common mistakes and fixes

| Symptom | Causes to check | How to fix |
| --- | --- | --- |
| `#this` returns a different object than expected in `.?[]` | In selection, the current object is the element being checked. | Use `#this.property` for the element; use `#root.property` for root. |
| Using `#root` when intending to read the current element | `#root` does not change when iterating over a collection. | Use `#this` or an unprefixed property within the selection/projection scope. |
| Nested expression reads the wrong object | `#this` switches to the element of the innermost collection scope. | Identify the current scope at that expression position; use a path from `#root` when root is needed. |
| `#this` does not have the expected value at the top level | Root object was not provided or the `getValue` call used a different root. | Check `StandardEvaluationContext` and the `getValue(context, rootObject)` overload. |
| Confusing `#this` with an application variable | `#this` is a special variable managed by SpEL. | Do not register a `this` variable; use a distinct name like `#threshold` for application data. |
| Short property form is hard to read with multiple objects | Properties are resolved on the current active object. | Write `#this.property` or `#root.property` explicitly. |
| Method gets called multiple times in projection | The sub-expression is evaluated once per element. | Avoid side effects; precompute data or use pure read methods. |

## Takeaways

- `#this` is the active evaluation object at the position where the expression is running.
- At the top level, `#this` usually matches `#root`.
- `#root` is the root object of the entire evaluation and does not change when SpEL iterates over collections.
- In selection `.?[...]`, `#this` is the element being checked.
- In projection `.![...]`, `#this` is the element being projected.
- An unprefixed property in a selection/projection scope is resolved on the current object; `#this.property` explicitly states the same meaning.
- In nested scopes, `#this` belongs to the innermost collection scope; do not assume it is still the parent element.
- `#threshold` is an application variable registered in the context; `#this` and `#root` are special variables provided by SpEL.
- Set the root via the context constructor/setter or an appropriate `getValue` overload.
- Use `#this` and `#root` explicitly to avoid confusing objects in complex expressions.

## References

- [Spring Framework Reference — Variables (`#this` and `#root`)](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/variables.html)
- [Spring Framework Reference — Collection Selection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html)
- [Spring Framework Reference — Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-projection.html)
- [Spring Framework API — EvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationContext.html)
- [Spring Framework API — StandardEvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)