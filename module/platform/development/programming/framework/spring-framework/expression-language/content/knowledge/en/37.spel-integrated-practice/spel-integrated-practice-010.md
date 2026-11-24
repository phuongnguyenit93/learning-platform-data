# Complete Profile: Syntax, Context, Testing, Security, and Performance

## Objectives

This practice lesson connects the key parts of Spring Expression Language (SpEL) into a deliverable and operable implementation profile. You will define expression syntax and parsing; describe the root object, variables, beans, and functions; configure EvaluationContext with least privilege; evaluate results and handle errors; build functional, boundary, and access-permission tests; protect expressions from unintended usage; and measure performance before selecting a compiler mode.

The desired outcome is for each expression to have an explicit contract: what it is for, what data it receives, what it is allowed to access, what type it returns, how it handles nulls and errors, which cases test it, and what its runtime cost is.

## 1. Lifecycle of an expression

An expression typically goes through these stages:

1. Define the business purpose and data sources.
2. Write the SpEL string or template expression.
3. Configure the parser and ParserContext if needed.
4. Parse the string into an Expression.
5. Prepare the root object and EvaluationContext.
6. Evaluate the expression with runtime data.
7. Convert or verify the result type if needed.
8. Handle errors, record operational information, and use the result.
9. Re-test whenever the expression, model, or context changes.

Parsing and evaluating are two distinct stages. Successful parsing only confirms the syntax can be analyzed; it does not guarantee that required variables, beans, properties, or methods exist at runtime.

Fixed expressions should be parsed and checked for dependencies as early as possible. Request-varying data is provided at evaluation time. This separation helps catch configuration errors before they appear in live processing flows.

## 2. Choosing syntax suited to the purpose

SpEL supports property access, operators, method calls, functions, collection operations, and many other constructs. Choose short expressions that directly express the rule to execute.

Property reading example:

~~~text
customer.name
~~~

Comparison and logic:

~~~text
total >= #minimumTotal and active
~~~

Conditional:

~~~text
status == 'PAID' ? 'Complete' : 'Pending'
~~~

Element access:

~~~text
#orders[0].id
~~~

Selection and projection:

~~~text
#orders.?[total >= #minimumTotal].![id]
~~~

Syntax should reflect the exact data source. Properties without the `#` prefix are read from the current evaluation object; variables with the `#` prefix are looked up in EvaluationContext; bean references use `@`. Inside collection operations, `#this` can represent the current element while `#root` keeps the original root object.

If an expression becomes too long, nests many conditions, or calls multiple side-effecting methods, move the complex logic into Java and pass only the necessary results or inputs into SpEL.

## 3. Parsing expressions and reusing Expression

Basic example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("total >= #minimumTotal");
~~~

An Expression can be reused across multiple evaluations:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

context.setVariable(
    "minimumTotal",
    new BigDecimal("100.00")
);

Boolean accepted =
    expression.getValue(context, orderView, Boolean.class);
~~~

If the same string is used repeatedly, parsing once is usually more sensible than re-parsing on every request. Contexts can be created separately for each execution to supply the appropriate root object and variables.

Do not share a mutable EvaluationContext across unrelated requests if variables or root objects change. A reused Expression and isolated contexts form an easily controllable organization.

For expressions stored in external configuration, attach an identifier and version to know exactly which string is running. When updating, parse and validate it before putting it into use.

## 4. ParserContext and template expressions

Plain expressions treat the entire string as SpEL syntax. Template expressions allow mixing literal text with SpEL segments.

For example:

~~~java
Expression message = parser.parseExpression(
    "Order #{#orderId} is now #{#status}.",
    new TemplateParserContext()
);
~~~

With the default delimiters, segments between `#{` and `}` are evaluated; the rest is kept as-is. You can use TemplateParserContext with custom prefixes/suffixes when default delimiters easily conflict with content.

ParserContext only decides how the parser splits the string. It does not register variables, beans, functions, or permissions. Those dependencies belong to EvaluationContext.

In Spring configuration, distinguish configuration placeholders from SpEL: placeholders use `${...}` syntax to retrieve values from property sources; SpEL uses `#{...}` to evaluate expressions. Both mechanisms can be combined in Spring configuration locations that support them.

## 5. Defining the root object

The root object is the starting object for properties without a `#` prefix. If an expression uses:

~~~text
total >= #minimumTotal and customer.active
~~~

then total and customer must exist on the root object or be handled by a corresponding PropertyAccessor.

An expression profile should document:

- The concrete Java type of the root object.
- Which properties are read.
- Data type and nullability of each property.
- Nested properties and existence conditions.
- Source that constructs the root object.
- Whether the root object is mutable.
- Whether the root object contains sensitive data or broad-privilege objects.

Prefer a dedicated DTO or view containing only the necessary data. If the expression only needs total, status, and customerActive, there is no need to pass an entire entity along with relationships to repositories, credentials, or services.

A small root object makes expressions easier to understand, tests easier to write, and limits the data the expression can reach.

## 6. Declaring variables explicitly

Variables are registered in EvaluationContext and referenced with `#`:

~~~java
context.setVariable("minimumTotal", new BigDecimal("100.00"));
context.setVariable("currentUserId", "U-1024");
context.setVariable("featureEnabled", true);
~~~

For each variable, document:

| Attribute | Content |
|---|---|
| Name | Name after the `#` sign |
| Java type | Concrete registered type |
| Required | Whether it must be provided |
| Nullable | Whether it can accept null |
| Source | Java component providing the value |
| Constraints | Value range or format |
| Lifecycle | Creation and update timing |
| Purpose | Meaning in the rule |

Do not merely document a variable as "number" or "user". For example, minimumTotal should be described as BigDecimal, required, non-null, and sourced from pricing policy.

Distinguish an unregistered variable from a registered variable whose value is null. If a variable is required, validate before evaluating. If a variable is optional, clearly document how the expression handles it using null checks, safe navigation, or Elvis.

## 7. Distinguishing root properties, variables, and beans

Three syntaxes have distinct meanings:

| Syntax | Source |
|---|---|
| `name` | Property of the current evaluation object |
| `#name` | Variable in EvaluationContext |
| `@name` | Bean resolved via BeanResolver |
| `#root.name` | Property name of the original root object |
| `#this.name` | Property name of the current evaluation object |

If the root object has a name property and the context also has a name variable, `name` and `#name` still read from two different sources.

Bean references require a BeanResolver. In manually constructed contexts, the application can connect a BeanFactory using BeanFactoryResolver:

~~~java
context.setBeanResolver(
    new BeanFactoryResolver(beanFactory)
);
~~~

Document the bean name or alias, bean type, called methods, scope/lifecycle, side effects, and required permissions. Do not expose the entire container if the expression only needs a single value already computed by a service.

## 8. Documenting functions and method invocations

A function is a Java Method registered in EvaluationContext and called using `#functionName(arguments)`.

~~~java
Method method =
    TextFunctions.class.getMethod("normalize", String.class);

context.registerFunction("normalize", method);
~~~

Method invocation on an object uses a different syntax:

~~~text
#customer.getDisplayName()
~~~

Bean methods are invoked via bean references:

~~~text
@pricingService.calculate(#order)
~~~

The profile should document each kind separately: function name and Method signature; target object and instance method; bean name and invoked method. For each method, document argument types, return type, null handling, exceptions, side effects, and potential for repeated invocation.

Prefer pure functions with deterministic results that do not mutate state. If logic requires dependencies, transactions, or external system access, keep it in a Java service and provide only the needed data to the expression.

## 9. Choosing EvaluationContext with least privilege

EvaluationContext determines how SpEL reads properties, calls methods, looks up beans, converts types, and uses functions. Two common choices are:

- StandardEvaluationContext: flexible, supporting many resolvers and SpEL features.
- SimpleEvaluationContext: restricts the feature set and allows selecting appropriate property/method access modes.

For read-only data expressions:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

If read-write data binding or instance method invocation is needed, enable only the exact required capability. Do not switch to a broad context just to push an expression past an error without understanding its dependencies.

Explicitly document the context type, PropertyAccessor, MethodResolver, BeanResolver, TypeConverter, and registered functions. Unused capabilities should also be marked "Not used" to avoid misunderstanding that they were considered and overlooked.

## 10. Property access and write permissions

PropertyAccessor controls reading and writing properties. Read permission does not imply write permission.

If an expression is only for computation or display, use a read-only context. If writing is needed, explicitly define which properties are allowed to change and use an allowlist accessor when per-field restrictions are needed.

For custom PropertyAccessors, documentation should state target types, readable properties, writable properties, accepted value types, and behavior when a property is disallowed. Both nested paths and accessor fallbacks need to be controlled.

Do not treat a public setter as proof that an expression is authorized to write. Sensitive business changes such as role, balance, or ownership should go through Java services with explicit authorization and validation.

## 11. Type conversion and validation

SpEL uses the EvaluationContext's TypeConverter when an operation requires a target type different from the source type. StandardTypeConverter can connect to a Spring ConversionService.

For example, a string can convert to Integer if supported by a converter. However, successful conversion does not prove the value is valid. The number 500 may be a valid Integer yet exceed business limits.

Distinguish:

- Conversion: changing type or representation.
- Validation: checking structure, value ranges, cross-field relationships, and business rules.
- Authorization: determining whether the caller is allowed to perform the action.

Document converters, ConversionService, supported type pairs, formats, locales, timezones, and null/empty string handling. Validation and authorization must be performed at the appropriate layer rather than handing full responsibility to the expression.

## 12. Collection operations and data types

SpEL supports selection, projection, and first/last selection:

~~~text
#orders.?[total >= #minimumTotal]
#orders.![id]
#orders.^[status == 'PAID']
#orders.$[status == 'PAID']
~~~

The profile must describe collection type, element type, ordering, nullability, and the result when no element matches.

Selection normally returns an empty collection when no elements match. Projection creates results corresponding to source elements and does not filter automatically. First/last selection returns null if no element is found.

Distinguish an empty collection from null. An empty collection is a valid object with zero elements; null is the absence of a collection reference. If both states share the same business meaning, normalize before evaluating. If they differ, keep them separate and test them separately.

In collection operations, `#this` can be the element under evaluation; `#root` remains the original root object. Document each property's data source to avoid misreading between elements and root.

## 13. Nullability and safe expressions

Intermediate objects can be null. For example:

~~~text
#customer?.address?.city ?: 'Not provided'
~~~

Safe navigation protects access on null references; Elvis provides a replacement value when the left-hand side matches the operator's rules.

Do not use fallbacks to hide missing required data. If customer is required, validate before evaluating or report an explicit business error.

Document nullability of the root object, variables, nested properties, collections, and elements. Test both allowed nulls and nulls that must be rejected. For collections, test null, empty, no-match, and matching cases separately.

## 14. Result type and output contract

Each expression should have an expected result type:

- Boolean for conditions.
- String for messages or labels.
- BigDecimal for monetary calculations.
- Collection for selection/projection.
- A concrete DTO or object if a structured result is needed.

Document whether the result can be null, whether output conversion is required, what element type a collection holds, and where the value is consumed.

For example:

~~~java
Boolean eligible =
    expression.getValue(context, orderView, Boolean.class);
~~~

Requesting the target type helps callers express the output contract. If the result is used for money, specify currency, scale, and rounding rules at the business layer.

Do not assume the result has the desired type just because one test run returned the right value. Test branches that could return different types.

## 15. Categorizing errors by stage

Errors should be separated by stage:

| Stage | Examples |
|---|---|
| Parse | Invalid syntax, missing delimiter, wrong ParserContext |
| Context setup | Missing variable, resolver, or function |
| Property/method access | Non-existent property, disallowed method |
| Conversion | Cannot convert value to target type |
| Runtime data | Null root or intermediate property, out-of-range index |
| Business validation | Right type of value, but out of bounds |
| Authorization | Caller lacks permission to perform the action |

ParseException/SpelParseException typically relate to syntax parsing. EvaluationException/SpelEvaluationException relate to evaluation. Invoked methods or getters can also throw their own exceptions; preserve the cause chain to identify the origin.

Fixed expressions should be parsed and checked for dependencies at startup. Request data is validated at runtime. Do not catch every exception and arbitrarily return null or a default value, as that can hide configuration errors.

## 16. Building a functional test suite

Each expression needs tests for:

- Normal values.
- Each conditional branch.
- Exact boundary values and just outside boundaries.
- Missing or null variables.
- Null root object if possible.
- Null nested properties.
- Null, empty, no-match, and matching collections.
- Incompatible data types.
- Function or method throwing an exception.
- Return type and returned content.

JUnit 5 can use parameterized tests to run the same expression against multiple datasets:

~~~java
@ParameterizedTest
@CsvSource({
    "true, PAID",
    "false, PENDING"
})
void mapsPaymentState(boolean paid, String expected) {
    SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

    context.setVariable("paid", paid);

    Expression expression =
        new SpelExpressionParser().parseExpression(
            "#paid ? 'PAID' : 'PENDING'"
        );

    assertEquals(
        expected,
        expression.getValue(context, String.class)
    );
}
~~~

Tests must verify both result and type when the type is part of the contract. For first/last selection, control collection ordering. For projection, inspect each resulting element rather than only checking that the collection is non-null.

## 17. Positive and negative tests for access permissions

Positive tests confirm required operations are permitted: reading properties, using variables, calling functions, or accessing approved beans.

Negative tests confirm operations beyond requirements are denied:

- Writing properties in a read-only context.
- Reading properties not on the allowlist.
- Calling methods that are not enabled.
- Referencing beans that are not provided.
- Calling unregistered functions.
- Using type references or constructors outside scope.

After an operation is denied, verify the object was not mutated. Do not assert only that an exception was thrown; confirm state remains intact.

When narrowing a context, run the same test suite against the old and new configurations. Approved behavior must stay unchanged; excess capabilities must be removed.

## 18. Protecting expressions and input data

Expressions are executable code. If users or external sources can modify expressions, treat template editing permission as permission to alter logic.

Principles:

1. Never concatenate user data directly into expression sources.
2. Pass data via strongly typed variables.
3. Use small root DTOs without services or secrets.
4. Prefer read-only contexts and restricted accessors.
5. Do not provide a BeanResolver unless bean references are needed.
6. Register only approved functions.
7. Restrict method invocation, type references, and constructor invocations.
8. Validate expression length and origin.
9. Encode output for HTML, attribute, URL, or email contexts.
10. Log identifiers/versions and sanitized errors, without logging tokens or full sensitive objects.

ParserContext is not a sandbox. Parsing succeeding does not prove an expression is safe. The real boundary lies in the supplied data, resolvers/accessors, and privileges of objects the expression can reach.

## 19. Managing templates and dependency changes

When an expression changes, its dependencies can change too. Adding `#discountRate` creates a variable dependency; adding `@pricingService.calculate(...)` creates a bean dependency; adding functions or methods creates new permission and data type requirements.

For expressions stored outside code, manage:

- Identifier and version.
- Source expression or template.
- ParserContext and parser configuration.
- Root object type and property paths.
- Variable names, Java types, and nullability.
- Bean names, aliases, and method signatures.
- Function signatures.
- Accessors, resolvers, and converters.
- Expected result type and errors.
- Positive/negative tests.
- People or workflows authorized to change expressions.

When updating, test the expression with the expected context before release. Do not edit a string and forget to update context-building code; also do not add global capabilities just to support a single expression.

## 20. Measuring performance before enabling the compiler

SpEL has an interpreted mode and a compiler mode. The compiler can help expressions evaluated repeatedly with stable data types, but does not guarantee every expression will be faster.

Three common modes:

| Mode | Behavior |
|---|---|
| OFF | Interpreted only |
| IMMEDIATE | Prefers compiled execution whenever possible |
| MIXED | Can fall back to interpreted when the compiled expression is no longer suitable in supported cases |

Measure parse, evaluate, warm-up/compile, and context setup separately. If production parses once while the benchmark parses in every loop iteration, the measurement does not reflect the real workload.

Use representative expressions and data types. Test root objects, variables, nulls, different implementations, and collection sizes. A microbenchmark on a simple arithmetic expression does not represent an entire application.

## 21. Benchmarks and operational metrics

JMH is better suited than a hand-written loop using `System.nanoTime()` for microbenchmarks. Separate setup from the measured method if production also reuses the Expression:

~~~java
@State(Scope.Thread)
public class SpelBenchmark {

    private Expression expression;
    private StandardEvaluationContext context;

    @Setup(Level.Trial)
    public void setup() {
        ExpressionParser parser = new SpelExpressionParser();
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

Compare OFF, IMMEDIATE, and MIXED with the same expression, data, warm-up, measurement, and forks. Track throughput, average, p50, p95, p99, allocation rate, GC, CPU, startup time, and error rate.

Measure both microbenchmarks and end-to-end. If an expression calls a database or network service, external latency may dwarf SpEL cost. Separate expression overhead from service cost to know what the compiler actually improves.

## 22. Conditions for choosing a compiler mode

Before enabling the compiler, verify:

- Is the expression invoked often enough to recoup compilation cost?
- Is the AST structure supported by the compiler?
- Are the types of the root object and variables stable?
- Does compiled execution preserve results equivalent to interpreted mode?
- Do tail latency, allocation, and GC change adversely?
- Is the ClassLoader compatible with accessed types?
- Can it be rolled back to OFF if errors occur or gains disappear?

OFF is the baseline. Only select IMMEDIATE or MIXED when benchmarks and functional tests confirm a benefit. MIXED is not a mechanism for handling all exceptions; business errors or exceptions inside getters/services still must be handled according to contract.

Roll out in a controlled manner in staging or canary, monitor sufficient representative workloads, and retain rollback capability.

## 23. Example integrated expression profile

A short record can be structured as follows:

~~~text
Expression ID: order-eligibility-v1
Purpose: Check whether an order meets the minimum threshold

Source:
  total >= #minimumTotal and active

Parser:
  Type: SpelExpressionParser
  ParserContext: Plain expression
  CompilerMode: OFF

Root:
  Type: OrderView
  total: BigDecimal, required, non-null
  active: boolean

Variables:
  minimumTotal:
    Type: BigDecimal
    Required: Yes
    Nullable: No
    Source: PricingPolicy

Beans: None
Functions: None
Method invocation: Not required
Property access: Read-only data binding
BeanResolver: Not configured
Custom TypeConverter: None

Result:
  Type: Boolean
  Nullable: No

Errors:
  Invalid expression syntax
  Missing minimumTotal
  Incompatible total type

Tests:
  Below threshold
  Equal to threshold
  Above threshold
  Missing variable
  Null root
  Access denied for writes

Security:
  Root is a read-only view
  No bean or side-effecting method exposed

Performance:
  Parse once
  Evaluate per request
  Compiler mode selected after benchmark
~~~

This is an illustrative template. When applying it, replace all types, names, and conditions with real application data. Unused capabilities must be explicitly marked None or Not required.

## 24. Checklist before taking an expression to production

**Syntax and parser**

- The expression has a clear purpose and identifier.
- ParserContext matches plain expression or template.
- Expression is pre-parsed before use if the source is fixed.
- Parser configuration and compiler mode are documented.

**Data and context**

- Root object has a concrete type and small scope.
- Variables have clear types, sources, required flags, and nullability.
- Beans/functions are provided only when needed.
- Accessors and resolvers match required permissions.
- Mutable contexts are not shared across inappropriate scopes.

**Results and errors**

- Result type and nullability are defined.
- Conversion is separated from validation.
- Parse errors and evaluation errors are categorized.
- Cause chains are preserved.
- Logs do not contain secrets or sensitive data.

**Testing and security**

- Both conditional branches are tested.
- Null, empty, no-match, and boundary cases are tested.
- Positive and negative permission tests exist.
- Expressions from external sources are treated as executable code.
- Output is encoded appropriately for its context.

**Performance and operations**

- Parse, evaluate, and context setup are measured separately.
- Benchmarks use realistic workloads and proper warm-up.
- Throughput, latency distribution, allocation, GC, and error rate are monitored.
- Compiler is enabled only after benefits are confirmed.
- Canary and rollback plans are in place.

## 25. Key takeaways

A SpEL expression is not merely a syntax string. It is a component running within a contract made of parser, root object, variables, beans, functions, accessors, resolvers, converters, result type, and runtime data.

Document dependencies and access permissions explicitly; use small root DTOs and least-privilege contexts; separate parsing from evaluation, conversion from validation, and configuration errors from data errors; test both valid branches and denied operations; and optimize with the compiler only based on representative benchmarks.

Expressions should focus on short, readable, testable rules. Complex business logic, authorization, and side-effecting operations belong in Java services with clear contracts. Maintain profiles, tests, and performance metrics together so every expression change can be evaluated and operated under control.

## References

- [Spring Framework Reference — Spring Expression Language](https://docs.spring.io/spring-framework/reference/core/expressions.html)
- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework Reference — Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html)
- [StandardEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)
- [SimpleEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
- [SpelParserConfiguration Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelParserConfiguration.html)
- [JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh)