# Caching Expressions by Source and Configuration Lifecycle

## Objective

Parsing a SpEL expression produces an **Expression** object that can be used for multiple evaluations. If an application frequently evaluates the same rule, re-parsing the string every time adds unnecessary overhead. Parsed Expressions can be cached by expression source and parser configuration for reuse.

The cache must accurately reflect the lifecycle of rules and configuration. When the expression source, ParserContext, compiler mode, or class loader changes, old entries may no longer be valid. At the same time, Expression must be separated from EvaluationContext: Expression describes the parsed logic, whereas EvaluationContext holds the root object, variables, and data for a single evaluation. Mistakenly caching contexts or results can retain stale state and mix data across requests.

After this lesson, you can:

- Distinguish parsing, evaluating, and caching results.
- Cache Expressions by source, rule version, and parser configuration.
- Use caches with bounded capacity and eviction policies.
- Invalidate expressions when content or configuration changes.
- Separate Expression lifecycle from EvaluationContext and root objects.
- Understand the impact of compiler mode and class loaders on caching.
- Avoid unbounded caching of untrusted expressions.
- Test cache hits, cache misses, invalidation, concurrency, and stale state.

## 1. Why Cache Expressions?

When calling parseExpression(), SpEL analyzes the source text and builds the Expression structure. If an application parses the same string on every request, parsing work is repeated even though the logic has not changed.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#root.total >= #minimumTotal");
~~~

If a rule is used for thousands of requests, the Expression can be retained after the first parse and re-evaluated with new root objects and variables.

~~~java
Boolean accepted = expression.getValue(context, Boolean.class);
~~~

Caching Expressions can reduce parse cost and help centralize rule management. It does not automatically make evaluation faster in all cases; costs of property access, method calls, conversion, and data processing remain. If the compiler is used, compilation benefits and conditions are a separate matter requiring measurement.

Caching is appropriate when:

- The same expression source is evaluated many times.
- Rules have a stable ID or version.
- Parser configuration is clearly managed.
- It is possible to determine when to update and evict old expressions.
- The number of rules is controlled or the cache is bounded.

If every request generates a completely different expression, a cache may not achieve a good hit rate and will retain many unnecessary objects.

## 2. Distinguishing Parsing, Evaluating, and Result Caching

Three operations have different lifecycles:

| Component | Content | Typically Appropriate Lifecycle |
|---|---|---|
| Source expression | SpEL string stored in rule/configuration | Per rule version |
| Parsed Expression | Parsed expression structure, possibly with compiled state | Cached by source and parser configuration |
| EvaluationContext | Root object, variables, and resolvers/accessors for one evaluation | Per request or evaluation |
| Evaluation result | Returned value for a specific input | Cache only if all dependencies are fully identified |

Example expression:

~~~text
#root.total >= #minimumTotal
~~~

The source may remain unchanged for months. The parsed Expression can be reused. However, each request may have a different Order and a different minimumTotal, so the context must accurately reflect the current request's data.

Do not treat an Expression cache as a result cache. The same expression can return true for one request and false for another.

Nor should you cache an EvaluationContext containing a request's root object or variables and reuse it for the next request. A context can hold references and mutable state, causing stale data or data leakage between requests.

## 3. Designing Cache Keys

A cache key must uniquely identify an expression within the right parsing context. Using only the rule name may not be enough if the rule content is edited while the key stays the same.

A cache key may include:

- Rule ID or logical name.
- Rule version or revision.
- Exact expression source or a hash of the source.
- ParserContext, including template mode and prefix/suffix pair if any.
- SpelParserConfiguration options that affect parsing/evaluation.
- Compiler mode and compiler class loader if they belong to expression configuration.
- Version or fingerprint of the parser configuration managed by the application.

For example, the same string can be parsed in two different ways:

~~~java
parser.parseExpression(source);
~~~

and:

~~~java
parser.parseExpression(source, new TemplateParserContext());
~~~

The second uses a template ParserContext. Do not take an Expression parsed in normal mode and substitute it for a template expression merely because the source text is identical.

If the application supports custom delimiters, prefix/suffix must belong to the key. Similarly, when compiler mode or class loader changes, create a new cache namespace or invalidate expressions created under the old configuration.

You can use rule ID plus version as the key if the version is guaranteed to increment whenever the source or parser configuration changes. If there is no reliable versioning mechanism, include the source or source hash in the key.

## 4. Simple Expression Cache Example

For a small and controlled set of rules, ConcurrentHashMap can serve as a basic cache:

~~~java
public class SpelExpressionRegistry {

    private final ExpressionParser parser =
        new SpelExpressionParser();

    private final ConcurrentMap<String, Expression> cache =
        new ConcurrentHashMap<>();

    public Expression get(String ruleVersion, String source) {
        String key = ruleVersion + ":" + source;

        return cache.computeIfAbsent(
            key,
            ignored -> parser.parseExpression(source)
        );
    }
}
~~~

computeIfAbsent only creates a value when the key is not yet in the map. If the source does not change and the key is identical, the application gets back the already parsed Expression.

This is an illustrative example for a small cache. In a real application, the key should be a dedicated data type rather than arbitrary string concatenation, and it must account for ParserContext as well as parser configuration.

Structured key example:

~~~java
public record ExpressionKey(
    String ruleId,
    long ruleVersion,
    String source,
    String parserContextId,
    String parserConfigurationId
) {}
~~~

The registry can use ExpressionKey as the ConcurrentMap key. The parserConfigurationId field is an application-generated fingerprint from the relevant options; do not rely on a configuration object's toString() if it is not designed as a stable identifier.

If the project uses a Java version before records, create an immutable class with corresponding equals() and hashCode().

## 5. Using Bounded-Capacity Caches

ConcurrentHashMap does not limit entry count on its own. If rule sources come from users or are generated continuously, the map can grow unboundedly and hold Expressions and related objects in memory.

For systems with many rules or changing sources, use a bounded cache with an eviction policy. For example, Caffeine supports limiting entry counts:

~~~java
Cache<ExpressionKey, Expression> cache =
    Caffeine.newBuilder()
        .maximumSize(2_000)
        .build();
~~~

Retrieving or creating an expression:

~~~java
Expression expression = cache.get(
    key,
    ignored -> parser.parseExpression(source, parserContext)
);
~~~

The limit of 2,000 is only an illustrative value. Choose maximumSize based on the number of active rules, expression size, heap budget, and number of application instances.

Policies typically worth considering:

- Maximum size to limit the number of retained expressions.
- Expiration after inactivity if rules are temporary.
- Explicit invalidation when rules change.
- Statistics for hits, misses, evictions, and parse failures.
- Limits on source length and rate of new rule creation.
- Separating caches by tenant or namespace if rules have different scopes.

An external caching library is not strictly necessary if the number of rules is small, fixed, and loaded at startup. However, if using an unbounded map, there must be strict limits on rule sources and a clear lifecycle.

## 6. Cache Misses, Cache Hits, and Parse Failures

A cache miss occurs when the key does not yet have an entry. The application parses the source, then stores the Expression if parsing succeeds.

A cache hit occurs when the key already exists. The application retrieves the parsed Expression and proceeds straight to the evaluation step.

If the source has invalid syntax, parseExpression() throws an exception. Decide on a policy for parse failures:

- Report a configuration error and do not activate the rule.
- Log the rule ID, version, and parse error location.
- Do not place an invalid Expression into the cache as if parsing had succeeded.
- A separate validation/error state can be stored if the application needs to avoid repeatedly parsing a broken rule, but it must be tied to the right version and have an invalidation policy.

Do not keep a parse error indefinitely if the source can be edited. When a new version is published, the old version's error state must not prevent the new rule from being parsed.

## 7. Invalidation When Source or Rules Change

A cache is only valid while entries still match the current source and configuration.

Events requiring invalidation:

- Expression content is edited.
- Rule is deleted or disabled.
- Rule version is changed.
- ParserContext or delimiters change.
- SpelParserConfiguration changes.
- Compiler mode or compiler class loader changes.
- Application reloads modules or class loaders.
- Tenant or namespace changes rule ownership scope.

There are two common strategies.

### Versioned Key

Each time a rule changes, increment the version. The new key creates a new entry; the old version's entry can be evicted later.

An advantage is that in-flight requests using the old version can finish with the old expression while new requests use the new version, if the system permits two versions to coexist.

### Explicit Invalidation

When a rule changes, call invalidate(key) or invalidateAll() for the relevant namespace. This frees old entries sooner but requires coordination with in-flight evaluations and deployment policy.

Do not mutate the contents of an expression cache entry in place in an unclear way. Create a new key/version or invalidate and re-parse so every request knows which rule revision it is using.

## 8. Parser Configuration Lifecycle

An Expression is created by a parser with a specific configuration. Parser configuration can include:

- Compiler mode.
- Compiler class loader.
- Auto-grow null references.
- Auto-grow collections.
- Maximum auto-grow size.
- ParserContext and template delimiters.
- Other options of the Spring version in use.

If the application has multiple parser configuration sets, use a separate registry/cache per configuration set or include a configuration fingerprint in the key. Do not retrieve an Expression from a cache built with one parser and use it as though it were guaranteed equivalent to an Expression parsed with another parser.

Compiler configuration example:

~~~java
SpelParserConfiguration configuration =
    SpelParserConfiguration.builder()
        .compilerMode(SpelCompilerMode.MIXED)
        .build();

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

When compiler mode changes, treat it as a configuration change that may require a new cache namespace or invalidation. Compiled state belongs to the parsed Expression and can be influenced by the compiler class loader as well as observed runtime types.

Parser configuration should be created centrally, have a clear version or fingerprint, and not change silently while the cache is active.

## 9. Compiler and Expression Lifecycle

An Expression can hold compilation state when the compiler is enabled. The compiler learns runtime types from interpreted evaluations and can generate bytecode for supported expressions.

This affects cache management:

- A cache entry can hold an Expression that already has compiled state.
- Changing compiler mode does not automatically turn an old Expression into a new Expression with a different configuration.
- Changing class loaders or unloading modules can make old compiled expressions no longer valid.
- Changing runtime types can cause the compiled form to fail depending on the chosen mode.
- MIXED can fall back to interpreted mode after a compiled evaluation error.

If a class loader is tied to a plugin or module that can be unloaded, invalidate expressions depending on that class loader before releasing the module. Otherwise, the cache may retain references preventing the old class loader and classes from being reclaimed.

Do not use an Expression cache to hide type instability issues. Test the same expression with realistic runtime types and choose an appropriate compiler mode.

## 10. Separating EvaluationContext from Cache

EvaluationContext holds the root object, variables, and resolvers/accessors. This is typically the state of a single evaluation.

Correct lifecycle example:

~~~java
Expression expression = expressionRegistry.get(key, source);

StandardEvaluationContext context =
    new StandardEvaluationContext(currentOrder);

context.setVariable("minimumTotal", currentMinimum);

Boolean result =
    expression.getValue(context, Boolean.class);
~~~

The Expression is retrieved from the cache. A new context is created with the current request's Order and minimumTotal.

Avoid designs like the following:

~~~java
// Do not keep a context containing request data in a singleton cache.
sharedContext.setRootObject(currentOrder);
sharedContext.setVariable("minimumTotal", currentMinimum);
~~~

If multiple requests simultaneously change the root object or variables on a single context, one evaluation can read another request's state. A context can also retain references to entities, collections, or large objects longer than necessary.

A context can be reused within a sequential flow if the root object and variables are truly stable, but it must have clear ownership and lifecycle. For independent requests, separate contexts are usually safer and easier to test.

## 11. Do Not Cache Results If Dependencies Are Unidentified

Result caching is a different problem from Expression caching. A result can depend on:

- Root object and mutable properties.
- Context variables.
- Referenced beans.
- Current time.
- Locale, timezone, and environment configuration.
- User, tenant, or security context.
- Database data or services invoked by methods.
- ConversionService and custom functions.
- Rule version.

Example expression:

~~~text
#root.total >= #minimumTotal
~~~

If results are cached only by rule ID, another request may receive a Boolean calculated from the previous request's Order or threshold.

Only cache results when input keys, all affecting dependencies, and valid expiration are completely determined. If an expression reads changing state or calls methods with side effects, caching results can break business logic.

In many applications, caching the parsed Expression is sufficient; evaluation still runs against current context and data.

## 12. Configuration and Security When Caching Expressions

Caching does not make an expression source safe. An expression parsed from an untrusted source can still invoke whatever capabilities EvaluationContext permits.

Principles:

- Only parse expressions from authenticated sources authorized to configure rules.
- Use an EvaluationContext with the minimum necessary permissions.
- Restrict provided property accessors, method resolvers, type locators, bean resolvers, and functions.
- Limit source length and rule counts.
- Use bounded caches to avoid unbounded heap consumption.
- Do not log sources if they may contain secrets or private data.
- Separate caches by tenant if rules and ownership are not shared.
- Do not use client-chosen cache keys without checking rule access permissions.
- Version rules and record the version at evaluation time for traceability.
- Invalidate entries when permissions, sources, or configuration change.

A unique cache key is not an authorization mechanism. Before retrieving an expression, the application still needs to verify the caller is allowed to use that rule.

## 13. Observing Caches and Operations

To know whether caching brings benefits, monitor both hit rate and parse/evaluation costs.

Useful metrics:

- Cache hit count and miss count.
- Hit ratio by rule group or namespace.
- Parse duration and parse failure count.
- Current entry count and eviction count.
- Source size or expression length distribution.
- Rule invalidation count and invalidation reasons.
- Evaluation duration separate from parse duration.
- Compiler mode and compiled evaluation errors if the compiler is enabled.

Do not combine parse time with evaluation time. If evaluation accounts for nearly all the time, caching parses may not make a big difference.

When cache misses spike, check whether rule versions are changing continuously, whether keys unintentionally contain request values, or whether the cache is too small. If entries are evicted frequently, consider increasing the limit after measuring heap and workload.

When deploying a new application version, check whether the cache resides in each instance's memory or is shared out-of-process. With an in-memory cache, each instance may have its own entries and must load/invalidate consistently by rule version.

## 14. Testing Caches and Configuration Lifecycles

A test suite needs to verify that the cache returns the right Expression, does not reuse old contexts, and that invalidation works.

### Cache Hit and Miss

~~~java
@Test
void reusesParsedExpressionForSameKey() {
    Expression first = registry.get(key, source);
    Expression second = registry.get(key, source);

    assertSame(first, second);
}
~~~

This test is only appropriate when the registry is designed to return the same instance from the cache. If the cache implementation does not guarantee identity, check how many times the parser is invoked or check hit/miss metrics instead of assertSame.

### Source Version Change

~~~java
Expression versionOne =
    registry.get(keyForVersionOne, "1 + 2");

Expression versionTwo =
    registry.get(keyForVersionTwo, "1 + 3");

assertEquals(3, versionOne.getValue());
assertEquals(4, versionTwo.getValue());
~~~

Two versions must not accidentally share an expression if their sources differ.

### Separate Context per Evaluation

~~~java
Expression expression =
    registry.get(ruleKey, "#root.total >= #minimumTotal");

StandardEvaluationContext first =
    new StandardEvaluationContext(orderA);
first.setVariable("minimumTotal", new BigDecimal("100"));

StandardEvaluationContext second =
    new StandardEvaluationContext(orderB);
second.setVariable("minimumTotal", new BigDecimal("500"));

Boolean firstResult =
    expression.getValue(first, Boolean.class);

Boolean secondResult =
    expression.getValue(second, Boolean.class);
~~~

The same Expression is used with two independent contexts. Tests need to verify each result depends on the corresponding root object and variable.

Cases that should be tested:

- Cache miss parses successfully.
- Cache hit reuses the expression.
- Source changes while rule ID stays the same.
- Rule version changes.
- ParserContext or delimiters change.
- Compiler mode or parser configuration changes.
- Parse failure is not treated as a valid entry.
- Invalidation removes the right key/namespace.
- Eviction does not alter evaluation results.
- Two concurrent requests use separate contexts.
- Cache does not retain request root objects or variables.
- When a plugin/class loader is unloaded, dependent expressions are invalidated.
- Cache stays bounded when new sources continuously appear.

## 15. Cache Implementation Workflow

1. **Identify rule sources.** Choose rule ID, version, and where expression sources are stored.
2. **Define parser configuration.** Fix compiler mode, ParserContext, delimiters, class loader, and related options.
3. **Design keys.** Include source/version and parser configuration identity in the key.
4. **Choose cache policy.** Define maximum size, expiration, and namespace.
5. **Parse on miss.** Only cache the Expression if parsing succeeds.
6. **Create context at evaluation.** Set the current request's root object and variables.
7. **Track version.** Record the rule version used for the evaluation.
8. **Invalidate on change.** Remove old entries when source, permissions, or configuration change.
9. **Measure performance.** Separate parse duration, cache lookup, and evaluate duration.
10. **Test isolation.** Verify contexts and results are not mixed across requests.

## 16. Best Practices

- Cache parsed Expressions when the same source is used repeatedly.
- Build cache keys from rule ID/version, source, and parser configuration.
- Include ParserContext and delimiters in keys when they affect parsing.
- Create stable parser configurations and manage them by version.
- Use bounded caches for rule sets that can grow over time.
- Invalidate or version entries when rules change.
- Do not cache EvaluationContexts containing request root objects or variables.
- Do not cache evaluation results unless all dependencies are fully identified.
- Create separate contexts for independent requests or evaluations.
- Control expression sources and access permissions before parsing/evaluating.
- Monitor hits, misses, evictions, parse failures, and evaluation duration.
- Handle class loader/plugin lifecycles so caches do not retain old classes.
- Measure actual performance before increasing cache complexity.

## 17. Review Checklist

Before putting an expression cache into production, check:

- [ ] Cache stores only successfully parsed Expressions.
- [ ] Cache keys distinguish rule ID and version/source.
- [ ] ParserContext and delimiters are reflected in keys.
- [ ] Parser configuration and compiler mode have clear identities.
- [ ] Class loaders are managed according to lifecycle.
- [ ] Cache has a maximum size or rule source limits.
- [ ] Appropriate expiration/eviction policies are in place.
- [ ] Invalidation occurs when source or configuration changes.
- [ ] EvaluationContext is not kept in a shared cache.
- [ ] Root objects and variables belong to the right request.
- [ ] Evaluation results are not cached with keys missing dependencies.
- [ ] Expressions from external sources are validated and permission-restricted.
- [ ] Metrics exist for hits, misses, parse failures, and evictions.
- [ ] Tests cover cache hits/misses, version changes, invalidation, and concurrency.
- [ ] Tests verify state is not mixed across evaluations.

## Conclusion

Caching Expressions avoids repeatedly parsing the same SpEL source. Cache keys need to reflect the source or rule version along with any affecting ParserContext and parser configuration. When the source, compiler mode, class loader, or configuration changes, create a new version/key or invalidate old entries. Keep EvaluationContext and root objects scoped to each request's lifecycle, do not cache results unless all dependencies are identified, and use bounded caches with metrics to control memory and performance.