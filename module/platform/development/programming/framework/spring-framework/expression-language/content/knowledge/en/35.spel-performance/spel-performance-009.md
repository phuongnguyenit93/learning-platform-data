# Measuring Latency, Allocation, and Throughput Before Optimizing in Spring Expression Language

When a Spring Expression Language (SpEL) expression is evaluated frequently, small per-call costs can accumulate into significant latency or put pressure on CPU and memory. However, do not optimize simply because an expression looks complex or because compiler mode seems faster. First, measure on a representative workload to find out whether time is spent in parsing, evaluation, context creation, data conversion, or business logic itself.

A useful measurement needs to look at at least three aspects:

- **Latency:** how long a single execution takes, including percentiles such as p50, p95, and p99.
- **Allocation:** how many objects/bytes each execution creates and how it affects garbage collection.
- **Throughput:** how many evaluations or requests the system can process per unit of time under load.

Measuring each part separately helps pinpoint the right bottleneck. After establishing a baseline, try caching Expressions, reusing configurations, changing compiler mode, or simplifying expressions; finally, re-measure under the same conditions to confirm improvement.

## 1. Why Measure Before Optimizing?

A \`getValue()\` call can involve several different tasks:

1. Looking up properties on the root object or nested objects.
2. Calling methods via MethodResolver.
3. Reading variables from EvaluationContext.
4. Converting types via TypeConverter.
5. Executing selection, projection, indexing, or operators.
6. Creating result objects or template strings.
7. Handling errors if data is invalid.

Beyond evaluation itself, the application may also create parsers, parse expressions, create EvaluationContexts, register variables, prepare data, and write logs.

If a benchmark lumps all steps into one number, it is very hard to know which part to optimize. For example, if parsing occurs on every request, parse cost may outweigh the evaluation portion the application is trying to improve.

The goal of a benchmark is to answer concrete questions:

- How long does it take to parse an expression?
- How long does it take to evaluate an already parsed Expression?
- Is creating a new EvaluationContext significant?
- Does the expression allocate heavily?
- As load increases, does throughput scale linearly or become limited by CPU, GC, or locks?
- Does compiler mode improve realistic workloads?
- Does a change worsen p95/p99 even though the average looks better?

## 2. Three Groups of Metrics to Track

### 2.1. Latency

Latency is the time to complete a single execution. It can be measured in nanoseconds or microseconds in benchmarks, and milliseconds in real request flows.

Do not look only at the average. Some evaluations can be slow due to GC, JIT compilation, cache misses, system load, or special data.

Useful percentiles:

| Metric | Meaning |
|---|---|
| p50 | Half of executions complete within this time or faster |
| p90 | 90% of executions complete within this time or faster |
| p95 | 95% of executions complete within this time or faster |
| p99 | 99% of executions complete within this time or faster |
| max | Slowest execution in the measurement window; sensitive to outliers |

p50 describes typical experience, while p95 and p99 help detect tail latency. If p50 drops but p99 spikes sharply, that optimization may be unsuitable for systems requiring consistent response times.

### 2.2. Allocation

Allocation measures the amount of memory allocated per unit of work, typically expressed in bytes/op or objects/op.

An expression may run fast yet create many temporary objects, causing GC to run frequently. Under high load, GC overhead can increase latency and reduce throughput.

Metrics to inspect:

- Bytes allocated per operation.
- Allocation rate over time.
- Garbage collection count and time.
- Heap occupancy before and after load bursts.
- Most heavily allocated object types during profiling.

Do not equate allocation with retained heap. Objects allocated and quickly reclaimed still increase GC pressure even though they are not retained long-term in the heap.

### 2.3. Throughput

Throughput indicates how many executions complete per unit of time, such as operations/second or requests/second.

When a benchmark increases thread count, throughput may rise up to a point and then plateau. Causes can include CPU saturation, contention, allocation/GC, shared resources, or external dependencies.

Measure throughput alongside latency. Higher throughput with an excessive increase in p99 may not be a good improvement for users.

## 3. Separating Parsing Cost from Evaluation

\`ExpressionParser.parseExpression(...)\` turns a string into an Expression object. Afterward, \`Expression.getValue(...)\` evaluates the parsed object.

The two operations have different costs:

~~~java
ExpressionParser parser =
    new SpelExpressionParser();

Expression expression =
    parser.parseExpression("price * #quantity");

Object result =
    expression.getValue(context);
~~~

If an application uses the same expression many times, it is usually best to parse once and reuse the Expression. If a benchmark parses and evaluates inside the same method, results will reflect both costs and will not show evaluation speed on its own.

There should be at least two benchmarks:

- **Parse benchmark:** measures the cost of creating an Expression from a string.
- **Evaluation benchmark:** pre-parses in setup and measures only getValue in the benchmark method.

You can add an end-to-end benchmark to measure context creation, variable registration, and evaluation together if that is how the application actually runs.

## 4. Using JMH for Java Microbenchmarks

JMH (Java Microbenchmark Harness) is designed for measuring JVM performance. It handles many pitfalls that easily skew hand-written benchmarks, such as warm-up, dead-code elimination, JIT compilation, and process forking.

A JMH benchmark should:

- Have sufficient warm-up for the JVM to reach steady state.
- Have multiple measurement iterations.
- Use multiple forks to reduce carry-over JVM state from previous runs.
- Return results or feed them into a Blackhole to prevent the compiler from eliminating work.
- Use representative data and avoid creating unintended extra work inside the measured region.
- Record JDK version, Spring version, and machine specifications.

Example benchmark structure evaluating a parsed Expression:

~~~java
@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 8, time = 1)
@Fork(3)
public class SpelEvaluationBenchmark {

    private Expression expression;
    private StandardEvaluationContext context;

    @Setup(Level.Trial)
    public void setup() {
        Product product =
            new Product(new BigDecimal("250000"));

        context = new StandardEvaluationContext(product);
        context.setVariable("quantity", 3);

        ExpressionParser parser =
            new SpelExpressionParser();

        expression =
            parser.parseExpression("price * #quantity");
    }

    @Benchmark
    public Object evaluate() {
        return expression.getValue(context);
    }
}
~~~

In this benchmark, the parser, Expression, and context are created in setup, outside the measured region of the evaluate method. Results reflect mainly the cost of evaluating the expression with a prepared context.

If the real application creates a new context for every request, benchmark that case separately; do not use results from a reused context alone to represent the entire production flow.

## 5. Benchmarking Parsing Separately

To measure parsing cost, place the parse operation inside the benchmark method:

~~~java
@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
public class SpelParsingBenchmark {

    private ExpressionParser parser;

    @Setup(Level.Trial)
    public void setup() {
        parser = new SpelExpressionParser();
    }

    @Benchmark
    public Expression parse() {
        return parser.parseExpression(
            "price * #quantity + tax"
        );
    }
}
~~~

This benchmark measures creating an Expression from a string. It does not measure getValue.

Use expressions with length and structure close to those in your application. An expression adding two numbers does not represent long templates, collection selections, or method invocations with many nested properties.

If the application caches Expressions by key, also measure cache hit/miss rates and lookup cost in an end-to-end benchmark.

## 6. Measuring EvaluationContext Creation Cost Separately

EvaluationContext holds the root object, variables, and access services. Creating a new context each time can create extra objects and allocations.

Compare two cases:

- Reusing a context within an appropriate scope.
- Creating a new context for each execution and registering variables.

Example context-creation benchmark:

~~~java
@Benchmark
public Object evaluateWithNewContext(BenchmarkState state) {
    StandardEvaluationContext context =
        new StandardEvaluationContext(state.product);

    context.setVariable("quantity", state.quantity);

    return state.expression.getValue(context);
}
~~~

Comparing against a benchmark using a context prepared in setup will show the additional cost of context creation and variable registration.

Do not share a context with mutable variables across independent requests or threads without controlling state. Reuse must match the application's data lifecycle and concurrency requirements.

An often clear choice is to reuse the parsed Expression, while creating a separate EvaluationContext for each unit of work if the context holds per-request changing data.

## 7. Choosing Representative SpEL Workloads

Do not benchmark a single simple expression and extrapolate results to all expressions. Build a workload suite reflecting the types of expressions the application actually uses.

| Expression Group | Example | Characteristics to Measure |
|---|---|---|
| Property access | \`customer.address.city\` | Property depth, accessors |
| Method invocation | \`customer.calculate(#amount)\` | MethodResolver, arguments |
| Variable lookup | \`#minimum\` | Variable lookup |
| Arithmetic | \`price * #quantity\` | Operators, numeric types |
| Conversion | Assigning String to numeric property | TypeConverter, converters |
| Selection | \`#items.?[active]\` | Element count, predicate |
| Projection | \`#items.![name]\` | Element count, result objects |
| Template | \`"Total: #{#total}"\` | Segment count and String creation |
| Null-safe access | \`#customer?.address?.city\` | Null and non-null branches |
| Custom accessor/resolver | Domain-specific access | Extension cost |

For selection and projection, vary input element counts. An expression running on 5 elements can have very different performance characteristics from the same expression running on 5,000 elements.

Also measure both normal data and boundary data such as empty collections, null properties, long strings, or cases with no matching elements.

## 8. Measuring Latency Distribution Instead of Just Average

JMH supports multiple benchmark modes. Choose the mode suited to your question:

- \`Mode.AverageTime\`: average time per operation.
- \`Mode.Throughput\`: operations per unit of time.
- \`Mode.SampleTime\`: samples individual operation times to observe latency distribution.
- \`Mode.SingleShotTime\`: measures single cold invocations, useful for certain cold-start cases but not a replacement for steady-state benchmarks.

Example choosing SampleTime:

~~~java
@BenchmarkMode(Mode.SampleTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 10)
@Fork(3)
public class SpelLatencyBenchmark {
    // State and benchmark method.
}
~~~

SampleTime output can provide percentiles and histograms according to JMH configuration. In production, use metrics or histograms from your observability system to track p50, p95, and p99 over time windows.

Do not compare percentiles from two runs if background load, machine configuration, or sampling settings differ significantly.

## 9. Measuring Throughput at Multiple Concurrency Levels

A single-threaded benchmark shows individual cost but does not fully capture behavior when multiple requests evaluate expressions concurrently.

You can use JMH with \`Scope.Thread\` so each thread has its own state, then vary the thread count when running. For example:

~~~bash
java -jar target/benchmarks.jar SpelEvaluationBenchmark -t 1
java -jar target/benchmarks.jar SpelEvaluationBenchmark -t 4
java -jar target/benchmarks.jar SpelEvaluationBenchmark -t 8
~~~

Observe:

- How does throughput scale as threads increase?
- Does p95/p99 latency rise sharply?
- Does CPU reach saturation?
- Do allocation rate and GC increase with load?
- Is there contention on shared objects or caches?

If throughput stops scaling when adding threads, profile to find the limiting resource. Do not conclude SpEL is slow if the actual bottleneck lies in the database, network, locks, or business code called from expressions.

## 10. Measuring Allocation and GC with JMH

JMH includes a GC profiler to observe allocation and garbage collection activity:

~~~bash
java -jar target/benchmarks.jar SpelEvaluationBenchmark -prof gc
~~~

Useful metrics typically include:

- \`gc.alloc.rate\`: allocation rate.
- \`gc.alloc.rate.norm\`: normalized allocation per operation.
- \`gc.count\`: number of GC runs during the measurement window.
- \`gc.time\`: total GC time.

Output names and formats may vary by JMH and profiler version. Read the output header for exact units and meanings.

If bytes/op is high, use Java Flight Recorder (JFR) or an allocation profiler to find which object types are created most. Do not assume all allocations come from SpEL; objects may come from business methods invoked in the expression, converters, loggers, or test data.

## 11. Using Java Flight Recorder and Profilers

JFR records JVM runtime events, useful for observing:

- CPU hot methods.
- Allocations by class.
- Garbage collection and pauses.
- Lock contention.
- Thread scheduling.
- Class loading and JIT compilation.
- Exceptions or runtime events depending on recording configuration.

You can capture a recording during a representative run and open it with Java Mission Control. JFR helps turn the question "this expression is slow" into more concrete questions: which method consumes CPU, which objects are heavily allocated, or which GC pauses affect tail latency.

Profilers must be used deliberately. Profiling has overhead; compare runs with and without profiling to understand tool impact.

## 12. Comparing Interpreted and Compiled Modes Fairly

SpEL has compiler modes:

- \`OFF\`: interpreted execution.
- \`IMMEDIATE\`: requests compiled execution early when possible.
- \`MIXED\`: can switch from interpreted to compiled and back to interpreted when compiled execution is no longer suitable.

Parser configuration:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        SpelCompilerMode.MIXED,
        Product.class.getClassLoader()
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

To compare fairly:

1. Use the same expression and the same input data.
2. Separate parsing time from evaluation.
3. Give the JVM and expression sufficient warm-up.
4. Run multiple forks.
5. Verify the expression can actually be handled by the compiler.
6. Measure latency, throughput, and allocation together.
7. Verify logical results across modes are identical.
8. Test both stable runtime types and changing-type cases if production has both.

Do not measure just the first few calls and conclude compiler mode is faster or slower. Warm-up and compilation costs can make initial results differ from steady-state.

The compiler does not support every expression construct. An expression that evaluates in interpreted mode may not be compilable. MIXED supports fallback, whereas IMMEDIATE must be tested carefully with realistic workloads.

## 13. Measuring Expression Caching as a Separate Change

If an application parses the same string many times, caching Expressions can reduce parsing cost.

A cache should have bounds and an appropriate eviction policy if expression keys can grow unboundedly. If expressions come from fixed configuration, they can be parsed at startup and stored by key.

When benchmarking caching, measure separately:

- Cache hit: looking up and using an already parsed Expression.
- Cache miss: parsing the expression and storing it.
- Synchronization or contention cost when multiple threads miss simultaneously.
- Memory retained by the cache.
- Impact of cache size and eviction.

Do not cache an EvaluationContext containing a request's root object or variables as if it were an immutable Expression. Contexts typically carry runtime data and must have an appropriate lifecycle.

## 14. Measuring End-to-End Spring Flows

Isolated microbenchmarks help pinpoint SpEL costs, but production optimization decisions need confirmation at the application level.

A real flow may include:

~~~text
HTTP request
    |
    v
Controller / service
    |
    v
Create or obtain EvaluationContext
    |
    v
Retrieve Expression from cache
    |
    v
SpEL getValue(...)
    |
    v
Invoke business method / repository
    |
    v
Serialize response
~~~

If only getValue is benchmarked, the remaining steps are excluded. That is useful for isolating SpEL cost, but cannot replace end-to-end request benchmarks.

Use metrics at appropriate boundaries to measure total latency and, if possible, add a separate timer for parsing/evaluation. Comparing the two measurement layers shows what share SpEL accounts for in total request time.

If evaluation only accounts for 1% of latency, even doubling SpEL speed will only have a small impact on total time. Prioritize bottlenecks with greater impact.

## 15. Metrics in Spring Applications

In Spring Boot applications with Micrometer, evaluation time can be recorded with a Timer:

~~~java
@Service
public class RuleEvaluator {

    private final MeterRegistry meterRegistry;
    private final Expression expression;

    public RuleEvaluator(
            MeterRegistry meterRegistry,
            Expression expression) {
        this.meterRegistry = meterRegistry;
        this.expression = expression;
    }

    public Object evaluate(EvaluationContext context) {
        return Timer.builder("spel.evaluation")
            .description("Time spent evaluating SpEL expressions")
            .tag("rule", "order-eligibility")
            .register(meterRegistry)
            .record(() -> expression.getValue(context));
    }
}
~~~

In production, register the Timer once or inject an already registered meter rather than doing repeated lookup/registration on a hot path if that introduces overhead. The example above illustrates the API; a real implementation can hold the Timer in a field.

Keep tag cardinality low. Do not use the full expression string, user ID, order ID, or input data as tags because the number of time series can explode.

You can also track:

- Total number of evaluations.
- Failed evaluations grouped by bounded error categories.
- Latency histograms.
- Cache hit/miss counts if an expression cache is present.
- Throughput per endpoint or rule category.
- GC and JVM metrics from Micrometer.

Do not record sensitive expression contents or variable data in metric labels.

## 16. Designing Benchmarks with Realistic Data

Benchmark data should reflect production distributions:

- Typical collection sizes and large cases.
- Ratio of null properties.
- Ratio of selections yielding no matches.
- String and template lengths.
- Number of variables and property depth.
- Root object types and runtime implementations.
- Frequency of errors and conversion failures if present in the workload.
- Number of evaluations of the same Expression.

If only ideal data is used, benchmarks may miss null-handling branches, exceptions, or large collections that happen frequently in production.

Also avoid benchmarking with only one fixed object if production uses multiple runtime types. The JIT can aggressively optimize for a single type, producing results not representative of the application.

## 17. Controlling Noise Factors

A reliable benchmark requires stable measurement conditions.

Before comparing:

1. Use the same JDK vendor and version.
2. Use the same Spring Framework and dependency versions.
3. Record CPU, core count, RAM, and operating system.
4. Avoid running other heavy tasks on the machine during measurement.
5. Use the same heap and JVM flags.
6. Run multiple forks and iterations.
7. Ensure sufficient warm-up.
8. Avoid logging on the benchmark hot path.
9. Do not allocate unintended test data inside each operation.
10. Use the returned result or a Blackhole to avoid dead-code elimination.

When results fluctuate widely across runs, investigate the cause before picking the most favorable number. Noise can come from CPU frequency scaling, GC, JIT, background tasks, or container configuration.

## 18. Evidence-Based Optimization Workflow

A practical workflow may include:

1. **Define the goal:** e.g., reduce p95 evaluation latency or reduce allocation bytes/op.
2. **Establish a baseline:** measure the current workload with fixed configuration and data.
3. **Separate costs:** parsing, context creation, evaluation, and end-to-end.
4. **Profile:** find actual hot CPU methods, allocations, and GC activity.
5. **Form a hypothesis:** e.g., repeated parsing, excessive context creation, or selection on overly large collections.
6. **Try one change:** cache Expression, reduce intermediate objects, or test compiler mode.
7. **Re-measure:** run the same benchmark and conditions.
8. **Compare:** latency percentiles, throughput, allocation, and correctness.
9. **Verify in production:** roll out with monitoring if the change affects runtime behavior.
10. **Keep or revert:** keep the change only if it improves the goal without degrading other key metrics.

Changing one main factor at a time makes results easier to interpret. If you change compiler mode, caching, context, and expressions simultaneously, it becomes hard to tell which factor made the difference.

## 19. Reading Results and Deciding Whether to Optimize

Example before-and-after benchmark comparison:

| Metric | Before | After | Interpretation |
|---|---:|---:|---|
| p50 latency | 80 µs | 60 µs | Improved typical time |
| p95 latency | 150 µs | 120 µs | Better tail latency |
| Allocation | 1.2 KB/op | 0.8 KB/op | Fewer objects/bytes per call |
| Throughput | 20k ops/s | 25k ops/s | More operations per second |

The numbers in the table only illustrate how to read results, not default SpEL benchmarks.

One change can improve one metric while worsening another. For example, the compiler may raise steady-state throughput while increasing warm-up cost; caching may cut parse time while increasing retained heap; reusing contexts may reduce allocation while creating state-sharing risks if mismanaged.

The final decision must be based on system goals and real workloads, not on a single isolated metric.

## 20. Common Misconceptions

**Misconception 1: Measuring parse and evaluation time together is enough.**  
If optimizing evaluation, pre-parse and measure getValue separately. End-to-end benchmarks are still needed, but they answer a different question.

**Misconception 2: Average latency represents every request.**  
p95 and p99 can be bad even when the average looks good. Inspect the latency distribution.

**Misconception 3: Higher throughput always means a better experience.**  
Tail latency can rise under high load. Examine throughput alongside latency.

**Misconception 4: Less CPU means fewer allocations.**  
CPU time and allocation are separate metrics. Use a GC profiler or JFR to measure allocations.

**Misconception 5: Compiler mode is always faster than interpreted mode.**  
Only eligible expressions and workloads with enough evaluations can benefit; warm-up and compilation have costs.

**Misconception 6: Contexts should be shared to save allocations.**  
Contexts hold mutable roots and variables. Sharing at the wrong scope causes data corruption and concurrency bugs; measure and design lifecycles properly.

**Misconception 7: Microbenchmarks alone are enough for production decisions.**  
JMH isolates costs, while real requests involve controllers, services, databases, serialization, and contention. Confirm at the end-to-end level.

**Misconception 8: Optimizing one simple expression represents all of SpEL.**  
Property access, method calls, selection, projection, templates, and conversions have different cost profiles.

## 21. Key Takeaways

- Measure before optimizing to identify the actual bottleneck.
- Track latency distribution, especially p50, p95, and p99; not just the average.
- Measure allocation bytes/op, allocation rate, and GC to understand memory pressure.
- Measure throughput at multiple concurrency levels and observe saturation points.
- Separate parsing, EvaluationContext creation, and getValue into distinct benchmarks.
- Use JMH with warm-up, measurement iterations, forks, and results protected from dead-code elimination.
- Benchmark representative workloads covering properties, methods, variables, conversions, selection, projection, and templates.
- Compare OFF, IMMEDIATE, and MIXED after warm-up, on the same expressions and data.
- Use the JMH GC profiler, JFR, or an appropriate profiler to locate allocation sources and CPU hot spots.
- Measure both microbenchmarks and end-to-end requests before deciding on optimizations.
- Caching Expressions can reduce parse cost; contexts need lifecycles matching root objects and variables.
- Keep benchmark conditions consistent and change one factor at a time so results remain explainable.
- Only keep an optimization when target metrics improve while correctness and other critical metrics remain acceptable.

When optimizing SpEL, start with a reproducible baseline, separate parse and evaluation costs, measure latency, allocation, and throughput on production-like data, and use a profiler to identify root causes. A change is only worth keeping when post-change measurements prove a benefit on the workload the application actually runs.
