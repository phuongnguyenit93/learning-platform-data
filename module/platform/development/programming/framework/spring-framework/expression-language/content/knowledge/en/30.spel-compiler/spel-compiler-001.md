# What is the SpEL expression compiler?

## 1. Overview of the SpEL compiler

Spring Expression Language (SpEL) normally evaluates expressions using an interpreter. The interpreter reads the expression structure and executes each node when `getValue()` is called. This approach is flexible because SpEL can handle dynamic objects and data types at runtime, but repeated interpretation can incur overhead when the same expression is evaluated very many times.

The SpEL compiler is an optional mechanism that generates Java bytecode from an expression so that subsequent evaluations run faster. Instead of walking through the entire interpreter on every call, SpEL uses the generated class to perform the expression's behavior.

The compiler is best suited when:

- An expression is evaluated repeatedly in a performance-sensitive path.
- The types of properties and intermediate values remain stable across evaluations.
- The expression belongs to the subset of syntax supported by the compiler.
- The initialization/compilation cost is offset by the number of subsequent evaluations.

The compiler is not enabled by default. Simple expressions or those evaluated only occasionally usually do not need compilation.

## 2. Interpreter and compiled expression

When an expression runs in interpreted mode, SpEL evaluates the syntax tree (AST) using interpreter nodes. During that process, the framework can learn additional runtime information such as the actual type of a property or the type of an intermediate result.

The compiler uses the information gathered from interpreted evaluations to generate bytecode for the expression. This matters because SpEL expressions do not declare full static types like Java does. For example:

```text
payload.customer.address.city
```

Just by looking at the expression, the compiler does not necessarily know the runtime type of `payload`, `customer`, or `address`. After the expression is evaluated in interpreted mode with a real object, SpEL can record the required types to generate bytecode.

An example expression with array access, multiple properties, and a numeric operation:

```text
someArray[0].someProperty.someOtherProperty < 0.1
```

If this expression is evaluated very many times on objects with a stable structure, the compiler can reduce interpretation overhead. The Spring Reference gives an illustrative microbenchmark in which 50,000 evaluations take about 75 ms in the interpreter and 3 ms in compiled form. This is only the result of a specific benchmark example, not a speed guarantee for every expression or application.

## 3. Why must data types be stable?

The compiler relies on the types it observes while the expression runs in interpreted mode. If subsequent evaluations receive objects of different types, the compiled code may no longer be suitable.

For example, a property initially always returns a String:

```java
public class Message {
    private String payload;

    public String getPayload() {
        return payload;
    }
}
```

Expression:

```text
payload.toUpperCase()
```

After the first evaluation, the compiler can generate code based on `payload` being a String. If another object or a later evaluation provides an incompatible type, the compiled expression may fail.

Therefore:

- Use the compiler for expressions with stable structure and data types.
- Avoid compiled mode when the same expression is evaluated on objects whose property types vary from call to call.
- Test null cases and different runtime types.
- If data types change frequently, keep interpreted mode or consider MIXED mode depending on side effects.

## 4. Three SpelCompilerMode modes

The SpEL compiler has three modes in the `org.springframework.expression.spel.SpelCompilerMode` enum:

| Mode | Behavior |
|---|---|
| `OFF` | Disables the compiler; all expressions run interpreted. This is the default. |
| `IMMEDIATE` | Compiles expressions as soon as possible, usually after the first interpreted evaluation. If the compiled expression fails, the exception is propagated to the caller. |
| `MIXED` | Automatically switches between interpreted and compiled over time. If the compiled expression fails, SpEL catches the error internally and falls back to interpreted mode; it may later attempt to recompile. |

### 4.1. OFF

Use OFF when:

- The expression only runs occasionally.
- Maximum flexibility is needed for objects with changing types.
- The expression uses syntax not yet supported by the compiler.
- There is no measurement evidence showing that the compiler brings a benefit.

```java
SpelParserConfiguration config =
        SpelParserConfiguration.builder()
                .compilerMode(SpelCompilerMode.OFF)
                .build();

SpelExpressionParser parser =
        new SpelExpressionParser(config);
```

OFF is also the default choice if no compiler mode is configured.

### 4.2. IMMEDIATE

IMMEDIATE compiles the expression early, usually after the first interpreted evaluation. If the compiled expression encounters an error, the error is propagated to the caller.

```java
SpelParserConfiguration config =
        SpelParserConfiguration.builder()
                .compilerMode(SpelCompilerMode.IMMEDIATE)
                .compilerClassLoader(getClass().getClassLoader())
                .build();

SpelExpressionParser parser =
        new SpelExpressionParser(config);

Expression expression = parser.parseExpression("payload");

Object result = expression.getValue(message);
```

Choose IMMEDIATE when data types are stable and the application wants to receive an error immediately if the compiled expression is no longer suitable. Do not use IMMEDIATE just to force every expression to compile; the compiler still does not support all syntax.

### 4.3. MIXED

MIXED switches automatically between the two evaluation approaches. After a number of successful interpreted runs, the expression can be compiled. If the compiled form fails, SpEL falls back to interpreted mode instead of propagating that compilation/evaluation error to the caller the way IMMEDIATE does. Afterward, the framework may try to compile again; if errors repeat too many times, the expression may be kept in interpreted mode.

MIXED is useful when data types occasionally change and the application wants the expression to continue being evaluated. However, there is an important caveat regarding side effects: the compiled expression may already have executed part of an operation before the error occurred. If MIXED automatically re-runs the expression in interpreted mode, part of the behavior may be executed a second time.

Therefore, do not rely on MIXED for expressions with important side effects, such as writing data, calling external services, or performing non-idempotent state changes.

## 5. Configuring the compiler with SpelParserConfiguration

The most direct way to enable the compiler is to configure `SpelParserConfiguration` and create a `SpelExpressionParser` from that configuration:

```java
SpelParserConfiguration config =
        SpelParserConfiguration.builder()
                .compilerMode(SpelCompilerMode.IMMEDIATE)
                .compilerClassLoader(getClass().getClassLoader())
                .build();

SpelExpressionParser parser =
        new SpelExpressionParser(config);

Expression expression =
        parser.parseExpression("payload.customer.name");

String name = expression.getValue(message, String.class);
```

Important parts:

- `compilerMode(...)` selects OFF, IMMEDIATE, or MIXED.
- `compilerClassLoader(...)` specifies the ClassLoader used as the parent to define the compiled expression.
- A parser created from the configuration applies the compiler mode to the expressions that the parser parses.

In Spring versions that have the corresponding constructor API, it can be configured using the `SpelParserConfiguration` constructor:

```java
SpelParserConfiguration config =
        new SpelParserConfiguration(
                SpelCompilerMode.IMMEDIATE,
                getClass().getClassLoader());
```

Use the API appropriate for the application's Spring Framework version; the builder and overloads can differ across versions.

## 6. Configuring the compiler via system property

When SpEL is embedded in another component and the application does not create the parser directly, the compiler mode can be configured via a property:

```properties
spring.expression.compiler.mode=immediate
```

Or via a JVM system property:

```text
-Dspring.expression.compiler.mode=immediate
```

The valid values corresponding to the enum are:

```text
off
immediate
mixed
```

Spring also supports setting this through the `SpringProperties` mechanism. This property is useful for components that create parsers internally, though its scope of impact can be broader than an individually configured parser. Consider the impact on every expression in the process before enabling a global mode.

If the application controls the parser, configuring it individually with `SpelParserConfiguration` is usually easier to scope.

## 7. ClassLoader of a compiled expression

The SpEL compiler generates Java classes at runtime. Compiled classes are defined in a child ClassLoader created beneath the supplied ClassLoader.

If a ClassLoader is specified, it must be able to see all types involved in expression evaluation, including:

- The type of the root object.
- The types of accessed properties.
- Method parameter and return types.
- Intermediate types in operations.

Example:

```java
ClassLoader applicationClassLoader =
        Order.class.getClassLoader();

SpelParserConfiguration config =
        SpelParserConfiguration.builder()
                .compilerMode(SpelCompilerMode.MIXED)
                .compilerClassLoader(applicationClassLoader)
                .build();
```

If no ClassLoader is specified, SpEL uses a default ClassLoader, typically the thread context ClassLoader at the time of expression evaluation.

In applications with plugins, application servers, or multiple ClassLoaders, choosing the wrong ClassLoader can prevent the compiled expression from accessing the required types. When encountering class-loading-related errors, check the ClassLoader of the root object and intermediate types before changing the expression.

## 8. Expression types not supported by the compiler

The SpEL compiler cannot compile every kind of expression. The following categories are not supported in current Spring documentation:

- Expressions with assignment.
- Expressions relying on ConversionService.
- Expressions using custom resolvers.
- Expressions using overloaded operators.
- Expressions using Optional together with the null-safe operator or Elvis operator.
- Expressions using array creation syntax.
- Expressions using collection selection or projection.
- Expressions using bean references.

Examples of forms that must remain interpreted:

```text
name = 'Ada'
items.?[active]
items.![name]
@pricingService.currentRate
```

For unsupported expressions, do not assume that enabling compiler mode will automatically turn that expression into compiled bytecode. Uncompilable expressions still need to be handled under an appropriate interpreted mechanism.

The support list may change across Spring versions. Check the documentation for the version in use before designing a system that depends on compiled expressions.

## 9. Checking whether an expression is compiled

Do not infer that an expression is compiled just because the parser is configured with IMMEDIATE or MIXED. The compiler might not support the expression's syntax, might lack type information, or might fail to compile.

When checking in tests or diagnostics is needed, the specific API on `SpelExpression` can be used:

```java
SpelExpression expression =
        (SpelExpression) parser.parseExpression("payload");

Object first = expression.getValue(message);

// For a supported expression and appropriate configuration,
// the compiled state can be checked:
boolean compiled = expression.isCompiled();
```

`isCompiled()` is an API detail of the `SpelExpression` implementation, not a method on the general `Expression` interface. If code only holds the Expression type, an appropriate cast is needed or observation via diagnostic tools of the version in use.

Do not use compiled status as a business condition. It is meant for diagnostics and performance optimization; the correct result of the expression is what the application needs to guarantee.

## 10. Measuring performance before and after enabling the compiler

The compiler aims to reduce repeated evaluation overhead. However, compilation has initialization cost and not every expression can be compiled.

When measuring, separate:

1. Expression parsing time.
2. Cost of initial interpreted evaluations.
3. Compilation cost.
4. Evaluation time once compiled.
5. Impact of real objects, invocation count, and concurrency.

A microbenchmark should run sufficient warm-up, use the same input data and the same expression, and compare OFF against IMMEDIATE/MIXED. Do not compare a single interpreted call against a single compiled call and draw conclusions.

Simple benchmark structure example:

```java
ExpressionParser interpretedParser =
        new SpelExpressionParser(
                SpelParserConfiguration.builder()
                        .compilerMode(SpelCompilerMode.OFF)
                        .build());

ExpressionParser compiledParser =
        new SpelExpressionParser(
                SpelParserConfiguration.builder()
                        .compilerMode(SpelCompilerMode.IMMEDIATE)
                        .build());

Expression interpreted =
        interpretedParser.parseExpression("payload.amount * 1.08");

Expression compiled =
        compiledParser.parseExpression("payload.amount * 1.08");

// Warm up and measure repeatedly with the same set of messages.
```

In real applications, use JMH or an appropriate benchmark tool to avoid skew from JIT, GC, class loading, and warm-up. If an expression runs only a few times, compilation cost can outweigh the benefit.

## 11. Security note: SimpleEvaluationContext and CVE-2026-59283

`SimpleEvaluationContext` is designed to restrict certain SpEL capabilities. However, Spring published CVE-2026-59283 on August 20, 2026 regarding how the compiler could bypass safety guards of SimpleEvaluationContext in certain configurations.

The relevant conditions include:

- The application evaluates expressions using SimpleEvaluationContext.
- The SpEL compiler is enabled with `IMMEDIATE` or `MIXED`, either via `SpelParserConfiguration` or the `spring.expression.compiler.mode` property.

In affected versions, expressions could be silently compiled even when using SimpleEvaluationContext. Subsequent compiled evaluations could bypass safety guards that are enforced in interpreted mode. The advisory also notes the potential for unbounded growth in loaded classes caused by different expressions generating classes in the child ClassLoader.

Spring published the affected versions:

| Release line | Affected range |
|---|---|
| 7.0 | 7.0.0 to 7.0.8 |
| 6.2 | 6.2.0 to 6.2.19 |
| 6.1 | 6.1.0 to 6.1.28 |
| 6.0 | 6.0.0 to 6.0.30 |
| 5.3 | 5.3.0 to 5.3.49 |
| 5.2 | 5.2.25.RELEASE and older |

The fixes listed by the advisory:

| Fixed version | Status published by advisory |
|---|---|
| 7.0.9 | OSS |
| 7.0.8.1 | Enterprise Support Only |
| 6.2.20 | Enterprise Support Only |
| 6.1.29 | Enterprise Support Only |
| 6.0.31 | Enterprise Support Only |
| 5.3.50 | Enterprise Support Only |
| 5.2.26 | Enterprise Support Only |

In the fixed versions, SimpleEvaluationContext does not support expression compilation by default, regardless of the compiler mode configured on the parser or property. Applications that genuinely require compiled expressions with SimpleEvaluationContext and only process trusted expressions can opt in using `withCompilationSupported()` on the builder.

Opting in removes the safety guards applied during interpreted evaluation. Do not enable this option when expressions can come from users or untrusted sources. Upgrade to a fixed Spring version appropriate for the application's support line and read the official advisory before configuring the compiler.

## 12. Choosing the right mode

| Scenario | Selection guidance |
|---|---|
| Expression evaluated infrequently | OFF |
| Expression with stable types, supported syntax, and compiled errors should be propagated | IMMEDIATE |
| Expression whose types may change and automatic fallback to interpreted mode is desired | MIXED |
| Expression with important side effects | Prefer OFF or carefully assess the risk of re-execution in MIXED |
| Expression using selection/projection, assignment, or custom resolvers | OFF/interpreted |
| Expression evaluated on untrusted data with SimpleEvaluationContext | Do not enable the compiler; use a patched Spring version |
| Compiler needed for SimpleEvaluationContext on a patched version | Opt in only if expressions are completely trusted and the loss of safety guards is understood |

There is no single optimal mode for every application. Choose based on type stability, expression kind, side effects, and benchmark results.

## 13. Common errors and troubleshooting

| Symptom | Common cause | Resolution |
|---|---|---|
| No performance improvement seen | Expression runs rarely, compiler could not compile it, or initialization cost is high. | Measure repeatedly after warm-up and check compiled status. |
| IMMEDIATE throws error after compiling | Runtime type differs from inferred type or compiled code encounters an error. | Check type stability; use OFF or MIXED if appropriate. |
| MIXED falls back to interpreted | Compiled expression failed. | Inspect input data and types; determine whether the expression is stable. |
| Expression does not compile | Syntax belongs to an unsupported category or lacks type information. | Keep interpreted mode for that expression. |
| ClassNotFoundException/LinkageError | Compiler ClassLoader cannot see the involved types. | Choose a ClassLoader matching the root object and domain classes. |
| Side effects happen twice in MIXED | Compiled expression partially executed before failing and the framework re-ran it interpreted. | Avoid MIXED with non-idempotent expressions; use IMMEDIATE/OFF as required. |
| SimpleEvaluationContext behaves differently across Spring versions | Differences in CVE-2026-59283 patches and compilation policy. | Upgrade to a patched version; do not opt in to compilation for untrusted expressions. |
| Global compiler mode affects other expressions | Configuration property applies to parsers used by components. | Prefer configuring individual parsers if scope needs to be limited. |
| Benchmark yields unstable results | Missing warm-up, differing data, JIT/GC, or mixing parse and evaluation in measurements. | Use JMH, separate phases, and keep comparison data equivalent. |

## 14. Process for enabling the SpEL compiler

1. Identify which expressions are evaluated frequently enough to warrant optimization.
2. Measure a baseline with the compiler OFF.
3. Confirm the expression belongs to a compiler-supported category.
4. Verify that the types of the root object, properties, and results are stable across runs.
5. Choose OFF, IMMEDIATE, or MIXED based on error behavior and side effects.
6. Configure SpelParserConfiguration for the parser to be optimized.
7. If needed, choose a ClassLoader that can see all involved types.
8. Run tests with valid data, nulls, and the runtime types that may appear.
9. Re-measure with a benchmark that includes warm-up and many iterations.
10. If using SimpleEvaluationContext, check the Spring version and CVE-2026-59283 patch status; do not opt in to compilation for untrusted expressions.
11. Monitor compiled evaluation errors, class loading, and memory usage in the real runtime environment.
12. Keep interpreted mode for unsupported or type-unstable expressions.

## 15. Takeaways

- The SpEL compiler generates Java bytecode for expressions to speed up repeated evaluation.
- The compiler uses type information gathered from interpreted evaluation; stable runtime types are an important condition.
- Compiler OFF is the default.
- IMMEDIATE compiles early and propagates compiled errors to the caller.
- MIXED automatically falls back to interpreted when a compiled expression fails, but may cause side effects to run again.
- Enable the compiler via SpelParserConfiguration or the `spring.expression.compiler.mode` property.
- Compiled classes are loaded via a child ClassLoader; the ClassLoader needs to see the involved types.
- Assignment, ConversionService, custom resolvers, overloaded operators, selection/projection, bean references, and some other syntax forms are not supported by the compiler.
- Measure performance on real workloads; do not treat illustrative benchmarks as guarantees.
- CVE-2026-59283 concerns compiled SimpleEvaluationContext; upgrade to a fixed version and only opt in to compilation for trusted expressions.

## References

- [Spring Framework Reference — SpEL Compilation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [SpelCompilerMode Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelCompilerMode.html)
- [SpelParserConfiguration Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/standard/SpelParserConfiguration.html)
- [SpelCompiler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/standard/SpelCompiler.html)
- [Spring Security Advisory — CVE-2026-59283](https://spring.io/security/cve-2026-59283/)
