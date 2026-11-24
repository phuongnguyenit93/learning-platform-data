# Measuring before enabling the compiler

## Objectives

After this lesson, you will be able to determine when the Spring Expression Language (SpEL) compiler actually brings benefits; establish a baseline in interpreted mode; separately measure parsing, evaluation, and compilation costs; compare OFF, IMMEDIATE, and MIXED modes; and choose representative workloads for benchmarking. You will also know how to monitor latency, throughput, memory allocation, data type stability, and errors after enabling the compiler; roll out in a controlled manner; and revert to interpreted mode when results do not meet expectations.

## 1. The compiler does not automatically make every expression faster

SpEL can evaluate expressions in interpreted mode or compile expressions into bytecode to run on the JVM. The compiler can reduce repeated evaluation overhead for suitable expressions, but it does not guarantee that every expression will be faster.

A simple expression called very few times may not recoup its compilation cost. An expression that depends heavily on resolvers, converters, or changing data structures may not be fully supported by the compiler. An expression that runs fast in a microbenchmark is also not guaranteed to improve overall request response time if most of the time is spent in the database, network, or other processing.

Therefore, before enabling the compiler, answer with data:

- Which expressions are consuming significant time?
- What is the evaluation frequency of the expression?
- Does the cost lie in parsing, evaluation, or external operations?
- Does the expression have a stable structure and data types?
- How much does compiler mode improve throughput or latency?
- Do startup, compilation, and allocation costs increase?
- Are the results accurate across all real-world data cases?

The goal is to optimize parts that significantly impact the application, not to enable the compiler merely because the feature exists.

## 2. Understanding the three compiler modes

SpEL provides three modes via the SpelCompilerMode enum:

| Mode | Behavior |
|---|---|
| OFF | Does not compile expressions; continues evaluating in interpreted mode |
| IMMEDIATE | Prioritizes compiling expressions when the compiler can do so; errors when running the compiled version must be taken seriously |
| MIXED | Allows switching between compiled and interpreted mode; when the compiled version can no longer run due to changing runtime conditions, SpEL can fall back to interpreted mode |

The compiler is disabled by default if the application does not configure another mode.

OFF is a useful baseline for measuring current cost. IMMEDIATE helps evaluate performance when an expression can be compiled and data types match compiler assumptions. MIXED provides a more flexible mechanism when the application encounters type changes or cases where a compiled expression is no longer suitable.

Mode names do not replace benchmarks. Verify behavior on the exact Spring Framework version the application runs, because compilation details and the set of supported expressions depend on the version.

## 3. Separating parse, evaluate, and compile into distinct costs

A SpEL workflow typically has these steps:

1. Create the parser and configuration.
2. Parse the string into an Expression.
3. Prepare the EvaluationContext and data.
4. Evaluate the expression.
5. When the compiler is enabled and the expression qualifies, SpEL can compile the expression after initial interpreted evaluation.
6. Subsequent evaluations can use the compiled version.

If a benchmark runs parseExpression() and getValue() inside the same loop, the results mix syntax-parsing cost with evaluation cost. In real applications, expressions are usually parsed once and reused, so that measurement may not reflect the real production workload.

Measure separately:

- **Parse cost:** time to create an Expression from a string.
- **Interpreted evaluation cost:** `getValue()` time when the compiler is OFF.
- **Compilation/warm-up cost:** initial overhead when the expression transitions to compiled mode.
- **Steady-state cost:** evaluation time after the expression reaches a steady running state.
- **Context setup cost:** cost of creating an EvaluationContext, registering variables, and setting the root object if the application does this per request.

If production reuses the Expression while creating a new context for each request, the benchmark must simulate that exact lifecycle. Do not include context setup in evaluation measurements if production does not do so; nor omit it if the application actually pays that cost.

## 4. Establishing a baseline in OFF mode

First, measure current behavior with the compiler OFF. The parser can be configured explicitly:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        SpelCompilerMode.OFF,
        getClass().getClassLoader()
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

Then parse the expression and evaluate it with a context matching how the application uses it:

~~~java
Expression expression =
    parser.parseExpression("#order.total >= #minimum");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("order", order);
context.setVariable("minimum", minimum);

Boolean accepted =
    expression.getValue(context, Boolean.class);
~~~

Record baselines for each expression category, not just a single representative expression. Include simple expressions, nested property accesses, arithmetic expressions, conditionals, and the expressions that actually appear in processing flows.

The baseline must include both performance results and functional results. Measuring only time without verifying return values can cause a benchmark to accidentally compare two non-equivalent behaviors.

## 5. Enabling the compiler with explicit configuration

A parser can be configured in IMMEDIATE mode:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        SpelCompilerMode.IMMEDIATE,
        getClass().getClassLoader()
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

Or use MIXED mode:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        SpelCompilerMode.MIXED,
        getClass().getClassLoader()
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

The ClassLoader passed into the configuration is where the compiler defines generated classes. In applications with custom classloaders, plugins, or hot-reload environments, check that the classloader matches the types the expression accesses.

Create parsers according to the configuration to be measured. Do not modify a shared parser during a benchmark or at runtime without understanding the lifecycle of expressions already parsed from that parser.

Also remember that compiler mode is a configuration for the parser/expressions created from it. Changing the configuration on another parser does not automatically change existing Expressions.

## 6. Choosing expressions representative of real workloads

A benchmark is only useful when expressions represent how the application actually runs.

Select categories such as:

- Reading a simple property from the root object.
- Reading multiple nested properties.
- Arithmetic calculations on values with stable types.
- Combining boolean conditions.
- Reading variables in EvaluationContext.
- Accessing array or List elements.
- Selection or projection if the application actually uses them.
- Calling methods, converters, or custom accessors if they are on the real path.

Do not benchmark only a short arithmetic expression and conclude the entire SpEL workload will improve. The compiler may support some AST forms better than others.

For each expression, save the source string, root object type, variable types, collection sizes, return type, and call frequency. This information helps reproduce the benchmark and explain results.

## 7. Measuring with realistic data and types

An expression may run on multiple objects with different structures. If a benchmark uses only a mocked single object, results can miss data type issues.

Prepare representative data:

- Concrete types of the root object.
- Actual return types of getters.
- Null values if the model permits them.
- Different subtypes or implementations of interfaces.
- Small, medium, and large collections.
- Variables with types and values similar to production.
- Edge cases that the expression must handle.

A compiled expression may rely on type assumptions observed in earlier evaluations. If the same expression later receives an object of a different type, the compiled version may no longer be suitable.

For example, a getter observed returning one specific type during warm-up may return a different implementation at runtime. Test valid type-change cases as well, not just normal data.

## 8. Warm-up and steady-state

The JVM has its own JIT compiler. Therefore, when measuring the SpEL compiler, distinguish two mechanisms:

- The SpEL compiler compiles an expression into bytecode.
- The JVM can further optimize that bytecode during execution.

A first run is usually not representative of steady-state. Results can be affected by class loading, JIT compilation, caches, garbage collection, and other initialization activities.

The benchmark workflow should include:

1. Warm-up long enough to eliminate most initialization overhead.
2. Measuring multiple iterations or multiple independent forks.
3. Keeping workload and data equivalent across modes.
4. Reporting result distributions rather than just a single average.
5. Measuring first-run and steady-state separately if startup latency matters.
6. Repeating in an environment with configuration close to production.

Do not pick a warm-up count merely from a general guideline. Increase warm-up until results stabilize and check variance across runs.

## 9. Using JMH instead of simple timing loops

Java Microbenchmark Harness (JMH) helps control warm-up, measurement iterations, forks, and how results are consumed. It is better suited than a hand-written loop using System.nanoTime() for small benchmarks.

A minimal benchmark might look like:

~~~java
@State(Scope.Thread)
public class SpelBenchmark {

    private Expression expression;
    private StandardEvaluationContext context;

    @Setup(Level.Trial)
    public void setup() {
        ExpressionParser parser = createParser();
        expression = parser.parseExpression(
            "#order.total >= #minimum"
        );

        context = new StandardEvaluationContext();
        context.setVariable("order", createOrder());
        context.setVariable("minimum", new BigDecimal("100.00"));
    }

    @Benchmark
    public Boolean evaluate() {
        return expression.getValue(context, Boolean.class);
    }
}
~~~

This example illustrates separating setup from the evaluation measurement. In real benchmarks, create different parser configurations for OFF, IMMEDIATE, and MIXED, then run the same expression and data.

If production creates a context on every call, add a separate benchmark measuring that entire path. If production parses expressions per request, include parse cost since it is part of the real workload.

Do not use logging, println, or I/O operations inside benchmark methods. Let JMH consume the result to prevent the JVM from eliminating dead computation.

## 10. Metrics to monitor

Do not look only at average time. At minimum, record:

| Metric | Meaning |
|---|---|
| Throughput | Number of completed evaluations per unit of time |
| Average time | Average time of a single operation |
| p50 | Median latency |
| p95 and p99 | Latency distribution tails, important for requests |
| Allocation rate | Amount of memory allocated over time |
| GC activity | Frequency and duration of garbage collection |
| CPU utilization | CPU usage while the workload runs |
| Error rate | Number of failed evaluations or compiled expressions |
| Startup/warm-up time | Cost before reaching steady-state |

A mode with higher throughput but worse p99 may not suit latency-sensitive APIs. A mode that lowers evaluation time while increasing allocation or GC also needs to be weighed against overall load.

Measure on the same hardware, JVM version, Spring Framework version, heap, collector, and application configuration. Record these parameters with the results so comparisons can be reproduced after version upgrades.

## 11. Comparing OFF, IMMEDIATE, and MIXED

Run the same set of expressions across the three configurations:

| Measurement aspect | OFF | IMMEDIATE | MIXED |
|---|---|---|---|
| Interpreted baseline | Yes | May occur in early phase | May occur in early phase |
| Compiled execution | No | When expression compiles successfully | When expression compiles successfully |
| Behavior when compiled expression is no longer suitable | Not applicable | May throw evaluation error | Has mechanism to fall back to interpreted |
| Compilation cost | None | Yes | Yes |
| Use as baseline | Very suitable | No | No |

Do not assume IMMEDIATE is always faster than MIXED or vice versa. Results depend on the expression, data types, evaluation count, and runtime behavior.

Compare the same operation count, same data, and same warm-up conditions. Clearly report which expressions compiled successfully, which remained interpreted, and which cases caused compiled mode to fail.

## 12. Recognizing expressions unsuitable for compilation

Not every SpEL construct can be supported by the compiler. Some expressions may continue running interpreted because they contain nodes or access mechanisms not compiled in the current version.

Factors to check:

- Expressions using selection or projection.
- Expressions invoking methods via custom resolvers.
- Expressions relying on custom TypeConverters or PropertyAccessors.
- Expressions with changing return or intermediate types.
- Expressions using language features not yet supported by the compiler.
- Expressions with unstable data structures across evaluations.

Do not assume a parser in IMMEDIATE mode means every expression has been compiled. Observe compiler state or behavior using the API provided by the Spring version and check logs/exceptions in a test environment.

If an expression cannot be compiled, interpreted mode may still be the appropriate execution method. There is no need to force every expression into the compiler if benchmarks show no benefit.

## 13. Checking data type stability

An important risk is an expression running with different data types over time.

For example, a property may return different implementations or a context variable may be updated with a different type:

~~~java
context.setVariable("value", Integer.valueOf(10));
expression.getValue(context);

context.setVariable("value", Long.valueOf(10));
expression.getValue(context);
~~~

If the expression was already compiled based on the previous type assumption, evaluating with the new type may no longer be suitable.

Test:

- Same variable name with values of different types.
- Getters returning different valid implementation types.
- Properties that can be null on some evaluations.
- Collections changing element types or implementations.
- Conditional branches producing different result types.

If the data contract requires a single type, normalize the type before placing it in the context. If type changes are valid, verify MIXED mode and handle IMMEDIATE mode errors according to application requirements.

## 14. Measuring the impact of collection operations

Selection and projection can invoke a sub-expression for each element. If the expression contains many property accesses or method calls, total cost grows with element count.

Benchmarks should use representative collection sizes, such as:

- Small collections corresponding to typical requests.
- Medium collections corresponding to common workloads.
- Large collections corresponding to peak or boundary data.

Measure total time and the number of processed elements separately. An expression taking 2 ms on 10 elements cannot be directly compared to one taking 2 ms on 1,000 elements without considering per-element throughput.

If selection/projection is not supported by the compiler in the version in use, enabling the compiler may not change the cost of that part. Identify which nodes are actually compiled rather than only looking at compiler mode.

## 15. Separating SpEL cost from external costs

An expression may invoke a method, bean, or getter that executes a query. If you benchmark the entire expression, database or network time can drown out the SpEL portion.

Example:

~~~text
#orderService.loadSummary(#orderId)
~~~

If loadSummary queries a database, benchmark results mainly reflect the query and connection layer, not SpEL evaluation speed.

Perform two measurements:

1. **Expression microbenchmark:** replace external methods with data or a stub having stable cost to measure SpEL overhead.
2. **End-to-end benchmark:** keep the real service to measure overall impact on the request.

Both are useful, though they answer different questions. Microbenchmarks help understand the compiler; end-to-end benchmarks confirm whether users actually see an improvement.

## 16. Analyzing startup and compilation costs

The compiler can add overhead to early evaluations. If the application is short-lived or an expression is called only a few times, this cost may exceed subsequent savings.

Measure:

- Parser initialization time.
- Expression parse time.
- Number of evaluations before compiled mode is used.
- Compile time if observable.
- Latency during mode transitions.
- Total time needed to recoup compilation cost.

If an expression runs only a few times in the application lifecycle, OFF may be more suitable. If an expression runs millions of times with stable data types, compiled mode has a better chance of delivering clear benefits.

Do not infer the break-even point from a single benchmark run. Measure with the real frequency and real lifecycle of each expression.

## 17. Monitoring errors and correctness after enabling the compiler

Benchmarks must verify that return results match the baseline for the same data.

Compare:

- Return values.
- Return types.
- Behavior with null.
- Thrown exceptions.
- Side effects if the expression invokes stateful methods.
- Results on boundary data and changing data types.

IMMEDIATE mode needs thorough testing when the compiled expression may no longer match runtime types. MIXED mode can fall back to interpreted mode when the compiled version encounters issues, but that does not mean all business errors or all exceptions are automatically fixed.

Do not treat MIXED's fallback as a general error-handling mechanism. If a getter, service, or method throws an exception because of bad data, the application still must handle the error according to its contract.

## 18. Controlled rollout plan

After benchmarking in a test environment, roll out step by step:

1. Keep OFF as the recorded baseline.
2. Select a group of high-frequency, type-stable expressions.
3. Enable the compiler in a staging environment with production-like data.
4. Run functional and load tests.
5. Compare latency, throughput, CPU, allocation, and error rate.
6. Canary deploy to a small percentage of traffic if architecture permits.
7. Monitor long enough to encounter representative data types and workloads.
8. Expand gradually once benefits are confirmed.
9. Retain the ability to revert to OFF if latency or errors worsen.

Do not change compiler mode for all expressions based on a single microbenchmark. Some expressions may benefit, while others show no change or incur extra cost.

## 19. Criteria for deciding to enable the compiler

A decision table can be used:

| Measurement result | Recommended decision |
|---|---|
| Expression rarely called, no bottleneck | Keep OFF |
| Expression runs frequently, stable types, compiled is clearly faster | Consider IMMEDIATE or MIXED after testing |
| Data types legitimately change across evaluations | Check MIXED and normalize data if appropriate |
| Expression not supported by the compiler | Keep interpreted; optimize structure or other logic |
| Throughput increases but p99 worsens | Do not roll out broadly; investigate tail latency |
| CPU decreases but allocation/GC increases significantly | Evaluate application-wide impact |
| Compiled mode errors or results differ from baseline | Do not deploy for that expression |
| End-to-end latency does not improve | Do not enable solely for a nice microbenchmark |

The required improvement depends on the application's SLOs and operating costs. Define acceptance thresholds before benchmarking to avoid picking favorable results after seeing the numbers.

## 20. Example configuring a three-mode benchmark

Parsers can be created per mode to run the same expression:

~~~java
private ExpressionParser parserFor(
        SpelCompilerMode mode,
        ClassLoader classLoader) {

    SpelParserConfiguration configuration =
        new SpelParserConfiguration(mode, classLoader);

    return new SpelExpressionParser(configuration);
}
~~~

Use the same expression source:

~~~java
String source = "#order.total >= #minimum";
~~~

Create three separate Expressions:

~~~java
Expression interpreted =
    parserFor(SpelCompilerMode.OFF, getClass().getClassLoader())
        .parseExpression(source);

Expression immediate =
    parserFor(SpelCompilerMode.IMMEDIATE, getClass().getClassLoader())
        .parseExpression(source);

Expression mixed =
    parserFor(SpelCompilerMode.MIXED, getClass().getClassLoader())
        .parseExpression(source);
~~~

Prepare equivalent contexts and data, then warm up and measure each expression in independent forks. Do not reuse the same expression instance across multiple modes because compiler mode is configured when the parser creates the expression.

In real benchmarks, run each mode in separate processes or forks to reduce interference from class loading, JIT profiles, and shared state from previous runs.

## 21. Recording results for reproducibility

A benchmark report should record:

- Spring Framework and JDK versions.
- Compiler mode and parser configuration.
- ClassLoader used.
- Expression sources and expression count.
- Root object types, variables, and sample data.
- How EvaluationContext is created.
- Warm-up and measurement iteration counts.
- Fork count, thread count, and collection sizes.
- Throughput, p50, p95, p99, and average time.
- Allocation, GC, and CPU.
- Percentage of expressions compiled or remaining interpreted if observable.
- Error counts and result differences compared to OFF.
- Machine specs and heap limits.

Also save results that show no improvement. These measurements help avoid repeating experiments and indicate which expressions are unsuitable for the compiler.

## 22. Takeaways

The SpEL compiler can speed up repeatedly evaluated expressions with suitable structures, but not every expression compiles or runs faster. OFF is the interpreted baseline; IMMEDIATE prioritizes compiled execution; MIXED can fall back to interpreted when a compiled expression is no longer suitable.

Separately measure parsing, evaluation, warm-up/compilation, and context setup. Use workloads, data types, collection sizes, and lifecycles close to production. Warm up the JVM, run multiple forks, and measure throughput, latency distribution, allocation, GC, CPU, and error rate. JMH is more suitable than hand-written timing loops.

Verify correctness with nulls, changing data types, getters, methods, and collection operations. Compiler mode is a performance optimization, not a security sandbox and not a replacement for validation or EvaluationContext permission restrictions.

Enable the compiler only when benchmarks show a meaningful improvement for the application's SLOs and tests confirm results equivalent to the baseline. Roll out in a controlled manner, monitor after enabling, and keep a path to revert to OFF if benefits disappear or errors increase.

## References

- [Spring Framework Reference — SpEL Compilation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [SpelCompilerMode Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelCompilerMode.html)
- [SpelParserConfiguration Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/standard/SpelParserConfiguration.html)
- [JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh)