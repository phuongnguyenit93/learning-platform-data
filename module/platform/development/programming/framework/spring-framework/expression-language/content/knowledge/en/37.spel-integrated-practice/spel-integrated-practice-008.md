# Measuring Interpreted and Compiled Expressions on the Same Data

SpEL can evaluate expressions in two main ways: interpreted evaluation, in which the expression tree is executed through an interpreter mechanism, and compiled evaluation, in which an eligible expression is compiled into Java bytecode. Comparing both approaches on the same data helps determine whether the compiler improves the runtime of a real-world workload.

A fair measurement must keep the expression, root object, variables, data types, EvaluationContext, and number of evaluations identical. You need to separate parse time, context creation, warm-up, and steady-state evaluation. If one side has to parse or construct data every time while the other reuses them, the results will not isolate the difference between interpreted and compiled execution.

## 1. Interpreted and compiled evaluation

In interpreted mode, SpEL executes the nodes in the expression tree via runtime evaluation. This is the default mode and supports a broad range of expressions.

In compiled mode, SpEL attempts to generate Java bytecode for the expression to reduce interpretation overhead in subsequent evaluations. The compiler needs to know the runtime types of objects and only supports a specific set of constructs. Not every expression can be compiled.

Compiled evaluation can be helpful when:

- The same expression is evaluated very many times.
- The types of the root object and properties are stable.
- The expression uses constructs supported by the compiler.
- Interpretation overhead accounts for a significant share of total time.
- Custom resolvers and accessors do not prevent the compilation path.

If an expression runs only a few times or most of the time is spent in database queries, HTTP calls, or business methods, SpEL compilation may not make a noticeable difference.

## 2. Keeping the data identical across both measurements

When comparing, use the exact same input dataset:

- Same expression string.
- Same root object type and values.
- Same context variable values.
- Same data types for properties and arguments.
- Same TypeConverter, PropertyAccessor, and resolvers if any.
- Same result retrieval method and target type.
- Same number of evaluations in each phase.

For example, if the expression checks order total:

~~~text
total >= #minimum
~~~

use the same OrderData and the same minimum for both modes. Do not use a simple object for interpreted mode and an object with nested getters for compiled mode.

It is best to create data once during benchmark setup. Both expressions can be parsed separately by two differently configured parsers, while sharing the same root object and variable values.

## 3. Choosing representative expressions

A small expression helps check basic overhead:

~~~text
total >= #minimum
~~~

An expression closer to a real workload might combine several properties and operators:

~~~text
active and total >= #minimum and region == #allowedRegion
~~~

Do not benchmark only an extremely short expression and conclude the compiler is always faster. Also do not choose an expression containing database queries or API calls and attribute the entire time to SpEL.

Choose expressions representative of real rules, including the data types, property depth, and operators commonly used. If the application has multiple distinct groups of expressions, benchmark each group rather than collapsing them into a single number.

## 4. Configuring compiler mode

The SpEL compiler is controlled by SpelCompilerMode in SpelParserConfiguration.

Three commonly used modes:

| Mode | Behavior |
|---|---|
| OFF | Does not automatically compile; expressions are evaluated in interpreted mode |
| IMMEDIATE | Attempts to compile early once sufficient type information is available |
| MIXED | Starts with interpreted evaluation, then attempts compilation once the expression is evaluated enough times |

OFF is the natural baseline for measuring interpreted evaluation. IMMEDIATE fits when you want to try compiled evaluation early. MIXED fits applications with repeatedly evaluated expressions where you want the runtime to transition automatically under the compiler mechanism.

Do not assume every expression in IMMEDIATE or MIXED has definitely been compiled. The compiler may not support a construct or may lack sufficient type information to generate bytecode.

## 5. Creating parsers for the two modes

You can create two SpelExpressionParser instances with the same class loader but different compiler modes:

~~~java
ClassLoader classLoader = OrderData.class.getClassLoader();

SpelParserConfiguration interpretedConfiguration =
        new SpelParserConfiguration(
                SpelCompilerMode.OFF,
                classLoader
        );

SpelParserConfiguration compiledConfiguration =
        new SpelParserConfiguration(
                SpelCompilerMode.IMMEDIATE,
                classLoader
        );

ExpressionParser interpretedParser =
        new SpelExpressionParser(interpretedConfiguration);

ExpressionParser compiledParser =
        new SpelExpressionParser(compiledConfiguration);
~~~

Using the same class loader avoids unnecessary differences when generating compiled classes. In applications with custom class loaders, use the loader appropriate for the types referenced in the expression.

The parser configured with OFF serves as the baseline. The IMMEDIATE parser attempts to compile the expression when runtime has enough information. If you need to measure MIXED, create a third parser with the rest of the configuration identical and change only the compiler mode.

## 6. Creating identical root objects and contexts

Simple root object example:

~~~java
public class OrderData {

    private final int total;
    private final boolean active;
    private final String region;

    public OrderData(
            int total,
            boolean active,
            String region) {
        this.total = total;
        this.active = active;
        this.region = region;
    }

    public int getTotal() {
        return total;
    }

    public boolean isActive() {
        return active;
    }

    public String getRegion() {
        return region;
    }
}
~~~

Create the same data for both evaluations:

~~~java
OrderData order = new OrderData(
        250,
        true,
        "APAC"
);

StandardEvaluationContext interpretedContext =
        new StandardEvaluationContext(order);

StandardEvaluationContext compiledContext =
        new StandardEvaluationContext(order);

interpretedContext.setVariable("minimum", 100);
interpretedContext.setVariable("allowedRegion", "APAC");

compiledContext.setVariable("minimum", 100);
compiledContext.setVariable("allowedRegion", "APAC");
~~~

Two separate contexts prevent state mutations between measurements. Both still use the same root object and variable values.

If the expression has custom converters or resolvers, configure both contexts equivalently. Do not use a custom resolver on one side and the default resolver on the other.

## 7. Parsing both Expressions from the same source

Use a single source string:

~~~java
String source =
        "active and total >= #minimum and region == #allowedRegion";

Expression interpretedExpression =
        interpretedParser.parseExpression(source);

Expression compiledExpression =
        compiledParser.parseExpression(source);
~~~

The two Expressions are separate instances because each parser has a different compiler mode. However, the source content must be identical.

Do not place parseExpression inside the evaluation benchmark method if the goal is to measure steady-state evaluation. Parsing has its own cost and should be measured in a separate benchmark.

If production parses expressions once at startup and reuses them, the main benchmark should also reuse the Expression.

## 8. Confirming identical results before measuring speed

Before comparing performance, confirm that both evaluation modes produce equivalent results:

~~~java
Boolean interpretedResult =
        interpretedExpression.getValue(
                interpretedContext,
                Boolean.class
        );

Boolean compiledResult =
        compiledExpression.getValue(
                compiledContext,
                Boolean.class
        );

if (!Objects.equals(
        interpretedResult,
        compiledResult)) {
    throw new IllegalStateException(
            "Interpreted and compiled results differ"
    );
}
~~~

If the expression returns an object or number, compare according to that type's semantics. For BigDecimal, clearly decide whether to compare scale or only numeric value.

Correct results are a prerequisite. A faster compiled expression that returns a different result is not a valid optimization.

Test multiple inputs, including true/false, null if allowed, boundary values, and the runtime types the application actually uses.

## 9. Warming up before taking measurements

The first evaluation time may include class loading, JVM JIT compilation, metadata initialization, and other cold-start costs.

With compiled mode, the runtime also needs a chance to collect type information and attempt compiling the expression. If you measure on the very first call, the result may include mode transition overhead.

A measurement procedure should include:

1. Parsing expressions outside the steady-state measurement region.
2. Creating the root object and contexts before measuring.
3. Running warm-up for both modes.
4. Ensuring the compiled expression has had a chance to compile.
5. Measuring only after warm-up.
6. Running multiple iterations and multiple forks.
7. Comparing result distributions, not just a single run.

Warm-up for interpreted mode is also necessary because the JVM can optimize the interpreter code and frequently used method accessors.

## 10. Understanding compilation cost and steady-state cost

The total cost of using a compiled expression can include:

- Parsing the expression.
- Initial interpreted evaluations.
- Compiler time to generate bytecode.
- Class loading cost for the generated class.
- Subsequent compiled evaluations.

If the expression only runs a few times, compilation cost may exceed the time saved.

For expressions running thousands or millions of times, initialization cost can be amortized over many evaluations. In that case steady-state throughput is the key metric, though startup time still matters if the application restarts frequently or rules change continuously.

Measure both cold-start and steady-state if both matter for the product. Do not lump them into a single number without stating the scope.

## 11. JMH benchmark example

JMH is well-suited for measuring small Java operations with controlled warm-up, measurement, and forks.

Benchmark example:

~~~java
@State(Scope.Thread)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
public class SpelModeBenchmark {

    private static final String SOURCE =
            "active and total >= #minimum and region == #allowedRegion";

    private Expression interpretedExpression;
    private Expression compiledExpression;

    private EvaluationContext interpretedContext;
    private EvaluationContext compiledContext;

    private OrderData order;

    @Setup(Level.Trial)
    public void setup() {
        ClassLoader loader =
                OrderData.class.getClassLoader();

        SpelExpressionParser interpretedParser =
                new SpelExpressionParser(
                        new SpelParserConfiguration(
                                SpelCompilerMode.OFF,
                                loader
                        )
                );

        SpelExpressionParser compiledParser =
                new SpelExpressionParser(
                        new SpelParserConfiguration(
                                SpelCompilerMode.IMMEDIATE,
                                loader
                        )
                );

        interpretedExpression =
                interpretedParser.parseExpression(SOURCE);

        compiledExpression =
                compiledParser.parseExpression(SOURCE);

        order = new OrderData(250, true, "APAC");

        interpretedContext =
                new StandardEvaluationContext(order);

        compiledContext =
                new StandardEvaluationContext(order);

        interpretedContext.setVariable("minimum", 100);
        interpretedContext.setVariable("allowedRegion", "APAC");

        compiledContext.setVariable("minimum", 100);
        compiledContext.setVariable("allowedRegion", "APAC");

        Boolean interpreted = interpretedExpression.getValue(
                interpretedContext,
                Boolean.class
        );

        Boolean compiled = compiledExpression.getValue(
                compiledContext,
                Boolean.class
        );

        if (!Objects.equals(interpreted, compiled)) {
            throw new IllegalStateException("Results differ");
        }
    }

    @Benchmark
    public Boolean interpreted() {
        return interpretedExpression.getValue(
                interpretedContext,
                Boolean.class
        );
    }

    @Benchmark
    public Boolean compiled() {
        return compiledExpression.getValue(
                compiledContext,
                Boolean.class
        );
    }
}
~~~

JMH warm-up for the compiled benchmark gives the compiler a chance to turn the expression into bytecode. However, if the expression is ineligible for compilation, the compiled method may still run on the interpreted path. Verify compilability instead of relying solely on the compiler mode name.

The example only illustrates benchmark structure. Use the JMH and Spring versions matching your project, and add data types and expressions representative of your actual workload.

## 12. Measuring parsing separately if needed

If the application constructs expressions dynamically on a frequent basis, parse cost can be significant. In that case, create a separate benchmark for parsing:

~~~java
@Benchmark
public Expression parseExpression() {
    return parser.parseExpression(SOURCE);
}
~~~

This benchmark measures creating an Expression from source. Do not use that result to conclude whether compiled evaluation is faster or slower.

Three separate measurements can be used:

| Benchmark | Scope |
|---|---|
| Parse | Creating Expression from source |
| Context setup | Creating EvaluationContext and attaching root/variables |
| Evaluate | Running parsed Expression with an existing context |

If production caches Expressions but creates contexts per request, the evaluate and context setup benchmarks should be examined separately to reflect the real architecture.

## 13. Checking whether an expression is compilable

The compiler supports only a subset of constructs and access types. An expression may work properly in interpreted mode yet fail to compile.

Factors that can affect compilation:

- Unstable runtime types.
- Properties or methods accessed through custom resolvers.
- SpEL constructs outside the compiler-supported set.
- Return types or intermediate types that cannot be determined.
- Class loader unable to access required classes.
- Objects changing structure or type between evaluations.

In versions that have the SpelExpression.compileExpression() API, you can try compiling explicitly and inspect the returned Boolean value to know whether compilation succeeded:

~~~java
SpelExpression spelExpression =
        (SpelExpression) parser.parseExpression(SOURCE);

boolean compiled = spelExpression.compileExpression();

if (!compiled) {
    // Expression was not compiled successfully.
}
~~~

The API and compilation capabilities should be confirmed against the Spring version in use. Do not force an expression onto the compiled path if the compiler does not support its constructs.

Keep interpreted mode as a valid baseline for every expression that needs to be supported.

## 14. Meaning of IMMEDIATE and MIXED on errors

IMMEDIATE prioritizes early compilation. If the compiled form is used but cannot execute with the actual runtime types, an error may be propagated instead of automatically falling back to interpreted mode.

MIXED is designed to be more flexible: if the compiled form encounters issues during execution, the runtime can fall back to interpreted evaluation and continue according to this compiler mode's mechanism.

That does not mean MIXED is always faster or automatically fixes every error. Falling back can make some evaluations slower and should be observed in benchmarks.

If the application uses multiple root object types or highly dynamic expressions, test different runtime types as well. Do not benchmark only the case where compilation succeeds with a single object and generalize to all data.

## 15. Comparing throughput and latency

Throughput measures how many evaluations complete in a unit of time. Latency measures the time for a single evaluation or request.

The two metrics can tell different stories. Compiled mode may increase throughput in repetitive workloads without noticeably improving request latency dominated by database or network calls.

Metrics to track:

- Operations per second.
- Average time if provided by the benchmark tool.
- Median and percentiles such as p95 and p99 in suitable benchmarks.
- CPU usage.
- Allocation rate and garbage collection.
- Warm-up time and when the compiler activates.
- Rate of expressions successfully compiled.

Do not look at only a single average number. A change may improve the average while worsening tail latency due to compilation or fallback happening during requests.

## 16. Avoiding common biases

Several mistakes make measurements unfair:

| Bias | Why the result is wrong | Fix |
|---|---|---|
| One side parses every time | Mixes parse cost into evaluation | Parse both before the benchmark |
| Using different inputs | Non-equivalent workloads | Use the same root object and variables |
| Measuring only the first call | Includes class loading and compilation | Warm up before measurement |
| Compiled expression never compiled | Compares interpreted against interpreted | Verify compile eligibility |
| One side uses a custom converter | Different conversion paths | Configure equivalent contexts |
| Measuring only one tiny expression | Not representative of workload | Use a realistic set of expressions |
| Running once on a busy machine | High system noise | Multiple forks, iterations, and a stable environment |
| Mixing parse, context, and evaluate | Cannot tell where cost comes from | Benchmark each phase |
| Discarding return values | JVM may optimize away unobserved work | Return results or consume with Blackhole |
| Comparing only averages | Hides tail latency and variance | Examine distributions and multiple runs |

Record the JDK version, Spring Framework version, JVM flags, CPU, operating system, and benchmark configuration so measurements can be reproduced.

## 17. Measuring with custom resolvers and converters

If production uses custom PropertyAccessors, MethodResolvers, or TypeConverters, the benchmark should use those exact components. Otherwise, results can be overly optimistic.

However, separate the baseline benchmark from production-like benchmarks:

1. Baseline using only property access and simple operations.
2. Benchmark with custom converters.
3. Benchmark with custom accessors or resolvers.
4. Benchmark with full expressions and representative data.

This approach helps identify which extension contributes additional cost.

If a custom resolver is not supported by the compiler, compiled mode may not apply to that expression. Do not remove necessary resolvers just to get a nicer benchmark; measure on the configuration the application actually has to run.

## 18. Collection operation considerations

Selection and projection can iterate over many elements. If an expression runs on large collections, the element count and predicate logic usually strongly affect total time.

For example:

~~~text
orders.?[active and total >= #minimum]
~~~

When comparing interpreted and compiled modes, use the same collection, same element order, and same predicate. Measure multiple collection sizes if that reflects the real workload.

Do not let methods in predicates query databases or call APIs. If each element triggers a query, I/O cost will dwarf any difference between interpreter and compiler.

If the collection is very large, consider filtering at the repository or service layer before passing results into SpEL.

## 19. Interpreting benchmark results

Results must be read in context:

- If compiled is clearly faster in steady-state, the expression may benefit when evaluated frequently.
- If the difference is small, parsing, context setup, or method execution may dominate total cost.
- If compiled fails to run, the expression or resolver may not be eligible for compilation.
- If cold-start is slower while steady-state is faster, the decision depends on how many times the expression is evaluated over its real lifecycle.
- If MIXED shows latency spikes, inspect when compilation or fallback occurs.
- If one root object type runs fast while another fails, the expression may depend on the runtime type observed during compilation.

There is no universal speedup ratio for every expression. Apply benchmark conclusions only to the expression types, data, and environment that were measured.

## 20. Checklist for a repeatable comparison

Before accepting conclusions:

1. Use the same source expression.
2. Use the same root object and variables.
3. Use the same data types and collection sizes.
4. Use contexts with equivalent accessor, resolver, and converter configuration.
5. Parse both expressions outside the steady-state measurement region.
6. Confirm identical logical results.
7. Warm up long enough for the JVM and SpEL compiler to stabilize.
8. Confirm the expression can actually compile.
9. Measure parse, setup, and evaluate separately.
10. Run multiple iterations and forks.
11. Record throughput, latency, and allocation.
12. Repeat on a production-representative workload.
13. Test cases where the compiler does not support constructs or runtime types change.
14. Never trade correctness or security boundaries for speed.

## 21. Key takeaways

Interpreted mode is the default baseline and supports a broad range of expressions. Compiled mode can reduce repeated evaluation cost using Java bytecode, but only helps when the expression is eligible for compilation and the execution count is large enough to offset warm-up, compilation, and class loading costs.

For a fair comparison, use the same source, root object, variables, data types, context, and expected results. Parse expressions and build data outside the steady-state measurement region; warm up both modes; verify the expression can compile; and measure parse, context setup, and evaluate separately.

OFF serves as the interpreted baseline, IMMEDIATE tries compiling early, and MIXED allows more flexible transitions when the compiled form encounters issues. Use JMH or an appropriate benchmarking tool, run multiple iterations/forks, and inspect throughput, latency, allocation, and fallback behavior together. Only choose a compiler mode after results are confirmed on realistic workloads with the same correctness requirements.