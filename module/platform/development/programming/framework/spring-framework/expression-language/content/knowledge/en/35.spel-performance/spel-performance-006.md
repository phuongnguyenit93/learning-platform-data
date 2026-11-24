# Expression Compiler and Criteria for Measuring SpEL Effectiveness

Spring Expression Language (SpEL) can evaluate expressions in two ways: **interpreted** and **compiled** (compiled to bytecode). In interpreted mode, SpEL traverses the expression structure and performs each operation at runtime. When compilable, SpEL generates bytecode so subsequent evaluations execute more directly, potentially reducing repeated overhead.

The compiler does not make every expression faster, nor does it support every SpEL construct. Effectiveness depends on evaluation count, data type stability, expression structure, and the cost of invoked methods. Measure on representative workloads before enabling the compiler in an application.

## 1. Interpreted Evaluation and Compiled Evaluation

When parsing an expression, SpEL creates a structure representing the expression. In interpreted mode, on each evaluation SpEL uses that structure to perform operations such as reading properties, calling methods, computing values, and converting types.

Example:

    ExpressionParser parser = new SpelExpressionParser();
    Expression expression =
            parser.parseExpression("customer.age >= 18");

    Boolean result = expression.getValue(context, Boolean.class);

In interpreted mode, the expression is executed through SpEL's evaluation mechanism. If the same Expression is evaluated many times, the framework still performs the corresponding interpretation steps.

The SpEL compiler can generate a Java class at runtime containing bytecode representing the expression's behavior. After successful compilation, subsequent evaluations can run the compiled form instead of going through the entire interpreted path.

The compiler optimizes **evaluation**, does not replace expression parsing, and does not automatically optimize external methods invoked by the expression. If an expression calls a method that queries a database taking several milliseconds, reducing SpEL interpretation overhead may be negligible compared to the database time.

## 2. When Is Compilation Beneficial?

Compilation is usually beneficial when:

- The same Expression is reused many times.
- The expression is evaluated frequently on a hot processing path.
- Object types and accessed properties remain stable across evaluations.
- Interpretation overhead is a significant portion of total processing time.
- The expression uses operations within the set of constructs supported by the compiler.

Compilation is usually less beneficial when an expression runs only a few times, most time is spent in I/O or external methods, or the expression changes continuously so parse/compile cost is not amortized over enough evaluations.

If every request creates a parser and re-parses the same string, that cost may exceed the savings from compiled evaluation. Reuse Expressions when appropriate and measure parsing cost, first evaluation, compilation, and steady-state evaluations separately.

## 3. SpEL Compiler Modes

SpEL provides three modes via the `SpelCompilerMode` enum:

| Mode | Behavior |
|---|---|
| `OFF` | Do not use the compiler; this is the default |
| `IMMEDIATE` | Attempt compilation after the first interpreted evaluation |
| `MIXED` | Interpret initially, then attempt compilation after a number of evaluations; can fall back to interpreted if the compiled form encounters a runtime error |

**OFF** is suitable when consistent interpreted behavior is desired or there is no evidence yet that compilation brings benefits.

**IMMEDIATE** is suitable when expressions have stable types and the application wants to switch to compiled evaluation early. The first run still requires interpreted evaluation to gather information needed for compilation. If the compiled form later throws an exception, the error is propagated to the caller; this mode does not automatically fall back to interpreted to hide errors.

**MIXED** is more suitable when runtime types may vary or it is uncertain whether the compiled form always applies. The framework can fall back to interpreted mode if the compiled expression fails and attempt compilation again later. Switching modes like this can cause evaluation times to fluctuate, so both performance and correctness must be checked.

Do not rely on a fixed evaluation count threshold for MIXED unless guaranteed by the Spring version in use. Check the behavior of the specific framework version and measure in a realistic environment.

## 4. Configuring the Compiler via SpelParserConfiguration

Compiler mode is configured when creating the parser with `SpelParserConfiguration`:

    ClassLoader classLoader =
            Order.class.getClassLoader();

    SpelParserConfiguration configuration =
            new SpelParserConfiguration(
                    SpelCompilerMode.IMMEDIATE,
                    classLoader
            );

    ExpressionParser parser =
            new SpelExpressionParser(configuration);

    Expression expression =
            parser.parseExpression("total * taxRate");

    BigDecimal result =
            expression.getValue(context, BigDecimal.class);

The example uses IMMEDIATE. To disable the compiler, use `SpelCompilerMode.OFF`; to use adaptive mode, use `SpelCompilerMode.MIXED`.

The ClassLoader passed to the configuration is used to load bytecode classes generated by the compiler. It needs to see the types referenced by the expression. In applications with plugins, modules, custom classloaders, or hot reload, choose a classloader aligned with the lifecycle of the domain classes used in the context.

Compiler mode belongs to parser configuration. When comparing modes, create separate parsers and corresponding Expressions per mode to avoid mixing compilation state across measurements.

## 5. Compilation Occurs After Runtime Information Is Available

The SpEL compiler relies on information gathered when the expression is evaluated. Therefore, an expression usually needs at least one interpreted evaluation before it can be compiled.

Example:

    Expression expression =
            parser.parseExpression("customer.age + 1");

    Integer first =
            expression.getValue(context, Integer.class);

    Integer second =
            expression.getValue(context, Integer.class);

In an appropriate compiler mode, the first evaluation provides information about target and result types; subsequent runs can use the compiled form if the expression is eligible.

Do not treat Expression creation or successful parsing as proof that an expression has been compiled. Parsing and compiling are separate stages. An expression can parse and run interpreted normally yet not fall within the constructs supported by the compiler.

Certain specific SpEL APIs allow requesting compilation or reverting to interpreted mode via the `SpelExpression` implementation. If using this low-level API, consult the documentation for the exact Spring version and handle compilation failure cases; do not assume every Expression can be compiled.

## 6. Limitations to Know

The SpEL compiler only supports a subset of expression forms. Compilability depends on the Spring version and the nodes present in the expression. Some dynamic constructs or collection operations such as selection and projection may continue running interpreted.

Do not rely on an expression having simple syntax to conclude definitively that it can compile. Confirm on the exact framework version and realistic context.

Factors that can affect compilation:

- Whether nodes in the expression support bytecode generation.
- Whether runtime types of the root object and properties are stable.
- Whether invoked methods have consistent signatures and return types across evaluations.
- Whether a property is sometimes null, sometimes a different type, or changes structure.
- Whether the ClassLoader can see the required types.
- Whether the expression uses collection operations or dynamic constructs.

If the compiler cannot produce a compiled form, the expression can still operate in interpreted mode. That is not necessarily a business error; it simply means the compiler cannot be applied to that expression.

## 7. Runtime Type Stability and Errors When Compiled Form Runs

A compiled expression may rely on runtime types observed during interpretation. If subsequent evaluations pass in objects of a different type or values with an incompatible shape, the compiled code may fail.

For example, an expression is evaluated the first time with a Customer type whose `age` property is Integer, but the next time the root object is a different implementation or the property returns a different type. The compiled form may not handle that situation the way the interpreted evaluator does.

Cases to watch out for:

- Root object changes across multiple incompatible classes.
- Property sometimes returns null, sometimes an object of another type.
- Method overloads or return types differ by target.
- Collection contains elements of multiple types.
- Data changes make an access path no longer valid.
- Classes loaded from a different classloader after the expression has compiled.

If input types vary significantly, MIXED may be more suitable than IMMEDIATE because it has a mechanism to fall back to interpreted when compiled execution errors. However, fallback does not replace testing; the application still needs to verify whether results and exceptions match its contract.

## 8. ClassLoader and Application Lifecycle

The compiler generates bytecode at runtime and requires a ClassLoader that can define and load generated classes as well as access the classes used by the expression.

In a simple application, the domain class's classloader is usually an appropriate choice. In applications using plugins, application servers, multiple modules, or DevTools reload, the classloader may change with the context lifecycle.

If a compiled expression holds references to an old classloader while the application has reloaded domain classes, type errors or classloader lifecycle issues can occur. Recreate the parser and Expression when the relevant context or classloader is replaced; avoid retaining compiled expressions longer than the lifecycle of the types they depend on.

Do not choose a classloader solely because compilation succeeds in a small test. Check how the application deploys and loads classes in the real runtime environment.

## 9. Reusing Expressions to Amortize Cost

If an expression is used many times, parse once and reuse the Expression object when appropriate:

    ExpressionParser parser =
            new SpelExpressionParser(configuration);

    Expression expression =
            parser.parseExpression(
                    "#order.total >= #minimum"
            );

    Boolean evaluate(
            Order order,
            BigDecimal minimum,
            EvaluationContext context) {

        context.setVariable("order", order);
        context.setVariable("minimum", minimum);

        return expression.getValue(context, Boolean.class);
    }

This is an illustrative example of Expression lifecycle; contexts and mutable data must be managed safely per request or thread. Do not share an EvaluationContext that is mutated concurrently across multiple threads.

If expressions are created from dynamic configuration, they can be cached by expression string or a versioned configuration code. Caches need a size bound and invalidation policy when configuration or classloaders change. Do not let users create an unlimited number of expressions causing unbounded cache growth.

## 10. Criteria for Measuring Effectiveness Properly

A useful benchmark must answer whether the compiler reduces the cost of a real workload. Do not just measure a single `getValue()` call and draw conclusions.

Measure separately:

1. **Parse cost:** time to create an Expression from a string.
2. **First evaluation:** cost of the initial evaluation, including interpretation and compilation preparation if any.
3. **Compilation cost:** overhead to generate and load bytecode, if measurable separately in the harness.
4. **Steady-state evaluation:** time or throughput after warm-up when the compiled form is used.
5. **Allocation and GC:** volume of objects created and impact on garbage collection.
6. **Tail latency:** p95/p99 latency if the application is latency-sensitive.

Compare OFF, IMMEDIATE, and MIXED with the same expression, same data, same EvaluationContext, and same JVM environment. Ensure results are consumed so the JIT or benchmark harness does not eliminate the work being measured.

## 11. Using JMH Instead of Manual Measurement Loops

JMH is the appropriate tool for measuring Java microbenchmarks. A minimal benchmark can look like:

    @State(Scope.Thread)
    public class SpelBenchmark {

        private EvaluationContext context;
        private Expression expression;

        @Setup(Level.Trial)
        public void setup() {
            SpelParserConfiguration config =
                    new SpelParserConfiguration(
                            SpelCompilerMode.IMMEDIATE,
                            getClass().getClassLoader()
                    );

            ExpressionParser parser =
                    new SpelExpressionParser(config);

            expression = parser.parseExpression(
                    "#root.total >= #minimum"
            );

            context = new StandardEvaluationContext(
                    new OrderView(new BigDecimal("150"))
            );
            context.setVariable(
                    "minimum",
                    new BigDecimal("100")
            );
        }

        @Benchmark
        public Object evaluate() {
            return expression.getValue(context);
        }
    }

This is an illustrative skeleton; real benchmarks should have separate configurations for OFF, IMMEDIATE, and MIXED while separating setup from the measured part. Use `@Warmup`, `@Measurement`, and multiple forks to reduce effects from JVM startup and JIT.

With MIXED, warm-up must be long enough for the expression to pass through the interpreted phase and reach a measurable steady state. Do not use the timing of the first few invocations as representative of steady state.

Avoid writing a single `System.nanoTime()` loop in a regular test. Results are easily skewed by JIT, GC, scheduler, dead-code elimination, and JVM state across runs.

## 12. Choosing Representative Workloads

Benchmarks need to reflect how expressions are used in the application:

- Expressions have complexity equivalent to production.
- Root objects, variables, and properties have types matching real data.
- Evaluation count and cache/reuse ratio match reality.
- Collections have appropriate sizes and element types.
- Methods invoked inside expressions have production-equivalent cost.
- Null ratios, type variations, and boundary data are represented.
- JVM, JDK, Spring, and classloader configurations match the target environment.

Include at least one simple calculation expression benchmark, one expression reading nested properties or calling methods, and one workload close to a real use case. Do not use a tiny arithmetic expression to extrapolate that the entire application will speed up by the same ratio.

If an expression primarily calls databases or APIs, also measure end-to-end time. In such cases, compiled evaluation might improve a microbenchmark while barely changing user-facing latency.

## 13. Reading Results and Calculating the Break-Even Point

Compilation has an upfront cost. Benefits only appear when the number of evaluations is large enough for per-call savings to offset compile cost.

The break-even point can be estimated:

    breakEvenEvaluations =
        compileOverhead /
        (interpretedTimePerCall - compiledTimePerCall)

The formula only makes sense when interpreted time per call exceeds compiled time per call and measurements come from a steady-state workload. It is an estimate, not a replacement for end-to-end benchmarks.

When reading results, inspect:

- By what percentage did throughput increase?
- How did average time and p95/p99 change?
- How long does compilation overhead take to pay back?
- Did allocation and GC increase?
- Did any expressions fail to compile or fall back?
- Did any runtime errors appear when data types changed?
- Is the improvement large enough to justify added operational complexity?

Do not look only at a single average number. A mode with higher throughput but fluctuating tail latency or frequent fallbacks may be unsuitable for latency-sensitive systems.

## 14. Testing Correctness Between Interpreted and Compiled

Before enabling the compiler, compare expression results and behavior across modes:

1. Same input produces the same output.
2. Null values are handled according to contract.
3. Different runtime types do not cause unexpected errors.
4. Method overloads and TypeConverters behave consistently.
5. Exceptions are thrown in the right cases.
6. Non-compilable expressions still have an appropriate interpreted path.
7. MIXED fallback does not alter business results.
8. ClassLoader of the test environment matches the deployment environment to be verified.

Test both boundary values and production-like data. If an expression reads nested properties, test null intermediate objects. If an expression calls methods, test possible argument types and method states. If an expression runs on collections, test empty collections and elements of different types.

Compilation is an execution optimization; it must not alter the functional contract the application expects.

## 15. Common Performance Evaluation Mistakes

- **Measuring only the first call:** results include parse, warm-up, or compile overhead, not representing steady state.
- **Not reusing Expression:** benchmark mainly measures the parser instead of the compiler.
- **Warm-up too short:** MIXED has not switched to compiled mode or JVM has not stabilized.
- **Using overly simple data:** fails to reflect types, nulls, collections, and methods in production.
- **Ignoring compile overhead:** fails to account for the number of calls required to pay back upfront cost.
- **Measuring with a hand-written loop:** easily skewed by JIT, GC, and dead-code elimination.
- **Measuring only throughput:** ignores tail latency, allocation, and fallback.
- **Assuming every expression can compile:** some nodes are not in the supported set.
- **Ignoring classloader:** an expression may run in tests but fail in reload or plugin environments.
- **Treating the compiler as a fix for slow I/O:** the compiler only optimizes SpEL evaluation, not making databases or APIs faster on its own.

## 16. Decision Workflow for Enabling the Compiler

A practical workflow:

1. Identify which expressions are evaluated frequently and account for significant cost.
2. Reuse parser/Expression instead of re-parsing on the hot path.
3. Measure a baseline with `SpelCompilerMode.OFF`.
4. Check whether the expression belongs to the compiler-supported subset and whether data types are stable.
5. Measure IMMEDIATE and MIXED using a benchmark with warm-up.
6. Test correctness with boundary data and type variations.
7. Check classloader, context lifecycle, and fallback behavior.
8. Deploy only when measured benefits are meaningful for realistic workloads.

If there is no evidence that SpEL evaluation is a bottleneck, keeping OFF is a sensible choice. Simplifying expressions, caching Expressions, and reducing evaluation frequency are usually steps to measure before adding compilation.

## 17. Key Takeaways

The SpEL compiler generates bytecode to reduce repeated evaluation overhead; it does not replace the parser and does not optimize I/O operations external to the expression. `OFF` disables the compiler, `IMMEDIATE` attempts compilation after the first interpreted evaluation and does not automatically fall back when compiled execution errors, while `MIXED` can fall back to interpreted when the compiled form fails. Compilation applies only to a subset of expressions and depends on runtime type stability and the ClassLoader. Reuse Expressions, measure parse/first evaluation/steady state separately, use JMH with warm-up and representative workloads, and verify allocation, tail latency, and correctness. Enable the compiler only when benchmarks show substantial benefit in the real deployment environment.
