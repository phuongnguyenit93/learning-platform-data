# Checking Expression Length, Syntax, and Resources in SpEL

## 1. Why Must Expressions Be Bounded?

Spring Expression Language (SpEL) can read properties, invoke methods, instantiate objects, access collections, perform arithmetic operations, and reference beans depending on the EvaluationContext. This flexibility is useful for configuration and business rules, yet an expression that is overly long, overly complex, or evaluated over a wide object graph can consume excessive CPU, memory, and processing time.

When expressions come from configuration or external sources, at least three aspects must be controlled:

1. **Length and structure:** limit input size and syntactic complexity before parsing.
2. **Evaluation resources:** limit operation counts, large numeric result sizes, and collection auto-growth capabilities.
3. **Access privileges:** limit the objects, properties, methods, functions, and beans an expression can reach.

A parser limit does not replace access control. A short expression can still invoke an expensive method or one with side effects; a syntactically valid expression can still be unsafe if evaluated against an overly privileged object.

## 2. Separating Parsing from Evaluation

SpEL has two main phases:

- `ExpressionParser.parseExpression(...)` parses the string and creates an Expression object.
- `Expression.getValue(...)` evaluates the expression against a root object and an EvaluationContext.

Example:

```java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("age >= 18");

boolean allowed = expression.getValue(
        customer, Boolean.class);
```

If syntax is wrong, the error occurs during the parse phase. If syntax is valid but a property does not exist, data types do not match, or a method cannot be called, the error occurs during the evaluation phase.

| Phase | API | Common Exception Type | Meaning |
|---|---|---|---|
| Parse | `parseExpression()` | `ParseException`, typically `SpelParseException` | String violates grammar or exceeds parse limits. |
| Evaluate | `getValue()` | `EvaluationException`, typically `SpelEvaluationException` | Unable to read property, invoke method, convert type, or execute operation. |

Successful parsing only proves the expression is syntactically valid and accepted by the parser. Parsing does not prove the expression can evaluate against real data, satisfies business rules, or is safe.

## 3. Limiting Expression Length

In current Spring Framework versions, SpEL expression length defaults to no more than **10,000 characters**. This limit helps prevent overly large input strings from inflating parsing and AST storage costs.

When creating a parser in code, configure a custom limit via `SpelParserConfiguration`:

```java
SpelParserConfiguration config =
        SpelParserConfiguration.builder()
                .maximumExpressionLength(2_000)
                .build();

ExpressionParser parser =
        new SpelExpressionParser(config);
```

The example above sets a 2,000-character limit for expressions processed by that parser. Choose a value based on the expression language the application genuinely permits; do not raise the limit just to accommodate an anomalous expression.

For expressions processed inside ApplicationContext, such as in XML bean definitions or `@Value`, you can configure the Spring property:

```properties
spring.context.expression.maxLength=2000
```

This property can be supplied via a JVM system property or the SpringProperties mechanism. For parsers created directly by the application, prefer configuring directly on the parser so the scope of impact is clear.

Input size should also be checked at the request boundary before invoking the parser. SpEL's limit is an additional layer of defense; the HTTP/API layer still needs to bound payloads and the number of expressions a single request can submit.

## 4. Limiting Operation Count During Evaluation

Starting in Spring Framework 6.2.19 and 7.0.8, SpEL limits the number of operations executed during a single expression evaluation. The current default value is **10,000 operations**. When the threshold is exceeded, evaluation halts and throws a SpEL exception.

Configure via the parser:

```java
SpelParserConfiguration config =
        SpelParserConfiguration.builder()
                .maximumOperations(500)
                .build();

ExpressionParser parser =
        new SpelExpressionParser(config);
```

The example limits each evaluation using this parser to 500 operations. Choose the threshold based on valid application expressions and measure with representative data.

If the parser cannot be configured directly, a Spring/JVM property can be set:

```properties
spring.expression.maxOperations=500
```

This limit is useful for expressions with many nodes, arithmetic operations, or iterative operations. However, it is not a general-purpose timeout for an entire Java program. A custom method can execute a long loop, query a database, access the network, or wait on a lock inside a single call; SpEL's operation counter does not capture all internal costs of that method.

Therefore, avoid exposing expensive methods to expressions, set timeouts on external APIs if needed, and limit concurrency at the execution layer.

## 5. Limiting BigInteger and BigDecimal Exponentiation Results

Exponentiation with `BigInteger` or `BigDecimal` can produce huge results, consuming significant CPU and memory. Spring Framework 7.0.9 and later limits the result size of power operations in SpEL to a default of **1,000,000 bits**.

It can be configured via the parser:

```java
SpelParserConfiguration config =
        SpelParserConfiguration.builder()
                .maximumBigPowerBits(8_192)
                .build();

ExpressionParser parser =
        new SpelExpressionParser(config);
```

The example sets a result limit of 8,192 bits. If a calculation could exceed the limit, SpEL stops with an evaluation error instead of allocating an unbounded result.

It can be configured via a Spring/JVM property:

```properties
spring.expression.maxBigPowerBits=8192
```

Do not set `Integer.MAX_VALUE` just to disable the limit in environments that accept expressions from untrusted sources. Allowing huge numeric results can cause sudden spikes in time and memory consumption.

This limit applies only to the result of power operations with BigInteger/BigDecimal. It does not bound all arithmetic operations, all large strings, or all methods invoked from an expression.

## 6. Limiting Collection Auto-Growth and Null References

SpEL can be configured to automatically instantiate objects when intermediate properties are null or automatically grow collections when an index exceeds the current size. This feature is useful for data binding, but it can mutate objects and allocate additional memory.

Two related options:

- `autoGrowNullReferences()`: enables auto-instantiation of null references in property paths.
- `autoGrowCollections()`: enables auto-growing collections and arrays during index access.

In the current builder, both features are disabled by default. If collection auto-growth is genuinely needed, set a size limit:

```java
SpelParserConfiguration config =
        SpelParserConfiguration.builder()
                .autoGrowCollections()
                .maximumAutoGrowSize(64)
                .build();

ExpressionParser parser =
        new SpelExpressionParser(config);
```

Collections or arrays are then allowed to auto-grow, but not beyond 64 elements. `maximumAutoGrowSize` only takes effect when auto-grow is enabled.

The current builder defaults the auto-grow limit to 256 elements. Note that older `SpelParserConfiguration` constructors may default to `Integer.MAX_VALUE` for backward compatibility. Prefer the builder and set explicit limits if the application allows expressions to write data or auto-grow collections.

If expressions only need to read data, keep auto-grow disabled and use an appropriate read-only context.

## 7. Additional Protections for Strings, Regexes, and Arrays

Beyond the main configuration limits, SpEL has internal checks for certain operations that can produce large or expensive data, including:

- Size of strings created via repetition.
- Size of strings after concatenation.
- Length of regexes used with the `matches` operator.
- Number of elements declared when creating an array.
- Certain regexes identified as difficult to evaluate efficiently.

Threshold violations can produce messages such as `MAX_REPEATED_TEXT_SIZE_EXCEEDED`, `MAX_CONCATENATED_STRING_LENGTH_EXCEEDED`, `MAX_REGEX_LENGTH_EXCEEDED`, `MAX_ARRAY_ELEMENTS_THRESHOLD_EXCEEDED`, or `FLAWED_PATTERN`.

Exact thresholds and behavior depend on the Spring version. Do not rely on these internal checks as a general execution-time limit. In particular, regexes can incur heavy cost when applied to long strings; do not accept arbitrary regexes from users without a policy controlling patterns and input data.

If the business logic needs regex matching, prefer application-defined patterns or an allowlist of vetted patterns. Bound both the length of strings being matched and the execution frequency.

## 8. Configuring Multiple Limits Together

Multiple core limits can be configured on one parser:

```java
SpelParserConfiguration config =
        SpelParserConfiguration.builder()
                .maximumExpressionLength(2_000)
                .maximumOperations(500)
                .maximumBigPowerBits(8_192)
                .maximumAutoGrowSize(64)
                .build();

ExpressionParser parser =
        new SpelExpressionParser(config);
```

In this configuration:

- Expressions are at most 2,000 characters long.
- Each evaluation has at most 500 operations.
- BigInteger/BigDecimal power results do not exceed 8,192 bits.
- If collection auto-grow is later enabled, maximum auto-grow size is 64 elements.
- Auto-grow remains disabled because neither `autoGrowCollections()` nor `autoGrowNullReferences()` was called.

This is an illustrative limit example. Production values should be based on valid expressions, real data, acceptable latency, and deployment resources. Limits set too low may reject valid expressions; limits set too high reduce protection effectiveness.

## 9. Parsing to Validate Syntax Before Saving Expressions

If the application lets administrators configure expressions, you can parse immediately upon receiving configuration to catch syntax errors before the expression is used in real requests.

Example:

```java
public Expression parseConfiguredRule(
        String source,
        ExpressionParser parser) {

    if (source == null || source.isBlank()) {
        throw new IllegalArgumentException(
                "Expression must not be empty");
    }

    return parser.parseExpression(source);
}
```

Callers should catch `ParseException` and report a configuration error with a specific position or message. There is no need to call `getValue()` just to check syntax, because evaluation can invoke getters/methods, mutate state, or access the system.

If you need to test execution on a sample model, use isolated test data and an EvaluationContext with minimal privileges. Do not test-run arbitrary expressions on production objects just to see whether they work.

Parse an expression once and reuse it when the same expression is evaluated repeatedly under the same security scope and equivalent configuration. Do not share a parsed Expression across contexts with different privilege levels; the AST may cache accessors or executors from a previous evaluation.

## 10. Restricting Syntax with Grammars and Allowlists

Limiting length does not mean syntax is restricted. A short expression can still use constructors, type references, bean references, method invocation, or assignment if the EvaluationContext permits them.

If the business logic only needs conditions such as:

```text
age >= 18 and country == 'VN'
```

explicitly define the accepted syntax set, for example:

- Allow only a known list of properties.
- Allow only supported comparison and logical operators.
- Allow only literals of specified types.
- Disallow constructors, type references, bean references, assignments, or method calls if unneeded.
- Bound condition count, operator count, and expression depth at the application layer.

Do not use a simple regex to try filtering out all dangerous SpEL syntax. SpEL grammar has many forms of nesting, escaping, literals, and operators; string-based blacklists easily miss cases. If user-defined expressions are required, consider a small DSL with its own grammar and translate that DSL into controlled expressions.

## 11. EvaluationContext Is a Critical Security Boundary

Spring distinguishes two main context types:

| Context | Characteristics |
|---|---|
| `StandardEvaluationContext` | Provides full SpEL features, including access to methods, constructors, types, beans, and configurable strategies. |
| `SimpleEvaluationContext` | Provides only a subset of features; excludes type references, constructors, and bean references, and requires explicit selection of property/method privileges. |

Do not use `StandardEvaluationContext` to evaluate expressions from untrusted sources. Spring documentation warns that evaluating untrusted SpEL is inherently dangerous because expressions can execute behavior inside the application.

`SimpleEvaluationContext` only restricts features on a best-effort basis and is not an absolute security sandbox. Expressions can still invoke properties, methods, or functions exposed by the root object, accessors, resolvers, variables, or registered functions.

Even property getters can have side effects. A zero-argument value-returning method can look like a getter while actually deleting files, polling and removing queue elements, or incrementing counters. Read-only data binding only prevents property writes; it does not prove reading properties is harmless.

When evaluating expressions from not-fully-trusted sources:

- Use dedicated, small, immutable DTOs instead of entities or infrastructure objects.
- Expose only truly necessary properties.
- Audit all getters and accessor-shaped methods that may be invoked.
- Do not register beans, functions, or MethodResolvers with broad privileges.
- Bound the entire object graph reachable by the expression, including nested objects and collection elements.
- Parse into separate Expressions per security scope; do not reuse an Expression run under a privileged context in a narrower context.

## 12. Time and Resource Limits Outside SpEL

Limits in SpelParserConfiguration do not create a hard timeout for all activity. A single method call can run a database query, make an HTTP call, wait on a lock, or run a long loop in Java code. Those costs are not necessarily reflected fully by SpEL's operation counter.

The application needs additional safeguards in surrounding layers:

- Limit request size and number of expressions per request.
- Limit evaluation count per user/tenant within a time window.
- Use an executor with a bounded queue and bounded concurrency if expressions run in separate tasks.
- Set timeouts on external APIs that allowed methods may call.
- Avoid letting expressions invoke methods that perform I/O or operations with side effects.
- Monitor parse time, evaluation time, limit-rejection counts, and error rates.
- If truly untrusted logic must run, consider not using SpEL inside the application process; use a safe DSL or execute in an appropriate isolated environment.

Do not treat running evaluation inside a `Future` with a timeout as a reliable way to stop a Java method that does not cooperate with interruption. Design exposed methods to have their own timeouts and resource bounds.

## 13. Classifying Parse Errors and Limit-Exceeded Errors

Common errors:

| Symptom | Phase | Handling Direction |
|---|---|---|
| Missing parentheses, quotes, or misplaced operator | Parse | Fix grammar and show error location. |
| Expression exceeds `maximumExpressionLength` | Parse | Reduce length or adjust limit under control. |
| Expression structure is too complex | Parse | Simplify grammar/expression; check nesting limits for your Spring version. |
| Property does not exist on root object | Evaluation | Check model, property path, and accessor. |
| Method not found or argument mismatch | Evaluation | Check method resolver, types, and method signature. |
| Evaluation exceeds `maximumOperations` | Evaluation | Reduce operations or adjust budget after measuring valid expressions. |
| Power result exceeds `maximumBigPowerBits` | Evaluation | Bound inputs/exponents or perform controlled calculation in Java. |
| Auto-grow exceeds limit | Evaluation | Reduce index, disable auto-grow, or set an appropriate `maximumAutoGrowSize`. |
| Regex or generated string exceeds internal threshold | Parse/Evaluation depending on operation | Reduce pattern/input and inspect specific error code. |
| Evaluation runs long despite staying under budget | Inside method or external system | Inspect exposed methods, I/O, locks, and service-layer timeouts. |

Errors can be caught via the general API:

```java
try {
    Expression expression = parser.parseExpression(source);
    Object result = expression.getValue(context, rootObject);
}
catch (ParseException ex) {
    // Invalid syntax or rejected by the parser.
}
catch (EvaluationException ex) {
    // Expression has valid syntax but failed to evaluate.
}
```

In production systems, map exceptions to appropriate business error codes and do not return stack traces or internal details to the expression submitter.

## 14. Expression Intake and Evaluation Workflow

1. Identify whether the expression source is a trusted developer/admin or an external user/system.
2. If the source is untrusted, prefer a DSL or structured selection instead of accepting arbitrary SpEL.
3. Limit request size and expression length before parsing.
4. Use `SpelParserConfiguration` with an appropriate `maximumExpressionLength`.
5. Set `maximumOperations` and `maximumBigPowerBits` according to the application's resource budget.
6. Keep auto-grow disabled; if enabling is required, set a small, explicit `maximumAutoGrowSize`.
7. Parse expressions before saving configuration to catch grammar errors.
8. Use a least-privilege EvaluationContext and a dedicated root DTO.
9. Do not expose methods with side effects, I/O, or unbounded cost.
10. Evaluate with service-layer timeout/concurrency controls if needed.
11. Separate `ParseException` and `EvaluationException`; log error codes, expression IDs, and processing time instead of recording sensitive data.
12. Monitor hit limits and tune based on measured valid workloads.

## 15. Summary

- SpEL separates parsing and evaluation; successful parsing does not mean an expression is business-valid or safe.
- Current Spring Framework defaults expression length to 10,000 characters.
- Starting in Spring 6.2.19/7.0.8, evaluation has a default limit of 10,000 operations.
- Starting in Spring 7.0.9, BigInteger/BigDecimal power results default to a 1,000,000-bit limit.
- The current builder disables auto-grow by default and caps collection auto-grow at 256 elements if enabled.
- `maximumExpressionLength`, `maximumOperations`, `maximumBigPowerBits`, and `maximumAutoGrowSize` can be configured on `SpelParserConfiguration`.
- Spring includes internal checks for regexes, repeated text, concatenated strings, and array sizes; they do not replace application budgets.
- Operation budgets do not reliably bound time spent inside custom methods or I/O.
- `StandardEvaluationContext` is not for untrusted expressions; `SimpleEvaluationContext` is also not an absolute security sandbox.
- Use dedicated, immutable root objects, restrict accessors, and do not reuse parsed Expressions across contexts with different privileges.
- For user-defined expressions, prefer DSLs/allowlists rather than trying to filter SpEL with regexes or blacklists.

## References

- [Spring Framework Reference — Evaluation, Parser Configuration, and Security Considerations](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [SpelParserConfiguration.Builder Javadoc — Spring Framework 7.0.10](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelParserConfiguration.Builder.html)
- [SpelParserConfiguration Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelParserConfiguration.html)
- [SpelMessage Source — Resource and Pattern Limit Errors](https://github.com/spring-projects/spring-framework/blob/main/spring-expression/src/main/java/org/springframework/expression/spel/SpelMessage.java)
- [SimpleEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
