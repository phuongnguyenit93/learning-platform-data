# Error Messages That Do Not Expose Sensitive Data When Using SpEL

## Objectives

When Spring Expression Language (SpEL) parses or evaluates an expression, errors can arise from invalid syntax, missing properties, `null` values, failed type conversions, disallowed methods, or exceptions thrown by logic inside a method. Error details are very useful for developers, yet messages and cause chains sometimes contain the expression source, input values, class/bean names, resource paths, or business data.

Applications must separate information intended for callers from internal diagnostic information. External responses should use short messages, stable error codes, and a correlation ID if support is needed. Internal logs should record only necessary metadata, enforce access controls, and avoid logging raw expressions, secrets, tokens, personal data, or entire objects from the evaluation context.

## 1. Common Error Types When Evaluating SpEL

Distinguishing errors by phase helps handle them properly and avoid returning overly detailed technical information:

| Phase | Error Type | Example |
| --- | --- | --- |
| Parse | `ParseException` or `SpelParseException` | Missing brackets, invalid operator syntax, malformed literal. |
| Evaluation | `EvaluationException` or `SpelEvaluationException` | Non-existent property, null dereference, out-of-bounds index, method or type not found. |
| Conversion | Type conversion error during evaluation | Result or argument cannot be converted to expected type. |
| Method/function execution | Exception raised from an invoked Java method | Helper or bean throws an error while processing arguments. |
| Business validation | Expression runs successfully but data fails rules | Boolean result is false or value is outside permitted range. |

Parse errors and evaluation errors are not the same as a business result of `false`. An expression can validly evaluate to `false`; that differs from an expression failing to run.

## 2. Do Not Return Exception Messages Directly to Clients

Avoid putting the following values directly into HTTP responses, UI messages, or API error bodies:

- `exception.getMessage()` or full stack traces.
- The full expression source, especially if the expression was submitted by a user.
- Values of the root object, context variables, method arguments, or rejected values.
- Internal class, package, bean, or method names if they reveal application structure.
- SQL, internal URLs, file paths, hostnames, configuration, or connection details.
- Tokens, passwords, session identifiers, access keys, or personal data.

Exception messages can change across library versions and runtime content. Do not treat a framework message as a stable API or a sanitized message.

Instead, return messages mapped to application-defined error codes:

| Internal Error Code | Usable External Message |
| --- | --- |
| `RULE_INVALID` | The rule expression is invalid. |
| `RULE_EVALUATION_FAILED` | Unable to evaluate the rule at this time. |
| `RULE_RESULT_INVALID` | The rule did not return a valid result. |
| `INPUT_INVALID` | Input data is invalid. |
| `REQUEST_FAILED` | Unable to process the request. |

Only return field validation details if that content was designed for public display and contains no sensitive values.

## 3. Separate Parse Error, Evaluation Error, and Business Result

Handle parsing and evaluation at clear boundaries. The example below illustrates using custom error codes without returning exception messages:

```java
Expression expression;
try {
    expression = parser.parseExpression(ruleSource);
}
catch (ParseException ex) {
    logger.warn(
            "Rule parse failed: ruleId={}, correlationId={}",
            ruleId, correlationId);
    return RuleResult.error("RULE_INVALID");
}

try {
    Boolean result = expression.getValue(context, Boolean.class);
    if (result == null) {
        return RuleResult.error("RULE_RESULT_INVALID");
    }
    return RuleResult.success(Boolean.TRUE.equals(result));
}
catch (EvaluationException ex) {
    logger.error(
            "Rule evaluation failed: ruleId={}, correlationId={}",
            ruleId, correlationId);
    return RuleResult.error("RULE_EVALUATION_FAILED");
}
```

`RuleResult` is an application-defined result type to distinguish successful evaluation from errors. Do not turn every exception into `false` and continue as if the rule ran normally.

For authorization or action-permission decisions, evaluation errors must lead to a denial or safe error state per policy. Never permit an action merely because a rule could not be evaluated. At the same time, keep a distinct error code so operations can detect system errors instead of mistaking them for a valid `false` decision.

## 4. Log Useful Metadata, Not Input Data

Logs should help identify the rule and the failing request without storing sensitive content:

**Typically useful metadata:**

- ID of the application-managed rule or expression.
- Version of the rule or configuration.
- Correlation ID/request ID.
- Application-classified error type: parse, evaluation, conversion, or business validation.
- Handling component name and timestamp.
- Internal message/code if it can be logged without containing input data.

**Do not log by default:**

- Raw expressions or expressions concatenated from user data.
- The entire `EvaluationContext`, root object, or variable map.
- Method arguments and return values.
- Passwords, tokens, API keys, cookies, session IDs, or credentials.
- Full `FieldError.getRejectedValue()` from `DataBinder`.
- Exception messages/cause chains if they might contain input data or secrets.

Structured log example:

```java
logger.warn(
        "SpEL parse failed: ruleId={}, ruleVersion={}, correlationId={}, category={}",
        ruleId, ruleVersion, correlationId, "RULE_PARSE_FAILED");
```

Do not pass the exception as the final argument if the logger will record the full message and stack trace containing unsanitized data. When stack traces are needed for investigation, use an internal sink with restricted access, proper retention, and verified redaction mechanisms.

## 5. Be Careful with the Exception Cause Chain

It is not only the outermost exception that can contain sensitive data. A method invoked from SpEL can throw exceptions from an HTTP client, JDBC driver, ORM, parser, or other library. The cause chain may contain:

- Internal URLs, query parameters, or hostnames.
- SQL statements, table/column names, or bound data.
- File paths and directory names.
- Argument values or request contents.
- Authentication details added by libraries to diagnostics.

Therefore, do not assume replacing the outer message alone is sufficient. Decide clearly where stack traces may be stored, who can read the logs, and what data must be redacted before writing.

If a full stack trace is not needed to resolve an incident, log the exception category and correlation ID. If deep investigation is needed, write technical details to a protected internal system, avoiding putting them in responses or broadly accessible logs.

## 6. Do Not Echo User Expression Sources

If users can create or edit rules, the expression source may contain secrets or personal data. Do not put the verbatim source into validation errors, audit logs, analytics events, or UI notifications.

Instead of:

```java
logger.warn("Invalid expression: {}", ruleSource);
```

log the rule ID/version:

```java
logger.warn(
        "Invalid expression: ruleId={}, ruleVersion={}, correlationId={}",
        ruleId, ruleVersion, correlationId);
```

If you need to identify a specific version of a source, you can store a fingerprint/hash generated per application policy; do not use a hash as a substitute for access control, and do not treat a hash as absolute anonymization for low-entropy data domains.

Do not concatenate request data into the expression source. Use fixed expressions and pass data through variables or a root DTO:

```java
Expression expression = parser.parseExpression("customerCode == #inputCode");
StandardEvaluationContext context = new StandardEvaluationContext(customerView);
context.setVariable("inputCode", suppliedCode);
```

This separates data from SpEL syntax. If the expression source itself is untrusted, you must still restrict the features and access permissions of `EvaluationContext`; using variables does not automatically make a source safe.

## 7. Do Not Expose Data Through DataBinder and Validation Errors

In Spring MVC, binding or validation errors can contain `FieldError`, field names, rejected values, and conversion details. `rejectedValue` might be a password, token, or private data.

Do not serialize the entire `BindingResult` or `FieldError` directly into a response without controlling the contents. Select only permitted fields and error codes to display:

```java
for (FieldError error : bindingResult.getFieldErrors()) {
    String field = error.getField();
    String code = error.getCode();

    // Map field/code to an application-defined message.
    // Do not log or return error.getRejectedValue() by default.
}
```

For sensitive fields, return only a generic message such as “Invalid value”. Do not echo the submitted value even when it is rejected.

## 8. Use Safe API Error Responses

For APIs, return stable error codes and generic content. Applications using Spring Framework 6 or newer can use `ProblemDetail` to standardize responses:

```java
ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.BAD_REQUEST,
        "The supplied rule is invalid.");
problem.setProperty("code", "RULE_INVALID");
problem.setProperty("correlationId", correlationId);
return problem;
```

For internal errors when evaluating an application-configured rule, the response should usually be a generic processing error (e.g., HTTP 500) with a stable error code. Do not return HTTP 400 for every `EvaluationException`, because the cause may be a configuration error or a code/server bug rather than client data.

Only include a correlation ID in the response when the system supports safe lookup by that ID. The correlation ID must not contain personal data or secrets.

## 9. Do Not Swallow Errors and Do Not Use Dangerous Fallbacks

Avoid handling patterns like this:

```java
try {
    return expression.getValue(context, Boolean.class);
}
catch (Exception ex) {
    return true; // Unsafe for authorization decision rules.
}
```

Do not return `true`, `0`, an empty collection, or an arbitrary default object when an expression fails. Such fallbacks can cause technical errors to be interpreted as valid business results.

Instead:

- Use a result type with distinct `SUCCESS` or `ERROR` statuses.
- For authorization, apply fail-closed: do not permit the action if the rule cannot be evaluated.
- For financial calculations or critical data, halt the processing flow and require explicit error handling.
- Only use a default when that default is a defined business rule, not a way to hide exceptions.
- Do not catch overly broad `Exception` if you can classify `ParseException`, `EvaluationException`, and business errors separately.

## 10. Control Sensitive Data in the Context

Sensitive information exposure does not only come from the expression source. Root objects, variables, bean methods, and property accessors can all introduce sensitive data into evaluation.

Practices to apply:

- Create DTO/view objects containing only the properties the expression needs.
- Do not put passwords, credentials, access tokens, secret keys, or full entities into the root object.
- Register only necessary variables; avoid passing entire request/session/security contexts if not needed.
- Do not expose beans with methods that return secrets or dump full configurations.
- Avoid getters or methods that could build messages containing sensitive data upon failure.
- Restrict log read permissions and diagnostic retention times.

In particular, do not use `toString()` on the root object or arguments as log content. `toString()` may print sensitive fields or change across implementations.

## 11. Restrict Error Information by Environment

Information shown to end users and information intended for developers may differ, but both require clear policies:

| Channel | Should Contain | Should Not Contain |
| --- | --- | --- |
| UI/client response | Error code, standardized message, correlation ID if needed. | Stack trace, expression source, classpath, secrets, SQL, or file paths. |
| Application log | Rule ID/version, correlation ID, error category, component. | Raw input, entire context, credentials, or rejected values. |
| Restricted diagnostic store | Technical details needed for investigation, redacted and access-controlled. | Unnecessary secrets or data without a retention policy. |
| Metrics/tracing tags | Low-cardinality error category and operation name. | User input, raw expressions, tokens, or personal values as labels. |

Do not put full exception messages into tracing spans or metric tags. Observability systems are often accessed by many teams and have long retention periods.

## 12. Test to Ensure Error Messages Do Not Leak Data

Tests should verify both responses and logs, not just that exceptions are caught:

1. Create input containing a secret sentinel string, such as `SECRET_TEST_92A7`.
2. Make expression parsing or evaluation fail using that input.
3. Verify the response does not contain the sentinel, raw expression, stack trace, or rejected value.
4. Verify the default log only has rule ID, correlation ID, and error category.
5. Verify the cause chain is not written to public logs or broadly accessible sinks.
6. Verify evaluation errors are not converted into allow/`true` results.
7. Verify a business `false` result is distinguished from an inability to evaluate.
8. Verify validation errors do not echo data from sensitive fields.

Conceptual assertion example:

```java
assertThat(responseBody).doesNotContain("SECRET_TEST_92A7");
assertThat(responseBody).doesNotContain("SpelEvaluationException");
assertThat(responseBody).doesNotContain("at org.springframework");
assertThat(result.status()).isEqualTo(RuleStatus.ERROR);
```

In real tests, inspect the logger using the project's test appender or log capture. Use fake sentinel data, not production secrets.

## 13. Common Errors and How to Handle Them

| Symptom | Cause to Check | How to Fix |
| --- | --- | --- |
| API returns `SpelEvaluationException` details | Exception message was serialized directly. | Map to error codes and standardized messages; keep diagnostics in internal channels. |
| Logs contain raw expressions | Logger records expression source for debugging convenience. | Log rule ID/version or policy-compliant fingerprint, not the source. |
| Stack trace leaks URL or SQL | Cause chain comes from HTTP/JDBC/ORM. | Do not write full exceptions to broad logs; use restricted sinks and redact. |
| Password appears in binding errors | `rejectedValue` is logged or serialized. | Use only field/error codes; do not echo rejected values of sensitive fields. |
| Evaluation error treated as false result | Exception is caught and replaced with a default Boolean. | Use a dedicated error status; fail-closed for permission decisions. |
| Server error returned as HTTP 400 | All SpEL errors treated as bad client input. | Distinguish client-supplied source errors, configuration errors, and internal errors; pick proper status codes. |
| Logs/metrics contain high-cardinality data | Using user input or expressions as tags. | Use only stable categories/operations; drop arbitrary data from labels. |
| Diagnostics too sparse to investigate | Only generic messages returned without saving internal metadata. | Log rule ID/version, correlation ID, and category in controlled logs. |

## Key Takeaways

- Parse errors, evaluation errors, and business results are three distinct states; do not collapse errors into `false`.
- Do not return `exception.getMessage()`, stack traces, expression sources, or cause chains to clients.
- Use stable error codes and standardized messages; include a correlation ID when lookup is needed.
- Log rule ID/version, correlation ID, and error category; avoid raw expressions, root objects, variables, arguments, and rejected values.
- Cause chains from HTTP, JDBC, ORM, or invoked methods may contain URLs, SQL, file paths, or input data.
- Do not log `FieldError.getRejectedValue()` or `toString()` of objects containing sensitive data.
- Use DTO/view objects and put only necessary data into `EvaluationContext`.
- Do not turn evaluation failures into `true`, `0`, or arbitrary defaults; use a dedicated `ERROR` status.
- For authorization, evaluation errors must fail-closed and be distinguished from valid deny decisions.
- Test responses and logs with fake sentinels to prove secrets are not echoed.

## References

- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework API — ParseException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ParseException.html)
- [Spring Framework API — EvaluationException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationException.html)
- [Spring Framework API — SpelParseException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelParseException.html)
- [Spring Framework API — SpelEvaluationException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelEvaluationException.html)
- [Spring Framework API — BindingResult](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework Reference — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)