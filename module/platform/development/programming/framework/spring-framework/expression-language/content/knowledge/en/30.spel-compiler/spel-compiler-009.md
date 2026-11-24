# Equivalence testing between interpreted and compiled expressions in SpEL

Spring Expression Language (SpEL) can evaluate expressions in two ways: interpreted, where the engine analyzes and executes the expression structure at runtime, and compiled, where SpEL generates bytecode for faster execution of supported expressions. The compiler can improve performance when an expression is evaluated repeatedly many times, but enabling the compiler does not automatically guarantee that every expression is compiled or that both execution paths always fit all dynamic data types.

Equivalence testing aims to confirm that the same expression, same input data, and same business context produce equivalent results when run in interpreted and compiled modes. This is especially important when expressions depend on runtime types, nested properties, method invocations, collections, or objects with mutable state.

## 1. Objectives and prerequisites

After this lesson, you will be able to:

- Distinguish interpreted evaluation from compiled evaluation.
- Configure the SpEL compiler using SpelParserConfiguration and SpelCompilerMode.
- Understand OFF, IMMEDIATE, and MIXED modes.
- Identify which expressions the compiler can support and which cases remain interpreted.
- Design tests running the same expression on identical data across multiple modes.
- Compare values, result types, exceptions, and business behavior.
- Test with multiple runtime types and boundary data.
- Detect differences caused by type assumptions, overloads, nulls, or mutable objects.
- Measure performance properly without confusing benchmarking with correctness testing.

You should know how to create SpelExpressionParser, Expression, EvaluationContext, and how SpEL accesses properties, calls methods, handles collections, and converts types.

## 2. Interpreted and compiled evaluation

In interpreted mode, SpEL executes the expression through its evaluation engine. This is a flexible mode suited to many expression structures and data with changing runtime types.

In compiled mode, SpEL can generate bytecode for expressions within the supported syntax subset. Bytecode reduces repeated interpretation overhead and can improve throughput when the same expression is evaluated many times.

Key distinctions:

| Aspect | Interpreted | Compiled |
|---|---|---|
| Execution method | Engine interprets the expression | Bytecode generated for supported expressions |
| Runtime type flexibility | More flexible with varying types | May rely on types observed during evaluation |
| Syntax support scope | Broader | Supports only a subset |
| Performance | Interpretation cost per call | Can be faster when run repeatedly |
| When uncompilable | Can still run interpreted | May continue interpreted depending on mode and expression |

The compiler is an execution optimization. It does not change the business intent of an expression and does not replace logic testing.

## 3. Configuring the SpEL compiler

The compiler is configured through SpelParserConfiguration. There are three main modes in SpelCompilerMode:

- OFF: disables the compiler; expressions are executed in interpreted mode.
- IMMEDIATE: SpEL attempts to compile the expression early once the necessary evaluation information is available. If the compiled path encounters an error because type assumptions no longer hold, the error can be surfaced to the caller.
- MIXED: SpEL can switch back to interpreted evaluation when the compiled path encounters an error, adapting better to certain runtime type changes.

Example creating a parser in OFF mode:

~~~java
SpelParserConfiguration offConfiguration =
    new SpelParserConfiguration(
        SpelCompilerMode.OFF,
        getClass().getClassLoader()
    );

ExpressionParser interpretedParser =
    new SpelExpressionParser(offConfiguration);
~~~

Example creating a parser in IMMEDIATE mode:

~~~java
SpelParserConfiguration immediateConfiguration =
    new SpelParserConfiguration(
        SpelCompilerMode.IMMEDIATE,
        getClass().getClassLoader()
    );

ExpressionParser compiledParser =
    new SpelExpressionParser(immediateConfiguration);
~~~

Example of MIXED mode:

~~~java
SpelParserConfiguration mixedConfiguration =
    new SpelParserConfiguration(
        SpelCompilerMode.MIXED,
        getClass().getClassLoader()
    );

ExpressionParser mixedParser =
    new SpelExpressionParser(mixedConfiguration);
~~~

The application's class loader can be used so the compiler generates and loads classes in an appropriate environment. In applications with custom class loaders, plugins, or separate modules, configure and test with the actual class loader.

Do not enable the compiler across the entire application just because one benchmarked expression runs faster. Measure on real workloads and confirm equivalence before deploying.

## 4. Creating two parsers for comparison

A clear testing approach is to create separate parsers for interpreted and compiled modes, then parse the exact same expression source.

~~~java
String source = "#order.total * #taxRate";

ExpressionParser interpretedParser =
    new SpelExpressionParser(
        new SpelParserConfiguration(
            SpelCompilerMode.OFF,
            getClass().getClassLoader()
        )
    );

ExpressionParser compiledParser =
    new SpelExpressionParser(
        new SpelParserConfiguration(
            SpelCompilerMode.IMMEDIATE,
            getClass().getClassLoader()
        )
    );

Expression interpretedExpression =
    interpretedParser.parseExpression(source);

Expression compiledExpression =
    compiledParser.parseExpression(source);
~~~

Using the same source eliminates differences caused by accidentally writing two non-identical expressions. Do not reuse an Expression parsed by an OFF parser to conclude that a compiled parser works as expected; each parser should parse its own source with its corresponding configuration.

A test should keep constant:

- Expression source.
- Root object and variables.
- EvaluationContext capabilities.
- TypeConverter and property/method accessors.
- Input data.
- Object state before each evaluation.

## 5. Comparing results with the same input

Example expression calculating total after tax:

~~~java
String source = "#subtotal * (1 + #taxRate)";

Expression interpreted =
    interpretedParser.parseExpression(source);

Expression compiled =
    compiledParser.parseExpression(source);

StandardEvaluationContext contextA =
    new StandardEvaluationContext();

contextA.setVariable("subtotal", new BigDecimal("100.00"));
contextA.setVariable("taxRate", new BigDecimal("0.10"));

StandardEvaluationContext contextB =
    new StandardEvaluationContext();

contextB.setVariable("subtotal", new BigDecimal("100.00"));
contextB.setVariable("taxRate", new BigDecimal("0.10"));

Object interpretedResult = interpreted.getValue(contextA);
Object compiledResult = compiled.getValue(contextB);
~~~

Two independent contexts with identical data prevent the first evaluation from mutating variables or objects used by the second evaluation.

With BigDecimal, do not compare only string representations if scales might differ. Use comparison rules suited to the domain, such as compareTo if the business cares about numeric value without requiring identical scale.

If the result type is a DTO or collection, compare contents according to the data contract, not only object identity.

## 6. Checking result types, not just display values

Two results can print the same string while having different runtime types. For example, Integer 10 and Long 10 both display as 10, yet consuming code may handle them differently.

An equivalence test should check:

- Whether the result is null.
- Whether the runtime type matches the contract.
- Whether values are equal by domain rules.
- Whether a collection has the right element count and required order.
- Whether a Map has the right keys and values.
- Whether nested objects have the required properties.

Example:

~~~java
assertThat(interpretedResult)
    .isInstanceOf(BigDecimal.class);

assertThat(compiledResult)
    .isInstanceOf(BigDecimal.class);

assertThat(((BigDecimal) interpretedResult)
    .compareTo((BigDecimal) compiledResult))
    .isZero();
~~~

If the application requires exact scale, precision, or a specific type, assert those properties separately. Do not let an overly broad comparison hide differences that downstream code depends on.

## 7. Testing expressions with properties and methods

The compiler can support many common property/method expressions, though compilability depends on expression structure and the type information SpEL observes.

Example:

~~~text
#customer.address.city
~~~

Or:

~~~text
#priceCalculator.calculate(#order.total)
~~~

Test with real objects and real contexts. Pay particular attention to:

- Do getters return a stable type?
- Are methods overloaded?
- Do methods return different types depending on data?
- Do proxies change runtime types or invocation paths?
- Are there custom property accessors?
- Do methods have side effects or depend on external state?

When comparing the two modes, methods should be pure and input data must be independent. If a method writes to a database or increments a counter, running twice can produce double effects and invalidate comparing under identical conditions.

## 8. Testing runtime type changes

An important reason interpreted and compiled behave differently is runtime types changing between evaluations.

For example, a variable may sometimes reference Customer and other times reference a different implementation or null. An expression can be optimized by the compiler based on types observed earlier.

Create cases for:

| Evaluation | Type/data | What to verify |
|---|---|---|
| 1 | Object of type A | Result is correct |
| 2 | Object of type A with different value | Result remains correct |
| 3 | Object of type B with the same required contract | Check how the compiler handles the new type |
| 4 | Null value | Null behavior matches the expression |
| 5 | Object missing required property/method | Errors are handled consistently |
| 6 | Collection with different element types | Result or error matches the contract |

If the application has polymorphic data, test every implementation that actually appears in production. Do not test only one sample object and infer that all subclasses/proxies are compatible.

MIXED mode can fall back to interpreted when the compiled path fails, but do not treat that as a reason to skip tests. Observe the behavior and exceptions that the caller actually receives.

## 9. Testing null and safe navigation

Nulls are boundary cases that must be in the test matrix. Example:

~~~text
#customer?.address?.city
~~~

Test at least:

- customer non-null and address non-null.
- customer null.
- customer non-null but address null.
- address present but city null.

If collections are used with projection or selection, test null, empty, and collections containing null elements. The compiler may not support all collection constructs or null-safe syntax in every Spring version; if an expression is not compiled, it may continue interpreted depending on configuration and engine capabilities.

Do not conclude compiled mode is equivalent based on a single fully populated data case. Missing data is often where type assumptions and null behavior reveal differences.

## 10. Testing exceptions and runtime errors

An equivalence test needs to compare error behavior when an expression cannot be evaluated.

Error types to test:

- Nonexistent property or method.
- Unconvertible arguments.
- Method throwing an exception.
- Null receiver at an unprotected position.
- Runtime type changing after the compiler already gathered info.
- Expression not supported by the compiler.
- Class loader unable to load the generated class or involved types.

Do not catch all exceptions and treat two outcomes as equivalent. Identify which error types are permitted under the application contract and which error types indicate an unacceptable discrepancy.

You can write a helper that runs an expression and captures an outcome containing either a result or an exception type. Then compare the two outcomes according to test policy. Do not assert exact exception messages if messages depend on implementation or version; prefer exception class, cause, and observable application behavior.

## 11. Testing expressions not supported by the compiler

The SpEL compiler supports only a subset of expression constructs. When an expression cannot compile, evaluation may continue in interpreted mode depending on configuration and expression state.

Therefore distinguish:

1. The expression runs properly in interpreted mode.
2. Whether the expression is supported by the compiler.
3. Whether the expression is actually executed via bytecode or remains interpreted.
4. Whether the compiled path's results and errors are equivalent to the interpreted path.

A test that merely calls getValue successfully does not prove the expression was compiled. When confirmation that the compiled path is used is needed, use observation/logging or instrumentation mechanisms appropriate for the application's Spring version. Do not infer compiler status just because the parser is configured with IMMEDIATE or MIXED.

For unsupported expressions, fallback behavior should be documented clearly. If performance is the goal, measure only expressions that are actually compiled.

## 12. Using the same EvaluationContext or independent contexts?

In principle, both modes need identical data and identical configuration for a fair comparison. Two independent contexts created from the same factory can be used to avoid side effects and shared mutable variables.

Example:

~~~java
StandardEvaluationContext newContext(Order order, BigDecimal rate) {
    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("order", order);
    context.setVariable("taxRate", rate);

    return context;
}
~~~

Then create a separate context for each evaluation:

~~~java
Object interpretedResult =
    interpreted.getValue(newContext(orderCopyA, rate));

Object compiledResult =
    compiled.getValue(newContext(orderCopyB, rate));
~~~

orderCopyA and orderCopyB must have identical data state. If objects cannot be copied, ensure the expression is read-only and called methods do not mutate objects.

Do not share a mutable context across parallel tests if tests update variables or properties.

## 13. Equivalence checking across multiple datasets

A single dataset is usually not enough. Create test cases representing:

- Normal values.
- Boundary values such as 0, negative numbers, and very large numbers.
- Null values.
- Empty collections and large collections.
- Multiple implementations of the same interface.
- Different numeric types such as Integer, Long, and BigDecimal.
- Strings with valid and invalid formats.
- Proxy objects if the application uses AOP.
- Nested properties with a null level.

Parameterized tests can be used to run the same dataset on both parser modes. For each input, create independent contexts, evaluate, and compare outcomes.

If an expression has side effects, do not run the same object sequentially in both modes and compare results. Remove side effects from the expression or prepare two independent equivalent fixtures.

## 14. JUnit test structure example

The following example illustrates creating parsers for both modes and comparing results of a pure expression:

~~~java
class SpelCompilerEquivalenceTest {

    private ExpressionParser parser(SpelCompilerMode mode) {
        SpelParserConfiguration configuration =
            new SpelParserConfiguration(
                mode,
                getClass().getClassLoader()
            );

        return new SpelExpressionParser(configuration);
    }

    @Test
    void interpretedAndCompiledReturnEquivalentValues() {
        String source = "#subtotal * (1 + #taxRate)";

        Expression interpreted =
            parser(SpelCompilerMode.OFF).parseExpression(source);

        Expression compiled =
            parser(SpelCompilerMode.IMMEDIATE).parseExpression(source);

        StandardEvaluationContext contextA =
            new StandardEvaluationContext();
        contextA.setVariable("subtotal", new BigDecimal("100.00"));
        contextA.setVariable("taxRate", new BigDecimal("0.10"));

        StandardEvaluationContext contextB =
            new StandardEvaluationContext();
        contextB.setVariable("subtotal", new BigDecimal("100.00"));
        contextB.setVariable("taxRate", new BigDecimal("0.10"));

        BigDecimal resultA =
            interpreted.getValue(contextA, BigDecimal.class);

        BigDecimal resultB =
            compiled.getValue(contextB, BigDecimal.class);

        assertThat(resultA.compareTo(resultB)).isZero();
    }
}
~~~

This is a test template for a pure expression. In a real test suite, add more inputs, check result types, nulls, exceptions, and expressions with structures used by the application. If comparing MIXED, also run a parser configured with SpelCompilerMode.MIXED.

## 15. Measuring performance separately from equivalence testing

Correctness and performance are two separate goals.

Equivalence testing answers: do both modes produce matching results and behavior?

Benchmarking answers: for a specific workload, is compiled mode faster?

When measuring performance:

- Parse the expression outside the timed region if the goal is measuring evaluation.
- Warm up the JVM and execution path before taking measurements.
- Use multiple iterations and multiple forks if using JMH.
- Avoid measuring with a single call.
- Use data representative of production.
- Measure both throughput and latency if appropriate.
- Measure context creation cost separately from evaluation cost.
- Check whether the expression actually compiled.
- Monitor allocation and GC if the expression creates many objects.
- Compare on the same JDK, Spring, and class loader versions.

Do not enable the compiler based solely on an overly small microbenchmark. If an expression runs only a few times in the application lifecycle, compilation cost may bring no significant benefit.

## 16. Common errors and troubleshooting

| Symptom | Common cause | Resolution |
|---|---|---|
| Both modes return different results | Runtime type changed or compiled path used a type assumption | Test multiple types and boundary data |
| Expression does not compile | Structure lies outside the supported syntax subset | Accept interpreted or simplify the expression if reasonable |
| IMMEDIATE throws an error when type changes | Compiled expression no longer matches new data | Use stable types or consider MIXED if fallback is appropriate |
| MIXED runs but performance is unstable | Expression continuously switches between compiled and interpreted | Check polymorphic data, type stability, and logs |
| Test passes but unsure if compiled | Successful getValue does not prove bytecode was used | Use version-appropriate logging/instrumentation |
| Comparison results are untrustworthy | Both evaluations used mutated objects/contexts | Use independent fixtures and contexts with identical state |
| Exceptions differ | Two execution paths fail at different layers | Compare exception types and application contract |
| Compiled mode is not faster | Expression rarely repeats, didn't compile, or other costs dominate | Benchmark real workloads before enabling |
| Class loader error | Generated class or involved types were not loaded properly | Check class loader and deployment environment |

## 17. Practice exercises

1. Create OFF and IMMEDIATE parsers; run the same arithmetic expression on the same dataset.
2. Compare runtime types and result values, not just display strings.
3. Add a MIXED parser and rerun the test suite.
4. Test expressions reading nested properties and method invocations.
5. Try variables of types Integer, Long, and BigDecimal.
6. Try null receivers, null properties, and empty collections.
7. Create an expression unsupported by the compiler and determine how it continues interpreted.
8. Try changing object types between evaluations to observe differences between IMMEDIATE and MIXED.
9. Write parameterized tests with normal, boundary, and invalid data.
10. Use JMH to benchmark a pure expression evaluated many times.
11. Confirm the benchmark excludes parsing or context setup if those are not the costs being measured.
12. Run tests with the application's actual class loader.

## 18. Checklist before enabling compiled mode

- [ ] Have expressions evaluated frequently enough to benefit been identified?
- [ ] Has the exact same source been tested on OFF and compiled mode?
- [ ] Are input data and EvaluationContext equivalent?
- [ ] Have runtime types and result types been checked?
- [ ] Have multiple implementations, overloads, and proxies been tested?
- [ ] Have nulls, empty collections, and boundary data been tested?
- [ ] Have exceptions and error behaviors been compared?
- [ ] Is it known whether the expression is actually supported by the compiler?
- [ ] Are fallback differences between IMMEDIATE and MIXED understood?
- [ ] Does the expression have side effects making double-run tests unsafe?
- [ ] Has the production class loader been verified?
- [ ] Does the benchmark include warm-up and representative workloads?
- [ ] Do benchmark results prove real-world benefit?
- [ ] Can OFF be kept for unsuitable expressions?

## 19. Conclusion

Interpreted evaluation is flexible and supports a wide range of expressions; compiled evaluation can improve speed for supported expressions when evaluated repeatedly. SpelParserConfiguration lets you choose OFF, IMMEDIATE, or MIXED, though configuring the compiler does not prove an expression was compiled. Parse the same source across modes, use equivalent contexts and data, verify values, types, exceptions, and runtime type-change cases. Decide to enable the compiler only after testing correctness and benchmarking on the application's real workloads.