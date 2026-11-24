# Variables Passed from the Application Context

## Objectives

In Spring Expression Language (SpEL), variables allow an application to pass data into an expression at evaluation time. Instead of concatenating values directly into the expression string, the application registers a value in **EvaluationContext** and references it using the **#variableName** syntax.

This approach enables reusing the same expression with multiple datasets, keeps input data separate from SpEL syntax, and supports parameterized conditions such as price thresholds, allowed statuses, the current user, or business policies.

After this lesson, you can:

- Register variables using the **setVariable()** method in EvaluationContext.
- Reference variables using the **#name** syntax.
- Distinguish context variables from root object properties and the current element.
- Pass numbers, strings, enums, collections, and objects into expressions.
- Use variables in selection, projection, and nested conditions.
- Reuse an Expression with different variable values.
- Handle missing, null, and mistyped variables, and control what data is put into the context.

## 1. What Is a Variable in SpEL?

A variable is a value placed into EvaluationContext by the application so the expression can read it at runtime. In SpEL, a variable name is written with a leading # symbol:

~~~text
#minimumPrice
#currentUser
#allowedStatuses
~~~

The # symbol is part of the reference syntax inside the expression. When registering a variable in Java, pass the variable name without the # symbol:

~~~java
context.setVariable("minimumPrice", new BigDecimal("100.00"));
~~~

Then, the expression can use:

~~~text
#minimumPrice
~~~

Keep the convention consistent: the name passed to setVariable() has no hash symbol; the name in SpEL has a hash symbol.

Variables can hold many data types: String, numbers, Boolean, enums, collections, Maps, or a business object. SpEL evaluates the variable based on the value and object type passed in by the application.

## 2. Registering Variables in EvaluationContext

Basic example using StandardEvaluationContext:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("minimumPrice", new BigDecimal("100.00"));
context.setVariable("requiredStatus", "APPROVED");

Expression expression = parser.parseExpression(
    "#minimumPrice <= 150 and #requiredStatus == 'APPROVED'");

Boolean accepted = expression.getValue(context, Boolean.class);
~~~

The application registers two variables and then evaluates the expression. The result is Boolean true because both conditions hold.

You can pass a root object at the same time as variables:

~~~java
Order order = loadOrder();

StandardEvaluationContext context = new StandardEvaluationContext(order);
context.setVariable("minimumTotal", new BigDecimal("100.00"));

Expression expression = parser.parseExpression(
    "#root.total >= #minimumTotal");

Boolean eligible = expression.getValue(context, Boolean.class);
~~~

In this example:

- order is the root object of the context.
- #root.total reads the total property from the root object.
- #minimumTotal reads the variable registered by the application.
- The result is requested as a Boolean.

Variables registered on a context are used when evaluating expressions with that context. If an expression is evaluated with another context, that context must be supplied with the variables required by the expression.

## 3. Distinguishing Variables, Root Object, and Current Object

The following three references have different meanings:

| Syntax | Meaning |
|---|---|
| **#minimumTotal** | Variable passed into EvaluationContext by the application |
| **#root.total** | The total property of the root object |
| **#this.total** | The total property of the current object in the evaluation context |
| **total** | The total property on the current object, if that property is accessible |

Suppose the root object is Order and the expression is evaluated directly on Order:

~~~text
#root.total >= #minimumTotal
~~~

When inside collection selection, #this typically represents the current element:

~~~text
#root.orders.?[#this.total >= #minimumTotal]
~~~

Here, #root remains the object containing the orders list; #this changes for each Order under consideration; #minimumTotal remains the context variable with the same value throughout the entire evaluation.

Do not confuse a property with a variable just because they share the same name. For example:

- minimumTotal reads the minimumTotal property of the current object.
- #minimumTotal reads the minimumTotal variable in EvaluationContext.

When an expression spans multiple object layers, using #root, #this, and #variableName explicitly helps avoid reading the wrong data.

## 4. Passing Different Data Types

### Strings and Statuses

~~~java
context.setVariable("requiredStatus", "PAID");
context.setVariable("regionCode", "HCM");
~~~

Expression:

~~~text
#order.status == #requiredStatus and #order.region == #regionCode
~~~

If the root object is order and the corresponding properties exist, the expression compares the status and region against the data supplied by the application.

### Numbers and Business Thresholds

~~~java
context.setVariable("minimumScore", 80);
context.setVariable("maximumDiscount", new BigDecimal("0.15"));
~~~

Expression:

~~~text
#student.score >= #minimumScore
~~~

Or:

~~~text
#discount <= #maximumDiscount
~~~

Use numeric types suited to the business domain. For monetary amounts and rates requiring decimal precision, BigDecimal is usually more suitable than floating-point calculations.

### Enums

~~~java
context.setVariable("requiredStatus", OrderStatus.APPROVED);
~~~

Expression:

~~~text
#order.status == #requiredStatus
~~~

Using enums helps avoid typos and restricts values to the set of states defined in Java.

### Collections and Maps

~~~java
context.setVariable(
    "allowedStatuses",
    Set.of(OrderStatus.PAID, OrderStatus.SHIPPED));

context.setVariable(
    "priceLimits",
    Map.of("STANDARD", new BigDecimal("100"),
           "PREMIUM", new BigDecimal("500")));
~~~

The expression can call an appropriate method on the collection value or access the Map by index:

~~~text
#allowedStatuses.contains(#order.status)
~~~

~~~text
#priceLimits['PREMIUM']
~~~

Method invocation capability depends on the MethodResolver and EvaluationContext configuration. Test the expression in the exact context that the application uses.

### Business Objects

The application can also pass an object as a variable:

~~~java
context.setVariable("policy", policy);
~~~

Expression:

~~~text
#policy.minimumTotal
#policy.allowedStatuses
~~~

SpEL reads properties of the object assigned to the variable according to the context's PropertyAccessor. Therefore, the passed object needs to expose the properties used by the expression.

## 5. Using Variables in Selection and Projection

Variables are particularly helpful when collection conditions change with application data.

Suppose the root object has a list of orders:

~~~text
#root.orders.?[#this.total >= #minimumTotal]
~~~

The application can change minimumTotal without creating a new expression string.

Example evaluating with two thresholds:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(
    "#root.orders.?[#this.total >= #minimumTotal]");

StandardEvaluationContext context = new StandardEvaluationContext(customer);
context.setVariable("minimumTotal", new BigDecimal("100"));

List<?> regularOrders =
    expression.getValue(context, List.class);

context.setVariable("minimumTotal", new BigDecimal("500"));

List<?> highValueOrders =
    expression.getValue(context, List.class);
~~~

The same Expression is evaluated with two different threshold values. In a real application, if a context is used concurrently across multiple threads, do not mutate variables on the same context while evaluations are running. Create a separate context per evaluation or manage the context lifecycle in a way free from concurrent updates.

Variables can also be used in projection:

~~~text
#root.orders.?[#this.total >= #minimumTotal].![#this.id]
~~~

The expression filters orders meeting the threshold and then returns a list of their IDs.

### Using Variables Across Multiple Levels

~~~text
#root.departments.![employees.?[#this.salary >= #minimumSalary].![name]]
~~~

In the expression above, #minimumSalary can be used in every selection inside the projection. #this is Department in the outer operation, then Employee in the inner selection. The variable remains the value supplied by the context.

If a condition involves multiple variables, pick clear names:

~~~text
#root.orders.?[
    #this.total >= #minimumTotal and
    #this.status == #requiredStatus
]
~~~

Variable names should reflect units and purpose. For example, #minimumTotal is clearer than #limit, especially when an expression has several different thresholds.

## 6. Variables and Reusing Expression

A key benefit of variables is that an expression can be parsed once and evaluated many times with different data.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "#quantity * #unitPrice");

StandardEvaluationContext context = new StandardEvaluationContext();

context.setVariable("quantity", 3);
context.setVariable("unitPrice", new BigDecimal("12.50"));

BigDecimal firstResult =
    expression.getValue(context, BigDecimal.class);

context.setVariable("quantity", 5);

BigDecimal secondResult =
    expression.getValue(context, BigDecimal.class);
~~~

The expression does not need to change when quantity changes. The application simply updates the variable value before the next evaluation.

Parsing once and reusing the Expression can reduce repeated parsing overhead. However, distinguish the lifecycle of Expression from the lifecycle of EvaluationContext. An Expression can be stored for reuse; the context holding the root object and variables of an evaluation should be managed appropriately for the application's data and concurrency.

Do not share a context with mutable variables across multiple requests and overwrite variables per request. Doing so can cause one evaluation to read values set by another request. Creating a new context or a per-request context keeps input data cleaner.

## 7. Null Variables, Missing Variables, and Type Mismatches

An expression only works properly if the variables it needs have been supplied with compatible data types.

Distinguish between:

- **Variable with a value:** the expression can use that value.
- **Variable set to null:** the expression receives null; subsequent operations must handle null appropriately.
- **Unregistered variable:** the lookup does not supply the value the application expects; depending on the expression, the result may be null or raise an error in a subsequent operation.
- **Mistyped variable:** comparisons, property access, or method calls may fail during evaluation.

For example, if #minimumTotal needs to be a BigDecimal, avoid passing a String sometimes and an Integer other times without clear conversion rules.

Before evaluation, the application should validate required inputs:

~~~java
if (minimumTotal == null) {
    throw new IllegalArgumentException("minimumTotal is required");
}

context.setVariable("minimumTotal", minimumTotal);
~~~

If a variable is optional, define clearly what null means. You can use a condition:

~~~text
#optionalLimit == null or #order.total <= #optionalLimit
~~~

This expression expresses that when there is no limit, the condition is accepted; if there is a limit, total must be within the limit. Choose the policy according to business logic rather than letting null accidentally decide the outcome.

Variable names should be managed centrally or defined as constants in Java to prevent typos between registration and reference sites.

## 8. StandardEvaluationContext and SimpleEvaluationContext

Both context types serve SpEL evaluation, but their purpose and capability scope differ.

**StandardEvaluationContext** can be configured with a root object, variables, property accessors, method resolvers, type locator, bean resolver, and other extension components. This is the flexible choice when expressions need many SpEL capabilities.

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(rootObject);

context.setVariable("minimumTotal", new BigDecimal("100"));
~~~

**SimpleEvaluationContext** is designed for data binding cases with a more restricted scope. It lets the application configure the needed capabilities without exposing the full feature set like StandardEvaluationContext.

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

context.setVariable("minimumTotal", new BigDecimal("100"));
~~~

Choose the context according to the operations the expression needs to perform. Passing variables does not imply every property, method, type reference, constructor, or bean reference is allowed. Those capabilities still depend on the context and configured accessors/resolvers.

Use the same context creation approach in tests and production to avoid an expression working in one environment while failing in another.

## 9. Passing Variables Instead of Concatenating Expression Strings

Do not concatenate input data directly into a SpEL string:

~~~java
String expressionText =
    "total >= " + request.getMinimumTotal();
Expression expression = parser.parseExpression(expressionText);
~~~

This mixes data with syntax. If the data contains quotes or special characters, the expression can be malformed. If the data comes from an untrusted source, string concatenation can also allow input to alter the expression structure.

Keep the expression fixed and pass data through variables:

~~~java
Expression expression =
    parser.parseExpression("total >= #minimumTotal");

StandardEvaluationContext context =
    new StandardEvaluationContext(order);

context.setVariable("minimumTotal", request.getMinimumTotal());

Boolean accepted = expression.getValue(context, Boolean.class);
~~~

This approach offers several benefits:

- Expression syntax does not depend on input content.
- Values are passed with Java types rather than turned into text fragments.
- The same Expression can be used across multiple requests.
- Input validation is performed in Java before evaluation.
- It is easy to test the expression and data separately.

However, passing variables does not automatically make an untrusted expression safe. If users are allowed to submit entire SpEL strings, they can still write expressions using whatever capabilities EvaluationContext permits. Control both the expression source and the context scope.

## 10. Restricting Access and Data in the Context

EvaluationContext is an important boundary between expressions and application objects. Only put into the context the variables and objects that the expression truly needs.

Several principles:

- Avoid passing the entire application context, service registry, or overly privileged objects when the expression only needs a few values.
- Prefer DTOs or read-only objects with only the required properties.
- Validate variable types and value ranges before registering.
- Do not put secrets, credentials, or sensitive data into the context if the expression does not need them.
- Use SimpleEvaluationContext when a restricted data binding scope meets the requirement.
- Configure property accessors and method resolvers intentionally.
- Do not evaluate arbitrary user-supplied expressions with a full-featured StandardEvaluationContext.
- Log the expression ID and evaluation errors without logging sensitive data.

Variables are data provided to an expression; they are not an authorization mechanism. Registering a variable does not mean the end user is permitted to view or modify the object the variable points to.

## 11. Common Errors and Diagnostics

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Variable returns null | Not registered, wrong name, or value set to null | Cross-check names in setVariable and #name; validate required variables |
| Cannot resolve variable | Syntax error in reference or context lacks corresponding value | Check the # symbol and variable name |
| Error during comparison | Two values have incompatible types | Normalize types before setVariable |
| Error accessing property of variable | Variable object lacks the property or accessor does not support it | Check object type and PropertyAccessor |
| Error calling method on variable | Method does not exist or context disallows that resolver | Check method signature and MethodResolver |
| Results vary across requests | Mutable context shared and variables overwritten | Create a separate context or manage concurrency properly |
| Expression contains syntactically invalid input values | Data concatenated directly into expression string | Keep expression fixed and pass data via variables |
| Collection variable fails in selection | Wrong collection type or predicate | Check element type and condition |
| Variable missing in production | Context factory does not register the same variables as tests | Share context creation logic with tests |

When diagnosing, check in order: the expression being parsed, the referenced variable name, whether the variable was registered on the right context, the type and value of the variable, and only then the operation or property applied to the variable.

## 12. Testing Context Variables

Tests should verify that the expression receives the right values from the context and can be reused with different values.

Example:

~~~java
@Test
void evaluatesExpressionWithContextVariable() {
    ExpressionParser parser = new SpelExpressionParser();
    Expression expression =
        parser.parseExpression("#amount >= #minimumAmount");

    StandardEvaluationContext context = new StandardEvaluationContext();
    context.setVariable("amount", new BigDecimal("150"));
    context.setVariable("minimumAmount", new BigDecimal("100"));

    assertEquals(Boolean.TRUE, expression.getValue(context, Boolean.class));

    context.setVariable("minimumAmount", new BigDecimal("200"));

    assertEquals(Boolean.FALSE, expression.getValue(context, Boolean.class));
}
~~~

Cases to test:

- Variables registered with the exact name and type.
- Numeric, string, enum, and object variables read properly.
- Variables used in selection and projection.
- Variables used alongside root object and #this.
- Missing required variables.
- Variables with null values.
- Variables with incompatible types.
- Same Expression evaluated with multiple variable sets.
- Separate context per request when values change concurrently.
- Production context having the same configuration as the test context.

For object variables, test the properties accessed by the expression. For collection variables, verify element types and selection/projection outputs. For configuration variables, test boundary values and out-of-range values.

## 13. Workflow for Using Variables in an Application

When building parameterized expressions:

1. **Identify required inputs.** List each variable's name, type, and whether it is required or optional.
2. **Write a fixed expression.** Reference variables using #name; do not concatenate data into the string.
3. **Choose an EvaluationContext.** Use a context with the exact capabilities needed for properties, methods, and other operations.
4. **Create the context for the evaluation.** Set the root object and register all variables before calling getValue.
5. **Validate data.** Check null, type, value range, and permission to use the object.
6. **Evaluate the expression.** Request an explicit result type when the application needs a specific Boolean, number, or collection.
7. **Manage the context lifecycle.** Avoid updating variables on a context being used by multiple threads.
8. **Test and log errors.** Use the same context factory as production and record the expression ID for tracing.

If the variable list grows long or the expression depends on too many external objects, consider creating a single input object such as EvaluationParameters. This object groups related values, has explicit types, and is easy to validate before evaluation.

## 14. Best Practices

- Use setVariable("name", value) to register; use #name in the expression.
- Pick meaningful variable names with units when appropriate, such as minimumTotal or maximumAge.
- Distinguish #name from the name property of the current object.
- Use #root for the root object and #this for the current element in collection operations.
- Pass objects, collections, or enums with Java types instead of converting everything to strings.
- Reuse the Expression when syntax is unchanged and only context data varies.
- Create a dedicated context per request or evaluation when variables change per request.
- Validate required variables, null values, types, and value ranges before evaluating.
- Keep expressions separate from input data to avoid string concatenation bugs.
- Put only necessary objects into the context and limit access permissions.
- Use the same context factory in tests and production.
- Move multi-step logic or logic with side effects into clearly named Java methods.

## 15. Review Checklist

Before accepting an expression that uses context variables, check:

- [ ] Each variable has a clear name, type, and purpose.
- [ ] setVariable uses names without the # symbol.
- [ ] The expression references variables using #name syntax.
- [ ] Variables are not confused with properties of the root or current object.
- [ ] Root object and #this are used within the right scope.
- [ ] Required variables are registered before evaluation.
- [ ] Null and mistyped data are handled intentionally.
- [ ] Collection/object variables have appropriate structure and properties.
- [ ] Data is not concatenated directly into the expression string.
- [ ] EvaluationContext grants only the permissions and data required.
- [ ] Mutable contexts are not concurrently updated across requests.
- [ ] Tests cover multiple value sets, boundary values, and the production context.

## Conclusion

Variables in SpEL allow an application to pass data into an expression through EvaluationContext and reference that data using the **#name** syntax. Register variables using names without the # symbol, keep the root object and #this separate from variables, and use Java-typed values in conditions or collection operations. This allows reusing an Expression without concatenating data into the syntax string. Validate variables before evaluation, manage the context with an appropriate lifecycle, and restrict the objects and access permissions the expression is allowed to use.