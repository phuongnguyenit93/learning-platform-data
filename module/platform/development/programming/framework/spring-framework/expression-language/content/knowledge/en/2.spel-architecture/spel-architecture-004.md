# Root object, active context object, and variables in SpEL

## Objective

When SpEL evaluates an expression, it needs to know which object the expression starts from, which object is being processed at the current position, and what external values are passed in. These three concepts correspond to the root object, active object, and expression variables.

Key point to remember: `EvaluationContext` is where the information and mechanisms needed for evaluation are provided; it is not the root object itself. Inside an expression, `#root` points to the root object, `#this` points to the object currently being processed, and `#variableName` accesses a variable registered in the context.

## 1. Three data sources in an expression

| Component | Syntax | Meaning |
| --- | --- | --- |
| Root object | `#root` | The root object from which the evaluation starts. This value remains unchanged throughout the evaluation. |
| Active object | `#this` | The object currently being processed by the expression. At the top level, it usually matches the root object; inside selection or projection, it switches to each element. |
| Expression variable | `#minPrice` | A value supplied by the application into `EvaluationContext` under a variable name. |
| Property of current object | `price` | A property resolved on the current active object. |

Therefore, `price` and `#price` can carry different meanings: `price` looks up a property on the active object, whereas `#price` looks up a variable named `price` in the evaluation context.

## 2. Root object: the root object of the evaluation

The root object is the starting point for SpEL to resolve properties, methods, and other accesses. You can set the root object when creating `StandardEvaluationContext`:

```java
Order order = orderService.findById(42L);
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context = new StandardEvaluationContext(order);

String customerName = parser.parseExpression("customer.name")
        .getValue(context, String.class);

String explicitCustomerName = parser.parseExpression("#root.customer.name")
        .getValue(context, String.class);
```

At the top level, `customer.name` is resolved from the root object. Writing `#root.customer.name` yields the same result while making it explicit that the path starts from the root object. Explicit notation is useful when the expression descends into a collection or spans multiple object levels.

You can create the context first and set the root object with `setRootObject`:

```java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setRootObject(order);
```

Additionally, the `getValue(context, rootObject)` overload allows supplying a root object for a specific evaluation:

```java
String id = parser.parseExpression("#root.id")
        .getValue(context, anotherOrder, String.class);
```

In this call, `anotherOrder` is the root object used to evaluate the expression. If no root object is passed in the call, SpEL uses the root object already set in the context.

## 3. Active object: the current object via `#this`

`#this` represents the object that SpEL is processing at the current position. When evaluation begins, `#this` usually matches `#root`. The difference becomes clear in collection selection (`.?[]`) and projection (`.![]`) operators.

- Selection filters elements that satisfy a condition.
- Projection transforms each element into a resulting value or object.
- Inside the per-element condition or expression, `#this` points to the element being processed.
- `#root` still points to the original root object.

Suppose the root object is an `Order` with an `items` property, and each element is a `LineItem`:

```spel
items.?[price >= 100]
```

In the condition above, `price` is looked up on each `LineItem` being examined. It can be written explicitly using `#this`:

```spel
items.?[#this.price >= 100]
```

If you need to compare against a property of `Order`, use `#root`:

```spel
items.?[#this.price >= #root.minimumPrice]
```

Here `#this.price` is the price of the current line item, while `#root.minimumPrice` is the price threshold on the root order. When moving to projection, `#this` continues to represent each element:

```spel
items.![#this.productName]
```

The expression above returns a list of product names. In nested selections or projections, interpret `#this` according to the active scope at the position where the expression is evaluated; `#root` remains the root point of the entire evaluation.

## 4. Expression variables: passing data via `#variableName`

An application can pass parameters into an expression through `EvaluationContext`. With `StandardEvaluationContext`, use `setVariable` to register a variable:

```java
context.setVariable("minPrice", new BigDecimal("100.00"));
```

In SpEL, reference a variable using the `#` symbol:

```spel
items.?[#this.price >= #minPrice].![#this.productName]
```

Complete example:

```java
Order order = orderService.findById(42L);
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context = new StandardEvaluationContext(order);
context.setVariable("minPrice", new BigDecimal("100.00"));

Expression expression = parser.parseExpression(
        "items.?[#this.price >= #minPrice].![#this.productName]");
List<?> productNames = expression.getValue(context, List.class);
```

In this example:

- `order` is the root object.
- `#this` is each `LineItem` in turn as selection and projection run.
- `#minPrice` is the value passed by the application into the context.
- The result is the list of `productName` values for line items whose price is at least the passed threshold.

The name passed to `setVariable` does not include `#`; the `#` prefix only appears when referencing the variable in the expression. You can read back a registered value with `lookupVariable`:

```java
Object minPrice = context.lookupVariable("minPrice");
```

Variables can hold objects, strings, numbers, dates, or other values that the expression needs. If a variable name matches an object property, distinguish them clearly: `price` accesses a property on the active object, whereas `#price` accesses a variable in the context.

## 5. Distinguishing variables, functions, and Spring beans

Syntax with `#` does not always point to an ordinary variable:

- `#minPrice`: variable registered with `setVariable("minPrice", value)`.
- `#root` and `#this`: special variables provided by SpEL for the root object and active object.
- `#calculateTax(...)`: invocation of a function registered in the evaluation context, for example via `registerFunction`.
- `@pricingService`: reference to a Spring bean when the context has an appropriate `BeanResolver`. This is a bean reference mechanism, not an expression variable.

When reading an expression, check how names are registered in the context rather than assuming every name is a property of the root object.

## 6. Choosing the right EvaluationContext

`StandardEvaluationContext` provides extensive capabilities for resolving properties, methods, types, constructors, beans, and functions. It is suitable when the application needs full SpEL features and explicitly controls which capabilities are enabled.

`SimpleEvaluationContext` is designed for data binding scenarios where features need to be restricted. You can configure property accessors and the necessary level of method invocation support; this context removes powerful capabilities such as type references, constructors, and bean references.

If the expression comes from a user or untrusted source, restrict the allowed property accessors and method resolvers. Avoid evaluating untrusted expressions with a `StandardEvaluationContext` that has full access permissions. For input data, pass values through context variables rather than concatenating strings directly into the expression text. Only put into the context data that the expression is permitted to read.

When evaluating for multiple users or multiple requests, manage the lifecycle of the context and variables within the proper scope. Do not allow variable values from a previous request to accidentally be used in a subsequent request.

## 7. How to read and handle common errors

| Symptom | Cause to check | How to handle |
| --- | --- | --- |
| `price` reads from the wrong object inside `.?[]` | `#this` has switched to the current collection element. | Use `#this.price` for the element or `#root.price` for the root object. |
| `#minPrice` does not have the expected value | Variable was not registered, name is misspelled, or the context being used is not the configured one. | Call `setVariable` before `getValue` and verify the variable name. |
| Property sharing a name with a variable causes confusion | `name` and `#name` are resolved through two different mechanisms. | Use `#` explicitly when intending to read a variable. |
| Selection or projection result differs from expectation | The expression is running within the active object scope of the collection element. | Identify the current object at each step; use `#root` when needing to return to the root object. |
| Numeric comparison behaves unexpectedly | The two values have different numeric types or conversion rules. | Pass values with an appropriate type, e.g., using `BigDecimal` for monetary data. |

## Key takeaways

- `#root` is the root object of the evaluation and remains unchanged inside selections/projections.
- `#this` is the object currently being processed; it usually equals the root object at the top level and switches to each element inside selections/projections.
- `#variableName` is a value registered by the application in `EvaluationContext`.
- Unprefixed properties without `#` are resolved on the current active object.
- `EvaluationContext` holds the root object, variables, and resolution mechanisms; it is not synonymous with the root object.