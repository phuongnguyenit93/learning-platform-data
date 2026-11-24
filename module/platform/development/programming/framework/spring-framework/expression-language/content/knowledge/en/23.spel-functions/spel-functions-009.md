# Avoiding Functions with Side Effects or Unintended Resource Access in SpEL

## Objectives

SpEL allows applications to register Java methods as functions so expressions can invoke them using the `#functionName(...)` syntax. This mechanism is useful when reusing a small calculation or rule across multiple expressions. However, functions are invoked while an expression is being evaluated. If a method writes data, sends messages, accesses the network, reads files, or queries a database, an expression that appears read-only can trigger external actions.

Therefore, functions intended for SpEL should have a narrow scope, predictable results, and no side effects. Operations involving external resources should be executed explicitly in the application layer; expressions only receive prepared data and make decisions or calculations on that data.

## 1. What is a Function in SpEL?

A function is a Java `Method` registered in an `EvaluationContext` and called from an expression using `#`:

```spel
#normalize(name)
#isEligible(age, country)
```

With `StandardEvaluationContext`, a method can be registered using `registerFunction`. The registered method must be static; use a public static method with a clear signature:

```java
public final class TextFunctions {

    private TextFunctions() {
    }

    public static String normalize(String value) {
        return value == null ? null : value.trim().toLowerCase(Locale.ROOT);
    }
}
```

Registering and calling the function:

```java
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context = new StandardEvaluationContext(customer);

Method normalize = TextFunctions.class.getMethod(
        "normalize", String.class);
context.registerFunction("normalize", normalize);

Expression expression = parser.parseExpression("#normalize(name)");
String normalizedName = expression.getValue(context, String.class);
```

The name passed to `registerFunction` is `normalize`, without `#`. The `#` symbol only appears when referencing the function in SpEL. A `Method` can also be registered as a variable using `setVariable`; `registerFunction` expresses more clearly the intent of using that method as a function.

## 2. Functions Should Perform Pure Calculations

Functions suited for SpEL typically take arguments, compute on them, and return a result. Given the same set of arguments, a function should return the same result and not mutate external state.

Examples of typically suitable functions:

- Normalizing strings, changing case, or formatting a value.
- Computing sums, ratios, scores, or derived values from arguments.
- Checking a pure condition such as whether a code matches a format.
- Mapping an enum or business code to a display label from an already available lookup table.
- Checking whether a value belongs to a set already passed into the context.

Example:

```java
public final class RuleFunctions {

    private RuleFunctions() {
    }

    public static boolean isAllowed(String role, Set<String> allowedRoles) {
        return role != null && allowedRoles.contains(role);
    }

    public static BigDecimal withTax(BigDecimal amount, BigDecimal rate) {
        if (amount == null || rate == null) {
            return null;
        }
        return amount.multiply(BigDecimal.ONE.add(rate));
    }
}
```

These methods only read arguments and produce results. They do not write to a database, mutate input objects, or call another system.

## 3. Side Effects to Avoid

Do not register functions that perform the following if expressions are used as rules or calculations:

| Action type | Examples | Why unsuitable in a SpEL function |
| --- | --- | --- |
| Writing data | `saveOrder`, `updateAccount`, `deleteRecord` | An expression could unintentionally mutate state when expected only to evaluate a condition. |
| Sending messages | `publishEvent`, `sendEmail`, `sendSms` | Re-evaluating the expression can send duplicate notifications. |
| Network calls | HTTP client, REST API, remote service | Introduces latency, timeouts, network errors, and unpredictable call counts. |
| Database access | Repository query, transaction, or stored procedure | Can cause hidden queries inside selection/projection or on every `getValue`. |
| File access | Reading/writing files, listing directories | Results depend on filesystem state and may expose or modify data. |
| Mutating state | Incrementing counters, modifying shared objects, updating caches | Results depend on call history and can vary between evaluations. |
| Resource-heavy tasks | Compressing files, processing large images, unbounded loops | A simple expression can tie up CPU, memory, or threads for a long time. |

Not every method with side effects is always wrong in every application. The issue is that functions in expressions are often invoked at times and frequencies that expression authors do not easily notice. If an action needs to be performed, invoke it in a controlled Java workflow where the application can manage transactions, retries, logging, authorization, and errors.

## 4. Functions Can Be Called Multiple Times

Registering a function does not mean SpEL executes it once and caches the result. The function is invoked whenever evaluation reaches that call. If the same expression is evaluated multiple times, the function can be called repeatedly.

This is especially important with selection and projection:

```spel
users.?[#isEligible(#this.age, #this.country)]
products.![#formatPrice(#this.price)]
```

In selection, the function may be called for each user whose condition needs checking. In projection, the function may be called for each projected product. If the expression is re-evaluated on another request or at another processing step, the calls are executed again as well.

Short-circuiting may prevent a branch from being evaluated, but you should not rely on it to control side effects. Whether a function is invoked depends on the expression's evaluation path and runtime data.

Parsing an expression once only reuses the parsed structure; it does not automatically cache function results. If an external service needs to be called exactly once, call the service in the application layer and pass the result into the context.

## 5. Supply External Data to the Context Before Evaluation

If a rule needs data from a database or API, load the data beforehand via a service/repository, then put the result into the `EvaluationContext` as a root property or variable.

For example, instead of registering a `loadCountryName(code)` function to query the database every time an expression needs a country name, preload a map:

```java
Map<String, String> countryNames = countryRepository.findAllNames();

StandardEvaluationContext context = new StandardEvaluationContext(customer);
context.setVariable("countryNames", countryNames);
```

The expression simply looks up already available data:

```spel
#countryNames[countryCode] == 'Vietnam'
```

With this approach, the map lookup creates no hidden database queries. The application controls load timing, data scope, caching, errors, and access permissions before the expression runs.

If the data is large or requires conditional querying, perform queries in the service layer according to an explicit plan. Do not use functions in SpEL as a replacement for repositories or the orchestration layer.

## 6. Full Example: Registering a Pure Function and Using It in Selection

Suppose you need to select users with an active status. You can write a pure helper:

```java
public final class UserRuleFunctions {

    private UserRuleFunctions() {
    }

    public static boolean isActive(Boolean active) {
        return Boolean.TRUE.equals(active);
    }
}
```

Registering and using:

```java
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context = new StandardEvaluationContext(account);

Method isActive = UserRuleFunctions.class.getMethod(
        "isActive", Boolean.class);
context.registerFunction("isActive", isActive);

Expression expression = parser.parseExpression(
        "users.?[#isActive(#this.active)]");

List<?> activeUsers = expression.getValue(context, List.class);
```

`isActive` returns true when the value is `Boolean.TRUE`; both false and null return false according to the rule explicitly written in the helper. The function accesses no resources, does not mutate users, and can be called many times without changing application state.

## 7. Distinguishing Functions from Instance Methods and Spring Beans

SpEL has several ways to invoke Java code. They do not carry the same implications:

| Syntax | Mechanism |
| --- | --- |
| `#normalize(name)` | Calls a function registered in the evaluation context. |
| `#formatter.format(name)` | Calls an instance method on the object registered under the `formatter` variable. |
| `@formatterBean.format(name)` | Calls a method on a Spring bean when the context has a suitable `BeanResolver`. |
| `T(com.example.Formatters).normalize(name)` | Calls a static method via a type reference. |

A function is a method reference exposed under a name in the context. Beans or instance methods can carry broader privileges, such as accessing repositories or mutating state. Only expose them when the expression genuinely needs them and those privileges are restricted.

If a helper only performs a pure calculation, registering a static function with a narrow signature is usually easier to control than exposing an entire large service. If business or resource operations are needed, call services in Java before or after evaluating the rule in a clear flow.

## 8. Designing Functions with Clear Inputs and Outputs

A safe function should have a simple contract:

- A name indicating the specific action or calculation.
- Clear parameter count and parameter types.
- No dependence on mutable static variables or global state.
- Does not mutate arguments or shared objects.
- Handles nulls and boundary inputs according to defined rules.
- Returns a value with a stable type, preferably an immutable/value object.
- Does not retain sensitive data or request objects after returning the result.

Avoid generic names like `execute`, `process`, `invoke`, or `run` if they hide multiple kinds of actions. Names like `normalizeCustomerCode` or `isWithinLimit` help expression readers understand what the function does.

If a calculation needs multiple pieces of data, pass the required values as arguments or group them in a read-only input object. Avoid letting functions look up additional data via singletons, static service locators, or global state.

## 9. Restricting Permissions of Registered Functions

What an expression can invoke depends on the functions and access capabilities provided in the evaluation context. Therefore, registering functions is also a permission decision.

For expressions coming from users, external configuration files, or not-fully-trusted sources:

- Only register functions truly necessary for the rules.
- Do not register helpers that can execute commands, access arbitrary filesystem paths, call arbitrary URLs, or perform administrative actions.
- Do not expose an entire service/repository just so an expression can call one small method.
- Validate and limit argument sizes/lengths before evaluation.
- Use a separate context per request if variables or the root object vary by request.
- Inspect both registered functions and other objects/methods accessible from root and context.

Simply registering a few functions is part of an allowlist; it does not automatically turn every expression into a complete sandbox. A root object with many public methods or a broad bean resolver can still open other access paths.

## 10. Error Handling and Predictability

Functions can throw exceptions like regular Java methods. An error while invoking a function will fail evaluation and be reported by SpEL through an evaluation exception; the root cause is usually in the cause chain.

To make errors easy to handle:

- Validate inputs at the application layer before calling `getValue`.
- Keep functions short and performing only a single calculation.
- Do not swallow exceptions and return an ambiguous default value.
- If an input case is valid yet produces no result, return a meaningful value such as null or Optional per a supported contract, then handle it explicitly in the expression/application.
- Log errors at the application boundary with sufficient context without logging sensitive data.
- Do not perform network/database retries inside a function; retries belong in a layer that can manage timeouts, idempotency, and attempt limits.

In particular, do not use a blanket default value such as `false` for all errors. `false` can be a valid business outcome and cause infrastructure errors to be masked.

## 11. Checking a Function Before Registration

Before putting a function into the evaluation context, determine:

1. Is the method static and does it have a clear signature?
2. Does it read/write a database, file, network, cache, or message broker?
3. Does it mutate input objects, global state, or shared data?
4. Can it be called multiple times in one expression or on each collection element?
5. Is the result deterministic for the same set of arguments?
6. Do inputs have length, size, and value-range limits?
7. How are nulls, exceptions, and invalid data handled?
8. Can the needed data be preloaded and passed into the context instead of accessing resources from the function?
9. Does the expression come from an untrusted source, and does the context expose any other permissions?

## 12. Common Errors and Resolutions

| Symptom | Cause to check | Resolution |
| --- | --- | --- |
| `#functionName(...)` cannot find function | Function not registered, name mismatch, or active context differs from configured context. | Register using `registerFunction` before `getValue`; check exact name and context. |
| Function cannot be invoked | Method lacks matching signature, is not static, or is inaccessible. | Use a public static method and retrieve the exact `Method` signature via reflection. |
| Function called multiple times | Expression evaluated multiple times or function sits inside selection/projection. | Design the function to be pure, cheap, and side-effect-free; precompute external data. |
| Rule causes repeated database or HTTP queries | Function hides external resource access. | Load data once in the service layer as needed and pass it into the context. |
| Results change across evaluations | Function depends on clock, random, mutable global state, or external state. | Pass fixed timestamps/values via variables; keep functions deterministic from arguments. |
| Exception from function breaks evaluation | Method throws an error or input is invalid. | Validate beforehand, define clear error contracts, and handle at the application boundary. |
| Expression can invoke too many capabilities | Context exposes overly broad helpers/services. | Narrow the function allowlist and audit other objects/methods in the context. |
| Function mutates data unexpectedly | Helper has side effects or uses shared state. | Move write operations to a Java service flow; functions only compute and return results. |

## Takeaways

- A SpEL function is a Java `Method` registered in the evaluation context and called with `#functionName(...)`.
- Use public static methods with clear signatures; register using `StandardEvaluationContext.registerFunction`.
- Functions should be pure calculations: identical arguments yield identical results, without mutating state or accessing external resources.
- SpEL does not automatically cache function results; calls execute whenever evaluation reaches the function.
- Functions in selection/projection can be invoked for every element; re-evaluated expressions also re-invoke functions.
- Do not perform database, HTTP, file, messaging, or state updates inside rule functions.
- Load external data in the service layer and pass it into the root object or context variables.
- Distinguish functions `#fn(...)`, instance methods `#object.method(...)`, bean references `@bean.method(...)`, and static methods `T(Class).method(...)`.
- Only register necessary functions; a function allowlist does not replace restricting other objects and resolvers in the context.
- Validate inputs, bound costs, handle exceptions clearly, and avoid masking infrastructure errors with default values.

## References

- [Spring Framework Reference — Functions](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/functions.html)
- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework API — StandardEvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)
- [Spring Framework API — EvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationContext.html)