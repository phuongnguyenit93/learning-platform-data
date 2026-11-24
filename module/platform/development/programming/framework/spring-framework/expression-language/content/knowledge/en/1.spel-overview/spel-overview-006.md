# Readability, Testability, and Risks When Expressions Change

## Objectives

In Spring Framework Expression Language (SpEL), expressions are often stored as strings and parsed and evaluated within a context provided by the application. This approach allows configuration or policies to change without rewriting Java control flow, but it also introduces a dependency that is less visible than a regular method call.

After this lesson, you will be able to:

- Write short, readable expressions that clearly convey business conditions.
- Identify the root data, variables, beans, and capabilities that EvaluationContext allows an expression to use.
- Verify expression syntax and behavior with repeatable tests.
- Recognize changes in models, data types, or context that can break expressions.
- Limit risks when expressions are stored in configuration or updated while the application is running.

## 1. Why Does SpEL Readability Matter?

SpEL is an expression language. A string such as **order.total >= 100** can be parsed and then evaluated on an Order object. Java code that calls a method directly normally exposes types and method names through the compiler; a SpEL expression instead references properties and methods by name as strings. Therefore, a change in the model may not be caught by the compiler at build time.

Consider the following expression:

~~~text
order.customer?.active and order.total >= #minimum
~~~

A reader can recognize three components: customer, active status, and order total compared against the threshold. The expression is still short enough to inspect by eye. Conversely, if an expression contains many nested levels of conditions, collection accesses, calls to methods with side effects, and references to many variables, maintainers will struggle to tell which part determines the result.

A good expression should answer three questions:

1. Which object is being evaluated?
2. Which dependent values are passed in from outside?
3. What does the expression's result mean in the business domain?

If you have to read through several Java classes just to answer these questions, consider extracting the logic into a clearly named business method, or splitting the expression into small named parts tested individually.

## 2. Clarifying Data and Evaluation Context

SpEL does not automatically know which object the application wants to evaluate. The application passes a root object and an EvaluationContext to Expression.

- **Root object** is the default object that the expression accesses. With Order as the root, the expression **total** corresponds to reading the total property on Order.
- **EvaluationContext** provides ways to read properties, invoke methods, resolve types, beans, functions, and variables. Actual capabilities depend on the context type and configured resolvers/accessors.
- **Variables** are referenced with the # symbol, for example **#minimum** or **#region**.
- **#root** always points to the root object. **#this** points to the current object in part of an evaluation; this is especially useful in collection selection and projection.
- **Bean references** use the **@beanName** syntax, but only work when the context has a suitable BeanResolver.

For example:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("total >= #minimum");

SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();
context.setVariable("minimum", new BigDecimal("100.00"));

Boolean accepted = expression.getValue(context, order, Boolean.class);
~~~

In this example, the root object is order, while the minimum threshold is a variable passed via the context. Putting the threshold in a variable keeps the expression from hard-coding a fixed number and lets tests vary input data clearly.

You should document each expression's contract where it is managed: the root object type, variable names and types, expected result type, and permitted context capabilities. This contract helps anyone modifying the expression know which parts of the application they must remain compatible with.

## 3. Rules to Keep Expressions Readable

### Keep One Main Business Idea per Expression

Prefer conditions that can be stated in a single sentence. Use parentheses to show logical grouping when there are multiple operators:

~~~text
(order.status == 'PAID' or order.status == 'SHIPPED')
and order.total >= #minimum
~~~

Do not rely solely on memory of operator precedence when an expression has multiple AND/OR operators. Parentheses clarify intent and make editing conditions safer.

### Name Variables After Business Concepts

Names such as **#minimumEligibleTotal**, **#allowedRegion**, or **#reviewRequired** are easier to understand than generic names such as **#x**, **#v1**. Variables should represent input data or an established concept in the application.

### Handle Null Intentionally

The safe navigation operator **?.** allows accessing a property or calling a method without throwing an error solely because the object on the left is null:

~~~text
order.customer?.name
~~~

The Elvis operator **?:** can provide a default value when the expression on the left lacks a suitable value:

~~~text
order.customer?.name ?: 'Guest'
~~~

Choose defaults based on business requirements. A default value may allow the expression to continue running while hiding missing data. If a customer is required to exist, checking for null and reporting a clear error may be more accurate than substituting a default name.

Safe navigation also does not replace defining a data contract. If an expression accesses several chained properties, inspect each point that can be null and test that case.

### Use Collection Operations Moderately

SpEL supports common operations on collections:

- Selection **.?[condition]** filters elements matching the condition.
- Projection **.![expression]** creates a new collection from the result of the expression on each element.
- Index access such as **[0]** retrieves an element by position.

For example:

~~~text
#root.items.?[active].![code]
~~~

The expression above filters items that are active and then retrieves the code of each item. It is concise, yet readers still need to know whether items can be null or empty, whether active is a Boolean property, and whether code can be null.

Be especially careful with index access. The expression **items[0]** may work on a non-empty collection but fail when the collection is empty. If the result depends on the first element, define clear behavior for empty collections and write a corresponding test.

### Avoid Calling Methods with Side Effects

Expressions used for making decisions or reading data should be observable and repeatable. Avoid calling methods that write to a database, send notifications, mutate state, or modify collections during evaluation. An expression may be evaluated multiple times, in multiple places, or during verification; side effects make outcomes hard to predict.

If the business operation needs to modify data, perform that action in a clearly named Java service. Use SpEL to select or evaluate conditions, not as a place to execute workflows.

## 4. Choosing EvaluationContext Based on Required Permissions

The context type directly affects what an expression can do.

**StandardEvaluationContext** offers powerful extensibility: property accessors, method resolvers, constructor resolvers, type locators, bean resolvers, and variables. It fits when the application explicitly needs those capabilities and controls the expression source.

**SimpleEvaluationContext** is designed for data binding scenarios with a narrower scope of capabilities. You can build a read-only context:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

If calling instance methods is genuinely needed, the application can configure that capability using the corresponding builder. Enable only what the expression needs and state it explicitly in the expression's contract.

Do not evaluate strings supplied arbitrarily by users or external sources using a full-privilege StandardEvaluationContext. An untrusted expression could attempt to access methods, types, or beans the application never intended to allow. When user-configurable expressions are required, restrict syntax and context, control access permissions, limit length/complexity, and test rejected cases.

Choosing the context is also part of compatibility. An expression might run in StandardEvaluationContext yet fail when switched to SimpleEvaluationContext because a method resolver, bean resolver, or another capability is no longer enabled. Treat a context change as a contract change, not merely an internal configuration tweak.

## 5. Testing Expressions Systematically

A SpEL test should verify both syntax and evaluation results. Do not just check that the parser does not throw an exception: a syntactically valid expression can still return wrong results when data changes.

### Testing Syntax

Parse expressions in tests or when loading configuration to detect syntax errors early:

~~~java
ExpressionParser parser = new SpelExpressionParser();

assertDoesNotThrow(() ->
    parser.parseExpression("total >= #minimum")
);
~~~

If expressions live in configuration or a policy store, you can validate all expressions at load time so errors are caught before handling real requests. Report the expression name/ID and configuration location so operators can find the exact source.

### Testing Results with Realistic Root Objects and Contexts

~~~java
@Test
void acceptsOrderAtMinimumThreshold() {
    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression("total >= #minimum");

    SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();
    context.setVariable("minimum", new BigDecimal("100.00"));

    Order order = new Order(new BigDecimal("100.00"));

    Boolean result = expression.getValue(context, order, Boolean.class);

    assertEquals(Boolean.TRUE, result);
}
~~~

The test uses the same context type, root object, and result type used by the real application. If production adds variables, custom accessors, or bean resolvers, put the corresponding configuration in a shared factory so tests and the application do not accidentally evaluate in two different environments.

### Creating a Set of Edge Cases

For an expression checking an order condition, consider at a minimum:

| Case | What to Verify |
|---|---|
| Value equal to threshold | Is the >= boundary as intended |
| Value below threshold | Does the expression return false as expected |
| Null root object | Does the application reject or handle per contract |
| Null intermediate property | Are safe navigation/defaults as intended |
| Empty collection | Do selection, projection, or index access have defined behavior |
| Unsupplied variable | Is the error caught and reported with enough context |
| Changed data type | Are conversions or comparisons still valid |
| Out-of-range value | Are results and errors handled clearly |

Not every expression needs all of the cases above. Choose cases based on the root object, variables, operations, and data structures the expression actually uses.

### Checking Result Types

If an expression is expected to return Boolean, request the Boolean type when calling **getValue**:

~~~java
Boolean decision = expression.getValue(context, rootObject, Boolean.class);
~~~

This helps catch expressions returning an incompatible type at the evaluation point. Do not convert every result into a string and interpret it with other logic; the result type should be specified directly in the contract.

### Testing Evaluation Errors

Separate parsing errors from evaluation errors. ParseException usually indicates an invalid expression string. EvaluationException usually relates to a missing property, an uninvokable method, an unresolved variable or bean, null data, or failed type conversion.

In logs, prefer recording the expression ID, version, timestamp, error type, and request correlation ID. Avoid logging all sensitive data from the root object or variables solely for diagnostics.

## 6. Risks When Expressions Change

An expression is a runtime contract between the SpEL string, the Java model, and EvaluationContext. A change in any component can affect the result.

### Renaming or Restructuring Properties

If **customer.active** changes to **customer.enabled**, the Java compiler will not necessarily detect the old SpEL string. The expression might only fail when a specific business flow executes. When refactoring models, also search expressions stored in annotations, XML, configuration, databases, or policy management systems.

### Changing Data Types or Semantics

A property may still exist yet change from Integer to String, from a numeric amount to a currency type, or from Boolean to a multi-value status. The expression may still parse, yet the comparison, conversion, or business meaning has changed. Check types and semantics, not only property names.

### Changing Nullability and Cardinality

A property that previously always had a value may become nullable. A collection that previously always had elements may become empty. Chained property access or **[0]** may start failing. Conversely, adding a default value may mask data errors and cause business decisions to change silently.

### Changing EvaluationContext

Disabling a method resolver, changing a property accessor, removing a BeanResolver, or switching from StandardEvaluationContext to SimpleEvaluationContext can prevent existing expressions from running. Conversely, enabling extra capabilities can expand expression privileges beyond expectations.

### Changing Order or Combination of Conditions

Changing **and** to **or**, removing parentheses, or altering thresholds can significantly change the set of accepted objects. Boundary cases and condition combinations should be tested as part of review.

### Changing Invoked Methods

A method may change its name, parameters, return type, or side effects. Because method names in SpEL are strings, ordinary refactoring may not find all reference sites. Avoid having expressions depend on many internal methods or methods with complex logic.

### Changing Expression Sources

If expressions are stored outside source code and can be edited while the application is running, two instances may evaluate two different versions during rollout. Define distribution, caching, effective timing, rollback, and version identification. A new expression should be parsed and validated before becoming the active version.

## 7. Safe Process for Changing Expressions

When modifying an expression currently in use:

1. **Identify the source and owner.** Locate where the string is stored, the expression ID, loading site, caching site, and callers.
2. **Document the current contract.** Record root type, variables, permitted beans/functions, context, result type, and business meaning.
3. **Create representative input examples.** Include normal, boundary, null, empty collection, and invalid data cases if relevant.
4. **Edit the expression and test independently.** Parse the new expression and evaluate it on the same context and dataset.
5. **Compare old and new results.** For policies deciding permissions, pricing, limits, or statuses, review cases where results change and confirm they are intentional.
6. **Deploy with rollback capability.** If expressions are updated outside the application, store the previous version, new version ID, and restoration procedure. Do not replace the active version before the new version is validated.
7. **Monitor errors after deployment.** Track parse/evaluation errors by expression ID and version, unusual result rates, and affected business flows.

For expressions fixed in source code, focus on regression testing alongside model changes. For expressions editable at runtime, add pre-activation validation, version management, and a rollback mechanism.

## 8. Managing Expressions in the Application

A few organizational rules help reduce maintenance cost:

- Place expressions in a location with a stable name or ID instead of repeating strings across multiple classes.
- Store a brief description of purpose, root type, variables, and result type alongside the expression.
- Use a shared factory or configuration to construct identical EvaluationContexts between production and tests.
- Parse once when loading or updating an expression and reuse the Expression object when appropriate; avoid re-parsing the same string for every record unnecessarily.
- If enabling the SpEL compiler to optimize performance, measure first and test with the actual set of expressions/models. Do not treat compiler mode as a fix for an overly complex expression.
- Do not let end users enter an arbitrary SpEL string into search fields or regular forms. If the product needs a policy editor, provide a restricted capability set and dedicated validation.
- When diagnostics are needed, log the expression ID and version rather than relying on logging the entire input payload.

## 9. Review Checklist

Before accepting a SpEL-related change, verify:

- [ ] The expression can be read and explained in one short sentence.
- [ ] The root object, variables, and result type are clearly defined.
- [ ] EvaluationContext enables only the required capabilities.
- [ ] Nullable points, empty collections, and index accesses have been considered.
- [ ] The expression is parsed in tests or during configuration loading.
- [ ] Results are tested with normal, boundary, and relevant invalid data.
- [ ] Property and method name/type changes have been cross-checked against expression strings.
- [ ] If the expression is updated at runtime, the new version has validation and a rollback path.
- [ ] Logs and error messages are sufficient to identify the failing expression without exposing sensitive data.

## Conclusion

SpEL is maintainable when expressions are short, have clear data contracts, are evaluated in an appropriately scoped EvaluationContext, and have tests describing their behavior. Because expressions are strings checked at runtime, any change to the model, data types, context, or configuration source must be treated as a contract change. Focusing on readability, boundary testing, and version management will keep expressions accurately reflecting business logic as the application evolves.
