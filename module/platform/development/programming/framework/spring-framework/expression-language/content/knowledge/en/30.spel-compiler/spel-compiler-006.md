# Warm-up performance and compilation cost

SpEL performance does not depend solely on expression complexity. Processing time is also affected by parsing the string, creating an EvaluationContext, evaluating the expression the first time, compiling the expression to bytecode, and the JVM optimizing running code. Measuring only a single `getValue()` call makes it easy to confuse startup cost with steady-state processing cost.

By default, SpEL evaluates expressions using an interpreter. For expressions used repeatedly with stable data types, the SpEL compiler can be enabled to generate bytecode and reduce evaluation cost. However, compilation has its own cost, supports only a subset of expressions, and relies on type information gathered at runtime. Therefore, measure each phase separately and choose a compiler mode based on how the application actually uses expressions.

## 1. Components that make up processing time

A SpEL processing flow typically has these phases:

1. Creating or configuring an ExpressionParser.
2. Parsing the string into an Expression object and internal syntax tree.
3. Preparing the EvaluationContext along with the required root object, variables, and resolvers.
4. Calling getValue() to evaluate the expression.
5. If the compiler is enabled, SpEL may generate bytecode from the expression after one or more interpreted evaluations.
6. The JVM can further optimize frequently executed bytecode using the JVM JIT compiler.

These phases have different costs and lifecycles. Parsing is the work of processing the string and syntax structure. Evaluation is the work of executing the expression on current data. SpEL compilation generates a bytecode class to execute the expression. JVM JIT optimizes bytecode running in the process.

Do not lump everything into a single "SpEL time" number. When an expression is slow, determine whether the time is spent in parsing, context initialization, interpreted evaluation, compilation, or the application's own getter/method logic.

## 2. Parsing an expression and evaluating an expression are two different costs

ExpressionParser converts a SpEL string into an Expression. Parsing should usually be done once when loading configuration or when a rule is created, then the Expression reused across many evaluations.

Example:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
            parser.parseExpression("order.total > 1000");

    for (Order order : orders) {
        Boolean accepted =
                expression.getValue(
                        order, Boolean.class);
    }

In the example, the parser parses only once. Each loop iteration only evaluates the Expression with a different root object.

If parsed inside the loop:

    for (Order order : orders) {
        Expression expression =
                parser.parseExpression("order.total > 1000");

        Boolean accepted =
                expression.getValue(
                        order, Boolean.class);
    }

the application pays repeated parsing costs even though the expression string does not change. When a rule is used many times, this cost can outweigh the savings provided by the compiler.

Parsed Expressions can be cached by content and parser configuration. The cache needs a size limit if expressions are created from dynamic configuration or users; do not keep every string ever seen unboundedly. Cache the Expression, and do not cache an EvaluationContext holding a request's root object or variables by default.

## 3. Interpreter is the default mode

When the compiler is not configured, SpEL evaluates expressions using the interpreter. The interpreter traverses the expression tree and performs operations, property accesses, or method invocations according to the current context.

Example:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
            parser.parseExpression(
                    "customer.address.city");

    String city =
            expression.getValue(order, String.class);

This evaluation approach is flexible and is the default choice. It suits infrequently called expressions, expressions with dynamic structure, or cases where there is no evidence that evaluation cost is a bottleneck.

The interpreter can still run fast for simple expressions. Do not enable the compiler just because an expression has many dots or looks long. Measure on realistic data and load, because the cost of object access, getters, collections, and type conversion can dominate total time.

## 4. What does the SpEL compiler do?

The SpEL compiler converts certain parsed expressions into JVM bytecode. Instead of interpreting the expression tree on every call, the compiled code executes the corresponding operations more directly.

The compiler can reduce evaluation overhead for repeatedly called expressions, especially when property paths and data types are stable. It does not reduce the cost of reading data from a database, making network calls, running expensive getters, or executing business logic inside methods.

SpEL compilation is also not the same as JVM JIT compilation:

- The SpEL compiler takes a SpEL syntax tree and generates bytecode that executes the expression.
- The JVM JIT optimizes application bytecode and generated bytecode at runtime based on the process's actual behavior.

Both mechanisms can occur together. An expression compiled by the SpEL compiler can still be further optimized by the JVM JIT once executed frequently enough.

The compiler does not guarantee every expression can be compiled. Features relying on custom resolvers, dynamic conversion, or unsupported expression structures may continue to need the interpreter. Support scope varies by Spring version; check the version in use and test with the application's actual expressions.

## 5. Three SpelCompilerMode modes

Compiler mode can be selected via SpelParserConfiguration:

- OFF: disables SpEL compilation. This is the default mode.
- IMMEDIATE: SpEL attempts to compile the expression early after the first interpreted evaluation.
- MIXED: the expression starts in interpreted mode; after reaching an internal evaluation threshold, SpEL attempts compilation. If the compiled expression encounters an issue at runtime, MIXED mode can fall back to interpretation.

Example enabling MIXED:

    SpelParserConfiguration configuration =
            new SpelParserConfiguration(
                    SpelCompilerMode.MIXED,
                    MyService.class.getClassLoader());

    ExpressionParser parser =
            new SpelExpressionParser(configuration);

    Expression expression =
            parser.parseExpression(
                    "customer.address.city");

The passed ClassLoader is the loader used to define the generated bytecode class. Use a loader appropriate for the application and deployment lifecycle. If compilation is not needed, keep the default configuration or set OFF explicitly to express intent.

The threshold for switching from interpreter to compiler in MIXED is a Spring implementation detail and should not be treated as a fixed number for designing application logic. Do not write code that depends on the exact number of evaluations before compilation occurs.

## 6. Choosing OFF, IMMEDIATE, or MIXED?

| Mode | Behavior | Suitable when |
|---|---|---|
| OFF | Always evaluates with the interpreter | Expressions are rarely used, dynamic, or do not yet need optimization |
| IMMEDIATE | Attempts to compile after the first interpreted evaluation | Data types and expression structure are stable and controlled |
| MIXED | Starts with the interpreter, then tries compiling; can fall back to the interpreter if the compiled expression fails | Rules used repeatedly where runtime data may change types |

OFF is a safe baseline for measurement and a reasonable choice if compilation provides no clear benefit.

IMMEDIATE can be useful for rules with stable data types, such as an expression reading a fixed-structure DTO. Because compilation happens early, startup or the first request may incur extra cost.

MIXED is useful when you want SpEL to switch automatically between interpretation and compilation. However, the ability to fall back to the interpreter does not eliminate the need to test data types. If types change constantly, the compiler may not deliver stable benefits.

## 7. Example configuring a parser with the compiler

A parser using IMMEDIATE can be created:

    SpelParserConfiguration configuration =
            new SpelParserConfiguration(
                    SpelCompilerMode.IMMEDIATE,
                    OrderRuleService.class.getClassLoader());

    ExpressionParser parser =
            new SpelExpressionParser(configuration);

    Expression expression =
            parser.parseExpression(
                    "total >= minimumTotal");

    Boolean result =
            expression.getValue(
                    orderRuleInput, Boolean.class);

Or a parser using MIXED:

    SpelParserConfiguration configuration =
            new SpelParserConfiguration(
                    SpelCompilerMode.MIXED,
                    OrderRuleService.class.getClassLoader());

    ExpressionParser parser =
            new SpelExpressionParser(configuration);

The compiler configuration applies to expressions parsed by that parser. If an application has multiple rule groups, separate parsers/configurations can be used per group instead of changing global mode or creating a new parser per request.

Do not create a new parser and SpelParserConfiguration on every `getValue()` call. Create the parser according to the application lifecycle or configuration group, parse rules when loading, and reuse the Expression.

## 8. What is warm-up?

Warm-up is the phase of bringing an execution path into a state close to steady-state operation before measuring or serving real load. With SpEL, warm-up may include:

- Loading configuration and parsing the needed expressions.
- Trial evaluations with the interpreter.
- Giving the SpEL compiler an opportunity to compile if the mode is enabled.
- Additional executions so the JVM JIT has an opportunity to optimize the code.
- Preparing caches or dependent data accessed by the expression.

Warm-up does not mean calling `getValue()` just once. The first call may incur class initialization, class loading, context creation, expression parsing, or compilation costs. The JVM JIT also needs time to observe the execution path before optimizing.

If the system is sensitive to first-request latency, a known set of expressions can be loaded and warmed up during startup. Warm-up must use safe test data and must not cause side effects.

## 9. Separating cold-start latency and steady-state latency

Cold-start latency is the latency during the initial phase, before the parser, expressions, classes, or compiler have been used. Steady-state latency is the latency after the system has initialized and executed enough times.

The two numbers answer different questions:

- Does the first user after deployment have to wait long?
- Once the system is running steadily, how much does each expression evaluation cost?

A compiler mode can increase initial cost while lowering cost for subsequent evaluations. For an expression run only a few times, total cost may be higher than OFF mode. For an expression run millions of times with stable types, compilation cost can be recouped.

When reporting performance, record parse time, first evaluation time, compilation time if observable, and post-warm-up latency distribution separately. Do not just take the average across all calls, as it hides the startup phase and latency tails.

## 10. Compilation cost and break-even point

Compiling an expression consumes CPU and memory. SpEL must generate bytecode, define classes, and potentially perform extra work when runtime types change. Therefore, compilation only pays off when overhead saved across later evaluations is enough to offset initial costs.

This can be described simply:

    Total cost =
        parse cost
        + evaluation cost
        + compilation cost
        + later compiled evaluation cost

With OFF, the compilation cost part is zero, though each evaluation continues using the interpreter.

With IMMEDIATE or MIXED, compilation cost may be incurred; in return, later evaluations can be cheaper if the expression is supported and types are stable.

The break-even point depends on the expression, data, call count, Spring version, JVM, and hardware. There is no universal call count that fits every application. Measure total cost over a realistic operating window rather than comparing just one compiled call against one interpreted call.

## 11. Stable data types affect compilation

The SpEL compiler uses type information gathered during evaluation to generate code. If a property initially returns String but later returns an incompatible type, the compiled code may no longer be suitable.

Example of an expression reading:

    customer.address.city

If customer always has the same type, address always has a concrete type, and city is always String, the compiler can generate more efficient code. If the object graph changes types per request or properties have widely varying runtime types, compilation may fail or the compiled expression may not run with new data.

Items to control:

- Use DTOs and stable property types for compiled rules.
- Avoid changing getter return types across evaluations.
- Avoid reusing one expression with multiple root objects that do not share the same structure.
- Test with boundary values and real runtime types.
- Choose MIXED if fallback to the interpreter is needed when the compiled expression is no longer suitable.

MIXED increases tolerance for type changes compared to IMMEDIATE, but does not replace designing clear data type contracts.

## 12. Limitations of the SpEL compiler

The SpEL compiler does not support the entire SpEL language. Some expressions cannot be compiled due to structure, custom resolvers, type conversion, or dynamic features that the compiler cannot represent safely.

Scenarios to inspect carefully include:

- Selection and projection on collections.
- Conversions relying on ConversionService.
- Methods or properties handled by custom resolvers/accessors.
- Expressions whose runtime types change across evaluations.
- Dynamic structures depending on data or unstable object graphs.

These are examples to check, not an exhaustive list or a guarantee that every Spring version has the same limitations. Check the documentation and source code of the exact Spring version the application uses.

If an expression cannot be compiled, the application must continue working properly with the interpreter or use an appropriate compiler mode. Do not design business logic around the assumption that every expression will compile successfully.

## 13. Parser, Expression, and EvaluationContext should have different lifecycles

A common pattern is:

- Parser/configuration: created per application lifecycle or per rule group.
- Expression: parsed once and cached per rule.
- EvaluationContext: created or prepared per evaluation, with the request's root object and variables.
- Root object: contains only the data needed for the current rule.

Example:

    public class RuleEvaluator {

        private final Expression expression;

        public RuleEvaluator() {
            SpelParserConfiguration config =
                    new SpelParserConfiguration(
                            SpelCompilerMode.MIXED,
                            getClass().getClassLoader());

            ExpressionParser parser =
                    new SpelExpressionParser(config);

            this.expression =
                    parser.parseExpression(
                            "total >= #minimumTotal");
        }

        public boolean evaluate(
                OrderRuleInput input,
                BigDecimal minimumTotal) {

            StandardEvaluationContext context =
                    new StandardEvaluationContext(input);

            context.setVariable(
                    "minimumTotal", minimumTotal);

            return Boolean.TRUE.equals(
                    expression.getValue(
                            context, Boolean.class));
        }
    }

The example illustrates reusing the Expression and creating a context per call. In real applications, choose a context type and resolvers matching the permissions the rule needs. Do not share a mutable context across concurrent requests if each request updates the root or variables.

## 14. Designing safe warm-up

If you want to warm up expressions during startup, identify the list of required rules and prepare representative test data.

A workflow may include:

1. Load configured rules and validate syntax.
2. Parse each rule using the parser/configuration that will be used at runtime.
3. Evaluate with read-only fixtures having matching data types.
4. If the compiler is enabled, pass the expression through enough evaluations for the selected mode to attempt compilation.
5. Record parse errors, evaluate errors, or compilation errors per rule.
6. Only place valid rules into the registry serving requests.

Do not use real orders, shared mutable objects, or data that could trigger sending emails, writing to a database, or changing state for warm-up. If an expression has functions or getters with side effects, warm-up may perform unintended actions.

With MIXED, do not hard-code the warm-up count based on Spring's internal threshold. It can be executed several times on safe fixtures, but verify the actual behavior of the framework version and do not treat calling N times as conclusive proof that the expression has compiled.

## 15. Measuring performance properly

Benchmarks need to separate scenarios for meaningful results:

- Parse-only: measure the cost of creating an Expression from a string.
- Evaluate interpreted: use an OFF parser and a pre-parsed Expression.
- Evaluate compiled: use IMMEDIATE or MIXED, warm up appropriately, then measure steady state.
- End-to-end: include fetching data, creating context, evaluating, and operations the request actually performs.

Use JMH for Java microbenchmarks instead of writing simple loops with System.nanoTime(). JMH handles warm-up iterations, measurement iterations, JVM forks, and reduces skew from JIT, dead-code elimination, or constant folding.

Some principles:

- Use the same input data and expression logic when comparing modes.
- Do not include parse cost on one side while omitting it from the other.
- Consume results via Blackhole or use the results to prevent the JVM from eliminating work.
- Use multiple forks and report percentiles or distributions, not just a single average.
- Measure both throughput and latency if the system needs both.
- Benchmark with object graphs and data types like production.
- Measure simple expressions separately from expressions with expensive getters/methods.
- Do not run benchmarks while CPU or other systems are causing interference without recording conditions.

If an expression takes only a tiny fraction of request time, a microbenchmark may show large improvement while end-to-end impact is negligible. Check both levels.

## 16. Observing in production

When deploying the compiler, monitor relevant metrics:

- Number of expressions parsed and repeated parse counts.
- Evaluation count and latency per rule group.
- Parse/evaluate error rate.
- Proportion of rules used frequently enough to have a chance to compile.
- Errors when compiled expressions run with runtime data.
- CPU, allocation, and startup time after changing compiler mode.

Do not log full expressions or root data if they contain sensitive information. Use rule IDs or controlled configuration names to tag metrics.

Java Flight Recorder, profilers, or tracing can be used to identify whether time is spent in the parser, SpEL, getters, business methods, or external systems. Do not blame high latency on the interpreter before measuring.

If possible, roll out compiler mode changes by rule group or environment, compare against the OFF baseline, and keep the ability to revert to the old configuration if errors or latency increase.

## 17. Common errors and misconceptions

| Situation | Cause | Resolution |
|---|---|---|
| Enabled compiler but see no improvement | Expression is rarely called or expensive part is in getters/I/O | Measure call counts and profile the full flow |
| First request is slower | Parsing, class loading, or compilation happens at startup/first call | Load rules and warm up safely before taking traffic |
| Expression cannot be compiled | Structure lies outside the compiler-supported subset | Use the interpreter or rewrite the rule suitably |
| Compiled expression fails on new data | Runtime types changed compared to compile time | Stabilize DTO/types or use MIXED |
| Benchmark gives erratic results | Mixed parsing, warm-up, JIT, and evaluation | Separate phases and use JMH |
| Re-parsing on every request | Not reusing Expression | Cache Expression per rule |
| Cache grows unboundedly | Dynamic expressions generate many keys | Use a bounded cache with an eviction policy |
| Warm-up mutates data | Functions/getters have side effects | Use safe fixtures and pure expressions |
| Sharing EvaluationContext across requests | Mutable context holds root/variables | Create context per evaluation |

## Conclusion

SpEL uses the interpreter by default. The compiler can be enabled with OFF, IMMEDIATE, or MIXED through SpelParserConfiguration, but benefits only appear when expressions are used frequently enough, supported by the compiler, and have stable runtime types. Compilation has CPU, memory, and initial latency costs; it does not eliminate parsing, I/O, or getter logic costs.

Parse and cache Expressions rather than parsing per request, separate cold-start from steady-state, warm up with safe data, benchmark with JMH, and monitor latency and errors in production. Choose compiler mode based on measurements of the actual rules and Spring version running; keep OFF when compilation produces no real benefit.