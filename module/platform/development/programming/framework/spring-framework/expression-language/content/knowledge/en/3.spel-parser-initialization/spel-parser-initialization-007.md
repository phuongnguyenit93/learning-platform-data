# SpringEL Compiler Mode and ParserConfiguration

## Objective

After this lesson, you will be able to explain how Spring Expression Language (SpEL) transitions from interpreted expression evaluation to executing compiled bytecode; distinguish the three modes `OFF`, `IMMEDIATE`, and `MIXED`; configure the parser with `SpelParserConfiguration`; and decide when to enable compilation or data auto-grow features.

## 1. From parser to evaluation result

When using SpEL, three stages should be distinguished:

1. **Parsing (parse):** `SpelExpressionParser` reads the expression string and creates an `Expression` object.
2. **Interpreted evaluation:** when calling `getValue(...)`, SpEL evaluates the expression tree based on the runtime object and context.
3. **Compiled evaluation:** if the compiler is enabled and the expression falls into a supported group, SpEL can generate bytecode so subsequent evaluations run faster.

Parsing does not mean the expression has been compiled. Calling `parseExpression(...)` primarily creates the expression object; the actual result only appears when calling an evaluation method such as `getValue(...)`.

Basic example:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("#price * #quantity");

EvaluationContext context = new StandardEvaluationContext();
context.setVariable("price", new BigDecimal("12.50"));
context.setVariable("quantity", 4);

BigDecimal amount = expression.getValue(context, BigDecimal.class);
~~~

This snippet uses the default parser. Without configuring the compiler, SpEL evaluates expressions in interpreted mode. When you need to change the compilation mode or data auto-grow behaviors, pass a `SpelParserConfiguration` into the parser.

## 2. What problem does the SpEL compiler solve?

In interpreted mode, SpEL must traverse the expression structure and perform the necessary evaluation steps on every call. For an expression evaluated a very large number of times, this overhead can become significant.

The SpEL compiler can translate a supported expression into Java bytecode. That bytecode is loaded and executed in the JVM. The goal is to reduce repeated evaluation overhead when the expression and actual data types are sufficiently stable.

The compiler is usually helpful when:

- The same expression is evaluated repeatedly on a hot path.
- The types of the root object, properties, and results remain stable across calls.
- The expression uses constructs supported by the compiler of the running Spring version.
- Expression evaluation cost is large enough that optimization is meaningful after performance measurement.

The compiler is not a full compiler for every SpEL syntax feature. Some expressions still need to be evaluated via the interpreter. Enabling the compiler also does not guarantee a faster application in every case: for infrequently called expressions, the overhead of compilation and code management may bring no benefit.

## 3. Three compilation modes

SpEL provides the `SpelCompilerMode` enum with three main values:

| Mode | Behavior | Suitable scenarios |
|---|---|---|
| `OFF` | Disables compilation; expressions are evaluated via the interpreter | Safe default, infrequently executed expressions, or data with changing types |
| `IMMEDIATE` | SpEL attempts to switch the expression to compiled form early during evaluation | Hot expressions with stable, tested data types |
| `MIXED` | Initially evaluates via interpreter; after a number of runs, SpEL may switch to compilation | Applications needing self-adaptation between fast startup and hot-path optimization |

### 3.1. OFF

`OFF` is the default mode when no compiler is requested. SpEL continues evaluating expressions via the interpreter.

Choose `OFF` when:

- Expressions are evaluated only occasionally.
- Input data types change frequently.
- Predictable behavior is needed during development or debugging.
- Expressions use constructs not supported by the compiler.
- Performance measurements have not shown evaluation to be a bottleneck.

Disabling the compiler does not remove any capabilities of the SpEL language. It only determines how expressions are executed.

### 3.2. IMMEDIATE

`IMMEDIATE` instructs SpEL to try compiling the expression early during evaluation. Once sufficient information is available from initial evaluation, the compiler can generate executable code for the expression if it is supported.

This mode fits when the application controls the expression and knows that data types will remain stable. If compiled code encounters a situation incompatible with the type assumptions made at compile time, errors may be surfaced to the caller. Therefore, do not choose this mode for expressions receiving data whose shape or types vary arbitrarily.

For example, if `#order.total` always returns the same numeric type and `#rate` also has a stable type, a total calculation expression stands a better chance of suiting the compiler than an expression depending on heterogeneous object types.

### 3.3. MIXED

`MIXED` starts with interpreted evaluation. After the expression has been evaluated enough times, SpEL may attempt compilation to optimize subsequent runs.

If executing in compiled form encounters an error because type assumptions no longer hold, `MIXED` mode has a mechanism to fall back to the interpreter. This mechanism makes the application more flexible when actual runtime types can vary.

This is often a worthwhile option when:

- The application has expressions evaluated repeatedly.
- There may be more data types or runtime scenarios than anticipated.
- You want SpEL to attempt optimization after observing how the expression is used.
- You accept automatic fallback to the interpreter when compiled code is no longer suitable.

`MIXED` does not replace testing. If an expression keeps changing types or the compiler does not support the constructs in use, the benefit may be low or absent.

## 4. Configuring the compiler when creating a parser

The `SpelParserConfiguration` class resides in the `org.springframework.expression.spel` package. You can pass the compiler mode and class loader into the constructor, then use that configuration to create `SpelExpressionParser`.

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.SpelCompilerMode;
import org.springframework.expression.spel.SpelParserConfiguration;
import org.springframework.expression.spel.standard.SpelExpressionParser;

SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        SpelCompilerMode.MIXED,
        OrderService.class.getClassLoader()
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);

Expression expression =
    parser.parseExpression("#order.total * #rate");
~~~

In the example:

- `SpelCompilerMode.MIXED` selects interpreted execution first, then allows compilation once the expression is used enough times.
- `OrderService.class.getClassLoader()` provides the class loader that the compiler can use when generating and loading the class containing compiled bytecode.
- `SpelExpressionParser(configuration)` creates a parser using the declared policy.

The class loader needs visibility into the types referenced by the expression. In applications running inside containers, plugins, or multi-classloader environments, choose a class loader appropriate for the lifecycle and class visibility of the application. If there are no special requirements, use the class loader of the application class that owns the expression.

The no-argument constructor of `SpelExpressionParser` can still be used when default settings are acceptable. You do not need to enable the compiler simply because the application uses SpEL.

## 5. Configuring auto-growing null references and collections

`SpelParserConfiguration` also lets you configure two auto-grow behaviors:

- `autoGrowNullReferences`: allows SpEL to automatically create an object when a segment of a property path encounters a `null` reference, if the corresponding type can be instantiated.
- `autoGrowCollections`: allows SpEL to automatically grow an array or collection when an expression accesses an index beyond the current size, within allowed limits.
- `maximumAutoGrowSize`: caps the maximum size that the collection auto-grow mechanism can allocate.

Complete configuration example:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        SpelCompilerMode.OFF,
        OrderService.class.getClassLoader(),
        true,   // autoGrowNullReferences
        true,   // autoGrowCollections
        128     // maximumAutoGrowSize
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

For example, suppose an `order` object has a `shippingAddress` property that is currently `null`. If `autoGrowNullReferences` is enabled and SpEL can instantiate the required type, evaluating the path:

~~~text
shippingAddress.city
~~~

can instantiate a `shippingAddress` object before accessing `city`.

Similarly, if a list has fewer elements than the index the expression needs to access, `autoGrowCollections` can grow the list. The `maximumAutoGrowSize` limit helps prevent growth beyond the configured bound.

Keep in mind that auto-growing can mutate objects in memory. It is not purely a read operation. If the expression runs on shared, persisted, or transactional objects, creating extra objects or elements can affect application state.

Both auto-grow features should generally remain disabled unless the business logic needs them. Enable them only intentionally and set an appropriate size cap. The target object type must also have an instantiation mechanism SpEL can invoke; not every type can be auto-created in every situation.

## 6. Distinguishing ParserConfiguration and EvaluationContext

These two objects solve two different problems:

| Component | Responsibility |
|---|---|
| `SpelParserConfiguration` | Configures how the parser handles expressions, compiler mode, class loader, and auto-grow options |
| `EvaluationContext` | Provides the data and permissions an expression can use during evaluation, such as root object, variables, functions, bean resolver, property accessors, and method resolvers |
| `Expression` | Represents the parsed expression and provides methods to get or set values when permitted |

Example combining a compiler-configured parser with an evaluation context:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        SpelCompilerMode.MIXED,
        OrderService.class.getClassLoader()
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);

Expression expression =
    parser.parseExpression("#order.total * #rate");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("order", order);
context.setVariable("rate", new BigDecimal("1.08"));

BigDecimal amount =
    expression.getValue(context, BigDecimal.class);
~~~

Here, `ParserConfiguration` determines the parser's parsing and execution policy. `EvaluationContext` supplies the `order` and `rate` variables to the expression. Changing the compiler mode does not create variables by itself, grant bean lookup permissions, or replace context configuration.

Conversely, switching from `StandardEvaluationContext` to a more restricted context changes access permissions and evaluation capabilities, not the compiler mode.

## 7. Limitations and conditions for effective compilation

Not every SpEL expression can be compiled to bytecode. Compilability depends on the expression structure and the running Spring version. Some expressions may continue running in interpreted mode even when the parser is configured with the compiler enabled.

Factors to watch out for:

### 7.1. Data types must be sufficiently stable

The compiler generates code based on the types it observes during evaluation. If the same expression receives a `String` at one time, a numeric type at another, or objects with differing structures, the compiled code may no longer fit.

Favor expressions with a clear, stable root object and property types. Avoid assuming an expression can be well optimized if it accepts arbitrary data from multiple sources.

### 7.2. Expression constructs must be supported

The SpEL compiler only supports a subset of language constructs. A syntactically valid expression may still be non-compilable. In that case, enabling the compiler does not make that syntax supported for compilation.

If an expression is unsuitable, keep interpreted mode. There is no need to rewrite an expression solely to force the compiler to emit bytecode.

### 7.3. Compilation does not change business semantics

The compiler is an execution optimization mechanism. It should never be used to alter the expected result of an expression. The same expression must yield the same correct result for valid data in both interpreted and compiled modes.

### 7.4. Do not equate compilation with Java static type checking

SpEL remains an expression language evaluated at runtime. Enabling the compiler does not turn it into a Java class fully checked at application compile time. Syntax errors, property access errors, conversion errors, and data errors still must be handled at the appropriate time.

## 8. Choosing a configuration in an application

You can start from these practical choices:

| Scenario | Recommended configuration | Reason |
|---|---|---|
| Infrequently run expressions used for general configuration | `OFF` | Keeps configuration simple without unnecessary compilation steps |
| Hot expressions with fixed, controlled data types | `IMMEDIATE` | Allows early optimization when there is sufficient confidence |
| Frequently run expressions whose runtime types may vary | `MIXED` | Can fall back to the interpreter when compiled code no longer fits |
| Need to auto-create objects or grow collections on access | Enable only the needed auto-grow options | Mutates data only when business logic requires it and with a bound |
| Expressions taken from untrusted sources | Keep context privileges minimal; consider disabling auto-grow | Limits side effects and object access capabilities |

Do not choose `IMMEDIATE` or `MIXED` just because the mode name sounds faster. Measure evaluation time in a production-like environment, with representative data and realistic call counts. Compare startup time, first-run overhead, warmed-up throughput, and behavior when data types change.

If a parser is created in a shared location, its configuration affects every expression that parser produces. When groups of expressions have different compiler or auto-grow requirements, consider creating parsers with separate configurations instead of applying one broad policy to everything.

## 9. Complete example: creating a parser and evaluating an expression

The example below selects `MIXED`, uses the application's class loader, disables auto-growing objects or collections, and passes data via variables in the context:

~~~java
import java.math.BigDecimal;

import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.SpelCompilerMode;
import org.springframework.expression.spel.SpelParserConfiguration;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

public class OrderExpressionService {

    public BigDecimal calculate(Order order) {
        SpelParserConfiguration configuration =
            new SpelParserConfiguration(
                SpelCompilerMode.MIXED,
                OrderExpressionService.class.getClassLoader(),
                false,
                false,
                128
            );

        ExpressionParser parser =
            new SpelExpressionParser(configuration);

        Expression expression =
            parser.parseExpression("#order.total * #taxRate");

        StandardEvaluationContext context =
            new StandardEvaluationContext();

        context.setVariable("order", order);
        context.setVariable("taxRate", new BigDecimal("1.08"));

        return expression.getValue(context, BigDecimal.class);
    }
}
~~~

In a real application, it is unnecessary to create the parser and re-parse the same expression on every call as shown in the illustrative example. If the expression is fixed, you can initialize the parser and `Expression` once during configuration or service initialization, then reuse them in a way that fits the application lifecycle. The context and evaluation data still must be supplied properly for each execution.

## 10. Key takeaways

`SpelParserConfiguration` is where parser policies are configured. It lets you choose the compiler mode, supply a class loader, and decide whether SpEL auto-creates `null` references or auto-grows collections.

`OFF` keeps SpEL in interpreted mode. `IMMEDIATE` requests early compilation where possible and suits stable data types. `MIXED` starts with interpreted execution and can transition to bytecode, while also being able to fall back to the interpreter if compiled code runs into type issues.

The compiler only optimizes a subset of supported expressions; it does not turn SpEL into Java and does not guarantee every application will be faster. `autoGrowNullReferences` and `autoGrowCollections` can mutate the object graph in memory, so enable them only when needed and cap the size appropriately.

Choose the parser configuration based on evaluation frequency, data type stability, access privileges, and the behavior your business logic genuinely needs.