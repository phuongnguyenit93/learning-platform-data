# Designing Allowlists and Testing Privilege-Escalation Cases

When an application allows configuration or user-supplied Spring Expression Language (SpEL) expressions, it is necessary to define precisely which data an expression may read and which operations it may perform. An **Allowlist** is an explicit list of properties, methods, Java types, and behaviors that an expression is authorized to use. Every capability outside that list must be denied.

This is a security concern because SpEL can do far more than arithmetic or comparisons. With a broad EvaluationContext, an expression can access properties, invoke methods, instantiate objects, reference Java types, or reference beans if the corresponding mechanisms are enabled. If the expression string comes from an untrusted source, evaluating it in a default context can open unintended access privileges.

Secure design begins with limiting exposed data, choosing the least-capable EvaluationContext, and then testing both valid expressions and attempts to bypass restrictions.

## Defining the Threat Model

Before building an allowlist, clarify who controls each component:

- **Expression source:** can users enter or edit the entire SpEL string, or only choose a predefined rule?
- **Input values:** do users only supply values such as numbers, strings, and dates, while the expression is controlled by the application?
- **Root object:** is the expression evaluated on a restricted DTO or on a business object with many references?
- **EvaluationContext:** does the context provide broad method resolvers, type locators, bean resolvers, or constructor resolvers?
- **Output:** is the result displayed, used for authorization decisions, written to a database, or forwarded to another system?

Clearly distinguish **input data** from **expression code**. If users only send values such as names, quantities, or thresholds, pass them as variables in the EvaluationContext. Do not concatenate that data directly into the SpEL string and re-parse it.

Example of a safer and more controllable way to pass data:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("minimum", minimumFromRequest);
context.setVariable("status", statusFromRequest);

Expression expression =
        parser.parseExpression("amount >= #minimum and state == #status");
~~~

Request values are passed as data. They are not interpreted as SpEL syntax. Conversely, if input is concatenated directly into the expression string, characters supplied by the user can alter the structure of the expression.

## Preferring an EvaluationContext with a Small Access Surface

**StandardEvaluationContext** provides broad flexibility and includes default reflective mechanisms for accessing properties, calling methods, and instantiating objects. It suits application-controlled expressions, but requires very careful configuration if the expression source is untrusted.

If you only need to read properties to evaluate conditions, consider **SimpleEvaluationContext**. This context is designed for a subset of SpEL features and does not support type references, constructor invocation, or bean references. Method invocation is also not enabled by default in typical data binding configurations.

Example of a read-only context for data binding:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

A read-only context restricts property assignment through SpEL. It does not make Java objects immutable, does not copy collections, and does not stop other Java code from mutating referenced objects. Therefore, still use a small root object with an appropriate lifecycle.

If a more exact property allowlist is needed, a dedicated PropertyAccessor can be provided:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forPropertyAccessors(
                new AllowlistedCriteriaAccessor())
                .build();
~~~

The accessor should read only properties defined in policy. If the use case does not need method invocation, do not enable instance methods and do not register additional MethodResolvers.

## Designing the Root Object Around an Allowlist

Do not pass entities, services, repositories, the application context, or objects with many references as the root object of externally supplied expressions. Those objects can open access paths to data or behaviors unrelated to the expression's purpose.

Create a small DTO containing only the necessary values:

~~~java
public final class PricingFacts {
    private final String region;
    private final BigDecimal amount;
    private final boolean active;

    public PricingFacts(
            String region,
            BigDecimal amount,
            boolean active) {
        this.region = region;
        this.amount = amount;
        this.active = active;
    }

    public String getRegion() {
        return region;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

The expression can check selected properties:

~~~java
Expression expression = parser.parseExpression(
        "active == true and amount >= #minimum");

Boolean accepted =
        expression.getValue(context, facts, Boolean.class);
~~~

The root object holds only the data needed for the condition. Do not put side-effecting methods, services, or resource-managing objects into the DTO. If a property is not needed by the expression, it is best not to expose it at all.

DTOs should prefer simple, immutable, or safely copyable value types. For collections and Maps, include only necessary elements and avoid letting expressions access mutable objects that can alter application state.

## Allowlisted PropertyAccessor

**PropertyAccessor** determines whether SpEL can read or write a property on a target. An allowlisted accessor should check both the target type and the property name. For read-only expressions, **canWrite(...)** must return false and **write(...)** must reject the operation.

Abbreviated example for a DTO with two permitted properties:

~~~java
public final class CriteriaAccessor implements PropertyAccessor {

    @Override
    public Class<?>[] getSpecificTargetClasses() {
        return new Class<?>[] { PricingFacts.class };
    }

    @Override
    public boolean canRead(
            EvaluationContext context,
            Object target,
            String name) {
        if (target == null || target.getClass() != PricingFacts.class) {
            return false;
        }

        return "region".equals(name)
                || "amount".equals(name);
    }

    @Override
    public TypedValue read(
            EvaluationContext context,
            Object target,
            String name) throws AccessException {
        if (!canRead(context, target, name)) {
            throw new AccessException("Property is not allowlisted");
        }

        PricingFacts facts = (PricingFacts) target;

        if ("region".equals(name)) {
            return new TypedValue(facts.getRegion());
        }

        if ("amount".equals(name)) {
            return new TypedValue(facts.getAmount());
        }

        throw new AccessException("Unknown property");
    }

    @Override
    public boolean canWrite(
            EvaluationContext context,
            Object target,
            String name) {
        return false;
    }

    @Override
    public void write(
            EvaluationContext context,
            Object target,
            String name,
            Object newValue) throws AccessException {
        throw new AccessException("Read-only access");
    }
}
~~~

Register this accessor using **SimpleEvaluationContext.forPropertyAccessors(...)** so the context uses only the provided accessor. When using StandardEvaluationContext, note that adding an allowlisted accessor while keeping ReflectivePropertyAccessor can create a broader fallback than intended.

An allowlist that checks only property names is insufficient if it applies to every target type. Check the target class, return types, and nested properties as well. If access to `customer.address.city` is permitted, every object layer needs an appropriate access policy.

## Method Allowlist

Method invocation significantly expands what an expression can do. A method can read sensitive data, mutate state, access files or the network, or invoke other application components.

If calling methods is not needed, leave method invocation disabled. If genuinely required, permit only pure methods with simple inputs and outputs and no side effects.

With StandardEvaluationContext, **MethodResolver** can restrict calls by:

- Exact type of the target object.
- Method name.
- Argument count and types.
- Return type.
- Specific permitted overloads.

Do not allowlist by method name alone. Two different classes can have methods with the same name but completely different behaviors. An overload can also accept a broader argument type and cause effects that another overload does not.

If using a custom resolver, do not leave a broad ReflectiveMethodResolver as a fallback when the goal is to reject every method outside the list. When a custom resolver returns null, the next resolver in line can handle that call.

## Type References and ConstructorResolver

The **T(...)** syntax allows an expression to reference Java types. If TypeLocator resolves a type, the expression can read static fields or invoke static methods. Some static methods can produce side effects.

The **new ...(...)** syntax allows instantiating objects through constructors. With StandardEvaluationContext, the default ReflectiveConstructorResolver can locate matching constructors.

If the expression source is untrusted, reject type references and constructor invocation unless there is a specific use case. SimpleEvaluationContext does not support these two capabilities. If StandardEvaluationContext must be used:

- Use an allowlisted TypeLocator rather than permitting arbitrary resolution.
- Register a ConstructorResolver only for selected types and constructors.
- Do not leave broad reflective resolvers as an unintended fallback.
- Validate both arguments and result types.
- Do not allow instantiating objects whose constructors read resources or produce side effects.

StandardTypeLocator's package imports are only a convenience for resolving short names, not a security mechanism. Registering only one package does not mean other types are blocked if fully qualified names can still be resolved.

## Do Not Expose Broadly Privileged Beans or Objects

The **@beanName** syntax can reference Spring beans if EvaluationContext has a BeanResolver. Do not configure a BeanResolver for expressions that do not need bean access.

Avoid placing services or repositories into variables. An object variable does not merely hold data; if the context enables method invocation or appropriate property access, the expression can use that object's capabilities.

If a business function is needed, consider computing the result in Java and passing the value into the context. If exposing a function is unavoidable, register only controlled static methods or small wrappers without access to resources beyond their purpose.

## Do Not Rely on String Blacklists

Do not try to protect SpEL by searching for and stripping strings such as **Runtime**, **Class**, **getClass**, **new**, or **T(**. Blacklists routinely miss equivalent syntax, nested expressions, property traversal, overloads, aliases, or other language capabilities.

Instead:

1. Permit only the necessary capabilities.
2. Restrict the root object and values in the context.
3. Use allowlisted accessors/resolvers.
4. Deny every undeclared capability.
5. If the business logic only needs a small conditional language, consider building a custom DSL with a restricted grammar rather than accepting arbitrary SpEL.

Do not rely on inspecting SpEL's internal AST as a security boundary unless the application tightly controls the Spring version and every supported node type. An incomplete AST blacklist can also let dangerous behavior slip through.

## Restricting Template Expressions and Expression Injection

If the application only needs to evaluate plain expressions, use **parseExpression(String)**. Do not enable template parsing for user data without a clear requirement.

Template expressions allow embedding SpEL inside text, typically with **#{** and **}** delimiters. If a user can insert delimiters into template content and the whole string is parsed as a template, part of the data can become expression code.

Do not concatenate untrusted data into the expression source. Keep the expression under application control and pass input via variables:

~~~java
context.setVariable("searchText", userSuppliedText);

Expression expression =
        parser.parseExpression("#searchText == #expectedText");
~~~

In this example, `userSuppliedText` is a String value. SpEL-like syntax characters inside that value are not re-parsed as an expression.

If users must be allowed to edit templates, treat templates as executable code. Control who is permitted to edit them, use a restricted context, and escape results according to the output format such as HTML. SpEL does not automatically escape results for HTML, SQL, or shells.

## Controlling Cost and Complexity

An expression does not need to call a dangerous method to consume heavy CPU or memory if it iterates over large collections, builds large results, or uses expensive computational operations.

Measures to apply:

- Limit expression source length.
- Limit collection sizes and element counts placed into the context.
- Restrict property access depth and expression complexity.
- Do not expose methods with unbounded runtime or network dependencies.
- Avoid letting user expressions supply regexes or operations capable of creating abnormal workloads without controls.
- Rate-limit evaluation frequency and monitor execution time.

SpEL does not provide a general-purpose safe timeout to arbitrarily stop a running method. Do not treat interrupting a thread as a reliable sandboxing measure. If genuinely untrusted expressions with resource-exhaustion risk must be evaluated, isolate them in a process or environment with appropriate resource limits.

## Two-Way Testing of the Allowlist

The test suite must prove two things:

- Permitted expressions work properly.
- Expressions outside the allowlist are rejected and cause no side effects.

Do not check only Boolean results. Verify that the root object, collections, side-effect counters, and application state remain unchanged after bypass attempts.

### Testing Valid Cases

Example using JUnit:

~~~java
@Test
void evaluatesAllowlistedCondition() {
    PricingFacts facts = new PricingFacts(
            "VN",
            new BigDecimal("120.00"),
            true);

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadOnlyDataBinding()
                    .build();

    Expression expression = new SpelExpressionParser()
            .parseExpression(
                    "active == true and amount >= #minimum");

    context.setVariable("minimum", new BigDecimal("100.00"));

    Boolean result =
            expression.getValue(context, facts, Boolean.class);

    assertTrue(result);
}
~~~

This test confirms that permitted properties are readable and input variables are applied correctly. A higher threshold case can be added to confirm a `false` result.

### Testing Rejected Type References

Use the following strings as test inputs in a restricted context:

~~~java
"T(java.lang.Runtime)"
"T(java.lang.System).getProperties()"
~~~

The parser may accept the expression structure, but the EvaluationContext does not support type references so evaluation must be rejected. The strings above are test data only; do not evaluate them in a broad StandardEvaluationContext.

### Testing Rejected Constructor Invocation

~~~java
"new java.io.File('sample.txt')"
~~~

A read-only context does not support constructor invocation. Tests must verify the expression does not instantiate objects via constructors. There is no need to execute file read/write behavior to verify this.

### Testing Rejected Method Invocation

~~~java
"#root.toString()"
"#root.getClass()"
~~~

If policy disallows method invocation, expressions calling methods must fail during evaluation. Test against the real context used in production; do not infer from a test context with a different configuration.

### Testing Rejected Bean References

~~~java
"@sensitiveService"
~~~

If the context has no BeanResolver or uses SimpleEvaluationContext, bean references must be rejected. Do not register a real service solely to run a rejection test; a fake bean with a call counter can be used to confirm it is never invoked if an integration test needs to verify the access path.

### Testing Assignment and Property Writes

~~~java
"active = false"
~~~

In a read-only context, property assignment must be rejected. After evaluation fails, re-check the `active` value on the root object to ensure state is unchanged.

### Testing Non-Allowlisted Properties

If a DTO or accessor permits only `region` and `amount`, try reading another property such as `internalCode` or `owner`. Evaluation must fail and must not fall back to a reflective accessor.

In particular, test nested properties, Map keys, array indices, and the `class` property. Do not test only a single direct property name; test traversal paths that could lead to other objects.

## Privilege-Escalation Test Matrix

Tests can be organized by category:

| Category | Sample Input | Expected Outcome |
|---|---|---|
| Valid property | **amount >= #minimum** | Evaluated |
| Non-allowlisted property | **internalCode** | Rejected |
| Out-of-scope nested property | **owner.account.secret** | Rejected |
| Property write | **active = false** | Rejected |
| Method invocation | **#root.getClass()** | Rejected unless allowlisted |
| Type reference | **T(java.lang.Runtime)** | Rejected |
| Static method | **T(java.lang.System).getProperties()** | Rejected |
| Constructor | **new java.io.File('x')** | Rejected |
| Bean reference | **@sensitiveService** | Rejected |
| Template injection | Content with **#{...}** delimiters | Not re-parsed if treated strictly as data |
| Collection traversal | Selection/projection on unexposed data | Rejected or bounded per policy |
| Oversized input | Expression exceeding length limit | Rejected before evaluation |

Expected outcomes must be defined according to the actual context. If policy actively permits a method or collection operation, document the exception explicitly and add tests for that exact capability.

## Verifying Zero Side Effects

A security test must verify unchanged state, not merely that an exception was thrown.

For instance, a test DTO with setter counters or a mock collaborator with a call counter. Before evaluating a rejected expression, record initial state. Afterward, verify:

- Setters were not called.
- Methods outside the allowlist were not executed.
- Constructors outside the allowlist were not invoked.
- Source collections did not have elements added, removed, or replaced.
- Mock beans or services received no calls.
- No unexpected events or persistence state changes occurred.

If testing an entity managed by a persistence context, verify both in-memory state and post-transaction data appropriately. An in-memory assignment could be flushed to the database by the ORM on flush or commit.

## Testing Variables and Context Isolation

Variables placed into EvaluationContext are data, yet variable values can still be objects with behavior. Verify that the context accepts only normalized input types and never receives services or broadly privileged objects.

If contexts are created per request, test two consecutive requests with two different sets of variables to verify no values leak across. If an Expression is cached for reuse, create an appropriate context for each evaluation and do not share a mutable context across threads when variables can change.

Expression caches must also be tied to security policy. Do not take an expression parsed in a broad context and reuse it in a place with a different policy without accounting for access differences.

## Testing Parser and Input Limits

Alongside capabilities, test resource limits:

- Empty or whitespace-only expressions.
- Expressions exceeding the length limit.
- Expressions with many levels of nesting.
- Input collections exceeding size limits.
- Expressions with multiple chained selections/projections.
- Null values, incompatible types, and conversion failures.
- Templates containing unexpected delimiters.
- Variants with whitespace, letter casing, or Unicode characters.

Do not test only a blacklist by trying a few known attack strings. Tests must validate the full capability policy: everything permitted works, and everything unpermitted has no alternative access path.

## Handling Errors Without Leaking Internals

When an expression is rejected, the application should return a brief external message, such as **Expression is not permitted** or **Invalid rule**. Do not return stack traces, internal class names, file paths, bean configurations, or runtime details to users.

On the server side, log the error category, rule ID, request identifier, and denied capability group. Do not log the entire expression or variable values if they may contain personal data, tokens, or secrets.

Separating parse errors, evaluation errors, and policy errors makes operations easier. However, do not turn detailed error messages into an oracle for users probing internal structure.

## Implementation Checklist

- Determine whether the expression source is user-controlled or only input data is controlled.
- Use SimpleEvaluationContext if only property reads are needed and advanced capabilities are unnecessary.
- Create a small root DTO containing only required data.
- Use an allowlisted PropertyAccessor for exact properties.
- Keep method invocation disabled if not needed.
- If methods are needed, allowlist by target type and signature, not name alone.
- Reject type references, constructor invocation, and bean references unless specifically required.
- Do not leave broad reflective resolvers as unintended fallbacks.
- Pass input via variables rather than concatenating into the expression source.
- Do not parse user data as a template.
- Bound length, data size, and evaluation cost.
- Test positive, negative, nested access, mutation, side effects, and context isolation.
- Escape/encode results according to the output format.
- Monitor and update tests when upgrading Spring versions.

## Conclusion

Designing an allowlist for SpEL requires constraining every surface an expression can access: root object, properties, methods, types, constructors, beans, and variables. Prefer SimpleEvaluationContext with a small DTO when only reading data; if advanced capabilities are needed, register explicitly allowlisted accessors and resolvers, and never let reflective fallbacks reopen denied privileges.

The test suite must prove valid expressions work properly and privilege-escalation attempts are blocked without side effects. In particular, test nested properties, methods, type references, constructors, bean references, assignments, template injection, large data, and context reuse. If the business logic only needs a small conditional language, a custom DSL with a restricted grammar is usually easier to secure than accepting arbitrary SpEL.
