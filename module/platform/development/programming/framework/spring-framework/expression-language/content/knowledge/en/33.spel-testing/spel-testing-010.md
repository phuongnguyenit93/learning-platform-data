# Testing Permission Boundaries and Untrusted Expressions in SpEL

## Objectives

When an application evaluates Spring Expression Language (SpEL), the `EvaluationContext` determines which capabilities an expression can use: reading and writing properties, invoking methods, referencing classes with `T(...)`, creating objects with `new`, accessing beans via `@beanName`, or calling registered functions. For expressions controlled by users or external configuration sources, tests must verify that only permitted capabilities work.

Security testing does not merely verify that a valid expression returns the right result. The test suite needs both positive and negative cases: permitted properties remain readable; types, constructors, methods, beans, or functions outside the allowlist are rejected; input data is passed as data; and errors do not leak source, secrets, or internal details.

## 1. Define the policy before writing tests

First, explicitly state what the expression is permitted to do. A simple policy for a read-only rule might include:

- Read a set of known properties on a DTO/view object.
- Use literals, comparisons, logical operators, and necessary arithmetic.
- Use variables whose types are provided by the application.
- No writing properties.
- No invoking arbitrary methods.
- No using type references `T(...)`, constructors `new`, or bean references `@bean`.
- No calling functions if the rule does not need functions.
- No accessing repositories, HTTP clients, the filesystem, message brokers, or administrative services.

If a use case needs a specific method or function, record its exact name, signature, target class, and permitted behavior. A concrete policy enables tests to prove each capability is enabled or blocked.

## 2. Using SimpleEvaluationContext as a restricted baseline

`SimpleEvaluationContext` is suitable when a rule only needs data binding. It does not support type references, constructor invocations, or bean references. Method invocation is disabled by default; the builder can enable instance methods when needed.

Example creating a read-only context:

~~~java
EvaluationContext context = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .build();

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(
        "active == true and age >= 18");

Boolean allowed = expression.getValue(
        context, customerView, Boolean.class);
~~~

With this configuration, tests should verify that needed properties work and excluded features all fail. If property writing is needed, write separate tests for `forReadWriteDataBinding()` and allow only the exact fields that need to change.

Read-only only controls writes through property accessors. It does not guarantee getters are purely read-only. Use DTO/view objects with simple getters that do not access resources and do not mutate state.

## 3. Organizing tests with JUnit

A basic test suite can use JUnit 5 and AssertJ. Use small test objects to define the exact properties exposed:

~~~java
final class CustomerView {
    private final String name;
    private final int age;
    private final boolean active;

    CustomerView(String name, int age, boolean active) {
        this.name = name;
        this.age = age;
        this.active = active;
    }

    public String getName() { return name; }
    public int getAge() { return age; }
    public boolean isActive() { return active; }
}
~~~

Example testing allowed properties:

~~~java
class SpelSecurityTests {

    private final ExpressionParser parser = new SpelExpressionParser();
    private final EvaluationContext context = SimpleEvaluationContext
            .forReadOnlyDataBinding()
            .build();
    private final CustomerView customer =
            new CustomerView("Lan", 28, true);

    @Test
    void allowsApprovedPropertyReads() {
        Boolean result = parser.parseExpression(
                "active == true and age >= 18")
                .getValue(context, customer, Boolean.class);

        assertThat(result).isTrue();
    }
}
~~~

This test is a positive test: it proves the context can still perform permitted business work. A suite with only negative tests can accidentally block valid functionality as well.

## 4. Testing blocked type references

Type references use the `T(package.ClassName)` syntax. If a rule does not need class access, `SimpleEvaluationContext` does not provide type references. Test a representative call to a high-privilege class:

~~~java
@Test
void rejectsTypeReferences() {
    assertThatThrownBy(() -> parser
            .parseExpression("T(java.lang.Runtime).getRuntime()")
            .getValue(context, Object.class))
            .isInstanceOf(EvaluationException.class);
}
~~~

Do not test only one class. Pick classes representative of the application's policy, such as system classes, utility classes, and unexposed internal classes. Tests should verify the result is rejected; do not depend on the full exception message content because messages can change across Spring versions.

If a use case needs a few types in `StandardEvaluationContext`, replace `StandardTypeLocator` with an allowlist implementation. Test both allowed types and rejected types, and check full class names to avoid overly broad package-level allowlists.

## 5. Testing blocked constructor invocations

Constructor invocations use `new`. If there is no need to instantiate objects inside expressions, `SimpleEvaluationContext` does not support this capability:

~~~java
@Test
void rejectsConstructorInvocation() {
    assertThatThrownBy(() -> parser
            .parseExpression("new java.lang.String('unexpected')")
            .getValue(context, Object.class))
            .isInstanceOf(EvaluationException.class);
}
~~~

If the application uses `StandardEvaluationContext`, check the `ConstructorResolver` configuration. Reflective constructor resolvers can be removed when constructor invocation is unnecessary, or an allowlist resolver can be supplied only for specific constructors.

Tests should cover allowed constructors (if any) and disallowed constructors. Do not test only one blocked constructor and infer every other class is blocked too.

## 6. Testing blocked method invocations

Method invocations can execute Java code on the root object or nested objects. With `SimpleEvaluationContext`, method invocation is off by default:

~~~java
@Test
void rejectsInstanceMethodInvocationByDefault() {
    assertThatThrownBy(() -> parser
            .parseExpression("name.toUpperCase()")
            .getValue(context, customer, String.class))
            .isInstanceOf(EvaluationException.class);
}
~~~

This test checks an ordinary method on a property value. Add tests with simulated sensitive methods on a fixture, such as `resetAccount()`, `deleteRecord()`, or `sendMessage()`, and confirm the method is not invoked.

Example using a counter to confirm the method does not run:

~~~java
final class SideEffectProbe {
    private int calls;

    public void dangerousAction() {
        calls++;
    }

    public int getCalls() {
        return calls;
    }
}

@Test
void blockedMethodDoesNotRun() {
    SideEffectProbe probe = new SideEffectProbe();

    assertThatThrownBy(() -> parser
            .parseExpression("dangerousAction()")
            .getValue(context, probe))
            .isInstanceOf(EvaluationException.class);

    assertThat(probe.getCalls()).isZero();
}
~~~

The `calls == 0` assertion is more important than only checking an exception was thrown: it proves no side effect occurred before evaluation failed.

If enabling `withInstanceMethods()`, do not treat it as a method-name allowlist. Inspect exposed objects and use an appropriate resolver/filter when specific methods must be restricted.

## 7. Testing blocked bean references

Bean references use `@beanName` syntax and require a `BeanResolver`. `SimpleEvaluationContext` does not support bean references. With a manual context, do not configure a resolver if the expression does not need Spring beans.

~~~java
@Test
void rejectsBeanReferences() {
    assertThatThrownBy(() -> parser
            .parseExpression("@adminService.resetAll()")
            .getValue(context, Object.class))
            .isInstanceOf(EvaluationException.class);
}
~~~

In tests, there is no need to instantiate a real service with permission to delete data. If resolver behavior needs verification, use a fake bean with a counter and check the counter does not increment. Tests must prove the resolver cannot resolve beans or beans outside the allowlist cannot be obtained.

If the application needs a few beans in expressions, expose a small facade or an allowlist BeanResolver. Test valid beans, invalid beans, and bean aliases if aliases are part of the policy.

## 8. Testing registered and unregistered functions

Functions are called with `#functionName(...)` and registered in the context. MethodResolver does not automatically control all functions; functions added to the context must be checked separately.

Testing an unregistered function:

~~~java
@Test
void rejectsUnregisteredFunction() {
    assertThatThrownBy(() -> parser
            .parseExpression("#dangerousAction()")
            .getValue(context, Object.class))
            .isInstanceOf(EvaluationException.class);
}
~~~

If the policy allows pure functions, register the exact method and test the result:

~~~java
public final class RuleFunctions {
    private RuleFunctions() { }

    public static String normalize(String value) {
        return value == null ? null : value.trim().toLowerCase(Locale.ROOT);
    }
}

Method normalize = RuleFunctions.class.getMethod(
        "normalize", String.class);
standardContext.registerFunction("normalize", normalize);

Expression expression = parser.parseExpression("#normalize('  LAN  ')");
assertThat(expression.getValue(standardContext, String.class))
        .isEqualTo("lan");
~~~

Do not register functions that can run commands, read/write files, access arbitrary URLs, update databases, or send messages. Add tests confirming pure functions do not mutate input objects or shared state.

## 9. Testing property access and getter side effects

Blocking method invocation does not mean blocking getters. When SpEL reads `customer.name`, the property accessor can invoke `getName()`. Getters can contain unexpected logic such as lazy loading, database access, or state mutation.

To test:

- Use a fixture whose getters increment a counter or record invocations.
- Evaluate properties in the intended context.
- Confirm only permitted getters are called.
- Do not put ORM entities with lazy relationships or service-backed properties into the root object of untrusted expressions.
- If exact property allowlisting is needed, use a DTO/view object or a custom `PropertyAccessor` with an allowed property list.

With custom accessors, test matching target classes, wrong target classes, allowed properties, blocked properties, and write operations. Do not assume a read-only builder turns every custom accessor read-only; the accessor implementation itself must enforce the policy.

## 10. Testing that input is passed as data, not source

Do not concatenate user strings directly into expression source. Use a fixed expression and pass values via variables:

~~~java
Expression expression = parser.parseExpression("name == #suppliedName");
StandardEvaluationContext context = new StandardEvaluationContext(customer);
context.setVariable("suppliedName", suppliedInput);

Boolean matches = expression.getValue(context, Boolean.class);
~~~

Tests should use a string resembling SpEL syntax yet treat it as data:

~~~java
String suppliedInput = "T(java.lang.Runtime).getRuntime()";
~~~

The comparison result is simply true/false based on the string value. That content is not parsed a second time and is not executed as a type reference.

This is an important test for detecting expression injection. However, passing input via variables does not make user-controlled expression source safe. If users can edit the source, supported context and syntax must still be restricted or arbitrary SpEL replaced with a typed DSL/schema.

## 11. Testing invalid expressions and denied permissions

Distinguish three cases:

| Case | Expected result |
| --- | --- |
| Expression is valid and uses permitted features | Evaluates successfully with expected result. |
| Expression has invalid syntax | Parsing fails with `ParseException`. |
| Expression has valid syntax but uses blocked capabilities | Evaluation fails with `EvaluationException` or a matching subtype. |

Parse error example:

~~~java
assertThatThrownBy(() -> parser.parseExpression("age > > 18"))
        .isInstanceOf(ParseException.class);
~~~

Denied capability examples must be checked at the `getValue` stage, because many expressions are only resolved when evaluation occurs.

Do not rely on exact message text like "method not found" or "type not allowed" in long-lived tests. Prefer checking the exception family, application error codes, and that no side effects occurred.

## 12. Testing restrictions when using StandardEvaluationContext

If a use case needs `StandardEvaluationContext`, configure each extension point according to policy:

| Extension point | Permission to control | Tests to include |
| --- | --- | --- |
| `TypeLocator` | Classes referenced via `T(...)`. | Allowlisted types resolve; non-allowlisted types are rejected. |
| `ConstructorResolver` | Classes/constructors callable via `new`. | Allowed constructors run; non-allowlisted constructors do not run. |
| `MethodResolver` | Instance/static methods callable. | Allowed methods and signatures work; dangerous methods do not resolve. |
| `MethodFilter` | Reflective methods on a specific type. | Methods in the filter are kept; others are excluded. |
| `BeanResolver` | Beans retrieved via `@beanName`. | Allowlisted beans resolve; non-allowlisted beans are rejected. |
| Registered functions | Java methods called via `#function(...)`. | Allowed functions work; unregistered functions do not work. |
| `PropertyAccessor` | Properties read/written. | Property allowlist and read/write policy are enforced. |

Example blocking all method and constructor invocations when unnecessary:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext(customerView);
context.setMethodResolvers(Collections.emptyList());
context.setConstructorResolvers(Collections.emptyList());
~~~

To restrict types, replace `StandardTypeLocator` with an allowlist `TypeLocator`. Do not configure a `BeanResolver` if bean references are not needed. Check both variables and the root object because resolver restrictions do not render exposed objects harmless.

`MethodFilter` applies only to reflective method resolvers on registered types. If changing resolvers or exposing other classes, test the policy for those access paths too.

## 13. Testing large inputs and resource limits

Untrusted expressions can consume resources even without calling dangerous methods. Set and test limits at the application layer:

- Maximum expression source length.
- Number of expressions parsed/stored and expression creation rate.
- List/map sizes, object depth, and number of elements traversed by selection/projection.
- Array sizes and collection auto-growth.
- Allowed string lengths and regexes.
- Execution duration of exposed functions/methods.
- Concurrent evaluation requests and rate limits.

Do not assume SpEL provides a general timeout or a CPU/memory-budgeted sandbox. If execution time must be bounded, run evaluation in an architecture with appropriate timeout/concurrency controls; do not rely on thread interruption alone to guarantee all Java code stops immediately.

For user-controlled regexes, consider disabling the `matches` feature or using a regex policy/engine with explicit limits. Test both long inputs and patterns that can cause backtracking.

## 14. Testing fail-closed behavior and error reporting

If expressions are used for authorization or deciding whether to allow an action, evaluation errors must never turn into `true` or be treated as success.

Tests need to confirm:

- Valid rule returning true permits the action per policy.
- Valid rule returning false denies the action per policy.
- Parse/evaluation errors produce a distinct error state and do not permit the action.
- Responses contain no raw expression, stack trace, exception message, or secrets.
- Default logs record only rule ID/version, correlation ID, and error category.

Example checking fail-closed state:

~~~java
RuleResult result = ruleEvaluator.evaluate(untrustedRule, customerView);

assertThat(result.status()).isEqualTo(RuleStatus.ERROR);
assertThat(result.isAllowed()).isFalse();
~~~

`RuleResult` is an application-defined type. Keep `ERROR` distinct from `DENY` so operations can distinguish rules that evaluated cleanly and denied from rules that could not be evaluated.

## 15. Regression matrix for CI

A short test table helps ensure context or Spring version changes do not accidentally open extra permissions:

| Group | Positive test | Negative test |
| --- | --- | --- |
| Property | Read permitted DTO fields. | Read properties outside allowlist. |
| Write access | Update permitted fields if needed by use case. | Write sensitive fields or write in a read-only context. |
| Type reference | Resolve allowlisted types if permitted. | Resolve `Runtime` or classes outside allowlist. |
| Constructor | Call approved constructors if needed. | Instantiate unpermitted classes. |
| Method | Call allowlisted pure methods. | Call methods with side effects or outside allowlist. |
| Bean | Resolve permitted facade beans. | Resolve repository/admin beans outside allowlist. |
| Function | Call registered pure helpers. | Call unregistered or dangerous functions. |
| Input | Data containing SpEL characters is compared as a string. | Input is concatenated into source or parsed a second time. |
| Error handling | Stable error codes, safe responses. | Source, secrets, stack traces, or rejected values leaked. |
| Resource limits | Expressions within limits run normally. | Oversized source, huge collections, or overly complex regexes are rejected. |

Run the regression suite whenever changing Spring Framework, `EvaluationContext`, resolvers/accessors, function registrations, root DTOs, or rule parsers. Security configuration is part of application behavior and must be tested like code.

## 16. Common errors and how to handle them

| Symptom | Cause to check | How to handle |
| --- | --- | --- |
| Test only verifies the expression throws an exception | The method may have already executed side effects before failing at a later step. | Use a probe/counter to verify the action did not run. |
| Negative tests pass yet valid rules are also blocked | Only wrote rejection tests, lacking positive tests. | Test permitted and forbidden properties/operations in parallel. |
| `T(...)` still works in Standard context | Default `TypeLocator` is still configured. | Use an allowlist locator or a context not supporting type references. |
| Constructors still run | Reflective constructor resolver is still active. | Remove the resolver or use an allowlist resolver and test out-of-policy constructors. |
| Dangerous methods can still be called | Reflective method resolver or broad-API object is still exposed. | Restrict resolvers, filter by type, and constrain the root object. |
| Bean references work unexpectedly | Context has a BeanResolver or uses a preconfigured Spring expression template. | Check the actual context; expose only allowlisted beans. |
| Dangerous functions still run | Functions were registered as variables/methods. | Audit and separately test the function registry. |
| Input strings execute as expressions | Input was concatenated into source or parsed a second time. | Use a fixed source and pass data via typed variables. |
| Getters trigger unintended queries | Actual DTO is an entity with lazy loading or getters with side effects. | Use pre-populated view objects and test getters/accessors. |
| Evaluation errors treated as allow | Exceptions were caught and returned `true` or a default value. | Use a distinct ERROR status and fail-closed behavior. |

## Key takeaways

- Write the permission policy first, then create positive and negative tests for each capability.
- Use `SimpleEvaluationContext.forReadOnlyDataBinding()` when only reading properties; method invocation is off by default.
- Separately test type references, constructors, methods, bean references, registered functions, and property accessors.
- Test side effects using a probe/counter; an exception alone does not prove a method did not run.
- `MethodFilter` only restricts reflective methods on registered types; it does not replace controlling other resolvers and objects.
- Pass user input via variables, never concatenate it into expression source; if the source is user-controlled, syntax and permissions must still be restricted.
- Use DTO/view objects with pure read-only getters; a read-only context does not automatically guarantee getters have no side effects.
- Test parse errors, evaluation errors, and business false as three distinct outcomes.
- For authorization, evaluation errors must fail closed and be represented by a distinct ERROR status.
- Set limits on expression length, collection sizes, auto-growth, regexes, and concurrency; SpEL does not provide a general sandbox/timeout.
- Run the regression suite when changing the Spring version or EvaluationContext/resolver/accessor configuration.

## Official references

- [Spring Framework Reference — Evaluation and SimpleEvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework Reference — Type References](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/types.html)
- [Spring Framework Reference — Constructors](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/constructors.html)
- [Spring Framework Reference — Methods](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/methods.html)
- [Spring Framework Reference — Bean References](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/bean-references.html)
- [Spring Framework API — SimpleEvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
- [Spring Framework API — TypeLocator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/TypeLocator.html)
- [Spring Framework API — MethodFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/MethodFilter.html)
- [Spring Framework API — ConstructorResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ConstructorResolver.html)
- [Spring Framework API — StandardEvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)