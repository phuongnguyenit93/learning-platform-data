# A SpEL Learning Path from Basic Syntax to Safe Integration

Spring Expression Language (SpEL) is the expression language of the Spring ecosystem. SpEL lets you read properties, invoke methods, compute values, query collections, and reference beans using an expression string that is parsed and then evaluated in a specific context. SpEL appears in many Spring integration points, such as `@Value`, bean configuration, and several conditional mechanisms.

This article lays out a layered learning path: understand how expressions are executed, master the syntax, work with objects and collections, pass data through an evaluation context, integrate into Spring, and restrict evaluation permissions to avoid turning expressions into an arbitrary code execution point.

## 1. Objectives and Prerequisites

After this lesson, you will be able to:

- Explain the roles of the parser, expression, and evaluation context.
- Write expressions using literals, operators, properties, indexes, methods, and conditionals.
- Pass a root object, variables, and functions into an expression.
- Use selection and projection to filter or transform collections.
- Recognize how SpEL is used in `@Value` and Spring integration points.
- Choose an appropriate evaluation context and restrict expression capabilities when input data is untrusted.

You should know basic Java, objects and collections, Spring IoC/Dependency Injection, how Spring creates beans, and how annotations are read. You do not need to learn all of Spring before starting SpEL; you only need to understand what a bean is and how an expression is evaluated at runtime.

## 2. The Big Picture: How Is an Expression Executed?

The basic process has three parts:

1. **Parser** receives the expression string and parses its syntax.
2. **Expression** represents the parsed expression. You can request the expression to return a value or set a value if the context permits.
3. **EvaluationContext** provides the data and permissions the expression is allowed to use: root object, variables, functions, property accessors, method resolvers, type locators, bean resolvers, and type conversion mechanisms.

The execution flow can be pictured as follows:

    Expression string
          |
          v
    SpelExpressionParser
          |
          v
    Expression (parsed expression tree)
          |
          v
    getValue(EvaluationContext)
          |
          v
    Result or evaluation error

Minimal example:

    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression("'Hello ' + 'Spring'");
    String result = expression.getValue(String.class);

The result is `Hello Spring`. This example needs no root object because the expression only operates on literals.

Distinguish parsing errors from evaluation errors. Parsing errors occur when the string has invalid syntax. Evaluation errors occur when the expression is valid, yet data or permissions in the context do not meet requirements, such as accessing a nonexistent property or calling an unsuitable method.

## 3. Stage One: Mastering Foundational Syntax

### 3.1. Literals and Data Types

SpEL supports common literals such as strings, numbers, booleans, and null. Strings in expressions use single quotes:

- `'Spring'` is a string.
- `42`, `3.14` are numbers.
- `true`, `false` are booleans.
- `null` is the null value.

Expressions can combine literals with operators:

    10 + 5
    100 / 4
    'Spring' + ' Framework'
    7 > 3
    true and false

### 3.2. Operators

Groups of operators to learn in order:

- Arithmetic: `+`, `-`, `*`, `/`, `%`, `^`.
- Comparison: `==`, `!=`, `<`, `>`, `<=`, `>=`, `between`, `instanceof`, `matches`.
- Logical: `and`, `or`, `not` or `!`.
- Conditional: `condition ? valueA : valueB`.
- Elvis: `value ?: fallback`, using a fallback value when the left-hand side is null.

For example:

    #quantity > 0 and #price >= 0
    #score >= 80 ? 'pass' : 'retry'
    #displayName ?: 'Guest'

Comparison and logical expressions are especially useful for expressing configuration conditions. For long business rules with multiple branches or complex debugging needs, move the logic to Java for easier testing and maintenance.

### 3.3. Property, Method, and Index Access

When the root object is a Java object, an expression can read properties and call methods:

    name
    customer.name
    customer.getName()
    customer.address.city
    customer.tags[0]
    settings['timeout']

For maps, keys can be accessed using index syntax. For lists or arrays, indexes start at 0. Accessing nested properties requires each intermediate object to exist; if one link is null, ordinary access can raise an error.

Safe navigation `?.` helps avoid errors when the object immediately before the operator is null:

    customer?.address?.city

When using safe navigation, the result on a null branch is null. Do not treat this operator as a complete data validation mechanism: you still need to define whether null is valid and handle the resulting value in the calling layer.

### 3.4. Type References and Object Creation

The `T(...)` operator references a Java type by its fully qualified name. For example:

    T(java.lang.Math).max(12, 30)
    T(java.lang.Math).PI

SpEL also has `new` syntax to invoke constructors when the evaluation context allows:

    new java.math.BigDecimal('19.95')

Type references and constructors significantly increase an expression's capabilities. Only use them in application-controlled expressions and in contexts with appropriate permissions. Do not open these capabilities to strings supplied by external users.

## 4. Stage Two: Root Object, Variables, and Functions

### 4.1. Root Object

The root object is the default object an expression accesses when a property name has no prefix. For example, if the root is `Order`, the expression `total` can read the order's total property.

    Order order = ...;
    Expression expression = parser.parseExpression("total");
    Object total = expression.getValue(context, order);

Inside an expression, `#root` represents the root object. `#this` represents the current object at the point of evaluation; in some collection operations, the current object can differ from root.

### 4.2. Variables

Variables have the `#` prefix. The application sets variables in the context before evaluation:

    StandardEvaluationContext context = new StandardEvaluationContext();
    context.setVariable("quantity", 3);
    context.setVariable("price", 12.5);
    Expression expression = parser.parseExpression("#quantity * #price");
    Double total = expression.getValue(context, Double.class);

Using variables lets expressions receive data explicitly without embedding data into the string. This approach also makes testing easier because each evaluation can supply a context with its own data.

### 4.3. Functions

You can register a Java method as a function in the context and call it using `#functionName(...)` syntax. Functions must be explicitly registered by the application. Only register small functions with clear inputs and results; avoid placing a general service with many side effects into the expression context.

## 5. Stage Three: Working with Collections

SpEL supports operations on lists, arrays, and collections. Two important capabilities are selection and projection.

### 5.1. Selection — Filtering Elements

Selection uses `.?[...]` to retain elements matching a condition. For example, given a collection `orders` with a `total` property:

    orders.?[total > 100]

Two useful variants:

- `.^[...]` retrieves the first element matching the condition.
- `.$[...]` retrieves the last element matching the condition.

Inside the predicate, `#this` represents the element currently being examined. Keep conditions short, with consistent data types, and avoid calling methods with side effects.

### 5.2. Projection — Transforming Elements

Projection uses `.![]` to build a resulting collection from an expression applied to each element:

    orders.![customerName]
    products.![price]

Selection returns the original elements matching the condition; projection returns values computed from each element. You can combine both operations, but split long expressions into Java steps for readability and testability.

### 5.3. Inline Lists and Maps

SpEL supports declaring collections directly inside an expression:

    {1, 2, 3}
    {'red', 'green', 'blue'}
    {name: 'Spring', version: 6}

Inline collections fit short configurations. For large data, frequently changing data, or data needing validation, create the collection in Java and pass it into the context.

## 6. Stage Four: Integrating SpEL in Spring

### 6.1. Using SpEL with `@Value`

`@Value` is a common integration point. SpEL expressions are placed inside `#{...}`:

    @Value("#{2 * T(java.lang.Math).PI}")
    private double circumferenceFactor;

Another example is reading a property of a Spring-managed bean:

    @Value("#{@pricingPolicy.defaultRate}")
    private BigDecimal defaultRate;

The `@beanName` syntax references a bean through a bean resolver provided by Spring. That means the expression can depend on the container, and the corresponding bean must exist with a matching name.

### 6.2. Distinguishing Placeholders and SpEL

Two syntaxes often appear close together yet serve different purposes:

- `${app.name}` is a placeholder for retrieving a configuration value from property sources.
- `#{...}` is a SpEL expression that is evaluated.

Placeholders substitute configuration values; SpEL evaluates expressions against values and objects in the context. When reading `@Value`, clearly identify whether you need plain configuration retrieval or calculation/object reading.

### 6.3. Template Expressions

When a string contains both ordinary text and expressions, use template parsing. `TemplateParserContext` uses `#{` and `}` as delimiters by default:

    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression(
        "Hello #{#name}", new TemplateParserContext());
    context.setVariable("name", "Spring");
    String message = expression.getValue(context, String.class);

The result is `Hello Spring`. Templates are useful for display strings, though template content must also be controlled by the application if evaluated with a broadly privileged context.

## 7. Stage Five: Choosing the Right EvaluationContext

The evaluation context determines what an expression can see and do. This is the most critical point when moving from learning examples to real applications.

### 7.1. StandardEvaluationContext

`StandardEvaluationContext` provides broad capabilities: root object, variables, functions, property accessors, method resolvers, type locators, constructor resolvers, and bean resolvers. It fits cases where the application fully trusts the expression and requires extensive customization.

Because it can extend to type, constructor, method, and bean access, this context has very broad permissions. Do not use it to directly evaluate expressions submitted by users, tenants, or external sources.

### 7.2. SimpleEvaluationContext

`SimpleEvaluationContext` is designed for scenarios requiring restricted features, especially data binding. Example of a read-only property access context:

    SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

You can choose read-write mode when the business case genuinely needs to update properties and the target object is controlled. The simple context does not provide all powerful features of the standard context; higher-privilege features must be intentionally configured and reviewed for risk before enabling.

### 7.3. Principle of Least Privilege

When designing a context, ask yourself:

1. What is the root object? Does it contain sensitive data or references to services?
2. Does the expression need to invoke methods or only read properties?
3. Are type references, constructors, or beans truly needed?
4. Which variables and functions are allowed to appear?
5. Can `SimpleEvaluationContext` be used instead of `StandardEvaluationContext`?
6. Is the result type-checked and null-checked before use?

Place into the context only the exact data and capabilities required for a specific purpose. Do not use a single all-privileged context shared across every kind of expression in the system.

## 8. Stage Six: Safe Integration

SpEL is an expression language capable of accessing objects and invoking behavior depending on the context. If an application takes strings from users and evaluates them with a highly privileged context, expressions can become an unintended execution path.

### 8.1. Do Not Evaluate Untrusted Expressions with a Full-Privilege Context

Do not concatenate user input into an expression string and call `parseExpression(...).getValue(...)`. An anti-pattern to avoid is accepting an arbitrary expression from a request and evaluating it with a `StandardEvaluationContext` that has a bean resolver or method-invocation permissions.

If the product truly needs users to define conditions, design a restricted condition language or a permitted set of expressions. Syntax and data validation do not substitute for restricting execution permissions.

### 8.2. Use Allowlists and Restricted Contexts

- Allow only defined properties; use small DTOs instead of passing large entities or services.
- Prefer `SimpleEvaluationContext` in read-only mode when only reading data is needed.
- Register only functions that have been reviewed and have no unintended side effects.
- Do not register a bean resolver, type locator, or constructor resolver if the use case does not need them.
- Do not allow expressions to choose arbitrary classes, beans, or methods.
- Limit expression length and count at the application layer to prevent oversized inputs.

### 8.3. Separate Parsing and Evaluation

If expressions are fixed configuration owned by the application, you can parse once and reuse the `Expression`. Each evaluation should receive a context with data appropriate for that call. Avoid storing a context containing request data or user data in a singleton and reusing it across requests.

Do not treat parsing once as proof that an expression is safe. Parsing only checks syntax; execution permissions depend on the context at evaluation time.

### 8.4. Validate Results and Errors

Handle these scenarios explicitly:

- Malformed expression syntax.
- Nonexistent property or method.
- Null value in the middle of a path.
- Result type incompatible with the target type.
- Out-of-bounds index or missing key.
- Method/function throwing an exception during execution.

Do not return stack traces or internal bean details to clients. Log enough information for operations and debugging, while avoiding logging sensitive data or entire expressions that may contain secrets.

### 8.5. Minimize Side Effects

Prefer read-only expressions with deterministic results. Avoid methods that mutate state, make network calls, write to databases, or perform expensive operations. When business operations require side effects, call services from Java in a controlled flow instead of hiding that behavior inside an expression.

## 9. Process for Building a Real Use Case

Suppose an application needs to evaluate a condition for displaying a promotion based on order data. You can implement it in the following sequence:

1. Identify minimal inputs: total amount, customer status, and item count.
2. Create a DTO containing only the properties that need to be read; do not pass an entire entity graph or Spring service.
3. Write a short expression, such as `total >= 100 and customerLevel == 'GOLD'`.
4. Parse the configured expression at startup or when configuration is updated.
5. Create a restricted context and set a root object or variables with explicit types.
6. Evaluate with the expected result type, such as Boolean.
7. Handle null, parse errors, and evaluation errors according to application policy.
8. Write tests for true, false, null, boundary data, and invalid expression cases.

If conditions are entered by end users, a dedicated allowlist design is needed: define the supported grammar, readable fields, allowed operators, and size limits. Do not merely check the string with regex and pass it into a full-privilege context.

## 10. Common Errors and Troubleshooting

| Symptom | Common Cause | How to Fix |
|---|---|---|
| Cannot parse expression | Wrong quotes, parentheses, or operators | Shrink the expression and verify syntax piece by piece |
| Property not found | Wrong root object or wrong property name | Check the object passed to `getValue` and accessors |
| NullPointerException when reading a path | An intermediate property is null | Use safe navigation at appropriate spots and define a null policy |
| Variable not found | Missing `setVariable` call or wrong variable name | Match the name after `#` with the context |
| Bean not found | Bean not registered or wrong name | Check the Spring context and bean resolver |
| Cannot convert type | Incompatible result type | Request an explicit result type and check conversion |
| Expression calls unexpected methods | Context granted overly broad permissions | Narrow the context, root object, and resolvers |

When debugging, try step by step: parse the expression standalone, evaluate with small sample data, check the root object, check variables, and only then add beans or functions. This isolates errors without escalating context permissions just to bypass an error.

## 11. Stage-by-Stage Practice Roadmap

| Stage | Content | Completion Exercise |
|---|---|---|
| 1. Syntax | Literals, operators, conditionals, properties, and indexes | Write expressions to compute totals, check status, and provide defaults |
| 2. Context | Root object, `#this`, `#root`, variables, and functions | Evaluate expressions against a simple DTO |
| 3. Collection | Selection, projection, lists, and maps | Filter orders by total and extract a list of codes |
| 4. Spring | `@Value`, bean references, and template expressions | Read configuration and build strings from variables |
| 5. Evaluation permissions | Standard and Simple evaluation contexts | Compare property-reading and method-calling capabilities |
| 6. Safety | Allowlists, untrusted input, errors, and limits | Build a read-only condition evaluator on a DTO |

A good capstone exercise is creating an `OrderView` with only `total`, `customerLevel`, and `active`. Write a Boolean expression determining whether a promotion applies. Evaluate the expression with a read-only `SimpleEvaluationContext`, then write tests for GOLD customers, regular customers, total equal to the threshold, total below the threshold, and null data. Finally, try changing the expression to reference a type or invoke a method and observe the restricted context rejecting ungranted capabilities.

## 12. Checklist Before Bringing SpEL into an Application

- [ ] Is the expression short, clear, and necessary for configuration?
- [ ] Does the expression string come from a trusted source with a change process?
- [ ] Does the root object contain only necessary data?
- [ ] Has the context with minimal permissions been chosen?
- [ ] Can a read-only `SimpleEvaluationContext` be used?
- [ ] Have unnecessary beans, classes, constructors, and methods been avoided?
- [ ] Does the result have an explicit type and null handling?
- [ ] Have boundary data, parse errors, and evaluation errors been tested?
- [ ] Does the expression avoid side effects and expensive operations?
- [ ] Do logs avoid exposing sensitive data?

## 13. Conclusion

Learn SpEL in order from syntax to context, and then to Spring integration and security. Syntax lets you write expressions; the evaluation context determines what an expression can see and execute. In real applications, design quality lies in keeping expressions small, input data explicit, and evaluation permissions at a minimum. When logic becomes long, hard to test, or has side effects, move it to Java to keep behavior understandable and maintainable.