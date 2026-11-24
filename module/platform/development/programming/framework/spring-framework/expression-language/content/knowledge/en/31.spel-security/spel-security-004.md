# Blocking Dangerous Type References, Constructors, and Methods in SpEL

## Objective

Spring Expression Language (SpEL) can do much more than read properties and compare values. Depending on the `EvaluationContext` provided, an expression can reference classes using `T(...)`, instantiate objects using `new`, invoke instance or static methods, access Spring beans using `@beanName`, and traverse property accessors of input objects.

These capabilities are very useful for application-controlled expressions. When an expression or part of an expression source comes from users, external configuration files, or data stored in a database, they can open paths to code execution, resource access, or unexpected resource consumption.

The safety principle is to expose only the exact capabilities a rule needs. If you only need to read a few properties and evaluate conditions, use a restricted context and a simple data object. If type references, constructors, or methods are strictly required, allowlist specific classes and methods while controlling the beans, functions, and property accessors provided.

## 1. Execution Paths That Must Be Controlled

| SpEL Capability | Example | Risk If Opened Too Broadly |
| --- | --- | --- |
| Type reference | `T(java.lang.Math).max(1, 2)` | Can reference classes and invoke static members of those classes. |
| Constructor invocation | `new java.math.BigDecimal('12.50')` | Can instantiate objects, including objects whose constructors consume resources or have side effects. |
| Method invocation | `customer.refresh()` | Can invoke methods on the root object, variables, or nested objects. |
| Bean reference | `@pricingService.calculate(total)` | Can expose services, repositories, or beans with system-level access. |
| Function | `#calculate(value)` | A registered function can execute whatever Java code that method performs. |
| Property/index access | `customer.profile.name`, `items[#index]` | Getters or custom accessors can load data, mutate state, or expand collections. |

It is not only `T(...)` or `new` syntax that warrants attention. An expression without type references can still call methods on exposed objects or trigger logic inside getters.

## 2. Choose SimpleEvaluationContext When Only Data Binding Is Needed

`SimpleEvaluationContext` is designed for a more restricted subset of SpEL features. It does not support type references, constructor invocation, or bean references. Method invocation is disabled by default; applications can opt in to instance methods when truly needed.

For rules that only read properties, start with read-only data binding:

```java
EvaluationContext context = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .build();

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(
        "active == true and age >= 18");

Boolean allowed = expression.getValue(
        context, customerView, Boolean.class);
```

This context fits DTO/view objects with simple properties. There is no need to provide the entire ApplicationContext or domain services if the rule only reads pre-prepared data.

If the expression needs to write properties, `forReadWriteDataBinding()` can enable data-binding write access. Only use this mode when updating objects is a genuine requirement; rules that only perform checks should stay read-only.

### When Instance Methods Are Needed

The builder can enable instance method invocation:

```java
EvaluationContext context = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .withInstanceMethods()
        .build();
```

This is an opt-in for method invocation, not a method-name allowlist. Enable it only when exposed objects have narrow, predictable APIs and contain no methods that write data or access resources. `SimpleEvaluationContext` still does not support `T(...)`, `new`, or `@beanName`.

Read-only also does not guarantee pure, read-only getters. Getters can trigger ORM lazy loading, database queries, service calls, or state mutations. Use view objects with simple getters and expose only the necessary data.

## 3. Restricting Type References with TypeLocator

In `StandardEvaluationContext`, type references `T(...)` are resolved via `TypeLocator`. `StandardTypeLocator` is convenient for internal expressions, but it can locate many classes on the classpath. For expressions that are not fully trusted, replace it with a locator that returns only allowed types.

Example allowlist permitting only `java.lang.Math`:

```java
public final class AllowlistedTypeLocator implements TypeLocator {

    private final Map<String, Class<?>> allowedTypes = Map.of(
            "java.lang.Math", Math.class);

    @Override
    public Class<?> findType(String typeName) throws EvaluationException {
        Class<?> type = allowedTypes.get(typeName);
        if (type == null) {
            throw new EvaluationException("Type is not allowed: " + typeName);
        }
        return type;
    }
}
```

Configuring the context:

```java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setTypeLocator(new AllowlistedTypeLocator());
```

Now the expression can use `T(java.lang.Math)` if method resolution permits the corresponding method. Other types are rejected immediately during the type lookup step.

Type allowlists should use exact, fully qualified class names. Avoid broad rules such as allowing every class in a package or every class starting with a prefix, because a package may contain classes not intended to be exposed.

## 4. Restricting Method Invocation

Method invocation is a code execution path on the root object, property objects, variables, or referenced classes. If the expression does not need to call methods, you can remove all reflective method resolvers:

```java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setMethodResolvers(Collections.emptyList());
```

This blocks method invocation through the resolvers configured in the context. If certain methods are needed, use an allowlisted resolver/filter rather than opening every method on every object.

### Using MethodFilter for Allowed Classes

`StandardEvaluationContext.registerMethodFilter(...)` can restrict the list of methods considered by the reflective method resolver on a specific type:

```java
Set<String> allowedNames = Set.of("max", "min", "abs");

StandardEvaluationContext context = new StandardEvaluationContext();
context.registerMethodFilter(Math.class, methods ->
        methods.stream()
                .filter(method -> allowedNames.contains(method.getName()))
                .toList());
```

This filter applies only to the registered type and the reflective method resolver. If the default resolver is replaced with another resolver, ensure the new resolver enforces the same policy. Other objects in the root/context must also be controlled; restricting methods on `Math` does not automatically restrict methods on another service object.

If method invocation must be allowlisted across multiple classes, register filters for each exposed class or provide a custom `MethodResolver` that resolves only permitted signatures.

## 5. Blocking Constructor Invocation

Constructor invocation uses `ConstructorResolver`. If the expression does not need to instantiate objects, you can remove reflective constructor resolvers from the context:

```java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setConstructorResolvers(Collections.emptyList());
```

Without a matching constructor resolver, expressions of the form `new SomeType(...)` cannot be resolved.

If specific constructors are needed, use a custom `ConstructorResolver` to allow only the required classes and signatures. Do not allowlist solely by package name or solely by class if that class has overloaded constructors with different behaviors.

In many cases, a simpler and safer approach is to create objects in Java and pass the created objects into the root object or variables. This keeps object creation in application code, where inputs can be validated and resources managed.

## 6. Controlling Bean References

Bean references `@beanName` only work when `EvaluationContext` has a `BeanResolver`. If the expression does not need Spring beans, do not configure a resolver. Manually created contexts typically do not have a bean resolver until the application adds one.

If certain beans are needed, do not expose the entire ApplicationContext or a resolver that allows resolving arbitrary beans. Provide a narrow facade with the necessary pure read methods, or implement a resolver that returns only a specific set of beans.

`SimpleEvaluationContext` does not support bean references. This is one reason to choose it when rules only need property data binding.

Do not directly expose repositories, HTTP clients, filesystem services, process runners, message publishers, or administrative beans to untrusted expressions. A public method on a bean can perform external system actions even if the expression syntax looks simple.

## 7. Controlling Functions and Variables

Functions registered in the context typically invoke a Java `Method` via `#functionName(...)` syntax. A MethodResolver allowlist does not automatically replace function checks: function references have their own evaluation mechanism.

Register only necessary functions and prefer pure computations:

```java
Method normalize = TextFunctions.class.getMethod(
        "normalize", String.class);
context.registerFunction("normalize", normalize);
```

Do not register functions that can run commands, access arbitrary URLs, read/write files, send messages, or perform database updates. A function in selection/projection can be called once per element; re-evaluated expressions also call the function again.

Variables must also be controlled. Do not place services or broadly privileged objects into the context just for convenience. Prefer scalars, immutable value objects, bounded collections, and DTOs containing only required properties.

## 8. Property Accessors Are Also a Security Boundary

Even after blocking type references, constructors, and method invocation, an expression can still read properties through registered `PropertyAccessor`s. Reflective accessors can access many getters on exposed objects.

For external rules, restrict the root object to a DTO/view object containing only necessary data. If finer-grained control is needed, provide a custom `PropertyAccessor` permitting only a specific set of properties.

Avoid exposing entities with lazy-loading getters or getters that perform I/O. `forReadOnlyDataBinding()` only restricts writes through the accessor; it does not prove getters are side-effect-free.

Index access must also be considered: maps, lists, and custom `IndexAccessor`s can open additional access paths. If using a custom accessor, support only the intended targets and keys/indices.

## 9. Example Context Configuration with Least Privilege

The following example illustrates a context that disallows type references, constructors, bean references, and method invocation. The expression only reads properties through the selected accessor:

```java
EvaluationContext context = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .build();

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(
        "accountEnabled == true and creditLimit >= #requestedAmount");
```

Place into the context only a view object with the necessary properties and the `requestedAmount` value via the variable mechanism used by the application. Do not place services/repositories into the root.

If an auxiliary calculation is needed, prefer computing it in Java and putting the result into the view object. If methods must be allowed, expose a small object with only safe methods or enable method invocation with a tested allowlist policy.

## 10. User-Supplied Expressions vs. Fixed Expressions

Clearly distinguish two models:

- **Application-managed expressions:** expression sources reside in reviewed internal code or configuration. Full SpEL can be used if the context and access privileges are appropriately designed.
- **User-controlled expressions:** users can submit or edit the expression source. Treat this as code that must be restricted, not ordinary data.

If users only need to select an operation or condition, consider providing a small DSL, a list of permitted operators, or typed configuration fields. Do not require them to submit an arbitrary SpEL snippet when a simple data structure can express the same requirement.

Do not concatenate user data directly into the expression source:

```java
// Avoid building expressions by concatenating input into the source.
String source = "name == '" + userInput + "'";

// Use a fixed expression and pass data through the context.
Expression expression = parser.parseExpression("name == #input");
StandardEvaluationContext context = new StandardEvaluationContext(view);
context.setVariable("input", userInput);
```

Passing input via a variable prevents the data from being interpreted as SpEL syntax. However, if `source` itself is user-controlled, passing variables does not make that source safe; the expression must be restricted or a DSL used.

## 11. Resource and Complexity Limits

Restricting classes and methods does not by itself solve all resource risks. Expressions can consume CPU or memory through large collections, complex regexes, nested property access, exposed methods, or collection auto-growth.

Practical measures:

- Limit expression source length and the number of stored/evaluated expressions.
- Limit collection sizes and the depth of input data.
- Disable auto-grow for null references/collections if the use case does not need it; if enabled, set an appropriate maximum auto-grow size.
- Do not expose methods with unbounded runtime or external service calls.
- Avoid user-controlled regexes without appropriate length and complexity limits.
- Perform evaluation in a layer where timeouts, rate limits, and concurrency controls can be applied if the application requires those limits.
- Do not assume SpEL itself provides a general-purpose sandbox or execution time budget for every expression.

Do not use compiler mode as a security boundary. Whether an expression is interpreted or compiled does not replace restricting type, constructor, method, bean, function, and property access.

## 12. Error Handling and Observability

When an expression attempts to invoke a disallowed type, constructor, or method, evaluation will fail. Handle errors at the application boundary:

- Return safe error messages without exposing stack traces or internal class names to clients.
- Record the expression ID, caller, and policy outcome; avoid logging secrets or full sensitive input data.
- Distinguish invalid expressions, denied permissions, and business errors.
- Do not swallow exceptions and return `true` or a default value that could inadvertently let a rule pass.
- Test both valid cases and attempts to invoke functionality outside the allowlist.

## 13. Pre-Evaluation Expression Checklist

1. Who controls the expression source: the application or the user?
2. Does the expression actually need `T(...)`, `new`, method invocation, or `@bean`?
3. Can read-only `SimpleEvaluationContext` be used instead?
4. Is the root object a small DTO/view object containing only necessary data?
5. Do getters, accessors, and methods access the database, files, network, or shared state?
6. Does TypeLocator allowlist exact classes?
7. Do ConstructorResolver and MethodResolver restrict permitted signatures?
8. Do BeanResolver and functions expose only the minimal APIs?
9. Do variables contain services or broadly privileged objects?
10. Are expression length, collection sizes, regexes, and evaluation cost bounded?
11. Are errors returned safely and logged without leaking sensitive data?

## 14. Common Mistakes and Fixes

| Symptom | Cause to Check | Remediation |
| --- | --- | --- |
| Expression invokes unexpected classes | StandardTypeLocator resolves classes more broadly than needed. | Replace with an allowlisted TypeLocator returning only permitted classes. |
| `new SomeType(...)` still executes | Reflective ConstructorResolver is still configured. | Remove constructor resolvers or use an allowlisted resolver. |
| Dangerous methods can still be called | Reflective method resolver permits methods on exposed objects. | Remove method resolvers if unneeded; if needed, restrict via MethodFilter or custom resolver for every involved target class. |
| Methods blocked but functions still run | Function references are not restricted by MethodResolver alone. | Inspect every registered function; register only pure, allowlisted helpers. |
| `@beanName` resolves unexpectedly | Context has a BeanResolver. | Do not configure a resolver or replace it with one permitting only required beans. |
| Read-only expression still hits the database | Getters or PropertyAccessors perform lazy loading/I/O. | Use pre-populated DTOs and simple accessors. |
| Expression spikes memory usage | Collection auto-grow or input collections/indices are too large. | Disable auto-grow or set limits; validate input sizes. |
| User data alters expression meaning | Input is concatenated directly into expression source. | Use a fixed expression and pass input via typed variables. |
| Compiler configuration treated as a sandbox | Compiler mode does not restrict expression access privileges. | Design context allowlists and resource limits independently of compiler mode. |

## Key Takeaways

- `T(...)`, `new`, method invocation, `@beanName`, functions, and property access are all surfaces that must be controlled.
- Use `SimpleEvaluationContext.forReadOnlyDataBinding()` when only reading properties; it does not support type references, constructors, or bean references.
- Method invocation in SimpleEvaluationContext is off by default; `withInstanceMethods()` enables it broadly and should only be used with narrow-API objects.
- With StandardEvaluationContext, TypeLocator controls class references; ConstructorResolver controls `new`; MethodResolver/MethodFilter controls method invocation; BeanResolver controls `@bean`.
- Registered functions require their own allowlist; do not assume MethodResolver blocks functions.
- Expose only necessary DTOs/view objects, property accessors, and variables; getters can also have side effects.
- Do not evaluate arbitrary user-supplied SpEL sources with the full ApplicationContext or domain services.
- Pass data via variables rather than concatenating input into the source; however, variables do not make an untrusted expression source safe.
- Limit expression size, collection size, auto-growth, regexes, and method cost; do not assume SpEL provides a general-purpose sandbox or timeout.
- Compiler mode is not a security boundary.

## References

- [Spring Framework Reference — Evaluation and SimpleEvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework Reference — Type References](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/types.html)
- [Spring Framework Reference — Constructors](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/constructors.html)
- [Spring Framework Reference — Methods](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/methods.html)
- [Spring Framework Reference — Bean References](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/bean-references.html)
- [Spring Framework API — TypeLocator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/TypeLocator.html)
- [Spring Framework API — ConstructorResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ConstructorResolver.html)
- [Spring Framework API — MethodFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/MethodFilter.html)
- [Spring Framework API — StandardEvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)