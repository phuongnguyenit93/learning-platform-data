# Expression Parsing Cost and When to Create a Parser

When using Spring Expression Language (SpEL) on a frequently executed path, it is necessary to separate three operations that have different costs: **creating the parser**, **parsing a string into an Expression**, and **evaluating the Expression**. Creating a SpelExpressionParser does not mean an expression has been parsed. The actual syntax parsing work occurs when calling **parseExpression(...)**; whereas reading data, computing values, and invoking the required operations occur when calling **getValue(...)** or **setValue(...)**.

If an application re-parses the same string on every request, it repeats the work of building the Expression structure even though the syntax has not changed. For fixed expressions or rules updated in batches, a more efficient approach is usually to parse once at initialization or configuration load time, and then reuse the Expression across multiple evaluations.

## Distinguishing the Three Types of Cost

A flow using SpEL typically consists of the following steps:

1. Create or obtain a configured ExpressionParser.
2. Call parseExpression to convert the string into an Expression.
3. Prepare the root object and EvaluationContext for the evaluation.
4. Call getValue or setValue to execute the expression.

The first three costs should not be lumped into one:

| Operation | When It Occurs | Main Work |
|---|---|---|
| Create parser | During parser initialization | Create the parser object and attach SpelParserConfiguration |
| Parse expression | On each parseExpression call | Read syntax, build the expression structure, and validate syntax |
| Evaluate expression | On each getValue/setValue call | Access data, execute operators, convert types, and invoke required operations |

A parser can be reused to parse many strings. Once parsed, an Expression can be evaluated many times with different root objects or contexts.

## Creating a Parser Once and Reusing It

When parser configuration does not change, it is usually best to create a single SpelExpressionParser at application or component initialization time and reuse it:

~~~java
public class PricingEvaluator {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    public Expression parse(String source) {
        return parser.parseExpression(source);
    }
}
~~~

There is no need to create a new parser for each evaluation. The parser is the component used to analyze strings; it does not hold per-request data such as the root object or business variables.

If the application needs compiler mode, auto-grow, or other parser settings, create the parser with the corresponding SpelParserConfiguration and keep that configuration stable over the parser's lifecycle:

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                SpelCompilerMode.OFF,
                MyApplication.class.getClassLoader());

ExpressionParser parser =
        new SpelExpressionParser(configuration);
~~~

Having a separate parser per configuration set helps avoid confusion between expressions parsed under different policies. If the application has multiple parsing modes, manage them as separate dependencies rather than changing configuration arbitrarily per request.

## Parsing Expressions Once at Initialization

If an expression is known ahead of time in source code, it can be parsed immediately when creating the component. When the application starts up, syntax errors are detected early instead of only appearing when a rare request goes through that execution branch.

~~~java
public class OrderEvaluator {

    private final Expression eligibleExpression;

    public OrderEvaluator() {
        ExpressionParser parser =
                new SpelExpressionParser();

        this.eligibleExpression =
                parser.parseExpression(
                        "active and total >= #minimum");
    }

    public boolean isEligible(
            EvaluationContext context,
            Order order) {
        Boolean result = eligibleExpression.getValue(
                context,
                order,
                Boolean.class);

        return Boolean.TRUE.equals(result);
    }
}
~~~

In the example, the Expression is created once in the constructor. Each call to isEligible only performs evaluation with the current context and Order. There is no repeated parsing operation on the request processing path.

If the expression has invalid syntax, the component may fail to initialize. This is usually good behavior for static configuration: the application detects the error at startup instead of silently running with an invalid rule.

## Parsing When Loading Configuration or Dynamic Rules

Not every expression is hardcoded in source code. Some applications store rules in a database, configuration files, or an admin page. For those cases, the appropriate time is usually when **loading or updating a rule**, not every time the rule is applied.

A workflow may consist of:

1. Reading the rule source.
2. Checking the length and permission to use the rule.
3. Parsing the source with a properly configured parser.
4. If parsing fails, rejecting the update and keeping the currently active rule version.
5. If parsing succeeds, storing or publishing the new Expression.
6. Subsequent requests retrieve the parsed Expression to evaluate it.

Illustrative example:

~~~java
public final class RuleEntry {
    private final String source;
    private final Expression expression;

    public RuleEntry(
            String source,
            Expression expression) {
        this.source = source;
        this.expression = expression;
    }

    public String getSource() {
        return source;
    }

    public Expression getExpression() {
        return expression;
    }
}
~~~

~~~java
public RuleEntry loadRule(
        String source,
        ExpressionParser parser) {
    Expression expression =
            parser.parseExpression(source);

    return new RuleEntry(source, expression);
}
~~~

When an administrator updates a rule, the application creates a new RuleEntry and replaces the active version after parsing succeeds. This approach avoids making running requests re-parse the same rule and allows syntax errors to be handled right at the save or publish configuration step.

If a rule uses a template expression, use the proper ParserContext when parsing. ParserContext is part of how the string is interpreted; you should not parse a template using the plain expression overload and expect equivalent results.

## Comparing Parsing Every Time vs. Parsing Once

Approach that parses on every request:

~~~java
public boolean evaluate(Order order) {
    ExpressionParser parser =
            new SpelExpressionParser();

    Expression expression =
            parser.parseExpression(
                    "active and total >= #minimum");

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable(
            "minimum",
            new BigDecimal("100.00"));

    Boolean result =
            expression.getValue(context, Boolean.class);

    return Boolean.TRUE.equals(result);
}
~~~

Each time evaluate is called, the application creates a parser, parses the string, and evaluates the expression. If the source does not change, the first two steps are repeated unnecessarily.

Approach that parses once and reuses:

~~~java
public class OrderEvaluator {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    private final Expression expression =
            parser.parseExpression(
                    "active and total >= #minimum");

    public boolean evaluate(Order order) {
        StandardEvaluationContext context =
                new StandardEvaluationContext(order);

        context.setVariable(
                "minimum",
                new BigDecimal("100.00"));

        Boolean result =
                expression.getValue(context, Boolean.class);

        return Boolean.TRUE.equals(result);
    }
}
~~~

In the second approach, the parser and Expression are retained. Each call only creates a context suitable for the Order and evaluates the expression. This is usually the better choice when the same expression is used repeatedly.

## Parse Cost Depends on Expression Complexity

Not all expressions have the same parsing cost. A simple expression such as:

~~~text
price > 100
~~~

usually involves less work than an expression with multiple levels of properties, method calls, operators, selection/projection, or a template containing many expression segments.

Several factors can affect parsing cost:

- Length of the source string.
- Number of tokens and depth of the syntax structure.
- Number of sub-expressions, operators, and method calls.
- Number of expression segments embedded in a template.
- Parser configuration and enabled features.
- Allocation cost of nodes and objects used to represent the Expression.

Parsing a complex expression once and reusing it is usually more economical than re-parsing it many times. However, if an expression is only used once, maintaining a cache or complex management mechanism may not bring significant benefits.

## Parsing Does Not Mean Evaluating

Calling parseExpression only creates an Expression from the source. It does not automatically execute all logic against a root object.

~~~java
Expression expression =
        parser.parseExpression("customer.address.city");
~~~

At this point, the parser has parsed the syntax and created the Expression. Accessing customer, address, and city only happens when calling getValue with an appropriate root object and EvaluationContext:

~~~java
String city =
        expression.getValue(
                context,
                order,
                String.class);
~~~

Therefore, an expression can parse successfully yet still fail at evaluation time if a property does not exist, an intermediate object is null, a method is not allowed to be called, or data types are incompatible.

Parsing early helps detect syntax errors. It does not prove that the expression will run successfully with all runtime data.

## An Expression Can Be Used with Multiple Root Objects

A parsed Expression does not need to be permanently tied to a single root object. The same Expression can be evaluated against multiple objects as long as they satisfy the structure the expression requires:

~~~java
Expression expression =
        parser.parseExpression("total >= #minimum");

StandardEvaluationContext firstContext =
        new StandardEvaluationContext();
firstContext.setVariable(
        "minimum",
        new BigDecimal("100.00"));

StandardEvaluationContext secondContext =
        new StandardEvaluationContext();
secondContext.setVariable(
        "minimum",
        new BigDecimal("250.00"));

boolean firstResult = Boolean.TRUE.equals(
        expression.getValue(
                firstContext,
                firstOrder,
                Boolean.class));

boolean secondResult = Boolean.TRUE.equals(
        expression.getValue(
                secondContext,
                secondOrder,
                Boolean.class));
~~~

The same Expression is used with two different root objects and two different contexts. Variable values are not stored in the Expression source; they come from the context passed in on each evaluation.

This helps separate the stable syntax from per-request changing data.

## Do Not Cache EvaluationContext Together with Expression

An Expression is usually the reusable part. An EvaluationContext, on the other hand, can contain a root object, variables, and data specific to a single processing execution.

If a context contains per-request variables, it should not be stored alongside the Expression in a shared cache:

~~~java
// Do not use a shared mutable context for all requests
StandardEvaluationContext sharedContext =
        new StandardEvaluationContext();
~~~

If multiple requests simultaneously update variables on this context, one request's values can overwrite another's. That can lead to inconsistent results or data leakage between evaluations.

Keep the Expression in the cache and create a separate context for each evaluation or for each unit of work with a clear lifecycle:

~~~java
public boolean evaluate(
        Expression expression,
        Order order,
        BigDecimal minimum) {

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable("minimum", minimum);

    return Boolean.TRUE.equals(
            expression.getValue(context, Boolean.class));
}
~~~

If a context only contains fixed configuration and is used concurrently, explicitly verify the thread safety of every custom component. In particular, do not share a mutable context if variables or the root object can change.

## Caching Expressions for Dynamic Rules

If the expression source comes from a database or users with rule-configuration privileges, caching the Expression can avoid repeated parsing. With a fixed parser and ParserContext, the source can be used as the cache key.

Illustrative example with ConcurrentHashMap:

~~~java
private final ExpressionParser parser =
        new SpelExpressionParser();

private final ConcurrentMap<String, Expression> expressionCache =
        new ConcurrentHashMap<>();

public Expression getExpression(String source) {
    return expressionCache.computeIfAbsent(
            source,
            parser::parseExpression);
}
~~~

The example above illustrates the principle of caching by source. In a real application, if there are multiple parser configurations or ParserContexts, the cache key must distinguish those configurations. The same string can be interpreted differently between a plain expression and a template expression.

A production cache should have a size limit, an eviction policy, and an invalidation mechanism. Do not use an unbounded ConcurrentHashMap for freely user-supplied sources, because each distinct string can create another Expression and cause memory to grow continuously.

You can use a bounded cache such as Caffeine or an equivalent cache management mechanism. You need to clearly decide on the time-to-live, maximum entry count, and behavior when a rule is deleted or updated.

## Cache Keys Must Reflect Parsing Configuration

Source text alone does not determine the parsing result. Several other pieces of information can also have an effect:

- **ParserContext:** plain expressions and template expressions are parsed differently.
- **Template prefix/suffix:** custom delimiters change how literals and expressions are split.
- **SpelParserConfiguration:** compiler mode, auto-grow, and other parser settings.
- **Rule version or type:** if the application has multiple grammars or distinct parsing policies.

If a single cache is shared across multiple configurations, the key needs to include the details that affect how the Expression is created. A simpler approach is to maintain a separate cache per parser with a fixed configuration.

Do not retrieve an Expression parsed under a broad policy and reuse it in a different security context without checking. An Expression does not contain an EvaluationContext, yet the application's parser configuration and evaluation policy still need to remain consistent.

## Invalidation When Expressions Change

When a rule is updated, the old Expression no longer represents the new source. The application needs to remove or replace the corresponding cache entry.

A safe workflow:

1. Receive the new source.
2. Parse the new source into an Expression.
3. If parsing fails, keep the active rule and return an error to the updater.
4. If parsing succeeds, atomically publish the new version.
5. Remove the old entry or replace it with the new entry.
6. Record the version for logging and tracing when needed.

If multiple requests are using the old Expression, publishing the new reference allows subsequent requests to receive the new version while current requests can finish with the version they previously obtained. The replacement approach needs to match the synchronization and caching model the application uses.

Do not clear the cache before successfully parsing the new source. If the new source has invalid syntax and the old entry has already been deleted, the application may lose the running rule even though the new version cannot yet be used.

## Parse at Startup or Parse Lazily?

Two common strategies:

| Strategy | Approach | Advantages | Considerations |
|---|---|---|---|
| Parse at startup | Parse all static expressions when the application starts | Detects errors early; first request does not pay parse cost | Startup may take longer if there are many rules |
| Parse on config load | Parse when reading or publishing rules | Ties errors to the update operation; no re-parsing per request | Requires version management and invalidation |
| Lazy parse | Only parse when the expression is first used | Avoids parsing rules that are never used | First request pays the cost and may encounter errors |
| Parse every time | Re-parse on every evaluation | Simple implementation | Repeats cost and creates unnecessary objects |

For static expressions, parsing at startup is usually the clear choice. For dynamic rules, parsing when saving or publishing rules helps catch errors before a rule enters the main processing path. Lazy parsing is suitable when the number of rules is large but only a subset is used, provided there is a bounded cache and proper error handling.

Parsing every time only makes sense when expressions truly differ on each call or the frequency is so low that the cost is negligible. Even when the source changes, consider caching by normalized source with a bound instead of continuously creating new parsers.

## Template Expressions Also Need to Be Parsed Once

If the application uses template expressions, the parser must receive the right ParserContext:

~~~java
ParserContext templateContext =
        new TemplateParserContext();

Expression messageTemplate =
        parser.parseExpression(
                "Hello, #{#name}!",
                templateContext);
~~~

After parsing, messageTemplate can be reused with multiple EvaluationContexts:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("name", "An");

String message =
        messageTemplate.getValue(context, String.class);
~~~

If you parse the same source using parseExpression(String) instead of the overload taking a ParserContext, the parser will interpret the entire string in plain expression mode. Therefore, template caching needs to keep the right ParserContext or use a separate cache for the template parser.

## Compiler Mode and First-Evaluation Cost

SpEL has compiler modes **OFF**, **IMMEDIATE**, and **MIXED**. This is part of the evaluation cost after the Expression has been parsed.

Parsing once does not mean all costs are over. With compiler mode, the initial evaluations may use the interpreter, collect type information, and attempt to generate bytecode depending on the mode. If a benchmark only measures the first few calls, the results may not reflect steady-state performance.

When measuring, you need to separate:

- Parser creation time.
- Source parsing time.
- Evaluation time using the interpreter.
- Warm-up and compilation time, if applicable.
- Evaluation time after the compiled form is used.

Do not enable the compiler just to solve repeated parsing. The compiler optimizes part of the evaluation cost; caching the Expression is what solves re-parsing the same source.

## Measuring Parse Cost and Evaluation Cost Separately

To know which optimization helps, benchmarks need to measure separate paths:

1. **Parser construction:** create SpelExpressionParser with the same configuration.
2. **Parse only:** call parseExpression on the chosen source.
3. **Evaluate only:** use a pre-parsed Expression and call getValue multiple times.
4. **Parse plus evaluate:** simulate the current processing path if the application is doing both in every request.
5. **Warm-up/steady state:** if using compiler mode, measure both before and after compilation.

Use JMH for Java benchmarks instead of taking a single measurement with System.nanoTime in a regular test. JMH handles warm-up, iterations, forking, and JVM optimization concerns much better.

Benchmarks need to use expressions and data representative of production. A short arithmetic calculation does not represent selection on a large collection or nested property access. Measure throughput, latency, and allocation as well if Expression creation cost is a concern.

## Handling Untrusted Expression Sources

Parsing user-supplied sources also consumes CPU and memory. If an application allows users to create many distinct expressions, an unbounded cache can be exploited to increase memory usage.

Several measures:

- Limit source length before parsing.
- Limit the number of rules or expressions per tenant/user.
- Use a bounded cache with eviction.
- Rate-limit expression creation or updates.
- Parse at the save/publish step and reject invalid syntax.
- Use an EvaluationContext with a capability allowlist if the source is untrusted.
- Do not concatenate input data into the source; pass data via variables.
- Monitor parsing time and cache miss counts.

Caching helps reduce parse cost, but it does not make an expression safer. Evaluation still depends on the root object, EvaluationContext, property accessors, method resolvers, type locators, and exposed capabilities.

## Parse Errors Should Be Detected at the Right Time

Parsing can fail with **ParseException** when the string has invalid syntax or an unsuitable ParserContext. Evaluation can fail with **EvaluationException** when runtime data or the context does not satisfy the expression.

If parsed at startup, syntax errors may prevent the application from starting. If parsed when saving a rule, errors should be returned to the administrator while the old rule continues to run. If parsed lazily, errors may only surface on the first request that uses that rule.

~~~java
Expression expression;

try {
    expression = parser.parseExpression(source);
} catch (ParseException ex) {
    throw new IllegalArgumentException(
            "Rule has invalid SpEL syntax", ex);
}

try {
    Object result =
            expression.getValue(context, rootObject);
} catch (EvaluationException ex) {
    throw new IllegalStateException(
            "Rule cannot be evaluated with current data", ex);
}
~~~

Separating the two stages helps log the right cause. Do not catch all errors and return a default value, as this can hide invalid source, missing variables, or invalid runtime data.

## Recommended Workflow

For static expressions in an application:

1. Create the parser when initializing the component or application configuration.
2. Parse the expressions once.
3. Keep the Expression in a final field or a registry with a clear lifecycle.
4. Create an appropriate root object and context for each evaluation.
5. Track evaluation errors separately from parse errors.

For dynamic rules:

1. Limit and validate the source when users create or update it.
2. Parse with the right parser and ParserContext.
3. Only publish the rule if parsing succeeds.
4. Cache the Expression by source and parsing configuration, with a capacity bound.
5. Invalidate or replace the entry when the rule changes.
6. Create a separate context for each evaluation's data.
7. Benchmark the parse and evaluation paths separately before optimizing the compiler.

## Conclusion

The costs to distinguish are **creating the parser**, **parsing the source into an Expression**, and **evaluating the Expression**. Creating the parser is usually a lightweight initialization step; parseExpression performs syntax analysis and builds the expression structure; getValue/setValue actually accesses data and executes logic. If the source does not change, re-parsing on every request is usually wasteful.

Create the parser with a stable configuration and reuse it. Parse static expressions at startup; parse dynamic rules when loading or publishing configuration; cache Expressions with bounded capacity and clear invalidation. Only cache the syntax part, not contexts containing request data. When benchmarking, measure parse and evaluation separately, including warm-up if the compiler is enabled. This organization reduces repeated work while keeping runtime data and access permissions in the proper EvaluationContext for each evaluation.
