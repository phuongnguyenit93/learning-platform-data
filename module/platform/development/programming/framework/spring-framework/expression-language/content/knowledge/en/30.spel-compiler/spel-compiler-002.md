# Interpreter mode, immediate mode, and mixed mode

Spring Expression Language (SpEL) can evaluate expressions using an **interpreter** or compile expressions into bytecode for faster execution. The choice is controlled by **SpelCompilerMode**, typically passed into **SpelParserConfiguration** when creating a SpelExpressionParser.

The three main modes are **OFF**, **IMMEDIATE**, and **MIXED**. They determine whether SpEL attempts to compile an expression, when it begins trying, and how it handles situations where a compiled expression no longer matches runtime data. There is no single best mode for every application: the choice depends on evaluation frequency, data type stability, and whether the expression can be compiled.

## What is interpreter mode?

In interpreted mode, SpEL evaluates the Expression structure using an interpreter. The parser parses the string once to create an Expression; each time getValue or setValue is called, the interpreter performs the required operations according to that structure.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("price * quantity");

BigDecimal total =
        expression.getValue(order, BigDecimal.class);
~~~

The expression is parsed into an Expression. When the application calls getValue, SpEL reads the price and quantity properties from the root object order and performs the multiplication.

The interpreter suits many cases because it flexibly supports SpEL features and does not need to generate separate bytecode for an expression. It is also the default evaluation method when the compiler is disabled.

An important optimization is to **parse once and reuse the Expression**. If an application creates a parser and re-parses the same string on every request, the repeated parsing cost can exceed the savings the compiler provides. Before enabling the compiler, ensure the Expression is cached or held in a component with an appropriate lifecycle.

## SpelCompilerMode

SpEL provides the **SpelCompilerMode** enum with three values:

| Mode | Main behavior | Suitable when |
|---|---|---|
| **OFF** | Does not compile; continues using the interpreter | Flexibility is prioritized or expressions do not need compile optimization |
| **IMMEDIATE** | Attempts to compile early, usually after the first interpreted evaluation | Data types are stable and switching to bytecode quickly is desired |
| **MIXED** | Starts with the interpreter, attempts to compile after a number of evaluations; can fall back to the interpreter if the compiled form fails | Repetitive workloads where runtime types may change |

The mode is chosen when creating the parser configuration. This is a policy applied to the Expressions created by that parser, not a per-call toggle on individual getValue calls.

## OFF mode

**SpelCompilerMode.OFF** disables the compiler. Expressions are evaluated by the interpreter throughout their lifecycle.

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                SpelCompilerMode.OFF,
                MyApplication.class.getClassLoader());

ExpressionParser parser =
        new SpelExpressionParser(configuration);

Expression expression =
        parser.parseExpression("price * quantity");
~~~

OFF is the default choice when no other compiler mode is configured. This mode fits when expressions are evaluated infrequently, when expression structures are not supported by the compiler, or when data has varying types that make compilation benefits unclear.

OFF incurs no bytecode generation cost for expressions. In return, each evaluation still goes through the interpreter. For simple expressions or non-hot workloads, the performance difference may be negligible.

## IMMEDIATE mode

**SpelCompilerMode.IMMEDIATE** instructs SpEL to attempt compiling an expression as soon as possible. Typically, the expression is evaluated by the interpreter first to gather the necessary runtime information; after the first evaluation, SpEL can attempt to generate a bytecode version for expressions the compiler supports.

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                SpelCompilerMode.IMMEDIATE,
                MyApplication.class.getClassLoader());

ExpressionParser parser =
        new SpelExpressionParser(configuration);

Expression expression =
        parser.parseExpression("price * quantity");
~~~

When an expression can be compiled, subsequent evaluations can run the compiled version. This can reduce repeated evaluation overhead in suitable workloads.

On the other hand, compiled expressions typically rely on the data types and object structures observed during compilation. If runtime data later changes in a way that no longer matches the bytecode, executing the compiled expression may fail and throw an exception.

For example, an expression is compiled when the payload property has type String, but later receives an object of another type. The compiled version may assume the previously observed type and fail to handle this change the way the interpreter would.

Therefore, IMMEDIATE is better suited when the types of the root object, properties, and related values are stable across evaluations. If the same Expression is used with multiple object types or heterogeneous data, thoroughly test the behavior before choosing this mode.

If the compiler cannot compile an expression, SpEL can continue using the interpreter for that expression. Enabling IMMEDIATE does not mean every expression is guaranteed to produce bytecode.

## MIXED mode

**SpelCompilerMode.MIXED** starts with the interpreter. After a number of evaluations, SpEL attempts to compile the expression if sufficient information is available and the expression is supported.

If the compiled expression runs successfully, SpEL can continue using the compiled version. If the compiled form fails due to a change in runtime type or structure, MIXED can fall back to the interpreter and continue evaluating in interpreted mode. Afterward, SpEL may try compiling again when conditions are suitable.

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                SpelCompilerMode.MIXED,
                MyApplication.class.getClassLoader());

ExpressionParser parser =
        new SpelExpressionParser(configuration);

Expression expression =
        parser.parseExpression("price * quantity");
~~~

MIXED is useful when an expression is evaluated repeatedly but data may change types in practice. The ability to fall back to the interpreter gives the application more flexibility than IMMEDIATE when the compiled form is no longer suitable.

Do not treat MIXED as a mechanism that guarantees every expression runs fast or automatically handles all runtime errors. Errors caused by null data, nonexistent properties, invalid operations, or business logic can still occur in the interpreter. MIXED only manages switching between compiled and interpreted forms when executing a compiled expression runs into issues within the compiler's scope.

## Comparing how runtime type changes are handled

Suppose the same Expression is evaluated on objects whose properties have heterogeneous data types. The interpreter can handle this more flexibly because on each evaluation it uses accessors and conversions appropriate for the current context. A compiled expression may rely on the types observed at compile time.

| Scenario | OFF | IMMEDIATE | MIXED |
|---|---|---|---|
| Stable data types | Continues interpreting | Can use compiled form after compilation | Can switch to compiled form after an interpreted phase |
| Type changes after compilation | Interpreter handles by runtime type if expression is valid | Compiled form may throw an error | Can fall back to interpreter when compiled form fails |
| Expression not supported for compilation | Continues interpreting | Continues interpreting if not compilable | Continues interpreting if not compilable |
| Bytecode generation cost | None | Tried early | Tried after multiple evaluations |

This difference is especially important for expressions shared across multiple DTO types, proxy objects, or data coming from sources with heterogeneous schemas. If runtime types are unstable, OFF or MIXED is usually more predictable than IMMEDIATE.

## Configuring parser and ClassLoader

The compiler generates bytecode for an expression and needs a **ClassLoader** to load the generated class. The compiler mode and ClassLoader can be passed into SpelParserConfiguration:

~~~java
ClassLoader compilerClassLoader =
        MyApplication.class.getClassLoader();

SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                SpelCompilerMode.MIXED,
                compilerClassLoader);

ExpressionParser parser =
        new SpelExpressionParser(configuration);
~~~

The ClassLoader needs to see the types referenced by the compiled expression. In applications with plugins, application servers, separate modules, or hierarchical class loaders, choosing the appropriate class loader can affect the ability to compile and load bytecode.

If no specific class loader is specified, other configuration overloads or the default mechanism of the Spring version in use will decide how classes are loaded. In complex deployment environments, configure this explicitly and test in the actual runtime environment rather than only on a development machine.

The compiler mode and class loader are tied to SpelParserConfiguration. If the application needs parsers with different policies, separate SpelExpressionParsers can be created with the corresponding configurations.

## Not every expression can be compiled

The SpEL compiler supports a subset of expressions. Compilability depends on the expression structure, the type information gathered during evaluations, and the features supported by the compiler.

Expressions with stable data types, property access, and clear operations are generally a better fit. Expressions that rely heavily on dynamic behavior, changing types, or capabilities not supported by the compiler may continue running via the interpreter.

Do not assume an expression will definitely compile just because the parser accepts its syntax. Successful parsing and successful compilation are two different things:

1. The parser validates that the string has valid SpEL syntax and creates an Expression.
2. The interpreter can evaluate the Expression against the current context and data.
3. The compiler may or may not be able to generate bytecode for that expression structure.
4. Once compiled, the compiled form still needs to match the data in subsequent runs.

An uncompilable expression is not necessarily a wrong expression. It can be completely valid and continue to be evaluated by the interpreter.

## When a compiled expression is no longer suitable

A compiled form can rely on previously observed data types. If the runtime type changes, the compiled code may no longer execute the generated operation properly.

For example, an expression that accesses a property or calls a method on a specific type can be compiled with assumptions about that type. If a later evaluation receives an object of a different type or an incompatible value, the compiled form may fail.

Behavior differs by mode:

- With **IMMEDIATE**, errors from the compiled expression can be propagated to the caller. The application needs to handle them or choose another mode if real-world data allows type changes.
- With **MIXED**, SpEL can switch back to the interpreter after a compiled execution error, then attempt to recompile at a later time.
- With **OFF**, there is no compiled form, so no error occurs from compiled code assuming an old type.

Whichever mode is used, the application still needs to validate data and handle evaluation errors. Do not rely on compiler mode as a substitute for validation.

## Measuring performance before choosing a mode

The compiler is designed to improve performance for expressions evaluated many times, but compilation also has a cost. For rarely used expressions, initialization and bytecode generation overhead may not be offset by time saved in subsequent runs.

A practical selection workflow:

1. Parse the expression once and reuse the Expression.
2. Measure evaluation time in OFF mode on a representative workload.
3. Try MIXED or IMMEDIATE with the same data and evaluation count.
4. Measure startup cost, warm-up phase, and steady-state throughput.
5. Check whether data changes types or structure between evaluations.
6. Choose the mode based on measured benefit and application stability requirements.

Benchmarks need to use data close to production. If tests only use a single object with a fixed type, results may not reflect the real system when multiple object types or proxies are passed to the same expression.

Do not compare just a single getValue call. Measure enough evaluations to reflect when the compiler activates and the warm-up cost.

## Parse once and reuse the Expression

Before enabling the compiler, avoid re-parsing the same string on hot paths:

~~~java
public class PricingEvaluator {
    private final Expression totalExpression;

    public PricingEvaluator() {
        ExpressionParser parser =
                new SpelExpressionParser();

        this.totalExpression =
                parser.parseExpression("price * quantity");
    }

    public BigDecimal calculate(Order order) {
        return totalExpression.getValue(
                order,
                BigDecimal.class);
    }
}
~~~

The Expression is created once when PricingEvaluator is initialized and reused for each Order. When further optimization is needed, the parser can be replaced with one created from a SpelParserConfiguration with an appropriate compiler mode.

EvaluationContext should be managed per evaluation's data. If a context holds mutable per-request variables, avoid sharing it across multiple threads without a synchronization policy or creating separate contexts.

## Parse errors, evaluation errors, and compile failures

Three phases need to be distinguished:

- **ParseException:** the expression string has invalid syntax, so the parser cannot create an Expression.
- **EvaluationException:** the expression is valid, but cannot be evaluated against the current root object, variables, or context.
- **Compile failure:** the compiler cannot generate bytecode for the expression, or the compiled form cannot execute against the current runtime data.

A compile failure is not the same as a ParseException. An expression can parse and evaluate normally with the interpreter while not being supported by the compiler.

Example handling parse and evaluation:

~~~java
Expression expression;

try {
    expression = parser.parseExpression("price * quantity");
} catch (ParseException ex) {
    throw new IllegalArgumentException(
            "Invalid SpEL syntax", ex);
}

try {
    BigDecimal total =
            expression.getValue(order, BigDecimal.class);
} catch (EvaluationException ex) {
    throw new IllegalStateException(
            "Cannot evaluate pricing expression", ex);
}
~~~

When the compiler is enabled, also observe errors related to compiled execution according to the chosen mode. Do not catch all exceptions and return a default value, as that can hide invalid data or business errors.

## Choosing a mode by application characteristics

| Workload characteristic | Selection guidance |
|---|---|
| Expression evaluated infrequently | OFF is usually sufficient |
| Expression with stable data types and called very frequently | Benchmark IMMEDIATE or MIXED |
| Expression used across multiple object types | Prefer testing OFF/MIXED; be cautious with IMMEDIATE |
| Flexible behavior needed when compiled form fails | MIXED |
| Expression not supported by the compiler | OFF or continue using the interpreter |
| Application running in a complex class loader environment | Verify and configure an appropriate ClassLoader |

These are selection guidelines, not rigid rules. Actual results depend on the expression, Spring version, JDK, class loader, data, and evaluation frequency.

## Conclusion

SpEL provides three compiler modes: **OFF** always uses the interpreter; **IMMEDIATE** attempts early compilation and may propagate compiled execution errors to the caller when runtime types change; **MIXED** starts with the interpreter, attempts compilation after multiple evaluations, and can fall back to the interpreter if the compiled form fails.

Choose a mode based on evaluation frequency, data type stability, and expression compilability. Parse once and reuse the Expression before optimizing further, configure an appropriate ClassLoader, and benchmark with realistic workloads. The compiler is an optional optimization; it does not replace validation, error handling, or understanding the data an expression will receive.
