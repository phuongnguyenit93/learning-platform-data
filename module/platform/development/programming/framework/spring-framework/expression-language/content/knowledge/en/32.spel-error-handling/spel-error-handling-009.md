# Designing Explicit Fallbacks Instead of Swallowing Expression Errors in SpEL

## 1. Why Should You Not Swallow Expression Errors?

Spring Expression Language (SpEL) allows reading properties, invoking methods, performing calculations, accessing collections, and combining multiple conditions. When an expression fails to evaluate, the application needs to decide explicitly: is this optional data where a replacement value can be used, or is it a configuration/programming error that must be reported?

A dangerous handling pattern is catching all exceptions and returning a default value:

```java
try {
    return expression.getValue(context, root, Boolean.class);
}
catch (Exception ex) {
    return false;
}
```

This snippet loses the real cause of the error. A mistyped expression, a renamed property, a missing converter, a method throwing an error, or mismatched data types can all be turned into `false`. The application keeps running, yet business results may be wrong without anyone noticing.

A good fallback needs to answer four questions:

1. In which cases is a fallback permitted?
2. Is the fallback value of the right type and safe for business logic?
3. Is the original error logged and monitored?
4. In which cases must processing stop and propagate the error to the caller?

Not every expression error is a recoverable situation. Use fallbacks only for predefined cases, such as missing optional data or a value that may be `null` according to the data contract.

## 2. Separating Parse Errors from Evaluation Errors

SpEL has two separate phases:

- Parse: `ExpressionParser.parseExpression(source)` analyzes syntax and creates an `Expression`.
- Evaluation: `Expression.getValue(...)` executes the expression against an `EvaluationContext` and a root object.

Example:

```java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("customer.age >= 18");

Boolean allowed =
        expression.getValue(customer, Boolean.class);
```

If the source has invalid syntax, the error occurs at the parse step. If the expression is syntactically valid but the `age` property does not exist on the object, the error occurs at the evaluation step.

| Phase | Common Exception Group | Example Causes |
|---|---|---|
| Parse | `ParseException`, usually `SpelParseException` | Missing brackets, unclosed quotes, misplaced operators. |
| Evaluation | `EvaluationException`, usually `SpelEvaluationException` | Non-existent property, incompatible method call, conversion error, or operation error. |

If the expression comes from fixed configuration, parse and validate it immediately at application startup. A syntax error in configuration is usually a deployment bug; do not wait until a request runs through and replace it with a default value.

For expressions updated by administrators, parse before accepting the new configuration. Only bring successfully parsed expressions into active use. Keep the currently working configuration if the new version is invalid and report the error clearly to the administrator.

## 3. Using the Elvis Operator for Null Values or Empty Strings

SpEL supports the Elvis operator `?:` to choose a replacement value when the left side is `null`. For `String`, an empty string is also treated as having no value.

Example:

```text
customer.nickname ?: 'Guest'
```

If `nickname` is `null` or an empty string, the result is `'Guest'`. If `nickname` has a value, SpEL keeps that value.

It can be combined with safe navigation:

```text
customer?.profile?.displayName ?: 'Guest'
```

In this example, if `customer`, `profile`, or `displayName` has no value because an intermediate object is `null`, the expression can return the fallback `'Guest'`.

The Elvis operator is suitable for optional data, such as display names, labels, or non-mandatory descriptions. It is not an exception-catching mechanism.

The following cases can still raise errors:

- Property `nickname` does not exist.
- Property has a getter that throws an exception.
- A method called on the left side throws an exception.
- The expression has invalid syntax.
- The result cannot be converted to the target type requested by the caller.

For example, `unknownProperty ?: 'Guest'` does not guarantee returning `Guest`. If `unknownProperty` does not exist on the object, SpEL cannot read the left side to apply Elvis.

## 4. Safe Navigation Handles Null, Not Exceptions

The safe navigation operator `?.` stops property access or method invocation when the object immediately preceding the operator is `null` and returns `null`.

Example:

```text
customer?.address?.city
```

If `customer` is `null`, SpEL does not attempt to read `address`. If `address` is `null`, SpEL does not attempt to read `city`. The result of the safe access chain is `null`.

It can be used together with Elvis to produce a default value:

```text
customer?.address?.city ?: 'Unknown city'
```

However, safe navigation does not catch errors thrown by getters or methods:

```text
customer?.loadProfile()?.displayName
```

If `customer` is non-null yet `loadProfile()` throws an exception, the exception is still propagated. Safe navigation only checks `null` on the receiving object.

For multi-level access chains, place `?.` at every segment that can be `null`. Do not assume a single safe navigation operator at the start makes the entire trailing expression safe.

## 5. Fallbacks for Optional Data and Fallbacks for Errors Are Different

Distinguish the following cases:

| Situation | Appropriate Mechanism |
|---|---|
| Property exists but has a null value | Safe navigation or Elvis. |
| Optional String is an empty string | Elvis operator. |
| Property does not exist or is misspelled | Fix the expression/model; do not use Elvis to hide errors. |
| Expression has invalid syntax | Report configuration error during the parse phase. |
| Value cannot be converted to target type | Identify data/conversion error and handle separately. |
| Invoked method throws an exception | Diagnose the method and decide whether recovery is permitted by contract. |
| External service is temporarily unavailable | Use retry/timeout/circuit breaker or service-layer fallback; do not assume Elvis handles it. |

For example, a UI label can use a fallback when missing:

```java
String label = parser.parseExpression(
        "customer?.profile?.displayName ?: 'Guest'")
        .getValue(context, customer, String.class);
```

Conversely, for conditions deciding access permissions or pricing, a missing property or evaluation error should generally be treated as an error requiring explicit handling. Never automatically convert it to an allow result or an amount of `0`.

## 6. Designing Wrappers to Preserve the Root Cause

A wrapper class can add business context to a SpEL error while keeping the original exception as the cause.

Example:

```java
public class RuleEvaluationException extends RuntimeException {

    private final String ruleId;

    public RuleEvaluationException(
            String ruleId,
            String message,
            Throwable cause) {
        super(message, cause);
        this.ruleId = ruleId;
    }

    public String getRuleId() {
        return ruleId;
    }
}
```

Parse the expression when loading the rule:

```java
public Expression parseRule(
        String ruleId,
        String source,
        ExpressionParser parser) {

    try {
        return parser.parseExpression(source);
    }
    catch (ParseException ex) {
        throw new IllegalArgumentException(
                "Invalid SpEL rule: " + ruleId, ex);
    }
}
```

Evaluate the expression:

```java
public <T> T evaluateRule(
        String ruleId,
        Expression expression,
        EvaluationContext context,
        Object root,
        Class<T> targetType) {

    try {
        return expression.getValue(context, root, targetType);
    }
    catch (EvaluationException ex) {
        throw new RuleEvaluationException(
                ruleId,
                "Could not evaluate SpEL rule: " + ruleId,
                ex);
    }
}
```

Callers can distinguish which rule failed and still access the root cause via `getCause()`. The wrapper does not turn the error into a fake value; it makes the error easier to locate and handle.

Depending on the application, you can add rule version, tenant, correlation ID, or operation name. Do not put the entire expression or sensitive data into error messages returned to clients.

## 7. When Is a Fallback Permitted After EvaluationException?

Some systems have an explicit contract allowing a fallback if a specific condition cannot be evaluated, such as an optional label computed from non-mandatory data. In that case, classify recoverable errors rather than catching all exceptions.

You can separate fallback policy from evaluation code:

```java
public <T> T evaluateOptionalRule(
        String ruleId,
        Expression expression,
        EvaluationContext context,
        Object root,
        Class<T> targetType,
        T fallbackValue,
        Predicate<EvaluationException> recoverable) {

    try {
        return expression.getValue(context, root, targetType);
    }
    catch (EvaluationException ex) {
        if (!recoverable.test(ex)) {
            throw new RuleEvaluationException(
                    ruleId,
                    "Could not evaluate rule: " + ruleId,
                    ex);
        }

        log.warn(
                "Using fallback for optional rule {}",
                ruleId,
                ex);

        return fallbackValue;
    }
}
```

`recoverable` must be an application-defined policy based on permitted error types or conditions. Do not set it to `ex -> true`, because that swallows every evaluation error.

If your Spring version provides suitable SpEL error codes, you can use those error codes for classification. However, verify the error codes and behavior of the version in use; do not rely on parsing message strings to decide whether an error is recoverable.

The fallback value must be compatible with `targetType`. If the target type is `Boolean`, the fallback must be `Boolean`; if the target type is `BigDecimal`, the fallback must be a business-meaningful `BigDecimal`. Avoid forcing an arbitrary default value through conversion to make an error disappear.

## 8. Do Not Use Permissive Fallbacks for Sensitive Decisions

A fallback must match the consequences of the decision:

| Context | Potentially Appropriate Fallback Example | What to Avoid |
|---|---|---|
| Display label | `"Guest"`, `"Unknown"` | Losing a property-name configuration error without logging it. |
| Optional description | Empty string or an agreed generic message. | Returning stale data without indicating that the data is stale. |
| Non-critical feature flag | Approved and logged default value. | Enabling sensitive features by default when the rule fails. |
| Authorization | Deny or halt the decision under a fail-closed policy. | Returning `true` when the expression fails. |
| Pricing/billing | Halt the transaction and require error handling. | Returning 0 or an unsubstantiated default price. |
| Limit/risk rules | Halt or apply a defined protective action. | Skipping the check because the expression could not evaluate. |

For security and financial operations, “fail closed” is usually safer than “fail open”. However, the exact behavior must be defined by business requirements; do not arbitrarily choose one default for every system.

## 9. Property Placeholders and the Elvis Operator Are Not the Same

In Spring configuration, you may encounter two mechanisms:

- Property placeholders retrieve values from external configuration and can declare a default value when a property does not exist.
- The SpEL Elvis operator selects a replacement value when the expression result is `null` or an empty `String`.

Property placeholder example in an annotation:

```java
@Value("${app.display-name:Guest}")
private String displayName;
```

SpEL Elvis example in an annotation:

```java
@Value("#{systemProperties['user.region'] ?: 'unknown'}")
private String region;
```

Placeholders do not catch SpEL evaluation errors. Nor does Elvis handle bean resolution or property path errors. Use the right mechanism for the corresponding value source.

If a configuration property is required, do not set an arbitrary default. Let the application fail fast when configuration is missing so deployment errors are caught early.

## 10. Classify and Log Errors Helpfully

When an expression fails, logs need enough information to find the rule and error phase without exposing sensitive data.

Typically useful information:

- Rule ID or configuration name.
- Rule version.
- Parse or evaluation phase.
- Exception type and error code if available.
- Correlation ID or request ID.
- Evaluation timestamp and operation type.
- Whether a fallback was used and under which policy.

Example:

```java
try {
    return expression.getValue(context, root, Boolean.class);
}
catch (EvaluationException ex) {
    log.error(
            "SpEL evaluation failed: ruleId={}, errorType={}",
            ruleId,
            ex.getClass().getSimpleName(),
            ex);

    throw new RuleEvaluationException(
            ruleId,
            "Rule evaluation failed",
            ex);
}
```

Do not log passwords, tokens, personal data, the entire root object, or sensitive rejected values. If an expression contains secrets or tenant info, use a controlled ID/version instead of logging the verbatim source.

If a valid fallback occurs, log explicitly that the fallback was applied. Maintain separate metrics for fallback count, parse failures, and evaluation failures to detect broken configurations or anomalous data.

## 11. Do Not Blindly Retry Expressions

Retrying makes sense for transient errors of an external service if the operation can be retried safely. However, many SpEL errors are deterministic:

- Invalid syntax will not fix itself on retry.
- A non-existent property will continue not to exist.
- Incompatible data types usually remain incompatible.
- An unregistered converter will not appear on its own.

If an expression invokes a method with side effects, retrying can execute the action twice. Retry only when you know the error is transient, the method is idempotent, and retry count/time are bounded.

For parse errors, fix the source/configuration and re-parse. For data-caused evaluation errors, validate or fix the data. For external service errors, use service-layer resilience mechanisms instead of blindly retrying the entire expression.

## 12. Testing Fallbacks and Error Paths

Tests must prove both behaviors: the fallback only runs in permitted situations, while unrecoverable errors propagate upward.

Cases to include:

1. `null` property: Elvis returns the default.
2. Empty `String`: Elvis returns the default.
3. Property has a value: the original result is preserved.
4. `null` intermediate object: safe navigation returns `null` so Elvis picks the default.
5. Non-existent property: evaluation fails, not treated as `null`.
6. Syntactically invalid expression: parse fails before evaluation.
7. Method throws an exception: the exception is logged/propagated per policy.
8. Conversion fails: do not replace with a default unless a clear policy exists.
9. Fallback matches the target type and is business-meaningful.
10. Logs/metrics record when a fallback is used.

JUnit example for Elvis:

```java
@Test
void usesDefaultForNullProperty() {
    StandardEvaluationContext context =
            new StandardEvaluationContext(customerWithNullNickname);

    String value = parser.parseExpression(
            "nickname ?: 'Guest'")
            .getValue(context, String.class);

    assertEquals("Guest", value);
}
```

Example verifying a missing property is not masked by Elvis:

```java
@Test
void missingPropertyStillFails() {
    StandardEvaluationContext context =
            new StandardEvaluationContext(customer);

    Expression expression = parser.parseExpression(
            "missingProperty ?: 'Guest'");

    assertThrows(
            EvaluationException.class,
            () -> expression.getValue(context, String.class));
}
```

Specific class and exception names in tests can be adjusted to your project's Spring API/version. What must be guaranteed is that a property error does not turn into a fallback simply because the expression has an Elvis operator.

## 13. Common Errors and How to Fix Them

| Symptom | Cause | How to Fix |
|---|---|---|
| Every error returns a default | Catch is too broad and does not classify exceptions. | Fallback only for policy-permitted cases; preserve causes for remaining errors. |
| Elvis does not handle misspelled properties | Elvis only handles null/empty string values, not evaluation exceptions. | Fix the property path or validate expressions when loading configuration. |
| Safe navigation still throws an exception | The invoked getter/method itself threw an exception. | Diagnose the method; safe navigation only handles a null receiver. |
| Fallback causes wrong business decisions | Default does not fit the type or decision consequences. | Define fallbacks per rule and use fail-closed when necessary. |
| Configuration error only appears during request execution | Expression was not parsed at startup/config update. | Parse and validate configuration before putting it into use. |
| Logs cannot locate the failing rule | Only a generic message logged or rule ID/version missing. | Log rule ID, version, phase, exception type, and correlation ID. |
| Retry repeats an action | Method inside the expression has side effects. | Do not retry blindly; retry only bounded idempotent operations. |
| Fallback returns the wrong type | Default value is incompatible with target type. | Use an explicitly typed fallback and test against target type. |
| Data errors masked as valid results | Using fallbacks for unexpected conversion/property/method failures. | Separate data errors, configuration errors, and optional cases per policy. |

## 14. Workflow for Designing SpEL Fallbacks

1. Determine whether the expression is fixed configuration or user/admin-provided.
2. Parse the expression early and reject syntactically invalid configurations.
3. Identify which properties are allowed to be `null` or empty per data contract.
4. Use safe navigation and Elvis for intentional `null`/empty cases.
5. Do not expect Elvis or safe navigation to catch exceptions.
6. Specify an explicit target type when calling `getValue()`.
7. Wrap parse/evaluation errors with an exception carrying the rule ID and preserving the cause.
8. If fallback after evaluation errors is permitted, define a classifier/policy for specific recoverable errors.
9. Do not use permissive fallbacks for authorization, pricing, billing, or risk checks.
10. Do not retry methods with side effects without ensuring idempotency.
11. Log/emit metrics when fallbacks are used and protect sensitive data.
12. Test `null`, empty, missing property, invalid syntax, conversion failure, and method exception cases.

## 15. Key Takeaways

- Do not catch all exceptions and return a default; that masks configuration errors and programming bugs.
- Parse errors and evaluation errors occur in different phases and require separate diagnostics.
- Elvis `?:` picks a fallback when the left value is `null` or an empty `String`; it does not catch exceptions.
- Safe navigation `?.` handles a `null` receiver; it does not catch exceptions from getters or methods.
- Missing properties, wrong methods, conversion failures, and syntax errors must be handled by their root causes.
- Wrap exceptions to add rule ID/context while preserving the cause.
- Only fall back after `EvaluationException` when an explicit policy exists for that error type and the fallback has the right type/semantics.
- Security, pricing, and billing decisions typically require failing closed or halting the transaction.
- Parse expressions before putting them into use; log errors and fallback metrics in a controlled manner.
- Retries are suitable only for transient errors and idempotent operations.

## References

- [Spring Framework Reference — Elvis Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-elvis.html)
- [Spring Framework Reference — Safe Navigation Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html)
- [Spring Framework Reference — Evaluation and Exception Handling](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [ExpressionParser Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ExpressionParser.html)
- [EvaluationException Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationException.html)
- [ParseException Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ParseException.html)
