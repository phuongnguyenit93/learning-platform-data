# Using Variables and Functions in a Minimal EvaluationContext

## Objectives

`EvaluationContext` provides the data and rules that Spring Expression Language (SpEL) uses when evaluating expressions. A context can hold a root object, variables, property accessors, method resolvers, type conversion, and other resolution mechanisms.

For a small rule, you often only need a root DTO, a few variables, and a pure function. `SimpleEvaluationContext` is a builder-based choice to enable a more restricted set of features than `StandardEvaluationContext`. It supports variables and functions, and can configure property access in read-only mode.

This lesson puts all three parts together into a complete example: passing data into the context with `setVariable`, registering a function with a `Method`, and evaluating an expression against a root object. The goal is to keep the context small, clear, and providing only the capabilities the rule needs.

## 1. Three components in a single evaluation

An expression typically draws data from three places:

| Component | How it is referenced in SpEL | Value source |
| --- | --- | --- |
| Root object | Unprefixed property, `#root`, or `#this` | Object passed to `getValue(...)` or root set on the context. |
| Variable | `#variableName` | Value registered by the application using `context.setVariable(...)`. |
| Function | `#functionName(arguments)` | `Method` or `MethodHandle` registered in the context. |

For example:

~~~spel
active == true and #isAtLeast(age, #minimumAge)
~~~

In this expression, `active` and `age` are read from the root object; `#minimumAge` is a variable; `#isAtLeast(...)` invokes the registered function. The `#` sign appears before variables and functions, and does not appear in the name passed to `setVariable`.

## 2. Creating a simple root DTO

The root object should contain only the data the rule needs. Avoid passing entire entities or service objects if only a few fields are needed.

~~~java
public final class CustomerView {
    private final String name;
    private final int age;
    private final boolean active;

    public CustomerView(String name, int age, boolean active) {
        this.name = name;
        this.age = age;
        this.active = active;
    }

    public String getName() {
        return name;
    }

    public int getAge() {
        return age;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

The context's property accessor reads the corresponding getters. Keep getters simple and do not perform database queries, network calls, file access, or state mutations. Read-only binding prevents expressions from writing properties via accessors, but does not by itself prove that a getter is read-only.

## 3. Creating pure Java functions

Functions are registered using a `Method` or `MethodHandle`. When registering a `Method`, the method must be static. Use public methods with clear signatures and predictable results.

~~~java
public final class RuleFunctions {

    private RuleFunctions() {
    }

    public static boolean isAtLeast(Integer actual, Integer minimum) {
        return actual != null
                && minimum != null
                && actual >= minimum;
    }

    public static String normalize(String value) {
        return value == null ? null : value.trim().toLowerCase(Locale.ROOT);
    }
}
~~~

`isAtLeast` clearly defines how null is handled: if either argument is null, it returns false. `normalize` returns null if the input is null. Specifying null behavior inside the function keeps expressions shorter and easier to test.

Do not register functions that perform database updates, send messages, call URLs, read/write files, or mutate shared state. Functions can be invoked many times during a single evaluation, especially when placed inside selection or projection.

## 4. Creating SimpleEvaluationContext and registering variables

For rules that only need to read properties, use `forReadOnlyDataBinding()`. `SimpleEvaluationContext` supports `setVariable(...)` to register variables and functions:

~~~java
ExpressionParser parser = new SpelExpressionParser();

EvaluationContext context = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .build();

context.setVariable("minimumAge", 18);
context.setVariable("countryCode", "VN");
~~~

The expression references those values using `#minimumAge` and `#countryCode`:

~~~spel
age >= #minimumAge and countryCode == #countryCode
~~~

In the example above, if the root object also has a `countryCode` property, the unprefixed name is the root property; `#countryCode` is the variable in the context. Use variable names distinct from property names whenever possible to avoid confusion.

A variable can be a scalar, enum, collection, or small DTO/value object. Only put data the expression actually needs into the context; avoid registering entire requests, sessions, repositories, or services just for convenience.

## 5. Registering a function in SimpleEvaluationContext

In `SimpleEvaluationContext`, register a function as a variable whose value is a `Method`:

~~~java
Method isAtLeast = RuleFunctions.class.getMethod(
        "isAtLeast", Integer.class, Integer.class);

context.setVariable("isAtLeast", isAtLeast);
~~~

Then invoke the function in the expression:

~~~spel
#isAtLeast(age, #minimumAge)
~~~

Function references are a distinct feature of SpEL. You do not need to enable general instance method invocation with `withInstanceMethods()` just to call a registered function. `withInstanceMethods()` opens the ability to invoke instance methods on objects in expressions; only enable it when the use case genuinely requires it.

Functions and variables share a single namespace. Do not register a variable and a function with the same name; the later registration can replace the earlier value in the context.

## 6. Complete example: root, variable, and function

The following example combines all three components in one expression:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Method isAtLeast = RuleFunctions.class.getMethod(
        "isAtLeast", Integer.class, Integer.class);

EvaluationContext context = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .build();

context.setVariable("minimumAge", 18);
context.setVariable("isAtLeast", isAtLeast);

CustomerView customer = new CustomerView("Lan", 28, true);

Expression rule = parser.parseExpression(
        "active == true and #isAtLeast(age, #minimumAge)");

Boolean eligible = rule.getValue(
        context, customer, Boolean.class);
~~~

The result is `true` because the customer is active and age meets the threshold. In this `getValue` call:

- `customer` is the root object.
- `active` and `age` are properties of root.
- `#minimumAge` is a variable with value 18.
- `#isAtLeast(...)` calls the registered static method.

The expression only reads a DTO, uses a scalar variable, and invokes a specific function. No type reference, constructor invocation, bean reference, or service object is needed in the context.

## 7. Using functions and variables in collection operations

Variables and functions can also be used in selection and projection. `#this` is the current element of the collection; variables/functions are still looked up in the same evaluation context:

~~~spel
#customers.?[active == true and #isAtLeast(age, #minimumAge)]
~~~

Java example:

~~~java
context.setVariable("minimumAge", 18);
context.setVariable("isAtLeast", isAtLeast);
context.setVariable("customers", customers);

Expression selection = parser.parseExpression(
        "#customers.?[active == true and #isAtLeast(age, #minimumAge)]");

List<?> eligibleCustomers = selection.getValue(context, List.class);
~~~

The function is called for each customer checked by selection. If the collection has thousands of elements, the function may be called thousands of times. Keep functions small, fast, and pure; if a calculation is expensive, precompute it in Java and put the result in the view object.

Projection can also call functions:

~~~spel
#customers.![#normalize(name)]
~~~

Projection produces one result per element. If you need both filtering and transformation, chain selection and projection while keeping traversal cost and intermediate collections in mind.

## 8. Using MethodHandle instead of Method

EvaluationContext allows registering functions using `java.lang.invoke.MethodHandle` in addition to `java.lang.reflect.Method`. MethodHandle is useful when you need a function already bound to a receiver or when the application wants to control how the handle is created.

~~~java
MethodHandle handle = lookup.findStatic(
        RuleFunctions.class,
        "normalize",
        MethodType.methodType(String.class, String.class));

context.setVariable("normalize", handle);
~~~

Expression:

~~~spel
#normalize(name)
~~~

This example illustrates a static method handle. If using a handle for an instance method, bind the receiver beforehand and only bind an object with a narrow, expression-safe API. Do not expose a handle that can invoke services or perform unintended operations.

For simple code, registering a `Method` is usually easier to read. Choose `MethodHandle` when there is a specific reason regarding binding or API; there is no need to use both approaches for the same function.

## 9. When to use StandardEvaluationContext?

`SimpleEvaluationContext` supports variables and functions, but excludes some full SpEL features such as type references `T(...)`, constructors `new`, and bean references `@bean`. It also requires explicitly choosing property/method access.

If the use case needs those features, you can use `StandardEvaluationContext` and configure the minimal required permissions:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext(customer);
context.setVariable("minimumAge", 18);
context.registerFunction("isAtLeast", isAtLeast);
~~~

`StandardEvaluationContext` has reflective property/method access and constructor/type resolution enabled by default. Therefore, use it only when expressions need broader capabilities; if expressions do not need to call arbitrary methods, restrict resolvers/accessors or continue using `SimpleEvaluationContext`.

Do not treat `SimpleEvaluationContext` as a general-purpose security sandbox. Spring warns that feature restrictions are provided on a best-effort basis and do not guarantee that expressions from untrusted sources are safe. Getters, property accessors, and registered functions can still execute code.

## 10. Namespace and naming rules

Variables and functions share the same namespace in a context. Therefore:

- Give variables and functions distinct names.
- Use names that describe roles, such as `minimumAge`, `allowedCountries`, `normalizeCode`.
- Do not use `this` or `root` for application data; those are special SpEL variables.
- Register names without the `#` sign; only add `#` when writing the expression.
- Register all variables/functions before evaluating the expression.

For example:

~~~java
context.setVariable("minimumAge", 18);
context.setVariable("normalizeCode", normalizeMethod);
~~~

~~~spel
#normalizeCode(customerCode) == 'vn'
~~~

Do not change a variable name's meaning into a function between evaluations. Sharing the same namespace makes such configurations hard to read and prone to runtime errors.

## 11. Managing lifecycle and reusing contexts

Parsers and parsed expressions can be reused. Variables and the root object, however, often depend on the request or evaluation:

~~~java
Expression rule = parser.parseExpression(
        "active and #isAtLeast(age, #minimumAge)");

EvaluationContext context = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .build();
context.setVariable("isAtLeast", isAtLeast);

for (CustomerView customer : customers) {
    context.setVariable("minimumAge", 18);
    Boolean eligible = rule.getValue(
            context, customer, Boolean.class);
}
~~~

This snippet illustrates expression reuse. In multi-threaded applications, avoid sharing a mutable context across requests if each request can change variables or context data. Create a context per request/evaluation or use a factory that creates preconfigured contexts.

Do not confuse reusing an expression with caching results: each `getValue` call still evaluates the expression using the current root and variables. Functions are also invoked again whenever evaluation reaches the function call.

## 12. Handling null, data types, and errors

Register variables with clear data types so expressions are predictable. For example, use `Integer` for numeric thresholds, `Set<String>` for lists of allowed codes, and enums for fixed statuses.

~~~java
context.setVariable("minimumAge", Integer.valueOf(18));
context.setVariable("allowedRegions", Set.of("VN", "SG"));
~~~

~~~spel
#allowedRegions.contains(region)
~~~

Define null behavior for functions and variables:

- If null is invalid input, validate before calling `getValue`.
- If null is a valid state, write functions that return a clear result for null.
- Do not rely on implicit conversion when overloads or argument types are ambiguous.
- If the expression needs a Boolean, require an explicit Boolean result and handle null as a separate state.

Parse errors and evaluation errors are two different kinds of errors. Parse sources before storing rules; during evaluation, handle `EvaluationException` at the application boundary. Do not return exception messages or raw expressions to end users.

## 13. Keeping functions pure and the context small

A registered function is an execution path into Java code. Even when the context is SimpleEvaluationContext, a function can still do whatever that method is written to do.

The design should follow these principles:

- Register only functions the expression genuinely needs.
- Prefer pure, deterministic static methods without side effects.
- Do not call databases, HTTP, filesystem, message brokers, or processes from functions.
- Do not pass services, repositories, application contexts, or broad-privilege objects into variables.
- Do not let functions retain or mutate the input root object/collection.
- Limit the size and value domain of variables.
- Use DTO/view objects with only the necessary properties.

For external data such as query results, load the data in the service layer beforehand and pass a bounded collection or map into the context. Do not use functions to create hidden I/O inside a rule.

## 14. Testing a minimal EvaluationContext

Tests should verify both valid results and unsupported capabilities:

~~~java
@Test
void evaluatesWithRootVariableAndFunction() throws Exception {
    ExpressionParser parser = new SpelExpressionParser();
    EvaluationContext context = SimpleEvaluationContext
            .forReadOnlyDataBinding()
            .build();

    Method isAtLeast = RuleFunctions.class.getMethod(
            "isAtLeast", Integer.class, Integer.class);
    context.setVariable("minimumAge", 18);
    context.setVariable("isAtLeast", isAtLeast);

    CustomerView customer = new CustomerView("Lan", 28, true);
    Boolean result = parser.parseExpression(
            "active and #isAtLeast(age, #minimumAge)")
            .getValue(context, customer, Boolean.class);

    assertThat(result).isTrue();
}
~~~

Add tests for these cases:

- Inactive customer returns false.
- Age below threshold returns false.
- Unregistered variable produces an evaluation error.
- Unregistered function produces an evaluation error.
- Function receiving null handles it according to the defined contract.
- Expressions using `T(...)`, `new`, or `@bean` are rejected in SimpleEvaluationContext.
- Function does not mutate input or shared state.
- Two requests using different variables do not misread each other's values.

In security tests, verify side effects using counters or probes; checking only for exceptions does not prove dangerous code was not executed.

## 15. Common errors and how to fix them

| Symptom | Causes to check | Resolution |
| --- | --- | --- |
| `#minimumAge` has no value | Variable not registered or name mismatch. | Call `setVariable("minimumAge", value)` before evaluation and use `#minimumAge` accurately. |
| `#isAtLeast(...)` function not found | Function not registered, wrong method signature, or name overwritten by another variable. | Obtain the right public Method, register with `setVariable`, and avoid namespace collisions. |
| Function does not run in SimpleEvaluationContext | Confusing function reference with instance method invocation. | Register `Method`/`MethodHandle` as a variable; no need to enable general instance methods for function references. |
| `name.toUpperCase()` does not work | General instance method invocation is disabled by default. | Only enable `withInstanceMethods()` if needed, and restrict exposed objects. |
| `T(...)`, `new`, or `@bean` does not work | These features are not supported by SimpleEvaluationContext. | Use Java to prepare values or switch to StandardEvaluationContext with restricted permissions. |
| Variable replaced by function or vice versa | Variables and functions share the same namespace. | Use distinct names and register context items in a single place. |
| Function called too many times | Function is inside selection/projection or expression is re-evaluated. | Keep functions fast and pure; precompute expensive data. |
| One request reads another request's variable | Sharing a mutable context across concurrent evaluations. | Create a separate context per request/evaluation. |
| Read-only expression still performs I/O | Getter or function accesses resources. | Use pure DTO getters and register only non-I/O functions. |

## Key takeaways

- `EvaluationContext` provides the root object, variables, functions, and access strategies for SpEL.
- Use unprefixed properties or `#root`/`#this` to read root; use `#name` for variables; use `#function(args)` for functions.
- `SimpleEvaluationContext.forReadOnlyDataBinding()` fits rules that only read properties.
- `SimpleEvaluationContext.setVariable(...)` registers both variables and functions; a function can be a `Method` or `MethodHandle`.
- When registering a `Method`, use a public static method with a clear signature; `StandardEvaluationContext.registerFunction(...)` is a convenience API when using Standard context.
- Functions and variables share a namespace; do not reuse the same name.
- Function references are not synonymous with general instance method invocation; there is no need to enable `withInstanceMethods()` just to call registered functions.
- SimpleEvaluationContext excludes `T(...)`, `new`, and `@bean`, but is not a general sandbox for untrusted expressions.
- Reusing parsers/expressions does not cache results; each `getValue` still uses the root, variables, and functions of that evaluation.
- Use separate contexts when variables change per request; keep functions pure, fast, and free of resource access.

## References

- [Spring Framework Reference — Variables](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/variables.html)
- [Spring Framework Reference — Functions](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/functions.html)
- [Spring Framework Reference — EvaluationContext and SimpleEvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework API — EvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationContext.html)
- [Spring Framework API — SimpleEvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
- [Spring Framework API — StandardEvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)