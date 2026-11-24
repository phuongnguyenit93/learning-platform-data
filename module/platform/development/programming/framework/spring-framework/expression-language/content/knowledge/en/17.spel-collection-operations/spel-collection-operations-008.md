# Avoiding overly long and hard-to-test collection expressions in SpEL

## 1. Why keep collection expressions short?

Spring Expression Language (SpEL) supports many collection operations such as index access, selection, and projection. These operations help filter elements, retrieve a matching element, or transform a collection directly inside an expression.

Short, readable example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("items.?[active]");

List<?> activeItems = expression.getValue(order, List.class);
~~~

When adding multiple nested conditions, multi-level property accesses, null-safe operators, computations, and conditional branches, an expression can become very long:

~~~text
orders.?[customer != null and customer.active and items != null and items.?[product != null and product.enabled and quantity > 0].size() > 0].![customer.address?.city]
~~~

Long expressions are often hard to read, hard to pinpoint where an error occurred, hard to test condition by condition, and hard to change when the data model changes. A practical rule is to keep SpEL for short operations with a clear purpose; move multi-step workflows to Java or split them into small named expressions.

## 2. Recognizing signs that an expression has become too complex

A collection expression usually needs to be split when it shows one or more of the following signs:

- Selection contains many conditions combined with and and or, especially with multiple levels of parentheses.
- Selection nested inside selection or projection nested across many levels.
- One expression filters, transforms, sums, and applies business rules all at once.
- The same long property path is repeated multiple times.
- There are many potentially null points and the expression must handle multiple null-safe branches.
- A reader has to trace multiple #this variables across collection levels to understand what object the current element is.
- The expression can only be tested by building a large object graph.
- A small change in the domain model forces edits to many expression strings.

Character length is not the only criterion. A short expression with hard-to-follow semantics still needs simplification. Conversely, a short, clear property path can stay as is.

## 3. Naming business intent in Java

SpEL only sees the syntax and data provided. When a rule has a business name, put that name into a Java method so readers understand the purpose without decoding the entire expression.

For example, instead of leaving a long string to decide whether an order is eligible for processing:

~~~text
orders.?[status == 'PAID' and customer != null and customer.active and total >= 100]
~~~

You can create a Java method:

~~~java
public boolean isEligibleForProcessing(Order order) {
    return order.getStatus() == OrderStatus.PAID
            && order.getCustomer() != null
            && order.getCustomer().isActive()
            && order.getTotal().compareTo(new BigDecimal("100")) >= 0;
}
~~~

If the application needs to filter a collection, you can use Java Stream with a clearly named method:

~~~java
List<Order> eligibleOrders = orders.stream()
        .filter(this::isEligibleForProcessing)
        .toList();
~~~

The name isEligibleForProcessing directly describes the rule. The method can be unit-tested independently, have breakpoints set on it, and be reused across multiple processing flows. SpEL remains useful for configuration conditions or short expressions, while business rules with many parts should have a clear place in Java.

## 4. Splitting a workflow into named steps

When processing needs to remain in SpEL, divide the workflow into small expressions. Each expression should do one thing and have a name describing its result.

For example, needing to get the totals of paid orders:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression paidOrdersExpression =
        parser.parseExpression("orders.?[status == 'PAID']");

Expression paidTotalsExpression =
        parser.parseExpression("#paidOrders.![total]");

StandardEvaluationContext context =
        new StandardEvaluationContext(orderBook);

List<?> paidOrders =
        paidOrdersExpression.getValue(context, List.class);

context.setVariable("paidOrders", paidOrders);

List<?> totals =
        paidTotalsExpression.getValue(context, List.class);
~~~

This flow has two clear steps:

1. paidOrdersExpression selects the paid orders.
2. paidTotalsExpression extracts the total property from each selected order.

The variable name paidOrders describes the intermediate data. If inspection is needed, you can check the result after the selection step before running the projection. This split also helps identify which expression causes an error when data is not as expected.

There is no need to split a very simple expression into multiple steps. Split when naming intermediate steps clarifies intent or testing.

## 5. Understanding #this properly in selection and projection

In collection operations, #this represents the current element being processed. When collection operations are nested, #this changes according to the current level. This is a common source of confusion.

Simple selection example:

~~~java
Expression expression =
        parser.parseExpression("items.?[#this.active]");
~~~

Inside the predicate, #this is an item. You can omit #this when accessing a property of the current element directly:

~~~java
Expression expression =
        parser.parseExpression("items.?[active]");
~~~

With projection:

~~~java
Expression expression =
        parser.parseExpression("items.![name]");
~~~

Each time projection runs, name is read on the current element.

When nesting collection operations, clearly identify which object each level is processing. If you have to write multiple nested #this expressions to reach outer elements, move the logic into a Java method or extract intermediate collections into named variables.

## 6. Avoiding too many levels of nested selection and projection

An expression like the following carries too many responsibilities at once:

~~~text
departments.?[employees != null and employees.?[active and salary > 5000].size() > 2].![employees.?[active].![name]]
~~~

It filters departments by qualifying employee count, filters employees, and extracts employee names. Readers must understand the department structure, employee structure, and the meaning of each #this at every level.

It can be split in Java:

~~~java
List<Department> departmentsWithActiveStaff = departments.stream()
        .filter(department -> department.getEmployees().stream()
                .filter(Employee::isActive)
                .filter(employee -> employee.getSalary() > 5000)
                .count() > 2)
        .toList();

List<List<String>> activeEmployeeNames = departmentsWithActiveStaff.stream()
        .map(department -> department.getEmployees().stream()
                .filter(Employee::isActive)
                .map(Employee::getName)
                .toList())
        .toList();
~~~

If the application still needs expressions for small individual steps, prepare intermediate data in Java and then evaluate expressions on named collections. Data structures and variable names clarify context far better than a deeply nested expression.

## 7. Extracting conditions into named methods or properties

A long predicate is often a sign that it expresses a named concept. You can add a method to the domain object or a service:

~~~java
public boolean isReadyForDispatch() {
    return paid && stockReserved && !cancelled;
}
~~~

Then selection becomes short:

~~~java
Expression expression =
        parser.parseExpression("orders.?[readyForDispatch]");
~~~

If the rule needs to call a service or depends on multiple data sources, process it in a Java service before passing the result into an expression. This avoids turning SpEL into a business orchestration layer and keeps dependency management clear.

Do not add a getter solely to hide a long expression if that getter performs queries, side effects, or heavy work. Properties accessed via SpEL can invoke getters; therefore getters should have stable and predictable data-reading behavior.

## 8. Handling null at data boundaries

Null-safe operators help an expression handle null targets, but do not make the entire expression automatically safe. Every step that can return null needs to be handled explicitly.

Example:

~~~text
orders?.?[customer?.active == true]
~~~

Here ?.? guards the orders collection; customer?.active guards the customer property of the current element. If the expression accesses other properties that may be null, handle those segments separately.

When null logic begins having many branches, normalizing data before evaluating the expression is usually clearer:

~~~java
List<Order> safeOrders =
        orders == null ? Collections.emptyList() : orders;

context.setVariable("orders", safeOrders);
~~~

Only normalize null to an empty collection when the two states have the same business meaning. If null means "data not loaded yet" while an empty collection means "loaded with no results", preserve the distinction and handle it in Java.

## 9. Passing dynamic data into EvaluationContext

Do not build expression source by concatenating runtime values directly into the string. Data can contain quotes, special characters, or content that alters syntax.

For example, use a variable:

~~~java
Expression expression =
        parser.parseExpression("items.?[category == #requiredCategory]");

StandardEvaluationContext context =
        new StandardEvaluationContext(catalog);

context.setVariable("requiredCategory", requestedCategory);

List<?> matches = expression.getValue(context, List.class);
~~~

requiredCategory is passed separately in the evaluation context. The same expression can be reused with different values. This approach also makes it easier to test input cases without rebuilding the expression string.

If an expression needs a well-defined set of inputs, create a dedicated root object or use variables with purpose-describing names instead of placing many unrelated values into one context.

## 10. Parse once, evaluate many times

When the same expression is used repeatedly, parse it once and retain the Expression object to evaluate against different contexts or data:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("items.?[active]");

List<?> firstResult = expression.getValue(firstCatalog, List.class);
List<?> secondResult = expression.getValue(secondCatalog, List.class);
~~~

Separating parsing from evaluation distinguishes syntax errors from runtime data errors. If the expression source comes from configuration, you can parse and validate syntax during startup to detect misconfigurations early.

There is no need to re-parse the same string in every loop iteration. If you need to filter elements individually with a simple rule, consider Java Stream or a predicate method instead of creating and parsing a new expression for each element.

## 11. Testing expressions by individual behavior

A collection expression should have tests for both normal data and edge cases. Create small, readable fixtures with just enough data to demonstrate the rule.

Example selection test:

~~~java
@Test
void selectsOnlyActiveItems() {
    List<Item> items = List.of(
            new Item("A", true),
            new Item("B", false),
            new Item("C", true));

    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression("items.?[active]");

    Catalog catalog = new Catalog(items);

    List<?> result = expression.getValue(catalog, List.class);

    assertEquals(2, result.size());
}
~~~

Include the following cases depending on expression behavior:

- A collection with multiple elements, some matching and some not matching.
- An empty collection.
- A null collection if the expression is designed to support null.
- Elements with null properties.
- No elements matching the selection.
- Valid indices and out-of-bounds indices if index access is used.
- Result type matching what the application expects.

Tests should verify results and meaningful error cases. You do not need large fixtures if a small collection already demonstrates the behavior.

## 12. Testing parsing and evaluation separately

Parse errors and evaluation errors are two different kinds of errors:

- Parse errors occur when the string does not follow valid SpEL syntax.
- Evaluation errors occur when the expression is valid, but data or context does not permit performing the operation.

You can test syntax separately:

~~~java
Expression expression = parser.parseExpression("items.?[active]");
~~~

Then evaluate with data:

~~~java
List<?> result = expression.getValue(catalog, List.class);
~~~

When a test fails, separating the two steps helps pinpoint whether the fault lies in the expression source or in runtime data. If expressions are read from configuration, have tests or startup checks to catch parse errors before business flows run.

## 13. Limiting EvaluationContext permissions

Collection expressions can access properties and invoke methods depending on the configured evaluation context. StandardEvaluationContext supports broad capabilities such as reflection, method resolution, type access, and bean resolution when enabled.

Do not evaluate SpEL strings submitted by untrusted users using a context with broad permissions. If only data binding or restricted property reading is needed, consider SimpleEvaluationContext and enable only the capabilities truly required.

A short expression can still perform inappropriate operations if the context grants overly broad permissions. Therefore, expression length and complexity are maintainability issues; context access permissions are a separate security concern that must be designed.

## 14. When to use SpEL, when to use Java?

| Situation | Appropriate choice |
|---|---|
| Filtering a collection with a short predicate at a configuration point | SpEL selection |
| Selecting the first or last element by a simple condition | SpEL first/last selection |
| Extracting a property from each element | SpEL projection |
| Multiple levels of nested selection/projection | Split into Java or intermediate steps |
| Business rules with many conditions and many states | Java method/service |
| Needing to call repositories, APIs, or coordinate multiple services | Java service |
| Needing logging, exception handling, and explicit side effects | Java |
| Needing a short expression driven by configuration | SpEL, with an appropriately restricted context |

SpEL is beneficial when expressions are short, input data is clear, and the integration point genuinely needs an expression. Java is better suited when logic has many steps or needs named behavior, independent testing, and dependency management.

## 15. Process for simplifying a long expression

When encountering a hard-to-read collection expression, process it in this sequence:

1. Identify what the final result must be: a collection, a single element, a value, or a Boolean.
2. Document selection conditions as sentences with business names.
3. Identify property paths that can be null and boundaries needing null-safe access.
4. Extract meaningful intermediate steps into variables or Java methods.
5. Keep SpEL for individual short operations if it still keeps configuration easy to understand.
6. Parse the expression once and write tests for normal results and edge cases.
7. If you still have to read it multiple times to understand it, move the main rule into a Java method/service.

The goal is for each expression to represent one clear operation. Method names and intermediate variables should explain intent instead of forcing readers to decode a long string themselves.

## 16. Comprehensive example: from nested expression to testable steps

Suppose you need to retrieve the names of active employees belonging to departments that have at least two active employees. It could be written as a multi-level nested expression, but understanding and testing it is difficult:

~~~text
departments.?[employees != null and employees.?[active].size() >= 2].![employees.?[active].![name]]
~~~

You can move the rule to Java:

~~~java
public boolean hasEnoughActiveEmployees(Department department) {
    return department.getEmployees() != null
            && department.getEmployees().stream()
                    .filter(Employee::isActive)
                    .count() >= 2;
}

List<Department> eligibleDepartments = departments.stream()
        .filter(this::hasEnoughActiveEmployees)
        .toList();

List<List<String>> activeNames = eligibleDepartments.stream()
        .map(department -> department.getEmployees().stream()
                .filter(Employee::isActive)
                .map(Employee::getName)
                .toList())
        .toList();
~~~

The hasEnoughActiveEmployees method expresses the selection condition. The employee name projection is a separate step. You can write unit tests for the predicate method, tests for the name projection, and tests for the combined flow. If a simple predicate still needs to be exposed or configured, SpEL can still be used at the appropriate boundary.

## 17. Key takeaways

- Keep selection and projection short, focused on a single operation.
- Put multi-condition business rules into clearly named Java methods.
- Split nested collection operations into named intermediate steps.
- Understand clearly that #this changes with the current collection operation.
- Handle null at every boundary; null and an empty collection can carry different meanings.
- Pass dynamic data via variables in EvaluationContext; avoid concatenating data into expression source.
- Parse once when reusing the same expression; evaluate with the corresponding context/data.
- Test parsing and evaluation separately, including empty collections, null, no matching elements, and out-of-bounds indices.
- Restrict evaluation context permissions when expressions are not completely controlled by the application.
- Choose Java when multiple steps, side effects, dependencies, logging, or explicit error handling are needed.
