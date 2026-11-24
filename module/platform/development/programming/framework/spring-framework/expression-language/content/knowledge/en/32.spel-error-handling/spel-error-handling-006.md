# Distinguishing Configuration Errors from Runtime Data Errors

## Objectives

After this lesson, you can distinguish errors caused by application configuration from errors caused by runtime data or state when using Spring Expression Language (SpEL); recognize parse errors, evaluation errors, property/method/bean resolution errors, and type conversion errors; determine when each error group should be detected; and design appropriate handling, logging, and error responses. You will also know how to validate expressions and `EvaluationContext` at startup to avoid letting early-detectable configuration errors reach live requests.

## 1. Two Groups of Causes to Distinguish

A SpEL expression can fail because the application's configuration is incorrect or because runtime data does not satisfy the conditions required by the expression.

**Configuration errors** stem from how the application defines, parses, or sets up the evaluation environment. Examples: invalid expression syntax, missing `BeanResolver`, wrong configured bean name, property accessor not supporting the object type, unregistered function, or unsuitable parser configuration.

**Runtime data errors** stem from specific values supplied during evaluation. Examples: a required variable is `null`, an intermediate property does not exist on the current data, an out-of-bounds index, a string that cannot be parsed as a number, or an order state that fails business rules.

| Group | Typical Cause | Usually Detected When |
|---|---|---|
| Configuration | Expression has invalid syntax | At parse time or bean initialization |
| Configuration | Missing BeanResolver for expressions using @bean | At evaluation time; should be detected at startup |
| Configuration | Function unregistered or registered with wrong Method | At evaluation time; should be checked when creating context |
| Configuration | Unsuitable PropertyAccessor/MethodResolver | When evaluating on the corresponding object type |
| Runtime | Variable or property has a null value | When evaluating with concrete data |
| Runtime | Index does not exist | When accessing a collection or array |
| Runtime | Value cannot be converted | When a converter is requested |
| Runtime/business | Invalid state or value | When checking business rules |

Not every configuration error appears immediately during parsing. The parser only checks language structure; some errors related to resolvers, object types, and access permissions only surface when the expression is evaluated. Therefore, proactively verify expression dependencies with representative data and context.

## 2. Parse and Evaluate Are Two Different Phases

SpEL typically has two main steps:

1. Parse the source string into an `Expression` object.
2. Evaluate the `Expression` with a specific `EvaluationContext` and root object.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#order.total >= #minimum");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("order", order);
context.setVariable("minimum", new BigDecimal("100.00"));

Boolean accepted =
    expression.getValue(context, Boolean.class);
~~~

If the string is missing a parenthesis or has an invalid operator, the error occurs in `parseExpression()`. If the string parses successfully but the `order` variable is not registered, or `order` is `null` when accessing `total`, the error occurs in `getValue()`.

An expression that parses successfully does not prove the expression will work with every context. It only proves the parser can build an expression structure from the source string.

For fixed expressions in configuration, parse and check dependencies as early as possible. When a request arrives, simply provide valid runtime data and perform evaluation.

## 3. Syntax Errors and Parse Errors

Parse errors usually indicate the expression string does not follow SpEL syntax. Common causes:

- Missing closing or opening parentheses/brackets.
- Unbalanced quotes in a string literal.
- Wrong operator or misplaced token.
- Incorrect selection, projection, or template delimiter syntax.
- Invoking a constructor or function with invalid syntax.
- Mixing literal text and SpEL without using a template `ParserContext`.

Invalid example:

~~~text
#order.total >=
~~~

Valid example:

~~~text
#order.total >= #minimum
~~~

You can catch parse errors at the configuration loading step:

~~~java
try {
    Expression expression = parser.parseExpression(source);
}
catch (ParseException ex) {
    // Report expression configuration error.
}
~~~

In SpEL, concrete parse errors are usually represented by `SpelParseException`, which belongs to Spring Expression's `ParseException` hierarchy. Preserve the error position and original message so configurators know which token needs fixing.

Do not wait until a rare request arrives to parse a fixed expression. If an expression is stored in a config file or database, validate it when the application loads configuration or when an administrator saves changes.

## 4. Parser and ParserContext Configuration Errors

The parser is created with `SpelParserConfiguration` and can use `ParserContext` to define how templates are read. If the configuration is unsuitable, expressions may fail immediately or behave unexpectedly.

For example, a template string with plain text and a SpEL segment:

~~~text
Hello, #{#customer.name}!
~~~

Must be parsed with `TemplateParserContext`:

~~~java
Expression expression = parser.parseExpression(
    template,
    new TemplateParserContext()
);
~~~

If that string is parsed as a regular expression, the parser tries to treat the entire sentence as SpEL syntax and may report an error.

Other configuration issues include compiler mode, auto-grow, auto-grow size limits, classloader, and parser settings for the running Spring version. Manage parsers with explicit configurations and do not inadvertently mix parsers with different `ParserContext` or compiler modes.

`ParserContext` determines how strings are split during parsing; it does not supply variables, beans, or access permissions during evaluation. Those belong to `EvaluationContext`.

## 5. Missing or Incorrect EvaluationContext Errors

`EvaluationContext` provides the root object, variables, and access mechanisms such as `PropertyAccessor`, `MethodResolver`, `BeanResolver`, `TypeConverter`, and registered functions.

An expression may parse properly yet fail to run if the context lacks required components.

Example expression using a variable:

~~~text
#minimumTotal
~~~

If Java does not call `setVariable("minimumTotal", value)`, the expression will not have the expected data.

Example expression referencing a bean:

~~~text
@pricingService.calculate(#order)
~~~

If the context is created manually without registering a `BeanResolver`, SpEL cannot resolve the bean reference.

Example expression calling a function:

~~~text
#normalize(#input)
~~~

If the `normalize` function is not registered via `registerFunction()` or the corresponding mechanism for your Spring version, evaluation will fail.

List the dependencies of each expression: root type, variable names, bean names, function names, and required access capabilities. Initialize the context deliberately with those dependencies.

## 6. Distinguishing Missing Configuration from Missing Data

The same access error can appear due to two different causes.

Example:

~~~text
#order.customer.name
~~~

If the `order` variable is not registered in the context, that is a context preparation error. If the variable is registered but the `order` value is `null`, that is runtime data missing an object. If `order` exists but the actual model does not have a `customer` property, it may be a data contract error or model change.

When investigating, check in order:

1. Is the expression source correct?
2. Does the context contain the required variables?
3. Do the root object and variables have the expected types?
4. Which step has a `null` concrete value?
5. Does `PropertyAccessor` support that target type and property?
6. Are the property or getter readable?

Do not collapse all errors into a message like "SpEL expression failed". Keep enough information to tell whether the error lies in configuration or in the data of a single execution.

## 7. Missing or Inaccessible Property Errors

An expression can access properties on the root object or on objects stored in variables:

~~~text
#customer.profile.displayName
~~~

Errors can occur when:

- The object type does not have a `profile` property.
- `PropertyAccessor` does not support the object type.
- The getter or property is inaccessible under the current configuration.
- An intermediate object is `null`.
- The model changed, but the expression has not been updated.

If every customer in the system must have a `profile` per data contract, the missing property may be a model or configuration error. If only a single record lacks a profile, that may be runtime data that should be handled according to business rules.

Distinguish "property does not exist" from "property exists but its value is null". The two cases require different fixes.

For long-lived expressions, test them against actual root object types at startup or in a configuration test suite.

## 8. Method Invocation and Function Errors

An expression can invoke methods on the root object, variables, or beans:

~~~text
#order.calculateTotal()
@pricingService.calculate(#order)
#normalize(#code)
~~~

Errors can include:

- The method does not exist on the actual object type.
- `MethodResolver` does not allow the call.
- Argument count or types do not match.
- Function is unregistered or wrong `Method` was registered.
- The method throws an exception during execution.
- The method has side effects or depends on external state.

Distinguish errors finding/calling the method from exceptions raised by the method itself. For example, `calculateTotal()` may be found and invoked successfully, yet throw an error internally because order data is missing.

At configuration time, verify the methods/functions the expression requires. At runtime, log the root exception from the method along with necessary business context, while avoiding sensitive data.

## 9. Bean Reference and Alias Errors

Expressions using `@beanName` depend on `BeanResolver` and bean names in the container.

Example:

~~~text
@'order.service'.calculate(#order)
~~~

Possible causes include:

- A manually created context lacks a `BeanResolver`.
- The bean name or alias does not exist.
- The bean name contains special characters but is not enclosed properly in a string literal.
- The bean exists but cannot be initialized because another dependency failed.
- The bean is found, but the subsequent method does not exist or is not allowed to be called.

If a bean name is wrong in a fixed configuration, treat it as a configuration error and detect it during application startup. If a bean has a scope or dependency that is only created upon access, the error may only surface on the first evaluation.

Do not replace a bean resolution error with `null` and keep computing. That can hide deployment errors and produce wrong results.

## 10. Conversion Errors Differ from Validation Errors

SpEL may need `TypeConverter` when retrieving a result as a target type, assigning a property, or passing arguments to a method.

Example:

~~~java
Expression expression = parser.parseExpression("'abc'");
Integer value = expression.getValue(Integer.class);
~~~

The string `abc` cannot be converted to `Integer` by a suitable converter, so evaluation fails at the conversion step.

Another case:

~~~text
#quantity >= 1
~~~

If `quantity` is `Integer` `500`, the expression can run normally. `quantity` exceeding business limits is a validation issue, not a conversion or parse error.

Distinguish:

- Conversion error: cannot convert the value to the required type.
- Validation error: the value already has the right type, but violates rules.
- Configuration error: the required converter is unregistered or misconfigured.
- Runtime data error: specific data cannot be converted or has an invalid state.

Do not use arbitrary default values when conversion fails, as that can turn invalid data into seemingly valid results.

## 11. Null, Index, and Runtime Data Errors

Common runtime errors stem from concrete values:

- Root object is `null`.
- Variable has a `null` value.
- Intermediate property is `null`.
- Collection is empty or index is out of bounds.
- `Map` does not contain the requested key.
- Collection element has a different type than expected.
- Malformed string data.

Example:

~~~text
#orders[0].id
~~~

The expression assumes `orders` has a first element and that element has an `id` property. If `orders` is empty, `null`, or the first element is `null`, evaluation can fail.

If missing data is allowed, express it explicitly in the expression:

~~~text
#customer?.profile?.displayName ?: 'Guest'
~~~

If the data is mandatory, validate before calling SpEL or let the runtime error translate into a meaningful business error. Do not use safe navigation to mask a violation of a mandatory data contract.

## 12. Compiler Configuration and Compiled Expression Errors

The SpEL compiler can alter how expressions execute. An expression may run in interpreted mode yet encounter issues when compiled because runtime data types no longer match the compiled version's assumptions or because the expression structure is unsupported.

Distinguish:

- An unsuitable compiler mode or wrong classloader is a configuration issue.
- Object types legitimately varying across evaluations can be a runtime condition.
- Expressions unsupported for compilation can continue running interpreted.
- Business errors from getters or methods do not automatically become compiler configuration errors.

When investigating, test the same expression in `OFF` mode to determine whether the error depends on compiled mode. Inspect the root object type, variable types, and implementations used at runtime.

`MIXED` mode has a fallback mechanism back to interpreted mode in some situations where the compiled expression is no longer applicable. Do not treat that mechanism as a handler for all exceptions or all data errors.

## 13. Classifying Spring Expression Exceptions

Common exceptions belong to the Spring Expression exception hierarchy:

| Type | Role |
|---|---|
| ParseException | Error while parsing expression syntax |
| SpelParseException | SpEL-specific parse error, includes position info |
| EvaluationException | Error during expression evaluation |
| SpelEvaluationException | SpEL-specific evaluation error |

In Java, you can catch `ParseException` in the parse phase and `EvaluationException` in the evaluate phase:

~~~java
Expression expression;

try {
    expression = parser.parseExpression(source);
}
catch (ParseException ex) {
    throw new IllegalStateException(
        "Invalid SpEL configuration", ex
    );
}

try {
    Object result = expression.getValue(context);
}
catch (EvaluationException ex) {
    throw new IllegalArgumentException(
        "Unable to evaluate expression for current data", ex
    );
}
~~~

The snippet illustrates how to separate handling boundaries. In real applications, exceptions may be wrapped by bean creation, configuration loading, or service layers. Preserve the cause chain so the original cause is not lost.

Do not catch generic `RuntimeException` everywhere and return `null`. Doing so erases the distinction between configuration errors, data errors, and programming bugs.

## 14. Detecting Configuration Errors at Startup

For expressions declared in config files, annotations, or databases, validate as early as possible.

A startup workflow may include:

1. Load the list of expressions.
2. Parse each expression with the right `ParserContext`.
3. Create an `EvaluationContext` with corresponding resolvers and accessors.
4. Verify required variables, beans, and functions are registered.
5. Evaluate with representative test data or suitable sample objects.
6. Report configuration errors with the expression name and declaration location.
7. Keep misconfigured expressions out of production processing flows.

Not every expression can be evaluated completely at startup because it depends on request data. In that case, verify parsing, types, and static dependencies first; check concrete data at runtime.

You can create a dedicated initializer component or configuration validation step to run these checks. Avoid calling real services or causing side effects just to test expressions at startup.

## 15. Handling Runtime Errors at the Appropriate Boundary

Runtime errors should be handled where the application understands the meaning of the data.

For example, a service receives an order and evaluates a condition:

~~~java
public boolean isEligible(Order order) {
    if (order == null) {
        throw new IllegalArgumentException("Order is required");
    }

    StandardEvaluationContext context =
        new StandardEvaluationContext(order);

    context.setVariable(
        "minimumTotal",
        new BigDecimal("100.00")
    );

    return eligibilityExpression.getValue(
        context,
        Boolean.class
    );
}
~~~

If `order` is `null`, the service can reject immediately with a clear input error. If the expression fails due to configuration that was already checked at startup, that may be an internal error requiring appropriate logging and operational alerts.

Do not turn every `EvaluationException` into a user error. Some errors are bugs or misconfigurations that should be treated as server errors; some errors are invalid input data requiring actionable messages.

## 16. Logging Enough Information Without Exposing Sensitive Data

Useful logs should indicate:

- Expression identifier or configuration name.
- Error phase: parse, context setup, evaluate, or conversion.
- Exception type and cause chain.
- Root object type and related configuration version.
- Request correlation ID or job ID if available.
- Parse error position when available.
- Related input data category in sanitized form.

Avoid logging the entire expression if it contains secrets, tokens, or personal data. Never log raw root objects, passwords, access tokens, or sensitive content.

For fixed expressions, use a stable identifier to locate the source configuration. For admin-created expressions, log the template version or revision to identify which version caused the error.

User-facing messages should be concise and not reveal internal details such as bean names, packages, classloaders, or domain object structures.

## 17. Do Not Use Fallbacks to Mask Configuration Errors

Some applications may be tempted to return a default value when an expression fails. This is only appropriate when the default is a clearly defined business behavior.

Example:

~~~text
#customer?.nickname ?: 'Customer'
~~~

This is an explicit fallback for when `nickname` is `null`.

However, if `@pricingService` does not exist or the `normalize` function is not registered, returning `0` or an empty string can mask a configuration error. That result could flow into invoices, pricing decisions, or incorrect notifications.

Distinguish fallbacks for optional data from swallowing exceptions. Fallbacks should be written explicitly in the expression or Java logic and applied only to approved states.

## 18. Testing Both Error Groups Separately

Tests should be organized by cause:

| Group | Scenario | Expected Result |
|---|---|---|
| Configuration | Expression has invalid syntax | Parse fails before runtime |
| Configuration | Missing BeanResolver | Configuration check detects it |
| Configuration | Wrong bean name | Configuration validation or context test fails |
| Configuration | Function not registered | Dependency check detects it |
| Configuration | Accessor does not support type | Test with target type fails clearly |
| Configuration | Unsuitable compiler/classloader | Detected in compiler mode tests |
| Runtime | Null variable | Follows defined null contract |
| Runtime | Null intermediate property | Safe navigation or clear business error |
| Runtime | Out-of-bounds index | Data error handled appropriately |
| Runtime | Malformed number string | Conversion error |
| Runtime | Value outside min/max | Validation error |
| Runtime | Method throws exception | Cause chain preserved |

Configuration should have unit tests or integration tests independent of request data. Runtime should have tests for valid data, nulls, missing fields, and edge cases.

A test that only confirms an expression parses successfully is insufficient if the expression also depends on beans, functions, method resolvers, or property accessors.

## 19. Investigation Checklist When an Expression Fails

When receiving a SpEL error, verify in sequence:

1. Did the error occur in `parseExpression` or `getValue`/`setValue`?
2. Are the expression source and `ParserContext` correct?
3. Is the root object of the right type and non-null?
4. Are required variables registered?
5. Are the needed `BeanResolver`, functions, and resolvers present?
6. Does the property or method exist on the actual runtime type?
7. Is any intermediate object or collection `null`/empty?
8. Does `TypeConverter` support the required conversion?
9. Does the converted value violate business limits?
10. Does the error only appear in compiled mode?
11. Is the root exception a SpEL error or from an invoked method/getter?
12. Is this a configuration error to fix once, or bad request data to reject?

This classification helps choose the right place to fix. Do not alter request data to hide a wrong bean name; nor should you change system-wide configuration just because one record is missing an optional value.

## 20. Key Takeaways

Configuration errors originate from the expression source, parser, `ParserContext`, `EvaluationContext`, or improperly declared resolvers and dependencies. Runtime data errors originate from the concrete root object, variables, properties, collections, types, or state at evaluation time.

Successful parsing does not guarantee successful evaluation. Distinguish `ParseException`/`SpelParseException` from `EvaluationException`/`SpelEvaluationException`; validate fixed configuration at startup and handle runtime data at the appropriate business boundary.

When investigating, identify the error phase, inspect the context and object types, distinguish non-existent properties from `null` values, conversion from validation, and method call errors from exceptions inside the method. Preserve the cause chain, log the expression identifier and sanitized context, and never log secrets or entire sensitive objects.

Do not use default values to mask configuration errors. Only apply fallbacks for optional data according to clear rules. Fixed expressions should be parsed and dependency-checked early; request-dependent expressions should be tested with boundary data and consistent runtime error handling.

## References

- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework Reference — Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html)
- [ParseException Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ParseException.html)
- [EvaluationException Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationException.html)
- [SpelEvaluationException Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelEvaluationException.html)