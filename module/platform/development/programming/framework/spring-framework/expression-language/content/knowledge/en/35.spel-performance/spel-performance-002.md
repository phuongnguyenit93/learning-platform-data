# Reusing a Parsed Expression When Expressions Repeat

## 1. Why Parse Once and Evaluate Many Times?

SpEL separates syntax parsing from expression evaluation:

- `ExpressionParser.parseExpression(source)` parses the string and creates an `Expression` object.
- `Expression.getValue(...)` evaluates the parsed expression against a root object and EvaluationContext.

An expression can be evaluated multiple times, on the same or on different root objects. Therefore, if the same rule is used across multiple requests or multiple records, parse it once and reuse the Expression object.

Example of what not to do inside a loop:

```java
for (Customer customer : customers) {
    Expression expression =
            parser.parseExpression("age >= 18");

    Boolean eligible =
            expression.getValue(customer, Boolean.class);
}
```

Each iteration re-parses the same string and creates a new AST. A better approach:

```java
Expression expression =
        parser.parseExpression("age >= 18");

for (Customer customer : customers) {
    Boolean eligible =
            expression.getValue(customer, Boolean.class);
}
```

In the second example, the parser only creates the Expression once; each call to `getValue()` still evaluates against the current Customer data.

## 2. Roles of ExpressionParser and Expression

The two abstractions have different responsibilities:

| Component | Responsibility | Usage Lifecycle |
|---|---|---|
| `ExpressionParser` | Parses a SpEL string and returns an Expression. | Can be reused to parse multiple sources. |
| `Expression` | Represents a parsed expression and performs evaluation. | Designed to be parsed once and evaluated repeatedly. |
| `EvaluationContext` | Provides the root object, variables, property/method/type resolvers, and other strategies. | Can be created once and reused across multiple evaluations if configuration is suitable. |

`SpelExpressionParser` is reusable and thread-safe. A shared parser can be created in a bean or service:

```java
@Component
public class RuleEvaluator {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    public Expression parse(String source) {
        return parser.parseExpression(source);
    }
}
```

Thread safety of the parser does not mean every object passed into EvaluationContext is also thread-safe. The root object, variables, custom PropertyAccessors, MethodResolvers, and services invoked from the expression must still follow the application's concurrency rules.

## 3. Example: Parse Once, Evaluate on Multiple Root Objects

An Expression can be evaluated on different root objects:

```java
ExpressionParser parser = new SpelExpressionParser();

Expression eligibilityRule =
        parser.parseExpression("age >= #minimumAge and active");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("minimumAge", 18);

Customer first = new Customer("Ada", 20, true);
Customer second = new Customer("Grace", 16, true);
Customer third = new Customer("Linus", 25, false);

Boolean firstResult =
        eligibilityRule.getValue(context, first, Boolean.class);

Boolean secondResult =
        eligibilityRule.getValue(context, second, Boolean.class);

Boolean thirdResult =
        eligibilityRule.getValue(context, third, Boolean.class);

// true, false, false
```

The Expression retains its source and AST. On each call to `getValue(context, root, Boolean.class)`, SpEL evaluates against the root object passed for that call.

The `#minimumAge` variable is retrieved from EvaluationContext. If the threshold changes per request, you can create a separate EvaluationContext and set the corresponding variable, provided the contexts are of the same type and have equivalent security configuration.

## 4. Reusing an Expression Does Not Mean Results Are Cached

Three types of data should be distinguished:

- **Expression cache:** holds parsed Expression objects to avoid re-parsing the source.
- **Evaluation metadata cache:** some AST nodes may cache an accessor or executor found during a previous evaluation.
- **Result cache:** holds evaluation results to return without running the expression again.

SpEL supports the first two at appropriate levels, but reusing an Expression does not mean results are cached.

Example:

```java
Expression expression =
        parser.parseExpression("balance >= #minimum");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("minimum", new BigDecimal("100"));

Boolean first = expression.getValue(
        context, account, Boolean.class);

// Account changes balance.
account.setBalance(new BigDecimal("50"));

Boolean second = expression.getValue(
        context, account, Boolean.class);
```

The second evaluation reads the current state of the object and may return a different result from the first. If the application wants to cache results, that is a separate policy at the application layer, requiring definition of keys, expiration, invalidation, and the impact of changing data.

## 5. AST May Cache Accessors and Executors

To avoid resolving every strategy on each evaluation, nodes in the Expression AST may cache components that have already succeeded, for example:

- `PropertyAccessor`: property access.
- `IndexAccessor`: element access by index/key.
- `MethodExecutor`: executing method invocation.
- `ConstructorExecutor`: executing constructor invocation.

When the expression is re-evaluated, SpEL can use the cached metadata if that strategy is still suitable for the current EvaluationContext. As a result, subsequent evaluations can reduce accessor/resolver resolution work.

For example, with the expression:

```text
customer.address.city
```

After the first evaluation, SpEL can remember the appropriate accessor for reading the corresponding properties. Subsequent calls on compatible objects can reuse that access path.

This is an internal cache serving evaluation. The application does not need to manually manage or modify accessor caches in the AST. Note that this caching has implications for how an Expression is reused across different EvaluationContexts.

## 6. Conditions for Reusing Across EvaluationContexts

Spring supports reusing an Expression across:

- Different root objects.
- Different EvaluationContexts that are of the same type and have equivalent configuration.
- For example: multiple StandardEvaluationContexts that register the same types of custom PropertyAccessor and MethodResolver.

If contexts have configurations that differ in security implications, a single Expression instance must not be shared. An Expression may have cached an accessor/executor from a previous evaluation; that metadata may be reused in a subsequent evaluation.

In particular, do not evaluate the same Expression first with a `StandardEvaluationContext` and then reuse it with a `SimpleEvaluationContext`. The first context may allow more capabilities than the second; caching from the broader-permission evaluation can defeat the restrictions the application expects in the subsequent evaluation.

If the same source needs to run under two security profiles, parse it into two separate Expressions:

```java
ExpressionParser parser = new SpelExpressionParser();

String source = "customer.name";

Expression trustedExpression =
        parser.parseExpression(source);

Expression restrictedExpression =
        parser.parseExpression(source);

StandardEvaluationContext trustedContext =
        new StandardEvaluationContext();

SimpleEvaluationContext restrictedContext =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

// Only use trustedExpression with a trusted context.
// Only use restrictedExpression with a restricted context.
```

Do not reuse an Expression instance between two groups of contexts with different permissions, regardless of which EvaluationContext implementations they are.

## 7. Do Not Arbitrarily Modify Resolvers/Accessors After Using an Expression

Contexts of the same type with equivalent configuration can share an Expression. However, changing the list of PropertyAccessors, IndexAccessors, MethodResolvers, ConstructorResolvers, or TypeLocators between evaluations is something that should not be done in normal flow.

Configure EvaluationContext once before using it:

```java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.addPropertyAccessor(customPropertyAccessor);
context.addMethodResolver(customMethodResolver);
context.setTypeConverter(customTypeConverter);

// After configuration is complete, use the context under a stable policy.
```

If a group of rules needs a different set of accessors/resolvers, create a separate context and Expression for that group. This clarifies access boundaries and prevents a cached expression from being used across non-equivalent policies.

## 8. Building an Expression Cache by Rule

For rules with fixed configuration, they can be parsed when the application starts up and kept in a registry:

```java
@Component
public class RuleRegistry {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    private final Map<String, Expression> expressions;

    public RuleRegistry() {
        Map<String, Expression> rules = new HashMap<>();

        rules.put(
                "adult-customer",
                parser.parseExpression("age >= 18"));

        rules.put(
                "active-customer",
                parser.parseExpression("active == true"));

        this.expressions = Map.copyOf(rules);
    }

    public Expression get(String ruleId) {
        Expression expression = expressions.get(ruleId);

        if (expression == null) {
            throw new IllegalArgumentException(
                    "Unknown rule: " + ruleId);
        }

        return expression;
    }
}
```

The registry above only illustrates a fixed set of rules. In a real application, you should keep the rule's version and security profile alongside the corresponding Expression.

Parsing early has an extra benefit: syntax errors are caught when loading configuration instead of appearing unexpectedly on the first request. If a rule fails to parse, the application can reject the new configuration version and keep the currently active version.

## 9. Bounded Dynamic Expression Caching

If administrators can create or update rules while the application is running, the number of sources can change. An unbounded cache risks growing memory proportionally to the number of distinct expressions.

When dynamic caching is needed:

- Use a cache with a bounded entry count or memory limit.
- Use rule ID and version to identify the expression version.
- Include parser configuration and security profile in the cache separation policy.
- Remove old entries when a rule is replaced or revoked.
- Do not cache arbitrary sources from end users without size and count limits.
- Do not overwrite an Expression from one security profile with an Expression from another profile.

Logical key example:

```java
record ExpressionCacheKey(
        String ruleId,
        long ruleVersion,
        String securityProfile) {
}
```

A real cache also needs to ensure the source is tied to the right version of the rule. When the source changes, increment the version or create a new key to avoid reusing the AST of old content.

Do not use a source with concatenated request data as a key if the data can be passed via variables. That approach creates many nearly identical expressions, bloats the cache, and increases parsing cost.

## 10. Passing Data via Variables Instead of Creating New Sources

A common mistake is concatenating input data directly into the expression string:

```java
String source =
        "age >= " + request.getMinimumAge();

Expression expression =
        parser.parseExpression(source);
```

Each minimumAge value creates a different source and can lead to a new parse/cache entry. This approach also mixes input data with expression syntax.

Keep the source stable and pass data via variables:

```java
Expression expression =
        parser.parseExpression("age >= #minimumAge");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable(
        "minimumAge",
        request.getMinimumAge());

Boolean result = expression.getValue(
        context, customer, Boolean.class);
```

This allows reusing the same Expression for many input values while separating data from SpEL syntax. You still must validate the variable's type and range according to business rules.

## 11. Separating Context per Request When Data Changes

Expressions can be reused, but EvaluationContext can contain variables, root objects, or request-dependent data. Do not place sensitive data or per-request changing variables in a shared context and update it concurrently from multiple threads.

Example creating a separate context for each evaluation:

```java
private final Expression eligibility =
        parser.parseExpression("age >= #minimumAge");

public boolean isEligible(
        Customer customer,
        int minimumAge) {

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("minimumAge", minimumAge);

    Boolean result = eligibility.getValue(
            context, customer, Boolean.class);

    return Boolean.TRUE.equals(result);
}
```

The Expression is reused; the context and variable are created per call. If a context is reused within a single synchronous flow and configuration does not change, that can also be suitable. However, with concurrent requests, a shared mutable context can mix up variables or root objects between requests.

Custom PropertyAccessors, MethodResolvers, and exposed objects also need thread-safe behavior when used concurrently.

## 12. Do Not Share Parsed Expressions Across Security Profiles

This is a particularly important rule when caching expressions.

Unsafe example:

```java
Expression shared =
        parser.parseExpression("customer.name");

Object trustedValue =
        shared.getValue(standardEvaluationContext, trustedRoot);

// Do not reuse shared with a restricted context:
Object restrictedValue =
        shared.getValue(simpleEvaluationContext, untrustedRoot);
```

Spring does not support this usage because the AST may cache accessors/executors from the first evaluation. A less restrictive context may have exposed access capabilities that the subsequent context does not allow.

The right way is to create a separate expression for each security profile:

```java
Expression trusted =
        parser.parseExpression("customer.name");

Expression restricted =
        parser.parseExpression("customer.name");
```

Then each instance is only evaluated within its corresponding context group. If rules have multiple tenants or multiple permission levels, classify them by actual policy and create separate caches when security implications differ.

## 13. Parsing and Evaluation Fail at Different Times

Parsing once shifts syntax errors to the rule registration phase:

```java
Expression expression;

try {
    expression = parser.parseExpression(source);
}
catch (ParseException ex) {
    throw new IllegalArgumentException(
            "Invalid rule syntax: " + ruleId,
            ex);
}
```

Evaluation can still fail on real data:

```java
try {
    Boolean result = expression.getValue(
            context, rootObject, Boolean.class);
}
catch (EvaluationException ex) {
    // Record rule ID and cause.
    throw new RuleEvaluationException(ruleId, ex);
}
```

Do not cache an error result as if the expression were valid. If the source fails to parse, do not create a successful Expression cache entry; return a clear configuration error. If evaluation fails due to a root object, that does not necessarily mean the expression needs to be re-parsed.

## 14. Measuring the Benefit of Reusing Expressions

To measure accurately, separate parsing cost and evaluation cost:

| Measurement | Description |
|---|---|
| Parse | Time to create an Expression from source. |
| Evaluate after parse | Time to evaluate an existing Expression. |
| Parse every time | Simulates repeatedly creating parser/expression on a hot path. |
| Reuse | Parse once then evaluate against multiple root objects. |
| Cache hit/miss | Cost of cache lookup and parsing on cache miss. |

Benchmarks should:

- Use the same expression and same data for both approaches.
- Warm up the JVM before measuring.
- Run enough iterations and measurement rounds.
- Exclude Spring context startup time from evaluation time.
- Measure interpreted and compiled cases separately if the parser enables the compiler.
- Use JMH or an appropriate benchmarking tool when reliable figures are needed.
- Track both allocation and GC if the expression is called at high frequency.

Do not assume that parsing once will make overall evaluation faster by a fixed ratio. The benefit depends on expression complexity, call count, data types, and accessors/resolvers.

## 15. Common Mistakes and How to Handle Them

| Symptom | Cause | Remedy |
|---|---|---|
| High CPU in a loop | Calling parseExpression for the same source in each iteration. | Parse once and reuse the Expression. |
| Memory grows with request count | Unbounded dynamic expression cache or creating different sources per request. | Use a bounded cache and pass data via variables. |
| Updated rule still runs old logic | Cache key lacks version or cache is not invalidated when source changes. | Include rule version in key and remove old entry. |
| Expression run with broad permissions still works in restricted context | Same Expression instance reused across contexts with different security implications. | Parse separate Expressions for each security profile. |
| Context receives wrong variable from another request | Mutable EvaluationContext shared concurrently. | Create a context per request or isolate state. |
| Parser created continuously | Not reusing SpelExpressionParser. | Use a singleton parser; parser instances are reusable and thread-safe. |
| Assuming Expression cache always caches results | Confusing AST/accessor cache with result cache. | Understand each getValue still evaluates on the current root/context. |
| Changing resolvers after expression has run causes unpredictable behavior | Context changes configuration between evaluations. | Configure context stably before use. |
| Parse error only appears on first request | Rule not parsed at registration/configuration time. | Parse early and reject invalid syntax. |
| Benchmark shows no benefit | Low call workload, simple expression, or wrong phase measured. | Separate parse/evaluate, warm up, and measure realistic workload. |

## 16. Parse-Once/Evaluate-Many Implementation Workflow

1. Identify which expressions are used repeatedly and have a stable source.
2. Create a shared SpelExpressionParser with an appropriate parser configuration.
3. Parse the source once at initialization or when registering/versioning the rule.
4. Handle ParseException right at rule load time.
5. Store the Expression in a registry/cache with appropriate bounds.
6. Associate cache entries with rule ID, version, parser configuration, and security profile.
7. When evaluating, pass the appropriate root object and EvaluationContext for that call.
8. Reuse the Expression across different root objects or contexts of the same type and equivalent configuration.
9. Do not reuse a single Expression across contexts with different security implications.
10. Create a separate context when variables/root objects depend on the request or may change concurrently.
11. Invalidate the cache when a rule changes or is revoked.
12. Benchmark parse and evaluation separately before optimizing further.

## 17. Key Takeaways

- `ExpressionParser` parses the source; `Expression` evaluates the parsed AST.
- `parseExpression()` returns an Expression usable for repeated evaluation.
- `SpelExpressionParser` instances are reusable and thread-safe.
- Parse once, evaluate many times avoids parsing the same source on hot paths.
- AST may cache PropertyAccessor, IndexAccessor, MethodExecutor, and ConstructorExecutor; this is not a result cache.
- The same Expression can be used with different root objects and EvaluationContexts of the same type/equivalent configuration.
- Do not reuse an Expression across contexts with different security implications; parse separately per profile.
- Create separate EvaluationContexts when variables or root objects depend on the request; do not share a mutable context concurrently without synchronization design.
- Dynamic caches must have bounds, versioning, and invalidation.
- Use variables instead of concatenating request data into the expression source.
- Parse early to catch syntax errors; evaluation can still fail depending on runtime data.
- Measure parse/evaluation separately to determine actual benefit.

## References

- [Spring Framework Reference — Evaluation, Lifecycle and Reuse](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [ExpressionParser Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ExpressionParser.html)
- [Expression Javadoc — Reuse and Security Implications](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/Expression.html)
- [EvaluationContext Javadoc — Lifecycle and Reuse](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationContext.html)
- [SpelExpressionParser Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/standard/SpelExpressionParser.html)
