# Cost of Selection, Projection, and Method Invocation in SpEL

## Objective

Spring Expression Language (SpEL) collection operations allow filtering and transforming data directly within an expression. Selection `.?[...]` retains elements that satisfy a condition; projection `.![...]` computes a value for each element. When an expression also invokes methods, the actual cost depends on the number of elements traversed, how many times sub-expressions run, the work inside getters/methods, and the amount of resulting collections created.

For small collections and simple expressions, SpEL is usually readable and fast enough. For large datasets, nested collections, or expensive methods, the same expression can trigger many invocations and create many intermediate objects. It is necessary to understand the step-by-step cost, measure on realistic workloads, and move heavy processing to Java or the data query layer when appropriate.

## 1. Basic Cost of Selection

Selection uses `.?[condition]` to test each element:

~~~spel
users.?[active == true]
orders.?[total >= #minimum]
~~~

For a source with `n` elements, standard selection must evaluate the condition for each element. Therefore, if the condition has constant cost, time grows linearly with the number of elements: O(n). The result is a new collection containing the retained elements.

Example:

~~~text
Input:  [A: active, B: inactive, C: active, D: active]
Output: [A, C, D]
~~~

Selection on an array or `Iterable` produces a List result. Selection on a Map retains matching entries in a resulting Map. The result size depends on how many elements match; in the case where all elements match, the resulting collection is nearly the same size as the source.

With first selection `.^[...]`, SpEL can stop when it finds the first matching element. If the matching element is at the end or no element matches, nearly the entire source must still be traversed. Last selection `.$[...]` needs to continue traversing to determine the last matching element.

## 2. Basic Cost of Projection

Projection uses `.![expression]` to evaluate an expression for each element:

~~~spel
users.![name]
products.![price * #quantity]
~~~

For `n` elements, standard projection evaluates the sub-expression `n` times and creates a result collection containing one value per element. If the sub-expression has constant cost, time is O(n); result memory also grows as O(n).

Projection on an array, `Iterable`, or Map returns a List of projected values. For a Map, the sub-expression runs on each entry (`key`, `value`); the result is still a List rather than preserving the Map structure automatically.

Projection does not automatically filter null values, remove duplicates, or sort results. If the sub-expression returns null, the null result still occupies a position. If multiple elements produce the same value, all results are retained.

## 3. Combining Selection and Projection

The following expression both filters and transforms:

~~~spel
orders.?[status == 'PAID'].![id]
~~~

For a source with `n` orders and `k` matching orders:

1. Selection checks up to `n` elements and creates a collection of `k` orders.
2. Projection runs on `k` orders and creates a List of `k` IDs.

If both the condition and projection have constant cost, total time is still O(n + k), which is O(n) since `k <= n`. However, the expression may create an intermediate collection from selection and then create the result collection from projection. For large sources, allocation and garbage collection can be significant even though time complexity is linear.

If only a final result is needed or streaming processing is required, a Java loop can filter and project in a single pass, avoiding holding an intermediate collection. Choose the style based on clarity and measure performance before optimizing.

## 4. Method Invocation in Selection and Projection

A method inside a sub-expression is invoked every time SpEL evaluates that expression:

~~~spel
users.?[#this.isEligible()]
products.![#this.calculateDisplayPrice()]
~~~

In selection, the predicate method can be called once per tested element. In projection, the method is called once per projected element. If a collection has 10,000 elements, a method in projection can be called 10,000 times in a single expression evaluation.

The cost of a method can be much larger than the cost of traversing the collection. A seemingly simple getter can trigger ORM lazy loading; a method can perform complex calculations, parse data, or call a service. If a method performs I/O, a database query, or a network call, total cost can surge and depend on external systems.

Do not put methods with side effects inside selection/projection. Re-evaluating expressions, retrying requests, or running per element can cause the method to be called multiple times and trigger repeated actions.

## 5. Avoiding Repeating the Same Expensive Computation

If a computation is used multiple times in the same expression or across multiple collection operation steps, check how many times it is actually invoked.

Example of why an expensive method should not be repeated in a condition:

~~~spel
products.?[#this.calculateScore() > #minimum and #this.calculateScore() < #maximum]
~~~

In the condition above, `calculateScore()` can be called twice per product because both operands reference the method. With `n` products, the number of calls can reach roughly `2n`.

If the calculation can be prepared beforehand, compute it once in Java and place the value in a DTO/view object:

~~~java
List<ProductView> views = products.stream()
        .map(product -> new ProductView(
                product.getId(),
                product.calculateScore()))
        .toList();
~~~

The following expression only reads the precomputed value:

~~~spel
views.?[score >= #minimum and score < #maximum]
~~~

This clarifies when the computation occurs and avoids calling the method repeatedly in the expression. If data can change, clearly define the snapshot timing and lifecycle of the view object.

## 6. Nested Selection and Projection

Nested collection operations can cause the number of evaluations to grow as the product of the collection sizes:

~~~spel
departments.![employees.?[active == true].![email]]
~~~

Suppose there are `d` departments and each department has an average of `e` employees. The inner selection can check roughly `d * e` employees; projection runs on the retained employees. Total cost grows with the total number of employees traversed, not just the number of departments.

With multi-level structures, estimate the total number of elements traversed at each level. If the expression calls a method or accesses an expensive getter at the innermost level, the cost is multiplied by the number of elements across all outer levels.

Do not use nested collection operations to hide multiple complex loops. When logic has many branches, grouping, joins, flattening, or large aggregations, Java Streams/loops or queries at the data layer are usually easier to control.

## 7. Memory Cost and Intermediate Collections

Selection and projection typically create new result collections. When chaining multiple operations, multiple intermediate collections can arise:

~~~spel
orders.?[status == 'PAID'].![customer.address.city]
~~~

Selection creates a collection of retained orders; projection creates a List of cities. Objects kept in the selection collection are usually references to the source objects, not deep copies. Projection creates new values in a List, though it can also return references to original objects.

With large collections, consider:

- The source size and the ratio of elements retained by selection.
- The number of result/intermediate collections created in a single evaluation.
- The size of objects returned by projection.
- How many times the expression is evaluated concurrently.
- Garbage collection pressure when requests run frequently.

If only a boolean or a first element is needed, do not construct an entire large list only to inspect the result afterward. Use an appropriate expression such as first selection when semantics permit, or process in Java with short-circuiting.

## 8. Property Access and Lazy Loading

Property access in SpEL typically goes through a `PropertyAccessor`. The fact that reflection metadata can be reused does not mean a getter will not run again. Each time the expression reads a property, the corresponding getter or accessor can still be executed.

Example:

~~~spel
orders.?[customer.address.country == 'VN']
~~~

If `customer.address` is a lazy ORM relationship, traversing thousands of orders can issue many database queries (N+1). The cost is no longer just O(n) in memory; it can include thousands of I/O round-trips.

To avoid this:

- Use DTOs/view objects whose data has been loaded according to plan.
- Fetch needed relationships with an appropriate query before evaluating SpEL.
- Do not let getters call repositories or services.
- Use projection on flat data when only a few fields are needed.
- Measure actual query counts in integration tests or a profiler.

## 9. Parse Once and Reuse the Expression

Parsing the expression source has its own cost. If the same rule is evaluated many times, re-parsing on every request adds unnecessary work.

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(
        "users.?[active == true].![name]");

// Reuse the parsed expression for subsequent evaluations.
List<?> names = expression.getValue(context, users, List.class);
~~~

In an application, parsed expressions can be stored by rule ID and version. When the rule source changes, create a new expression for the new version. If expressions are supplied externally, limit the count and size of stored expressions to prevent unbounded cache growth.

Reusing the AST does not mean selection/projection results or method invocation results are cached. Each call to `getValue()` still evaluates the expression against that call's data and context.

Do not share a mutable `EvaluationContext` across concurrent requests if requests modify variables or root state. You can reuse the expression while creating an appropriate context for each evaluation.

## 10. SpEL Compiler and Performance

SpEL has an optional compiler to compile certain expressions to bytecode. Compiler mode can be configured via `SpelParserConfiguration`, including modes such as `OFF`, `IMMEDIATE`, and `MIXED`.

The compiler can make repeatedly evaluated expressions faster when the AST and data types fall within the supported subset. However:

- Not every expression or every AST node can be compiled.
- Collection selection, projection, method dispatch, or changing data types can affect compilability and actual benefit.
- Compilation has an upfront cost; an expression run only a few times may not benefit.
- `MIXED` may start with interpreted evaluation and then attempt compilation based on a threshold; do not assume every expression will eventually be compiled.
- Compiler mode is a performance option, not a security measure or a replacement for restricting permissions in the context.

Verify compilability for the exact expression and Spring version in use, then benchmark with representative data. If an expression is not supported, interpreted evaluation can still work normally.

Configuration example:

~~~java
SpelParserConfiguration configuration = new SpelParserConfiguration(
        SpelCompilerMode.MIXED,
        getClass().getClassLoader());

ExpressionParser parser = new SpelExpressionParser(configuration);
~~~

Do not enable the compiler solely on the assumption that every expression will become faster. Measure warm-up, steady-state time, and allocation.

## 11. When Should Processing Move to Java or the Database?

SpEL fits short, readable expressions operating on objects already in memory. Consider Java or the data layer when:

- Collections have hundreds of thousands or millions of elements.
- Selection/projection is nested multiple levels deep or has many intermediate steps.
- Expressions call expensive methods or require memoization.
- Logic requires grouping, joins, complex sorting, pagination, or streaming.
- Getters may trigger database queries or I/O.
- Control over transactions, timeouts, retries, cancellation, or concurrency is needed.
- Clear profiling and optimization of individual code segments is required.

If data resides in a database, pushing filter conditions down to the repository/query is usually more economical than loading all rows and running selection in SpEL. Load only the needed fields, paginate, and project to DTOs when appropriate.

A large collection alone does not force abandoning SpEL. If the expression is simple, evaluated infrequently, and the data is already present, measure before changing the design.

## 12. Benchmarking Properly

Do not evaluate performance with a single `System.nanoTime()` call around an expression. Results are easily skewed by JIT warm-up, garbage collection, compilation, data caches, and machine load.

For Java benchmarks, JMH is a suitable choice. Separate the following cases:

1. Parse expression and evaluate in the same benchmark to measure total cost when the source is new.
2. Parse once in setup and measure only `getValue()` to measure evaluation.
3. Compare SpEL selection/projection against a Java loop or Stream with the same semantics.
4. Compare with and without method invocation.
5. Use multiple collection sizes and selection ratios.
6. Measure throughput/latency and allocation; use warm-up, measurement iterations, and forks.

Example JMH skeleton:

~~~java
@State(Scope.Thread)
public class SpelCollectionBenchmark {
    private Expression expression;
    private EvaluationContext context;
    private List<UserView> users;

    @Setup(Level.Trial)
    public void setup() {
        ExpressionParser parser = new SpelExpressionParser();
        expression = parser.parseExpression(
                ".?[active == true].![name]");
        context = SimpleEvaluationContext
                .forReadOnlyDataBinding()
                .build();
        users = TestData.users(10_000);
    }

    @Benchmark
    public Object selectionAndProjection() {
        return expression.getValue(context, users);
    }
}
~~~

In this benchmark, the parser and expression are created in setup so the measurement focuses on evaluation. Create a separate benchmark if you want to measure parse cost. Use the same dataset, same conditions, and same output results when comparing with Java.

Do not turn benchmark numbers from a developer machine into production guarantees. Use a profiler and metrics on production-like workloads to identify bottlenecks.

## 13. Comparison Example with a Java Loop

SpEL:

~~~spel
users.?[active == true].![name]
~~~

Single-pass Java:

~~~java
List<String> names = new ArrayList<>();
for (UserView user : users) {
    if (user.isActive()) {
        names.add(user.getName());
    }
}
~~~

A Java loop can filter and project in a single pass, creating only the final result collection. The SpEL expression is shorter and states intent clearly, but selection followed by projection can create an intermediate collection. The final choice should be based on readability, maintainability requirements, and real benchmarks.

## 14. Optimization Checklist

Before optimizing an expression, determine:

1. How many elements does the source have at each collection level?
2. How many elements does selection traverse and how many does it retain?
3. How many values does projection create and are all of them needed?
4. Which methods/getters are called, and how many times is each called?
5. Do getters have lazy loading or I/O?
6. Are there expensive computations repeated in the condition or projection?
7. Are there large intermediate collections or nested results?
8. Is the expression parsed once and reused?
9. Does the compiler support this specific expression, and does it improve benchmarks?
10. Can filtering be done in the database, via prepared DTOs, or with a Java loop/Stream to reduce allocation?

## 15. Common Mistakes and How to Handle Them

| Symptom | Cause to Check | Remedy |
| --- | --- | --- |
| Selection is slow on large collections | Condition must be evaluated on many or all elements. | Reduce input data, filter in the database, or use an appropriate lookup structure. |
| Projection is slow despite short expression | Sub-expression runs once per element. | Measure methods/getters inside; prepare data beforehand if needed. |
| Method is called more times than expected | Method appears multiple times in expression or collection operation traverses every element. | Precompute values, avoid repeating the method in the same condition, and keep methods pure. |
| Many database queries during selection | Getter triggers lazy loading or method calls a repository. | Fetch data beforehand, use DTOs, and inspect query counts. |
| High memory usage when chaining selection and projection | Both intermediate and result collections are created. | Use a single Java loop if single-pass or streaming processing is needed. |
| Nested expression causes execution time to surge | Element counts multiply across levels; method in innermost loop has high cost. | Reduce nesting depth; flatten/aggregate in Java or the database. |
| Repeated expression parsing | Parser is called on every request. | Parse once and cache expressions by ID/version with a capacity bound. |
| Enabling compiler does not speed things up | Unsupported expression, compilation cost, or bottleneck in methods/I/O. | Verify compile support and benchmark; optimize the largest cost component. |
| Unstable benchmarks | Missing warm-up/forks or measuring parse, JIT, and GC together. | Use JMH, separate parse/evaluation, and use representative data. |

## Key Takeaways

- Standard selection traverses the source and evaluates the predicate per element: O(n) if the predicate has constant cost.
- Projection evaluates a sub-expression per element and builds a result List: O(n) time and O(n) result memory.
- Selection followed by projection can create an intermediate collection; with `n` elements and `k` retained elements, basic work is O(n + k).
- Methods inside selection/projection can run once per element; expensive methods or I/O can dominate total cost.
- First selection can stop at the first match; last selection must keep traversing to determine the last match.
- Nested collection operations multiply evaluation counts by the size of each level.
- Getter/property access can still execute code; watch out for ORM lazy loading and N+1 queries.
- Parse once and reuse the Expression; this does not cache evaluation results.
- The SpEL compiler only supports a subset of expressions; verify compilability and benchmark the exact expression.
- Use JMH to measure parse, evaluation, allocation, and compare against Java loops/Streams.
- Push large filtering down to the database or process in Java when streaming, pagination, joins, or fine-grained cost control are needed.

## References

- [Spring Framework Reference — Collection Selection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html)
- [Spring Framework Reference — Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-projection.html)
- [Spring Framework Reference — SpEL Compilation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework API — SpelParserConfiguration](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelParserConfiguration.html)
- [OpenJDK JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh)