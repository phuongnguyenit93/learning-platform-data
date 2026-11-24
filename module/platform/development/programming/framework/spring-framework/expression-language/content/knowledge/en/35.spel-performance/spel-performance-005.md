# Impact of Custom Conversion and Resolvers

SpEL can be extended with TypeConverter, PropertyAccessor, MethodResolver, TypeLocator, BeanResolver, and other custom components. These extensions enable expressions to work with an application's custom data types and object models, but they can also increase evaluation cost. A simple expression can become slow if each run must try multiple accessors, search for methods across multiple resolvers, or perform expensive conversions.

When optimizing, distinguish expression parsing cost, context setup cost, and per-evaluation cost. It is also necessary to identify which component actually lies on the hot path. Do not assume a custom resolver is always slower or always faster than the default resolver; performance depends on implementation, registration order, caching, object types, and how many times the expression is evaluated.

## 1. Cost-Producing Stages

A single SpEL execution can incur costs across multiple stages:

| Stage | Work | Influencing Factors |
|---|---|---|
| Parse | Parse string and build Expression | Length, syntax complexity, parse count |
| Context creation | Set root object, variables, accessors, and resolvers | Component count, repeated object creation |
| Property access | Read or write a property | Accessor, reflection, caching, getters |
| Method resolution | Find matching method | Number of resolvers, overloads, argument types |
| Type conversion | Convert value to target type | Converter lookup and converter logic |
| Bean/type resolution | Resolve bean or class | Resolver, TypeLocator, class loading |
| Evaluate | Execute operations and collection operations | Step count, data size, invoked methods |

An expression parsed once and evaluated thousands of times has a different performance profile from an expression re-parsed on every request. Therefore, before optimizing resolvers, measure whether the actual cost lies in parsing, context setup, or evaluation.

## 2. Cost of TypeConverter

TypeConverter is used when SpEL needs to convert a value to a target type, such as typed getValue, property assignment via setValue, or preparing arguments for method invocation.

Example:

~~~java
Expression expression = parser.parseExpression("#rawAmount");

BigDecimal amount = expression.getValue(
        context,
        BigDecimal.class
);
~~~

If rawAmount has type String, SpEL may ask the TypeConverter to convert String to BigDecimal. Conversion typically consists of finding an appropriate converter and running the conversion logic.

A custom converter can increase cost if it:

- Performs database queries or API calls.
- Repeatedly parses complex strings.
- Creates many intermediate objects.
- Uses reflection or uncached metadata lookups.
- Performs validation or business logic outside the responsibility of conversion.

Converters should focus on type conversion. Do not use them to query data, check permissions, or perform I/O. Those tasks carry high cost and make conversion unpredictable.

## 3. Designing Lightweight and Predictable Converters

A good converter has clear inputs, outputs, and rules. It should avoid side effects and not depend on external state unnecessarily.

Example converter for account codes:

~~~java
public record AccountCode(String value) {
}

public class StringToAccountCodeConverter
        implements Converter<String, AccountCode> {

    @Override
    public AccountCode convert(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException(
                    "Account code is required"
            );
        }

        return new AccountCode(source.trim());
    }
}
~~~

This logic only normalizes the string and creates a value object. It does not query a repository or call another service.

If conversion needs to look up an entity in a database, consider fetching the entity beforehand and passing it into the context instead of placing a query inside the converter. When a converter runs multiple times in collection operations or method invocations, hidden I/O can cause N+1 queries and sharply increase evaluation time.

If a conversion can be computed upfront, normalize the data before putting it into the EvaluationContext.

## 4. Avoiding Unnecessary Repeated Conversions

If the same value is used multiple times in an expression, check whether it can be converted once upfront in Java.

For example, instead of passing a string into multiple calls requiring BigDecimal:

~~~text
#calculateTax(#rawAmount)
#calculateFee(#rawAmount)
#calculateDiscount(#rawAmount)
~~~

you can normalize it upfront:

~~~java
BigDecimal amount = new BigDecimal(rawAmount);

context.setVariable("amount", amount);
~~~

Then the expression uses the same data type:

~~~text
#calculateTax(#amount)
#calculateFee(#amount)
#calculateDiscount(#amount)
~~~

This avoids relying on repeated conversions and makes data types in the context clearer.

Pre-conversion is not always necessary. If the default converter is cheap and the expression only runs once, adding normalization code may not yield meaningful benefits. Measure before changing.

## 5. Cost of PropertyAccessor

PropertyAccessor determines how SpEL reads or writes properties on objects. StandardEvaluationContext typically uses reflective property access for Java objects; SimpleEvaluationContext can use accessors suited for data binding.

When multiple accessors are present, SpEL needs to determine which accessor supports the object and property being accessed. A custom accessor may be queried via canRead or canWrite before performing the actual operation.

If the accessor list is long or multiple accessors check object types in an expensive way, property access cost can increase.

An accessor should:

- Quickly check the target types it supports.
- Reject unsuitable object types early.
- Validate property names using an allowlist or pre-prepared metadata.
- Avoid scanning all fields via reflection on every read.
- Not perform I/O in canRead, canWrite, read, or write.
- Only do the exact work assigned to the accessor.

If an accessor only supports a specific DTO, check the appropriate class or interface before processing the property name.

## 6. Order of PropertyAccessors

Accessor registration order can affect how many checks SpEL must perform before finding the right accessor. A specialized accessor should usually come before a general accessor if it is used frequently for the corresponding object type.

For example, if an application has an accessor for a DTO and a general accessor for JavaBeans, placing the specialized accessor first can avoid unnecessarily trying the general accessor.

However, changing the order can change semantics if multiple accessors claim to support the same property. Ensure accessors do not conflict and the order reflects the intended access policy.

Do not add many fallback accessors without a concrete use case. Each new accessor increases the access surface and can raise property resolution cost.

## 7. Caching Metadata in a Custom PropertyAccessor

If an accessor needs to look up metadata such as getters, setters, or fields, metadata can be prepared and cached per class rather than searched again on every access.

Illustrative example:

~~~java
private final Map<Class<?>, Map<String, Method>> getterCache =
        new ConcurrentHashMap<>();
~~~

The cache should have keys appropriate for the target type and property. Class loaders, dynamic classes, and application lifecycle need to be handled according to the actual architecture.

Do not cache business objects or property values in a way that produces stale results after objects change. Access metadata caching is different from data caching.

Before writing a custom cache, check whether the default accessor or framework already caches the necessary metadata. Avoid building duplicate caches that increase memory and complexity without significantly reducing cost.

## 8. Cost of MethodResolver

MethodResolver locates a suitable method when an expression calls a method on an object:

~~~text
#customer.calculateDiscount(#orderTotal)
#text.substring(0, 5)
~~~

A context with multiple MethodResolvers may have to try them sequentially until finding one that handles the call. A custom resolver can increase cost if it scans many methods, parses annotations, or runs complex permission checks on every resolution.

A resolver should quickly reject target types outside its supported scope. If only certain methods are needed, use an allowlist or pre-prepared metadata instead of scanning all class methods each time.

Do not put database queries, API calls, or business logic inside method resolution. MethodResolver should decide how to locate the executor; the method's actual work only happens when the expression actually invokes it.

## 9. Distinguishing Method Resolution from Method Execution

Method resolution determines which method will be called and creates the appropriate execution mechanism. Method execution runs the Java logic of that method.

The two parts have different costs:

- Resolution can take time when searching for methods, checking overloads, and checking argument types.
- Execution can take time due to logic inside the method, I/O, databases, or computations.

If an expression is slow, do not assume MethodResolver is the cause. A quickly resolved method can still take a long time to run because of a database query or external service call.

Measure total time and profile the call stack to determine which part accounts for the cost. If method execution is the bottleneck, optimizing the resolver will not solve the problem.

## 10. Overloads and Conversions Increase Resolution Work

When a class has multiple overloads with the same name, the resolver may have to examine parameter types and conversion capabilities to choose the matching method.

Example:

~~~java
public String format(Integer value) {
    return "integer";
}

public String format(BigDecimal value) {
    return "decimal";
}

public String format(String value) {
    return "text";
}
~~~

An expression passing a String can make method selection depend on runtime types and supported conversions.

If an API is called frequently from SpEL, design methods with clear signatures and avoid too many nearly identical overloads. You can create wrapper methods with distinct names to reduce ambiguity:

~~~java
public String formatInteger(Integer value) {
    return format(value);
}
~~~

Clear method names make expressions easier to understand and reduce the number of candidates that must be resolved.

## 11. TypeLocator and BeanResolver

TypeLocator resolves classes referenced with T(...). BeanResolver resolves beans by name using the @beanName syntax.

These operations are usually unnecessary in expressions that only read simple properties. If not needed, do not configure or expose these capabilities in the context.

When needed, avoid custom resolvers that perform classpath scanning or search for beans across multiple sources on every call. Use metadata or a registry prepared during application configuration.

For frequently evaluated expressions, measure type/bean resolution cost if they lie on the hot path. If the bean or class is already known upfront, consider placing the required object/value in the context instead of resolving it repeatedly by name.

Limiting resolvers also helps reduce the access surface. Performance and safety often improve together when the context only provides necessary capabilities.

## 12. Reusing Expressions Instead of Re-Parsing

Parsing expressions has a cost. If the same string is used many times, parse once and reuse the Expression.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("#order.total >= #minimum");

for (Order order : orders) {
    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable(
            "minimum",
            new BigDecimal("100.00")
    );

    Boolean accepted = expression.getValue(
            context,
            Boolean.class
    );
}
~~~

Here the parser creates the Expression only once. Each loop iteration uses a separate context for the current order.

If re-parsed in every loop iteration, the application repeats syntax parsing work unnecessarily. For fixed rules, caching Expressions by string or rule code can reduce parse cost.

Caches need a size limit and invalidation policy if rules can change. Do not use an unbounded cache for arbitrary user-submitted expressions because it can increase memory usage.

## 13. Reusing Expressions While Managing EvaluationContext Separately

Expressions are typically designed to be reused, whereas EvaluationContext can contain a root object and variables that change per evaluation.

Do not share a mutable context across multiple requests or threads if requests overwrite the root object, variables, or resolver state. Sharing can create race conditions and inconsistent results.

A safer organization:

- Cache the parser or immutable Expression by rule/version.
- Create an EvaluationContext per evaluation or per appropriate processing unit.
- Put the current run's root object and variables into that context.
- Do not modify registries or resolvers after concurrent evaluation begins.

Context creation has its own cost. If context setup is a bottleneck, measure and consider a factory or shared immutable configuration objects. Do not optimize by sharing mutable state if doing so sacrifices correctness.

## 14. SpEL Compiler and Execution Modes

SpEL has a compiler mode to compile certain expressions to Java bytecode to reduce repeated evaluation cost.

Common modes:

| Mode | Behavior |
|---|---|
| OFF | Use interpreted evaluation only |
| IMMEDIATE | Compile expression when eligible; execution errors in compiled form may be propagated |
| MIXED | Can switch between interpreted and compiled evaluation when needed |

The parser can be configured:

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                SpelCompilerMode.MIXED,
                getClass().getClassLoader()
        );

ExpressionParser parser =
        new SpelExpressionParser(configuration);
~~~

The compiler can help frequently evaluated expressions, but not every expression can be compiled. Eligibility depends on the constructs used, runtime types, and custom components in the context.

Do not enable the compiler just for general optimization. Measure on realistic workloads and verify the expression still produces correct results when data types or objects change.

## 15. When an Expression Changes Runtime Types

A compiled expression may assume certain types observed during evaluation. If the same expression is used with objects of a different runtime type, the compiled code may no longer be suitable.

MIXED mode is designed to fall back to interpreted evaluation when the compiled form encounters issues and continue adapting per the compiler mechanism. IMMEDIATE mode can propagate errors when a compiled expression cannot run.

Therefore, consider data type stability before choosing a compiler mode. An expression used on a stable DTO is usually easier to optimize than an expression run on many unrelated object types.

If a rule receives polymorphic data, benchmark with all realistic runtime types, not just a single representative fixture.

## 16. Limitations of Custom Accessors and the Compiler

Expressions using custom PropertyAccessors, custom MethodResolvers, or dynamic features may not be as fully supported by the compiler as by interpreted evaluation. Some access paths requiring custom resolver mechanisms may only run in interpreted mode.

Verify compilability on the exact Spring version in use and the application's exact context configuration. If an expression cannot be compiled, enabling the compiler will not automatically make a custom resolver faster.

Do not alter accessor or resolver semantics just to force the compiler to work. Correctness and access restrictions matter more than a faster benchmark that does not reflect production behavior.

## 17. Reducing Resolver Invocations Inside Expressions

An expression may read the same property or call the same method multiple times. If that operation is expensive, consider precomputing the value in Java or passing it as a context variable.

Example:

~~~text
#customer.profile.account.region == 'APAC' and
#customer.profile.account.active and
#customer.profile.account.ageDays > 30
~~~

If accessing account involves lazy loading or getters performing computation, the expression may repeat that cost.

Data can be prepared:

~~~java
context.setVariable("accountRegion", account.getRegion());
context.setVariable("accountActive", account.isActive());
context.setVariable("accountAgeDays", account.getAgeDays());
~~~

The expression becomes simpler:

~~~text
#accountRegion == 'APAC' and
#accountActive and
#accountAgeDays > 30
~~~

Do not create redundant variables for cheap properties or ones used only once. Pre-normalization only helps when it eliminates repeated work or clarifies data types.

## 18. Performance of Selection and Projection

Selection .?[...] must check elements to find all matching results. Projection .![...] must transform each element. If the predicate or projection calls an expensive method, total cost grows with the number of elements.

Example:

~~~text
#orders.?[#this.customer.loadRiskScore() < 50]
~~~

If loadRiskScore queries a database, a collection with many orders can generate many queries. The issue lies in method execution and data, not just the resolver.

Prepare risk scores beforehand or batch-load data in a service and pass needed values into a DTO. Avoid lazy loading and I/O in predicates.

If only the first matching element is needed, first selection can stop once a match is found. If all results are needed, the whole collection must be processed as required.

## 19. Measure Performance Instead of Guessing

A useful benchmark needs to reflect how the application actually uses SpEL:

- Parse once or parse per request.
- Number of evaluations per Expression.
- Root object types and degree of polymorphism.
- Number of accessors and resolvers.
- Default converter or custom converter.
- Collection size.
- Whether invoked methods perform I/O.
- Context newly created or reused.
- Compiler mode in use.

JMH is suitable for controlled Java micro-operation benchmarks. For real applications, a profiler or tracing helps identify time spent in converters, accessors, resolvers, and invoked methods.

Measure both throughput and latency, including high percentiles if the system serves requests. Run multiple warm-up and measurement rounds, avoiding including JVM startup or initial class loading in steady-state conclusions.

Do not compare two configurations using a single short run or rely solely on average time.

## 20. JMH Example Comparing Reused Expressions

Benchmark sketch example:

~~~java
@State(Scope.Thread)
public class SpelBenchmark {

    private Expression expression;
    private StandardEvaluationContext context;
    private Order order;

    @Setup
    public void setup() {
        ExpressionParser parser =
                new SpelExpressionParser();

        expression = parser.parseExpression("total >= 100");

        order = new Order(new BigDecimal("250.00"));
        context = new StandardEvaluationContext(order);
    }

    @Benchmark
    public Boolean evaluateReusedExpression() {
        return expression.getValue(context, Boolean.class);
    }
}
~~~

This benchmark measures evaluation on an already parsed Expression. If you want to measure parse cost, create a separate benchmark calling parseExpression inside the benchmarked method.

Do not lump parsing, context creation, object creation, and evaluation into one benchmark and conclude which resolver is slow. Separating the parts shows which optimization actually helps.

In a production-like benchmark, include the custom converters and resolvers used by the application, along with data of matching types and sizes.

## 21. Cache and Memory Management

Caching Expressions can reduce parsing cost, but an unbounded cache can retain too many expressions and increase memory usage.

If expressions are modified by administrators, cache keys should include the rule code and version or expression content. When a rule changes, invalidation is needed so the old expression is not continuously reused.

Do not cache EvaluationContexts containing root objects, request data, or user variables. That can leak data across requests and retain objects longer than their required lifecycle.

Accessor/resolver metadata caches should have bounds and stable keys. Monitor entry counts, hit rate, and memory usage to avoid trading uncontrolled memory consumption for time optimization.

## 22. Balancing Performance and Safety

Custom resolvers are often added to control access permissions or integrate domain types. Do not remove allowlists, validation, or accessor limits just to save a few checks.

A fast resolver that allows reading or calling any property/method can create security risks. Optimize the implementation within the permitted policy:

- Check target types quickly.
- Cache validated metadata.
- Use immutable allowlists.
- Avoid repeated reflection scans.
- Avoid I/O and side effects.
- Keep resolver ordering clear.
- Test both permitted and denied properties/methods.

Performance must be measured under the exact access-control policy that production will use.

## 23. Signs That Require Investigation

| Symptom | Potential Bottleneck Area | Investigation Direction |
|---|---|---|
| CPU rises during repeated evaluation | Expression or resolver repeating work | Profile call stack |
| Many allocations when reading properties | Accessor creating intermediate metadata/objects | Check cache and implementation |
| Latency rises with custom converter | Converter parsing or querying too much | Measure conversion separately |
| Method lookup takes significant time | Many resolvers or many overloads | Check ordering and method signatures |
| Rule slows down with element count | Predicate/projection calling expensive methods | Batch data and reduce I/O |
| Parse accounts for a large share | Expression parsed repeatedly | Reuse/cache Expression |
| Compiled mode shows no improvement | Expression not compiled or bottleneck in methods/I/O | Check compile eligibility and profile |
| Memory grows with rule count | Unbounded expression cache | Use bounded cache and invalidation |

These signs only serve as pointers. A profiler or benchmark is needed to confirm the root cause before changing the design.

## 24. Key Takeaways

TypeConverter can increase cost when conversions repeat or converters perform heavy work. PropertyAccessor and MethodResolver affect how property reads/writes or method calls are resolved; resolver count, order, and metadata caching can all impact the execution path. TypeLocator and BeanResolver also need to be restricted and optimized if used frequently.

Parse expressions once and reuse the Expression when appropriate. Manage EvaluationContext per evaluation to avoid sharing mutable state. Keep converters and resolvers lightweight, reject unsupported types fast, cache metadata rather than business data, and avoid I/O during evaluation.

The SpEL compiler can help some frequently executed expressions, but it does not support every construct or custom resolver. Choose OFF, IMMEDIATE, or MIXED based on data types and actual runtime behavior. Use JMH, a profiler, and representative workloads to measure parsing, context setup, conversion, resolution, and method execution separately.