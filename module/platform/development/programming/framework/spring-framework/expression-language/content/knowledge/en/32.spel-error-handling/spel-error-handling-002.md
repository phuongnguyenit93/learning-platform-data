# EvaluationException and Errors During Evaluation

SpEL separates expression usage into two main phases: parsing the expression string to create an `Expression` object, and then evaluating the `Expression` with specific data and an `EvaluationContext`. Errors can appear in both phases. Properly distinguishing when an error occurs helps identify whether the cause lies in syntax, input data, context configuration, type conversion, or an invoked method.

In Spring Expression, `EvaluationException` is the exception hierarchy for errors during expression processing. SpEL has concrete classes such as `SpelParseException` for parsing errors and `SpelEvaluationException` for many evaluation-time errors. When handling errors, inspect the exception type, position in the expression, message code, and root cause rather than reading just a single message line.

## 1. Two Phases: Parse and Evaluate

An expression is typically created using an `ExpressionParser`:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("name == 'Lan'");
~~~

Calling `parseExpression` parses the string and creates an `Expression`. If the string has invalid syntax, the error occurs immediately in the parse phase.

Afterward, `getValue` evaluates the expression:

~~~java
Boolean result = expression.getValue(
        context,
        rootObject,
        Boolean.class
);
~~~

Errors in this phase can be caused by a non-existent property, a null object, an unresolvable method, wrong argument types, an unsupported converter, or an invoked method throwing an exception.

The two phases should be handled separately in code. This helps log and report errors more accurately, especially when an expression is parsed once and evaluated many times with different data.

## 2. Main Spring Expression Exceptions

Some commonly encountered exception classes:

| Exception | Role |
|---|---|
| EvaluationException | General exception class for expression evaluation errors |
| ParseException | Error during expression parsing |
| SpelParseException | SpEL-specific class for parse errors |
| SpelEvaluationException | SpEL-specific class for evaluation errors |

`ParseException` and `SpelParseException` belong to the Spring Expression exception branch dedicated to parsing. `SpelEvaluationException` is typically used when SpEL cannot complete an operation during evaluation.

Not all errors have the same cause. A parse error usually indicates the string does not follow the grammar; an evaluation error may depend on the root object or context that only appears at runtime.

When writing a `catch` block, catch the most specific exception the application can handle. If you need to catch the whole group, use `EvaluationException` at the evaluation boundary after separating parse errors.

## 3. Catching Parse Errors Separately from Evaluation Errors

Example:

~~~java
Expression expression;

try {
    expression = parser.parseExpression(
            "#order.total > 100"
    );
} catch (ParseException ex) {
    // Invalid expression string.
    throw ex;
}

try {
    Boolean accepted = expression.getValue(
            context,
            Boolean.class
    );
} catch (EvaluationException ex) {
    // Expression parsed but could not be evaluated.
    throw ex;
}
~~~

You must catch `ParseException` first if sharing a single `try` block because it belongs to the Spring Expression exception hierarchy and can be treated as a form of `EvaluationException`.

If the application parses expressions at startup, parse errors can prevent the context from initializing. If expressions are evaluated per request, evaluation errors may only occur for a specific dataset or context.

Do not merge both into a generic message like “SpEL failed”. Record the error phase so operators know whether to check the expression configuration or runtime data.

## 4. SpelParseException: Syntax Errors

`SpelParseException` appears when the parser cannot understand the expression string. Common causes include:

- Missing or extra brackets/parentheses.
- Unclosed string literals.
- Incorrect operator or operand syntax.
- Invalid selection/projection structure.
- Mistyped function, type reference, or bean reference syntax.
- Incorrect separators in nested expressions.

Error examples:

~~~java
parser.parseExpression("total >");
parser.parseExpression("'Spring");
parser.parseExpression("#items.?[active == true");
~~~

The parser cannot create a valid `Expression` from these strings.

When diagnosing, check the error position provided by the exception if available. For long expressions, the character position helps locate the wrong bracket or operator faster than re-reading the entire string.

If the expression is built by concatenating multiple strings, log or reconstruct the final string passed to the parser. Do not log only individual fragments because the error can occur at the boundary between two fragments.

## 5. SpelEvaluationException: Errors During Evaluation

`SpelEvaluationException` occurs when the expression has been parsed, but an operation cannot complete at runtime.

Example:

~~~java
Expression expression =
        parser.parseExpression("customer.address.city");

String city = expression.getValue(
        context,
        rootObject,
        String.class
);
~~~

The expression can parse successfully, but fails during evaluation if `customer` does not exist on the root object, `address` is null, or the property accessor cannot read `city`.

Other causes include:

- Property or method does not exist.
- Method is not permitted to be called in the current context.
- Unregistered function.
- Bean or type cannot be resolved.
- Invalid index or key.
- Data types incompatible with the operator.
- Conversion cannot be performed.
- Getter, setter, or method throws an exception.

To find the cause, inspect the root object, variables, and resolvers of the exact `EvaluationContext` passed to `getValue`. The same `Expression` can succeed with one context and fail with another.

## 6. Reading Position and Error Codes

Spring Expression exceptions can provide information about the position in the expression, message codes, and values related to the error. With SpEL, `SpelMessage` describes specific error types such as property not found, method cannot be invoked, or type cannot be converted.

When handling errors, record at minimum:

- Exception type.
- Message code if provided by the specific exception.
- Error position if available.
- Rule name or configuration code being evaluated.
- Root cause in the cause chain.
- Root object type and rule version if this information is safe to log.

Do not rely on the full message text to categorize errors because message content can change across framework versions or languages. If handling by error code is needed, use the corresponding exception API and verify the Spring version the application is running.

Avoid logging the entire root object or all context variables. The data may contain personal information, tokens, account details, or configuration secrets.

## 7. Property Not Found Errors

An expression may reference a property that does not exist on the current object:

~~~text
#customer.dispayName
~~~

The example above misspells `displayName`. The parser may still accept the syntax, but during evaluation, `PropertyAccessor` cannot find the corresponding property.

Common causes:

- Misspelled property name.
- Root object has a different type than expected.
- Getter does not follow the property convention recognized by the accessor.
- Custom `PropertyAccessor` does not support the object type.
- Context restricts property read permissions.
- The expression is inside a collection operation so the current object differs from the root object.

Verify the actual object and property path at each level. For expressions with `#this`, check whether `#this` points to the root object or a collection element.

Do not handle every property error by returning `null`. A forbidden property, a misspelled property, and a property with a `null` value are different situations that need to be distinguished.

## 8. Null Errors When Accessing Nested Objects

A property path can traverse multiple objects:

~~~text
#order.customer.address.city
~~~

If `customer` or `address` is `null`, subsequent access can fail. This is a runtime error, not a syntax error.

You can check beforehand:

~~~text
#order.customer != null and
#order.customer.address != null and
#order.customer.address.city == 'Da Nang'
~~~

`AND` has short-circuiting: when a left-hand condition is `false`, subsequent conditions do not need to be evaluated.

SpEL also has the safe navigation operator `?.` in appropriate access contexts:

~~~text
#order.customer?.address?.city
~~~

Safe navigation can help return `null` when the object before the operator is `null`. However, you must understand how this operator propagates through the entire expression and the expected result type. It does not replace validation if the property is required to exist.

If input data missing structure is a business error, detect and report it clearly instead of turning every case into `null`.

## 9. Method Resolution and Method Invocation Errors

An expression can invoke methods on the root object, variables, or property objects:

~~~text
#customer.calculateDiscount()
#text.substring(0, 5)
~~~

Errors can occur when:

- The object does not have the invoked method.
- The number or types of arguments do not match.
- `MethodResolver` does not permit that method.
- The method is not accessible.
- The selected method throws an exception when running.
- A `null` argument is not handled by the method.

Distinguish method-not-found errors from errors inside the method. If the method was invoked and threw an exception, inspect the root cause to determine whether the error belongs to Java logic or SpEL.

Do not catch all exceptions and treat the method as returning `null`. That can hide errors in services, databases, or domain rules. Give methods clear contracts and handle exceptions at the appropriate application layer.

## 10. Unregistered Function or Wrong Signature Errors

Registered functions are invoked using `#functionName(...)` syntax. If the function does not exist in `EvaluationContext`, SpEL cannot resolve the call.

~~~text
#normalize(#rawName)
~~~

Common causes:

- The function is not registered in the context being evaluated.
- The name in `registerFunction` differs from the name in the expression.
- The context was recreated without registering the function.
- The function is overwritten by a binding with the same name in the context.
- The number or types of arguments do not match the registered `Method`.
- Conversion to the parameter type fails.

Check function configuration in the exact context, not just where the parser is initialized. The parser creates the `Expression`; `EvaluationContext` provides functions and bindings during evaluation.

If a function has multiple overloads, specify the exact `Method` being registered. A registered function name is bound to a specific `Method`, so do not expect SpEL to automatically pick an overload like a regular method call on an object.

## 11. Type Reference and Bean Reference Errors

Type references use `T(...)` syntax. If `TypeLocator` cannot resolve the class, the expression may parse but fail during evaluation:

~~~text
T(com.example.MissingType)
~~~

Bean references use `@beanName` syntax. If `BeanResolver` is not configured or the bean does not exist, resolution may fail:

~~~text
@pricingService.currentRate()
~~~

Check:

- Class and package names.
- The `TypeLocator` used by the context.
- Bean name and `ApplicationContext`.
- Whether `BeanResolver` is provided.
- Whether the current context supports type/bean references.

`SimpleEvaluationContext` restricts many features compared to `StandardEvaluationContext`. An expression using `T(...)` or `@beanName` may not fit a restricted context. Do not widen the context just to make the error disappear if the use case does not actually need that capability.

## 12. Indexer, Collection, and Map Errors

Indexers can be used to read a `List`, array, or `Map`:

~~~text
#items[0]
#settings['region']
~~~

Runtime errors can occur when:

- The index is negative or out of bounds for the array/`List`.
- The source collection is `null`.
- The key is missing from the `Map` and the expression continues accessing a property on the `null` result.
- The key has a different type from the actual key.
- The collection does not support write operations.
- The element at the selected position is `null`.

For a `Map`, a missing key usually results in `null`. If you need to distinguish a missing key from a `null` value, use `containsKey()` before reading.

For a `List` or array, check the size before accessing an index if the position comes from dynamic data. For write operations, confirm the collection is mutable and the target position already exists.

## 13. Incompatible Operator and Data Type Errors

An expression may apply operators to inappropriate data types:

~~~text
#price + #customer
#createdAt > #quantity
~~~

SpEL has operator and conversion mechanisms, but not every pair of types makes sense or can be converted.

For example, addition between two numbers may be valid; addition between a number and a domain object depends on the operator, converters, and actual data types. Comparing two objects also depends on their types and comparability.

Inspect the runtime types of variables and properties. If conversion is needed, perform explicit conversion or normalize data before putting it into the context.

Do not rely on an expression parsing successfully to conclude that an operation is definitely valid. Parsing checks syntax; many type issues only appear when the expression is evaluated with concrete data.

## 14. Type Conversion Errors

SpEL can use the `TypeConverter` of `EvaluationContext` when needing to convert a value to a target type, for example in typed `getValue`, property assignment, or calling a method with parameters of a different type.

Example:

~~~java
Expression expression =
        parser.parseExpression("#rawAge");

Integer age = expression.getValue(
        context,
        Integer.class
);
~~~

If `rawAge` is the string `"twenty"`, the default converter cannot convert it to `Integer`. The error occurs during the evaluation or conversion phase.

Common causes:

- Source data is malformed.
- No converter exists for the source/target type pair.
- A custom converter rejects the value.
- A `null` value is assigned to a primitive.
- The return type is incompatible with the type requested by the caller.

When custom domain types are needed, configure `StandardTypeConverter` with a `ConversionService` that has the corresponding converters. A converter should only be responsible for type conversion; business validation must still be performed separately.

## 15. Errors When Writing Properties with setValue

`Expression.setValue` also evaluates the property path and performs a write, so it can raise `EvaluationException`.

Example:

~~~java
Expression expression =
        parser.parseExpression("address.city");

expression.setValue(context, customer, "Da Nang");
~~~

Errors can occur if:

- The property does not exist or has no setter.
- The intermediate object `address` is `null`.
- The current accessor is read-only.
- The new value cannot be converted to the target type.
- The object or collection does not support updates.
- The setter throws an exception due to validation or invariants.

Being able to read a property does not guarantee you can write to it. For immutable objects, create a new object via a constructor or factory instead of trying to use `setValue`.

If an expression only needs to read, use a read-only context. Do not grant write permissions just to avoid an accessor error.

## 16. Exceptions from Methods Invoked Inside Expressions

When SpEL invokes a Java method, the method may throw exceptions such as `IllegalArgumentException`, `IllegalStateException`, or a custom business exception. The framework may wrap this error in an evaluation exception.

Example:

~~~java
public static BigDecimal calculateTax(BigDecimal amount) {
    if (amount.signum() < 0) {
        throw new IllegalArgumentException(
                "Amount must be non-negative"
        );
    }
    return amount.multiply(new BigDecimal("0.08"));
}
~~~

If the expression calls this function with a negative `amount`, the root error comes from the method. Inspect the cause chain to distinguish a method that ran and rejected the data from a SpEL error failing to resolve the function.

Methods used in expressions should have clear contracts, validate inputs, and avoid side effects. If a method may call a database or API, clearly decide how to handle errors, timeouts, and transactions at the service layer.

## 17. Error Handling Strategies by Use Case

There is no single default policy suitable for every expression. The handling approach depends on the consequences if the expression fails to evaluate.

| Use Case | Typically Appropriate Handling |
|---|---|
| Required configuration at startup | Fail fast and clearly report the offending expression/property |
| Access-control decision rule | Fail closed; errors must not turn into permission granted |
| Optional display value | May use a defined fallback |
| Administrator-configured rule | Report validation error before publishing the rule |
| Per-request expression | Log error with request/rule ID and return an appropriate error |
| Financial calculation | Do not use silent defaults; propagate error to the business layer |

Do not return `true` when an expression fails if the expression decides permissions, eligibility, or critical conditions. A fallback is only safe when the business has clearly defined the replacement value and operators know when the fallback is used.

For required configurations, failing fast typically helps detect errors immediately at startup rather than letting the application run in an invalid state.

## 18. Useful Error Logging Without Exposing Data

Logs should help reproduce the issue without exposing sensitive information.

Useful information:

- Rule ID or identified expression name.
- Parse or evaluate phase.
- Exception type and message code if available.
- Error position if provided by the exception.
- Root object type.
- Configuration version or deployment ID.
- Root cause filtered of sensitive information.

Avoid logging passwords, access tokens, payment information, entire entities, or all context variables. If expressions are user-provided, the expression string itself may also contain personal data; apply appropriate logging policies.

Do not log full stack traces for every expected input error at `ERROR` level if it creates heavy log noise. However, do not strip the root cause when investigating programming or system errors.

## 19. Parse Once, Evaluate Many Times

If an expression is fixed or pre-configured by an administrator, parse it once and reuse the `Expression`:

~~~java
Expression expression =
        parser.parseExpression("#order.total >= #minimum");

for (Order order : orders) {
    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable(
            "minimum",
            new BigDecimal("100.00")
    );

    Boolean accepted = expression.getValue(
            context,
            Boolean.class
    );
}
~~~

This separates parse errors from per-order evaluation errors. If the expression has invalid syntax, it is detected immediately when loading the rule. If an order has anomalous data, the evaluation error can be linked to the exact record.

Do not share a mutable `EvaluationContext` across multiple threads or requests if the root object and variables change. Create a separate context for each evaluation or manage data in a concurrency-safe manner.

If the expression changes, re-parse the new version and manage the `Expression` lifecycle/cache by rule ID or configuration version.

## 20. Testing Error Scenarios

In addition to success cases, test the errors that can occur in both phases.

Useful test groups:

1. Syntactically invalid expressions must produce parse errors.
2. Non-existent properties must be handled according to policy.
3. Null root object or intermediate properties.
4. Unregistered method or function.
5. Method is invoked and throws an exception.
6. Unresolved type reference or bean reference.
7. Wrong argument types or unsupported converter.
8. Out-of-bounds index and missing `Map` key.
9. `setValue` on a read-only property.
10. Expressions restricted by `SimpleEvaluationContext`.
11. Errors must not turn into a default allow result.
12. Logs must not contain sensitive data.

Tests should use the application's actual `EvaluationContext`, accessors, resolvers, and converters. A test that only calls `parseExpression` cannot verify data-dependent runtime errors.

## 21. Complete Example: Separating Parse and Evaluate, Recording Cause

~~~java
public class RuleEvaluator {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    public boolean evaluate(
            String ruleId,
            String expressionText,
            EvaluationContext context) {

        final Expression expression;

        try {
            expression = parser.parseExpression(expressionText);
        } catch (ParseException ex) {
            // Record ruleId, parse error type, and position if available.
            throw new IllegalArgumentException(
                    "Invalid rule syntax: " + ruleId,
                    ex
            );
        }

        try {
            Boolean result = expression.getValue(
                    context,
                    Boolean.class
            );

            return Boolean.TRUE.equals(result);
        } catch (EvaluationException ex) {
            // Record ruleId, exception, and root cause.
            throw new IllegalStateException(
                    "Could not evaluate rule: " + ruleId,
                    ex
            );
        }
    }
}
~~~

The example illustrates separating errors and normalizing exceptions at the application boundary. The policy of returning `false` when a `Boolean` result is `null` must be decided by use case; for authorization or critical rules, do not use this default if it could unintentionally open permissions.

In real-world applications, you can create custom domain exceptions such as `RuleParseException` and `RuleEvaluationException` so callers can distinguish configuration errors from runtime data errors. Do not lose the root cause when wrapping exceptions.

## 22. Key Takeaways

`ParseException` or `SpelParseException` reports errors when the parser cannot create an `Expression` from a string. `EvaluationException` and `SpelEvaluationException` report errors during evaluation, such as missing properties, methods, functions, types, or beans; null objects; invalid indices; incompatible types; failed conversions; or methods throwing exceptions.

Separate parsing from evaluation, check the position and message code if available, inspect the cause chain, and confirm the correct root object and `EvaluationContext`. Parse once for stable rules, but create an appropriate context for each evaluation.

Choose policies according to the consequences of the rule: required configurations should fail fast, authorization rules should fail closed, and fallbacks should only be used when clearly defined by business requirements. Log enough information for investigation without recording sensitive data, and test both syntax errors and runtime errors.